"""
Verification script for human-baseline standardization (claude_v1).

Inspects every folder under --input-dir and checks:
  1. No front-matter leakage in transcript.json
  2. No back-matter leakage in transcript.json
  3. No standalone section headings as full dialogue turns in transcript.json
  4. No speaker_name I / AN / SM / CF with speaker_role = participant
  5. Moderator/facilitator turns exist where expected
  6. No time expressions became speaker labels
  7. Generic Participant: maps to unattributed_participant (not participant)
  8. No UNKNOWN_SPEAKER front-matter turns in transcript
  9. First actual dialogue turn is moderator/facilitator where expected
 10. transcript.json files are present and non-empty
 11. No embedded speaker labels inside turn content (line-start #Name: or moderator labels)
 12. No standalone QESB section headings inside turn content (any line of content)

Writes:
  <output-dir>/verification_report.md
  <output-dir>/verification_report.json
"""

import os
import json
import argparse
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Known front-matter / back-matter strings that must not appear in transcript
# ---------------------------------------------------------------------------
FRONT_MATTER_STRINGS = [
    "READ ME",
    "Copyright of this transcript",
    "Recommended citation:",
    "Reporting conventions used",
    "Date of the interview:",
    "Location: Online",
    "Pre-election transcripts:",
    "Alias | Sex",
    # Use the full table-header phrase, not standalone "Panellist" which can appear in dialogue
    "Alias | Sex | Special Category",
    "Initial Transcription by:",
    "PHIND employee group",
    "PHIND employer focus group",
    "Transcription commenced",
    "Transcription starts",
    "Transcription begins",
    "On copyright and attribution",
    "On the transcription",
]

BACK_MATTER_STRINGS = [
    "End of transcript",
    "end of transcript",
]

QESB_HEADING_STRINGS = [
    "Your Voting Story",
    "Your Voting Outcome Story",
    "Turnout Impressions",
    "Song of the Election",
    "Impressions of Results by Party",
    "One Word to Describe the Election",
    "Standout Moments from the Campaign",
    "What's Next for the Parties",
    "Advice for Parties",
]

# Moderator label names that must not appear with role = participant
MODERATOR_LABEL_NAMES = {"I", "AN", "SM", "CF", "Interviewer"}

# Time-expression patterns: should never be speaker_id or speaker_name
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_TIME_PREFIX_RE = re.compile(r"^to\s+\d", re.IGNORECASE)

# C11: Embedded speaker-label patterns inside turn content
# Hash-prefixed (DOCX artifact): #Arden: or #Arden::
_EMBEDDED_HASH_SPEAKER_RE = re.compile(r"^#[A-Za-z][A-Za-z0-9 _]*::?\s", re.IGNORECASE)
# Standalone moderator abbreviations: I: I:: AN: AN:: SM: SM:: CF: CF::
_EMBEDDED_MODERATOR_LABEL_RE = re.compile(r"^(?:I|AN|SM|CF|Interviewer)::?\s", re.IGNORECASE)
# Inline clock-time guard: 10:00 12:30 etc — do NOT flag these
_INLINE_TIME_RE = re.compile(r"^\d{1,2}:\d{2}")

# C12: Heading normalisation (same logic as parser)
def _normalise_heading_for_verify(s: str) -> str:
    s = s.strip().lower()
    s = s.rstrip("?").strip()
    s = s.replace("â€™", "")
    s = s.replace("â€˜", "")
    s = re.sub(r"['''‘’′]", "", s)
    return s

QESB_HEADING_NORMALISED = {
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

def _is_qesb_heading_line(line: str) -> bool:
    return _normalise_heading_for_verify(line) in QESB_HEADING_NORMALISED


# ---------------------------------------------------------------------------
# Finding dataclass-like structure
# ---------------------------------------------------------------------------
class Finding:
    def __init__(self, baseline_id, check_id, description,
                 classification, severity, evidence=""):
        self.baseline_id = baseline_id
        self.check_id = check_id
        self.description = description
        self.classification = classification   # true_positive | false_positive | needs_review
        self.severity = severity               # blocking | minor | info
        self.evidence = evidence

    def to_dict(self):
        return {
            "baseline_id": self.baseline_id,
            "check_id": self.check_id,
            "description": self.description,
            "classification": self.classification,
            "severity": self.severity,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Per-baseline inspection
# ---------------------------------------------------------------------------

def inspect_baseline(baseline_dir: str) -> list[Finding]:
    baseline_id = os.path.basename(baseline_dir)
    findings: list[Finding] = []

    transcript_path = os.path.join(baseline_dir, "transcript.json")
    baseline_meta_path = os.path.join(baseline_dir, "baseline_metadata.json")

    # ------------------------------------------------------------------
    # Check 10: transcript.json present and non-empty
    # ------------------------------------------------------------------
    if not os.path.exists(transcript_path):
        findings.append(Finding(
            baseline_id, "C10_MISSING_TRANSCRIPT",
            "transcript.json does not exist",
            "true_positive", "blocking",
        ))
        return findings  # cannot continue without transcript

    with open(transcript_path, encoding="utf-8") as fh:
        try:
            transcript = json.load(fh)
        except json.JSONDecodeError as exc:
            findings.append(Finding(
                baseline_id, "C10_INVALID_TRANSCRIPT",
                f"transcript.json is not valid JSON: {exc}",
                "true_positive", "blocking",
            ))
            return findings

    if not isinstance(transcript, list) or len(transcript) == 0:
        findings.append(Finding(
            baseline_id, "C10_EMPTY_TRANSCRIPT",
            "transcript.json is empty (zero turns)",
            "true_positive", "blocking",
        ))
        return findings

    # ------------------------------------------------------------------
    # Detect dataset type from baseline_id
    # ------------------------------------------------------------------
    bl_lower = baseline_id.lower()
    is_qesb = "qesb" in bl_lower
    is_phind = (
        "work at home" in bl_lower
        or "employee" in bl_lower
        or "employer" in bl_lower
    )

    # ------------------------------------------------------------------
    # Check 1: Front-matter leakage
    # ------------------------------------------------------------------
    for turn in transcript:
        content = turn.get("content", "")
        for fm_str in FRONT_MATTER_STRINGS:
            if fm_str.lower() in content.lower():
                findings.append(Finding(
                    baseline_id, "C01_FRONT_MATTER_LEAKAGE",
                    f"Front-matter string found in turn {turn.get('turn')}: '{fm_str}'",
                    "true_positive", "blocking",
                    evidence=content[:200],
                ))

    # ------------------------------------------------------------------
    # Check 2: Back-matter leakage
    # ------------------------------------------------------------------
    for turn in transcript:
        content = turn.get("content", "")
        for bm_str in BACK_MATTER_STRINGS:
            if bm_str.lower() in content.lower():
                findings.append(Finding(
                    baseline_id, "C02_BACK_MATTER_LEAKAGE",
                    f"Back-matter string found in turn {turn.get('turn')}: '{bm_str}'",
                    "true_positive", "blocking",
                    evidence=content[:200],
                ))

    # ------------------------------------------------------------------
    # Check 3: Section headings in transcript
    # ------------------------------------------------------------------
    if is_qesb:
        for turn in transcript:
            content = turn.get("content", "").strip()
            for h in QESB_HEADING_STRINGS:
                if content.lower() == h.lower():
                    findings.append(Finding(
                        baseline_id, "C03_HEADING_IN_TRANSCRIPT",
                        f"Standalone QESB heading found as dialogue turn {turn.get('turn')}: '{content}'",
                        "true_positive", "blocking",
                        evidence=content,
                    ))

    # ------------------------------------------------------------------
    # Check 4: Moderator labels with participant role
    # ------------------------------------------------------------------
    for turn in transcript:
        sname = turn.get("speaker_name", "")
        srole = turn.get("speaker_role", "")
        if sname in MODERATOR_LABEL_NAMES and srole == "participant":
            findings.append(Finding(
                baseline_id, "C04_MODERATOR_LABEL_AS_PARTICIPANT",
                f"Turn {turn.get('turn')}: speaker_name='{sname}' has role 'participant'",
                "true_positive", "blocking",
                evidence=turn.get("content", "")[:200],
            ))

    # ------------------------------------------------------------------
    # Check 5: Moderator turns exist
    # ------------------------------------------------------------------
    mod_turns = [t for t in transcript if t.get("speaker_role") == "moderator"]
    if not mod_turns:
        findings.append(Finding(
            baseline_id, "C05_NO_MODERATOR_TURNS",
            "No moderator turns found in transcript",
            "true_positive", "blocking",
        ))

    # ------------------------------------------------------------------
    # Check 6: Time expressions as speaker labels
    # ------------------------------------------------------------------
    for turn in transcript:
        sname = turn.get("speaker_name", "")
        sid = turn.get("speaker_id", "")
        for label in (sname, sid):
            if _TIME_RE.match(label.strip()) or _TIME_PREFIX_RE.match(label.strip()):
                findings.append(Finding(
                    baseline_id, "C06_TIME_EXPRESSION_SPEAKER",
                    f"Turn {turn.get('turn')}: time-like label '{label}' used as speaker",
                    "true_positive", "blocking",
                    evidence=turn.get("content", "")[:200],
                ))

    # ------------------------------------------------------------------
    # Check 7: Generic Participant: maps to unattributed_participant
    # ------------------------------------------------------------------
    for turn in transcript:
        sname = turn.get("speaker_name", "")
        srole = turn.get("speaker_role", "")
        if sname.strip().lower() == "participant" and srole != "unattributed_participant":
            findings.append(Finding(
                baseline_id, "C07_PARTICIPANT_ROLE_INFLATION",
                f"Turn {turn.get('turn')}: generic 'Participant' has role '{srole}' not 'unattributed_participant'",
                "true_positive", "blocking",
                evidence=turn.get("content", "")[:200],
            ))

    # Also verify baseline_metadata participant_count_detected excludes unattributed
    if os.path.exists(baseline_meta_path):
        with open(baseline_meta_path, encoding="utf-8") as fh:
            try:
                bmeta = json.load(fh)
                unattributed_count = sum(
                    1 for t in transcript
                    if t.get("speaker_role") == "unattributed_participant"
                )
                if unattributed_count > 0:
                    actual_named = len({
                        t["speaker_id"] for t in transcript
                        if t.get("speaker_role") == "participant"
                    })
                    reported = bmeta.get("participant_count_detected", -1)
                    if reported != actual_named:
                        findings.append(Finding(
                            baseline_id, "C07B_PARTICIPANT_COUNT_INFLATED",
                            (
                                f"participant_count_detected={reported} but named participants={actual_named}; "
                                f"unattributed_participant turns={unattributed_count}"
                            ),
                            "true_positive", "minor",
                        ))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Check 8: UNKNOWN_SPEAKER front-matter turns
    # ------------------------------------------------------------------
    for turn in transcript:
        if turn.get("speaker_id") == "UNKNOWN_SPEAKER":
            content = turn.get("content", "")
            # Check if the content looks like front matter
            looks_like_fm = any(
                fm.lower() in content.lower() for fm in FRONT_MATTER_STRINGS
            )
            if looks_like_fm:
                findings.append(Finding(
                    baseline_id, "C08_UNKNOWN_SPEAKER_FRONT_MATTER",
                    f"Turn {turn.get('turn')}: UNKNOWN_SPEAKER with front-matter content",
                    "true_positive", "blocking",
                    evidence=content[:200],
                ))
            else:
                findings.append(Finding(
                    baseline_id, "C08_UNKNOWN_SPEAKER",
                    f"Turn {turn.get('turn')}: UNKNOWN_SPEAKER (may need review)",
                    "needs_review", "minor",
                    evidence=content[:200],
                ))

    # ------------------------------------------------------------------
    # Check 9: First actual dialogue turn is moderator
    # ------------------------------------------------------------------
    if transcript:
        first_turn = transcript[0]
        first_role = first_turn.get("speaker_role", "")
        if first_role != "moderator":
            severity = "minor"
            cls = "needs_review"
            # For QESB, first turn should always be moderator (I:)
            # For PHIND, first turn should always be AN/SM/CF
            if is_qesb or is_phind:
                severity = "blocking"
                cls = "true_positive"
            findings.append(Finding(
                baseline_id, "C09_FIRST_TURN_NOT_MODERATOR",
                (
                    f"First dialogue turn (turn 0) has role '{first_role}', "
                    f"speaker='{first_turn.get('speaker_name')}'"
                ),
                cls, severity,
                evidence=first_turn.get("content", "")[:200],
            ))

    # ------------------------------------------------------------------
    # Check 11: No embedded speaker labels inside turn content
    # Catches cases where #Name: or I:/AN:/SM:/CF: appear mid-content
    # (a sign the parser failed to split those as new turns).
    # ------------------------------------------------------------------
    for turn in transcript:
        content = turn.get("content", "")
        for line in content.split("\n"):
            line_s = line.strip()
            if not line_s:
                continue
            if _INLINE_TIME_RE.match(line_s):
                continue  # e.g. "10:00 to 11:00" — not a speaker label
            if _EMBEDDED_HASH_SPEAKER_RE.match(line_s):
                findings.append(Finding(
                    baseline_id, "C11_EMBEDDED_SPEAKER_LABEL",
                    (
                        f"Turn {turn.get('turn')}: content contains embedded "
                        f"hash-prefixed speaker label '{line_s[:60]}'"
                    ),
                    "true_positive", "blocking",
                    evidence=content[:300],
                ))
                break
            if _EMBEDDED_MODERATOR_LABEL_RE.match(line_s):
                findings.append(Finding(
                    baseline_id, "C11_EMBEDDED_MODERATOR_LABEL",
                    (
                        f"Turn {turn.get('turn')}: content contains embedded "
                        f"moderator label '{line_s[:60]}'"
                    ),
                    "true_positive", "blocking",
                    evidence=content[:300],
                ))
                break

    # ------------------------------------------------------------------
    # Check 12: No standalone QESB section headings inside turn content
    # Checks every line of every turn's content against the heading set.
    # ------------------------------------------------------------------
    if is_qesb:
        for turn in transcript:
            content = turn.get("content", "")
            for line in content.split("\n"):
                line_s = line.strip()
                if not line_s:
                    continue
                if _is_qesb_heading_line(line_s):
                    findings.append(Finding(
                        baseline_id, "C12_HEADING_INSIDE_CONTENT",
                        (
                            f"Turn {turn.get('turn')}: content line is a QESB section heading "
                            f"'{line_s[:80]}'"
                        ),
                        "true_positive", "blocking",
                        evidence=content[:300],
                    ))
                    break

    # ------------------------------------------------------------------
    # Info: canonical_speaker_id present on all turns
    # ------------------------------------------------------------------
    missing_cid = [
        t.get("turn") for t in transcript
        if "canonical_speaker_id" not in t
    ]
    if missing_cid:
        findings.append(Finding(
            baseline_id, "C_SCHEMA_MISSING_CANONICAL_ID",
            f"canonical_speaker_id missing from {len(missing_cid)} turns: {missing_cid[:5]}",
            "true_positive", "minor",
        ))

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Verify human-baseline standardization outputs."
    )
    parser.add_argument(
        "--input-dir",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "human_baseline", "standardized_claude_v1",
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs", "testing", "human_baseline_standardization_claude_v1",
        ),
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if not os.path.isdir(args.input_dir):
        print(f"ERROR: input-dir does not exist: {args.input_dir}")
        raise SystemExit(1)

    baseline_dirs = sorted(
        d for d in (
            os.path.join(args.input_dir, name)
            for name in os.listdir(args.input_dir)
        )
        if os.path.isdir(d)
    )

    if not baseline_dirs:
        print("WARNING: No baseline directories found.")

    all_findings: list[Finding] = []
    summary: dict = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "input_dir": args.input_dir,
        "baselines_inspected": len(baseline_dirs),
        "baselines": [],
    }

    for bd in baseline_dirs:
        bid = os.path.basename(bd)
        findings = inspect_baseline(bd)
        all_findings.extend(findings)

        tp_blocking = [
            f for f in findings
            if f.classification == "true_positive" and f.severity == "blocking"
        ]
        tp_minor = [
            f for f in findings
            if f.classification == "true_positive" and f.severity == "minor"
        ]
        needs_review = [f for f in findings if f.classification == "needs_review"]
        fp = [f for f in findings if f.classification == "false_positive"]

        # Count turns for reporting
        tp = os.path.join(bd, "transcript.json")
        turn_count = 0
        if os.path.exists(tp):
            with open(tp, encoding="utf-8") as fh:
                try:
                    turn_count = len(json.load(fh))
                except Exception:
                    pass

        status = "PASS"
        if tp_blocking:
            status = "BLOCKED"
        elif tp_minor or needs_review:
            status = "WARNINGS"

        summary["baselines"].append({
            "baseline_id": bid,
            "turn_count": turn_count,
            "status": status,
            "blocking_true_positives": len(tp_blocking),
            "minor_true_positives": len(tp_minor),
            "needs_review": len(needs_review),
            "false_positives": len(fp),
            "findings": [f.to_dict() for f in findings],
        })

        flag = "[PASS]" if status == "PASS" else ("[BLOCKED]" if status == "BLOCKED" else "[WARN]")
        print(
            f"  {flag} {bid} -- {turn_count} turns, "
            f"blocking={len(tp_blocking)}, minor={len(tp_minor)}, "
            f"needs_review={len(needs_review)}"
        )

    # Overall stats
    total_blocking_tp = sum(
        b["blocking_true_positives"] for b in summary["baselines"]
    )
    total_minor_tp = sum(b["minor_true_positives"] for b in summary["baselines"])
    total_needs_review = sum(b["needs_review"] for b in summary["baselines"])
    pass_count = sum(1 for b in summary["baselines"] if b["status"] == "PASS")
    blocked_count = sum(1 for b in summary["baselines"] if b["status"] == "BLOCKED")
    warn_count = sum(1 for b in summary["baselines"] if b["status"] == "WARNINGS")

    overall_status = "PASS"
    if total_blocking_tp > 0:
        overall_status = "BLOCKED"
    elif total_minor_tp > 0 or total_needs_review > 0:
        overall_status = "WARNINGS"

    summary["overall_status"] = overall_status
    summary["total_blocking_true_positives"] = total_blocking_tp
    summary["total_minor_true_positives"] = total_minor_tp
    summary["total_needs_review"] = total_needs_review
    summary["baselines_pass"] = pass_count
    summary["baselines_blocked"] = blocked_count
    summary["baselines_warnings"] = warn_count
    summary["completion_blocked"] = total_blocking_tp > 0

    # ------------------------------------------------------------------
    # Write JSON report
    # ------------------------------------------------------------------
    json_report_path = os.path.join(args.output_dir, "verification_report.json")
    with open(json_report_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Write Markdown report
    # ------------------------------------------------------------------
    md_lines = [
        "# Human Baseline Standardization Verification Report — Claude v1",
        "",
        f"**Run:** {summary['run_timestamp']}  ",
        f"**Input dir:** `{args.input_dir}`  ",
        f"**Overall status:** `{overall_status}`  ",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Baselines inspected | {len(baseline_dirs)} |",
        f"| Baselines PASS | {pass_count} |",
        f"| Baselines WARNINGS | {warn_count} |",
        f"| Baselines BLOCKED | {blocked_count} |",
        f"| Total blocking true-positives | {total_blocking_tp} |",
        f"| Total minor true-positives | {total_minor_tp} |",
        f"| Total needs-review | {total_needs_review} |",
        f"| **Completion blocked** | **{'YES — fix blocking issues first' if total_blocking_tp > 0 else 'NO'}** |",
        "",
        "## Per-Baseline Results",
        "",
    ]

    for b in summary["baselines"]:
        status_icon = (
            "[PASS]" if b["status"] == "PASS"
            else ("[BLOCKED]" if b["status"] == "BLOCKED" else "[WARNINGS]")
        )
        md_lines += [
            f"### {b['baseline_id']}",
            "",
            f"**Status:** {status_icon}  ",
            f"**Turns:** {b['turn_count']}  ",
            f"**Blocking true-positives:** {b['blocking_true_positives']}  ",
            f"**Minor true-positives:** {b['minor_true_positives']}  ",
            f"**Needs-review:** {b['needs_review']}  ",
            "",
        ]
        if b["findings"]:
            md_lines.append("| Check | Description | Class | Severity |")
            md_lines.append("|-------|-------------|-------|----------|")
            for f in b["findings"]:
                ev = f["evidence"].replace("\n", " ")[:80] if f["evidence"] else ""
                desc = f["description"][:100]
                md_lines.append(
                    f"| `{f['check_id']}` | {desc} | {f['classification']} | {f['severity']} |"
                )
            md_lines.append("")
        else:
            md_lines += ["_No findings._", ""]

    md_lines += [
        "## Verification Checks",
        "",
        "| # | Check | Status |",
        "|---|-------|--------|",
            "| C01 | No front-matter leakage in transcript.json | " + ("FAIL" if any(b["findings"] and any(f["check_id"] == "C01_FRONT_MATTER_LEAKAGE" for f in b["findings"]) for b in summary["baselines"]) else "PASS") + " |",
        "| C02 | No back-matter leakage in transcript.json | " + ("FAIL" if any(f.check_id == "C02_BACK_MATTER_LEAKAGE" for f in all_findings) else "PASS") + " |",
        "| C03 | No standalone section headings in transcript.json | " + ("FAIL" if any(f.check_id == "C03_HEADING_IN_TRANSCRIPT" for f in all_findings) else "PASS") + " |",
        "| C04 | No I/AN/SM/CF with role=participant | " + ("FAIL" if any(f.check_id == "C04_MODERATOR_LABEL_AS_PARTICIPANT" for f in all_findings) else "PASS") + " |",
        "| C05 | Moderator turns present | " + ("FAIL" if any(f.check_id == "C05_NO_MODERATOR_TURNS" for f in all_findings) else "PASS") + " |",
        "| C06 | No time expressions as speaker labels | " + ("FAIL" if any(f.check_id == "C06_TIME_EXPRESSION_SPEAKER" for f in all_findings) else "PASS") + " |",
        "| C07 | Generic Participant maps to unattributed_participant | " + ("FAIL" if any(f.check_id == "C07_PARTICIPANT_ROLE_INFLATION" for f in all_findings) else "PASS") + " |",
        "| C08 | No UNKNOWN_SPEAKER front-matter turns | " + ("FAIL" if any(f.check_id == "C08_UNKNOWN_SPEAKER_FRONT_MATTER" for f in all_findings) else "PASS") + " |",
        "| C09 | First dialogue turn is moderator | " + ("FAIL" if any(f.check_id == "C09_FIRST_TURN_NOT_MODERATOR" and f.severity == "blocking" for f in all_findings) else "PASS") + " |",
        "| C10 | transcript.json present and non-empty | " + ("FAIL" if any(f.check_id.startswith("C10_") for f in all_findings) else "PASS") + " |",
        "| C11 | No embedded speaker labels inside turn content | " + ("FAIL" if any(f.check_id.startswith("C11_") for f in all_findings) else "PASS") + " |",
        "| C12 | No QESB section headings inside turn content | " + ("FAIL" if any(f.check_id == "C12_HEADING_INSIDE_CONTENT" for f in all_findings) else "PASS") + " |",
        "",
        "---",
        f"*Generated by verify_human_baseline_standardization.py — {summary['run_timestamp']}*",
    ]

    md_report_path = os.path.join(args.output_dir, "verification_report.md")
    with open(md_report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"\nVerification complete.")
    print(f"  Overall status : {overall_status}")
    print(f"  Blocking TPs   : {total_blocking_tp}")
    print(f"  Minor TPs      : {total_minor_tp}")
    print(f"  Needs review   : {total_needs_review}")
    print(f"  JSON report    : {json_report_path}")
    print(f"  MD report      : {md_report_path}")

    if total_blocking_tp > 0:
        print("\n[WARNING] Completion is BLOCKED. Fix blocking findings before proceeding to Stage 7C.")
        raise SystemExit(2)
    else:
        print("\n[OK] No blocking issues. Proceeding is safe.")


if __name__ == "__main__":
    main()
