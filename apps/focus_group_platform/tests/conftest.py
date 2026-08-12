"""
Shared fixtures.

Every test that touches the data directory injects a temporary one. No test resolves
the real data directory, and no test writes anywhere in the repository.

THE SECOND SENTENCE USED TO BE A CLAIM RATHER THAN A FACT. Jobs built by the
generation tests carried an `expected_output_directory` under the repository's own
`output/session_logs/`, and the fake worker wrote transcripts there. A test that died
before its cleanup left a directory behind, and `build_job` — correctly — then refused
that session id for every later run, so the next suite failed for a reason that had
nothing to do with the code. `redirect_session_output` below makes the sentence true.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from platform_core.config import resolve_data_dir  # noqa: E402


@pytest.fixture
def data_dir(tmp_path):
    """An injected data directory. Created, because the test is about what follows."""
    return resolve_data_dir(injected=tmp_path / "appdata", ensure=True)


@pytest.fixture(autouse=True)
def redirect_session_output(tmp_path, monkeypatch):
    """
    Session output goes to a temporary directory, for every test, always.

    Autouse and unconditional: a test that forgets is exactly the test that leaves a
    directory in the researcher's repository. `monkeypatch` unsets it afterwards, so
    nothing leaks into a later process.
    """
    from platform_core.generation.launcher import SESSION_OUTPUT_ROOT_ENV
    # NOT created. Several hardening tests assert `tmp_path` is still empty after a
    # refusal — creating a directory here would make them fail for a reason that has
    # nothing to do with what they check. Whatever writes session output creates it.
    target = tmp_path / "session_logs"
    monkeypatch.setenv(SESSION_OUTPUT_ROOT_ENV, str(target))
    return target


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def app_root():
    return APP_ROOT


def make_profile(agent_id: str = "p1", **overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "agent_id": agent_id,
        "language": "en",
        "field_provenance": {
            "persona.demographics.name": "observed",
            "persona.demographics.age": "observed",
            "persona.demographics.location.country": "derived",
        },
        "persona": {
            "demographics": {
                "name": "Alex",
                "age": 34,
                "gender": "Male",
                "location": {"country": "UK", "region": "North"},
            }
        },
        "simulation_config": {"model": "claude-haiku-4-5", "max_tokens": 400},
    }
    payload.update(overrides)
    return payload


def make_guide(guide_id: str = "g1", phase: str = "context") -> dict:
    return {
        "guide_id": guide_id,
        "title": "A guide",
        "description": "d",
        "topic_domain": "t",
        "participant_collective_identity": "p",
        "moderator_knowledge_brief": "m",
        "sections": [
            {"label": "Opening", "phase": "intro",
             "scripted_question": "Welcome. Shall we begin?"},
            {"label": "Main", "phase": phase,
             "scripted_question": "  What do you think?  ",
             "suggested_probes": ["Why?", "Can you say more?"]},
        ],
    }
