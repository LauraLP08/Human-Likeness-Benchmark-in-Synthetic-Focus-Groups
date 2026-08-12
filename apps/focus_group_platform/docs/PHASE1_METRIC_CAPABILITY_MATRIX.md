# Phase 1 — Metric capability matrix

**Status: SPECIFICATION.** Source of truth for definitions:
`analysis/production_evaluation/metric_registry.csv` (46 rows, hash recorded per
result). **No metric is invented here.** This document adds only the *application
status* — what the platform may compute, refuse, or defer — using the vocabulary in
`decisions/ADR-004-evaluation-status-model.md`.

Every row's `definition`, `numerator`, `denominator`, `aggregation` and
`notes_and_caveats` are read from the registry at runtime and displayed verbatim.
This file records the fields the registry does not carry: status, required inputs,
human-referent dependency, new-corpus support, provenance function, and permitted
outputs.

---

## 1. Status vocabulary and its mapping from the registry

| Application status | Meaning | Registry `evidence_class` it comes from |
|---|---|---|
| `AVAILABLE_VALIDATED` | Computed and reportable as a primary result. | `AUTOMATIC_VALIDATED` |
| `AVAILABLE_EXPLORATORY` | Computed, reportable only as exploratory or diagnostic, never as a primary claim. | `EXPLORATORY`, `AUTOMATIC_DIAGNOSTIC`, `LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC` |
| `NOT_IN_REPORTED_INSTRUMENT` | Designed and not adopted; retained in the registry, **not computed** by this application. Permanent under current evidence. | `NOT_IN_REPORTED_INSTRUMENT` |
| `DEFERRED_NOT_IMPLEMENTED` | Defined in the registry, no working producer. | `DEFERRED_NOT_IMPLEMENTED` |
| `NOT_APPLICABLE_MISSING_INPUT` | Runtime state: a required input is absent for this dataset. Includes `NOT_APPLICABLE_MISSING_HUMAN_REFERENCE`. | — (runtime) |
| `SYNTHETIC_ONLY` | Defined only for synthetic runs; a human transcript cannot produce it. | namespace `_full_run_operational` |
| `REQUIRES_RESEARCHER_ADJUDICATION` | Computable, but this corpus produced a condition the metric itself flags as invalid or ambiguous. | — (runtime) |

Two of these are **runtime** statuses: a metric can be `AVAILABLE_VALIDATED` in the
catalogue and resolve to `NOT_APPLICABLE_MISSING_INPUT` or
`REQUIRES_RESEARCHER_ADJUDICATION` for a particular dataset. The catalogue status is
the ceiling; the result status is what is exported.

**Open vocabulary gap.** The registry contains one `RETIRED_NOT_FOR_FIDELITY` row
(`tier2b_section_theme_lists`). None of the seven approved values fits: it is not
withheld for want of human validation, not deferred, and not unavailable for want of
input — it was deliberately retired from fidelity use. It is listed below with a
provisional eighth status pending your decision (question Q1 in the delivery note).

---

## 2. Correction carried from Phase 0 — two different metrics

The audit blurred these. The registry does not, and neither will the application.

| | `specificity` | `reference_density` |
|---|---|---|
| Registry tier | `interpretive` | `interaction` |
| Registry evidence class | `NOT_IN_REPORTED_INSTRUMENT` | `AUTOMATIC_DIAGNOSTIC` |
| Application status | **`NOT_IN_REPORTED_INSTRUMENT`** | **`AVAILABLE_EXPLORATORY`** |
| What it asks | Does this turn carry a concrete detail — a time, place, action, person, decision — rather than generic opinion? An interpretive judgement. | In what proportion of participant turns does a speaker name or take up another named participant? A lexical/label count. |
| Produced by | An LLM coder, requiring the two-coder gold-standard validation that was never opened. | `structural_metrics_transportability.compute` → keys `reference_density`, `reference_density_label_aware`. |
| Unit | turn | turn |

They may never share a label, a chart axis, a table column or a caption. The
application shows `reference_density` under *interaction*, and shows `specificity` in
the catalogue with its withheld status and reason, with no value. A reader must not
be able to mistake the automatic count for the withheld judgement.

---

## 3. Catalogue

Columns: **ID** · **Level** · **Status** · **Unit** · **Human referent** ·
**New corpora** · **Provenance**.
`Human referent`: *required* = comparative by construction; *no* = computable on one
corpus alone. `New corpora`: whether the metric can run on data other than Macho
Meals. Denominator, aggregation and caveats come from the registry row and are not
restated here.

### Level 1 — thematic fidelity  (namespace `_comparable_window`)

| ID | Status | Unit | Human referent | New corpora | Provenance |
|---|---|---|---|---|---|
| `tier1_subtheme_recall` | AVAILABLE_VALIDATED | focus group | required | yes, with a codebook | `thematic_coding.code_transcript_tier1` + `compute_tier1_scores` |
| `tier1_matched_theme_precision` | AVAILABLE_VALIDATED | focus group | required | yes | same |
| `tier1_f1` | AVAILABLE_VALIDATED | focus group | required | yes | same |
| `tier1_participant_reach` | AVAILABLE_VALIDATED | focus group | required | yes | same |
| `tier1_theme_level_recall` | AVAILABLE_EXPLORATORY | focus group | required | yes | same |
| `tier1_theme_level_precision` | AVAILABLE_EXPLORATORY | focus group | required | yes | same |
| `tier1_salience_hierarchy` | AVAILABLE_EXPLORATORY | focus group | required | yes | `salience_hierarchy.py` over coded output |
| `tier1_coverage_by_word_count_curve` | AVAILABLE_EXPLORATORY | focus group | required | yes | producer exists, never run — see §4.1 |
| `tier1_length_matched_recall` | DEFERRED_NOT_IMPLEMENTED | focus group | required | — | none |
| `tier1_length_matched_precision` | DEFERRED_NOT_IMPLEMENTED | focus group | required | — | none |

Required inputs for the computed rows: locked comparable windows for both sides, a
deductive codebook, and a configured evaluator. Absent any of them → runtime
`NOT_APPLICABLE_MISSING_INPUT`. **Quote verification is not optional**:
`thematic_coding._is_verified_quote` gates every code, and a code whose quote fails
verification is dropped and its item raised to the review queue.

### Level 2 — interaction process  (namespace `_comparable_window`)

| ID | Status | Unit | Human referent | New corpora | Provenance |
|---|---|---|---|---|---|
| `words_per_turn_median` | AVAILABLE_VALIDATED | turn | no | yes | `structural_metrics_transportability.compute` |
| `words_per_turn_iqr` | AVAILABLE_VALIDATED | turn | no | yes | same |
| `short_turn_proportion_25w` | AVAILABLE_VALIDATED | turn | no | yes | same |
| `short_turn_proportion_10w` | AVAILABLE_EXPLORATORY | turn | no | yes | same |
| `short_turn_proportion_50w` | AVAILABLE_EXPLORATORY | turn | no | yes | same |
| `turn_balance_gini` | AVAILABLE_VALIDATED | focus group | no | yes | same |
| `word_balance_gini` | AVAILABLE_VALIDATED | focus group | no | yes | same |
| `moderator_turn_share` | AVAILABLE_VALIDATED | focus group | no | yes | same |
| `moderator_word_share` | AVAILABLE_VALIDATED | focus group | no | yes | same |
| `participant_participant_adjacency` | AVAILABLE_VALIDATED | turn transition | no | yes | same |
| `chain_depth` | AVAILABLE_VALIDATED | chain | no | yes | same |
| `reference_density` | AVAILABLE_EXPLORATORY | turn | no | yes, conditionally | same — see §4.2 |
| `length_ratio_synthetic_to_human` | AVAILABLE_EXPLORATORY | focus group | **required** | yes | same, ratio computed by the app |
| `agreement` | NOT_IN_REPORTED_INSTRUMENT | turn | — | — | not computed |
| `disagreement` | NOT_IN_REPORTED_INSTRUMENT | turn | — | — | not computed |
| `challenge` | NOT_IN_REPORTED_INSTRUMENT | turn | — | — | not computed |
| `neutral_elaboration` | NOT_IN_REPORTED_INSTRUMENT | turn | — | — | not computed |
| `specificity` | NOT_IN_REPORTED_INSTRUMENT | turn | — | — | not computed — see §2 |
| `substantive_vs_superficial_elaboration` | NOT_IN_REPORTED_INSTRUMENT | turn | — | — | not computed |

**Hard precondition.** Every computed row requires normalised turns carrying
`speaker_role`, `content` and `canonical_speaker_id`;
`structural_metrics_transportability.compute` raises `KeyError` otherwise
(PHASE0 §10, C-1). Level 2 is unavailable, with that reason shown, until
normalisation succeeds.

### Level 3 — agent fidelity, exploratory

Four questions that must stay separate, per the brief. The application groups them
under four headings and never lets one answer the other.

**Q1. Does the corpus use varied vocabulary?**

| ID | Status | Unit | Human referent | Provenance |
|---|---|---|---|---|
| lexical diversity (TTR / MATTR) | AVAILABLE_EXPLORATORY | focus group | no | `lexical_analysis._diversity` / `_mattr` (copy-and-parameterise) |

**Q2. Do participants in one group speak differently from each other?**

| ID | Status | Unit | Human referent | Provenance |
|---|---|---|---|---|
| between-speaker lexical similarity | AVAILABLE_EXPLORATORY | focus group | no | `lexical_analysis._budgeted_overlap`, `_unadjusted_jaccard` |

**Q3. Can one voice be recognised across questions?**

| ID | Status | Unit | Human referent | Provenance |
|---|---|---|---|---|
| speaker attribution accuracy | AVAILABLE_EXPLORATORY | focus-group session | no | `agent_fidelity_stylometry.py` |
| chance-corrected attribution | AVAILABLE_EXPLORATORY | focus-group session | no | same |

**Q4. Are stated positions compatible along the conversation?**

| ID | Status | Unit | Human referent | Provenance |
|---|---|---|---|---|
| `profile_continuity_group` | NOT_IN_REPORTED_INSTRUMENT | focus group | — | not computed |
| `profile_consistency_group` | NOT_IN_REPORTED_INSTRUMENT | focus group | — | not computed |
| `attribute_attitude_relational_fidelity` | AVAILABLE_EXPLORATORY | focus group | no | registry `exploratory` row |
| `hyper_exactness` | NOT_IN_REPORTED_INSTRUMENT | turn | — | not computed |
| numeral-density proxy | AVAILABLE_EXPLORATORY | focus group | no | `lexical_analysis._numerals` |

**Two guards the UI enforces.** (a) A high lexical-diversity result may never be
rendered on the same axis, table or caption as a Q2 or Q3 result — high diversity is
not evidence of individual voices, and the four headings exist to keep that from
being read off a chart. (b) The numeral-density proxy always carries the registry's
own caveat that it does **not** discharge `hyper_exactness`; it is labelled *proxy*
in every export.

**Profile-adherence guard.** No synthetic profile-adherence figure is ever placed
beside a human figure, because no equivalent human profile exists. Attempting it is
blocked, not warned.

### Level 2b — accumulation and open coding

| ID | Status | Unit | Human referent | New corpora | Provenance |
|---|---|---|---|---|---|
| `tier2_open_themes` | AVAILABLE_EXPLORATORY | focus group | required | yes | Tier-2 path in `thematic_coding.py` |
| `tier2_not_observed_in_human_themes` | AVAILABLE_EXPLORATORY | focus group | required | yes | same |
| `tier2_missed_themes` | AVAILABLE_EXPLORATORY | focus group | required | yes | same |
| `saturation_curve` | AVAILABLE_EXPLORATORY | study replicate | no | yes, ≥2 groups | `saturation_analysis.py` |
| `theme_recurrence_across_groups` | AVAILABLE_EXPLORATORY | study replicate | no | yes, ≥2 groups | same |
| `evidence_localized_length_matched_recall` | AVAILABLE_EXPLORATORY | excerpt | required | yes | D2 proxy path |
| `evidence_localized_length_matched_precision` | AVAILABLE_EXPLORATORY | excerpt | required | yes | D2 proxy path |
| `tier2b_section_theme_lists` | **RETIRED_NOT_FOR_FIDELITY** (provisional 8th status) | guide section | — | — | not offered |

### Operational  (namespace `_full_run_operational` — the full run, not the window)

| ID | Status | Unit | Human referent | Provenance |
|---|---|---|---|---|
| `forced_silence_count` | SYNTHETIC_ONLY | synthetic run | no | run artefacts |
| `forced_silence_rate` | SYNTHETIC_ONLY | synthetic run | no | run artefacts |
| `api_error_rate` | SYNTHETIC_ONLY | synthetic run | no | `api_calls.jsonl` |
| `response_truncation_rate` | SYNTHETIC_ONLY | synthetic run | no | `api_calls.jsonl` (`response_truncated`) |
| `full_run_total_words` | SYNTHETIC_ONLY | synthetic run | no | `transcript.json` |

These are the only metrics computed over the **full** run rather than the comparable
window. The UI states the namespace beside them, because mixing the two namespaces is
the easiest way to produce a wrong denominator.

---

## 4. Metrics needing specific handling

### 4.1 `tier1_coverage_by_word_count_curve`
Registry class is `AUTOMATIC_DIAGNOSTIC`, **not** deferred — Phase 0 said otherwise
and was wrong (PHASE0 §10, C-2). A producer exists and was never run for the thesis.
The application may offer it as `AVAILABLE_EXPLORATORY`, and must state that it has
no frozen counterpart, so Phase 5 cannot check it against anything.

### 4.2 `reference_density` → `REQUIRES_RESEARCHER_ADJUDICATION`
`compute` returns validity companions: `reference_density_valid`,
`reference_density_labels_collapsed`, `reference_density_unrepresentable_names`,
`reference_density_ambiguous_names_excluded`, and a `reference_density_label_aware`
variant. When `reference_density_valid` is false — speaker labels collapsed or names
unrepresentable — the value is **not** reported. The item goes to the review queue
with the offending labels listed, and the researcher either supplies a label mapping
or marks the metric not applicable for that corpus. This is the pattern for every
metric that ships its own validity flag.

### 4.3 Comparative metrics without a human referent
`length_ratio_synthetic_to_human` and all Level 1 metrics are comparative by
construction. With no paired human file they resolve to
`NOT_APPLICABLE_MISSING_HUMAN_REFERENCE`, `value = null`, and the export carries the
reason (decision 6). No zero, no imputation, no silent omission from the table — the
row appears, with the status in place of a number.

### 4.4 Withheld metrics in the interface
Rendered in the catalogue with: name, registry definition verbatim, status badge,
and this reason — *"Retained in the framework and excluded prospectively: the
two-coder gold-standard human validation this metric requires was never opened. No
value is computed."* No slider, no toggle, no advanced mode reveals a value. The
catalogue entry is the deliverable.

---

## 5. What the catalogue stores per metric

The runtime record backing every row above.

```
CatalogEntry
  metric_id                 str
  display_name              str
  definition                str      verbatim from the registry
  benchmark_level           enum(level1_thematic|level2_interaction|level3_agent|level2b_accumulation|operational)
  registry_tier             str      verbatim
  registry_evidence_class   str      verbatim
  status                    MetricStatus
  status_reason             str
  required_inputs           list[enum(human_window|synthetic_window|codebook|guide|profiles|evaluator|normalised_turns)]
  unit_of_analysis          str      verbatim
  denominator_definition    str      verbatim
  aggregation_hierarchy     str      verbatim
  requires_human_referent   bool
  requires_human_review     bool
  supports_new_corpora      bool
  provenance_function       str      module.function or "not computed"
  limitations               str      verbatim registry caveats + application-specific additions
  permitted_outputs         list[enum(primary_table|exploratory_table|figure|report_body|catalogue_only)]
  plain_language_gloss      str
  explanation_source        str
  metric_version            str
```

`permitted_outputs` is enforced, not advisory: a `catalogue_only` metric has no code
path that can place it in a figure or a results table.


---

# AMENDMENT 1 - Phase 1 conditional approval (2026-08-04)

The decisions below **supersede** the text above where they conflict. Superseded text
is left in place so the review history stays legible.

## A1.1 `RETIRED_NOT_FOR_FIDELITY` is the eighth formal status

The vocabulary gap flagged in section 1 is closed. It is **not** mapped to `WITHHELD`
or `DEFERRED`.

| Status | Meaning | Compute | Results table | Figure | Catalogue |
|---|---|---|---|---|---|
| `RETIRED_NOT_FOR_FIDELITY` | Exists in the registry; deliberately withdrawn as a fidelity indicator | never | never | never | yes, with the retirement reason |

`tier2b_section_theme_lists` carries it. Its catalogue entry states: *"Retired as a
fidelity indicator. It remains in the registry as a record of what was tried and
withdrawn. No value is computed."*

The distinction from the neighbouring statuses is the **reason** for exclusion, which
is what a future researcher needs: `NOT_IN_REPORTED_INSTRUMENT` lacks a validation
that could in principle be obtained; `DEFERRED_NOT_IMPLEMENTED` lacks a producer;
`RETIRED_NOT_FOR_FIDELITY` was judged unsuitable for the purpose and withdrawn.

## A1.2 New runtime status for Level 1

`NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE`. The evaluator model version is part of the
instrument (`production_eval_pipeline.py` enforces a hard evaluator guard). When the
required model is unavailable every Level 1 metric resolves to this status, with a
message naming the required model and stating that no substitute is used because
substitution would change the instrument. Adding an alternative model requires new
documented validation, not a configuration change.

## A1.3 Status count

Eight catalogue statuses and four runtime statuses
(`NOT_APPLICABLE_MISSING_INPUT`, `NOT_APPLICABLE_MISSING_HUMAN_REFERENCE`,
`NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE`, `REQUIRES_RESEARCHER_ADJUDICATION`).


---

# AMENDMENT 2 - Phase 2A.1 hardening (2026-08-04)

Findings from an independent security review of the Phase 2A code. These supersede the
text above where they conflict; the superseded text stays so the review history is
legible.

## A2.1 Level 2 has TWO producers, not one

The matrix listed `structural_metrics_transportability.compute` as the provenance for
every Level 2 row. That is correct for the **human** side only. The frozen synthetic
values were produced by
`aggregate_production_results.compute_structural_metrics`, which takes a comparable
window, filters empty entries (`blind_included_entries`) and derives the role from
`speaker_id == "MODERATOR"`.

| Side | Producer | Input |
|---|---|---|
| human | `structural_metrics_transportability.compute(turns, roster_names)` | standardized transcript + participant roster |
| synthetic | `aggregate_production_results.compute_structural_metrics(entries)` | one comparable window |

Routing by side is a requirement: running the human producer over a synthetic window
does not reproduce the frozen values. `platform_core/level2.py` routes and records
which producer ran in every result's provenance.

## A2.2 Level 2 blocks rather than guesses

When normalisation leaves `speaker_role` or `canonical_speaker_id` unresolved, every
Level 2 metric resolves to `NOT_APPLICABLE_MISSING_INPUT` with that reason, and a
review item names the turns. No role is inferred from position.
