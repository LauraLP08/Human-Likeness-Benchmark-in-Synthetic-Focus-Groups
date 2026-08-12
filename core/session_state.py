# core/session_state.py
#
# The canonical data model for a focus group session.
# Every field referenced in the prompt files is defined here.
# All session state mutations go through these models.
#
# Dependencies: pip install pydantic>=2.0

from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def safe_enum_value(value: Any, none_value: str = "none") -> str | None:
    """Safely extract the string value from an optional Enum."""
    if value is None:
        return none_value
    return value.value if hasattr(value, "value") else str(value)


_ANNOTATION_RE = re.compile(r'^\(.*\)$|^\[.*\]$|^\{.*\}$')
_ALPHA_RE = re.compile(r'[a-zA-ZÀ-ɏ]')


def count_words(text: str) -> int:
    """
    Count words per the project's uniform word-counting rule
    (docs/length_measurement_rule.md) — a whitespace-delimited token counts
    if it contains at least one alphabetic character and is not wholly a
    transcription annotation ((.), [inaudible], {laughs}, etc.). Defined
    here (not imported) so this foundational data-model layer stays
    dependency-free of other core/ modules; core/prompt_renderer.py imports
    it from here for the time-budget status line.
    """
    return sum(
        1 for token in text.split()
        if _ALPHA_RE.search(token) and not _ANNOTATION_RE.match(token)
    )


# ---------------------------------------------------------------------------
# Enumerations — these are the typed vocabularies the prompts reference
# ---------------------------------------------------------------------------

class SectionPhase(str, Enum):
    INTRO = "intro"
    CONTEXT = "context"
    MAIN_TOPIC = "main_topic"
    STIMULUS = "stimulus"
    CLOSING = "closing"


class ProbingDepthCeiling(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    DEEP = "deep"


class ModeratorAction(str, Enum):
    ASK_INITIAL_TO_GROUP = "ask_initial_to_group"
    DIRECT_PROBE = "direct_probe"
    REDIRECT_TO_GROUP = "redirect_to_group"
    INVITE_DISSENT = "invite_dissent"
    SYNTHESIZE_AND_CHALLENGE = "synthesize_and_challenge"
    REACTIVATE_SILENT = "reactivate_silent"
    REFLECT_CONTRADICTION = "reflect_contradiction"
    INTRODUCE_STIMULUS = "introduce_stimulus"
    SECTION_TRANSITION = "section_transition"
    REFOCUS_TO_GUIDE = "refocus_to_guide"
    STAY_SILENT = "stay_silent"
    INVITE_TO_SPEAK = "invite_to_speak"


class ProbeType(str, Enum):
    SPECIFICITY = "specificity"
    EMOTIONAL_DEPTH = "emotional_depth"
    BEHAVIOURAL_GROUNDING = "behavioural_grounding"
    CONTRADICTION_SURFACE = "contradiction_surface"
    TRADE_OFF_EXPLORATION = "trade_off_exploration"
    SOCIAL_INFLUENCE = "social_influence"
    MEANING_CLARIFICATION = "meaning_clarification"


class FollowUpIntensity(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    DEEP = "deep"


class DominantSignal(str, Enum):
    RESPONSE_NEEDS_PROBING = "response_needs_probing"
    PARTICIPATION_IMBALANCE = "participation_imbalance"
    CONSENSUS_RISK = "consensus_risk"
    CONTRADICTION_PENDING = "contradiction_pending"
    SECTION_COMPLETE = "section_complete"
    EMOTIONAL_REGISTER = "emotional_register"
    GUIDE_QUESTION_PENDING = "guide_question_pending"
    SILENCE_DETECTED = "silence_detected"
    CONFLICT_DETECTED = "conflict_detected"


class TriggerEventType(str, Enum):
    PARTICIPANT_RESPONSE = "participant_response"
    SESSION_START = "session_start"
    STIMULUS_PRESENTED = "stimulus_presented"
    SILENCE_DETECTED = "silence_detected"


class ResponseQuality(str, Enum):
    RICH = "rich"           # Specific example, emotional context, complete reasoning
    ADEQUATE = "adequate"   # Answers the question but lacks depth
    SHALLOW = "shallow"     # Generic or socially scripted
    INCOMPLETE = "incomplete"  # Started but didn't resolve


class EngagementSignal(str, Enum):
    ACTIVE = "active"
    MODERATE = "moderate"
    PASSIVE = "passive"
    WITHDRAWN = "withdrawn"


class ModeratorReflection(BaseModel):
    """
    Two short, regenerated-fresh LLM summaries produced at section/question
    boundaries when moderator_reflection_enabled=True. This is Piece 2 of
    the reflection mechanism (docs/changes/2026-06-30_moderator_dedup_A_reflection.md);
    Piece 1 (moderator turn-share) is a deterministic GroupState field, not
    part of this model — see GroupState.moderator_turn_share_overall /
    moderator_turn_share_recent.

    One-channel rule: this model intentionally does NOT include coverage or
    participation-balance fields — both are already available to the
    moderator via DiscussionGuideSection.completed and GroupState's existing
    participation fields respectively. Restating them here, even reworded,
    would be derived-signal duplication (the same failure class as the
    participant-memory bug, one level up).

    Regenerated fresh from the transcript at each boundary — NOT built from
    moderator_log's windowed-and-then-discarded justifications (that path
    was considered and abandoned: it would have re-created the duplication
    concern this mechanism exists to avoid).
    """
    discussion_summary: str = Field(
        ...,
        description=(
            "ONE paragraph, <=80 words. A THEMATIC synthesis of which ideas/themes "
            "participants' answers have revolved around so far. Must abstract to "
            "themes, not recap who-said-what in sequence. Good: 'answers centered "
            "on convenience and peer judgment.' Forbidden (recap, not synthesis): "
            "'David said X, then Sam said Y.'"
        ),
    )
    strategy_summary: str = Field(
        ...,
        description=(
            "ONE paragraph, <=80 words. A synthesis of the moderator's own "
            "reasoning/approach so far: what you have been trying to do, and "
            "whether it is working."
        ),
    )


class SectionSummary(BaseModel):
    """
    One completed section's accumulated reflection record (2026-06-30,
    docs/changes/2026-06-30_full_session_cost_fix.md, Part 0).

    GroupState.section_summaries accumulates one of these per completed
    section — the shared compression substrate reused by the moderator's
    regular decision-call context (Part 1: accumulated summaries +
    current-section verbatim, instead of the full raw transcript) and by
    the reflection mechanism itself (Part 3: each new reflection call
    summarizes only the content since the prior one, carrying these
    accumulated summaries forward for continuity instead of re-reading the
    whole transcript).

    Replaces the single-slot, overwritten-each-section
    GroupState.last_reflection field that existed before this date — see
    docs/findings/2026-06-30_full_session_token_growth_issue.md's
    verification addendum, Q3/Q4, for why the single-slot version could not
    serve as a real compression substrate (only the most recent section's
    summary was ever retrievable from live state).
    """
    section_index: int
    section_label: str
    discussion_summary: str
    strategy_summary: str


# ---------------------------------------------------------------------------
# Discussion Guide
# ---------------------------------------------------------------------------

class StimulusConfig(BaseModel):
    """An indirect probing stimulus (vignette, ranking, hypothetical)."""
    stimulus_type: str = Field(..., description="vignette | ranking | hypothetical | card_sort")
    description: str = Field(..., description="The stimulus content or instruction")
    introduction_cue: str = Field(..., description="How the moderator introduces it naturally")


class DiscussionGuideSection(BaseModel):
    section_index: int
    section_label: str = Field(..., description="Human-readable label for this section")
    section_phase: SectionPhase
    section_purpose: str = Field(..., description="What research work this section does")
    scripted_question: str = Field(..., description="The researcher's intended question verbatim")
    probing_depth_ceiling: ProbingDepthCeiling | None = None
    stimulus: StimulusConfig | None = None
    completed: bool = False
    suggested_probes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------

class ParticipantState(BaseModel):
    id: str = Field(..., description="e.g. 'P1', 'P2'")
    name: str
    profile_summary: str = Field(default="", description="Brief relevant profile for this participant")
    # Full raw agent JSON when loaded from an external platform file; empty for inline participants
    agent_payload: dict = Field(default_factory=dict)

    # Tracked during the session
    turn_count: int = 0
    emotional_signal: str | None = Field(
        None,
        description="Free-text description of any active emotional signal, e.g. 'guilt about price choices'"
    )
    follow_up_count_current_question: int = 0

    @property
    def has_spoken(self) -> bool:
        return self.turn_count > 0


# ---------------------------------------------------------------------------
# Group State
# ---------------------------------------------------------------------------

class UnresolvedTension(BaseModel):
    participant_id: str
    flagged_at_turn: int
    description: str
    resolved: bool = False
    resolved_at_turn: int | None = None
    surfaced: bool = False
    surface_count: int = 0


class ParticipantEngagementAssessment(BaseModel):
    participant_id: str
    wants_to_speak: bool
    urgency: float = Field(ge=0.0, le=1.0)
    hook: str = Field(
        default="",
        description="What in the conversation is prompting this participant to speak. Empty if wants_to_speak False.",
    )
    addressed_to: str | None = Field(
        default=None,
        description="Name of a specific participant addressed by this response (resolved via _resolve_name_to_id by the orchestrator)."
    )
    intent: Literal["respond", "challenge", "affirm_and_elaborate", "introduce_new_angle", "stay_silent"] | None = Field(
        default=None,
        description="Categorical assessment of the participant's intent. Only 'challenge' impacts routing dynamically; others are for qualitative audit data."
    )


class GroupState(BaseModel):
    participation_balance: dict[str, float] = Field(
        default_factory=dict,
        description="participant_id -> share of total turns (0.0 to 1.0). Sum = 1.0"
    )
    silent_participants: list[str] = Field(
        default_factory=list,
        description="IDs of participants below the 15% participation threshold"
    )
    consensus_risk: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="0.0 = no consensus risk, 1.0 = complete artificial harmony"
    )
    dominant_voices: list[str] = Field(
        default_factory=list,
        description="IDs of participants who have taken >50% of turns in the current section"
    )
    unresolved_tensions: list[UnresolvedTension] = Field(
        default_factory=list,
        description="Contradictions or tensions flagged but not yet surfaced"
    )
    group_has_agreed_easily_on: list[str] = Field(
        default_factory=list,
        description="Topics where the group has converged without sufficient tension"
    )
    section_turn_counts: dict[str, int] = Field(
        default_factory=dict,
        description="participant_id -> turn count within the CURRENT section only. Resets on section_transition."
    )
    section_word_counts: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "participant_id (or 'MODERATOR') -> word count within the CURRENT "
            "section only. Mirrors section_turn_counts exactly — incremented "
            "wherever a transcript entry is appended, reset on "
            "section_transition. Always bookkept regardless of "
            "session_meta.time_budget_tracking_enabled (cheap, deterministic, "
            "same as section_turn_counts) — only the prompt-injection helper "
            "that reads it is gated behind that flag."
        )
    )
    completed_section_turn_counts: dict[int, dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "section_index (of the section being closed) -> a snapshot of "
            "section_turn_counts taken immediately before it's reset on "
            "SECTION_TRANSITION. Without this archive, the participant whose "
            "turn triggers the transition has their count incremented and then "
            "wiped by the same-call reset before any state snapshot can observe "
            "it — see docs/changes/ for the sandbox pilot that surfaced this."
        )
    )
    completed_section_word_counts: dict[int, dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "section_index (of the section being closed) -> a snapshot of "
            "section_word_counts taken immediately before it's reset on "
            "SECTION_TRANSITION. Mirrors completed_section_turn_counts exactly."
        )
    )
    consecutive_silent_turns: int = Field(
        0,
        description="Number of consecutive participant turns where the moderator chose stay_silent"
    )
    consecutive_participant_turns: int = Field(
        0,
        description="Number of consecutive participant turns without a visible moderator intervention (speak)"
    )
    last_speaker_id: str | None = Field(
        None,
        description="ID of the last participant or 'MODERATOR' who produced an utterance"
    )
    last_engagement_round: list[ParticipantEngagementAssessment] = Field(
        default_factory=list,
        description="Engagement assessments from the most recent run_conversation_step call"
    )
    section_summaries: list[SectionSummary] = Field(
        default_factory=list,
        description=(
            "Accumulated, one-per-completed-section reflection records "
            "(Piece 2 of the reflection mechanism; 2026-06-30 cost-fix Part "
            "0). Only ever populated when "
            "session_meta.moderator_reflection_enabled=True. Each "
            "completed section APPENDS one entry — replaces the older "
            "single-slot last_reflection field, which overwrote rather "
            "than accumulated (see "
            "docs/changes/2026-06-30_full_session_cost_fix.md). Stripped "
            "from to_prompt_json()'s output entirely when the toggle is "
            "False."
        ),
    )
    moderator_turn_share_overall: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Piece 1 of the reflection mechanism (2026-06-30): the "
            "moderator's own share of all turns so far (speak-mode "
            "moderator_log entries / total moderator_log entries). "
            "Deterministic count, no LLM call, updated every turn in "
            "apply_moderator_response() — the same cheap way "
            "participation_balance is computed for participants. This is "
            "the cause-C fix (GroupState tracked every participant's share "
            "but had no field for the moderator's own). Stripped from "
            "to_prompt_json()'s output entirely when "
            "session_meta.moderator_reflection_enabled is False."
        ),
    )
    moderator_turn_share_recent: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Same as moderator_turn_share_overall but windowed to the most "
            "recent MODERATOR_OWN_SHARE_RECENT_WINDOW moderator_log "
            "entries (core/config.py) — a more responsive signal than the "
            "session-wide average. Same computation and visibility rules "
            "as moderator_turn_share_overall."
        ),
    )

    @field_validator("consensus_risk")
    @classmethod
    def validate_consensus_risk(cls, v: float) -> float:
        return round(v, 3)


# ---------------------------------------------------------------------------
# Moderator Log
# ---------------------------------------------------------------------------

class QueuedNextAction(BaseModel):
    action: ModeratorAction
    target: str
    rationale: str
    condition: str = Field(..., description="What must be true in the next response for this to execute")


class ModeratorLogEntry(BaseModel):
    turn: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trigger: DominantSignal | None = None
    situation_assessment: str | None = None
    action: ModeratorAction | None = None
    target: str | None = None
    probe_type: ProbeType | None = None
    follow_up_intensity: FollowUpIntensity | None = None
    queued_next_action: QueuedNextAction | None = None
    intervention_mode: str = "speak"
    utterance: str
    # Compressed flag: set True when this entry has been summarised for context window management
    compressed: bool = False
    # Set True when the response was a system fallback (validation failed after retry)
    validation_fallback: bool = False
    selection_mode: str | None = Field(
        default=None,
        description="How the speaker was selected (urgency_self_selection, addressed_by_peer, moderator_invited, silence_fallback, orchestrated_round_robin)"
    )


# ---------------------------------------------------------------------------
# Session Metadata
# ---------------------------------------------------------------------------

class SessionMeta(BaseModel):
    id: str
    research_objective: str
    topic_domain: str
    participant_collective_identity: str = Field(
        ...,
        description="The shared category participants represent (e.g. 'urban commuters')"
    )
    moderator_knowledge_brief: str = Field(
        ...,
        description="What the moderator is permitted to know. Does NOT include researcher hypotheses."
    )
    researcher_notes: str = ""
    temperature: float = Field(
        1.0,
        description="Session-level API temperature applied uniformly to all participants in this run"
    )
    participant_response_max_tokens: int | None = Field(
        default=None,
        description="Optional ceiling on participant response length to prevent truncated turns"
    )
    participation_mode: str = Field(
        default="orchestrated",
        description="orchestrated | emergent",
    )
    moderator_model: str = Field(
        default="claude-sonnet-4-6",
        description="Model for all moderator API calls. Overridable per session config.",
    )
    initial_session_plan: dict | None = None

    current_section_index: int = 0
    section_phase: SectionPhase = SectionPhase.INTRO
    current_question_index: int = 0
    total_turns: int = 0
    session_started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inject_participant_intro: bool = Field(
        default=False,
        description="When true, include each intro-eligible agent's opening_intro.text in their system prompt."
    )
    run_label: str | None = Field(
        default=None,
        description=(
            "Optional recording-only label identifying this run (e.g. a "
            "replication group tag). Has NO effect on generation — the "
            "Anthropic API has no seed parameter and hosted-LLM output is "
            "non-deterministic. For organizing/labelling replicated runs only. "
            "(Renamed from generation_seed 2026-06-29: the prior name falsely "
            "implied a determinism control the system cannot have — see "
            "docs/changes/2026-06-29_rename_seed_to_run_label.md.)"
        ),
    )
    participant_episodic_depth: Literal["full", "since_last_n", "recent_k"] = Field(
        default="full",
        description=(
            "How much prior session context a participant receives. 'full': entire "
            "session since start, delivered incrementally (entries since this "
            "participant last spoke), no fixed window, no duplication. 'since_last_n': "
            "same incremental delivery, capped at participant_episodic_since_last_n "
            "entries per turn. 'recent_k': legacy sliding window of the last "
            "participant_episodic_recent_k transcript entries, stateless (no "
            "accumulated history) — kept for depth-comparison experiments, not "
            "recommended as a default. Default is 'full' because current sessions are "
            "short (~15-22 turns); this is not an assumption that more context is "
            "always better (Bhattacharyya: persona-manifold collapse risk at depth is "
            "an open, testable question, not a foregone conclusion)."
        ),
    )
    participant_episodic_since_last_n: int = Field(
        default=10,
        description="Cap on new entries per turn when participant_episodic_depth='since_last_n'.",
    )
    participant_episodic_recent_k: int = Field(
        default=6,
        description="Window size when participant_episodic_depth='recent_k'.",
    )
    moderator_reflection_enabled: bool = Field(
        default=False,
        description=(
            "Toggle for the moderator's across-turn reflection mechanism "
            "(2026-06-30). When True, a periodic synthesis call (at section "
            "transitions and every MODERATOR_REFLECTION_CADENCE_TURNS turns) "
            "produces a ModeratorReflection — a fresh, compact synthesis of "
            "discussion coverage, energy, participation balance, and "
            "crucially the moderator's OWN recent turn-share — injected into "
            "subsequent turns until superseded by the next reflection. "
            "Default False: OFF must reproduce current behavior exactly. "
            "Independently toggleable from moderator_restraint_prompt so "
            "their effects on over-intervention can be attributed separately "
            "(docs/changes/2026-06-30_moderator_dedup_A_reflection.md)."
        ),
    )
    moderator_restraint_prompt: bool = Field(
        default=False,
        description=(
            "Toggle for an added restraint block in the moderator system "
            "prompt (2026-06-30), balancing the existing 'be active' "
            "language found one-sided in "
            "docs/changes/2026-06-30_moderator_overintervention_diagnostic.md "
            "(Candidate A). When True, prompts/05_MODERATOR_RESTRAINT_BLOCK.md "
            "is appended to the system prompt. Does not remove or weaken any "
            "existing rule. Default False: OFF must reproduce current "
            "behavior exactly. Independently toggleable from "
            "moderator_reflection_enabled so their effects can be attributed "
            "separately."
        ),
    )
    moderator_context_mode: Literal["summarized", "full"] = Field(
        default="full",
        description=(
            "Controls what conversational context the moderator's regular "
            "decision call receives (2026-06-30 cost fix, Part 1). 'full' "
            "(default): the entire untrimmed transcript, as before this "
            "field existed — behavior-preserving, no existing config is "
            "affected. 'summarized': only the verbatim transcript of the "
            "current section, plus the accumulated thematic summaries "
            "(GroupState.section_summaries) for every completed section — "
            "a deliberate reversal of the prior 'moderator should see the "
            "full transcript, it is not context-starved' decision "
            "(docs/changes/2026-06-30_moderator_review.md), made explicit "
            "and validated once the full-transcript approach's cost was "
            "quantified at full-session length (~61% of total run cost; "
            "docs/findings/2026-06-30_full_session_token_growth_issue.md). "
            "Intended for full natural-completion sessions; 'summarized' "
            "without moderator_reflection_enabled=True produces an empty "
            "summary list and the moderator sees only the current section "
            "with no cross-section continuity — a known, undesirable "
            "combination, not silently prevented."
        ),
    )
    engagement_own_history_token_budget: int | None = Field(
        default=None,
        description=(
            "Caps the TOKEN size (not just entry count) of "
            "participant_own_turns fed to assess_engagement() (2026-06-30 "
            "cost fix, Part 2). Default None: legacy behavior — only the "
            "existing entry-count cap (_MAX_PARTICIPANT_HISTORY=15, "
            "core/orchestrator.py) applies, exactly as before this field "
            "existed; every existing short-session config is unaffected. "
            "When set, applied AFTER the 15-entry slice: keeps the MOST "
            "RECENT entries that fit within the budget (approximate "
            "char-count/4 estimate, no extra API call), always keeping at "
            "least the single most recent entry even if it alone exceeds "
            "the budget. This targets the verified dominant driver of "
            "engagement-call growth (own_history: 60->4,454 tokens, ~74x, "
            "docs/findings/2026-06-30_full_session_token_growth_issue.md) "
            "while preserving the field's repetition-suppression purpose "
            "for RECENT points — the ones most likely to be re-raised — at "
            "the cost of visibility into very old own-turns in long "
            "sessions, a deliberate, bounded trade-off, not a blind cut."
        ),
    )
    moderator_prompt_override: str | None = Field(
        default=None,
        description=(
            "Sandbox mechanism (INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md): "
            "filename (relative to prompts/) passed as "
            "core.prompt_renderer.load_system_prompt's prompt_override_filename. "
            "Default None: production behavior, byte-identical to before this "
            "field existed — 01_MODERATOR_SYSTEM_PROMPT.md is always used."
        ),
    )
    moderator_opening_prompt_override: str | None = Field(
        default=None,
        description=(
            "Sandbox mechanism, same rationale as moderator_prompt_override: "
            "filename (relative to prompts/) passed as "
            "core.prompt_renderer.render_opening_message's "
            "opening_prompt_override_filename. Default None: production "
            "behavior, byte-identical — 03_SESSION_OPENING_PROMPT.md is "
            "always used."
        ),
    )
    time_budget_tracking_enabled: bool = Field(
        default=False,
        description=(
            "Sandbox mechanism: when True, render_turn_message injects a "
            "{SECTION_BUDGET_STATUS} line into the 02 template reporting "
            "words/turns used against SessionMeta.initial_session_plan.time_budget. "
            "Default False: the line is omitted entirely (not rendered empty) "
            "— production template output is byte-identical to before this "
            "field existed. GroupState.section_word_counts is bookkept "
            "unconditionally regardless of this flag; only the prompt "
            "injection is gated."
        ),
    )


# Number of recent moderator log entries sent to the moderator in the live context window.
# Set to 3 for short-term strategic memory and as a fallback when structured state fields are
# incomplete. Review this value once feedback loop reliability is confirmed in trials — at that
# point 1 may be sufficient.
_MODERATOR_LOG_LIVE_WINDOW = 3

# Recent-window size for moderator_turn_share_recent (2026-06-30). Local
# constant, mirroring core.config.MODERATOR_OWN_SHARE_RECENT_WINDOW —
# session_state.py has no dependency on core.config (foundational data-model
# layer), so this is defined independently here rather than imported.
_MODERATOR_OWN_SHARE_RECENT_WINDOW = 10


# ---------------------------------------------------------------------------
# Root Session State
# ---------------------------------------------------------------------------

class SessionState(BaseModel):
    """
    The complete, living state of a focus group session.
    Serialised to JSON and injected into every moderator API call.
    Validated after every state mutation.
    """
    schema_version: int = 3
    session_meta: SessionMeta
    discussion_guide: list[DiscussionGuideSection]
    participants: dict[str, ParticipantState] = Field(
        ...,
        description="Keyed by participant ID (e.g. 'P1')"
    )
    group_state: GroupState = Field(default_factory=GroupState)
    moderator_log: list[ModeratorLogEntry] = Field(default_factory=list)

    # Full conversation transcript — every utterance, not just moderator turns
    transcript: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {turn, speaker_id, speaker_name, content, timestamp}"
    )

    @model_validator(mode="after")
    def validate_participation_balance(self) -> "SessionState":
        """Keep participation_balance in sync with participant turn counts."""
        total = sum(p.turn_count for p in self.participants.values())
        if total > 0:
            self.group_state.participation_balance = {
                pid: round(p.turn_count / total, 3)
                for pid, p in self.participants.items()
            }
        return self

    @property
    def current_section(self) -> DiscussionGuideSection:
        return self.discussion_guide[self.session_meta.current_section_index]

    @property
    def active_participant_ids(self) -> list[str]:
        return list(self.participants.keys())

    def to_prompt_json(self, compress_before_turn: int | None = None) -> str:
        """
        Serialise to the JSON string injected into the moderator prompt.
        Optionally compress old moderator_log entries to save tokens.
        agent_payload is excluded from all participant representations so that
        psychological dimension names do not reach the moderator model.
        """
        data = self.model_dump(mode="json")

        # Strip agent_payload from every participant — moderator sees only
        # behavioural tracking fields, not raw persona scores or dimension names.
        _MODERATOR_PARTICIPANT_FIELDS = {
            "id", "name", "turn_count", "emotional_signal",
            "follow_up_count_current_question",
        }
        for pid, p_data in data.get("participants", {}).items():
            keys_to_remove = [k for k in p_data if k not in _MODERATOR_PARTICIPANT_FIELDS]
            for k in keys_to_remove:
                del p_data[k]

        # Trim moderator_log for the live context.
        # The moderator receives only the 3 most recent entries. This is sufficient for:
        #   - honouring or abandoning queued_next_action
        #   - short-term strategic awareness of recent moderation direction
        #   - fallback context when structured state fields have not been fully populated
        # The full log is preserved in the Python object and saved to disk for research audit purposes.
        if data.get("moderator_log"):
            data["moderator_log"] = data["moderator_log"][-_MODERATOR_LOG_LIVE_WINDOW:]

        # De-duplication fix (2026-06-30): strip `utterance` from the live
        # moderator_log window. For any turn where the moderator actually
        # spoke, that exact text is already present, once, as a native
        # MODERATOR entry in `transcript` (never trimmed — see the class
        # docstring above). Leaving `utterance` in moderator_log[-3:] meant
        # the model's own last-3 utterances were serialized into the same
        # prompt twice — the same class of bug fixed for participants on
        # 2026-06-29, here capped at 3 entries rather than accumulating. The
        # reasoning fields (situation_assessment,
        # dominant_signal, action, target, queued_next_action) are NOT
        # stripped — they exist only in moderator_log, carry no duplicate
        # elsewhere, and are exactly the self-reasoning continuity this
        # window exists to preserve. See
        # docs/changes/2026-06-30_moderator_dedup_A_reflection.md.
        for entry in data.get("moderator_log", []):
            entry.pop("utterance", None)

        if compress_before_turn is not None:
            for entry in data["moderator_log"]:
                if entry["turn"] < compress_before_turn and not entry.get("compressed"):
                    entry.pop("situation_assessment", None)
                    entry["compressed"] = True

        # Reflection mechanism visibility gate (2026-06-30, toggleable, OFF by
        # default). moderator_turn_share_overall/_recent are computed every
        # turn in apply_moderator_response() regardless of the toggle (cheap,
        # deterministic — same as participation_balance), and section_summaries
        # is only ever non-empty when the toggle is True. To guarantee OFF
        # reproduces today's prompt byte-for-byte, all three are stripped
        # from the serialized group_state here whenever the toggle is False
        # — not just left at their zero/empty defaults, which would still
        # change the JSON's byte content relative to before this mechanism
        # existed.
        if not self.session_meta.moderator_reflection_enabled:
            data["group_state"].pop("moderator_turn_share_overall", None)
            data["group_state"].pop("moderator_turn_share_recent", None)
            data["group_state"].pop("section_summaries", None)

        # Moderator context mode (2026-06-30 cost fix, Part 1 — DOMINANT FIX,
        # reverses the prior "moderator sees the full untrimmed transcript"
        # decision defended in docs/changes/2026-06-30_moderator_review.md).
        # That decision was correct on its own terms (not context-starved)
        # but its cost was unquantified at the time; the verification in
        # docs/findings/2026-06-30_full_session_token_growth_issue.md showed
        # the full-transcript re-send is ~61% of total run cost and ~80% of
        # the moderator's per-turn growth (911->33,434 tokens across one
        # killed full session). Default stays "full" — behavior-preserving
        # for every existing short-session config; only configs that
        # explicitly opt into "summarized" get the new, cheaper behavior.
        #
        # "summarized": the moderator receives the verbatim transcript of
        # ONLY the current (most recent, possibly still in progress) section
        # — found the same way the reflection cadence finds it, by scanning
        # moderator_log for the most recent SECTION_TRANSITION turn — PLUS
        # the accumulated section_summaries for every section completed
        # before that point (Part 0's shared primitive). This trades raw
        # verbatim recall of completed sections for the thematic synthesis
        # already produced for them, at a fraction of the token cost.
        # moderator_log's own 3-entry window (above) is unaffected either way.
        if self.session_meta.moderator_context_mode == "summarized":
            last_transition_turn = -1
            for entry in self.moderator_log:
                if entry.action == ModeratorAction.SECTION_TRANSITION:
                    last_transition_turn = entry.turn
            data["transcript"] = [
                e for e in data["transcript"] if e.get("turn", -1) > last_transition_turn
            ]
            data["completed_section_summaries"] = [
                s.model_dump(mode="json") for s in self.group_state.section_summaries
            ]

        return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Trigger Event — what caused this moderator turn
# ---------------------------------------------------------------------------

class TriggerEvent(BaseModel):
    type: TriggerEventType
    speaker_id: str | None = None
    speaker_name: str | None = None
    content: str = Field(..., description="Raw text of what was said, or description of what happened")
    turn_number: int
    follow_up_count_this_question: int = 0


# ---------------------------------------------------------------------------
# Moderator API Response — the model's output, validated on receipt
# ---------------------------------------------------------------------------

class QueuedNextActionResponse(BaseModel):
    action: ModeratorAction
    target: str
    rationale: str
    condition: str


class ContradictionItem(BaseModel):
    participant_id: str = Field(
        description="Exact participant ID as it appears in the "
                    "session state, e.g. 'P1'"
    )
    description: str = Field(
        description="Brief description of the contradiction using "
                    "the participant's own words where possible"
    )


class EmotionalSignalItem(BaseModel):
    participant_id: str = Field(
        description="Exact participant ID as it appears in the "
                    "session state, e.g. 'P1'"
    )
    signal: str = Field(
        description="Description of the emotional signal using "
                    "the participant's own words, not the "
                    "moderator's interpretation"
    )


class ModeratorDecisionResponse(BaseModel):
    """
    Validated against the model's JSON output.
    If validation fails, the orchestrator can retry or flag for human review.
    """
    intervention_mode: Literal["observe", "yield", "speak"]
    situation_assessment: str | None = None
    dominant_signal: DominantSignal | None = None
    action: ModeratorAction | None = None
    target: str | None = Field(None, description="participant ID or 'group'")
    probe_type: ProbeType | None = None
    follow_up_intensity: FollowUpIntensity | None = None
    consensus_risk_assessment: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Moderator's assessment of current consensus "
                    "risk. 0.0 = genuine diversity of views. "
                    "1.0 = artificial harmony. Required on every "
                    "turn, not only when risk is high."
    )
    emotional_signals: list[EmotionalSignalItem] = Field(
        default_factory=list,
        description="Emotional signals detected in participant "
                    "responses this turn. Only populate when a "
                    "genuine signal is present. Empty list if none."
    )
    new_contradictions: list[ContradictionItem] = Field(
        default_factory=list,
        description="Newly detected contradictions not yet in "
                    "unresolved_tensions. One entry per new "
                    "contradiction only — do not re-report "
                    "contradictions already flagged."
    )
    queued_next_action: QueuedNextActionResponse | None = None
    new_easy_agreements: list[str] = Field(
        default_factory=list,
        description="New topics where the group has converged without tension. Empty list if none."
    )

    @model_validator(mode="after")
    def validate_speak_mode(self) -> "ModeratorDecisionResponse":
        if self.intervention_mode == "speak":
            if not all([self.situation_assessment, self.dominant_signal, self.action, self.target]):
                missing = [f for f, v in [("situation_assessment", self.situation_assessment),
                                          ("dominant_signal", self.dominant_signal),
                                          ("action", self.action),
                                          ("target", self.target)] if not v]
                raise ValueError(f"Intervention mode 'speak' requires these fields: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def validate_yield_mode(self) -> "ModeratorDecisionResponse":
        if self.intervention_mode == "yield":
            has_update = (
                self.consensus_risk_assessment is not None or
                bool(self.emotional_signals) or
                bool(self.new_contradictions) or
                bool(self.new_easy_agreements)
            )
            if not has_update:
                raise ValueError("Intervention mode 'yield' requires at least one state tracking field to be updated. Use 'observe' if you have no updates.")
        return self

    # Removed: normalization in moderator_brain.py forces probe_type=None for non-direct_probe
    # actions before this validator would run. Keeping both created redundant and potentially
    # conflicting logic.
    # @model_validator(mode="after")
    # def validate_probe_type_consistency(self) -> "ModeratorDecisionResponse":
    #     """direct_probe requires a probe_type; other actions must not set one."""
    #     if self.action == ModeratorAction.DIRECT_PROBE and self.probe_type is None:
    #         raise ValueError("direct_probe action requires a probe_type")
    #     if self.action != ModeratorAction.DIRECT_PROBE and self.probe_type is not None:
    #         raise ValueError(f"probe_type should only be set for direct_probe, not {self.action}")
    #     return self

    @model_validator(mode="after")
    def validate_follow_up_intensity_consistency(self) -> "ModeratorDecisionResponse":
        """follow_up_intensity is only meaningful for probing actions — strip it silently for others."""
        probe_actions = {
            ModeratorAction.DIRECT_PROBE,
            ModeratorAction.REFLECT_CONTRADICTION,
            ModeratorAction.SYNTHESIZE_AND_CHALLENGE,
            ModeratorAction.REFOCUS_TO_GUIDE,
        }
        if self.action not in probe_actions and self.follow_up_intensity is not None:
            self.follow_up_intensity = None
        return self


class ModeratorAPIResponse(BaseModel):
    """The complete parsed response from a moderator API call."""
    moderator_decision: ModeratorDecisionResponse
    utterance: str = ""
    # Set True by call_moderator when a system fallback was substituted for a failed response
    validation_fallback: bool = False

    @field_validator("utterance")
    @classmethod
    def utterance_strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def validate_utterance_by_action(self) -> "ModeratorAPIResponse":
        """stay_silent requires an empty utterance; speak requires a non-empty one."""
        if self.moderator_decision.intervention_mode != "speak":
            self.utterance = ""
        elif self.moderator_decision.action == ModeratorAction.STAY_SILENT:
            self.utterance = ""
        elif not self.utterance:
            raise ValueError("utterance must not be empty for non-silent actions when intervention_mode is speak")
        return self


# ---------------------------------------------------------------------------
# State Mutation — the only place session state should be updated
# ---------------------------------------------------------------------------

def apply_moderator_response(
    state: SessionState,
    response: ModeratorAPIResponse,
    trigger_event: TriggerEvent,
    selection_mode: str | None = None,
) -> SessionState:
    """
    Apply a validated moderator API response to the session state.
    Returns an updated (re-validated) SessionState.
    This is the single mutation point — do not mutate state elsewhere.
    """
    decision = response.moderator_decision

    # 1. Increment total turns
    state.session_meta.total_turns += 1

    # 2. Update participant state if a participant just spoke
    if trigger_event.speaker_id and trigger_event.speaker_id in state.participants:
        p = state.participants[trigger_event.speaker_id]
        p.turn_count += 1

        # Update section-level turn count
        pid = trigger_event.speaker_id
        state.group_state.section_turn_counts[pid] = (
            state.group_state.section_turn_counts.get(pid, 0) + 1
        )
        state.group_state.section_word_counts[pid] = (
            state.group_state.section_word_counts.get(pid, 0) + count_words(trigger_event.content)
        )

    # 3. Update dominant_voices for this section
    section_total = sum(state.group_state.section_turn_counts.values())
    if section_total > 0:
        state.group_state.dominant_voices = [
            pid for pid, count in state.group_state.section_turn_counts.items()
            if count / section_total > 0.50
        ]

    # 4. Update silent_participants (only outside intro)
    if state.session_meta.section_phase != SectionPhase.INTRO:
        total_turns = sum(p.turn_count for p in state.participants.values())
        if total_turns > 0:
            state.group_state.silent_participants = [
                pid for pid, p in state.participants.items()
                if p.turn_count / total_turns < 0.15
            ]

    # 5. Handle section transition
    if decision.action == ModeratorAction.SECTION_TRANSITION:
        state.current_section.completed = True
        next_index = state.session_meta.current_section_index + 1
        if next_index < len(state.discussion_guide):
            closing_section_index = state.session_meta.current_section_index
            # Archive before resetting — otherwise a participant whose turn
            # triggers this same transition has their count incremented
            # earlier in this function and then wiped by the reset below
            # before any state snapshot ever observes it.
            state.group_state.completed_section_turn_counts[closing_section_index] = (
                dict(state.group_state.section_turn_counts)
            )
            state.group_state.completed_section_word_counts[closing_section_index] = (
                dict(state.group_state.section_word_counts)
            )
            state.session_meta.current_section_index = next_index
            state.session_meta.section_phase = state.current_section.section_phase
            state.session_meta.current_question_index = 0
            # Reset section-level turn counts
            state.group_state.section_turn_counts = {}
            state.group_state.section_word_counts = {}

    if decision.action == ModeratorAction.ASK_INITIAL_TO_GROUP:
        state.session_meta.current_question_index += 1

    if decision.new_easy_agreements:
        state.group_state.group_has_agreed_easily_on.extend(decision.new_easy_agreements)
        state.group_state.group_has_agreed_easily_on = list(dict.fromkeys(state.group_state.group_has_agreed_easily_on))

    if decision.action in (ModeratorAction.ASK_INITIAL_TO_GROUP, ModeratorAction.SECTION_TRANSITION, ModeratorAction.INTRODUCE_STIMULUS):
        for p in state.participants.values():
            p.follow_up_count_current_question = 0
            
    if decision.action == ModeratorAction.DIRECT_PROBE and decision.target in state.participants:
        state.participants[decision.target].follow_up_count_current_question += 1

    # 5a. Handle reflect_contradiction — advance the oldest unresolved tension for the target
    if (
        decision.action == ModeratorAction.REFLECT_CONTRADICTION
        and decision.target in state.participants
    ):
        oldest_tension = next(
            (
                t for t in state.group_state.unresolved_tensions
                if t.participant_id == decision.target and not t.resolved
            ),
            None,
        )
        if oldest_tension is not None:
            oldest_tension.surfaced = True
            oldest_tension.surface_count += 1
            if oldest_tension.surface_count >= 2:
                oldest_tension.resolved = True
                oldest_tension.resolved_at_turn = trigger_event.turn_number

    # 6. Update consecutive_participant_turns and last_speaker_id
    if decision.intervention_mode in ("observe", "yield"):
        state.group_state.consecutive_participant_turns += 1
        state.group_state.consecutive_silent_turns += 1
    else:
        state.group_state.consecutive_participant_turns = 0
        state.group_state.consecutive_silent_turns = 0
        state.group_state.last_speaker_id = "MODERATOR"

    # 7. Append to moderator log (always, including stay_silent — internal audit trail)
    log_entry = ModeratorLogEntry(
        turn=trigger_event.turn_number,
        trigger=decision.dominant_signal,
        situation_assessment=decision.situation_assessment,
        action=decision.action,
        target=decision.target,
        probe_type=decision.probe_type,
        follow_up_intensity=decision.follow_up_intensity,
        queued_next_action=(
            QueuedNextAction(**decision.queued_next_action.model_dump())
            if decision.queued_next_action else None
        ),
        intervention_mode=decision.intervention_mode,
        utterance=response.utterance,
        validation_fallback=response.validation_fallback,
        selection_mode=selection_mode,
    )
    state.moderator_log.append(log_entry)

    # 7b. Moderator turn-share (2026-06-30) — Piece 1 of the reflection
    # mechanism. Deterministic count, no LLM call, computed every turn
    # regardless of session_meta.moderator_reflection_enabled (cheap, same
    # pattern as participation_balance for participants) — visibility to the
    # moderator prompt is gated separately in to_prompt_json(), not here.
    mlog = state.moderator_log
    overall_speak = sum(1 for e in mlog if e.intervention_mode == "speak")
    state.group_state.moderator_turn_share_overall = round(overall_speak / len(mlog), 3) if mlog else 0.0
    recent_window = mlog[-_MODERATOR_OWN_SHARE_RECENT_WINDOW:]
    recent_speak = sum(1 for e in recent_window if e.intervention_mode == "speak")
    state.group_state.moderator_turn_share_recent = round(recent_speak / len(recent_window), 3) if recent_window else 0.0

    # 7a. Feedback loop — write moderator inferences directly from typed fields
    # consensus_risk
    if decision.consensus_risk_assessment is not None:
        state.group_state.consensus_risk = decision.consensus_risk_assessment

    # emotional signals
    for item in decision.emotional_signals:
        if item.participant_id in state.participants:
            state.participants[item.participant_id].emotional_signal = item.signal

    # new contradictions
    for item in decision.new_contradictions:
        if item.participant_id in state.participants:
            already_exists = any(
                t.participant_id == item.participant_id and not t.resolved
                for t in state.group_state.unresolved_tensions
            )
            if not already_exists:
                state.group_state.unresolved_tensions.append(
                    UnresolvedTension(
                        participant_id=item.participant_id,
                        flagged_at_turn=trigger_event.turn_number,
                        description=item.description,
                    )
                )

    # 8. Append utterance to transcript only when the moderator actually spoke
    if decision.intervention_mode == "speak" and response.utterance:
        state.transcript.append({
            "turn": trigger_event.turn_number,
            "speaker_id": "MODERATOR",
            "speaker_name": "Moderator",
            "content": response.utterance,
            "timestamp": datetime.now(UTC).isoformat(),
            "selection_mode": "moderator_intervention",
        })
        state.group_state.section_word_counts["MODERATOR"] = (
            state.group_state.section_word_counts.get("MODERATOR", 0) + count_words(response.utterance)
        )

    # Re-validate the whole state (triggers participation_balance sync)
    return SessionState.model_validate(state.model_dump())


def record_participant_utterance(
    state: SessionState,
    trigger_event: TriggerEvent,
    selection_mode: str | None = None,
) -> SessionState:
    """
    Record a participant utterance in the transcript.
    Called by the orchestrator BEFORE calling the moderator API.
    """
    if trigger_event.speaker_id:
        state.group_state.last_speaker_id = trigger_event.speaker_id
        state.transcript.append({
            "turn": trigger_event.turn_number,
            "speaker_id": trigger_event.speaker_id,
            "speaker_name": trigger_event.speaker_name,
            "content": trigger_event.content,
            "timestamp": datetime.now(UTC).isoformat(),
            "selection_mode": selection_mode,
        })
    return state
