"""
Tests for the stay_silent removal: the action block is dropped from the
system prompt, but ModeratorAction.STAY_SILENT stays in the schema as an
inert, unreferenced enum member.

Pure pydantic construction + file reads. Zero network calls, zero API calls.
See INSTRUCTIONS_STAY_SILENT_REMOVAL.md
"""

from __future__ import annotations

from pathlib import Path

from core.prompt_renderer import load_system_prompt
from core.session_state import ModeratorAction, ModeratorDecisionResponse


def test_observe_mode_with_no_action_validates():
    """The replacement path — observe mode, no action needed — already works
    without stay_silent."""
    decision = ModeratorDecisionResponse(
        intervention_mode="observe",
        situation_assessment="Participants are building on each other's points productively.",
    )
    assert decision.intervention_mode == "observe"
    assert decision.action is None


def test_stay_silent_enum_member_still_exists():
    """Guards against scope creep in either direction: the enum member is
    deliberately left inert, not removed."""
    assert ModeratorAction.STAY_SILENT == "stay_silent"


def test_system_prompt_no_longer_lists_stay_silent_block():
    prompt = load_system_prompt()
    assert "### `stay_silent`" not in prompt
    # Surrounding blocks and the section boundary survived intact.
    assert "### `invite_to_speak`" in prompt
    assert "### `consensus_risk_assessment`" in prompt
