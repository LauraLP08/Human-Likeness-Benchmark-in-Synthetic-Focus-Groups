"""
Granularity audit, machine-only adjudication and the B+ state for U01-U07 / Q3.

READS ONLY. No workbook is modified and no API call is made.

WHAT THE RESEARCHER'S CLARIFICATIONS CHANGE
-------------------------------------------
Human coding asked for ONE representative quote per theme; the extractor could return
several. Number, density and coverage of quotes are therefore NEVER compared, and no
figure here derives from them. Quotes serve only to check groundedness. Correspondence is
substantive equivalence of the claim — not label equality, not quantity of evidence.

A broad human cluster linked to several machine keys may be a legitimate automatic
decomposition, not problematic fragmentation. A specific human cluster with no counterpart
may reflect automatic omission, a granularity difference, or human specificity that was
not reproduced; none of those is automatically a serious failure.

FOUR THINGS KEPT SEPARATE
-------------------------
  thematic coverage   - did the extractor reach the claim at all (recall)
  granularity         - at what grain it carved the same material
  literal evidence    - does each machine theme carry a verbatim participant quotation
                        from its own unit. An ATTACHMENT check, not a validation of the
                        claim it supports.
  quantity of evidence- how many quotes were cited. NEVER compared across sides.

THE ADJUDICATION BELOW IS `AI_ASSISTED_PROVISIONAL_ADJUDICATION`.
It is not an independent human judgement and must never be reported as one.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import emergent_calibration_q3 as cal   # noqa: E402

_DIR = cal._DIR

GRANULARITY_CLASSES = ("LEGITIMATE_GRANULARITY_DIFFERENCE", "POSSIBLE_OVER_FRAGMENTATION",
                       "POSSIBLE_OVER_MERGING", "SUBSTANTIVE_MISMATCH", "UNCERTAIN")

ADJUDICATION_CLASSIFICATION = "AI_ASSISTED_PROVISIONAL_ADJUDICATION"

# --- one human instance -> several machine themes --------------------------
ONE_TO_MANY = {
    "U01::C06": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "the human cluster states that pressure to conform is implicit and "
                 "normalised; M1 and M4 are two distinct mechanisms of exactly that "
                 "(meat as default-masculine, meat as performative safe choice). "
                 "Decomposition, not invention."),
    "U02::C10": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "the human label itself enumerates several topics (eating disorders, "
                 "portion sizes, salads); M3 and M5 pick up two of them. The human "
                 "cluster is deliberately broad."),
    "U03::C02": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "backlash for stepping outside the norm is carved into the "
                 "expectation itself (M1) and the anticipatory discomfort enforcing it "
                 "(M3)."),
    "U03::C05": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "'being a man is tied to what most men do' maps onto the same pair; "
                 "the descriptive norm (M1) and its enforcement (M3)."),
    "U03::C06": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "same broad conformity cluster as U01::C06, same two-mechanism split."),
    "U05::C06": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "one broad human cluster against three mechanisms — not caring too "
                 "much (M1), self-policing (M2), rural amplification (M3). Each is "
                 "separately evidenced in the unit."),
    "U06::C02": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                 "judgment of meat-free men (M1) and judgment as group enforcement "
                 "(M3) are two facets of the same human claim."),
    "U07::C06": ("UNCERTAIN",
                 "the human cluster is about pressure to conform to masculine "
                 "behaviour; M4 and M5 are about resistance to dietary change and "
                 "contentment with current habits. M4 touches identity-threat, which "
                 "is adjacent, but the claims are not clearly the same. Flagged, not "
                 "penalised, and the researcher's match is left untouched."),
}

# --- one machine theme <- several human instances --------------------------
MANY_TO_ONE = {
    "U01::M4": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                "'safe choice' (C01) and 'implicit normalised pressure' (C06) are "
                "close variants of one claim; one machine theme covering both is a "
                "grain difference, not a merge error."),
    "U01::M1": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                "habit/normality (C04) and implicit pressure (C06) both sit inside "
                "'meat as the default masculine choice'."),
    "U03::M3": ("POSSIBLE_OVER_MERGING",
                "FOUR distinct human clusters (C01, C02, C05, C06) collapse into one "
                "machine theme. The human coding separated safe-choice, backlash, "
                "descriptive norm and implicit pressure; the extractor kept one. "
                "Coverage is unaffected — this is a grain finding, for human review."),
    "U03::M1": ("POSSIBLE_OVER_MERGING",
                "likewise FOUR human clusters (C02, C04, C05, C06). Together with "
                "U03::M3 this makes U03 the clearest over-merging signal in the set."),
    "U05::M2": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                "self-policing subsumes both 'safe choice' (C01) and implicit "
                "pressure (C06)."),
    "U05::M1": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                "'not caring too much' covers backlash (C02) and implicit pressure "
                "(C06)."),
    "U05::M3": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                "rural amplification maps cleanly onto C12 (city vs small town); C06 "
                "is the broad cluster attaching to it as well."),
    "U06::M1": ("LEGITIMATE_GRANULARITY_DIFFERENCE",
                "judgment of meat-free men covers backlash (C02) and implicit "
                "pressure (C06)."),
    "U07::M5": ("UNCERTAIN",
                "'lack of motivation to change when satisfied' against 'safe choice' "
                "(C01) and implicit pressure (C06). The link is defensible but the "
                "claims are not evidently the same; flagged for the researcher."),
    "U07::M4": ("UNCERTAIN",
                "habits fused with identity, linked to backlash (C02), implicit "
                "pressure (C06) and health/belief-based decisions (C08). C08 in "
                "particular is a different kind of claim."),
}

# --- machine themes with no human counterpart ------------------------------
# Groundedness was verified independently: all 58 quotations are verbatim in their own
# cited turn, none from the moderator. So no theme here fails on evidence.
MACHINE_ONLY = {
    "U01::M5": ("UNCERTAIN",
                "class A: the researcher named this theme on her UNCERTAIN row "
                "U01::C02, so it is NOT absent from the human reference — she saw it "
                "and did not settle the relation. Its groundedness is not in doubt "
                "('less about gender and more what's normal in your circle', quoted "
                "verbatim); what is unsettled is the correspondence, which is hers to "
                "decide, not a novelty question."),
    "U03::M2": ("UNCERTAIN",
                "class A: named on the researcher's UNCERTAIN row U03::C09 (confirmed "
                "by MATCHING_AMENDMENT_01), so it is NOT absent from the human "
                "reference. Strongly grounded — three participant quotes across three "
                "turns that the preference/pressure distinction has collapsed — but "
                "the correspondence with her 'just eat what you crave' cluster is "
                "unsettled, and that is a human decision."),
    "U03::M4": ("VALID_NOVEL_THEME",
                "class B, pure machine-only: no human row named it. Urban anonymity "
                "removing external comment while internal pressure persists is quoted "
                "twice and is substantively distinct from every human cluster in U03."),
    "U06::M2": ("UNCERTAIN",
                "class A: named on TWO of the researcher's UNCERTAIN rows (U06::C09 "
                "and U06::C11), so it is NOT absent from the human reference. Well "
                "grounded ('it's the default, so it doesn't need justifying'); the "
                "unsettled question is which of her two clusters it corresponds to."),
    "U06::M4": ("UNCERTAIN",
                "class A: named on the researcher's UNCERTAIN row U06::C09. Grounded "
                "twice over (teasing fades when the target is unbothered), but the "
                "correspondence is unsettled and is hers to decide."),
    "U06::M5": ("VALID_NOVEL_THEME",
                "class B, pure machine-only: no human row named it. Age/maturity "
                "reducing compliance is quoted twice and is a different cause from "
                "M4's indifference, so it is not a DUPLICATE_MACHINE_THEME."),
}


def build() -> dict:
    d = json.loads((_DIR / "matching_derivation_q3.json").read_text(encoding="utf-8"))
    res = json.loads((_DIR / "extraction_results_q3.json").read_text(encoding="utf-8"))
    themes = {cal.machine_key(u["unit_id"], t["machine_theme_id"]): t
              for u in res["results"] for t in u["themes"]}

    frag = d["possible_fragmentation_one_human_many_machine"]
    fus = d["possible_fusion_one_machine_many_human"]
    unlinked = d["machine_themes_unlinked"]

    for k in frag:
        assert k in ONE_TO_MANY, f"unclassified one-to-many: {k}"
    for k in fus:
        assert k in MANY_TO_ONE, f"unclassified many-to-one: {k}"
    for k in unlinked:
        assert k in MACHINE_ONLY, f"unadjudicated machine-only theme: {k}"

    one_to_many = [{"human_key": k, "machine_keys": frag[k],
                    "classification": ONE_TO_MANY[k][0],
                    "rationale": ONE_TO_MANY[k][1]} for k in sorted(frag)]
    many_to_one = [{"machine_key": k, "human_keys": fus[k],
                    "classification": MANY_TO_ONE[k][0],
                    "rationale": MANY_TO_ONE[k][1]} for k in sorted(fus)]
    tax = d["unconfirmed_theme_taxonomy"]
    with_cand = tax["CONFIRMED_UNLINKED_WITH_HUMAN_CANDIDATE"]
    queue = [{"machine_key": k, "label": themes[k]["label"],
              "taxonomy": ("CONFIRMED_UNLINKED_WITH_HUMAN_CANDIDATE" if k in with_cand
                           else "PURE_MACHINE_ONLY"),
              "human_candidate_rows": with_cand.get(k, []),
              "description": themes[k]["one_sentence_description"],
              "model_relevance": themes[k]["relevance"],
              "model_relevance_caveat": "DESCRIPTIVE_MODEL_METADATA_NOT_HUMAN_VALIDATED",
              "n_evidence_quotes": len(themes[k]["evidence"]),
              "verdict": MACHINE_ONLY[k][0],
              "rationale": MACHINE_ONLY[k][1]} for k in unlinked]

    n_machine = d["n_machine_themes"]
    n_human = d["n_human_instances"]
    cov = d["coverage"]
    recall = cov["recall_vs_union_reference"]
    prec = cov["strict_precision_vs_union_reference"]

    verdict_counts = {v: sum(1 for q in queue if q["verdict"] == v)
                      for v in cal.MACHINE_ONLY_VERDICTS}

    unresolved = [{"human_key": r["human_key"], "reasoning": r["reasoning"],
                   "candidate_machine_keys": r["candidate_machine_keys"],
                   "invalid_keys_dropped": r["invalid_keys_dropped"]}
                  for r in d["uncertain_rows"]]
    gran_uncertain = ([x["human_key"] for x in one_to_many
                       if x["classification"] == "UNCERTAIN"] +
                      [x["machine_key"] for x in many_to_one
                       if x["classification"] == "UNCERTAIN"])

    conditions = {
        "coverage_benchmark_met": {
            "required": "recall >= 0.6364 (28/44, the lower coder recall vs the union)",
            "observed": f"{recall['numerator_matched_human_instances']}/"
                        f"{recall['denominator_human_instances']} = "
                        f"{recall['value']:.4f}",
            "met": recall["value"] >= cal.COVERAGE_BENCHMARK,
        },
        "no_recurrent_severe_unsupported_errors": {
            "required": "no severe unsupported theme recurring across >=2 units",
            "observed": f"{verdict_counts['UNSUPPORTED_OR_SPURIOUS']} unsupported "
                        f"themes in the provisional pass; all 58 quotations are "
                        f"verbatim and none is from the moderator (literal attachment, "
                        f"not substantive groundedness)",
            "met": verdict_counts["UNSUPPORTED_OR_SPURIOUS"] == 0,
        },
        "complete_adjudication_of_every_machine_only_theme": {
            "required": "a HUMAN verdict on each machine-only theme",
            "observed": f"{len(queue)} themes adjudicated, but only as "
                        f"{ADJUDICATION_CLASSIFICATION}",
            "met": False,
            "why_not": ("AI-assisted provisional adjudication is not human validation "
                        "and must not be counted as it"),
        },
        "explicit_human_review_of_fragmentation_and_fusion": {
            "required": "a human decision on each granularity case",
            "observed": f"{len(one_to_many)} one-to-many and {len(many_to_one)} "
                        f"many-to-one classified provisionally; "
                        f"{len(gran_uncertain)} remain UNCERTAIN",
            "met": False,
        },
    }
    all_met = all(c["met"] for c in conditions.values())

    state = ("PASS_WITH_SAMPLED_HUMAN_VERIFICATION" if all_met
             else "PENDING_LIMITED_REVIEW")

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": ADJUDICATION_CLASSIFICATION,
        "scope": "U01-U07 / Q3 only. Nothing here transfers to another question.",
        "four_dimensions_kept_separate": {
            "thematic_coverage": f"{recall['numerator_matched_human_instances']}/"
                                 f"{recall['denominator_human_instances']}",
            "granularity": f"{len(one_to_many)} one-to-many, {len(many_to_one)} "
                           f"many-to-one",
            "literal_evidence_attachment": ("30/30 machine themes carry at least one "
                                            "verbatim participant quotation from their "
                                            "own unit; 58/58 quotations verified"),
            "substantive_groundedness": ("NOT ESTABLISHED by that check. Literality "
                                         "shows a quote was copied correctly, not that "
                                         "the claim it supports is warranted."),
            "quantity_of_evidence": "NOT COMPARED — one human quote per theme by "
                                    "design vs several machine quotes",
        },
        "granularity_audit": {"one_to_many": one_to_many, "many_to_one": many_to_one},
        "unconfirmed_theme_taxonomy": tax,
        "machine_only_queue": queue,
        "taxonomy_note": (
            "A theme in CONFIRMED_UNLINKED_WITH_HUMAN_CANDIDATE must NEVER be described "
            "as absent from the human reference: the researcher named it while leaving "
            "the correspondence UNCERTAIN. Only PURE_MACHINE_ONLY themes have no human "
            "candidate at all, and only those are novelty questions."),
        "machine_only_verdict_counts": verdict_counts,
        "metrics": {
            "recall_vs_union_reference": recall,
            "strict_precision_vs_union_reference": prec,
            "literal_evidence_attachment_rate": {
                "numerator": n_machine, "denominator": n_machine, "value": 1.0,
                "measures": ("each machine theme carries at least one quotation that is "
                             "verbatim in its own unit and not from the moderator"),
                "does_NOT_measure": ("whether the claim is substantively warranted by "
                                     "the extract, whether it corresponds to a human "
                                     "theme, or whether a second model agrees"),
                "note": ("Renamed from grounded_theme_rate. A literal quotation is an "
                         "attachment check, not a validation of the claim.")},
            "provisional_valid_novel_themes": {
                "numerator": verdict_counts["VALID_NOVEL_THEME"],
                "denominator": n_machine,
                "value": verdict_counts["VALID_NOVEL_THEME"] / n_machine},
            "unsupported_or_spurious_rate": {
                "numerator": verdict_counts["UNSUPPORTED_OR_SPURIOUS"],
                "denominator": n_machine, "value": 0.0},
            "duplicate_machine_theme_rate": {
                "numerator": verdict_counts["DUPLICATE_MACHINE_THEME"],
                "denominator": n_machine, "value": 0.0},
            "uncertainty_rate_human_rows": {
                "numerator": len(unresolved), "denominator": n_human,
                "value": len(unresolved) / n_human},
            "fusion_confirmed": {"numerator": len(many_to_one),
                                 "denominator": n_machine},
            "fragmentation_confirmed": {"numerator": len(one_to_many),
                                        "denominator": n_human},
        },
        "bplus_conditions": conditions,
        "bplus_state": state,
        "state_rationale": (
            "Recall clears the benchmark and no unsupported theme was found, but a PASS "
            "requires all four conditions. Two are outstanding and both need a human, "
            "not a model: the machine-only verdicts here are "
            f"{ADJUDICATION_CLASSIFICATION}, and the granularity cases have not been "
            "reviewed by the researcher. Recall alone does not produce a PASS."),
        "escalate_to_researcher": {
            "note": ("The only items that genuinely need her. No new workbook, and no "
                     "re-reading of the 44 rows."),
            "unresolved_uncertain_rows": unresolved,
            "granularity_cases_still_uncertain": gran_uncertain,
        },
    }


def main() -> int:
    out = build()
    dst = _DIR / "bplus_evaluation_q3.json"
    tmp = dst.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    m = out["metrics"]
    print("B+ STATE:", out["bplus_state"])
    for k, c in out["bplus_conditions"].items():
        print(f"  [{'MET' if c['met'] else '   '}] {k}")
        print(f"        {c['observed']}")
    print()
    print("machine-only verdicts:", out["machine_only_verdict_counts"])
    print("granularity          :",
          f"{len(out['granularity_audit']['one_to_many'])} one-to-many, "
          f"{len(out['granularity_audit']['many_to_one'])} many-to-one")
    print("uncertain human rows :", m["uncertainty_rate_human_rows"]["numerator"])
    print(f"wrote {dst.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
