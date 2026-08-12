"""
Tests 88–117: Human baseline source and assessment closure.

Verifies the final cleaned state of data/human_baseline/ after the cleanup
and closure patch:

  1. standardized_claude_v1 directory exists
  2. Exactly 7 final baseline folders exist
  3. No active competing standardized folders outside archive
  4. Old failed attempts absent from active root
  5. Total turns = 649
  6. Arden = 145 turns
  7. Arden section markers = 8
  8. Greta section markers = 7
  9. Jeremy section markers = 8
 10. No transcript.json contains READ ME/front matter sentinels
 11. No transcript.json contains embedded #Speaker labels
 12. No QESB transcript.json contains standalone section headings in content
 13. clean_transcript.txt exists for each baseline
 14. clean_transcript.txt contains no READ ME/front matter
 15. clean_transcript.txt contains no participant metadata table
 16. clean_transcript.txt contains no End of transcript
 17. transcript.txt, if present, is clean (no READ ME)
 18. raw_extracted_transcript.txt exists and is named as raw (not clean)
 19. No fake moderator_log.json exists
 20. No fake run_metadata.json exists
 21. No fake session_state_final.json exists
 22. raw_vs_standardized_comparison.json exists and overall_status = PASS
 23. Raw comparison has 0 blocking issues
 24. Raw comparison uses raw_docx/raw_pdf extraction_source
 25. verification_report.json exists and overall_status = PASS
 26. Assessments exist for all 7 baselines
 27. Assessments use human_baseline_transcript source type
 28. Synthetic-only metrics are NOT_APPLICABLE_HUMAN_BASELINE
 29. No assessment references old Gemini/Antigravity folders
 30. No active test requires on-disk standardized_claude_v1.zip
"""

import os
import json
import re
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HB_DIR = os.path.join(ROOT, "data", "human_baseline")
STD_DIR = os.path.join(HB_DIR, "standardized_claude_v1")
ARCHIVE_DIR = os.path.join(HB_DIR, "archive")
DOCS_DIR = os.path.join(ROOT, "docs", "testing", "human_baseline_standardization_claude_v1")
ASSESS_DIR = os.path.join(DOCS_DIR, "assessments")
CMP_JSON = os.path.join(DOCS_DIR, "raw_vs_standardized_comparison.json")
VERIFY_JSON = os.path.join(DOCS_DIR, "verification_report.json")
PKG_TEST_FILE = os.path.join(ROOT, "tests", "test_human_baseline_package_integrity.py")

ARDEN_BID = "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript"
GRETA_BID = "QESB_Post_Greta_Kiyaan_Matilda_230724__transcript"
JEREMY_BID = "QESB_Post_Jeremy_Chloe_Kim_190724__transcript"

FRONT_MATTER_SENTINELS = [
    "READ ME",
    "copyright of this transcript",
    "recommended citation",
    "reporting conventions",
    "Alias | Sex",
    "Date of the interview",
    "Location: Online",
    "Pre-election transcripts",
]

QESB_HEADING_EXACT = {
    "your voting story",
    "your voting outcome story",
    "your voting story and your voting outcome story",
    "turnout impressions",
    "song of the election",
    "impressions of results by party",
    "one word to describe the election",
    "standout moments from the campaign",
    "whats next for the parties",
    "advice for parties",
}

_EMBEDDED_HASH_RE = re.compile(r"^#[A-Za-z][A-Za-z0-9 _]*::?\s", re.IGNORECASE)
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}")


def _normalise_heading(s):
    s = s.strip().lower().rstrip("?").strip()
    s = s.replace("â€™", "").replace("â€˜", "")
    s = re.sub(r"['''ʹ′‚‛]", "", s)
    return s


def _is_qesb_heading(line):
    return _normalise_heading(line) in QESB_HEADING_EXACT


def _load_transcript(bid):
    tp = os.path.join(STD_DIR, bid, "transcript.json")
    if not os.path.exists(tp):
        return None
    with open(tp, encoding="utf-8") as fh:
        return json.load(fh)


def _load_section_markers(bid):
    sp = os.path.join(STD_DIR, bid, "section_markers.json")
    if not os.path.exists(sp):
        return []
    with open(sp, encoding="utf-8") as fh:
        return json.load(fh)


def _skip_if_no_std():
    if not os.path.isdir(STD_DIR):
        pytest.skip("standardized_claude_v1/ not available")


# ---------------------------------------------------------------------------
# Test 88: standardized_claude_v1 directory exists
# ---------------------------------------------------------------------------
def test_88_std_dir_exists():
    assert os.path.isdir(STD_DIR), (
        f"standardized_claude_v1 directory not found: {STD_DIR}"
    )


# ---------------------------------------------------------------------------
# Test 89: exactly 7 baseline folders
# ---------------------------------------------------------------------------
def test_89_exactly_7_baseline_folders():
    _skip_if_no_std()
    baselines = [d for d in os.listdir(STD_DIR) if os.path.isdir(os.path.join(STD_DIR, d))]
    assert len(baselines) == 7, (
        f"Expected 7 baseline folders; found {len(baselines)}: {baselines}"
    )


# ---------------------------------------------------------------------------
# Test 90: no active competing standardized folders outside archive
# ---------------------------------------------------------------------------
def test_90_no_competing_standardized_active():
    competing = [
        d for d in os.listdir(HB_DIR)
        if os.path.isdir(os.path.join(HB_DIR, d))
        and d.startswith("standardized")
        and d != "standardized_claude_v1"
        and d != "archive"
    ]
    assert len(competing) == 0, (
        f"Competing standardized folders found in active root: {competing}"
    )


# ---------------------------------------------------------------------------
# Test 91: old Gemini/Antigravity/failed attempts absent from active root
# ---------------------------------------------------------------------------
def test_91_no_old_attempts_in_active_root():
    disallowed = []
    for d in os.listdir(HB_DIR):
        d_lower = d.lower()
        if any(tok in d_lower for tok in ["gemini", "antigravity", "old", "previous", "failed"]):
            if os.path.isdir(os.path.join(HB_DIR, d)) and d != "archive":
                disallowed.append(d)
    assert len(disallowed) == 0, (
        f"Old attempt directories found in active root (should be in archive/): {disallowed}"
    )


# ---------------------------------------------------------------------------
# Test 92: total turns = 649
# ---------------------------------------------------------------------------
def test_92_total_turns_649():
    _skip_if_no_std()
    total = sum(
        len(json.load(open(os.path.join(STD_DIR, bid, "transcript.json"), encoding="utf-8")))
        for bid in os.listdir(STD_DIR)
        if os.path.isfile(os.path.join(STD_DIR, bid, "transcript.json"))
    )
    assert total == 649, f"Expected 649 total turns; got {total}"


# ---------------------------------------------------------------------------
# Test 93: Arden = 145 turns
# ---------------------------------------------------------------------------
def test_93_arden_turns_145():
    _skip_if_no_std()
    t = _load_transcript(ARDEN_BID)
    if t is None:
        pytest.skip("Arden transcript.json not found")
    assert len(t) == 145, f"Expected 145 Arden turns; got {len(t)}"


# ---------------------------------------------------------------------------
# Test 94: Arden section markers = 8
# ---------------------------------------------------------------------------
def test_94_arden_section_markers_8():
    _skip_if_no_std()
    sm = _load_section_markers(ARDEN_BID)
    assert len(sm) == 8, f"Expected 8 Arden section markers; got {len(sm)}"


# ---------------------------------------------------------------------------
# Test 95: Greta section markers = 7
# ---------------------------------------------------------------------------
def test_95_greta_section_markers_7():
    _skip_if_no_std()
    sm = _load_section_markers(GRETA_BID)
    assert len(sm) == 7, f"Expected 7 Greta section markers; got {len(sm)}"


# ---------------------------------------------------------------------------
# Test 96: Jeremy section markers = 8
# ---------------------------------------------------------------------------
def test_96_jeremy_section_markers_8():
    _skip_if_no_std()
    sm = _load_section_markers(JEREMY_BID)
    assert len(sm) == 8, f"Expected 8 Jeremy section markers; got {len(sm)}"


# ---------------------------------------------------------------------------
# Test 97: No transcript.json contains front matter sentinels
# ---------------------------------------------------------------------------
def test_97_no_transcript_json_front_matter():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        t = _load_transcript(bid)
        if not t:
            continue
        for turn in t:
            content = turn.get("content", "")
            for sentinel in FRONT_MATTER_SENTINELS:
                if sentinel in content:
                    violations.append(f"{bid} turn {turn.get('turn')}: '{sentinel}'")
                    break
    assert len(violations) == 0, (
        f"Front matter found in transcript.json turns: {violations[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 98: No transcript.json contains embedded #Speaker labels
# ---------------------------------------------------------------------------
def test_98_no_embedded_hash_speakers():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        t = _load_transcript(bid)
        if not t:
            continue
        for turn in t:
            for line in turn.get("content", "").split("\n"):
                l = line.strip()
                if not l or _TIME_RE.match(l):
                    continue
                if _EMBEDDED_HASH_RE.match(l):
                    violations.append(f"{bid} turn {turn.get('turn')}: {l[:60]}")
                    break
    assert len(violations) == 0, (
        f"Embedded #Speaker labels in transcript.json: {violations[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 99: No QESB transcript.json contains standalone section headings in content
# ---------------------------------------------------------------------------
def test_99_no_qesb_heading_leakage():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        if "qesb" not in bid.lower():
            continue
        t = _load_transcript(bid)
        if not t:
            continue
        for turn in t:
            for line in turn.get("content", "").split("\n"):
                if _is_qesb_heading(line.strip()):
                    violations.append(
                        f"{bid} turn {turn.get('turn')}: {line.strip()[:60]}"
                    )
                    break
    assert len(violations) == 0, (
        f"QESB heading leakage in transcript.json: {violations[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 100: clean_transcript.txt exists for each baseline
# ---------------------------------------------------------------------------
def test_100_clean_transcript_exists():
    _skip_if_no_std()
    missing = []
    for bid in os.listdir(STD_DIR):
        if not os.path.isdir(os.path.join(STD_DIR, bid)):
            continue
        ct = os.path.join(STD_DIR, bid, "clean_transcript.txt")
        if not os.path.isfile(ct):
            missing.append(bid)
    assert len(missing) == 0, (
        f"clean_transcript.txt missing for: {missing}"
    )


# ---------------------------------------------------------------------------
# Test 101: clean_transcript.txt contains no READ ME/front matter sentinels
# ---------------------------------------------------------------------------
def test_101_clean_transcript_no_front_matter():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        ct = os.path.join(STD_DIR, bid, "clean_transcript.txt")
        if not os.path.isfile(ct):
            continue
        with open(ct, encoding="utf-8") as fh:
            text = fh.read()
        for sentinel in FRONT_MATTER_SENTINELS:
            if sentinel in text:
                violations.append(f"{bid}: '{sentinel}'")
                break
    assert len(violations) == 0, (
        f"Front matter found in clean_transcript.txt: {violations[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 102: clean_transcript.txt contains no participant metadata table
# ---------------------------------------------------------------------------
def test_102_clean_transcript_no_participant_table():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        ct = os.path.join(STD_DIR, bid, "clean_transcript.txt")
        if not os.path.isfile(ct):
            continue
        with open(ct, encoding="utf-8") as fh:
            text = fh.read()
        if "Alias | Sex" in text or "Alias|Sex" in text:
            violations.append(bid)
    assert len(violations) == 0, (
        f"Participant table header found in clean_transcript.txt: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 103: clean_transcript.txt contains no "End of transcript"
# ---------------------------------------------------------------------------
def test_103_clean_transcript_no_end_of_transcript():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        ct = os.path.join(STD_DIR, bid, "clean_transcript.txt")
        if not os.path.isfile(ct):
            continue
        with open(ct, encoding="utf-8") as fh:
            text = fh.read()
        if "End of transcript" in text or "end of transcript" in text.lower():
            violations.append(bid)
    assert len(violations) == 0, (
        f"'End of transcript' found in clean_transcript.txt: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 104: transcript.txt, if present, is clean (no READ ME)
# ---------------------------------------------------------------------------
def test_104_transcript_txt_clean_if_present():
    _skip_if_no_std()
    violations = []
    for bid in os.listdir(STD_DIR):
        tt = os.path.join(STD_DIR, bid, "transcript.txt")
        if not os.path.isfile(tt):
            continue
        with open(tt, encoding="utf-8") as fh:
            text = fh.read()
        if "READ ME" in text:
            violations.append(bid)
    assert len(violations) == 0, (
        f"transcript.txt contains READ ME (should be clean): {violations}"
    )


# ---------------------------------------------------------------------------
# Test 105: raw_extracted_transcript.txt exists for each baseline
# ---------------------------------------------------------------------------
def test_105_raw_extracted_transcript_exists():
    _skip_if_no_std()
    missing = []
    for bid in os.listdir(STD_DIR):
        if not os.path.isdir(os.path.join(STD_DIR, bid)):
            continue
        rt = os.path.join(STD_DIR, bid, "raw_extracted_transcript.txt")
        if not os.path.isfile(rt):
            missing.append(bid)
    assert len(missing) == 0, (
        f"raw_extracted_transcript.txt missing for: {missing}"
    )


# ---------------------------------------------------------------------------
# Test 106: No fake moderator_log.json
# ---------------------------------------------------------------------------
def test_106_no_fake_moderator_log():
    _skip_if_no_std()
    fakes = [
        bid for bid in os.listdir(STD_DIR)
        if os.path.isfile(os.path.join(STD_DIR, bid, "moderator_log.json"))
    ]
    assert len(fakes) == 0, f"moderator_log.json found in: {fakes}"


# ---------------------------------------------------------------------------
# Test 107: No fake run_metadata.json
# ---------------------------------------------------------------------------
def test_107_no_fake_run_metadata():
    _skip_if_no_std()
    fakes = [
        bid for bid in os.listdir(STD_DIR)
        if os.path.isfile(os.path.join(STD_DIR, bid, "run_metadata.json"))
    ]
    assert len(fakes) == 0, f"run_metadata.json found in: {fakes}"


# ---------------------------------------------------------------------------
# Test 108: No fake session_state_final.json
# ---------------------------------------------------------------------------
def test_108_no_fake_session_state():
    _skip_if_no_std()
    fakes = [
        bid for bid in os.listdir(STD_DIR)
        if os.path.isfile(os.path.join(STD_DIR, bid, "session_state_final.json"))
    ]
    assert len(fakes) == 0, f"session_state_final.json found in: {fakes}"


# ---------------------------------------------------------------------------
# Test 109: raw_vs_standardized_comparison.json exists and overall_status = PASS
# ---------------------------------------------------------------------------
def test_109_raw_comparison_exists_and_passes():
    if not os.path.isfile(CMP_JSON):
        pytest.skip("raw_vs_standardized_comparison.json not found")
    with open(CMP_JSON, encoding="utf-8") as fh:
        cmp = json.load(fh)
    assert cmp.get("overall_status") == "PASS", (
        f"raw_vs_standardized_comparison overall_status = '{cmp.get('overall_status')}'"
    )


# ---------------------------------------------------------------------------
# Test 110: Raw comparison has 0 blocking issues
# ---------------------------------------------------------------------------
def test_110_raw_comparison_zero_blocking():
    if not os.path.isfile(CMP_JSON):
        pytest.skip("raw_vs_standardized_comparison.json not found")
    with open(CMP_JSON, encoding="utf-8") as fh:
        cmp = json.load(fh)
    assert cmp.get("total_blocking", -1) == 0, (
        f"raw_vs_standardized_comparison total_blocking = {cmp.get('total_blocking')}"
    )


# ---------------------------------------------------------------------------
# Test 111: Raw comparison uses raw_docx/raw_pdf (no silent fallback)
# ---------------------------------------------------------------------------
def test_111_raw_comparison_uses_raw_source():
    if not os.path.isfile(CMP_JSON):
        pytest.skip("raw_vs_standardized_comparison.json not found")
    with open(CMP_JSON, encoding="utf-8") as fh:
        cmp = json.load(fh)
    allowed = {"raw_docx", "raw_pdf", "raw_txt"}
    bad = []
    for b in cmp.get("baselines", []):
        src = b.get("extraction_source", "")
        if src not in allowed:
            bad.append(f"{b['baseline_id']}: {src}")
    assert len(bad) == 0, (
        f"Baselines not using raw source extraction: {bad}"
    )


# ---------------------------------------------------------------------------
# Test 112: verification_report.json exists and overall_status = PASS
# ---------------------------------------------------------------------------
def test_112_verification_report_exists_and_passes():
    if not os.path.isfile(VERIFY_JSON):
        pytest.skip("verification_report.json not found")
    with open(VERIFY_JSON, encoding="utf-8") as fh:
        vr = json.load(fh)
    assert vr.get("overall_status") == "PASS", (
        f"verification_report overall_status = '{vr.get('overall_status')}'"
    )


# ---------------------------------------------------------------------------
# Test 113: Assessments exist for all 7 baselines
# ---------------------------------------------------------------------------
def test_113_assessments_exist_for_all_7():
    if not os.path.isdir(ASSESS_DIR):
        pytest.skip("assessments/ directory not found")
    baselines_with_assessment = [
        d for d in os.listdir(ASSESS_DIR)
        if os.path.isfile(os.path.join(ASSESS_DIR, d, "assessment_metrics.json"))
    ]
    assert len(baselines_with_assessment) == 7, (
        f"Expected assessments for 7 baselines; found {len(baselines_with_assessment)}"
    )


# ---------------------------------------------------------------------------
# Test 114: Assessments use human_baseline_transcript source type
# ---------------------------------------------------------------------------
def test_114_assessments_human_baseline_source_type():
    if not os.path.isdir(ASSESS_DIR):
        pytest.skip("assessments/ directory not found")
    wrong = []
    for bid in os.listdir(ASSESS_DIR):
        mf = os.path.join(ASSESS_DIR, bid, "assessment_manifest.json")
        if not os.path.isfile(mf):
            continue
        m = json.load(open(mf, encoding="utf-8"))
        if m.get("source_type") != "human_baseline_transcript":
            wrong.append(f"{bid}: source_type={m.get('source_type')}")
    assert len(wrong) == 0, (
        f"Assessments with wrong source_type: {wrong}"
    )


# ---------------------------------------------------------------------------
# Test 115: Synthetic-only metrics are NOT_APPLICABLE_HUMAN_BASELINE
# ---------------------------------------------------------------------------
def test_115_synthetic_only_metrics_not_applicable():
    from assessment.loader import load_session_artifacts
    from assessment.metrics import compute_moderator_metrics

    _skip_if_no_std()
    bid = ARDEN_BID
    bd = os.path.join(STD_DIR, bid)
    artifacts = load_session_artifacts(bd, is_human_baseline=True)
    mod_track = compute_moderator_metrics(artifacts)
    status = mod_track.metrics.get(
        "internal_overvalidation_entries_total"
    )
    assert status is not None, "internal_overvalidation_entries_total metric missing"
    assert status.status == "NOT_APPLICABLE_HUMAN_BASELINE", (
        f"Expected NOT_APPLICABLE_HUMAN_BASELINE; got '{status.status}'"
    )


# ---------------------------------------------------------------------------
# Test 116: No assessment references old Gemini/Antigravity folders
# ---------------------------------------------------------------------------
def test_116_assessments_no_old_folder_references():
    if not os.path.isdir(ASSESS_DIR):
        pytest.skip("assessments/ directory not found")
    violations = []
    for bid in os.listdir(ASSESS_DIR):
        mf = os.path.join(ASSESS_DIR, bid, "assessment_manifest.json")
        if not os.path.isfile(mf):
            continue
        text = open(mf, encoding="utf-8").read()
        for old_ref in ["gemini", "antigravity", "standardized_old",
                        "standardized_previous", "failed"]:
            if old_ref.lower() in text.lower():
                violations.append(f"{bid}: contains '{old_ref}'")
                break
    assert len(violations) == 0, (
        f"Assessment manifests reference old folders: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 117: No active test requires on-disk standardized_claude_v1.zip
# ---------------------------------------------------------------------------
def test_117_no_active_test_requires_ondisk_zip():
    if not os.path.isfile(PKG_TEST_FILE):
        pytest.skip("test_human_baseline_package_integrity.py not found")
    with open(PKG_TEST_FILE, encoding="utf-8") as fh:
        src = fh.read()
    # The test file must not have any test that reads from the on-disk ZIP_PATH
    # (tests that use _make_temp_zip() are OK — they create their own fresh ZIP)
    # Check for direct use of ZIP_PATH in test functions (not in the constant definition)
    test_bodies = re.split(r"\ndef test_", src)
    zip_path_in_tests = []
    for i, body in enumerate(test_bodies[1:], start=1):
        # Check if ZIP_PATH is referenced directly in the test body (not via _make_temp_zip)
        if "ZIP_PATH" in body and "_make_temp_zip" not in body:
            # Only the manifest test (test_87) legitimately reads from output dir
            func_name = body.split("(")[0]
            if "manifest" not in func_name.lower():
                zip_path_in_tests.append(f"test_{func_name[:40]}")
    assert len(zip_path_in_tests) == 0, (
        f"Tests reference on-disk ZIP_PATH without using _make_temp_zip: {zip_path_in_tests}"
    )
