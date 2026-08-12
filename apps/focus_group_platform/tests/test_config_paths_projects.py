"""Data-directory resolution, path safety, projects. ADR-005."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from platform_core import config, projects
from platform_core.config import (DataDirError, ENV_VAR, dev_reference_enabled,
                                  resolve_data_dir)
from platform_core.paths import PathValidationError, safe_path, slugify


# ------------------------------------------------------- resolution order
def test_env_var_wins(tmp_path):
    r = resolve_data_dir(env={ENV_VAR: str(tmp_path / "from_env")})
    assert r.source == "env_var"
    assert r.path.name == "from_env"


def test_injected_beats_env(tmp_path):
    r = resolve_data_dir(injected=tmp_path / "injected",
                         env={ENV_VAR: str(tmp_path / "from_env")})
    assert r.source == "injected"
    assert r.path.name == "injected"


def test_falls_back_to_os_app_data():
    r = resolve_data_dir(env={})
    assert r.source == "os_app_data"
    assert r.path.is_absolute()


def test_resolution_creates_nothing(tmp_path):
    target = tmp_path / "never_created"
    r = resolve_data_dir(injected=target)
    assert r.created_by_this_call is False
    assert r.exists is False
    assert not target.exists()


def test_ensure_creates_explicitly(tmp_path):
    target = tmp_path / "created"
    r = resolve_data_dir(injected=target, ensure=True)
    assert r.created_by_this_call is True
    assert target.is_dir()


def test_repository_workspace_is_refused():
    with pytest.raises(DataDirError, match="never lives inside the repository"):
        resolve_data_dir(env={ENV_VAR: str(config.APP_ROOT / "workspace")})


def test_any_path_inside_the_repository_is_refused():
    with pytest.raises(DataDirError, match="inside the repository"):
        resolve_data_dir(env={ENV_VAR: str(config.REPO_ROOT / "somewhere")})


def test_dev_reference_flag():
    assert dev_reference_enabled(env={}) is False
    assert dev_reference_enabled(env={"FOCUS_GROUP_PLATFORM_DEV_REFERENCE": "1"})


# ------------------------------------------------------------- safe_path
def test_safe_path_joins_inside_root(tmp_path):
    assert safe_path(tmp_path, "a", "b").parent.name == "a"


@pytest.mark.parametrize("part", ["..", "../x", "a/b", "a\\b", "", ".",
                                  "/etc", "C:/Windows", "con", "PRN.txt",
                                  "x" * 129, "we;rd"])
def test_safe_path_refuses_unsafe_components(tmp_path, part):
    with pytest.raises(PathValidationError):
        safe_path(tmp_path, part)


def test_safe_path_refuses_absolute_drive_change(tmp_path):
    with pytest.raises(PathValidationError):
        safe_path(tmp_path, "D:\\other")


def test_safe_path_requires_absolute_root():
    with pytest.raises(PathValidationError, match="root must be absolute"):
        safe_path(Path("relative"), "a")


def test_safe_path_refuses_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this machine")
    with pytest.raises(PathValidationError, match="symlink"):
        safe_path(root, "link")


def test_must_exist(tmp_path):
    with pytest.raises(PathValidationError, match="does not exist"):
        safe_path(tmp_path, "nope", must_exist=True)


def test_slugify():
    assert slugify("My Pilot Study!") == "my_pilot_study"
    assert slugify("   ") == "project"


# -------------------------------------------------------------- projects
def test_create_project_under_data_dir(data_dir):
    p = projects.create_project("Pilot Study", data_dir)
    assert p.project_id == "pilot_study"
    assert p.path.is_dir()
    assert p.path.parent == data_dir.projects_dir
    for sub in projects.PROJECT_SUBDIRS:
        assert (p.path / sub).is_dir()
    assert (p.path / projects.PROJECT_FILE).is_file()


def test_project_never_created_inside_repository(data_dir, repo_root):
    p = projects.create_project("Pilot", data_dir)
    assert repo_root.absolute() not in p.path.absolute().parents


def test_duplicate_project_refused(data_dir):
    projects.create_project("Pilot", data_dir)
    with pytest.raises(projects.ProjectError, match="already exists"):
        projects.create_project("Pilot", data_dir)


def test_round_trip(data_dir):
    created = projects.create_project("Pilot", data_dir, description="d")
    loaded = projects.load_project("pilot", data_dir)
    assert loaded.name == created.name
    assert loaded.description == "d"
    assert [p.project_id for p in projects.list_projects(data_dir)] == ["pilot"]


def test_delete_is_recoverable(data_dir):
    projects.create_project("Pilot", data_dir)
    trashed = projects.delete_project("pilot", data_dir)
    assert trashed.is_dir()
    assert not (data_dir.projects_dir / "pilot").exists()
    assert projects.list_projects(data_dir) == []

    projects.restore_project(trashed.name, data_dir)
    assert (data_dir.projects_dir / "pilot").is_dir()


def test_purge_is_a_separate_call(data_dir):
    projects.create_project("Pilot", data_dir)
    trashed = projects.delete_project("pilot", data_dir)
    projects.purge_trashed_project(trashed.name, data_dir)
    assert not trashed.exists()


def test_subdir_rejects_unknown(data_dir):
    p = projects.create_project("Pilot", data_dir)
    with pytest.raises(projects.ProjectError):
        p.subdir("elsewhere")


# ------------------------------------------------------------ no side effects
def test_platform_core_does_not_import_streamlit():
    """
    Checked in a FRESH interpreter.

    `"streamlit" not in sys.modules` was true only until some other test file
    imported it - once the Phase 3A interface tests existed, this test passed or
    failed depending on collection order, which is no test at all. A subprocess asks
    the real question: does importing platform_core, on its own, pull in Streamlit?
    """
    import subprocess

    script = ("import sys, platform_core, platform_core.services; "
              "print('streamlit' in sys.modules)")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == "False", completed.stdout


def test_importing_platform_core_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "should_not_appear"))
    import importlib

    import platform_core
    importlib.reload(platform_core)
    assert not (tmp_path / "should_not_appear").exists()


def test_repository_workspace_directory_does_not_exist():
    """ADR-005: apps/focus_group_platform/workspace/ is never a destination."""
    assert not (config.APP_ROOT / "workspace").exists()
