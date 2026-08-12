# CONSENSUS_SCALE_LLM_EXPLORATORY — design

*Drafted 6 August 2026 to the researcher's specification. Dry run passes; **no live call
made**. Status `LLM_CODED_HUMAN_VALIDATION_REQUIRED`. Separate from Tier 1/2/2B, from
`CONSENSUS_DYNAMICS_EXPLORATORY` and from `CONSENSUS_FUNCTION_LLM_EXPLORATORY` (the
turn-level layer this replaces); never aggregated with any of them.*

Script: `scripts/consensus_scale_coding.py` · Evaluator `gemini-3.5-flash`, temperature **not
transmittable** (see the FG1 pilot results of the previous layer, §2.1 of its design).

## Stages

| | What | Calls (FG1) |
|---|---|---|
| **A extract** | 2 key claims per guide question per transcript, each with a verbatim quote | 7 |
| **B pool** | candidates from all 7 transcripts merged/deduplicated into ONE shared claim set per guide question | 5 |
| **C score** | each participant × each pooled claim, ordinal stance | 35 |
| **D probe** | extraction-stability probe (2 sections re-extracted twice) | 4 |
| | **total** | **51** |

**Anchor: pooled shared claim set** (researcher's decision). Every condition is scored against
the same claims, so the comparison is about content — "on this claim, that group dispersed
more" — not merely about the value of a statistic computed over different objects.

## Scale

| Value | Meaning |
|---|---|
| `+1` | strong agreement / explicit validation |
| `0` | neutral or no clear position, **having engaged the subject** |
| `-1` | strong disagreement / objection |
| `not_addressed` | spoke in the section, never touched this claim — **model-assigned** |
| `absent_from_section` | never spoke in the section — **deterministic, computed in Python** |

`not_addressed` is separate from `0` because synthetic turns average 232 words against 48
human: synthetic participants touch nearly every claim, human participants do not. Folding
"never mentioned it" into `0` would fill the human cells with zeros, depress human dispersion
and manufacture human consensus — the same length asymmetry that invalidated the turn-level
layer, arriving by another door. **Dispersion is computed only over stances in {−1, 0, +1};
coverage is reported beside every statistic as a result in its own right.**

## Metrics (stage D, deterministic, no model)

Per transcript × guide section × claim:

* full distribution: counts of +1 / 0 / −1, plus `n_not_addressed`, `n_absent_from_section`
* `n_with_stance` (the denominator) and `coverage_of_present`
* **mean stance = DIRECTION**, not consensus — a group unanimous at −1 has perfect consensus
  and a strongly negative position. Direction and dispersion are reported on separate axes and
  never collapsed into one score.
* **Leik (1966) ordinal consensus** — the preferred concentration measure, because the scale is
  ordinal and SD assumes the step +1→0 equals 0→−1. Formula: cumulative proportions `F_i`,
  `d_i = F_i if F_i ≤ 0.5 else 1 − F_i`, `D = Σd_i`, consensus `= 1 − D/((K−1)/2)`. 1.0 =
  everyone in one category, 0.0 = maximum dispersion. Verified in the dry run against
  hand-computable cases (unanimity → 1.0, even split on the poles → 0.0).
* standard deviation, labelled with its interval assumption
* mode, **with an explicit tie flag**, and proportion in the modal category

**No coefficient of variation.** `CV = SD/mean` is undefined or explosive on a scale whose mean
can be exactly zero and which crosses zero. It was in the original specification and is
deliberately not implemented.

**No composite consensus score.**

## Blinding — and a defect found in the shared segmenter

Sections and the blind `Participant N` render come from `tier2b_segmentation.py`, so this layer
inherits Tier 2B's section boundaries rather than inventing its own. Only the 5 sections
comparable on both sides are used; sections 0 and 6 have no human counterpart and are excluded,
which also keeps the name-introduction round out of the evaluator's view.

**`tier2b_segmentation` masks the speaker LABEL but leaves real first names inside utterance
text.** Measured over comparable sections 1–5 of FG1:

| | in-text real-name occurrences |
|---|---|
| human | **1** |
| enriched runs | 57 / 77 / 72 |
| demographics-only runs | 68 / 44 / 60 |

Synthetic participants address each other by name constantly; the humans barely do. Raw name
density is therefore itself a near-perfect condition signal, and unmasked names would also let
the scorer resolve "Amir said" to a real identity.

**Fixed in this layer** by post-processing the segmenter's output (`mask_in_text_names`).
`tier2b_segmentation.py` is **not** modified: it is built architecture and Tier 2B's existing
results were produced under its current behaviour. **This is reported as a finding about Tier
2B's blinding claim, not silently repaired underneath it.**

As always, blinding here is **procedural, not perceptual**: turn length (48 vs 232 words) still
identifies the side in any excerpt, and no claim is made that the evaluator cannot tell.

## The feasibility limit this design has, stated before spending

`n_present` — participants who actually spoke in a section, the ceiling on the denominator:

| | s1 | s2 | s3 | s4 | s5 |
|---|---|---|---|---|---|
| human | 5 | 4 | 5 | 5 | 5 |
| enriched run01 / 02 / 03 | 4 / 5 / 3 | 2 / 3 / 2 | 5 / 3 / 5 | 5 / 3 / 5 | 5 / 5 / 5 |
| demoonly run01 / 02 / 03 | 3 / 3 / 3 | 2 / 2 / 5 | 5 / 3 / 3 | 5 / 4 / 5 | 4 / 3 / 5 |

Two consequences, neither of which more API calls can fix:

1. **Section 2 is close to uncomputable on the synthetic side** — five of six synthetic cells
   have 2–3 speakers, so dispersion would be computed over 2–3 stances. Recommend reporting
   section 2 with its `n` and excluding it from any cross-section summary, or dropping it.
2. **Counter to the expectation behind this design, the HUMAN transcript has more participants
   present per section (24 slots across the 5 sections) than most synthetic runs** (15–24).
   Synthetic sessions produce more words from fewer distinct speakers per section. So the
   denominator problem is *worse* on the synthetic side, and coverage will not be a story about
   humans failing to engage.

With `n_with_stance` ≤ 5 and three scale points there are at most 21 distinct distributions per
claim; every statistic below is coarse and lumpy by construction. This layer can support
"these distributions differ" at the descriptive level for one FG. It cannot support a precise
dispersion estimate, and no amount of coding will change that — the constraint is the number of
people in the room.
