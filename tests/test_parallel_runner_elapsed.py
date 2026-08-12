"""
Regression tests for per-session elapsed timing in scripts/run_parallel_sessions.py.

THE BUG THIS PINS DOWN:
    The wait loop used to be `for r in running: r["proc"].wait()`, with elapsed
    stamped in the `finally:`. wait() blocks in list order, so a session that
    finished early had its elapsed stamped only once every session ahead of it
    in the list had ALSO finished — inflating it to the slower session's
    duration.

    Observed impact on real runs: macho_meals_fg1_run02 truly ran ~26m29s but
    was reported as 43m05s (+17.5 min). Worse, because both sessions' elapsed
    collapsed onto the slowest, the derived "sequential baseline" (2 x each
    session's own duration) was always exactly 2 x the wall-clock, so the
    reported speedup was exactly 2.00x on every single run — a tautology, not a
    measurement. True speedups were 1.61x-1.95x.

    The fix is a round-robin non-blocking poll() loop that stamps each process
    at the moment it is observed to have exited.

These tests use fake process objects, so no subprocess is ever spawned.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.run_parallel_sessions as runner


class FakeProc:
    """A process that reports 'still running' for `alive_polls` polls, then exits."""

    def __init__(self, pid, alive_polls, rc=0):
        self.pid = pid
        self._left = alive_polls
        self._rc = rc
        self.terminated = False

    def poll(self):
        if self._left > 0:
            self._left -= 1
            return None
        return self._rc

    def terminate(self):
        self.terminated = True


class FakeHandle:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _run_wait_loop(procs, monkeypatch):
    """
    Drive the REAL runner.wait_for_all(), with a fake clock that advances by a
    known amount per poll round so elapsed values are exactly predictable.

    Calling the production function (rather than a copy of its logic) is the
    point: if anyone reverts it to a blocking sequential wait, these tests fail.
    """
    clock = {"t": 0.0}
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(runner.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

    running = [{"sid": f"s{i}", "proc": p, "handle": FakeHandle(),
                "log": Path(f"s{i}.log"), "start": 0.0}
               for i, p in enumerate(procs)]

    assert runner.wait_for_all(running) == "ok"
    return running


def test_fast_session_is_not_inflated_by_a_slower_one_ahead_of_it(monkeypatch):
    """
    THE core regression. Session 0 is slow (50 polls), session 1 is fast (5).
    Under the old blocking-wait code both reported the SAME elapsed. They must
    now differ, with the fast one substantially shorter.
    """
    slow = FakeProc(pid=1, alive_polls=50)
    fast = FakeProc(pid=2, alive_polls=5)

    running = _run_wait_loop([slow, fast], monkeypatch)
    slow_elapsed = running[0]["elapsed"]
    fast_elapsed = running[1]["elapsed"]

    assert fast_elapsed < slow_elapsed, (
        f"fast session inflated to the slow one: {fast_elapsed} vs {slow_elapsed}")
    # 5 polls at 0.2s of simulated sleep between rounds.
    assert fast_elapsed == pytest.approx(5 * runner._POLL_INTERVAL_SECONDS, abs=1e-9)
    assert slow_elapsed == pytest.approx(50 * runner._POLL_INTERVAL_SECONDS, abs=1e-9)


def test_ordering_in_the_list_does_not_change_measured_durations(monkeypatch):
    """
    The old bug was order-dependent: the fast session was only inflated when it
    sat AFTER a slower one. Durations must now be identical either way.
    """
    a = _run_wait_loop([FakeProc(1, 50), FakeProc(2, 5)], monkeypatch)
    b = _run_wait_loop([FakeProc(2, 5), FakeProc(1, 50)], monkeypatch)

    assert sorted(r["elapsed"] for r in a) == pytest.approx(
        sorted(r["elapsed"] for r in b))


def test_speedup_is_not_forced_to_exactly_2x(monkeypatch):
    """
    Guards the specific false signal the bug produced: with both elapsed values
    collapsed onto the slowest, sequential/parallel was exactly 2.00x every run.
    With real durations it must not be.
    """
    running = _run_wait_loop([FakeProc(1, 50), FakeProc(2, 25)], monkeypatch)
    durations = [r["elapsed"] for r in running]
    wall = max(durations)
    speedup = sum(durations) / wall

    assert speedup == pytest.approx(1.5, abs=1e-6)
    assert speedup != pytest.approx(2.0, abs=1e-6)


def test_all_handles_closed_and_return_codes_captured(monkeypatch):
    running = _run_wait_loop([FakeProc(1, 3, rc=0), FakeProc(2, 7, rc=1)], monkeypatch)
    assert [r["rc"] for r in running] == [0, 1]
    assert all(r["handle"].closed for r in running)
    assert all("elapsed" in r for r in running)


def test_poll_interval_is_small_enough_to_be_accurate():
    """A coarse interval would reintroduce measurable error on long runs."""
    assert runner._POLL_INTERVAL_SECONDS <= 1.0
