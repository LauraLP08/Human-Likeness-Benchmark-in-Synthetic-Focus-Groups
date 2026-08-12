import argparse
import os

from assessment.schema import AssessmentResult
from assessment.loader import load_session_artifacts
from assessment.metrics import (
    compute_mechanical_integrity,
    compute_process_metrics,
    compute_moderator_metrics,
    compute_topic_metrics,
    compute_distinctiveness_metrics,
    compute_research_design_metrics
)
from assessment.interaction_graph import build_interaction_graph
from assessment.recommendation import generate_recommendation
from assessment.report import generate_report
from assessment.versioning import generate_manifest

def assess_session(session_dir: str, topic: str = "grocery_delivery", topic_terms=None) -> AssessmentResult:
    artifacts = load_session_artifacts(session_dir)
    result = AssessmentResult(run_id=artifacts.run_id)
    
    # 1. Mechanical
    mech_track = compute_mechanical_integrity(artifacts)
    result.tracks[mech_track.track_id] = mech_track
    
    if mech_track.status == "FAIL":
        # Don't compute further if blocked
        pass
    else:
        # 2. Process
        proc_track = compute_process_metrics(artifacts, result.speaker_stats)
        result.tracks[proc_track.track_id] = proc_track
        
        # 3. Moderator
        mod_track = compute_moderator_metrics(artifacts)
        result.tracks[mod_track.track_id] = mod_track
        
        # 4. Topic
        topic_track = compute_topic_metrics(artifacts, topic, topic_terms)
        result.tracks[topic_track.track_id] = topic_track
        
        # 5. Distinctiveness
        dist_track = compute_distinctiveness_metrics(artifacts, result.speaker_stats)
        result.tracks[dist_track.track_id] = dist_track
        
        # 6. Interaction graph
        ig_track, edges = build_interaction_graph(artifacts)
        result.tracks[ig_track.track_id] = ig_track
        result.interaction_edges = edges
        
        # 7. Research design
        rd_track = compute_research_design_metrics(artifacts)
        result.tracks[rd_track.track_id] = rd_track

    # 8. Recommendation
    result.recommendation = generate_recommendation(result.tracks)
    
    # 9. Manifest
    result.manifest = generate_manifest(session_dir, result.run_id, topic)
    
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--topic", default="grocery_delivery")
    parser.add_argument("--topic-terms", nargs="*")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    
    res = assess_session(args.session_dir, args.topic, args.topic_terms)
    generate_report(res, args.output_dir)
    print(f"Assessed {args.session_dir}. Recommendation: {res.recommendation.recommendation}")
