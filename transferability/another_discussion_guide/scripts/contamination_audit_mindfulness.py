"""
Cross-domain contamination audit for the mindfulness FG1 run.

Offline only. No API calls.

Method mirrors analysis/production_evaluation/contamination_audit.json: prompts
are RENDERED through the same functions the live run uses, so "rendered" means
what the generating model would actually receive — not what the source files
store. Rendering matters here because core.prompt_renderer.load_system_prompt
strips the file-level comment header, so provenance comments in the prompt
files never reach the model and must not be counted as leakage.

Surfaces audited:
  - moderator system prompt (via load_system_prompt, with the config's override
    and restraint settings)
  - session opening prompt (via render_opening_message, with the real config)
  - moderator reflection prompt (via render_reflection_message)
  - participant system prompt for every agent (via build_participant_system_prompt)

Usage:
    py scripts/contamination_audit_mindfulness.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.orchestrator import _build_state_from_config  # noqa: E402
from core.participant_agent import build_participant_system_prompt  # noqa: E402
from core.prompt_renderer import (  # noqa: E402
    load_system_prompt,
    render_opening_message,
    render_reflection_message,
)

_CONFIG = _ROOT / "configs/experiment/mindfulness_fg1_run01.json"
_OUT = _ROOT / "analysis/transportability_mindfulness/contamination_audit_mindfulness.json"

# Terms whose presence in a rendered mindfulness prompt indicates Macho Meals
# content has crossed domains. Word-boundary matched to avoid false positives
# such as "TEMPLATE" containing "plate" or "repeating" containing "eating".
_LEXICON = {
    "domain_nouns": [
        r"\bmeat\b", r"\bvegan\b", r"\bvegetarian\b", r"\bplant-based\b",
        r"\bsalad\b", r"\bmasculin\w*\b", r"\bmacho\b", r"\bdiet\b",
        r"\bfood\b", r"\bmeal\b", r"\beating\b", r"\bgrocer\w*\b",
        r"\bshopping habits\b", r"\bmates\b",
    ],
    "study_identifiers": [
        r"\bmacho[_ ]meals\b", r"\bmm_fg\d\b", r"\bDS03\b", r"\bMRNI\b",
    ],
    "participant_names": [
        r"\bAmir\b", r"\bDavid\b", r"\bIbrahim\b", r"\bIsaiah\b", r"\bWill\b",
        r"\bSam\b", r"\bNoah\b", r"\bHenry\b", r"\bBilal\b", r"\bConnor\b",
        r"\bAndrew\b", r"\bDaniel\b", r"\bJohn\b", r"\bNick\b", r"\bPaul\b",
        r"\bGregor\b", r"\bJames\b", r"\bMark\b", r"\bFletcher\b",
        r"\bKeith\b", r"\bPatrick\b", r"\bToby\b",
    ],
}


# Participant names are matched CASE-SENSITIVELY. Several Macho Meals
# participants share a spelling with a common English word ("Will" / "will",
# "Mark" / "mark"), and case-insensitive matching produced 18 false positives on
# the modal verb alone. Capitalisation is the only signal available that
# separates a name from its homograph, so the name category uses it; the other
# two categories stay case-insensitive.
_CASE_SENSITIVE_CATEGORIES = {"participant_names"}


def _scan(name: str, text: str) -> list[dict]:
    hits = []
    for category, patterns in _LEXICON.items():
        flags = 0 if category in _CASE_SENSITIVE_CATEGORIES else re.IGNORECASE
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=flags):
                start = max(0, match.start() - 90)
                end = min(len(text), match.end() + 90)
                hits.append(
                    {
                        "surface": name,
                        "category": category,
                        "pattern": pattern,
                        "matched_text": match.group(0),
                        "context": text[start:end].replace("\n", " ").strip(),
                    }
                )
    return hits


def main() -> int:
    config = json.loads(_CONFIG.read_text(encoding="utf-8"))
    state = _build_state_from_config(config)

    surfaces: dict[str, str] = {}

    surfaces["moderator_system_prompt"] = load_system_prompt(
        restraint_enabled=config.get("moderator_restraint_prompt", False),
        prompt_override_filename=config.get("moderator_prompt_override"),
    )
    surfaces["session_opening_prompt"] = render_opening_message(
        config, config.get("moderator_opening_prompt_override")
    )
    surfaces["moderator_reflection_prompt"] = render_reflection_message({})

    roster = state.participants
    entries = roster.values() if isinstance(roster, dict) else roster
    for participant in entries:
        pid = getattr(participant, "participant_id", None) or getattr(participant, "id", "?")
        surfaces[f"participant_system_prompt::{pid}"] = build_participant_system_prompt(
            participant, state.session_meta, has_other_participants=True
        )

    all_hits: list[dict] = []
    per_surface = {}
    for name, text in surfaces.items():
        hits = _scan(name, text)
        all_hits.extend(hits)
        per_surface[name] = {"chars": len(text), "hits": len(hits)}

    report = {
        "record_type": "CROSS_DOMAIN_CONTAMINATION_AUDIT",
        "scope": "mindfulness_fg1_run01 — pre-run, offline",
        "read_only": True,
        "no_api_calls": True,
        "method_note": (
            "Prompts rendered through the same functions the live run uses. "
            "load_system_prompt strips the file-level comment header, so provenance "
            "comments (which mention macho_meals_fg1_run01) do not reach the model and "
            "are correctly absent from these results."
        ),
        "config_audited": str(_CONFIG.relative_to(_ROOT)).replace("\\", "/"),
        "surfaces_audited": per_surface,
        "total_hits": len(all_hits),
        "hits": all_hits,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {_OUT.relative_to(_ROOT)}\n")
    for name, info in per_surface.items():
        flag = "  <-- HITS" if info["hits"] else ""
        print(f"  {info['hits']:3d} hits  {info['chars']:6d} chars  {name}{flag}")
    print(f"\nTOTAL HITS: {len(all_hits)}")
    for hit in all_hits:
        print(f"\n  [{hit['category']}] {hit['matched_text']!r} in {hit['surface']}")
        print(f"      ...{hit['context']}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
