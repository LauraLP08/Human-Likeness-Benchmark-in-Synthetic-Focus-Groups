import json
import os
from .schema import AssessmentResult

def generate_report(result: AssessmentResult, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Output metrics JSON
    metrics_dict = {}
    for t_id, t_result in result.tracks.items():
        metrics_dict[t_id] = {m_id: {"value": m.value, "status": m.status} for m_id, m in t_result.metrics.items()}
        
    with open(os.path.join(output_dir, "assessment_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics_dict, f, indent=2)
        
    # 2. Output flags JSON
    flags_list = []
    for t_id, t_result in result.tracks.items():
        for flag in t_result.flags:
            flags_list.append({
                "flag_id": flag.flag_id,
                "severity": flag.severity,
                "track": flag.track,
                "message": flag.message,
                "evidence": [vars(e) for e in flag.evidence],
                "suggested_follow_up": flag.suggested_follow_up
            })
            
    with open(os.path.join(output_dir, "assessment_flags.json"), "w", encoding="utf-8") as f:
        json.dump(flags_list, f, indent=2)
        
    # 3. Output speaker stats CSV
    with open(os.path.join(output_dir, "speaker_stats.csv"), "w", encoding="utf-8") as f:
        f.write("speaker_id,speaker_name,turn_count,word_count,words_per_turn_avg,first_turn_index\n")
        for s in result.speaker_stats.values():
            f.write(f"{s.speaker_id},{s.speaker_name},{s.turn_count},{s.word_count},{s.words_per_turn_avg},{s.first_turn_index}\n")
            
    # 4. Output interaction edges CSV
    with open(os.path.join(output_dir, "interaction_edges.csv"), "w", encoding="utf-8") as f:
        f.write("source,target,type\n")
        for e in result.interaction_edges:
            f.write(f"{e['source']},{e['target']},{e['type']}\n")
            
    # 5. Output manifest JSON
    with open(os.path.join(output_dir, "assessment_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(result.manifest, f, indent=2)
        
    # 6. Generate Markdown Report
    lines = []
    lines.append(f"# Assessment Report: {result.run_id}")
    
    lines.append("\n## 1. Session Summary")
    lines.append(f"Assessed on: {result.manifest.get('timestamp')}")
    
    lines.append("\n## 2. Artifacts Inspected")
    lines.append("Included standard session logs (transcript.json, moderator_log.json, etc.).")
    
    tracks_to_show = [
        ("mechanical_integrity", "3. Mechanical integrity"),
        ("process_and_participation", "4. Process and participation"),
        ("moderator_quality", "5. Moderator quality"),
        ("topic_tethering", "6. Topic tethering and concreteness"),
        ("participant_distinctiveness", "7. Participant distinctiveness"),
        ("interaction_graph", "8. Interaction graph"),
        ("research_design_coverage", "9. Research-design coverage")
    ]
    
    for t_id, t_title in tracks_to_show:
        lines.append(f"\n## {t_title}")
        if t_id in result.tracks:
            tr = result.tracks[t_id]
            lines.append(f"**Status**: {tr.status}")
            lines.append("\n**Metrics**:")
            for m in tr.metrics.values():
                lines.append(f"- `{m.metric_id}`: {m.value} ({m.status})")
        else:
            lines.append("**Status**: Not evaluated (Track missing)")
            
    lines.append("\n## 10. Traceability table of key flags")
    if not flags_list:
        lines.append("No flags generated.")
    else:
        for f in flags_list:
            lines.append(f"### {f['flag_id']}")
            lines.append(f"- **Severity**: {f['severity']}")
            lines.append(f"- **Track**: {f['track']}")
            lines.append(f"- **Message**: {f['message']}")
            if f['suggested_follow_up']:
                lines.append(f"- **Suggested Follow-up**: {f['suggested_follow_up']}")
            if f['evidence']:
                lines.append("- **Evidence Excerpts**:")
                for e in f['evidence']:
                    lines.append(f"  - [{e['source_file']} Turn {e['turn']} / {e['speaker_name']}]: \"{e['excerpt']}\"")
                    
    lines.append("\n## 11. Recommendation")
    lines.append(f"**{result.recommendation.recommendation if result.recommendation else 'UNKNOWN'}**")
    if result.recommendation:
        for rule in result.recommendation.triggered_rules:
            lines.append(f"- Rule triggered: {rule}")
            
    lines.append("\n## 12. Caveats and limitations")
    if result.recommendation:
        for caveat in result.recommendation.caveats:
            lines.append(f"- {caveat}")
            
    lines.append("\n## 13. Goodhart Warning")
    lines.append("> **WARNING:** These assessment metrics are audit tools, not optimization targets. They should not be directly used to tune the moderator or participant prompts without held-out checks. Optimizing directly against visible metrics can produce degenerate behavior such as artificial turn variation, keyword stuffing, forced disagreement, or superficial concrete examples.")
    
    lines.append("\n## 14. Reproducibility manifest")
    lines.append("Manifest available in `assessment_manifest.json`.")
    
    with open(os.path.join(output_dir, "assessment_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
