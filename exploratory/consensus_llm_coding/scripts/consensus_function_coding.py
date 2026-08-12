"""
Consensus function coding — LLM multi-label turn classification
(namespace: CONSENSUS_FUNCTION_LLM_EXPLORATORY).

STATUS: LLM_CODED_HUMAN_VALIDATION_REQUIRED. Not a validated measure.

Classifies the CONVERSATIONAL FUNCTION of each participant turn — agreement,
disagreement, challenge, neutral_elaboration — allowing several labels on one
turn, because a turn that says "I agree it's expensive, but that's not the main
reason" carries two functions and a single categorical label destroys one of
them. `mixed` is DERIVED (agreement AND disagreement), never assigned, so every
mixed turn necessarily carries two separately verifiable quotes.

This is NOT Tier 1 / Tier 2 / Tier 2B: no theme is extracted and no theme is
matched. It is also NOT CONSENSUS_DYNAMICS_EXPLORATORY, which is a frozen
lexicon with zero API calls and which deliberately refused to classify stance.
Results from this layer are never aggregated with either.

Design, category definitions, denominators and open decisions:
    analysis/production_evaluation/consensus_function/DESIGN_AND_CODING_SCHEME.md

READ-ONLY on the corpus. Inputs come exclusively from the frozen whitelist in
`analysis/production_evaluation/frozen_evaluator_inputs.json` (5 human + 30
synthetic). `output/session_logs/` is never read and never written. Nothing is
generated or regenerated.

Usage:
    py scripts/consensus_function_coding.py --dry-run --fg fg1      # no API calls
    py scripts/consensus_function_coding.py --fg fg1                # live, cached
    py scripts/consensus_function_coding.py --fg fg1 --aggregate-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_FROZEN = _REPO_ROOT / "analysis" / "production_evaluation" / "frozen_evaluator_inputs.json"
_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_function"
_CACHE_DIR = _OUT_DIR / "cache"

# ---------------------------------------------------------------------------
# Evaluator. CONFIRMED against scripts/thematic_coding.py EVALUATOR_CONFIGS.
#
# gemini-2.5-flash is DISQUALIFIED in this project (81.8% Gate-1 agreement vs an
# 85% threshold) and is still the module default of thematic_coding._MODEL, so
# the identifier is pinned here and guarded rather than inherited.
#
# temperature: NOT transmitted. EVALUATOR_CONFIGS["gemininext"]["temperature"] is
# None ("not supported - omitted from request"). A request for "temperature 0"
# CANNOT be honoured on this model in this project; determinism is therefore not
# guaranteed and the cache freezes the first answer rather than demonstrating
# reproducibility. See DESIGN_AND_CODING_SCHEME.md section 2.1.
#
# thinking_config: NOT transmitted. thematic_coding attaches one only when "2.5"
# is in the model id. "thinking_level: medium" in EVALUATOR_CONFIGS is a logging
# label, not a transmitted parameter.
#
# safety_settings: never set anywhere in this repo -> API defaults, unpinned.
# ---------------------------------------------------------------------------
REQUIRED_MODEL = "gemini-3.5-flash"
EVALUATOR_KEY = "gemininext"
MAX_OUTPUT_TOKENS = 16384

CHUNK_TARGET_TURNS = 12
CONTEXT_DEPTH = 3

LABELS = ("agreement", "disagreement", "challenge", "neutral_elaboration")
RELATIONAL = ("agreement", "disagreement", "challenge")
NO_CODE_REASONS = ("procedural", "unintelligible", "off_topic",
                   "moderator_directed_only", "other")
MIN_QUOTE_WORDS = 3


class ConsensusFunctionError(RuntimeError):
    """Raised when a guard on model, inputs or schema fails."""


# ---------------------------------------------------------------------------
# Prompt. FROZEN at the first live call; its SHA-256 enters every cache key.
#
# It never mentions humans, AI, synthesis, conditions, or that transcripts
# differ in origin. Blinding is procedural, not perceptual: turn length and
# register remain visible and no claim is made that the evaluator cannot tell.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are coding the conversational function of turns in a group discussion.

For each turn marked TO CODE, decide which of these functions the turn performs.
A turn may perform SEVERAL functions at once — assign every label that applies.
Do not force one label per turn.

LABELS

agreement — endorses, affirms, ratifies or aligns with a position attributable to
  ANOTHER speaker in the preceding context.
  Includes: explicit endorsement; approvingly restating another's point; extending
    another's point as correct.
  Excludes: mere acknowledgement of having heard ("right", "mm"); politeness with no
    stance; agreeing with the moderator's question rather than a participant's position.

disagreement — rejects, contradicts, denies, or asserts a counter-position to a
  position attributable to ANOTHER speaker.
  Excludes: disagreement with an absent third party or with society in general.

challenge — questions, probes, or asks for justification of another speaker's
  position WITHOUT committing to a counter-position.
  The test: does the speaker assert something that could be false? If yes, it is
    disagreement, not challenge.
  Excludes: rhetorical questions that assert a counter-position (those are
    disagreement); questions directed at the moderator.

neutral_elaboration — contributes substantive content (own experience, description,
  reasoning, example) WITHOUT positioning toward another speaker's position.

If none applies, return an empty label list and a no_code_reason from exactly:
procedural, unintelligible, off_topic, moderator_directed_only, other.

EVIDENCE — MANDATORY

Every label must carry:
  evidence_quote  — a VERBATIM, EXACT substring of that turn's text, at least 3
                    words long, copied character for character. Do not paraphrase,
                    do not normalise punctuation, do not fix spelling. A quote that
                    is not an exact substring invalidates the label.
  target_turn_id  — for agreement, disagreement and challenge: the id (e.g. "T08")
                    of the turn whose position is being responded to. It must be a
                    turn shown in this chunk. For neutral_elaboration it must be null.

If a turn both agrees with one thing and disagrees with another, return BOTH labels,
each with its own quote. Do not collapse them into a single label.

OUTPUT — JSON only, no prose, no code fences:

{"codings": [
  {"turn_id": "T08",
   "labels": [
     {"label": "agreement", "evidence_quote": "...", "target_turn_id": "T07"},
     {"label": "disagreement", "evidence_quote": "...", "target_turn_id": "T07"}
   ],
   "no_code_reason": null}
]}

Return exactly one coding object for every turn marked TO CODE, and none for any
other turn.
"""

# Clause boundary. IDENTICAL rule to scripts/consensus_dynamics_events.py so that
# per-clause normalisation is comparable across the two consensus layers. Replicated
# rather than imported to avoid coupling to that module's frozen-hash surface.
_CLAUSE_SPLIT = re.compile(
    r"(?:^|[.!?;:\n]+|\s+(?:and|but|so|because|although|though)\s+)", re.I)


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]


# Typographic normalisation used ONLY as a secondary check on evidence quotes.
#
# The corpus is never rewritten. The blinded FG1 corpus contains 820 em dashes,
# ALL of them on the synthetic side (1.0-1.5 per 100 words in every synthetic run,
# 0 in the human transcript). A coder that copies "a - b" for "a — b" would fail a
# strict substring check on the synthetic side only, turning a transcription habit
# into an asymmetric measurement artefact. So the verifier records BOTH verdicts:
# strict is primary, normalised is counted separately, and neither is hidden.
_PUNCT_MAP = {"—": "-", "–": "-", "’": "'", "‘": "'",
              "“": '"', "”": '"', "…": "..."}


def _norm_punct(text: str) -> str:
    for a, b in _PUNCT_MAP.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Effective request configuration
#
# Re-implemented over THIS call's generation config rather than imported from
# production_eval_pipeline: that function reads the keys transmitted by
# thematic_coding.code_transcript_tier1, and this is a different call site with a
# different config. Importing it would report Tier 1's parameters for a request
# that does not make them.
# ---------------------------------------------------------------------------
def generation_config(system_prompt: str) -> dict:
    """The generation config actually transmitted. Single source of truth."""
    return {
        "system_instruction": system_prompt,
        "response_mime_type": "application/json",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        # temperature: deliberately absent - not supported on gemini-3.5-flash.
        # thinking_config: deliberately absent - only attached for 2.5-class models.
        # safety_settings: deliberately absent - API defaults, as everywhere else here.
    }


def effective_request_config() -> dict:
    """
    What is ACTUALLY transmitted, read from generation_config() rather than
    restated, so the two cannot drift. Serialised verbatim into the cache key: a
    parameter that can move the output but is absent from the key would let two
    materially different runs collide on one entry.
    """
    gen = generation_config(_SYSTEM_PROMPT)
    if "temperature" in gen or "thinking_config" in gen:
        raise ConsensusFunctionError(
            "generation_config now transmits temperature or thinking_config. The "
            "recorded effective configuration and the frozen design both state "
            "these are omitted for gemini-3.5-flash. Re-declare before running.")
    return {
        "execution_mode": "synchronous",
        "model": REQUIRED_MODEL,
        "response_mime_type": gen["response_mime_type"],
        "max_output_tokens": gen["max_output_tokens"],
        "temperature_transmitted": False,
        "temperature": None,
        "thinking_config_transmitted": False,
        "thinking_config": None,
        "thinking_level_effective": "model_default_unpinned",
        "thinking_level_label_in_config": "medium",
        "safety_settings_transmitted": False,
    }


def canonical_model_config(effective: dict) -> str:
    return json.dumps(effective, sort_keys=True, separators=(",", ":"))


def guard_model() -> dict:
    """Refuse to run on anything but the frozen production evaluator."""
    import thematic_coding as tc
    ecfg = tc.EVALUATOR_CONFIGS.get(EVALUATOR_KEY)
    if ecfg is None:
        raise ConsensusFunctionError(
            f"EVALUATOR_CONFIGS has no {EVALUATOR_KEY!r} entry.")
    if ecfg["model"] != REQUIRED_MODEL:
        raise ConsensusFunctionError(
            f"EVALUATOR_CONFIGS[{EVALUATOR_KEY!r}]['model'] is {ecfg['model']!r}, "
            f"not {REQUIRED_MODEL!r}. gemini-2.5-flash is DISQUALIFIED.")
    if ecfg.get("temperature") is not None:
        raise ConsensusFunctionError(
            "EVALUATOR_CONFIGS now carries a temperature for gemini-3.5-flash. "
            "The frozen design records temperature as NOT transmitted; re-declare "
            "before running.")
    return ecfg


# ---------------------------------------------------------------------------
# Corpus loading — whitelist only
# ---------------------------------------------------------------------------
@dataclass
class Turn:
    turn_id: str
    speaker_masked: str
    is_participant: bool
    text: str
    n_words: int
    n_clauses: int
    prev_speaker_is_participant: bool


@dataclass
class Transcript:
    fg: str
    condition: str
    run: str
    path: Path
    source_sha256: str
    turns: list[Turn]
    name_substitutions: dict[str, str]
    n_substitutions_in_text: int
    blinded_sha256: str = ""
    chunks: list[dict] = field(default_factory=list)


def _load_whitelist(fg: str) -> list[dict]:
    frozen = json.loads(_FROZEN.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for r in frozen["human_inputs"]:
        if r["fg"] == fg:
            rows.append({"condition": "human", "run": f"{fg}_human",
                         "path": r["path"], "sha256": r["sha256"]})
    for r in frozen["synthetic_inputs"]:
        if r["fg"] == fg:
            rows.append({"condition": r["condition"], "run": r["physical_run"],
                         "path": r["path"], "sha256": r["sha256"]})
    if not rows:
        raise ConsensusFunctionError(f"No whitelisted inputs for {fg!r}.")
    return rows


def _raw_entries(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "transcript" in data:      # synthetic window
        return data["transcript"]
    if isinstance(data, list):                               # standardized human
        return data
    raise ConsensusFunctionError(f"Unrecognised transcript shape: {path}")


def _is_moderator(entry: dict) -> bool:
    role = entry.get("speaker_role")
    if role is not None:
        return role != "participant"
    return entry.get("speaker_id") == "MODERATOR"


def blind_transcript(fg: str, condition: str, run: str, path: Path,
                     source_sha: str) -> Transcript:
    """
    Strip every provenance field and mask speaker identity.

    Removed: timestamp, selection_mode, source_type, source_file, page,
    paragraph_indices, standardization_confidence, speaker_role, speaker_id.
    Speaker names map to "Speaker A".. by order of first appearance, and the same
    mapping is applied to occurrences of those names INSIDE turn text so the coder
    can resolve "like David said" against a masked label. Substitutions are counted
    so the mapping is auditable.

    The blinded text is what is hashed, what is sent, and what evidence quotes are
    verified against.
    """
    entries = _raw_entries(path)
    alphabet = [chr(ord("A") + i) for i in range(26)]
    mapping: dict[str, str] = {}
    for e in entries:
        if _is_moderator(e):
            continue
        name = (e.get("speaker_name") or "").strip()
        if name and name not in mapping:
            mapping[name] = f"Speaker {alphabet[len(mapping)]}"

    patterns = [(re.compile(rf"\b{re.escape(n)}\b"), m)
                for n, m in sorted(mapping.items(), key=lambda kv: -len(kv[0]))]

    turns: list[Turn] = []
    n_subs = 0
    prev_participant = False
    for idx, e in enumerate(entries):
        text = (e.get("content") or "").strip()
        for pat, repl in patterns:
            text, k = pat.subn(repl, text)
            n_subs += k
        is_p = not _is_moderator(e)
        speaker = mapping.get((e.get("speaker_name") or "").strip(), "Moderator") \
            if is_p else "Moderator"
        turns.append(Turn(
            turn_id=f"T{idx:03d}",
            speaker_masked=speaker,
            is_participant=is_p,
            text=text,
            n_words=len(text.split()),
            n_clauses=len(_clauses(text)),
            prev_speaker_is_participant=prev_participant,
        ))
        prev_participant = is_p

    tr = Transcript(fg=fg, condition=condition, run=run, path=path,
                    source_sha256=source_sha, turns=turns,
                    name_substitutions=mapping, n_substitutions_in_text=n_subs)
    tr.blinded_sha256 = _sha(render_full_blind(tr))
    return tr


def render_full_blind(tr: Transcript) -> str:
    return "\n".join(f"[{t.turn_id}] {t.speaker_masked}: {t.text}" for t in tr.turns)


def build_chunks(tr: Transcript) -> list[dict]:
    """
    Windows of CHUNK_TARGET_TURNS participant turns, each preceded by
    CONTEXT_DEPTH turns of any speaker for target attribution. Context turns are
    shown but never coded. Chunk boundaries are recorded so a turn's context is
    auditable after the fact.
    """
    targets = [i for i, t in enumerate(tr.turns) if t.is_participant]
    chunks: list[dict] = []
    for c, start in enumerate(range(0, len(targets), CHUNK_TARGET_TURNS)):
        block = targets[start:start + CHUNK_TARGET_TURNS]
        lo = max(0, block[0] - CONTEXT_DEPTH)
        span = list(range(lo, block[-1] + 1))
        chunks.append({
            "chunk_index": c,
            "target_turn_ids": [tr.turns[i].turn_id for i in block],
            "shown_turn_ids": [tr.turns[i].turn_id for i in span],
            "prompt_body": _render_chunk(tr, span, set(block)),
        })
    return chunks


def _render_chunk(tr: Transcript, span: list[int], targets: set[int]) -> str:
    lines = []
    for i in span:
        t = tr.turns[i]
        mark = "   <-- TO CODE" if i in targets else ""
        lines.append(f"[{t.turn_id}] {t.speaker_masked}: {t.text}{mark}")
    return "DISCUSSION EXCERPT:\n" + "\n\n".join(lines)


def cache_key(tr: Transcript, chunk: dict, effective: dict) -> str:
    return _sha(json.dumps({
        "blinded_transcript_sha256": tr.blinded_sha256,
        "chunk_index": chunk["chunk_index"],
        "chunk_turn_ids": chunk["target_turn_ids"],
        "prompt_sha256": _sha(_SYSTEM_PROMPT),
        "canonical_model_config": canonical_model_config(effective),
    }, sort_keys=True, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Validation of returned labels — the discipline of Tier 1 / Tier 2
# ---------------------------------------------------------------------------
def validate_coding(coding: dict, tr: Transcript, chunk: dict) -> list[dict]:
    """
    Returns one validated row per label (or a single NONE row).

    A quote that is not an exact substring of the blinded turn text is marked
    EVIDENCE_FAIL and excluded from the primary table, never silently dropped: the
    evidence-failure rate is itself a reported result.
    """
    by_id = {t.turn_id: t for t in tr.turns}
    turn = by_id.get(coding.get("turn_id", ""))
    if turn is None:
        return [{"turn_id": coding.get("turn_id"), "label": "SCHEMA_FAIL",
                 "evidence_quote": "", "target_turn_id": None,
                 "evidence_verified": "unknown_turn_id"}]
    shown = set(chunk["shown_turn_ids"])
    labels = coding.get("labels") or []
    if not labels:
        reason = coding.get("no_code_reason")
        ok = reason in NO_CODE_REASONS
        return [{"turn_id": turn.turn_id, "label": "NONE",
                 "evidence_quote": "", "target_turn_id": None,
                 "evidence_verified": f"no_code:{reason}" if ok
                                      else "SCHEMA_FAIL:missing_no_code_reason"}]
    rows = []
    for lab in labels:
        name = lab.get("label")
        quote = (lab.get("evidence_quote") or "")
        target = lab.get("target_turn_id")
        # Sequential, not a single elif chain: a quote accepted only under
        # punctuation normalisation must still have its target validated.
        if name not in LABELS:
            verdict = "SCHEMA_FAIL:unknown_label"
        elif len(quote.split()) < MIN_QUOTE_WORDS:
            verdict = "EVIDENCE_FAIL:quote_too_short"
        elif quote in turn.text:
            verdict = "ok"
        elif _norm_punct(quote) in _norm_punct(turn.text):
            verdict = "ok_normalized_punctuation"
        else:
            verdict = "EVIDENCE_FAIL:not_substring"
        if verdict.startswith("ok"):
            if name in RELATIONAL and target not in shown:
                verdict = "TARGET_FAIL:not_in_context"
            elif name == "neutral_elaboration" and target is not None:
                verdict = "TARGET_FAIL:target_on_non_relational"
        rows.append({"turn_id": turn.turn_id, "label": name,
                     "evidence_quote": quote, "target_turn_id": target,
                     "evidence_verified": verdict})
    return rows


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------
def dry_run(fg: str) -> dict:
    guard_model()
    effective = effective_request_config()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    transcripts = []
    for row in _load_whitelist(fg):
        p = _REPO_ROOT / row["path"]
        if not p.exists():
            raise ConsensusFunctionError(f"Whitelisted input missing: {p}")
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != row["sha256"]:
            raise ConsensusFunctionError(
                f"{p} does not match its frozen sha256 — refusing to code a "
                f"transcript that changed since the whitelist was frozen.")
        tr = blind_transcript(fg, row["condition"], row["run"], p, row["sha256"])
        tr.chunks = build_chunks(tr)
        transcripts.append(tr)

    # --- self-checks against the real corpus, not a fixture -----------------
    leak_fields = ("timestamp", "selection_mode", "source_file", "paragraph_indices",
                   "standardization_confidence", "speaker_role", "speaker_id")
    for tr in transcripts:
        blob = render_full_blind(tr)
        for f in leak_fields:
            if f in blob:
                raise ConsensusFunctionError(
                    f"Blinded text for {tr.run} still contains {f!r}.")
        if _sha(render_full_blind(tr)) != tr.blinded_sha256:
            raise ConsensusFunctionError(f"Blinding is not deterministic for {tr.run}.")
        for name in tr.name_substitutions:
            for t in tr.turns:
                if re.search(rf"\b{re.escape(name)}\b", t.text):
                    raise ConsensusFunctionError(
                        f"Unmasked speaker name {name!r} survives in {tr.run} "
                        f"{t.turn_id}.")
        coded = {tid for c in tr.chunks for tid in c["target_turn_ids"]}
        expected = {t.turn_id for t in tr.turns if t.is_participant}
        if coded != expected:
            raise ConsensusFunctionError(
                f"Chunking does not cover every participant turn in {tr.run}.")

    # verifier must reject as well as accept, on real text
    probe = next(t for t in transcripts[0].turns if t.is_participant and t.n_words > 8)
    good = " ".join(probe.text.split()[:5])
    chunk0 = transcripts[0].chunks[0]
    acc = validate_coding({"turn_id": probe.turn_id, "labels": [
        {"label": "neutral_elaboration", "evidence_quote": good,
         "target_turn_id": None}]}, transcripts[0], chunk0)
    rej = validate_coding({"turn_id": probe.turn_id, "labels": [
        {"label": "neutral_elaboration",
         "evidence_quote": "this phrase is definitely not present verbatim",
         "target_turn_id": None}]}, transcripts[0], chunk0)
    if acc[0]["evidence_verified"] != "ok" or "EVIDENCE_FAIL" not in rej[0]["evidence_verified"]:
        raise ConsensusFunctionError(
            "The evidence verifier does not both accept a true substring and reject "
            "a false one on real corpus text.")
    # a quote accepted only under punctuation normalisation must still be target-checked
    tgt = validate_coding({"turn_id": probe.turn_id, "labels": [
        {"label": "agreement", "evidence_quote": good,
         "target_turn_id": "T999"}]}, transcripts[0], chunk0)
    if tgt[0]["evidence_verified"] != "TARGET_FAIL:not_in_context":
        raise ConsensusFunctionError(
            "Target validation does not fire on a verified quote.")

    manifest = {
        "namespace": "CONSENSUS_FUNCTION_LLM_EXPLORATORY",
        "status": "LLM_CODED_HUMAN_VALIDATION_REQUIRED",
        "generated_utc": datetime.now(UTC).isoformat(),
        "fg": fg,
        "evaluator": {"model": REQUIRED_MODEL, "config_key": EVALUATOR_KEY,
                      "key_env": "GEMINI_API_KEY_NEXT"},
        "effective_request_config": effective,
        "prompt_sha256": _sha(_SYSTEM_PROMPT),
        "chunking": {"target_turns": CHUNK_TARGET_TURNS, "context_depth": CONTEXT_DEPTH},
        "transcripts": [],
    }
    total_calls = 0
    for tr in transcripts:
        pt = [t for t in tr.turns if t.is_participant]
        mt = [t for t in tr.turns if not t.is_participant]
        total_calls += len(tr.chunks)
        manifest["transcripts"].append({
            "condition": tr.condition, "run": tr.run,
            "path": str(tr.path.relative_to(_REPO_ROOT)),
            "source_sha256": tr.source_sha256,
            "blinded_sha256": tr.blinded_sha256,
            "participant_turns": len(pt),
            "moderator_turns_excluded": len(mt),
            "participant_words": sum(t.n_words for t in pt),
            "mean_words_per_participant_turn": round(
                sum(t.n_words for t in pt) / max(1, len(pt)), 1),
            "mean_clauses_per_participant_turn": round(
                sum(t.n_clauses for t in pt) / max(1, len(pt)), 1),
            # residual stylistic leakage, measured not assumed
            "em_dashes_per_100_participant_words": round(
                100 * sum(t.text.count("—") for t in pt)
                / max(1, sum(t.n_words for t in pt)), 2),
            "speakers_masked": len(tr.name_substitutions),
            "in_text_name_substitutions": tr.n_substitutions_in_text,
            "chunks": len(tr.chunks),
            "cache_keys": [cache_key(tr, c, effective) for c in tr.chunks],
        })
    manifest["estimated_api_calls"] = total_calls

    (_OUT_DIR / "dry_run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    (_OUT_DIR / "prompt_frozen.txt").write_text(_SYSTEM_PROMPT, encoding="utf-8")
    (_OUT_DIR / "sample_chunk_as_sent.txt").write_text(
        transcripts[0].chunks[0]["prompt_body"], encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------
# Live coding
# ---------------------------------------------------------------------------
def _load_corpus(fg: str) -> list[Transcript]:
    out = []
    for row in _load_whitelist(fg):
        p = _REPO_ROOT / row["path"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != row["sha256"]:
            raise ConsensusFunctionError(
                f"{p} does not match its frozen sha256 — refusing to code a "
                f"transcript that changed since the whitelist was frozen.")
        tr = blind_transcript(fg, row["condition"], row["run"], p, row["sha256"])
        tr.chunks = build_chunks(tr)
        out.append(tr)
    return out


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def call_chunk(tr: Transcript, chunk: dict, effective: dict,
               bypass_cache: bool = False, probe_tag: str = "") -> dict:
    """
    One chunk, one call. Results are written once per cache key and never
    overwritten: a re-run with the same key is a cache hit, not a rewrite.

    A MAX_TOKENS finish reason is recorded as truncation and never allowed to
    look like a set of turns that legitimately received no labels.
    """
    import thematic_coding as tc
    from google.genai import errors as _genai_errors
    key = cache_key(tr, chunk, effective)
    path = _CACHE_DIR / f"{key}.json" if not bypass_cache else \
        _CACHE_DIR / "probe" / f"{key}_{probe_tag}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    ecfg = guard_model()
    client = tc._client_for_evaluator(ecfg)
    gen = generation_config(_SYSTEM_PROMPT)

    payload: dict = {}
    for attempt in range(3):
        # 503 UNAVAILABLE is transient model overload. tc._generate_with_fallback
        # only handles 429 RESOURCE_EXHAUSTED, so an unretried 503 would abort a
        # batch mid-way. Completed chunks are cached, so a retry never re-pays for
        # work already done.
        resp = None
        for backoff in (0, 15, 30, 60, 120, 240, 300):
            if backoff:
                time.sleep(backoff)
            try:
                resp = tc._generate_with_fallback(
                    client, no_fallback=True,   # stay on the designated evaluator key
                    model=REQUIRED_MODEL, contents=chunk["prompt_body"], config=gen)
                break
            except _genai_errors.ServerError as exc:
                if "503" not in str(exc) and "UNAVAILABLE" not in str(exc):
                    raise
                print(f"    503 on {tr.run}#c{chunk['chunk_index']}, "
                      f"retrying in {backoff or 15}s", flush=True)
        if resp is None:
            raise ConsensusFunctionError(
                f"{tr.run} chunk {chunk['chunk_index']}: model still returning 503 "
                f"after retries. Cached chunks are kept; re-run to resume.")
        cands = getattr(resp, "candidates", None) or []
        finish = [str(getattr(c, "finish_reason", None)) for c in cands]
        um = getattr(resp, "usage_metadata", None)
        try:
            tc._log_call("consensus_function_coding", {
                "run_label": f"{tr.run}#c{chunk['chunk_index']}{probe_tag}",
                "model": REQUIRED_MODEL, "usage": tc._usage_dict(resp)})
        except Exception:
            pass
        truncated = any("MAX_TOKENS" in f for f in finish)
        try:
            parsed = json.loads(_strip_fences(resp.text))
            codings = parsed.get("codings", [])
            parse_error = None
        except Exception as exc:
            codings, parse_error = [], f"{type(exc).__name__}: {exc}"
        payload = {
            "cache_key": key, "run": tr.run, "condition": tr.condition,
            "chunk_index": chunk["chunk_index"],
            "target_turn_ids": chunk["target_turn_ids"],
            "shown_turn_ids": chunk["shown_turn_ids"],
            "blinded_transcript_sha256": tr.blinded_sha256,
            "prompt_sha256": _sha(_SYSTEM_PROMPT),
            "effective_request_config": effective,
            "probe_tag": probe_tag or None,
            "attempt": attempt + 1,
            "finish_reasons": finish,
            "truncated": truncated,
            "parse_error": parse_error,
            "prompt_tokens": getattr(um, "prompt_token_count", None),
            "candidates_tokens": getattr(um, "candidates_token_count", None),
            "thoughts_tokens": getattr(um, "thoughts_token_count", None),
            "codings": codings,
            "called_utc": datetime.now(UTC).isoformat(),
        }
        if parse_error is None and not truncated:
            break

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# The repeatability probe. Frozen choice, declared rather than picked after the
# fact: chunk 0 of the first enriched replicate. It measures whether the SAME
# request returns the SAME labels under unpinned sampling (temperature is not
# transmittable on this model — see section 2.1 of the design). Three extra calls
# compared against the cached primary answer = 4 observations of one chunk.
PROBE_RUN = "macho_meals_fg1_run01"
PROBE_CHUNK = 0
PROBE_REPEATS = 3


def run_live(fg: str) -> dict:
    guard_model()
    effective = effective_request_config()
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    corpus = _load_corpus(fg)

    rows: list[dict] = []
    call_log: list[dict] = []
    for tr in corpus:
        by_id = {t.turn_id: t for t in tr.turns}
        for chunk in tr.chunks:
            payload = call_chunk(tr, chunk, effective)
            call_log.append({k: payload[k] for k in
                             ("run", "chunk_index", "truncated", "parse_error",
                              "prompt_tokens", "candidates_tokens")})
            returned = {c.get("turn_id") for c in payload["codings"]}
            for coding in payload["codings"]:
                if coding.get("turn_id") not in chunk["target_turn_ids"]:
                    continue                    # coded a context turn; ignored, counted below
                for r in validate_coding(coding, tr, chunk):
                    t = by_id[r["turn_id"]]
                    rows.append({
                        "fg": fg, "condition": tr.condition, "run": tr.run,
                        "transcript_sha256": tr.blinded_sha256,
                        "turn_id": r["turn_id"], "speaker_masked": t.speaker_masked,
                        "is_participant": t.is_participant,
                        "prev_speaker_is_participant": t.prev_speaker_is_participant,
                        "n_words": t.n_words, "n_clauses": t.n_clauses,
                        "label": r["label"], "evidence_quote": r["evidence_quote"],
                        "target_turn_id": r["target_turn_id"],
                        "evidence_verified": r["evidence_verified"],
                        "chunk_index": chunk["chunk_index"],
                    })
            # a target turn the model simply did not return is recorded, not inferred
            for tid in chunk["target_turn_ids"]:
                if tid not in returned:
                    t = by_id[tid]
                    rows.append({
                        "fg": fg, "condition": tr.condition, "run": tr.run,
                        "transcript_sha256": tr.blinded_sha256, "turn_id": tid,
                        "speaker_masked": t.speaker_masked, "is_participant": True,
                        "prev_speaker_is_participant": t.prev_speaker_is_participant,
                        "n_words": t.n_words, "n_clauses": t.n_clauses,
                        "label": "MISSING_FROM_RESPONSE", "evidence_quote": "",
                        "target_turn_id": None,
                        "evidence_verified": "SCHEMA_FAIL:turn_not_returned",
                        "chunk_index": chunk["chunk_index"]})

    probe = run_probe(corpus, effective)
    write_outputs(fg, corpus, rows, probe, effective, call_log)
    return {"rows": len(rows), "probe": probe}


def run_probe(corpus: list[Transcript], effective: dict) -> dict:
    tr = next(t for t in corpus if t.run == PROBE_RUN)
    chunk = tr.chunks[PROBE_CHUNK]
    baseline = call_chunk(tr, chunk, effective)          # cached primary, no new call
    observations = [baseline] + [
        call_chunk(tr, chunk, effective, bypass_cache=True, probe_tag=f"r{i+1}")
        for i in range(PROBE_REPEATS)]

    def label_sets(p: dict) -> dict[str, frozenset]:
        out = {}
        for c in p.get("codings", []):
            tid = c.get("turn_id")
            if tid in chunk["target_turn_ids"]:
                out[tid] = frozenset(
                    l.get("label") for l in (c.get("labels") or [])
                    if l.get("label") in LABELS)
        return out

    sets = [label_sets(p) for p in observations]
    turns = chunk["target_turn_ids"]
    identical = sum(1 for t in turns
                    if len({s.get(t, frozenset()) for s in sets}) == 1)
    jac = []
    for t in turns:
        base = sets[0].get(t, frozenset())
        for s in sets[1:]:
            other = s.get(t, frozenset())
            union = base | other
            jac.append(1.0 if not union else len(base & other) / len(union))
    return {
        "run": PROBE_RUN, "chunk_index": PROBE_CHUNK,
        "n_turns": len(turns), "n_observations": len(observations),
        "extra_calls": PROBE_REPEATS,
        "turns_identical_across_all_observations": identical,
        "pct_turns_identical": round(100 * identical / max(1, len(turns)), 1),
        "mean_pairwise_jaccard_vs_baseline": round(sum(jac) / max(1, len(jac)), 3),
        "per_turn": {t: [sorted(s.get(t, frozenset())) for s in sets] for t in turns},
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def write_outputs(fg: str, corpus: list[Transcript], rows: list[dict],
                  probe: dict, effective: dict, call_log: list[dict]) -> None:
    import csv
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["fg", "condition", "run", "transcript_sha256", "turn_id",
            "speaker_masked", "is_participant", "prev_speaker_is_participant",
            "n_words", "n_clauses", "label", "evidence_quote", "target_turn_id",
            "evidence_verified", "chunk_index"]
    with (_OUT_DIR / "codings_long.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    failed = [r for r in rows if not (r["evidence_verified"].startswith("ok")
                                      or r["evidence_verified"].startswith("no_code"))]
    with (_OUT_DIR / "evidence_failures.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(failed)

    # per-turn label sets, counting only labels whose evidence verified
    turns: dict[tuple, dict] = {}
    for tr in corpus:
        for t in tr.turns:
            if t.is_participant:
                turns[(tr.run, t.turn_id)] = {
                    "condition": tr.condition, "run": tr.run,
                    "n_words": t.n_words, "n_clauses": t.n_clauses,
                    "labels": set(), "no_code": False, "failed": 0, "normalized": 0}
    for r in rows:
        k = (r["run"], r["turn_id"])
        if k not in turns:
            continue
        v = r["evidence_verified"]
        if v.startswith("ok"):
            turns[k]["labels"].add(r["label"])
            if v == "ok_normalized_punctuation":
                turns[k]["normalized"] += 1
        elif v.startswith("no_code"):
            turns[k]["no_code"] = True
        else:
            turns[k]["failed"] += 1

    def summarise(sel) -> dict:
        sub = [v for v in turns.values() if sel(v)]
        n = len(sub)
        def pct(f) -> str:
            c = sum(1 for v in sub if f(v))
            return f"{100*c/n:.1f}% ({c}/{n})" if n else "-"
        L = lambda v: v["labels"]
        return {
            "n_participant_turns": n,
            "mean_words_per_turn": round(sum(v["n_words"] for v in sub)/max(1, n), 1),
            "mean_clauses_per_turn": round(sum(v["n_clauses"] for v in sub)/max(1, n), 1),
            "agreement_only": pct(lambda v: "agreement" in L(v)
                                  and "disagreement" not in L(v) and "challenge" not in L(v)),
            "disagreement_only": pct(lambda v: "disagreement" in L(v)
                                     and "agreement" not in L(v) and "challenge" not in L(v)),
            "mixed_agree_and_disagree": pct(lambda v: "agreement" in L(v)
                                            and "disagreement" in L(v)),
            "challenge_any": pct(lambda v: "challenge" in L(v)),
            "neutral_elaboration_any": pct(lambda v: "neutral_elaboration" in L(v)),
            "neutral_only": pct(lambda v: L(v) == {"neutral_elaboration"}),
            "relational_any": pct(lambda v: bool(L(v) & set(RELATIONAL))),
            "no_code_applicable": pct(lambda v: v["no_code"] and not L(v)),
            "labels_per_100_clauses": round(
                100*sum(len(L(v)) for v in sub)/max(1, sum(v["n_clauses"] for v in sub)), 2),
            "turns_with_an_evidence_failure": pct(lambda v: v["failed"] > 0),
            "turns_with_a_normalized_quote": pct(lambda v: v["normalized"] > 0),
        }

    conditions = ["human", "enriched", "demographics-only"]
    summary = {c: summarise(lambda v, c=c: v["condition"] == c) for c in conditions}
    per_run = {tr.run: summarise(lambda v, r=tr.run: v["run"] == r) for tr in corpus}
    mod_excluded = {tr.run: sum(1 for t in tr.turns if not t.is_participant)
                    for tr in corpus}

    out = {
        "namespace": "CONSENSUS_FUNCTION_LLM_EXPLORATORY",
        "status": "LLM_CODED_HUMAN_VALIDATION_REQUIRED",
        "generated_utc": datetime.now(UTC).isoformat(),
        "fg": fg,
        "denominator": "participant turns only; moderator turns excluded (counts below)",
        "moderator_turns_excluded": mod_excluded,
        "cells_are_not_exclusive": (
            "agreement_only / disagreement_only / mixed / no_code are mutually "
            "exclusive; challenge_any, neutral_elaboration_any and relational_any "
            "overlap with them. Percentages do not sum to 100 by design."),
        "effective_request_config": effective,
        "prompt_sha256": _sha(_SYSTEM_PROMPT),
        "by_condition": summary,
        "by_run": per_run,
        "repeatability_probe": probe,
        "api_calls": call_log,
    }
    (_OUT_DIR / "summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    with (_OUT_DIR / "summary_by_condition.csv").open("w", newline="", encoding="utf-8") as fh:
        keys = list(next(iter(summary.values())).keys())
        w = csv.writer(fh)
        w.writerow(["condition"] + keys)
        for c in conditions:
            w.writerow([c] + [summary[c][k] for k in keys])
        for r, s in per_run.items():
            w.writerow([r] + [s[k] for k in keys])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fg", default="fg1")
    ap.add_argument("--dry-run", action="store_true",
                    help="verify inputs, blinding and chunking; make no API call")
    args = ap.parse_args()

    if not args.dry_run:
        res = run_live(args.fg)
        p = res["probe"]
        print(f"CONSENSUS_FUNCTION_LLM_EXPLORATORY — live, {args.fg}")
        print(f"  rows written        : {res['rows']}")
        print(f"  repeatability probe : {p['pct_turns_identical']}% of "
              f"{p['n_turns']} turns identical across {p['n_observations']} observations; "
              f"mean Jaccard {p['mean_pairwise_jaccard_vs_baseline']}")
        print(f"  wrote {(_OUT_DIR / 'summary.json').relative_to(_REPO_ROOT)}")
        return 0

    m = dry_run(args.fg)
    print(f"CONSENSUS_FUNCTION_LLM_EXPLORATORY — dry run, {m['fg']}")
    print(f"  status              : {m['status']}")
    print(f"  model               : {m['evaluator']['model']}")
    print(f"  temperature         : NOT TRANSMITTED (unsupported on this model)")
    print(f"  thinking_config     : NOT TRANSMITTED (label 'medium' is logging only)")
    print(f"  safety_settings     : NOT TRANSMITTED (API defaults)")
    print(f"  max_output_tokens   : {m['effective_request_config']['max_output_tokens']}")
    print(f"  prompt sha256       : {m['prompt_sha256'][:16]}...")
    print()
    print(f"  {'condition':<19}{'run':<30}{'P turns':>8}{'mod':>5}"
          f"{'w/turn':>8}{'cl/turn':>9}{'chunks':>8}")
    for t in m["transcripts"]:
        print(f"  {t['condition']:<19}{t['run']:<30}{t['participant_turns']:>8}"
              f"{t['moderator_turns_excluded']:>5}"
              f"{t['mean_words_per_participant_turn']:>8}"
              f"{t['mean_clauses_per_participant_turn']:>9}{t['chunks']:>8}")
    tot = sum(t["participant_turns"] for t in m["transcripts"])
    print(f"\n  participant turns to code : {tot}")
    print(f"  ESTIMATED API CALLS       : {m['estimated_api_calls']}")
    print(f"\n  wrote {(_OUT_DIR / 'dry_run_manifest.json').relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
