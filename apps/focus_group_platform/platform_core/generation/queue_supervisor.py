"""
The process that actually advances the queue.

WHAT WAS WRONG. `queue.tick()` was correct and nothing called it. A tick happened when
a researcher reloaded the Streamlit page, so a twelve-session study advanced at the
speed of someone remembering to press F5, and a run left overnight sat at one finished
session and eleven pending ones. A scheduler that only runs while a browser tab is
open is not a scheduler.

The supervisor is a separate, long-lived process that ticks on an interval. It is
started deliberately, it holds a per-project lock so two of them cannot both launch
the same pending job, and it writes a heartbeat so the interface can tell RUNNING
from died-without-saying-so.

TWO FILES, ONE WRITER EACH. The supervisor writes `supervisor_state.json` and never
reads instructions from it; the controller (the interface, or a researcher) writes
`supervisor_control.json` and never writes state. A single file written by both would
race, and the losing write would be a lost stop request.

WHAT IT WILL NOT DO. It does not retry, restart or resurrect anything: terminal jobs
stay terminal, exactly as in `queue.tick()`. It does not launch anything while paused.
It does not start itself - no page load, no import and no test spawns a supervisor as
a side effect.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..config import APP_ROOT
from ..paths import safe_path
from ..projects import Project, load_project, open_or_resolve
from ..services import audit
from . import queue as Q
from .contracts import GenerationError

STATE_FILENAME = "supervisor_state.json"
CONTROL_FILENAME = "supervisor_control.json"
LOG_FILENAME = "supervisor.log"
LOCK_FILENAME = "supervisor.lock.json"
SCHEMA_VERSION = "3F.1"

DEFAULT_INTERVAL_SECONDS = 20.0
MIN_INTERVAL_SECONDS = 2.0
MAX_INTERVAL_SECONDS = 600.0
# A heartbeat older than this, with the process still alive, means the loop is stuck
# rather than working. Three missed intervals, floored, so a slow tick is not called a
# hang the first time it runs long.
STALE_AFTER_INTERVALS = 3
MIN_STALE_SECONDS = 60.0
# How patiently an existing lock is re-read before it is called corrupt. Covers the
# create-then-write window of a supervisor that is starting at the same moment.
READ_LOCK_ATTEMPTS = 5
READ_LOCK_RETRY_SECONDS = 0.2
TAKEOVER_ATTEMPTS = 3
# A supervisor is not an unattended service. It stops on its own after this long so a
# forgotten process cannot keep launching paid work for days.
MAX_LIFETIME_SECONDS = 12 * 3600


class SupervisorState(str, Enum):
    NOT_STARTED = "NOT_STARTED"          # no supervisor has ever run for this project
    RUNNING = "RUNNING"                  # alive, heartbeat fresh, ticking
    PAUSED = "PAUSED"                    # alive, heartbeat fresh, launching nothing
    STOPPED = "STOPPED"                  # exited after being asked to
    CRASHED = "CRASHED"                  # the process is gone and never said goodbye
    UNRESPONSIVE = "UNRESPONSIVE"        # the process is alive; the heartbeat is not


ALIVE_STATES = (SupervisorState.RUNNING.value, SupervisorState.PAUSED.value,
                SupervisorState.UNRESPONSIVE.value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _audit(project: Project, action: str, **detail) -> None:
    """Append-only, same log as every other generation act."""
    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=f"supervisor:{project.name}",
                 detail={"action": action, **detail})


def _parse(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ------------------------------------------------------------------- records
@dataclass
class SupervisorRecord:
    """What the supervisor says about itself. Only the supervisor writes it."""

    project_name: str
    # THE IDENTIFIER, not the display name. Found by the first real launch: the
    # command carried the human-readable name, and `load_project` refuses it because
    # a name with spaces is not a safe path component.
    project_id: str = ""
    supervisor_id: str = ""
    pid: int | None = None
    process_start_time: float | None = None
    python_executable: str = ""
    state: str = SupervisorState.NOT_STARTED.value
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    started_utc: str = ""
    last_heartbeat_utc: str = ""
    stopped_utc: str = ""
    stop_reason: str = ""
    tick_count: int = 0
    launched_total: int = 0
    last_tick_utc: str = ""
    last_tick_detail: dict = field(default_factory=dict)
    last_error: str = ""
    consecutive_errors: int = 0
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SupervisorControl:
    """What the researcher asks of it. Only the controller writes it."""

    pause_requested: bool = False
    stop_requested: bool = False
    requested_utc: str = ""
    requested_by: str = "interface"

    def to_dict(self) -> dict:
        return asdict(self)


def _from_dict(cls, payload: dict):
    known = set(cls.__dataclass_fields__)
    return cls(**{k: v for k, v in payload.items() if k in known})


# --------------------------------------------------------------------- paths
def _generation_dir(project: Project) -> Path:
    from .planner import generation_dir
    return generation_dir(project)


def state_path(project: Project) -> Path:
    return safe_path(_generation_dir(project), STATE_FILENAME)


def control_path(project: Project) -> Path:
    return safe_path(_generation_dir(project), CONTROL_FILENAME)


def log_path(project: Project) -> Path:
    return safe_path(_generation_dir(project), LOG_FILENAME)


def _read(path: Path, cls, **defaults):
    if not path.is_file():
        return None
    try:
        return _from_dict(cls, json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        return None


def load_state(project: Project) -> SupervisorRecord | None:
    return _read(state_path(project), SupervisorRecord)


def load_control(project: Project) -> SupervisorControl:
    return _read(control_path(project), SupervisorControl) or SupervisorControl()


def _save(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, indent=1, ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return path


def save_state(project: Project, record: SupervisorRecord) -> Path:
    return _save(state_path(project), record.to_dict())


def save_control(project: Project, control: SupervisorControl) -> Path:
    return _save(control_path(project), control.to_dict())


# ------------------------------------------------------------ process identity
def _process_signature(pid: int | None):
    """(create_time, cmdline) for a live pid, or None. psutil is required."""
    if not pid:
        return None
    try:
        import psutil
    except ImportError as exc:                                     # pragma: no cover
        raise GenerationError(
            "psutil is required to identify the supervisor process; without it a "
            "recycled pid could be mistaken for a running supervisor") from exc
    try:
        process = psutil.Process(int(pid))
        return process.create_time(), " ".join(process.cmdline() or [])
    except Exception:                                              # noqa: BLE001
        return None


def _holder_is_live_supervisor(holder: dict, signature, project: Project) -> bool:
    """
    Is the recorded holder a supervisor for THIS project that is still running?

    A bare pid is not an identity. Where the start time was never recorded, the
    command line decides - the previous version assumed "alive" in that case, which
    meant a recycled pid belonging to any unrelated program could make a project
    permanently unschedulable, the exact outcome the takeover path exists to prevent.
    """
    if signature is None:
        return False
    create_time, cmdline = signature
    recorded = holder.get("process_start_time")
    if recorded is not None and create_time is not None:
        return abs(float(create_time) - float(recorded)) <= 1.0
    # No usable start time: fall back to what the process says it is running.
    # THE PROJECT WE WERE ASKED ABOUT, not the one the lock file claims. Trusting the
    # lock's self-report meant a copied project directory carried a lock naming the
    # original, and the copy could never take a supervisor.
    identifier = project.project_id
    if not cmdline or not identifier:
        return False
    # Whole-argument match: `--project alpha` must not be satisfied by a supervisor
    # running `--project alpha_beta`.
    return ("queue_supervisor" in cmdline
            and f"--project {identifier}" in cmdline)


def lock_path(project: Project) -> Path:
    return safe_path(_generation_dir(project), LOCK_FILENAME)


class LockHeld(GenerationError):
    """Another live supervisor owns this project."""


def acquire_lock(project: Project, *, signature_of=None) -> dict:
    """
    Create the lock file exclusively, or refuse.

    `start()` also checks whether a supervisor is running, but that check and the
    spawn are two separate moments: two researchers pressing start together would both
    see nothing running. Only an exclusive create decides it, because only one caller
    can win `O_CREAT | O_EXCL`.

    A lock held by a process that no longer exists is TAKEN OVER, not honoured - a
    machine that lost power would otherwise leave a project permanently unschedulable.
    The takeover is recorded in the new lock.
    """
    target = lock_path(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    resolve = signature_of or _process_signature
    signature = resolve(os.getpid())
    payload = {
        "pid": os.getpid(),
        "process_start_time": (signature or (None, ""))[0],
        "project_name": project.name, "project_id": project.project_id,
        "acquired_utc": _now(),
        "python_executable": sys.executable, "took_over_from": None,
    }

    def _write_exclusive() -> bool:
        try:
            fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        return True

    if _write_exclusive():
        return payload

    # AN UNREADABLE LOCK IS HELD, NOT FREE. `O_CREAT | O_EXCL` is exclusive but the
    # write that follows it is not instantaneous: for the few milliseconds between the
    # create and the fsync the file is zero bytes. Treating that as "nobody owns this"
    # let a second supervisor take the lock away from one that had acquired it
    # moments earlier - which is precisely the double-launch this lock exists to stop.
    # A genuinely corrupt lock is still recoverable: it simply has to still be
    # unreadable after the writer has had time to finish.
    holder, readable = None, False
    for attempt in range(READ_LOCK_ATTEMPTS):
        try:
            holder = json.loads(target.read_text(encoding="utf-8"))
            readable = isinstance(holder, dict)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            readable = False
        if readable:
            break
        if attempt < READ_LOCK_ATTEMPTS - 1:
            time.sleep(READ_LOCK_RETRY_SECONDS)
    if not readable:
        raise LockHeld(
            f"{project.name} has a lock file that cannot be read after "
            f"{READ_LOCK_ATTEMPTS} attempts. It is treated as held: a lock that "
            f"cannot be read is not evidence that nobody owns it. Remove "
            f"{target.name} by hand once you have confirmed no supervisor is running.")

    holder_pid = holder.get("pid")
    holder_signature = resolve(holder_pid) if holder_pid else None
    holder_alive = _holder_is_live_supervisor(holder, holder_signature, project)
    if holder_alive:
        raise LockHeld(
            f"supervisor pid {holder_pid} already holds {project.name}; a second "
            f"scheduler would launch into the same free slot")

    # THE OPERATING SYSTEM DECIDES, not the last writer. Overwriting the stale lock
    # atomically was not enough: two supervisors that both found the same dead holder
    # both wrote and both continued, and a read-back only catches the interleaving
    # where the other save lands in the microseconds between this save and its own
    # re-read. Removing the stale file and racing `O_CREAT | O_EXCL` again means
    # exactly one caller can win, because only one create can succeed.
    payload["took_over_from"] = holder_pid
    for _ in range(TAKEOVER_ATTEMPTS):
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise LockHeld(
                f"the stale lock on {project.name} could not be removed: {exc}") from exc
        if _write_exclusive():
            _audit(project, "supervisor_lock_taken_over", stale_pid=holder_pid)
            return payload
        # Someone created it between the unlink and the create. If they are alive we
        # lost; if they are another corpse we go round again.
        try:
            other = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            other = {}
        if not isinstance(other, dict):
            other = {}
        other_pid = other.get("pid")
        if other_pid == os.getpid():
            return payload
        if _holder_is_live_supervisor(other, resolve(other_pid) if other_pid else None,
                                      project):
            raise LockHeld(
                f"another supervisor (pid {other_pid}) took {project.name} while this "
                f"one was claiming the same stale lock")
    raise LockHeld(
        f"the lock on {project.name} changed hands {TAKEOVER_ATTEMPTS} times while "
        f"this supervisor tried to claim it; it is not taken rather than risk two")


def lock_holder(project: Project) -> dict | None:
    """What the lock file says, or None. Read-only; never takes or frees anything."""
    target = lock_path(project)
    if not target.is_file():
        return None
    try:
        holder = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return holder if isinstance(holder, dict) else None


def release_lock(project: Project) -> bool:
    """Remove the lock only if this process holds it."""
    target = lock_path(project)
    if not target.is_file():
        return False
    try:
        holder = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        holder = {}
    if holder.get("pid") != os.getpid():
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True


def _is_our_supervisor(record: SupervisorRecord, signature_of=None) -> bool:
    """
    Pid plus start time plus the project on the command line.

    A pid alone is not an identity: the operating system reuses them, and a reused pid
    belonging to an unrelated program would otherwise be reported as a running
    supervisor and stop a real one from starting.
    """
    resolve = signature_of or _process_signature
    signature = resolve(record.pid)
    if signature is None:
        return False
    create_time, cmdline = signature
    if record.process_start_time is not None and create_time is not None:
        if abs(float(create_time) - float(record.process_start_time)) > 1.0:
            return False
    identifier = record.project_id or record.project_name
    if identifier and cmdline:
        if "queue_supervisor" not in cmdline or identifier not in cmdline:
            return False
    return True


# ------------------------------------------------------------------ observing
def observe(project: Project, *, signature_of=None,
            now: datetime | None = None) -> SupervisorRecord:
    """
    The state on disk is a claim; this re-derives it from the process table.

    A record saying RUNNING while the process is gone is the state this design
    expects to meet, not an anomaly.
    """
    record = load_state(project)
    if record is None:
        return SupervisorRecord(project_name=project.name,
                                project_id=project.project_id,
                                state=SupervisorState.NOT_STARTED.value)

    if record.state == SupervisorState.STOPPED.value:
        return record

    alive = _is_our_supervisor(record, signature_of=signature_of)
    if not alive:
        record.state = SupervisorState.CRASHED.value
        record.stop_reason = (record.stop_reason
                              or "the supervisor process is no longer running and did "
                                 "not record a stop")
        return record

    moment = now or datetime.now(UTC)
    beat = _parse(record.last_heartbeat_utc)
    stale_after = max(MIN_STALE_SECONDS,
                      STALE_AFTER_INTERVALS * float(record.interval_seconds or
                                                    DEFAULT_INTERVAL_SECONDS))
    if beat is None or (moment - beat).total_seconds() > stale_after:
        record.state = SupervisorState.UNRESPONSIVE.value
    return record


def is_running(project: Project, *, signature_of=None) -> bool:
    return observe(project, signature_of=signature_of).state in ALIVE_STATES


# ------------------------------------------------------------------- controls
def request_pause(project: Project) -> SupervisorControl:
    """Stop launching. Nothing already running is touched."""
    control = load_control(project)
    control.pause_requested = True
    control.requested_utc = _now()
    save_control(project, control)
    _audit(project, "pause_requested")
    return control


def request_resume(project: Project) -> SupervisorControl:
    control = load_control(project)
    control.pause_requested = False
    control.requested_utc = _now()
    save_control(project, control)
    _audit(project, "resume_requested")
    return control


def request_stop(project: Project) -> SupervisorControl:
    """
    Ask the loop to finish. Running sessions are NOT killed.

    Stopping the scheduler and cancelling work are different acts: a session that is
    already paid for keeps running to its end.
    """
    control = load_control(project)
    control.stop_requested = True
    control.requested_utc = _now()
    save_control(project, control)
    _audit(project, "stop_requested")
    return control


def force_release(project: Project, *, signature_of=None) -> dict:
    """
    Give up on a supervisor that is alive but not listening, and free the project.

    A wedged loop never reaches the line that reads the control file, so `request_stop`
    writes something nobody will ever read: the interface offered a remedy that could
    not work, and Start stayed disabled because the pid was alive. This does NOT kill
    the process - killing something mid-launch could orphan a paid session. It records
    that the supervisor was abandoned and releases the lock, so a new one can start.

    THE OLD PROCESS MAY STILL BE RUNNING. It holds no lock now, so if it recovers it
    could tick alongside the new supervisor; the returned record says so, and the
    researcher is told to end it themselves.
    """
    record = observe(project, signature_of=signature_of)
    if record.state in (SupervisorState.RUNNING.value, SupervisorState.PAUSED.value):
        # RE-CHECKED AT THE MOMENT OF ACTING. Streamlit renders, then acts on a later
        # run: a supervisor that was merely slow can be shown UNRESPONSIVE, recover,
        # and then have its lock pulled by a click on the stale screen - leaving two
        # schedulers launching into the same slot.
        raise GenerationError(
            f"the supervisor for {project.name} is {record.state} and its heartbeat "
            f"is current; it recovered while this page was open. Nothing was "
            f"released. Refresh and look again.")
    detail = {"released_utc": _now(), "abandoned_pid": record.pid,
              "abandoned_state": record.state, "process_killed": False}
    record.state = SupervisorState.CRASHED.value
    record.stop_reason = (
        f"abandoned by the researcher while {detail['abandoned_state']}; the process "
        f"was NOT killed and may still hold resources")
    save_state(project, record)
    target = lock_path(project)
    try:
        target.unlink()
        detail["lock_removed"] = True
    except OSError:
        detail["lock_removed"] = False
    # A STOP IS LEFT STANDING. Clearing the control file deleted the one instruction
    # the abandoned process would still obey if it woke up - and the interface tells
    # the researcher to press Stop before Abandon.
    control = load_control(project)
    control.stop_requested = True
    control.requested_utc = _now()
    save_control(project, control)
    _audit(project, "supervisor_force_released", **detail)
    return detail


def clear_control(project: Project) -> SupervisorControl:
    control = SupervisorControl(requested_utc=_now())
    save_control(project, control)
    return control


# ------------------------------------------------------------------- starting
def supervisor_command(project: Project, *, interval: float,
                       python_executable: str | None = None) -> list[str]:
    """An argument list. Never a string, and never through a shell."""
    return [python_executable or sys.executable, "-m",
            "platform_core.generation.queue_supervisor",
            "--project", project.project_id,
            "--interval", str(float(interval))]


def start(project: Project, *, interval: float = DEFAULT_INTERVAL_SECONDS,
          spawn=None, signature_of=None) -> SupervisorRecord:
    """
    Start one supervisor for this project, or refuse.

    Refusing is the point: two supervisors ticking the same queue would each see the
    same free slot and each launch a job into it, and the concurrency limit the
    researcher set would be quietly doubled.
    """
    if interval < MIN_INTERVAL_SECONDS:
        raise GenerationError(
            f"the tick interval must be at least {MIN_INTERVAL_SECONDS}s; a tighter "
            f"loop re-reads every job from disk without anything having changed")
    existing = observe(project, signature_of=signature_of)
    if existing.state in ALIVE_STATES:
        raise GenerationError(
            f"a supervisor is already running for {project.name} (pid {existing.pid}, "
            f"state {existing.state}); a second one would exceed the concurrency limit")

    if Q.load_queue(project) is None:
        raise GenerationError("no queue exists for this project; build one first")

    clear_control(project)
    command = supervisor_command(project, interval=interval)
    log = log_path(project)
    log.parent.mkdir(parents=True, exist_ok=True)

    if spawn is None:
        import subprocess
        handle = open(log, "a", encoding="utf-8")               # noqa: SIM115
        creation = {}
        if os.name == "nt":
            # DETACHED_PROCESS, not just CREATE_NEW_PROCESS_GROUP. The group flag only
            # exempts the child from Ctrl-C; it stays attached to the console, so
            # closing the terminal running Streamlit delivered CTRL_CLOSE_EVENT to the
            # supervisor AND to the sessions it had spawned - killing paid work by
            # closing a window.
            creation["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        else:
            creation["start_new_session"] = True
        try:
            process = subprocess.Popen(
                command, cwd=str(APP_ROOT), stdout=handle,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                shell=False, **creation)
            pid = process.pid
        finally:
            # The handle was never closed, so the interface leaked one per start and
            # held the log open for its whole life. The child keeps its own duplicate.
            handle.close()
    else:
        pid = spawn(command, str(APP_ROOT), str(log))

    _audit(project, "supervisor_started", pid=pid, interval=interval,
           command=" ".join(command))
    # The supervisor writes its own record once it is up; this is the launch claim,
    # and `observe()` will contradict it if the process never appeared.
    record = SupervisorRecord(
        project_name=project.name, project_id=project.project_id, pid=pid,
        process_start_time=(_process_signature(pid) or (None, ""))[0],
        python_executable=command[0], state=SupervisorState.RUNNING.value,
        interval_seconds=interval, started_utc=_now(), last_heartbeat_utc=_now())
    save_state(project, record)
    return record


# ----------------------------------------------------------------- the loop
def run_supervisor(project: Project, *, interval: float = DEFAULT_INTERVAL_SECONDS,
                   spawn=None, verify=None, signature_of=None,
                   max_ticks: int | None = None, sleep=time.sleep,
                   clock=None) -> SupervisorRecord:
    """
    The loop itself, with every external effect injectable so a test can drive it.

    `spawn` and `verify` are handed straight to `queue.tick()`; `max_ticks` bounds the
    loop for tests. In production none of them is supplied.
    """
    started = clock() if clock else datetime.now(UTC)
    # Before anything else. A supervisor that could not take the lock does not write a
    # state file, because writing one would overwrite the running supervisor's own
    # record with a claim that is not true.
    acquire_lock(project, signature_of=signature_of)

    record = SupervisorRecord(
        project_name=project.name, project_id=project.project_id, pid=os.getpid(),
        process_start_time=(_process_signature(os.getpid()) or (None, ""))[0],
        python_executable=sys.executable, state=SupervisorState.RUNNING.value,
        interval_seconds=interval, started_utc=started.isoformat(),
        last_heartbeat_utc=started.isoformat())
    save_state(project, record)

    try:
        _loop(project, record, interval=interval, spawn=spawn, verify=verify,
              signature_of=signature_of, max_ticks=max_ticks, sleep=sleep,
              clock=clock, started=started)
    except BaseException as exc:                                   # noqa: BLE001
        # A death is not a stop. Recording STOPPED here made a disk-full crash at tick
        # 40 of 120 indistinguishable from a clean finish, and `observe()` reports
        # STOPPED verbatim - so the researcher would believe the run completed while
        # eight sessions never launched.
        record.state = SupervisorState.CRASHED.value
        record.last_error = f"{type(exc).__name__}: {exc}"
        record.stop_reason = (f"the supervisor loop raised "
                              f"{type(exc).__name__}; it did not finish the queue")
        raise
    else:
        record.state = SupervisorState.STOPPED.value
    finally:
        record.stopped_utc = (clock() if clock else datetime.now(UTC)).isoformat()
        # Releasing the lock matters more than recording the state: a lock left behind
        # blocks every future supervisor. Neither failure may prevent the other.
        try:
            save_state(project, record)
        finally:
            release_lock(project)
            try:
                _audit(project, "supervisor_stopped", ticks=record.tick_count,
                       launched_total=record.launched_total,
                       reason=record.stop_reason)
            except Exception:                                      # noqa: BLE001, S110
                pass
    return record


def _loop(project: Project, record: SupervisorRecord, *, interval: float, spawn,
          verify, signature_of, max_ticks, sleep, clock, started) -> None:
    ticks = 0
    while True:
        if max_ticks is not None and ticks >= max_ticks:
            record.stop_reason = f"the tick limit of {max_ticks} was reached"
            break

        control = load_control(project)
        if control.stop_requested:
            record.stop_reason = "a stop was requested"
            break

        moment = clock() if clock else datetime.now(UTC)
        if (moment - started).total_seconds() > MAX_LIFETIME_SECONDS:
            record.stop_reason = (
                f"the supervisor reached its {MAX_LIFETIME_SECONDS / 3600:.0f}-hour "
                f"lifetime; a forgotten scheduler does not keep spending")
            break

        if control.pause_requested:
            record.state = SupervisorState.PAUSED.value
            record.last_heartbeat_utc = moment.isoformat()
            save_state(project, record)
            ticks += 1
            sleep(interval)
            continue

        record.state = SupervisorState.RUNNING.value
        try:
            result = Q.tick(project, spawn=spawn, verify=verify,
                            signature_of=signature_of)
            record.last_tick_utc = result.utc
            record.last_tick_detail = result.to_dict()
            record.launched_total += len(result.launched)
            record.consecutive_errors = 0
            record.last_error = ""
            queue_done = result.queue_status == Q.QueueStatus.COMPLETED.value
        except GenerationError as exc:
            # A queue that has gone the researcher does not get replaced by a new one.
            record.last_error = str(exc)
            record.stop_reason = f"the queue could not be ticked: {exc}"
            break
        except Exception as exc:                                   # noqa: BLE001
            record.consecutive_errors += 1
            record.last_error = f"{type(exc).__name__}: {exc}"
            if record.consecutive_errors >= 3:
                record.stop_reason = (
                    f"three consecutive ticks failed; the last was {record.last_error}")
                break
            queue_done = False

        record.tick_count += 1
        record.last_heartbeat_utc = (clock() if clock
                                     else datetime.now(UTC)).isoformat()
        save_state(project, record)
        ticks += 1

        if queue_done:
            record.stop_reason = "every job in the queue reached a terminal state"
            break
        sleep(interval)


# ------------------------------------------------------------------ entry point
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Advance one project's generation queue until it is done.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args(argv)

    try:
        project = load_project(args.project, open_or_resolve())
    except Exception as exc:                                       # noqa: BLE001
        print(f"the project {args.project!r} could not be loaded: {exc}",
              file=sys.stderr)
        return 2

    # Capped as well as floored. `--interval 86400` slept for a day inside one
    # `sleep()` call, so the 12-hour lifetime check could not fire until it woke.
    interval = min(max(float(args.interval), MIN_INTERVAL_SECONDS),
                   MAX_INTERVAL_SECONDS)
    try:
        record = run_supervisor(project, interval=interval)
    except GenerationError as exc:
        print(f"the supervisor stopped: {exc}", file=sys.stderr)
        return 1
    print(f"supervisor stopped after {record.tick_count} tick(s): "
          f"{record.stop_reason}")
    return 0


if __name__ == "__main__":                                        # pragma: no cover
    raise SystemExit(main())
