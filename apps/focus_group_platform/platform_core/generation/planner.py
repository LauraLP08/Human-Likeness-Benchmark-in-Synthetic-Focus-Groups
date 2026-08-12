"""
Build a run plan, and refuse to launch until every part of it checks out.

THE DRY-RUN IS THE GATE. Ten checks, none of which touches the network: the study,
the profiles, the guide, every compiled config, the identifiers, the CLI's existence,
whether a credential is present (never its value), the session count, the models and
turn cap, and whether a cost estimate can be made at all.

`Launch` is unavailable until all of them pass. That is not caution for its own sake -
a plan that fails on session nine has already spent the money for sessions one to
eight.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..config import REPO_ROOT
from ..guides import GuideError, compile_guide, validate_guide
from ..paths import PathValidationError, safe_component, safe_path, slugify
from ..provenance import APPLICATION_VERSION
from ..projects import Project
from .effective_config import architecture_code_manifest_hash
from .config_builder import build_session_config, cli_command, serialise
from .contracts import (CLI_MODES, CLI_RELATIVE_PATH, DEFAULT_CONCURRENCY,
                        GenerationError, GenerationRunPlan, GenerationSession,
                        GenerationStudy, MAX_CONCURRENCY, ValidationStatus,
                        plan_from_dict, sha256_text, study_from_dict)
from .profiles_source import ProfileSet

GENERATION_DIRNAME = "generation"
CONFIGS_DIRNAME = "configs"
STUDY_FILENAME = "generation_study.json"
PLAN_FILENAME = "run_plan.json"

# Names the CLI's own environment loading would look for. The platform checks
# PRESENCE only and never reads, stores, displays or copies a value.
CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY",)
DOTENV_PATH = ".env"

SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def generation_dir(project: Project) -> Path:
    return safe_path(project.subdir("derived"), GENERATION_DIRNAME)


def configs_dir(project: Project) -> Path:
    """Compiled configs live INSIDE the project. `configs/` is never written."""
    return safe_path(generation_dir(project), CONFIGS_DIRNAME)


# ------------------------------------------------------------------ persistence
def save_study(project: Project, study: GenerationStudy) -> Path:
    directory = generation_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_path(directory, STUDY_FILENAME)
    atomic_write_text(target, json.dumps(study.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_study(project: Project) -> GenerationStudy | None:
    target = generation_dir(project) / STUDY_FILENAME
    if not target.is_file():
        return None
    return study_from_dict(json.loads(target.read_text(encoding="utf-8")))


def save_plan(project: Project, plan: GenerationRunPlan) -> Path:
    directory = generation_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_path(directory, PLAN_FILENAME)
    atomic_write_text(target, json.dumps(plan.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_plan(project: Project) -> GenerationRunPlan | None:
    target = generation_dir(project) / PLAN_FILENAME
    if not target.is_file():
        return None
    return plan_from_dict(json.loads(target.read_text(encoding="utf-8")))


# ----------------------------------------------------------------- the guide
@dataclass
class GuideBundle:
    yaml_text: str
    yaml_sha256: str
    compiled: list[dict] = field(default_factory=list)
    compiled_sha256: str = ""
    guide_id: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and bool(self.compiled)

    def to_dict(self) -> dict:
        return {"guide_id": self.guide_id, "yaml_sha256": self.yaml_sha256,
                "compiled_sha256": self.compiled_sha256,
                "n_sections": len(self.compiled),
                "problems": self.problems, "warnings": self.warnings}


def compile_guide_text(yaml_text: str) -> GuideBundle:
    """
    YAML in, the CLI's `discussion_guide` out. Both hashes retained.

    A guide problem blocks the plan: a malformed section is not something to discover
    once the moderator is already talking.
    """
    import yaml

    bundle = GuideBundle(yaml_text=yaml_text, yaml_sha256=sha256_text(yaml_text))
    try:
        raw = yaml.safe_load(yaml_text)
    except Exception as exc:                                    # noqa: BLE001
        bundle.problems.append(f"the YAML could not be parsed: {exc}")
        return bundle
    if not isinstance(raw, dict):
        bundle.problems.append("the guide must be a mapping with a `sections` list")
        return bundle

    validation = validate_guide(raw)
    for problem in validation.errors:
        bundle.problems.append(
            f"section {problem.section_index} {problem.field_path}: "
            f"{problem.message}")
    for problem in validation.warnings:
        bundle.warnings.append(
            f"section {problem.section_index} {problem.field_path}: "
            f"{problem.message}")
    if bundle.problems:
        return bundle

    try:
        compiled = compile_guide(raw, yaml_text)
    except GuideError as exc:
        bundle.problems.append(str(exc))
        return bundle
    bundle.compiled = compiled.sections
    bundle.compiled_sha256 = compiled.compiled_json_sha256
    bundle.guide_id = compiled.guide_id
    return bundle


# ------------------------------------------------------------------ identity
def make_session_id(study: GenerationStudy, condition_id: str, focus_group_id: str,
                    replicate_index: int) -> str:
    """
    Deterministic, path-safe and readable. NOT a timestamp.

    A timestamp would make the identity depend on when a button was pressed, so
    re-creating the same plan would produce different ids for the same logical
    sessions and nothing downstream could tell they were the same position.
    """
    stem = slugify(study.generation_study_id)
    session_id = (f"{stem}_{slugify(condition_id)}_{slugify(focus_group_id)}"
                  f"_r{int(replicate_index):02d}")
    if slugify(session_id) != session_id:
        raise GenerationError(
            f"the generated session id {session_id!r} does not survive slugify; it "
            f"would become a different transcript id on import")
    return session_id


def session_id_problems(session_id: str, *, project: Project,
                        seen: set[str]) -> list[str]:
    problems = []
    if not SESSION_ID.match(session_id):
        problems.append(f"{session_id!r} is not usable as a path component")
    try:
        safe_component(session_id, field="session_id")
    except PathValidationError as exc:
        problems.append(str(exc))
    if session_id in seen:
        problems.append(f"{session_id!r} appears twice in this plan")
    if (configs_dir(project) / f"{session_id}.json").exists():
        problems.append(f"a compiled config for {session_id!r} already exists in "
                        f"this project")
    if (REPO_ROOT / "output" / "session_logs" / session_id).exists():
        problems.append(
            f"output/session_logs/{session_id} already exists. The directory is "
            f"never reused - choose a new run so the previous one keeps its "
            f"transcript")
    return problems


# ---------------------------------------------------------------- the plan
def build_plan(project: Project, study: GenerationStudy, *,
               profile_set: ProfileSet, guide: GuideBundle,
               plan_id: str | None = None) -> GenerationRunPlan:
    """Compile every session. Nothing is written and nothing is launched."""
    plan = GenerationRunPlan(
        plan_id=plan_id or f"plan__{slugify(study.generation_study_id)}",
        generation_study_id=study.generation_study_id,
        guide_yaml_sha256=guide.yaml_sha256,
        guide_compiled_sha256=guide.compiled_sha256,
        profile_source=profile_set.to_dict(), created_utc=_now())

    from .profiles_source import participants_from_profiles
    participants = participants_from_profiles(profile_set, relative_to=REPO_ROOT)

    seen: set[str] = set()
    for condition_id in study.synthetic_conditions:
        for focus_group_id in study.focus_groups:
            for replicate_index in range(1, study.replicates + 1):
                session_id = make_session_id(study, condition_id, focus_group_id,
                                             replicate_index)
                run_label = (f"{condition_id}_{focus_group_id}"
                             f"_r{replicate_index:02d}")
                built = build_session_config(
                    study, session_id=session_id, run_label=run_label,
                    participants=participants,
                    discussion_guide=guide.compiled)
                for problem in built.problems:
                    plan.validation_problems.append(
                        {"session_id": session_id, "where": "config",
                         "message": problem})
                for problem in session_id_problems(session_id, project=project,
                                                   seen=seen):
                    plan.validation_problems.append(
                        {"session_id": session_id, "where": "identity",
                         "message": problem})
                seen.add(session_id)

                plan.config_hashes[session_id] = built.sha256
                plan.sessions.append(GenerationSession(
                    session_id=session_id, condition_id=condition_id,
                    focus_group_id=focus_group_id,
                    replicate_index=replicate_index, run_label=run_label,
                    config_path=str(configs_dir(project) / f"{session_id}.json"),
                    config_sha256=built.sha256, agent_ids=built.agent_ids,
                    guide_hash=guide.compiled_sha256,
                    output_directory=str(REPO_ROOT / "output" / "session_logs"
                                         / session_id)))
    return plan


# ------------------------------------------------------------------ dry run
@dataclass
class DryRunReport:
    plan_id: str
    checks: list[dict] = field(default_factory=list)
    problems: list[dict] = field(default_factory=list)
    total_sessions: int = 0
    models: dict = field(default_factory=dict)
    max_turns: int = 0
    concurrency_limit: int = DEFAULT_CONCURRENCY
    cost_estimate: str = "Cost estimate unavailable"
    output_directories: list[str] = field(default_factory=list)
    made_external_calls: bool = False
    credentials: dict = field(default_factory=dict)
    architecture_code_manifest_hash: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def _check(report: DryRunReport, name: str, ok: bool, detail: str) -> None:
    report.checks.append({"check": name, "ok": ok, "detail": detail})
    if not ok:
        report.problems.append({"check": name, "message": detail})


def dry_run(project: Project, study: GenerationStudy, plan: GenerationRunPlan, *,
            profile_set: ProfileSet, guide: GuideBundle,
            env: dict | None = None) -> DryRunReport:
    """Ten checks. No external call is made, and a test asserts that."""
    environ = os.environ if env is None else env
    report = DryRunReport(plan_id=plan.plan_id, total_sessions=len(plan.sessions),
                          max_turns=study.max_turns,
                          concurrency_limit=study.concurrency_limit,
                          models={"moderator_model": study.moderator_model,
                                  "participant_model": study.participant_model,
                                  "participant_model_source":
                                      "agent_payload.simulation_config.model"},
                          output_directories=[s.output_directory
                                              for s in plan.sessions])

    # 1 study
    study_problems = []
    if not study.synthetic_conditions:
        study_problems.append("no synthetic condition is declared")
    if not study.focus_groups:
        study_problems.append("no focus group is declared")
    if study.replicates < 1:
        study_problems.append("replicates must be at least 1")
    if study.participation_mode not in CLI_MODES:
        study_problems.append(f"participation_mode must be one of {list(CLI_MODES)}")
    if not (1 <= study.concurrency_limit <= MAX_CONCURRENCY):
        study_problems.append(f"concurrency_limit must be between 1 and "
                              f"{MAX_CONCURRENCY}")
    _check(report, "study", not study_problems,
           "; ".join(study_problems) or
           f"{study.n_sessions} session(s) declared")

    # 2 profiles
    _check(report, "profiles", profile_set.ok,
           "; ".join(profile_set.problems
                     + [f"{r.agent_id}: {p}" for r in profile_set.records
                        for p in r.problems])
           or f"{len(profile_set.records)} profile(s) validated")

    # 3 guide
    _check(report, "discussion_guide", guide.ok,
           "; ".join(guide.problems) or
           f"{len(guide.compiled)} section(s) compiled")

    # 4 configs
    config_problems = [p for p in plan.validation_problems
                       if p["where"] == "config"]
    _check(report, "configs", not config_problems,
           "; ".join(f"{p['session_id']}: {p['message']}" for p in config_problems)
           or f"{len(plan.sessions)} config(s) compiled")

    # 5 identifiers and paths
    identity_problems = [p for p in plan.validation_problems
                         if p["where"] == "identity"]
    _check(report, "identifiers", not identity_problems,
           "; ".join(f"{p['session_id']}: {p['message']}"
                     for p in identity_problems)
           or "every session id is unique, path-safe and unused")

    # 6 the CLI exists
    cli = REPO_ROOT / CLI_RELATIVE_PATH
    _check(report, "cli", cli.is_file(),
           f"{CLI_RELATIVE_PATH} " + ("found" if cli.is_file() else "NOT FOUND"))

    # 7 credentials: BY PROVIDER, presence only, never the value. The existence of
    # a .env file proves nothing - an empty or unrelated one used to pass.
    from . import credentials as GCRED
    agent_models = {r.agent_id: _agent_model(r) for r in profile_set.records}
    credential_report = GCRED.check(moderator_model=study.moderator_model,
                                    agent_models=agent_models, env=environ)
    report.credentials = credential_report.to_dict()
    _check(report, "credentials", credential_report.ok,
           ("every required provider has a credential: "
            + ", ".join(f"{r.provider} ({r.source})"
                        for r in credential_report.requirements)
            + ". No value is read, stored, hashed or shown.")
           if credential_report.ok else
           "; ".join(f"{r.provider} needs {r.missing_variables} for {r.used_by}"
                     for r in credential_report.missing))

    # 8 session count, 9 models and cap: informational, always pass
    _check(report, "session_count", True,
           f"{len(plan.sessions)} session(s) would run, "
           f"{study.concurrency_limit} at a time")
    _check(report, "models_and_turns", True,
           f"moderator {study.moderator_model}; participant model comes from each "
           f"agent payload; --max-turns {study.max_turns}")

    # 10 cost
    report.cost_estimate = _cost_estimate(project, study, plan)
    _check(report, "cost_estimate", True, report.cost_estimate)

    # 11 the architecture this plan would be pinned to
    report.architecture_code_manifest_hash = architecture_code_manifest_hash()
    _check(report, "architecture_manifest", True,
           f"the plan will be pinned to architecture "
           f"{report.architecture_code_manifest_hash[:12]}…; if it changes before "
           f"launch, the run is blocked until the plan is reconfirmed")

    return report


def _agent_model(record) -> str:
    """The model an agent payload names, or the architecture default."""
    from .effective_config import ARCHITECTURE_DEFAULTS
    try:
        payload = json.loads(Path(record.source_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ARCHITECTURE_DEFAULTS["participant_model"]
    simulation = payload.get("simulation_config") or {}
    return simulation.get("model") or ARCHITECTURE_DEFAULTS["participant_model"]


def _cost_estimate(project: Project, study: GenerationStudy,
                   plan: GenerationRunPlan) -> str:
    """
    An estimate needs a rate table AND a token expectation. The second never exists
    before a run: --max-turns is a ceiling, and pricing a ceiling produces a figure
    that reads as a forecast without being one.
    """
    from .pricing_ledger import estimate_note, load_pricing_table
    return estimate_note(load_pricing_table(project))


def confirmed_plan(plan: GenerationRunPlan, report: DryRunReport
                   ) -> GenerationRunPlan:
    plan.validation_status = (ValidationStatus.VALID.value if report.ok
                              else ValidationStatus.INVALID.value)
    plan.validation_problems = list(plan.validation_problems) + [
        {"session_id": "", "where": p["check"], "message": p["message"]}
        for p in report.problems
        if not any(v["message"] == p["message"] for v in plan.validation_problems)]
    return plan


def write_configs(project: Project, study: GenerationStudy,
                  plan: GenerationRunPlan, *, profile_set: ProfileSet,
                  guide: GuideBundle,
                  inline_profiles: bool = True) -> list[Path]:
    """
    Build the immutable bundle, then write the configs from it.

    PORTABLE BY CONSTRUCTION. Profiles go into the config as INLINE agent payloads
    (the public contract accepts them), so the config does not depend on a path that
    can change or that means nothing on another machine. The exact profile bytes are
    also kept in the bundle, so the original is still there to compare against.

    Where a payload lacks what the inline form requires, the participant falls back
    to a BUNDLED path - inside the project, snapshotted, hashed - rather than the
    live upload directory.
    """
    if not plan.launchable:
        raise GenerationError(
            "the plan has not passed its dry-run; configs are not written for a plan "
            "that cannot be launched")

    from . import bundle as GB
    from .effective_config import resolve

    architecture_hash = architecture_code_manifest_hash()
    manifest = GB.build_bundle(
        project, plan_id=plan.plan_id,
        generation_study_id=study.generation_study_id,
        guide_yaml=guide.yaml_text, guide_compiled=guide.compiled,
        profile_paths=[(r.agent_id, Path(r.source_path))
                       for r in profile_set.records],
        architecture_code_manifest_hash=architecture_hash,
        application_version=APPLICATION_VERSION)

    payloads = []
    for record in profile_set.records:
        bundled = GB.bundled_profile_path(project, plan.plan_id, record.agent_id)
        payloads.append((record.agent_id, bundled,
                         json.loads(bundled.read_text(encoding="utf-8"))))

    participants = _participants_from_bundle(payloads,
                                             inline_profiles=inline_profiles)

    directory = configs_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for session in plan.sessions:
        built = build_session_config(
            study, session_id=session.session_id, run_label=session.run_label,
            participants=participants, discussion_guide=guide.compiled)
        if not built.ok:
            raise GenerationError(f"{session.session_id}: "
                                  + "; ".join(built.problems))

        target = safe_path(directory, f"{session.session_id}.json")
        atomic_write_text(target, serialise(built.config), on_exists=OnExists.FAIL,
                          verify=lambda written_text: json.loads(written_text))
        command = cli_command(python_executable=sys.executable,
                              cli_path=str(REPO_ROOT / CLI_RELATIVE_PATH),
                              config_path=str(target),
                              max_turns=study.max_turns,
                              mode=study.participation_mode)
        effective = resolve(study, session_id=session.session_id,
                            plan_id=plan.plan_id, config=built.config,
                            profiles=[payload for _a, _p, payload in payloads],
                            config_sha256=built.sha256, command=command)
        effective_path = safe_path(
            directory, f"{session.session_id}.effective_config.json")
        atomic_write_text(effective_path,
                          json.dumps(effective.to_dict(), indent=1,
                                     ensure_ascii=False),
                          on_exists=OnExists.REPLACE,
                          verify=lambda written_text: json.loads(written_text))

        GB.add_config(project, manifest, session_id=session.session_id,
                      config=built.config, effective_config=effective.to_dict())

        session.config_path = str(target)
        session.config_sha256 = built.sha256
        plan.config_hashes[session.session_id] = built.sha256
        plan.effective_config_hashes[session.session_id] = effective.sha256
        written.append(target)

    plan.bundle_plan_id = plan.plan_id
    plan.architecture_code_manifest_hash = architecture_hash
    plan.confirmed_utc = _now()
    GB.confirm(project, manifest)
    return written


def _participants_from_bundle(payloads, *, inline_profiles: bool) -> list[dict]:
    """
    One participant entry per agent, in exactly one of the accepted forms.

    Inline needs `persona.demographics.{name, age, gender}`; a payload without them
    keeps the bundled-path form rather than being edited to fit.
    """
    participants = []
    for _agent_id, bundled_path, payload in payloads:
        demographics = ((payload.get("persona") or {}).get("demographics") or {})
        complete = all(demographics.get(k) is not None
                       for k in ("name", "age", "gender"))
        if inline_profiles and complete:
            participants.append({"agent_payload": payload})
        else:
            participants.append(
                {"agent_payload_path": str(bundled_path).replace("\\", "/")})
    return participants
