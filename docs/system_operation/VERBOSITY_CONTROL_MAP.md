# Verbosity Control Map

This document identifies all current sources of verbosity in the system and proposes safe future intervention points. **No changes to verbosity have been made yet.**

## 1. Overview

Verbosity in the system stems from a combination of hard-coded token limits, prompt instructions, and emergent mode mechanics that allow participants to speak continuously without moderator interruption.

## 2. Verbosity Sources

| Verbosity Source | Where Configured | Current Value / Behavior | Affects | Deterministic / Model | How to Reduce Safely | Risk of Over-Reduction |
|------------------|------------------|--------------------------|---------|-----------------------|----------------------|------------------------|
| `max_tokens` (Moderator) | `core/moderator_brain.py` | `1500` | Moderator | Deterministic | Lower the constant in the python file. | Moderator JSON response might truncate, causing parse failures. |
| `max_tokens` (Participant) | `core/participant_agent.py` or `session_config` | Usually `400` (or set via payload) | Participant | Deterministic | Adjust `participant_response_max_tokens` in session config. | Responses get cut off mid-sentence. |
| Engagement Thresholds | `core/config.py` | `URGENCY_THRESHOLD` (e.g., `0.7`) | Transcript length | Deterministic | Raise threshold to require higher urgency before speaking. | Sessions stall with consecutive silence. |
| Participant Behavior Prompts | `core/participant_agent.py` | "Do not speak in a polished essay style... Some contributions may be brief" | Participant | Model-driven | Strengthen prompts to enforce brevity (e.g., "1-2 short sentences max"). | Loss of qualitative nuance or character voice. |
| Guide Probing Instructions | `prompts/01_MODERATOR_SYSTEM_PROMPT.md` | Moderator instructed to probe deeply. | Moderator/Transcript | Model-driven | Adjust prompt to require immediate progression after 1-2 probes. | Loss of depth in the transcript. |
| Maximum Consecutive Turns | `core/config.py` | `MAX_CONSECUTIVE_PARTICIPANT_TURNS` | Transcript length | Deterministic | Lower this limit to force faster moderator intervention. | Stifles natural participant-to-participant dialogue. |

## 3. Recommended Future Intervention Points

When the evaluation work resumes, the safest points to adjust verbosity without destabilizing the system are:

1. **Session Config (`participant_response_max_tokens`):** This is the safest deterministic control. By enforcing a strict token limit, participants cannot monologue.
2. **Participant Prompt Adjustments:** Reinforcing brevity in `_BEHAVIOUR_INSTRUCTIONS` (`core/participant_agent.py`) ensures the model *chooses* to be concise, avoiding hard API truncations.
3. **Emergent Limits (`MAX_CONSECUTIVE_PARTICIPANT_TURNS`):** Lowering this value will force the moderator to step in more frequently, preventing long chains of participant agreement.

## 4. Code vs Model Boundary Summary

- **Deterministic Code:** Token limits (`max_tokens`), consecutive turn limits, urgency thresholds.
- **Model-Decided:** Actual response length within the token limit, decision to probe vs transition section.

*Disclaimer: Changes to any of these parameters should be systematically tested before full deployment to avoid side effects like API validation failures.*
