import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from core.session_state import (
    SessionState, ParticipantEngagementAssessment,
    ModeratorAPIResponse, ModeratorDecisionResponse, ModeratorAction, DominantSignal,
    ProbeType, FollowUpIntensity
)
from core.orchestrator import FocusGroupOrchestrator
from core.config import (
    PEER_ADDRESS_BONUS, CONSENSUS_RISK_CHALLENGE_PREFERENCE, MAX_CONSECUTIVE_PARTICIPANT_TURNS, URGENCY_THRESHOLD
)

@pytest.fixture
def mock_config():
    return {
        "session_id": "smoke_test_grocery_001",
        "research_objective": "Test",
        "topic_domain": "Test",
        "participation_mode": "emergent",
        "temperature": 1.0,
        "participant_collective_identity": "consumers",
        "moderator_knowledge_brief": "brief",
        "researcher_notes": "notes",
        "participants": [
            {"id": "P1", "name": "Sarah", "profile_summary": ""},
            {"id": "P2", "name": "John", "profile_summary": ""},
            {"id": "P3", "name": "Elena", "profile_summary": ""}
        ],
        "discussion_guide": [
            {
                "section_index": 0,
                "section_label": "Intro",
                "section_phase": "intro",
                "section_purpose": "Test",
                "scripted_question": "Test",
                "probing_depth_ceiling": "light",
                "stimulus": None
            }
        ]
    }

@pytest.fixture
def temp_config_file(tmp_path, mock_config):
    config_file = tmp_path / "smoke_test_grocery.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(mock_config, f)
    return config_file

@pytest.fixture
def orchestrator(mock_config, monkeypatch):
    """
    Constructs a FocusGroupOrchestrator and mocks out LLM calls.
    """
    orchestrator = FocusGroupOrchestrator(mock_config)
    
    # Mocking call_participant to prevent live API calls
    monkeypatch.setattr("core.orchestrator.call_participant", MagicMock(return_value=("Mocked participant response.", [])))
    
    # Mocking assess_engagement default to stay_silent
    default_assessment = ParticipantEngagementAssessment(
        participant_id="P1",
        wants_to_speak=False,
        urgency=0.0,
        hook="",
        addressed_to=None,
        intent="stay_silent"
    )
    monkeypatch.setattr("core.orchestrator.assess_engagement", MagicMock(return_value=default_assessment))
    
    # Mocking run_opening to bypass the initial LLM call
    monkeypatch.setattr(orchestrator, "run_opening", MagicMock())
    orchestrator.state.session_meta.total_turns = 1 # mimic post-opening
    
    return orchestrator

def test_addressed_to_resolution(orchestrator, monkeypatch):
    """
    Test 1: addressed_to resolution
    Verify that when one participant addresses another by name, the orchestrator resolves it
    to an internal ID and applies the peer address bonus on the next turn.
    """
    # Force last speaker to be P1 addressing "John" (P2)
    orchestrator.state.transcript.append({
        "turn": 1,
        "speaker_id": "P1",
        "speaker_name": "Sarah",
        "content": "What do you think, John?",
        "timestamp": "2026-05-22T00:00:00Z"
    })
    
    orchestrator.state.group_state.last_engagement_round = [
        ParticipantEngagementAssessment(
            participant_id="P1",
            wants_to_speak=True,
            urgency=0.8,
            hook="Ask John",
            addressed_to="John",
            intent="respond"
        )
    ]

    def mock_assess(participant, *args, **kwargs):
        if participant.id == "P2": # John
            return ParticipantEngagementAssessment(
                participant_id="P2", wants_to_speak=True, urgency=0.50, hook="", addressed_to=None, intent="respond"
            )
        return ParticipantEngagementAssessment(
            participant_id=participant.id, wants_to_speak=False, urgency=0.0, hook="", addressed_to=None, intent="stay_silent"
        )

    monkeypatch.setattr("core.orchestrator.assess_engagement", mock_assess)
    
    # Mock moderator response just to observe
    monkeypatch.setattr("core.orchestrator.call_moderator", MagicMock(return_value=(ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            situation_assessment="Test",
            dominant_signal="response_needs_probing",
            action="stay_silent",
            target="group",
            probe_type=None,
            follow_up_intensity=None,
            next_speaker=None,
            brief_justification="Test",
            justification="Test",
            queued_next_action=None,
            group_dynamic_flags=[]
        ),
        utterance="",
        validation_fallback=False
        ), [])))

    result = orchestrator.run_conversation_step()
    
    assert result["step_type"] == "participant_led"
    assert result["speaker"] == "P2"
    # P2's original urgency was 0.50, but with PEER_ADDRESS_BONUS (0.15) it became 0.65, surpassing URGENCY_THRESHOLD (0.55).
    # Since P2 was selected, the bonus logic worked.
    assert result["selection_mode"] == "voluntary"

def test_consensus_risk_challenge_bonus(orchestrator, monkeypatch):
    """
    Test 2: consensus_risk challenge bonus
    Verify that when group_state.consensus_risk >= 0.65 and a participant's intent is "challenge",
    they receive CONSENSUS_RISK_CHALLENGE_PREFERENCE.
    """
    orchestrator.state.group_state.consensus_risk = 0.65
    
    def mock_assess(participant, *args, **kwargs):
        if participant.id == "P1":
            return ParticipantEngagementAssessment(
                participant_id="P1", wants_to_speak=True, urgency=0.60, hook="", addressed_to=None, intent="respond"
            )
        elif participant.id == "P2":
            return ParticipantEngagementAssessment(
                participant_id="P2", wants_to_speak=True, urgency=0.55, hook="", addressed_to=None, intent="challenge"
            )
        return ParticipantEngagementAssessment(
            participant_id=participant.id, wants_to_speak=False, urgency=0.0, hook="", addressed_to=None, intent="stay_silent"
        )

    monkeypatch.setattr("core.orchestrator.assess_engagement", mock_assess)
    monkeypatch.setattr("core.orchestrator.call_moderator", MagicMock(return_value=(ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            situation_assessment="Test",
            dominant_signal="response_needs_probing",
            action="stay_silent",
            target="group",
            probe_type=None,
            follow_up_intensity=None,
            next_speaker=None,
            brief_justification="Test",
            justification="Test",
            queued_next_action=None,
            group_dynamic_flags=[]
        ),
        utterance="",
        validation_fallback=False
        ), [])))

    result = orchestrator.run_conversation_step()
    
    # P1: 0.60, P2: 0.55 + 0.10 (challenge bonus) = 0.65 -> P2 wins
    assert result["speaker"] == "P2"

def test_moderator_observe_mode(orchestrator, monkeypatch):
    """
    Test 3: moderator observe mode
    Verify that intervention_mode = "observe" records in log but does not output a visible moderator utterance to transcript.
    """
    def mock_assess(participant, *args, **kwargs):
        if participant.id == "P1":
            return ParticipantEngagementAssessment(
                participant_id="P1", wants_to_speak=True, urgency=0.8, hook="", addressed_to=None, intent="respond"
            )
        return ParticipantEngagementAssessment(
            participant_id=participant.id, wants_to_speak=False, urgency=0.0, hook="", addressed_to=None, intent="stay_silent"
        )

    monkeypatch.setattr("core.orchestrator.assess_engagement", mock_assess)
    monkeypatch.setattr("core.orchestrator.call_moderator", MagicMock(return_value=(ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            situation_assessment="Test",
            dominant_signal="response_needs_probing",
            action="stay_silent",
            target="group",
            probe_type=None,
            follow_up_intensity=None,
            next_speaker=None,
            queued_next_action=None,
        ),
        utterance="",
        validation_fallback=False
        ), [])))

    result = orchestrator.run_conversation_step()
    assert result["moderator_intervention_mode"] == "observe"

    # Transcript should not have a moderator turn for this step (only the participant's turn)
    transcript_speakers = [t["speaker_id"] for t in orchestrator.state.transcript]
    assert "MODERATOR" not in transcript_speakers # since we mocked opening too

    # Moderator log should contain the decision
    assert orchestrator.state.moderator_log[-1].intervention_mode == "observe"
    assert orchestrator.state.moderator_log[-1].situation_assessment == "Test"

def test_max_consecutive_participant_turns(orchestrator, monkeypatch):
    """
    Test 4: MAX_CONSECUTIVE_PARTICIPANT_TURNS forced check-in
    Verify that endless participant chains are cut off.
    """
    orchestrator.state.group_state.consecutive_participant_turns = MAX_CONSECUTIVE_PARTICIPANT_TURNS
    
    def mock_assess(participant, *args, **kwargs):
        return ParticipantEngagementAssessment(
            participant_id=participant.id, wants_to_speak=True, urgency=0.9, hook="", addressed_to=None, intent="respond"
        )

    monkeypatch.setattr("core.orchestrator.assess_engagement", mock_assess)
    monkeypatch.setattr("core.orchestrator.call_moderator", MagicMock(return_value=(ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="speak",
            situation_assessment="Test",
            dominant_signal="section_complete",
            action="section_transition",
            target="group",
            probe_type=None,
            follow_up_intensity=None,
            next_speaker=None,
            brief_justification="Time to move on",
            justification="Test",
            queued_next_action=None,
            group_dynamic_flags=[]
        ),
        utterance="Let's move on.",
        validation_fallback=False
        ), [])))

    result = orchestrator.run_conversation_step()
    
    # Because of forced intervention, it skips the willing participants and forces moderator check-in.
    # Wait, looking at orchestrator logic, if max turns reached, next_pid becomes None, which triggers silence_or_forced
    assert result["step_type"] == "moderator_intervention"
    assert result["selection_mode"] == "moderator_forced_by_consecutive_turns"
    assert orchestrator.state.moderator_log[-1].selection_mode == "moderator_forced_by_consecutive_turns"


def _mock_moderator_redirect():
    """Moderator response used by the dominant-voice gate tests (no live API call)."""
    return MagicMock(return_value=(ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="speak",
            situation_assessment="Test",
            dominant_signal="section_complete",
            action="redirect_to_group",
            target="group",
            probe_type=None,
            follow_up_intensity=None,
            next_speaker=None,
            brief_justification="Opening the floor",
            justification="Test",
            queued_next_action=None,
            group_dynamic_flags=[]
        ),
        utterance="Let's hear from others too.",
        validation_fallback=False
        ), []))


def test_dominant_voice_gate_forces_moderator_intervention(orchestrator, monkeypatch):
    """
    Dominant-speaker code safeguard: a participant who has taken >50% of the current
    section's turns (with a minimum section sample of 4) must not be allowed to keep
    taking turns — the orchestrator forces a moderator intervention instead, mirroring
    MAX_CONSECUTIVE_PARTICIPANT_TURNS's own enforcement shape.
    """
    orchestrator.state.group_state.section_turn_counts = {"P1": 3, "P2": 1}
    orchestrator.state.group_state.dominant_voices = ["P1"]
    # Isolate the cause: the sibling consecutive-turns gate must be nowhere near
    # firing, so a forced intervention here can only come from the dominant-voice gate.
    orchestrator.state.group_state.consecutive_participant_turns = 0

    def mock_assess(participant, *args, **kwargs):
        # P1 (the dominant voice) is the one wanting to speak next — this is exactly the
        # case the gate must intercept. Everyone else stays silent so P1 wins the auction.
        if participant.id == "P1":
            return ParticipantEngagementAssessment(
                participant_id="P1", wants_to_speak=True, urgency=0.9, hook="",
                addressed_to=None, intent="respond"
            )
        return ParticipantEngagementAssessment(
            participant_id=participant.id, wants_to_speak=False, urgency=0.0, hook="",
            addressed_to=None, intent="stay_silent"
        )

    monkeypatch.setattr("core.orchestrator.assess_engagement", mock_assess)
    monkeypatch.setattr("core.orchestrator.call_moderator", _mock_moderator_redirect())

    result = orchestrator.run_conversation_step()

    assert result["step_type"] == "moderator_intervention"
    # INSTRUCTIONS_FORCED_INTERVENTION_LABEL_FIX.md makes this label gate-specific:
    # the else-branch now propagates whichever gate fired instead of collapsing both
    # (and genuine silence) into "silence_or_forced".
    assert result["selection_mode"] == "moderator_forced_by_dominant_voice"
    assert orchestrator.state.moderator_log[-1].selection_mode == "moderator_forced_by_dominant_voice"
    # The dominant participant was blocked from taking the turn.
    assert "participant_response" not in result
    assert "P1" not in [t["speaker_id"] for t in orchestrator.state.transcript]


def test_dominant_voice_gate_does_not_fire_below_minimum_section_sample(orchestrator, monkeypatch):
    """
    The >50% ratio must not force an intervention when the section has too few turns to
    make the ratio meaningful — otherwise the very first speaker in a new section (100%
    of 1 turn) would trigger this every single time a section starts.
    """
    orchestrator.state.group_state.section_turn_counts = {"P1": 1}
    orchestrator.state.group_state.dominant_voices = ["P1"]  # would be >50%, but sample too small
    orchestrator.state.group_state.consecutive_participant_turns = 0

    def mock_assess(participant, *args, **kwargs):
        if participant.id == "P1":
            return ParticipantEngagementAssessment(
                participant_id="P1", wants_to_speak=True, urgency=0.9, hook="",
                addressed_to=None, intent="respond"
            )
        return ParticipantEngagementAssessment(
            participant_id=participant.id, wants_to_speak=False, urgency=0.0, hook="",
            addressed_to=None, intent="stay_silent"
        )

    monkeypatch.setattr("core.orchestrator.assess_engagement", mock_assess)
    monkeypatch.setattr("core.orchestrator.call_moderator", _mock_moderator_redirect())

    result = orchestrator.run_conversation_step()

    assert result["step_type"] == "participant_led"
    assert result["speaker"] == "P1"


def test_genuine_silence_still_uses_generic_label(orchestrator, monkeypatch):
    """
    When nobody volunteers to speak and neither gate has fired, the forced intervention
    must still fall back to the original generic label — the fix only disambiguates the
    two known gate reasons, it must not misattribute genuine silence to either of them.
    """
    orchestrator.state.group_state.consecutive_participant_turns = 0
    orchestrator.state.group_state.dominant_voices = []
    # The orchestrator fixture's default assess_engagement mock already returns
    # wants_to_speak=False / intent="stay_silent" for every participant — no override
    # needed here to get genuine silence. Only call_moderator needs mocking.
    monkeypatch.setattr("core.orchestrator.call_moderator", _mock_moderator_redirect())

    result = orchestrator.run_conversation_step()

    assert result["step_type"] == "moderator_intervention"
    assert result["selection_mode"] == "silence_or_forced"
    assert orchestrator.state.moderator_log[-1].selection_mode == "silence_or_forced"

def test_invalid_moderator_json_retry_and_fallback(orchestrator, monkeypatch):
    """
    Test 5: invalid moderator JSON retry and fallback audit
    Verify that repeated invalid moderator responses produce an auditable fallback response.
    """
    from core.session_state import TriggerEvent, TriggerEventType
    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Sarah",
        content="Test",
        turn_number=1,
        follow_up_count_this_question=0
    )
    
    # Part A: Retry success - mocking the low-level _call_api in moderator_brain to fail once
    call_counts = {"count": 0}
    def mock_call_api(*args, **kwargs):
        call_counts["count"] += 1
        mock_msg = MagicMock()
        mock_content = MagicMock()
        if call_counts["count"] == 1:
            mock_content.text = "INVALID JSON"
        else:
            mock_content.text = '{"moderator_decision": {"intervention_mode": "observe", "action": "stay_silent", "target": "group", "justification": "T", "situation_assessment": "T", "dominant_signal": "conflict_detected", "brief_justification": "T"}}'
        mock_msg.content = [mock_content]
        return mock_msg
    
    monkeypatch.setattr("core.moderator_brain._call_api", mock_call_api)
    
    # Run a single moderator turn
    from core.moderator_brain import call_moderator
    response, _ = call_moderator(orchestrator.state, trigger, orchestrator.log_dir)
    assert response.validation_fallback is False
    assert response.moderator_decision.intervention_mode == "observe"
    assert call_counts["count"] == 2 # retried once
    
    # Part B: Fallback after repeated failure
    def mock_call_api_always_fail(*args, **kwargs):
        mock_msg = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "INVALID JSON"
        mock_msg.content = [mock_content]
        return mock_msg
    
    monkeypatch.setattr("core.moderator_brain._call_api", mock_call_api_always_fail)
    
    response_fallback, _ = call_moderator(orchestrator.state, trigger, orchestrator.log_dir)
    assert response_fallback.validation_fallback is True
    assert response_fallback.moderator_decision.intervention_mode == "observe"
    assert response_fallback.moderator_decision.action is None
