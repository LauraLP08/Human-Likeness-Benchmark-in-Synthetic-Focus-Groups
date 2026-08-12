"""
Phase 4 — blinded Claude audit over the hybrid candidate cases, two repetitions each.

Round 1 : correspondence (task A) over every candidate pair.
Round 2 : machine-only status (task C) and granularity (task D), built from round 1.

Same rubrics, schemas, blinding and gates as the Q3 cross-model audit.

    py scripts/hybrid_claude_audit.py --round1-submit | --status | --round1-retrieve
    py scripts/hybrid_claude_audit.py --round2-submit | --round2-retrieve
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy   # noqa: E402
import cross_model_audit_q3 as cm      # noqa: E402

_HY = hy._HY


class AuditError(RuntimeError):
    pass


def _load_env():
    p = _ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _cands():
    return json.loads((_HY / "hybrid_candidates.json").read_text(encoding="utf-8"))


def cache_key(task, case_id, rep, rendered_sha) -> str:
    blob = "|".join([hy.CLASSIFICATION, task, case_id, str(rep), rendered_sha,
                     cm.prompt_sha(task), cm.schema_sha(task), hy.AUDITOR_MODEL,
                     hy.AUDITOR_EFFORT, "batch"])
    return hashlib.sha256(blob.encode()).hexdigest()


def _block(title, label, desc, quotes, rep):
    out = [title, f"  label       : {label}", f"  description : {desc}",
           "  evidence    :"]
    ev = list(quotes)
    if rep % 2 == 1:
        ev = list(reversed(ev))
    for e in ev:
        if isinstance(e, dict):
            out.append(f"    [{e['turn_id']}] {e.get('speaker','')}: \"{e['quote']}\"")
        else:
            out.append(f"    \"{e}\"")
    return out


def render(case, rep) -> str:
    u = case["blind_unit_id"]
    parts = [f"BLINDED EXTRACT ID: {hy.blind_unit(u)}", "", "EXTRACT", ""]
    parts += hy.units()[u]["lines"]
    parts += ["", "-" * 60, ""]
    secs = []
    if case.get("reference"):
        r = case["reference"]
        secs.append(("REFERENCE THEME", r["label"], r["description"], [r["quote"]]))
    if case.get("candidate"):
        c = case["candidate"]
        secs.append(("CANDIDATE THEME", c["label"], c["description"], c["evidence"]))
    if rep % 2 == 1:
        secs = list(reversed(secs))
    for t, l, d, q in secs:
        parts += _block(t, l, d, q, rep) + [""]
    for key, title in (("reference_inventory", "ALL REFERENCE THEMES FOR THIS EXTRACT"),
                       ("sibling_candidates", "OTHER CANDIDATE THEMES FOR THIS EXTRACT"),
                       ("reference_group", "REFERENCE THEMES (the group)"),
                       ("candidate_group", "CANDIDATE THEMES (the group)")):
        if case.get(key):
            grp = list(case[key])
            if rep % 2 == 1:
                grp = list(reversed(grp))
            parts.append(title)
            for b in grp:
                parts += _block("  -", b["label"], b["description"],
                                b.get("evidence") or [b.get("quote", "")], rep)
            parts.append("")
    return "\n".join(parts)


# Terms that can never occur in participant speech. If one of these appears inside the
# extract itself, something is genuinely wrong.
HARD_LEAKS_ANYWHERE = ("gemini", "claude", "anthropic", "openai", "gpt",
                       "enriched", "demographics-only", "demographics only",
                       "synthetic", "0.6364", "u01", "u02", "u03", "u04", "u05",
                       "u06", "u07", "fg1", "fg2", "fg3", "fg4", "fg5",
                       "run01", "run02", "run03", "coder a", "coder b")


def _split_extract(text: str):
    """The verbatim extract vs everything we wrote around it."""
    start = text.find("EXTRACT\n")
    end = text.find("-" * 60)
    if start == -1 or end == -1:
        return "", text
    return text[start:end], text[:start] + text[end:]


def render_problems(case, rep) -> list[str]:
    """
    The extract is DATA quoted verbatim from a human transcript and may not be altered
    or redacted. A participant saying "macho" is speech about masculinity, not the study
    name, and censoring it would corrupt the very text the coder read. So the full
    provenance check runs on the scaffolding we author, and the extract is checked only
    for terms that could never be participant speech.
    """
    t = render(case, rep)
    extract, scaffold = _split_extract(t)
    bad = cm.prompt_purity_problems(scaffold)

    low = " ".join(extract.split()).lower()
    for term in HARD_LEAKS_ANYWHERE:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low):
            bad.append(f"hard provenance leak inside the extract: {term!r}")

    if hy.blind_unit(case["blind_unit_id"]) not in t:
        bad.append("blinded unit id missing")
    for u in ("S01", "S02", "S03", "S04", "S05", "S06"):
        if re.search(rf"(?<![A-Za-z0-9]){u}(?![A-Za-z0-9])", t):
            bad.append(f"unit id {u} leaked")
    return sorted(set(bad))


def _mk_cases_round1():
    c = _cands()
    H = {h["key"]: h for v in c["humans"].values() for h in v}
    M = {m["key"]: m for v in c["machines"].values() for m in v}
    out = []
    for case in c["cases"]:
        h, m = H[case["human_key"]], M[case["machine_key"]]
        out.append({"case_id": case["case_id"], "task": "A_PAIRWISE_CORRESPONDENCE",
                    "blind_unit_id": case["blind_unit_id"],
                    "question_id": case["question_id"],
                    "reference": {"label": h["label"], "description": h["description"],
                                  "quote": h["quote"]},
                    "candidate": {"label": m["label"], "description": m["description"],
                                  "evidence": m["evidence"]},
                    "provenance": {"human_key": h["key"], "machine_key": m["key"]}})
    return out


def _submit(cases, job_path, label):
    if job_path.exists():
        e = json.loads(job_path.read_text(encoding="utf-8"))
        raise AuditError(f"job already exists: {e.get('job_id')}")
    reqs, id_map = [], {}
    _load_env()
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    client = anthropic.Anthropic()

    n = 0
    for c in cases:
        for rep in (1, 2):
            probs = render_problems(c, rep)
            if probs:
                raise AuditError(f"{c['case_id']} rep{rep}: {probs}")
            text = render(c, rep)
            n += 1
            cid = f"hy{n:03d}"
            id_map[cid] = {"case_id": c["case_id"], "task": c["task"],
                           "repetition_index": rep,
                           "blind_unit_id": c["blind_unit_id"],
                           "question_id": c["question_id"],
                           "provenance": c.get("provenance", {}),
                           "cache_key": cache_key(
                               c["task"], c["case_id"], rep,
                               hashlib.sha256(text.encode()).hexdigest())}
            reqs.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(
                model=hy.AUDITOR_MODEL, max_tokens=hy.AUDITOR_MAX_OUTPUT_TOKENS,
                system=cm.prompt_for(c["task"]),
                messages=[{"role": "user", "content": text}],
                output_config={"effort": hy.AUDITOR_EFFORT,
                               "format": {"type": "json_schema",
                                          "schema": cm.task_schema(c["task"])}})))
    keys = [v["cache_key"] for v in id_map.values()]
    if len(set(keys)) != len(keys):
        raise AuditError("duplicate cache keys")

    print(f"submitting {label}: {len(reqs)} requests ...")
    batch = client.messages.batches.create(requests=reqs)
    rec = {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
           "processing_status": batch.processing_status, "n_requests": len(reqs),
           "model": hy.AUDITOR_MODEL, "effort": hy.AUDITOR_EFFORT,
           "custom_id_map": id_map, "cases": cases}
    hy._atomic(job_path, rec)
    print("  job id:", batch.id)
    return rec


def _retrieve(job_path, out_path):
    rec = json.loads(job_path.read_text(encoding="utf-8"))
    _load_env()
    import anthropic
    client = anthropic.Anthropic()
    b = client.messages.batches.retrieve(rec["job_id"])
    if b.processing_status != "ended":
        raise AuditError(f"status {b.processing_status}, not ended")
    id_map = rec["custom_id_map"]
    results = []
    for res in client.messages.batches.results(rec["job_id"]):
        meta = id_map.get(res.custom_id)
        if meta is None:
            raise AuditError(f"unknown custom_id {res.custom_id}")
        e = {"custom_id": res.custom_id, **meta, "result_type": res.result.type}
        if res.result.type != "succeeded":
            results.append({**e, "status": "NO_OUTPUT"})
            continue
        msg = res.result.message
        text = next((bl.text for bl in msg.content if bl.type == "text"), None)
        e["stop_reason"] = msg.stop_reason
        e["usage"] = {"input_tokens": msg.usage.input_tokens,
                      "output_tokens": msg.usage.output_tokens}
        if msg.stop_reason == "max_tokens":
            results.append({**e, "status": "OUTPUT_TRUNCATED"})
            continue
        try:
            j = json.loads(text)
        except Exception as ex:                     # noqa: BLE001
            results.append({**e, "status": "INVALID_JSON", "error": str(ex)})
            continue
        ok = (j.get("category") in cm.TASKS[meta["task"]]
              and j.get("confidence") in cm.CONFIDENCE)
        results.append({**e, "status": "COMPLETE" if ok else "INVALID",
                        "judgement": j})
    missing = sorted(set(id_map) - {r["custom_id"] for r in results})
    if missing:
        raise AuditError(f"missing responses: {missing[:8]}")
    out = {"retrieved_utc": datetime.now(UTC).isoformat(), "job_id": rec["job_id"],
           "classification": hy.CLASSIFICATION, "n_results": len(results),
           "n_complete": sum(1 for r in results if r["status"] == "COMPLETE"),
           "total_usage": {
               "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0)
                                   for r in results),
               "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0)
                                    for r in results)},
           "results": results}
    hy._atomic(out_path, out)
    return out


def main() -> int:
    a = sys.argv[1:]
    if "--round1-submit" in a:
        _submit(_mk_cases_round1(), _HY / "claude_job_round1.json", "round 1")
    elif "--status" in a:
        which = _HY / ("claude_job_round2.json" if "--r2" in a else "claude_job_round1.json")
        rec = json.loads(which.read_text(encoding="utf-8"))
        _load_env()
        import anthropic
        client = anthropic.Anthropic()
        b = client.messages.batches.retrieve(rec["job_id"])
        print(f"  job   : {rec['job_id']}")
        print(f"  status: {b.processing_status}")
        print(f"  counts: {b.request_counts}")
    elif "--round1-retrieve" in a:
        o = _retrieve(_HY / "claude_job_round1.json", _HY / "claude_round1_results.json")
        print(f"results {o['n_results']}  complete {o['n_complete']}  usage {o['total_usage']}")
    elif "--round2-submit" in a:
        import hybrid_round2 as r2
        _submit(r2.build_cases(), _HY / "claude_job_round2.json", "round 2")
    elif "--round2-retrieve" in a:
        o = _retrieve(_HY / "claude_job_round2.json", _HY / "claude_round2_results.json")
        print(f"results {o['n_results']}  complete {o['n_complete']}  usage {o['total_usage']}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
