"""
Offline verification (mocked client, no live API) that call_moderator selects
the correct max_tokens ceiling per turn type:

- is_opening_turn=True  -> _OPENING_TURN_MAX_TOKENS (4096)
- is_opening_turn=False -> _MAX_TOKENS (1500)

This is the fix for the truncation found in the sandbox_minimal_prompt_budget_01
pilot: the opening turn's schema (5x participant_notes + risk_conditions +
directivity_plan + 3-section time_budget + moderator_decision + utterance) was
too large for the fixed 1500-token ceiling, causing both the initial attempt
and the retry to hit output_tokens=1500 with a json_parse_error and fall back.

What this test CANNOT verify: whether 4096 tokens is actually enough for the
opening turn's real schema against the real model. That can only be confirmed
by a live pilot run — this is offline, mocked-client verification of the
max_tokens value passed to the API, nothing more.
"""

from unittest.mock import patch, MagicMock

from core.moderator_brain import call_moderator, _MAX_TOKENS, _OPENING_TURN_MAX_TOKENS
from core.session_state import (
    TriggerEvent,
    TriggerEventType,
    SessionState,
    SessionMeta,
    ParticipantState,
    GroupState,
)


def _base_state():
    return SessionState(
        session_meta=SessionMeta(
            id="test",
            research_objective="test",
            topic_domain="test",
            participant_collective_identity="test",
            moderator_knowledge_brief="test",
        ),
        discussion_guide=[],
        participants={
            "P1": ParticipantState(id="P1", name="Alice", agent_payload={}),
        },
        group_state=GroupState(),
        moderator_log=[],
        transcript=[],
    )


def _valid_observe_json() -> str:
    return (
        '{"moderator_decision": {"intervention_mode": "observe", '
        '"action": null, "target": null, "consensus_risk_assessment": 0.5, '
        '"emotional_signals": [], "new_contradictions": [], "new_easy_agreements": []}}'
    )


@patch("core.moderator_brain.anthropic.Anthropic")
def test_opening_turn_uses_4096_max_tokens(mock_anthropic):
    assert _OPENING_TURN_MAX_TOKENS == 4096

    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    msg = MagicMock()
    msg.content = [MagicMock(text=_valid_observe_json())]
    msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    mock_client.messages.create.return_value = msg

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=0,
    )

    call_moderator(
        state=_base_state(),
        trigger_event=trigger,
        conversation_history=[],
        is_opening_turn=True,
    )

    assert mock_client.messages.create.call_count == 1
    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["max_tokens"] == 4096


@patch("core.moderator_brain.anthropic.Anthropic")
def test_non_opening_turn_uses_1500_max_tokens(mock_anthropic):
    assert _MAX_TOKENS == 1500

    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    msg = MagicMock()
    msg.content = [MagicMock(text=_valid_observe_json())]
    msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    mock_client.messages.create.return_value = msg

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=3,
    )

    call_moderator(
        state=_base_state(),
        trigger_event=trigger,
        conversation_history=[],
        is_opening_turn=False,
    )

    assert mock_client.messages.create.call_count == 1
    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["max_tokens"] == 1500


@patch("core.moderator_brain.anthropic.Anthropic")
def test_opening_turn_retry_also_uses_4096(mock_anthropic):
    """Both the first attempt AND the retry must use the opening-turn ceiling —
    the truncation bug in the pilot hit BOTH attempts, not just the first."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    bad_msg = MagicMock()
    bad_msg.content = [MagicMock(text="not json")]
    bad_msg.usage = MagicMock(input_tokens=10, output_tokens=5)

    good_msg = MagicMock()
    good_msg.content = [MagicMock(text=_valid_observe_json())]
    good_msg.usage = MagicMock(input_tokens=15, output_tokens=30)

    mock_client.messages.create.side_effect = [bad_msg, good_msg]

    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="Hello",
        turn_number=0,
    )

    call_moderator(
        state=_base_state(),
        trigger_event=trigger,
        conversation_history=[],
        is_opening_turn=True,
    )

    assert mock_client.messages.create.call_count == 2
    for call in mock_client.messages.create.call_args_list:
        assert call.kwargs["max_tokens"] == 4096
