"""
Agent-fidelity blinded audits, v2.

    py scripts/agent_fidelity_audit_v2.py --preflight

Supersedes the packaging in `agent_fidelity_audit_packages.py`. Four things changed and
each one changed because the v1 version would have produced a number nobody could defend.

1. EVIDENCE IS WHOLE AND SENTENCE-ALIGNED.
   v1 sent `text[start-40 : start+220]`, which cuts words in half and drops the sentence
   that gives a claim its meaning. Every item now carries the full participant turn, the
   guide question it answered, and - only where a turn exceeds the length limit - a
   sentence-aligned quote plus a separate sentence-aligned context window. Nothing is cut
   mid-word, and both the source turn and the presented text are hashed.

2. THE CONSISTENCY SCREENER NO LONGER USES LOW VOCABULARY OVERLAP.
   Jaccard < 0.12 mostly selects pairs about DIFFERENT TOPICS, which is the opposite of a
   contradiction. A contradiction needs a shared referent AND a possible contrast of
   position, so the screener now requires both.

3. FIXTURES ARE EXECUTED, NOT DESCRIBED.
   v1 listed eight validation cases in a manifest that no request would ever carry. They
   are now real items with real cache keys, marked only in the sealed mapping.

4. PROVIDER REQUESTS ARE COUNTED, NOT ESTIMATED.
   v1 wrote 240 item-rows and announced "24 requests". There are now two manifests, and
   the announced request count IS the length of the provider manifest.

Offline until `--submit`. No closed artefact is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, UTC
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

import agent_fidelity_corpus as afc
import agent_fidelity_audit_packages as v1

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "analysis/production_evaluation/agent_fidelity"

TOK_SLOPE, TOK_INTERCEPT = 1.7502, 1620
CLAUDE_BATCH_IN, CLAUDE_BATCH_OUT = 2.50, 12.50
GEMINI_COST = "NOT_CALCULATED_RATE_NOT_VERIFIED"

MODEL = "claude-opus-5"
EFFORT = "high"
N_REPETITIONS = 2

# Literal moderator headers from the human transcripts. The auditor needs to know what
# was asked; it reveals nothing about condition or provenance because both sides answered
# the same guide.
GUIDE_QUESTIONS = {
    1: "What's your favourite place in your city to spend time with your male friends? "
       "Why - feel free to be specific?",
    2: "How do you decide what to eat?",
    3: "Do you think your gender influences what you eat? Tell us more about why or why "
       "not?",
    4: "Imagine you decided to go plant-based - what would need to change in your life "
       "for you to do that?",
    5: "What might make plant-based foods more appealing to you or other men you know?",
}

MAX_QUOTE_WORDS = 220         # beyond this a turn is reduced, sentence-aligned
CONTEXT_SENTENCES = 2

HX_CATEGORIES = v1.HYPER_EXACT_CATEGORIES
PC_CATEGORIES = v1.CONSISTENCY_CATEGORIES

_SENT = re.compile(r"(?<=[.!?])\s+")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------- evidence
def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.strip()) if s.strip()]


def sentence_aligned(text: str, max_words: int = MAX_QUOTE_WORDS):
    """
    Reduce a long turn WITHOUT cutting a word or a sentence.

    Returns (quote, context, was_reduced). The quote is a run of whole sentences from the
    middle of the turn; the context is the sentences immediately around it, supplied
    separately so the auditor can see what surrounds the claim without the two being
    confused.
    """
    words = text.split()
    if len(words) <= max_words:
        return text, "", False
    sents = sentences(text)
    if len(sents) == 1:
        # one very long sentence: keep it whole rather than cut a word
        return text, "", False
    mid = len(sents) // 2
    lo = hi = mid
    total = len(sents[mid].split())
    while total < max_words and (lo > 0 or hi < len(sents) - 1):
        if lo > 0 and (hi == len(sents) - 1
                       or len(sents[lo - 1].split()) <= len(sents[hi + 1].split())):
            lo -= 1
            total += len(sents[lo].split())
        elif hi < len(sents) - 1:
            hi += 1
            total += len(sents[hi].split())
        else:
            break
    quote = " ".join(sents[lo:hi + 1])
    ctx = " ".join(sents[max(0, lo - CONTEXT_SENTENCES):lo]
                   + sents[hi + 1:hi + 1 + CONTEXT_SENTENCES])
    return quote, ctx, True


def evidence(turn: dict) -> dict:
    """One statement, whole and verifiable against its source turn."""
    full = turn["text"]
    quote, ctx, reduced = sentence_aligned(full)
    return {
        "turn_id": f"T{turn['turn']:03d}",
        "guide_question": GUIDE_QUESTIONS[turn["question"]],
        "quote": quote,
        "context_window": ctx,
        "is_full_turn": not reduced,
        "n_words_presented": len(quote.split()),
        "n_words_source_turn": len(full.split()),
        "source_turn_sha256": _sha(full),
        "presented_text_sha256": _sha(quote),
    }


def verify_literal(presented: str, source: str) -> bool:
    """The presented text must be a contiguous substring of the source turn."""
    return presented in source


# ------------------------------------------------- consistency screener (v2)
_NEG = re.compile(r"\b(not|never|no|nothing|none|dont|doesnt|didnt|wouldnt|wont|cant|"
                  r"couldnt|hardly|rarely|barely)\b", re.I)
_POS_FREQ = re.compile(r"\b(always|every|all the time|constantly|usually|mostly|often|"
                       r"definitely|absolutely)\b", re.I)
_CHANGE = re.compile(r"\b(but|however|although|though|used to|changed|now|these days|"
                     r"actually|whereas|instead)\b", re.I)
_STANCE = re.compile(r"\b(i|i'd|id|ive|i've)\s+(would|wouldn't|wont|will|do|don't|dont|"
                     r"did|didn't|can|can't|cant|could|couldn't|like|hate|love|prefer|"
                     r"never|always|think|reckon|believe|eat|avoid|buy|cook)\b", re.I)

_STOP = set("""a an the and or but if then than that this these those of in on at to for
with without from by as is are was were be been being am it its they them their there
here what which who how why when we you i he she his her our your my me not no yes do
does did done have has had can could would should will just about into over under more
most less very really quite so such own same other each any all some one two three thing
things people person like get got make made go going went say said know think really
actually maybe probably yeah okay right well um uh oh
""".split())


def content_terms(text: str) -> set[str]:
    return {w for w in afc.words(text) if len(w) >= 4 and w not in _STOP}


def polarity_profile(text: str) -> dict:
    return {"negation": bool(_NEG.search(text)),
            "high_frequency": bool(_POS_FREQ.search(text)),
            "change_marker": bool(_CHANGE.search(text))}


def polarity_contrast(a: str, b: str) -> bool:
    """
    A possible contrast of position: the two statements differ in NEGATION or in
    FREQUENCY commitment.

    A change marker on its own is deliberately NOT sufficient. Words like "but", "now",
    "actually" and "though" occur in almost every conversational turn of this length -
    1,257 of 2,611 screened pairs had their contrast driven by a change marker alone, and
    including them made HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST unreachable. A
    stratum defined by the absence of a near-constant is empty by construction, so the
    marker is recorded as a separate flag and does not decide the stratum.

    This PROPOSES; it never decides.
    """
    pa, pb = polarity_profile(a), polarity_profile(b)
    return (pa["negation"] != pb["negation"]
            or pa["high_frequency"] != pb["high_frequency"])


def screen_pairs(turns, high_similarity_quantile=0.70):
    """
    Same participant, different guide questions, with a shared referent.

    Topic similarity is word-level TF-IDF cosine over content terms, computed within a
    document so one session's vocabulary does not set another's scale. Pairs are placed
    in three strata; none of them is a negative.
    """
    by_part = defaultdict(list)
    for t in turns:
        if len(t["text"].split()) < 25:
            continue
        if not _STANCE.search(t["text"]):
            continue
        by_part[(t["doc_id"], t["participant"])].append(t)

    rows = []
    for (doc, part), items in sorted(by_part.items()):
        if len(items) < 2:
            continue
        texts = [i["text"] for i in items]
        vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 1), lowercase=True,
                              stop_words=sorted(_STOP), min_df=1)
        try:
            X = vec.fit_transform(texts).toarray()
        except ValueError:
            continue
        X = X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
        for i, j in combinations(range(len(items)), 2):
            a, b = items[i], items[j]
            if a["question"] == b["question"]:
                continue
            shared = content_terms(a["text"]) & content_terms(b["text"])
            rows.append({
                "doc_id": doc, "participant": part, "a": a, "b": b,
                "topic_cosine": round(float(X[i] @ X[j]), 4),
                "n_shared_content_terms": len(shared),
                "shared_content_terms": sorted(shared)[:12],
                "polarity_contrast": polarity_contrast(a["text"], b["text"]),
                "condition": a["_condition"], "fg": a["_fg"],
                "replicate": a["_replicate"]})

    if not rows:
        return []
    cos = sorted(r["topic_cosine"] for r in rows)
    hi_cut = cos[int(len(cos) * high_similarity_quantile)]
    for r in rows:
        high = r["topic_cosine"] >= hi_cut and r["n_shared_content_terms"] >= 3
        if high and r["polarity_contrast"]:
            r["stratum"] = "HIGH_TOPIC_SIMILARITY_WITH_POLARITY_CONTRAST"
        elif high:
            r["stratum"] = "HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST"
        else:
            r["stratum"] = "LOW_TOPIC_SIMILARITY_RANDOM_CONTROL"
    return rows, round(hi_cut, 4)


def balanced_pilot(rows, per_condition_proposed=20, per_condition_control=20):
    """
    A balanced pilot: 20 proposed and 20 controls in EVERY condition. Selection is
    deterministic - candidates are ordered by a stable hash and taken round-robin over
    (focus group x topic-similarity tercile) so no cell is silently favoured.

    If a cell cannot be filled, the shortfall is REPORTED and the caller stops. A quietly
    substituted pair would make the per-condition denominators fictional, which is the
    defect this whole rebuild exists to remove.
    """
    def _key(r):
        return _sha(f"pilot2|{r['doc_id']}|{r['participant']}|"
                    f"{r['a']['turn']}|{r['b']['turn']}")

    proposed_pool = [r for r in rows
                     if r["stratum"].startswith("HIGH_TOPIC_SIMILARITY")]
    control_pool = [r for r in rows
                    if r["stratum"] == "LOW_TOPIC_SIMILARITY_RANDOM_CONTROL"]

    cos = sorted(r["topic_cosine"] for r in rows)
    t1, t2 = cos[len(cos) // 3], cos[2 * len(cos) // 3]

    def tercile(v):
        return "T1" if v <= t1 else ("T2" if v <= t2 else "T3")

    def _draw(pool, cond, n):
        cells = defaultdict(list)
        for r in pool:
            if r["condition"] != cond:
                continue
            cells[(r["fg"], tercile(r["topic_cosine"]))].append(r)
        for k in cells:
            cells[k].sort(key=_key)
        picked, i, keys = [], 0, sorted(cells)
        while len(picked) < n and any(len(cells[k]) > i for k in keys):
            for k in keys:
                if len(picked) >= n:
                    break
                if i < len(cells[k]):
                    picked.append(cells[k][i])
            i += 1
        return picked[:n], sum(len(v) for v in cells.values())

    # The proposed half is split evenly across the two HIGH strata. Drawing from their
    # union would let whichever stratum happens to be larger fill the quota, and a
    # stratum that is defined but never sampled cannot inform anything.
    with_pool = [r for r in proposed_pool
                 if r["stratum"] == "HIGH_TOPIC_SIMILARITY_WITH_POLARITY_CONTRAST"]
    without_pool = [r for r in proposed_pool
                    if r["stratum"] == "HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST"]
    half = per_condition_proposed // 2

    plan = [(with_pool, half, "PROPOSED"), (without_pool, half, "PROPOSED"),
            (control_pool, per_condition_control, "CONTROL")]

    selection, shortfalls = [], []
    for cond in afc.CONDITIONS:
        for pool, n, tag in plan:
            got, avail = _draw(pool, cond, n)
            if len(got) < n:
                shortfalls.append({
                    "condition": cond, "role": tag,
                    "stratum": pool[0]["stratum"] if pool else "?",
                    "requested": n, "available": avail, "obtained": len(got)})
            for r in got:
                r["role"] = tag
                r["topic_tercile"] = tercile(r["topic_cosine"])
            selection.extend(got)
    return selection, shortfalls, [round(t1, 4), round(t2, 4)]


# ------------------------------------------------------------------- fixtures
def _fixture_turn(text, turn=900, question=3):
    return {"turn": turn, "question": question, "text": " ".join(text.split()),
            "doc_id": "FIXTURE", "participant": "FIXTURE#S00",
            "_condition": "fixture", "_fg": "fixture", "_replicate": None}


HX_FIXTURES = [
    ("HXF-ORD-1", "ORDINARY_EVERYDAY_SPECIFICITY",
     "i usually grab a coffee on the way in and then have a sandwich around lunchtime. "
     "nothing fancy, just whatever is in the fridge really."),
    ("HXF-ORD-2", "ORDINARY_EVERYDAY_SPECIFICITY",
     "we go to the pub down the road most fridays after work and i normally get a pint "
     "and a burger. it is about a ten minute walk from the office."),
    ("HXF-REC-1", "PLAUSIBLE_PERSONAL_RECALL",
     "i remember the first time i tried one of those bean burgers, it was at my mate's "
     "barbecue a couple of summers ago and it fell apart on the grill."),
    ("HXF-REC-2", "PLAUSIBLE_PERSONAL_RECALL",
     "i gave up red meat for about six months a few years back when i was training, and "
     "i felt fine but i did miss a proper steak."),
    ("HXF-STAT-1", "HYPER_EXACT_STATISTICAL_CLAIM",
     "the research shows that 68.4 per cent of men in this age bracket reduce their meat "
     "consumption within 14 months of a partner going vegetarian."),
    ("HXF-STAT-2", "HYPER_EXACT_STATISTICAL_CLAIM",
     "plant based options are on average 23.7 per cent more expensive per hundred grams "
     "of protein according to the survey data from last year."),
    ("HXF-EPI-1", "IMPLAUSIBLY_PRECISE_EPISODIC_RECALL",
     "it was the 14th of march 2019 at 7.42 in the evening and i ate exactly 312 grams "
     "of chicken, i remember it to the minute."),
    ("HXF-EPI-2", "IMPLAUSIBLY_PRECISE_EPISODIC_RECALL",
     "over the last four years i have eaten precisely 1,247 plant based meals and spent "
     "exactly 3,891 pounds on them, down to the penny."),
    ("HXF-UNC-1", "UNCERTAIN",
     "it was about twenty quid i think, or maybe a bit more, i honestly cannot remember "
     "what the bill came to."),
    ("HXF-UNC-2", "UNCERTAIN",
     "someone told me it was something like a third of the country now but i have no "
     "idea where that figure came from or whether it is right."),
]

PC_FIXTURES = [
    ("PCF-CONTRA-1", "UNEXPLAINED_CONTRADICTION",
     "i never eat meat. i gave it up years ago on principle and i do not miss it at all, "
     "not even a little bit.",
     "i have a steak most weekends. it is honestly the best part of my week and i would "
     "not give it up for anything."),
    ("PCF-CONTRA-2", "UNEXPLAINED_CONTRADICTION",
     "cost is not a factor for me at all. i buy whatever i want when i am doing the "
     "shopping and i never look at the price.",
     "price is the only thing that decides what i buy. i check every label and i will "
     "not pay more than a couple of quid for anything."),
    ("PCF-CHANGE-1", "POSITION_CHANGED_WITH_EXPLANATION",
     "i would never cook plant based food at home. it is just not for me and i would not "
     "know where to start.",
     "i said earlier it was not for me, but hearing you all talk about it i have changed "
     "my mind and i would give cooking it a go."),
    ("PCF-CONTEXT-1", "CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY",
     "when i am out with my mates i will always order the burger. it is what you do when "
     "you are in the pub, nobody is having a salad.",
     "at home during the week i mostly cook vegetables and pasta because it is quicker "
     "and cheaper than doing a proper meat dish."),
    ("PCF-REJECT-SPEAKER", "REJECT",
     "i think the price is the main barrier for most people i know.",
     "as the other participant said, taste matters more than price for him."),
    ("PCF-REJECT-QUOTE", "REJECT",
     "i eat meat about three times a week, mostly chicken.",
     "i eat meat roughly three times per week, mainly chicken."),
    ("PCF-REJECT-TURN", "REJECT",
     "i would try it if the texture was better.",
     "i would try it if the texture was better."),
    ("PCF-REJECT-UNCERTAIN", "REJECT",
     "i am not sure how i feel about it really.",
     "it depends on the day i suppose."),
]


# ------------------------------------------------------------------- manifests
def _cache_key(classification, item_id, payload, rep):
    return _sha("|".join([classification, item_id,
                          _sha(json.dumps(payload, sort_keys=True)),
                          MODEL, EFFORT, f"rep{rep}"]))


def build_manifests(classification, items, items_per_request, out_tokens_per_item,
                    prompt_text):
    """
    Two levels, deliberately separate.

    item_manifest  - one row per item x repetition. This is what must come back.
    provider_request_manifest - one row per ACTUAL provider call, with its items listed.

    The announced number of API requests is len(provider_request_manifest), never the
    length of the item manifest.
    """
    prompt_sha = _sha(prompt_text)
    schema_sha = _sha(json.dumps(SCHEMAS[classification], sort_keys=True))

    item_rows, requests = [], []
    for rep in range(1, N_REPETITIONS + 1):
        ordered = sorted(items, key=lambda z: z["item_id"])
        for it in ordered:
            item_rows.append({
                "item_id": it["item_id"], "repetition_index": rep,
                "cache_key": _cache_key(classification, it["item_id"], it, rep)})
        for k in range(0, len(ordered), items_per_request):
            chunk = ordered[k:k + items_per_request]
            cid = f"{classification[:6]}-R{rep}-B{k // items_per_request + 1:03d}"
            words = sum(len(json.dumps(c).split()) for c in chunk)
            requests.append({
                "custom_id": cid,
                "repetition_index": rep,
                "ordered_item_ids": [c["item_id"] for c in chunk],
                "expected_item_count": len(chunk),
                "prompt_sha256": prompt_sha,
                "schema_sha256": schema_sha,
                "model": MODEL, "effort": EFFORT,
                "max_output_tokens": min(32768, 1024 + out_tokens_per_item * len(chunk)),
                "estimated_input_tokens": int(TOK_SLOPE * words + TOK_INTERCEPT),
                "cache_key": _sha(f"{classification}|{cid}|{prompt_sha}|{schema_sha}|"
                                  f"{MODEL}|{EFFORT}|rep{rep}|"
                                  + ",".join(c["item_id"] for c in chunk)),
            })
    assert len({r["custom_id"] for r in requests}) == len(requests)
    assert len({r["cache_key"] for r in requests}) == len(requests)
    assert len({(r["item_id"], r["repetition_index"]) for r in item_rows}) \
        == len(item_rows)
    covered = [i for r in requests for i in r["ordered_item_ids"]]
    assert len(covered) == len(item_rows), (len(covered), len(item_rows))

    in_tok = sum(r["estimated_input_tokens"] for r in requests)
    out_tok = out_tokens_per_item * len(item_rows)
    cost = {"n_items": len(items), "n_repetitions": N_REPETITIONS,
            "n_adjudications": len(item_rows),
            "n_provider_requests": len(requests),
            "items_per_request": items_per_request,
            "estimated_input_tokens": in_tok, "estimated_output_tokens": out_tok,
            "claude_batch_usd": round(in_tok / 1e6 * CLAUDE_BATCH_IN
                                      + out_tok / 1e6 * CLAUDE_BATCH_OUT, 4),
            "claude_rate_verified_utc": "2026-08-02",
            "gemini_cost_status": GEMINI_COST,
            "announced_request_count_is_len_provider_manifest": True}
    return {"classification": classification, "item_manifest": item_rows,
            "provider_request_manifest": requests, "cost": cost,
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha}


SCHEMAS = {
    "HYPER_EXACTNESS": {
        "type": "object", "additionalProperties": False,
        "required": ["decisions"],
        "properties": {"decisions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["item_id", "turn_id", "speaker", "category",
                         "verbatim_quote", "justification", "minimum_context_used",
                         "what_would_resolve_uncertainty"],
            "properties": {
                "item_id": {"type": "string"}, "turn_id": {"type": "string"},
                "speaker": {"type": "string"},
                "category": {"type": "string", "enum": list(HX_CATEGORIES)},
                "verbatim_quote": {"type": "string"},
                "justification": {"type": "string"},
                "minimum_context_used": {"type": "string"},
                "what_would_resolve_uncertainty": {"type": "string"}}}}}},
    "PROFILE_CONSISTENCY": {
        "type": "object", "additionalProperties": False,
        "required": ["decisions"],
        "properties": {"decisions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["item_id", "category", "quote_a", "quote_b", "turn_id_a",
                         "turn_id_b", "justification", "minimum_context_used",
                         "what_would_resolve_uncertainty"],
            "properties": {
                "item_id": {"type": "string"},
                "category": {"type": "string", "enum": list(PC_CATEGORIES)},
                "quote_a": {"type": "string"}, "quote_b": {"type": "string"},
                "turn_id_a": {"type": "string"}, "turn_id_b": {"type": "string"},
                "justification": {"type": "string"},
                "minimum_context_used": {"type": "string"},
                "what_would_resolve_uncertainty": {"type": "string"}}}}}},
}

HX_PROMPT = """You are auditing single turns from anonymised discussion transcripts.

For each item, classify how the speaker states specificity, using exactly one category:

- ORDINARY_EVERYDAY_SPECIFICITY: concrete but unremarkable detail of the kind people
  produce in ordinary conversation.
- PLAUSIBLE_PERSONAL_RECALL: a specific personal memory at a level of precision a person
  could realistically retain.
- HYPER_EXACT_STATISTICAL_CLAIM: a statistical, survey or population figure stated with
  precision the speaker is unlikely to be able to support.
- IMPLAUSIBLY_PRECISE_EPISODIC_RECALL: a personal episode recalled at a precision a
  person is unlikely to retain.
- UNCERTAIN: the item cannot be classified from what is supplied.

Rules:
- verbatim_quote MUST be a contiguous substring of the quote supplied for that item.
- turn_id and speaker MUST be copied exactly from the item.
- justification must say what in the wording drove the category.
- minimum_context_used must name what you needed to read.
- what_would_resolve_uncertainty is required for every decision, and for UNCERTAIN it
  must state the specific missing information.
- Return one decision per item, for every item.
"""

PC_PROMPT = """You are auditing pairs of statements made by the SAME speaker in answer to
two different discussion questions.

Classify each pair with exactly one category:

- CONSISTENT: the two statements can both be true of the same person with no tension.
- POSITION_CHANGED_WITH_EXPLANATION: the speaker changes position and says why.
- CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY: the statements describe different situations,
  so differing content is not a contradiction.
- UNEXPLAINED_CONTRADICTION: the two statements cannot both be true of the same person
  and no explanation is offered.
- UNCERTAIN: the pair cannot be classified from what is supplied.

Rules:
- quote_a and quote_b MUST each be contiguous substrings of statement A and statement B
  respectively, and must not be paraphrased.
- turn_id_a and turn_id_b MUST be copied exactly from the item.
- Do not treat two statements about different situations as a contradiction.
- Do not attribute to this speaker anything said by anyone else.
- justification, minimum_context_used and what_would_resolve_uncertainty are required for
  every decision; for UNCERTAIN the last must state the specific missing information.
- Return one decision per item, for every item.
"""


# ---------------------------------------------------------------------- build
def build_hyper_exactness(turns):
    cand_keys = {(t["doc_id"], t["question"], t["turn"]) for t in turns
                 if any(p.search(t["text"]) for p in v1.PATTERNS.values())}
    cands = v1.hyper_exact_candidates(turns)
    ctls = v1.nondetected_controls(turns, cand_keys, per_condition=20)
    by_key = {(t["doc_id"], t["question"], t["turn"]): t for t in turns}

    items, sealed = [], {}
    for src, stratum in ((cands, "DETECTOR_PROPOSED_CANDIDATE"),
                         (ctls, "RANDOM_NONDETECTED_CONTROL_TURNS")):
        for c in src:
            t = by_key[(c["_doc_id"], c["_question"],
                        int(c["turn_id"][1:]))]
            ev = evidence(t)
            assert verify_literal(ev["quote"], t["text"])
            items.append({"item_id": c["item_id"], "speaker": c["speaker"], **ev})
            sealed[c["item_id"]] = {"_stratum": stratum, "_kind": "REAL_PILOT_CASE",
                                    "_doc_id": c["_doc_id"],
                                    "_question": c["_question"],
                                    "_condition": c["_condition"], "_fg": c["_fg"],
                                    "_replicate": c["_replicate"],
                                    "_detectors": c["detectors_fired"]}
    for fid, expected, text in HX_FIXTURES:
        t = _fixture_turn(text)
        ev = evidence(t)
        items.append({"item_id": fid, "speaker": "S00", **ev})
        sealed[fid] = {"_stratum": "TECHNICAL_VALIDATION_FIXTURE",
                       "_kind": "TECHNICAL_VALIDATION_FIXTURE",
                       "_expected_category": expected}
    return items, sealed, len(cands), len(ctls)


def build_consistency(turns):
    screened, hi_cut = screen_pairs(turns)
    selection, shortfalls, terciles = balanced_pilot(screened)

    items, sealed = [], {}
    for r in selection:
        iid = "PC2-" + _sha(f"pc2|{r['doc_id']}|{r['participant']}|"
                            f"{r['a']['turn']}|{r['b']['turn']}")[:16].upper()
        ea, eb = evidence(r["a"]), evidence(r["b"])
        assert verify_literal(ea["quote"], r["a"]["text"])
        assert verify_literal(eb["quote"], r["b"]["text"])
        items.append({"item_id": iid, "speaker": r["participant"].split("#")[-1],
                      "statement_a": ea, "statement_b": eb})
        sealed[iid] = {"_kind": "REAL_PILOT_CASE", "_role": r["role"],
                       "_stratum": r["stratum"], "_doc_id": r["doc_id"],
                       "_condition": r["condition"], "_fg": r["fg"],
                       "_replicate": r["replicate"],
                       "_topic_cosine": r["topic_cosine"],
                       "_topic_tercile": r["topic_tercile"],
                       "_polarity_contrast": r["polarity_contrast"],
                       "_n_shared_content_terms": r["n_shared_content_terms"]}
    for fid, expected, ta, tb in PC_FIXTURES:
        a, b = _fixture_turn(ta, 901, 2), _fixture_turn(tb, 902, 4)
        items.append({"item_id": fid, "speaker": "S00",
                      "statement_a": evidence(a), "statement_b": evidence(b)})
        sealed[fid] = {"_kind": "TECHNICAL_VALIDATION_FIXTURE",
                       "_expected_category": expected}
    return items, sealed, screened, hi_cut, shortfalls, terciles


def strata_counts(sealed, key, kinds=("REAL_PILOT_CASE",)):
    out = defaultdict(lambda: defaultdict(int))
    for v in sealed.values():
        if v.get("_kind") not in kinds:
            continue
        out[v.get(key, "?")][v.get("_condition", "?")] += 1
    return {k: dict(v) for k, v in out.items()}


def preflight() -> dict:
    turns = v1._turns()
    hx_items, hx_sealed, n_cand, n_ctl = build_hyper_exactness(turns)
    hx = build_manifests("HYPER_EXACTNESS", hx_items, 12, 1000, HX_PROMPT)

    pc_items, pc_sealed, screened, hi_cut, shortfalls, terciles = \
        build_consistency(turns)
    pc = build_manifests("PROFILE_CONSISTENCY", pc_items, 10, 1200, PC_PROMPT)

    role = strata_counts(pc_sealed, "_role")
    stratum = strata_counts(pc_sealed, "_stratum")
    hx_stratum = strata_counts(hx_sealed, "_stratum")

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "AGENT_FIDELITY_AUDIT_V2_PREFLIGHT",
        "supersedes": "agent_fidelity_audit_packages.json packaging",
        "model": MODEL, "effort": EFFORT, "n_repetitions": N_REPETITIONS,
        "evidence_rule": {
            "full_participant_turn_verbatim": True,
            "guide_question_included": True,
            "sentence_aligned_when_reduced": True,
            "context_window_supplied_separately": True,
            "never_cuts_a_word": True,
            "max_quote_words": MAX_QUOTE_WORDS,
            "hashes": ["source_turn_sha256", "presented_text_sha256"],
            "supersedes": "v1 character slice text[start-40:start+220]",
        },
        "hyper_exactness": {
            "n_detector_candidates": n_cand,
            "n_random_nondetected_controls": n_ctl,
            "n_real_items": n_cand + n_ctl,
            "n_fixtures": len(HX_FIXTURES),
            "n_items_total": len(hx_items),
            "by_stratum": hx_stratum,
            "n_full_turns_presented": sum(1 for i in hx_items if i["is_full_turn"]),
            "n_reduced_sentence_aligned": sum(1 for i in hx_items
                                              if not i["is_full_turn"]),
            "cost": hx["cost"],
            "repetition_rules": {
                "agreement_between_repetitions": "CORROBORATED",
                "disagreement": "UNRESOLVED",
                "one_repetition_UNCERTAIN": "NOT converted to absence",
                "non_literal_quote_or_wrong_speaker_or_invalid_turn_id": "GATE_FAILURE",
                "no_third_call": True, "no_confidence_or_majority_resolution": True},
            "fixtures_excluded_from_rates": True,
        },
        "profile_consistency": {
            "status": "PREPARED_NOT_AUTHORISED",
            "screener": {
                "retired_rule": "jaccard < 0.12",
                "why_retired": ("low vocabulary overlap mostly selects pairs about "
                                "DIFFERENT topics, which is the opposite of a "
                                "contradiction"),
                "requires": ["evidence of a common topic or referent",
                             "a possible contrast of position"],
                "topic_similarity": "word-level TF-IDF cosine within a document",
                "high_similarity_cutoff": hi_cut,
                "min_shared_content_terms": 3,
                "polarity_signals": ["negation", "high frequency", "change marker"],
                "embeddings_or_nli": "may propose, never decide",
                "strata": ["HIGH_TOPIC_SIMILARITY_WITH_POLARITY_CONTRAST",
                           "HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST",
                           "LOW_TOPIC_SIMILARITY_RANDOM_CONTROL"],
                "no_stratum_is_a_negative": True,
            },
            "n_screened_pairs": len(screened),
            "balanced_design": {"proposed_per_condition": 20,
                                "controls_per_condition": 20,
                                "total_per_condition": 40},
            "counts_by_role_and_condition": role,
            "counts_by_stratum_and_condition": stratum,
            "topic_tercile_bounds": terciles,
            "shortfalls": shortfalls,
            "balanced": not shortfalls,
            "n_real_pairs": sum(sum(v.values()) for v in role.values()),
            "n_fixtures": len(PC_FIXTURES),
            "n_items_total": len(pc_items),
            "cost": pc["cost"],
            "fixtures_excluded_from_rates": True,
        },
        "v1_denominator_correction": {
            "v1_pilot_proposed_by_condition": {"human": 15, "enriched": 15,
                                               "demographics-only": 30},
            "v1_pilot_controls_by_condition": {"human": 10, "enriched": 17,
                                               "demographics-only": 33},
            "v1_pilot_total_by_condition": {"human": 25, "enriched": 32,
                                            "demographics-only": 63},
            "what_v1_said_wrongly": ("the v1 report attributed the imbalance to the "
                                     "controls alone; the proposed pairs were also "
                                     "unbalanced at 15/15/30"),
        },
        "_hx": hx, "_hx_items": hx_items, "_hx_sealed": hx_sealed,
        "_pc": pc, "_pc_items": pc_items, "_pc_sealed": pc_sealed,
    }


def write(o: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    hx = o.pop("_hx"); hx_items = o.pop("_hx_items"); hx_sealed = o.pop("_hx_sealed")
    pc = o.pop("_pc"); pc_items = o.pop("_pc_items"); pc_sealed = o.pop("_pc_sealed")

    for tag, man, items, sealed, prompt in (
            ("hyper_exactness", hx, hx_items, hx_sealed, HX_PROMPT),
            ("profile_consistency", pc, pc_items, pc_sealed, PC_PROMPT)):
        (_OUT / f"v2_{tag}_items_blinded.json").write_text(
            json.dumps({"classification": man["classification"],
                        "categories": list(HX_CATEGORIES if tag == "hyper_exactness"
                                           else PC_CATEGORIES),
                        "prompt": prompt, "n_items": len(items), "items": items},
                       indent=1, ensure_ascii=False), encoding="utf-8")
        (_OUT / f"v2_{tag}_item_manifest.json").write_text(
            json.dumps({"n_rows": len(man["item_manifest"]),
                        "rows": man["item_manifest"]}, indent=1), encoding="utf-8")
        (_OUT / f"v2_{tag}_provider_request_manifest.json").write_text(
            json.dumps({"n_requests": len(man["provider_request_manifest"]),
                        "requests": man["provider_request_manifest"]},
                       indent=1), encoding="utf-8")
        (_OUT / f"v2_{tag}_sealed_reference.json").write_text(
            json.dumps(sealed, indent=1, ensure_ascii=False), encoding="utf-8")

    (_OUT / "v2_audit_preflight.json").write_text(
        json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")


class GateError(RuntimeError):
    pass


def _load_env() -> None:
    import os
    p = _ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def submission_gates() -> dict:
    """
    Hard preconditions. Any failure raises rather than submitting: a job sent on a
    manifest that does not reconcile cannot be interpreted afterwards.
    """
    items = json.loads((_OUT / "v2_hyper_exactness_items_blinded.json").read_text(
        encoding="utf-8"))["items"]
    im = json.loads((_OUT / "v2_hyper_exactness_item_manifest.json").read_text(
        encoding="utf-8"))["rows"]
    rm = json.loads((_OUT / "v2_hyper_exactness_provider_request_manifest.json")
                    .read_text(encoding="utf-8"))["requests"]
    sealed = json.loads((_OUT / "v2_hyper_exactness_sealed_reference.json").read_text(
        encoding="utf-8"))

    problems = []
    ids = {i["item_id"] for i in items}
    if len(items) != 137:
        problems.append(f"{len(items)} items, expected 137")
    real = {k for k, v in sealed.items() if v["_kind"] == "REAL_PILOT_CASE"}
    if len(real) != 127:
        problems.append(f"{len(real)} real items, expected 127")
    if sum(1 for r in im if r["item_id"] in real) != 254:
        problems.append("real adjudications != 254")
    if len(im) != 274:
        problems.append(f"{len(im)} adjudications, expected 274")
    if set(sealed) != ids:
        problems.append("sealed reference and payload disagree on item ids")

    covered = defaultdict(int)
    for r in rm:
        for iid in r["ordered_item_ids"]:
            covered[(iid, r["repetition_index"])] += 1
        if r["expected_item_count"] != len(r["ordered_item_ids"]):
            problems.append(f"{r['custom_id']}: expected_item_count mismatch")
    if covered != {(r["item_id"], r["repetition_index"]): 1 for r in im}:
        problems.append("provider requests do not cover the item manifest exactly")

    fixtures = {f[0] for f in HX_FIXTURES}
    if not fixtures <= ids:
        problems.append("fixtures missing from the payload")

    banned = ("macho_meals", "::", "demoonly", "run01", "run02", "run03",
              "demographics-only", "_stratum", "_kind", "_condition")
    blob = json.dumps(items)
    for tok in banned:
        if tok in blob:
            problems.append(f"blinding leak: {tok}")
    for it in items:
        if not verify_literal(it["quote"], it["quote"]) or \
                it["presented_text_sha256"] != _sha(it["quote"]):
            problems.append(f"{it['item_id']}: presented text hash mismatch")

    return {"n_items": len(items), "n_real": len(real), "n_adjudications": len(im),
            "n_real_adjudications": sum(1 for r in im if r["item_id"] in real),
            "n_provider_requests": len(rm), "n_fixtures": len(fixtures),
            "manifests_reconcile": not problems, "problems": problems}


def submit_hyper_exactness() -> dict:
    g = submission_gates()
    if g["problems"]:
        raise GateError("; ".join(g["problems"]))

    _load_env()
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    items = {i["item_id"]: i for i in json.loads(
        (_OUT / "v2_hyper_exactness_items_blinded.json").read_text(
            encoding="utf-8"))["items"]}
    rm = json.loads((_OUT / "v2_hyper_exactness_provider_request_manifest.json")
                    .read_text(encoding="utf-8"))["requests"]

    reqs = []
    for r in rm:
        payload = [items[i] for i in r["ordered_item_ids"]]
        body = (HX_PROMPT + "\n\nITEMS (" + str(len(payload)) + "):\n"
                + json.dumps(payload, ensure_ascii=False, indent=1))
        reqs.append(Request(
            custom_id=r["custom_id"],
            params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=r["max_output_tokens"],
                messages=[{"role": "user", "content": body}],
                output_config={"effort": EFFORT,
                               "format": {"type": "json_schema",
                                          "schema": SCHEMAS["HYPER_EXACTNESS"]}})))
    if len(reqs) != len(rm):
        raise GateError("request count drifted between manifest and submission")

    print(f"submitting HYPER_EXACTNESS: {len(reqs)} provider requests, "
          f"{g['n_adjudications']} adjudications, model {MODEL}, effort {EFFORT}")
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)

    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_id": batch.id, "classification": "HYPER_EXACTNESS",
           "processing_status": batch.processing_status,
           "n_provider_requests": len(reqs),
           "n_adjudications": g["n_adjudications"],
           "n_real_adjudications": g["n_real_adjudications"],
           "model": MODEL, "effort": EFFORT, "n_repetitions": N_REPETITIONS,
           "temperature_transmitted": False,
           "gates": g}
    (_OUT / "v2_hyper_exactness_job.json").write_text(
        json.dumps(rec, indent=1), encoding="utf-8")
    print("job id:", batch.id, " status:", batch.processing_status)
    return rec


def submit_profile_consistency() -> dict:
    """
    The authorised pilot: 120 real pairs + 8 fixtures, two repetitions, 256
    adjudications. The remaining corpus stays blocked behind the gate whatever the
    result.
    """
    items = {i["item_id"]: i for i in json.loads(
        (_OUT / "v2_profile_consistency_items_blinded.json").read_text(
            encoding="utf-8"))["items"]}
    rm = json.loads((_OUT / "v2_profile_consistency_provider_request_manifest.json")
                    .read_text(encoding="utf-8"))["requests"]
    im = json.loads((_OUT / "v2_profile_consistency_item_manifest.json").read_text(
        encoding="utf-8"))["rows"]
    sealed = json.loads((_OUT / "v2_profile_consistency_sealed_reference.json")
                        .read_text(encoding="utf-8"))

    problems = []
    real = {k for k, v in sealed.items() if v["_kind"] == "REAL_PILOT_CASE"}
    if len(real) != 120:
        problems.append(f"{len(real)} real pairs, expected 120")
    if len(items) != 128:
        problems.append(f"{len(items)} items, expected 128")
    if len(im) != 256:
        problems.append(f"{len(im)} adjudications, expected 256")
    covered = defaultdict(int)
    for r in rm:
        for iid in r["ordered_item_ids"]:
            covered[(iid, r["repetition_index"])] += 1
    if covered != {(r["item_id"], r["repetition_index"]): 1 for r in im}:
        problems.append("provider requests do not cover the item manifest exactly")
    blob = json.dumps(list(items.values()))
    for tok in ("macho_meals", "::", "demoonly", "run01", "demographics-only",
                "_stratum", "_kind", "_role", "SCREENER", "RANDOM_CONTROL"):
        if tok in blob:
            problems.append(f"blinding leak: {tok}")
    if problems:
        raise GateError("; ".join(problems))

    _load_env()
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    reqs = []
    for r in rm:
        payload = [items[i] for i in r["ordered_item_ids"]]
        body = (PC_PROMPT + "\n\nITEMS (" + str(len(payload)) + "):\n"
                + json.dumps(payload, ensure_ascii=False, indent=1))
        reqs.append(Request(
            custom_id=r["custom_id"],
            params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=r["max_output_tokens"],
                messages=[{"role": "user", "content": body}],
                output_config={"effort": EFFORT,
                               "format": {"type": "json_schema",
                                          "schema": SCHEMAS["PROFILE_CONSISTENCY"]}})))

    print(f"submitting PROFILE_CONSISTENCY pilot: {len(reqs)} provider requests, "
          f"{len(im)} adjudications")
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)
    rec = {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
           "classification": "PROFILE_CONSISTENCY_PILOT",
           "processing_status": batch.processing_status,
           "n_provider_requests": len(reqs), "n_adjudications": len(im),
           "n_real_pairs": len(real), "n_fixtures": len(items) - len(real),
           "model": MODEL, "effort": EFFORT,
           "max_output_tokens_range": [min(r["max_output_tokens"] for r in rm),
                                       max(r["max_output_tokens"] for r in rm)],
           "remaining_corpus_blocked_behind_the_gate": True}
    (_OUT / "v2_profile_consistency_job.json").write_text(
        json.dumps(rec, indent=1), encoding="utf-8")
    print("job id:", batch.id, batch.processing_status)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit-profile-consistency", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--submit-hyper-exactness", action="store_true")
    a = ap.parse_args()

    if a.gates:
        g = submission_gates()
        print(json.dumps(g, indent=1))
        return 0 if g["manifests_reconcile"] else 1
    if a.submit_hyper_exactness:
        submit_hyper_exactness()
        return 0
    if a.submit_profile_consistency:
        submit_profile_consistency()
        return 0
    o = preflight()
    hx, pc = o["hyper_exactness"], o["profile_consistency"]
    write(o)

    print("=== EVIDENCE ===")
    print(f"  full turns presented {hx['n_full_turns_presented']}   "
          f"sentence-aligned reductions {hx['n_reduced_sentence_aligned']}")
    print("\n=== HYPER-EXACTNESS ===")
    print(f"  {hx['n_detector_candidates']} candidates + "
          f"{hx['n_random_nondetected_controls']} controls = {hx['n_real_items']} real"
          f"   + {hx['n_fixtures']} fixtures = {hx['n_items_total']} items")
    c = hx["cost"]
    print(f"  {c['n_adjudications']} adjudications ({c['n_items']} x "
          f"{c['n_repetitions']})  ->  {c['n_provider_requests']} PROVIDER REQUESTS")
    print(f"  in {c['estimated_input_tokens']:,d} tok   out "
          f"{c['estimated_output_tokens']:,d} tok   USD {c['claude_batch_usd']:.2f}")

    print("\n=== PROFILE CONSISTENCY (prepared, not authorised) ===")
    print(f"  screened pairs {pc['n_screened_pairs']}   balanced {pc['balanced']}")
    for role, d in sorted(pc["counts_by_role_and_condition"].items()):
        print(f"    {role:10s} {d}")
    for st, d in sorted(pc["counts_by_stratum_and_condition"].items()):
        print(f"    {st:52s} {d}")
    if pc["shortfalls"]:
        print("  SHORTFALLS:", pc["shortfalls"])
    c = pc["cost"]
    print(f"  {c['n_adjudications']} adjudications  ->  "
          f"{c['n_provider_requests']} PROVIDER REQUESTS   "
          f"USD {c['claude_batch_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
