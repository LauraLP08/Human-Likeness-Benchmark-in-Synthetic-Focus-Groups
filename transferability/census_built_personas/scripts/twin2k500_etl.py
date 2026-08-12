"""
Twin-2K-500 → agent JSON ETL.

Reads cached Twin-2K-500 data, applies scripts/twin2k500_mapping.yaml,
and writes one agent JSON per participant to agents/twin2k500/.

Each output file conforms to ARCHITECTURE.md Appendix B (verified via
the local mirror in twin2k500_schema_mirror.py).

This script DOES NOT import from core/ and does not modify any existing file.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from datasets import load_dataset

from twin2k500_schema_mirror import AgentPayload

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "twin2k500" / "raw"
OUT_DIR = ROOT / "agents" / "twin2k500"
MAPPING_PATH = Path(__file__).resolve().parent / "twin2k500_mapping.yaml"

DEFAULT_MODEL = "claude-haiku-4-5-20251001"   # matches the Haiku default in Appendix B
DEFAULT_MAX_TOKENS = 512
SUMMARY_CHAR_LIMIT = 12000                    # keep notes field bounded

OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Helpers ----------------------------------------------------------

def _parse_persona_json(raw: Any) -> list:
    return json.loads(raw) if isinstance(raw, str) else raw


def _load_mapping() -> dict:
    with MAPPING_PATH.open() as f:
        return yaml.safe_load(f) or {}


def _find_answer(persona_json: list, qid: str) -> Any:
    """Return the answer value for a given QID, or None if not found."""
    for block in persona_json:
        for q in block.get("Questions", []) or []:
            if q.get("QuestionID") != qid:
                continue
            ans = q.get("Answers") or {}
            # Multiple choice
            if "SelectedText" in ans:
                return ans["SelectedText"]
            if "SelectedByPosition" in ans:
                return ans["SelectedByPosition"]
            # Numeric or text entry — try common keys
            for key in ("Value", "Text", "EnteredText", "EnteredValue"):
                if key in ans:
                    return ans[key]
            return ans  # raw fallback
    return None


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


_AGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_AGE_OPEN_TOP_RE = re.compile(r"^\s*(\d+)\s*\+\s*$")


def _parse_age_bucket(value: object) -> tuple[int, str | None]:
    """
    Parse a Twin-2K-500 age value.

    Returns (age_int, bucket_string_or_None) where:
      - "18-29"  -> (24, "18-29")    midpoint (floor)
      - "65+"    -> (65, "65+")      lower bound for open-ended top bucket
      - "24"     -> (24, None)       already numeric, no bucket
      - 24       -> (24, None)
      - None     -> (0, None)        absent
      - other    -> (0, None)        unparseable
    """
    if value is None:
        return 0, None

    if isinstance(value, (int, float)):
        return int(value), None

    s = str(value).strip()
    if not s:
        return 0, None

    if s.isdigit():
        return int(s), None

    m = _AGE_RANGE_RE.match(s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo + hi) // 2, s

    m = _AGE_OPEN_TOP_RE.match(s)
    if m:
        return int(m.group(1)), s

    return 0, None


def _extract_demographics(persona_json: list, mapping: dict) -> dict[str, Any]:
    demo: dict[str, Any] = {}
    for field, qid in (mapping.get("demographics") or {}).items():
        if not qid:
            continue
        val = _find_answer(persona_json, qid)
        if val is not None and val != "":
            demo[field] = val
    return demo


def _extract_psych(persona_json: list, mapping: dict) -> dict[str, Any]:
    psych: dict[str, Any] = {}
    for category, dims in (mapping.get("psychological_profile") or {}).items():
        if not dims:
            continue
        cat_block: dict[str, Any] = {}
        for dim, cfg in (dims or {}).items():
            if not cfg:
                continue
            qids = list(cfg.get("qids") or [])
            reverse = set(cfg.get("reverse_scored") or [])
            scale_max = float(cfg.get("scale_max", 5))
            scores: list[float] = []
            for qid in qids:
                raw = _find_answer(persona_json, qid)
                try:
                    n = float(raw)
                except (TypeError, ValueError):
                    continue
                if qid in reverse:
                    n = (scale_max + 1.0) - n
                scores.append(n)
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            cat_block[dim] = {
                "score": round(avg, 2),
                "description": (
                    f"Aggregated from {len(scores)} item(s) on a 1-{int(scale_max)} scale."
                ),
            }
        if cat_block:
            psych[category] = cat_block
    return psych


def _synthesize_name(pid: str) -> str:
    """Twin-2K-500 does not ship names. Stable, anonymous identifier."""
    return f"Participant_{pid}"


# ---------- Core transformation ----------------------------------------------

def build_agent_payload(row: dict, mapping: dict) -> dict[str, Any]:
    pid = str(row["pid"])
    persona_json = _parse_persona_json(row["persona_json"])
    persona_summary = row.get("persona_summary") or ""

    demo = _extract_demographics(persona_json, mapping)
    psych = _extract_psych(persona_json, mapping)

    # Required fields per Appendix B: name, age, gender
    age_int, age_bucket = _parse_age_bucket(demo.get("age"))
    demographics_block: dict[str, Any] = {
        "name": _synthesize_name(pid),
        "age": age_int,
        "gender": str(demo.get("gender") or "unspecified"),
    }
    if age_bucket is not None:
        demographics_block["age_bucket"] = age_bucket
    location_fields = {
        "region": demo.get("region"),
        "country": demo.get("country", "US"),
        "urban_rural": demo.get("urbanicity"),
    }
    if any(v not in (None, "") for v in location_fields.values()):
        demographics_block["location"] = {
            k: (v if v not in (None, "") else "unknown")
            for k, v in location_fields.items()
        }

    persona_block: dict[str, Any] = {"demographics": demographics_block}
    if psych:
        persona_block["psychological_profile"] = psych

    notes_text = persona_summary[:SUMMARY_CHAR_LIMIT] if persona_summary else ""

    payload = {
        "agent_id": f"twin_{pid}",
        "version": 1,
        "tier": "twin2k500",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "persona": persona_block,
        "simulation_config": {
            "model": DEFAULT_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "notes": notes_text,
        },
    }

    # Local schema validation — fails fast on schema drift.
    AgentPayload.model_validate(payload)
    return payload


# ---------- Entry point ------------------------------------------------------

def main() -> None:
    mapping = _load_mapping()
    print(f"[twin2k500_etl] Loaded mapping from {MAPPING_PATH}")

    ds = load_dataset(
        "LLM-Digital-Twin/Twin-2K-500",
        "full_persona",
        cache_dir=str(CACHE_DIR),
    )
    rows = ds["data"]
    print(f"[twin2k500_etl] Transforming {len(rows)} participants ...")

    manifest = {
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mapping_path": str(MAPPING_PATH),
        "produced": [],
        "skipped": [],
    }

    for row in rows:
        pid = str(row.get("pid", "?"))
        try:
            payload = build_agent_payload(row, mapping)
            out_path = OUT_DIR / f"{payload['agent_id']}.json"
            out_path.write_text(json.dumps(payload, indent=2))
            manifest["produced"].append(payload["agent_id"])
        except Exception as exc:                    # noqa: BLE001
            manifest["skipped"].append({"pid": pid, "error": repr(exc)})

    (OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        f"[twin2k500_etl] Produced {len(manifest['produced'])}; "
        f"skipped {len(manifest['skipped'])}."
    )
    print(f"[twin2k500_etl] Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
