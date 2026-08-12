#!/usr/bin/env python3
"""
twinpop_build_configs.py — builds the 6 twinpop session configs and runs the
config equivalence test (ADENDUM v5 entry 12, gate G5).

Each config is cloned from its ORIGINAL experimental config
(configs/experiment/macho_meals_fg{3,4}_run01.json) and may differ in exactly
three keys: session_id, run_label, participants. The equivalence test fails on
any other change, and enumerates explicitly the elements that must not move:
discussion guide, research objective, models, temperature, token limits, memory,
participation mode, moderator prompt, reflection, conversational restraints.

Includes positive and negative controls: no verification result is accepted here
without a planted defect the test must catch.

No API calls. Nothing is executed; configs are written to disk only.

Usage:
    py scripts/twinpop_build_configs.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "configs" / "experiment"
AGENTS_TWIN = "agents/macho_meals_twinpop"

ALLOWED_TO_DIFFER = {"session_id", "run_label", "participants"}

# Named explicitly so the test is readable as a contract, not just as a diff.
MUST_NOT_MOVE = [
    "discussion_guide", "research_objective", "topic_domain",
    "participant_collective_identity", "moderator_knowledge_brief", "researcher_notes",
    "moderator_prompt_override", "moderator_restraint_prompt", "moderator_context_mode",
    "moderator_reflection_enabled", "time_budget_tracking_enabled",
    "participant_response_max_tokens", "participant_episodic_depth",
    "participant_episodic_since_last_n", "engagement_own_history_token_budget",
    "temperature", "participation_mode",
]


def equivalence(src: dict, new: dict) -> tuple[bool, list[str]]:
    problems = []
    for key in set(src) | set(new):
        if key in ALLOWED_TO_DIFFER:
            continue
        a = json.dumps(src.get(key, "<<absent>>"), sort_keys=True, ensure_ascii=False)
        b = json.dumps(new.get(key, "<<absent>>"), sort_keys=True, ensure_ascii=False)
        if a != b:
            problems.append(f"{key}: differs")
    for key in MUST_NOT_MOVE:
        if key in src and key not in new:
            problems.append(f"{key}: dropped")
    if set(new) - set(src) - ALLOWED_TO_DIFFER:
        problems.append(f"new keys: {sorted(set(new) - set(src) - ALLOWED_TO_DIFFER)}")
    return (not problems), problems


def controls(src: dict, good: dict) -> list[tuple[str, str, str]]:
    """Positive and negative controls for the equivalence test itself."""
    out = []
    ok, _ = equivalence(src, good)
    out.append(("negative: clean clone", "PASS", "PASS" if ok else "FAIL"))

    for name, mutate in [
        ("temperature changed", lambda c: c.update({"temperature": 0.7})),
        ("moderator prompt swapped",
         lambda c: c.update({"moderator_prompt_override": "sandbox/OTHER.md"})),
        ("token limit raised", lambda c: c.update({"participant_response_max_tokens": 1200})),
        ("participation mode changed", lambda c: c.update({"participation_mode": "orchestrated"})),
        ("episodic memory depth changed",
         lambda c: c.update({"participant_episodic_since_last_n": 5})),
        ("reflection disabled", lambda c: c.update({"moderator_reflection_enabled": False})),
        ("guide question edited",
         lambda c: c["discussion_guide"][2].update({"scripted_question": "Tampered?"})),
        ("extra key added", lambda c: c.update({"sneaky_new_flag": True})),
    ]:
        bad = json.loads(json.dumps(good))
        mutate(bad)
        ok, _ = equivalence(src, bad)
        out.append((f"positive: {name}", "FAIL", "PASS" if ok else "FAIL"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    roster = {"fg3": ["nick", "andrew", "john", "paul", "daniel"],
              "fg4": ["james", "mark", "gregor"]}

    built, report, failures = [], [], []
    control_rows = None

    for fg in ("fg3", "fg4"):
        src_path = CFG / f"macho_meals_{fg}_run01.json"
        src = json.loads(src_path.read_text(encoding="utf-8"))

        # participants: same shape as the source, repointed at the twinpop payloads
        new_participants = []
        for p in src["participants"]:
            path = p["agent_payload_path"] if isinstance(p, dict) else p
            name = Path(path).stem
            q = json.loads(json.dumps(p))
            if isinstance(q, dict):
                q["agent_payload_path"] = f"{AGENTS_TWIN}/{name}.json"
            else:
                q = f"{AGENTS_TWIN}/{name}.json"
            new_participants.append(q)

        for m in (1, 2, 3):
            sid = f"macho_meals_{fg}_twinpop_run0{m}"
            new = json.loads(json.dumps(src))
            new["session_id"] = sid
            new["run_label"] = f"twinpop_run0{m}"
            new["participants"] = new_participants
            dest = CFG / f"{sid}.json"
            dest.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            built.append(dest)

            ok, problems = equivalence(src, new)
            paths_ok = all(AGENTS_TWIN in (p["agent_payload_path"] if isinstance(p, dict) else p)
                           for p in new["participants"])
            outdir_free = not (ROOT / "output" / "session_logs" / sid).exists()
            allg = ok and paths_ok and outdir_free
            if not allg:
                failures.append((sid, problems or ["path/outdir"]))
            report.append({"session_id": sid, "cloned_from": src_path.name,
                           "equivalence_pass": ok, "problems": problems,
                           "participants_point_at_twinpop": paths_ok,
                           "output_dir_absent": outdir_free, "pass": allg})
            print(f"  {sid:36s} {'OK  ' if allg else 'FAIL'} "
                  f"equiv={ok} paths={paths_ok} outdir_free={outdir_free}")

            if control_rows is None:
                control_rows = controls(src, new)

    print("\nCONTROLES DE LA PRUEBA DE EQUIVALENCIA")
    controls_ok = True
    for name, expected, got in control_rows:
        good = expected == got
        controls_ok &= good
        print(f"  {'OK ' if good else 'ROTO'}  {name:38s} esperado={expected}  obtenido={got}")

    out = {"gate": "G5 + config equivalence", "allowed_to_differ": sorted(ALLOWED_TO_DIFFER),
           "must_not_move": MUST_NOT_MOVE, "n_configs": len(report),
           "all_pass": not failures, "controls_all_correct": controls_ok,
           "controls": [{"name": n, "expected": e, "observed": g} for n, e, g in control_rows],
           "configs": report}
    (args.out_dir / "G5_config_equivalence.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    print()
    if failures or not controls_ok:
        print("G5 FAIL"); return 1
    print(f"G5 PASS — {len(report)} configs, equivalencia y controles correctos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
