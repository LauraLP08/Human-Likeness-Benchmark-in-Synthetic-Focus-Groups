"""
Frozen adjudication rules for the blinded cross-model absence audit.

Every rule here is fixed BEFORE any request is submitted, and every one is exercised
offline against synthetic fixtures in tests/test_absence_audit.py. No API call.

WHAT "REPETITION" MEANS HERE
----------------------------
The auditor runs each request twice. These are **two separately keyed stochastic
repetitions of an independent cross-model auditor** — not two independent auditors.

`claude-opus-5` is independent of Gemini, which produced the original coding; that is
the cross-model independence this design claims. Its two repetitions share a model, a
prompt, a schema and a rendering. They differ only in a repetition index carried in the
cache key, so they resample the same model's stochasticity. Agreement between them
measures the STABILITY of one auditor, never the concurrence of two.

ORDER OF OPERATIONS — cannot be rearranged
------------------------------------------
    1. LOCAL EVIDENCE GATE   applied to each repetition separately, before the
                             repetitions are compared. A verdict whose quotation cannot
                             be located in the named turn of that document is downgraded,
                             not discarded and not repaired.
    2. REPETITION RULE       the two gated repetitions are reconciled. Disagreement is
                             recorded as unresolved; it is never settled by preferring
                             the more confident, the more detailed, or the later one.
    3. CROSS-MODEL RULE      the reconciled auditor verdict is set against the original
                             coder's decision. The auditor never overwrites it.

A corroborated absence is not proof of absolute absence. It means one independent
cross-model auditor, resampled twice, also found nothing under the same definition. That
is the strongest claim the design supports.
"""
from __future__ import annotations

import math
import re
import unicodedata

# ------------------------------------------------------------- vocabulary
GATE_PASS = "EVIDENCE_LOCALISED"
GATE_NO_QUOTE = "UNCERTAIN_NO_QUOTATION_SUPPLIED"
GATE_NO_TURN = "UNCERTAIN_TURN_NOT_FOUND"
GATE_NOT_IN_TURN = "UNCERTAIN_QUOTATION_NOT_IN_NAMED_TURN"
GATE_SPEAKER_MISMATCH = "UNCERTAIN_SPEAKER_MISMATCH"
GATE_MODERATOR = "UNCERTAIN_EVIDENCE_ATTRIBUTED_TO_MODERATOR"

# Reconciled auditor verdicts
AUD_EVIDENCE = "AUDITOR_EVIDENCE_FOUND"
AUD_NONE = "AUDITOR_DID_NOT_FIND_EVIDENCE"
AUD_UNRESOLVED = "AUDITOR_UNRESOLVED"

# Cross-model outcomes for an absence decision
ABSENCE_CORROBORATED = "ABSENCE_CORROBORATED"
ABSENCE_CONTESTED = "ABSENCE_CONTESTED"
ABSENCE_UNRESOLVED = "ABSENCE_UNRESOLVED"

# Cross-model outcomes for an originally-present cell (the concurrence control)
PRESENCE_CONCURRED = "PRESENCE_CONCURRED"
PRESENCE_NOT_CONCURRED = "PRESENCE_NOT_CONCURRED"
PRESENCE_UNRESOLVED = "PRESENCE_UNRESOLVED"

# Calibration cell labels. Neither is ground truth, and neither is called "reference".
ORIGINAL_PRESENT = "ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED"
ORIGINAL_ABSENCE = "ORIGINAL_GEMINI_ABSENCE"

# Stage-1 gate outcomes
GATE_A = "PROCEED_WITH_ABSENCE_CORROBORATION"
GATE_B = "PROCEED_DETECTION_ONLY"
GATE_C = "STOP_AUDITOR_UNUSABLE"


# ---------------------------------------------------------- Wilson interval
#
# WHAT THESE INTERVALS ARE, AND ARE NOT
# -------------------------------------
# The Wilson intervals in this audit are OPERATIONAL GATE SUMMARIES. They convert a
# count into a decision band and nothing more. They are NOT confirmatory confidence
# intervals and must never be reported as inferential statistics about the auditor's
# accuracy.
#
# The binomial assumption they rest on does not hold here. The 63 positive-control cells
# are clustered within 14 documents, and the 11 assessments produced for one document
# arrive in a single response: they share a context, a rendering and a generation, so
# they are dependent. Clustered, dependent observations make a binomial interval
# anticonservative — the true interval is wider than the one printed. The figures are
# used only to place a count into band A, B or C, a purpose that tolerates the
# approximation because the thresholds are stipulated in advance rather than estimated
# from the data.
#
WILSON_CAVEAT = (
    "operational gate summary, not a confirmatory confidence interval: the 63 "
    "positive-control cells are clustered within 14 documents and the 11 assessments in "
    "one response are dependent, so this binomial interval is anticonservative and the "
    "true interval is wider; it is used only to place a count into a decision band "
    "against thresholds stipulated in advance")


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    """
    Wilson score interval. Returns nulls rather than a spurious 0-1 when n == 0.

    See WILSON_CAVEAT: an operational gate summary, not a confirmatory interval.
    """
    if n <= 0:
        return {"k": k, "n": n, "point": None, "lower": None, "upper": None, "z": z}
    if k < 0 or k > n:
        raise ValueError(f"k={k} outside 0..n={n}")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {"k": k, "n": n, "point": round(p, 4),
            "lower": round(max(0.0, centre - half), 4),
            "upper": round(min(1.0, centre + half), 4), "z": z}


def min_k_for_lower_bound(n: int, target: float, z: float = 1.96) -> int | None:
    """Smallest k out of n whose Wilson lower bound reaches `target`. None if impossible."""
    if n <= 0:
        return None
    for k in range(n + 1):
        if wilson(k, n, z)["lower"] >= target:
            return k
    return None


# ------------------------------------------------------------ Stage-1 gate
#
# PROSPECTIVE. Fixed before Stage 1 is submitted. No universal 0.80 convention is used;
# each threshold is stated with the claim it licenses and the reason it sits where it does.
#
# THRESHOLD_A = 1/1.20. The audit estimates how many of the 260 absences are contestable.
# If the auditor detects a fraction s of the evidence that is demonstrably locatable, an
# observed count C of contested cells implies roughly C/s contestable absences. Fixing a
# tolerance that this inflation may not exceed 20% gives a required detection rate of
# 1/1.20 = 0.8333 on the lower bound. The 20% tolerance is a stipulated choice, declared
# here in advance; the threshold follows from it arithmetically.
#
# THRESHOLD_B = 0.50 is a property of the instrument, not of any cell. Below a detection
# rate of one half, the auditor fails to detect more known-localisable positive controls
# than it detects. An instrument in that state produces non-detections carrying too
# little information to support a corroboration claim of any kind.
#
# NO CLAIM IS MADE about any particular non-detection. This audit cannot rank a given
# AUDITOR_DID_NOT_FIND_EVIDENCE as more probably an auditor failure than a true absence:
# that would require knowing how many absences are genuinely contestable, which is the
# unknown the audit exists to bound and cannot assume. The threshold governs whether the
# instrument may license a corroboration label at all, never the status of one cell.
#
# Detections are unaffected by a low detection rate: a gate-passed quotation is verified
# against the transcript itself, so it remains valid however insensitive the auditor is.
# That asymmetry is what band B exploits.
#
THRESHOLD_A = round(1 / 1.20, 4)      # 0.8333
THRESHOLD_B = 0.50
MAX_UNRESOLVED_UPPER_A = 0.20

# The gate is evaluated on EVERY originally-present quote-verified cell returned by the
# Stage-1 documents, not on the 11 designated present cases. With n = 11 a flawless 11/11
# yields a Wilson lower bound of only 0.7412, so a gate stated on the designated set alone
# could not be passed at THRESHOLD_A by any performance whatsoever. The designated cases
# guarantee balanced subtheme coverage; they are not the denominator.
GATE_DENOMINATOR_RULE = ("all originally-present quote-verified cells returned by the "
                         "Stage-1 documents; the 22 designated cases guarantee subtheme "
                         "coverage and are reported separately, never as the denominator")


def stage1_gate(n_detected: int, n_original_present: int,
                n_agree: int, n_cells: int,
                n_unresolved: int, z: float = 1.96) -> dict:
    """
    Three prospectively defined outcomes.

      A  PROCEED_WITH_ABSENCE_CORROBORATION
         detection lower bound >= THRESHOLD_A AND stability lower bound >= THRESHOLD_A
         AND unresolved upper bound <= MAX_UNRESOLVED_UPPER_A.
         The report may state ABSENCE_CORROBORATED, printing the residual miss rate.

      B  PROCEED_DETECTION_ONLY
         both lower bounds >= THRESHOLD_B but band A not met.
         Only AUDITOR_DID_NOT_FIND_EVIDENCE may be used. The words "corroborated",
         "confirmed" and "validated" are not available for absences, and no absence
         claim is strengthened. Contested cells stand, because a gate-passed quotation
         is verified against the transcript rather than against the auditor.

      C  STOP_AUDITOR_UNUSABLE
         either lower bound < THRESHOLD_B.
         Stage 2 is not submitted. The calibration failure is itself the reported result
         and no absence figure is revised.

    Band A is NECESSARY BUT NOT SUFFICIENT for ABSENCE_CORROBORATED. The subtheme-level
    eligibility rule in subtheme_control_eligibility() must also be satisfied for the
    subtheme in question. See absence_label().
    """
    det = wilson(n_detected, n_original_present, z)
    stab = wilson(n_agree, n_cells, z)
    unres = wilson(n_unresolved, n_cells, z)

    if det["lower"] is None or stab["lower"] is None:
        return {"outcome": GATE_C, "reasons": ["empty calibration denominator"],
                "detection_rate": det, "repetition_stability": stab,
                "unresolved_rate": unres}

    reasons, fails = [], []
    if det["lower"] < THRESHOLD_B:
        fails.append(f"detection lower bound {det['lower']} < {THRESHOLD_B}")
    if stab["lower"] < THRESHOLD_B:
        fails.append(f"stability lower bound {stab['lower']} < {THRESHOLD_B}")
    if fails:
        return {"outcome": GATE_C, "reasons": fails, "detection_rate": det,
                "repetition_stability": stab, "unresolved_rate": unres,
                "consequence": ("Stage 2 is not submitted; the calibration failure is "
                                "the reported result and no absence figure is revised")}

    if det["lower"] < THRESHOLD_A:
        reasons.append(f"detection lower bound {det['lower']} < {THRESHOLD_A}")
    if stab["lower"] < THRESHOLD_A:
        reasons.append(f"stability lower bound {stab['lower']} < {THRESHOLD_A}")
    if unres["upper"] > MAX_UNRESOLVED_UPPER_A:
        reasons.append(f"unresolved upper bound {unres['upper']} "
                       f"> {MAX_UNRESOLVED_UPPER_A}")
    if reasons:
        return {"outcome": GATE_B, "reasons": reasons, "detection_rate": det,
                "repetition_stability": stab, "unresolved_rate": unres,
                "permitted_label": AUD_NONE,
                "forbidden_labels": [ABSENCE_CORROBORATED],
                "consequence": ("absences may be reported only as "
                                f"{AUD_NONE}; contested cells stand because a "
                                "gate-passed quotation is verified against the "
                                "transcript, not against the auditor")}

    return {"outcome": GATE_A, "reasons": [], "detection_rate": det,
            "repetition_stability": stab, "unresolved_rate": unres,
            "permitted_label": ABSENCE_CORROBORATED,
            "residual_miss_rate_upper": round(1 - det["lower"], 4),
            "consequence": ("ABSENCE_CORROBORATED may be used, printed alongside the "
                            "residual miss rate")}


# --------------------------------------------------- 1. local evidence gate
def _normalise(s: str) -> str:
    """
    Whitespace, case and typographic normalisation only. This tolerates the substitutions
    a model makes when copying (curly to straight quotes, em dash to hyphen) without
    tolerating paraphrase: no word is added, removed or reordered, and no stemming runs.
    """
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-")
          .replace("…", "..."))
    return re.sub(r"\s+", " ", s).strip().lower()


def evidence_gate(assessment: dict, turns: dict) -> dict:
    """
    `turns` maps turn_id -> list of {"speaker", "text", "is_moderator"} for THIS document.

    A quotation is localised only if, after normalisation, it is a contiguous substring
    of an utterance in the named turn of THIS document. Finding it in some other turn
    does not pass: the auditor was required to name the turn, and a quotation that is
    real but misattributed is exactly the failure the gate exists to catch.

    On failure the verdict is downgraded to UNCERTAIN and NO speaker is emitted, so gate
    failures can never contribute to a reach bound.
    """
    verdict = assessment.get("verdict")
    if verdict != "EVIDENCE_FOUND":
        return {"gate": None, "verdict_after_gate": verdict, "downgraded": False,
                "speaker": None, "reason": "gate applies to EVIDENCE_FOUND only"}

    quote = (assessment.get("quotation") or "").strip()
    tid = (assessment.get("turn_id") or "").strip()
    spk = (assessment.get("speaker") or "").strip()

    def fail(code):
        return {"gate": code, "verdict_after_gate": "UNCERTAIN", "downgraded": True,
                "speaker": None, "reason": code}

    if not quote:
        return fail(GATE_NO_QUOTE)
    if tid not in turns:
        return fail(GATE_NO_TURN)

    nq = _normalise(quote)
    hit = next((u for u in turns[tid] if nq and nq in _normalise(u["text"])), None)
    if hit is None:
        return fail(GATE_NOT_IN_TURN)
    if hit["is_moderator"] or _normalise(spk) == "moderator":
        return fail(GATE_MODERATOR)
    if spk and _normalise(spk) != _normalise(hit["speaker"]):
        return fail(GATE_SPEAKER_MISMATCH)

    return {"gate": GATE_PASS, "verdict_after_gate": "EVIDENCE_FOUND",
            "downgraded": False, "speaker": hit["speaker"], "reason": None}


# ------------------------------------------------------- 2. repetition rule
def reconcile_repetitions(gated_verdicts) -> dict:
    """
    Two separately keyed stochastic repetitions of the same auditor, reconciled by
    agreement only.

        both EVIDENCE_FOUND      -> AUDITOR_EVIDENCE_FOUND
        both NO_EVIDENCE_FOUND   -> AUDITOR_DID_NOT_FIND_EVIDENCE
        anything else            -> AUDITOR_UNRESOLVED

    A disagreement is never resolved by confidence, by quotation length, by which
    repetition ran later, or by a third tie-breaking call. Instability between
    repetitions is a finding about the auditor, not noise to be averaged away.
    """
    vs = list(gated_verdicts)
    if len(vs) != 2:
        return {"verdict": AUD_UNRESOLVED, "agreement": False,
                "reason": f"expected 2 repetitions, received {len(vs)}"}
    if vs[0] == vs[1] == "EVIDENCE_FOUND":
        return {"verdict": AUD_EVIDENCE, "agreement": True, "reason": None}
    if vs[0] == vs[1] == "NO_EVIDENCE_FOUND":
        return {"verdict": AUD_NONE, "agreement": True, "reason": None}
    if vs[0] == vs[1] == "UNCERTAIN":
        return {"verdict": AUD_UNRESOLVED, "agreement": True,
                "reason": "both repetitions UNCERTAIN"}
    return {"verdict": AUD_UNRESOLVED, "agreement": False,
            "reason": f"repetitions disagree: {vs[0]} vs {vs[1]}"}


# ------------------------------------------------------ 3. cross-model rule
def cross_model_outcome(original_present: bool, auditor_verdict: str) -> str:
    """
    The original coder's decision is the reference and is never overwritten. This
    classifies the relationship between the two codings, nothing more.
    """
    if not original_present:
        return {AUD_NONE: ABSENCE_CORROBORATED,
                AUD_EVIDENCE: ABSENCE_CONTESTED}.get(auditor_verdict,
                                                     ABSENCE_UNRESOLVED)
    return {AUD_EVIDENCE: PRESENCE_CONCURRED,
            AUD_NONE: PRESENCE_NOT_CONCURRED}.get(auditor_verdict,
                                                  PRESENCE_UNRESOLVED)


# ------------------------------------------- 4. subtheme eligibility rule
#
# A global pass says the auditor works ACROSS the codebook. It does not say the auditor
# can recognise any PARTICULAR subtheme. An auditor could reach band A while being blind
# to one definition — and every absence for that definition would then be corroborated by
# an instrument demonstrably unable to detect it.
#
# So corroboration is gated twice. An ORIGINAL_GEMINI_ABSENCE may be labelled
# ABSENCE_CORROBORATED only if BOTH hold:
#
#   1. the global gate reaches band A; and
#   2. the auditor detected the designated ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED control
#      for that same subtheme, under the reconciled two-repetition rule.
#
# If a subtheme's designated control is not detected, or is unresolved, every
# non-detection for that subtheme stays AUDITOR_DID_NOT_FIND_EVIDENCE even under a global
# band A.
#
# Contested cells are untouched. A gate-passed quotation is verified against the
# transcript, so a valid contested absence remains contestable however the control for
# its subtheme behaved.
#
ELIGIBLE = "SUBTHEME_CONTROL_DETECTED"
INELIGIBLE_NOT_DETECTED = "SUBTHEME_CONTROL_NOT_DETECTED"
INELIGIBLE_UNRESOLVED = "SUBTHEME_CONTROL_UNRESOLVED"
INELIGIBLE_MISSING = "SUBTHEME_CONTROL_MISSING"


def subtheme_control_eligibility(control_verdicts, subthemes=None) -> dict:
    """
    `control_verdicts` maps subtheme_id -> the reconciled auditor verdict on that
    subtheme's designated positive control. `subthemes` is the full codebook; any
    subtheme without a returned control is ineligible rather than silently absent.
    """
    keys = sorted(set(subthemes) if subthemes is not None else control_verdicts)
    out = {}
    for s in keys:
        v = control_verdicts.get(s)
        if v == AUD_EVIDENCE:
            status, eligible = ELIGIBLE, True
        elif v == AUD_NONE:
            status, eligible = INELIGIBLE_NOT_DETECTED, False
        elif v == AUD_UNRESOLVED:
            status, eligible = INELIGIBLE_UNRESOLVED, False
        else:
            status, eligible = INELIGIBLE_MISSING, False
        out[s] = {"subtheme_id": s, "control_verdict": v,
                  "status": status, "eligible_for_corroboration": eligible}
    return out


def absence_label(global_gate_outcome: str, subtheme_id: str,
                  auditor_verdict: str, eligibility: dict) -> dict:
    """
    The final label for one ORIGINAL_GEMINI_ABSENCE cell.

    Corroboration requires the global band A AND this subtheme's control. Everything
    else that would have been corroborated falls back to the neutral
    AUDITOR_DID_NOT_FIND_EVIDENCE, which asserts only what the auditor reported.
    """
    if auditor_verdict == AUD_EVIDENCE:
        return {"label": ABSENCE_CONTESTED, "downgraded": False,
                "reason": ("evidence gate passed in both repetitions; a contested "
                           "absence is verified against the transcript and is "
                           "unaffected by the subtheme eligibility rule")}
    if auditor_verdict == AUD_UNRESOLVED:
        return {"label": ABSENCE_UNRESOLVED, "downgraded": False, "reason": None}

    if auditor_verdict != AUD_NONE:
        raise ValueError(f"unknown auditor verdict {auditor_verdict!r}")

    e = eligibility.get(subtheme_id, {"eligible_for_corroboration": False,
                                      "status": INELIGIBLE_MISSING})
    if global_gate_outcome != GATE_A:
        return {"label": AUD_NONE, "downgraded": True,
                "reason": f"global gate is {global_gate_outcome}, not {GATE_A}"}
    if not e["eligible_for_corroboration"]:
        return {"label": AUD_NONE, "downgraded": True,
                "reason": (f"global gate reached {GATE_A} but the designated positive "
                           f"control for {subtheme_id} was not detected: {e['status']}")}
    return {"label": ABSENCE_CORROBORATED, "downgraded": False, "reason": None}


# ------------------------------------------------------ calibration scoring
def calibration_scores(cells) -> dict:
    """
    `cells` is an iterable of {"original_status", "auditor_verdict"} where
    original_status is ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED or ORIGINAL_GEMINI_ABSENCE.

    Neither label is ground truth. The originally-present cells carry a quotation the
    original coder localised and that was verified verbatim, which makes them a usable
    positive control. The originally-absent cells carry no such warrant: they are the
    original coder's decisions and are the very thing under audit.

    Reported as counts and Wilson intervals with denominators printed, never as one
    accuracy figure: the two directions have different consequences and only one of them
    can be scored against anything.
    """
    n_pos = n_neg = 0
    detected = missed = unres_pos = 0
    concurs_abs = contests_abs = unres_neg = 0
    for c in cells:
        ref, v = c["original_status"], c["auditor_verdict"]
        if ref == ORIGINAL_PRESENT:
            n_pos += 1
            detected += v == AUD_EVIDENCE
            missed += v == AUD_NONE
            unres_pos += v == AUD_UNRESOLVED
        elif ref == ORIGINAL_ABSENCE:
            n_neg += 1
            concurs_abs += v == AUD_NONE
            contests_abs += v == AUD_EVIDENCE
            unres_neg += v == AUD_UNRESOLVED
        else:
            raise ValueError(f"unknown original_status {ref!r}")

    return {
        "n_original_present_quote_verified": n_pos,
        "n_original_gemini_absence": n_neg,
        "detected_on_original_present": detected,
        "missed_on_original_present": missed,
        "unresolved_on_original_present": unres_pos,
        "concurs_on_original_absence": concurs_abs,
        "contests_original_absence": contests_abs,
        "unresolved_on_original_absence": unres_neg,
        "detection_rate_on_original_present": wilson(detected, n_pos),
        "concurrence_rate_on_original_absence": wilson(concurs_abs, n_neg),
        "denominators_printed": True,
        "single_accuracy_figure": None,
        "interpretation": (
            "The detection rate on originally-present quote-verified cells is the only "
            "quantity scored against an external warrant, and it bounds how much this "
            "auditor can be trusted when it reports finding nothing. The concurrence "
            "rate on ORIGINAL_GEMINI_ABSENCE cells is NOT a specificity and NOT a "
            "ground-truth accuracy: those cells are the original coder's decisions, so "
            "a contested cell may be an original omission rather than an auditor error, "
            "which is the question the audit exists to ask and cannot assume away."),
    }


# ------------------------------------------------- speaker evidence handling
def speaker_evidence(rep1_gated, rep2_gated) -> dict:
    """
    FROZEN speaker handling for a single contested cell.

    Each argument is that repetition's gate result. A speaker is admitted only from a
    gate result whose outcome is GATE_PASS; a downgraded, failed or unresolved
    assessment contributes no speaker at all, in either direction.

      union         deduplicated across both repetitions -> feeds UPPER
      intersection  recorded separately, never used as a bound
    """
    def admit(g):
        if not g or g.get("gate") != GATE_PASS:
            return set()
        return {g["speaker"]} if g.get("speaker") else set()

    s1, s2 = admit(rep1_gated), admit(rep2_gated)
    return {"union": sorted(s1 | s2), "intersection": sorted(s1 & s2),
            "n_union": len(s1 | s2), "n_intersection": len(s1 & s2),
            "rule": ("union of speakers supported by evidence-gated quotations across "
                     "both repetitions, deduplicated; failed or unresolved evidence "
                     "contributes no speaker")}


# ------------------------------------------- sensitivity output 1: breadth
def participant_breadth_bounds(contested_cells, participants_n_by_doc) -> dict:
    """
    Bounds on the participant-breadth hierarchy. Contested absences are NOT converted
    into presences; the hierarchy is recomputed under three explicit treatments.

      LOWER  original coding unchanged; every contested cell stays 0. PRIMARY — the
             reported result does not move.
      MID    1/n for the document. Exactly one participant is warranted by the design,
             since a contested cell requires a localised quotation.
      UPPER  |union of gate-passed speakers across both repetitions| / n.
             Equals MID when both repetitions cite the same speaker.

    UNRESOLVED cells enter no bound. Each cell also carries its speaker intersection,
    recorded for transparency and never used as a bound.
    """
    per_doc, rows = {}, []
    for c in contested_cells:
        n = participants_n_by_doc.get(c["doc_key"])
        if n is None or n <= 0:
            raise ValueError(f"non-positive participant denominator for {c['doc_key']}")
        union = sorted(set(c.get("union_speakers") or []))
        inter = sorted(set(c.get("intersection_speakers") or []))
        if not union:
            raise ValueError(
                f"contested cell {c['doc_key']}/{c['subtheme_id']} has no gate-passed "
                "speaker; a contested cell requires a localised quotation in both "
                "repetitions")
        if not set(inter) <= set(union):
            raise ValueError("intersection is not a subset of union")
        row = {"doc_key": c["doc_key"], "subtheme_id": c["subtheme_id"],
               "lower_reach": 0.0, "mid_reach": 1 / n, "upper_reach": len(union) / n,
               "n_participants": n, "union_speakers": union,
               "intersection_speakers": inter,
               "n_union": len(union), "n_intersection": len(inter)}
        if row["upper_reach"] < row["mid_reach"]:
            raise ValueError("UPPER below MID is impossible")
        rows.append(row)
        per_doc.setdefault(c["doc_key"], []).append(row)

    return {"output": "participant_breadth_bounds",
            "treatments": ["LOWER", "MID", "UPPER"], "primary": "LOWER",
            "primary_note": "the reported hierarchy is LOWER and is unchanged",
            "unresolved_enter_any_bound": False,
            "intersection_is_a_bound": False,
            "rows": rows, "per_document": per_doc,
            "n_contested_cells": len(rows)}


# ---------------------------------------- sensitivity output 2: recurrence
def across_group_recurrence_sensitivity(presence_rows, contested_keys) -> dict:
    """
    Across-group recurrence is a COUNT OF FOCUS GROUPS, not a reach, so it takes a
    different sensitivity from participant breadth and is reported separately.

      ORIGINAL             the coding as it stands
      CONTESTED_AS_PRESENT every contested absence flipped to present

    `presence_rows` are dicts with condition, canonical_replication_index, fg,
    subtheme_id, doc_key, present. `contested_keys` is a set of (doc_key, subtheme_id).

    Only these two treatments exist here. There is no MID: a focus group either counts
    or does not, and there is no fractional group.
    """
    contested = set(contested_keys)
    orig, flip = {}, {}
    for r in presence_rows:
        key = (r["condition"], r.get("canonical_replication_index"), r["subtheme_id"])
        p = bool(r["present"])
        q = p or ((r["doc_key"], r["subtheme_id"]) in contested)
        orig.setdefault(key, set())
        flip.setdefault(key, set())
        if p:
            orig[key].add(r["fg"])
        if q:
            flip[key].add(r["fg"])

    rows = []
    for key in sorted(orig, key=lambda k: (str(k[0]), str(k[1]), str(k[2]))):
        o, f = len(orig[key]), len(flip[key])
        rows.append({"condition": key[0], "canonical_replication_index": key[1],
                     "subtheme_id": key[2], "n_fgs_original": o,
                     "n_fgs_contested_as_present": f, "delta": f - o})
    return {"output": "across_group_recurrence_sensitivity",
            "treatments": ["ORIGINAL", "CONTESTED_AS_PRESENT"], "primary": "ORIGINAL",
            "no_mid_treatment": "a focus group either counts or does not",
            "unresolved_enter_any_treatment": False,
            "rows": rows, "n_changed": sum(1 for r in rows if r["delta"])}
