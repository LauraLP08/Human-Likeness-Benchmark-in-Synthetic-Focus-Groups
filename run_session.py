"""
CLI entrypoint for running a complete synthetic focus group session.

Usage:
    python run_session.py --config examples/sample_session_config.json --turns 5
    python run_session.py --config examples/sample_session_config.json --turns 20 --mode emergent
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _load_config(config_path: str) -> dict:
    return json.loads(Path(config_path).read_text(encoding="utf-8"))


def _print_separator() -> None:
    print("\n" + "-" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a synthetic AI focus group session.")
    parser.add_argument("--config", required=True, help="Path to session config JSON")
    parser.add_argument("--turns", type=int, default=3, help="Number of turns/steps to run")
    parser.add_argument(
        "--mode",
        choices=["orchestrated", "emergent"],
        default=None,
        help="Participation mode override (default: value from session config)",
    )
    args = parser.parse_args()

    session_config = _load_config(args.config)

    # Import here so top-level errors surface before any heavy imports
    from core.orchestrator import FocusGroupOrchestrator

    orchestrator = FocusGroupOrchestrator(session_config)
    state = orchestrator.state

    # Determine participation mode: CLI flag overrides config
    if args.mode is not None:
        state.session_meta.participation_mode = args.mode
    mode = state.session_meta.participation_mode

    session_id = state.session_meta.id
    print(f"Session {session_id} initialised.")
    print(f"Participants: {', '.join(p.name for p in state.participants.values())}")
    print(f"Participation mode: {mode}")
    _print_separator()

    try:
        # Opening turn
        print("MODERATOR (opening):")
        opening = orchestrator.run_opening()
        print(opening)
        _print_separator()

        # Track transcript length before each step to print new entries
        prev_transcript_len = len(orchestrator.state.transcript)

        if mode == "emergent":
            for step_i in range(1, args.turns + 1):
                print(f"=== STEP {step_i} ===")
                result = orchestrator.run_conversation_step()
                step_type = result.get("step_type", "?")
                print(f"[{step_type}]")

                new_entries = orchestrator.state.transcript[prev_transcript_len:]
                for entry in new_entries:
                    speaker = entry.get("speaker_name") or entry.get("speaker_id", "?")
                    content = entry.get("content", "")
                    if entry.get("speaker_id") == "MODERATOR":
                        print(f"\nMODERATOR: {content}")
                    else:
                        print(f"\n{speaker.upper()}: {content}")
                prev_transcript_len = len(orchestrator.state.transcript)

                # Show engagement assessments
                assessments = orchestrator.state.group_state.last_engagement_round
                if assessments:
                    print("\n  [Engagement]", end="")
                    for a in assessments:
                        p = orchestrator.state.participants.get(a.participant_id)
                        name = p.name if p else a.participant_id
                        wants = "Y" if a.wants_to_speak else "N"
                        print(f"  {name}: {wants} u={a.urgency:.2f}", end="")
                    print()
                _print_separator()

        else:  # orchestrated
            for turn_i in range(1, args.turns + 1):
                print(f"=== ROUND {turn_i} ===")
                result = orchestrator.run_full_turn()

                new_entries = orchestrator.state.transcript[prev_transcript_len:]
                for entry in new_entries:
                    speaker = entry.get("speaker_name") or entry.get("speaker_id", "?")
                    content = entry.get("content", "")
                    if entry.get("speaker_id") == "MODERATOR":
                        print(f"\nMODERATOR: {content}")
                    else:
                        print(f"\n{speaker.upper()}: {content}")
                prev_transcript_len = len(orchestrator.state.transcript)
                _print_separator()

    except KeyboardInterrupt:
        print("\n\nInterrupted — saving transcript and moderator log...")
    finally:
        orchestrator.save_transcript()
        orchestrator.save_moderator_log()

    # Summary statistics
    state = orchestrator.state
    total_turns = state.session_meta.total_turns
    print("-" * 72)
    print("SESSION COMPLETE")
    print(f"Total moderator turns: {total_turns}")
    print()

    print("Participant participation:")
    all_p_turns = sum(p.turn_count for p in state.participants.values())
    for pid, p in state.participants.items():
        pct = round(p.turn_count / all_p_turns * 100, 1) if all_p_turns else 0
        print(f"  {p.name}: {p.turn_count} turns ({pct}%)")

    sections_done = sum(1 for s in state.discussion_guide if s.completed)
    print(f"\nSections completed: {sections_done}/{len(state.discussion_guide)}")

    action_counts: Counter = Counter(
        entry.action.value if entry.action else "observe_yield"
        for entry in state.moderator_log
    )
    print("\nModerator actions:")
    for action, count in sorted(action_counts.items()):
        print(f"  {action}: {count}")

    print(f"\nTranscript and logs saved to: {orchestrator.log_dir}")


if __name__ == "__main__":
    main()
