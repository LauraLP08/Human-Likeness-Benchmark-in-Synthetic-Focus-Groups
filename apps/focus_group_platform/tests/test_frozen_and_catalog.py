"""Frozen-corpus protection (ADR-006) and the eight-status catalogue (ADR-004)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from platform_core import catalog, frozen
from platform_core.catalog import RuntimeStatus, Status


# ------------------------------------------------------------------ manifest
def test_manifest_shape():
    m = frozen.load_manifest()
    assert len(m.entries) == 77
    synthetic = [e for e in m.entries if e.kind == "synthetic_session"]
    human = [e for e in m.entries if e.kind == "human_transcript_set"]
    windows_ = [e for e in m.entries if e.kind == "comparable_window"]
    assert len(human) == 5
    assert len(windows_) == 30
    assert len([e for e in synthetic if e.acceptance]) == 30
    assert len([e for e in synthetic if not e.acceptance]) == 12
    assert len(m.acceptance_paths) == 65
    assert m.sha256()


def test_session_log_root_is_not_frozen_wholesale():
    """The architecture writes new sessions there; freezing the root would break it."""
    assert "output/session_logs" not in frozen.FROZEN_TREES
    assert not frozen.is_frozen(frozen.SESSION_LOG_ROOT / "brand_new_session")


@pytest.mark.parametrize("rel", [
    "output/session_logs/macho_meals_fg1_run02",
    "output/session_logs/macho_meals_fg3_demoonly_run01",
    "data/datasets_transcripts/standardized/macho_meals/fg1",
    "core/orchestrator.py",
    "agents/macho_meals/mm_fg1_amir.json",
    "configs/experiment/macho_meals_fg1_run02.json",
    "analysis/production_evaluation/metric_registry.csv",
])
def test_frozen_paths_are_frozen(repo_root, rel):
    assert frozen.is_frozen(repo_root / rel)


def test_files_inside_a_frozen_session_are_frozen(repo_root):
    assert frozen.is_frozen(
        repo_root / "output/session_logs/macho_meals_fg1_run02/transcript.json")


def test_assert_writable_raises_before_opening_a_file(repo_root):
    target = repo_root / "output/session_logs/macho_meals_fg1_run02/transcript.json"
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(frozen.FrozenCorpusError, match="frozen path"):
        frozen.assert_writable(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


def test_paths_outside_the_repository_are_not_frozen(tmp_path):
    assert not frozen.is_frozen(tmp_path / "anything")


# --------------------------------------------------------- session planning
def test_new_session_with_unique_prefixed_id_is_allowed(tmp_path):
    plan = frozen.plan_session_destination(
        "pilot__enriched__fg1__r1", "pilot", session_log_root=tmp_path)
    assert plan.allowed
    assert plan.refusal_reason is None
    assert plan.project_prefixed and not plan.collision and not plan.frozen


def test_collision_with_any_existing_directory_is_refused(tmp_path):
    (tmp_path / "pilot__enriched__fg1__r1").mkdir()
    plan = frozen.plan_session_destination(
        "pilot__enriched__fg1__r1", "pilot", session_log_root=tmp_path)
    assert not plan.allowed
    assert "already exists" in plan.refusal_reason
    assert "never overwrites or resumes" in plan.refusal_reason


def test_unprefixed_session_id_is_refused(tmp_path):
    plan = frozen.plan_session_destination(
        "macho_meals_fg1_run02", "pilot", session_log_root=tmp_path)
    assert not plan.allowed
    assert "not prefixed" in plan.refusal_reason


def test_frozen_destination_is_refused_against_the_real_root():
    plan = frozen.plan_session_destination(
        "macho_meals_fg1_run02", "macho_meals_fg1_run02")
    assert not plan.allowed
    assert plan.frozen or plan.collision


# ------------------------------------------------------------------ catalogue
@pytest.fixture(scope="module")
def cat():
    return catalog.load_catalog()


def test_every_registry_row_is_classified(cat):
    assert len(cat.entries) == 46
    assert all(isinstance(e.status, Status) for e in cat.entries.values())


def test_all_eight_statuses_have_rules():
    for status in Status:
        assert status in catalog.PERMITTED_OUTPUTS
        assert status in catalog.STATUS_REASON


def test_retired_is_its_own_status(cat):
    entry = cat.get("tier2b_section_theme_lists")
    assert entry.status is Status.RETIRED_NOT_FOR_FIDELITY
    assert entry.status is not Status.NOT_IN_REPORTED_INSTRUMENT
    assert entry.status is not Status.DEFERRED_NOT_IMPLEMENTED
    assert "Retired as a fidelity indicator" in entry.status_reason


@pytest.mark.parametrize("metric_id", [
    "specificity", "agreement", "disagreement", "challenge",
    "neutral_elaboration", "substantive_vs_superficial_elaboration",
    "profile_continuity_group", "profile_consistency_group", "hyper_exactness",
])
def test_withheld_metrics_cannot_be_computed(cat, metric_id):
    entry = cat.get(metric_id)
    assert entry.status is Status.NOT_IN_REPORTED_INSTRUMENT
    assert entry.permitted_outputs == ("catalogue_only",)
    with pytest.raises(catalog.CatalogError, match="cannot be computed"):
        cat.assert_computable(metric_id)


def test_retired_metric_cannot_be_computed(cat):
    with pytest.raises(catalog.CatalogError, match="cannot be computed"):
        cat.assert_computable("tier2b_section_theme_lists")


@pytest.mark.parametrize("metric_id", ["specificity", "tier2b_section_theme_lists"])
@pytest.mark.parametrize("output", ["primary_table", "exploratory_table", "figure",
                                    "report_body"])
def test_withheld_and_retired_have_no_path_to_tables_or_figures(cat, metric_id,
                                                                output):
    with pytest.raises(catalog.CatalogError, match="may not appear"):
        cat.assert_output_allowed(metric_id, output)


def test_specificity_and_reference_density_stay_distinct(cat):
    spec = cat.get("specificity")
    ref = cat.get("reference_density")
    assert spec.metric_id != ref.metric_id
    assert spec.display_name != ref.display_name
    assert spec.status is Status.NOT_IN_REPORTED_INSTRUMENT
    assert ref.status is Status.AVAILABLE_EXPLORATORY
    assert spec.permitted_outputs != ref.permitted_outputs
    assert spec.registry_tier == "interpretive"
    assert ref.registry_tier == "interaction"
    # the automatic count may be drawn; the withheld judgement may not
    cat.assert_output_allowed("reference_density", "figure")
    with pytest.raises(catalog.CatalogError):
        cat.assert_output_allowed("specificity", "figure")


def test_exploratory_may_not_enter_a_primary_table(cat):
    cat.assert_output_allowed("tier1_subtheme_recall", "primary_table")
    with pytest.raises(catalog.CatalogError):
        cat.assert_output_allowed("reference_density", "primary_table")


def test_operational_metrics_are_synthetic_only(cat):
    for mid in ("forced_silence_count", "forced_silence_rate", "api_error_rate",
                "response_truncation_rate", "full_run_total_words"):
        e = cat.get(mid)
        assert e.status is Status.SYNTHETIC_ONLY
        assert e.namespace == "_full_run_operational"


def test_deferred_metrics(cat):
    for mid in ("tier1_length_matched_recall", "tier1_length_matched_precision"):
        assert cat.get(mid).status is Status.DEFERRED_NOT_IMPLEMENTED


def test_coverage_curve_is_not_deferred(cat):
    """Phase 0 said DEFERRED; the registry says AUTOMATIC_DIAGNOSTIC (C-2)."""
    e = cat.get("tier1_coverage_by_word_count_curve")
    assert e.registry_evidence_class == "AUTOMATIC_DIAGNOSTIC"
    assert e.status is Status.AVAILABLE_EXPLORATORY


def test_registry_definitions_are_verbatim(cat, repo_root):
    import csv
    rows = {r["metric_id"]: r for r in csv.DictReader(
        (repo_root / "analysis/production_evaluation/metric_registry.csv").open(
            encoding="utf-8-sig"))}
    for mid, entry in cat.entries.items():
        assert entry.definition == rows[mid]["definition"].strip()
        assert entry.denominator_definition == rows[mid]["denominator"].strip()


# ------------------------------------------------------------ runtime status
def test_missing_human_referent_is_not_zero(cat):
    entry = cat.get("tier1_subtheme_recall")
    assert entry.requires_human_referent
    status, reason = catalog.resolve_runtime_status(entry, has_human_referent=False)
    assert status is RuntimeStatus.NOT_APPLICABLE_MISSING_HUMAN_REFERENCE
    assert "not zero" in reason


def test_independent_metric_runs_without_a_human_referent(cat):
    entry = cat.get("words_per_turn_median")
    assert not entry.requires_human_referent
    status, reason = catalog.resolve_runtime_status(entry, has_human_referent=False)
    assert status is Status.AVAILABLE_VALIDATED
    assert reason is None


def test_instrument_unavailable_blocks_level1(cat):
    entry = cat.get("tier1_f1")
    status, reason = catalog.resolve_runtime_status(
        entry, has_human_referent=True, instrument_available=False)
    assert status is RuntimeStatus.NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE
    assert "no substitute model is used" in reason


def test_self_invalidating_metric_goes_to_adjudication(cat):
    entry = cat.get("reference_density")
    assert entry.requires_human_review
    status, reason = catalog.resolve_runtime_status(
        entry, has_human_referent=True, self_reported_valid=False)
    assert status is RuntimeStatus.REQUIRES_RESEARCHER_ADJUDICATION
    assert "researcher decision" in reason


def test_withheld_metric_reports_its_reason_at_runtime(cat):
    status, reason = catalog.resolve_runtime_status(
        cat.get("specificity"), has_human_referent=True)
    assert status is Status.NOT_IN_REPORTED_INSTRUMENT
    assert "never opened" in reason


def test_unmapped_evidence_class_is_an_error(tmp_path):
    src = Path(catalog.REGISTRY_PATH).read_text(encoding="utf-8-sig").splitlines()
    header, first = src[0], src[1]
    broken = first.replace("AUTOMATIC_VALIDATED", "SOMETHING_NEW", 1)
    p = tmp_path / "registry.csv"
    p.write_text("\n".join([header, broken]), encoding="utf-8")
    with pytest.raises(catalog.CatalogError, match="unmapped registry evidence_class"):
        catalog.load_catalog(p)
