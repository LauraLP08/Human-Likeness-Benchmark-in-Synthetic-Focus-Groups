"""
Stage 2: Controlled Live Pilot Harness

Execution harness for running emergent Model B focus group sessions using the Anthropic API.
Built for safety, auditability, and deterministic artifact preservation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path
from collections import Counter

# Must be able to import core from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orchestrator import FocusGroupOrchestrator, _OUTPUT_ROOT
from core.session_state import safe_enum_value


def _print_warning(msg: str) -> None:
    print("\n" + "=" * 72)
    print(f"WARNING: {msg}")
    print("=" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: Controlled Live Pilot Harness for Model B.")
    parser.add_argument("--config", required=False, default="configs/smoke_test_grocery.json", help="Path to session config JSON")
    parser.add_argument("--max-steps", type=int, default=10, help="Maximum number of orchestration steps to run")
    parser.add_argument("--run-id", type=str, default=None, help="Unique identifier for this run. Defaults to timestamped ID.")
    parser.add_argument("--dry-run", action="store_true", help="Validate config, check output path, save dry-run metadata, but do not call the API.")
    parser.add_argument("--confirm-live", action="store_true", help="Explicitly confirm live API execution, acknowledging associated costs.")
    
    args = parser.parse_args()

    # 1. API Safety Check
    if not args.dry_run and not args.confirm_live:
        _print_warning(
            "Live mode requires explicit confirmation.\n"
            "Execution will use the Anthropic API and incur real costs.\n"
            "Use --confirm-live to proceed, or --dry-run to validate locally."
        )
        sys.exit(1)

    if args.confirm_live and not args.dry_run:
        _print_warning("LIVE API CALLS ENABLED. THIS WILL INCUR ANTHROPIC API COSTS.")

    # 2. Config validation
    config_path = Path(args.config)
    if not config_path.exists() or not config_path.is_file():
        print(f"ERROR: Config path '{args.config}' is invalid or does not exist.")
        sys.exit(1)

    if args.max_steps <= 0:
        print(f"ERROR: --max-steps must be greater than 0. Received: {args.max_steps}")
        sys.exit(1)

    try:
        session_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse config JSON: {e}")
        sys.exit(1)

    # 3. Run ID safety and output path verification
    base_session_id = session_config.get("session_id", "session")
    
    if args.run_id:
        run_id = args.run_id
    else:
        timestamp_suffix = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        run_id = f"{base_session_id}_{timestamp_suffix}"

    if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
        print(f"ERROR: Unsafe run ID '{run_id}'. Only alphanumeric characters, dashes, and underscores are permitted.")
        sys.exit(1)

    output_dir = _OUTPUT_ROOT / run_id
    if output_dir.exists():
        print(f"ERROR: Output directory {output_dir} already exists. Silent overwrites are prohibited.")
        sys.exit(1)

    # Inject the safe run ID into the config before initializing orchestrator
    session_config["session_id"] = run_id
    session_config["participation_mode"] = "emergent"

    # Initialize Metadata
    started_at = datetime.now(UTC)
    steps_completed = 0
    ended_normally = False
    error_msg = None

    try:
        # 4. Initialize Orchestrator
        orchestrator = FocusGroupOrchestrator(session_config)
        
        # 5. Execution Loop
        if args.dry_run:
            print(f"DRY RUN: Initialised session {run_id} successfully.")
            print(f"Output directory established at: {orchestrator.log_dir}")
            ended_normally = True
        else:
            print(f"LIVE PILOT: Starting session {run_id} for up to {args.max_steps} steps.")
            # Opening turn
            orchestrator.run_opening()

            for step_i in range(1, args.max_steps + 1):
                print(f"=== STEP {step_i}/{args.max_steps} ===")
                orchestrator.run_conversation_step()
                steps_completed = step_i
            
            ended_normally = True

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Preserving state and exiting safely...")
        error_msg = "KeyboardInterrupt"
    except Exception as e:
        print(f"\n\nERROR during execution: {e}")
        error_msg = str(e)
    finally:
        # Note: If initialization fails, orchestrator might not be fully instantiated.
        # Check if orchestrator exists.
        if 'orchestrator' in locals() and hasattr(orchestrator, 'log_dir'):
            # Save original config
            config_used_path = orchestrator.log_dir / "config_used.json"
            config_used_path.write_text(json.dumps(session_config, indent=2), encoding="utf-8")

            if not args.dry_run:
                # Save transcripts and logs via existing hooks
                orchestrator.save_transcript()
                orchestrator.save_moderator_log()
            
            # Calculate metrics
            state = orchestrator.state
            ended_at = datetime.now(UTC)
            
            validation_fallback_count = 0
            intervention_counts = Counter()
            moderator_action_counts = Counter()
            for entry in state.moderator_log:
                if entry.validation_fallback:
                    validation_fallback_count += 1
                # 1. Properly count intervention modes
                mode_name = safe_enum_value(entry.intervention_mode)
                intervention_counts[mode_name] += 1
                # 2. Safe action extraction
                action_name = safe_enum_value(entry.action)
                moderator_action_counts[action_name] += 1
                
            selection_counts = Counter()
            for entry in state.transcript:
                if "selection_mode" in entry:
                    selection_counts[entry["selection_mode"]] += 1

            # 4. Count participant truncations from api_calls.jsonl
            participant_response_truncation_count = 0
            api_calls_path_str = str(orchestrator.log_dir / "api_calls.jsonl")
            if Path(api_calls_path_str).exists():
                with Path(api_calls_path_str).open("r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            log_entry = json.loads(line)
                            if log_entry.get("response_truncated") is True:
                                participant_response_truncation_count += 1
                        except json.JSONDecodeError:
                            pass

            # 5. Save final state explicitly
            state_dump_path = orchestrator.log_dir / "session_state_final.json"
            state_dump_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

            # 5. Build artifact_status map
            # We construct paths first to check their existence
            config_used_path_str = str(config_used_path)
            metadata_path_str = str(orchestrator.log_dir / "run_metadata.json")
            state_dump_path_str = str(state_dump_path)
            transcript_json_path_str = str(orchestrator.log_dir / "transcript.json")
            transcript_txt_path_str = str(orchestrator.log_dir / "transcript.txt")
            moderator_log_path_str = str(orchestrator.log_dir / "moderator_log.json")

            artifact_status = {
                "config_used": {
                    "path": config_used_path_str,
                    "exists": config_used_path.exists(),
                    "mode": "dry_run_and_live"
                },
                "run_metadata": {
                    "path": metadata_path_str,
                    "exists": True, # Written immediately after this
                    "mode": "dry_run_and_live"
                },
                "session_state_final": {
                    "path": state_dump_path_str,
                    "exists": state_dump_path.exists(),
                    "mode": "dry_run_and_live"
                },
                "transcript_json": {
                    "path": transcript_json_path_str,
                    "exists": Path(transcript_json_path_str).exists(),
                    "mode": "live_only"
                },
                "transcript_txt": {
                    "path": transcript_txt_path_str,
                    "exists": Path(transcript_txt_path_str).exists(),
                    "mode": "live_only"
                },
                "moderator_log": {
                    "path": moderator_log_path_str,
                    "exists": Path(moderator_log_path_str).exists(),
                    "mode": "live_only"
                },
                "api_calls": {
                    "path": api_calls_path_str,
                    "exists": Path(api_calls_path_str).exists(),
                    "mode": "live_only_if_api_calls_occur"
                }
            }

            # Build Metadata
            metadata = {
                "stage": "Stage 2 live pilot harness",
                "run_id": run_id,
                "original_session_id": base_session_id,
                "session_id": session_config["session_id"],
                "config_path": str(config_path),
                "dry_run": args.dry_run,
                "mode": "emergent",
                "max_steps_requested": args.max_steps,
                "steps_completed": steps_completed,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "ended_normally": ended_normally,
                "error": error_msg,
                "validation_fallback_count": validation_fallback_count,
                "participant_response_truncation_count": participant_response_truncation_count,
                "intervention_mode_counts": dict(intervention_counts),
                "moderator_action_counts": dict(moderator_action_counts),
                "selection_mode_counts": dict(selection_counts),
                "artifact_status": artifact_status,
                "transcript_path": transcript_json_path_str,
                "moderator_log_path": moderator_log_path_str,
                "state_output_directory": str(orchestrator.log_dir),
                "final_state_path": state_dump_path_str,
                "api_calls_path": api_calls_path_str
            }

            metadata_path = orchestrator.log_dir / "run_metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

            print(f"\n--- SESSION SUMMARY ---")
            print(f"Run ID: {run_id}")
            print(f"Dry Run: {args.dry_run}")
            print(f"Steps Completed: {steps_completed}/{args.max_steps}")
            print(f"Validation Fallbacks: {validation_fallback_count}")
            print(f"Participant Truncations: {participant_response_truncation_count}")
            print(f"Interventions: {dict(intervention_counts)}")
            print(f"Moderator Actions: {dict(moderator_action_counts)}")
            print(f"Selection Modes: {dict(selection_counts)}")
            print(f"Output directory: {orchestrator.log_dir}")
            print(f"Metadata saved to: {metadata_path}")
            if error_msg:
                sys.exit(1)


if __name__ == "__main__":
    main()
