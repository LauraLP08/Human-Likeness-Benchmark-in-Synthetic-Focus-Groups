"""
F1 must reach the statistical path unrounded.

The previous fix corrected recall, precision and reach but left `f1_score` rounding
to 4 dp unconditionally, and `unrounded_run_metrics` called it — so F1 differences,
signs and ties were still decided on 4-dp values while the other three were exact.
A partially-fixed pipeline is worse than an obviously broken one: three metrics look
trustworthy and the fourth silently is not.

`f1_score` now takes `ndigits`, mirroring `_rate`. The formula exists in one place.

No API calls.
"""

import csv
import statistics
import sys
from fractions import Fraction as F
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate_production_results as agg     # noqa: E402
import build_primary_effects_tables as eff     # noqa: E402

RESULTS = ROOT / "analysis" / "production_evaluation" / "results"


@pytest.fixture(scope="module")
def corpus():
    res = agg.load_results()
    if len(res) != 35:
        pytest.skip(f"corpus not complete ({len(res)}/35)")
    return res


@pytest.fixture(scope="module")
def data():
    return eff.build()


# ---------------------------------------------------------------------------
# (b) the statistical path uses unrounded F1
# ---------------------------------------------------------------------------

def test_f1_score_honours_ndigits_none():
    assert agg.f1_score(1 / 3, 1 / 6) == 0.2222
    exact = agg.f1_score(1 / 3, 1 / 6, ndigits=None)
    assert exact == pytest.approx(2 * (1 / 3) * (1 / 6) / (1 / 3 + 1 / 6), abs=1e-15)
    assert exact != 0.2222


def test_unrounded_run_metrics_returns_unrounded_f1(corpus):
    human = {r["input"]["fg"]: r for r in corpus if r["input"]["side"] == "human"}
    seen_unrounded = False
    for r in corpus:
        if r["input"]["side"] != "synthetic":
            continue
        m = agg.unrounded_run_metrics(human[r["input"]["fg"]], r)
        if m["f1_secondary"] is None:
            continue
        assert m["f1_secondary"] == agg.f1_score(m["recall"], m["precision"],
                                                 ndigits=None)
        if round(m["f1_secondary"], 4) != m["f1_secondary"]:
            seen_unrounded = True
    assert seen_unrounded, (
        "no F1 in the corpus carried more than 4 dp — the test cannot demonstrate "
        "the fix and must be reviewed")


def test_f1_matches_exact_rational_arithmetic(corpus):
    human = {r["input"]["fg"]: r for r in corpus if r["input"]["side"] == "human"}
    V = lambda r: {c["subtheme_id"] for c in r["tier1"]["codes"]
                   if c.get("present") and c.get("quote_verified")}
    for r in corpus:
        if r["input"]["side"] != "synthetic":
            continue
        h, s = V(human[r["input"]["fg"]]), V(r)
        if not h or not s:
            continue
        rec, pre = F(len(h & s), len(h)), F(len(h & s), len(s))
        exact = F(0) if rec + pre == 0 else 2 * rec * pre / (rec + pre)
        got = agg.unrounded_run_metrics(human[r["input"]["fg"]], r)["f1_secondary"]
        assert got == pytest.approx(float(exact), abs=1e-12)


# ---------------------------------------------------------------------------
# (c) the ordinary table keeps 4-dp presentation
# ---------------------------------------------------------------------------

def test_per_run_metrics_csv_keeps_four_decimal_f1():
    path = RESULTS / "per_run_metrics.csv"
    if not path.exists():
        pytest.skip("per_run_metrics.csv not generated")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert len(rows) == 30
    for r in rows:
        v = r["tier1_f1_secondary"]
        if v in ("", None):
            continue
        assert float(v) == round(float(v), 4), f"{r['physical_run']}: F1 {v} exceeds 4 dp"
        assert len(v.split(".")[-1]) <= 4


def test_aggregate_table_path_still_rounds(corpus):
    rows = agg.aggregate(corpus)["per_run_metrics.csv"]
    for r in rows:
        v = r["tier1_f1_secondary"]
        if v is not None:
            assert v == round(v, 4)


def test_default_ndigits_is_unchanged_for_every_caller():
    """Anything calling f1_score without ndigits must behave exactly as before."""
    for rec, pre in ((0.75, 0.75), (1 / 3, 1 / 6), (0.0, 0.0), (1.0, 1.0),
                     (2 / 7, 5 / 11)):
        assert agg.f1_score(rec, pre) == round(
            agg.f1_score(rec, pre, ndigits=None), 4)
    assert agg.f1_score(None, 0.5) is None
    assert agg.f1_score(0.5, None) is None
    assert agg.f1_score(0.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# (a) + (d) tiny differences, signs, ties and the sign test
# ---------------------------------------------------------------------------

def test_tiny_f1_difference_is_not_flattened_into_a_tie():
    """Two cells whose exact F1 means differ by < 5e-5 must not become a tie."""
    e = [F(1, 3), F(1, 3), F(1, 3)]
    d = [F(33333, 100000), F(33333, 100000), F(33333, 100000)]
    em, dm = sum(e) / len(e), sum(d) / len(d)
    diff = float(em - dm)
    assert 0 < abs(diff) < 5e-5
    assert round(diff, 4) == 0.0, "4-dp rounding would have called this a tie"
    r = eff.sign_test_two_sided([diff, 0.1, 0.2, 0.3, 0.4])
    assert r["n_ties"] == 0
    assert r["n_effective_pairs"] == 5


def test_f1_signs_and_ties_come_from_unrounded_values(data):
    entry = data["metrics"]["f1_secondary"]
    for p in entry["per_fg"]:
        full = p["difference_full_precision"]
        assert (p["direction"] == "tie") == (full == 0.0)
        assert p["difference_enriched_minus_demo"] == round(full, 4)
    t = entry["exploratory_sign_test"]
    recomputed = eff.sign_test_two_sided(
        [p["difference_full_precision"] for p in entry["per_fg"]])
    for k in ("n_effective_pairs", "n_ties", "possible_sign_assignments",
              "p_two_sided", "minimum_attainable_two_sided_p"):
        assert t[k] == recomputed[k]


def test_f1_full_precision_values_are_not_multiples_of_one_ten_thousandth(data):
    """If F1 were still rounded upstream, every difference would sit on a 1e-4 grid."""
    fulls = [p["difference_full_precision"]
             for p in data["metrics"]["f1_secondary"]["per_fg"]]
    off_grid = [v for v in fulls if abs(v - round(v, 4)) > 1e-9]
    assert off_grid, ("every F1 difference lands exactly on the 4-dp grid, which is "
                      "what a still-rounded upstream would produce")


# ---------------------------------------------------------------------------
# (e) the values that changed
# ---------------------------------------------------------------------------

def test_within_cell_sds_are_computed_from_unrounded_f1(data):
    """The three SDs the fix corrected, verified against exact arithmetic."""
    expected = {("fg2", "demographics_only_within_cell_sd"): 0.2297,
                ("fg3", "enriched_within_cell_sd"): 0.0634,
                ("fg4", "enriched_within_cell_sd"): 0.1866}
    per_fg = {p["fg"]: p for p in data["metrics"]["f1_secondary"]["per_fg"]}
    for (fg, key), want in expected.items():
        assert per_fg[fg][key] == want, (
            f"{fg}.{key} is {per_fg[fg][key]}, expected {want} from unrounded F1")


def test_sd_from_rounded_inputs_would_differ(corpus):
    """Shows the three SD corrections are real, not cosmetic."""
    human = {r["input"]["fg"]: r for r in corpus if r["input"]["side"] == "human"}
    V = lambda r: {c["subtheme_id"] for c in r["tier1"]["codes"]
                   if c.get("present") and c.get("quote_verified")}
    for fg, cond, old, new in (("fg2", "demographics-only", 0.2298, 0.2297),
                               ("fg3", "enriched", 0.0635, 0.0634),
                               ("fg4", "enriched", 0.1867, 0.1866)):
        vals = []
        for r in corpus:
            if (r["input"]["side"] != "synthetic" or r["input"]["fg"] != fg
                    or r["input"]["condition"] != cond):
                continue
            h, s = V(human[fg]), V(r)
            rec, pre = F(len(h & s), len(h)), F(len(h & s), len(s))
            vals.append(F(0) if rec + pre == 0 else 2 * rec * pre / (rec + pre))
        exact = [float(v) for v in vals]
        assert round(statistics.stdev(exact), 4) == new
        assert round(statistics.stdev([round(v, 4) for v in exact]), 4) == old


def test_recall_precision_reach_are_untouched_by_the_f1_fix(data):
    """The F1 fix must not have moved any other metric."""
    expected = {
        "recall": {"fg1": 0.0417, "fg2": -0.0476, "fg3": 0.2667,
                   "fg4": 0.2778, "fg5": 0.0667},
        "precision": {"fg1": 0.0, "fg2": -0.0833, "fg3": 0.0,
                      "fg4": 0.4222, "fg5": 0.05},
        "reach": {"fg1": 0.2389, "fg2": 0.2167, "fg3": 0.1056,
                  "fg4": -0.1704, "fg5": 0.1972},
    }
    for metric, per_fg in expected.items():
        got = {p["fg"]: p["difference_enriched_minus_demo"]
               for p in data["metrics"][metric]["per_fg"]}
        assert got == per_fg, f"{metric} changed: {got}"


def test_f1_aggregate_figures_are_unchanged(data):
    s = data["metrics"]["f1_secondary"]["across_fgs"]
    assert s["mean_difference"] == 0.1495
    assert s["median_difference"] == 0.0685
    assert s["min_difference"] == -0.0606
    assert s["max_difference"] == 0.353
    assert (s["n_favouring_enriched"], s["n_favouring_demographics_only"],
            s["n_ties"]) == (4, 1, 0)
