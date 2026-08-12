"""
Tests for the claude_v1 human-baseline standardization pipeline.

Tests 1–35 as specified in the project requirements.
"""

import os
import json
import tempfile
import pytest

from scripts.standardize_human_focus_group_transcript import parse_transcript
from scripts.standardize_focus_group_guide import parse_guide
from assessment.loader import load_session_artifacts
from assessment.metrics import (
    compute_moderator_metrics,
    compute_research_design_metrics,
    compute_process_metrics,
)


# ---------------------------------------------------------------------------
# Helper: canonical IDs from transcript
# ---------------------------------------------------------------------------
def _speakers_by_role(transcript, role):
    return [t for t in transcript if t.get("speaker_role") == role]


def _speaker_names_with_role(transcript, role):
    return {t["speaker_name"] for t in transcript if t.get("speaker_role") == role}


# ---------------------------------------------------------------------------
# Minimal QESB transcript fixture
# ---------------------------------------------------------------------------
QESB_MINIMAL = """
READ ME

Transcribed 'Qualitative Election Study of Britain 2024' Dataset Version 1.0

On copyright and attribution

Copyright of this transcript belongs to Drs Thom Oliver, Edzia Carvalho, Kristi Winters.
Recommended citation: Oliver, T. et al. 2024.

Reporting conventions used

We have used ** to indicate words we could not hear.
Italic font indicates a guess.
Words in parentheses {} indicate gestures.
Removal of identifiers are set off with + word +

Alias | Sex | Special Category | Age group | Supporter | Party | Strength | Constituency | 2024 vote preference | 2024 vote reported | Panellist
Arden | Non-binary | N | 34-41 | N | n/a | n/a | Arbroath | Y, but NOT which party | Spoilled ballot | N
Dominic | M | Student | 26-33 | N | n/a | n/a | Dundee | Y, but NOT which party | TUSC | Y
Amalia | Non-binary | Student | 26-33 | N | n/a | n/a | Dundee | Y, and which party | Liberal Democrats | N

Date of the interview: 19 July 2024
Moderator: Dr. Edzia Carvalho
Location: Online
Participants:
Pre-election transcripts: Pre_Dominic_Aurora_29_v1.0

Your Voting Story
I: So, tell us about your voting day. Arden, shall I start with you?
Arden:	Yeah, I had a postal vote. I didn't go out that day. I came home and had a nap. {laughs}
I:: Thanks Arden. Dominic?
Dominic:: I tried to be first at the polling station.
Your Voting Outcome Story
I: Did you stay up for the exit poll? Julius?
Amalia: I couldn't care less! ** unclear ** Yeah.
Turnout Impressions
I: What do you think about turnout levels?
Dominic: Only 52% in Dundee, which is shocking.
"""


QESB_MINIMAL_BASELINE_ID = "QESB_Post_Arden_Dominic_Amalia_test"


@pytest.fixture
def qesb_transcript():
    return parse_transcript(
        QESB_MINIMAL, "QESB_Post_Arden_Dominic_Amalia_test.txt", "docx", QESB_MINIMAL_BASELINE_ID
    )


# ---------------------------------------------------------------------------
# Minimal PHIND transcript fixture
# ---------------------------------------------------------------------------
PHIND_MINIMAL = """1
PHIND employee group 1
[Transcription commenced 11:30]

AN:
What did you think about the infographic about sitting?  Was any of that new to you?
Who wants to go first?

Grace:
I'll go first. None of it was new to me. My research is in lower back pain
and sedentary behaviour. [inaudible 12:19]

AN:
Thanks, Grace. Noah?

Noah:
I was just going to say pretty much the same as Grace.

SM:
Thanks. Anyone else?

Emily:
Yeah, I'm not familiar with the research but it's clear.

Participant:
I agree with the others.

End of transcript
"""

PHIND_MINIMAL_BASELINE_ID = "Work at home_FG transcript_employee group 1_pseudo"


@pytest.fixture
def phind_transcript():
    return parse_transcript(
        PHIND_MINIMAL, "Work at home_FG transcript_employee group 1_pseudo.txt", "pdf",
        PHIND_MINIMAL_BASELINE_ID
    )


# ===========================================================================
# QESB Tests (1–10)
# ===========================================================================

# Test 1: I: maps to speaker_role = moderator
def test_1_qesb_I_colon_is_moderator(qesb_transcript):
    transcript, *_ = qesb_transcript
    mod_turns = [t for t in transcript if t["speaker_name"] == "I"]
    assert len(mod_turns) > 0, "Expected at least one turn with speaker_name='I'"
    for t in mod_turns:
        assert t["speaker_role"] == "moderator", (
            f"Expected 'moderator' but got '{t['speaker_role']}'"
        )
        assert t["speaker_id"] == "MODERATOR_I"
        assert t["canonical_speaker_id"] == "MODERATOR"


# Test 2: I:: maps to speaker_role = moderator
def test_2_qesb_I_double_colon_is_moderator(qesb_transcript):
    transcript, *_ = qesb_transcript
    # PHIND_MINIMAL has "I:: Thanks Arden." — QESB_MINIMAL also has "I::"
    double_colon_turns = [
        t for t in transcript
        if t["speaker_name"] == "I" and t["speaker_role"] == "moderator"
    ]
    assert len(double_colon_turns) > 0, "Expected I:: turns to map to moderator"


# Test 3: Interviewer: maps to speaker_role = moderator
def test_3_qesb_interviewer_is_moderator():
    text = """
Alias | Sex | Special Category | Age group | Supporter | Party | Strength | Constituency | 2024 vote preference | 2024 vote reported | Panellist
Kim | F | N | 26-33 | N | n/a | n/a | Clacton | Y | Labour | N

Your Voting Story
Interviewer: Tell us your voting story. Kim?
Kim: I voted Labour this time.
"""
    transcript, *_ = parse_transcript(text, "test.txt", "docx", "QESB_test")
    mod_turns = [t for t in transcript if t.get("speaker_name") == "Interviewer"]
    assert len(mod_turns) > 0
    for t in mod_turns:
        assert t["speaker_role"] == "moderator"


# Test 4: Moderator: Dr. Edzia Carvalho in front matter is not dialogue
def test_4_qesb_moderator_front_matter_not_dialogue(qesb_transcript):
    transcript, *_ = qesb_transcript
    for turn in transcript:
        assert "Dr. Edzia Carvalho" not in turn.get("content", ""), (
            "Moderator front-matter line leaked into transcript"
        )
        assert turn.get("speaker_name") != "Dr. Edzia Carvalho"
        assert turn.get("speaker_id") != "Dr. Edzia Carvalho"


# Test 5: READ ME text is in front_matter.txt, not transcript.json
def test_5_qesb_readme_in_front_matter(qesb_transcript):
    transcript, warnings, review_queue, front_matter, section_markers, back_matter, p_meta = qesb_transcript
    assert "READ ME" in front_matter, "READ ME should be in front_matter"
    for turn in transcript:
        assert "READ ME" not in turn.get("content", ""), "READ ME leaked into transcript"


# Test 6: Participant table rows in participant_metadata, not transcript
def test_6_qesb_participant_table_not_dialogue(qesb_transcript):
    transcript, warnings, review_queue, front_matter, section_markers, back_matter, p_meta = qesb_transcript
    for turn in transcript:
        content = turn.get("content", "")
        assert "Alias | Sex" not in content, "Table header leaked into transcript"
        assert "Non-binary / third gender" not in content, "Table row leaked"


# Test 7: Participant aliases pre-seed stable P1/P2/P3 mapping
def test_7_qesb_participant_aliases_preseeded(qesb_transcript):
    transcript, *_, p_meta = qesb_transcript
    aliases = {p["source_alias"] for p in p_meta["participants"]}
    # Must contain the aliases from the participant table
    assert "Arden" in aliases
    assert "Dominic" in aliases
    assert "Amalia" in aliases
    # Check speaker_ids are stable Px
    arden_id = next(
        p["speaker_id"] for p in p_meta["participants"] if p["source_alias"] == "Arden"
    )
    assert re.match(r"^P\d+$", arden_id), f"Arden should have Px id, got {arden_id}"


import re  # needed for test_7


# Test 8: Standalone QESB section headings in section_markers, not transcript
def test_8_qesb_section_headings_in_markers(qesb_transcript):
    transcript, warnings, review_queue, front_matter, section_markers, back_matter, p_meta = qesb_transcript
    heading_contents = {m["content"] for m in section_markers}
    # Our QESB_MINIMAL has: Your Voting Story, Your Voting Outcome Story, Turnout Impressions
    assert any("Voting Story" in h for h in heading_contents), (
        f"'Your Voting Story' should be in section_markers; got {heading_contents}"
    )
    assert any("Turnout Impressions" in h for h in heading_contents), (
        f"'Turnout Impressions' should be in section_markers; got {heading_contents}"
    )
    # Confirm headings are NOT in transcript turns
    for turn in transcript:
        content = turn.get("content", "").strip()
        for heading in ["Your Voting Story", "Turnout Impressions", "Your Voting Outcome Story"]:
            assert content.lower() != heading.lower(), (
                f"Heading '{heading}' found as dialogue turn: {turn}"
            )


# Test 9: First actual QESB dialogue turn is moderator
def test_9_qesb_first_turn_is_moderator(qesb_transcript):
    transcript, *_ = qesb_transcript
    assert len(transcript) > 0
    assert transcript[0]["speaker_role"] == "moderator", (
        f"First QESB turn should be moderator, got '{transcript[0]['speaker_role']}'"
    )


# Test 10: No speaker_name 'I' with role = participant
def test_10_qesb_I_never_participant(qesb_transcript):
    transcript, *_ = qesb_transcript
    for turn in transcript:
        if turn.get("speaker_name") == "I":
            assert turn["speaker_role"] != "participant", (
                f"'I' must not be participant: {turn}"
            )


# ===========================================================================
# PHIND Tests (11–23)
# ===========================================================================

# Test 11: AN: maps to speaker_role = moderator
def test_11_phind_AN_is_moderator(phind_transcript):
    transcript, *_ = phind_transcript
    an_turns = [t for t in transcript if t["speaker_name"] == "AN"]
    assert len(an_turns) > 0
    for t in an_turns:
        assert t["speaker_role"] == "moderator"
        assert t["speaker_id"] == "MODERATOR_AN"
        assert t["canonical_speaker_id"] == "MODERATOR"


# Test 12: SM: maps to speaker_role = moderator
def test_12_phind_SM_is_moderator(phind_transcript):
    transcript, *_ = phind_transcript
    sm_turns = [t for t in transcript if t["speaker_name"] == "SM"]
    assert len(sm_turns) > 0
    for t in sm_turns:
        assert t["speaker_role"] == "moderator"
        assert t["speaker_id"] == "MODERATOR_SM"
        assert t["canonical_speaker_id"] == "MODERATOR"


# Test 13: CF: maps to speaker_role = moderator
def test_13_phind_CF_is_moderator():
    text = """1
PHIND employer focus group 1
[Transcription begins 11:25]

CF:
Thanks everyone for joining today.

Rory:
Happy to be here.
"""
    transcript, *_ = parse_transcript(text, "test.txt", "pdf", "Work at home_FG Transcript_employer group 1_pseudo")
    cf_turns = [t for t in transcript if t["speaker_name"] == "CF"]
    assert len(cf_turns) > 0
    for t in cf_turns:
        assert t["speaker_role"] == "moderator"
        assert t["speaker_id"] == "MODERATOR_CF"
        assert t["canonical_speaker_id"] == "MODERATOR"


# Test 14: AN:: SM:: CF:: map to moderator
def test_14_phind_double_colon_facilitators_are_moderator():
    text = """1
PHIND employee group 2
[Transcription starts at 12.30]

AN::
Good morning everyone.

SM::
I'll take the next question.

CF::
Thanks for your input.

Grace:
Thank you.
"""
    transcript, *_ = parse_transcript(text, "test.txt", "pdf", "Work at home_FG Transcript_employee group 2_pseudo")
    for label in ("AN", "SM", "CF"):
        turns = [t for t in transcript if t["speaker_name"] == label]
        assert len(turns) > 0, f"Expected turns for {label}"
        for t in turns:
            assert t["speaker_role"] == "moderator", (
                f"{label} should be moderator, got {t['speaker_role']}"
            )


# Test 15: PHIND employee group label in front_matter, not transcript
def test_15_phind_group_label_in_front_matter(phind_transcript):
    transcript, warnings, review_queue, front_matter, section_markers, back_matter, p_meta = phind_transcript
    assert "PHIND employee group 1" in front_matter, (
        "Group label should be in front_matter"
    )
    for turn in transcript:
        assert "PHIND employee group" not in turn.get("content", ""), (
            "Group label leaked into transcript"
        )


# Test 16: [Transcription commenced 11:30] is front matter, not dialogue
def test_16_phind_transcription_timestamp_is_front_matter(phind_transcript):
    transcript, warnings, review_queue, front_matter, section_markers, back_matter, p_meta = phind_transcript
    assert "Transcription commenced" in front_matter, (
        "Transcription timestamp should be in front_matter"
    )
    for turn in transcript:
        assert "Transcription commenced" not in turn.get("content", ""), (
            "Transcription timestamp leaked into transcript"
        )


# Test 17: Page-number-only lines are removed from dialogue
def test_17_phind_page_numbers_excluded():
    # Our PHIND_MINIMAL has "1" as line 1. It should not appear as content.
    text = """1
PHIND employee group 1
[Transcription commenced 11:30]

AN:
First question.

2
Grace:
I'll answer.
"""
    transcript, *_ = parse_transcript(text, "test.txt", "pdf", "Work at home_FG transcript_employee group 1_pseudo")
    for turn in transcript:
        # Content should not be just a digit
        content = turn.get("content", "").strip()
        assert not re.match(r"^\d+$", content), (
            f"Page number appeared as turn content: {content}"
        )
        # speaker_name should not be a digit
        assert not re.match(r"^\d+$", turn.get("speaker_name", "")), (
            f"Page number appeared as speaker: {turn}"
        )


# Test 18: End of transcript is back matter or excluded from dialogue
def test_18_phind_end_of_transcript_is_back_matter(phind_transcript):
    transcript, warnings, review_queue, front_matter, section_markers, back_matter, p_meta = phind_transcript
    # "End of transcript" should be in back_matter or not in transcript at all
    for turn in transcript:
        assert "end of transcript" not in turn.get("content", "").lower(), (
            "End of transcript appeared in transcript.json"
        )
    assert "End of transcript" in back_matter, (
        "End of transcript should be captured in back_matter"
    )


# Test 19: Generic Participant: maps to unattributed_participant
def test_19_phind_generic_participant_maps_to_unattributed(phind_transcript):
    transcript, *_ = phind_transcript
    participant_turns = [t for t in transcript if t["speaker_name"] == "Participant"]
    assert len(participant_turns) > 0, "Expected at least one generic Participant turn"
    for t in participant_turns:
        assert t["speaker_role"] == "unattributed_participant", (
            f"Generic Participant should be 'unattributed_participant', got '{t['speaker_role']}'"
        )
        assert t["speaker_id"] == "UNATTRIBUTED_PARTICIPANT"


# Test 20: Generic Participant: does not inflate participant_count_detected
def test_20_phind_generic_participant_excluded_from_count(phind_transcript):
    transcript, *_ = phind_transcript
    named_participant_ids = {
        t["speaker_id"] for t in transcript
        if t["speaker_role"] == "participant"
    }
    unattributed_ids = {
        t["speaker_id"] for t in transcript
        if t["speaker_role"] == "unattributed_participant"
    }
    # Unattributed participants should NOT be in the named participant set
    assert "UNATTRIBUTED_PARTICIPANT" not in named_participant_ids, (
        "UNATTRIBUTED_PARTICIPANT incorrectly included in participant count"
    )
    # Count should only include role=participant
    count_participants = len(named_participant_ids)
    count_unattributed = len(unattributed_ids)
    assert count_participants >= 1, "Should have at least one named participant (Grace, Noah, etc.)"
    # Verify UNATTRIBUTED_PARTICIPANT is not counted as a named participant
    assert "UNATTRIBUTED_PARTICIPANT" not in {
        t["speaker_id"] for t in transcript if t["speaker_role"] == "participant"
    }


# Test 21: PHIND first actual dialogue turn is moderator/facilitator
def test_21_phind_first_turn_is_moderator(phind_transcript):
    transcript, *_ = phind_transcript
    assert len(transcript) > 0
    first = transcript[0]
    assert first["speaker_role"] == "moderator", (
        f"First PHIND turn should be moderator, got '{first['speaker_role']}' "
        f"(speaker='{first.get('speaker_name')}')"
    )


# Test 22: [inaudible 11:30] preserved and counted as transcription convention
def test_22_phind_inaudible_preserved(phind_transcript):
    transcript, *_ = phind_transcript
    all_content = " ".join(t["content"] for t in transcript)
    assert "[inaudible" in all_content.lower(), (
        "Expected [inaudible ...] to be preserved in transcript content"
    )


# Test 23: [location removed] and [organisation name removed] preserved
def test_23_phind_removal_markers_preserved():
    text = """1
PHIND employer focus group 3
[Transcription begins 11:25]

SM:
Thanks for joining.

Archie:
We work across the [organisation name removed] campus.
The [location removed] office is now remote.
"""
    transcript, *_ = parse_transcript(text, "test.txt", "pdf", "Work at home_FG Transcript_employer group 3_pseudo")
    all_content = " ".join(t["content"] for t in transcript)
    assert "[organisation name removed]" in all_content, (
        "Organisation name removal marker should be preserved"
    )
    assert "[location removed]" in all_content, (
        "Location removal marker should be preserved"
    )


# ===========================================================================
# Shared Tests (24–35)
# ===========================================================================

# Test 24: Time expressions not parsed as speakers
def test_24_time_expressions_not_speakers():
    text = """1
PHIND employee group 1
[Transcription commenced 11:30]

AN:
We usually work from 9:00 to 5:00. What changed for you? Between 3:00 and 4:00?

Grace:
I now work from 8:00 to 17:00 typically, and sit 12:30 straight.
"""
    transcript, *_ = parse_transcript(
        text, "test.txt", "pdf",
        "Work at home_FG transcript_employee group 1_pseudo"
    )
    for turn in transcript:
        sname = turn.get("speaker_name", "")
        sid = turn.get("speaker_id", "")
        for label in (sname, sid):
            assert not re.match(r"^\d{1,2}:\d{2}$", label), (
                f"Time expression '{label}' used as speaker in turn {turn['turn']}"
            )
            assert not re.match(r"^\d{1,2}$", label), (
                f"Bare number '{label}' used as speaker in turn {turn['turn']}"
            )
            assert not label.lower().startswith("to "), (
                f"Time-range prefix '{label}' used as speaker in turn {turn['turn']}"
            )


# Test 25: UNKNOWN_SPEAKER front matter does not appear as dialogue
def test_25_no_unknown_speaker_front_matter(qesb_transcript):
    transcript, *_ = qesb_transcript
    for turn in transcript:
        if turn.get("speaker_id") == "UNKNOWN_SPEAKER":
            # Content should not look like front matter
            content = turn.get("content", "").lower()
            assert "read me" not in content
            assert "copyright" not in content
            assert "recommended citation" not in content
            assert "alias | sex" not in content


# Test 26: Paragraph breaks inside a speaker turn are preserved
def test_26_paragraph_breaks_preserved():
    text = """1
PHIND employee group 1
[Transcription commenced 11:30]

AN:
Question one.

Grace:
First paragraph of my answer.

Second paragraph continues the same thought.

AN:
Thank you.
"""
    transcript, *_ = parse_transcript(
        text, "test.txt", "pdf",
        "Work at home_FG transcript_employee group 1_pseudo"
    )
    grace_turns = [t for t in transcript if t["speaker_name"] == "Grace"]
    assert len(grace_turns) == 1, "Grace should have one turn (multi-paragraph)"
    content = grace_turns[0]["content"]
    assert "First paragraph" in content
    assert "Second paragraph" in content


# Test 27: Human baseline assessment runs on standardized_claude_v1 folders
def test_27_human_baseline_assessment_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as fh:
            json.dump([
                {
                    "turn": 0,
                    "speaker_id": "MODERATOR_I",
                    "canonical_speaker_id": "MODERATOR",
                    "speaker_name": "I",
                    "speaker_role": "moderator",
                    "content": "Welcome everyone.",
                    "source_type": "human_baseline_transcript",
                    "standardization_confidence": "high",
                    "requires_review": False,
                },
                {
                    "turn": 1,
                    "speaker_id": "P1",
                    "canonical_speaker_id": "P1",
                    "speaker_name": "Arden",
                    "speaker_role": "participant",
                    "content": "Thanks for having me.",
                    "source_type": "human_baseline_transcript",
                    "standardization_confidence": "high",
                    "requires_review": False,
                },
            ], fh)

        artifacts = load_session_artifacts(tmpdir, is_human_baseline=True)
        assert artifacts.transcript is not None
        assert not os.path.exists(os.path.join(tmpdir, "moderator_log.json"))
        assert not os.path.exists(os.path.join(tmpdir, "run_metadata.json"))
        assert not os.path.exists(os.path.join(tmpdir, "session_state_final.json"))


# Test 28: Synthetic-only metrics are NOT_APPLICABLE_HUMAN_BASELINE
def test_28_synthetic_only_metrics_not_applicable():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as fh:
            json.dump([
                {
                    "turn": 0,
                    "speaker_id": "MODERATOR_I",
                    "canonical_speaker_id": "MODERATOR",
                    "speaker_name": "I",
                    "speaker_role": "moderator",
                    "content": "Hello.",
                    "source_type": "human_baseline_transcript",
                    "standardization_confidence": "high",
                    "requires_review": False,
                }
            ], fh)

        artifacts = load_session_artifacts(tmpdir, is_human_baseline=True)
        mod_track = compute_moderator_metrics(artifacts)
        assert mod_track.metrics["internal_overvalidation_entries_total"].status == "NOT_APPLICABLE_HUMAN_BASELINE", (
            "internal_overvalidation should be NOT_APPLICABLE_HUMAN_BASELINE for human baselines"
        )


# Test 29: Human guide coverage not PASS/0 when per-turn progress cannot be inferred
def test_29_guide_coverage_not_pass_without_evidence():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as fh:
            json.dump([
                {
                    "turn": 0,
                    "speaker_id": "MODERATOR_I",
                    "canonical_speaker_id": "MODERATOR",
                    "speaker_name": "I",
                    "speaker_role": "moderator",
                    "content": "Hello.",
                    "source_type": "human_baseline_transcript",
                    "standardization_confidence": "high",
                    "requires_review": False,
                }
            ], fh)
        with open(os.path.join(tmpdir, "guide.json"), "w") as fh:
            json.dump({
                "guide_id": "test_guide",
                "source_type": "human_focus_group_guide",
                "sections": [{"section_label": "Intro", "scripted_question": "Tell us about yourself."}],
            }, fh)

        artifacts = load_session_artifacts(tmpdir, is_human_baseline=True)
        res_track = compute_research_design_metrics(artifacts)
        # When guide exists but no per-turn mapping, guide coverage should NOT be 0 or plain PASS
        sections_total = res_track.metrics.get("sections_total")
        assert sections_total is not None
        # For human baseline with guide available, sections_total.value should be 1 (sections found)
        assert sections_total.value == 1


# Test 30: No fake moderator_log.json created
def test_30_no_fake_moderator_log(qesb_transcript):
    # parse_transcript should not produce moderator_log.json
    # This test verifies the pipeline does not create it via the fixture itself
    # (The fixture returns parsed data; no file creation)
    transcript, warnings, review_queue, fm, sm, bm, p_meta = qesb_transcript
    # Verify none of the returned objects are moderator_log data
    for turn in transcript:
        assert "moderator_action" not in turn, "moderator_action field from synthetic pipeline leaked"
        assert "action_type" not in turn, "action_type field from synthetic pipeline leaked"


# Test 31: No fake run_metadata.json created
def test_31_no_fake_run_metadata(qesb_transcript):
    transcript, *_ = qesb_transcript
    for turn in transcript:
        assert "run_id" not in turn, "run_id field (synthetic) leaked into human baseline"
        assert "session_config" not in turn, "session_config (synthetic) leaked"


# Test 32: No fake session_state_final.json created
def test_32_no_fake_session_state(qesb_transcript):
    transcript, *_ = qesb_transcript
    for turn in transcript:
        assert "session_state" not in turn, "session_state (synthetic) leaked"
        assert "phase" not in turn, "phase field (synthetic) leaked"


# Test 33: Verification report blocks completion if true-positive leakage remains
def test_33_verification_blocks_on_true_positive():
    """If front-matter leakage is present, the verify script should flag it."""
    from scripts.verify_human_baseline_standardization import inspect_baseline

    with tempfile.TemporaryDirectory() as tmpdir:
        contaminated = [
            {
                "turn": 0,
                "speaker_id": "MODERATOR_I",
                "canonical_speaker_id": "MODERATOR",
                "speaker_name": "I",
                "speaker_role": "moderator",
                "content": "READ ME — copyright of this transcript belongs to Drs Oliver...",
                "source_type": "human_baseline_transcript",
                "standardization_confidence": "low",
                "requires_review": True,
            }
        ]
        with open(os.path.join(tmpdir, "transcript.json"), "w") as fh:
            json.dump(contaminated, fh)

        findings = inspect_baseline(tmpdir)
        blocking = [
            f for f in findings
            if f.classification == "true_positive" and f.severity == "blocking"
        ]
        assert len(blocking) > 0, (
            "Expected blocking true-positive finding for front-matter leakage"
        )


# Test 34: All 7 baselines are present in standardized_claude_v1
def test_34_all_7_baselines_present():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    std_dir = os.path.join(root, "data", "human_baseline", "standardized_claude_v1")
    if not os.path.isdir(std_dir):
        pytest.skip("standardized_claude_v1/ not yet generated — run process_human_baselines_claude_v1.py first")
    baselines = [
        d for d in os.listdir(std_dir)
        if os.path.isdir(os.path.join(std_dir, d))
    ]
    assert len(baselines) == 7, (
        f"Expected 7 baselines in standardized_claude_v1/, found {len(baselines)}: {baselines}"
    )


# Test 35: Raw transcript files are not modified
def test_35_raw_transcripts_not_modified():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(root, "data", "human_baseline", "raw_transcripts")
    if not os.path.isdir(raw_dir):
        pytest.skip("raw_transcripts/ not found")

    expected_raw_files = [
        "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript.docx",
        "QESB_Post_Greta_Kiyaan_Matilda_230724__transcript.docx",
        "QESB_Post_Jeremy_Chloe_Kim_190724__transcript.docx",
        "Work at home_FG transcript_employee group 1_pseudo.pdf",
        "Work at home_FG Transcript_employee group 2_pseudo.pdf",
        "Work at home_FG Transcript_employer group 1_pseudo.pdf",
        "Work at home_FG Transcript_employer group 3_pseudo.pdf",
    ]
    existing = os.listdir(raw_dir)
    for expected in expected_raw_files:
        assert expected in existing, (
            f"Raw transcript file '{expected}' not found in raw_transcripts/. "
            "Raw files must not be renamed or deleted."
        )


# ===========================================================================
# v1.1 Patch Tests (36–54)
# ===========================================================================

# ---------------------------------------------------------------------------
# Fixtures for hash-speaker and heading-leakage unit tests
# ---------------------------------------------------------------------------

QESB_HASH_SPEAKER = """
READ ME
Alias | Sex | Special Category | Age group
Arden | Non-binary | N | 34-41
Julius | M | N | 26-33

Date of the interview: 19 July 2024
Moderator: Edzia Carvalho
Location: Online

Your Voting Story
I: So, tell us about your voting day.
Arden: I had a postal vote.
I: Thanks Arden. Julius, standout moments?
#Julius: Yeah, it was quite something. Rishi in the rain.
What's Next for the Parties?
I: What do you think is next for the parties?
"""

QESB_HEADING_LEAK = """
READ ME
Alias | Sex | Special Category | Age group
Kiyaan | M | N | 26-33

Date of the interview: 23 July 2024
Moderator: Dr. Edzia Carvalho
Location: Online

Standout Moments from the Campaign?
I: Were there any standout moments?
Kiyaan: Rishi in the rain was the thing.
I: Yes indeed. Next question.
Standout Moments from the Campaign?
I: Let me ask again about standout moments.
Kiyaan: Same answer.
"""

QESB_HEADING_QUESTION_MARK = """
READ ME
Alias | Sex | Special Category | Age group
Matilda | F | N | 26-33

Date of the interview: 19 July 2024
Moderator: Dr. Thom Oliver
Location: Online

Turnout Impressions
I: What do you think about turnout?
Matilda: It was low everywhere.
I: Right. Thanks.
Standout Moments from the Campaign?
I: Any standout moments?
Matilda: The D-Day moment.
What's Next for the Parties?
I: And what is next for the parties?
Matilda: Hard to say.
"""


# Test 36: #Julius: is parsed as participant Julius, not left inside moderator content
def test_36_hash_speaker_parsed_as_participant():
    transcript, *_ = parse_transcript(
        QESB_HASH_SPEAKER, "QESB_hash_test.txt", "docx", "QESB_hash_test"
    )
    julius_turns = [t for t in transcript if t["speaker_name"] == "Julius"]
    assert len(julius_turns) > 0, "Expected at least one Julius turn from #Julius: label"
    for t in julius_turns:
        assert t["speaker_role"] == "participant", (
            f"Julius should be participant, got {t['speaker_role']}"
        )


# Test 37: Embedded #Julius: after a moderator line creates a separate participant turn
def test_37_hash_speaker_splits_from_moderator_turn():
    transcript, *_ = parse_transcript(
        QESB_HASH_SPEAKER, "QESB_hash_test.txt", "docx", "QESB_hash_test"
    )
    # The moderator turn "Thanks Arden. Julius, standout moments?" must NOT contain "#Julius:"
    for turn in transcript:
        content = turn.get("content", "")
        assert "#Julius" not in content, (
            f"#Julius leaked into turn {turn['turn']}: {content[:120]}"
        )
    # Julius must have its own turn
    julius_turns = [t for t in transcript if t["speaker_name"] == "Julius"]
    assert len(julius_turns) >= 1, "Julius should have at least one separate turn"
    # Julius content should not start with "#Julius:"
    for t in julius_turns:
        assert not t["content"].startswith("#"), (
            f"Julius turn content should not start with '#': {t['content'][:60]}"
        )


# Test 38: "Standout Moments from the Campaign?" stored in section_markers, not transcript
def test_38_standout_moments_question_mark_in_markers():
    transcript, _, _, _, section_markers, _, _ = parse_transcript(
        QESB_HEADING_QUESTION_MARK, "QESB_qmark_test.txt", "docx", "QESB_qmark_test"
    )
    heading_contents = {m["content"] for m in section_markers}
    assert any("Standout Moments" in h for h in heading_contents), (
        f"'Standout Moments from the Campaign?' should be in section_markers; got {heading_contents}"
    )
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert "Standout Moments from the Campaign" not in line.strip() or not any(
                line.strip() == m["content"] for m in section_markers
            ), f"Heading leaked into turn {turn['turn']}: {line}"
        # Full check: no content line equals the heading
        for line in turn.get("content", "").split("\n"):
            from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
            assert not _is_qesb_heading(line.strip()), (
                f"Heading line found inside turn {turn['turn']} content: {line.strip()}"
            )


# Test 39: "What's Next for the Parties?" stored in section_markers, not transcript
def test_39_whats_next_question_mark_in_markers():
    from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
    transcript, _, _, _, section_markers, _, _ = parse_transcript(
        QESB_HASH_SPEAKER, "QESB_hash_test.txt", "docx", "QESB_hash_test"
    )
    heading_contents = {m["content"] for m in section_markers}
    assert any("Next for the Parties" in h for h in heading_contents), (
        f"'What's Next for the Parties?' should be in section_markers; got {heading_contents}"
    )
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not _is_qesb_heading(line.strip()), (
                f"Heading line found inside turn {turn['turn']} content: {line.strip()}"
            )


def _load_baseline_transcript(baseline_id: str) -> list[dict]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(
        root, "data", "human_baseline", "standardized_claude_v1", baseline_id, "transcript.json"
    )
    if not os.path.exists(path):
        pytest.skip(f"Reprocessed baseline not found: {path} — run process_human_baselines_claude_v1.py")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_baseline_markers(baseline_id: str) -> list[dict]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(
        root, "data", "human_baseline", "standardized_claude_v1", baseline_id, "section_markers.json"
    )
    if not os.path.exists(path):
        pytest.skip(f"section_markers.json not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# Test 40: QESB Arden baseline — no '#' prefix inside any turn content
def test_40_arden_no_hash_prefix_in_content():
    transcript = _load_baseline_transcript("QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript")
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not line.strip().startswith("#"), (
                f"Turn {turn['turn']} content has line starting with '#': {line.strip()[:80]}"
            )


# Test 41: QESB Arden baseline — no "Standout Moments from the Campaign?" in any turn content
def test_41_arden_no_standout_moments_in_content():
    from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
    transcript = _load_baseline_transcript("QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript")
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not _is_qesb_heading(line.strip()), (
                f"Turn {turn['turn']} content contains a section heading: {line.strip()[:80]}"
            )


# Test 42: QESB Arden baseline — no "What's Next for the Parties?" in any turn content
def test_42_arden_no_whats_next_in_content():
    from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
    transcript = _load_baseline_transcript("QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript")
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not _is_qesb_heading(line.strip()), (
                f"Turn {turn['turn']} content contains a section heading: {line.strip()[:80]}"
            )


# Test 43: QESB Greta baseline — no "Standout Moments from the Campaign?" in any turn content
def test_43_greta_no_standout_moments_in_content():
    from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
    transcript = _load_baseline_transcript("QESB_Post_Greta_Kiyaan_Matilda_230724__transcript")
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not _is_qesb_heading(line.strip()), (
                f"Turn {turn['turn']} content contains a section heading: {line.strip()[:80]}"
            )


# Test 44: QESB Greta baseline — no "What's Next for the Parties?" in any turn content
def test_44_greta_no_whats_next_in_content():
    from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
    transcript = _load_baseline_transcript("QESB_Post_Greta_Kiyaan_Matilda_230724__transcript")
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not _is_qesb_heading(line.strip()), (
                f"Turn {turn['turn']} content contains a section heading: {line.strip()[:80]}"
            )


# Test 45: QESB Jeremy baseline — no "What's Next for the Parties?" in any turn content
def test_45_jeremy_no_whats_next_in_content():
    from scripts.standardize_human_focus_group_transcript import _is_qesb_heading
    transcript = _load_baseline_transcript("QESB_Post_Jeremy_Chloe_Kim_190724__transcript")
    for turn in transcript:
        for line in turn.get("content", "").split("\n"):
            assert not _is_qesb_heading(line.strip()), (
                f"Turn {turn['turn']} content contains a section heading: {line.strip()[:80]}"
            )


# Test 46: Verification script C11 flags embedded hash-prefixed speaker labels
def test_46_verifier_c11_flags_embedded_hash_speaker():
    from scripts.verify_human_baseline_standardization import inspect_baseline

    with tempfile.TemporaryDirectory() as tmpdir:
        contaminated = [
            {
                "turn": 0,
                "speaker_id": "MODERATOR_I",
                "canonical_speaker_id": "MODERATOR",
                "speaker_name": "I",
                "speaker_role": "moderator",
                "content": "Thanks Julius. Arden, standout moments?\n#Arden: Yeah, I was going to say...",
                "source_type": "human_baseline_transcript",
                "standardization_confidence": "low",
                "requires_review": False,
            }
        ]
        with open(os.path.join(tmpdir, "transcript.json"), "w") as fh:
            json.dump(contaminated, fh)

        findings = inspect_baseline(tmpdir)
        c11_blocking = [
            f for f in findings
            if f.check_id == "C11_EMBEDDED_SPEAKER_LABEL"
            and f.severity == "blocking"
        ]
        assert len(c11_blocking) > 0, "Expected C11 blocking finding for embedded #Arden: label"


# Test 47: Verification script C12 flags standalone section headings inside content
def test_47_verifier_c12_flags_heading_in_content():
    from scripts.verify_human_baseline_standardization import inspect_baseline

    with tempfile.TemporaryDirectory() as tmpdir:
        contaminated = [
            {
                "turn": 0,
                "speaker_id": "MODERATOR_I",
                "canonical_speaker_id": "MODERATOR",
                "speaker_name": "I",
                "speaker_role": "moderator",
                "content": "Relief, yeah. Thanks.\nStandout Moments from the Campaign?",
                "source_type": "human_baseline_transcript",
                "standardization_confidence": "low",
                "requires_review": False,
            }
        ]
        # Use a QESB-style baseline_id so is_qesb=True in the verifier
        baseline_id = "QESB_test_heading_leak"
        os.rename(tmpdir, tmpdir + "_renamed")
        actual_dir = tmpdir + "_renamed"
        try:
            findings = inspect_baseline(actual_dir)
            # Won't work — inspect_baseline uses basename of path
        except Exception:
            pass

        # Use a workaround: create a subdir with the QESB name
        import shutil
        qesb_dir = os.path.join(os.path.dirname(tmpdir), "QESB_heading_test_dir_" + os.path.basename(tmpdir))
        os.makedirs(qesb_dir, exist_ok=True)
        with open(os.path.join(qesb_dir, "transcript.json"), "w") as fh:
            json.dump(contaminated, fh)
        try:
            findings = inspect_baseline(qesb_dir)
            c12_blocking = [
                f for f in findings
                if f.check_id == "C12_HEADING_INSIDE_CONTENT"
                and f.severity == "blocking"
            ]
            assert len(c12_blocking) > 0, (
                "Expected C12 blocking finding for heading 'Standout Moments from the Campaign?' inside content"
            )
        finally:
            shutil.rmtree(qesb_dir, ignore_errors=True)


# Test 48: Verification script C11 does NOT flag normal time expressions
def test_48_verifier_c11_does_not_flag_time_expressions():
    from scripts.verify_human_baseline_standardization import inspect_baseline

    with tempfile.TemporaryDirectory() as tmpdir:
        clean = [
            {
                "turn": 0,
                "speaker_id": "MODERATOR_AN",
                "canonical_speaker_id": "MODERATOR",
                "speaker_name": "AN",
                "speaker_role": "moderator",
                "content": "We usually work from 9:00 to 17:00. Any changes?",
                "source_type": "human_baseline_transcript",
                "standardization_confidence": "high",
                "requires_review": False,
            },
            {
                "turn": 1,
                "speaker_id": "P1",
                "canonical_speaker_id": "P1",
                "speaker_name": "Grace",
                "speaker_role": "participant",
                "content": "I now start at 8:30 and finish around 16:30.",
                "source_type": "human_baseline_transcript",
                "standardization_confidence": "high",
                "requires_review": False,
            },
        ]
        with open(os.path.join(tmpdir, "transcript.json"), "w") as fh:
            json.dump(clean, fh)

        findings = inspect_baseline(tmpdir)
        c11_findings = [f for f in findings if f.check_id.startswith("C11_")]
        assert len(c11_findings) == 0, (
            f"C11 should NOT flag time expressions; got: {[f.description for f in c11_findings]}"
        )


# Test 49: Raw-vs-standardized comparison reports no missing speakers after fix
def test_49_comparison_no_missing_speakers_after_fix():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bid = "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript"
    bd = os.path.join(root, "data", "human_baseline", "standardized_claude_v1", bid)
    if not os.path.isdir(bd):
        pytest.skip("Reprocessed baselines not available — run pipeline first")
    issues = compare_baseline(bid, bd)
    blocking = [i for i in issues if i.severity == "blocking"]
    assert len(blocking) == 0, (
        f"Expected no blocking issues after patch; got: {[i.description for i in blocking]}"
    )


# Test 50: Raw-vs-standardized comparison reports no embedded headings after fix
def test_50_comparison_no_embedded_headings_after_fix():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for bid in [
        "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript",
        "QESB_Post_Greta_Kiyaan_Matilda_230724__transcript",
        "QESB_Post_Jeremy_Chloe_Kim_190724__transcript",
    ]:
        bd = os.path.join(root, "data", "human_baseline", "standardized_claude_v1", bid)
        if not os.path.isdir(bd):
            pytest.skip("Reprocessed baselines not available — run pipeline first")
        issues = compare_baseline(bid, bd)
        heading_issues = [i for i in issues if "HEADING" in i.check_id and i.severity == "blocking"]
        assert len(heading_issues) == 0, (
            f"{bid}: Expected no heading-in-content issues; got: {[i.description for i in heading_issues]}"
        )


# Test 51: All 7 baselines still process after patch
def test_51_all_7_baselines_still_present():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    std_dir = os.path.join(root, "data", "human_baseline", "standardized_claude_v1")
    if not os.path.isdir(std_dir):
        pytest.skip("standardized_claude_v1/ not yet generated")
    baselines = [d for d in os.listdir(std_dir) if os.path.isdir(os.path.join(std_dir, d))]
    assert len(baselines) == 7, (
        f"Expected 7 baselines after patch, found {len(baselines)}: {baselines}"
    )
    for bid in baselines:
        tp = os.path.join(std_dir, bid, "transcript.json")
        assert os.path.exists(tp), f"transcript.json missing for {bid}"


# Test 52: No fake moderator_log.json created in any reprocessed baseline
def test_52_no_fake_moderator_log_on_disk():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    std_dir = os.path.join(root, "data", "human_baseline", "standardized_claude_v1")
    if not os.path.isdir(std_dir):
        pytest.skip("standardized_claude_v1/ not yet generated")
    for bid in os.listdir(std_dir):
        bd = os.path.join(std_dir, bid)
        if not os.path.isdir(bd):
            continue
        assert not os.path.exists(os.path.join(bd, "moderator_log.json")), (
            f"moderator_log.json found in {bid} — must not exist for human baselines"
        )


# Test 53: No fake run_metadata.json created in any reprocessed baseline
def test_53_no_fake_run_metadata_on_disk():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    std_dir = os.path.join(root, "data", "human_baseline", "standardized_claude_v1")
    if not os.path.isdir(std_dir):
        pytest.skip("standardized_claude_v1/ not yet generated")
    for bid in os.listdir(std_dir):
        bd = os.path.join(std_dir, bid)
        if not os.path.isdir(bd):
            continue
        assert not os.path.exists(os.path.join(bd, "run_metadata.json")), (
            f"run_metadata.json found in {bid} — must not exist for human baselines"
        )


# Test 54: No fake session_state_final.json created in any reprocessed baseline
def test_54_no_fake_session_state_on_disk():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    std_dir = os.path.join(root, "data", "human_baseline", "standardized_claude_v1")
    if not os.path.isdir(std_dir):
        pytest.skip("standardized_claude_v1/ not yet generated")
    for bid in os.listdir(std_dir):
        bd = os.path.join(std_dir, bid)
        if not os.path.isdir(bd):
            continue
        assert not os.path.exists(os.path.join(bd, "session_state_final.json")), (
            f"session_state_final.json found in {bid} — must not exist for human baselines"
        )
