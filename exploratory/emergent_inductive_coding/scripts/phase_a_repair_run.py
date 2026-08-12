"""PHASE_A_EVIDENCE_REPAIR — submit, retrieve and resolve the single repair request."""
from __future__ import annotations
import json, sys
from datetime import datetime, UTC
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
import inductive_phase_a as pa            # noqa: E402
import phase_a_revalidation as rv         # noqa: E402

D = _ROOT / "analysis/production_evaluation/inductive_phase_a"
JOB = D / "phase_a_repair_job.json"
RAW = D / "phase_a_repair_raw.json"


def submit():
    rep = json.loads((D / "evidence_repair_manifest.json").read_text(encoding="utf-8"))
    if rep["n_requests"] != 1 or not rep["unique_keys"]:
        raise SystemExit("manifest is not the single verified request")
    if JOB.exists():
        raise SystemExit("repair job already exists; creation is NOT idempotent")
    r = rep["requests"][0]
    _, ren = pa.build_manifest()
    body = ren[r["unit_id"]]["body"]
    if pa._sha(body) != r["unit_text_sha256"]:
        raise SystemExit("unit text does not reproduce unit_text_sha256")

    user = (f"{body}\n\n{'-' * 60}\n\nTHEME REQUIRING A SUPPORTING QUOTATION\n"
            f"  theme_id    : {r['theme_id']}\n"
            f"  label       : {r['label']}\n"
            f"  description : {r['description']}\n")
    pa._load_env()
    from google import genai
    from google.genai import types
    import os
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    cfg = types.GenerateContentConfig(
        system_instruction=rep["prompt"],
        response_mime_type="application/json",
        response_schema={k: v for k, v in rep["schema"].items()
                         if k in ("type", "required", "properties")},
        max_output_tokens=pa.MAX_OUTPUT_TOKENS)
    inline = [{"model": pa.MODEL,
               "contents": [{"parts": [{"text": user}], "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": r["custom_request_key"]}}]
    job = client.batches.create(model=pa.MODEL, src=inline,
                                config={"display_name": "phase_a_evidence_repair_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "execution_stage": "PHASE_A_EVIDENCE_REPAIR",
           "model": pa.MODEL, "execution_mode": pa.EXECUTION_MODE,
           "n_requests": 1,
           "custom_request_keys": [r["custom_request_key"]],
           "rendered_user_sha256": pa._sha(user)}
    rv._atomic(JOB, rec)
    print("job:", rec["job_name"])


def status():
    rec = json.loads(JOB.read_text(encoding="utf-8"))
    pa._load_env()
    from google import genai
    import os
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    j = client.batches.get(name=rec["job_name"])
    print(rec["job_name"], str(getattr(j, "state", None)))


def retrieve():
    rec = json.loads(JOB.read_text(encoding="utf-8"))
    pa._load_env()
    from google import genai
    import os
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", ""))
    if "SUCCEEDED" not in st:
        raise SystemExit(f"state {st}")
    out = {}
    for item in (getattr(getattr(job, "dest", None), "inlined_responses", None) or []):
        meta = getattr(item, "metadata", None) or {}
        key = (meta.get("custom_request_key") if isinstance(meta, dict)
               else getattr(meta, "custom_request_key", None))
        if key is None:
            raise SystemExit("response carries no custom_request_key")
        resp = getattr(item, "response", None)
        cands = getattr(resp, "candidates", None) or []
        um = getattr(resp, "usage_metadata", None)
        out[key] = {"custom_request_key": key,
                    "finish_reason": str(getattr(cands[0], "finish_reason", "")) if cands else "",
                    "raw_text": getattr(resp, "text", None),
                    "usage": {"input_tokens": getattr(um, "prompt_token_count", 0) or 0,
                              "output_tokens": getattr(um, "candidates_token_count", 0) or 0}}
    if set(out) != set(rec["custom_request_keys"]):
        raise SystemExit("custom_request_key mismatch")
    rv._atomic(RAW, {"retrieved_utc": datetime.now(UTC).isoformat(),
                     "job_name": rec["job_name"], "final_observed_state": st,
                     "matched_by": "custom_request_key",
                     "responses": list(out.values())})
    print("retrieved", len(out))


if __name__ == "__main__":
    a = sys.argv[1:]
    {"--submit": submit, "--status": status, "--retrieve": retrieve}[a[0]]()
