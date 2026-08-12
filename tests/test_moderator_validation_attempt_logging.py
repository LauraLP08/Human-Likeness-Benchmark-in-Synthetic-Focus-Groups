import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.moderator_brain import call_moderator
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

@patch("core.moderator_brain.anthropic.Anthropic")
def test_successful_first_attempt(mock_anthropic, base_state, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    msg1 = MagicMock()
    valid_json = '{"moderator_decision": {"intervention_mode": "observe", "brief_justification": "Testing.", "action": null, "target": null, "justification": null, "consensus_risk_assessment": 0.5, "emotional_signals": [], "new_contradictions": [], "new_emergent_themes": [], "new_easy_agreements": []}}'
    msg1.content = [MagicMock(text=valid_json)]
    msg1.usage = MagicMock(input_tokens=10, output_tokens=5)
    mock_client.messages.create.return_value = msg1

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=1,
    )
    
    response, _ = call_moderator(
        state=base_state,
        trigger_event=trigger,
        conversation_history=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split('\n')
    assert len(lines) == 2
    
    # First attempt
    log1 = json.loads(lines[0])
    assert log1["event_type"] == "moderator_decision_attempt"
    assert log1["token_accounting"] is True
    assert log1["input_tokens"] == 10
    assert log1["parse_success"] is True
    assert log1["validation_success"] is True
    
    # Final
    log2 = json.loads(lines[1])
    assert log2["event_type"] == "moderator_decision"
    assert log2["token_accounting"] is False
    assert "input_tokens" not in log2
    assert "output_tokens" not in log2

@patch("core.moderator_brain.anthropic.Anthropic")
def test_invalid_json_first_attempt_valid_retry(mock_anthropic, base_state, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    # First response: invalid JSON
    msg1 = MagicMock()
    msg1.content = [MagicMock(text='This is not json.')]
    msg1.usage = MagicMock(input_tokens=10, output_tokens=5)
    
    # Second response: valid JSON
    msg2 = MagicMock()
    valid_json = '{"moderator_decision": {"intervention_mode": "observe", "brief_justification": "Testing.", "action": null, "target": null, "justification": null, "consensus_risk_assessment": 0.5, "emotional_signals": [], "new_contradictions": [], "new_emergent_themes": [], "new_easy_agreements": []}}'
    msg2.content = [MagicMock(text=valid_json)]
    msg2.usage = MagicMock(input_tokens=15, output_tokens=30)
    
    mock_client.messages.create.side_effect = [msg1, msg2]

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=1,
    )
    
    response, _ = call_moderator(
        state=base_state,
        trigger_event=trigger,
        conversation_history=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split('\n')
    assert len(lines) == 3
    
    # First attempt
    log1 = json.loads(lines[0])
    assert log1["event_type"] == "moderator_decision_attempt"
    assert log1["parse_success"] is False
    assert log1["validation_success"] is False
    assert log1["error_type"] == "json_parse_error"
    assert log1["token_accounting"] is True
    assert log1["input_tokens"] == 10
    
    # Second attempt
    log2 = json.loads(lines[1])
    assert log2["event_type"] == "moderator_decision_retry_attempt"
    assert log2["parse_success"] is True
    assert log2["validation_success"] is True
    assert log2["token_accounting"] is True
    assert log2["input_tokens"] == 15
    
    # Final
    log3 = json.loads(lines[2])
    assert log3["event_type"] == "moderator_decision"
    assert log3["token_accounting"] is False
    assert "input_tokens" not in log3

@patch("core.moderator_brain.anthropic.Anthropic")
def test_schema_invalid_first_attempt(mock_anthropic, base_state, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    # First response: invalid Pydantic (missing required fields)
    msg1 = MagicMock()
    msg1.content = [MagicMock(text='{"moderator_decision": {}}')]
    msg1.usage = MagicMock(input_tokens=10, output_tokens=5)
    
    # Second response: valid JSON
    msg2 = MagicMock()
    valid_json = '{"moderator_decision": {"intervention_mode": "observe", "brief_justification": "Testing.", "action": null, "target": null, "justification": null, "consensus_risk_assessment": 0.5, "emotional_signals": [], "new_contradictions": [], "new_emergent_themes": [], "new_easy_agreements": []}}'
    msg2.content = [MagicMock(text=valid_json)]
    msg2.usage = MagicMock(input_tokens=15, output_tokens=30)
    
    mock_client.messages.create.side_effect = [msg1, msg2]

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=1,
    )
    
    response, _ = call_moderator(
        state=base_state,
        trigger_event=trigger,
        conversation_history=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split('\n')
    assert len(lines) == 3
    
    # First attempt
    log1 = json.loads(lines[0])
    assert log1["event_type"] == "moderator_decision_attempt"
    assert log1["parse_success"] is True
    assert log1["validation_success"] is False
    assert log1["error_type"] == "pydantic_validation_error"
    assert log1["token_accounting"] is True
    
    # Second attempt
    log2 = json.loads(lines[1])
    assert log2["event_type"] == "moderator_decision_retry_attempt"
    assert log2["parse_success"] is True
    assert log2["validation_success"] is True
    assert log2["token_accounting"] is True
    
    # Final
    log3 = json.loads(lines[2])
    assert log3["event_type"] == "moderator_decision"
    assert log3["token_accounting"] is False
    assert "input_tokens" not in log3

@patch("core.moderator_brain.anthropic.Anthropic")
def test_invalid_json_both_attempts_fallback(mock_anthropic, base_state, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    # First response: invalid JSON
    msg1 = MagicMock()
    msg1.content = [MagicMock(text='This is not json.')]
    msg1.usage = MagicMock(input_tokens=10, output_tokens=5)
    
    # Second response: invalid JSON
    msg2 = MagicMock()
    msg2.content = [MagicMock(text='Still not json.')]
    msg2.usage = MagicMock(input_tokens=15, output_tokens=5)
    
    mock_client.messages.create.side_effect = [msg1, msg2]

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=1,
    )
    
    response, _ = call_moderator(
        state=base_state,
        trigger_event=trigger,
        conversation_history=[],
        log_dir=tmp_path
    )
    
    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split('\n')
    assert len(lines) == 3
    
    # First attempt
    log1 = json.loads(lines[0])
    assert log1["event_type"] == "moderator_decision_attempt"
    assert log1["parse_success"] is False
    assert log1["validation_success"] is False
    assert log1["token_accounting"] is True
    
    # Second attempt
    log2 = json.loads(lines[1])
    assert log2["event_type"] == "moderator_decision_retry_attempt"
    assert log2["parse_success"] is False
    assert log2["validation_success"] is False
    assert log2["token_accounting"] is True
    
    # Final fallback
    log3 = json.loads(lines[2])
    assert log3["event_type"] == "moderator_decision_fallback"
    assert log3["token_accounting"] is False
    assert "input_tokens" not in log3
    
    assert response.moderator_decision.intervention_mode == "observe"
    assert response.moderator_decision.action is None
