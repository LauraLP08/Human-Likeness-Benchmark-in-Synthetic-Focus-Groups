"""
Phase 3D: the generation adapter, and the Phase 3C closure items.

NO PROCESS IS STARTED AND NO PROVIDER IS CALLED anywhere in this file. Launching goes
through a fake `spawn`; the CLI is never executed.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
import sys
if str(APP_DIR.parent) not in sys.path:
    sys.path.insert(0, str(APP_DIR.parent))

from platform_core import analysis_window as AW
from platform_core import design as D
from platform_core import thematic as TH
from platform_core.config import REPO_ROOT, resolve_data_dir
from platform_core.generation import (config_builder as CB, contracts as GC,
                                      importer as GI, launcher as GL,
                                      monitor as GM, planner as GP,
                                      profiles_source as PS, terminal as GT,
                                      worker as GW)
from platform_core.services import (audit, design_service as DS,
                                    import_service as I, structural_service as S,
                                    window_service as W)

GUIDE_YAML = """
guide_id: weeknight_guide_v1
title: Weeknight cooking
sections:
  - label: Warm up
    phase: intro
    scripted_question: To start, what does a normal weeknight dinner look like?
  - label: Everyday choices
    phase: main_topic
    scripted_question: Walk me through deciding what to cook last Tuesday.
  - label: Closing
    phase: closing
    scripted_question: Is there anything we have not covered?
"""

PROFILE = {
    "schema_version": "fg_agents_v1",
    "agent_id": "p_ana",
    "language": "en",
    "persona": {"demographics": {"name": "Ana", "age": 34,
                                 "gender": "woman"}},
    "simulation_config": {"model": "claude-haiku-4-5-20251001"},
}


@pytest.fixture()
def data_dir(tmp_path):
    return resolve_data_dir(injected=tmp_path / "platform-data", ensure=True)


@pytest.fixture()
def project(data_dir):
    return I.new_project("Gen trial", data_dir)


@pytest.fixture()
def profiles(tmp_path):
    paths = []
    for name in ("p_ana", "p_ben", "p_cara", "p_dan"):
        payload = dict(PROFILE, agent_id=name)
        payload["persona"] = {"demographics": {"name": name.title(), "age": 30,
                                               "gender": "man"}}
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    return PS.uploaded_profile_set(paths)


@pytest.fixture()
def guide():
    return GP.compile_guide_text(GUIDE_YAML)


def _study(project, **kwargs):
    defaults = dict(
        generation_study_id="weeknight", project_id=project.project_id,
        research_objective="How men in the UK make everyday food choices.",
        topic_domain="Food choice and everyday cooking",
        participant_collective_identity="Men in the UK reflecting on food choices",
        moderator_knowledge_brief="Explore how weeknight food decisions are made.",
        synthetic_conditions=["condition-a"], focus_groups=["fg1"], replicates=1,
        participation_mode="emergent", max_turns=40, created_utc="2026-08-05")
    defaults.update(kwargs)
    return GC.GenerationStudy(**defaults)


def _plan(project, profiles, guide, **kwargs):
    study = _study(project, **kwargs)
    GP.save_study(project, study)
    plan = GP.build_plan(project, study, profile_set=profiles, guide=guide)
    report = GP.dry_run(project, study, plan, profile_set=profiles, guide=guide,
                        env={"ANTHROPIC_API_KEY": "x"})
    plan = GP.confirmed_plan(plan, report)
    return study, plan, report


# =============================================== A1 producer freshness
def test_a_changed_producer_makes_a_result_stale(project, monkeypatch):
    """(1) The fixture changes the EXPECTED hash; no frozen producer is touched."""
    entries = [{"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "M",
                "content": "Tell me about weeknight cooking.",
                "timestamp": "2026-01-01T00:00:00Z", "selection_mode": "scripted"}]
    for i in range(6):
        entries.append({"turn": i + 2, "speaker_id": f"P{i % 3 + 1}",
                        "speaker_name": f"P{i % 3 + 1}",
                        "content": f"I cook most nights, usually quick things. {i}",
                        "timestamp": f"2026-01-01T00:0{i}:00Z",
                        "selection_mode": "model"})
    I.import_transcript(project, filename="syn.json",
                        content=json.dumps(entries).encode("utf-8"),
                        transcript_type="synthetic")
    window = W.confirm_whole_transcript(project, "syn",
                                        researcher_label="R. Lara",
                                        researcher_note="already trimmed")
    W.lock_window(project, window.window_id)
    DS.compute_for_assignment(project, "syn")

    stored = S.restore_results(project)[window.window_id]
    assert stored.freshness == S.FRESH
    assert stored.producer_identity_at_compute
    payload = S.load_structural(project, window.window_id)
    for key in ("producer_name", "producer_source_path", "producer_sha256",
                "producer_identity"):
        assert payload[key], key

    monkeypatch.setattr(S, "expected_producer_identity",
                        lambda side: "a.different.producer@deadbeefdeadbeef")
    after = S.restore_results(project)[window.window_id]
    assert after.freshness == S.STALE
    assert after.stale_reason == "the metric producer changed"
    assert window.window_id not in S.comparable_run_results(project)


def test_the_producer_fingerprint_runs_nothing():
    """Identity comes from reading source, not from computing a metric."""
    for side in ("human", "synthetic"):
        fingerprint = S.producer_fingerprint(side)
        assert len(fingerprint["producer_sha256"]) == 16
        assert fingerprint["producer_source_path"].endswith(".py")
    assert S.producer_fingerprint("synthetic") != S.producer_fingerprint("human")


# ================================================== A2 reviewer required
def test_locking_requires_a_researcher(project):
    """(2)"""
    I.import_transcript(project, filename="syn.json",
                        content=json.dumps([
                            {"turn": 1, "speaker_id": "P1", "speaker_name": "P1",
                             "content": "Something said here.",
                             "timestamp": "2026-01-01T00:00:00Z",
                             "selection_mode": "model"}]).encode("utf-8"),
                        transcript_type="synthetic")
    window = AW.build_window(
        window_id="syn__window_v001", source_transcript_id="syn",
        source_canonical_sha256=I.load_canonical(project,
                                                 "syn")["canonical_sha256"],
        side="synthetic", turns=I.load_canonical(project, "syn")["turns"])
    W.save_window(project, window)
    with pytest.raises(W.WindowServiceError, match="without a researcher"):
        W.lock_window(project, window.window_id)
    assert W.load_window(project, window.window_id).status == \
        AW.WindowStatus.PROPOSED.value


def test_a_confirmed_whole_transcript_needs_a_note(project):
    I.import_transcript(project, filename="syn.json",
                        content=json.dumps([
                            {"turn": 1, "speaker_id": "P1", "speaker_name": "P1",
                             "content": "Something said here.",
                             "timestamp": "2026-01-01T00:00:00Z",
                             "selection_mode": "model"}]).encode("utf-8"),
                        transcript_type="synthetic")
    window = W.confirm_whole_transcript(project, "syn",
                                        researcher_label="R. Lara",
                                        researcher_note="")
    with pytest.raises(W.WindowServiceError, match="needs a researcher note"):
        W.lock_window(project, window.window_id)
    W.lock_window(project, window.window_id,
                  researcher_note="the transcriber trimmed it at source")
    assert W.load_window(project, window.window_id).locked


# ================================================ A3 old declaration is inert
def test_the_upload_declaration_grants_nothing(project):
    """(3)"""
    I.import_transcript(project, filename="syn.json",
                        content=json.dumps([
                            {"turn": 1, "speaker_id": "P1", "speaker_name": "P1",
                             "content": "Something said here.",
                             "timestamp": "2026-01-01T00:00:00Z",
                             "selection_mode": "model"}]).encode("utf-8"),
                        transcript_type="synthetic",
                        window_declaration="comparable_window")
    state = W.window_state(project, "syn")
    assert state.window is None and not state.comparison_eligible
    assert state.namespace == AW.FULL_RUN_NAMESPACE

    from platform_core.services import design_service
    text = Path(design_service.__file__).read_text(encoding="utf-8")
    # eligibility is decided by the window state, never by the declaration
    assert "window_declaration" not in text.split("def eligibility_map")[1] \
        .split("def coverage")[0]


def test_the_declaration_is_labelled_as_not_a_reviewed_window():
    from app.views import new_evaluation
    text = Path(new_evaluation.__file__).read_text(encoding="utf-8")
    assert "Declared at upload — not a reviewed window" in text


# =========================================== A4 pagination, A5 diagnostics
def test_the_preview_pages_rather_than_truncating(project):
    """(4-adjacent) A long window is reviewed page by page, not silently cut."""
    entries = [{"turn": i + 1, "speaker_id": f"P{i % 4 + 1}",
                "speaker_name": f"P{i % 4 + 1}", "content": f"Turn number {i}.",
                "timestamp": "2026-01-01T00:00:00Z", "selection_mode": "model"}
               for i in range(120)]
    I.import_transcript(project, filename="long.json",
                        content=json.dumps(entries).encode("utf-8"),
                        transcript_type="synthetic")
    window = W.confirm_whole_transcript(project, "long",
                                        researcher_label="R. Lara",
                                        researcher_note="whole session")
    W.lock_window(project, window.window_id)

    first = W.preview(project, window.window_id, page=1, page_size=25)
    assert first["total_turns"] == 120 and first["total_pages"] == 5
    assert first["page"] == 1 and len(first["retained"]) == 25
    last = W.preview(project, window.window_id, page=5, page_size=25)
    assert len(last["retained"]) == 20            # 120 = 4 full pages + 20
    assert last["retained"][-1]["turn_id"] != first["retained"][-1]["turn_id"]
    beyond = W.preview(project, window.window_id, page=99, page_size=25)
    assert beyond["page"] == 5                      # clamped, not empty
    seen = {r["turn_id"] for page in range(1, 6)
            for r in W.preview(project, window.window_id, page=page,
                               page_size=25)["retained"]}
    assert len(seen) == 120                          # every turn is reachable


def test_window_diagnostics_never_block(project):
    """(4)"""
    for name, rounds in (("short", 2), ("long", 12)):
        entries = [{"turn": i + 1, "speaker_id": f"P{i % 4 + 1}",
                    "speaker_name": f"P{i % 4 + 1}",
                    "content": f"A sentence of some length here. {i}",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "selection_mode": "model"} for i in range(rounds * 4)]
        I.import_transcript(project, filename=f"{name}.json",
                            content=json.dumps(entries).encode("utf-8"),
                            transcript_type="synthetic")
        window = W.confirm_whole_transcript(project, name,
                                            researcher_label="R. Lara",
                                            researcher_note="whole session")
        W.lock_window(project, window.window_id)
        DS.compute_for_assignment(project, name)

    rows = W.window_diagnostics(project)
    assert len(rows) == 2
    assert {r.status for r in rows} == {"INFORMATIONAL"}      # no default threshold
    assert all(r.retained_turn_proportion == 1.0 for r in rows)
    assert sorted(r.n_retained_turns for r in rows) == [8, 48]
    assert all(r.participant_count == 4 for r in rows)

    # a threshold only exists if the researcher sets one, and it only suggests
    suggested = W.window_diagnostics(project,
                                     thresholds={"n_retained_turns_min": 20})
    statuses = {r.transcript_id: r.status for r in suggested}
    assert statuses["short"] == "REVIEW_SUGGESTED"
    assert statuses["long"] == "INFORMATIONAL"
    assert "BLOCKED" not in json.dumps([r.to_dict() for r in suggested])

    # and the comparison is unaffected either way
    assert all(W.window_state(project, r.transcript_id).comparison_eligible
               for r in rows)
    summary = W.diagnostics_summary(rows)
    assert summary and all(s["status"] == "INFORMATIONAL" for s in summary)


# ================================================== B1 the boundary holds
FORBIDDEN_IMPORTS = ("core.orchestrator", "core.participant_agent",
                     "core.moderator_brain", "ui.backend", "backend.api")
FORBIDDEN_CALLS = ("anthropic", "openai", "google.genai", "requests", "httpx")


def _generation_files():
    from platform_core import generation
    root = Path(generation.__file__).parent
    return sorted(root.glob("*.py"))


def test_the_adapter_never_imports_the_agent_architecture():
    """(5)"""
    for path in _generation_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(f)
                               for f in FORBIDDEN_IMPORTS), (path.name, node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(alias.name.startswith(f)
                                   for f in FORBIDDEN_IMPORTS), (path.name,
                                                                 alias.name)
        for forbidden in FORBIDDEN_IMPORTS + FORBIDDEN_CALLS:
            assert f"import {forbidden}" not in text, (path.name, forbidden)


def test_the_adapter_touches_no_private_name_of_core():
    for path in _generation_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                base = node.value
                name = getattr(base, "id", None) or getattr(base, "attr", "")
                assert name not in ("core", "orchestrator", "agent"), \
                    (path.name, node.attr)


def test_the_adapter_never_calls_a_provider():
    import sys
    for module in ("anthropic", "openai"):
        assert module not in sys.modules
    for path in _generation_files():
        text = path.read_text(encoding="utf-8").lower()
        assert "api.anthropic.com" not in text
        assert "messages.create" not in text


def test_the_only_entry_point_is_the_public_cli():
    assert GC.CLI_RELATIVE_PATH == "scripts/run_full_session.py"
    assert (REPO_ROOT / GC.CLI_RELATIVE_PATH).is_file()
    command = CB.cli_command(python_executable="py", cli_path="cli.py",
                             config_path="c.json", max_turns=40, mode="emergent")
    assert command == ["py", "cli.py", "--config", "c.json", "--max-turns", "40",
                       "--mode", "emergent"]


# ================================================== B5 the config contract
def test_the_compiled_config_matches_the_cli_contract(project, profiles, guide):
    """(6)"""
    study, plan, report = _plan(project, profiles, guide)
    assert report.ok, report.problems
    GP.write_configs(project, study, plan, profile_set=profiles, guide=guide)

    path = Path(plan.sessions[0].config_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in GC.REQUIRED_CONFIG_KEYS:
        assert key in config, key
    assert set(config) <= set(GC.PUBLIC_CONFIG_KEYS)
    assert config["session_id"] == plan.sessions[0].session_id
    assert len(config["discussion_guide"]) == 3
    # Phase 3E: participants travel INLINE so the config is portable
    assert all(set(p) == {"agent_payload"} for p in config["participants"])
    assert "seed" not in json.dumps(config).lower()

    effective = json.loads(
        path.with_suffix("").with_suffix(".effective_config.json")
        .read_text(encoding="utf-8"))
    from platform_core.generation import effective_config as GE
    names = {v["name"]: v for v in effective["values"]}
    assert names["session_id"]["provenance"] == GE.PLAN_FIXED
    assert names["moderator_model"]["provenance"] == GE.USER_SELECTED
    # Phase 3E: a resolved default carries its VALUE, not just a label
    assert names["temperature"]["provenance"] == GE.ARCHITECTURE_DEFAULT_RESOLVED
    assert names["temperature"]["value"] == GE.ARCHITECTURE_DEFAULTS["temperature"]
    assert effective["architecture_code_manifest_hash"]
    assert effective["command"][0]


def test_a_participant_may_not_mix_two_forms(project, profiles, guide):
    built = CB.build_session_config(
        _study(project), session_id="s", run_label="r",
        participants=[{"agent_payload_path": "a.json", "id": "x", "name": "X",
                       "profile_summary": "{}"}],
        discussion_guide=[{"section_index": 0}])
    assert not built.ok
    assert any("combined in one participant" in p for p in built.problems)


def test_the_platform_refuses_to_invent_a_config_key(project):
    built = CB.build_session_config(
        _study(project), session_id="s", run_label="r",
        participants=[{"agent_payload_path": "a.json"}],
        discussion_guide=[{"section_index": 0}])
    built.config["platform_special_option"] = True
    problems = CB._check_keys(built.config)
    assert any("not part of the public config contract" in p for p in problems)


# ================================================== B7 the dry run gate
def test_invalid_profiles_block_the_dry_run(project, guide, tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    profile_set = PS.uploaded_profile_set([bad])
    study, plan, report = _plan(project, profile_set, guide)
    assert not report.ok
    assert any(p["check"] == "profiles" for p in report.problems)
    assert plan.validation_status == GC.ValidationStatus.INVALID.value
    assert not plan.launchable


def test_an_invalid_guide_blocks_the_dry_run(project, profiles):
    guide = GP.compile_guide_text("sections:\n  - section_label: Only a label\n")
    assert not guide.ok
    study, plan, report = _plan(project, profiles, guide)
    assert not report.ok
    assert any(p["check"] == "discussion_guide" for p in report.problems)


def test_a_bad_phase_label_is_a_guide_error(project, profiles):
    guide = GP.compile_guide_text(GUIDE_YAML.replace("phase: intro",
                                                    "phase: warmup"))
    assert not guide.ok
    assert any("warmup" in p or "phase" in p.lower() for p in guide.problems)


def test_a_duplicate_session_id_blocks(project, profiles, guide, monkeypatch):
    """(9)"""
    monkeypatch.setattr(GP, "make_session_id",
                        lambda *a, **k: "always_the_same_id")
    study, plan, report = _plan(project, profiles, guide,
                                focus_groups=["fg1", "fg2"])
    assert not report.ok
    assert any("appears twice" in p["message"] for p in report.problems)


def test_an_existing_output_directory_blocks(project, profiles, guide, monkeypatch):
    existing = REPO_ROOT / "output" / "session_logs"
    names = [p.name for p in existing.iterdir()] if existing.is_dir() else []
    if not names:
        pytest.skip("no existing session log to collide with")
    monkeypatch.setattr(GP, "make_session_id", lambda *a, **k: names[0])
    study, plan, report = _plan(project, profiles, guide)
    assert not report.ok
    assert any("never reused" in p["message"] for p in report.problems)


def test_the_dry_run_makes_no_external_call(project, profiles, guide, monkeypatch):
    """(10)"""
    import socket
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError("the dry run attempted an external call")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(subprocess, "run", refuse)
    study, plan, report = _plan(project, profiles, guide)
    assert report.ok, report.problems
    assert report.made_external_calls is False


def test_the_dry_run_checks_credentials_without_reading_them(project, profiles,
                                                             guide):
    study = _study(project)
    plan = GP.build_plan(project, study, profile_set=profiles, guide=guide)
    report = GP.dry_run(project, study, plan, profile_set=profiles, guide=guide,
                        env={"ANTHROPIC_API_KEY": "sk-secret-value"})
    text = json.dumps(report.to_dict())
    assert "sk-secret-value" not in text
    credentials = next(c for c in report.checks if c["check"] == "credentials")
    # Phase 3E: presence is decided per provider, from the resolved models
    assert credentials["ok"]
    assert report.credentials["requirements"][0]["provider"] == "anthropic"
    assert report.credentials["requirements"][0]["status"] == "PRESENT"


def test_no_rate_table_means_no_invented_price(project, profiles, guide):
    study, plan, report = _plan(project, profiles, guide)
    assert report.cost_estimate.startswith("Cost estimate unavailable")
    assert report.ok                                  # and it does not block


def test_the_default_concurrency_is_one(project):
    """(13)"""
    assert GC.DEFAULT_CONCURRENCY == 1
    assert _study(project).concurrency_limit == 1
    assert GC.MAX_CONCURRENCY <= 4


def test_a_concurrency_above_the_ceiling_is_refused(project, profiles, guide):
    study, plan, report = _plan(project, profiles, guide, concurrency_limit=99)
    assert not report.ok
    assert any("concurrency_limit" in p["message"] for p in report.problems)


# =============================================== B8/B9 launching, fake spawn
class FakeSpawn:
    """A launcher that starts nothing. Records the call and invents a pid."""

    def __init__(self, pid=424242, start_time=1000.0):
        self.calls = []
        self.pid, self.start_time = pid, start_time

    def __call__(self, command, *, stdout_path, cwd):
        self.calls.append({"command": command, "stdout_path": stdout_path,
                           "cwd": cwd})
        Path(stdout_path).write_text("fake launcher\n", encoding="utf-8")
        return {"pid": self.pid, "process_start_time": self.start_time}


def _launchable(project, profiles, guide, **kwargs):
    study, plan, report = _plan(project, profiles, guide, **kwargs)
    assert report.ok, report.problems
    GP.write_configs(project, study, plan, profile_set=profiles, guide=guide)
    GP.save_plan(project, plan)
    return study, plan


def test_a_plan_is_not_launchable_until_the_dry_run_passes(project, profiles,
                                                           tmp_path):
    """(11)"""
    guide = GP.compile_guide_text("guide_id: g\ntitle: T\nsections: []")
    study = _study(project)
    plan = GP.build_plan(project, study, profile_set=profiles, guide=guide)
    assert not plan.launchable                       # NOT_VALIDATED by default
    with pytest.raises(GC.GenerationError, match="has not passed its dry-run"):
        GP.write_configs(project, study, plan, profile_set=profiles, guide=guide)


def test_launching_uses_an_argument_list_and_no_shell(project, profiles, guide):
    """(12)"""
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)

    command = spawn.calls[0]["command"]
    assert isinstance(command, list) and all(isinstance(c, str) for c in command)
    # Phase 3E: the launcher starts the WORKER; the worker starts the CLI
    assert command[1].endswith("worker.py")
    assert "--config" in command and "--max-turns" in command
    assert "--terminal-record" in command
    assert str(REPO_ROOT / "scripts" / "run_full_session.py") in command
    for source_path in (GL.__file__, GW.__file__):
        source = Path(source_path).read_text(encoding="utf-8")
        assert "shell=False" in source and "shell=True" not in source


def test_the_job_state_is_rebuilt_from_disk(project, profiles, guide):
    """(14) and (21): a restart loses nothing."""
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)

    # a fresh process would only have the files
    reloaded = GL.all_jobs(project)
    assert [j.job_id for j in reloaded] == [job.job_id]
    assert reloaded[0].pid == spawn.pid
    assert reloaded[0].command == job.command
    assert GL.job_for_session(project, plan.sessions[0].session_id).job_id == \
        job.job_id


def test_a_stranger_pid_is_not_adopted(project, profiles, guide):
    """(15)"""
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn(pid=999999, start_time=1000.0)
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)

    # same pid, different start time and command: somebody else's process
    stranger = {"pid": 999999, "create_time": 5000.0,
                "cmdline": ["python", "something_else.py"], "evidence": "psutil"}
    assert not GL.is_our_process(job, stranger)
    observed = GL.observe(project, job, signature_of=lambda pid: stranger)
    assert observed.status != GC.JobStatus.RUNNING.value

    ours = {"pid": 999999, "create_time": 1000.0,
            "cmdline": ["py", "worker.py", "--config", job.config_path,
                        "--terminal-record", job.terminal_record_path],
            "evidence": "psutil"}
    assert GL.is_our_process(job, ours)


def test_a_completed_run_needs_a_terminal_record(project, profiles, guide):
    """
    SUPERSEDED IN PHASE 3E. This used to assert that a transcript on disk meant
    COMPLETED. It does not: the architecture writes transcripts as it goes, so a
    crashed run leaves one behind too. Completion now requires the worker's record.
    """
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)

    output = Path(job.expected_output_directory)
    output.mkdir(parents=True, exist_ok=True)
    (output / "transcript.json").write_text(json.dumps([
        {"turn": 1, "speaker_id": "P1", "speaker_name": "P1",
         "content": "Said something.", "timestamp": "2026-01-01T00:00:00Z",
         "selection_mode": "model"}]), encoding="utf-8")
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status == GC.JobStatus.REQUIRES_RECOVERY.value
        assert "no terminal record" in observed.failure_reason

        record = GT.TerminalRecord(
            job_id=job.job_id, session_id=job.session_id, exit_code=0,
            termination_kind=GT.TerminationKind.NORMAL_EXIT.value,
            config_sha256=job.config_sha256, transcript_exists=True,
            transcript_parseable=True,
            completion_quality=GT.CompletionQuality.GUIDE_COMPLETED.value)
        Path(job.terminal_record_path).write_text(
            json.dumps(record.to_dict()), encoding="utf-8")
        again = GL.observe(project, GL.load_job(project, job.job_id),
                           signature_of=lambda pid: None)
        assert again.status == GC.JobStatus.COMPLETED.value
        assert again.completed_utc
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)


def test_a_failed_job_is_never_relaunched(project, profiles, guide):
    """(16)"""
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)
    job.status = GC.JobStatus.FAILED.value
    GL.save_job(project, job)

    assert job.relaunchable is False
    with pytest.raises(GC.GenerationError, match="never relaunched"):
        GL.launch(project, GL.load_job(project, job.job_id), spawn=spawn)
    assert len(spawn.calls) == 1


def test_an_orphaned_job_says_so_and_stops(project, profiles, guide):
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)
    observed = GL.observe(project, job, signature_of=lambda pid: None)
    assert observed.status == GC.JobStatus.ORPHANED.value
    assert "not relaunched automatically" in observed.failure_reason


def test_cancellation_keeps_the_artefacts(project, profiles, guide, monkeypatch):
    """(17)"""
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)

    output = Path(job.expected_output_directory)
    output.mkdir(parents=True, exist_ok=True)
    partial = output / "state_turn_3.json"
    partial.write_text(json.dumps({"session_meta": {"total_turns": 3}}),
                       encoding="utf-8")
    try:
        ours = {"pid": spawn.pid, "create_time": spawn.start_time,
                "cmdline": ["py", "worker.py", "--config", job.config_path,
                            "--terminal-record", job.terminal_record_path],
                "evidence": "psutil"}
        monkeypatch.setattr(GL, "process_signature", lambda pid: ours)
        monkeypatch.setattr(GL, "process_tree", lambda pid: [])
        killed = []
        with pytest.raises(GC.GenerationError, match="type the session id"):
            GL.cancel(project, job.job_id, confirm_session_id="wrong",
                      terminate=killed.append, signature_of=lambda pid: ours)
        assert not killed

        cancelled = GL.cancel(project, job.job_id,
                              confirm_session_id=job.session_id,
                              terminate=killed.append,
                              signature_of=lambda pid: ours)
        assert killed == [spawn.pid]
        assert cancelled.status == GC.JobStatus.CANCELLED.value
        assert partial.is_file()                      # artefacts kept
        assert "cost already incurred" in cancelled.failure_reason
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)


# ================================================ B10 monitoring, read-only
def test_progress_is_read_only_and_hides_secrets(tmp_path):
    output = tmp_path / "session"
    output.mkdir()
    (output / "state_turn_4.json").write_text(json.dumps({
        "session_meta": {"total_turns": 4, "current_section_index": 1,
                         "section_phase": "main_topic"},
        "transcript": [{"speaker_name": "Ana", "content": "hello"}],
        "moderator_system_prompt": "SECRET PROMPT TEXT"}), encoding="utf-8")
    (output / "api_calls.jsonl").write_text(
        '{"action":"participant","input_tokens":100,"output_tokens":40,"turn":1}\n'
        '{"action":"moderator","input_tokens":200,"output_tokens":60,"turn":2}\n',
        encoding="utf-8")
    stdout = tmp_path / "launcher_stdout.log"
    stdout.write_text("running turn 4\nANTHROPIC_API_KEY=sk-abcdef123456\n",
                      encoding="utf-8")

    before = {p.name: p.read_bytes() for p in output.iterdir()}
    progress = GM.read_progress(output, session_id="s", status="RUNNING",
                                stdout_path=stdout)
    assert progress.last_turn == 4 and progress.last_speaker == "Ana"
    assert progress.section_phase == "main_topic"
    assert progress.n_api_calls == 2
    assert progress.input_tokens == 300 and progress.output_tokens == 100
    assert "SECRET PROMPT TEXT" not in json.dumps(progress.to_dict())
    assert "sk-abcdef123456" not in json.dumps(progress.to_dict())
    assert "[redacted]" in " ".join(GM.stdout_tail(stdout))
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before

    ledger = GM.read_ledger(output)
    assert ledger.is_actual_usage and ledger.n_calls == 2
    assert ledger.by_action["moderator"]["output_tokens"] == 60


# ================================================= B12 importing outputs
def _completed_job(project, profiles, guide, entries=None):
    study, plan = _launchable(project, profiles, guide)
    spawn = FakeSpawn()
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    GL.launch(project, job, spawn=spawn)
    output = Path(job.expected_output_directory)
    output.mkdir(parents=True, exist_ok=True)
    payload = entries if entries is not None else [
        {"turn": i + 1, "speaker_id": "MODERATOR" if i == 0 else f"P{i % 3 + 1}",
         "speaker_name": "M" if i == 0 else f"P{i % 3 + 1}",
         "content": f"A line of dialogue number {i}.",
         "timestamp": "2026-01-01T00:00:00Z",
         "selection_mode": "scripted" if i == 0 else "model"} for i in range(9)]
    (output / "transcript.json").write_text(json.dumps(payload), encoding="utf-8")
    # Phase 3E: completion is proved by the worker's terminal record
    import hashlib as _hashlib
    record = GT.TerminalRecord(
        job_id=job.job_id, session_id=job.session_id, exit_code=0,
        termination_kind=GT.TerminationKind.NORMAL_EXIT.value,
        config_sha256=job.config_sha256, transcript_exists=True,
        transcript_parseable=True,
        transcript_sha256=_hashlib.sha256(
            (output / "transcript.json").read_bytes()).hexdigest(),
        completion_quality=GT.CompletionQuality.GUIDE_COMPLETED.value)
    Path(job.terminal_record_path).write_text(json.dumps(record.to_dict()),
                                              encoding="utf-8")
    job = GL.observe(project, job, signature_of=lambda pid: None)
    return study, plan, job, output


def test_an_unstable_transcript_is_not_imported(project, profiles, guide):
    """(18)"""
    study, plan, job, output = _completed_job(project, profiles, guide)
    try:
        path = output / "transcript.json"
        state = {"n": 0}

        def grow(_pause):
            state["n"] += 1
            path.write_text(json.dumps([{"turn": i} for i in range(state["n"])]),
                            encoding="utf-8")

        stable, reason = GI.transcript_is_stable(path, sleeper=grow)
        assert not stable and "still changing" in reason

        path.write_text("{ truncated", encoding="utf-8")
        stable, reason = GI.transcript_is_stable(path, sleeper=lambda _p: None)
        assert not stable and "not valid JSON" in reason

        outcome = GI.import_session_output(project, job, plan=plan,
                                           sleeper=lambda _p: None)
        assert not outcome.ok and outcome.problems
        assert I.stored_transcripts(project) == []
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)


def test_an_imported_output_is_not_comparable(project, profiles, guide):
    """(19)"""
    study, plan, job, output = _completed_job(project, profiles, guide)
    try:
        outcome = GI.import_session_output(project, job, plan=plan,
                                           sleeper=lambda _p: None)
        assert outcome.ok and outcome.comparable is False
        assert outcome.transcript_id == job.session_id
        assert len(outcome.transcript_sha256) == 64

        state = W.window_state(project, outcome.transcript_id)
        assert state.window is None
        assert not state.comparison_eligible
        assert W.all_windows(project) == []
        assert S.comparable_run_results(project) == {}
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)


def test_a_proposed_assignment_is_not_written_until_confirmed(project, profiles,
                                                              guide):
    """(20)"""
    study, plan, job, output = _completed_job(project, profiles, guide)
    try:
        outcome = GI.import_session_output(project, job, plan=plan,
                                           sleeper=lambda _p: None)
        proposal = outcome.proposed_assignment
        assert proposal["confirmed"] is False
        assert proposal["condition_id"] == plan.sessions[0].condition_id
        assert proposal["replicate_index"] == 1

        DS.save_design(project, GI.design_from_plan(project, plan,
                                                    study)["design"])
        assert DS.load_assignments(project) == []       # nothing written yet

        GI.confirm_assignment(project, proposal)
        assignments = DS.load_assignments(project)
        assert [a.transcript_id for a in assignments] == [outcome.transcript_id]
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)


def test_a_generated_output_never_replaces_silently(project, profiles, guide):
    study, plan, job, output = _completed_job(project, profiles, guide)
    try:
        with pytest.raises(GC.GenerationError, match="never replaces"):
            GI.import_session_output(
                project, job, plan=plan,
                on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED,
                sleeper=lambda _p: None)
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)


def test_a_design_from_a_plan_has_no_human_reference(project, profiles, guide):
    study, plan = _launchable(project, profiles, guide)
    bundle = GI.design_from_plan(project, plan, study)
    design = bundle["design"]
    assert [c.side for c in design.conditions] == [D.Side.SYNTHETIC.value]
    assert design.human_conditions == []
    assert "none is created" in bundle["human_reference"]
    assert len(bundle["expected_positions"]) == len(plan.sessions)


# =========================================================== D safety
def test_no_secret_is_written_into_the_project(project, profiles, guide):
    study, plan = _launchable(project, profiles, guide)
    for path in project.path.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "ANTHROPIC_API_KEY" not in text or "never" in text
            assert "sk-" not in text
    assert not (project.path / ".env").exists()


def test_the_repo_configs_directory_is_never_written(project, profiles, guide):
    before = sorted(p.name for p in (REPO_ROOT / "configs").iterdir())
    study, plan = _launchable(project, profiles, guide)
    after = sorted(p.name for p in (REPO_ROOT / "configs").iterdir())
    assert before == after
    assert str(GP.configs_dir(project)).startswith(str(project.path))


def test_the_frozen_benchmark_is_untouched(project, profiles, guide):
    """(22)"""
    def digests():
        return {k: hashlib.sha256(s.path.read_bytes()).hexdigest()
                for k, s in TH.SOURCES.items()}

    before = digests()
    study, plan = _launchable(project, profiles, guide)
    GP.dry_run(project, study, plan, profile_set=profiles, guide=guide,
               env={"ANTHROPIC_API_KEY": "x"})
    assert digests() == before

    from platform_core.services import benchmark_service as B
    assert B.check_sources()["ok"]
    assert len(B.level2_condition_summary()) == 7


def test_no_session_carries_anything_called_a_seed(project, profiles, guide):
    study, plan = _launchable(project, profiles, guide)
    text = json.dumps(plan.to_dict()).lower()
    for session in plan.sessions:
        assert "seed" not in json.dumps(session.to_dict()).lower()
    # the only legitimate seed selects a panel, and says what it means
    assert "panel_sampling_seed" in text
    assert "never a generation seed" in text


# ============================================================ the interface
def test_the_generation_view_is_separate_from_new_evaluation():
    """Generation controls never appear on an evaluation screen."""
    from app.views import generate, new_evaluation
    evaluation = Path(new_evaluation.__file__).read_text(encoding="utf-8")
    for control in ("Launch", "run_full_session", "dry_run", "GL.launch"):
        assert control not in evaluation, control
    generation = Path(generate.__file__).read_text(encoding="utf-8")
    assert "Start queue" in generation            # Phase 3E: a durable queue
    assert "Type `" in generation                 # explicit confirmation


def test_the_generation_view_renders():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=180)
    app.run()
    app.session_state["nav_request"] = "Generate focus groups"
    app.run()
    assert not app.exception, [str(e) for e in app.exception]
    assert app.title[0].value == "Generate focus groups"
    # without an open project it asks for one rather than showing launch controls
    assert any("project" in i.value.lower() for i in app.info)
    assert not app.button


def test_the_interface_never_launches_without_confirmation():
    from app.views import generate
    text = Path(generate.__file__).read_text(encoding="utf-8")
    assert "typed.strip() != plan.plan_id" in text
    assert "disabled=typed.strip() != target" in text     # cancellation too
