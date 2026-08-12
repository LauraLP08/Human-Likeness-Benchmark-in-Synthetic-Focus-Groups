"""
B_CANONICAL_TAXONOMY — five Gemini Batch calls, one canonical taxonomy per question.

    py scripts/stage_b_taxonomy.py --preflight
    py scripts/stage_b_taxonomy.py --submit
    py scripts/stage_b_taxonomy.py --status
    py scripts/stage_b_taxonomy.py --retrieve
    py scripts/stage_b_taxonomy.py --validate

STAGE B ONLY. Stage C, D, E1, E2, E3, F1 and F2 are not run, and no accumulation,
saturation or condition comparison is computed or interpreted here.

WHAT THE MODEL SEES
-------------------
Per theme: an opaque raw_theme_id, a label and a description. Nothing else. No condition,
no human/synthetic marker, no focus group, no replication, no unit id, no question
identifier, no quotations, no deductive codebook, no prior metric.

The real identity of each raw theme lives only in the sealed mapping.

VOLUME DOMINANCE, STATED NOT CORRECTED
--------------------------------------
The pooled corpus is 442 synthetic themes against 84 human ones. A taxonomy induced from
it is exposed to that asymmetry: clusters will tend to form around the wording that
recurs most, and synthetic wording recurs five times more often. Stage B does NOT try to
correct this — reweighting or stratifying here would silently redefine what "canonical"
means. The balanced-subsample sensitivity is E1/E2, it is separate, and it is future.

NO EMBEDDINGS, NO NEAREST NEIGHBOUR. Neither is used to decide correspondence anywhere
in this module; ordering is by content hash alone.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa   # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_A = _PE / "inductive_phase_a"
_B = _PE / "inductive_stage_b"
_SEALED = _B / "sealed"
_V2 = _A / "phase_a_accepted_v2.json"

MODEL = "gemini-3.5-flash"
EXECUTION_MODE = "batch"
MAX_OUTPUT_TOKENS = 32768
STAGE = "B_CANONICAL_TAXONOMY"
ORDER_SALT = "stage_b_order_v1"

_MANIFEST = _B / "stage_b_manifest.json"
_JOB = _B / "stage_b_batch_job.json"
_RAW = _B / "stage_b_raw_responses.json"

QUESTIONS = (1, 2, 3, 4, 5)


class StageBError(RuntimeError):
    pass


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


SYSTEM_PROMPT = """\
You are given a list of themes that were identified independently across many separate \
sections of discussion transcripts. Each carries an opaque identifier, a short label and \
a one-sentence description. You know nothing else about where any of them came from, and \
nothing else is relevant to this task.

Build a canonical taxonomy: group the themes that express THE SAME SUBSTANTIVE CLAIM.

What to group:
  * Group themes that make the same claim about the same thing, however differently \
they are worded.

What NOT to group:
  * Do not merge themes merely because they share vocabulary. Two themes about "family" \
are not the same theme unless they say the same thing about family.
  * Keep separate any themes that differ in MECHANISM (how something happens), in AGENT \
(who does it), in STANCE (whether it is endorsed, rejected or questioned), or in \
CONSEQUENCE (what follows from it). These distinctions matter even when the surface \
wording is close.

Granularity:
  * Avoid clusters so broad that they absorb unrelated claims.
  * Avoid a separate cluster for every surface rewording of one claim.

For each cluster return:
  * cluster_id      a short identifier unique within this taxonomy, e.g. C1, C2
  * label           a self-sufficient noun phrase, understandable without reading the \
member themes
  * definition      one or two sentences stating exactly what claim this cluster covers, \
self-sufficient in the same way

Then assign EVERY raw theme:
  * every raw_theme_id you were given must appear exactly once in the assignments
  * assign it to a cluster_id you defined, or to the literal value UNCERTAIN
  * use UNCERTAIN when the theme genuinely cannot be resolved to one cluster — it is a \
legitimate answer and is preferred to forcing a bad fit
  * never drop a theme, never ignore one, never invent an identifier
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["clusters", "assignments"],
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["cluster_id", "label", "definition"],
                "properties": {
                    "cluster_id": {"type": "string"},
                    "label": {"type": "string"},
                    "definition": {"type": "string"},
                },
            },
        },
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["raw_theme_id", "cluster_id"],
                "properties": {
                    "raw_theme_id": {"type": "string"},
                    "cluster_id": {"type": "string"},
                },
            },
        },
    },
}

# Tokens that identify provenance and CANNOT occur innocuously in a theme label or
# description. The words the extractor actually wrote are its own analytic vocabulary:
# themes here discuss whether plant-based food should "replicate" meat texture, and
# whether trust is "harder to replicate" in cities. Banning `replicate`/`replication`
# would block Stage B over ordinary content while identifying nothing.
#
# `human`, `synthetic` and `condition` are excluded for the same reason — they are
# ordinary English about food and are not provenance on their own. What no participant
# or extractor would ever write is a run identifier, a study slug or a codebook cell id.
BLIND_TOKENS = ("enriched", "demographics-only", "demographics only",
                "fg1", "fg2", "fg3", "fg4", "fg5",
                "run01", "run02", "run03", "run04", "macho_meals",
                "unit_id", "raw_theme_id of", "codebook", "subtheme",
                "a.1", "a.2", "a.3", "b.1", "b.2", "b.3", "b.4",
                "c.1", "c.2", "c.3")

# What the prompt STRUCTURE must never carry, checked separately from theme text.
STRUCTURAL_BLIND = ("condition", "human", "synthetic", "focus group", "replication",
                    "question 1", "question 2", "question 3", "question 4",
                    "question 5")


def opaque_id(question: int, unit_id: str, theme_id: str) -> str:
    return "RT_" + _sha(f"{ORDER_SALT}|{question}|{unit_id}|{theme_id}")[:12].upper()


def load_themes() -> dict:
    """question -> list of themes, ordered deterministically by content hash."""
    v2 = json.loads(_V2.read_text(encoding="utf-8"))
    if not v2["gate"]["pass"]:
        raise StageBError("Phase A gate did not pass")
    by_q = {q: [] for q in QUESTIONS}
    for u in v2["units"]:
        for t in u["themes"]:
            oid = opaque_id(u["question"], u["unit_id"], t["theme_id"])
            by_q[u["question"]].append({
                "raw_theme_id": oid,
                "label": t["label"], "description": t["description"],
                # sealed side, never rendered
                "_unit_id": u["unit_id"], "_theme_id": t["theme_id"],
                "_condition": u["condition"], "_fg": u["fg"],
                "_canonical_replication_index": u["canonical_replication_index"],
                "_physical_run": u["physical_run"], "_question": u["question"],
            })
    for q in QUESTIONS:
        # deterministic content-hash order; never grouped by condition first
        by_q[q].sort(key=lambda t: _sha(f"{ORDER_SALT}|{t['label']}|"
                                        f"{t['description']}|{t['raw_theme_id']}"))
    return by_q


def render(question: int, themes: list) -> str:
    lines = [f"THEMES TO CONSOLIDATE ({len(themes)} in total)", ""]
    for t in themes:
        lines.append(f"raw_theme_id: {t['raw_theme_id']}")
        lines.append(f"  label      : {t['label']}")
        lines.append(f"  description: {t['description']}")
        lines.append("")
    return "\n".join(lines)


def build_manifest() -> tuple[dict, dict]:
    by_q = load_themes()
    prompt_sha = _sha(SYSTEM_PROMPT)
    schema_sha = _sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))

    requests, bodies, problems = [], {}, []
    total = 0
    for q in QUESTIONS:
        themes = by_q[q]
        total += len(themes)
        body = render(q, themes)
        bodies[q] = body

        # theme text: hard provenance only. Prompt scaffolding: the full structural list.
        leaks = pa._hits(body, BLIND_TOKENS)
        if leaks:
            problems.append(f"Q{q}: blinding leak {leaks}")
        scaffold = SYSTEM_PROMPT + "\nTHEMES TO CONSOLIDATE (n in total)"
        if s := pa._hits(scaffold, STRUCTURAL_BLIND):
            problems.append(f"structural blinding leak in the prompt: {s}")
        ids = [t["raw_theme_id"] for t in themes]
        if len(set(ids)) != len(ids):
            problems.append(f"Q{q}: duplicate opaque ids")

        key = f"sb::q{q}"
        requests.append({
            "custom_request_key": key,
            "question": q,
            "n_themes": len(themes),
            "expected_raw_theme_ids": ids,
            "rendered_sha256": _sha(body),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "model": MODEL, "execution_mode": EXECUTION_MODE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "effective_config": {"model": MODEL,
                                 "response_mime_type": "application/json",
                                 "max_output_tokens": MAX_OUTPUT_TOKENS,
                                 "temperature_transmitted": False,
                                 "thinking_config_transmitted": False},
            "cache_key": _sha("|".join([STAGE, str(q), _sha(body), prompt_sha,
                                        schema_sha, MODEL, EXECUTION_MODE])),
            "prompt_words": len(body.split()),
        })

    if total != 526:
        problems.append(f"{total} themes rendered, expected 526")
    if len(requests) != 5:
        problems.append(f"{len(requests)} requests, expected 5")
    keys = [r["custom_request_key"] for r in requests]
    if len(set(keys)) != 5:
        problems.append("custom request keys are not unique")
    per_q = {str(r["question"]): r["n_themes"] for r in requests}
    if per_q != {"1": 95, "2": 103, "3": 107, "4": 105, "5": 116}:
        problems.append(f"per-question counts do not reconcile: {per_q}")

    all_ids = [i for r in requests for i in r["expected_raw_theme_ids"]]
    if len(set(all_ids)) != 526:
        problems.append(f"{len(set(all_ids))} unique opaque ids across questions")

    manifest = {
        "built_utc": datetime.now(UTC).isoformat(),
        "stage": STAGE,
        "authorised_scope": "B_CANONICAL_TAXONOMY only; C, D, E1, E2, E3, F1, F2 not run",
        "binding_source": str(_V2.relative_to(_ROOT)),
        "no_api_calls_yet": True,
        "model": MODEL, "execution_mode": EXECUTION_MODE,
        "extractor_is_not_claude": True,
        "n_requests": len(requests),
        "n_themes_total": total, "per_question": per_q,
        "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
        "ordering": {
            "rule": "deterministic content hash over label, description and opaque id",
            "seed": ORDER_SALT,
            "order_hash_algorithm": "sha256",
            "never_grouped_by_condition_first": True,
            "corpus_quantities_shown_to_model": False},
        "blinding": {
            "shown_per_theme": ["raw_theme_id", "label", "description"],
            "not_shown": ["condition", "human/synthetic", "focus group", "replication",
                          "unit_id", "question identifier", "quotations",
                          "deductive codebook", "prior metrics or results"],
            "theme_text_tokens_checked": len(BLIND_TOKENS),
            "structural_tokens_checked": len(STRUCTURAL_BLIND),
            "split_check_rationale": ("theme text is the extractor's own "
                "analytic vocabulary and legitimately contains words like "
                "replicate; only tokens that cannot occur innocuously are "
                "banned there, while the prompt scaffolding takes the full "
                "structural list"),
            "leaks": [p for p in problems if "blinding leak" in p],
            "sealed_mapping": "sealed/stage_b_sealed_raw_theme_mapping.json"},
        "volume_dominance": {
            "synthetic_themes": 442, "human_themes": 84, "ratio": "5.26 to 1",
            "acknowledged": True,
            "corrected_in_stage_b": False,
            "statement": ("the pooled taxonomy is exposed to volume dominance: clusters "
                          "tend to form around wording that recurs most, and synthetic "
                          "wording recurs over five times more often. Stage B does not "
                          "correct this; reweighting here would silently redefine what "
                          "canonical means."),
            "balanced_sensitivity": "E1/E2, separate and future"},
        "embeddings_or_nearest_neighbour_used_for_decisions": False,
        "requests": requests,
        "problems": problems, "pass": not problems,
    }
    return manifest, bodies


def sealed_mapping() -> dict:
    by_q = load_themes()
    rows = []
    for q in QUESTIONS:
        for t in by_q[q]:
            rows.append({"raw_theme_id": t["raw_theme_id"], "question": q,
                         "unit_id": t["_unit_id"], "theme_id": t["_theme_id"],
                         "condition": t["_condition"], "fg": t["_fg"],
                         "canonical_replication_index":
                             t["_canonical_replication_index"],
                         "physical_run": t["_physical_run"],
                         "label": t["label"], "description": t["description"]})
    return {"WARNING": ("SEALED. Maps opaque raw_theme_id to its real provenance. "
                        "Never transmitted to the model."),
            "order_salt": ORDER_SALT, "n_rows": len(rows), "rows": rows}
