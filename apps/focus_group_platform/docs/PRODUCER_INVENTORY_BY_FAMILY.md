# Preventive producer inventory, by metric family

Families are the stable identifiers: `THEMATIC_FIDELITY`, `INTERACTION_PROCESS`,
`AGENT_FIDELITY`, `OPERATIONAL`. The level NUMBER is a display label
(`display_order` / `display_label` in `platform_core/catalog.py`) and may be
re-presented without touching an identifier. Frozen artefact identifiers are historical
and are never renamed.

| Family | Current display label |
|---|---|
| `THEMATIC_FIDELITY` | Level 1 - Thematic fidelity |
| `INTERACTION_PROCESS` | Level 2 - Interaction process |
| `AGENT_FIDELITY` | Level 3 - Agent fidelity (exploratory) |

**Status: INVENTORY ONLY. Nothing in this document is implemented.**
Written before Level 1, 3 or 4 is built, because Phase 2B found that Level 2 had two
different producers where the Phase 0 audit had recorded one. That error would have
produced silently wrong synthetic values had the golden test not caught it. This
inventory asks the same question of the remaining levels *before* code exists.

The question is not "which function computes the metric" but **"did the human side and
the synthetic side travel through the same code, over the same kind of input?"**

---

## The distinction that matters

Level 2 taught the vocabulary. Two different things can diverge:

| Divergence | Meaning | Level 2 case |
|---|---|---|
| **Two producers** | different code computes each side | `structural_metrics_transportability.compute` vs `aggregate_production_results.compute_structural_metrics` |
| **Two inputs** | one producer, different material | complete human transcript vs derived comparable window |

Two producers is the dangerous case: the rules themselves differ (moderator
identification, entry exclusion, word counting), so routing by side is mandatory. Two
inputs is a scoping decision that is visible in the artefact and reproducible by
reading the right file.

---

## THEMATIC_FIDELITY (displayed as Level 1)

| | |
|---|---|
| **Human producer** | `scripts/thematic_coding.py` — `to_blind_text` → `code_transcript_tier1` → `verify_codes` → `compute_tier1_scores` |
| **Synthetic producer** | the same functions, called through `scripts/production_eval_pipeline.py` |
| **Rule differences** | **none in the producer.** The divergence is the input: the pipeline's own docstring states it reads "5 complete standardized human transcripts and 30 derived `comparable_transcript.json` windows". The human side is scored complete because those transcripts already begin at Question 1; the synthetic side is scored over the window so that introduction, presentation round and closing never enter the comparison. |
| **Instrument** | `gemini-3.5-flash`, enforced by a hard evaluator guard in the pipeline. The evaluator version is part of the instrument (ADR-004 A1.2). |
| **Transportability** | **Low without a codebook.** Every Tier-1 metric needs a deductive codebook and a paired human referent. Quote verification (`_is_verified_quote`) gates every code, so a new corpus inherits that gate for free — but the codebook is corpus-specific and is not supplied by the application. |
| **Golden source** | `analysis/production_evaluation/results/primary_effects_by_fg.csv`, `per_run_metrics.csv`, `thematic_code_presence_long.csv`, `thematic_reach_long.csv`. **Not** the structural artefacts. |
| **Risk to check first** | whether the cache key really keys on the comparable-window hash for the synthetic side (`freeze_evaluator_inputs.py` says it does — verify before trusting a cached result). |

---

## Level 3 / Level 4 — agent fidelity (the framework's complementary layer)

The framework taxonomy puts lexical distinctiveness, hyper-exactness, profile
continuity and profile consistency in **Level 4**; the four Level-3-agent questions in
the capability matrix are the same family. They are inventoried together because they
share producers.

### Lexical diversity and between-speaker similarity

| | |
|---|---|
| **Human producer** | `scripts/lexical_analysis.py` — one metric implementation, fed by `_human_session(fg)` |
| **Synthetic producer** | the same implementation, fed by `_synth_session(run)` |
| **Rule differences** | one producer, **two loaders**. `_human_session` reads `data/.../macho_meals/<fg>/transcript.json` and keys the speaker on `canonical_speaker_id`; `_synth_session` reads `comparable_transcripts/<run>/comparable_transcript.json` and keys on `speaker_id`, deriving the role from `speaker_id == "MODERATOR"`. The metric functions downstream (`_budgeted_overlap`, `_diversity`, `_mattr`, `_numerals`) are shared. |
| **Transportability** | **Medium.** The metric code is corpus-agnostic; the corpus discovery is not — `_sessions()` globs with the regex `macho_meals_(fg\d)(_demoonly)?_run0(\d)`, which (as Phase 2B found for the manifest) does not even match this corpus correctly: fg4 and fg5 use `run04`. Any reuse must parameterise the loader, and the regex must not be carried across. |
| **Golden source** | `analysis/production_evaluation/final/lexical_analysis.json` |
| **Risk to check first** | `_budgeted_overlap` subsamples. The offsets must be pinned before a golden comparison, or the metric is excluded from acceptance and the exclusion recorded. |

### Speaker attribution (voice recognisable across questions)

| | |
|---|---|
| **Producer** | `scripts/agent_fidelity_stylometry.py`, one implementation for both sides |
| **Rule differences** | none identified in the producer; the sides differ by input as above. Chance baselines differ **by construction** — the eligible participant set varies by fold, so each baseline is the mean of the per-fold `1/n_participants`. Raw accuracies are therefore not comparable across sides; the gain over each side's own baseline is. |
| **Transportability** | **Medium.** Character n-gram TF-IDF over a fixed word budget is corpus-agnostic; the eligibility rule (a fold needs enough participants) will behave differently on groups of a different size. |
| **Golden source** | `analysis/production_evaluation/agent_fidelity/agent_fidelity_stylometry.json` |
| **Risk to check first** | one demographics-only session produced no eligible fold and is absent (n=14, not 15). A reimplementation that silently produced 15 would be wrong. |

### Hyper-exactness

| | |
|---|---|
| **Producer** | none for the registry metric. Only a numeral-density proxy exists (`lexical_analysis._numerals`). |
| **Status** | `hyper_exactness` is `NOT_IN_REPORTED_INSTRUMENT`; the proxy is `AVAILABLE_EXPLORATORY` and explicitly does not discharge it. |
| **Golden source** | proxy values in `lexical_analysis.json` |

### Profile continuity and profile consistency

| | |
|---|---|
| **Producer** | none. Both are `Human` evidence class. |
| **Status** | `NOT_IN_REPORTED_INSTRUMENT`; no automatic implementation exists or should be written. |
| **Transportability** | not applicable — there is no instrument to transport. |
| **Note** | a synthetic profile-adherence figure has **no human counterpart**, so it may never be placed beside a human figure. |

---

## What to do before implementing any of these

1. **Locate the producer for each side separately.** Do not assume one. The question
   that found the Level 2 split is: *which script wrote the synthetic rows of the
   frozen artefact?* — answer it from the artefact's producer, not from the module
   whose name matches the metric.
2. **Read identifiers and indices from the frozen artefact**, never from a naming
   pattern. Two corrections in this project came from ignoring that: the acceptance
   run set and the study-replicate index.
3. **Pin any sampling** before comparing to a golden value, or exclude the metric and
   record the exclusion.
4. **Name the golden source per level.** Level 2 uses the three structural artefacts;
   Level 1 uses the thematic ones. Crossing them is a category error, not a rounding
   problem.
