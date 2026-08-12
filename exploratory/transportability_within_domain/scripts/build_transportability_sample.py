"""
SUPPLEMENTARY_SINGLE_CODER_TRANSPORTABILITY_SAMPLE — sampling, boundary audit, package.

WHAT THIS IS NOT
Not a gold standard, and not part of the primary calibration. U01-U07 (guide question
Q3) is the PRIMARY EMERGENT CALIBRATION SAMPLE: two independent coders and an
adjudicated human clustering. This sample has ONE coder and exists only to ask
whether the emergent extractor transports to other guide questions. The two are never
pooled, and no agreement statistic is computed here — one coder cannot produce one.

SELECTION IS BLIND TO EVERYTHING THAT COULD BIAS IT
The frame is enumerated from the frozen inputs and the guide alone. The draw consults
NO Tier-1 metric, no condition effect, no per-FG result and no thematic content. The
only content-adjacent fact consulted is technical feasibility — whether a section
exists and contains at least one participant turn — because an empty unit cannot be
coded at all. Word counts are recorded in the sealed manifest AFTER selection; they
are never an input to it.

The draw is deterministic under a recorded seed. Re-running reproduces the same six
units exactly.

No LLM call of any kind.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import production_eval_pipeline as pep          # noqa: E402
import tier2b_segmentation as seg               # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_DIR = _OUT / "transportability_sample"
_SEALED_DIR = _OUT / "gold_standard_sealed"
_GUIDE = _REPO_ROOT / "configs" / "guides" / "macho_meals_plant_based_masculinity_uk.yaml"

CLASSIFICATION = "SUPPLEMENTARY_SINGLE_CODER_TRANSPORTABILITY_SAMPLE"

# Guide section -> question id. Section 3 is the PRIMARY calibration question and is
# excluded here; 0 and 6 are introduction and closing and are never coded.
QUESTION_SECTIONS = {"Q1": 1, "Q2": 2, "Q4": 4, "Q5": 5}
EXCLUDED_SECTIONS = {0: "introduction", 3: "primary calibration sample (U01-U07)",
                     6: "closing"}

# Distinctive content of each guide question, used to confirm that a section's
# opening turn really does pose that question. Human transcripts carry a literal
# "Question N." header; synthetic moderators paraphrase and never do, which is why a
# header check alone would wrongly condemn every synthetic unit.
QUESTION_MARKERS = {
    "Q1": ("favourite", "favorite", "place", "male friends", "hang out", "spend time"),
    "Q2": ("decide", "what to eat", "choose", "what you eat"),
    "Q4": ("plant-based", "plant based", "change", "go plant"),
    "Q5": ("appealing", "plant-based", "plant based", "more attractive"),
}
MIN_MARKER_HITS = 2

STRATA = ("human", "enriched", "demographics-only")
N_PER_STRATUM = 2
N_UNITS = 6
MIN_DISTINCT_FGS = 4
SYNTHETIC_REPLICATION_INDEX = 2

# New seed, recorded. Changing it changes the sample and must be a deliberate act.
SELECTION_SEED = "macho_meals_transportability_2026-07-31_v1"
SELECTION_ALGORITHM = (
    "1. Enumerate the frame: every (stratum, FG, question) whose guide section exists "
    "and holds >=1 participant turn. 2. Seed Mersenne Twister with "
    "sha256(SELECTION_SEED). 3. Draw candidate samples of 2 per stratum without "
    "replacement, rejecting any sample that fails the coverage constraints "
    "(all four questions present, >=4 distinct FGs). 4. Accept the first sample that "
    "satisfies every constraint; record the attempt number."
)



# ---------------------------------------------------------------------------
# Sub-entry opening boundary and next-question end gate
# ---------------------------------------------------------------------------

# The ask of the question that FOLLOWS each sampled question. A unit must never
# contain the next question's ask after its final boundary: that material belongs to
# the next section and, for Q2, it is the primary-calibration question Q3.
NEXT_QUESTION_ASK = {
    "Q1": ("how do you decide what to eat", "decide what to eat"),
    "Q2": ("does your gender influence", "do you think your gender influences",
           "gender influences what you eat", "your gender influences what you eat"),
    "Q4": ("what might make plant-based foods more appealing",
           "make plant-based foods more appealing", "more appealing to you or other men"),
    "Q5": ("that's our time", "thanks so much for participating"),
}

# A sentence is treated as substantive residue from the PREVIOUS question — and the
# backward extension stops at it — when it addresses a participant by name, reads as
# a recap, or carries another question's content. Everything from that sentence
# backwards is dropped.
RECAP_PATTERNS = (
    "that last bit", "hang onto", "hold onto", "useful shift", "that's a good place",
    "picking up on", "coming back to", "you said", "you were saying", "earlier",
    "cheers", "thanks", "thank you",
)
LEAD_IN_PATTERNS = (
    "let's", "lets ", "right,", "okay", "ok,", "so ", "next", "move on", "moving on",
    "turn to", "ask you", "want to ask", "get into", "think about",
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[tuple[int, str]]:
    """(char_offset, sentence) preserving exact source offsets."""
    out, pos = [], 0
    for part in _SENT_SPLIT.split(text):
        if not part:
            continue
        idx = text.index(part, pos)
        out.append((idx, part))
        pos = idx + len(part)
    return out


def opening_suffix_slice(content: str, question: str, roster: set[str]) -> dict:
    """
    Find the verbatim suffix of a section's opening moderator turn that carries the
    target question's ask and nothing substantive from the previous question.

    Anchor on the last sentence position whose suffix still poses the question, then
    extend BACKWARD only across sentences that are lead-ins to that ask. Extension
    stops at the first sentence that names a participant, reads as a recap, or
    carries another question's content — that sentence and everything before it is
    dropped.

    Returns offset 0 when there is no substantive residue. Never paraphrases: the
    retained text is `content[offset:]`, byte-for-byte.
    """
    markers = QUESTION_MARKERS[question]
    sents = _sentences(content)
    if not sents:
        return {"offset": 0, "dropped_prefix": "", "retained": content,
                "reason": "no sentence boundaries found", "stopped_at": None}

    # anchor: the LAST start position whose suffix still holds >= MIN_MARKER_HITS
    anchor = 0
    for off, _ in sents:
        suffix = content[off:].lower()
        if sum(1 for m in markers if m in suffix) >= MIN_MARKER_HITS:
            anchor = off
        else:
            break

    # extend backward over ask lead-ins only
    other_markers = {m for q, ms in QUESTION_MARKERS.items() if q != question
                     for m in ms} - set(markers)
    starts = [o for o, _ in sents]
    i = starts.index(anchor) if anchor in starts else 0
    stopped_at = None
    while i > 0:
        off, sent = sents[i - 1]
        low = sent.lower()
        names = any(re.search(r"\b" + re.escape(n) + r"\b", sent, re.I) for n in roster)
        recap = any(pat in low for pat in RECAP_PATTERNS)
        foreign = any(m in low for m in other_markers)
        if names or recap or foreign:
            stopped_at = {"sentence": sent[:200],
                          "because": ("names a participant" if names else
                                      "reads as a recap" if recap else
                                      "carries another question's content")}
            break
        if not any(pat in low for pat in LEAD_IN_PATTERNS) and len(sent.split()) > 25:
            stopped_at = {"sentence": sent[:200],
                          "because": "not a lead-in to the ask"}
            break
        anchor = off
        i -= 1

    return {"offset": anchor,
            "dropped_prefix": content[:anchor],
            "retained": content[anchor:],
            "stopped_at": stopped_at,
            "reason": ("no substantive residue" if anchor == 0
                       else "dropped prior-question residue before the ask")}


def contains_next_question_ask(text: str, question: str) -> list[str]:
    """Distinctive asks of the FOLLOWING question found in this text."""
    low = " ".join(text.lower().split())
    return [a for a in NEXT_QUESTION_ASK.get(question, ()) if a in low]


def _rel(p):
    """Display path, tolerant of a redirected output workspace."""
    try:
        return p.relative_to(_REPO_ROOT)
    except ValueError:
        return p


class SamplingError(RuntimeError):
    pass


def _sha_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class _Section:
    """A section of a synthetic comparable window, with the same fields we use."""
    def __init__(self, section_index, section_label, blind_lines, turn_ids,
                 entry_indices, participant_turns, moderator_turns, total_words,
                 distinct_participants):
        self.section_index = section_index
        self.section_label = section_label
        self.blind_lines = blind_lines
        self.turn_ids = turn_ids
        self.entry_indices = entry_indices
        self.participant_turns = participant_turns
        self.moderator_turns = moderator_turns
        self.total_words = total_words
        self.distinct_participants = distinct_participants


class _WindowResult:
    def __init__(self, sections, boundary_method):
        self.sections = sections
        self.boundary_method = boundary_method


def _segment_synthetic_window(window_path: Path):
    """
    Section a synthetic COMPARABLE WINDOW.

    Boundaries come from the run's moderator_log via the frozen segmenter, which is
    read-only here and unmodified. The moderator log indexes the FULL transcript, so
    the boundaries are translated into window positions using the window's own
    recorded `first_source_entry_index`.

    The TEXT delivered is taken from `comparable_transcript.json` only — the full
    transcript is consulted for boundary positions and never for content. That
    matters: the window's first entry is a verbatim trim of its source entry, and it
    is that trimmed form the evaluator saw.
    """
    payload = json.loads(window_path.read_text(encoding="utf-8"))
    prov = payload["_provenance"]
    window_entries = payload["transcript"]
    offset = prov["first_source_entry_index"]
    source = _REPO_ROOT / prov["source_transcript"]

    full = seg.segment_synthetic_by_guide(source, _GUIDE)
    blind, _ = seg.to_blind_text(window_entries)

    # per-entry blind records: to_blind_text skips empty content and numbers 1..N
    recs, n = [], 0
    for e in window_entries:
        c = (e.get("content") or "").strip()
        if not c:
            recs.append(None)
            continue
        n += 1
        recs.append(n)

    sections = {}
    for idx, sec in full.sections.items():
        win_idx = [i - offset for i in sec.entry_indices
                   if 0 <= i - offset < len(window_entries)]
        if not win_idx:
            continue
        lines, tids, pt, mt, words, speakers = [], [], 0, 0, 0, set()
        blind_lines = {}
        cur = 0
        for e in window_entries:
            c = (e.get("content") or "").strip()
            if not c:
                continue
            cur += 1
            blind_lines[cur] = e
        for wi in win_idx:
            t = recs[wi]
            if t is None:
                continue
            e = window_entries[wi]
            spk = str(e.get("speaker_id", "")).upper()
            label = ("Moderator" if spk == "MODERATOR"
                     else f"Participant {sorted({str(x.get('speaker_id')) for x in window_entries if str(x.get('speaker_id','')).upper() != 'MODERATOR'}).index(str(e.get('speaker_id'))) + 1}")
            content = (e.get("content") or "").strip()
            lines.append(f"[T{t:03d}] {label}: {content}")
            tids.append(f"T{t:03d}")
            w = len(content.split())
            words += w
            if spk == "MODERATOR":
                mt += 1
            else:
                pt += 1
                speakers.add(str(e.get("speaker_id")))
        if not lines:
            continue
        sections[idx] = _Section(idx, sec.section_label, lines, tids, win_idx,
                                 pt, mt, words, len(speakers))
    return _WindowResult(sections,
                         "moderator_log.section_transition mapped onto the "
                         "comparable window via first_source_entry_index")


def _segment(item: dict):
    path = _REPO_ROOT / item["path"]
    if item["side"] == "human":
        return seg.segment_human_by_guide(path, _GUIDE)
    return _segment_synthetic_window(path)


def build_frame() -> tuple[list[dict], list[dict]]:
    """Every codeable (stratum, FG, question) unit, plus the ones ruled out."""
    frozen = pep.load_inputs()
    items = []
    for i in frozen["human_inputs"]:
        items.append(("human", i))
    for i in frozen["synthetic_inputs"]:
        if i.get("canonical_replication_index") == SYNTHETIC_REPLICATION_INDEX:
            items.append((i["condition"], i))

    frame, excluded = [], []
    for stratum, item in items:
        result = _segment(item)
        for qid, sec_idx in QUESTION_SECTIONS.items():
            sec = result.sections.get(sec_idx)
            if sec is None:
                excluded.append({"stratum": stratum, "fg": item["fg"], "question": qid,
                                 "reason": "section absent from this transcript"})
                continue
            if sec.participant_turns < 1:
                excluded.append({"stratum": stratum, "fg": item["fg"], "question": qid,
                                 "reason": "technically empty: no participant turns"})
                continue
            frame.append({
                "stratum": stratum, "fg": item["fg"], "question": qid,
                "section_index": sec_idx,
                "physical_run": item.get("physical_run"),
                "canonical_replication_index": item.get("canonical_replication_index"),
                "path": item["path"], "source_sha256": item["sha256"],
            })
    return frame, excluded


def select(frame: list[dict]) -> tuple[list[dict], int]:
    rng = random.Random(int(_sha_text(SELECTION_SEED)[:16], 16))
    by_stratum = {s: [f for f in frame if f["stratum"] == s] for s in STRATA}
    for s, pool in by_stratum.items():
        if len(pool) < N_PER_STRATUM:
            raise SamplingError(f"stratum {s!r} has only {len(pool)} candidate units")

    for attempt in range(1, 100_001):
        pick = []
        for s in STRATA:
            pick.extend(rng.sample(by_stratum[s], N_PER_STRATUM))
        if {p["question"] for p in pick} != set(QUESTION_SECTIONS):
            continue
        if len({p["fg"] for p in pick}) < MIN_DISTINCT_FGS:
            continue
        if len({(p["stratum"], p["fg"], p["question"]) for p in pick}) != N_UNITS:
            continue
        return sorted(pick, key=lambda p: (p["stratum"], p["question"], p["fg"])), attempt
    raise SamplingError("no sample satisfied the constraints within 100000 attempts")


def blind_unit_id(i: int) -> str:
    return f"S{i:02d}"


def _roster_names(sel) -> set:
    """Participant display names for this source, used to spot recap sentences."""
    import json as _json
    path = _REPO_ROOT / sel["path"]
    payload = _json.loads(path.read_text(encoding="utf-8"))
    entries = payload["transcript"] if isinstance(payload, dict) else payload
    return {str(e.get("speaker_name")) for e in entries
            if e.get("speaker_name") and str(e.get("speaker_id", "")).upper() != "MODERATOR"}


def build_units(selection):
    """Segment each selected unit, clean its boundaries, and audit the result."""
    units, audit = [], []
    cache = {}
    for n, sel in enumerate(selection, start=1):
        key = sel["path"]
        if key not in cache:
            cache[key] = _segment({"side": "human" if sel["stratum"] == "human"
                                   else "synthetic", "path": sel["path"]})
        result = cache[key]
        sec = result.sections[sel["section_index"]]
        uid = blind_unit_id(n)
        is_human = sel["stratum"] == "human"
        roster = set() if is_human else _roster_names(sel)

        lines_ = list(sec.blind_lines)
        turn_ids = list(sec.turn_ids)
        entry_idx = list(sec.entry_indices)
        problems, advisories = [], []

        # --- 1. opening sub-entry boundary (synthetic only) ------------------
        # Human transcripts open on a scripted "Question N." header with nothing
        # before it; there is no prefix to remove and none is invented.
        opening = {"applied": False, "offset": 0,
                   "reason": "human transcript: scripted question header, no residue"}
        if not is_human:
            head = lines_[0]
            prefix, content = head.split(": ", 1)
            sliced = opening_suffix_slice(content, sel["question"], roster)
            opening = {
                "applied": sliced["offset"] > 0,
                "source_entry_index": entry_idx[0],
                "source_character_start": sliced["offset"],
                "original_entry_sha256": _sha_text(content),
                "retained_text_sha256": _sha_text(sliced["retained"]),
                "boundary_text_is_verbatim_slice": content.endswith(sliced["retained"]),
                "original_entry": content,
                "dropped_prefix": sliced["dropped_prefix"],
                "retained_suffix": sliced["retained"],
                "dropped_words": len(sliced["dropped_prefix"].split()),
                "stopped_at": sliced["stopped_at"],
                "reason": sliced["reason"],
            }
            if not opening["boundary_text_is_verbatim_slice"]:
                problems.append("opening slice is not a verbatim suffix of the entry")
            lines_[0] = prefix + ": " + sliced["retained"]

        # --- 2. end gate: the next question's ask must not be inside ---------
        removed_tail = []
        while lines_:
            hits = contains_next_question_ask(lines_[-1], sel["question"])
            if not hits:
                break
            removed_tail.append({
                "turn_id": turn_ids[-1],
                "source_entry_index": entry_idx[-1],
                "speaker_label_as_recorded": lines_[-1].split("] ", 1)[1].split(":", 1)[0],
                "text": lines_[-1].split(": ", 1)[1] if ": " in lines_[-1] else lines_[-1],
                "next_question_markers_found": hits,
                "diagnosis": "NEXT_QUESTION_ASK_MISLABELLED_OR_NONSTANDARD",
                "note": ("This turn poses the following guide question. It belongs to "
                         "the next section regardless of the speaker label the "
                         "transcript assigns it."),
            })
            lines_.pop(); turn_ids.pop(); entry_idx.pop()
        if not lines_:
            problems.append("every turn was removed by the end gate")

        text = chr(10).join(lines_)
        # Word count is CONTENT words only — the "[T001] Moderator:" prefixes are
        # rendering, not transcript, and counting them would inflate every unit.
        content_words = sum(len(l.split(": ", 1)[1].split()) if ": " in l
                            else len(l.split()) for l in lines_)

        # --- 3. hard gates ---------------------------------------------------
        first, last = (lines_[0], lines_[-1]) if lines_ else ("", "")
        expected_q = sel["question"].replace("Q", "")
        if is_human:
            if not re.search(r"Question\s*" + expected_q + r"\b", first, re.I):
                problems.append("opening does not pose " + sel["question"])
            rest = chr(10).join(lines_[1:])
            for other in QUESTION_SECTIONS:
                if other == sel["question"]:
                    continue
                if re.search(r"Question\s*" + other.replace("Q", "") + r"\b", rest, re.I):
                    problems.append("contains the opening of " + other)
        else:
            low = first.lower()
            hits = [m for m in QUESTION_MARKERS[sel["question"]] if m in low]
            if len(hits) < MIN_MARKER_HITS:
                problems.append("opening does not pose " + sel["question"]
                                + ": only " + str(hits))
            for pat in RECAP_PATTERNS:
                if pat in first.split(": ", 1)[-1].lower()[:200]:
                    problems.append("opening still carries recap material: " + pat)
                    break
            for nm in roster:
                if re.search(r"\b" + re.escape(nm) + r"\b", first, re.I):
                    problems.append("opening still names a participant: " + nm)
                    break

        still = contains_next_question_ask(text, sel["question"])
        if still:
            problems.append("still contains the next question's ask: " + str(still))
        for marker, why in (("thanks so much for joining", "introduction leaked"),
                            ("that's our time", "closing leaked")):
            if marker.lower() in text.lower():
                problems.append(why)
        if entry_idx != list(range(entry_idx[0], entry_idx[-1] + 1)):
            problems.append("entry indices are not contiguous - turns were dropped")

        audit.append({
            "blind_unit_id": uid,
            "question": sel["question"], "section_index": sel["section_index"],
            "section_label": sec.section_label,
            "stratum": sel["stratum"],
            "first_included_turn": first[:200],
            "last_included_turn": last[:200],
            "n_turns": len(turn_ids),
            "entry_index_range": [entry_idx[0], entry_idx[-1]] if entry_idx else None,
            "contiguous": bool(entry_idx) and entry_idx == list(
                range(entry_idx[0], entry_idx[-1] + 1)),
            "opening_boundary": opening,
            "removed_from_end": removed_tail,
            "section_text_sha256": _sha_text(text),
            "word_count": content_words,
            "boundary_check": ("scripted 'Question N' header" if is_human
                               else "sub-entry suffix slice + question markers"),
            "problems": problems,
            "advisories": advisories,
        })
        units.append({
            "blind_unit_id": uid, "question": sel["question"],
            "turn_ids": turn_ids, "lines": lines_, "text": text,
            "_provenance": {**sel, "section_label": sec.section_label,
                            "total_words": content_words,
                            "participant_turns": sum(
                                1 for l in lines_ if "] Participant" in l),
                            "moderator_turns": sum(
                                1 for l in lines_ if "] Moderator" in l),
                            "distinct_participants": len({
                                l.split("] ", 1)[1].split(":", 1)[0]
                                for l in lines_ if "] Participant" in l}),
                            "section_text_sha256": _sha_text(text),
                            "boundary_method": result.boundary_method,
                            "opening_boundary": opening,
                            "removed_from_end": removed_tail}},
        )
    return units, audit



def main() -> int:
    _DIR.mkdir(parents=True, exist_ok=True)
    _SEALED_DIR.mkdir(parents=True, exist_ok=True)

    frame, excluded = build_frame()
    selection, attempt = select(frame)
    units, audit = build_units(selection)

    blocking = [a for a in audit if a["problems"]]
    manifest = {
        "created_utc": datetime.now(UTC).isoformat(),
        "classification": CLASSIFICATION,
        "relationship_to_primary": (
            "U01-U07 (guide question Q3) is the PRIMARY EMERGENT CALIBRATION SAMPLE: "
            "two coders, adjudicated human clustering. THIS sample is supplementary, "
            "single-coder, and covers Q1/Q2/Q4/Q5. The two are never pooled."),
        "selection_seed": SELECTION_SEED,
        "selection_algorithm": SELECTION_ALGORITHM,
        "accepted_on_attempt": attempt,
        "frame_size": len(frame),
        "frame_excluded": excluded,
        "constraints": {
            "n_units": N_UNITS, "per_stratum": N_PER_STRATUM,
            "questions_required": sorted(QUESTION_SECTIONS),
            "min_distinct_fgs": MIN_DISTINCT_FGS,
            "synthetic_replication_index": SYNTHETIC_REPLICATION_INDEX,
            "excluded_sections": EXCLUDED_SECTIONS,
        },
        "not_consulted_during_selection": [
            "Tier-1 metrics", "condition effects", "per-FG results",
            "thematic content", "word counts (recorded after selection only)"],
        "units": [{
            "blind_unit_id": u["blind_unit_id"],
            "question_id": u["question"],
            "stratum": u["_provenance"]["stratum"],
            "fg": u["_provenance"]["fg"],
            "physical_run": u["_provenance"]["physical_run"],
            "canonical_replication_index": u["_provenance"]["canonical_replication_index"],
            "source_path": u["_provenance"]["path"],
            "source_sha256": u["_provenance"]["source_sha256"],
            "section_index": u["_provenance"]["section_index"],
            "section_label": u["_provenance"]["section_label"],
            "boundary_method": u["_provenance"]["boundary_method"],
            "section_text_sha256": u["_provenance"]["section_text_sha256"],
            "word_count": u["_provenance"]["total_words"],
            "participant_turns": u["_provenance"]["participant_turns"],
            "moderator_turns": u["_provenance"]["moderator_turns"],
            "distinct_participants": u["_provenance"]["distinct_participants"],
        } for u in units],
    }
    (_SEALED_DIR / "transportability_sample_manifest.json").write_text(
        json.dumps({"warning": "SEALED — contains provenance. Do not give to the coder.",
                    **manifest}, indent=1, ensure_ascii=False), encoding="utf-8")
    (_SEALED_DIR / "transportability_boundary_audit.json").write_text(
        json.dumps({"warning": "SEALED", "classification": CLASSIFICATION,
                    "audited_utc": manifest["created_utc"],
                    "all_clear": not blocking, "units": audit},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (_DIR / "_units_for_packaging.json").write_text(
        json.dumps([{k: v for k, v in u.items() if k != "_provenance"} for u in units],
                   indent=1, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    print(f"  {CLASSIFICATION}")
    print("=" * 78)
    print(f"\nseed      : {SELECTION_SEED}")
    print(f"frame     : {len(frame)} candidate units ({len(excluded)} excluded)")
    print(f"accepted  : attempt {attempt}")
    print(f"\n{'unit':<6}{'Q':<5}{'stratum':<20}{'fg':<6}{'turns':>6}{'words':>8}  boundary")
    for u, a in zip(units, audit):
        p = u["_provenance"]
        print(f"{u['blind_unit_id']:<6}{u['question']:<5}{p['stratum']:<20}{p['fg']:<6}"
              f"{a['n_turns']:>6}{p['total_words']:>8}  "
              f"{'OK' if not a['problems'] else 'PROBLEM'}")
    print(f"\nquestions : {sorted({u['question'] for u in units})}")
    print(f"distinct FGs: {sorted({u['_provenance']['fg'] for u in units})}")
    if blocking:
        print("\nAMBIGUOUS BOUNDARIES — stopping, package not built:")
        for a in blocking:
            for p in a["problems"]:
                print(f"  {a['blind_unit_id']}: {p}")
        return 2
    print("\nboundary audit: all 6 clear")
    print(f"sealed manifest: {_rel(_SEALED_DIR / 'transportability_sample_manifest.json')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SamplingError as exc:
        print(f"REFUSED: {exc}")
        raise SystemExit(2)
