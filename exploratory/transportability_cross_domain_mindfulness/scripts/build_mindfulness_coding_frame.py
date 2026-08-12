"""
Derive HUMAN_DERIVED_RETROSPECTIVE_CODING_FRAME_V1 from the researcher's
findings summary for DS05 mindfulness.

Offline only. No API calls. The source .docx is never modified.

WHAT THIS IS, AND IS NOT
This is NOT a validated codebook and must not be called one. It is a
retrospective frame derived from a summary document the researcher wrote after
the focus group. Its codes are extracted from that document's own structure and
wording; no theme, definition or criterion is invented here.

WHAT IS AND IS NOT TREATED AS A CODE
Not every heading or sentence in the source is a code. Specifically excluded:
  - the document's metadata preamble (participants, discussion guide, links);
  - "Key Objectives" — these are study aims, not findings about what was said;
  - container headings that group codes but assert nothing themselves
    (e.g. "Audio Tracks:");
  - the closing "Overall ..." synthesis and "Conclusion" — general
    recommendations, not discussion codes.

Each numbered section becomes a parent theme; each "Label: assertion" bullet
under it becomes a code. A parent theme with no labelled bullets contributes one
code carrying its own body text.

Definitions, inclusion and exclusion criteria are built from the source
assertion. They are DERIVED, not authored: the operational definition is the
source sentence, and criteria are stated in terms of it.

Usage:
    py scripts/build_mindfulness_coding_frame.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from docx import Document

_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = Path(
    r"C:\Users\JLARA\Documents\Dissertation\Dataset"
    r"\Mindfulness Building Resilience Across Socioeconomic Contexts"
    r"\summarizes the findings.docx"
)
_OUT_DIR = _ROOT / "analysis/transportability_mindfulness/coding_frame"
_OUT = _OUT_DIR / "human_derived_coding_frame_v1.json"

FRAME_STATUS = "HUMAN_DERIVED_RETROSPECTIVE_CODING_FRAME_V1"

# Paragraph indices (into the non-empty paragraph sequence) that are NOT codes.
# Listed explicitly so the exclusion is auditable rather than heuristic.
_EXCLUDED_INDICES = {
    0, 1, 2, 3, 4,          # metadata preamble
    5,                      # "Key Findings" banner
    6, 7, 8, 9, 10,         # "Key Objectives" — study aims, not findings
    11,                     # "Key Discussions and Insights:" banner
    32,                     # "Audio Tracks:" — container heading, asserts nothing
    49, 50, 51, 52, 53,     # "Overall ..." synthesis and its general considerations
    54, 55,                 # "Conclusion:" heading and body
}
_EXCLUSION_REASONS = {
    **{i: "document_metadata_preamble" for i in (0, 1, 2, 3, 4)},
    5: "section_banner",
    **{i: "study_objective_not_a_finding" for i in (6, 7, 8, 9, 10)},
    11: "section_banner",
    32: "container_heading_asserts_nothing",
    **{i: "closing_synthesis_general_recommendation" for i in (49, 50, 51, 52, 53)},
    54: "section_banner",
    55: "closing_synthesis_general_recommendation",
}

_THEME_RE = re.compile(r"^(\d+)\.\s+(.*?):?\s*$")
_CODE_RE = re.compile(r"^([A-Z][A-Za-z /&'-]{2,40}):\s+(.*)$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def extract() -> dict:
    paragraphs = [p.text.strip() for p in Document(_SOURCE).paragraphs if p.text.strip()]

    themes: list[dict] = []
    codes: list[dict] = []
    excluded: list[dict] = []
    current_theme: dict | None = None

    for i, text in enumerate(paragraphs):
        if i in _EXCLUDED_INDICES:
            excluded.append(
                {"paragraph_index": i, "text": text, "reason": _EXCLUSION_REASONS[i]}
            )
            continue

        theme_match = _THEME_RE.match(text)
        if theme_match:
            number, label = theme_match.group(1), theme_match.group(2).strip()
            current_theme = {
                "parent_theme_id": f"T{int(number):02d}",
                "parent_theme_label": label,
                "source_paragraph_index": i,
                "source_text_verbatim": text,
                "code_ids": [],
            }
            themes.append(current_theme)
            continue

        if current_theme is None:
            excluded.append(
                {"paragraph_index": i, "text": text, "reason": "outside_any_numbered_theme"}
            )
            continue

        code_match = _CODE_RE.match(text)
        if code_match:
            label, assertion = code_match.group(1).strip(), code_match.group(2).strip()
        else:
            # A theme whose content sits in an unlabelled body paragraph: the
            # theme itself is the code, carrying its own text.
            label, assertion = current_theme["parent_theme_label"], text

        code_id = f"{current_theme['parent_theme_id']}_{_slug(label)}"
        codes.append(
            {
                "code_id": code_id,
                "parent_theme_id": current_theme["parent_theme_id"],
                "parent_theme_label": current_theme["parent_theme_label"],
                "code_label": label,
                "operational_definition": assertion,
                "inclusion_criteria": (
                    f"A participant turn counts for this code when it asserts, describes or "
                    f"argues about: {assertion} The turn must address the substance, not merely "
                    f"use the words of the label."
                ),
                "exclusion_criteria": (
                    "Does NOT count when: the content appears only in a moderator turn; the "
                    "label's words appear without the substantive claim; the turn concerns a "
                    "sibling code under the same parent theme and not this one; or the mention "
                    "is a passing reference with no stance, description or reasoning attached."
                ),
                "boundary_with_related_codes": [],  # filled below
                "human_supporting_quotes": [],      # filled by the verification step
                "source_turn_ids": [],              # filled by the verification step
                "verification_status": "PENDING_VERIFICATION",
                "notes": "",
                "source_paragraph_index": i,
                "source_text_verbatim": text,
            }
        )
        current_theme["code_ids"].append(code_id)

    # Sibling boundaries: every code names its siblings, since the most likely
    # confusion is within a parent theme.
    by_parent: dict[str, list[str]] = {}
    for code in codes:
        by_parent.setdefault(code["parent_theme_id"], []).append(code["code_id"])
    for code in codes:
        siblings = [c for c in by_parent[code["parent_theme_id"]] if c != code["code_id"]]
        code["boundary_with_related_codes"] = siblings

    # Duplicate and overlap detection — reported, never silently merged.
    label_counts: dict[str, list[str]] = {}
    for code in codes:
        label_counts.setdefault(code["code_label"].lower(), []).append(code["code_id"])
    duplicate_labels = {k: v for k, v in label_counts.items() if len(v) > 1}
    for code in codes:
        if len(label_counts[code["code_label"].lower()]) > 1:
            others = [c for c in label_counts[code["code_label"].lower()] if c != code["code_id"]]
            code["notes"] = (
                f"DUPLICATE LABEL: the label '{code['code_label']}' also appears as {others}. "
                "The two are kept separate because their parent themes differ; a coder must use "
                "the operational definition, not the label, to tell them apart."
            )

    return {
        "themes": themes,
        "codes": codes,
        "excluded": excluded,
        "duplicate_labels": duplicate_labels,
        "paragraphs_total": len(paragraphs),
    }


def main() -> int:
    if not _SOURCE.exists():
        print(f"FAIL: source not found: {_SOURCE}")
        return 2

    extracted = extract()
    frame = {
        "frame_id": FRAME_STATUS,
        "status": FRAME_STATUS,
        "not_a_validated_codebook": (
            "This frame is derived retrospectively from a researcher-authored summary. It has "
            "not undergone two-coder validation and must not be described as a validated "
            "codebook, nor used to claim codebook validation."
        ),
        "source_document": {
            "path": str(_SOURCE),
            "sha256": _sha256(_SOURCE),
            "non_empty_paragraphs": extracted["paragraphs_total"],
            "never_modified": True,
        },
        "derivation_rules": {
            "themes": "each '<n>. <Label>:' paragraph becomes a parent theme",
            "codes": (
                "each '<Label>: <assertion>' bullet under a theme becomes a code; a theme with "
                "no labelled bullets contributes one code carrying its own body text"
            ),
            "not_codes": (
                "document metadata, section banners, 'Key Objectives' (study aims), container "
                "headings that assert nothing, and the closing synthesis/conclusion"
            ),
        },
        "counts": {
            "parent_themes": len(extracted["themes"]),
            "codes": len(extracted["codes"]),
            "excluded_paragraphs": len(extracted["excluded"]),
            "duplicate_labels": len(extracted["duplicate_labels"]),
        },
        "duplicate_labels": extracted["duplicate_labels"],
        "excluded_paragraphs": extracted["excluded"],
        "themes": extracted["themes"],
        "codes": extracted["codes"],
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(frame, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {_OUT.relative_to(_ROOT)}\n")
    print(f"  status              : {FRAME_STATUS}")
    print(f"  source sha256       : {frame['source_document']['sha256']}")
    print(f"  parent themes       : {frame['counts']['parent_themes']}")
    print(f"  codes               : {frame['counts']['codes']}")
    print(f"  excluded paragraphs : {frame['counts']['excluded_paragraphs']}")
    print(f"  duplicate labels    : {frame['counts']['duplicate_labels']} {list(extracted['duplicate_labels'])}")
    print()
    for theme in extracted["themes"]:
        print(f"  {theme['parent_theme_id']}  {theme['parent_theme_label']}")
        for code_id in theme["code_ids"]:
            code = next(c for c in extracted["codes"] if c["code_id"] == code_id)
            print(f"       - {code['code_label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
