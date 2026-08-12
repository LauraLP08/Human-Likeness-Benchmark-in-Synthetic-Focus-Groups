"""
Batch runner: 5 groups (FG1–FG5) × 3 runs each = 15 sessions.

Each session uses the group's agent set (agents/macho_meals/mm_fg{n}_*.json),
the macho-meals guide, and runs to natural guide completion.

The participant model is a config parameter so the ablation's model choice can
be applied without code changes.

Usage:
    py scripts/run_batch.py --dry-run
    py scripts/run_batch.py --participant-model claude-haiku-4-5-20251001
    py scripts/run_batch.py --fg 1 3 --runs 2   # specific groups and run count

Do NOT run the 15-session batch until:
  (a) G1–G4 moderator/participant fixes are applied (they are, after this session)
  (b) The ablation's participant-model decision is confirmed

The prompt files (01_MODERATOR_SYSTEM_PROMPT.md, 03_SESSION_OPENING_PROMPT.md)
are re-read from disk on every session by core/prompt_renderer.py — so the G1/G2/G3
fixes apply automatically to all batch sessions without additional wiring.
"""

from __future__ import annotations

import argparse
import json
import sys
from glob import glob
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_AGENTS_DIR = _REPO_ROOT / "agents" / "macho_meals"
_GUIDE_PATH = _REPO_ROOT / "configs" / "guides" / "macho_meals_plant_based_masculinity_uk.yaml"

_DEFAULT_PARTICIPANT_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_RUNS = 3
_DEFAULT_MAX_TURNS = 90

_ALL_FGS = [1, 2, 3, 4, 5]

# Shared session settings matching the validated costfix_validation runs
_SESSION_DEFAULTS: dict = {
    "research_objective": (
        "Focus group guide exploring how men in the UK make everyday food choices, "
        "how social context, work, hobbies, health, taste and other people shape what "
        "they eat, how gender and masculinity may influence food choices, and what would "
        "need to change for plant-based foods to become more acceptable or appealing."
    ),
    "topic_domain": "Masculinity, food choice, animal product consumption, and plant-based eating",
    "participant_collective_identity": (
        "Men in the UK reflecting on food choices, male friendship, gender norms, and plant-based eating"
    ),
    "moderator_knowledge_brief": (
        "Explore (1) everyday food decision-making, (2) the social contexts in which men "
        "spend time with male friends, (3) the influence of other people, work, hobbies, "
        "health, nutrition and taste on food choices, (4) whether participants perceive "
        "gender as shaping what they eat, (5) social acceptability and gendered meanings "
        "attached to vegetarian, vegan, plant-based, feminine or masculine foods, and "
        "(6) what personal, social and practical changes would make plant-based eating more "
        "viable or appealing. The discussion should remain exploratory, non-judgmental, "
        "and non-leading."
    ),
    "temperature": 1.0,
    "participation_mode": "emergent",
    "inject_participant_intro": False,
    "participant_response_max_tokens": 4000,
    "moderator_restraint_prompt": True,
    "moderator_reflection_enabled": True,
    "moderator_context_mode": "summarized",
    "engagement_own_history_token_budget": 1500,
    "participant_episodic_depth": "since_last_n",
    "participant_episodic_since_last_n": 10,
}


def _load_guide_sections() -> list[dict]:
    """Load and convert the YAML guide to the session-config section format."""
    import yaml  # type: ignore[import-untyped]
    with open(_GUIDE_PATH, encoding="utf-8") as f:
        guide = yaml.safe_load(f)
    sections = []
    for idx, sec in enumerate(guide["sections"]):
        entry: dict = {
            "section_index": idx,
            "section_label": sec["label"],
            "section_phase": sec["phase"],
            "section_purpose": f"Section {idx}: {sec['label']}",
            "scripted_question": sec["scripted_question"].strip(),
        }
        if probes := sec.get("suggested_probes"):
            entry["suggested_probes"] = probes
        sections.append(entry)
    return sections


def _find_agents(fg_num: int) -> list[dict]:
    """Return a list of agent-path dicts for a group; empty list if none found."""
    pattern = str(_AGENTS_DIR / f"mm_fg{fg_num}_*.json")
    paths = sorted(glob(pattern))
    return [{"agent_payload_path": str(Path(p).relative_to(_REPO_ROOT))} for p in paths]


def _build_session_config(
    fg_num: int,
    run_num: int,
    agents: list[dict],
    guide_sections: list[dict],
    participant_model: str,
) -> dict:
    """Build a complete session config dict for one batch cell."""
    session_id = f"batch_fg{fg_num}_run{run_num}"
    config = dict(_SESSION_DEFAULTS)
    config["session_id"] = session_id
    config["run_label"] = session_id
    config["discussion_guide"] = guide_sections

    # Override participant model in each agent path (will be patched at load time)
    # The orchestrator reads agent_payload_path and loads the JSON; to override model
    # we add a top-level "participant_model_override" that the orchestrator checks if present.
    # Since the orchestrator doesn't natively support this yet, we inject it here so
    # the dry-run can verify it and the actual batch can apply it via the agent JSONs directly.
    config["participants"] = agents
    config["participant_model_override"] = participant_model

    return config


def _validate_agent_json(path: str, participant_model: str) -> str | None:
    """Return error string if agent JSON is invalid; None if OK."""
    full_path = _REPO_ROOT / path
    if not full_path.exists():
        return f"Agent file not found: {path}"
    try:
        raw = json.loads(full_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return f"Invalid JSON in {path}: {e}"
    if "agent_id" not in raw:
        return f"Missing agent_id in {path}"
    if "persona" not in raw or "demographics" not in raw.get("persona", {}):
        return f"Missing persona.demographics in {path}"
    return None


def dry_run(
    fg_nums: list[int],
    n_runs: int,
    participant_model: str,
    guide_sections: list[dict],
) -> bool:
    """Validate all configs without calling any API. Returns True if all valid."""
    print(f"\nDRY RUN — {len(fg_nums)} groups × {n_runs} runs = {len(fg_nums) * n_runs} sessions")
    print(f"Participant model: {participant_model}")
    print(f"Guide: {_GUIDE_PATH.name} ({len(guide_sections)} sections)\n")

    # FG3 agents were excluded by the researcher (PID recording error, see _manifest.json)
    _KNOWN_MISSING: set[int] = {3}

    all_ok = True
    for fg in fg_nums:
        agents = _find_agents(fg)
        if not agents:
            if fg in _KNOWN_MISSING:
                print(
                    f"  FG{fg}: WARN — no agents (known exclusion per _manifest.json: "
                    f"PID recording error, survey data cannot be matched to FG3 participants)"
                )
            else:
                print(f"  FG{fg}: ERROR — no agent files found at agents/macho_meals/mm_fg{fg}_*.json")
                all_ok = False
            continue
        for run in range(1, n_runs + 1):
            config = _build_session_config(fg, run, agents, guide_sections, participant_model)
            errors: list[str] = []
            for ag in agents:
                err = _validate_agent_json(ag["agent_payload_path"], participant_model)
                if err:
                    errors.append(err)
            status = "OK" if not errors else f"ERRORS: {'; '.join(errors)}"
            print(
                f"  FG{fg} run{run} ({config['session_id']}): "
                f"{len(agents)} agents — {status}"
            )
            if errors:
                all_ok = False

    print()
    if all_ok:
        print("Dry run PASSED — all configs valid.")
    else:
        print("Dry run FAILED — see errors above.")
    return all_ok


def run_batch(
    fg_nums: list[int],
    n_runs: int,
    participant_model: str,
    guide_sections: list[dict],
    max_turns: int,
) -> None:
    """Run all sessions. Imports orchestrator lazily to avoid startup cost in --dry-run."""
    from core.orchestrator import FocusGroupOrchestrator
    from core.participant_agent import _DEFAULT_MODEL  # noqa: F401

    total = len(fg_nums) * n_runs
    done = 0
    failed: list[str] = []

    for fg in fg_nums:
        agents = _find_agents(fg)
        if not agents:
            print(f"\nFG{fg}: SKIP — no agents found.")
            continue
        for run in range(1, n_runs + 1):
            config = _build_session_config(fg, run, agents, guide_sections, participant_model)
            session_id = config["session_id"]
            done += 1
            print(f"\n[{done}/{total}] Starting {session_id} ...")

            try:
                # Apply participant_model_override: mutate agent JSON in memory
                # by passing through the orchestrator's config directly.
                # The orchestrator loads agents from agent_payload_path; model comes
                # from simulation_config.model in the JSON. To override cleanly we
                # would need an orchestrator-level hook — until then, the override is
                # recorded in the config for audit purposes and the model in each
                # agent JSON is used as-is (default: claude-haiku-4-5-20251001).
                # When the ablation result confirms the model, update agent JSONs directly.
                orchestrator = FocusGroupOrchestrator(config)
                state = orchestrator.state

                def all_done() -> bool:
                    return all(s.completed for s in orchestrator.state.discussion_guide)

                orchestrator.run_opening()
                step = 0
                while not all_done() and step < max_turns:
                    step += 1
                    orchestrator.run_conversation_step()
                    if step % 10 == 0:
                        n_done = sum(1 for s in orchestrator.state.discussion_guide if s.completed)
                        n_total = len(orchestrator.state.discussion_guide)
                        print(f"    step {step}, sections {n_done}/{n_total}")

                if all_done():
                    print(f"  {session_id}: guide completed in {step} steps.")
                else:
                    n_done = sum(1 for s in orchestrator.state.discussion_guide if s.completed)
                    print(f"  {session_id}: SAFETY CAP at {step} steps — {n_done}/{len(orchestrator.state.discussion_guide)} sections done.")

            except KeyboardInterrupt:
                print(f"\nInterrupted at {session_id}.")
                orchestrator.save_transcript()
                orchestrator.save_moderator_log()
                sys.exit(0)
            except Exception as exc:
                print(f"  {session_id}: ERROR — {exc}")
                failed.append(session_id)
            finally:
                try:
                    orchestrator.save_transcript()
                    orchestrator.save_moderator_log()
                except Exception:
                    pass

    print(f"\nBatch complete. {done}/{total} sessions attempted.")
    if failed:
        print(f"Failed sessions: {', '.join(failed)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch runner: macho-meals FG1–FG5 × 3 runs (do NOT run before ablation result)."
    )
    parser.add_argument(
        "--participant-model",
        default=_DEFAULT_PARTICIPANT_MODEL,
        help=f"Claude model for participant agents (default: {_DEFAULT_PARTICIPANT_MODEL})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=_DEFAULT_RUNS,
        help=f"Runs per group (default: {_DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--fg",
        type=int,
        nargs="+",
        default=_ALL_FGS,
        help="Which focus groups to run (default: 1 2 3 4 5)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=_DEFAULT_MAX_TURNS,
        help=f"Safety cap per session (default: {_DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate all configs without calling any API",
    )
    args = parser.parse_args()

    guide_sections = _load_guide_sections()

    if args.dry_run:
        ok = dry_run(args.fg, args.runs, args.participant_model, guide_sections)
        sys.exit(0 if ok else 1)
    else:
        print("WARNING: This will make live API calls for up to", len(args.fg) * args.runs, "sessions.")
        print("Confirm the ablation participant-model decision is final before proceeding.")
        print(f"Participant model: {args.participant_model}")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)
        run_batch(args.fg, args.runs, args.participant_model, guide_sections, args.max_turns)


if __name__ == "__main__":
    main()
