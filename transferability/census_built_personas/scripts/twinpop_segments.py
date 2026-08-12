#!/usr/bin/env python3
"""
twinpop_segments.py — per-question segmentation of the 6 twinpop runs, using the
production segmenter.

Same discipline as twinpop_comparable_window.py: `inductive_segments.segment_synthetic`
is IMPORTED, never reimplemented, because the segments only mean anything if the
twinpop sections are cut by the same rule ("latest explicit guide-question ask across
every non-empty moderator_log utterance") that cut the sections it will be compared
against.

REGRESSION GATE
Before segmenting twinpop, three canonical runs are re-segmented and every
`section_sha256`, opener turn and closing turn is compared against the frozen
`inductive_segments.json`. `segment_synthetic` does not write, so nothing needs
restoring — the frozen file is only ever read.

WHAT A FAILURE MEANS
`segment_synthetic` raises `Unresolved` when it cannot anchor all five questions by
content. That is not an error to work around: an unanchorable run has no defensible
Q1..Q5 boundaries, and inventing them by position is precisely what the production
docstring forbids ("Position is never used as a fallback"). Such a run is recorded
as UNRESOLVED and excluded from R4, with the exclusion reported, never silently
dropped.

No API calls.

Usage:
    py scripts/twinpop_segments.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import inductive_segments as iseg  # noqa: E402

FROZEN = ROOT / "analysis/production_evaluation/final/inductive_segments.json"
DERIVED = ROOT / "analysis/production_evaluation/comparable_transcripts"

CONDITION = "twinpop"
# Canonical set. `fg3_twinpop_run04` is the single authorised replacement for
# run03 and inherits its canonical index 3 — the convention the corpus already
# uses, where fg4's run04 replaced run02 and took index 2.
TWINPOP_RUNS = [
    ("macho_meals_fg3_twinpop_run01", "fg3", 1),
    ("macho_meals_fg3_twinpop_run02", "fg3", 2),
    ("macho_meals_fg3_twinpop_run04", "fg3", 3),
    ("macho_meals_fg4_twinpop_run01", "fg4", 1),
    ("macho_meals_fg4_twinpop_run02", "fg4", 2),
    ("macho_meals_fg4_twinpop_run03", "fg4", 3),
]
# Archived, NOT deleted. Still segmented and still reported every run, so the
# exclusion stays visible in the output rather than becoming an absence nobody
# can see. Its sections never enter the corpus.
ARCHIVED_RUNS = [
    ("macho_meals_fg3_twinpop_run03", "fg3", 3, "ARCHIVED_UNANCHORABLE_Q5_BOUNDARY"),
]
CANONICAL_MAX_CLOSING_RESIDUE = None  # measured at runtime from the canonical corpus

# ---------------------------------------------------------------------------
# Q5 RECOGNISER — widened, and the widening is PROVED INERT on every run.
#
# The frozen Q5 markers are ['more appealing', 'appealing.{0,40}(to you|to men|
# in the first place)'], derived from the scripted section-5 question ("What might
# make plant-based foods more appealing to you or other men you know?"). Two twinpop
# runs could not be anchored under them. Inspecting the utterances showed the
# moderator DID pose section 5 and simply paraphrased it — which the system permits
# and `segment_synthetic` explicitly accommodates ("reformulations do not open a new
# section"). fg3_run02 asked "...for any of you to find it genuinely appealing? Or
# for the men you know to?", which the second marker misses by one word ("the men",
# not "to men").
#
# So the sessions are sound and the RECOGNISER is short. The repair is therefore not
# "a wider rule for twinpop" — that would make the sections incomparable, which is
# the whole point of importing the production segmenter. It is the same rule with a
# strictly wider recogniser, admissible only while it is INERT: it must reproduce
# every canonical section hash and must not move any twinpop section that already
# anchored. `inertness_gate()` asserts exactly that, on every run of this script. If
# it ever stops holding, the widening is withdrawn automatically and nothing is cut.
#
# fg3_run03 remains UNRESOLVED and is NOT rescued. It contains no member of the
# appealing/attractive/appeal family at all; its section-5 ask is phrased in Q4's
# vocabulary ("what would it take", "what would need to shift"). Reaching it would
# require keying on Q4 language, which could move the Q4/Q5 boundary elsewhere. It is
# reported as an excluded run, not segmented by a rule bent to fit it.
# ---------------------------------------------------------------------------
Q5_MARKERS_FROZEN = ["more appealing",
                     r"appealing.{0,40}(to you|to men|in the first place)"]
Q5_MARKERS_WIDENED = Q5_MARKERS_FROZEN + ["appealing"]
REGRESSION_RUNS = ["macho_meals_fg3_run01", "macho_meals_fg3_demoonly_run01",
                   "macho_meals_fg4_run01"]


def canonical_closing_residues() -> list[dict]:
    """The excluded-closing-residue band, MEASURED on the canonical corpus rather
    than assumed. Hardcoding a tolerance here would be a post-hoc threshold; this
    reads the band off the same 30 documents twinpop is compared against."""
    frozen = frozen_segments()
    rows = []
    for run in sorted({s["physical_run"] for s in frozen if s["condition"] != "human"}):
        mine = [s for s in frozen if s["physical_run"] == run]
        s0 = mine[0]
        rec = {"path": s0["source_path"], "physical_run": run, "condition": s0["condition"],
               "fg": s0["fg"], "canonical_replication_index": s0["canonical_replication_index"],
               "sha256": s0["source_sha256"]}
        try:
            segs, total, _, _ = iseg.segment_synthetic(rec)
        except iseg.Unresolved:
            continue
        rows.append({"run": run, "residue": total - sum(s["total_words"] for s in segs)})
    return rows


def frozen_segments() -> list[dict]:
    return json.loads(FROZEN.read_text(encoding="utf-8"))["segments"]


def rec_for(run: str, fg: str, repl: int) -> dict:
    path = DERIVED / run / "comparable_transcript.json"
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "physical_run": run, "condition": CONDITION, "fg": fg,
            "canonical_replication_index": repl,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def regression_gate() -> tuple[bool, list[dict]]:
    """Re-segment canonical runs; demand identical section hashes and boundaries."""
    frozen = frozen_segments()
    rows = []
    for run in REGRESSION_RUNS:
        mine = [s for s in frozen if s["physical_run"] == run]
        if not mine:
            rows.append({"run": run, "found_in_frozen": False, "matches": False})
            continue
        s0 = mine[0]
        rec = {"path": s0["source_path"], "physical_run": run,
               "condition": s0["condition"], "fg": s0["fg"],
               "canonical_replication_index": s0["canonical_replication_index"],
               "sha256": s0["source_sha256"]}
        try:
            segs, _, _, _ = iseg.segment_synthetic(rec)
        except iseg.Unresolved as exc:
            rows.append({"run": run, "found_in_frozen": True, "matches": False,
                         "error": f"Unresolved: {exc}"})
            continue
        by_q = {s["question"]: s for s in mine}
        checks = []
        for s in segs:
            f = by_q.get(s["question"], {})
            checks.append({
                "question": s["question"],
                "section_sha256_matches": s["section_sha256"] == f.get("section_sha256"),
                "opens_at_matches": (s["boundary_provenance"]["opens_at_turn"]
                                     == f.get("boundary_provenance", {}).get("opens_at_turn")),
                "closes_before_matches": (s["boundary_provenance"]["closes_before_turn"]
                                          == f.get("boundary_provenance", {}).get("closes_before_turn")),
                "words_match": s["total_words"] == f.get("total_words"),
            })
        matched = all(all(v for k, v in c.items() if k != "question") for c in checks)
        rows.append({"run": run, "found_in_frozen": True, "n_questions": len(segs),
                     "matches": matched, "per_question": checks})
    return all(r.get("matches") for r in rows), rows


def inertness_gate() -> tuple[bool, dict]:
    """The widened Q5 recogniser is admissible ONLY if it changes nothing that the
    frozen one already decided. Asserts two things:
      (1) all canonical synthetic runs reproduce their frozen section hashes;
      (2) every twinpop run that anchors under the frozen markers gets identical
          sections under the widened ones.
    (2) matters as much as (1): a widening that rescued run02 by shifting run01's
        Q4/Q5 boundary would satisfy (1) and still be corrupt."""
    frozen = frozen_segments()
    canon_runs = sorted({s["physical_run"] for s in frozen if s["condition"] != "human"})

    def cut(rec):
        try:
            segs, _, _, _ = iseg.segment_synthetic(rec)
            return [s["section_sha256"] for s in segs]
        except iseg.Unresolved:
            return None

    baseline_tw = {}
    iseg.QUESTION_MARKERS[5] = list(Q5_MARKERS_FROZEN)
    for run, fg, repl in TWINPOP_RUNS:
        baseline_tw[run] = cut(rec_for(run, fg, repl))

    iseg.QUESTION_MARKERS[5] = list(Q5_MARKERS_WIDENED)
    canon_changed = []
    for run in canon_runs:
        mine = [s for s in frozen if s["physical_run"] == run]
        s0 = mine[0]
        got = cut({"path": s0["source_path"], "physical_run": run,
                   "condition": s0["condition"], "fg": s0["fg"],
                   "canonical_replication_index": s0["canonical_replication_index"],
                   "sha256": s0["source_sha256"]})
        want = [s["section_sha256"] for s in sorted(mine, key=lambda x: x["question"])]
        if got != want:
            canon_changed.append(run)

    tw_moved, tw_rescued = [], []
    for run, fg, repl in TWINPOP_RUNS:
        now = cut(rec_for(run, fg, repl))
        was = baseline_tw[run]
        if was is not None and now != was:
            tw_moved.append(run)
        if was is None and now is not None:
            tw_rescued.append(run)

    ok = not canon_changed and not tw_moved
    if not ok:                       # withdraw the widening; cut nothing with it
        iseg.QUESTION_MARKERS[5] = list(Q5_MARKERS_FROZEN)
    return ok, {
        "frozen_markers": Q5_MARKERS_FROZEN, "widened_markers": Q5_MARKERS_WIDENED,
        "canonical_runs_tested": len(canon_runs),
        "canonical_runs_with_changed_cuts": canon_changed,
        "twinpop_already_anchored_that_moved": tw_moved,
        "twinpop_rescued_by_widening": tw_rescued,
        "still_unresolved_under_widened": [r for r, _, _ in TWINPOP_RUNS
                                           if cut(rec_for(r, *[(f, i) for x, f, i in TWINPOP_RUNS
                                                               if x == r][0])) is None],
        "inert": ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    print("GATE DE REGRESION — el segmentador aun reproduce los cortes congelados\n")
    ok, rows = regression_gate()
    for r in rows:
        mark = "OK   " if r.get("matches") else "FALLA"
        print(f"  {mark} {r['run']:34s} preguntas={r.get('n_questions','-')}  "
              f"{r.get('error','')}")
        if not r.get("matches"):
            for c in r.get("per_question", []):
                bad = [k for k, v in c.items() if k != "question" and not v]
                if bad:
                    print(f"          Q{c['question']}: difiere en {bad}")

    out = {"gate": "twinpop_segments", "regression_gate_passed": ok, "regression": rows}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not ok:
        out["segments"] = []
        out["abort_reason"] = ("el segmentador no reproduce los cortes congelados; "
                               "segmentar twinpop con una regla que ya no reproduce el "
                               "corpus haria incomparables las secciones.")
        (args.out_dir / "twinpop_segments.json").write_text(
            json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print("\nGATE FALLA — no se segmenta twinpop.")
        return 1

    global CANONICAL_MAX_CLOSING_RESIDUE
    canon = canonical_closing_residues()
    residues = [r["residue"] for r in canon]
    CANONICAL_MAX_CLOSING_RESIDUE = max(residues)
    out["canonical_closing_residue_band"] = {
        "n_runs": len(canon), "min": min(residues), "max": max(residues),
        "note": ("residuo de cierre excluido por construccion; banda medida sobre el "
                 "corpus canonico, no fijada a mano"),
    }
    print(f"\nBanda canonica de residuo de cierre: {min(residues)}-{max(residues)} "
          f"palabras sobre {len(canon)} runs\n")

    print("GATE DE INERCIA — el reconocedor Q5 ensanchado no puede mover nada ya decidido\n")
    inert_ok, inert = inertness_gate()
    print(f"  runs canonicos probados            : {inert['canonical_runs_tested']}")
    print(f"  canonicos con cortes alterados     : {inert['canonical_runs_with_changed_cuts'] or 'ninguno'}")
    print(f"  twinpop ya anclados que se movieron: {inert['twinpop_already_anchored_that_moved'] or 'ninguno'}")
    print(f"  twinpop rescatados                 : {inert['twinpop_rescued_by_widening'] or 'ninguno'}")
    print(f"  siguen sin resolver                : {inert['still_unresolved_under_widened'] or 'ninguno'}")
    out["q5_widening_inertness"] = inert
    if not inert_ok:
        print("\n  NO INERTE — ensanchamiento retirado; se corta con los marcadores congelados.\n")
    else:
        print("  -> INERTE. Se adopta.\n")

    print("GATE PASA. Segmentando twinpop:\n")
    all_segs, unresolved, flags = [], [], []
    for run, fg, repl in TWINPOP_RUNS:
        rec = rec_for(run, fg, repl)
        try:
            segs, total_words, _sha, _amb = iseg.segment_synthetic(rec)
        except iseg.Unresolved as exc:
            unresolved.append({"run": run, "reason": str(exc)})
            print(f"  NO RESUELTO {run:34s} {exc}")
            continue
        # Reconciliation. The first version of this check demanded EXACT equality
        # with the document total, following the production docstring. It reported
        # all four segmented runs as failures. Re-running the same check on six
        # canonical runs showed none of them reconciles exactly either: the closing
        # residue is excluded by construction (`end_of_q5 = closing_at`), leaving
        # 221-307 words unassigned. The assertion was miscalibrated against the
        # docstring rather than against the corpus, so it was the check that was
        # wrong, not the data. What is actually assertable: the residue is
        # non-negative and no larger than the canonical corpus ever produces.
        seg_words = sum(s["total_words"] for s in segs)
        residue = total_words - seg_words
        recon = 0 <= residue <= CANONICAL_MAX_CLOSING_RESIDUE
        all_segs.extend(segs)
        print(f"  OK    {run:34s} Q1..Q5 palabras={[s['total_words'] for s in segs]} "
              f"residuo_cierre={residue}{'' if recon else '  <-- MARCADO (retenido)'}")
        if not recon:
            # A FLAG, never an exclusion — and the two must not share a list, or a
            # downstream reader cannot tell whether this run's sections are in the
            # corpus or out of it. The residue is the CLOSING text, which the
            # segmenter excludes by construction; it enters no analysis. A residue
            # above the canonical envelope says this session's closing ran longer
            # than any canonical one, which is a property of text that was thrown
            # away. It cannot contaminate the five sections that were kept, so it
            # is recorded and the run stays in.
            flags.append({"run": run, "closing_residue": residue,
                          "canonical_max": CANONICAL_MAX_CLOSING_RESIDUE,
                          "excess_words": residue - CANONICAL_MAX_CLOSING_RESIDUE,
                          "excluded_from_corpus": False,
                          "why_not_excluded": ("el residuo es el cierre, excluido por "
                                               "construccion; no entra en ningun analisis")})

    archived = []
    for run, fg, repl, label in ARCHIVED_RUNS:
        try:
            segs, _, _, _ = iseg.segment_synthetic(rec_for(run, fg, repl))
            status = f"anchors now ({len(segs)} sections) but stays archived"
        except iseg.Unresolved as exc:
            status = str(exc)
        archived.append({"run": run, "label": label, "status": status,
                         "in_corpus": False})
        print(f"  ARCHIVADO {run:34s} [{label}] {status[:60]}")
    out["archived_runs"] = archived

    out["segments"] = all_segs
    out["unresolved_excluded"] = unresolved
    out["flagged_but_retained"] = flags
    out["n_runs_segmented"] = len({s["physical_run"] for s in all_segs})
    (args.out_dir / "twinpop_segments.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{out['n_runs_segmented']}/6 runs segmentados, {len(all_segs)} secciones "
          f"-> {args.out_dir / 'twinpop_segments.json'}")
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
