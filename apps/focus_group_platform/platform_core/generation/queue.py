"""
A durable queue with an explicit scheduler tick.

WHAT WAS WRONG. `concurrency_limit` was a number on a screen. The interface launched
whatever the researcher selected, and when a session finished nothing started the
next: a twelve-session study meant sitting there launching batches by hand, and the
declared limit guaranteed nothing.

Now the queue is a file. `tick()` looks at what is actually running - confirmed
processes, not remembered ones - works out how many slots are free, and starts that
many PENDING jobs. It survives a Streamlit restart because it never lived in
Streamlit.

WHAT THE TICK WILL NOT DO. It never restarts a job that reached a terminal state.
FAILED, CANCELLED, ORPHANED and COMPLETED are left alone: a retry may cost money and
may overwrite nothing while duplicating everything, and only the researcher can decide
that. Pausing stops NEW launches and touches nothing already running.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..paths import safe_path
from ..projects import Project
from ..services import audit
from . import launcher as GL
from .contracts import (DEFAULT_CONCURRENCY, GenerationError, GenerationRunPlan,
                        JobStatus, MAX_CONCURRENCY)

QUEUE_FILENAME = "run_queue.json"

# Statuses that occupy a slot. LAUNCHING counts: a worker that has been started but
# has not yet reported is still consuming capacity, and treating it as free is how a
# concurrency limit gets exceeded.
OCCUPYING = (JobStatus.RUNNING.value, JobStatus.LAUNCHING.value)
# Reached a conclusion, or waiting for a researcher. Either way the scheduler
# leaves it alone: none of these is restarted automatically.
TERMINAL = (JobStatus.COMPLETED.value, JobStatus.FAILED.value,
            JobStatus.CANCELLED.value, JobStatus.ORPHANED.value,
            JobStatus.FAILED_TO_LAUNCH.value,
            JobStatus.BLOCKED_INPUT_CHANGED.value,
            JobStatus.REQUIRES_RECOVERY.value)


class QueueStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class QueueRecord:
    plan_id: str
    ordered_job_ids: list[str] = field(default_factory=list)
    concurrency_limit: int = DEFAULT_CONCURRENCY
    queue_status: str = QueueStatus.IDLE.value
    created_utc: str = ""
    started_utc: str = ""
    completed_utc: str = ""
    paused: bool = False
    last_scheduler_tick_utc: str = ""
    last_tick_detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def record_from_dict(payload: dict) -> QueueRecord:
    known = set(QueueRecord.__dataclass_fields__)
    return QueueRecord(**{k: v for k, v in payload.items() if k in known})


def queue_path(project: Project) -> Path:
    from .planner import generation_dir
    return safe_path(generation_dir(project), QUEUE_FILENAME)


def save_queue(project: Project, record: QueueRecord) -> Path:
    target = queue_path(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(record.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_queue(project: Project) -> QueueRecord | None:
    target = queue_path(project)
    if not target.is_file():
        return None
    try:
        return record_from_dict(json.loads(target.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        # OSError included: on Windows a concurrent atomic replace raises a sharing
        # violation, and letting it out of `load_queue` counted toward the
        # supervisor's three-strikes stop.
        return None


# ------------------------------------------------------------------- building
def build_queue(project: Project, plan: GenerationRunPlan, *,
                concurrency_limit: int = DEFAULT_CONCURRENCY,
                max_turns: int, mode: str | None) -> QueueRecord:
    """
    Create every job as PENDING, in plan order, and persist the queue.

    Nothing is launched here. Building a queue and starting it are two acts, so a
    researcher can look at twelve pending sessions before any of them costs anything.
    """
    if not plan.launchable:
        raise GenerationError(
            f"{plan.plan_id} has not passed its dry-run; a queue is not built for a "
            f"plan that cannot be launched")
    if not 1 <= concurrency_limit <= MAX_CONCURRENCY:
        raise GenerationError(
            f"concurrency_limit must be between 1 and {MAX_CONCURRENCY}")

    existing = {j.session_id: j for j in GL.all_jobs(project)}
    ordered: list[str] = []
    for session in plan.sessions:
        job = existing.get(session.session_id)
        if job is None:
            # The launch-time gate verifies the effective configuration and the
            # architecture pin, so the job must carry both. Building it without them
            # produces a job that can never pass its own preflight.
            job = GL.build_job(
                project, plan, session.session_id, max_turns=max_turns, mode=mode,
                effective_config_sha256=plan.effective_config_hashes.get(
                    session.session_id, ""),
                architecture_code_manifest_hash=(
                    plan.architecture_code_manifest_hash))
            GL.save_job(project, job)
        ordered.append(job.job_id)

    record = QueueRecord(plan_id=plan.plan_id, ordered_job_ids=ordered,
                         concurrency_limit=concurrency_limit,
                         queue_status=QueueStatus.IDLE.value, created_utc=_now())
    save_queue(project, record)
    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=plan.plan_id,
                 detail={"action": "queue_built", "n_jobs": len(ordered),
                         "concurrency_limit": concurrency_limit})
    return record


def start(project: Project) -> QueueRecord:
    record = _require(project)
    record.paused = False
    record.queue_status = QueueStatus.RUNNING.value
    record.started_utc = record.started_utc or _now()
    save_queue(project, record)
    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=record.plan_id, detail={"action": "queue_started"})
    return record


def pause(project: Project) -> QueueRecord:
    """Stop starting NEW sessions. Anything already running keeps running."""
    record = _require(project)
    record.paused = True
    record.queue_status = QueueStatus.PAUSED.value
    save_queue(project, record)
    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=record.plan_id,
                 detail={"action": "queue_paused",
                         "cancels_running_jobs": False})
    return record


def resume(project: Project) -> QueueRecord:
    return start(project)


def _require(project: Project) -> QueueRecord:
    record = load_queue(project)
    if record is None:
        raise GenerationError("no queue exists for this project")
    return record


# ------------------------------------------------------------------- the tick
@dataclass
class TickResult:
    utc: str
    queue_status: str
    concurrency_limit: int
    occupied_slots: int
    available_slots: int
    launched: list[str] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    running: list[str] = field(default_factory=list)
    terminal: list[str] = field(default_factory=list)
    paused: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _refuse_if_another_scheduler(project: Project, signature_of=None) -> None:
    """
    A tick is a scheduler. Two of them launch into the same free slot.

    The interface disables its manual tick while a supervisor is alive, but a
    `disabled=` expression is advice, not enforcement: it reads a state file that can
    be one interval stale, and it is bypassed entirely by calling `tick()` directly.
    The lock is the authority, and it is checked HERE, where the launching happens.

    A supervisor ticking its own queue holds the lock itself and is not refused.
    """
    from . import queue_supervisor as GS          # deferred: GS imports this module
    holder = GS.lock_holder(project)
    if not holder:
        return
    holder_pid = holder.get("pid")
    if holder_pid in (None, os.getpid()):
        return
    resolve = signature_of or GS._process_signature
    if GS._holder_is_live_supervisor(holder, resolve(holder_pid), project):
        raise GenerationError(
            f"a supervisor (pid {holder_pid}) is scheduling {project.name}. A second "
            f"scheduler would launch into the same free slot and exceed the "
            f"concurrency limit. Stop the supervisor first, or let it do the work.")


def tick(project: Project, *, spawn=None, verify=None,
         signature_of=None) -> TickResult:
    """
    One scheduler step.

    1. observe every job from disk and the process table
    2. count only CONFIRMED occupying jobs
    3. compute free slots
    4. launch PENDING jobs, in queue order, until the slots are full
    5. never touch a terminal job
    6. persist what happened

    `verify` is the launch-time gate (`preflight.verify_before_launch`); a job that
    fails it is BLOCKED_INPUT_CHANGED and does not consume a slot.
    """
    _refuse_if_another_scheduler(project, signature_of=signature_of)
    record = _require(project)
    observed = {j.job_id: j for j in GL.observe_all(project,
                                                    signature_of=signature_of)}

    occupying, pending, terminal = [], [], []
    for job_id in record.ordered_job_ids:
        job = observed.get(job_id)
        if job is None:
            continue
        if job.status in OCCUPYING:
            occupying.append(job_id)
        elif job.status in TERMINAL:
            terminal.append(job_id)
        elif job.status == JobStatus.PENDING.value:
            pending.append(job_id)

    result = TickResult(
        utc=_now(), queue_status=record.queue_status,
        concurrency_limit=record.concurrency_limit,
        occupied_slots=len(occupying),
        available_slots=max(record.concurrency_limit - len(occupying), 0),
        pending=list(pending), running=list(occupying), terminal=list(terminal),
        paused=record.paused)

    if not record.paused and record.queue_status == QueueStatus.RUNNING.value:
        for job_id in pending:
            if result.available_slots <= 0:
                break
            job = observed[job_id]
            if verify is not None:
                verification = verify(project, job)
                if not verification.get("ok", False):
                    job.status = JobStatus.BLOCKED_INPUT_CHANGED.value
                    job.failure_reason = "; ".join(
                        p["message"] for p in verification.get("problems", []))
                    GL.save_job(project, job)
                    result.blocked.append({"job_id": job_id,
                                           "problems": verification.get("problems")})
                    continue
            try:
                GL.launch(project, job, spawn=spawn)
            except GenerationError as exc:
                result.blocked.append({"job_id": job_id,
                                       "problems": [{"message": str(exc)}]})
                continue
            result.launched.append(job_id)
            result.available_slots -= 1
            result.occupied_slots += 1

    if terminal and len(terminal) == len(record.ordered_job_ids):
        record.queue_status = QueueStatus.COMPLETED.value
        record.completed_utc = record.completed_utc or _now()
        result.queue_status = record.queue_status

    # RE-READ BEFORE WRITING. This tick loaded the queue at its start and spends
    # seconds launching; writing the whole record back at the end silently reverted a
    # pause the researcher set in the meantime, and the next tick launched again. Only
    # the fields this tick owns are carried over.
    latest = load_queue(project) or record
    latest.last_scheduler_tick_utc = result.utc
    latest.last_tick_detail = result.to_dict()
    if record.queue_status == QueueStatus.COMPLETED.value:
        latest.queue_status = QueueStatus.COMPLETED.value
        latest.completed_utc = latest.completed_utc or record.completed_utc
    if latest.paused and not result.paused and result.launched:
        # The pause arrived mid-tick, AFTER these launches. Recording `paused: true`
        # beside a non-empty `launched` list would read, in the queue file that
        # reconstructs spend, as "the scheduler launched while paused".
        latest.last_tick_detail["paused_after_launch"] = True
    else:
        result.paused = latest.paused
    save_queue(project, latest)
    return result
