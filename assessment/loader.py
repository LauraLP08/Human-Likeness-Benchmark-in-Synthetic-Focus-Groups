import os
import json
from typing import Dict, Any

from .schema import SessionArtifacts

def load_json_file(path: str, errors: list, missing: list, filename: str, missing_req: list = None, missing_opt: list = None, optional: bool = False) -> Dict[str, Any]:
    if not os.path.exists(path):
        missing.append(filename)
        if optional and missing_opt is not None:
            missing_opt.append(filename)
        elif not optional and missing_req is not None:
            missing_req.append(filename)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Malformed JSON in {filename}: {str(e)}")
        return {}
    except Exception as e:
        errors.append(f"Error reading {filename}: {str(e)}")
        return {}

def load_jsonl_file(path: str, errors: list, missing: list, filename: str, missing_req: list = None, missing_opt: list = None, optional: bool = False) -> list:
    if not os.path.exists(path):
        missing.append(filename)
        if optional and missing_opt is not None:
            missing_opt.append(filename)
        elif not optional and missing_req is not None:
            missing_req.append(filename)
        return []
    result = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError as e:
                    errors.append(f"Malformed JSON in {filename} line {i+1}: {str(e)}")
        return result
    except Exception as e:
        errors.append(f"Error reading {filename}: {str(e)}")
        return []

def load_session_artifacts(session_dir: str, is_human_baseline: bool = False) -> SessionArtifacts:
    run_id = os.path.basename(os.path.normpath(session_dir))
    artifacts = SessionArtifacts(session_dir=session_dir, run_id=run_id)
    
    transcript = load_json_file(os.path.join(session_dir, "transcript.json"), artifacts.load_errors, artifacts.missing_files, "transcript.json", artifacts.missing_required_files, artifacts.missing_optional_files, False)
    if isinstance(transcript, list):
        artifacts.transcript = transcript
        
    mod_log_optional = is_human_baseline
    mod_log = load_json_file(os.path.join(session_dir, "moderator_log.json"), artifacts.load_errors, artifacts.missing_files, "moderator_log.json", artifacts.missing_required_files, artifacts.missing_optional_files, mod_log_optional)
    if isinstance(mod_log, list):
        artifacts.moderator_log = mod_log
        
    metadata_optional = is_human_baseline
    artifacts.run_metadata = load_json_file(os.path.join(session_dir, "run_metadata.json"), artifacts.load_errors, artifacts.missing_files, "run_metadata.json", artifacts.missing_required_files, artifacts.missing_optional_files, metadata_optional)
    artifacts.session_state_final = load_json_file(os.path.join(session_dir, "session_state_final.json"), artifacts.load_errors, artifacts.missing_files, "session_state_final.json", artifacts.missing_required_files, artifacts.missing_optional_files, metadata_optional)
    artifacts.config_used = load_json_file(os.path.join(session_dir, "config_used.json"), artifacts.load_errors, artifacts.missing_files, "config_used.json", artifacts.missing_required_files, artifacts.missing_optional_files, True)
    
    api_calls_path = os.path.join(session_dir, "api_calls.jsonl")
    artifacts.api_calls = load_jsonl_file(api_calls_path, artifacts.load_errors, artifacts.missing_files, "api_calls.jsonl", artifacts.missing_required_files, artifacts.missing_optional_files, True)
    
    if is_human_baseline:
        guide = load_json_file(os.path.join(session_dir, "guide.json"), artifacts.load_errors, artifacts.missing_files, "guide.json", artifacts.missing_required_files, artifacts.missing_optional_files, True)
        if guide:
            artifacts.session_state_final = {"discussion_guide": guide.get("sections", [])}
            
    return artifacts
