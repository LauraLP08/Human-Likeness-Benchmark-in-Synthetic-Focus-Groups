"""
EXPLORATORY_OUT_OF_DOMAIN_LEXICAL_TRANSPORTABILITY_CHECK — DS05 mindfulness.

Offline only. No API calls.

METHOD IDENTITY
Every measure is IMPORTED from scripts/lexical_analysis.py, not re-implemented:
the tokenisation arms, the token budgets, the deterministic offset scheme, the
Jaccard / Jensen-Shannon / cosine computations and the MATTR windows are the
same objects the Macho Meals analysis used. Nothing is re-derived here, so the
specifications cannot silently drift.

WHY A PREFLIGHT COMES FIRST
The budget-equalised design requires EVERY compared participant to supply at
least `budget` tokens. A domain with fewer participants, shorter turns or a
smaller corpus may not support every specification. When a specification is
infeasible the correct action is to report it as infeasible — not to impute, not
to lower the budget silently, and not to drop the short speaker.

WHAT IS AND IS NOT COMPARED
  - PRIMARY: human DS05 vs synthetic DS05 — a within-domain comparison.
  - DESCRIPTIVE REFERENCE ONLY: Macho Meals human and synthetic values, shown
    alongside. These are a different domain and a different study design. They
    are never pooled with DS05, never averaged with it, and no test is run
    between them.

Documents, participants and domains are never treated as interchangeable
independent observations.

Usage:
    py scripts/lexical_transportability_mindfulness.py --preflight
    py scripts/lexical_transportability_mindfulness.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.lexical_analysis import (  # noqa: E402
    BUDGETS,
    MATTR_WINDOWS,
    N_SUBSAMPLES,
    TOKENISERS,
    _budgeted_overlap,
    _diversity,
    _speaker_tokens,
    _unadjusted_jaccard,
)
from scripts.lexical_analysis import _human_session as _macho_human_session  # noqa: E402

_MINDFULNESS = _ROOT / "data/datasets_transcripts/standardized/mindfulness/fg1"
_OUT_DIR = _ROOT / "analysis/transportability_mindfulness"
_OUT = _OUT_DIR / "lexical_transportability.json"

CLASSIFICATION = "EXPLORATORY_OUT_OF_DOMAIN_LEXICAL_TRANSPORTABILITY_CHECK"


def _mindfulness_human_turns() -> list[dict]:
    turns = json.loads((_MINDFULNESS / "transcript.json").read_text(encoding="utf-8"))
    return [
        {"speaker": t["canonical_speaker_id"], "role": t.get("speaker_role", ""), "text": t["content"]}
        for t in turns
    ]


def _mindfulness_synthetic_turns() -> list[dict]:
    """The comparable window derived by scripts/transportability_synthetic_window.py."""
    from scripts.transportability_synthetic_window import (
        _load_synthetic,
        _turn_to_section,
    )

    synthetic = _load_synthetic()
    turn_section = _turn_to_section()
    guide = json.loads(
        (_ROOT / "configs/experiment/mindfulness_fg1_run01.json").read_text(encoding="utf-8")
    )["discussion_guide"]
    drop = {s["section_index"] for s in guide if s["section_phase"] in {"intro", "closing"}}
    window = [t for t in synthetic if turn_section.get(t["turn"]) not in drop
              and turn_section.get(t["turn"]) is not None]
    return [{"speaker": t["speaker_id"], "role": t["speaker_role"], "text": t["content"]}
            for t in window]


def preflight(sides: dict[str, list[dict]]) -> dict:
    """
    Which (tokeniser x budget) specifications are feasible on BOTH DS05 sides?

    A specification is feasible for a side when every participant on that side
    supplies at least `budget` tokens under that tokenisation. A specification is
    COMPARABLE only when it is feasible on both sides.
    """
    per_side: dict[str, dict] = {}
    for side, turns in sides.items():
        arms = {}
        for arm, tk in TOKENISERS.items():
            toks = _speaker_tokens(turns, tk)
            counts = {s: len(v) for s, v in toks.items()}
            arms[arm] = {
                "n_participants": len(counts),
                "tokens_per_participant": counts,
                "min_tokens": min(counts.values()) if counts else 0,
                "feasible_budgets": [b for b in BUDGETS if counts and min(counts.values()) >= b],
                "infeasible_budgets": [b for b in BUDGETS if not counts or min(counts.values()) < b],
                "limiting_participant": (min(counts, key=counts.get) if counts else None),
            }
        per_side[side] = arms

    comparable, not_comparable = [], []
    for arm in TOKENISERS:
        for budget in BUDGETS:
            spec = f"{arm}::budget{budget}"
            ok = all(budget in per_side[s][arm]["feasible_budgets"] for s in sides)
            if ok:
                comparable.append(spec)
            else:
                blockers = {
                    s: {
                        "min_tokens": per_side[s][arm]["min_tokens"],
                        "limiting_participant": per_side[s][arm]["limiting_participant"],
                    }
                    for s in sides
                    if budget not in per_side[s][arm]["feasible_budgets"]
                }
                not_comparable.append({"specification": spec, "blocked_by": blockers})

    return {
        "per_side": per_side,
        "comparable_specifications": comparable,
        "not_comparable_specifications": not_comparable,
        "n_comparable": len(comparable),
        "n_total": len(TOKENISERS) * len(BUDGETS),
        "verdict": "PROCEED" if comparable else "NO_COMPARABLE_SPECIFICATION",
        "rule": (
            "A specification is comparable only when every participant on BOTH DS05 sides "
            "supplies at least `budget` tokens. Infeasible specifications are reported, never "
            "imputed and never silently down-budgeted."
        ),
    }


def analyse(sides: dict[str, list[dict]], comparable: list[str]) -> dict:
    results: dict = {"budget_equalised": {}, "unadjusted": {}, "diversity": {}}

    for side, turns in sides.items():
        results["unadjusted"][side] = {
            arm: _unadjusted_jaccard(turns, tk) for arm, tk in TOKENISERS.items()
        }
        results["diversity"][side] = _diversity(turns)

    for spec in comparable:
        arm, budget_str = spec.split("::budget")
        budget = int(budget_str)
        results["budget_equalised"][spec] = {
            side: _budgeted_overlap(turns, TOKENISERS[arm], budget, N_SUBSAMPLES)
            for side, turns in sides.items()
        }
    return results


def _macho_reference() -> dict:
    """Descriptive reference only. Never pooled with DS05."""
    frozen = _ROOT / "analysis/production_evaluation/final/lexical_analysis.json"
    if not frozen.exists():
        return {"available": False, "why": f"{frozen.name} not found"}
    data = json.loads(frozen.read_text(encoding="utf-8"))
    return {
        "available": True,
        "source": str(frozen.relative_to(_ROOT)).replace("\\", "/"),
        "status": "DESCRIPTIVE_REFERENCE_ONLY_DIFFERENT_DOMAIN_AND_DESIGN",
        "never_pooled_with_ds05": True,
        "summary_budget_equalised": data.get("summary", {}).get("budget_equalised"),
        "diversity": data.get("diversity"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", help="feasibility only, no analysis")
    args = parser.parse_args()

    sides = {
        "mindfulness_human": _mindfulness_human_turns(),
        "mindfulness_synthetic": _mindfulness_synthetic_turns(),
    }

    pf = preflight(sides)

    print("=" * 78)
    print("FEASIBILITY PREFLIGHT — DS05 lexical distinctiveness")
    print("=" * 78)
    for side, arms in pf["per_side"].items():
        print(f"\n  {side}")
        for arm, info in arms.items():
            print(f"    {arm:24s} participants={info['n_participants']} "
                  f"min_tokens={info['min_tokens']:5d} "
                  f"feasible_budgets={info['feasible_budgets']} "
                  f"(limiting: {info['limiting_participant']})")
    print(f"\n  comparable specifications: {pf['n_comparable']}/{pf['n_total']}")
    for spec in pf["comparable_specifications"]:
        print(f"    OK   {spec}")
    for item in pf["not_comparable_specifications"]:
        blockers = ", ".join(
            f"{s} min={d['min_tokens']}" for s, d in item["blocked_by"].items()
        )
        print(f"    SKIP {item['specification']:32s} blocked by {blockers}")
    print(f"\n  verdict: {pf['verdict']}")

    if args.preflight:
        return 0

    if pf["verdict"] != "PROCEED":
        print("\nNo comparable specification — no lexical result is reported.")
        report = {
            "record_type": CLASSIFICATION,
            "classification": CLASSIFICATION,
            "no_api_calls": True,
            "preflight": pf,
            "results": None,
            "why_no_results": "no (tokeniser x budget) specification was feasible on both sides",
        }
    else:
        results = analyse(sides, pf["comparable_specifications"])
        report = {
            "record_type": CLASSIFICATION,
            "classification": CLASSIFICATION,
            "no_api_calls": True,
            "method_identity": (
                "All measures imported from scripts/lexical_analysis.py: same tokenisation arms, "
                "same budgets, same deterministic offsets, same Jaccard / Jensen-Shannon / cosine, "
                "same MATTR windows. Nothing re-implemented."
            ),
            "primary_comparison": "mindfulness_human vs mindfulness_synthetic (within domain)",
            "macho_meals_reference": _macho_reference(),
            "independence_note": (
                "Documents, participants and domains are NOT treated as interchangeable "
                "independent observations. Budget windows are overlapping slices of one "
                "speaker's stream; no CI or p-value is derived from their spread."
            ),
            "preflight": pf,
            "results": results,
        }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {_OUT.relative_to(_ROOT)}")

    if report.get("results"):
        print("\n=== budget-equalised overlap (higher jaccard/cosine = LESS distinct) ===")
        print(f"{'specification':34s} {'measure':26s} {'HUMAN':>9s} {'SYNTH':>9s}")
        print("-" * 82)
        for spec, sides_res in report["results"]["budget_equalised"].items():
            for measure in ("jaccard", "jensen_shannon_distance", "cosine_similarity"):
                h = sides_res["mindfulness_human"]
                s = sides_res["mindfulness_synthetic"]
                hv = h[measure]["mean"] if h else None
                sv = s[measure]["mean"] if s else None
                print(f"{spec:34s} {measure:26s} {str(hv):>9s} {str(sv):>9s}")
        print("\n=== diversity (MATTR — less length-sensitive, not length-insensitive) ===")
        for side, d in report["results"]["diversity"].items():
            if d:
                mattr = {f"mattr_w{w}": d.get(f"mattr_w{w}") for w in MATTR_WINDOWS}
                print(f"  {side:24s} n_tokens={d['n_tokens']:6d} ttr={d['ttr']} {mattr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
