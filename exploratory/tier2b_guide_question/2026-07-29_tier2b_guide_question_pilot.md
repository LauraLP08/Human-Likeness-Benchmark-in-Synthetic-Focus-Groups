# Tier 2b — Emergent Thematic Fidelity by Guide Question (FG1 pilot)

> ## ⚠ Superseded — see final verdict
>
> **This document's own next-step recommendation was resolved by later diagnostics in
> this same chain.** Part D below called for a discrimination control before scaling;
> that control was run, and it — together with the human-ceiling and cross-section
> controls that followed — settled the question against this layer.
>
> **Final decision:** Tier 2b's recall/precision is **retired as fidelity evidence**
> (the matcher tracks the guide question, not group identity — confirmed by the
> cross-section control). The per-section theme lists below **remain valid as
> descriptive output**: they are stable on re-extraction and quote-verified.
>
> The 21.3% mean recall reported here must **not** be cited as evidence about
> synthetic fidelity.
>
> Full chain and reasoning: `docs/findings/2026-07-29_tier2b_cross_section_control.md`.
>
> _Nothing below has been altered — this document is retained as the record of the
> diagnostic process._

**Date:** 2026-07-29  
**Evaluator:** `gemini-2.5-flash` (temperature=0.0)  
**Human:** `data\datasets_transcripts\standardized\macho_meals\fg1\transcript.json`  
**Synthetic:** `output\session_logs\macho_meals_fg1_run01\transcript.json` (designated principal FG1 run)  
**Data floor:** MIN_PARTICIPANT_TURNS=3, MIN_WORDS=150

> **Exploratory.** Per-section extraction is a new method without the validation
> gates the whole-transcript Tier 2 has (5-run repeatability, discrimination).
> The stability check in Part C is a noise floor, not a Gate-1 substitute.
> All figures are n=1 group, n=1 synthetic run.

---

## Part A — Segmentation

| Side | Boundary signal | Sections found | Entries unassigned |
|------|----------------|---------------|--------------------|
| Human | moderator 'Question N.' header | 5 | 0 |
| Synthetic | moderator_log.section_transition | 7 | 0 |

Synthetic boundaries cross-checked against `state_turn_*.json` (`current_section_index`): **66 entries agree**, 6 differ only on a boundary turn (expected — the per-turn state index is off by one there), **0 genuine conflicts**.

### Per-section data volume

| Idx | Section | Human p-turns | Human words | Synth p-turns | Synth words | Status |
|----:|---------|-------------:|-----------:|-------------:|-----------:|--------|
| 0 | Introduction and instructions | — | — | 6 | 619 | `skipped_no_counterpart` |
| 1 | Opening discussion: male friendship and place | 12 | 414 | 6 | 1053 | compared |
| 2 | Everyday food decision-making | 7 | 333 | 5 | 1012 | compared |
| 3 | Gender and food choice | 9 | 481 | 11 | 2966 | compared |
| 4 | Imagining a plant-based shift | 13 | 752 | 8 | 2412 | compared |
| 5 | Making plant-based foods more appealing | 17 | 936 | 7 | 2056 | compared |
| 6 | Closing remarks | — | — | 4 | 1315 | `skipped_no_counterpart` |

**Skipped sections (reported, not silently dropped):**

- Section 0 — Introduction and instructions: `skipped_no_counterpart` — absent from the human transcript
- Section 6 — Closing remarks: `skipped_no_counterpart` — absent from the human transcript

---

## Part B — Emergent themes by guide question

Recall = human themes with a synthetic counterpart / all human themes.  
Precision = synthetic themes with a human counterpart / all synthetic themes.  
Themes are matched **only within the same section** — never across sections.

| Idx | Section | Human themes | Synth themes | Matched | Emergent | Missed | Recall | Precision |
|----:|---------|------------:|------------:|--------:|---------:|-------:|-------:|----------:|
| 1 | Opening discussion: male friendship and place | 3 | 3 | 0 | 3 | 3 | 0.0% | 0.0% |
| 2 | Everyday food decision-making | 3 | 4 | 0 | 4 | 3 | 0.0% | 0.0% |
| 3 | Gender and food choice | 3 | 5 | 2 | 3 | 1 | 66.7% | 40.0% |
| 4 | Imagining a plant-based shift | 4 | 4 | 0 | 4 | 4 | 0.0% | 0.0% |
| 5 | Making plant-based foods more appealing | 5 | 5 | 2 | 3 | 3 | 40.0% | 40.0% |

Mean across compared sections: recall **21.3%**, precision **16.0%**.

### Emergent themes (synthetic-only, per section)

> n=1 caveat: 'emergent' means absent from the matched human group only — 
> not automatically false. `participant_count` is evidence-constrained 
> (distinct participants with a verified quote); 1 flags a possible artifact.

**Section 1 — Opening discussion: male friendship and place**

- Pubs as default social venues (participants=0) ⚑ single-voice
- Importance of decent pub food (participants=3)
- Pubs' varying commitment to food quality (participants=2)

**Section 2 — Everyday food decision-making**

- Convenience and Ease of Preparation (participants=2)
- Quality and Taste Perception (participants=2)
- Price Markup and Value Chain (participants=2)
- Mindfulness in Food Choices (participants=2)

**Section 3 — Gender and food choice**

- Lack of Deliberation in Food Choices (participants=2)
- Active Choice to Avoid Thinking About Food Origins (participants=2)
- Influence of Geography and Local Norms (participants=3)

**Section 4 — Imagining a plant-based shift**

- Social Discomfort of Changing Diet (participants=4)
- Comfort of the Default and Lack of Motivation (participants=4)
- Distinction Between Passive Default and Active Choice (participants=3)
- Personal Connection to Food and Community (participants=2)

**Section 5 — Making plant-based foods more appealing**

- Preference for meat is deeply ingrained (participants=3)
- Contextual shaping of food preferences (participants=2)
- Difficulty of changing established preferences (participants=3)

### Missed themes (human-only, per section)

**Section 1 — Opening discussion: male friendship and place**

- Affordable Food and Drink (participants=2)
- Shared Hobbies and Interests (participants=2)
- Flexibility in Food Choices (participants=3)

**Section 2 — Everyday food decision-making**

- Influence of group cravings (participants=2)
- Tendency for routine orders (participants=2)
- Variety of available options (participants=2)

**Section 3 — Gender and food choice**

- Food choices based on cravings (participants=2)

**Section 4 — Imagining a plant-based shift**

- Significant dietary and lifestyle changes (participants=4)
- Impact on athletic and fitness routines (participants=3)
- Challenges with taste and food substitutes (participants=2)
- Need for new knowledge and recipes (participants=4)

**Section 5 — Making plant-based foods more appealing**

- Ingredient Transparency and Education (participants=3)
- Affordability and Price Competitiveness (participants=2)
- Recipe Ideas and Usage Guidance (participants=1)

---

## Part C — Minimum stability check

3 independent extractions of the same section text, aligned pairwise by the same semantic matcher. Run on a cost-capped subset (smallest / median / largest compared section by human word count).

| Idx | Section | Side | Themes per run | Mean pairwise recall | Verdict |
|----:|---------|------|---------------|---------------------:|---------|
| 2 | Everyday food decision-making | human | [3, 4, 3] | 91.7% | stable |
| 2 | Everyday food decision-making | synthetic | [4, 4, 4] | 100.0% | stable |
| 3 | Gender and food choice | human | [3, 4, 4] | 100.0% | stable |
| 3 | Gender and food choice | synthetic | [5, 5, 5] | 100.0% | stable |
| 5 | Making plant-based foods more appealing | human | [5, 5, 5] | 86.7% | stable |
| 5 | Making plant-based foods more appealing | synthetic | [5, 5, 6] | 100.0% | stable |

Overall mean pairwise recall across the checked sections: **96.4%**.

Compare against the whole-transcript Tier 2 repeatability reported in `docs/findings/2026-07-20_tier1reach_tier2.md`: if per-section agreement is materially lower, the per-section numbers in Part B carry more run-to-run noise than the whole-transcript layer and should be read as directional only.

---

## Part D — How far these numbers can be read

**Per-section recall is not comparable to whole-transcript Tier 2 recall.** Over a whole transcript the matcher may pair a synthetic theme with a human theme drawn from anywhere in the session; Tier 2b forbids that by construction. It is a strictly harder test, so a lower number here is expected and is not by itself evidence of worse fidelity.

**No discrimination control has been run for Tier 2b.** The whole-transcript layer establishes its floor by scoring a deliberately mismatched pair (real FG1 vs synthetic FG5) and showing the matched pair scores higher. Without the equivalent per-section control, a low per-section recall cannot be separated from the method's own floor — an unrelated group might score the same. Treat Part B as descriptive until that control exists.

**Section-level theme sets are small** (3–5 per side), so one match moves recall by 20–33 points. Differences between sections of a few points carry no weight.

**`participant_count` is evidence-constrained**: distinct non-moderator speakers with a quote verified as a substring of the section text. A count of 0 means no participant quote survived verification — the theme rests on moderator turns or unverifiable quotes and should be discounted.

**Data volume is not matched across sides**, which is itself a finding rather than a nuisance: see the per-section word counts in Part A.

---

_Auto-generated by `scripts/validate_tier2b_guide_question.py` (segmentation: `scripts/tier2b_segmentation.py`)._
