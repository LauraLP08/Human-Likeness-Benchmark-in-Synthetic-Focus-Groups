"""
Phase A revalidation under a FROZEN theme-level and quote-level policy.

    py scripts/phase_a_revalidation.py

Reads the 174 raw responses WITHOUT modifying them and re-decides every quote and every
theme under one written policy. Produces new artefacts; overwrites no history.

FROZEN QUOTE POLICY
-------------------
A quote is valid only if it is:
  * a CONTIGUOUS substring — no internal elision, no joined passages;
  * located ENTIRELY within the turn_id it names;
  * attributed to the speaker who actually holds that turn;
  * spoken by a participant, never the moderator;
  * free of paraphrase and inserted words.

Normalisation is permitted and is limited to: Unicode NFKC, curly-to-straight quotation
marks, en/em dash to hyphen, ellipsis character to three dots, whitespace collapse and
case. Normalisation NEVER bridges an elision: a contiguous-substring test after
normalisation still fails on any omitted word.

FROZEN THEME POLICY
-------------------
  * keep only the valid quotes;
  * every invalid quote is moved to the rejected-quote audit, never deleted;
  * a theme is ACCEPTED if at least one valid quote survives;
  * a theme with no valid quote is EVIDENCE_REPAIR_REQUIRED;
  * an extra invalid quote NEVER removes a theme that keeps another valid quote;
  * a unit is COMPLETE only when every one of its themes is accepted or has an explicit
    resolution recorded after repair.

NO API CALLS in this module.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa   # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/inductive_phase_a"
_RAW = _OUT / "phase_a_raw_responses.json"
_MANIFEST = _OUT / "phase_a_manifest.json"

POLICY_ID = "PHASE_A_QUOTE_AND_THEME_VALIDATION_V1"

# The metric is named for what it measures. It permits normalisation, so calling it
# "character exact" would overstate it; the raw byte-exact count is kept beside it as a
# separate diagnostic so the difference between the two is always visible.
METRIC_NAME = "normalized_contiguous_quote"
DIAGNOSTIC_METRIC = "raw_exact_contiguous_quote"

AUTHORITATIVE_TEXT = ("the exact rendering presented to the extractor, reconstructed "
                      "deterministically and verified against rendered_sha256")
NORMALISATION = ("NFKC", "curly quotes to straight", "en/em dash to hyphen",
                 "ellipsis to three dots", "whitespace collapse", "case")

THEME_ACCEPTED = "ACCEPTED"
THEME_REPAIR = "EVIDENCE_REPAIR_REQUIRED"

Q_VALID = "VALID"
Q_TURN_NOT_IN_UNIT = "TURN_ID_NOT_IN_UNIT"
Q_NOT_CONTIGUOUS = "NOT_CONTIGUOUS_IN_NAMED_TURN"
Q_SPEAKER_MISMATCH = "SPEAKER_MISMATCH"
Q_MODERATOR = "MODERATOR_QUOTE"
Q_EMPTY = "EMPTY_QUOTE"


def _raw_contiguous(quote: str, turns: dict, turn_id: str) -> bool:
    """Byte-exact contiguous match. Diagnostic only; never decides a verdict."""
    return any(quote and quote in u["text"] for u in (turns.get(turn_id) or []))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-").replace("…", "..."))
    return re.sub(r"\s+", " ", s).strip().lower()


def classify_quote(q: dict, turns: dict) -> dict:
    """One quote, one verdict, with the evidence for it."""
    tid = (q.get("turn_id") or "").strip()
    spk = (q.get("speaker") or "").strip()
    text = q.get("quote") or ""
    if not text.strip():
        return {"verdict": Q_EMPTY, "turn_id": tid, "speaker": spk, "quote": text}
    us = turns.get(tid)
    if us is None:
        return {"verdict": Q_TURN_NOT_IN_UNIT, "turn_id": tid, "speaker": spk,
                "quote": text}
    nq = _norm(text)
    hit = next((u for u in us if nq and nq in _norm(u["text"])), None)
    if hit is None:
        return {"verdict": Q_NOT_CONTIGUOUS, "turn_id": tid, "speaker": spk,
                "quote": text,
                "turn_text": (us[0]["text"] if us else "")[:400]}
    if hit["is_moderator"] or _norm(spk) == "moderator":
        return {"verdict": Q_MODERATOR, "turn_id": tid, "speaker": spk, "quote": text}
    if spk and _norm(spk) != _norm(hit["speaker"]):
        return {"verdict": Q_SPEAKER_MISMATCH, "turn_id": tid, "speaker": spk,
                "actual_speaker": hit["speaker"], "quote": text}
    return {"verdict": Q_VALID, "turn_id": tid, "speaker": hit["speaker"],
            "quote": text}


def revalidate() -> dict:
    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(_RAW.read_text(encoding="utf-8"))
    _, renders = pa.build_manifest()
    by_key = {r["custom_request_key"]: r for r in man["requests"]}

    units, rejected, repairs = [], [], []
    n_themes = n_all_valid = n_mixed = n_none = 0
    n_quotes = n_raw_exact = 0
    qcounts = Counter()

    for r in sorted(raw["responses"], key=lambda x: x["custom_request_key"]):
        meta = by_key[r["custom_request_key"]]
        uid = meta["unit_id"]
        turns = renders[uid]["turns"]
        parsed = json.loads(r["raw_text"]) if r.get("raw_text") else {}
        themes_out = []
        for t in parsed.get("themes") or []:
            n_themes += 1
            kept, dropped = [], []
            for q in t.get("quotes") or []:
                n_quotes += 1
                c = classify_quote(q, turns)
                c["raw_exact_contiguous"] = _raw_contiguous(
                    q.get("quote") or "", turns, (q.get("turn_id") or "").strip())
                n_raw_exact += int(c["raw_exact_contiguous"])
                qcounts[c["verdict"]] += 1
                if c["verdict"] == Q_VALID:
                    kept.append(c)
                else:
                    dropped.append(c)
                    rejected.append({"unit_id": uid, "theme_id": t.get("theme_id"),
                                     **c})
            status = THEME_ACCEPTED if kept else THEME_REPAIR
            if kept and not dropped:
                n_all_valid += 1
            elif kept and dropped:
                n_mixed += 1
            else:
                n_none += 1
            rec = {"theme_id": t.get("theme_id"), "label": t.get("label"),
                   "description": t.get("description"),
                   "descriptive_prominence": t.get("descriptive_prominence"),
                   "status": status,
                   "n_valid_quotes": len(kept), "n_invalid_quotes": len(dropped),
                   "valid_quotes": kept}
            themes_out.append(rec)
            if status == THEME_REPAIR:
                repairs.append({"unit_id": uid, "theme_id": t.get("theme_id"),
                                "label": t.get("label"),
                                "description": t.get("description"),
                                "n_invalid_quotes": len(dropped)})

        needs = [t for t in themes_out if t["status"] == THEME_REPAIR]
        units.append({
            **{k: meta[k] for k in ("unit_id", "question", "condition", "fg",
                                    "canonical_replication_index", "physical_run",
                                    "length_tercile")},
            "n_themes": len(themes_out),
            "n_themes_accepted": len(themes_out) - len(needs),
            "n_themes_requiring_repair": len(needs),
            "unit_status": "COMPLETE" if not needs else "REPAIR_REQUIRED",
            "themes": themes_out,
        })

    complete = [u for u in units if u["unit_status"] == "COMPLETE"]
    repair_units = [u for u in units if u["unit_status"] == "REPAIR_REQUIRED"]

    return {
        "revalidated_utc": datetime.now(UTC).isoformat(),
        "policy_id": POLICY_ID,
        "metric_name": METRIC_NAME,
        "metric_is_not": "character_exact_quote",
        "authoritative_text": AUTHORITATIVE_TEXT,
        "diagnostic_metric": DIAGNOSTIC_METRIC,
        "n_quotes_raw_exact_contiguous": None,
        "normalisation_permitted": list(NORMALISATION),
        "normalisation_never_bridges_elision": True,
        "raw_responses_modified": False,
        "n_units": len(units),
        "n_themes": n_themes,
        "themes_all_quotes_valid": n_all_valid,
        "themes_mixed_valid_and_invalid": n_mixed,
        "themes_no_valid_quote": n_none,
        "n_quotes": n_quotes,
        "quote_verdicts": dict(qcounts),
        "raw_exact_diagnostic": {
            "metric": DIAGNOSTIC_METRIC,
            "n_raw_exact_contiguous": n_raw_exact,
            "n_normalized_contiguous": qcounts.get(Q_VALID, 0),
            "difference_absorbed_by_normalisation":
                qcounts.get(Q_VALID, 0) - n_raw_exact,
            "note": ("the gap is quotes that match only after NFKC, whitespace, "
                     "quotation-mark, dash, ellipsis or case normalisation; it is "
                     "reported, never hidden")},
        "n_units_complete": len(complete),
        "n_units_requiring_repair": len(repair_units),
        "units": units,
        "rejected_quotes": rejected,
        "repairs": repairs,
    }


# ---------------------------------------------------------------- artefacts
EXPECTED = {"n_themes": 526, "themes_all_quotes_valid": 276,
            "themes_mixed_valid_and_invalid": 214, "themes_no_valid_quote": 36,
            "n_units_complete": 146, "n_units_requiring_repair": 28}


def _atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    import os
    os.replace(tmp, path)


def build_repair_manifest(b: dict) -> dict:
    """
    One request per theme that kept no valid quote. DERIVED from the revalidation, never
    hard-coded to an expected count. Built but NOT submitted.
    """
    _, renders = pa.build_manifest()
    reqs = []
    for r in b["repairs"]:
        uid = r["unit_id"]
        body = renders[uid]["body"]
        theme_sha = pa._sha(f"{r['theme_id']}|{r['label']}|{r['description']}")
        reqs.append({
            "custom_request_key": f"par::{uid}::{r['theme_id']}",
            "execution_stage": "PHASE_A_EVIDENCE_REPAIR",
            "unit_id": uid, "theme_id": r["theme_id"],
            "label": r["label"], "description": r["description"],
            "unit_text_sha256": pa._sha(body),
            "theme_sha256": theme_sha,
            "prompt_sha256": pa._sha(REPAIR_PROMPT),
            "schema_sha256": pa._sha(json.dumps(REPAIR_SCHEMA, sort_keys=True)),
            "model": pa.MODEL, "execution_mode": pa.EXECUTION_MODE,
            "cache_key": pa._sha("|".join([
                "PHASE_A_EVIDENCE_REPAIR", uid, str(r["theme_id"]), theme_sha,
                pa._sha(body), pa._sha(REPAIR_PROMPT),
                pa._sha(json.dumps(REPAIR_SCHEMA, sort_keys=True)),
                pa.MODEL, pa.EXECUTION_MODE])),
        })
    keys = [x["custom_request_key"] for x in reqs]
    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "execution_stage": "PHASE_A_EVIDENCE_REPAIR",
        "submitted": False,
        "authorisation": "NOT SUBMITTED — awaiting resolution of the count discrepancy",
        "task": "evidence repair only; NO new open thematic extraction",
        "model": pa.MODEL, "execution_mode": pa.EXECUTION_MODE,
        "codebook_shown": False,
        "segmented_units_changed": False,
        "n_requests": len(reqs),
        "n_units": len({x["unit_id"] for x in reqs}),
        "unique_keys": len(set(keys)) == len(keys),
        "prompt": REPAIR_PROMPT,
        "schema": REPAIR_SCHEMA,
        "requests": reqs,
        "derived_not_hardcoded": ("request count comes from the revalidation's "
                                  "EVIDENCE_REPAIR_REQUIRED themes"),
    }


REPAIR_PROMPT = (
    "A supporting quotation must be one contiguous substring copied exactly from a "
    "single participant turn. Do not omit words from the middle, join separate "
    "passages, alter punctuation, repair grammar or paraphrase. If no exact contiguous "
    "participant quotation supports the theme, return NOT_SUPPORTED_IN_UNIT.")

REPAIR_SCHEMA = {
    "type": "object",
    "required": ["verdict"],
    "properties": {
        "verdict": {"type": "string",
                    "enum": ["SUPPORTED", "NOT_SUPPORTED_IN_UNIT"]},
        "turn_id": {"type": "string"},
        "speaker": {"type": "string"},
        "quote": {"type": "string"},
    },
    "conditional_requirement_enforced_locally": {
        "SUPPORTED": "turn_id, speaker and quote are all mandatory and non-empty",
        "NOT_SUPPORTED_IN_UNIT": "turn_id, speaker and quote must be empty or absent",
        "why_local": ("the provider's structured output does not express if/then across "
                      "sibling fields, so the requirement is enforced by the validator "
                      "below and a violation is quarantined, never repaired"),
    },
    "no_third_category": True,
    "confidence_not_requested": True,
}

REPAIR_SUPPORTED = "SUPPORTED"
REPAIR_NOT_SUPPORTED = "NOT_SUPPORTED_IN_UNIT"


def validate_repair(payload: dict, turns: dict) -> dict:
    """
    The repair verdict, checked WITHOUT normalisation.

    Phase A's own metric is `normalized_contiguous_quote`. This repair is stricter by
    instruction: the returned quotation must be CHARACTER-EXACT and contiguous in the
    rendering. Normalisation is deliberately not applied — it exists to accept quotes
    already given in good faith, not to rescue a response produced after the model was
    told exactly what a valid quotation is.
    """
    v = (payload or {}).get("verdict")
    tid = ((payload or {}).get("turn_id") or "").strip()
    spk = ((payload or {}).get("speaker") or "").strip()
    quote = (payload or {}).get("quote") or ""
    problems = []

    if v not in (REPAIR_SUPPORTED, REPAIR_NOT_SUPPORTED):
        return {"resolution": "QUARANTINE", "verdict": v,
                "problems": [f"verdict {v!r} is not one of the two permitted values"]}

    if v == REPAIR_NOT_SUPPORTED:
        if tid or spk or quote.strip():
            problems.append("NOT_SUPPORTED_IN_UNIT carries evidence fields")
        return {"resolution": ("EXCLUDE_THEME" if not problems else "QUARANTINE"),
                "verdict": v, "problems": problems,
                "evidence_invented": False}

    for name, val in (("turn_id", tid), ("speaker", spk), ("quote", quote.strip())):
        if not val:
            problems.append(f"SUPPORTED is missing {name}")
    if problems:
        return {"resolution": "QUARANTINE", "verdict": v, "problems": problems}

    us = turns.get(tid)
    if us is None:
        problems.append("turn_id is not in this unit")
    else:
        hit = next((u for u in us if quote in u["text"]), None)   # NO normalisation
        if hit is None:
            problems.append("quote is not a character-exact contiguous substring of "
                            "the named turn")
        elif hit["is_moderator"] or spk.lower() == "moderator":
            problems.append("quote is attributed to the moderator")
        elif spk != hit["speaker"]:
            problems.append(f"speaker {spk!r} does not hold turn {tid}")
    return {"resolution": ("KEEP_THEME" if not problems else "QUARANTINE"),
            "verdict": v, "problems": problems,
            "turn_id": tid, "speaker": spk, "quote": quote,
            "character_exact": not problems}


def main() -> int:
    b = revalidate()
    reproduced = {k: (b[k], EXPECTED[k], b[k] == EXPECTED[k]) for k in EXPECTED}
    all_ok = all(v[2] for v in reproduced.values())

    _atomic(_OUT / "phase_a_theme_level_validation.json",
            {k: v for k, v in b.items() if k not in ("rejected_quotes", "repairs")})
    _atomic(_OUT / "rejected_quotes_audit.json",
            {"policy_id": POLICY_ID, "n_rejected": len(b["rejected_quotes"]),
             "verdict_counts": {k: v for k, v in b["quote_verdicts"].items()
                                if k != Q_VALID},
             "rule": "every invalid quote is retained here, never deleted",
             "quotes": b["rejected_quotes"]})
    _atomic(_OUT / "evidence_repair_manifest.json", build_repair_manifest(b))

    print("=== RECOMPUTACIÓN vs CONTEOS ESPERADOS ===")
    for k, (got, exp, ok) in reproduced.items():
        print(f"  {k:34s} esperado {exp:4d}  obtenido {got:4d}   "
              f"{'OK' if ok else 'DIFIERE'}")
    print(f"\n  reproduce todos los conteos: {all_ok}")
    print(f"  citas {b['n_quotes']}  veredictos {b['quote_verdicts']}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
