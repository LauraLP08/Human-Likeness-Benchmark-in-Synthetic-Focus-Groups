"""
Raw-vs-standardized comparison for human baseline transcripts (claude_v1).

For each baseline in --standardized-dir, locates the original raw transcript
file from --raw-dir (using baseline_metadata.json for filename/type lookup),
re-extracts text from the raw source using the same extraction logic as the
pipeline, and verifies:

  1. Raw extraction fidelity — raw_extracted_transcript.txt matches re-extracted
     raw source text (uses raw_extracted_transcript.txt, NOT transcript.txt, which
     now contains clean dialogue only)
  2. Speaker-label sequence — raw speaker labels vs transcript.json sequence
  3. Clean transcript content — no embedded speaker labels in turn content
  4. QESB heading handling — headings in section_markers, not turn content
  5. PHIND speaker handling — AN/SM/CF moderator, Participant unattributed,
     time expressions not speakers

If the raw file cannot be found or re-extraction fails, falls back to a
pre-extracted .txt from --extracted-dir with an explicit
CMP_FALLBACK_EXTRACTED_TEXT warning.  If neither source is available, the
text-dependent checks (CMP01, CMP02, CMP04b) are skipped; structural checks
(CMP03, CMP04a, CMP05) still run.

Writes:
  <output-dir>/raw_vs_standardized_comparison.md
  <output-dir>/raw_vs_standardized_comparison.json

Exit codes:
  0 — all baselines pass
  2 — one or more blocking issues found
"""

import os
import sys
import json
import re
import argparse
from typing import Optional
from datetime import datetime, timezone
from difflib import SequenceMatcher

# Make scripts/ importable so extract_focus_group_transcript_text can be loaded
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

try:
    from extract_focus_group_transcript_text import extract_text as _extract_text
    HAVE_EXTRACTOR = True
except ImportError:  # pragma: no cover
    HAVE_EXTRACTOR = False

ROOT = os.path.dirname(_SCRIPTS_DIR)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SUPPORTED_RAW_EXTS = {".docx", ".pdf", ".txt", ".md"}

_SPEAKER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _]*)::?\s*(.*)", re.IGNORECASE)
_SPEAKER_HASH_RE = re.compile(r"^#([A-Za-z][A-Za-z0-9 _]*)::?\s*(.*)", re.IGNORECASE)
_EMBEDDED_HASH_RE = re.compile(r"^#[A-Za-z][A-Za-z0-9 _]*::?\s", re.IGNORECASE)
_EMBEDDED_MOD_RE = re.compile(r"^(?:I|AN|SM|CF|Interviewer)::?\s", re.IGNORECASE)
_PAGE_RE = re.compile(r"^\d+$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}")

MODERATOR_LABELS = {"i", "an", "sm", "cf", "interviewer", "moderator"}

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

FRONT_MATTER_SENTINELS = {
    "read me", "copyright of this transcript", "recommended citation",
    "reporting conventions", "date of the interview", "location: online",
    "alias | sex", "initial transcription by", "phind employee group",
    "phind employer focus group", "transcription commenced",
    "transcription starts", "transcription begins",
}


def _normalise_heading(s: str) -> str:
    s = s.strip().lower().rstrip("?").strip()
    s = s.replace("â€™", "").replace("â€˜", "")
    s = re.sub(r"['‘’ʹ′‚‛]", "", s)
    return s


def _is_qesb_heading(line: str) -> bool:
    return _normalise_heading(line) in QESB_HEADING_EXACT


def _is_time_expression(name: str) -> bool:
    """Mirror the parser's time-expression guard so raw-sequence extraction is consistent."""
    s = name.strip().lower()
    if re.match(r"^\d{1,2}$", s):
        return True
    if re.match(r"^to\s+\d", s):
        return True
    return False


def _is_front_matter(line: str) -> bool:
    lower = line.strip().lower()
    return any(s in lower for s in FRONT_MATTER_SENTINELS)


# ---------------------------------------------------------------------------
# Issue helper
# ---------------------------------------------------------------------------
class Issue:
    def __init__(self, check_id: str, description: str, severity: str, evidence: str = ""):
        self.check_id = check_id
        self.description = description
        self.severity = severity   # blocking | warning | info
        self.evidence = evidence

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "description": self.description,
            "severity": self.severity,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Raw text resolution
# ---------------------------------------------------------------------------

def _find_raw_file(raw_dir: str, stem: str, ext: str):
    """
    Locate raw file in raw_dir. Returns (path_or_None, is_ambiguous).

    Primary strategy: exact {stem}{ext} (case-sensitive).
    Secondary: case-insensitive scan within raw_dir.
    """
    if not raw_dir or not os.path.isdir(raw_dir):
        return None, False

    target_name = stem + ext
    exact_path = os.path.join(raw_dir, target_name)
    if os.path.isfile(exact_path):
        return exact_path, False

    target_lower = target_name.lower()
    candidates = [
        os.path.join(raw_dir, f)
        for f in os.listdir(raw_dir)
        if f.lower() == target_lower and os.path.isfile(os.path.join(raw_dir, f))
    ]
    if len(candidates) == 1:
        return candidates[0], False
    if len(candidates) > 1:
        return None, True  # ambiguous

    return None, False


def _resolve_raw_text(
    baseline_id: str,
    baseline_dir: str,
    raw_dir: Optional[str],
    extracted_dir: Optional[str],
):
    """
    Locate and load the raw transcript text for one baseline.

    Returns (raw_text_or_None, extraction_source, issues_list).

    extraction_source values:
      "raw_docx"                    — re-extracted from original .docx via extract_text()
      "raw_pdf"                     — re-extracted from original .pdf via extract_text()
      "raw_txt"                     — re-extracted from original .txt via extract_text()
      "pre_extracted_text_fallback" — loaded from --extracted-dir/{baseline_id}.txt
      "unavailable"                 — no raw text could be located
    """
    issues: list = []

    # Read baseline_metadata.json for raw file hints
    meta_path = os.path.join(baseline_dir, "baseline_metadata.json")
    original_filename = None
    original_file_type = None
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            bm = json.load(fh)
        original_filename = bm.get("original_filename")
        original_file_type = bm.get("original_file_type")

    # Attempt raw file lookup when --raw-dir is provided
    if raw_dir:
        if not original_filename or not original_file_type:
            issues.append(Issue(
                "CMP_METADATA_MISSING",
                "baseline_metadata.json missing or lacks original_filename/original_file_type; "
                "cannot locate raw file in --raw-dir",
                "warning",
            ))
        else:
            stem = os.path.splitext(original_filename)[0]
            ext = "." + original_file_type.lstrip(".")

            if ext.lower() not in _SUPPORTED_RAW_EXTS:
                issues.append(Issue(
                    "CMP_UNSUPPORTED_RAW_FORMAT",
                    f"Raw file type '{ext}' not supported "
                    f"(supported: {sorted(_SUPPORTED_RAW_EXTS)})",
                    "warning",
                ))
            else:
                raw_path, is_ambiguous = _find_raw_file(raw_dir, stem, ext)

                if is_ambiguous:
                    issues.append(Issue(
                        "NEEDS_REVIEW_FILE_MATCH",
                        f"Multiple candidate raw files match stem '{stem}{ext}' "
                        f"in --raw-dir",
                        "warning",
                        evidence=f"stem={stem}, ext={ext}, raw_dir={raw_dir}",
                    ))
                elif raw_path is None:
                    issues.append(Issue(
                        "CMP_RAW_FILE_NOT_FOUND",
                        f"Raw file not found in --raw-dir: expected '{stem}{ext}'",
                        "warning",
                        evidence=f"raw_dir={raw_dir}",
                    ))
                else:
                    # Found raw file — extract text
                    if HAVE_EXTRACTOR:
                        raw_text, emeta = _extract_text(raw_path)
                        if raw_text.strip():
                            src_map = {
                                ".docx": "raw_docx",
                                ".pdf":  "raw_pdf",
                                ".txt":  "raw_txt",
                                ".md":   "raw_txt",
                            }
                            extraction_source = src_map.get(ext.lower(), "raw_txt")
                            return raw_text, extraction_source, issues
                        else:
                            warn_msg = "; ".join(
                                emeta.get("extraction_warnings", ["empty extraction"])
                            )
                            issues.append(Issue(
                                "CMP_RAW_EXTRACTION_FAILED",
                                f"extract_text() returned empty text for "
                                f"'{os.path.basename(raw_path)}': {warn_msg}",
                                "warning",
                            ))
                    else:
                        issues.append(Issue(
                            "CMP_EXTRACTOR_UNAVAILABLE",
                            "extract_focus_group_transcript_text module not importable; "
                            "cannot re-extract from raw file",
                            "warning",
                        ))

    # Fallback: pre-extracted .txt from --extracted-dir
    if extracted_dir:
        extracted_path = os.path.join(extracted_dir, baseline_id + ".txt")
        if os.path.isfile(extracted_path):
            with open(extracted_path, encoding="utf-8") as fh:
                raw_text = fh.read()
            issues.append(Issue(
                "CMP_FALLBACK_EXTRACTED_TEXT",
                "Using pre-extracted .txt from --extracted-dir (not re-extracted from raw source)",
                "warning",
                evidence=f"extracted_path={extracted_path}",
            ))
            return raw_text, "pre_extracted_text_fallback", issues
        else:
            issues.append(Issue(
                "CMP_MISSING_EXTRACTED",
                f"Pre-extracted .txt not found: {extracted_path}",
                "warning",
            ))

    return None, "unavailable", issues


# ---------------------------------------------------------------------------
# Per-baseline comparison
# ---------------------------------------------------------------------------

def compare_baseline(
    baseline_id: str,
    baseline_dir: str,
    raw_dir: Optional[str] = None,
    extracted_dir: Optional[str] = None,
) -> list:
    issues: list = []
    bl_lower = baseline_id.lower()
    is_qesb = "qesb" in bl_lower
    is_phind = (
        "work at home" in bl_lower
        or "employee" in bl_lower
        or "employer" in bl_lower
    )

    # Locate artefacts
    transcript_path = os.path.join(baseline_dir, "transcript.json")
    # raw_extracted_transcript.txt holds the raw source extraction (may contain READ ME/front matter).
    # transcript.txt now holds clean dialogue only and must NOT be used for fidelity checks.
    raw_extracted_txt_path = os.path.join(baseline_dir, "raw_extracted_transcript.txt")
    section_markers_path = os.path.join(baseline_dir, "section_markers.json")

    if not os.path.exists(transcript_path):
        issues.append(Issue("CMP_MISSING_TRANSCRIPT", "transcript.json not found", "blocking"))
        return issues

    with open(transcript_path, encoding="utf-8") as fh:
        transcript = json.load(fh)

    section_markers = []
    if os.path.exists(section_markers_path):
        with open(section_markers_path, encoding="utf-8") as fh:
            section_markers = json.load(fh)

    # Resolve raw text
    raw_text, extraction_source, res_issues = _resolve_raw_text(
        baseline_id, baseline_dir, raw_dir, extracted_dir
    )
    issues.extend(res_issues)
    issues.append(Issue(
        "CMP_EXTRACTION_SOURCE",
        f"Raw text resolved via: {extraction_source}",
        "info",
        evidence=extraction_source,
    ))

    raw_lines = raw_text.split("\n") if raw_text is not None else []

    # ---------------------------------------------------------------
    # Check 1: Raw extraction fidelity (requires raw_text)
    # Compares against raw_extracted_transcript.txt (raw source copy),
    # NOT transcript.txt which now contains clean dialogue only.
    # ---------------------------------------------------------------
    if raw_text is not None:
        if os.path.exists(raw_extracted_txt_path):
            with open(raw_extracted_txt_path, encoding="utf-8") as fh:
                stored_raw_txt = fh.read()
            ratio = SequenceMatcher(None, raw_text, stored_raw_txt).ratio()
            if ratio < 0.98:
                issues.append(Issue(
                    "CMP01_EXTRACTION_MISMATCH",
                    f"raw_extracted_transcript.txt similarity to re-extracted raw text is "
                    f"{ratio:.3f} (expected >= 0.98)",
                    "blocking",
                    evidence=f"ratio={ratio:.4f}, extraction_source={extraction_source}",
                ))
        else:
            issues.append(Issue(
                "CMP01_MISSING_RAW_EXTRACTED_TXT",
                "raw_extracted_transcript.txt not found in baseline dir",
                "warning",
            ))

    # ---------------------------------------------------------------
    # Check 2: Speaker-label sequence from raw text (requires raw_text)
    # ---------------------------------------------------------------
    if raw_text is not None:
        raw_speaker_sequence: list = []
        in_front_matter = True

        for raw_line in raw_lines:
            stripped = raw_line.strip()

            if _PAGE_RE.match(stripped):
                continue
            if stripped.lower().startswith("end of transcript"):
                break

            m = _SPEAKER_RE.match(stripped) or _SPEAKER_HASH_RE.match(stripped)
            if m:
                sp = m.group(1).strip()
                sl = sp.lower()

                if in_front_matter:
                    if is_qesb and sl in {"i", "interviewer"}:
                        in_front_matter = False
                    elif is_phind and sl in {"an", "sm", "cf"}:
                        in_front_matter = False
                    elif not is_qesb and not is_phind:
                        if not _is_front_matter(stripped):
                            in_front_matter = False

                if not in_front_matter:
                    if is_qesb and sl == "moderator":
                        continue
                    if _TIME_RE.match(stripped) or _is_time_expression(sp):
                        continue
                    raw_speaker_sequence.append(sp)

            elif not in_front_matter and not _is_qesb_heading(stripped) and stripped:
                pass  # content line — OK

        json_speaker_sequence = [t.get("speaker_name", "") for t in transcript]

        if len(raw_speaker_sequence) != len(json_speaker_sequence):
            issues.append(Issue(
                "CMP02_SPEAKER_COUNT_MISMATCH",
                (
                    f"Raw speaker-label count ({len(raw_speaker_sequence)}) != "
                    f"transcript.json turn count ({len(json_speaker_sequence)})"
                ),
                "warning",
                evidence=(
                    f"First 10 raw: {raw_speaker_sequence[:10]}  |  "
                    f"First 10 json: {json_speaker_sequence[:10]}"
                ),
            ))
        else:
            mismatches = [
                (i, raw_speaker_sequence[i], json_speaker_sequence[i])
                for i in range(len(raw_speaker_sequence))
                if raw_speaker_sequence[i].lower() != json_speaker_sequence[i].lower()
            ]
            if mismatches:
                issues.append(Issue(
                    "CMP02_SPEAKER_SEQUENCE_MISMATCH",
                    f"{len(mismatches)} speaker-label mismatches between raw and standardized",
                    "warning",
                    evidence=str(mismatches[:5]),
                ))

    # ---------------------------------------------------------------
    # Check 3: No embedded speaker labels in turn content (structural)
    # ---------------------------------------------------------------
    for turn in transcript:
        content = turn.get("content", "")
        for line in content.split("\n"):
            line_s = line.strip()
            if not line_s or _TIME_RE.match(line_s):
                continue
            if _EMBEDDED_HASH_RE.match(line_s):
                issues.append(Issue(
                    "CMP03_EMBEDDED_HASH_SPEAKER",
                    (
                        f"Turn {turn.get('turn')}: content contains embedded "
                        f"hash-prefixed speaker label '{line_s[:60]}'"
                    ),
                    "blocking",
                    evidence=content[:200],
                ))
                break
            if _EMBEDDED_MOD_RE.match(line_s):
                issues.append(Issue(
                    "CMP03_EMBEDDED_MODERATOR_LABEL",
                    (
                        f"Turn {turn.get('turn')}: content contains embedded "
                        f"moderator label '{line_s[:60]}'"
                    ),
                    "blocking",
                    evidence=content[:200],
                ))
                break

    # ---------------------------------------------------------------
    # Check 4: QESB section heading handling
    # ---------------------------------------------------------------
    if is_qesb:
        # 4a. No heading lines inside turn content (structural)
        for turn in transcript:
            content = turn.get("content", "")
            for line in content.split("\n"):
                if _is_qesb_heading(line.strip()):
                    issues.append(Issue(
                        "CMP04_HEADING_IN_CONTENT",
                        (
                            f"Turn {turn.get('turn')}: content line is a QESB heading "
                            f"'{line.strip()[:80]}'"
                        ),
                        "blocking",
                        evidence=content[:200],
                    ))
                    break

        # 4b. Raw headings that appear in extracted text are in section_markers (requires raw_text)
        if raw_text is not None:
            raw_headings_found = set()
            for raw_line in raw_lines:
                s = raw_line.strip()
                if s and _is_qesb_heading(s):
                    raw_headings_found.add(_normalise_heading(s))

            section_marker_headings = {
                _normalise_heading(sm.get("content", ""))
                for sm in section_markers
            }
            missing_from_markers = raw_headings_found - section_marker_headings
            if missing_from_markers:
                issues.append(Issue(
                    "CMP04_HEADING_MISSING_FROM_MARKERS",
                    f"Raw headings not found in section_markers.json: "
                    f"{sorted(missing_from_markers)}",
                    "blocking",
                    evidence=(
                        f"raw_found={sorted(raw_headings_found)}, "
                        f"in_markers={sorted(section_marker_headings)}"
                    ),
                ))

    # ---------------------------------------------------------------
    # Check 5: PHIND speaker handling (structural)
    # ---------------------------------------------------------------
    if is_phind:
        for turn in transcript:
            sname = turn.get("speaker_name", "").lower()
            srole = turn.get("speaker_role", "")

            if sname in {"an", "sm", "cf"} and srole != "moderator":
                issues.append(Issue(
                    "CMP05_PHIND_FACILITATOR_NOT_MODERATOR",
                    f"Turn {turn.get('turn')}: {sname} has role '{srole}' not 'moderator'",
                    "blocking",
                ))

            if sname == "participant" and srole != "unattributed_participant":
                issues.append(Issue(
                    "CMP05_PHIND_PARTICIPANT_ROLE_WRONG",
                    f"Turn {turn.get('turn')}: generic Participant has role '{srole}'",
                    "blocking",
                ))

            sid = turn.get("speaker_id", "")
            for label in (turn.get("speaker_name", ""), sid):
                if re.match(r"^\d{1,2}:\d{2}$", label.strip()):
                    issues.append(Issue(
                        "CMP05_TIME_EXPRESSION_SPEAKER",
                        f"Turn {turn.get('turn')}: time expression '{label}' used as speaker",
                        "blocking",
                    ))

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare raw transcripts to standardized claude_v1 outputs. "
            "Uses --raw-dir to locate original DOCX/PDF/TXT files for each baseline, "
            "re-extracts text from the raw source via the same extraction logic as the "
            "pipeline, and verifies standardization fidelity. "
            "Falls back to --extracted-dir pre-extracted .txt files if raw extraction "
            "is unavailable."
        )
    )
    parser.add_argument(
        "--raw-dir",
        default=os.path.join(ROOT, "data", "human_baseline", "raw_transcripts"),
        help=(
            "Directory containing the original raw transcript files "
            "(.docx, .pdf, .txt). Looked up via baseline_metadata.json "
            "original_filename + original_file_type per baseline."
        ),
    )
    parser.add_argument(
        "--extracted-dir",
        default=None,
        help=(
            "Optional fallback directory containing pre-extracted .txt files "
            "(named <baseline_id>.txt). Used only when raw file extraction from "
            "--raw-dir fails or is unavailable. Emits CMP_FALLBACK_EXTRACTED_TEXT "
            "warning when used."
        ),
    )
    parser.add_argument(
        "--standardized-dir",
        default=os.path.join(ROOT, "data", "human_baseline", "standardized_claude_v1"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(
            ROOT, "docs", "testing", "human_baseline_standardization_claude_v1"
        ),
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if not os.path.isdir(args.standardized_dir):
        print(f"ERROR: standardized-dir not found: {args.standardized_dir}")
        raise SystemExit(1)

    baseline_dirs = sorted(
        os.path.join(args.standardized_dir, name)
        for name in os.listdir(args.standardized_dir)
        if os.path.isdir(os.path.join(args.standardized_dir, name))
    )

    report: dict = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "standardized_dir": args.standardized_dir,
        "raw_dir": args.raw_dir,
        "extracted_dir": args.extracted_dir,
        "baselines_compared": len(baseline_dirs),
        "baselines": [],
        "overall_status": "PASS",
        "total_blocking": 0,
        "total_warnings": 0,
    }

    total_blocking = 0
    total_warnings = 0

    for bd in baseline_dirs:
        bid = os.path.basename(bd)
        issues = compare_baseline(
            bid, bd,
            raw_dir=args.raw_dir,
            extracted_dir=args.extracted_dir,
        )

        extraction_source = next(
            (i.evidence for i in issues if i.check_id == "CMP_EXTRACTION_SOURCE"),
            "unknown",
        )

        blocking = [i for i in issues if i.severity == "blocking"]
        warnings = [i for i in issues if i.severity == "warning"]
        total_blocking += len(blocking)
        total_warnings += len(warnings)

        status = "PASS"
        if blocking:
            status = "BLOCKED"
        elif warnings:
            status = "WARNINGS"

        flag = (
            "[PASS]" if status == "PASS"
            else ("[BLOCKED]" if status == "BLOCKED" else "[WARN]")
        )
        print(
            f"  {flag} {bid} -- "
            f"extraction_source={extraction_source}, "
            f"blocking={len(blocking)}, warnings={len(warnings)}"
        )

        report["baselines"].append({
            "baseline_id": bid,
            "status": status,
            "extraction_source": extraction_source,
            "blocking_count": len(blocking),
            "warning_count": len(warnings),
            "issues": [i.to_dict() for i in issues if i.severity != "info"],
        })

    report["total_blocking"] = total_blocking
    report["total_warnings"] = total_warnings
    report["overall_status"] = (
        "BLOCKED" if total_blocking > 0
        else ("WARNINGS" if total_warnings > 0 else "PASS")
    )

    # Write JSON report
    json_path = os.path.join(args.output_dir, "raw_vs_standardized_comparison.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    # Write Markdown report
    md_lines = [
        "# Raw-vs-Standardized Comparison Report — Claude v1",
        "",
        f"**Run:** {report['run_timestamp']}  ",
        f"**Raw dir:** `{args.raw_dir}`  ",
        f"**Standardized dir:** `{args.standardized_dir}`  ",
        f"**Overall status:** `{report['overall_status']}`  ",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Baselines compared | {len(baseline_dirs)} |",
        f"| Total blocking issues | {total_blocking} |",
        f"| Total warnings | {total_warnings} |",
        f"| Overall status | **{report['overall_status']}** |",
        "",
        "## Per-Baseline Results",
        "",
    ]

    for b in report["baselines"]:
        icon = (
            "[PASS]" if b["status"] == "PASS"
            else ("[BLOCKED]" if b["status"] == "BLOCKED" else "[WARN]")
        )
        md_lines += [
            f"### {b['baseline_id']}",
            "",
            f"**Status:** {icon}  ",
            f"**Extraction source:** `{b['extraction_source']}`  ",
            f"**Blocking:** {b['blocking_count']} | **Warnings:** {b['warning_count']}  ",
            "",
        ]
        if b["issues"]:
            md_lines += [
                "| Check | Description | Severity |",
                "|-------|-------------|----------|",
            ]
            for iss in b["issues"]:
                desc = iss["description"][:120]
                md_lines.append(f"| `{iss['check_id']}` | {desc} | {iss['severity']} |")
            md_lines.append("")
        else:
            md_lines += ["_No issues._", ""]

    md_lines += [
        "---",
        f"*Generated by compare_raw_to_standardized_transcripts.py — "
        f"{report['run_timestamp']}*",
    ]

    md_path = os.path.join(args.output_dir, "raw_vs_standardized_comparison.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"\nComparison complete.")
    print(f"  Overall status    : {report['overall_status']}")
    print(f"  Blocking          : {total_blocking}")
    print(f"  Warnings          : {total_warnings}")
    print(f"  JSON report       : {json_path}")
    print(f"  MD report         : {md_path}")

    if total_blocking > 0:
        print("\n[WARNING] Blocking issues found. Review the comparison report for details.")
        raise SystemExit(2)
    else:
        print("\n[OK] No blocking issues.")


if __name__ == "__main__":
    main()
