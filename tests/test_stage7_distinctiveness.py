import pytest
from assessment.schema import SessionArtifacts, SpeakerStats
from assessment.metrics import compute_distinctiveness_metrics

def test_distinctiveness_metrics():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "I think it is definitely good."},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "Well, maybe it is okay, I mean... no, I should say it is bad."}
        ]
    )
    speaker_stats = {"P1": SpeakerStats(speaker_id="P1", speaker_name="Alice"), "P2": SpeakerStats(speaker_id="P2", speaker_name="Bob")}
    track = compute_distinctiveness_metrics(artifacts, speaker_stats)
    
    assert track.metrics["p_P1_lexical_diversity"].value > 0
    assert track.metrics["p_P1_first_person_rate"].value > 0
    assert track.metrics["p_P2_repair_rate"].value > 0
    assert track.metrics["p_P2_hedging_rate"].value > 0
    assert track.metrics["participant_lexical_diversity_range"].value >= 0
    assert not any(f.flag_id == "ZERO_REPAIR_RATE" for f in track.flags)
    
def test_distinctiveness_zero_repairs():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "I am certain."}
        ]
    )
    speaker_stats = {"P1": SpeakerStats(speaker_id="P1", speaker_name="Alice")}
    track = compute_distinctiveness_metrics(artifacts, speaker_stats)
    assert any(f.flag_id == "ZERO_REPAIR_RATE" for f in track.flags)
