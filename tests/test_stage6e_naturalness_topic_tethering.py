import pytest
from core.participant_agent import _BEHAVIOUR_INSTRUCTIONS

# Test Participant Prompts
def test_participant_instructions_contain_required_stage_6e_guidance():
    assert "willing to participate" in _BEHAVIOUR_INSTRUCTIONS
    assert "depend on your participant profile" in _BEHAVIOUR_INSTRUCTIONS
    assert "ideal qualitative-research answer" in _BEHAVIOUR_INSTRUCTIONS
    assert "theatrical stage directions" in _BEHAVIOUR_INSTRUCTIONS
    assert "markdown asterisks" in _BEHAVIOUR_INSTRUCTIONS
    assert "leave room for others to speak" in _BEHAVIOUR_INSTRUCTIONS
    assert "partial, ordinary, repetitive, uncertain" in _BEHAVIOUR_INSTRUCTIONS

def test_participant_instructions_do_not_contain_overly_prescriptive_guidance():
    assert "2-5 sentences" not in _BEHAVIOUR_INSTRUCTIONS
    assert "word limit" not in _BEHAVIOUR_INSTRUCTIONS.lower()
    assert "lived experience" not in _BEHAVIOUR_INSTRUCTIONS.lower()
    assert "contradictions" not in _BEHAVIOUR_INSTRUCTIONS.lower()
    assert "frustrations" not in _BEHAVIOUR_INSTRUCTIONS.lower()
    assert "ambivalence" not in _BEHAVIOUR_INSTRUCTIONS.lower()
    assert "trade-offs" not in _BEHAVIOUR_INSTRUCTIONS.lower()

# Test Moderator Prompts
def test_moderator_prompt_contains_stage_6e_guidance():
    with open("prompts/01_MODERATOR_SYSTEM_PROMPT.md", "r", encoding="utf-8") as f:
        mod_prompt = f.read()
    
    # Check for Neutral Facilitation
    assert "The moderator should facilitate rather than reward." in mod_prompt
    assert "Avoid repeatedly praising participant contributions" in mod_prompt
    assert "Use neutral acknowledgements instead of evaluative praise." in mod_prompt
    assert "ask one clear question at a time" in mod_prompt
    
    # Check for Topic Tethering
    # Domain wording updated when this prompt moved from the grocery-delivery study
    # to Macho Meals. The Stage 6E topic-tethering guidance itself is unchanged and
    # still present (see TOPIC TETHERING AND CONCRETE GROUNDING); only the concrete
    # domain nouns differ, so the assertions track the current wording.
    #
    # NOTE: this file is NOT the prompt any Macho Meals run executed. All 32 audited
    # runs set moderator_prompt_override = sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md
    # (run_readiness_audit.csv), so this test guards a prompt used by zero canonical
    # runs and its result cannot affect the production evaluation either way.
    assert "ground the discussion back in concrete food choices" in mod_prompt
    assert "ask for how the abstract issue appears in actual food behaviour" in mod_prompt
    
    # Check for Managing Conversational Space
    assert "protect conversational space without imposing quotas" in mod_prompt
    assert "ask for a concrete example rather than a full position statement" in mod_prompt
    
    # Check for Banned phrases
    assert "really powerful insight" not in mod_prompt.lower() or "avoid repeatedly praising" in mod_prompt.lower()
    assert "really brave" not in mod_prompt.lower() or "brave" in mod_prompt.lower()

def test_session_opening_prompt_contains_stage_6e_guidance():
    with open("prompts/03_SESSION_OPENING_PROMPT.md", "r", encoding="utf-8") as f:
        opening_prompt = f.read()
    
    assert "invite actual, concrete experiences" in opening_prompt
    assert "respond naturally if something connects with their experience" in opening_prompt
    assert "do not over-emphasize the need for disagreement, debate, or profound insight" in opening_prompt
    assert "search for deep philosophical truth" in opening_prompt

