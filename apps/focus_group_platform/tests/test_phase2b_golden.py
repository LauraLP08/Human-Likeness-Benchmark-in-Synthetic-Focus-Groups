"""
Phase 2B golden tests: reproduce the frozen structural values for all 35 acceptance
documents (5 human + 30 synthetic).

Read-only throughout. No evaluator is called. Nothing is written outside tmp_path.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from platform_core import level2, transcripts, windows
from platform_core.catalog import RuntimeStatus, load_catalog

REPO = Path(__file__).resolve().parents[3]
HUMAN_DIR = REPO / "data/datasets_transcripts/standardized/macho_meals"
FROZEN_CSV = (REPO / "analysis/production_evaluation/results"
              / "structural_interaction_metrics_long.csv")

FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")


def _acceptance_runs() -> tuple[str, ...]:
    """
    The canonical 30, read from the frozen results CSV.

    NOT inferred from a naming pattern: fg4 and fg5 enriched use run01/run03/run04,
    so `run0[1-3]` silently omits two real runs and invents two that do not exist.
    """
    rows = list(csv.DictReader(FROZEN_CSV.open(encoding="utf-8-sig")))
    return tuple(sorted({r["physical_run"] for r in rows if r["side"] == "synthetic"}))


SYNTHETIC_RUNS = _acceptance_runs()


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def frozen_rows():
    rows = list(csv.DictReader(FROZEN_CSV.open(encoding="utf-8-sig")))
    assert len(rows) == 665, f"frozen CSV has {len(rows)} rows, expected 665"
    return rows


@pytest.fixture(scope="module")
def frozen_human(frozen_rows):
    out: dict[str, dict[str, str]] = {}
    for r in frozen_rows:
        if r["side"] == "human":
            out.setdefault(r["fg"], {})[r["metric_id"]] = r["value"]
    return out


@pytest.fixture(scope="module")
def frozen_synthetic(frozen_rows):
    out: dict[str, dict[str, str]] = {}
    for r in frozen_rows:
        if r["side"] == "synthetic":
            out.setdefault(r["physical_run"], {})[r["metric_id"]] = r["value"]
    return out


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def _roster(fg: str) -> list[str]:
    people = json.loads((HUMAN_DIR / fg / "participant_metadata.json")
                        .read_text(encoding="utf-8"))
    return [p["speaker_name"] for p in people if p["speaker_role"] == "participant"]


def _human_run(fg: str, catalog):
    t = transcripts.normalise_transcript(
        HUMAN_DIR / fg / "transcript.json", transcript_type="human",
        transcript_id=fg, focus_group=fg)
    return t, level2.run_level2(t, roster_names=_roster(fg), catalog=catalog)


def _synthetic_run(run_id: str, catalog, tmp_path: Path):
    window, entries = windows.read_frozen_window(run_id)
    staged = tmp_path / f"{run_id}.json"
    staged.write_text(json.dumps(entries), encoding="utf-8")
    condition = "demographics-only" if "_demoonly" in run_id else "enriched"
    fg = run_id.split("_")[2]
    t = transcripts.normalise_transcript(
        staged, transcript_type="synthetic", transcript_id=run_id,
        focus_group=fg, condition=condition,
        replicate_label=f"r{run_id[-1]}")
    return t, level2.run_level2(t, catalog=catalog,
                                window_source=window.source_path,
                                window_sha256=window.provenance["file_sha256"])


def _compare(got, frozen_value: str) -> bool:
    """Compare at the precision the frozen artefact stored."""
    if got is None:
        return False
    decimals = len(frozen_value.split(".")[1]) if "." in frozen_value else 0
    return round(float(got), decimals) == round(float(frozen_value), decimals)


# =============================================================== human side
@pytest.mark.parametrize("fg", FGS)
def test_human_structural_matches_frozen(fg, frozen_human, catalog):
    _, run = _human_run(fg, catalog)
    got = {r.metric_id: r.value for r in run.results}
    mismatches = []
    checked = 0
    for metric_id, frozen_value in frozen_human[fg].items():
        if metric_id not in got:
            continue
        checked += 1
        if not _compare(got[metric_id], frozen_value):
            mismatches.append((metric_id, got[metric_id], frozen_value))
    assert checked >= 12, f"{fg}: only {checked} metrics compared"
    assert not mismatches, f"{fg}: {mismatches}"


@pytest.mark.parametrize("fg", FGS)
def test_human_counts_match_frozen(fg, frozen_human, catalog):
    _, run = _human_run(fg, catalog)
    for key in ("participant_turns", "moderator_turns", "participant_words",
                "total_words"):
        assert str(run.counts[key]) == str(int(float(frozen_human[fg][key]))), key


def test_human_producer_is_the_human_one(catalog):
    _, run = _human_run("fg1", catalog)
    assert run.producer == "structural_metrics_transportability.compute"


# =========================================================== synthetic side
@pytest.mark.parametrize("run_id", SYNTHETIC_RUNS)
def test_synthetic_structural_matches_frozen(run_id, frozen_synthetic, catalog,
                                             tmp_path):
    assert run_id in frozen_synthetic, f"{run_id} absent from the frozen CSV"
    _, run = _synthetic_run(run_id, catalog, tmp_path)
    got = {r.metric_id: r.value for r in run.results}
    mismatches = []
    checked = 0
    for metric_id, frozen_value in frozen_synthetic[run_id].items():
        if metric_id not in got or got[metric_id] is None:
            continue
        checked += 1
        if not _compare(got[metric_id], frozen_value):
            mismatches.append((metric_id, got[metric_id], frozen_value))
    assert checked >= 10, f"{run_id}: only {checked} metrics compared"
    assert not mismatches, f"{run_id}: {mismatches}"


@pytest.mark.parametrize("run_id", SYNTHETIC_RUNS[:6])
def test_synthetic_counts_match_frozen(run_id, frozen_synthetic, catalog, tmp_path):
    _, run = _synthetic_run(run_id, catalog, tmp_path)
    for key in ("participant_turns", "moderator_turns", "total_words"):
        assert str(run.counts[key]) == str(int(float(frozen_synthetic[run_id][key])))


def test_synthetic_producer_is_the_synthetic_one(catalog, tmp_path):
    _, run = _synthetic_run("macho_meals_fg1_run02", catalog, tmp_path)
    assert run.producer == "aggregate_production_results.compute_structural_metrics"


def test_all_thirty_windows_exist():
    available = set(windows.available_frozen_windows())
    assert set(SYNTHETIC_RUNS) == available
    assert len(SYNTHETIC_RUNS) == 30
    # the two runs a naming pattern would have got wrong
    assert "macho_meals_fg4_run04" in SYNTHETIC_RUNS
    assert "macho_meals_fg5_run04" in SYNTHETIC_RUNS
    assert "macho_meals_fg4_run02" not in SYNTHETIC_RUNS
    assert "macho_meals_fg5_run02" not in SYNTHETIC_RUNS


# ============================================================== schema rules
def test_human_and_synthetic_schemas_are_detected_explicitly(tmp_path):
    human = json.loads((HUMAN_DIR / "fg1" / "transcript.json")
                       .read_text(encoding="utf-8"))
    assert transcripts.detect_schema(human) == "standardized_human"

    _, entries = windows.read_frozen_window("macho_meals_fg1_run02")
    assert transcripts.detect_schema(entries) == "synthetic_session_log"


def test_a_file_matching_both_schemas_is_blocked():
    """One entry carrying both marker sets is a mix, and is blocked as such."""
    hybrid = [{"turn": 0, "speaker_id": "P1", "speaker_name": "A", "content": "x",
               "canonical_speaker_id": "P1", "speaker_role": "participant",
               "timestamp": "t", "selection_mode": "m"}]
    with pytest.raises(transcripts.SchemaDetectionError, match="mixed"):
        transcripts.detect_schema(hybrid)


def test_a_file_matching_neither_schema_is_rejected():
    with pytest.raises(transcripts.SchemaDetectionError, match="unsupported"):
        transcripts.detect_schema([{"who": "a", "said": "b"}])


def test_declared_type_must_match_the_detected_schema(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(json.loads(
        (HUMAN_DIR / "fg1" / "transcript.json").read_text(encoding="utf-8"))),
        encoding="utf-8")
    with pytest.raises(transcripts.SchemaDetectionError, match="declared synthetic"):
        transcripts.normalise_transcript(p, transcript_type="synthetic")


# =========================================================== provenance rules
def test_every_turn_carries_provenance(catalog):
    t, _ = _human_run("fg1", catalog)
    for turn in t.turns:
        assert turn.turn_id and turn.original_index >= 0
        assert turn.provenance.source_field_map
        assert "turn_id" in turn.provenance.derived_fields


def test_synthetic_role_and_canonical_id_are_recorded_as_derived(catalog, tmp_path):
    t, _ = _synthetic_run("macho_meals_fg1_run02", catalog, tmp_path)
    turn = t.turns[0]
    assert "speaker_role" in turn.provenance.derived_fields
    assert "canonical_speaker_id" in turn.provenance.derived_fields
    assert "MODERATOR" in (turn.provenance.notes or "")


def test_source_hash_and_original_coordinates_are_kept(catalog):
    t, _ = _human_run("fg2", catalog)
    raw = (HUMAN_DIR / "fg2" / "transcript.json").read_bytes()
    assert t.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert [turn.original_index for turn in t.turns] == list(range(len(t.turns)))


def test_unresolved_turn_blocks_metrics_and_raises_a_review_item(tmp_path):
    entries = [{"turn": 0, "speaker_id": "", "speaker_name": "", "content": "hello",
                "timestamp": "t", "selection_mode": "m"},
               {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Mod",
                "content": "and you?", "timestamp": "t", "selection_mode": "m"}]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    t = transcripts.normalise_transcript(p, transcript_type="synthetic")

    assert not t.fully_resolved
    assert t.review_items and t.review_items[0].kind == "TURN_UNRESOLVED"
    assert "no value is assigned by position" in t.review_items[0].detail

    run = level2.run_level2(t)
    assert run.producer == "none"
    assert all(r.value is None for r in run.results)
    assert all(r.status == RuntimeStatus.NOT_APPLICABLE_MISSING_INPUT.value
               for r in run.results)


# ============================================================ catalogue rules
def test_only_permitted_metrics_are_produced(catalog):
    _, run = _human_run("fg1", catalog)
    for r in run.results:
        entry = catalog.get(r.metric_id)
        assert entry.computable, f"{r.metric_id} should not be computed"


def test_no_withheld_metric_appears_in_a_result(catalog):
    _, run = _human_run("fg1", catalog)
    produced = {r.metric_id for r in run.results}
    withheld = {"specificity", "agreement", "disagreement", "challenge",
                "neutral_elaboration", "substantive_vs_superficial_elaboration",
                "hyper_exactness", "profile_continuity_group",
                "profile_consistency_group"}
    assert produced & withheld == set()


def test_results_carry_denominator_hierarchy_and_provenance(catalog):
    _, run = _human_run("fg1", catalog)
    for r in run.results:
        assert r.aggregation_path == "run -> focus group -> study replicate"
        assert "value" in r.denominator and "definition" in r.denominator
        assert r.provenance["metric_id"] == r.metric_id
        assert r.provenance["code_content_hash"].startswith("cch:")
        assert r.provenance["metric_registry_hash"]


def test_reference_density_keeps_its_self_invalidating_behaviour(catalog):
    entry = catalog.get("reference_density")
    assert entry.requires_human_review
    from platform_core.catalog import resolve_runtime_status
    status, reason = resolve_runtime_status(entry, has_human_referent=True,
                                            self_reported_valid=False)
    assert status is RuntimeStatus.REQUIRES_RESEARCHER_ADJUDICATION
    assert "researcher decision" in reason


# ================================================================ read-only
def test_frozen_windows_are_read_not_derived():
    window, _ = windows.read_frozen_window("macho_meals_fg3_run01")
    assert window.status is windows.WindowStatus.LOCKED
    assert "neither re-derived nor re-trimmed" in window.derivation_rule
    assert window.provenance["read_only"] is True


def test_new_corpus_window_is_a_contract_not_a_guess():
    w = windows.propose_window_for_new_corpus("some_new_run")
    assert w.status is windows.WindowStatus.UNDER_REVIEW
    assert w.unambiguous is False
    assert w.provenance["contract"]["implemented"] is False


def test_golden_run_writes_nothing_into_protected_trees(catalog, tmp_path):
    """The whole golden path touches no repository file."""
    watched = [HUMAN_DIR / "fg1" / "transcript.json",
               windows.frozen_window_path("macho_meals_fg1_run02"),
               FROZEN_CSV]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    _human_run("fg1", catalog)
    _synthetic_run("macho_meals_fg1_run02", catalog, tmp_path)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    assert before == after
