"""
Offline design tests for RETROSPECTIVE_INDUCTIVE_THEMATIC_ACCUMULATION_ANALYSIS.

No API call. These verify the design's factual claims and its mechanisms before any
execution is approved:

  * the universe is 174 question x document units, not 175;
  * Q4 curves are restricted to four focus groups with 24 orderings;
  * the 30 synthetic paths come from the frozen manifest, not a run0[1-3] glob;
  * the deductive codebook cannot reach a prompt, and the gate is not vacuous;
  * cluster alignment works and never relies on cluster_id equality;
  * the empty output tables carry the corrected shape.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_inventory as inv        # noqa: E402
import inductive_alignment as al         # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_DESIGN = _PE / "final/RETROSPECTIVE_INDUCTIVE_ACCUMULATION_DESIGN.md"


@pytest.fixture(scope="module")
def inventory():
    return inv.build()


# ------------------------------------------------------------ 1. inventory
def test_universe_is_174_units_not_175(inventory):
    assert inventory["n_units"] == 174
    assert inventory["n_units_expected"] == 174
    assert inventory["n_documents"] == 35
    assert inventory["pass"] is True, inventory["problems"]


def test_human_fg5_has_no_question_4(inventory):
    """Verified from the transcript AND cross-checked against the sealed audit."""
    assert inv.human_questions("fg5") == [1, 2, 3, 5]
    assert inv.audit_questions()[("human", "fg5")] == [1, 2, 3, 5]
    for fg in ("fg1", "fg2", "fg3", "fg4"):
        assert inv.human_questions(fg) == [1, 2, 3, 4, 5], fg
    h = inventory["human_fg5"]
    assert h["question_4"] == "NOT ASKED IN FIELDWORK"
    assert "never thematic absence" in h["interpretation_rule"].lower()


def test_missing_section_is_never_read_as_thematic_absence(inventory):
    units = [u for u in inventory["units"]
             if u["condition"] == "human" and u["fg"] == "fg5"]
    assert sorted(u["question"] for u in units) == [1, 2, 3, 5]
    assert not any(u["question"] == 4 for u in units)


def test_q4_is_restricted_to_four_fgs_with_24_orderings(inventory):
    q4 = inventory["per_question"][4] if 4 in inventory["per_question"] \
        else inventory["per_question"]["4"]
    assert q4["fgs_in_scope"] == ["fg1", "fg2", "fg3", "fg4"]
    assert q4["n_fgs"] == 4
    assert q4["n_orderings"] == 24
    assert q4["n_units_in_curve"] == 28          # 4 human + 12 + 12
    assert q4["n_units_in_universe"] == 34       # synthetic FG5 Q4 exists
    assert q4["n_units_extracted_but_excluded_from_curve"] == 6
    assert q4["restricted"] is True
    assert "symmetric" in q4["restriction_reason"]


def test_other_questions_use_five_fgs_and_120_orderings(inventory):
    for q in (1, 2, 3, 5):
        v = inventory["per_question"].get(q) or inventory["per_question"][str(q)]
        assert v["n_fgs"] == 5, q
        assert v["n_orderings"] == 120, q
        assert v["n_units_in_curve"] == 35, q
        assert v["restricted"] is False, q


def test_unit_totals_reconcile(inventory):
    per_q = inventory["per_question"]
    tot = sum((per_q.get(q) or per_q[str(q)])["n_units_in_universe"] for q in (1, 2, 3, 4, 5))
    assert tot == inventory["n_units"] == 174


# ------------------------------------------------------- 2. canonical paths
def test_synthetic_paths_come_from_the_frozen_manifest():
    syn = inv.canonical_synthetic()
    assert len(syn) == 30
    for r in syn:
        assert r["path"], r
        assert r["sha256"], r
        assert r["canonical_replication_index"] in (1, 2, 3), r


def test_a_run01_to_run03_glob_would_build_a_different_corpus(inventory):
    """
    The canonical set includes fg4_run04 and fg5_run04 and excludes fg4_run02 /
    fg5_run02. Reconstructing by pattern silently substitutes the corpus.
    """
    assert inventory["canonical_only_not_in_run01_03_glob"] == [
        "macho_meals_fg4_run04", "macho_meals_fg5_run04"]
    assert inventory["glob_would_have_included_but_is_not_canonical"] == [
        "macho_meals_fg4_run02", "macho_meals_fg5_run02"]
    assert inventory["synthetic_not_reconstructed_by_glob"] is True


def test_every_cell_has_exactly_three_canonical_replicates():
    from collections import defaultdict
    per = defaultdict(list)
    for r in inv.canonical_synthetic():
        per[(r["condition"], r["fg"])].append(r["canonical_replication_index"])
    assert len(per) == 10
    for k, v in per.items():
        assert sorted(v) == [1, 2, 3], k


def test_canonical_paths_exist_on_disk():
    for r in inv.canonical_synthetic():
        p = _ROOT / r["path"] if not Path(r["path"]).is_absolute() else Path(r["path"])
        assert p.exists(), r["path"]


# ------------------------------------------------- 3. codebook cannot leak
def test_codebook_terms_are_loaded():
    t = al.codebook_terms()
    assert len(t["subtheme_ids"]) == 11
    assert "A.1" in t["subtheme_ids"] and "D" in t["subtheme_ids"]
    assert len(t["descriptions"]) == 11


def test_a_clean_prompt_passes_the_gate():
    scaffold = ("You will read one segment of a group discussion and identify the "
                "themes present. Return a label, a one-sentence definition, and one "
                "verbatim supporting quotation with its turn id and speaker.")
    transcript = "[T4] P2: I just eat whatever is quick after work, honestly."
    assert al.codebook_leak_problems(scaffold, transcript) == []


@pytest.mark.parametrize("planted", [
    "Use subtheme A.1 as a guide.",
    "Consider the theme A) Gender does(n't) matter.",
    "Refer to codebook_reference.csv before answering.",
    "Apply the codebook supplied by the researchers.",
])
def test_the_gate_fires_on_each_planted_leak(planted):
    """Non-vacuous by demonstration, not by assertion."""
    assert al.codebook_leak_problems(planted, "") != [], planted


def test_every_codebook_artefact_class_is_detected():
    t = al.codebook_terms()
    for s in (t["subtheme_ids"][0], t["subtheme_labels"][0], t["themes"][0],
              t["filenames"][0]):
        assert al.codebook_leak_problems(f"prefix {s} suffix", "") != [], s
    long_desc = next(d for d in t["descriptions"] if len(d) > 20)
    assert al.codebook_leak_problems(f"note: {long_desc}", "") != []


def test_participant_speech_is_not_flagged_for_ordinary_codebook_words():
    """
    The codebook contains words like 'natural' and 'animal'. Participants use them.
    Flagging the transcript for those would force redaction of the data being coded —
    the 'macho' false positive, repeated.
    """
    transcript = ("[T9] P1: it's just natural to eat animal products, that's normal "
                  "where I'm from, nothing to do with gender")
    assert al.codebook_leak_problems("Identify the themes present.", transcript) == []


def test_structural_identifiers_are_still_caught_inside_the_transcript():
    assert al.codebook_leak_problems("Identify themes.", "[T1] P1: see A.1 above") != []


# --------------------------------------------------- 4. cluster alignment
def test_stability_detects_agreement_and_disagreement():
    passes = {
        "construction": {"r1": "c1", "r2": "c2", "r3": "c1"},
        "audit_a":      {"r1": "c1", "r2": "c2", "r3": "c2"},
        "audit_b":      {"r1": "c1", "r2": "c2", "r3": "c1"},
    }
    s = al.assignment_stability(passes)
    assert s["n_themes"] == 3 and s["n_passes"] == 3
    assert s["per_theme"]["r1"]["stable"] is True
    assert s["per_theme"]["r2"]["stable"] is True
    assert s["per_theme"]["r3"]["stable"] is False
    assert s["unstable_theme_ids"] == ["r3"]
    assert s["stability_rate"] == round(2 / 3, 4)


def test_uncertain_is_never_counted_as_stable():
    passes = {"a": {"r1": al.UNCERTAIN}, "b": {"r1": al.UNCERTAIN}}
    s = al.assignment_stability(passes)
    assert s["per_theme"]["r1"]["stable"] is False
    assert s["per_theme"]["r1"]["any_uncertain"] is True


def test_a_missing_assignment_is_not_stable():
    passes = {"a": {"r1": "c1", "r2": "c1"}, "b": {"r1": "c1"}}
    s = al.assignment_stability(passes)
    assert s["per_theme"]["r2"]["any_missing"] is True
    assert s["per_theme"]["r2"]["stable"] is False


def test_coassignment_alignment_is_label_invariant():
    """Identical partitions under different cluster names must align perfectly."""
    a = {"r1": "c1", "r2": "c1", "r3": "c2", "r4": "c2"}
    b = {"r1": "zeta", "r2": "zeta", "r3": "alpha", "r4": "alpha"}
    out = al.coassignment_alignment(a, b)
    assert out["pair_jaccard"] == 1.0
    assert out["disagreeing_pairs"] == []
    assert out["greedy_one_to_one"]["c1"]["maps_to"] == "zeta"
    assert out["greedy_one_to_one"]["c2"]["maps_to"] == "alpha"


def test_coassignment_alignment_detects_a_real_disagreement():
    a = {"r1": "c1", "r2": "c1", "r3": "c2"}
    b = {"r1": "x", "r2": "y", "r3": "y"}
    out = al.coassignment_alignment(a, b)
    assert out["pair_jaccard"] < 1.0
    assert ("r1", "r2") in out["disagreeing_pairs"]
    assert ("r2", "r3") in out["disagreeing_pairs"]


def test_id_equality_alone_would_have_been_wrong():
    """
    Demonstrates why the fallback exists: two identical partitions under permuted names
    agree on zero ids but on every pair.
    """
    a = {"r1": "c1", "r2": "c1", "r3": "c2"}
    b = {"r1": "c2", "r2": "c2", "r3": "c1"}
    naive = sum(1 for k in a if a[k] == b[k])
    assert naive == 0
    assert al.coassignment_alignment(a, b)["pair_jaccard"] == 1.0


def test_canonical_order_is_deterministic_and_content_based():
    themes = [{"label": "b", "definition": "second"},
              {"label": "a", "definition": "first"},
              {"label": "c", "definition": "third"}]
    o1 = al.canonical_order(themes)
    o2 = al.canonical_order(list(reversed(themes)))
    assert [t["label"] for t in o1] == [t["label"] for t in o2]


# ------------------------------------------------------ 5. design document
def test_design_document_states_the_corrected_universe():
    """175 may appear only where the superseded figure is being named as superseded."""
    t = _DESIGN.read_text(encoding="utf-8")
    assert "174" in t
    for line in t.splitlines():
        if "175" in line:
            assert "174" in line, f"175 stated without the correction: {line}"
    for s in ("frozen_evaluator_inputs.json", "24 orderings",
              "LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION"):
        assert s in t, s
    assert "human FG5 has no Q4" in t


def test_design_document_does_not_claim_symmetric_bias():
    """
    v1 claimed pooled blinding made grouping bias symmetric. The claim must not reappear.
    v4 no longer restates the withdrawal in prose, so the check is that the affirmative
    claim is absent, which is the property that matters.
    """
    t = _DESIGN.read_text(encoding="utf-8")
    for line in t.splitlines():
        if "equally to all three corpora" in line:
            assert "v1 said" in line or "withdraw" in line.lower(), line
    flat = " ".join(t.split()).lower()
    assert "bias symmetric" not in flat
    assert "applies equally" not in flat


def test_design_document_carries_the_corrected_shape():
    """
    v4 reports the corrected shape in prose plus artefacts rather than as empty tables,
    so the check is that every corrected quantity is still stated.
    """
    t = _DESIGN.read_text(encoding="utf-8")
    low = t.lower()
    assert "4 FGs" in t and "24 orderings" in t
    assert "BALANCED_TAXONOMY_EXTENDED_V1" in t
    assert "strict" in low and "extended" in low and "uncertain" in low
    assert "extractor" in low and "instability" in low
    assert "PLANNING_ESTIMATE_V3_SUPERSEDED" in t
    assert "PHASE_A_MANIFEST" in t and "POST_C_STAGE_D_MANIFEST" in t
    assert "nearest-neighbour" in low
    # The design document previously had to say boundaries were NOT resolved, because
    # the segmentation gate was open. Codex has since closed it, so that prose is
    # legitimately gone. The substantive property is unchanged and is now asserted where
    # it actually lives — the artefact — instead of against wording that has moved on.
    assert "position is never used as a fallback" in low
    import json as _json
    seg = _json.loads(
        (_ROOT / "analysis/production_evaluation/final/inductive_segments.json")
        .read_text(encoding="utf-8"))
    assert seg["boundary_ambiguity"]["resolved_silently"] is False
    assert seg["unresolved_runs"]["n"] == 0


# ------------------------------------------------- no write side effects
def test_build_is_pure_and_writes_nothing(tmp_path):
    """
    build() used to persist as a side effect, so running the suite rewrote
    final/inductive_inventory.json — a frozen artefact of work still at NO-GO.
    """
    import hashlib
    frozen = _ROOT / "analysis/production_evaluation/final/inductive_inventory.json"
    before = hashlib.sha256(frozen.read_bytes()).hexdigest()
    inv.build()
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == before


def test_write_targets_tmp_path_when_asked(tmp_path):
    out = tmp_path / "inventory.json"
    written = inv.write(inv.build(), out)
    assert written == out and out.exists()
    import json as _json
    assert _json.loads(out.read_text(encoding="utf-8"))["n_units"] == 174


def test_write_defaults_to_the_project_path_but_is_never_called_by_tests():
    import inspect
    src = inspect.getsource(inv.build)
    assert "write_text" not in src and "os.replace" not in src
