# ADR-004 — Every metric carries a status, and the status governs what may be shown

* **Status:** Accepted (2026-08-04)
* **Decides:** the seven-value status model, where each value comes from, and what it
  permits

## Context

The benchmark is not uniformly available. Some metrics are validated; some are
exploratory; nine are retained in the framework but withheld for want of human
validation (recorded 2026-08-04 in `metric_registry.csv` and the discussion draft as
`NOT_IN_REPORTED_INSTRUMENT`); two have no producer; several are comparative and
collapse when no human referent exists; five are defined only for synthetic runs; and
at least one ships its own validity flag and can be invalid for a given corpus.

A binary available/unavailable model would flatten all of that, and the first casualty
would be the withheld metrics — the ones the research deliberately declined to report.

## Decision

Seven statuses. A metric has a **catalogue status** (its ceiling) and each result has
a **result status** (what actually happened for that dataset).

| Status | Source | May be computed | May appear in a primary table | May appear in a figure |
|---|---|---|---|---|
| `AVAILABLE_VALIDATED` | registry `AUTOMATIC_VALIDATED` | yes | yes | yes |
| `AVAILABLE_EXPLORATORY` | registry `EXPLORATORY`, `AUTOMATIC_DIAGNOSTIC`, `LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC` | yes | **no** — exploratory table only | yes, labelled exploratory |
| `NOT_IN_REPORTED_INSTRUMENT` | registry `NOT_IN_REPORTED_INSTRUMENT` | **no** | no | no — catalogue entry only |
| `DEFERRED_NOT_IMPLEMENTED` | registry `DEFERRED_NOT_IMPLEMENTED` | no | no | no |
| `NOT_APPLICABLE_MISSING_INPUT` | runtime | n/a | row present, value `null` | omitted point, noted |
| `SYNTHETIC_ONLY` | namespace `_full_run_operational` | yes, synthetic only | yes, synthetic-only table | yes, never beside a human series |
| `REQUIRES_RESEARCHER_ADJUDICATION` | runtime | computed, not reported | no, until resolved | no, until resolved |

`NOT_APPLICABLE_MISSING_HUMAN_REFERENCE` is the named specialisation of
`NOT_APPLICABLE_MISSING_INPUT` used when the only missing input is the paired human
transcript (decision 6).

### Enforcement, not convention

* `permitted_outputs` on each catalogue entry is checked by the rendering layer. A
  `catalogue_only` metric has no code path that reaches a figure or a results table.
* The evaluation API raises if asked to compute a `NOT_IN_REPORTED_INSTRUMENT`
  metric. There is no flag, advanced mode or override that produces a value. This is
  a permanent exclusion under current evidence, not a feature gate.
* `null` is never coerced. Aggregators skip nulls and report the reduced denominator;
  they do not impute, and they do not treat a null as a zero-valued observation.

### Two metrics that must never be conflated

`specificity` (interpretive, withheld) and `reference_density` (interaction,
automatic) answer different questions with different methods and different evidence
classes. They may not share a label, a table column, a chart series or a caption. The
capability matrix §2 states the distinction; the rendering layer enforces it, and the
test suite asserts it on the produced output structures.

### Four questions kept apart at Level 3

Lexical diversity, between-speaker differentiation, cross-question voice recognition,
and position consistency are rendered under four separate headings. A high diversity
result may not be placed on the same axis as a differentiation or recognition result,
because breadth of vocabulary is not evidence of individual voices — a claim the
research explicitly declines to make.

## Consequences

**Positive.** The interface can present the whole framework honestly: what was
measured, what was measured only exploratorily, and what was deliberately not
measured and why. A future researcher inherits the reasoning, not just the outputs.

**Negative.** More surface to maintain: every metric needs a status, a reason and a
permitted-output list, and the enforcement points are places where a careless change
could silently loosen the model. The acceptance plan therefore treats a status change
as a hard failure (`PHASE1_ACCEPTANCE_TEST_PLAN.md` §2.3).

**Open.** The registry's `RETIRED_NOT_FOR_FIDELITY` row
(`tier2b_section_theme_lists`) fits none of the seven values. It is carried
provisionally as an eighth status pending a decision.


---

# AMENDMENT 1 - Phase 1 conditional approval (2026-08-04)

The decisions below **supersede** the text above where they conflict. Superseded text
is left in place so the review history stays legible.

## A1.1 Eighth status: `RETIRED_NOT_FOR_FIDELITY`

The gap left open at the end of this ADR is closed. It is a formal status, not a
mapping onto another.

| Status | Compute | Primary table | Exploratory table | Figure | Catalogue |
|---|---|---|---|---|---|
| `RETIRED_NOT_FOR_FIDELITY` | no | no | no | no | yes, with reason |

Enforcement is identical to `NOT_IN_REPORTED_INSTRUMENT`: the evaluation API raises
if asked to compute it, and `permitted_outputs` is `["catalogue_only"]`. The two are
kept distinct because their reasons differ, and the reason is what a future researcher
needs: a withheld metric awaits a validation that could be obtained; a retired metric
was judged unsuitable and withdrawn.

## A1.2 Fourth runtime status: `NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE`

The evaluator model version is part of the instrument. When the required model is
unavailable, the affected metrics take this status, nothing is called, and no
substitute model is used. Substitution would silently change the instrument, which is
precisely what the hard evaluator guard in `production_eval_pipeline.py` exists to
prevent.

## A1.3 Totals

Eight catalogue statuses; four runtime statuses. Two catalogue statuses
(`NOT_IN_REPORTED_INSTRUMENT`, `RETIRED_NOT_FOR_FIDELITY`) have no code path to any
value.
