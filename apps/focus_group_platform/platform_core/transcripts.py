"""
Canonical transcript schema, explicit schema detection, and per-turn provenance.

Two source schemas exist in this repository and they do not overlap:

  standardized human  turn, speaker_id, canonical_speaker_id, speaker_name,
                      speaker_role, content, source_type, source_file, ...
  synthetic session   turn, speaker_id, speaker_name, content, timestamp,
                      selection_mode

Detection is EXPLICIT: a file matches one adapter, or both (ambiguous, blocked), or
neither (unsupported, rejected). Nothing is guessed from position.

Nothing is invented. Where `speaker_role` or `canonical_speaker_id` cannot be
determined unambiguously the turn is UNRESOLVED, a review item is created, and the
metrics that need that field are blocked. A role is never assigned by turn position.

The source file is opened read-only. The canonical representation is written outside
the repository, into the project's data directory.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .provenance import TRANSCRIPT_SCHEMA_VERSION

NORMALISER_VERSION = "1.0.0"

HUMAN_MARKERS = {"canonical_speaker_id", "speaker_role"}
SYNTHETIC_MARKERS = {"selection_mode", "timestamp"}
COMMON_MARKERS = {"turn", "speaker_id", "speaker_name", "content"}

# Every entry must carry these, not just the ones the detector happened to sample.
REQUIRED_PER_ENTRY = {
    "standardized_human": ("turn", "speaker_id", "speaker_name", "content",
                           "canonical_speaker_id", "speaker_role"),
    "synthetic_session_log": ("turn", "speaker_id", "speaker_name", "content",
                              "timestamp", "selection_mode"),
}
VALID_TRANSCRIPT_TYPES = ("human", "synthetic")

MODERATOR_TOKEN = "MODERATOR"


class TranscriptError(ValueError):
    pass


class SchemaDetectionError(TranscriptError):
    pass


@dataclass
class TurnProvenance:
    source_field_map: dict[str, str] = field(default_factory=dict)
    derived_fields: list[str] = field(default_factory=list)
    undefined_fields: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass
class CanonicalTurn:
    turn_id: str                        # canonical, stable within the transcript
    original_turn_id: Any               # as it appeared in the source
    original_index: int                 # 0-based coordinate in the source array
    original_speaker_id: str
    canonical_speaker_id: str | None    # None => unresolved
    speaker_role: str | None            # moderator | participant | None (unresolved)
    speaker_name: str | None
    text: str
    guide_question: str | None
    provenance: TurnProvenance
    unresolved_fields: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return not self.unresolved_fields


@dataclass
class ReviewItem:
    kind: str
    subject: str
    detail: str
    blocking: bool = True


@dataclass
class EmptyEntryAccounting:
    """
    Empty interventions are counted, never removed silently.

    The frozen synthetic producer filters them (`blind_included_entries`) because the
    evaluator never saw an empty turn. That filter is applied by the PRODUCER, not by
    normalisation - the canonical form retains every entry and records how many are
    empty, so a reader can see what the producer will drop.
    """

    found: int = 0
    retained_in_canonical: int = 0
    excluded_by_producer_rule: int = 0
    turn_ids: list[str] = field(default_factory=list)
    rule: str = ("normalisation retains every entry; the frozen synthetic producer "
                 "excludes entries whose content is empty after stripping "
                 "(aggregate_production_results.blind_included_entries)")


@dataclass
class NormalisationRecord:
    normaliser_version: str
    input_schema_detected: str
    writes_to: str
    unmapped_source_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    n_entries: int = 0
    empty_entries: EmptyEntryAccounting = field(
        default_factory=EmptyEntryAccounting)
    duplicate_original_turn_ids: list[str] = field(default_factory=list)
    missing_original_turn_ids: int = 0


@dataclass
class CanonicalTranscript:
    transcript_id: str
    source_file: str
    source_sha256: str
    transcript_type: str                # human | synthetic
    focus_group: str | None
    condition: str | None
    replicate_label: str | None
    model: str | None
    normalisation: NormalisationRecord
    turns: list[CanonicalTurn]
    review_items: list[ReviewItem] = field(default_factory=list)
    schema_version: str = TRANSCRIPT_SCHEMA_VERSION

    @property
    def fully_resolved(self) -> bool:
        return all(t.resolved for t in self.turns)

    @property
    def unresolved_turn_ids(self) -> list[str]:
        return [t.turn_id for t in self.turns if not t.resolved]

    def blocked_fields(self) -> set[str]:
        out: set[str] = set()
        for t in self.turns:
            out.update(t.unresolved_fields)
        return out

    def to_dict(self) -> dict:
        return {
            "transcript_id": self.transcript_id,
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "transcript_type": self.transcript_type,
            "focus_group": self.focus_group,
            "condition": self.condition,
            "replicate_label": self.replicate_label,
            "model": self.model,
            "schema_version": self.schema_version,
            "normalisation": asdict(self.normalisation),
            "turns": [asdict(t) for t in self.turns],
            "review_items": [asdict(r) for r in self.review_items],
        }


# ------------------------------------------------------------------ detection
def detect_schema(entries: list[dict]) -> str:
    """
    Explicit detection over EVERY entry, not a sample.

    Returns `standardized_human` or `synthetic_session_log`. Raises when the file
    matches both (ambiguous), matches neither (unsupported), or mixes the two - a mix
    that begins after entry 50 is exactly what a sampled detector misses.
    """
    if not entries:
        raise SchemaDetectionError("empty transcript: no entries to classify")

    keys: set[str] = set()
    human_entries, synthetic_entries = 0, 0
    for idx, e in enumerate(entries):
        if not isinstance(e, dict):
            raise SchemaDetectionError(
                f"entry {idx}: transcript entry is not a mapping, got "
                f"{type(e).__name__}")
        ek = set(e)
        keys |= ek
        if HUMAN_MARKERS <= ek:
            human_entries += 1
        if SYNTHETIC_MARKERS <= ek:
            synthetic_entries += 1

    if human_entries and synthetic_entries:
        raise SchemaDetectionError(
            f"mixed transcript schemas: {human_entries} entr(ies) carry the "
            f"standardized human markers {sorted(HUMAN_MARKERS)} and "
            f"{synthetic_entries} carry the synthetic markers "
            f"{sorted(SYNTHETIC_MARKERS)}. Blocked - a file must match exactly one "
            f"adapter for all of its entries.")

    missing_common = COMMON_MARKERS - keys
    if missing_common:
        raise SchemaDetectionError(
            f"unsupported transcript schema: missing required fields "
            f"{sorted(missing_common)}. Supported: standardized human and synthetic "
            f"session log.")

    human = HUMAN_MARKERS <= keys
    synthetic = SYNTHETIC_MARKERS <= keys
    if human and synthetic:
        raise SchemaDetectionError(
            "ambiguous transcript schema: the file carries markers of BOTH the "
            f"standardized human schema {sorted(HUMAN_MARKERS)} and the synthetic "
            f"session log {sorted(SYNTHETIC_MARKERS)}. Blocked - a file must match "
            "exactly one adapter.")
    if human:
        return "standardized_human"
    if synthetic:
        return "synthetic_session_log"
    raise SchemaDetectionError(
        f"unsupported transcript schema: no adapter matches these fields "
        f"{sorted(keys)}")


# ------------------------------------------------------------------- adapters
def _adapt_human(entries: list[dict]) -> tuple[list[CanonicalTurn], list[ReviewItem],
                                               list[str]]:
    turns: list[CanonicalTurn] = []
    reviews: list[ReviewItem] = []
    mapped = {"turn", "speaker_id", "canonical_speaker_id", "speaker_name",
              "speaker_role", "content"}
    unmapped = sorted({k for e in entries for k in e} - mapped)

    for idx, e in enumerate(entries):
        turn_id = f"t{idx:04d}"
        unresolved: list[str] = []
        role = e.get("speaker_role")
        canonical = e.get("canonical_speaker_id")

        if role not in {"moderator", "participant"}:
            unresolved.append("speaker_role")
            role = None
        if not canonical:
            unresolved.append("canonical_speaker_id")
            canonical = None

        prov = TurnProvenance(
            source_field_map={
                "original_turn_id": "turn",
                "original_speaker_id": "speaker_id",
                "canonical_speaker_id": "canonical_speaker_id",
                "speaker_role": "speaker_role",
                "speaker_name": "speaker_name",
                "text": "content",
            },
            derived_fields=["turn_id"],
            undefined_fields=list(unresolved),
        )
        if unresolved:
            reviews.append(ReviewItem(
                kind="TURN_UNRESOLVED", subject=turn_id,
                detail=(f"{', '.join(unresolved)} could not be determined "
                        f"unambiguously from the source; no value is assigned by "
                        f"position")))
        turns.append(CanonicalTurn(
            turn_id=turn_id,
            original_turn_id=e.get("turn"),
            original_index=idx,
            original_speaker_id=str(e.get("speaker_id", "")),
            canonical_speaker_id=canonical,
            speaker_role=role,
            speaker_name=e.get("speaker_name"),
            text=str(e.get("content", "")),
            guide_question=None,
            provenance=prov,
            unresolved_fields=unresolved,
        ))
    return turns, reviews, unmapped


def _adapt_synthetic(entries: list[dict]) -> tuple[list[CanonicalTurn],
                                                   list[ReviewItem], list[str]]:
    """
    The synthetic log carries neither `speaker_role` nor `canonical_speaker_id`.

    Both are DERIVED, by the rule the repository already uses
    (`aggregate_production_results._is_moderator`: `speaker_id == "MODERATOR"`), and
    both derivations are recorded. A blank `speaker_id` cannot be resolved and the
    turn is left unresolved rather than guessed.
    """
    turns: list[CanonicalTurn] = []
    reviews: list[ReviewItem] = []
    mapped = {"turn", "speaker_id", "speaker_name", "content", "timestamp",
              "selection_mode"}
    unmapped = sorted({k for e in entries for k in e} - mapped)

    for idx, e in enumerate(entries):
        turn_id = f"t{idx:04d}"
        sid = str(e.get("speaker_id", "")).strip()
        unresolved: list[str] = []
        if not sid:
            unresolved.extend(["speaker_role", "canonical_speaker_id"])
            role, canonical = None, None
        else:
            role = ("moderator" if sid.upper() == MODERATOR_TOKEN else "participant")
            canonical = sid

        prov = TurnProvenance(
            source_field_map={
                "original_turn_id": "turn",
                "original_speaker_id": "speaker_id",
                "speaker_name": "speaker_name",
                "text": "content",
            },
            derived_fields=(["turn_id"] if unresolved else
                            ["turn_id", "canonical_speaker_id", "speaker_role"]),
            undefined_fields=list(unresolved),
            notes=(None if unresolved else
                   "speaker_role derived by the repository rule "
                   "speaker_id == 'MODERATOR' -> moderator, else participant; "
                   "canonical_speaker_id derived from speaker_id"),
        )
        if unresolved:
            reviews.append(ReviewItem(
                kind="TURN_UNRESOLVED", subject=turn_id,
                detail=("speaker_id is empty, so neither speaker_role nor "
                        "canonical_speaker_id can be determined; no value is "
                        "assigned by position")))
        turns.append(CanonicalTurn(
            turn_id=turn_id,
            original_turn_id=e.get("turn"),
            original_index=idx,
            original_speaker_id=sid,
            canonical_speaker_id=canonical,
            speaker_role=role,
            speaker_name=e.get("speaker_name"),
            text=str(e.get("content", "")),
            guide_question=None,
            provenance=prov,
            unresolved_fields=unresolved,
        ))
    return turns, reviews, unmapped


ADAPTERS = {
    "standardized_human": _adapt_human,
    "synthetic_session_log": _adapt_synthetic,
}


def validate_entries(entries: list[dict], schema: str) -> None:
    """
    Every entry, every required field. A file is rejected on the first structural
    defect, naming the entry index and the field - a transcript with one malformed
    intervention in the middle is not silently normalised around.
    """
    required = REQUIRED_PER_ENTRY[schema]
    for idx, e in enumerate(entries):
        if not isinstance(e, dict):
            raise TranscriptError(
                f"entry {idx}: not a mapping, got {type(e).__name__}")
        missing = [f for f in required if f not in e]
        if missing:
            raise TranscriptError(
                f"entry {idx}: missing required field(s) {missing} for schema "
                f"{schema}")


def audit_turn_ids(entries: list[dict]) -> tuple[list[str], int]:
    """Duplicate and missing original turn ids. Reported, never renumbered."""
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    missing = 0
    for e in entries:
        raw = e.get("turn")
        if raw is None or raw == "":
            missing += 1
            continue
        key = str(raw)
        if key in seen:
            duplicates.append(key)
        seen[key] = seen.get(key, 0) + 1
    return sorted(set(duplicates)), missing


def audit_empty_entries(entries: list[dict]) -> EmptyEntryAccounting:
    ids = [f"t{idx:04d}" for idx, e in enumerate(entries)
           if not str(e.get("content", "")).strip()]
    return EmptyEntryAccounting(
        found=len(ids),
        retained_in_canonical=len(ids),
        excluded_by_producer_rule=len(ids),
        turn_ids=ids,
    )


# ----------------------------------------------------------------- normalise
def _entries_from(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("transcript"), list):
        return payload["transcript"]
    raise TranscriptError(
        "unsupported transcript container: expected a list of entries or an object "
        "with a `transcript` array")


def normalise_transcript(path: Path | str, *, transcript_type: str,
                         transcript_id: str | None = None,
                         focus_group: str | None = None,
                         condition: str | None = None,
                         replicate_label: str | None = None,
                         model: str | None = None) -> CanonicalTranscript:
    """Read a transcript READ-ONLY and produce its canonical form."""
    if transcript_type not in VALID_TRANSCRIPT_TYPES:
        raise TranscriptError(
            f"transcript_type must be exactly one of {list(VALID_TRANSCRIPT_TYPES)}, "
            f"got {transcript_type!r}")

    p = Path(path)
    raw = p.read_bytes()                                  # read-only, always
    payload = json.loads(raw.decode("utf-8"))
    entries = _entries_from(payload)
    schema = detect_schema(entries)
    validate_entries(entries, schema)

    if transcript_type == "human" and schema != "standardized_human":
        raise SchemaDetectionError(
            f"{p.name}: declared human but the file matches {schema}")
    if transcript_type == "synthetic" and schema != "synthetic_session_log":
        raise SchemaDetectionError(
            f"{p.name}: declared synthetic but the file matches {schema}")

    turns, reviews, unmapped = ADAPTERS[schema](entries)
    duplicates, missing_ids = audit_turn_ids(entries)
    empties = audit_empty_entries(entries)

    warnings = [f"{len(reviews)} turn(s) unresolved"] if reviews else []
    if duplicates:
        warnings.append(f"duplicate original turn id(s): {duplicates}")
        reviews.append(ReviewItem(
            kind="DUPLICATE_TURN_ID", subject=",".join(duplicates),
            detail=("the source repeats these turn identifiers; they are kept as "
                    "provenance and never renumbered")))
    if missing_ids:
        warnings.append(f"{missing_ids} entr(ies) carry no original turn id")
    if empties.found:
        warnings.append(
            f"{empties.found} empty intervention(s) retained in the canonical form; "
            f"the frozen synthetic producer will exclude them")

    record = NormalisationRecord(
        normaliser_version=NORMALISER_VERSION,
        input_schema_detected=schema,
        writes_to="project data directory (outside the repository)",
        unmapped_source_fields=unmapped,
        warnings=warnings,
        n_entries=len(entries),
        empty_entries=empties,
        duplicate_original_turn_ids=duplicates,
        missing_original_turn_ids=missing_ids,
    )
    return CanonicalTranscript(
        transcript_id=transcript_id or p.parent.name or p.stem,
        source_file=str(p),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        transcript_type=transcript_type,
        focus_group=focus_group,
        condition=condition,
        replicate_label=replicate_label,
        model=model,
        normalisation=record,
        turns=turns,
        review_items=reviews,
    )


# ------------------------------------------------- producer input adapters
def to_human_producer_turns(t: CanonicalTranscript) -> list[dict]:
    """
    Shape the canonical form for
    `scripts.structural_metrics_transportability.compute`, which reads
    `speaker_role`, `content`, `canonical_speaker_id` and `speaker_name`.
    """
    return [{
        "turn": turn.original_turn_id,
        "speaker_id": turn.original_speaker_id,
        "canonical_speaker_id": turn.canonical_speaker_id,
        "speaker_name": turn.speaker_name,
        "speaker_role": turn.speaker_role,
        "content": turn.text,
    } for turn in t.turns]


def to_synthetic_producer_entries(t: CanonicalTranscript) -> list[dict]:
    """
    Shape the canonical form for
    `scripts.aggregate_production_results.compute_structural_metrics`, which reads
    `speaker_id` and `content`.
    """
    return [{
        "turn": turn.original_turn_id,
        "speaker_id": turn.original_speaker_id,
        "speaker_name": turn.speaker_name,
        "content": turn.text,
    } for turn in t.turns]
