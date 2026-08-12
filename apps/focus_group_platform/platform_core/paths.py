"""
Path validation. Every path the application writes goes through `safe_path`.

The rule: a resolved path must stay inside its declared root. Absolute components,
parent traversal, symlinks (including a symlinked ROOT) and drive changes are refused.
No module builds a path by string concatenation, so there is exactly one place where
this can go wrong.

Identifiers that arrive from a file - `agent_id`, `guide_id`, `session_id` - are
untrusted input and never reach the filesystem without passing `safe_component`
(ADR-008).
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_RESERVED_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class PathValidationError(ValueError):
    pass


def is_symlink(path: Path) -> bool:
    """
    Indirection so the symlink branch is unit-testable on a machine that cannot
    create symlinks. The real integration test still runs where the OS permits it.
    """
    try:
        return Path(path).is_symlink()
    except OSError:
        return False


def safe_component(name: str, *, field: str = "component") -> str:
    """
    A single path component. Anything else is refused with a localised message.

    Deliberately ASCII-only: these identifiers travel into file names, session ids and
    provenance keys across a pipeline that does not normalise Unicode, so accepting
    look-alike characters would make two distinct identifiers indistinguishable on
    some filesystems (ADR-008).
    """
    if not isinstance(name, str) or not name:
        raise PathValidationError(f"{field}: empty identifier")
    if name in {".", ".."}:
        raise PathValidationError(f"{field}: traversal component refused: {name!r}")
    if "/" in name or "\\" in name:
        raise PathValidationError(
            f"{field}: path separator inside an identifier refused: {name!r}")
    if not _SAFE_NAME.match(name):
        raise PathValidationError(
            f"{field}: unsafe identifier {name!r}. Allowed: ASCII letters, digits, "
            f"dot, underscore and hyphen; 1-128 characters. Spaces, Unicode, "
            f"separators and drive letters are refused.")
    if name.split(".")[0].upper() in _RESERVED_WINDOWS:
        raise PathValidationError(
            f"{field}: reserved Windows device name refused: {name!r}")
    return name


def is_safe_component(name: str) -> bool:
    try:
        safe_component(name)
        return True
    except PathValidationError:
        return False


def _assert_no_symlink_ancestor(path: Path, stop_at: Path) -> None:
    """Walk existing ancestors from `path` up to (and including) `stop_at`."""
    current = path
    stop = stop_at.absolute()
    seen = 0
    while True:
        if is_symlink(current):
            raise PathValidationError(f"symlink refused on the path: {current}")
        if current.absolute() == stop or current.parent == current:
            return
        current = current.parent
        seen += 1
        if seen > 64:            # defensive: never loop on a pathological path
            return


def safe_path(root: Path, *parts: str, must_exist: bool = False) -> Path:
    """
    Join `parts` under `root` and prove the result stays inside it.

    Refuses: a symlinked root, absolute parts, `..`, embedded separators, symlinked
    ancestors, and any resolved path outside `root` (which covers drive changes).
    """
    root = Path(root)
    if not root.is_absolute():
        raise PathValidationError(f"root must be absolute: {root}")
    if is_symlink(root):
        raise PathValidationError(f"symlinked root refused: {root}")
    _assert_no_symlink_ancestor(root, root.anchor and Path(root.anchor) or root)

    for part in parts:
        if not isinstance(part, str):
            raise PathValidationError(f"path component must be a string: {part!r}")
        if PurePosixPath(part).is_absolute() or PureWindowsPath(part).is_absolute():
            raise PathValidationError(f"absolute path component refused: {part!r}")
        safe_component(part)

    candidate = root.joinpath(*parts)

    probe = root
    for part in parts:
        probe = probe / part
        if is_symlink(probe):
            raise PathValidationError(f"symlink refused on the path: {probe}")

    root_resolved = root.resolve() if root.exists() else root.absolute()
    resolved = candidate.resolve() if candidate.exists() else candidate.absolute()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathValidationError(
            f"path escapes its root: {resolved} is not inside {root_resolved}"
        ) from exc

    if must_exist and not candidate.exists():
        raise PathValidationError(f"path does not exist: {candidate}")
    return candidate


def slugify(text: str, *, fallback: str = "project") -> str:
    """A safe identifier derived from free text. Never used as a raw path component."""
    lowered = (text or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    slug = re.sub(r"_{2,}", "_", slug)[:64]
    return safe_component(slug or fallback, field="project_id")
