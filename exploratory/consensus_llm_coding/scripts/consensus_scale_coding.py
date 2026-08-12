"""
Consensus scales by guide question (namespace: CONSENSUS_SCALE_LLM_EXPLORATORY).

STATUS: LLM_CODED_HUMAN_VALIDATION_REQUIRED. Not a validated measure.

Three stages, per the researcher's specification of 2026-08-06:

  A  EXTRACT   Gemini extracts key claims per guide question from each transcript.
  B  POOL      Candidates from ALL transcripts are deduplicated into ONE shared
               claim set per guide question (the researcher chose the pooled
               shared anchor over per-transcript claims), so every condition is
               scored against the same objects and the comparison is about
               content, not merely about the value of a statistic.
  C  SCORE     Each participant's stance on each pooled claim, ordinal:
                 +1 strong agreement / explicit validation
                  0 neutral or no clear position
                 -1 strong disagreement / objection
               plus two NON-stance outcomes that must never be folded into 0:
                 not_addressed      spoke in the section, took no position
                 absent_from_section  never spoke in the section (DETERMINISTIC,
                                      computed in Python, never asked of the model)
  D  METRICS   Dispersion / concentration per transcript x guide section.

WHY not_addressed IS A SEPARATE VALUE. Synthetic participant turns average 232
words against 48 human. Synthetic participants touch nearly every claim; human
participants do not. Coding "never mentioned it" as 0 would fill the human cells
with zeros, depress human dispersion and manufacture human consensus. That is the
same length asymmetry that invalidated the turn-level layer, arriving by another
door. Dispersion is computed ONLY over participants with a stance in {-1,0,+1},
and coverage is reported beside every statistic as a result in its own right.

WHY THERE IS NO COEFFICIENT OF VARIATION. CV = SD/mean is undefined or explosive
on a scale whose mean can be exactly zero and which crosses zero. It was in the
original specification and is deliberately not implemented.

This is NOT Tier 1 / Tier 2 / Tier 2B, and NOT CONSENSUS_DYNAMICS_EXPLORATORY
(frozen lexicon, zero API calls). Results are never aggregated with either.

Sections come from scripts/tier2b_segmentation.py, the Tier 2B segmenter, which
also supplies the blind `Participant N` render. Only sections comparable on both
sides are used. READ-ONLY: nothing is generated, no session log is written.

Usage:
    py scripts/consensus_scale_coding.py --dry-run --fg fg1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tier2b_segmentation import (                                   # noqa: E402
    SegmentationResult,
    comparable_sections,
    segment_human_by_guide,
    segment_synthetic_by_guide,
)

_FROZEN = _REPO_ROOT / "analysis" / "production_evaluation" / "frozen_evaluator_inputs.json"
_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"
_HUMAN_DIR = _REPO_ROOT / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_scale"
_CACHE_DIR = _OUT_DIR / "cache"

REQUIRED_MODEL = "gemini-3.5-flash"
EVALUATOR_KEY = "gemininext"
MAX_OUTPUT_TOKENS = 16384

CLAIMS_PER_SECTION_PER_TRANSCRIPT = 2      # the researcher's specification
MAX_POOLED_CLAIMS_PER_SECTION = 8          # cap; drops are logged, never silent
STANCES = (1, 0, -1)
MIN_QUOTE_WORDS = 3


class ConsensusScaleError(RuntimeError):
    """Raised when a guard on model, inputs or schema fails."""


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Prompts. FROZEN at the first live call; hashed into every cache key.
# Neither mentions humans, AI, synthesis or conditions.
# ---------------------------------------------------------------------------
_EXTRACT_PROMPT = """\
You are analysing a group discussion that follows a discussion guide. The excerpt
for each guide question is given separately.

For EACH guide question shown, identify exactly {k} KEY CLAIMS made in that
section. A key claim is a substantive, contestable proposition about the topic —
something a participant could agree or disagree with.

A good claim:
  * is a complete proposition, not a topic label
    GOOD: "The pub is the default place to meet because it requires no planning"
    BAD:  "Pubs"
  * is contestable — someone could reasonably take the opposite position
  * is stated in neutral third-person terms, NOT attributed to any speaker, and
    NOT quoting the discussion's wording verbatim
  * is about the substance of the topic, not about the conversation itself

Each claim must carry an `evidence_quote`: a VERBATIM, EXACT substring of that
section's text, at least 3 words, copied character for character, showing where
the claim comes from.

OUTPUT — JSON only, no prose, no code fences:

{{"sections": [
  {{"section_index": 1,
    "claims": [
      {{"claim": "...", "evidence_quote": "..."}}
    ]}}
]}}
"""

_POOL_PROMPT = """\
You are consolidating candidate claims about ONE discussion-guide question. The
candidates were drawn from several independent discussions of the same question.

Merge candidates that express the SAME underlying proposition into a single
claim, even when they are worded differently. Keep genuinely distinct
propositions separate. Do not invent claims that no candidate expressed, and do
not drop a distinct proposition merely because only one candidate raised it.

Write each merged claim in neutral third-person terms, so it can be presented to
a reader who has not seen any of the discussions.

For each merged claim list `source_ids`: the ids of every candidate it merges.
Every candidate id must appear in exactly one merged claim.

OUTPUT — JSON only, no prose, no code fences:

{"claims": [{"claim": "...", "source_ids": ["c1", "c4"]}]}
"""

_SCORE_PROMPT = """\
You are rating the position each participant takes on a set of claims, using ONLY
the discussion excerpt provided.

For EVERY participant listed and EVERY claim listed, assign exactly one value:

  1   strong agreement or explicit validation — the participant endorses the claim
 -1   strong disagreement or objection — the participant contradicts the claim
  0   neutral, mixed, or no clear position, ALTHOUGH the participant did speak to
      this subject
  not_addressed   the participant never spoke to this claim's subject at all

The distinction between 0 and not_addressed is critical and must not be blurred.
Use 0 ONLY when the participant engaged the subject and their position is neutral,
balanced or unclear. Use not_addressed when they simply never touched it. If in
doubt about whether they touched it, choose not_addressed.

For every value that is NOT not_addressed, give an `evidence_quote`: a VERBATIM,
EXACT substring of THAT PARTICIPANT'S OWN words in this excerpt, at least 3 words,
copied character for character. For not_addressed, the quote must be null.

OUTPUT — JSON only, no prose, no code fences:

{"ratings": [
  {"participant": "Participant 1", "claim_id": "s1c1",
   "stance": 1, "evidence_quote": "..."},
  {"participant": "Participant 2", "claim_id": "s1c1",
   "stance": "not_addressed", "evidence_quote": null}
]}

Return exactly one rating for every participant x claim combination.
"""


def generation_config(system_prompt: str) -> dict:
    """The generation config actually transmitted. Single source of truth."""
    return {
        "system_instruction": system_prompt,
        "response_mime_type": "application/json",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        # temperature / thinking_config / safety_settings: deliberately absent.
        # temperature is NOT supported on gemini-3.5-flash in this project, so
        # sampling is unpinned and the cache freezes a first answer rather than
        # demonstrating reproducibility. Stage A is the step most exposed to this,
        # which is what the extraction-stability probe measures.
    }


def effective_request_config(stage: str) -> dict:
    gen = generation_config("")
    if "temperature" in gen or "thinking_config" in gen:
        raise ConsensusScaleError(
            "generation_config now transmits temperature or thinking_config; the "
            "frozen design records both as omitted. Re-declare before running.")
    return {
        "execution_mode": "synchronous", "stage": stage,
        "model": REQUIRED_MODEL,
        "response_mime_type": gen["response_mime_type"],
        "max_output_tokens": gen["max_output_tokens"],
        "temperature_transmitted": False, "temperature": None,
        "thinking_config_transmitted": False, "thinking_config": None,
        "thinking_level_effective": "model_default_unpinned",
        "safety_settings_transmitted": False,
    }


def guard_model() -> dict:
    import thematic_coding as tc
    ecfg = tc.EVALUATOR_CONFIGS.get(EVALUATOR_KEY)
    if ecfg is None or ecfg["model"] != REQUIRED_MODEL:
        raise ConsensusScaleError(
            f"EVALUATOR_CONFIGS[{EVALUATOR_KEY!r}] is not {REQUIRED_MODEL!r}. "
            f"gemini-2.5-flash is DISQUALIFIED.")
    if ecfg.get("temperature") is not None:
        raise ConsensusScaleError(
            "EVALUATOR_CONFIGS now carries a temperature for gemini-3.5-flash; "
            "the frozen design records it as not transmitted.")
    return ecfg


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
@dataclass
class Cell:
    """One transcript, segmented into guide sections."""
    fg: str
    condition: str
    run: str
    seg: SegmentationResult
    source_path: Path
    participants_by_section: dict[int, list[str]] = field(default_factory=dict)
    masked_lines: dict[int, list[str]] = field(default_factory=dict)
    name_substitutions: int = 0


def mask_in_text_names(seg: SegmentationResult, sections: list[int]
                       ) -> tuple[dict[int, list[str]], int]:
    """
    Mask real first names occurring INSIDE utterance text.

    tier2b_segmentation masks the speaker LABEL but leaves names in the text. Over
    comparable sections 1-5 of FG1 that is 1 occurrence on the human side against
    44-77 per synthetic run: participants in the synthetic sessions address each
    other by name constantly and the humans barely do, so the raw name density is
    itself a condition signal. Left alone it would also let the scorer resolve
    "Amir said" to a real identity.

    Fixed HERE, by post-processing the segmenter's output. tier2b_segmentation is
    not modified — it is built architecture, and Tier 2B's own results were
    produced with its current behaviour. The finding is reported instead.
    """
    pairs = sorted(((n, m) for n, m in seg.speaker_map.items() if n != "Moderator"),
                   key=lambda kv: -len(kv[0]))
    patterns = [(re.compile(rf"\b{re.escape(n)}\b"), m) for n, m in pairs]
    out: dict[int, list[str]] = {}
    total = 0
    for i in sections:
        lines = []
        for line in seg.sections[i].blind_lines:
            head, sep, body = line.partition(": ")
            for pat, repl in patterns:
                body, k = pat.subn(repl, body)
                total += k
            lines.append(head + sep + body)
        out[i] = lines
    return out, total


def _whitelist(fg: str) -> list[dict]:
    frozen = json.loads(_FROZEN.read_text(encoding="utf-8"))
    rows = [{"condition": "human", "run": f"{fg}_human", "path": r["path"]}
            for r in frozen["human_inputs"] if r["fg"] == fg]
    rows += [{"condition": r["condition"], "run": r["physical_run"],
              "path": r["path"]} for r in frozen["synthetic_inputs"] if r["fg"] == fg]
    if not rows:
        raise ConsensusScaleError(f"No whitelisted inputs for {fg!r}.")
    return rows


def _participants_in(seg: SegmentationResult, idx: int) -> list[str]:
    """
    Participants who actually SPOKE in this section. Deterministic — never asked
    of the model. A participant absent here can hold no stance, and is recorded as
    absent_from_section rather than as a neutral 0.
    """
    seen = []
    for line in seg.sections[idx].blind_lines:
        m = re.match(r"\[[^\]]+\]\s+(Participant \d+):", line)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def load_cells(fg: str) -> tuple[list[Cell], list[int], list[dict]]:
    """
    Segment every whitelisted transcript for `fg`. Guide source is each synthetic
    run's own executed guide (session_state_initial.json), as in the prior layer;
    the human transcript is segmented against the same guide.

    Reading session logs is read-only and is how tier2b_segmentation locates
    synthetic boundaries. Nothing under output/session_logs/ is written.
    """
    rows = _whitelist(fg)
    synth = [r for r in rows if r["condition"] != "human"]
    guide = _SESSION_LOGS / synth[0]["run"] / "session_state_initial.json"
    human_path = _HUMAN_DIR / fg / "transcript.json"

    human_seg = segment_human_by_guide(human_path, guide)
    cells: list[Cell] = []
    comparable: set[int] | None = None
    skips: list[dict] = []

    for r in rows:
        if r["condition"] == "human":
            seg, src = human_seg, human_path
        else:
            src = _SESSION_LOGS / r["run"] / "transcript.json"
            seg = segment_synthetic_by_guide(
                src, _SESSION_LOGS / r["run"] / "session_state_initial.json")
            comp, sk = comparable_sections(human_seg, seg)
            skips.extend([dict(s, run=r["run"]) for s in sk])
            comparable = set(comp) if comparable is None else comparable & set(comp)
        cells.append(Cell(fg=fg, condition=r["condition"], run=r["run"],
                          seg=seg, source_path=src))

    sections = sorted(comparable or set())
    for c in cells:
        c.participants_by_section = {i: _participants_in(c.seg, i) for i in sections}
        c.masked_lines, c.name_substitutions = mask_in_text_names(c.seg, sections)
    return cells, sections, skips


# ---------------------------------------------------------------------------
# Stage D — metrics. Deterministic, no model.
# ---------------------------------------------------------------------------
def leik_consensus(counts: dict[int, int]) -> float | None:
    """
    Leik (1966) ordinal consensus, on the ordered scale (-1, 0, +1).

    Cumulative proportions F_i; d_i = F_i if F_i <= 0.5 else 1 - F_i;
    D = sum(d_i); maximum D for K categories is (K-1)/2; consensus = 1 - D/maxD.
    1.0 = every rater in one category, 0.0 = maximum dispersion.

    Preferred over the standard deviation because the scale is ORDINAL: SD assumes
    the step +1 -> 0 is the same size as 0 -> -1. Both are reported; neither is
    presented as the other.
    """
    n = sum(counts.values())
    if n == 0:
        return None
    ordered = [-1, 0, 1]
    cum, D = 0.0, 0.0
    for cat in ordered[:-1]:                 # last cumulative is always 1.0
        cum += counts.get(cat, 0) / n
        D += cum if cum <= 0.5 else 1.0 - cum
    max_d = (len(ordered) - 1) / 2
    return round(1.0 - D / max_d, 4)


def claim_metrics(stances: list[int], n_present: int, n_not_addressed: int) -> dict:
    """
    Dispersion over participants WITH a stance. Coverage is reported beside it and
    is part of the result: a claim with n=2 stances and near-zero dispersion is not
    evidence of consensus.
    """
    counts = {s: stances.count(s) for s in STANCES}
    n = len(stances)
    mode_n = max(counts.values()) if n else 0
    modes = [s for s, c in counts.items() if c == mode_n and n]
    return {
        "n_with_stance": n,
        "n_present_in_section": n_present,
        "n_not_addressed": n_not_addressed,
        "n_absent_from_section": None,       # filled by the caller
        "coverage_of_present": round(n / n_present, 3) if n_present else None,
        "count_plus1": counts[1], "count_zero": counts[0], "count_minus1": counts[-1],
        "mean_stance_DIRECTION": round(statistics.fmean(stances), 3) if n else None,
        "sd_stance_interval_assumption": (
            round(statistics.pstdev(stances), 3) if n > 1 else (0.0 if n == 1 else None)),
        "mode_stance": modes if n else None,
        "mode_is_tied": len(modes) > 1 if n else None,
        "proportion_in_mode": round(mode_n / n, 3) if n else None,
        "leik_consensus_ORDINAL": leik_consensus(counts),
    }


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------
def dry_run(fg: str) -> dict:
    guard_model()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    cells, sections, skips = load_cells(fg)

    if not sections:
        raise ConsensusScaleError("No section is comparable across all cells.")

    # --- self-checks on real corpus -----------------------------------------
    for c in cells:
        for i in sections:
            if i not in c.seg.sections:
                raise ConsensusScaleError(f"{c.run} lacks comparable section {i}.")
            if not c.participants_by_section[i]:
                raise ConsensusScaleError(
                    f"{c.run} section {i}: no participant lines parsed — the "
                    f"blind-render speaker pattern does not match.")
        blob = "\n".join(l for i in sections for l in c.masked_lines[i])
        for leak in ("timestamp", "selection_mode", "source_file", "speaker_role"):
            if leak in blob:
                raise ConsensusScaleError(f"{c.run}: {leak!r} survives in blind text.")
        for real_name in c.seg.speaker_map:
            if real_name != "Moderator" and re.search(rf"\b{re.escape(real_name)}\b", blob):
                raise ConsensusScaleError(
                    f"{c.run}: unmasked speaker name {real_name!r} in blind text.")

    # Leik sanity, against hand-computable cases
    if leik_consensus({1: 5, 0: 0, -1: 0}) != 1.0:
        raise ConsensusScaleError("Leik: unanimity must be 1.0")
    if leik_consensus({1: 0, 0: 5, -1: 0}) != 1.0:
        raise ConsensusScaleError("Leik: unanimity on the middle must be 1.0")
    if leik_consensus({1: 3, 0: 0, -1: 3}) != 0.0:
        raise ConsensusScaleError("Leik: an even split on the poles must be 0.0")
    if not 0.0 < leik_consensus({1: 2, 0: 1, -1: 2}) < 1.0:
        raise ConsensusScaleError("Leik: a mixed distribution must be interior")

    n_cells = len(cells)
    calls = {
        "A_extract_per_transcript": n_cells,
        "B_pool_per_section": len(sections),
        "C_score_per_transcript_section": n_cells * len(sections),
    }
    calls["subtotal"] = sum(calls.values())
    calls["D_extraction_stability_probe"] = 4
    calls["total"] = calls["subtotal"] + calls["D_extraction_stability_probe"]

    manifest = {
        "namespace": "CONSENSUS_SCALE_LLM_EXPLORATORY",
        "status": "LLM_CODED_HUMAN_VALIDATION_REQUIRED",
        "generated_utc": datetime.now(UTC).isoformat(),
        "fg": fg,
        "anchor": "pooled_shared_claim_set_per_guide_question",
        "scale": {"+1": "strong agreement / explicit validation",
                  "0": "neutral or no clear position, having engaged the subject",
                  "-1": "strong disagreement / objection",
                  "not_addressed": "spoke in the section, never touched the claim",
                  "absent_from_section": "never spoke in the section (deterministic)"},
        "no_coefficient_of_variation": (
            "CV = SD/mean is undefined or explosive on a scale whose mean can be "
            "zero and which crosses zero. Dropped by design."),
        "comparable_sections": [
            {"section_index": i,
             "section_label": cells[0].seg.sections[i].section_label} for i in sections],
        "sections_skipped": skips,
        "effective_request_config": {s: effective_request_config(s)
                                     for s in ("extract", "pool", "score")},
        "prompt_sha256": {"extract": _sha(_EXTRACT_PROMPT), "pool": _sha(_POOL_PROMPT),
                          "score": _sha(_SCORE_PROMPT)},
        "estimated_api_calls": calls,
        "cells": [],
    }
    for c in cells:
        manifest["cells"].append({
            "condition": c.condition, "run": c.run,
            "source": str(c.source_path.relative_to(_REPO_ROOT)),
            "in_text_names_masked_by_this_layer": c.name_substitutions,
            "sections": {str(i): {
                "participant_turns": c.seg.sections[i].participant_turns,
                "participant_words": c.seg.sections[i].participant_words,
                "participants_present": c.participants_by_section[i],
                "n_present": len(c.participants_by_section[i]),
            } for i in sections},
        })
    (_OUT_DIR / "dry_run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    for name, p in (("extract", _EXTRACT_PROMPT), ("pool", _POOL_PROMPT),
                    ("score", _SCORE_PROMPT)):
        (_OUT_DIR / f"prompt_{name}_frozen.txt").write_text(p, encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fg", default="fg1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.dry_run:
        print("Live coding is not enabled in this revision. Run with --dry-run.\n"
              "A live run must be approved with a call-count estimate first.")
        return 2

    m = dry_run(args.fg)
    print(f"CONSENSUS_SCALE_LLM_EXPLORATORY — dry run, {m['fg']}")
    print(f"  status  : {m['status']}")
    print(f"  anchor  : {m['anchor']}")
    print(f"  model   : {REQUIRED_MODEL} (temperature NOT transmitted)")
    print(f"\n  comparable guide sections: "
          f"{[s['section_index'] for s in m['comparable_sections']]}")
    for s in m["comparable_sections"]:
        print(f"    {s['section_index']}  {s['section_label']}")
    print(f"\n  {'condition':<19}{'run':<31}" +
          "".join(f"s{s['section_index']}" .rjust(7) for s in m["comparable_sections"]))
    for c in m["cells"]:
        cells = "".join(
            f"{c['sections'][str(s['section_index'])]['n_present']}p".rjust(7)
            for s in m["comparable_sections"])
        print(f"  {c['condition']:<19}{c['run']:<31}{cells}")
    print("\n  (np = participants who actually spoke in that section, of 5)")
    k = m["estimated_api_calls"]
    print(f"\n  ESTIMATED API CALLS")
    print(f"    A extract  (1 per transcript)          : {k['A_extract_per_transcript']}")
    print(f"    B pool     (1 per guide section)       : {k['B_pool_per_section']}")
    print(f"    C score    (1 per transcript x section): {k['C_score_per_transcript_section']}")
    print(f"    D stability probe                      : {k['D_extraction_stability_probe']}")
    print(f"    TOTAL                                  : {k['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
