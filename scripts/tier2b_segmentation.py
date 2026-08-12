"""
Tier 2b — segment a focus-group transcript into guide-question sections.

ADDITIVE. This module does not modify Tier 2 (`extract_themes_tier2`,
`verify_tier2_themes`, `match_tier2_themes`) in any way. It only produces the
shorter per-section `blind_text` those functions are then called with.

WHY A SEPARATE MODULE (and not extra functions in thematic_coding.py):
`thematic_coding.py` is the quarantined LLM-coding layer — it imports
`google.genai` at module scope and is the only place the codebook is read.
Segmentation is pure, offline, deterministic transcript arithmetic with no API
surface, so it lives on its own and can be tested without an API key.

SEGMENTATION SIGNALS (both verified by direct inspection, not assumed):

  Synthetic — `output/session_logs/<run>/moderator_log.json`.
    `core/session_state.py::apply_moderator_response` advances
    `session_meta.current_section_index` exactly when the moderator emits a
    decision with `action == "section_transition"`, and that same utterance is
    appended to the transcript. So the transcript entry carrying the k-th
    advancing `section_transition` utterance IS the first entry of section k+1.
    Section 0 starts at entry 0. Transcript entries themselves carry no section
    field, and `state_turn_N.json` records only a per-turn section index — which
    is off by one at every boundary, because a participant entry and the
    moderator's transition entry can share a turn number. `moderator_log` is
    therefore the precise signal; the state files are used as a cross-check.

  Human — `data/datasets_transcripts/standardized/macho_meals/fg*/transcript.json`.
    Every moderator turn that opens a guide question begins with the literal
    header `Question N.` (N = 1..5), which the researcher's transcription
    convention preserves. `Question N` maps 1:1 onto guide `section_index` N
    (verified by comparing the header text against each section's
    `scripted_question`). There is no `section_markers.json` for this corpus —
    that artefact belongs to the QESB/PHIND human-baseline pipeline, a different
    dataset — so no marker file is read and none is fabricated.

GLOBAL TURN IDS ARE PRESERVED. Sections are cut out of the *full* blind render
produced by `to_blind_text()`, so a quote verified inside a section is still
verifiable, with the same `[T0NN]` label, against the whole-transcript blind
text. Turns are never renumbered per section.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from thematic_coding import to_blind_text  # noqa: E402  (path set above)


# ---------------------------------------------------------------------------
# Minimum-data floor
# ---------------------------------------------------------------------------
# A section below either floor is NOT sent to extraction. It is reported as
# skipped_insufficient_data with its real counts — never silently dropped.
MIN_PARTICIPANT_TURNS = 3
MIN_WORDS = 150


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SectionSegment:
    """One guide section's slice of a single transcript."""

    section_index: int
    section_label: str
    blind_lines: list[str] = field(default_factory=list)
    turn_ids: list[str] = field(default_factory=list)
    entry_indices: list[int] = field(default_factory=list)

    # Counts computed over this section only
    participant_turns: int = 0
    moderator_turns: int = 0
    participant_words: int = 0
    total_words: int = 0
    distinct_participants: int = 0

    @property
    def blind_text(self) -> str:
        return "\n".join(self.blind_lines)

    @property
    def meets_floor(self) -> bool:
        return (
            self.participant_turns >= MIN_PARTICIPANT_TURNS
            and self.total_words >= MIN_WORDS
        )

    def counts(self) -> dict:
        return {
            "section_index": self.section_index,
            "section_label": self.section_label,
            "participant_turns": self.participant_turns,
            "moderator_turns": self.moderator_turns,
            "participant_words": self.participant_words,
            "total_words": self.total_words,
            "distinct_participants": self.distinct_participants,
            "first_turn_id": self.turn_ids[0] if self.turn_ids else None,
            "last_turn_id": self.turn_ids[-1] if self.turn_ids else None,
            "meets_floor": self.meets_floor,
        }


@dataclass
class SegmentationResult:
    """All sections found in one transcript, plus the full blind render."""

    side: str                      # "human" | "synthetic"
    source_path: str
    blind_text_full: str
    speaker_map: dict[str, str]
    sections: dict[int, SectionSegment] = field(default_factory=dict)
    unassigned_entry_indices: list[int] = field(default_factory=list)
    boundary_method: str = ""
    warnings: list[str] = field(default_factory=list)

    def section_indices(self) -> list[int]:
        return sorted(self.sections)


# ---------------------------------------------------------------------------
# Guide loading
# ---------------------------------------------------------------------------

def load_guide_sections(guide_source: str | Path) -> list[dict]:
    """
    Return [{section_index, section_label, scripted_question}, ...].

    Accepts either a guide YAML (`configs/guides/*.yaml`, `sections:` list) or a
    run artefact carrying an executed `discussion_guide` array
    (`session_state_initial.json`, `state_turn_N.json`, or an experiment config).
    The executed guide is the authority for a synthetic run; the YAML mirrors it.
    """
    path = Path(guide_source)
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return [
            {
                "section_index": i,
                "section_label": s["label"],
                "scripted_question": (s.get("scripted_question") or "").strip(),
            }
            for i, s in enumerate(data["sections"])
        ]

    data = json.loads(path.read_text(encoding="utf-8"))
    guide = data.get("discussion_guide")
    if guide is None:
        raise ValueError(f"No 'discussion_guide' array in {path}")
    return [
        {
            "section_index": s.get("section_index", i),
            "section_label": s["section_label"],
            "scripted_question": (s.get("scripted_question") or "").strip(),
        }
        for i, s in enumerate(guide)
    ]


# ---------------------------------------------------------------------------
# Shared machinery
# ---------------------------------------------------------------------------

def _is_moderator(entry: dict) -> bool:
    role = (entry.get("speaker_role") or "").lower()
    name = (entry.get("speaker_name") or entry.get("speaker_id") or "").lower()
    return role == "moderator" or name == "moderator"


def _normalize_utterance(s: str) -> str:
    """Whitespace/unicode-insensitive form, for matching a log utterance to a
    transcript entry. Deliberately lossy: both come from the same writer, but
    the JSON round-trip can differ in whitespace."""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


def _blind_line_index(entries: list[dict]) -> tuple[str, dict[str, str], list[int], list[str]]:
    """
    Render the full blind transcript and map blind record j → transcript entry index.

    `to_blind_text()` joins one record per non-empty entry with "\\n", but a
    record's own content may itself contain newlines — so the output CANNOT be
    split back into records with `splitlines()`. This function reproduces the
    renderer's per-entry records and then asserts that joining them reproduces
    `to_blind_text()`'s output byte for byte. If the renderer ever changes, this
    raises instead of silently mis-slicing sections.

    Returns (blind_text, speaker_map, entry_index_per_record, record_text).
    """
    blind_text, speaker_map = to_blind_text(entries)

    kept: list[int] = []
    records: list[str] = []
    for i, entry in enumerate(entries):
        content = (entry.get("content") or "").strip()
        if not content:
            continue
        speaker_name = entry.get("speaker_name") or entry.get("speaker_id", "Unknown")
        label = speaker_map.get(speaker_name, speaker_name)
        turn_id = f"T{len(records) + 1:03d}"
        records.append(f"[{turn_id}] {label}: {content}")
        kept.append(i)

    if "\n".join(records) != blind_text:
        raise RuntimeError(
            "Blind-render mismatch: Tier 2b's per-entry reconstruction no longer "
            "reproduces to_blind_text() output. to_blind_text() has changed — "
            "update _blind_line_index before using Tier 2b."
        )
    return blind_text, speaker_map, kept, records


def _build_sections(
    entries: list[dict],
    entry_section: dict[int, int],
    guide: list[dict],
    side: str,
    source_path: Path,
    boundary_method: str,
    warnings: list[str],
) -> SegmentationResult:
    """Cut the full blind render into per-section slices, preserving turn ids."""
    blind_text, speaker_map, kept, records = _blind_line_index(entries)
    labels = {s["section_index"]: s["section_label"] for s in guide}

    result = SegmentationResult(
        side=side,
        source_path=str(source_path),
        blind_text_full=blind_text,
        speaker_map=speaker_map,
        boundary_method=boundary_method,
        warnings=list(warnings),
    )
    speakers_seen: dict[int, set[str]] = {}

    for j, entry_idx in enumerate(kept):
        sec = entry_section.get(entry_idx)
        if sec is None:
            result.unassigned_entry_indices.append(entry_idx)
            continue
        if sec not in result.sections:
            result.sections[sec] = SectionSegment(
                section_index=sec,
                section_label=labels.get(sec, f"section_{sec}"),
            )
            speakers_seen[sec] = set()

        seg = result.sections[sec]
        entry = entries[entry_idx]
        # Global turn id — identical to the whole-transcript blind render.
        turn_id = f"T{j + 1:03d}"
        seg.blind_lines.append(records[j])
        seg.turn_ids.append(turn_id)
        seg.entry_indices.append(entry_idx)

        words = len((entry.get("content") or "").split())
        seg.total_words += words
        if _is_moderator(entry):
            seg.moderator_turns += 1
        else:
            seg.participant_turns += 1
            seg.participant_words += words
            speakers_seen[sec].add(
                entry.get("speaker_name") or entry.get("speaker_id") or "?"
            )

    for sec, seg in result.sections.items():
        seg.distinct_participants = len(speakers_seen.get(sec, set()))

    return result


# ---------------------------------------------------------------------------
# Synthetic segmentation
# ---------------------------------------------------------------------------

def find_synthetic_boundaries(
    entries: list[dict],
    moderator_log: list[dict],
    n_guide_sections: int,
) -> tuple[list[int], list[str]]:
    """
    Return (entry indices that open sections 1..k, warnings).

    Each advancing `section_transition` decision is matched back to the
    transcript entry carrying its utterance, by (turn, moderator, normalized
    content). A trailing `section_transition` fired on the final guide section
    does not advance the index (see `apply_moderator_response`), so at most
    `n_guide_sections - 1` boundaries are returned.
    """
    warnings: list[str] = []
    transitions = [
        e for e in moderator_log
        if e.get("action") == "section_transition" and (e.get("utterance") or "").strip()
    ]

    boundaries: list[int] = []
    used: set[int] = set()
    for t in transitions:
        if len(boundaries) >= n_guide_sections - 1:
            break  # cannot advance past the last guide section
        target = _normalize_utterance(t.get("utterance"))
        match = None
        for i, entry in enumerate(entries):
            if i in used or not _is_moderator(entry):
                continue
            if entry.get("turn") != t.get("turn"):
                continue
            if _normalize_utterance(entry.get("content")) == target:
                match = i
                break
        if match is None:
            warnings.append(
                f"section_transition at turn {t.get('turn')} has no matching "
                f"transcript entry — boundary skipped."
            )
            continue
        used.add(match)
        boundaries.append(match)

    if boundaries != sorted(boundaries):
        warnings.append("section_transition boundaries are not monotonic in entry order.")
        boundaries = sorted(boundaries)
    return boundaries, warnings


def segment_synthetic_by_guide(
    transcript_json_path: str | Path,
    guide_source: str | Path,
    moderator_log_path: str | Path | None = None,
) -> SegmentationResult:
    """
    Segment a synthetic run's transcript into guide sections.

    transcript_json_path : output/session_logs/<run>/transcript.json
    guide_source         : the executed guide (session_state_initial.json) or the
                           guide YAML — see load_guide_sections()
    moderator_log_path   : defaults to moderator_log.json beside the transcript
    """
    transcript_json_path = Path(transcript_json_path)
    run_dir = transcript_json_path.parent
    moderator_log_path = Path(moderator_log_path or run_dir / "moderator_log.json")

    entries = json.loads(transcript_json_path.read_text(encoding="utf-8"))
    moderator_log = json.loads(moderator_log_path.read_text(encoding="utf-8"))
    guide = load_guide_sections(guide_source)

    boundaries, warnings = find_synthetic_boundaries(entries, moderator_log, len(guide))
    if len(boundaries) < len(guide) - 1:
        warnings.append(
            f"Only {len(boundaries)} of {len(guide) - 1} expected section transitions "
            f"found — later guide sections were never reached in this run."
        )

    # Section 0 opens at entry 0; boundary k opens section k+1.
    entry_section: dict[int, int] = {}
    starts = [0] + boundaries
    for sec, start in enumerate(starts):
        end = starts[sec + 1] if sec + 1 < len(starts) else len(entries)
        for i in range(start, end):
            entry_section[i] = sec

    return _build_sections(
        entries, entry_section, guide, "synthetic", transcript_json_path,
        "moderator_log.section_transition", warnings,
    )


def crosscheck_synthetic_against_state_files(
    result: SegmentationResult,
    run_dir: str | Path,
) -> dict:
    """
    Independent check on the moderator_log boundaries.

    `state_turn_N.json` records `current_section_index` at the end of turn N.
    That value is authoritative for every entry of turn N *except* the ones
    preceding a transition utterance in the same turn — precisely the
    off-by-one this module exists to avoid. So a clean result is: agreement on
    every turn that contains no boundary, and disagreement confined to boundary
    turns. Anything else means the two signals genuinely conflict.
    """
    run_dir = Path(run_dir)
    entries = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))

    state_section_by_turn: dict[int, int] = {}
    for path in run_dir.glob("state_turn_*.json"):
        n = int(re.search(r"state_turn_(\d+)", path.name).group(1))
        state = json.loads(path.read_text(encoding="utf-8"))
        state_section_by_turn[n] = state["session_meta"]["current_section_index"]

    entry_section = {
        i: seg.section_index
        for seg in result.sections.values()
        for i in seg.entry_indices
    }
    boundary_entries = {
        min(seg.entry_indices) for seg in result.sections.values()
        if seg.section_index > 0 and seg.entry_indices
    }
    boundary_turns = {entries[i].get("turn") for i in boundary_entries}

    agree = disagree_on_boundary_turn = conflict = 0
    conflicts: list[dict] = []
    for i, entry in enumerate(entries):
        expected = state_section_by_turn.get(entry.get("turn"))
        got = entry_section.get(i)
        if expected is None or got is None:
            continue
        if expected == got:
            agree += 1
        elif entry.get("turn") in boundary_turns:
            disagree_on_boundary_turn += 1
        else:
            conflict += 1
            conflicts.append({"entry_index": i, "turn": entry.get("turn"),
                              "state_says": expected, "segmenter_says": got})

    return {
        "state_files_found": len(state_section_by_turn),
        "entries_agree": agree,
        "entries_differ_on_boundary_turn": disagree_on_boundary_turn,
        "entries_in_conflict": conflict,
        "conflicts": conflicts[:20],
        "clean": conflict == 0,
    }


# ---------------------------------------------------------------------------
# Human segmentation
# ---------------------------------------------------------------------------

# Moderator turns opening a guide question start with this literal header.
_QUESTION_HEADER_RE = re.compile(r"^\s*Question\s*(\d+)\s*[.:\)]", re.IGNORECASE)


def find_human_boundaries(entries: list[dict]) -> tuple[list[tuple[int, int]], list[str]]:
    """
    Return ([(entry_index, question_number), ...], warnings) for every moderator
    turn carrying a `Question N.` header, in transcript order.
    """
    warnings: list[str] = []
    found: list[tuple[int, int]] = []
    for i, entry in enumerate(entries):
        if not _is_moderator(entry):
            continue
        m = _QUESTION_HEADER_RE.match(entry.get("content") or "")
        if m:
            found.append((i, int(m.group(1))))

    numbers = [n for _, n in found]
    if len(set(numbers)) != len(numbers):
        warnings.append(f"Duplicate Question headers: {numbers}")
    if numbers != sorted(numbers):
        warnings.append(f"Question headers out of order: {numbers}")
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        warnings.append(
            f"Question numbering has gaps: {numbers} — the missing question was "
            f"not asked in this group and is reported as absent, not inferred."
        )
    return found, warnings


def segment_human_by_guide(
    standardized_transcript_path: str | Path,
    guide_source: str | Path,
    section_map: dict[int, int] | None = None,
) -> SegmentationResult:
    """
    Segment a standardized human transcript into guide sections.

    section_map maps the transcript's own question number → guide section_index.
    For the macho_meals corpus the mapping is the identity (`Question N` ↔
    guide `section_index` N, verified against each section's scripted_question),
    so it defaults to identity. Pass an explicit map for any corpus where the
    two do not line up — never guess one.

    NOTE: there is no `section_markers.json` for this corpus. That artefact is
    produced by the QESB/PHIND human-baseline standardizer for a different
    dataset and is deliberately not read here.
    """
    standardized_transcript_path = Path(standardized_transcript_path)
    entries = json.loads(standardized_transcript_path.read_text(encoding="utf-8"))
    guide = load_guide_sections(guide_source)
    valid_indices = {s["section_index"] for s in guide}

    found, warnings = find_human_boundaries(entries)
    if not found:
        raise ValueError(
            f"No 'Question N.' headers found in {standardized_transcript_path}. "
            f"Section boundaries cannot be established for this transcript and "
            f"must not be guessed — segment it manually or exclude it."
        )

    entry_section: dict[int, int] = {}
    for k, (start, qnum) in enumerate(found):
        end = found[k + 1][0] if k + 1 < len(found) else len(entries)
        sec = section_map.get(qnum) if section_map else qnum
        if sec is None or sec not in valid_indices:
            warnings.append(
                f"Question {qnum} has no counterpart in the guide — entries "
                f"{start}..{end - 1} left unassigned (not comparable)."
            )
            continue
        for i in range(start, end):
            entry_section[i] = sec

    if found[0][0] > 0:
        warnings.append(
            f"{found[0][0]} entries precede the first Question header — left "
            f"unassigned (pre-question material, no guide counterpart)."
        )

    return _build_sections(
        entries, entry_section, guide, "human", standardized_transcript_path,
        "moderator 'Question N.' header", warnings,
    )


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def comparable_sections(
    human: SegmentationResult,
    synthetic: SegmentationResult,
) -> tuple[list[int], list[dict]]:
    """
    Return (section indices comparable on both sides, per-section skip records).

    A section is comparable only if it is present on BOTH sides and clears the
    data floor on BOTH sides. Every other section gets a skip record with its
    real counts — nothing is dropped silently.
    """
    comparable: list[int] = []
    skipped: list[dict] = []
    all_indices = sorted(set(human.sections) | set(synthetic.sections))

    for idx in all_indices:
        h = human.sections.get(idx)
        s = synthetic.sections.get(idx)
        label = (h or s).section_label

        if h is None or s is None:
            skipped.append({
                "section_index": idx,
                "section_label": label,
                "status": "skipped_no_counterpart",
                "reason": f"absent from the {'human' if h is None else 'synthetic'} transcript",
                "human_counts": h.counts() if h else None,
                "synthetic_counts": s.counts() if s else None,
            })
            continue

        if not (h.meets_floor and s.meets_floor):
            failing = [
                side for side, seg in (("human", h), ("synthetic", s))
                if not seg.meets_floor
            ]
            skipped.append({
                "section_index": idx,
                "section_label": label,
                "status": "skipped_insufficient_data",
                "reason": (
                    f"below floor (MIN_PARTICIPANT_TURNS={MIN_PARTICIPANT_TURNS}, "
                    f"MIN_WORDS={MIN_WORDS}) on: {', '.join(failing)}"
                ),
                "human_counts": h.counts(),
                "synthetic_counts": s.counts(),
            })
            continue

        comparable.append(idx)

    return comparable, skipped
