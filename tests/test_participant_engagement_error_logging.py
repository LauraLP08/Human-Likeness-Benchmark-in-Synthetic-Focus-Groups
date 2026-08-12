import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.participant_agent import assess_engagement, ParticipantState
from core.session_state import SessionMeta

@pytest.fixture
def dummy_participant():
    return ParticipantState(
        id="P1",
        name="Alice",
        profile_summary="Alice, 30",
        agent_payload={"simulation_config": {"model": "test-model"}}
    )

@pytest.fixture
def dummy_session_meta():
    return SessionMeta(
        id="test_sess_id",
        session_id="test_sess",
        research_objective="test",
        topic_domain="test",
        moderator_knowledge_brief="test",
        participant_collective_identity="Group",
        temperature=0.7,
        max_turns=5
    )

def test_successful_engagement_assessment(tmp_path, dummy_participant, dummy_session_meta):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"wants_to_speak": true, "urgency": 0.9, "hook": "test", "intent": "respond"}')]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_client.messages.create.return_value = mock_response

    with patch('core.participant_agent.anthropic.Anthropic', return_value=mock_client):
        assessment = assess_engagement(dummy_participant, dummy_session_meta, [], log_dir=log_dir)

    assert assessment.wants_to_speak is True
    assert assessment.urgency == 0.9
    assert assessment.hook == "test"
    assert assessment.intent == "respond"

    log_file = log_dir / "api_calls.jsonl"
    lines = log_file.read_text("utf-8").splitlines()
    assert len(lines) == 1
    
    log_data = json.loads(lines[0])
    assert log_data["event_type"] == "participant_engagement_assessment"
    assert log_data["token_accounting"] is True
    assert log_data["parse_success"] is True
    assert log_data["validation_success"] is True
    assert log_data["error_type"] == "none"
    assert "input_tokens" in log_data

# NOTE ON THE TWO TESTS BELOW (updated 2026-07-29)
#
# These previously asserted that ANY engagement fault silenced the participant
# immediately, with no retry. That contract was the source of a measured bias:
# across 12 completed sessions, 44 participants were forced silent by technical
# faults (1.4%-9.4% of assessments, present in every session), which contaminated
# participation analysis. The tests were codifying the defect, so they were
# rewritten to the corrected contract rather than kept passing.
#
# Deliberately preserved from the originals: token accounting, log structure, and
# the "quiet logging" requirement that warnings must not leak raw exception class
# names. See tests/test_engagement_forced_silence_fix.py for the full coverage.

def test_invalid_json_retries_then_silences_with_distinct_log(
    tmp_path, dummy_participant, dummy_session_meta, caplog
):
    """
    Malformed JSON must now cost a retry before any silence. The mock returns the
    same bad payload for both attempts, so the participant does end up silent —
    but only after two attempts, and flagged as a FORCED silence.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{invalid_json: oops}')]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_client.messages.create.return_value = mock_response

    with patch('core.participant_agent.anthropic.Anthropic', return_value=mock_client):
        assessment = assess_engagement(dummy_participant, dummy_session_meta, [], log_dir=log_dir)

    assert mock_client.messages.create.call_count == 2, "the retry must fire"
    assert assessment.intent == "stay_silent"
    assert assessment.wants_to_speak is False

    lines = (log_dir / "api_calls.jsonl").read_text("utf-8").splitlines()
    assert len(lines) == 2, "first attempt and retry must both be logged"

    first, retry = json.loads(lines[0]), json.loads(lines[1])
    assert first["event_type"] == "participant_engagement_assessment"
    assert first["token_accounting"] is True
    assert first["parse_success"] is False
    assert first["error_type"] == "json_parse_error"

    assert retry["event_type"] == "participant_engagement_assessment_retry"
    assert retry["token_accounting"] is True
    assert retry["validation_success"] is False
    assert retry["error_type"] == "engagement_fallback_after_retry"
    assert retry["first_attempt_error_type"] == "json_parse_error"

    # Quiet logging: informative, but no raw exception class names leaked.
    warnings = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("failed twice for P1" in w for w in warnings), warnings
    assert not any("JSONDecodeError" in w for w in warnings)


def test_unrecognised_intent_is_salvaged_not_silenced(
    tmp_path, dummy_participant, dummy_session_meta, caplog
):
    """
    THE bias case, inverted. `intent` is audit-only per the model's own field
    docs, so an out-of-enum value must not cost the participant their turn: the
    intent is nulled, wants_to_speak survives, and no retry is spent.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"wants_to_speak": true, "urgency": 0.9, "hook": "test", "intent": "invalid_enum_val"}')]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_client.messages.create.return_value = mock_response

    with patch('core.participant_agent.anthropic.Anthropic', return_value=mock_client):
        assessment = assess_engagement(dummy_participant, dummy_session_meta, [], log_dir=log_dir)

    assert mock_client.messages.create.call_count == 1, "salvage must not cost a retry"
    assert assessment.wants_to_speak is True, "participant was silenced over audit data"
    assert assessment.urgency == 0.9
    assert assessment.hook == "test"
    assert assessment.intent is None

    lines = (log_dir / "api_calls.jsonl").read_text("utf-8").splitlines()
    assert len(lines) == 1

    log_data = json.loads(lines[0])
    assert log_data["event_type"] == "participant_engagement_assessment"
    assert log_data["token_accounting"] is True
    assert log_data["parse_success"] is True
    assert log_data["validation_success"] is True
    assert log_data["error_type"] == "none"
    # The coercion stays visible for audit.
    assert "intent" in log_data["fields_coerced"]

    # No forced-silence warning should have been emitted at all.
    warnings = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
    assert not any("stay_silent" in w for w in warnings), warnings
