"""
Clean rebuild pipeline — claude_v1.

Reads raw transcripts and guides from:
  data/human_baseline/raw_transcripts/
  data/human_baseline/raw_guides/

Uses pre-existing extracted text from:
  data/human_baseline/extracted_text/

Writes standardized output to:
  data/human_baseline/standardized_claude_v1/<baseline_id>/

Writes assessment output to:
  docs/testing/human_baseline_standardization_claude_v1/assessments/<baseline_id>/

Does NOT overwrite data/human_baseline/standardized/ (the previous outputs).
Does NOT create moderator_log.json, run_metadata.json, or session_state_final.json.
Does NOT run live API calls.
"""

import os
import subprocess
import glob
import json
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RAW_TRANSCRIPTS_DIR = os.path.join(ROOT, "data", "human_baseline", "raw_transcripts")
RAW_GUIDES_DIR = os.path.join(ROOT, "data", "human_baseline", "raw_guides")
EXTRACTED_DIR = os.path.join(ROOT, "data", "human_baseline", "extracted_text")
OUTPUT_DIR = os.path.join(ROOT, "data", "human_baseline", "standardized_claude_v1")
ASSESSMENT_DIR = os.path.join(
    ROOT, "docs", "testing", "human_baseline_standardization_claude_v1", "assessments"
)
METADATA_FILE = os.path.join(EXTRACTED_DIR, "extraction_metadata.json")

env = os.environ.copy()
env["PYTHONPATH"] = ROOT


def run(cmd, label=""):
    print(f"  >> {label or ' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode})")
        sys.exit(result.returncode)
    return result


# ---------------------------------------------------------------------------
# Step 1 — Extract raw files (re-run to ensure freshness, skip if already done)
# ---------------------------------------------------------------------------
def step1_extract():
    print("\n=== Step 1: Extract raw transcripts and guides ===")
    extracted_txts = glob.glob(os.path.join(EXTRACTED_DIR, "*.txt"))
    if extracted_txts and os.path.exists(METADATA_FILE):
        print(f"  Extracted text already present ({len(extracted_txts)} .txt files). Skipping re-extraction.")
        return
    run(
        [
            sys.executable, os.path.join(ROOT, "scripts", "extract_focus_group_transcript_text.py"),
            "--input-dir", RAW_TRANSCRIPTS_DIR,
            "--output-dir", EXTRACTED_DIR,
        ],
        label="extract transcripts",
    )


# ---------------------------------------------------------------------------
# Step 2 — Standardize each extracted transcript → standardized_claude_v1/
# ---------------------------------------------------------------------------
def step2_standardize():
    print("\n=== Step 2: Standardize transcripts -> standardized_claude_v1/ ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    txt_files = sorted(glob.glob(os.path.join(EXTRACTED_DIR, "*.txt")))
    if not txt_files:
        print("  ERROR: No .txt files found in extracted_text/. Run extraction first.")
        sys.exit(1)
    for txt_file in txt_files:
        run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "standardize_human_focus_group_transcript.py"),
                "--input-file", txt_file,
                "--metadata-file", METADATA_FILE,
                "--output-base-dir", OUTPUT_DIR,
            ],
            label=f"standardize {os.path.basename(txt_file)}",
        )


# ---------------------------------------------------------------------------
# Step 3 — Match and standardize guides
# ---------------------------------------------------------------------------
def step3_guides():
    print("\n=== Step 3: Match and standardize guides ===")
    guides = sorted(glob.glob(os.path.join(RAW_GUIDES_DIR, "*.*")))
    if not guides:
        print("  No guide files found — skipping.")
        return

    baselines = [
        d for d in os.listdir(OUTPUT_DIR)
        if os.path.isdir(os.path.join(OUTPUT_DIR, d))
    ]

    for guide_path in guides:
        gname = os.path.basename(guide_path).lower()
        matched: list[str] = []

        if "qesb" in gname:
            matched = [b for b in baselines if "qesb" in b.lower()]
        elif "work at home" in gname or "work_at_home" in gname:
            if "employee" in gname and "employer" not in gname:
                matched = [
                    b for b in baselines
                    if ("work at home" in b.lower() or "work_at_home" in b.lower())
                    and "employee" in b.lower()
                    and "employer" not in b.lower()
                ]
            elif "employer" in gname:
                matched = [
                    b for b in baselines
                    if ("work at home" in b.lower() or "work_at_home" in b.lower())
                    and "employer" in b.lower()
                ]

        if matched:
            for baseline_id in matched:
                baseline_dir = os.path.join(OUTPUT_DIR, baseline_id)
                print(f"  Matching guide '{os.path.basename(guide_path)}' -> '{baseline_id}'")
                run(
                    [
                        sys.executable,
                        os.path.join(ROOT, "scripts", "standardize_focus_group_guide.py"),
                        "--input-file", guide_path,
                        "--output-base-dir", OUTPUT_DIR,
                        "--baseline-id", baseline_id,
                    ],
                    label=f"guide -> {baseline_id}",
                )
                # Update baseline_metadata.json to mark guide_available = True
                meta_path = os.path.join(baseline_dir, "baseline_metadata.json")
                if os.path.exists(meta_path):
                    with open(meta_path, "r", encoding="utf-8") as fh:
                        meta = json.load(fh)
                    meta["guide_available"] = True
                    meta["guide_id"] = baseline_id
                    with open(meta_path, "w", encoding="utf-8") as fh:
                        json.dump(meta, fh, indent=2, ensure_ascii=False)
        else:
            print(f"  No baseline match for guide '{os.path.basename(guide_path)}' — writing to unmatched_guides/")
            run(
                [
                    sys.executable,
                    os.path.join(ROOT, "scripts", "standardize_focus_group_guide.py"),
                    "--input-file", guide_path,
                    "--output-base-dir", OUTPUT_DIR,
                ],
                label=f"unmatched guide {os.path.basename(guide_path)}",
            )


# ---------------------------------------------------------------------------
# Step 4 — Run assessments
# ---------------------------------------------------------------------------
def step4_assess():
    print("\n=== Step 4: Run human-baseline assessments ===")
    baselines = sorted(
        d for d in os.listdir(OUTPUT_DIR)
        if os.path.isdir(os.path.join(OUTPUT_DIR, d))
    )
    for baseline_id in baselines:
        b_dir = os.path.join(OUTPUT_DIR, baseline_id)
        out_dir = os.path.join(ASSESSMENT_DIR, baseline_id)
        os.makedirs(out_dir, exist_ok=True)
        run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "assess_human_baseline.py"),
                "--baseline-dir", b_dir,
                "--output-dir", out_dir,
            ],
            label=f"assess {baseline_id}",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Claude v1 Human Baseline Standardization Pipeline")
    print(f"Output dir: {OUTPUT_DIR}")
    print("=" * 70)

    step1_extract()
    step2_standardize()
    step3_guides()
    step4_assess()

    # Summary
    baselines = [
        d for d in os.listdir(OUTPUT_DIR)
        if os.path.isdir(os.path.join(OUTPUT_DIR, d))
    ]
    print(f"\n=== Pipeline complete ===")
    print(f"Baselines standardized: {len(baselines)}")
    for b in sorted(baselines):
        tm = os.path.join(OUTPUT_DIR, b, "transcript.json")
        tc = 0
        if os.path.exists(tm):
            with open(tm, encoding="utf-8") as fh:
                tc = len(json.load(fh))
        print(f"  {b}: {tc} turns")


if __name__ == "__main__":
    main()
