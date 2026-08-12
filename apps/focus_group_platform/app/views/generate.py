"""
Generate focus groups.

Seven steps, kept apart from New evaluation on purpose: generating a corpus and
evaluating one are different activities with different risks, and a launch button on
an evaluation screen is a launch button somebody will press by accident.

Everything here is state on disk. Closing the browser does not stop a run, and
reopening finds the jobs again.
"""
from __future__ import annotations

import json

import streamlit as st

from platform_core.config import DataDirError, resolve_data_dir
from platform_core.generation import (bundle as GB, contracts as GC,
                                      credentials as GCRED,
                                      effective_config as GE, importer as GI,
                                      launcher as GL, monitor as GM,
                                      planner as GP, preflight as GPF,
                                      pricing_ledger as GPL,
                                      profiles_source as PS, queue as GQ,
                                      queue_supervisor as GS)
from platform_core.services import audit, design_service, import_service

from .. import ui

STATUS_TONE = {
    GC.JobStatus.RUNNING.value: "running",
    GC.JobStatus.COMPLETED.value: "done",
    GC.JobStatus.FAILED.value: "failed",
    GC.JobStatus.CANCELLED.value: "cancelled",
    GC.JobStatus.ORPHANED.value: "orphaned",
    GC.JobStatus.REQUIRES_RECOVERY.value: "needs a decision",
    GC.JobStatus.BLOCKED_INPUT_CHANGED.value: "blocked",
}


def render(state) -> None:
    st.title("Generate focus groups")
    st.caption("Sessions run as separate processes through the project's public "
               "CLI. The interface never calls a model itself.")

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

    st.caption(f"Project **{project.name}**")
    tabs = st.tabs(["1 · Study", "2 · Profiles", "3 · Discussion guide",
                    "4 · Run plan", "5 · Dry-run", "6 · Launch and monitor",
                    "7 · Import outputs"])
    with tabs[0]:
        _study(state, project)
    with tabs[1]:
        _profiles(state, project)
    with tabs[2]:
        _guide(state, project)
    with tabs[3]:
        _plan(state, project)
    with tabs[4]:
        _dry_run(state, project)
    with tabs[5]:
        _launch(state, project)
    with tabs[6]:
        _import(state, project)


# ----------------------------------------------------------------------- study
def _study(state, project) -> None:
    existing = GP.load_study(project)
    if existing:
        st.success(f"Study **{existing.generation_study_id}** — "
                   f"{existing.n_sessions} session(s)")

    with st.form("generation_study"):
        left, right = st.columns(2)
        study_id = left.text_input("Study id", value=getattr(
            existing, "generation_study_id", "my_study"))
        topic = right.text_input("Topic domain", value=getattr(
            existing, "topic_domain", ""))
        objective = st.text_area("Research objective", value=getattr(
            existing, "research_objective", ""), height=90)
        identity = st.text_area("Participant collective identity", value=getattr(
            existing, "participant_collective_identity", ""), height=70)
        brief = st.text_area("Moderator knowledge brief", value=getattr(
            existing, "moderator_knowledge_brief", ""), height=90)

        left, right = st.columns(2)
        conditions = left.text_input("Synthetic conditions (comma separated)",
                                     value=", ".join(getattr(
                                         existing, "synthetic_conditions",
                                         ["condition-a"])))
        focus_groups = right.text_input("Focus groups (comma separated)",
                                        value=", ".join(getattr(
                                            existing, "focus_groups", ["fg1"])))
        left, right, third = st.columns(3)
        replicates = left.number_input("Runs per focus group", 1, 20,
                                       value=getattr(existing, "replicates", 1))
        max_turns = right.number_input("Max turns (safety cap)", 5, 300,
                                       value=getattr(existing, "max_turns", 90))
        concurrency = third.number_input(
            "Concurrency", 1, GC.MAX_CONCURRENCY,
            value=getattr(existing, "concurrency_limit", GC.DEFAULT_CONCURRENCY),
            help="One at a time by default, so a mistake costs one session.")
        left, right = st.columns(2)
        mode = left.selectbox("Participation mode", list(GC.CLI_MODES),
                              index=list(GC.CLI_MODES).index(
                                  getattr(existing, "participation_mode",
                                          "emergent")))
        moderator_model = right.text_input(
            "Moderator model", value=getattr(existing, "moderator_model",
                                             "claude-sonnet-4-6"))
        submitted = st.form_submit_button("Save study")

    if submitted:
        study = GC.GenerationStudy(
            generation_study_id=study_id.strip(), project_id=project.project_id,
            research_objective=objective.strip(), topic_domain=topic.strip(),
            participant_collective_identity=identity.strip(),
            moderator_knowledge_brief=brief.strip(),
            synthetic_conditions=[c.strip() for c in conditions.split(",")
                                  if c.strip()],
            focus_groups=[f.strip() for f in focus_groups.split(",") if f.strip()],
            replicates=int(replicates), participation_mode=mode,
            moderator_model=moderator_model.strip(), max_turns=int(max_turns),
            concurrency_limit=int(concurrency))
        GP.save_study(project, study)
        st.rerun()

    st.caption("The participant model is not set here: it comes from each agent "
               "payload's `simulation_config.model`, which is where the "
               "architecture reads it.")


# -------------------------------------------------------------------- profiles
def _profiles(state, project) -> None:
    st.markdown("**Uploaded profiles**")
    uploaded = st.file_uploader("Agent payload JSON", type=["json"],
                                accept_multiple_files=True)
    if uploaded:
        directory = project.subdir("uploads") / "agents"
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for item in uploaded:
            path = directory / item.name
            path.write_bytes(item.getvalue())
            paths.append(path)
        state["generation_profile_paths"] = [str(p) for p in paths]

    paths = state.get("generation_profile_paths") or []
    if paths:
        profile_set = PS.uploaded_profile_set(paths)
        rows = [dict(r.to_dict(),
                     recognised=", ".join(r.recognised_fields),
                     unrecognised=", ".join(r.unrecognised_fields) or "—",
                     problems="; ".join(r.problems) or "—")
                for r in profile_set.records]
        ui.table(rows, [("agent_id", "Agent"), ("recognised", "Recognised fields"),
                        ("unrecognised", "Not recognised"),
                        ("source_sha256", "Hash"), ("problems", "Problems")])
        if profile_set.ok:
            st.success(f"{len(profile_set.records)} profile(s) validated. Payloads "
                       f"are passed to the architecture unmodified.")
        else:
            st.error("**Profiles have problems**\n\n"
                     + "\n".join(f"- {p}" for p in profile_set.problems))
    else:
        st.info("No profiles uploaded yet.")

    st.divider()
    st.markdown("**Twin2K**")
    status = PS.twin2k_status()
    if status["status"] == PS.NOT_AVAILABLE_LOCAL_INDEX:
        st.warning(f"**{status['status']}**\n\n{status['etl_note']}")
        st.caption(f"Searched: {status['searched']}")
    else:
        st.success(f"Local index found at `{status['index_path']}`.")
        st.caption("A panel sampling seed may be recorded: it selects WHICH "
                   "participants are drawn. It is not a generation seed and does "
                   "not make a run reproducible.")


# ----------------------------------------------------------------------- guide
def _guide(state, project) -> None:
    text = st.text_area("Discussion guide (YAML)",
                        value=state.get("generation_guide_yaml", ""), height=280,
                        placeholder="guide_id: my_guide\ntitle: My study\n"
                                    "sections:\n  - label: Warm up\n"
                                    "    phase: intro\n"
                                    "    scripted_question: To start...")
    if st.button("Compile and preview"):
        state["generation_guide_yaml"] = text
        st.rerun()

    if not state.get("generation_guide_yaml"):
        st.info("Paste the guide YAML and compile it.")
        return

    bundle = GP.compile_guide_text(state["generation_guide_yaml"])
    if bundle.problems:
        st.error("**The guide does not compile**\n\n"
                 + "\n".join(f"- {p}" for p in bundle.problems))
        st.caption("Guide errors block the plan: a malformed section is not "
                   "something to discover once the moderator is already talking.")
        return
    for warning in bundle.warnings:
        st.warning(warning)

    st.success(f"{len(bundle.compiled)} section(s) compiled.")
    ui.table(bundle.compiled, [("section_index", "#"), ("section_label", "Label"),
                               ("section_phase", "Phase"),
                               ("scripted_question", "Scripted question")])
    ui.detail_rows({"guide id": bundle.guide_id,
                    "YAML sha256": bundle.yaml_sha256,
                    "compiled sha256": bundle.compiled_sha256})


# --------------------------------------------------------------------- the plan
def _current(project, state):
    study = GP.load_study(project)
    paths = state.get("generation_profile_paths") or []
    profile_set = PS.uploaded_profile_set(paths) if paths else None
    yaml_text = state.get("generation_guide_yaml")
    guide = GP.compile_guide_text(yaml_text) if yaml_text else None
    return study, profile_set, guide


def _plan(state, project) -> None:
    study, profile_set, guide = _current(project, state)
    if not (study and profile_set and guide):
        st.info("Complete the study, the profiles and the guide first.")
        return

    if st.button("Build run plan", type="primary"):
        plan = GP.build_plan(project, study, profile_set=profile_set, guide=guide)
        GP.save_plan(project, plan)
        st.rerun()

    plan = GP.load_plan(project)
    if plan is None:
        st.caption("No plan yet.")
        return

    st.markdown(f"**{plan.plan_id}** — {plan.total_sessions} session(s), "
                f"status {plan.validation_status}")
    ui.table([s.to_dict() for s in plan.sessions],
             [("session_id", "Session"), ("condition_id", "Condition"),
              ("focus_group_id", "Focus group"),
              ("replicate_index", "Run label index"),
              ("config_sha256", "Config hash"), ("status", "Status")])
    st.caption("`replicate_index` is a run label — the position of an independent "
               "realisation. It is not a seed and implies no reproducibility.")


# -------------------------------------------------------------------- dry run
def _dry_run(state, project) -> None:
    study, profile_set, guide = _current(project, state)
    plan = GP.load_plan(project)
    if not (study and profile_set and guide and plan):
        st.info("Build a run plan first.")
        return

    if st.button("Run the dry-run", type="primary"):
        report = GP.dry_run(project, study, plan, profile_set=profile_set,
                            guide=guide)
        plan = GP.confirmed_plan(plan, report)
        GP.save_plan(project, plan)
        state["generation_dry_run"] = report.to_dict()
        if report.ok:
            try:
                GP.write_configs(project, study, plan, profile_set=profile_set,
                                 guide=guide)
                GP.save_plan(project, plan)
            except Exception as exc:                            # noqa: BLE001
                st.error(f"**Configs not written**\n\n{exc}")
        st.rerun()

    report = state.get("generation_dry_run")
    if not report:
        st.caption("Not run yet. No external call is made by the dry-run.")
        return

    for check in report["checks"]:
        (st.success if check["ok"] else st.error)(
            f"**{check['check']}** — {check['detail']}")

    columns = st.columns(4)
    columns[0].metric("Sessions", report["total_sessions"])
    columns[1].metric("Concurrency", report["concurrency_limit"])
    columns[2].metric("Max turns", report["max_turns"])
    columns[3].metric("Launchable", "Yes" if report["ok"] else "No")
    st.caption(report["cost_estimate"])
    st.caption("Credentials are checked for PRESENCE only. Their value is never "
               "read, stored, displayed or copied into the project.")


# ------------------------------------------------------------ launch and monitor
def _readiness(project, plan, study) -> dict:
    """Bundle, hashes, credentials — the three things a launch depends on."""
    verification = GB.verify(
        project, plan.plan_id,
        architecture_code_manifest_hash=GE.architecture_code_manifest_hash())
    agent_models = {}
    manifest = GB.load_manifest(project, plan.plan_id)
    if manifest is not None:
        root = GB.bundle_dir(project, plan.plan_id)
        for dependency in manifest.dependencies:
            if dependency.kind != "profile":
                continue
            try:
                payload = json.loads((root / dependency.relative_path)
                                     .read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            agent_models[dependency.agent_id] = (
                (payload.get("simulation_config") or {}).get("model")
                or GE.ARCHITECTURE_DEFAULTS["participant_model"])
    credential_report = GCRED.check(moderator_model=study.moderator_model,
                                    agent_models=agent_models)
    return {"verification": verification, "credentials": credential_report,
            "agent_models": agent_models}


def _launch(state, project) -> None:
    study = GP.load_study(project)
    plan = GP.load_plan(project)
    if not (study and plan):
        st.info("Build and validate a plan first.")
        return

    jobs = {j.session_id: j for j in GL.observe_all(project)}
    readiness = _readiness(project, plan, study)
    verification = readiness["verification"]
    credential_report = readiness["credentials"]

    columns = st.columns(4)
    columns[0].metric("Bundle", "Immutable" if verification.immutable else "Draft")
    columns[1].metric("Hashes", "Verified" if verification.ok else "CHANGED")
    columns[2].metric("Credentials",
                      "Ready" if credential_report.ok else "Missing")
    queue_record = GQ.load_queue(project)
    columns[3].metric("Queue",
                      queue_record.queue_status if queue_record else "Not built")

    if not verification.ok:
        st.error("**Inputs changed since this plan was confirmed**\n\n"
                 + "\n".join(f"- {p['message']}" for p in verification.problems)
                 + "\n\n*What to do:* create a new plan, or restore the files and "
                   "reconfirm.")
    ui.table([r.to_dict() for r in credential_report.requirements],
             [("provider", "Provider"), ("required_variables", "Variables"),
              ("status", "Status"), ("source", "Source"), ("used_by", "Used by")])
    st.caption("Presence only. No credential value is read, stored, hashed or "
               "shown.")

    st.divider()
    if not plan.launchable:
        st.warning("**The plan has not passed its dry-run.** Launch is unavailable.")
    elif not verification.ok:
        st.warning("**Launch is blocked** until the inputs match the confirmed "
                   "plan.")
    else:
        _queue_controls(state, project, plan, study, verification,
                        credential_report)

    # ALWAYS RENDERED, even when launching is blocked. These controls used to live
    # inside `_queue_controls`, so a bundled input changing its hash mid-run removed
    # Pause and Stop from the screen while the supervisor carried on launching paid
    # sessions. The controls that stop work must not depend on the checks that permit
    # starting it.
    _supervisor_controls(project, GQ.load_queue(project))

    _job_table(state, project, plan, study, jobs)


def _queue_controls(state, project, plan, study, verification,
                    credential_report) -> None:
    record = GQ.load_queue(project)
    if record is None:
        with st.expander("Start queue", expanded=True):
            st.markdown(f"**{plan.total_sessions} session(s)** · conditions "
                        f"{study.synthetic_conditions} · focus groups "
                        f"{study.focus_groups} · {study.replicates} run(s) each")
            ui.detail_rows({
                "participants per session": len(plan.sessions[0].agent_ids)
                if plan.sessions else 0,
                "moderator model": study.moderator_model,
                "participant model": "from each agent payload",
                "max turns": study.max_turns,
                "concurrency": study.concurrency_limit,
                "config hash (first session)":
                    plan.config_hashes.get(plan.sessions[0].session_id, "")[:12]
                    + "…" if plan.sessions else "",
                "guide compiled hash": plan.guide_compiled_sha256[:12] + "…",
                "architecture hash":
                    plan.architecture_code_manifest_hash[:12] + "…",
                "cost estimate": GPL.estimate_note(
                    GPL.load_pricing_table(project)),
                "output directories": f"{len(plan.sessions)} under "
                                      f"output/session_logs/",
            })
            typed = st.text_input(f"Type `{plan.plan_id}` to confirm")
            if st.button("Start queue", type="primary",
                         disabled=typed.strip() != plan.plan_id
                         or not credential_report.ok):
                try:
                    GQ.build_queue(project, plan,
                                   concurrency_limit=study.concurrency_limit,
                                   max_turns=study.max_turns,
                                   mode=study.participation_mode)
                    GQ.start(project)
                except Exception as exc:                        # noqa: BLE001
                    st.error(f"**Queue not started**\n\n{exc}")
                st.rerun()
        return

    columns = st.columns(4)
    columns[0].metric("Queue", record.queue_status)
    columns[1].metric("Concurrency", record.concurrency_limit)
    detail = record.last_tick_detail or {}
    columns[2].metric("Active slots",
                      f"{detail.get('occupied_slots', 0)}/"
                      f"{record.concurrency_limit}")
    columns[3].metric("Pending", len(detail.get("pending", [])))

    actions = st.columns(3)
    if actions[0].button("Refresh status"):
        # An explicit read. Opening or reloading this page does NOT launch anything:
        # a scheduler that ran as a side effect of a page load would start paid work
        # because somebody pressed F5.
        st.rerun()
    if record.paused:
        if actions[1].button("Resume queue"):
            GQ.resume(project)
            st.rerun()
    elif actions[1].button("Pause new launches"):
        GQ.pause(project)
        st.rerun()
    # A MANUAL TICK IS A SECOND SCHEDULER. It runs `queue.tick()` inside this process
    # and takes no supervisor lock, so pressing it while a supervisor is alive gives
    # two schedulers reading the same free slot - each launches into it, and the
    # concurrency limit the researcher set is silently doubled. No race is needed;
    # one click during any tick interval is enough.
    supervisor_alive = False
    try:
        supervisor_alive = GS.observe(project).state in GS.ALIVE_STATES
    except Exception:                                           # noqa: BLE001
        supervisor_alive = False
    if actions[2].button("Scheduler tick (one step)", disabled=supervisor_alive):
        GQ.tick(project, verify=lambda p, j: GPF.verify_before_launch(
            p, j, plan=plan, occupied_slots=0,
            concurrency_limit=record.concurrency_limit))
        st.rerun()
    st.caption("Pausing stops NEW launches. Anything already running keeps running."
               + (" The manual tick is unavailable while the supervisor is running: "
                  "two schedulers would launch into the same free slot."
                  if supervisor_alive else ""))

    if detail.get("blocked"):
        st.error("**Blocked by the launch-time check**\n\n" + "\n".join(
            f"- `{b['job_id']}`: "
            + "; ".join(p.get("message", "") for p in (b.get("problems") or []))
            for b in detail["blocked"]))
    st.caption(f"Last tick: {record.last_scheduler_tick_utc or 'never'}")


SUPERVISOR_TONE = {
    GS.SupervisorState.RUNNING.value: "running",
    GS.SupervisorState.PAUSED.value: "paused",
    GS.SupervisorState.CRASHED.value: "failed",
    GS.SupervisorState.UNRESPONSIVE.value: "failed",
}


def _clock(utc: str) -> str:
    """
    HH:MM:SS from an ISO timestamp, in UTC, or an em dash.

    Everything else here is stamped UTC, so rendering the offset-local wall time of
    whatever string happened to be stored would have shown a heartbeat from a
    different clock without saying so.
    """
    if not utc:
        return "—"
    if not isinstance(utc, str):
        return "—"
    try:
        from datetime import UTC as _UTC, datetime
        parsed = datetime.fromisoformat(utc.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC).strftime("%H:%M:%S")


def _supervisor_controls(project, queue_record) -> None:
    """
    Start, pause, resume and stop the process that advances the queue.

    Without it a tick happens only when this page is reloaded, which is not a
    scheduler. It is started deliberately and never as a side effect of a page load.
    """
    with st.expander("Queue supervisor", expanded=False):
        try:
            supervisor = GS.observe(project)
        except Exception as exc:                                # noqa: BLE001
            st.error(f"**The supervisor state could not be read**\n\n{exc}")
            return

        columns = st.columns(4)
        columns[0].metric("Supervisor", supervisor.state)
        columns[1].metric("Ticks", supervisor.tick_count)
        columns[2].metric("Launched", supervisor.launched_total)
        columns[3].metric("Heartbeat (UTC)",
                          _clock(supervisor.last_heartbeat_utc))

        if supervisor.state == GS.SupervisorState.CRASHED.value:
            st.error("**The supervisor process is gone and did not record a stop.** "
                     "Sessions it launched are unaffected; nothing was retried. "
                     f"Last reason: {supervisor.stop_reason or 'none recorded'}")
        elif supervisor.state == GS.SupervisorState.UNRESPONSIVE.value:
            st.warning(
                "**The process is alive but its heartbeat is stale.** A stuck loop "
                "never reads a stop request, so **Stop supervisor** may do nothing. "
                "Use *Abandon* below to release the project, then end process "
                f"`{supervisor.pid}` yourself before starting another supervisor.")
            if st.button("Abandon this supervisor and release the project"):
                detail = GS.force_release(project)
                st.warning(
                    f"Released. Process `{detail['abandoned_pid']}` was **not "
                    f"killed** and may still be running — end it yourself before "
                    f"starting a new supervisor, or two schedulers could launch into "
                    f"the same slot.")
                st.rerun()
        elif supervisor.state == GS.SupervisorState.NOT_STARTED.value:
            st.info("No supervisor is running. The queue advances only when you "
                    "press **Scheduler tick**.")

        alive = supervisor.state in GS.ALIVE_STATES
        buttons = st.columns(4)
        interval = st.number_input("Tick interval (seconds)",
                                   min_value=float(GS.MIN_INTERVAL_SECONDS),
                                   max_value=600.0,
                                   value=float(GS.DEFAULT_INTERVAL_SECONDS),
                                   step=5.0, key="supervisor_interval")
        if buttons[0].button("Start supervisor", disabled=alive
                             or queue_record is None):
            try:
                GS.start(project, interval=float(interval))
            except Exception as exc:                            # noqa: BLE001
                st.error(f"**The supervisor was not started**\n\n{exc}")
            st.rerun()
        if buttons[1].button("Pause supervisor", disabled=not alive):
            GS.request_pause(project)
            st.rerun()
        if buttons[2].button("Resume supervisor", disabled=not alive):
            GS.request_resume(project)
            st.rerun()
        if buttons[3].button("Stop supervisor", disabled=not alive):
            GS.request_stop(project)
            st.rerun()

        st.caption("Stopping the supervisor stops the SCHEDULER. Sessions already "
                   "running are never killed by it, and no job is ever retried "
                   "automatically. The supervisor stops on its own after "
                   f"{GS.MAX_LIFETIME_SECONDS // 3600} hours.")
        if supervisor.last_error:
            st.caption(f"Last error: {supervisor.last_error}")


def _job_table(state, project, plan, study, jobs) -> None:
    st.divider()
    st.subheader("Jobs")
    if not jobs:
        st.caption("Nothing launched yet.")
        return

    table = GPL.load_pricing_table(project)
    agent_models = _readiness(project, plan, study)["agent_models"]
    rows = []
    usage_reports = {}
    for job in jobs.values():
        progress = GM.read_progress(job.expected_output_directory,
                                    session_id=job.session_id, status=job.status,
                                    stdout_path=job.launcher_stdout_path)
        usage = GPL.consolidate(
            job_id=job.job_id, session_id=job.session_id,
            output_directory=job.expected_output_directory,
            moderator_model=study.moderator_model, agent_models=agent_models,
            table=table)
        usage_reports[job.session_id] = usage
        sections = ("—" if job.guide_sections_total is None
                    else f"{job.guide_sections_completed}/"
                         f"{job.guide_sections_total}")
        run_seconds = job.run_duration_seconds
        rows.append({
            "session_id": job.session_id, "status": job.status,
            "completion_quality": job.completion_quality or "—",
            "completion_evidence": job.completion_evidence or "—",
            "sections": sections,
            "coherent": {True: "yes", False: "NO", None: "—"}[
                job.transcript_state_match],
            "last_turn": progress.last_turn, "phase": progress.section_phase,
            "run_seconds": ("—" if run_seconds is None else f"{run_seconds:.0f}"),
            # NOT ZERO. `UsageReport` counters default to 0 and stay 0 when the ledger
            # is absent or unreadable, so a job whose api_calls.jsonl did not survive
            # rendered as "0 calls" — indistinguishable from a job that made none. The
            # crashed smoke run made six billed calls and would have shown zero.
            "calls": usage.n_calls if usage.ledger_valid else "—",
            "input_tokens": usage.input_tokens if usage.ledger_valid else "—",
            "output_tokens": usage.output_tokens if usage.ledger_valid else "—",
            "cost": usage.cost_display, "cost_status": usage.cost_status,
            "last_event": progress.last_event,
        })
    ui.table(rows, [("session_id", "Session"), ("status", "Status"),
                    ("completion_quality", "Completion"),
                    ("completion_evidence", "Evidence"),
                    ("sections", "Sections"), ("coherent", "Coherent"),
                    ("last_turn", "Last turn"), ("phase", "Phase"),
                    ("run_seconds", "Run (s)"),
                    ("calls", "Calls"), ("input_tokens", "In"),
                    ("output_tokens", "Out"), ("cost", "Cost"),
                    ("cost_status", "Cost status"),
                    ("last_event", "Last event")])
    st.caption("Read-only. Prompts, credentials and environment variables are never "
               "shown. **Completion** comes from the session's own final state; "
               "**Evidence** says whether the process output agreed. Cost is "
               "Undefined unless a versioned rate table prices the observed usage; a "
               "token ceiling is never turned into a forecast.")

    # EVERY PROBLEM THE COST LAYER RECORDS, SHOWN. They were computed and rendered
    # nowhere, so a mislabelled currency, a corrupt token value or a failed call with
    # no token counts all reached the reader as a clean figure.
    cost_problems = [(session, problem)
                     for session, report in usage_reports.items()
                     for problem in report.problems]
    if cost_problems:
        st.warning("**What the cost figures do not cover**\n\n" + "\n".join(
            f"- `{session}`: {problem}" for session, problem in cost_problems))

    # STATUSES THAT NAME THEMSELVES BADLY. A researcher reading REQUIRES_RECOVERY
    # looks for a recover button; there isn't one, and there shouldn't be — the tool
    # cannot say whether the session finished, so only a person can decide. Saying so
    # where the status appears is the difference between a considered refusal and
    # something that looks broken.
    needs_reading = {
        GC.JobStatus.REQUIRES_RECOVERY.value: (
            "output exists on disk, but the durable record of how the session ended "
            "does not. Nothing was deleted. Open the output directory and decide "
            "yourself whether the run is usable — the platform will not guess."),
        GC.JobStatus.ORPHANED.value: (
            "the process is gone and left no record of how it ended. Its artefacts "
            "are kept and it is never relaunched automatically, because a repeat may "
            "cost money and duplicate what is already there."),
        GC.JobStatus.BLOCKED_INPUT_CHANGED.value: (
            "an input changed after the plan was confirmed, so this job was not "
            "launched. Create a new plan rather than editing this one."),
    }
    unexplained = [(j, needs_reading[j.status]) for j in jobs.values()
                   if j.status in needs_reading]
    if unexplained:
        st.info("**Waiting on you, not on the platform**\n\n" + "\n".join(
            f"- `{j.session_id}` is **{j.status}** — {why}"
            for j, why in unexplained))

    incoherent = [j for j in jobs.values() if j.transcript_state_match is False]
    if incoherent:
        st.error("**The transcript and the final state disagree**\n\n" + "\n".join(
            f"- `{j.session_id}` — {j.failure_reason}" for j in incoherent)
            + "\n\nNeither artefact is used. Which one is right is not something "
              "the platform can decide.")

    summary = GM.plan_duration_summary(list(jobs.values()), plan_id=plan.plan_id)
    if summary.n_jobs:
        with st.expander("Durations"):
            ui.table([s.to_dict() for s in summary.stages.values()],
                     [("stage", "Stage"), ("n_observations", "n"),
                      ("n_missing", "Missing"), ("mean_seconds", "Mean (s)"),
                      ("median_seconds", "Median (s)"), ("min_seconds", "Min"),
                      ("max_seconds", "Max"), ("status", "Status")])
            for note in summary.notes:
                st.caption(note)
    capped = [j for j in jobs.values()
              if j.completion_quality == "MAX_TURNS_REACHED"]
    if capped:
        st.warning("**Potentially incomplete sessions**\n\n" + "\n".join(
            f"- `{j.session_id}` hit the max-turns cap with the guide unfinished"
            for j in capped))

    running = [j for j in jobs.values()
               if j.status == GC.JobStatus.RUNNING.value]
    if running:
        with st.expander("Cancel a running session"):
            target = st.selectbox("Session", [j.session_id for j in running])
            typed = st.text_input(f"Type `{target}` to confirm cancellation",
                                  key="cancel_confirm")
            st.caption("Partial artefacts are kept, and cost already incurred is "
                       "not refunded.")
            if st.button("Cancel session", disabled=typed.strip() != target):
                job = next(j for j in running if j.session_id == target)
                try:
                    GL.cancel(project, job.job_id, confirm_session_id=target)
                except Exception as exc:                        # noqa: BLE001
                    st.error(f"**Not cancelled**\n\n{exc}")
                st.rerun()

    failed = [j for j in jobs.values()
              if j.status in (GC.JobStatus.FAILED.value,
                              GC.JobStatus.ORPHANED.value)]
    if failed:
        st.warning("**Not relaunched automatically**\n\n" + "\n".join(
            f"- `{j.session_id}` — {j.status}: {j.failure_reason}"
            for j in failed))


# ------------------------------------------------------------- import outputs
def _import(state, project) -> None:
    plan = GP.load_plan(project)
    study = GP.load_study(project)
    jobs = GL.observe_all(project)
    completed = [j for j in jobs if j.status == GC.JobStatus.COMPLETED.value]
    if not completed:
        st.info("No completed session to import yet.")
        return

    st.markdown("**Completed sessions**")
    ui.table([{"session_id": j.session_id, "job_id": j.job_id,
               "imported": j.imported_transcript_id or "—"} for j in completed],
             [("session_id", "Session"), ("job_id", "Job"),
              ("imported", "Imported as")])

    target = st.selectbox("Session to import",
                          [j.session_id for j in completed])
    policy_label = st.radio("If the transcript id already exists",
                            ["Reject", "Keep both — new version"],
                            key="gen_import_policy")
    policy = (import_service.CollisionPolicy.REJECT if policy_label == "Reject"
              else import_service.CollisionPolicy.NEW_VERSION)

    if st.button("Import output", type="primary"):
        job = next(j for j in completed if j.session_id == target)
        outcome = GI.import_session_output(project, job, plan=plan,
                                           on_collision=policy)
        state["generation_import"] = outcome.to_dict()
        st.rerun()

    outcome = state.get("generation_import")
    if not outcome:
        return
    if not outcome["ok"]:
        st.error("**Not imported**\n\n"
                 + "\n".join(f"- {p}" for p in outcome["problems"]))
        return

    st.success(f"Imported as **{outcome['transcript_id']}**")
    st.info(outcome["note"])
    st.caption(f"transcript sha256 `{outcome['transcript_sha256'][:16]}…`")

    proposal = outcome.get("proposed_assignment")
    if proposal:
        st.markdown("**Proposed assignment**")
        ui.detail_rows({k: v for k, v in proposal.items() if k != "note"})
        st.caption(proposal["note"])
        design = design_service.load_design(project)
        if design is None and plan and study:
            if st.button("Create a study design from this plan"):
                bundle = GI.design_from_plan(project, plan, study)
                design_service.save_design(project, bundle["design"])
                st.caption(bundle["human_reference"])
                st.rerun()
        elif st.button("Confirm this assignment"):
            try:
                GI.confirm_assignment(project, proposal)
            except Exception as exc:                            # noqa: BLE001
                st.error(f"**Not assigned**\n\n{exc}")
            else:
                st.rerun()

    st.caption("Next: create and lock a comparable window on the New evaluation "
               "page. Nothing generated here is comparable until that is done.")
