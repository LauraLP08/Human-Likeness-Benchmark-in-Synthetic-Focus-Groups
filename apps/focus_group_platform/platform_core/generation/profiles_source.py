"""
Where the participants come from: uploaded profiles, or a local Twin2K index.

UPLOADED PROFILES ARE NOT REWRITTEN. The agent payload is validated and hashed, and
then passed to the architecture exactly as it arrived. A platform that "helpfully"
normalised a payload would be changing the persona the researcher wrote.

TWIN2K IS DETECTED, NEVER FETCHED. If the local index is absent the answer is
`NOT_AVAILABLE_LOCAL_INDEX` plus the ETL that would produce it. Nothing is downloaded:
a dataset arriving because someone opened a screen is not a decision anyone made.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import REPO_ROOT
from ..profiles import ProfileError, architecture_shape_problems, load_profile_file
from .contracts import ProfileSourceKind, sha256_text

TWIN2K_INDEX_CANDIDATES = (
    "data/twin2k/index.json",
    "data/twin2k/panel_index.json",
    "analysis/twin2k/index.json",
)

TWIN2K_ETL_NOTE = (
    "Twin2K needs a local index built by its ETL before the platform can sample a "
    "panel. Nothing is downloaded automatically. Build the index into one of "
    f"{list(TWIN2K_INDEX_CANDIDATES)} and reopen this screen.")

NOT_AVAILABLE_LOCAL_INDEX = "NOT_AVAILABLE_LOCAL_INDEX"
AVAILABLE = "AVAILABLE"


@dataclass
class ProfileRecord:
    agent_id: str
    source_path: str
    source_sha256: str
    recognised_fields: list[str] = field(default_factory=list)
    unrecognised_fields: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProfileSet:
    kind: str
    records: list[ProfileRecord] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    panel_sampling_seed: int | None = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems and all(r.ok for r in self.records) \
            and bool(self.records)

    @property
    def agent_ids(self) -> list[str]:
        return [r.agent_id for r in self.records]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        # The seed selects PARTICIPANTS, not text. Said here so the field is never
        # read as a generation seed.
        d["panel_sampling_seed_meaning"] = (
            "reproducible selection of WHICH participants are drawn from the local "
            "index. It does not make an LLM run reproducible and is never a "
            "generation seed.")
        return d


RECOGNISED_TOP_LEVEL = {
    "schema_version", "agent_id", "language", "field_provenance", "persona",
    "simulation_config", "provenance", "source", "notes", "metadata",
}


def inspect_profile(path: Path) -> ProfileRecord:
    """Validate one agent payload. The payload itself is left untouched."""
    raw = path.read_bytes()
    record = ProfileRecord(agent_id="", source_path=str(path),
                           source_sha256=sha256_text(
                               raw.decode("utf-8", errors="replace")))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        record.problems.append(f"not valid JSON: {exc}")
        return record
    if not isinstance(payload, dict):
        record.problems.append("the profile is not a JSON object")
        return record

    record.agent_id = str(payload.get("agent_id") or path.stem)
    record.recognised_fields = sorted(k for k in payload
                                      if k in RECOGNISED_TOP_LEVEL)
    record.unrecognised_fields = sorted(k for k in payload
                                        if k not in RECOGNISED_TOP_LEVEL)
    try:
        load_profile_file(path)
    except ProfileError as exc:
        record.problems.append(str(exc))
    except Exception as exc:                                   # noqa: BLE001
        record.problems.append(f"{type(exc).__name__}: {exc}")
    record.problems += architecture_shape_problems(payload)
    return record


def uploaded_profile_set(paths) -> ProfileSet:
    records = [inspect_profile(Path(p)) for p in paths]
    problems = []
    seen: dict[str, int] = {}
    for record in records:
        seen[record.agent_id] = seen.get(record.agent_id, 0) + 1
    duplicates = sorted(a for a, n in seen.items() if n > 1)
    if duplicates:
        problems.append(f"duplicate agent id(s) {duplicates}; each participant needs "
                        f"a distinct identity")
    if not records:
        problems.append("no profile was supplied")
    return ProfileSet(kind=ProfileSourceKind.UPLOADED.value, records=records,
                      problems=problems,
                      note="payloads are passed to the architecture unmodified")


def twin2k_status(repo_root: Path | None = None) -> dict:
    root = repo_root or REPO_ROOT
    found = [c for c in TWIN2K_INDEX_CANDIDATES if (root / c).is_file()]
    if not found:
        return {"status": NOT_AVAILABLE_LOCAL_INDEX,
                "searched": list(TWIN2K_INDEX_CANDIDATES),
                "etl_note": TWIN2K_ETL_NOTE,
                "downloads_anything": False}
    return {"status": AVAILABLE, "index_path": found[0],
            "searched": list(TWIN2K_INDEX_CANDIDATES),
            "downloads_anything": False,
            "note": ("a panel may be sampled reproducibly from this index; the "
                     "sampling seed selects participants, never text")}


def participants_from_profiles(profile_set: ProfileSet, *,
                               relative_to: Path | None = None) -> list[dict]:
    """
    The public participant shape: one `agent_payload_path` per participant.

    Paths, not inline payloads, so the architecture reads the same file the
    researcher uploaded and the hash in the plan still refers to something on disk.
    """
    out = []
    for record in profile_set.records:
        path = Path(record.source_path)
        if relative_to is not None:
            try:
                path = path.relative_to(relative_to)
            except ValueError:
                pass
        out.append({"agent_payload_path": str(path).replace("\\", "/")})
    return out
