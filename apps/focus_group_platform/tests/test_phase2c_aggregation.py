"""
Phase 2B.1 normalisation hardening and Phase 2C structural aggregation.

Golden sources for Level 2 are the three structural artefacts only:
  * structural_interaction_metrics_long.csv
  * structural_distributions_long.csv
  * FINAL_RESULTS_TABLES.xlsx sheet 3_Structural_Interaction

`primary_effects_by_fg.csv` is deliberately NOT used: it is thematic fidelity, not
structural interaction.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from platform_core import aggregate as A
from platform_core import frozen, transcripts

REPO = Path(__file__).resolve().parents[3]
XLSX = REPO / "analysis/production_evaluation/final/FINAL_RESULTS_TABLES.xlsx"
STRUCT_SHEET_METRICS = ["total_words", "participant_turns", "words_per_turn_iqr",
                        "short_turn_proportion_25w", "turn_balance_gini",
                        "chain_depth", "moderator_word_share"]


@pytest.fixture(scope="module")
def rows():
    return A.load_frozen_metric_rows()


def _synthetic_entry(idx=0, **over):
    e = {"turn": idx, "speaker_id": "P1", "speaker_name": "A", "content": "hello",
         "timestamp": "t", "selection_mode": "m"}
    e.update(over)
    return e


def _human_entry(idx=0, **over):
    e = {"turn": idx, "speaker_id": "P1", "speaker_name": "A", "content": "hello",
         "canonical_speaker_id": "P1", "speaker_role": "participant"}
    e.update(over)
    return e


# ==================================================== 2B.1 per-entry validation
def test_missing_required_field_in_a_single_entry_is_rejected(tmp_path):
    entries = [_synthetic_entry(i) for i in range(5)]
    del entries[3]["selection_mode"]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(transcripts.TranscriptError, match="entry 3"):
        transcripts.normalise_transcript(p, transcript_type="synthetic")


def test_a_schema_mix_after_entry_50_is_caught(tmp_path):
    """A sampled detector reads the first 50 and misses this."""
    entries = [_synthetic_entry(i) for i in range(60)]
    entries[55] = _human_entry(55)
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(transcripts.SchemaDetectionError, match="mixed"):
        transcripts.normalise_transcript(p, transcript_type="synthetic")


def test_non_mapping_entry_after_50_is_caught(tmp_path):
    entries = [_synthetic_entry(i) for i in range(60)]
    entries[57] = "not a mapping"
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(transcripts.SchemaDetectionError, match="entry 57"):
        transcripts.normalise_transcript(p, transcript_type="synthetic")


@pytest.mark.parametrize("bad", ["Human", "SYNTHETIC", "hybrid", "", None, "humans"])
def test_invalid_transcript_type_is_rejected(tmp_path, bad):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([_synthetic_entry()]), encoding="utf-8")
    with pytest.raises(transcripts.TranscriptError, match="transcript_type"):
        transcripts.normalise_transcript(p, transcript_type=bad)


def test_duplicate_turn_ids_are_reported_not_renumbered(tmp_path):
    entries = [_synthetic_entry(0), _synthetic_entry(1), _synthetic_entry(1)]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    t = transcripts.normalise_transcript(p, transcript_type="synthetic")
    assert t.normalisation.duplicate_original_turn_ids == ["1"]
    assert [turn.original_turn_id for turn in t.turns] == [0, 1, 1]
    assert any(r.kind == "DUPLICATE_TURN_ID" for r in t.review_items)


def test_missing_turn_ids_are_counted(tmp_path):
    entries = [_synthetic_entry(0), _synthetic_entry(None), _synthetic_entry(2)]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    t = transcripts.normalise_transcript(p, transcript_type="synthetic")
    assert t.normalisation.missing_original_turn_ids == 1


def test_empty_interventions_are_counted_and_retained(tmp_path):
    entries = [_synthetic_entry(0), _synthetic_entry(1, content="   "),
               _synthetic_entry(2, content=""), _synthetic_entry(3)]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    t = transcripts.normalise_transcript(p, transcript_type="synthetic")
    acc = t.normalisation.empty_entries
    assert acc.found == 2
    assert acc.retained_in_canonical == 2
    assert acc.excluded_by_producer_rule == 2
    assert acc.turn_ids == ["t0001", "t0002"]
    assert len(t.turns) == 4                      # retained, not silently dropped
    assert "blind_included_entries" in acc.rule
    assert any("empty intervention" in w for w in t.normalisation.warnings)


def test_entry_count_is_recorded(tmp_path):
    entries = [_synthetic_entry(i) for i in range(7)]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    t = transcripts.normalise_transcript(p, transcript_type="synthetic")
    assert t.normalisation.n_entries == 7


def test_original_ids_survive_as_provenance(tmp_path):
    entries = [_synthetic_entry(41), _synthetic_entry(42)]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    t = transcripts.normalise_transcript(p, transcript_type="synthetic")
    assert [turn.original_turn_id for turn in t.turns] == [41, 42]
    assert all(turn.provenance.source_field_map["original_turn_id"] == "turn"
               for turn in t.turns)


# =========================================== 2B.1 manifest terminology
def test_manifest_terminology_distinguishes_three_counts():
    m = frozen.load_manifest()
    protected_paths = len(m.entries)
    acceptance_entries = len(m.acceptance_paths)
    sessions = [e for e in m.entries
                if e.kind == "synthetic_session" and e.acceptance]
    humans = [e for e in m.entries if e.kind == "human_transcript_set"]
    analytic_documents = len(sessions) + len(humans)

    assert protected_paths == 77          # protected artefacts / paths
    assert acceptance_entries == 65       # acceptance ENTRIES, not transcripts
    assert analytic_documents == 35       # 5 human + 30 synthetic
    assert len(humans) == 5 and len(sessions) == 30
    # the 30 comparable windows are views of the same 30 sessions, not extra documents
    assert len([e for e in m.entries if e.kind == "comparable_window"]) == 30


# ================================================ 2C integrity and coverage
def test_frozen_corpus_passes_integrity(rows):
    """Coverage is now per metric (2C.1); the corpus must be clean for all of them."""
    report = A.check_integrity(rows)
    assert report.complete, report.problems()
    for cov in report.per_metric.values():
        assert cov.cells_present == cov.cells_expected == 30
        assert not cov.duplicate_same_run
        assert not cov.collision_different_runs
        assert not cov.missing_units


def test_replicate_index_is_read_not_inferred(rows):
    km = A.replicate_index_map(rows)
    assert km["macho_meals_fg4_run04"] == 2
    assert km["macho_meals_fg4_run03"] == 3
    assert km["macho_meals_fg5_run04"] == 3
    assert km["macho_meals_fg5_run03"] == 2
    assert len(km) == 30


def test_run04_is_included_for_fg4_and_fg5(rows):
    runs = {r.physical_run for r in rows if r.side == "synthetic"}
    assert "macho_meals_fg4_run04" in runs
    assert "macho_meals_fg5_run04" in runs
    assert "macho_meals_fg4_run02" not in runs
    assert "macho_meals_fg5_run02" not in runs


def test_duplicate_cell_is_detected():
    """Superseded in detail by test_phase2c1: same-run vs different-run are split."""
    base = A.RunRow("r1", "synthetic", "enriched", "fg1", 1, "total_words", 10.0)
    dup = A.RunRow("r2", "synthetic", "enriched", "fg1", 1, "total_words", 11.0)
    cov = A.check_integrity([base, dup]).for_metric("total_words")
    assert cov.collision_different_runs
    assert cov.collision_different_runs[0]["runs"] == ["r1", "r2"]


def test_incomplete_coverage_is_named():
    rows = [A.RunRow(f"r{k}", "synthetic", "enriched", "fg1", k, "total_words", 1.0)
            for k in (1, 2)]
    cov = A.check_integrity(rows).for_metric("total_words")
    assert not cov.complete
    assert "enriched|fg1|r3" in cov.missing_units
    assert "demographics-only|fg1|r1" in cov.missing_units


def test_unknown_condition_or_replicate_raises():
    with pytest.raises(A.AggregationError, match="unknown condition"):
        A.check_integrity([A.RunRow("r", "synthetic", "other", "fg1", 1, "m", 1.0)])
    with pytest.raises(A.AggregationError, match="outside"):
        A.check_integrity([A.RunRow("r", "synthetic", "enriched", "fg1", 9, "m", 1.0)])


def test_aggregators_default_to_strict_on_the_frozen_corpus(rows):
    """The frozen corpus is complete, so STRICT (the default) succeeds."""
    assert A.aggregate_focus_group_condition(rows, ["total_words"])
    assert A.aggregate_study_replicates(rows, ["total_words"])


# ============================================= 2C route A: FG x condition
def test_focus_group_condition_cells_have_three_runs(rows):
    cells = A.aggregate_focus_group_condition(rows, ["total_words"])
    assert len(cells) == 10                       # 5 FGs x 2 conditions
    for c in cells:
        assert len(c.runs) == 3
        assert c.summary.n_expected == 3
        assert c.summary.n_valid == 3
        assert c.summary.complete
        assert c.human_value is not None          # the paired human referent
        assert c.summary.minimum <= c.summary.mean <= c.summary.maximum


def test_cell_reports_individual_values_and_range(rows):
    cell = next(c for c in A.aggregate_focus_group_condition(rows, ["chain_depth"])
                if c.focus_group == "fg1" and c.condition == "enriched")
    assert len(cell.summary.values) == 3
    assert cell.summary.minimum is not None and cell.summary.maximum is not None
    assert cell.summary.sd is not None


# =========================================== 2C route B: study replicates
def test_three_study_replicates_of_five_focus_groups(rows):
    reps = A.aggregate_study_replicates(rows, ["total_words"])
    assert len(reps) == 6                          # 3 replicates x 2 conditions
    for r in reps:
        assert sorted(r.fgs_included) == list(A.FGS)
        assert r.summary.n_expected == 5
        assert r.summary.n_valid == 5
        assert len(r.runs) == 5


def test_study_replicate_two_of_enriched_uses_run04_for_fg4(rows):
    rep = next(r for r in A.aggregate_study_replicates(rows, ["total_words"])
               if r.condition == "enriched" and r.replicate_index == 2)
    assert "macho_meals_fg4_run04" in rep.runs
    assert "macho_meals_fg5_run03" in rep.runs


def test_study_level_summarises_three_replicates_not_fifteen_sessions(rows):
    summaries = A.summarise_study_level(rows, ["total_words"])
    assert len(summaries) == 2
    for s in summaries:
        assert len(s.replicate_means) == 3
        assert s.across_replicates.n_expected == 3
        assert s.human_reference.n_expected == 5
        assert "never pooled" in s.note or "not paired seeds" in s.note


def test_flat_pooling_of_fifteen_sessions_is_never_produced(rows):
    """No summary anywhere is computed over 15 values."""
    for s in A.summarise_study_level(rows, ["total_words"]):
        assert s.across_replicates.n_expected == 3
    for r in A.aggregate_study_replicates(rows, ["total_words"]):
        assert r.summary.n_expected == 5
    for c in A.aggregate_focus_group_condition(rows, ["total_words"]):
        assert c.summary.n_expected == 3


# ================================================== nulls and denominators
def test_null_reduces_n_and_never_becomes_zero():
    s = A.summarise([1.0, None, 3.0], n_expected=3)
    assert s.n_valid == 2 and s.n_expected == 3
    assert s.mean == 2.0                       # not (1+0+3)/3
    assert not s.complete
    assert "not imputed" in s.undefined_reason
    assert s.values[1] is None


def test_all_null_is_undefined_not_zero():
    s = A.summarise([None, None, None], n_expected=3)
    assert s.mean is None and s.median is None
    assert s.n_valid == 0
    assert "not zero" in s.undefined_reason


def test_every_summary_reports_its_n(rows):
    for c in A.aggregate_focus_group_condition(rows, ["reference_density"]):
        assert c.summary.n_expected == 3
        assert isinstance(c.summary.n_valid, int)


def test_ratio_metrics_declare_their_aggregation_rule(rows):
    for c in A.aggregate_focus_group_condition(rows, ["moderator_word_share"]):
        assert c.aggregation_rule == "ratio_no_pooling"
        assert c.summary.aggregation_rule == "ratio_no_pooling"
    for c in A.aggregate_focus_group_condition(rows, ["total_words"]):
        assert c.aggregation_rule == "mean_of_values"


def test_every_metric_has_a_declared_rule(rows):
    metric_ids = {r.metric_id for r in rows
                  if r.metric_id in A.AGGREGATION_RULE}
    assert metric_ids
    for m in metric_ids:
        assert A.AGGREGATION_RULE[m] in ("mean_of_values", "ratio_no_pooling")


# ============================================== distributions, three steps
def test_location_summary_is_three_steps_not_a_pool():
    """
    The location summary survives, renamed. The distribution AGGREGATORS that replace
    it are tested in test_phase2c1_coverage_and_distributions.py.
    """
    rows = A.load_frozen_distributions()
    out = A.summarise_distribution_location(rows, "words_per_turn")
    assert len(out["step_1_within_run"]) == 30           # one value per run
    assert len(out["step_2_within_cell"]) == 10          # 5 FGs x 2 conditions
    assert set(out["step_3_across_focus_groups"]) == set(A.CONDITIONS)
    for c in out["step_3_across_focus_groups"].values():
        assert c["n_focus_groups"] == 5
    assert "never pooled" in out["rule"]
    assert "NOT the" in out["what_this_is"]


@pytest.mark.parametrize("distribution_id", A.DISTRIBUTION_IDS)
def test_every_frozen_distribution_has_a_location_summary(distribution_id):
    rows = A.load_frozen_distributions()
    out = A.summarise_distribution_location(rows, distribution_id)
    assert out["step_1_within_run"]
    assert len(out["step_2_within_cell"]) == 10


# ====================================== golden: the frozen structural sheet
def _xlsx_structural_rows() -> dict[str, dict[str, float]]:
    z = zipfile.ZipFile(XLSX)
    xml = z.read("xl/worksheets/sheet4.xml").decode("utf-8", "replace")
    out: dict[str, dict[str, float]] = {}
    for raw in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
        cells = [(t[0] or t[1] or t[2]) for t in
                 re.findall(r"<is><t[^>]*>(.*?)</t></is>|<t[^>]*>(.*?)</t>|<v>(.*?)</v>",
                            raw)]
        if len(cells) >= 5 and cells[0] in STRUCT_SHEET_METRICS:
            out[cells[0]] = {"human_mean": float(cells[1]),
                             "enriched_mean": float(cells[2]),
                             "demographics_only_mean": float(cells[3]),
                             "n_fg_enriched_closer_to_human": cells[5]}
    return out


@pytest.mark.parametrize("metric_id", STRUCT_SHEET_METRICS)
def test_structural_sheet_is_reproduced(rows, metric_id):
    frozen_sheet = _xlsx_structural_rows()
    assert metric_id in frozen_sheet, f"{metric_id} absent from the workbook sheet"
    mine = {r["metric"]: r for r in A.frozen_workbook_route(rows,
                                                            STRUCT_SHEET_METRICS)}
    got, want = mine[metric_id], frozen_sheet[metric_id]
    for key in ("human_mean", "enriched_mean", "demographics_only_mean"):
        assert round(got[key], 4) == round(want[key], 4), (metric_id, key)
    assert got["n_fg_enriched_closer_to_human"] == \
        want["n_fg_enriched_closer_to_human"]
    assert got["n_fgs"] == 5


def test_the_workbook_route_is_not_the_study_replicate_route(rows):
    """
    The workbook means the three runs per cell, then the five cells. Route B groups
    run k across the five FGs. They answer different questions and are reported
    separately rather than reconciled.
    """
    workbook = {r["metric"]: r for r in
                A.frozen_workbook_route(rows, ["total_words"])}["total_words"]
    study = [s for s in A.summarise_study_level(rows, ["total_words"])
             if s.condition == "enriched"][0]
    assert workbook["enriched_mean"] == pytest.approx(
        study.across_replicates.mean, abs=1e-9)
    # identical for a plain mean, but the n differs - and n is what is reported
    assert study.across_replicates.n_expected == 3
    assert workbook["n_fgs"] == 5


def test_primary_effects_is_not_used_as_a_level2_golden_source():
    src = Path(__file__).read_text(encoding="utf-8")
    assert "primary_effects_by_fg" in src            # named only to exclude it
    assert "primary_effects_by_fg.csv\"" not in src.replace(
        "`primary_effects_by_fg.csv`", "")
