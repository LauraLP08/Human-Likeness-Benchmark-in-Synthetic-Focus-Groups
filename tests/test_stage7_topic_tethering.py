import pytest
from assessment.schema import SessionArtifacts
from assessment.metrics import compute_topic_metrics

def test_topic_tethering_markers():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "I ordered £10 of groceries last week from Tesco."},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "Society is an inevitable structure of capitalism."}
        ]
    )
    track = compute_topic_metrics(artifacts)
    assert track.metrics["concrete_markers"].value > 0
    assert track.metrics["abstract_markers"].value > 0
    assert track.metrics["topic_terms_used_count"].value > 0
    assert track.metrics["abstract_only_turns"].value == 1

def test_topic_tethering_configurable():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "I bought some apples."},
        ]
    )
    track = compute_topic_metrics(artifacts, topic_terms=["apples", "bananas"])
    assert track.metrics["topic_terms_used_count"].value == 1
    assert track.metrics["topic_dictionary_version"].value == "custom"
