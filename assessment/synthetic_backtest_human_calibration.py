import os
import json
import csv
import sys

def check_human_calibration_gate():
    summary_path = "docs/testing/stage7c5_human_baseline_calibration/human_process_calibration_summary.json"
    if not os.path.exists(summary_path):
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["Missing human calibration summary"]}
        
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    md = data.get("metadata", {})
    if md.get("gate_status") != "PASS":
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["Gate status is not PASS"]}
        
    if md.get("blocking_issue_count", -1) != 0:
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["Blocking issue count is not 0"]}
        
    if not md.get("transcript_assessment_id_set_match"):
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["ID set match is false"]}
        
    if not md.get("transcript_assessment_turn_count_match"):
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["Turn count match is false"]}
        
    if md.get("human_baseline_count_from_transcript_json") != 7:
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["Baseline count != 7"]}
        
    if md.get("total_dialogue_turns_from_transcript_json") != 649:
        return {"gate_status": "BLOCKED", "blocking_issue_count": 1, "issues": ["Total turns != 649"]}
        
    # Count metrics
    cal_ref_count = 0
    ill_only_count = 0
    not_comp_count = 0
    
    for m, info in data.get("metrics", {}).items():
        st = info.get("final_status")
        if st == "CALIBRATION_REFERENCE":
            cal_ref_count += 1
        elif st == "ILLUSTRATIVE_ONLY":
            ill_only_count += 1
        elif st in ["NOT_COMPARABLE", "HUMAN_ONLY_CONTEXTUAL"]:
            not_comp_count += 1
            
    return {
        "gate_status": "PASS",
        "blocking_issue_count": 0,
        "human_baseline_count": 7,
        "total_human_turns": 649,
        "calibration_reference_metrics_count": cal_ref_count,
        "illustrative_only_metrics_count": ill_only_count,
        "not_comparable_metrics_count": not_comp_count,
        "metrics": data.get("metrics", {})
    }

def get_bounded_near_margin(metric_name, human_min, human_max):
    # Determine bounds based on metric name for proportions/rates
    lower_bound = float('-inf')
    upper_bound = float('inf')
    
    # Common bounded metrics
    if "share" in metric_name or "rate" in metric_name or "density" in metric_name or "gini" in metric_name:
        lower_bound = 0.0
        upper_bound = 1.0
        
    human_range = human_max - human_min
    near_margin = 0.15 * human_range
    
    lower_near = max(human_min - near_margin, lower_bound)
    upper_near = min(human_max + near_margin, upper_bound)
    
    return lower_near, upper_near

def classify_synthetic_value(synthetic_value, metric_info, metric_name):
    final_status = metric_info.get("final_status")
    
    if final_status == "ILLUSTRATIVE_ONLY":
        return "HUMAN_REFERENCE_ILLUSTRATIVE_ONLY", "use_as_descriptive_context_only"
    elif final_status in ["NOT_COMPARABLE", "HUMAN_ONLY_CONTEXTUAL"]:
        return "NOT_COMPARABLE", "do_not_compare"
    elif final_status == "SYNTHETIC_ONLY_NOT_APPLICABLE":
        return "SYNTHETIC_ONLY_AUDIT_METRIC", "synthetic_only_audit_metric"
    elif final_status in ["INSUFFICIENT_SAMPLE", "INSUFFICIENT_HUMAN_REFERENCE"]:
        return "INSUFFICIENT_HUMAN_REFERENCE", "insufficient_reference"
    elif final_status != "CALIBRATION_REFERENCE":
        return final_status, "unknown"
        
    if synthetic_value is None:
        return "SYNTHETIC_METRIC_MISSING", ""
        
    human_min = metric_info.get("min")
    human_max = metric_info.get("max")
    
    if human_min is None or human_max is None:
        return "INSUFFICIENT_HUMAN_REFERENCE", ""
        
    if human_min == human_max:
        if abs(synthetic_value - human_min) < 1e-6:
            return "INSIDE_HUMAN_OBSERVED_RANGE", "exact match"
        else:
            # Fallback for 0-width interval
            # Allow +/- 0.05 absolute margin for near
            if abs(synthetic_value - human_min) <= 0.05:
                return "NEAR_HUMAN_OBSERVED_RANGE", "LOW_VARIANCE_HUMAN_REFERENCE"
            else:
                return "OUTSIDE_HUMAN_OBSERVED_RANGE", "LOW_VARIANCE_HUMAN_REFERENCE"
                
    lower_near, upper_near = get_bounded_near_margin(metric_name, human_min, human_max)
    
    if human_min <= synthetic_value <= human_max:
        return "INSIDE_HUMAN_OBSERVED_RANGE", "within observed human range"
    elif lower_near <= synthetic_value <= upper_near:
        return "NEAR_HUMAN_OBSERVED_RANGE", "just outside observed range but within margin"
    else:
        return "OUTSIDE_HUMAN_OBSERVED_RANGE", "outside observed human reference range; requires review"

def evaluate_progression(values, expected_direction):
    valid_vals = [v for v in values if v is not None]
    if len(valid_vals) < 2 or values[0] is None or values[-1] is None:
        return "NOT_ENOUGH_DATA", "Not enough data because metric was not mapped or derived."
        
    v_start = values[0]
    v_end = values[-1]
    
    if expected_direction == "down":
        if v_end < v_start:
            return "IMPROVED_AS_EXPECTED", "Metric decreased"
        elif v_end > v_start:
            if v_end > 0: # Still problematic if it went up
                return "STILL_PROBLEMATIC", "Metric regressed or remained high"
            return "REGRESSED", "Metric worsened"
        else:
            return "STABLE", "No change"
    elif expected_direction == "up":
        if v_end > v_start:
            return "IMPROVED_AS_EXPECTED", "Metric increased"
        elif v_end < v_start:
            return "STILL_PROBLEMATIC", "Metric regressed"
        else:
            return "STABLE", "No change"
    else:
        return "NOT_COMPARABLE_TO_HUMAN", "N/A"

def derive_metrics_from_interaction_edges(run_id):
    path = f"docs/testing/assessments_hardened/{run_id}/interaction_edges.csv"
    if not os.path.exists(path):
        return {}
        
    participants = set()
    edges = set()
    
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = row.get("source", "")
            tgt = row.get("target", "")
            if src and "moderator" not in src.lower():
                participants.add(src)
            if tgt and "moderator" not in tgt.lower():
                participants.add(tgt)
                
            if src and tgt and "moderator" not in src.lower() and "moderator" not in tgt.lower() and src != tgt:
                edges.add((src, tgt))
                
    p_count = len(participants)
    if p_count < 2:
        return {"participant_to_participant_edge_density": 0.0}
        
    possible_edges = p_count * (p_count - 1)
    density = len(edges) / possible_edges
    return {"participant_to_participant_edge_density": density}

def derive_metrics_from_transcript(run_id):
    path = f"docs/testing/assessments_hardened/{run_id}/transcript.json"
    if not os.path.exists(path):
        return {}
    
    with open(path, "r", encoding="utf-8") as f:
        t = json.load(f)
        
    dialogue = t.get("dialogue", [])
    if not dialogue:
        return {}
        
    moderator_turns = 0
    participant_turns = 0
    mod_words = 0
    part_words = 0
    p_turn_words = []
    max_consec = 0
    cur_consec = 0
    participants = set()
    
    edges = set()
    last_speaker = None
    
    for turn in dialogue:
        sp = turn.get("speaker", "").lower()
        txt = turn.get("text", "")
        wc = len(txt.split())
        
        if "moderator" in sp:
            moderator_turns += 1
            mod_words += wc
            cur_consec = 0
            last_speaker = "moderator"
        else:
            participant_turns += 1
            part_words += wc
            p_turn_words.append(wc)
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
            participants.add(sp)
            
            if last_speaker and "moderator" not in last_speaker and last_speaker != sp:
                edges.add((sp, last_speaker)) # B -> A edge (current participant responds to previous participant)
            
            last_speaker = sp
            
    total_words = mod_words + part_words
    mod_share = mod_words / total_words if total_words > 0 else 0.0
    
    p_turn_words.sort()
    if p_turn_words:
        n = len(p_turn_words)
        avg = sum(p_turn_words) / n
        if n % 2 == 0:
            median = (p_turn_words[n//2 - 1] + p_turn_words[n//2]) / 2.0
        else:
            median = p_turn_words[n//2]
    else:
        avg = 0
        median = 0
        
    p_count = len(participants)
    if p_count < 2:
        edge_density = 0.0
    else:
        edge_density = len(edges) / (p_count * (p_count - 1))
        
    return {
        "dialogue_turn_count": len(dialogue),
        "moderator_turn_count": moderator_turns,
        "participant_turn_count": participant_turns,
        "participant_count": p_count,
        "moderator_word_share": mod_share,
        "avg_participant_turn_words": avg,
        "median_participant_turn_words": median,
        "max_consecutive_participant_turns": max_consec,
        "participant_to_participant_edge_density": edge_density
    }

def map_human_to_synthetic(human_metric, synthetic_metrics_flat, derived_transcript, derived_edges):
    aliases = {
        "dialogue_turn_count": ["visible_utterance_count", "turn_count"],
        "moderator_turn_count": ["transcript_moderator_count"],
        "participant_turn_count": ["transcript_participant_count"],
        "participant_count": ["participant_count"],
        "moderator_word_share": ["moderator_word_share"],
        "gini_turns": ["gini_turns"],
        "gini_words": ["gini_words"],
        "max_consecutive_participant_turns": ["max_consecutive_participant_turns"],
        "avg_participant_turn_words": ["avg_participant_turn_words"],
        "median_participant_turn_words": ["median_participant_turn_words"],
        "participant_to_participant_edge_density": ["participant_to_participant_edge_density"],
        "total_edges": ["total_edges"],
        "total_repairs": ["total_repairs"],
        "total_hedges": ["total_hedges"],
        "participant_lexical_diversity_range": ["participant_lexical_diversity_range"],
        "sections_completed": ["sections_completed"],
        "section_coverage_rate": ["section_coverage_rate"],
        "section_transition_count": ["section_transition_count"],
        "stage_direction_count": ["stage_direction_count"],
        "nonverbal_marker_count": ["nonverbal_marker_count"],
        "internal_overvalidation_entries_total": ["internal_overvalidation_entries", "internal_overvalidation_entries_total"],
        "strict_target_count": ["strict_target_count"],
        "visible_overvalidation_hits": ["visible_overvalidation_hits"]
    }
    
    if human_metric in synthetic_metrics_flat:
        return "MAPPED_EXACT", synthetic_metrics_flat[human_metric]
        
    for alias in aliases.get(human_metric, []):
        if alias in synthetic_metrics_flat:
            return "MAPPED_ALIAS", synthetic_metrics_flat[alias]
            
    if human_metric == "participant_to_participant_edge_density" and human_metric in derived_edges:
        return "DERIVED_FROM_INTERACTION_EDGES", derived_edges[human_metric]
            
    if human_metric in derived_transcript:
        return "DERIVED_FROM_SYNTHETIC_TRANSCRIPT", derived_transcript[human_metric]
        
    return "UNMAPPED", None

def generate_backtest():
    gate_check = check_human_calibration_gate()
    
    out_dir = "docs/testing/stage7c6_synthetic_backtest_human_calibration"
    os.makedirs(out_dir, exist_ok=True)
    
    out_gate = gate_check.copy()
    if "metrics" in out_gate:
        del out_gate["metrics"]
    with open(os.path.join(out_dir, "human_calibration_gate_check.json"), "w", encoding="utf-8") as f:
        json.dump(out_gate, f, indent=2)
        
    run_ids = [
        "stage6c_grocery_topic_development_01",
        "stage6d_prompt_cleanup_verification_01",
        "stage6e_naturalness_topic_tethering_verification_01",
        "stage6f_internal_reasoning_calibration_verification_01"
    ]
    
    inventory = []
    run_metrics_flat = {}
    run_metrics_mapped = {}
    derived_metrics = {}
    derived_edges = {}
    
    for r in run_ids:
        a_path = f"docs/testing/assessments_hardened/{r}/assessment_metrics.json"
        has_file = os.path.exists(a_path)
        
        item = {
            "run_id": r,
            "assessment_path": a_path,
            "track_names": [],
            "metric_keys_found": [],
            "numeric_metrics": [],
            "nonnumeric_metrics": []
        }
        
        m_flat = {}
        if has_file:
            try:
                with open(a_path, "r", encoding="utf-8") as f:
                    a_data = json.load(f)
                    
                for track, t_data in a_data.items():
                    if isinstance(t_data, dict):
                        item["track_names"].append(track)
                        metrics_obj = t_data.get("metrics", t_data)
                        for k, v in metrics_obj.items():
                            if k == "status": continue
                            if isinstance(v, dict) and "value" in v:
                                val = v["value"]
                            else:
                                val = v
                                
                            item["metric_keys_found"].append(k)
                            m_flat[k] = val
                            if isinstance(val, (int, float)):
                                item["numeric_metrics"].append(k)
                            else:
                                item["nonnumeric_metrics"].append(k)
            except Exception:
                pass
                
        inventory.append(item)
        run_metrics_flat[r] = m_flat
        derived_metrics[r] = derive_metrics_from_transcript(r)
        derived_edges[r] = derive_metrics_from_interaction_edges(r)
        
    with open(os.path.join(out_dir, "synthetic_metric_inventory_by_run.json"), "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)
        
    matrix_rows = []
    human_metrics = gate_check.get("metrics", {})
    
    numeric_comparison_occurred = False
    run_mapping_stats = {r: {"mapped": 0, "total": 0} for r in run_ids}
    
    overall_mapped_exact = 0
    overall_mapped_alias = 0
    overall_derived = 0
    overall_derived_edges = 0
    overall_unmapped = 0
    
    for run in run_ids:
        r_flat = run_metrics_flat[run]
        r_derived = derived_metrics[run]
        r_edges = derived_edges[run]
        r_mapped = {}
        
        for metric, m_info in human_metrics.items():
            if m_info.get("final_status") == "CALIBRATION_REFERENCE":
                run_mapping_stats[run]["total"] += 1
                
            status, val = map_human_to_synthetic(metric, r_flat, r_derived, r_edges)
            r_mapped[metric] = {"status": status, "value": val}
            
            if m_info.get("final_status") == "CALIBRATION_REFERENCE":
                if status == "MAPPED_EXACT": overall_mapped_exact += 1
                elif status == "MAPPED_ALIAS": overall_mapped_alias += 1
                elif status == "DERIVED_FROM_SYNTHETIC_TRANSCRIPT": overall_derived += 1
                elif status == "DERIVED_FROM_INTERACTION_EDGES": overall_derived_edges += 1
                elif status == "UNMAPPED": overall_unmapped += 1
                
                if status != "UNMAPPED":
                    run_mapping_stats[run]["mapped"] += 1
                    
            c_label, interpretation = classify_synthetic_value(val, m_info, metric)
            if c_label in ["INSIDE_HUMAN_OBSERVED_RANGE", "NEAR_HUMAN_OBSERVED_RANGE", "OUTSIDE_HUMAN_OBSERVED_RANGE"]:
                numeric_comparison_occurred = True
                
            matrix_rows.append({
                "run_id": run,
                "human_metric": metric,
                "synthetic_metric_path": metric if status != "UNMAPPED" else "N/A",
                "synthetic_value": val if val is not None else "N/A",
                "source_track": "auto_resolved",
                "source_metric_key": metric,
                "mapping_status": status,
                "human_min": m_info.get("min", "N/A"),
                "human_median": m_info.get("median", "N/A"),
                "human_max": m_info.get("max", "N/A"),
                "human_observed_range": m_info.get("observed_range", "N/A"),
                "human_final_status": m_info.get("final_status", "N/A"),
                "comparison_classification": c_label,
                "interpretation": interpretation,
                "caution": "Do not optimize directly" if m_info.get("final_status") == "CALIBRATION_REFERENCE" else "N/A"
            })
        run_metrics_mapped[run] = r_mapped
            
    with open(os.path.join(out_dir, "synthetic_vs_human_process_reference_matrix.csv"), "w", newline="", encoding="utf-8") as f:
        if matrix_rows:
            writer = csv.DictWriter(f, fieldnames=matrix_rows[0].keys())
            writer.writeheader()
            writer.writerows(matrix_rows)
            
    with open(os.path.join(out_dir, "synthetic_vs_human_process_reference_matrix.md"), "w", encoding="utf-8") as f:
        f.write("# Synthetic vs Human Process Reference Matrix\n\n")
        f.write("| Run ID | Metric | Mapping Status | Synthetic Value | Human Range | Classification | Interpretation |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for row in matrix_rows:
            f.write(f"| {row['run_id']} | {row['human_metric']} | {row['mapping_status']} | {row['synthetic_value']} | {row['human_observed_range']} | {row['comparison_classification']} | {row['interpretation']} |\n")
            
    progression_dims = [
        {"dimension": "internal over-validation reduction", "metric": "internal_overvalidation_entries_total", "dir": "down"},
        {"dimension": "visible over-validation", "metric": "visible_overvalidation_hits", "dir": "down"},
        {"dimension": "named-speaker targeting mismatch", "metric": "strict_target_count", "dir": "down"},
        {"dimension": "participant-to-participant interaction", "metric": "participant_to_participant_edge_density", "dir": "up"},
        {"dimension": "moderator word share", "metric": "moderator_word_share", "dir": "down"},
        {"dimension": "participation balance", "metric": "gini_words", "dir": "down"},
        {"dimension": "turn length / long monologue rate", "metric": "max_consecutive_participant_turns", "dir": "down"},
        {"dimension": "topic tethering", "metric": "section_transition_count", "dir": "up"},
        {"dimension": "section coverage", "metric": "sections_completed", "dir": "up"},
        {"dimension": "concreteness / abstraction", "metric": "participant_lexical_diversity_range", "dir": "none"},
        {"dimension": "repair/self-correction markers", "metric": "total_repairs", "dir": "up"},
        {"dimension": "synthetic-only metrics that remain important even without human comparison", "metric": "internal_overvalidation_entries_total", "dir": "down"}
    ]
    
    progression_rows = []
    progression_has_non_na = False
    
    for pd in progression_dims:
        vals = [run_metrics_mapped[r].get(pd["metric"], {}).get("value") for r in run_ids]
        p_label, p_interp = evaluate_progression(vals, pd["dir"])
        
        if any(v is not None for v in vals):
            progression_has_non_na = True
            
        m_status = run_metrics_mapped[run_ids[-1]].get(pd["metric"], {}).get("status", "UNMAPPED")
        
        progression_rows.append({
            "dimension": pd["dimension"],
            "metric_used": pd["metric"],
            "mapping_status": m_status,
            "stage6c_value": vals[0] if vals[0] is not None else "N/A",
            "stage6d_value": vals[1] if vals[1] is not None else "N/A",
            "stage6e_value": vals[2] if vals[2] is not None else "N/A",
            "stage6f_value": vals[3] if vals[3] is not None else "N/A",
            "expected_direction": pd["dir"],
            "observed_direction": "calculated_by_logic",
            "classification": p_label,
            "reason": p_interp
        })
        
    with open(os.path.join(out_dir, "stage6c_to_6f_progression_table.csv"), "w", newline="", encoding="utf-8") as f:
        if progression_rows:
            writer = csv.DictWriter(f, fieldnames=progression_rows[0].keys())
            writer.writeheader()
            writer.writerows(progression_rows)
            
    with open(os.path.join(out_dir, "stage6c_to_6f_progression_table.md"), "w", encoding="utf-8") as f:
        f.write("# Stage 6C to 6F Progression\n\n")
        f.write("| Dimension | Metric Used | 6C | 6D | 6E | 6F | Classification | Reason |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for r in progression_rows:
            f.write(f"| {r['dimension']} | {r['metric_used']} | {r['stage6c_value']} | {r['stage6d_value']} | {r['stage6e_value']} | {r['stage6f_value']} | {r['classification']} | {r['reason']} |\n")
            
    known_issues = [
        {"issue": "internal over-validation", "intended": "internal_overvalidation_entries_total", "type": "direct"},
        {"issue": "visible over-validation", "intended": "visible_overvalidation_hits", "type": "direct"},
        {"issue": "speaker targeting mismatch", "intended": "strict_target_count", "type": "direct"},
        {"issue": "topic drift", "intended": "section_transition_count", "type": "proxy"},
        {"issue": "over-polished participant style", "intended": "total_repairs", "type": "direct"},
        {"issue": "insufficient participant-to-participant uptake", "intended": "participant_to_participant_edge_density", "type": "direct"},
        {"issue": "round-robin / over-managed balance", "intended": "moderator_word_share", "type": "direct"},
        {"issue": "guide coverage or section transition problems", "intended": "sections_completed", "type": "proxy"}
    ]
    
    visibility_has_metric = False
    with open(os.path.join(out_dir, "known_issue_visibility_matrix.md"), "w", encoding="utf-8") as f:
        f.write("# Known Issue Visibility Matrix\n\n")
        f.write("| Issue | Intended Metric | Available | Stage 6C Val | Stage 6F Val | Visibility Status |\n")
        f.write("|---|---|---|---|---|---|\n")
        for i in known_issues:
            m = i["intended"]
            val_6c = run_metrics_mapped["stage6c_grocery_topic_development_01"].get(m, {}).get("value")
            val_6f = run_metrics_mapped["stage6f_internal_reasoning_calibration_verification_01"].get(m, {}).get("value")
            av = "Yes" if val_6f is not None else "No"
            
            if val_6f is not None:
                visibility_has_metric = True
                status = "VISIBLE_WITH_PROXY" if i["type"] == "proxy" else "VISIBLE_WITH_DIRECT_METRIC"
            else:
                status = "NOT_VISIBLE_METRIC_MISSING"
                
            f.write(f"| {i['issue']} | {m} | {av} | {val_6c if val_6c is not None else 'N/A'} | {val_6f if val_6f is not None else 'N/A'} | {status} |\n")
            
    is_blocked = gate_check["gate_status"] != "PASS"
    all_runs_loaded = os.path.exists("docs/testing/assessments_hardened/stage6c_grocery_topic_development_01/assessment_metrics.json") and \
                      os.path.exists("docs/testing/assessments_hardened/stage6d_prompt_cleanup_verification_01/assessment_metrics.json") and \
                      os.path.exists("docs/testing/assessments_hardened/stage6e_naturalness_topic_tethering_verification_01/assessment_metrics.json") and \
                      os.path.exists("docs/testing/assessments_hardened/stage6f_internal_reasoning_calibration_verification_01/assessment_metrics.json")
                      
    # We must enforce that edge density is mapped or derived for all four
    p2p_all_mapped = True
    for r in run_ids:
        m_stat = run_metrics_mapped[r].get("participant_to_participant_edge_density", {}).get("status", "UNMAPPED")
        if m_stat == "UNMAPPED":
            p2p_all_mapped = False
            break
            
    min_50_pct_mapped = True
    for r, stats in run_mapping_stats.items():
        if stats["total"] > 0 and (stats["mapped"] / stats["total"]) < 0.5:
            min_50_pct_mapped = False
            
    at_least_one_mapped = any(s["mapped"] > 0 for s in run_mapping_stats.values())
    
    if is_blocked or not all_runs_loaded:
        final_verdict = "STAGE7C6_BLOCKED"
    elif not min_50_pct_mapped or not at_least_one_mapped or not numeric_comparison_occurred or not progression_has_non_na or not visibility_has_metric or not p2p_all_mapped:
        final_verdict = "STAGE7C6_SYNTHETIC_BACKTEST_PARTIAL"
    else:
        final_verdict = "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE"
        
    with open(os.path.join(out_dir, "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"), "w", encoding="utf-8") as f:
        f.write("# Stage 7C.6: Synthetic Backtest With Human-Calibrated Process References\n\n")
        f.write("## 1. Scope\n")
        f.write("- This is a process backtesting evaluation only.\n")
        f.write("- This is not outcome validity.\n")
        f.write("- This is not theme equivalence.\n")
        f.write("- This does not validate synthetic data.\n")
        f.write("- Human ranges are soft process references only.\n")
        f.write("- Human baselines are QESB election and PHIND work-at-home, while synthetic runs may be grocery.\n\n")
        
        f.write("## 2. Mapping & Derivation Stats\n")
        f.write(f"- CALIBRATION_REFERENCE metrics available in baseline: {run_mapping_stats['stage6c_grocery_topic_development_01']['total']}\n")
        f.write(f"- Mapped EXACT: {overall_mapped_exact // 4} (avg per run)\n")
        f.write(f"- Mapped ALIAS: {overall_mapped_alias // 4} (avg per run)\n")
        f.write(f"- Derived from transcript: {overall_derived // 4} (avg per run)\n")
        f.write(f"- Derived from interaction edges: {overall_derived_edges // 4} (avg per run)\n")
        f.write(f"- Unmapped (CALIBRATION_REFERENCE): {overall_unmapped // 4} (avg per run)\n")
        for r, st in run_mapping_stats.items():
            pct = (st["mapped"]/st["total"]*100) if st["total"]>0 else 0
            f.write(f"- Run {r} mapped: {pct:.1f}%\n")
        f.write(f"- Numeric comparisons occurred: {numeric_comparison_occurred}\n")
        f.write(f"- Progression has non-N/A values: {progression_has_non_na}\n")
        f.write(f"- Known issue visibility has supporting metrics: {visibility_has_metric}\n\n")
        
        f.write("## 3. Audit Status\n")
        gate_verdict = "BLOCKED" if is_blocked else "COMPLETE"
        f.write(f"- Stage 7C.5 per-baseline reconciliation: {gate_verdict}\n\n")
        
        f.write("## Final Verdict\n")
        f.write(f"**{final_verdict}**\n")

if __name__ == "__main__":
    generate_backtest()
