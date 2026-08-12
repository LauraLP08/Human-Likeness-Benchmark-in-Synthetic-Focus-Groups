# Tier 2b — Cross-Section Control (does the matcher follow the question or the group?)

> ## Final document in the Tier 2b diagnostic chain
>
> This document carries the verdict. It is the fourth and last of four, each of which
> raised the question the next one answered:
>
> 1. **Pilot** — `2026-07-29_tier2b_guide_question_pilot.md`. Real FG1 vs synth FG1,
>    per guide question: **21.3%** mean recall, extraction stable at **96.4%** on
>    re-extraction. Uninterpretable without a floor → asked for a discrimination control.
> 2. **Discrimination control** — `2026-07-29_tier2b_discrimination_control.md`. Real
>    FG1 vs deliberately mismatched synth FG5: **44.7%** (run01, primary) and **18.3%**
>    (run03). The primary control scored *above* the matched pair — margin **−23.3%**,
>    the wrong sign → asked for a human-vs-human ceiling.
> 3. **Human ceiling** — `2026-07-29_tier2b_human_ceiling.md`. Real groups scored
>    against each other on the same questions: **57.0%** (FG1↔FG2), **43.7%**
>    (FG1↔FG3), **41.3%** (FG2↔FG3). Ambiguous — above the matched synthetic pair, but
>    overlapping the mismatched one → asked for this cross-section control.
> 4. **Cross-section control** — this document. Same transcript, *different* guide
>    questions: **0.0%**. Different groups, different questions: **8.0%**. Different
>    groups, *related* questions: **50.0%**.
>
> **Verdict:** the matcher tracks the guide question, not group identity. Tier 2b's
> recall/precision is **retired as fidelity evidence**; the per-section theme lists
> **remain valid as descriptive output**. `match_tier2_themes` is *not* implicated in
> general — it returned exactly 0.0% on 7 of 8 genuinely unrelated-topic comparisons,
> so the whole-transcript Tier 2 and its Gate 2 margin are unaffected.

**Date:** 2026-07-29  
**Evaluator:** `gemini-2.5-flash` (temperature=0.0) — identical to every prior Tier 2b run  
**Themes:** reused verbatim from `analysis/coding_frame/tier2b_human_ceiling_fg1_fg2_fg3.json` — **no new extraction**; only `match_tier2_themes` was called  
**Read-only:** no synthetic generation; nothing written to `data/`.

> **Recall here is a control figure, not fidelity.** The two sides answer
> different guide questions by construction, so neither "should" reproduce the
> other. The number means only: how readily does the matcher pair these two
> theme sets?

---

## Part A — The 2×2

| | same question | different question |
|---|---|---|
| **same group** | 96.4% _(pilot stability)_ | **0.0%** _(this run, 3 pairs)_ |
| **different group** | 41.3–57.0% _(human ceiling)_ | **8.0%** _(this run, 5 pairs)_ |

Intermediate rung — different group, **related** question (guide sections 4↔5, both about plant-based eating): **50.0%** (2 pairs).

---

## Part B — Every cross pair

| Cell | Pair | Section A | Section B | Topic | A themes | B themes | Matched | Recall | Precision |
|------|------|-----------|-----------|-------|---------:|---------:|--------:|-------:|----------:|
| same_group_diff_question | fg1 s2 × fg1 s4 | Everyday food decision-making | Imagining a plant-based shift | unrelated_topic | 3 | 4 | 0 | 0.0% | 0.0% |
| same_group_diff_question | fg2 s1 × fg2 s3 | Opening discussion: male friendship and place | Gender and food choice | unrelated_topic | 3 | 3 | 0 | 0.0% | 0.0% |
| same_group_diff_question | fg3 s3 × fg3 s5 | Gender and food choice | Making plant-based foods more appealing | unrelated_topic | 5 | 3 | 0 | 0.0% | 0.0% |
| diff_group_diff_question | fg1 s2 × fg2 s4 | Everyday food decision-making | Imagining a plant-based shift | unrelated_topic | 3 | 4 | 0 | 0.0% | 0.0% |
| diff_group_diff_question | fg1 s3 × fg3 s5 | Gender and food choice | Making plant-based foods more appealing | unrelated_topic | 3 | 3 | 0 | 0.0% | 0.0% |
| diff_group_diff_question | fg2 s1 × fg3 s4 | Opening discussion: male friendship and place | Imagining a plant-based shift | unrelated_topic | 3 | 5 | 0 | 0.0% | 0.0% |
| diff_group_diff_question | fg1 s1 × fg3 s3 | Opening discussion: male friendship and place | Gender and food choice | unrelated_topic | 3 | 5 | 0 | 0.0% | 0.0% |
| diff_group_diff_question | fg1 s5 × fg2 s2 | Making plant-based foods more appealing | Everyday food decision-making | unrelated_topic | 5 | 4 | 2 | 40.0% | 50.0% |
| diff_group_related_question | fg1 s4 × fg2 s5 | Imagining a plant-based shift | Making plant-based foods more appealing | related_topic | 4 | 5 | 1 | 25.0% | 20.0% |
| diff_group_related_question | fg2 s4 × fg3 s5 | Imagining a plant-based shift | Making plant-based foods more appealing | related_topic | 4 | 3 | 3 | 75.0% | 100.0% |

---

## Part C — All figures on one scale

| Comparison | Condition | Mean recall |
|------------|-----------|------------:|
| Same text, re-extracted (pilot stability) | same group, same question | 96.4% |
| real FG1 ↔ real FG2 (human ceiling) | diff group, same question | 57.0% |
| real FG1 ↔ real FG3 (human ceiling) | diff group, same question | 43.7% |
| real FG2 ↔ real FG3 (human ceiling) | diff group, same question | 41.3% |
| real FG1 ↔ synth FG1 run01 (matched) | synthetic, same question | 21.3% |
| real FG1 ↔ synth FG5 run01 (mismatched) | synthetic, same question | 44.7% |
| real FG1 ↔ synth FG5 run03 (mismatched) | synthetic, same question | 18.3% |
| **Cross-section control (same_group_diff_question)** | same group, DIFFERENT question | **0.0%** |
| **Cross-section control (diff_group_related_question)** | diff group, RELATED question | **50.0%** |
| **Cross-section control (diff_group_diff_question)** | diff group, DIFFERENT question | **8.0%** |

---

## Part D — Accepted matches across different questions

Any pairing here joins themes drawn from answers to *different* guide
questions, so every accepted match is worth inspecting on its own terms.

**fg1 s5 (Making plant-based foods more appealing) × fg2 s2 (Everyday food decision-making)** — unrelated_topic

- sim=0.564: _Health Benefits and Nutritional Value_ ↔ _Menu and Dietary Restrictions_
  - A: This theme captures participants' recognition of the potential health advantages of plant-based foods, such as lower calories and benefits for blood sugar regulation and weight management.
  - B: This theme reflects how participants' food choices are influenced by available menu options and personal dietary restrictions or preferences.
- sim=0.636: _Taste and Texture Improvement_ ↔ _Comfort and Enjoyment from Food_
  - A: This theme captures participants' desire for plant-based foods to have better flavor, more substantial texture, and overall improved palatability to be more appealing.
  - B: This theme highlights the importance participants place on food being enjoyable and providing comfort, often leading them to choose familiar or easy-to-make dishes.

**fg1 s4 (Imagining a plant-based shift) × fg2 s5 (Making plant-based foods more appealing)** — related_topic

- sim=0.769: _Challenges with taste and food substitutes_ ↔ _Taste and texture as key factors_
  - A: This theme captures participants' skepticism and dissatisfaction regarding the taste and quality of plant-based meat substitutes and the perceived blandness of plant-based meals.
  - B: Participants emphasize that the taste and texture of plant-based alternatives are crucial for their appeal and willingness to switch from meat.

**fg2 s4 (Imagining a plant-based shift) × fg3 s5 (Making plant-based foods more appealing)** — related_topic

- sim=0.786: _High cost of plant-based alternatives_ ↔ _Cost and Affordability_
  - A: Participants identify the higher price point of plant-based products as a significant barrier to adoption, especially given current economic conditions.
  - B: This theme reflects participants' consideration of price as a significant factor in the appeal and adoption of plant-based foods, especially in the current economic climate.
- sim=0.688: _Unsatisfying taste and texture_ ↔ _Mimicking Meat Taste and Texture_
  - A: Participants indicate that plant-based alternatives often fail to replicate the taste and texture of traditional meat and dairy products, leading to dissatisfaction.
  - B: This theme captures participants' desire for plant-based foods to closely replicate the taste, texture, and overall experience of eating meat, or to be entirely distinct.
- sim=0.503: _Lack of clarity on ingredients and processing_ ↔ _Nutritional Value and Health Concerns_
  - A: Participants express concern and confusion regarding the ingredients and manufacturing processes of plant-based alternatives, leading to distrust.
  - B: This theme highlights participants' concerns about whether plant-based diets can provide all necessary nutrients, particularly protein, without supplements.

---

_Auto-generated by `scripts/validate_tier2b_cross_section_control.py`. Theme sets from `tier2b_human_ceiling_fg1_fg2_fg3.json`; no extraction call was made._
