"""
Derive round-1 correspondence under the frozen gate, then build round-2 cases.

Round 2 covers only what round 1 leaves open: machine themes with no confirmed match
(task C) and derived fragmentation / fusion relations (task D).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy   # noqa: E402
import cross_model_audit_q3 as cm      # noqa: E402

_HY = hy._HY


def _turns(unit):
    d = {}
    for ln in hy.units()[unit]["lines"]:
        m = re.match(r"^\[(T\d+)\]\s+([^:]+):\s*(.*)$", ln, re.S)
        if m:
            d[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    return d


def _evidence_problems(j, unit):
    """The frozen evidence gate: literal, right turn, never the moderator."""
    turns = _turns(unit)
    norm = lambda t: " ".join(str(t).split())
    bad = []
    if not j.get("quotations"):
        bad.append("cited no evidence")
    for q in j.get("quotations", []):
        tid = q.get("turn_id")
        if tid not in turns:
            bad.append(f"unknown turn {tid}")
            continue
        speaker, body = turns[tid]
        if speaker.lower().startswith("moderator"):
            bad.append(f"quotes the moderator at {tid}")
        if norm(q.get("quote", "")) not in norm(body):
            bad.append(f"quote at {tid} is not literal")
    return bad


def gate(reps: dict, unit: str):
    """
    The RELIABILITY gate only: two repetitions, agreeing, non-LOW, evidence valid.

    It deliberately says nothing about WHICH category was returned. An earlier version
    folded "category is not an accepted correspondence" in here as a failure reason,
    which filed a cleanly agreed, well-evidenced NO_CORRESPONDENCE as unresolved — and
    that would have inflated the recall upper bound, since a settled non-correspondence
    is not a plausible pending relation.
    """
    reasons = []
    if 1 not in reps or 2 not in reps:
        return None, ["one or both repetitions produced no judgement"]
    j1, j2 = reps[1], reps[2]
    if j1["category"] != j2["category"]:
        reasons.append(f"repetitions disagree: {j1['category']} vs {j2['category']}")
    if "LOW" in (j1["confidence"], j2["confidence"]):
        reasons.append("LOW confidence in at least one repetition")
    for n, j in ((1, j1), (2, j2)):
        for b in _evidence_problems(j, unit):
            reasons.append(f"repetition {n}: {b}")
    return (None if reasons else j1["category"]), reasons


def derive_round1() -> dict:
    res = json.loads((_HY / "claude_round1_results.json").read_text(encoding="utf-8"))
    by_case = {}
    for r in res["results"]:
        if r["status"] == "COMPLETE":
            by_case.setdefault(r["case_id"], {})[r["repetition_index"]] = r["judgement"]
    meta = {r["case_id"]: r for r in res["results"]}

    rows = []
    for cid, m in sorted(meta.items()):
        unit = m["blind_unit_id"]
        cat, reasons = gate(by_case.get(cid, {}), unit)
        if reasons:
            status = hy.HYBRID_UNRESOLVED
        elif cat in hy.CORRESPONDENCE_ACCEPTED:
            status = hy.HYBRID_CONFIRMED_MATCH
        elif cat in hy.CORRESPONDENCE_REJECTED:
            # Agreed, evidenced, non-LOW rejection: settled, not pending.
            status = "HYBRID_CONFIRMED_NON_CORRESPONDENCE"
        else:                                   # UNCERTAIN returned by the auditor
            status = hy.HYBRID_UNRESOLVED
            reasons = ["auditor returned UNCERTAIN in both repetitions"]
        rows.append({"case_id": cid, "blind_unit_id": unit,
                     "question_id": m["question_id"],
                     "human_key": m["provenance"]["human_key"],
                     "machine_key": m["provenance"]["machine_key"],
                     "category": cat, "status": status, "reasons": reasons})
    return {"n_cases": len(rows), "rows": rows}


def build_cases():
    """Round-2 cases: machine-only status, then derived granularity."""
    d1 = derive_round1()
    c = json.loads((_HY / "hybrid_candidates.json").read_text(encoding="utf-8"))
    H = {h["key"]: h for v in c["humans"].values() for h in v}
    M = {m["key"]: m for v in c["machines"].values() for m in v}

    confirmed_m, confirmed_h = {}, {}
    for r in d1["rows"]:
        if r["status"] == hy.HYBRID_CONFIRMED_MATCH:
            confirmed_m.setdefault(r["machine_key"], []).append(r["human_key"])
            confirmed_h.setdefault(r["human_key"], []).append(r["machine_key"])

    cases = []
    # --- task C: machine themes with no confirmed match --------------------
    for mk in sorted(M):
        if mk in confirmed_m:
            continue
        unit = mk.split("::")[0]
        cases.append({
            "case_id": f"C::{mk}", "task": "C_UNMATCHED_CANDIDATE_STATUS",
            "blind_unit_id": unit, "question_id": hy.QUESTION_OF[unit],
            "reference": None,
            "candidate": {"label": M[mk]["label"], "description": M[mk]["description"],
                          "evidence": M[mk]["evidence"]},
            "reference_inventory": [{"label": H[k]["label"],
                                     "description": H[k]["description"],
                                     "quote": H[k]["quote"]}
                                    for k in sorted(H) if k.startswith(unit + "::")],
            "sibling_candidates": [{"label": M[k]["label"],
                                    "description": M[k]["description"],
                                    "evidence": M[k]["evidence"]}
                                   for k in sorted(M)
                                   if k.startswith(unit + "::") and k != mk],
            "provenance": {"machine_key": mk}})

    # --- task D: derived fragmentation and fusion --------------------------
    for hk, mks in sorted(confirmed_h.items()):
        if len(mks) > 1:
            unit = hk.split("::")[0]
            cases.append({
                "case_id": f"D::frag::{hk}", "task": "D_GRANULARITY",
                "blind_unit_id": unit, "question_id": hy.QUESTION_OF[unit],
                "reference": {"label": H[hk]["label"],
                              "description": H[hk]["description"],
                              "quote": H[hk]["quote"]},
                "candidate": None,
                "candidate_group": [{"label": M[k]["label"],
                                     "description": M[k]["description"],
                                     "evidence": M[k]["evidence"]}
                                    for k in sorted(mks)],
                "provenance": {"human_key": hk, "machine_keys": sorted(mks),
                               "relation": "possible_fragmentation"}})
    for mk, hks in sorted(confirmed_m.items()):
        if len(hks) > 1:
            unit = mk.split("::")[0]
            cases.append({
                "case_id": f"D::fuse::{mk}", "task": "D_GRANULARITY",
                "blind_unit_id": unit, "question_id": hy.QUESTION_OF[unit],
                "reference": None,
                "reference_group": [{"label": H[k]["label"],
                                     "description": H[k]["description"],
                                     "quote": H[k]["quote"]} for k in sorted(hks)],
                "candidate": {"label": M[mk]["label"],
                              "description": M[mk]["description"],
                              "evidence": M[mk]["evidence"]},
                "provenance": {"machine_key": mk, "human_keys": sorted(hks),
                               "relation": "possible_fusion"}})

    hy._atomic(_HY / "hybrid_round1_derivation.json",
               {**d1, "confirmed_by_machine": confirmed_m,
                "confirmed_by_human": confirmed_h,
                "n_round2_cases": len(cases)})
    return cases


def main() -> int:
    d = derive_round1()
    from collections import Counter
    print("round-1 cases:", d["n_cases"])
    for k, v in Counter(r["status"] for r in d["rows"]).most_common():
        print(f"   {k:38s} {v}")
    cases = build_cases()
    from collections import Counter as C2
    print("\nround-2 cases:", len(cases))
    for k, v in C2(c["task"] for c in cases).most_common():
        print(f"   {k:34s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
