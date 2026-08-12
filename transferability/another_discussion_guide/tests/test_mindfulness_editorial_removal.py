"""
Focused tests for the DS05 editorial-preamble removal.

Proves that exactly one paragraph — the editorial preamble — is absent from the
analytical copy, and that every other character of the dialogue is unchanged.

    py -m pytest tests/test_mindfulness_editorial_removal.py -q
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.mindfulness_editorial_removal_record import (  # noqa: E402
    REMOVED_TEXT,
    STATUS,
    apply_removal,
    source_paragraphs,
    verify,
)

_STD = _ROOT / "data/datasets_transcripts/standardized/mindfulness/fg1"
_SOURCE = _ROOT / "data/datasets_transcripts/Mindfulness_raw transcript/Mindfulness_Focus Group Transcript.docx"


@pytest.fixture(scope="module")
def paragraphs() -> list[str]:
    return source_paragraphs()


@pytest.fixture(scope="module")
def record() -> dict:
    path = _STD / "editorial_removal_record.json"
    assert path.exists(), "run scripts/mindfulness_editorial_removal_record.py first"
    return json.loads(path.read_text(encoding="utf-8"))


# --- the source is never touched -------------------------------------------

def test_source_docx_hash_matches_record(record):
    actual = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
    assert actual == record["source_file_sha256"], "source .docx changed since the record was written"


def test_source_still_contains_the_preamble(paragraphs):
    """The removal is applied to the analytical copy only, never to the source."""
    assert any(p == REMOVED_TEXT for p in paragraphs)


# --- exactly one paragraph removed, nothing else altered --------------------

def test_removal_drops_exactly_one_paragraph(paragraphs):
    after, removed = apply_removal(paragraphs)
    assert len(removed) == 1
    assert len(after) == len(paragraphs) - 1


def test_every_other_paragraph_is_character_identical(paragraphs):
    after, removed = apply_removal(paragraphs)
    expected = [t for i, t in enumerate(paragraphs) if i not in set(removed)]
    assert after == expected


def test_verify_reports_no_problems(paragraphs):
    after, removed = apply_removal(paragraphs)
    assert verify(paragraphs, after, removed) == []


def test_record_verification_passed(record):
    assert record["verification"] == "PASS"
    assert record["verification_problems"] == []
    assert record["counts"]["paragraphs_otherwise_modified"] == 0
    assert record["counts"]["paragraphs_removed"] == 1


def test_record_carries_the_required_status(record):
    assert record["status"] == STATUS
    assert "RESEARCHER_CONFIRMED_NOT_PART_OF_SPEECH" in record["status"]
    assert record["hashes"]["concatenated_paragraph_text_sha256_before"] != \
        record["hashes"]["concatenated_paragraph_text_sha256_after"]


# --- the analytical artefacts are clean ------------------------------------

@pytest.mark.parametrize("filename", ["transcript.txt", "clean_transcript.txt"])
def test_analytical_text_files_do_not_contain_the_preamble(filename):
    text = (_STD / filename).read_text(encoding="utf-8")
    assert REMOVED_TEXT not in text


def test_transcript_json_does_not_contain_the_preamble():
    turns = json.loads((_STD / "transcript.json").read_text(encoding="utf-8"))
    assert all(REMOVED_TEXT not in t["content"] for t in turns)


def test_dialogue_content_survives_intact():
    """
    Every non-preamble source paragraph must still be locatable in the analytical
    transcript, so the removal cannot have silently taken dialogue with it.
    """
    turns = json.loads((_STD / "transcript.json").read_text(encoding="utf-8"))
    blob = "\n".join(t["content"] for t in turns)
    missing = []
    for paragraph in source_paragraphs():
        if paragraph == REMOVED_TEXT or paragraph == "Transcript":
            continue
        # Speaker-labelled paragraphs are stored with the label stripped.
        body = paragraph.split(":", 1)[1].strip() if ":" in paragraph[:30] else paragraph
        if body and body not in blob:
            missing.append(paragraph[:80])
    assert not missing, f"dialogue lost during standardization: {missing}"


# --- the retracted claim is gone -------------------------------------------

def test_baseline_metadata_retracts_the_ai_rewrite_claim():
    meta = json.loads((_STD / "baseline_metadata.json").read_text(encoding="utf-8"))
    flags = meta["SOURCE_INTEGRITY_FLAGS"]
    assert "ai_editing_artefact_detected" not in flags
    assert "ai_editing_extent" not in flags
    assert flags["editorial_preamble_removed"] is True
    assert flags["editorial_preamble_status"] == STATUS
    assert "RETRACTED_EARLIER_CLAIM" in flags
    assert "WITHDRAWN" in flags["RETRACTED_EARLIER_CLAIM"]
