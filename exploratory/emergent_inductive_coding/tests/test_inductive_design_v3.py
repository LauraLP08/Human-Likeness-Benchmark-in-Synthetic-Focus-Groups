"""
Design-v3 offline tests: the Stage E split, the Stage F assignment rule, and a budget
whose call counts are derived rather than hard-coded.

No API call. Complements `test_inductive_design.py`, which covers the universe, the
canonical paths, codebook absence and cluster alignment.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_alignment as al     # noqa: E402
import inductive_budget as bud       # noqa: E402
import inductive_inventory as inv    # noqa: E402


@pytest.fixture(scope="module")
def inventory():
    return inv.build()


@pytest.fixture(scope="module")
def budget():
    return bud.plan()


def _themes(n, cond, prefix):
    return [{"raw_theme_id": f"{prefix}{i}", "condition": cond,
             "label": f"{cond} label {i}", "definition": f"{cond} definition {i}"}
            for i in range(n)]


# =========================== Stage E1 / E2 ================================
def test_balanced_subsample_takes_equal_numbers_per_condition():
    raw = (_themes(4, "human", "h") + _themes(40, "enriched", "e")
           + _themes(40, "demographics-only", "d"))
    sub = al.balanced_subsample(raw)
    c = Counter(t["condition"] for t in sub)
    assert c["human"] == 4 and c["enriched"] == 4 and c["demographics-only"] == 4
    assert len(sub) == 12


def test_balanced_subsample_is_deterministic():
    raw = _themes(3, "human", "h") + _themes(9, "enriched", "e")
    a = [t["raw_theme_id"] for t in al.balanced_subsample(raw)]
    b = [t["raw_theme_id"] for t in al.balanced_subsample(list(reversed(raw)))]
    assert a == b


def test_e1_prompt_may_not_contain_themes_outside_the_subsample():
    """
    E1 exists to test whether the pooled taxonomy is shaped by synthetic volume. If a
    non-selected theme reaches the E1 prompt, the balanced taxonomy is contaminated by
    the dominant pool and the sensitivity analysis measures nothing.
    """
    raw = (_themes(2, "human", "h") + _themes(6, "enriched", "e")
           + _themes(6, "demographics-only", "d"))
    sub = al.balanced_subsample(raw)
    clean = "Consolidate these themes:\n" + "\n".join(
        f"{t['raw_theme_id']}: {t['label']} - {t['definition']}" for t in sub)
    assert al.e1_prompt_problems(clean, sub, raw) == []


def test_e1_gate_fires_when_an_out_of_subsample_theme_leaks():
    raw = (_themes(2, "human", "h") + _themes(6, "enriched", "e")
           + _themes(6, "demographics-only", "d"))
    sub = al.balanced_subsample(raw)
    inside = {s["raw_theme_id"] for s in sub}
    outside = next(t for t in raw if t["raw_theme_id"] not in inside)
    leaked = ("Consolidate these themes:\n"
              + "\n".join(f"{t['raw_theme_id']}: {t['label']}" for t in sub)
              + f"\n{outside['raw_theme_id']}: {outside['label']}")
    problems = al.e1_prompt_problems(leaked, sub, raw)
    assert problems, "an out-of-subsample theme reached E1 undetected"
    assert any(outside["raw_theme_id"] in p for p in problems)


def test_e2_uses_a_frozen_taxonomy():
    tax = [{"cluster_id": "c1", "label": "one", "definition": "d1"},
           {"cluster_id": "c2", "label": "two", "definition": "d2"}]
    key = al.frozen_taxonomy_key(tax)
    ok = {"t1": "c1", "t2": "c2", "t3": al.NEW_CLUSTER, "t4": al.UNCERTAIN}
    assert al.e2_problems(tax, key, ok) == []


def test_e2_detects_a_revised_e1_taxonomy():
    tax = [{"cluster_id": "c1", "label": "one", "definition": "d1"}]
    key = al.frozen_taxonomy_key(tax)
    revised = tax + [{"cluster_id": "c9", "label": "added later", "definition": "d9"}]
    assert any("was revised" in p for p in al.e2_problems(revised, key, {"t1": "c9"}))


def test_e2_rejects_an_assignment_to_an_unknown_cluster():
    tax = [{"cluster_id": "c1", "label": "one", "definition": "d1"}]
    key = al.frozen_taxonomy_key(tax)
    problems = al.e2_problems(tax, key, {"t1": "c7"})
    assert any("not in the frozen E1 taxonomy" in p for p in problems)


def test_new_cluster_and_uncertain_remain_available_in_e2():
    tax = [{"cluster_id": "c1", "label": "one", "definition": "d1"}]
    key = al.frozen_taxonomy_key(tax)
    assert al.e2_problems(tax, key, {"t1": al.NEW_CLUSTER}) == []
    assert al.e2_problems(tax, key, {"t2": al.UNCERTAIN}) == []


# =============================== Stage F ==================================
def test_stage_f_records_must_carry_an_adjudicated_verdict():
    good = [{"pass2_theme_id": "p1", "verdict": al.SAME_CLUSTER,
             "canonical_cluster_id": "c3", "decided_by": "adjudicator",
             "similarity_ordered_candidates": ["c3", "c1"]},
            {"pass2_theme_id": "p2", "verdict": al.NEW_CLUSTER,
             "decided_by": "adjudicator"},
            {"pass2_theme_id": "p3", "verdict": al.UNCERTAIN,
             "decided_by": "adjudicator"}]
    assert al.stage_f_assignment_problems(good) == []


def test_stage_f_rejects_nearest_neighbour_as_a_decision():
    """
    The v2 defect: measuring stability against the "nearest pass-1 counterpart" lets a
    similarity score decide a correspondence, contradicting the rule that similarity may
    propose but never decide.
    """
    bad = [{"pass2_theme_id": "p1", "nearest_pass1_theme": "t42",
            "verdict": al.SAME_CLUSTER, "canonical_cluster_id": "c3"}]
    assert any("nearest-neighbour field" in p
               for p in al.stage_f_assignment_problems(bad))


def test_stage_f_rejects_a_similarity_decided_record():
    bad = [{"pass2_theme_id": "p1", "verdict": al.SAME_CLUSTER,
            "canonical_cluster_id": "c1", "decided_by": "cosine_similarity"}]
    assert al.stage_f_assignment_problems(bad) != []


def test_similarity_may_order_candidates_without_deciding():
    """
    The case that makes the rule bite: the lexically closest cluster is substantively
    wrong. Similarity ranks it first; the adjudicator picks the second. That record must
    pass, because ordering is not deciding.
    """
    rec = [{"pass2_theme_id": "p1",
            "similarity_ordered_candidates": ["c_meat_texture", "c_masculinity_norms"],
            "verdict": al.SAME_CLUSTER,
            "canonical_cluster_id": "c_masculinity_norms",
            "decided_by": "adjudicator",
            "note": ("lexically nearest was c_meat_texture on the shared words meat and "
                     "steak; the theme is about peer expectation, not texture")}]
    assert al.stage_f_assignment_problems(rec) == []
    assert rec[0]["canonical_cluster_id"] != rec[0]["similarity_ordered_candidates"][0]


def test_stage_f_verdict_and_cluster_id_must_agree():
    assert al.stage_f_assignment_problems(
        [{"pass2_theme_id": "p1", "verdict": al.SAME_CLUSTER}]) != []
    assert al.stage_f_assignment_problems(
        [{"pass2_theme_id": "p2", "verdict": al.NEW_CLUSTER,
          "canonical_cluster_id": "c1"}]) != []


# =============================== budget ===================================
def test_call_counts_are_derived_from_the_manifest_not_hard_coded(budget, inventory):
    stages = {s["stage"]: s for s in budget["stages"]}
    n_units = inventory["n_units"]
    n_questions = len({u["question"] for u in inventory["units"]})
    assert stages["A_EXTRACTION"]["calls"] == n_units == 174
    assert stages["B_CANONICAL_TAXONOMY"]["calls"] == n_questions == 5
    assert stages["C_REASSIGNMENT_AUDITS"]["calls"] == n_questions * 2
    assert stages["E1_BALANCED_TAXONOMY_CONSTRUCTION"]["calls"] == n_questions
    assert stages["E2_FULL_REASSIGNMENT_TO_BALANCED_TAXONOMY"]["calls"] == n_questions
    assert stages["F2_PASS2_ASSIGNMENT_TO_CANONICAL_TAXONOMY"]["calls"] == n_questions
    assert budget["corpus"]["n_units"] == n_units


def test_budget_reacts_to_the_corpus_rather_than_a_literal(monkeypatch):
    """
    If the corpus shrank, the extraction call count must shrink with it. Stage A is
    derived from the SEGMENTED units, so that is what gets shrunk here — the budget no
    longer reads the inventory's unit list for this quantity.
    """
    import inductive_segments as _seg
    real = _seg.build
    try:
        monkeypatch.setattr(bud.seg, "build",
                            lambda: {**real(), "segments": real()["segments"][:100]})
        b2 = bud.plan()
        assert b2["stages"][0]["calls"] == 100
        assert b2["corpus"]["n_units"] == 100
    finally:
        monkeypatch.undo()
        bud.plan()          # restore the artefact to the real corpus


def test_stage_e_is_split_into_two_budgeted_stages(budget):
    e1 = next(s for s in budget["stages"] if s["stage"].startswith("E1"))
    e2 = next(s for s in budget["stages"] if s["stage"].startswith("E2"))
    for s in (e1, e2):
        assert s["calls"] > 0 and s["input_tokens"] > 0 and s["output_tokens"] > 0
    # E2 reads every raw theme; E1 reads only the balanced subsample
    assert e2["input_tokens"] > e1["input_tokens"]
    assert "ONLY the balanced subsample" in e1["derivation"]
    assert "never revised" in e2["derivation"]


def test_stage_f_is_split_and_pass2_assignment_is_budgeted(budget):
    names = [s["stage"] for s in budget["stages"]]
    assert "F1_INSTABILITY_REEXTRACTION" in names
    assert "F2_PASS2_ASSIGNMENT_TO_CANONICAL_TAXONOMY" in names
    f2 = next(s for s in budget["stages"] if s["stage"].startswith("F2"))
    assert f2["calls"] > 0 and f2["input_tokens"] > 0
    assert "nearest-neighbour" in f2["derivation"]


def test_stage_f_covers_every_question_condition_and_length_tercile(budget):
    cells = budget["stage_f_cells"]["cells"]
    assert {c["question"] for c in cells} == {1, 2, 3, 4, 5}
    assert {c["condition"] for c in cells} == {"human", "enriched", "demographics-only"}
    assert {c["length_tercile"] for c in cells} == {1, 2, 3}
    assert budget["stage_f_cells"]["n_cells"] == 45


def test_costs_are_reported_per_provider(budget):
    assert budget["by_model"]["claude"]["calls"] > 0
    assert budget["by_model"]["gemini"]["calls"] > 0
    assert budget["claude_cost_usd"] > 0
    assert budget["gemini_cost_usd"] is None
    assert budget["gemini_cost_status"] == "NOT_CALCULATED_RATE_NOT_VERIFIED"
    c = budget["by_model"]["claude"]
    want = c["input_tokens"] / 1e6 * 2.50 + c["output_tokens"] / 1e6 * 12.50
    assert abs(budget["claude_cost_usd"] - round(want, 2)) < 0.01


def test_totals_reconcile_with_the_stage_table(budget):
    t = budget["totals"]
    assert t["calls"] == sum(s["calls"] for s in budget["stages"])
    assert t["input_tokens"] == sum(s["input_tokens"] for s in budget["stages"])
    assert t["output_tokens"] == sum(s["output_tokens"] for s in budget["stages"])
    assert t["calls"] == sum(v["calls"] for v in budget["by_model"].values())


def test_context_headroom_is_reported_and_ample(budget):
    assert budget["largest_prompt_tokens"] > 0
    assert budget["context_headroom_vs_200k"] > 0.5


def test_stage_d_stays_with_claude_and_is_not_handed_to_a_human(budget):
    d = next(s for s in budget["stages"] if s["stage"].startswith("D_"))
    assert d["model"] == "claude"
    assert d["calls"] > 0


def test_analysis_is_renamed(budget):
    assert budget["analysis"] == "LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION"


# ------------------------------------- Q4 invariants still hold in v3
def test_q4_still_uses_24_orderings_and_excludes_fg5(inventory):
    q4 = inventory["per_question"].get(4) or inventory["per_question"]["4"]
    assert q4["n_orderings"] == 24
    assert q4["n_fgs"] == 4
    assert "fg5" not in q4["fgs_in_scope"]
    assert q4["n_units_in_curve"] == 28
    assert q4["n_units_extracted_but_excluded_from_curve"] == 6
    for u in inventory["units"]:
        if u["question"] == 4 and u["condition"] == "human":
            assert u["fg"] != "fg5"


def test_stage_f_human_q4_cells_cannot_draw_from_fg5(inventory, budget):
    """Stage F samples units; no human Q4 unit exists for FG5, so none can be drawn."""
    human_q4 = [u for u in inventory["units"]
                if u["question"] == 4 and u["condition"] == "human"]
    assert human_q4 and all(u["fg"] in ("fg1", "fg2", "fg3", "fg4") for u in human_q4)
    assert any(c["question"] == 4 and c["condition"] == "human"
               for c in budget["stage_f_cells"]["cells"])
