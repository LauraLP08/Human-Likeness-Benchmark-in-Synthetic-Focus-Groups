"""
Corrective completion of the S01-S06 correspondence space.

The original check audited 61 of the 93 within-unit human x machine pairs. The other 32
were dropped by a similarity screener that was only ever entitled to PROPOSE pairs, and
were then treated in the metrics as though they had been adjudicated. They had not been.
This module audits them, so that every statement about a human theme being unrecovered
rests on its complete local universe.

    py scripts/hybrid_complement.py --manifest      # build + prove the 32, no API
    py scripts/hybrid_complement.py --submit
    py scripts/hybrid_complement.py --status
    py scripts/hybrid_complement.py --retrieve
    py scripts/hybrid_complement.py --retry-missing  # ONE technical retry, see policy
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy      # noqa: E402
import hybrid_claude_audit as au          # noqa: E402
import cross_model_audit_q3 as cm         # noqa: E402

_HY = hy._HY
SOURCE_ORIGINAL = "ORIGINAL_SCREENED_61"
SOURCE_COMPLEMENT = "COMPLEMENT_32"

# ---------------------------------------------------------------------------
# Frozen before submission. This is an operational correction to a contingency the
# original protocol left unspecified; it is NOT part of the original protocol and is
# recorded as such in PROTOCOL_DEVIATIONS.md.
RETRY_POLICY = {
    "id": "COMPLEMENT_RETRY_POLICY_V1",
    "frozen_before_submission": True,
    "not_part_of_original_protocol": True,
    "max_technical_retries_per_request": 1,
    "retry_allowed_only_when": (
        "the request produced NO usable substantive response: an API-level error, an "
        "absent result, invalid JSON, or output truncated at max_tokens"),
    "never_retry": [
        "a disagreement between the two repetitions",
        "LOW confidence",
        "an invalid or non-literal quotation",
        "a category the analyst finds unfavourable",
        "any result that is substantively usable but inconvenient",
    ],
    "on_retry_failure": "the pair remains HYBRID_UNRESOLVED",
    "no_retry_until_agreement": (
        "retrying until the repetitions agree would manufacture agreement; the retry "
        "is permitted only to recover from transport failure, never to resample a "
        "judgement"),
    "reporting": "every attempt and its reason is recorded in claude_complement_results.json",
}

INTEGRATION_RULE = {
    "id": "COMPLEMENT_INTEGRATION_V1",
    "universe": "exactly 93 within-unit pairs = 61 ORIGINAL_SCREENED_61 + 32 COMPLEMENT_32",
    "historical_decisions": "never overwritten, never re-interpreted, never re-run",
    "gates": "identical to the original: two repetitions, agreeing, non-LOW, literal evidence",
    "confirmed_not_recovered": (
        "a human theme may be called confirmed-not-recovered only when EVERY machine "
        "theme in its unit has been adjudicated against it and every one of those pairs "
        "is a confirmed non-correspondence"),
    "unresolved_is_not_absence": (
        "a human theme with no confirmed match but >=1 unresolved pair sits inside the "
        "recall band, never below it"),
}


def _L(n):
    return json.loads((_HY / n).read_text(encoding="utf-8"))


def pair_key(hk: str, mk: str) -> str:
    return f"{hk}||{mk}"


def case_id(hk: str, mk: str) -> str:
    return f"P::{hk}::{mk}"


# --------------------------------------------------------------------- manifest
def build_manifest() -> dict:
    c = _L("hybrid_candidates.json")
    humans = {u: [h["key"] for h in v] for u, v in c["humans"].items()}
    machines = {u: [m["key"] for m in v] for u, v in c["machines"].items()}

    cartesian, per_unit = [], {}
    for u in hy.UNITS:
        hs, ms = humans.get(u, []), machines.get(u, [])
        pu = [(h, m) for h in hs for m in ms]
        per_unit[u] = {"n_human": len(hs), "n_machine": len(ms), "n_pairs": len(pu)}
        cartesian += pu
    cart = {pair_key(h, m) for h, m in cartesian}

    audited = {pair_key(x["human_key"], x["machine_key"]) for x in c["cases"]}
    complement = cart - audited

    problems = []
    if len(cart) != len(cartesian):
        problems.append(f"duplicate pairs in the cartesian: {len(cartesian)} vs {len(cart)}")
    if not audited <= cart:
        problems.append(f"audited pairs outside the cartesian: {sorted(audited - cart)[:5]}")
    if len(audited) != 61:
        problems.append(f"expected 61 historical pairs, found {len(audited)}")
    if len(cart) != 93:
        problems.append(f"expected 93 cartesian pairs, found {len(cart)}")
    if len(complement) != 32:
        problems.append(f"expected 32 complement pairs, found {len(complement)}")
    if audited | complement != cart:
        problems.append("61 + 32 does not reconstitute the cartesian")
    if audited & complement:
        problems.append(f"overlap between historical and complement: {len(audited & complement)}")

    # every pair must live inside exactly one unit
    for pk in sorted(cart):
        hk, mk = pk.split("||")
        if hk.split("::")[0] != mk.split("::")[0]:
            problems.append(f"pair crosses units: {pk}")

    # independent cross-check: the screener's own rejection list must BE the complement
    rej = {pair_key(r["human_key"], r["machine_key"]) for r in c["rejected_pairs"]}
    if rej != complement:
        problems.append(
            f"screener rejection list != complement (only in rejects: "
            f"{sorted(rej - complement)[:3]}; only in complement: "
            f"{sorted(complement - rej)[:3]})")

    sims = {pair_key(r["human_key"], r["machine_key"]): r["similarity"]
            for r in c["rejected_pairs"]}
    pairs = []
    for pk in sorted(complement):
        hk, mk = pk.split("||")
        u = hk.split("::")[0]
        pairs.append({"pair_key": pk, "case_id": case_id(hk, mk),
                      "blind_unit_id": u, "question_id": hy.QUESTION_OF[u],
                      "human_key": hk, "machine_key": mk,
                      "source_round": SOURCE_COMPLEMENT,
                      "screener_similarity_FOR_RECORD_ONLY": sims.get(pk),
                      "excluded_originally_because":
                          "not top-K for either side and below the similarity floor"})

    man = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "classification": hy.CLASSIFICATION,
        "purpose": (
            "audit the 32 within-unit pairs the similarity screener excluded, so that "
            "the correspondence space is complete at 93/93 and no human theme is called "
            "unrecovered on the strength of an unjudged pair"),
        "why_this_was_necessary": (
            "coverage of both SIDES (every human theme and every machine theme appearing "
            "in at least one pair) was mistaken for coverage of all possible "
            "correspondences. It is not the same property. The screener proposes; only "
            "the adjudicator decides; 32 pairs were never put to the adjudicator."),
        "no_similarity_exclusion": (
            "similarity is recorded for the record only and excludes nothing here. All "
            "32 remaining pairs are audited regardless of score."),
        "arithmetic": {
            "n_human_themes": sum(len(v) for v in humans.values()),
            "n_machine_themes": sum(len(v) for v in machines.values()),
            "n_cartesian_within_unit": len(cart),
            "n_historical_audited": len(audited),
            "n_complement": len(complement),
            "reconstitutes_cartesian": audited | complement == cart,
            "duplicates": 0 if len(cart) == len(cartesian) else len(cartesian) - len(cart),
            "per_unit": per_unit},
        "historical_pairs_read_only": {
            "n": len(audited),
            "source_round": SOURCE_ORIGINAL,
            "policy": "never re-run, never overwritten, never re-interpreted",
            "sha256_of_sorted_pair_keys": hashlib.sha256(
                "\n".join(sorted(audited)).encode()).hexdigest(),
            "claude_round1_results_sha256": hashlib.sha256(
                (_HY / "claude_round1_results.json").read_bytes()).hexdigest(),
            "claude_round2_results_sha256": hashlib.sha256(
                (_HY / "claude_round2_results.json").read_bytes()).hexdigest()},
        "audit_configuration": {
            "model": hy.AUDITOR_MODEL, "execution_mode": "batch",
            "effort": hy.AUDITOR_EFFORT,
            "max_output_tokens": hy.AUDITOR_MAX_OUTPUT_TOKENS,
            "task": "A_PAIRWISE_CORRESPONDENCE",
            "structured_output": True,
            "repetitions_per_pair": 2,
            "n_requests_expected": len(complement) * 2,
            "prompt_sha256": cm.prompt_sha("A_PAIRWISE_CORRESPONDENCE"),
            "schema_sha256": cm.schema_sha("A_PAIRWISE_CORRESPONDENCE"),
            "categories": list(cm.TASKS["A_PAIRWISE_CORRESPONDENCE"]),
            "accepted_as_correspondence": list(hy.CORRESPONDENCE_ACCEPTED),
            "rejected_as_correspondence": list(hy.CORRESPONDENCE_REJECTED),
            "blinding": ("identical REFERENCE/CANDIDATE rendering; the auditor is shown "
                         "no prior result, no metric, no classification, no Q3, no "
                         "experimental condition, and no human/model provenance"),
            "order_policy": "block and evidence order reversed in repetition 1",
            "cache_key": ("sha256 over classification | task | pair case_id | "
                          "repetition_index | rendered text sha | prompt sha | schema "
                          "sha | model | effort | mode")},
        "retry_policy": RETRY_POLICY,
        "integration_rule": INTEGRATION_RULE,
        "problems": problems,
        "pass": not problems,
        "pairs": pairs,
    }
    hy._atomic(_HY / "hybrid_complement_manifest.json", man)
    return man


# ----------------------------------------------------------------------- cases
def cases_from_manifest() -> list[dict]:
    man = _L("hybrid_complement_manifest.json")
    if not man["pass"]:
        raise RuntimeError(f"manifest did not pass: {man['problems']}")
    c = _L("hybrid_candidates.json")
    H = {h["key"]: h for v in c["humans"].values() for h in v}
    M = {m["key"]: m for v in c["machines"].values() for m in v}
    out = []
    for p in man["pairs"]:
        h, m = H[p["human_key"]], M[p["machine_key"]]
        out.append({"case_id": p["case_id"], "task": "A_PAIRWISE_CORRESPONDENCE",
                    "blind_unit_id": p["blind_unit_id"],
                    "question_id": p["question_id"],
                    "reference": {"label": h["label"], "description": h["description"],
                                  "quote": h["quote"]},
                    "candidate": {"label": m["label"], "description": m["description"],
                                  "evidence": m["evidence"]},
                    "provenance": {"human_key": h["key"], "machine_key": m["key"],
                                   "source_round": SOURCE_COMPLEMENT}})
    return out


# ------------------------------------------------------------------- retry
RETRYABLE = {"NO_OUTPUT", "INVALID_JSON", "OUTPUT_TRUNCATED", "INVALID"}


def retry_missing(res_path: Path, job_path: Path) -> dict:
    """
    The single technical retry permitted by COMPLEMENT_RETRY_POLICY_V1.

    Only requests with no usable substantive response are eligible. A disagreement, a LOW
    confidence, an invalid quotation or an unwelcome category is a RESULT, not a failure,
    and is never resent — resampling a judgement until it converges manufactures the
    agreement the gate is supposed to detect.
    """
    o = json.loads(res_path.read_text(encoding="utf-8"))
    rec = json.loads(job_path.read_text(encoding="utf-8"))
    todo = [r for r in o["results"]
            if r["status"] in RETRYABLE and r.get("attempt", 1) < 2]
    if not todo:
        print("nothing eligible for a technical retry")
        return o
    cases = {c["case_id"]: c for c in rec["cases"]}
    au._load_env()
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    client = anthropic.Anthropic()

    reqs, id_map = [], {}
    for n, r in enumerate(todo, start=1):
        c = cases[r["case_id"]]
        rep = r["repetition_index"]
        text = au.render(c, rep)
        probs = au.render_problems(c, rep)
        if probs:
            raise au.AuditError(f"{c['case_id']} rep{rep}: {probs}")
        cid = f"rt{n:03d}"
        id_map[cid] = {**{k: r[k] for k in ("case_id", "task", "repetition_index",
                                            "blind_unit_id", "question_id",
                                            "provenance", "cache_key")},
                       "attempt": 2, "retry_reason": r["status"]}
        reqs.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(
            model=hy.AUDITOR_MODEL, max_tokens=hy.AUDITOR_MAX_OUTPUT_TOKENS,
            system=cm.prompt_for(c["task"]),
            messages=[{"role": "user", "content": text}],
            output_config={"effort": hy.AUDITOR_EFFORT,
                           "format": {"type": "json_schema",
                                      "schema": cm.task_schema(c["task"])}})))
    print(f"retrying {len(reqs)} request(s) with no usable response: "
          f"{[(r['case_id'], r['repetition_index'], r['status']) for r in todo]}")
    batch = client.messages.batches.create(requests=reqs)
    rj = _HY / "claude_complement_retry_job.json"
    hy._atomic(rj, {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
                    "n_requests": len(reqs), "custom_id_map": id_map,
                    "policy": RETRY_POLICY["id"],
                    "cases": [cases[r["case_id"]] for r in todo]})
    print("  retry job id:", batch.id)
    return {"retry_job": batch.id, "n": len(reqs)}


def merge_retry(res_path: Path) -> dict:
    """Fold the retry outcomes back in, keeping the original attempt on the record."""
    rj = _HY / "claude_complement_retry_job.json"
    out = au._retrieve(rj, _HY / "claude_complement_retry_results.json")
    o = json.loads(res_path.read_text(encoding="utf-8"))
    got = {(r["case_id"], r["repetition_index"]): r for r in out["results"]}
    merged, replaced = [], 0
    for r in o["results"]:
        k = (r["case_id"], r["repetition_index"])
        if k in got:
            merged.append({**r, "attempt_1_status": r["status"], **got[k],
                           "attempt": 2, "retry_reason": r["status"]})
            replaced += 1
        else:
            merged.append({**r, "attempt": r.get("attempt", 1)})
    o["results"] = merged
    o["retry"] = {"policy": RETRY_POLICY["id"], "job_id": out["job_id"],
                  "n_retried": replaced,
                  "n_recovered": sum(1 for r in merged
                                     if r.get("attempt") == 2 and r["status"] == "COMPLETE")}
    o["n_complete"] = sum(1 for r in merged if r["status"] == "COMPLETE")
    for k in ("input_tokens", "output_tokens"):
        o["total_usage"][k] += out["total_usage"][k]
    hy._atomic(res_path, o)
    return o


def main() -> int:
    a = sys.argv[1:]
    job = _HY / "claude_complement_job.json"
    res = _HY / "claude_complement_results.json"
    if "--manifest" in a:
        m = build_manifest()
        q = m["arithmetic"]
        print(f"human themes          : {q['n_human_themes']}")
        print(f"machine themes        : {q['n_machine_themes']}")
        print(f"cartesian within unit : {q['n_cartesian_within_unit']}")
        print(f"historical audited    : {q['n_historical_audited']}")
        print(f"complement to audit   : {q['n_complement']}")
        print(f"61 + 32 == cartesian  : {q['reconstitutes_cartesian']}")
        print(f"duplicate pairs       : {q['duplicates']}")
        print("\nper unit:")
        for u, v in q["per_unit"].items():
            print(f"   {u}  {v['n_human']} x {v['n_machine']} = {v['n_pairs']:>3d}")
        print(f"\nrequests to send      : {m['audit_configuration']['n_requests_expected']}")
        print(f"PASS                  : {m['pass']}")
        for p in m["problems"]:
            print("   PROBLEM:", p)
    elif "--submit" in a:
        au._submit(cases_from_manifest(), job, "complement (32 pairs x 2)")
    elif "--status" in a:
        rec = json.loads(job.read_text(encoding="utf-8"))
        au._load_env()
        import anthropic
        client = anthropic.Anthropic()
        b = client.messages.batches.retrieve(rec["job_id"])
        print(f"  job   : {rec['job_id']}")
        print(f"  status: {b.processing_status}")
        print(f"  counts: {b.request_counts}")
    elif "--retrieve" in a:
        o = au._retrieve(job, res)
        print(f"results {o['n_results']}  complete {o['n_complete']}  "
              f"usage {o['total_usage']}")
        bad = [(r["case_id"], r["repetition_index"], r["status"])
               for r in o["results"] if r["status"] != "COMPLETE"]
        print("needing a technical retry:", bad or "none")
    elif "--retry-missing" in a:
        retry_missing(res, job)
    elif "--merge-retry" in a:
        o = merge_retry(res)
        print("retry:", o["retry"])
        print(f"complete now {o['n_complete']}/{o['n_results']}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
