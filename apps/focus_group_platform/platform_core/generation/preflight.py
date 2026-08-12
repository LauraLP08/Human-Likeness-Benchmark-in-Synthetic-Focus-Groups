"""
The check that runs immediately before a process is created.

A DRY-RUN IS A STATEMENT ABOUT BYTES AT A MOMENT. Between that moment and the launch,
a config can be edited, a profile replaced, a guide recompiled, the architecture
updated. Confirming a plan on Tuesday does not authorise running different bytes on
Thursday, so every dependency is re-hashed here, in the seconds before the worker
starts.

A failure is BLOCKED_INPUT_CHANGED, and the report names the file and both hashes. "A
hash changed" is not something a researcher can act on; "the profile p_ana.json
changed after the bundle was built" is.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import REPO_ROOT
from ..projects import Project
from . import bundle as GB
from . import credentials as GC_CRED
from .contracts import GenerationRunPlan, JobRecord, sha256_json
from .effective_config import architecture_code_manifest_hash


@dataclass
class PreflightReport:
    job_id: str
    session_id: str
    ok: bool = False
    checks: list[dict] = field(default_factory=list)
    problems: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _check(report: PreflightReport, name: str, ok: bool, detail: str,
           **extra) -> None:
    report.checks.append(dict({"check": name, "ok": ok, "detail": detail}, **extra))
    if not ok:
        report.problems.append(dict({"check": name, "message": detail}, **extra))


def verify_before_launch(project: Project, job: JobRecord, *,
                         plan: GenerationRunPlan | None = None,
                         env: dict | None = None,
                         occupied_slots: int | None = None,
                         concurrency_limit: int | None = None) -> dict:
    """
    Eleven checks. Any failure means the job is not started.

    Returns a plain dict so the queue can carry it into a `TickResult` without
    importing this module's types.
    """
    from .planner import load_plan

    report = PreflightReport(job_id=job.job_id, session_id=job.session_id)
    plan = plan if plan is not None else load_plan(project)

    # 1 the plan is confirmed
    _check(report, "plan_confirmed", bool(plan and plan.launchable),
           "the plan has passed its dry-run" if (plan and plan.launchable)
           else "the plan is not confirmed; run the dry-run again")

    # 2 the bundle is intact and immutable
    architecture_now = architecture_code_manifest_hash()
    verification = GB.verify(project, job.bundle_plan_id or (plan.plan_id if plan
                                                             else ""),
                             architecture_code_manifest_hash=architecture_now)
    _check(report, "bundle_immutable", verification.ok and verification.immutable,
           ("the bundle is confirmed and every dependency still hashes as recorded"
            if verification.ok and verification.immutable else
            "; ".join(p["message"] for p in verification.problems)
            or "the bundle has not been confirmed"),
           problems=verification.problems)

    # 3 the config bytes
    config_path = Path(job.config_path)
    if not config_path.is_file():
        _check(report, "config_hash", False,
               f"the config {config_path} does not exist")
    else:
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            actual = sha256_json(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            _check(report, "config_hash", False,
                   f"the config could not be read: {exc}")
        else:
            _check(report, "config_hash", actual == job.config_sha256,
                   ("the config is byte-for-byte the one that was confirmed"
                    if actual == job.config_sha256 else
                    f"the config changed after confirmation: expected "
                    f"{job.config_sha256[:12]}…, found {actual[:12]}…"),
                   expected=job.config_sha256, actual=actual)

    # 4 the effective configuration
    effective_path = config_path.with_suffix("").with_suffix(
        ".effective_config.json")
    if job.effective_config_sha256 and effective_path.is_file():
        try:
            effective = json.loads(effective_path.read_text(encoding="utf-8"))
            recorded = effective.get("effective_config_sha256", "")
        except (json.JSONDecodeError, OSError):
            recorded = ""
        _check(report, "effective_config_hash",
               recorded == job.effective_config_sha256,
               ("the resolved effective configuration is unchanged"
                if recorded == job.effective_config_sha256 else
                f"the effective configuration changed: expected "
                f"{job.effective_config_sha256[:12]}…, found {recorded[:12]}…"),
               expected=job.effective_config_sha256, actual=recorded)
    else:
        _check(report, "effective_config_hash", bool(job.effective_config_sha256),
               "no effective configuration hash was recorded for this job"
               if not job.effective_config_sha256
               else "the effective configuration file is missing")

    # 5, 6 the guide and profile snapshots (covered by the bundle, reported apart so
    # the researcher sees WHICH dependency moved)
    guide_problems = [p for p in verification.problems
                      if p.get("kind", "").startswith("guide")]
    _check(report, "guide_hashes", not guide_problems,
           "; ".join(p["message"] for p in guide_problems)
           or "the bundled guide is unchanged")
    profile_problems = [p for p in verification.problems
                        if p.get("kind") == "profile"]
    _check(report, "profile_hashes", not profile_problems,
           "; ".join(p["message"] for p in profile_problems)
           or "every bundled profile is unchanged, byte for byte")

    # 7 the architecture
    architecture_problems = [p for p in verification.problems
                             if p.get("where") == "architecture"]
    _check(report, "architecture_manifest", not architecture_problems,
           "; ".join(p["message"] for p in architecture_problems)
           or "the generation architecture is the one this plan was pinned to",
           expected=job.architecture_code_manifest_hash or
           verification.architecture_hash_at_bundle,
           actual=architecture_now)

    # 8 the session id is unused, 9 the output directory does not exist
    output = Path(job.expected_output_directory)
    _check(report, "output_directory", not output.exists(),
           f"{output} does not exist yet" if not output.exists() else
           f"{output} already exists; the directory is never reused")

    # 10 credentials, by provider
    if plan is not None:
        study = None
        try:
            from .planner import load_study
            study = load_study(project)
        except Exception:                                        # noqa: BLE001
            study = None
        if study is not None:
            agent_models = _agent_models(project, job)
            credential_report = GC_CRED.check(
                moderator_model=study.moderator_model,
                agent_models=agent_models, env=env)
            _check(report, "credentials", credential_report.ok,
                   ("every required provider has a credential"
                    if credential_report.ok else
                    "; ".join(f"{r.provider}: {r.missing_variables} missing"
                              for r in credential_report.missing)),
                   providers=[r.to_dict() for r in credential_report.requirements])

    # 11 a free slot
    if occupied_slots is not None and concurrency_limit is not None:
        free = concurrency_limit - occupied_slots
        _check(report, "concurrency_slot", free > 0,
               f"{free} slot(s) free of {concurrency_limit}" if free > 0
               else f"no slot free: {occupied_slots} of {concurrency_limit} in use")

    report.ok = not report.problems
    return report.to_dict()


def _agent_models(project: Project, job: JobRecord) -> dict[str, str]:
    """Resolve each agent's model from the BUNDLED payloads, not from a live path."""
    from .effective_config import ARCHITECTURE_DEFAULTS

    out: dict[str, str] = {}
    manifest = GB.load_manifest(project, job.bundle_plan_id or job.plan_id)
    if manifest is None:
        return out
    root = GB.bundle_dir(project, manifest.plan_id)
    for dependency in manifest.dependencies:
        if dependency.kind != "profile":
            continue
        path = root / dependency.relative_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        simulation = payload.get("simulation_config") or {}
        out[dependency.agent_id] = (simulation.get("model")
                                    or ARCHITECTURE_DEFAULTS["participant_model"])
    return out
