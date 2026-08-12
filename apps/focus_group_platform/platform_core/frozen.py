"""
Frozen corpus protection (ADR-006).

NOT a directory root. `output/session_logs/` is where the architecture writes NEW
sessions, so freezing it would break generation. Protection is an explicit manifest
of session directories and corpus paths.

Two jobs:
  * refuse a write to anything in the manifest, before a file is opened;
  * plan a new session destination and refuse a collision or a frozen match.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_ROOT, APP_ROOT
from .paths import PathValidationError, safe_path, safe_component

MANIFEST_PATH = APP_ROOT / "frozen_sessions.json"

# Trees that are read-only in their entirety. `output/session_logs/` is deliberately
# ABSENT: it is protected per-directory through the manifest instead.
FROZEN_TREES = (
    "core",
    "agents",
    "configs",
    "prompts",
    "data/datasets_transcripts/standardized",
    "analysis",
)


class FrozenCorpusError(PermissionError):
    pass


@dataclass(frozen=True)
class FrozenEntry:
    path: str                    # repo-relative, posix
    kind: str                    # synthetic_session | human_transcript_set
    acceptance: bool
    reason: str


@dataclass
class FrozenManifest:
    version: str
    generated_utc: str
    entries: list[FrozenEntry] = field(default_factory=list)

    @property
    def paths(self) -> set[str]:
        return {e.path for e in self.entries}

    @property
    def acceptance_paths(self) -> list[str]:
        return sorted(e.path for e in self.entries if e.acceptance)

    def sha256(self) -> str:
        blob = json.dumps(
            {"version": self.version,
             "entries": [{"path": e.path, "kind": e.kind,
                          "acceptance": e.acceptance} for e in
                         sorted(self.entries, key=lambda x: x.path)]},
            sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_manifest(path: Path | None = None) -> FrozenManifest:
    p = Path(path) if path else MANIFEST_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    return FrozenManifest(
        version=raw["version"],
        generated_utc=raw["generated_utc"],
        entries=[FrozenEntry(**e) for e in raw["entries"]],
    )


def _repo_relative(target: Path) -> str | None:
    try:
        return Path(target).absolute().relative_to(REPO_ROOT.absolute()).as_posix()
    except ValueError:
        return None


def is_frozen(target: Path, manifest: FrozenManifest | None = None) -> bool:
    """True when `target` is, or lives under, a frozen tree or a manifest entry."""
    rel = _repo_relative(target)
    if rel is None:
        return False
    for tree in FROZEN_TREES:
        if rel == tree or rel.startswith(tree + "/"):
            return True
    man = manifest or load_manifest()
    for entry in man.paths:
        if rel == entry or rel.startswith(entry + "/"):
            return True
    return False


def assert_writable(target: Path, manifest: FrozenManifest | None = None) -> None:
    """Raise BEFORE any file is opened. Called by every write path."""
    if is_frozen(target, manifest):
        raise FrozenCorpusError(
            f"refusing to write to a frozen path: {target}. It belongs to the thesis "
            f"corpus and is read-only for this application (ADR-006).")


# ----------------------------------------------------------------- new sessions
SESSION_LOG_ROOT = REPO_ROOT / "output" / "session_logs"


@dataclass(frozen=True)
class SessionDestinationPlan:
    session_id: str
    resolved_path: Path
    project_prefixed: bool
    collision: bool
    frozen: bool
    allowed: bool
    refusal_reason: str | None


def plan_session_destination(session_id: str, project_slug: str,
                             manifest: FrozenManifest | None = None,
                             session_log_root: Path | None = None
                             ) -> SessionDestinationPlan:
    """
    Resolve the exact destination for a new run and decide whether it is allowed.

    ORDER MATTERS (ADR-008). The identifiers are validated as single safe path
    components and the destination is built with `safe_path` BEFORE anything touches
    the filesystem. A prefix check alone is not protection: `pilot__../../outside`
    keeps the prefix and still escapes.

    Refuses on four grounds: an unsafe project slug or session id, a session id that
    is not project-prefixed, ANY existing directory at the destination, and a match
    against the frozen manifest.
    """
    root = Path(session_log_root) if session_log_root else SESSION_LOG_ROOT

    try:
        safe_component(project_slug, field="project_slug")
        safe_component(session_id, field="session_id")
        resolved = safe_path(root, session_id)
    except PathValidationError as exc:
        return SessionDestinationPlan(
            session_id=session_id, resolved_path=root / "<refused>",
            project_prefixed=False, collision=False, frozen=False,
            allowed=False,
            refusal_reason=(f"unsafe identifier, refused before touching the "
                            f"filesystem: {exc}"))

    prefixed = session_id.startswith(f"{project_slug}__")
    collision = resolved.exists()
    frozen = is_frozen(resolved, manifest)

    reason = None
    if not prefixed:
        reason = (f"session_id {session_id!r} is not prefixed with the project slug "
                  f"{project_slug!r}; a project prefix is what keeps new runs "
                  f"distinguishable from the frozen corpus")
    elif frozen:
        reason = (f"{resolved} is in the frozen manifest; the thesis corpus is "
                  f"read-only")
    elif collision:
        reason = (f"{resolved} already exists; the application never overwrites or "
                  f"resumes a run directory - use a new session_id")

    return SessionDestinationPlan(
        session_id=session_id, resolved_path=resolved,
        project_prefixed=prefixed, collision=collision, frozen=frozen,
        allowed=reason is None, refusal_reason=reason)
