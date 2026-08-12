"""
Mator "Conversational completeness" — % of prompted guide topics reached.

Separated from the BERTScore layer on purpose: this is pure structural
arithmetic over the section map, it needs no model, and it runs in seconds. It
has no business being coupled to a two-hour scoring pass.

THE METRIC
----------
A topic counts as reached when its guide section carries at least one
participant turn inside the comparable window. Section boundaries come from
`scripts/tier2b_segmentation.py`: the logged moderator `section_transition` on
the synthetic side, the `Question N.` header convention on the human side.
Sections 0 (introduction) and 6 (closing) are excluded -- they are outside the
window and have no human counterpart.

WHY THERE IS AN OPENER TABLE AND NOT AN AUTOMATIC CROSS-CHECK
-------------------------------------------------------------
The metric depends on the section LABEL naming the guide question its index
implies, and in 2 of the 30 synthetic runs it does not (`load_units` detects
and flags this: the moderator asked question 1 while still inside section 0, so
every later label is displaced, and two consecutive labels carry the same
question).

An automatic token-overlap cross-check was built and then removed rather than
shipped. Guide question 2 ("How do you decide what to eat?") contributes exactly
one content token, `decide`, and guide question 4 ("Imagine you decided to go
plant-based...") contains `decided`. Any lemmatisation that lets "deciding"
match "decide" also makes those two questions inseparable; without one, a
moderator who said "deciding" reads as never having asked question 2. Both
settings flagged all 35 units. A check that fires on everything discriminates
nothing, and shipping it as a validation would be worse than shipping no
validation at all.

What is emitted instead is `mator_completeness_openers.csv`: every
section-opening moderator turn in every unit, with its label, the guide question
that label is supposed to carry, and the opening words of what was actually
asked. That is ~200 short rows -- directly checkable by eye, which is what §5 of
the instruction asks for -- and it makes the displacement in the two flagged
runs immediately visible instead of asserted.

Usage:
    py scripts/mator_completeness.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mator_bertscore_metrics import (  # noqa: E402
    SUBSTANTIVE_SECTIONS, Unit, _is_moderator, load_units,
)

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "mator_comparable"


def completeness(unit: Unit) -> dict:
    covered = sorted({
        unit.section_of[i] for i in unit.participant_indices()
        if unit.section_of.get(i) in SUBSTANTIVE_SECTIONS
    })
    return {
        "sections_covered": covered,
        "sections_missing": [k for k in SUBSTANTIVE_SECTIONS if k not in covered],
        "value": round(len(covered) / len(SUBSTANTIVE_SECTIONS), 4),
    }


def openers(unit: Unit) -> list[dict]:
    """The moderator turn that opened each labelled section, in order.

    One row per (unit, label). `guide_question_for_this_label` is what the guide
    says that index should be asking; `moderator_actually_asked` is what was
    said. Where the two diverge the run's labels are displaced.
    """
    rows = []
    seen: set[int] = set()
    for i, e in enumerate(unit.entries):
        sec = unit.section_of.get(i)
        if sec is None or sec in seen or not _is_moderator(e):
            continue
        seen.add(sec)
        rows.append({
            "unit": unit.unit_id,
            "side": unit.side,
            "condition": unit.condition,
            "section_label_index": sec,
            "window_entry_index": i,
            "guide_question_for_this_label":
                _clip(unit.guide_questions.get(sec, "(none - not a question section)"), 120),
            "moderator_actually_asked": _clip(e.get("content", ""), 300),
            "labels_displaced_in_this_run": unit.section_labels_misaligned,
        })
    return rows


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + " [...]"


def main() -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    units, provenance = load_units()

    rows, opener_rows = [], []
    for u in units:
        c = completeness(u)
        rows.append({
            "unit": u.unit_id,
            "side": u.side,
            "fg": u.fg,
            "condition": u.condition,
            "completeness": c["value"],
            "sections_covered": "|".join(str(x) for x in c["sections_covered"]),
            "sections_missing": "|".join(str(x) for x in c["sections_missing"]),
            "section_labels_misaligned": u.section_labels_misaligned,
            "n_participant_turns": len(u.participant_indices()),
            "notes": "; ".join(u.notes),
        })
        opener_rows += openers(u)

    _write_csv(_OUT / "mator_completeness_by_unit.csv", rows)
    _write_csv(_OUT / "mator_completeness_openers.csv", opener_rows)

    spec = {
        "namespace": "_comparable_window",
        "evidence_class": "AUTOMATIC_PROXY_EXPLORATORY",
        "api_calls": 0,
        "definition": "substantive guide sections (1-5) carrying >=1 participant turn / 5",
        "segmentation": "scripts/tier2b_segmentation.py",
        "n_units": len(rows),
        "units_below_5_of_5": [r["unit"] for r in rows if r["completeness"] < 1.0],
        "runs_with_displaced_section_labels":
            provenance["section_label_misaligned_runs"],
        "excluded_from_universe": provenance["excluded_from_universe"],
        "automatic_token_cross_check": "BUILT AND REMOVED - see module docstring; it "
                                       "flagged all 35 units and discriminated nothing. "
                                       "mator_completeness_openers.csv is the checkable "
                                       "artefact in its place.",
    }
    (_OUT / "mator_completeness_spec.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    below = [r for r in rows if r["completeness"] < 1.0]
    print(f"{len(rows)} units; {len(rows) - len(below)} reached 5/5")
    for r in below:
        print(f"  {r['unit']} ({r['side']}): {r['completeness']:.1f} — missing "
              f"section(s) {r['sections_missing']}")
    for m in provenance["section_label_misaligned_runs"]:
        print(f"  LABELS DISPLACED {m['run']}: check its rows in "
              f"mator_completeness_openers.csv")
    print(f"\nwrote {_OUT / 'mator_completeness_by_unit.csv'}")
    print(f"wrote {_OUT / 'mator_completeness_openers.csv'} ({len(opener_rows)} rows)")
    print(f"wrote {_OUT / 'mator_completeness_spec.json'}")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
