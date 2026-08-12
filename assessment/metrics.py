import re
import math
from typing import Dict, Any, List
from collections import Counter
from .schema import SessionArtifacts, TrackResult, MetricResult, Flag, EvidenceSpan, SpeakerStats
from .flags import create_flag, apply_track_status_from_flags

def compute_mechanical_integrity(artifacts: SessionArtifacts) -> TrackResult:
    track = TrackResult(track_id="mechanical_integrity")
    
    if artifacts.missing_required_files:
        track.flags.append(create_flag(
            "MISSING_REQUIRED_FILES", "critical", "mechanical_integrity",
            f"Missing required files: {', '.join(artifacts.missing_required_files)}"
        ))
        
    if artifacts.missing_optional_files:
        track.flags.append(create_flag(
            "MISSING_OPTIONAL_FILES", "info", "mechanical_integrity",
            f"Missing optional files: {', '.join(artifacts.missing_optional_files)}"
        ))
        
    if artifacts.load_errors:
        track.flags.append(create_flag(
            "LOAD_ERRORS", "critical", "mechanical_integrity",
            f"Load errors encountered: {'; '.join(artifacts.load_errors)}"
        ))
        
    if not artifacts.transcript:
        track.flags.append(create_flag(
            "NO_TRANSCRIPT", "critical", "mechanical_integrity",
            "Transcript is empty or missing."
        ))
        track.status = "FAIL"
        return track
        
    malformed_entries = []
    visible_count = 0
    mod_count = 0
    participant_count = 0
    
    for i, t in enumerate(artifacts.transcript):
        if not isinstance(t, dict):
            malformed_entries.append(i)
            continue
        if "speaker_id" not in t or "content" not in t or "turn" not in t:
            malformed_entries.append(i)
            continue
        if not t.get("content"):
            malformed_entries.append(i)
            continue
            
        visible_count += 1
        role = t.get("speaker_role")
        if role == "moderator" or t.get("speaker_id") == "MODERATOR":
            mod_count += 1
        elif role == "participant" or (not role and t.get("speaker_id", "").startswith("P")):
            participant_count += 1
            
    if malformed_entries:
        track.flags.append(create_flag(
            "MALFORMED_TRANSCRIPT_ENTRIES", "fail", "mechanical_integrity",
            f"{len(malformed_entries)} transcript entries are malformed or missing required fields."
        ))
        
    track.metrics["visible_utterance_count"] = MetricResult("visible_utterance_count", visible_count)
    track.metrics["transcript_moderator_count"] = MetricResult("transcript_moderator_count", mod_count)
    track.metrics["transcript_participant_count"] = MetricResult("transcript_participant_count", participant_count)
    
    md_mod_count = artifacts.run_metadata.get("selection_mode_counts", {}).get("moderator_intervention", 0)
    md_vol_count = artifacts.run_metadata.get("selection_mode_counts", {}).get("voluntary", 0)
    
    is_human_baseline = False
    if artifacts.transcript and artifacts.transcript[0].get("source_type") == "human_baseline_transcript":
        is_human_baseline = True
        
    if not is_human_baseline:
        if md_mod_count > 0 and mod_count != md_mod_count:
            track.flags.append(create_flag(
                "MODERATOR_COUNT_MISMATCH", "fail", "mechanical_integrity",
                f"Transcript moderator count ({mod_count}) != metadata intervention count ({md_mod_count})"
            ))
            
        if md_vol_count > 0 and participant_count != md_vol_count:
            track.flags.append(create_flag(
                "PARTICIPANT_COUNT_MISMATCH", "fail", "mechanical_integrity",
                f"Transcript participant count ({participant_count}) != metadata voluntary count ({md_vol_count})"
            ))
        
    trunc_count = artifacts.run_metadata.get("participant_response_truncation_count", 0)
    if artifacts.api_calls:
        for call in artifacts.api_calls:
            if call.get("response_truncated", False):
                trunc_count += 1
                
    if trunc_count > 0:
        track.flags.append(create_flag(
            "PARTICIPANT_TRUNCATION", "critical", "mechanical_integrity",
            f"Detected {trunc_count} truncated participant responses."
        ))
        
    stage_direction_pattern = re.compile(r'\*.*?\*|\[.*?\]')
    stage_direction_evidence = []
    
    for t in artifacts.transcript:
        content = t.get("content", "")
        if stage_direction_pattern.search(content):
            stage_direction_evidence.append(EvidenceSpan(
                run_id=artifacts.run_id, turn=t.get("turn"), speaker_id=t.get("speaker_id"),
                speaker_name=t.get("speaker_name"), excerpt=content, source_file="transcript.json"
            ))
            
    if stage_direction_evidence:
        if is_human_baseline:
            track.flags.append(create_flag(
                "STAGE_DIRECTIONS_DETECTED", "info", "mechanical_integrity",
                f"Found {len(stage_direction_evidence)} instances of transcription markers.",
                evidence=stage_direction_evidence[:5]
            ))
        else:
            track.flags.append(create_flag(
                "STAGE_DIRECTIONS_DETECTED", "warning", "mechanical_integrity",
                f"Found {len(stage_direction_evidence)} instances of possible stage directions or markdown.",
                evidence=stage_direction_evidence[:5]
            ))
        
    track.metrics["stage_direction_count"] = MetricResult("stage_direction_count", len(stage_direction_evidence))
    
    if is_human_baseline:
        unclear_word_marker_count = 0
        nonverbal_marker_count = 0
        redaction_marker_count = 0
        inaudible_marker_count = 0
        removed_identifier_marker_count = 0
        transcript_time_marker_count = 0
        transcription_artifact_marker_count = 0
        
        for t in artifacts.transcript:
            content = t.get("content", "")
            if "**" in content:
                unclear_word_marker_count += content.count("**")
            if re.search(r'\{(laughs|sighs|chuckles|pauses|clears throat.*?)\}', content, re.IGNORECASE):
                nonverbal_marker_count += len(re.findall(r'\{(laughs|sighs|chuckles|pauses|clears throat.*?)\}', content, re.IGNORECASE))
            if re.search(r'\+.*?\+', content):
                redaction_marker_count += len(re.findall(r'\+.*?\+', content))
            if "inaudible" in content.lower():
                inaudible_marker_count += content.lower().count("inaudible")
            if "removed" in content.lower():
                removed_identifier_marker_count += content.lower().count("removed")
            if re.search(r'\[\d{1,2}:\d{2}(:\d{2})?\]', content):
                transcript_time_marker_count += len(re.findall(r'\[\d{1,2}:\d{2}(:\d{2})?\]', content))
            if re.search(r'\[Professor\]|\[Moderator\]|\[Interviewer\]', content, re.IGNORECASE):
                transcription_artifact_marker_count += len(re.findall(r'\[Professor\]|\[Moderator\]|\[Interviewer\]', content, re.IGNORECASE))
                
        track.metrics["unclear_word_marker_count"] = MetricResult("unclear_word_marker_count", unclear_word_marker_count)
        track.metrics["nonverbal_marker_count"] = MetricResult("nonverbal_marker_count", nonverbal_marker_count)
        track.metrics["redaction_marker_count"] = MetricResult("redaction_marker_count", redaction_marker_count)
        track.metrics["inaudible_marker_count"] = MetricResult("inaudible_marker_count", inaudible_marker_count)
        track.metrics["removed_identifier_marker_count"] = MetricResult("removed_identifier_marker_count", removed_identifier_marker_count)
        track.metrics["transcript_time_marker_count"] = MetricResult("transcript_time_marker_count", transcript_time_marker_count)
        track.metrics["transcription_artifact_marker_count"] = MetricResult("transcription_artifact_marker_count", transcription_artifact_marker_count)
    
    return apply_track_status_from_flags(track)

def compute_process_metrics(artifacts: SessionArtifacts, speaker_stats: Dict[str, SpeakerStats]) -> TrackResult:
    track = TrackResult(track_id="process_and_participation")
    
    if not artifacts.transcript:
        track.status = "BLOCKED"
        return track
        
    is_human_baseline = False
    if artifacts.transcript and artifacts.transcript[0].get("source_type") == "human_baseline_transcript":
        is_human_baseline = True
        
    front_matter_word_count = 0
    back_matter_word_count = 0
    participant_count_from_metadata = 0
    moderator_labels = []
    
    if is_human_baseline:
        import os
        import json
        try:
            meta_path = os.path.join(artifacts.session_dir, "baseline_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    b_meta = json.load(f)
                    front_matter_word_count = b_meta.get("front_matter_word_count", 0)
                    back_matter_word_count = b_meta.get("back_matter_word_count", 0)
                    moderator_labels = b_meta.get("moderator_labels_detected", [])
        except Exception:
            pass
            
        try:
            pm_path = os.path.join(artifacts.session_dir, "participant_metadata.json")
            if os.path.exists(pm_path):
                with open(pm_path, "r", encoding="utf-8") as f:
                    pm = json.load(f)
                    participant_count_from_metadata = len(pm.get("participants", []))
        except Exception:
            pass

    participants = set()
    total_words = 0
    mod_words = 0
    participant_words = 0
    turn_lengths = []
    
    dialogue_turn_count = len(artifacts.transcript)
    mod_turns = 0
    part_turns = 0
    unattributed_part_turns = 0
    unknown_turns = 0
    unknown_words = 0
    
    consecutive_part = 0
    max_consecutive_part = 0
    consecutive_mod = 0
    max_consecutive_mod = 0
    last_speaker_type = None
    
    for t in artifacts.transcript:
        speaker = t.get("speaker_id")
        role = t.get("speaker_role")
        content = t.get("content", "")
        words = len(content.split())
        total_words += words
        
        if role == "moderator" or speaker == "MODERATOR":
            mod_words += words
            mod_turns += 1
            if last_speaker_type == "MODERATOR":
                consecutive_mod += 1
            else:
                consecutive_mod = 1
                consecutive_part = 0
            max_consecutive_mod = max(max_consecutive_mod, consecutive_mod)
            last_speaker_type = "MODERATOR"
        elif role == "participant" or (not role and speaker != "UNKNOWN_SPEAKER"):
            if speaker not in speaker_stats:
                speaker_stats[speaker] = SpeakerStats(speaker_id=speaker, speaker_name=t.get("speaker_name", speaker))
            
            p_stat = speaker_stats[speaker]
            p_stat.turn_count += 1
            p_stat.word_count += words
            if p_stat.first_turn_index is None:
                p_stat.first_turn_index = t.get("turn")
                
            participant_words += words
            turn_lengths.append(words)
            participants.add(speaker)
            part_turns += 1
            
            if last_speaker_type == "PARTICIPANT":
                consecutive_part += 1
            else:
                consecutive_part = 1
                consecutive_mod = 0
            max_consecutive_part = max(max_consecutive_part, consecutive_part)
            last_speaker_type = "PARTICIPANT"
        elif role == "unattributed_participant":
            unattributed_part_turns += 1
        else:
            unknown_turns += 1
            unknown_words += words
            
    track.metrics["participant_count"] = MetricResult("participant_count", len(participants))
    
    if len(participants) < 3:
        track.flags.append(create_flag("INSUFFICIENT_PARTICIPANTS", "fail", "process_and_participation", f"Expected at least 3 participants, found {len(participants)}"))
        track.status = "FAIL"
        return track
        
    for p in speaker_stats.values():
        if p.turn_count > 0:
            p.words_per_turn_avg = p.word_count / p.turn_count
            
    def gini(array):
        if not array: return 0.0
        array = sorted(array)
        n = len(array)
        coef_ = 2.0 / n
        const_ = (n + 1.0) / n
        weighted_sum = sum([(i+1)*yi for i, yi in enumerate(array)])
        return coef_ * weighted_sum / (sum(array) + 1e-8) - const_
        
    turn_counts = [p.turn_count for p in speaker_stats.values()]
    word_counts = [p.word_count for p in speaker_stats.values()]
    
    gini_turns = gini(turn_counts)
    gini_words = gini(word_counts)
    
    track.metrics["gini_turns"] = MetricResult("gini_turns", gini_turns)
    track.metrics["gini_words"] = MetricResult("gini_words", gini_words)
    track.metrics["moderator_word_share"] = MetricResult("moderator_word_share", mod_words / total_words if total_words > 0 else 0)
    track.metrics["max_consecutive_participant_turns"] = MetricResult("max_consecutive_participant_turns", max_consecutive_part)
    
    if is_human_baseline:
        track.metrics["dialogue_turn_count"] = MetricResult("dialogue_turn_count", dialogue_turn_count)
        track.metrics["front_matter_word_count"] = MetricResult("front_matter_word_count", front_matter_word_count)
        track.metrics["back_matter_word_count"] = MetricResult("back_matter_word_count", back_matter_word_count)
        track.metrics["unknown_speaker_word_share"] = MetricResult("unknown_speaker_word_share", unknown_words / total_words if total_words > 0 else 0.0)
        track.metrics["unattributed_participant_turn_count"] = MetricResult("unattributed_participant_turn_count", unattributed_part_turns)
        track.metrics["moderator_turn_count"] = MetricResult("moderator_turn_count", mod_turns)
        track.metrics["participant_turn_count"] = MetricResult("participant_turn_count", part_turns)
        track.metrics["participant_count_detected_from_dialogue"] = MetricResult("participant_count_detected_from_dialogue", len(participants))
        track.metrics["participant_count_detected_from_metadata"] = MetricResult("participant_count_detected_from_metadata", participant_count_from_metadata)
        track.metrics["moderator_labels_detected"] = MetricResult("moderator_labels_detected", list(moderator_labels))
    
    if len(turn_lengths) > 0:
        turn_lengths.sort()
        track.metrics["avg_participant_turn_words"] = MetricResult("avg_participant_turn_words", sum(turn_lengths) / len(turn_lengths))
        track.metrics["median_participant_turn_words"] = MetricResult("median_participant_turn_words", turn_lengths[len(turn_lengths)//2])
        track.metrics["max_participant_turn_words"] = MetricResult("max_participant_turn_words", turn_lengths[-1])
        track.metrics["min_participant_turn_words"] = MetricResult("min_participant_turn_words", turn_lengths[0])
    
    if gini_turns > 0.5:
        track.flags.append(create_flag("HIGH_PARTICIPATION_IMBALANCE", "warning", "process_and_participation", f"Gini coefficient for turns is high ({gini_turns:.2f}), indicating imbalance."))
    elif gini_turns < 0.05 and sum(turn_counts) > len(participants) * 3:
         track.flags.append(create_flag("SUSPICIOUSLY_PERFECT_BALANCE", "warning", "process_and_participation", f"Gini coefficient for turns is unusually low ({gini_turns:.2f}), indicating possible artificial round-robin."))
         
    if len(turn_lengths) < 10:
        for k in track.metrics:
            track.metrics[k].status = "INSUFFICIENT_SAMPLE"
            
    return apply_track_status_from_flags(track)

def compute_moderator_metrics(artifacts: SessionArtifacts) -> TrackResult:
    track = TrackResult(track_id="moderator_quality")
    
    is_human_baseline = False
    if artifacts.transcript and artifacts.transcript[0].get("source_type") == "human_baseline_transcript":
        is_human_baseline = True
        
    if is_human_baseline:
        track.metrics["internal_overvalidation_entries_total"] = MetricResult("internal_overvalidation_entries_total", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        track.metrics["internal_overvalidation_entries_with_hits"] = MetricResult("internal_overvalidation_entries_with_hits", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        track.metrics["internal_overvalidation_phrase_hits"] = MetricResult("internal_overvalidation_phrase_hits", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        track.metrics["internal_overvalidation_entry_rate"] = MetricResult("internal_overvalidation_entry_rate", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        track.metrics["internal_overvalidation_phrases_per_entry"] = MetricResult("internal_overvalidation_phrases_per_entry", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        track.metrics["strict_target_count"] = MetricResult("strict_target_count", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        track.metrics["strict_target_mismatch_count"] = MetricResult("strict_target_mismatch_count", 0, "NOT_APPLICABLE_HUMAN_BASELINE")
        
        visible_hits = 0
        visible_evidence = []
        participant_map = {u.get("speaker_id"): u.get("speaker_name", u.get("speaker_id")) for u in artifacts.transcript if u.get("speaker_role") != "moderator" and u.get("speaker_id") != "MODERATOR"}
        overvalidation_visible = [
            "powerful insight", "intellectual courage", "cuts through everything", "really important",
            "significant shift", "great point", "excellent point", "very insightful"
        ]
        
        for turn_index, u in enumerate(artifacts.transcript):
            if u.get("speaker_role") == "moderator" or u.get("speaker_id") == "MODERATOR":
                utterance_text = u.get("content", "")
                utterance_lower = utterance_text.lower()
                for phrase in overvalidation_visible:
                    if phrase in utterance_lower:
                        visible_hits += 1
                        visible_evidence.append(EvidenceSpan(artifacts.run_id, turn_index, "MODERATOR", "Moderator", utterance_text, "transcript.json"))
                        break
        
        track.metrics["visible_overvalidation_hits"] = MetricResult("visible_overvalidation_hits", visible_hits)
        return apply_track_status_from_flags(track)
        
    overvalidation_internal = [
        "excellent", "rich data", "powerful", "remarkable", "sophisticated", "vulnerable", 
        "honest data", "exactly what the research needs", "intellectual honesty", 
        "emotional richness", "analytically rich", "valuable depth", "high-quality material"
    ]
    
    overvalidation_visible = [
        "powerful insight", "intellectual courage", "cuts through everything", "really important",
        "significant shift", "great point", "excellent point", "very insightful"
    ]
    
    internal_entries_total = 0
    internal_entries_with_hits = 0
    internal_phrase_hits = 0
    internal_evidence = []
    visible_hits = 0
    visible_evidence = []
    
    actions = {}
    strict_targets = 0
    strict_honored = 0
    strict_mismatch = 0
    soft_group = 0
    broad_group = 0
    section_transitions = 0
    ambiguous = 0
    
    participant_map = {u.get("speaker_id"): u.get("speaker_name", u.get("speaker_id")) for u in artifacts.transcript if u.get("speaker_role") != "moderator" and u.get("speaker_id") != "MODERATOR"}
    
    for entry in artifacts.moderator_log:
        action = entry.get("action", "unknown")
        actions[action] = actions.get(action, 0) + 1
        
        # Build real reasoning string
        reasoning_fields = []
        for field in ["situation_assessment", "brief_justification", "justification"]:
            if field in entry and entry[field]:
                reasoning_fields.append(str(entry[field]))
        if "queued_next_action" in entry and isinstance(entry["queued_next_action"], dict):
            if "rationale" in entry["queued_next_action"] and entry["queued_next_action"]["rationale"]:
                reasoning_fields.append(str(entry["queued_next_action"]["rationale"]))
                
        reasoning = " ".join(reasoning_fields).lower()
        if reasoning:
            internal_entries_total += 1
            hits_in_entry = 0
            for phrase in overvalidation_internal:
                hits_in_entry += reasoning.count(phrase)
                
            if hits_in_entry > 0:
                internal_entries_with_hits += 1
                internal_phrase_hits += hits_in_entry
                internal_evidence.append(EvidenceSpan(artifacts.run_id, entry.get("turn"), "MODERATOR", "Moderator", reasoning[:200] + "...", "moderator_log.json"))
                
        target = entry.get("target")
        turn_index = entry.get("turn")
        
        mod_utt = None
        mod_utt_index = -1
        for i, u in enumerate(artifacts.transcript):
            if u.get("turn") == turn_index and (u.get("speaker_role") == "moderator" or u.get("speaker_id") == "MODERATOR"):
                mod_utt = u
                mod_utt_index = i
                break
                
        if mod_utt:
            utterance_text = mod_utt.get("content", "")
            utterance_lower = utterance_text.lower()
            
            for phrase in overvalidation_visible:
                if phrase in utterance_lower:
                    visible_hits += 1
                    visible_evidence.append(EvidenceSpan(artifacts.run_id, turn_index, "MODERATOR", "Moderator", utterance_text, "transcript.json"))
                    break
            
            names_in_utterance = [p_name for p_name in participant_map.values() if p_name in utterance_text]
            
            strict_actions = ["direct_probe", "reactivate_silent", "invite_to_speak"]
            group_actions = ["redirect_to_group", "ask_initial_to_group", "invite_dissent", "synthesize_and_challenge"]
            section_acts = ["section_transition"]
            
            classification = "UNKNOWN"
            expected_speaker_id = None
            
            if action in strict_actions and target in participant_map:
                classification = "STRICT_TARGET"
                expected_speaker_id = target
            elif target == "group" and len(names_in_utterance) > 0:
                classification = "SOFT_GROUP_WITH_NAMES"
            elif target == "group" and len(names_in_utterance) == 0:
                if action in group_actions:
                    classification = "BROAD_GROUP_REDIRECT"
                elif action in section_acts:
                    classification = "OPENING_OR_SECTION_TRANSITION"
                else:
                    classification = "BROAD_GROUP_REDIRECT"
            elif action in section_acts or action == "ask_initial_to_group":
                classification = "OPENING_OR_SECTION_TRANSITION"
            else:
                classification = "AMBIGUOUS"
                
            if classification == "STRICT_TARGET":
                strict_targets += 1
                next_part_utt = None
                for u in artifacts.transcript[mod_utt_index+1:]:
                    if u.get("speaker_role") != "moderator" and u.get("speaker_id") != "MODERATOR":
                        next_part_utt = u
                        break
                if next_part_utt:
                    if next_part_utt.get("speaker_id") == expected_speaker_id:
                        strict_honored += 1
                    else:
                        strict_mismatch += 1
            elif classification == "SOFT_GROUP_WITH_NAMES":
                soft_group += 1
            elif classification == "BROAD_GROUP_REDIRECT":
                broad_group += 1
            elif classification == "OPENING_OR_SECTION_TRANSITION":
                section_transitions += 1
            else:
                ambiguous += 1
                
    track.metrics["internal_overvalidation_entries_total"] = MetricResult("internal_overvalidation_entries_total", internal_entries_total)
    track.metrics["internal_overvalidation_entries_with_hits"] = MetricResult("internal_overvalidation_entries_with_hits", internal_entries_with_hits)
    track.metrics["internal_overvalidation_phrase_hits"] = MetricResult("internal_overvalidation_phrase_hits", internal_phrase_hits)
    entry_rate = (internal_entries_with_hits / internal_entries_total) if internal_entries_total > 0 else 0
    phrases_per_entry = (internal_phrase_hits / internal_entries_total) if internal_entries_total > 0 else 0
    track.metrics["internal_overvalidation_entry_rate"] = MetricResult("internal_overvalidation_entry_rate", entry_rate)
    track.metrics["internal_overvalidation_phrases_per_entry"] = MetricResult("internal_overvalidation_phrases_per_entry", phrases_per_entry)
    
    track.metrics["visible_overvalidation_hits"] = MetricResult("visible_overvalidation_hits", visible_hits)
    track.metrics["strict_target_count"] = MetricResult("strict_target_count", strict_targets)
    track.metrics["strict_target_mismatch_count"] = MetricResult("strict_target_mismatch_count", strict_mismatch)
    
    for act, count in actions.items():
        track.metrics[f"action_{act}"] = MetricResult(f"action_{act}", count)
        
    if strict_mismatch > 0:
        track.flags.append(create_flag("TARGETING_MISMATCH", "warning", "moderator_quality", f"Found {strict_mismatch} true targeting mismatches."))
        
    if entry_rate > 0.2:
        track.flags.append(create_flag("HIGH_INTERNAL_OVERVALIDATION", "warning", "moderator_quality", f"High internal over-validation detected ({internal_entries_with_hits} entries with hits, rate {entry_rate:.2f}, total {internal_phrase_hits} phrases).", evidence=internal_evidence[:3]))
        
    return apply_track_status_from_flags(track)

def compute_topic_metrics(artifacts: SessionArtifacts, topic: str = "grocery_delivery", topic_terms: List[str] = None) -> TrackResult:
    track = TrackResult(track_id="topic_tethering")
    
    if topic_terms is not None:
        topic_dict = topic_terms
    elif topic == "grocery_delivery":
        topic_dict = ["tesco", "ocado", "sainsbury", "deliveroo", "grocery", "groceries", "delivery", "substitution", "substitutions", "markup", "fee", "slot", "app", "order", "basket", "fresh produce", "milk", "mince", "nappies", "supermarket"]
    else:
        topic_dict = []
        
    concrete_regex = re.compile(r'(£|\$|\d+\s*pounds?|quid|percent|\d+|tuesday|monday|wednesday|thursday|friday|saturday|sunday|last week|morning|evening|hour|last time|i ordered|i went|it arrived)')
    abstract_regex = re.compile(r'\b(system|society|structure|people like us|everyone|inevitable|capitalism|privilege|complicity|responsibility)\b', re.IGNORECASE)
    
    total_concrete = 0
    total_abstract = 0
    topic_refs = 0
    abstract_only_turns = 0
    
    for t in artifacts.transcript:
        if t.get("speaker_role") == "moderator" or t.get("speaker_id") == "MODERATOR":
            continue
            
        content = t.get("content", "").lower()
        
        c_matches = len(concrete_regex.findall(content))
        a_matches = len(abstract_regex.findall(content))
        
        total_concrete += c_matches
        total_abstract += a_matches
        
        if topic_dict and any(term in content for term in topic_dict):
            topic_refs += 1
            
        if a_matches > 0 and c_matches == 0:
            abstract_only_turns += 1
            
    track.metrics["concrete_markers"] = MetricResult("concrete_markers", total_concrete)
    track.metrics["abstract_markers"] = MetricResult("abstract_markers", total_abstract)
    track.metrics["topic_terms_used_count"] = MetricResult("topic_terms_used_count", topic_refs)
    track.metrics["topic_dictionary_version"] = MetricResult("topic_dictionary_version", "custom" if topic_terms else "1.0")
    track.metrics["abstract_only_turns"] = MetricResult("abstract_only_turns", abstract_only_turns)
    
    if abstract_only_turns > 5:
        track.flags.append(create_flag("HIGH_ABSTRACT_ONLY_TURNS", "warning", "topic_tethering", f"Found {abstract_only_turns} abstract-only participant turns."))
        
    return apply_track_status_from_flags(track)

def compute_distinctiveness_metrics(artifacts: SessionArtifacts, speaker_stats: Dict[str, SpeakerStats]) -> TrackResult:
    track = TrackResult(track_id="participant_distinctiveness")
    
    repair_regex = re.compile(r'\b(i mean|sorry|wait|let me|actually no|i should say)\b', re.IGNORECASE)
    hedge_regex = re.compile(r'\b(probably|maybe|might|sort of|kind of|i guess|perhaps|possibly)\b', re.IGNORECASE)
    first_person_regex = re.compile(r'\b(i|me|my|mine|we|us|our|ours)\b', re.IGNORECASE)
    certainty_regex = re.compile(r'\b(definitely|absolutely|always|never|certainly|exactly)\b', re.IGNORECASE)
    func_regex = re.compile(r'\b(the|a|an|and|but|or|for|nor|on|at|to|from|by|in|with)\b', re.IGNORECASE)
    
    total_repairs = 0
    total_hedges = 0
    total_certainty = 0
    
    participant_turns = {}
    for t in artifacts.transcript:
        spk = t.get("speaker_id")
        role = t.get("speaker_role")
        if role == "moderator" or spk == "MODERATOR": continue
        if role and role != "participant": continue
        if spk not in participant_turns:
            participant_turns[spk] = []
        participant_turns[spk].append(t.get("content", ""))
        
    lexical_diversities = []
    avg_turn_lengths = []
    first_person_rates = []
    hedging_rates = []
    repair_rates = []
        
    for p_id, turns in participant_turns.items():
        all_text = " ".join(turns)
        words = [w.lower() for w in re.findall(r'\w+', all_text)]
        word_count = len(words)
        
        sentences = [len(s.split()) for turn in turns for s in turn.split('.') if s.strip()]
        avg_sen_len = sum(sentences)/len(sentences) if sentences else 0
        var_sen_len = sum((x - avg_sen_len)**2 for x in sentences)/len(sentences) if sentences else 0
        avg_turn_length = sum(len(t.split()) for t in turns)/len(turns) if turns else 0
        
        unique_words = len(set(words))
        lex_div = unique_words / word_count if word_count > 0 else 0
        
        p_repairs = sum(1 for turn in turns if repair_regex.search(turn))
        p_hedges = sum(1 for turn in turns if hedge_regex.search(turn))
        p_certains = sum(1 for turn in turns if certainty_regex.search(turn))
        
        p_repair_rate = p_repairs / len(turns) if turns else 0
        p_hedge_rate = p_hedges / len(turns) if turns else 0
        p_certainty_rate = p_certains / len(turns) if turns else 0
        
        p_first_person = len(first_person_regex.findall(all_text))
        p_fp_rate = p_first_person / word_count if word_count > 0 else 0
        
        p_funcs = len(func_regex.findall(all_text))
        p_func_rate = p_funcs / word_count if word_count > 0 else 0
        
        if p_id in speaker_stats:
            speaker_stats[p_id].lexical_diversity = lex_div
            speaker_stats[p_id].first_person_rate = p_fp_rate
            speaker_stats[p_id].hedging_rate = p_hedge_rate
            speaker_stats[p_id].certainty_rate = p_certainty_rate
            
        total_repairs += p_repairs
        total_hedges += p_hedges
        total_certainty += p_certains
        
        lexical_diversities.append(lex_div)
        avg_turn_lengths.append(avg_turn_length)
        first_person_rates.append(p_fp_rate)
        hedging_rates.append(p_hedge_rate)
        repair_rates.append(p_repair_rate)
        
        track.metrics[f"p_{p_id}_lexical_diversity"] = MetricResult(f"p_{p_id}_lexical_diversity", lex_div)
        track.metrics[f"p_{p_id}_first_person_rate"] = MetricResult(f"p_{p_id}_first_person_rate", p_fp_rate)
        track.metrics[f"p_{p_id}_hedging_rate"] = MetricResult(f"p_{p_id}_hedging_rate", p_hedge_rate)
        track.metrics[f"p_{p_id}_certainty_rate"] = MetricResult(f"p_{p_id}_certainty_rate", p_certainty_rate)
        track.metrics[f"p_{p_id}_repair_rate"] = MetricResult(f"p_{p_id}_repair_rate", p_repair_rate)
        track.metrics[f"p_{p_id}_avg_sen_len"] = MetricResult(f"p_{p_id}_avg_sen_len", avg_sen_len)
        track.metrics[f"p_{p_id}_var_sen_len"] = MetricResult(f"p_{p_id}_var_sen_len", var_sen_len)
        track.metrics[f"p_{p_id}_avg_turn_length"] = MetricResult(f"p_{p_id}_avg_turn_length", avg_turn_length)
        track.metrics[f"p_{p_id}_function_word_rate_basic"] = MetricResult(f"p_{p_id}_function_word_rate_basic", p_func_rate)
        
    def calc_range(arr):
        return max(arr) - min(arr) if arr else 0.0

    track.metrics["participant_lexical_diversity_range"] = MetricResult("participant_lexical_diversity_range", calc_range(lexical_diversities))
    track.metrics["participant_avg_turn_length_range"] = MetricResult("participant_avg_turn_length_range", calc_range(avg_turn_lengths))
    track.metrics["participant_first_person_rate_range"] = MetricResult("participant_first_person_rate_range", calc_range(first_person_rates))
    track.metrics["participant_hedging_rate_range"] = MetricResult("participant_hedging_rate_range", calc_range(hedging_rates))
    track.metrics["participant_repair_rate_range"] = MetricResult("participant_repair_rate_range", calc_range(repair_rates))
            
    if total_repairs == 0 and len(participant_turns) > 0:
        track.flags.append(create_flag("ZERO_REPAIR_RATE", "warning", "participant_distinctiveness", "No repair/self-correction markers found across transcript (possible artificial smoothness)."))
        
    track.metrics["total_repairs"] = MetricResult("total_repairs", total_repairs)
    track.metrics["total_hedges"] = MetricResult("total_hedges", total_hedges)
    track.metrics["total_certainty"] = MetricResult("total_certainty", total_certainty)
    
    parts_with_turns = len([p for p, turns in participant_turns.items() if len(turns) >= 5])
    if len(participant_turns) < 3 or parts_with_turns < 3:
         track.metrics["speaker_classification_accuracy"] = MetricResult("speaker_classification_accuracy", None, "INSUFFICIENT_SAMPLE")
    else:
         track.metrics["speaker_classification_accuracy"] = MetricResult("speaker_classification_accuracy", 0, "NOT_IMPLEMENTED")
         
    return apply_track_status_from_flags(track)

def compute_research_design_metrics(artifacts: SessionArtifacts) -> TrackResult:
    track = TrackResult(track_id="research_design_coverage")
    
    is_human_baseline = False
    if artifacts.transcript and artifacts.transcript[0].get("source_type") == "human_baseline_transcript":
        is_human_baseline = True
        
    ss = artifacts.session_state_final
    if not ss and is_human_baseline:
        track.metrics["sections_total"] = MetricResult("sections_total", 0, "NOT_APPLICABLE_NO_GUIDE")
        track.metrics["sections_completed"] = MetricResult("sections_completed", 0, "NOT_APPLICABLE_NO_GUIDE")
        track.metrics["section_coverage_rate"] = MetricResult("section_coverage_rate", 0, "NOT_APPLICABLE_NO_GUIDE")
        return apply_track_status_from_flags(track)
        
    if not ss:
        track.status = "BLOCKED"
        return track
        
    guide = ss.get("discussion_guide", [])
    sections_total = len(guide)
    
    sections_completed = 0
    skipped_sections = 0
    for section in guide:
        if section.get("completed", False):
            sections_completed += 1
        else:
            skipped_sections += 1
            
    current_idx = ss.get("current_section_index", 0)
    closing_reached = ss.get("completed", False)
    
    intro_probes = 0
    main_probes = 0
    section_transitions = 0
    
    for entry in artifacts.moderator_log:
        if entry.get("action") == "section_transition":
            section_transitions += 1
        elif entry.get("action") == "direct_probe":
            if entry.get("turn", 0) < 5:
                intro_probes += 1
            else:
                main_probes += 1
    
    track.metrics["sections_total"] = MetricResult("sections_total", sections_total)
    track.metrics["sections_completed"] = MetricResult("sections_completed", sections_completed)
    track.metrics["skipped_sections"] = MetricResult("skipped_sections", skipped_sections)
    track.metrics["current_section_at_end"] = MetricResult("current_section_at_end", current_idx)
    track.metrics["closing_reached"] = MetricResult("closing_reached", closing_reached)
    track.metrics["section_transition_count"] = MetricResult("section_transition_count", section_transitions)
    track.metrics["intro_probe_count"] = MetricResult("intro_probe_count", intro_probes)
    track.metrics["main_topic_probe_count"] = MetricResult("main_topic_probe_count", main_probes)
    
    if sections_total > 0:
        coverage = sections_completed / sections_total
        track.metrics["section_coverage_rate"] = MetricResult("section_coverage_rate", coverage)
        if coverage < 0.5:
             track.flags.append(create_flag("LOW_SECTION_COVERAGE", "info", "research_design_coverage", f"Only completed {sections_completed}/{sections_total} sections."))
             
    return apply_track_status_from_flags(track)
