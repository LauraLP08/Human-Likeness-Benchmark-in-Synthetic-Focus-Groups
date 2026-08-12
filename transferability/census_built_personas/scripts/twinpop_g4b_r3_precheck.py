#!/usr/bin/env python3
"""
twinpop_g4b_r3_precheck.py — Gate G4b, the R3 pre-check.

R3 (pre-registro §7): `demoonly` is NOT a no-biography control. Its agents already
invent biographical specifics — a demoonly agent with only "Suburban, North West"
in its payload said "North West — suburbs just outside Manchester". So the twinpop
contrast is not "no enrichment vs enrichment" but "self-invented modal enrichment
vs external census enrichment".

If what the model invents unprompted already matches the population mode, a
confirmation of P1 would mean "the model already knew the census", not "generic
richness does not help". This gate extracts what the demoonly agents actually said
about themselves in the existing FG3/FG4 transcripts and puts it beside the census
cell drawn for the same agent, so the comparison is on the record BEFORE any
twinpop session runs.

Output is a declaration, not a stop condition. No API calls.

Usage:
    py scripts/twinpop_g4b_r3_precheck.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "output" / "session_logs"

RUNS = [f"macho_meals_fg{n}_demoonly_run0{m}" for n in (3, 4) for m in (1, 2, 3)]

# First-person biographical markers, grouped by the narrative field they map to.
MARKERS = {
    "working_life": r"\b(i work|i'm a|i am a|my job|my work|at work|my boss|my company|"
                    r"i run a|self-employed|retired|my shift|my career|i manage|my office|"
                    r"my trade|apprentice|foreman|engineer|driver|teacher|nurse|builder)\b",
    "home_and_household": r"\b(my wife|my husband|my partner|my kids|my children|my son|"
                          r"my daughter|my family|live alone|on my own|my house|my flat|"
                          r"my home|my mortgage|i rent|divorced|married|single)\b",
    "week_and_hobbies": r"\b(my car|i drive|i commute|the gym|football|golf|fishing|"
                        r"my garden|gardening|diy|weekends|my hobby|i play|walking|cycling)\b",
    "place": r"\b(manchester|liverpool|leeds|birmingham|london|bristol|norwich|ipswich|"
             r"cambridge|brighton|reading|oxford|exeter|plymouth|chelmsford|colchester)\b",
}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    cells = {c["agent_id"]: c for c in
             json.loads((args.out_dir / "microdata_cells.json").read_text(encoding="utf-8"))}
    name_to_id = {c["name"]: aid for aid, c in cells.items()}

    found: dict[str, dict[str, list[str]]] = {aid: {k: [] for k in MARKERS} for aid in cells}
    n_turns = 0

    for run in RUNS:
        path = LOGS / run / "transcript.json"
        if not path.exists():
            print(f"  (missing {run})")
            continue
        for turn in json.loads(path.read_text(encoding="utf-8")):
            speaker = turn.get("speaker_name") or ""
            if speaker not in name_to_id:
                continue
            n_turns += 1
            aid = name_to_id[speaker]
            for sent in sentences(turn.get("content") or ""):
                low = sent.lower()
                for field, pattern in MARKERS.items():
                    if re.search(pattern, low):
                        found[aid][field].append(sent)

    report = []
    print(f"scanned {n_turns} demoonly participant turns across {len(RUNS)} runs\n")
    for aid in sorted(cells):
        cell = cells[aid]
        attrs = cell["candidates"][0]["attributes"]
        census = {
            "occupation": attrs["working_life"].get("occupation_105a", ""),
            "household": attrs["home_and_household"].get("hh_size_9a", ""),
            "living": attrs["home_and_household"].get("living_arrangements_11a", ""),
        }
        counts = {k: len(v) for k, v in found[aid].items()}
        report.append({"agent_id": aid, "name": cell["name"],
                       "self_invented_counts": counts,
                       "census_drawn": census,
                       "examples": {k: v[:3] for k, v in found[aid].items() if v}})
        print(f"{cell['name']:8s} invented: " +
              " ".join(f"{k}={counts[k]}" for k in MARKERS))
        print(f"         census  : {census['occupation'][:58]} | {census['household']}")
        for field in ("working_life", "home_and_household"):
            for s in found[aid][field][:2]:
                print(f"         said    : \"{s[:96]}\"")
        print()

    total = sum(sum(r["self_invented_counts"].values()) for r in report)
    out = {
        "gate": "G4b", "risk": "R3",
        "n_demoonly_turns_scanned": n_turns,
        "total_self_invented_biographical_statements": total,
        "interpretation_rule": (
            "If demoonly agents already invent biography at this rate and it matches the "
            "population mode, a CONFIRMATION of P1 (twinpop close to demoonly) would mean "
            "'the model already knew the census', not 'generic richness does not help'. "
            "This is declared before any twinpop session runs; it does not stop the arm."
        ),
        "agents": report,
    }
    (args.out_dir / "G4b_R3_precheck.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"total self-invented biographical statements: {total}")
    print(f"-> {args.out_dir / 'G4b_R3_precheck.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
