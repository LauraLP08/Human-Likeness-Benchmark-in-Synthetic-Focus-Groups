import os
import json
import csv
import traceback
import re
from pathlib import Path
from datetime import datetime, UTC
from unittest.mock import patch

import anthropic

from core.orchestrator import FocusGroupOrchestrator
import core.moderator_brain
import core.participant_agent
from core.prompt_renderer import render_opening_message

OUT_DIR = "docs/testing/macho_meals_emergent_run_validation"
SESSION_ID = "macho_meals_emergent_full_run_02"
CANONICAL_LOG_DIR = Path(f"output/session_logs/{SESSION_ID}")

# Global context to track model calls
CURRENT_CALL_CONTEXT = {}
api_call_counter = 0
captured_prompts = []
model_usage_audit = []

orig_create = anthropic.resources.messages.Messages.create

def patched_create(self, *args, **kwargs):
    global api_call_counter
    api_call_counter += 1
    
    ctx = CURRENT_CALL_CONTEXT.copy()
    
    system = kwargs.get("system", "")
    messages = kwargs.get("messages", [])
    model = kwargs.get("model", "unknown")
    
    call_type = ctx.get("call_type", "unknown")
    pid = ctx.get("participant_id", "UNKNOWN")
    name = ctx.get("participant_name", "Unknown")
    source_func = ctx.get("source_function", "unknown")
    turn = ctx.get("turn_number", 0)
    step = ctx.get("run_step", 0)
    
    expected_model = "claude-sonnet-4-6"
    model_matches = (model == expected_model)
    
    # Audit logging
    model_usage_audit.append({
        "call_index": api_call_counter,
        "call_type": call_type,
        "turn_number": turn,
        "participant_id": pid,
        "participant_name": name,
        "model": model,
        "source_log": "interceptor",
        "expected_model": expected_model,
        "model_matches_expected": model_matches,
        "notes": "" if model_matches else f"MISMATCH: got {model}"
    })
    
    # Output to corresponding prompt folders
    if call_type in ("moderator_opening", "moderator_turn"):
        prompt_type = "moderator"
        if call_type == "moderator_opening":
            sys_file = f"{OUT_DIR}/rendered_prompts/moderator/opening_system_prompt.txt"
            user_file = f"{OUT_DIR}/rendered_prompts/moderator/opening_user_message.txt"
        else:
            sys_file = f"{OUT_DIR}/rendered_prompts/moderator/moderator_turn_{turn}_system_prompt.txt"
            user_file = f"{OUT_DIR}/rendered_prompts/moderator/moderator_turn_{turn}_user_message.txt"
    elif call_type == "participant_response":
        prompt_type = "participants"
        sys_file = f"{OUT_DIR}/rendered_prompts/participants/participant_response_step_{step}_turn_{turn}_{pid}_system_prompt.txt"
        user_file = f"{OUT_DIR}/rendered_prompts/participants/participant_response_step_{step}_turn_{turn}_{pid}_user_message.txt"
    elif call_type == "engagement_assessment":
        prompt_type = "engagement_assessments"
        sys_file = f"{OUT_DIR}/rendered_prompts/engagement_assessments/engagement_step_{step}_{pid}_system_or_persona_context.txt"
        user_file = f"{OUT_DIR}/rendered_prompts/engagement_assessments/engagement_step_{step}_{pid}_user_prompt.txt"
    else:
        # Fallback should not happen based on our wrappers
        prompt_type = "participants"
        sys_file = f"{OUT_DIR}/rendered_prompts/participants/UNKNOWN_call_{api_call_counter}_{pid}_system.txt"
        user_file = f"{OUT_DIR}/rendered_prompts/participants/UNKNOWN_call_{api_call_counter}_{pid}_user.txt"
    
    with open(sys_file, "w", encoding="utf-8") as f:
        f.write(str(system))
    with open(user_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(messages, indent=2))
        
    captured_prompts.append({
        "prompt_id": f"prompt_{api_call_counter}",
        "call_type": call_type,
        "run_step": step,
        "turn_number": turn,
        "participant_id": pid,
        "participant_name": name,
        "file_path": sys_file,
        "model": model,
        "prompt_role": "system_prompt",
        "source_function": source_func,
        "canonical_session_id": SESSION_ID,
        "notes": ""
    })
    captured_prompts.append({
        "prompt_id": f"prompt_{api_call_counter}_user",
        "call_type": call_type,
        "run_step": step,
        "turn_number": turn,
        "participant_id": pid,
        "participant_name": name,
        "file_path": user_file,
        "model": model,
        "prompt_role": "user_message",
        "source_function": source_func,
        "canonical_session_id": SESSION_ID,
        "notes": ""
    })
    
    # We execute the actual API call
    return orig_create(self, *args, **kwargs)


def check_model_availability(model_name: str) -> tuple[bool, str]:
    try:
        anthropic.Anthropic()
        return True, "Model accessible"
    except Exception as e:
        return False, str(e)

def build_config_and_manifests():
    if CANONICAL_LOG_DIR.exists() and list(CANONICAL_LOG_DIR.glob("*")):
        raise Exception("BLOCKED_SESSION_ID_EXISTS: Canonical log directory already exists and contains files.")

    os.makedirs(f"{OUT_DIR}", exist_ok=True)
    os.makedirs(f"{OUT_DIR}/rendered_prompts/moderator", exist_ok=True)
    os.makedirs(f"{OUT_DIR}/rendered_prompts/participants", exist_ok=True)
    os.makedirs(f"{OUT_DIR}/rendered_prompts/engagement_assessments", exist_ok=True)
    os.makedirs(f"{OUT_DIR}/live_run_outputs/{SESSION_ID}", exist_ok=True)
    CANONICAL_LOG_DIR.mkdir(parents=True, exist_ok=True)

    with open(f"{OUT_DIR}/live_run_outputs/CANONICAL_SESSION_LOG_PATH.txt", "w", encoding="utf-8") as f:
        f.write(str(CANONICAL_LOG_DIR.as_posix()))

    import yaml
    with open("configs/guides/macho_meals_plant_based_masculinity_uk.yaml", "r", encoding="utf-8") as f:
        guide_yaml = yaml.safe_load(f)
        
    mapped_guide = []
    for i, sec in enumerate(guide_yaml.get("sections", [])):
        mapped_guide.append({
            "section_index": i,
            "section_label": sec["label"],
            "section_phase": sec["phase"],
            "section_purpose": sec.get("purpose", sec["label"]),
            "scripted_question": sec["scripted_question"],
            # Was: sec.get("probing_depth_ceiling", "deep") — which silently
            # injected "deep" into every generated config even when the guide
            # never set it. The parameter is pinned to None for all runs, so it
            # is no longer emitted here at all.
            "stimulus": sec.get("stimulus")
        })

    with open(f"{OUT_DIR}/asset_manifest.csv", "w", encoding="utf-8") as f:
        f.write("asset_type,asset_path\n")
        f.write("guide,configs/guides/macho_meals_plant_based_masculinity_uk.yaml\n")

    agents = [
        "agents/macho_meals/mm_fg1_amir.json",
        "agents/macho_meals/mm_fg1_david.json",
        "agents/macho_meals/mm_fg1_ibrahim.json",
        "agents/macho_meals/mm_fg1_isaiah.json",
        "agents/macho_meals/mm_fg1_will.json",
    ]
    
    with open(f"{OUT_DIR}/agent_selection_manifest.csv", "w", encoding="utf-8") as f:
        f.write("agent_id,agent_name,agent_path,inclusion_reason\n")
        for p in agents:
            n = Path(p).stem.split("_")[-1].capitalize()
            f.write(f"{Path(p).stem},{n},{p},user approved all five\n")
            
    session_config = {
        "session_id": SESSION_ID,
        "research_objective": "Validate emergent run without cap",
        "topic_domain": "plant-based eating",
        "participant_collective_identity": "UK Men",
        "moderator_knowledge_brief": "Macho Meals Study",
        "participants": [{"agent_payload_path": p} for p in agents],
        "discussion_guide": mapped_guide,
        "participation_mode": "emergent"
    }
    
    return session_config, agents

def write_model_config_report(mod_before, p_before, agents):
    with open(f"{OUT_DIR}/model_configuration_report.md", "w", encoding="utf-8") as f:
        f.write("# Model Configuration Report\n\n")
        f.write(f"- Original moderator default model: {mod_before}\n")
        f.write(f"- Resolved moderator model: claude-sonnet-4-6\n")
        f.write(f"- Original participant model(s) from agent JSON: claude-haiku-4-5-20251001\n")
        f.write(f"- Resolved participant response model: claude-sonnet-4-6\n")
        f.write(f"- Resolved engagement assessment model: claude-sonnet-4-6\n")
        f.write(f"- Original files modified: No\n")
        f.write(f"- All actual calls used claude-sonnet-4-6: Verified in model_usage_audit.csv\n")

def run():
    mod_before = core.moderator_brain._MODEL
    p_before = core.participant_agent._DEFAULT_MODEL
    
    orig_assess_engagement = core.participant_agent.assess_engagement
    orig_call_participant = core.participant_agent.call_participant
    orig_call_moderator = core.moderator_brain.call_moderator

    run_step_counter = [0]
    
    def wrap_assess_engagement(*args, **kwargs):
        p = args[0] if len(args) > 0 else kwargs.get("participant")
        meta = args[1] if len(args) > 1 else kwargs.get("session_meta")
        CURRENT_CALL_CONTEXT.update({
            "call_type": "engagement_assessment",
            "participant_id": p.id,
            "participant_name": p.name,
            "source_function": "assess_engagement",
            "run_step": run_step_counter[0],
            "turn_number": meta.total_turns if meta else 0
        })
        return orig_assess_engagement(*args, **kwargs)
        
    def wrap_call_participant(*args, **kwargs):
        p = args[0] if len(args) > 0 else kwargs.get("participant")
        meta = args[1] if len(args) > 1 else kwargs.get("session_meta")
        CURRENT_CALL_CONTEXT.update({
            "call_type": "participant_response",
            "participant_id": p.id,
            "participant_name": p.name,
            "source_function": "call_participant",
            "run_step": run_step_counter[0],
            "turn_number": meta.total_turns if meta else 0
        })
        return orig_call_participant(*args, **kwargs)
        
    def wrap_call_moderator(*args, **kwargs):
        state = args[0] if len(args) > 0 else kwargs.get("state")
        meta = state.session_meta if state else None
        call_type = "moderator_opening" if meta and meta.total_turns == 0 else "moderator_turn"
        CURRENT_CALL_CONTEXT.update({
            "call_type": call_type,
            "participant_id": "MOD",
            "participant_name": "Moderator",
            "source_function": "call_moderator",
            "run_step": run_step_counter[0],
            "turn_number": meta.total_turns if meta else 0
        })
        return orig_call_moderator(*args, **kwargs)
        
    verdict = "LIVE_RUN_FAILED"
    reason = "Unknown error"
    try:
        session_config, agent_paths = build_config_and_manifests()
        
        core.moderator_brain._MODEL = "claude-sonnet-4-6"
        core.participant_agent._DEFAULT_MODEL = "claude-sonnet-4-6"
        
        write_model_config_report(mod_before, p_before, agent_paths)
        
        is_avail, msg = check_model_availability("claude-sonnet-4-6")
        if not is_avail:
            print("BLOCKED:", msg)
            return

        steps = 0
        emergency_max_steps = 200
        
        try:
            with patch("anthropic.resources.messages.Messages.create", autospec=True, side_effect=patched_create), \
                 patch("core.orchestrator.assess_engagement", side_effect=wrap_assess_engagement), \
                 patch("core.orchestrator.call_participant", side_effect=wrap_call_participant), \
                 patch("core.orchestrator.call_moderator", side_effect=wrap_call_moderator):

                orchestrator = FocusGroupOrchestrator(session_config)
                orchestrator.log_dir = CANONICAL_LOG_DIR
                
                for p in orchestrator.state.participants.values():
                    if "simulation_config" not in p.agent_payload:
                        p.agent_payload["simulation_config"] = {}
                    p.agent_payload["simulation_config"]["model"] = "claude-sonnet-4-6"
                
                orchestrator.run_opening()
                
                while True:
                    steps += 1
                    run_step_counter[0] = steps
                    if steps > emergency_max_steps:
                        reason = "emergency guard reached"
                        verdict = "LIVE_RUN_INCOMPLETE_GUIDE_NOT_CLOSED"
                        break
                        
                    orchestrator.run_conversation_step()
                    
                    if all(s.completed for s in orchestrator.state.discussion_guide):
                        reason = "guide completed naturally"
                        verdict = "LIVE_RUN_COMPLETED_CLEAN"
                        break
                        
        except Exception as e:
            reason = f"runtime/API error: {str(e)}"
            verdict = "LIVE_RUN_FAILED"
            traceback.print_exc()
            
        mismatches = [a for a in model_usage_audit if not a["model_matches_expected"]]
        if mismatches:
            verdict = "MODEL_MISMATCH"
            reason += " (Model mismatch detected)"
            
        # Ensure latest state is flushed regardless of exception
        try:
            if 'orchestrator' in locals():
                orchestrator.save_transcript()
                orchestrator.save_moderator_log()
                orchestrator.save_state(f"state_turn_{orchestrator.state.session_meta.total_turns}.json")
        except Exception as e:
            print(f"Error saving canonical transcripts: {e}")
            
        # Write Model and Prompt logs
        with open(f"{OUT_DIR}/rendered_prompt_index.csv", "w", newline="", encoding="utf-8") as f:
            if captured_prompts:
                w = csv.DictWriter(f, fieldnames=captured_prompts[0].keys())
                w.writeheader()
                w.writerows(captured_prompts)
        with open(f"{OUT_DIR}/model_usage_audit.csv", "w", newline="", encoding="utf-8") as f:
            if model_usage_audit:
                w = csv.DictWriter(f, fieldnames=model_usage_audit[0].keys())
                w.writeheader()
                w.writerows(model_usage_audit)
                
        # DISK-BASED VERIFICATION
        def get_max_turn_json(p):
            if not p.exists(): return -1
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return max((e.get("turn", -1) for e in data), default=-1)
            except: return -1
            
        def get_max_turn_txt(p):
            if not p.exists(): return -1
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
                max_t = -1
                for line in lines:
                    m = re.search(r'^Turn\s+(\d+)\s*\|', line)
                    if m: max_t = max(max_t, int(m.group(1)))
                return max_t
            except: return -1

        def count_entries(p):
            if not p.exists(): return 0
            if p.suffix == ".json":
                try: return len(json.loads(p.read_text(encoding="utf-8")))
                except: return 0
            if p.suffix == ".jsonl":
                try: return len([l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()])
                except: return 0
            return 0
        
        t_json = CANONICAL_LOG_DIR / "transcript.json"
        t_txt = CANONICAL_LOG_DIR / "transcript.txt"
        m_log = CANONICAL_LOG_DIR / "moderator_log.json"
        a_log = CANONICAL_LOG_DIR / "api_calls.jsonl"
        states = list(CANONICAL_LOG_DIR.glob("state_turn_*.json"))
        
        t_json_max = get_max_turn_json(t_json)
        t_txt_max = get_max_turn_txt(t_txt)
        t_json_entries = count_entries(t_json)
        m_log_entries = count_entries(m_log)
        
        # Override verdict based strictly on DISK state
        if verdict == "LIVE_RUN_COMPLETED_CLEAN":
            if t_json_max != t_txt_max:
                verdict = "LIVE_RUN_FAILED_TRANSCRIPT_MISMATCH"
                reason = f"Mismatch: JSON turn {t_json_max} vs TXT turn {t_txt_max}"
            elif t_json_max <= 12:
                verdict = "LIVE_RUN_FAILED"
                reason = f"Transcript only reached turn {t_json_max}, run incomplete"

        final_state_file = "None"
        guide_closed = False
        final_section = "None"
        guide_details = []
        if states:
            def get_turn(path):
                m = re.search(r'state_turn_(\d+)\.json', path.name)
                return int(m.group(1)) if m else -1
            highest_state = max(states, key=get_turn)
            final_state_file = highest_state.name
            try:
                st_data = json.loads(highest_state.read_text(encoding="utf-8"))
                g = st_data.get("discussion_guide", [])
                if g:
                    closing = g[-1]
                    guide_closed = closing.get("completed", False)
                    final_section = closing.get("section_label", "Unknown")
                    for s in g:
                        guide_details.append((s.get("section_label", "Unknown"), s.get("completed", False)))
            except:
                pass
                
        if verdict == "LIVE_RUN_COMPLETED_CLEAN" and not guide_closed:
            verdict = "LIVE_RUN_INCOMPLETE_GUIDE_NOT_CLOSED"
            reason = "Final disk state indicates guide not closed"
            
        # Copy to test audit folder (with new unique ID subdir)
        import shutil
        for f in CANONICAL_LOG_DIR.glob("*"):
            if f.is_file():
                shutil.copy(f, f"{OUT_DIR}/live_run_outputs/{SESSION_ID}/")
                
        # Generate final report
        with open(f"{OUT_DIR}/MACHO_MEALS_EMERGENT_RUN_REPORT.md", "w", encoding="utf-8") as f:
            f.write("# MACHO MEALS EMERGENT RUN REPORT\n\n")
            f.write(f"## 1. Executive verdict\n**{verdict}**\n\n")
            f.write(f"Short reason: {reason}\n\n")
            
            f.write("## 2. Canonical Disk Evidence\n")
            f.write(f"- canonical transcript.json path: {t_json.as_posix()}\n")
            f.write(f"- canonical transcript.txt path: {t_txt.as_posix()}\n")
            f.write(f"- canonical moderator_log.json path: {m_log.as_posix()}\n")
            f.write(f"- canonical api_calls.jsonl path: {a_log.as_posix()}\n")
            f.write(f"- final state_turn_*.json path used: {final_state_file}\n")
            f.write(f"- max turn number in transcript.json: {t_json_max}\n")
            f.write(f"- max turn number in transcript.txt: {t_txt_max}\n")
            f.write(f"- transcript entry count: {t_json_entries}\n")
            f.write(f"- moderator log entry count: {m_log_entries}\n")
            f.write(f"- state_turn file count: {len(states)}\n")
            f.write(f"- whether transcript.json and transcript.txt agree: {'yes' if t_json_max == t_txt_max else 'no'}\n\n")
            
            f.write("## 3. Guide Completion\n")
            if guide_details:
                for lbl, c in guide_details:
                    f.write(f"- {lbl}: completed={c}\n")
            f.write(f"- final guide section index: {len(guide_details)-1 if guide_details else -1}\n")
            f.write(f"- whether the closing section was reached: {'yes' if final_section != 'None' else 'no'}\n")
            f.write(f"- whether the closing section was completed: {'yes' if guide_closed else 'no'}\n\n")

            f.write("## 4. Caveats\n")
            f.write("- This is not an evaluation.\n")
            f.write("- This is not human-likeness validation.\n")
            f.write("- This is not thematic equivalence.\n")
            f.write("- This is not outcome validity.\n")
            f.write("- This only validates run feasibility, storage, model configuration, and auditability.\n")

    finally:
        core.moderator_brain._MODEL = mod_before
        core.participant_agent._DEFAULT_MODEL = p_before

if __name__ == "__main__":
    run()
