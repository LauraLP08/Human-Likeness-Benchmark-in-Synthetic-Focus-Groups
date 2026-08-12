"""
Phases 5 and 6 recomputed over the COMPLETE 93-pair correspondence universe.

The earlier version of this module derived recall and precision from the 61 screened
pairs, which treated a similarity heuristic's exclusions as adjudications. It did not.
Everything here now sources from hybrid_universe.json, where every within-unit human x
machine pair has an explicit status.

Never pooled with U01-U07/Q3; the Q3 figures are a descriptive landmark only.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy   # noqa: E402
import hybrid_round2 as r2             # noqa: E402
import hybrid_complement as hc         # noqa: E402
import hybrid_universe as hu           # noqa: E402

_HY = hy._HY
QUESTIONS = ["Q1", "Q2", "Q4", "Q5"]
PRE_COMPLEMENT_CLASSIFICATION = {
    "value": "DESCRIPTIVELY_COMPATIBLE_WITH_Q3",
    "status": "PROVISIONAL_SUPERSEDED — based on 61/93 screened pairs",
    "why_superseded": (
        "computed before the 32 omitted pairs were adjudicated, so its recall band and "
        "its claim of zero unresolved human themes rested on unjudged pairs"),
    "retained_as": "historical record; never cite it as a current figure",
}


def _L(n):
    return json.loads((_HY / n).read_text(encoding="utf-8"))


def _rate(n, d):
    return None if not d else round(n / d, 4)


def _block(H, M, hstate, mstate, machine_only):
    """Recall and precision for a set of human and machine keys."""
    rec = [k for k in H if hstate[k]["state"] == "RECOVERED"]
    pend = [k for k in H if hstate[k]["state"] == "UNRESOLVED_POSSIBLY_RECOVERED"]
    notrec = [k for k in H if hstate[k]["state"] == "CONFIRMED_NOT_RECOVERED"]
    mm = [k for k in M if mstate[k]["state"] == "MATCHED"]
    mpend = [k for k in M if mstate[k]["state"] == "UNRESOLVED_POSSIBLY_MATCHED"]
    munm = [k for k in M if mstate[k]["state"] == "CONFIRMED_UNMATCHED"]
    novel = [x["machine_key"] for x in machine_only
             if x["machine_key"] in M and x["status"] == hy.HYBRID_CORROBORATED_NOVEL]
    lo, hi = _rate(len(rec), len(H)), _rate(len(rec) + len(pend), len(H))
    return {
        "n_human_themes": len(H), "n_machine_themes": len(M),
        "confirmed_recall_lower_bound": lo, "possible_recall_upper_bound": hi,
        "recall_band_width": round((hi or 0) - (lo or 0), 4),
        "n_recovered": len(rec), "n_unresolved_possibly_recovered": len(pend),
        "n_confirmed_not_recovered": len(notrec),
        "strict_confirmed_precision": _rate(len(mm), len(M)),
        "possible_precision_upper_bound": _rate(len(mm) + len(mpend), len(M)),
        "precision_band_width": round((_rate(len(mm) + len(mpend), len(M)) or 0)
                                      - (_rate(len(mm), len(M)) or 0), 4),
        "exploratory_adjusted_precision_including_corroborated_novelty":
            _rate(len(mm) + len(novel), len(M)),
        "n_machine_matched": len(mm),
        "n_machine_unresolved_possibly_matched": len(mpend),
        "n_machine_confirmed_unmatched": len(munm),
        "n_corroborated_novel": len(novel),
    }


def build() -> dict:
    uni = _L("hybrid_universe.json")
    if not uni["pass"]:
        raise RuntimeError(f"universe did not pass integrity: {uni['problems']}")
    old = _L("hybrid_matching_derivation.json")   # round-2 outcomes, unchanged
    machine_only, granularity = old["machine_only"], old["granularity"]
    cands = _L("hybrid_candidates.json")
    ext = _L("gemini_extraction_results.json")

    hstate, mstate = uni["human_state"], uni["machine_state"]
    HK = {u: [h["key"] for h in cands["humans"].get(u, [])] for u in hy.UNITS}
    MK = {u: [m["key"] for m in cands["machines"].get(u, [])] for u in hy.UNITS}

    per_unit = {u: {"question_id": hy.QUESTION_OF[u],
                    **_block(HK[u], MK[u], hstate, mstate, machine_only)}
                for u in hy.UNITS}
    per_q = {}
    for q in QUESTIONS:
        us = [u for u in hy.UNITS if hy.QUESTION_OF[u] == q]
        per_q[q] = {"units": us,
                    **_block([k for u in us for k in HK[u]],
                             [k for u in us for k in MK[u]],
                             hstate, mstate, machine_only)}
    overall = {"scope": "the six supplementary units only — never pooled with U01-U07/Q3",
               **_block([k for u in hy.UNITS for k in HK[u]],
                        [k for u in hy.UNITS for k in MK[u]],
                        hstate, mstate, machine_only)}
    overall["human_themes_confirmed_not_recovered"] = sorted(
        k for k, v in hstate.items() if v["state"] == "CONFIRMED_NOT_RECOVERED")
    overall["machine_themes_unresolved_possibly_matched"] = sorted(
        k for k, v in mstate.items() if v["state"] == "UNRESOLVED_POSSIBLY_MATCHED")

    # A candidate can be corroborated-novel (task C, judged against the unit's whole
    # reference inventory) while still holding an unsettled pairwise correspondence.
    # Those are different questions and the tension is reported, not resolved by fiat.
    novel_keys = {x["machine_key"] for x in machine_only
                  if x["status"] == hy.HYBRID_CORROBORATED_NOVEL}
    both = sorted(novel_keys & set(overall["machine_themes_unresolved_possibly_matched"]))

    # --- evidence ----------------------------------------------------------
    n_themes = sum(r["n_themes"] for r in ext["results"])
    attached = sum(1 for r in ext["results"] for t in r["themes"] if t.get("evidence"))
    evidence = {
        "literal_evidence_attachment_rate": {
            "numerator": attached, "denominator": n_themes,
            "value": _rate(attached, n_themes),
            "measures": ("each Gemini theme carries >=1 quotation verbatim in its own "
                         "unit and not from the moderator"),
            "does_NOT_measure": ("NOT substantive groundedness; verifies literal "
                                 "evidence attachment only.")},
        "n_quotations_verified": sum(r["n_quotes"] for r in ext["results"]),
        "n_units_quarantined": sum(1 for r in ext["results"]
                                   if r["status"] != "COMPLETE")}

    # --- frozen rule, applied unchanged to the corrected figures ------------
    n_h = overall["n_human_themes"]
    unres_share = overall["n_unresolved_possibly_recovered"] / n_h
    mean_band = statistics.mean(v["recall_band_width"] for v in per_q.values())
    below = sum(1 for v in per_q.values()
                if v["possible_recall_upper_bound"] < hy.Q3_REFERENCE["recall"])
    reaches = all(v["possible_recall_upper_bound"] >= hy.Q3_REFERENCE["recall"]
                  for v in per_q.values())
    unsupported_units = {x["blind_unit_id"] for x in machine_only
                         if x["status"] == "HYBRID_CORROBORATED_UNSUPPORTED_OR_SPURIOUS"}
    if unres_share > 0.40 or mean_band > 0.35:
        frozen, why = ("UNRESOLVED_DUE_TO_HYBRID_UNCERTAINTY",
                       f"unresolved share {unres_share:.3f}, mean recall band "
                       f"{mean_band:.3f}")
    elif below >= 3:
        frozen, why = ("DESCRIPTIVELY_LOWER_THAN_Q3",
                       f"{below} of 4 questions have an upper bound below "
                       f"{hy.Q3_REFERENCE['recall']}")
    elif reaches and len(unsupported_units) < 2:
        frozen, why = ("DESCRIPTIVELY_COMPATIBLE_WITH_Q3",
                       "every question's recall band reaches "
                       f"{hy.Q3_REFERENCE['recall']} and no unsupported theme recurs "
                       "in >=2 units")
    else:
        frozen, why = ("MIXED_OUTSIDE_Q3_PERFORMANCE",
                       "neither uniformly compatible nor uniformly lower")

    prec_gap = hy.Q3_REFERENCE["strict_precision"] - overall["strict_confirmed_precision"]
    balanced = {
        "statement": (
            "Recall-compatible with Q3 under the frozen rule, but with lower strict "
            "precision and greater thematic proliferation; evidence of transportability "
            "is mixed across fidelity dimensions."
            if frozen == "DESCRIPTIVELY_COMPATIBLE_WITH_Q3" and prec_gap > 0.05
            else f"Frozen rule returned {frozen}; see the dimensions below."),
        "dimensions_weighed": {
            "recall_outside_q3": [overall["confirmed_recall_lower_bound"],
                                  overall["possible_recall_upper_bound"]],
            "strict_precision_outside_q3": overall["strict_confirmed_precision"],
            "precision_band_outside_q3": [overall["strict_confirmed_precision"],
                                          overall["possible_precision_upper_bound"]],
            "q3_descriptive_reference": hy.Q3_REFERENCE,
            "strict_precision_gap_vs_q3": round(prec_gap, 4),
            "thematic_proliferation": {
                "n_machine_themes_per_human_theme": round(
                    overall["n_machine_themes"] / overall["n_human_themes"], 3),
                "n_corroborated_novel": overall["n_corroborated_novel"]},
            "n_unresolved_pairs": sum(1 for r in uni["rows"]
                                      if r["status"] == hy.HYBRID_UNRESOLVED),
            "n_small_and_single_coder": (
                "6 units, 18 human themes, one coder, no second human adjudicator; a "
                "single reclassification moves any rate here visibly")},
        "forbidden_language": ["transportability established", "validated", "equivalent"],
        "why_two_conclusions": (
            "the frozen rule keys on recall only and was fixed before any result "
            "existed, so it is reported unmodified. It is not a summary of overall "
            "fidelity, and reporting it alone would overstate the finding."),
    }

    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": hy.CLASSIFICATION,
        "derived_from": "hybrid_universe.json — the complete 93-pair universe",
        "never_pooled_with_q3": True, "no_pass_fail": True,
        "no_statistical_test_between_questions": True,
        "correspondence_space": {
            "n_pairs": uni["n_pairs"], "n_historical": uni["n_historical"],
            "n_complement": uni["n_complement"], "complete": True},
        "per_unit": per_unit, "per_question": per_q,
        "overall_within_check": overall,
        "evidence": evidence,
        "pair_status_counts": Counter(r["status"] for r in uni["rows"]),
        "pair_status_by_source": {
            s: dict(Counter(r["status"] for r in uni["rows"] if r["source_round"] == s))
            for s in (hc.SOURCE_ORIGINAL, hc.SOURCE_COMPLEMENT)},
        "human_theme_states": dict(Counter(v["state"] for v in hstate.values())),
        "machine_theme_states": dict(Counter(v["state"] for v in mstate.values())),
        "machine_only": {"counts": dict(Counter(x["status"] for x in machine_only)),
                         "cases": machine_only,
                         "corroborated_novel_but_pairwise_unresolved": both,
                         "note": ("task C asks whether a candidate is a distinct valid "
                                  "theme given the whole reference inventory; the "
                                  "pairwise task asks whether it corresponds to one "
                                  "specific reference theme. A candidate can be settled "
                                  "on the first and open on the second. Novelty is "
                                  "never converted into a human correspondence.")},
        "granularity": {
            "counts": dict(Counter(f"{x['status']}|{x['category']}"
                                   for x in granularity)),
            "cases": granularity,
            "re_derived_from_the_93_pair_universe": True,
            "n_new_cases_created_by_the_complement": 0,
            "why_none": ("all 19 confirmed matches come from the original 61 pairs, so "
                         "the fragmentation and fusion multiplicities are unchanged and "
                         "the three corroborated cases remain the complete derived set")},
        "unresolved_pairs": [r for r in uni["rows"]
                             if r["status"] == hy.HYBRID_UNRESOLVED],
        "pre_complement_classification": PRE_COMPLEMENT_CLASSIFICATION,
        "FROZEN_RULE_CLASSIFICATION": {
            "value": frozen, "reason": why,
            "rule": hy.FINAL_RULE,
            "rule_unmodified": ("the rule keys on recall only and was frozen before any "
                                "result existed; it was NOT retrofitted to include "
                                "precision")},
        "BALANCED_INTERPRETATION": balanced,
        "q3_reference_descriptive_only": hy.Q3_REFERENCE,
        "n_caveat": hy.FINAL_RULE["n_caveat"],
    }
    hy._atomic(_HY / "hybrid_metrics.json", out)
    hy._atomic(_HY / "hybrid_matching_derivation.json", {
        "derived_from": "the complete 93-pair universe",
        "universe": {"n_pairs": uni["n_pairs"], "n_historical": uni["n_historical"],
                     "n_complement": uni["n_complement"], "rows": uni["rows"]},
        "human_state": hstate, "machine_state": mstate,
        "machine_only": machine_only, "granularity": granularity,
        "confirmed_by_human": {k: v["confirmed_matches"] for k, v in hstate.items()
                               if v["confirmed_matches"]},
        "confirmed_by_machine": {k: v["confirmed_matches"] for k, v in mstate.items()
                                 if v["confirmed_matches"]}})
    return out


def main() -> int:
    o = build()
    c = o["correspondence_space"]
    print(f"universe {c['n_pairs']} pairs = {c['n_historical']} historical + "
          f"{c['n_complement']} complement\n")
    for s, d in o["pair_status_by_source"].items():
        print(f"  {s}: {d}")
    print("\nhuman theme states :", o["human_theme_states"])
    print("machine states     :", o["machine_theme_states"])
    print("\n=== per question ===")
    print(f"{'Q':4s} {'nH':>3s} {'nM':>3s} {'rec lo':>7s} {'rec hi':>7s} {'band':>6s} "
          f"{'prec lo':>8s} {'prec hi':>8s} {'band':>6s}")
    for q, v in o["per_question"].items():
        print(f"{q:4s} {v['n_human_themes']:>3d} {v['n_machine_themes']:>3d} "
              f"{v['confirmed_recall_lower_bound']:>7.4f} "
              f"{v['possible_recall_upper_bound']:>7.4f} "
              f"{v['recall_band_width']:>6.3f} "
              f"{v['strict_confirmed_precision']:>8.4f} "
              f"{v['possible_precision_upper_bound']:>8.4f} "
              f"{v['precision_band_width']:>6.3f}")
    v = o["overall_within_check"]
    print(f"\noverall  recall [{v['confirmed_recall_lower_bound']:.4f}, "
          f"{v['possible_recall_upper_bound']:.4f}]   precision "
          f"[{v['strict_confirmed_precision']:.4f}, "
          f"{v['possible_precision_upper_bound']:.4f}]   adjusted "
          f"{v['exploratory_adjusted_precision_including_corroborated_novelty']:.4f}")
    print("\npre-complement :", o["pre_complement_classification"]["value"],
          "->", o["pre_complement_classification"]["status"])
    print("FROZEN RULE    :", o["FROZEN_RULE_CLASSIFICATION"]["value"])
    print("                ", o["FROZEN_RULE_CLASSIFICATION"]["reason"])
    print("\nBALANCED       :", o["BALANCED_INTERPRETATION"]["statement"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
