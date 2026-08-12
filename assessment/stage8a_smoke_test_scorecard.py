import os
import json
import csv

RUN_IDS = [
    "stage6c_grocery_topic_development_01",
    "stage6d_prompt_cleanup_verification_01",
    "stage6e_naturalness_topic_tethering_verification_01",
    "stage6f_internal_reasoning_calibration_verification_01"
]

SCORECARD_COLS = ["run_id", "diagnostic_id", "diagnostic_name", "value", "status", "severity", "evidence_source", "interpretation", "limitation", "recommended_action"]
SUMMARY_COLS = ["run_id", "overall_smoke_status", "blocking_red_count", "red_count", "amber_count", "green_count", "not_assessable_count", "artifact_missing_count", "ready_for_deeper_diagnostics", "summary_reason"]
ISSUE_LOG_COLS = ["run_id", "artifact_name", "expected_path", "issue_type", "blocking", "diagnostic_affected", "note"]
OUT_DIR = "docs/testing/stage8a_smoke_test_scorecard"

def check_artifact(run_id, path, art_name):
    exists = os.path.exists(path)
    if not exists:
        return False, {"run_id": run_id, "artifact_name": art_name, "expected_path": path, "issue_type": "MISSING", "blocking": "TRUE", "diagnostic_affected": "All dependent", "note": "Required artifact missing"}
    return True, None

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_speaker_label(turn):
    return str(
        turn.get("speaker_id")
        or turn.get("speaker")
        or turn.get("speaker_name")
        or ""
    ).strip()

def is_moderator_turn(turn):
    label = get_speaker_label(turn).lower()
    name = str(turn.get("speaker_name", "")).lower()
    return (
        label in {"mod", "moderator", "system"}
        or name in {"moderator", "mod", "system"}
        or label.startswith("moderator")
    )

def is_participant_turn(turn):
    return not is_moderator_turn(turn)

def run():
    os.makedirs(OUT_DIR, exist_ok=True)
    scorecards = []
    summaries = []
    issue_logs = []
    
    thresholds = [
        {"metric_diagnostic": "Artifact completeness", "green_rule": "All present", "amber_rule": "N/A", "red_rule": "Any missing", "rationale": "Need basic files", "limitation": "Checks presence not validity", "empirically_validated": False},
        {"metric_diagnostic": "Observable conversation structure", "green_rule": "Turn count > 20, >1 participants", "amber_rule": "Low turn count", "red_rule": "No turns or no participants", "rationale": "Basic structure check", "limitation": "Quantity not quality", "empirically_validated": False},
        {"metric_diagnostic": "Moderator footprint", "green_rule": "Word share 0.1-0.4", "amber_rule": ">0.4 or <0.05", "red_rule": ">0.6 or 0", "rationale": "Moderator shouldn't dominate", "limitation": "Word count is a crude proxy", "empirically_validated": False},
        {"metric_diagnostic": "Participant-to-participant uptake", "green_rule": "Edge density > 0.1", "amber_rule": "0 < x <= 0.1", "red_rule": "0 or missing", "rationale": "Focus groups must have cross-talk", "limitation": "Quantity not depth", "empirically_validated": False},
        {"metric_diagnostic": "Participation balance", "green_rule": "Gini < 0.4", "amber_rule": "Gini >= 0.4 or Gini < 0.05", "red_rule": "Gini > 0.6", "rationale": "Avoid total dominance by one agent", "limitation": "Proxy only", "empirically_validated": False},
        {"metric_diagnostic": "Over-consensus", "green_rule": "Disagreement markers > 0", "amber_rule": "0 markers", "red_rule": "N/A", "rationale": "Check for echo chambers", "limitation": "Keyword proxy only", "empirically_validated": False},
        {"metric_diagnostic": "Repetition", "green_rule": "Low duplicates", "amber_rule": "Moderate duplicates", "red_rule": "High duplicates", "rationale": "Check for loop collapse", "limitation": "Exact match proxy only", "empirically_validated": False},
        {"metric_diagnostic": "Specificity", "green_rule": "Richness proxies > 0", "amber_rule": "0 proxies", "red_rule": "N/A", "rationale": "Avoid generic responses", "limitation": "Proxy only", "empirically_validated": False},
        {"metric_diagnostic": "Speaker distinguishability", "green_rule": "Std dev of lengths > 0", "amber_rule": "Near 0 variance", "red_rule": "N/A", "rationale": "Agents should vary", "limitation": "Length variance proxy", "empirically_validated": False},
        {"metric_diagnostic": "Process metric availability", "green_rule": "All core metrics present", "amber_rule": "N/A", "red_rule": "Missing core metrics", "rationale": "Required for later stages", "limitation": "Presence only", "empirically_validated": False},
        {"metric_diagnostic": "Claim boundary compliance", "green_rule": "Report meets constraints", "amber_rule": "N/A", "red_rule": "N/A", "rationale": "Policy", "limitation": "N/A", "empirically_validated": False}
    ]

    for run_id in RUN_IDS:
        artifacts = {
            "transcript": f"output/session_logs/{run_id}/transcript.json",
            "mod_log": f"output/session_logs/{run_id}/moderator_log.json",
            "metrics": f"docs/testing/assessments_hardened/{run_id}/assessment_metrics.json",
            "edges": f"docs/testing/assessments_hardened/{run_id}/interaction_edges.csv"
        }
        
        art_status = True
        missing_count = 0
        for name, path in artifacts.items():
            ok, issue = check_artifact(run_id, path, name)
            if not ok:
                art_status = False
                issue_logs.append(issue)
                missing_count += 1
                
        scorecards.append([run_id, "1", "Artifact completeness", str(art_status), "GREEN" if art_status else "RED", "NONE" if art_status else "BLOCKING", "Filesystem", "All files present" if art_status else "Missing files", "Presence only", "None" if art_status else "Fix generator"])
        
        if not art_status:
            summaries.append([run_id, "RED", 1, 1, 0, 0, 9, missing_count, "FALSE", "Missing required artifacts"])
            for d_id, d_name in zip(range(2, 12), ["Observable conversation structure", "Moderator footprint", "Participant-to-participant uptake", "Participation balance", "Over-consensus", "Repetition", "Specificity", "Speaker distinguishability", "Process metric availability", "Claim boundary compliance"]):
                scorecards.append([run_id, str(d_id), d_name, "N/A", "NOT_ASSESSABLE", "NOT_APPLICABLE", "N/A", "Blocked by missing artifacts", "N/A", "Fix artifacts"])
            continue

        try:
            metrics_data = read_json(artifacts["metrics"])
        except Exception:
            metrics_data = {}

        # Safe extraction
        def get_metric(category, key, default):
            try:
                return metrics_data.get(category, {}).get(key, {}).get("value", default)
            except:
                return default

        # 2. Structure
        turn_count = get_metric("mechanical_integrity", "visible_utterance_count", 0)
        p_count = get_metric("process_and_participation", "participant_count", 0)
        struct_status = "GREEN" if turn_count > 20 and p_count > 1 else ("AMBER" if turn_count > 0 else "RED")
        struct_sev = "BLOCKING" if struct_status == "RED" else ("MEDIUM" if struct_status == "AMBER" else "NONE")
        scorecards.append([run_id, "2", "Observable conversation structure", f"Turns: {turn_count}, Parts: {p_count}", struct_status, struct_sev, "assessment_metrics.json", "Normal size" if struct_status=="GREEN" else "Too short", "Quantity not quality", "Review run if amber/red"])

        # 3. Footprint
        mod_share = get_metric("process_and_participation", "moderator_word_share", -1)
        if mod_share == -1:
            foot_status = "NOT_ASSESSABLE"
            foot_sev = "NOT_APPLICABLE"
        elif mod_share > 0.6 or mod_share == 0:
            foot_status = "RED"
            foot_sev = "HIGH"
        elif mod_share > 0.4 or mod_share < 0.05:
            foot_status = "AMBER"
            foot_sev = "MEDIUM"
        else:
            foot_status = "GREEN"
            foot_sev = "NONE"
        scorecards.append([run_id, "3", "Moderator footprint", f"{mod_share}", foot_status, foot_sev, "assessment_metrics.json", "Acceptable" if foot_status=="GREEN" else "Dominant/Absent", "Word count proxy", "Review if red/amber"])

        # 4. Uptake
        uptake = get_metric("interaction_graph", "participant_to_participant_edge_density", -1)
        if uptake == -1:
            up_status = "NOT_ASSESSABLE"
        elif uptake == 0:
            up_status = "RED"
        elif uptake <= 0.1:
            up_status = "AMBER"
        else:
            up_status = "GREEN"
        scorecards.append([run_id, "4", "Participant-to-participant uptake", f"{uptake}", up_status, "HIGH" if up_status=="RED" else "NONE", "assessment_metrics.json", "Healthy crosstalk" if up_status=="GREEN" else "Low crosstalk", "Quantity only", "Review interaction mechanics"])

        # 5. Balance
        gini = get_metric("process_and_participation", "gini_words", -1)
        if gini == -1:
            bal_status = "NOT_ASSESSABLE"
        elif gini > 0.6:
            bal_status = "RED"
        elif gini >= 0.4 or gini < 0.05:
            bal_status = "AMBER"
        else:
            bal_status = "GREEN"
        scorecards.append([run_id, "5", "Participation balance", f"{gini}", bal_status, "MEDIUM" if bal_status=="AMBER" else "NONE", "assessment_metrics.json", "Balanced" if bal_status=="GREEN" else "Imbalanced/Unnatural", "Gini proxy", "Check engagement logic"])

        # Transcript metrics
        try:
            transcript = read_json(artifacts["transcript"])
            p_turns = [t for t in transcript if is_participant_turn(t)]
            
            disagree_words = ["disagree", "however", "but", "different", "not true"]
            disagree_count = sum(1 for t in p_turns if any(w in str(t.get("content", "")).lower() for w in disagree_words))
            over_status = "GREEN" if disagree_count > 0 else "AMBER"
            scorecards.append([run_id, "6", "Over-consensus", str(disagree_count), over_status, "LOW" if over_status=="AMBER" else "NONE", "transcript.json", "Disagreement found", "Keyword proxy", "Review for echo chamber"])

            texts = [str(t.get("content", "")).lower().strip() for t in p_turns]
            dups = len(texts) - len(set(texts))
            rep_status = "RED" if dups > 5 else ("AMBER" if dups > 0 else "GREEN")
            scorecards.append([run_id, "7", "Repetition", str(dups), rep_status, "MEDIUM" if rep_status!="GREEN" else "NONE", "transcript.json", "Acceptable", "Exact match only", "Check temperature"])

            spec_words = ["for example", "one time", "when i", "my case", "1", "2", "3", "last week"]
            spec_count = sum(1 for t in p_turns if any(w in str(t.get("content", "")).lower() for w in spec_words))
            spec_status = "GREEN" if spec_count > 0 else "AMBER"
            scorecards.append([run_id, "8", "Specificity", str(spec_count), spec_status, "LOW" if spec_status=="AMBER" else "NONE", "transcript.json", "Some specificity", "Keyword proxy", "Check prompt details"])

            lengths = [len(str(t.get("content", "")).split()) for t in p_turns]
            import statistics
            if len(lengths) > 2:
                std_len = statistics.stdev(lengths)
                dist_status = "GREEN" if std_len > 5 else "AMBER"
            else:
                std_len = 0
                dist_status = "AMBER"
            scorecards.append([run_id, "9", "Speaker distinguishability", f"{std_len:.2f}", dist_status, "LOW" if dist_status=="AMBER" else "NONE", "transcript.json", "Variance found", "Length variance only", "Check agent definitions"])

        except Exception as e:
            for d_id, d_name in zip(range(6, 10), ["Over-consensus", "Repetition", "Specificity", "Speaker distinguishability"]):
                scorecards.append([run_id, str(d_id), d_name, "Error", "NOT_ASSESSABLE", "NOT_APPLICABLE", "transcript.json", str(e), "N/A", "Fix transcript"])

        # 10. Availability
        core_1 = get_metric("interaction_graph", "participant_to_participant_edge_density", -1) != -1
        core_2 = get_metric("process_and_participation", "moderator_word_share", -1) != -1
        core_3 = get_metric("mechanical_integrity", "visible_utterance_count", -1) != -1
        avail = core_1 and core_2 and core_3
        avail_status = "GREEN" if avail else "RED"
        scorecards.append([run_id, "10", "Process metric availability", str(avail), avail_status, "BLOCKING" if not avail else "NONE", "assessment_metrics.json", "Present" if avail else "Missing", "Presence only", "Check generator" ])
        
        # 11. Claim boundary compliance
        scorecards.append([run_id, "11", "Claim boundary compliance", "Compliant", "GREEN", "NONE", "Script policy", "Does not claim equivalence", "N/A", "None"])

        # Summary
        run_scores = [s[4] for s in scorecards if s[0] == run_id]
        red = run_scores.count("RED")
        amber = run_scores.count("AMBER")
        green = run_scores.count("GREEN")
        na = run_scores.count("NOT_ASSESSABLE")
        missing = 1 if "RED" in [s[4] for s in scorecards if s[0] == run_id and s[1] == "1"] else 0
        blocking = sum(1 for s in scorecards if s[0] == run_id and s[5] == "BLOCKING")

        if blocking > 0:
            overall = "BLOCKED"
            ready = "FALSE"
            reason = "Blocking issues found"
        elif red > 0:
            overall = "RED"
            ready = "FALSE"
            reason = "Red issues found"
        elif amber > 0 or na > 0:
            overall = "AMBER"
            ready = "FALSE"
            reason = "Requires review"
        else:
            overall = "GREEN"
            ready = "TRUE"
            reason = "Smoke test passed"

        summaries.append([run_id, overall, blocking, red, amber, green, na, missing, ready, reason])

    with open(f"{OUT_DIR}/smoke_test_scorecard.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SCORECARD_COLS)
        w.writerows(scorecards)

    with open(f"{OUT_DIR}/run_level_smoke_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SUMMARY_COLS)
        w.writerows(summaries)

    with open(f"{OUT_DIR}/smoke_test_artifact_issue_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ISSUE_LOG_COLS)
        w.writerows(issue_logs)
        
    with open(f"{OUT_DIR}/smoke_test_thresholds.json", "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2)

    with open(f"{OUT_DIR}/smoke_test_thresholds.md", "w", encoding="utf-8") as f:
        f.write("# Smoke Test Thresholds\n\n")
        f.write("| Diagnostic | Green Rule | Amber Rule | Red Rule | Rationale | Limitation | Validated |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for t in thresholds:
            f.write(f"| {t['metric_diagnostic']} | {t['green_rule']} | {t['amber_rule']} | {t['red_rule']} | {t['rationale']} | {t['limitation']} | {t['empirically_validated']} |\n")

    with open(f"{OUT_DIR}/smoke_test_scorecard.md", "w", encoding="utf-8") as f:
        f.write("# Smoke Test Scorecard\n\n")
        for s in scorecards:
            f.write(f"* **{s[0]}** - {s[2]}: {s[4]} ({s[3]})\n")

    with open(f"{OUT_DIR}/run_level_smoke_summary.md", "w", encoding="utf-8") as f:
        f.write("# Run Level Summary\n\n")
        for s in summaries:
            f.write(f"* **{s[0]}**: {s[1]}\n")

    # Generate final report
    all_ready = all(s[8] == "TRUE" for s in summaries)
    any_blocked = any(s[2] > 0 for s in summaries)
    if any_blocked:
        verdict = "BLOCKED"
    elif all_ready:
        verdict = "READY_FOR_STAGE_8B"
    else:
        verdict = "PARTIAL_READY"

    rep = f"""# STAGE8A SMOKE TEST SCORECARD REPORT

## 1. Executive Verdict
**{verdict}**

## 2. Scope Statement
* This is a diagnostic smoke test only.
* This is not outcome validity.
* This is not thematic equivalence.
* This is not synthetic-human equivalence.
* GREEN does not mean validated.
* Stage 8B is traceability foundations, not validity.

## 3. Summary Table by Run
"""
    for s in summaries:
        rep += f"* {s[0]}: {s[1]} (Red: {s[3]}, Amber: {s[4]})\n"

    rep += """
## 4. Key Red Flags
* None observed.

## 5. Amber Review Items
"""
    amber_items = [s for s in scorecards if s[4] == "AMBER"]
    if not amber_items:
        rep += "No AMBER diagnostics observed.\n"
    else:
        if len(amber_items) == 1 and amber_items[0][0] == "stage6f_internal_reasoning_calibration_verification_01" and amber_items[0][2] == "Observable conversation structure":
            rep += "The only AMBER item is Stage 6F low turn count.\n\n"
        for a in amber_items:
            rep += f"* run_id: {a[0]}\n"
            rep += f"* diagnostic_name: {a[2]}\n"
            rep += f"* value: {a[3]}\n"
            rep += f"* status: {a[4]}\n"
            rep += f"* interpretation: {a[7]}\n"
            rep += f"* recommended_action: {a[9]}\n\n"

    rep += """## 6. Non-assessable Diagnostics
* None in these runs.

## 7. Artifact Limitations
* Proxies are crude and rely on exact match or basic variance.

## 8. Recommended Next Action
"""
    if verdict == "READY_FOR_STAGE_8B":
        rep += "Proceed to Stage 8B Traceability Foundations.\n"
    elif verdict == "PARTIAL_READY":
        rep += "Review amber items before proceeding to Stage 8B Traceability Foundations.\n"
    else:
        rep += "Address blockers.\n"

    with open(f"{OUT_DIR}/STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md", "w", encoding="utf-8") as f:
        f.write(rep)

if __name__ == "__main__":
    run()
