"""
Hardened Stage C scorer.

    py scripts/stage_c_score.py

Reads the submitted manifest and the retrieved responses WITHOUT modifying either. The
job is never resubmitted or replaced.

THREE THINGS THIS ADDS OVER THE FIRST SCORER
--------------------------------------------
1. The frozen taxonomy is re-derived from the clusters themselves and must equal both
   the hash Stage B froze and the hash each Stage C request recorded. A taxonomy that
   drifted between freezing and assignment would make every stability figure meaningless
   while looking perfectly well-formed.

2. A completeness gate blocks all output and every later stage unless the corpus is
   whole. A quarantined call may be documented, but it must never leave a partial corpus
   that later stages silently treat as complete.

3. STABLE is split, because "the two repetitions agreed" and "the two repetitions agreed
   with Stage B" are different facts and only the second supports leaving Stage B alone.

No modal assignment is chosen here and Stage B is not overwritten. Similarity, embeddings
and nearest neighbour are used nowhere.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import stage_b_taxonomy as sb        # noqa: E402
import stage_c_stability as sc       # noqa: E402

_B = sb._B
_C = sc._C
UNCERTAIN = "UNCERTAIN"

STABLE_SAME = "STABLE_SAME_AS_STAGE_B"
STABLE_DIFF = "STABLE_DIFFERENT_FROM_STAGE_B"
UNSTABLE = "UNSTABLE"
UNRESOLVED = "UNRESOLVED"

EXPECTED_THEMES = 526
EXPECTED_CALLS = 10
EXPECTED_QUESTIONS = 5
EXPECTED_REPS = 2


class GateFailure(RuntimeError):
    pass


# ------------------------------------------------------------ taxonomy hash
def verify_taxonomy_hashes(taxes: dict, requests: list) -> dict:
    """
    Re-derive each taxonomy hash from its clusters and require equality with BOTH the
    frozen value and the value each Stage C request carried.
    """
    rows, problems = [], []
    by_q = defaultdict(list)
    for r in requests:
        by_q[str(r["question"])].append(r)

    for q, tax in sorted(taxes.items()):
        recomputed = sb._sha(json.dumps({"clusters": tax["clusters"]},
                                        sort_keys=True, ensure_ascii=False))
        frozen = tax["taxonomy_sha256"]
        req_hashes = sorted({r["taxonomy_sha256"] for r in by_q[q]})
        ok_frozen = recomputed == frozen
        ok_requests = req_hashes == [frozen]
        if not ok_frozen:
            problems.append(f"Q{q}: recomputed taxonomy hash != frozen hash")
        if not ok_requests:
            problems.append(f"Q{q}: Stage C requests carry {req_hashes} != {frozen}")
        rows.append({"question": q, "recomputed": recomputed, "frozen": frozen,
                     "in_stage_c_requests": req_hashes,
                     "matches_frozen": ok_frozen,
                     "matches_requests": ok_requests,
                     "n_clusters": len(tax["clusters"])})
    return {"rows": rows, "problems": problems, "pass": not problems}


# -------------------------------------------------------- completeness gate
def completeness_gate(parsed: dict, quarantine: list, requests: list) -> dict:
    """
    Blocks output unless the corpus is whole. A partial corpus is never emitted.
    `parsed` maps (question, repetition) -> {raw_theme_id: cluster_id}.
    """
    problems = []
    n_valid = len(parsed)
    if n_valid != EXPECTED_CALLS:
        problems.append(f"{n_valid}/{EXPECTED_CALLS} valid responses")

    reps_by_q = defaultdict(set)
    for (q, rep) in parsed:
        reps_by_q[q].add(rep)
    for q in sorted({r["question"] for r in requests}):
        got = sorted(reps_by_q.get(q, ()))
        if got != [1, 2]:
            problems.append(f"Q{q}: repetitions {got}, expected [1, 2]")
    if len(reps_by_q) != EXPECTED_QUESTIONS:
        problems.append(f"{len(reps_by_q)}/{EXPECTED_QUESTIONS} questions complete")

    expected_ids = {(r["question"], i) for r in requests
                    for i in r["expected_raw_theme_ids"]}
    if len({i for _, i in expected_ids}) != EXPECTED_THEMES:
        problems.append(f"{len({i for _, i in expected_ids})} unique expected ids")

    counts = Counter()
    unknown = set()
    for (q, _rep), asg in parsed.items():
        for rid in asg:
            if (q, rid) not in expected_ids:
                unknown.add((q, rid))
            counts[(q, rid)] += 1
    if unknown:
        problems.append(f"{len(unknown)} unknown raw_theme_id")

    wrong = {k: v for k, v in counts.items() if v != EXPECTED_REPS}
    omitted = expected_ids - set(counts)
    if omitted:
        problems.append(f"{len(omitted)} raw_theme_id with no assignment")
    if wrong:
        problems.append(f"{len(wrong)} raw_theme_id without exactly "
                        f"{EXPECTED_REPS} assignments")
    if len(counts) != EXPECTED_THEMES:
        problems.append(f"{len(counts)} raw_theme_id covered, "
                        f"expected {EXPECTED_THEMES}")

    return {"n_valid_responses": n_valid,
            "questions_complete": len(reps_by_q),
            "n_raw_theme_ids_covered": len(counts),
            "n_with_exactly_two_assignments": sum(1 for v in counts.values()
                                                  if v == EXPECTED_REPS),
            "n_unknown": len(unknown), "n_omitted": len(omitted),
            "n_quarantined_calls": len(quarantine),
            "quarantine": quarantine,
            "problems": problems, "pass": not problems,
            "rule": ("a quarantined call may be documented, but it must never leave a "
                     "partial corpus that a later stage treats as complete")}


# ------------------------------------------------------------------ scoring
def classify(rep1: str | None, rep2: str | None, stage_b: str | None) -> str:
    if rep1 is None or rep2 is None:
        return UNRESOLVED
    if rep1 != rep2:
        return UNSTABLE
    if rep1 == UNCERTAIN:
        return UNRESOLVED
    return STABLE_SAME if rep1 == stage_b else STABLE_DIFF


def score() -> dict:
    man = json.loads(sc._MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(sc._RAW.read_text(encoding="utf-8"))
    bfile = json.loads((_B / "stage_b_canonical_taxonomies.json").read_text(
        encoding="utf-8"))
    taxes = bfile["taxonomies"]

    tax_check = verify_taxonomy_hashes(taxes, man["requests"])
    if not tax_check["pass"]:
        raise GateFailure("taxonomy hash mismatch: " + "; ".join(tax_check["problems"]))

    b_asg = {}
    for row in csv.DictReader((_B / "stage_b_assignments_long.csv").open(
            encoding="utf-8")):
        b_asg[(int(row["question"]), row["raw_theme_id"])] = row["cluster_id"]

    by_key = {r["custom_request_key"]: r for r in man["requests"]}
    parsed, quarantine = {}, []
    for resp in raw["responses"]:
        req = by_key[resp["custom_request_key"]]
        q, rep = req["question"], req["repetition_index"]
        problems = []
        if "STOP" not in (resp["finish_reason"] or "").upper():
            problems.append(f"finish_reason {resp['finish_reason']}")
        try:
            j = json.loads(resp["raw_text"] or "")
        except Exception as e:                                   # noqa: BLE001
            quarantine.append({"question": q, "repetition": rep,
                               "problems": [f"invalid json: {e}"]})
            continue
        asg = j.get("assignments") or []
        expected = set(req["expected_raw_theme_ids"])
        got = [a.get("raw_theme_id") for a in asg]
        if dup := [i for i, n in Counter(got).items() if n > 1]:
            problems.append(f"{len(dup)} duplicated raw_theme_id")
        if unk := sorted(set(got) - expected):
            problems.append(f"{len(unk)} unknown raw_theme_id")
        if omi := sorted(expected - set(got)):
            problems.append(f"{len(omi)} omitted raw_theme_id")
        valid = set(req["valid_cluster_ids"]) | {UNCERTAIN}
        if bad := [a for a in asg if a.get("cluster_id") not in valid]:
            problems.append(f"{len(bad)} assignments to a non-existent cluster")
        if problems:
            quarantine.append({"question": q, "repetition": rep,
                               "problems": problems})
            continue
        parsed[(q, rep)] = {a["raw_theme_id"]: a["cluster_id"] for a in asg}

    gate = completeness_gate(parsed, quarantine, man["requests"])
    if not gate["pass"]:
        raise GateFailure("completeness gate failed: " + "; ".join(gate["problems"]))

    rows = []
    for r in man["requests"]:
        if r["repetition_index"] != 1:
            continue
        q = r["question"]
        for rid in r["expected_raw_theme_ids"]:
            c1 = parsed[(q, 1)].get(rid)
            c2 = parsed[(q, 2)].get(rid)
            b0 = b_asg.get((q, rid))
            rows.append({
                "question": q, "raw_theme_id": rid,
                "stage_b_cluster": b0, "rep1_cluster": c1, "rep2_cluster": c2,
                "status": classify(c1, c2, b0),
                "reps_agree": c1 == c2,
                "both_reps_agree_with_stage_b": bool(c1 == c2 == b0),
                "stage_b_was_uncertain": b0 == UNCERTAIN,
                "resolves_a_stage_b_uncertain": bool(
                    b0 == UNCERTAIN and c1 == c2 and c1 != UNCERTAIN),
                "new_uncertain": bool(b0 != UNCERTAIN and c1 == c2 == UNCERTAIN),
            })

    def summarise(rs):
        n = len(rs)
        st = Counter(r["status"] for r in rs)
        return {
            "n_themes": n,
            "reps_agree": sum(1 for r in rs if r["reps_agree"]),
            "reps_agree_rate": round(sum(1 for r in rs if r["reps_agree"]) / n, 4),
            "both_reps_agree_with_stage_b": sum(
                1 for r in rs if r["both_reps_agree_with_stage_b"]),
            "resolves_a_stage_b_uncertain": sum(
                1 for r in rs if r["resolves_a_stage_b_uncertain"]),
            "new_uncertain": sum(1 for r in rs if r["new_uncertain"]),
            STABLE_SAME: st[STABLE_SAME], STABLE_DIFF: st[STABLE_DIFF],
            UNSTABLE: st[UNSTABLE], UNRESOLVED: st[UNRESOLVED]}

    per_q = {str(q): summarise([r for r in rows if r["question"] == q])
             for q in sb.QUESTIONS}

    # Stage D covers everything the two repetitions did not settle in agreement with
    # Stage B. Deduplicated so one call never covers the same theme twice.
    d_cases = [r for r in rows if r["status"] in (UNSTABLE, UNRESOLVED, STABLE_DIFF)]
    d_ids = sorted({(r["question"], r["raw_theme_id"]) for r in d_cases})

    return {
        "scored_utc": datetime.now(UTC).isoformat(),
        "stage": "C_ASSIGNMENT_STABILITY",
        "scorer": "HARDENED_V2",
        "taxonomy_hash_verification": tax_check,
        "completeness_gate": gate,
        "final_assignment_chosen_here": False,
        "stage_b_overwritten": False,
        "modal_assignment_used": False,
        "similarity_used_for_decisions": False,
        "total": summarise(rows),
        "per_question": per_q,
        "stage_d_input": {
            "n_cases": len(d_ids),
            "deduplicated": True,
            "covers": [UNSTABLE, UNRESOLVED, STABLE_DIFF],
            "by_status": dict(Counter(r["status"] for r in d_cases)),
            "cases": [{"question": q, "raw_theme_id": i} for q, i in d_ids]},
        "measured_usage": raw["measured_usage"],
        "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED",
        "rows": rows,
    }


def main() -> int:
    try:
        s = score()
    except GateFailure as e:
        print("GATE FAILURE — no output written, no later stage may run")
        print(" ", e)
        return 2
    sb._atomic(_C / "stage_c_stability.json",
               {k: v for k, v in s.items() if k != "rows"})
    with (_C / "stage_c_stability_long.csv").open("w", encoding="utf-8",
                                                  newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(s["rows"][0]))
        w.writeheader()
        w.writerows(s["rows"])

    t = s["total"]
    print("=== STAGE C (scorer endurecido) ===")
    print(f"  hashes de taxonomía verificados: "
          f"{s['taxonomy_hash_verification']['pass']}")
    print(f"  completeness gate: {s['completeness_gate']['pass']}  "
          f"({s['completeness_gate']['n_raw_theme_ids_covered']} temas, "
          f"{s['completeness_gate']['n_with_exactly_two_assignments']} con 2 "
          f"asignaciones)")
    print(f"\n  acuerdo entre repeticiones {t['reps_agree']}/{t['n_themes']} "
          f"({t['reps_agree_rate']:.1%})")
    print(f"  ambas coinciden con Stage B  {t['both_reps_agree_with_stage_b']}")
    print(f"  resuelven un UNCERTAIN de B  {t['resolves_a_stage_b_uncertain']}")
    print(f"  nuevos UNCERTAIN             {t['new_uncertain']}")
    for k in (STABLE_SAME, STABLE_DIFF, UNSTABLE, UNRESOLVED):
        print(f"  {k:32s} {t[k]}")
    print("\n  por pregunta:")
    for q, v in s["per_question"].items():
        print(f"    Q{q}: same {v[STABLE_SAME]:3d}  diff {v[STABLE_DIFF]:3d}  "
              f"unstable {v[UNSTABLE]:3d}  unresolved {v[UNRESOLVED]:3d}  "
              f"acuerdo {v['reps_agree_rate']:.1%}")
    d = s["stage_d_input"]
    print(f"\n  entrada para Stage D: {d['n_cases']} casos deduplicados {d['by_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
