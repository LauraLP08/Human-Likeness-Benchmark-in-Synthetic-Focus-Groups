#!/usr/bin/env python3
"""
twinpop_gate_controls.py — positive and negative controls for the twinpop gates.

A verifier that has never been shown a defect it must catch is an untested
instrument. Three of this arm's verifiers failed silently before anyone looked:

  * the domain scan matched 'pub' inside 'public transport' (false positive);
  * the human self-description extractor returned zero and made a gate report
    PASS against an empty comparator (false negative — the dangerous direction);
  * G1's diff compared line MEMBERSHIP, so reordering and duplicating identity
    lines were invisible.

From here, no verification result is accepted without its controls. Each control
plants a defect the gate MUST catch (positive) and a clean case it MUST pass
(negative). This script is itself part of the audit trail.

No API calls.

Usage:
    py scripts/twinpop_gate_controls.py
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core import participant_agent as pa  # noqa: E402
from core.session_state import SessionMeta  # noqa: E402

DEMO = ROOT / "agents" / "macho_meals_demoonly" / "mm_fg3_andrew.json"
TWIN = ROOT / "agents" / "macho_meals_twinpop" / "mm_fg3_andrew.json"
EXPECTED_HEADER = ("Your everyday life (speak from these naturally — don't list them, "
                   "just let them inform your answers):")


def meta(intro: bool = False) -> SessionMeta:
    return SessionMeta(id="ctl", research_objective="g", topic_domain="g",
                       participant_collective_identity="g", moderator_knowledge_brief="g",
                       participant_response_max_tokens=800, participation_mode="emergent",
                       inject_participant_intro=intro)


def render(payload: dict) -> str:
    st = pa.ParticipantState(id="ctl", name=payload["persona"]["demographics"]["name"],
                             profile_summary="", agent_payload=payload)
    return pa.build_participant_system_prompt(st, meta(), has_other_participants=True)


# Imported, NOT re-implemented: a control that tests its own copy of the gate
# passes happily while the production gate is broken.
from twinpop_build_agents import (  # noqa: E402
    gate_diff_is_only_background, EXPECTED_HEADER as _HDR)


def main() -> int:
    demo = json.loads(DEMO.read_text(encoding="utf-8"))
    twin = json.loads(TWIN.read_text(encoding="utf-8"))
    bg = twin["persona"]["background"]
    p_demo = render(demo)

    results = []

    # --- NEGATIVE control: the real, clean payload must PASS -----------------
    results.append(("negative: clean twinpop payload", "PASS",
                    gate_diff_is_only_background(p_demo, render(twin), bg)))

    # --- POSITIVE control 1: smuggled notes carrying the header substring ----
    ex1 = json.loads(json.dumps(twin))
    ex1["simulation_config"]["notes"] = "Recruited as a regular meat eater who enjoys everyday life."
    results.append(("positive: smuggled simulation_config.notes", "FAIL",
                    gate_diff_is_only_background(p_demo, render(ex1), bg)))

    # --- POSITIVE control 2: two identity lines SWAPPED ----------------------
    p_swapped = render(twin).splitlines()
    for i, ln in enumerate(p_swapped):
        if ln.startswith("You live in") and i + 1 < len(p_swapped):
            p_swapped[i], p_swapped[i - 1] = p_swapped[i - 1], p_swapped[i]
            break
    results.append(("positive: two identity lines reordered", "FAIL",
                    gate_diff_is_only_background(p_demo, "\n".join(p_swapped), bg)))

    # --- POSITIVE control 3: an identity line DUPLICATED --------------------
    p_dup = render(twin).splitlines()
    for i, ln in enumerate(p_dup):
        if ln.startswith("You live in"):
            p_dup.insert(i + 1, ln)
            break
    results.append(("positive: identity line duplicated", "FAIL",
                    gate_diff_is_only_background(p_demo, "\n".join(p_dup), bg)))

    # --- POSITIVE control 4: background prose silently altered ---------------
    ex4 = json.loads(json.dumps(twin))
    ex4["persona"]["background"]["working_life"] += " He also enjoys a Sunday roast."
    results.append(("positive: background prose altered", "FAIL",
                    gate_diff_is_only_background(p_demo, render(ex4), bg)))

    ok = True
    print("CONTROLES DE LA PUERTA G1 (diff_is_only_background)\n")
    for name, expected, got in results:
        got_label = "PASS" if got else "FAIL"
        good = got_label == expected
        ok &= good
        print(f"  {'OK ' if good else 'ROTO'}  {name:44s} esperado={expected}  obtenido={got_label}")

    out = {"gate": "G1 controls", "all_controls_correct": ok,
           "controls": [{"name": n, "expected": e, "observed": "PASS" if g else "FAIL",
                         "correct": ("PASS" if g else "FAIL") == e} for n, e, g in results]}
    (ROOT / "analysis" / "production_evaluation" / "twinpop" / "G1_controls.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'TODOS LOS CONTROLES CORRECTOS' if ok else 'ALGUN CONTROL FALLA — la puerta no sirve'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
