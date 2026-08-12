from typing import List
from .schema import Flag, EvidenceSpan, TrackResult

def create_flag(flag_id: str, severity: str, track: str, message: str, evidence: List[EvidenceSpan] = None, suggested_follow_up: str = None, metric_value = None) -> Flag:
    return Flag(
        flag_id=flag_id,
        severity=severity,
        track=track,
        message=message,
        evidence=evidence or [],
        suggested_follow_up=suggested_follow_up,
        metric_value=metric_value
    )

def apply_track_status_from_flags(track: TrackResult) -> TrackResult:
    if track.status == "BLOCKED":
        return track
        
    has_critical_or_fail = any(f.severity in ["critical", "fail"] for f in track.flags)
    has_warning = any(f.severity == "warning" for f in track.flags)
    
    if has_critical_or_fail:
        track.status = "FAIL"
    elif has_warning:
        track.status = "WARNING"
    else:
        track.status = "PASS"
        
    return track
