"""
Tests 55–70: Documentation and comparison-script integrity patch.

Covers:
  - compare_raw_to_standardized_transcripts.py genuinely uses --raw-dir
  - Failed raw match emits CMP_RAW_FILE_NOT_FOUND warning
  - Fallback to --extracted-dir emits CMP_FALLBACK_EXTRACTED_TEXT warning
  - Successful raw extraction produces correct extraction_source
  - No raw_dir + no extracted_dir → extraction_source "unavailable"
  - Hardcoded EXTRACTED_DIR constant removed from script
  - --extracted-dir argument present in script
  - main() passes raw_dir to compare_baseline (not ignored)
  - No "Stage 7C" readiness claim in blocking warning print
  - Results doc total turns = 649
  - Results doc Arden turn count = 145
  - Results doc Arden section markers = 8
  - Results doc does NOT contain stale "648" count
  - Results doc does NOT contain stale "144 turns"
  - Results doc contains post-v1.1 doc+comparison correction section
  - Results doc Greta section markers = 7
"""

import os
import json
import tempfile
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DOC = os.path.join(
    ROOT,
    "docs", "testing",
    "STAGE7C0_CLAUDE_V1_HUMAN_BASELINE_STANDARDIZATION_RESULTS.md",
)
COMPARE_SCRIPT = os.path.join(
    ROOT, "scripts", "compare_raw_to_standardized_transcripts.py"
)
RAW_DIR = os.path.join(ROOT, "data", "human_baseline", "raw_transcripts")
EXTRACTED_DIR = os.path.join(ROOT, "data", "human_baseline", "extracted_text")
STD_DIR = os.path.join(ROOT, "data", "human_baseline", "standardized_claude_v1")
ARDEN_BID = "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript"
GRETA_BID = "QESB_Post_Greta_Kiyaan_Matilda_230724__transcript"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _std_dir(bid: str) -> str:
    return os.path.join(STD_DIR, bid)


# ---------------------------------------------------------------------------
# Test 55: compare_baseline() with valid raw_dir uses it (extraction_source = raw_docx)
# ---------------------------------------------------------------------------
def test_55_compare_baseline_uses_raw_dir_for_docx():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline

    bd = _std_dir(ARDEN_BID)
    if not os.path.isdir(bd):
        pytest.skip("Arden baseline not available")
    if not os.path.isdir(RAW_DIR):
        pytest.skip("raw_transcripts/ not available")

    issues = compare_baseline(ARDEN_BID, bd, raw_dir=RAW_DIR)
    src = next(
        (i.evidence for i in issues if i.check_id == "CMP_EXTRACTION_SOURCE"),
        None,
    )
    assert src == "raw_docx", (
        f"Expected extraction_source='raw_docx' when --raw-dir has DOCX; got '{src}'"
    )


# ---------------------------------------------------------------------------
# Test 56: compare_baseline() with raw_dir missing the file emits CMP_RAW_FILE_NOT_FOUND
# ---------------------------------------------------------------------------
def test_56_compare_baseline_missing_raw_emits_warning():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline

    bd = _std_dir(ARDEN_BID)
    if not os.path.isdir(bd):
        pytest.skip("Arden baseline not available")

    with tempfile.TemporaryDirectory() as empty_dir:
        issues = compare_baseline(ARDEN_BID, bd, raw_dir=empty_dir)
    check_ids = [i.check_id for i in issues]
    assert "CMP_RAW_FILE_NOT_FOUND" in check_ids, (
        f"Expected CMP_RAW_FILE_NOT_FOUND when raw file absent; got: {check_ids}"
    )


# ---------------------------------------------------------------------------
# Test 57: compare_baseline() falls back to extracted_dir with CMP_FALLBACK_EXTRACTED_TEXT
# ---------------------------------------------------------------------------
def test_57_compare_baseline_fallback_emits_warning():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline

    bd = _std_dir(ARDEN_BID)
    if not os.path.isdir(bd):
        pytest.skip("Arden baseline not available")
    if not os.path.isdir(EXTRACTED_DIR):
        pytest.skip("extracted_text/ not available")

    with tempfile.TemporaryDirectory() as empty_raw:
        issues = compare_baseline(
            ARDEN_BID, bd,
            raw_dir=empty_raw,
            extracted_dir=EXTRACTED_DIR,
        )

    check_ids = [i.check_id for i in issues]
    assert "CMP_RAW_FILE_NOT_FOUND" in check_ids, (
        "Expected CMP_RAW_FILE_NOT_FOUND when raw dir is empty"
    )
    assert "CMP_FALLBACK_EXTRACTED_TEXT" in check_ids, (
        f"Expected CMP_FALLBACK_EXTRACTED_TEXT when falling back; got: {check_ids}"
    )


# ---------------------------------------------------------------------------
# Test 58: compare_baseline() with valid raw_dir does NOT emit CMP_FALLBACK_EXTRACTED_TEXT
# ---------------------------------------------------------------------------
def test_58_compare_baseline_no_fallback_warning_when_raw_succeeds():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline

    bd = _std_dir(ARDEN_BID)
    if not os.path.isdir(bd):
        pytest.skip("Arden baseline not available")
    if not os.path.isdir(RAW_DIR):
        pytest.skip("raw_transcripts/ not available")

    issues = compare_baseline(ARDEN_BID, bd, raw_dir=RAW_DIR)
    fallback = [i for i in issues if i.check_id == "CMP_FALLBACK_EXTRACTED_TEXT"]
    assert len(fallback) == 0, (
        f"CMP_FALLBACK_EXTRACTED_TEXT should not appear when raw extraction succeeds; "
        f"got: {[i.description for i in fallback]}"
    )


# ---------------------------------------------------------------------------
# Test 59: No raw_dir and no extracted_dir → extraction_source = "unavailable"
# ---------------------------------------------------------------------------
def test_59_no_raw_no_extracted_gives_unavailable():
    from scripts.compare_raw_to_standardized_transcripts import compare_baseline

    bd = _std_dir(ARDEN_BID)
    if not os.path.isdir(bd):
        pytest.skip("Arden baseline not available")

    issues = compare_baseline(ARDEN_BID, bd, raw_dir=None, extracted_dir=None)
    src = next(
        (i.evidence for i in issues if i.check_id == "CMP_EXTRACTION_SOURCE"),
        None,
    )
    assert src == "unavailable", (
        f"Expected extraction_source='unavailable' when no dirs given; got '{src}'"
    )


# ---------------------------------------------------------------------------
# Test 60: Script does NOT define module-level EXTRACTED_DIR constant
# ---------------------------------------------------------------------------
def test_60_script_has_no_hardcoded_extracted_dir_constant():
    with open(COMPARE_SCRIPT, encoding="utf-8") as fh:
        src = fh.read()
    assert "EXTRACTED_DIR" not in src, (
        "compare_raw_to_standardized_transcripts.py must not contain EXTRACTED_DIR constant"
    )


# ---------------------------------------------------------------------------
# Test 61: Script accepts --extracted-dir as a CLI argument
# ---------------------------------------------------------------------------
def test_61_script_has_extracted_dir_argument():
    with open(COMPARE_SCRIPT, encoding="utf-8") as fh:
        src = fh.read()
    assert "--extracted-dir" in src, (
        "compare_raw_to_standardized_transcripts.py must expose --extracted-dir argument"
    )


# ---------------------------------------------------------------------------
# Test 62: main() passes raw_dir to compare_baseline (not ignored)
# ---------------------------------------------------------------------------
def test_62_main_passes_raw_dir_to_compare_baseline():
    with open(COMPARE_SCRIPT, encoding="utf-8") as fh:
        src = fh.read()
    assert "raw_dir=args.raw_dir" in src, (
        "main() must pass raw_dir=args.raw_dir to compare_baseline()"
    )


# ---------------------------------------------------------------------------
# Test 63: Blocking warning print does not contain "Stage 7C"
# ---------------------------------------------------------------------------
def test_63_no_stage_7c_in_blocking_warning():
    with open(COMPARE_SCRIPT, encoding="utf-8") as fh:
        src = fh.read()
    # Find all print() calls that reference blocking
    import re
    blocking_prints = re.findall(r'print\([^)]*[Bb]locking[^)]*\)', src, re.DOTALL)
    for bp in blocking_prints:
        assert "Stage 7C" not in bp, (
            f"Blocking warning print must not reference 'Stage 7C'; found: {bp[:120]}"
        )


# ---------------------------------------------------------------------------
# Test 64: Results doc total turns = 649
# ---------------------------------------------------------------------------
def test_64_results_doc_total_turns_649():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    assert "649" in text, (
        "Results doc must contain '649' (total turns across all baselines)"
    )


# ---------------------------------------------------------------------------
# Test 65: Results doc Arden turn count = 145 (not 144)
# ---------------------------------------------------------------------------
def test_65_results_doc_arden_turns_145():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    import re
    # Must contain "145" in context of Arden or turns
    assert re.search(r"Arden.*?145|145.*?turn", text, re.IGNORECASE | re.DOTALL), (
        "Results doc must reference 145 turns for Arden"
    )


# ---------------------------------------------------------------------------
# Test 66: Results doc Arden section markers = 8
# ---------------------------------------------------------------------------
def test_66_results_doc_arden_section_markers_8():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    import re
    # QESB Arden row in baseline summary table has | 8 |
    assert re.search(r"Arden[^\n]*\|\s*8\s*\|", text), (
        "Results doc must show 8 section markers for Arden in baseline table"
    )


# ---------------------------------------------------------------------------
# Test 67: Results doc does NOT contain stale "648" count
# ---------------------------------------------------------------------------
def test_67_results_doc_no_stale_648():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    import re
    # "648" should not appear as a standalone turn count (not part of a year or path)
    stale = re.findall(r'\b648\b', text)
    assert len(stale) == 0, (
        f"Results doc contains stale '648' count at {len(stale)} location(s)"
    )


# ---------------------------------------------------------------------------
# Test 68: Results doc does NOT contain stale "144 turns"
# ---------------------------------------------------------------------------
def test_68_results_doc_no_stale_144_turns():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    import re
    stale = re.findall(r'144\s+turns', text, re.IGNORECASE)
    assert len(stale) == 0, (
        f"Results doc contains stale '144 turns' at {len(stale)} location(s)"
    )


# ---------------------------------------------------------------------------
# Test 69: Results doc contains "Post-v1.1 documentation" correction section
# ---------------------------------------------------------------------------
def test_69_results_doc_has_integrity_correction_section():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    assert "Post-v1.1 Documentation and Comparison-Script Integrity Correction" in text, (
        "Results doc must contain 'Post-v1.1 Documentation and Comparison-Script "
        "Integrity Correction' section"
    )


# ---------------------------------------------------------------------------
# Test 70: Results doc Greta section markers = 7
# ---------------------------------------------------------------------------
def test_70_results_doc_greta_section_markers_7():
    if not os.path.isfile(RESULTS_DOC):
        pytest.skip("Results doc not found")
    with open(RESULTS_DOC, encoding="utf-8") as fh:
        text = fh.read()
    import re
    assert re.search(r"Greta[^\n]*\|\s*7\s*\|", text), (
        "Results doc must show 7 section markers for Greta in baseline table"
    )
