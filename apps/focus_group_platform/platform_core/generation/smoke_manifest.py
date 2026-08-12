"""
A read-only account of every exploratory run this project has actually executed.

WHY THIS EXISTS. Real sessions were run against a paid provider while testing the
generation path - two smoke runs and then a three-session pilot under the supervisor.
They produced output directories that look exactly like study data and are not study
data. Left undescribed, a directory full of transcripts is indistinguishable from a
result.

WHAT THIS MODULE DOES. It reads those directories, hashes what it finds, classifies
how each run ended using the same structured rules as every other run, and writes a
manifest that says in as many words that this is not thesis data.

WHAT IT WILL NOT DO. It does not write, move, rename or delete anything inside the
run directories, and it does not register them in any project. `build_manifest()`
opens files for reading only; the single write is the manifest itself, and it goes to
a path the caller names, outside the runs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..config import REPO_ROOT
from . import terminal as T

SCHEMA_VERSION = "3F.1"

# The classification that matters most. Every field below exists to keep these runs
# from being mistaken for benchmark material.
EXPLORATORY_NOT_THESIS_DATA = "EXPLORATORY_NOT_THESIS_DATA"

SMOKE_RUNS = (
    {
        "session_id": "smoke_smoke_fg1_r01",
        "relative_path": "output/session_logs/smoke_smoke_fg1_r01",
        "purpose": ("first real launch through the platform's generation path, to "
                    "confirm the public CLI boundary worked end to end"),
        "outcome_summary": ("the session crashed during the first participant turn: "
                            "a profile carried `persona.background` as a string and "
                            "the architecture iterates it as a mapping"),
    },
    {
        "session_id": "smoke2_smoke_fg1_r01",
        "relative_path": "output/session_logs/smoke2_smoke_fg1_r01",
        "purpose": ("second real launch, after the profile shape was corrected, to "
                    "confirm a session could complete"),
        "outcome_summary": ("the run completed a two-section throwaway guide; the "
                            "guide, the panel and the topic were written to exercise "
                            "the machinery and answer no research question"),
    },
) + tuple(
    {
        "session_id": f"commuting_pilot_pilot_fg1_r{index:02d}",
        "relative_path": f"output/session_logs/commuting_pilot_pilot_fg1_r{index:02d}",
        "purpose": ("Phase 3F pilot session, run under the autonomous queue "
                    "supervisor at concurrency 1"),
        "outcome_summary": ("completed a three-section guide on commuting - a topic "
                            "chosen precisely because it has nothing to do with the "
                            "thesis, so these artefacts cannot be mistaken for it"),
    }
    for index in (1, 2, 3)
)

WHY_NOT_DATA = (
    "The discussion guides were written to be short, not to be instruments. No panel "
    "was sampled. The topics do not match the study's research objective - the pilot "
    "sessions are about commuting, chosen for exactly that reason. No condition, "
    "focus group or replicate index in these directories refers to a cell of the "
    "frozen design, and the names that look like cells (`fg1`, `r01`) are throwaway "
    "labels. Replicate indices here are run labels and carry no seed.")

HANDLING = (
    "Keep the directories as evidence that the path was exercised. Do not import them "
    "into a project, do not code them, do not count them in any denominator, and do "
    "not present them as results. They are excluded from the frozen benchmark by "
    "this manifest, not by being hidden.")


@dataclass
class RunEvidence:
    session_id: str
    relative_path: str
    exists: bool = False
    purpose: str = ""
    outcome_summary: str = ""
    n_files: int | None = None
    total_bytes: int | None = None
    file_hashes: dict = field(default_factory=dict)
    transcript_exists: bool = False
    transcript_parseable: bool = False
    n_transcript_entries: int | None = None
    final_state_path: str = ""
    final_state_turn_index: int | None = None
    guide_sections_total: int | None = None
    guide_sections_completed: int | None = None
    structured_guide_completed: bool | None = None
    transcript_state_match: bool | None = None
    completion_quality: str = ""
    completion_evidence: str = ""
    guide_completion_status: str = ""
    final_state_problems: list[str] = field(default_factory=list)
    n_ledger_entries: int | None = None
    # This manifest classifies from the final state ALONE - no stdout was kept and the
    # session's max-turns cap is not known here. A run that stopped at the cap would
    # therefore read PARTIAL_OUTPUT here and MAX_TURNS_REACHED in its own terminal
    # record. Saying so is cheaper than pretending the two are interchangeable.
    classification_basis: str = ("structured final state only; no stdout and no "
                                 "max_turns were available to this reader")
    classification: str = EXPLORATORY_NOT_THESIS_DATA

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SmokeManifest:
    generated_utc: str
    schema_version: str = SCHEMA_VERSION
    repo_root: str = ""
    classification: str = EXPLORATORY_NOT_THESIS_DATA
    why_not_data: str = WHY_NOT_DATA
    handling: str = HANDLING
    runs: list[RunEvidence] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["runs"] = [r.to_dict() for r in self.runs]
        return d


def _hash_directory(directory: Path) -> tuple[dict, int, int]:
    """
    Hash every file, in lexicographic path order, without changing any of them.

    The listing is materialised first, so a file created while hashing is absent from
    a manifest that presents itself as complete. That is acceptable only because these
    directories are finished; do not reuse this on a live run.
    """
    hashes: dict[str, str] = {}
    total = 0
    for child in sorted(directory.rglob("*")):
        if not child.is_file():
            continue
        try:
            hashes[child.relative_to(directory).as_posix()] = T.sha256_file(child)
            total += child.stat().st_size
        except OSError as exc:                                     # noqa: PERF203
            hashes[child.relative_to(directory).as_posix()] = f"unreadable: {exc}"
    return hashes, len(hashes), total


def _count_ledger(directory: Path) -> int | None:
    ledger = directory / "api_calls.jsonl"
    if not ledger.is_file():
        return None
    try:
        text = ledger.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # A file another process holds open is unreadable, not empty. Returning 0
        # would be a count.
        return None
    return sum(1 for line in text.splitlines() if line.strip())


def inspect_run(spec: dict, *, repo_root: Path | None = None) -> RunEvidence:
    """Read one run directory. Nothing inside it is written, moved or renamed."""
    root = Path(repo_root or REPO_ROOT)
    directory = root / spec["relative_path"]
    evidence = RunEvidence(
        session_id=spec["session_id"], relative_path=spec["relative_path"],
        purpose=spec.get("purpose", ""),
        outcome_summary=spec.get("outcome_summary", ""))
    if not directory.is_dir():
        return evidence

    evidence.exists = True
    evidence.file_hashes, evidence.n_files, evidence.total_bytes = _hash_directory(
        directory)
    evidence.n_ledger_entries = _count_ledger(directory)

    # The same rules every other run is judged by. No stdout was captured for these
    # two, so the structured state is the only evidence there is - which is exactly
    # the case this classification was built for.
    try:
        inspected = T.inspect_output(directory, "", session_id=spec["session_id"])
    except OSError as exc:
        evidence.final_state_problems = [
            f"the run could not be inspected: {exc}"]
        return evidence
    for name in ("transcript_exists", "transcript_parseable", "n_transcript_entries",
                 "final_state_turn_index", "guide_sections_total",
                 "guide_sections_completed", "structured_guide_completed",
                 "transcript_state_match", "completion_quality",
                 "completion_evidence", "guide_completion_status",
                 "final_state_problems"):
        if name in inspected:
            setattr(evidence, name, inspected[name])
    final_state = inspected.get("final_state_path", "")
    if final_state:
        evidence.final_state_path = Path(final_state).name
    return evidence


def build_manifest(*, repo_root: Path | None = None,
                   utc: str | None = None) -> SmokeManifest:
    root = Path(repo_root or REPO_ROOT)
    manifest = SmokeManifest(
        generated_utc=utc or datetime.now(UTC).isoformat(), repo_root=str(root))
    for spec in SMOKE_RUNS:
        evidence = inspect_run(spec, repo_root=root)
        manifest.runs.append(evidence)
        if not evidence.exists:
            manifest.problems.append(
                f"{spec['relative_path']} is not present; the manifest records what "
                f"was expected and does not recreate it")
    return manifest


def write_manifest(target: Path | str, *, repo_root: Path | None = None,
                   utc: str | None = None) -> Path:
    """
    The only write in this module, and it lands outside the run directories.

    `target` is refused if it resolves inside one of them: a manifest written into the
    thing it describes would change that thing's hashes, including its own.
    """
    manifest = build_manifest(repo_root=repo_root, utc=utc)
    path = Path(target).resolve()
    root = Path(repo_root or REPO_ROOT)
    for spec in SMOKE_RUNS:
        directory = (root / spec["relative_path"]).resolve()
        if path == directory or directory in path.parents:
            raise ValueError(
                f"the manifest may not be written inside {spec['relative_path']}; "
                f"describing a directory must not modify it")
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(manifest.to_dict(), indent=1,
                                       ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return path
