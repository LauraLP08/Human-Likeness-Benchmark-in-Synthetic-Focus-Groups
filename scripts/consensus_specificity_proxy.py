"""
Specificity proxy — does a turn carry concrete detail, or stay general?

Operationalises the framework §H indicator: a turn counts as SPECIFIC if it
contains at least one concrete anchor -- a number, a temporal expression, a
named entity, or a currency/quantity. Deterministic regex + closed gazetteers,
no model and no download, so it is auditable line by line like D1.

(spaCy NER would be the upgrade and is what §H names. It needs a model
download; this proxy needs nothing and can be swapped later without changing
the reporting shape.)

THE LENGTH TRAP, again. "Proportion of turns containing >=1 anchor" rises
mechanically with turn length: a 230-word turn has ~6x the chances of a
17-word one. Synthetic turns are 4-5x longer, so the raw proportion would
flatter them exactly the way whole-turn D1 counting did. Three views, always
together:

    raw       proportion of turns with >=1 anchor           (length-confounded)
    density   anchors per 100 words                         (length-normalised)
    first40   proportion with >=1 anchor in the first 40     (identical rule)
              words -- 40 is just below the human median turn

Usage:
    py scripts/consensus_specificity_proxy.py
"""

from __future__ import annotations

import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"
_ACTS = _OUT / "response_acts.csv"

FIRST_N_WORDS = 40

_DAYS = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_MONTHS = (r"january|february|march|april|may|june|july|august|september|"
           r"october|november|december")

PATTERNS: dict[str, re.Pattern] = {
    # numerals, ordinals, currency, quantities
    "number": re.compile(
        r"(?<![A-Za-z])(?:£|\$|€)?\d+(?:[.,]\d+)?\s?"
        r"(?:%|p|k|quid|pounds?|quid|mins?|minutes?|hours?|years?|stone|kg|lbs?|ml|l)?"
        r"(?![A-Za-z])", re.I),
    # temporal expressions
    "temporal": re.compile(
        rf"\b(?:{_DAYS}|{_MONTHS}|yesterday|today|tonight|tomorrow|"
        r"last\s+(?:night|week|month|year|time|summer|winter)|"
        r"this\s+(?:morning|afternoon|evening|week|month|year)|"
        r"next\s+(?:week|month|year)|"
        r"(?:every|each)\s+(?:day|week|weekend|morning|night|friday|saturday|sunday)|"
        r"\d+\s*(?:years?|months?|weeks?|days?)\s+ago|"
        r"o'?clock|midday|midnight|lunchtime|teatime|weekend)\b", re.I),
    # proper nouns: capitalised token not at sentence start, not a stopword
    "named_entity": None,   # handled separately, needs position
}

_CAP = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b")
_NOT_ENTITY = {
    "The", "And", "But", "But", "Yeah", "Well", "That", "This", "There", "They",
    "Then", "When", "What", "With", "You", "Your", "For", "Not", "Its", "It's",
    "Like", "Just", "Because", "Actually", "Maybe", "Probably", "Honestly",
    "Sometimes", "Also", "Even", "Still", "Nah", "Yes", "No", "Okay", "Right",
    "One", "Some", "Most", "All", "Every", "Something", "Someone", "Anything",
    "Anyone", "Everything", "Everyone", "Nothing", "Nobody", "Mean", "Think",
    "Know", "Get", "Got", "Say", "Said", "Sort", "Kind", "Bit", "Thing",
    "Things", "People", "Blokes", "Lads", "Mate", "Mates", "Guys", "Men",
    "Food", "Pub", "Home", "Work", "Life", "Time", "Day", "Days", "Week",
    "Suppose", "Guess", "Wonder", "Take", "Point", "Fair", "Whereas", "Whether",
    "Which", "Where", "While", "Who", "Whose", "How", "Why", "Any", "Both",
}

# Participant first names are excluded from the entity count. Naming the person
# you are answering is direct address, not concrete detail about the world, and
# the two sides do it at very different rates: 58.6% of synthetic "entities"
# were participant names against 24.4% human. Counting them would have measured
# the known named-speaker-targeting behaviour of the agents and reported it as
# specificity. Populated at run time from the corpus.
SPEAKER_NAMES: set[str] = set()


def _entities(text: str) -> list[str]:
    return [m.group(1) for m in _CAP.finditer(text)
            if m.group(1) not in _NOT_ENTITY and m.group(1) not in SPEAKER_NAMES]


def anchors(text: str) -> dict[str, list[str]]:
    out = {"number": [m.group(0).strip() for m in PATTERNS["number"].finditer(text)],
           "temporal": [m.group(0) for m in PATTERNS["temporal"].finditer(text)],
           "named_entity": _entities(text)}
    return out


def score(text: str) -> tuple[int, dict[str, int]]:
    a = anchors(text)
    counts = {k: len(v) for k, v in a.items()}
    return sum(counts.values()), counts


def main() -> None:
    rows = list(csv.DictReader(_ACTS.open(encoding="utf-8")))
    for r in rows:
        for n in (r["resp_speaker"], r["prev_speaker"]):
            if n and n != "Moderator":
                SPEAKER_NAMES.add(n.split()[0])
    print(f"nombres de participantes excluidos del conteo de entidades: {len(SPEAKER_NAMES)}")

    recs = []
    for r in rows:
        full = r["resp_text"]
        head = " ".join(full.split()[:FIRST_N_WORDS])
        n_full, c = score(full)
        n_head, _ = score(head)
        recs.append({
            "act_id": r["act_id"], "side": r["side"], "fg": r["fg"],
            "run": r["run"], "condition": r["condition"],
            "section_index": int(r["section_index"]),
            "resp_words": int(r["resp_words"]),
            "anchors_total": n_full, "n_number": c["number"],
            "n_temporal": c["temporal"], "n_entity": c["named_entity"],
            "specific_raw": int(n_full > 0),
            "anchors_head40": n_head, "specific_first40": int(n_head > 0),
        })

    with (_OUT / "specificity_by_act.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(recs[0]))
        w.writeheader()
        w.writerows(recs)

    # per FG x condition, so each side gives 5 values
    grp: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in recs:
        grp[(r["fg"], r["condition"])].append(r)

    def per_group(fn):
        return {g: fn(v) for g, v in grp.items()}

    views = [
        ("specific_raw", "proportion of turns with >=1 anchor (raw)",
         lambda v: sum(r["specific_raw"] for r in v) / len(v)),
        ("density", "anchors per 100 words",
         lambda v: 100 * sum(r["anchors_total"] for r in v) / sum(r["resp_words"] for r in v)),
        ("first40", f"proportion with >=1 anchor in the first {FIRST_N_WORDS} words",
         lambda v: sum(r["specific_first40"] for r in v) / len(v)),
        ("d_number", "  of which: numbers per 100 words",
         lambda v: 100 * sum(r["n_number"] for r in v) / sum(r["resp_words"] for r in v)),
        ("d_temporal", "  temporal expressions per 100 words",
         lambda v: 100 * sum(r["n_temporal"] for r in v) / sum(r["resp_words"] for r in v)),
        ("d_entity", "  named entities per 100 words",
         lambda v: 100 * sum(r["n_entity"] for r in v) / sum(r["resp_words"] for r in v)),
    ]

    lines = [
        "# Specificity proxy (framework §H)",
        "",
        "*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Deterministic, zero downloads, zero API.*",
        "",
        "A turn is SPECIFIC if it contains at least one concrete anchor: a number/quantity,",
        "a temporal expression, or a named entity. The raw proportion rises mechanically with",
        "turn length, so it is reported alongside the density per 100 words and the identical",
        "window over the first 40 words.",
        "",
        "| Measure | Human mean [min-max by FG] | Enriched | Demo-only | Inside envelope |",
        "|---|---|---|---|---|",
    ]
    summary = {}
    for key, label, fn in views:
        vals = per_group(fn)
        hv = [v for (fg, c), v in vals.items() if c == "human"]
        lo, hi = min(hv), max(hv)
        cells, inside = [], []
        for c in ("enriched", "demographics-only"):
            cv = [v for (fg, cc), v in vals.items() if cc == c]
            m = statistics.mean(cv)
            cells.append(m)
            inside.append(lo <= m <= hi)
        flag = "yes" if all(inside) else ("no" if not any(inside) else "partial")
        lines.append(f"| {label} | {statistics.mean(hv):.3f} [{lo:.3f}-{hi:.3f}] "
                     f"| {cells[0]:.3f} | {cells[1]:.3f} | {flag} |")
        summary[key] = {"human_mean": statistics.mean(hv), "human_range": [lo, hi],
                        "enriched": cells[0], "demographics_only": cells[1],
                        "within_envelope": flag}

    (_OUT / "SPECIFICITY_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {_OUT / 'specificity_by_act.csv'}")
    print(f"wrote {_OUT / 'SPECIFICITY_RESULTS.md'}")


if __name__ == "__main__":
    main()
