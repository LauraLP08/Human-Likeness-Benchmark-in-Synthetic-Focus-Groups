#!/usr/bin/env python3
"""
twinpop_render_personas.py — Phase 3, step 2 of the twin-population arm.

Renders each sampled census record into a three-field persona narrative, and
renders its gender-inverted twin for the stereotype-amplification audit
(pre-registro §4.4a, adendum entry 6: 24 pairs).

Frozen by ADENDUM_TWIN_POBLACIONAL_CONGELADO_2026-08-04.md entry 1
(as corrected 2026-08-05):
    model        claude-opus-5
    sampling     NONE — temperature/top_p/top_k are removed on this model (400)
    effort       medium
    max_tokens   4000  (thinking is on by default and shares the budget)
    fallbacks    disabled on purpose — the renderer's model identity is frozen,
                 so a silent substitution would corrupt the audit trail
    output       structured JSON, the three keys of entry 3
    prompt       verbatim from entry 1

A `stop_reason: "refusal"` STOPS the run and is recorded. It is never retried
on another model.

Outputs are archived verbatim with a per-item SHA-256: reproducibility here is
by archive, not by re-derivation (no seed parameter exists).

Usage:
    py scripts/twinpop_render_personas.py --out-dir <dir> --dry-run
    py scripts/twinpop_render_personas.py --out-dir <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load ANTHROPIC_API_KEY from the repo-root .env, so a run works without the key
# being exported in the calling shell. Same pattern as run_full_session.py,
# ablation_experiment.py, thematic_coding.py; a real environment variable still
# wins, since load_dotenv() does not override variables that are already set.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MODEL = "claude-opus-5"
MAX_TOKENS = 4000
EFFORT = "medium"

SCHEMA = {
    "type": "object",
    "properties": {
        "working_life": {"type": "string"},
        "home_and_household": {"type": "string"},
        "week_and_hobbies": {"type": "string"},
    },
    "required": ["working_life", "home_and_household", "week_and_hobbies"],
    "additionalProperties": False,
}

PROMPT_TEMPLATE = """You are writing a short factual life-sketch of a real UK resident for a research
simulation, based only on the census attributes given below. Write three separate
paragraphs, one per field, in plain British English, third-person-free (write as
neutral description, not as speech).

HARD CONSTRAINTS — a sketch violating any of these is discarded:
- Never mention food, meals, cooking, shopping for food, restaurants, pubs, drink,
  diet, nutrition, health, fitness, the gym, protein, farming, animals, bodies,
  weight, or eating of any kind.
- Never mention gender roles, masculinity, femininity, or what men or women are like.
- Never mention ethnicity, nationality, religion or country of birth.
- No markdown, no bullet points, no quotation marks around the text, no line breaks
  inside a field. One single paragraph per field.
- 65–92 words per field.
- Do not invent attributes that contradict the census attributes given.

CENSUS ATTRIBUTES: {attributes}

Return JSON: {{"working_life": "...", "home_and_household": "...", "week_and_hobbies": "..."}}"""

# The person's NAME is deliberately never passed to the renderer: it is a
# separate demographic field on the agent payload, it is not needed to write the
# narrative, and in the gender-inverted control it would be a confound that
# §4.4b's blind forced choice explicitly neutralises.
FIELD_ORDER = ["working_life", "home_and_household", "week_and_hobbies"]


def build_attributes(cell: dict, candidate: dict, sex: str) -> str:
    parts = [
        f"Sex: {sex}",
        f"Age: {cell['age']}",
        f"Settlement type: {cell['urban_rural']}",
        f"Region: {cell['region']}, {cell['country']}",
    ]
    for field in FIELD_ORDER:
        for var, label in candidate["attributes"].get(field, {}).items():
            if label in ("Does not apply", "?"):
                continue
            parts.append(f"{var.replace('_', ' ')}: {label}")
    return "; ".join(parts)


def render(client, prompt: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        raise SystemExit(
            "REFUSAL from the renderer — the run stops here by design (adendum entry 1).\n"
            f"  category: {getattr(detail, 'category', None)}\n"
            f"  explanation: {getattr(detail, 'explanation', None)}\n"
            "Record this, decide with the researcher, and do NOT substitute another model."
        )
    text = next(b.text for b in resp.content if b.type == "text")
    return {
        "narrative": json.loads(text),
        "raw_text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "stop_reason": resp.stop_reason,
        "model": resp.model,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true", help="build prompts, make no API calls")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cells = json.loads((args.out_dir / "microdata_cells.json").read_text(encoding="utf-8"))

    jobs = []
    for cell in cells:
        for cand in cell["candidates"]:
            for branch, sex in (("real", "Male"), ("inverted", "Female")):
                jobs.append({
                    "agent_id": cell["agent_id"],
                    "candidate_index": cand["candidate_index"],
                    "branch": branch,
                    "microdata_record_id": cand["microdata_record_id"],
                    "prompt": PROMPT_TEMPLATE.format(
                        attributes=build_attributes(cell, cand, sex)
                    ),
                })

    print(f"{len(jobs)} calls "
          f"({sum(1 for j in jobs if j['branch'] == 'real')} real + "
          f"{sum(1 for j in jobs if j['branch'] == 'inverted')} gender-inverted)")

    if args.dry_run:
        print("\n--- DRY RUN: no API calls. First prompt verbatim ---\n")
        print(jobs[0]["prompt"])
        (args.out_dir / "render_prompts_dryrun.json").write_text(
            json.dumps(jobs, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nall {len(jobs)} prompts -> {args.out_dir / 'render_prompts_dryrun.json'}")
        return 0

    import anthropic
    client = anthropic.Anthropic()

    results, tot_in, tot_out = [], 0, 0
    for i, job in enumerate(jobs, start=1):
        out = render(client, job["prompt"])
        tot_in += out["usage"]["input_tokens"]
        tot_out += out["usage"]["output_tokens"]
        results.append({**{k: v for k, v in job.items() if k != "prompt"},
                        "prompt_sha256": hashlib.sha256(job["prompt"].encode("utf-8")).hexdigest(),
                        **out})
        words = sum(len(v.split()) for v in out["narrative"].values())
        print(f"  [{i:2d}/{len(jobs)}] {job['agent_id']} c{job['candidate_index']} "
              f"{job['branch']:8s} {words:3d}w  {out['sha256'][:12]}")

    manifest = {
        "gate": "phase3_step2",
        "arm": "twinpop",
        "frozen_by": "ADENDUM entry 1 (corrected 2026-08-05)",
        "model": MODEL,
        "params": {"effort": EFFORT, "max_tokens": MAX_TOKENS,
                   "sampling": "none — removed on this model",
                   "fallbacks": "disabled by design"},
        "prompt_template_sha256": hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest(),
        "n_calls": len(results),
        "usage_total": {"input_tokens": tot_in, "output_tokens": tot_out},
        "reproducibility": "by archive, not by re-derivation — the API exposes no seed parameter",
        "name_withheld_from_renderer": True,
        "results": results,
    }
    (args.out_dir / "persona_narratives.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    cost = tot_in / 1e6 * 5 + tot_out / 1e6 * 25
    print(f"\n{len(results)} narratives -> {args.out_dir / 'persona_narratives.json'}")
    print(f"tokens: {tot_in:,} in / {tot_out:,} out  (~${cost:.2f} at Opus 5 list price)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
