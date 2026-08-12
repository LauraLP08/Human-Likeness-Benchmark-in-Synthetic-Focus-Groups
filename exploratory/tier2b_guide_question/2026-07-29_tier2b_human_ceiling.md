# Tier 2b — Human-vs-Human Ceiling (does the method discriminate group identity at all?)

> ## ⚠ Superseded — see final verdict
>
> **This document's own next-step recommendation was resolved by later diagnostics in
> this same chain.** It closed ambiguous between two readings and called for one
> decisive test — a cross-section control. That control was run, and it resolved the
> ambiguity.
>
> **Final decision:** Tier 2b's recall/precision is **retired as fidelity evidence**
> (the matcher tracks the guide question, not group identity — confirmed by the
> cross-section control). The per-section theme lists **remain valid as descriptive
> output**: they are stable on re-extraction and quote-verified.
>
> The ambiguity left open here is now settled. Matching theme sets from the **same
> transcript** across **different** guide questions scored 0.0% — the lowest cell in
> the completed 2×2, below even different-group cross pairs. The 41.3–57.0%
> human-vs-human band reported below therefore reflects shared topic, not shared group
> identity, and should not be read as a ceiling for group discrimination.
>
> Full chain and reasoning: `docs/findings/2026-07-29_tier2b_cross_section_control.md`.
>
> _Nothing below has been altered — this document is retained as the record of the
> diagnostic process._

**Date:** 2026-07-29  
**Evaluator:** `gemini-2.5-flash` (temperature=0.0) — identical to the pilot and the FG1-vs-FG5 control  
**Pairs:** real fg1 vs real fg2, real fg1 vs real fg3, real fg2 vs real fg3  
**FG1 themes:** reused verbatim from `analysis/coding_frame/tier2b_guide_question_human_fg1.json` (not re-extracted)  
**Data floor:** MIN_PARTICIPANT_TURNS=3, MIN_WORDS=150  
**Read-only:** no synthetic generation; nothing written to `data/`; guide read from `configs/guides/`, not from a synthetic run artefact.

> The FG1-vs-FG5 control returned the wrong sign (mismatched 44.7% vs matched 21.3%).
> Two readings survive it: either per-section theme sets carry no group signal for
> anyone, or there is a real group signal the synthetic runs fail to reproduce.
> Scoring real groups against each other is the only thing that separates them.

---

## Part A — Segmentation

| Group | Participants | Sections | s1 | s2 | s3 | s4 | s5 |
|-------|-------------:|---------:|---:|---:|---:|---:|---:|
| real fg1 | 5 | 5 | 12t/414w | 7t/333w | 9t/481w | 13t/752w | 17t/936w |
| real fg2 | 5 | 5 | 5t/397w | 5t/558w | 5t/274w | 7t/976w | 6t/758w |
| real fg3 | 5 | 5 | 6t/399w | 15t/887w | 31t/2385w | 28t/2524w | 18t/1436w |

All sections on every group cleared the data floor; no section was skipped.

---

## Part B — Human-vs-human, section by section

Recall = side-A themes with a side-B counterpart / all side-A themes (same direction as the pilot).

| Idx | Section | fg1↔fg2 recall | fg1↔fg3 recall | fg2↔fg3 recall |
|----:|---------|------:|------:|------:|
| 1 | Opening discussion: male friendship and place | 33.3% | 66.7% | 33.3% |
| 2 | Everyday food decision-making | 100.0% | 33.3% | 50.0% |
| 3 | Gender and food choice | 66.7% | 33.3% | 33.3% |
| 4 | Imagining a plant-based shift | 25.0% | 25.0% | 50.0% |
| 5 | Making plant-based foods more appealing | 60.0% | 60.0% | 40.0% |
| **Mean** | | **57.0%** | **43.7%** | **41.3%** |

Theme pairs matched across all five sections: fg1↔fg2 **10**; fg1↔fg3 **8**; fg2↔fg3 **8**.

Precision: fg1↔fg2 52.0%; fg1↔fg3 43.0%; fg2↔fg3 40.3%.

---

## Part C — All figures side by side

| Comparison | Kind | Mean per-section recall |
|------------|------|------------------------:|
| Same text re-extracted (pilot stability check) <br>_upper bound: identical text, 3 extractions, mean pairwise recall_ | ceiling | 96.4% |
| real FG1 vs synth FG1 `macho_meals_fg1_run01` (matched) | matched | 21.3% |
| real FG1 vs synth FG5 `macho_meals_fg5_run01` (mismatched, primary) | mismatched | 44.7% |
| real FG1 vs synth FG5 `macho_meals_fg5_run03` (mismatched, second arm) | mismatched | 18.3% |
| real fg1 vs real fg2 | human-vs-human | **57.0%** |
| real fg1 vs real fg3 | human-vs-human | **43.7%** |
| real fg2 vs real fg3 | human-vs-human | **41.3%** |

> Reading rule fixed in advance, before the numbers were seen: if human-vs-human
> also lands in the ~20–45% band, no pair — human or synthetic — is separable at
> this granularity, and Tier 2b cannot serve as fidelity evidence. If
> human-vs-human sits clearly above 44.7%, a real group signal exists that the
> synthetic runs fail to reproduce, which validates the method and makes
> FG1-vs-FG5 a genuine negative finding.

---

## Part D — Match-quality audit

`match_tier2_themes` flags a judge/embedding disagreement only outside the
0.35–0.65 similarity band. Accepted pairs inside that band are never examined —
which is how *"Variety of available options" ↔ "Simplicity of limited choice"*
passed unremarked in the previous control. Every accepted pair below
cosine 0.50 is therefore listed here.

_No accepted pair fell below cosine 0.50._

### All accepted matches

**fg1 ↔ fg2**

- s1 (sim=0.725): _Shared Hobbies and Interests_ ↔ _Socializing in sports-related environments_
- s2 (sim=0.768): _Influence of group cravings_ ↔ _Social Dining Considerations_
- s2 (sim=0.676): _Variety of available options_ ↔ _Menu and Dietary Restrictions_
- s2 (sim=0.64): _Tendency for routine orders_ ↔ _Comfort and Enjoyment from Food_
- s3 (sim=0.854): _Food choices based on cravings_ ↔ _Personal preference as primary factor_
- s3 (sim=0.757): _Gender's influence on food choices_ ↔ _Gender has no influence on food choices_
- s4 (sim=0.827): _Challenges with taste and food substitutes_ ↔ _Unsatisfying taste and texture_
- s5 (sim=0.886): _Ingredient Transparency and Education_ ↔ _Transparency and processing information_
- s5 (sim=0.781): _Taste and Texture Improvement_ ↔ _Taste and texture as key factors_
- s5 (sim=0.742): _Affordability and Price Competitiveness_ ↔ _Cost and affordability_

**fg1 ↔ fg3**

- s1 (sim=0.625): _Affordable Food and Drink_ ↔ _Meeting at friends' houses to save money_
- s1 (sim=0.602): _Shared Hobbies and Interests_ ↔ _Integrating socialising with sports events_
- s2 (sim=0.754): _Influence of group cravings_ ↔ _Influence of Household Dynamics_
- s3 (sim=0.905): _Gender's influence on food choices_ ↔ _Gender's Limited Influence on Food Choices_
- s4 (sim=0.85): _Challenges with taste and food substitutes_ ↔ _Dissatisfaction with meat alternatives_
- s5 (sim=0.875): _Affordability and Price Competitiveness_ ↔ _Cost and Affordability_
- s5 (sim=0.784): _Health Benefits and Nutritional Value_ ↔ _Nutritional Value and Health Concerns_
- s5 (sim=0.707): _Taste and Texture Improvement_ ↔ _Mimicking Meat Taste and Texture_

**fg2 ↔ fg3**

- s1 (sim=0.817): _Socializing in sports-related environments_ ↔ _Integrating socialising with sports events_
- s2 (sim=0.756): _Impulsivity and Mood-Based Choices_ ↔ _Lack of Detailed Meal Planning_
- s2 (sim=0.726): _Social Dining Considerations_ ↔ _Influence of Household Dynamics_
- s3 (sim=0.836): _Gender has no influence on food choices_ ↔ _Gender's Limited Influence on Food Choices_
- s4 (sim=0.899): _Unsatisfying taste and texture_ ↔ _Dissatisfaction with meat alternatives_
- s4 (sim=0.67): _Lack of clarity on ingredients and processing_ ↔ _Skepticism about health benefits of plant-based foods_
- s5 (sim=0.782): _Cost and affordability_ ↔ _Cost and Affordability_
- s5 (sim=0.754): _Taste and texture as key factors_ ↔ _Mimicking Meat Taste and Texture_

---

_Auto-generated by `scripts/validate_tier2b_human_ceiling.py` (segmentation: `scripts/tier2b_segmentation.py`)._
