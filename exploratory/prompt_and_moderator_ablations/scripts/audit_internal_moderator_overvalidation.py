import os
import json
import glob
import re

def audit_overvalidation():
    logs_dir = "output/session_logs"
    if not os.path.exists(logs_dir):
        print("No session logs found.")
        return

    run_dirs = glob.glob(os.path.join(logs_dir, "*"))
    
    flagged_phrases = [
        "excellent",
        "rich data",
        "powerful",
        "remarkable",
        "sophisticated",
        "vulnerable",
        "honest data",
        "exactly what the research needs",
        "intellectual honesty",
        "emotional richness",
        "analytically rich",
        "valuable depth"
    ]
    
    # Compile regex pattern to match any phrase, case insensitive
    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, flagged_phrases)) + r')\b', re.IGNORECASE)
    
    target_fields = [
        "situation_assessment",
        "brief_justification",
        "justification"
    ]
    
    output_lines = []
    
    for rdir in run_dirs:
        run_id = os.path.basename(rdir)
        mod_log_path = os.path.join(rdir, "moderator_log.json")
        
        if not os.path.exists(mod_log_path):
            continue
            
        try:
            with open(mod_log_path, "r", encoding="utf-8") as f:
                mod_logs = json.load(f)
        except Exception as e:
            continue
            
        total_entries = len(mod_logs)
        entries_with_flags = 0
        total_phrase_hits = 0
        examples = []
        
        for entry in mod_logs:
            has_flag = False
            for field in target_fields:
                val = entry.get(field, "")
                if val and isinstance(val, str):
                    matches = pattern.findall(val)
                    if matches:
                        has_flag = True
                        total_phrase_hits += len(matches)
                        examples.append({
                            "turn": entry.get("turn"),
                            "field": field,
                            "matched": matches,
                            "excerpt": val
                        })
            
            # also check queued_next_action.rationale
            queued = entry.get("queued_next_action")
            if queued and isinstance(queued, dict):
                val = queued.get("rationale", "")
                if val and isinstance(val, str):
                    matches = pattern.findall(val)
                    if matches:
                        has_flag = True
                        total_phrase_hits += len(matches)
                        examples.append({
                            "turn": entry.get("turn"),
                            "field": "queued_next_action.rationale",
                            "matched": matches,
                            "excerpt": val
                        })
                        
            if has_flag:
                entries_with_flags += 1
                
        if total_entries > 0:
            rate = (entries_with_flags / total_entries) * 100
        else:
            rate = 0.0
            
        if "stage6e" in run_id or "stage6f" in run_id:
            output_lines.append(f"Run ID: {run_id}")
            output_lines.append(f"Total Entries: {total_entries}")
            output_lines.append(f"Entries with Over-Validation: {entries_with_flags}")
            output_lines.append(f"Total Phrase Hits: {total_phrase_hits}")
            output_lines.append(f"Over-Validation Rate: {rate:.1f}%")
            output_lines.append("Examples:")
            for ex in examples:
                output_lines.append(f"  Turn {ex['turn']} [{ex['field']}]: found {ex['matched']}")
                # print a snippet (up to 150 chars)
                snippet = ex['excerpt'][:150] + "..." if len(ex['excerpt']) > 150 else ex['excerpt']
                output_lines.append(f"    Excerpt: {snippet}")
            output_lines.append("-" * 40)
            
    output_text = "\n".join(output_lines)
    print(output_text)
    
    output_path = "docs/testing/stage6f_internal_overvalidation_baseline_output.txt"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_text)

if __name__ == "__main__":
    audit_overvalidation()
