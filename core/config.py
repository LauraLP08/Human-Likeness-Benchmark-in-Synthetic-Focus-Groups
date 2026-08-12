from typing import Final

URGENCY_THRESHOLD: Final[float] = 0.55
PEER_ADDRESS_BONUS: Final[float] = 0.15
MODERATOR_INVITE_BONUS: Final[float] = 0.15
CONSENSUS_RISK_CHALLENGE_PREFERENCE: Final[float] = 0.10
MAX_CONSECUTIVE_PARTICIPANT_TURNS: Final[int] = 6

# Reflection cadence (only relevant when session_meta.moderator_reflection_enabled=True,
# core/orchestrator.py run_moderator_turn): the two reflection summaries
# (core/session_state.py ModeratorReflection) regenerate at section/question
# boundaries only — i.e. whenever the moderator's action this turn was
# SECTION_TRANSITION. No turn-count fallback: per the tightened spec, a
# handful of summary calls per session, not a competing per-N-turns cadence.
# (Moderator turn-share itself, Piece 1, is unrelated to this cadence — it is
# a free, deterministic count updated every turn regardless of reflection
# cadence; see session_state.py's local _MODERATOR_OWN_SHARE_RECENT_WINDOW.)
