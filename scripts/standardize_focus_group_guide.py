import os
import argparse
import json
import re
import uuid

# Import extraction logic
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_focus_group_transcript_text import extract_text

def parse_guide(text: str, filename: str, file_type: str, guide_id: str) -> tuple[dict, list, list]:
    sections = []
    warnings = []
    review_queue = []
    
    lines = text.split('\n')
    
    current_section = None
    section_index = 0
    
    # Naive parsing
    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        
        # Heading detection: all caps, or bold-like numbering e.g. "1. Introduction"
        is_heading = False
        if stripped.isupper() and len(stripped) > 5:
            is_heading = True
        elif re.match(r'^\d+\.\s+[A-Z]', stripped):
            is_heading = True
            
        if is_heading:
            if current_section:
                sections.append(current_section)
                
            current_section = {
                "section_index": section_index,
                "section_label": stripped,
                "section_phase": "unknown",
                "section_purpose": "",
                "scripted_question": "",
                "probes": [],
                "stimulus": None,
                "standardization_confidence": "low",
                "requires_review": True
            }
            section_index += 1
            
            # Map common phases
            lower_head = stripped.lower()
            if "intro" in lower_head or "welcome" in lower_head:
                current_section["section_phase"] = "intro"
            elif "close" in lower_head or "wrap" in lower_head:
                current_section["section_phase"] = "close"
            elif "main" in lower_head or "discussion" in lower_head:
                current_section["section_phase"] = "main"
        else:
            if not current_section:
                current_section = {
                    "section_index": section_index,
                    "section_label": "Unlabeled Opening",
                    "section_phase": "intro",
                    "section_purpose": "",
                    "scripted_question": "",
                    "probes": [],
                    "stimulus": None,
                    "standardization_confidence": "low",
                    "requires_review": True
                }
                section_index += 1
                
            # Naive probe detection
            if stripped.startswith("-") or stripped.startswith("•") or stripped.startswith("*"):
                current_section["probes"].append(stripped.lstrip("-•* "))
            else:
                if current_section["scripted_question"]:
                    current_section["scripted_question"] += "\n" + stripped
                else:
                    current_section["scripted_question"] = stripped

    if current_section:
        sections.append(current_section)
        
    for s in sections:
        if s["requires_review"]:
            review_queue.append({
                "issue_id": str(uuid.uuid4()),
                "baseline_id": guide_id,
                "issue_type": "unclear_guide_section",
                "excerpt": s["section_label"],
                "proposed_action": "Manually verify section boundaries and questions",
                "confidence": "low",
                "requires_human_review": True
            })
            
    guide = {
        "guide_id": guide_id,
        "source_type": "human_focus_group_guide",
        "source_file": filename,
        "original_file_type": file_type,
        "topic_domain": "unknown",
        "sections": sections,
        "standardization_warnings": warnings,
        "requires_human_review": len(review_queue) > 0
    }
    
    return guide, review_queue

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-base-dir", required=True)
    parser.add_argument("--baseline-id", default=None)
    args = parser.parse_args()
    
    filename = os.path.basename(args.input_file)
    guide_id = args.baseline_id if args.baseline_id else os.path.splitext(filename)[0]
    out_dir = os.path.join(args.output_base_dir, guide_id) if args.baseline_id else os.path.join(args.output_base_dir, "unmatched_guides", guide_id)
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Extracting guide: {filename}")
    text, meta = extract_text(args.input_file)
    
    guide, review_queue = parse_guide(text, filename, meta["file_type"], guide_id)
    
    with open(os.path.join(out_dir, "guide.json"), "w", encoding="utf-8") as f:
        json.dump(guide, f, indent=2)
        
    if review_queue:
        q_path = os.path.join(out_dir, "review_queue.json")
        existing_q = []
        if os.path.exists(q_path):
            with open(q_path, "r", encoding="utf-8") as f:
                existing_q = json.load(f)
        existing_q.extend(review_queue)
        with open(q_path, "w", encoding="utf-8") as f:
            json.dump(existing_q, f, indent=2)
            
if __name__ == "__main__":
    main()
