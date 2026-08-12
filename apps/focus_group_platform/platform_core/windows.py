"""
Comparable windows.

FROZEN CORPUS: the windows already exist
(`analysis/production_evaluation/comparable_transcripts/<run>/comparable_transcript.json`)
and are READ, never re-derived. The frozen window is the artefact of record; deriving
it again would substitute this application's judgement for the one the thesis froze.

NEW CORPORA: only the contract and the review states are defined here. No general
trimming heuristic is implemented, and none is guessed at runtime - an undetermined
boundary becomes a review item.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import REPO_ROOT

FROZEN_WINDOW_ROOT = (REPO_ROOT / "analysis" / "production_evaluation"
                      / "comparable_transcripts")


class WindowStatus(str, Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    LOCKED = "locked"
    REJECTED = "rejected"


class WindowError(RuntimeError):
    pass


@dataclass
class Boundary:
    turn_id: str | None
    char_offset: int | None
    matched_text: str
    confidence: str                     # exact | heuristic | manual


@dataclass
class ComparableWindow:
    window_id: str
    transcript_id: str
    status: WindowStatus
    derivation_rule: str
    unambiguous: bool
    n_entries: int
    retained_sha256: str
    source_path: str
    provenance: dict = field(default_factory=dict)
    start: Boundary | None = None
    end: Boundary | None = None
    positional_fallback_used: bool = False
    researcher_note: str | None = None


def frozen_window_path(run_id: str) -> Path:
    return FROZEN_WINDOW_ROOT / run_id / "comparable_transcript.json"


def available_frozen_windows() -> list[str]:
    if not FROZEN_WINDOW_ROOT.is_dir():
        return []
    return sorted(d.name for d in FROZEN_WINDOW_ROOT.iterdir()
                  if (d / "comparable_transcript.json").is_file())


def read_frozen_window(run_id: str) -> tuple[ComparableWindow, list[dict]]:
    """
    Read a frozen comparable window. Read-only, never re-derived, never re-trimmed.

    Returns the window record and its entries exactly as stored.
    """
    path = frozen_window_path(run_id)
    if not path.is_file():
        raise WindowError(f"no frozen comparable window for {run_id}: {path}")

    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    entries = payload.get("transcript")
    if not isinstance(entries, list):
        raise WindowError(f"{path}: no `transcript` array")

    retained = "\n".join(str(e.get("content", "")) for e in entries)
    window = ComparableWindow(
        window_id=f"frozen::{run_id}",
        transcript_id=run_id,
        status=WindowStatus.LOCKED,
        derivation_rule=("frozen artefact of record; read as stored and neither "
                         "re-derived nor re-trimmed"),
        unambiguous=True,
        n_entries=len(entries),
        retained_sha256=hashlib.sha256(retained.encode("utf-8")).hexdigest(),
        source_path=str(path),
        provenance={
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "recorded_provenance": payload.get("_provenance"),
            "read_only": True,
        },
    )
    return window, entries


def verify_frozen_window(run_id: str, expected_file_sha256: str) -> bool:
    window, _ = read_frozen_window(run_id)
    return window.provenance["file_sha256"] == expected_file_sha256


# ------------------------------------------------------- new corpora contract
NEW_CORPUS_CONTRACT = {
    "ladder": ["raw transcript", "normalised transcript", "proposed comparable window",
               "researcher review", "locked comparable window", "benchmark"],
    "rules": [
        "a boundary that cannot be located unambiguously inside its entry produces "
        "unambiguous=false and a review item; the benchmark is blocked",
        "a positional boundary is only ever recorded as a researcher decision, with "
        "positional_fallback_used=true; it is never applied silently",
        "no general trimming heuristic is implemented in this phase",
    ],
    "implemented": False,
}


def propose_window_for_new_corpus(transcript_id: str) -> ComparableWindow:
    """
    Contract placeholder for a corpus with no frozen window.

    Deliberately returns an UNDER_REVIEW window with `unambiguous=False` rather than
    a guess. Implementing a general boundary heuristic is out of scope for this phase
    and would be an unvalidated instrument if invented here.
    """
    return ComparableWindow(
        window_id=f"proposed::{transcript_id}",
        transcript_id=transcript_id,
        status=WindowStatus.UNDER_REVIEW,
        derivation_rule=("no general derivation rule is implemented for new corpora; "
                         "a researcher must set the boundaries"),
        unambiguous=False,
        n_entries=0,
        retained_sha256="",
        source_path="",
        provenance={"contract": NEW_CORPUS_CONTRACT},
    )
