# Blinded cross-model absence audit — complete results

**Stage 1** `msgbatch_01GjsFCpq5CULdhcdMzN6Ti1` (28 requests) ·
**Stage 2** `msgbatch_01HyNAhx8ESA2eitjtmmL5GB` (42 requests)
70/70 requests succeeded, 0 errored, every response `end_turn`, 0 invalid.

> ## Band B — `PROCEED_DETECTION_ONLY`
> **`ABSENCE_CORROBORATED` is forbidden globally**, regardless of subtheme control
> eligibility. All 11 subtheme controls passed, and it changes nothing: the global band
> governs.

**Nothing has been integrated.** The Gemini coding is unchanged, no absence was converted
into a presence, and the final heatmap and workbook are untouched.
**ORIGINAL / LOWER remains the primary thematic-salience result.**

---

## 1. Coverage

| | |
|---|---|
| Documents | **35** (14 Stage 1 + 21 Stage 2) |
| Requests | **70** = 35 × 2 separately keyed repetitions |
| Cells reconciled | **385** = 35 × 11 |
| Absence decisions audited | **260** |
| Originally-present concurrence controls | **125** |
| Invalid responses | **0** |
| Cache-key collisions | **0** |

Configuration identical across both stages: `claude-opus-5`, Batch API, `effort=high`,
`max_output_tokens=8192` (frozen prospectively, not retuned on Stage-1 results), frozen
prompt and JSON schema, no temperature/top_p/top_k, no model substitution, no synchronous
fallback, retrieval by `custom_id` only.

---

## 2. The complete 260-cell absence audit

| Label | n | % |
|---|---:|---:|
| `AUDITOR_DID_NOT_FIND_EVIDENCE` | **180** | 69.2% |
| `ABSENCE_UNRESOLVED` | **64** | 24.6% |
| `ABSENCE_CONTESTED` | **16** | 6.2% |
| `ABSENCE_CORROBORATED` | **0** | forbidden under Band B |

The 180 are the cells where the auditor searched and reported nothing. Under Band B that
is **all they say** — it is not corroboration, and the label was made unreachable in code
rather than filtered out afterwards.

**16 contested absences** carry gate-passed evidence in both repetitions. They are
verified against the transcript, not against the auditor, so they stand regardless of the
band. **They have not been converted into presences.**

### Concurrence control — the 125 originally-present cells

| | n |
|---|---:|
| `PRESENCE_CONCURRED` | **121** (96.8%) |
| `PRESENCE_UNRESOLVED` | 4 |
| `PRESENCE_NOT_CONCURRED` | **0** |

**Not one originally-present cell was flatly contradicted.** Repetition agreement across
all 385 cells: **349/385 (90.6%)**. Quotation-gate failures: **2 of 770 assessments**,
both `UNCERTAIN_QUOTATION_NOT_IN_NAMED_TURN`, neither repaired nor relocated.

---

## 3. Sensitivity 1 — `participant_breadth_bounds`

**Primary treatment: LOWER. The reported hierarchy does not move.**

All 16 contested cells, with MID = 1/n and UPPER = deduplicated union of gate-passed
speakers across both repetitions:

| Document | Code | n | LOWER | MID | UPPER |
|---|---|---:|---:|---:|---:|
| `human::fg1` | A.3 | 5 | 0.0 | 0.2000 | 0.2000 |
| `human::fg1` | D | 5 | 0.0 | 0.2000 | 0.2000 |
| `human::fg4` | A.1 | 3 | 0.0 | 0.3333 | 0.3333 |
| `macho_meals_fg1_run01` | D | 5 | 0.0 | 0.2000 | 0.2000 |
| `macho_meals_fg1_run02` | A.2 | 5 | 0.0 | 0.2000 | **0.4000** |
| `macho_meals_fg2_run03` | B.4 | 5 | 0.0 | 0.2000 | 0.2000 |
| `macho_meals_fg3_run03` | A.2 | 5 | 0.0 | 0.2000 | 0.2000 |
| `macho_meals_fg4_run04` | A.3 | 3 | 0.0 | 0.3333 | 0.3333 |
| `macho_meals_fg5_run01` | A.2 | 4 | 0.0 | 0.2500 | 0.2500 |
| `macho_meals_fg5_run03` | A.2 | 4 | 0.0 | 0.2500 | **0.5000** |
| `macho_meals_fg1_demoonly_run01` | D | 5 | 0.0 | 0.2000 | 0.2000 |
| `macho_meals_fg2_demoonly_run02` | D | 5 | 0.0 | 0.2000 | 0.2000 |
| `macho_meals_fg4_demoonly_run01` | A.3 | 3 | 0.0 | 0.3333 | 0.3333 |
| `macho_meals_fg4_demoonly_run01` | B.2 | 3 | 0.0 | 0.3333 | 0.3333 |
| `macho_meals_fg4_demoonly_run02` | D | 3 | 0.0 | 0.3333 | 0.3333 |
| `macho_meals_fg4_demoonly_run03` | D | 3 | 0.0 | 0.3333 | 0.3333 |

MID equals UPPER in 14 of 16: both repetitions cited the same single participant. Only two
cells widen, where the two repetitions localised different speakers. **The 64 unresolved
cells enter no bound.**

### The part that needs attention: 3 contested cells are on human documents

`human::fg1` A.3, `human::fg1` D and `human::fg4` A.1 are contested **on the human side**.
Those are not synthetic omissions — they are cells where the auditor found participant
evidence in a *human* transcript that the original coding recorded as absent.

This matters more than the synthetic cells, because **the human FG is the reference
universe of the salience hierarchy**. If a human theme is added, every synthetic run paired
with that FG is re-scored against a larger universe. That is why fg1 and fg4 dominate the
affected list below.

---

## 4. Sensitivity 2 — `across_group_recurrence_sensitivity`

**Primary treatment: ORIGINAL.** No MID exists here: a focus group either counts or it does
not.

**14 recurrence rows would change** under `CONTESTED_AS_PRESENT`:

| Condition | Rep | Code | ORIGINAL → CONTESTED_AS_PRESENT |
|---|---|---|---|
| human | — | A.1 | 3 → 4 |
| human | — | A.3 | 2 → 3 |
| human | — | D | 3 → 4 |
| enriched | R1 | A.2 | 0 → 1 |
| enriched | R1 | D | 1 → 2 |
| enriched | R2 | A.2 | 2 → 4 |
| enriched | R2 | A.3 | 1 → 2 |
| enriched | R3 | A.2 | 0 → 1 |
| enriched | R3 | B.4 | 3 → 4 |
| demographics-only | R1 | A.3 | 2 → 3 |
| demographics-only | R1 | B.2 | 3 → 4 |
| demographics-only | R1 | D | 1 → 2 |
| demographics-only | R2 | D | 0 → 2 |
| demographics-only | R3 | D | 0 → 1 |

**D and A.2 are where this concentrates.** D moves from 0 to 2 groups in demographics-only
R2 and 0 to 1 in R3; A.2 moves off zero in enriched R1 and R3. Codes recorded as recurring
in no group would recur in one or two. Both conditions move, and neither is systematically
favoured.

---

## 5. Exactly which salience cells and tau-b values would change

**16 salience cells** — the 16 contested cells listed in §3, each moving from a scored 0
under LOWER to a non-zero reach under MID/UPPER.

**17 of 30 Kendall tau-b values** would change; **13 would not**:

| FG | Condition | Rep | tau-b (ORIGINAL/LOWER) | Synthetic-side | Human-side |
|---|---|---|---|---|---|
| fg1 | enriched | R1 | −0.2941 | D | A.3, D |
| fg1 | enriched | R2 | −0.1765 | A.2 | A.3, D |
| fg1 | enriched | R3 | −0.2941 | — | A.3, D |
| fg1 | demographics-only | R1 | 0.1345 | D | A.3, D |
| fg1 | demographics-only | R2 | 0.0000 | — | A.3, D |
| fg1 | demographics-only | R3 | 0.1345 | — | A.3, D |
| fg2 | enriched | R3 | −0.1925 | B.4 | — |
| fg2 | demographics-only | R2 | −0.1925 | D | — |
| fg3 | enriched | R3 | 0.3916 | A.2 | — |
| fg4 | enriched | R1 | −0.2697 | — | A.1 |
| fg4 | enriched | R2 | 0.1818 | A.3 | A.1 |
| fg4 | enriched | R3 | −0.2697 | — | A.1 |
| fg4 | demographics-only | R1 | **undefined** | A.3, B.2 | A.1 |
| fg4 | demographics-only | R2 | **undefined** | D | A.1 |
| fg4 | demographics-only | R3 | **undefined** | D | A.1 |
| fg5 | enriched | R1 | 0.1361 | A.2 | — |
| fg5 | enriched | R2 | 0.4330 | A.2 | — |

All 12 fg1 and fg4 runs appear because their **human** reference universe would grow.
The three `fg4 demographics-only` cells are currently **undefined**
(`SYNTHETIC_SIDE_CONSTANT`) — adding a non-zero synthetic reach could make them defined,
which would change the count of defined runs, not just its value.

**A correction found while producing this table.** My first version reported only 12
affected runs. `per_run` carries no `physical_run` column, so the synthetic-side join
silently matched nothing and only human-side effects were captured. Joined properly
through (condition, fg, replication index), the figure is 17.

**No tau-b has been recomputed.** This table states which values are *exposed*, not what
they would become. Recomputation belongs to integration, which is not authorised.

---

## 6. Tokens and cost — estimates and measurements reported separately

**Pre-run estimates**

| | |
|---|---:|
| Input | 1,146,898 |
| Output | 161,700 |
| Cost | $4.89 |

**Measured**

| Stage | Input | Output | Calculated list-rate cost |
|---|---:|---:|---:|
| Stage 1 | 426,734 | 122,817 | $2.60 |
| Stage 2 | 681,264 | 196,584 | $4.16 |
| **Total** | **1,107,998** | **319,401** | **$6.76** |

Input came in 3.4% under estimate. **Output was 97.5% over**: the estimate assumed 210
tokens per assessment, the measured figure is 415 across 770 assessments. Under
`effort=high` the auditor writes far fuller reasoning than the prior corpus predicted.
Costs are **calculated at published list Batch rates** ($2.50/$12.50 per MTok, verified
2026-08-02) from measured counts; they are not necessarily the amount charged.

---

## 7. What this audit establishes, and what it does not

- **It establishes** that an independent cross-model auditor, run twice, found
  transcript-localised participant evidence contradicting **16 of 260** absence decisions,
  and concurred with **121 of 125** originally-present codings without a single flat
  contradiction.
- **It does not establish** that any absence is correct. Under Band B, corroboration is
  unavailable: 180 cells record only that the auditor did not find evidence.
- **It does not establish** that the 16 contested cells are original errors. They are
  cells where two codings disagree and the second supplies a localised quotation.
- **64 cells remain unresolved** — a quarter of the universe — and enter no sensitivity
  bound in either direction.

## 8. Artefacts

| File | Contents |
|---|---|
| `stage2_batch_job.json` | Stage-2 job id, config, custom_id map |
| `stage2_raw_responses.json` | 42 raw responses, unchanged |
| `absence_audit_complete.json` | full reconciliation, both sensitivities, tokens |
| `absence_adjudication_260.csv` | the 260 absence cells with final labels |
| `audit_results_long_385.csv` | all 385 cells, both repetitions, gate outcomes |
| `participant_breadth_bounds.csv` | the 16 contested cells, LOWER/MID/UPPER |
| `across_group_recurrence_sensitivity.csv` | ORIGINAL vs CONTESTED_AS_PRESENT |
| `ABSENCE_AUDIT_REPORT.md` | this document |

---

**Stopped for review before integrating anything.** The heatmap, workbook and dissertation
drafts are untouched; ORIGINAL/LOWER stands as the primary result; the Gemini coding is
unchanged.
