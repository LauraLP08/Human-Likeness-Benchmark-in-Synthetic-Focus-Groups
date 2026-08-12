"""
The sign test's ceiling follows n_effective, not n_total.

A tie carries no sign and is dropped. Quoting "n=5, 32 assignments, p_min=0.0625"
for a metric with two ties overstates what the test could ever have detected: on
three effective pairs the floor is 0.25, four times higher. Precision in this corpus
has exactly that shape.

No API calls.
"""

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_primary_effects_tables as eff   # noqa: E402

RESULTS = ROOT / "analysis" / "production_evaluation" / "results"
st = eff.sign_test_two_sided


def test_five_differences_no_ties():
    r = st([0.1, 0.2, 0.3, 0.4, -0.1])
    assert r["n_total_pairs"] == 5
    assert r["n_effective_pairs"] == 5
    assert r["n_ties"] == 0
    assert r["possible_sign_assignments"] == 32
    assert r["minimum_attainable_two_sided_p"] == 0.0625
    assert r["cannot_reach_p05"] is True


def test_three_nonzero_and_two_ties():
    """The precision case: the ceiling must be 0.25, not 0.0625."""
    r = st([0.0, -0.0833, 0.0, 0.4222, 0.05])
    assert r["n_total_pairs"] == 5
    assert r["n_effective_pairs"] == 3
    assert r["n_ties"] == 2
    assert r["possible_sign_assignments"] == 8
    assert r["minimum_attainable_two_sided_p"] == 0.25
    assert r["minimum_attainable_two_sided_p"] != 0.0625, (
        "the n_total ceiling must not be reported for a metric with ties")
    assert r["p_two_sided"] == 1.0
    assert r["cannot_reach_p05"] is True


def test_all_pairs_tied():
    r = st([0.0, 0.0, 0.0, 0.0, 0.0])
    assert r["n_effective_pairs"] == 0
    assert r["n_ties"] == 5
    assert r["p_two_sided"] is None
    assert r["minimum_attainable_two_sided_p"] is None
    assert r["possible_sign_assignments"] == 0
    assert "undefined" in r["caveat"]


def test_p_is_never_above_one():
    for diffs in ([0.1, -0.1], [0.1, -0.1, 0.2, -0.2], [0.1, -0.1, 0.2],
                  [1.0], [0.5, 0.5, -0.5, -0.5, 0.1, -0.1]):
        r = st(diffs)
        if r["p_two_sided"] is not None:
            assert 0.0 <= r["p_two_sided"] <= 1.0, f"{diffs} -> {r['p_two_sided']}"


def test_minimum_p_is_based_on_effective_not_total():
    """Same n_total, different tie counts, therefore different floors."""
    floors = {}
    for ties in range(0, 5):
        diffs = [0.0] * ties + [0.1] * (5 - ties)
        r = st(diffs)
        floors[ties] = r["minimum_attainable_two_sided_p"]
        assert r["n_total_pairs"] == 5
        assert r["n_effective_pairs"] == 5 - ties
        if r["n_effective_pairs"]:
            assert r["possible_sign_assignments"] == 2 ** (5 - ties)
            assert r["minimum_attainable_two_sided_p"] == round(
                2 / 2 ** (5 - ties), 4)
    assert floors[0] == 0.0625 and floors[2] == 0.25
    assert floors[0] < floors[1] < floors[2] < floors[3]


def test_one_effective_pair_can_never_be_significant():
    r = st([0.0, 0.0, 0.0, 0.0, 0.3])
    assert r["n_effective_pairs"] == 1
    assert r["possible_sign_assignments"] == 2
    assert r["minimum_attainable_two_sided_p"] == 1.0
    assert r["cannot_reach_p05"] is True


def test_it_is_labelled_exploratory():
    r = st([0.1, 0.2, 0.3, 0.4, -0.1])
    assert "EXPLORATORY" in r["classification"]
    assert "does not replace the per-FG effects" in r["caveat"]


# ---------------------------------------------------------------------------
# The emitted summary must carry the tie-aware columns
# ---------------------------------------------------------------------------

def test_summary_csv_exposes_tie_aware_columns():
    path = RESULTS / "primary_effects_summary.csv"
    if not path.exists():
        pytest.skip("primary_effects_summary.csv not generated")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    for col in ("n_nonzero_pairs", "n_ties", "possible_sign_assignments",
                "minimum_attainable_p", "sign_test_cannot_reach_p05"):
        assert col in rows[0], f"{col} missing from primary_effects_summary.csv"
    for r in rows:
        n_eff, ties = int(r["n_nonzero_pairs"]), int(r["n_ties"])
        assert n_eff + ties == int(r["n_fgs"])
        assert int(r["possible_sign_assignments"]) == 2 ** n_eff
        assert float(r["minimum_attainable_p"]) == round(2 / 2 ** n_eff, 4)


def test_precision_row_reports_its_own_ceiling_not_the_recall_one():
    path = RESULTS / "primary_effects_summary.csv"
    if not path.exists():
        pytest.skip("primary_effects_summary.csv not generated")
    rows = {r["metric"]: r for r in csv.DictReader(
        path.read_text(encoding="utf-8-sig").splitlines())}
    assert rows["recall"]["n_nonzero_pairs"] == "5"
    assert float(rows["recall"]["minimum_attainable_p"]) == 0.0625
    assert rows["precision"]["n_nonzero_pairs"] == "3"
    assert rows["precision"]["n_ties"] == "2"
    assert float(rows["precision"]["minimum_attainable_p"]) == 0.25
