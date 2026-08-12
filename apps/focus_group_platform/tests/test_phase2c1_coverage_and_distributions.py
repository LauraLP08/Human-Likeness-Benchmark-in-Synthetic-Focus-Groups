"""
Phase 2C.1: per-metric coverage, coverage policies, and distribution aggregators.

Golden sources for INTERACTION_PROCESS remain the three structural artefacts only.
`primary_effects_by_fg.csv` is thematic and is never used here.
"""
from __future__ import annotations

import statistics

import pytest

from platform_core import aggregate as A
from platform_core.catalog import Family, load_catalog

STRUCT_SHEET_METRICS = ["total_words", "participant_turns", "words_per_turn_iqr",
                        "short_turn_proportion_25w", "turn_balance_gini",
                        "chain_depth", "moderator_word_share"]


@pytest.fixture(scope="module")
def rows():
    return A.load_frozen_metric_rows()


@pytest.fixture(scope="module")
def dist_rows():
    return A.load_frozen_distributions()


def _row(run, condition, fg, k, metric, value=1.0, side="synthetic"):
    return A.RunRow(run, side, condition, fg, k, metric, value)


def _complete_corpus(metric="m1", extra=()):
    rows = []
    for c in A.CONDITIONS:
        for f in A.FGS:
            for k in A.REPLICATES:
                rows.append(_row(f"{c}_{f}_r{k}", c, f, k, metric, float(k)))
    for f in A.FGS:
        rows.append(_row("", "", f, None, metric, 10.0, side="human"))
    return rows + list(extra)


# ===================================================== per-metric integrity
def test_duplicate_same_run_is_detected():
    rows = _complete_corpus()
    rows.append(_row("enriched_fg1_r1", "enriched", "fg1", 1, "m1", 1.0))
    cov = A.check_integrity(rows).for_metric("m1")
    assert cov.duplicate_same_run
    assert cov.duplicate_same_run[0]["unit"] == "enriched|fg1|r1"
    assert cov.duplicate_same_run[0]["n_rows"] == 2
    assert not cov.collision_different_runs
    assert cov.status == A.CoverageStatus.DUPLICATED.value


def test_collision_of_two_different_runs_is_detected():
    rows = _complete_corpus()
    rows.append(_row("a_different_run", "enriched", "fg1", 1, "m1", 2.0))
    cov = A.check_integrity(rows).for_metric("m1")
    assert cov.collision_different_runs
    assert sorted(cov.collision_different_runs[0]["runs"]) == \
        ["a_different_run", "enriched_fg1_r1"]
    assert not cov.duplicate_same_run


def test_the_two_defects_are_reported_separately():
    rows = _complete_corpus()
    rows.append(_row("enriched_fg1_r1", "enriched", "fg1", 1, "m1"))   # same run
    rows.append(_row("other", "enriched", "fg2", 1, "m1"))             # collision
    cov = A.check_integrity(rows).for_metric("m1")
    assert [d["unit"] for d in cov.duplicate_same_run] == ["enriched|fg1|r1"]
    assert [d["unit"] for d in cov.collision_different_runs] == ["enriched|fg2|r1"]


def test_one_metric_incomplete_is_not_hidden_by_another():
    """m2 is missing a replicate; m1's full coverage must not mask it."""
    rows = _complete_corpus("m1")
    for c in A.CONDITIONS:
        for f in A.FGS:
            for k in A.REPLICATES:
                if (c, f, k) == ("enriched", "fg3", 2):
                    continue
                rows.append(_row(f"{c}_{f}_r{k}", c, f, k, "m2", 1.0))
    for f in A.FGS:                       # m2 has its own human side, complete
        rows.append(_row("", "", f, None, "m2", 10.0, side="human"))
    report = A.check_integrity(rows)
    assert report.for_metric("m1").complete
    assert not report.for_metric("m2").complete
    assert report.for_metric("m2").missing_units == ["enriched|fg3|r2"]
    assert not report.complete
    assert report.incomplete_metrics() == ["m2"]


def test_duplicate_human_row_blocks_strict():
    rows = _complete_corpus()
    rows.append(_row("", "", "fg2", None, "m1", 99.0, side="human"))
    cov = A.check_integrity(rows).for_metric("m1")
    assert cov.human_duplicates == [{"fg": "fg2", "n_rows": 2}]
    assert not cov.complete
    with pytest.raises(A.CoverageError, match="human_duplicates"):
        A.aggregate_focus_group_condition(rows, ["m1"],
                                          policy=A.CoveragePolicy.STRICT)


def test_duplicate_human_value_is_not_silently_overwritten():
    rows = _complete_corpus()
    rows.append(_row("", "", "fg2", None, "m1", 99.0, side="human"))
    cells = A.aggregate_focus_group_condition(
        rows, ["m1"], policy=A.CoveragePolicy.EXPLORATORY)
    fg2 = next(c for c in cells if c.focus_group == "fg2"
               and c.condition == "enriched")
    assert fg2.human_value is None          # ambiguous, so undefined - not "the last"


def test_per_metric_coverage_counts_units():
    cov = A.check_integrity(_complete_corpus()).for_metric("m1")
    assert cov.cells_expected == 30         # 2 conditions x 5 FGs x 3 replicates
    assert cov.cells_present == 30
    assert cov.human_fgs_expected == list(A.FGS)
    assert cov.human_fgs_present == list(A.FGS)
    assert cov.human_n_valid == cov.human_n_expected == 5
    assert not cov.missing_human_fgs and not cov.undefined_human_fgs


# ============================================================ coverage modes
@pytest.mark.parametrize("fn", [
    A.aggregate_focus_group_condition,
    A.aggregate_study_replicates,
    A.summarise_study_level,
])
def test_public_aggregators_block_incomplete_input_in_strict(fn):
    rows = [r for r in _complete_corpus()
            if not (r.condition == "enriched" and r.fg == "fg1"
                    and r.replicate_index == 2)]
    with pytest.raises(A.CoverageError, match="STRICT policy blocks"):
        fn(rows, ["m1"], policy=A.CoveragePolicy.STRICT)


def test_frozen_workbook_route_blocks_incomplete_input_in_strict():
    rows = [r for r in _complete_corpus()
            if not (r.condition == "enriched" and r.fg == "fg1"
                    and r.replicate_index == 2)]
    with pytest.raises(A.CoverageError):
        A.frozen_workbook_route(rows, ["m1"], policy=A.CoveragePolicy.STRICT)


def test_aggregators_do_not_depend_on_the_caller_running_check_integrity():
    """No caller has to remember: the policy is applied inside."""
    rows = _complete_corpus()
    rows.append(_row("other", "enriched", "fg1", 1, "m1"))
    with pytest.raises(A.CoverageError):
        A.aggregate_focus_group_condition(rows, ["m1"])      # STRICT is the default


def test_exploratory_keeps_none_and_reports_missing_units():
    rows = [r for r in _complete_corpus()
            if not (r.condition == "enriched" and r.fg == "fg1"
                    and r.replicate_index == 2)]
    cells = A.aggregate_focus_group_condition(
        rows, ["m1"], policy=A.CoveragePolicy.EXPLORATORY)
    cell = next(c for c in cells if c.condition == "enriched"
                and c.focus_group == "fg1")
    assert cell.summary.values[1] is None                     # not imputed
    assert cell.summary.n_valid == 2 and cell.summary.n_expected == 3
    assert cell.coverage_status == A.CoverageStatus.INCOMPLETE.value
    assert cell.missing_units == ["enriched|fg1|r2"]
    assert cell.summary.mean == statistics.mean([1.0, 3.0])   # not (1+0+3)/3


def test_exploratory_study_replicate_reports_missing_units():
    rows = [r for r in _complete_corpus()
            if not (r.condition == "enriched" and r.fg == "fg4"
                    and r.replicate_index == 1)]
    reps = A.aggregate_study_replicates(rows, ["m1"],
                                        policy=A.CoveragePolicy.EXPLORATORY)
    rep = next(r for r in reps if r.condition == "enriched"
               and r.replicate_index == 1)
    assert rep.missing_units == ["enriched|fg4|r1"]
    assert rep.summary.n_valid == 4 and rep.summary.n_expected == 5
    assert rep.coverage_status == A.CoverageStatus.INCOMPLETE.value


def test_study_level_carries_coverage_status():
    rows = [r for r in _complete_corpus()
            if not (r.condition == "enriched" and r.fg == "fg4"
                    and r.replicate_index == 1)]
    out = A.summarise_study_level(rows, ["m1"],
                                  policy=A.CoveragePolicy.EXPLORATORY)
    enriched = next(o for o in out if o.condition == "enriched")
    assert enriched.coverage_status == A.CoverageStatus.INCOMPLETE.value
    assert "enriched|fg4|r1" in enriched.missing_units


def test_frozen_corpus_is_complete_under_strict(rows):
    report = A.check_integrity(rows)
    assert report.complete, report.problems()
    assert len(report.per_metric) == 19
    for cov in report.per_metric.values():
        assert cov.status == A.CoverageStatus.COMPLETE.value
        assert cov.cells_present == cov.cells_expected == 30


# ============================================= words_per_turn distribution
def test_words_per_turn_percentages_sum_to_one_within_each_run(dist_rows):
    out = A.aggregate_words_per_turn(dist_rows)
    assert len(out["synthetic"]["per_run"]) == 30
    for run, bins in out["synthetic"]["per_run"].items():
        assert sum(bins.values()) == pytest.approx(1.0, abs=1e-9), run
    for fg, bins in out["human_reference"]["per_run"].items():
        assert sum(bins.values()) == pytest.approx(1.0, abs=1e-9), fg


def test_words_per_turn_is_run_then_fg_then_condition(dist_rows):
    out = A.aggregate_words_per_turn(dist_rows)
    assert len(out["synthetic"]["per_run"]) == 30
    assert len(out["synthetic"]["per_cell"]) == 10
    assert set(out["synthetic"]["per_condition"]) == set(A.CONDITIONS)
    for c in out["synthetic"]["per_condition"].values():
        assert c["n_focus_groups"] == 5
    assert len(out["human_reference"]["per_run"]) == 5


def test_words_per_turn_reports_bins_dispersion_and_n(dist_rows):
    out = A.aggregate_words_per_turn(dist_rows)
    cond = out["synthetic"]["per_condition"]["enriched"]
    for label in out["bins"]:
        stats = cond["bins"][label]
        assert set(stats) == {"mean_percent", "sd_across_focus_groups",
                              "n_focus_groups"}
        assert stats["n_focus_groups"] == 5


def test_words_per_turn_bins_align_with_the_registry_thresholds():
    labels = [A._bin_label(lo, hi) for lo, hi in A.WORDS_PER_TURN_BINS]
    assert labels[0] == "0-9w" and labels[1] == "10-24w" and labels[2] == "25-49w"
    assert labels[-1].endswith("+")


def test_a_long_run_does_not_dominate_its_cell():
    """
    A run with three times the turns must not outweigh the other two.

    Planted: two runs of 10 turns, all short; one run of 300 turns, all long. Pooling
    the turns would report ~94% long; the run-first ladder reports 33%.
    """
    rows = []
    def mk(run, fg, condition, n, value):
        for i in range(n):
            rows.append({"side": "synthetic", "physical_run": run,
                         "condition": condition, "fg": fg,
                         "canonical_replication_index": "1",
                         "distribution_id": "words_per_turn",
                         "element_index": str(i), "element_label": f"P{i}",
                         "value": str(value), "supports_metric": "",
                         "namespace": "_comparable_window"})
    mk("r1", "fg1", "enriched", 10, 5)         # short
    mk("r2", "fg1", "enriched", 10, 5)         # short
    mk("r3", "fg1", "enriched", 300, 500)      # long, and 15x the turns

    out = A.aggregate_words_per_turn(rows)
    cell = out["synthetic"]["per_cell"]["enriched|fg1"]
    assert cell["n_runs"] == 3
    assert cell["bins"]["300w+"] == pytest.approx(1 / 3, abs=1e-9)
    assert cell["bins"]["0-9w"] == pytest.approx(2 / 3, abs=1e-9)
    pooled = 300 / 320
    assert cell["bins"]["300w+"] != pytest.approx(pooled, abs=1e-3)


def test_words_per_turn_declares_its_specification(dist_rows):
    out = A.aggregate_words_per_turn(dist_rows)
    for key in ("original_unit", "within_run_transformation",
                "within_focus_group_aggregation",
                "across_focus_group_aggregation", "denominators", "statistics",
                "bins", "human_reference_rule"):
        assert out[key]


# ================================== participant vectors and chain depth
@pytest.mark.parametrize("distribution_id", ["participant_turn_counts",
                                             "participant_word_counts"])
def test_participant_vectors_use_gini_and_shares_not_bins(distribution_id,
                                                          dist_rows):
    out = A.aggregate_participant_counts(distribution_id, dist_rows)
    assert out["statistics"] == ["gini"]
    assert "why_not_bins" in out
    assert "bins" not in out
    run = next(iter(out["synthetic"]["per_run"].values()))
    assert set(run) == {"n_participants", "gini", "per_run_diagnostics"}
    assert set(run["per_run_diagnostics"]) == {"share_min", "share_median",
                                               "share_max"}
    assert len(out["synthetic"]["gini_per_cell"]) == 10


def test_participant_aggregator_refuses_a_non_vector_distribution(dist_rows):
    with pytest.raises(A.AggregationError, match="not a per-participant vector"):
        A.aggregate_participant_counts("words_per_turn", dist_rows)


def test_chain_depth_keeps_median_iqr_and_maximum(dist_rows):
    out = A.aggregate_chain_depth(dist_rows)
    run = next(iter(out["synthetic"]["per_run"].values()))
    assert {"median", "iqr", "maximum", "mean", "n_chains"} <= set(run)
    for stat in ("median", "iqr", "maximum", "mean"):
        assert len(out["synthetic"]["aggregated"][stat]["per_cell"]) == 10
    assert "mean OF MAXIMA" in out["note"]


def test_every_distribution_has_a_dedicated_aggregator(dist_rows):
    assert set(A.DISTRIBUTION_AGGREGATORS) == set(A.DISTRIBUTION_IDS)
    for distribution_id, fn in A.DISTRIBUTION_AGGREGATORS.items():
        out = fn(dist_rows)
        assert out["distribution_id"] == distribution_id
        for key in ("original_unit", "within_run_transformation",
                    "within_focus_group_aggregation",
                    "across_focus_group_aggregation", "denominators",
                    "statistics"):
            assert out[key], (distribution_id, key)


def test_location_summary_is_named_and_labelled_as_such(dist_rows):
    out = A.summarise_distribution_location(dist_rows, "words_per_turn")
    assert "NOT the" in out["what_this_is"]
    assert out["statistic"] == "median"
    assert not hasattr(A, "summarise_distribution")


# ==================================================== naming and families
def test_families_are_stable_identifiers_and_levels_are_display():
    cat = load_catalog()
    entry = cat.get("words_per_turn_median")
    assert entry.family == Family.INTERACTION_PROCESS.value
    assert entry.display_order == 2
    assert entry.display_label == "Level 2 - Interaction process"
    assert cat.get("tier1_subtheme_recall").family == \
        Family.THEMATIC_FIDELITY.value
    assert cat.get("attribute_attitude_relational_fidelity").family == \
        Family.AGENT_FIDELITY.value
    assert cat.get("api_error_rate").family == Family.OPERATIONAL.value


def test_every_metric_belongs_to_exactly_one_family():
    cat = load_catalog()
    total = sum(len(cat.by_family(f)) for f in Family)
    assert total == len(cat.entries) == 46


def test_display_label_can_change_without_touching_identifiers():
    from platform_core import catalog
    assert set(catalog.FAMILY_DISPLAY) == set(Family)
    for cfg in catalog.FAMILY_DISPLAY.values():
        assert "display_order" in cfg and "display_label" in cfg


# ================================== frozen Level 2 values still reproduce
@pytest.mark.parametrize("metric_id", STRUCT_SHEET_METRICS)
def test_frozen_scalars_still_reproduce_under_strict(rows, metric_id):
    import re
    import zipfile
    from pathlib import Path
    xlsx = (Path(__file__).resolve().parents[3]
            / "analysis/production_evaluation/final/FINAL_RESULTS_TABLES.xlsx")
    xml = zipfile.ZipFile(xlsx).read("xl/worksheets/sheet4.xml").decode(
        "utf-8", "replace")
    frozen_sheet = {}
    for raw in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
        cells = [(t[0] or t[1] or t[2]) for t in re.findall(
            r"<is><t[^>]*>(.*?)</t></is>|<t[^>]*>(.*?)</t>|<v>(.*?)</v>", raw)]
        if len(cells) >= 5 and cells[0] in STRUCT_SHEET_METRICS:
            frozen_sheet[cells[0]] = [float(cells[1]), float(cells[2]),
                                      float(cells[3]), cells[5]]

    mine = {r["metric"]: r for r in A.frozen_workbook_route(
        rows, STRUCT_SHEET_METRICS, policy=A.CoveragePolicy.STRICT)}
    got, want = mine[metric_id], frozen_sheet[metric_id]
    assert round(got["human_mean"], 4) == round(want[0], 4)
    assert round(got["enriched_mean"], 4) == round(want[1], 4)
    assert round(got["demographics_only_mean"], 4) == round(want[2], 4)
    assert got["n_fg_enriched_closer_to_human"] == want[3]
    assert got["coverage_status"] == A.CoverageStatus.COMPLETE.value


def test_route_a_and_route_b_still_hold_on_the_frozen_corpus(rows):
    cells = A.aggregate_focus_group_condition(rows, ["total_words"])
    assert len(cells) == 10 and all(c.summary.n_valid == 3 for c in cells)
    reps = A.aggregate_study_replicates(rows, ["total_words"])
    assert len(reps) == 6 and all(r.summary.n_valid == 5 for r in reps)
    assert all(sorted(r.fgs_included) == list(A.FGS) for r in reps)


def test_replicate_index_is_still_read_not_inferred(rows):
    km = A.replicate_index_map(rows)
    assert km["macho_meals_fg4_run04"] == 2
    assert km["macho_meals_fg5_run04"] == 3
