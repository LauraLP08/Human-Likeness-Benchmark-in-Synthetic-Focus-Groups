"""
Projects: the unit of isolation.

Every path the application writes derives from the resolved data directory through
`safe_path`. Nothing is created at import time or by resolution - a project directory
appears only when `create_project` is called.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .atomic import OnExists, atomic_write_text
from .config import DataDirResolution, resolve_data_dir
from .paths import PathValidationError, safe_component, safe_path, slugify
from .provenance import (APPLICATION_VERSION, GUIDE_COMPILER_VERSION,
                         PROFILE_SCHEMA_VERSION, TRANSCRIPT_SCHEMA_VERSION)

PROJECT_SUBDIRS = ("uploads", "derived", "runs", "cache", "exports")
PROJECT_FILE = "project.json"


class ProjectError(RuntimeError):
    pass


@dataclass
class SchemaVersions:
    application_version: str = APPLICATION_VERSION
    guide_compiler_version: str = GUIDE_COMPILER_VERSION
    profile_schema_version: str = PROFILE_SCHEMA_VERSION
    transcript_schema_version: str = TRANSCRIPT_SCHEMA_VERSION


@dataclass
class Project:
    project_id: str
    name: str
    root: str
    created_at: str
    updated_at: str
    description: str = ""
    demo_mode: bool = False
    default_pricing_table_version: str = ""
    schema_versions: SchemaVersions = field(default_factory=SchemaVersions)

    @property
    def path(self) -> Path:
        return Path(self.root)

    def subdir(self, name: str) -> Path:
        if name not in PROJECT_SUBDIRS:
            raise ProjectError(f"unknown project subdirectory {name!r}")
        return safe_path(self.path, name)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _now() -> str:
    return datetime.now(UTC).isoformat()


def projects_root(data_dir: DataDirResolution) -> Path:
    return data_dir.projects_dir


def create_project(name: str, data_dir: DataDirResolution, *,
                   description: str = "", demo_mode: bool = False) -> Project:
    """Create a project. This is the ONLY function that creates user directories."""
    project_id = slugify(name)
    root_dir = projects_root(data_dir)
    root_dir.mkdir(parents=True, exist_ok=True)

    target = safe_path(root_dir, project_id)
    if target.exists():
        raise ProjectError(
            f"a project directory already exists for {name!r} -> {project_id}; "
            f"choose a different name rather than merging into it")

    target.mkdir(parents=True)
    for sub in PROJECT_SUBDIRS:
        safe_path(target, sub).mkdir()

    now = _now()
    project = Project(project_id=project_id, name=name, root=str(target),
                      created_at=now, updated_at=now, description=description,
                      demo_mode=demo_mode)
    _write_project_file(project)
    return project


def _write_project_file(project: Project) -> None:
    target = safe_path(project.path, PROJECT_FILE)
    atomic_write_text(target,
                      json.dumps(project.to_dict(), indent=1, ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))


def load_project(project_id: str, data_dir: DataDirResolution) -> Project:
    """
    Load a project. `project.json` is DATA, never path authority (ADR-009).

    The authoritative root is derived from the resolved data directory and the
    validated project id. A `root` recorded inside the file must match that
    derivation exactly; anything else - an external root, a different project id, a
    relative path, another project's directory - is refused. A tampered file
    therefore cannot redirect uploads, derived artefacts or trash.
    """
    safe_component(project_id, field="project_id")
    derived_root = safe_path(projects_root(data_dir), project_id)
    pf = safe_path(derived_root, PROJECT_FILE, must_exist=True)
    raw = json.loads(pf.read_text(encoding="utf-8"))

    internal_id = raw.get("project_id")
    if internal_id != project_id:
        raise ProjectError(
            f"{pf}: project_id inside the file is {internal_id!r} but the directory "
            f"is {project_id!r}; refusing to load a project whose identity does not "
            f"match its location")

    recorded_root = raw.get("root")
    if recorded_root is not None:
        recorded = Path(recorded_root)
        if not recorded.is_absolute():
            raise ProjectError(
                f"{pf}: recorded root {recorded_root!r} is relative; the root must "
                f"be the absolute derived path or absent")
        if recorded.absolute() != derived_root.absolute():
            raise ProjectError(
                f"{pf}: recorded root {recorded_root!r} does not match the derived "
                f"path {derived_root}; project.json is data, not path authority "
                f"(ADR-009)")

    raw["schema_versions"] = SchemaVersions(**raw.get("schema_versions", {}))
    raw["project_id"] = project_id
    raw["root"] = str(derived_root)          # always the derived path
    return Project(**raw)


def list_projects(data_dir: DataDirResolution) -> list[Project]:
    root = projects_root(data_dir)
    if not root.exists():
        return []
    out: list[Project] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / PROJECT_FILE).is_file():
            try:
                out.append(load_project(child.name, data_dir))
            except (PathValidationError, ProjectError, json.JSONDecodeError):
                continue
    return out


def delete_project(project_id: str, data_dir: DataDirResolution) -> Path:
    """
    Recoverable deletion: move to `<data_dir>/trash/<project_id>_<timestamp>/`.

    Nothing outside the data directory is touched, and nothing is unlinked - the
    second step (permanent removal) is a separate, explicit call.
    """
    src = safe_path(projects_root(data_dir), project_id, must_exist=True)
    trash = data_dir.trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    dst = safe_path(trash, f"{project_id}_{stamp}")
    shutil.move(str(src), str(dst))
    return dst


def restore_project(trashed_name: str, data_dir: DataDirResolution) -> Path:
    src = safe_path(data_dir.trash_dir, trashed_name, must_exist=True)
    project_id = trashed_name.rsplit("_", 1)[0]
    root = projects_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    dst = safe_path(root, project_id)
    if dst.exists():
        raise ProjectError(f"cannot restore: {project_id} already exists")
    shutil.move(str(src), str(dst))
    return dst


def purge_trashed_project(trashed_name: str, data_dir: DataDirResolution) -> None:
    """Permanent removal. Deliberately a separate call from `delete_project`."""
    target = safe_path(data_dir.trash_dir, trashed_name, must_exist=True)
    shutil.rmtree(target)


def open_or_resolve(data_dir: Path | str | None = None) -> DataDirResolution:
    """Convenience for callers that only need the resolved directory."""
    return resolve_data_dir(injected=data_dir)
