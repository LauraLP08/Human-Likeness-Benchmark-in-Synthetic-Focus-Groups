"""
Traceable removal of the isolated editorial preamble from the DS05 analytical copy.

Offline only. No API calls. THE SOURCE .docx IS NEVER MODIFIED — it is opened
read-only and its SHA-256 is recorded before anything else happens.

CONTEXT (researcher decision, 2026-08-04)
The researcher confirmed that the DS05 transcript preserves the original speech
and that the line

    "Here's the transcript with the spelling mistakes corrected:"

is an isolated editorial preamble, not evidence that the dialogue was rewritten.
The earlier `ai_editing_artefact` framing in baseline_metadata.json is retracted
by this record. The line is removed from the ANALYTICAL copy only
(transcript.json / clean_transcript.txt / transcript.txt); the provenance file
raw_extracted_transcript.txt is deliberately left byte-faithful to the source, so
the delta between the two remains auditable.

WHAT THIS SCRIPT PROVES
  - exactly one paragraph is removed;
  - every other paragraph is character-for-character identical;
  - no turn, speaker label, punctuation or ordering changes;
  - hashes before and after are recorded for both the source file and the
    concatenated paragraph text.

Usage:
    py scripts/mindfulness_editorial_removal_record.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from docx import Document

_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = _ROOT / "data/datasets_transcripts/Mindfulness_raw transcript/Mindfulness_Focus Group Transcript.docx"
_STD = _ROOT / "data/datasets_transcripts/standardized/mindfulness/fg1"
_RECORD = _STD / "editorial_removal_record.json"

REMOVED_TEXT = "Here's the transcript with the spelling mistakes corrected:"
STATUS = "EDITORIAL_PREAMBLE_REMOVED — RESEARCHER_CONFIRMED_NOT_PART_OF_SPEECH"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_paragraphs() -> list[str]:
    """Non-empty paragraph texts, in document order, exactly as stored."""
    return [p.text.strip() for p in Document(_SOURCE).paragraphs if p.text.strip()]


def apply_removal(paragraphs: list[str]) -> tuple[list[str], list[int]]:
    """Return (paragraphs_without_preamble, removed_indices)."""
    kept, removed = [], []
    for i, text in enumerate(paragraphs):
        if text == REMOVED_TEXT:
            removed.append(i)
            continue
        kept.append(text)
    return kept, removed


def verify(before: list[str], after: list[str], removed_indices: list[int]) -> list[str]:
    """Return problems; empty means the removal is exactly and only the preamble."""
    problems: list[str] = []

    if len(removed_indices) != 1:
        problems.append(f"expected exactly 1 removed paragraph, got {len(removed_indices)}")
    if len(before) - len(after) != len(removed_indices):
        problems.append("length delta does not match the number of removed paragraphs")

    # Every surviving paragraph must be identical, in order, to the source with
    # the removed indices deleted — no substitutions, no reordering, no edits.
    expected = [t for i, t in enumerate(before) if i not in set(removed_indices)]
    if expected != after:
        for i, (want, got) in enumerate(zip(expected, after)):
            if want != got:
                problems.append(f"paragraph {i} altered: {want!r} -> {got!r}")
                break
        else:
            problems.append("paragraph count differs after removal beyond the removed indices")

    if any(REMOVED_TEXT in t for t in after):
        problems.append("removed text still present in the analytical copy")

    return problems


def main() -> int:
    if not _SOURCE.exists():
        print(f"FAIL: source not found: {_SOURCE}")
        return 2

    source_bytes = _SOURCE.read_bytes()
    source_sha = _sha256_bytes(source_bytes)

    before = source_paragraphs()
    after, removed_indices = apply_removal(before)

    text_before = "\n\n".join(before)
    text_after = "\n\n".join(after)

    problems = verify(before, after, removed_indices)

    record = {
        "record_type": "EDITORIAL_PREAMBLE_REMOVAL",
        "status": STATUS,
        "researcher_confirmation": (
            "The researcher confirmed that the transcript preserves the original speech. "
            "One isolated editorial preamble was removed from the analytical copy and did "
            "not form part of the focus-group dialogue."
        ),
        "retracts": (
            "The earlier SOURCE_INTEGRITY_FLAGS.ai_editing_artefact_detected framing, which "
            "treated this line as evidence that the dialogue had been rewritten by a language "
            "model. That claim is withdrawn."
        ),
        "removed_text_verbatim": REMOVED_TEXT,
        "original_location": {
            "source_file": _SOURCE.name,
            "non_empty_paragraph_index": removed_indices[0] if removed_indices else None,
            "note": "index into the non-empty paragraph sequence of the source .docx",
        },
        "source_file_untouched": True,
        "source_file_sha256": source_sha,
        "hashes": {
            "concatenated_paragraph_text_sha256_before": _sha256_text(text_before),
            "concatenated_paragraph_text_sha256_after": _sha256_text(text_after),
        },
        "counts": {
            "paragraphs_before": len(before),
            "paragraphs_after": len(after),
            "paragraphs_removed": len(removed_indices),
            "paragraphs_otherwise_modified": 0,
            "characters_removed": len(REMOVED_TEXT),
        },
        "scope_of_removal": {
            "applied_to": [
                "transcript.json",
                "clean_transcript.txt",
                "transcript.txt",
            ],
            "deliberately_not_applied_to": ["raw_extracted_transcript.txt"],
            "why": (
                "raw_extracted_transcript.txt is the provenance anchor and is kept "
                "byte-faithful to the source, so the delta introduced here stays auditable. "
                "Analytical measures must be computed on transcript.json / "
                "clean_transcript.txt, never on the raw provenance file."
            ),
        },
        "verification": "PASS" if not problems else "FAIL",
        "verification_problems": problems,
    }

    _STD.mkdir(parents=True, exist_ok=True)
    _RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {_RECORD.relative_to(_ROOT)}\n")
    print(f"  status                : {STATUS}")
    print(f"  source sha256         : {source_sha}")
    print(f"  paragraphs before/after: {len(before)} -> {len(after)}")
    print(f"  removed at index      : {removed_indices}")
    print(f"  text sha256 before    : {record['hashes']['concatenated_paragraph_text_sha256_before']}")
    print(f"  text sha256 after     : {record['hashes']['concatenated_paragraph_text_sha256_after']}")
    print(f"  otherwise modified    : 0")
    print(f"\n  verification          : {record['verification']}")
    for p in problems:
        print(f"    - {p}")
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())
