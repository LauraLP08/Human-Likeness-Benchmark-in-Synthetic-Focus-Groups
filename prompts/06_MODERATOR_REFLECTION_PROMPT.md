# Moderator Reflection Prompt
# File: prompts/06_MODERATOR_REFLECTION_PROMPT.md
#
# Usage: Sent as a SEPARATE, lightweight API call (not the main per-turn
#        moderator decision call) when session_meta.moderator_reflection_enabled
#        is True, ONLY at section/question boundaries (when the moderator's
#        action this turn was section_transition) — a handful of calls per
#        session, not every turn. Built and parsed in
#        core/moderator_brain.py (run_moderator_reflection()).
#
# One-channel rule: this call deliberately does NOT ask about coverage or
# participation balance — both already reach the moderator through other
# channels (DiscussionGuideSection.completed; GroupState's participation
# fields). Restating them here, even reworded, would be duplication.
# Moderator turn-share is ALSO not requested here — it is a separate,
# deterministic GroupState field, not part of this LLM call.
#
# This call does NOT receive moderator_log (the moderator's own past
# justifications) — only transcript content — so each summary is
# regenerated fresh rather than recycled from prior reasoning.
#
# 2026-06-30 cost fix (Part 3): TRANSCRIPT is now the SINCE-LAST-REFLECTION
# slice (the section that just ended), not the full session — paired with
# PRIOR_SUMMARIES, the accumulated summaries of every earlier completed
# section, so this call has continuity without re-reading everything. On
# the first-ever reflection, PRIOR_SUMMARIES is empty and TRANSCRIPT is
# everything since session start — identical to the old full-transcript
# behavior at that one point, correctly, since there is nothing yet to
# compress.

---

You are pausing, at a natural break point in the discussion, to produce two short, fresh summaries of the section that just ended — not to decide your next move.

## SUMMARIES OF EARLIER SECTIONS (for continuity — already captured, do not re-summarize these)

```
{PRIOR_SUMMARIES}
```

## NEW CONTENT — THE SECTION THAT JUST ENDED

```json
{TRANSCRIPT}
```

## YOUR TASK

Produce a summary of the NEW CONTENT above — the section that just ended — informed by but not repeating the earlier-section summaries. Produce exactly this JSON structure and nothing else:

```json
{
  "discussion_summary": "ONE paragraph, 80 WORDS OR FEWER. A THEMATIC synthesis of which ideas/themes participants' answers revolved around IN THIS SECTION. Abstract to themes — do NOT recap who said what in sequence, and do NOT restate themes already covered in the earlier-section summaries above unless this section meaningfully extended or complicated them. Good example: 'This section centered on convenience and peer judgment, with a recurring tension between stated values and described shopping habits.' Forbidden example (this is a recap, not a synthesis, and duplicates the transcript): 'David said he prioritizes price, then Sam said he agrees, then Isaiah pushed back.'",
  "strategy_summary": "ONE paragraph, 80 WORDS OR FEWER. A synthesis of YOUR OWN reasoning and approach DURING THIS SECTION: what you were trying to do as moderator (e.g. drawing out quieter voices, deepening a particular thread, holding back to let a tension develop), and an honest read on whether it worked."
}
```

Both fields must stay at or under 80 words — be concise and synthesized, not exhaustive. Produce valid JSON only. No markdown, no prose outside the JSON block.
