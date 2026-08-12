# OCA-001 integration and final salience sensitivity products

**Nothing has been overwritten.** `evaluator_cache/` is untouched, the Gemini results CSVs
are unchanged, `FINAL_RESULTS_TABLES.xlsx`, the existing heatmap and the dissertation
drafts are not modified. The original analysis remains **primary** throughout.

Two sensitivity families are reported here and are **deliberately kept apart**:

| Family | Source | Status |
|---|---|---|
| **OCA** | one human reviewer's adjudication of a single item | `POST_RESULT_HUMAN_ADJUDICATED_SENSITIVITY` |
| **Cross-model** | the blinded absence audit, 16 contested cells | `CROSS_MODEL_SALIENCE_SENSITIVITY` |

They are never combined: one is a human judgement about one code in one run, the other is
a model-derived treatment across the corpus. The three-panel figure carries the
cross-model family only.

---

## 1. OCA-001 imported read-only

| Field | Value |
|---|---|
| Item | **OCA-001** |
| Verdict | **`DOES_NOT_SUPPORT_A1`** |
| Alternative subtheme | **A.3** |
| Reviewer | **LCLP** |
| Date (UTC) | **2026-08-03** |
| Workbook SHA-256 | `67ca18116b39a4af0976d17250a4efddf815928e2575047cbe3b770f4ef902d2` |
| Workbook bytes | 13,102 |
| Import mode | **READ_ONLY** — the workbook was opened and never written |

**Reasoning, as recorded:** the reviewer judged the passage "more accurate to say … a
subtopic of A.3", noting that the gender link is "touched on briefly but not in detail",
that the conversation later shifts to "topics that are highly dependent on gender and
traditional roles", but that "the participants don't directly point out the link to
gender; rather, they discuss how they are more removed from day-to-day food-related
decisions."

### Integrity against the sealed source

**10 immutable/blinded elements checked, all matching.** Each of the 6 presented turns
verified by SHA-256 against `presented_sha256` in
`gold_standard_sealed/open_coding_item_mapping.json` (sealed 2026-07-31), plus the A.1 and
A.3 labels and definitions against the frozen codebook. The cited-turn count matches.

### Mapping, applied only after import

```
OCA-001  ->  FG4-DEMO-R01-A1  ->  macho_meals_fg4_demoonly_run01
             fg4 · demographics-only · synthetic · replicate 1 · subtheme A.1
             turns shown  T020 T021 T022 T023 T026 T027
             turns cited  T021 T023 T027
```

The import step attaches no provenance; the blinded record is read first and mapped
afterwards.

---

## 2. The distinction that must not collapse

| | A.1 removal | A.3 |
|---|---|---|
| Status | **explicit human verdict** | **reviewer-proposed alternative** |
| Warrant | the form asked exactly this question | **none from the form** |
| Effect | `present=False` in both OCA variants | `present=True` in the third variant **only** |

**The form never asked whether A.3 should be set `present=true`.** It showed A.3 only so
the A.1/A.3 boundary was visible. Proposing A.3 as the better fit is not the same act as
adjudicating it present, so A.3 is never promoted automatically — it exists as its own
variant precisely so the difference stays visible.

The reach assigned to a proposed A.3 (3/3 = 1.0) is **inferred** from the three cited
turns, one per participant. The form did not ask for reach either.

---

## 3. Three deductive variants — the affected run

`macho_meals_fg4_demoonly_run01`. Human FG4 present set: **A.2, B.3, B.4, C.1, C.3, D**
(n = 6). Note that **A.1 was never in the human set**, so it contributed to precision but
never to recall.

| Variant | Synthetic present set | Shared | Recall | Precision | F1 (secondary) |
|---|---|---:|---:|---|---|
| `ORIGINAL_GEMINI` | {A.1} | 0/6 | 0.0 | 0.0 | **0.0** |
| `OCA_REMOVE_A1_ONLY` | **∅** | 0/6 | 0.0 | **UNDEFINED** | **undefined** |
| `OCA_REMOVE_A1_ADD_PROPOSED_A3` | {A.3} | 0/6 | 0.0 | 0.0 | **0.0** |

### The F1 rule, and a defect corrected

> **F1 is undefined ONLY when recall or precision is undefined.** If both are measured and
> both equal 0, **F1 = 0.0**. A complete mismatch between two non-empty code sets is a
> **measured zero, not missingness**.

An earlier version of this integration returned an undefined F1 whenever
`recall + precision == 0`. That contradicted the rule and, more seriously, contradicted the
frozen source table, which records `tier1_f1_secondary = 0.0` for exactly these runs. The
implementation was fixed at source and every OCA product regenerated.

The distinction is substantive. Under `ORIGINAL_GEMINI` and under the proposed-A.3 variant
both sides assert codes and none of them agree — a real, total mismatch, and reporting it
as a blank would hide the very result that makes this cell interesting. Under
`OCA_REMOVE_A1_ONLY` the synthetic side asserts **nothing**, so precision is `0/0` and F1
inherits that undefinedness. Only there is a blank correct.

A source-fidelity check now runs inside the pipeline: all **90** ORIGINAL_GEMINI values
(30 runs × recall, precision, F1) are compared against `results/per_run_metrics.csv` and
the build aborts on any mismatch. It currently passes exactly.

Recall is unchanged at 0.0 throughout: neither A.1 nor A.3 is in human FG4's set, so
removing one and adding the other cannot create an overlap.

**Reach:** A.1 3/3 = 1.0 → removed → A.3 3/3 = 1.0 (inferred).

---

## 4. FG4 zero-overlap interpretation

The original flag `ZERO_OVERLAP_NOT_ZERO_CODING` says explicitly that this is *"not 'the
synthetic groups produced no themes'"*. That wording is variant-dependent:

| Variant | Reading |
|---|---|
| `ORIGINAL_GEMINI` | `ZERO_OVERLAP_NOT_ZERO_CODING` — codes were asserted, none overlap |
| `OCA_REMOVE_A1_ONLY` | **MIXED** — 1 of 3 replicates now asserts **no verified code at all**, so for that replicate the flag's wording *"codes WERE asserted"* no longer holds |
| `OCA_REMOVE_A1_ADD_PROPOSED_A3` | `ZERO_OVERLAP_NOT_ZERO_CODING` — unchanged |

This is the one place where the human verdict materially changes an interpretation rather
than a number. **`fg4_demoonly_zero_overlap_flag.json` has not been modified.**

---

## 5. Downstream aggregation

Every mean is reported **with the number of defined values behind it**. A mean over 2 of 3
runs and a mean over 3 of 3 are different quantities.

| Variant | Condition | Mean recall (n FGs) | Mean precision (n FGs) | Mean F1 (n FGs) | Undefined runs |
|---|---|---|---|---|---|
| `ORIGINAL_GEMINI` | demographics-only | 0.2695 (5/5) | 0.7100 (5/5) | 0.3579 (5/5) | prec 0, F1 0 |
| | enriched | 0.3906 (5/5) | 0.7878 (5/5) | 0.5074 (5/5) | prec 0, F1 0 |
| `OCA_REMOVE_A1_ONLY` | demographics-only | 0.2695 (5/5) | 0.7100 (5/5) | 0.3579 (5/5) | **prec 1, F1 1** |
| | enriched | 0.3906 (5/5) | 0.7878 (5/5) | 0.5074 (5/5) | prec 0, F1 0 |
| `OCA_REMOVE_A1_ADD_PROPOSED_A3` | demographics-only | 0.2695 (5/5) | 0.7100 (5/5) | 0.3579 (5/5) | prec 0, F1 0 |
| | enriched | 0.3906 (5/5) | 0.7878 (5/5) | 0.5074 (5/5) | prec 0, F1 0 |

Unit of analysis: **focus group, n = 5** — never 15 sessions. The condition-level means are
over focus groups with a defined value; undefined **run** counts are reported separately
rather than folded in.

**No condition-level or FG-level mean moves.** At the FG4 demographics-only cell,
`ORIGINAL_GEMINI` has 3 of 3 defined precision and F1 values, all 0.0;
`OCA_REMOVE_A1_ONLY` has 2 of 3, also both 0.0. The mean stays 0.0 and the denominator
drops from 3 to 2 — which is why the defined n is printed rather than absorbed.

**Salience is unaffected by OCA.** Neither A.1 nor A.3 is in human FG4's universe, so the
primary participant-breadth hierarchy for that cell is all zeros under every variant and
its tau-b stays undefined (`SYNTHETIC_SIDE_CONSTANT`).

---

## 6. Cross-model salience sensitivity — all 30 tau-b under each treatment

**`ORIGINAL_LOWER` is primary and unmodified.** 16 contested cells applied under MID and
UPPER; the **64 unresolved cells enter no treatment in either direction**.

| Treatment | Defined tau-b | Changed vs primary |
|---|---:|---:|
| ORIGINAL / LOWER | **27/30** | — |
| MID | **30/30** | 15 |
| UPPER | **30/30** | 15 |

### Definedness transitions

**6 undefined → defined. 0 defined → undefined.**

| FG | Condition | Rep | Treatment | Was | Becomes |
|---|---|---|---|---|---|
| fg4 | demographics-only | R1 | MID / UPPER | `SYNTHETIC_SIDE_CONSTANT` | **−0.5941** |
| fg4 | demographics-only | R2 | MID / UPPER | `SYNTHETIC_SIDE_CONSTANT` | **−0.2194** |
| fg4 | demographics-only | R3 | MID / UPPER | `SYNTHETIC_SIDE_CONSTANT` | **−0.2194** |

All three previously-undefined cells become defined and **negative**. Under the primary
result these runs produced no variation in reach across the human themes; giving a
contested cell a non-zero reach creates a hierarchy, and it runs opposite to the human one.

### The 15 values that move

| FG | Condition | Rep | ORIGINAL/LOWER | MID | UPPER |
|---|---|---|---:|---:|---:|
| fg1 | demographics-only | R1 | +0.1345 | +0.0387 | +0.0387 |
| fg1 | demographics-only | R2 | 0.0000 | +0.2069 | +0.2069 |
| fg1 | demographics-only | R3 | +0.1345 | +0.2702 | +0.2702 |
| fg1 | enriched | R1 | −0.2941 | −0.1724 | −0.1724 |
| fg1 | enriched | R2 | −0.1765 | +0.1034 | **+0.1429** |
| fg1 | enriched | R3 | −0.2941 | −0.0387 | −0.0387 |
| fg2 | demographics-only | R2 | −0.1925 | −0.4975 | −0.4975 |
| fg2 | enriched | R3 | −0.1925 | −0.2843 | −0.2843 |
| fg3 | enriched | R3 | +0.3916 | +0.1977 | +0.1977 |
| fg4 | demographics-only | R1 | undefined | −0.5941 | −0.5941 |
| fg4 | demographics-only | R2 | undefined | −0.2194 | −0.2194 |
| fg4 | demographics-only | R3 | undefined | −0.2194 | −0.2194 |
| fg4 | enriched | R1 | −0.2697 | −0.5850 | −0.5850 |
| fg4 | enriched | R2 | +0.1818 | −0.1819 | −0.1819 |
| fg4 | enriched | R3 | −0.2697 | −0.5369 | −0.5369 |

**MID and UPPER agree in 14 of 15**; only `fg1 enriched R2` separates them (+0.1034 vs
+0.1429), the one run where the two repetitions localised different speakers.

### 17 exposed, 15 changed — and why the gap matters

The complete-audit report listed **17** runs as exposed. **15** actually move. The two that
do not are `fg5 enriched R1` and `R2`, whose contested cell is **A.2** — and A.2 is **not
in human fg5's present set** (`A.1, B.2, B.3, B.4, C.3`). The primary universe is the human
FG's themes, so a contested synthetic code outside that universe cannot change the primary
tau-b. Exposure is not the same as change, and reporting only exposure would have
overstated the sensitivity.

**Direction:** movements go both ways — 6 up, 9 down — and the largest are negative. This
is not a treatment that uniformly flatters either condition.

---

## 7. Recurrence sensitivity and the three-panel figure

`ORIGINAL` vs `CONTESTED_AS_PRESENT`, **14 rows change** (§4 of the complete audit report).
There is no MID treatment: a focus group either counts or it does not.

The figure is written to a **new** file, `recurrence_sensitivity_three_panel.png`. The
existing `salience_recurrence_heatmap.png` is **not replaced**.

| Panel | Contents |
|---|---|
| **A** | Original Gemini-coded recurrence — the primary coding, unchanged |
| **B** | Cross-model `CONTESTED_AS_PRESENT` sensitivity |
| **C** | Difference (B − A): added focus-group counts |

The figure carries its own caption stating that it is a sensitivity, not a result, that
unresolved cells enter no treatment, and that **the OCA human adjudication is not applied
in it**.

---

## 8. What has and has not been touched

**Correction applied before integration:** the F1 rule above was fixed at source in
`scripts/oca_integration.py` and `oca_integration.json`, `oca_variants_per_run.csv` and
this report were regenerated. All Kendall tau-b values and the recurrence sensitivity are
unaffected and verified unchanged (§6, §7) — the defect was confined to the OCA F1 column.

**Written (all new files):**
`open_coding_adjudication/oca_integration.json`, `oca_variants_per_run.csv`,
`salience_absence_audit/salience_sensitivity_final.json`,
`kendall_tau_b_by_treatment.csv`, `tau_b_definedness_transitions.csv`,
`recurrence_sensitivity_three_panel.png`, this report.

**Not touched:** `evaluator_cache/`, `OCA-001_adjudication.xlsx`,
`open_coding_item_mapping.json`, `thematic_code_presence_long.csv`,
`thematic_reach_long.csv`, `per_run_metrics.csv`, `fg4_demoonly_zero_overlap_flag.json`,
`salience_hierarchy.json`, `salience_recurrence_heatmap.png`,
`FINAL_RESULTS_TABLES.xlsx`.

---

**Stopped before modifying `FINAL_RESULTS_TABLES.xlsx`.**
`ORIGINAL_GEMINI` and `ORIGINAL/LOWER` remain the primary results.
