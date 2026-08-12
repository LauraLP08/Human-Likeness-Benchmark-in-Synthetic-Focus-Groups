import os
import argparse
import json
import csv
from assessment.loader import load_session_artifacts
from assessment.metrics import (
    compute_mechanical_integrity,
    compute_process_metrics,
    compute_moderator_metrics,
    compute_research_design_metrics,
    compute_distinctiveness_metrics,
    apply_track_status_from_flags
)
from assessment.interaction_graph import build_interaction_graph
from scripts.assess_session import generate_manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Load artifacts as human baseline
    artifacts = load_session_artifacts(args.baseline_dir, is_human_baseline=True)
    
    # Compute tracks
    tracks = {}
    tracks["mechanical_integrity"] = compute_mechanical_integrity(artifacts)
    speaker_stats = {}
    tracks["process_metrics"] = compute_process_metrics(artifacts, speaker_stats)
    tracks["moderator_quality"] = compute_moderator_metrics(artifacts)
    tracks["research_design_coverage"] = compute_research_design_metrics(artifacts)
    
    ig_track, edges = build_interaction_graph(artifacts)
    tracks["interaction_graph"] = ig_track
    
    tracks["distinctiveness"] = compute_distinctiveness_metrics(artifacts, speaker_stats)
        
    # Collate results
    all_metrics = {}
    all_flags = []
    
    for tk, tr in tracks.items():
        all_metrics[tk] = {
            "status": tr.status,
            "metrics": {mk: mv.value for mk, mv in tr.metrics.items()}
        }
        all_flags.extend([{
            "flag_id": f.flag_id,
            "severity": f.severity,
            "track_id": f.track,
            "description": f.message
        } for f in tr.flags])
        
    with open(os.path.join(args.output_dir, "assessment_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)
        
    with open(os.path.join(args.output_dir, "assessment_flags.json"), "w", encoding="utf-8") as f:
        json.dump(all_flags, f, indent=2)
        
    if edges:
        with open(os.path.join(args.output_dir, "interaction_edges.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source", "target", "type"])
            writer.writeheader()
            for e in edges:
                writer.writerow(e)
                
    if speaker_stats:
        with open(os.path.join(args.output_dir, "speaker_stats.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["speaker_id", "speaker_name", "turns", "words", "avg_words_per_turn"])
            writer.writeheader()
            for sid, sst in speaker_stats.items():
                writer.writerow({
                    "speaker_id": sst.speaker_id,
                    "speaker_name": sst.speaker_name,
                    "turns": sst.turn_count,
                    "words": sst.word_count,
                    "avg_words_per_turn": sst.words_per_turn_avg
                })

    # Read guide to check if available
    guide_available = False
    if os.path.exists(os.path.join(args.baseline_dir, "guide.json")):
        guide_available = True
        
    manifest = {
        "session_dir": args.baseline_dir,
        "run_id": artifacts.run_id,
        "source_type": "human_baseline_transcript",
        "notes": [
            "no synthetic moderator log used",
            "no fake run metadata used",
            f"guide_available: {'yes' if guide_available else 'no'}"
        ]
    }
    
    with open(os.path.join(args.output_dir, "assessment_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    # Generate report
    report = f"# Assessment Report: {artifacts.run_id}\n\n"
    for tk, tm in all_metrics.items():
        report += f"## {tk} (Status: {tm['status']})\n"
        for mk, mv in tm["metrics"].items():
            if mk != "speaker_stats":
                report += f"- **{mk}**: {mv}\n"
        report += "\n"
        
    with open(os.path.join(args.output_dir, "assessment_report.md"), "w", encoding="utf-8") as f:
        f.write(report)
        
if __name__ == "__main__":
    main()
