"""
Package and verify standardized_claude_v1 artifacts for the claude_v1
human baseline pipeline.

Steps:
  1. Verify source directory (count/content/cleanliness checks).
  2. Create ZIP archive of the verified directory.
  3. Extract ZIP to a temp directory and re-run the same checks.
  4. Write package_manifest.json (paths, hashes, per-baseline stats,
     verification result).

The ZIP is only considered valid if post-extraction verification also passes.

Output files (both written to --output-dir):
  standardized_claude_v1.zip
  package_manifest.json

Exit codes:
  0 — source directory and ZIP both pass all checks
  2 — one or more blocking issues found in source or ZIP
"""

import os
import sys
import json
import re
import hashlib
import zipfile
import tempfile
import shutil
import argparse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXPECTED_TOTAL_TURNS = 649

EXPECTED_BASELINE_COUNTS = {
    "arden": {"turns": 145, "sections": 8},
    "greta": {"sections": 7},
    "jeremy": {"sections": 8},
}

FAKE_ARTEFACTS = [
    "moderator_log.json",
    "run_metadata.json",
    "session_state_final.json",
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_heading(s: str) -> str:
    s = s.strip().lower().rstrip("?").strip()
    s = s.replace("â€™", "").replace("â€˜", "")
    s = re.sub(r"['''ʹ′‚‛]", "", s)
    return s


def _is_qesb_heading(line: str) -> bool:
    return _normalise_heading(line) in QESB_HEADING_EXACT


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_zip(path: str) -> str:
    return _sha256_file(path)


# ---------------------------------------------------------------------------
# Blocking issue
# ---------------------------------------------------------------------------

class BlockingIssue:
    def __init__(self, check_id: str, baseline_id: str, description: str):
        self.check_id = check_id
        self.baseline_id = baseline_id
        self.description = description

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "baseline_id": self.baseline_id,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_directory(std_dir: str):
    """
    Run all blocking checks against std_dir.

    Returns:
        (issues, baseline_stats, total_turns)

    baseline_stats: list of dicts with keys: bid, turns, sections, transcript_hash, files
    """
    issues: list = []
    baseline_stats: list = []
    total_turns = 0

    if not os.path.isdir(std_dir):
        issues.append(BlockingIssue("PKG00", "ALL", f"std_dir not found: {std_dir}"))
        return issues, baseline_stats, total_turns

    baselines = sorted(
        d for d in os.listdir(std_dir)
        if os.path.isdir(os.path.join(std_dir, d))
    )

    if len(baselines) == 0:
        issues.append(BlockingIssue("PKG00", "ALL", "No baseline directories found"))
        return issues, baseline_stats, total_turns

    for bid in baselines:
        bd = os.path.join(std_dir, bid)
        bl_lower = bid.lower()
        is_qesb = "qesb" in bl_lower

        tp = os.path.join(bd, "transcript.json")
        sm_path = os.path.join(bd, "section_markers.json")

        if not os.path.exists(tp):
            issues.append(BlockingIssue("PKG00", bid, "transcript.json missing"))
            baseline_stats.append({
                "bid": bid, "turns": 0, "sections": 0,
                "transcript_hash": None, "files": [],
            })
            continue

        with open(tp, encoding="utf-8") as fh:
            transcript = json.load(fh)

        turns = len(transcript)
        total_turns += turns

        sections = 0
        if os.path.exists(sm_path):
            with open(sm_path, encoding="utf-8") as fh:
                sections = len(json.load(fh))

        # File list with hashes
        files = []
        for fname in sorted(os.listdir(bd)):
            fpath = os.path.join(bd, fname)
            if os.path.isfile(fpath):
                files.append({
                    "filename": fname,
                    "sha256": _sha256_file(fpath),
                    "size_bytes": os.path.getsize(fpath),
                })

        baseline_stats.append({
            "bid": bid,
            "turns": turns,
            "sections": sections,
            "transcript_hash": _sha256_file(tp),
            "files": files,
        })

        # PKG01: No embedded hash-prefixed speaker labels
        for turn in transcript:
            content = turn.get("content", "")
            for line in content.split("\n"):
                line_s = line.strip()
                if not line_s or _TIME_RE.match(line_s):
                    continue
                if _EMBEDDED_HASH_RE.match(line_s):
                    issues.append(BlockingIssue(
                        "PKG01", bid,
                        f"Turn {turn.get('turn')}: embedded hash-prefixed speaker label "
                        f"'{line_s[:60]}'",
                    ))
                    break

        # PKG02: No QESB section headings inside turn content
        if is_qesb:
            for turn in transcript:
                content = turn.get("content", "")
                for line in content.split("\n"):
                    if _is_qesb_heading(line.strip()):
                        issues.append(BlockingIssue(
                            "PKG02", bid,
                            f"Turn {turn.get('turn')}: standalone QESB heading in content "
                            f"'{line.strip()[:80]}'",
                        ))
                        break

        # PKG03: No fake synthetic artefacts
        for fname in FAKE_ARTEFACTS:
            if os.path.exists(os.path.join(bd, fname)):
                issues.append(BlockingIssue(
                    "PKG03", bid,
                    f"Fake synthetic artefact present: {fname}",
                ))

    # PKG04: Total turns
    if total_turns != EXPECTED_TOTAL_TURNS:
        issues.append(BlockingIssue(
            "PKG04", "ALL",
            f"Total dialogue turns {total_turns} != expected {EXPECTED_TOTAL_TURNS}",
        ))

    # PKG05-PKG08: Named baseline counts
    arden = next((s for s in baseline_stats if "arden" in s["bid"].lower()), None)
    greta  = next((s for s in baseline_stats if "greta"  in s["bid"].lower()), None)
    jeremy = next((s for s in baseline_stats if "jeremy" in s["bid"].lower()), None)

    if arden:
        if arden["turns"] != 145:
            issues.append(BlockingIssue(
                "PKG05", arden["bid"],
                f"Arden turn count {arden['turns']} != 145",
            ))
        if arden["sections"] != 8:
            issues.append(BlockingIssue(
                "PKG06", arden["bid"],
                f"Arden section marker count {arden['sections']} != 8",
            ))
    else:
        issues.append(BlockingIssue("PKG05", "ALL", "Arden baseline not found"))

    if greta:
        if greta["sections"] != 7:
            issues.append(BlockingIssue(
                "PKG07", greta["bid"],
                f"Greta section marker count {greta['sections']} != 7",
            ))
    else:
        issues.append(BlockingIssue("PKG07", "ALL", "Greta baseline not found"))

    if jeremy:
        if jeremy["sections"] != 8:
            issues.append(BlockingIssue(
                "PKG08", jeremy["bid"],
                f"Jeremy section marker count {jeremy['sections']} != 8",
            ))
    else:
        issues.append(BlockingIssue("PKG08", "ALL", "Jeremy baseline not found"))

    return issues, baseline_stats, total_turns


# ---------------------------------------------------------------------------
# ZIP creation
# ---------------------------------------------------------------------------

def create_zip(std_dir: str, zip_path: str) -> None:
    """Create a ZIP of all files in std_dir, preserving baseline subdirectory structure."""
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for bid in sorted(os.listdir(std_dir)):
            bd = os.path.join(std_dir, bid)
            if not os.path.isdir(bd):
                continue
            for fname in sorted(os.listdir(bd)):
                fpath = os.path.join(bd, fname)
                if os.path.isfile(fpath):
                    arcname = f"{bid}/{fname}"
                    zf.write(fpath, arcname)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def build_manifest(
    zip_path: str,
    std_dir: str,
    baseline_stats: list,
    total_turns: int,
    src_issues: list,
    zip_issues: list,
    zip_total_turns: int,
    timestamp: str,
) -> dict:
    all_issues = src_issues + zip_issues
    verification_status = "PASS" if not all_issues else "BLOCKED"

    baselines_entry = []
    for s in baseline_stats:
        baselines_entry.append({
            "baseline_id": s["bid"],
            "turn_count": s["turns"],
            "section_marker_count": s["sections"],
            "transcript_json_sha256": s.get("transcript_hash"),
            "files": s.get("files", []),
        })

    return {
        "package_path": zip_path,
        "package_creation_timestamp": timestamp,
        "package_sha256": _sha256_zip(zip_path),
        "source_directory": std_dir,
        "total_dialogue_turns_source": total_turns,
        "total_dialogue_turns_zip": zip_total_turns,
        "baselines": baselines_entry,
        "verification_status": verification_status,
        "blocking_issue_count": len(all_issues),
        "source_blocking_issues": [i.to_dict() for i in src_issues],
        "zip_blocking_issues": [i.to_dict() for i in zip_issues],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Package and verify standardized_claude_v1 artifacts."
    )
    parser.add_argument(
        "--source-dir",
        default=os.path.join(ROOT, "data", "human_baseline", "standardized_claude_v1"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(
            ROOT, "docs", "testing", "human_baseline_standardization_claude_v1"
        ),
    )
    args = parser.parse_args()

    zip_path = os.path.join(args.output_dir, "standardized_claude_v1.zip")
    manifest_path = os.path.join(args.output_dir, "package_manifest.json")
    timestamp = datetime.now(timezone.utc).isoformat()

    os.makedirs(args.output_dir, exist_ok=True)

    # Step 1: Verify source directory
    print("Step 1: Verifying source directory...")
    src_issues, baseline_stats, total_turns = verify_directory(args.source_dir)

    if src_issues:
        print(f"  [BLOCKED] {len(src_issues)} blocking issue(s) in source directory:")
        for issue in src_issues:
            print(f"    [{issue.check_id}] {issue.baseline_id}: {issue.description}")
    else:
        print(f"  [PASS] Source directory: {total_turns} total turns, 0 blocking issues")

    # Step 2: Create ZIP
    print(f"\nStep 2: Creating ZIP archive...")
    create_zip(args.source_dir, zip_path)
    zip_size = os.path.getsize(zip_path)
    print(f"  Created: {zip_path} ({zip_size:,} bytes)")

    # Step 3: Verify ZIP after extraction
    print("\nStep 3: Verifying ZIP after extraction...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        zip_issues, zip_stats, zip_total_turns = verify_directory(tmpdir)

    if zip_issues:
        print(f"  [BLOCKED] {len(zip_issues)} blocking issue(s) in extracted ZIP:")
        for issue in zip_issues:
            print(f"    [{issue.check_id}] {issue.baseline_id}: {issue.description}")
    else:
        print(f"  [PASS] Extracted ZIP: {zip_total_turns} total turns, 0 blocking issues")

    # Step 4: Write manifest
    manifest = build_manifest(
        zip_path, args.source_dir,
        baseline_stats, total_turns,
        src_issues, zip_issues,
        zip_total_turns, timestamp,
    )
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print(f"\nManifest written: {manifest_path}")

    # Final status
    all_blocking = len(src_issues) + len(zip_issues)
    overall = "PASS" if all_blocking == 0 else "BLOCKED"
    print(f"\nPackaging complete.")
    print(f"  Overall status     : {overall}")
    print(f"  Source turns       : {total_turns}")
    print(f"  ZIP turns          : {zip_total_turns}")
    print(f"  Source blocking    : {len(src_issues)}")
    print(f"  ZIP blocking       : {len(zip_issues)}")
    print(f"  ZIP path           : {zip_path}")
    print(f"  Manifest path      : {manifest_path}")

    if all_blocking > 0:
        print("\n[WARNING] Blocking issues found. Review manifest for details.")
        raise SystemExit(2)
    else:
        print("\n[OK] All checks pass.")


if __name__ == "__main__":
    main()
