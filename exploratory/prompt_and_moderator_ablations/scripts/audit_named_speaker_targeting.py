import os
import json
import glob

def audit_targeting():
    logs_dir = "output/session_logs"
    if not os.path.exists(logs_dir):
        print("No session logs found.")
        return

    run_dirs = glob.glob(os.path.join(logs_dir, "*"))
    
    strict_targets = 0
    strict_honored = 0
    strict_not_honored = 0
    soft_group_invitations = 0
    broad_group_redirects = 0
    opening_section_transitions = 0
    ambiguous_cases = 0
    
    true_targeting_mismatches = []
    
    strict_actions = ["direct_probe", "reactivate_silent", "invite_to_speak"]
    group_actions = ["redirect_to_group", "ask_initial_to_group", "invite_dissent", "synthesize_and_challenge"]
    section_actions = ["section_transition"]
    
    participant_names = ["Maya", "Robert", "Priya", "Daniel", "Sarah", "Tom", "Aisha", "Marcus"]
    
    for rdir in run_dirs:
        run_id = os.path.basename(rdir)
        mod_log_path = os.path.join(rdir, "moderator_log.json")
        trans_path = os.path.join(rdir, "transcript.json")
        
        if not os.path.exists(mod_log_path) or not os.path.exists(trans_path):
            continue
            
        try:
            with open(mod_log_path, "r", encoding="utf-8") as f:
                mod_logs = json.load(f)
            with open(trans_path, "r", encoding="utf-8") as f:
                transcript = json.load(f)
        except Exception as e:
            continue
            
        for entry in mod_logs:
            action = entry.get("action")
            target = entry.get("target")
            turn_index = entry.get("turn")
            
            # Find the moderator utterance in the transcript for this turn
            mod_utt = None
            for u in transcript:
                if u.get("turn") == turn_index and u.get("speaker_id") == "MODERATOR":
                    mod_utt = u
                    break
                    
            if not mod_utt:
                continue
                
            utterance_text = mod_utt.get("content", "")
            
            # Count names
            names_in_utterance = [name for name in participant_names if name in utterance_text]
            
            # Classification
            classification = "UNKNOWN"
            expected_speaker_id = None
            expected_speaker_name = None
            
            if action in strict_actions and target and target.startswith("P"):
                # Check if it uniquely names the target or is generally directed
                # As a heuristic, if target is Px, we treat it as STRICT_TARGET
                classification = "STRICT_TARGET"
                expected_speaker_id = target
            elif target == "group" and len(names_in_utterance) > 0:
                classification = "SOFT_GROUP_WITH_NAMES"
            elif target == "group" and len(names_in_utterance) == 0:
                if action in group_actions:
                    classification = "BROAD_GROUP_REDIRECT"
                elif action in section_actions:
                    classification = "OPENING_OR_SECTION_TRANSITION"
                else:
                    classification = "BROAD_GROUP_REDIRECT"
            elif action in section_actions or action == "ask_initial_to_group":
                classification = "OPENING_OR_SECTION_TRANSITION"
            else:
                classification = "AMBIGUOUS"
                
            if classification == "STRICT_TARGET":
                strict_targets += 1
            elif classification == "SOFT_GROUP_WITH_NAMES":
                soft_group_invitations += 1
            elif classification == "BROAD_GROUP_REDIRECT":
                broad_group_redirects += 1
            elif classification == "OPENING_OR_SECTION_TRANSITION":
                opening_section_transitions += 1
            else:
                ambiguous_cases += 1
                
            if classification == "STRICT_TARGET":
                # Now find the NEXT participant utterance (turn > turn_index, speaker != MODERATOR)
                next_part_utt = None
                for u in transcript:
                    if u.get("turn") > turn_index and u.get("speaker_id") != "MODERATOR":
                        next_part_utt = u
                        break
                        
                if next_part_utt:
                    next_speaker_id = next_part_utt.get("speaker_id")
                    next_speaker_name = next_part_utt.get("speaker_name", "")
                    selection_mode = next_part_utt.get("selection_mode", "unknown")
                    
                    if next_speaker_id == expected_speaker_id:
                        strict_honored += 1
                    else:
                        strict_not_honored += 1
                        true_targeting_mismatches.append({
                            "run_id": run_id,
                            "turn": turn_index,
                            "action": action,
                            "target": target,
                            "moderator_utterance": utterance_text,
                            "next_speaker_id": next_speaker_id,
                            "next_speaker_name": next_speaker_name,
                            "selection_mode": selection_mode
                        })
                        
    output_lines = []
    output_lines.append("=== TARGETING CLASSIFICATION RE-AUDIT ===")
    output_lines.append(f"Total Strict Participant-Targeted Interventions: {strict_targets}")
    output_lines.append(f"Strict Targets Honored: {strict_honored}")
    output_lines.append(f"Strict Targets Not Honored (True Mismatches): {strict_not_honored}")
    
    if strict_targets > 0:
        rate = (strict_honored / strict_targets) * 100
        output_lines.append(f"Strict-Target Honor Rate: {rate:.1f}%")
        
    output_lines.append("")
    output_lines.append("--- OTHER CATEGORIES ---")
    output_lines.append(f"Soft Group Invitations: {soft_group_invitations}")
    output_lines.append(f"Broad Group Redirects: {broad_group_redirects}")
    output_lines.append(f"Section/Opening Cases: {opening_section_transitions}")
    output_lines.append(f"Ambiguous Cases: {ambiguous_cases}")
    output_lines.append("")
    
    output_lines.append("=== TRUE TARGETING MISMATCHES ===")
    for m in true_targeting_mismatches:
        output_lines.append(f"Run: {m['run_id']} | Turn: {m['turn']}")
        output_lines.append(f"Action: {m['action']} | Target: {m['target']}")
        output_lines.append(f"Moderator said: {m['moderator_utterance']}")
        output_lines.append(f"Next Speaker: {m['next_speaker_id']} ({m['next_speaker_name']}) [Mode: {m['selection_mode']}]")
        output_lines.append("-" * 40)
        
    output_text = "\n".join(output_lines)
    print(output_text)
    
    output_path = "docs/testing/stage6f_named_speaker_targeting_strict_reaudit_output.txt"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_text)

if __name__ == "__main__":
    audit_targeting()
