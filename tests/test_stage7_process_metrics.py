import pytest
from assessment.schema import SessionArtifacts, SpeakerStats
from assessment.metrics import compute_process_metrics

def test_process_metrics_insufficient_participants():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi"},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "Hello"}
        ]
    )
    speaker_stats = {}
    track = compute_process_metrics(artifacts, speaker_stats)
    assert track.status == "FAIL"
    assert any(f.flag_id == "INSUFFICIENT_PARTICIPANTS" for f in track.flags)

def test_process_metrics_valid():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "One two three"},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "Four five"},
            {"turn": 3, "speaker_id": "P3", "speaker_name": "Charlie", "content": "Six seven eight nine"},
        ]
    )
    speaker_stats = {}
    track = compute_process_metrics(artifacts, speaker_stats)
    assert track.status != "FAIL"
    assert track.metrics["participant_count"].value == 3
    assert len(speaker_stats) == 3
    assert speaker_stats["P1"].word_count == 3
    assert speaker_stats["P2"].word_count == 2
    assert speaker_stats["P3"].word_count == 4
