import os
import json
import re

def audit_baselines():
    standardized_dir = "data/human_baseline/standardized"
    results = {}
    
    # Matching terms for leakage detection
    front_matter_leakage_regex = re.compile(
        r"READ ME|copyright|recommended citation|reporting conventions|"
        r"Date of the interview|Location|Participants|Alias \| Sex|"
        r"PHIND employee group|PHIND employer focus group|"
        r"Transcription commenced|Transcription starts|Transcription begins",
        re.IGNORECASE
    )
    
    # Section headings to check for leakage
    section_headings = [
        "Your Voting Story", 
        "Your Voting Outcome Story", 
        "Turnout Impressions", 
        "Song of the Election", 
        "Impressions of Results by Party"
    ]
    
    moderator_initials = {"I", "AN", "SM", "CF"}
    
    if not os.path.exists(standardized_dir):
        print(f"Error: Standardized directory {standardized_dir} does not exist.")
        return
        
    for baseline in os.listdir(standardized_dir):
        baseline_path = os.path.join(standardized_dir, baseline)
        if not os.path.isdir(baseline_path):
            continue
            
        transcript_path = os.path.join(baseline_path, "transcript.json")
        metadata_path = os.path.join(baseline_path, "baseline_metadata.json")
        guide_path = os.path.join(baseline_path, "guide.json")
        review_path = os.path.join(baseline_path, "review_queue.json")
        warnings_path = os.path.join(baseline_path, "standardization_warnings.json")
        
        if not os.path.exists(transcript_path):
            continue
            
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = json.load(f)
            
        # Initialize checkers
        mod_label_errors = []
        front_matter_leakage = []
        back_matter_leakage = []
        unknown_speaker_turns = []
        section_heading_leakage = []
        
        participant_names = set()
        participant_ids = set()
        moderator_detected_in_turns = False
        
        total_words = 0
        unknown_words = 0
        first_unknown_excerpt = None
        unknown_before_dialogue = False
        dialogue_started = False
        
        for i, turn in enumerate(transcript):
            speaker_name = turn.get("speaker_name", "")
            speaker_id = turn.get("speaker_id", "")
            speaker_role = turn.get("speaker_role", "")
            content = turn.get("content", "")
            words = len(content.split())
            total_words += words
            
            # Identify if dialogue has actually started (i.e. first turn with actual speaker)
            if speaker_id != "UNKNOWN_SPEAKER" and not dialogue_started:
                dialogue_started = True
            
            # 1. Moderator label errors
            if speaker_name in moderator_initials:
                if speaker_role != "moderator":
                    mod_label_errors.append(
                        f"Turn {i}: '{speaker_name}' has role '{speaker_role}' instead of 'moderator'"
                    )
                if speaker_id.startswith("P") or speaker_id == "UNATTRIBUTED_PARTICIPANT":
                    mod_label_errors.append(
                        f"Turn {i}: '{speaker_name}' has speaker_id '{speaker_id}' (participant mapping)"
                    )
            
            if speaker_role == "moderator" or speaker_id.startswith("MODERATOR"):
                moderator_detected_in_turns = True
                
            # 2. Front matter leakage in content
            if front_matter_leakage_regex.search(content):
                front_matter_leakage.append(f"Turn {i} ({speaker_name}): {content[:80]}")
            if re.match(r"^\d+$", content.strip()):
                front_matter_leakage.append(f"Turn {i} ({speaker_name}): Page-number content '{content.strip()}'")
                
            # 3. Back matter leakage
            if "End of transcript" in content:
                back_matter_leakage.append(f"Turn {i} ({speaker_name}): {content[:80]}")
                
            # 4. Unknown speaker issues
            if speaker_id == "UNKNOWN_SPEAKER":
                unknown_speaker_turns.append(i)
                unknown_words += words
                if first_unknown_excerpt is None:
                    first_unknown_excerpt = content[:100]
                if not dialogue_started:
                    unknown_before_dialogue = True
                    
            # 5. Section heading leakage
            for sh in section_headings:
                if sh.lower() in content.lower() and len(content) < len(sh) + 20:
                    section_heading_leakage.append(f"Turn {i} ({speaker_name}): Section heading '{content.strip()}'")
            # PHIND question blocks check
            if ("question" in content.lower() or "thinking now about" in content.lower()) and len(content) < 80 and not ":" in content:
                section_heading_leakage.append(f"Turn {i} ({speaker_name}): Possible heading '{content.strip()}'")
                
            # 6. Participant mapping
            if speaker_role == "participant" or (not speaker_role and speaker_id.startswith("P")):
                if speaker_name not in moderator_initials and speaker_name != "Participant":
                    participant_names.add(speaker_name)
                    participant_ids.add(speaker_id)
                    
            if speaker_name == "Participant" and speaker_role == "participant":
                mod_label_errors.append(f"Turn {i}: Generic Participant counted as stable participant")
                
            if speaker_name in moderator_initials and (speaker_role == "participant" or speaker_id.startswith("P")):
                mod_label_errors.append(f"Turn {i}: Moderator initial '{speaker_name}' counted as participant")
                
        # Check text for absence of moderator turns if known labels appear
        txt_path = os.path.join(baseline_path, "transcript.txt")
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            for init in moderator_initials:
                if f"\n{init}:" in raw_text or f"\n{init}::" in raw_text:
                    # Known moderator label in raw text, check if we have turns
                    if not moderator_detected_in_turns:
                        mod_label_errors.append(f"Raw text has '{init}:', but no moderator turns detected in transcript.json")

        unknown_share = (unknown_words / total_words) if total_words > 0 else 0.0
        
        # Read review queue & warnings counts if available
        review_queue_count = 0
        if os.path.exists(review_path):
            with open(review_path, "r", encoding="utf-8") as f:
                rq = json.load(f)
                review_queue_count = len(rq)
                
        warnings_count = 0
        if os.path.exists(warnings_path):
            with open(warnings_path, "r", encoding="utf-8") as f:
                wn = json.load(f)
                warnings_count = len(wn)
                
        results[baseline] = {
            "moderator_label_errors": mod_label_errors,
            "front_matter_leakage": front_matter_leakage,
            "back_matter_leakage": back_matter_leakage,
            "unknown_speaker_issues": {
                "turn_count": len(unknown_speaker_turns),
                "word_count": unknown_words,
                "word_share": unknown_share,
                "first_excerpt": first_unknown_excerpt,
                "appears_before_dialogue": unknown_before_dialogue
            },
            "section_heading_leakage": section_heading_leakage,
            "participant_mapping_issues": {
                "participant_count_detected": len(participant_names),
                "detected_speaker_names": list(participant_names),
                "detected_speaker_ids": list(participant_ids)
            },
            "guide_available": os.path.exists(guide_path),
            "review_queue_count": review_queue_count,
            "warnings_count": warnings_count
        }
        
    # Write JSON output
    os.makedirs("docs/testing/human_baseline_standardization", exist_ok=True)
    with open("docs/testing/human_baseline_standardization/stage7c01_standardization_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    # Generate Markdown report
    md_lines = [
        "# Stage 7C.0.1 Standardization Audit Results\n",
        f"Audited {len(results)} baselines under `data/human_baseline/standardized/`.\n"
    ]
    
    for baseline, res in results.items():
        md_lines.append(f"## Baseline: `{baseline}`")
        md_lines.append(f"- **Guide Available**: {'Yes' if res['guide_available'] else 'No'}")
        md_lines.append(f"- **Review Queue Items**: {res['review_queue_count']}")
        md_lines.append(f"- **Warnings Count**: {res['warnings_count']}")
        md_lines.append(f"- **Participant Count**: {res['participant_mapping_issues']['participant_count_detected']}")
        md_lines.append(f"- **Detected Speaker Names**: {res['participant_mapping_issues']['detected_speaker_names']}")
        
        md_lines.append("- **Moderator/Facilitator Label Errors**: " + (str(len(res['moderator_label_errors'])) if res['moderator_label_errors'] else "0"))
        for err in res['moderator_label_errors']:
            md_lines.append(f"  - {err}")
            
        md_lines.append("- **Front Matter Leakage**: " + (str(len(res['front_matter_leakage'])) if res['front_matter_leakage'] else "0"))
        for leak in res['front_matter_leakage']:
            md_lines.append(f"  - {leak}")
            
        md_lines.append("- **Back Matter Leakage**: " + (str(len(res['back_matter_leakage'])) if res['back_matter_leakage'] else "0"))
        for leak in res['back_matter_leakage']:
            md_lines.append(f"  - {leak}")
            
        md_lines.append("- **Section Heading Leakage**: " + (str(len(res['section_heading_leakage'])) if res['section_heading_leakage'] else "0"))
        for leak in res['section_heading_leakage']:
            md_lines.append(f"  - {leak}")
            
        unknown = res['unknown_speaker_issues']
        md_lines.append("- **Unknown Speaker Issues**:")
        md_lines.append(f"  - Turn count: {unknown['turn_count']}")
        md_lines.append(f"  - Word count: {unknown['word_count']}")
        md_lines.append(f"  - Word share: {unknown['word_share']:.4f}")
        md_lines.append(f"  - Appears before dialogue: {unknown['appears_before_dialogue']}")
        if unknown['first_excerpt']:
            md_lines.append(f"  - First excerpt: `{unknown['first_excerpt']}`")
        md_lines.append("")
        
    with open("docs/testing/human_baseline_standardization/STAGE7C01_STANDARDIZATION_AUDIT_RESULTS.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    print("Audit complete. Results saved to docs/testing/human_baseline_standardization/")

if __name__ == "__main__":
    audit_baselines()
