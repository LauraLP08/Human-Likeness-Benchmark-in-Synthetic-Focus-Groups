"""
Build configs/experiment/mindfulness_fg1_run01.json.

Offline only. No API calls.

Design rule (transportability): every moderator/session knob is copied through
from configs/experiment/macho_meals_fg1_run01.json UNCHANGED, so that the only
variable differing between the Macho Meals runs and this run is the domain
(guide + personas). Instrument parity is what makes the comparison legitimate;
any knob edited here would become a rival explanation for an observed
difference.

Domain content is read verbatim from configs/guides/
mindfulness_self_administered_intervention.yaml — nothing is authored here.

Usage:
    py scripts/build_mindfulness_fg1_config.py [--check]

--check validates an existing config without rewriting it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_REFERENCE_CONFIG = _ROOT / "configs/experiment/macho_meals_fg1_run01.json"
_GUIDE = _ROOT / "configs/guides/mindfulness_self_administered_intervention.yaml"
_OUT = _ROOT / "configs/experiment/mindfulness_fg1_run01.json"
_AGENT_DIR = _ROOT / "agents/mindfulness"

# Keys whose values are domain content and are therefore re-derived from the
# mindfulness guide rather than copied from the reference config.
_DOMAIN_KEYS = {
    "session_id",
    "run_label",
    "research_objective",
    "topic_domain",
    "participant_collective_identity",
    "moderator_knowledge_brief",
    "participants",
    "discussion_guide",
}

# Krueger phase -> SectionPhase enum, per the mapping recorded in the guide headers.
_PHASE_PASSTHROUGH = {"intro", "context", "main_topic", "stimulus", "closing"}


def _load_guide() -> dict:
    with _GUIDE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _build_discussion_guide(guide: dict) -> list[dict]:
    sections = []
    for i, sec in enumerate(guide["sections"]):
        phase = sec["phase"]
        if phase not in _PHASE_PASSTHROUGH:
            raise ValueError(f"section {i}: unmapped phase {phase!r}")
        label = sec["label"]
        sections.append(
            {
                "section_index": i,
                "section_label": label,
                "section_phase": phase,
                "section_purpose": f"Section {i}: {label}",
                "scripted_question": sec["scripted_question"].strip(),
                "suggested_probes": [p for p in sec.get("suggested_probes") or []],
            }
        )
    return sections


def _participants() -> list[dict]:
    paths = sorted(p for p in _AGENT_DIR.glob("mf_*.json"))
    if not paths:
        raise SystemExit(f"no agent payloads found in {_AGENT_DIR}")
    return [{"agent_payload_path": f"agents/mindfulness/{p.name}"} for p in paths]


def build() -> dict:
    reference = json.loads(_REFERENCE_CONFIG.read_text(encoding="utf-8"))
    guide = _load_guide()

    config = {}
    for key, value in reference.items():
        if key in _DOMAIN_KEYS:
            continue
        config[key] = value  # instrument knob: copied through unchanged

    domain = {
        "session_id": "mindfulness_fg1_run01",
        "run_label": "run01",
        "research_objective": guide["description"].strip(),
        "topic_domain": guide["topic_domain"],
        "participant_collective_identity": guide["participant_collective_identity"],
        "moderator_knowledge_brief": guide["moderator_knowledge_brief"].strip(),
        "participants": _participants(),
        "discussion_guide": _build_discussion_guide(guide),
    }

    # Preserve the reference config's key order so a diff reads cleanly.
    ordered = {}
    for key in reference:
        ordered[key] = domain[key] if key in _DOMAIN_KEYS else config[key]
    for key in domain:
        ordered.setdefault(key, domain[key])
    return ordered


def check(config: dict, pre_run: bool = True) -> list[str]:
    """
    Return a list of problems; empty means PASS.

    pre_run gates the collision guard only. Before the session is launched an
    existing log directory means the session_id would collide; afterwards it
    simply means the run happened, which is not a problem.
    """
    problems: list[str] = []
    reference = json.loads(_REFERENCE_CONFIG.read_text(encoding="utf-8"))

    # 1. Key set must match the reference exactly.
    if set(config) != set(reference):
        problems.append(
            f"key set differs from reference: "
            f"only-here={sorted(set(config) - set(reference))} "
            f"only-there={sorted(set(reference) - set(config))}"
        )

    # 2. Every non-domain knob must be byte-identical to the reference.
    for key in reference:
        if key in _DOMAIN_KEYS:
            continue
        if config.get(key) != reference[key]:
            problems.append(
                f"instrument knob {key!r} differs from reference "
                f"({config.get(key)!r} vs {reference[key]!r}) — this would confound the comparison"
            )

    # 3. Referenced agent payloads must exist and be the right dataset.
    for entry in config["participants"]:
        path = _ROOT / entry["agent_payload_path"]
        if not path.exists():
            problems.append(f"missing agent payload: {entry['agent_payload_path']}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        dataset = payload.get("study_context", {}).get("dataset")
        if dataset != "DS05_SAM_MINDFULNESS":
            problems.append(f"{path.name}: unexpected dataset {dataset!r}")

    # 4. No Macho Meals residue anywhere in the serialized config.
    blob = json.dumps(config, ensure_ascii=False).lower()
    for term in (
        "macho",
        "meat",
        "plant-based",
        "vegan",
        "vegetarian",
        "masculin",
        "mm_fg",
        "amir",
        "ibrahim",
        "isaiah",
    ):
        if term in blob:
            problems.append(f"MACHO MEALS RESIDUE in config: {term!r}")

    # 5. Output dir must not already exist (no collision with a prior run).
    log_dir = _ROOT / "output/session_logs" / config["session_id"]
    if pre_run and log_dir.exists():
        problems.append(f"session log dir already exists: {log_dir}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate only, do not write")
    args = parser.parse_args()

    if args.check:
        if not _OUT.exists():
            print(f"FAIL: {_OUT} does not exist")
            return 2
        config = json.loads(_OUT.read_text(encoding="utf-8"))
    else:
        config = build()
        _OUT.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {_OUT.relative_to(_ROOT)}")

    problems = check(config, pre_run=not args.check)
    reference = json.loads(_REFERENCE_CONFIG.read_text(encoding="utf-8"))
    differing = sorted(k for k in reference if config.get(k) != reference.get(k))

    print(f"\nkeys differing from macho_meals_fg1_run01: {differing}")
    print(f"expected (domain only):                    {sorted(_DOMAIN_KEYS)}")
    print(f"participants: {len(config['participants'])}")
    print(f"guide sections: {len(config['discussion_guide'])}")

    if problems:
        print("\nFAIL")
        for p in problems:
            print(f"  - {p}")
        return 2
    print("\nPASS: all instrument knobs identical to reference; no Macho Meals residue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
