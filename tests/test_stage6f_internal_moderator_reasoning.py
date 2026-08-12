import pytest
from pathlib import Path

def get_moderator_prompt():
    prompt_path = Path("prompts/01_MODERATOR_SYSTEM_PROMPT.md")
    return prompt_path.read_text(encoding="utf-8")

def test_moderator_prompt_includes_internal_reasoning_guidance():
    prompt = get_moderator_prompt()
    
    assert "Internal reasoning style" in prompt or "INTERNAL REASONING STYLE" in prompt
    assert "neutral" in prompt
    assert "evidence-based" in prompt
    assert "not evaluative" in prompt
    assert "Do not describe participant contributions as" in prompt

def test_moderator_prompt_targets_hidden_fields():
    prompt = get_moderator_prompt()

    assert "situation_assessment" in prompt
    # brief_justification/justification were consolidated into situation_assessment
    # — see docs/changes/2026-07-23_moderator_output_prune_and_reasoning_consolidation.md
    assert "brief_justification" not in prompt
    assert "justification" not in prompt

def test_moderator_prompt_discourages_over_validation_phrases():
    prompt = get_moderator_prompt()
    
    # We check that these are mentioned in the prompt (as they are in the Avoid list)
    banned_phrases = [
        "excellent data",
        "rich data",
        "powerful analysis",
        "remarkable analytical depth",
        "vulnerable, honest data",
        "exactly what the research needs",
        "intellectually honest",
        "sophisticated response",
        "emotional richness"
    ]
    
    for phrase in banned_phrases:
        assert phrase in prompt, f"Prompt should mention '{phrase}' in its 'Avoid' list."
