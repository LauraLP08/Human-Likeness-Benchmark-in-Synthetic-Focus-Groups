"""
Narrative reconciliation against the authoritative CSV.

Every figure that appears in prose or in a table must be derivable from
`inductive_endpoints_by_replicate.csv`. This exists because a previous narrative reported
canonical endpoint sums that the artefacts never contained: the artefacts were correct
and the write-up was not. A number nobody can recompute is a number nobody should cite.

Offline; no API call.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_curves_v2 as cv          # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/inductive_curves"
_CSV = _OUT / "inductive_endpoints_by_replicate.csv"

# The figures the narrative is allowed to state, as sums of per-question endpoints
# within one study realisation.
NARRATIVE = {
    "CANONICAL_RESOLVED_LOWER": {
        "human": [31], "enriched": [31, 40, 38],
        "demographics-only": [42, 36, 35]},
    "CANONICAL_ASSIGNMENT_SENSITIVITY_R1": {
        "human": [33], "enriched": [32, 43, 39],
        "demographics-only": [43, 38, 39]},
    "CANONICAL_ASSIGNMENT_SENSITIVITY_R2": {
        "human": [31], "enriched": [32, 41, 38],
        "demographics-only": [42, 36, 36]},
    "CANONICAL_MATHEMATICAL_MAXIMUM": {
        "human": [48], "enriched": [39, 49, 49],
        "demographics-only": [50, 51, 50]},
    "STRICT_AGAINST_E1": {
        "human": [25], "enriched": [20, 22, 23],
        "demographics-only": [22, 18, 19]},
    "EXTENDED_E3": {
        "human": [33], "enriched": [31, 36, 39],
        "demographics-only": [41, 32, 33]},
}

# Values a previous narrative stated that the artefacts never contained.
BANNED = {
    "CANONICAL_RESOLVED_LOWER": {"enriched": [34, 40, 38],
                                 "demographics-only": [43, 38, 39]},
    "CANONICAL_ASSIGNMENT_SENSITIVITY_R1": {"enriched": [35, 42, 40],
                                            "demographics-only": [44, 39, 41]},
}
# The pooled aggregates from the superseded curve module.
BANNED_AGGREGATES = {"human": 31, "enriched": 65, "demographics-only": 63}

FINAL_INCREMENTS = {
    "1": {"human": 1.4, "enriched": 1.2, "demographics-only": 1.4},
    "2": {"human": 0.6, "enriched": 0.6, "demographics-only": 1.2},
    "3": {"human": 0.4, "enriched": 1.0, "demographics-only": 0.8},
    "4": {"human": 0.5, "enriched": 1.25, "demographics-only": 1.0},
    "5": {"human": 0.2, "enriched": 0.8, "demographics-only": 1.2},
}


@pytest.fixture(scope="module")
def csv_sums():
    rows = list(csv.DictReader(_CSV.open(encoding="utf-8")))
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in rows:
        out[r["scenario"]][r["condition"]][r["replicate"]] += int(r["endpoint"])
    res = {}
    for scen, conds in out.items():
        res[scen] = {}
        for cond, reps in conds.items():
            order = ["human"] if cond == "human" else ["R1", "R2", "R3"]
            res[scen][cond] = [reps[k] for k in order]
    return res


@pytest.fixture(scope="module")
def full():
    return json.loads((_OUT / "inductive_curves_v2_full.json").read_text(
        encoding="utf-8"))


# ------------------------------------------------ every narrative figure
def test_every_narrative_endpoint_matches_the_csv(csv_sums):
    for scen, conds in NARRATIVE.items():
        for cond, vals in conds.items():
            assert csv_sums[scen][cond] == vals, (
                f"{scen} / {cond}: narrative {vals}, CSV {csv_sums[scen][cond]}")


def test_every_narrative_median_matches_the_csv(csv_sums):
    for scen, conds in NARRATIVE.items():
        for cond, vals in conds.items():
            assert statistics.median(csv_sums[scen][cond]) == \
                statistics.median(vals)


def test_the_csv_is_the_only_source_needed():
    """The narrative must be reproducible from the CSV alone."""
    rows = list(csv.DictReader(_CSV.open(encoding="utf-8")))
    assert len(rows) == 6 * 5 * 7
    assert {r["scenario"] for r in rows} == set(NARRATIVE)


# ------------------------------------------------------ banned figures
def test_the_previously_reported_canonical_sums_are_rejected(csv_sums):
    """PLANTED: the exact wrong numbers a previous narrative stated."""
    for scen, conds in BANNED.items():
        for cond, wrong in conds.items():
            assert csv_sums[scen][cond] != wrong, (
                f"{scen} / {cond}: the artefacts must not reproduce {wrong}")


def test_the_pooled_aggregates_appear_nowhere(csv_sums):
    for scen, conds in csv_sums.items():
        for cond, vals in conds.items():
            if cond == "human":
                continue
            for v in vals:
                assert v not in (65, 63), (
                    f"{scen}/{cond}: {v} reproduces a pooled aggregate")


def test_banned_aggregates_are_recorded_as_retired():
    meta = json.loads((_OUT / "inductive_accumulation_curves_v2.json").read_text(
        encoding="utf-8"))
    assert meta["supersedes"]["superseded_endpoints"] == BANNED_AGGREGATES
    assert meta["supersedes"]["must_not_be_cited"] is True


# ------------------------------------------- pooling must remain impossible
def test_pooling_replicates_would_change_every_synthetic_sum(csv_sums, full):
    """
    If replicates were pooled the union would be at least the largest single replicate
    and generally larger. This asserts the stored values are per-realisation, not pooled.
    """
    prov = cv.v1.provenance()
    assign = cv.v1.canonical_assignments()["CANONICAL_RESOLVED_LOWER"]
    per_rep = [cv.realisation_curve(assign, prov, 1, "enriched", r)["endpoint"]
               for r in ("1", "2", "3")]
    pooled = set()
    for (q, rid), cl in assign.items():
        if q != 1 or cl is None:
            continue
        p = prov.get((q, rid))
        if p and p["condition"] == "enriched":
            pooled.add(cl)
    assert len(pooled) > max(per_rep), "pooling must inflate the endpoint"
    stored = [int(r["endpoint"]) for r in csv.DictReader(_CSV.open(encoding="utf-8"))
              if r["scenario"] == "CANONICAL_RESOLVED_LOWER" and r["question"] == "1"
              and r["condition"] == "enriched"]
    assert sorted(stored) == sorted(per_rep)
    assert len(pooled) not in stored


def test_no_synthetic_curve_exceeds_its_session_budget(full):
    for scen, per_q in full.items():
        for q, block in per_q.items():
            limit = 4 if q == "4" else 5
            for cond in ("enriched", "demographics-only"):
                for r in block[cond]["realisations"]:
                    assert r["n_sessions_contributing"] <= limit


def test_exactly_three_synthetic_and_one_human_realisation(csv_sums):
    for scen, conds in csv_sums.items():
        assert len(conds["human"]) == 1
        assert len(conds["enriched"]) == 3
        assert len(conds["demographics-only"]) == 3


# ------------------------------------------------ final-position increments
def test_final_position_increments_match_the_curves(full):
    for q, exp in FINAL_INCREMENTS.items():
        b = full["CANONICAL_RESOLVED_LOWER"][q]
        got = {
            "human": b["human"]["realisations"][0]["mean_new_at_position"][-1],
            "enriched": statistics.median(
                r["mean_new_at_position"][-1] for r in b["enriched"]["realisations"]),
            "demographics-only": statistics.median(
                r["mean_new_at_position"][-1]
                for r in b["demographics-only"]["realisations"])}
        for cond, v in exp.items():
            assert round(got[cond], 2) == v, f"Q{q} {cond}: {got[cond]} != {v}"


def test_every_final_increment_is_above_zero(full):
    """The basis for saying accumulation continued at the final position."""
    for q, exp in FINAL_INCREMENTS.items():
        for cond, v in exp.items():
            assert v > 0, f"Q{q} {cond}"


# --------------------------------------------------------------- language
def test_the_figure_caption_makes_the_required_statements():
    # markdown wraps lines; compare on normalised whitespace
    cap = " ".join((_OUT / "figure_caption.md")
                   .read_text(encoding="utf-8").lower().split())
    for required in (
            "not equivalent measures",
            "does not demonstrate saturation achieved",
            "exclude 86 unresolved raw themes",
            "ranges across three study realisations, not confidence intervals"):
        assert required in cap, required
    for banned in ("saturation achieved.", "plateau demonstrated",
                   "meaning saturation was assessed"):
        assert banned not in cap, banned


# ============================================ saturation section (inductive only)
_SAT = _OUT / "SATURATION_SECTION.md"

CUMULATIVE = {
    ("human", 0): (79.4, 91.6),
    ("enriched", 0): (77.7, 91.6), ("enriched", 1): (72.2, 89.0),
    ("enriched", 2): (74.9, 90.0),
    ("demographics-only", 0): (71.0, 87.6), ("demographics-only", 1): (68.8, 85.6),
    ("demographics-only", 2): (72.9, 89.7),
}


def test_cumulative_percentages_reproduce_from_the_curves(full):
    L = full["CANONICAL_RESOLVED_LOWER"]
    for (cond, i), (e3, e4) in CUMULATIVE.items():
        c3 = sum(L[q][cond]["realisations"][i]["mean_cumulative_by_position"][2]
                 for q in "12345")
        c4 = sum(L[q][cond]["realisations"][i]["mean_cumulative_by_position"][3]
                 for q in "12345")
        ep = sum(L[q][cond]["realisations"][i]["endpoint"] for q in "12345")
        assert abs(100 * c3 / ep - e3) < 0.15, f"{cond} R{i+1} 3FG"
        assert abs(100 * c4 / ep - e4) < 0.15, f"{cond} R{i+1} 4FG"


def test_the_saturation_section_states_every_percentage():
    t = _SAT.read_text(encoding="utf-8")
    for (_c, _i), (e3, e4) in CUMULATIVE.items():
        assert f"{e3}%" in t, e3
        assert f"{e4}%" in t, e4


def test_the_saturation_section_carries_the_verified_endpoints():
    t = " ".join(_SAT.read_text(encoding="utf-8").split())
    assert "[31, 40, 38]" in t and "[42, 36, 35]" in t and "[31]" in t


def test_the_saturation_section_has_no_deductive_panel():
    t = " ".join(_SAT.read_text(encoding="utf-8").lower().split())
    assert "a-priori subthemes observed" not in t
    assert "deductive coverage of the fixed a-priori codebook belongs to the " \
           "thematic-fidelity section" in t


def test_forbidden_saturation_language_is_absent():
    t = " ".join(_SAT.read_text(encoding="utf-8").lower().split())
    for banned in ("saturation achieved", "saturation reached",
                   "plateau demonstrated", "sufficient sample size proven"):
        assert banned not in t, banned


def test_the_four_required_conclusions_are_present():
    t = " ".join(_SAT.read_text(encoding="utf-8").lower().split())
    for required in (
            "most of the resolved repertoire was identified by the fourth focus group",
            "themes continued to accumulate at the final focus-group position",
            "code-emergence stabilisation was not established",
            "meaning saturation was not assessed"):
        assert required in t, required


def test_the_four_limitations_stay_visible():
    t = " ".join(_SAT.read_text(encoding="utf-8").lower().split())
    for required in ("440 of 526", "86 unresolved", "36 of 139",
                     "retrospective and llm-assisted",
                     "full taxonomy was not human-validated"):
        assert required in t, required
