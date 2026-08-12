"""
Bring a finished session into the project.

WHAT WAS WRONG. The importer copied the transcript into `uploads/` with a plain
`write_bytes()` BEFORE the collision policy had been resolved. A rejected import still
overwrote the workspace copy - the one case where "reject" must mean nothing changed.

Now nothing is written to a shared name until `import_service` has resolved the
policy. Where staging is genuinely needed it goes to a unique path, is written
atomically, and only that staging file is cleaned up afterwards.

EVIDENCE BEFORE BYTES. A session is imported only when the worker's terminal record
says it ended cleanly, over a parseable transcript, from the config this job recorded.
A transcript with no terminal record is not imported at all: file existence is not
evidence that a session finished.

MAX_TURNS_REACHED CAN BE IMPORTED, WITH A LABEL. The run stopped at the safety cap
with the guide unfinished. That is real data, and it is not a clean session; it
carries `generated_session_completeness = MAX_TURNS_REACHED` and its proposed
assignment needs a stronger confirmation than a clean one.

NOTHING BECOMES COMPARABLE BY ARRIVING. No window is created, none is locked, no
assignment is written.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..paths import safe_path
from ..projects import Project
from ..services import audit, import_service
from .contracts import GenerationError, GenerationRunPlan, JobRecord, JobStatus
from .terminal import CompletionQuality, TerminationKind, load_terminal_record

SETTLE_SECONDS = 0.4
SETTLE_READS = 2
STAGING_DIRNAME = "generation_staging"

CLEAN = "GUIDE_COMPLETED"
CAPPED = "MAX_TURNS_REACHED"


@dataclass
class ImportOutcome:
    session_id: str
    ok: bool
    transcript_id: str | None = None
    transcript_sha256: str = ""
    problems: list[str] = field(default_factory=list)
    proposed_assignment: dict | None = None
    comparable: bool = False
    generated_session_completeness: str = ""
    requires_reinforced_confirmation: bool = False
    terminal_record: dict | None = None
    note: str = ("imported as a synthetic transcript. It is NOT comparable: no "
                 "window exists yet, and none is created automatically.")

    def to_dict(self) -> dict:
        return asdict(self)


def _digest(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def transcript_is_stable(path: Path, *, reads: int = SETTLE_READS,
                         pause: float = SETTLE_SECONDS,
                         sleeper=time.sleep) -> tuple[bool, str]:
    """Same size and hash across consecutive reads, and parseable JSON."""
    if not path.is_file():
        return False, "transcript.json does not exist"
    first = _digest(path)
    for _ in range(max(reads - 1, 1)):
        sleeper(pause)
        again = _digest(path)
        if again != first:
            return False, ("transcript.json is still changing between reads; the "
                           "session appears to be mid-write")
        first = again
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, f"transcript.json is not valid JSON: {exc}"
    entries = payload if isinstance(payload, list) else payload.get("transcript")
    if not isinstance(entries, list) or not entries:
        return False, "transcript.json contains no transcript entries"
    return True, "stable across consecutive reads and parseable"


def _evidence_problems(job: JobRecord, record) -> list[str]:
    problems: list[str] = []
    if record is None:
        problems.append(
            "no terminal record was written for this job, so there is no evidence "
            "the session finished. A transcript on disk is not that evidence.")
        return problems
    if record.termination_kind == TerminationKind.USER_CANCELLED.value:
        problems.append("this session was cancelled; a cancelled run is not "
                        "imported as a completed session")
    if record.exit_code != 0:
        problems.append(f"the session exited with code {record.exit_code}")
    if not record.transcript_parseable:
        problems.append("the recorded transcript does not parse")
    if record.config_sha256 and record.config_sha256 != job.config_sha256:
        problems.append(
            f"the worker ran config {record.config_sha256[:12]}… but the job records "
            f"{job.config_sha256[:12]}…")
    if record.completion_quality not in (CLEAN, CAPPED):
        problems.append(
            f"completion quality is {record.completion_quality}; only "
            f"{CLEAN} or {CAPPED} may be imported")
    return problems


def staging_dir(project: Project) -> Path:
    return safe_path(project.subdir("cache"), STAGING_DIRNAME)


def import_session_output(project: Project, job: JobRecord, *,
                          plan: GenerationRunPlan | None = None,
                          on_collision=import_service.CollisionPolicy.REJECT,
                          sleeper=time.sleep) -> ImportOutcome:
    outcome = ImportOutcome(session_id=job.session_id, ok=False)
    if on_collision is import_service.CollisionPolicy.REPLACE_INVALIDATE_DERIVED:
        raise GenerationError(
            "a generated output never replaces an existing transcript silently; use "
            "REJECT or NEW_VERSION")
    if job.status != JobStatus.COMPLETED.value:
        outcome.problems.append(
            f"the job is {job.status}; only a COMPLETED session is imported")
        return outcome

    record = load_terminal_record(job.terminal_record_path) \
        if job.terminal_record_path else None
    outcome.terminal_record = record.to_dict() if record else None
    evidence = _evidence_problems(job, record)
    if evidence:
        outcome.problems += evidence
        return outcome

    path = Path(job.expected_output_directory) / "transcript.json"
    stable, reason = transcript_is_stable(path, sleeper=sleeper)
    if not stable:
        outcome.problems.append(reason)
        return outcome

    raw = path.read_bytes()
    outcome.transcript_sha256 = hashlib.sha256(raw).hexdigest()
    if record.transcript_sha256 and record.transcript_sha256 != \
            outcome.transcript_sha256:
        outcome.problems.append(
            f"the transcript changed after the worker recorded it: "
            f"{record.transcript_sha256[:12]}… became "
            f"{outcome.transcript_sha256[:12]}…")
        return outcome

    # Staging is UNIQUE and atomic, and exists only so a later reader can see what
    # was handed to the importer. It never uses a name another artefact could own.
    staging = staging_dir(project)
    staging.mkdir(parents=True, exist_ok=True)
    staged = safe_path(staging,
                       f"{job.session_id}.{uuid.uuid4().hex[:8]}.transcript.json")
    atomic_write_text(staged, raw.decode("utf-8", errors="replace"),
                      on_exists=OnExists.FAIL)

    try:
        # import_service owns collision resolution and final persistence. Nothing
        # under a shared name has been written at this point.
        imported = import_service.import_transcript(
            project, filename=f"{job.session_id}.json", content=raw,
            transcript_type="synthetic", transcript_id=job.session_id,
            window_declaration=None, on_collision=on_collision)
        if not imported.ok:
            outcome.problems += [p.message for p in imported.problems if p.blocking]
            if outcome.problems:
                return outcome
    finally:
        # Only our own staging file, and only after the importer has decided.
        staged.unlink(missing_ok=True)

    outcome.ok = True
    outcome.transcript_id = imported.transcript_id
    outcome.generated_session_completeness = record.completion_quality
    outcome.requires_reinforced_confirmation = (
        record.completion_quality == CAPPED)
    if outcome.requires_reinforced_confirmation:
        outcome.note += (" The session hit the max-turns safety cap with the guide "
                         "unfinished; it is potentially incomplete and does not "
                         "join a comparative study without explicit confirmation.")

    if plan is not None:
        try:
            session = plan.session(job.session_id)
        except GenerationError:
            session = None
        if session is not None:
            outcome.proposed_assignment = {
                "transcript_id": imported.transcript_id,
                "condition_id": session.condition_id,
                "focus_group_id": session.focus_group_id,
                "replicate_index": session.replicate_index,
                "role": "SYNTHETIC_RUN",
                "confirmed": False,
                "generated_session_completeness": record.completion_quality,
                "requires_reinforced_confirmation":
                    outcome.requires_reinforced_confirmation,
                "note": ("proposed from the run plan. It is not written until the "
                         "researcher confirms it."),
            }

    audit.record(project.path, audit.GENERATE, project_id=project.project_id,
                 subject=job.job_id,
                 detail={"action": "imported_output",
                         "session_id": job.session_id,
                         "transcript_id": imported.transcript_id,
                         "transcript_sha256": outcome.transcript_sha256,
                         "config_sha256": job.config_sha256,
                         "completion_quality": record.completion_quality,
                         "exit_code": record.exit_code,
                         "comparable": False})
    return outcome


def confirm_assignment(project: Project, proposal: dict, *,
                       reinforced_confirmation: str = "") -> object:
    """
    Write the proposed assignment. Only ever after the researcher says so.

    A capped session needs the transcript id typed back: it is potentially incomplete,
    and putting it into a comparative cell is a methodological decision, not a click.
    """
    from ..services import design_service
    if not proposal:
        raise GenerationError("there is no proposed assignment to confirm")
    if proposal.get("requires_reinforced_confirmation"):
        if reinforced_confirmation.strip() != proposal["transcript_id"]:
            raise GenerationError(
                f"{proposal['transcript_id']} hit the max-turns cap and is "
                f"potentially incomplete. To assign it to a comparative study, type "
                f"its transcript id to confirm.")
    return design_service.assign(
        project, transcript_id=proposal["transcript_id"],
        condition_id=proposal["condition_id"],
        focus_group_id=proposal["focus_group_id"],
        role=proposal["role"],
        replicate_index=proposal.get("replicate_index"))


def design_from_plan(project: Project, plan: GenerationRunPlan, study) -> dict:
    """
    A synthetic StudyDesign matching the plan, offered for creation.

    No human condition and no human reference: the plan generated synthetic sessions
    and knows nothing about a human corpus.
    """
    from .. import design as D
    conditions = [D.Condition(condition_id=c, label=c.replace("-", " ").title(),
                              side=D.Side.SYNTHETIC.value,
                              expected_replicates=study.replicates)
                  for c in study.synthetic_conditions]
    design = D.StudyDesign(
        design_id="default", project_id=project.project_id,
        study_name=study.generation_study_id,
        conditions=conditions,
        focus_groups=[D.FocusGroup(focus_group_id=f) for f in study.focus_groups],
        human_reference_policy=D.HumanReferencePolicy.OPTIONAL.value,
        matching_policy=D.MatchingPolicy.NONE.value,
        created_utc=datetime.now(UTC).isoformat())
    return {
        "design": design,
        "expected_positions": [
            {"condition_id": s.condition_id, "focus_group_id": s.focus_group_id,
             "replicate_index": s.replicate_index, "session_id": s.session_id}
            for s in plan.sessions],
        "human_reference": ("none is created; a human corpus is imported and "
                            "declared separately"),
    }
