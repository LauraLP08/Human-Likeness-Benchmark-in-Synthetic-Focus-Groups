"""
Phase 2 — Human Anchor Validity Scoring.

Loads filled human worksheets from analysis/coding_frame/human_anchor/,
scores each model (gemini-2.5-flash, gemini-3.5-flash) against the human
gold standard for all three transcripts, and writes a summary report.

Run ONLY after the human has filled:
  worksheet_real_fg1.csv
  worksheet_synth_fg1.csv
  worksheet_synth_fg5.csv

Usage:
    py scripts/human_anchor_score.py
"""

from __future__ import annotations

import csv
import json
import sys
import unicodedata
from pathlib import Path

import openpyxl

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from thematic_coding import _normalize_for_match  # type: ignore[attr-defined]

_ANCHOR_DIR = _REPO_ROOT / "analysis" / "coding_frame" / "human_anchor"
_CODING_DIR = _REPO_ROOT / "analysis" / "coding_frame"

_ALL_SUBTHEMES = ["A.1", "A.2", "A.3", "B.1", "B.2", "B.3", "B.4", "C.1", "C.2", "C.3", "D"]

# Map: transcript label → how to extract model present-set from the JSON report
_MODEL_PRESENT_KEYS: dict[str, tuple[str, ...]] = {
    "real_fg1":  ("gate1_run1_present_codes",),
    "synth_fg1": ("gate2_discrimination", "matched_real_fg1_vs_synth_fg1",   "target_present"),
    "synth_fg5": ("gate2_discrimination", "mismatched_real_fg1_vs_synth_fg5", "target_present"),
}

# Neutral filenames given to the coder (see _LABEL_KEY_DO_NOT_SHARE.md for mapping)
_TRANSCRIPT_FILES = {
    "real_fg1":  _ANCHOR_DIR / "transcript_1.txt",
    "synth_fg1": _ANCHOR_DIR / "transcript_2.txt",
    "synth_fg5": _ANCHOR_DIR / "transcript_3.txt",
}

_MODEL_FILES = {
    "gemini-2.5-flash": _CODING_DIR / "validation_stage1_gemini25.json",
    "gemini-3.5-flash": _CODING_DIR / "validation_stage1_gemininext.json",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dig(obj: dict, *path: str):
    for k in path:
        obj = obj[k]
    return obj


_WORKSHEET_NEUTRAL = {
    "real_fg1":  "worksheet_1.csv",
    "synth_fg1": "worksheet_2.csv",
    "synth_fg5": "worksheet_3.csv",
}


def _worksheet_path(label: str) -> Path:
    """Returns .xlsx path if the coder saved as Excel, else falls back to .csv."""
    base = _ANCHOR_DIR / _WORKSHEET_NEUTRAL[label].replace(".csv", "")
    xlsx = base.with_suffix(".xlsx")
    return xlsx if xlsx.exists() else base.with_suffix(".csv")


def _load_rows(path: Path) -> list[dict]:
    """Reads worksheet rows as list of dicts from .xlsx or .csv."""
    if path.suffix == ".xlsx":
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h) if h is not None else "" for h in rows[0]]
        return [
            {h: (str(v) if v is not None else "") for h, v in zip(headers, row)}
            for row in rows[1:]
        ]
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_human_worksheet(label: str) -> tuple[set[str], dict[str, dict]]:
    """Returns (present_set, {subtheme_id: {turn_id, quote, note}})."""
    path = _worksheet_path(label)
    if not path.exists():
        raise FileNotFoundError(f"Worksheet not found: {path}")
    present: set[str] = set()
    details: dict[str, dict] = {}
    for row in _load_rows(path):
        sid = row.get("subtheme_id", "").strip()
        yn  = row.get("present_YN", "").strip().upper()
        if yn not in ("Y", "N", ""):
            print(f"  WARNING: {label}/{sid} present_YN={yn!r} — treating as N")
            yn = "N"
        if yn == "Y":
            present.add(sid)
            details[sid] = {
                "turn_id": row.get("turn_id", "").strip(),
                "quote":   row.get("quote", "").strip(),
                "note":    row.get("note", "").strip(),
            }
        if yn == "":
            print(f"  WARNING: {label}/{sid} present_YN is blank — treating as N")
    return present, details


def _check_unfilled(label: str, present: set[str]) -> bool:
    """Returns True if worksheet looks unfilled (all present_YN are blank)."""
    path = _worksheet_path(label)
    rows = _load_rows(path)
    filled = [r for r in rows if r.get("present_YN", "").strip()]
    if not filled:
        print(f"  ERROR: {path.name} has no present_YN entries — not yet filled.")
        return True
    return False


def _load_model_present(report: dict, label: str) -> set[str]:
    keys = _MODEL_PRESENT_KEYS[label]
    val = _dig(report, *keys)
    return set(val)


def _verify_human_quotes(
    label: str, details: dict[str, dict], blind_text: str
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for sid, d in details.items():
        q = d.get("quote", "")
        if not q:
            results[sid] = False
            continue
        raw_match = q in blind_text
        norm_match = bool(_normalize_for_match(q)) and _normalize_for_match(q) in _normalize_for_match(blind_text)
        results[sid] = raw_match or norm_match
    return results


def _metrics(model_present: set[str], human_present: set[str]) -> dict:
    n = len(_ALL_SUBTHEMES)
    agree = sum(
        (s in model_present) == (s in human_present)
        for s in _ALL_SUBTHEMES
    )
    shared = model_present & human_present
    recall    = len(shared) / len(human_present) if human_present else None
    precision = len(shared) / len(model_present) if model_present else None
    return {
        "agreement":       round(agree / n, 4),
        "recall_vs_human": round(recall, 4) if recall is not None else None,
        "precision_vs_human": round(precision, 4) if precision is not None else None,
        "model_present":   sorted(model_present),
        "human_present":   sorted(human_present),
        "shared":          sorted(shared),
        "model_only":      sorted(model_present - human_present),
        "human_only":      sorted(human_present - model_present),
    }


def _per_subtheme_table(
    human_present: set[str],
    m25_present: set[str],
    mnxt_present: set[str],
) -> list[dict]:
    rows = []
    for sid in _ALL_SUBTHEMES:
        h   = "Y" if sid in human_present  else "N"
        m25 = "Y" if sid in m25_present    else "N"
        mnx = "Y" if sid in mnxt_present   else "N"
        match25  = "✓" if h == m25 else "✗"
        matchnxt = "✓" if h == mnx else "✗"
        rows.append({
            "subtheme_id":        sid,
            "human":              h,
            "gemini-2.5-flash":   m25,
            "match_25":           match25,
            "gemini-3.5-flash":   mnx,
            "match_nxt":          matchnxt,
        })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Load model reports
    model_reports: dict[str, dict] = {}
    for mname, fpath in _MODEL_FILES.items():
        if not fpath.exists():
            print(f"ERROR: {fpath} not found — run run_evaluator_comparison.py first.")
            sys.exit(1)
        with open(fpath, encoding="utf-8") as f:
            model_reports[mname] = json.load(f)

    labels = ["real_fg1", "synth_fg1", "synth_fg5"]

    # Guard: check worksheets exist and are filled
    any_unfilled = False
    for label in labels:
        ws = _worksheet_path(label)
        if not ws.exists():
            print(f"ERROR: {ws} not found — run generate_human_anchor.py first.")
            sys.exit(1)
        if _check_unfilled(label, set()):
            any_unfilled = True
    if any_unfilled:
        print("\nOne or more worksheets are not yet filled. Return here after coding.")
        sys.exit(1)

    results: dict[str, dict] = {}

    for label in labels:
        print(f"\n{'=' * 60}")
        print(f"  Transcript: {label}")
        print(f"{'=' * 60}")

        human_present, human_details = _load_human_worksheet(label)
        blind_text = _TRANSCRIPT_FILES[label].read_text(encoding="utf-8")

        # Verify human quotes
        quote_checks = _verify_human_quotes(label, human_details, blind_text)
        bad_quotes = [sid for sid, ok in quote_checks.items() if not ok]
        if bad_quotes:
            print(f"  WARNING: {len(bad_quotes)} human quote(s) not found as exact/normalized substrings:")
            for sid in bad_quotes:
                print(f"    {sid}: {human_details[sid]['quote'][:80]!r}")
        else:
            print(f"  Human quotes: all {len(quote_checks)} verified as exact substrings.")

        per_model: dict[str, dict] = {}
        for mname, report in model_reports.items():
            mp = _load_model_present(report, label)
            per_model[mname] = _metrics(mp, human_present)

        results[label] = {
            "human_present":        sorted(human_present),
            "human_quote_verified": {k: v for k, v in quote_checks.items()},
            "models":               per_model,
        }

        # Print per-subtheme table
        m25_present  = _load_model_present(model_reports["gemini-2.5-flash"], label)
        mnxt_present = _load_model_present(model_reports["gemini-3.5-flash"], label)
        table = _per_subtheme_table(human_present, m25_present, mnxt_present)

        print(f"\n  {'Subtheme':<8} {'Human':^6} {'2.5':^6} {'ok':^4} {'3.5':^6} {'ok':^4}")
        print(f"  {'-' * 38}")
        for row in table:
            print(
                f"  {row['subtheme_id']:<8} {row['human']:^6} "
                f"{row['gemini-2.5-flash']:^6} {row['match_25']:^4} "
                f"{row['gemini-3.5-flash']:^6} {row['match_nxt']:^4}"
            )

        for mname, m in per_model.items():
            print(
                f"\n  {mname}: agreement={m['agreement']:.1%}  "
                f"recall_vs_human={m['recall_vs_human']}  "
                f"precision_vs_human={m['precision_vs_human']}"
            )

    # Disputed synth FG1 codes (where models disagree)
    print(f"\n{'=' * 60}")
    print("  SYNTH FG1 — Disputed subthemes (models disagreed)")
    print(f"{'=' * 60}")
    r25  = _load_model_present(model_reports["gemini-2.5-flash"], "synth_fg1")
    rnxt = _load_model_present(model_reports["gemini-3.5-flash"], "synth_fg1")
    human_sfg1, _ = _load_human_worksheet("synth_fg1")
    disputed = [s for s in _ALL_SUBTHEMES if (s in r25) != (s in rnxt)]
    if not disputed:
        print("  No disputed codes — models agree on all subthemes for synth FG1.")
    else:
        print(f"  {'Subtheme':<8} {'2.5':^6} {'3.5':^6} {'Human':^8} {'Sided with':^14}")
        print(f"  {'-' * 50}")
        for sid in disputed:
            in25  = "Y" if sid in r25        else "N"
            innxt = "Y" if sid in rnxt       else "N"
            inh   = "Y" if sid in human_sfg1 else "N"
            if inh == in25:
                sided = "gemini-2.5-flash"
            elif inh == innxt:
                sided = "gemini-3.5-flash"
            else:
                sided = "(neither)"
            print(f"  {sid:<8} {in25:^6} {innxt:^6} {inh:^8} {sided:<14}")

    # Calibration check: real FG1 human vs models
    print(f"\n{'=' * 60}")
    print("  CALIBRATION: real FG1 human vs models")
    print(f"{'=' * 60}")
    r25_real  = _load_model_present(model_reports["gemini-2.5-flash"], "real_fg1")
    rnxt_real = _load_model_present(model_reports["gemini-3.5-flash"], "real_fg1")
    human_r1, _ = _load_human_worksheet("real_fg1")
    m25_cal  = _metrics(r25_real,  human_r1)
    mnxt_cal = _metrics(rnxt_real, human_r1)
    print(f"  gemini-2.5-flash: agreement={m25_cal['agreement']:.1%}  recall={m25_cal['recall_vs_human']}  precision={m25_cal['precision_vs_human']}")
    print(f"  gemini-3.5-flash: agreement={mnxt_cal['agreement']:.1%}  recall={mnxt_cal['recall_vs_human']}  precision={mnxt_cal['precision_vs_human']}")
    # Flag if both models diverge substantially from human on real FG1
    if m25_cal["agreement"] < 0.70 and mnxt_cal["agreement"] < 0.70:
        print("\n  FLAG: Both models agree with the human on <70% of real FG1 codes.")
        print("  The models and human coding matched earlier — check whether worksheets")
        print("  were filled after reviewing model output (would violate blind coding).")

    # Verdict
    print(f"\n{'=' * 60}")
    print("  VALIDITY VERDICT (per a-priori decision rule)")
    print(f"{'=' * 60}")
    print()
    print("  Decision rule: on SYNTHETIC transcripts (synth FG1 primary), higher")
    print("  agreement/recall/precision vs the human = more valid instrument.")
    print("  Combined with Gate 1 reliability: 3.5-flash already won repeatability.")
    print()
    m25_sfg1  = results["synth_fg1"]["models"]["gemini-2.5-flash"]
    mnxt_sfg1 = results["synth_fg1"]["models"]["gemini-3.5-flash"]
    print(f"  Synth FG1 vs human:")
    print(f"    gemini-2.5-flash:  agreement={m25_sfg1['agreement']:.1%}  recall={m25_sfg1['recall_vs_human']}  precision={m25_sfg1['precision_vs_human']}")
    print(f"    gemini-3.5-flash:  agreement={mnxt_sfg1['agreement']:.1%}  recall={mnxt_sfg1['recall_vs_human']}  precision={mnxt_sfg1['precision_vs_human']}")

    # Count how many disputed codes the human sided with each model
    n_sided_25 = n_sided_nxt = n_sided_neither = 0
    for sid in disputed:
        inh = "Y" if sid in human_sfg1 else "N"
        in25 = "Y" if sid in r25 else "N"
        innxt = "Y" if sid in rnxt else "N"
        if inh == in25:
            n_sided_25 += 1
        elif inh == innxt:
            n_sided_nxt += 1
        else:
            n_sided_neither += 1

    if disputed:
        print(f"\n  On {len(disputed)} disputed synth FG1 code(s):")
        print(f"    Human sided with gemini-2.5-flash: {n_sided_25}")
        print(f"    Human sided with gemini-3.5-flash: {n_sided_nxt}")
        print(f"    Neither:                           {n_sided_neither}")

        if n_sided_25 > n_sided_nxt:
            print("\n  IMPLICATION: Human sides with 2.5-flash on most disputed codes.")
            print("  3.5-flash is under-sensitive. Per the decision rule, do NOT finalize 3.5.")
            print("  Recommended options:")
            print("    (a) Use gemini-2.5-flash with majority-consensus coding (present if ≥3/5 runs)")
            print("    (b) Re-run gemini-3.5-flash at a higher thinking level, then re-validate.")
        elif n_sided_nxt > n_sided_25:
            print("\n  IMPLICATION: Human sides with 3.5-flash on most disputed codes.")
            print("  3.5-flash is BOTH more reliable (Gate 1 PASS) and more valid.")
            print("  RECOMMENDATION: Use gemini-3.5-flash as the primary evaluator.")
        else:
            print("\n  IMPLICATION: Disputed codes split equally or all went to neither.")
            print("  Report tie — no validity advantage for either model on disputed codes.")

    # Save JSON report
    out_path = _ANCHOR_DIR / "human_anchor_results.json"
    full_results = {
        "decision_rule": (
            "validity = agreement/recall/precision vs human on SYNTHETIC transcripts "
            "(synth_fg1 primary); combined with Gate-1 reliability (3.5 won)"
        ),
        "transcripts": results,
        "synth_fg1_disputed_codes": {
            "n_disputed": len(disputed),
            "sided_with_gemini25":   n_sided_25,
            "sided_with_gemininext": n_sided_nxt,
            "sided_with_neither":    n_sided_neither,
        },
        "calibration_real_fg1": {
            "gemini-2.5-flash": m25_cal,
            "gemini-3.5-flash": mnxt_cal,
        },
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2, default=str)
    print(f"\n  Full results saved to: {out_path.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
