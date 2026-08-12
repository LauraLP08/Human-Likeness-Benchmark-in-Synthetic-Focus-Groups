"""
Comparable windows for a user's corpus: propose, preview, review, lock, supersede.

A LOCKED window is immutable. Changing one means creating the next version and marking
the previous SUPERSEDED - never editing in place, never deleting. The old window keeps
its identity and its historical results keep meaning, because the numbers they carry
were computed from an artefact that still exists and still hashes the same.

Window ids are versioned per transcript:

    <transcript_id>__window_v001
    <transcript_id>__window_v002
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..analysis_window import (COMPARABLE_NAMESPACE, ComparableWindow,
                               DerivationMethod, WindowError, WindowStatus,
                               analysis_input_for_full_run,
                               analysis_input_for_window, build_window,
                               confirm_entire_transcript, locate_text_boundary,
                               preview as preview_window, window_from_dict)
from ..atomic import OnExists, atomic_write_text
from ..level2 import STRUCTURAL_METRIC_IDS
from ..paths import safe_component, safe_path
from ..projects import Project
from . import audit, import_service

WINDOWS_DIRNAME = "windows"
WINDOW_ID = re.compile(r"^(?P<stem>.+)__window_v(?P<n>\d{3})$")


class WindowServiceError(RuntimeError):
    pass


def windows_dir(project: Project) -> Path:
    return safe_path(project.subdir("derived"), WINDOWS_DIRNAME)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _side(transcript_type: str) -> str:
    return "human" if transcript_type == "human" else "synthetic"


# ------------------------------------------------------------------ persistence
def save_window(project: Project, window: ComparableWindow) -> Path:
    directory = windows_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    safe_component(window.window_id, field="window_id")
    target = safe_path(directory, f"{window.window_id}.json")
    atomic_write_text(target, json.dumps(window.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_window(project: Project, window_id: str) -> ComparableWindow:
    safe_component(window_id, field="window_id")
    target = safe_path(windows_dir(project), f"{window_id}.json", must_exist=True)
    return window_from_dict(json.loads(target.read_text(encoding="utf-8")))


def all_windows(project: Project) -> list[ComparableWindow]:
    directory = windows_dir(project)
    if not directory.is_dir():
        return []
    out = []
    for child in sorted(directory.glob("*.json")):
        try:
            out.append(window_from_dict(
                json.loads(child.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def windows_for(project: Project, transcript_id: str) -> list[ComparableWindow]:
    return [w for w in all_windows(project)
            if w.source_transcript_id == transcript_id]


def active_window(project: Project, transcript_id: str) -> ComparableWindow | None:
    """
    The window that currently speaks for this transcript.

    A LOCKED one wins. Otherwise the newest that is not superseded or rejected -
    because a proposal under review is still the thing the researcher is working on.
    """
    candidates = [w for w in windows_for(project, transcript_id)
                  if w.status not in (WindowStatus.SUPERSEDED.value,
                                      WindowStatus.REJECTED.value)]
    if not candidates:
        return None
    locked = [w for w in candidates if w.locked]
    pool = locked or candidates
    return max(pool, key=lambda w: _version_of(w.window_id))


def _version_of(window_id: str) -> int:
    match = WINDOW_ID.match(window_id or "")
    return int(match.group("n")) if match else 0


def next_window_id(project: Project, transcript_id: str) -> str:
    version = max((_version_of(w.window_id)
                   for w in windows_for(project, transcript_id)), default=0) + 1
    return f"{transcript_id}__window_v{version:03d}"


# --------------------------------------------------------------------- creation
def _canonical(project: Project, transcript_id: str) -> tuple[dict, list[dict], str]:
    payload = import_service.load_canonical(project, transcript_id)
    return payload, payload["turns"], payload["canonical_sha256"]


def propose_manual_window(project: Project, transcript_id: str, *,
                          start_turn_id: str | None = None,
                          end_turn_id: str | None = None,
                          start_char_offset: int | None = None,
                          end_char_offset: int | None = None,
                          start_text: str | None = None,
                          end_text: str | None = None,
                          researcher_label: str = "",
                          researcher_note: str = "",
                          positional_fallback_used: bool = False,
                          supersedes_window_id: str | None = None
                          ) -> ComparableWindow:
    """
    Propose a window from explicit boundaries.

    Boundaries may be given as turn ids or as text. Text that matches once resolves to
    that turn; text that matches zero or several times leaves the window UNDER_REVIEW
    with the count recorded - the platform does not pick one for you.
    """
    payload, turns, canonical_sha = _canonical(project, transcript_id)
    review: list[str] = []
    unambiguous = True

    if start_text:
        matches, reason = locate_text_boundary(turns, start_text)
        if len(matches) == 1:
            start_turn_id = matches[0]["turn_id"]
            if start_char_offset is None:
                start_char_offset = matches[0]["char_offset"]
        else:
            unambiguous = False
            review.append(f"start boundary: {reason}")
    if end_text:
        matches, reason = locate_text_boundary(turns, end_text)
        if len(matches) == 1:
            end_turn_id = matches[0]["turn_id"]
            if end_char_offset is None:
                end_char_offset = (matches[0]["char_offset"]
                                   + len(end_text.strip()))
        else:
            unambiguous = False
            review.append(f"end boundary: {reason}")

    if positional_fallback_used:
        if not researcher_label.strip() or not researcher_note.strip():
            raise WindowServiceError(
                "a positional boundary is a researcher decision, not a fallback the "
                "platform applies: it needs a researcher label and a note explaining "
                "why the boundary could not be located by text")

    window = build_window(
        window_id=next_window_id(project, transcript_id),
        source_transcript_id=transcript_id,
        source_canonical_sha256=canonical_sha,
        side=_side(payload["transcript_type"]), turns=turns,
        start_turn_id=start_turn_id, end_turn_id=end_turn_id,
        start_char_offset=start_char_offset, end_char_offset=end_char_offset,
        derivation_method=DerivationMethod.MANUAL.value,
        positional_fallback_used=positional_fallback_used,
        unambiguous=unambiguous, researcher_label=researcher_label,
        researcher_note=researcher_note, proposed_utc=_now(),
        supersedes_window_id=supersedes_window_id, review_problems=review)

    save_window(project, window)
    audit.record(project.path, audit.WINDOW, project_id=project.project_id,
                 subject=window.window_id,
                 detail={"action": "proposed", "method": window.derivation_method,
                         "status": window.status,
                         "n_retained_turns": window.n_retained_turns,
                         "n_source_turns": window.n_source_turns,
                         "unambiguous": window.unambiguous,
                         "positional_fallback_used": positional_fallback_used,
                         "researcher_label": researcher_label,
                         "window_artifact_sha256": window.window_artifact_sha256,
                         "source_canonical_sha256": canonical_sha})
    return window


def confirm_whole_transcript(project: Project, transcript_id: str, *,
                             researcher_label: str, researcher_note: str = "",
                             supersedes_window_id: str | None = None
                             ) -> ComparableWindow:
    payload, turns, canonical_sha = _canonical(project, transcript_id)
    window = confirm_entire_transcript(
        window_id=next_window_id(project, transcript_id),
        source_transcript_id=transcript_id,
        source_canonical_sha256=canonical_sha,
        side=_side(payload["transcript_type"]), turns=turns,
        researcher_label=researcher_label, researcher_note=researcher_note,
        proposed_utc=_now(), supersedes_window_id=supersedes_window_id)
    save_window(project, window)
    audit.record(project.path, audit.WINDOW, project_id=project.project_id,
                 subject=window.window_id,
                 detail={"action": "confirmed_entire_transcript",
                         "status": window.status,
                         "n_retained_turns": window.n_retained_turns,
                         "researcher_label": researcher_label,
                         "window_artifact_sha256": window.window_artifact_sha256,
                         "source_canonical_sha256": canonical_sha})
    return window


def preview(project: Project, window_id: str, *, context: int = 3,
            page: int = 1, page_size: int = 25) -> dict:
    window = load_window(project, window_id)
    _payload, turns, _ = _canonical(project, window.source_transcript_id)
    return preview_window(turns, window, context=context, page=page,
                          page_size=page_size)


# ------------------------------------------------------------- A5 diagnostics
@dataclass
class WindowDiagnostics:
    """
    What a locked window actually contains. INFORMATIONAL by construction.

    Windows of different lengths are not automatically a fault - a focus group that
    ran short IS shorter, and trimming it to match would fabricate comparability
    rather than measure it. So nothing here blocks, nothing is normalised, and there
    is NO default threshold: the only threshold that exists is one the researcher
    sets for their own study.
    """

    transcript_id: str
    window_id: str
    side: str
    n_source_turns: int
    n_retained_turns: int
    retained_turn_proportion: float | None
    retained_words: int
    participant_turns: int
    moderator_turns: int
    participant_count: int
    derivation_method: str
    positional_fallback_used: bool
    focus_group: str | None = None
    condition: str | None = None
    replicate_index: int | None = None
    status: str = "INFORMATIONAL"
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def diagnostics_for(project: Project, window: ComparableWindow) -> WindowDiagnostics:
    turns = windowed_turns(project, window)
    participants = {t.get("canonical_speaker_id") for t in turns
                    if t.get("speaker_role") == "participant"}
    return WindowDiagnostics(
        transcript_id=window.source_transcript_id, window_id=window.window_id,
        side=window.side, n_source_turns=window.n_source_turns,
        n_retained_turns=window.n_retained_turns,
        retained_turn_proportion=(window.n_retained_turns / window.n_source_turns
                                  if window.n_source_turns else None),
        retained_words=sum(len((t.get("text") or "").split()) for t in turns),
        participant_turns=len([t for t in turns
                               if t.get("speaker_role") == "participant"]),
        moderator_turns=len([t for t in turns
                             if t.get("speaker_role") == "moderator"]),
        participant_count=len(participants - {None}),
        derivation_method=window.derivation_method,
        positional_fallback_used=window.positional_fallback_used)


def window_diagnostics(project: Project, *, assignments=None,
                       thresholds: dict | None = None) -> list[WindowDiagnostics]:
    """
    One row per LOCKED window, with the design position when it is assigned.

    `thresholds` is optional and has NO default. Supplying, say,
    `{"retained_turn_proportion_min": 0.5}` marks the rows below it
    REVIEW_SUGGESTED. Nothing becomes BLOCKED, here or anywhere.
    """
    by_transcript = {a.transcript_id: a for a in (assignments or [])}
    out: list[WindowDiagnostics] = []
    for window in all_windows(project):
        if not window.locked:
            continue
        try:
            row = diagnostics_for(project, window)
        except (WindowServiceError, Exception):                # noqa: BLE001
            continue
        assignment = by_transcript.get(window.source_transcript_id)
        if assignment is not None:
            row.focus_group = assignment.focus_group_id
            row.condition = assignment.condition_id
            row.replicate_index = assignment.replicate_index
        for name, minimum in (thresholds or {}).items():
            value = getattr(row, name.removesuffix("_min"), None)
            if value is not None and value < minimum:
                row.status = "REVIEW_SUGGESTED"
                row.flags.append(f"{name.removesuffix('_min')}={value} is below the "
                                 f"threshold you set ({minimum})")
        out.append(row)
    return out


def diagnostics_summary(rows: list[WindowDiagnostics]) -> list[dict]:
    """Range and median per focus group x condition. Descriptive, never a gate."""
    import statistics

    grouped: dict[tuple, list[WindowDiagnostics]] = {}
    for row in rows:
        grouped.setdefault((row.condition or "—", row.focus_group or "—"),
                           []).append(row)

    out = []
    for (condition, focus_group), group in sorted(grouped.items()):
        for field_name in ("n_retained_turns", "retained_words",
                           "participant_turns", "participant_count"):
            values = [getattr(g, field_name) for g in group
                      if getattr(g, field_name) is not None]
            if not values:
                continue
            out.append({
                "condition": condition, "focus_group": focus_group,
                "measure": field_name, "n_windows": len(values),
                "median": statistics.median(values),
                "minimum": min(values), "maximum": max(values),
                "range": max(values) - min(values),
                "status": ("REVIEW_SUGGESTED"
                           if any(g.status == "REVIEW_SUGGESTED" for g in group)
                           else "INFORMATIONAL"),
            })
    return out


# ----------------------------------------------------------------- transitions
def lock_window(project: Project, window_id: str, *, researcher_label: str = "",
                researcher_note: str = "") -> ComparableWindow:
    window = load_window(project, window_id)
    if window.locked:
        raise WindowServiceError(f"{window_id} is already locked")
    if window.status in (WindowStatus.SUPERSEDED.value,
                         WindowStatus.REJECTED.value):
        raise WindowServiceError(
            f"{window_id} is {window.status} and cannot be locked; create a new "
            f"version instead")
    if not window.unambiguous or window.review_problems:
        raise WindowServiceError(
            f"{window_id} is under review and cannot be locked: "
            + "; ".join(window.review_problems or ["the boundary is ambiguous"])
            + ". Resolve the boundary, or record an explicit positional decision.")

    # A LOCKED window is a decision, and a decision has an author. Without one it
    # stays a proposal - the artefact would otherwise carry the authority of a
    # review that nobody performed.
    label = (researcher_label or window.researcher_label or "").strip()
    if not label:
        raise WindowServiceError(
            f"{window_id} cannot be locked without a researcher: locking is a "
            f"review decision and the artefact records who made it. The window "
            f"stays {window.status} until a reviewer is named.")

    note = (researcher_note or window.researcher_note or "").strip()
    needs_note = []
    if window.derivation_method == \
            DerivationMethod.CONFIRMED_ENTIRE_TRANSCRIPT.value:
        needs_note.append("the whole transcript is being confirmed as the window")
    if window.positional_fallback_used:
        needs_note.append("the boundary was set by position")
    if window.supersedes_window_id:
        needs_note.append(f"this supersedes {window.supersedes_window_id}")
    if window.status == WindowStatus.UNDER_REVIEW.value:
        needs_note.append("an ambiguous proposal is being resolved by hand")
    if needs_note and not note:
        raise WindowServiceError(
            f"{window_id} needs a researcher note because "
            + "; ".join(needs_note)
            + ". These are judgements a later reader cannot reconstruct from the "
              "boundaries alone.")

    _payload, _turns, canonical_sha = _canonical(project,
                                                 window.source_transcript_id)
    if canonical_sha != window.source_canonical_sha256:
        raise WindowServiceError(
            f"{window_id} was derived from canonical "
            f"{window.source_canonical_sha256[:12]}… but the transcript is now "
            f"{canonical_sha[:12]}…; re-propose the window against the current "
            f"transcript")

    window.status = WindowStatus.LOCKED.value
    window.reviewed_utc = window.reviewed_utc or _now()
    window.locked_utc = _now()
    if researcher_label:
        window.researcher_label = researcher_label
    if researcher_note:
        window.researcher_note = researcher_note
    save_window(project, window)

    # A newly locked window supersedes the one it replaces, and only then.
    if window.supersedes_window_id:
        _mark_superseded(project, window.supersedes_window_id, window.window_id)

    audit.record(project.path, audit.WINDOW, project_id=project.project_id,
                 subject=window_id,
                 detail={"action": "locked",
                         "window_artifact_sha256": window.window_artifact_sha256,
                         "supersedes": window.supersedes_window_id,
                         "researcher_label": window.researcher_label})
    return window


def _mark_superseded(project: Project, window_id: str, by_window_id: str) -> None:
    try:
        previous = load_window(project, window_id)
    except Exception:                                       # noqa: BLE001
        return
    previous.status = WindowStatus.SUPERSEDED.value
    previous.superseded_by_window_id = by_window_id
    save_window(project, previous)
    audit.record(project.path, audit.WINDOW, project_id=project.project_id,
                 subject=window_id,
                 detail={"action": "superseded", "by": by_window_id})


def supersede_window(project: Project, window_id: str, **kwargs
                     ) -> ComparableWindow:
    """
    Replace a locked window with a new version.

    The previous one is NOT edited and NOT deleted: it becomes SUPERSEDED once the new
    version is locked, and the results computed from it keep their meaning because the
    artefact they name still exists and still hashes the same.
    """
    previous = load_window(project, window_id)
    kwargs.setdefault("researcher_label", previous.researcher_label)
    if previous.derivation_method == \
            DerivationMethod.CONFIRMED_ENTIRE_TRANSCRIPT.value \
            and not kwargs.get("start_turn_id") and not kwargs.get("start_text"):
        return confirm_whole_transcript(
            project, previous.source_transcript_id,
            researcher_label=kwargs.get("researcher_label", ""),
            researcher_note=kwargs.get("researcher_note", ""),
            supersedes_window_id=window_id)
    return propose_manual_window(project, previous.source_transcript_id,
                                 supersedes_window_id=window_id, **kwargs)


def reject_window(project: Project, window_id: str, *, researcher_note: str = ""
                  ) -> ComparableWindow:
    window = load_window(project, window_id)
    if window.locked:
        raise WindowServiceError(
            f"{window_id} is locked; supersede it with a new version rather than "
            f"rejecting it")
    window.status = WindowStatus.REJECTED.value
    window.reviewed_utc = _now()
    if researcher_note:
        window.researcher_note = researcher_note
    save_window(project, window)
    audit.record(project.path, audit.WINDOW, project_id=project.project_id,
                 subject=window_id, detail={"action": "rejected"})
    return window


def edit_locked_window(project: Project, window_id: str) -> None:
    """There is no such operation. Named so the refusal is discoverable."""
    raise WindowServiceError(
        "a locked window is immutable. Create a new version with supersede_window(); "
        "the previous one becomes SUPERSEDED and keeps its results")


# ------------------------------------------------------------- analysis inputs
@dataclass
class TranscriptWindowState:
    transcript_id: str
    side: str
    n_source_turns: int
    source_canonical_sha256: str
    window: ComparableWindow | None
    window_status: str
    analysis_input_id: str
    namespace: str
    comparison_eligible: bool
    reason: str
    versions: list[str] = field(default_factory=list)


def window_state(project: Project, transcript_id: str) -> TranscriptWindowState:
    record = {t["transcript_id"]: t
              for t in import_service.stored_transcripts(project)}.get(transcript_id)
    if record is None:
        raise WindowServiceError(f"{transcript_id!r} is not stored in this project")

    window = active_window(project, transcript_id)
    side = _side(record["transcript_type"])
    if window is None:
        return TranscriptWindowState(
            transcript_id=transcript_id, side=side,
            n_source_turns=record["n_turns"],
            source_canonical_sha256=record["canonical_sha256"], window=None,
            window_status=WindowStatus.RAW_FULL_TRANSCRIPT.value,
            analysis_input_id=f"{transcript_id}__fullrun",
            namespace="_full_run_descriptive", comparison_eligible=False,
            reason=("no comparable window exists for this transcript; results over "
                    "the whole session are descriptive only"),
            versions=[])

    stale = window.source_canonical_sha256 != record["canonical_sha256"]
    eligible = window.locked and not stale
    return TranscriptWindowState(
        transcript_id=transcript_id, side=side,
        n_source_turns=record["n_turns"],
        source_canonical_sha256=record["canonical_sha256"], window=window,
        window_status=window.status,
        analysis_input_id=window.window_id,
        namespace=COMPARABLE_NAMESPACE if eligible else "_full_run_descriptive",
        comparison_eligible=eligible,
        reason=("a locked comparable window" if eligible else
                (f"the window was derived from a different version of the "
                 f"transcript" if stale else
                 f"the window is {window.status}; only a LOCKED window may feed a "
                 f"comparison")),
        versions=sorted(w.window_id for w in windows_for(project, transcript_id)))


def analysis_input(project: Project, transcript_id: str, *,
                   use_window: bool = True):
    """The analytical input this transcript currently offers."""
    state = window_state(project, transcript_id)
    if use_window and state.window is not None:
        return analysis_input_for_window(
            state.window, eligible_metrics=list(STRUCTURAL_METRIC_IDS),
            created_utc=_now())
    return analysis_input_for_full_run(
        transcript_id=transcript_id, side=state.side,
        source_canonical_sha256=state.source_canonical_sha256,
        eligible_metrics=list(STRUCTURAL_METRIC_IDS), created_utc=_now())


def windowed_turns(project: Project, window: ComparableWindow) -> list[dict]:
    """The canonical turns the window retains, in order, with their text trimmed."""
    from ..analysis_window import select_turns
    _payload, turns, _ = _canonical(project, window.source_transcript_id)
    start = window.start_boundary or {}
    end = window.end_boundary or {}
    retained, problems = select_turns(
        turns, start_turn_id=start.get("turn_id"), end_turn_id=end.get("turn_id"),
        start_char_offset=start.get("char_offset"),
        end_char_offset=end.get("char_offset"))
    if problems:
        raise WindowServiceError("; ".join(problems))
    return [dict(turn, text=text) for turn, text in retained]
