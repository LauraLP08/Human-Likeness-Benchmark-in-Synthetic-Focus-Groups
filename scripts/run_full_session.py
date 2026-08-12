"""
Run a synthetic focus group session to NATURAL GUIDE COMPLETION, not a fixed
turn count. Unlike run_session.py --turns N (which always runs exactly N
iterations regardless of guide state), this stops as soon as every section in
discussion_guide is marked completed, with a generous --max-turns safety cap
to prevent a runaway session if the moderator never closes the guide.

Built for the thematic-fidelity full-session experiment
(docs/findings/2026-06-30_thematic_fidelity_macho_meals.md), where the
instructions require "full sessions... NOT the 14-turn truncation; let it
run to natural completion or a generous cap that reaches all sections" —
exactly running run_session.py with a large --turns would not stop early
and would waste calls (and produce confusing post-closing content) once the
guide is already done.

Usage:
    python scripts/run_full_session.py --config examples/foo.json --max-turns 90
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load ANTHROPIC_API_KEY (and anything else) from the repo-root .env, so a run
# works without the key being exported in the calling shell. Same pattern as
# scripts/ablation_experiment.py, sycophancy_rerun.py, thematic_coding.py and
# moderator_drift_diagnostic.py; a real environment variable still wins, since
# load_dotenv() does not override variables that are already set.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _load_config(config_path: str) -> dict:
    return json.loads(Path(config_path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a synthetic focus group session to natural guide completion.")
    parser.add_argument("--config", required=True, help="Path to session config JSON")
    parser.add_argument("--max-turns", type=int, default=90, help="Safety cap on total turns")
    parser.add_argument("--mode", choices=["orchestrated", "emergent"], default=None)
    args = parser.parse_args()

    session_config = _load_config(args.config)

    from core.orchestrator import FocusGroupOrchestrator

    orchestrator = FocusGroupOrchestrator(session_config)
    state = orchestrator.state

    if args.mode is not None:
        state.session_meta.participation_mode = args.mode
    mode = state.session_meta.participation_mode

    session_id = state.session_meta.id
    n_sections = len(state.discussion_guide)
    print(f"Session {session_id} initialised. Participants: {', '.join(p.name for p in state.participants.values())}")
    print(f"Mode: {mode}. Guide sections: {n_sections}. Max turns (safety cap): {args.max_turns}")

    def all_sections_done() -> bool:
        return all(s.completed for s in orchestrator.state.discussion_guide)

    try:
        print("Running opening turn...")
        orchestrator.run_opening()

        step_i = 0
        while not all_sections_done() and step_i < args.max_turns:
            step_i += 1
            if mode == "emergent":
                orchestrator.run_conversation_step()
            else:
                orchestrator.run_full_turn()
            if step_i % 10 == 0:
                done = sum(1 for s in orchestrator.state.discussion_guide if s.completed)
                print(f"  ...step {step_i}, total_turns={orchestrator.state.session_meta.total_turns}, sections done={done}/{n_sections}")

        done = sum(1 for s in orchestrator.state.discussion_guide if s.completed)
        if all_sections_done():
            print(f"Guide completed naturally after {step_i} steps (total_turns={orchestrator.state.session_meta.total_turns}).")
        else:
            print(f"SAFETY CAP HIT at {step_i} steps — {done}/{n_sections} sections completed, guide did not finish naturally.")

    except KeyboardInterrupt:
        print("\nInterrupted — saving transcript and moderator log...")
    finally:
        orchestrator.save_transcript()
        orchestrator.save_moderator_log()

    state = orchestrator.state
    print(f"Total turns: {state.session_meta.total_turns}")
    sections_done = sum(1 for s in state.discussion_guide if s.completed)
    print(f"Sections completed: {sections_done}/{n_sections}")
    print(f"Saved to: {orchestrator.log_dir}")


if __name__ == "__main__":
    main()
