"""
Phase 3F: structured completion, autonomous supervision, cost honesty.

NO PROVIDER IS CALLED, NO SESSION IS RUN AND NO SUPERVISOR PROCESS IS SPAWNED. Every
launch goes through a fake worker, and the supervisor loop is driven in-process with
its sleep, its clock and its spawn injected.

The two real smoke runs under `output/session_logs/` are read and never written.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from platform_core import profiles as PROF
from platform_core.config import REPO_ROOT, resolve_data_dir
from platform_core.generation import (contracts as GC, launcher as GL,
                                      monitor as GM, planner as GP,
                                      pricing_ledger as GPL,
                                      profiles_source as PS, queue as GQ,
                                      queue_supervisor as GS,
                                      smoke_manifest as GSM, terminal as GT,
                                      worker as GW)
from platform_core.services import import_service as I

from test_phase3e_reliability import (ENV, FakeWorker, GUIDE_YAML,  # noqa: F401
                                       TRANSCRIPT, _confirmed, _study, data_dir,
                                       guide, profiles, project)

SMOKE_CRASHED = REPO_ROOT / "output" / "session_logs" / "smoke_smoke_fg1_r01"
SMOKE_COMPLETED = REPO_ROOT / "output" / "session_logs" / "smoke2_smoke_fg1_r01"

requires_smoke = pytest.mark.skipif(
    not SMOKE_COMPLETED.is_dir(),
    reason="the exploratory smoke runs are not present in this checkout")


def _state(*, session_id, turn_index, total_turns, sections_completed,
           sections_total, transcript):
    guide_sections = [
        {"section_index": i, "section_label": f"S{i}", "section_phase": "main_topic",
         "completed": i < sections_completed}
        for i in range(sections_total)]
    return {
        "schema_version": "fg_state_v1",
        "session_meta": {"id": session_id, "total_turns": total_turns,
                         "current_section_index": max(sections_completed - 1, 0)},
        "discussion_guide": guide_sections,
        "participants": {}, "moderator_log": [], "group_state": {},
        "transcript": transcript,
    }


def _write_run(directory: Path, *, session_id="s1", turn_index=9, total_turns=9,
               sections_completed=3, sections_total=3, transcript=None,
               state_transcript="same"):
    directory.mkdir(parents=True, exist_ok=True)
    entries = TRANSCRIPT if transcript is None else transcript
    (directory / "transcript.json").write_text(json.dumps(entries),
                                               encoding="utf-8")
    in_state = entries if state_transcript == "same" else state_transcript
    (directory / f"state_turn_{turn_index}.json").write_text(
        json.dumps(_state(session_id=session_id, turn_index=turn_index,
                          total_turns=total_turns,
                          sections_completed=sections_completed,
                          sections_total=sections_total, transcript=in_state)),
        encoding="utf-8")
    return directory


# ================================ 1 the structured state is the authority
def test_completion_is_read_from_the_final_state_without_any_stdout(tmp_path):
    """(1) A completed guide is recognised with no completion line in the output."""
    output = _write_run(tmp_path / "run")
    result = GT.inspect_output(output, "", session_id="s1")
    assert result["completion_quality"] == GT.CompletionQuality.GUIDE_COMPLETED.value
    assert result["completion_evidence"] == GT.CompletionEvidence.STRUCTURED_STATE.value
    assert result["structured_guide_completed"] is True
    assert result["stdout_completion_marker_found"] is False


def test_stdout_corroborates_it_rather_than_deciding_it(tmp_path):
    """(2) The same state, now with the marker, is CORROBORATED - not re-decided."""
    output = _write_run(tmp_path / "run")
    result = GT.inspect_output(
        output, "Guide completed naturally after 9 steps", session_id="s1")
    assert result["completion_quality"] == GT.CompletionQuality.GUIDE_COMPLETED.value
    assert (result["completion_evidence"]
            == GT.CompletionEvidence.STDOUT_CORROBORATED.value)


def test_stdout_claiming_completion_over_an_unfinished_state_conflicts(tmp_path):
    """(3) The old rule would have believed the line. It is now a conflict."""
    output = _write_run(tmp_path / "run", sections_completed=1, sections_total=3)
    result = GT.inspect_output(
        output, "Guide completed naturally after 9 steps", session_id="s1")
    assert (result["completion_evidence"]
            == GT.CompletionEvidence.CONFLICTING_EVIDENCE.value)
    assert result["completion_quality"] != GT.CompletionQuality.GUIDE_COMPLETED.value


def test_a_run_with_no_final_state_is_not_completed_on_stdout_alone(tmp_path):
    """(4) A completion line over no structured evidence proves nothing."""
    output = tmp_path / "run"
    output.mkdir()
    (output / "transcript.json").write_text(json.dumps(TRANSCRIPT), encoding="utf-8")
    result = GT.inspect_output(output, "Guide completed naturally after 9 steps",
                               session_id="s1")
    assert result["completion_quality"] != GT.CompletionQuality.GUIDE_COMPLETED.value
    assert any("state_turn" in p for p in result["final_state_problems"])


def test_a_final_state_from_another_session_is_a_problem(tmp_path):
    """(5) Evidence has to belong to the run it is used to judge."""
    output = _write_run(tmp_path / "run", session_id="somebody_else")
    result = GT.inspect_output(output, "", session_id="s1")
    assert any("belongs to session" in p for p in result["final_state_problems"])
    assert result["completion_quality"] != GT.CompletionQuality.GUIDE_COMPLETED.value


def test_a_legacy_record_is_labelled_and_not_recomputed(tmp_path):
    """(6) Records written before 3F keep their verdict, marked as stdout-only."""
    path = tmp_path / "terminal_record.json"
    path.write_text(json.dumps({
        "schema_version": "1.0.0", "job_id": "j", "session_id": "s1",
        "exit_code": 0, "termination_kind": GT.TerminationKind.NORMAL_EXIT.value,
        "transcript_exists": True, "transcript_parseable": True,
        "completion_quality": GT.CompletionQuality.GUIDE_COMPLETED.value,
    }), encoding="utf-8")
    record = GT.load_terminal_record(path)
    assert (record.completion_evidence
            == GT.CompletionEvidence.STDOUT_ONLY_LEGACY.value)
    assert record.completion_quality == GT.CompletionQuality.GUIDE_COMPLETED.value


# ============================================== 2 transcript coherence
def test_a_transcript_that_contradicts_the_state_is_not_usable(tmp_path):
    """(7) Two artefacts, two different discussions: neither is used."""
    shorter = TRANSCRIPT[:4]
    output = _write_run(tmp_path / "run", state_transcript=shorter)
    result = GT.inspect_output(output, "", session_id="s1")
    assert result["transcript_state_match"] is False
    assert "intervention" in result["transcript_state_mismatch_reason"] or \
           "transcript.json has" in result["transcript_state_mismatch_reason"]


def test_coherence_compares_content_not_bytes(tmp_path):
    """(8) Reordered keys and added fields are serialisation, not disagreement."""
    reserialised = [{"content": e["content"], "speaker_name": e["speaker_name"],
                     "speaker_id": e["speaker_id"], "turn": e["turn"],
                     "extra_field": "written by a later version"}
                    for e in TRANSCRIPT]
    output = _write_run(tmp_path / "run", state_transcript=reserialised)
    result = GT.inspect_output(output, "", session_id="s1")
    assert result["transcript_state_match"] is True


def test_an_incoherent_run_fails_the_job_with_a_named_reason(project, profiles,
                                                             guide):
    """(9) The gate reaches the job record, not just the inspection."""
    study, plan = _confirmed(project, profiles, guide)
    session = plan.sessions[0]
    job = GL.build_job(project, plan, session.session_id, max_turns=study.max_turns,
                       mode=study.participation_mode,
                       effective_config_sha256=plan.effective_config_hashes.get(
                           session.session_id, ""),
                       architecture_code_manifest_hash=(
                           plan.architecture_code_manifest_hash))
    record = GT.TerminalRecord(
        job_id=job.job_id, session_id=job.session_id, exit_code=0,
        termination_kind=GT.TerminationKind.NORMAL_EXIT.value,
        config_sha256=job.config_sha256, transcript_exists=True,
        transcript_parseable=True,
        completion_quality=GT.CompletionQuality.GUIDE_COMPLETED.value,
        completion_evidence=GT.CompletionEvidence.STRUCTURED_STATE.value,
        transcript_state_match=False,
        transcript_state_mismatch_reason="intervention 3 differs on ['content']")
    GL._apply_terminal_record(job, record)
    assert job.status == GC.JobStatus.FAILED.value
    assert "different discussions" in job.failure_reason


# =================================== 3 the worker mirrors the platform
@requires_smoke
@pytest.mark.parametrize("directory", [SMOKE_CRASHED, SMOKE_COMPLETED])
@pytest.mark.parametrize("stdout", ["", "Guide completed naturally after 9 steps",
                                    "SAFETY CAP HIT at 15 steps"])
def test_the_worker_and_the_platform_agree_on_the_real_runs(directory, stdout):
    """(10) One rule, two implementations, checked against real output."""
    session_id = directory.name
    from_worker = GW.inspect_output(directory, stdout, session_id=session_id,
                                    max_turns=15)
    from_platform = GT.inspect_output(directory, stdout, session_id=session_id,
                                      max_turns=15)
    assert from_worker == from_platform


@requires_smoke
def test_the_completed_smoke_run_is_recognised_from_its_state_alone():
    """(11) No stdout was kept for it, and it is still classifiable."""
    result = GT.inspect_output(SMOKE_COMPLETED, "",
                               session_id=SMOKE_COMPLETED.name)
    assert result["completion_quality"] == GT.CompletionQuality.GUIDE_COMPLETED.value
    assert result["completion_evidence"] == GT.CompletionEvidence.STRUCTURED_STATE.value
    assert result["guide_sections_completed"] == result["guide_sections_total"] == 2
    assert result["transcript_state_match"] is True


@requires_smoke
def test_the_crashed_smoke_run_is_not_reported_as_completed():
    """(12) It wrote a parseable transcript. It finished nothing."""
    result = GT.inspect_output(SMOKE_CRASHED, "", session_id=SMOKE_CRASHED.name)
    assert result["completion_quality"] != GT.CompletionQuality.GUIDE_COMPLETED.value
    assert result["guide_sections_completed"] == 0


# ============================================ 4 the supervisor process
def _fake_signature(cmdline):
    def resolve(pid):
        return (1000.0, cmdline) if pid else None
    return resolve


def test_the_supervisor_ticks_the_queue_until_every_job_is_terminal(project,
                                                                    profiles, guide):
    """(13) The demonstration: a queue that empties itself, no real process."""
    study, plan = _confirmed(project, profiles, guide,
                             focus_groups=["fg1", "fg2"], replicates=1)
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)
    worker = FakeWorker()

    slept = []
    record = GS.run_supervisor(project, interval=5.0, spawn=worker,
                               sleep=slept.append, max_ticks=12)

    assert record.state == GS.SupervisorState.STOPPED.value
    assert record.launched_total == plan.total_sessions
    assert "terminal state" in record.stop_reason
    jobs = GL.observe_all(project)
    assert {j.status for j in jobs} == {GC.JobStatus.COMPLETED.value}
    for job in jobs:
        import shutil
        shutil.rmtree(Path(job.expected_output_directory), ignore_errors=True)


def test_a_paused_supervisor_launches_nothing(project, profiles, guide):
    """(14) Pausing stops NEW launches and keeps the loop alive."""
    study, plan = _confirmed(project, profiles, guide)
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)
    GS.request_pause(project)
    worker = FakeWorker()

    record = GS.run_supervisor(project, interval=1.0, spawn=worker,
                               sleep=lambda _s: None, max_ticks=3)
    assert record.launched_total == 0
    assert worker.calls == []
    assert all(j.status == GC.JobStatus.PENDING.value
               for j in GL.observe_all(project))


def test_a_stop_request_ends_the_loop_without_touching_running_work(project,
                                                                    profiles, guide):
    """(15) Stopping the scheduler is not cancelling the sessions."""
    study, plan = _confirmed(project, profiles, guide)
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)
    GS.request_stop(project)
    record = GS.run_supervisor(project, interval=1.0, spawn=FakeWorker(),
                               sleep=lambda _s: None, max_ticks=5)
    assert record.tick_count == 0
    assert record.stop_reason == "a stop was requested"
    assert record.state == GS.SupervisorState.STOPPED.value


def test_two_supervisors_cannot_hold_the_same_project(project, profiles, guide):
    """(16) The lock, not the status check, is what decides it."""
    study, plan = _confirmed(project, profiles, guide)
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    live = _fake_signature("py -m platform_core.generation.queue_supervisor "
                           f"--project {project.name}")
    GS.acquire_lock(project, signature_of=live)
    holder = json.loads(GS.lock_path(project).read_text(encoding="utf-8"))
    holder["pid"] = holder["pid"] + 1          # someone else holds it, and is alive
    GS.lock_path(project).write_text(json.dumps(holder), encoding="utf-8")

    with pytest.raises(GS.LockHeld):
        GS.acquire_lock(project, signature_of=live)


def test_a_lock_held_by_a_dead_process_is_taken_over(project, profiles, guide):
    """(17) A machine that lost power must not make a project unschedulable."""
    study, plan = _confirmed(project, profiles, guide)
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GS.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.lock_path(project).write_text(json.dumps(
        {"pid": 999999, "process_start_time": 1.0, "project_name": project.name}),
        encoding="utf-8")

    payload = GS.acquire_lock(project, signature_of=lambda pid: None)
    assert payload["took_over_from"] == 999999


def test_a_supervisor_whose_process_vanished_is_reported_as_crashed(project):
    """(18) A record saying RUNNING is a claim, and the process table settles it."""
    GS.state_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.save_state(project, GS.SupervisorRecord(
        project_name=project.name, pid=999999, process_start_time=1.0,
        state=GS.SupervisorState.RUNNING.value, started_utc="2026-08-05T00:00:00Z",
        last_heartbeat_utc="2026-08-05T00:00:00Z"))
    observed = GS.observe(project, signature_of=lambda pid: None)
    assert observed.state == GS.SupervisorState.CRASHED.value


def test_a_stale_heartbeat_from_a_live_process_is_unresponsive(project):
    """(19) Alive is not the same as working."""
    old = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    GS.state_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.save_state(project, GS.SupervisorRecord(
        project_name=project.name, pid=4242, process_start_time=1000.0,
        state=GS.SupervisorState.RUNNING.value, interval_seconds=20.0,
        started_utc=old, last_heartbeat_utc=old))
    live = _fake_signature("py -m platform_core.generation.queue_supervisor "
                           f"--project {project.name}")
    observed = GS.observe(project, signature_of=live)
    assert observed.state == GS.SupervisorState.UNRESPONSIVE.value


def test_the_supervisor_command_is_an_argument_list(project):
    """(20) No shell, ever, and the project is on the command line for identity."""
    command = GS.supervisor_command(project, interval=30.0)
    assert isinstance(command, list)
    assert "queue_supervisor" in " ".join(command)
    assert project.project_id in command   # the identifier, never the display name
    assert not any(";" in part or "&" in part for part in command)

    # THE REGRESSION. The first real launch put `project.name` here — "Pilot 3F
    # commuting" — and the supervisor died on startup because a name with spaces is
    # not a safe path component. The command has to carry something loadable.
    from platform_core.projects import load_project as _load
    identifier = command[command.index("--project") + 1]
    assert _load(identifier, resolve_data_dir(injected=Path(project.root).parent.parent,
                                              ensure=False)).project_id == \
        project.project_id


# ================================================= 5 durations
def test_durations_are_computed_per_stage_and_missing_stays_missing():
    """(21) A stage without both endpoints is None, never zero."""
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                       queued_utc="2026-08-05T10:00:00+00:00",
                       launch_attempt_utc="2026-08-05T10:00:05+00:00",
                       started_utc="2026-08-05T10:00:06+00:00",
                       completed_utc="2026-08-05T10:04:06+00:00")
    GL._apply_durations(job)
    assert job.queue_wait_seconds == 5.0
    assert job.launch_duration_seconds == 1.0
    assert job.run_duration_seconds == 240.0
    assert job.total_elapsed_seconds == 246.0

    never_ran = GC.JobRecord(job_id="k", session_id="s", plan_id="p",
                             queued_utc="2026-08-05T10:00:00+00:00")
    GL._apply_durations(never_ran)
    assert never_ran.run_duration_seconds is None
    assert never_ran.total_elapsed_seconds is None


def test_a_single_job_summary_is_labelled_as_one_observation():
    """(22) One point is not a distribution, and the summary says so."""
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                       queued_utc="2026-08-05T10:00:00+00:00",
                       started_utc="2026-08-05T10:00:06+00:00",
                       completed_utc="2026-08-05T10:04:06+00:00")
    GL._apply_durations(job)
    summary = GM.plan_duration_summary([job], plan_id="p")
    stage = summary.stages["run_duration_seconds"]
    assert stage.status == GM.SINGLE_OBSERVATION
    assert stage.dispersion_available is False
    assert any("single observation" in n for n in summary.notes)


def test_an_unfinished_job_does_not_contribute_a_zero_duration():
    """(23) Averaging a failure as instant would make a broken plan look fast."""
    done = GC.JobRecord(job_id="a", session_id="s", plan_id="p",
                        queued_utc="2026-08-05T10:00:00+00:00",
                        started_utc="2026-08-05T10:00:00+00:00",
                        completed_utc="2026-08-05T10:10:00+00:00")
    GL._apply_durations(done)
    never = GC.JobRecord(job_id="b", session_id="s2", plan_id="p")
    summary = GM.plan_duration_summary([done, never], plan_id="p")
    stage = summary.stages["run_duration_seconds"]
    assert stage.n_observations == 1
    assert stage.n_missing == 1
    assert stage.mean_seconds == 600.0


# ================================================= 6 cost honesty
def _ledger(tmp_path, entries):
    output = tmp_path / "session"
    output.mkdir(parents=True, exist_ok=True)
    (output / "api_calls.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return output


def test_an_unknown_cache_write_ttl_leaves_the_cost_bounded_not_priced(tmp_path):
    """(24) The provider bills 5-minute and 1-hour writes differently."""
    output = _ledger(tmp_path, [
        {"role": "participant", "model": "claude-haiku-4-5-20251001",
         "input_tokens": 1000, "output_tokens": 300,
         "cache_creation_input_tokens": 10000, "cache_read_input_tokens": 0}])
    table = GPL.PricingTable(table_version="t1", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=2.00, cache_read_rate=0.10)])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={}, table=table)
    assert report.cost_status == GPL.CACHE_WRITE_TTL_UNKNOWN
    assert report.total_cost is None
    assert report.cost_lower_bound < report.cost_upper_bound
    assert "between" in report.cost_display


def test_a_declared_ttl_resolves_the_ambiguity(tmp_path):
    """(25) When the ledger says which TTL was used, the price is a price."""
    output = _ledger(tmp_path, [
        {"role": "participant", "model": "claude-haiku-4-5-20251001",
         "input_tokens": 1000, "output_tokens": 300,
         "cache_creation_input_tokens": 10000, "cache_write_ttl": "1h"}])
    table = GPL.PricingTable(table_version="t1", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=2.00, cache_read_rate=0.10)])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={}, table=table)
    assert report.cost_status == GPL.OBSERVED_USAGE_PRICED
    assert report.total_cost == pytest.approx(
        1000 / 1e6 * 1.0 + 300 / 1e6 * 5.0 + 10000 / 1e6 * 2.00)


def test_the_retired_cache_creation_rate_is_not_reused_as_a_five_minute_rate():
    """(26) The old field never said which TTL it priced; it is not guessed."""
    table = GPL.table_from_dict({
        "table_version": "old", "currency": "USD",
        "rows": [{"provider": "anthropic", "model": "claude-haiku-4-5-20251001",
                  "input_rate": 1.0, "output_rate": 5.0,
                  "cache_creation_rate": 1.25, "cache_read_rate": 0.10}]})
    rate = table.rate_for("claude-haiku-4-5-20251001")
    assert rate.cache_write_5m_rate is None
    assert rate.cache_write_1h_rate is None
    assert "cache_creation_rate" in table.note


def test_reconciliation_reports_a_divergence_without_correcting_either_figure():
    """(27) The platform's total is never adjusted to match a bill."""
    record = GPL.reconcile(scope="one session", platform_total=1.20,
                           provider_total=1.55, provider_figure_source="console")
    assert record.status == GPL.DIVERGENT
    assert record.platform_total == 1.20 and record.provider_total == 1.55
    assert any("Neither figure is adjusted" in n for n in record.notes)


def test_an_undefined_platform_total_is_not_compared_as_zero():
    """(28) Undefined stays undefined, including here."""
    record = GPL.reconcile(scope="one session", platform_total=None,
                           provider_total=2.00)
    assert record.status == GPL.NOT_COMPARABLE
    assert record.difference is None
    assert any("not read as zero" in n for n in record.notes)


def test_a_projection_is_labelled_a_scenario_and_never_a_budget():
    """(29) The label travels with the artefact, not with the caption."""
    priced = [GPL.UsageReport(total_cost=1.20, currency="USD"),
              GPL.UsageReport(total_cost=1.60, currency="USD")]
    projection = GPL.project_scenario(priced, n_sessions=30)
    assert projection.status == GPL.SCENARIO_NOT_BUDGET
    assert projection.to_dict()["status"] == GPL.SCENARIO_NOT_BUDGET
    assert projection.projected_cost == pytest.approx(42.0)
    assert projection.assumptions


def test_a_projection_from_one_session_declares_it_has_no_dispersion():
    """(30) One observation scaled thirty times is still one observation."""
    projection = GPL.project_scenario(
        [GPL.UsageReport(total_cost=1.20, currency="USD")], n_sessions=30)
    assert projection.single_observation is True
    assert projection.dispersion_available is False
    assert any("ONE observed session" in p for p in projection.problems)


def test_an_unpriced_session_is_excluded_from_a_projection_not_counted_as_zero():
    """(31) Averaging an Undefined cost as zero understates every projection."""
    reports = [GPL.UsageReport(total_cost=2.00, currency="USD"),
               GPL.UsageReport(total_cost=None, currency="USD")]
    projection = GPL.project_scenario(reports, n_sessions=10)
    assert projection.n_observations == 1
    assert projection.projected_cost == pytest.approx(20.0)
    assert any("not counted as zero" in p for p in projection.problems)


def test_a_pricing_context_without_a_date_says_it_cannot_be_verified():
    """(32) A rate with no date is not checkable against anything."""
    table = GPL.PricingTable(table_version="t1", rows=[
        GPL.RateRow(provider="anthropic", model="m", input_rate=1.0,
                    output_rate=5.0)])
    context = GPL.context_from_table(table)
    assert any("cannot be verified" in p for p in context.problems)
    assert "never fetched" in context.note


# ======================================= 7 one public profile validator
def test_the_architecture_validator_has_exactly_one_definition():
    """(33) Two copies meant a profile could reach a paid run unchecked."""
    assert PS.architecture_shape_problems is PROF.architecture_shape_problems


def test_a_string_background_is_refused_by_the_general_loader(tmp_path):
    """(34) The shape that crashed a real session after six paid calls."""
    payload = {"agent_id": "p1", "schema_version": "fg_agents_v1",
               "persona": {"demographics": {"name": "Ana", "age": 40,
                                            "gender": "woman"},
                           "background": "a paragraph, not a mapping"}}
    path = tmp_path / "p1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    record = PROF.load_profile_file(path)
    assert any("must be an object" in p for p in record.architecture_problems)
    profile_set = PROF.load_profile_set([path])
    assert profile_set.validation.blocking is True


# ============================================ 8 the smoke-run manifest
@requires_smoke
def test_the_manifest_classifies_every_run_as_not_thesis_data(tmp_path):
    """(35) A directory of transcripts is otherwise indistinguishable from data."""
    manifest = GSM.build_manifest()
    assert manifest.classification == GSM.EXPLORATORY_NOT_THESIS_DATA
    # The two smoke runs plus the three pilot sessions. Every real run this project
    # has ever produced is listed; none of them is study data.
    assert len(manifest.runs) == len(GSM.SMOKE_RUNS) >= 5
    assert all(r.classification == GSM.EXPLORATORY_NOT_THESIS_DATA
               for r in manifest.runs)
    present = [r for r in manifest.runs if r.exists]
    assert present and all(r.file_hashes for r in present)
    completed = next(r for r in manifest.runs
                     if r.session_id == SMOKE_COMPLETED.name)
    assert completed.completion_quality == GT.CompletionQuality.GUIDE_COMPLETED.value
    assert completed.n_ledger_entries and completed.n_ledger_entries > 0

    # The pilot sessions ran under the supervisor and every one finished its guide.
    pilot = [r for r in manifest.runs if r.session_id.startswith("commuting_pilot")]
    assert len(pilot) == 3
    for run in pilot:
        if run.exists:
            assert (run.completion_quality
                    == GT.CompletionQuality.GUIDE_COMPLETED.value)
            assert run.guide_sections_completed == run.guide_sections_total == 3
            assert run.transcript_state_match is True


@requires_smoke
def test_building_the_manifest_does_not_modify_the_runs(tmp_path):
    """(36) Describing evidence must not change it."""
    before = {p: p.stat().st_mtime_ns for p in SMOKE_COMPLETED.rglob("*")
              if p.is_file()}
    GSM.build_manifest()
    after = {p: p.stat().st_mtime_ns for p in SMOKE_COMPLETED.rglob("*")
             if p.is_file()}
    assert before == after


@requires_smoke
def test_the_manifest_may_not_be_written_inside_a_run_it_describes():
    """(37) It would change the hashes it just recorded, including its own."""
    with pytest.raises(ValueError):
        GSM.write_manifest(SMOKE_COMPLETED / "manifest.json")

# ================================ 9 defects found by the adversarial review
# Every one of these passed 760 tests before an independent reader found it. The tests
# below exist so the same mistake cannot come back quietly.
def test_a_bound_that_omits_an_unpriced_row_is_not_offered(tmp_path):
    """(38) A one-character typo in a model name turned USD 1.16 into "0.09 to 0.11".

    The bound summed only the rows it could price, so a range that omitted real
    spending read as a complete answer. Worst possible failure for the one module
    whose entire purpose is not misstating money.
    """
    output = _ledger(tmp_path, [
        {"role": "moderator", "model": "claude-sonnet-4-6", "input_tokens": 1_000_000,
         "output_tokens": 0},
        {"role": "participant", "model": "claude-haiku-4-5-20251001", "input_tokens": 1000,
         "output_tokens": 0, "cache_creation_input_tokens": 10000}])
    partial = GPL.PricingTable(table_version="partial", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001", input_rate=1.0,
                    output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=2.00, cache_read_rate=0.10)])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={},
                             table=partial)
    assert report.cost_status == GPL.OBSERVED_USAGE_UNPRICED
    assert report.total_cost is None
    assert report.cost_display == "Undefined"
    assert "claude-sonnet-4-6" in report.unpriced_models
    assert "claude-haiku-4-5-20251001" not in report.unpriced_models   # it IS priced, to a bound


def test_per_ttl_cache_fields_are_counted_as_tokens_not_read_as_a_flag(tmp_path):
    """(39) The 5m/1h fields picked a TTL and their token counts were discarded."""
    table = GPL.PricingTable(table_version="t", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=2.00, cache_read_rate=0.10)])
    output = _ledger(tmp_path / "a", [
        {"model": "claude-haiku-4-5-20251001", "input_tokens": 100, "output_tokens": 50,
         "cache_creation_5m_input_tokens": 20000}])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={}, table=table)
    assert report.cache_creation_tokens == 20000
    assert report.total_cost == pytest.approx(
        100 / 1e6 * 1.0 + 50 / 1e6 * 5.0 + 20000 / 1e6 * 1.25)


def test_a_call_using_both_ttls_is_priced_at_both_rates(tmp_path):
    """(40) Every write went into whichever bucket matched first - 33% out, and
    reported as determined rather than bounded."""
    table = GPL.PricingTable(table_version="t", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=2.00, cache_read_rate=0.10)])
    output = _ledger(tmp_path / "b", [
        {"model": "claude-haiku-4-5-20251001", "cache_creation_input_tokens": 6000,
         "cache_creation_5m_input_tokens": 1000,
         "cache_creation_1h_input_tokens": 5000}])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={}, table=table)
    assert report.cost_status == GPL.OBSERVED_USAGE_PRICED
    assert report.total_cost == pytest.approx((1000 * 1.25 + 5000 * 2.00) / 1e6)


def test_an_unreadable_lock_is_held_not_free(project, profiles, guide):
    """(41) O_EXCL creates a zero-byte file and the JSON lands milliseconds later.

    Reading the lock in that window returned nothing, which was taken as "no owner" -
    so a second supervisor stole the lock from one that had just acquired it, and both
    launched into the same free slot.
    """
    study, plan = _confirmed(project, profiles, guide, generation_study_id="lockread")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GS.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.lock_path(project).write_text("", encoding="utf-8")
    with pytest.raises(GS.LockHeld):
        GS.acquire_lock(project, signature_of=lambda pid: None)


def test_a_recycled_pid_with_no_start_time_does_not_block_the_project(project,
                                                                     profiles, guide):
    """(42) An unverifiable holder was assumed alive, deadlocking the project."""
    study, plan = _confirmed(project, profiles, guide, generation_study_id="lockpid")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GS.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.lock_path(project).write_text(json.dumps(
        {"pid": 4242, "process_start_time": None,
         "project_id": project.project_id}), encoding="utf-8")
    # The pid is alive; it is running something else entirely.
    payload = GS.acquire_lock(project,
                              signature_of=lambda pid: (5000.0, "notepad.exe"))
    assert payload["took_over_from"] == 4242

    # ...but a live supervisor for THIS project is still honoured.
    GS.lock_path(project).write_text(json.dumps(
        {"pid": 4242, "process_start_time": None,
         "project_id": project.project_id}), encoding="utf-8")
    cmdline = (f"py -m platform_core.generation.queue_supervisor "
               f"--project {project.project_id}")
    with pytest.raises(GS.LockHeld):
        GS.acquire_lock(project, signature_of=lambda pid: (5000.0, cmdline))


def test_the_worker_writes_a_verdict_for_every_malformed_transcript(tmp_path):
    """(43) `null` in transcript.json killed the worker before it wrote anything, so
    a session that really ran ended up with no evidence it had existed."""
    for index, content in enumerate(
            ("null", '{"transcript": 5}', "[]", "not json at all")):
        output = tmp_path / f"run_{index}"
        output.mkdir()
        (output / "transcript.json").write_text(content, encoding="utf-8")
        result = GW.inspect_output(output, "", session_id="s", max_turns=15)
        assert (result["completion_quality"]
                == GT.CompletionQuality.INVALID_OUTPUT.value)
        assert result["transcript_parseable"] is False


def test_max_turns_typing_cannot_split_the_two_implementations(tmp_path):
    """(44) A string max_turns raised in one copy and capped the run in the other -
    at the COMPLETED/FAILED boundary, not somewhere cosmetic."""
    output = _write_run(tmp_path / "run", turn_index=15, total_turns=15,
                        sections_completed=1, sections_total=2)
    for max_turns in (15, "15", 15.5, None, True, "abc"):
        from_terminal = GT.inspect_output(output, "", session_id="s1",
                                          max_turns=max_turns)
        from_worker = GW.inspect_output(output, "", session_id="s1",
                                        max_turns=max_turns)
        assert from_terminal == from_worker, f"diverged on max_turns={max_turns!r}"


def test_an_unreadable_terminal_record_is_absent_not_fatal(tmp_path):
    """(45) A record containing `null` raised out of observe() and blanked every job
    in the project, not only its own."""
    path = tmp_path / "terminal_record.json"
    for content in ("null", "[]", '"x"', "3", "{not json"):
        path.write_text(content, encoding="utf-8")
        assert GT.load_terminal_record(path) is None


def test_a_non_boolean_in_a_gate_field_is_unestablished_not_benign(tmp_path):
    """(46) "transcript_state_match": "no" passed `is False`, so the gate that stops
    an incoherent run being imported never fired."""
    path = tmp_path / "terminal_record.json"
    path.write_text(json.dumps({
        "job_id": "j", "session_id": "s", "exit_code": 0,
        "termination_kind": GT.TerminationKind.NORMAL_EXIT.value,
        "transcript_exists": True, "transcript_parseable": True,
        "completion_quality": GT.CompletionQuality.GUIDE_COMPLETED.value,
        "completion_evidence": GT.CompletionEvidence.STRUCTURED_STATE.value,
        "transcript_state_match": "no"}), encoding="utf-8")
    record = GT.load_terminal_record(path)
    assert record.transcript_state_match is None
    assert any("neither true, false nor absent" in p
               for p in record.final_state_problems)


def test_a_legacy_stdout_only_verdict_is_not_accepted_as_final(tmp_path):
    """(47) The verdict Phase 3F exists to distrust was still reaching COMPLETED."""
    path = tmp_path / "terminal_record.json"
    path.write_text(json.dumps({
        "schema_version": "1.0.0", "job_id": "j", "session_id": "s", "exit_code": 0,
        "termination_kind": GT.TerminationKind.NORMAL_EXIT.value,
        "transcript_exists": True, "transcript_parseable": True,
        "completion_quality": GT.CompletionQuality.GUIDE_COMPLETED.value,
    }), encoding="utf-8")
    record = GT.load_terminal_record(path)
    assert (record.completion_evidence
            == GT.CompletionEvidence.STDOUT_ONLY_LEGACY.value)
    assert record.usable_output is False


def test_no_real_agent_payload_in_this_repository_is_refused():
    """(48) The validator refused 44 of 123 real payloads by inventing a requirement.

    It followed `core.participant_agent`'s docstring, which lists age and gender as
    required, instead of its code, which does `if age is not None`. A validator that
    blocks work the architecture accepts is as broken as one that admits work it
    rejects.
    """
    agents = REPO_ROOT / "agents"
    if not agents.is_dir():
        pytest.skip("the agents directory is not present in this checkout")
    refused = []
    for path in sorted(agents.rglob("*.json")):
        if path.name == "_manifest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict) and PROF.architecture_shape_problems(payload):
            refused.append(path.name)
    assert refused == [], f"{len(refused)} real payload(s) refused: {refused[:5]}"

# ============================ 10 the second review pass (state and control)
def test_a_state_carrying_a_different_guide_cannot_report_completion(project,
                                                                    profiles, guide):
    """(49) THE ONE ROUTE by which an incomplete session was recorded as complete.

    "All sections completed" was a claim the session's own state got to make about
    itself. A state carrying one section, marked done, read as GUIDE_COMPLETED for a
    three-section plan. The plan's section count is now on the job and is checked.
    """
    study, plan = _confirmed(project, profiles, guide, generation_study_id="guidechk")
    session = plan.sessions[0]
    job = GL.build_job(project, plan, session.session_id, max_turns=study.max_turns,
                       mode=study.participation_mode,
                       effective_config_sha256=plan.effective_config_hashes.get(
                           session.session_id, ""),
                       architecture_code_manifest_hash=(
                           plan.architecture_code_manifest_hash))
    assert job.guide_sections_expected == 3      # read from the compiled config

    def record(sections_total):
        return GT.TerminalRecord(
            job_id=job.job_id, session_id=job.session_id, exit_code=0,
            termination_kind=GT.TerminationKind.NORMAL_EXIT.value,
            config_sha256=job.config_sha256, transcript_exists=True,
            transcript_parseable=True,
            completion_quality=GT.CompletionQuality.GUIDE_COMPLETED.value,
            completion_evidence=GT.CompletionEvidence.STRUCTURED_STATE.value,
            transcript_state_match=True, guide_sections_total=sections_total,
            guide_sections_completed=sections_total)

    GL._apply_terminal_record(job, record(1))
    assert job.status == GC.JobStatus.FAILED.value
    assert "3 guide section(s)" in job.failure_reason

    GL._apply_terminal_record(job, record(3))
    assert job.status == GC.JobStatus.COMPLETED.value


def test_a_wrong_config_is_reported_before_a_coherence_problem(project, profiles,
                                                               guide):
    """(50) Running the wrong configuration is a different study cell — wrong panel,
    wrong guide, wrong condition. It used to be hidden behind the smaller finding."""
    study, plan = _confirmed(project, profiles, guide)
    job = GC.JobRecord(job_id="j", session_id="s", plan_id=plan.plan_id,
                       config_sha256="a" * 64, guide_sections_expected=3)
    GL._apply_terminal_record(job, GT.TerminalRecord(
        job_id="j", session_id="s", exit_code=0,
        termination_kind=GT.TerminationKind.NORMAL_EXIT.value,
        config_sha256="b" * 64, transcript_exists=True, transcript_parseable=True,
        completion_quality=GT.CompletionQuality.GUIDE_COMPLETED.value,
        completion_evidence=GT.CompletionEvidence.CONFLICTING_EVIDENCE.value,
        transcript_state_match=False,
        transcript_state_mismatch_reason="intervention 3 differs"))
    assert job.status == GC.JobStatus.FAILED.value
    assert "config hashing" in job.failure_reason


def test_a_naive_timestamp_does_not_raise_out_of_the_duration_maths():
    """(51) One hand-edited record blanked the Generate view for every job.

    NOTE: the first fix made a naive stamp aware by ASSUMING UTC. The audit argued
    that this manufactures a plausible number when the stamp was local time, and it
    was right - see test 65. Not raising is the requirement here; the value being
    None rather than invented is the requirement there.
    """
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                       queued_utc="2026-08-05T10:00:00",             # no offset
                       started_utc="2026-08-05T10:00:06+00:00",
                       completed_utc="2026-08-05T10:04:06+00:00")
    GL._apply_durations(job)
    assert job.queue_wait_seconds is None
    assert job.run_duration_seconds == 240.0

    # A non-string is not a timestamp, and is not an AttributeError either.
    numeric = GC.JobRecord(job_id="k", session_id="s", plan_id="p",
                           queued_utc=1754388000,
                           completed_utc="2026-08-05T10:04:06+00:00")
    GL._apply_durations(numeric)
    assert numeric.queue_wait_seconds is None
    summary = GM.plan_duration_summary([job, numeric], plan_id="p")
    assert summary.n_jobs == 2


def test_a_pause_set_during_a_tick_is_not_reverted(project, profiles, guide):
    """(52) `tick()` wrote the whole record back, so a pause set while it ran was
    silently undone and the next tick launched again."""
    study, plan = _confirmed(project, profiles, guide,
                             focus_groups=["fg1", "fg2"], replicates=1, generation_study_id="pausetick")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)
    worker = FakeWorker()

    def pause_midway(command, *, stdout_path, cwd):
        # The researcher presses Pause while this launch is in flight.
        GQ.pause(project)
        return worker(command, stdout_path=stdout_path, cwd=cwd)

    GQ.tick(project, spawn=pause_midway)
    assert GQ.load_queue(project).paused is True

    following = GQ.tick(project, spawn=worker)
    assert following.launched == []
    import shutil
    for job in GL.observe_all(project):
        shutil.rmtree(Path(job.expected_output_directory), ignore_errors=True)


def test_n_completed_counts_completions_not_timestamps():
    """(53) CANCELLED and ORPHANED jobs carry a completed_utc too, so a plan where
    two of three jobs died reported "3 of 3" and a clean wall clock."""
    jobs = []
    for index, status in enumerate((GC.JobStatus.COMPLETED.value,
                                    GC.JobStatus.CANCELLED.value,
                                    GC.JobStatus.ORPHANED.value)):
        job = GC.JobRecord(job_id=f"j{index}", session_id=f"s{index}", plan_id="p",
                           status=status,
                           queued_utc="2026-08-05T10:00:00+00:00",
                           started_utc="2026-08-05T10:00:00+00:00",
                           completed_utc="2026-08-05T10:10:00+00:00")
        GL._apply_durations(job)
        jobs.append(job)
    summary = GM.plan_duration_summary(jobs, plan_id="p")
    assert summary.n_jobs == 3
    assert summary.n_completed == 1
    assert summary.n_terminal == 3
    assert any("did not run as designed" in n for n in summary.notes)


def test_the_launch_stage_is_not_presented_as_a_distribution():
    """(54) It spans two adjacent assignments; the pilot measured 1e-5 s and the
    table rendered interpreter jitter beside three real metrics."""
    assert "launch_duration_seconds" not in GM.STAGES
    assert "launch_duration_seconds" in GM.UNSUMMARISED_STAGES
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p")
    assert "launch_duration_seconds" in job.durations   # still recorded per job


def test_a_rate_edited_in_memory_invalidates_the_table_hash():
    """(55) The stored hash won, so a report could name a table that had not priced
    it."""
    table = GPL.table_from_dict({
        "table_version": "v1", "currency": "USD",
        "rows": [{"provider": "anthropic", "model": "claude-sonnet-4-6",
                  "input_rate": 3.0, "output_rate": 15.0}]})
    before = table.to_dict()["table_sha256"]
    table.rows[0].input_rate = 30.0
    assert table.to_dict()["table_sha256"] != before


def test_a_mixed_currency_table_produces_no_total():
    """(56) 1 USD + 3 GBP was summed to "4.0000 USD" with no problem recorded."""
    output = _ledger(Path(__import__("tempfile").mkdtemp()), [
        {"role": "moderator", "model": "claude-sonnet-4-6", "input_tokens": 1_000_000,
         "output_tokens": 0},
        {"role": "participant", "model": "claude-haiku-4-5-20251001",
         "input_tokens": 1_000_000, "output_tokens": 0}])
    mixed = GPL.PricingTable(table_version="mixed", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-sonnet-4-6", input_rate=3.0,
                    output_rate=15.0, currency="GBP"),
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, currency="USD")])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={},
                             table=mixed)
    assert report.total_cost is None
    assert any("not added" in p for p in report.problems)


def test_a_projection_says_the_excluded_sessions_were_bounded_not_cheap():
    """(57) The excluded sessions are the cache-heavy ones, so the exclusion is not
    missing-at-random and the projection understates."""
    reports = [GPL.UsageReport(total_cost=0.50, currency="USD"),
               GPL.UsageReport(total_cost=None, cost_lower_bound=5.0,
                               cost_upper_bound=9.0, currency="USD",
                               cost_status=GPL.CACHE_WRITE_TTL_UNKNOWN)]
    projection = GPL.project_scenario(reports, n_sessions=30)
    assert projection.n_observations == 1
    assert any("BOUNDED, not unknown" in p for p in projection.problems)
    assert any("understate" in p for p in projection.problems)


def test_starting_a_supervisor_builds_a_detached_command_and_records_it(project,
                                                                       profiles,
                                                                       guide):
    """(58) `start()` had NO test — every other test injected `spawn`. That is
    exactly why the first real launch died before its first tick."""
    study, plan = _confirmed(project, profiles, guide, generation_study_id="startsup")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)

    seen = {}

    def fake_spawn(command, cwd, log):
        seen["command"], seen["cwd"], seen["log"] = command, cwd, log
        return 4242

    record = GS.start(project, interval=30.0, spawn=fake_spawn,
                      signature_of=lambda pid: None)
    assert record.pid == 4242
    assert record.project_id == project.project_id
    # The identifier on the command line must be one `load_project` accepts, and the
    # module must be importable as `python -m`.
    identifier = seen["command"][seen["command"].index("--project") + 1]
    assert identifier == project.project_id
    assert seen["command"][1:3] == ["-m", "platform_core.generation.queue_supervisor"]
    import importlib.util
    assert importlib.util.find_spec("platform_core.generation.queue_supervisor")
    assert Path(seen["log"]).name == GS.LOG_FILENAME


def test_an_unresponsive_supervisor_can_be_abandoned(project, profiles, guide):
    """(59) A wedged loop never reads a stop request, so the interface offered a
    remedy that could not work and Start stayed disabled forever."""
    study, plan = _confirmed(project, profiles, guide, generation_study_id="abandon")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GS.save_state(project, GS.SupervisorRecord(
        project_name=project.name, project_id=project.project_id, pid=4242,
        process_start_time=1000.0, state=GS.SupervisorState.RUNNING.value,
        interval_seconds=20.0, started_utc="2026-08-05T00:00:00+00:00",
        last_heartbeat_utc="2026-08-05T00:00:00+00:00"))
    GS.lock_path(project).write_text(json.dumps(
        {"pid": 4242, "process_start_time": 1000.0,
         "project_id": project.project_id}), encoding="utf-8")
    live = (f"py -m platform_core.generation.queue_supervisor "
            f"--project {project.project_id}")
    assert GS.observe(project, signature_of=lambda pid: (1000.0, live)).state == (
        GS.SupervisorState.UNRESPONSIVE.value)

    detail = GS.force_release(project, signature_of=lambda pid: (1000.0, live))
    assert detail["abandoned_pid"] == 4242
    assert detail["process_killed"] is False    # never killed; it may be mid-launch
    assert not GS.lock_path(project).exists()
    # And the project can take a new supervisor again.
    GS.acquire_lock(project, signature_of=lambda pid: None)

# ========================= 11 defects the audit of the FIXES found
def test_the_lock_is_taken_by_the_operating_system_not_the_last_writer(project,
                                                                      profiles,
                                                                      guide):
    """(60) Overwriting a stale lock atomically was not exclusion: two supervisors
    that both found the same corpse both wrote and both continued."""
    study, plan = _confirmed(project, profiles, guide, generation_study_id="takeover")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GS.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.lock_path(project).write_text(json.dumps(
        {"pid": 999999, "process_start_time": 1.0,
         "project_id": project.project_id}), encoding="utf-8")

    payload = GS.acquire_lock(project, signature_of=lambda pid: None)
    assert payload["took_over_from"] == 999999
    # The lock is now genuinely held: a second claimant meets an EXCLUSIVE create,
    # not a file it can overwrite.
    with pytest.raises(GS.LockHeld):
        GS.acquire_lock(project, signature_of=lambda pid: (
            (1000.0, f"py -m platform_core.generation.queue_supervisor "
                     f"--project {project.project_id}")))


def test_a_tick_refuses_to_run_beside_a_live_supervisor(project, profiles, guide):
    """(61) THE ENFORCEMENT. `disabled=` on a button is advice: it reads a state file
    that can be an interval stale, and calling tick() directly bypasses it."""
    study, plan = _confirmed(project, profiles, guide, generation_study_id="ticklock")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)
    GS.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    GS.lock_path(project).write_text(json.dumps(
        {"pid": 999999, "process_start_time": 1000.0,
         "project_id": project.project_id}), encoding="utf-8")
    live = (f"py -m platform_core.generation.queue_supervisor "
            f"--project {project.project_id}")

    worker = FakeWorker()
    with pytest.raises(GC.GenerationError) as caught:
        GQ.tick(project, spawn=worker, signature_of=lambda pid: (1000.0, live))
    assert "second scheduler" in str(caught.value)
    assert worker.calls == []          # nothing was launched


def test_abandoning_a_supervisor_that_recovered_is_refused(project, profiles, guide):
    """(62) Streamlit renders, then acts on a later run. A supervisor that was merely
    slow could have its lock pulled by a click on a stale screen."""
    study, plan = _confirmed(project, profiles, guide, generation_study_id="abandon2")
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GS.save_state(project, GS.SupervisorRecord(
        project_name=project.name, project_id=project.project_id, pid=4242,
        process_start_time=1000.0, state=GS.SupervisorState.RUNNING.value,
        interval_seconds=20.0, started_utc=datetime.now(UTC).isoformat(),
        last_heartbeat_utc=datetime.now(UTC).isoformat()))     # heartbeat is CURRENT
    live = (f"py -m platform_core.generation.queue_supervisor "
            f"--project {project.project_id}")
    with pytest.raises(GC.GenerationError) as caught:
        GS.force_release(project, signature_of=lambda pid: (1000.0, live))
    assert "recovered" in str(caught.value)


def test_the_workers_own_failure_reason_outranks_what_we_infer(project, profiles,
                                                               guide):
    """(63) The one config change this platform can actually detect - the worker
    re-verifying the hash in its own process - was reported as "the session ended
    without writing a transcript"."""
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                       config_sha256="a" * 64)
    GL._apply_terminal_record(job, GT.TerminalRecord(
        job_id="j", session_id="s", exit_code=None,
        termination_kind=GT.TerminationKind.PROCESS_LOST.value,
        config_sha256="a" * 64, transcript_exists=False,
        failure_reason=("the config changed after the plan was confirmed: expected "
                        "aaaa…, found bbbb…")))
    assert job.status == GC.JobStatus.FAILED.value
    assert "the config changed after the plan was confirmed" in job.failure_reason


def test_an_orphaned_job_does_not_decay_to_unknown(project, profiles, guide):
    """(64) ORPHANED became UNKNOWN on the next observation. UNKNOWN is in neither
    the queue's occupying nor its terminal set, so the queue never reached COMPLETED
    and the supervisor ran until its twelve-hour lifetime."""
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                       status=GC.JobStatus.ORPHANED.value,
                       failure_reason="the worker vanished")
    GL.save_job(project, job)
    observed = GL.observe(project, job, signature_of=lambda pid: None)
    assert observed.status == GC.JobStatus.ORPHANED.value
    assert observed.status in GQ.TERMINAL


def test_a_naive_timestamp_is_unobserved_rather_than_assumed_to_be_utc():
    """(65) Reading an offset-less stamp as UTC manufactured a plausible number: from
    a UTC-5 machine, a queue wait 18,000 seconds too long, entering the mean unmarked.
    None is a first-class outcome here and is reported as n_missing."""
    job = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                       queued_utc="2026-08-05T10:00:00",              # no offset
                       started_utc="2026-08-05T10:00:06+00:00",
                       completed_utc="2026-08-05T10:04:06+00:00")
    GL._apply_durations(job)
    assert job.queue_wait_seconds is None       # not 6.0, and not a crash
    assert job.run_duration_seconds == 240.0    # the aware pair still works
    summary = GM.plan_duration_summary([job], plan_id="p")
    assert summary.stages["queue_wait_seconds"].n_missing == 1


def test_terminality_is_a_property_of_the_job_not_of_a_timestamp():
    """(66) A REQUIRES_RECOVERY job carries a completed_utc and is explicitly NOT
    terminal - it is waiting for a human."""
    waiting = GC.JobRecord(job_id="j", session_id="s", plan_id="p",
                           status=GC.JobStatus.REQUIRES_RECOVERY.value,
                           completed_utc="2026-08-05T10:10:00+00:00")
    summary = GM.plan_duration_summary([waiting], plan_id="p")
    assert waiting.terminal is False
    assert summary.n_terminal == 0
    assert summary.n_completed == 0


def test_a_failed_plan_is_described_by_the_statuses_it_actually_had():
    """(67) The note enumerated "cancelled, orphaned or failed to launch" and left out
    FAILED - the commonest outcome of a bad run - in a sentence a reader may copy."""
    jobs = [GC.JobRecord(job_id=f"j{i}", session_id=f"s{i}", plan_id="p", status=st,
                         queued_utc="2026-08-05T10:00:00+00:00",
                         completed_utc="2026-08-05T10:10:00+00:00")
            for i, st in enumerate((GC.JobStatus.COMPLETED.value,
                                    GC.JobStatus.FAILED.value))]
    summary = GM.plan_duration_summary(jobs, plan_id="p")
    assert any("FAILED" in n for n in summary.notes)


def test_a_corrupt_token_value_does_not_kill_the_whole_cost_report(tmp_path):
    """(68) `read_calls` tolerates a corrupt LINE; a corrupt VALUE raised straight out
    of consolidate and took the cost report and the page with it."""
    output = _ledger(tmp_path, [
        {"model": "claude-haiku-4-5-20251001", "input_tokens": "abc",
         "output_tokens": 100}])
    table = GPL.PricingTable(table_version="t", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0)])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={},
                             table=table)
    assert report.total_cost == pytest.approx(100 / 1e6 * 5.0)
    assert any("not a token count" in p for p in report.problems)
    assert any("understated" in p for p in report.problems)


def test_a_total_is_labelled_with_the_currency_its_rates_were_in(tmp_path):
    """(69) A real total carried the table's label while every figure in it came from
    the rows: 3.00 GBP was displayed as "3.0000 USD"."""
    output = _ledger(tmp_path, [
        {"model": "claude-sonnet-4-6", "input_tokens": 1_000_000, "output_tokens": 0}])
    mislabelled = GPL.PricingTable(table_version="t", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-sonnet-4-6", input_rate=3.0,
                    output_rate=15.0, currency="GBP")])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={},
                             table=mislabelled)
    assert report.total_cost == pytest.approx(3.0)
    assert report.cost_display.endswith("GBP")
    assert any("the label was wrong" in p for p in report.problems)


def test_the_pricing_context_names_the_table_that_actually_priced_the_run():
    """(70) The stale-hash defect removed from to_dict() was still live one function
    away, so the provenance record named a different table from the report."""
    table = GPL.table_from_dict({
        "table_version": "v1", "currency": "USD",
        "rows": [{"provider": "anthropic", "model": "claude-sonnet-4-6",
                  "input_rate": 3.0, "output_rate": 15.0}]})
    table.rows[0].input_rate = 30.0
    context = GPL.context_from_table(table)
    assert context.table_sha256 == GPL.compute_table_hash(table)

# ============================ 12 the five that were left open
def test_the_real_provider_cache_breakdown_shape_is_read(tmp_path):
    """(71) The per-TTL branch looked for flat field names nobody emits.

    The provider nests the breakdown: `cache_creation_input_tokens` is the total and
    `cache_creation: {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}` splits it.
    Support written against invented names is not support.
    """
    table = GPL.PricingTable(table_version="t", currency="USD", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=2.00, cache_read_rate=0.10)])
    output = _ledger(tmp_path, [{
        "model": "claude-haiku-4-5-20251001",
        "cache_creation_input_tokens": 6000,
        "cache_creation": {"ephemeral_5m_input_tokens": 1000,
                            "ephemeral_1h_input_tokens": 5000}}])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={},
                             table=table)
    assert report.cost_status == GPL.OBSERVED_USAGE_PRICED
    assert report.total_cost == pytest.approx((1000 * 1.25 + 5000 * 2.00) / 1e6)


def test_a_malformed_entry_is_not_read_as_transcript_agreement(tmp_path):
    """(72) Non-dict entries were skipped and then the lengths compared, so a state
    that picked up a stray entry was certified coherent with a file that lacked it."""
    stray = [TRANSCRIPT[0], "a stray string", TRANSCRIPT[1]]
    match, reason = GT.compare_transcripts(TRANSCRIPT[:2], stray)
    assert match is False
    assert "not objects" in reason
    # And the worker agrees.
    assert GW._compare_transcripts(TRANSCRIPT[:2], stray) == (match, reason)


def test_the_coherence_contract_is_stated_not_implied():
    """(73) An integer turn equalling its string form was deliberate, and nowhere
    written down. A contract that lives only in the implementation is not a contract:
    the next reader has to guess whether it is intent or oversight."""
    doc = GT.canonical_transcript.__doc__
    assert "STRING form" in doc
    assert "ABSENT field" in doc
    assert "SKIPPED" in doc
    # The behaviour the contract now promises.
    typed = [dict(e, turn=str(e["turn"])) for e in TRANSCRIPT[:2]]
    assert GT.compare_transcripts(TRANSCRIPT[:2], typed)[0] is True


def test_tests_never_write_into_the_researchers_repository(tmp_path, monkeypatch):
    """(74) A test that died mid-run left a directory that made build_job refuse that
    session id on every later run."""
    from platform_core.generation.launcher import (SESSION_OUTPUT_ROOT_ENV,
                                                   session_output_root)
    # The autouse fixture has already redirected it.
    assert str(session_output_root()) != str(REPO_ROOT / "output" / "session_logs")
    monkeypatch.delenv(SESSION_OUTPUT_ROOT_ENV, raising=False)
    assert session_output_root() == REPO_ROOT / "output" / "session_logs"


def test_the_validator_is_reachable_from_the_other_application():
    """(75) POST /start-session built an orchestrator from an unvalidated HTTP body -
    the last route by which a malformed profile could reach a billed call."""
    api = REPO_ROOT / "ui" / "backend" / "api.py"
    if not api.is_file():
        pytest.skip("the separate UI backend is not present in this checkout")
    source = api.read_text(encoding="utf-8")
    assert "_architecture_shape_problems(raw)" in source
    assert "architecture_shape_problems" in source
    # It refuses rather than proceeding unvalidated if the validator cannot load.
    assert "status_code=503" in source
