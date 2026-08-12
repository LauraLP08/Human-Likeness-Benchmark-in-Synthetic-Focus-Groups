"""
Phase 3 — deterministic, auditable candidate generation.

Similarity PROPOSES pairs; it never accepts one. Every acceptance is Claude's, under the
frozen gate. Coverage of both sides is guaranteed by construction: each human theme
contributes its top-K machine partners and each machine theme its top-K human partners,
so no theme can be absent from the case set.

The deductive codebook is not used anywhere.

    py scripts/hybrid_candidates.py --build
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy   # noqa: E402

TOP_K = 2            # per side; high sensitivity, deliberately generous
FLOOR = 0.18         # any pair at or above this is proposed as well

STOP = set("""a an the and or but if then than that this these those of in on at to for
with without from by as is are was were be been being it its it's they them their there
here what which who whom how why when we you i he she his her our your my me not no yes
do does did done have has had can could would should will just about into over under
more most less least very really quite so such own same other another each any all some
one two three thing things people person like get got make made go going went say said
""".split())


def _bag(*parts) -> set:
    toks = re.findall(r"[a-z']+", " ".join(str(p) for p in parts).lower())
    return {t for t in toks if len(t) > 2 and t not in STOP}


def _sim(a: set, b: set, sa: str, sb: str) -> float:
    """Jaccard on content words, nudged by sequence ratio. Deterministic."""
    if not a or not b:
        return 0.0
    j = len(a & b) / len(a | b)
    r = difflib.SequenceMatcher(None, sa[:400].lower(), sb[:400].lower()).ratio()
    return round(0.75 * j + 0.25 * r, 4)


def build() -> dict:
    ref = hy.human_reference()
    ext = json.loads((hy._HY / "gemini_extraction_results.json").read_text(
        encoding="utf-8"))
    if ext["n_complete"] != len(hy.UNITS):
        raise RuntimeError("not every unit is COMPLETE; candidate generation refused")

    humans, machines = {}, {}
    for t in ref["themes"]:
        u = t["blind_unit_id"]
        humans.setdefault(u, []).append({
            "human_theme_id": t["source_row_id"],
            "key": f"{u}::{t['source_row_id']}",
            "label": t["theme_label"], "description": t["theme_description"],
            "quote": t["supporting_quote"]})
    for r in ext["results"]:
        u = r["blind_unit_id"]
        for t in r["themes"]:
            machines.setdefault(u, []).append({
                "machine_theme_id": t["machine_theme_id"],
                "key": f"{u}::{t['machine_theme_id']}",
                "label": t["label"], "description": t["one_sentence_description"],
                "evidence": t.get("evidence") or [],
                "model_relevance": t.get("relevance")})

    pairs, proposed_by, rejected = {}, {}, []
    for u in hy.UNITS:
        H, M = humans.get(u, []), machines.get(u, [])
        grid = {}
        for h in H:
            hb = _bag(h["label"], h["description"], h["quote"])
            hs = f"{h['label']} {h['description']}"
            for m in M:
                mb = _bag(m["label"], m["description"],
                          " ".join(e["quote"] for e in m["evidence"]))
                ms = f"{m['label']} {m['description']}"
                grid[(h["key"], m["key"])] = _sim(hb, mb, hs, ms)

        def keep(pk, why):
            pairs[pk] = grid[pk]
            proposed_by.setdefault(pk, []).append(why)

        for h in H:                                    # cover every human theme
            for mk, _ in sorted(((m["key"], grid[(h["key"], m["key"])]) for m in M),
                                key=lambda x: (-x[1], x[0]))[:TOP_K]:
                keep((h["key"], mk), "top_k_for_human")
        for m in M:                                    # cover every machine theme
            for hk, _ in sorted(((h["key"], grid[(h["key"], m["key"])]) for h in H),
                                key=lambda x: (-x[1], x[0]))[:TOP_K]:
                keep((hk, m["key"]), "top_k_for_machine")
        for pk, v in grid.items():                     # plus anything above the floor
            if v >= FLOOR:
                keep(pk, "above_similarity_floor")
        for pk, v in grid.items():
            if pk not in pairs:
                rejected.append({"human_key": pk[0], "machine_key": pk[1],
                                 "similarity": v,
                                 "reason": "not top-K for either side and below floor"})

    covered_h = {pk[0] for pk in pairs}
    covered_m = {pk[1] for pk in pairs}
    all_h = {h["key"] for v in humans.values() for h in v}
    all_m = {m["key"] for v in machines.values() for m in v}
    no_candidate = sorted((all_h - covered_h) | (all_m - covered_m))

    cases = [{"case_id": f"P::{hk}::{mk}", "blind_unit_id": hk.split("::")[0],
              "question_id": hy.QUESTION_OF[hk.split("::")[0]],
              "human_key": hk, "machine_key": mk,
              "similarity": pairs[(hk, mk)],
              "proposed_by": sorted(set(proposed_by[(hk, mk)]))}
             for hk, mk in sorted(pairs)]

    out = {"classification": hy.CLASSIFICATION,
           "method": {
               "rule": "top-K per side (K=2) UNION any pair with similarity >= floor",
               "K": TOP_K, "floor": FLOOR,
               "similarity": "0.75 x Jaccard(content words) + 0.25 x SequenceMatcher ratio",
               "deterministic": True,
               "similarity_role": ("PROPOSES pairs only. It never accepts one; every "
                                   "acceptance is Claude's under the frozen gate."),
               "codebook_used": False},
           "n_human_themes": len(all_h), "n_machine_themes": len(all_m),
           "n_candidate_pairs": len(cases),
           "n_pairs_possible_cartesian": sum(len(humans.get(u, [])) * len(machines.get(u, []))
                                             for u in hy.UNITS),
           "coverage": {"human_side": f"{len(covered_h)}/{len(all_h)}",
                        "machine_side": f"{len(covered_m)}/{len(all_m)}",
                        "complete": not no_candidate},
           "no_candidate_found": no_candidate,
           "rejected_pairs": sorted(rejected, key=lambda r: -r["similarity"]),
           "humans": humans, "machines": machines, "cases": cases}
    hy._atomic(hy._HY / "hybrid_candidates.json", out)
    return out


def main() -> int:
    o = build()
    print("human themes        :", o["n_human_themes"])
    print("machine themes      :", o["n_machine_themes"])
    print("candidate pairs     :", o["n_candidate_pairs"],
          f"(of {o['n_pairs_possible_cartesian']} cartesian)")
    print("coverage human side :", o["coverage"]["human_side"])
    print("coverage machine    :", o["coverage"]["machine_side"])
    print("NO_CANDIDATE_FOUND  :", o["no_candidate_found"] or "none")
    print("rejected pairs kept :", len(o["rejected_pairs"]))
    print("COVERAGE COMPLETE   :", o["coverage"]["complete"])
    if not o["coverage"]["complete"]:
        print("STOP — improve candidate generation; never invent matches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
