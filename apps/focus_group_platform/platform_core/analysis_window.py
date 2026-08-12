"""
Comparable windows for a user's corpus, and the identity of an analytical input.

`windows.py` reads the FROZEN windows: they are the artefacts of record, they are not
re-derived, and nothing here touches them. This module is the other half - windows for
a corpus the user brought, which do not exist yet and must be made deliberately.

THE ASSUMPTION THIS MODULE REMOVES. Until now a synthetic file could be declared "a
comparable window" at import and that declaration was the whole of the evidence; a
human transcript was assumed comparable simply by being human. Neither is a reviewable
decision. From here, BOTH SIDES need a window artefact, and only a LOCKED one may feed
a comparison. A researcher who genuinely has a pre-trimmed file confirms that in one
click - but the confirmation produces an artefact with boundaries, hashes and a name
attached, which the declaration never did.

WHAT THE ARTEFACT HASH COVERS. Order, turn ids, speaker ids, roles, text, the
boundaries, and the source canonical hash. Not the concatenated content: two windows
that retain the same words in a different order, or attribute them to different
speakers, are different analytical inputs and must hash differently. A content-only
digest would call them identical, and every structural metric that depends on who
spoke would then be silently interchangeable.

NO BOUNDARY IS EVER GUESSED. A text boundary that matches once is unambiguous; zero or
several matches leaves the window UNDER_REVIEW. A positional boundary is accepted only
as an explicit researcher decision, with a name and a note. No heuristic runs here and
none is planned for this phase.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

SCHEMA_VERSION = "1.0.0"

COMPARABLE_NAMESPACE = "_comparable_window"
FULL_RUN_NAMESPACE = "_full_run_descriptive"
FROZEN_NAMESPACE = "_comparable_window"


class WindowStatus(str, Enum):
    RAW_FULL_TRANSCRIPT = "RAW_FULL_TRANSCRIPT"
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    LOCKED = "LOCKED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class DerivationMethod(str, Enum):
    MANUAL = "MANUAL"
    CONFIRMED_ENTIRE_TRANSCRIPT = "CONFIRMED_ENTIRE_TRANSCRIPT"
    FROZEN = "FROZEN"


class CalculationStatus(str, Enum):
    COMPARABLE = "COMPARABLE"
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    LEGACY_UNVERIFIED_WINDOW = "LEGACY_UNVERIFIED_WINDOW"


class WindowError(RuntimeError):
    pass


@dataclass
class Boundary:
    turn_id: str | None
    char_offset: int | None = None
    matched_text: str = ""
    confidence: str = "manual"          # exact | manual | positional
    n_matches: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComparableWindow:
    window_id: str
    source_transcript_id: str
    source_canonical_sha256: str
    side: str                            # human | synthetic
    status: str
    derivation_method: str
    included_turn_ids: list[str] = field(default_factory=list)
    n_source_turns: int = 0
    n_retained_turns: int = 0
    retained_sha256: str = ""
    window_artifact_sha256: str = ""
    start_boundary: dict | None = None
    end_boundary: dict | None = None
    positional_fallback_used: bool = False
    unambiguous: bool = True
    researcher_label: str = ""
    researcher_note: str = ""
    proposed_utc: str = ""
    reviewed_utc: str = ""
    locked_utc: str = ""
    supersedes_window_id: str | None = None
    superseded_by_window_id: str | None = None
    review_problems: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    @property
    def locked(self) -> bool:
        return self.status == WindowStatus.LOCKED.value

    @property
    def namespace(self) -> str:
        return COMPARABLE_NAMESPACE if self.locked else FULL_RUN_NAMESPACE

    def to_dict(self) -> dict:
        return asdict(self)


def window_from_dict(payload: dict) -> ComparableWindow:
    known = {f for f in ComparableWindow.__dataclass_fields__}
    return ComparableWindow(**{k: v for k, v in payload.items() if k in known})


# ------------------------------------------------------------------- hashing
def _turn_fingerprint(turn: dict, text: str) -> list:
    """
    Everything that makes a turn THIS turn, in order.

    Speaker id and role are in here on purpose: a window that keeps the same words but
    attributes them differently is a different analytical input, and `turn_balance`,
    `moderator_word_share` and adjacency all depend on the attribution.
    """
    return [turn.get("turn_id"), turn.get("original_turn_id"),
            turn.get("original_index"), turn.get("canonical_speaker_id"),
            turn.get("original_speaker_id"), turn.get("speaker_role"), text]


def artifact_digest(*, source_canonical_sha256: str, side: str,
                    derivation_method: str, retained: list[tuple[dict, str]],
                    start_boundary: dict | None, end_boundary: dict | None) -> str:
    body = {
        "schema_version": SCHEMA_VERSION,
        "source_canonical_sha256": source_canonical_sha256,
        "side": side,
        "derivation_method": derivation_method,
        "start_boundary": start_boundary,
        "end_boundary": end_boundary,
        "turns": [_turn_fingerprint(turn, text) for turn, text in retained],
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def retained_digest(retained: list[tuple[dict, str]]) -> str:
    """The retained TEXT only. Kept for continuity; never used as identity."""
    return hashlib.sha256(
        "\n".join(text for _turn, text in retained).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ selection
def locate_text_boundary(turns: list[dict], text: str) -> tuple[list[dict], str]:
    """
    Find a boundary expressed as text.

    One match is unambiguous. Zero means the phrase is not in the transcript. Several
    means the phrase does not identify a point - and picking the first would be a
    guess wearing the clothes of a decision.
    """
    needle = (text or "").strip()
    if not needle:
        return [], "no boundary text was given"
    matches = [{"turn_id": t["turn_id"], "original_index": t["original_index"],
                "char_offset": t["text"].find(needle)}
               for t in turns if needle in (t.get("text") or "")]
    if len(matches) == 1:
        return matches, "exactly one match"
    if not matches:
        return [], f"no turn contains {needle!r}"
    return matches, (f"{len(matches)} turns contain {needle!r}; the phrase does not "
                     f"identify a single boundary")


def select_turns(turns: list[dict], *, start_turn_id: str | None,
                 end_turn_id: str | None, start_char_offset: int | None = None,
                 end_char_offset: int | None = None
                 ) -> tuple[list[tuple[dict, str]], list[str]]:
    """
    Apply the boundaries to the canonical turns.

    Returns (retained, problems). The turns come back IN SOURCE ORDER, with their
    provenance untouched - only the first and last may be trimmed by an offset, and
    only within their own text. An invalid selection returns problems and no window
    is ever built from it.
    """
    problems: list[str] = []
    if not turns:
        return [], ["the source transcript has no turns"]

    index_by_id = {t["turn_id"]: i for i, t in enumerate(turns)}
    start_id = start_turn_id or turns[0]["turn_id"]
    end_id = end_turn_id or turns[-1]["turn_id"]

    if start_id not in index_by_id:
        problems.append(f"start turn {start_id!r} is not in the source transcript")
    if end_id not in index_by_id:
        problems.append(f"end turn {end_id!r} is not in the source transcript")
    if problems:
        return [], problems

    first, last = index_by_id[start_id], index_by_id[end_id]
    if first > last:
        return [], [f"the start turn ({start_id}) comes after the end turn "
                    f"({end_id}); a window cannot run backwards"]

    if start_char_offset is not None:
        text = turns[first]["text"] or ""
        if not 0 <= start_char_offset <= len(text):
            problems.append(
                f"start offset {start_char_offset} is outside turn {start_id}, whose "
                f"text is {len(text)} characters")
    if end_char_offset is not None:
        text = turns[last]["text"] or ""
        if not 0 <= end_char_offset <= len(text):
            problems.append(
                f"end offset {end_char_offset} is outside turn {end_id}, whose text "
                f"is {len(text)} characters")
    if first == last and start_char_offset is not None \
            and end_char_offset is not None and start_char_offset > end_char_offset:
        problems.append("within a single turn the start offset comes after the end "
                        "offset")
    if problems:
        return [], problems

    retained: list[tuple[dict, str]] = []
    for position in range(first, last + 1):
        turn = turns[position]
        text = turn.get("text") or ""
        if position == first and start_char_offset is not None:
            text = text[start_char_offset:]
        if position == last and end_char_offset is not None:
            cut = end_char_offset
            if position == first and start_char_offset is not None:
                cut = max(end_char_offset - start_char_offset, 0)
            text = text[:cut]
        retained.append((turn, text))
    return retained, []


def build_window(*, window_id: str, source_transcript_id: str,
                 source_canonical_sha256: str, side: str, turns: list[dict],
                 start_turn_id: str | None = None, end_turn_id: str | None = None,
                 start_char_offset: int | None = None,
                 end_char_offset: int | None = None,
                 derivation_method: str = DerivationMethod.MANUAL.value,
                 positional_fallback_used: bool = False,
                 unambiguous: bool = True,
                 researcher_label: str = "", researcher_note: str = "",
                 proposed_utc: str = "",
                 supersedes_window_id: str | None = None,
                 review_problems: list[str] | None = None) -> ComparableWindow:
    """
    Build a PROPOSED (or UNDER_REVIEW) window. Never a LOCKED one - locking is a
    separate act with its own preconditions.
    """
    retained, problems = select_turns(
        turns, start_turn_id=start_turn_id, end_turn_id=end_turn_id,
        start_char_offset=start_char_offset, end_char_offset=end_char_offset)
    if problems:
        raise WindowError("; ".join(problems))

    start = Boundary(
        turn_id=retained[0][0]["turn_id"], char_offset=start_char_offset,
        matched_text=(retained[0][1][:60] if start_char_offset is not None else ""),
        confidence="positional" if positional_fallback_used else "manual").to_dict()
    end = Boundary(
        turn_id=retained[-1][0]["turn_id"], char_offset=end_char_offset,
        matched_text=(retained[-1][1][-60:] if end_char_offset is not None else ""),
        confidence="positional" if positional_fallback_used else "manual").to_dict()

    review = list(review_problems or [])
    status = (WindowStatus.UNDER_REVIEW.value
              if (not unambiguous or review) else WindowStatus.PROPOSED.value)

    return ComparableWindow(
        window_id=window_id, source_transcript_id=source_transcript_id,
        source_canonical_sha256=source_canonical_sha256, side=side, status=status,
        derivation_method=derivation_method,
        included_turn_ids=[t["turn_id"] for t, _ in retained],
        n_source_turns=len(turns), n_retained_turns=len(retained),
        retained_sha256=retained_digest(retained),
        window_artifact_sha256=artifact_digest(
            source_canonical_sha256=source_canonical_sha256, side=side,
            derivation_method=derivation_method, retained=retained,
            start_boundary=start, end_boundary=end),
        start_boundary=start, end_boundary=end,
        positional_fallback_used=positional_fallback_used,
        unambiguous=unambiguous, researcher_label=researcher_label,
        researcher_note=researcher_note, proposed_utc=proposed_utc,
        supersedes_window_id=supersedes_window_id, review_problems=review)


def confirm_entire_transcript(*, window_id: str, source_transcript_id: str,
                              source_canonical_sha256: str, side: str,
                              turns: list[dict], researcher_label: str,
                              researcher_note: str,
                              proposed_utc: str = "",
                              supersedes_window_id: str | None = None
                              ) -> ComparableWindow:
    """
    "This file already contains only the comparable segment."

    A legitimate and common case - but it becomes an ARTEFACT with the first and last
    turn as boundaries, a hash, a name and a note, rather than a claim made once at
    upload and never inspected again.
    """
    if not turns:
        raise WindowError("cannot confirm an empty transcript as a window")
    if not researcher_label.strip():
        raise WindowError("confirming a whole transcript as the window is a "
                          "researcher decision; it needs a researcher label")
    return build_window(
        window_id=window_id, source_transcript_id=source_transcript_id,
        source_canonical_sha256=source_canonical_sha256, side=side, turns=turns,
        start_turn_id=turns[0]["turn_id"], end_turn_id=turns[-1]["turn_id"],
        derivation_method=DerivationMethod.CONFIRMED_ENTIRE_TRANSCRIPT.value,
        unambiguous=True, researcher_label=researcher_label,
        researcher_note=researcher_note, proposed_utc=proposed_utc,
        supersedes_window_id=supersedes_window_id)


def preview(turns: list[dict], window: ComparableWindow, *, context: int = 3,
            page: int = 1, page_size: int = 25) -> dict:
    """
    The retained content, PAGED, with the boundary context always visible.

    A 400-turn window is not reviewable as one table, and truncating it silently is
    worse than paging it: the reviewer sees the first forty turns and believes they
    have seen the window. The context either side is repeated on every page, because
    it is what the boundaries are being judged against.
    """
    page_size = max(int(page_size), 1)
    index_by_id = {t["turn_id"]: i for i, t in enumerate(turns)}
    included = set(window.included_turn_ids)
    first = min((index_by_id[t] for t in included if t in index_by_id), default=0)
    last = max((index_by_id[t] for t in included if t in index_by_id), default=0)

    def row(turn, position, section):
        return {"position": position, "turn_id": turn["turn_id"],
                "original_turn_id": turn.get("original_turn_id"),
                "speaker": turn.get("canonical_speaker_id")
                or turn.get("original_speaker_id"),
                "role": turn.get("speaker_role"),
                "section": section,
                "text": (turn.get("text") or "")[:220]}

    before = [row(turns[i], i, "before")
              for i in range(max(first - context, 0), first)]
    after = [row(turns[i], i, "after")
             for i in range(last + 1, min(last + 1 + context, len(turns)))]
    retained_rows = [row(turns[i], i, "retained")
                     for i in range(first, last + 1)
                     if turns[i]["turn_id"] in included]

    total_turns = len(retained_rows)
    total_pages = max((total_turns + page_size - 1) // page_size, 1)
    page = min(max(int(page), 1), total_pages)
    start = (page - 1) * page_size
    window_rows = retained_rows[start:start + page_size]

    return {"before": before, "retained": window_rows, "after": after,
            "page": page, "page_size": page_size, "total_turns": total_turns,
            "total_pages": total_pages,
            "first_shown": start + 1 if window_rows else 0,
            "last_shown": start + len(window_rows),
            "n_retained": total_turns, "n_shown": len(window_rows)}


# --------------------------------------------------------------- analysis input
@dataclass
class AnalysisInput:
    """
    WHAT WAS ANALYSED - which is not the same thing as which file was uploaded.

    One transcript can yield several analytical inputs: a full-run descriptive view
    and one or more windows over its life. Level 2 results are keyed by THIS id, so a
    second window never overwrites the first one's numbers and a comparison can state
    exactly which segment it used.
    """

    analysis_input_id: str
    source_transcript_id: str
    window_id: str | None
    namespace: str
    source_canonical_sha256: str
    window_artifact_sha256: str | None
    side: str
    comparison_eligible: bool
    eligible_metrics: list[str] = field(default_factory=list)
    calculation_status: str = CalculationStatus.DESCRIPTIVE_ONLY.value
    created_utc: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def full_run_input_id(transcript_id: str) -> str:
    return f"{transcript_id}__fullrun"


def analysis_input_for_window(window: ComparableWindow, *, eligible_metrics,
                              created_utc: str = "") -> AnalysisInput:
    eligible = window.locked
    return AnalysisInput(
        analysis_input_id=window.window_id,
        source_transcript_id=window.source_transcript_id,
        window_id=window.window_id,
        namespace=COMPARABLE_NAMESPACE if eligible else FULL_RUN_NAMESPACE,
        source_canonical_sha256=window.source_canonical_sha256,
        window_artifact_sha256=window.window_artifact_sha256,
        side=window.side, comparison_eligible=eligible,
        eligible_metrics=list(eligible_metrics),
        calculation_status=(CalculationStatus.COMPARABLE.value if eligible
                            else CalculationStatus.DESCRIPTIVE_ONLY.value),
        created_utc=created_utc,
        reason=("a locked comparable window" if eligible else
                f"the window is {window.status}; only a LOCKED window may feed a "
                f"comparison"))


def analysis_input_for_full_run(*, transcript_id: str, side: str,
                                source_canonical_sha256: str, eligible_metrics,
                                created_utc: str = "") -> AnalysisInput:
    return AnalysisInput(
        analysis_input_id=full_run_input_id(transcript_id),
        source_transcript_id=transcript_id, window_id=None,
        namespace=FULL_RUN_NAMESPACE,
        source_canonical_sha256=source_canonical_sha256,
        window_artifact_sha256=None, side=side, comparison_eligible=False,
        eligible_metrics=list(eligible_metrics),
        calculation_status=CalculationStatus.DESCRIPTIVE_ONLY.value,
        created_utc=created_utc,
        reason=("computed over the whole session; descriptive only, and never "
                "averaged with windowed results"))
