"""
Thematic fidelity check for DS05 mindfulness — frame verification, human vs
synthetic coding, and quality control.

    py scripts/thematic_transportability_mindfulness.py --preflight   # offline
    py scripts/thematic_transportability_mindfulness.py --verify-frame
    py scripts/thematic_transportability_mindfulness.py --evaluate
    py scripts/thematic_transportability_mindfulness.py --audit

PHASES
  A  verify-frame  Code the HUMAN transcript against the 26-code derived frame.
                   A code survives only with at least one literal, verifiable
                   human participant quote. Codes without one become
                   UNVERIFIED_SUMMARY_CLAIM and are excluded from the primary
                   reference. The surviving frame is then FROZEN and hashed.
  B  evaluate      Code the SYNTHETIC window against the frozen frame, and
                   compute presence, recall, precision, F1 and reach.
  C  audit         Blind Claude audit of: repetition disagreements, synthetic
                   codes with no human counterpart, and a sample of negatives.

The evaluator plumbing is IMPORTED from scripts/thematic_coding.py — the same
client, the same Tier-1 prompt scaffold, the same automatic literal-substring
quote verification, and the same call log
(analysis/coding_frame/gemini_calls.jsonl). Nothing is re-implemented.

Moderator turns are present in the blinded text so the coder can read context,
but a moderator quote NEVER counts as thematic evidence: the speaker gate in
_apply_gates rejects it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

_FRAME = _ROOT / "analysis/transportability_mindfulness/coding_frame/human_derived_coding_frame_v1.json"
_OUT_DIR = _ROOT / "analysis/transportability_mindfulness/coding_frame"
_MINDFULNESS = _ROOT / "data/datasets_transcripts/standardized/mindfulness/fg1"

CLASSIFICATION = "EXPLORATORY_OUT_OF_DOMAIN_THEMATIC_FIDELITY_CHECK"
EVALUATOR_KEY = "gemininext"
N_REPETITIONS = 2


# ---------------------------------------------------------------- transcripts

def human_entries() -> list[dict]:
    return json.loads((_MINDFULNESS / "transcript.json").read_text(encoding="utf-8"))


def synthetic_entries() -> list[dict]:
    from transportability_synthetic_window import _load_synthetic, _turn_to_section

    synthetic = _load_synthetic()
    turn_section = _turn_to_section()
    guide = json.loads(
        (_ROOT / "configs/experiment/mindfulness_fg1_run01.json").read_text(encoding="utf-8")
    )["discussion_guide"]
    drop = {s["section_index"] for s in guide if s["section_phase"] in {"intro", "closing"}}
    return [
        t for t in synthetic
        if turn_section.get(t["turn"]) is not None and turn_section.get(t["turn"]) not in drop
    ]


# ---------------------------------------------------------------------- frame

def load_frame() -> dict:
    return json.loads(_FRAME.read_text(encoding="utf-8"))


def frame_as_codebook(codes: list[dict]) -> list[dict]:
    """Adapt the derived frame to the {theme, subtheme_id, ...} shape thematic_coding expects."""
    return [
        {
            "theme": c["parent_theme_label"],
            "subtheme_id": c["code_id"],
            "subtheme_label": c["code_label"],
            "description": (
                f"{c['operational_definition']} "
                f"INCLUDE: {c['inclusion_criteria']} "
                f"EXCLUDE: {c['exclusion_criteria']}"
            ),
            "example": "",
        }
        for c in codes
    ]


# ------------------------------------------------------------------ the gates

def _apply_gates(result: dict, blind_text: str) -> dict:
    """
    Three gates, applied to every supporting quote:
      literalness — the quote must be an exact substring of the turn it cites;
      turn_id     — the cited turn must exist in the blinded text;
      speaker     — the cited turn must be a PARTICIPANT turn, never the moderator.
    A code counts as present only if at least one quote passes all three.
    """
    # Turns are NOT one per line: a turn's content may span several lines, so
    # splitting on newlines would truncate every multi-paragraph turn to its
    # first line and reject legitimate quotes drawn from later paragraphs.
    # Segment on the "[Tnnn] Speaker:" markers instead.
    turns: dict[str, tuple[str, str]] = {}
    markers = list(re.finditer(r"\[(T\d+)\]\s+([^:\n]+):", blind_text))
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(blind_text)
        turns[m.group(1)] = (m.group(2).strip(), blind_text[m.end():end].strip())

    gated = []
    for item in result.get("codes", result.get("subthemes", [])):
        kept, rejected = [], []
        for q in item.get("supporting_quotes") or []:
            tid = str(q.get("turn_id") or "").strip()
            quote = (q.get("quote") or "").strip()
            if tid not in turns:
                rejected.append({**q, "gate_failed": "turn_id_not_found"})
                continue
            speaker, content = turns[tid]
            if speaker.lower() == "moderator":
                rejected.append({**q, "gate_failed": "moderator_turn_not_thematic_evidence"})
                continue
            if not quote or quote not in content:
                rejected.append({**q, "gate_failed": "not_a_literal_substring"})
                continue
            kept.append({**q, "speaker": speaker})
        gated.append({
            **item,
            "verified_quotes": kept,
            "rejected_quotes": rejected,
            "present_verified": bool(kept),
        })
    return {"codes": gated}


# --------------------------------------------------------------------- calls

def _to_dict(obj):
    """Serialise a pydantic model, a dataclass or a plain object uniformly."""
    import dataclasses

    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return vars(obj)


def _code_side(entries: list[dict], codebook: list[dict], label: str) -> dict:
    from thematic_coding import EVALUATOR_CONFIGS, code_transcript_tier1, to_blind_text

    blind_text, speaker_map = to_blind_text(entries)
    cfg = dict(EVALUATOR_CONFIGS[EVALUATOR_KEY])
    result, quote_stats = code_transcript_tier1(blind_text, codebook, label, cfg)
    raw = _to_dict(result)
    gated = _apply_gates(raw, blind_text)
    return {
        "label": label,
        "speaker_map": speaker_map,
        "blind_text_sha256": hashlib.sha256(blind_text.encode("utf-8")).hexdigest(),
        "n_turns": len(re.findall(r"\[T\d+\]", blind_text)),
        "quote_validity_stats": _to_dict(quote_stats),
        "raw": raw,
        "gated": gated,
    }


# ----------------------------------------------------------------- preflight

def preflight() -> dict:
    frame = load_frame()
    codes = frame["codes"]
    human = human_entries()
    synthetic = synthetic_entries()

    from thematic_coding import to_blind_text

    human_blind, _ = to_blind_text(human)
    synth_blind, _ = to_blind_text(synthetic)

    codebook = frame_as_codebook(codes)
    frame_chars = sum(len(c["description"]) + len(c["subtheme_label"]) for c in codebook)

    def approx_tokens(chars: int) -> int:
        return chars // 4

    per_call_input = approx_tokens(frame_chars) + 400
    human_call = per_call_input + approx_tokens(len(human_blind))
    synth_call = per_call_input + approx_tokens(len(synth_blind))

    calls = {
        "phase_A_frame_verification": {
            "description": "code the HUMAN transcript against all 26 derived codes",
            "n_calls": N_REPETITIONS,
            "approx_input_tokens_each": human_call,
        },
        "phase_B_synthetic_coding": {
            "description": "code the SYNTHETIC window against the FROZEN frame",
            "n_calls": N_REPETITIONS,
            "approx_input_tokens_each": synth_call,
        },
    }
    total_gemini_calls = sum(c["n_calls"] for c in calls.values())
    total_input = sum(c["n_calls"] * c["approx_input_tokens_each"] for c in calls.values())

    return {
        "record_type": "THEMATIC_EVALUATION_PREFLIGHT",
        "classification": CLASSIFICATION,
        "frame": {
            "status": frame["status"],
            "source_sha256": frame["source_document"]["sha256"],
            "parent_themes": frame["counts"]["parent_themes"],
            "codes_total": frame["counts"]["codes"],
            "codes_verified": "PENDING — determined by phase A",
            "codes_excluded": "PENDING — codes without a literal human quote become UNVERIFIED_SUMMARY_CLAIM",
            "duplicate_labels": frame["duplicate_labels"],
        },
        "units_and_denominators": {
            "unit_of_analysis": "code x corpus (presence), and code x participant (reach)",
            "human_reference_recall": "verified-present codes in BOTH / verified-present codes in HUMAN",
            "strict_precision": "verified-present codes in BOTH / verified-present codes in SYNTHETIC",
            "f1": "computed only when both denominators are non-zero",
            "participant_reach": (
                "distinct participants with >=1 verified quote for a code / participants in that "
                "corpus — SYNTHETIC ONLY; the human side has no recoverable speaker identities "
                "(see baseline identity_reconciliation.json), so human reach is not computed"
            ),
            "salience_hierarchy": "NOT COMPUTED — human speaker mapping is not recoverable",
        },
        "evaluator": {
            "primary": EVALUATOR_KEY,
            "repetitions_per_side": N_REPETITIONS,
            "structured_output": "response_mime_type=application/json via thematic_coding Tier-1 scaffold",
            "call_log": "analysis/coding_frame/gemini_calls.jsonl",
        },
        "gates": {
            "literalness": "each quote must be an exact substring of the turn it cites",
            "turn_id": "the cited turn must exist in the blinded transcript",
            "speaker": "moderator turns are never thematic evidence for a participant code",
            "definition": "a quote counts only if it satisfies the operational definition, not the label",
        },
        "calls": calls,
        "totals": {
            "gemini_calls": total_gemini_calls,
            "approx_input_tokens": total_input,
            "approx_output_tokens": total_gemini_calls * 6000,
            "claude_audit_calls": "determined after phase B; capped at 30 and reported",
        },
        "cost": {
            "status": "NOT_CALCULATED_RATE_NOT_VERIFIED",
            "why": (
                "No published rate for gemini-3.5-flash was verified in this project; the earlier "
                "hybrid check recorded the same position. Measured token counts are reported "
                "instead of an invented cost."
            ),
        },
        "corpus": {
            "human_turns": len(re.findall(r"\[T\d+\]", human_blind)),
            "synthetic_turns": len(re.findall(r"\[T\d+\]", synth_blind)),
            "human_chars": len(human_blind),
            "synthetic_chars": len(synth_blind),
        },
        "verdict": "PASS" if codes and human and synthetic else "BLOCKED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--verify-frame", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    if args.preflight or not any((args.verify_frame, args.evaluate, args.audit)):
        pf = preflight()
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        (_OUT_DIR / "thematic_preflight.json").write_text(
            json.dumps(pf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("=" * 78)
        print("THEMATIC EVALUATION PREFLIGHT — DS05 mindfulness")
        print("=" * 78)
        print(f"\n  frame                 : {pf['frame']['status']}")
        print(f"  parent themes / codes : {pf['frame']['parent_themes']} / {pf['frame']['codes_total']}")
        print(f"  duplicate labels      : {list(pf['frame']['duplicate_labels'])}")
        print(f"\n  human turns           : {pf['corpus']['human_turns']}")
        print(f"  synthetic turns       : {pf['corpus']['synthetic_turns']}")
        print("\n  CALLS")
        for name, c in pf["calls"].items():
            print(f"    {name:32s} n={c['n_calls']}  ~{c['approx_input_tokens_each']:>7,} in-tokens each")
        print(f"\n  TOTAL Gemini calls    : {pf['totals']['gemini_calls']}")
        print(f"  approx input tokens   : {pf['totals']['approx_input_tokens']:,}")
        print(f"  approx output tokens  : {pf['totals']['approx_output_tokens']:,}")
        print(f"  Claude audit calls    : {pf['totals']['claude_audit_calls']}")
        print(f"  cost                  : {pf['cost']['status']}")
        print("\n  GATES")
        for k, v in pf["gates"].items():
            print(f"    {k:14s} {v}")
        print("\n  DENOMINATORS")
        for k, v in pf["units_and_denominators"].items():
            print(f"    {k:26s} {v}")
        print(f"\n  verdict: {pf['verdict']}")
        return 0

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = load_frame()
    codebook = frame_as_codebook(frame["codes"])

    if args.verify_frame:
        reps = [
            _code_side(human_entries(), codebook, f"ds05_human_rep{i + 1}")
            for i in range(N_REPETITIONS)
        ]
        verified, unverified = {}, {}
        for code in frame["codes"]:
            cid = code["code_id"]
            quotes, present_in = [], []
            for i, rep in enumerate(reps):
                item = next(
                    (c for c in rep["gated"]["codes"]
                     if str(c.get("subtheme_id") or c.get("code_id")) == cid),
                    None,
                )
                if item and item["present_verified"]:
                    present_in.append(i + 1)
                    quotes.extend(item["verified_quotes"])
            record = {
                "code_id": cid,
                "code_label": code["code_label"],
                "parent_theme_id": code["parent_theme_id"],
                "present_in_repetitions": present_in,
                "n_repetitions": N_REPETITIONS,
                "agreement": "both" if len(present_in) == N_REPETITIONS
                else ("one" if present_in else "neither"),
                "human_supporting_quotes": quotes,
                "source_turn_ids": sorted({q["turn_id"] for q in quotes}),
            }
            if quotes:
                record["verification_status"] = "VERIFIED_LITERAL_HUMAN_EVIDENCE"
                verified[cid] = record
            else:
                record["verification_status"] = "UNVERIFIED_SUMMARY_CLAIM"
                unverified[cid] = record

        frozen = {
            "frame_id": "HUMAN_DERIVED_RETROSPECTIVE_CODING_FRAME_V1_FROZEN",
            "status": "FROZEN_BEFORE_SYNTHETIC_EVALUATION",
            "not_a_validated_codebook": frame["not_a_validated_codebook"],
            "derived_from_sha256": frame["source_document"]["sha256"],
            "codes_total": len(frame["codes"]),
            "codes_verified": len(verified),
            "codes_unverified_excluded": len(unverified),
            "verified_codes": verified,
            "unverified_summary_claims": unverified,
            "repetition_records": reps,
        }
        blob = json.dumps(
            {k: frozen[k] for k in ("verified_codes", "unverified_summary_claims")},
            sort_keys=True, ensure_ascii=False,
        )
        frozen["frame_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        (_OUT_DIR / "frozen_frame.json").write_text(
            json.dumps(frozen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nVERIFIED   {len(verified)}/{len(frame['codes'])}")
        print(f"EXCLUDED   {len(unverified)} as UNVERIFIED_SUMMARY_CLAIM")
        print(f"frame_sha256 {frozen['frame_sha256']}")
        for cid, r in unverified.items():
            print(f"  excluded: {cid} ({r['code_label']})")
        return 0

    if args.evaluate:
        frozen = json.loads((_OUT_DIR / "frozen_frame.json").read_text(encoding="utf-8"))
        verified_ids = set(frozen["verified_codes"])
        frozen_codebook = [c for c in codebook if c["subtheme_id"] in verified_ids]

        reps = [
            _code_side(synthetic_entries(), frozen_codebook, f"ds05_synth_rep{i + 1}")
            for i in range(N_REPETITIONS)
        ]
        synth = {}
        for cid in verified_ids:
            quotes, present_in = [], []
            for i, rep in enumerate(reps):
                item = next(
                    (c for c in rep["gated"]["codes"]
                     if str(c.get("subtheme_id") or c.get("code_id")) == cid),
                    None,
                )
                if item and item["present_verified"]:
                    present_in.append(i + 1)
                    quotes.extend(item["verified_quotes"])
            synth[cid] = {
                "present_in_repetitions": present_in,
                "agreement": "both" if len(present_in) == N_REPETITIONS
                else ("one" if present_in else "neither"),
                "verified_quotes": quotes,
                "reach_speakers": sorted({q["speaker"] for q in quotes}),
            }

        # Presence counted only where BOTH repetitions agree; single-repetition
        # cases are held as UNRESOLVED rather than converted by majority.
        human_present = {c for c, r in frozen["verified_codes"].items() if r["agreement"] == "both"}
        synth_present = {c for c, r in synth.items() if r["agreement"] == "both"}
        unresolved = (
            {c for c, r in frozen["verified_codes"].items() if r["agreement"] == "one"}
            | {c for c, r in synth.items() if r["agreement"] == "one"}
        )
        both = human_present & synth_present
        recall = len(both) / len(human_present) if human_present else None
        precision = len(both) / len(synth_present) if synth_present else None
        f1 = (2 * recall * precision / (recall + precision)
              if recall and precision else None)
        n_synth_participants = len({
            q["speaker"] for r in synth.values() for q in r["verified_quotes"]
        }) or None
        reach = (
            round(sum(len(r["reach_speakers"]) for c, r in synth.items() if c in synth_present)
                  / (len(synth_present) * n_synth_participants), 4)
            if synth_present and n_synth_participants else None
        )

        results = {
            "record_type": CLASSIFICATION,
            "classification": CLASSIFICATION,
            "frame_sha256": frozen["frame_sha256"],
            "frame_frozen_before_synthetic_evaluation": True,
            "denominators": {
                "human_verified_present": len(human_present),
                "synthetic_verified_present": len(synth_present),
                "shared": len(both),
                "unresolved_single_repetition": len(unresolved),
            },
            "human_reference_recall": round(recall, 4) if recall is not None else None,
            "strict_precision": round(precision, 4) if precision is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "participant_reach_synthetic_only": reach,
            "participant_reach_human": "NOT_RECOVERABLE_FROM_ANONYMISED_SPEAKER_LABELS",
            "salience_hierarchy": "NOT_COMPUTED_HUMAN_SPEAKER_MAPPING_UNAVAILABLE",
            "human_themes_missed_by_synthetic": sorted(human_present - synth_present),
            "synthetic_themes_without_human_counterpart": sorted(synth_present - human_present),
            "unresolved_codes": sorted(unresolved),
            "per_code": {
                cid: {
                    "label": frozen["verified_codes"][cid]["code_label"],
                    "parent_theme_id": frozen["verified_codes"][cid]["parent_theme_id"],
                    "human_agreement": frozen["verified_codes"][cid]["agreement"],
                    "synthetic_agreement": synth[cid]["agreement"],
                    "synthetic_reach_speakers": synth[cid]["reach_speakers"],
                }
                for cid in sorted(verified_ids)
            },
            "repetition_records": reps,
        }
        (_OUT_DIR / "thematic_results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        d = results["denominators"]
        print(f"\nhuman present  {d['human_verified_present']}")
        print(f"synth present  {d['synthetic_verified_present']}")
        print(f"shared         {d['shared']}")
        print(f"unresolved     {d['unresolved_single_repetition']}")
        print(f"\nrecall    {results['human_reference_recall']}")
        print(f"precision {results['strict_precision']}")
        print(f"f1        {results['f1']}")
        print(f"reach(S)  {results['participant_reach_synthetic_only']}")
        print(f"\nmissed by synthetic: {results['human_themes_missed_by_synthetic']}")
        print(f"no human counterpart: {results['synthetic_themes_without_human_counterpart']}")
        return 0

    if args.audit:
        import anthropic
        from thematic_coding import to_blind_text

        results = json.loads((_OUT_DIR / "thematic_results.json").read_text(encoding="utf-8"))
        frozen = json.loads((_OUT_DIR / "frozen_frame.json").read_text(encoding="utf-8"))
        blind_text, _ = to_blind_text(synthetic_entries())

        # Audit scope, per the QC design: repetition disagreements, synthetic codes
        # with no human counterpart, and a sample of negatives. Here the negatives
        # ARE the finding under test, so all of them are audited rather than sampled.
        targets = (
            results["unresolved_codes"]
            + results["synthetic_themes_without_human_counterpart"]
            + results["human_themes_missed_by_synthetic"]
        )
        targets = list(dict.fromkeys(targets))[:30]

        client = anthropic.Anthropic()
        by_id = {c["code_id"]: c for c in frame["codes"]}
        audits = {}
        for cid in targets:
            code = by_id[cid]
            prompt = (
                "You are auditing whether a focus-group transcript contains evidence for one "
                "specific code. Be strict and default to ABSENT when uncertain.\n\n"
                f"CODE: {code['code_label']}\n"
                f"DEFINITION: {code['operational_definition']}\n"
                f"INCLUDE: {code['inclusion_criteria']}\n"
                f"EXCLUDE: {code['exclusion_criteria']}\n\n"
                "Rules: evidence must come from a PARTICIPANT turn, never the Moderator. "
                "Each quote must be an EXACT substring of the turn you cite. A turn that merely "
                "uses the label's words without the substantive claim does NOT count.\n\n"
                "Return ONLY JSON:\n"
                '{"present": true|false, "supporting_quotes": '
                '[{"turn_id": "T012", "quote": "exact substring"}], "reasoning": "one sentence"}\n\n'
                f"TRANSCRIPT:\n{blind_text}"
            )
            msg = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\{.*\}", text, re.DOTALL)
            try:
                parsed = json.loads(m.group(0)) if m else {"present": False, "supporting_quotes": []}
            except json.JSONDecodeError:
                parsed = {"present": False, "supporting_quotes": [], "reasoning": "unparseable"}
            gated = _apply_gates(
                {"codes": [{"subtheme_id": cid, **parsed}]}, blind_text
            )["codes"][0]
            gemini_said = (
                "present" if cid in results["synthetic_themes_without_human_counterpart"]
                else ("one_repetition" if cid in results["unresolved_codes"] else "absent")
            )
            audits[cid] = {
                "code_label": code["code_label"],
                "gemini_verdict": gemini_said,
                "claude_present_raw": bool(parsed.get("present")),
                "claude_present_after_gates": gated["present_verified"],
                "claude_verified_quotes": gated["verified_quotes"],
                "claude_rejected_quotes": gated["rejected_quotes"],
                "reasoning": parsed.get("reasoning"),
                "agreement": (
                    "agree" if (gated["present_verified"] == (gemini_said == "present"))
                    else "disagree"
                ),
            }

        disagreements = {k: v for k, v in audits.items() if v["agreement"] == "disagree"}
        out = {
            "record_type": "THEMATIC_QC_BLIND_CLAUDE_AUDIT",
            "classification": CLASSIFICATION,
            "auditor_model": "claude-sonnet-4-5-20250929",
            "n_calls": len(targets),
            "scope": (
                "all repetition disagreements, all synthetic codes without a human counterpart, "
                "and ALL negatives (not a sample: the negatives are the finding under test)"
            ),
            "not_a_substitute_for_the_human_frame": (
                "Claude is used only to test whether the primary evaluator's negatives survive an "
                "independent read. It does not define, extend or replace the human-derived frame, "
                "and its verdict does not override Gemini by majority."
            ),
            "n_disagreements": len(disagreements),
            "disagreements": disagreements,
            "audits": audits,
        }
        (_OUT_DIR / "thematic_qc_audit.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\naudited {len(targets)} codes")
        print(f"disagreements with the primary evaluator: {len(disagreements)}")
        for cid, a in disagreements.items():
            n = len(a["claude_verified_quotes"])
            print(f"  {cid:42s} gemini={a['gemini_verdict']:14s} claude=present ({n} verified quotes)")
        return 0

    print("choose a phase: --preflight | --verify-frame | --evaluate | --audit")
    return 1


if __name__ == "__main__":
    sys.exit(main())
