import pytest
from assessment.schema import SessionArtifacts
from assessment.metrics import compute_mechanical_integrity

def test_mechanical_integrity_valid():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Hello"},
            {"turn": 2, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi"}
        ],
        run_metadata={
            "selection_mode_counts": {"moderator_intervention": 1, "voluntary": 1},
            "participant_response_truncation_count": 0
        }
    )
    track = compute_mechanical_integrity(artifacts)
    assert track.status == "PASS"
    assert track.metrics["visible_utterance_count"].value == 2
    assert track.metrics["transcript_moderator_count"].value == 1
    assert track.metrics["transcript_participant_count"].value == 1
    assert track.metrics["stage_direction_count"].value == 0

def test_mechanical_integrity_truncation():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[{"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Hello"}],
        run_metadata={"participant_response_truncation_count": 1}
    )
    track = compute_mechanical_integrity(artifacts)
    assert track.status == "FAIL"
    assert any(f.flag_id == "PARTICIPANT_TRUNCATION" for f in track.flags)

def test_mechanical_integrity_stage_directions():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[{"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "*laughs* Yes"}],
        run_metadata={}
    )
    track = compute_mechanical_integrity(artifacts)
    assert track.status == "WARNING"
    assert any(f.flag_id == "STAGE_DIRECTIONS_DETECTED" for f in track.flags)
