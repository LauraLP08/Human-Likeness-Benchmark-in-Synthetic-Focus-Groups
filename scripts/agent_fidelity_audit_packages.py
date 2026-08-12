"""
Blinded audit packages for hyper-exactness and profile consistency.

    py scripts/agent_fidelity_audit_packages.py

BUILDS INVENTORIES AND REQUEST MANIFESTS ONLY. It makes no API call and never assigns a
category to anything. Both detectors PROPOSE candidates; the classification is contextual
and belongs to a blinded audit that has not been authorised.

WHY A DETECTOR CANNOT BE THE MEASURE
------------------------------------
Numeral density counts how many figures appear, not how they are used. "I went about
three times" and "I go 3.2 times a week on average" are both numerals and only one is
hyper-exact. Density is therefore retained as
NUMERAL_DENSITY_DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS and cannot discharge the indicator.
A lower numeral density does not mean less hyper-exactness.

BLINDING
--------
Every item carries an opaque item id and the quote with minimal surrounding context.
Condition, focus group, replicate, human/synthetic status, model and agent profiles are
sealed away from the request payload and kept in a separate reference file, exactly as
the cross-model absence audit did.

Offline. No API call.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import defaultdict
from datetime import datetime, UTC
from itertools import combinations
from pathlib import Path

import agent_fidelity_corpus as afc

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "analysis/production_evaluation/agent_fidelity"

# Measured token model for this project: tokens = 1.7502 * words + 1620 (R2 0.9989).
TOK_SLOPE, TOK_INTERCEPT = 1.7502, 1620
CLAUDE_BATCH_IN, CLAUDE_BATCH_OUT = 2.50, 12.50      # USD / MTok, verified 2026-08-02
GEMINI_COST = "NOT_CALCULATED_RATE_NOT_VERIFIED"

SEED = 20260803          # fixed; the control sample must be reproducible

HYPER_EXACT_CATEGORIES = ("ORDINARY_EVERYDAY_SPECIFICITY", "PLAUSIBLE_PERSONAL_RECALL",
                          "HYPER_EXACT_STATISTICAL_CLAIM",
                          "IMPLAUSIBLY_PRECISE_EPISODIC_RECALL", "UNCERTAIN")
CONSISTENCY_CATEGORIES = ("CONSISTENT", "POSITION_CHANGED_WITH_EXPLANATION",
                          "CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY",
                          "UNEXPLAINED_CONTRADICTION", "UNCERTAIN")

# Numbers in this corpus are overwhelmingly SPOKEN, not written: only 50 of 1,301
# participant turns contain any digit, while 567 contain a spelled-out number. A
# digit-only detector would therefore miss almost everything it is meant to propose, so
# every quantity pattern below accepts both forms.
_N = (r"(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
      r"twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
      r"thousand|dozen|half|quarter|couple)")
_UNIT = (r"(?:g|kg|ml|l|litres?|grams?|kilos?|calories|kcal|miles?|km|metres?|"
         r"minutes?|mins?|hours?|quid|pounds?|pence|dollars?|euros?|portions?|servings?)")

# Candidate patterns. Each only PROPOSES; none classifies.
#
# "exactly" and "precisely" are deliberately NOT standalone triggers. In this corpus
# "exactly" occurs 162 times and is almost always an intensifier - "not exactly the
# healthiest", "tasted exactly like beef" - which has nothing to do with implausible
# precision. Used alone it swamped the inventory with false positives and buried the
# numeric candidates. It now fires only when a quantity follows it.
PATTERNS = {
    "PERCENTAGE_OR_DECIMAL": re.compile(
        rf"\b{_N}\s*(?:%|per\s?cent|percent)\b|\b\d+\.\d+\b", re.I),
    "EXACT_DATE_OR_TIME": re.compile(
        r"\b(?:\d{1,2}[:.]\d{2}\s*(?:am|pm)?|\d{1,2}(?:st|nd|rd|th)\s+of\s+\w+"
        r"|(?:19|20)\d{2})\b", re.I),
    "STATISTICAL_FIGURE": re.compile(
        rf"\b(?:average|median|percent|percentage|statistic\w*|survey|study|studies|"
        rf"research|data)\b[^.?!]{{0,60}}?\b{_N}\b", re.I),
    "SPECIFIC_QUANTITY_OR_PRICE": re.compile(
        rf"[£$€]\s?\d+(?:[.,]\d+)?|\b{_N}\s*(?:{_UNIT})\b", re.I),
    "SPECIFIC_FREQUENCY_OR_DURATION": re.compile(
        rf"\b{_N}\s*(?:times?|days?|weeks?|months?|years?)\s*(?:a|per|every)\s*"
        rf"(?:day|week|month|year)\b", re.I),
    # "to the minute/second/penny" is unambiguously a precision idiom. "to the day" and
    # "to the pound" are not - "start to the day", "listen to the pound" - so those two
    # need an explicit intensifier before they count.
    "PRECISE_EPISODIC_MARKER": re.compile(
        rf"\b(?:to\s+the\s+(?:minute|second|penny)"
        rf"|(?:right|down)\s+to\s+the\s+(?:day|pound)"
        rf"|on the dot|(?:exactly|precisely)\s+{_N})\b", re.I),
}

# Detector families where an implausibly precise claim would be most consequential if
# present. Used only to prioritise if the full volume is not authorised.
SEVERE_FAMILIES = ("STATISTICAL_FIGURE", "PERCENTAGE_OR_DECIMAL", "EXACT_DATE_OR_TIME",
                   "PRECISE_EPISODIC_MARKER")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _turns():
    """
    Participant turns inside the validated Q1-Q5 sections, with the turn id and the
    speaker's stable label. Names are scrubbed; provenance is kept OUT of the payload and
    returned separately for the sealed reference.
    """
    rost = afc.roster()
    pats = {d: afc._name_pattern(v.values()) for d, v in rost.items()}
    labels = {d: {sid: f"{d}#S{i + 1:02d}" for i, sid in enumerate(sorted(rost[d]))}
              for d in rost}
    out = []
    for seg in afc.segments():
        d = afc.doc_id(seg)
        chosen, _ = afc._slice(seg)
        for e in chosen:
            sid, is_mod = afc._speaker(e)
            if is_mod:
                continue
            clean, _ = afc.scrub(e["content"], pats[d])
            out.append({
                "doc_id": d, "question": int(seg["question"]),
                "turn": int(e["turn"]), "participant": labels[d][sid],
                "text": clean, "n_words": len(clean.split()),
                # provenance - sealed, never in a payload
                "_condition": seg["condition"], "_fg": seg["fg"],
                "_replicate": seg["canonical_replication_index"]})
    return out


# ------------------------------------------------------------ E hyper-exactness
def hyper_exact_candidates(turns):
    cands = []
    for t in turns:
        hits = defaultdict(list)
        for name, pat in PATTERNS.items():
            for m in pat.finditer(t["text"]):
                hits[name].append(m.group(0).strip())
        if not hits:
            continue
        item = _sha(f"hx|{t['doc_id']}|{t['question']}|{t['turn']}")[:16].upper()
        cands.append({
            "item_id": f"HX-{item}",
            "detectors_fired": sorted(hits),
            "matched_strings": sorted({s for v in hits.values() for s in v}),
            "n_detectors": len(hits),
            "turn_id": f"T{t['turn']:03d}",
            "speaker": t["participant"].split("#")[-1],
            "quote": t["text"],
            "n_words": t["n_words"],
            "_stratum": "DETECTOR_PROPOSED_CANDIDATE",
            "_doc_id": t["doc_id"], "_question": t["question"],
            "_condition": t["_condition"], "_fg": t["_fg"],
            "_replicate": t["_replicate"]})
    return cands


def nondetected_controls(turns, candidate_keys, per_condition=20):
    """
    RANDOM_NONDETECTED_CONTROL_TURNS.

    Auditing only what a detector proposed can never tell you what the detector missed.
    These turns fired NO detector; they are not "known negatives" and must not be called
    that. Their function is to measure hyper-exact cases the detector overlooked.

    Deterministic: turns are ordered by a stable hash and taken round-robin across focus
    groups, so every focus group contributes before any contributes twice.
    """
    pool = defaultdict(lambda: defaultdict(list))
    for t in turns:
        key = (t["doc_id"], t["question"], t["turn"])
        if key in candidate_keys:
            continue
        if t["n_words"] < 15:
            continue          # too short to judge specificity either way
        pool[t["_condition"]][t["_fg"]].append(t)

    chosen = []
    for cond in afc.CONDITIONS:
        by_fg = {f: sorted(v, key=lambda x: _sha(f"ctl|{x['doc_id']}|{x['turn']}"))
                 for f, v in sorted(pool[cond].items())}
        picked, i = [], 0
        while len(picked) < per_condition and any(by_fg.values()):
            for f in sorted(by_fg):
                if len(picked) >= per_condition:
                    break
                if i < len(by_fg[f]):
                    picked.append(by_fg[f][i])
            i += 1
        chosen.extend(picked[:per_condition])

    out = []
    for t in chosen:
        item = _sha(f"hxctl|{t['doc_id']}|{t['question']}|{t['turn']}")[:16].upper()
        out.append({
            "item_id": f"HX-{item}",
            "detectors_fired": [], "matched_strings": [], "n_detectors": 0,
            "turn_id": f"T{t['turn']:03d}",
            "speaker": t["participant"].split("#")[-1],
            "quote": t["text"], "n_words": t["n_words"],
            "_stratum": "RANDOM_NONDETECTED_CONTROL_TURNS",
            "_doc_id": t["doc_id"], "_question": t["question"],
            "_condition": t["_condition"], "_fg": t["_fg"],
            "_replicate": t["_replicate"]})
    return out


# ------------------------------------------------ G profile-consistency pairs
_STANCE = re.compile(
    r"\b(i (?:would|wouldn't|will|won't|do|don't|did|didn't|can|can't|could|couldn't|"
    r"like|hate|love|prefer|never|always|think|reckon|believe))\b", re.I)


def consistency_candidates(turns, n_control=60):
    """
    Candidate pairs of first-person stance statements by the SAME participant in
    DIFFERENT questions. A screener proposes; it does not adjudicate. A random control
    sample of pairs the screener did NOT propose is included so false negatives can be
    estimated - without it, a screener's silence would be mistaken for consistency.
    """
    by_part = defaultdict(list)
    for t in turns:
        for m in _STANCE.finditer(t["text"]):
            s = max(0, m.start() - 40)
            frag = t["text"][s:m.start() + 220].strip()
            by_part[(t["doc_id"], t["participant"])].append(
                {"question": t["question"], "turn": t["turn"], "fragment": frag,
                 "_condition": t["_condition"], "_fg": t["_fg"],
                 "_replicate": t["_replicate"]})
            break        # one stance fragment per turn keeps the inventory tractable

    screened, unscreened = [], []
    for (doc, part), items in by_part.items():
        for a, b in combinations(items, 2):
            if a["question"] == b["question"]:
                continue
            rec = {"doc_id": doc, "participant": part, "a": a, "b": b}
            # The screener proposes a pair when the two stance fragments share little
            # vocabulary, which is a weak signal of divergence - and is why it cannot be
            # the verdict.
            wa = set(afc.words(a["fragment"]))
            wb = set(afc.words(b["fragment"]))
            jac = len(wa & wb) / len(wa | wb) if (wa | wb) else 0.0
            rec["screener_jaccard"] = round(jac, 4)
            (screened if jac < 0.12 else unscreened).append(rec)

    rng = random.Random(SEED)
    control = rng.sample(unscreened, min(n_control, len(unscreened)))
    for r in control:
        r["control_sample"] = True

    def _pack(rec, tag):
        item = _sha(f"pc|{rec['doc_id']}|{rec['participant']}|"
                    f"{rec['a']['turn']}|{rec['b']['turn']}")[:16].upper()
        return {"item_id": f"PC-{item}",
                "source": tag,
                "screener_jaccard": rec["screener_jaccard"],
                "speaker": rec["participant"].split("#")[-1],
                "statement_a": {"turn_id": f"T{rec['a']['turn']:03d}",
                                "quote": rec["a"]["fragment"]},
                "statement_b": {"turn_id": f"T{rec['b']['turn']:03d}",
                                "quote": rec["b"]["fragment"]},
                "_doc_id": rec["doc_id"],
                "_question_a": rec["a"]["question"],
                "_question_b": rec["b"]["question"],
                "_condition": rec["a"]["_condition"], "_fg": rec["a"]["_fg"],
                "_replicate": rec["a"]["_replicate"]}

    return ([_pack(r, "SCREENER_PROPOSED") for r in screened]
            + [_pack(r, "RANDOM_CONTROL_NOT_PROPOSED") for r in control]), len(unscreened)


# ----------------------------------------------------- pilot construction
def consistency_pilot(pairs, n_proposed=60):
    """
    120 pairs: the 60 random controls already drawn, plus 60 screener-proposed pairs
    stratified by condition, by similarity tercile and by focus group where availability
    allows. Sending all 802 before knowing whether the auditor is stable would spend the
    budget on an instrument nobody has checked.
    """
    controls = [x for x in pairs if x["source"] == "RANDOM_CONTROL_NOT_PROPOSED"]
    proposed = [x for x in pairs if x["source"] == "SCREENER_PROPOSED"]

    vals = sorted(x["screener_jaccard"] for x in proposed)
    t1, t2 = vals[len(vals) // 3], vals[2 * len(vals) // 3]

    def tercile(v):
        return "T1" if v <= t1 else ("T2" if v <= t2 else "T3")

    cells = defaultdict(list)
    for x in proposed:
        cells[(x["_condition"], tercile(x["screener_jaccard"]), x["_fg"])].append(x)
    for k in cells:
        cells[k].sort(key=lambda z: z["item_id"])

    # Round-robin over strata so every cell contributes before any contributes twice.
    picked, i, keys = [], 0, sorted(cells)
    while len(picked) < n_proposed and any(len(cells[k]) > i for k in keys):
        for k in keys:
            if len(picked) >= n_proposed:
                break
            if i < len(cells[k]):
                picked.append(cells[k][i])
        i += 1
    picked = picked[:n_proposed]

    for x in controls + picked:
        x["_similarity_tercile"] = tercile(x["screener_jaccard"])
    strata = sorted({f"{x['_condition']}|{x['_similarity_tercile']}" for x in picked})
    return controls + picked, {
        "tercile_bounds": [round(t1, 4), round(t2, 4)],
        "n_strata_available": len(cells),
        "strata_represented": strata,
        "n_controls": len(controls), "n_proposed": len(picked)}


def cache_key(classification, item_id, payload, repetition_index, model, schema_sha):
    """
    Distinct per item AND per repetition. Two stochastic repetitions sharing a key would
    return one cached answer twice and look like perfect agreement.
    """
    return _sha("|".join([classification, item_id,
                          _sha(json.dumps(payload, sort_keys=True)),
                          schema_sha, model, f"rep{repetition_index}"]))


# --------------------------------------------- auditor technical validation
AUDITOR_VALIDATION_CASES = [
    {"case": "DIRECT_CONTRADICTION", "must_return": "UNEXPLAINED_CONTRADICTION",
     "a": "i never eat meat, i gave it up years ago and i do not miss it at all",
     "b": "i have a steak most weekends, it is the best part of my week"},
    {"case": "EXPLAINED_CHANGE", "must_return": "POSITION_CHANGED_WITH_EXPLANATION",
     "a": "i would never cook plant based food at home, it is not for me",
     "b": "i said earlier it was not for me, but hearing you all i have changed my "
          "mind and i would try cooking it"},
    {"case": "DIFFERENT_CONTEXTS_NOT_CONTRADICTORY",
     "must_return": "CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY",
     "a": "when i am out with my mates i will always order the burger",
     "b": "at home during the week i mostly cook vegetables and pasta"},
    {"case": "EVIDENCE_FROM_ANOTHER_SPEAKER", "must_return": "REJECT",
     "reject_reason": "the quoted evidence is attributed to a different participant"},
    {"case": "NON_LITERAL_QUOTE", "must_return": "REJECT",
     "reject_reason": "the returned quote is not contiguous verbatim text of the item"},
    {"case": "UNKNOWN_TURN_ID", "must_return": "REJECT",
     "reject_reason": "the returned turn id is not one of the two supplied"},
    {"case": "NO_JUSTIFICATION", "must_return": "REJECT",
     "reject_reason": "a category was returned with an empty justification"},
    {"case": "UNCERTAIN_WITHOUT_EXPLANATION", "must_return": "REJECT",
     "reject_reason": "UNCERTAIN was returned without stating what would resolve it"},
]

# Prospective gate, fixed BEFORE any result is seen. No conventional 0.80 is adopted:
# each bound is argued from what the interpretation needs.
CONSISTENCY_PILOT_GATE = {
    "id": "PROFILE_CONSISTENCY_PILOT_GATE_V1",
    "fixed_before_any_result_is_seen": True,
    "no_conventional_threshold_adopted": (
        "0.80 is not used as a default. Each bound below is set by the precision the "
        "interpretation needs, not by convention."),
    "criteria": {
        "planted_contradiction_recall": {
            "requirement": "the direct-contradiction validation case returns "
                           "UNEXPLAINED_CONTRADICTION in BOTH repetitions",
            "why": "an auditor that misses a contradiction built to be unmissable "
                   "cannot support any claim about contradictions"},
        "contradiction_vs_context_separation": {
            "requirement": "the CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY case is never "
                           "returned as UNEXPLAINED_CONTRADICTION in either repetition",
            "why": "the indicator rests entirely on this distinction; confusing the two "
                   "would inflate contradiction in exactly the direction under study"},
        "malformed_response_rejection": {
            "requirement": "all five REJECT validation cases are rejected",
            "why": "a verdict resting on a misattributed or paraphrased quote is not "
                   "evidence"},
        "exact_agreement_between_repetitions": {
            "detection_only_floor": 0.60,
            "full_audit_floor": 0.75,
            "why": ("below 0.60 the repetitions disagree on more than a third of items "
                    "and no rate computed from them would be interpretable; 0.75 is "
                    "where a five-category judgement becomes stable enough to carry a "
                    "reported distribution rather than a flag")},
        "uncertain_rate": {
            "ceiling": 0.30,
            "why": "above 0.30 the audit is mostly declining to decide and the "
                   "remaining categories describe a self-selected subset"},
        "verbatim_evidence_validity": {
            "floor": 0.95,
            "why": "quote verification is mechanical, so anything short of near-perfect "
                   "means the auditor is reconstructing rather than citing"},
        "control_behaviour": {
            "requirement": "the 60 non-proposed controls are adjudicated with the same "
                           "field completeness as the proposed pairs",
            "why": "if controls are treated differently, the false-negative estimate "
                   "they exist to provide is not usable"},
    },
    "outcomes": ["AUDITOR_USABLE_FOR_EXPLORATORY_FULL_AUDIT",
                 "AUDITOR_USABLE_FOR_DETECTION_ONLY",
                 "AUDITOR_USABLE_FOR_CORROBORATION_ONLY",
                 "AUDITOR_UNSTABLE_STOP"],
    "if_gate_fails": ("the remaining 682 pairs are NOT executed and the instability is "
                      "itself the pilot result"),
    "disagreement_resolution_forbidden": [
        "model confidence", "modal vote", "a third call", "similarity scores",
        "unrecorded manual choice"],
    "disagreement_resolution_rule": (
        "items where the two repetitions disagree stay UNRESOLVED and are reported as "
        "such; they are never collapsed to a single label"),
}


# ------------------------------------------------------------------- packaging
def _split(items, keys_public):
    """Public request payload and sealed provenance reference, never in one file."""
    public = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]
    sealed = {it["item_id"]: {k: v for k, v in it.items() if k.startswith("_")}
              for it in items}
    for p in public:
        assert set(p) <= set(keys_public), sorted(set(p) - set(keys_public))
    return public, sealed


def _cost(items, per_item_words, out_tokens_per_item, items_per_request):
    n_req = max(1, -(-len(items) // items_per_request))
    words_per_req = per_item_words * items_per_request
    in_tok = int(TOK_SLOPE * words_per_req + TOK_INTERCEPT) * n_req
    out_tok = out_tokens_per_item * len(items)
    return {"n_items": len(items), "items_per_request": items_per_request,
            "n_requests": n_req,
            "estimated_input_tokens": in_tok,
            "estimated_output_tokens": out_tok,
            "claude_batch_usd": round(in_tok / 1e6 * CLAUDE_BATCH_IN
                                      + out_tok / 1e6 * CLAUDE_BATCH_OUT, 4),
            "claude_rate_verified_utc": "2026-08-02",
            "gemini_cost_status": GEMINI_COST,
            "token_model": "tokens = 1.7502 * words + 1620 (measured, R2 0.9989)"}


MODEL_FOR_KEYS = "blinded-auditor-tbd"
SCHEMA_SHA_PLACEHOLDER = "SCHEMA_SHA_ASSIGNED_AT_SUBMISSION"


def build() -> dict:
    turns = _turns()
    hx_cand = hyper_exact_candidates(turns)
    cand_keys = {(t["doc_id"], t["question"], t["turn"]) for t in turns
                 if any(p.search(t["text"]) for p in PATTERNS.values())}
    hx_ctl = nondetected_controls(turns, cand_keys, per_condition=20)
    hx = hx_cand + hx_ctl                      # the audited universe: 67 + 60 = 127

    pc_all, n_unscreened = consistency_candidates(turns)
    pilot, strat = consistency_pilot(pc_all)

    public_keys_hx = {"item_id", "detectors_fired", "matched_strings", "n_detectors",
                      "turn_id", "speaker", "quote", "n_words"}
    # The auditor must not be able to tell a detector candidate from a control. The
    # detector fields would give the stratum away, so they are stripped from BOTH.
    hx_payload = [{k: v for k, v in i.items()
                   if k in {"item_id", "turn_id", "speaker", "quote", "n_words"}}
                  for i in sorted(hx, key=lambda z: z["item_id"])]
    _, hx_sealed = _split(hx, public_keys_hx | {"item_id"})
    hx_pub = hx_payload

    pc_pub, pc_sealed = _split(pc_all, {"item_id", "source", "screener_jaccard",
                                        "speaker", "statement_a", "statement_b"})
    # Same reasoning for the pilot: `source` and the screener score reveal the stratum.
    pilot_payload = [{k: v for k, v in i.items()
                      if k in {"item_id", "speaker", "statement_a", "statement_b"}}
                     for i in sorted(pilot, key=lambda z: z["item_id"])]
    _, pilot_sealed = _split(pilot, {"item_id", "source", "screener_jaccard", "speaker",
                                     "statement_a", "statement_b"})

    pilot_requests = []
    for rep in (1, 2):
        for it in pilot_payload:
            pilot_requests.append({
                "custom_id": f"PC-R{rep}-{it['item_id'].split('-')[1]}",
                "item_id": it["item_id"], "repetition_index": rep,
                "cache_key": cache_key("PROFILE_CONSISTENCY_PILOT", it["item_id"],
                                       it, rep, MODEL_FOR_KEYS,
                                       SCHEMA_SHA_PLACEHOLDER)})
    assert len({r["cache_key"] for r in pilot_requests}) == len(pilot_requests)

    hx_words = int(sum(i["n_words"] for i in hx) / max(1, len(hx)))
    pc_words = int(sum(len(i["statement_a"]["quote"].split())
                       + len(i["statement_b"]["quote"].split()) for i in pilot)
                   / max(1, len(pilot)))

    by_cond_hx = defaultdict(int)
    for i in hx_cand:
        by_cond_hx[i["_condition"]] += 1
    by_cond_ctl = defaultdict(int)
    for i in hx_ctl:
        by_cond_ctl[i["_condition"]] += 1
    by_cond_pc = defaultdict(int)
    for i in pilot:
        by_cond_pc[i["_condition"]] += 1
    pc = pc_all

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "AGENT_FIDELITY_BLINDED_AUDIT_PACKAGES",
        "status": "PREPARED_NOT_EXECUTED",
        "no_api_calls": True, "no_new_human_tasks": True,
        "detector_role": ("the detectors PROPOSE candidates and classify nothing; the "
                          "category is a contextual judgement the audit makes"),
        "numeral_density_status": "NUMERAL_DENSITY_DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS",
        "numeral_density_warning": ("a lower numeral density must not be read as less "
                                    "hyper-exactness; density counts how many figures "
                                    "appear, not how they are used"),
        "blinding": {
            "payload_excludes": ["condition", "focus group", "replicate",
                                 "human or synthetic", "model", "agent profile",
                                 "run name", "unit_id"],
            "sealed_reference": "agent_fidelity_audit_sealed_reference.json",
            "request_manifest_has_no_read_dependency_on_the_sealed_file": True,
        },
        "hyper_exactness": {
            "categories": list(HYPER_EXACT_CATEGORIES),
            "required_fields_per_decision": ["item_id", "verbatim_quote", "turn_id",
                                             "speaker", "category", "justification",
                                             "minimum_context_used",
                                             "what_would_resolve_uncertain"],
            "n_participant_turns_scanned": len(turns),
            "n_detector_candidates": len(hx_cand),
            "n_random_nondetected_controls": len(hx_ctl),
            "n_universe": len(hx),
            "control_stratum_name": "RANDOM_NONDETECTED_CONTROL_TURNS",
            "controls_are_not_known_negatives": (
                "these turns fired no detector; they have not been judged and must "
                "never be called known negatives. Their purpose is to measure "
                "hyper-exact cases the detector missed."),
            "candidates_by_condition": dict(by_cond_hx),
            "controls_by_condition": dict(by_cond_ctl),
            "control_selection": ("deterministic: non-candidate turns of at least 15 "
                                  "words ordered by a stable hash and taken round-robin "
                                  "across focus groups, 20 per condition"),
            "no_overlap_between_candidates_and_controls": True,
            "stratum_is_not_revealed_to_the_auditor": (
                "detector fields are stripped from every payload, so a control and a "
                "candidate are indistinguishable in the request"),
            "detector_hit_counts": {
                k: sum(1 for i in hx_cand if k in i["detectors_fired"])
                for k in PATTERNS},
            "mean_words_per_item": hx_words,
            "cost_full_universe": _cost(hx, hx_words, 220, 12),
            "reporting_distinctions_required": [
                "detector candidate yield",
                "adjudicated hyper-exact cases among candidates",
                "hyper-exact cases found in the nondetected controls",
                "estimated or detected corpus rate"],
            "if_controls_cannot_support_prevalence": "DETECTED_LOWER_BOUND_RATE",
            "unaudited_is_not_negative": (
                "turns that were neither detected nor audited are reported as "
                "NOT_AUDITED, never as negative"),
        },
        "profile_consistency": {
            "classification": "LLM_ASSISTED_EXPLORATORY_PROFILE_CONSISTENCY_AUDIT",
            "not_called": "validated profile consistency",
            "categories": list(CONSISTENCY_CATEGORIES),
            "screener_role": ("vocabulary overlap proposes pairs; it never decides. No "
                              "embedding and no NLI model may dictate a verdict."),
            "n_candidate_pairs_total": len(pc),
            "n_screener_proposed_total": sum(1 for i in pc
                                             if i["source"] == "SCREENER_PROPOSED"),
            "n_unscreened_population": n_unscreened,
            "control_sample_purpose": ("estimate false negatives; a screener's silence "
                                       "is not evidence of consistency"),
            "control_sample_seed": SEED,

            "pilot": {
                "n_pairs": len(pilot),
                "n_random_controls": strat["n_controls"],
                "n_screener_proposed": strat["n_proposed"],
                "stratification": ("condition x similarity tercile x focus group, "
                                   "round-robin so every stratum contributes before "
                                   "any contributes twice"),
                "similarity_tercile_bounds": strat["tercile_bounds"],
                "n_strata_available": strat["n_strata_available"],
                "strata_represented": strat["strata_represented"],
                "pairs_by_condition": dict(by_cond_pc),
                "proposed_by_condition": {
                    c: sum(1 for i in pilot if i["source"] == "SCREENER_PROPOSED"
                           and i["_condition"] == c) for c in afc.CONDITIONS},
                "controls_by_condition": {
                    c: sum(1 for i in pilot
                           if i["source"] == "RANDOM_CONTROL_NOT_PROPOSED"
                           and i["_condition"] == c) for c in afc.CONDITIONS},
                "control_condition_balance_note": (
                    "the 60 controls were drawn at random from the unscreened "
                    "population and are therefore NOT balanced by condition; only the "
                    "60 proposed pairs are stratified. Any false-negative estimate must "
                    "be reported per condition with its own denominator."),
                "n_repetitions": 2,
                "n_adjudications": len(pilot) * 2,
                "cache_keys_distinct_per_item_and_repetition": True,
                "n_distinct_cache_keys": len(pilot_requests),
                "mean_words_per_pair": pc_words,
                "cost": _cost(pilot * 2, pc_words, 200, 10),
                "gate": CONSISTENCY_PILOT_GATE,
                "auditor_validation_cases": AUDITOR_VALIDATION_CASES,
                "n_remaining_pairs_not_sent": len(pc) - len(pilot),
                "remaining_pairs_are_blocked_until_the_gate_passes": True,
            },
            "cost_full_audit_if_gate_passes": _cost(pc, pc_words, 200, 10),
        },
        "_public_hyper_exactness": hx_pub,
        "_sealed_hyper_exactness": hx_sealed,
        "_public_consistency": pc_pub,
        "_sealed_consistency": pc_sealed,
        "_pilot_payload": pilot_payload,
        "_pilot_sealed": pilot_sealed,
        "_pilot_requests": pilot_requests,
    }


def write(o: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    pub_hx = o.pop("_public_hyper_exactness")
    seal_hx = o.pop("_sealed_hyper_exactness")
    pub_pc = o.pop("_public_consistency")
    seal_pc = o.pop("_sealed_consistency")
    pilot_pub = o.pop("_pilot_payload")
    pilot_seal = o.pop("_pilot_sealed")
    pilot_req = o.pop("_pilot_requests")

    (_OUT / "profile_consistency_pilot_blinded.json").write_text(
        json.dumps({"categories": list(CONSISTENCY_CATEGORIES),
                    "n_repetitions": 2, "items": pilot_pub},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (_OUT / "profile_consistency_pilot_manifest.json").write_text(
        json.dumps({"id": "PROFILE_CONSISTENCY_PILOT_MANIFEST",
                    "status": "PREPARED_NOT_SUBMITTED",
                    "n_items": len(pilot_pub), "n_repetitions": 2,
                    "n_adjudications": len(pilot_req),
                    "gate": CONSISTENCY_PILOT_GATE,
                    "auditor_validation_cases": AUDITOR_VALIDATION_CASES,
                    "requests": pilot_req},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    (_OUT / "agent_fidelity_audit_packages.json").write_text(
        json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")
    (_OUT / "hyper_exactness_universe_blinded.json").write_text(
        json.dumps({"categories": list(HYPER_EXACT_CATEGORIES),
                    "n_items": len(pub_hx), "items": pub_hx},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (_OUT / "profile_consistency_pairs_blinded.json").write_text(
        json.dumps({"categories": list(CONSISTENCY_CATEGORIES), "items": pub_pc},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (_OUT / "agent_fidelity_audit_sealed_reference.json").write_text(
        json.dumps({"hyper_exactness": seal_hx, "profile_consistency": seal_pc},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    with (_OUT / "hyper_exactness_universe.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "turn_id", "speaker", "n_words"])
        for i in pub_hx:
            w.writerow([i["item_id"], i["turn_id"], i["speaker"], i["n_words"]])


def main() -> int:
    o = build()
    hx, pc = o["hyper_exactness"], o["profile_consistency"]
    write(o)
    print(f"participant turns scanned: {hx['n_participant_turns_scanned']}")
    print(f"\n=== E hyper-exactness universe: {hx['n_universe']} items ===")
    print(f"  detector candidates {hx['n_detector_candidates']}  "
          f"{hx['candidates_by_condition']}")
    print(f"  {hx['control_stratum_name']} {hx['n_random_nondetected_controls']}  "
          f"{hx['controls_by_condition']}")
    for k, v in sorted(hx["detector_hit_counts"].items(), key=lambda x: -x[1]):
        print(f"    {k:32s} {v:>4d}")
    c = hx["cost_full_universe"]
    print(f"  {c['n_items']:>4d} items -> {c['n_requests']:>3d} requests   "
          f"in {c['estimated_input_tokens']:>7,d} tok  out "
          f"{c['estimated_output_tokens']:>6,d} tok   "
          f"Claude Batch USD {c['claude_batch_usd']:.2f}   "
          f"Gemini {c['gemini_cost_status']}")

    pl = pc["pilot"]
    print(f"\n=== G profile-consistency PILOT: {pl['n_pairs']} pairs x "
          f"{pl['n_repetitions']} repetitions = {pl['n_adjudications']} "
          f"adjudications ===")
    print(f"  {pl['n_random_controls']} random controls + "
          f"{pl['n_screener_proposed']} screener-proposed  "
          f"{pl['pairs_by_condition']}")
    print(f"  tercile bounds {pl['similarity_tercile_bounds']}   "
          f"strata available {pl['n_strata_available']}   "
          f"distinct cache keys {pl['n_distinct_cache_keys']}")
    c = pl["cost"]
    print(f"  {c['n_items']:>4d} adjudications -> {c['n_requests']:>3d} requests   "
          f"in {c['estimated_input_tokens']:>7,d} tok  out "
          f"{c['estimated_output_tokens']:>6,d} tok   "
          f"Claude Batch USD {c['claude_batch_usd']:.2f}")
    print(f"  {pl['n_remaining_pairs_not_sent']} remaining pairs are BLOCKED until the "
          f"gate passes")
    c = pc["cost_full_audit_if_gate_passes"]
    print(f"  full audit if the gate passes: {c['n_items']} pairs -> "
          f"{c['n_requests']} requests, Claude Batch USD {c['claude_batch_usd']:.2f}")

    tot_in = (hx["cost_full_universe"]["estimated_input_tokens"]
              + pl["cost"]["estimated_input_tokens"])
    tot_out = (hx["cost_full_universe"]["estimated_output_tokens"]
               + pl["cost"]["estimated_output_tokens"])
    usd = (hx["cost_full_universe"]["claude_batch_usd"]
           + pl["cost"]["claude_batch_usd"])
    reqs = hx["cost_full_universe"]["n_requests"] + pl["cost"]["n_requests"]
    print(f"\nAUTHORISATION BUNDLE (hyper-exactness universe + consistency pilot): "
          f"{reqs} requests, in {tot_in:,d} tok, out {tot_out:,d} tok, "
          f"Claude Batch USD {usd:.2f}")
    print("\nSTATUS: PREPARED_NOT_EXECUTED - no API call made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
