"""
Corrected place analysis for the specificity layer.

Two fixes to how the GLiNER output was first reported.

1. ENRICHED AND DEMOGRAPHICS-ONLY ARE NEVER POOLED. They are separate
   experimental conditions; averaging them hides exactly the contrast the study
   is built to measure. Every table here carries three columns.

2. A PARTICIPANT'S OWN PLACE OF ORIGIN IS NOT SPECIFICITY. Saying where you live
   is reciting a profile attribute; naming the pub you went to is recounting an
   experience. The agents are assigned a REGION (West Midlands, Scotland,
   Yorkshire...) and self-declare a city consistent with it, so "Birmingham" in
   an agent turn is the persona speaking, not a concrete detail about the world.
   Human participants do the same thing at a much lower rate.

   `place or location` is therefore split, by a frozen gazetteer, into:
       origin_geography  nations, regions, counties, cities  -> excluded from
                         the specificity headline, reported separately
       venue_setting     establishments, landmarks, settings -> the episodic
                         layer, which is what the indicator is about

   The same gazetteer is applied to both sides. Nothing is deleted: the origin
   layer is reported in its own table, because the fact that synthetic place
   mentions are overwhelmingly origin geography is itself the finding.

Reads the existing GLiNER entity dump. No model call, runs in seconds.

Usage:
    py scripts/consensus_specificity_place_split.py
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CD = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"

CONDITIONS = ["human", "enriched", "demographics-only"]

# Frozen gazetteer. Lowercased exact match on the entity span.
ORIGIN_GEOGRAPHY = {
    # nations / countries
    "uk", "united kingdom", "britain", "great britain", "england", "scotland",
    "wales", "northern ireland", "ireland", "india", "nigeria", "south africa",
    "pakistan", "poland", "italy", "spain", "france", "china", "japan",
    # UK regions as used in the agent personas
    "west midlands", "east midlands", "north east", "north west", "south east",
    "south west", "east of england", "greater london", "yorkshire",
    "yorkshire and the humber", "the humber", "west", "north", "south", "east",
    # counties
    "oxfordshire", "somerset", "cornwall", "devon", "kent", "essex", "surrey",
    "lancashire", "cheshire", "merseyside", "tyne and wear",
    # cities and towns
    "london", "birmingham", "manchester", "leeds", "glasgow", "edinburgh",
    "newcastle", "liverpool", "sheffield", "bristol", "belfast", "cardiff",
    "nottingham", "leicester", "coventry", "sunderland", "lisburn", "swindon",
    "oxford", "cambridge", "melton mowbray", "bridgewater", "bridgwater",
    "little hampton", "littlehampton", "aberdeen", "dundee", "york", "hull",
}

# Spans GLiNER returned that the capitalisation heuristic wrongly called
# "concrete": they are common nouns that happened to be capitalised.
GENERIC_NOT_CONCRETE = {
    "the pub", "pubs", "pub", "house", "my usual spots", "home", "the gym",
    "supermarket", "restaurant", "the shop", "town", "the office", "work",
}


def classify_place(text: str) -> str:
    t = text.strip().lower()
    if t in ORIGIN_GEOGRAPHY:
        return "origin_geography"
    if t in GENERIC_NOT_CONCRETE:
        return "generic"
    return "venue_setting"


def main() -> None:
    acts = {r["act_id"]: r for r in
            csv.DictReader((_CD / "specificity_gliner_by_act.csv").open(encoding="utf-8"))}
    ents = list(csv.DictReader((_CD / "specificity_gliner_entities.csv").open(encoding="utf-8")))

    words: dict[tuple[str, str], int] = defaultdict(int)
    for a in acts.values():
        words[(a["fg"], a["condition"])] += int(a["resp_words"])

    counts: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    inventory: dict[tuple[str, str], Counter] = defaultdict(Counter)

    for e in ents:
        a = acts[e["act_id"]]
        g = (a["fg"], a["condition"])
        if e["label"] != "place or location":
            continue
        kind = classify_place(e["text"])
        counts[kind][g] += 1
        if kind != "generic":
            inventory[(a["condition"], kind)][e["text"]] += 1
    for e in ents:
        a = acts[e["act_id"]]
        if e["label"] != "place or location":
            counts[e["label"]][(a["fg"], a["condition"])] += 1

    def row(kind: str) -> tuple[str, list[float]]:
        per = {g: 100 * counts[kind][g] / words[g] for g in words}
        cells = []
        for c in CONDITIONS:
            v = [x for (fg, cc), x in per.items() if cc == c]
            cells.append(statistics.mean(v) if v else float("nan"))
        hv = [x for (fg, cc), x in per.items() if cc == "human"]
        return f"{min(hv):.3f}-{max(hv):.3f}", cells

    lines = [
        "# Specificity — corrected place analysis",
        "",
        "*Corrects two things in the previous report: (1) enriched and demographics-only "
        "are never averaged together; (2) the participant's own place of origin is separated "
        "from episodic place.*",
        "",
        "The agents are assigned a **region** (West Midlands, Scotland, Yorkshire…) and "
        "self-attribute a city consistent with it. Saying where you live is reciting a profile "
        "attribute; naming the pub you went to is narrating an experience. Only the second is "
        "specificity in the sense of the indicator.",
        "",
        "## Mentions per 100 words",
        "",
        "| Category | Human [min-max by FG] | Enriched | Demographics-only |",
        "|---|---|---|---|",
    ]
    for kind, label in [
        ("venue_setting", "**lugar episodico (local, sitio concreto)**"),
        ("origin_geography", "geografia de origen (pais/region/ciudad)"),
        ("generic", "lugar generico (pub, casa, super)"),
    ]:
        rng, c = row(kind)
        lines.append(f"| {label} | {c[0]:.3f} [{rng}] | {c[1]:.3f} | {c[2]:.3f} |")

    lines += [
        "",
        "## Inventario completo (auditable)",
        "",
    ]
    for kind, title in [("venue_setting", "Lugares episodicos"),
                        ("origin_geography", "Geografia de origen")]:
        lines += [f"**{title}**", ""]
        for c in CONDITIONS:
            inv = inventory[(c, kind)]
            tot = sum(inv.values())
            items = ", ".join(f"{t} ({n})" for t, n in inv.most_common())
            lines.append(f"- *{c}* — {tot} menciones, {len(inv)} distintas: {items or '—'}")
        lines.append("")

    (_CD / "SPECIFICITY_PLACE_CORRECTED.md").write_text("\n".join(lines), encoding="utf-8")
    (_CD / "place_gazetteer_frozen.json").write_text(json.dumps({
        "origin_geography": sorted(ORIGIN_GEOGRAPHY),
        "generic_not_concrete": sorted(GENERIC_NOT_CONCRETE),
        "rule": "lowercased exact match on the GLiNER span; everything else is venue_setting",
    }, indent=2), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {_CD / 'SPECIFICITY_PLACE_CORRECTED.md'}")


if __name__ == "__main__":
    main()
