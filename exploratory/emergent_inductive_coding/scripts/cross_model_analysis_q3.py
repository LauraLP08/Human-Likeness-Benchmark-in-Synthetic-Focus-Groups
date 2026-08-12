"""
Judge calibration, then corroboration, then the final emergent-phase state.

Order is enforced: the 14 calibration cases are scored FIRST, and if the judge
systematically contradicts the researcher — or confuses a granularity difference with
thematic absence — the 24 pending cases are not resolved with it.

Nothing here calls an API. It reads cross_model_results_q3.json.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import cross_model_audit_q3 as cm      # noqa: E402
import emergent_calibration_q3 as cal  # noqa: E402

_DIR = cal._DIR

# Claude's task-A categories, collapsed to the same binary the researcher decided on.
CORRESPONDS = {"SAME_SUBSTANTIVE_THEME",
               "PARTIAL_OVERLAP_REFERENCE_MORE_SPECIFIC",
               "PARTIAL_OVERLAP_CANDIDATE_MORE_SPECIFIC"}
DOES_NOT = {"NO_CORRESPONDENCE", "RELATED_BUT_DISTINCT"}
ABSTAIN = {"UNCERTAIN"}

# ANALYTIC DECISION, not a validated standard, and fixed before the results were read:
# the judge is unusable if it contradicts the researcher on most decided calibration
# cases, or if it reads a coarser-grained human match as thematic absence in more than
# one unit. Both are systematic-failure signals, not accuracy thresholds.
UNUSABLE_IF = (
    "contradicts the researcher on more than half of the decided calibration cases",
    "reads a one-to-many or many-to-one human match as non-correspondence "
    "(NO_CORRESPONDENCE or RELATED_BUT_DISTINCT) in >= 2 units",
)


def _atomic(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _load():
    res = json.loads((_DIR / "cross_model_results_q3.json").read_text(encoding="utf-8"))
    man = json.loads((_DIR / "cross_model_manifest_q3.json").read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for g in ("calibration", "pending")
             for c in man["cases"][g]}
    by_case = {}
    for r in res["results"]:
        by_case.setdefault(r["case_id"], {})[r["repetition_index"]] = r
    return res, cases, by_case


def calibrate() -> dict:
    _, cases, by_case = _load()
    rows, matrix = [], Counter()
    gran_confusions = []

    for cid, c in sorted(cases.items()):
        if not cid.startswith("CAL::"):
            continue
        human = c["human_decision_WITHHELD_FROM_PROMPT"]
        rel = c["human_relation_WITHHELD_FROM_PROMPT"]
        reps = by_case.get(cid, {})
        cats = [reps[i]["judgement"]["category"] for i in (1, 2)
                if i in reps and reps[i].get("judgement")]
        confs = [reps[i]["judgement"]["confidence"] for i in (1, 2)
                 if i in reps and reps[i].get("judgement")]
        if len(cats) < 2:
            rows.append({"case_id": cid, "human": human, "relation": rel,
                         "claude": cats, "agreement": "NO_OUTPUT"})
            continue

        stable = cats[0] == cats[1]
        claude_side = ("corresponds" if cats[0] in CORRESPONDS else
                       "does_not" if cats[0] in DOES_NOT else "abstain")
        human_side = "corresponds" if human == "MATCHED" else "does_not"

        if not stable:
            agreement = "UNSTABLE"
        elif claude_side == "abstain":
            agreement = "ABSTAIN"
        elif claude_side == human_side:
            agreement = "AGREE"
        else:
            agreement = "DISAGREE"
        if agreement in ("AGREE", "DISAGREE"):
            matrix[(human_side, claude_side)] += 1

        if (agreement == "DISAGREE" and human_side == "corresponds"
                and rel in ("one_to_many", "many_to_one")
                and cats[0] in DOES_NOT):
            gran_confusions.append({"case_id": cid, "relation": rel,
                                    "unit": c["unit_id"], "claude": cats[0]})

        rows.append({"case_id": cid, "stratum": c["stratum"], "unit_id": c["unit_id"],
                     "human": human, "relation": rel,
                     "claude_rep1": cats[0], "claude_rep2": cats[1],
                     "confidence": confs, "stable": stable,
                     "claude_side": claude_side, "human_side": human_side,
                     "agreement": agreement})

    decided = [r for r in rows if r["agreement"] in ("AGREE", "DISAGREE")]
    n_agree = sum(1 for r in decided if r["agreement"] == "AGREE")
    n_dis = len(decided) - n_agree
    units_confused = {g["unit"] for g in gran_confusions}

    fail_majority = bool(decided) and n_dis > len(decided) / 2
    fail_gran = len(units_confused) >= 2
    usable = not (fail_majority or fail_gran)
    # The judge cleared the two systematic-failure rules, and nothing more. It is a
    # corroborating voice, never an arbiter: it self-contradicted on 5 of 14 settled
    # cases, abstained zero times, and produced 8 non-verbatim quotations of which 2
    # were fabricated. "Usable" here means usable FOR CORROBORATION ONLY.
    usable_label = ("USABLE_FOR_CORROBORATION_ONLY" if usable
                    else "NOT_USABLE_SYSTEMATIC_CONTRADICTION")

    return {
        "n_calibration_cases": len(rows),
        "n_decided": len(decided),
        "n_agree": n_agree,
        "n_disagree": n_dis,
        "exact_agreement_on_decided": (n_agree / len(decided)) if decided else None,
        "n_abstain": sum(1 for r in rows if r["agreement"] == "ABSTAIN"),
        "n_unstable": sum(1 for r in rows if r["agreement"] == "UNSTABLE"),
        "disagreement_matrix_decided_cases_only": {
            f"human={h} | claude={c}": n for (h, c), n in sorted(matrix.items())},
        "instability_rate": (sum(1 for r in rows if r["agreement"] == "UNSTABLE")
                             / len(rows)) if rows else None,
        "granularity_confusions": gran_confusions,
        "units_with_granularity_confusion": sorted(units_confused),
        "unusable_if": list(UNUSABLE_IF),
        "failed_majority_rule": fail_majority,
        "failed_granularity_rule": fail_gran,
        "judge_usable_for_pending_cases": usable_label,
        "judge_usable_boolean": usable,
        "what_usable_does_not_mean": (
            "It is NOT evidence of reliability sufficient for autonomous adjudication. "
            "The judge may corroborate a human-anchored finding; it may not settle one."),
        "reliability_against_it": {
            "exact_agreement_with_researcher": f"{n_agree}/{len(decided)} stable cases",
            "self_contradiction_rate": f"{sum(1 for r in rows if r['agreement']=='UNSTABLE')}"
                                       f"/{len(rows)}",
            "abstentions": sum(1 for r in rows if r["agreement"] == "ABSTAIN"),
        },
        "note": ("No universal accuracy threshold is asserted. The two rules above are "
                 "systematic-failure signals fixed before the results were read, and "
                 "are analytic decisions rather than validated standards."),
        "rows": rows,
    }


def corroborate_pending() -> dict:
    _, cases, by_case = _load()
    out = []
    for cid, c in sorted(cases.items()):
        if cid.startswith("CAL::"):
            continue
        reps = by_case.get(cid, {})
        if 1 not in reps or 2 not in reps or not all(
                reps[i].get("judgement") for i in (1, 2)):
            out.append({"case_id": cid, "task": c["task"], "status": cm.UNRESOLVED,
                        "reasons": ["one or both repetitions produced no judgement"]})
            continue
        v = cm.corroborate(reps[1]["judgement"], reps[2]["judgement"],
                           cal.unit_lines(c["unit_id"]))
        alias = cm.CATEGORY_ALIASES.get(v["category"], v["category"])
        out.append({"case_id": cid, "task": c["task"], "unit_id": c["unit_id"],
                    "provenance": c.get("provenance", {}),
                    "status": v["status"], "category": alias,
                    "category_as_returned": v["category"],
                    "confidence": [reps[i]["judgement"]["confidence"] for i in (1, 2)],
                    "reasons": v["reasons"]})
    return {"n": len(out),
            "n_corroborated": sum(1 for x in out if x["status"] == cm.CORROBORATED),
            "n_unresolved": sum(1 for x in out if x["status"] == cm.UNRESOLVED),
            "cases": out}


def build() -> dict:
    cal_out = calibrate()
    bp = json.loads((_DIR / "bplus_evaluation_q3.json").read_text(encoding="utf-8"))
    d = json.loads((_DIR / "matching_derivation_q3.json").read_text(encoding="utf-8"))

    corr = (corroborate_pending() if cal_out["judge_usable_boolean"]
            else {"n": 0, "n_corroborated": 0, "n_unresolved": 0, "cases": [],
                  "skipped": "judge failed calibration; pending cases not resolved with it"})

    state = "HUMAN_ANCHORED_WITH_CROSS_MODEL_AUDIT"
    unresolved = [c for c in corr.get("cases", [])
                  if c["status"] == cm.UNRESOLVED]
    disposition = {
        "bplus_status": bp["bplus_state"],
        "final_disposition": "CLOSED_WITH_UNRESOLVED_CASES_NO_FURTHER_HUMAN_ADJUDICATION",
        "means": [
            "the unresolved cases are NOT converted into matches, errors or valid themes",
            "they enter no confirmed numerator",
            "each is retained individually with its reason for uncertainty",
            "no PASS and no FAIL is declared",
        ],
        "rationale": (
            "The study chose to preserve the uncertainty rather than continue an "
            "adjudication chain incompatible with its efficiency objective. Two B+ "
            "conditions require a human and were not met; a second model's opinion "
            "cannot substitute for either."),
        "n_unresolved_retained": len(unresolved),
        "unresolved_cases": [
            {"case_id": c["case_id"], "task": c["task"], "unit_id": c.get("unit_id"),
             "reason": c["reasons"][0] if c["reasons"] else "unspecified"}
            for c in unresolved],
        "human_uncertain_rows_retained": bp["metrics"]["uncertainty_rate_human_rows"],
    }
    return {
        "final_disposition": disposition,
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": cm.CLASSIFICATION,
        "state": state,
        "provenance_of_every_number": {
            "human": ["44 human instances", "30/44 recall", "8 NO_MATCH_HUMAN_ONLY",
                      "6 UNCERTAIN", "all matched/unmatched decisions"],
            "claude_cross_model": ["calibration agreement", "corroborated categories",
                                   "unresolved cases"],
            "ai_assisted_provisional": ["granularity classifications",
                                        "machine-only provisional verdicts"],
        },
        "human_anchored_metrics": {
            "recall_vs_union_reference": bp["metrics"]["recall_vs_union_reference"],
            "strict_precision_vs_union_reference":
                bp["metrics"]["strict_precision_vs_union_reference"],
            "literal_evidence_attachment_rate":
                bp["metrics"]["literal_evidence_attachment_rate"],
            "uncertainty_rate_human_rows": bp["metrics"]["uncertainty_rate_human_rows"],
            "unconfirmed_theme_taxonomy": d["unconfirmed_theme_taxonomy"],
        },
        "judge_calibration": cal_out,
        "cross_model_audit": corr,
        "bplus_conditions_unchanged": bp["bplus_conditions"],
        "bplus_state_from_human_evidence": bp["bplus_state"],
        "claude_cannot_change_the_state": (
            "A cross-model opinion does not satisfy 'complete adjudication of every "
            "machine-only theme' or 'explicit human review of fragmentation and "
            "fusion'. Those conditions require a human, so the B+ state cannot become "
            "PASS_WITH_SAMPLED_HUMAN_VERIFICATION on the strength of this audit."),
    }


def main() -> int:
    out = build()
    _atomic(_DIR / "cross_model_analysis_q3.json", out)
    c = out["judge_calibration"]
    print("=== JUDGE CALIBRATION (14 cases, human decision withheld) ===")
    print(f"  decided        : {c['n_decided']}   agree {c['n_agree']}  "
          f"disagree {c['n_disagree']}")
    if c["exact_agreement_on_decided"] is not None:
        print(f"  exact agreement: {c['exact_agreement_on_decided']:.3f}")
    print(f"  abstain (UNCERTAIN): {c['n_abstain']}   unstable: {c['n_unstable']} "
          f"({c['instability_rate']:.1%} of all calibration cases)")
    print(f"  granularity confusions: {len(c['granularity_confusions'])} "
          f"in units {c['units_with_granularity_confusion']}")
    print(f"  JUDGE USABLE   : {c['judge_usable_for_pending_cases']}")
    print("\n  disagreement matrix:")
    for k, v in c["disagreement_matrix_decided_cases_only"].items():
        print(f"    {k}: {v}")
    a = out["cross_model_audit"]
    print(f"\n=== PENDING CASES ===")
    print(f"  corroborated : {a['n_corroborated']} / {a['n']}")
    print(f"  unresolved   : {a['n_unresolved']}")
    print(f"\nSTATE: {out['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
