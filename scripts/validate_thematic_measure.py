"""
Stage 1 validation gates for the LLM-assisted, evidence-constrained thematic
fidelity measure (Gemini blind evaluator).

Three mandatory gates — ALL must pass before the measure is used on experiment data:

  Gate 1  REPEATABILITY   Code the same transcript 3×. Report pairwise code-vector
                          agreement (%). Threshold ≥85% worst pairwise.

  Gate 2  DISCRIMINATION  Real FG1 anchor vs:
            (a) UPPER BOUND:  real FG1 self (sanity check — expect ~1.0 recall)
            (b) MATCHED:      synthetic FG1 (costfix_validation_fg1) ← pass criterion
            (c) MISMATCHED:   synthetic FG5 (costfix_validation_fg5)
          Pass = matched subtheme recall > mismatched subtheme recall (non-trivially).
          MARGIN is reported — a tiny margin is a weak measure even if it passes.

  Gate 3  QUOTE VALIDITY  % quotes verified as exact substrings ≥80%; % positive
                          codes with verified evidence ≥90%. Low rates are a
                          reportable finding about Gemini's evidentiary reliability,
                          not merely a binary gate.

SCOPE NOTE: A PASS validates the measure FOR MACHO MEALS (English, this codebook).
It does NOT validate the Spanish/multilingual path (SF dataset) — that requires
Stage 2's sentence-transformer cross-check, which is untested here.

GEMINI CALLS: 3 (real FG1 repeatability) + 2 (synth FG1, synth FG5) = 5 Tier-1 calls.

Usage:
    py scripts/validate_thematic_measure.py
    py scripts/validate_thematic_measure.py --out analysis/coding_frame/validation_stage1.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from thematic_coding import (
    QuoteValidityStats,
    Tier1Result,
    TierOneScores,
    code_transcript_tier1,
    compute_tier1_scores,
    load_codebook,
    to_blind_text,
)

# ---------------------------------------------------------------------------
# Gate thresholds (explicit and reportable)
# ---------------------------------------------------------------------------
# Force UTF-8 stdout so Unicode in print() works on Windows cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPEATABILITY_THRESHOLD = 0.85   # min pairwise code-vector agreement across 3 runs
QUOTE_VERIFY_THRESHOLD  = 0.80   # min fraction of quotes that are exact substrings
CODE_PRESERVE_THRESHOLD = 0.90   # min fraction of positive codes with verified evidence


# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------

def _load_transcript(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _real_transcript_path(group: str) -> Path:
    return (
        _REPO_ROOT
        / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
        / group / "transcript.json"
    )


def _synth_transcript_path(session_name: str) -> Path:
    return _REPO_ROOT / "output" / "session_logs" / session_name / "transcript.json"


# ---------------------------------------------------------------------------
# Gate 1 — Repeatability
# ---------------------------------------------------------------------------

def run_gate1(blind_fg1: str, codebook: list[dict], evaluator_cfg: dict | None = None) -> dict:
    """
    Code real FG1 N_REPEAT times at temp=0 to measure coding stability.
    Gemini is non-deterministic even at temp=0 for long responses.

    Agreement: pairwise code-vector comparison across all N_REPEAT*(N_REPEAT-1)/2 pairs.
    Reports: worst pairwise %, all-way agreement %, and per-pair breakdown.
    """
    N_REPEAT = 5

    print(f"\n[Gate 1] REPEATABILITY — coding real FG1 {N_REPEAT} times...")
    results: list[Tier1Result] = []
    stats_list: list[QuoteValidityStats] = []

    for i in range(1, N_REPEAT + 1):
        print(f"  Run {i}/{N_REPEAT} ...", end=" ", flush=True)
        result, stats = code_transcript_tier1(
            blind_fg1, codebook, run_label=f"gate1_fg1_run{i}",
            evaluator_cfg=evaluator_cfg,
        )
        results.append(result)
        stats_list.append(stats)
        n_present = sum(1 for c in result.codes if c.present)
        print(f"done  ({n_present}/{len(result.codes)} codes present, "
              f"{stats.demoted_codes} demoted by quote-check)")

    code_ids = [c.subtheme_id for c in results[0].codes]
    n_codes = len(code_ids)
    vectors: list[list[bool]] = []
    for r in results:
        id_to_present = {c.subtheme_id: c.present for c in r.codes}
        vectors.append([id_to_present.get(cid, False) for cid in code_ids])

    # Build per-run lookup maps for the diagnostic fields
    run_code_maps: list[dict[str, dict]] = []
    for r in results:
        run_code_maps.append({
            c.subtheme_id: {
                "present":               c.present,
                "quote_verified":        c.quote_verified,
                "unverified_quote_count": c.unverified_quote_count,
            }
            for c in r.codes
        })

    # Collect codes where runs disagree on `present`
    disagreement_diagnostic: list[dict] = []
    for i, cid in enumerate(code_ids):
        vals = [vectors[r][i] for r in range(N_REPEAT)]
        if len(set(vals)) > 1:  # not unanimous
            record: dict = {"code_id": cid}
            for run_idx in range(N_REPEAT):
                label = f"run{run_idx + 1}"
                fields = run_code_maps[run_idx].get(cid, {})
                record[label] = {
                    "present":               fields.get("present", False),
                    "quote_verified":        fields.get("quote_verified", True),
                    "unverified_quote_count": fields.get("unverified_quote_count", 0),
                }
            disagreement_diagnostic.append(record)

    pairs = list(itertools.combinations(range(N_REPEAT), 2))
    pair_labels = [f"Run {a + 1} vs Run {b + 1}" for a, b in pairs]
    pair_agreements: list[float] = []
    for a, b in pairs:
        agree = sum(vectors[a][i] == vectors[b][i] for i in range(n_codes))
        pair_agreements.append(agree / n_codes)

    all_way = sum(
        len({vectors[r][i] for r in range(N_REPEAT)}) == 1
        for i in range(n_codes)
    ) / n_codes

    worst = min(pair_agreements)
    passed = worst >= REPEATABILITY_THRESHOLD

    _print_gate_header("Gate 1: REPEATABILITY")
    print(f"  Codes in frame: {n_codes}")
    for label, pct in zip(pair_labels, pair_agreements):
        print(f"    {label}: {pct:.1%} agreement")
    print(f"  All-way agreement ({N_REPEAT} runs): {all_way:.1%}")
    print(f"  Worst pairwise:   {worst:.1%}  (threshold >={REPEATABILITY_THRESHOLD:.0%})")
    _print_result(passed)
    if not passed:
        print(
            f"  INTERPRETATION: {1 - worst:.0%} noise floor on code-presence decisions.\n"
            "  All downstream overlap numbers carry this uncertainty; report with caution."
        )
    else:
        print(
            f"  INTERPRETATION: {worst:.0%} agreement is the measure's repeatability ceiling.\n"
            "  Downstream overlap differences larger than "
            f"{1 - worst:.0%} are likely signal, not noise."
        )

    def _fmt(d: dict) -> str:
        p  = "T" if d["present"] else "F"
        qv = "verified" if d["quote_verified"] else "UNVERIFIED"
        uq = d["unverified_quote_count"]
        return f"present={p}/{qv}" + (f"/unverified_quotes={uq}" if uq else "")

    if disagreement_diagnostic:
        print(f"\n  DISAGREEMENT DETAIL ({len(disagreement_diagnostic)} code(s) not unanimous):")
        for rec in disagreement_diagnostic:
            parts = [f"run{k+1}={_fmt(rec[f'run{k+1}'])}" for k in range(N_REPEAT)]
            print(f"    {rec['code_id']}: " + "  ".join(parts))
    else:
        print(f"\n  DISAGREEMENT DETAIL: all codes unanimous across {N_REPEAT} runs.")

    return {
        "passed": passed,
        "n_codes": n_codes,
        "n_repeat": N_REPEAT,
        "pair_agreements": {
            lbl: round(pct, 4)
            for lbl, pct in zip(pair_labels, pair_agreements)
        },
        "all_way_agreement": round(all_way, 4),
        "worst_pairwise": round(worst, 4),
        "threshold": REPEATABILITY_THRESHOLD,
        "disagreement_diagnostic": disagreement_diagnostic,
        "_fg1_run1":       results[0],      # popped in main() before JSON serialization
        "_fg1_run1_stats": stats_list[0],
    }


# ---------------------------------------------------------------------------
# Gate 2 — Discrimination
# ---------------------------------------------------------------------------

def run_gate2(
    fg1_anchor: Tier1Result,
    synth_fg1_result: Tier1Result,
    synth_fg5_result: Tier1Result,
    synth_fg1_stats: QuoteValidityStats,
    synth_fg5_stats: QuoteValidityStats,
) -> dict:
    """
    Tests whether the measure discriminates genuine thematic correspondence
    from cross-group noise.

    Three comparisons, all using real FG1 as anchor:
      (a) Upper-bound calibration: real FG1 vs real FG1 (self) — must be near-perfect.
      (b) MATCHED (pass criterion): real FG1 vs synthetic FG1 (same study group).
      (c) MISMATCHED (control):     real FG1 vs synthetic FG5 (different group, 60+).

    Pass = matched recall > mismatched recall with non-trivial margin (>0).
    The margin is reported; a tiny margin is a weak measure even if it passes formally.
    """
    upper_bound = compute_tier1_scores(fg1_anchor, fg1_anchor)
    matched     = compute_tier1_scores(fg1_anchor, synth_fg1_result)
    mismatched  = compute_tier1_scores(fg1_anchor, synth_fg5_result)

    recall_margin = matched.subtheme_recall - mismatched.subtheme_recall
    passed = recall_margin > 0

    _print_gate_header("Gate 2: DISCRIMINATION")

    print("\n  (a) Upper-bound calibration — real FG1 vs real FG1 (self)")
    _print_scores_inline(upper_bound)
    print("      [Sanity check: should be ~1.0 recall; if not, measure is broken]")

    print("\n  (b) MATCHED -- real FG1 (anchor) vs synthetic FG1  <- pass criterion")
    _print_scores_inline(matched)
    _print_quote_stats_inline(synth_fg1_stats, "synth FG1")

    print("\n  (c) MISMATCHED -- real FG1 (anchor) vs synthetic FG5  <- control")
    _print_scores_inline(mismatched)
    _print_quote_stats_inline(synth_fg5_stats, "synth FG5")

    print(f"\n  DISCRIMINATION MARGIN (matched recall − mismatched recall):")
    print(f"    {matched.subtheme_recall:.3f} − {mismatched.subtheme_recall:.3f} = {recall_margin:+.3f}")
    if recall_margin > 0.15:
        strength = "strong"
    elif recall_margin > 0.05:
        strength = "moderate"
    elif recall_margin > 0:
        strength = "weak (marginal pass — interpret downstream scores with caution)"
    else:
        strength = "none (FAIL)"
    print(f"    Margin strength: {strength}")

    print("\n  NOTE: uses costfix_validation synthetic transcripts; no new runs required.")
    print("  Matched pair is real vs actual synthetic (not self-comparison).")
    _print_result(passed)
    if not passed:
        print(
            "  FAILURE: matched does not outscore mismatched on subtheme recall.\n"
            "  The measure cannot reliably distinguish matched from mismatched groups.\n"
            "  Do NOT proceed to Stage 2 or the experiment batch."
        )

    return {
        "passed": passed,
        "upper_bound_self_comparison": _scores_to_dict(upper_bound),
        "matched_real_fg1_vs_synth_fg1": _scores_to_dict(matched),
        "mismatched_real_fg1_vs_synth_fg5": _scores_to_dict(mismatched),
        "recall_margin": round(recall_margin, 4),
        "margin_strength": strength,
        "synth_fg1_quote_stats": _stats_to_dict(synth_fg1_stats),
        "synth_fg5_quote_stats": _stats_to_dict(synth_fg5_stats),
    }


# ---------------------------------------------------------------------------
# Gate 3 — Quote validity
# ---------------------------------------------------------------------------

def run_gate3(
    real_fg1_stats: QuoteValidityStats,
    synth_fg1_stats: QuoteValidityStats,
    synth_fg5_stats: QuoteValidityStats,
) -> dict:
    """
    Aggregates quote-verification statistics across all Tier-1 coding runs used
    in Gates 1 and 2 (real FG1 run 1, synthetic FG1, synthetic FG5).

    A low quote-verification rate is a reportable finding about Gemini's
    evidentiary reliability — it is interpreted, not merely gated.
    """
    all_stats = [real_fg1_stats, synth_fg1_stats, synth_fg5_stats]
    labels    = ["real FG1 (run 1)", "synth FG1", "synth FG5"]

    total_q   = sum(s.total_quotes for s in all_stats)
    verified_q = sum(s.verified_quotes for s in all_stats)
    total_pos  = sum(s.total_present_codes for s in all_stats)
    verified_pos = sum(s.verified_codes for s in all_stats)
    demoted    = sum(s.demoted_codes for s in all_stats)

    quote_rate = verified_q / total_q if total_q else 1.0
    code_rate  = verified_pos / total_pos if total_pos else 1.0

    passed_quote = quote_rate >= QUOTE_VERIFY_THRESHOLD
    passed_code  = code_rate  >= CODE_PRESERVE_THRESHOLD
    passed = passed_quote and passed_code

    _print_gate_header("Gate 3: QUOTE VALIDITY")
    print(f"  Per-transcript breakdown:")
    for label, s in zip(labels, all_stats):
        print(f"    {label}: {s.verified_quotes}/{s.total_quotes} quotes verified "
              f"({s.quote_verification_rate:.1%}), "
              f"{s.demoted_codes} codes demoted")

    print(f"\n  AGGREGATE (across {len(all_stats)} coding runs):")
    print(f"    Quotes submitted:          {total_q}")
    print(f"    Quotes verified:           {verified_q}  ({quote_rate:.1%})  "
          f"[threshold >={QUOTE_VERIFY_THRESHOLD:.0%}]  {'PASS' if passed_quote else 'FAIL'}")
    print(f"    Positive codes total:      {total_pos}")
    print(f"    Codes with verified quote: {verified_pos}  ({code_rate:.1%})  "
          f"[threshold >={CODE_PRESERVE_THRESHOLD:.0%}]  {'PASS' if passed_code else 'FAIL'}")
    print(f"    Codes demoted to absent:   {demoted}")

    print(f"\n  INTERPRETATION:")
    if quote_rate >= 0.95:
        print("    Quote fidelity is high (>=95%): Gemini evidence is overwhelmingly verbatim.")
    elif quote_rate >= QUOTE_VERIFY_THRESHOLD:
        unverified_pct = 1 - quote_rate
        print(f"    {unverified_pct:.0%} of quotes were non-verbatim (paraphrase or fabrication).")
        print("    These were excluded from positive codes; the surviving evidence is verified.")
    else:
        unverified_pct = 1 - quote_rate
        print(f"    LOW QUOTE FIDELITY: {unverified_pct:.0%} of quotes are non-verbatim.")
        print("    This is a finding about Gemini's evidentiary reliability at this transcript")
        print("    length/complexity. All positive codes in this study carry this caveat.")

    _print_result(passed)

    return {
        "passed": passed,
        "per_transcript": {
            lbl: _stats_to_dict(s) for lbl, s in zip(labels, all_stats)
        },
        "aggregate": {
            "total_quotes": total_q,
            "verified_quotes": verified_q,
            "quote_verification_rate": round(quote_rate, 4),
            "total_present_codes": total_pos,
            "codes_with_verified_quote": verified_pos,
            "code_preservation_rate": round(code_rate, 4),
            "codes_demoted": demoted,
        },
        "thresholds": {
            "quote_verification_rate": QUOTE_VERIFY_THRESHOLD,
            "code_preservation_rate": CODE_PRESERVE_THRESHOLD,
        },
        "interpretation": (
            "high fidelity" if quote_rate >= 0.95
            else "acceptable with caveats" if passed_quote
            else "low — Gemini fabrication rate is a reportable finding"
        ),
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_gate_header(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def _print_result(passed: bool) -> None:
    label = "PASS" if passed else "FAIL"
    print(f"\n  RESULT: {label}")


def _print_scores_inline(s: TierOneScores) -> None:
    print(f"      Subtheme: recall={s.subtheme_recall:.3f}  precision={s.subtheme_precision:.3f}  "
          f"F1={s.subtheme_f1:.3f}  Jaccard={s.subtheme_jaccard:.3f}")
    print(f"      Theme:    recall={s.theme_recall:.3f}  precision={s.theme_precision:.3f}  "
          f"F1={s.theme_f1:.3f}  Jaccard={s.theme_jaccard:.3f}")
    print(f"      Codes: anchor={len(s.real_present)}  target={len(s.synthetic_present)}  "
          f"shared={len(s.shared_subthemes)}  |  "
          f"Themes: anchor={sorted(s.real_themes)}  shared={sorted(s.shared_themes)}")
    print(f"      {s.interpretation()}")


def _print_quote_stats_inline(s: QuoteValidityStats, label: str) -> None:
    print(f"      ({label} quote-validity: {s.verified_quotes}/{s.total_quotes} quotes "
          f"verified={s.quote_verification_rate:.1%}, "
          f"{s.demoted_codes} codes demoted)")


def _scores_to_dict(s: TierOneScores) -> dict:
    return {
        "subtheme_recall":    round(s.subtheme_recall, 4),
        "subtheme_precision": round(s.subtheme_precision, 4),
        "subtheme_f1":        round(s.subtheme_f1, 4),
        "subtheme_jaccard":   round(s.subtheme_jaccard, 4),
        "theme_recall":       round(s.theme_recall, 4),
        "theme_precision":    round(s.theme_precision, 4),
        "theme_f1":           round(s.theme_f1, 4),
        "theme_jaccard":      round(s.theme_jaccard, 4),
        "anchor_present":     sorted(s.real_present),
        "target_present":     sorted(s.synthetic_present),
        "shared_subthemes":   sorted(s.shared_subthemes),
        "anchor_themes":      sorted(s.real_themes),
        "target_themes":      sorted(s.synthetic_themes),
        "shared_themes":      sorted(s.shared_themes),
        "interpretation":     s.interpretation(),
    }


def _stats_to_dict(s: QuoteValidityStats) -> dict:
    return {
        "total_quotes":                s.total_quotes,
        "verified_quotes":             s.verified_quotes,
        "raw_exact_quotes":            s.raw_exact_quotes,
        "normalized_recovered_quotes": s.normalized_recovered_quotes,
        "total_present_codes":         s.total_present_codes,
        "verified_codes":              s.verified_codes,
        "demoted_codes":               s.demoted_codes,
        "quote_verification_rate":     round(s.quote_verification_rate, 4),
        "code_preservation_rate":      round(s.code_preservation_rate, 4),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(out_path: Path | None, evaluator_cfg: dict | None = None) -> int:
    _ecfg = evaluator_cfg or {}
    _model_display = _ecfg.get("model", "gemini-2.5-flash")
    _think = _ecfg.get("thinking_level")
    _temp  = _ecfg.get("temperature", 0.0) if evaluator_cfg else 0.0
    _param_display = f"thinking_level={_think}" if _think else f"temp={_temp}"

    print("=" * 65)
    print("  STAGE 1 VALIDATION: LLM-ASSISTED THEMATIC FIDELITY MEASURE")
    print(f"  Evaluator:  {_model_display} ({_param_display})")
    print("  Coding:     blind, symmetric, quote-grounded")
    print("  Scope:      Macho Meals (English) — Spanish path NOT validated here")
    print("=" * 65)

    # --- Load codebook ---
    print("\nLoading codebook...")
    codebook = load_codebook()
    print(f"  {len(codebook)} subtheme codes across "
          f"{len(set(c['subtheme_id'][0] for c in codebook))} themes")

    # --- Load and blind all transcripts ---
    print("\nLoading and blinding transcripts...")
    real_fg1_entries  = _load_transcript(_real_transcript_path("fg1"))
    synth_fg1_entries = _load_transcript(_synth_transcript_path("costfix_validation_fg1"))
    synth_fg5_entries = _load_transcript(_synth_transcript_path("costfix_validation_fg5"))

    blind_real_fg1,  sm_real  = to_blind_text(real_fg1_entries)
    blind_synth_fg1, sm_sfg1  = to_blind_text(synth_fg1_entries)
    blind_synth_fg5, sm_sfg5  = to_blind_text(synth_fg5_entries)

    print(f"  real  FG1:  {len(blind_real_fg1.splitlines())} blind turns, "
          f"{len(sm_real)} speakers")
    print(f"  synth FG1:  {len(blind_synth_fg1.splitlines())} blind turns, "
          f"{len(sm_sfg1)} speakers")
    print(f"  synth FG5:  {len(blind_synth_fg5.splitlines())} blind turns, "
          f"{len(sm_sfg5)} speakers")

    # --- Code synthetic transcripts (done once, used in Gate 2 + Gate 3) ---
    print("\nCoding synthetic transcripts (blind, same prompt as real)...")
    print("  synth FG1 ...", end=" ", flush=True)
    synth_fg1_result, synth_fg1_stats = code_transcript_tier1(
        blind_synth_fg1, codebook, run_label="gate2_synth_fg1",
        evaluator_cfg=evaluator_cfg,
    )
    n_sfg1 = sum(1 for c in synth_fg1_result.codes if c.present)
    print(f"done  ({n_sfg1}/{len(synth_fg1_result.codes)} present, "
          f"{synth_fg1_stats.demoted_codes} demoted)")

    print("  synth FG5 ...", end=" ", flush=True)
    synth_fg5_result, synth_fg5_stats = code_transcript_tier1(
        blind_synth_fg5, codebook, run_label="gate2_synth_fg5",
        evaluator_cfg=evaluator_cfg,
    )
    n_sfg5 = sum(1 for c in synth_fg5_result.codes if c.present)
    print(f"done  ({n_sfg5}/{len(synth_fg5_result.codes)} present, "
          f"{synth_fg5_stats.demoted_codes} demoted)")

    # --- Gate 1: repeatability on real FG1 ---
    gate1_raw = run_gate1(blind_real_fg1, codebook, evaluator_cfg=evaluator_cfg)
    fg1_canonical: Tier1Result      = gate1_raw.pop("_fg1_run1")
    fg1_run1_stats: QuoteValidityStats = gate1_raw.pop("_fg1_run1_stats")

    # --- Gate 2: genuine real-vs-synthetic discrimination ---
    gate2 = run_gate2(
        fg1_anchor=fg1_canonical,
        synth_fg1_result=synth_fg1_result,
        synth_fg5_result=synth_fg5_result,
        synth_fg1_stats=synth_fg1_stats,
        synth_fg5_stats=synth_fg5_stats,
    )

    # --- Gate 3: quote validity across all runs ---
    gate3 = run_gate3(
        real_fg1_stats=fg1_run1_stats,
        synth_fg1_stats=synth_fg1_stats,
        synth_fg5_stats=synth_fg5_stats,
    )

    # --- Overall verdict ---
    all_pass = gate1_raw["passed"] and gate2["passed"] and gate3["passed"]

    print(f"\n{'=' * 65}")
    print(f"  OVERALL STAGE 1 VERDICT: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'=' * 65}")

    print("\n  SUMMARY OF NUMBERS:")
    print(f"    Gate 1 repeatability:  worst pairwise = "
          f"{gate1_raw['worst_pairwise']:.1%}  "
          f"(threshold >={REPEATABILITY_THRESHOLD:.0%})  "
          f"{'PASS' if gate1_raw['passed'] else 'FAIL'}")
    print(f"    Gate 2 discrimination: matched recall = "
          f"{gate2['matched_real_fg1_vs_synth_fg1']['subtheme_recall']:.3f}  "
          f"mismatched = {gate2['mismatched_real_fg1_vs_synth_fg5']['subtheme_recall']:.3f}  "
          f"margin = {gate2['recall_margin']:+.3f} ({gate2['margin_strength']})  "
          f"{'PASS' if gate2['passed'] else 'FAIL'}")
    print(f"    Gate 3 quote validity: quote rate = "
          f"{gate3['aggregate']['quote_verification_rate']:.1%}  "
          f"code preservation = {gate3['aggregate']['code_preservation_rate']:.1%}  "
          f"{'PASS' if gate3['passed'] else 'FAIL'}")

    print()
    if all_pass:
        print("  SCOPE: the measure is validated FOR MACHO MEALS (English, this codebook).")
        print("  The Spanish/multilingual path (SF dataset) is NOT cleared by this result.")
        print("  SF requires Stage 2's sentence-transformer cross-check (untested here).")
        print("\n  Next step: Stage 2 (Tier 2 open extraction) or the Macho Meals batch.")
    else:
        print("  One or more gates FAILED. Resolve failures before Stage 2 or the batch.")

    # --- Save JSON report ---
    report = {
        "measure": "LLM-assisted evidence-constrained thematic fidelity (Stage 1)",
        "evaluator": _model_display,
        "evaluator_params": {
            "temperature": None if _think else _temp,
            "thinking_level": _think,
        },
        "scope": "Macho Meals (English) only — Spanish/multilingual path not validated",
        "gate1_run1_present_codes": sorted(
            c.subtheme_id for c in fg1_canonical.codes if c.present
        ),
        "thresholds": {
            "repeatability_pairwise_agreement": REPEATABILITY_THRESHOLD,
            "quote_verification_rate": QUOTE_VERIFY_THRESHOLD,
            "code_preservation_rate": CODE_PRESERVE_THRESHOLD,
        },
        "gate1_repeatability": gate1_raw,
        "gate2_discrimination": gate2,
        "gate3_quote_validity": gate3,
        "summary": {
            "gate1_worst_pairwise":           gate1_raw["worst_pairwise"],
            "gate2_matched_recall":           gate2["matched_real_fg1_vs_synth_fg1"]["subtheme_recall"],
            "gate2_mismatched_recall":        gate2["mismatched_real_fg1_vs_synth_fg5"]["subtheme_recall"],
            "gate2_recall_margin":            gate2["recall_margin"],
            "gate2_margin_strength":          gate2["margin_strength"],
            "gate3_quote_verification_rate":  gate3["aggregate"]["quote_verification_rate"],
            "gate3_code_preservation_rate":   gate3["aggregate"]["code_preservation_rate"],
        },
        "overall_passed": all_pass,
        "stage2_cleared": all_pass,
        "macho_meals_cleared": all_pass,
        "spanish_sf_cleared":  False,
    }

    if out_path is None:
        out_path = _REPO_ROOT / "analysis" / "coding_frame" / "validation_stage1.json"
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    try:
        display_path = out_path.relative_to(_REPO_ROOT)
    except ValueError:
        display_path = out_path
    print(f"\n  Full report saved to: {display_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Stage 1 validation gates.")
    parser.add_argument("--out", type=Path, default=None, help="Output JSON report path.")
    args = parser.parse_args()
    out = args.out.resolve() if args.out is not None else None
    sys.exit(main(out))
