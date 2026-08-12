import os
import json
import statistics
import csv

def generate_human_calibration_data():
    assessment_dir = r"docs\testing\human_baseline_standardization_claude_v1\assessments"
    if not os.path.exists(assessment_dir):
        assessment_dir = "docs/testing/human_baseline_standardization_claude_v1/assessments"
        
    transcript_dir = r"data\human_baseline\standardized_claude_v1"
    if not os.path.exists(transcript_dir):
        transcript_dir = "data/human_baseline/standardized_claude_v1"
        
    assessment_baselines = [d for d in os.listdir(assessment_dir) if os.path.isdir(os.path.join(assessment_dir, d))]
    transcript_baselines = [d for d in os.listdir(transcript_dir) if os.path.isdir(os.path.join(transcript_dir, d)) and d != "archive" and d != "raw_guides" and d != "raw_transcripts" and d != "extracted_text"]
    
    METRIC_REGISTRY = {
        "dialogue_turn_count": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Fundamental conversational volume", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "moderator_turn_count": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Moderator intervention frequency", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "participant_turn_count": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Participant intervention frequency", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "participant_count": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Number of participants in focus group", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "moderator_word_share": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Core metric of facilitator dominance", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "gini_turns": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Participant equity metric", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "gini_words": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Participant equity metric", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "max_consecutive_participant_turns": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Indicator of participant-to-participant flow", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "avg_participant_turn_words": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Turn length distribution", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "median_participant_turn_words": {"track": "process_metrics", "status": "CALIBRATION_REFERENCE", "reason": "Turn length distribution", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "participant_to_participant_edge_density": {"track": "interaction_graph", "status": "CALIBRATION_REFERENCE", "reason": "Shows cross-talk levels", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "total_edges": {"track": "interaction_graph", "status": "ILLUSTRATIVE_ONLY", "reason": "Depends on length of group", "topic_sensitive": False, "sample_sensitive": True, "threshold_allowed": "no", "recommended_use": "use_as_descriptive_context_only", "comparable": "conditional"},
        "total_repairs": {"track": "distinctiveness", "status": "CALIBRATION_REFERENCE", "reason": "Measures human-like self-correction", "topic_sensitive": False, "sample_sensitive": True, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "total_hedges": {"track": "distinctiveness", "status": "CALIBRATION_REFERENCE", "reason": "Measures uncertainty language", "topic_sensitive": False, "sample_sensitive": True, "threshold_allowed": "conditional", "recommended_use": "use_as_soft_reference_range", "comparable": "yes"},
        "participant_lexical_diversity_range": {"track": "distinctiveness", "status": "ILLUSTRATIVE_ONLY", "reason": "Depends on topic and text length", "topic_sensitive": True, "sample_sensitive": True, "threshold_allowed": "no", "recommended_use": "use_as_descriptive_context_only", "comparable": "yes"},
        "sections_completed": {"track": "research_design_coverage", "status": "NOT_COMPARABLE", "reason": "Guide structure differs heavily between topics", "topic_sensitive": True, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "do_not_compare", "comparable": "no"},
        "section_coverage_rate": {"track": "research_design_coverage", "status": "NOT_COMPARABLE", "reason": "Guide structure differs heavily between topics", "topic_sensitive": True, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "do_not_compare", "comparable": "no"},
        "section_transition_count": {"track": "research_design_coverage", "status": "NOT_COMPARABLE", "reason": "Section markers vary by dataset (QESB has headings, PHIND does not)", "topic_sensitive": True, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "do_not_compare", "comparable": "no"},
        "stage_direction_count": {"track": "mechanical_integrity", "status": "NOT_COMPARABLE", "reason": "Humans use [inaudible], synthetic uses *laughs*. Not directly equivalent.", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "do_not_compare", "comparable": "no"},
        "nonverbal_marker_count": {"track": "mechanical_integrity", "status": "HUMAN_ONLY_CONTEXTUAL", "reason": "Captures human-only transcription notes", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "use_as_descriptive_context_only", "comparable": "no"},
        "internal_overvalidation_entries_total": {"track": "moderator_quality", "status": "SYNTHETIC_ONLY_NOT_APPLICABLE", "reason": "Humans do not have internal reasoning logs", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "synthetic_only_audit_metric", "comparable": "no"},
        "strict_target_count": {"track": "moderator_quality", "status": "SYNTHETIC_ONLY_NOT_APPLICABLE", "reason": "Humans do not have internal reasoning logs", "topic_sensitive": False, "sample_sensitive": False, "threshold_allowed": "no", "recommended_use": "synthetic_only_audit_metric", "comparable": "no"},
        "visible_overvalidation_hits": {"track": "moderator_quality", "status": "ILLUSTRATIVE_ONLY", "reason": "Valid for human dialogue, but underpowered n=7", "topic_sensitive": False, "sample_sensitive": True, "threshold_allowed": "no", "recommended_use": "use_as_descriptive_context_only", "comparable": "yes"}
    }
    
    total_dialogue_turns_from_transcript_json = 0
    total_dialogue_turns_from_assessments = 0
    per_baseline = {}
    
    metrics_data = {m: [] for m in METRIC_REGISTRY.keys()}
    
    # Use transcript.json for authoritative counts
    valid_transcript_baselines = []
    for b in transcript_baselines:
        t_path = os.path.join(transcript_dir, b, "transcript.json")
        if os.path.exists(t_path):
            valid_transcript_baselines.append(b)
            turns = 0
            with open(t_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                if isinstance(t_data, list):
                    turns = len(t_data)
                elif isinstance(t_data, dict):
                    turns = len(t_data.get("dialogue", []))
            total_dialogue_turns_from_transcript_json += turns
            if b not in per_baseline: per_baseline[b] = {}
            per_baseline[b]["transcript_turns"] = turns

    valid_assessment_baselines = []
    for b in assessment_baselines:
        a_path = os.path.join(assessment_dir, b, "assessment_metrics.json")
        if os.path.exists(a_path):
            valid_assessment_baselines.append(b)
            with open(a_path, "r", encoding="utf-8") as f:
                a_data = json.load(f)
                turns = a_data.get("process_metrics", {}).get("metrics", {}).get("dialogue_turn_count", 0)
                if isinstance(turns, dict) and "value" in turns: turns = turns["value"]
                total_dialogue_turns_from_assessments += turns
                if b not in per_baseline: per_baseline[b] = {}
                per_baseline[b]["assessment_turns"] = turns
                
                for metric, info in METRIC_REGISTRY.items():
                    track = info["track"]
                    if track in a_data and "metrics" in a_data[track] and metric in a_data[track]["metrics"]:
                        metrics_data[metric].append(a_data[track]["metrics"][metric])

    transcript_baseline_ids = set(valid_transcript_baselines)
    assessment_baseline_ids = set(valid_assessment_baselines)
    
    missing_assessment_for_transcript = transcript_baseline_ids - assessment_baseline_ids
    missing_transcript_for_assessment = assessment_baseline_ids - transcript_baseline_ids
    transcript_assessment_id_set_match = (transcript_baseline_ids == assessment_baseline_ids)
    
    count_match = (len(valid_transcript_baselines) == 7 and len(valid_assessment_baselines) == 7)
    turn_match = (total_dialogue_turns_from_transcript_json == 649 and total_dialogue_turns_from_assessments == 649)
    
    blocking_issues = []
    if not transcript_assessment_id_set_match:
        blocking_issues.append("ID sets do not match between transcripts and assessments.")
    if not (len(valid_transcript_baselines) == len(valid_assessment_baselines)):
        blocking_issues.append("Count of baselines does not match between transcripts and assessments.")
    if not (total_dialogue_turns_from_transcript_json == total_dialogue_turns_from_assessments):
        blocking_issues.append("Turn counts do not match between transcripts and assessments.")
    if len(valid_transcript_baselines) != 7:
        blocking_issues.append("human_baseline_count_from_transcript_json is not 7.")
    if len(valid_assessment_baselines) != 7:
        blocking_issues.append("human_baseline_count_from_assessments is not 7.")
    if total_dialogue_turns_from_transcript_json != 649:
        blocking_issues.append("total_dialogue_turns_from_transcript_json is not 649.")
    if total_dialogue_turns_from_assessments != 649:
        blocking_issues.append("total_dialogue_turns_from_assessments is not 649.")
        

    for b in sorted(list(set(valid_transcript_baselines + valid_assessment_baselines))):
        if b not in valid_transcript_baselines:
            blocking_issues.append(f"Baseline {b} missing transcript")
        elif b not in valid_assessment_baselines:
            blocking_issues.append(f"Baseline {b} missing assessment")
        else:
            t_turns = per_baseline[b].get("transcript_turns", 0)
            a_turns = per_baseline[b].get("assessment_turns", 0)
            if t_turns != a_turns:
                blocking_issues.append(f"Turn mismatch in {b}: transcript={t_turns}, assessment={a_turns}")

    gate_status = "BLOCKED" if blocking_issues else "PASS"
    
    summary = {
        "metadata": {
            "human_baseline_count_from_transcript_json": len(valid_transcript_baselines),
            "human_baseline_count_from_assessments": len(valid_assessment_baselines),
            "total_dialogue_turns_from_transcript_json": total_dialogue_turns_from_transcript_json,
            "total_dialogue_turns_from_assessments": total_dialogue_turns_from_assessments,
            "transcript_assessment_count_match": (len(valid_transcript_baselines) == len(valid_assessment_baselines)),
            "transcript_assessment_turn_count_match": (total_dialogue_turns_from_transcript_json == total_dialogue_turns_from_assessments),
            "transcript_assessment_id_set_match": transcript_assessment_id_set_match,
            "gate_status": gate_status,
            "blocking_issue_count": len(blocking_issues),
            "blocking_issues": blocking_issues,
            "caution": "Stage 7C.5 establishes which human baseline metrics may be used for process calibration. Synthetic-vs-human comparison should be run only after this calibration gate is reviewed. No outcome/theme comparison is made. Thresholds remain provisional."
        },
        "metrics": {}
    }
    
    for metric, values in metrics_data.items():
        proposed_status = METRIC_REGISTRY[metric]["status"]
        final_status = proposed_status
        
        vals = [float(v) for v in values if v is not None]
        valid_value_count = len(vals)
        
        exempt_statuses = ["SYNTHETIC_ONLY_NOT_APPLICABLE", "HUMAN_ONLY_CONTEXTUAL", "NOT_COMPARABLE"]
        
        if proposed_status not in exempt_statuses:
            if valid_value_count == 0:
                final_status = "INSUFFICIENT_SAMPLE"
            elif valid_value_count < 3:
                final_status = "INSUFFICIENT_SAMPLE"
                
        # Calculate stats if possible
        if valid_value_count > 0:
            mean_val = statistics.mean(vals)
            median_val = statistics.median(vals)
            min_val = min(vals)
            max_val = max(vals)
            sd_val = statistics.stdev(vals) if valid_value_count > 1 else None
            
            iqr_val = None
            if valid_value_count >= 4:
                vals_sorted = sorted(vals)
                q1 = statistics.median(vals_sorted[:valid_value_count//2])
                q3 = statistics.median(vals_sorted[(valid_value_count+1)//2:])
                iqr_val = q3 - q1
                
            summary["metrics"][metric] = {
                "proposed_status": proposed_status,
                "final_status": final_status,
                "n": len(values),
                "valid_value_count": valid_value_count,
                "min": min_val,
                "max": max_val,
                "mean": mean_val,
                "median": median_val,
                "sd": sd_val,
                "iqr": iqr_val,
                "observed_range": f"{min_val} - {max_val}",
                "status_reason": METRIC_REGISTRY[metric]["reason"],
                "limitations": METRIC_REGISTRY[metric]["reason"]
            }
        else:
            summary["metrics"][metric] = {
                "proposed_status": proposed_status,
                "final_status": final_status,
                "n": len(values),
                "valid_value_count": valid_value_count,
                "status_reason": METRIC_REGISTRY[metric]["reason"],
                "limitations": METRIC_REGISTRY[metric]["reason"]
            }
            
    out_dir = "docs/testing/stage7c5_human_baseline_calibration"
    os.makedirs(out_dir, exist_ok=True)
    
    with open(os.path.join(out_dir, "human_process_calibration_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    with open(os.path.join(out_dir, "human_process_calibration_summary.md"), "w", encoding="utf-8") as f:
        f.write("# Human Process Calibration Summary\n\n")
        f.write(f"**Human Baselines from transcript.json**: {len(valid_transcript_baselines)}\n")
        f.write(f"**Human Baselines from assessments**: {len(valid_assessment_baselines)}\n")
        f.write(f"**Total Dialogue Turns from transcript.json**: {total_dialogue_turns_from_transcript_json}\n")
        f.write(f"**Total Dialogue Turns from assessments**: {total_dialogue_turns_from_assessments}\n")
        f.write(f"**Count Match**: {count_match}\n")
        f.write(f"**Turn Match**: {turn_match}\n\n")
        f.write("> **CAUTION**: Stage 7C.5 establishes which human baseline metrics may be used for process calibration. Synthetic-vs-human comparison should be run only after this calibration gate is reviewed. This does not validate outcome/theme content, and all thresholds derived from this n=7 sample remain provisional soft reference ranges.\n\n")
        
        f.write("## Metrics Evaluation\n")
        for metric, stats in summary["metrics"].items():
            f.write(f"### {metric}\n")
            f.write(f"- Proposed Status: {stats.get('proposed_status')}\n")
            f.write(f"- Final Status: **{stats.get('final_status')}**\n")
            if stats.get('valid_value_count', 0) > 0:
                f.write(f"- Observed range (soft reference): {stats.get('observed_range', 'N/A')}\n")
                f.write(f"- Mean: {stats.get('mean', 'N/A')}, Median: {stats.get('median', 'N/A')}\n")
            f.write(f"- Limitation/Reason: {stats.get('limitations', 'N/A')}\n\n")
                
    rec_csv_path = os.path.join(out_dir, "per_baseline_reconciliation_table.csv")
    rec_md_path = os.path.join(out_dir, "per_baseline_reconciliation_table.md")
    with open(rec_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["baseline_id", "transcript_present", "assessment_present", "transcript_turns", "assessment_turns", "match_status"])
        for b in sorted(list(set(valid_transcript_baselines + valid_assessment_baselines))):
            t_pres = "Yes" if b in valid_transcript_baselines else "No"
            a_pres = "Yes" if b in valid_assessment_baselines else "No"
            t_turns = per_baseline.get(b, {}).get("transcript_turns", 0) if t_pres == "Yes" else 0
            a_turns = per_baseline.get(b, {}).get("assessment_turns", 0) if a_pres == "Yes" else 0
            m_stat = "MATCH" if (t_pres == "Yes" and a_pres == "Yes" and t_turns == a_turns) else "MISMATCH"
            writer.writerow([b, t_pres, a_pres, t_turns, a_turns, m_stat])
            
    with open(rec_md_path, "w", encoding="utf-8") as f:
        f.write("# Per-Baseline Reconciliation Table\n\n")
        f.write("| Baseline ID | Transcript Present | Assessment Present | Transcript Turns | Assessment Turns | Match Status |\n")
        f.write("|---|---|---|---|---|---|\n")
        for b in sorted(list(set(valid_transcript_baselines + valid_assessment_baselines))):
            t_pres = "Yes" if b in valid_transcript_baselines else "No"
            a_pres = "Yes" if b in valid_assessment_baselines else "No"
            t_turns = per_baseline.get(b, {}).get("transcript_turns", 0) if t_pres == "Yes" else 0
            a_turns = per_baseline.get(b, {}).get("assessment_turns", 0) if a_pres == "Yes" else 0
            m_stat = "MATCH" if (t_pres == "Yes" and a_pres == "Yes" and t_turns == a_turns) else "MISMATCH"
            f.write(f"| {b} | {t_pres} | {a_pres} | {t_turns} | {a_turns} | {m_stat} |\n")

    audit_csv_path = os.path.join(out_dir, "human_metric_status_audit.csv")
    with open(audit_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "proposed_status", "final_status"])
        for metric, info in METRIC_REGISTRY.items():
            final_st = summary["metrics"][metric]["final_status"]
            writer.writerow([metric, info["status"], final_st])
            
    status_counts = {}
    for metric, info in METRIC_REGISTRY.items():
        st = summary["metrics"][metric]["final_status"]
        status_counts[st] = status_counts.get(st, 0) + 1

    res_path = os.path.join(out_dir, "STAGE7C5_HUMAN_BASELINE_AUDIT_HARDENING_RESULTS.md")
    with open(res_path, "w", encoding="utf-8") as f:
        gate_verdict = "COMPLETE" if gate_status == "PASS" else ("BLOCKED" if gate_status == "BLOCKED" else "PARTIAL")
        f.write("# Stage 7C.5 Audit Hardening Results\n\n")
        f.write(f"**Final Verdict: {gate_verdict}**\n\n")
        f.write("## Scope\n")
        f.write("This is a process calibration only, not an outcome or theme validity check.\n\n")
        f.write("## Reconciliation Summary\n")
        f.write(f"- Transcript Baseline Count: {len(valid_transcript_baselines)}\n")
        f.write(f"- Assessment Baseline Count: {len(valid_assessment_baselines)}\n")
        f.write(f"- Total Transcript Turns: {total_dialogue_turns_from_transcript_json}\n")
        f.write(f"- Total Assessment Turns: {total_dialogue_turns_from_assessments}\n")
        f.write(f"- ID Set Match Status: {transcript_assessment_id_set_match}\n")
        f.write(f"- Per-Baseline Turn Match Status: {'MATCH' if len(blocking_issues)==0 else 'MISMATCH'}\n\n")
        f.write("## Metric Status Counts\n")
        for st, c in status_counts.items():
            f.write(f"- {st}: {c}\n")
        f.write("\n## Tests Run\n")
        f.write("Automated tests enforce that every baseline reconciles exactly in ID and turn counts. Tests verify aggregate counts match and status categories are strictly allowed.\n\n")
        f.write("## Remaining Limitations\n")
        f.write("Thresholds derived from this n=7 human sample remain provisional and soft reference ranges.\n\n")
        f.write("## Baseline Reconciliation Evidence Table\n")
        f.write("| Baseline ID | Transcript Present | Assessment Present | Transcript Turns | Assessment Turns | Match Status |\n")
        f.write("|---|---|---|---|---|---|\n")
        for b in sorted(list(set(valid_transcript_baselines + valid_assessment_baselines))):
            t_pres = "Yes" if b in valid_transcript_baselines else "No"
            a_pres = "Yes" if b in valid_assessment_baselines else "No"
            t_turns = per_baseline.get(b, {}).get("transcript_turns", 0) if t_pres == "Yes" else 0
            a_turns = per_baseline.get(b, {}).get("assessment_turns", 0) if a_pres == "Yes" else 0
            m_stat = "MATCH" if (t_pres == "Yes" and a_pres == "Yes" and t_turns == a_turns) else "MISMATCH"
            f.write(f"| {b} | {t_pres} | {a_pres} | {t_turns} | {a_turns} | {m_stat} |\n")

    csv_path = os.path.join(out_dir, "calibration_applicability_matrix.csv")
    md_path = os.path.join(out_dir, "calibration_applicability_matrix.md")
    
    headers = [
        "metric", "track", "available_for_human", "available_for_synthetic",
        "comparable", "proposed_status", "final_status", "reason_not_comparable_if_any",
        "sample_size_note", "topic_sensitivity_note", "threshold_allowed", "recommended_use"
    ]
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for metric, info in METRIC_REGISTRY.items():
            final_st = summary["metrics"][metric]["final_status"]
            avail_human = "yes" if info["status"] != "SYNTHETIC_ONLY_NOT_APPLICABLE" else "no"
            avail_synth = "yes" if info["status"] != "HUMAN_ONLY_CONTEXTUAL" else "no"
            
            writer.writerow([
                metric,
                info["track"],
                avail_human,
                avail_synth,
                info["comparable"],
                info["status"],
                final_st,
                info["reason"] if info["status"] in ["NOT_COMPARABLE", "SYNTHETIC_ONLY_NOT_APPLICABLE", "HUMAN_ONLY_CONTEXTUAL"] else "",
                "sample-size-sensitive" if info["sample_sensitive"] else "robust",
                "topic-sensitive" if info["topic_sensitive"] else "robust",
                info["threshold_allowed"],
                info["recommended_use"]
            ])
            
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Calibration Applicability Matrix\n\n")
        f.write("| Metric | Track | Comparable | Proposed Status | Final Status | Recommended Use | Topic Sensitive |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for metric, info in METRIC_REGISTRY.items():
            final_st = summary["metrics"][metric]["final_status"]
            f.write(f"| {metric} | {info['track']} | {info['comparable']} | {info['status']} | {final_st} | {info['recommended_use']} | {'Yes' if info['topic_sensitive'] else 'No'} |\n")

    return summary

if __name__ == "__main__":
    summary = generate_human_calibration_data()
    if summary["metadata"]["gate_status"] == "BLOCKED":
        import sys
        sys.exit(2)
