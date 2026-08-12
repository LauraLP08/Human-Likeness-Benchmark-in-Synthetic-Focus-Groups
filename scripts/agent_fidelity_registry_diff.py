"""
Proposed metric-registry changes for Level 3 agent fidelity.

    py scripts/agent_fidelity_registry_diff.py

Writes a PROPOSAL and a DIFF. It never touches `metric_registry.csv`, which stays frozen
until the diff is approved.

Offline. No API call.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_FROZEN = _ROOT / "analysis/production_evaluation/metric_registry.csv"
_OUT = _ROOT / "analysis/production_evaluation/agent_fidelity"

# metric_id -> proposed evidence_class and the reason it changes.
PROPOSED = {
    "lexical_identity_continuity": {
        "tier": "Tier 3", "category": "exploratory",
        "evidence_class": "EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC",
        "unit_of_analysis": "focus group",
        "definition": (
            "LEAVE_ONE_QUESTION_OUT_SPEAKER_IDENTIFICATION: whether a participant's "
            "held-out answer is matched to their own profile, built from their other "
            "questions only, against the profiles of eligible fellow participants in "
            "the same session"),
        "numerator": "correctly identified held-out cells",
        "denominator": "eligible held-out cells",
        "aggregation": ("per document -> per focus group; the three synthetic "
                        "replicates are reported separately and never pooled"),
        "notes_and_caveats": (
            "NEW. Reported with the chance baseline 1/n_eligible_participants and with "
            "chance-corrected accuracy, because the eligible set varies by fold. "
            "Character n-gram TF-IDF fitted on the training fold only. Text is "
            "equalised at 50 words per participant x question, one deterministic "
            "window, offsets never repeated. Says nothing about psychological or "
            "biographical continuity and is not human-validated."),
    },
    "between_speaker_lexical_differentiation": {
        "tier": "Tier 3", "category": "exploratory",
        "evidence_class": "EXPLORATORY_AUTOMATIC_LEXICAL_DIAGNOSTIC",
        "unit_of_analysis": "focus group",
        "definition": ("BETWEEN_SPEAKER_LEXICAL_DIFFERENTIATION_DIAGNOSTICS: how much "
                       "participants within one session resemble each other lexically, "
                       "measured within a question so topic is common to both speakers"),
        "numerator": "-", "denominator": "participant pairs within a question",
        "aggregation": "per document -> per focus group; replicates separate",
        "notes_and_caveats": (
            "RENAMED from the earlier lexical-distinctiveness diagnostics (Jaccard, "
            "Jensen-Shannon, cosine), which are retained unchanged under this name. "
            "Measures how alike the members of a session are; it does NOT measure "
            "whether one participant keeps a recognisable voice across questions. Lower "
            "overlap is not evidence of an individual identity."),
    },
    "numeral_density": {
        "tier": "Tier 3", "category": "descriptive",
        "evidence_class": "DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS",
        "unit_of_analysis": "focus group",
        "definition": "count of numeric expressions per 1,000 participant words",
        "numerator": "numeric expression matches", "denominator": "participant words",
        "aggregation": "per run -> per FG x condition",
        "notes_and_caveats": (
            "RECLASSIFIED. Withdrawn as a measure of hyper-exactness and retained only "
            "as a descriptive proxy. It counts how many figures appear, not how they "
            "are used, and a LOWER numeral density must never be read as less "
            "hyper-exactness. In this corpus only 50 of 1,301 participant turns contain "
            "any digit while 567 contain a spelled-out number, so a digit-based count "
            "does not even track how often quantities are stated."),
    },
    "hyper_exactness": {
        "tier": "Tier 3", "category": "interpretive",
        "evidence_class": "LLM_ASSISTED_EXPLORATORY_CONTEXTUAL_AUDIT",
        "unit_of_analysis": "turn",
        "definition": ("blinded contextual classification of detector-proposed "
                       "candidates into ORDINARY_EVERYDAY_SPECIFICITY, "
                       "PLAUSIBLE_PERSONAL_RECALL, HYPER_EXACT_STATISTICAL_CLAIM, "
                       "IMPLAUSIBLY_PRECISE_EPISODIC_RECALL or UNCERTAIN"),
        "numerator": "turns classified into a hyper-exact category",
        "denominator": "participant turns audited",
        "aggregation": ("per 1,000 words and proportion of participants affected; per "
                        "FG x condition"),
        "notes_and_caveats": (
            "EXECUTED. No corroborated hyper-exactness case among 127 audited turns of "
            "1,301: a DETECTED_LOWER_BOUND_RATE, not evidence of absence, and the 1,174 "
            "unaudited turns are not negative. 121/127 corroborated, 6 unresolved, "
            "exact agreement 0.9528. The "
            "offline detector PROPOSES "
            "candidates and classifies nothing. The audit is blinded to condition, "
            "focus group, human/synthetic status, model and agent profiles. Candidates "
            "not audited are reported as NOT_AUDITED, never as negative."),
    },
    "input_profile_adherence": {
        "tier": "Tier 3", "category": "exploratory",
        "evidence_class": "SYNTHETIC_ONLY_EXPLORATORY",
        "unit_of_analysis": "participant",
        "definition": ("whether explicit attributes of a synthetic agent's input profile "
                       "appear in a compatible way in that agent's speech"),
        "numerator": "profile attributes expressed compatibly",
        "denominator": "explicit profile attributes",
        "aggregation": "per participant -> per document -> per FG; replicates separate",
        "notes_and_caveats": (
            "NEW. SYNTHETIC CONDITIONS ONLY and NOT comparable with humans: no "
            "equivalent input sheet exists for a human participant, so a human value "
            "would be undefined rather than zero. Must never be aggregated with "
            "lexical_identity_continuity into a single continuity score."),
    },
    "expressed_position_continuity": {
        "tier": "Tier 3", "category": "interpretive",
        "evidence_class": "LLM_ASSISTED_EXPLORATORY",
        "unit_of_analysis": "participant",
        "definition": ("continuity of a participant's expressed positions across guide "
                       "questions, judged contextually"),
        "numerator": "-", "denominator": "participants audited",
        "aggregation": "per participant -> per document; replicates separate",
        "notes_and_caveats": (
            "NEW. Requires contextual interpretation and is exploratory. Distinct from "
            "lexical_identity_continuity: a recognisable style is not a maintained "
            "position."),
    },
    "profile_consistency": {
        "tier": "Tier 3", "category": "interpretive",
        "evidence_class": "LLM_ASSISTED_EXPLORATORY",
        "unit_of_analysis": "statement pair",
        "definition": ("absence of unexplained contradiction between two statements by "
                       "the same participant, classified as CONSISTENT, "
                       "POSITION_CHANGED_WITH_EXPLANATION, "
                       "CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY, "
                       "UNEXPLAINED_CONTRADICTION or UNCERTAIN"),
        "numerator": "pairs classified UNEXPLAINED_CONTRADICTION",
        "denominator": "statement pairs audited",
        "aggregation": "per participant -> per document -> per FG; replicates separate",
        "notes_and_caveats": (
            "EXECUTED AS A PILOT ONLY, gate passed, full audit DECLINED_AFTER_PILOT: "
            "the screener was not demonstrated to enrich for contradictions. 120 of "
            "2,611 screened pairs adjudicated; 100 corroborated, 20 unresolved, 2 "
            "CROSS_REPETITION_CORROBORATED_CANDIDATE_CONTRADICTION, both in the control "
            "stratum. No corpus-wide rate; the 2,491 unaudited pairs are not negative. "
            "Two repetitions of one auditor measure auditor stability, not independent "
            "validation. SUPERSEDES profile_consistency_group, which was group level "
            "only. "
            "Screening may use vocabulary overlap, embeddings or NLI to PROPOSE pairs; "
            "none of them may dictate a verdict. A random control sample of pairs the "
            "screener did not propose is audited so false negatives can be estimated. "
            "Reported as LLM_ASSISTED_EXPLORATORY_PROFILE_CONSISTENCY_AUDIT and never "
            "as validated profile consistency."),
    },
}

# Metrics that may be PROPOSED NOW: their evidence exists and is offline.
PROPOSABLE_NOW = ("lexical_identity_continuity",
                  "between_speaker_lexical_differentiation", "numeral_density",
                  "hyper_exactness", "profile_consistency")

# Metrics whose class cannot be settled until their audit runs AND passes its gate.
# Listing a class for them now would be describing evidence that does not exist.
PENDING_AUDIT = {
    "input_profile_adherence": "not executed; optional expansion",
    "expressed_position_continuity": "not executed; optional expansion",
}

# Frozen rows these would eventually replace. The replacement is NOT applied yet: a
# superseded row would leave the registry with no live entry for the indicator while the
# replacement is still unaudited.
SUPERSEDED = {
    "profile_continuity_group": "split into lexical_identity_continuity, "
                                "input_profile_adherence and "
                                "expressed_position_continuity",
    "profile_consistency_group": "superseded by participant-level profile_consistency",
}


def build() -> dict:
    frozen = {r["metric_id"]: r for r in csv.DictReader(
        _FROZEN.open(encoding="utf-8"))}
    changes = []
    for mid, prop in PROPOSED.items():
        cur = frozen.get(mid)
        if mid in PENDING_AUDIT:
            changes.append({"metric_id": mid, "change": "PROPOSED_PENDING_AUDIT",
                            "from_evidence_class": cur["evidence_class"]
                            if cur else None,
                            "to_evidence_class": "PENDING_AUDIT",
                            "eventual_evidence_class_if_gate_passes":
                                prop["evidence_class"],
                            "reason": PENDING_AUDIT[mid]})
            continue
        if cur is None:
            changes.append({"metric_id": mid, "change": "ADD",
                            "from_evidence_class": None,
                            "to_evidence_class": prop["evidence_class"],
                            "reason": prop["notes_and_caveats"].split(".")[0]})
        elif cur["evidence_class"] != prop["evidence_class"]:
            changes.append({"metric_id": mid, "change": "RECLASSIFY",
                            "from_evidence_class": cur["evidence_class"],
                            "to_evidence_class": prop["evidence_class"],
                            "reason": prop["notes_and_caveats"].split(".")[0]})
        else:
            changes.append({"metric_id": mid, "change": "UNCHANGED_CLASS",
                            "from_evidence_class": cur["evidence_class"],
                            "to_evidence_class": prop["evidence_class"],
                            "reason": "definition and caveats updated only"})
    for mid, why in SUPERSEDED.items():
        changes.append({"metric_id": mid, "change": "PROPOSED_PENDING_AUDIT",
                        "from_evidence_class": frozen[mid]["evidence_class"]
                        if mid in frozen else None,
                        "to_evidence_class": "PROPOSED_PENDING_AUDIT",
                        "eventual_evidence_class_if_gate_passes": "SUPERSEDED",
                        "reason": why + " - not superseded yet: the replacement is "
                                        "still unaudited, and retiring the frozen row "
                                        "now would leave the indicator with no live "
                                        "entry"})
    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "AGENT_FIDELITY_REGISTRY_DIFF",
        "status": "PROPOSAL_AWAITING_APPROVAL",
        "frozen_registry_untouched": True,
        "frozen_registry": str(_FROZEN.relative_to(_ROOT)).replace("\\", "/"),
        "n_frozen_metrics": len(frozen),
        "changes": changes,
        "n_add": sum(1 for c in changes if c["change"] == "ADD"),
        "n_reclassify": sum(1 for c in changes if c["change"] == "RECLASSIFY"),
        "n_pending_audit": sum(1 for c in changes
                              if c["change"] == "PROPOSED_PENDING_AUDIT"),
        "proposable_now": list(PROPOSABLE_NOW),
        "pending_audit": PENDING_AUDIT,
        "nothing_is_superseded_yet": True,
        "two_coder_scope_note": (
            "The two-coder exercise partially validates THEMATIC EXTRACTION in Q3. It "
            "is not human validation of stylometry, hyper-exactness, continuity or "
            "contradiction, and must not be cited as such for any metric above."),
        "proposed_rows": PROPOSED,
    }


def write(o: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "metric_registry_diff_proposal.json").write_text(
        json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")
    cols = ["metric_id", "tier", "category", "evidence_class", "unit_of_analysis",
            "definition", "numerator", "denominator", "aggregation",
            "notes_and_caveats"]
    with (_OUT / "metric_registry_proposed_rows.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for mid, r in o["proposed_rows"].items():
            w.writerow({"metric_id": mid,
                        **{k: v for k, v in r.items() if k in cols}})


def main() -> int:
    o = build()
    write(o)
    print(f"frozen registry metrics: {o['n_frozen_metrics']}   "
          f"(untouched: {o['frozen_registry_untouched']})")
    print(f"{'metric_id':40s} {'change':16s} from -> to")
    for c in o["changes"]:
        print(f"  {c['metric_id']:38s} {c['change']:16s} "
              f"{c['from_evidence_class']} -> {c['to_evidence_class']}")
    print(f"\nADD {o['n_add']}   RECLASSIFY {o['n_reclassify']}   "
          f"PROPOSED_PENDING_AUDIT {o['n_pending_audit']}")
    print(f"proposable now: {o['proposable_now']}")
    print("STATUS: PROPOSAL_AWAITING_APPROVAL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
