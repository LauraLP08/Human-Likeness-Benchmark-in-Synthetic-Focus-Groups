"""
Phase 3E: generation reliability closure.

NO PROVIDER IS CALLED AND NO SESSION IS RUN. Every launch goes through a fake spawn
that writes a terminal record instead of starting anything.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from platform_core import thematic as TH
from platform_core.config import REPO_ROOT, resolve_data_dir
from platform_core.generation import (bundle as GB, contracts as GC,
                                      credentials as GCRED,
                                      effective_config as GE, importer as GI,
                                      launcher as GL, planner as GP,
                                      pricing_ledger as GPL, preflight as GPF,
                                      profiles_source as PS, queue as GQ,
                                      terminal as GT, worker as GW)
from platform_core.services import import_service as I, window_service as W

GUIDE_YAML = """
guide_id: weeknight_guide_v1
title: Weeknight cooking
sections:
  - label: Warm up
    phase: intro
    scripted_question: To start, what does a normal weeknight dinner look like?
    suggested_probes:
      - Who usually cooks?
  - label: Everyday choices
    phase: main_topic
    scripted_question: Walk me through deciding what to cook last Tuesday.
    suggested_probes:
      - What made that easy or hard?
  - label: Closing
    phase: closing
    scripted_question: Is there anything we have not covered?
    suggested_probes:
      - Anything we missed?
"""

TRANSCRIPT = [
    {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
     "content": "To start, what does a normal weeknight dinner look like?",
     "timestamp": "2026-01-01T18:00:00Z", "selection_mode": "scripted"},
] + [
    {"turn": i + 2, "speaker_id": f"P{i % 4 + 1}", "speaker_name": f"P{i % 4 + 1}",
     "content": f"I keep a rotation of about five meals I can do easily. ({i})",
     "timestamp": f"2026-01-01T18:{i + 1:02d}:00Z", "selection_mode": "model"}
    for i in range(8)
]


@pytest.fixture()
def data_dir(tmp_path):
    return resolve_data_dir(injected=tmp_path / "platform-data", ensure=True)


@pytest.fixture()
def project(data_dir):
    return I.new_project("Reliability", data_dir)


@pytest.fixture()
def profiles(tmp_path):
    paths = []
    for name in ("ana", "ben", "cara", "dan"):
        payload = {"schema_version": "fg_agents_v1", "agent_id": f"p_{name}",
                   "language": "en",
                   "persona": {"demographics": {"name": name.title(), "age": 34,
                                                "gender": "man"}},
                   "simulation_config": {"model": "claude-haiku-4-5-20251001"}}
        path = tmp_path / f"p_{name}.json"
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        paths.append(path)
    return PS.uploaded_profile_set(paths)


@pytest.fixture()
def guide():
    return GP.compile_guide_text(GUIDE_YAML)


ENV = {"ANTHROPIC_API_KEY": "sk-test-not-real"}


def _study(project, **kwargs):
    defaults = dict(
        generation_study_id="weeknight", project_id=project.project_id,
        research_objective="How men in the UK make everyday food choices.",
        topic_domain="Food choice and everyday cooking",
        participant_collective_identity="Men in the UK reflecting on food choices",
        moderator_knowledge_brief="Explore how weeknight food decisions get made.",
        synthetic_conditions=["condition-a"], focus_groups=["fg1"], replicates=1,
        participation_mode="emergent", max_turns=40, created_utc="2026-08-05")
    defaults.update(kwargs)
    return GC.GenerationStudy(**defaults)


def _confirmed(project, profiles, guide, **kwargs):
    study = _study(project, **kwargs)
    GP.save_study(project, study)
    plan = GP.build_plan(project, study, profile_set=profiles, guide=guide)
    report = GP.dry_run(project, study, plan, profile_set=profiles, guide=guide,
                        env=ENV)
    plan = GP.confirmed_plan(plan, report)
    assert report.ok, report.problems
    GP.write_configs(project, study, plan, profile_set=profiles, guide=guide)
    GP.save_plan(project, plan)
    return study, plan


class FakeWorker:
    """
    A launcher that starts nothing and writes the terminal record itself.

    It stands in for the real worker: the platform's job is to read durable evidence,
    and this produces evidence without producing a session.
    """

    def __init__(self, *, exit_code=0, quality=GT.CompletionQuality.GUIDE_COMPLETED,
                 write_transcript=True, write_record=True, transcript=None,
                 pid=515001, start_time=2000.0, config_sha256=None):
        self.exit_code = exit_code
        self.quality = quality
        self.write_transcript = write_transcript
        self.write_record = write_record
        self.transcript = TRANSCRIPT if transcript is None else transcript
        self.pid, self.start_time = pid, start_time
        self.config_sha256 = config_sha256
        self.calls = []

    def __call__(self, command, *, stdout_path, cwd):
        self.calls.append({"command": command, "cwd": cwd})
        arguments = dict(zip(command[2::2], command[3::2]))
        output = Path(arguments["--output-dir"])
        record_path = Path(arguments["--terminal-record"])
        output.mkdir(parents=True, exist_ok=True)

        transcript_sha = ""
        if self.write_transcript:
            target = output / "transcript.json"
            target.write_text(json.dumps(self.transcript), encoding="utf-8")
            transcript_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        # The real ledger names the model and the role on every BILLED entry, and
        # writes zero-token decision summaries that carry an `action` instead.
        entries = [{"event_type": "moderator_decision_attempt", "role": "moderator",
                    "model": "claude-sonnet-4-6", "input_tokens": 800,
                    "output_tokens": 200, "turn": 0}]
        entries += [{"event_type": "participant_response", "role": "participant",
                     "model": "claude-haiku-4-5-20251001", "input_tokens": 800,
                     "output_tokens": 200, "participant_id": f"p{i}", "turn": i}
                    for i in range(8)]
        entries += [{"event_type": "moderator_decision", "action": "ask_followup",
                     "role": "moderator", "turn": 1}]   # no tokens: not a call
        (output / "api_calls.jsonl").write_text(
            "\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        Path(stdout_path).write_text(
            "Guide completed naturally after 9 steps (total_turns=9)."
            if self.quality is GT.CompletionQuality.GUIDE_COMPLETED else
            "SAFETY CAP HIT at 40 steps — 2/3 sections completed",
            encoding="utf-8")

        if self.write_record:
            parseable = bool(self.write_transcript
                             and self.quality is not
                             GT.CompletionQuality.INVALID_OUTPUT)
            record = GT.TerminalRecord(
                job_id=arguments["--job-id"], session_id=arguments["--session-id"],
                worker_pid=self.pid, cli_pid=self.pid + 1, command=list(command),
                config_path=arguments["--config"],
                config_sha256=self.config_sha256 or arguments["--config-sha256"],
                started_utc="2026-08-05T00:00:00Z",
                completed_utc="2026-08-05T00:05:00Z", exit_code=self.exit_code,
                termination_kind=(GT.TerminationKind.NORMAL_EXIT.value
                                  if self.exit_code == 0
                                  else GT.TerminationKind.NONZERO_EXIT.value),
                transcript_exists=self.write_transcript,
                transcript_sha256=transcript_sha,
                transcript_parseable=parseable,
                max_turns_reached=(self.quality is
                                   GT.CompletionQuality.MAX_TURNS_REACHED),
                completion_quality=self.quality.value)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(json.dumps(record.to_dict()), encoding="utf-8")
        return {"pid": self.pid, "process_start_time": self.start_time}


def _launch(project, plan, study, worker, session_index=0):
    session = plan.sessions[session_index]
    job = GL.build_job(project, plan, session.session_id,
                       max_turns=study.max_turns, mode=study.participation_mode,
                       effective_config_sha256=plan.effective_config_hashes.get(
                           session.session_id, ""),
                       architecture_code_manifest_hash=(
                           plan.architecture_code_manifest_hash))
    GL.launch(project, job, spawn=worker)
    return job


def _cleanup(job):
    shutil.rmtree(Path(job.expected_output_directory), ignore_errors=True)


# ============================================ 1 terminal evidence is required
def test_a_transcript_without_a_terminal_record_is_not_completed(project, profiles,
                                                                 guide):
    """(1)"""
    study, plan = _confirmed(project, profiles, guide)
    worker = FakeWorker(write_record=False)
    job = _launch(project, plan, study, worker)
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status != GC.JobStatus.COMPLETED.value
        assert observed.status == GC.JobStatus.REQUIRES_RECOVERY.value
        assert "no terminal record" in observed.failure_reason
        assert (Path(job.expected_output_directory) / "transcript.json").is_file()
    finally:
        _cleanup(job)


def test_a_nonzero_exit_is_failed_even_with_a_transcript(project, profiles, guide):
    """(2)"""
    study, plan = _confirmed(project, profiles, guide)
    worker = FakeWorker(exit_code=1)
    job = _launch(project, plan, study, worker)
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status == GC.JobStatus.FAILED.value
        assert observed.exit_code == 1
        assert (Path(job.expected_output_directory) / "transcript.json").is_file()
    finally:
        _cleanup(job)


def test_exit_zero_over_an_unparseable_transcript_is_not_completed(project, profiles,
                                                                   guide):
    """(3)"""
    study, plan = _confirmed(project, profiles, guide)
    worker = FakeWorker(quality=GT.CompletionQuality.INVALID_OUTPUT)
    job = _launch(project, plan, study, worker)
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status == GC.JobStatus.FAILED.value
        assert "does not parse" in observed.failure_reason
    finally:
        _cleanup(job)


def test_guide_completed_and_max_turns_are_distinguished(project, profiles, guide):
    """(4)"""
    study, plan = _confirmed(project, profiles, guide)
    clean = FakeWorker()
    job = _launch(project, plan, study, clean)
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status == GC.JobStatus.COMPLETED.value
        assert observed.completion_quality == \
            GT.CompletionQuality.GUIDE_COMPLETED.value
        record = GL.terminal_record_for(observed)
        assert record.usable_output and not record.potentially_incomplete
    finally:
        _cleanup(job)

    # the same shape, capped
    capped_output = GT.inspect_output(
        Path(job.expected_output_directory),
        "SAFETY CAP HIT at 40 steps — 2/3 sections completed")
    assert capped_output["max_turns_reached"] is True


def test_the_worker_marks_a_capped_run_as_potentially_incomplete(project, profiles,
                                                                 guide):
    study, plan = _confirmed(project, profiles, guide)
    worker = FakeWorker(quality=GT.CompletionQuality.MAX_TURNS_REACHED)
    job = _launch(project, plan, study, worker)
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status == GC.JobStatus.COMPLETED.value
        assert observed.completion_quality == \
            GT.CompletionQuality.MAX_TURNS_REACHED.value
        record = GL.terminal_record_for(observed)
        assert record.usable_output and record.potentially_incomplete
    finally:
        _cleanup(job)


def test_the_worker_module_writes_a_record_without_the_platform(tmp_path):
    """The worker is stdlib-only and does not import the application."""
    import ast
    source = Path(GW.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, "the worker must not use relative imports"
            imported.add((node.module or "").split(".")[0])
    assert "platform_core" not in imported
    assert imported <= {"argparse", "hashlib", "json", "os", "re", "subprocess",
                        "sys", "tempfile", "datetime", "pathlib", "__future__"}
    assert "shell=False" in source and "shell=True" not in source

    config = tmp_path / "c.json"
    config.write_text(json.dumps({"session_id": "s"}), encoding="utf-8")
    wrong = "0" * 64
    record_path = tmp_path / "terminal_record.json"
    exit_code = GW.main([
        "--job-id", "j", "--session-id", "s", "--config", str(config),
        "--config-sha256", wrong, "--cli", str(tmp_path / "cli.py"),
        "--max-turns", "5", "--output-dir", str(tmp_path / "out"),
        "--terminal-record", str(record_path),
        "--stdout", str(tmp_path / "stdout.log")])
    assert exit_code == 0
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["termination_kind"] == "PROCESS_LOST"
    assert "changed after the plan was confirmed" in record["failure_reason"]
    assert not (tmp_path / "out").exists()          # nothing was launched


# =========================================== 5-8 launch-time hash verification
def test_a_config_changed_after_the_dry_run_blocks(project, profiles, guide):
    """(5)"""
    study, plan = _confirmed(project, profiles, guide)
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode,
                       effective_config_sha256=plan.effective_config_hashes[
                           plan.sessions[0].session_id],
                       architecture_code_manifest_hash=(
                           plan.architecture_code_manifest_hash))
    assert GPF.verify_before_launch(project, job, plan=plan, env=ENV)["ok"]

    config_path = Path(job.config_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["research_objective"] = "something else entirely"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    report = GPF.verify_before_launch(project, job, plan=plan, env=ENV)
    assert not report["ok"]
    assert any(p["check"] == "config_hash" for p in report["problems"])
    assert any("changed after confirmation" in p["message"]
               for p in report["problems"])


def test_a_changed_profile_blocks_after_confirmation(project, profiles, guide):
    """(6)"""
    study, plan = _confirmed(project, profiles, guide)
    bundled = GB.bundled_profile_path(project, plan.plan_id, "p_ana")
    payload = json.loads(bundled.read_text(encoding="utf-8"))
    payload["persona"]["demographics"]["age"] = 99
    bundled.write_text(json.dumps(payload), encoding="utf-8")

    verification = GB.verify(project, plan.plan_id)
    assert not verification.ok
    assert any(p["kind"] == "profile" for p in verification.problems)

    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    report = GPF.verify_before_launch(project, job, plan=plan, env=ENV)
    assert not report["ok"]
    assert any(p["check"] == "profile_hashes" for p in report["problems"])


def test_a_changed_guide_blocks_after_confirmation(project, profiles, guide):
    """(7)"""
    study, plan = _confirmed(project, profiles, guide)
    bundled = GB.bundle_dir(project, plan.plan_id) / "guide" / "original.yaml"
    bundled.write_text(GUIDE_YAML + "\n# edited after confirmation\n",
                       encoding="utf-8")
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    report = GPF.verify_before_launch(project, job, plan=plan, env=ENV)
    assert not report["ok"]
    assert any(p["check"] == "guide_hashes" for p in report["problems"])


def test_a_changed_architecture_blocks(project, profiles, guide):
    """(8)"""
    study, plan = _confirmed(project, profiles, guide)
    manifest = GB.load_manifest(project, plan.plan_id)
    manifest.immutable = False
    manifest.architecture_code_manifest_hash = "f" * 64
    GB.write_manifest(project, manifest)
    GB.confirm(project, manifest)

    verification = GB.verify(
        project, plan.plan_id,
        architecture_code_manifest_hash=GE.architecture_code_manifest_hash())
    assert not verification.ok
    assert any(p["where"] == "architecture" for p in verification.problems)
    assert any("Create or reconfirm a plan" in p["message"]
               for p in verification.problems)

    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    report = GPF.verify_before_launch(project, job, plan=plan, env=ENV)
    assert not report["ok"]
    assert any(p["check"] == "architecture_manifest" for p in report["problems"])


# ================================================ 9-12 the bundle
def test_a_confirmed_bundle_is_immutable(project, profiles, guide):
    """(9)"""
    study, plan = _confirmed(project, profiles, guide)
    manifest = GB.load_manifest(project, plan.plan_id)
    assert manifest.immutable and manifest.confirmed_utc

    with pytest.raises(GC.GenerationError, match="immutable"):
        GB.add_config(project, manifest, session_id="x", config={},
                      effective_config={})
    with pytest.raises(GC.GenerationError, match="immutable"):
        GB.build_bundle(project, plan_id=plan.plan_id,
                        generation_study_id="x", guide_yaml="y",
                        guide_compiled=[], profile_paths=[],
                        architecture_code_manifest_hash="z")


def test_the_bundle_keeps_profile_bytes_exactly(project, profiles, guide):
    """(10)"""
    study, plan = _confirmed(project, profiles, guide)
    for record in profiles.records:
        original = Path(record.source_path).read_bytes()
        bundled = GB.bundled_profile_path(project, plan.plan_id, record.agent_id)
        assert bundled.read_bytes() == original          # byte for byte
        manifest = GB.load_manifest(project, plan.plan_id)
        dependency = manifest.dependency(f"profiles/{record.agent_id}.json")
        assert dependency.raw_sha256 == hashlib.sha256(original).hexdigest()
        assert dependency.semantic_sha256
        assert dependency.source_path == str(record.source_path)


def test_the_config_does_not_depend_on_an_external_absolute_path(project, profiles,
                                                                 guide, tmp_path):
    """(11)"""
    study, plan = _confirmed(project, profiles, guide)
    config = json.loads(Path(plan.sessions[0].config_path).read_text(
        encoding="utf-8"))
    for participant in config["participants"]:
        assert set(participant) == {"agent_payload"}     # inline, portable
        assert participant["agent_payload"]["agent_id"].startswith("p_")
    text = json.dumps(config)
    assert str(tmp_path) not in text                     # no upload path survives
    assert "agent_payload_path" not in text

    # deleting the original uploads changes nothing about the config
    for record in profiles.records:
        Path(record.source_path).unlink()
    again = json.loads(Path(plan.sessions[0].config_path).read_text(
        encoding="utf-8"))
    assert again == config


def test_the_same_plan_keeps_its_effective_configuration(project, profiles, guide):
    """(12)"""
    study, plan = _confirmed(project, profiles, guide)
    session_id = plan.sessions[0].session_id
    path = Path(plan.sessions[0].config_path).with_suffix("").with_suffix(
        ".effective_config.json")
    effective = json.loads(path.read_text(encoding="utf-8"))

    names = {v["name"]: v for v in effective["values"]}
    assert names["temperature"]["provenance"] == GE.ARCHITECTURE_DEFAULT_RESOLVED
    assert names["temperature"]["value"] == GE.ARCHITECTURE_DEFAULTS["temperature"]
    assert names["moderator_model"]["provenance"] == GE.USER_SELECTED
    assert names["participant_models"]["provenance"] == GE.PROFILE_SELECTED
    assert effective["per_agent_models"]["p_ana"]["model"] == \
        "claude-haiku-4-5-20251001"
    assert effective["architecture_code_manifest_hash"]
    assert effective["effective_config_sha256"] == \
        plan.effective_config_hashes[session_id]

    # a resolved default carries its VALUE, not just a label
    for value in effective["values"]:
        if value["provenance"] == GE.ARCHITECTURE_DEFAULT_RESOLVED:
            assert value["value"] is not None

    # and nothing here fixes a response length: the only mentions of a word count
    # are the notes saying none is imposed
    text = json.dumps(effective).lower()
    for fragment in text.split('"'):
        if "word" in fragment:
            assert "no word count is imposed" in fragment, fragment
    assert "max_words" not in text and "word_limit" not in text
    assert "target_length" not in text


# ================================================ 13-15 credentials
def test_an_empty_dotenv_does_not_satisfy_credentials(tmp_path):
    """(13)"""
    dotenv = tmp_path / ".env"
    dotenv.write_text("\n# nothing useful here\n", encoding="utf-8")
    report = GCRED.check(moderator_model="claude-sonnet-4-6",
                         agent_models={"a": "claude-haiku-4-5-20251001"},
                         env={}, dotenv_path=dotenv)
    assert not report.ok
    assert report.dotenv_present is True             # the file exists...
    assert report.missing[0].provider == "anthropic"
    assert report.missing[0].missing_variables == ["ANTHROPIC_API_KEY"]

    dotenv.write_text("ANTHROPIC_API_KEY=\n", encoding="utf-8")
    assert not GCRED.check(moderator_model="claude-sonnet-4-6", agent_models={},
                           env={}, dotenv_path=dotenv).ok

    dotenv.write_text('export ANTHROPIC_API_KEY="sk-value"\n', encoding="utf-8")
    ok = GCRED.check(moderator_model="claude-sonnet-4-6", agent_models={},
                     env={}, dotenv_path=dotenv)
    assert ok.ok and ok.requirements[0].source == GCRED.DOTENV


def test_the_wrong_providers_credential_does_not_satisfy(tmp_path):
    """(14)"""
    report = GCRED.check(moderator_model="gpt-4o",
                         agent_models={"a": "claude-haiku-4-5-20251001"},
                         env={"ANTHROPIC_API_KEY": "sk-anthropic"},
                         dotenv_path=tmp_path / "absent.env")
    providers = {r.provider: r for r in report.requirements}
    assert providers["anthropic"].ok
    assert not providers["openai"].ok
    assert providers["openai"].missing_variables == ["OPENAI_API_KEY"]
    assert "moderator (gpt-4o)" in providers["openai"].used_by
    assert not report.ok


def test_no_secret_appears_in_any_report(project, profiles, guide, tmp_path):
    """(15)"""
    dotenv = tmp_path / ".env"
    dotenv.write_text("ANTHROPIC_API_KEY=sk-super-secret-value\n", encoding="utf-8")
    credential_report = GCRED.check(
        moderator_model="claude-sonnet-4-6",
        agent_models={"a": "claude-haiku-4-5-20251001"}, env={},
        dotenv_path=dotenv)
    assert "sk-super-secret-value" not in json.dumps(credential_report.to_dict())

    study = _study(project)
    GP.save_study(project, study)
    plan = GP.build_plan(project, study, profile_set=profiles, guide=guide)
    report = GP.dry_run(project, study, plan, profile_set=profiles, guide=guide,
                        env={"ANTHROPIC_API_KEY": "sk-super-secret-value"})
    text = json.dumps(report.to_dict())
    assert "sk-super-secret-value" not in text
    # not even a hash of it
    assert hashlib.sha256(b"sk-super-secret-value").hexdigest() not in text


def test_an_unknown_provider_is_not_assumed_to_be_anthropic():
    report = GCRED.check(moderator_model="some-local-model-v2", agent_models={},
                         env={"ANTHROPIC_API_KEY": "x"}, dotenv_path=Path("absent"))
    assert not report.ok
    assert report.requirements[0].provider == "unknown"


# ================================================ 16-18 atomic import
def test_the_importer_writes_nothing_before_the_collision_is_resolved(
        project, profiles, guide):
    """(16) and (17)"""
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker())
    try:
        job = GL.observe(project, job, signature_of=lambda pid: None)
        first = GI.import_session_output(project, job, plan=plan,
                                         sleeper=lambda _p: None)
        assert first.ok
        before = {p: p.read_bytes() for p in project.path.rglob("*")
                  if p.is_file()}

        second = GI.import_session_output(project, job, plan=plan,
                                          sleeper=lambda _p: None)
        assert not second.ok
        assert any("already exists" in p for p in second.problems)
        after = {p: p.read_bytes() for p in project.path.rglob("*") if p.is_file()}
        changed = {p for p in before if p in after and before[p] != after[p]}
        # only the append-only audit log may differ
        assert all(p.name == "audit_log.jsonl" for p in changed), changed
        assert set(before) - set(after) == set()
        new_files = set(after) - set(before)
        assert not [p for p in new_files
                    if "staging" not in str(p) and p.name != "audit_log.jsonl"]
    finally:
        _cleanup(job)


def test_new_version_keeps_both_generated_imports(project, profiles, guide):
    """(18)"""
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker())
    try:
        job = GL.observe(project, job, signature_of=lambda pid: None)
        first = GI.import_session_output(project, job, plan=plan,
                                         sleeper=lambda _p: None)
        second = GI.import_session_output(
            project, job, plan=plan,
            on_collision=I.CollisionPolicy.NEW_VERSION, sleeper=lambda _p: None)
        assert first.ok and second.ok
        assert second.transcript_id.endswith("__v002")
        ids = sorted(t["transcript_id"] for t in I.stored_transcripts(project))
        assert ids == [first.transcript_id, second.transcript_id]
    finally:
        _cleanup(job)


def test_an_import_without_terminal_evidence_is_refused(project, profiles, guide):
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker(write_record=False))
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        outcome = GI.import_session_output(project, observed, plan=plan,
                                           sleeper=lambda _p: None)
        assert not outcome.ok
        assert I.stored_transcripts(project) == []
    finally:
        _cleanup(job)


def test_a_capped_session_imports_with_a_reinforced_confirmation(project, profiles,
                                                                 guide):
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study,
                  FakeWorker(quality=GT.CompletionQuality.MAX_TURNS_REACHED))
    try:
        job = GL.observe(project, job, signature_of=lambda pid: None)
        outcome = GI.import_session_output(project, job, plan=plan,
                                           sleeper=lambda _p: None)
        assert outcome.ok
        assert outcome.generated_session_completeness == "MAX_TURNS_REACHED"
        assert outcome.requires_reinforced_confirmation
        assert "potentially incomplete" in outcome.note

        from platform_core.services import design_service as DS
        DS.save_design(project, GI.design_from_plan(project, plan,
                                                    study)["design"])
        with pytest.raises(GC.GenerationError, match="type its transcript id"):
            GI.confirm_assignment(project, outcome.proposed_assignment)
        GI.confirm_assignment(project, outcome.proposed_assignment,
                              reinforced_confirmation=outcome.transcript_id)
        assert DS.load_assignments(project)
    finally:
        _cleanup(job)


def test_an_imported_generated_output_is_still_not_comparable(project, profiles,
                                                              guide):
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker())
    try:
        job = GL.observe(project, job, signature_of=lambda pid: None)
        outcome = GI.import_session_output(project, job, plan=plan,
                                           sleeper=lambda _p: None)
        assert outcome.ok and not outcome.comparable
        assert W.all_windows(project) == []
        assert not W.window_state(project,
                                  outcome.transcript_id).comparison_eligible
    finally:
        _cleanup(job)


# ================================================ 19-23 the queue
def test_the_queue_never_exceeds_the_concurrency_limit(project, profiles, guide):
    """(19)"""
    study, plan = _confirmed(project, profiles, guide,
                             focus_groups=["fg1", "fg2", "fg3", "fg4"],
                             concurrency_limit=2)
    GQ.build_queue(project, plan, concurrency_limit=2, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)

    worker = FakeWorker(write_record=False, write_transcript=False)
    alive = {"pids": set()}

    def signature_of(pid):
        if pid in alive["pids"]:
            job = next(j for j in GL.all_jobs(project) if j.pid == pid)
            return {"pid": pid, "create_time": worker.start_time,
                    "cmdline": ["py", "worker.py", "--config", job.config_path,
                                "--terminal-record", job.terminal_record_path],
                    "evidence": "psutil"}
        return None

    def spawn(command, *, stdout_path, cwd):
        result = worker(command, stdout_path=stdout_path, cwd=cwd)
        worker.pid += 1
        alive["pids"].add(result["pid"])
        return result

    try:
        first = GQ.tick(project, spawn=spawn, signature_of=signature_of)
        assert len(first.launched) == 2
        assert first.occupied_slots == 2 and first.available_slots == 0

        second = GQ.tick(project, spawn=spawn, signature_of=signature_of)
        assert second.launched == []                  # still full
        assert second.occupied_slots == 2

        # one finishes
        finished = GL.load_job(project, first.launched[0])
        alive["pids"].discard(finished.pid)
        GT_record = GT.TerminalRecord(
            job_id=finished.job_id, session_id=finished.session_id, exit_code=0,
            termination_kind=GT.TerminationKind.NORMAL_EXIT.value,
            transcript_exists=True, transcript_parseable=True,
            config_sha256=finished.config_sha256,
            completion_quality=GT.CompletionQuality.GUIDE_COMPLETED.value)
        Path(finished.terminal_record_path).write_text(
            json.dumps(GT_record.to_dict()), encoding="utf-8")

        third = GQ.tick(project, spawn=spawn, signature_of=signature_of)
        assert len(third.launched) == 1               # exactly one slot opened
        assert third.occupied_slots == 2
        running = [j for j in GL.observe_all(project, signature_of=signature_of)
                   if j.status in GQ.OCCUPYING]
        assert len(running) <= 2
    finally:
        for job in GL.all_jobs(project):
            _cleanup(job)


def test_a_restart_rebuilds_the_queue_from_disk(project, profiles, guide):
    """(20)"""
    study, plan = _confirmed(project, profiles, guide, focus_groups=["fg1", "fg2"])
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)

    # a "fresh process" holds nothing but the files
    record = GQ.load_queue(project)
    assert record.plan_id == plan.plan_id
    assert len(record.ordered_job_ids) == 2
    assert record.queue_status == GQ.QueueStatus.RUNNING.value
    assert [j.status for j in GL.all_jobs(project)] == ["PENDING", "PENDING"]


def test_pause_does_not_cancel_a_running_job(project, profiles, guide):
    """(21)"""
    study, plan = _confirmed(project, profiles, guide, focus_groups=["fg1", "fg2"])
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)

    worker = FakeWorker(write_record=False, write_transcript=False)
    alive = set()

    def signature_of(pid):
        if pid in alive:
            job = next(j for j in GL.all_jobs(project) if j.pid == pid)
            return {"pid": pid, "create_time": worker.start_time,
                    "cmdline": ["py", "worker.py", "--config", job.config_path,
                                "--terminal-record", job.terminal_record_path],
                    "evidence": "psutil"}
        return None

    def spawn(command, *, stdout_path, cwd):
        result = worker(command, stdout_path=stdout_path, cwd=cwd)
        alive.add(result["pid"])
        return result

    try:
        first = GQ.tick(project, spawn=spawn, signature_of=signature_of)
        assert len(first.launched) == 1
        running_id = first.launched[0]

        GQ.pause(project)
        paused = GQ.tick(project, spawn=spawn, signature_of=signature_of)
        assert paused.launched == []
        assert paused.paused is True
        still = GL.observe(project, GL.load_job(project, running_id),
                           signature_of=signature_of)
        assert still.status == GC.JobStatus.RUNNING.value   # untouched
        assert not still.cancelled_by_user

        GQ.resume(project)
        assert GQ.load_queue(project).queue_status == GQ.QueueStatus.RUNNING.value
    finally:
        for job in GL.all_jobs(project):
            _cleanup(job)


def test_the_queue_never_relaunches_a_terminal_job(project, profiles, guide):
    """(22)"""
    study, plan = _confirmed(project, profiles, guide)
    GQ.build_queue(project, plan, concurrency_limit=2, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)

    job = GL.load_job(project, GQ.load_queue(project).ordered_job_ids[0])
    for status in (GC.JobStatus.FAILED.value, GC.JobStatus.CANCELLED.value,
                   GC.JobStatus.ORPHANED.value, GC.JobStatus.COMPLETED.value):
        job.status = status
        GL.save_job(project, job)
        calls = []
        result = GQ.tick(project, spawn=lambda *a, **k: calls.append(a) or
                         {"pid": 1, "process_start_time": 1.0},
                         signature_of=lambda pid: None)
        assert result.launched == [], status
        assert calls == [], status


def test_an_abandoned_launching_job_is_resolved(project, profiles, guide):
    """(23)"""
    study, plan = _confirmed(project, profiles, guide)
    job = GL.build_job(project, plan, plan.sessions[0].session_id,
                       max_turns=study.max_turns, mode=study.participation_mode)
    job.status = GC.JobStatus.LAUNCHING.value
    job.launch_attempt_id = "abc123"
    job.launch_attempt_utc = "2020-01-01T00:00:00+00:00"
    job.pid = 999999
    GL.save_job(project, job)

    # inside the timeout it stays LAUNCHING rather than being declared dead early
    fresh = GL.build_job(project, plan, plan.sessions[0].session_id,
                         max_turns=study.max_turns, mode=study.participation_mode)
    fresh.job_id = "job__fresh_attempt"
    fresh.status = GC.JobStatus.LAUNCHING.value
    fresh.launch_attempt_utc = GL._now()
    GL.save_job(project, fresh)
    assert GL.observe(project, fresh, signature_of=lambda pid: None).status == \
        GC.JobStatus.LAUNCHING.value

    resolved = GL.observe(project, job, signature_of=lambda pid: None)
    assert resolved.status == GC.JobStatus.FAILED_TO_LAUNCH.value
    assert "abc123" in resolved.failure_reason
    assert "not relaunched automatically" in resolved.failure_reason
    assert resolved.terminal


# ================================================ 24 cancellation
def test_cancellation_stops_only_the_confirmed_tree(project, profiles, guide,
                                                    monkeypatch):
    """(24)"""
    study, plan = _confirmed(project, profiles, guide)
    worker = FakeWorker(write_record=False, write_transcript=False)
    job = _launch(project, plan, study, worker)
    try:
        output = Path(job.expected_output_directory)
        output.mkdir(parents=True, exist_ok=True)
        partial = output / "state_turn_3.json"
        partial.write_text(json.dumps({"session_meta": {"total_turns": 3}}),
                           encoding="utf-8")

        signature = {"pid": worker.pid, "create_time": worker.start_time,
                     "cmdline": ["py", "worker.py", "--config", job.config_path,
                                 "--terminal-record", job.terminal_record_path],
                     "evidence": "psutil"}
        monkeypatch.setattr(GL, "process_signature", lambda pid: signature)
        monkeypatch.setattr(GL, "process_tree", lambda pid: [worker.pid + 1])

        killed = []
        cancelled = GL.cancel(project, job.job_id,
                              confirm_session_id=job.session_id,
                              terminate=killed.append,
                              signature_of=lambda pid: signature)
        # the CLI child first, then the worker; nothing else
        assert killed == [worker.pid + 1, worker.pid]
        assert cancelled.status == GC.JobStatus.CANCELLED.value
        assert partial.is_file()                       # artefacts kept

        record = GL.terminal_record_for(cancelled)
        assert record.termination_kind == GT.TerminationKind.USER_CANCELLED.value
        assert "cost already incurred" in record.failure_reason
        # a cancelled session is never imported as completed
        outcome = GI.import_session_output(project, cancelled, plan=plan,
                                           sleeper=lambda _p: None)
        assert not outcome.ok
    finally:
        _cleanup(job)


def test_a_stranger_process_is_never_signalled(project, profiles, guide):
    study, plan = _confirmed(project, profiles, guide)
    worker = FakeWorker(write_record=False, write_transcript=False)
    job = _launch(project, plan, study, worker)
    try:
        stranger = {"pid": worker.pid, "create_time": 9999.0,
                    "cmdline": ["python", "something_else.py"],
                    "evidence": "psutil"}
        assert not GL.is_our_process(job, stranger)
        killed = []
        with pytest.raises(GC.GenerationError):
            GL.cancel(project, job.job_id, confirm_session_id=job.session_id,
                      terminate=killed.append, signature_of=lambda pid: stranger)
        assert killed == []
    finally:
        _cleanup(job)


# ================================================ 25-26 usage and cost
def test_cost_is_undefined_without_a_rate_table(project, profiles, guide):
    """(25)"""
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker())
    try:
        report = GPL.consolidate(
            job_id=job.job_id, session_id=job.session_id,
            output_directory=job.expected_output_directory,
            moderator_model="claude-sonnet-4-6",
            agent_models={"p_ana": "claude-haiku-4-5-20251001"}, table=None)
        assert report.n_calls == 9          # the zero-token summary is not a call
        assert report.input_tokens == 7200 and report.output_tokens == 1800
        assert report.total_cost is None
        assert report.cost_display == "Undefined"
        assert report.cost_status == GPL.OBSERVED_USAGE_UNPRICED
        assert all("no pricing table" in r.unpriced_reason for r in report.rows)
    finally:
        _cleanup(job)


def test_cost_uses_only_observed_usage(project, profiles, guide):
    """(26)"""
    study, plan = _confirmed(project, profiles, guide)
    table = GPL.PricingTable(
        table_version="2026-08-05",
        rows=[GPL.RateRow(provider="anthropic", model="claude-sonnet-4-6",
                          input_rate=3.0, output_rate=15.0, currency="USD",
                          effective_from="2026-01-01", source="user supplied"),
              GPL.RateRow(provider="anthropic",
                          model="claude-haiku-4-5-20251001",
                          input_rate=1.0, output_rate=5.0, currency="USD",
                          effective_from="2026-01-01", source="user supplied")])
    GPL.save_pricing_table(project, table)
    reloaded = GPL.load_pricing_table(project)
    assert reloaded.table_sha256 == GPL.compute_table_hash(table)

    job = _launch(project, plan, study, FakeWorker())
    try:
        report = GPL.consolidate(
            job_id=job.job_id, session_id=job.session_id,
            output_directory=job.expected_output_directory,
            moderator_model="claude-sonnet-4-6",
            agent_models={"p_ana": "claude-haiku-4-5-20251001"}, table=reloaded)
        assert report.cost_status == GPL.OBSERVED_USAGE_PRICED
        # attributed FROM THE LEDGER: moderator 800/200 on sonnet, participants
        # 6400/1600 on haiku
        expected = (800 / 1e6 * 3.0 + 200 / 1e6 * 15.0
                    + 6400 / 1e6 * 1.0 + 1600 / 1e6 * 5.0)
        assert report.total_cost == pytest.approx(expected)
        by_model = {r.model: r for r in report.rows}
        assert by_model["claude-sonnet-4-6"].n_calls == 1
        assert by_model["claude-haiku-4-5-20251001"].n_calls == 8
        assert report.pricing_table_version == "2026-08-05"
        assert report.pricing_table_sha256
        # the figure comes from the ledger, never from --max-turns
        assert study.max_turns not in (report.input_tokens, report.output_tokens)
    finally:
        _cleanup(job)


def test_a_missing_rate_leaves_money_undefined_and_tokens_visible(project, profiles,
                                                                  guide):
    study, plan = _confirmed(project, profiles, guide)
    table = GPL.PricingTable(
        table_version="partial",
        rows=[GPL.RateRow(provider="anthropic", model="claude-sonnet-4-6",
                          input_rate=3.0, output_rate=15.0)])
    job = _launch(project, plan, study, FakeWorker())
    try:
        report = GPL.consolidate(
            job_id=job.job_id, session_id=job.session_id,
            output_directory=job.expected_output_directory,
            moderator_model="claude-sonnet-4-6",
            agent_models={"p_ana": "claude-haiku-4-5-20251001"}, table=table)
        assert report.total_cost is None
        assert report.cost_display == "Undefined"
        assert "claude-haiku-4-5-20251001" in report.unpriced_models
        assert report.input_tokens == 7200        # tokens still visible
    finally:
        _cleanup(job)


def test_no_estimate_is_produced_from_a_token_ceiling(project):
    assert "ceiling" in GPL.estimate_note(None) or "no pricing table" in \
        GPL.estimate_note(None)
    table = GPL.PricingTable(table_version="v", rows=[
        GPL.RateRow(provider="anthropic", model="m", input_rate=1.0,
                    output_rate=1.0)])
    note = GPL.estimate_note(table)
    assert note.startswith("Cost estimate unavailable")
    assert "ceiling, not a prediction" in note


# ================================================ 27-28 safety
def test_no_provider_is_called_anywhere_in_this_suite(monkeypatch):
    """(27)"""
    import socket
    import sys
    for module in ("anthropic", "openai"):
        assert module not in sys.modules
    from platform_core import generation
    root = Path(generation.__file__).parent
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        assert "api.anthropic.com" not in text
        assert "messages.create" not in text
    assert socket is not None


def test_the_frozen_benchmark_is_untouched(project, profiles, guide):
    """(28)"""
    def digests():
        return {k: hashlib.sha256(s.path.read_bytes()).hexdigest()
                for k, s in TH.SOURCES.items()}

    before = digests()
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker())
    try:
        GL.observe(project, job, signature_of=lambda pid: None)
        GI.import_session_output(project, job, plan=plan, sleeper=lambda _p: None)
        assert digests() == before
        from platform_core.services import benchmark_service as B
        assert B.check_sources()["ok"]
        assert len(B.level2_condition_summary()) == 7
    finally:
        _cleanup(job)


def test_psutil_is_a_declared_dependency():
    assert GL.psutil_available()
    requirements = (Path(GL.__file__).parents[2] / "requirements.txt")
    if requirements.is_file():
        assert "psutil" in requirements.read_text(encoding="utf-8")


def test_nothing_writes_to_the_repository_configs_directory(project, profiles,
                                                            guide):
    before = sorted(p.name for p in (REPO_ROOT / "configs").iterdir())
    _confirmed(project, profiles, guide)
    assert sorted(p.name for p in (REPO_ROOT / "configs").iterdir()) == before
    assert str(GB.bundle_dir(project, "plan__weeknight")).startswith(
        str(project.path))


def test_requires_recovery_does_not_decay_and_is_never_relaunched(project, profiles,
                                                                  guide):
    """
    Regression. REQUIRES_RECOVERY used to become UNKNOWN on the next observation,
    which took the job out of every list that shows what needs attention - and out
    of the queue's terminal set, where it belongs.
    """
    study, plan = _confirmed(project, profiles, guide)
    job = _launch(project, plan, study, FakeWorker(write_record=False))
    try:
        observed = GL.observe(project, job, signature_of=lambda pid: None)
        assert observed.status == GC.JobStatus.REQUIRES_RECOVERY.value
        again = GL.observe(project, GL.load_job(project, job.job_id),
                           signature_of=lambda pid: None)
        assert again.status == GC.JobStatus.REQUIRES_RECOVERY.value

        assert GC.JobStatus.REQUIRES_RECOVERY.value in GQ.TERMINAL
        GQ.build_queue(project, plan, concurrency_limit=2,
                       max_turns=study.max_turns, mode=study.participation_mode)
        GQ.start(project)
        calls = []
        result = GQ.tick(project,
                         spawn=lambda *a, **k: calls.append(a) or {"pid": 1},
                         signature_of=lambda pid: None)
        assert result.launched == [] and calls == []
        assert job.job_id in result.terminal
    finally:
        _cleanup(job)


def test_a_queued_job_carries_what_its_own_preflight_verifies(project, profiles,
                                                              guide):
    """
    Regression, found by the first real launch attempt. `build_queue` created jobs
    without the effective-config and architecture hashes, so the launch-time gate
    blocked every one of them: a job that cannot pass its own preflight.
    """
    study, plan = _confirmed(project, profiles, guide)
    GQ.build_queue(project, plan, concurrency_limit=1, max_turns=study.max_turns,
                   mode=study.participation_mode)
    GQ.start(project)

    job = GL.load_job(project, GQ.load_queue(project).ordered_job_ids[0])
    assert job.effective_config_sha256 == \
        plan.effective_config_hashes[job.session_id]
    assert job.architecture_code_manifest_hash == \
        plan.architecture_code_manifest_hash

    report = GPF.verify_before_launch(project, job, plan=plan, env=ENV)
    assert report["ok"], report["problems"]

    result = GQ.tick(project, spawn=FakeWorker(),
                     verify=lambda p, j: GPF.verify_before_launch(
                         p, j, plan=plan, env=ENV))
    try:
        assert result.blocked == []
        assert result.launched == [job.job_id]
    finally:
        _cleanup(GL.load_job(project, job.job_id))


# ================================ findings from the first real run
def test_a_payload_the_architecture_would_reject_is_caught_before_launch(tmp_path):
    """
    Found by the first real run. `persona.background` written as a string passed
    this platform's schema validation and then crashed the session after six paid
    calls. Validating a schema is not validating what the consumer does with it.
    """
    bad = {"schema_version": "fg_agents_v1", "agent_id": "p_x", "language": "en",
           "persona": {"demographics": {"name": "X", "age": 30, "gender": "man"},
                       "background": "a sentence rather than labelled entries"},
           "simulation_config": {"model": "claude-haiku-4-5-20251001"}}
    path = tmp_path / "p_x.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    profile_set = PS.uploaded_profile_set([path])
    assert not profile_set.ok
    assert any("must be an object of labelled entries" in p
               for r in profile_set.records for p in r.problems)

    good = dict(bad)
    good["persona"] = dict(bad["persona"], background={"work": "shift work"})
    path.write_text(json.dumps(good), encoding="utf-8")
    assert PS.uploaded_profile_set([path]).ok


def test_optional_demographics_are_not_treated_as_required(tmp_path):
    """
    This test used to assert the opposite, and it was wrong.

    `core.participant_agent.load_agent_from_json`'s DOCSTRING lists age and gender as
    required; its CODE does `if age is not None` and builds the identity line without
    them. Following the docstring made the validator refuse 44 of the 123 agent
    payloads in this repository — real panels the architecture runs perfectly well.
    A validator that blocks work the consumer accepts is as broken as one that admits
    work the consumer rejects.
    """
    payload = {"schema_version": "fg_agents_v1", "agent_id": "p_y",
               "persona": {"demographics": {"name": "Y"}},
               "simulation_config": {"model": "claude-haiku-4-5-20251001"}}
    assert PS.architecture_shape_problems(payload) == []

    # A missing NAME is still a problem: it is indexed, not tested for absence.
    nameless = {"agent_id": "p_z", "persona": {"demographics": {"age": 30}}}
    assert any("name" in p for p in PS.architecture_shape_problems(nameless))


def test_shapes_that_crash_the_architecture_are_all_caught(tmp_path):
    """
    Every field `core.participant_agent` indexes without a type check.

    `background` is the one that cost six billed calls. The other three were found by
    reading the consumer rather than waiting for them to bite.
    """
    def problems(**persona_or_top):
        base = {"agent_id": "p", "persona": {"demographics": {"name": "A"}}}
        for key, value in persona_or_top.items():
            if key in ("background", "food_consumption"):
                base["persona"][key] = value
            elif key == "location":
                base["persona"]["demographics"][key] = value
            else:
                base[key] = value
        return PS.architecture_shape_problems(base)

    assert any("background" in p for p in problems(background="a paragraph"))
    assert any("location" in p for p in problems(location="Madrid"))
    assert any("psychometric_scores" in p
               for p in problems(psychometric_scores=["openness"]))
    assert any("psychometric_scores.d" in p
               for p in problems(psychometric_scores={"d": "high"}))
    assert any("must be a number" in p
               for p in problems(psychometric_scores={"d": {"value": "high"}}))
    assert any("opening_intro" in p for p in problems(opening_intro="hello"))
    # And the well-formed versions of all of them pass.
    assert problems(background={"work": "shifts"}, location={"country": "UK"},
                    psychometric_scores={"d": {"value": 4.2, "direction": "high"}},
                    opening_intro={"intro_eligible": False}) == []


def test_an_unattributed_call_is_counted_but_never_priced(tmp_path):
    """
    Found by the first real run: five of six ledger entries carried no `action`.
    Attributing them to the participant model would have priced moderator calls at
    the participant rate whenever the two models differ.
    """
    output = tmp_path / "session"
    output.mkdir()
    (output / "api_calls.jsonl").write_text(
        json.dumps({"role": "moderator", "model": "claude-sonnet-4-6",
                    "input_tokens": 1000, "output_tokens": 300, "turn": 0}) + "\n"
        # an entry that names no model: counted, never attributed
        + json.dumps({"role": "participant", "input_tokens": 4000,
                      "output_tokens": 1500, "turn": 1}) + "\n",
        encoding="utf-8")

    table = GPL.PricingTable(table_version="v1", rows=[
        GPL.RateRow(provider="anthropic", model="claude-sonnet-4-6",
                    input_rate=3.0, output_rate=15.0),
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0)])
    report = GPL.consolidate(
        job_id="j", session_id="s", output_directory=output,
        moderator_model="claude-sonnet-4-6",
        agent_models={"a": "claude-haiku-4-5-20251001"}, table=table)

    by_model = {r.model: r for r in report.rows}
    assert by_model["claude-sonnet-4-6"].total_cost is not None
    assert GPL.UNATTRIBUTED in by_model
    unattributed = by_model[GPL.UNATTRIBUTED]
    assert unattributed.input_tokens == 4000        # counted
    assert unattributed.total_cost is None          # never priced
    assert "names no model" in unattributed.unpriced_reason

    # the whole report stays unpriced while any usage is unattributed
    assert report.total_cost is None
    assert report.cost_display == "Undefined"
    assert report.input_tokens == 5000              # every token still visible


def test_cache_tokens_without_cache_rates_leave_the_cost_undefined(tmp_path):
    """
    An incomplete price is not a price. Cache creation is dearer than input and
    cache reads are cheaper; a total that ignored both would be wrong in two
    directions at once.
    """
    output = tmp_path / "session"
    output.mkdir()
    (output / "api_calls.jsonl").write_text(json.dumps({
        "role": "participant", "model": "claude-haiku-4-5-20251001",
        "input_tokens": 1000, "output_tokens": 300,
        "cache_creation_input_tokens": 5000, "cache_read_input_tokens": 20000,
        "turn": 1}), encoding="utf-8")

    without = GPL.PricingTable(table_version="no-cache", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0)])
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6",
                             agent_models={}, table=without)
    assert report.cache_creation_tokens == 5000
    assert report.cache_read_tokens == 20000
    assert report.total_cost is None
    assert report.cost_display == "Undefined"
    assert any("does not price them" in p for p in report.problems)

    # Phase 3F split cache writes by time-to-live. Here both TTLs cost the same, so
    # not knowing which was requested changes nothing and the row still prices.
    with_cache = GPL.PricingTable(table_version="with-cache", rows=[
        GPL.RateRow(provider="anthropic", model="claude-haiku-4-5-20251001",
                    input_rate=1.0, output_rate=5.0, cache_write_5m_rate=1.25,
                    cache_write_1h_rate=1.25, cache_read_rate=0.10)])
    priced = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6",
                             agent_models={}, table=with_cache)
    assert priced.cost_status == GPL.OBSERVED_USAGE_PRICED
    assert priced.total_cost == pytest.approx(
        1000 / 1e6 * 1.0 + 300 / 1e6 * 5.0 + 5000 / 1e6 * 1.25
        + 20000 / 1e6 * 0.10)


def test_a_zero_token_decision_summary_is_not_counted_as_a_call(tmp_path):
    """The real ledger writes moderator decision summaries with no tokens."""
    output = tmp_path / "session"
    output.mkdir()
    (output / "api_calls.jsonl").write_text(
        json.dumps({"event_type": "moderator_decision", "action": "redirect_to_group",
                    "role": "moderator", "turn": 2}) + "\n"
        + json.dumps({"role": "moderator", "model": "claude-sonnet-4-6",
                      "input_tokens": 100, "output_tokens": 50}) + "\n",
        encoding="utf-8")
    report = GPL.consolidate(job_id="j", session_id="s", output_directory=output,
                             moderator_model="claude-sonnet-4-6", agent_models={},
                             table=None)
    assert report.n_calls == 1
    assert report.input_tokens == 100
