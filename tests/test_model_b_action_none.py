import json
import pytest
from unittest.mock import patch, MagicMock

from core.orchestrator import FocusGroupOrchestrator
from core.session_state import TriggerEvent, TriggerEventType, ParticipantEngagementAssessment, ModeratorAPIResponse, ModeratorDecisionResponse
from core.moderator_brain import call_moderator

@pytest.fixture
def base_config():
    return {
        "session_id": "test_action_none",
        "research_objective": "Test",
        "topic_domain": "Test",
        "participant_collective_identity": "Test users",
        "moderator_knowledge_brief": "Test",
        "participants": [
            {"id": "P1", "name": "Alice"}
        ],
        "discussion_guide": [
            {
                "section_index": 0,
                "section_label": "Intro",
                "section_phase": "intro",
                "section_purpose": "Welcome",
                "scripted_question": "Hello",
                "probing_depth_ceiling": "light"
            }
        ]
    }

@patch("core.moderator_brain.anthropic.Anthropic")
def test_moderator_api_logging_with_action_none(mock_anthropic, base_config, tmp_path):
    # A. Moderator API logging with action=None
    orchestrator = FocusGroupOrchestrator(base_config)
    orchestrator.log_dir = tmp_path
    
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_message = MagicMock()
    # Mock valid API response but with action = null
    mock_message.content = [MagicMock(text='{"moderator_decision": {"intervention_mode": "observe", "brief_justification": "Just observing.", "action": null, "target": null, "justification": null, "consensus_risk_assessment": 0.5, "emotional_signals": [], "new_contradictions": [], "new_emergent_themes": [], "new_easy_agreements": []}}')]
    mock_message.usage = MagicMock(input_tokens=10, output_tokens=20)
    mock_client.messages.create.return_value = mock_message

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello world",
        turn_number=1,
    )
    
    # Should not crash
    response, _ = call_moderator(
        state=orchestrator.state,
        trigger_event=trigger,
        conversation_history=[],
        log_dir=orchestrator.log_dir
    )
    
    assert response.moderator_decision.action is None
    
    # Verify API logging
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split('\n')
    data = json.loads(lines[-1])
    
    assert data["event_type"] == "moderator_decision"


@patch("core.orchestrator.call_participant")
@patch("core.orchestrator.call_moderator")
def test_orchestrator_return_dict_with_action_none(mock_call_mod, mock_call_part, base_config):
    # B. Orchestrator return dict with action=None
    orchestrator = FocusGroupOrchestrator(base_config)
    
    mock_call_part.return_value = ("I am speaking", [])
    
    # Setup moderator response with action=None
    mock_response = ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            action=None,
            target=None,
            dominant_signal="silence_detected",
            situation_assessment="Observing",
            probe_type=None,
            follow_up_intensity=None,
            brief_justification="Testing",
            justification="Testing",
            group_dynamic_flags=[],
            queued_next_action=None,
            consensus_risk_assessment=0.5,
            emotional_signals=[],
            new_contradictions=[],
            new_emergent_themes=[],
            new_easy_agreements=[],
        ),
        utterance="",
        validation_fallback=False
    )
    mock_call_mod.return_value = (mock_response, [])
    
    # Make P1 eligible to speak
    with patch("core.orchestrator.assess_engagement") as mock_assess:
        mock_assessment = ParticipantEngagementAssessment(
            participant_id="P1",
            wants_to_speak=True,
            intent="respond",
            urgency=0.9,
            hook="hook",
        )
        mock_assess.return_value = mock_assessment
        
        # Should not crash
        result = orchestrator.run_conversation_step()
        
        assert result["moderator_action"] == "none"
        assert result["moderator_intervention_mode"] == "observe"


@patch("core.orchestrator.call_participant")
@patch("core.orchestrator.call_moderator")
def test_transcript_visibility_with_action_none(mock_call_mod, mock_call_part, base_config):
    # C. Transcript visibility
    orchestrator = FocusGroupOrchestrator(base_config)
    
    mock_call_part.return_value = ("I am speaking", [])
    
    mock_response = ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            action=None,
            target=None,
            dominant_signal="silence_detected",
            situation_assessment="Observing",
            probe_type=None,
            follow_up_intensity=None,
            brief_justification="Testing",
            justification="Testing",
            group_dynamic_flags=[],
            queued_next_action=None,
            consensus_risk_assessment=0.5,
            emotional_signals=[],
            new_contradictions=[],
            new_emergent_themes=[],
            new_easy_agreements=[],
        ),
        utterance="",
        validation_fallback=False
    )
    mock_call_mod.return_value = (mock_response, [])
    
    # Make P1 eligible to speak
    with patch("core.orchestrator.assess_engagement") as mock_assess:
        mock_assessment = ParticipantEngagementAssessment(
            participant_id="P1",
            wants_to_speak=True,
            intent="respond",
            urgency=0.9,
            hook="hook",
        )
        mock_assess.return_value = mock_assessment
        
        orchestrator.run_conversation_step()
        
        # Verify moderator_log has the entry
        assert len(orchestrator.state.moderator_log) == 1
        assert orchestrator.state.moderator_log[0].action is None
        
        # Verify transcript does NOT have a moderator utterance
        # It should only have the participant utterance
        assert len(orchestrator.state.transcript) == 1
        assert orchestrator.state.transcript[-1]["speaker_id"] == "P1"
