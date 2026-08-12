"""
Phase 2A.1 hardening: untrusted identifiers (ADR-008), project path authority
(ADR-009) and atomic artefact writes (ADR-010).

Every case here is an attempt to make an identifier or a stored file decide a path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conftest import make_guide, make_profile
from platform_core import atomic, config, frozen, guides, profiles, projects
from platform_core.atomic import ArtifactExistsError, OnExists, atomic_write_text
from platform_core.config import DataDirError, resolve_data_dir
from platform_core.paths import PathValidationError, safe_component, safe_path

# The identifiers a hostile or careless file could carry.
HOSTILE_IDS = [
    "../../outside",
    "..\\outside",
    "C:\\outside",
    "/tmp/outside",
    "CON",
    "PRN",
    "name/subdir",
    "name\\subdir",
    "..",
    ".",
    "",
    "with space",
    "café",              # Unicode: refused by documented decision (ADR-008)
    "п",                 # Cyrillic look-alike
    "a" * 129,
]


def _write(path: Path, payload: dict, fmt: str = "json") -> Path:
    if fmt == "json":
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    return path


# =============================================== P0.1 agent_id as a path
@pytest.mark.parametrize("bad_id", HOSTILE_IDS)
def test_hostile_agent_id_is_refused_at_load(tmp_path, bad_id):
    p = _write(tmp_path / "p.json", make_profile(bad_id))
    with pytest.raises(profiles.ProfileError) as exc:
        profiles.load_profile_file(p)
    assert "agent_id" in str(exc.value)


@pytest.mark.parametrize("bad_id", HOSTILE_IDS)
def test_a_refused_identifier_creates_no_file(tmp_path, bad_id):
    p = _write(tmp_path / "p.json", make_profile(bad_id))
    out = tmp_path / "derived"
    with pytest.raises(profiles.ProfileError):
        profiles.load_profile_file(p)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == [p]


def test_agent_id_is_not_silently_rewritten(tmp_path):
    """A safe id keeps its substantive value; storage_name mirrors it exactly."""
    p = _write(tmp_path / "p.json", make_profile("mm_fg1_amir"))
    r = profiles.load_profile_file(p)
    assert r.agent_id == "mm_fg1_amir"
    assert r.storage_name == "mm_fg1_amir"
    assert r.payload["agent_id"] == "mm_fg1_amir"


def test_derived_path_is_built_from_the_storage_name(tmp_path):
    p = _write(tmp_path / "p.json", make_profile("agent.1-x_2"))
    r = profiles.load_profile_file(p)
    d = profiles.derive_profile(r, tmp_path / "derived",
                                participant_model="claude-opus-5")
    target = Path(d.derived_path)
    assert target.name == "agent.1-x_2.json"
    assert target.parent == tmp_path / "derived"


def test_json_and_yaml_with_the_same_safe_id_still_normalise_identically(tmp_path):
    payload = make_profile("safe_id_1")
    j = _write(tmp_path / "p.json", payload, "json")
    y = _write(tmp_path / "p.yaml", payload, "yaml")
    rj, ry = profiles.load_profile_file(j), profiles.load_profile_file(y)
    assert rj.canonical_sha256 == ry.canonical_sha256
    assert rj.storage_name == ry.storage_name == "safe_id_1"


# ================================================= P0.2 guide_id as a path
@pytest.mark.parametrize("bad_id", HOSTILE_IDS)
def test_hostile_guide_id_blocks_compilation(tmp_path, bad_id):
    g = make_guide(bad_id)
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(g, sort_keys=False, allow_unicode=True),
                 encoding="utf-8")
    with pytest.raises(guides.GuideError):
        guides.compile_guide_file(p)

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    v = guides.validate_guide(raw)
    assert not v.ok
    assert any(e.field_path == "guide_id" for e in v.errors)


@pytest.mark.parametrize("bad_id", ["../../outside", "CON", "name/subdir"])
def test_a_rejected_guide_writes_no_partial_json(tmp_path, bad_id):
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(make_guide(bad_id), sort_keys=False),
                 encoding="utf-8")
    out = tmp_path / "derived"
    with pytest.raises(guides.GuideError):
        guides.compile_guide_file(p)
    assert not out.exists()
    assert [f.name for f in tmp_path.iterdir()] == ["g.yaml"]


def test_guide_source_file_is_never_modified(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(make_guide("g_ok"), sort_keys=False),
                 encoding="utf-8")
    before = p.read_bytes()
    compiled = guides.compile_guide_file(p)
    guides.write_compiled(compiled, tmp_path / "derived")
    assert p.read_bytes() == before


def test_compiled_path_uses_the_storage_name(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(make_guide("guide.1-a_b"), sort_keys=False),
                 encoding="utf-8")
    compiled = guides.compile_guide_file(p)
    assert compiled.storage_name == "guide.1-a_b"
    out = guides.write_compiled(compiled, tmp_path / "derived")
    assert out.name == "guide.1-a_b.discussion_guide.json"


# =============================================== P0.3 session_id as a path
@pytest.mark.parametrize("session_id", [
    "pilot__../../outside",
    "pilot__..\\outside",
    "pilot__/absolute",
    "pilot__C:\\outside",
    "pilot__a/b",
    "pilot__with space",
])
def test_prefixed_but_escaping_session_ids_are_refused(tmp_path, session_id):
    plan = frozen.plan_session_destination(session_id, "pilot",
                                           session_log_root=tmp_path)
    assert not plan.allowed
    assert "unsafe identifier" in plan.refusal_reason
    assert "before touching the filesystem" in plan.refusal_reason
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("slug", ["../evil", "C:\\x", "sl ug", "CON"])
def test_unsafe_project_slug_is_refused(tmp_path, slug):
    plan = frozen.plan_session_destination(f"{slug}__fg1__r1", slug,
                                           session_log_root=tmp_path)
    assert not plan.allowed
    assert "project_slug" in plan.refusal_reason or "session_id" in plan.refusal_reason


def test_refused_plan_never_resolves_outside_the_root(tmp_path):
    plan = frozen.plan_session_destination("pilot__../../outside", "pilot",
                                           session_log_root=tmp_path)
    assert plan.resolved_path.parent == tmp_path
    assert plan.resolved_path.name == "<refused>"
    assert plan.collision is False and plan.frozen is False


def test_safe_session_id_still_allowed(tmp_path):
    plan = frozen.plan_session_destination("pilot__enriched__fg1__r1", "pilot",
                                           session_log_root=tmp_path)
    assert plan.allowed
    assert plan.resolved_path == tmp_path / "pilot__enriched__fg1__r1"


def test_reserved_name_check_is_exact_not_substring(tmp_path):
    """
    Only an exact Windows device name is reserved. `pilot__CON` is a legal directory
    name and must not be refused - over-refusing would reject valid research ids for
    no security gain.
    """
    assert safe_component("pilot__CON") == "pilot__CON"
    with pytest.raises(PathValidationError, match="reserved Windows device"):
        safe_component("CON")
    with pytest.raises(PathValidationError, match="reserved Windows device"):
        safe_component("con.json")
    assert frozen.plan_session_destination("pilot__CON", "pilot",
                                           session_log_root=tmp_path).allowed


# ======================================== P0.4 project.json is not authority
def _tamper(project_path: Path, **changes) -> None:
    pf = project_path / "project.json"
    raw = json.loads(pf.read_text(encoding="utf-8"))
    raw.update(changes)
    pf.write_text(json.dumps(raw, indent=1), encoding="utf-8")


def test_external_root_is_refused(data_dir, tmp_path):
    p = projects.create_project("Pilot", data_dir)
    _tamper(p.path, root=str(tmp_path / "somewhere_else"))
    with pytest.raises(projects.ProjectError, match="does not match the derived"):
        projects.load_project("pilot", data_dir)


def test_relative_root_is_refused(data_dir):
    p = projects.create_project("Pilot", data_dir)
    _tamper(p.path, root="relative/path")
    with pytest.raises(projects.ProjectError, match="is relative"):
        projects.load_project("pilot", data_dir)


def test_root_pointing_at_another_project_is_refused(data_dir):
    a = projects.create_project("Alpha", data_dir)
    projects.create_project("Beta", data_dir)
    _tamper(a.path, root=str(data_dir.projects_dir / "beta"))
    with pytest.raises(projects.ProjectError, match="does not match the derived"):
        projects.load_project("alpha", data_dir)


def test_mismatched_internal_project_id_is_refused(data_dir):
    p = projects.create_project("Pilot", data_dir)
    _tamper(p.path, project_id="someone_else")
    with pytest.raises(projects.ProjectError, match="does not match its location"):
        projects.load_project("pilot", data_dir)


def test_tampered_project_produces_no_write(data_dir, tmp_path):
    p = projects.create_project("Pilot", data_dir)
    outside = tmp_path / "somewhere_else"
    _tamper(p.path, root=str(outside))
    with pytest.raises(projects.ProjectError):
        projects.load_project("pilot", data_dir)
    assert not outside.exists()


def test_loaded_root_is_always_the_derived_path(data_dir):
    p = projects.create_project("Pilot", data_dir)
    _tamper(p.path, root=str(p.path))          # matching, therefore accepted
    loaded = projects.load_project("pilot", data_dir)
    assert loaded.path == data_dir.projects_dir / "pilot"
    assert loaded.subdir("uploads") == data_dir.projects_dir / "pilot" / "uploads"


def test_list_projects_skips_a_tampered_project(data_dir, tmp_path):
    projects.create_project("Good", data_dir)
    bad = projects.create_project("Bad", data_dir)
    _tamper(bad.path, root=str(tmp_path / "elsewhere"))
    assert [p.project_id for p in projects.list_projects(data_dir)] == ["good"]


@pytest.mark.parametrize("bad_id", ["../../outside", "C:\\x", "a/b", "CON"])
def test_hostile_project_id_is_refused_on_load(data_dir, bad_id):
    with pytest.raises((PathValidationError, projects.ProjectError)):
        projects.load_project(bad_id, data_dir)


# =============================================== P1 symlinked root
def test_symlinked_root_is_refused_via_the_seam(tmp_path, monkeypatch):
    """
    Unit-level cover for the symlink branch on a machine that cannot create one.
    The real integration test runs where the OS permits it (CI/Linux).
    """
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr("platform_core.paths.is_symlink",
                        lambda p: Path(p) == root)
    with pytest.raises(PathValidationError, match="symlinked root refused"):
        safe_path(root, "child")


def test_symlinked_ancestor_is_refused_via_the_seam(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    target = root / "a"
    monkeypatch.setattr("platform_core.paths.is_symlink",
                        lambda p: Path(p) == target)
    with pytest.raises(PathValidationError, match="symlink refused on the path"):
        safe_path(root, "a", "b")


def test_symlink_seam_defaults_to_the_real_check(tmp_path):
    from platform_core import paths
    assert paths.is_symlink(tmp_path) is False


# =============================================== P1 injected repo directory
def test_injected_repository_path_is_refused_by_default():
    with pytest.raises(DataDirError, match="never lives inside the repository"):
        resolve_data_dir(injected=config.REPO_ROOT / "tmp_injected")


def test_injected_repository_path_needs_an_explicit_test_flag():
    r = resolve_data_dir(injected=config.REPO_ROOT / "tmp_injected",
                         allow_repo_for_tests=True)
    assert r.source == "injected"
    assert not r.path.exists()          # still creates nothing


def test_workspace_is_refused_even_with_the_test_flag():
    with pytest.raises(DataDirError):
        resolve_data_dir(injected=config.APP_ROOT / "workspace",
                         allow_repo_for_tests=True)


def test_outside_paths_need_no_flag(tmp_path):
    assert resolve_data_dir(injected=tmp_path).source == "injected"


# =============================================== P1 atomic writes
def test_atomic_write_creates_the_file(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_text(target, '{"a": 1}')
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert atomic.stale_temp_files(tmp_path) == []


def test_overwrite_is_not_implicit(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_text(target, '{"a": 1}')
    with pytest.raises(ArtifactExistsError, match="not implicit"):
        atomic_write_text(target, '{"a": 2}')
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_explicit_replace_is_allowed(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_text(target, '{"a": 1}')
    atomic_write_text(target, '{"a": 2}', on_exists=OnExists.REPLACE)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}


def test_skip_leaves_the_original(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_text(target, '{"a": 1}')
    atomic_write_text(target, '{"a": 2}', on_exists=OnExists.SKIP)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_a_failed_verification_leaves_the_previous_file_intact(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_text(target, '{"a": 1}')

    def explode(_written):
        raise ValueError("verification failed")

    with pytest.raises(ValueError, match="verification failed"):
        atomic_write_text(target, '{"a": 2}', on_exists=OnExists.REPLACE,
                          verify=explode)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert atomic.stale_temp_files(tmp_path) == []


def test_no_temporary_survives_a_failure(tmp_path):
    def explode(_written):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        atomic_write_text(tmp_path / "new.json", "{}", verify=explode)
    assert not (tmp_path / "new.json").exists()
    assert atomic.stale_temp_files(tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_derived_profile_collision_does_not_overwrite(tmp_path):
    p = _write(tmp_path / "p.json", make_profile("agent_a"))
    r = profiles.load_profile_file(p)
    out = tmp_path / "derived"
    first = profiles.derive_profile(r, out, participant_model="claude-opus-5")
    before = Path(first.derived_path).read_bytes()

    with pytest.raises(ArtifactExistsError):
        profiles.derive_profile(r, out, participant_model="claude-sonnet-5")
    assert Path(first.derived_path).read_bytes() == before
    assert atomic.stale_temp_files(out) == []


def test_compiled_guide_collision_does_not_overwrite(tmp_path):
    src = tmp_path / "g.yaml"
    src.write_text(yaml.safe_dump(make_guide("g_a"), sort_keys=False),
                   encoding="utf-8")
    compiled = guides.compile_guide_file(src)
    out_dir = tmp_path / "derived"
    first = guides.write_compiled(compiled, out_dir)
    before = first.read_bytes()

    with pytest.raises(ArtifactExistsError):
        guides.write_compiled(compiled, out_dir)
    assert first.read_bytes() == before
    assert atomic.stale_temp_files(out_dir) == []


def test_project_file_write_is_atomic_and_replaceable(data_dir):
    p = projects.create_project("Pilot", data_dir)
    assert atomic.stale_temp_files(p.path) == []
    projects._write_project_file(p)          # replace policy, no exception
    assert json.loads((p.path / "project.json").read_text(encoding="utf-8"))[
        "project_id"] == "pilot"


# ================================================ invariants that must hold
def test_frozen_manifest_still_classifies_its_entries():
    m = frozen.load_manifest()
    assert len(m.entries) == 77
    assert len(m.acceptance_paths) == 65


def test_catalog_still_classifies_46_metrics():
    from collections import Counter

    from platform_core import catalog
    c = catalog.load_catalog()
    assert len(c.entries) == 46
    counts = Counter(e.status.value for e in c.entries.values())
    assert counts == {
        "AVAILABLE_EXPLORATORY": 16,
        "AVAILABLE_VALIDATED": 13,
        "NOT_IN_REPORTED_INSTRUMENT": 9,
        "SYNTHETIC_ONLY": 5,
        "DEFERRED_NOT_IMPLEMENTED": 2,
        "RETIRED_NOT_FOR_FIDELITY": 1,
    }


@pytest.mark.parametrize("component", HOSTILE_IDS)
def test_safe_component_is_the_single_gate(component):
    with pytest.raises(PathValidationError):
        safe_component(component)
