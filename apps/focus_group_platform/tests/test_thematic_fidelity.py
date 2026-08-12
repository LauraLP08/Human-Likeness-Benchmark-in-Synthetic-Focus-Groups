"""
THEMATIC_FIDELITY offline layer (block B).

Every number here comes from an artefact that already exists. Nothing in this file
calls an evaluator, and a test asserts that nothing could.
"""
from __future__ import annotations

import csv
import hashlib
import statistics
import sys

import pytest

from platform_core import thematic as T
from platform_core.aggregate import CalculationStatus, FGS, REPLICATES
from platform_core.config import REPO_ROOT

RESULTS = REPO_ROOT / "analysis" / "production_evaluation" / "results"


def _csv(path):
    return list(csv.DictReader(path.open(encoding="utf-8-sig")))


@pytest.fixture(scope="module")
def primary():
    return T.primary_results()


# ============================================================ B2 source registry
def test_every_registered_source_matches_its_pinned_schema_hash_and_row_count():
    for report in T.verify_sources():
        assert report["exists"], report
        assert report["ok"], (report["key"], report["problems"])


def test_expected_row_counts_are_declared_not_discovered():
    expected = {"per_run_metrics": 30, "primary_effects_by_fg": 20,
                "per_group_condition_summary": 10, "study_replication_summary": 6,
                "thematic_code_presence_long": 385, "thematic_reach_long": 125,
                "salience_hierarchy_per_run": 30,
                "salience_hierarchy_by_fg_condition": 10,
                "across_group_recurrence_sensitivity": 77,
                "combined_recurrence_sensitivity": 77,
                "inductive_theme_accumulation_main": 135}
    for key, n in expected.items():
        assert T.SOURCES[key].expected_rows == n
        assert len(T.SOURCES[key].rows()) == n


def test_the_inventory_records_all_six_required_facts():
    for row in T.source_inventory():
        for key in ("path", "schema", "producer", "sha256", "expected_rows",
                    "coding_basis", "unit_of_analysis"):
            assert key in row, (row["key"], key)
        assert row["coding_basis"] in {"PRIMARY", "SENSITIVITY", "BOTH"}


def test_a_changed_source_is_an_error_not_a_different_answer(tmp_path):
    src = T.SOURCES["per_run_metrics"]
    tampered = T.ThematicSource(**{**src.__dict__,
                                   "expected_sha256": "0" * 64})
    report = tampered.verify()
    assert not report["ok"]
    assert any("sha256" in p for p in report["problems"])


def test_no_metric_is_implemented_without_its_five_contract_fields():
    for spec in T.METRIC_SPECS.values():
        assert spec.unit_of_analysis and spec.numerator and spec.denominator
        assert spec.aggregation_rule and spec.estimand
        assert spec.source_key in T.SOURCES
        if spec.golden:
            assert spec.golden in T.SOURCES


# ================================================== B3 primary vs sensitivity
def test_primary_results_are_all_primary(primary):
    assert primary
    assert {r.coding_basis for r in primary} == {T.CodingBasis.PRIMARY.value}


def test_sensitivity_results_are_all_sensitivity():
    comparisons = T.recurrence_sensitivity()
    assert comparisons
    assert all(c.primary_is_unmodified for c in comparisons)
    assert all(c.treatment == "CONTESTED_AS_PRESENT" for c in comparisons)
    ordering = T.ordering_agreement_sensitivity()
    assert ordering["coding_basis"] == T.CodingBasis.SENSITIVITY.value


def test_no_function_returns_the_two_bases_mixed(primary):
    """
    A comparison carries both, in two named fields. A RESULT list never does.
    """
    assert len({r.coding_basis for r in primary}) == 1
    c = T.recurrence_sensitivity()[0]
    assert hasattr(c, "primary_value") and hasattr(c, "sensitivity_value")
    assert not hasattr(c, "value")          # no single field to publish by accident


def test_the_sensitivity_view_never_overwrites_the_primary_number():
    primary_recurrence = {(r.condition, r.replicate_index, r.caveats[0]): r.value
                          for r in T.recurrence_across_focus_groups()}
    for c in T.recurrence_sensitivity():
        key = (c.condition, c.replicate_index, f"subtheme {c.subtheme_id}")
        assert primary_recurrence[key] == pytest.approx(c.primary_value, abs=1e-12)


def test_an_unknown_sensitivity_treatment_is_refused():
    with pytest.raises(T.ThematicError, match="unknown sensitivity treatment"):
        T.recurrence_sensitivity("SOMETHING_ELSE")


def test_the_ordering_sensitivity_refuses_to_run_if_primary_was_modified(
        monkeypatch):
    source = T.SOURCES["salience_sensitivity_final"]
    payload = dict(source.payload(), primary_unmodified=False)
    monkeypatch.setattr(type(source), "payload", lambda self: payload)
    with pytest.raises(T.ThematicError, match="MODIFIED"):
        T.ordering_agreement_sensitivity()


# ============================================ recall / precision / f1 / reach
def test_recall_keeps_its_numerator_and_denominator(primary):
    rows = {r["physical_run"]: r for r in T.load_per_run_metrics()}
    for res in [r for r in primary if r.metric_id == "tier1_subtheme_recall"]:
        assert res.numerator is not None and res.denominator is not None
        assert res.value == pytest.approx(res.numerator / res.denominator, abs=1e-12)
    assert len(rows) == 30


def test_precision_with_a_zero_denominator_is_undefined_not_perfect():
    """A run that produced no subtheme is not precise; it is unmeasured."""
    row = dict(T.load_per_run_metrics()[0],
               synthetic_present_n="0", shared_n="0")
    res = T.precision_results([row])[0]
    assert res.value is None
    assert res.denominator == 0        # the count is recorded; the ratio is not
    assert any("UNDEFINED, not zero" in c for c in res.caveats)


def test_recall_with_a_zero_human_denominator_is_undefined():
    row = dict(T.load_per_run_metrics()[0], human_present_n="0", shared_n="0")
    res = T.recall_results([row])[0]
    assert res.value is None
    assert any("undefined, not zero" in c for c in res.caveats)


def test_no_none_is_ever_read_as_zero(primary):
    undefined = [r for r in primary if r.value is None]
    assert 0 not in [r.value for r in undefined]
    cells = T.aggregate_thematic_focus_group_condition(primary)
    for cell in cells:
        valid = [v for v in cell.summary.values if v is not None]
        assert cell.summary.n_valid == len(valid)
        if valid:
            assert cell.summary.mean == pytest.approx(statistics.mean(valid),
                                                      abs=1e-12)


def test_f1_is_computed_from_counts_because_rounded_inputs_do_not_reproduce():
    """
    `per_run_metrics.csv` stores f1 rounded to 4dp; `primary_effects_by_fg.csv` stores
    it computed at full precision. They differ in the fourth decimal for fg2, and only
    the count-based computation matches the published table.
    """
    golden = {(r["fg"], cond): [float(r[f"{pfx}_r{k}"]) for k in (1, 2, 3)]
              for r in _csv(RESULTS / "primary_effects_by_fg.csv")
              if r["metric"] == "f1_secondary"
              for cond, pfx in (("enriched", "enriched"),
                                ("demographics-only", "demographics_only"))}
    mine = {}
    for res in T.f1_results():
        mine.setdefault((res.focus_group, res.condition), {})[
            res.replicate_index] = res.value

    disagreements = 0
    for (fg, cond), want in golden.items():
        got = mine[(fg, cond)]
        for i, k in enumerate((1, 2, 3)):
            assert round(got[k], 4) == round(want[i], 4), (fg, cond, k)
        stored = [float(r["tier1_f1_secondary"])
                  for r in T.load_per_run_metrics()
                  if r["fg"] == fg and r["condition"] == cond]
        disagreements += sum(1 for i in range(3)
                             if round(sorted(stored)[i], 4) != round(
                                 sorted(want)[i], 4))
    assert disagreements > 0, ("the rounding discrepancy this test guards against "
                               "has disappeared; re-check which artefact changed")


def test_the_two_reach_estimands_are_different_numbers(primary):
    general = {(r.condition, r.focus_group, r.replicate_index): r
               for r in primary if r.metric_id == "tier1_participant_reach"}
    shared = {(r.condition, r.focus_group, r.replicate_index): r
              for r in primary
              if r.metric_id == "tier1_participant_reach_shared_only"}
    assert set(general) == set(shared)
    assert any(general[k].value != shared[k].value for k in general)
    # different denominators, and each says so
    for k in general:
        if general[k].denominator and shared[k].denominator:
            assert shared[k].denominator <= general[k].denominator


def test_the_two_reach_estimands_have_separate_metric_ids_and_specs():
    a = T.METRIC_SPECS["tier1_participant_reach"]
    b = T.METRIC_SPECS["tier1_participant_reach_shared_only"]
    assert a.metric_id != b.metric_id
    assert a.denominator != b.denominator
    assert "ESTIMAND 1" in a.estimand and "ESTIMAND 2" in b.estimand


def test_shared_only_reach_carries_the_paired_human_figure(primary):
    shared = [r for r in primary
              if r.metric_id == "tier1_participant_reach_shared_only"]
    assert all(any("paired human reach" in c for c in r.caveats) for r in shared)


# ======================================================== replicate integrity
def test_run04_is_replicate_two_and_the_index_is_read_not_inferred(primary):
    rows = {r["physical_run"]: r for r in T.load_per_run_metrics()}
    assert rows["macho_meals_fg4_run04"]["canonical_replication_index"] == "2"
    assert rows["macho_meals_fg5_run04"]["canonical_replication_index"] == "3"
    assert "macho_meals_fg4_run02" not in rows
    fg4 = sorted(r.replicate_index for r in primary
                 if r.metric_id == "tier1_subtheme_recall"
                 and r.focus_group == "fg4" and r.condition == "enriched")
    assert fg4 == [1, 2, 3]


def test_every_cell_has_exactly_three_runs(primary):
    for cell in T.aggregate_thematic_focus_group_condition(primary):
        assert len(cell.replicate_indices) == 3
        assert sorted(cell.replicate_indices) == list(REPLICATES)
        assert cell.summary.n_expected == 3


def test_there_are_three_study_replicates_of_five_focus_groups(primary):
    reps = T.aggregate_thematic_study_replicates(primary)
    recall = [r for r in reps if r.metric_id == "tier1_subtheme_recall"]
    assert len(recall) == 6                       # 2 conditions x 3 replicates
    for r in recall:
        assert r.fgs_included == list(FGS)
        assert r.summary.n_valid == r.summary.n_expected == 5
    assert sorted({r.replicate_index for r in recall}) == list(REPLICATES)


def test_a_study_replicate_is_not_described_as_a_shared_seed(primary):
    rep = T.aggregate_thematic_study_replicates(primary)[0]
    assert "does not imply a shared seed" in rep.note


def test_the_fifteen_sessions_of_a_condition_are_never_pooled(primary):
    reps = [r for r in T.aggregate_thematic_study_replicates(primary)
            if r.metric_id == "tier1_subtheme_recall" and r.condition == "enriched"]
    assert all(r.summary.n_expected == 5 for r in reps)
    assert 15 not in [r.summary.n_expected for r in reps]


# =============================================== golden reproduction (route A/B)
@pytest.mark.parametrize("metric,column", [
    ("tier1_subtheme_recall", "recall"),
    ("tier1_matched_theme_precision", "precision"),
    ("tier1_participant_reach", "reach"),
    ("tier1_f1_secondary", "f1_secondary"),
])
def test_route_a_reproduces_primary_effects_by_fg(primary, metric, column):
    golden = {r["fg"]: r for r in _csv(RESULTS / "primary_effects_by_fg.csv")
              if r["metric"] == column}
    cells = {(c.focus_group, c.condition): c
             for c in T.aggregate_thematic_focus_group_condition(primary)
             if c.metric_id == metric}
    for fg, row in golden.items():
        for cond, pfx in (("enriched", "enriched"),
                          ("demographics-only", "demographics_only")):
            got = cells[(fg, cond)]
            assert round(got.summary.mean, 4) == round(float(row[f"{pfx}_mean"]), 4)
            for i, k in enumerate((1, 2, 3)):
                assert round(got.summary.values[i], 4) == \
                    round(float(row[f"{pfx}_r{k}"]), 4), (metric, fg, cond, k)


@pytest.mark.parametrize("metric,column", [
    ("tier1_subtheme_recall", "recall_mean_across_5_fgs"),
    ("tier1_matched_theme_precision", "precision_mean_across_5_fgs"),
    ("tier1_participant_reach", "reach_mean"),
])
def test_route_b_reproduces_study_replication_summary(primary, metric, column):
    golden = {(r["condition"], int(r["study_replicate"])): r
              for r in _csv(RESULTS / "study_replication_summary.csv")}
    mine = {(r.condition, r.replicate_index): r
            for r in T.aggregate_thematic_study_replicates(primary)
            if r.metric_id == metric}
    assert len(mine) == 6
    for key, row in golden.items():
        assert round(mine[key].summary.mean, 4) == round(float(row[column]), 4), key


def test_the_two_f1_goldens_disagree_and_the_module_follows_the_counts():
    """
    `primary_effects_by_fg.csv` computes f1 from full-precision inputs;
    `study_replication_summary.csv` averages the 4dp values stored in
    `per_run_metrics.csv`. In demographics-only replicate 2 the two frozen artefacts
    differ by 1e-4. The module follows the counts - the definition - and this test
    pins BOTH sides of the discrepancy so it cannot be mistaken for a regression.
    """
    golden = {(r["condition"], int(r["study_replicate"])):
              float(r["f1_secondary_mean"])
              for r in _csv(RESULTS / "study_replication_summary.csv")}
    mine = {(r.condition, r.replicate_index): r.summary.mean
            for r in T.aggregate_thematic_study_replicates(T.f1_results())}

    stored = {}
    for r in T.load_per_run_metrics():
        stored.setdefault((r["condition"], int(r["canonical_replication_index"])),
                          []).append(float(r["tier1_f1_secondary"]))

    off_by_one_ulp = []
    for key, want in golden.items():
        # the frozen route B number IS the mean of the rounded per-run values
        assert round(statistics.mean(stored[key]), 4) == round(want, 4), key
        if round(mine[key], 4) != round(want, 4):
            assert abs(mine[key] - want) < 1.5e-4, key
            off_by_one_ulp.append(key)
    assert off_by_one_ulp == [("demographics-only", 2)], off_by_one_ulp


def test_route_a_range_reproduces_per_group_condition_summary(primary):
    golden = {(r["fg"], r["condition"]): r
              for r in _csv(RESULTS / "per_group_condition_summary.csv")}
    cells = {(c.focus_group, c.condition): c
             for c in T.aggregate_thematic_focus_group_condition(primary)
             if c.metric_id == "tier1_subtheme_recall"}
    for key, row in golden.items():
        got = cells[key]
        assert round(got.summary.minimum, 4) == round(float(row["recall_min"]), 4)
        assert round(got.summary.maximum, 4) == round(float(row["recall_max"]), 4)
        assert got.summary.n_valid == int(row["n_replicates"])


def test_recurrence_reproduces_the_frozen_original_column():
    golden = {(r["condition"], r["canonical_replication_index"], r["subtheme_id"]):
              int(r["n_fgs_original"])
              for r in T.SOURCES["across_group_recurrence_sensitivity"].rows()}
    mine = {}
    for r in T.recurrence_across_focus_groups():
        subtheme = r.caveats[0].removeprefix("subtheme ")
        k = "" if r.replicate_index is None else str(r.replicate_index)
        mine[(r.condition, k, subtheme)] = r.numerator
    assert len(golden) == 77
    assert mine == golden


def test_salience_route_a_reproduces_the_frozen_by_fg_table():
    golden = {(r["fg"], r["condition"]): r
              for r in T.SOURCES["salience_hierarchy_by_fg_condition"].rows()}
    n_undefined_cells = 0
    for row in T.salience_ordering_by_focus_group():
        want = golden[(row["focus_group"], row["condition"])]
        assert row["n_defined"] == int(want["n_defined"])
        if row["n_defined"] == 0:
            # fg4 demographics-only: no run has a defined tau-b. The frozen table
            # leaves the cell EMPTY and so does this module - not 0.0.
            n_undefined_cells += 1
            assert row["median"] is None
            assert want["median_kendall_tau_b"] == ""
            continue
        for mine_key, want_key in (("median", "median_kendall_tau_b"),
                                   ("minimum", "min_kendall_tau_b"),
                                   ("maximum", "max_kendall_tau_b")):
            assert round(row[mine_key], 4) == round(float(want[want_key]), 4), \
                (row["focus_group"], row["condition"], mine_key)
    assert n_undefined_cells == 1


# ============================================================ salience labelling
def test_recurrence_and_reach_are_kept_apart():
    rec = T.METRIC_SPECS["theme_recurrence_across_groups"]
    assert "focus group" in rec.denominator.lower()
    assert "not across participants" in \
        T.recurrence_across_focus_groups()[0].caveats[1]
    reach = T.METRIC_SPECS["tier1_participant_reach"]
    assert "subtheme" in reach.denominator


def test_ordering_agreement_has_a_readable_label_and_keeps_the_statistic_in_metadata():
    row = T.salience_ordering_agreement()[0]
    assert row["label"] == "Agreement in thematic ordering"
    assert row["metadata"]["statistic"] == "Kendall tau-b"
    assert "NOT 'no themes in common'" in row["metadata"]["zero_means"]


def test_an_undefined_ordering_run_is_not_reported_as_agreement_of_zero():
    rows = T.salience_ordering_agreement()
    undefined = [r for r in rows if r["value"] is None]
    for r in undefined:
        assert r["undefined_reason"]
    by_fg = {(r["focus_group"], r["condition"]): r
             for r in T.salience_ordering_by_focus_group()}
    for cell in by_fg.values():
        assert cell["n_defined"] <= cell["n_replicates"]
    # at least one cell in the frozen corpus really is short of three
    assert any(c["n_defined"] < c["n_replicates"] for c in by_fg.values())


def test_ordering_agreement_is_exploratory_despite_reproducing_exactly():
    """The arithmetic checks out; the instrument is still not validated."""
    row = T.salience_ordering_agreement()[0]
    assert row["calculation_status"] == CalculationStatus.EXPLORATORY.value
    assert row["verification"] == T.Verification.READ_FROM_FROZEN_ARTIFACT.value


# ============================================================= B5 accumulation
def test_accumulation_covers_the_three_conditions_and_five_positions():
    curves = T.accumulation_curves()
    assert {c.condition for c in curves} == {"human", "enriched",
                                             "demographics-only"}
    for c in curves:
        assert c.positions == list(T.ACCUMULATION_POSITIONS)
        assert len(c.values) == 5


def test_the_synthetic_conditions_summarise_three_realisations():
    by_condition = {c["condition"]: c for c in T.accumulation_by_condition()}
    for condition in ("enriched", "demographics-only"):
        row = by_condition[condition]
        assert row["n_realisations"] == 3
        assert sorted(row["realisations"]) == ["R1", "R2", "R3"]
        assert not row["single_realisation"]
        for p in row["per_position"]:
            assert p["n_realisations"] == 3
            assert p["minimum"] <= p["mean"] <= p["maximum"]
    human = by_condition["human"]
    assert human["n_realisations"] == 1 and human["single_realisation"]


def test_accumulation_is_monotonic_within_every_sequence():
    for c in T.accumulation_curves():
        for earlier, later in zip(c.values, c.values[1:]):
            assert later >= earlier - 1e-9, (c.condition, c.realisation, c.values)
        assert c.values[-1] == pytest.approx(100.0, abs=1e-6)


def test_accumulation_does_not_claim_the_categories_are_the_same():
    row = T.accumulation_by_condition()[0]
    assert "does not imply the same categories" in row["repertoire_note"]
    assert row["calculation_status"] == CalculationStatus.DERIVED_FROM_FROZEN.value


# ============================================================== B6 deferrals
def test_guide_coverage_is_deferred_and_not_inferred():
    status = T.guide_coverage_status()
    assert status["status"] == "DEFERRED_NOT_IMPLEMENTED"
    assert status["reason"]
    assert any("NOT inferred from thematic recall" in s
               for s in status["explicitly_not_done"])
    assert status["blocks_other_metrics"] is False


def test_a_deferred_metric_has_no_builder_and_says_so():
    assert "guide_coverage" not in T.PRIMARY_BUILDERS
    with pytest.raises(T.ThematicError, match="no primary builder"):
        T.primary_results(["guide_coverage"])


def test_deferring_one_metric_does_not_block_the_others(primary):
    assert len(T.implemented_metrics()) >= 7
    assert T.deferred_metrics() == ["guide_coverage"]
    assert len(primary) == 150


# ================================================== offline and non-destructive
def test_the_module_imports_nothing_that_could_reach_the_network():
    source = (T.__file__)
    text = open(source, encoding="utf-8").read()
    for forbidden in ("import requests", "import httpx", "import socket",
                      "import urllib", "from urllib", "anthropic", "google.genai",
                      "openai", "subprocess", "http.client"):
        assert forbidden not in text, forbidden


def test_no_network_module_is_loaded_by_importing_thematic():
    for module in ("requests", "httpx", "anthropic", "openai"):
        assert module not in sys.modules, module


def test_running_the_whole_layer_modifies_no_frozen_artefact():
    def digests():
        return {k: hashlib.sha256(s.path.read_bytes()).hexdigest()
                for k, s in T.SOURCES.items()}

    before = digests()
    results = T.primary_results()
    T.aggregate_thematic_focus_group_condition(results)
    T.aggregate_thematic_study_replicates(results)
    T.recurrence_across_focus_groups()
    T.salience_ordering_agreement()
    T.salience_ordering_by_focus_group()
    T.recurrence_sensitivity()
    T.recurrence_sensitivity("COMBINED")
    T.ordering_agreement_sensitivity()
    T.accumulation_curves()
    T.accumulation_by_condition()
    assert digests() == before


def test_every_result_carries_the_hash_of_the_artefact_it_came_from(primary):
    for r in primary:
        assert len(r.source_hash) == 64
        assert r.source_artifact.endswith(".csv")
        assert r.aggregation_version
