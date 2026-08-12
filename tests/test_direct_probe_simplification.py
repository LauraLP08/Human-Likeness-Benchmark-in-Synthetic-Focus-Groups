"""
Tests for the direct_probe simplification: probe_type is no longer a forced
sub-classification, just always null. Prompt-text-only change.

Pure pydantic construction + file reads. Zero network calls, zero API calls.
See INSTRUCTIONS_DIRECT_PROBE_SIMPLIFICATION.md
"""

from __future__ import annotations

from pathlib import Path

from core.prompt_renderer import load_system_prompt
from core.session_state import ModeratorAction, ModeratorDecisionResponse


def test_direct_probe_validates_with_probe_type_none():
    """probe_type was never required for direct_probe at the schema level —
    prove it with a runnable, offline construction rather than by inspection."""
    decision = ModeratorDecisionResponse(
        intervention_mode="speak",
        situation_assessment="P2's answer is vague; needs a concrete example.",
        dominant_signal="response_needs_probing",
        action=ModeratorAction.DIRECT_PROBE,
        target="P2",
        probe_type=None,
    )
    assert decision.action == ModeratorAction.DIRECT_PROBE
    assert decision.probe_type is None


def test_system_prompt_no_longer_lists_probe_subtypes():
    prompt = load_system_prompt()
    assert "Probe sub-types" not in prompt
    assert "you do not need to label or categorise" in prompt


def test_user_message_template_probe_type_instruction_updated():
    text = Path("prompts/02_USER_MESSAGE_TEMPLATE.md").read_text(encoding="utf-8")
    assert "must be chosen precisely" not in text
    assert "No longer used to classify probes" in text
