"""
Import and normalisation of a user's transcript.

The interface hands over bytes, a filename and a declared type. Everything else -
where the upload lands, schema detection, per-entry validation, the canonical form,
the validation report - happens here.

TWO THINGS ARE NEVER GUESSED.

  The transcript type. The user declares human or synthetic and the file must match;
  a declared-human file that carries the synthetic markers is refused rather than
  reinterpreted.

  Participant identity. A human transcript whose entries lack `canonical_speaker_id`
  leaves those turns unresolved and blocks the metrics that need them. No participant
  is assigned by position, and the roster is asked for rather than inferred.

NOTHING IS OVERWRITTEN BY DEFAULT (Phase 3B). Importing a second file under an
identifier that already exists is REJECTED unless the caller states what should
happen. `REPLACE_INVALIDATE_DERIVED` exists but must be asked for by name, and it
archives every derived artefact of the old canonical rather than leaving a Level 2
result pointing at a hash that no longer exists.

VALIDATION IS PERSISTED PER TRANSCRIPT. `derived/validation/<transcript_id>.json`,
written atomically beside the canonical form. An export reads the report belonging to
the transcript being exported; there is no path by which the report of one transcript
can travel with the results of another.

Problems come back as `ImportProblem` objects with a stable code, a sentence a
researcher can act on, and the remedy. The interface renders those; it never renders
a traceback.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..config import DataDirResolution
from ..paths import PathValidationError, safe_component, safe_path, slugify
from ..projects import Project, create_project, list_projects, load_project
from ..transcripts import (CanonicalTranscript, CanonicalTurn,
                           EmptyEntryAccounting, NormalisationRecord, ReviewItem,
                           SchemaDetectionError, TranscriptError, TurnProvenance,
                           normalise_transcript)
from . import audit

CANONICAL_DIRNAME = "canonical"
VALIDATION_DIRNAME = "validation"
ARCHIVE_DIRNAME = "archive"
TRANSCRIPT_TYPES = ("human", "synthetic")

# What the uploaded synthetic file IS. Declared, never detected: the difference
# between a full session and an already-trimmed comparable window is not visible in
# the file, and getting it wrong silently would corrupt every comparison downstream.
WINDOW_DECLARATIONS = ("comparable_window", "full_transcript")

# Keys that change on every save and must not enter the canonical digest, or the same
# transcript would hash differently each time it was written.
VOLATILE_CANONICAL_KEYS = ("saved_utc", "canonical_sha256")


class ImportError_(RuntimeError):
    """Raised only for programming faults; user-facing problems are ImportProblem."""


class CollisionPolicy(str, Enum):
    """
    What to do when the identifier already exists.

      REJECT                      the default. Nothing is touched.
      NEW_VERSION                 keeps both: the new one becomes `<id>__v002`.
      REPLACE_INVALIDATE_DERIVED  explicit only. The old canonical, its validation and
                                  its Level 2 result are ARCHIVED, not deleted, and
                                  the assignment that referenced the old hash goes
                                  STALE rather than silently inheriting new numbers.
    """

    REJECT = "REJECT"
    NEW_VERSION = "NEW_VERSION"
    REPLACE_INVALIDATE_DERIVED = "REPLACE_INVALIDATE_DERIVED"


@dataclass
class ImportProblem:
    code: str
    message: str
    remedy: str
    blocking: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


PROBLEM_CODES = (
    "invalid_file",
    "unsupported_schema",
    "unresolved_participant_identity",
    "missing_roster",
    "incomplete_comparable_window",
    "metric_undefined",
    "methodological_comparison_unavailable",
    "protected_benchmark_source_changed",
    "transcript_id_collision",
    "traceability_mismatch",
    "stale_result",
)


@dataclass
class ImportOutcome:
    ok: bool
    transcript: CanonicalTranscript | None
    canonical_path: str | None
    upload_path: str | None
    problems: list[ImportProblem] = field(default_factory=list)
    validation_report: dict = field(default_factory=dict)
    transcript_id: str | None = None
    canonical_sha256: str | None = None
    version: int = 1
    replaced: bool = False

    @property
    def blocking_problems(self) -> list[ImportProblem]:
        return [p for p in self.problems if p.blocking]


# ---------------------------------------------------------------- projects
def new_project(name: str, data_dir: DataDirResolution, *,
                description: str = "") -> Project:
    project = create_project(name, data_dir, description=description)
    audit.record(project.path, audit.DESIGN, project_id=project.project_id,
                 subject=project.project_id, detail={"action": "project_created"})
    return project


def open_project(project_id: str, data_dir: DataDirResolution) -> Project:
    return load_project(project_id, data_dir)


def all_projects(data_dir: DataDirResolution) -> list[dict]:
    out = []
    for p in list_projects(data_dir):
        out.append({"project_id": p.project_id, "name": p.name,
                    "description": p.description, "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "n_transcripts": len(stored_transcripts(p))})
    return out


def canonical_dir(project: Project) -> Path:
    return safe_path(project.subdir("derived"), CANONICAL_DIRNAME)


def validation_dir(project: Project) -> Path:
    return safe_path(project.subdir("derived"), VALIDATION_DIRNAME)


def archive_dir(project: Project) -> Path:
    return safe_path(project.subdir("derived"), ARCHIVE_DIRNAME)


# ------------------------------------------------------------------- hashing
def canonical_digest(payload: dict) -> str:
    """
    A stable digest of the canonical form.

    Computed over the payload with the volatile keys removed and the keys sorted, so
    re-reading a stored canonical and hashing it again gives the same value. Without
    that, `saved_utc` alone would make every transcript look changed on every read and
    the STALE check would fire constantly - which is the same as having no check.
    """
    body = {k: v for k, v in payload.items() if k not in VOLATILE_CANONICAL_KEYS}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------- discovery
def stored_transcripts(project: Project) -> list[dict]:
    """
    Everything on disk. This - not session state - is the source of truth.
    """
    directory = canonical_dir(project)
    if not directory.is_dir():
        return []
    out = []
    for child in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(child.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        transcript_id = payload.get("transcript_id", child.stem)
        out.append({
            "transcript_id": transcript_id,
            "base_transcript_id": audit.base_transcript_id(transcript_id),
            "version": audit.version_number(transcript_id),
            "transcript_type": payload.get("transcript_type"),
            "path": str(child),
            "n_turns": len(payload.get("turns") or []),
            "focus_group": payload.get("focus_group"),
            "condition": payload.get("condition"),
            "window_declaration": payload.get("window_declaration"),
            "roster_names": payload.get("roster_names") or [],
            "source_sha256": payload.get("source_sha256"),
            "canonical_sha256": canonical_digest(payload),
            "has_validation": validation_path(project, transcript_id).is_file(),
            "fully_resolved": not [t for t in (payload.get("turns") or [])
                                   if t.get("unresolved_fields")],
        })
    return out


def current_canonical_hashes(project: Project) -> dict[str, str]:
    return {t["transcript_id"]: t["canonical_sha256"]
            for t in stored_transcripts(project)}


def transcript_exists(project: Project, transcript_id: str) -> bool:
    directory = canonical_dir(project)
    return (directory / f"{transcript_id}.json").is_file()


def next_version_id(project: Project, transcript_id: str) -> str:
    base = audit.base_transcript_id(transcript_id)
    version = 2
    while transcript_exists(project, f"{base}__v{version:03d}"):
        version += 1
    return f"{base}__v{version:03d}"


# ---------------------------------------------------------------- validation
def validation_path(project: Project, transcript_id: str) -> Path:
    safe_component(transcript_id, field="transcript_id")
    return safe_path(validation_dir(project), f"{transcript_id}.json")


def save_validation_report(project: Project, transcript_id: str, report: dict, *,
                           source_sha256: str, canonical_sha256: str,
                           normaliser_version: str,
                           generated_utc: str | None = None) -> Path:
    """
    Persist the report for ONE transcript, keyed by its id and bound to its hashes.

    The timestamp is on the envelope; the report body is deterministic, so two
    imports of the same bytes produce the same body.
    """
    directory = validation_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": generated_utc or datetime.now(UTC).isoformat(),
        "transcript_id": transcript_id,
        "source_sha256": source_sha256,
        "canonical_sha256": canonical_sha256,
        "normaliser_version": normaliser_version,
        "validation_report": report,
    }
    target = validation_path(project, transcript_id)
    atomic_write_text(target, json.dumps(payload, indent=1, ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_validation_report(project: Project, transcript_id: str) -> dict:
    target = validation_path(project, transcript_id)
    if not target.is_file():
        raise ImportError_(
            f"no validation report stored for {transcript_id!r}; re-import the "
            f"transcript so its report is written beside its canonical form")
    return json.loads(target.read_text(encoding="utf-8"))


def stored_validation_reports(project: Project) -> list[dict]:
    directory = validation_dir(project)
    if not directory.is_dir():
        return []
    out = []
    for child in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(child.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({"transcript_id": payload.get("transcript_id", child.stem),
                    "generated_utc": payload.get("generated_utc"),
                    "source_sha256": payload.get("source_sha256"),
                    "canonical_sha256": payload.get("canonical_sha256"),
                    "normaliser_version": payload.get("normaliser_version"),
                    "path": str(child)})
    return out


def build_validation_report(transcript: CanonicalTranscript,
                            problems: list[ImportProblem]) -> dict:
    record = transcript.normalisation
    unresolved = [
        {"turn_id": t.turn_id,
         "original_turn_id": t.original_turn_id,
         "original_index": t.original_index,
         "unresolved_fields": t.unresolved_fields,
         "speaker_id": t.original_speaker_id}
        for t in transcript.turns if not t.resolved]

    return {
        "transcript_id": transcript.transcript_id,
        "transcript_type": transcript.transcript_type,
        "source_file": transcript.source_file,
        "source_sha256": transcript.source_sha256,
        "schema_detected": record.input_schema_detected,
        "normaliser_version": record.normaliser_version,
        "n_entries": record.n_entries,
        "n_turns": len(transcript.turns),
        "empty_entries": {
            "found": record.empty_entries.found,
            "retained_in_canonical": record.empty_entries.retained_in_canonical,
            "excluded_by_producer_rule":
                record.empty_entries.excluded_by_producer_rule,
            "turn_ids": record.empty_entries.turn_ids,
            "rule": record.empty_entries.rule,
        },
        "turn_ids": {
            "duplicate_original_turn_ids": record.duplicate_original_turn_ids,
            "missing_original_turn_ids": record.missing_original_turn_ids,
            "rule": "reported as provenance; entries are never renumbered",
        },
        "unresolved_turns": unresolved,
        "n_unresolved_turns": len(unresolved),
        "blocked_fields": sorted(transcript.blocked_fields()),
        "unmapped_source_fields": record.unmapped_source_fields,
        "warnings": record.warnings,
        "review_items": [{"kind": r.kind, "subject": r.subject, "detail": r.detail,
                          "blocking": r.blocking} for r in transcript.review_items],
        "problems": [p.to_dict() for p in problems],
        "fully_resolved": transcript.fully_resolved,
    }


def _identity_problems(transcript: CanonicalTranscript,
                       roster_names) -> list[ImportProblem]:
    problems: list[ImportProblem] = []
    blocked = sorted(transcript.blocked_fields())
    if blocked:
        n = len(transcript.unresolved_turn_ids)
        problems.append(ImportProblem(
            code="unresolved_participant_identity",
            message=(f"{n} intervention(s) do not resolve {', '.join(blocked)}. "
                     f"No speaker is assigned by position, so the metrics that need "
                     f"those fields cannot be computed."),
            remedy=("edit the source so every intervention carries the field, or "
                    "supply the mapping explicitly; the affected turns are listed in "
                    "the validation report")))
    if transcript.transcript_type == "human" and not roster_names:
        problems.append(ImportProblem(
            code="missing_roster",
            message=("the human structural producer needs the participant roster; "
                     "it is not derived from the transcript."),
            remedy=("provide the participant names (one per line), normally from "
                    "participant_metadata.json for this focus group")))
    return problems


def _window_problems(transcript: CanonicalTranscript,
                     window_declaration: str | None) -> list[ImportProblem]:
    """
    A synthetic full session is not a comparable window, and no window is derived for
    it here. The Macho Meals boundaries belong to that study and are not reapplied.
    """
    if transcript.transcript_type != "synthetic":
        return []
    if window_declaration == "comparable_window":
        return []
    return [ImportProblem(
        code="incomplete_comparable_window",
        message=("this file is declared a full transcript, not a comparable window. "
                 "No general rule for deriving a window is implemented, and the "
                 "Macho Meals boundaries are specific to that study and are not "
                 "applied to another corpus."),
        remedy=("either upload the already-trimmed comparable window and declare it "
                "as such, or record the boundaries as a researcher decision. "
                "Descriptive structural results over the full transcript are still "
                "produced and are labelled as such."),
        blocking=False)]


# ------------------------------------------------------------------- import
def import_transcript(project: Project, *, filename: str, content: bytes,
                      transcript_type: str,
                      transcript_id: str | None = None,
                      focus_group: str | None = None,
                      condition: str | None = None,
                      replicate_label: str | None = None,
                      model: str | None = None,
                      roster_names: list[str] | None = None,
                      window_declaration: str | None = None,
                      on_collision: CollisionPolicy = CollisionPolicy.REJECT
                      ) -> ImportOutcome:
    """
    Store the upload, normalise it, and report. Never raises for a bad file.
    """
    if transcript_type not in TRANSCRIPT_TYPES:
        raise ImportError_(
            f"transcript_type must be one of {list(TRANSCRIPT_TYPES)}, got "
            f"{transcript_type!r} - the user declares this; it is never detected")
    if window_declaration is not None and \
            window_declaration not in WINDOW_DECLARATIONS:
        raise ImportError_(
            f"window_declaration must be one of {list(WINDOW_DECLARATIONS)}")
    on_collision = CollisionPolicy(on_collision)

    requested = slugify(transcript_id or Path(filename).stem)
    try:
        safe_component(requested, field="transcript_id")
    except PathValidationError as exc:
        return ImportOutcome(False, None, None, None, [ImportProblem(
            code="invalid_file",
            message=f"the file name does not produce a usable identifier: {exc}",
            remedy="rename the file using letters, digits, hyphen or underscore")])

    # ---- collision policy, decided BEFORE anything is written
    stem, replaced, version = requested, False, 1
    if transcript_exists(project, requested):
        if on_collision is CollisionPolicy.REJECT:
            return ImportOutcome(False, None, None, None, [ImportProblem(
                code="transcript_id_collision",
                message=(f"a transcript called {requested!r} already exists in this "
                         f"project. Nothing has been changed."),
                remedy=("import as a new version to keep both, or choose a different "
                        "identifier. Replacing is a separate, explicit action "
                        "because it invalidates the Level 2 results and the "
                        "assignments that referenced the old file."))],
                transcript_id=requested)
        if on_collision is CollisionPolicy.NEW_VERSION:
            stem = next_version_id(project, requested)
            version = audit.version_number(stem)
        else:
            replaced = True

    uploads = project.subdir("uploads")
    uploads.mkdir(parents=True, exist_ok=True)
    upload_path = safe_path(uploads, f"{stem}.json")
    atomic_write_text(upload_path, content.decode("utf-8", errors="replace"),
                      on_exists=OnExists.REPLACE)

    try:
        transcript = normalise_transcript(
            upload_path, transcript_type=transcript_type, transcript_id=stem,
            focus_group=focus_group, condition=condition,
            replicate_label=replicate_label, model=model)
    except SchemaDetectionError as exc:
        return ImportOutcome(False, None, None, str(upload_path), [ImportProblem(
            code="unsupported_schema", message=str(exc),
            remedy=("supported schemas are the standardized human transcript and the "
                    "synthetic session log; a file must match exactly one, for all "
                    "of its entries"))], transcript_id=stem)
    except (TranscriptError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return ImportOutcome(False, None, None, str(upload_path), [ImportProblem(
            code="invalid_file", message=str(exc),
            remedy=("check the file is UTF-8 JSON containing a list of entries, or "
                    "an object with a `transcript` array"))], transcript_id=stem)

    if replaced:
        archive_derived(project, stem)

    problems = _identity_problems(transcript, roster_names)
    problems += _window_problems(transcript, window_declaration)

    canonical_path, digest = save_canonical(
        project, transcript, window_declaration=window_declaration,
        roster_names=roster_names)
    report = build_validation_report(transcript, problems)
    save_validation_report(project, stem, report,
                           source_sha256=transcript.source_sha256,
                           canonical_sha256=digest,
                           normaliser_version=transcript.normalisation
                           .normaliser_version)

    audit.record(project.path,
                 audit.VERSION if (version > 1 or replaced) else audit.IMPORT,
                 project_id=project.project_id, subject=stem,
                 detail={"requested_id": requested, "version": version,
                         "policy": on_collision.value, "replaced": replaced,
                         "transcript_type": transcript_type,
                         "n_entries": transcript.normalisation.n_entries,
                         "source_sha256": transcript.source_sha256,
                         "canonical_sha256": digest,
                         "window_declaration": window_declaration,
                         "n_problems": len(problems)})

    return ImportOutcome(
        ok=not [p for p in problems if p.blocking],
        transcript=transcript, canonical_path=str(canonical_path),
        upload_path=str(upload_path), problems=problems,
        validation_report=report, transcript_id=stem, canonical_sha256=digest,
        version=version, replaced=replaced)


def archive_derived(project: Project, transcript_id: str) -> list[str]:
    """
    Move the derived artefacts of a transcript out of the way before it is replaced.

    Archived, not deleted - and moved rather than left in place, so a Level 2 result
    computed from the previous bytes cannot be read as if it belonged to the new ones.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    destination = safe_path(archive_dir(project), f"{transcript_id}_{stamp}")
    destination.mkdir(parents=True, exist_ok=True)

    moved: list[str] = []
    candidates = [
        canonical_dir(project) / f"{transcript_id}.json",
        validation_dir(project) / f"{transcript_id}.json",
        project.subdir("runs") / "level2" / f"{transcript_id}.json",
    ]
    # Every Level 2 result over this transcript, whichever analytical input produced
    # it. A window's result must not survive the replacement of the bytes under it.
    runs = project.subdir("runs") / "level2"
    if runs.is_dir():
        for child in sorted(runs.glob("*.json")):
            try:
                payload = json.loads(child.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if payload.get("source_transcript_id") == transcript_id \
                    or payload.get("transcript_id") == transcript_id:
                candidates.append(child)
    for source in dict.fromkeys(candidates):
        if source.is_file():
            target = destination / f"{source.parent.name}_{source.name}"
            shutil.move(str(source), str(target))
            moved.append(str(target))
    audit.record(project.path, audit.VERSION, project_id=project.project_id,
                 subject=transcript_id,
                 detail={"action": "archived_derived", "n_files": len(moved),
                         "archive": str(destination)})
    return moved


def save_canonical(project: Project, transcript: CanonicalTranscript, *,
                   window_declaration: str | None = None,
                   roster_names: list[str] | None = None) -> tuple[Path, str]:
    """Write the canonical form into the project's data directory."""
    directory = canonical_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    payload = transcript.to_dict()
    payload["window_declaration"] = window_declaration
    payload["roster_names"] = list(roster_names or [])
    digest = canonical_digest(payload)
    payload["canonical_sha256"] = digest
    payload["saved_utc"] = datetime.now(UTC).isoformat()

    target = safe_path(directory, f"{transcript.transcript_id}.json")
    atomic_write_text(target, json.dumps(payload, indent=1, ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target, digest


def load_canonical(project: Project, transcript_id: str) -> dict:
    safe_component(transcript_id, field="transcript_id")
    target = safe_path(canonical_dir(project), f"{transcript_id}.json",
                       must_exist=True)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["canonical_sha256"] = canonical_digest(payload)
    return payload


def migrate_project(project: Project) -> dict:
    """
    Bring a Phase 3A project up to the Phase 3B contract.

    Phase 3A wrote canonical forms but kept the validation report in session state,
    and stored no hash with a Level 2 result. Both are rebuilt or diagnosed here:

      * a canonical form with no validation report gets one, rebuilt FROM THE STORED
        CANONICAL. The source bytes are not re-read; the report describes what is
        actually on disk.
      * a Level 2 result with no recorded hash is left alone and reported. It cannot
        be adopted, because there is no way to know which bytes produced it - and
        guessing would be exactly the failure the hash exists to prevent. It shows as
        STALE until it is recomputed.

    Idempotent: running it twice changes nothing the second time.
    """
    written, already, unverifiable = [], [], []
    for record in stored_transcripts(project):
        transcript_id = record["transcript_id"]
        if validation_path(project, transcript_id).is_file():
            already.append(transcript_id)
            continue
        payload = load_canonical(project, transcript_id)
        transcript = rehydrate(payload)
        report = build_validation_report(transcript, [])
        save_validation_report(
            project, transcript_id, report,
            source_sha256=transcript.source_sha256,
            canonical_sha256=payload["canonical_sha256"],
            normaliser_version=transcript.normalisation.normaliser_version)
        written.append(transcript_id)

    runs = project.subdir("runs") / RUNS_LEVEL2_DIRNAME
    if runs.is_dir():
        for child in sorted(runs.glob("*.json")):
            try:
                stored = json.loads(child.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not stored.get("canonical_sha256"):
                unverifiable.append(child.stem)

    if written or unverifiable:
        audit.record(project.path, audit.VERSION, project_id=project.project_id,
                     subject=project.project_id,
                     detail={"action": "migrated_from_phase_3a",
                             "validation_reports_written": len(written),
                             "results_without_hash": len(unverifiable)})
    return {
        "validation_reports_written": sorted(written),
        "validation_reports_already_present": sorted(already),
        "level2_results_without_hash": sorted(unverifiable),
        "note": ("a Level 2 result with no recorded canonical hash is shown as STALE "
                 "and must be recomputed; it is never adopted on trust"),
    }


RUNS_LEVEL2_DIRNAME = "level2"


def migration_report(project: Project) -> dict:
    """
    What a Phase 3B project looks like under the Phase 3C rules.

    Nothing is promoted. A result computed from a transcript the user once DECLARED a
    comparable window is `LEGACY_UNVERIFIED_WINDOW`: readable as history, excluded
    from every comparison until a window is actually created and locked. Turning an
    old declaration into a locked artefact automatically would manufacture exactly the
    reviewed decision this phase exists to require.
    """
    from . import structural_service, window_service

    legacy, descriptive, current = [], [], []
    for result in structural_service.restore_results(project).values():
        if result.calculation_status == "LEGACY_UNVERIFIED_WINDOW":
            legacy.append(result.analysis_input_id or result.transcript_id)
        elif result.analysis_input_id and result.window_id:
            current.append(result.analysis_input_id)
        else:
            descriptive.append(result.analysis_input_id or result.transcript_id)

    without_window = sorted(
        t["transcript_id"] for t in stored_transcripts(project)
        if window_service.active_window(project, t["transcript_id"]) is None)

    return {
        "legacy_unverified_window": sorted(legacy),
        "descriptive_only": sorted(descriptive),
        "current_windowed_results": sorted(current),
        "transcripts_without_window": without_window,
        "promotion_policy": ("an import-time declaration is NOT promoted to a locked "
                             "window; create the window and lock it, then recompute"),
        "history_policy": "legacy results stay readable and are never deleted",
    }


def replacement_preview(project: Project, transcript_id: str) -> dict:
    """
    What REPLACE would do, before it is done.

    Everything listed is archived or invalidated - nothing is unlinked. The caller
    must confirm by typing the transcript id, so a replacement cannot happen by
    clicking in the wrong row.
    """
    from . import design_service, structural_service, window_service

    windows = [w.window_id for w in window_service.windows_for(project,
                                                               transcript_id)]
    results = [r.analysis_input_id
               for r in structural_service.restore_results(project).values()
               if r.transcript_id == transcript_id]
    assignments = [a.to_dict() for a in design_service.load_assignments(project)
                   if a.transcript_id == transcript_id]
    return {
        "transcript_id": transcript_id,
        "canonical_archived": transcript_exists(project, transcript_id),
        "validation_archived": validation_path(project, transcript_id).is_file(),
        "level2_results_archived": sorted(results),
        "windows_invalidated": sorted(windows),
        "assignments_becoming_stale": assignments,
        "reversible": True,
        "note": ("nothing is deleted: the canonical form, its validation and its "
                 "Level 2 results are moved into derived/archive/, the windows are "
                 "left in place but no longer match the new canonical, and the "
                 "assignments go STALE until they are re-made"),
        "confirmation_required": (f"type {transcript_id!r} to confirm"),
    }


def rehydrate(payload: dict) -> CanonicalTranscript:
    """
    Rebuild the canonical object from its stored JSON, so a later session can run
    Level 2 without re-reading the upload. The stored form is the source of truth;
    nothing is re-detected and nothing is re-derived.
    """
    turns = [CanonicalTurn(
        turn_id=t["turn_id"], original_turn_id=t["original_turn_id"],
        original_index=t["original_index"],
        original_speaker_id=t["original_speaker_id"],
        canonical_speaker_id=t["canonical_speaker_id"],
        speaker_role=t["speaker_role"], speaker_name=t["speaker_name"],
        text=t["text"], guide_question=t.get("guide_question"),
        provenance=TurnProvenance(**t["provenance"]),
        unresolved_fields=list(t.get("unresolved_fields") or []))
        for t in payload["turns"]]

    record = dict(payload["normalisation"])
    record["empty_entries"] = EmptyEntryAccounting(**record["empty_entries"])
    return CanonicalTranscript(
        transcript_id=payload["transcript_id"], source_file=payload["source_file"],
        source_sha256=payload["source_sha256"],
        transcript_type=payload["transcript_type"],
        focus_group=payload.get("focus_group"), condition=payload.get("condition"),
        replicate_label=payload.get("replicate_label"), model=payload.get("model"),
        normalisation=NormalisationRecord(**record), turns=turns,
        review_items=[ReviewItem(**r) for r in payload.get("review_items") or []])
