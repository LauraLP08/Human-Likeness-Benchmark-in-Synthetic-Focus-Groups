"""
D_CROSS_MODEL_ADJUDICATION — Claude adjudicates the 188 cases Stage C did not settle.

    py scripts/stage_d_adjudication.py --preflight
    py scripts/stage_d_adjudication.py --submit
    py scripts/stage_d_adjudication.py --status
    py scripts/stage_d_adjudication.py --retrieve
    py scripts/stage_d_adjudication.py --score

TEN REQUESTS, 376 EVALUATIONS
-----------------------------
Five questions x two repetitions. Each request carries every case for its question and
returns one decision per raw_theme_id. Requests and evaluations are different quantities
and are reported separately throughout.

PROVENANCE
----------
Gemini remains the primary extractor and the author of the canonical taxonomy. Claude is
a cross-model adjudicator of the ambiguous cases only. Cross-model consensus is NOT human
validation and is never described as such.

WHAT THE ADJUDICATOR IS NOT TOLD
--------------------------------
Not the condition, corpus, focus group or replicate; not Stage B's decision; not Stage
C's decisions; not the status that caused the case to be adjudicated; not the deductive
codebook; not any prior result. It sees the theme and the frozen taxonomy, nothing else.

ORDER NEVER DECIDES
-------------------
Themes and clusters are ordered by two DIFFERENT deterministic hashes in the two
repetitions, so a decision that depended on position would show up as instability
instead of hiding.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import stage_b_taxonomy as sb        # noqa: E402
import stage_c_stability as sc       # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_D = _ROOT / "analysis/production_evaluation/inductive_stage_d"
_B = sb._B
_C = sc._C

MODEL = "claude-opus-5"
EFFORT = "high"
MAX_OUTPUT_TOKENS = 8192
EXECUTION_MODE = "batch"
STAGE = "D_CROSS_MODEL_ADJUDICATION"

ORDER_SALT = {1: "stage_d_rep1_order", 2: "stage_d_rep2_order"}

_MANIFEST = _D / "stage_d_manifest.json"
_JOB = _D / "stage_d_batch_job.json"
_RAW = _D / "stage_d_raw_responses.json"

UNCERTAIN = "UNCERTAIN"
CONSENSUS = "CROSS_MODEL_CONSENSUS_ASSIGNMENT"
UNRESOLVED = "CROSS_MODEL_UNRESOLVED"

SYSTEM_PROMPT = """\
You are given a fixed taxonomy of clusters and a list of themes. Decide, for each theme, \
which single cluster it belongs to.

Rules:
  * Use ONLY the cluster_ids given to you. Never invent, rename, merge or split a \
cluster. The taxonomy is fixed.
  * Decide by whether the theme makes the SAME SUBSTANTIVE CLAIM as the cluster's \
definition, not by shared vocabulary. Themes about the same topic belong to different \
clusters when they differ in mechanism, agent, stance or consequence.
  * Give a brief justification for each decision, one sentence, referring to the claim \
rather than to the wording.
  * If a theme genuinely does not resolve to one cluster, return the literal value \
UNCERTAIN. This is a legitimate answer and is preferred to forcing a poor fit.
  * Every raw_theme_id you are given must appear exactly once in your decisions. Never \
drop a theme and never invent an identifier.
  * The order in which themes and clusters are listed carries no meaning.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decisions"],
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["raw_theme_id", "assigned_cluster_id", "justification"],
                "properties": {
                    "raw_theme_id": {"type": "string"},
                    "assigned_cluster_id": {"type": "string"},
                    "justification": {"type": "string"},
                },
            },
        },
    },
}


def cases() -> dict:
    """question -> [{raw_theme_id, label, description}], from Stage C's deduplicated set."""
    s = json.loads((_C / "stage_c_stability.json").read_text(encoding="utf-8"))
    wanted = {(c["question"], c["raw_theme_id"]) for c in s["stage_d_input"]["cases"]}
    by_q = sb.load_themes()
    out = defaultdict(list)
    for q in sb.QUESTIONS:
        for t in by_q[q]:
            if (q, t["raw_theme_id"]) in wanted:
                out[q].append({"raw_theme_id": t["raw_theme_id"],
                               "label": t["label"], "description": t["description"]})
    got = sum(len(v) for v in out.values())
    if got != len(wanted):
        raise sb.StageBError(f"{got} cases resolved, expected {len(wanted)}")
    return dict(out)


def render(themes: list, clusters: list, rep: int) -> str:
    salt = ORDER_SALT[rep]
    cl = sorted(clusters, key=lambda c: sb._sha(f"{salt}|C|{c['cluster_id']}|"
                                                f"{c['label']}"))
    th = sorted(themes, key=lambda t: sb._sha(f"{salt}|T|{t['raw_theme_id']}|"
                                              f"{t['label']}"))
    lines = ["FIXED TAXONOMY", ""]
    for c in cl:
        lines.append(f"cluster_id: {c['cluster_id']}")
        lines.append(f"  label     : {c['label']}")
        lines.append(f"  definition: {c['definition']}")
        lines.append("")
    lines += ["-" * 60, "", f"THEMES TO DECIDE ({len(th)} in total)", ""]
    for t in th:
        lines.append(f"raw_theme_id: {t['raw_theme_id']}")
        lines.append(f"  label      : {t['label']}")
        lines.append(f"  description: {t['description']}")
        lines.append("")
    return "\n".join(lines)


# Anything that would reveal why a case is here, or where it came from.
#
# Matched on WORD BOUNDARIES, not as substrings. A substring test flagged "medical
# conditions" as the study's `condition` variable in all ten requests — ordinary English
# in a participant's own theme, identifying nothing.
#
# `condition` and `replicate` are dropped entirely for the same reason they were dropped
# in Stage B: participants discuss medical conditions and whether plant-based food can
# replicate meat texture. What no theme or cluster would ever contain is a run
# identifier, a study slug, a pipeline stage name or a stability status.
FORBIDDEN = ("stage b", "stage c", "unstable", "stable_same_as_stage_b",
             "stable_different_from_stage_b", "enriched", "demographics-only",
             "fg1", "fg2", "fg3", "fg4", "fg5", "run01", "run02", "run03", "run04",
             "macho_meals", "codebook", "subtheme", "adjudicator", "adjudication")


def build_manifest() -> tuple[dict, dict]:
    taxes = json.loads((_B / "stage_b_canonical_taxonomies.json").read_text(
        encoding="utf-8"))["taxonomies"]
    cs = cases()
    prompt_sha = sb._sha(SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))

    reqs, bodies, problems = [], {}, []
    for q in sb.QUESTIONS:
        tax = taxes[str(q)]
        recomputed = sb._sha(json.dumps({"clusters": tax["clusters"]},
                                        sort_keys=True, ensure_ascii=False))
        if recomputed != tax["taxonomy_sha256"]:
            problems.append(f"Q{q}: taxonomy hash drifted since freezing")
        themes = cs[q]
        for rep in (1, 2):
            body = render(themes, tax["clusters"], rep)
            bodies[(q, rep)] = body
            import re as _re
            low = " ".join(body.lower().split())
            hits = [f for f in FORBIDDEN
                    if _re.search(r"(?<![a-z0-9])" + _re.escape(f) + r"(?![a-z0-9])",
                                  low)]
            if hits:
                problems.append(f"Q{q} rep{rep}: forbidden context {hits}")
            reqs.append({
                "custom_id": f"sd_q{q}_r{rep}",
                "question": q, "repetition_index": rep,
                "n_cases": len(themes),
                "expected_raw_theme_ids": sorted(t["raw_theme_id"] for t in themes),
                "valid_cluster_ids": [c["cluster_id"] for c in tax["clusters"]],
                "taxonomy_sha256": tax["taxonomy_sha256"],
                "order_salt": ORDER_SALT[rep],
                "rendered_sha256": sb._sha(body),
                "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
                "model": MODEL, "effort": EFFORT,
                "execution_mode": EXECUTION_MODE,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "cache_key": sb._sha("|".join([STAGE, str(q), str(rep),
                                               tax["taxonomy_sha256"], sb._sha(body),
                                               prompt_sha, schema_sha, MODEL, EFFORT,
                                               EXECUTION_MODE])),
                "prompt_words": len(body.split()),
            })

    n_cases = sum(len(v) for v in cs.values())
    n_evals = n_cases * 2
    if len(reqs) != 10:
        problems.append(f"{len(reqs)} requests, expected 10")
    if n_cases != 188:
        problems.append(f"{n_cases} cases, expected 188")
    if len({r["custom_id"] for r in reqs}) != 10:
        problems.append("custom ids are not unique")
    for q in sb.QUESTIONS:
        r1 = next(r for r in reqs if r["question"] == q and r["repetition_index"] == 1)
        r2 = next(r for r in reqs if r["question"] == q and r["repetition_index"] == 2)
        if r1["rendered_sha256"] == r2["rendered_sha256"]:
            problems.append(f"Q{q}: both repetitions render identically; "
                            "the order is not varied")
        if r1["expected_raw_theme_ids"] != r2["expected_raw_theme_ids"]:
            problems.append(f"Q{q}: repetitions cover different themes")

    est_in = sum(round(r["prompt_words"] * 1.75 + 1600) for r in reqs)
    est_out = n_evals * 90
    cost = est_in / 1e6 * 2.5 + est_out / 1e6 * 12.5
    return {"built_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
            "n_requests": len(reqs), "n_evaluations": n_evals, "n_cases": n_cases,
            "requests_and_evaluations_are_different": True,
            "cases_per_question": {str(q): len(v) for q, v in sorted(cs.items())},
            "model": MODEL, "effort": EFFORT, "execution_mode": EXECUTION_MODE,
            "provenance": {
                "primary_extractor": "Gemini",
                "canonical_taxonomy_author": "Gemini",
                "cross_model_adjudicator": "Claude",
                "cross_model_consensus_is_not_human_validation": True},
            "blinding": {
                "shown": ["opaque raw_theme_id", "label", "description",
                          "frozen cluster ids, labels and definitions"],
                "not_shown": ["condition", "corpus", "focus group", "replicate",
                              "Stage B decision", "Stage C decisions",
                              "the status that triggered adjudication",
                              "deductive codebook", "any prior result"],
                "forbidden_tokens_checked": len(FORBIDDEN)},
            "ordering": {"rep1_salt": ORDER_SALT[1], "rep2_salt": ORDER_SALT[2],
                         "themes_and_clusters_both_reordered": True,
                         "order_never_decides": True},
            "estimated_input_tokens": est_in, "estimated_output_tokens": est_out,
            "calculated_list_batch_cost_usd": round(cost, 2),
            "rate_source": "verified list Batch rate 2026-08-02, $2.50/$12.50 per MTok",
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def submit() -> dict:
    man, bodies = build_manifest()
    if not man["pass"]:
        raise sb.StageBError("preflight failed: " + "; ".join(man["problems"]))
    if _JOB.exists():
        raise sb.StageBError("stage D job exists; creation is NOT idempotent")
    S1._atomic(_MANIFEST, man)
    S1._load_env()
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    client = anthropic.Anthropic()
    reqs = [Request(custom_id=r["custom_id"],
                    params=MessageCreateParamsNonStreaming(
                        model=MODEL, max_tokens=MAX_OUTPUT_TOKENS,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user",
                                   "content": bodies[(r["question"],
                                                      r["repetition_index"])]}],
                        output_config={"effort": EFFORT,
                                       "format": {"type": "json_schema",
                                                  "schema": RESPONSE_SCHEMA}}))
            for r in man["requests"]]
    batch = client.messages.batches.create(requests=reqs)
    rec = {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
           "stage": STAGE, "state_at_creation": batch.processing_status,
           "n_requests": len(reqs), "n_evaluations": man["n_evaluations"],
           "custom_ids": [r["custom_id"] for r in man["requests"]]}
    S1._atomic(_JOB, rec)
    print("job:", rec["job_id"])
    return rec


def status() -> str:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    S1._load_env()
    import anthropic
    b = anthropic.Anthropic().messages.batches.retrieve(rec["job_id"])
    print(rec["job_id"], b.processing_status, dict(b.request_counts))
    return b.processing_status


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    S1._load_env()
    import anthropic
    client = anthropic.Anthropic()
    b = client.messages.batches.retrieve(rec["job_id"])
    if b.processing_status != "ended":
        raise sb.StageBError(f"status {b.processing_status}")
    out, uin, uout = {}, 0, 0
    for res in client.messages.batches.results(rec["job_id"]):
        cid = res.custom_id
        if cid not in rec["custom_ids"]:
            raise sb.StageBError(f"unknown custom_id {cid}")
        e = {"custom_id": cid, "result_type": res.result.type}
        if res.result.type == "succeeded":
            m = res.result.message
            uin += m.usage.input_tokens
            uout += m.usage.output_tokens
            e.update({"stop_reason": m.stop_reason,
                      "raw_text": next((bl.text for bl in m.content
                                        if bl.type == "text"), None)})
        out[cid] = e
    if missing := sorted(set(rec["custom_ids"]) - set(out)):
        raise sb.StageBError(f"missing: {missing}")
    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_id": rec["job_id"], "stage": STAGE, "matched_by": "custom_id",
               "n_results": len(out),
               "measured_usage": {"input_tokens": uin, "output_tokens": uout},
               "responses": [out[k] for k in sorted(out)]}
    S1._atomic(_RAW, payload)
    print(f"retrieved {len(out)}")
    return payload


def score() -> dict:
    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(_RAW.read_text(encoding="utf-8"))
    by_id = {r["custom_id"]: r for r in man["requests"]}

    parsed, quarantine = {}, []
    for resp in raw["responses"]:
        req = by_id[resp["custom_id"]]
        q, rep = req["question"], req["repetition_index"]
        problems = []
        if resp.get("result_type") != "succeeded":
            problems.append("not succeeded")
        elif resp.get("stop_reason") != "end_turn":
            problems.append(f"stop_reason {resp.get('stop_reason')}")
        j = None
        if not problems:
            try:
                j = json.loads(resp["raw_text"] or "")
            except Exception as e:                               # noqa: BLE001
                problems.append(f"invalid json: {e}")
        if j is not None:
            dec = j.get("decisions") or []
            expected = set(req["expected_raw_theme_ids"])
            got = [d.get("raw_theme_id") for d in dec]
            if dup := [i for i, n in Counter(got).items() if n > 1]:
                problems.append(f"{len(dup)} duplicated raw_theme_id")
            if unk := sorted(set(got) - expected):
                problems.append(f"{len(unk)} unknown raw_theme_id")
            if omi := sorted(expected - set(got)):
                problems.append(f"{len(omi)} omitted raw_theme_id")
            valid = set(req["valid_cluster_ids"]) | {UNCERTAIN}
            if bad := [d for d in dec if d.get("assigned_cluster_id") not in valid]:
                problems.append(f"{len(bad)} decisions to a non-existent cluster")
            if miss := [d for d in dec if not (d.get("justification") or "").strip()]:
                problems.append(f"{len(miss)} decisions without a justification")
        if problems:
            quarantine.append({"question": q, "repetition": rep,
                               "problems": problems})
            continue
        parsed[(q, rep)] = {d["raw_theme_id"]: d for d in j["decisions"]}

    gate_problems = []
    if len(parsed) != 10:
        gate_problems.append(f"{len(parsed)}/10 valid responses")
    counts = Counter()
    for (q, _r), dd in parsed.items():
        for rid in dd:
            counts[(q, rid)] += 1
    expected_pairs = {(r["question"], i) for r in man["requests"]
                      for i in r["expected_raw_theme_ids"]}
    if len(counts) != 188:
        gate_problems.append(f"{len(counts)}/188 themes covered")
    if wrong := {k for k, v in counts.items() if v != 2}:
        gate_problems.append(f"{len(wrong)} themes without exactly two evaluations")
    if missing := expected_pairs - set(counts):
        gate_problems.append(f"{len(missing)} themes with no evaluation")
    for q in sb.QUESTIONS:
        tax_hashes = {r["taxonomy_sha256"] for r in man["requests"]
                      if r["question"] == q}
        if len(tax_hashes) != 1:
            gate_problems.append(f"Q{q}: taxonomy hash differs between repetitions")
    if gate_problems:
        return {"gate_pass": False, "gate_problems": gate_problems,
                "quarantine": quarantine}

    rows = []
    for (q, rid) in sorted(counts):
        d1 = parsed[(q, 1)][rid]
        d2 = parsed[(q, 2)][rid]
        a1, a2 = d1["assigned_cluster_id"], d2["assigned_cluster_id"]
        if a1 == a2 and a1 != UNCERTAIN:
            res, final = CONSENSUS, a1
        else:
            res, final = UNRESOLVED, None
        rows.append({"question": q, "raw_theme_id": rid,
                     "rep1_cluster": a1, "rep2_cluster": a2,
                     "resolution": res, "final_cluster_id": final,
                     "rep1_justification": d1["justification"],
                     "rep2_justification": d2["justification"]})

    per_q = defaultdict(Counter)
    for r in rows:
        per_q[r["question"]][r["resolution"]] += 1
    return {"scored_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
            "gate_pass": True, "gate_problems": [],
            "n_requests": len(parsed), "n_evaluations": sum(counts.values()),
            "n_cases": len(rows),
            "resolution_counts": dict(Counter(r["resolution"] for r in rows)),
            "per_question": {str(q): dict(v) for q, v in sorted(per_q.items())},
            "tie_breaking_by_confidence_or_mode": False,
            "cross_model_consensus_is_not_human_validation": True,
            "quarantine": quarantine,
            "measured_usage": raw["measured_usage"],
            "rows": rows}


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        man, _ = build_manifest()
        S1._atomic(_MANIFEST, man)
        print("=== STAGE D PREFLIGHT ===")
        print(f"  SOLICITUDES        {man['n_requests']}   (no 376)")
        print(f"  EVALUACIONES       {man['n_evaluations']}")
        print(f"  casos              {man['n_cases']}  {man['cases_per_question']}")
        print(f"  modelo             {man['model']} effort {man['effort']} "
              f"({man['execution_mode']})")
        print(f"  tokens estimados   in {man['estimated_input_tokens']:,}  "
              f"out {man['estimated_output_tokens']:,}")
        print(f"  coste calculado    ${man['calculated_list_batch_cost_usd']}  "
              f"({man['rate_source']})")
        print(f"  orden rep1/rep2 distinto, el orden nunca decide: "
              f"{man['ordering']['order_never_decides']}")
        print(f"  contexto prohibido comprobado: "
              f"{man['blinding']['forbidden_tokens_checked']} tokens")
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
            return 2
        S1._atomic(_D / "stage_d_adjudication.json",
                   {k: v for k, v in s.items() if k != "rows"})
        with (_D / "stage_d_decisions_long.csv").open("w", encoding="utf-8",
                                                      newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(s["rows"][0]))
            w.writeheader()
            w.writerows(s["rows"])
        print(f"solicitudes {s['n_requests']}  evaluaciones {s['n_evaluations']}  "
              f"casos {s['n_cases']}")
        print("  ", s["resolution_counts"])
        for q, v in s["per_question"].items():
            print(f"    Q{q}: {v}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
