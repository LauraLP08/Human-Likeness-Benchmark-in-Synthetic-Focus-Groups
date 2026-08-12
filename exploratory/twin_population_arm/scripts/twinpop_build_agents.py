#!/usr/bin/env python3
"""
twinpop_build_agents.py — Phase 3, step 3 of the twin-population arm.

Builds the 8 `agents/macho_meals_twinpop/` payloads and runs the offline gates
G1 (the narrative reaches the model, exactly once, and nothing else changed) and
G4 (volume of the rendered block).

Selection rule (pre-registro §4.5): the FIRST surviving candidate in generation
order. Candidate 1 was clean on the §4.3 layer-1 domain list for all 8 cells, so
candidate 1 is taken throughout — no investigator choice is exercised.

Each payload is `demoonly` + `persona.background`. Nothing else changes, which is
what G1's mechanical diff asserts.

No API calls.

Usage:
    py scripts/twinpop_build_agents.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import participant_agent as pa  # noqa: E402
from core.session_state import SessionMeta  # noqa: E402

SRC_FULL = ROOT / "agents" / "macho_meals"
SRC_DEMO = ROOT / "agents" / "macho_meals_demoonly"
DEST = ROOT / "agents" / "macho_meals_twinpop"

BACKGROUND_KEY_ORDER = ["working_life", "home_and_household", "week_and_hobbies"]
MUST_BE_ABSENT = [
    ("persona", "demographics", "diet"),
    ("persona", "food_consumption"),
    ("psychometric_scores",),
    ("simulation_config", "notes"),
]
G4_BAND = (220, 300)
EXPECTED_HEADER = ("Your everyday life (speak from these naturally — don't list them, "
                   "just let them inform your answers):")
# field_provenance entries inherited from demoonly that describe fields G1
# certifies ABSENT. Left in place the file contradicts itself; purge on build.
STALE_PROVENANCE = ["persona.demographics.diet", "persona.food_consumption",
                    "psychometric_scores", "simulation_config.notes"]


def meta(intro: bool = False) -> SessionMeta:
    return SessionMeta(
        id="twinpop_gate", research_objective="g", topic_domain="g",
        participant_collective_identity="g", moderator_knowledge_brief="g",
        participant_response_max_tokens=800, participation_mode="emergent", inject_participant_intro=intro,
    )


def absent(payload: dict, path: tuple[str, ...]) -> bool:
    node = payload
    for key in path[:-1]:
        node = node.get(key, {})
        if not isinstance(node, dict):
            return True
    return path[-1] not in node


def gate_diff_is_only_background(prompt_demo: str, prompt_new: str, background: dict) -> bool:
    """THE G1 assertion. Exported so twinpop_gate_controls.py tests this exact
    function rather than a copy of it — a duplicated gate can silently diverge
    from the one that runs in production while its controls keep passing."""
    diff = list(difflib.ndiff(prompt_demo.splitlines(), prompt_new.splitlines()))
    removed = [l[2:] for l in diff if l.startswith("- ")]
    added = [l[2:] for l in diff if l.startswith("+ ") and l[2:].strip()]
    expected = [EXPECTED_HEADER] + [f"  - {k.replace('_', ' ').capitalize()}: {v}"
                                    for k, v in background.items()]
    return (not removed) and added == expected


def render(payload: dict, agent_id: str, intro: bool = False) -> str:
    state = pa.ParticipantState(id=agent_id, name=payload["persona"]["demographics"]["name"],
                               profile_summary="", agent_payload=payload)
    return pa.build_participant_system_prompt(state, meta(intro), has_other_participants=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    narratives = json.loads((args.out_dir / "persona_narratives.json").read_text(encoding="utf-8"))
    selected = {r["agent_id"]: r for r in narratives["results"]
                if r["branch"] == "real" and r["candidate_index"] == 1}

    DEST.mkdir(parents=True, exist_ok=True)
    report, failures = [], []

    for agent_id in sorted(selected):
        demo_path = SRC_DEMO / f"{agent_id}.json"
        full_path = SRC_FULL / f"{agent_id}.json"
        demo = json.loads(demo_path.read_text(encoding="utf-8"))
        full = json.loads(full_path.read_text(encoding="utf-8"))
        rec = selected[agent_id]

        payload = json.loads(json.dumps(demo))  # deep copy, key order preserved
        payload["persona"]["background"] = {k: rec["narrative"][k] for k in BACKGROUND_KEY_ORDER}
        for stale in STALE_PROVENANCE:
            payload.get("field_provenance", {}).pop(stale, None)
        payload.setdefault("field_provenance", {}).update({
            f"persona.background.{k}": "rendered_from_census_microdata_sn9154"
            for k in BACKGROUND_KEY_ORDER
        })
        (DEST / f"{agent_id}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # ---- G1 -----------------------------------------------------------
        checks = {}
        d_new, d_full = payload["persona"]["demographics"], full["persona"]["demographics"]
        checks["demographics_identical_to_original"] = all(
            json.dumps(d_new.get(k), sort_keys=True) == json.dumps(d_full.get(k), sort_keys=True)
            for k in ("name", "age", "gender", "location"))
        checks["four_keys_absent"] = all(absent(payload, p) for p in MUST_BE_ABSENT)

        prompt_new = render(payload, agent_id)
        prompt_demo = render(demo, agent_id)

        counts = {k: prompt_new.count(v) for k, v in payload["persona"]["background"].items()}
        checks["each_prose_exactly_once"] = all(c == 1 for c in counts.values())

        # Mechanical negative assertion. The previous implementation compared
        # line MEMBERSHIP, which is blind to reordering and duplication — the
        # very property §3.3 relies on when it justifies persona.background by
        # serial position, and the risk R7 names. It also had an operator-
        # precedence hole that made any line containing "everyday life" an
        # unconditional pass. Both were demonstrated with working exploits.
        # This version does a positional diff and demands LIST EQUALITY against
        # the expected block, built explicitly rather than matched by predicate.
        checks["diff_is_only_background"] = gate_diff_is_only_background(
            prompt_demo, prompt_new, payload["persona"]["background"])
        # G0 exercises both inject_participant_intro settings; G1 must too.
        checks["diff_holds_with_intro_on"] = gate_diff_is_only_background(
            render(demo, agent_id, intro=True), render(payload, agent_id, intro=True),
            payload["persona"]["background"])
        # Provenance assertion: the prose in the payload must be the prose whose
        # hash was recorded at generation. Without this, every other G1 check
        # compares the payload with itself and says nothing about where the
        # content came from.
        import hashlib
        recomputed = hashlib.sha256(rec["raw_text"].encode("utf-8")).hexdigest()
        checks["narrative_hash_matches_generation"] = (recomputed == rec["sha256"]) and all(
            payload["persona"]["background"][k] == rec["narrative"][k]
            for k in BACKGROUND_KEY_ORDER)

        # ---- G4 -----------------------------------------------------------
        net_words = len(prompt_new.split()) - len(prompt_demo.split())
        checks["G4_volume_in_band"] = G4_BAND[0] <= net_words <= G4_BAND[1]

        ok = all(checks.values())
        if not ok:
            failures.append((agent_id, {k: v for k, v in checks.items() if not v}))
        report.append({"agent_id": agent_id, "candidate_index": 1,
                       "microdata_record_id": rec["microdata_record_id"],
                       "narrative_sha256": rec["sha256"], "net_words": net_words,
                       "prose_occurrences": counts, "checks": checks, "pass": ok})
        print(f"  {agent_id:16s} net={net_words:3d}w  " +
              "  ".join(f"{'OK ' if v else 'FAIL'} {k}" for k, v in checks.items()))

    (args.out_dir / "G1_G4_report.json").write_text(
        json.dumps({"gate": "G1+G4", "band": G4_BAND, "n_agents": len(report),
                    "all_pass": not failures, "agents": report}, indent=1, ensure_ascii=False),
        encoding="utf-8")

    print()
    if failures:
        print("G1/G4 FAIL:")
        for a, f in failures:
            print(f"  {a}: {list(f)}")
        return 1
    print(f"G1 + G4 PASS on all {len(report)} agents -> {DEST.relative_to(ROOT).as_posix()}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
