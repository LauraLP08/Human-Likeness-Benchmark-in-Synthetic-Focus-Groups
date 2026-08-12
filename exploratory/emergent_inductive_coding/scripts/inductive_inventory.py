"""
Universe inventory for RETROSPECTIVE_INDUCTIVE_THEMATIC_ACCUMULATION_ANALYSIS.

Offline only: reads sealed artefacts, makes no API call, writes one JSON.

Two facts this module exists to enforce, both verified against sealed artefacts rather
than assumed:

  * **Human FG5 contains no Question 4.** `gold_standard_boundary_audit.csv` records
    `question_headers_found = 1|2|3|5` for `human/fg5`, and the standardized transcript
    confirms it: the moderator opens Q1, Q2, Q3, Q5 and never asks Q4. The universe is
    therefore **174** question x document units, not 175. A missing section is a
    property of the fieldwork and must never be read as thematic absence.

  * **The 30 synthetic runs come from `frozen_evaluator_inputs.json` only.** They cannot
    be reconstructed by globbing `run0{1..3}`: the canonical set includes
    `macho_meals_fg4_run04` and `macho_meals_fg5_run04`, and excludes archived runs. A
    pattern-based reconstruction silently substitutes a different corpus.

    py scripts/inductive_inventory.py
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PE = _ROOT / "analysis/production_evaluation"
_FROZEN = _PE / "frozen_evaluator_inputs.json"
_AUDIT = _PE / "gold_standard_boundary_audit.csv"
_HUMAN = _ROOT / "data/datasets_transcripts/standardized/macho_meals"
_OUT = _PE / "final/inductive_inventory.json"

QUESTIONS = [1, 2, 3, 4, 5]
FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]
CONDITIONS = ["human", "enriched", "demographics-only"]

# Q4 is missing for one human focus group, so its curves rest on four FGs, not five.
# 4! = 24 orderings rather than 5! = 120. Stated here so the asymmetry is designed in
# rather than discovered at analysis time.
FULL_QUESTIONS = [1, 2, 3, 5]
RESTRICTED = {4: ["fg1", "fg2", "fg3", "fg4"]}
_HDR = re.compile(r"^\s*Question\s+(\d)\b")


def canonical_synthetic():
    """The 30 synthetic documents, from the frozen manifest and nowhere else."""
    j = json.loads(_FROZEN.read_text(encoding="utf-8"))
    out = []
    for r in j["synthetic_inputs"]:
        out.append({
            "condition": r["condition"], "fg": r["fg"],
            "canonical_replication_index": r["canonical_replication_index"],
            "physical_run": r["physical_run"],
            "path": r["path"], "sha256": r["sha256"],
            "total_words": r["total_words"], "entries": r["entries"]})
    return out


def canonical_human():
    j = json.loads(_FROZEN.read_text(encoding="utf-8"))
    return [{"condition": "human", "fg": r.get("fg"), "path": r.get("path"),
             "sha256": r.get("sha256"), "total_words": r.get("total_words")}
            for r in j["human_inputs"]]


def human_questions(fg: str):
    """Question numbers actually asked in a human transcript, read from the source."""
    t = json.loads((_HUMAN / fg / "transcript.json").read_text(encoding="utf-8"))
    found = []
    for e in t:
        m = _HDR.match(e.get("content", ""))
        if m and e.get("speaker_role") == "moderator":
            n = int(m.group(1))
            if n not in found:
                found.append(n)
    return sorted(found)


def audit_questions():
    """`question_headers_found` per stratum x fg, from the sealed boundary audit."""
    out = {}
    with _AUDIT.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hdr = r["question_headers_found"].strip()
            out[(r["stratum"], r["fg"])] = (
                sorted(int(x) for x in hdr.split("|") if x) if hdr else None)
    return out


def build() -> dict:
    syn = canonical_synthetic()
    hum = canonical_human()
    audit = audit_questions()

    problems = []
    if len(syn) != 30:
        problems.append(f"expected 30 synthetic documents, frozen manifest has {len(syn)}")
    if len(hum) != 5:
        problems.append(f"expected 5 human documents, frozen manifest has {len(hum)}")

    # every (condition, fg) must contribute exactly 3 canonical replicates
    per_cell = defaultdict(list)
    for r in syn:
        per_cell[(r["condition"], r["fg"])].append(r["canonical_replication_index"])
    for cond in ("enriched", "demographics-only"):
        for fg in FGS:
            reps = sorted(per_cell[(cond, fg)])
            if reps != [1, 2, 3]:
                problems.append(f"{cond}/{fg} canonical replicates {reps} != [1,2,3]")

    # the canonical set is NOT the run0{1..3} glob
    globbed = {f"macho_meals_{fg}{'_demoonly' if c == 'demographics-only' else ''}_run0{i}"
               for c in ("enriched", "demographics-only") for fg in FGS
               for i in (1, 2, 3)}
    canon = {r["physical_run"] for r in syn}
    only_canonical = sorted(canon - globbed)
    only_globbed = sorted(globbed - canon)

    # ---- per-document question availability --------------------------------
    docs = []
    for r in hum:
        qs = human_questions(r["fg"])
        a = audit.get(("human", r["fg"]))
        if a is not None and a != qs:
            problems.append(f"human/{r['fg']}: transcript says {qs}, audit says {a}")
        docs.append({**r, "questions_available": qs,
                     "questions_missing": [q for q in QUESTIONS if q not in qs],
                     "source_of_questions": "literal `Question N.` moderator headers"})
    for r in syn:
        # The moderator agent works through the frozen guide, so all five sections
        # exist by construction; this is asserted at extraction time against the
        # section transitions rather than assumed here.
        docs.append({**r, "questions_available": list(QUESTIONS),
                     "questions_missing": [],
                     "source_of_questions": ("moderator_log.section_transition, "
                                             "verified at extraction time")})

    units = [{"condition": d["condition"], "fg": d["fg"],
              "canonical_replication_index": d.get("canonical_replication_index"),
              "physical_run": d.get("physical_run"), "question": q}
             for d in docs for q in d["questions_available"]]

    if len(units) != 174:
        problems.append(f"expected 174 question x document units, built {len(units)}")

    missing = [(d["condition"], d["fg"], d["questions_missing"])
               for d in docs if d["questions_missing"]]
    if missing != [("human", "fg5", [4])]:
        problems.append(f"unexpected missing-question pattern: {missing}")

    # ---- per-question design ----------------------------------------------
    # Two distinct quantities that must not be conflated:
    #   n_units_in_universe  — units that EXIST and are extracted
    #   n_units_in_curve     — units the accumulation curve for that question USES
    # They differ only for Q4: synthetic FG5 does contain a Q4 section, but the human
    # FG5 counterpart does not, so including it would make the Q4 curve asymmetric —
    # five synthetic FGs against four human ones.
    import math
    per_q = {}
    for q in QUESTIONS:
        fgs = RESTRICTED.get(q, FGS)
        in_universe = [u for u in units if u["question"] == q]
        in_curve = [u for u in in_universe if u["fg"] in fgs]
        excluded = [u for u in in_universe if u["fg"] not in fgs]
        per_q[q] = {
            "fgs_in_scope": fgs,
            "n_fgs": len(fgs),
            "n_orderings": math.factorial(len(fgs)),
            "n_units_in_universe": len(in_universe),
            "n_units_in_curve": len(in_curve),
            "n_units_extracted_but_excluded_from_curve": len(excluded),
            "excluded_from_curve": [
                {"condition": u["condition"], "fg": u["fg"],
                 "canonical_replication_index": u["canonical_replication_index"]}
                for u in excluded],
            "restricted": q in RESTRICTED,
            "restriction_reason": (
                "human FG5 contains no Question 4, so a five-FG curve cannot be built "
                "for any condition without imputing content. All three conditions are "
                "restricted to FG1-FG4 so the comparison stays symmetric; the six "
                "synthetic FG5 Q4 units are still extracted and reported, but only as "
                "an out-of-curve descriptor."
                if q in RESTRICTED else None),
            "human_fg5_q4_is_not_thematic_absence": (
                "human FG5 contributes no Q4 unit because the question was never asked. "
                "It is missing data, never a zero and never thematic absence."
                if q == 4 else None),
        }
        want_universe = 34 if q == 4 else 35
        want_curve = 28 if q == 4 else 35
        if len(in_universe) != want_universe:
            problems.append(f"Q{q}: {len(in_universe)} units in universe, "
                            f"expected {want_universe}")
        if len(in_curve) != want_curve:
            problems.append(f"Q{q}: {len(in_curve)} units in curve, expected {want_curve}")

    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": "RETROSPECTIVE_INDUCTIVE_THEMATIC_ACCUMULATION_INVENTORY",
        "no_api_calls": True,
        "n_documents": len(docs),
        "n_units": len(units),
        "n_units_expected": 174,
        "synthetic_source": "analysis/production_evaluation/frozen_evaluator_inputs.json",
        "synthetic_not_reconstructed_by_glob": True,
        "canonical_only_not_in_run01_03_glob": only_canonical,
        "glob_would_have_included_but_is_not_canonical": only_globbed,
        "human_fg5": {
            "questions_available": human_questions("fg5"),
            "question_4": "NOT ASKED IN FIELDWORK",
            "interpretation_rule": (
                "a section that was never asked is missing data, NEVER thematic "
                "absence; human FG5 contributes no Q4 unit and is excluded from the Q4 "
                "curve rather than counted as zero"),
            "audit_source": "gold_standard_boundary_audit.csv question_headers_found",
        },
        "per_question": per_q,
        "documents": docs,
        "units": units,
        "problems": problems,
        "pass": not problems,
    }
    return out


def write(out: dict, path=None) -> Path:
    """
    Persist the inventory. Kept OUT of build() deliberately.

    build() used to write as a side effect, so merely importing it in a test rewrote
    `final/inductive_inventory.json` — a frozen artefact of work that is still at NO-GO.
    Computation and persistence are now separate: build() is pure, and only an explicit
    write() call touches disk.
    """
    path = Path(path) if path is not None else _OUT
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def main() -> int:
    o = build()
    write(o)
    print(f"documents {o['n_documents']}  units {o['n_units']} "
          f"(expected {o['n_units_expected']})\n")
    print("=== per question ===")
    for q, v in o["per_question"].items():
        print(f"  Q{q}: universe {v['n_units_in_universe']:>2d} | curve "
              f"{v['n_units_in_curve']:>2d} | {v['n_fgs']} FGs, "
              f"{v['n_orderings']:>3d} orderings"
              f"{'   <- RESTRICTED (' + str(v['n_units_extracted_but_excluded_from_curve']) + ' extracted, out of curve)' if v['restricted'] else ''}")
    print(f"\nhuman FG5 questions: {o['human_fg5']['questions_available']}  "
          f"-> Q4 {o['human_fg5']['question_4']}")
    print(f"\ncanonical runs a run0[1-3] glob would MISS: "
          f"{o['canonical_only_not_in_run01_03_glob']}")
    print(f"runs the glob would wrongly include: "
          f"{o['glob_would_have_included_but_is_not_canonical']}")
    print(f"\nPASS: {o['pass']}")
    for p in o["problems"]:
        print("   PROBLEM:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
