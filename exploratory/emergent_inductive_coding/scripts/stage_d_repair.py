"""
TECHNICAL_TRUNCATION_REPAIR — resubmit only the six requests that hit max_tokens.

    py scripts/stage_d_repair.py --preflight
    py scripts/stage_d_repair.py --submit
    py scripts/stage_d_repair.py --status
    py scripts/stage_d_repair.py --retrieve
    py scripts/stage_d_repair.py --score

WHAT THIS IS
------------
A technical repair of a truncation, not a new adjudication and not a substitution of the
analysis. Six requests hit the 8192-token ceiling and returned unparseable output. The
cases, prompts, schema, frozen taxonomies, per-repetition orderings, model, execution
mode and effort are all identical. The ONLY changed parameter is max_output_tokens,
8192 -> 32768.

Q1 and Q4 are not resubmitted. Their four responses ended with end_turn and a complete
decision list, and are reused byte-identical from the original raw file.

The original job record and the original raw responses are preserved unmodified.
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
import stage_d_adjudication as sd    # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_D = sd._D
REPAIR_TAG = "TECHNICAL_TRUNCATION_REPAIR"
REPAIR_ATTEMPT = 1
OLD_MAX = 8192
NEW_MAX = 32768

REPAIR_QUESTIONS = (2, 3, 5)
REUSE_QUESTIONS = (1, 4)

_RJOB = _D / "stage_d_repair_job.json"
_RRAW = _D / "stage_d_repair_raw.json"
_RMANIFEST = _D / "stage_d_repair_manifest.json"


def reusable() -> dict:
    """The four complete originals, verified before anything is reused."""
    raw = json.loads(sd._RAW.read_text(encoding="utf-8"))
    man = json.loads(sd._MANIFEST.read_text(encoding="utf-8"))
    by_id = {r["custom_id"]: r for r in man["requests"]}
    out, problems = {}, []
    for resp in raw["responses"]:
        req = by_id[resp["custom_id"]]
        if req["question"] not in REUSE_QUESTIONS:
            continue
        if resp.get("stop_reason") != "end_turn":
            problems.append(f"{resp['custom_id']}: stop_reason "
                            f"{resp.get('stop_reason')}, not end_turn")
            continue
        dec = json.loads(resp["raw_text"])["decisions"]
        if len(dec) != req["n_cases"]:
            problems.append(f"{resp['custom_id']}: {len(dec)}/{req['n_cases']} decisions")
            continue
        out[resp["custom_id"]] = {"response": resp, "request": req,
                                  "n_decisions": len(dec)}
    if len(out) != 4:
        problems.append(f"{len(out)}/4 reusable responses")
    return {"responses": out, "problems": problems, "pass": not problems}


def build_manifest() -> tuple[dict, dict]:
    man = json.loads(sd._MANIFEST.read_text(encoding="utf-8"))
    taxes = json.loads((sd._B / "stage_b_canonical_taxonomies.json").read_text(
        encoding="utf-8"))["taxonomies"]
    cs = sd.cases()
    reuse = reusable()

    problems = list(reuse["problems"])
    reqs, bodies = [], {}
    for r in man["requests"]:
        q, rep = r["question"], r["repetition_index"]
        if q not in REPAIR_QUESTIONS:
            continue
        # identical rendering: same cases, same frozen taxonomy, same per-rep ordering
        body = sd.render(cs[q], taxes[str(q)]["clusters"], rep)
        if sb._sha(body) != r["rendered_sha256"]:
            problems.append(f"{r['custom_id']}: rendering differs from the original")
        bodies[(q, rep)] = body
        new_id = f"{r['custom_id']}_rep{REPAIR_ATTEMPT}_max{NEW_MAX}"
        reqs.append({
            "custom_id": new_id,
            "original_custom_id": r["custom_id"],
            "repair_attempt": REPAIR_ATTEMPT,
            "max_output_tokens": NEW_MAX,
            "question": q, "repetition_index": rep, "n_cases": r["n_cases"],
            "expected_raw_theme_ids": r["expected_raw_theme_ids"],
            "valid_cluster_ids": r["valid_cluster_ids"],
            "taxonomy_sha256": r["taxonomy_sha256"],
            "order_salt": r["order_salt"],
            "rendered_sha256": r["rendered_sha256"],
            "prompt_sha256": r["prompt_sha256"],
            "schema_sha256": r["schema_sha256"],
            "model": r["model"], "effort": r["effort"],
            "execution_mode": r["execution_mode"],
            "cache_key": sb._sha("|".join([
                REPAIR_TAG, r["custom_id"], str(REPAIR_ATTEMPT), str(NEW_MAX),
                r["taxonomy_sha256"], r["rendered_sha256"], r["prompt_sha256"],
                r["schema_sha256"], r["model"], r["effort"], r["execution_mode"]])),
            "prompt_words": r["prompt_words"]})

    # the only permitted difference
    changed = []
    for r in reqs:
        o = next(x for x in man["requests"] if x["custom_id"] == r["original_custom_id"])
        for k in ("prompt_sha256", "schema_sha256", "taxonomy_sha256",
                  "rendered_sha256", "order_salt", "model", "effort",
                  "execution_mode", "n_cases"):
            if r[k] != o[k]:
                changed.append(f"{r['custom_id']}: {k} changed")
        if o["expected_raw_theme_ids"] != r["expected_raw_theme_ids"]:
            changed.append(f"{r['custom_id']}: cases changed")
    problems += changed

    n_eval = sum(r["n_cases"] for r in reqs)
    if len(reqs) != 6:
        problems.append(f"{len(reqs)} requests, expected 6")
    if n_eval != 270:
        problems.append(f"{n_eval} evaluations, expected 270")
    if any(r["question"] in REUSE_QUESTIONS for r in reqs):
        problems.append("a Q1 or Q4 request is present and must not be")

    est_in = sum(round(r["prompt_words"] * 1.75 + 1600) for r in reqs)
    est_out = n_eval * 290          # measured 77,667 output over 135 completed evals
    cost = est_in / 1e6 * 2.5 + est_out / 1e6 * 12.5
    orig = json.loads(sd._RAW.read_text(encoding="utf-8"))["measured_usage"]
    spent = orig["input_tokens"] / 1e6 * 2.5 + orig["output_tokens"] / 1e6 * 12.5

    return {"built_utc": datetime.now(UTC).isoformat(),
            "record_type": REPAIR_TAG,
            "is_not": ["a new methodological adjudication",
                       "a substitution of the analysis"],
            "reason": ("six requests hit the 8192 max_output_tokens ceiling and returned "
                       "unparseable output; the ceiling was undersized for 41-52 "
                       "decisions with justifications"),
            "only_changed_parameter": {"max_output_tokens": [OLD_MAX, NEW_MAX]},
            "n_requests": len(reqs), "n_evaluations": n_eval,
            "repair_questions": list(REPAIR_QUESTIONS),
            "reused_questions": list(REUSE_QUESTIONS),
            "reused_responses": sorted(reuse["responses"]),
            "reused_byte_identical": True,
            "original_job_preserved": True,
            "original_raw_preserved": True,
            "estimated_input_tokens": est_in, "estimated_output_tokens": est_out,
            "repair_cost_usd": round(cost, 2),
            "already_spent_usd": round(spent, 2),
            "cost_note": "the repair cost is additional to the cost already consumed",
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def submit():
    man, bodies = build_manifest()
    if not man["pass"]:
        raise sb.StageBError("repair preflight failed: " + "; ".join(man["problems"]))
    if _RJOB.exists():
        raise sb.StageBError("repair job exists; creation is NOT idempotent")
    S1._atomic(_RMANIFEST, man)
    S1._load_env()
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    client = anthropic.Anthropic()
    reqs = [Request(custom_id=r["custom_id"],
                    params=MessageCreateParamsNonStreaming(
                        model=r["model"], max_tokens=NEW_MAX,
                        system=sd.SYSTEM_PROMPT,
                        messages=[{"role": "user",
                                   "content": bodies[(r["question"],
                                                      r["repetition_index"])]}],
                        output_config={"effort": r["effort"],
                                       "format": {"type": "json_schema",
                                                  "schema": sd.RESPONSE_SCHEMA}}))
            for r in man["requests"]]
    batch = client.messages.batches.create(requests=reqs)
    rec = {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
           "record_type": REPAIR_TAG, "state_at_creation": batch.processing_status,
           "n_requests": len(reqs), "n_evaluations": man["n_evaluations"],
           "max_output_tokens": NEW_MAX,
           "custom_ids": [r["custom_id"] for r in man["requests"]]}
    S1._atomic(_RJOB, rec)
    print("repair job:", rec["job_id"])


def status():
    rec = json.loads(_RJOB.read_text(encoding="utf-8"))
    S1._load_env()
    import anthropic
    b = anthropic.Anthropic().messages.batches.retrieve(rec["job_id"])
    print(rec["job_id"], b.processing_status, dict(b.request_counts))
    return b.processing_status


def retrieve():
    rec = json.loads(_RJOB.read_text(encoding="utf-8"))
    S1._load_env()
    import anthropic
    client = anthropic.Anthropic()
    b = client.messages.batches.retrieve(rec["job_id"])
    if b.processing_status != "ended":
        raise sb.StageBError(f"status {b.processing_status}")
    out, uin, uout = {}, 0, 0
    for res in client.messages.batches.results(rec["job_id"]):
        if res.custom_id not in rec["custom_ids"]:
            raise sb.StageBError(f"unknown custom_id {res.custom_id}")
        e = {"custom_id": res.custom_id, "result_type": res.result.type}
        if res.result.type == "succeeded":
            m = res.result.message
            uin += m.usage.input_tokens
            uout += m.usage.output_tokens
            e.update({"stop_reason": m.stop_reason,
                      "raw_text": next((bl.text for bl in m.content
                                        if bl.type == "text"), None)})
        out[res.custom_id] = e
    if missing := sorted(set(rec["custom_ids"]) - set(out)):
        raise sb.StageBError(f"missing: {missing}")
    S1._atomic(_RRAW, {"retrieved_utc": datetime.now(UTC).isoformat(),
                       "job_id": rec["job_id"], "record_type": REPAIR_TAG,
                       "matched_by": "custom_id", "n_results": len(out),
                       "measured_usage": {"input_tokens": uin, "output_tokens": uout},
                       "responses": [out[k] for k in sorted(out)]})
    print(f"retrieved {len(out)}")


def score():
    """Combine the six repaired with the four originals and apply the final gate."""
    rman = json.loads(_RMANIFEST.read_text(encoding="utf-8"))
    rraw = json.loads(_RRAW.read_text(encoding="utf-8"))
    oman = json.loads(sd._MANIFEST.read_text(encoding="utf-8"))
    reuse = reusable()
    if not reuse["pass"]:
        return {"gate_pass": False, "gate_problems": reuse["problems"]}

    by_new = {r["custom_id"]: r for r in rman["requests"]}
    parsed, quarantine, chunk_needed = {}, [], []

    for resp in rraw["responses"]:
        req = by_new[resp["custom_id"]]
        q, rep = req["question"], req["repetition_index"]
        problems = []
        if resp.get("result_type") != "succeeded":
            problems.append("not succeeded")
        elif resp.get("stop_reason") != "end_turn":
            problems.append(f"stop_reason {resp.get('stop_reason')}")
            chunk_needed.append({"custom_id": resp["custom_id"], "question": q,
                                 "repetition_index": rep, "n_cases": req["n_cases"]})
        j = None
        if not problems:
            try:
                j = json.loads(resp["raw_text"] or "")
            except Exception as e:                              # noqa: BLE001
                problems.append(f"invalid json: {e}")
        if j is not None:
            dec = j.get("decisions") or []
            expected = set(req["expected_raw_theme_ids"])
            got = [d.get("raw_theme_id") for d in dec]
            if len(dec) != req["n_cases"]:
                problems.append(f"{len(dec)}/{req['n_cases']} decisions")
            if dup := [i for i, n in Counter(got).items() if n > 1]:
                problems.append(f"{len(dup)} duplicated")
            if unk := sorted(set(got) - expected):
                problems.append(f"{len(unk)} unknown")
            if omi := sorted(expected - set(got)):
                problems.append(f"{len(omi)} omitted")
            valid = set(req["valid_cluster_ids"]) | {sd.UNCERTAIN}
            if bad := [d for d in dec if d.get("assigned_cluster_id") not in valid]:
                problems.append(f"{len(bad)} to a non-existent cluster")
        if problems:
            quarantine.append({"custom_id": resp["custom_id"], "question": q,
                               "repetition": rep, "problems": problems})
            continue
        parsed[(q, rep)] = {d["raw_theme_id"]: d for d in j["decisions"]}

    for cid, meta in reuse["responses"].items():
        req = meta["request"]
        dec = json.loads(meta["response"]["raw_text"])["decisions"]
        parsed[(req["question"], req["repetition_index"])] = {
            d["raw_theme_id"]: d for d in dec}

    gate = []
    if len(parsed) != 10:
        gate.append(f"{len(parsed)}/10 responses")
    counts = Counter()
    for (q, _r), dd in parsed.items():
        for rid in dd:
            counts[(q, rid)] += 1
    expected_pairs = {(r["question"], i) for r in oman["requests"]
                      for i in r["expected_raw_theme_ids"]}
    if len(counts) != 188:
        gate.append(f"{len(counts)}/188 themes")
    if wrong := {k for k, v in counts.items() if v != 2}:
        gate.append(f"{len(wrong)} themes without exactly two evaluations")
    if missing := expected_pairs - set(counts):
        gate.append(f"{len(missing)} themes with no evaluation")
    if quarantine:
        gate.append(f"{len(quarantine)} quarantined requests")
    n_eval = sum(counts.values())
    if n_eval != 376:
        gate.append(f"{n_eval}/376 evaluations")

    if gate:
        return {"gate_pass": False, "gate_problems": gate,
                "quarantine": quarantine,
                "chunking_required_for": chunk_needed}

    rows = []
    for (q, rid) in sorted(counts):
        d1, d2 = parsed[(q, 1)][rid], parsed[(q, 2)][rid]
        a1, a2 = d1["assigned_cluster_id"], d2["assigned_cluster_id"]
        if a1 == a2 and a1 != sd.UNCERTAIN:
            res, final = sd.CONSENSUS, a1
        else:
            res, final = sd.UNRESOLVED, None
        rows.append({"question": q, "raw_theme_id": rid,
                     "rep1_cluster": a1, "rep2_cluster": a2,
                     "resolution": res, "final_cluster_id": final,
                     "rep1_justification": d1["justification"],
                     "rep2_justification": d2["justification"]})

    per_q = defaultdict(Counter)
    for r in rows:
        per_q[r["question"]][r["resolution"]] += 1
    orig_usage = json.loads(sd._RAW.read_text(encoding="utf-8"))["measured_usage"]
    return {"scored_utc": datetime.now(UTC).isoformat(),
            "stage": sd.STAGE, "repair": REPAIR_TAG,
            "gate_pass": True, "gate_problems": [],
            "n_requests_total": 10, "n_requests_repaired": 6,
            "n_requests_reused": 4, "n_evaluations": n_eval, "n_cases": len(rows),
            "resolution_counts": dict(Counter(r["resolution"] for r in rows)),
            "per_question": {str(q): dict(v) for q, v in sorted(per_q.items())},
            "tie_breaking_by_confidence_or_mode": False,
            "cross_model_consensus_is_not_human_validation": True,
            "quarantine": [],
            "usage_original_batch": orig_usage,
            "usage_repair_batch": rraw["measured_usage"],
            "rows": rows}


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        man, _ = build_manifest()
        S1._atomic(_RMANIFEST, man)
        print(f"=== {REPAIR_TAG} PREFLIGHT ===")
        print(f"  solicitudes        {man['n_requests']}  (Q{man['repair_questions']})")
        print(f"  evaluaciones       {man['n_evaluations']}")
        print(f"  reutilizadas       {man['n_requests'] and len(man['reused_responses'])}"
              f"  {man['reused_responses']}")
        print(f"  ninguna de Q1/Q4 reenviada: "
              f"{not any(r['question'] in REUSE_QUESTIONS for r in man['requests'])}")
        print(f"  único parámetro cambiado: {man['only_changed_parameter']}")
        print(f"  tokens estimados   in {man['estimated_input_tokens']:,}  "
              f"out {man['estimated_output_tokens']:,}")
        print(f"  coste reparación   ${man['repair_cost_usd']}   "
              f"ya consumido ${man['already_spent_usd']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    if "--submit" in a:
        submit()
    elif "--status" in a:
        status()
    elif "--retrieve" in a:
        retrieve()
    elif "--score" in a:
        s = score()
        if not s["gate_pass"]:
            print("GATE FAILURE:", s["gate_problems"])
            if s.get("chunking_required_for"):
                print("  chunking required for:", s["chunking_required_for"])
            return 2
        S1._atomic(_D / "stage_d_adjudication.json",
                   {k: v for k, v in s.items() if k != "rows"})
        with (_D / "stage_d_decisions_long.csv").open("w", encoding="utf-8",
                                                      newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(s["rows"][0]))
            w.writeheader()
            w.writerows(s["rows"])
        print(f"gate PASS  solicitudes {s['n_requests_total']} "
              f"({s['n_requests_repaired']} reparadas + {s['n_requests_reused']} "
              f"reutilizadas)  evaluaciones {s['n_evaluations']}")
        print("  ", s["resolution_counts"])
        for q, v in s["per_question"].items():
            print(f"    Q{q}: {v}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
