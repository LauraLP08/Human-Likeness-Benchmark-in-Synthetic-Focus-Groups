import json
from pathlib import Path
from datetime import datetime, UTC
from enum import Enum
from typing import Any

def _safe_serialize(val: Any) -> Any:
    if val is None:
        return "none"
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    return str(val)

def append_api_log(
    log_dir: Path,
    event_type: str,
    role: str,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    participant_id: str | None = None,
    participant_name: str | None = None,
    moderator_action: str | None = None,
    intervention_mode: str | None = None,
    selection_mode: str | None = None,
    validation_fallback: bool | None = None,
    source_function: str | None = None,
    token_accounting: bool | None = None,
    stop_reason: str | None = None,
    max_tokens: int | None = None,
    response_truncated: bool | None = None,
    metadata: dict[str, Any] | None = None
) -> None:
    """
    Unified API logging utility to track all Anthropic calls.
    """
    if not log_dir:
        return
        
    log_path = log_dir / "api_calls.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Calculate total if omitted but others are present
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": _safe_serialize(event_type),
        "role": _safe_serialize(role),
        "source_function": _safe_serialize(source_function)
    }
    
    if model is not None:
        entry["model"] = _safe_serialize(model)
    if input_tokens is not None:
        entry["input_tokens"] = input_tokens
    if output_tokens is not None:
        entry["output_tokens"] = output_tokens
    if total_tokens is not None:
        entry["total_tokens"] = total_tokens
        
    if participant_id is not None:
        entry["participant_id"] = _safe_serialize(participant_id)
    if participant_name is not None:
        entry["participant_name"] = _safe_serialize(participant_name)
    if moderator_action is not None:
        entry["moderator_action"] = _safe_serialize(moderator_action)
        # For backward compatibility with existing log schema parsing
        entry["action"] = _safe_serialize(moderator_action)
    if intervention_mode is not None:
        entry["intervention_mode"] = _safe_serialize(intervention_mode)
    if selection_mode is not None:
        entry["selection_mode"] = _safe_serialize(selection_mode)
    if validation_fallback is not None:
        entry["validation_fallback"] = _safe_serialize(validation_fallback)
    if token_accounting is not None:
        entry["token_accounting"] = _safe_serialize(token_accounting)
    if stop_reason is not None:
        entry["stop_reason"] = _safe_serialize(stop_reason)
    if max_tokens is not None:
        entry["max_tokens"] = max_tokens
    if response_truncated is not None:
        entry["response_truncated"] = _safe_serialize(response_truncated)
        
    if metadata:
        for k, v in metadata.items():
            entry[k] = _safe_serialize(v)
            
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
