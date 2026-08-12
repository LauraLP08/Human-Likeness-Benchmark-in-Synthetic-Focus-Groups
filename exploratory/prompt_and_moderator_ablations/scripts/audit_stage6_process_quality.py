import json
from pathlib import Path
from collections import defaultdict

def extract_metrics():
    base_dir = Path("output/session_logs")
    runs = ["stage5_replication_grocery_01", "stage5_replication_grocery_02", "stage5_replication_grocery_03"]
    results = {}

    agree_markers = ["agree", "same", "yeah", "exactly", "i get that"]
    disagree_markers = ["but", "however", "not really", "i disagree", "on the other hand"]

    print("STAGE 6 PROCESS QUALITY EXTRACTION\n" + "="*40)
    for run in runs:
        run_dir = base_dir / run
        if not run_dir.exists():
            continue
            
        # load artifacts
        with open(run_dir / "transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        with open(run_dir / "run_metadata.json", encoding="utf-8") as f:
            meta = json.load(f)
        with open(run_dir / "moderator_log.json", encoding="utf-8") as f:
            mod_log = json.load(f)
        with open(run_dir / "api_calls.jsonl", encoding="utf-8") as f:
            api_calls = [json.loads(line) for line in f if line.strip()]

        total_transcript_entries = len(transcript)
        mod_utterances = sum(1 for t in transcript if t["speaker_id"] == "MODERATOR")
        part_utterances = sum(1 for t in transcript if t["speaker_id"] != "MODERATOR")
        
        participant_counts = defaultdict(int)
        for t in transcript:
            if t["speaker_id"] != "MODERATOR":
                participant_counts[t["speaker_name"]] += 1
                
        # API calls metrics
        val_fallback = meta.get("validation_fallback_count", 0)
        part_failures = sum(1 for e in api_calls 
                            if e.get("event_type") == "participant_engagement_assessment" 
                            and (e.get("parse_success") is False or e.get("validation_success") is False))
        
        # Interactions
        part_to_part_refs = 0
        agree_count = 0
        disagree_count = 0
        
        for t in transcript:
            if t["speaker_id"] != "MODERATOR":
                text = t["content"].lower()
                # Basic name reference heuristic (P1, P2... or names if mapped)
                # We'll just look for P1, P2, P3, P4, P5, P6 as crude heuristic
                for px in ["p1", "p2", "p3", "p4", "p5", "p6", "alex", "jordan", "taylor", "morgan", "sam", "casey", "maya", "robert", "priya", "daniel"]:
                    # Note: we don't know the exact names, but "P1" is often used, or real names.
                    if px in text and px.lower() not in t["speaker_name"].lower():
                        part_to_part_refs += 1
                        break # count once per utterance max
                
                if any(m in text for m in agree_markers):
                    agree_count += 1
                if any(m in text for m in disagree_markers):
                    disagree_count += 1

        # Moderator log checks
        interventions = meta.get("intervention_mode_counts", {})
        actions = meta.get("moderator_action_counts", {})
        speak_interventions = interventions.get("speak", 0)
        observe_interventions = interventions.get("observe", 0)
        
        mod_visible_matches_speak = (mod_utterances == speak_interventions)
        
        all_justified = all(bool(m.get("brief_justification")) for m in mod_log)
        all_consensus = all(m.get("consensus_risk_assessment") is not None for m in mod_log)
        all_flags = all(m.get("group_dynamic_flags") is not None for m in mod_log)
        
        # Are observe interventions absent from transcript?
        # True if total moderator entries in transcript == speak interventions
        observe_absent = (mod_utterances == speak_interventions)

        results[run] = {
            "transcript_entries": total_transcript_entries,
            "visible_moderator_utterances": mod_utterances,
            "participant_utterances": part_utterances,
            "utterance_count_by_participant": dict(participant_counts),
            "moderator_log_entries": len(mod_log),
            "intervention_mode_counts": interventions,
            "action_counts": actions,
            "observe_count": observe_interventions,
            "speak_count": speak_interventions,
            "validation_fallback_count": val_fallback,
            "participant_engagement_failures": part_failures,
            "participant_to_participant_refs": part_to_part_refs,
            "agreement_markers": agree_count,
            "disagreement_markers": disagree_count,
            "mod_visible_matches_speak": mod_visible_matches_speak,
            "observe_absent_from_transcript": observe_absent,
            "all_entries_have_justification": all_justified,
            "all_entries_have_consensus_risk": all_consensus,
            "all_entries_have_group_flags": all_flags
        }

        print(f"--- {run} ---")
        print(f"Transcript: {total_transcript_entries} (Mod: {mod_utterances}, Part: {part_utterances})")
        print(f"Participant Counts: {dict(participant_counts)}")
        print(f"Interventions - Speak: {speak_interventions}, Observe: {observe_interventions}")
        print(f"Part Failures: {part_failures}, P2P Refs: {part_to_part_refs}")
        print(f"Agree: {agree_count}, Disagree: {disagree_count}")
        print(f"Observe absent: {observe_absent}, Audit info complete: {all_justified and all_consensus and all_flags}\n")

    output_path = Path("docs/testing/STAGE6_PROCESS_QUALITY_EXTRACTED_METRICS.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    extract_metrics()
