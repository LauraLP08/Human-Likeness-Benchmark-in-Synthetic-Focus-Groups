"""
Signs and ties must be decided at full precision; rounding is for display only.

The effect pipeline used to average 4-dp values, difference them, and round again —
so a tie was whatever rounded to 0.0 at 4 dp. A true difference below 5e-5 would have
been recorded as an exact tie, and one displayed figure was wrong by a unit in the
last place (FG2 recall: -0.0477 for an exact -1/21 = -0.047619...).

TIE DEFINITION: a pair is a tie when the FULL-PRECISION difference of the two cell
means is exactly 0.0. Not "rounds to zero".

No API calls.
"""

import csv
import json
import statistics
import sys
from fractions import Fraction as F
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate_production_results as agg     # noqa: E402
import build_primary_effects_tables as eff     # noqa: E402

OUT = ROOT / "analysis" / "production_evaluation"
RESULTS = OUT / "results"


@pytest.fixture(scope="module")
def data():
    return eff.build()


@pytest.fixture(scope="module")
def corpus():
    res = agg.load_results()
    if len(res) != 35:
        pytest.skip(f"corpus not complete ({len(res)}/35)")
    return res


# ---------------------------------------------------------------------------
# (a) a real difference below display precision is not a tie
# ---------------------------------------------------------------------------

def test_tiny_real_difference_is_not_swallowed_into_a_tie():
    diffs = [1e-6, -1e-6, 3e-5, -4.9e-5, 0.2]
    r = eff.sign_test_two_sided(diffs)
    assert r["n_effective_pairs"] == 5, (
        "differences below 5e-5 are real and must keep their sign")
    assert r["n_ties"] == 0
    assert all(round(d, 4) == 0.0 for d in diffs[:4]), (
        "these are exactly the values 4-dp rounding would have flattened")


def test_a_difference_of_one_ulp_still_counts():
    r = eff.sign_test_two_sided([5e-16, 0.1, 0.2, 0.3, 0.4])
    assert r["n_effective_pairs"] == 5 and r["n_ties"] == 0


def test_only_exact_zero_is_a_tie():
    r = eff.sign_test_two_sided([0.0, -0.0, 1e-12, 0.1, -0.1])
    assert r["n_ties"] == 2, "0.0 and -0.0 are ties; 1e-12 is not"
    assert r["n_effective_pairs"] == 3
    assert eff.TIE_IS_EXACT_ZERO is True


def test_rounding_before_differencing_would_have_flipped_a_tie():
    """Demonstrates the defect this guards against, on synthetic values."""
    e_vals, d_vals = [0.33334, 0.33334, 0.33334], [0.33330, 0.33330, 0.33330]
    exact = statistics.mean(e_vals) - statistics.mean(d_vals)
    naive = round(round(statistics.mean(e_vals), 4)
                  - round(statistics.mean(d_vals), 4), 4)
    assert exact != 0.0, "the true difference is non-zero"
    assert naive == 0.0, "the old double-rounded path would call it a tie"
    assert eff.sign_test_two_sided([exact, 0.1, 0.2, 0.3, 0.4])["n_ties"] == 0


# ---------------------------------------------------------------------------
# (b) the observed precision ties are genuine
# ---------------------------------------------------------------------------

def test_fg1_and_fg3_precision_ties_are_exact_not_rounding_artefacts(corpus):
    """Verified with exact rational arithmetic from the cache, not floats."""
    human = {r["input"]["fg"]: r for r in corpus if r["input"]["side"] == "human"}
    synth = [r for r in corpus if r["input"]["side"] == "synthetic"]
    V = lambda r: {c["subtheme_id"] for c in r["tier1"]["codes"]
                   if c.get("present") and c.get("quote_verified")}
    for fg in ("fg1", "fg3"):
        h = V(human[fg])
        means = {}
        for cond in ("enriched", "demographics-only"):
            vals = []
            for r in synth:
                if r["input"]["fg"] != fg or r["input"]["condition"] != cond:
                    continue
                s = V(r)
                vals.append(F(len(h & s), len(s)) if s else None)
            vals = [v for v in vals if v is not None]
            means[cond] = sum(vals) / len(vals)
        exact_diff = means["enriched"] - means["demographics-only"]
        assert exact_diff == F(0), (
            f"{fg} precision difference is {exact_diff}, not an exact tie")


def test_reported_ties_match_exact_arithmetic(data, corpus):
    """Every tie the tables report must be an exact zero, and vice versa."""
    for metric, entry in data["metrics"].items():
        for p in entry["per_fg"]:
            full = p["difference_full_precision"]
            is_tie = p["direction"] == "tie"
            assert is_tie == (full == 0.0), (
                f"{metric}/{p['fg']}: direction={p['direction']} but "
                f"full-precision difference is {full!r}")


# ---------------------------------------------------------------------------
# (c) display rounding does not change the test
# ---------------------------------------------------------------------------

def test_rounding_for_display_does_not_alter_n_effective_ties_or_p(data):
    for metric, entry in data["metrics"].items():
        full = [p["difference_full_precision"] for p in entry["per_fg"]]
        a = eff.sign_test_two_sided(full)
        b = eff.sign_test_two_sided([round(x, 4) for x in full])
        for k in ("n_effective_pairs", "n_ties", "possible_sign_assignments",
                  "p_two_sided", "minimum_attainable_two_sided_p"):
            assert a[k] == b[k], f"{metric}: {k} changed under display rounding"


def test_displayed_difference_equals_rounded_full_precision(data):
    for metric, entry in data["metrics"].items():
        for p in entry["per_fg"]:
            assert p["difference_enriched_minus_demo"] == round(
                p["difference_full_precision"], 4), (
                f"{metric}/{p['fg']}: displayed value is not the rounded exact value")


# ---------------------------------------------------------------------------
# (d) the corrected values are the exact ones
# ---------------------------------------------------------------------------

EXPECTED_EXACT = {                      # from rational arithmetic over the cache
    ("recall", "fg1"): F(1, 24), ("recall", "fg2"): F(-1, 21),
    ("recall", "fg3"): F(4, 15), ("recall", "fg4"): F(5, 18),
    ("recall", "fg5"): F(1, 15),
    ("precision", "fg1"): F(0), ("precision", "fg2"): F(-1, 12),
    ("precision", "fg3"): F(0), ("precision", "fg4"): F(19, 45),
    ("precision", "fg5"): F(1, 20),
    ("reach", "fg1"): F(43, 180), ("reach", "fg2"): F(13, 60),
    ("reach", "fg3"): F(19, 180), ("reach", "fg4"): F(-23, 135),
    ("reach", "fg5"): F(71, 360),
}


def test_effects_match_exact_rational_values(data):
    for (metric, fg), frac in EXPECTED_EXACT.items():
        p = next(x for x in data["metrics"][metric]["per_fg"] if x["fg"] == fg)
        assert p["difference_full_precision"] == pytest.approx(float(frac), abs=1e-12)
        assert p["difference_enriched_minus_demo"] == round(float(frac), 4)


def test_fg2_recall_is_the_corrected_value():
    """The one figure the fix changed: -0.0477 was double-rounded; -1/21 -> -0.0476."""
    assert round(float(F(-1, 21)), 4) == -0.0476
    rows = {(r["metric"], r["fg"]): r for r in csv.DictReader(
        (RESULTS / "primary_effects_by_fg.csv").read_text(encoding="utf-8-sig").splitlines())}
    assert float(rows[("recall", "fg2")]["difference_enriched_minus_demo"]) == -0.0476


def test_directions_and_counts_are_unchanged_by_the_fix(data):
    expected = {"recall": (4, 1, 0), "precision": (2, 1, 2),
                "reach": (4, 1, 0), "f1_secondary": (4, 1, 0)}
    for metric, (e, d, t) in expected.items():
        s = data["metrics"][metric]["across_fgs"]
        assert (s["n_favouring_enriched"], s["n_favouring_demographics_only"],
                s["n_ties"]) == (e, d, t)


def test_aggregator_table_rounding_is_unchanged():
    """`_rate` must still round to 4 dp by default — only the opt-in path is new."""
    assert agg._rate(1, 3) == 0.3333
    assert agg._rate(1, 3, ndigits=None) == pytest.approx(1 / 3, abs=1e-15)
    assert agg._rate(1, 0) is None and agg._rate(1, 0, ndigits=None) is None


def test_unrounded_run_metrics_shares_definitions_with_the_table_path(corpus):
    human = {r["input"]["fg"]: r for r in corpus if r["input"]["side"] == "human"}
    table = {r["physical_run"]: r
             for r in agg.aggregate(corpus)["per_run_metrics.csv"]}
    for r in corpus:
        if r["input"]["side"] != "synthetic":
            continue
        m = agg.unrounded_run_metrics(human[r["input"]["fg"]], r)
        t = table[r["input"]["physical_run"]]
        assert m["shared_n"] == t["shared_n"]
        assert m["human_present_n"] == t["human_present_n"]
        for k, col in (("recall", "tier1_subtheme_recall"),
                       ("precision", "tier1_matched_theme_precision")):
            if m[k] is None:
                assert t[col] is None
            else:
                assert round(m[k], 4) == t[col], (
                    f"{r['input']['physical_run']}: {k} diverges from the table path")
