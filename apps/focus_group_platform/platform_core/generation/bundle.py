"""
The generation bundle: everything a plan depends on, copied and frozen.

WHAT THIS REPLACES. Configs used to point at profile files by absolute path. The file
could change after validation, the path meant nothing on another machine, and the plan
recorded a hash of something it did not own. A bundle owns its inputs.

    generation/bundles/<plan_id>/
        manifest.json
        guide/original.yaml
        guide/compiled.json
        profiles/<agent_id>.json
        configs/<session_id>.json
        configs/<session_id>.effective_config.json

PROFILE BYTES ARE COPIED, NOT REWRITTEN. `raw_sha256` is over the exact bytes and a
test compares them byte for byte. `semantic_sha256` is over the parsed structure, so a
reformatted-but-identical payload can be recognised as such - but it is recorded
beside the raw hash, never instead of it.

IMMUTABLE AFTER CONFIRMATION. `verify()` re-hashes every dependency; any difference
invalidates the plan and the answer is a new plan, not a repaired bundle.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..paths import safe_component, safe_path
from ..projects import Project
from .contracts import GenerationError

BUNDLES_DIRNAME = "bundles"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def semantic_sha256(data: bytes) -> str | None:
    """Structure, not formatting. None when the bytes are not JSON."""
    try:
        payload = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class BundledDependency:
    relative_path: str
    kind: str                       # guide_yaml | guide_compiled | profile | config
                                    # | effective_config
    raw_sha256: str
    semantic_sha256: str | None = None
    source_path: str = ""           # provenance only; never resolved at run time
    agent_id: str = ""
    session_id: str = ""
    bundled_utc: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BundleManifest:
    schema_version: str
    plan_id: str
    project_id: str
    generation_study_id: str
    dependencies: list[BundledDependency] = field(default_factory=list)
    architecture_code_manifest_hash: str = ""
    application_version: str = ""
    created_utc: str = ""
    confirmed_utc: str = ""
    immutable: bool = False
    rebase_note: str = (
        "paths inside this manifest are RELATIVE TO THE BUNDLE ROOT. Moving the "
        "bundle is supported; rebasing is explicit at import and is never applied "
        "silently to a config that already names a path.")

    def dependency(self, relative_path: str) -> BundledDependency:
        for d in self.dependencies:
            if d.relative_path == relative_path:
                return d
        raise GenerationError(f"{relative_path!r} is not in this bundle")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dependencies"] = [x.to_dict() for x in self.dependencies]
        return d


def manifest_from_dict(payload: dict) -> BundleManifest:
    known = set(BundleManifest.__dataclass_fields__)
    body = {k: v for k, v in payload.items() if k in known}
    body["dependencies"] = [BundledDependency(**d)
                            for d in payload.get("dependencies", [])]
    return BundleManifest(**body)


# ------------------------------------------------------------------ locations
def bundles_dir(project: Project) -> Path:
    from .planner import generation_dir
    return safe_path(generation_dir(project), BUNDLES_DIRNAME)


def bundle_dir(project: Project, plan_id: str) -> Path:
    safe_component(plan_id, field="plan_id")
    return safe_path(bundles_dir(project), plan_id)


def manifest_path(project: Project, plan_id: str) -> Path:
    return safe_path(bundle_dir(project, plan_id), MANIFEST_NAME)


def load_manifest(project: Project, plan_id: str) -> BundleManifest | None:
    target = manifest_path(project, plan_id)
    if not target.is_file():
        return None
    return manifest_from_dict(json.loads(target.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ building
def _add(root: Path, dependencies: list[BundledDependency], *, relative: str,
         kind: str, data: bytes, source_path: str = "", agent_id: str = "",
         session_id: str = "") -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    dependencies.append(BundledDependency(
        relative_path=relative, kind=kind, raw_sha256=raw_sha256(data),
        semantic_sha256=semantic_sha256(data), source_path=source_path,
        agent_id=agent_id, session_id=session_id, bundled_utc=_now()))
    return target


def build_bundle(project: Project, *, plan_id: str, generation_study_id: str,
                 guide_yaml: str, guide_compiled: list[dict],
                 profile_paths: list[tuple[str, Path]],
                 architecture_code_manifest_hash: str,
                 application_version: str = "") -> BundleManifest:
    """
    Snapshot the guide and the profiles. Configs are added afterwards, once they are
    compiled against the bundled profiles.
    """
    root = bundle_dir(project, plan_id)
    if root.exists():
        existing = load_manifest(project, plan_id)
        if existing and existing.immutable:
            raise GenerationError(
                f"the bundle for {plan_id} is confirmed and immutable; create a new "
                f"plan rather than rebuilding it")
        shutil.rmtree(root)
    root.mkdir(parents=True)

    dependencies: list[BundledDependency] = []
    _add(root, dependencies, relative="guide/original.yaml", kind="guide_yaml",
         data=guide_yaml.encode("utf-8"))
    _add(root, dependencies, relative="guide/compiled.json",
         kind="guide_compiled",
         data=json.dumps(guide_compiled, indent=1,
                         ensure_ascii=False).encode("utf-8"))

    for agent_id, path in profile_paths:
        safe_component(agent_id, field="agent_id")
        # EXACT BYTES. Not re-serialised, not reformatted, not normalised.
        _add(root, dependencies, relative=f"profiles/{agent_id}.json",
             kind="profile", data=Path(path).read_bytes(),
             source_path=str(path), agent_id=agent_id)

    manifest = BundleManifest(
        schema_version=SCHEMA_VERSION, plan_id=plan_id,
        project_id=project.project_id,
        generation_study_id=generation_study_id, dependencies=dependencies,
        architecture_code_manifest_hash=architecture_code_manifest_hash,
        application_version=application_version, created_utc=_now())
    write_manifest(project, manifest)
    return manifest


def add_config(project: Project, manifest: BundleManifest, *, session_id: str,
               config: dict, effective_config: dict) -> BundleManifest:
    if manifest.immutable:
        raise GenerationError(
            f"the bundle for {manifest.plan_id} is immutable; a config cannot be "
            f"added to a confirmed plan")
    root = bundle_dir(project, manifest.plan_id)
    _add(root, manifest.dependencies,
         relative=f"configs/{session_id}.json", kind="config",
         data=json.dumps(config, indent=1, ensure_ascii=False).encode("utf-8"),
         session_id=session_id)
    _add(root, manifest.dependencies,
         relative=f"configs/{session_id}.effective_config.json",
         kind="effective_config",
         data=json.dumps(effective_config, indent=1,
                         ensure_ascii=False).encode("utf-8"),
         session_id=session_id)
    return manifest


def write_manifest(project: Project, manifest: BundleManifest) -> Path:
    target = manifest_path(project, manifest.plan_id)
    atomic_write_text(target, json.dumps(manifest.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def confirm(project: Project, manifest: BundleManifest) -> BundleManifest:
    """Freeze it. From here the bundle is read-only and drift is detectable."""
    manifest.immutable = True
    manifest.confirmed_utc = _now()
    write_manifest(project, manifest)
    return manifest


# ---------------------------------------------------------------- verification
@dataclass
class BundleVerification:
    plan_id: str
    ok: bool
    immutable: bool
    problems: list[dict] = field(default_factory=list)
    checked: int = 0
    architecture_hash_now: str = ""
    architecture_hash_at_bundle: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def verify(project: Project, plan_id: str, *,
           architecture_code_manifest_hash: str | None = None
           ) -> BundleVerification:
    """
    Re-hash every dependency. Names exactly what changed, not merely that something
    did - "a hash changed" is not something a researcher can act on.
    """
    manifest = load_manifest(project, plan_id)
    if manifest is None:
        return BundleVerification(plan_id=plan_id, ok=False, immutable=False,
                                  problems=[{"where": "manifest",
                                             "message": "no bundle exists for this "
                                                        "plan"}])
    root = bundle_dir(project, plan_id)
    problems: list[dict] = []
    for dependency in manifest.dependencies:
        target = root / dependency.relative_path
        if not target.is_file():
            problems.append({"where": dependency.relative_path,
                             "kind": dependency.kind,
                             "message": "the bundled file is missing"})
            continue
        data = target.read_bytes()
        actual = raw_sha256(data)
        if actual != dependency.raw_sha256:
            problems.append({
                "where": dependency.relative_path, "kind": dependency.kind,
                "expected_sha256": dependency.raw_sha256, "actual_sha256": actual,
                "message": (f"{dependency.kind} {dependency.relative_path} changed "
                            f"after the bundle was built")})

    now = architecture_code_manifest_hash
    if now is not None and manifest.architecture_code_manifest_hash and \
            now != manifest.architecture_code_manifest_hash:
        problems.append({
            "where": "architecture",
            "expected_sha256": manifest.architecture_code_manifest_hash,
            "actual_sha256": now,
            "message": ("the generation architecture changed after this plan was "
                        "bundled; the same config would now run a different "
                        "instrument. Create or reconfirm a plan.")})

    return BundleVerification(
        plan_id=plan_id, ok=not problems, immutable=manifest.immutable,
        problems=problems, checked=len(manifest.dependencies),
        architecture_hash_now=now or "",
        architecture_hash_at_bundle=manifest.architecture_code_manifest_hash)


def bundled_profile_path(project: Project, plan_id: str, agent_id: str) -> Path:
    return bundle_dir(project, plan_id) / "profiles" / f"{agent_id}.json"


def bundled_config_path(project: Project, plan_id: str, session_id: str) -> Path:
    return bundle_dir(project, plan_id) / "configs" / f"{session_id}.json"


def rebase(manifest: BundleManifest, new_root: Path) -> dict:
    """
    Explicit rebasing for a bundle that has moved.

    Returns the mapping it WOULD apply, and does not touch any config. A platform
    that silently rewrote paths inside a confirmed config would be editing a frozen
    artefact to make it work - which is the failure the bundle exists to prevent.
    """
    return {
        "plan_id": manifest.plan_id,
        "new_root": str(new_root),
        "mapping": {d.relative_path: str(new_root / d.relative_path)
                    for d in manifest.dependencies},
        "applied": False,
        "note": ("nothing has been rewritten. Rebasing a confirmed bundle means "
                 "creating a new plan whose configs name the new location."),
    }
