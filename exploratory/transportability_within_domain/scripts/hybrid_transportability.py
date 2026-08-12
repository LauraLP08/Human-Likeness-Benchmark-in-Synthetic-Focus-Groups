"""
EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK — S01-S06, questions Q1/Q2/Q4/Q5.

NOT a formal validation. Never pooled numerically with U01-U07/Q3.

Everything below is frozen before any API call: scope, analytic units, the Gemini
configuration (identical to Q3), the Claude audit configuration, the hybrid decision
rules, and the final classification rule.

    py scripts/hybrid_transportability.py --freeze     # Phase 0, offline
    py scripts/hybrid_transportability.py --validate   # Phase 1, offline
    py scripts/hybrid_transportability.py --candidates # Phase 3, offline
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

import emergent_calibration_q3 as cal      # noqa: E402  (frozen Q3 prompt/schema/config)
import cross_model_audit_q3 as cm          # noqa: E402  (frozen Q3 audit rubrics)
import build_transportability_package as pkg   # noqa: E402

CLASSIFICATION = "EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK"

_TR = pkg._DIR
_HY = _TR / "hybrid_evaluation"
_SEALED = pkg._SEAL.parent

UNITS = ["S01", "S02", "S03", "S04", "S05", "S06"]
QUESTION_OF = {"S01": "Q1", "S03": "Q1", "S05": "Q2",
               "S02": "Q4", "S04": "Q4", "S06": "Q5"}
EXPECTED_HUMAN_THEMES = {"S01": 4, "S02": 3, "S03": 2, "S04": 1, "S05": 4, "S06": 4}

# --- Gemini: identical to U01-U07/Q3 -------------------------------------
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_EXECUTION_MODE = "batch"
GEMINI_MAX_OUTPUT_TOKENS = 16384

# --- Claude audit: identical to the Q3 cross-model audit ------------------
AUDITOR_MODEL = cm.AUDITOR_MODEL
AUDITOR_EFFORT = cm.EFFORT
AUDITOR_MAX_OUTPUT_TOKENS = cm.MAX_OUTPUT_TOKENS
REPETITIONS = 2

BLIND_SALT = "hybrid_transportability_v1"

# --- frozen hybrid decision rules ----------------------------------------
CORRESPONDENCE_ACCEPTED = ("SAME_SUBSTANTIVE_THEME",
                           "PARTIAL_OVERLAP_REFERENCE_MORE_SPECIFIC",
                           "PARTIAL_OVERLAP_CANDIDATE_MORE_SPECIFIC")
CORRESPONDENCE_REJECTED = ("RELATED_BUT_DISTINCT", "NO_CORRESPONDENCE")

HYBRID_CONFIRMED_MATCH = "HYBRID_CONFIRMED_MATCH"
HYBRID_UNRESOLVED = "HYBRID_UNRESOLVED"
HYBRID_CORROBORATED_NOVEL = "HYBRID_CORROBORATED_NOVEL"
HYBRID_UNRESOLVED_MACHINE_ONLY = "HYBRID_UNRESOLVED_MACHINE_ONLY"

# --- frozen final classification rule (set before any result exists) ------
FINAL_CLASSES = ("DESCRIPTIVELY_COMPATIBLE_WITH_Q3",
                 "MIXED_OUTSIDE_Q3_PERFORMANCE",
                 "DESCRIPTIVELY_LOWER_THAN_Q3",
                 "UNRESOLVED_DUE_TO_HYBRID_UNCERTAINTY")

Q3_REFERENCE = {"recall": 0.6818, "strict_precision": 0.8000,
                "note": "descriptive comparison only; never a test, never pooled"}

FINAL_RULE = {
    "evaluated_in_order": [
        {"class": "UNRESOLVED_DUE_TO_HYBRID_UNCERTAINTY",
         "when": ("unresolved human themes > 40% of 18, OR the mean per-question "
                  "lower-upper band width > 0.35 — the check cannot say anything")},
        {"class": "DESCRIPTIVELY_LOWER_THAN_Q3",
         "when": ("in at least 3 of the 4 questions the UPPER bound is still below the "
                  "Q3 recall of 0.6818 — even the optimistic reading falls short")},
        {"class": "DESCRIPTIVELY_COMPATIBLE_WITH_Q3",
         "when": ("in every question the band [lower, upper] reaches or exceeds 0.6818, "
                  "AND no unsupported/spurious theme is corroborated in >= 2 units")},
        {"class": "MIXED_OUTSIDE_Q3_PERFORMANCE", "when": "otherwise"},
    ],
    "explicitly_not": ("The choice never depends on whether a single pooled average "
                       "exceeds 0.6818. Per-question results, band width, unresolved "
                       "share and recurrent unsupported themes all enter."),
    "n_caveat": ("Per-question denominators are 6 (Q1), 4 (Q2), 4 (Q4), 4 (Q5). These "
                 "are far too small for any inferential reading; a single theme moves a "
                 "question by 0.17-0.25."),
    "no_pass_fail": "No PASS/FAIL is issued under any branch.",
}


def blind_unit(u: str) -> str:
    return f"extract_{hashlib.sha256(f'{BLIND_SALT}|{u}'.encode()).hexdigest()[:6]}"


def _atomic(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def units() -> dict:
    return {u["blind_unit_id"]: u for u in
            json.loads((_TR / "_units_for_packaging.json").read_text(encoding="utf-8"))}


def human_reference() -> dict:
    return json.loads((_TR / "supplementary_human_reference.json").read_text(
        encoding="utf-8"))


def unit_text(u: str) -> str:
    return "\n".join(units()[u]["lines"])


def gemini_effective_config() -> dict:
    """Identical to Q3 apart from the recorded scope."""
    c = dict(cal.proposed_effective_config())
    c["scope"] = "S01-S06 supplementary transportability"
    c["max_output_tokens"] = GEMINI_MAX_OUTPUT_TOKENS
    return c


def gemini_cache_key(unit: str) -> str:
    text_sha = hashlib.sha256(unit_text(unit).encode("utf-8")).hexdigest()
    blob = "|".join([text_sha, cal.prompt_sha(), cal.response_schema_sha(),
                     GEMINI_MODEL, GEMINI_EXECUTION_MODE,
                     json.dumps(gemini_effective_config(), sort_keys=True)])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Phase 1 — input validation
# ---------------------------------------------------------------------------

def validate_inputs() -> dict:
    U, ref = units(), human_reference()
    audit = json.loads((_SEALED / "transportability_boundary_audit.json").read_text(
        encoding="utf-8"))
    import build_transportability_sample as smp
    problems = []

    per = {}
    for t in ref["themes"]:
        per[t["blind_unit_id"]] = per.get(t["blind_unit_id"], 0) + 1
    for u, n in EXPECTED_HUMAN_THEMES.items():
        if per.get(u, 0) != n:
            problems.append(f"{u}: {per.get(u, 0)} human themes, expected {n}")
    if sum(per.values()) != 18:
        problems.append(f"total human themes {sum(per.values())} != 18")

    for a in audit["units"]:
        u = a["blind_unit_id"]
        if hashlib.sha256(U[u]["text"].encode()).hexdigest() != a["section_text_sha256"]:
            problems.append(f"{u}: unit text hash differs from the sealed audit")

    for u, d in U.items():
        q = d["question"]
        if sum(1 for m in smp.QUESTION_MARKERS[q] if m in d["lines"][0].lower()) \
                < smp.MIN_MARKER_HITS:
            problems.append(f"{u}: own question ask missing")
        if smp.contains_next_question_ask(d["text"], q):
            problems.append(f"{u}: contains the next question's ask")
        for ln in d["lines"]:
            sp = ln.split("] ", 1)[1].split(":", 1)[0]
            if not re.match(r"^(Moderator|Participant \d+)$", sp):
                problems.append(f"{u}: speaker label not blinded ({sp})")

    norm = lambda t: " ".join(str(t).split())
    for t in ref["themes"]:
        if norm(t["supporting_quote"]) not in norm(U[t["blind_unit_id"]]["text"]):
            problems.append(f"{t['source_row_id']}: human quote not literal")

    return {"n_units": len(U), "n_human_themes": sum(per.values()),
            "per_unit": per, "problems": problems, "pass": not problems}


# ---------------------------------------------------------------------------
# Phase 0 — freeze
# ---------------------------------------------------------------------------

def freeze() -> dict:
    v = validate_inputs()
    if not v["pass"]:
        raise RuntimeError(f"inputs do not reconcile: {v['problems']}")
    ref = human_reference()
    man = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "classification": CLASSIFICATION,
        "not_a_validation": ("exploratory only; never pooled numerically with "
                             "U01-U07/Q3 and never a formal validation"),
        "scope": {
            "units": UNITS, "questions": sorted(set(QUESTION_OF.values())),
            "question_of_unit": QUESTION_OF,
            "human_themes_per_unit": EXPECTED_HUMAN_THEMES,
            "n_human_themes": 18,
            "reporting": ("results are reported per unit and per question; any six-unit "
                          "summary is descriptive only and must keep the per-question "
                          "values visible"),
        },
        "analytic_units": {
            "human": "(blind_unit_id, human_theme_id)",
            "machine": "(blind_unit_id, machine_theme_id)",
            "rule": "a local id is never used without its blind_unit_id",
        },
        "gemini": {
            "model": GEMINI_MODEL, "execution_mode": GEMINI_EXECUTION_MODE,
            "prompt_sha256": cal.prompt_sha(),
            "response_schema_sha256": cal.response_schema_sha(),
            "effective_config": gemini_effective_config(),
            "identical_to_q3": True,
            "human_coding_shown_to_model": False,
            "cache_keys": {u: gemini_cache_key(u) for u in UNITS},
        },
        "claude_audit": {
            "model": AUDITOR_MODEL, "execution_mode": "batch",
            "effort": AUDITOR_EFFORT,
            "max_output_tokens": AUDITOR_MAX_OUTPUT_TOKENS,
            "structured_output": "json_schema",
            "repetitions_per_case": REPETITIONS,
            "cache_key_includes_repetition_index": True,
            "blinding": ("sides labelled REFERENCE / CANDIDATE; opaque unit labels; no "
                         "model names, no Q3 results, no benchmark, no experimental "
                         "condition, no provenance"),
            "prompt_sha256": {t: cm.prompt_sha(t) for t in cm.TASKS},
            "status": "USABLE_FOR_CORROBORATION_ONLY",
        },
        "decision_rules": {
            "correspondence_accepted": list(CORRESPONDENCE_ACCEPTED),
            "correspondence_rejected_from_numerators": list(CORRESPONDENCE_REJECTED),
            HYBRID_CONFIRMED_MATCH: [
                "both repetitions give an accepted correspondence category",
                "neither repetition is LOW confidence",
                "every cited quotation is literally verifiable in the unit",
                "no quotation is from the moderator",
                "no unknown ids",
                "no contradiction between the repetitions",
            ],
            HYBRID_UNRESOLVED: ("any disagreement, invalid evidence, LOW confidence or "
                                "conceptually ambiguous case. Counted as neither a "
                                "match nor a confirmed error."),
            HYBRID_CORROBORATED_NOVEL: ("both repetitions VALID_NOVEL_THEME, confidence "
                                        "not LOW, evidence valid"),
            HYBRID_UNRESOLVED_MACHINE_ONLY: "any other machine-only outcome",
            "claude_cannot_declare_human_validated": True,
        },
        "granularity": {
            "derived": ["one human theme -> several machine themes = possible fragmentation",
                        "one machine theme -> several human themes = possible fusion"],
            "categories": list(cm.TASKS["D_GRANULARITY"]),
            "reported_corroborated_only_when": "both repetitions agree and evidence passes",
            "never_alters_numerators_automatically": True,
        },
        "final_classification_rule": FINAL_RULE,
        "q3_reference_for_description_only": Q3_REFERENCE,
        "input_validation": v,
        "protections": ["no human workbook is modified",
                        "supplementary_human_reference.json is read-only",
                        "no human task is created",
                        "no model, prompt or configuration is substituted"],
    }
    _atomic(_HY / "hybrid_manifest.json", man)
    return man


def main() -> int:
    a = sys.argv[1:]
    if "--validate" in a:
        v = validate_inputs()
        print("units:", v["n_units"], "human themes:", v["n_human_themes"])
        print("problems:", v["problems"] or "none")
        print("PHASE 1:", "PASS" if v["pass"] else "STOP")
    elif "--freeze" in a:
        m = freeze()
        print("classification :", m["classification"])
        print("units          :", m["scope"]["units"])
        print("questions      :", m["scope"]["questions"])
        print("human themes   :", m["scope"]["n_human_themes"])
        print("gemini prompt  :", m["gemini"]["prompt_sha256"][:16], "(identical to Q3)")
        print("gemini schema  :", m["gemini"]["response_schema_sha256"][:16])
        print("auditor        :", m["claude_audit"]["model"],
              m["claude_audit"]["effort"], f"x{REPETITIONS}")
        print("frozen -> hybrid_manifest.json")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
