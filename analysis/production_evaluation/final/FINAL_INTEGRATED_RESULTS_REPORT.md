# Final integrated results

**Research question.** To what extent does enriching agent profiles with the study's
available metadata improve thematic, interactional and group-level correspondence with
the paired human focus group, relative to agents configured with demographic information
only?

**Design.** 5 focus groups × 3 stochastic replicates × 2 conditions = 30 synthetic
sessions, paired against 5 human transcripts. **FG is the comparative unit: n = 5 paired
groups.** The three replicates per cell estimate *generator variability*; they are not
additional focus groups, and no session is treated as an independent group.

**What this report does not do.** No causal language. No confirmatory p-values. No
conclusion that the enriched condition is superior. Directions, magnitudes, variability
and exceptions only.

Every figure below traces to a source artefact in
[RESULTS_TRACEABILITY_INDEX.md](RESULTS_TRACEABILITY_INDEX.md); all 16 headline figures
reconciled, no contradictions found.

---

## 1. Descriptive findings — thematic correspondence (deductive, 30 runs)

Tier 1 codebook coding, comparable-window namespace, FG-level means of three replicates.

| Metric | Mean difference (enriched − demographics-only) | FGs favouring enriched | Favouring demographics-only | Ties |
|---|---|---|---|---|
| Subtheme recall | **+0.121** | 4 | 1 (FG2) | 0 |
| Matched-theme precision | +0.078 | 2 | 1 (FG2) | 2 |
| Participant reach | +0.118 | 4 | 1 (FG4) | 0 |
| F1 *(secondary)* | +0.150 | 4 | 1 (FG2) | 0 |

The direction favours enriched on recall, reach and F1 in four of five groups. **This is
a description of five paired differences, not a test.** The exploratory two-sided sign
test returns p = 0.375 for recall, reach and F1, and its *minimum attainable* p at n = 5
is 0.0625 — the design cannot reach p < .05 even under a perfect split, and precision
(2 ties, n_effective = 3) cannot go below p = 0.25.

**Within-cell variability is large relative to the between-condition difference.** FG2
enriched has a within-cell SD of 0.218 on recall against a between-condition difference
of −0.048; FG4 enriched 0.193 against +0.278. Replicate-to-replicate spread is of the
same order as, and often larger than, the effect being described.

### Exceptions that matter

- **FG2 reverses on every thematic metric** (recall −0.048, precision −0.083, F1 −0.061).
- **FG4 reverses on reach** (−0.170): demographics-only achieved reach 1.000 in all three
  replicates while enriched averaged 0.830.

---

## 2. Descriptive findings — interactional structure

| Metric | Human | Enriched | Demographics-only | Enriched − demo | FGs where enriched is closer to human |
|---|---|---|---|---|---|
| Total words | 4,689 | 8,277 | 8,817 | −540 | 3/5 |
| Participant turns | 69.2 | 32.1 | 33.5 | −1.3 | 2/5 |
| Words per turn (IQR) | 96.5 | 70.5 | 52.8 | +17.8 | 3/5 |
| Short-turn proportion (<25w) | **0.344** | **0.000** | **0.000** | 0.000 | 0/5 |
| Turn-balance Gini | 0.195 | 0.072 | 0.088 | −0.016 | 2/5 |
| Chain depth | **12.8** | **2.02** | **2.02** | +0.004 | 4/5 |
| Moderator word share | 0.025 | 0.108 | 0.116 | −0.008 | 4/5 |

Both synthetic conditions differ markedly from the human transcripts, and by broadly
similar margins: roughly **1.8× the words in half the turns**, **no short turns at all**
where humans produce 34%, participation far more evenly distributed (Gini 0.07–0.09 vs
0.195), participant-to-participant chains of depth ~2 against 12.8, and four times the
moderator word share.

No consistent or descriptively substantial improvement in interactional structure was
observed under enrichment. Both conditions remained markedly different from the human
groups, while the observed differences between conditions were comparatively small. **This
pattern does not demonstrate equivalence, absence of effect, or an exactly null effect** —
no equivalence test was run and no equivalence margins were predefined.

The `closer to human` counts range from 0/5 to 4/5 across the seven metrics. **These
small-n directional counts do not provide conclusive evidence of a consistent structural
advantage.**

The zero short-turn proportion is the sharpest single descriptive contrast: in these
transcripts, synthetic agents in both conditions produce no brief interjections, while the
human groups produce them frequently.

---

## 3. Exploratory — emergent calibration, U01–U07 / Q3 (human-anchored)

A separate strand. **Not pooled with the deductive results**: different coding paradigm,
different units, different denominators.

| Quantity | Value |
|---|---|
| Human theme × unit instances (denominator) | **44** |
| Thematic categories (distinct cluster ids) | 16 |
| Original coder rows | 76 |
| Machine themes extracted | 30 |
| Recall vs `union_reference` | **30/44 = 0.6818** |
| Strict precision vs `union_reference` | **24/30 = 0.8000** |
| Human uncertainty retained | 6/44 = 0.1364 |
| Literal evidence attachment | 30/30 themes, 58/58 quotations |

Three quantities are deliberately kept apart and must never be conflated: **16 categories**,
**44 theme × unit instances** (the denominator), **76 raw coder rows**.

**Strict precision is conservative by construction.** Machine themes judged valid but not
linked to any human theme remain *outside* the numerator, so 0.8000 understates
correspondence if novelty is credited.

### Literal evidence attachment is not groundedness

`literal_evidence_attachment_rate = 30/30` establishes only that **each machine theme
carries at least one quotation that is verbatim in its own unit and not from the
moderator**. It does **not** establish that the claim the quotation supports is
substantively warranted. Four distinct things are reported separately throughout:

1. **literal evidence attached** — the quote is real and correctly located;
2. **correspondence with the human reference** — recall / precision;
3. **substantive groundedness** — whether the claim is warranted (not established here);
4. **cross-model corroboration** — whether a second model agrees.

---

## 4. Corroborated evidence — cross-model audit

`BLINDED_CROSS_MODEL_LLM_ADJUDICATION`, Claude Opus 5, 38 cases × 2 repetitions = 76
Batch requests, fully blinded (no model name, no condition, no provenance, no aggregate
result, no benchmark, opaque unit labels, sides labelled REFERENCE/CANDIDATE).

**Where the auditor was useful:**

- corroborated **17 of 24** pending cases;
- corroborated `U03::M4` and `U06::M5` as **`VALID_NOVEL_THEME`**;
- classified all three U07 granularity cases as **`SUBSTANTIVE_MISMATCH`** — a stronger
  reading than the provisional pass, which had left them UNCERTAIN;
- corroborated `U04::C09 ↔ U04::M1` as correspondence;
- corroborated `U06::C11 ↔ U06::M3` as non-correspondence at HIGH/HIGH;
- demonstrated that the evidence gate **rejects unverifiable quotations** — including the
  auditor's own.

**Why it is not an arbiter:**

| Reliability signal | Value |
|---|---|
| Exact agreement with the researcher (stable cases) | 6/9 = **0.667** |
| Self-contradiction between repetitions | 5/14 = **0.357** |
| Abstentions | **0** |
| Non-verbatim quotations produced | 8/315 |
| Fabricated or misattributed | **2**, both in `B::U01::M5` |

The judge never once abstained while disagreeing with *itself* on more than a third of
cases the researcher had already settled, and it fabricated the same quotation in both
independent readings of one case. Status:

**`USABLE_FOR_CORROBORATION_ONLY`** — it may corroborate a human-anchored finding; it may
not settle one. This is not evidence of reliability sufficient for autonomous
adjudication.

---

## 5. Unresolved uncertainty (retained, not resolved)

**`BPLUS_STATUS = PENDING_LIMITED_REVIEW`**
**Final disposition: `CLOSED_WITH_UNRESOLVED_CASES_NO_FURTHER_HUMAN_ADJUDICATION`**

Seven cross-model cases and six human UNCERTAIN rows are retained individually with their
reason for uncertainty. They are **not** converted into matches, errors or valid themes,
and enter **no** confirmed numerator. No PASS and no FAIL is declared.

The study chose to preserve this uncertainty rather than continue an adjudication chain
incompatible with its efficiency objective. Two B+ conditions — complete human
adjudication of every machine-only theme, and explicit human review of fragmentation and
fusion — were not met, and a second model's opinion cannot substitute for either.

Five of the seven unresolved cases are unresolved *because the auditor's own quotation
failed verification*, which is the gate behaving correctly rather than a property of the
extractor.

---

## 6. Supplementary transportability, S01–S06 — never pooled

Six units, one coder, 18 themes, questions Q1/Q2/Q4/Q5.
`CONSOLIDATION_NOT_REQUIRED — CODER_ROWS_ALREADY_DISTINCT`. Relevance `NOT_ASSESSED` by
methodological decision.

This sample is **never combined numerically with U01–U07/Q3** — different questions,
different design, different denominators, single coder, no inter-coder agreement — and
never with the deductive results or the enriched vs demographics-only comparison.

### 6.1 `EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK`

An automatic extraction and a blinded cross-model adjudication were subsequently run on
this sample. It is an **exploratory check, not a validation**, and its denominators are
never pooled with any other strand in this report.

18 human themes against 30 candidate themes. **All 93 within-unit human × candidate pairs
were adjudicated** — 61 in the original run, 32 in a later complementary audit that closed
a screening gap (see `PROTOCOL_DEVIATIONS.md`). Outcomes: 19 confirmed matches, 60
confirmed non-correspondences, 14 unresolved.

| Figure | Value |
|---|---|
| Recall (confirmed) | **16/18 = 0.8889** |
| Strict confirmed precision — *primary estimate* | **18/30 = 0.6000** |
| Possible precision upper bound | 23/30 = 0.7667 |
| Adjusted precision — *optimistic exploratory ceiling* | 29/30 = 0.9667 |
| Literal evidence attachment | 30/30 = 1.0000 |

The extractor recovered **16 of 18** human themes. The two it did not — `S01::S01_slot_02`
and `S06::S06_slot_03` — were each adjudicated against **every** candidate in their own
unit, and every pair returned a confirmed non-correspondence; their absence is a measured
result, not a gap in the adjudication.

**Five candidate themes hold a correspondence that remains uncertain**, which is why
precision is reported as the interval [0.6000, 0.7667] rather than a point. A further
**11 candidates were corroborated by Claude as novel themes** — but that is **automated
corroboration, not human validation**; no researcher adjudicated them, and a single coder
working to a defined scope is entitled to leave material uncoded. The adjusted figure of
0.9667 is therefore an **optimistic exploratory ceiling, not the headline estimate**. The
headline precision estimate is **0.6000**.

**Q2 was the cleanest case** (4 human themes, 5 candidates, recall 1.0000, precision
1.0000, nothing unresolved). **Q4 showed the greatest thematic proliferation** (11
candidates against 4 human themes, precision 0.5455, 5 corroborated novel themes). Per-
question rows rest on 3–6 human themes each and are **not** compared statistically.

Two conclusions are reported together, and neither stands alone:

- `FROZEN_RULE_CLASSIFICATION = DESCRIPTIVELY_COMPATIBLE_WITH_Q3` — the rule was fixed
  before any result existed and keys on **recall only**. It was not retrofitted.
- `BALANCED_INTERPRETATION = Recall-compatible with Q3 under the frozen rule, but with
  lower strict precision and greater thematic proliferation; evidence of transportability
  is mixed across fidelity dimensions.`

**This does not demonstrate equivalence and does not establish transportability.** Both
ends of the precision interval sit below the Q3 landmark of 0.8000. Full results,
per-question tables and the complete pair-level record are in
`transportability_sample/hybrid_evaluation/`.

---

## 7. Qualitative finding — FG4 demographics-only

FG4 demographics-only returns recall 0.000, precision 0.000 and F1 0.000 in **all three**
replicates, while simultaneously returning **reach 1.000** in all three.

FG4 demographics-only presents a result that is **highly sensitive to coding granularity**:
zero overlap at subtheme level across the three replicates, but partial correspondence at
the broader theme level (recall 0.25–0.50, precision 1.00 in the same runs). This
demonstrates dependence on the operational level of the codebook; **it does not establish
that granularity causally produced the result**. Any reading of FG4 as "the condition
produced nothing" is not supported by the theme-level figures.

FG4 is retained in the primary analysis. A targeted blinded human coding review of this cell
has since been completed; its verdict enters the results as a sensitivity analysis
and does not change the primary coding.

---

## 8. Operational limitations

- **Evaluator.** `gemini-3.5-flash` refused synchronous serving three times (503) and
  served every input via Batch. The model was never substituted. It was validated for
  Tier 1 deductive coding; that validation **does not transfer** to open inductive
  extraction, which is what §3 measures.
- **Forced silences.** The zero short-turn proportion means synthetic sessions never
  contain the brief interjections, partial agreements and interrupted turns that make up
  a third of human turns. Content the design could not elicit is recorded as a structural
  absence, not read as evidence of absence.
- **Batch vs synchronous.** All reported evaluator results are Batch. Batch and
  synchronous outputs are never mixed.
- **Deferred diagnostics.** `tier1_coverage_by_word_count_curve` has a producer but was
  not run; `tier1_length_matched_*` remain `DEFERRED_NOT_IMPLEMENTED`. The
  `evidence_localized_*` results are secondary/exploratory evidence-localisation
  diagnostics, not recoding.
- **Cost.** The cross-model audit consumed 338,638 input and 75,551 output tokens =
  **$1.79 calculated at the published list Batch rate** (pre-run estimate was $1.22; the
  estimate was low by 32% of actual). This is a calculated list-rate figure, not
  necessarily the amount charged.
- **Cost, exploratory transportability check (§6.1), recorded separately.** Three Claude
  Batch jobs consumed 1,014,065 input and 165,352 output tokens = **$4.60 calculated at
  the same list Batch rate**. The Gemini extraction cost is **not calculated**: no
  published Batch rate for that model was verified, and an unsourced rate would be worse
  than none. Both figures are calculated, not invoices; the Console is authoritative.

---

## 9. Claims the design does not support

- That the enriched condition **is** superior. Four-of-five directional agreement at
  n = 5, with within-cell SD of the same order as the effect, does not support it.
- Any **causal** statement about why enrichment changes thematic correspondence.
- That enrichment improves **interactional realism**. No consistent or descriptively
  substantial improvement was observed. Equally unsupported is the converse claim that
  enrichment has no structural effect: no equivalence test was run and no equivalence
  margins were predefined, so neither direction is established.
- That the emergent extractor is **validated**. Its status is `PENDING_LIMITED_REVIEW`
  with unresolved cases retained.
- That **substantive groundedness** was measured. Only literal evidence attachment was.
- That the Q3 calibration **transports** to other guide questions. The exploratory check
  on S01–S06 (§6.1) is recall-compatible with Q3 under a pre-frozen recall-only rule, but
  strict precision is lower at both ends of its interval and the evidence is mixed across
  fidelity dimensions. It is single-coder, descriptive, never numerically combined, and
  **not a validation**. Neither equivalence nor established transportability follows.
- That the 11 candidates corroborated as **novel** in §6.1 represent themes the human
  coder missed. They were corroborated by an LLM, not adjudicated by a researcher.
- That any finding generalises **beyond U01–U07/Q3** for the emergent strand, or beyond
  these five paired groups for the deductive strand.

---

## 10. Summary of integrated findings

1. **Thematic correspondence leans toward enriched** — +0.121 recall, +0.118 reach,
   +0.150 F1, four of five groups — but the design cannot test it and replicate
   variability rivals the effect.
2. **No consistent or descriptively substantial improvement in interactional structure was
   observed under enrichment.** Both conditions remained markedly different from the human
   groups, while the observed differences between conditions were comparatively small.
   This pattern does not demonstrate equivalence, absence of effect, or an exactly null
   effect.
3. **Thematic correspondence descriptively favoured enrichment in most FGs, whereas no
   comparable consistent improvement was observed in the structural metrics. This is a
   descriptive divergence between fidelity dimensions, not proof that enrichment affects
   one dimension and has no effect on the other.**
4. **The emergent extractor reaches 0.6818 recall** against a 44-instance human reference,
   above the 0.6364 coverage benchmark, with conservative 0.8000 strict precision — but
   is not validated, and closes with uncertainty retained.
5. **FG4 demographics-only is highly sensitive to coding granularity** — zero overlap at
   subtheme level, partial correspondence at theme level. It shows dependence on the
   operational level of the codebook, not that granularity causally produced the result.

---

<!-- BEGIN GENERATED: cross-model audit and human coding review -->

## Cross-model absence audit, salience sensitivity and human coding review

### Hierarchy of evidence

| Layer | Analysis | Status |
|---|---|---|
| **1 · PRIMARY** | `ORIGINAL_GEMINI` / `ORIGINAL_LOWER` | the reported result |
| **2 · CROSS-MODEL SENSITIVITY** | 16 `ABSENCE_CONTESTED` cells under MID/UPPER and `CONTESTED_AS_PRESENT` | sensitivity input |
| **3 · HUMAN-CODING SENSITIVITY** | `OCA_REMOVE_A1_ONLY` — the explicit A.1 verdict | sensitivity input |
| **4 · EXPLORATORY VARIANT** | `OCA_REMOVE_A1_ADD_PROPOSED_A3` — the proposed alternative | exploratory only |

These layers are **never pooled**, and no sensitivity result is presented as corrected ground truth. The three strands of evidence — the Gemini primary coding, the blinded cross-model audit and the targeted blinded human coding review — are reported separately throughout.

### Absence audit — all 260 Gemini absence decisions

| Outcome | n |
|---|---:|
| `AUDITOR_DID_NOT_FIND_EVIDENCE` | 180 |
| `ABSENCE_UNRESOLVED` | 64 |
| `ABSENCE_CONTESTED` | 16 |
| `ABSENCE_CORROBORATED` | **0** |

Concurrence control: **121 of 125** originally-present cells concurred, with **0** flatly contradicted. Repetition agreement **349/385**. Evidence-gate failures **2/770** assessments.

**`AUDITOR_DID_NOT_FIND_EVIDENCE` records only that the auditor searched and reported nothing.** It is never a confirmed absence and is not paraphrased as one. Contested cells are sensitivity inputs; none was recoded.

### Thematic-salience sensitivity

| Treatment | tau-b defined | Changed vs primary |
|---|---:|---:|
| ORIGINAL / LOWER (**primary**) | 27/30 | — |
| MID | 30/30 | 15 |
| UPPER | 30/30 | 15 |

The three FG4 demographics-only runs move from undefined (`SYNTHETIC_SIDE_CONSTANT`) to **defined and negative**. The "6 undefined → defined" figure is **three runs under two sensitivity treatments, not six distinct runs.** There are 0 transitions in the other direction.

MID and UPPER differ in **one** run only. Movements occur in **both directions**, so the sensitivity does not uniformly favour either condition. The 64 unresolved cells **enter no treatment**.

### Targeted blinded human coding review

A targeted blinded human coding review of **FG4 demographics-only run01**, subtheme **A.1**, returned the verdict **`DOES_NOT_SUPPORT_A1`** with **A.3** proposed as the better fit. Reviewer LCLP, 2026-08-03. **The review is complete and its verdict is recorded**; it is carried into the results as a sensitivity analysis, not as a change to the primary coding.

**Removing A.1 is the explicit human verdict.** **Adding A.3 is exploratory**, because the form did not explicitly adjudicate A.3 as present. The A.3 reach of 3/3 is **inferred** from the three cited turns and is **not human-validated reach**.

| Layer | Variant | Recall | Precision | F1 |
|---|---|---|---|---|
| 1 · primary | `ORIGINAL_GEMINI` | 0.0 | 0.0 | **0.0** |
| 3 · human-coding sensitivity | `OCA_REMOVE_A1_ONLY` | 0.0 | **undefined** | **undefined** |
| 4 · exploratory | `OCA_REMOVE_A1_ADD_PROPOSED_A3` | 0.0 | 0.0 | **0.0** |

A complete mismatch between two non-empty code sets is a **measured zero**, so F1 is 0.0 in layers 1 and 4. Under layer 3 the synthetic side asserts nothing, the precision denominator is empty, and precision and F1 are **undefined** — the only place a blank is correct.

**Defined and undefined denominators, reported separately** — FG4 demographics-only:

| Variant | Precision defined | Precision undefined | F1 defined | F1 undefined |
|---|---:|---:|---:|---:|
| `ORIGINAL_GEMINI` | 3 | 0 | 3 | 0 |
| `OCA_REMOVE_A1_ONLY` | 2 | 1 | 2 | 1 |

No condition-level or FG-level mean moves; the denominator behind the FG4 demographics-only mean drops from 3 to 2 and is printed rather than absorbed.

### Combined sensitivity: A.1 → A.3 reclassification

For FG4 demographics-only R1 the combined treatment applies the reclassification the targeted blinded human coding review adjudicated: **A.1 removed, A.3 added**. It is a sensitivity analysis derived from independent human review, **not a modification of the primary deductive result**.

| Subtheme | ORIGINAL | CROSS-MODEL | COMBINED |
|---|---:|---:|---:|
| A.1 | 5 | 5 | **4** |
| A.3 | 2 | 3 | **3** |

**Counts are distinct focus groups.** The blinded auditor contested A.3 in this same run, and the human review proposes A.3 for it as well — the two independent reviews **converge on one focus group**, which is therefore counted **once**. A.3 accordingly moves 2 → 3, not 2 → 4; A.1 moves 5 → 4. Across the table, **15** recurrence rows change under the combined treatment.

### Required wording

> Gemini remained the primary deductive evaluator. A blinded cross-model audit using Claude identified transcript-grounded evidence contesting 16 of 260 Gemini-coded absences. Because the auditor met only the pre-specified detection-only gate, its non-detections were not treated as corroborated absences. The original Gemini coding therefore remained primary, and contested cells were examined only through sensitivity analyses.

> A targeted blinded human coding review judged that FG4 demographics-only run01 did not support A.1. Removing A.1 left the run with no verified deductive code, rendering precision and F1 undefined for that run. Adding the reviewer-proposed A.3 was examined separately as an exploratory variant because the form did not explicitly adjudicate A.3 presence.

### Figures

| Role | Figure |
|---|---|
| **Primary** | `salience_recurrence_heatmap.png` — original Gemini-coded across-group recurrence. **Not replaced.** |
| **Combined sensitivity** | `analysis/figures/thematic_salience_sensitivity_heatmap.png` — cross-model contested-as-present **and** the A.1 → A.3 reclassification |
| Component view | `figures/recurrence_sensitivity_three_panel.png` — the cross-model strand alone; it is **not** the final combined sensitivity |

*Caption.* Salience here is **LLM-coded participant breadth and across-group recurrence**. It is **not** mention frequency and **not** human-validated interpretive centrality. The combined sensitivity figure incorporates the targeted blinded human coding review; the three-panel component figure does not.

---

<!-- END GENERATED: cross-model audit and human coding review -->
