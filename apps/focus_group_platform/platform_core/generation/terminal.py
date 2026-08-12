"""
Durable terminal evidence, decided from the STRUCTURED FINAL STATE.

WHAT CHANGED IN 3F. Completion used to be read from two strings the CLI prints. That
works until the wording changes, and it cannot be cross-examined. The authority is now
`state_turn_N.json`: whether every section of `discussion_guide` carries
`completed: true`. Stdout became corroboration.

FIVE GRADES OF EVIDENCE, because "we know" and "we were told" are different claims:

    STRUCTURED_STATE      the state says so; stdout is silent or absent
    STDOUT_CORROBORATED   the state says so and stdout agrees
    STDOUT_ONLY_LEGACY    a record written before the state was inspected
    CONFLICTING_EVIDENCE  the two disagree, or the state disagrees with itself
    INSUFFICIENT_EVIDENCE neither could be established

A CONFLICT NEVER PRODUCES GUIDE_COMPLETED. If stdout announces completion over a state
with an unfinished section, something is wrong with one of them and the platform does
not get to pick the convenient one.

TRANSCRIPT COHERENCE IS CANONICAL, NOT BYTE-WISE. `transcript.json` and the state's
own transcript are serialised separately; identical bytes were never the contract. The
comparison is turn, speaker, content and order.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

SCHEMA_VERSION = "1.1.0"
TERMINAL_RECORD_NAME = "terminal_record.json"


class TerminationKind(str, Enum):
    NORMAL_EXIT = "NORMAL_EXIT"
    NONZERO_EXIT = "NONZERO_EXIT"
    USER_CANCELLED = "USER_CANCELLED"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"
    PROCESS_LOST = "PROCESS_LOST"
    UNKNOWN = "UNKNOWN"


class CompletionQuality(str, Enum):
    GUIDE_COMPLETED = "GUIDE_COMPLETED"
    MAX_TURNS_REACHED = "MAX_TURNS_REACHED"
    PARTIAL_OUTPUT = "PARTIAL_OUTPUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    UNKNOWN = "UNKNOWN"


class CompletionEvidence(str, Enum):
    STRUCTURED_STATE = "STRUCTURED_STATE"
    STDOUT_CORROBORATED = "STDOUT_CORROBORATED"
    STDOUT_ONLY_LEGACY = "STDOUT_ONLY_LEGACY"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


GUIDE_COMPLETED_MARKER = re.compile(r"Guide completed naturally after (\d+) steps")
MAX_TURNS_MARKER = re.compile(r"SAFETY CAP HIT at (\d+) steps")
STATE_TURN = re.compile(r"^state_turn_(\d+)\.json$")

# Fields compared between the two transcripts. Timestamps and selection modes are
# excluded: they are recorded independently and a difference in them is not a
# disagreement about what was said.
TRANSCRIPT_FIELDS = ("turn", "speaker_id", "speaker_name", "content")


@dataclass
class FinalStateInspection:
    """What the structured final state says, and whether it holds together."""

    path: str = ""
    sha256: str = ""
    parseable: bool = False
    session_id: str | None = None
    turn_index: int | None = None            # N from state_turn_N.json
    total_turns: int | None = None
    current_section_index: int | None = None
    guide_sections_total: int | None = None
    guide_sections_completed: int | None = None
    all_sections_completed: bool = False
    state_transcript_entries: int | None = None
    turn_index_coherent: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.parseable and not self.problems

    def to_dict(self) -> dict:
        d = asdict(self)
        d["usable"] = self.usable
        return d


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_state_path(output_directory: Path) -> tuple[int, Path] | None:
    states = []
    for child in output_directory.glob("state_turn_*.json"):
        match = STATE_TURN.match(child.name)
        if match:
            states.append((int(match.group(1)), child))
    return max(states, key=lambda t: t[0]) if states else None


def canonical_transcript(entries) -> list[tuple]:
    """
    Turn, speaker and content, in order. Serialisation is not part of identity.

    THE CONTRACT, stated because it was previously only implied:

    * Each value is compared as its STRING form. `turn: 3` and `turn: "3"` are the
      same intervention — one writer used a number and another a string, and that is
      a serialisation difference, not two different discussions. The cost is that a
      genuine type change is invisible here; nothing downstream depends on the type.
    * An ABSENT field and an explicit `None` are the same: both mean "not recorded".
      A literal string `"None"` is NOT the same as `None`, and will register as a
      difference — which is correct, because one is a value and the other is absence.
    * Non-dict entries are SKIPPED rather than compared. A malformed entry is not
      evidence of disagreement; `n_non_dict_entries` on the inspection records how
      many were dropped, so a skipped entry cannot masquerade as an equal one.
    * Order is part of identity. The same interventions in a different sequence are a
      different discussion.
    """
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        out.append(tuple(
            str(entry.get(field_name)) if entry.get(field_name) is not None else None
            for field_name in TRANSCRIPT_FIELDS))
    return out


def _non_dict_count(entries) -> int:
    """How many entries were skipped as malformed. Never silently zero."""
    return sum(1 for e in (entries or []) if not isinstance(e, dict))


def compare_transcripts(file_entries, state_entries) -> tuple[bool, str]:
    """
    Canonical comparison. Returns (match, reason).

    A mismatch is a reason to stop, not a detail: if the two records of what was said
    disagree, the platform cannot say which one a metric would be computed over.
    """
    left, right = canonical_transcript(file_entries), canonical_transcript(
        state_entries)
    dropped = _non_dict_count(file_entries) + _non_dict_count(state_entries)
    if dropped:
        # A MALFORMED ENTRY IS NOT AGREEMENT. Skipping it and then comparing lengths
        # let a state that had picked up a stray entry be certified coherent with a
        # file that lacked it.
        return False, (f"{dropped} transcript entr(ies) are not objects and could not "
                       f"be compared; coherence is not established")
    if not left and not right:
        return False, "neither transcript.json nor the final state carries entries"
    if len(left) != len(right):
        return False, (f"transcript.json has {len(left)} intervention(s) and the "
                       f"final state has {len(right)}")
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            differing = [name for name, x, y in zip(TRANSCRIPT_FIELDS, a, b)
                         if x != y]
            return False, (f"intervention {index} differs on {differing} between "
                           f"transcript.json and the final state")
    return True, "the two transcripts agree on turn, speaker, content and order"


def inspect_final_state(output_directory: Path, *, session_id: str = "",
                        transcript_entries=None) -> FinalStateInspection:
    """
    Read the highest-numbered `state_turn_N.json` and check it against itself.

    Everything it cannot establish becomes a problem, not a silent default: a state
    that names a different session, or whose transcript disagrees with the file, is
    exactly the case where a confident answer would be wrong.
    """
    inspection = FinalStateInspection()
    latest = latest_state_path(Path(output_directory))
    if latest is None:
        inspection.problems.append("no state_turn_*.json exists in the output")
        return inspection

    index, path = latest
    inspection.path = str(path)
    inspection.turn_index = index
    try:
        inspection.sha256 = sha256_file(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        inspection.problems.append(f"the final state could not be read: {exc}")
        return inspection
    if not isinstance(payload, dict):
        inspection.problems.append("the final state is not a JSON object")
        return inspection
    inspection.parseable = True

    meta = payload.get("session_meta")
    if not isinstance(meta, dict):
        inspection.problems.append("the final state has no session_meta object")
        meta = {}
    inspection.session_id = meta.get("id")
    inspection.total_turns = meta.get("total_turns")
    inspection.current_section_index = meta.get("current_section_index")

    if session_id and inspection.session_id and \
            inspection.session_id != session_id:
        inspection.problems.append(
            f"the final state belongs to session {inspection.session_id!r} but this "
            f"job is {session_id!r}")

    guide = payload.get("discussion_guide")
    if not isinstance(guide, list) or not guide:
        inspection.problems.append(
            "the final state has no discussion_guide list; completion cannot be "
            "established from it")
    else:
        inspection.guide_sections_total = len(guide)
        completed = [s for s in guide
                     if isinstance(s, dict) and s.get("completed") is True]
        inspection.guide_sections_completed = len(completed)
        inspection.all_sections_completed = len(completed) == len(guide)

    state_entries = payload.get("transcript")
    if isinstance(state_entries, list):
        inspection.state_transcript_entries = len(state_entries)
    else:
        inspection.problems.append("the final state carries no transcript list")
        state_entries = []

    if isinstance(inspection.total_turns, int):
        # The file index and the recorded turn count come from the same run; a gap of
        # more than one means the state and its file name disagree about where the
        # session got to.
        inspection.turn_index_coherent = abs(inspection.total_turns - index) <= 1
        if not inspection.turn_index_coherent:
            inspection.problems.append(
                f"state_turn_{index}.json records total_turns="
                f"{inspection.total_turns}; the file index and the state disagree")
    else:
        inspection.problems.append("session_meta.total_turns is missing")

    if transcript_entries is not None:
        match, reason = compare_transcripts(transcript_entries, state_entries)
        if not match:
            inspection.problems.append(reason)
    return inspection


@dataclass
class TerminalRecord:
    schema_version: str = SCHEMA_VERSION
    job_id: str = ""
    session_id: str = ""
    worker_pid: int | None = None
    cli_pid: int | None = None
    command: list[str] = field(default_factory=list)
    command_hash: str = ""
    config_path: str = ""
    config_sha256: str = ""
    started_utc: str = ""
    completed_utc: str = ""
    exit_code: int | None = None
    termination_kind: str = TerminationKind.UNKNOWN.value
    transcript_exists: bool = False
    transcript_sha256: str = ""
    transcript_parseable: bool = False
    final_state_path: str = ""
    final_state_sha256: str = ""
    guide_completion_status: str = ""
    max_turns_reached: bool = False
    completion_quality: str = CompletionQuality.UNKNOWN.value
    failure_reason: str = ""
    # ---- Phase 3F: structured completion
    final_state_parseable: bool = False
    final_state_session_id: str | None = None
    final_state_turn_index: int | None = None
    final_state_total_turns: int | None = None
    guide_sections_total: int | None = None
    guide_sections_completed: int | None = None
    structured_guide_completed: bool | None = None
    stdout_completion_marker_found: bool = False
    completion_evidence: str = CompletionEvidence.INSUFFICIENT_EVIDENCE.value
    transcript_state_match: bool | None = None
    transcript_state_mismatch_reason: str = ""
    final_state_problems: list[str] = field(default_factory=list)

    @property
    def clean_exit(self) -> bool:
        return (self.exit_code == 0
                and self.termination_kind == TerminationKind.NORMAL_EXIT.value)

    @property
    def usable_output(self) -> bool:
        """
        The conditions COMPLETED needs.

        A transcript that disagrees with the state blocks this, and so does
        conflicting evidence: neither is a run whose output can be used without
        someone looking at it first.
        """
        if self.transcript_state_match is False:
            return False
        if self.completion_evidence == CompletionEvidence.CONFLICTING_EVIDENCE.value:
            return False
        if self.completion_evidence == CompletionEvidence.STDOUT_ONLY_LEGACY.value:
            # A verdict that rests on a regex over a print statement is exactly what
            # Phase 3F stopped trusting. Accepting it as final here would have let the
            # old authority back in through the loader.
            return False
        return (self.clean_exit and self.transcript_exists
                and self.transcript_parseable
                and self.completion_quality in (
                    CompletionQuality.GUIDE_COMPLETED.value,
                    CompletionQuality.MAX_TURNS_REACHED.value))

    @property
    def potentially_incomplete(self) -> bool:
        return self.completion_quality == CompletionQuality.MAX_TURNS_REACHED.value

    @property
    def needs_review(self) -> bool:
        return (self.completion_evidence
                == CompletionEvidence.CONFLICTING_EVIDENCE.value
                or self.transcript_state_match is False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["clean_exit"] = self.clean_exit
        d["usable_output"] = self.usable_output
        d["potentially_incomplete"] = self.potentially_incomplete
        d["needs_review"] = self.needs_review
        return d


# Fields whose value decides a gate. A record carrying "no" or "maybe" here used to
# slip past `is False` / `== CONFLICTING_EVIDENCE` and be treated as benign - the
# fail-open direction on the one check that stops a bad run being imported.
_TRISTATE_FIELDS = ("transcript_state_match", "structured_guide_completed")


def record_from_dict(payload: dict) -> TerminalRecord:
    if not isinstance(payload, dict):
        raise ValueError("a terminal record must be a JSON object")
    known = set(TerminalRecord.__dataclass_fields__)
    cleaned = {k: v for k, v in payload.items() if k in known}
    problems = []
    for name in _TRISTATE_FIELDS:
        value = cleaned.get(name)
        if value is not None and not isinstance(value, bool):
            problems.append(f"{name} was {value!r}, which is neither true, false nor "
                            f"absent; it is read as unestablished")
            cleaned[name] = None
    record = TerminalRecord(**cleaned)
    if problems:
        record.final_state_problems = list(record.final_state_problems) + problems
    return record


def load_terminal_record(path: str | Path) -> TerminalRecord | None:
    target = Path(path)
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        record = record_from_dict(payload)
    except (json.JSONDecodeError, TypeError, ValueError, OSError, AttributeError,
            UnicodeDecodeError):
        # An unreadable record is ABSENT, not fatal. It used to propagate out of
        # `observe()` and take down the whole observation pass, so one corrupt file
        # blanked every job in the project. A job with no readable record is resolved
        # by the no-record path, which is what that path is for.
        return None
    # A record written before 3F carries no structured fields. It stays exactly as
    # written - its hashes are not recomputed and its quality is not revised - but it
    # is labelled so a reader knows what the claim rests on.
    if "completion_evidence" not in payload:
        record.completion_evidence = CompletionEvidence.STDOUT_ONLY_LEGACY.value
        record.failure_reason = (record.failure_reason or "") + (
            "" if record.failure_reason else "")
    return record


def _as_int(value):
    """
    An int, or None. NEVER a raise.

    `max_turns` arrives from a JSON record and from argparse. A string "15" raised
    TypeError here while the worker's own copy coerced it and capped the run - the two
    implementations then disagreed on COMPLETED versus FAILED for the same directory.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def classify(*, exit_code: int | None, termination_kind: str,
             transcript_exists: bool, transcript_parseable: bool,
             inspection: FinalStateInspection, stdout_text: str,
             max_turns: int | None = None) -> dict:
    """
    Decide the completion quality and how well it is evidenced.

    The state is the authority; stdout corroborates. Where they disagree the answer
    is CONFLICTING_EVIDENCE and the quality is PARTIAL_OUTPUT - never the completion
    one of them claims.
    """
    completed_marker = GUIDE_COMPLETED_MARKER.search(stdout_text or "")
    capped_marker = MAX_TURNS_MARKER.search(stdout_text or "")
    marker_found = bool(completed_marker or capped_marker)

    out = {
        "stdout_completion_marker_found": marker_found,
        "structured_guide_completed": (inspection.all_sections_completed
                                       if inspection.parseable else None),
        "max_turns_reached": bool(capped_marker),
        "guide_completion_status": "",
        "completion_quality": CompletionQuality.UNKNOWN.value,
        "completion_evidence": CompletionEvidence.INSUFFICIENT_EVIDENCE.value,
    }

    if not transcript_exists:
        out["completion_quality"] = CompletionQuality.PARTIAL_OUTPUT.value
        out["guide_completion_status"] = "no transcript was written"
        return out
    if not transcript_parseable:
        out["completion_quality"] = CompletionQuality.INVALID_OUTPUT.value
        out["guide_completion_status"] = "the transcript does not parse"
        return out

    if not inspection.usable:
        # No trustworthy state. A stdout marker alone is not upgraded to completion.
        out["completion_quality"] = CompletionQuality.PARTIAL_OUTPUT.value
        out["completion_evidence"] = (
            CompletionEvidence.CONFLICTING_EVIDENCE.value
            if (marker_found and inspection.parseable and inspection.problems)
            else CompletionEvidence.INSUFFICIENT_EVIDENCE.value)
        out["guide_completion_status"] = (
            "; ".join(inspection.problems)
            or "no usable final state; completion could not be established")
        return out

    all_done = inspection.all_sections_completed
    cap_hit = bool(capped_marker) or (
        _as_int(max_turns) is not None
        and isinstance(inspection.total_turns, int)
        and inspection.total_turns >= _as_int(max_turns))

    if all_done and capped_marker and not completed_marker:
        out["completion_quality"] = CompletionQuality.PARTIAL_OUTPUT.value
        out["completion_evidence"] = CompletionEvidence.CONFLICTING_EVIDENCE.value
        out["guide_completion_status"] = (
            "the final state reports every section completed, but the output "
            "announces the safety cap")
        return out
    if not all_done and completed_marker:
        out["completion_quality"] = CompletionQuality.PARTIAL_OUTPUT.value
        out["completion_evidence"] = CompletionEvidence.CONFLICTING_EVIDENCE.value
        out["guide_completion_status"] = (
            f"the output announces natural completion, but "
            f"{inspection.guide_sections_completed} of "
            f"{inspection.guide_sections_total} sections are marked completed")
        return out

    if all_done:
        out["completion_quality"] = CompletionQuality.GUIDE_COMPLETED.value
        out["completion_evidence"] = (
            CompletionEvidence.STDOUT_CORROBORATED.value if completed_marker
            else CompletionEvidence.STRUCTURED_STATE.value)
        out["guide_completion_status"] = (
            f"all {inspection.guide_sections_total} guide section(s) are marked "
            f"completed in the final state")
        return out

    if cap_hit:
        out["completion_quality"] = CompletionQuality.MAX_TURNS_REACHED.value
        out["max_turns_reached"] = True
        out["completion_evidence"] = (
            CompletionEvidence.STDOUT_CORROBORATED.value if capped_marker
            else CompletionEvidence.STRUCTURED_STATE.value)
        out["guide_completion_status"] = (
            f"{inspection.guide_sections_completed} of "
            f"{inspection.guide_sections_total} section(s) completed; the run "
            f"stopped at the safety cap")
        return out

    out["completion_quality"] = CompletionQuality.PARTIAL_OUTPUT.value
    out["completion_evidence"] = CompletionEvidence.STRUCTURED_STATE.value
    out["guide_completion_status"] = (
        f"{inspection.guide_sections_completed} of "
        f"{inspection.guide_sections_total} section(s) completed and no safety cap "
        f"was reported; the session ended before the guide finished")
    return out


def inspect_output(output_directory: Path, stdout_text: str, *,
                   session_id: str = "", max_turns: int | None = None) -> dict:
    """Everything the worker can establish from outside the architecture."""
    directory = Path(output_directory)
    result = {
        "transcript_exists": False, "transcript_sha256": "",
        "transcript_parseable": False, "final_state_path": "",
        "final_state_sha256": "", "n_transcript_entries": None,
    }
    entries = None
    transcript = directory / "transcript.json"
    if transcript.is_file():
        result["transcript_exists"] = True
        result["transcript_sha256"] = sha256_file(transcript)
        try:
            payload = json.loads(transcript.read_text(encoding="utf-8"))
            candidate = (payload if isinstance(payload, list)
                         else payload.get("transcript"))
            if isinstance(candidate, list) and candidate:
                result["transcript_parseable"] = True
                result["n_transcript_entries"] = len(candidate)
                entries = candidate
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            result["transcript_parseable"] = False

    inspection = inspect_final_state(directory, session_id=session_id,
                                     transcript_entries=entries)
    result["final_state_path"] = inspection.path
    result["final_state_sha256"] = inspection.sha256
    result["final_state_parseable"] = inspection.parseable
    result["final_state_session_id"] = inspection.session_id
    result["final_state_turn_index"] = inspection.turn_index
    result["final_state_total_turns"] = inspection.total_turns
    result["guide_sections_total"] = inspection.guide_sections_total
    result["guide_sections_completed"] = inspection.guide_sections_completed
    result["final_state_problems"] = list(inspection.problems)

    if entries is not None and inspection.parseable:
        match, reason = compare_transcripts(
            entries, json.loads(Path(inspection.path).read_text(
                encoding="utf-8")).get("transcript") if inspection.path else [])
        result["transcript_state_match"] = match
        result["transcript_state_mismatch_reason"] = "" if match else reason
    else:
        result["transcript_state_match"] = None
        result["transcript_state_mismatch_reason"] = (
            "the comparison could not be made")

    result.update(classify(
        exit_code=None, termination_kind="", transcript_exists=result[
            "transcript_exists"],
        transcript_parseable=result["transcript_parseable"],
        inspection=inspection, stdout_text=stdout_text, max_turns=max_turns))
    return result
