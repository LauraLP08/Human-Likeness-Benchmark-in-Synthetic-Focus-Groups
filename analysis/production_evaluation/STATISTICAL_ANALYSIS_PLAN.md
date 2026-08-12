# Statistical Analysis Plan — Macho Meals synthetic focus group evaluation

**Finalised after automated results and diagnostic inspections were available, but
before formal integrative interpretation and conclusions were written.** 2026-07-31.
**Corpus: 35/35 Tier-1 Batch results complete. No further evaluator calls.**

### Temporal status — read this first

This document was **not** written before the results existed. Precisely:

* the **automated results had already been observed** — condition means, both levels
  of SD, and the per-FG directions;
* a **diagnostic inspection of FG4 had already been carried out**, including the
  zero-overlap case and the codes and quotes behind it;
* the **formal qualitative–quantitative synthesis had not yet been performed**, and
  no conclusions had been written;
* this is therefore **not a preregistration and not a confirmatory analysis**.

Describing it as pre-specified would be false, and would lend post-hoc choices an
authority they have not earned.

What follows therefore separates two kinds of decision. The distinction matters:
the first set constrains what the results were allowed to look like; the second was
chosen knowing what they do look like.

#### A PRIORI / PRE-SCORING decisions
Fixed in `frozen_evaluation_spec.md` and `metric_registry.csv` before any Tier-1
result existed:

* recall and precision are **primary**, reported separately and before any combined figure;
* F1 is **secondary/complementary**, never the headline;
* **no composite "human-likeness" score** is constructed;
* all **three replicates are retained**, never collapsed into a mean alone;
* the comparison is made at the **focus-group level**;
* interpretive metrics are **withheld** pending a human gold standard;
* the 15 sessions of a condition are **never concatenated** against the 5 humans.

#### POST-RESULT / PRE-INTERPRETATION decisions
Chosen after the results were available, and therefore **exploratory, not
confirmatory**:

* reporting an **exact paired sign test**;
* presenting **both levels of SD** side by side;
* the **descriptive sensitivity analysis excluding FG4**;
* the **qualitative audit of the FG4 zero-overlap case**;
* reporting the **ratios between the two SDs**.

None of these five can confirm a hypothesis. Each was prompted by something already
seen in the data, so any apparent support they lend is not independent of the
observation that motivated them. They are documented here so that a reader can
discount them accordingly, not so that they can be cited as pre-planned.

---

## 1. Research question and estimands

**Question.** To what extent does enriching agent profiles with the study's
available metadata improve thematic, interactional and group-level correspondence
with the paired human focus group, relative to agents configured with demographic
information only?

**Primary estimand.** For each focus group *g*, the difference

> Δ_g = (enriched correspondence with human *g*) − (demographics-only correspondence with human *g*)

and the distribution of Δ over the five focus groups.

**What this is not.** Not a population estimate. Not a causal effect of "enrichment"
in general. Five focus groups, one study, one generator configuration, one evaluator.

---

## 2. Unit of analysis — FROZEN

| | |
|---|---|
| **Paired unit** | the focus group |
| **n** | **5 pairs** |
| **Cell value** | mean of that FG × condition's **three canonical replicates** |
| **Pairing** | each synthetic cell is compared only to *its own* paired human transcript |

**Replicates are generator variability, not focus groups.** The three replicates per
FG × condition estimate how much output varies when the same configuration is run
again. They are not three additional groups, not independent samples of a
population, and not exchangeable with the five human transcripts.

**Consequently the following are NOT run** on this corpus:

* t-test, Mann–Whitney, or any test treating the 15 runs per condition as
  independent observations;
* regression with run-level rows and no accounting for FG nesting;
* confidence intervals built on n = 15 independent observations.

Treating 15 runs as 15 independent units would inflate the apparent sample threefold
by counting generator noise as evidence about focus groups.

---

## 3. Levels of aggregation

| Level | Unit | n | Purpose |
|---|---|---|---|
| 1. Session | one synthetic run vs its paired human | 30 | raw values, retained, never replaced by means |
| 2. FG × condition | mean of 3 replicates | 10 | **the cell used for the primary comparison** |
| 2b. Paired effect | enriched − demographics-only, per FG | **5** | **the primary comparison** |
| 3. Study replicate | five FGs assembled by replication index | 6 | between-study-realisation variability |
| 4. Condition | across the 3 study replicates | 2 | descriptive only |

Replicate values are retained in `*_values` columns at every level. A mean never
replaces the values behind it.

---

## 4. Metrics

### Primary
* `tier1_subtheme_recall`
* `tier1_matched_theme_precision`
* `tier1_participant_reach` — always with its implementation caveat

Recall and precision are **always reported separately and before** any combined
figure. They answer different questions and can move in opposite directions.

### Secondary / complementary
* `tier1_f1_secondary` — reported **after** recall and precision, never as the headline
* `tier1_theme_level_recall` / `_precision` — parent-theme granularity, diagnostic
* `tier1_salience_hierarchy` — Spearman over shared verified subthemes

### Structural / interaction
Reported descriptively; not part of the primary comparison.

### Withheld
All interpretive metrics (agreement, disagreement, challenge, elaboration,
specificity, profile continuity/consistency, hyper-exactness) remain **WITHHELD**
pending a completed human gold standard, which does not exist. The current coder
exercise is a **partial emergent review** (7 shared units), not a gold standard.

### Deferred
`tier1_length_matched_recall` / `_precision` remain **DEFERRED_NOT_IMPLEMENTED**.
The offline `evidence_localized_length_matched_*` metrics are a **different
estimand** and are EXPLORATORY; they must never be reported under the deferred names.

---

## 5. Variability — two different SDs, never interchangeable

Both are reported, each labelled with its level and n. **Neither is quoted without
both.**

**Session-level SD (n = 15 sessions per condition).** Mixes two sources: variation
*between focus groups* and variation *between replicates nested within* a focus
group. It is not a measure of replicate noise alone.

**Study-replicate SD (n = 3 per condition).** Computed over three averages, each
already aggregated across five focus groups. With n = 3, an SD is a **very unstable**
estimate — it is reported for completeness, not as a precise quantity.

Observed ratios (session-level SD ÷ study-replicate SD):

| Metric | enriched | demographics-only |
|---|---|---|
| recall | 2.03 | 6.64 |
| precision | 7.22 | 11.12 |
| reach | 1.09 | 18.70 |

**These ratios are not a result, and reporting them is itself a post-result
decision.** In this corpus, the three five-FG averages are less dispersed than the 15
session-level observations. Averaging commonly reduces observed dispersion, but this
is not guaranteed for every realised sample, and n=3 makes the resulting SD unstable.

A previous draft summarised the ratios as "the two levels differ by roughly 2–11×".
That both understated the range — reach reaches **18.70** — and presented a
consequence of how the two statistics are constructed as though it were a finding.
Withdrawn.

The two SDs answer different questions: *how much do individual sessions vary?* and
*how much does a whole five-group study realisation vary?* Neither substitutes for
the other.

---

## 6. Inference — deliberately limited

**No confirmatory p-values are reported.**

An exact paired **sign test** may be reported as **EXPLORATORY** (a post-result
decision — see the temporal status above), always with its own ceiling.

**The ceiling follows `n_effective`, not `n_total`.** A tie carries no sign and is
dropped from the test, so a metric with ties is tested on fewer pairs than the design
provides:

| | |
|---|---|
| `n_total` | number of paired FGs = 5 |
| `n_effective` | number of **non-zero** differences |
| `ties` | `n_total − n_effective` |
| possible assignments | `2^n_effective` |
| minimum attainable two-sided p | `2 / 2^n_effective` |

As realised in this corpus:

| Metric | n_effective | ties | assignments | min attainable two-sided p |
|---|---|---|---|---|
| recall | 5 | 0 | 32 | **0.0625** |
| precision | **3** | **2** | **8** | **0.25** |
| reach | 5 | 0 | 32 | **0.0625** |
| F1 *(secondary)* | 5 | 0 | 32 | **0.0625** |

**None of these can reach p < .05 at any effect size.** Quoting the n=5 / 32-assignment
ceiling for **precision** would be wrong by a factor of four: with two ties its floor
is 0.25.

A non-significant result from a test whose floor already exceeds .05 carries no
evidential weight against an effect. Reporting it without the ceiling would present
an arithmetic impossibility as a null finding.

**Primary evidence is the per-FG effect table**: five paired differences, their
direction, magnitude and within-cell spread — read alongside the qualitative
inspection of codes and quotes.

---

## 7. Missingness and completeness

* Aggregation is **gated**: exactly 5 human + 30 synthetic complete Batch results,
  3 replicates per FG × condition with indices [1,2,3], 35 unique cache keys.
  A partial corpus refuses to aggregate.
* Incomplete or malformed evaluator responses go to **quarantine**, never to cache,
  and never into an aggregate. A missing code from a truncated response is **never**
  read as `present=false`.
* Rates with a genuinely zero denominator are `None`, never 0.0 or 1.0.
* F1 is `None` only when recall or precision is undefined; two non-empty disjoint
  sets give a measured F1 of 0.0.
* Only one execution mode enters the corpus (`batch`). Synchronous results from the
  preflight investigation are excluded and are not pooled.

---

## 8. FG4 demographics-only — sensitivity, not exclusion

All three FG4 demographics-only replicates yield **subtheme recall 0 and precision 0
with `synthetic_present_n` > 0**.

**This is zero overlap, not zero coding.** Every run returned quote-verified codes
with reach 1.0. At parent-theme granularity the same runs show **theme-level recall
0.25–0.50 with precision 1.00** — the zero is specific to subtheme granularity.

**FG4 is NOT excluded.** There is no technical failure to justify exclusion: the
responses are complete, schema-valid and quote-verified. Results are reported **with
and without FG4** purely as a diagnostic sensitivity check, and every such
presentation states that exclusion is **not methodologically justified**.

A separate qualitative report (`fg4_demographics_only_qualitative_report.json`)
records the six human codes, the codes asserted by each run, their verified quotes,
the missed human codes, and candidate interpretation differences.

**Specific question referred to human review — not decided here.** In
`macho_meals_fg4_demoonly_run01`, subtheme **A.1** is asserted with reach 1.0 on
three verified quotes:

> [T021] *"being a bloke probably means I'm not thinking about the food side of
> things as much as she is"*
> [T023] *"Yeah, it rings true in terms of my wife doing most of the planning"*
> [T027] *"your awareness of the gender dynamics in your household is sharper than
> Gregor's or mine"*

Two of the three refer to **household planning and domestic division of labour**
rather than to the speaker's own food choice. Whether this evidence supports A.1 as
*gender influencing food choice*, or instead describes *domestic division of
labour/planning* and so was mis-assigned, is a **human coding judgement**.

**No code is changed automatically.** The reviewer's verdict is to be recorded in
the qualitative report under `human_review_verdict`, with a date and reasoning. Until
then A.1 stands as the evaluator returned it, and this question is an open caveat on
the FG4 demographics-only reading — not a correction that has been applied.

---

## 9. Integration with the qualitative analysis

The quantitative tables do not stand alone. Planned integration:

1. **Per-FG effects first** — five paired differences with their spread.
2. **Code-level inspection** — which subthemes are recovered, which missed, and what
   the verified quotes actually say, per FG and condition.
3. **Not-observed themes** — synthetic themes with no human counterpart are recorded
   as `synthetic_only_not_observed_in_human`, never as errors or hallucinations.
4. **Granularity check** — subtheme vs parent-theme results read together, since FG4
   shows they can diverge sharply.
5. **Length asymmetry** — the D2 coverage curve and the evidence-localised proxies
   read as context on whether length drives any apparent difference. Observed
   `length_ratio_synthetic_to_human` spans 0.82×–5.19× (median 2.08×).
6. **Partial human review** — once clustering is adjudicated, the emergent themes
   inform whether the codebook captures what human coders see. This is a qualitative
   input, not a validation statistic.

---

## 10. Standing limitations

* One study, five focus groups, one generator configuration, one evaluator model.
* A single human transcript per FG: no within-group human variability can be
  estimated, so a synthetic replicate's spread has no human comparator.
* Replicates are not independent groups; n for the primary comparison is 5.
* Tier-1 coding is LLM-produced. Quote verification confirms that quotes are verbatim
  and attributed to the right turn; it does not confirm that the code is the right
  code. That judgement is what the (incomplete) human gold standard was for.
* Interpretive metrics are withheld; the emergent human review covers 7 of 15 units
  and is not a gold standard.
* `tier1_length_matched_*` are deferred, so the length question is addressed only by
  the coverage curve and an explicitly different-estimand proxy.
* Engagement-path asymmetry between conditions is recorded as operational metadata
  and is a known confound on reach.

---

## Amendment 1 — 2026-07-31 — full-precision effect arithmetic

**Made after results were inspected. Corrective, not interpretive.**

Signs and ties were being decided on twice-rounded numbers: the aggregator rounds
session values to 4 dp for its tables, and the effect script then averaged those,
differenced them, and rounded again. A true difference below 5e-5 would have been
recorded as an exact tie.

Fixed: means, differences, signs and ties are computed at full precision from the
evaluator cache via `unrounded_run_metrics`, which shares its definitions with the
table path. **Rounding now happens only on output.** A tie is defined as a
full-precision difference of exactly 0.0.

**Audited before and after with exact rational arithmetic.** No sign, tie, direction,
p-value, `n_effective` or ceiling changed. One displayed figure was corrected:

| | was | is | exact |
|---|---|---|---|
| recall, FG2 difference | −0.0477 | **−0.0476** | −1/21 = −0.047619… |

The old figure came from differencing two already-rounded means. The FG1 and FG3
precision ties were confirmed **exactly zero** in rational arithmetic — genuine ties,
not rounding artefacts.

## Amendment 2 — 2026-07-31 — F1 full-precision arithmetic

**Made after results were inspected. Corrective, not interpretive.**

Amendment 1 corrected recall, precision and reach but left `f1_score` rounding to
4 dp unconditionally, and `unrounded_run_metrics` called it. F1 differences, signs
and ties were therefore still decided on 4-dp values while the other three metrics
were exact — a partially corrected pipeline, in which three metrics are trustworthy
and the fourth silently is not.

Fixed: `f1_score` takes `ndigits`, mirroring `_rate` — 4 for tables, `None` for
downstream arithmetic. The formula remains in one place; `aggregate()`'s table output
is unchanged.

**Audited before and after.** No F1 sign, tie, direction, p-value, `n_effective`,
ceiling, or across-FG statistic changed. Three **within-cell SD** figures were
corrected, each verified against exact rational arithmetic:

| Cell | was | is | exact |
|---|---|---|---|
| F1, FG2 demographics-only SD | 0.2298 | **0.2297** | SD of {2/9, 2/3, 6/11} = 0.22974710 |
| F1, FG3 enriched SD | 0.0635 | **0.0634** | SD of {6/13, 4/7, 4/7} = 0.06344508 |
| F1, FG4 enriched SD | 0.1867 | **0.1866** | SD of {6/11, 2/9, 2/9} = 0.18661827 |

Recall, precision and reach are untouched by this amendment.

**Artifacts changed by Amendment 2:** five result artifacts
(`primary_effects_by_fg.csv`, `primary_effects_summary.csv`,
`primary_effects_fg_level.json`, `STATISTICAL_ANALYSIS_PLAN.md`,
`STATISTICAL_PHASE_COMPLETION_REPORT.md`), two scripts
(`aggregate_production_results.py`, `build_primary_effects_tables.py`) and one test
file (`tests/test_f1_precision.py`). The aggregate and D2 tables were **not**
regenerated; the evaluator cache, transcripts, frozen inputs, registry and frozen
spec were untouched, and no evaluator call was made.

**Amendment policy.** Changes to this plan after 2026-07-31 must be recorded above as
a numbered amendment, with a date, a reason, and an explicit statement of whether the
change was made before or after the results were inspected.
