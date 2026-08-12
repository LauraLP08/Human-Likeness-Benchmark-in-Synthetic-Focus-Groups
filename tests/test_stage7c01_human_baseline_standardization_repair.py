import os
import json
import pytest
import re
from scripts.standardize_human_focus_group_transcript import parse_transcript
from assessment.schema import SessionArtifacts
from assessment.metrics import compute_mechanical_integrity, compute_process_metrics, compute_moderator_metrics

# --- QESB Tests ---

# 1. I: maps to speaker_role = moderator.
def test_qesb_i_moderator():
    text = "I: Hello everyone.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert len(transcript) == 1
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_id"] == "MODERATOR_I"
    assert transcript[0]["speaker_name"] == "I"

# 2. I:: maps to speaker_role = moderator.
def test_qesb_double_colon_moderator():
    text = "I:: Hello again.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert len(transcript) == 1
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_id"] == "MODERATOR_I"
    assert transcript[0]["speaker_name"] == "I"

# 3. Interviewer: maps to speaker_role = moderator.
def test_qesb_interviewer_moderator():
    text = "Interviewer: Good day.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert len(transcript) == 1
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_id"] == "MODERATOR"
    assert transcript[0]["speaker_name"] == "Interviewer"

# 4. Moderator: Dr. Edzia Carvalho in front matter is metadata, not dialogue.
def test_qesb_moderator_name_metadata():
    text = "READ ME\nModerator: Dr. Edzia Carvalho\nI: Let's start.\n"
    transcript, _, _, fm, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert "Dr. Edzia Carvalho" in fm
    assert "Moderator: Dr. Edzia Carvalho" in fm
    # It shouldn't create a turn for the moderator declaration line
    assert len(transcript) == 1
    assert transcript[0]["speaker_name"] == "I"

# 5. READ ME text is stored in front_matter.txt, not transcript.json.
def test_qesb_readme_is_front_matter():
    text = "READ ME\nOn copyright and attribution\nI: Let's start.\n"
    transcript, _, _, fm, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert "READ ME" in fm
    assert "On copyright and attribution" in fm
    assert len(transcript) == 1
    assert "READ ME" not in transcript[0]["content"]

# 6. Participant table rows are stored in participant_metadata.json, not transcript.json.
def test_qesb_participant_table_in_metadata():
    text = "Alias | Sex | Constituency\nArden | Non-binary | Dundee\nI: Let's start.\n"
    transcript, _, _, fm, _, _, p_meta = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert len(p_meta["participants"]) == 1
    assert p_meta["participants"][0]["speaker_name"] == "Arden"
    assert p_meta["participants"][0]["metadata_fields"]["Sex"] == "Non-binary"
    assert len(transcript) == 1
    assert all("Arden" not in turn["content"] for turn in transcript)

# 7. Participant aliases pre-seed stable P1/P2/P3 mapping.
def test_qesb_aliases_preseed():
    text = "Alias | Sex | Constituency\nArden | Non-binary | Dundee\nDominic | M | Dundee\nI: Let's start.\nArden: Hello.\nDominic: Hi.\n"
    transcript, _, _, _, _, _, p_meta = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert transcript[1]["speaker_id"] == "P1"
    assert transcript[1]["speaker_name"] == "Arden"
    assert transcript[2]["speaker_id"] == "P2"
    assert transcript[2]["speaker_name"] == "Dominic"

# 8. First actual QESB dialogue turn is moderator.
def test_qesb_first_turn_is_moderator():
    text = "READ ME\nI: Hello.\nArden: Hi.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_name"] == "I"

# 9. No speaker_name I exists with speaker_role = participant.
def test_qesb_no_speaker_name_i_is_participant():
    text = "I: Hello.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    for turn in transcript:
        if turn["speaker_name"] == "I":
            assert turn["speaker_role"] == "moderator"

# 10. Section headings are stored in section_markers.json, not as participant turns.
def test_qesb_section_headings():
    text = "Your Voting Story\nI: Let's start.\n"
    transcript, _, _, fm, sm, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    assert len(sm) == 1
    assert sm[0]["content"] == "Your Voting Story"
    assert len(transcript) == 1


# --- PHIND Tests ---

# 11. AN: maps to speaker_role = moderator.
def test_phind_an_moderator():
    text = "AN: Welcome.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_id"] == "MODERATOR_AN"

# 12. SM: maps to speaker_role = moderator.
def test_phind_sm_moderator():
    text = "SM: Welcome.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_id"] == "MODERATOR_SM"

# 13. CF: maps to speaker_role = moderator.
def test_phind_cf_moderator():
    text = "CF: Welcome.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert transcript[0]["speaker_role"] == "moderator"
    assert transcript[0]["speaker_id"] == "MODERATOR_CF"

# 14. AN::, SM::, CF:: map to moderator/facilitator.
def test_phind_double_colon_facilitators():
    text = "AN:: First.\nSM:: Second.\nCF:: Third.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert len(transcript) == 3
    assert all(t["speaker_role"] == "moderator" for t in transcript)

# 15. PHIND employee group 1 is stored in front_matter.txt, not transcript.json.
def test_phind_title_is_front_matter():
    text = "PHIND employee group 1\nAN: Hello.\n"
    transcript, _, _, fm, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert "PHIND employee group 1" in fm
    assert len(transcript) == 1

# 16. [Transcription commenced 11:30] is stored in front_matter/metadata, not transcript.json.
def test_phind_timestamp_is_front_matter():
    text = "[Transcription commenced 11:30]\nAN: Hello.\n"
    transcript, _, _, fm, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert "[Transcription commenced 11:30]" in fm
    assert len(transcript) == 1

# 17. Page-number-only lines are removed from dialogue turns.
def test_phind_page_numbers_removed():
    text = "AN: Hello.\n12\nGrace: Hi.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert len(transcript) == 2
    assert "12" not in transcript[0]["content"]
    assert "12" not in transcript[1]["content"]

# 18. End of transcript is stored in back_matter.txt or excluded from dialogue.
def test_phind_end_of_transcript_is_back_matter():
    text = "AN: Let's close.\nEnd of transcript\n"
    transcript, _, _, _, _, bm, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert "End of transcript" in bm
    assert "End of transcript" not in transcript[0]["content"]

# 19. Generic Participant: maps to speaker_role = unattributed_participant.
def test_phind_generic_participant_role():
    text = "AN: Hello.\nParticipant: Yes.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert transcript[1]["speaker_role"] == "unattributed_participant"
    assert transcript[1]["speaker_id"] == "UNATTRIBUTED_PARTICIPANT"
    assert transcript[1]["speaker_name"] == "Participant"

# 20. Generic Participant: does not inflate participant_count_detected.
def test_phind_generic_participant_no_inflation():
    text = "AN: Hello.\nParticipant: Yes.\nGrace: Hi.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    participants = set(t["speaker_id"] for t in transcript if t["speaker_role"] == "participant")
    # Excludes UNATTRIBUTED_PARTICIPANT
    assert len(participants) == 1 # Only Grace (P1)
    assert "UNATTRIBUTED_PARTICIPANT" not in participants

# 21. PHIND first actual dialogue turn is moderator/facilitator.
def test_phind_first_turn_is_moderator():
    text = "PHIND employee group 1\nAN: Welcome.\nGrace: Hi.\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert transcript[0]["speaker_role"] == "moderator"

# 22. [inaudible 11:30] is preserved and counted as transcription convention.
def test_phind_inaudible_preserved():
    text = "AN: Hello [inaudible 11:30]\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert "[inaudible 11:30]" in transcript[0]["content"]

# 23. [location removed] and [organisation name removed] are preserved and counted as removed identifier conventions.
def test_phind_removed_identifiers_preserved():
    text = "AN: We are in [location removed] and work at [organisation name removed].\n"
    transcript, _, _, _, _, _, _ = parse_transcript(text, "test.txt", "txt", "PHIND_test")
    assert "[location removed]" in transcript[0]["content"]
    assert "[organisation name removed]" in transcript[0]["content"]


# --- Shared & Assessment Tests ---

# 24. UNKNOWN_SPEAKER front matter does not appear as a dialogue turn.
def test_unknown_speaker_no_front_matter_dialogue():
    text = "READ ME\nSome introductory comments\nI: Let's start.\n"
    transcript, _, _, fm, _, _, _ = parse_transcript(text, "test.txt", "txt", "QESB_test")
    # Front matter should not yield an UNKNOWN_SPEAKER turn
    assert all(turn["speaker_id"] != "UNKNOWN_SPEAKER" for turn in transcript)

# 25. Human baseline assessment runs on repaired transcripts.
def test_human_baseline_assessment_runs():
    transcript_data = [
        {
            "turn": 0, "speaker_id": "MODERATOR_I", "speaker_name": "I", "speaker_role": "moderator",
            "content": "Welcome. Let's start with your voting story.", "source_type": "human_baseline_transcript"
        },
        {
            "turn": 1, "speaker_id": "P1", "speaker_name": "Arden", "speaker_role": "participant",
            "content": "I voted Labour. ** I felt good.", "source_type": "human_baseline_transcript"
        },
        {
            "turn": 2, "speaker_id": "P2", "speaker_name": "Dominic", "speaker_role": "participant",
            "content": "I voted Green. {laughs} It was nice.", "source_type": "human_baseline_transcript"
        },
        {
            "turn": 3, "speaker_id": "P3", "speaker_name": "Amalia", "speaker_role": "participant",
            "content": "I went to [location removed] and voted.", "source_type": "human_baseline_transcript"
        }
    ]
    artifacts = SessionArtifacts(session_dir="data/human_baseline/standardized/mock_baseline", run_id="mock_baseline")
    artifacts.transcript = transcript_data
    
    # Run track metrics
    mech = compute_mechanical_integrity(artifacts)
    proc = compute_process_metrics(artifacts, {})
    mod = compute_moderator_metrics(artifacts)
    
    assert mech.status == "PASS"
    assert proc.status == "PASS" or proc.status == "WARNING" # due to balance/turn counts
    assert mod.status == "PASS"

# 26. Moderator word share is computed from speaker_role == moderator.
def test_moderator_word_share_computation():
    transcript_data = [
        {"turn": 0, "speaker_id": "MODERATOR_I", "speaker_name": "I", "speaker_role": "moderator", "content": "Hello.", "source_type": "human_baseline_transcript"}, # 1 word
        {"turn": 1, "speaker_id": "P1", "speaker_name": "Arden", "speaker_role": "participant", "content": "One two.", "source_type": "human_baseline_transcript"}, # 2 words
        {"turn": 2, "speaker_id": "P2", "speaker_name": "Bob", "speaker_role": "participant", "content": "Yes.", "source_type": "human_baseline_transcript"}, # 1 word
        {"turn": 3, "speaker_id": "P3", "speaker_name": "Charlie", "speaker_role": "participant", "content": "No.", "source_type": "human_baseline_transcript"} # 1 word
    ]
    artifacts = SessionArtifacts(session_dir="mock", run_id="mock")
    artifacts.transcript = transcript_data
    proc = compute_process_metrics(artifacts, {})
    # 1 word moderator / 5 words total = 0.20
    assert abs(proc.metrics["moderator_word_share"].value - 0.20) < 0.01

# 27. Participant count excludes moderator/facilitator initials.
def test_participant_count_excludes_moderators():
    transcript_data = [
        {"turn": 0, "speaker_id": "MODERATOR_I", "speaker_name": "I", "speaker_role": "moderator", "content": "Hello.", "source_type": "human_baseline_transcript"},
        {"turn": 1, "speaker_id": "P1", "speaker_name": "Arden", "speaker_role": "participant", "content": "Yes.", "source_type": "human_baseline_transcript"},
        {"turn": 2, "speaker_id": "P2", "speaker_name": "Dominic", "speaker_role": "participant", "content": "Yes.", "source_type": "human_baseline_transcript"}
    ]
    artifacts = SessionArtifacts(session_dir="mock", run_id="mock")
    artifacts.transcript = transcript_data
    proc = compute_process_metrics(artifacts, {})
    assert proc.metrics["participant_count"].value == 2 # Only Arden & Dominic

# 28. Participant count excludes generic unattributed participant closings.
def test_participant_count_excludes_unattributed():
    transcript_data = [
        {"turn": 0, "speaker_id": "MODERATOR_I", "speaker_name": "I", "speaker_role": "moderator", "content": "Hello.", "source_type": "human_baseline_transcript"},
        {"turn": 1, "speaker_id": "P1", "speaker_name": "Arden", "speaker_role": "participant", "content": "Yes.", "source_type": "human_baseline_transcript"},
        {"turn": 2, "speaker_id": "UNATTRIBUTED_PARTICIPANT", "speaker_name": "Participant", "speaker_role": "unattributed_participant", "content": "Goodbye.", "source_type": "human_baseline_transcript"}
    ]
    artifacts = SessionArtifacts(session_dir="mock", run_id="mock")
    artifacts.transcript = transcript_data
    proc = compute_process_metrics(artifacts, {})
    assert proc.metrics["participant_count"].value == 1 # Only Arden (P1)

# 29. Synthetic-session assessment tests still pass.
def test_synthetic_session_assessment_still_passes():
    # A synthetic transcript (source_type is NOT human_baseline_transcript)
    transcript_data = [
        {"turn": 0, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "speaker_role": "moderator", "content": "Hello.", "source_type": "synthetic_agent"},
        {"turn": 1, "speaker_id": "P1", "speaker_name": "Participant 1", "speaker_role": "participant", "content": "Yes.", "source_type": "synthetic_agent"}
    ]
    artifacts = SessionArtifacts(session_dir="mock", run_id="mock")
    artifacts.transcript = transcript_data
    artifacts.run_metadata = {
        "selection_mode_counts": {"moderator_intervention": 1, "voluntary": 1},
        "participant_response_truncation_count": 0
    }
    mech = compute_mechanical_integrity(artifacts)
    # Since moderator and participant count match, mismatch flags shouldn't fail the track
    assert not any(f.flag_id == "MODERATOR_COUNT_MISMATCH" for f in mech.flags)
    assert not any(f.flag_id == "PARTICIPANT_COUNT_MISMATCH" for f in mech.flags)
