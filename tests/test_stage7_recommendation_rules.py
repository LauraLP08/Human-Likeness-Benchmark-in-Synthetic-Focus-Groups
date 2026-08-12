import pytest
from assessment.schema import TrackResult
from assessment.recommendation import generate_recommendation

def test_recommendation_blocked():
    tracks = {
        "mechanical_integrity": TrackResult("mechanical_integrity", status="FAIL")
    }
    res = generate_recommendation(tracks)
    assert res.recommendation == "BLOCKED_MECHANICAL"

def test_recommendation_not_suitable():
    tracks = {
        "mechanical_integrity": TrackResult("mechanical_integrity", status="PASS"),
        "moderator_quality": TrackResult("moderator_quality", status="FAIL"),
        "process_and_participation": TrackResult("process_and_participation", status="FAIL")
    }
    res = generate_recommendation(tracks)
    assert res.recommendation == "NOT_SUITABLE_FOR_RESEARCH_USE"
    assert any("NO_EXTERNAL_BASELINE_CAVEAT" in c for c in res.caveats)

def test_recommendation_piloting_only():
    tracks = {
        "mechanical_integrity": TrackResult("mechanical_integrity", status="PASS"),
        "moderator_quality": TrackResult("moderator_quality", status="FAIL")
    }
    res = generate_recommendation(tracks)
    assert res.recommendation == "PILOTING_OR_INTERNAL_DIAGNOSTIC_ONLY"
    assert any("NO_EXTERNAL_BASELINE_CAVEAT" in c for c in res.caveats)

def test_recommendation_three_warnings_piloting_only():
    tracks = {
        "mechanical_integrity": TrackResult("mechanical_integrity", status="PASS"),
        "moderator_quality": TrackResult("moderator_quality", status="WARNING"),
        "process_and_participation": TrackResult("process_and_participation", status="WARNING"),
        "topic_tethering": TrackResult("topic_tethering", status="WARNING")
    }
    res = generate_recommendation(tracks)
    assert res.recommendation == "PILOTING_OR_INTERNAL_DIAGNOSTIC_ONLY"
    assert "Three or more warning tracks detected." in res.triggered_rules

def test_recommendation_detailed_review():
    tracks = {
        "mechanical_integrity": TrackResult("mechanical_integrity", status="PASS"),
        "moderator_quality": TrackResult("moderator_quality", status="PASS")
    }
    res = generate_recommendation(tracks)
    assert res.recommendation == "DETAILED_HUMAN_REVIEW_RECOMMENDED"
    assert any("NO_EXTERNAL_BASELINE_CAVEAT" in c for c in res.caveats)
