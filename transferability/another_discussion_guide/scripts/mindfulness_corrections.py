"""
Corrections to the DS05 mindfulness thematic package.

Offline only. NO API calls, NO new human adjudication tasks. Reads the existing
Gemini and Claude raw outputs and re-derives the reportable quantities; the raw
outputs and the source .docx are never modified.

WHAT THIS FIXES

1. Frame strata. The frame is reported as four disjoint strata, not as a single
   "23 verified" number. Only the 21 codes stable across BOTH repetitions form
   the coverage denominator. Reporting 1/21 while calling the frame "23
   verified" mixed two different denominators.

2. The envelope. [0.048, 0.429] is renamed
   AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE. It is NOT a confidence interval,
   NOT a reliability band, and NOT a range for a true recall. Its upper end is
   an arithmetic consequence of accepting, simultaneously and without human
   adjudication, all 7 Claude-vs-Gemini disagreements plus the 1 additional
   unstable code.

3. Claude's status. The three gates verify quote literality, turn existence and
   speaker role. They do NOT verify that a quote satisfies a code's operational
   definition. Claude's 7 disagreements are therefore
   CROSS_MODEL_SEMANTIC_DISAGREEMENTS awaiting human adjudication, not
   validated presences. Gemini remains the primary evaluator.

4. Reach and salience. Speaker 2..Speaker 6 are STABLE ANONYMOUS LABELS. Counting
   distinct speakers per code needs no mapping to real identities, so reach and
   within-group salience rank ARE computable — the earlier
   NOT_RECOVERABLE verdict conflated identity mapping with speaker counting.

5. Closed-frame limits. A closed human-derived frame cannot surface a synthetic
   theme absent from it, so precision has no identifiable denominator and
   synthetic novelty was never assessed.

Usage:
    py scripts/mindfulness_corrections.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CF = _ROOT / "analysis/transportability_mindfulness/coding_frame"
_AGENTS = _ROOT / "agents/mindfulness"

# Human participant labels are anonymous but STABLE, which is all that counting
# requires. "Unknown Speaker" carries a single unattributed turn and is excluded
# from the participant denominator, matching baseline_metadata participant_count.
HUMAN_PARTICIPANTS = 5
SYNTHETIC_PARTICIPANTS = 5


def _load(name: str) -> dict:
    return json.loads((_CF / name).read_text(encoding="utf-8"))


def frame_strata(frozen: dict) -> dict:
    verified = frozen["verified_codes"]
    unverified = frozen["unverified_summary_claims"]
    stable = {c: r for c, r in verified.items() if r["agreement"] == "both"}
    unstable = {c: r for c, r in verified.items() if r["agreement"] == "one"}
    return {
        "codes_total": len(verified) + len(unverified),
        "stratum_1_any_valid_quote_in_some_repetition": {
            "n": len(verified),
            "codes": sorted(verified),
            "note": "NOT a denominator. Includes codes that were unstable across repetitions.",
        },
        "stratum_2_stable_in_both_repetitions": {
            "n": len(stable),
            "codes": sorted(stable),
            "note": "THE COVERAGE DENOMINATOR. Only these are used for coverage arithmetic.",
        },
        "stratum_3_unstable_between_repetitions": {
            "n": len(unstable),
            "codes": sorted(unstable),
            "labels": {c: r["code_label"] for c, r in unstable.items()},
            "note": "Present in one repetition only. Held UNRESOLVED, never counted as present.",
        },
        "stratum_4_excluded_no_participant_speech": {
            "n": len(unverified),
            "codes": sorted(unverified),
            "labels": {c: r["code_label"] for c, r in unverified.items()},
            "note": "UNVERIFIED_SUMMARY_CLAIM. No literal participant quote passed the gates.",
        },
        "denominator_rule": (
            "The coverage denominator is stratum 2 (n=21), NOT stratum 1 (n=23). "
            "A code that appeared in only one of two repetitions is not a stable "
            "human reference point and cannot sit in the denominator."
        ),
    }


def reach_and_salience(frozen: dict, results: dict) -> dict:
    """
    Reach needs distinct-speaker COUNTS, not speaker identities. Speaker 2..6 are
    stable anonymous labels, so this is computable on both sides.
    """
    stable = {c: r for c, r in frozen["verified_codes"].items() if r["agreement"] == "both"}

    human_rows = {}
    for cid, rec in stable.items():
        speakers = sorted({q["speaker"] for q in rec["human_supporting_quotes"]})
        human_rows[cid] = {
            "code_label": rec["code_label"],
            "parent_theme_id": rec["parent_theme_id"],
            "distinct_speakers": len(speakers),
            "speaker_labels": speakers,
            "participant_denominator": HUMAN_PARTICIPANTS,
            "reach": round(len(speakers) / HUMAN_PARTICIPANTS, 4),
        }

    # Within-group salience: dense rank on reach, highest reach = rank 1.
    ordered = sorted(human_rows.items(), key=lambda kv: (-kv[1]["reach"], kv[0]))
    distinct = sorted({v["reach"] for v in human_rows.values()}, reverse=True)
    rank_of = {r: i + 1 for i, r in enumerate(distinct)}
    for cid, row in human_rows.items():
        row["salience_rank"] = rank_of[row["reach"]]
    tiers = Counter(row["salience_rank"] for row in human_rows.values())

    # Synthetic side: only codes Gemini placed present in BOTH repetitions.
    synth_rows = {}
    per_code = results.get("per_code", {})
    for cid, info in per_code.items():
        if info.get("synthetic_agreement") != "both":
            continue
        speakers = sorted(info.get("synthetic_reach_speakers") or [])
        synth_rows[cid] = {
            "code_label": info.get("label"),
            "distinct_speakers": len(speakers),
            "speaker_labels": speakers,
            "participant_denominator": SYNTHETIC_PARTICIPANTS,
            "reach": round(len(speakers) / SYNTHETIC_PARTICIPANTS, 4),
        }

    return {
        "status": "COMPUTABLE_FROM_STABLE_ANONYMOUS_LABELS",
        "supersedes": (
            "The earlier verdict NOT_RECOVERABLE_FROM_ANONYMISED_SPEAKER_LABELS was wrong. "
            "It conflated mapping a label to a real identity — which remains impossible and is "
            "not attempted — with counting distinct speakers, which the stable labels support."
        ),
        "human": {
            "participant_denominator": HUMAN_PARTICIPANTS,
            "denominator_note": (
                "5 identified participants (Speaker 2..Speaker 6). The single 'Unknown Speaker' "
                "turn is unattributed and excluded; no verified quote originates from it."
            ),
            "codes_scored": len(human_rows),
            "mean_reach": round(sum(r["reach"] for r in human_rows.values()) / len(human_rows), 4)
            if human_rows else None,
            "salience_tiers": {f"rank_{k}": v for k, v in sorted(tiers.items())},
            "top_codes_by_reach": [
                {"code_id": c, "label": r["code_label"], "reach": r["reach"],
                 "distinct_speakers": r["distinct_speakers"]}
                for c, r in ordered[:5]
            ],
            "per_code": human_rows,
        },
        "synthetic": {
            "participant_denominator": SYNTHETIC_PARTICIPANTS,
            "codes_scored": len(synth_rows),
            "per_code": synth_rows,
            "caveat": (
                "Scored over the single code Gemini placed present in both repetitions, so this "
                "side rests on almost no observations."
            ),
        },
        "comparison_status": "EXPLORATORY_ONLY",
        "comparison_caveat": (
            "Human and synthetic reach are NOT matched participant-to-participant and no test is "
            "run between them. The synthetic side has too few scored codes for the comparison to "
            "carry weight; it is shown for completeness, not as a result."
        ),
    }


def envelope(frozen: dict, results: dict, audit: dict) -> dict:
    stable = {c for c, r in frozen["verified_codes"].items() if r["agreement"] == "both"}
    shared = {c for c, v in results["per_code"].items() if v.get("synthetic_agreement") == "both"} & stable
    disagreements = set(audit["disagreements"]) & stable
    unstable_synth = set(results.get("unresolved_codes", [])) & stable
    upper = shared | disagreements | unstable_synth
    return {
        "name": "AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE",
        "is_not": [
            "a confidence interval",
            "a reliability band",
            "a range within which a true recall lies",
            "an estimate of thematic fidelity",
        ],
        "denominator": len(stable),
        "denominator_stratum": "stratum 2 — codes stable across both repetitions",
        "lower_bound": {
            "value": round(len(shared) / len(stable), 4),
            "codes": sorted(shared),
            "derivation": "primary evaluator (Gemini) only; codes present in both repetitions on both sides",
        },
        "upper_bound": {
            "value": round(len(upper) / len(stable), 4),
            "codes": sorted(upper),
            "derivation": (
                "arithmetic consequence of accepting SIMULTANEOUSLY, and without any human "
                f"adjudication: (a) all {len(disagreements)} Claude-vs-Gemini semantic "
                f"disagreements, and (b) the {len(unstable_synth)} additional code that was "
                "unstable across the synthetic repetitions. No evidence establishes that any of "
                "these assignments is correct."
            ),
            "components": {
                "primary_shared": sorted(shared),
                "cross_model_semantic_disagreements": sorted(disagreements),
                "unstable_synthetic_code": sorted(unstable_synth),
            },
        },
        "interpretation_rule": (
            "Quote the two ends as what they are: what the primary evaluator found, and what "
            "would follow if every contested assignment were granted. The distance between them "
            "measures assignment sensitivity, not uncertainty about a fixed quantity."
        ),
    }


def closed_frame_limits() -> dict:
    return {
        "PRECISION_NOT_IDENTIFIABLE_UNDER_CLOSED_FRAME": (
            "The instrument is a closed human-derived frame: the coder is asked only whether each "
            "of 26 predefined codes is present. A synthetic passage matching no code is never "
            "surfaced, so the synthetic present-set is bounded by the frame and cannot serve as a "
            "precision denominator. The earlier precision of 1.0 was an artefact of that closure "
            "and is withdrawn."
        ),
        "F1_NOT_IDENTIFIABLE": (
            "F1 requires an identifiable precision. It is not computed and no value should be "
            "quoted."
        ),
        "SYNTHETIC_NOVELTY_NOT_ASSESSED": (
            "The earlier statement that there were no synthetic themes without a human "
            "counterpart is withdrawn. The instrument cannot detect a synthetic theme outside the "
            "frame, so an empty list is a property of the design, not a finding. Assessing "
            "novelty would require an open inductive pass, which was not run."
        ),
    }


def privacy_report() -> dict:
    """Identify, do not modify. Reported for a later authorised privacy correction."""
    findings = []
    for path in sorted(_AGENTS.glob("mf_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = ((payload.get("opening_intro") or {}).get("text") or "")
        # Two detectors of different strength, kept apart. A privacy report that
        # mixes a confirmed personal name with capitalised programme titles is
        # not actionable, so low-confidence matches are labelled as such rather
        # than asserted to be names.
        hits = []
        m = re.search(r"(?:I'?m|I am|My name is)\s+([A-Z][a-z]{2,})\b", text)
        if m:
            hits.append({
                "kind": "self_introduced_first_name",
                "value": m.group(1),
                "confidence": "high",
                "why": "the payload text introduces this as the speaker's own name",
            })
        # A full name immediately followed by a person-describing predicate.
        for first, last in re.findall(
            r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b(?=\s+is\s+(?:a|an|the)\b)", text
        ):
            hits.append({
                "kind": "personal_full_name",
                "value": f"{first} {last}",
                "confidence": "high",
                "why": "a capitalised bigram immediately predicated as a person",
            })
        if hits:
            findings.append({
                "file": f"agents/mindfulness/{path.name}",
                "field": "opening_intro.text",
                "provenance_of_field": (payload.get("field_provenance") or {}).get("opening_intro.text"),
                "anonymisation_note_present": bool(
                    (payload.get("study_context") or {}).get("anonymisation_note")
                ),
                "anonymisation_note": (payload.get("study_context") or {}).get("anonymisation_note"),
                "identifiers_found": hits,
            })
    return {
        "record_type": "PRIVACY_FINDING_IDENTIFIED_NOT_MODIFIED",
        "action_taken": "NONE — files are unmodified and no correction is applied without authorisation",
        "n_files_affected": len(findings),
        "findings": findings,
        "contradiction": (
            "Each affected payload carries an anonymisation_note asserting that the real name was "
            "withheld because the participant is identifiable from their certificate and public "
            "profile. The opening_intro.text field contradicts that note."
        ),
        "downstream_exposure": (
            "opening_intro.text is rendered into the participant system prompt and was therefore "
            "transmitted to the generation model during mindfulness_fg1_run01."
        ),
        "recommended_correction_scope": (
            "Replace the personal name inside opening_intro.text only, leaving every other field "
            "and the professional description intact; then re-run the contamination audit. This "
            "requires researcher authorisation and is NOT done here."
        ),
    }


def main() -> int:
    frozen = _load("frozen_frame.json")
    results = _load("thematic_results.json")
    audit = _load("thematic_qc_audit.json")

    strata = frame_strata(frozen)
    env = envelope(frozen, results, audit)
    reach = reach_and_salience(frozen, results)
    limits = closed_frame_limits()

    disagreements = {
        cid: {
            "code_label": a["code_label"],
            "primary_evaluator_gemini": "absent",
            "cross_model_auditor_claude": "asserted present",
            "gates_passed": ["quote_literality", "turn_id_exists", "speaker_is_participant"],
            "gates_NOT_passed": ["correspondence_with_the_operational_definition"],
            "status": "CROSS_MODEL_SEMANTIC_DISAGREEMENT",
            "resolution": "AWAITING_HUMAN_ADJUDICATION",
            "counted_as_present": False,
        }
        for cid, a in audit["disagreements"].items()
    }

    corrected = {
        "record_type": "MINDFULNESS_THEMATIC_PACKAGE_CORRECTED",
        "classification": "EXPLORATORY_OUT_OF_DOMAIN_THEMATIC_FIDELITY_CHECK",
        "no_api_calls": True,
        "no_new_human_tasks": True,
        "raw_outputs_unmodified": True,
        "primary_evaluator": "gemini (gemininext) — unchanged",
        "cross_model_auditor": (
            "claude — auditor only. Its disagreements form a sensitivity analysis and are NOT a "
            "correction to the primary result."
        ),
        "frame_strata": strata,
        "coverage": {
            "denominator": env["denominator"],
            "denominator_stratum": env["denominator_stratum"],
            "primary_evaluator_shared_codes": env["lower_bound"]["codes"],
            "primary_evaluator_coverage": env["lower_bound"]["value"],
        },
        "AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE": env,
        "cross_model_semantic_disagreements": disagreements,
        "gate_scope": {
            "what_the_gates_verify": [
                "the quote is an exact substring of the cited turn",
                "the cited turn exists",
                "the cited turn belongs to a participant, not the moderator",
            ],
            "what_the_gates_DO_NOT_verify": [
                "that the quoted passage satisfies the code's operational definition",
            ],
            "consequence": (
                "A literal, gate-passing quote is NOT automatic semantic validation. No "
                "gate-passing Claude quote is converted into a presence."
            ),
        },
        "participant_reach_and_salience": reach,
        "closed_frame_limits": limits,
        "privacy": privacy_report(),
    }

    out = _CF / "thematic_package_corrected.json"
    out.write_text(json.dumps(corrected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(_ROOT)}\n")

    s = strata
    print("FRAME STRATA")
    print(f"  total codes                          {s['codes_total']}")
    print(f"  1  any valid quote (NOT a denominator) {s['stratum_1_any_valid_quote_in_some_repetition']['n']}")
    print(f"  2  stable in both reps (DENOMINATOR)   {s['stratum_2_stable_in_both_repetitions']['n']}")
    print(f"  3  unstable between reps               {s['stratum_3_unstable_between_repetitions']['n']}")
    print(f"  4  excluded, no participant speech     {s['stratum_4_excluded_no_participant_speech']['n']}")

    print(f"\n{env['name']}")
    print(f"  denominator {env['denominator']}")
    print(f"  lower {env['lower_bound']['value']}  ({len(env['lower_bound']['codes'])} codes, Gemini only)")
    print(f"  upper {env['upper_bound']['value']}  ({len(env['upper_bound']['codes'])} codes, all contested granted)")

    print(f"\nREACH (human, denominator {reach['human']['participant_denominator']})")
    print(f"  codes scored {reach['human']['codes_scored']}   mean reach {reach['human']['mean_reach']}")
    for row in reach["human"]["top_codes_by_reach"]:
        print(f"    {row['reach']:.2f}  {row['distinct_speakers']}/5  {row['label']}")
    print(f"  salience tiers {reach['human']['salience_tiers']}")

    print(f"\nCLOSED-FRAME LIMITS")
    for k in limits:
        print(f"  {k}")

    p = corrected["privacy"]
    print(f"\nPRIVACY  {p['n_files_affected']} file(s), unmodified")
    for f in p["findings"]:
        vals = ", ".join(h["value"] for h in f["identifiers_found"])
        print(f"    {f['file']}  field={f['field']}  -> {vals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
