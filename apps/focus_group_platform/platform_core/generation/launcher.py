"""
Launch sessions, and recognise them again afterwards.

THREE PROCESSES, NOT TWO. The launcher starts a WORKER; the worker starts the CLI. The
worker exists so that something is alive when the CLI exits, sees the exit code, and
writes it down. Without it the platform is left inferring completion from files the
architecture writes as it goes - and a crashed run leaves those files behind too.

COMPLETION REQUIRES A TERMINAL RECORD. `observe()` will not call a job COMPLETED
because `transcript.json` exists. It reads the record the worker wrote: exit code 0,
a parseable transcript, coherent hashes. A transcript with no record is ORPHANED or
REQUIRES_RECOVERY, and says so.

RECOGNISING A PROCESS. Pid, start time and command line must all agree, and the
command must still name this job's config and terminal record. Pids are reused; a
platform that adopted one on the strength of the number alone would report a
stranger's process as running and would offer to kill it.

`psutil` IS REQUIRED. Without it there is no start time and no command line, and
identity collapses to a pid - which is not identity. The application declares it as a
dependency rather than degrading quietly.

NO SHELL. Argument lists, `shell=False`, everywhere.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..config import APP_ROOT, REPO_ROOT
from ..paths import safe_component, safe_path
from ..projects import Project
from ..services import audit
from .contracts import (CLI_RELATIVE_PATH, GenerationError, GenerationRunPlan,
                        JobRecord, JobStatus, LAUNCH_RECOVERY_TIMEOUT_SECONDS,
                        job_from_dict, sha256_text)
from .terminal import (CompletionEvidence, CompletionQuality, TerminalRecord,
                       TerminationKind, load_terminal_record)

JOBS_DIRNAME = "jobs"
STDOUT_NAME = "launcher_stdout.log"
TERMINAL_NAME = "terminal_record.json"
WORKER_PATH = APP_ROOT / "platform_core" / "generation" / "worker.py"


class PsutilUnavailable(GenerationError):
    """`psutil` is a declared dependency; identity is not weakened without it."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _psutil():
    try:
        import psutil                                            # noqa: PLC0415
    except ImportError as exc:                                    # pragma: no cover
        raise PsutilUnavailable(
            "psutil is required to identify generation processes. Without it a pid "
            "cannot be corroborated by start time and command line, and pid-only "
            "identity is not identity. Install psutil.") from exc
    return psutil


def psutil_available() -> bool:
    try:
        _psutil()
    except PsutilUnavailable:
        return False
    return True


# ------------------------------------------------------------------ storage
def jobs_dir(project: Project) -> Path:
    return safe_path(project.subdir("runs"), JOBS_DIRNAME)


def job_path(project: Project, job_id: str) -> Path:
    safe_component(job_id, field="job_id")
    return safe_path(jobs_dir(project), f"{job_id}.json")


def save_job(project: Project, job: JobRecord) -> Path:
    directory = jobs_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    target = job_path(project, job.job_id)
    atomic_write_text(target, json.dumps(job.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_job(project: Project, job_id: str) -> JobRecord:
    return job_from_dict(json.loads(
        job_path(project, job_id).read_text(encoding="utf-8")))


def all_jobs(project: Project) -> list[JobRecord]:
    directory = jobs_dir(project)
    if not directory.is_dir():
        return []
    out = []
    for child in sorted(directory.glob("*.json")):
        try:
            out.append(job_from_dict(
                json.loads(child.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def job_for_session(project: Project, session_id: str) -> JobRecord | None:
    matches = [j for j in all_jobs(project) if j.session_id == session_id]
    return max(matches, key=lambda j: j.created_utc) if matches else None


# ------------------------------------------------------------ process identity
def process_signature(pid: int) -> dict | None:
    """Start time and command line, or None when the pid is not running."""
    if pid is None:
        return None
    psutil = _psutil()
    try:
        process = psutil.Process(pid)
        return {"pid": pid, "create_time": process.create_time(),
                "cmdline": list(process.cmdline()), "evidence": "psutil"}
    except Exception:                                             # noqa: BLE001
        return None


def is_our_process(job: JobRecord, signature: dict | None) -> bool:
    """
    Five things must agree: pid, start time, and a command line that still names our
    config and our terminal record.

    The terminal-record path is in there deliberately. Two jobs of the same plan share
    a python executable and a CLI path; only the config and the record path make the
    command unique to one job.
    """
    if signature is None or job.pid is None:
        return False
    if signature.get("pid") != job.pid:
        return False
    recorded = job.worker_start_time if job.worker_start_time is not None \
        else job.process_start_time
    if recorded is not None and signature.get("create_time") is not None:
        if abs(signature["create_time"] - recorded) > 1.0:
            return False
    cmdline = signature.get("cmdline")
    if not cmdline:
        return False
    joined = " ".join(cmdline)
    if job.config_path and job.config_path not in joined:
        return False
    if job.terminal_record_path and job.terminal_record_path not in joined:
        return False
    return True


def process_tree(pid: int) -> list[int]:
    """The confirmed descendants of a pid. Used only to stop what we started."""
    psutil = _psutil()
    try:
        parent = psutil.Process(pid)
        return [child.pid for child in parent.children(recursive=True)]
    except Exception:                                             # noqa: BLE001
        return []


# ------------------------------------------------------------------ launching
SESSION_OUTPUT_ROOT_ENV = "FGP_TEST_SESSION_OUTPUT_ROOT"


def session_output_root() -> Path:
    """
    Where the architecture writes session logs. The default is not a preference.

    The ORCHESTRATOR decides this path, not the platform, so the default has to match
    what it actually does — `output/session_logs` inside the repository. The platform
    only predicts it, in order to recognise the output afterwards.

    The environment variable exists for the TEST SUITE, which otherwise builds jobs
    pointing into the researcher's real repository: a test that dies mid-run leaves a
    directory behind, and `build_job` then refuses that session id on every later run.
    SETTING IT IN PRODUCTION BREAKS RECOGNITION — the platform would look somewhere
    the orchestrator never writes, and every run would come back with no output.
    """
    override = os.environ.get(SESSION_OUTPUT_ROOT_ENV)
    return Path(override) if override else REPO_ROOT / "output" / "session_logs"


def _planned_sections(config_path: Path) -> int | None:
    """How many guide sections the compiled config carries. None if unreadable."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    guide = config.get("discussion_guide") if isinstance(config, dict) else None
    return len(guide) if isinstance(guide, list) else None


def build_job(project: Project, plan: GenerationRunPlan, session_id: str, *,
              max_turns: int, mode: str | None,
              python_executable: str | None = None,
              effective_config_sha256: str = "",
              architecture_code_manifest_hash: str = "") -> JobRecord:
    session = plan.session(session_id)
    config_path = Path(session.config_path)
    if not config_path.is_file():
        raise GenerationError(
            f"{session_id}: the compiled config {config_path} does not exist; write "
            f"the configs before launching")
    output_directory = session_output_root() / session_id
    if output_directory.exists():
        raise GenerationError(
            f"{session_id}: {output_directory} already exists. The directory is never "
            f"reused - create a new run with a new id instead")

    job_id = f"job__{session_id}"
    stamp = _now()          # one reading, so created and queued are genuinely equal
    directory = jobs_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    terminal_record_path = directory / f"{job_id}.{TERMINAL_NAME}"
    stdout_path = directory / f"{job_id}.{STDOUT_NAME}"

    command = worker_command(
        python_executable=python_executable or sys.executable, job_id=job_id,
        session_id=session_id, config_path=config_path,
        config_sha256=session.config_sha256, max_turns=max_turns, mode=mode,
        output_directory=output_directory,
        terminal_record_path=terminal_record_path, stdout_path=stdout_path)

    return JobRecord(
        job_id=job_id, session_id=session_id, plan_id=plan.plan_id,
        command=command, command_hash=sha256_text(" ".join(command)),
        config_path=str(config_path), config_sha256=session.config_sha256,
        expected_output_directory=str(output_directory),
        launcher_stdout_path=str(stdout_path),
        terminal_record_path=str(terminal_record_path),
        effective_config_sha256=effective_config_sha256,
        bundle_plan_id=plan.plan_id,
        architecture_code_manifest_hash=architecture_code_manifest_hash,
        guide_sections_expected=_planned_sections(config_path),
        status=JobStatus.PENDING.value, created_utc=stamp, queued_utc=stamp)


def worker_command(*, python_executable: str, job_id: str, session_id: str,
                   config_path: Path, config_sha256: str, max_turns: int,
                   mode: str | None, output_directory: Path,
                   terminal_record_path: Path, stdout_path: Path) -> list[str]:
    """The worker's argument list. Never a string, never a shell."""
    command = [
        python_executable, str(WORKER_PATH),
        "--job-id", job_id,
        "--session-id", session_id,
        "--config", str(config_path),
        "--config-sha256", config_sha256,
        "--cli", str(REPO_ROOT / CLI_RELATIVE_PATH),
        "--max-turns", str(int(max_turns)),
        "--output-dir", str(output_directory),
        "--terminal-record", str(terminal_record_path),
        "--stdout", str(stdout_path),
        "--cwd", str(REPO_ROOT),
        "--python", python_executable,
    ]
    if mode:
        command += ["--mode", mode]
    return command


def default_spawn(command: list[str], *, stdout_path: str, cwd: str) -> dict:
    """
    Start the worker. `shell=False`, argument list, no pipe held open.

    The worker's own stdout goes to a separate file; the CLI's output is captured by
    the worker into `stdout_path`.
    """
    worker_log = Path(stdout_path).with_suffix(".worker.log")
    worker_log.parent.mkdir(parents=True, exist_ok=True)
    handle = open(worker_log, "ab", buffering=0)                  # noqa: SIM115
    process = subprocess.Popen(                                   # noqa: S603
        command, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        cwd=cwd, shell=False)
    signature = process_signature(process.pid)
    return {"pid": process.pid,
            "process_start_time": (signature or {}).get("create_time")}


def launch(project: Project, job: JobRecord, *, spawn=None) -> JobRecord:
    """
    Start one session's worker. `spawn` is the seam a test replaces.

    A job that already reached a terminal state is never restarted here; the refusal
    is the point, not an inconvenience.
    """
    spawn = spawn or default_spawn
    if job.status not in (JobStatus.PENDING.value, JobStatus.LAUNCHING.value):
        raise GenerationError(
            f"{job.job_id} is {job.status}; a job is never relaunched by the "
            f"platform. Create a new run if it should be repeated.")

    job.launch_attempt_id = uuid.uuid4().hex[:12]
    job.launch_attempt_utc = _now()
    job.status = JobStatus.LAUNCHING.value
    job.started_utc = job.started_utc or _now()
    save_job(project, job)

    Path(job.launcher_stdout_path).parent.mkdir(parents=True, exist_ok=True)
    Path(job.launcher_stdout_path).touch()
    try:
        result = spawn(job.command, stdout_path=job.launcher_stdout_path,
                       cwd=str(REPO_ROOT))
    except Exception as exc:                                      # noqa: BLE001
        job.status = JobStatus.FAILED_TO_LAUNCH.value
        job.failure_reason = f"the worker could not be started: {exc}"
        job.completed_utc = _now()
        _apply_durations(job)
        save_job(project, job)
        raise

    job.pid = result.get("pid")
    job.worker_pid = result.get("pid")
    job.worker_start_time = result.get("process_start_time")
    job.process_start_time = result.get("process_start_time")
    job.status = JobStatus.RUNNING.value
    job.last_observed_utc = _now()
    save_job(project, job)
    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=job.job_id,
                 detail={"action": "launched", "session_id": job.session_id,
                         "plan_id": job.plan_id, "worker_pid": job.worker_pid,
                         "launch_attempt_id": job.launch_attempt_id,
                         "command_hash": job.command_hash,
                         "config_sha256": job.config_sha256, "shell": False})
    return job


# ------------------------------------------------------------------ observing
def _age_seconds(stamp: str) -> float | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (datetime.now(UTC) - moment).total_seconds()


def observe(project: Project, job: JobRecord, *, signature_of=None,
            recovery_timeout: float = LAUNCH_RECOVERY_TIMEOUT_SECONDS
            ) -> JobRecord:
    """
    Re-derive the status from durable evidence.

    ORDER MATTERS. The terminal record is consulted FIRST: a worker that finished and
    wrote its record is the strongest evidence available, stronger than a process
    table that has already forgotten the pid.
    """
    signature_of = signature_of or process_signature
    # States that are already a conclusion. REQUIRES_RECOVERY is deliberately NOT
    # here: durable evidence always wins, so a terminal record that arrives late -
    # a slow write, a filesystem catching up - still resolves the job. What it must
    # not do is decay to UNKNOWN, which would take it out of every list showing what
    # needs attention; that is handled below.
    if job.status in (JobStatus.CANCELLED.value, JobStatus.COMPLETED.value,
                      JobStatus.FAILED.value, JobStatus.FAILED_TO_LAUNCH.value,
                      JobStatus.BLOCKED_INPUT_CHANGED.value):
        return job

    previous = job.status
    record = load_terminal_record(job.terminal_record_path) \
        if job.terminal_record_path else None
    alive = is_our_process(job, signature_of(job.pid)) if job.pid else False

    if record is not None:
        _apply_terminal_record(job, record)
    elif alive:
        job.status = JobStatus.RUNNING.value
    elif job.status in (JobStatus.RUNNING.value, JobStatus.LAUNCHING.value):
        job.status, job.failure_reason = _resolve_without_record(
            job, recovery_timeout)
        if job.status != JobStatus.LAUNCHING.value:
            job.completed_utc = job.completed_utc or _now()
            _apply_durations(job)
    elif job.status in (JobStatus.PENDING.value,
                        JobStatus.REQUIRES_RECOVERY.value,
                        JobStatus.ORPHANED.value):
        # PENDING has nothing to observe yet; turning it into UNKNOWN would take it
        # out of the queue's pending list and the scheduler would never start it.
        # REQUIRES_RECOVERY is a specific finding - output exists, evidence does not
        # - and it is kept until a record appears or a researcher acts on it.
        # ORPHANED was missing from this list and decayed to UNKNOWN on the next
        # observation. UNKNOWN is in neither the queue's OCCUPYING nor its TERMINAL
        # set, so the queue could never reach COMPLETED and the supervisor ran until
        # its twelve-hour lifetime expired - and the job dropped off the interface's
        # "not relaunched automatically" list after a single refresh.
        pass
    else:
        job.status = JobStatus.UNKNOWN.value

    job.last_observed_utc = _now()
    if job.status != previous:
        save_job(project, job)
    return job


def _parse_utc(value):
    """
    An aware UTC datetime, or None. NEVER a raise.

    A NAIVE STAMP IS NOT OBSERVED. Every timestamp this platform writes carries an
    offset, so an offset-less one came from a hand edit or a migration and its zone is
    unknown. Reading it as UTC would manufacture a plausible number - from a UTC-5
    machine, a queue wait 18,000 seconds too long, entering the mean with no marker.
    None is a first-class outcome here and is reported as `n_missing`.

    Not raising is the other half: leaving it naive made `aware - naive` raise
    TypeError inside `observe()`, and one such record blanked the Generate view for
    every job in the project.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _apply_durations(job: JobRecord) -> None:
    """Stage durations from the timestamps that exist. Absent stays absent."""
    queued = _parse_utc(job.queued_utc)
    launched = _parse_utc(job.launch_attempt_utc)
    started = _parse_utc(job.started_utc)
    completed = _parse_utc(job.completed_utc)

    def delta(a, b):
        if a is None or b is None:
            return None
        seconds = (b - a).total_seconds()
        return seconds if seconds >= 0 else None

    job.queue_wait_seconds = delta(queued, launched or started)
    job.launch_duration_seconds = delta(launched, started)
    job.run_duration_seconds = delta(started, completed)
    job.total_elapsed_seconds = delta(queued or launched or started, completed)


def _apply_terminal_record(job: JobRecord, record: TerminalRecord) -> None:
    job.exit_code = record.exit_code
    job.termination_kind = record.termination_kind
    job.completion_quality = record.completion_quality
    job.cli_pid = record.cli_pid
    job.completed_utc = record.completed_utc or job.completed_utc or _now()
    job.completion_evidence = record.completion_evidence
    job.transcript_state_match = record.transcript_state_match
    job.guide_sections_completed = record.guide_sections_completed
    job.guide_sections_total = record.guide_sections_total
    _apply_durations(job)

    if record.termination_kind == TerminationKind.USER_CANCELLED.value:
        job.status = JobStatus.CANCELLED.value
        job.failure_reason = (record.failure_reason
                              or "cancelled by the researcher; artefacts are kept")
        return
    planned = job.guide_sections_expected
    ran = record.guide_sections_total
    guide_mismatch = (isinstance(planned, int) and isinstance(ran, int)
                      and planned != ran)

    if (record.usable_output and record.config_sha256 == job.config_sha256
            and not guide_mismatch):
        job.status = JobStatus.COMPLETED.value
        job.failure_reason = ""
        return
    job.status = JobStatus.FAILED.value
    if job.config_sha256 and not record.config_sha256:
        job.failure_reason = (
            "the terminal record names no config hash, so what this session ran "
            "cannot be established; it is not assumed to be the planned config")
        return
    if record.config_sha256 and record.config_sha256 != job.config_sha256:
        # FIRST, when it can fire at all. NOTE: `worker.py` echoes the hash the
        # launcher passed it, so for records this codebase writes the two are equal by
        # construction and this branch is unreachable. The check that actually catches
        # a changed config is the worker re-verifying it in its OWN process before
        # spawning; that arrives here as a `failure_reason`. This branch guards against
        # a hand-edited or stale record file, which is worth guarding but is not the
        # config-drift detector - do not read it as one.
        job.failure_reason = (
            f"the worker ran a config hashing {record.config_sha256[:12]}… but this "
            f"job records {job.config_sha256[:12]}…")
        return
    if guide_mismatch:
        job.failure_reason = (
            f"the plan compiled {planned} guide section(s) for this session and the "
            f"final state carries {ran}; completion cannot be judged against a guide "
            f"the session substituted for the planned one")
        return
    if record.transcript_state_match is False:
        # Two artefacts describing the same session disagree. Which one is right is
        # not something the platform can decide, so neither is used.
        job.failure_reason = (
            f"transcript.json and the final state describe different discussions: "
            f"{record.transcript_state_mismatch_reason}")
        return
    if record.completion_evidence == CompletionEvidence.CONFLICTING_EVIDENCE.value:
        job.failure_reason = (
            record.guide_completion_status
            or "the structured state and the process output disagree about how the "
               "session ended")
        return
    if record.failure_reason:
        # THE WORKER SAW IT HAPPEN. Its own reason outranks anything inferred from the
        # artefacts afterwards. The one config change this platform can actually
        # detect - the worker re-verifying the config hash in its own process and
        # refusing to launch - was being reported as "the session ended without
        # writing a transcript", which is true and useless.
        job.failure_reason = record.failure_reason
    elif record.exit_code not in (0, None):
        job.failure_reason = f"the session exited with code {record.exit_code}"
    elif not record.transcript_exists:
        job.failure_reason = "the session ended without writing a transcript"
    elif not record.transcript_parseable:
        job.failure_reason = ("the session wrote a transcript that does not parse; "
                              "exit code 0 over unreadable output is still a "
                              "failure")
    else:
        job.failure_reason = (record.failure_reason
                              or f"terminated as {record.termination_kind} with "
                                 f"quality {record.completion_quality}")


def apply_durations(job: JobRecord) -> JobRecord:
    """Public: stage durations from whatever timestamps the job carries."""
    _apply_durations(job)
    return job


def _resolve_without_record(job: JobRecord,
                            recovery_timeout: float) -> tuple[str, str]:
    """
    No terminal record, no live process. What can honestly be said.

    A transcript on disk is NOT promoted to COMPLETED here. It is evidence that the
    architecture wrote something, and the question of whether the session finished is
    exactly what the missing record would have answered.
    """
    output = Path(job.expected_output_directory)
    transcript = output / "transcript.json"

    if job.status == JobStatus.LAUNCHING.value:
        age = _age_seconds(job.launch_attempt_utc or job.started_utc)
        if age is not None and age < recovery_timeout:
            return JobStatus.LAUNCHING.value, ""
        return (JobStatus.FAILED_TO_LAUNCH.value,
                f"no worker was confirmed within {recovery_timeout:.0f}s of the "
                f"launch attempt {job.launch_attempt_id or '?'}. It is not "
                f"relaunched automatically.")

    if transcript.is_file():
        return (JobStatus.REQUIRES_RECOVERY.value,
                "a transcript exists but the worker wrote no terminal record, so "
                "there is no evidence the session finished. It is not COMPLETED and "
                "is not imported until a researcher decides what happened.")
    if output.exists():
        return (JobStatus.ORPHANED.value,
                "the worker is gone, output exists and no terminal record was "
                "written. It is not relaunched automatically.")
    return (JobStatus.ORPHANED.value,
            "the worker is gone and nothing was written. It is not relaunched "
            "automatically.")


def observe_all(project: Project, *, signature_of=None,
                recovery_timeout: float = LAUNCH_RECOVERY_TIMEOUT_SECONDS
                ) -> list[JobRecord]:
    return [observe(project, job, signature_of=signature_of,
                    recovery_timeout=recovery_timeout)
            for job in all_jobs(project)]


def terminal_record_for(job: JobRecord) -> TerminalRecord | None:
    return load_terminal_record(job.terminal_record_path) \
        if job.terminal_record_path else None


# ---------------------------------------------------------------- cancellation
def cancel(project: Project, job_id: str, *, confirm_session_id: str,
           terminate=None, signature_of=None) -> JobRecord:
    """
    Stop one RUNNING job: its worker, its CLI child, and confirmed descendants.

    Only the tree that this job started. A pid is signalled only after the parent has
    been confirmed as ours, and every partial artefact is left where it is - it cost
    money to produce and may be the only evidence of what went wrong.
    """
    signature_of = signature_of or process_signature
    job = observe(project, load_job(project, job_id), signature_of=signature_of)
    if confirm_session_id != job.session_id:
        raise GenerationError(
            f"cancellation not confirmed: type the session id {job.session_id!r}")
    if job.status != JobStatus.RUNNING.value:
        raise GenerationError(
            f"{job_id} is {job.status}; only a RUNNING job can be cancelled")
    if not is_our_process(job, signature_of(job.pid)):
        raise GenerationError(
            f"{job_id}: the running process could not be confirmed as this job's. "
            f"Refusing to signal a process that may belong to something else.")

    if terminate is None:
        def terminate(pid):
            psutil = _psutil()
            try:
                psutil.Process(pid).terminate()
            except Exception:                                     # noqa: BLE001
                pass

    # Children first, then the worker: killing the worker first would orphan the CLI
    # and leave it running with nobody to record how it ended.
    try:
        descendants = process_tree(job.pid)
    except PsutilUnavailable:
        descendants = []
    for pid in descendants:
        terminate(pid)
    terminate(job.pid)

    write_cancellation_record(job)
    job.status = JobStatus.CANCELLED.value
    job.cancelled_by_user = True
    job.termination_kind = TerminationKind.USER_CANCELLED.value
    job.completed_utc = _now()
    _apply_durations(job)
    job.failure_reason = ("cancelled by the researcher; partial artefacts are kept "
                          "and cost already incurred is not refunded")
    save_job(project, job)
    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=job.job_id,
                 detail={"action": "cancelled", "session_id": job.session_id,
                         "n_descendants_signalled": len(descendants),
                         "artefacts_kept": True})
    return job


def write_cancellation_record(job: JobRecord) -> Path | None:
    """
    Record the cancellation atomically, even though the worker cannot.

    The worker is being terminated, so it will not write its own record. Without this
    the job would look ORPHANED afterwards and nobody could tell a cancellation from
    a crash.
    """
    if not job.terminal_record_path:
        return None
    existing = load_terminal_record(job.terminal_record_path)
    record = existing or TerminalRecord(
        job_id=job.job_id, session_id=job.session_id, worker_pid=job.worker_pid,
        cli_pid=job.cli_pid, command=list(job.command),
        command_hash=job.command_hash, config_path=job.config_path,
        config_sha256=job.config_sha256, started_utc=job.started_utc)
    record.termination_kind = TerminationKind.USER_CANCELLED.value
    record.completed_utc = _now()
    record.completion_quality = CompletionQuality.PARTIAL_OUTPUT.value
    record.failure_reason = ("cancelled by the researcher; partial artefacts are "
                             "kept and cost already incurred is not refunded")
    target = Path(job.terminal_record_path)
    atomic_write_text(target, json.dumps(record.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target
