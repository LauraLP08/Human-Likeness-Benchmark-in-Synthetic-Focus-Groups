"""
Tests for the moderator output prune (six decorative fields) and the
reasoning-prose consolidation (brief_justification + justification ->
situation_assessment).

Pure pydantic construction + file reads. Zero network calls, zero API calls.
See docs/changes/2026-07-23_moderator_output_prune_and_reasoning_consolidation.md
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.session_state import (
    DiscussionGuideSection,
    GroupState,
    ModeratorAction,
    ModeratorAPIResponse,
    ModeratorDecisionResponse,
    ParticipantState,
    SectionPhase,
    SessionMeta,
    SessionState,
    TriggerEvent,
    TriggerEventType,
    apply_moderator_response,
)

PRUNED_FIELDS = [
    "group_dynamic_flags",
    "new_emergent_themes",
    "participant_response_quality",
    "participant_engagement_signal",
    "participant_dominant_tendency",
    "new_topics_covered",
]
REMOVED_REASONING_FIELDS = ["brief_justification", "justification"]


def _make_state() -> SessionState:
    meta = SessionMeta(
        id="test_prune",
        research_objective="test",
        topic_domain="test",
        participant_collective_identity="test participants",
        moderator_knowledge_brief="",
    )
    guide = [
        DiscussionGuideSection(
            section_index=0,
            section_label="main",
            section_phase=SectionPhase.MAIN_TOPIC,
            section_purpose="test",
            scripted_question="Tell us something.",
        )
    ]
    participants = {
        "P1": ParticipantState(id="P1", name="Alice"),
        "P2": ParticipantState(id="P2", name="Bob"),
    }
    return SessionState(
        session_meta=meta,
        discussion_guide=guide,
        participants=participants,
        group_state=GroupState(),
    )


def test_pruned_fields_absent_from_schema():
    fields = ModeratorDecisionResponse.model_fields
    for f in PRUNED_FIELDS + REMOVED_REASONING_FIELDS:
        assert f not in fields, f"{f!r} should have been removed from ModeratorDecisionResponse"


def test_minimal_speak_decision_validates():
    decision = ModeratorDecisionResponse(
        intervention_mode="speak",
        situation_assessment="The group has drifted off the guide question; needs refocusing.",
        dominant_signal="guide_question_pending",
        action="redirect_to_group",
        target="group",
    )
    assert decision.situation_assessment.startswith("The group")
    assert decision.intervention_mode == "speak"


def test_minimal_speak_decision_missing_situation_assessment_fails():
    with pytest.raises(ValidationError):
        ModeratorDecisionResponse(
            intervention_mode="speak",
            dominant_signal="guide_question_pending",
            action="redirect_to_group",
            target="group",
        )


class TestYieldJustifiableByConsensusOnly:
    def test_yield_with_only_consensus_risk_validates(self):
        decision = ModeratorDecisionResponse(
            intervention_mode="yield",
            consensus_risk_assessment=0.7,
        )
        assert decision.consensus_risk_assessment == 0.7

    def test_yield_with_no_tracking_update_raises(self):
        with pytest.raises(ValidationError):
            ModeratorDecisionResponse(intervention_mode="yield")


def test_apply_runs_without_pruned_fields():
    state = _make_state()
    decision = ModeratorDecisionResponse(
        intervention_mode="speak",
        situation_assessment="P1 gave a shallow answer; needs a specificity probe.",
        dominant_signal="response_needs_probing",
        action=ModeratorAction.DIRECT_PROBE,
        target="P1",
        consensus_risk_assessment=0.4,
    )
    response = ModeratorAPIResponse(
        moderator_decision=decision,
        utterance="Can you say more about that?",
    )
    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="It was fine.",
        turn_number=1,
    )

    updated = apply_moderator_response(state, response, trigger)

    assert updated.participants["P1"].turn_count == 1
    assert updated.group_state.consensus_risk == 0.4
    assert len(updated.moderator_log) == 1
    assert updated.moderator_log[-1].situation_assessment == "P1 gave a shallow answer; needs a specificity probe."


def test_template_field_order():
    text = (
        __import__("pathlib").Path("prompts/02_USER_MESSAGE_TEMPLATE.md").read_text(encoding="utf-8")
    )

    task_start = text.index("## YOUR TASK")
    task_block = text[task_start:]

    sa_pos = task_block.index('"situation_assessment"')
    im_pos = task_block.index('"intervention_mode"')
    assert sa_pos < im_pos, "situation_assessment must precede intervention_mode in the task block"

    for f in REMOVED_REASONING_FIELDS + PRUNED_FIELDS:
        assert f not in task_block, f"{f!r} should have been removed from the task block"


def test_opening_prompt_block_validates():
    text = (
        __import__("pathlib").Path("prompts/03_SESSION_OPENING_PROMPT.md").read_text(encoding="utf-8")
    )

    start = text.index('"moderator_decision": {')
    depth = 0
    i = text.index("{", start)
    block_start = i
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                block_end = j + 1
                break
    raw = text[block_start:block_end]

    import json
    data = json.loads(raw)

    decision = ModeratorDecisionResponse.model_validate(data)
    assert decision.intervention_mode == "speak"
    assert decision.situation_assessment
    for f in REMOVED_REASONING_FIELDS + PRUNED_FIELDS:
        assert f not in data
