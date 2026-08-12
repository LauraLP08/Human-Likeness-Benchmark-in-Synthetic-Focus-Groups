"""
BLINDED_CROSS_MODEL_LLM_ADJUDICATION — frozen protocol for U01-U07 / Q3.

NOT human validation. NOT a neutral judge. NOT ground truth.
It is a second model's opinion, collected under blinding, and it never converts a
human-anchored result into a validated one.

BLINDING
--------
The auditor never sees: the name of the model that produced the candidate themes; the
enriched / demographics-only / human condition; whether a transcript is synthetic or
human; any aggregate result; the 0.6364 benchmark; the B+ state; or the researcher's
view of overall quality. Unit ids are replaced by opaque blinded labels.

It sees only: a blinded unit id, the unit's full text, the reference theme and its
evidence (where the task has one), the candidate theme and ALL of its evidence, and the
frozen rubric for one task.

The two sides are labelled REFERENCE and CANDIDATE — never "human" and "machine" — so
provenance is not recoverable from the prompt.

FOUR SEPARATE TASKS, NEVER ONE HOLISTIC SCORE
---------------------------------------------
  A PAIRWISE_CORRESPONDENCE      does the candidate express the reference's claim
  B MACHINE_THEME_GROUNDEDNESS   is the candidate supported by the unit's own speech
  C MACHINE_ONLY_STATUS          is an unmatched candidate novel, duplicate, or unsupported
  D GRANULARITY                  is a one-to-many / many-to-one a grain difference

Each judgement returns a category, an ordinal confidence, exact quotes, brief reasoning,
and what information would be needed to decide definitively.

ROBUSTNESS
----------
Every case runs TWICE, independently, with the alternatives rotated and distinct cache
keys per repetition_index. Labels are never averaged. A judgement is
CROSS_MODEL_CORROBORATED only if both repetitions agree, both cite valid evidence, the
verdict does not contradict the human substantive-correspondence rule, and confidence is
not LOW. Otherwise CROSS_MODEL_UNRESOLVED.

    py scripts/cross_model_audit_q3.py --manifest    # offline
    py scripts/cross_model_audit_q3.py --dry-run     # offline, renders prompts
    py scripts/cross_model_audit_q3.py --estimate    # offline cost estimate
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import emergent_calibration_q3 as cal   # noqa: E402

_DIR = cal._DIR

CLASSIFICATION = "BLINDED_CROSS_MODEL_LLM_ADJUDICATION"
NOT_WHAT_IT_IS = ("not human validation", "not a neutral judge", "not ground truth")

AUDITOR_MODEL = "claude-opus-5"
EXECUTION_MODE = "batch"
MAX_OUTPUT_TOKENS = 8192
EFFORT = "high"

# Blinded unit labels — deterministic, opaque, and stable across repetitions.
BLIND_SALT = "cross_model_audit_q3_v1"


def blind_unit(unit_id: str) -> str:
    h = hashlib.sha256(f"{BLIND_SALT}|{unit_id}".encode()).hexdigest()[:6]
    return f"extract_{h}"


CONFIDENCE = ("LOW", "MEDIUM", "HIGH")

TASKS = {
    "A_PAIRWISE_CORRESPONDENCE": (
        "SAME_SUBSTANTIVE_THEME",
        "PARTIAL_OVERLAP_REFERENCE_MORE_SPECIFIC",
        "PARTIAL_OVERLAP_CANDIDATE_MORE_SPECIFIC",
        "RELATED_BUT_DISTINCT",
        "NO_CORRESPONDENCE",
        "UNCERTAIN",
    ),
    "B_CANDIDATE_GROUNDEDNESS": (
        "FULLY_SUPPORTED",
        "PARTIALLY_SUPPORTED_OR_OVERBROAD",
        "UNSUPPORTED",
        "UNCERTAIN",
    ),
    "C_UNMATCHED_CANDIDATE_STATUS": (
        "VALID_NOVEL_THEME",
        "DUPLICATE_CANDIDATE_THEME",
        "UNSUPPORTED_OR_SPURIOUS",
        "UNCERTAIN",
    ),
    "D_GRANULARITY": (
        "LEGITIMATE_GRANULARITY_DIFFERENCE",
        "POSSIBLE_OVER_FRAGMENTATION",
        "POSSIBLE_OVER_MERGING",
        "SUBSTANTIVE_MISMATCH",
        "UNCERTAIN",
    ),
}

# The category names the researcher approved use HUMAN_MORE_SPECIFIC / MACHINE_MORE_
# SPECIFIC. Those words would unblind the sides, so the prompt uses REFERENCE / CANDIDATE
# and results are mapped back on import.
CATEGORY_ALIASES = {
    "PARTIAL_OVERLAP_REFERENCE_MORE_SPECIFIC": "PARTIAL_OVERLAP_HUMAN_MORE_SPECIFIC",
    "PARTIAL_OVERLAP_CANDIDATE_MORE_SPECIFIC": "PARTIAL_OVERLAP_MACHINE_MORE_SPECIFIC",
    "DUPLICATE_CANDIDATE_THEME": "DUPLICATE_MACHINE_THEME",
}

SHARED_RUBRIC = """\
You are comparing themes identified in one short extract from a group discussion.

Work only from the extract in front of you. You have no predefined category list and
are not matching against one. You do not know where this extract came from, who produced either theme, or
how any other extract was judged. Do not speculate about any of that.

TWO SIDES

  REFERENCE theme - a theme recorded for this extract, with its evidence.
  CANDIDATE theme - a separate theme proposed for the same extract, with all of its
                    evidence.

Judge them on the substance of the claim each one makes. Do NOT judge by:
  * how similar the two labels look;
  * how many quotations each side cites. The two sides were produced under different
    conventions and their quote counts are not comparable. Quotes tell you whether a
    claim is grounded in the extract, nothing more.

EVIDENCE RULES

  * Every quotation you give must be copied verbatim from the extract.
  * Attribute each quotation to the turn it appears in.
  * Never quote the moderator. The moderator's questions and summaries are not evidence
    of what the group thinks.

CONFIDENCE

  HIGH   - the extract settles it.
  MEDIUM - the reading is well supported but another is defensible.
  LOW    - you are genuinely unsure.

Use LOW when you mean it. A LOW judgement is treated as unresolved, which is the correct
outcome when the extract does not settle the question.

BLOCKING INFORMATION

State what you would need in order to decide definitively. If nothing is missing and the
extract settles it, say so explicitly.

Return JSON only, matching the schema you are given. No commentary.
"""

TASK_RUBRICS = {
    "A_PAIRWISE_CORRESPONDENCE": """\
TASK: Do the REFERENCE theme and the CANDIDATE theme express the same substantive claim?

  SAME_SUBSTANTIVE_THEME
      They assert the same thing about the same matter, however differently worded.
  PARTIAL_OVERLAP_REFERENCE_MORE_SPECIFIC
      Overlapping, but the REFERENCE makes a narrower or more specific claim that the
      CANDIDATE does not carry.
  PARTIAL_OVERLAP_CANDIDATE_MORE_SPECIFIC
      Overlapping, but the CANDIDATE makes a narrower or more specific claim that the
      REFERENCE does not carry.
  RELATED_BUT_DISTINCT
      Same topic, different claims. Asserting something and denying it are two themes,
      not one, however similar the wording.
  NO_CORRESPONDENCE
      They are about different things.
  UNCERTAIN
      The extract permits more than one reasonable reading.

A broad theme on one side matched by a narrower one on the other is a PARTIAL_OVERLAP,
not a failure.
""",
    "B_CANDIDATE_GROUNDEDNESS": """\
TASK: Is the CANDIDATE theme supported by what participants actually say in this extract?

  FULLY_SUPPORTED
      Participant speech in this extract states or clearly implies the claim.
  PARTIALLY_SUPPORTED_OR_OVERBROAD
      Something in the extract points this way, but the claim reaches further than the
      speech supports - for example it generalises a single passing remark into a
      substantive position.
  UNSUPPORTED
      The extract does not support it, or contradicts it, or the claim invents a
      relationship, an actor, or a position nobody takes.
  UNCERTAIN
      You cannot tell from this extract.

Judge only the claim against the speech. Do not judge whether the theme is interesting,
well worded, or worth reporting.
""",
    "C_UNMATCHED_CANDIDATE_STATUS": """\
TASK: A CANDIDATE theme has no counterpart among the reference themes recorded for this
extract. All of those reference themes are listed for you.

  VALID_NOVEL_THEME
      Clearly supported by the extract AND a distinct thematic idea that none of the
      listed reference themes states.
  DUPLICATE_CANDIDATE_THEME
      It restates another CANDIDATE theme for the same extract - the same claim twice.
  UNSUPPORTED_OR_SPURIOUS
      Not sufficiently supported by the extract, or it contradicts the extract, or it
      turns an incidental mention into a substantive thematic claim.
  UNCERTAIN
      The extract permits more than one reasonable reading.

Absence from the reference list is NOT by itself evidence of a fault. The reference list
may simply be incomplete.
""",
    "D_GRANULARITY": """\
TASK: One theme on one side has been linked to SEVERAL themes on the other. Judge what
that relationship is.

  LEGITIMATE_GRANULARITY_DIFFERENCE
      Both sides carve up the same material, one at a finer grain. A broad theme
      decomposed into its distinct mechanisms is legitimate.
  POSSIBLE_OVER_FRAGMENTATION
      One coherent claim has been split into pieces that are not really separate claims.
  POSSIBLE_OVER_MERGING
      Genuinely distinct claims have been collapsed into one.
  SUBSTANTIVE_MISMATCH
      The themes linked together are not about the same claim at all.
  UNCERTAIN
      The extract permits more than one reasonable reading.

A difference in grain is not a fault by default. Say SUBSTANTIVE_MISMATCH only when the
claims genuinely differ.
""",
}

FORBIDDEN_IN_PROMPT = (
    "gemini", "claude", "anthropic", "google", "openai", "gpt", "llm", "model name",
    "enriched", "demographics-only", "demographics only", "synthetic", "simulated",
    "human transcript", "focus group", "macho", "0.6364", "benchmark", "b+", "recall",
    "precision", "f1", "tier 1", "codebook", "dissertation", "researcher",
    "u01", "u02", "u03", "u04", "u05", "u06", "u07", "q3", "fg1", "fg2", "fg3",
    "fg4", "fg5", "run01", "run02", "run03", "coder a", "coder b",
)


def _schema(categories) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "confidence", "quotations", "reasoning",
                     "information_that_would_settle_it"],
        "properties": {
            "category": {"type": "string", "enum": list(categories)},
            "confidence": {"type": "string", "enum": list(CONFIDENCE)},
            "quotations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["turn_id", "speaker", "quote"],
                    "properties": {
                        "turn_id": {"type": "string"},
                        "speaker": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                },
            },
            "reasoning": {"type": "string"},
            "information_that_would_settle_it": {"type": "string"},
        },
    }


def task_schema(task: str) -> dict:
    return _schema(TASKS[task])


def prompt_for(task: str) -> str:
    return SHARED_RUBRIC + "\n" + TASK_RUBRICS[task]


def prompt_sha(task: str) -> str:
    return hashlib.sha256(prompt_for(task).encode("utf-8")).hexdigest()


def schema_sha(task: str) -> str:
    return hashlib.sha256(json.dumps(task_schema(task), sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def effective_config() -> dict:
    """Every parameter transmitted. Anything absent here is not sent."""
    return {
        "task": "cross_model_adjudication",
        "model": AUDITOR_MODEL,
        "execution_mode": EXECUTION_MODE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "effort": EFFORT,
        "thinking": "adaptive_default_not_transmitted",
        "temperature_transmitted": False,
        "top_p_transmitted": False,
        "top_k_transmitted": False,
        "output_config_format": "json_schema",
        "protocol_version": "cross_model_audit_q3_v1",
    }


def cache_key(task: str, case_id: str, repetition_index: int,
              rendered_sha: str) -> str:
    """
    Distinct per repetition BY CONSTRUCTION — repetition_index is part of the key, so a
    second repetition can never be served from the first one's cache.
    """
    blob = "|".join([task, case_id, str(repetition_index), rendered_sha,
                     prompt_sha(task), schema_sha(task),
                     json.dumps(effective_config(), sort_keys=True)])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def prompt_purity_problems(text: str = None) -> list[str]:
    """Word-boundary matched, so 'model' inside 'modelling' does not fire."""
    if text is None:
        text = "\n".join([SHARED_RUBRIC] + list(TASK_RUBRICS.values()))
    low = " ".join(text.split()).lower()
    bad = []
    for term in FORBIDDEN_IN_PROMPT:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low):
            bad.append(term)
    return sorted(set(bad))


# ---------------------------------------------------------------------------
# Case construction
# ---------------------------------------------------------------------------

def _load():
    d = json.loads((_DIR / "matching_derivation_q3.json").read_text(encoding="utf-8"))
    b = json.loads((_DIR / "bplus_evaluation_q3.json").read_text(encoding="utf-8"))
    res = json.loads((_DIR / "extraction_results_q3.json").read_text(encoding="utf-8"))
    ref = json.loads((_DIR / "human_reference_q3.json").read_text(encoding="utf-8"))
    themes = {cal.machine_key(u["unit_id"], t["machine_theme_id"]): t
              for u in res["results"] for t in u["themes"]}
    humans = {h["human_key"]: h for h in ref["union_reference"]}
    return d, b, themes, humans


def _ref_block(h) -> dict:
    return {"label": h["cluster_label"],
            "description": h.get("consolidated_definition", ""),
            "evidence": [q["quote"] for q in h.get("supporting_quotes", [])]}


def _cand_block(t) -> dict:
    return {"label": t["label"], "description": t["one_sentence_description"],
            "evidence": [{"turn_id": e["turn_id"], "speaker": e.get("speaker", ""),
                          "quote": e["quote"]} for e in (t.get("evidence") or [])]}


def build_cases() -> dict:
    d, b, themes, humans = _load()
    rows = {r["human_key"]: r for r in d["rows"]}
    pending, calibration = [], []

    # --- A: every candidate named on an unresolved row ---------------------
    for u in d["uncertain_rows"]:
        for mk in u["candidate_machine_keys"]:
            pending.append({
                "case_id": f"A::{u['human_key']}::{mk}",
                "task": "A_PAIRWISE_CORRESPONDENCE",
                "unit_id": u["unit_id"],
                "reference": _ref_block(humans[u["human_key"]]),
                "candidate": _cand_block(themes[mk]),
                "provenance": {"human_key": u["human_key"], "machine_key": mk},
            })

    # --- B: groundedness of every candidate involved in a pending case -----
    involved = sorted({c["provenance"]["machine_key"] for c in pending}
                      | set(d["unconfirmed_theme_taxonomy"]["PURE_MACHINE_ONLY"])
                      | {x["machine_key"] for x in b["granularity_audit"]["many_to_one"]
                         if x["classification"] == "UNCERTAIN"})
    for mk in involved:
        pending.append({
            "case_id": f"B::{mk}", "task": "B_CANDIDATE_GROUNDEDNESS",
            "unit_id": mk.split("::")[0], "reference": None,
            "candidate": _cand_block(themes[mk]),
            "provenance": {"machine_key": mk},
        })

    # --- C: pure machine-only themes only ----------------------------------
    for mk in d["unconfirmed_theme_taxonomy"]["PURE_MACHINE_ONLY"]:
        unit = mk.split("::")[0]
        pending.append({
            "case_id": f"C::{mk}", "task": "C_UNMATCHED_CANDIDATE_STATUS",
            "unit_id": unit, "reference": None,
            "candidate": _cand_block(themes[mk]),
            "reference_inventory": [_ref_block(h) for k, h in humans.items()
                                    if k.startswith(unit + "::")],
            "sibling_candidates": [_cand_block(themes[k]) for k in sorted(themes)
                                   if k.startswith(unit + "::") and k != mk],
            "provenance": {"machine_key": mk},
        })

    # --- D: granularity cases the provisional pass left UNCERTAIN ----------
    for x in b["granularity_audit"]["one_to_many"]:
        if x["classification"] == "UNCERTAIN":
            pending.append({
                "case_id": f"D::{x['human_key']}", "task": "D_GRANULARITY",
                "unit_id": x["human_key"].split("::")[0],
                "reference": _ref_block(humans[x["human_key"]]),
                "candidate": None,
                "candidate_group": [_cand_block(themes[k]) for k in x["machine_keys"]],
                "provenance": {"human_key": x["human_key"],
                               "machine_keys": x["machine_keys"]},
            })
    for x in b["granularity_audit"]["many_to_one"]:
        if x["classification"] == "UNCERTAIN":
            mk = x["machine_key"]
            pending.append({
                "case_id": f"D::{mk}", "task": "D_GRANULARITY",
                "unit_id": mk.split("::")[0],
                "reference": None,
                "reference_group": [_ref_block(humans[h]) for h in x["human_keys"]],
                "candidate": _cand_block(themes[mk]),
                "provenance": {"machine_key": mk, "human_keys": x["human_keys"]},
            })

    # --- calibration: stratified over cases the researcher already settled -
    def _take(pred, n, stratum):
        out = []
        for hk in sorted(rows):
            if len(out) >= n:
                break
            r = rows[hk]
            if pred(r):
                mk = r["confirmed_machine_keys"][0] if r["confirmed_machine_keys"] else None
                out.append({
                    "case_id": f"CAL::{stratum}::{hk}",
                    "task": "A_PAIRWISE_CORRESPONDENCE",
                    "stratum": stratum,
                    "unit_id": r["unit_id"],
                    "reference": _ref_block(humans[hk]),
                    "candidate": _cand_block(themes[mk]) if mk else None,
                    "provenance": {"human_key": hk, "machine_key": mk},
                    "human_decision_WITHHELD_FROM_PROMPT": r["decision"],
                    "human_relation_WITHHELD_FROM_PROMPT": r["relation"],
                })
        return out

    fus = {x["machine_key"] for x in b["granularity_audit"]["many_to_one"]
           if x["classification"] != "UNCERTAIN"}
    calibration += _take(lambda r: r["relation"] == "one_to_one", 4, "MATCHED_one_to_one")
    calibration += _take(lambda r: r["decision"] == "NO_MATCH_HUMAN_ONLY", 4,
                         "NO_MATCH_HUMAN_ONLY")
    calibration += _take(lambda r: r["relation"] == "one_to_many"
                         and f"D::{r['human_key']}" not in
                         {c["case_id"] for c in pending}, 3, "one_to_many")
    calibration += [{
        "case_id": f"CAL::many_to_one::{mk}", "task": "A_PAIRWISE_CORRESPONDENCE",
        "stratum": "many_to_one", "unit_id": mk.split("::")[0],
        "reference": _ref_block(humans[sorted(
            x for x in b["granularity_audit"]["many_to_one"]
            if x["machine_key"] == mk)[0]["human_keys"][0]]),
        "candidate": _cand_block(themes[mk]),
        "provenance": {"machine_key": mk},
        "human_decision_WITHHELD_FROM_PROMPT": "MATCHED",
        "human_relation_WITHHELD_FROM_PROMPT": "many_to_one",
    } for mk in sorted(fus)[:3]]

    # NO_MATCH_HUMAN_ONLY calibration rows have no confirmed key: pair each with the
    # nearest available candidate from its own unit so the judge has two sides to
    # compare. The human verdict stays hidden.
    for c in calibration:
        if c["candidate"] is None:
            unit = c["unit_id"]
            sib = [k for k in sorted(themes) if k.startswith(unit + "::")]
            c["candidate"] = _cand_block(themes[sib[0]])
            c["provenance"]["machine_key"] = sib[0]

    return {"pending": pending, "calibration": calibration}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(case: dict, repetition_index: int) -> str:
    """
    The user-turn content. Alternatives are rotated by repetition_index so a second
    reading cannot be anchored by the first ordering.
    """
    unit = case["unit_id"]
    lines = cal.unit_lines(unit)
    parts = [f"BLINDED EXTRACT ID: {blind_unit(unit)}", "", "EXTRACT", ""]
    parts += lines
    parts += ["", "-" * 60, ""]

    def block(title, b):
        out = [title, f"  label       : {b['label']}",
               f"  description : {b['description']}", "  evidence    :"]
        ev = b["evidence"]
        if repetition_index % 2 == 1:
            ev = list(reversed(ev))
        for e in ev:
            if isinstance(e, dict):
                out.append(f"    [{e['turn_id']}] {e['speaker']}: \"{e['quote']}\"")
            else:
                out.append(f"    \"{e}\"")
        return out

    sections = []
    if case.get("reference"):
        sections.append(("REFERENCE THEME", case["reference"]))
    if case.get("candidate"):
        sections.append(("CANDIDATE THEME", case["candidate"]))
    if repetition_index % 2 == 1:
        sections = list(reversed(sections))
    for title, b in sections:
        parts += block(title, b) + [""]

    for key, title in (("reference_group", "REFERENCE THEMES (the group)"),
                       ("candidate_group", "CANDIDATE THEMES (the group)"),
                       ("reference_inventory", "ALL REFERENCE THEMES FOR THIS EXTRACT"),
                       ("sibling_candidates", "OTHER CANDIDATE THEMES FOR THIS EXTRACT")):
        if case.get(key):
            group = list(case[key])
            if repetition_index % 2 == 1:
                group = list(reversed(group))
            parts.append(title)
            for b in group:
                parts += block("  -", b)
            parts.append("")
    return "\n".join(parts)


def render_problems(case: dict, repetition_index: int) -> list[str]:
    """The rendered prompt must leak nothing, including the real unit id."""
    text = render(case, repetition_index)
    bad = prompt_purity_problems(text)
    if case["unit_id"] in text:
        bad.append(f"real unit id {case['unit_id']} present")
    if blind_unit(case["unit_id"]) not in text:
        bad.append("blinded unit id missing")
    return sorted(set(bad))


def build_manifest() -> dict:
    cases = build_cases()
    requests = []
    for group in ("calibration", "pending"):
        for c in cases[group]:
            for rep in (1, 2):
                problems = render_problems(c, rep)
                if problems:
                    raise RuntimeError(f"{c['case_id']} rep{rep}: {problems}")
                text = render(c, rep)
                rsha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                requests.append({
                    "custom_request_key": f"{c['case_id']}|rep{rep}",
                    "group": group, "task": c["task"], "case_id": c["case_id"],
                    "repetition_index": rep,
                    "blinded_unit": blind_unit(c["unit_id"]),
                    "rendered_sha256": rsha,
                    "rendered_chars": len(text),
                    "cache_key": cache_key(c["task"], c["case_id"], rep, rsha),
                    "provenance_NOT_SENT": c.get("provenance", {}),
                })
    keys = [r["cache_key"] for r in requests]
    if len(set(keys)) != len(keys):
        raise RuntimeError("duplicate cache keys")

    # DISCLOSED LIMITATION. Rotation reorders the alternatives presented to the auditor.
    # A case with a single section and a single quotation has nothing to reorder, so its
    # two repetitions carry an identical prompt and differ only by the model's own
    # sampling. They are still two independent calls with distinct cache keys — but the
    # anchoring control does not apply to them, and that is stated rather than implied.
    flat = sorted({c["case_id"] for group in ("calibration", "pending")
                   for c in cases[group]
                   if render(c, 1) == render(c, 2)})
    man = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": CLASSIFICATION,
        "what_this_is_not": list(NOT_WHAT_IT_IS),
        "auditor_model": AUDITOR_MODEL,
        "effective_config": effective_config(),
        "prompt_sha256": {t: prompt_sha(t) for t in TASKS},
        "schema_sha256": {t: schema_sha(t) for t in TASKS},
        "category_aliases_applied_on_import": CATEGORY_ALIASES,
        "n_cases": len(cases["calibration"]) + len(cases["pending"]),
        "n_requests": len(requests),
        "repetitions_per_case": 2,
        "rotation": {
            "rule": "alternatives are reordered on repetition_index 2",
            "n_cases_rotated": (len(cases["calibration"]) + len(cases["pending"])
                                - len(flat)),
            "n_cases_with_nothing_to_rotate": len(flat),
            "cases_with_nothing_to_rotate": flat,
            "note": ("These carry one section and one quotation, so no ordering exists "
                     "to vary. Their repetitions remain independent calls with distinct "
                     "cache keys, but the anti-anchoring control does not apply."),
        },
        "requests": requests,
        "cases": cases,
    }
    dst = _DIR / "cross_model_manifest_q3.json"
    tmp = dst.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    return man


# ---------------------------------------------------------------------------
# Corroboration
# ---------------------------------------------------------------------------

CORROBORATED = "CROSS_MODEL_CORROBORATED"
UNRESOLVED = "CROSS_MODEL_UNRESOLVED"


def corroborate(rep1: dict, rep2: dict, unit_lines: list[str]) -> dict:
    """Both repetitions must agree, cite real evidence, and not be LOW."""
    reasons = []
    if rep1["category"] != rep2["category"]:
        reasons.append(f"repetitions disagree: {rep1['category']} vs {rep2['category']}")
    if "LOW" in (rep1["confidence"], rep2["confidence"]):
        reasons.append("confidence is LOW in at least one repetition")

    turns = {}
    for ln in unit_lines:
        m = re.match(r"^\[(T\d+)\]\s+([^:]+):\s*(.*)$", ln, re.S)
        if m:
            turns[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    norm = lambda t: " ".join(str(t).split())
    for n, rep in ((1, rep1), (2, rep2)):
        if not rep.get("quotations"):
            reasons.append(f"repetition {n} cited no evidence")
        for q in rep.get("quotations", []):
            if q["turn_id"] not in turns:
                reasons.append(f"repetition {n}: unknown turn {q['turn_id']}")
                continue
            speaker, body = turns[q["turn_id"]]
            if speaker.lower().startswith("moderator"):
                reasons.append(f"repetition {n}: quotes the moderator")
            if norm(q["quote"]) not in norm(body):
                reasons.append(f"repetition {n}: quote not verbatim in {q['turn_id']}")

    return {
        "status": CORROBORATED if not reasons else UNRESOLVED,
        "category": rep1["category"] if not reasons else None,
        "reasons": reasons,
        "note": ("Labels are never averaged. A CORROBORATED result is still a second "
                 "model's opinion and never converts a human-anchored finding into a "
                 "validated one."),
    }


def main() -> int:
    a = sys.argv[1:]
    if "--manifest" in a or "--dry-run" in a or "--estimate" in a:
        man = build_manifest()
        print(f"classification : {man['classification']}")
        print(f"auditor model  : {man['auditor_model']}  ({EXECUTION_MODE})")
        print(f"cases          : {man['n_cases']}")
        print(f"requests       : {man['n_requests']}  (2 repetitions each)")
        print(f"prompt purity  : {prompt_purity_problems() or 'clean'}")
        by = {}
        for r in man["requests"]:
            by[(r["group"], r["task"])] = by.get((r["group"], r["task"]), 0) + 1
        for k in sorted(by):
            print(f"   {k[0]:12s} {k[1]:32s} {by[k]:>3} requests")
        if "--dry-run" in a:
            c = man["cases"]["pending"][0]
            print("\n--- rendered prompt, first pending case, repetition 1 ---")
            print(render(c, 1)[:1400])
        if "--estimate" in a:
            chars = sum(r["rendered_chars"] for r in man["requests"])
            rub = sum(len(prompt_for(r["task"])) for r in man["requests"])
            tin = (chars + rub) / 4
            tout = man["n_requests"] * 700
            std = tin / 1e6 * 5 + tout / 1e6 * 25
            print(f"\nestimated input tokens  : {tin:,.0f}  (~4 chars/token)")
            print(f"estimated output tokens : {tout:,.0f}  (~700/judgement)")
            print(f"standard cost           : ${std:,.2f}")
            print(f"batch cost (50%)        : ${std / 2:,.2f}")
        print("\nNOT SUBMITTED. No Claude API call has been made.")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
