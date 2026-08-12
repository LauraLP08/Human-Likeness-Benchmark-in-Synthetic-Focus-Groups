"""
Study design, transcript assignment, coverage and aggregation for a user's corpus.

The one service that knows what a study looks like. It persists the design and the
assignments, checks them against what is actually on disk, and drives the
design-parametrised engine.

TWO THINGS IT REFUSES TO DO.

  Infer an assignment. No condition, focus group or replicate index is ever read from
  a file name. `assign()` takes them; `import_manifest()` reads them from a manifest
  the user wrote. Both record who said so.

  Aggregate a stale or absent result. Only FRESH Level 2 results enter an aggregate.
  A cell that is short of a run reports n=2 of 3 and lists what is missing; nothing is
  imputed and nothing is quietly dropped from the denominator.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from .. import analysis_window as AW
from ..design import (CoverageReport, DesignError, DesignStatus, Role, Side,
                      StudyDesign, TranscriptAssignment, WindowStatus,
                      assignment_from_dict, build_coverage, design_from_dict,
                      validate_design)
from ..design_aggregate import (DISPLAY_METRIC_IDS, aggregate_route_a,
                                aggregate_route_b, summarise_conditions)
from ..paths import safe_component, safe_path
from ..projects import Project
from . import audit, import_service, structural_service, window_service

DESIGN_DIRNAME = "design"
DESIGN_FILENAME = "study_design.json"
ASSIGNMENTS_FILENAME = "transcript_assignments.json"

MANIFEST_COLUMNS = ("transcript_id", "condition_id", "focus_group_id",
                    "replicate_index", "role")


class DesignServiceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def design_dir(project: Project) -> Path:
    return safe_path(project.subdir("derived"), DESIGN_DIRNAME)


# ------------------------------------------------------------------ persistence
def save_design(project: Project, design: StudyDesign) -> Path:
    problems = validate_design(design)
    if problems:
        raise DesignServiceError(
            "the design is not valid and was not saved: " + "; ".join(problems))
    directory = design_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_path(directory, DESIGN_FILENAME)
    atomic_write_text(target, json.dumps(design.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    audit.record(project.path, audit.DESIGN, project_id=project.project_id,
                 subject=design.design_id,
                 detail={"action": "design_saved",
                         "n_conditions": len(design.conditions),
                         "n_focus_groups": len(design.focus_groups),
                         "expected_replicates":
                             design.expected_replicates_by_condition,
                         "human_reference_policy": design.human_reference_policy})
    return target


def load_design(project: Project) -> StudyDesign | None:
    target = design_dir(project) / DESIGN_FILENAME
    if not target.is_file():
        return None
    return design_from_dict(json.loads(target.read_text(encoding="utf-8")))


def save_assignments(project: Project,
                     assignments: list[TranscriptAssignment]) -> Path:
    directory = design_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_path(directory, ASSIGNMENTS_FILENAME)
    atomic_write_text(
        target,
        json.dumps([a.to_dict() for a in assignments], indent=1, ensure_ascii=False),
        on_exists=OnExists.REPLACE, verify=lambda written: json.loads(written))
    return target


def load_assignments(project: Project) -> list[TranscriptAssignment]:
    target = design_dir(project) / ASSIGNMENTS_FILENAME
    if not target.is_file():
        return []
    return [assignment_from_dict(a)
            for a in json.loads(target.read_text(encoding="utf-8"))]


# ------------------------------------------------------------------ assignment
def assign(project: Project, *, transcript_id: str, condition_id: str,
           focus_group_id: str, role: str,
           replicate_index: int | None = None) -> TranscriptAssignment:
    """
    Place one transcript in one logical position.

    The hashes are read from the canonical form ON DISK at this moment, so the
    assignment records what was actually assigned. Re-importing the transcript later
    changes its hash and the assignment goes STALE - which is the intended outcome,
    not a fault.
    """
    safe_component(transcript_id, field="transcript_id")
    stored = {t["transcript_id"]: t
              for t in import_service.stored_transcripts(project)}
    record = stored.get(transcript_id)
    if record is None:
        raise DesignServiceError(
            f"{transcript_id!r} is not stored in this project; import it before "
            f"assigning it")

    design = load_design(project)
    if design is None:
        raise DesignServiceError("no study design is saved for this project")
    if condition_id not in design.condition_ids:
        raise DesignServiceError(
            f"condition {condition_id!r} is not declared in the design "
            f"({design.condition_ids})")
    if focus_group_id not in design.focus_group_ids:
        raise DesignServiceError(
            f"focus group {focus_group_id!r} is not declared in the design "
            f"({design.focus_group_ids})")
    if role not in (Role.HUMAN_REFERENCE.value, Role.SYNTHETIC_RUN.value):
        raise DesignServiceError(f"unknown role {role!r}")

    # ---- the transcript's ACTUAL type decides which role it may hold. A file the
    # user declared human at import cannot become a synthetic run by being assigned
    # to one: the two sides are measured by different producers, and a mis-assigned
    # transcript would be scored by the wrong instrument.
    transcript_type = record["transcript_type"]
    side = design.condition(condition_id).side
    if transcript_type == "human" and role != Role.HUMAN_REFERENCE.value:
        raise DesignServiceError(
            f"{transcript_id!r} was imported as a HUMAN transcript, so it can only "
            f"be assigned as {Role.HUMAN_REFERENCE.value}. A human transcript is "
            f"measured by the human producer; placing it in a synthetic run would "
            f"score it with the wrong instrument.")
    if transcript_type == "synthetic" and role != Role.SYNTHETIC_RUN.value:
        raise DesignServiceError(
            f"{transcript_id!r} was imported as a SYNTHETIC transcript, so it can "
            f"only be assigned as {Role.SYNTHETIC_RUN.value}. If it really is the "
            f"human reference, re-import it declaring it human.")
    if role == Role.HUMAN_REFERENCE.value and side != Side.HUMAN.value:
        raise DesignServiceError(
            f"condition {condition_id!r} is declared {side}; a human reference "
            f"belongs in a HUMAN condition")
    if role == Role.SYNTHETIC_RUN.value and side != Side.SYNTHETIC.value:
        raise DesignServiceError(
            f"condition {condition_id!r} is declared {side}; a synthetic run belongs "
            f"in a SYNTHETIC condition")
    if role == Role.HUMAN_REFERENCE.value and replicate_index is not None:
        raise DesignServiceError(
            "a human reference has no replicate index: there is one human focus "
            "group, not a set of runs over it")
    if role == Role.SYNTHETIC_RUN.value and replicate_index is None:
        raise DesignServiceError(
            f"a synthetic run needs a replicate index (1.."
            f"{design.condition(condition_id).expected_replicates}); without one it "
            f"has no position in the design and cannot be grouped")

    state = window_service.window_state(project, transcript_id)
    window = {
        AW.WindowStatus.LOCKED.value: WindowStatus.COMPARABLE_WINDOW.value,
        AW.WindowStatus.RAW_FULL_TRANSCRIPT.value: WindowStatus.FULL_TRANSCRIPT.value,
    }.get(state.window_status, WindowStatus.UNDECLARED.value)

    assignment = TranscriptAssignment(
        transcript_id=transcript_id, condition_id=condition_id,
        focus_group_id=focus_group_id, role=role,
        source_sha256=record["source_sha256"],
        canonical_sha256=record["canonical_sha256"],
        replicate_index=replicate_index, window_status=window,
        assigned_utc=_now(),
        analysis_input_id=state.analysis_input_id,
        window_id=state.window.window_id if state.window else None,
        window_artifact_sha256=(state.window.window_artifact_sha256
                                if state.window else None))

    existing = [a for a in load_assignments(project)
                if a.transcript_id != transcript_id]
    existing.append(assignment)
    save_assignments(project, existing)
    audit.record(project.path, audit.ASSIGN, project_id=project.project_id,
                 subject=transcript_id,
                 detail={"condition_id": condition_id,
                         "focus_group_id": focus_group_id, "role": role,
                         "replicate_index": replicate_index,
                         "window_status": window,
                         "canonical_sha256": record["canonical_sha256"]})
    return assignment


def unassign(project: Project, transcript_id: str) -> None:
    remaining = [a for a in load_assignments(project)
                 if a.transcript_id != transcript_id]
    save_assignments(project, remaining)
    audit.record(project.path, audit.ASSIGN, project_id=project.project_id,
                 subject=transcript_id, detail={"action": "unassigned"})


def import_manifest(project: Project, text: str) -> tuple[list[TranscriptAssignment],
                                                          list[str]]:
    """
    Assign from an explicit CSV manifest the user wrote.

    Columns: transcript_id, condition_id, focus_group_id, replicate_index, role.
    Every value is read from the manifest; nothing is derived from a file name.
    """
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return [], ["the manifest is empty"]
    missing = [c for c in MANIFEST_COLUMNS if c not in rows[0]]
    if missing:
        return [], [f"the manifest is missing column(s) {missing}; expected "
                    f"{list(MANIFEST_COLUMNS)}"]

    assigned, problems = [], []
    for index, row in enumerate(rows, start=2):
        raw = (row.get("replicate_index") or "").strip()
        try:
            assigned.append(assign(
                project, transcript_id=(row["transcript_id"] or "").strip(),
                condition_id=(row["condition_id"] or "").strip(),
                focus_group_id=(row["focus_group_id"] or "").strip(),
                role=(row["role"] or "").strip(),
                replicate_index=int(raw) if raw else None))
        except (DesignServiceError, ValueError) as exc:
            problems.append(f"line {index}: {exc}")
    return assigned, problems


# -------------------------------------------------------------------- coverage
def eligibility_map(project: Project) -> dict[str, dict]:
    """
    For every stored transcript: does it have a window, is it locked, is there a
    current Level 2 result over it, and may it enter a comparison.

    One place answers all five questions, so the coverage matrix and the aggregation
    gate cannot drift apart.
    """
    results = structural_service.restore_results(project)
    by_input = {r.analysis_input_id: r for r in results.values()}

    out: dict[str, dict] = {}
    for record in import_service.stored_transcripts(project):
        transcript_id = record["transcript_id"]
        state = window_service.window_state(project, transcript_id)
        result = by_input.get(state.analysis_input_id)
        out[transcript_id] = {
            "window_present": state.window is not None,
            "window_locked": bool(state.window and state.window.locked),
            "window_status": state.window_status,
            "window_id": state.window.window_id if state.window else None,
            "analysis_input_id": state.analysis_input_id,
            "namespace": state.namespace,
            "level2_fresh": bool(result
                                 and result.freshness == structural_service.FRESH),
            "comparison_eligible": bool(result and result.aggregation_eligible),
            "reason": (result.stale_reason if (result and result.stale_reason)
                       else state.reason),
        }
    return out


def coverage(project: Project) -> CoverageReport:
    design = load_design(project)
    if design is None:
        raise DesignServiceError("no study design is saved for this project")
    stored = import_service.stored_transcripts(project)
    return build_coverage(
        design, load_assignments(project),
        current_hashes={t["transcript_id"]: t["canonical_sha256"] for t in stored},
        known_transcript_ids=[t["transcript_id"] for t in stored],
        eligibility=eligibility_map(project))


def readiness(project: Project) -> dict:
    """A compact answer to "can I aggregate yet, and if not, what is missing"."""
    design = load_design(project)
    if design is None:
        return {"status": DesignStatus.EMPTY.value, "design": None,
                "reasons": ["no study design is saved for this project"],
                "route_a": False, "route_b": False}

    report = coverage(project)
    eligibility = eligibility_map(project)
    assignments = load_assignments(project)
    assigned_ids = {a.transcript_id for a in assignments}

    no_window = sorted(t for t in assigned_ids
                       if t in eligibility and not eligibility[t]["window_present"])
    not_locked = sorted(t for t in assigned_ids
                        if t in eligibility and eligibility[t]["window_present"]
                        and not eligibility[t]["window_locked"])
    without_result = sorted(t for t in assigned_ids
                            if t in eligibility
                            and eligibility[t]["window_locked"]
                            and not eligibility[t]["level2_fresh"])
    ineligible = sorted(t for t in assigned_ids
                        if t in eligibility and eligibility[t]["level2_fresh"]
                        and not eligibility[t]["comparison_eligible"])

    reasons = list(report.problems)
    if report.missing_assigned_transcript_ids:
        reasons.append("assigned but no longer stored: "
                       f"{report.missing_assigned_transcript_ids}")
    if no_window:
        reasons.append(f"no comparable window has been created for {no_window}")
    if not_locked:
        reasons.append(f"the window is not locked for {not_locked}")
    if without_result:
        reasons.append(f"Level 2 has not been computed over the window for "
                       f"{without_result}")
    if ineligible:
        reasons.append(f"computed but not comparison-eligible: {ineligible}")
    if report.missing_human_focus_groups:
        reasons.append("focus groups without a human reference: "
                       f"{report.missing_human_focus_groups}")

    route_a = (report.status not in (DesignStatus.INVALID.value,
                                     DesignStatus.EMPTY.value)
               and report.ready_for_comparison)
    return {
        "status": report.status,
        "design_id": design.design_id,
        "coverage": report.to_dict(),
        "reasons": reasons,
        "route_a": route_a,
        "route_b": route_a and report.route_b_available,
        "route_b_reason": report.route_b_reason,
        "transcripts_without_window": no_window,
        "transcripts_without_locked_window": not_locked,
        "transcripts_without_result": without_result,
        "transcripts_not_eligible": ineligible,
        "stale_transcripts": sorted(report.stale_transcript_ids),
        "missing_transcripts": sorted(report.missing_assigned_transcript_ids),
    }


# ----------------------------------------------------------------- aggregation
def aggregate(project: Project, *, metric_ids=None) -> dict:
    """
    Route A and, when the design allows it, route B.

    Only FRESH Level 2 results are fed in. A stale one is excluded and named, not
    silently used and not silently dropped.
    """
    design = load_design(project)
    if design is None:
        raise DesignServiceError("no study design is saved for this project")
    metric_ids = tuple(metric_ids or DISPLAY_METRIC_IDS)

    assignments = load_assignments(project)
    report = coverage(project)

    # THE GATE. The engine is keyed by transcript, so the filtering happens here: a
    # transcript contributes only through an analytical input that is fresh, locked,
    # in the comparable namespace and marked eligible. A full-session result and a
    # proposed window are both absent from this mapping, so neither can enter a mean.
    results = structural_service.restore_results(project)
    by_input = {r.analysis_input_id: r for r in results.values()}
    eligibility = eligibility_map(project)
    run_results: dict[str, list[dict]] = {}
    excluded: list[dict] = []
    for a in assignments:
        info = eligibility.get(a.transcript_id)
        result = by_input.get(info["analysis_input_id"]) if info else None
        if result is not None and result.aggregation_eligible:
            run_results[a.transcript_id] = result.rows
        else:
            excluded.append({
                "transcript_id": a.transcript_id,
                "analysis_input_id": (info or {}).get("analysis_input_id"),
                "namespace": (info or {}).get("namespace"),
                "reason": ((info or {}).get("reason")
                           or "no analytical input for this transcript")})

    cells = aggregate_route_a(design, assignments, run_results,
                              metric_ids=metric_ids, coverage=report)
    conditions = summarise_conditions(design, cells)
    replicates, route_b_reason = aggregate_route_b(
        design, assignments, run_results, metric_ids=metric_ids, coverage=report)

    audit.record(project.path, audit.COMPUTE, project_id=project.project_id,
                 subject=design.design_id,
                 detail={"action": "aggregate", "status": report.status,
                         "n_cells": len(cells), "n_replicates": len(replicates),
                         "route_b_available": report.route_b_available,
                         "n_fresh_results": len(run_results)})

    return {
        "design": design.to_dict(),
        "coverage": report.to_dict(),
        "route_a": [c.to_dict() for c in cells],
        "condition_summary": [c.to_dict() for c in conditions],
        "route_b": [r.to_dict() for r in replicates],
        "route_b_available": report.route_b_available,
        "route_b_reason": route_b_reason,
        "metric_ids": list(metric_ids),
        "analysis_inputs_used": {t: eligibility[t]["analysis_input_id"]
                                 for t in sorted(run_results)
                                 if t in eligibility},
        "excluded": excluded,
        "excluded_stale": sorted(
            r.analysis_input_id or t for t, r in results.items()
            if r.freshness != structural_service.FRESH),
        "namespace": AW.COMPARABLE_NAMESPACE,
        "namespace_rule": ("every contributing result is a LOCKED comparable window "
                           "in _comparable_window; full-session results are never "
                           "mixed in"),
        "inference": "none performed; all figures are descriptive",
        "frozen_benchmark_used": False,
    }


# ------------------------------------------------------------------ table rows
def route_a_rows(payload: dict) -> list[dict]:
    from .. import theme
    out = []
    for cell in payload["route_a"]:
        stat = cell["stat"]
        out.append({
            "metric_id": cell["metric_id"],
            "metric": theme.metric_label(cell["metric_id"]),
            "condition_id": cell["condition_id"],
            "focus_group_id": cell["focus_group_id"],
            "mean": stat["mean"], "mean_display": theme.format_value(stat["mean"]),
            "median_display": theme.format_value(stat["median"]),
            "sd_display": theme.format_value(stat["sd"]),
            "range_display": theme.format_value(stat["range"]),
            "n_valid": stat["n_valid"], "n_expected": stat["n_expected"],
            "human_reference": cell["human_reference"],
            "human_display": theme.format_value(cell["human_reference"]),
            "coverage_status": cell["coverage_status"],
            "missing_replicates": cell["missing_replicates"],
            "aggregation_rule": cell["aggregation_rule"],
            "transcript_ids": cell["transcript_ids"],
        })
    return out


def route_b_rows(payload: dict) -> list[dict]:
    from .. import theme
    out = []
    for rep in payload["route_b"]:
        stat = rep["stat"]
        out.append({
            "metric_id": rep["metric_id"],
            "metric": theme.metric_label(rep["metric_id"]),
            "condition_id": rep["condition_id"],
            "replicate_index": rep["replicate_index"],
            "mean": stat["mean"], "mean_display": theme.format_value(stat["mean"]),
            "sd_display": theme.format_value(stat["sd"]),
            "range_display": theme.format_value(stat["range"]),
            "n_valid": stat["n_valid"], "n_expected": stat["n_expected"],
            "coverage_status": rep["coverage_status"],
            "missing_focus_groups": rep["missing_focus_groups"],
            "aggregation_rule": rep["aggregation_rule"],
            "focus_groups_included": rep["focus_groups_included"],
        })
    return out


def coverage_matrix(report: CoverageReport, design: StudyDesign) -> list[dict]:
    """
    FG x condition, showing ELIGIBLE/expected rather than merely present/expected.

    A cell with three files, one of which is a full session, reads `2/3` here and
    names the ineligible one. Reporting `3/3` would be true about files and false
    about the comparison.
    """
    human_state = {p.transcript_id: p for p in report.human_positions}
    out = []
    for fg in design.focus_group_ids:
        human_ids = report.human_by_focus_group.get(fg, [])
        human_label = "—"
        if human_ids:
            states = [human_state.get(i) for i in human_ids]
            marks = [f"{i} ({s.display})" if s and not s.complete_for_comparison
                     else i for i, s in zip(human_ids, states)]
            human_label = ", ".join(marks)
        row = {"focus_group_id": fg, "human_reference": human_label}
        for condition in design.synthetic_conditions:
            cell = report.cell(condition.condition_id, fg)
            flags = []
            if cell.duplicates:
                flags.append("duplicate")
            if cell.missing_transcript_ids:
                flags.append("missing transcript")
            if cell.stale_transcript_ids:
                flags.append("stale")
            if cell.missing_replicates:
                flags.append(f"missing {cell.missing_replicates}")
            for item in cell.ineligible:
                if item["reason"] not in flags:
                    flags.append(item["reason"])
            row[condition.condition_id] = (
                f"{cell.eligible}/{cell.expected}"
                + (f" ({', '.join(flags)})" if flags else ""))
        out.append(row)
    return out


def compute_for_assignment(project: Project, transcript_id: str, *,
                           use_window: bool = True):
    """
    Run Level 2 over the analytical input this transcript currently offers.

    With a locked window, the producer sees ONLY the retained turns. Without one, the
    whole session is measured and the result is filed as descriptive.
    """
    payload = import_service.load_canonical(project, transcript_id)
    transcript = import_service.rehydrate(payload)
    state = window_service.window_state(project, transcript_id)
    analysis_input = window_service.analysis_input(project, transcript_id,
                                                   use_window=use_window)
    turns = None
    if use_window and state.window is not None:
        turns = window_service.windowed_turns(project, state.window)
    return structural_service.run_structural(
        project, transcript, roster_names=payload.get("roster_names") or None,
        window_declaration=payload.get("window_declaration"),
        canonical_sha256=payload["canonical_sha256"],
        analysis_input=analysis_input, turns_override=turns)
