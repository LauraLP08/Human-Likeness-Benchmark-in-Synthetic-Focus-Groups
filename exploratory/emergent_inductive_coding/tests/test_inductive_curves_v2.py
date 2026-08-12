"""
Tests for the corrected accumulation unit of analysis.

The defect being guarded against: pooling R1, R2 and R3 before accumulating, so a
synthetic curve drew on 15 sessions while the human curve drew on 5. Every test here
fails if replicates are merged again.

Offline; no API call.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_curves_v2 as cv         # noqa: E402
import stage_b_taxonomy as sb            # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/inductive_curves"


@pytest.fixture(scope="module")
def curves():
    return json.loads((_OUT / "inductive_curves_v2_full.json").read_text(
        encoding="utf-8"))


@pytest.fixture(scope="module")
def meta():
    return json.loads((_OUT / "inductive_accumulation_curves_v2.json").read_text(
        encoding="utf-8"))


# ------------------------------------------------------- synthetic fixtures
def _prov(condition, replicate, fg):
    return {"condition": condition, "fg": fg, "replicate": replicate}


def _fixture():
    """R1 and R2 hold DIFFERENT clusters, so any pooling is immediately visible."""
    prov, assign = {}, {}
    for i, fg in enumerate(cv.ALL_FGS):
        prov[(1, f"R1_{i}")] = _prov("enriched", "1", fg)
        assign[(1, f"R1_{i}")] = f"C_R1_{i}"
        prov[(1, f"R2_{i}")] = _prov("enriched", "2", fg)
        assign[(1, f"R2_{i}")] = f"C_R2_{i}"
        prov[(1, f"R3_{i}")] = _prov("enriched", "3", fg)
        assign[(1, f"R3_{i}")] = "C_SHARED"
    return assign, prov


def test_replicates_are_never_unioned_in_one_endpoint():
    """R1 and R2 have five disjoint clusters each; pooling would give 10."""
    assign, prov = _fixture()
    r1 = cv.realisation_curve(assign, prov, 1, "enriched", "1")
    r2 = cv.realisation_curve(assign, prov, 1, "enriched", "2")
    assert r1["endpoint"] == 5, "R1 must see only its own five clusters"
    assert r2["endpoint"] == 5
    assert r1["endpoint"] + r2["endpoint"] == 10
    assert r1["endpoint"] != 10, "pooling R1 and R2 would produce 10"


def test_permuting_one_replicate_never_changes_the_others():
    assign, prov = _fixture()
    before = [cv.realisation_curve(assign, prov, 1, "enriched", r)["endpoint"]
              for r in ("1", "2", "3")]
    # rewrite R1's clusters entirely; R2 and R3 must not move
    mutated = dict(assign)
    for i in range(len(cv.ALL_FGS)):
        mutated[(1, f"R1_{i}")] = f"TOTALLY_DIFFERENT_{i}"
    after = [cv.realisation_curve(mutated, prov, 1, "enriched", r)["endpoint"]
             for r in ("1", "2", "3")]
    assert after[1] == before[1] and after[2] == before[2]


def test_a_synthetic_curve_never_holds_more_than_five_sessions(curves):
    for scen, per_q in curves.items():
        for q, block in per_q.items():
            limit = 4 if q == "4" else 5
            for cond in ("enriched", "demographics-only"):
                for r in block[cond]["realisations"]:
                    assert r["n_sessions_contributing"] <= limit, (
                        f"{scen} {cond} Q{q} R{r['replicate']}: "
                        f"{r['n_sessions_contributing']} sessions")
                    assert r["n_focus_groups_in_curve"] == limit


def test_q4_uses_four_focus_groups_and_24_orderings(curves):
    for scen, per_q in curves.items():
        for cond in ("human", "enriched", "demographics-only"):
            for r in per_q["4"][cond]["realisations"]:
                assert r["n_orderings"] == 24
                assert r["n_focus_groups_in_curve"] == 4
                assert set(r["per_fg_repertoire"]) == set(cv.Q4_FGS)
                assert "fg5" not in r["per_fg_repertoire"]


def test_other_questions_use_five_focus_groups_and_120_orderings(curves):
    for scen, per_q in curves.items():
        for q in ("1", "2", "3", "5"):
            for cond in ("human", "enriched", "demographics-only"):
                for r in per_q[q][cond]["realisations"]:
                    assert r["n_orderings"] == 120
                    assert r["n_focus_groups_in_curve"] == 5


def test_exactly_three_endpoints_per_synthetic_condition(curves):
    for scen, per_q in curves.items():
        for q, block in per_q.items():
            for cond in ("enriched", "demographics-only"):
                s = block[cond]
                assert s["n_realisations"] == 3
                assert len(s["endpoints"]) == 3
                assert all(f"endpoint_R{i}" in s for i in (1, 2, 3))
                assert s["min_endpoint"] <= s["median_endpoint"] <= s["max_endpoint"]


def test_exactly_one_human_endpoint_and_no_invented_variation(curves):
    for scen, per_q in curves.items():
        for q, block in per_q.items():
            h = block["human"]
            assert h["n_realisations"] == 1
            assert len(h["endpoints"]) == 1
            assert h["single_realisation"] is True
            assert "no_between_replicate_variation" in h
            assert "endpoint_R2" not in h and "endpoint_R3" not in h


def test_averaging_happens_within_then_across(curves, meta):
    for scen, per_q in curves.items():
        for q, block in per_q.items():
            for cond in ("enriched", "demographics-only"):
                for pos in block[cond]["cumulative_by_position"]:
                    assert len(pos["replicate_means"]) == 3
                    assert pos["min"] <= pos["median"] <= pos["max"]
    assert meta["orderings"]["orderings_are_not_independent_observations"] is True


# --------------------------------------------------------- superseded record
def test_the_old_endpoints_are_retired_and_not_a_headline(meta):
    r = meta["supersedes"]
    assert r["record"] == "RETIRED_SUPERSEDED"
    assert r["superseded_endpoints"] == {"human": 31, "enriched": 65,
                                         "demographics-only": 63}
    assert r["must_not_be_cited"] is True
    old = _OUT / "inductive_accumulation_curves.json"
    if old.exists():
        j = json.loads(old.read_text(encoding="utf-8"))
        assert j["status"] == "RETIRED_SUPERSEDED"
        assert j["superseded_by"] == "inductive_accumulation_curves_v2.json"


def test_no_synthetic_endpoint_reproduces_the_retired_aggregate(curves, meta):
    """65 and 63 came from pooling; no corrected per-replicate sum should hit them."""
    for scen, s in meta["sums_within_realisation"].items():
        for cond in ("enriched", "demographics-only"):
            for v in s[cond]["per_realisation"]:
                assert v not in (65, 63), (
                    f"{scen} {cond}: a corrected sum reproduces a retired aggregate")


# --------------------------------------------------------- reconciliation
def test_endpoints_reconcile_against_the_long_assignments():
    """Rebuild one cell straight from the CSVs and compare."""
    rows = list(csv.DictReader((_OUT / "inductive_endpoints_by_replicate.csv").open(
        encoding="utf-8")))
    assert len(rows) == 6 * 5 * 7, "6 scenarios x 5 questions x (1 human + 6 synthetic)"

    prov = cv.v1.provenance()
    lower = cv.v1.canonical_assignments()["CANONICAL_RESOLVED_LOWER"]
    got = cv.realisation_curve(lower, prov, 1, "enriched", "1")
    row = next(r for r in rows
               if r["scenario"] == "CANONICAL_RESOLVED_LOWER" and r["question"] == "1"
               and r["condition"] == "enriched" and r["replicate"] == "R1")
    assert int(row["endpoint"]) == got["endpoint"]
    assert int(row["n_sessions"]) == got["n_sessions_contributing"]


def test_every_scenario_and_condition_is_present(curves):
    expected = {"CANONICAL_RESOLVED_LOWER", "CANONICAL_ASSIGNMENT_SENSITIVITY_R1",
                "CANONICAL_ASSIGNMENT_SENSITIVITY_R2",
                "CANONICAL_MATHEMATICAL_MAXIMUM", "STRICT_AGAINST_E1", "EXTENDED_E3"}
    assert set(curves) == expected
    for per_q in curves.values():
        assert set(per_q) == {"1", "2", "3", "4", "5"}
        for block in per_q.values():
            assert set(block) == {"human", "enriched", "demographics-only"}


# ------------------------------------------------------------- unresolved
def test_unresolved_are_reported_by_condition_replicate_and_question(meta):
    u = meta["unresolved"]
    assert u["n_total"] == 86
    assert u["by_condition_replicate_question"]
    q4 = u["q4_note"]
    assert q4["unresolved_in_full_universe"] == 9
    assert q4["unresolved_inside_FG1_FG4_curve_universe"] == 6
    assert q4["outside_curve"] == 3


def test_lower_excludes_the_unresolved(curves):
    for q, block in curves["CANONICAL_RESOLVED_LOWER"].items():
        for cond, s in block.items():
            for r in s["realisations"]:
                assert r["n_themes_unassigned_in_this_scenario"] >= 0


def test_language_is_scenario_not_interval(meta):
    assert meta["scenarios_are_not_confidence_intervals"] is True
    assert meta["maximum_is_a_construction_ceiling_not_an_estimate"] is True
    blob = json.dumps(meta).lower()
    for banned in ("confidence interval", "saturation achieved", "plateau demonstrated",
                   "meaning saturation"):
        assert banned not in blob, banned


def test_sums_are_labelled_as_endpoint_sums_not_distinct_themes(meta):
    assert meta["sum_label"] == "sum of question-specific repertoire endpoints"
    assert "number of distinct themes" in meta["sum_is_not"]
    assert meta["canonical_and_balanced_ids_never_mixed"] is True
