"""
`platform_acceptance_immutability` - check A.

Hashes every protected file, runs the platform's own work, and hashes again. ANY
change is a failure. No baseline-after-the-fact, no silent exclusion, no timestamp
tolerance.

This is deliberately NOT the repository regression suite. `tests/test_cross_model_audit_q3.py`
rewrites `analysis/production_evaluation/emergent_calibration_q3/cross_model_manifest_q3.json`
on every run (its `built_utc` field changes), so that suite cannot serve as an
immutability proof for this application. It is a separate check with its own
documented caveat - see `docs/decisions/ADR-006-frozen-session-manifest.md` and
`PHASE1_ACCEPTANCE_TEST_PLAN.md` AMENDMENT 2.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from platform_core import frozen, level2, transcripts, windows
from platform_core.catalog import load_catalog

REPO = Path(__file__).resolve().parents[3]
HUMAN_DIR = REPO / "data/datasets_transcripts/standardized/macho_meals"

# Trees hashed in full. `output/session_logs/` is NOT hashed wholesale - only its
# manifest entries are - because the architecture legitimately creates new run
# directories there (ADR-006).
PROTECTED_TREES = ("core", "agents", "configs", "prompts",
                   "data/datasets_transcripts/standardized")


def _hash_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for f in root.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            out[str(f.relative_to(REPO))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _snapshot() -> dict[str, str]:
    snap: dict[str, str] = {}
    for tree in PROTECTED_TREES:
        snap.update(_hash_tree(REPO / tree))
    for entry in frozen.load_manifest().entries:
        snap.update(_hash_tree(REPO / entry.path))
    return snap


def _session_log_dirs() -> set[str]:
    root = REPO / "output" / "session_logs"
    return {d.name for d in root.iterdir() if d.is_dir()} if root.exists() else set()


def _do_platform_work(tmp_path: Path) -> None:
    """Everything the platform does that could conceivably touch a protected file."""
    catalog = load_catalog()
    frozen.load_manifest()

    t = transcripts.normalise_transcript(
        HUMAN_DIR / "fg1" / "transcript.json", transcript_type="human",
        transcript_id="fg1", focus_group="fg1")
    people = json.loads((HUMAN_DIR / "fg1" / "participant_metadata.json")
                        .read_text(encoding="utf-8"))
    roster = [p["speaker_name"] for p in people if p["speaker_role"] == "participant"]
    level2.run_level2(t, roster_names=roster, catalog=catalog)

    for run_id in ("macho_meals_fg1_run02", "macho_meals_fg4_run04"):
        window, entries = windows.read_frozen_window(run_id)
        staged = tmp_path / f"{run_id}.json"
        staged.write_text(json.dumps(entries), encoding="utf-8")
        st = transcripts.normalise_transcript(staged, transcript_type="synthetic",
                                              transcript_id=run_id)
        level2.run_level2(st, catalog=catalog,
                          window_source=window.source_path,
                          window_sha256=window.provenance["file_sha256"])


def test_platform_acceptance_immutability(tmp_path):
    before = _snapshot()
    dirs_before = _session_log_dirs()
    assert before, "snapshot is empty - the protected trees were not found"

    _do_platform_work(tmp_path)

    after = _snapshot()
    dirs_after = _session_log_dirs()

    changed = sorted(p for p in before.keys() & after.keys()
                     if before[p] != after[p])
    removed = sorted(before.keys() - after.keys())
    added = sorted(after.keys() - before.keys())

    assert not changed, f"protected files changed: {changed[:10]}"
    assert not removed, f"protected files removed: {removed[:10]}"
    assert not added, f"files appeared inside protected paths: {added[:10]}"

    # A new run directory would be authorised only if project-prefixed; the platform
    # created none here, so the set must be identical.
    assert dirs_before == dirs_after, (
        f"session_logs changed: {sorted(dirs_after - dirs_before)}")


def test_platform_writes_only_into_the_temporary_directory(tmp_path):
    _do_platform_work(tmp_path)
    produced = sorted(p.name for p in tmp_path.iterdir())
    assert produced == ["macho_meals_fg1_run02.json", "macho_meals_fg4_run04.json"]


def test_repository_regression_is_a_separate_check():
    """
    Documented, not asserted here.

    `tests/test_cross_model_audit_q3.py` regenerates
    `analysis/.../cross_model_manifest_q3.json`, changing its `built_utc` timestamp on
    every run. That is pre-existing repository behaviour, unrelated to this
    application, and it is the reason the repository suite is NOT used as an
    immutability proof. A fully clean repository check requires running that suite in
    a disposable copy; neither the test nor the artefact is edited from this phase.
    """
    artefact = (REPO / "analysis/production_evaluation/emergent_calibration_q3"
                / "cross_model_manifest_q3.json")
    assert artefact.is_file()
    payload = json.loads(artefact.read_text(encoding="utf-8"))
    assert "built_utc" in payload, (
        "the documented caveat names built_utc as the field that moves; if it is "
        "gone, re-check the caveat rather than assuming the problem went away")


@pytest.mark.parametrize("run_id", ["macho_meals_fg4_run04", "macho_meals_fg5_run04"])
def test_acceptance_runs_that_a_naming_pattern_would_miss(run_id):
    """The manifest is read from the frozen CSV, not inferred (see the 2B correction)."""
    manifest = frozen.load_manifest()
    assert f"output/session_logs/{run_id}" in manifest.acceptance_paths
    assert frozen.is_frozen(REPO / "output" / "session_logs" / run_id)
