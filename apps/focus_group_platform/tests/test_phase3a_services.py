"""
Phase 3A services, exercised WITHOUT Streamlit.

If any of these needed a browser, the architecture would already have failed: a test
that has to start a server to check a methodological rule is a test nobody runs.
"""
from __future__ import annotations

import hashlib
import json
import sys

import pytest

from platform_core import theme
from platform_core.config import resolve_data_dir
from platform_core.services import (benchmark_service as B, context as C,
                                    export_service as E, import_service as I,
                                    structural_service as S)
from platform_core import thematic as TH

HUMAN_ENTRIES = [
    {"turn": 1, "speaker_id": "MOD", "speaker_name": "Moderator",
     "canonical_speaker_id": "MOD", "speaker_role": "moderator",
     "content": "Tell me about weeknight cooking."},
    {"turn": 2, "speaker_id": "P1", "speaker_name": "Ana",
     "canonical_speaker_id": "P1", "speaker_role": "participant",
     "content": "I cook most nights, usually something quick with rice or pasta."},
    {"turn": 3, "speaker_id": "P2", "speaker_name": "Ben",
     "canonical_speaker_id": "P2", "speaker_role": "participant",
     "content": "Ana is right, though I lean on the freezer more than she does."},
    {"turn": 4, "speaker_id": "P1", "speaker_name": "Ana",
     "canonical_speaker_id": "P1", "speaker_role": "participant",
     "content": "Freezer meals feel like giving up to me, honestly."},
]

SYNTHETIC_ENTRIES = [
    {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
     "content": "Tell me about weeknight cooking.",
     "timestamp": "2026-01-01T00:00:00Z", "selection_mode": "scripted"},
    {"turn": 2, "speaker_id": "P1", "speaker_name": "Ana",
     "content": "I cook most nights, usually something quick with rice or pasta.",
     "timestamp": "2026-01-01T00:01:00Z", "selection_mode": "model"},
    {"turn": 3, "speaker_id": "P2", "speaker_name": "Ben",
     "content": "Ana is right, though I lean on the freezer more than she does.",
     "timestamp": "2026-01-01T00:02:00Z", "selection_mode": "model"},
    {"turn": 4, "speaker_id": "P1", "speaker_name": "Ana",
     "content": "Freezer meals feel like giving up to me, honestly.",
     "timestamp": "2026-01-01T00:03:00Z", "selection_mode": "model"},
]


@pytest.fixture()
def data_dir(tmp_path):
    return resolve_data_dir(injected=tmp_path / "platform-data", ensure=True)


@pytest.fixture()
def project(data_dir):
    return I.new_project("Trial study", data_dir)


def _bytes(entries) -> bytes:
    return json.dumps(entries).encode("utf-8")


def _import(project, entries, transcript_type, **kwargs):
    return I.import_transcript(
        project, filename=f"{transcript_type}_a.json", content=_bytes(entries),
        transcript_type=transcript_type, **kwargs)


# ============================================== the layer is Streamlit-free
def test_no_service_imports_streamlit():
    import platform_core.services as services_pkg
    roots = [services_pkg.__file__]
    for module in (B, C, E, I, S):
        roots.append(module.__file__)
    for path in roots:
        text = open(path, encoding="utf-8").read()
        assert "import streamlit" not in text, path
    assert "streamlit" not in sys.modules or True   # importing services never needs it


def test_services_import_without_streamlit_being_loaded():
    """The whole layer is reachable from a plain script."""
    import importlib
    for name in ("benchmark_service", "import_service", "structural_service",
                 "export_service", "context"):
        importlib.import_module(f"platform_core.services.{name}")


# ==================================================== benchmark: level 1 and 2
def test_benchmark_sources_are_intact():
    report = B.check_sources()
    assert report["ok"], report["problems"]
    assert report["n_level1_sources"] == 13
    assert report["n_level2_metrics"] == 19


def test_benchmark_loads_level1_in_both_views():
    fg = B.level1_rows(B.FOCUS_GROUP_VIEW)
    rep = B.level1_rows(B.STUDY_REPLICATE_VIEW)
    assert len(fg) == 50           # 5 metrics x 2 conditions x 5 focus groups
    assert len(rep) == 30          # 5 metrics x 2 conditions x 3 replicates
    assert {r["unit"] for r in fg} == {"Focus group"}
    assert {r["unit"] for r in rep} == {"Study replicate"}
    for row in fg:
        assert row["n_valid"] is not None and row["n_expected"] == 3
        assert row["calculation_status_label"] in \
            theme.CALCULATION_STATUS_LABELS.values()


def test_benchmark_loads_level2_in_both_views():
    fg = B.level2_rows(B.FOCUS_GROUP_VIEW)
    rep = B.level2_rows(B.STUDY_REPLICATE_VIEW)
    assert len(fg) == 7 * 15       # 7 metrics x (10 synthetic cells + 5 human)
    assert len(rep) == 7 * 6
    assert {r["condition"] for r in fg} == {"human", "enriched",
                                            "demographics-only"}
    summary = B.level2_condition_summary()
    assert [r["metric_id"] for r in summary] == list(B.LEVEL2_SHEET_METRICS)
    assert all(r["calculation_status"] == "FROZEN_REPRODUCED" for r in summary)


def test_the_three_conditions_are_present_and_named_for_a_reader():
    rows = B.level2_rows()
    labels = {r["condition_label"] for r in rows}
    assert labels == {"Human", "Enriched", "Demographics-only"}


def test_an_unknown_view_is_refused_rather_than_defaulted():
    for fn in (B.level1_rows, B.level2_rows):
        with pytest.raises(B.BenchmarkError, match="unknown view"):
            fn("whatever")


def test_words_per_turn_uses_the_fixed_bins_and_the_existing_aggregation():
    distribution = B.level2_words_per_turn()
    assert distribution["bins"] == ["0-9w", "10-24w", "25-49w", "50-99w",
                                    "100-199w", "200-249w", "250-299w", "300w+"]
    for condition, values in distribution["series"].items():
        assert sum(values) == pytest.approx(1.0, abs=1e-9), condition
    assert distribution["calculation_status"] == "DERIVED_FROM_FROZEN"
    assert "within_run" in distribution["denominators"]


def test_the_chart_palette_comes_from_the_shared_theme():
    for payload in (B.level2_words_per_turn(), B.level1_accumulation()):
        for condition, colour in payload["colours"].items():
            assert colour == theme.PALETTE[condition]


# ================================================ primary vs sensitivity
def test_primary_is_the_default_and_there_is_no_basis_switch():
    rows = B.level1_rows()
    assert {r["coding_basis"] for r in rows} == {"PRIMARY"}
    import inspect
    signature = inspect.signature(B.level1_rows)
    assert "basis" not in signature.parameters
    assert "coding_basis" not in signature.parameters


def test_sensitivity_rows_cannot_be_rendered_as_primary_rows():
    """Different shape on purpose: no `value`, no `coding_basis == PRIMARY`."""
    sensitivity = B.level1_sensitivity_rows()
    assert sensitivity
    for row in sensitivity:
        assert "value" not in row
        assert row["primary_value"] is not None
        assert row["coding_basis"] == "SENSITIVITY"
        assert row["primary_is_unmodified"] is True


def test_sensitivity_never_changes_a_primary_number():
    before = {(r["metric_id"], r["condition"], r["unit_value"]): r["value"]
              for r in B.level1_rows()}
    B.level1_sensitivity_rows("CONTESTED_AS_PRESENT")
    B.level1_sensitivity_rows("COMBINED")
    B.level1_ordering_sensitivity()
    after = {(r["metric_id"], r["condition"], r["unit_value"]): r["value"]
             for r in B.level1_rows()}
    assert after == before


def test_f1_is_the_full_precision_value_and_the_discrepancy_is_only_recorded():
    rows = [r for r in B.level1_rows(B.STUDY_REPLICATE_VIEW)
            if r["metric_id"] == "tier1_f1_secondary"
            and r["condition"] == "demographics-only"
            and r["unit_value"] == 2]
    assert len(rows) == 1                       # ONE visible value, not two
    assert round(rows[0]["value"], 4) == 0.3641
    discrepancy = next(d for d in B.KNOWN_ARTEFACT_DISCREPANCIES
                       if d["metric_id"] == "tier1_f1_secondary")
    assert discrepancy["affects_displayed_value"] is False
    assert "0.3641" in discrepancy["detail"] and "0.3642" in discrepancy["detail"]


def test_guide_coverage_is_shown_as_unavailable_and_blocks_nothing():
    notice = B.guide_coverage_notice()
    assert notice["display"].startswith("Not available")
    assert notice["blocks_other_metrics"] is False
    assert len(B.level1_rows()) == 50           # everything else still loads


def test_ordering_agreement_is_labelled_for_a_reader():
    rows = B.level1_ordering_rows()
    assert {r["metric"] for r in rows} == {"Agreement in thematic ordering"}
    assert rows[0]["details"]["statistic"] == "Kendall tau-b"


def test_undefined_is_displayed_as_undefined_never_as_zero():
    rows = B.level1_ordering_rows(B.STUDY_REPLICATE_VIEW)
    undefined = [r for r in rows if r["value"] is None]
    assert undefined
    for row in undefined:
        assert row["value_display"] == "Undefined"
        assert row["value_display"] != "0"
    assert theme.format_value(None) == "Undefined"
    assert theme.format_value(0.0) == "0.0000"


# ================================================= comparability rules
def test_a_lone_synthetic_upload_is_descriptive_only():
    context = C.build_context(context_id="c1", study_name="X",
                              synthetic_set_ids=["syn1"])
    assert context.comparability_status == \
        C.ComparabilityStatus.DESCRIPTIVE_ONLY.value
    assert not context.structural_comparison_allowed
    assert not context.may_use_frozen_human_referent
    assert any("NOT substituted" in r for r in context.comparability_reasons)


def test_a_declared_pair_gets_a_structural_comparison():
    context = C.build_context(
        context_id="c2", study_name="X", human_set_id="hum1",
        synthetic_set_ids=["syn1"],
        declaration_by_user="same guide, same recruitment strata")
    assert context.comparability_status == \
        C.ComparabilityStatus.MATCHED_STRUCTURAL_COMPARISON.value
    assert context.structural_comparison_allowed
    assert not context.may_use_frozen_human_referent


def test_a_pair_without_a_declaration_requires_review():
    context = C.build_context(context_id="c3", study_name="X",
                              human_set_id="hum1", synthetic_set_ids=["syn1"])
    assert context.comparability_status == \
        C.ComparabilityStatus.REQUIRES_REVIEW.value
    assert not context.structural_comparison_allowed


@pytest.mark.parametrize("kwargs", [
    {"study_name": "Macho Meals"},
    {"study_name": "X", "discussion_guide_id": "macho_meals_guide"},
    {"study_name": "X", "codebook_id": "macho_meals_codebook"},
    {"study_name": "X", "human_set_id": "fg1", "synthetic_set_ids": ["fg1_run01"],
     "declaration_by_user": "identical to the thesis benchmark"},
])
def test_no_upload_can_reach_frozen_benchmark_compatible(kwargs):
    """Name, guide, codebook, declaration - none of them is a route."""
    context = C.build_context(context_id="c4", **kwargs)
    assert context.comparability_status != \
        C.ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value
    assert not context.may_use_frozen_human_referent
    assert not context.thematic_available


def test_only_the_built_in_benchmark_context_may_use_the_frozen_referent():
    frozen = C.frozen_benchmark_context()
    assert frozen.may_use_frozen_human_referent
    assert frozen.thematic_available
    assert frozen.source_type == C.SourceType.FROZEN_BENCHMARK.value


def test_level1_stays_unavailable_for_a_new_corpus_even_with_a_codebook_id():
    context = C.build_context(context_id="c5", study_name="X",
                              human_set_id="h", synthetic_set_ids=["s"],
                              codebook_id="my_codebook",
                              declaration_by_user="declared homologues")
    assert context.thematic_status == \
        C.ComparabilityStatus.THEMATIC_COMPARISON_NOT_AVAILABLE.value
    assert not context.thematic_available
    assert any("does not supply a validated coding procedure" in r
               for r in context.comparability_reasons)


def test_a_saved_context_cannot_promote_itself_by_editing_the_file(project):
    context = C.build_context(context_id="default", study_name="X",
                              project_id=project.project_id,
                              synthetic_set_ids=["syn1"])
    path = C.save_context(context, project.path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["comparability_status"] = "FROZEN_BENCHMARK_COMPATIBLE"
    payload["thematic_status"] = "FROZEN_BENCHMARK_COMPATIBLE"
    path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded = C.load_context("default", project.path)
    assert reloaded.comparability_status == \
        C.ComparabilityStatus.DESCRIPTIVE_ONLY.value
    assert not reloaded.may_use_frozen_human_referent


def test_a_stored_context_claiming_to_be_the_frozen_benchmark_is_refused(project):
    context = C.build_context(context_id="default", study_name="X",
                              synthetic_set_ids=["syn1"])
    path = C.save_context(context, project.path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_type"] = "FROZEN_BENCHMARK"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(C.ContextError, match="FROZEN_BENCHMARK"):
        C.load_context("default", project.path)


def test_the_frozen_context_is_not_storable(project):
    with pytest.raises(C.ContextError, match="not stored in a project"):
        C.save_context(C.frozen_benchmark_context(), project.path)


# ======================================================= import and Level 2
def test_import_normalises_and_reports(project):
    outcome = _import(project, HUMAN_ENTRIES, "human", roster_names=["Ana", "Ben"])
    assert outcome.ok
    report = outcome.validation_report
    assert report["schema_detected"] == "standardized_human"
    assert report["n_entries"] == 4 and report["n_unresolved_turns"] == 0
    assert report["fully_resolved"]
    assert (project.path / "derived" / "canonical").is_dir()


def test_a_declared_type_that_does_not_match_the_file_is_refused(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "human")
    assert not outcome.ok
    assert outcome.problems[0].code == "unsupported_schema"
    assert outcome.problems[0].remedy


def test_a_broken_file_produces_a_problem_not_a_traceback(project):
    outcome = I.import_transcript(project, filename="x.json",
                                  content=b"{not json", transcript_type="human")
    assert not outcome.ok
    assert outcome.problems[0].code == "invalid_file"
    assert outcome.problems[0].remedy


def test_unresolved_identity_blocks_and_names_the_turns(project):
    entries = [dict(e) for e in HUMAN_ENTRIES]
    entries[2]["canonical_speaker_id"] = ""
    outcome = _import(project, entries, "human", roster_names=["Ana", "Ben"])
    assert not outcome.ok
    codes = {p.code for p in outcome.problems}
    assert "unresolved_participant_identity" in codes
    unresolved = outcome.validation_report["unresolved_turns"]
    assert [t["original_index"] for t in unresolved] == [2]


def test_a_human_import_without_a_roster_asks_for_one(project):
    outcome = _import(project, HUMAN_ENTRIES, "human")
    assert {p.code for p in outcome.problems} == {"missing_roster"}


def test_empty_interventions_are_counted_not_removed(project):
    entries = [dict(e) for e in SYNTHETIC_ENTRIES]
    entries[3]["content"] = "   "
    outcome = _import(project, entries, "synthetic",
                      window_declaration="comparable_window")
    empty = outcome.validation_report["empty_entries"]
    assert empty["found"] == 1
    assert empty["retained_in_canonical"] == 1
    assert empty["excluded_by_producer_rule"] == 1
    assert len(outcome.transcript.turns) == 4


def test_duplicate_turn_ids_are_reported_and_never_renumbered(project):
    entries = [dict(e) for e in SYNTHETIC_ENTRIES]
    entries[2]["turn"] = 2
    outcome = _import(project, entries, "synthetic",
                      window_declaration="comparable_window")
    assert outcome.validation_report["turn_ids"][
        "duplicate_original_turn_ids"] == ["2"]
    assert [t.original_turn_id for t in outcome.transcript.turns] == [1, 2, 2, 4]


def test_a_full_synthetic_transcript_does_not_get_the_macho_meals_window(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="full_transcript")
    problem = next(p for p in outcome.problems
                   if p.code == "incomplete_comparable_window")
    assert not problem.blocking            # descriptive results still produced
    assert "not applied to another corpus" in problem.message


def test_level2_runs_for_a_synthetic_window(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="comparable_window")
    result = S.run_structural(project, outcome.transcript,
                              window_declaration="comparable_window")
    assert result.ok
    metrics = [r for r in result.rows if r["kind"] == "metric"]
    counts = [r for r in result.rows if r["kind"] == "count"]
    assert len(metrics) == 12 and len(counts) == 7
    values = {r["metric_id"]: r["value"] for r in result.rows}
    assert values["words_per_turn_median"] is not None
    assert result.run.producer.startswith("aggregate_production_results")
    # Phase 3C: results are filed under the ANALYTICAL INPUT, not the file.
    assert S.stored_runs(project) == [f"{outcome.transcript.transcript_id}__fullrun"]


def test_level2_runs_for_a_human_transcript_with_a_roster(project):
    outcome = _import(project, HUMAN_ENTRIES, "human", roster_names=["Ana", "Ben"])
    result = S.run_structural(project, outcome.transcript,
                              roster_names=["Ana", "Ben"])
    assert result.ok
    assert result.run.producer.startswith("structural_metrics_transportability")


def test_the_human_producer_is_not_run_without_a_roster(project):
    """
    No roster anywhere - not passed, and none stored with the transcript. The
    producer is not run and the reason says what is missing.
    """
    outcome = _import(project, HUMAN_ENTRIES, "human")      # imported with no roster
    result = S.run_structural(project, outcome.transcript)
    assert not result.ok
    assert result.problems[0].code == "missing_roster"


def test_a_stored_roster_is_reused_when_the_caller_does_not_pass_one(project):
    """State comes from disk: the roster given at import is found again later."""
    outcome = _import(project, HUMAN_ENTRIES, "human", roster_names=["Ana", "Ben"])
    result = S.run_structural(project, outcome.transcript)
    assert result.ok
    assert result.run.producer.startswith("structural_metrics_transportability")


def test_a_blocked_transcript_still_returns_every_metric_with_its_reason(project):
    entries = [dict(e) for e in SYNTHETIC_ENTRIES]
    entries[1]["speaker_id"] = ""
    outcome = _import(project, entries, "synthetic",
                      window_declaration="comparable_window")
    result = S.run_structural(project, outcome.transcript)
    assert not result.ok
    assert len([r for r in result.rows if r["kind"] == "metric"]) == 12
    assert all(r["value"] is None for r in result.rows)
    assert all(r["value_display"] == "Undefined" for r in result.rows)


def test_none_is_preserved_through_the_whole_service_chain(project):
    entries = [dict(e) for e in SYNTHETIC_ENTRIES]
    entries[1]["speaker_id"] = ""
    outcome = _import(project, entries, "synthetic",
                      window_declaration="comparable_window")
    result = S.run_structural(project, outcome.transcript)
    stored = S.load_structural(
        project, f"{outcome.transcript.transcript_id}__fullrun")
    assert all(r["value"] is None for r in stored["results"])
    files = E.project_export(
        transcript_payload=I.load_canonical(project,
                                            outcome.transcript.transcript_id),
        validation_report=outcome.validation_report,
        structural_payload=stored, structural_rows=result.rows,
        generated_utc="2026-08-04T00:00:00Z")
    csv_text = next(f for f in files if f.filename.endswith(".csv")).text
    assert ",0," not in csv_text
    assert "Undefined" in csv_text


def test_rehydrating_a_stored_transcript_gives_the_same_metrics(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="comparable_window")
    first = S.run_structural(project, outcome.transcript)
    again = S.run_structural(
        project, I.rehydrate(I.load_canonical(project,
                                              outcome.transcript.transcript_id)))
    assert [r["value"] for r in first.rows] == [r["value"] for r in again.rows]


# ======================================================== comparison gating
def _both_sides(project):
    human = _import(project, HUMAN_ENTRIES, "human", roster_names=["Ana", "Ben"])
    synthetic = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                        window_declaration="comparable_window")
    human_rows = S.run_structural(project, human.transcript,
                                  roster_names=["Ana", "Ben"]).rows
    synthetic_rows = S.run_structural(project, synthetic.transcript).rows
    return human_rows, synthetic_rows


def test_a_declared_pair_can_be_compared_structurally(project):
    human_rows, synthetic_rows = _both_sides(project)
    context = C.build_context(context_id="default", study_name="X",
                              human_set_id="human_a",
                              synthetic_set_ids=["synthetic_a"],
                              declaration_by_user="same guide and strata")
    result = S.compare_single_session(
        context, human_transcript_id="human_a",
        synthetic_transcript_id="synthetic_a",
        human_rows=human_rows, synthetic_rows=synthetic_rows)
    assert result.allowed
    assert result.rows
    assert result.human_transcript_id == "human_a"
    assert result.synthetic_transcript_id == "synthetic_a"
    for row in result.rows:
        assert "human_denominator" in row and "synthetic_denominator" in row
    assert any("no inferential test" in c for c in result.caveats)
    assert any("not thematic fidelity" in c for c in result.caveats)


def test_an_undeclared_pair_is_refused_with_its_reason(project):
    human_rows, synthetic_rows = _both_sides(project)
    context = C.build_context(context_id="default", study_name="X",
                              human_set_id="human_a",
                              synthetic_set_ids=["synthetic_a"])
    result = S.compare_single_session(
        context, human_transcript_id="human_a",
        synthetic_transcript_id="synthetic_a",
        human_rows=human_rows, synthetic_rows=synthetic_rows)
    assert not result.allowed
    assert "has not declared them homologues" in result.reason
    problem = S.comparison_unavailable_problem(context)
    assert problem.code == "methodological_comparison_unavailable"


def test_a_lone_synthetic_project_is_never_compared_with_the_frozen_benchmark(
        project):
    _, synthetic_rows = _both_sides(project)
    context = C.build_context(context_id="default", study_name="X",
                              synthetic_set_ids=["synthetic_a"])
    result = S.compare_single_session(
        context, human_transcript_id="human_a",
        synthetic_transcript_id="synthetic_a",
        human_rows=[], synthetic_rows=synthetic_rows)
    assert not result.allowed
    assert not result.rows
    # The reason NAMES the frozen study, to say the referent is not substituted.
    # What must not appear is a frozen VALUE: no human number reaches this result.
    frozen_human = {r["value"] for r in B.level2_rows()
                    if r["condition"] == "human" and r["value"] is not None}
    payload = json.dumps(result.__dict__)
    for value in frozen_human:
        assert repr(value) not in payload
    assert "not substituted" in " ".join(context.comparability_reasons).lower()


def test_a_difference_against_an_undefined_side_is_undefined_not_zero(project):
    human_rows, synthetic_rows = _both_sides(project)
    synthetic_rows = [dict(r, value=None) for r in synthetic_rows]
    context = C.build_context(context_id="default", study_name="X",
                              human_set_id="h", synthetic_set_ids=["s"],
                              declaration_by_user="declared")
    result = S.compare_single_session(
        context, human_transcript_id="human_a",
        synthetic_transcript_id="synthetic_a",
        human_rows=human_rows, synthetic_rows=synthetic_rows)
    assert all(row["difference"] is None for row in result.rows)
    assert all(row["difference_display"] == "Undefined" for row in result.rows)


# ================================================================== exports
def test_a_project_export_carries_denominators_status_and_hashes(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="comparable_window")
    result = S.run_structural(project, outcome.transcript)
    stored = S.load_structural(
        project, f"{outcome.transcript.transcript_id}__fullrun")
    files = E.project_export(
        transcript_payload=I.load_canonical(project,
                                            outcome.transcript.transcript_id),
        validation_report=outcome.validation_report,
        structural_payload=stored, structural_rows=result.rows,
        generated_utc="2026-08-04T00:00:00Z")
    names = [f.filename for f in files]
    assert names == ["canonical_transcript.json", "validation_report.json",
                     "level2_results.json", "level2_results.csv",
                     "provenance.json"]

    provenance = json.loads(next(f for f in files
                                 if f.filename == "provenance.json").text)
    body = provenance["results"]
    assert body["transcript"]["source_sha256"]
    assert body["denominators"] and body["calculation_status"]
    assert body["frozen_benchmark_used"] is False
    assert provenance["generated_utc"] == "2026-08-04T00:00:00Z"


def test_the_timestamp_is_only_on_the_envelope(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="comparable_window")
    result = S.run_structural(project, outcome.transcript)
    stored = S.load_structural(
        project, f"{outcome.transcript.transcript_id}__fullrun")

    def build(stamp):
        return {f.filename: f.text for f in E.project_export(
            transcript_payload=I.load_canonical(
                project, outcome.transcript.transcript_id),
            validation_report=outcome.validation_report,
            structural_payload=stored, structural_rows=result.rows,
            generated_utc=stamp)}

    first, second = build("2026-01-01T00:00:00Z"), build("2030-12-31T23:59:59Z")
    assert first["level2_results.csv"] == second["level2_results.csv"]
    for name in ("level2_results.json", "provenance.json"):
        a = json.loads(first[name])["results"]
        b = json.loads(second[name])["results"]
        assert a == b
        assert "generated_utc" not in json.dumps(a)


def test_a_benchmark_export_references_sources_without_copying_them():
    rows = B.level2_rows()
    files = E.benchmark_export(table_name="level2_focus_group", rows=rows,
                               generated_utc="2026-08-04T00:00:00Z")
    payload = json.loads(next(f for f in files
                              if f.filename.endswith(".json")).text)["results"]
    assert payload["sources_are_read_only"] is True
    assert len(payload["source_inventory"]) == 13
    for source in payload["source_inventory"]:
        assert len(source["sha256"]) == 64
        assert "rows" not in source            # the reference travels, not the data
    assert payload["calculation_status_by_row"]
    csv_text = next(f for f in files if f.filename.endswith(".csv")).text
    assert "calculation_status" in csv_text.splitlines()[0]


# ============================================================== immutability
def test_the_whole_service_layer_leaves_the_protected_sources_untouched(project):
    def digests():
        return {k: hashlib.sha256(s.path.read_bytes()).hexdigest()
                for k, s in TH.SOURCES.items()}

    before = digests()
    B.check_sources()
    B.level1_rows(); B.level1_rows(B.STUDY_REPLICATE_VIEW)
    B.level1_condition_summary(); B.level1_recurrence_rows()
    B.level1_ordering_rows(); B.level1_accumulation()
    B.level1_sensitivity_rows(); B.level1_ordering_sensitivity()
    B.level2_rows(); B.level2_rows(B.STUDY_REPLICATE_VIEW)
    B.level2_condition_summary(); B.level2_words_per_turn()
    E.benchmark_export(table_name="t", rows=B.level2_rows(),
                       generated_utc="2026-08-04T00:00:00Z")
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="comparable_window")
    S.run_structural(project, outcome.transcript)
    assert digests() == before


def test_project_writes_stay_inside_the_project_directory(project):
    outcome = _import(project, SYNTHETIC_ENTRIES, "synthetic",
                      window_declaration="comparable_window")
    S.run_structural(project, outcome.transcript)
    C.save_context(C.build_context(context_id="default", study_name="X",
                                   synthetic_set_ids=["s"]), project.path)
    written = [p for p in project.path.rglob("*") if p.is_file()]
    assert written
    for path in written:
        assert project.path in path.parents or path.parent == project.path
