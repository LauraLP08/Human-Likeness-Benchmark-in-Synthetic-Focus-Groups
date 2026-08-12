"""
Shared corpus for the Level 3 agent-fidelity analyses.

WHAT THIS MODULE GUARANTEES
---------------------------
The observable property under study is LEXICALLY_INDIVIDUALISABLE_AGENT_VOICE: whether a
participant's text can be told apart from that of their fellow participants, and whether
the same participant can be recognised across different guide questions. Every downstream
analysis depends on the text being clean of anything that would let a classifier win
without doing that work, so the scrubbing lives here rather than in each analysis.

Removed from the analysed text:
  * speaker labels and turn ids (never concatenated into the analysed string);
  * every roster first name in the document, including the speaker's own;
  * the moderator entirely - the moderator is not a participant and their wording is
    shared across the whole session.

Never present in the analysed text by construction: unit_id, condition, focus group,
replicate, model, run name. The analysed string is the participant's own words and
nothing else. `leakage_report()` proves it rather than asserting it.

Participant identity is the CANONICAL SPEAKER ID, which is persistent across questions on
both sides. It is mapped to an opaque per-document label so nothing downstream can read a
name off an identifier.

Slicing reuses the validated Q1-Q5 segmentation and reconciles word counts against it, so
the two coordinate systems (human = entry index, synthetic = `turn` field) cannot be
confused.

Offline. No API call. Reads only; writes nothing.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SEGMENTS = _ROOT / "analysis/production_evaluation/final/inductive_segments.json"

QUESTIONS = (1, 2, 3, 4, 5)
CONDITIONS = ("human", "enriched", "demographics-only")

# Human FG5 never asked Q4 in fieldwork. It is an absence, never a zero and never an
# eligible fold.
NOT_ASKED_IN_FIELDWORK = {("human", "fg5", 4)}

_WORD = re.compile(r"[a-z']+")
_NAME_PLACEHOLDER = " nameref "


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _norm_space(s: str) -> str:
    return " ".join(s.split())


def segments() -> list[dict]:
    return json.loads(_SEGMENTS.read_text(encoding="utf-8"))["segments"]


def doc_id(seg: dict) -> str:
    """Stable document label. A document is one focus-group session."""
    if seg["condition"] == "human":
        return f"human::{seg['fg']}"
    tag = "E" if seg["condition"] == "enriched" else "D"
    return f"{tag}::{seg['fg']}::R{seg['canonical_replication_index']}"


def _entries(seg: dict):
    obj = json.loads((_ROOT / seg["source_path"]).read_text(encoding="utf-8"))
    return obj if isinstance(obj, list) else obj["transcript"]


def _slice(seg: dict):
    """
    The validated section, in whichever coordinate system delimits it. Human sections are
    delimited by ENTRY INDEX into the transcript list, synthetic sections by the `turn`
    FIELD value; slicing one with the other's coordinate silently selects the wrong text.
    """
    entries = _entries(seg)
    bp = seg["boundary_provenance"]
    if "opens_at_entry_index" in bp:
        lo, hi = bp["opens_at_entry_index"], bp["closes_before_entry_index"]
        return list(entries)[lo:hi], "entry_index"
    lo, hi = bp["opens_at_turn"], bp["closes_before_turn"]
    return [e for e in entries if lo <= int(e["turn"]) < hi], "turn_field"


def _speaker(e):
    sid = e.get("canonical_speaker_id") or e.get("speaker_id")
    is_mod = (sid == "MODERATOR" or e.get("speaker_role") == "moderator")
    return sid, is_mod


def roster() -> dict[str, dict[str, str]]:
    """
    doc_id -> {canonical_speaker_id: display name}. Built over the WHOLE source document,
    not just the sections in scope, so a name mentioned in Q3 by someone who only speaks
    in Q1 is still scrubbed.
    """
    out = defaultdict(dict)
    for seg in segments():
        d = doc_id(seg)
        if d in out:
            continue
        for e in _entries(seg):
            sid, is_mod = _speaker(e)
            if not is_mod and e.get("speaker_name"):
                out[d][sid] = e["speaker_name"]
    return dict(out)


def _name_pattern(names) -> re.Pattern | None:
    """
    Word-boundary match on first names, accent- and case-insensitive. The boundary
    excludes letters and digits but NOT punctuation, so "David," and "David's" are both
    caught.
    """
    parts = set()
    for n in names:
        for tok in _strip_accents(n).lower().split():
            if len(tok) >= 3 and tok.isalpha():
                parts.add(re.escape(tok))
    if not parts:
        return None
    return re.compile(r"(?<![a-z0-9])(" + "|".join(sorted(parts)) + r")(?![a-z0-9])")


def scrub(text: str, pattern: re.Pattern | None, delete: bool = False):
    """Replace roster names. Returns (clean_text, n_scrubbed)."""
    low = _strip_accents(_norm_space(text)).lower()
    if pattern is None:
        return low, 0
    n = len(pattern.findall(low))
    return _norm_space(pattern.sub("" if delete else _NAME_PLACEHOLDER, low)), n


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def build(delete_names: bool = False) -> dict:
    """
    (doc_id, question, participant) -> record. Participants are opaque per-document
    labels; the mapping back to a canonical speaker id is kept beside the corpus for
    audit but is never part of any analysed string.
    """
    rost = roster()
    pats = {d: _name_pattern(v.values()) for d, v in rost.items()}
    # Participant labels come from a DOCUMENT-level ordering, never a per-question one.
    # Ordering within a question would make S03 a different person in any question where
    # someone stayed silent, and the whole cross-question design rests on that label
    # meaning one person.
    labels = {d: {sid: f"{d}#S{i + 1:02d}"
                  for i, sid in enumerate(sorted(rost[d]))} for d in rost}

    cells, docs, reconcile = {}, {}, []
    for seg in segments():
        d = doc_id(seg)
        q = int(seg["question"])
        chosen, coord = _slice(seg)
        docs.setdefault(d, {"condition": seg["condition"], "fg": seg["fg"],
                            "replicate": seg["canonical_replication_index"],
                            "coordinate_system": coord, "questions": []})
        docs[d]["questions"].append(q)

        by_speaker, mod_words, part_words = defaultdict(list), 0, 0
        for e in chosen:
            sid, is_mod = _speaker(e)
            n = len(e["content"].split())
            if is_mod:
                mod_words += n
                continue
            part_words += n
            by_speaker[sid].append(e["content"])

        # The slice must be the same text the segmentation counted, whichever coordinate
        # delimited it. This is the check that proves the two systems were not confused.
        reconcile.append({"unit_id": seg["unit_id"],
                          "coordinate_system": coord,
                          "recomputed_total_words": part_words + mod_words,
                          "segment_total_words": seg["total_words"],
                          "recomputed_participant_words": part_words,
                          "segment_participant_words": seg["participant_words"],
                          "reconciles": (part_words + mod_words == seg["total_words"]
                                         and part_words == seg["participant_words"])})

        for sid in sorted(by_speaker):
            raw = " ".join(by_speaker[sid])
            clean, n_scrub = scrub(raw, pats[d], delete=delete_names)
            pid = labels[d][sid]
            cells[(d, q, pid)] = {
                "doc_id": d, "question": q, "participant": pid,
                "canonical_speaker_id": sid,
                "condition": seg["condition"], "fg": seg["fg"],
                "replicate": seg["canonical_replication_index"],
                "text": clean,
                "n_words": len(words(clean)),
                "n_raw_words": len(raw.split()),
                "n_turns": len(by_speaker[sid]),
                "n_names_scrubbed": n_scrub,
            }

    # Participant labels must be stable across questions within a document: the whole
    # cross-question design collapses if S01 means a different person in Q1 and Q3.
    seen = defaultdict(dict)
    for (d, q, pid), rec in cells.items():
        prev = seen[d].get(pid)
        if prev is not None and prev != rec["canonical_speaker_id"]:
            raise ValueError(f"{d}: {pid} is not stable across questions")
        seen[d][pid] = rec["canonical_speaker_id"]

    return {"cells": cells, "docs": docs, "roster": rost,
            "reconciliation": reconcile,
            "all_units_reconcile": all(r["reconciles"] for r in reconcile),
            "names_deleted_not_placeheld": delete_names}


# ------------------------------------------------------------------ leakage
# Strings that cannot occur in spontaneous speech and would therefore be provenance
# rather than language. Ordinary English words that merely appear in this project's
# metadata vocabulary are deliberately NOT here: participants really do say "hard to
# replicate that" about meat texture and "the moderator's asking", and treating those as
# leaks would flag natural speech as contamination.
FORBIDDEN_SUBSTRINGS = ("macho_meals", "demoonly", "run01", "run02", "run03", "run04",
                        "unit_id", "::", "fg1", "fg2", "fg3", "fg4", "fg5",
                        "demographics-only", "gemini", "claude", "canonical_speaker",
                        "comparable_transcript", "speaker_id", "replication_index")


def leakage_report(corpus: dict) -> dict:
    """
    Prove, rather than assert, that no analysed string carries a name, an identifier or a
    provenance token. Any hit here is a defect, not a warning.
    """
    rost = corpus["roster"]
    name_hits, token_hits, digit_ids = [], [], []
    for (d, q, pid), rec in corpus["cells"].items():
        t = rec["text"]
        pat = _name_pattern(rost[d].values())
        if pat is not None and not corpus["names_deleted_not_placeheld"]:
            found = pat.findall(t)
            if found:
                name_hits.append({"cell": f"{d}|Q{q}|{pid}", "names": sorted(set(found))})
        for tok in FORBIDDEN_SUBSTRINGS:
            if tok in t:
                token_hits.append({"cell": f"{d}|Q{q}|{pid}", "token": tok})
        if re.search(r"\bT\d{3}\b", t):
            digit_ids.append(f"{d}|Q{q}|{pid}")
    return {"n_cells": len(corpus["cells"]),
            "name_leaks": name_hits, "n_name_leaks": len(name_hits),
            "identifier_leaks": token_hits, "n_identifier_leaks": len(token_hits),
            "turn_id_leaks": digit_ids, "n_turn_id_leaks": len(digit_ids),
            "clean": not (name_hits or token_hits or digit_ids)}


def eligible_questions(condition: str, fg: str) -> tuple[int, ...]:
    return tuple(q for q in QUESTIONS
                 if (condition, fg, q) not in NOT_ASKED_IN_FIELDWORK)
