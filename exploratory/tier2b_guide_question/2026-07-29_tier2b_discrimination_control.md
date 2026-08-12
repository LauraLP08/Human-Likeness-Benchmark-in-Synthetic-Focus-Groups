# Tier 2b — Discrimination Control (real FG1 vs mismatched synth FG5)

> ## ⚠ Superseded — see final verdict
>
> **This document's own next-step recommendation was resolved by later diagnostics in
> this same chain.** Part D below called for a human-vs-human ceiling to interpret the
> wrong-signed margin found here; that ceiling was run, and the cross-section control
> that followed identified the mechanism behind it.
>
> **Final decision:** Tier 2b's recall/precision is **retired as fidelity evidence**
> (the matcher tracks the guide question, not group identity — confirmed by the
> cross-section control). The per-section theme lists **remain valid as descriptive
> output**: they are stable on re-extraction and quote-verified.
>
> The wrong-signed margin recorded here (−23.3% on the primary control arm) is now
> **explained rather than anomalous**: within a guide section the topic is held
> constant by construction, which removes the only variable the matcher is sensitive
> to. Note this does **not** implicate `match_tier2_themes` in general — the
> cross-section control showed it discriminates topic correctly, so the
> whole-transcript Tier 2 is unaffected.
>
> Full chain and reasoning: `docs/findings/2026-07-29_tier2b_cross_section_control.md`.
>
> _Nothing below has been altered — this document is retained as the record of the
> diagnostic process._

**Date:** 2026-07-29  
**Evaluator:** `gemini-2.5-flash` (temperature=0.0) — identical to the matched pilot  
**Human arm:** real FG1 themes reused verbatim from `analysis/coding_frame/tier2b_guide_question_human_fg1.json` (not re-extracted)  
**Matched arm (from pilot):** `macho_meals_fg1_run01`  
**Control arms:** `macho_meals_fg5_run01`, `macho_meals_fg5_run03` (primary: `macho_meals_fg5_run01`)  
**Data floor:** MIN_PARTICIPANT_TURNS=3, MIN_WORDS=150

> Purpose: establish Tier 2b's own floor. The matched pilot scored 21.3% mean
> per-section recall; on its own that could be genuine partial fidelity or it
> could be what the method returns for *any* two focus groups on the same guide.
> Scoring deliberately unrelated groups separates the two.

> **Control arms are not pooled.** Each FG5 run is an independent control with
> its own margin. No averaged mismatched figure is reported — pooling replicates
> would hide the run-to-run spread a second arm exists to expose.

---

## Part A — Segmentation of the control arms

### `macho_meals_fg5_run01` (primary)

Cross-checked against `state_turn_*.json`: **46 entries agree**, 6 differ only on a boundary turn (expected), **0 genuine conflicts**.

| Idx | Section | p-turns | words | speakers | Floor |
|----:|---------|--------:|------:|---------:|-------|
| 0 | Introduction and instructions | 6 | 1007 | 4 | ok |
| 1 | Opening discussion: male friendship and place | 4 | 1117 | 2 | ok |
| 2 | Everyday food decision-making | 4 | 994 | 2 | ok |
| 3 | Gender and food choice | 7 | 1941 | 4 | ok |
| 4 | Imagining a plant-based shift | 8 | 2530 | 4 | ok |
| 5 | Making plant-based foods more appealing | 5 | 1436 | 4 | ok |
| 6 | Closing remarks | 1 | 381 | 1 | **BELOW** |

Skipped (reported, not silently dropped):

- Section 0 — Introduction and instructions: `skipped_no_counterpart` — absent from the human transcript
- Section 6 — Closing remarks: `skipped_no_counterpart` — absent from the human transcript

### `macho_meals_fg5_run03`

Cross-checked against `state_turn_*.json`: **63 entries agree**, 6 differ only on a boundary turn (expected), **0 genuine conflicts**.

| Idx | Section | p-turns | words | speakers | Floor |
|----:|---------|--------:|------:|---------:|-------|
| 0 | Introduction and instructions | 6 | 508 | 4 | ok |
| 1 | Opening discussion: male friendship and place | 6 | 993 | 4 | ok |
| 2 | Everyday food decision-making | 6 | 1259 | 4 | ok |
| 3 | Gender and food choice | 12 | 3156 | 4 | ok |
| 4 | Imagining a plant-based shift | 6 | 1739 | 4 | ok |
| 5 | Making plant-based foods more appealing | 6 | 1734 | 4 | ok |
| 6 | Closing remarks | 1 | 269 | 1 | **BELOW** |

Skipped (reported, not silently dropped):

- Section 0 — Introduction and instructions: `skipped_no_counterpart` — absent from the human transcript
- Section 6 — Closing remarks: `skipped_no_counterpart` — absent from the human transcript

Human FG1 per-section volume (unchanged from the pilot): s1 12t/414w, s2 7t/333w, s3 9t/481w, s4 13t/752w, s5 17t/936w.

---

## Part B — Matched vs mismatched, section by section

Matched arm = real FG1 vs synth FG1 (`macho_meals_fg1_run01`), from the pilot.  
Control arms = the same real FG1 themes vs synth FG5.  
Same evaluator, same human baseline, same matcher — only the synthetic group differs.

| Idx | Section | Matched recall | FG5 run01 recall | margin | FG5 run03 recall | margin |
|----:|---------|---------------:|-----:|-------:|-----:|-------:|
| 1 | Opening discussion: male friendship and place | 0.0% | 33.3% | -33.3% | 0.0% | +0.0% |
| 2 | Everyday food decision-making | 0.0% | 66.7% | -66.7% | 33.3% | -33.3% |
| 3 | Gender and food choice | 66.7% | 33.3% | +33.3% | 33.3% | +33.3% |
| 4 | Imagining a plant-based shift | 0.0% | 50.0% | -50.0% | 25.0% | -25.0% |
| 5 | Making plant-based foods more appealing | 40.0% | 40.0% | +0.0% | 0.0% | +40.0% |

| **Mean** | | **21.3%** | **44.7%** | **-23.3%** | **18.3%** | **+3.0%** |

Theme pairs matched across all five sections:

- matched arm (`macho_meals_fg1_run01`): **4**
- control arm (`macho_meals_fg5_run01`): **8**
- control arm (`macho_meals_fg5_run03`): **3**

Precision, for completeness: matched 16.0%; `macho_meals_fg5_run01` 33.7%; `macho_meals_fg5_run03` 14.0%.

> No pass/fail threshold is applied. At n=5 sections with 3–5 themes per side,
> a single theme pairing moves a section's recall by 20–33 points, so the margin
> is interpreted, not tested against a fixed cut.

---

## Part C — Themes extracted from the control arms

### `macho_meals_fg5_run01`

**Section 1 — Opening discussion: male friendship and place** (1 matched of 3 human / 5 synthetic)

- matched: _Flexibility in Food Choices_ ↔ _Ease and lack of agenda in pub meetups_
- FG5-only: Pubs as primary social spaces (participants=2)
- FG5-only: Unspoken social pressures in male spaces (participants=2)
- FG5-only: Impact of changing dietary habits (participants=2)
- FG5-only: Pubs reinforcing traditional masculinity (participants=1) ⚑ single-voice

**Section 2 — Everyday food decision-making** (2 matched of 3 human / 4 synthetic)

- matched: _Tendency for routine orders_ ↔ _Influence of habit and practicality on food choices_
- matched: _Influence of group cravings_ ↔ _Perceived social pressure and 'normal' eating_
- FG5-only: Distinction between marketing and social pressure (participants=2)
- FG5-only: Impact of local context on social dynamics (participants=2)

**Section 3 — Gender and food choice** (1 matched of 3 human / 4 synthetic)

- matched: _Gender's influence on food choices_ ↔ _Outdated Link Between Meat and Masculinity_
- FG5-only: Unnoticed Social Pressure to Eat Meat (participants=3)
- FG5-only: Complicity in Perpetuating Norms (participants=3)
- FG5-only: The Burden of Conscious Food Choices (participants=3)

**Section 4 — Imagining a plant-based shift** (2 matched of 4 human / 6 synthetic)

- matched: _Need for new knowledge and recipes_ ↔ _Practicality and Knowledge Gaps_
- matched: _Significant dietary and lifestyle changes_ ↔ _Comfort vs. Willingness to Change_
- FG5-only: Social Awkwardness and Inconvenience (participants=2)
- FG5-only: Lack of Supporting Infrastructure (participants=4)
- FG5-only: Age and Life Stage as a Factor (participants=3)
- FG5-only: Individual Action Driving Systemic Change (participants=2)

**Section 5 — Making plant-based foods more appealing** (2 matched of 5 human / 5 synthetic)

- matched: _Recipe Ideas and Usage Guidance_ ↔ _Need for demonstration and cultural shift_
- matched: _Taste and Texture Improvement_ ↔ _Lack of exposure to appealing plant-based food_
- FG5-only: Comfort and familiarity with traditional diet (participants=3)
- FG5-only: Personal choice to not explore plant-based options (participants=3)
- FG5-only: Motivation beyond just taste or health (participants=1) ⚑ single-voice

### `macho_meals_fg5_run03`

**Section 1 — Opening discussion: male friendship and place** (0 matched of 3 human / 4 synthetic)

- FG5-only: Value of Familiarity and Comfort (participants=4)
- FG5-only: Being Known and Accepted Authentically (participants=4)
- FG5-only: Shifting Priorities with Age (participants=2)
- FG5-only: Importance of Genuine Interaction (participants=2)

**Section 2 — Everyday food decision-making** (1 matched of 3 human / 4 synthetic)

- matched: _Variety of available options_ ↔ _Simplicity of limited choice_
- FG5-only: Prioritizing local and trusted suppliers (participants=2)
- FG5-only: Anxiety over loss of local shops (participants=2)
- FG5-only: Convenience versus quality dilemma (participants=1) ⚑ single-voice

**Section 3 — Gender and food choice** (1 matched of 3 human / 5 synthetic)

- matched: _Gender's influence on food choices_ ↔ _Outdated Masculinity and Meat_
- FG5-only: Reactions to Vegetarianism/Veganism (participants=2)
- FG5-only: Visibility and Social Scrutiny in Small Communities (participants=2)
- FG5-only: Distinguishing Intentionality from Difference (participants=2)
- FG5-only: Personal Responsibility for Social Pressure (participants=2)

**Section 4 — Imagining a plant-based shift** (1 matched of 4 human / 4 synthetic)

- matched: _Significant dietary and lifestyle changes_ ↔ _Disruption of established routines and habits_
- FG5-only: Visibility and social discomfort of dietary choices (participants=3)
- FG5-only: The burden of 'owning' a deliberate choice (participants=1) ⚑ single-voice
- FG5-only: Hypocrisy in judging others' visibility (participants=2)

**Section 5 — Making plant-based foods more appealing** (0 matched of 5 human / 5 synthetic)

- FG5-only: Social pressure against visible change (participants=3)
- FG5-only: Plant-based food as a 'statement' (participants=2)
- FG5-only: Difficulty in changing ingrained social behaviour (participants=2)
- FG5-only: Collective responsibility for social norms (participants=2)
- FG5-only: Awareness as a first step to change (participants=3)

---

## Part D — Reading the margin

The comparison is tightly controlled: the human theme set is byte-identical
across all arms (reused, not re-extracted), the evaluator config is the same,
and the matcher is unmodified. The only thing that varies is which synthetic
group is scored.

Limits that still apply:

- **All groups follow the same discussion guide**, so a mismatched pair is not
  an unrelated-topic control — it is a same-topic, different-people control.
  That is the right test for this question, but it makes a large margin
  inherently unlikely: both sides are answering the same question.
- **The matched arm is n=1 synthetic run**, so its 21.3% carries its own
  run-to-run uncertainty, which the pilot's stability check bounded (96.4% mean
  pairwise recall on re-extraction) but did not remove.
- **2 control arm(s)** — enough to see whether the margin survives a
  change of FG5 replicate, not enough to put a confidence interval on it.

---

_Auto-generated by `scripts/validate_tier2b_discrimination_control.py` (segmentation: `scripts/tier2b_segmentation.py`; matched-arm figures from `tier2b_guide_question_pilot_fg1_gemini25.json`)._
