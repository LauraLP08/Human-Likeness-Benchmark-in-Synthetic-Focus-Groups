from typing import Dict, List
from .schema import TrackResult, RecommendationResult

def generate_recommendation(tracks: Dict[str, TrackResult]) -> RecommendationResult:
    result = RecommendationResult(recommendation="UNKNOWN")
    
    mech_track = tracks.get("mechanical_integrity")
    
    if mech_track:
        if mech_track.status == "FAIL" or any(f.severity == "critical" for f in mech_track.flags):
            result.recommendation = "BLOCKED_MECHANICAL"
            result.triggered_rules.append("Critical mechanical flag or track failure detected.")
            result.failed_tracks.append("mechanical_integrity")
            return result
        
    failed_quality_tracks = []
    warning_quality_tracks = []
    
    for t_id, t_result in tracks.items():
        if t_id == "mechanical_integrity": continue
        if t_result.status == "FAIL":
            failed_quality_tracks.append(t_id)
        elif t_result.status == "WARNING":
            warning_quality_tracks.append(t_id)
            
        for m in t_result.metrics.values():
            if m.status == "INSUFFICIENT_SAMPLE":
                result.caveats.append(f"INSUFFICIENT_SAMPLE in {t_id}.{m.metric_id}")
            
    result.failed_tracks = failed_quality_tracks
    result.warning_tracks = warning_quality_tracks
    
    if len(failed_quality_tracks) >= 2:
        result.recommendation = "NOT_SUITABLE_FOR_RESEARCH_USE"
        result.triggered_rules.append("Two or more major quality tracks failed.")
    elif len(failed_quality_tracks) == 1:
        result.recommendation = "PILOTING_OR_INTERNAL_DIAGNOSTIC_ONLY"
        result.triggered_rules.append("One major quality track failed.")
    elif len(warning_quality_tracks) >= 3:
        result.recommendation = "PILOTING_OR_INTERNAL_DIAGNOSTIC_ONLY"
        result.triggered_rules.append("Three or more warning tracks detected.")
    else:
        result.recommendation = "DETAILED_HUMAN_REVIEW_RECOMMENDED"
        result.triggered_rules.append("Mechanical integrity passed, <=2 warnings, no major track failures.")
        
    result.caveats.append("NO_EXTERNAL_BASELINE_CAVEAT: Thresholds are provisional as no external human baseline was used.")
    
    return result
