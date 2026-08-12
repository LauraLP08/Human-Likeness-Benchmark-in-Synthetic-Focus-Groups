"""
Launch N independent full-session runs concurrently, as separate OS processes.

Scope is process management only: launch, wait, report. No session logic lives
here — each child is an ordinary `scripts/run_full_session.py` invocation, so
this script never needs to know anything about orchestrators, prompts or state.

Why a new script rather than concurrency inside run_batch.py: run_batch.py is
sequential by design and other workflows depend on it. Adding a standalone
launcher leaves every existing tested file untouched.

Safety of running sessions concurrently was verified by tracing the write paths
(see INSTRUCTIONS_MODERATOR_SYNTHESIS_FIX_AND_PARALLEL_RUNNER.md §B.3):
orchestrator.log_dir is `output/session_logs/<session_id>` — derived purely from
the config's session_id, with no timestamp component — and every file written
(transcript.json, transcript.txt, moderator_log.json, api_calls.jsonl,
state_turn_N.json) hangs off that directory. There is no module-level file
handle, lockfile or shared counter anywhere in core/. Distinct session_ids
therefore cannot collide, even when launched in the same instant.

Usage:
    python scripts/run_parallel_sessions.py \
      --config configs/experiment/macho_meals_fg1_run01.json \
      --config configs/experiment/macho_meals_fg1_run02.json \
      --config configs/experiment/macho_meals_fg1_run03.json \
      [--max-turns 90]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_ROOT = _REPO_ROOT / "output" / "session_logs"
_RUNNER = _REPO_ROOT / "scripts" / "run_full_session.py"

# How often to re-check each child for exit. Small enough that the recorded
# elapsed is accurate to well under a second on runs lasting tens of minutes,
# large enough that polling costs nothing.
_POLL_INTERVAL_SECONDS = 0.2


def _read_session_id(config_path: Path) -> str:
    """Read session_id up front — never launch blind."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    session_id = data.get("session_id")
    if not session_id:
        raise ValueError(f"{config_path}: config has no 'session_id'")
    return session_id


def wait_for_all(running: list[dict]) -> str:
    """
    Wait for every launched session, recording each one's own true duration.

    Round-robin non-blocking poll, NOT a sequential `for r: r["proc"].wait()`.
    With a blocking wait in list order, a session that finished early has its
    elapsed stamped only once every session ahead of it in the list has ALSO
    finished, silently inflating it to the slower one's duration. On real runs
    that overstated a session by up to 17 minutes, and — because both sessions'
    elapsed collapsed onto the slowest — made the derived speedup come out as
    exactly 2.00x every single time: an artifact, not a measurement.

    Mutates each entry in `running` with "rc" and "elapsed" (and "error" if
    polling itself raised). Returns "interrupted" if the launcher caught a
    KeyboardInterrupt, else "ok".
    """
    pending = list(running)
    try:
        while pending:
            still_running = []
            for r in pending:
                try:
                    rc = r["proc"].poll()
                except Exception as exc:              # noqa: BLE001
                    r["rc"] = None
                    r["error"] = repr(exc)
                    r["elapsed"] = time.monotonic() - r["start"]
                    r["handle"].close()
                    continue
                if rc is None:
                    still_running.append(r)
                    continue
                # Stamp the moment THIS process was observed to exit.
                r["rc"] = rc
                r["elapsed"] = time.monotonic() - r["start"]
                r["handle"].close()
            pending = still_running
            if pending:
                time.sleep(_POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        # Don't leave orphans behind if the launcher itself is interrupted.
        print("\nInterrupted — terminating child sessions...", file=sys.stderr)
        for other in pending:
            if other["proc"].poll() is None:
                other["proc"].terminate()
        for other in pending:
            other.setdefault("rc", None)
            other.setdefault("elapsed", time.monotonic() - other["start"])
            other["handle"].close()
        return "interrupted"
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run multiple full sessions concurrently as separate processes."
    )
    parser.add_argument("--config", action="append", required=True, metavar="PATH",
                        help="Path to a session config JSON. Repeatable; minimum 2.")
    parser.add_argument("--max-turns", type=int, default=90,
                        help="Safety cap passed through to each session (default 90).")
    args = parser.parse_args()

    config_paths = [Path(c) for c in args.config]
    if len(config_paths) < 2:
        parser.error("--config must be given at least twice (this is a parallel runner).")

    # ---- Pre-flight: resolve everything before spending anything -----------
    missing = [p for p in config_paths if not p.is_file()]
    if missing:
        for p in missing:
            print(f"ERROR: config not found: {p}", file=sys.stderr)
        return 2

    try:
        sessions = [(p, _read_session_id(p)) for p in config_paths]
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    ids = [sid for _, sid in sessions]
    dupes = {s for s in ids if ids.count(s) > 1}
    if dupes:
        # Two configs sharing a session_id would write into one directory and
        # corrupt each other — the one failure mode directory isolation cannot
        # protect against.
        print(f"ERROR: duplicate session_id across configs: {sorted(dupes)}", file=sys.stderr)
        return 2

    print(f"Launching {len(sessions)} sessions concurrently (max-turns={args.max_turns}):")
    for path, sid in sessions:
        print(f"  {sid:<40} <- {path}")
    print()

    # ---- Launch -----------------------------------------------------------
    running = []
    for path, sid in sessions:
        out_dir = _OUTPUT_ROOT / sid
        out_dir.mkdir(parents=True, exist_ok=True)
        log_file = out_dir / "launcher_stdout.log"
        handle = log_file.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(_RUNNER),
             "--config", str(path),
             "--max-turns", str(args.max_turns)],
            cwd=str(_REPO_ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        running.append({"sid": sid, "path": path, "proc": proc,
                        "handle": handle, "log": log_file,
                        "start": time.monotonic()})
        print(f"  started pid={proc.pid:<7} {sid}  -> {log_file.relative_to(_REPO_ROOT)}")

    print("\nWaiting for all sessions to finish...\n")

    # ---- Wait -------------------------------------------------------------
    if wait_for_all(running) == "interrupted":
        return 130

    # ---- Report -----------------------------------------------------------
    # Exit code alone does not prove a session produced data — check the file.
    print("=" * 88)
    print(f"{'session_id':<40}{'exit':>6}{'elapsed':>12}{'transcript.json':>20}")
    print("-" * 88)
    ok = 0
    for r in running:
        tpath = _OUTPUT_ROOT / r["sid"] / "transcript.json"
        if tpath.is_file() and tpath.stat().st_size > 2:      # "[]" is 2 bytes
            transcript = f"OK ({tpath.stat().st_size:,} B)"
            wrote = True
        elif tpath.is_file():
            transcript = "EMPTY"
            wrote = False
        else:
            transcript = "MISSING"
            wrote = False
        mins, secs = divmod(int(r["elapsed"]), 60)
        rc = r.get("rc")
        if rc == 0 and wrote:
            ok += 1
        print(f"{r['sid']:<40}{str(rc):>6}{f'{mins}m{secs:02d}s':>12}{transcript:>20}")
    print("-" * 88)
    print(f"{ok}/{len(running)} session(s) completed with output.")

    for r in running:
        if r.get("error"):
            print(f"  {r['sid']}: launcher error {r['error']}", file=sys.stderr)
        elif r.get("rc") not in (0, None):
            print(f"  {r['sid']}: exited {r['rc']} — see {r['log'].relative_to(_REPO_ROOT)}",
                  file=sys.stderr)

    return 0 if ok == len(running) else 1


if __name__ == "__main__":
    raise SystemExit(main())
