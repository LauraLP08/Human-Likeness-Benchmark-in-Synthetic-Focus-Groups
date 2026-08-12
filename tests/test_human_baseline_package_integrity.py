"""
Tests 71–87: Human baseline artifact package integrity.

Covers:
  1. standardized_claude_v1 source directory has total turns = 649
  2. Arden transcript has 145 turns
  3. Arden section_markers.json has 8 markers
  4. Greta section_markers.json has 7 markers
  5. Jeremy section_markers.json has 8 markers
  6. No transcript.json contains embedded #Speaker labels
  7. No QESB transcript.json contains standalone section headings in content
  8. Package script creates a ZIP from source directory (temp dir, no on-disk dependency)
  9. ZIP after extraction has total turns = 649
  10. ZIP after extraction has Arden = 145 turns
  11. ZIP after extraction has Arden = 8 section markers
  12. ZIP after extraction has no embedded #Speaker labels
  13. ZIP after extraction has no QESB section heading leakage
  14. ZIP contains no fake moderator_log.json
  15. ZIP contains no fake run_metadata.json
  16. ZIP contains no fake session_state_final.json
  17. package_manifest.json exists and reports verification_status = PASS

NOTE: Tests 78–87 create a fresh temp ZIP from the source directory on each run.
They do NOT depend on the on-disk standardized_claude_v1.zip in docs/testing/.
"""

import os
import json
import re
import zipfile
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STD_DIR = os.path.join(ROOT, "data", "human_baseline", "standardized_claude_v1")
OUTPUT_DIR = os.path.join(
    ROOT, "docs", "testing", "human_baseline_standardization_claude_v1"
)
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "package_manifest.json")

ARDEN_BID = "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript"
GRETA_BID = "QESB_Post_Greta_Kiyaan_Matilda_230724__transcript"
JEREMY_BID = "QESB_Post_Jeremy_Chloe_Kim_190724__transcript"

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


def _normalise_heading(s: str) -> str:
    s = s.strip().lower().rstrip("?").strip()
    s = s.replace("â€™", "").replace("â€˜", "")
    s = re.sub(r"['''ʹ′‚‛]", "", s)
    return s


def _is_qesb_heading(line: str) -> bool:
    return _normalise_heading(line) in QESB_HEADING_EXACT


def _load_transcript(std_root: str, bid: str):
    tp = os.path.join(std_root, bid, "transcript.json")
    if not os.path.exists(tp):
        return None
    with open(tp, encoding="utf-8") as fh:
        return json.load(fh)


def _load_section_markers(std_root: str, bid: str):
    sp = os.path.join(std_root, bid, "section_markers.json")
    if not os.path.exists(sp):
        return []
    with open(sp, encoding="utf-8") as fh:
        return json.load(fh)


def _total_turns(std_root: str) -> int:
    total = 0
    for bid in os.listdir(std_root):
        if not os.path.isdir(os.path.join(std_root, bid)):
            continue
        t = _load_transcript(std_root, bid)
        if t:
            total += len(t)
    return total


def _skip_if_no_source():
    if not os.path.isdir(STD_DIR):
        pytest.skip("standardized_claude_v1/ not available")


def _make_temp_zip():
    """Create a fresh ZIP of STD_DIR in a temp directory and return (tmpdir, zip_path)."""
    from scripts.package_and_verify_standardized_claude_v1 import create_zip
    tmpdir = tempfile.mkdtemp()
    zip_path = os.path.join(tmpdir, "test_pkg.zip")
    create_zip(STD_DIR, zip_path)
    return tmpdir, zip_path


# ---------------------------------------------------------------------------
# SOURCE DIRECTORY CHECKS
# ---------------------------------------------------------------------------

# Test 71: source directory total turns = 649
def test_71_source_total_turns_649():
    _skip_if_no_source()
    total = _total_turns(STD_DIR)
    assert total == 649, f"Expected 649 total turns in source; got {total}"


# Test 72: Arden has 145 turns
def test_72_arden_source_turns_145():
    _skip_if_no_source()
    t = _load_transcript(STD_DIR, ARDEN_BID)
    if t is None:
        pytest.skip(f"{ARDEN_BID} transcript.json not found")
    assert len(t) == 145, f"Expected 145 Arden turns; got {len(t)}"


# Test 73: Arden section_markers.json has 8 entries
def test_73_arden_source_section_markers_8():
    _skip_if_no_source()
    sm = _load_section_markers(STD_DIR, ARDEN_BID)
    assert len(sm) == 8, f"Expected 8 Arden section markers; got {len(sm)}"


# Test 74: Greta section_markers.json has 7 entries
def test_74_greta_source_section_markers_7():
    _skip_if_no_source()
    sm = _load_section_markers(STD_DIR, GRETA_BID)
    assert len(sm) == 7, f"Expected 7 Greta section markers; got {len(sm)}"


# Test 75: Jeremy section_markers.json has 8 entries
def test_75_jeremy_source_section_markers_8():
    _skip_if_no_source()
    sm = _load_section_markers(STD_DIR, JEREMY_BID)
    assert len(sm) == 8, f"Expected 8 Jeremy section markers; got {len(sm)}"


# Test 76: No embedded #Speaker labels in source transcripts
def test_76_source_no_embedded_hash_speakers():
    _skip_if_no_source()
    violations = []
    for bid in os.listdir(STD_DIR):
        bd = os.path.join(STD_DIR, bid)
        if not os.path.isdir(bd):
            continue
        t = _load_transcript(STD_DIR, bid)
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
        f"Embedded #Speaker labels found in source: {violations[:5]}"
    )


# Test 77: No QESB section heading leakage in source turn content
def test_77_source_no_qesb_heading_leakage():
    _skip_if_no_source()
    violations = []
    for bid in os.listdir(STD_DIR):
        if "qesb" not in bid.lower():
            continue
        bd = os.path.join(STD_DIR, bid)
        if not os.path.isdir(bd):
            continue
        t = _load_transcript(STD_DIR, bid)
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
        f"QESB heading leakage in source turn content: {violations[:5]}"
    )


# ---------------------------------------------------------------------------
# ZIP CREATION AND VERIFICATION (fresh temp ZIP, no on-disk dependency)
# ---------------------------------------------------------------------------

# Test 78: Package script create_zip() produces a non-empty ZIP
def test_78_package_script_creates_zip():
    _skip_if_no_source()
    from scripts.package_and_verify_standardized_claude_v1 import (
        verify_directory, create_zip,
    )
    src_issues, _, _ = verify_directory(STD_DIR)
    assert len(src_issues) == 0, (
        f"Source verification failed before ZIP creation: "
        f"{[i.description for i in src_issues]}"
    )
    tmpdir, zip_path = _make_temp_zip()
    try:
        assert os.path.isfile(zip_path), "ZIP file was not created"
        assert os.path.getsize(zip_path) > 0, "ZIP file is empty"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# Test 79: ZIP after extraction has total turns = 649
def test_79_zip_total_turns_649():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    try:
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            total = _total_turns(extract_dir)
        assert total == 649, f"ZIP extraction: expected 649 total turns; got {total}"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# Test 80: ZIP after extraction has Arden = 145 turns
def test_80_zip_arden_turns_145():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    try:
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            t = _load_transcript(extract_dir, ARDEN_BID)
        if t is None:
            pytest.fail("Arden transcript.json not found in ZIP")
        assert len(t) == 145, f"ZIP extraction Arden: expected 145 turns; got {len(t)}"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# Test 81: ZIP after extraction has Arden = 8 section markers
def test_81_zip_arden_section_markers_8():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    try:
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            sm = _load_section_markers(extract_dir, ARDEN_BID)
        assert len(sm) == 8, (
            f"ZIP extraction Arden: expected 8 section markers; got {len(sm)}"
        )
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# Test 82: ZIP after extraction has no embedded #Speaker labels
def test_82_zip_no_embedded_hash_speakers():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    violations = []
    try:
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            for bid in os.listdir(extract_dir):
                bd = os.path.join(extract_dir, bid)
                if not os.path.isdir(bd):
                    continue
                t = _load_transcript(extract_dir, bid)
                if not t:
                    continue
                for turn in t:
                    for line in turn.get("content", "").split("\n"):
                        l = line.strip()
                        if not l or _TIME_RE.match(l):
                            continue
                        if _EMBEDDED_HASH_RE.match(l):
                            violations.append(
                                f"{bid} turn {turn.get('turn')}: {l[:60]}"
                            )
                            break
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    assert len(violations) == 0, (
        f"ZIP: embedded #Speaker labels found: {violations[:5]}"
    )


# Test 83: ZIP after extraction has no QESB section heading leakage
def test_83_zip_no_qesb_heading_leakage():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    violations = []
    try:
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            for bid in os.listdir(extract_dir):
                if "qesb" not in bid.lower():
                    continue
                bd = os.path.join(extract_dir, bid)
                if not os.path.isdir(bd):
                    continue
                t = _load_transcript(extract_dir, bid)
                if not t:
                    continue
                for turn in t:
                    for line in turn.get("content", "").split("\n"):
                        if _is_qesb_heading(line.strip()):
                            violations.append(
                                f"{bid} turn {turn.get('turn')}: {line.strip()[:60]}"
                            )
                            break
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    assert len(violations) == 0, (
        f"ZIP: QESB heading leakage in turn content: {violations[:5]}"
    )


# Test 84: ZIP contains no fake moderator_log.json
def test_84_zip_no_fake_moderator_log():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        fakes = [n for n in names if os.path.basename(n) == "moderator_log.json"]
        assert len(fakes) == 0, f"ZIP contains moderator_log.json: {fakes}"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# Test 85: ZIP contains no fake run_metadata.json
def test_85_zip_no_fake_run_metadata():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        fakes = [n for n in names if os.path.basename(n) == "run_metadata.json"]
        assert len(fakes) == 0, f"ZIP contains run_metadata.json: {fakes}"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# Test 86: ZIP contains no fake session_state_final.json
def test_86_zip_no_fake_session_state():
    _skip_if_no_source()
    tmpdir, zip_path = _make_temp_zip()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        fakes = [n for n in names if os.path.basename(n) == "session_state_final.json"]
        assert len(fakes) == 0, f"ZIP contains session_state_final.json: {fakes}"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# MANIFEST CHECK
# ---------------------------------------------------------------------------

# Test 87: package_manifest.json exists and reports verification_status = PASS
def test_87_manifest_exists_and_passes():
    if not os.path.isfile(MANIFEST_PATH):
        pytest.skip("package_manifest.json not available — run package script first")
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)
    status = manifest.get("verification_status")
    blocking = manifest.get("blocking_issue_count", -1)
    assert status == "PASS", (
        f"package_manifest.json verification_status is '{status}' "
        f"(blocking_issue_count={blocking})"
    )
    assert blocking == 0, (
        f"package_manifest.json blocking_issue_count={blocking} (expected 0)"
    )
