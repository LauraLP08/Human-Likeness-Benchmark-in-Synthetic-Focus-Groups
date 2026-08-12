import pytest
from assessment.schema import TrackResult, Flag
from assessment.flags import apply_track_status_from_flags

def test_flags_status_propagation():
    # Warning
    track1 = TrackResult(track_id="t1")
    track1.flags.append(Flag("TEST_WARNING", "warning", "t1", "test"))
    track1 = apply_track_status_from_flags(track1)
    assert track1.status == "WARNING"
    
    # Critical
    track2 = TrackResult(track_id="t2")
    track2.flags.append(Flag("TEST_CRITICAL", "critical", "t2", "test"))
    track2 = apply_track_status_from_flags(track2)
    assert track2.status == "FAIL"
    
    # Blocked shouldn't change
    track3 = TrackResult(track_id="t3", status="BLOCKED")
    track3.flags.append(Flag("TEST_WARNING", "warning", "t3", "test"))
    track3 = apply_track_status_from_flags(track3)
    assert track3.status == "BLOCKED"
