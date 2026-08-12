# Session Opening Prompt — SANDBOX VARIANT
# File: prompts/sandbox/03_SESSION_OPENING_PROMPT_SANDBOX.md
#
# Usage: Used ONLY when session_meta.moderator_opening_prompt_override is set
#        to this filename (INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md).
#        Never used by any production or run_batch.py/run_live_pilot.py
#        session unless explicitly configured to.
#
# Identical to prompts/03_SESSION_OPENING_PROMPT.md except:
#   1. The words-per-minute rate used to compute the time budget is raised
#      from production's literature-cited (Zhang et al., 2024) rate to the
#      midpoint of the researcher's own timed measurement (110-115 wpm) —
#      see the "Word budget" line below for the exact figure used.
#   2. The "Total duration" worked example is re-anchored to the sandbox
#      guide's own stated duration instead of production's fixed one — the
#      duration and word-budget lines stay coupled to a single real figure,
#      exactly as production's file hardcodes its own duration
#      self-consistently, rather than one line going generic while the
#      other kept an implicit total derived from the old anchor.
#
# NOTE: this comment block deliberately avoids restating either the old or
# new duration/rate figures verbatim (beyond what's below) — this file is
# NOT header-stripped before being sent to the model (unlike
# 01_MODERATOR_SYSTEM_PROMPT.md via load_system_prompt), so any number
# written here becomes a second candidate anchor in the same prompt the
# model reads. Keep this section's actual figures as the single source of
# truth.
#
# The opening call has two jobs:
#   1. Have the moderator generate the welcome and ground-rules utterance
#   2. Have it produce an initial session plan — a lightweight internal staging
#      plan written into the moderator_log before any participant speaks.
#
# Inject: the full research config JSON below replaces the SESSION_CONFIG placeholder in the code block (see schema below)

---

## NEW SESSION INITIALISATION

A new focus group session is about to begin. You have not yet spoken. No participant has contributed.

Read the session configuration below. Then produce two things:

1. An **initial session plan** that you will carry as your internal orientation throughout the session
2. Your **opening utterance** — the welcome and ground-rules statement you will deliver to the group

---

## SESSION CONFIGURATION

```json
{SESSION_CONFIG}
```

The session config schema is:

```json
{
  "session_id": "string",
  "research_objective": "string — the research question this focus group is designed to answer",
  "topic_domain": "string — what the discussion is broadly about",
  "participant_collective_identity": "string — the shared category participants represent (e.g. 'urban commuters', 'first-time parents', 'NHS patients'). Used in thematisation.",
  "moderator_knowledge_brief": "string — what the moderator is permitted to know about the topic. Does NOT include researcher hypotheses or expected findings.",
  "participants": [
    {
      "id": "P1",
      "name": "string",
      "profile_summary": "string — brief relevant profile for this participant"
    }
  ],
  "discussion_guide": [
    {
      "section_index": 0,
      "section_label": "intro | context | main_topic | stimulus | closing",
      "section_purpose": "string",
      "scripted_question": "string",
      "stimulus": null
    }
  ],
  "researcher_notes": "string — any session-specific instructions from the researcher that do not constitute hypotheses (e.g. 'pay particular attention to cost references', 'this group contains participants with sensitive personal histories on this topic')"
}
```

**Important — internal use only.** `research_objective` and `moderator_knowledge_brief` describe
what the researcher is trying to learn and what you are permitted to know about the topic. They
orient your own judgment throughout the session — how you probe, what you listen for, what
matters — but they are not for the group. Never state, paraphrase, summarize, or hint at either of
these to participants, in the opening or at any later point in the session. Participants should
never be able to infer the specific research question from anything you say.

---

## YOUR TASK FOR THIS OPENING CALL

Before producing the JSON, compute a time budget:
- Total duration: read from the scripted question of the first guide section (it states "about 20 minutes") → **20 minutes**.
- Word budget: ~112 words ≈ 1 minute → **~2240 words total** across all participant and moderator turns.
- Distribute across sections: weight `main_topic` sections most heavily (they carry the research); `context` sections moderately; `intro` and `closing` lightly.
- Express each section's share as a `word_budget` (words) and a `turn_budget` (estimated participant turns).

Produce the following JSON and nothing else:

```json
{
  "initial_session_plan": {
    "thematisation_approach": "In 2-3 sentences: how will you frame the collective identity of these participants in your opening? What specific category or shared context will you ask them to speak from?",

    "priority_research_areas": [
      "List the 2-4 areas within the research objective that you judge will require the most careful moderation — not just question delivery. These are the areas where probe depth, consensus risk, or participant sensitivity are most likely to matter."
    ],

    "participant_notes": [
      {
        "participant_id": "P1",
        "anticipated_role": "string — based on profile, any anticipation of engagement style, potential dominance, potential reticence, or relevant personal context",
        "initial_attention_flag": "string | null"
      }
    ],

    "known_risk_conditions": [
      "List any conditions you anticipate that will require active moderator management. Examples: 'Topic may produce socially desirable answers — use behavioural grounding early', 'Group may converge quickly on price as a barrier — plan sharpening move', 'Researcher notes indicate personal sensitivity — avoid emotional depth probes in early sections'."
    ],

    "directivity_plan": "How will directivity shift across the session? Where will you hold back and where will you push harder?",

    "time_budget": {
      "total_minutes": 20,
      "total_word_budget": 2240,
      "budget_rationale": "Brief note on how you weighted the sections (main_topic sections heavier; intro/closing lighter).",
      "per_section": [
        {
          "section_index": 0,
          "section_label": "string — the label from the discussion guide",
          "section_phase": "intro | context | main_topic | stimulus | closing",
          "word_budget": 750,
          "turn_budget": 3
        }
      ]
    }
  },

  "moderator_decision": {
    "situation_assessment": "Session is initialising. No data yet. This decision covers the opening utterance only. Opening utterance must establish the collective framing, the ground rules, and the psychological safety conditions before any substantive question is posed.",
    "intervention_mode": "speak",
    "dominant_signal": "guide_question_pending",
    "action": "ask_initial_to_group",
    "target": "group",
    "probe_type": null,
    "follow_up_intensity": null,
    "queued_next_action": null
  },

  "utterance": "Your full opening statement. This must accomplish all of the following in natural, warm, conversational language — not a formal list of rules:\n\n1. Welcome the group and introduce yourself briefly.\n2. Set expectations for natural conversation: invite actual, concrete experiences (what participants have used, avoided, liked, disliked, or felt unsure about).\n3. Establish ground rules lightly: remind participants to listen to each other and respond naturally if something connects with their experience.\n4. State clearly that there are no right or wrong answers, but do not over-emphasize the need for disagreement, debate, or profound insight.\n5. Introduce the first question naturally as a continuation of the welcome — not as a formal pivot. Use the first discussion-guide section's own `scripted_question` as written; it already carries whatever brief topic framing the original study included. Do not add your own explanation of what the discussion or the research is about before, after, or around it.\n\nThe entire utterance should feel like one continuous, warm, human opening — not a sequence of procedural announcements or a search for deep philosophical truth."
}
```
