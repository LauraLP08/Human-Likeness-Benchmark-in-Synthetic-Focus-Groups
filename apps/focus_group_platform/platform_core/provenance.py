"""
Versioning without git (Phase 1 contracts §9.1).

There is no `.git` in this repository, so "commit" is not available. A deterministic
content hash over an EXPLICIT file list takes its place. It is never labelled a
commit, and the label carried through the interface says so.

A file listed in the manifest but missing on disk is a hard error, not a skipped
entry - otherwise deleting a file would silently produce a stable-looking hash.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import APP_ROOT, REPO_ROOT

CODE_MANIFEST_PATH = Path(__file__).resolve().parent / "code_manifest.txt"

APPLICATION_VERSION = "0.1.0"
GUIDE_COMPILER_VERSION = "1.0.0"
PROFILE_SCHEMA_VERSION = "1.0.0"
TRANSCRIPT_SCHEMA_VERSION = "1.0.0"

HASH_LABEL = "code content hash (no git repository present)"


class ProvenanceError(RuntimeError):
    pass


def read_code_manifest(path: Path | None = None) -> list[str]:
    p = Path(path) if path else CODE_MANIFEST_PATH
    lines = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    if not lines:
        raise ProvenanceError(f"code manifest is empty: {p}")
    return lines


def code_content_hash(manifest_path: Path | None = None,
                      repo_root: Path | None = None) -> str:
    """
    Deterministic hash over the listed files, in manifest order.

    For each entry: sha256(relative_posix_path + NUL + sha256(file_bytes)); the
    concatenation is hashed once more. Order is manifest order, not directory order,
    so the value cannot drift with the filesystem.
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    parts: list[str] = []
    for rel in read_code_manifest(manifest_path):
        target = root / rel
        if not target.is_file():
            raise ProvenanceError(
                f"code manifest lists a file that does not exist: {rel}. A missing "
                f"file is an error, not a skipped entry - otherwise the hash would "
                f"look stable while the code changed.")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        parts.append(f"{rel}\0{digest}")
    joined = "\n".join(parts).encode("utf-8")
    return "cch:" + hashlib.sha256(joined).hexdigest()[:16]


def describe_code_hash(value: str) -> str:
    """Never render the hash as a commit."""
    return f"{value} - {HASH_LABEL}"


@dataclass(frozen=True)
class SchemaVersions:
    application_version: str = APPLICATION_VERSION
    guide_compiler_version: str = GUIDE_COMPILER_VERSION
    profile_schema_version: str = PROFILE_SCHEMA_VERSION
    transcript_schema_version: str = TRANSCRIPT_SCHEMA_VERSION


@dataclass
class ProvenanceBlock:
    """Embedded in every result, figure sidecar and export."""

    metric_id: str
    status: str
    application_version: str = APPLICATION_VERSION
    code_content_hash: str = ""
    code_content_hash_label: str = HASH_LABEL
    metric_registry_hash: str = ""
    guide_compiler_version: str = GUIDE_COMPILER_VERSION
    pricing_table_version: str = ""
    profile_schema_version: str = PROFILE_SCHEMA_VERSION
    transcript_schema_version: str = TRANSCRIPT_SCHEMA_VERSION
    metric_version: str = ""
    inputs: list[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    exclusions: list[dict] = field(default_factory=list)
    denominator: dict = field(default_factory=lambda: {"value": None,
                                                       "definition": ""})
    aggregation_path: str = "run -> focus group -> study replicate"
    executed_at: str = ""
    evaluator_model: str | None = None
    evaluator_config: dict | None = None
    human_intervention: bool = False
    human_decisions: list[str] = field(default_factory=list)
    result_class: str = "exploratory"
    demo_mode: bool = False

    def stamp(self) -> "ProvenanceBlock":
        if not self.executed_at:
            self.executed_at = datetime.now(UTC).isoformat()
        return self

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# Figures carry only these three fields; the full block goes to a sidecar (§A1.5).
FIGURE_CAPTION_FIELDS = ("metric_id", "status", "denominator")


def figure_caption_fields(block: ProvenanceBlock) -> dict:
    d = block.to_dict()
    return {k: d[k] for k in FIGURE_CAPTION_FIELDS}


def sidecar_path(figure_path: Path) -> Path:
    return Path(figure_path).with_suffix("").with_suffix(".provenance.json")
