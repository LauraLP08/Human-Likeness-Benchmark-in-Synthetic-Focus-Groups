"""
Human focus group transcript standardizer — claude_v1 pipeline.

Parses extracted .txt transcript files into structured JSON turn arrays,
separating front matter, back matter, section headings, and participant
metadata.  Writes to whatever --output-base-dir is supplied (call this
script via process_human_baselines_claude_v1.py for the v1 run).

Key design rules
----------------
* Do NOT force human transcripts into the synthetic session schema.
* Do NOT create moderator_log.json / run_metadata.json / session_state_final.json.
* Do NOT invent participant profiles or guide content.
* canonical_speaker_id is present on every turn.
* Time expressions (3:00, 10:00, to 4:00, 12:30) must not become speakers.
* All 9 QESB section headings (plus combined variants) are detected.
* PHIND front-matter lines (page headers, group labels, transcription timestamps)
  are excluded from transcript.json.
* Generic "Participant:" maps to unattributed_participant and does NOT inflate
  participant_count_detected.
* standardization_warnings.json and review_queue.json are always written
  (as empty arrays when there are no issues).
"""

import os
import argparse
import json
import re
import uuid


# ---------------------------------------------------------------------------
# QESB section heading set (all known variants, lower-cased for lookup)
# ---------------------------------------------------------------------------
_QESB_HEADING_EXACT = {
    "your voting story",
    "your voting outcome story",
    "your voting story and your voting outcome story",
    "turnout impressions",
    "song of the election",
    "impressions of results by party",
    "one word to describe the election",
    "standout moments from the campaign",
    "what's next for the parties",
    "whats next for the parties",          # apostrophe-free variant
    "advice for parties",
}


def _normalise_for_heading(s: str) -> str:
    """Normalise heading text for lookup in _QESB_HEADING_EXACT.

    Handles:
    - Trailing '?' (some transcripts append it to heading lines)
    - cp1252 mojibake sequences for curly apostrophes produced when UTF-8
      bytes are mis-decoded as Windows-1252 (e.g. â€™ for U+2019 ')
    - Standard curly quotes / apostrophes
    """
    s = s.strip().lower()
    s = s.rstrip("?").strip()
    # â€™ = UTF-8 bytes E2 80 99 (RIGHT SINGLE QUOTATION MARK) mis-decoded as cp1252
    s = s.replace("â€™", "")
    # â€˜ = UTF-8 bytes E2 80 98 (LEFT SINGLE QUOTATION MARK) mis-decoded as cp1252
    s = s.replace("â€˜", "")
    # Standard apostrophes and curly single quotes
    s = re.sub(r"['‘’′]", "", s)
    return s


def _is_qesb_heading(stripped: str) -> bool:
    return _normalise_for_heading(stripped) in _QESB_HEADING_EXACT


def _is_time_expression(name: str) -> bool:
    """Return True if *name* looks like a clock time or time prefix — not a speaker.

    Prevents e.g. '3' (split from '3:00'), '10', 'to 4', 'to 10' from being
    treated as speaker names.
    """
    s = name.strip().lower()
    if re.match(r"^\d{1,2}$", s):
        return True
    if re.match(r"^to\s+\d", s):
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_transcript(
    text: str,
    source_file: str,
    file_type: str,
    baseline_id: str,
) -> tuple:
    """Parse extracted transcript text into structured artefacts.

    Returns
    -------
    transcript : list[dict]
        Spoken dialogue turns only.
    warnings : list[dict]
    review_queue : list[dict]
    front_matter : str
    section_markers : list[dict]
    back_matter : str
    participant_metadata : dict
    """
    transcript: list[dict] = []
    warnings: list[dict] = []
    review_queue: list[dict] = []

    front_matter_lines: list[str] = []
    back_matter_lines: list[str] = []
    section_markers: list[dict] = []
    participant_metadata: dict = {
        "participants": [],
        "dialogue_start_line": -1,
        "dialogue_end_line": -1,
    }

    # ------------------------------------------------------------------
    # Dataset detection
    # ------------------------------------------------------------------
    bl_lower = baseline_id.lower()
    sf_lower = source_file.lower()
    text_lower = text[:5000].lower()  # check only header region for speed

    is_qesb = (
        "qesb" in bl_lower
        or "qesb" in sf_lower
        or "qualitative election study" in text_lower
        or bool(re.search(r"^(I|Interviewer):", text, re.M))
    )
    is_phind = (
        "work at home" in bl_lower
        or "work at home" in sf_lower
        or "phind" in text_lower
        or "employee group" in bl_lower
        or "employer group" in bl_lower
        or "employee group" in sf_lower
        or "employer group" in sf_lower
        or bool(re.search(r"^(AN|SM|CF):", text, re.M))
    )

    lines = text.split("\n")

    participant_map: dict[str, str] = {}
    next_p_idx = 1
    used_p_indices: set[int] = set()

    # ------------------------------------------------------------------
    # Pre-parse QESB participant table
    # ------------------------------------------------------------------
    if is_qesb:
        in_table = False
        headers: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            if "Alias | Sex" in stripped or "Alias|Sex" in stripped:
                in_table = True
                headers = [h.strip() for h in stripped.split("|")]
                continue
            if in_table:
                if not stripped or "|" not in stripped:
                    if stripped:
                        in_table = False
                    # empty lines keep the table "open" — do not break early
                    continue
                parts = [p.strip() for p in stripped.split("|")]
                alias = parts[0]
                if alias and alias.lower() not in ("alias", ""):
                    p_id = f"P{next_p_idx}"
                    participant_map[alias] = p_id
                    used_p_indices.add(next_p_idx)
                    next_p_idx += 1

                    meta_fields: dict = {}
                    for idx, val in enumerate(parts[1:]):
                        if idx + 1 < len(headers):
                            meta_fields[headers[idx + 1]] = val

                    participant_metadata["participants"].append({
                        "speaker_id": p_id,
                        "speaker_name": alias,
                        "source_alias": alias,
                        "metadata_fields": meta_fields,
                        "requires_review": False,
                    })

    # ------------------------------------------------------------------
    # Allowed-speaker sets (seeded with known names; PHIND speakers are
    # discovered dynamically from first-occurrence labels)
    # ------------------------------------------------------------------
    phind_allowed_names: set[str] = {
        # facilitators / moderators
        "an", "sm", "cf",
        # common facilitator given names (in case the transcript uses them)
        "ailsa", "sarah", "claire",
        # generic label
        "participant",
        # known PHIND participant pseudonyms
        "grace", "noah", "emily", "freya", "isla", "amelia", "millie",
        "olivia", "james", "luca", "ella", "ava", "harris", "sophie",
        "oliver", "charlotte", "rory", "sophia", "lily", "aria",
        "esme", "archie", "bonnie", "anna", "elsie", "alfie", "ellie",
        "maya", "divya",
    }

    qesb_allowed_names: set[str] = {
        "i", "interviewer", "moderator", "participant",
        "arden", "dominic", "amalia", "julius",
        "greta", "kiyaan", "matilda",
        "jeremy", "chloe", "kim",
    }
    # Add any participant aliases discovered from the table
    for alias in participant_map:
        qesb_allowed_names.add(alias.lower())

    def is_allowed_speaker(name: str) -> bool:
        lower = name.lower().strip()
        # Never allow bare numbers or time-expression fragments
        if _is_time_expression(lower):
            return False
        if re.match(r"^\d+$", lower):
            return False
        if is_qesb:
            return lower in qesb_allowed_names
        if is_phind:
            return lower in phind_allowed_names
        # Generic fallback for unknown dataset type
        bad_kw = {
            "date of", "location", "participants", "transcription",
            "conventions", "alias", "copyright", "group",
        }
        if any(kw in lower for kw in bad_kw):
            return False
        if len(name) > 30 or "|" in name:
            return False
        if lower.startswith("to "):
            return False
        return True

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    dialogue_started = False
    dialogue_ended = False

    current_speaker_raw: str | None = None
    current_content: list[str] = []
    current_page: int | None = None
    paragraph_indices: list[int] = []
    turn_count = 0

    # ------------------------------------------------------------------
    # Speaker normalisation
    # Returns: (speaker_id, canonical_speaker_id, speaker_name, speaker_role, requires_review)
    # ------------------------------------------------------------------
    def normalize_speaker(raw_name: str):
        nonlocal next_p_idx
        raw = raw_name.strip()
        lower = raw.lower()

        if raw == "UNKNOWN_SPEAKER":
            return "UNKNOWN_SPEAKER", "UNKNOWN", "Unknown", "unknown", True

        # --- Moderator / facilitator detection ---
        if lower == "moderator":
            return "MODERATOR", "MODERATOR", "Moderator", "moderator", False
        if lower == "interviewer":
            return "MODERATOR", "MODERATOR", "Interviewer", "moderator", False
        if lower == "i" and (is_qesb or not is_phind):
            return "MODERATOR_I", "MODERATOR", "I", "moderator", False
        if lower == "an" and (is_phind or not is_qesb):
            return "MODERATOR_AN", "MODERATOR", "AN", "moderator", False
        if lower == "sm" and (is_phind or not is_qesb):
            return "MODERATOR_SM", "MODERATOR", "SM", "moderator", False
        if lower == "cf" and (is_phind or not is_qesb):
            return "MODERATOR_CF", "MODERATOR", "CF", "moderator", False

        # --- Generic unattributed participant ---
        if lower == "participant":
            return (
                "UNATTRIBUTED_PARTICIPANT",
                "UNATTRIBUTED_PARTICIPANT",
                "Participant",
                "unattributed_participant",
                False,
            )

        # --- Numbered patterns: Participant 1, P2, Speaker 3, etc. ---
        p_match = re.match(
            r"^(?:participant|speaker|respondent|p)\s*0*(\d+|[a-z])$", lower
        )
        if p_match:
            idx = p_match.group(1).upper()
            try:
                used_p_indices.add(int(idx))
            except ValueError:
                pass
            pid = f"P{idx}"
            return pid, pid, f"Participant {idx}", "participant", False

        # --- Named participant ---
        if raw not in participant_map:
            while next_p_idx in used_p_indices:
                next_p_idx += 1
            p_id = f"P{next_p_idx}"
            participant_map[raw] = p_id
            used_p_indices.add(next_p_idx)
            next_p_idx += 1

            participant_metadata["participants"].append({
                "speaker_id": p_id,
                "speaker_name": raw,
                "source_alias": raw,
                "metadata_fields": {},
                "requires_review": False,
            })

        p_id = participant_map[raw]
        return p_id, p_id, raw, "participant", False

    # ------------------------------------------------------------------
    # push_turn: flush current speaker buffer → transcript
    # ------------------------------------------------------------------
    def push_turn(line_idx: int) -> None:
        nonlocal turn_count, current_speaker_raw, current_content, paragraph_indices
        if not current_content:
            return
        content_str = "\n".join(current_content).strip()
        if not content_str:
            current_content = []
            paragraph_indices = []
            return

        if not current_speaker_raw:
            sid = "UNKNOWN_SPEAKER"
            cid = "UNKNOWN"
            sname = "Unknown"
            srole = "unknown"
            needs_review = True
        else:
            sid, cid, sname, srole, needs_review = normalize_speaker(current_speaker_raw)

        turn = {
            "turn": turn_count,
            "speaker_id": sid,
            "canonical_speaker_id": cid,
            "speaker_name": sname,
            "speaker_role": srole,
            "content": content_str,
            "source_type": "human_baseline_transcript",
            "source_file": source_file,
            "original_file_type": file_type,
            "page": current_page,
            "paragraph_indices": list(paragraph_indices),
            "standardization_confidence": "low" if needs_review else "high",
            "requires_review": needs_review,
        }
        transcript.append(turn)

        if needs_review:
            review_queue.append({
                "issue_id": str(uuid.uuid4()),
                "baseline_id": baseline_id,
                "issue_type": "unknown_speaker",
                "excerpt": content_str[:200],
                "proposed_action": "Manually identify speaker",
                "confidence": "low",
                "requires_human_review": True,
            })

        turn_count += 1
        current_content = []
        paragraph_indices = []

    # ------------------------------------------------------------------
    # Speaker-label regexes
    # Primary: starts with a letter, handles both : and :: attribution.
    # Bracket: [Unknown Name]: syntax, only used for generic datasets
    #   (not QESB, not PHIND) to avoid misclassifying PHIND transcription
    #   annotations like [inaudible] or [name removed] as speaker turns.
    # ------------------------------------------------------------------
    _SPEAKER_RE = re.compile(
        r"^([A-Za-z][A-Za-z0-9 _]*)::?\s*(.*)", re.IGNORECASE
    )
    # Hash-prefix: #SpeakerName: or #SpeakerName:: (DOCX extraction artifact in QESB)
    _SPEAKER_HASH_RE = re.compile(
        r"^#([A-Za-z][A-Za-z0-9 _]*)::?\s*(.*)", re.IGNORECASE
    )
    _SPEAKER_BRACKET_RE = re.compile(
        r"^\[([A-Za-z][A-Za-z0-9\s_]*?)\]::?\s*(.*)", re.IGNORECASE
    )

    def _speaker_match(line: str):
        """Try speaker patterns in order; restrict each to appropriate datasets."""
        m = _SPEAKER_RE.match(line)
        if m is None and not is_phind:
            # Hash-prefixed speaker labels: DOCX-to-text artifact, not seen in PHIND PDFs
            m = _SPEAKER_HASH_RE.match(line)
        if m is None and not is_qesb and not is_phind:
            # Bracket-syntax [Unknown Name]: only for generic datasets
            m = _SPEAKER_BRACKET_RE.match(line)
        return m

    # ------------------------------------------------------------------
    # Main parse loop
    # ------------------------------------------------------------------
    for line_idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        line_num = line_idx + 1

        # --- Back-matter sentinel ---
        if dialogue_started and not dialogue_ended:
            if stripped.lower() in ("end of transcript", "end of transcript."):
                dialogue_ended = True
                push_turn(line_idx)
                back_matter_lines.append(stripped)
                continue
            if stripped.lower().startswith("end of transcript"):
                dialogue_ended = True
                push_turn(line_idx)
                back_matter_lines.append(stripped)
                continue

        if dialogue_ended:
            back_matter_lines.append(raw_line)
            continue

        # --- Page-number-only lines ---
        if re.match(r"^\d+$", stripped):
            current_page = int(stripped)
            continue

        # --- Blank lines ---
        if not stripped:
            if dialogue_started:
                # Preserve paragraph breaks within a turn
                current_content.append("")
                paragraph_indices.append(line_num)
            else:
                front_matter_lines.append(raw_line)
            continue

        # ==============================================================
        # PRE-DIALOGUE PHASE
        # ==============================================================
        if not dialogue_started:
            match = _speaker_match(stripped)
            is_start = False

            if match:
                speaker_raw = match.group(1).strip()
                sl = speaker_raw.lower()

                if is_qesb:
                    # In QESB the moderator always speaks as "I:" in dialogue.
                    # "Moderator: [Name]" is always a front-matter metadata line.
                    if sl in {"i", "interviewer"}:
                        is_start = True
                    elif speaker_raw in participant_map:
                        is_start = True
                elif is_phind:
                    if sl in {"an", "sm", "cf"}:
                        is_start = True
                else:
                    is_start = bool(is_allowed_speaker(speaker_raw))

            if is_start:
                dialogue_started = True
                participant_metadata["dialogue_start_line"] = line_num
                current_speaker_raw = match.group(1).strip()
                rest = match.group(2).strip()
                current_content = [rest] if rest else []
                paragraph_indices = [line_num]
                participant_metadata["dialogue_end_line"] = line_num
            else:
                # Check for QESB section heading in pre-dialogue region
                if is_qesb and _is_qesb_heading(stripped):
                    section_markers.append({
                        "type": "heading",
                        "content": stripped,
                        "turn_index": turn_count,
                        "position": "pre_dialogue",
                    })
                else:
                    front_matter_lines.append(raw_line)
            continue

        # ==============================================================
        # DIALOGUE PHASE
        # ==============================================================
        match = _speaker_match(stripped)
        if match:
            speaker_raw = match.group(1).strip()

            # Hard guard: prevent time-expression fragments from ever
            # becoming speakers (e.g. "3" from "3:00", "to 4" from ranges)
            if _is_time_expression(speaker_raw):
                current_content.append(raw_line)
                paragraph_indices.append(line_num)
                participant_metadata["dialogue_end_line"] = line_num
                continue

            if is_allowed_speaker(speaker_raw):
                push_turn(line_idx)
                current_speaker_raw = speaker_raw
                rest = match.group(2).strip()
                current_content = [rest] if rest else []
                paragraph_indices = [line_num]
                participant_metadata["dialogue_end_line"] = line_num
            else:
                # Not a recognised speaker — treat as continuation content
                current_content.append(raw_line)
                paragraph_indices.append(line_num)
                participant_metadata["dialogue_end_line"] = line_num
        else:
            # Non-speaker line — check for standalone section heading first
            is_heading = False

            if is_qesb and _is_qesb_heading(stripped):
                push_turn(line_idx)
                section_markers.append({
                    "type": "heading",
                    "content": stripped,
                    "turn_index": turn_count,
                })
                is_heading = True

            # PHIND: section headings are not standalone in the PDF transcripts;
            # all questions are embedded within AN/SM/CF speaker turns.
            # Do not attempt to extract PHIND section headings automatically.

            if not is_heading:
                current_content.append(raw_line)
                paragraph_indices.append(line_num)
                participant_metadata["dialogue_end_line"] = line_num

    # Flush last open turn
    push_turn(len(lines))

    return (
        transcript,
        warnings,
        review_queue,
        "\n".join(front_matter_lines),
        section_markers,
        "\n".join(back_matter_lines),
        participant_metadata,
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Standardize a human focus-group transcript to JSON."
    )
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--metadata-file", required=True)
    parser.add_argument("--output-base-dir", required=True)
    args = parser.parse_args()

    filename = os.path.basename(args.input_file)
    baseline_id = os.path.splitext(filename)[0]
    out_dir = os.path.join(args.output_base_dir, baseline_id)
    os.makedirs(out_dir, exist_ok=True)

    with open(args.input_file, "r", encoding="utf-8") as fh:
        text = fh.read()

    # Look up extraction metadata for original file type / page count
    file_type = "txt"
    pages = None
    p_count = None
    extraction_method = "unknown"
    if os.path.exists(args.metadata_file):
        with open(args.metadata_file, "r", encoding="utf-8") as fh:
            md_list = json.load(fh)
        for md in md_list:
            candidate = (
                md.get("filename", "")
                .replace(".docx", ".txt")
                .replace(".pdf", ".txt")
            )
            if candidate == filename:
                file_type = md.get("file_type", "txt")
                pages = md.get("pages")
                p_count = md.get("paragraph_count")
                extraction_method = md.get("extraction_method", "unknown")
                break

    (
        transcript,
        warnings,
        review_queue,
        fm_text,
        section_markers,
        bm_text,
        p_meta,
    ) = parse_transcript(text, filename, file_type, baseline_id)

    # --- Write artefacts ---
    def _jdump(obj, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)

    _jdump(transcript, os.path.join(out_dir, "transcript.json"))

    # raw_extracted_transcript.txt — raw source extraction (may contain READ ME/front matter)
    with open(os.path.join(out_dir, "raw_extracted_transcript.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)

    # clean_transcript.txt — clean dialogue turns only, no front/back matter
    def _make_clean_transcript(turns):
        lines = []
        for turn in turns:
            name = turn.get("speaker_name", "UNKNOWN")
            content = turn.get("content", "").strip()
            lines.append(f"{name}:")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)

    clean_text = _make_clean_transcript(transcript)
    with open(os.path.join(out_dir, "clean_transcript.txt"), "w", encoding="utf-8") as fh:
        fh.write(clean_text)

    # transcript.txt — clean dialogue (same as clean_transcript.txt)
    with open(os.path.join(out_dir, "transcript.txt"), "w", encoding="utf-8") as fh:
        fh.write(clean_text)

    with open(os.path.join(out_dir, "front_matter.txt"), "w", encoding="utf-8") as fh:
        fh.write(fm_text)

    with open(os.path.join(out_dir, "back_matter.txt"), "w", encoding="utf-8") as fh:
        fh.write(bm_text)

    _jdump(section_markers, os.path.join(out_dir, "section_markers.json"))
    _jdump(p_meta, os.path.join(out_dir, "participant_metadata.json"))

    # Always write these files (empty list if no issues)
    _jdump(warnings, os.path.join(out_dir, "standardization_warnings.json"))
    _jdump(review_queue, os.path.join(out_dir, "review_queue.json"))

    # --- Compute baseline_metadata ---
    named_participants = {
        t["speaker_id"]
        for t in transcript
        if t["speaker_role"] == "participant"
    }
    has_mod = any(t["speaker_role"] == "moderator" for t in transcript)
    words = len(text.split())
    fm_words = len(fm_text.split())
    bm_words = len(bm_text.split())

    baseline_metadata = {
        "baseline_id": baseline_id,
        "source_type": "human_baseline_transcript",
        "original_filename": filename,
        "original_file_type": file_type,
        "extraction_method": extraction_method,
        "standardization_method": "script_claude_v1",
        "topic_domain": "unknown",
        "participant_count_detected": len(named_participants),
        "moderator_detected": has_mod,
        "turn_count": len(transcript),
        "word_count": words,
        "pages": pages,
        "paragraph_count": p_count,
        "guide_available": False,
        "guide_id": None,
        "comparable_to_synthetic_topic": "unknown",
        "usable_for_process_baseline": "yes" if len(transcript) > 0 else "no",
        "usable_for_topic_outcome_baseline": "no",
        "notes": "",
        "caveats": "Automatically standardized — claude_v1 pipeline.",
        "front_matter_extracted": bool(fm_text.strip()),
        "front_matter_word_count": fm_words,
        "back_matter_extracted": bool(bm_text.strip()),
        "back_matter_word_count": bm_words,
        "participant_table_detected": len(p_meta["participants"]) > 0,
        "participant_aliases_detected": [
            p["source_alias"] for p in p_meta["participants"]
        ],
        "dialogue_start_line": p_meta.get("dialogue_start_line", -1),
        "dialogue_start_confidence": "high",
        "dialogue_end_line": p_meta.get("dialogue_end_line", -1),
        "section_markers_count": len(section_markers),
        "moderator_labels_detected": sorted(
            {t["speaker_name"] for t in transcript if t["speaker_role"] == "moderator"}
        ),
        "facilitator_labels_detected": sorted(
            {t["speaker_name"] for t in transcript if t["speaker_role"] == "moderator"}
        ),
    }

    _jdump(baseline_metadata, os.path.join(out_dir, "baseline_metadata.json"))

    print(
        f"[standardize] {baseline_id}: {len(transcript)} turns, "
        f"{len(named_participants)} participants, "
        f"{len(section_markers)} section markers, "
        f"mod={has_mod}"
    )


if __name__ == "__main__":
    main()
