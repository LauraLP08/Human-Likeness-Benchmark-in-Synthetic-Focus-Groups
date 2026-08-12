"""
Generation contracts: the study, the plan, the sessions, the jobs.

THE WORD THIS MODULE REFUSES TO USE. There is no seed and no `generation_seed`
anywhere in a session. An LLM run is not seeded and calling an index a seed would
promise a reproducibility the architecture does not offer. `replicate_index` is a RUN
LABEL - the position of an independent realisation in the design, nothing more.

The one place a sampling seed is legitimate is panel selection: choosing WHICH
participants are drawn from a local index is a sampling decision and is reproducible.
It is recorded as `panel_sampling_seed`, on the profile source, and never on a
session.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

SCHEMA_VERSION = "1.0.0"

# The CLI that runs a session. The platform speaks to the architecture through this
# and nothing else.
CLI_RELATIVE_PATH = "scripts/run_full_session.py"
CLI_MODES = ("orchestrated", "emergent")

# Public top-level keys of the session config contract, as `core.orchestrator` and
# `scripts/run_full_session.py` already read them. The platform fills these and
# invents no key of its own.
PUBLIC_CONFIG_KEYS = (
    "session_id",
    "run_label",
    "research_objective",
    "topic_domain",
    "participant_collective_identity",
    "moderator_knowledge_brief",
    "researcher_notes",
    "participation_mode",
    "moderator_model",
    "temperature",
    "participants",
    "discussion_guide",
)

REQUIRED_CONFIG_KEYS = (
    "session_id", "research_objective", "topic_domain",
    "participant_collective_identity", "moderator_knowledge_brief",
    "participants", "discussion_guide",
)

# Conservative ceiling. A researcher may raise the limit up to this; the default
# stays 1 so a mistake costs one session, not twelve.
MAX_CONCURRENCY = 4
DEFAULT_CONCURRENCY = 1

# How long a job may sit in LAUNCHING with no confirmed worker before the
# platform stops waiting. It is resolved, never relaunched.
LAUNCH_RECOVERY_TIMEOUT_SECONDS = 120.0


class ValidationStatus(str, Enum):
    NOT_VALIDATED = "NOT_VALIDATED"
    VALID = "VALID"
    INVALID = "INVALID"


class SessionStatus(str, Enum):
    PLANNED = "PLANNED"
    LAUNCHED = "LAUNCHED"
    IMPORTED = "IMPORTED"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    LAUNCHING = "LAUNCHING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ORPHANED = "ORPHANED"
    UNKNOWN = "UNKNOWN"
    # Phase 3E. A job whose inputs moved between confirmation and launch is not a
    # failure of the run - it never started - and it is not PENDING either, because
    # starting it now would run something the researcher did not confirm.
    BLOCKED_INPUT_CHANGED = "BLOCKED_INPUT_CHANGED"
    FAILED_TO_LAUNCH = "FAILED_TO_LAUNCH"
    REQUIRES_RECOVERY = "REQUIRES_RECOVERY"


class ProfileSourceKind(str, Enum):
    UPLOADED = "UPLOADED"
    TWIN2K = "TWIN2K"
    LEGACY_INLINE = "LEGACY_INLINE"


class GenerationError(RuntimeError):
    pass


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(payload) -> str:
    return sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


@dataclass
class GenerationStudy:
    generation_study_id: str
    project_id: str
    research_objective: str
    topic_domain: str
    participant_collective_identity: str
    moderator_knowledge_brief: str
    discussion_guide_id: str | None = None
    agent_set_id: str | None = None
    synthetic_conditions: list[str] = field(default_factory=list)
    focus_groups: list[str] = field(default_factory=list)
    replicates: int = 1
    participation_mode: str = "emergent"
    moderator_model: str = "claude-sonnet-4-6"
    participant_model: str = "claude-haiku-4-5-20251001"
    max_turns: int = 90
    concurrency_limit: int = DEFAULT_CONCURRENCY
    temperature: float | None = None
    researcher_notes: str = ""
    created_utc: str = ""
    schema_version: str = SCHEMA_VERSION

    @property
    def n_sessions(self) -> int:
        return (len(self.synthetic_conditions) * len(self.focus_groups)
                * max(self.replicates, 0))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GenerationSession:
    session_id: str
    condition_id: str
    focus_group_id: str
    replicate_index: int
    run_label: str
    config_path: str = ""
    config_sha256: str = ""
    agent_ids: list[str] = field(default_factory=list)
    guide_hash: str = ""
    status: str = SessionStatus.PLANNED.value
    output_directory: str = ""
    job_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GenerationRunPlan:
    plan_id: str
    generation_study_id: str
    sessions: list[GenerationSession] = field(default_factory=list)
    validation_status: str = ValidationStatus.NOT_VALIDATED.value
    validation_problems: list[dict] = field(default_factory=list)
    config_hashes: dict[str, str] = field(default_factory=dict)
    effective_config_hashes: dict[str, str] = field(default_factory=dict)
    bundle_plan_id: str = ""
    architecture_code_manifest_hash: str = ""
    guide_yaml_sha256: str = ""
    guide_compiled_sha256: str = ""
    profile_source: dict = field(default_factory=dict)
    created_utc: str = ""
    confirmed_utc: str = ""
    schema_version: str = SCHEMA_VERSION

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    @property
    def launchable(self) -> bool:
        return self.validation_status == ValidationStatus.VALID.value

    def session(self, session_id: str) -> GenerationSession:
        for s in self.sessions:
            if s.session_id == session_id:
                return s
        raise GenerationError(f"no session {session_id!r} in plan {self.plan_id}")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_sessions"] = self.total_sessions
        return d


def plan_from_dict(payload: dict) -> GenerationRunPlan:
    known = set(GenerationRunPlan.__dataclass_fields__)
    body = {k: v for k, v in payload.items() if k in known}
    body["sessions"] = [GenerationSession(**s) for s in payload.get("sessions", [])]
    return GenerationRunPlan(**body)


def study_from_dict(payload: dict) -> GenerationStudy:
    known = set(GenerationStudy.__dataclass_fields__)
    return GenerationStudy(**{k: v for k, v in payload.items() if k in known})


@dataclass
class JobRecord:
    """
    One launched process. Everything needed to recognise it again after a restart.

    The status on disk is a RECORD, not the truth: `launcher.observe()` re-derives it
    from the filesystem and the process table on every read. A record saying RUNNING
    while the process is gone is exactly the state this design expects to encounter.
    """

    job_id: str
    session_id: str
    plan_id: str
    command: list[str] = field(default_factory=list)
    command_hash: str = ""
    pid: int | None = None
    process_start_time: float | None = None
    config_path: str = ""
    config_sha256: str = ""
    expected_output_directory: str = ""
    launcher_stdout_path: str = ""
    status: str = JobStatus.PENDING.value
    exit_code: int | None = None
    created_utc: str = ""
    started_utc: str = ""
    completed_utc: str = ""
    last_observed_utc: str = ""
    failure_reason: str = ""
    cancelled_by_user: bool = False
    imported_transcript_id: str | None = None
    # ---- Phase 3E: durable terminal evidence and launch accounting
    worker_pid: int | None = None
    worker_start_time: float | None = None
    cli_pid: int | None = None
    terminal_record_path: str = ""
    launch_attempt_id: str = ""
    launch_attempt_utc: str = ""
    effective_config_sha256: str = ""
    bundle_plan_id: str = ""
    architecture_code_manifest_hash: str = ""
    completion_quality: str = ""
    termination_kind: str = ""
    # ---- Phase 3F: what the completion claim rests on, and how long each stage took
    completion_evidence: str = ""
    transcript_state_match: bool | None = None
    guide_sections_completed: int | None = None
    guide_sections_total: int | None = None
    # How many sections the PLAN said this session would have. Without it, "all
    # sections completed" is a claim the session's own state gets to make about
    # itself: a state carrying one section, marked complete, read as GUIDE_COMPLETED
    # for a three-section plan.
    guide_sections_expected: int | None = None
    queued_utc: str = ""
    queue_wait_seconds: float | None = None
    launch_duration_seconds: float | None = None
    run_duration_seconds: float | None = None
    total_elapsed_seconds: float | None = None
    schema_version: str = SCHEMA_VERSION

    @property
    def terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value,
                               JobStatus.CANCELLED.value, JobStatus.ORPHANED.value,
                               JobStatus.FAILED_TO_LAUNCH.value)

    @property
    def relaunchable(self) -> bool:
        """
        Never. A failed or orphaned job is not retried by the platform: the run may
        have spent money, may have written a partial transcript, and only the
        researcher can decide whether repeating it is the right thing to do.
        """
        return False

    @property
    def durations(self) -> dict:
        """
        Four stage durations, each None where its endpoints are not both known.

        A missing timestamp yields None, never 0.0: a duration that was not observed
        is not a duration of zero, and averaging zeros would understate every summary
        that included one.
        """
        return {
            "queue_wait_seconds": self.queue_wait_seconds,
            "launch_duration_seconds": self.launch_duration_seconds,
            "run_duration_seconds": self.run_duration_seconds,
            "total_elapsed_seconds": self.total_elapsed_seconds,
        }

    def to_dict(self) -> dict:
        return asdict(self)


def job_from_dict(payload: dict) -> JobRecord:
    known = set(JobRecord.__dataclass_fields__)
    return JobRecord(**{k: v for k, v in payload.items() if k in known})
