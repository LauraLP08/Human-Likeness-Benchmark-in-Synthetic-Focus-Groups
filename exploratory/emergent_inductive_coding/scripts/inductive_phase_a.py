"""
PHASE_A_EXTRACTION — codebook-blind open thematic extraction, one call per segmented unit.

    py scripts/inductive_phase_a.py --preflight
    py scripts/inductive_phase_a.py --submit
    py scripts/inductive_phase_a.py --status
    py scripts/inductive_phase_a.py --retrieve
    py scripts/inductive_phase_a.py --validate

PHASE A ONLY. Nothing here runs B, C, D, E1, E2, E3, F1 or F2, builds a taxonomy,
consolidates themes, computes a curve or interprets saturation.

WHY GEMINI
----------
Claude generated the synthetic transcripts, so Claude cannot be the open extractor over
them without reading its own output. Extraction uses `gemini-3.5-flash`.

CODEBOOK-BLIND
--------------
The deductive codebook is never shown, quoted, named or paraphrased. The extractor sees
one segmented unit of transcript and nothing else, and is asked what themes are present
in that text on its own terms.

NO POOLING
----------
One request per unit. Questions, documents, conditions and replications are never
combined in a request.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_segments as segmod    # noqa: E402
import inductive_inventory as invmod   # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_FIN = _PE / "final"
_OUT = _PE / "inductive_phase_a"
_QUAR = _OUT / "quarantine"

MODEL = "gemini-3.5-flash"
EXECUTION_MODE = "batch"
MAX_OUTPUT_TOKENS = 16384
STAGE = "PHASE_A_EXTRACTION"

_MANIFEST = _OUT / "phase_a_manifest.json"
_JOB = _OUT / "phase_a_batch_job.json"
_RAW = _OUT / "phase_a_raw_responses.json"
_ACCEPTED = _OUT / "phase_a_accepted.json"


class PhaseAError(RuntimeError):
    pass


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _load_env() -> None:
    p = _ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ------------------------------------------------------------- prompting
SYSTEM_PROMPT = """\
You are reading one section of a transcript from a group discussion.

Identify the themes that are actually present in this section, on the text's own terms. \
Work inductively: describe what these speakers are saying, not what any prior framework \
expects them to say. You have not been given any coding scheme, and none exists for you \
to match.

For EACH theme you identify, return:
  * theme_id   a short identifier unique WITHIN this section, e.g. T1, T2, T3
  * label      a brief noun phrase, at most about six words
  * description one sentence describing the theme
  * quotes     one or more supporting quotations, each with:
                 turn_id  the exact turn identifier as printed in the section
                 speaker  the exact speaker label as printed for that turn
                 quote    a VERBATIM extract copied character for character
  * descriptive_prominence  optional, one of LOW / MEDIUM / HIGH — an impression of how
                 much space the theme occupies in THIS section only

Rules:
  * Quotations must be copied exactly as printed. Never paraphrase, never repair, never \
reconstruct from memory. If you cannot copy a passage exactly, do not use it.
  * Only participant speech may support a theme. The moderator's questions introduce \
topics; they are not evidence that participants raised them.
  * There is NO required or expected number of themes. Report as many as the section \
actually supports, and no more.
  * If the section genuinely contains no identifiable theme, return an empty theme list \
and set no_themes_found to true with a brief reason. Do not invent a theme to fill space.
  * descriptive_prominence is an impression about this section alone. It is not a \
measure of importance, centrality or significance, and it has not been validated.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["themes", "no_themes_found"],
    "properties": {
        "no_themes_found": {"type": "boolean"},
        "no_themes_reason": {"type": "string"},
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["theme_id", "label", "description", "quotes"],
                "properties": {
                    "theme_id": {"type": "string"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "descriptive_prominence": {"type": "string",
                                               "enum": ["LOW", "MEDIUM", "HIGH"]},
                    "quotes": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["turn_id", "speaker", "quote"],
                            "properties": {
                                "turn_id": {"type": "string"},
                                "speaker": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

# THE CHECK IS SPLIT, because the two regions of a request have different authorship.
#
#   SCAFFOLD  — the system prompt and the wrapper I author. Entirely under my control,
#               so it takes the complete list.
#   VERBATIM  — the segmented transcript. It cannot be edited without corrupting the
#               evidence, and ordinary speech collides with the vocabulary: participants
#               in this corpus say "it's very hard to replicate that" about meat texture
#               and "gender does influence what I eat" in their own words. The latter
#               happens to match the A.1 codebook LABEL, but a participant saying it is
#               not the codebook being shown to the extractor. Treating it as
#               contamination would either block Phase A or force edits to the data.
#
#               So the transcript takes a HARD-LEAK list only: tokens that identify
#               provenance or reproduce codebook machinery and cannot occur innocuously.
SCAFFOLD_FORBIDDEN = ("macho_meals", "fg1", "fg2", "fg3", "fg4", "fg5", "run01", "run02",
                      "run03", "run04", "enriched", "demographics-only",
                      "demographics only", "synthetic", "gemini", "claude", "anthropic",
                      "replicate", "replication", "condition",
                      "a.1", "a.2", "a.3", "b.1", "b.2", "b.3", "b.4", "c.1", "c.2",
                      "c.3", "does influence", "no influence", "4n", "codebook",
                      "subtheme", "deductive", "natural, necessary", "extreme cases")

HARD_LEAK_TOKENS = ("macho_meals", "fg1", "fg2", "fg3", "fg4", "fg5",
                    "run01", "run02", "run03", "run04",
                    "demographics-only", "gemini", "anthropic",
                    "a.1", "a.2", "a.3", "b.1", "b.2", "b.3", "b.4",
                    "c.1", "c.2", "c.3", "codebook", "subtheme")

# retained for the manifest's own vocabulary checks
PROVENANCE_TOKENS = HARD_LEAK_TOKENS
CODEBOOK_TOKENS = ("a.1", "a.2", "a.3", "b.1", "b.2", "b.3", "b.4", "c.1", "c.2", "c.3",
                   "codebook", "subtheme", "deductive")


def _hits(text: str, tokens) -> list[str]:
    low = " ".join(text.lower().split())
    return sorted({t for t in tokens
                   if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low)})


# ------------------------------------------------------------ rendering
def render_unit(seg: dict) -> dict:
    """
    The unit as the extractor sees it: turn ids, pseudonymised speakers, verbatim text.
    No provenance, no condition, no question number, no codebook.
    """
    src = _ROOT / seg["source_path"]
    obj = json.loads(src.read_text(encoding="utf-8"))
    entries = obj if isinstance(obj, list) else obj["transcript"]
    bp = seg["boundary_provenance"]

    # The two sides record their boundary in different coordinates and must not be
    # conflated: human sections are delimited by ENTRY INDEX into the transcript list,
    # synthetic sections by the `turn` FIELD value. Slicing one with the other's
    # coordinate would silently select the wrong text, so each is handled explicitly and
    # the result is reconciled against the word count the segmentation recorded.
    if "opens_at_entry_index" in bp:
        lo, hi = bp["opens_at_entry_index"], bp["closes_before_entry_index"]
        chosen = list(enumerate(entries))[lo:hi]
        coord = "entry_index"
    else:
        lo, hi = bp["opens_at_turn"], bp["closes_before_turn"]
        chosen = [(i, e) for i, e in enumerate(entries) if lo <= int(e["turn"]) < hi]
        coord = "turn_field"

    speakers, lines, turns = {}, [], {}
    for idx, e in chosen:
        t = int(e["turn"])
        sid = e.get("canonical_speaker_id") or e.get("speaker_id")
        is_mod = (sid == "MODERATOR" or e.get("speaker_role") == "moderator")
        if is_mod:
            name = "Moderator"
        else:
            if sid not in speakers:
                speakers[sid] = f"P{len(speakers) + 1}"
            name = speakers[sid]
        tid = f"T{t:03d}"
        text = " ".join(e["content"].split())
        lines.append(f"[{tid}] {name}: {text}")
        turns.setdefault(tid, []).append({"speaker": name, "text": text,
                                          "is_moderator": is_mod})
    body = "SECTION OF TRANSCRIPT\n\n" + "\n".join(lines)
    # Reconcile against what the segmentation counted. This is what proves the slice is
    # the same text, whichever coordinate system delimited it.
    rendered_words = sum(len(u["text"].split()) for us in turns.values() for u in us)
    return {"body": body, "turns": turns, "n_turns": len(turns),
            "n_participants": len(speakers), "words": len(body.split()),
            "rendered_transcript_words": rendered_words,
            "segment_total_words": seg["total_words"],
            "reconciles": rendered_words == seg["total_words"],
            "coordinate_system": coord}


# ------------------------------------------------------------- manifest
def build_manifest() -> dict:
    seg = segmod.build()
    inv = invmod.build()
    if not seg["pass"]:
        raise PhaseAError(f"segmentation gate not clean: {seg['problems']}")
    if seg["n_segments"] != 174 or inv["n_units"] != 174:
        raise PhaseAError(f"expected 174 units, got {seg['n_segments']}/{inv['n_units']}")

    prompt_sha = _sha(SYSTEM_PROMPT)
    schema_sha = _sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))

    requests, problems, prov_hits, cb_hits, renders = [], [], [], [], {}
    for s in sorted(seg["segments"], key=lambda x: x["unit_id"]):
        r = render_unit(s)
        renders[s["unit_id"]] = r
        if r["n_turns"] == 0:
            problems.append(f"{s['unit_id']}: rendered zero turns")
        if not r["reconciles"]:
            problems.append(f"{s['unit_id']}: rendered {r['rendered_transcript_words']} "
                            f"words, segmentation recorded {r['segment_total_words']}")
        if ph := _hits(r["body"], HARD_LEAK_TOKENS):
            prov_hits.append({s["unit_id"]: ph})

        key = f"pa::{s['unit_id']}"
        cache_key = _sha("|".join([
            STAGE, s["unit_id"], str(s["question"]), s["section_sha256"],
            _sha(r["body"]), prompt_sha, schema_sha, MODEL, EXECUTION_MODE]))
        requests.append({
            "custom_request_key": key,
            "unit_id": s["unit_id"],
            "question": s["question"],
            "condition": s["condition"], "fg": s["fg"],
            "canonical_replication_index": s["canonical_replication_index"],
            "physical_run": s["physical_run"],
            "source_path": s["source_path"],
            "segment_text_sha256": s["section_sha256"],
            "rendered_sha256": _sha(r["body"]),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "model": MODEL, "execution_mode": EXECUTION_MODE,
            "effective_config": {"model": MODEL,
                                 "response_mime_type": "application/json",
                                 "max_output_tokens": MAX_OUTPUT_TOKENS,
                                 "temperature_transmitted": False,
                                 "thinking_config_transmitted": False},
            "cache_key": cache_key,
            "n_turns": r["n_turns"], "n_participants": r["n_participants"],
            "prompt_words": r["words"],
            "length_tercile": s["length_tercile"],
        })

    # ---- the checks the instruction requires, each computed not assumed
    keys = [r["custom_request_key"] for r in requests]
    if len(set(keys)) != 174:
        problems.append(f"{len(set(keys))} unique custom request keys, expected 174")
    if len(requests) != 174:
        problems.append(f"{len(requests)} requests, expected 174")

    seg_hashes = {s["unit_id"]: s["section_sha256"] for s in seg["segments"]}
    mismatched = [r["unit_id"] for r in requests
                  if r["segment_text_sha256"] != seg_hashes.get(r["unit_id"])]
    if mismatched:
        problems.append(f"{len(mismatched)} text hashes differ from inductive_segments")

    def _uid(u):
        """Mirror the unit_id shape the segmentation emits, on both sides."""
        if u["condition"] == "human":
            return f"human::{u['fg']}::Q{u['question']}"
        return (f"{u['condition']}::{u['fg']}::"
                f"R{u['canonical_replication_index']}::Q{u['question']}")

    universe = {_uid(u) for u in inv["units"]}
    outside = sorted({r["unit_id"] for r in requests} - universe)
    missing = sorted(universe - {r["unit_id"] for r in requests})
    if outside:
        problems.append(f"{len(outside)} units outside the universe")
    if missing:
        problems.append(f"{len(missing)} units absent from the manifest")

    syn_bad = [r["unit_id"] for r in requests
               if r["physical_run"] and "comparable_transcripts" not in r["source_path"]]
    if syn_bad:
        problems.append(f"{len(syn_bad)} synthetic units not from a comparable window")

    scaffold = SYSTEM_PROMPT + "\nSECTION OF TRANSCRIPT\n\n"
    cb_hits = [{"SYSTEM_PROMPT_AND_WRAPPER": h}] if (h := _hits(
        scaffold, SCAFFOLD_FORBIDDEN)) else []
    if prov_hits:
        problems.append(f"hard provenance leak in {len(prov_hits)} units")
    if cb_hits:
        problems.append(f"forbidden vocabulary in the authored scaffolding: {cb_hits}")

    # closing residue must be excluded: every unit ends before its run's closing turn
    closing_included = []
    for s in seg["segments"]:
        bp = s["boundary_provenance"]
        if bp.get("includes_closing"):
            closing_included.append(s["unit_id"])
    if closing_included:
        problems.append(f"{len(closing_included)} units include a closing section")

    est_in = sum(round(r["prompt_words"] * 1.35) for r in requests)
    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "stage": STAGE,
        "authorised_scope": "PHASE_A_EXTRACTION only; B, C, D, E1, E2, E3, F1, F2 "
                            "are NOT authorised and are not run",
        "no_api_calls_yet": True,
        "model": MODEL, "execution_mode": EXECUTION_MODE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "extractor_rationale": ("Claude generated the synthetic transcripts, so Claude "
                                "cannot be the open extractor over them"),
        "codebook_blind": True,
        "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
        "n_requests": len(requests),
        "checks": {
            "unique_custom_request_keys": len(set(keys)),
            "text_hashes_matching_inductive_segments": len(requests) - len(mismatched),
            "units_outside_universe": len(outside),
            "units_missing": len(missing),
            "hard_provenance_leaks_in_transcript": len(prov_hits),
            "forbidden_vocabulary_in_authored_scaffolding": len(cb_hits),
            "synthetic_not_from_comparable_window": len(syn_bad),
            "units_including_closing": len(closing_included),
        },
        "contamination_check": {
            "design": "SPLIT",
            "scaffold_rule": "full forbidden list over the system prompt and wrapper",
            "verbatim_rule": ("hard provenance and codebook-machinery leaks only inside "
                              "transcript text, which cannot be edited without "
                              "corrupting the evidence"),
            "why": ("participants say 'hard to replicate that' about meat texture and "
                    "'gender does influence what I eat' in their own words; the latter "
                    "matches the A.1 codebook label but is not the codebook being shown "
                    "to the extractor"),
            "scaffold_terms_checked": len(SCAFFOLD_FORBIDDEN),
            "hard_leak_terms_checked": len(HARD_LEAK_TOKENS),
            "provenance_detail": prov_hits[:10], "scaffold_detail": cb_hits[:10]},
        "estimated_input_tokens": est_in,
        "estimate_basis": "1.35 tokens/word, PLANNING ESTIMATE for Gemini",
        "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED",
        "problems": problems, "pass": not problems,
        "requests": requests,
    }, renders


# ------------------------------------------------------------ validation
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-").replace("…", "..."))
    return re.sub(r"\s+", " ", s).strip().lower()


QUARANTINE_REASONS = (
    "TRUNCATED", "SCHEMA_INCOMPLETE", "DUPLICATE_THEME_ID", "TURN_ID_NOT_IN_UNIT",
    "QUOTE_NOT_LITERAL", "MODERATOR_QUOTE", "EMPTY_RESPONSE", "WRONG_UNIT",
    "CODEBOOK_CONTAMINATION", "INVALID_JSON", "NO_OUTPUT")


def validate_one(rec: dict, turns: dict) -> dict:
    """Every failure mode the instruction names, each with its own reason."""
    reasons, themes = [], []
    if rec.get("result_type") != "succeeded" or not rec.get("raw_text"):
        return {"accepted": False, "reasons": ["NO_OUTPUT"], "themes": []}

    # The provider returns an enum repr such as "FinishReason.STOP". Matching the bare
    # literal flagged every one of 174 complete responses as truncated.
    fin = str(rec.get("finish_reason") or "").upper()
    if fin and "STOP" not in fin:
        reasons.append("TRUNCATED")

    try:
        j = json.loads(rec["raw_text"])
    except Exception:                                  # noqa: BLE001
        return {"accepted": False, "reasons": ["INVALID_JSON"], "themes": []}

    if not isinstance(j, dict) or "themes" not in j:
        reasons.append("SCHEMA_INCOMPLETE")
        j = j if isinstance(j, dict) else {}

    # Unit identity is established by the custom_request_key the provider echoes, which
    # is unique and verified at preflight. It is NOT taken from a self-declared field:
    # the extractor is deliberately blind to provenance, so it cannot know its unit id
    # and returns placeholders like "section_1". Requiring it was a design error here.
    #
    # WRONG_UNIT is therefore detected from the DATA: a response that returns themes but
    # whose quotations localise nowhere in this unit is about some other text.

    raw_themes = j.get("themes") or []
    if not raw_themes and not j.get("no_themes_found"):
        reasons.append("EMPTY_RESPONSE")

    ids = [t.get("theme_id") for t in raw_themes]
    if len(ids) != len(set(ids)):
        reasons.append("DUPLICATE_THEME_ID")

    blob = json.dumps(j, ensure_ascii=False)
    if _hits(blob, CODEBOOK_TOKENS):
        reasons.append("CODEBOOK_CONTAMINATION")

    n_quotes_checked = n_quotes_localised = 0
    for t in raw_themes:
        for f in ("theme_id", "label", "description"):
            if not t.get(f):
                reasons.append("SCHEMA_INCOMPLETE")
        qs = t.get("quotes") or []
        if not qs:
            reasons.append("SCHEMA_INCOMPLETE")
        for q in qs:
            tid, spk, quote = q.get("turn_id"), q.get("speaker"), q.get("quote")
            if not (tid and spk and quote):
                reasons.append("SCHEMA_INCOMPLETE")
                continue
            n_quotes_checked += 1
            if tid not in turns:
                reasons.append("TURN_ID_NOT_IN_UNIT")
                continue
            hit = next((u for u in turns[tid]
                        if _norm(quote) and _norm(quote) in _norm(u["text"])), None)
            if hit is None:
                reasons.append("QUOTE_NOT_LITERAL")
                continue
            n_quotes_localised += 1
            if hit["is_moderator"] or _norm(spk) == "moderator":
                reasons.append("MODERATOR_QUOTE")
        themes.append(t)

    if raw_themes and n_quotes_checked and n_quotes_localised == 0:
        reasons.append("WRONG_UNIT")

    reasons = sorted(set(reasons))
    return {"accepted": not reasons, "reasons": reasons,
            "themes": themes if not reasons else [],
            "no_themes_found": bool(j.get("no_themes_found")),
            "no_themes_reason": j.get("no_themes_reason")}


# ---------------------------------------------------------- submit/retrieve
def submit() -> dict:
    man, renders = build_manifest()
    if not man["pass"]:
        raise PhaseAError("preflight failed:\n  " + "\n  ".join(man["problems"]))
    if _JOB.exists():
        raise PhaseAError(f"{_JOB.name} already exists; creation is NOT idempotent")

    _atomic(_MANIFEST, man)
    _load_env()
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    inline = [{"model": MODEL,
               "contents": [{"parts": [{"text": renders[r["unit_id"]]["body"]}],
                             "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": r["custom_request_key"]}}
              for r in man["requests"]]
    if len(inline) != 174:
        raise PhaseAError(f"{len(inline)} inline requests, expected 174")

    print(f"submitting ONE batch job with {len(inline)} requests, model {MODEL} ...")
    job = client.batches.create(model=MODEL, src=inline,
                                config={"display_name": "inductive_phase_a_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "display_name": getattr(job, "display_name", None),
           "state": str(getattr(job, "state", None)),
           "stage": STAGE, "model": MODEL, "execution_mode": EXECUTION_MODE,
           "n_requests": len(inline),
           "split_into_multiple_jobs": False,
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]],
           "retrieval_rule": "by custom_request_key only, never by position",
           "warning": "creation is NOT idempotent — never create a second job to retry"}
    _atomic(_JOB, rec)
    print(f"job name saved immediately: {rec['job_name']}")
    return rec


def status() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", None))
    print(rec["job_name"], st)
    return {"state": st, "job": job}


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", ""))
    if "SUCCEEDED" not in st and "SUCCESS" not in st:
        raise PhaseAError(f"job state {st}, not succeeded")

    expected = set(rec["custom_request_keys"])
    out, usage_in, usage_out = {}, 0, 0
    dest = getattr(job, "dest", None)
    responses = getattr(dest, "inlined_responses", None) or []
    for item in responses:
        meta = getattr(item, "metadata", None) or {}
        key = (meta.get("custom_request_key") if isinstance(meta, dict)
               else getattr(meta, "custom_request_key", None))
        if key is None:
            raise PhaseAError("a response carries no custom_request_key; "
                              "positional matching is not permitted")
        if key in out:
            raise PhaseAError(f"duplicate custom_request_key {key}")
        resp = getattr(item, "response", None)
        err = getattr(item, "error", None)
        entry = {"custom_request_key": key,
                 "unit_id": key.split("::", 1)[1] if "::" in key else key}
        if err is not None or resp is None:
            entry.update({"result_type": "error", "error": str(err)})
        else:
            cands = getattr(resp, "candidates", None) or []
            fin = str(getattr(cands[0], "finish_reason", "")) if cands else ""
            text = getattr(resp, "text", None)
            um = getattr(resp, "usage_metadata", None)
            if um is not None:
                usage_in += getattr(um, "prompt_token_count", 0) or 0
                usage_out += getattr(um, "candidates_token_count", 0) or 0
            entry.update({"result_type": "succeeded", "finish_reason": fin,
                          "raw_text": text})
        out[key] = entry

    missing = sorted(expected - set(out))
    if missing:
        raise PhaseAError(f"{len(missing)} responses missing: {missing[:5]}")

    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_name": rec["job_name"], "stage": STAGE,
               "matched_by": "custom_request_key",
               "n_results": len(out),
               "measured_usage": {"input_tokens": usage_in, "output_tokens": usage_out},
               "responses": [out[k] for k in sorted(out)]}
    _atomic(_RAW, payload)
    print(f"retrieved {len(out)} responses -> {_RAW.name}")
    return payload


def validate() -> dict:
    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(_RAW.read_text(encoding="utf-8"))
    _, renders = build_manifest()
    by_key = {r["custom_request_key"]: r for r in man["requests"]}

    accepted, quarantined = [], []
    for r in raw["responses"]:
        meta = by_key[r["custom_request_key"]]
        v = validate_one({**r, "unit_id": meta["unit_id"]},
                         renders[meta["unit_id"]]["turns"])
        row = {**{k: meta[k] for k in ("unit_id", "question", "condition", "fg",
                                       "canonical_replication_index", "physical_run",
                                       "prompt_words", "length_tercile")},
               "n_themes": len(v["themes"]),
               "n_quotes": sum(len(t.get("quotes") or []) for t in v["themes"]),
               "reasons": v["reasons"], "themes": v["themes"],
               "no_themes_found": v.get("no_themes_found")}
        (accepted if v["accepted"] else quarantined).append(row)

    _QUAR.mkdir(parents=True, exist_ok=True)
    if quarantined:
        _atomic(_QUAR / "phase_a_quarantine.json",
                {"n": len(quarantined), "rows": quarantined,
                 "rule": "quarantined results NEVER enter the accepted cache"})

    out = {"validated_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
           "n_units": len(man["requests"]),
           "n_accepted": len(accepted), "n_quarantined": len(quarantined),
           "quarantine_reasons": dict(Counter(x for r in quarantined
                                              for x in r["reasons"])),
           "measured_usage": raw["measured_usage"],
           "estimated_input_tokens": man["estimated_input_tokens"],
           "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED",
           "accepted": accepted}
    _atomic(_ACCEPTED, out)
    return out


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        man, _ = build_manifest()
        _atomic(_MANIFEST, man)
        print("=== PHASE A PREFLIGHT ===")
        print(f"  stage              {man['stage']}")
        print(f"  model              {man['model']}  ({man['execution_mode']})")
        print(f"  requests           {man['n_requests']}")
        for k, v in man["checks"].items():
            print(f"  {k:44s} {v}")
        print(f"  estimated input tokens  {man['estimated_input_tokens']:,} "
              f"({man['estimate_basis']})")
        print(f"  gemini cost        {man['gemini_cost_status']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    if "--submit" in a:
        submit()
        return 0
    if "--status" in a:
        status()
        return 0
    if "--retrieve" in a:
        retrieve()
        return 0
    if "--validate" in a:
        o = validate()
        print(f"accepted {o['n_accepted']}/{o['n_units']}  "
              f"quarantined {o['n_quarantined']}")
        print("  reasons:", o["quarantine_reasons"])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PhaseAError as exc:
        print(f"REFUSED: {exc}")
        raise SystemExit(2)
