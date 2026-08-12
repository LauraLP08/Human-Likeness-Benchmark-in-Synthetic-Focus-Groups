"""
Phase A final gate, accepted_v2, observed inventory and POST_A_REPLAN.

    py scripts/phase_a_finalise.py

Resolves the repair verdict into the theme-level validation, applies the final gate, and
emits the observed inventory. Stage B is NOT executed.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa            # noqa: E402
import phase_a_revalidation as rv         # noqa: E402
import inductive_inventory as invmod      # noqa: E402

D = _ROOT / "analysis/production_evaluation/inductive_phase_a"


def build() -> dict:
    val = rv.revalidate()
    rep_man = json.loads(
        (D / "evidence_repair_manifest.json").read_text(encoding="utf-8"))
    rep_raw = json.loads((D / "phase_a_repair_raw.json").read_text(encoding="utf-8"))
    _, ren = pa.build_manifest()

    resolutions = {}
    for resp in rep_raw["responses"]:
        req = next(r for r in rep_man["requests"]
                   if r["custom_request_key"] == resp["custom_request_key"])
        key = (req["unit_id"], req["theme_id"])
        if "STOP" not in resp["finish_reason"].upper():
            resolutions[key] = {"resolution": "QUARANTINE",
                                "problems": ["truncated response"]}
            continue
        resolutions[key] = rv.validate_repair(json.loads(resp["raw_text"]),
                                              ren[req["unit_id"]]["turns"])

    units, excluded, quarantined = [], [], []
    n_themes = n_quotes = 0
    for u in val["units"]:
        themes = []
        for t in u["themes"]:
            if t["status"] == rv.THEME_ACCEPTED:
                themes.append(t)
                continue
            r = resolutions.get((u["unit_id"], t["theme_id"]))
            if r is None:
                quarantined.append({"unit_id": u["unit_id"], "theme_id": t["theme_id"],
                                    "problems": ["no repair result"]})
            elif r["resolution"] == "KEEP_THEME":
                themes.append({**t, "status": rv.THEME_ACCEPTED,
                               "n_valid_quotes": 1,
                               "valid_quotes": [{
                                   "verdict": rv.Q_VALID, "turn_id": r["turn_id"],
                                   "speaker": r["speaker"], "quote": r["quote"],
                                   "raw_exact_contiguous": True,
                                   "source": "PHASE_A_EVIDENCE_REPAIR"}],
                               "resolution": "REPAIRED_SUPPORTED"})
            elif r["resolution"] == "EXCLUDE_THEME":
                excluded.append({"unit_id": u["unit_id"], "theme_id": t["theme_id"],
                                 "label": t["label"],
                                 "reason": "NOT_SUPPORTED_IN_UNIT",
                                 "evidence_invented": False})
            else:
                quarantined.append({"unit_id": u["unit_id"], "theme_id": t["theme_id"],
                                    "problems": r["problems"]})
        n_themes += len(themes)
        n_quotes += sum(t["n_valid_quotes"] for t in themes)
        units.append({**{k: u[k] for k in
                         ("unit_id", "question", "condition", "fg",
                          "canonical_replication_index", "physical_run",
                          "length_tercile")},
                      "n_themes": len(themes),
                      "n_quotes": sum(t["n_valid_quotes"] for t in themes),
                      "themes": themes, "unit_status": "RESOLVED"})

    audit = json.loads((D / "rejected_quotes_audit.json").read_text(encoding="utf-8"))
    gate = {
        "units_resolved": f"{len(units)}/174",
        "all_174_units_resolved": len(units) == 174,
        "every_retained_theme_has_a_valid_quote": all(
            t["n_valid_quotes"] >= 1 for u in units for t in u["themes"]),
        "moderator_quotes": val["quote_verdicts"].get(rv.Q_MODERATOR, 0),
        "themes_without_evidence": sum(1 for u in units for t in u["themes"]
                                       if t["n_valid_quotes"] == 0),
        "incomplete_results": len(quarantined),
        "exclusions_recorded": len(excluded),
        "rejected_quotes_retained_in_audit": audit["n_rejected"],
        "counts_rebuilt_from_resolved_units": True,
    }
    gate["pass"] = bool(gate["all_174_units_resolved"]
                        and gate["every_retained_theme_has_a_valid_quote"]
                        and gate["moderator_quotes"] == 0
                        and gate["themes_without_evidence"] == 0
                        and gate["incomplete_results"] == 0)
    return {"val": val, "units": units, "excluded": excluded,
            "quarantined": quarantined, "gate": gate,
            "n_themes": n_themes, "n_quotes": n_quotes,
            "repair_usage": rep_raw["responses"][0]["usage"]}


def main() -> int:
    b = build()
    val, units, gate = b["val"], b["units"], b["gate"]
    raw_orig = json.loads(
        (D / "phase_a_raw_responses.json").read_text(encoding="utf-8"))

    def by(key):
        d = defaultdict(lambda: [0, 0, 0])
        for u in units:
            k = u[key] if u[key] is not None else "human"
            d[k][0] += 1
            d[k][1] += u["n_themes"]
            d[k][2] += u["n_quotes"]
        return {str(k): {"units": v[0], "themes": v[1], "quotes": v[2],
                         "mean_themes": round(v[1] / v[0], 3)}
                for k, v in sorted(d.items(), key=lambda x: str(x[0]))}

    inventory = {"by_question": by("question"), "by_condition": by("condition"),
                 "by_fg": by("fg"),
                 "by_replication": by("canonical_replication_index"),
                 "by_length_tercile": by("length_tercile")}

    out = {"built_utc": datetime.now(UTC).isoformat(),
           "stage": "PHASE_A_EXTRACTION",
           "supersedes": "phase_a_accepted.json (PROVISIONAL_SUPERSEDED)",
           "policy_id": rv.POLICY_ID,
           "metric_name": rv.METRIC_NAME,
           "metric_is_not": "character_exact_quote",
           "authoritative_text": rv.AUTHORITATIVE_TEXT,
           "raw_exact_diagnostic": val["raw_exact_diagnostic"],
           "repair_validated_without_normalisation": True,
           "gate": gate,
           "n_units": len(units), "n_themes": b["n_themes"], "n_quotes": b["n_quotes"],
           "excluded_themes": b["excluded"], "quarantined": b["quarantined"],
           "observed_inventory": inventory,
           "tokens": {
               "original_batch": raw_orig["measured_usage"],
               "evidence_repair": b["repair_usage"],
               "total_input": (raw_orig["measured_usage"]["input_tokens"]
                               + b["repair_usage"]["input_tokens"]),
               "total_output": (raw_orig["measured_usage"]["output_tokens"]
                                + b["repair_usage"]["output_tokens"]),
               "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED"},
           "units": units}
    rv._atomic(D / "phase_a_accepted_v2.json", out)

    inv = invmod.build()
    per_q = {str(q): inventory["by_question"][str(q)]["themes"] for q in (1, 2, 3, 4, 5)}
    replan = {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "POST_A_REPLAN",
        "status": "OBSERVED_NOT_ESTIMATED",
        "supersedes": "expected_raw_themes in inductive_budget.plan()",
        "basis": "the completed Phase A inventory over 174 resolved units",
        "observed_raw_themes_total": b["n_themes"],
        "observed_raw_themes_per_question": per_q,
        "previous_planning_estimate": {
            "total": 925,
            "per_question": {"1": 142, "2": 159, "3": 204, "4": 211, "5": 210}},
        "planning_estimate_overshoot_pct": round(
            (925 - b["n_themes"]) / b["n_themes"] * 100, 1),
        "stages_to_recompute": ["B", "C", "E1", "E2", "E3", "F1", "F2"],
        "stages_executed": [],
        "curve_restriction_Q4": {k: inv["per_question"][4][k] for k in
                                 ("n_units_in_universe", "n_units_in_curve",
                                  "n_fgs", "n_orderings")},
        "note": ("call counts, prompt sizes and budget for B-F must be rebuilt from "
                 "these observed theme counts; no stage beyond A is executed here"),
    }
    rv._atomic(D / "POST_A_REPLAN.json", replan)

    print("=== GATE FINAL DE PHASE A ===")
    for k, v in gate.items():
        print(f"  {k:42s} {v}")
    print(f"\n  temas aceptados {b['n_themes']}   citas aceptadas {b['n_quotes']}")
    print(f"  excluidos {len(b['excluded'])}   cuarentena {len(b['quarantined'])}")
    print(f"\n  POST_A_REPLAN: {b['n_themes']} temas observados vs 925 estimados "
          f"({replan['planning_estimate_overshoot_pct']:+}% de sobreestimación)")
    print("  por pregunta:", per_q)
    t = out["tokens"]
    print(f"\n  tokens batch original : in {t['original_batch']['input_tokens']:,} "
          f"out {t['original_batch']['output_tokens']:,}")
    print(f"  tokens reparación     : in {t['evidence_repair']['input_tokens']:,} "
          f"out {t['evidence_repair']['output_tokens']:,}")
    print(f"  total                 : in {t['total_input']:,} out {t['total_output']:,}")
    print(f"  coste gemini          : {t['gemini_cost_status']}")
    return 0 if gate["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
