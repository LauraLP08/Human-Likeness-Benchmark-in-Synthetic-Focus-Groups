#!/usr/bin/env python3
"""
twinpop_g0_render_hashes.py — G0 gate for the twin-population arm.

Captures a fingerprint of everything the `persona.background` change in
`core/participant_agent.py` must NOT alter, so that "the change is a no-op for
every existing agent" is proved rather than asserted.

Covers (see PREREGISTRO_BRAZO_TWIN_POBLACIONAL_2026-08-04.md §9, G0):
  G0.a  build_participant_system_prompt over ALL agents in agents/**/*.json,
        with inject_participant_intro False AND True.
  G0.b  load_agent_from_json(...).profile_summary over the same agents
        (covers the moderator route via moderator_brain.py).
  G0.c  inspect.getsource of the functions and constants that must not change.

G0.d (existing test suite runs unmodified and passes) is run separately.

Usage:
    py scripts/twinpop_g0_render_hashes.py --out <path.json>
    py scripts/twinpop_g0_render_hashes.py --compare <before.json> <after.json>

This script is additive: it imports the pipeline read-only and writes nothing
except its own output file.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import participant_agent as pa  # noqa: E402
from core.session_state import SessionMeta  # noqa: E402

# Functions and constants that the G0 change must leave byte-identical.
# build_participant_system_prompt is deliberately absent: it is the one thing
# that changes.
GUARDED_FUNCTIONS = [
    "load_agent_from_json",
    "assess_engagement",
    "call_participant",
    "_render_cacheable_messages",
    "_format_recent_transcript",
    "_score_to_instruction",
    "_bucket",
    "_stable_variant_index",
]

GUARDED_CONSTANTS = [
    "_BEHAVIOUR_INSTRUCTIONS",
    "_BEHAVIOUR_INSTRUCTIONS_ES",
    "_DIMENSION_TIER",
    "_HABIT_TEMPLATES",
    "_CODED_TEMPLATES",
    "_DISPOSITION_HEADER_EN",
    "_DISPOSITION_HEADER_ES",
]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_session_meta(inject_intro: bool) -> SessionMeta:
    """A fixed, minimal SessionMeta. Values are arbitrary but frozen: only
    inject_participant_intro is varied, since that is the branch G0 must cover."""
    return SessionMeta(
        id="g0_fixture",
        research_objective="g0",
        topic_domain="g0",
        participant_collective_identity="g0",
        moderator_knowledge_brief="g0",
        participant_response_max_tokens=800,
        participation_mode="emergent",
        inject_participant_intro=inject_intro,
    )


def agent_paths() -> list[Path]:
    return sorted(
        (p for p in (ROOT / "agents").rglob("*.json") if p.name != "_manifest.json"),
        key=lambda p: p.relative_to(ROOT).as_posix(),
    )


def capture() -> dict:
    meta_false = make_session_meta(False)
    meta_true = make_session_meta(True)

    agents: dict[str, dict] = {}
    skipped: list[dict] = []

    for path in agent_paths():
        rel = path.relative_to(ROOT).as_posix()
        try:
            state = pa.load_agent_from_json(str(path))
        except Exception as exc:  # not an agent file, or malformed
            skipped.append({"path": rel, "reason": f"{type(exc).__name__}: {exc}"})
            continue

        entry = {"profile_summary_sha256": sha(state.profile_summary)}
        for label, meta in (("intro_false", meta_false), ("intro_true", meta_true)):
            try:
                prompt = pa.build_participant_system_prompt(state, meta, has_other_participants=True)
                entry[f"prompt_{label}_sha256"] = sha(prompt)
                entry[f"prompt_{label}_len"] = len(prompt)
            except Exception as exc:
                entry[f"prompt_{label}_sha256"] = f"ERROR {type(exc).__name__}: {exc}"
        agents[rel] = entry

    source: dict[str, str] = {}
    for fn_name in GUARDED_FUNCTIONS:
        fn = getattr(pa, fn_name, None)
        source[f"fn:{fn_name}"] = sha(inspect.getsource(fn)) if fn is not None else "ABSENT"
    for const_name in GUARDED_CONSTANTS:
        if hasattr(pa, const_name):
            source[f"const:{const_name}"] = sha(repr(getattr(pa, const_name)))
        else:
            source[f"const:{const_name}"] = "ABSENT"

    return {
        "gate": "G0",
        "arm": "twinpop",
        "n_agents": len(agents),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "agents": agents,
        "source": source,
    }


def compare(before_path: Path, after_path: Path) -> int:
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))

    failures: list[str] = []

    b_agents, a_agents = before["agents"], after["agents"]
    if set(b_agents) != set(a_agents):
        only_b = sorted(set(b_agents) - set(a_agents))
        only_a = sorted(set(a_agents) - set(b_agents))
        for p in only_b:
            failures.append(f"AGENT MISSING AFTER: {p}")
        for p in only_a:
            failures.append(f"AGENT NEW AFTER: {p}")

    for path in sorted(set(b_agents) & set(a_agents)):
        for key in ("profile_summary_sha256", "prompt_intro_false_sha256", "prompt_intro_true_sha256"):
            if b_agents[path].get(key) != a_agents[path].get(key):
                failures.append(
                    f"CHANGED {key}: {path}\n"
                    f"    before={b_agents[path].get(key)}\n"
                    f"    after ={a_agents[path].get(key)}"
                )

    for key in sorted(set(before["source"]) | set(after["source"])):
        if before["source"].get(key) != after["source"].get(key):
            failures.append(f"CHANGED SOURCE {key}")

    n = len(set(b_agents) & set(a_agents))
    print(f"G0 comparison over {n} agents (x2 intro settings) + {len(before['source'])} source objects")
    if failures:
        print(f"\nG0 FAIL — {len(failures)} difference(s):\n")
        for f in failures:
            print("  " + f)
        print("\nPer the pre-registration, a single differing hash means: revert the change")
        print("and fall back to accepting-and-declaring the framing asymmetry (§3.4).")
        return 1

    print("\nG0 PASS — the change is a no-op for every existing agent,")
    print("under both inject_participant_intro settings, and no guarded")
    print("function or constant was modified.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, help="write a capture to this path")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args()

    if args.compare:
        return compare(*args.compare)

    if not args.out:
        ap.error("one of --out or --compare is required")

    result = capture()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print(f"captured {result['n_agents']} agents ({result['n_skipped']} skipped) -> {args.out}")
    if result["skipped"]:
        print("skipped:")
        for s in result["skipped"]:
            print(f"  {s['path']}: {s['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
