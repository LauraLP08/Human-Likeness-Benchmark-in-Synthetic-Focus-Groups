import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.participant_agent import _BEHAVIOUR_INSTRUCTIONS, call_participant
from core.session_state import ParticipantState, SessionMeta
from core.api_logging import append_api_log
from scripts.run_live_pilot import main

def test_participant_behaviour_instructions_cleanup():
    # Should NOT contain old overly-prescriptive terms
    prohibited_phrases = [
        "2–5 sentences",
        "lived experience",
        "contradictions",
        "frustrations",
        "ambivalence",
        "trade-offs"
    ]
    for phrase in prohibited_phrases:
        assert phrase not in _BEHAVIOUR_INSTRUCTIONS, f"Found prohibited phrase '{phrase}' in _BEHAVIOUR_INSTRUCTIONS"

    # Should contain new stance terms
    required_phrases = [
        "willing to participate",
        "participant profile",
        "Do not try to produce an ideal qualitative-research answer",
        "theatrical stage directions"
    ]
    for phrase in required_phrases:
        assert phrase in _BEHAVIOUR_INSTRUCTIONS, f"Missing required phrase '{phrase}' in _BEHAVIOUR_INSTRUCTIONS"

@patch("core.participant_agent.anthropic.Anthropic")
def test_participant_response_logging_includes_stop_reason_and_truncation(mock_anthropic, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="I have thoughts.")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 400
    mock_response.stop_reason = "max_tokens"
    mock_client.messages.create.return_value = mock_response

    participant = ParticipantState(id="p1", name="Test Participant")
    session_meta = SessionMeta(
        id="test_session",
        research_objective="Test",
        topic_domain="Test",
        participant_collective_identity="Test",
        moderator_knowledge_brief="Test",
        participant_response_max_tokens=400
    )

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    call_participant(
        participant=participant,
        session_meta=session_meta,
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=log_dir
    )

    api_calls_path = log_dir / "api_calls.jsonl"
    assert api_calls_path.exists()
    
    with open(api_calls_path, "r", encoding="utf-8") as f:
        log_entry = json.loads(f.readline())
        
    assert log_entry["event_type"] == "participant_response_generation"
    assert log_entry["stop_reason"] == "max_tokens"
    assert log_entry["max_tokens"] == 400
    assert log_entry["response_truncated"] is True

@patch("scripts.run_live_pilot.FocusGroupOrchestrator")
@patch("scripts.run_live_pilot.argparse.ArgumentParser")
def test_run_metadata_counts_participant_truncations(mock_parser, mock_orchestrator, tmp_path):
    # Setup args
    mock_args = MagicMock()
    mock_args.config = str(tmp_path / "config.json")
    mock_args.max_steps = 1
    mock_args.run_id = "test_truncation_run"
    mock_args.dry_run = False
    mock_args.confirm_live = True
    mock_parser.return_value.parse_args.return_value = mock_args

    # Create dummy config
    config_data = {
        "session_id": "base",
        "research_objective": "test",
        "topic_domain": "test",
        "participant_collective_identity": "test",
        "moderator_knowledge_brief": "test",
        "participants": [],
        "discussion_guide": [{"section_index": 1, "section_label": "Intro", "section_phase": "Opening", "section_purpose": "Intro", "scripted_question": "Hi", "probing_depth_ceiling": "shallow"}]
    }
    with open(mock_args.config, "w") as f:
        json.dump(config_data, f)

    # Setup orchestrator
    mock_orch_instance = MagicMock()
    mock_orch_instance.log_dir = tmp_path / "output_dir"
    mock_orch_instance.log_dir.mkdir()
    
    # Create fake state
    mock_state = MagicMock()
    mock_state.moderator_log = []
    mock_state.transcript = []
    mock_state.model_dump_json.return_value = "{}"
    mock_orch_instance.state = mock_state
    
    mock_orchestrator.return_value = mock_orch_instance

    # Create a dummy api_calls.jsonl with some truncations
    api_calls_path = mock_orch_instance.log_dir / "api_calls.jsonl"
    with open(api_calls_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"response_truncated": True}) + "\n")
        f.write(json.dumps({"response_truncated": False}) + "\n")
        f.write(json.dumps({"response_truncated": True}) + "\n")

    # Call main
    main()

    # Verify run_metadata.json
    meta_path = mock_orch_instance.log_dir / "run_metadata.json"
    assert meta_path.exists()
    
    with open(meta_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
        
    assert meta_data["participant_response_truncation_count"] == 2
