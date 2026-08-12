"""
TECHNICAL_TRUNCATION_REPAIR for the hyper-exactness audit.

    py scripts/agent_fidelity_hx_repair.py

WHAT WENT WRONG
---------------
`max_output_tokens` was sized as 1024 + 260 per item, giving 4,144 for a batch of twelve.
Each decision carries a verbatim quote that can run to 220 words plus three prose fields,
so a full batch needs several times that. Five of the twenty-four requests were cut
mid-string and returned unparseable JSON, taking 60 adjudications with them.

WHAT IS AND IS NOT CHANGED
--------------------------
The ONLY change is max_output_tokens. The prompt, the schema, the items, their order, the
model and the effort are identical, and the nineteen intact requests are neither resent
nor altered - their results are reused as returned. This is the same repair the study
already applied to Stage D.
"""
from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

import agent_fidelity_audit_v2 as v2

_OUT = Path(__file__).resolve().parent.parent / \
    "analysis/production_evaluation/agent_fidelity"

REPAIR_MAX_OUTPUT_TOKENS = 16384


def failed_custom_ids() -> list[str]:
    res = json.loads((_OUT / "v2_hyper_exactness_results.json").read_text(
        encoding="utf-8"))
    bad = {f["custom_id"] for f in res["validation_failures"] if "custom_id" in f}
    rm = {r["custom_id"]: r for r in json.loads(
        (_OUT / "v2_hyper_exactness_provider_request_manifest.json").read_text(
            encoding="utf-8"))["requests"]}
    # any request whose items are missing from the returned set also needs repair
    missing = {tuple(m) for m in res["missing_adjudications"]}
    for cid, r in rm.items():
        for iid in r["ordered_item_ids"]:
            if (iid, r["repetition_index"]) in missing:
                bad.add(cid)
                break
    return sorted(bad)


def submit_repair() -> dict:
    v2._load_env()
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    items = {i["item_id"]: i for i in json.loads(
        (_OUT / "v2_hyper_exactness_items_blinded.json").read_text(
            encoding="utf-8"))["items"]}
    rm = {r["custom_id"]: r for r in json.loads(
        (_OUT / "v2_hyper_exactness_provider_request_manifest.json").read_text(
            encoding="utf-8"))["requests"]}

    cids = failed_custom_ids()
    if not cids:
        raise RuntimeError("nothing to repair")

    reqs = []
    for cid in cids:
        r = rm[cid]
        payload = [items[i] for i in r["ordered_item_ids"]]
        body = (v2.HX_PROMPT + "\n\nITEMS (" + str(len(payload)) + "):\n"
                + json.dumps(payload, ensure_ascii=False, indent=1))
        reqs.append(Request(
            custom_id=cid,
            params=MessageCreateParamsNonStreaming(
                model=v2.MODEL, max_tokens=REPAIR_MAX_OUTPUT_TOKENS,
                messages=[{"role": "user", "content": body}],
                output_config={"effort": v2.EFFORT,
                               "format": {"type": "json_schema",
                                          "schema": v2.SCHEMAS["HYPER_EXACTNESS"]}})))

    print(f"repairing {len(reqs)} truncated requests at "
          f"max_output_tokens={REPAIR_MAX_OUTPUT_TOKENS}")
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)

    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_id": batch.id,
           "record": "TECHNICAL_TRUNCATION_REPAIR",
           "processing_status": batch.processing_status,
           "repaired_custom_ids": cids,
           "n_requests": len(reqs),
           "only_change": "max_output_tokens 4144 -> 16384",
           "prompt_schema_items_order_model_effort_unchanged": True,
           "intact_requests_reused_not_resent": True,
           "supersedes_nothing_in_the_original_job": True}
    (_OUT / "v2_hyper_exactness_repair_job.json").write_text(
        json.dumps(rec, indent=1), encoding="utf-8")
    print("repair job:", batch.id, batch.processing_status)
    return rec


if __name__ == "__main__":
    submit_repair()
