"""
Derive the comparable window for the synthetic mindfulness run and compute the
frozen structural metrics on both sides.

Offline only. No API calls. Nothing under output/session_logs/ is written.

PORTABILITY NOTE — the reason this script exists at all.
scripts/build_comparable_window.py could not be reused. Two of its parts are
bound to Macho Meals:

  1. WHITELIST — a hardcoded list of the 30 canonical Macho Meals runs. A run
     outside it cannot be processed.
  2. scripts/comparable_window_boundary.Q1_DISTINCTIVE — the token set
     {"favourite", "favorite", "place", "city", "friends", "spend", "male"},
     i.e. the content words of the Macho Meals Question 1.

Neither file is modified here; both produced frozen results.

BOUNDARY METHOD — and why it is not the frozen one.
Keyword anchoring with a mindfulness Q1 token set was tried first and FAILED:
the guide's welcome text contains "mindfulness" and "components", so the token
set also matched the opening entry, placing the boundary at turn 0 and admitting
the welcome, the instructions and the closing into the window. The residue gate
caught it. Both boundaries are therefore derived from the recorded
`session_meta.current_section_index` in the per-turn state snapshots, which
carries no domain vocabulary: entries in an `intro` or `closing` phase section
are excluded, everything between is retained. Sub-entry trimming of the first
retained moderator entry still uses the token set, and the residue gate still
reports on the retained text.

That the frozen boundary rule depends on the guide's first question being
lexically distinct from its own welcome text — true in Macho Meals, false in
DS05 — is itself a portability finding.

Usage:
    py scripts/transportability_synthetic_window.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.structural_metrics_transportability import (  # noqa: E402
    _load_baseline,
    _MINDFULNESS,
    _MINDFULNESS_Q1_ANCHOR,
    _tokens,
    _wc,
    compute,
)

_RUN = "mindfulness_fg1_run01"
_LOG_DIR = _ROOT / "output/session_logs" / _RUN
_OUT_DIR = _ROOT / "analysis/transportability_mindfulness"

# Content words of the mindfulness guide's first substantive question, standing
# in for Q1_DISTINCTIVE. Derived from the scripted question in
# configs/guides/mindfulness_self_administered_intervention.yaml, not invented.
_Q1_DISTINCTIVE = {
    "adapt", "adapted", "traditional", "mindfulness", "online", "format",
    "mbsr", "efficacy", "components", "acceptance", "protocol",
}
_Q1_MIN_HITS = 2

_ASK_LEAD_IN = re.compile(
    r"^(right|ok|okay|so|now|alright|let's|first|to start|starting)\b", re.IGNORECASE
)

# Residue classes the dropped prefix is expected to carry, mirroring the classes
# enumerated in analysis/production_evaluation/comparable_window_boundaries.md.
_RESIDUE_MARKERS = {
    "welcome": re.compile(r"\b(welcome|thanks so much|thank you for joining|glad you)\b", re.I),
    "instruction_confidentiality": re.compile(r"\b(recorded|confidential|no right or wrong|ground rules)\b", re.I),
    "presentation_summary": re.compile(r"\b(good to have you|great to hear|quite a spread)\b", re.I),
    "self_introduction": re.compile(r"\b(my name'?s|i'?ll be facilitating|i'?ll be moderating)\b", re.I),
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


def _is_q1(text: str) -> bool:
    return len(_Q1_DISTINCTIVE & set(_tokens(text))) >= _Q1_MIN_HITS


def find_q1_offset(text: str) -> tuple[int | None, dict]:
    """
    Anchor-and-extend, per comparable_window_boundaries.md:
      1. anchor on the LATEST sentence-aligned suffix that still poses Q1;
      2. extend backward one sentence at a time, only across sentences that are
         residue-free AND positively identified as part of the ask;
      3. stop at the first sentence failing either test.
    """
    sentences = _sentences(text)
    if not sentences:
        return None, {"reason": "no sentences"}

    offsets, cursor = [], 0
    for sentence in sentences:
        idx = text.index(sentence, cursor)
        offsets.append(idx)
        cursor = idx + len(sentence)

    anchor = None
    for i in range(len(sentences) - 1, -1, -1):
        if _is_q1(" ".join(sentences[i:])):
            anchor = i
        elif anchor is not None:
            break
    if anchor is None:
        return None, {"reason": "no sentence-aligned suffix poses Q1"}

    extended_over = []
    i = anchor - 1
    while i >= 0:
        sentence = sentences[i]
        residue = [name for name, rx in _RESIDUE_MARKERS.items() if rx.search(sentence)]
        part_of_ask = bool(_Q1_DISTINCTIVE & set(_tokens(sentence))) or bool(
            _ASK_LEAD_IN.match(sentence.strip())
        )
        if residue or not part_of_ask:
            break
        extended_over.append(sentence)
        anchor = i
        i -= 1

    return offsets[anchor], {
        "anchor_sentence_index": anchor,
        "extended_back_sentences": len(extended_over),
        "n_sentences": len(sentences),
    }


def _turn_to_section() -> dict[int, int]:
    """
    Map turn number -> active section index, read from the per-turn state
    snapshots. This is the DOMAIN-NEUTRAL boundary signal and is preferred over
    keyword anchoring, which failed here: the mindfulness guide's welcome text
    contains the words "mindfulness" and "components", so a Q1 token set built
    from the guide's first question also matched the opening entry and placed
    the boundary at turn 0. Section indices carry no domain vocabulary at all.
    """
    mapping: dict[int, int] = {}
    for path in _LOG_DIR.glob("state_turn_*.json"):
        match = re.search(r"state_turn_(\d+)\.json$", path.name)
        if not match:
            continue
        state = json.loads(path.read_text(encoding="utf-8"))
        mapping[int(match.group(1))] = state["session_meta"]["current_section_index"]
    return mapping


def _sections_from_log() -> dict:
    """Section boundaries from moderator_log.json section_transition actions."""
    path = _LOG_DIR / "moderator_log.json"
    if not path.exists():
        return {"available": False}
    log = json.loads(path.read_text(encoding="utf-8"))
    entries = log if isinstance(log, list) else log.get("entries", [])
    transitions = [
        e for e in entries if str(e.get("action") or "").strip() == "section_transition"
    ]
    return {
        "available": True,
        "n_entries": len(entries),
        "section_transitions": [
            {"turn": e.get("turn"), "utterance_head": str(e.get("utterance") or "")[:120]}
            for e in transitions
        ],
    }


# Output-side contamination. Section 3 of the report measures Macho Meals residue
# in the prompts the model RECEIVES; this measures whether any of it reached the
# text the model PRODUCED. The prompt-side measurement alone cannot answer that.
_OUTPUT_CONTAMINATION_TERMS = [
    r"\bmeat\b", r"\bvegan\b", r"\bvegetarian\b", r"\bplant-based\b",
    r"\bsalad\b", r"\bmasculin\w*", r"\bfood\b", r"\bmeal\b", r"\bgrocer\w*",
    r"\bshopping\b", r"\bmates\b", r"\bmacho\b",
]
_OUTPUT_CONTAMINATION_NAMES = [
    r"\bDavid\b", r"\bSam\b", r"\bIsaiah\b", r"\bAmir\b", r"\bIbrahim\b",
]


def _output_contamination(turns: list[dict]) -> dict:
    """Scan generated text for Macho Meals vocabulary and participant names."""
    hits = []
    for entry in turns:
        content = entry.get("content", "")
        for pattern in _OUTPUT_CONTAMINATION_TERMS:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                hits.append({
                    "turn": entry.get("turn"), "speaker": entry.get("speaker_name"),
                    "matched_text": m.group(0), "category": "domain_vocabulary",
                    "context": content[max(0, m.start() - 80): m.end() + 80].replace("\n", " "),
                })
        for pattern in _OUTPUT_CONTAMINATION_NAMES:
            for m in re.finditer(pattern, content):  # case-sensitive, see audit note
                hits.append({
                    "turn": entry.get("turn"), "speaker": entry.get("speaker_name"),
                    "matched_text": m.group(0), "category": "participant_name",
                    "context": content[max(0, m.start() - 80): m.end() + 80].replace("\n", " "),
                })
    return {
        "turns_scanned": len(turns),
        "total_hits": len(hits),
        "hits": hits,
        "interpretation": (
            "Zero hits means the Macho Meals residue measured in the moderator "
            "scaffolding did not propagate into generated text. It does not mean the "
            "residue is harmless in general, only that it did not surface here."
        ),
    }


def _load_synthetic() -> list[dict]:
    turns = json.loads((_LOG_DIR / "transcript.json").read_text(encoding="utf-8"))
    out = []
    for t in turns:
        role = "moderator" if t["speaker_id"] == "MODERATOR" else "participant"
        out.append(
            {
                "turn": t["turn"],
                "speaker_id": t["speaker_id"],
                "canonical_speaker_id": t["speaker_id"],
                "speaker_name": t["speaker_name"],
                "speaker_role": role,
                "content": t["content"],
            }
        )
    return out


def main() -> int:
    if not (_LOG_DIR / "transcript.json").exists():
        print(f"transcript not found yet: {_LOG_DIR / 'transcript.json'}")
        return 1

    synthetic = _load_synthetic()
    roster = sorted({t["speaker_name"] for t in synthetic if t["speaker_role"] == "participant"})

    # --- Boundaries from recorded section indices (domain-neutral) -----------
    turn_section = _turn_to_section()
    if not turn_section:
        print("HUMAN_REVIEW_REQUIRED: no state_turn_*.json snapshots to derive sections from")
        return 2

    guide = json.loads(
        (_ROOT / "configs/experiment/mindfulness_fg1_run01.json").read_text(encoding="utf-8")
    )["discussion_guide"]
    intro_sections = {s["section_index"] for s in guide if s["section_phase"] == "intro"}
    closing_sections = {s["section_index"] for s in guide if s["section_phase"] == "closing"}

    def section_of(entry: dict) -> int | None:
        return turn_section.get(entry["turn"])

    window = [
        dict(t) for t in synthetic
        if section_of(t) is not None
        and section_of(t) not in intro_sections
        and section_of(t) not in closing_sections
    ]
    excluded_intro = [t for t in synthetic if section_of(t) in intro_sections]
    excluded_closing = [t for t in synthetic if section_of(t) in closing_sections]

    if not window:
        print("HUMAN_REVIEW_REQUIRED: window is empty after excluding intro and closing")
        return 2

    boundary_index = synthetic.index(
        next(t for t in synthetic if t["turn"] == window[0]["turn"])
    )
    boundary_entry = window[0]

    # Sub-entry trim: if the first retained entry is a moderator turn that fuses
    # residue in front of the ask, trim it the way the frozen apparatus does.
    boundary_offset, boundary_detail = 0, {"applied": False}
    if boundary_entry["speaker_role"] == "moderator":
        offset, detail = find_q1_offset(boundary_entry["content"])
        if offset:
            boundary_offset, boundary_detail = offset, {"applied": True, **detail}
    dropped_prefix = boundary_entry["content"][:boundary_offset]
    retained = boundary_entry["content"][boundary_offset:].strip()
    window[0]["content"] = retained

    residue_in_retained = sorted(
        name for name, rx in _RESIDUE_MARKERS.items() if rx.search(retained)
    )
    sections = _sections_from_log()
    closing_index = 0 if excluded_closing else None

    synthetic_metrics = compute(window, roster)
    synthetic_full = compute(synthetic, roster)

    # --- Human side ----------------------------------------------------------
    human_turns, human_names = _load_baseline(_MINDFULNESS)
    anchor_i = next(
        (i for i, t in enumerate(human_turns) if _MINDFULNESS_Q1_ANCHOR in t["content"]), None
    )
    human_window = [dict(t) for t in human_turns]
    if anchor_i is not None:
        entry = human_window[anchor_i]
        off = entry["content"].index(_MINDFULNESS_Q1_ANCHOR)
        entry["content"] = entry["content"][off:].strip()
        human_window = human_window[anchor_i:]
    human_metrics = compute(human_window, human_names)

    report = {
        "record_type": "CROSS_DOMAIN_SYNTHETIC_VS_HUMAN_STRUCTURAL_COMPARISON",
        "classification": "EXPLORATORY_OUT_OF_DOMAIN_TRANSPORTABILITY_CHECK",
        "run": _RUN,
        "no_api_calls": True,
        "portability_note": (
            "scripts/build_comparable_window.py could not be reused: its run WHITELIST and its "
            "Q1_DISTINCTIVE token set are bound to Macho Meals. The algorithm was re-implemented "
            "with a mindfulness Q1 token set derived from the guide. Neither original file was "
            "modified. This substitution is a measured cost of porting the apparatus."
        ),
        "q1_token_set_used": sorted(_Q1_DISTINCTIVE),
        "synthetic_window": {
            "source_transcript_sha256": hashlib.sha256(
                (_LOG_DIR / "transcript.json").read_bytes()
            ).hexdigest(),
            "boundary_method": "recorded section indices (domain-neutral); sub-entry trim only inside the first retained moderator entry",
            "boundary_entry_index": boundary_index,
            "boundary_character_offset": boundary_offset,
            "boundary_detail": boundary_detail,
            "dropped_prefix_verbatim": dropped_prefix.strip(),
            "dropped_prefix_words": _wc(dropped_prefix),
            "retained_boundary_text_verbatim": retained,
            "residue_detected_in_retained_text": residue_in_retained,
            "residue_gate": "PASS" if not residue_in_retained else "REVIEW",
            "excluded_intro_entries": len(excluded_intro),
            "excluded_closing_entries": len(excluded_closing),
            "closing_section_detected": closing_index is not None,
            "closing_detection_caveat": (
                None if closing_index is not None else
                "NO CLOSING SECTION DETECTED. Either the session ended before reaching the "
                "closing section (e.g. the max-turn cap was hit) or the moderator closed with "
                "wording the phrase list does not cover. The END boundary is therefore the end "
                "of the transcript, which is NOT the same rule applied to the Macho Meals runs; "
                "the resulting window may include closing material and is not strictly "
                "comparable. Inspect before reporting."
            ),
            "included_entries": len(window),
        },
        "section_transitions": sections,
        "output_contamination_full_run": _output_contamination(synthetic),
        "metrics_synthetic_window": synthetic_metrics,
        "metrics_synthetic_full_run": synthetic_full,
        "metrics_human_q1_trimmed": human_metrics,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _OUT_DIR / "structural_synthetic_vs_human.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(_ROOT)}\n")

    print(f"boundary entry index {boundary_index}, offset {boundary_offset}, "
          f"dropped {_wc(dropped_prefix)} words, residue gate "
          f"{'PASS' if not residue_in_retained else 'REVIEW ' + str(residue_in_retained)}")
    print(f"excluded closing entries: {len(excluded_closing)}   included: {len(window)}")
    oc = report["output_contamination_full_run"]
    print(f"output contamination (full run, {oc['turns_scanned']} turns): {oc['total_hits']} hits")
    for hit in oc["hits"][:10]:
        print(f"    turn {hit['turn']} {hit['speaker']}: [{hit['matched_text']}] ...{hit['context']}...")
    print()

    keys = [
        "participant_turns", "moderator_turns", "total_words",
        "words_per_turn_median", "words_per_turn_iqr",
        "short_turn_proportion_25w", "turn_balance_gini", "word_balance_gini",
        "moderator_turn_share", "moderator_word_share",
        "participant_participant_adjacency", "chain_depth", "chain_depth_max",
    ]
    print(f"{'metric':38s} {'HUMAN':>10s} {'SYNTH':>10s}   ratio S/H")
    print("-" * 74)
    for key in keys:
        h, s = human_metrics.get(key), synthetic_metrics.get(key)
        ratio = ""
        if isinstance(h, (int, float)) and isinstance(s, (int, float)) and h:
            ratio = f"{s / h:.2f}x"
        print(f"{key:38s} {str(h):>10s} {str(s):>10s}   {ratio}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
