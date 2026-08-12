"""
New evaluation: import, design, assign, coverage, aggregate, export.

State comes FROM DISK on every run. `st.session_state` holds nothing but the widgets'
own values - which transcript is selected, what the user typed. Reopening the browser
rebuilds the project from the files in it.
"""
from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from platform_core import design as D
from platform_core import theme
from platform_core.config import DataDirError, resolve_data_dir
from platform_core.services import (audit, design_service, export_service,
                                    import_service, structural_service,
                                    window_service)
from platform_core.services.context import (ComparabilityStatus, SourceType,
                                            build_context, load_context,
                                            save_context)

from .. import ui
from . import windows_tab

STRUCTURAL_COLUMNS = [("metric", "Metric"), ("value_display", "Value"),
                      ("status", "Status"), ("denominator_display", "Denominator"),
                      ("denominator_definition", "Denominator is")]

FRESHNESS_LABELS = {structural_service.FRESH: "Current",
                    structural_service.STALE: "Stale — recompute",
                    structural_service.MISSING: "Transcript missing"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def render(state) -> None:
    st.title("New evaluation")

    try:
        data_dir = resolve_data_dir()
    except DataDirError as exc:
        st.error(f"**Data directory unavailable**\n\n{exc}")
        return

    project_id = state.get("project_id")
    if not project_id:
        st.info("Open or create a project on the Home page first.")
        return

    try:
        project = import_service.open_project(project_id, data_dir)
    except Exception as exc:                       # noqa: BLE001 - shown, not raised
        st.error(f"**Project could not be opened**\n\n{exc}")
        return

    st.caption(f"Project **{project.name}** · `{project.path}`")
    st.info("Level 1 (thematic fidelity) is **not available** for an uploaded "
            "corpus: it needs a codebook and a coding procedure for your study. "
            "No model is called anywhere in this phase.")

    tabs = st.tabs(["1 · Import", "2 · Study design", "3 · Assignment",
                    "4 · Comparable windows", "5 · Coverage", "6 · Comparison",
                    "7 · Export"])
    with tabs[0]:
        _import(state, project)
    with tabs[1]:
        _design(state, project)
    with tabs[2]:
        _assignment(state, project)
    with tabs[3]:
        windows_tab.render(state, project)
    with tabs[4]:
        _coverage(state, project)
    with tabs[5]:
        _comparison(state, project)
    with tabs[6]:
        _export(state, project)


# --------------------------------------------------------------------- import
def _import(state, project) -> None:
    stored = import_service.stored_transcripts(project)
    results = structural_service.restore_results(project)

    if stored:
        st.markdown("**Transcripts in this project**")
        rows = [dict(t, level2=FRESHNESS_LABELS.get(
            results[t["transcript_id"]].freshness, "Not computed")
            if t["transcript_id"] in results else "Not computed")
            for t in stored]
        ui.table(rows, [("transcript_id", "Id"), ("version", "v"),
                        ("transcript_type", "Type"), ("n_turns", "Turns"),
                        ("window_declaration", "Declared at upload — not a reviewed window"),
                        ("fully_resolved", "Resolved"),
                        ("has_validation", "Validation"),
                        ("level2", "Level 2")])

    st.markdown("**Import a transcript**")
    uploaded = st.file_uploader("Transcript JSON", type=["json"])
    left, right = st.columns(2)
    transcript_type = left.radio(
        "This file is", ["human", "synthetic"], horizontal=True,
        help="Declared by you. It is never detected from the file name.")
    window_declaration = None
    roster_text = ""
    if transcript_type == "synthetic":
        window_declaration = right.radio(
            "Declared at upload — not a reviewed window",
            list(import_service.WINDOW_DECLARATIONS),
            format_func=lambda v: ("The uploader says it is already trimmed"
                                   if v == "comparable_window"
                                   else "A full session transcript"),
            help="This is a note about the file, not a decision about the study. "
                 "It grants no eligibility: a comparable window is created and "
                 "locked on the Comparable windows tab.")
    else:
        roster_text = right.text_area(
            "Participant roster (one name per line)",
            help="The human structural producer needs the roster. Participants are "
                 "never inferred by position.")

    policy_label = st.radio(
        "If the identifier already exists",
        ["Reject the import", "Keep both — import as a new version"],
        help="Nothing is overwritten by default. Replacing invalidates the Level 2 "
             "results and the assignments that referenced the old file, so it is a "
             "separate, explicit action.")
    policy = (import_service.CollisionPolicy.REJECT if policy_label.startswith("Rej")
              else import_service.CollisionPolicy.NEW_VERSION)

    if st.button("Import and normalise", type="primary",
                 disabled=uploaded is None):
        roster = [n.strip() for n in roster_text.splitlines() if n.strip()]
        outcome = import_service.import_transcript(
            project, filename=uploaded.name, content=uploaded.getvalue(),
            transcript_type=transcript_type,
            roster_names=roster or None,
            window_declaration=window_declaration,
            on_collision=policy)
        state["last_transcript_id"] = outcome.transcript_id
        st.rerun()

    last = state.get("last_transcript_id")
    if last:
        try:
            stored_report = import_service.load_validation_report(project, last)
        except import_service.ImportError_:
            stored_report = None
        if stored_report:
            _validation(last, stored_report)

    if stored:
        _replace(state, project, [t["transcript_id"] for t in stored])


def _replace(state, project, ids) -> None:
    """
    REPLACE, exposed but fenced.

    The preview names every artefact that will be archived or invalidated, and the
    confirmation is the transcript id typed by hand - so a replacement cannot happen
    by clicking the wrong row. Nothing is deleted.
    """
    with st.expander("Replace a transcript (advanced)"):
        st.warning("Replacing keeps the identifier and changes the bytes underneath "
                   "it. Everything derived from the old bytes is archived or goes "
                   "stale. Nothing is deleted.")
        target = st.selectbox("Transcript to replace", ids, key="replace_target")
        preview = import_service.replacement_preview(project, target)
        ui.detail_rows({
            "canonical archived": preview["canonical_archived"],
            "validation archived": preview["validation_archived"],
            "Level 2 results archived": preview["level2_results_archived"] or "none",
            "windows invalidated": preview["windows_invalidated"] or "none",
            "assignments becoming stale":
                [a["transcript_id"] for a in preview["assignments_becoming_stale"]]
                or "none",
        })
        st.caption(preview["note"])

        uploaded = st.file_uploader("Replacement JSON", type=["json"],
                                    key="replace_file")
        typed = st.text_input(f"Type `{target}` to confirm", key="replace_confirm")
        declared = st.radio("The replacement is", ["human", "synthetic"],
                            horizontal=True, key="replace_type")
        window_declaration = ("comparable_window" if declared == "synthetic"
                              else None)
        ready = uploaded is not None and typed.strip() == target
        if st.button("Replace and invalidate derived artefacts", disabled=not ready):
            outcome = import_service.import_transcript(
                project, filename=uploaded.name, content=uploaded.getvalue(),
                transcript_type=declared, transcript_id=target,
                window_declaration=window_declaration,
                on_collision=(import_service.CollisionPolicy
                              .REPLACE_INVALIDATE_DERIVED))
            audit.record(project.path, audit.REPLACE,
                         project_id=project.project_id, subject=target,
                         detail={"confirmed_by_typing_id": True,
                                 "windows_invalidated":
                                     preview["windows_invalidated"],
                                 "results_archived":
                                     preview["level2_results_archived"]})
            state["last_transcript_id"] = outcome.transcript_id
            st.rerun()


def _validation(transcript_id: str, envelope: dict) -> None:
    report = envelope["validation_report"]
    st.divider()
    st.subheader(f"Validation report — {transcript_id}")
    st.caption(f"canonical `{envelope['canonical_sha256'][:16]}…` · source "
               f"`{envelope['source_sha256'][:16]}…` · normaliser "
               f"{envelope['normaliser_version']}")

    columns = st.columns(5)
    columns[0].metric("Schema", report.get("schema_detected") or "—")
    columns[1].metric("Interventions", report.get("n_entries", 0))
    columns[2].metric("Empty", report.get("empty_entries", {}).get("found", 0))
    columns[3].metric("Unresolved", report.get("n_unresolved_turns", 0))
    columns[4].metric("Duplicate ids",
                      len(report.get("turn_ids", {}).get(
                          "duplicate_original_turn_ids", [])))

    problems = [import_service.ImportProblem(**p)
                for p in report.get("problems", [])]
    if problems:
        ui.problem_block(problems)
    elif report.get("fully_resolved"):
        st.success("Every intervention resolved. Level 2 can run.")

    empty = report.get("empty_entries", {})
    if empty.get("found"):
        st.warning(
            f"**{empty['found']} empty intervention(s)** are retained in the "
            f"canonical form and will be excluded by the producer.\n\n"
            f"*Rule:* {empty['rule']}")

    turn_ids = report.get("turn_ids", {})
    if turn_ids.get("duplicate_original_turn_ids"):
        st.warning(f"Duplicate original turn ids: "
                   f"{turn_ids['duplicate_original_turn_ids']} — kept as "
                   f"provenance, never renumbered.")

    unresolved = report.get("unresolved_turns") or []
    if unresolved:
        st.markdown("**Interventions that did not resolve**")
        ui.table(unresolved, [("turn_id", "Turn"),
                              ("original_turn_id", "Original id"),
                              ("original_index", "Index"),
                              ("speaker_id", "Speaker id"),
                              ("unresolved_fields", "Unresolved")], height=220)


# ---------------------------------------------------------------- study design
def _design(state, project) -> None:
    existing = design_service.load_design(project)
    if existing:
        st.success(f"Design **{existing.design_id}** — "
                   f"{len(existing.focus_groups)} focus groups, "
                   f"{len(existing.synthetic_conditions)} synthetic condition(s)")
        ui.table([c.to_dict() for c in existing.conditions],
                 [("condition_id", "Condition"), ("label", "Label"),
                  ("side", "Side"), ("expected_replicates", "Expected runs")])
        st.caption(f"Focus groups: {', '.join(existing.focus_group_ids)} · "
                   f"human reference {existing.human_reference_policy} · "
                   f"matching {existing.matching_policy}")

    st.markdown("**Define the design**")
    st.caption("Your study is not assumed to be 5 focus groups by 3 replicates. "
               "Nothing is read from a file name.")
    with st.form("study_design"):
        left, right = st.columns(2)
        n_focus_groups = left.number_input("Focus groups", 1, 50, value=3)
        replicates = right.number_input("Synthetic runs per focus group", 1, 50,
                                        value=2)
        conditions_text = left.text_input(
            "Synthetic conditions (comma separated)", value="condition-a")
        with_human = right.checkbox("This study has a human reference set",
                                    value=True)
        submitted = st.form_submit_button("Save design")

    if submitted:
        names = [c.strip() for c in conditions_text.split(",") if c.strip()]
        if not names:
            st.warning("Declare at least one synthetic condition.")
            return
        design = D.simple_design(
            design_id="default", project_id=project.project_id,
            study_name=project.name, n_focus_groups=int(n_focus_groups),
            synthetic_conditions=names, replicates=int(replicates),
            with_human=with_human, created_utc=_now())
        try:
            design_service.save_design(project, design)
        except design_service.DesignServiceError as exc:
            st.error(f"**Design not saved**\n\n{exc}")
        else:
            st.rerun()


# ------------------------------------------------------------------ assignment
def _assignment(state, project) -> None:
    design = design_service.load_design(project)
    if design is None:
        st.info("Save a study design first.")
        return

    stored = import_service.stored_transcripts(project)
    if not stored:
        st.info("Import a transcript first.")
        return

    eligibility = design_service.eligibility_map(project)
    results = structural_service.restore_results(project)
    by_input = {r.analysis_input_id: r for r in results.values()}
    assignments = {a.transcript_id: a
                   for a in design_service.load_assignments(project)}

    rows = []
    for t in stored:
        a = assignments.get(t["transcript_id"])
        info = eligibility.get(t["transcript_id"], {})
        result = by_input.get(info.get("analysis_input_id"))
        rows.append({
            "transcript_id": t["transcript_id"],
            "transcript_type": t["transcript_type"],
            "canonical_sha256": (t["canonical_sha256"] or "")[:12] + "…",
            "window_status": info.get("window_status", "—"),
            "condition_id": a.condition_id if a else "—",
            "focus_group_id": a.focus_group_id if a else "—",
            "replicate_index": a.replicate_index if a else "—",
            "role": a.role if a else "—",
            "level2": (FRESHNESS_LABELS.get(result.freshness, result.freshness)
                       if result else "Not computed"),
            "eligible": "yes" if info.get("comparison_eligible") else "no",
        })
    ui.table(rows, [("transcript_id", "Transcript"),
                    ("transcript_type", "Type"),
                    ("canonical_sha256", "Canonical hash"),
                    ("window_status", "Window"),
                    ("condition_id", "Condition"),
                    ("focus_group_id", "Focus group"),
                    ("replicate_index", "Replicate"), ("role", "Role"),
                    ("level2", "Level 2"), ("eligible", "Comparable")])
    st.caption("A transcript's TYPE decides its role: a human transcript can only "
               "be a human reference, a synthetic one only a synthetic run.")

    st.markdown("**Assign a transcript**")
    ids = [t["transcript_id"] for t in stored]
    chosen = st.selectbox("Transcript", ids, key="assign_transcript")
    record = next(t for t in stored if t["transcript_id"] == chosen)

    columns = st.columns(4)
    role = columns[0].selectbox(
        "Role", [D.Role.SYNTHETIC_RUN.value, D.Role.HUMAN_REFERENCE.value],
        index=1 if record["transcript_type"] == "human" else 0)
    condition_id = columns[1].selectbox("Condition", design.condition_ids)
    focus_group_id = columns[2].selectbox("Focus group", design.focus_group_ids)
    replicate = None
    if role == D.Role.SYNTHETIC_RUN.value:
        try:
            maximum = design.condition(condition_id).expected_replicates
        except D.DesignError:
            maximum = 1
        replicate = columns[3].number_input("Replicate index", 1, max(maximum, 1),
                                            value=1)

    left, right = st.columns(2)
    if left.button("Assign", type="primary"):
        try:
            design_service.assign(
                project, transcript_id=chosen, condition_id=condition_id,
                focus_group_id=focus_group_id, role=role,
                replicate_index=int(replicate) if replicate else None)
        except design_service.DesignServiceError as exc:
            st.error(f"**Not assigned**\n\n{exc}")
        else:
            st.rerun()
    if right.button("Remove assignment"):
        design_service.unassign(project, chosen)
        st.rerun()

    st.markdown("**Or import a manifest**")
    st.caption("CSV with columns: "
               f"{', '.join(design_service.MANIFEST_COLUMNS)}. Every value is read "
               "from the manifest; nothing is derived from a file name.")
    manifest = st.file_uploader("Manifest CSV", type=["csv"], key="manifest")
    if st.button("Apply manifest", disabled=manifest is None):
        _, problems = design_service.import_manifest(
            project, manifest.getvalue().decode("utf-8", errors="replace"))
        for problem in problems:
            st.error(problem)
        if not problems:
            st.rerun()

    st.divider()
    st.markdown("**Compute Level 2**")
    to_compute = st.multiselect("Transcripts", ids, default=ids)
    st.caption("Level 2 runs over the transcript's ACTIVE WINDOW when it has one, "
               "and over the whole session otherwise. A whole-session result is "
               "descriptive and never enters a comparison.")
    if st.button("Run Level 2 on the selected transcripts"):
        for transcript_id in to_compute:
            try:
                design_service.compute_for_assignment(project, transcript_id)
            except Exception as exc:               # noqa: BLE001 - shown, not raised
                st.error(f"**{transcript_id}**: {exc}")
        st.rerun()

    stale = [r for r in results.values()
             if r.freshness == structural_service.STALE]
    if stale:
        ui.problem_block([structural_service.stale_problem(r) for r in stale])


# -------------------------------------------------------------------- coverage
def _coverage(state, project) -> None:
    design = design_service.load_design(project)
    if design is None:
        st.info("Save a study design first.")
        return

    report = design_service.coverage(project)
    readiness = design_service.readiness(project)

    columns = st.columns(3)
    columns[0].metric("Design status", report.status)
    columns[1].metric("Route A", "Ready" if readiness["route_a"] else "Not ready")
    columns[2].metric("Route B", "Ready" if readiness["route_b"] else "Not ready")

    st.markdown("**Focus group × condition**")
    matrix = design_service.coverage_matrix(report, design)
    columns_spec = [("focus_group_id", "Focus group")]
    columns_spec += [(c.condition_id, c.label) for c in design.synthetic_conditions]
    columns_spec.append(("human_reference", "Human reference"))
    ui.table(matrix, columns_spec)
    st.caption("**eligible/expected** — a cell counts a run only when its transcript "
               "is present, its window is locked, its Level 2 result is current and "
               "the input is comparable. No missing transcript is imputed.")
    st.caption("States: missing transcript · missing window · under review · "
               "locked, not computed · descriptive only · eligible · stale")

    with st.expander("Position detail"):
        positions = [dict(p.to_dict(), condition_id=cell.condition_id,
                          focus_group_id=cell.focus_group_id)
                     for cell in report.cells for p in cell.positions]
        positions += [dict(p.to_dict(), condition_id="human",
                           focus_group_id="—") for p in report.human_positions]
        if positions:
            ui.table(positions, [("transcript_id", "Transcript"),
                                 ("condition_id", "Condition"),
                                 ("focus_group_id", "Focus group"),
                                 ("replicate_index", "Replicate"),
                                 ("source_present", "Source"),
                                 ("window_present", "Window"),
                                 ("window_locked", "Locked"),
                                 ("level2_fresh", "Level 2"),
                                 ("comparison_eligible", "Eligible"),
                                 ("display", "State")], height=320)

    if report.problems:
        st.error("**Design problems**\n\n"
                 + "\n".join(f"- {p}" for p in report.problems))
    if report.missing_assigned_transcript_ids:
        st.error("**Assigned but no longer stored**\n\n"
                 f"{report.missing_assigned_transcript_ids} — the position is empty, "
                 f"not merely questionable. Re-import the transcript or remove the "
                 f"assignment.")
    if report.stale_transcript_ids:
        st.warning(f"Stale assignments (the transcript changed after it was "
                   f"assigned): {report.stale_transcript_ids}")
    if report.missing_human_focus_groups:
        st.warning("Focus groups with no human reference: "
                   f"{report.missing_human_focus_groups}")
    if report.duplicate_human_focus_groups:
        st.warning("Focus groups with more than one human reference: "
                   f"{report.duplicate_human_focus_groups} — no defensible referent, "
                   "so the human column is left Undefined.")
    if report.unassigned_transcript_ids:
        st.info(f"Imported but not assigned: {report.unassigned_transcript_ids}")
    for reason in readiness["reasons"]:
        st.caption(f"— {reason}")

    st.caption(f"**Route B**: {report.route_b_reason}")


# ------------------------------------------------------------------ comparison
def _comparison(state, project) -> None:
    design = design_service.load_design(project)
    if design is None:
        st.info("Save a study design first.")
        return

    readiness = design_service.readiness(project)
    st.caption(f"Design status **{readiness['status']}**")
    if not readiness["route_a"]:
        st.warning("**Aggregation not available yet**\n\n"
                   + "\n".join(f"- {r}" for r in readiness["reasons"]))
    else:
        payload = design_service.aggregate(project)
        route = st.radio("Route", ["A — focus group × condition",
                                   "B — study replicate"], horizontal=True)
        if route.startswith("A"):
            rows = design_service.route_a_rows(payload)
            ui.table(rows, [("metric", "Metric"), ("condition_id", "Condition"),
                            ("focus_group_id", "Focus group"),
                            ("mean_display", "Mean"),
                            ("median_display", "Median"), ("sd_display", "SD"),
                            ("range_display", "Range"),
                            ("human_display", "Human"),
                            ("n_valid", "n"), ("n_expected", "of"),
                            ("coverage_status", "Coverage")], height=400)
        elif payload["route_b_available"]:
            rows = design_service.route_b_rows(payload)
            ui.table(rows, [("metric", "Metric"), ("condition_id", "Condition"),
                            ("replicate_index", "Replicate"),
                            ("mean_display", "Mean"), ("sd_display", "SD"),
                            ("range_display", "Range"),
                            ("n_valid", "n"), ("n_expected", "of"),
                            ("coverage_status", "Coverage")], height=400)
            st.caption("Replicate k groups the run indexed k in each focus group. "
                       "The index labels a position in the design; it does not imply "
                       "a shared seed between focus groups.")
        else:
            st.warning(f"**Route B is not available**\n\n"
                       f"{payload['route_b_reason']}")

        if payload.get("excluded"):
            st.warning("**Excluded from these figures**\n\n" + "\n".join(
                f"- `{e['transcript_id']}` — {e['reason']}"
                for e in payload["excluded"]))
        if payload["excluded_stale"]:
            st.warning(f"Stale results, excluded: {payload['excluded_stale']}")
        with st.expander("Analytical inputs used"):
            ui.table([{"transcript_id": k, "analysis_input_id": v}
                      for k, v in payload["analysis_inputs_used"].items()],
                     [("transcript_id", "Transcript"),
                      ("analysis_input_id", "Analytical input")])
            st.caption(payload["namespace_rule"])
        st.caption("Ratios are aggregated as the mean of the run-level ratios; "
                   "numerators and denominators are never summed across sessions. "
                   "No inferential test is performed.")

    st.divider()
    _single_session(state, project)


def _single_session(state, project) -> None:
    st.subheader("Single-session diagnostic")
    st.caption("One named human transcript against one named synthetic transcript. "
               "Separate from the aggregate above, and not a result for the corpus.")

    stored = import_service.stored_transcripts(project)
    human = [t["transcript_id"] for t in stored if t["transcript_type"] == "human"]
    synthetic = [t["transcript_id"] for t in stored
                 if t["transcript_type"] == "synthetic"]
    if not (human and synthetic):
        st.info("Import at least one human and one synthetic transcript.")
        return

    left, right = st.columns(2)
    human_id = left.selectbox("Human transcript", human, key="diag_human")
    synthetic_id = right.selectbox("Synthetic transcript", synthetic,
                                   key="diag_synthetic")

    declaration = st.text_area(
        "Declare the correspondence between your human and synthetic sets",
        key="declaration",
        placeholder="e.g. both sets used discussion guide v3 with the same five "
                    "recruitment strata.")
    if st.button("Save study context"):
        context = build_context(
            context_id="default", study_name=project.name,
            source_type=SourceType.USER_PROVIDED.value,
            project_id=project.project_id, human_set_id=human_id,
            synthetic_set_ids=synthetic, declaration_by_user=declaration.strip()
            or None)
        save_context(context, project.path)
        st.rerun()

    try:
        context = load_context("default", project.path)
    except Exception:                              # noqa: BLE001 - first visit
        st.info("No study context saved yet.")
        return

    label = theme.COMPARABILITY_LABELS.get(context.comparability_status,
                                           context.comparability_status)
    st.markdown(f"**Comparability:** {label}")
    for reason in context.comparability_reasons:
        st.markdown(f"- {reason}")

    results = structural_service.restore_results(project)
    human_result = results.get(human_id)
    synthetic_result = results.get(synthetic_id)
    if not (human_result and synthetic_result):
        st.info("Compute Level 2 for both transcripts first.")
        return
    for result in (human_result, synthetic_result):
        if result.freshness != structural_service.FRESH:
            ui.problem_block([structural_service.stale_problem(result)])
            return

    comparison = structural_service.compare_single_session(
        context, human_transcript_id=human_id,
        synthetic_transcript_id=synthetic_id,
        human_rows=human_result.rows, synthetic_rows=synthetic_result.rows)
    if not comparison.allowed:
        ui.problem_block(
            [structural_service.comparison_unavailable_problem(context)])
        return

    st.markdown(f"Comparing **{comparison.human_transcript_id}** with "
                f"**{comparison.synthetic_transcript_id}**")
    ui.table(comparison.rows, [("metric", "Metric"), ("human_display", "Human"),
                               ("human_denominator", "Human n"),
                               ("synthetic_display", "Synthetic"),
                               ("synthetic_denominator", "Synthetic n"),
                               ("difference_display", "Difference")])
    for caveat in comparison.caveats:
        st.caption(f"— {caveat}")


# ---------------------------------------------------------------------- export
def _export(state, project) -> None:
    design = design_service.load_design(project)
    stored = import_service.stored_transcripts(project)
    results = structural_service.restore_results(project)

    st.subheader("Study package")
    if design is None:
        st.info("Save a study design first.")
    else:
        readiness = design_service.readiness(project)
        payload = (design_service.aggregate(project) if readiness["route_a"]
                   else {"route_a": [], "route_b": [], "route_b_available": False,
                         "route_b_reason": readiness.get("route_b_reason", ""),
                         "excluded_stale": readiness["stale_transcripts"]})
        report = design_service.coverage(project)
        files = export_service.study_package(
            project_id=project.project_id, design=design.to_dict(),
            assignments=[a.to_dict()
                         for a in design_service.load_assignments(project)],
            coverage=report.to_dict(), aggregation=payload,
            run_results={t: r.rows for t, r in results.items()},
            transcript_index={t["transcript_id"]: t for t in stored},
            freshness={t: r.freshness for t, r in results.items()},
            audit_summary=audit.summarise_log(project.path),
            generated_utc=_now())
        ui.download_files(files, key_prefix="study")
        st.caption("Every row carries the project, design, transcript, condition, "
                   "focus group, replicate, denominators, coverage status and both "
                   "hashes.")

    st.divider()
    st.subheader("Single transcript")
    if not stored:
        st.caption("Nothing to export yet.")
        return
    ids = [t["transcript_id"] for t in stored]
    chosen = st.selectbox("Transcript", ids, key="export_pick")
    result = results.get(chosen)
    if not result:
        st.caption("Run Level 2 for this transcript first.")
        return
    if result.freshness != structural_service.FRESH:
        ui.problem_block([structural_service.stale_problem(result)])
        return

    try:
        files = export_service.project_export(
            transcript_payload=import_service.load_canonical(project, chosen),
            validation_report={},
            validation_payload=import_service.load_validation_report(project,
                                                                     chosen),
            structural_payload=structural_service.load_structural(project, chosen),
            structural_rows=result.rows, generated_utc=_now())
    except export_service.TraceabilityError as exc:
        st.error(f"**Export blocked — traceability**\n\n{exc}\n\n"
                 f"*What to do:* recompute Level 2 for this transcript so every part "
                 f"of the package describes the same bytes.")
        return
    except import_service.ImportError_ as exc:
        st.error(f"**Export blocked**\n\n{exc}")
        return

    ui.download_files(files, key_prefix="export")
    st.caption("The validation report is read by transcript id, not from the last "
               "import. The timestamp is on the envelope only.")

    with st.expander("Audit log"):
        summary = audit.summarise_log(project.path)
        st.markdown(f"{summary['n_events']} events · {summary['by_event']}")
        entries = audit.read_log(project.path)[-25:]
        ui.table(entries, [("utc", "When"), ("event", "Event"),
                           ("subject", "Subject")])
        st.caption("Append-only. Identifiers, hashes and counts; never transcript "
                   "content.")
