import pytest
from assessment.schema import SessionArtifacts
from assessment.interaction_graph import build_interaction_graph

def test_interaction_graph_edges_exported():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi"},
            {"turn": 2, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Alice, what do you think?"},
            {"turn": 3, "speaker_id": "P1", "speaker_name": "Alice", "content": "I think..."}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    assert len(edges) > 0
    assert any(e["source"] == "MODERATOR" and e["target"] == "P1" for e in edges)
    assert track.metrics["total_edges"].value == len(edges)

def test_interaction_graph_first_name():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Daniel Whitmore", "content": "Hi"},
            {"turn": 2, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Daniel, what do you think?"}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    assert any(e["source"] == "MODERATOR" and e["target"] == "P1" for e in edges)
    assert track.metrics["first_name_match_count"].value > 0

def test_interaction_graph_full_name():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Maya Chen", "content": "Hi"},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "I agree with Maya Chen."}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    assert any(e["source"] == "P2" and e["target"] == "P1" for e in edges)
    assert track.metrics["full_name_match_count"].value > 0

def test_adjacent_uptake_edge():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "I think this.", "speaker_role": "participant"},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "Me too.", "speaker_role": "participant"}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    assert any(e["source"] == "P2" and e["target"] == "P1" and e["type"] == "adjacent_uptake" for e in edges)

def test_edge_density_bounded_and_repeated():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi", "speaker_role": "participant"},
            {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "content": "Hi", "speaker_role": "participant"},
            {"turn": 3, "speaker_id": "P1", "speaker_name": "Alice", "content": "Alice agrees with Bob", "speaker_role": "participant"},
            {"turn": 4, "speaker_id": "P2", "speaker_name": "Bob", "content": "Alice again", "speaker_role": "participant"}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    density = track.metrics["participant_to_participant_edge_density"].value
    assert 0 <= density <= 1.0
    assert density == 1.0

def test_edge_density_insufficient_sample():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi", "speaker_role": "participant"}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    metric = track.metrics["participant_to_participant_edge_density"]
    assert metric.value == 0.0
    assert metric.status == "INSUFFICIENT_SAMPLE"

def test_moderator_does_not_create_adjacent_p2p():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi", "speaker_role": "participant"},
            {"turn": 2, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "What about Bob?", "speaker_role": "moderator"},
            {"turn": 3, "speaker_id": "P2", "speaker_name": "Bob", "content": "Hello", "speaker_role": "participant"}
        ]
    )
    track, edges = build_interaction_graph(artifacts)
    assert not any(e["source"] == "P2" and e["target"] == "P1" and e["type"] == "adjacent_uptake" for e in edges)
