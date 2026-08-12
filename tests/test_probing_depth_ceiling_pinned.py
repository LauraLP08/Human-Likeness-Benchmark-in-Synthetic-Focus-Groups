"""
probing_depth_ceiling is pinned to None for every section of every run.

WHY:
    The researcher does not use per-section depth ceilings, and no system
    prompt — production (01_MODERATOR_SYSTEM_PROMPT.md) or sandbox/minimal
    (sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md) — defines what a ceiling
    would actually do. Grepping either for "depth ceiling" returns nothing.
    A value would therefore steer nothing while appearing in the moderator's
    SESSION CONFIGURATION as a live setting.

HOW:
    _build_state_from_config() ignores any configured value (warning logged)
    rather than rejecting it, so the historical configs that DO set it
    (sandbox_minimal_moderator_pilot_01/_02, smoke_test_grocery, the
    stage6d/6e/6f verification configs) still load for replay and inspection.
    Their existing session_logs are untouched; only future runs are pinned.

    _state_to_session_config() no longer emits the key at all, and both opening
    prompts' schema blocks no longer document it.

Offline: no orchestrator API calls are made — only config -> state construction
and prompt-file reads.
"""

from __future__ import annotations

import glob
import io
import json
import logging
import os

import pytest

from core.moderator_brain import _state_to_session_config
from core.orchestrator import FocusGroupOrchestrator, _build_state_from_config


def _config(ceilings: list) -> dict:
    """Config whose sections carry whatever ceiling values are passed in."""
    guide = []
    for i, c in enumerate(ceilings):
        sec = {
            "section_index": i,
            "section_label": f"S{i}",
            "section_phase": "main_topic",
            "section_purpose": "test",
            "scripted_question": "Test?",
            "stimulus": None,
        }
        if c is not _ABSENT:
            sec["probing_depth_ceiling"] = c
        guide.append(sec)
    return {
        "session_id": "ceiling_pin_test",
        "research_objective": "Test",
        "topic_domain": "Test",
        "participation_mode": "emergent",
        "temperature": 1.0,
        "participant_collective_identity": "test participants",
        "moderator_knowledge_brief": "brief",
        "researcher_notes": "",
        "participants": [{"id": "P1", "name": "Alice", "profile_summary": ""}],
        "discussion_guide": guide,
    }


_ABSENT = object()


# ---------------------------------------------------------------------------
# The guarantee
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["deep", "medium", "light"])
def test_configured_ceiling_is_ignored(value):
    """A config that sets a valid ceiling must still produce None."""
    state = _build_state_from_config(_config([value]))
    assert state.discussion_guide[0].probing_depth_ceiling is None


def test_absent_ceiling_stays_none():
    state = _build_state_from_config(_config([_ABSENT]))
    assert state.discussion_guide[0].probing_depth_ceiling is None


def test_mixed_sections_all_pinned_to_none():
    state = _build_state_from_config(_config(["deep", _ABSENT, "light", None]))
    assert [s.probing_depth_ceiling for s in state.discussion_guide] == [None, None, None, None]


def test_invalid_ceiling_value_no_longer_raises():
    """
    Previously ProbingDepthCeiling(value) was constructed from the config, so a
    typo'd value raised ValueError at load. Pinning removes that crash path —
    tests/test_stage6d_prompt_cleanup.py carries "shallow", which is not a
    valid enum member.
    """
    state = _build_state_from_config(_config(["shallow"]))
    assert state.discussion_guide[0].probing_depth_ceiling is None


def test_configured_ceiling_logs_a_warning(caplog):
    """Ignoring silently would be its own trap — say so."""
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        _build_state_from_config(_config(["deep"]))
    assert any("probing_depth_ceiling" in r.message and "ignoring it" in r.message
               for r in caplog.records), caplog.text


def test_absent_ceiling_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        _build_state_from_config(_config([_ABSENT]))
    assert not any("probing_depth_ceiling" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# It is no longer shown to the moderator
# ---------------------------------------------------------------------------

def test_session_config_sent_to_moderator_omits_the_key():
    state = _build_state_from_config(_config(["deep", "light"]))
    cfg = _state_to_session_config(state)
    for section in cfg["discussion_guide"]:
        assert "probing_depth_ceiling" not in section, section


@pytest.mark.parametrize("prompt_file", [
    "prompts/03_SESSION_OPENING_PROMPT.md",
    "prompts/sandbox/03_SESSION_OPENING_PROMPT_SANDBOX.md",
])
def test_opening_prompts_no_longer_document_the_field(prompt_file):
    text = io.open(prompt_file, encoding="utf-8").read()
    assert "probing_depth_ceiling" not in text


# ---------------------------------------------------------------------------
# Historical configs must still load — we are not rewriting the past
# ---------------------------------------------------------------------------

def test_every_existing_config_still_loads_with_ceiling_pinned():
    """
    Ignoring rather than rejecting means the seven historical configs that set
    probing_depth_ceiling remain loadable. If this ever becomes a hard error,
    replaying those runs breaks.
    """
    checked = 0
    for path in sorted(glob.glob("configs/**/*.json", recursive=True)):
        raw = json.loads(io.open(path, encoding="utf-8").read())
        if "discussion_guide" not in raw or "participants" not in raw:
            continue
        if any("agent_payload_path" in p for p in raw["participants"]):
            continue          # needs agent files; covered by other tests
        state = _build_state_from_config(raw)
        assert all(s.probing_depth_ceiling is None for s in state.discussion_guide), path
        checked += 1
    assert checked > 0, "no inline-participant configs were exercised"


def test_full_orchestrator_construction_pins_it(monkeypatch, tmp_path):
    """End-to-end through the real constructor, not just the builder."""
    monkeypatch.setattr("core.orchestrator._OUTPUT_ROOT", tmp_path)
    orch = FocusGroupOrchestrator(_config(["deep", "deep"]))
    assert all(s.probing_depth_ceiling is None for s in orch.state.discussion_guide)
