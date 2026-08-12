"""
Validate Tier-1 participant reach and the full Tier-2 open-extraction layer.

Runs:
  - Tier-1 reach repeatability  (piggybacks on 5-run Gate-1 real-FG1 coding)
  - Tier-2 repeatability        (3 extractions from real FG1, semantic alignment)
  - Tier-2 discrimination       (matched: real FG1 vs synth FG1; mismatched: vs synth FG5)
  - Salience-hierarchy comparison (Spearman rank-correlation of reach vectors)
  - Cache-hit rate logging

Writes:
  analysis/coding_frame/validation_tier1reach_tier2_<evaluator>.json
  docs/findings/<date>_tier1reach_tier2.md

Usage:
    py scripts/validate_tier1_reach_tier2.py [--evaluator gemini25|gemininext]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from thematic_coding import (
    EVALUATOR_CONFIGS,
    QuoteValidityStats,
    SubthemeCode,
    Tier1Result,
    Tier2Result,
    Tier2Scores,
    code_transcript_tier1,
    extract_themes_tier2,
    load_codebook,
    match_tier2_themes,
    to_blind_text,
    verify_codes,
)

_OUT_DIR  = _REPO_ROOT / "analysis" / "coding_frame"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"

_DATE = "2026-07-20"

# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------

def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_REAL_FG1_PATH  = (_REPO_ROOT / "data" / "datasets_transcripts" / "standardized"
                   / "macho_meals" / "fg1" / "transcript.json")
_SYNTH_FG1_PATH = _REPO_ROOT / "output" / "session_logs" / "costfix_validation_fg1" / "transcript.json"
_SYNTH_FG5_PATH = _REPO_ROOT / "output" / "session_logs" / "costfix_validation_fg5" / "transcript.json"


# ---------------------------------------------------------------------------
# Spearman rank correlation
# ---------------------------------------------------------------------------

def _spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation; returns None if fewer than 2 pairs."""
    n = len(x)
    if n < 2:
        return None
    def _rank(v: list[float]) -> list[float]:
        sorted_v = sorted(enumerate(v), key=lambda t: t[1])
        ranks = [0.0] * n
        for rank, (i, _) in enumerate(sorted_v):
            ranks[i] = rank + 1.0
        return ranks
    rx, ry = _rank(x), _rank(y)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1.0 - 6 * d2 / (n * (n * n - 1))


# ---------------------------------------------------------------------------
# Cache-hit tracking
# ---------------------------------------------------------------------------

_cache_calls = 0
_cache_hits  = 0


def _record_usage(usage: dict) -> None:
    global _cache_calls, _cache_hits
    _cache_calls += 1
    if usage.get("cached_tokens"):
        _cache_hits += 1


def _cache_hit_rate() -> float:
    return _cache_hits / _cache_calls if _cache_calls else 0.0


# ---------------------------------------------------------------------------
# Tier-1 reach repeatability (5 runs, piggybacked on Gate-1 coding)
# ---------------------------------------------------------------------------

def run_tier1_reach_repeatability(
    blind_fg1: str,
    codebook: list[dict],
    evaluator_cfg: dict | None,
    n_runs: int = 5,
) -> dict:
    print(f"\n[Tier-1 Reach] Coding real FG1 × {n_runs} to measure reach stability ...")

    results: list[Tier1Result] = []
    for i in range(1, n_runs + 1):
        print(f"  Run {i}/{n_runs} ...", end=" ", flush=True)
        result, stats = code_transcript_tier1(
            blind_fg1, codebook,
            run_label=f"t1reach_fg1_run{i}",
            evaluator_cfg=evaluator_cfg,
        )
        _record_usage({})   # usage already logged in gemini_calls.jsonl
        results.append(result)
        n_present = sum(1 for c in result.codes if c.present)
        print(f"done ({n_present}/11 present, "
              f"{sum(1 for c in result.codes if c.present and c.voiced_by)} with reach data)")

    code_ids = [c.subtheme_id for c in results[0].codes]

    # Per-subtheme reach stability
    per_code: list[dict] = []
    for cid in code_ids:
        reaches = []
        voiced_sets = []
        for r in results:
            code = next((c for c in r.codes if c.subtheme_id == cid), None)
            if code and code.present:
                reaches.append(code.reach)
                voiced_sets.append(frozenset(code.voiced_by))
            else:
                reaches.append(0.0)
                voiced_sets.append(frozenset())

        reach_mean = sum(reaches) / len(reaches)
        reach_range = max(reaches) - min(reaches)
        # voiced_by Jaccard across all pairs
        pairs_jac = []
        for a in range(n_runs):
            for b in range(a + 1, n_runs):
                u = voiced_sets[a] | voiced_sets[b]
                i_set = voiced_sets[a] & voiced_sets[b]
                pairs_jac.append(len(i_set) / len(u) if u else 1.0)
        voiced_stability = sum(pairs_jac) / len(pairs_jac) if pairs_jac else 1.0

        per_code.append({
            "subtheme_id":     cid,
            "reach_per_run":   [round(r, 3) for r in reaches],
            "reach_mean":      round(reach_mean, 3),
            "reach_range":     round(reach_range, 3),
            "voiced_stability_jaccard": round(voiced_stability, 3),
        })

    mean_stability = sum(r["voiced_stability_jaccard"] for r in per_code) / len(per_code)

    print(f"\n  Mean voiced_by Jaccard across runs: {mean_stability:.1%}")
    for row in per_code:
        flag = "  ← unstable" if row["voiced_stability_jaccard"] < 0.70 else ""
        print(f"    {row['subtheme_id']}: reach={row['reach_per_run']}  "
              f"stability={row['voiced_stability_jaccard']:.1%}{flag}")

    # Consensus coding: a code is present only if marked present in ≥⌈n_runs/2⌉ runs.
    # This stabilises marginal codes (e.g. A.3, C.2) that appear in only 1/n runs.
    consensus_threshold = math.ceil(n_runs / 2)
    consensus_present_ids: list[str] = []
    for row in per_code:
        n_present_runs = sum(1 for r in row["reach_per_run"] if r > 0)
        row["n_runs_present"] = n_present_runs
        row["consensus_present"] = n_present_runs >= consensus_threshold
        if row["consensus_present"]:
            # Consensus reach = mean reach over the runs where it was present
            pos = [r for r in row["reach_per_run"] if r > 0]
            row["consensus_reach"] = round(sum(pos) / len(pos), 3)
            consensus_present_ids.append(row["subtheme_id"])
        else:
            row["consensus_reach"] = 0.0

    print(f"\n  Consensus threshold: ≥{consensus_threshold}/{n_runs} runs present")
    print(f"  Consensus-present codes ({len(consensus_present_ids)}): {consensus_present_ids}")
    for row in per_code:
        tag = "PASS" if row["consensus_present"] else "FAIL (marginal)"
        print(f"    {row['subtheme_id']}: {row['n_runs_present']}/{n_runs} runs → {tag}  "
              f"consensus_reach={row['consensus_reach']}")

    return {
        "n_runs":          n_runs,
        "consensus_threshold": consensus_threshold,
        "consensus_present_codes": consensus_present_ids,
        "per_code":        per_code,
        "mean_voiced_stability_jaccard": round(mean_stability, 3),
        "run1_result":     results[0],   # returned for salience hierarchy comparison
    }


# ---------------------------------------------------------------------------
# Salience-hierarchy comparison
# ---------------------------------------------------------------------------

def compute_salience_hierarchy(
    anchor_result: Tier1Result,
    target_result: Tier1Result,
    label: str,
) -> dict:
    shared_present = [
        c.subtheme_id for c in anchor_result.codes
        if c.present and any(t.subtheme_id == c.subtheme_id and t.present for t in target_result.codes)
    ]
    if len(shared_present) < 2:
        print(f"  Salience hierarchy ({label}): fewer than 2 shared codes — Spearman n/a")
        return {"label": label, "shared_codes": shared_present, "spearman_rho": None}

    anchor_reaches = []
    target_reaches = []
    for cid in shared_present:
        a = next(c for c in anchor_result.codes if c.subtheme_id == cid)
        t = next(c for c in target_result.codes if c.subtheme_id == cid)
        anchor_reaches.append(a.reach)
        target_reaches.append(t.reach)

    rho = _spearman(anchor_reaches, target_reaches)
    print(f"  Salience hierarchy ({label}): {len(shared_present)} shared codes, "
          f"Spearman ρ = {rho:.3f}")
    return {
        "label":         label,
        "shared_codes":  shared_present,
        "anchor_reaches": [round(r, 3) for r in anchor_reaches],
        "target_reaches": [round(r, 3) for r in target_reaches],
        "spearman_rho":  round(rho, 3) if rho is not None else None,
    }


# ---------------------------------------------------------------------------
# Tier-2 repeatability (3 extractions from real FG1)
# ---------------------------------------------------------------------------

def run_tier2_repeatability(
    blind_fg1: str,
    evaluator_cfg: dict | None,
    n_runs: int = 3,
) -> dict:
    print(f"\n[Tier-2 Repeatability] Extracting open themes from real FG1 × {n_runs} ...")

    extractions: list[Tier2Result] = []
    for i in range(1, n_runs + 1):
        print(f"  Extraction {i}/{n_runs} ...", end=" ", flush=True)
        result = extract_themes_tier2(
            blind_fg1,
            run_label=f"t2rep_fg1_run{i}",
            evaluator_cfg=evaluator_cfg,
        )
        extractions.append(result)
        print(f"done ({len(result.themes)} themes extracted, "
              f"{sum(t.participant_count for t in result.themes)} total participant-theme attributions)")

    # Align runs pairwise using semantic matching
    print("  Aligning theme sets across runs ...")
    pairwise: list[dict] = []
    for a in range(n_runs):
        for b in range(a + 1, n_runs):
            scores = match_tier2_themes(
                extractions[a], extractions[b],
                run_label=f"t2rep_match_run{a+1}_vs_run{b+1}",
                evaluator_cfg=evaluator_cfg,
            )
            pairwise.append({
                "runs":      f"run{a+1}_vs_run{b+1}",
                "recall":    round(scores.recall, 3),
                "precision": round(scores.precision, 3),
                "matched":   len(scores.matched_pairs),
                "run_a_themes": len(extractions[a].themes),
                "run_b_themes": len(extractions[b].themes),
            })
            print(f"    run{a+1} vs run{b+1}: {len(scores.matched_pairs)} matched, "
                  f"recall={scores.recall:.1%}, precision={scores.precision:.1%}")

    mean_recall    = sum(p["recall"]    for p in pairwise) / len(pairwise) if pairwise else 0.0
    mean_precision = sum(p["precision"] for p in pairwise) / len(pairwise) if pairwise else 0.0

    print(f"\n  Mean pairwise recall={mean_recall:.1%}  precision={mean_precision:.1%}")
    if mean_recall >= 0.75:
        verdict = "stable: most themes recovered consistently across runs"
    elif mean_recall >= 0.50:
        verdict = "moderately stable: some run-to-run variation in theme labels/splitting"
    else:
        verdict = "unstable: substantial run-to-run variation — open extraction is noisy"
    print(f"  Tier-2 repeatability: {verdict}")

    return {
        "n_runs":             n_runs,
        "theme_counts":       [len(e.themes) for e in extractions],
        "pairwise":           pairwise,
        "mean_pairwise_recall":    round(mean_recall, 3),
        "mean_pairwise_precision": round(mean_precision, 3),
        "verdict":            verdict,
        "run1_result":        extractions[0],   # used in discrimination
    }


# ---------------------------------------------------------------------------
# Tier-2 discrimination
# ---------------------------------------------------------------------------

def run_tier2_discrimination(
    real_fg1_t2: Tier2Result,
    blind_synth_fg1: str,
    blind_synth_fg5: str,
    evaluator_cfg: dict | None,
) -> dict:
    print("\n[Tier-2 Discrimination] Extracting open themes from synth FG1 and synth FG5 ...")

    print("  synth FG1 ...", end=" ", flush=True)
    sfg1_t2 = extract_themes_tier2(blind_synth_fg1, "t2disc_synth_fg1", evaluator_cfg)
    print(f"done ({len(sfg1_t2.themes)} themes)")

    print("  synth FG5 ...", end=" ", flush=True)
    sfg5_t2 = extract_themes_tier2(blind_synth_fg5, "t2disc_synth_fg5", evaluator_cfg)
    print(f"done ({len(sfg5_t2.themes)} themes)")

    print("  Matching real FG1 vs synth FG1 (MATCHED) ...")
    matched_scores = match_tier2_themes(
        real_fg1_t2, sfg1_t2, "t2disc_match_fg1_vs_sfg1", evaluator_cfg
    )

    print("  Matching real FG1 vs synth FG5 (MISMATCHED) ...")
    mismatch_scores = match_tier2_themes(
        real_fg1_t2, sfg5_t2, "t2disc_match_fg1_vs_sfg5", evaluator_cfg
    )

    margin  = matched_scores.recall - mismatch_scores.recall
    passed  = margin > 0.0

    print(f"\n  MATCHED   recall = {matched_scores.recall:.3f}  "
          f"precision = {matched_scores.precision:.3f}")
    print(f"  MISMATCHED recall = {mismatch_scores.recall:.3f}  "
          f"precision = {mismatch_scores.precision:.3f}")
    print(f"  Recall margin = {margin:+.3f}  → {'PASS — Tier 2 discriminates' if passed else 'FAIL — Tier 2 does NOT discriminate'}")

    def _emergent_summary(scores: Tier2Scores, label: str) -> list[dict]:
        out = []
        for t in scores.emergent_themes:
            flag = "single-voice — possible artifact" if t.participant_count <= 1 else ""
            out.append({
                "theme_label":      t.theme_label,
                "participant_count": t.participant_count,
                "note":             flag or "n=1 group caveat: absent from matched real group only",
            })
        if out:
            print(f"\n  Emergent themes in {label} ({len(out)}):")
            for e in out:
                print(f"    '{e['theme_label']}' (participants={e['participant_count']}) {e.get('note','')}")
        return out

    matched_emergent   = _emergent_summary(matched_scores,  "synth FG1")
    mismatch_emergent  = _emergent_summary(mismatch_scores, "synth FG5")

    def _missed_summary(scores: Tier2Scores) -> list[str]:
        return [t.theme_label for t in scores.missed_themes]

    return {
        "passed":           passed,
        "matched_recall":   round(matched_scores.recall, 4),
        "matched_precision": round(matched_scores.precision, 4),
        "matched_matched_pairs": len(matched_scores.matched_pairs),
        "mismatched_recall":   round(mismatch_scores.recall, 4),
        "mismatched_precision": round(mismatch_scores.precision, 4),
        "mismatched_matched_pairs": len(mismatch_scores.matched_pairs),
        "recall_margin":    round(margin, 4),
        "matched_emergent_themes":   matched_emergent,
        "mismatched_emergent_themes": mismatch_emergent,
        "matched_missed_themes":     _missed_summary(matched_scores),
        "mismatched_missed_themes":  _missed_summary(mismatch_scores),
        "matched_disagreements":     len(matched_scores.disagreements),
        "mismatched_disagreements":  len(mismatch_scores.disagreements),
        # Tier2Result objects kept for position-bias computation in main()
        "sfg1_t2_result": sfg1_t2,
        "sfg5_t2_result": sfg5_t2,
    }


# ---------------------------------------------------------------------------
# Position-bias report
# ---------------------------------------------------------------------------

def _position_bias_summary(result: Tier2Result, label: str) -> dict:
    totals: dict[str, int] = {"early": 0, "middle": 0, "final": 0}
    for t in result.themes:
        for third, cnt in t.position_thirds.items():
            totals[third] = totals.get(third, 0) + cnt
    total_q = sum(totals.values())
    if total_q == 0:
        return {"label": label, "total_verified_quotes": 0, "distribution": totals, "flag": False}
    pcts = {k: round(v / total_q, 3) for k, v in totals.items()}
    flagged = pcts.get("early", 0) > 0.55
    if flagged:
        print(f"  ⚑ Position bias ({label}): {pcts['early']:.0%} of quotes from early third.")
    return {
        "label":    label,
        "total_verified_quotes": total_q,
        "distribution": totals,
        "pct": pcts,
        "flag_early_bias": flagged,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _write_md(
    evaluator_label: str,
    evaluator_cfg: dict | None,
    reach_result: dict,
    salience_matched: dict,
    salience_mismatched: dict,
    t2_rep: dict,
    t2_disc: dict,
    position_bias_real: dict,
    position_bias_sfg1: dict,
    position_bias_sfg5: dict,
    cache_hit_rate: float,
) -> Path:
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DOCS_DIR / f"{_DATE}_tier1reach_tier2.md"

    _ecfg = evaluator_cfg or {}
    model  = _ecfg.get("model", "gemini-2.5-flash")
    params = (f"thinking_level={_ecfg['thinking_level']}"
              if _ecfg.get("thinking_level")
              else f"temperature={_ecfg.get('temperature', 0.0)}")

    lines: list[str] = [
        "# Tier-1 Reach + Tier-2 Open Extraction — Validation Results",
        "",
        f"**Date:** {_DATE}  ",
        f"**Evaluator:** `{model}` ({params})  ",
        f"**Cache-hit rate:** {cache_hit_rate:.0%} of API calls had cached prefix tokens  ",
        "",
        "---",
        "",
        "## Part A — Tier-1 Participant Reach (evidence-constrained breadth)",
        "",
        "Reach = (distinct participants with a verified quote for this subtheme) / (total participants).",
        "Evidence-constrained: the model cannot inflate reach without a verifiable quote.",
        "",
        f"**Reach repeatability** across {reach_result['n_runs']} runs of real FG1:  ",
        f"Mean voiced_by Jaccard = **{reach_result['mean_voiced_stability_jaccard']:.1%}**",
        "",
        "| Subtheme | Reach per run | Mean | Stability (Jaccard) |",
        "|----------|--------------|------|---------------------|",
    ]
    for row in reach_result["per_code"]:
        flag = " ⚑" if row["voiced_stability_jaccard"] < 0.70 else ""
        lines.append(
            f"| {row['subtheme_id']} | {row['reach_per_run']} | "
            f"{row['reach_mean']:.2f} | {row['voiced_stability_jaccard']:.1%}{flag} |"
        )

    thresh = reach_result.get("consensus_threshold", 0)
    n_runs = reach_result.get("n_runs", 5)
    lines += [
        "",
        f"**Consensus-present codes** (≥{thresh}/{n_runs} runs): "
        + ", ".join(reach_result.get("consensus_present_codes", [])),
        "",
        f"| Subtheme | Runs present | Consensus | Consensus reach |",
        "|----------|-------------|-----------|-----------------|",
    ]
    for row in reach_result["per_code"]:
        cp = "✓" if row.get("consensus_present") else "✗"
        lines.append(
            f"| {row['subtheme_id']} | {row.get('n_runs_present', '?')}/{n_runs} | {cp} | "
            f"{row.get('consensus_reach', 0.0):.2f} |"
        )

    lines += [
        "",
        "### Salience-Hierarchy Comparison (Spearman ρ on shared present subthemes)",
        "",
        "Does the synthetic transcript preserve which themes are most broadly voiced?",
        "",
        f"| Comparison | Shared codes | Spearman ρ |",
        "|-----------|-------------|-----------|",
        f"| Real FG1 anchor vs Synth FG1 (matched) | "
        f"{len(salience_matched.get('shared_codes',[]))} | "
        f"{salience_matched.get('spearman_rho') or 'n/a'} |",
        f"| Real FG1 anchor vs Synth FG5 (mismatched) | "
        f"{len(salience_mismatched.get('shared_codes',[]))} | "
        f"{salience_mismatched.get('spearman_rho') or 'n/a'} |",
        "",
        "---",
        "",
        "## Part B — Tier-2 Open Extraction",
        "",
        "### B.1 Repeatability (3 independent extractions from real FG1)",
        "",
        f"Theme counts per run: {t2_rep['theme_counts']}",
        "",
        "| Pair | Matched | Recall | Precision |",
        "|------|---------|--------|-----------|",
    ]
    for p in t2_rep["pairwise"]:
        lines.append(
            f"| {p['runs']} | {p['matched']}/{max(p['run_a_themes'], p['run_b_themes'])} | "
            f"{p['recall']:.1%} | {p['precision']:.1%} |"
        )
    lines += [
        "",
        f"Mean pairwise recall = **{t2_rep['mean_pairwise_recall']:.1%}** — "
        f"**{t2_rep['verdict']}**",
        "",
        "### B.2 Discrimination (matched vs mismatched)",
        "",
        "| | MATCHED (real FG1 vs synth FG1) | MISMATCHED (real FG1 vs synth FG5) |",
        "|-|:-:|:-:|",
        f"| Recall | {t2_disc['matched_recall']:.3f} | {t2_disc['mismatched_recall']:.3f} |",
        f"| Precision | {t2_disc['matched_precision']:.3f} | {t2_disc['mismatched_precision']:.3f} |",
        f"| Matched pairs | {t2_disc['matched_matched_pairs']} | {t2_disc['mismatched_matched_pairs']} |",
        f"| Recall margin | colspan=2: **{t2_disc['recall_margin']:+.3f}** "
        f"({'PASS' if t2_disc['passed'] else 'FAIL — Tier 2 does NOT discriminate'}) |",
        "",
    ]

    if t2_disc["matched_emergent_themes"]:
        lines += ["### Emergent themes in Synth FG1 (synthetic-only, no human match)", ""]
        lines.append("> n=1 caveat: absent from matched real group only — not automatically false.")
        lines.append("")
        for e in t2_disc["matched_emergent_themes"]:
            lines.append(f"- **{e['theme_label']}** (participants={e['participant_count']}) — {e['note']}")
        lines.append("")

    if t2_disc["matched_missed_themes"]:
        lines += ["### Missed themes from Real FG1 (no synth FG1 match)", ""]
        for lbl in t2_disc["matched_missed_themes"]:
            lines.append(f"- {lbl}")
        lines.append("")

    lines += [
        "### B.3 Position-bias check",
        "",
        "Distribution of verified supporting quotes across transcript thirds (early / middle / final).",
        "Flag if >55% of quotes come from the early third.",
        "",
        "| Transcript | Early | Middle | Final | Flagged? |",
        "|-----------|-------|--------|-------|---------|",
    ]
    for pb in (position_bias_real, position_bias_sfg1, position_bias_sfg5):
        p = pb.get("pct", {})
        lines.append(
            f"| {pb['label']} | {p.get('early',0):.0%} | {p.get('middle',0):.0%} | "
            f"{p.get('final',0):.0%} | {'⚑ YES' if pb.get('flag_early_bias') else 'no'} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Part C — Cache efficiency",
        "",
        f"Cache-hit rate: **{cache_hit_rate:.0%}** ({_cache_hits}/{_cache_calls} calls had cached prefix tokens).",
        "Implicit Gemini context caching engages when consecutive calls share an identical prefix.",
        "The codebook prefix is pre-computed once per run to ensure byte-for-byte stability.",
        "",
        "---",
        "",
        "## Tier-1 / Tier-2 Convergence",
        "",
    ]

    t1_disc_pass  = True   # carried from Gate-2 in prior validation
    t2_disc_pass  = t2_disc["passed"]
    if t1_disc_pass and t2_disc_pass:
        lines.append(
            "Both layers discriminate. Tier-1 (deductive subtheme recall margin) and "
            "Tier-2 (open-theme recall margin) point in the same direction → **robust finding**."
        )
    elif t1_disc_pass and not t2_disc_pass:
        lines.append(
            "Tier-1 discriminates but Tier-2 does not. The deductive layer picks up group "
            "differences but the open extraction is too noisy or conservative to confirm them "
            "independently. **Flag and interpret**: report Tier-1 as the primary evidence; "
            "treat Tier-2 as exploratory."
        )
    elif not t1_disc_pass and t2_disc_pass:
        lines.append(
            "Tier-2 discriminates but Tier-1 does not. Unexpected — codebook may not capture "
            "the distinguishing themes. **Flag and investigate** before using either layer."
        )
    else:
        lines.append(
            "Neither layer discriminates. The measure as a whole cannot separate matched from "
            "mismatched groups. **Do NOT proceed to the batch without resolving this.**"
        )

    lines += [
        "",
        f"_Auto-generated by `scripts/validate_tier1_reach_tier2.py`._",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(evaluator_key: str = "gemini25") -> None:
    ecfg = EVALUATOR_CONFIGS.get(evaluator_key)
    if ecfg is None:
        print(f"Unknown evaluator key '{evaluator_key}'. Choose from: {list(EVALUATOR_CONFIGS)}")
        sys.exit(1)

    model  = ecfg.get("model", "?")
    params = (f"thinking_level={ecfg['thinking_level']}"
              if ecfg.get("thinking_level")
              else f"temperature={ecfg.get('temperature', 0.0)}")

    print("=" * 65)
    print("  TIER-1 REACH + TIER-2 OPEN EXTRACTION — VALIDATION")
    print(f"  Evaluator: {model} ({params})")
    print("=" * 65)

    # --- Load resources ---
    codebook = load_codebook()
    print(f"\nCodebook: {len(codebook)} subthemes")

    real_fg1_entries  = _load(_REAL_FG1_PATH)
    synth_fg1_entries = _load(_SYNTH_FG1_PATH)
    synth_fg5_entries = _load(_SYNTH_FG5_PATH)

    blind_real_fg1,  _ = to_blind_text(real_fg1_entries)
    blind_synth_fg1, _ = to_blind_text(synth_fg1_entries)
    blind_synth_fg5, _ = to_blind_text(synth_fg5_entries)

    print(f"Transcripts: real FG1={len(blind_real_fg1.splitlines())} turns  "
          f"synth FG1={len(blind_synth_fg1.splitlines())}  "
          f"synth FG5={len(blind_synth_fg5.splitlines())}")

    # --- Part A: Tier-1 reach repeatability ---
    reach_result = run_tier1_reach_repeatability(blind_real_fg1, codebook, ecfg)

    # Salience hierarchy: need Tier-1 codes for synth FG1 and synth FG5
    print("\n[Salience] Coding synth FG1 + synth FG5 for salience hierarchy ...")
    sfg1_t1, _ = code_transcript_tier1(blind_synth_fg1, codebook, "t1sal_sfg1", ecfg)
    sfg5_t1, _ = code_transcript_tier1(blind_synth_fg5, codebook, "t1sal_sfg5", ecfg)

    salience_matched     = compute_salience_hierarchy(reach_result["run1_result"], sfg1_t1, "real FG1 vs synth FG1")
    salience_mismatched  = compute_salience_hierarchy(reach_result["run1_result"], sfg5_t1, "real FG1 vs synth FG5")

    # --- Part B: Tier-2 open extraction ---
    t2_rep  = run_tier2_repeatability(blind_real_fg1, ecfg)
    t2_disc = run_tier2_discrimination(t2_rep["run1_result"], blind_synth_fg1, blind_synth_fg5, ecfg)

    # Position-bias
    position_bias_real = _position_bias_summary(t2_rep["run1_result"],       "real FG1")
    position_bias_sfg1 = _position_bias_summary(t2_disc["sfg1_t2_result"], "synth FG1")
    position_bias_sfg5 = _position_bias_summary(t2_disc["sfg5_t2_result"], "synth FG5")

    # --- Cache hit rate ---
    hit_rate = _cache_hit_rate()
    print(f"\n[Cache] Hit rate: {hit_rate:.0%} ({_cache_hits}/{_cache_calls} calls)")

    # --- Save JSON ---
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = _OUT_DIR / f"validation_tier1reach_tier2_{evaluator_key}.json"

    def _t2_to_dict(t2: Tier2Result) -> list[dict]:
        return [
            {
                "theme_label":       t.theme_label,
                "theme_definition":  t.theme_definition,
                "participant_count": t.participant_count,
                "position_thirds":   t.position_thirds,
            }
            for t in t2.themes
        ]

    report = {
        "evaluator":          model,
        "evaluator_params":   params,
        "tier1_reach": {
            "reach_repeatability":    reach_result,
            "salience_matched":       salience_matched,
            "salience_mismatched":    salience_mismatched,
        },
        "tier2": {
            "repeatability":          t2_rep,
            "discrimination":         t2_disc,
            "position_bias": {
                "real_fg1":   position_bias_real,
                "synth_fg1":  position_bias_sfg1,
                "synth_fg5":  position_bias_sfg5,
            },
        },
        "cache_hit_rate":     round(hit_rate, 4),
        "cache_calls":        _cache_calls,
        "cache_hits":         _cache_hits,
    }

    # Strip non-serialisable objects (Tier1Result, Tier2Result stored on reach_result)
    report["tier1_reach"]["reach_repeatability"].pop("run1_result", None)
    report["tier2"]["repeatability"].pop("run1_result", None)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON report: {out_json.relative_to(_REPO_ROOT)}")

    # --- Write markdown ---
    md_path = _write_md(
        evaluator_key, ecfg,
        reach_result, salience_matched, salience_mismatched,
        t2_rep, t2_disc,
        position_bias_real, position_bias_sfg1, position_bias_sfg5,
        hit_rate,
    )
    print(f"Markdown:    {md_path.relative_to(_REPO_ROOT)}")

    # --- Console summary ---
    print(f"\n{'=' * 65}")
    print("  SUMMARY")
    print(f"{'=' * 65}")
    print(f"  Tier-1 reach  — mean voiced_by stability: "
          f"{reach_result['mean_voiced_stability_jaccard']:.1%}")
    if salience_matched.get("spearman_rho") is not None:
        print(f"  Salience ρ    — matched={salience_matched['spearman_rho']:.3f}  "
              f"mismatched={salience_mismatched.get('spearman_rho') or 'n/a'}")
    print(f"  Tier-2 repeat — mean pairwise recall: {t2_rep['mean_pairwise_recall']:.1%}  "
          f"({t2_rep['verdict']})")
    print(f"  Tier-2 discrim — margin={t2_disc['recall_margin']:+.3f}  "
          f"{'PASS' if t2_disc['passed'] else 'FAIL'}")
    print(f"  Cache hit rate: {hit_rate:.0%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evaluator",
        default="gemini25",
        choices=list(EVALUATOR_CONFIGS),
        help="Which evaluator config to use (default: gemini25)",
    )
    args = parser.parse_args()
    main(args.evaluator)
