"""
Watch a running session, read-only.

Reads what the architecture already writes - `state_turn_*.json`, `transcript.json`,
`api_calls.jsonl`, the launcher's stdout - and never opens a socket, never writes into
the output directory and never touches the session.

WHAT IS NOT SHOWN. Prompts, system prompts, environment variables, credentials. A
progress screen that printed the moderator's full prompt would be an unmanaged copy of
the instrument, and one that echoed an environment would leak a key into a screenshot.
Turn counts, speakers, token totals and elapsed time are enough to know how a run is
going.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

STATE_TURN = re.compile(r"^state_turn_(\d+)\.json$")

# Only these keys are ever read out of a state file. Anything else - and prompts in
# particular - stays where it is.
SAFE_STATE_KEYS = ("total_turns", "current_section_index", "section_phase")

SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|ANTHROPIC_API_KEY\s*=\s*\S+|api[_-]?key\S*\s*[:=]\s*\S+)",
    re.IGNORECASE)


@dataclass
class Progress:
    session_id: str
    output_directory: str
    exists: bool = False
    last_turn: int | None = None
    last_speaker: str | None = None
    section_index: int | None = None
    section_phase: str | None = None
    n_api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    transcript_present: bool = False
    n_transcript_entries: int | None = None
    elapsed_seconds: float | None = None
    last_event: str = ""
    status: str = "UNKNOWN"

    def to_dict(self) -> dict:
        return asdict(self)


def _redact(text: str) -> str:
    return SECRET_PATTERN.sub("[redacted]", text)


def read_progress(output_directory: str | Path, *, session_id: str = "",
                  status: str = "UNKNOWN",
                  stdout_path: str | Path | None = None) -> Progress:
    directory = Path(output_directory)
    progress = Progress(session_id=session_id, output_directory=str(directory),
                        status=status)
    if not directory.is_dir():
        progress.last_event = "no output directory yet"
        return progress
    progress.exists = True

    turns = []
    for child in directory.glob("state_turn_*.json"):
        match = STATE_TURN.match(child.name)
        if match:
            turns.append((int(match.group(1)), child))
    if turns:
        number, path = max(turns, key=lambda t: t[0])
        progress.last_turn = number
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        meta = payload.get("session_meta") or {}
        progress.section_index = meta.get("current_section_index")
        progress.section_phase = meta.get("section_phase")
        transcript = payload.get("transcript") or []
        if transcript:
            last = transcript[-1]
            progress.last_speaker = (last.get("speaker_name")
                                     or last.get("speaker_id"))

    ledger = directory / "api_calls.jsonl"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                call = json.loads(line)
            except json.JSONDecodeError:
                continue
            progress.n_api_calls += 1
            progress.input_tokens += int(call.get("input_tokens") or 0)
            progress.output_tokens += int(call.get("output_tokens") or 0)

    transcript_path = directory / "transcript.json"
    if transcript_path.is_file():
        progress.transcript_present = True
        try:
            payload = json.loads(transcript_path.read_text(encoding="utf-8"))
            entries = (payload if isinstance(payload, list)
                       else payload.get("transcript") or [])
            progress.n_transcript_entries = len(entries)
        except (json.JSONDecodeError, OSError):
            progress.n_transcript_entries = None

    stamps = [p.stat().st_mtime for p in directory.iterdir() if p.is_file()]
    if stamps:
        progress.elapsed_seconds = round(max(stamps) - min(stamps), 1)

    if stdout_path:
        tail = _tail(Path(stdout_path))
        if tail:
            progress.last_event = _redact(tail)
    if not progress.last_event:
        progress.last_event = (f"turn {progress.last_turn}"
                               if progress.last_turn is not None
                               else "no turn recorded yet")
    return progress


def _tail(path: Path, lines: int = 1) -> str:
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return content[-lines][:300] if content else ""


def stdout_tail(path: str | Path, lines: int = 40) -> list[str]:
    """The launcher's own output, redacted. Never the session's prompts."""
    target = Path(path)
    if not target.is_file():
        return []
    try:
        content = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [_redact(line) for line in content[-lines:]]


@dataclass
class TokenLedger:
    """
    Actual usage, from `api_calls.jsonl`.

    This is the only place a REAL cost can come from - and only if a rate table
    exists. An estimate is never labelled as actual.
    """

    n_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_action: dict = field(default_factory=dict)
    source: str = "api_calls.jsonl"
    is_actual_usage: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def read_ledger(output_directory: str | Path) -> TokenLedger:
    ledger = TokenLedger()
    path = Path(output_directory) / "api_calls.jsonl"
    if not path.is_file():
        return ledger
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            call = json.loads(line)
        except json.JSONDecodeError:
            continue
        ledger.n_calls += 1
        ledger.input_tokens += int(call.get("input_tokens") or 0)
        ledger.output_tokens += int(call.get("output_tokens") or 0)
        action = str(call.get("action") or "unknown")
        bucket = ledger.by_action.setdefault(
            action, {"n_calls": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["n_calls"] += 1
        bucket["input_tokens"] += int(call.get("input_tokens") or 0)
        bucket["output_tokens"] += int(call.get("output_tokens") or 0)
    return ledger

# ------------------------------------------------------ duration summary (3F)
# `launch_duration_seconds` is deliberately NOT summarised. It spans two adjacent
# assignments in `launcher.launch()` - the real spawn happens after both - so the
# pilot recorded 1e-5 s and the table presented interpreter jitter as a distribution
# beside three measured stages. It is still stored per job; it is not averaged.
STAGES = ("queue_wait_seconds", "run_duration_seconds", "total_elapsed_seconds")
UNSUMMARISED_STAGES = ("launch_duration_seconds",)
SINGLE_OBSERVATION = "SINGLE_OBSERVATION"
NO_OBSERVATION = "NO_OBSERVATION"
SUMMARISED = "SUMMARISED"


@dataclass
class StageDuration:
    """
    One stage across the jobs that reported it.

    `status` is the point. With one job there is a value and no spread, and a mean
    over n=1 dressed up with a min and a max reads like a distribution. It is labelled
    SINGLE_OBSERVATION so nothing downstream treats it as one.
    """

    stage: str
    n_observations: int = 0
    n_missing: int = 0
    mean_seconds: float | None = None
    median_seconds: float | None = None
    min_seconds: float | None = None
    max_seconds: float | None = None
    total_seconds: float | None = None
    status: str = NO_OBSERVATION

    @property
    def dispersion_available(self) -> bool:
        return self.n_observations > 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dispersion_available"] = self.dispersion_available
        return d


@dataclass
class PlanDurationSummary:
    plan_id: str
    n_jobs: int = 0
    n_completed: int = 0            # status COMPLETED
    n_terminal: int = 0             # reached any end, including cancelled/orphaned
    stages: dict = field(default_factory=dict)
    wall_clock_seconds: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stages"] = {k: v.to_dict() for k, v in self.stages.items()}
        return d


def _summarise(stage: str, values: list[float], n_missing: int) -> StageDuration:
    row = StageDuration(stage=stage, n_observations=len(values),
                        n_missing=n_missing)
    if not values:
        return row
    ordered = sorted(values)
    row.min_seconds = ordered[0]
    row.max_seconds = ordered[-1]
    row.total_seconds = sum(ordered)
    row.mean_seconds = row.total_seconds / len(ordered)
    middle = len(ordered) // 2
    row.median_seconds = (ordered[middle] if len(ordered) % 2
                          else (ordered[middle - 1] + ordered[middle]) / 2)
    row.status = SINGLE_OBSERVATION if len(ordered) == 1 else SUMMARISED
    return row


def plan_duration_summary(jobs, *, plan_id: str = "") -> PlanDurationSummary:
    """
    Stage durations across a plan's jobs. A missing duration stays missing.

    A job that never launched has no run duration; it is counted in `n_missing` and
    contributes nothing to the mean. Substituting zero would make a plan that half
    failed look faster than one that succeeded.
    """
    relevant = [j for j in jobs if not plan_id or j.plan_id == plan_id]
    summary = PlanDurationSummary(plan_id=plan_id, n_jobs=len(relevant))
    # A TIMESTAMP IS NOT A COMPLETION. `completed_utc` is stamped for CANCELLED,
    # ORPHANED and FAILED_TO_LAUNCH too, so a field named n_completed was reporting
    # "3 of 3 completed" for a plan where one job was killed and one vanished.
    summary.n_completed = sum(1 for j in relevant
                              if getattr(j, "status", "") == "COMPLETED")
    # `JobRecord.terminal` decides this, not the presence of a stamp. A
    # REQUIRES_RECOVERY job carries a completed_utc and is explicitly NOT terminal -
    # it is waiting for a human.
    summary.n_terminal = sum(1 for j in relevant if getattr(j, "terminal", False))

    for stage in STAGES:
        values, missing = [], 0
        for job in relevant:
            value = getattr(job, stage, None)
            try:
                # Hardened alongside `_parse_utc`, and for the same reason: a single
                # hand-edited record must not blank the panel for every job.
                values.append(float(value)) if value is not None else None
            except (TypeError, ValueError):
                value = None
            if value is None:
                missing += 1
        summary.stages[stage] = _summarise(stage, values, missing)

    starts = [j.queued_utc or j.started_utc for j in relevant
              if (j.queued_utc or j.started_utc)]
    ends = [j.completed_utc for j in relevant if j.completed_utc]
    if len(ends) == len(relevant) and summary.n_completed != len(relevant):
        others = sorted({getattr(j, "status", "UNKNOWN") for j in relevant
                         if getattr(j, "status", "") != "COMPLETED"})
        summary.notes.append(
            f"only {summary.n_completed} of {len(relevant)} job(s) completed; the "
            f"others ended as {others}, so this wall-clock time covers a plan that "
            f"did not run as designed")
    if starts and ends and len(ends) == len(relevant):
        # Parse once, then filter. The generator called _parse_utc twice per element
        # and could empty itself while `starts` was non-empty, raising ValueError out
        # of min().
        parsed_starts = [d for d in (_parse_utc(s) for s in starts) if d]
        parsed_ends = [d for d in (_parse_utc(e) for e in ends) if d]
        first = min(parsed_starts) if parsed_starts else None
        last = max(parsed_ends) if parsed_ends else None
        if first and last:
            summary.wall_clock_seconds = (last - first).total_seconds()
    elif starts and ends:
        summary.notes.append(
            f"{len(relevant) - len(ends)} job(s) have not finished, so the plan's "
            f"wall-clock time is not yet defined")

    single = [s for s in summary.stages.values() if s.status == SINGLE_OBSERVATION]
    if single:
        summary.notes.append(
            f"{len(single)} stage(s) rest on a single observation and carry no "
            f"dispersion: {sorted(s.stage for s in single)}")
    return summary


def _parse_utc(value):
    """
    An aware UTC datetime, or None. Must agree with .

    Two copies of this existed and disagreed: one raised AttributeError on a numeric
    value while the other returned None, and NEITHER made a naive stamp aware - so
    mixing one naive timestamp with an aware one raised TypeError out of the whole
    plan summary. A naive stamp is now UNOBSERVED, not assumed to be UTC; see the
    reasoning in `launcher._parse_utc`.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None
