"""
The complete 93-pair correspondence universe: 61 historical + 32 complementary.

Historical decisions are carried forward exactly as they were derived. Nothing here
re-runs, re-judges or re-interprets them; the complement is added alongside, and the
derived quantities are recomputed from the union.

The rule that motivates the whole correction: a human theme may be called
confirmed-not-recovered only when every machine theme in its unit has been adjudicated
against it and every one of those pairs came back a confirmed non-correspondence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy      # noqa: E402
import hybrid_round2 as r2                # noqa: E402
import hybrid_complement as hc            # noqa: E402

_HY = hy._HY
NON_CORR = "HYBRID_CONFIRMED_NON_CORRESPONDENCE"


def _L(n):
    return json.loads((_HY / n).read_text(encoding="utf-8"))


def _classify(cat, reasons):
    """The frozen mapping, identical for both source rounds."""
    if reasons:
        return hy.HYBRID_UNRESOLVED, reasons
    if cat in hy.CORRESPONDENCE_ACCEPTED:
        return hy.HYBRID_CONFIRMED_MATCH, []
    if cat in hy.CORRESPONDENCE_REJECTED:
        return NON_CORR, []
    return hy.HYBRID_UNRESOLVED, ["auditor returned UNCERTAIN in both repetitions"]


def derive_complement() -> list[dict]:
    res = _L("claude_complement_results.json")
    by_case, meta = {}, {}
    attempts = {}
    for r in res["results"]:
        meta[r["case_id"]] = r
        attempts.setdefault(r["case_id"], []).append(
            {"custom_id": r["custom_id"], "repetition_index": r["repetition_index"],
             "status": r["status"], "attempt": r.get("attempt", 1),
             "retry_reason": r.get("retry_reason")})
        if r["status"] == "COMPLETE":
            by_case.setdefault(r["case_id"], {})[r["repetition_index"]] = r["judgement"]

    rows = []
    for cid, m in sorted(meta.items()):
        unit = m["blind_unit_id"]
        cat, reasons = r2.gate(by_case.get(cid, {}), unit)
        status, reasons = _classify(cat, reasons)
        rows.append({
            "case_id": cid, "source_round": hc.SOURCE_COMPLEMENT,
            "blind_unit_id": unit, "question_id": m["question_id"],
            "human_key": m["provenance"]["human_key"],
            "machine_key": m["provenance"]["machine_key"],
            "category": cat, "status": status, "reasons": reasons,
            "repetitions": {str(k): {"category": v["category"],
                                     "confidence": v["confidence"],
                                     "n_quotations": len(v.get("quotations") or [])}
                            for k, v in sorted(by_case.get(cid, {}).items())},
            "evidence_verified": not any("literal" in r or "moderator" in r
                                         or "unknown turn" in r for r in reasons),
            "attempts": sorted(attempts[cid],
                               key=lambda a: (a["repetition_index"], a["attempt"]))})
    return rows


def integrity_problems(rows: list[dict], cands: dict, hist: list[dict] | None = None):
    """
    The structural guarantees of the universe, in one place.

    build() and the mutation tests both call this. A mutation test that re-implements
    the checks it is meant to be probing proves only that the copy agrees with itself,
    so there is deliberately no second copy.
    """
    expected = {hc.pair_key(h["key"], m["key"])
                for u in hy.UNITS
                for h in cands["humans"].get(u, [])
                for m in cands["machines"].get(u, [])}
    seen = [hc.pair_key(r["human_key"], r["machine_key"]) for r in rows]
    problems = []
    if len(seen) != len(set(seen)):
        dup = sorted({k for k in seen if seen.count(k) > 1})
        problems.append(f"duplicate pair keys: {dup[:5]}")
    if set(seen) != expected:
        problems.append(f"missing: {sorted(expected - set(seen))[:5]} / "
                        f"unexpected: {sorted(set(seen) - expected)[:5]}")
    for r in rows:
        if r["human_key"].split("::")[0] != r["machine_key"].split("::")[0]:
            problems.append(f"pair crosses units: {r['case_id']}")
    n_hist = sum(1 for r in rows if r["source_round"] == hc.SOURCE_ORIGINAL)
    n_comp = sum(1 for r in rows if r["source_round"] == hc.SOURCE_COMPLEMENT)
    if (n_hist, n_comp) != (61, 32):
        problems.append(f"expected 61 + 32, got {n_hist} + {n_comp}")
    if hist is not None:
        was = {x["case_id"]: x for x in hist}
        for r in rows:
            if r["source_round"] != hc.SOURCE_ORIGINAL:
                continue
            w = was.get(r["case_id"])
            if not w or w["status"] != r["status"] or w["category"] != r["category"]:
                problems.append(f"historical decision altered: {r['case_id']}")
    return problems


def theme_states(rows: list[dict], cands: dict):
    """Roll pair-level decisions up to theme level, over the complete universe."""
    humans = {h["key"] for v in cands["humans"].values() for h in v}
    machines = {m["key"] for v in cands["machines"].values() for m in v}
    by_h, by_m = {}, {}
    for r in rows:
        by_h.setdefault(r["human_key"], []).append(r)
        by_m.setdefault(r["machine_key"], []).append(r)

    hstate, mstate = {}, {}
    for k, rs in by_h.items():
        conf = [r["machine_key"] for r in rs if r["status"] == hy.HYBRID_CONFIRMED_MATCH]
        unres = [r["machine_key"] for r in rs if r["status"] == hy.HYBRID_UNRESOLVED]
        n_unit = sum(1 for m in machines if m.startswith(k.split("::")[0] + "::"))
        hstate[k] = {
            "unit": k.split("::")[0], "n_pairs_adjudicated": len(rs),
            "n_pairs_in_unit": n_unit, "local_universe_complete": len(rs) == n_unit,
            "confirmed_matches": sorted(conf), "unresolved_pairs": sorted(unres),
            "state": ("RECOVERED" if conf else
                      "UNRESOLVED_POSSIBLY_RECOVERED" if unres else
                      "CONFIRMED_NOT_RECOVERED" if len(rs) == n_unit else
                      "NOT_RECOVERED_BUT_UNIVERSE_INCOMPLETE")}
    for k, rs in by_m.items():
        conf = [r["human_key"] for r in rs if r["status"] == hy.HYBRID_CONFIRMED_MATCH]
        unres = [r["human_key"] for r in rs if r["status"] == hy.HYBRID_UNRESOLVED]
        n_unit = sum(1 for h in humans if h.startswith(k.split("::")[0] + "::"))
        mstate[k] = {
            "unit": k.split("::")[0], "n_pairs_adjudicated": len(rs),
            "n_pairs_in_unit": n_unit, "local_universe_complete": len(rs) == n_unit,
            "confirmed_matches": sorted(conf), "unresolved_pairs": sorted(unres),
            "state": ("MATCHED" if conf else
                      "UNRESOLVED_POSSIBLY_MATCHED" if unres else
                      "CONFIRMED_UNMATCHED")}
    return hstate, mstate


def build() -> dict:
    hist_res = _L("claude_round1_results.json")
    hist = r2.derive_round1()["rows"]
    hist_by_case = {}
    for r in hist_res["results"]:
        if r["status"] == "COMPLETE":
            hist_by_case.setdefault(r["case_id"], {})[r["repetition_index"]] = r["judgement"]

    rows = []
    for r in hist:
        reps = hist_by_case.get(r["case_id"], {})
        rows.append({**r, "source_round": hc.SOURCE_ORIGINAL,
                     "repetitions": {str(k): {"category": v["category"],
                                              "confidence": v["confidence"],
                                              "n_quotations": len(v.get("quotations") or [])}
                                     for k, v in sorted(reps.items())},
                     "evidence_verified": not any(
                         "literal" in x or "moderator" in x or "unknown turn" in x
                         for x in r["reasons"]),
                     "attempts": [{"repetition_index": k, "status": "COMPLETE",
                                   "attempt": 1} for k in sorted(reps)]})
    rows += derive_complement()

    # ---- integrity of the universe ---------------------------------------
    cands = _L("hybrid_candidates.json")
    problems = integrity_problems(rows, cands, hist)
    human_state, machine_state = theme_states(rows, cands)
    n_hist = sum(1 for r in rows if r["source_round"] == hc.SOURCE_ORIGINAL)
    n_comp = sum(1 for r in rows if r["source_round"] == hc.SOURCE_COMPLEMENT)

    for k, v in human_state.items():
        if v["state"] == "NOT_RECOVERED_BUT_UNIVERSE_INCOMPLETE":
            problems.append(f"{k}: called not-recovered on an incomplete local universe")

    out = {"n_pairs": len(rows), "n_historical": n_hist, "n_complement": n_comp,
           "integration_rule": hc.INTEGRATION_RULE,
           "problems": problems, "pass": not problems,
           "rows": rows, "human_state": human_state, "machine_state": machine_state}
    hy._atomic(_HY / "hybrid_universe.json", out)
    return out


def main() -> int:
    o = build()
    from collections import Counter
    print(f"pairs {o['n_pairs']} = {o['n_historical']} historical + "
          f"{o['n_complement']} complement")
    print("\nby source and status:")
    for src in (hc.SOURCE_ORIGINAL, hc.SOURCE_COMPLEMENT):
        c = Counter(r["status"] for r in o["rows"] if r["source_round"] == src)
        print(f"  {src}")
        for k, v in c.most_common():
            print(f"     {k:38s} {v}")
    print("\nhuman theme states:")
    for k, v in Counter(v["state"] for v in o["human_state"].values()).most_common():
        print(f"   {k:38s} {v}")
    print("machine theme states:")
    for k, v in Counter(v["state"] for v in o["machine_state"].values()).most_common():
        print(f"   {k:38s} {v}")
    print("\nPASS:", o["pass"])
    for p in o["problems"]:
        print("   PROBLEM:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
