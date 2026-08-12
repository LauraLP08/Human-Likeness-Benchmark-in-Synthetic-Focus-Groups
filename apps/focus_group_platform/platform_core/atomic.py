"""
Atomic artefact writes (ADR-010).

A derived artefact is either completely there or not there at all. A process killed
mid-write must never leave a half-written profile, guide or project file that a later
run would read as valid.

Sequence: temporary file in the SAME directory (so `os.replace` is atomic on the same
filesystem) -> write -> flush -> fsync -> close -> optional verification -> atomic
replace -> remove the temporary on any error.

Overwrite policy is explicit, never implicit: `on_exists` must be chosen by the
caller. Silently replacing a derived artefact would destroy the artefact a previous
run's provenance points at.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from enum import Enum
from pathlib import Path


class OnExists(str, Enum):
    FAIL = "fail"          # default for derived artefacts
    REPLACE = "replace"    # explicit, caller-chosen
    SKIP = "skip"


class AtomicWriteError(RuntimeError):
    pass


class ArtifactExistsError(FileExistsError):
    pass


def atomic_write_text(target: Path, text: str, *,
                      on_exists: OnExists = OnExists.FAIL,
                      verify: Callable[[str], None] | None = None,
                      encoding: str = "utf-8") -> Path:
    """
    Write `text` to `target` atomically.

    `verify` is called with the text that was written back from the temporary file,
    before the replace. It raises to abort; the target is then left untouched.
    """
    target = Path(target)
    if target.exists():
        if on_exists is OnExists.FAIL:
            raise ArtifactExistsError(
                f"{target} already exists. Overwriting a derived artefact is not "
                f"implicit: pass on_exists=OnExists.REPLACE if that is the intent, "
                f"or write to a new name (ADR-010).")
        if on_exists is OnExists.SKIP:
            return target

    target.parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent),
                                        prefix=f".{target.name}.",
                                        suffix=".tmp")
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())

        if verify is not None:
            verify(tmp_path.read_text(encoding=encoding))

        os.replace(tmp_path, target)
        tmp_path = None
        return target
    except Exception:
        raise
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def stale_temp_files(directory: Path, stem: str | None = None) -> list[Path]:
    """Temporaries this module could have left behind. Used by tests and diagnostics."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    pattern = f".{stem}.*.tmp" if stem else ".*.tmp"
    return sorted(directory.glob(pattern))
