"""
Blinded cross-model audit of deductive absences — offline build.

STOPPING POINTS 1 AND 2 ONLY. This module derives the absence universe, renders the
blinded documents, builds the calibration and batch manifests and reports exact request
and token estimates. It makes NO API call. Nothing here modifies transcripts, evaluator
caches, human artefacts or existing results.

WHAT THIS IS
------------
An absence audit: can an independent model find transcript-grounded evidence that
contradicts an absence decision? It is not a new thematic analysis, and a corroborated
absence is not proof of absolute absence. The auditor never overwrites the original
coding; it produces a second opinion reconciled by a frozen rule.

The auditor is `claude-opus-5`. The original deductive coder was Gemini, so Gemini
cannot supply independent cross-model evidence and is not used here.

REQUEST SHAPE
-------------
Every request carries the FULL 11-code candidate set for its document, not only the
codes recorded as absent. Sending only the absent codes would give every production
request an all-absent structural signature and a candidate count varying from 1 to 10,
while calibration requests carried a mixture. Identical shape everywhere removes that
signature, and the 125 known-present cells become a concurrent-agreement control that
costs only output tokens.

    py scripts/absence_audit_build.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import absence_audit_rules as R  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_PE = _ROOT / "analysis/production_evaluation"
_RES = _PE / "results"
_OUT = _PE / "salience_absence_audit"
_CODEBOOK = _PE / "gold_standard_sealed/codebook_reference.csv"
_FROZEN = _PE / "frozen_evaluator_inputs.json"

_SEALED = _OUT / "sealed"

AUDITOR = {
    "model": "claude-opus-5",
    "execution_mode": "batch",
    "effort": "high",
    "structured_output": "output_config.format json_schema",
    "temperature_transmitted": False,
    "top_p_transmitted": False,
    "top_k_transmitted": False,
    "repetitions_per_request": 2,
    "repetition_semantics": ("two separately keyed stochastic repetitions of an "
                             "independent cross-model auditor; they share a model, "
                             "prompt, schema and rendering and differ only in the "
                             "repetition index, so they measure the stability of one "
                             "auditor and are not two independent auditors"),
    "cross_model_independence": ("claude-opus-5 is independent of Gemini, which "
                                 "produced the original coding; that is the "
                                 "independence this design claims"),
}

VERDICTS = ("EVIDENCE_FOUND", "NO_EVIDENCE_FOUND", "UNCERTAIN")
CONFIDENCE = ("LOW", "MEDIUM", "HIGH")

# --------------------------------------------------------------- blinding
#
# The check is SPLIT, because the two regions of a request have different authorship.
#
#   SCAFFOLD  — everything I author or assemble: system prompt, wrapper, candidate
#               blocks, codebook labels and definitions. Fully under my control, so it
#               takes the complete forbidden list.
#   VERBATIM  — the transcript exactly as the original evaluator received it. It cannot
#               be altered without destroying the thing being audited, and ordinary
#               English inevitably contains words like "missing", "error" and "reach"
#               ("missing out on nutrients", "more room for error"). It therefore takes
#               a hard-leak list only: terms that identify provenance or the original
#               coder and cannot occur innocuously in participant speech.
#
SCAFFOLD_FORBIDDEN = (
    "absent", "absence", "missed", "missing", "error", "validation", "validate",
    "original coder", "gemini", "claude", "anthropic", "recall", "precision",
    "salience", "reach", "enriched", "demographics-only", "demographics only",
    "synthetic", "human transcript", "replication", "replicate", "condition",
    "fg1", "fg2", "fg3", "fg4", "fg5", "run01", "run02", "run03", "run04",
    "macho_meals", "macho meals", "baseline", "agent", "persona",
)
HARD_LEAK_TERMS = (
    "fg1", "fg2", "fg3", "fg4", "fg5", "run01", "run02", "run03", "run04",
    "macho_meals", "gemini", "anthropic", "demographics-only", "original coder",
)

BLIND_SALT = "absence_audit_2026-08-03_v1"

# ---------------------------------------------------------- token model
#
# MEASURED, not assumed. Fitted by ordinary least squares over the 121 successful
# requests of batch msgbatch_01RgXvJrPHyUZfaTimUzw1Bf (claude_round1_results.json):
# same model, same execution mode, same effort, same corpus. Prompts were re-rendered
# from the stored job manifest and regressed on the recorded per-request input_tokens.
#
TOKEN_MODEL = {
    "input_tokens_per_word": 1.7502,
    "input_tokens_fixed_per_request": 1620,
    "r_squared": 0.9989,
    "fitted_over_words": [1135, 3387],
    "source_job": "msgbatch_01RgXvJrPHyUZfaTimUzw1Bf",
    "n_observations": 121,
    "caveat": ("this audit's prompts are roughly 8,300 words, well beyond the fitted "
               "range of 1,135-3,387, so the per-word slope is extrapolated; the fixed "
               "intercept also absorbs a response schema of a different size from the "
               "one used here. These are estimates with a stated band, not measurements."),
    "estimate_band_pct": 20,
}
# Verified 2026-08-02 against the published list Batch rates.
RATE_IN_PER_MTOK_USD = 2.50
RATE_OUT_PER_MTOK_USD = 12.50

# Mean measured output per structured assessment on the same corpus, rounded up for the
# richer schema used here (quotation plus reasoning for every candidate).
OUTPUT_TOKENS_PER_ASSESSMENT = 210


def _sha(x: str) -> str:
    return hashlib.sha256(x.encode("utf-8")).hexdigest()


def blind_id(doc_key: str) -> str:
    return "DOC_" + _sha(f"{BLIND_SALT}|{doc_key}")[:10].upper()


def _term_hits(text: str, terms) -> list[str]:
    """
    The boundary excludes alphanumerics only, NOT underscore. A leak arrives as
    `macho_meals_fg4_run01`, where every identifier is underscore-adjacent; a boundary
    that treated `_` as a word character would let exactly that case through.
    """
    low = " ".join(text.lower().split())
    return sorted({t for t in terms
                   if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low)})


def scaffold_purity_problems(text: str) -> list[str]:
    return [f"forbidden term in authored scaffolding: {t!r}"
            for t in _term_hits(text, SCAFFOLD_FORBIDDEN)]


def transcript_leak_problems(text: str) -> list[str]:
    return [f"hard provenance leak in verbatim transcript: {t!r}"
            for t in _term_hits(text, HARD_LEAK_TERMS)]


# ------------------------------------------------- public manifest purity
#
# The request manifest must be publishable beside the prompts without functioning as an
# answer key. These tokens would make it one.
#
ANSWER_KEY_TOKENS = ("original_status", "ORIGINAL_GEMINI", "SEALED", "reference_status",
                     "doc_key", "physical_run", "condition", "side", "provenance",
                     "present", "absence", "human::")


def public_manifest_problems(obj) -> list[str]:
    """A public manifest that contains any answer-key token is not public."""
    blob = json.dumps(obj, ensure_ascii=False)
    bad = []
    for t in ANSWER_KEY_TOKENS:
        if t in blob:
            bad.append(f"answer-key token in public manifest: {t!r}")
    return sorted(set(bad))


# --------------------------------------------------- repetition language
#
# Claude is independent of Gemini; its two repetitions are not independent auditors.
# Any phrasing that says otherwise overstates the design and is banned from every
# artefact and every document.
#
BANNED_REPETITION_PHRASES = (
    "two independent repetitions", "independent repetitions",
    "independently repeated", "independent repetition",
    "two independent runs", "independent replicates of the auditor",
)
REPETITION_PHRASE = ("two separately keyed stochastic repetitions of an independent "
                     "cross-model auditor")


def repetition_language_problems(text: str) -> list[str]:
    low = " ".join(text.lower().split())
    return sorted({f"overstated repetition independence: {p!r}"
                   for p in BANNED_REPETITION_PHRASES if p in low})


# --------------------------------------------------- per-cell overclaiming
#
# The detection rate is a property of the instrument. It licenses or withholds a
# corroboration LABEL; it says nothing about whether any individual non-detection is a
# miss or a true absence. Deciding that would require knowing how many absences are
# genuinely contestable — the unknown the audit exists to bound. These phrasings assert
# it anyway and are banned from every artefact and document.
#
BANNED_PER_CELL_CLAIMS = (
    "more likely a miss than a true absence", "more likely a miss than an absence",
    "more likely to be a miss", "probably a miss", "the corroboration reverses sign",
    "reverses sign",
)


def per_cell_overclaim_problems(text: str) -> list[str]:
    low = " ".join(text.lower().split())
    return sorted({f"unsupported per-cell claim: {p!r}"
                   for p in BANNED_PER_CELL_CLAIMS if p in low})


# ------------------------------------------------------------- codebook
def codebook() -> dict:
    with _CODEBOOK.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["subtheme_id"]: {"subtheme_id": r["subtheme_id"],
                               "label": r["subtheme_label"],
                               "parent_theme": r["theme"],
                               "definition": r["description"],
                               "example": r["example"]} for r in rows}


# ------------------------------------------------------------ documents
def documents() -> list[dict]:
    """The 35 frozen evaluator inputs, with a stable document key."""
    j = json.loads(_FROZEN.read_text(encoding="utf-8"))
    docs = []
    for r in j["human_inputs"]:
        docs.append({"doc_key": f"human::{r['fg']}", "side": "human",
                     "condition": "human", "fg": r["fg"],
                     "canonical_replication_index": None, "physical_run": None,
                     "path": r["path"], "sha256": r["sha256"]})
    for r in j["synthetic_inputs"]:
        docs.append({"doc_key": r["physical_run"], "side": "synthetic",
                     "condition": r["condition"], "fg": r["fg"],
                     "canonical_replication_index": r["canonical_replication_index"],
                     "physical_run": r["physical_run"],
                     "path": r["path"], "sha256": r["sha256"]})
    return docs


def render_blinded(doc: dict) -> dict:
    """
    The transcript as the original evaluator received it, with speaker labels
    pseudonymised to P1..Pn and turn ids exposed so a quotation can be verified against
    an exact turn. Utterance text is copied byte-for-byte apart from whitespace
    normalisation; it is never edited.
    """
    raw = (_ROOT / doc["path"]).read_bytes()
    obj = json.loads(raw.decode("utf-8"))
    entries = obj if isinstance(obj, list) else obj["transcript"]
    speakers, lines, turns = {}, [], {}
    for e in entries:
        sid = e.get("canonical_speaker_id") or e.get("speaker_id")
        is_mod = (sid == "MODERATOR" or e.get("speaker_role") == "moderator")
        if is_mod:
            name = "Moderator"
        else:
            if sid not in speakers:
                speakers[sid] = f"P{len(speakers) + 1}"
            name = speakers[sid]
        tid = f"T{int(e['turn']):03d}"
        text = " ".join(e["content"].split())
        lines.append(f"[{tid}] {name}: {text}")
        turns.setdefault(tid, []).append({"speaker": name, "text": text,
                                          "is_moderator": is_mod})
    return {"text": "\n".join(lines), "turns": turns, "speaker_map": speakers,
            "n_turns": len(turns), "n_participants": len(speakers),
            "source_sha256": hashlib.sha256(raw).hexdigest()}


# ------------------------------------------------- presence grid + universe
def presence_grid() -> dict:
    """(doc_key, subtheme_id) -> True where present AND quote-verified."""
    pres = list(csv.DictReader(
        (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8")))
    grid = {}
    for r in pres:
        k = f"human::{r['fg']}" if r["side"] == "human" else r["physical_run"]
        grid[(k, r["subtheme_id"])] = (r["present"] == "True"
                                       and r["quote_verified"] == "True")
    return grid


def absence_universe() -> dict:
    """
    DERIVED, never hard-coded:
        35 documents x 11 subthemes - 125 verified-present instances
    Fails loudly if the arithmetic does not reconcile against the source table.
    """
    cb, grid = codebook(), presence_grid()
    codes = sorted(cb)
    docs = {d["doc_key"]: d for d in documents()}

    problems = []
    for (k, c) in grid:
        if k not in docs:
            problems.append(f"presence row for unknown document {k}")
        if c not in cb:
            problems.append(f"presence row for unknown subtheme {c}")

    n_docs, n_codes = len(docs), len(codes)
    expected_cells = n_docs * n_codes
    if len(grid) != expected_cells:
        problems.append(f"grid has {len(grid)} cells, expected {expected_cells}")
    missing = [(k, c) for k in docs for c in codes if (k, c) not in grid]
    if missing:
        problems.append(f"{len(missing)} grid cells absent from the source table")

    present = sum(1 for v in grid.values() if v)
    derived = expected_cells - present

    rows = []
    for k, d in sorted(docs.items()):
        for c in codes:
            if grid.get((k, c)) is False:
                rows.append({"doc_key": k, "blinded_document_id": blind_id(k),
                             "subtheme_id": c, "subtheme_label": cb[c]["label"],
                             "side": d["side"], "condition": d["condition"],
                             "fg": d["fg"],
                             "canonical_replication_index":
                                 d["canonical_replication_index"] or "",
                             "physical_run": d["physical_run"] or ""})
    if len(rows) != derived:
        problems.append(f"universe rows {len(rows)} != derived {derived}")

    return {
        "n_documents": n_docs, "n_subthemes": n_codes, "n_cells": expected_cells,
        "n_verified_present": present,
        "n_absence_decisions_derived": derived,
        "derivation": (f"{n_docs} documents x {n_codes} subthemes "
                       f"- {present} verified-present instances = {derived}"),
        "hard_coded": False,
        "reconciliation_rule": ("every figure recomputed from "
                                "results/thematic_code_presence_long.csv at build time; "
                                "a mismatch aborts the build"),
        "rows": rows, "problems": problems, "pass": not problems,
    }


# ------------------------------------------------------------- prompting
SYSTEM_PROMPT = """\
You are assessing a transcript of a group discussion against a candidate coding set.

For EACH candidate code you receive, decide whether the transcript contains a passage \
that satisfies that code's complete definition, and return exactly one verdict:

  EVIDENCE_FOUND     the transcript contains a passage satisfying the full definition
  NO_EVIDENCE_FOUND  you reviewed the whole transcript and found no such passage
  UNCERTAIN          a passage is arguably relevant but you cannot decide

Rules:
  * For EVIDENCE_FOUND you must supply the exact turn_id, the exact speaker label as it \
appears in the transcript, a short VERBATIM quotation copied character-for-character \
from that turn, and an explanation of how the quotation satisfies the COMPLETE \
definition rather than merely sharing vocabulary with it. Also give a confidence of \
LOW, MEDIUM or HIGH.
  * A quotation attributed to the Moderator is never acceptable as evidence. The \
moderator's questions introduce topics; only participant speech can express a code.
  * For UNCERTAIN, give the candidate turn and quotation if one exists, and state \
precisely what prevents a decision.
  * For NO_EVIDENCE_FOUND, confirm briefly that you reviewed the entire transcript. Do \
not invent a quotation.
  * Never guess a turn_id and never reconstruct a quotation from memory. If you cannot \
copy it exactly as printed, return UNCERTAIN and say so.
  * Judge each candidate code independently and against its own definition. Some \
candidates are closely related; a passage satisfying a neighbouring definition does \
not satisfy this one.
  * Assess every candidate you are given. Return one entry per candidate, no more and \
no fewer.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_id", "assessments"],
    "properties": {
        "document_id": {"type": "string"},
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code_id", "verdict", "reasoning"],
                "properties": {
                    "code_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "turn_id": {"type": "string"},
                    "speaker": {"type": "string"},
                    "quotation": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "confidence": {"type": "string", "enum": list(CONFIDENCE)},
                },
            },
        },
    },
}


def candidate_order(doc_key: str, code_ids) -> list[str]:
    """Deterministic per-document shuffle, so codebook order carries no signal."""
    return sorted(code_ids, key=lambda c: _sha(f"{BLIND_SALT}|order|{doc_key}|{c}"))


def render_request(doc: dict, rendered: dict, code_ids, cb: dict):
    """Returns (scaffold_only, full_body, candidate_order)."""
    order = candidate_order(doc["doc_key"], code_ids)
    blocks = []
    for i, c in enumerate(order, start=1):
        d = cb[c]
        blocks.append(f"CANDIDATE {i}\n"
                      f"  code_id    : {d['subtheme_id']}\n"
                      f"  label      : {d['label']}\n"
                      f"  definition : {d['definition']}")
    header = f"DOCUMENT ID: {blind_id(doc['doc_key'])}\n\nTRANSCRIPT\n\n"
    footer = ("\n\n" + "-" * 60 + "\n\nCANDIDATE CODING SET REQUIRING ASSESSMENT\n"
              f"({len(order)} candidates)\n\n" + "\n\n".join(blocks))
    scaffold = SYSTEM_PROMPT + "\n" + header + footer
    return scaffold, header + rendered["text"] + footer, order


def cache_key(stage: str, doc_key: str, code_set, rendered_sha: str,
              prompt_sha: str, schema_sha: str, rep: int) -> str:
    return _sha("|".join([
        "BLINDED_ABSENCE_AUDIT", stage, blind_id(doc_key),
        rendered_sha, _sha("|".join(candidate_order(doc_key, code_set))),
        prompt_sha, schema_sha,
        AUDITOR["model"], AUDITOR["effort"], AUDITOR["execution_mode"], str(rep)]))


# ------------------------------------------------------------ render store
#
# THE BLINDING BOUNDARY. Everything above this line may touch provenance; everything
# below it is keyed by opaque document id alone. `render_store` is the only privileged
# step: it reads the frozen inputs by path and returns a structure whose keys and
# contents carry no provenance. The request builder consumes the store and the public
# manifest, and has no parameter, no import and no path by which it could read the
# sealed reference file.
#
def render_store(cb: dict, codes) -> dict:
    store = {}
    for d in documents():
        rend = render_blinded(d)
        scaffold, body, order = render_request(d, rend, codes, cb)
        bid = blind_id(d["doc_key"])
        store[bid] = {
            "blinded_document_id": bid, "body": body, "scaffold": scaffold,
            "turns": rend["turns"], "candidate_order": order,
            "n_turns": rend["n_turns"], "n_participants": rend["n_participants"],
            "prompt_words": len(body.split()), "prompt_chars": len(body),
            "rendered_sha256": _sha(body), "source_sha256": rend["source_sha256"],
        }
    return store


# ---------------------------------------------------------- calibration
ORIGINAL_PRESENT = "ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED"
ORIGINAL_ABSENCE = "ORIGINAL_GEMINI_ABSENCE"
_ADJACENT = {"A.1", "A.2", "A.3", "B.1", "B.2", "B.3", "B.4", "C.1", "C.2", "C.3"}


def calibration_selection(cb: dict) -> dict:
    """
    PRIVILEGED SELECTION STEP. One originally-present and one originally-absent cell per
    subtheme where available, balanced across the human and synthetic sides.

    Neither label is ground truth. ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED cells carry a
    quotation the original coder localised and that was verified verbatim, which makes
    them a usable positive control. ORIGINAL_GEMINI_ABSENCE cells carry no such warrant:
    they are the original coder's decisions and are the thing under audit, so they are
    not called known negatives anywhere.

    The status produced here is written ONLY to the sealed reference file.
    """
    grid = presence_grid()
    docs = {d["doc_key"]: d for d in documents()}
    pos, neg = {}, {}
    for (k, c), ok in sorted(grid.items()):
        (pos if ok else neg).setdefault(c, []).append(k)

    cases = []
    for c in sorted(cb):
        for kind, pool in ((ORIGINAL_PRESENT, pos.get(c, [])),
                           (ORIGINAL_ABSENCE, neg.get(c, []))):
            if not pool:
                continue
            hum = [k for k in pool if k.startswith("human::")]
            syn = [k for k in pool if not k.startswith("human::")]
            prefer = hum if (kind == ORIGINAL_PRESENT and hum) else (syn or hum)
            pick = sorted(prefer, key=lambda k: _sha(f"{BLIND_SALT}|cal|{c}|{k}"))[0]
            cases.append({"case_id": f"CAL::{c}::{kind}", "doc_key": pick,
                          "blinded_document_id": blind_id(pick), "subtheme_id": c,
                          "original_status": kind, "side": docs[pick]["side"],
                          "adjacent_code_family": c in _ADJACENT})
    return {"cases": cases, "doc_keys": sorted({c["doc_key"] for c in cases})}


def split_calibration(cal: dict, store: dict, codes) -> tuple[dict, dict]:
    """
    Splits the selection into a PUBLIC request manifest and a SEALED reference file.

    The public half carries opaque ids, hashes and request metadata only: no document
    key, no side, no original status, no subtheme-to-status association. The sealed half
    carries everything the public half must not.
    """
    cal_ids = sorted({c["blinded_document_id"] for c in cal["cases"]})
    public = {
        "classification": "ABSENCE_AUDIT_CALIBRATION_REQUEST_MANIFEST",
        "stage": "STAGE1_CALIBRATION",
        "contains": "opaque identifiers, hashes and request metadata only",
        "excludes": ("every field that could identify a source document, its origin, or "
                     "the original coder's decision; this file is not an answer key and "
                     "a purity check asserts it cannot become one"),
        "n_documents": len(cal_ids),
        "n_candidates_per_document": len(codes),
        "n_cells_returned": len(cal_ids) * len(codes),
        "repetitions_per_request": AUDITOR["repetitions_per_request"],
        "repetition_semantics": AUDITOR["repetition_semantics"],
        "documents": [{"blinded_document_id": b,
                       "rendered_sha256": store[b]["rendered_sha256"],
                       "candidate_order": store[b]["candidate_order"],
                       "n_turns": store[b]["n_turns"],
                       "n_participants": store[b]["n_participants"],
                       "prompt_words": store[b]["prompt_words"]}
                      for b in cal_ids],
    }
    sealed = {
        "WARNING": ("SEALED. Original coder status, provenance and document keys. "
                    "Never transmitted, and never read by the request builder."),
        "classification": "ABSENCE_AUDIT_CALIBRATION_REFERENCE_SEALED",
        "labels": {
            ORIGINAL_PRESENT: ("the original coder localised a quotation that was "
                               "verified verbatim; a usable positive control"),
            ORIGINAL_ABSENCE: ("the original coder's absence decision; NOT a known "
                               "negative and NOT ground truth, since it is the thing "
                               "under audit"),
        },
        "n_designated_cases": len(cal["cases"]),
        "cases": cal["cases"],
    }
    return public, sealed


# THE REQUEST BUILDER follows. It consumes opaque rows and the render store, nothing
# else — no parameter, no import and no path by which the answer key could be read. The
# function body below is deliberately free even of the words naming that file, so a test
# can inspect its source and assert the independence structurally. A second test removes
# the sealed directory and asserts requests still build.
def build_requests(public_documents, store: dict, stage_of, prompt_sha: str,
                   schema_sha: str, codes) -> list[dict]:
    """Build one request per opaque document id. Opaque inputs only."""
    out = []
    for row in public_documents:
        bid = row["blinded_document_id"]
        s = store[bid]
        stage = stage_of(bid)
        out.append({
            "blinded_document_id": bid, "stage": stage,
            "n_candidates": len(s["candidate_order"]),
            "candidate_order": s["candidate_order"],
            "n_turns": s["n_turns"], "n_participants": s["n_participants"],
            "prompt_words": s["prompt_words"], "prompt_chars": s["prompt_chars"],
            "rendered_sha256": s["rendered_sha256"],
            "source_sha256": s["source_sha256"],
            "estimated_input_tokens": round(
                s["prompt_words"] * TOKEN_MODEL["input_tokens_per_word"]
                + TOKEN_MODEL["input_tokens_fixed_per_request"]),
            "cache_keys": {str(rep): _sha("|".join([
                "BLINDED_ABSENCE_AUDIT", stage, bid, s["rendered_sha256"],
                _sha("|".join(s["candidate_order"])), prompt_sha, schema_sha,
                AUDITOR["model"], AUDITOR["effort"], AUDITOR["execution_mode"],
                str(rep)])) for rep in (1, 2)},
        })
    return out


def stage1_gate_specification(cal_doc_keys, codes) -> dict:
    """
    The exact Stage-1 gate, resolved to integer counts BEFORE submission.

    The denominator is every originally-present quote-verified cell the Stage-1
    documents return, not the 11 designated present cases. With n = 11 a flawless 11/11
    yields a Wilson lower bound of 0.7412, so a gate stated on the designated set alone
    could not reach THRESHOLD_A under any performance at all. That is a property of the
    interval at n = 11, not of the auditor, and it is why the denominator is stated here
    rather than assumed.
    """
    grid = presence_grid()
    n_cells = len(cal_doc_keys) * len(codes)
    n_present = sum(1 for k in cal_doc_keys for c in codes if grid[(k, c)])
    n_absence = n_cells - n_present

    k_a_det = R.min_k_for_lower_bound(n_present, R.THRESHOLD_A)
    k_b_det = R.min_k_for_lower_bound(n_present, R.THRESHOLD_B)
    k_a_stab = R.min_k_for_lower_bound(n_cells, R.THRESHOLD_A)
    k_b_stab = R.min_k_for_lower_bound(n_cells, R.THRESHOLD_B)
    max_unres = max((u for u in range(n_cells + 1)
                     if R.wilson(u, n_cells)["upper"] <= R.MAX_UNRESOLVED_UPPER_A),
                    default=None)

    return {
        "frozen_before_submission": True,
        "denominator_rule": R.GATE_DENOMINATOR_RULE,
        "n_stage1_documents": len(cal_doc_keys),
        "n_cells_returned": n_cells,
        "n_original_present_quote_verified": n_present,
        "n_original_gemini_absence": n_absence,
        "thresholds": {
            "THRESHOLD_A": R.THRESHOLD_A,
            "THRESHOLD_A_derivation": (
                "1/1.20. The audit estimates how many of the 260 absences are "
                "contestable. If the auditor detects a fraction s of demonstrably "
                "locatable evidence, an observed count C of contested cells implies "
                "about C/s contestable absences. A declared tolerance that this "
                "inflation may not exceed 20% gives 1/1.20 = 0.8333 on the lower bound. "
                "The 20% tolerance is a stipulated choice declared in advance; the "
                "threshold follows from it arithmetically. No 0.80 convention is used."),
            "THRESHOLD_B": R.THRESHOLD_B,
            "THRESHOLD_B_derivation": (
                "a property of the instrument, not of any cell. Below one half the "
                "auditor fails to detect more known-localisable positive controls than "
                "it detects, and an instrument in that state produces non-detections "
                "carrying too little information to license a corroboration label of "
                "any kind. Detections are unaffected: a gate-passed quotation is "
                "verified against the transcript itself."),
            "THRESHOLD_B_makes_no_per_cell_claim": (
                "no statement is made about whether any individual "
                "AUDITOR_DID_NOT_FIND_EVIDENCE is a miss or a true absence; that would "
                "require knowing how many absences are genuinely contestable, which is "
                "the unknown this audit exists to bound and cannot assume"),
            "MAX_UNRESOLVED_UPPER_A": R.MAX_UNRESOLVED_UPPER_A,
            "interval": "Wilson score, z = 1.96",
            "interval_status": R.WILSON_CAVEAT,
        },
        "exact_gate": {
            "band_a_requires": {
                "detected_on_original_present_at_least": k_a_det,
                "of": n_present,
                "repetition_agreement_at_least": k_a_stab, "of_cells": n_cells,
                "unresolved_at_most": max_unres,
                "outcome": R.GATE_A,
                "permits": R.ABSENCE_CORROBORATED,
                "NECESSARY_BUT_NOT_SUFFICIENT": (
                    "band A alone does not license ABSENCE_CORROBORATED for any cell; "
                    "the subtheme eligibility rule must also be satisfied"),
            },
            "band_b_requires": {
                "detected_on_original_present_at_least": k_b_det,
                "of": n_present,
                "repetition_agreement_at_least": k_b_stab, "of_cells": n_cells,
                "and_band_a_not_met": True,
                "outcome": R.GATE_B,
                "permits_only": R.AUD_NONE,
                "forbids": [R.ABSENCE_CORROBORATED],
            },
            "band_c_otherwise": {
                "outcome": R.GATE_C,
                "consequence": ("Stage 2 is not submitted; the calibration failure is "
                                "the reported result and no absence figure is revised"),
            },
        },
        "subtheme_eligibility_rule": {
            "applies_to": R.ABSENCE_CORROBORATED,
            "requires_both": [
                "the global gate reaches " + R.GATE_A,
                ("the auditor detected the designated "
                 f"{R.ORIGINAL_PRESENT} control for that same subtheme, under the "
                 "reconciled two-repetition rule"),
            ],
            "otherwise": ("every non-detection for that subtheme remains "
                          f"{R.AUD_NONE}, even under a global {R.GATE_A}"),
            "contested_cells_unaffected": (
                "a valid contested absence with gate-passed evidence remains "
                "contestable regardless of this rule, because it is verified against "
                "the transcript rather than against the auditor"),
            "why": ("a global pass shows the auditor works across the codebook, not "
                    "that it can recognise any particular subtheme; without this rule "
                    "an auditor blind to one definition would corroborate every "
                    "absence for that definition"),
            "n_designated_controls": 11,
            "one_control_per_subtheme": True,
        },
        "max_achievable_lower_bound_on_designated_present_only":
            R.wilson(11, 11)["lower"],
        "why_designated_set_is_not_the_denominator": (
            f"a flawless 11/11 on the designated present cases yields a Wilson lower "
            f"bound of {R.wilson(11, 11)['lower']}, below THRESHOLD_A "
            f"({R.THRESHOLD_A}); the designated cases guarantee balanced subtheme "
            "coverage and are reported separately"),
    }


def build() -> dict:
    cb = codebook()
    codes = sorted(cb)
    uni = absence_universe()
    prompt_sha = _sha(SYSTEM_PROMPT)
    schema_sha = _sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))
    cal = calibration_selection(cb)
    cal_docs = set(cal["doc_keys"])
    store = render_store(cb, codes)

    absences_by_doc = {}
    for r in uni["rows"]:
        absences_by_doc[r["doc_key"]] = absences_by_doc.get(r["doc_key"], 0) + 1

    scaffold_fail, leak_fail = [], []
    for d in documents():
        bid = blind_id(d["doc_key"])
        if bad := scaffold_purity_problems(store[bid]["scaffold"]):
            scaffold_fail.append({"doc": bid, "problems": bad})
        body = store[bid]["body"]
        transcript_only = body[body.index("TRANSCRIPT\n\n"):]
        if lk := transcript_leak_problems(transcript_only):
            leak_fail.append({"doc": bid, "problems": lk})

    stage1_ids = {blind_id(k) for k in cal_docs}
    public_docs = [{"blinded_document_id": blind_id(d["doc_key"])} for d in documents()]
    reqs = build_requests(
        public_docs, store,
        lambda bid: "STAGE1_CALIBRATION" if bid in stage1_ids else "STAGE2_COMPLETE",
        prompt_sha, schema_sha, codes)

    # absence / control counts are analysis metadata, attached after the blind build
    by_bid = {blind_id(k): v for k, v in absences_by_doc.items()}
    for r in reqs:
        n_abs = by_bid.get(r["blinded_document_id"], 0)
        r["n_absence_cells"] = n_abs
        r["n_present_control_cells"] = len(codes) - n_abs

    reps = AUDITOR["repetitions_per_request"]
    band = TOKEN_MODEL["estimate_band_pct"] / 100

    def size(group):
        tin = sum(r["estimated_input_tokens"] for r in group) * reps
        n_ass = sum(r["n_candidates"] for r in group) * reps
        tout = n_ass * OUTPUT_TOKENS_PER_ASSESSMENT
        cost = tin / 1e6 * RATE_IN_PER_MTOK_USD + tout / 1e6 * RATE_OUT_PER_MTOK_USD
        return {"n_documents": len(group), "n_requests": len(group) * reps,
                "n_assessments": n_ass,
                "n_absence_cells": sum(r["n_absence_cells"] for r in group),
                "n_present_control_cells": sum(r["n_present_control_cells"]
                                               for r in group),
                "estimated_input_tokens": tin, "estimated_output_tokens": tout,
                "estimated_input_tokens_band": [round(tin * (1 - band)),
                                                round(tin * (1 + band))],
                "calculated_list_batch_cost_usd": round(cost, 2),
                "calculated_list_batch_cost_band_usd": [round(cost * (1 - band), 2),
                                                        round(cost * (1 + band), 2)]}

    s1 = [r for r in reqs if r["stage"] == "STAGE1_CALIBRATION"]
    s2 = [r for r in reqs if r["stage"] == "STAGE2_COMPLETE"]
    all_keys = [k for r in reqs for k in r["cache_keys"].values()]

    manifest = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": "BLINDED_CROSS_MODEL_ABSENCE_AUDIT",
        "status": "PRE_SUBMISSION_NO_API_CALL_MADE",
        "purpose": ("determine whether an independent model finds transcript-grounded "
                    "evidence contradicting an absence decision"),
        "is_not": ["a new thematic analysis", "proof of absolute absence",
                   "a replacement for the original coding"],
        "auditor": AUDITOR,
        "auditor_rationale": ("the original deductive coder was Gemini, so Gemini cannot "
                              "supply independent cross-model evidence"),
        "stage1_gate": stage1_gate_specification(sorted(cal_docs), codes),
        "universe": {k: uni[k] for k in
                     ("n_documents", "n_subthemes", "n_cells", "n_verified_present",
                      "n_absence_decisions_derived", "derivation", "hard_coded",
                      "reconciliation_rule")},
        "request_shape": {
            "candidates_per_request": len(codes),
            "rule": "the full codebook is sent for every document",
            "why": ("sending only the absent codes would give every production request "
                    "an all-absent structural signature and a candidate count varying "
                    "from 1 to 10, while calibration requests carried a mixture"),
            "present_cells_become": ("a concurrence control, "
                                     f"{uni['n_verified_present']} cells"),
        },
        "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
        "cache_key_inputs": ["classification", "stage", "blinded_document_id",
                             "rendered_document_sha256", "candidate_code_set_sha256",
                             "prompt_sha256", "schema_sha256", "model", "effort",
                             "execution_mode", "repetition_index"],
        "cache_key_collisions": len(all_keys) - len(set(all_keys)),
        "blinding": {
            "check": "SPLIT",
            "scaffold_rule": ("full forbidden list over the system prompt, wrapper and "
                              "candidate blocks"),
            "verbatim_rule": ("hard provenance leaks only inside transcript text, which "
                              "cannot be altered without destroying what is audited"),
            "scaffold_terms_checked": len(SCAFFOLD_FORBIDDEN),
            "hard_leak_terms_checked": len(HARD_LEAK_TERMS),
            "scaffold_failures": scaffold_fail,
            "verbatim_leak_failures": leak_fail,
            "opaque_document_ids": True,
            "speakers_pseudonymised": "P1..Pn; the moderator is labelled Moderator",
            "sealed_files": ["sealed/sealed_document_mapping.json",
                             "sealed/calibration_reference_SEALED.json"],
            "request_builder_reads_sealed_files": False,
            "request_builder_note": ("build_requests() consumes the public manifest and "
                                     "the render store only; it has no parameter, no "
                                     "import and no path by which a sealed file could "
                                     "be read"),
            "not_transmitted": ["provenance", "condition", "focus-group identity",
                                "replication index", "original coder decisions",
                                "original status of calibration cells",
                                "existing reach, recall, precision or hierarchy results"],
            "candidate_order": "randomised deterministically per document",
            "residual_risk": ("participant first names occasionally occur inside "
                              "utterances; they identify no condition and the auditor "
                              "holds no reference set against which to match them"),
        },
        "token_model": TOKEN_MODEL,
        "rates": {"input_per_mtok_usd": RATE_IN_PER_MTOK_USD,
                  "output_per_mtok_usd": RATE_OUT_PER_MTOK_USD,
                  "verified_utc": "2026-08-02",
                  "IMPORTANT": ("cost CALCULATED at published list Batch rates from "
                                "estimated token counts; not necessarily the amount "
                                "charged. No Gemini rate is quoted anywhere in this "
                                "audit because none has been verified.")},
        "stage_1_calibration": size(s1), "stage_2_incremental": size(s2),
        "total_corpus": size(reqs),
        "stage_2_note": ("Stage 1 documents are not re-sent. Their requests would be "
                         "byte-identical, so the cache key matches and the stored result "
                         "is reused."),
        "requests": reqs,
    }
    return {"manifest": manifest, "universe": uni, "calibration": cal,
            "codes": codes, "codebook": cb}


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    b = build()
    uni, m, cal, codes = b["universe"], b["manifest"], b["calibration"], b["codes"]

    print("=== stopping point 1: absence universe (derived from source) ===")
    print("  " + uni["derivation"])
    print(f"  reconciles: {uni['pass']}")
    for p in uni["problems"]:
        print("   PROBLEM:", p)
    if not uni["pass"]:
        return 1

    (_OUT / "batch_manifest.json").write_text(
        json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")

    with (_OUT / "absence_universe.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(uni["rows"][0]))
        w.writeheader()
        w.writerows(uni["rows"])

    _SEALED.mkdir(parents=True, exist_ok=True)
    store = render_store(b["codebook"], codes)
    public, sealed_ref = split_calibration(cal, store, codes)
    (_OUT / "calibration_request_manifest.json").write_text(
        json.dumps(public, indent=1, ensure_ascii=False), encoding="utf-8")
    (_SEALED / "calibration_reference_SEALED.json").write_text(
        json.dumps(sealed_ref, indent=1, ensure_ascii=False), encoding="utf-8")

    sealed_map = {"WARNING": ("SEALED. Provenance mapping. Never transmitted, and never "
                              "read by the request builder."),
                  "blind_salt": BLIND_SALT,
                  "mapping": {blind_id(d["doc_key"]): {k: d[k] for k in
                              ("doc_key", "side", "condition", "fg",
                               "canonical_replication_index", "physical_run", "sha256")}
                              for d in documents()}}
    (_SEALED / "sealed_document_mapping.json").write_text(
        json.dumps(sealed_map, indent=1, ensure_ascii=False), encoding="utf-8")

    (_OUT / "stage1_gate.json").write_text(
        json.dumps(m["stage1_gate"], indent=1, ensure_ascii=False), encoding="utf-8")

    # supersede the pre-split artefacts so no stale answer key survives beside the split
    for stale in ("calibration_manifest.json", "sealed_document_mapping.json"):
        (_OUT / stale).unlink(missing_ok=True)

    bl = m["blinding"]
    print("\n=== stopping point 2: blinding (split check) ===")
    print(f"  authored scaffolding failures : {len(bl['scaffold_failures'])}"
          f"  ({bl['scaffold_terms_checked']} terms)")
    print(f"  verbatim hard leaks           : {len(bl['verbatim_leak_failures'])}"
          f"  ({bl['hard_leak_terms_checked']} terms)")
    print(f"  cache key collisions          : {m['cache_key_collisions']}")

    print("\n=== requests and estimates — NO API CALL MADE ===")
    for nm, g in (("stage 1 calibration", m["stage_1_calibration"]),
                  ("stage 2 incremental", m["stage_2_incremental"]),
                  ("TOTAL corpus", m["total_corpus"])):
        print(f"  {nm:20s} docs {g['n_documents']:2d}  requests {g['n_requests']:3d}  "
              f"assessments {g['n_assessments']:4d}  "
              f"in {g['estimated_input_tokens']:>9,}  "
              f"out {g['estimated_output_tokens']:>7,}  "
              f"${g['calculated_list_batch_cost_usd']:>6.2f}  "
              f"band ${g['calculated_list_batch_cost_band_usd'][0]}-"
              f"{g['calculated_list_batch_cost_band_usd'][1]}")
    t = m["total_corpus"]
    print(f"\n  absence cells audited {t['n_absence_cells']}   "
          f"present control cells {t['n_present_control_cells']}")

    g = m["stage1_gate"]
    a, bb = g["exact_gate"]["band_a_requires"], g["exact_gate"]["band_b_requires"]
    print("\n=== EXACT STAGE-1 GATE (frozen before submission) ===")
    print(f"  Stage-1 documents {g['n_stage1_documents']}, cells returned "
          f"{g['n_cells_returned']}")
    print(f"  denominator: {g['n_original_present_quote_verified']} "
          f"{R.ORIGINAL_PRESENT} cells")
    print(f"               {g['n_original_gemini_absence']} {R.ORIGINAL_ABSENCE} cells "
          "(not scored against anything)")
    print(f"  thresholds: A {R.THRESHOLD_A} (Wilson lower)   B {R.THRESHOLD_B}   "
          f"unresolved upper <= {R.MAX_UNRESOLVED_UPPER_A}")
    print(f"  A  {R.GATE_A}")
    print(f"       detections  >= {a['detected_on_original_present_at_least']}"
          f"/{a['of']}   agreement >= {a['repetition_agreement_at_least']}"
          f"/{a['of_cells']}   unresolved <= {a['unresolved_at_most']}")
    print(f"  B  {R.GATE_B}")
    print(f"       detections  >= {bb['detected_on_original_present_at_least']}"
          f"/{bb['of']}   agreement >= {bb['repetition_agreement_at_least']}"
          f"/{bb['of_cells']}   and band A not met")
    print(f"  C  {R.GATE_C}  otherwise")
    print(f"  note: a flawless 11/11 on the designated present cases alone gives a "
          f"Wilson lower bound of only "
          f"{g['max_achievable_lower_bound_on_designated_present_only']}, "
          f"below THRESHOLD_A")
    print(f"\n  calibration: {sealed_ref['n_designated_cases']} designated cases "
          f"(11 {R.ORIGINAL_PRESENT} / 11 {R.ORIGINAL_ABSENCE}), "
          f"{public['n_documents']} documents, "
          f"{public['n_cells_returned']} cells returned")
    print("\n  NO API CALL HAS BEEN MADE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
