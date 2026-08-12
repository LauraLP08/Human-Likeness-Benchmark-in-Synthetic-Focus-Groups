"""
Phase 2C.1 closure (block A): two-sided coverage, provenance status, fixed
words_per_turn bins, a declared quartile estimator, and share diagnostics that are
labelled as diagnostics.
"""
from __future__ import annotations

import json
import statistics

import pytest

from platform_core import aggregate as A


def _row(run, condition, fg, k, metric, value=1.0, side="synthetic"):
    return A.RunRow(run, side, condition, fg, k, metric, value)


def _corpus(metric="m1", human_fgs=A.FGS, human_value=10.0):
    rows = []
    for c in A.CONDITIONS:
        for f in A.FGS:
            for k in A.REPLICATES:
                rows.append(_row(f"{c}_{f}_r{k}", c, f, k, metric, float(k)))
    for f in human_fgs:
        rows.append(_row("", "", f, None, metric, human_value, side="human"))
    return rows


# ============================================== A1 two-sided metric coverage
def test_full_synthetic_coverage_with_a_missing_human_fg_is_not_complete():
    rows = _corpus(human_fgs=("fg1", "fg2", "fg3", "fg4"))
    cov = A.check_integrity(rows).for_metric("m1")
    assert cov.cells_present == cov.cells_expected == 30      # synthetic is perfect
    assert cov.missing_human_fgs == ["fg5"]
    assert cov.human_fgs_expected == list(A.FGS)
    assert cov.human_n_valid == 4
    assert not cov.complete
    assert cov.status == A.CoverageStatus.INCOMPLETE.value
    assert "human|fg5" in cov.missing_units


def test_a_null_human_value_is_undefined_not_missing():
    rows = _corpus()
    rows = [r for r in rows if not (r.side == "human" and r.fg == "fg3")]
    rows.append(_row("", "", "fg3", None, "m1", None, side="human"))
    cov = A.check_integrity(rows).for_metric("m1")
    assert cov.human_fgs_present == list(A.FGS)      # the row IS there
    assert cov.missing_human_fgs == []
    assert cov.undefined_human_fgs == ["fg3"]        # its value is not
    assert cov.human_n_valid == 4
    assert not cov.complete


def test_an_ambiguous_human_fg_counts_as_undefined():
    """Two rows for one focus group: no defensible value, so no value."""
    rows = _corpus()
    rows.append(_row("", "", "fg2", None, "m1", 99.0, side="human"))
    cov = A.check_integrity(rows).for_metric("m1")
    assert cov.human_duplicates == [{"fg": "fg2", "n_rows": 2}]
    assert cov.undefined_human_fgs == ["fg2"]
    assert cov.human_n_valid == 4


@pytest.mark.parametrize("fn", [A.aggregate_focus_group_condition,
                                A.aggregate_study_replicates,
                                A.summarise_study_level])
@pytest.mark.parametrize("mutate", ["missing_human", "null_human"])
def test_strict_blocks_both_human_defects(fn, mutate):
    if mutate == "missing_human":
        rows = _corpus(human_fgs=("fg1", "fg2", "fg3", "fg4"))
    else:
        rows = [r for r in _corpus() if not (r.side == "human" and r.fg == "fg3")]
        rows.append(_row("", "", "fg3", None, "m1", None, side="human"))
    with pytest.raises(A.CoverageError, match="human_fgs"):
        fn(rows, ["m1"], policy=A.CoveragePolicy.STRICT)


def test_exploratory_continues_and_declares_the_reduced_human_n():
    rows = _corpus(human_fgs=("fg1", "fg2", "fg3", "fg4"))
    out = A.summarise_study_level(rows, ["m1"],
                                  policy=A.CoveragePolicy.EXPLORATORY)
    enriched = next(o for o in out if o.condition == "enriched")
    href = enriched.human_reference
    assert href.n_expected == 5 and href.n_valid == 4     # denominator reduced...
    assert href.mean == 10.0                              # ...not diluted by a zero
    assert href.values == [10.0, 10.0, 10.0, 10.0, None]
    assert href.missing_units == ["human|fg5"]
    assert "human|fg5" in enriched.missing_units
    assert enriched.coverage_status == A.CoverageStatus.INCOMPLETE.value


def test_a_missing_human_group_never_becomes_zero():
    rows = _corpus(human_fgs=("fg1", "fg2", "fg3", "fg4"))
    cells = A.aggregate_focus_group_condition(
        rows, ["m1"], policy=A.CoveragePolicy.EXPLORATORY)
    fg5 = next(c for c in cells if c.focus_group == "fg5"
               and c.condition == "enriched")
    assert fg5.human_value is None
    assert 0 not in [c.human_value for c in cells]


def test_a_non_comparative_metric_can_declare_it_needs_no_human_side():
    rows = [r for r in _corpus() if r.side == "synthetic"]
    cov = A.check_integrity(rows, ["m1"],
                            human_reference_required=False).for_metric("m1")
    assert cov.human_reference_required is False
    assert cov.human_fgs_expected == [] and cov.complete
    A.aggregate_focus_group_condition(rows, ["m1"],
                                      human_reference_required=False)


def test_the_requirement_can_be_declared_per_metric():
    rows = [r for r in _corpus("m1") if r.side == "synthetic"]
    rows += [r for r in _corpus("m2") if r.side == "synthetic"]
    report = A.check_integrity(rows, ["m1", "m2"], human_reference_required=["m1"])
    assert not report.for_metric("m1").complete       # comparative, human absent
    assert report.for_metric("m2").complete           # declared non-comparative


def test_the_frozen_corpus_is_complete_on_both_sides():
    report = A.check_integrity(A.load_frozen_metric_rows())
    assert report.complete, report.problems()
    for cov in report.per_metric.values():
        assert cov.human_n_valid == cov.human_n_expected == 5


# ==================================================== A2 calculation status
def test_the_reproduced_scalars_are_labelled_frozen_reproduced():
    rows = A.load_frozen_metric_rows()
    got = A.frozen_workbook_route(rows, ["total_words"])[0]
    assert got["calculation_status"] == A.CalculationStatus.FROZEN_REPRODUCED.value
    assert got["source_artifact"].endswith("3_Structural_Interaction")
    assert got["aggregation_version"] == A.AGGREGATION_VERSION
    assert got["aggregation_rule"]


@pytest.mark.parametrize("fn,kwargs", [
    (A.aggregate_words_per_turn, {}),
    (lambda **k: A.aggregate_participant_counts("participant_turn_counts"), {}),
    (lambda **k: A.aggregate_participant_counts("participant_word_counts"), {}),
    (A.aggregate_chain_depth, {}),
])
def test_the_new_distribution_summaries_are_labelled_derived_from_frozen(fn, kwargs):
    out = fn(**kwargs)
    assert out["calculation_status"] == \
        A.CalculationStatus.DERIVED_FROM_FROZEN.value
    assert "structural_distributions_long.csv" in out["source_artifact"]
    assert out["aggregation_version"] == A.AGGREGATION_VERSION
    assert out["aggregation_rule"]


def test_study_replicates_are_not_claimed_to_be_reproduced():
    """No golden structural study-replicate table exists, so no such claim."""
    rows = A.load_frozen_metric_rows()
    rep = A.aggregate_study_replicates(rows, ["total_words"])[0]
    assert rep.provenance["calculation_status"] == \
        A.CalculationStatus.DERIVED_FROM_FROZEN.value


def test_generated_utc_is_on_the_envelope_and_never_inside_a_result():
    rows = A.load_frozen_metric_rows()
    payload = {"workbook": A.frozen_workbook_route(rows, ["total_words"]),
               "words_per_turn": A.aggregate_words_per_turn()}
    assert "generated_utc" not in json.dumps(payload)
    stamped = A.stamp_output_artifact(payload, "2026-08-04T00:00:00Z")
    assert stamped["generated_utc"] == "2026-08-04T00:00:00Z"
    assert "generated_utc" not in json.dumps(stamped["results"])


def test_results_are_byte_identical_across_two_calls():
    """A timestamp inside a result would break this."""
    rows = A.load_frozen_metric_rows()
    a = json.dumps(A.frozen_workbook_route(rows, ["total_words"]), sort_keys=True)
    b = json.dumps(A.frozen_workbook_route(rows, ["total_words"]), sort_keys=True)
    assert a == b


# ================================================== A3 words_per_turn bins
def test_the_bins_are_the_agreed_fixed_set():
    labels = [A._bin_label(lo, hi) for lo, hi in A.WORDS_PER_TURN_BINS]
    assert labels == ["0-9w", "10-24w", "25-49w", "50-99w", "100-199w",
                      "200-249w", "250-299w", "300w+"]


def test_the_first_three_edges_are_the_registry_short_turn_thresholds():
    edges = [lo for lo, _ in A.WORDS_PER_TURN_BINS]
    for threshold in (10, 25, 50):        # short_turn_proportion_10w/25w/50w
        assert threshold in edges


def test_a_turn_falls_on_the_same_side_of_a_boundary_as_the_scalar_metric():
    """
    `short_turn_proportion_25w` counts turns with fewer than 25 words. The bins below
    25 must contain exactly those turns - no more, no fewer.
    """
    values = [0, 9, 10, 24, 25, 49, 50, 99, 100, 199, 200, 249, 250, 299, 300, 1000]
    pct = A._bin_percentages([float(v) for v in values])
    n = len(values)
    below_25 = (pct["0-9w"] + pct["10-24w"]) * n
    assert below_25 == sum(1 for v in values if v < 25)
    below_10 = pct["0-9w"] * n
    assert below_10 == sum(1 for v in values if v < 10)
    below_50 = (pct["0-9w"] + pct["10-24w"] + pct["25-49w"]) * n
    assert below_50 == sum(1 for v in values if v < 50)


def test_the_bins_are_not_chosen_from_the_corpus():
    """Two very different corpora must produce the same bin labels."""
    def mk(run, value, n):
        return [{"side": "synthetic", "physical_run": run, "condition": "enriched",
                 "fg": "fg1", "canonical_replication_index": "1",
                 "distribution_id": "words_per_turn", "element_index": str(i),
                 "element_label": f"t{i}", "value": str(value),
                 "supports_metric": "", "namespace": "_comparable_window"}
                for i in range(n)]
    tiny = A.aggregate_words_per_turn(mk("r1", 3, 5))
    huge = A.aggregate_words_per_turn(mk("r1", 4000, 5))
    assert tiny["bins"] == huge["bins"] == \
        [A._bin_label(lo, hi) for lo, hi in A.WORDS_PER_TURN_BINS]
    assert huge["synthetic"]["per_run"]["r1"]["300w+"] == 1.0


def test_percentages_still_sum_to_one_with_the_new_bins():
    rows = A.load_frozen_distributions()
    out = A.aggregate_words_per_turn(rows)
    for side in ("synthetic", "human_reference"):
        for run, bins in out[side]["per_run"].items():
            assert sum(bins.values()) == pytest.approx(1.0, abs=1e-12), (side, run)
        for cell in out[side]["per_cell"].values():
            assert sum(cell["bins"].values()) == pytest.approx(1.0, abs=1e-12)
        for cond in out[side]["per_condition"].values():
            total = sum(b["mean_percent"] for b in cond["bins"].values())
            assert total == pytest.approx(1.0, abs=1e-12)


def test_the_run_to_fg_to_condition_ladder_survives_the_new_bins():
    rows = A.load_frozen_distributions()
    out = A.aggregate_words_per_turn(rows)
    assert len(out["synthetic"]["per_run"]) == 30
    assert len(out["synthetic"]["per_cell"]) == 10
    assert all(c["n_focus_groups"] == 5
               for c in out["synthetic"]["per_condition"].values())
    assert len(out["human_reference"]["per_run"]) == 5


def test_no_pooling_with_the_new_top_bins():
    """One 300-turn run of 5000-word turns must not swamp two 10-turn runs."""
    rows = []
    for run, n, value in (("r1", 10, 5), ("r2", 10, 5), ("r3", 300, 5000)):
        rows += [{"side": "synthetic", "physical_run": run, "condition": "enriched",
                  "fg": "fg1", "canonical_replication_index": "1",
                  "distribution_id": "words_per_turn", "element_index": str(i),
                  "element_label": f"t{i}", "value": str(value),
                  "supports_metric": "", "namespace": "_comparable_window"}
                 for i in range(n)]
    cell = A.aggregate_words_per_turn(rows)["synthetic"]["per_cell"]["enriched|fg1"]
    assert cell["bins"]["300w+"] == pytest.approx(1 / 3, abs=1e-12)
    assert cell["bins"]["0-9w"] == pytest.approx(2 / 3, abs=1e-12)
    assert cell["bins"]["300w+"] != pytest.approx(300 / 320, abs=1e-3)


# ==================================================== A4 quartile estimator
@pytest.mark.parametrize("values,expected_iqr", [
    ([4.0], None),
    ([2.0, 6.0], 2.0),                       # q1=3, q3=5 under the inclusive method
    ([1.0, 2.0, 9.0], 4.0),                  # q1=1.5, q3=5.5
    ([1.0, 2.0, 3.0, 4.0], 1.5),             # q1=1.75, q3=3.25
])
def test_quartiles_on_short_vectors(values, expected_iqr):
    q1, q3, iqr = A.quartiles(values)
    if expected_iqr is None:
        assert (q1, q3, iqr) == (None, None, None)
        return
    assert iqr == pytest.approx(expected_iqr, abs=1e-12)
    assert min(values) <= q1 <= q3 <= max(values)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 11])
def test_no_quartile_ever_leaves_the_observed_range(n):
    values = [float(v) for v in range(1, n + 1)]
    q1, q3, _ = A.quartiles(values)
    if q1 is None:
        assert n == 1
        return
    assert min(values) <= q1 <= max(values)
    assert min(values) <= q3 <= max(values)


def test_a_single_chain_gives_an_undefined_iqr_not_zero():
    rows = [{"side": "synthetic", "physical_run": "r1", "condition": "enriched",
             "fg": "fg1", "canonical_replication_index": "1",
             "distribution_id": "chain_depth", "element_index": "0",
             "element_label": "c0", "value": "3", "supports_metric": "",
             "namespace": "_comparable_window"}]
    run = A.aggregate_chain_depth(rows)["synthetic"]["per_run"]["r1"]
    assert run["n_chains"] == 1
    assert run["iqr"] is None
    assert run["iqr_undefined_reason"]
    assert run["median"] == 3 and run["maximum"] == 3


def test_an_undefined_iqr_reduces_n_rather_than_being_averaged_as_zero():
    rows = []
    for run, values in (("r1", [3]), ("r2", [1, 2, 3, 4]), ("r3", [1, 2, 3, 4])):
        rows += [{"side": "synthetic", "physical_run": run, "condition": "enriched",
                  "fg": "fg1", "canonical_replication_index": "1",
                  "distribution_id": "chain_depth", "element_index": str(i),
                  "element_label": f"c{i}", "value": str(v), "supports_metric": "",
                  "namespace": "_comparable_window"}
                 for i, v in enumerate(values)]
    agg = A.aggregate_chain_depth(rows)["synthetic"]["aggregated"]["iqr"]
    assert agg["n_runs_contributing"] == 2 and agg["n_runs_undefined"] == 1
    assert agg["per_cell"]["enriched|fg1"]["mean"] == pytest.approx(1.5, abs=1e-9)
    assert agg["per_cell"]["enriched|fg1"]["n_runs"] == 2      # not 3


def test_the_quartile_method_is_declared_in_the_output():
    out = A.aggregate_chain_depth()
    assert out["quartile_method"] == "inclusive"
    assert "min-max" in out["quartile_method_note"]
    run = next(iter(out["synthetic"]["per_run"].values()))
    assert run["q1"] is not None and run["q3"] is not None
    assert run["q1"] <= run["median"] <= run["q3"] <= run["maximum"]


# =================================================== A5 participant shares
@pytest.mark.parametrize("distribution_id", ["participant_turn_counts",
                                             "participant_word_counts"])
def test_shares_are_per_run_diagnostics_and_gini_is_the_aggregate(distribution_id):
    out = A.aggregate_participant_counts(distribution_id)
    assert out["aggregated_statistics"] == ["gini"]
    assert out["per_run_diagnostics"] == ["share_min", "share_median", "share_max"]
    assert out["per_run_diagnostics_note"]
    for run in out["synthetic"]["per_run"].values():
        assert set(run["per_run_diagnostics"]) == {"share_min", "share_median",
                                                   "share_max"}
    # Nothing named `share_*` was carried above the run.
    for level in ("gini_per_cell", "gini_per_condition"):
        assert "share" not in json.dumps(out["synthetic"][level])


def test_the_aggregated_gini_is_a_mean_of_run_ginis():
    rows = []
    for run, values in (("r1", [1, 1, 1, 1]), ("r2", [7, 1, 1, 1])):
        rows += [{"side": "synthetic", "physical_run": run, "condition": "enriched",
                  "fg": "fg1", "canonical_replication_index": "1",
                  "distribution_id": "participant_turn_counts",
                  "element_index": str(i), "element_label": f"P{i}",
                  "value": str(v), "supports_metric": "",
                  "namespace": "_comparable_window"}
                 for i, v in enumerate(values)]
    out = A.aggregate_participant_counts("participant_turn_counts", rows)
    per_run = out["synthetic"]["per_run"]
    assert per_run["r1"]["gini"] == pytest.approx(0.0, abs=1e-9)
    cell = out["synthetic"]["gini_per_cell"]["enriched|fg1"]
    assert cell["n_runs"] == 2
    assert cell["mean"] == pytest.approx(
        statistics.mean([per_run["r1"]["gini"], per_run["r2"]["gini"]]), abs=1e-6)
