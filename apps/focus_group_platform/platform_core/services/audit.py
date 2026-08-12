"""
Append-only audit log, one JSON object per line.

What happened to a project, in order: an import, a new version, an assignment, a
computation, an export. Enough to reconstruct how a number came to be on screen.

WHAT NEVER GOES IN: transcript content. Not a turn, not a quote, not a speaker name.
The log records identifiers, hashes and counts. A log that accumulated transcript text
would become a second, unmanaged copy of the data - subject to none of the protections
the canonical form has, and impossible to delete on request.

Append-only in the plain sense: the file is opened in append mode and existing lines
are never rewritten. A corrupted line is skipped on read rather than repairing the
file, because silently rewriting an audit log defeats its purpose.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..paths import safe_path

AUDIT_FILENAME = "audit_log.jsonl"

IMPORT = "IMPORT"
VERSION = "VERSION"
ASSIGN = "ASSIGN"
COMPUTE = "COMPUTE"
EXPORT = "EXPORT"
DESIGN = "DESIGN"
WINDOW = "WINDOW"
REPLACE = "REPLACE"
GENERATE = "GENERATE"

EVENTS = (IMPORT, VERSION, ASSIGN, COMPUTE, EXPORT, DESIGN, WINDOW, REPLACE,
          GENERATE)

# Keys that would carry transcript content if a caller passed them by mistake.
FORBIDDEN_DETAIL_KEYS = {"content", "text", "turns", "transcript", "entries",
                         "speaker_name", "quote", "quotes", "excerpt"}


class AuditError(RuntimeError):
    pass


@dataclass
class AuditEvent:
    event: str
    utc: str
    project_id: str
    subject: str
    detail: dict

    def to_dict(self) -> dict:
        return {"event": self.event, "utc": self.utc,
                "project_id": self.project_id, "subject": self.subject,
                "detail": self.detail}


def audit_path(project_root: Path) -> Path:
    return safe_path(project_root, AUDIT_FILENAME)


def _check_detail(detail: dict) -> None:
    for key in detail:
        if key.lower() in FORBIDDEN_DETAIL_KEYS:
            raise AuditError(
                f"refusing to log {key!r}: the audit log records identifiers, hashes "
                f"and counts, never transcript content")


def record(project_root: Path, event: str, *, project_id: str, subject: str,
           detail: dict | None = None, utc: str | None = None) -> AuditEvent:
    if event not in EVENTS:
        raise AuditError(f"unknown audit event {event!r}; expected one of "
                         f"{list(EVENTS)}")
    detail = dict(detail or {})
    _check_detail(detail)

    entry = AuditEvent(event=event, utc=utc or datetime.now(UTC).isoformat(),
                       project_id=project_id, subject=subject, detail=detail)
    line = json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True)
    if "\n" in line:
        raise AuditError("an audit line may not contain a newline")

    target = audit_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def read_log(project_root: Path, *, event: str | None = None) -> list[dict]:
    target = audit_path(project_root)
    if not target.is_file():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue                     # skipped, never repaired in place
        if event is None or entry.get("event") == event:
            out.append(entry)
    return out


def summarise_log(project_root: Path) -> dict:
    entries = read_log(project_root)
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["event"]] = counts.get(entry["event"], 0) + 1
    return {"n_events": len(entries), "by_event": counts,
            "first_utc": entries[0]["utc"] if entries else None,
            "last_utc": entries[-1]["utc"] if entries else None}


VERSION_SUFFIX = re.compile(r"^(?P<stem>.+?)__v(?P<n>\d{3})$")


def base_transcript_id(transcript_id: str) -> str:
    match = VERSION_SUFFIX.match(transcript_id)
    return match.group("stem") if match else transcript_id


def version_number(transcript_id: str) -> int:
    match = VERSION_SUFFIX.match(transcript_id)
    return int(match.group("n")) if match else 1
