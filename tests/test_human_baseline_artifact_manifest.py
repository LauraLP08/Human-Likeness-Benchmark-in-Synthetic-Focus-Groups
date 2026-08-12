"""
Tests 118–123: ARTIFACT_MANIFEST.json integrity.

Covers:
  1. ARTIFACT_MANIFEST.json exists in standardized_claude_v1/
  2. Manifest contains exactly 7 baselines with correct IDs
  3. Every file path listed in the manifest exists on disk
  4. SHA-256 hashes in the manifest match the current on-disk files
  5. transcript.txt and clean_transcript.txt have identical SHA-256 hashes
  6. validation_rules section present with expected keys
"""

import hashlib
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STD_DIR = os.path.join(ROOT, "data", "human_baseline", "standardized_claude_v1")
MANIFEST_PATH = os.path.join(STD_DIR, "ARTIFACT_MANIFEST.json")

EXPECTED_BASELINE_IDS = {
    "QESB_Post_Arden_Dominic_Amalia_Julius_190724_transcript",
    "QESB_Post_Greta_Kiyaan_Matilda_230724__transcript",
    "QESB_Post_Jeremy_Chloe_Kim_190724__transcript",
    "Work at home_FG transcript_employee group 1_pseudo",
    "Work at home_FG Transcript_employee group 2_pseudo",
    "Work at home_FG Transcript_employer group 1_pseudo",
    "Work at home_FG Transcript_employer group 3_pseudo",
}


def _load_manifest():
    if not os.path.isfile(MANIFEST_PATH):
        pytest.skip("ARTIFACT_MANIFEST.json not present")
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# Test 118: manifest file exists
def test_118_artifact_manifest_exists():
    assert os.path.isfile(MANIFEST_PATH), (
        f"ARTIFACT_MANIFEST.json not found at {MANIFEST_PATH}"
    )


# Test 119: manifest has exactly 7 baselines with all expected IDs
def test_119_manifest_has_7_correct_baselines():
    manifest = _load_manifest()
    baselines = manifest.get("baselines", [])
    found_ids = {b["baseline_id"] for b in baselines}
    assert len(baselines) == 7, f"Expected 7 baselines; got {len(baselines)}"
    missing = EXPECTED_BASELINE_IDS - found_ids
    extra = found_ids - EXPECTED_BASELINE_IDS
    assert not missing, f"Missing baseline IDs: {missing}"
    assert not extra, f"Unexpected baseline IDs: {extra}"


# Test 120: every file path listed in the manifest exists on disk
def test_120_all_manifest_paths_exist():
    manifest = _load_manifest()
    missing = []
    for b in manifest["baselines"]:
        bid = b["baseline_id"]
        for key, entry in b["files"].items():
            abs_path = os.path.join(ROOT, entry["path"].replace("/", os.sep))
            if not os.path.isfile(abs_path):
                missing.append(f"{bid}/{key}: {entry['path']}")
    assert len(missing) == 0, (
        f"{len(missing)} manifest paths missing on disk:\n" + "\n".join(missing[:10])
    )


# Test 121: SHA-256 hashes match current on-disk files
def test_121_manifest_hashes_match_disk():
    manifest = _load_manifest()
    mismatches = []
    for b in manifest["baselines"]:
        bid = b["baseline_id"]
        for key, entry in b["files"].items():
            if "sha256" not in entry:
                continue
            abs_path = os.path.join(ROOT, entry["path"].replace("/", os.sep))
            if not os.path.isfile(abs_path):
                mismatches.append(f"{bid}/{key}: file missing")
                continue
            actual = _sha256(abs_path)
            if actual != entry["sha256"]:
                mismatches.append(
                    f"{bid}/{key}: manifest={entry['sha256'][:12]} "
                    f"disk={actual[:12]}"
                )
    assert len(mismatches) == 0, (
        f"SHA-256 mismatches (manifest out of date?):\n"
        + "\n".join(mismatches[:10])
    )


# Test 122: transcript.txt sha256 == clean_transcript.txt sha256 (identical files)
def test_122_transcript_txt_identical_to_clean_transcript_txt():
    manifest = _load_manifest()
    mismatches = []
    for b in manifest["baselines"]:
        bid = b["baseline_id"]
        files = b["files"]
        txt_sha = files.get("transcript_txt", {}).get("sha256")
        clean_sha = files.get("clean_transcript_txt", {}).get("sha256")
        if txt_sha is None or clean_sha is None:
            mismatches.append(f"{bid}: sha256 missing from manifest entry")
            continue
        if txt_sha != clean_sha:
            mismatches.append(
                f"{bid}: transcript.txt sha256 ({txt_sha[:12]}) "
                f"!= clean_transcript.txt sha256 ({clean_sha[:12]})"
            )
    assert len(mismatches) == 0, (
        "transcript.txt and clean_transcript.txt are not identical:\n"
        + "\n".join(mismatches)
    )


# Test 123: validation_rules present with required keys
def test_123_manifest_validation_rules_present():
    manifest = _load_manifest()
    rules = manifest.get("validation_rules")
    assert rules is not None, "validation_rules key missing from manifest"

    clean = rules.get("clean_files", {})
    assert clean.get("applies_to"), "validation_rules.clean_files.applies_to missing"
    must_not = clean.get("must_not_contain", [])
    for sentinel in ["READ ME", "Alias | Sex", "End of transcript"]:
        assert sentinel in must_not, (
            f"'{sentinel}' missing from validation_rules.clean_files.must_not_contain"
        )
    assert clean.get("must_not_have_embedded_hash_speaker_labels") is True, (
        "validation_rules.clean_files.must_not_have_embedded_hash_speaker_labels "
        "should be True"
    )

    raw = rules.get("raw_extracted_transcript_txt", {})
    assert raw.get("may_contain_front_matter") is True, (
        "validation_rules.raw_extracted_transcript_txt.may_contain_front_matter "
        "should be True"
    )

    assert rules.get("transcript_txt_equals_clean_transcript_txt") is True, (
        "validation_rules.transcript_txt_equals_clean_transcript_txt should be True"
    )
    assert rules.get("authoritative_file_for_analysis") == "transcript.json", (
        "validation_rules.authoritative_file_for_analysis should be 'transcript.json'"
    )
