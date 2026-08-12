"""
Data-directory resolution (ADR-005).

User data NEVER lives inside the repository. Resolution order:

    1. FOCUS_GROUP_PLATFORM_DATA_DIR, when set and non-empty
    2. the operating system's local application-data directory
    3. an explicitly injected directory - tests only

NOTHING IS CREATED BY RESOLUTION. Importing this module creates nothing, and
`resolve_data_dir()` creates nothing. Creation is a separate, explicit act that
requires `ensure=True`, so installing the package, importing it, or running the test
suite can never leave user data behind.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "FOCUS_GROUP_PLATFORM_DATA_DIR"
DEV_REFERENCE_ENV_VAR = "FOCUS_GROUP_PLATFORM_DEV_REFERENCE"
APP_DIR_NAME_WINDOWS = "FocusGroupPlatform"
APP_DIR_NAME_POSIX = "focus-group-platform"
APP_DIR_NAME_MACOS = "FocusGroupPlatform"

# apps/focus_group_platform/platform_core/config.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path(__file__).resolve().parents[1]


class DataDirError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataDirResolution:
    """Where user data lives, and why it lives there."""

    path: Path
    source: str                      # env_var | os_app_data | injected
    env_var_name: str = ENV_VAR
    exists: bool = False
    created_by_this_call: bool = False

    @property
    def projects_dir(self) -> Path:
        return self.path / "projects"

    @property
    def trash_dir(self) -> Path:
        return self.path / "trash"


def _os_app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME_WINDOWS
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME_MACOS
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME_POSIX


def resolve_data_dir(injected: Path | str | None = None,
                     ensure: bool = False,
                     env: dict[str, str] | None = None,
                     allow_repo_for_tests: bool = False) -> DataDirResolution:
    """
    Resolve the data directory. Creates nothing unless `ensure=True`.

    `injected` is the test seam: it wins over everything, and is the only way a test
    is allowed to obtain a data directory.

    `allow_repo_for_tests` is the ONLY way to obtain a data directory inside the
    repository, and it exists solely so a test can use a repo-relative temporary
    path. Production code, the future Streamlit layer and any future API must never
    set it - a repository path is refused by default even when injected (ADR-005
    amended). A test that needs it must pass it explicitly, which makes the exception
    visible in the test source rather than implied by the injection.
    """
    environ = os.environ if env is None else env

    if injected is not None:
        path, source = Path(injected).expanduser(), "injected"
    else:
        raw = (environ.get(ENV_VAR) or "").strip()
        if raw:
            path, source = Path(raw).expanduser(), "env_var"
        else:
            path, source = _os_app_data_dir(), "os_app_data"

    path = path.resolve() if path.exists() else path.absolute()
    if path == APP_ROOT / "workspace":
        raise DataDirError(
            "the data directory may not be apps/focus_group_platform/workspace/ - "
            "user data never lives inside the repository (ADR-005)")
    if _is_within(path, REPO_ROOT) and not allow_repo_for_tests:
        raise DataDirError(
            f"refusing a data directory inside the repository: {path} (ADR-005). "
            f"User data never lives inside the repository. Set {ENV_VAR} to a "
            f"location outside {REPO_ROOT}. Tests that genuinely need a repo-relative "
            f"path must pass allow_repo_for_tests=True explicitly.")

    created = False
    if ensure and not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        created = True

    return DataDirResolution(path=path, source=source, exists=path.exists(),
                             created_by_this_call=created)


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.absolute().relative_to(parent.absolute())
        return True
    except ValueError:
        return False


def dev_reference_enabled(env: dict[str, str] | None = None) -> bool:
    """
    Whether the Macho Meals acceptance corpus is visible as a developer reference.
    It is never a project, never copied, never distributed (ADR-006).
    """
    environ = os.environ if env is None else env
    return (environ.get(DEV_REFERENCE_ENV_VAR) or "").strip() in {"1", "true", "TRUE"}
