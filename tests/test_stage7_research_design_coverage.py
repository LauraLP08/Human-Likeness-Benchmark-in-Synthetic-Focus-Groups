import pytest
from assessment.schema import SessionArtifacts
from assessment.metrics import compute_research_design_metrics

def test_research_design_coverage_metrics():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[],
        moderator_log=[],
        session_state_final={
            "discussion_guide": [
                {"completed": True},
                {"completed": True},
                {"completed": False}
            ],
            "current_section_index": 2,
            "completed": False
        }
    )
    track = compute_research_design_metrics(artifacts)
    assert track.metrics["sections_total"].value == 3
    assert track.metrics["sections_completed"].value == 2
    assert track.metrics["section_coverage_rate"].value == 2 / 3
