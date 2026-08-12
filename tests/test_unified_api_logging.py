import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.api_logging import append_api_log
from core.moderator_brain import call_moderator
from core.participant_agent import assess_engagement, call_participant
from core.session_state import (
    TriggerEvent,
    TriggerEventType,
    SessionState,
    SessionMeta,
    ParticipantState,
    GroupState,
)

@pytest.fixture
def base_state():
    return SessionState(
        session_meta=SessionMeta(
            id="test",
            research_objective="test",
            topic_domain="test",
            participant_collective_identity="test",
            moderator_knowledge_brief="test"
        ),
        discussion_guide=[],
        participants={
            "P1": ParticipantState(
                id="P1",
                name="Alice",
                agent_payload={}
            )
        },
        group_state=GroupState(),
        moderator_log=[],
        transcript=[]
    )

def test_shared_logger_writes_valid_jsonl(tmp_path):
    # A. Shared logger writes valid JSONL
    append_api_log(
        log_dir=tmp_path,
        event_type="test_event",
        role="test_role",
        model="test_model",
        input_tokens=10,
        output_tokens=20,
        participant_id="P1",
        moderator_action=None,
        metadata={"foo": "bar"}
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    
    data = json.loads(log_file.read_text().strip())
    assert data["event_type"] == "test_event"
    assert data["role"] == "test_role"
    assert data["model"] == "test_model"
    assert data["input_tokens"] == 10
    assert data["output_tokens"] == 20
    assert data["total_tokens"] == 30
    assert data["participant_id"] == "P1"
    assert "moderator_action" not in data
    assert data["foo"] == "bar"

@patch("core.moderator_brain.anthropic.Anthropic")
def test_moderator_logging_still_works(mock_anthropic, base_state, tmp_path):
    # B. Moderator logging still works
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_message = MagicMock()
    # E. No unsafe action=None serialization (action=null here)
    mock_message.content = [MagicMock(text='{"moderator_decision": {"intervention_mode": "observe", "brief_justification": "Testing.", "action": null, "target": null, "justification": null, "consensus_risk_assessment": 0.5, "emotional_signals": [], "new_contradictions": [], "new_emergent_themes": [], "new_easy_agreements": []}}')]
    mock_message.usage = MagicMock(input_tokens=10, output_tokens=20)
    mock_client.messages.create.return_value = mock_message

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=1,
    )
    
    # E. Verify logging action=None or intervention_mode observe does not crash.
    response, _ = call_moderator(
        state=base_state,
        trigger_event=trigger,
        conversation_history=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split('\n')
    data = json.loads(lines[-1])
    
    assert data["event_type"] == "moderator_decision"
    assert data["role"] == "moderator"
    assert data["moderator_action"] == "none"
    assert data["action"] == "none"
    assert data["intervention_mode"] == "observe"

@patch("core.participant_agent.anthropic.Anthropic")
def test_participant_engagement_logging_works(mock_anthropic, base_state, tmp_path):
    # C. Participant engagement logging works
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"wants_to_speak": true, "urgency": 0.9, "hook": "test hook", "intent": "respond"}')]
    mock_message.usage = MagicMock(input_tokens=5, output_tokens=15)
    mock_client.messages.create.return_value = mock_message
    
    assess_engagement(
        participant=base_state.participants["P1"],
        session_meta=base_state.session_meta,
        recent_transcript=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    data = json.loads(log_file.read_text().strip())
    
    assert data["event_type"] == "participant_engagement_assessment"
    assert data["role"] == "participant"
    assert data["participant_id"] == "P1"
    assert data["source_function"] == "assess_engagement"
    assert data["input_tokens"] == 5

@patch("core.participant_agent.anthropic.Anthropic")
def test_participant_response_logging_works(mock_anthropic, base_state, tmp_path):
    # D. Participant response logging works
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='I agree')]
    mock_message.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_client.messages.create.return_value = mock_message
    
    call_participant(
        participant=base_state.participants["P1"],
        session_meta=base_state.session_meta,
        moderator_utterance="Hello",
        conversation_history=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    data = json.loads(log_file.read_text().strip())
    
    assert data["event_type"] == "participant_response_generation"
    assert data["role"] == "participant"
    assert data["participant_id"] == "P1"
    assert data["source_function"] == "call_participant"
    assert data["total_tokens"] == 150
