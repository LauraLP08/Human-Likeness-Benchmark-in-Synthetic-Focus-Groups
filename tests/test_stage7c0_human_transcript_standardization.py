import os
import json
import tempfile
import pytest
from scripts.extract_focus_group_transcript_text import extract_text
from scripts.standardize_human_focus_group_transcript import parse_transcript
from scripts.standardize_focus_group_guide import parse_guide
from assessment.loader import load_session_artifacts
from assessment.metrics import compute_moderator_metrics, compute_research_design_metrics

def test_legacy_doc_flagged():
    text, meta = extract_text("test.doc")
    assert meta["legacy_doc_conversion_required"] is True
    assert text == ""

def test_parse_transcript_speaker_mapping_and_paragraphs():
    text = """
Some text before any speaker.
Moderator: Hello everyone.
Welcome to the group.

Participant 1: Hi there.
I agree.

P2: Me too.

[Unknown Name]: I don't know.

Some unlabeled text.
    """
    transcript, warnings, review_queue, fm, sm, bm, p_meta = parse_transcript(text, "test.pdf", "pdf", "base1")
    
    assert len(transcript) == 4
    assert transcript[0]["speaker_id"] == "MODERATOR"
    assert "Welcome to the group." in transcript[0]["content"]
    assert transcript[1]["speaker_id"] == "P1"
    assert "I agree." in transcript[1]["content"]
    assert transcript[2]["speaker_id"] == "P2"
    assert transcript[3]["speaker_id"] == "P3"
    assert "Some unlabeled text." in transcript[3]["content"]

def test_parse_guide_sections():
    text = """
1. Introduction
Welcome to the group.
- Please sign in

2. Main Discussion
What do you think?
- Why?
    """
    guide, review_queue = parse_guide(text, "guide.pdf", "pdf", "base1")
    assert len(guide["sections"]) == 2
    assert guide["sections"][0]["section_phase"] == "intro"
    assert "Welcome" in guide["sections"][0]["scripted_question"]
    assert "Please sign in" in guide["sections"][0]["probes"]

def test_human_baseline_assessment_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as f:
            json.dump([
                {"turn": 0, "speaker_id": "MODERATOR", "content": "hi", "source_type": "human_baseline_transcript"}
            ], f)
        
        artifacts = load_session_artifacts(tmpdir, is_human_baseline=True)
        assert artifacts.transcript is not None
        assert not os.path.exists(os.path.join(tmpdir, "moderator_log.json"))
        assert not os.path.exists(os.path.join(tmpdir, "run_metadata.json"))
        assert not os.path.exists(os.path.join(tmpdir, "session_state_final.json"))
        
        mod_track = compute_moderator_metrics(artifacts)
        assert mod_track.metrics["internal_overvalidation_entries_total"].status == "NOT_APPLICABLE_HUMAN_BASELINE"
        
        res_track = compute_research_design_metrics(artifacts)
        assert res_track.metrics["sections_total"].status == "NOT_APPLICABLE_NO_GUIDE"

def test_human_baseline_guide_assessment():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as f:
            json.dump([
                {"turn": 0, "speaker_id": "MODERATOR", "content": "hi", "source_type": "human_baseline_transcript"}
            ], f)
        with open(os.path.join(tmpdir, "guide.json"), "w") as f:
            json.dump({"sections": [{"section_label": "Intro"}]}, f)
            
        artifacts = load_session_artifacts(tmpdir, is_human_baseline=True)
        res_track = compute_research_design_metrics(artifacts)
        assert res_track.metrics["sections_total"].value == 1

