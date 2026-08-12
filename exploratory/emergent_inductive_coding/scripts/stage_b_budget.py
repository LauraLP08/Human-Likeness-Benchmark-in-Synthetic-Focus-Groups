"""
POST_A_REPLAN and the B-F budget, rebuilt on the 526 OBSERVED raw themes.

    py scripts/stage_b_budget.py

The previous plan assumed 925 themes. That figure is superseded everywhere here; nothing
in this module reads it except to record the overshoot.

Three classes of figure are kept apart and never blended:

  EXACT       known now, a count rather than a forecast
  ESTIMATE    still depends on a result that does not exist yet
  DEFERRED    cannot be estimated at all until an earlier stage is observed

Stage D stays DEFERRED: its call volume is a function of the instability Stage C
produces, and no amount of arithmetic on Phase A can anticipate it.

NO API CALLS in this module.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

_D = _ROOT / "analysis/production_evaluation/inductive_phase_a"
_B = _ROOT / "analysis/production_evaluation/inductive_stage_b"
_V2 = _D / "phase_a_accepted_v2.json"

EXACT, ESTIMATE, DEFERRED = "EXACT", "ESTIMATE", "DEFERRED"

# Retained only to record how far the planning figure was out.
SUPERSEDED_PLANNING_TOTAL = 925


def observed() -> dict:
    v2 = json.loads(_V2.read_text(encoding="utf-8"))
    if not v2["gate"]["pass"]:
        raise RuntimeError("Phase A gate did not pass; Stage B has no binding source")
    themes = [(u["question"], t) for u in v2["units"] for t in u["themes"]]
    per_q = Counter(q for q, _ in themes)
    return {"n_units": len(v2["units"]), "n_themes": len(themes),
            "per_question": {str(q): per_q[q] for q in (1, 2, 3, 4, 5)},
            "n_quotes": v2["n_quotes"],
            "per_condition": dict(Counter(
                u["condition"] for u in v2["units"] for _ in u["themes"]))}


def plan() -> dict:
    o = observed()
    n = o["n_themes"]
    per_q = o["per_question"]

    # Stage B: one call per question, the whole theme list for that question in one
    # prompt. Both numbers are counts, not forecasts.
    b_tokens_in = sum(round(v * 60 + 400) for v in per_q.values())
    b_tokens_out = sum(round(v * 45 + 300) for v in per_q.values())

    stages = [
        {"stage": "B_CANONICAL_TAXONOMY", "class": EXACT, "model": "gemini",
         "calls": 5, "basis": "one per question; 5 is a count",
         "input_tokens": b_tokens_in, "output_tokens": b_tokens_out,
         "token_class": ESTIMATE,
         "token_basis": "60 input / 45 output tokens per theme plus per-call overhead"},
        {"stage": "C_ASSIGNMENT_STABILITY", "class": ESTIMATE, "model": "gemini",
         "calls": 5 * 2,
         "basis": ("one repetition pair per question over the frozen Stage-B taxonomy; "
                   "exact once Stage B returns"),
         "input_tokens": b_tokens_in * 2, "output_tokens": round(b_tokens_out * 0.6) * 2,
         "token_class": ESTIMATE},
        {"stage": "D_DISAMBIGUATION", "class": DEFERRED, "model": "claude",
         "calls": None,
         "basis": ("a function of the unstable assignments Stage C produces; it cannot "
                   "be derived from Phase A and is not estimated here"),
         "input_tokens": None, "output_tokens": None, "token_class": DEFERRED},
        {"stage": "E1_BALANCED_SUBSAMPLE_TAXONOMY", "class": ESTIMATE, "model": "gemini",
         "calls": 5,
         "basis": ("one per question over a condition-balanced subsample; the subsample "
                   "size depends on the human theme count per question"),
         "input_tokens": None, "output_tokens": None, "token_class": DEFERRED},
        {"stage": "E2_BALANCED_ASSIGNMENT", "class": ESTIMATE, "model": "gemini",
         "calls": 5, "basis": "one per question against the frozen E1 taxonomy",
         "input_tokens": None, "output_tokens": None, "token_class": DEFERRED},
        {"stage": "E3_CURVES", "class": EXACT, "model": None, "calls": 0,
         "basis": "offline computation; no model call",
         "input_tokens": 0, "output_tokens": 0, "token_class": EXACT},
        {"stage": "F1_AUDIT_SAMPLE", "class": DEFERRED, "model": "claude", "calls": None,
         "basis": "sampled from Stage-C assignments that do not exist yet",
         "input_tokens": None, "output_tokens": None, "token_class": DEFERRED},
        {"stage": "F2_AUDIT_ADJUDICATION", "class": DEFERRED, "model": "claude",
         "calls": None, "basis": "follows F1", "input_tokens": None,
         "output_tokens": None, "token_class": DEFERRED},
    ]

    known_calls = sum(s["calls"] for s in stages if s["calls"] is not None)
    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "POST_A_REPLAN",
        "status": "REBUILT_ON_OBSERVED_PHASE_A",
        "binding_source": str(_V2.relative_to(_ROOT)),
        "observed": o,
        "superseded_planning_total": SUPERSEDED_PLANNING_TOTAL,
        "planning_overshoot_pct": round(
            (SUPERSEDED_PLANNING_TOTAL - n) / n * 100, 1),
        "figure_classes": {
            EXACT: "a count known now",
            ESTIMATE: "still depends on a result that does not exist yet",
            DEFERRED: "cannot be estimated until an earlier stage is observed"},
        "stage_d_status": DEFERRED,
        "stage_d_reason": ("Stage D volume is a function of the instability Stage C "
                           "produces; estimating it from Phase A would be inventing a "
                           "number"),
        "stages": stages,
        "known_model_calls": known_calls,
        "stages_executed_here": ["B_CANONICAL_TAXONOMY"],
        "stages_not_executed": ["C", "D", "E1", "E2", "E3", "F1", "F2"],
        "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED",
        "claude_rate": {"input_per_mtok": 2.5, "output_per_mtok": 12.5,
                        "verified_utc": "2026-08-02",
                        "applies_to": "Stage D and F only, both DEFERRED"},
    }


def main() -> int:
    p = plan()
    o = p["observed"]
    _B.mkdir(parents=True, exist_ok=True)
    tmp = _B / "post_a_replan_v2.json.tmp"
    tmp.write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
    import os
    os.replace(tmp, _B / "post_a_replan_v2.json")
    # keep the Phase A copy in step, without touching any other Phase A artefact
    tmp2 = _D / "POST_A_REPLAN.json.tmp"
    tmp2.write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp2, _D / "POST_A_REPLAN.json")

    print("=== POST_A_REPLAN reconstruido sobre lo observado ===")
    print(f"  temas observados {o['n_themes']}  (plan anterior "
          f"{SUPERSEDED_PLANNING_TOTAL}, sobreestimación "
          f"{p['planning_overshoot_pct']:+}%)")
    print(f"  por pregunta {o['per_question']}")
    print(f"  por condición {o['per_condition']}")
    print("\n  etapas:")
    for s in p["stages"]:
        calls = "DEFERRED" if s["calls"] is None else s["calls"]
        print(f"    {s['stage']:32s} {s['class']:9s} llamadas {calls}")
    print(f"\n  llamadas conocidas ahora: {p['known_model_calls']}")
    print(f"  Stage D: {p['stage_d_status']} — {p['stage_d_reason'][:70]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
