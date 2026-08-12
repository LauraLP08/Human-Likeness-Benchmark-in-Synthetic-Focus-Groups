"""
Stage plan and budget for LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION.

Offline; no API call. Every call count is DERIVED from the inventory
(`inductive_inventory.build()`) and from measured rates, never hard-coded. Changing the
corpus changes the budget automatically; a literal in this module would silently go stale.

Measured rates, taken from the hybrid Gemini extraction which used the same prompt family:

    1.681  input tokens per word          (includes per-call prompt overhead)
    3.60   raw themes per 1,000 words
    214.5  output tokens per extracted theme

Stage-B/C/E/F consolidation prompts present `label + definition` only — no quotation, no
JSON evidence scaffolding — which is why a theme costs ~70 tokens to READ against ~214 to
WRITE. Quotations appear only in Stage D, where the contested decision needs them.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_inventory as inv   # noqa: E402
import inductive_segments as seg   # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/final/inductive_budget.json"

ANALYSIS_NAME = "LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION"

# Scenarios for the one quantity that cannot be known before Stage C runs.
UNSTABLE_SCENARIOS = (0.05, 0.15, 0.30)
NEW_CLUSTER_SHARE = 0.08          # planning only; replaced by the observed count

# --- measured rates -------------------------------------------------------
TOK_PER_WORD = 1.681
THEMES_PER_1K_WORDS = 3.60
OUT_TOK_PER_THEME = 214.5
# --- representation sizes -------------------------------------------------
TOK_PER_THEME_READ = 70        # label + definition only
TOK_PER_CLUSTER_READ = 60      # cluster label + definition
TOK_PER_ASSIGNMENT_OUT = 18    # raw_theme_id -> cluster_id + verdict
PROMPT_OVERHEAD = 1200
# --- planning assumptions (declared, not hidden) --------------------------
CLUSTERS_PER_QUESTION = 55
UNSTABLE_SHARE = 0.15
STAGE_D_REPS = 2
STAGE_D_IN_PER_CALL = 3000     # item + candidate clusters + quotations
STAGE_D_OUT_PER_CALL = 300
N_AUDIT_PASSES = 2             # Stage C reassignment audits
# --- Stage F stratification ----------------------------------------------
LENGTH_TERCILES = 3
# --- verified list Batch rate, Claude -------------------------------------
CLAUDE_IN_RATE, CLAUDE_OUT_RATE = 2.50, 12.50


def _themes(words: float, units: int) -> float:
    """Planning theme count: mean of the word-based and unit-based estimates."""
    return ((words / 1000.0 * THEMES_PER_1K_WORDS) + (units * 5.0)) / 2.0


def plan() -> dict:
    o = inv.build()
    if not o["pass"]:
        raise RuntimeError(f"inventory did not pass: {o['problems']}")

    # ---- derived shape, from the REAL segmentation -----------------------
    sg = seg.build()
    if not sg["pass"]:
        raise RuntimeError(f"segmentation did not pass: {sg['problems']}")
    segments = sg["segments"]
    units = o["units"]
    n_units = len(segments)
    questions = sorted({x["question"] for x in segments})
    n_questions = len(questions)
    total_words = sg["total_words"]

    # per-question real word counts — NOT document_words / n_questions
    per_q_words = {q: sum(x["total_words"] for x in segments if x["question"] == q)
                   for q in questions}
    per_q_units = {q: sum(1 for x in segments if x["question"] == q) for q in questions}
    per_q_themes = {q: _themes(per_q_words[q], per_q_units[q]) for q in questions}
    total_themes = sum(per_q_themes.values())

    per_q_human_words = {q: sum(x["total_words"] for x in segments
                                if x["question"] == q and x["condition"] == "human")
                         for q in questions}
    per_q_human_units = {q: sum(1 for x in segments
                                if x["question"] == q and x["condition"] == "human")
                         for q in questions}
    per_q_human_themes = {q: _themes(per_q_human_words[q], per_q_human_units[q])
                          for q in questions}
    per_q_balanced = {q: per_q_human_themes[q] * 3 for q in questions}

    n_unstable = round(total_themes * UNSTABLE_SHARE)
    n_new_cluster = round(total_themes * NEW_CLUSTER_SHARE)

    # Stage F: one unit per question x condition x length tercile
    conditions = sorted({x["condition"] for x in segments})
    f_units = []
    for q in questions:
        for c in conditions:
            for t in (1, 2, 3):
                pool = [x for x in segments if x["question"] == q
                        and x["condition"] == c and x["length_tercile"] == t]
                if pool:
                    f_units.append(sorted(pool, key=lambda z: z["unit_id"])[0])
    n_f_units = len(f_units)
    f_cells = [{"question": x["question"], "condition": x["condition"],
                "length_tercile": x["length_tercile"], "unit_id": x["unit_id"],
                "total_words": x["total_words"]} for x in f_units]
    f_words = sum(x["total_words"] for x in f_units)          # REAL words, not a mean
    f_themes = sum(_themes(x["total_words"], 1) for x in f_units)

    S = []

    def add(stage, model, calls, tin, tout, note):
        S.append({"stage": stage, "model": model, "calls": int(round(calls)),
                  "input_tokens": int(round(tin)), "output_tokens": int(round(tout)),
                  "derivation": note})

    add("A_EXTRACTION", "gemini", n_units,
        total_words * TOK_PER_WORD, total_themes * OUT_TOK_PER_THEME,
        "one call per question x document unit; calls = len(inventory.units)")

    add("B_CANONICAL_TAXONOMY", "gemini", n_questions,
        sum(per_q_themes[q] * TOK_PER_THEME_READ + PROMPT_OVERHEAD for q in questions),
        sum(CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ
            + per_q_themes[q] * TOK_PER_ASSIGNMENT_OUT for q in questions),
        "one canonical taxonomy per question; calls = n_questions")

    add("C_REASSIGNMENT_AUDITS", "gemini", n_questions * N_AUDIT_PASSES,
        N_AUDIT_PASSES * sum(CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ
                             + per_q_themes[q] * TOK_PER_THEME_READ + PROMPT_OVERHEAD
                             for q in questions),
        N_AUDIT_PASSES * sum(per_q_themes[q] * TOK_PER_ASSIGNMENT_OUT
                             for q in questions),
        f"{N_AUDIT_PASSES} audits per question against the frozen canonical taxonomy")

    add("D_UNSTABLE_ADJUDICATION", "claude", n_unstable * STAGE_D_REPS,
        n_unstable * STAGE_D_REPS * STAGE_D_IN_PER_CALL,
        n_unstable * STAGE_D_REPS * STAGE_D_OUT_PER_CALL,
        f"{UNSTABLE_SHARE:.0%} of {total_themes:.0f} themes x {STAGE_D_REPS} repetitions")

    # ---- Stage E, split as required --------------------------------------
    add("E1_BALANCED_TAXONOMY_CONSTRUCTION", "gemini", n_questions,
        sum(per_q_balanced[q] * TOK_PER_THEME_READ + PROMPT_OVERHEAD for q in questions),
        sum(CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ
            + per_q_balanced[q] * TOK_PER_ASSIGNMENT_OUT for q in questions),
        "sees ONLY the balanced subsample; output taxonomy is frozen and hash-keyed")

    add("E2_FULL_REASSIGNMENT_TO_BALANCED_TAXONOMY", "gemini", n_questions,
        sum(CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ
            + per_q_themes[q] * TOK_PER_THEME_READ + PROMPT_OVERHEAD for q in questions),
        sum(per_q_themes[q] * TOK_PER_ASSIGNMENT_OUT for q in questions),
        "ALL raw themes assigned against the frozen E1 taxonomy; E1 is never revised")

    # ---- Stage F, split as required --------------------------------------
    add("E3_BALANCED_NEW_CLUSTER_CONSOLIDATION", "gemini", n_questions,
        n_questions * (n_new_cluster / n_questions * TOK_PER_THEME_READ
                       + CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ + PROMPT_OVERHEAD),
        n_questions * (n_new_cluster / n_questions * TOK_PER_ASSIGNMENT_OUT + 1500),
        "consolidates the E2 NEW_CLUSTER themes among themselves into "
        "BALANCED_TAXONOMY_EXTENDED_V1; E1 is never overwritten")

    add("F1_INSTABILITY_REEXTRACTION", "gemini", n_f_units,
        f_words * TOK_PER_WORD, f_themes * OUT_TOK_PER_THEME,
        f"{n_questions} questions x {len(conditions)} corpora x {LENGTH_TERCILES} "
        "length terciles, one unit each")

    add("F2_PASS2_ASSIGNMENT_TO_CANONICAL_TAXONOMY", "gemini", n_questions,
        sum(CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ
            + (f_themes / n_questions) * TOK_PER_THEME_READ + PROMPT_OVERHEAD
            for _ in questions),
        sum((f_themes / n_questions) * TOK_PER_ASSIGNMENT_OUT for _ in questions),
        "pass-2 themes assigned DIRECTLY against the canonical taxonomy; no "
        "nearest-neighbour matching decides anything")

    by_model = {}
    for s in S:
        m = by_model.setdefault(s["model"], {"calls": 0, "input_tokens": 0,
                                             "output_tokens": 0})
        m["calls"] += s["calls"]
        m["input_tokens"] += s["input_tokens"]
        m["output_tokens"] += s["output_tokens"]

    claude = by_model.get("claude", {"input_tokens": 0, "output_tokens": 0})
    claude_cost = (claude["input_tokens"] / 1e6 * CLAUDE_IN_RATE
                   + claude["output_tokens"] / 1e6 * CLAUDE_OUT_RATE)

    largest = max(
        max(per_q_themes.values()) * TOK_PER_THEME_READ + PROMPT_OVERHEAD,
        CLUSTERS_PER_QUESTION * TOK_PER_CLUSTER_READ
        + max(per_q_themes.values()) * TOK_PER_THEME_READ + PROMPT_OVERHEAD)

    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "analysis": ANALYSIS_NAME,
        "no_api_calls": True,
        "derived_from": "inductive_inventory.build() — no call count is hard-coded",
        "corpus": {"n_documents": o["n_documents"], "n_units": n_units,
                   "total_words": round(total_words),
                   "mean_words_per_unit": round(total_words / n_units)},
        "segmentation": {
            "source": "final/inductive_segments.json",
            "real_per_question_words": {str(q): per_q_words[q] for q in questions},
            "real_per_question_mean_words": {
                str(q): round(per_q_words[q] / per_q_units[q]) for q in questions},
            "even_split_would_have_said": round(total_words / n_units),
            "estimated_by_even_split": False,
            "all_documents_reconcile": sg["all_documents_reconcile"],
            "boundary_ambiguity_runs": sg["boundary_ambiguity"]["n_runs_affected"]},
        "expected_raw_themes": {
            "total": round(total_themes),
            "per_question": {str(q): round(per_q_themes[q]) for q in questions},
            "basis": "mean of word-based (3.60/1k words) and unit-based (5.0/unit)"},
        "balanced_subsample": {
            "rule": ("all human raw themes for the question, plus an equal number drawn "
                     "deterministically by content hash from each synthetic condition"),
            "per_question": {str(q): round(per_q_balanced[q]) for q in questions},
            "human_themes_per_question": {str(q): round(per_q_human_themes[q])
                                          for q in questions}},
        "stage_f_cells": {"n_cells": n_f_units, "cells": f_cells,
                          "rule": "question x condition x length tercile, one unit each"},
        "stages": S,
        "by_model": by_model,
        "claude_cost_usd": round(claude_cost, 2),
        "claude_rate": {"input_per_mtok": CLAUDE_IN_RATE,
                        "output_per_mtok": CLAUDE_OUT_RATE,
                        "source": "verified list Batch rate, 2026-08-02"},
        "gemini_cost_usd": None,
        "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED",
        "totals": {"calls": sum(s["calls"] for s in S),
                   "input_tokens": sum(s["input_tokens"] for s in S),
                   "output_tokens": sum(s["output_tokens"] for s in S)},
        "largest_prompt_tokens": int(round(largest)),
        "context_headroom_vs_200k": round(1 - largest / 200000, 4),
        "budget_class": "PLANNING_ESTIMATE",
        "phased_budget": {
            "PHASE_A_MANIFEST": {
                "status": "EXACT",
                "calls": n_units,
                "basis": "one per segmented unit; 174 is a count, not an estimate"},
            "POST_A_REPLAN": {
                "status": "DEFERRED",
                "recomputes": ["B", "C", "E1", "E2", "E3", "F1", "F2"],
                "trigger": "only once the real raw themes exist",
                "why": "every downstream size depends on the observed theme count"},
            "POST_C_STAGE_D_MANIFEST": {
                "status": "DEFERRED",
                "recomputes": ["D"],
                "trigger": "only once Stage C has produced observed instability",
                "why": ("Stage D volume is the number of OBSERVED unstable cases; the "
                        "scenario share below is a hypothesis, never a measurement")},
        },
        "stage_d_scenarios": {
            f"{int(sh*100)}pct": {
                "unstable_cases": round(total_themes * sh),
                "claude_calls": round(total_themes * sh) * STAGE_D_REPS,
                "claude_cost_usd": round(
                    (round(total_themes * sh) * STAGE_D_REPS * STAGE_D_IN_PER_CALL / 1e6
                     * CLAUDE_IN_RATE)
                    + (round(total_themes * sh) * STAGE_D_REPS * STAGE_D_OUT_PER_CALL
                       / 1e6 * CLAUDE_OUT_RATE), 2)}
            for sh in UNSTABLE_SCENARIOS},
        "planning_assumptions": {
            "clusters_per_question": CLUSTERS_PER_QUESTION,
            "unstable_share_PLANNING_ONLY": UNSTABLE_SHARE,
            "unstable_scenarios": list(UNSTABLE_SCENARIOS),
            "new_cluster_share_PLANNING_ONLY": NEW_CLUSTER_SHARE,
            "stage_d_repetitions": STAGE_D_REPS,
            "tokens_per_theme_read": TOK_PER_THEME_READ,
            "tokens_per_theme_written": OUT_TOK_PER_THEME},
    }
    return out


def write(out: dict, path=None) -> Path:
    """Persist a budget explicitly; plan() itself is side-effect free."""
    path = Path(path) if path is not None else _OUT
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def main() -> int:
    b = plan()
    write(b)
    c = b["corpus"]
    print(f"{b['analysis']}\n")
    print(f"corpus: {c['n_documents']} documents, {c['n_units']} units, "
          f"{c['total_words']:,} words")
    print(f"expected raw themes: {b['expected_raw_themes']['total']} "
          f"({b['expected_raw_themes']['per_question']})\n")
    print(f"{'stage':44s}{'model':8s}{'calls':>7s}{'input':>11s}{'output':>10s}")
    for s in b["stages"]:
        print(f"{s['stage']:44s}{s['model']:8s}{s['calls']:>7d}"
              f"{s['input_tokens']:>11,}{s['output_tokens']:>10,}")
    print()
    for m, v in b["by_model"].items():
        print(f"{m.upper():8s} {v['calls']:>4d} calls   in {v['input_tokens']:>10,}"
              f"   out {v['output_tokens']:>9,}")
    t = b["totals"]
    print(f"{'TOTAL':8s} {t['calls']:>4d} calls   in {t['input_tokens']:>10,}"
          f"   out {t['output_tokens']:>9,}")
    print(f"\nClaude cost: ${b['claude_cost_usd']:.2f} (verified list Batch rate)")
    print(f"Gemini cost: {b['gemini_cost_status']}")
    print(f"largest prompt: {b['largest_prompt_tokens']:,} tokens "
          f"({b['context_headroom_vs_200k']*100:.1f}% headroom vs 200k)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
