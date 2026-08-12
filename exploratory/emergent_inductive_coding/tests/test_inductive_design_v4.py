"""
Design-v4 offline tests: real per-question segmentation, NEW_CLUSTER resolution (E3),
and a phased budget whose Stage D is not derived from an assumed share.

No API call. Complements the v1/v3 design test files.
"""
from __future__ import annotations

import sys
import hashlib
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_alignment as al     # noqa: E402
import inductive_budget as bud       # noqa: E402
import inductive_segments as seg     # noqa: E402


@pytest.fixture(scope="module")
def segments():
    return seg.build()


@pytest.fixture(scope="module")
def budget():
    return bud.plan()


# ======================== real segmentation ===============================
def test_question_lengths_are_not_a_document_divided_by_five(segments):
    """
    The v3 defect: length estimated as document_words / n_questions. Guide questions
    attract very different amounts of discussion, so an even split misstates every
    length-dependent quantity downstream.
    """
    per_q = segments["per_question"]
    means = [v["mean_words"] for v in per_q.values()]
    even = segments["even_split_would_have_said"]
    assert segments["estimated_by_even_split"] is False
    assert max(means) / min(means) > 2.0, means
    assert not all(abs(m - even) < 50 for m in means), means


def test_segments_reconcile_with_their_source_documents(segments):
    assert segments["all_documents_reconcile"] is True
    for d in segments["document_reconciliation"]:
        assert d["segment_sum"] == d["document_total"], d["document"]
    assert len(segments["document_reconciliation"]) == 35
    assert segments["n_segments"] == 174
    assert segments["pass"] is True, segments["problems"]


def test_every_segment_carries_full_provenance(segments):
    for s in segments["segments"]:
        for k in ("unit_id", "question", "condition", "fg", "source_sha256",
                  "section_sha256", "turns", "participant_words", "moderator_words",
                  "total_words", "boundary_provenance", "length_tercile"):
            assert k in s, (s.get("unit_id"), k)
        assert s["participant_words"] + s["moderator_words"] == s["total_words"]
        assert s["length_tercile"] in (1, 2, 3)


def test_former_boundary_ambiguity_is_resolved_by_binding_anchors(segments):
    """The two researcher-reviewed cases reproduce their binding boundaries."""
    amb = segments["boundary_ambiguity"]
    assert amb["resolved_silently"] is False
    assert amb["n_runs_affected"] == 0
    assert amb["cases"] == []
    by_run = {}
    for row in segments["segments"]:
        if row["physical_run"]:
            by_run.setdefault(row["physical_run"], []).append(
                (row["question"], row["boundary_provenance"]["opens_at_turn"],
                 row["boundary_provenance"]["closes_before_turn"]))
    assert by_run["macho_meals_fg1_demoonly_run01"] == [
        (1, 0, 9), (2, 9, 19), (3, 19, 34), (4, 34, 46), (5, 46, 52)]
    assert by_run["macho_meals_fg4_demoonly_run01"] == [
        (1, 0, 6), (2, 6, 15), (3, 15, 20), (4, 20, 24), (5, 24, 28)]


def test_synthetic_segmentation_uses_the_window_not_the_full_transcript(segments):
    for s in segments["segments"]:
        if s["condition"] == "human":
            continue
        assert "comparable_transcripts" in s["source_path"]
        assert "full transcript never used" in s["boundary_provenance"]["window"]


def test_no_api_call_and_session_logs_are_read_only(segments):
    assert segments["no_api_calls"] is True
    assert "READ ONLY" in segments["session_logs_access"]


def test_segment_and_budget_builders_do_not_write_frozen_outputs():
    paths = [seg._OUT, bud._OUT]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    seg.build()
    bud.plan()
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert after == before


def test_length_terciles_come_from_real_counts(segments):
    by = defaultdict(list)
    for s in segments["segments"]:
        by[(s["question"], s["condition"])].append(s)
    for cell, items in by.items():
        t1 = [x["total_words"] for x in items if x["length_tercile"] == 1]
        t3 = [x["total_words"] for x in items if x["length_tercile"] == 3]
        if t1 and t3:
            assert max(t1) <= min(t3), cell


def test_q4_still_four_fgs_and_fg5_excluded(segments):
    q4 = [s for s in segments["segments"] if s["question"] == 4]
    assert len(q4) == 34
    human_q4 = [s for s in q4 if s["condition"] == "human"]
    assert len(human_q4) == 4
    assert all(s["fg"] != "fg5" for s in human_q4)


# ========================= NEW_CLUSTER / E3 ================================
def _tax():
    t = [{"cluster_id": "c1", "label": "one", "definition": "d1"},
         {"cluster_id": "c2", "label": "two", "definition": "d2"}]
    return t, al.frozen_taxonomy_key(t)


def test_e1_is_hash_identical_after_e3():
    tax, key = _tax()
    a = {"t1": "c1", "t2": al.NEW_CLUSTER, "t3": al.NEW_CLUSTER, "t4": al.UNCERTAIN}
    e3 = al.consolidate_new_clusters(tax, key, a, [["t2", "t3"]])
    assert al.frozen_taxonomy_key(tax) == key
    assert e3["parent_taxonomy_sha256"] == key
    assert e3["e1_unchanged"] is True
    assert e3["extended_taxonomy_sha256"] != key
    assert e3["version"] == "BALANCED_TAXONOMY_EXTENDED_V1"


def test_two_equivalent_new_clusters_consolidate_into_one():
    tax, key = _tax()
    a = {"t2": al.NEW_CLUSTER, "t3": al.NEW_CLUSTER}
    e3 = al.consolidate_new_clusters(tax, key, a, [["t2", "t3"]])
    assert e3["counts"]["n_new_cluster_raw_themes"] == 2
    assert e3["counts"]["n_consolidated_extended_clusters"] == 1
    assert e3["counts"]["collapsed"] == 1
    ext = [c for c in e3["extended_taxonomy"] if c.get("origin") == "E3"]
    assert len(ext) == 1 and ext[0]["n_raw_themes"] == 2


def test_new_cluster_is_not_automatically_a_distinct_cluster():
    tax, key = _tax()
    a = {"t2": al.NEW_CLUSTER, "t3": al.NEW_CLUSTER, "t4": al.NEW_CLUSTER}
    one = al.consolidate_new_clusters(tax, key, a, [["t2", "t3", "t4"]])
    sep = al.consolidate_new_clusters(tax, key, a, [["t2"], ["t3"], ["t4"]])
    assert one["counts"]["n_consolidated_extended_clusters"] == 1
    assert sep["counts"]["n_consolidated_extended_clusters"] == 3
    assert one["never_auto_one_cluster_per_new"] is True
    assert one["counts"]["n_new_cluster_raw_themes"] == 3


def test_e3_rejects_an_ungrouped_or_double_grouped_new_cluster():
    tax, key = _tax()
    a = {"t2": al.NEW_CLUSTER, "t3": al.NEW_CLUSTER}
    assert not al.consolidate_new_clusters(tax, key, a, [["t2"]])["pass"]
    assert not al.consolidate_new_clusters(tax, key, a,
                                           [["t2", "t3"], ["t3"]])["pass"]


def test_e3_refuses_a_revised_e1():
    tax, key = _tax()
    with pytest.raises(ValueError):
        al.consolidate_new_clusters(
            tax + [{"cluster_id": "cX", "label": "x", "definition": "y"}],
            key, {"t2": al.NEW_CLUSTER}, [["t2"]])


def test_uncertain_is_never_folded_into_an_extended_cluster():
    tax, key = _tax()
    a = {"t2": al.NEW_CLUSTER, "t4": al.UNCERTAIN}
    bad = al.consolidate_new_clusters(tax, key, a, [["t2", "t4"]])
    assert not bad["pass"]
    assert any("UNCERTAIN" in p for p in bad["problems"])


def test_strict_and_extended_curves_stay_separate():
    tax, key = _tax()
    a = {"t1": "c1", "t2": al.NEW_CLUSTER, "t3": al.NEW_CLUSTER, "t4": al.UNCERTAIN}
    e3 = al.consolidate_new_clusters(tax, key, a, [["t2", "t3"]])
    d = al.curve_denominators(a, e3)
    assert d["strict_vs_E1"]["n_clusters_available"] == 2
    assert d["extended"]["n_clusters_available"] == 3
    assert d["strict_vs_E1"]["n_raw_themes_counted"] == 1
    assert d["extended"]["n_raw_themes_counted"] == 3
    assert "strict_vs_E1" in e3["curves_reported_separately"]


def test_uncertain_and_new_cluster_are_shown_not_dropped():
    tax, key = _tax()
    a = {"t1": "c1", "t2": al.NEW_CLUSTER, "t4": al.UNCERTAIN}
    e3 = al.consolidate_new_clusters(tax, key, a, [["t2"]])
    d = al.curve_denominators(a, e3)
    assert d["strict_vs_E1"]["excluded_new_cluster"] == 1
    assert d["strict_vs_E1"]["excluded_uncertain"] == 1
    assert d["extended"]["excluded_uncertain"] == 1
    assert d["uncertain_never_silently_dropped"] is True
    assert e3["counts"]["uncertain_raw_theme_ids"] == ["t4"]


def test_stage_f_new_clusters_do_not_alter_the_canonical_taxonomy():
    """A pass-2 NEW_CLUSTER must not extend the taxonomy the pass-1 curves used."""
    assert al.stage_f_assignment_problems(
        [{"pass2_theme_id": "p1", "verdict": al.NEW_CLUSTER,
          "decided_by": "adjudicator"}]) == []
    assert al.stage_f_assignment_problems(
        [{"pass2_theme_id": "p2", "verdict": al.NEW_CLUSTER,
          "canonical_cluster_id": "c1", "decided_by": "adjudicator"}]) != []


# ========================== phased budget =================================
def test_budget_is_labelled_a_planning_estimate(budget):
    assert budget["budget_class"] == "PLANNING_ESTIMATE"


def test_phase_a_is_exact_and_later_phases_are_deferred(budget):
    ph = budget["phased_budget"]
    assert ph["PHASE_A_MANIFEST"]["status"] == "EXACT"
    assert ph["PHASE_A_MANIFEST"]["calls"] == 174
    assert ph["POST_A_REPLAN"]["status"] == "DEFERRED"
    assert ph["POST_C_STAGE_D_MANIFEST"]["status"] == "DEFERRED"
    assert "E3" in ph["POST_A_REPLAN"]["recomputes"]


def test_stage_d_is_derived_from_observed_cases_not_a_share(budget):
    ph = budget["phased_budget"]["POST_C_STAGE_D_MANIFEST"]
    assert "OBSERVED" in ph["why"] or "observed" in ph["why"]
    assert "hypothesis" in ph["why"] or "never a measurement" in ph["why"]
    sc = budget["stage_d_scenarios"]
    assert set(sc) == {"5pct", "15pct", "30pct"}
    assert (sc["5pct"]["claude_calls"] < sc["15pct"]["claude_calls"]
            < sc["30pct"]["claude_calls"])
    assert sc["5pct"]["claude_cost_usd"] < sc["30pct"]["claude_cost_usd"]
    assert budget["planning_assumptions"]["unstable_share_PLANNING_ONLY"] == 0.15


def test_e3_is_budgeted(budget):
    e3 = next(s for s in budget["stages"] if s["stage"].startswith("E3"))
    assert e3["calls"] > 0 and e3["input_tokens"] > 0
    assert "never overwritten" in e3["derivation"]


def test_budget_uses_real_segment_lengths(budget):
    s = budget["segmentation"]
    assert s["estimated_by_even_split"] is False
    assert s["all_documents_reconcile"] is True
    means = list(s["real_per_question_mean_words"].values())
    assert max(means) / min(means) > 2.0, means


def test_stage_f_units_are_real_units_with_real_lengths(budget):
    cells = budget["stage_f_cells"]["cells"]
    assert len(cells) == 45
    for c in cells:
        assert c["unit_id"] and c["total_words"] > 0
    assert len({c["unit_id"] for c in cells}) == 45
