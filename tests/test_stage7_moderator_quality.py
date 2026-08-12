import pytest
from assessment.schema import SessionArtifacts
from assessment.metrics import compute_moderator_metrics

def test_moderator_quality_overvalidation_real_fields():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "That is a powerful insight. Thank you."}
        ],
        moderator_log=[
            {
                "turn": 1, 
                "action": "direct_probe", 
                "situation_assessment": "This is sophisticated.",
                "brief_justification": "Very powerful stuff.",
                "justification": "Rich data indeed."
            }
        ]
    )
    track = compute_moderator_metrics(artifacts)
    assert track.metrics["internal_overvalidation_entries_with_hits"].value == 1
    assert track.metrics["internal_overvalidation_phrase_hits"].value == 3
    assert track.metrics["internal_overvalidation_entry_rate"].value == 1.0
    assert any(f.flag_id == "HIGH_INTERNAL_OVERVALIDATION" for f in track.flags)

def test_moderator_quality_no_reasoning_field():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Ok."}
        ],
        moderator_log=[
            {
                "turn": 1, 
                "action": "direct_probe", 
                "brief_justification": "Just asking."
            }
        ]
    )
    track = compute_moderator_metrics(artifacts)
    # Shouldn't crash, should find 0 hits
    assert track.metrics["internal_overvalidation_phrase_hits"].value == 0

def test_moderator_quality_strict_target_arbitrary_id():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Tom, what do you think?"},
            {"turn": 2, "speaker_id": "masters-london-tom", "speaker_name": "Tom", "content": "I think..."}
        ],
        moderator_log=[
            {"turn": 1, "action": "direct_probe", "target": "masters-london-tom"}
        ]
    )
    track = compute_moderator_metrics(artifacts)
    assert track.metrics["strict_target_count"].value == 1
    assert track.metrics["strict_target_mismatch_count"].value == 0

def test_moderator_quality_group_with_names():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "P1", "speaker_name": "Alice", "content": "Hi"},
            {"turn": 2, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Does anyone agree with Alice or Tom?"}
        ],
        moderator_log=[
            {"turn": 2, "action": "redirect_to_group", "target": "group"}
        ]
    )
    track = compute_moderator_metrics(artifacts)
    assert track.metrics["strict_target_count"].value == 0

def test_moderator_quality_next_participant_order():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[
            {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Tom, what do you think?"},
            {"turn": 1, "speaker_id": "P2", "speaker_name": "Robert", "content": "I'll jump in!"},
            {"turn": 2, "speaker_id": "masters-london-tom", "speaker_name": "Tom", "content": "I think..."}
        ],
        moderator_log=[
            {"turn": 1, "action": "direct_probe", "target": "masters-london-tom"}
        ]
    )
    track = compute_moderator_metrics(artifacts)
    assert track.metrics["strict_target_count"].value == 1
    assert track.metrics["strict_target_mismatch_count"].value == 1
