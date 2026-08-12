"""
Run Stage-1 validation (Gates 1/2/3) for BOTH Gemini evaluators and produce a
side-by-side comparison so we can choose the instrument on evidence.

Models run through the IDENTICAL pipeline (same codebook, same prompt, same
quote-verification). Only model + key + temperature-vs-thinking differ.

Outputs:
  analysis/coding_frame/validation_stage1_gemini25.json
  analysis/coding_frame/validation_stage1_gemininext.json
  docs/findings/2026-07-18_evaluator_model_comparison.md

Usage:
    py scripts/run_evaluator_comparison.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from thematic_coding import EVALUATOR_CONFIGS, load_codebook
from validate_thematic_measure import (
    REPEATABILITY_THRESHOLD,
    main as run_validation,
)

_OUT_DIR  = _REPO_ROOT / "analysis" / "coding_frame"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"


# ---------------------------------------------------------------------------
# Run one evaluator through the full Stage-1 pipeline
# ---------------------------------------------------------------------------

def _run_one(key: str) -> dict:
    cfg      = EVALUATOR_CONFIGS[key]
    out_path = _OUT_DIR / f"validation_stage1_{key}.json"
    if out_path.exists():
        print(f"\n[{key}] Result file already exists — loading without re-running: {out_path.name}")
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    print(f"\n{'#' * 65}")
    print(f"  RUNNING EVALUATOR: {key}  ({cfg['model']})")
    print(f"{'#' * 65}\n")
    run_validation(out_path=out_path, evaluator_cfg=cfg)
    with open(out_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Inter-model agreement
# ---------------------------------------------------------------------------

def _compute_agreement(
    codebook_ids: list[str],
    present_a: set[str],
    present_b: set[str],
) -> tuple[float, list[str]]:
    agree_n     = sum((cid in present_a) == (cid in present_b) for cid in codebook_ids)
    disagree    = [cid for cid in codebook_ids if (cid in present_a) != (cid in present_b)]
    return agree_n / len(codebook_ids), disagree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    return f"{v:.1%}"


def _g(obj: dict, *path: str):
    for k in path:
        obj = obj[k]
    return obj


def _sum_stat(r: dict, field: str) -> int:
    return sum(
        v.get(field, 0)
        for v in _g(r, "gate3_quote_validity", "per_transcript").values()
    )


def _winner(
    w25: float, wnxt: float,
    g1_pass_25: bool, g1_pass_nxt: bool,
    margin25: float, marginnxt: float,
    qr25: float, qrnxt: float,
) -> str:
    if g1_pass_25 and not g1_pass_nxt:
        return f"gemini-2.5-flash — gemini-3.5-flash fails Gate 1 ({_fmt(wnxt)} < {_fmt(REPEATABILITY_THRESHOLD)})"
    if g1_pass_nxt and not g1_pass_25:
        return f"gemini-3.5-flash — gemini-2.5-flash fails Gate 1 ({_fmt(w25)} < {_fmt(REPEATABILITY_THRESHOLD)})"
    if abs(w25 - wnxt) >= 0.01:
        m = "gemini-2.5-flash" if w25 > wnxt else "gemini-3.5-flash"
        return f"{m} — higher Gate 1 worst pairwise ({_fmt(max(w25, wnxt))} vs {_fmt(min(w25, wnxt))})"
    if abs(margin25 - marginnxt) > 0.01:
        m = "gemini-2.5-flash" if margin25 > marginnxt else "gemini-3.5-flash"
        return f"{m} — larger Gate 2 discrimination margin"
    if abs(qr25 - qrnxt) > 0.02:
        m = "gemini-2.5-flash" if qr25 > qrnxt else "gemini-3.5-flash"
        return f"{m} — higher raw quote verification rate"
    return "tie — no substantive difference by the a-priori decision rule"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    results: dict[str, dict] = {}
    for key in ("gemini25", "gemininext"):
        results[key] = _run_one(key)

    codebook     = load_codebook()
    codebook_ids = [c["subtheme_id"] for c in codebook]

    r25  = results["gemini25"]
    rnxt = results["gemininext"]

    present_25  = set(r25.get("gate1_run1_present_codes", []))
    present_nxt = set(rnxt.get("gate1_run1_present_codes", []))
    agreement_pct, disagree_ids = _compute_agreement(codebook_ids, present_25, present_nxt)

    # ---- Extract key numbers ------------------------------------------------
    w25      = _g(r25,  "gate1_repeatability", "worst_pairwise")
    wnxt     = _g(rnxt, "gate1_repeatability", "worst_pairwise")
    aw25     = _g(r25,  "gate1_repeatability", "all_way_agreement")
    awnxt    = _g(rnxt, "gate1_repeatability", "all_way_agreement")

    m25_r    = _g(r25,  "gate2_discrimination", "matched_real_fg1_vs_synth_fg1",    "subtheme_recall")
    mm25_r   = _g(r25,  "gate2_discrimination", "mismatched_real_fg1_vs_synth_fg5",  "subtheme_recall")
    margin25 = _g(r25,  "gate2_discrimination", "recall_margin")
    m25_str  = _g(r25,  "gate2_discrimination", "margin_strength")

    mnxt_r    = _g(rnxt, "gate2_discrimination", "matched_real_fg1_vs_synth_fg1",    "subtheme_recall")
    mmnxt_r   = _g(rnxt, "gate2_discrimination", "mismatched_real_fg1_vs_synth_fg5",  "subtheme_recall")
    marginnxt = _g(rnxt, "gate2_discrimination", "recall_margin")
    mnxt_str  = _g(rnxt, "gate2_discrimination", "margin_strength")

    agg25  = _g(r25,  "gate3_quote_validity", "aggregate")
    aggnxt = _g(rnxt, "gate3_quote_validity", "aggregate")

    raw25    = _sum_stat(r25,  "raw_exact_quotes")
    rawnxt   = _sum_stat(rnxt, "raw_exact_quotes")
    norm25   = _sum_stat(r25,  "normalized_recovered_quotes")
    normnxt  = _sum_stat(rnxt, "normalized_recovered_quotes")

    g1_pass_25  = r25["gate1_repeatability"]["passed"]
    g1_pass_nxt = rnxt["gate1_repeatability"]["passed"]
    g2_pass_25  = r25["gate2_discrimination"]["passed"]
    g2_pass_nxt = rnxt["gate2_discrimination"]["passed"]
    g3_pass_25  = r25["gate3_quote_validity"]["passed"]
    g3_pass_nxt = rnxt["gate3_quote_validity"]["passed"]

    qr25  = agg25["quote_verification_rate"]
    qrnxt = aggnxt["quote_verification_rate"]

    verdict = _winner(w25, wnxt, g1_pass_25, g1_pass_nxt, margin25, marginnxt, qr25, qrnxt)

    cfg25  = EVALUATOR_CONFIGS["gemini25"]
    cfgnxt = EVALUATOR_CONFIGS["gemininext"]
    param25  = f"temperature={cfg25['temperature']}"
    paramnxt = (
        f"thinking_level={cfgnxt['thinking_level']}"
        if cfgnxt.get("thinking_level")
        else f"temperature={cfgnxt.get('temperature')}"
    )

    # ---- Write markdown report ----------------------------------------------
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _DOCS_DIR / "2026-07-18_evaluator_model_comparison.md"

    lines: list[str] = [
        "# Evaluator Model Comparison: gemini-2.5-flash vs gemini-3.5-flash",
        "",
        "**Date:** 2026-07-18  ",
        "**Pipeline:** Stage-1 validation (Gates 1 / 2 / 3)  ",
        "**Decision rule:** fixed a priori — NOT selected post-hoc on results.",
        "",
        "## A-Priori Decision Rule",
        "",
        "Rank by, in this priority order:",
        "",
        "1. **Gate 1 repeatability** — worst pairwise code-vector agreement across 5 runs.",
        "   Must be ≥85%; higher is better. Failure here alone disqualifies the model.",
        "2. **Gate 2 discrimination margin** — matched recall − mismatched recall; larger = better.",
        "3. **Gate 3 raw-exact quote rate** — higher verbatim quoting = better grounding.",
        "",
        "> **Higher fidelity scores do NOT mean a better evaluator.** An instrument that",
        "> over-marks codes present is worse, not better. The winner is the more reliable",
        "> and better-grounded measuring instrument.",
        "",
        "## Comparison Table",
        "",
        "| Criterion | gemini-2.5-flash | gemini-3.5-flash |",
        "|-----------|:----------------:|:----------------:|",
        f"| **Model ID** | `{cfg25['model']}` | `{cfgnxt['model']}` |",
        f"| **Params** | {param25} | {paramnxt} |",
        "| **— Gate 1: Repeatability —** | | |",
        f"| Worst pairwise agreement | {_fmt(w25)} {'✓' if g1_pass_25 else '✗ **FAIL**'} | {_fmt(wnxt)} {'✓' if g1_pass_nxt else '✗ **FAIL**'} |",
        f"| All-way agreement (5 runs) | {_fmt(aw25)} | {_fmt(awnxt)} |",
        f"| Gate 1 result | **{'PASS' if g1_pass_25 else 'FAIL'}** | **{'PASS' if g1_pass_nxt else 'FAIL'}** |",
        "| **— Gate 2: Discrimination —** | | |",
        f"| Matched recall (real FG1 vs synth FG1) | {m25_r:.3f} | {mnxt_r:.3f} |",
        f"| Mismatched recall (real FG1 vs synth FG5) | {mm25_r:.3f} | {mmnxt_r:.3f} |",
        f"| Recall margin | {margin25:+.3f} ({m25_str}) | {marginnxt:+.3f} ({mnxt_str}) |",
        f"| Gate 2 result | **{'PASS' if g2_pass_25 else 'FAIL'}** | **{'PASS' if g2_pass_nxt else 'FAIL'}** |",
        "| **— Gate 3: Quote Grounding —** | | |",
        f"| Raw-exact quotes | {raw25} | {rawnxt} |",
        f"| Normalization-recovered | {norm25} | {normnxt} |",
        f"| Quote verification rate | {_fmt(qr25)} | {_fmt(qrnxt)} |",
        f"| Code preservation rate | {_fmt(agg25['code_preservation_rate'])} | {_fmt(aggnxt['code_preservation_rate'])} |",
        f"| Gate 3 result | **{'PASS' if g3_pass_25 else 'FAIL'}** | **{'PASS' if g3_pass_nxt else 'FAIL'}** |",
        "| **— Inter-model agreement —** | | |",
        f"| Code-presence agreement on real FG1 (run 1) | colspan=2: {_fmt(agreement_pct)} across {len(codebook_ids)} subthemes |",
        "",
        "## Inter-Model Agreement on Real FG1",
        "",
        f"Agreement on code presence/absence: **{_fmt(agreement_pct)}**"
        f" ({len(codebook_ids) - len(disagree_ids)}/{len(codebook_ids)} subthemes agree).",
        "",
    ]

    if disagree_ids:
        lines += [
            f"Subthemes where models disagree ({len(disagree_ids)}):",
            "",
        ]
        for sid in sorted(disagree_ids):
            in25  = "present" if sid in present_25  else "absent"
            innxt = "present" if sid in present_nxt else "absent"
            lines.append(f"- `{sid}`: gemini-2.5-flash → {in25},  gemini-3.5-flash → {innxt}")
        lines.append("")
    else:
        lines += ["Both models agree on all subtheme codes for real FG1 run 1.", ""]

    # Human reference
    human_ref = list((_REPO_ROOT / "analysis" / "coding_frame").glob("human_codes*.json"))
    lines += ["## Human-Coded Reference", ""]
    if human_ref:
        lines += [
            f"Found: {[p.name for p in human_ref]}",
            "Agreement with human reference not computed here — use as tiebreaker if needed.",
            "",
        ]
    else:
        lines += [
            "No human-coded reference file found in `analysis/coding_frame/`.",
            "This tiebreaker is not available for this comparison.",
            "",
        ]

    lines += [
        "## Verdict",
        "",
        f"**{verdict}**",
        "",
    ]

    if not g1_pass_nxt:
        lines += [
            f"> gemini-3.5-flash worst pairwise = {_fmt(wnxt)}, below the {_fmt(REPEATABILITY_THRESHOLD)} threshold.",
            "> **Gate 1 failure alone disqualifies it as the primary evaluator.**",
            "> Use gemini-2.5-flash for the dissertation batch.",
            "",
        ]
    elif not g1_pass_25:
        lines += [
            f"> gemini-2.5-flash worst pairwise = {_fmt(w25)}, below the {_fmt(REPEATABILITY_THRESHOLD)} threshold.",
            "> Gate 1 failure alone disqualifies it as the primary evaluator.",
            "",
        ]

    lines += [
        "## Configs Used",
        "",
        f"- `gemini25`: `{cfg25['model']}`, {param25}, key=`{cfg25['key_env']}`",
        f"- `gemininext`: `{cfgnxt['model']}`, {paramnxt}, key=`{cfgnxt['key_env']}`",
        "",
        "Full JSON reports:",
        "- `analysis/coding_frame/validation_stage1_gemini25.json`",
        "- `analysis/coding_frame/validation_stage1_gemininext.json`",
        "",
        "_Auto-generated by `scripts/run_evaluator_comparison.py`._",
    ]

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- Console summary ----------------------------------------------------
    W = 46
    print(f"\n{'=' * 65}")
    print("  EVALUATOR COMPARISON SUMMARY")
    print(f"{'=' * 65}")
    print(f"\n  {'Criterion':<{W}} {'gemini-2.5-flash':>12}  {'gemini-3.5-flash':>12}")
    print(f"  {'-' * (W + 28)}")
    print(f"  {'Gate 1 worst pairwise (≥85%)':<{W}} {_fmt(w25):>10} {'✓' if g1_pass_25 else '✗':>2}  {_fmt(wnxt):>10} {'✓' if g1_pass_nxt else '✗':>2}")
    print(f"  {'Gate 1 all-way agreement':<{W}} {_fmt(aw25):>12}  {_fmt(awnxt):>12}")
    print(f"  {'Gate 2 discrimination margin':<{W}} {margin25:>+12.3f}  {marginnxt:>+12.3f}")
    print(f"  {'Gate 3 quote verification rate':<{W}} {_fmt(qr25):>12}  {_fmt(qrnxt):>12}")
    print(f"  {'Gate 3 raw-exact quotes':<{W}} {raw25:>12}  {rawnxt:>12}")
    print(f"  {'Gate 3 normalization-recovered':<{W}} {norm25:>12}  {normnxt:>12}")
    print(f"  {'Inter-model agreement (real FG1 run 1)':<{W}} {_fmt(agreement_pct):>27}")
    print(f"\n  VERDICT: {verdict}")
    print(f"\n  Comparison report: {md_path.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
