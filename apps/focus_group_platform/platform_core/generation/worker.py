"""
The session worker. Runs as its own process; the CLI is its child.

    python worker.py --job-id J --session-id S --config C --config-sha256 H
                     --cli <run_full_session.py> --max-turns N [--mode M]
                     --output-dir O --terminal-record T --stdout L

WHY A WORKER AT ALL. Somebody has to be alive when the CLI exits, to see the exit
code and write it down. Without that, the platform is left inferring completion from
files the architecture writes as it goes - which is how a crashed run gets reported as
a finished one.

STDLIB ONLY. No `platform_core` import, no third-party package. The worker is invoked
by absolute path from an arbitrary working directory, and it must not depend on the
application being importable to do its one job.

IT RE-VERIFIES THE CONFIG. The bytes are hashed again here, in the worker, after the
launcher has handed over. A config that changed between confirmation and execution
never reaches the architecture.

IT NEVER TOUCHES CREDENTIALS. The child inherits the environment; the worker does not
read, log or pass any key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "1.1.0"

NORMAL_EXIT = "NORMAL_EXIT"
NONZERO_EXIT = "NONZERO_EXIT"
USER_CANCELLED = "USER_CANCELLED"
WORKER_INTERRUPTED = "WORKER_INTERRUPTED"
PROCESS_LOST = "PROCESS_LOST"
UNKNOWN = "UNKNOWN"

GUIDE_COMPLETED = "GUIDE_COMPLETED"
MAX_TURNS_REACHED = "MAX_TURNS_REACHED"
PARTIAL_OUTPUT = "PARTIAL_OUTPUT"
INVALID_OUTPUT = "INVALID_OUTPUT"

GUIDE_COMPLETED_MARKER = re.compile(r"Guide completed naturally after (\d+) steps")
MAX_TURNS_MARKER = re.compile(r"SAFETY CAP HIT at (\d+) steps")
STATE_TURN = re.compile(r"^state_turn_(\d+)\.json$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_config_sha256(path: Path) -> str:
    """
    Hash the config the way the plan hashed it: canonical JSON, sorted keys.

    Hashing raw bytes would make an identical config with different whitespace look
    like tampering, and the plan's hash is over the parsed structure.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def write_atomic(path: Path, text: str) -> None:
    """Temp file in the same directory, fsync, then replace. Never a partial record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


TRANSCRIPT_FIELDS = ("turn", "speaker_id", "speaker_name", "content")

STRUCTURED_STATE = "STRUCTURED_STATE"
STDOUT_CORROBORATED = "STDOUT_CORROBORATED"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _canonical(entries):
    """Turn, speaker and content, in order. Serialisation is not identity."""
    out = []
    for entry in entries or []:
        if isinstance(entry, dict):
            out.append(tuple(
                str(entry.get(f)) if entry.get(f) is not None else None
                for f in TRANSCRIPT_FIELDS))
    return out


def _compare_transcripts(file_entries, state_entries):
    left, right = _canonical(file_entries), _canonical(state_entries)
    dropped = sum(1 for e in (file_entries or []) if not isinstance(e, dict))
    dropped += sum(1 for e in (state_entries or []) if not isinstance(e, dict))
    if dropped:
        # A malformed entry is not agreement. See terminal.compare_transcripts.
        return False, (f"{dropped} transcript entr(ies) are not objects and could not "
                       f"be compared; coherence is not established")
    if not left and not right:
        return False, "neither transcript carries entries"
    if len(left) != len(right):
        return False, (f"transcript.json has {len(left)} intervention(s) and the "
                       f"final state has {len(right)}")
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            differing = [n for n, x, y in zip(TRANSCRIPT_FIELDS, a, b) if x != y]
            return False, f"intervention {index} differs on {differing}"
    return True, ""


def inspect_output(output_directory: Path, stdout_text: str, *,
                   session_id: str = "", max_turns=None) -> dict:
    """
    THE STRUCTURED FINAL STATE IS THE AUTHORITY. Stdout corroborates it.

    Duplicated from `terminal.py` rather than imported: the worker is stdlib-only and
    must run without the application being importable. A test asserts the two agree
    on the real smoke-run outputs.
    """
    result = {
        "transcript_exists": False, "transcript_sha256": "",
        "transcript_parseable": False, "final_state_path": "",
        "final_state_sha256": "", "final_state_parseable": False,
        "final_state_session_id": None, "final_state_turn_index": None,
        "final_state_total_turns": None, "guide_sections_total": None,
        "guide_sections_completed": None, "structured_guide_completed": None,
        "stdout_completion_marker_found": False,
        "completion_evidence": INSUFFICIENT_EVIDENCE,
        "transcript_state_match": None, "transcript_state_mismatch_reason": "",
        "final_state_problems": [], "guide_completion_status": "",
        "max_turns_reached": False, "completion_quality": UNKNOWN,
        "n_transcript_entries": None,
    }

    entries = None
    transcript = output_directory / "transcript.json"
    if transcript.is_file():
        result["transcript_exists"] = True
        try:
            # The hash was computed OUTSIDE this guard, and a payload of `null` made
            # `payload.get` raise AttributeError. Either killed the worker before it
            # wrote the record, leaving a session that really ran with no evidence at
            # all - the one outcome this process exists to prevent.
            result["transcript_sha256"] = _sha256(transcript)
            payload = json.loads(transcript.read_text(encoding="utf-8"))
            candidate = (payload.get("transcript")
                         if isinstance(payload, dict) else payload)
            if isinstance(candidate, list) and candidate:
                result["transcript_parseable"] = True
                entries = candidate
                result["n_transcript_entries"] = len(candidate)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError,
                AttributeError, TypeError, ValueError):
            result["transcript_parseable"] = False

    states = []
    for child in output_directory.glob("state_turn_*.json"):
        match = STATE_TURN.match(child.name)
        if match:
            states.append((int(match.group(1)), child))
    problems = []
    all_done = None
    state_entries = []
    if not states:
        problems.append("no state_turn_*.json exists in the output")
    else:
        index, path = max(states, key=lambda t: t[0])
        result["final_state_path"] = str(path)
        result["final_state_turn_index"] = index
        state = None
        try:
            result["final_state_sha256"] = _sha256(path)
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"the final state could not be read: {exc}")
        if isinstance(state, dict):
            result["final_state_parseable"] = True
            meta = state.get("session_meta")
            meta = meta if isinstance(meta, dict) else {}
            result["final_state_session_id"] = meta.get("id")
            result["final_state_total_turns"] = meta.get("total_turns")
            if session_id and meta.get("id") and meta.get("id") != session_id:
                problems.append(
                    f"the final state belongs to session {meta.get('id')!r} but "
                    f"this job is {session_id!r}")
            guide = state.get("discussion_guide")
            if isinstance(guide, list) and guide:
                completed = [x for x in guide
                             if isinstance(x, dict) and x.get("completed") is True]
                result["guide_sections_total"] = len(guide)
                result["guide_sections_completed"] = len(completed)
                all_done = len(completed) == len(guide)
                result["structured_guide_completed"] = all_done
            else:
                problems.append("the final state has no discussion_guide list")
            state_entries = state.get("transcript")
            if not isinstance(state_entries, list):
                problems.append("the final state carries no transcript list")
                state_entries = []
            total = meta.get("total_turns")
            if isinstance(total, int):
                if abs(total - index) > 1:
                    problems.append(
                        f"state_turn_{index}.json records total_turns={total}; the "
                        f"file index and the state disagree")
            else:
                problems.append("session_meta.total_turns is missing")
        elif state is not None:
            problems.append("the final state is not a JSON object")

    if entries is not None and result["final_state_parseable"]:
        match, reason = _compare_transcripts(entries, state_entries)
        result["transcript_state_match"] = match
        result["transcript_state_mismatch_reason"] = "" if match else reason
        if not match:
            problems.append(reason)
    result["final_state_problems"] = problems

    completed_marker = GUIDE_COMPLETED_MARKER.search(stdout_text or "")
    capped_marker = MAX_TURNS_MARKER.search(stdout_text or "")
    result["stdout_completion_marker_found"] = bool(completed_marker
                                                    or capped_marker)
    result["max_turns_reached"] = bool(capped_marker)

    if not result["transcript_exists"]:
        result["completion_quality"] = PARTIAL_OUTPUT
        result["guide_completion_status"] = "no transcript was written"
        return result
    if not result["transcript_parseable"]:
        result["completion_quality"] = INVALID_OUTPUT
        result["guide_completion_status"] = "the transcript does not parse"
        return result

    usable_state = result["final_state_parseable"] and not problems
    if not usable_state:
        result["completion_quality"] = PARTIAL_OUTPUT
        result["completion_evidence"] = (
            CONFLICTING_EVIDENCE
            if (result["stdout_completion_marker_found"]
                and result["final_state_parseable"] and problems)
            else INSUFFICIENT_EVIDENCE)
        result["guide_completion_status"] = ("; ".join(problems)
                                             or "no usable final state")
        return result

    cap = None
    if max_turns is not None and not isinstance(max_turns, bool):
        try:
            cap = int(max_turns)
        except (TypeError, ValueError):
            cap = None
    cap_hit = bool(capped_marker) or (
        cap is not None
        and isinstance(result["final_state_total_turns"], int)
        and result["final_state_total_turns"] >= cap)

    if all_done and capped_marker and not completed_marker:
        result["completion_quality"] = PARTIAL_OUTPUT
        result["completion_evidence"] = CONFLICTING_EVIDENCE
        result["guide_completion_status"] = (
            "the final state reports every section completed, but the output "
            "announces the safety cap")
    elif all_done is False and completed_marker:
        result["completion_quality"] = PARTIAL_OUTPUT
        result["completion_evidence"] = CONFLICTING_EVIDENCE
        result["guide_completion_status"] = (
            f"the output announces natural completion, but "
            f"{result['guide_sections_completed']} of "
            f"{result['guide_sections_total']} sections are marked completed")
    elif all_done:
        result["completion_quality"] = GUIDE_COMPLETED
        result["completion_evidence"] = (STDOUT_CORROBORATED if completed_marker
                                         else STRUCTURED_STATE)
        result["guide_completion_status"] = (
            f"all {result['guide_sections_total']} guide section(s) are marked "
            f"completed in the final state")
    elif cap_hit:
        result["completion_quality"] = MAX_TURNS_REACHED
        result["max_turns_reached"] = True
        result["completion_evidence"] = (STDOUT_CORROBORATED if capped_marker
                                         else STRUCTURED_STATE)
        result["guide_completion_status"] = (
            f"{result['guide_sections_completed']} of "
            f"{result['guide_sections_total']} section(s) completed; the run "
            f"stopped at the safety cap")
    else:
        result["completion_quality"] = PARTIAL_OUTPUT
        result["completion_evidence"] = STRUCTURED_STATE
        result["guide_completion_status"] = (
            f"{result['guide_sections_completed']} of "
            f"{result['guide_sections_total']} section(s) completed and no safety "
            f"cap was reported; the session ended before the guide finished")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one session and record how it "
                                                 "ended.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--max-turns", type=int, required=True)
    parser.add_argument("--mode", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--terminal-record", required=True)
    parser.add_argument("--stdout", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)

    record = {
        "schema_version": SCHEMA_VERSION, "job_id": args.job_id,
        "session_id": args.session_id, "worker_pid": os.getpid(),
        "cli_pid": None, "command": [], "command_hash": "",
        "config_path": args.config, "config_sha256": args.config_sha256,
        "started_utc": _now(), "completed_utc": "", "exit_code": None,
        "termination_kind": UNKNOWN, "transcript_exists": False,
        "transcript_sha256": "", "transcript_parseable": False,
        "final_state_path": "", "final_state_sha256": "",
        "guide_completion_status": "", "max_turns_reached": False,
        "completion_quality": UNKNOWN, "failure_reason": "",
        "final_state_parseable": False, "final_state_session_id": None,
        "final_state_turn_index": None, "final_state_total_turns": None,
        "guide_sections_total": None, "guide_sections_completed": None,
        "structured_guide_completed": None,
        "stdout_completion_marker_found": False,
        "completion_evidence": INSUFFICIENT_EVIDENCE,
        "transcript_state_match": None, "transcript_state_mismatch_reason": "",
        "final_state_problems": [],
    }
    terminal_path = Path(args.terminal_record)
    output_directory = Path(args.output_dir)
    stdout_path = Path(args.stdout)

    def finish(kind: str, exit_code, reason: str = "") -> int:
        record["termination_kind"] = kind
        record["exit_code"] = exit_code
        record["completed_utc"] = _now()
        record["failure_reason"] = reason
        try:
            text = stdout_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        try:
            record.update(inspect_output(output_directory, text,
                                         session_id=args.session_id,
                                         max_turns=args.max_turns))
        except Exception as exc:                               # noqa: BLE001
            # WRITING SOMETHING IS THE POINT. Inspection reads files another process
            # is still touching; if it fails, the record still has to exist, because a
            # missing record is how a session that really ran becomes unrecoverable.
            record["completion_quality"] = UNKNOWN
            record["completion_evidence"] = INSUFFICIENT_EVIDENCE
            record["final_state_problems"] = [
                f"the output could not be inspected: {type(exc).__name__}: {exc}"]
            record["guide_completion_status"] = (
                "the worker could not inspect the output; how this session ended is "
                "not established")
        if kind != NORMAL_EXIT and record["completion_quality"] in (
                GUIDE_COMPLETED, MAX_TURNS_REACHED):
            # The output looks finished but the process did not end normally. The
            # process is the authority on how it ended.
            record["completion_quality"] = PARTIAL_OUTPUT
        write_atomic(terminal_path, json.dumps(record, indent=1,
                                               ensure_ascii=False))
        return 0

    # ---- re-verify the config, in this process, immediately before launching
    config_path = Path(args.config)
    if not config_path.is_file():
        return finish(PROCESS_LOST, None,
                      f"the config {config_path} does not exist at launch time")
    try:
        actual = _canonical_config_sha256(config_path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return finish(PROCESS_LOST, None, f"the config could not be read: {exc}")
    if actual != args.config_sha256:
        return finish(
            PROCESS_LOST, None,
            f"the config changed after the plan was confirmed: expected "
            f"{args.config_sha256[:12]}…, found {actual[:12]}…. Nothing was launched.")

    command = [args.python, args.cli, "--config", str(config_path),
               "--max-turns", str(int(args.max_turns))]
    if args.mode:
        command += ["--mode", args.mode]
    record["command"] = command
    record["command_hash"] = _sha256_text(" ".join(command))

    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(stdout_path, "ab", buffering=0) as handle:
            process = subprocess.Popen(                           # noqa: S603
                command, stdout=handle, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, cwd=args.cwd, shell=False)
            record["cli_pid"] = process.pid
            write_atomic(terminal_path.with_suffix(".running.json"),
                         json.dumps(record, indent=1, ensure_ascii=False))
            exit_code = process.wait()
    except KeyboardInterrupt:
        return finish(WORKER_INTERRUPTED, None,
                      "the worker was interrupted; the child may still be running")
    except Exception as exc:                                      # noqa: BLE001
        return finish(PROCESS_LOST, None, f"the CLI could not be started: {exc}")
    finally:
        terminal_path.with_suffix(".running.json").unlink(missing_ok=True)

    if exit_code == 0:
        return finish(NORMAL_EXIT, 0)
    return finish(NONZERO_EXIT, exit_code,
                  f"the session CLI exited with code {exit_code}; see the captured "
                  f"output")


if __name__ == "__main__":
    raise SystemExit(main())
