# Stage 1 calibration — results

**Job `msgbatch_01GjsFCpq5CULdhcdMzN6Ti1`**, submitted and retrieved 2026-08-03.
28/28 requests succeeded, 0 errored, every response `end_turn`.

> ## Outcome: **Band B — `PROCEED_DETECTION_ONLY`**
>
> **No absence may be labelled `ABSENCE_CORROBORATED`.** Detections and repetition
> agreement both cleared Band A; the unresolved rate did not, by 0.0214.

**Stage 2 has not been submitted.** No Gemini result, salience table, heatmap, workbook or
reported product was touched, and no Gemini absence was converted into a presence.

---

## 1. Pre-submission revalidation — all ten passed

| Check | Required | Observed |
|---|---|---|
| Stage-1 documents | 14 | 14 |
| Unique requests | 28 = 14 × 2 repetitions | 28 |
| Candidates per request | 11 | 11 |
| Production ids | A.1 A.2 A.3 B.1 B.2 B.3 B.4 C.1 C.2 C.3 D | exact match |
| Assessments | 154 per repetition, 308 total | 154 / 308 |
| Positive controls | 63 | 63 |
| `ORIGINAL_GEMINI_ABSENCE` cells | 91 | 91 |
| Cache-key collisions | 0 | 0 |
| Provenance / original-decision leakage | 0 | 0 scaffold, 0 transcript, 0 sealed-token |
| Builder access to sealed files | none | none (source-inspected) |

---

## 2. Submission

```
model                claude-opus-5          (no substitution, no synchronous fallback)
effort               high
max_output_tokens    8192
structured output    output_config.format json_schema
temperature          NOT transmitted
top_p                NOT transmitted
top_k                NOT transmitted
repetitions          2, separately keyed
retrieval            by custom_id only, never by response position
```

Job id persisted to `stage1_batch_job.json` immediately after submission.

### 2.1 `max_output_tokens = 8192` — POST-FREEZE CONFIGURATION COMPLETION

Recorded as a **completion**, not a revision: the parameter was **absent from the
pre-submission manifest**, so nothing was chosen and then changed.

| | |
|---|---|
| Value | **8192** |
| Absent from the pre-submission manifest | **yes** |
| Adopted from | the existing project cross-model audit configuration, `scripts/cross_model_audit_q3.py` `MAX_OUTPUT_TOKENS` |
| Invented for this audit | no |
| Chosen by inspecting Stage-1 results | no |
| Transmitted on all 28 Stage-1 requests | **yes** |
| Associated `end_turn` responses | **28/28** |
| Truncated responses | **0** |
| Complete 11-code outputs | **28/28** |

**Frozen prospectively for Stage 2 at 8192, and not retunable on Stage-1 results.**
Measured Stage-1 output was 399 tokens per assessment (~4,390 per response), well inside
the ceiling — but the reason for not moving it is not the headroom. Adjusting a frozen
parameter to fit observed behaviour would tune the instrument on its own calibration data.

The record is stored in `stage1_batch_job.json` and in the auditor block of
`batch_manifest.json`. Schema and prompt were used exactly as frozen, hash-checked at
preflight.

---

## 3. Response validation

**0 invalid responses of 28.** Every response parsed, carried the correct
`document_id`, and returned exactly 11 unique production subtheme ids — no missing, no
duplicated, no out-of-codebook id. All raw responses preserved unchanged in
`stage1_raw_responses.json`.

---

## 4. The gate

| Axis | Count | Wilson lower | Threshold | Verdict |
|---|---|---|---|---|
| Detections on positive controls | **60/63** (0.9524) | **0.8691** | ≥ 0.8333 | **clears A** |
| Repetition agreement | **140/154** (0.9091) | **0.8532** | ≥ 0.8333 | **clears A** |
| Unresolved | **24/154** (0.1558) | upper **0.2214** | ≤ 0.20 | **fails A** |

**Wilson values here are operational gate summaries, not confirmatory confidence
intervals.** The 63 control cells are clustered within 14 documents, and the 11
assessments in each response share a context, a rendering and a generation, so they are
dependent; the binomial interval is anticonservative and the true interval is wider. They
serve only to place a count into a band against thresholds stipulated in advance.

### Why Band B, precisely

The auditor is **sensitive** (missed only 3 of 63 localisable positives) and **stable**
(140/154 agreement). What it is not is **decisive**: 24 cells could not be resolved into a
verdict, and the upper bound on that rate exceeds the 0.20 ceiling by 0.0214. Band B is
the correct and conservative reading — the instrument finds evidence well, but its
non-findings are not yet clean enough to license a corroboration claim.

---

## 5. What Stage 1 licenses

| Raw relation (91 absence cells) | n | **Final reportable label under Band B** | n |
|---|---:|---|---:|
| `ABSENCE_CORROBORATED` | 64 | `AUDITOR_DID_NOT_FIND_EVIDENCE` | **64** |
| `ABSENCE_CONTESTED` | 6 | `ABSENCE_CONTESTED` | **6** |
| `ABSENCE_UNRESOLVED` | 21 | `ABSENCE_UNRESOLVED` | **21** |

**Absences corroborated: 0.** The 64 in the left column are the raw two-coding relation,
not a result. Band B forbids the corroboration label, so all 64 fall back to the neutral
statement of what the auditor actually reported.

The 6 contested cells stand. A gate-passed quotation is verified against the transcript
rather than against the auditor, so low decisiveness does not weaken a detection. **They
are not converted into presences here** — that is a Stage-2-and-review matter, and the
Gemini coding is unchanged.

---

## 6. The 11 designated positive controls

**All 11 detected.** Every subtheme is eligible for future absence corroboration, so the
subtheme-specific rule blocks nothing on this evidence — and the global band alone is
what withholds corroboration.

| Subtheme | Verdict | Eligible |
|---|---|---|
| A.1, A.2, A.3 | `AUDITOR_EVIDENCE_FOUND` | ✅ |
| B.1, B.2, B.3, B.4 | `AUDITOR_EVIDENCE_FOUND` | ✅ |
| C.1, C.2, C.3 | `AUDITOR_EVIDENCE_FOUND` | ✅ |
| D | `AUDITOR_EVIDENCE_FOUND` | ✅ |

This matters more than it looks: `D` was the identifier the test fixture had wrong. It
is now exercised on real data and its control was detected.

**Eligible: 11/11. Ineligible: none.**

### The 3 undetected controls (none designated)

| Subtheme | Document | Rep 1 | Rep 2 | Result |
|---|---|---|---|---|
| D | `DOC_044D944A54` | UNCERTAIN | EVIDENCE_FOUND | unresolved |
| B.1 | `DOC_62191FF7A9` | UNCERTAIN | UNCERTAIN | unresolved |
| B.4 | `DOC_C71426C1B1` | EVIDENCE_FOUND | UNCERTAIN | unresolved |

**Not one is a clean miss.** All three are unresolved, and in two of them a repetition did
find the evidence. The auditor's weakness is indecision, not blindness.

---

## 7. Quotation-gate failures

**2 of 308 assessments**, both `UNCERTAIN_QUOTATION_NOT_IN_NAMED_TURN` — a quotation that
could not be located verbatim in the turn the auditor named.

| Type | n |
|---|---:|
| `UNCERTAIN_QUOTATION_NOT_IN_NAMED_TURN` | 2 |
| `UNCERTAIN_TURN_NOT_FOUND` | 0 |
| `UNCERTAIN_SPEAKER_MISMATCH` | 0 |
| `UNCERTAIN_EVIDENCE_ATTRIBUTED_TO_MODERATOR` | 0 |
| `UNCERTAIN_NO_QUOTATION_SUPPLIED` | 0 |

Neither was repaired or relocated; both were downgraded and neither contributed a speaker.
Zero moderator-attributed and zero misattributed evidence is a good sign for the
localisation discipline of the detections that did pass.

---

## 8. Where the 24 unresolved cells sit

| | n |
|---|---:|
| On `ORIGINAL_GEMINI_ABSENCE` cells | 21 |
| On positive controls | 3 |

By subtheme: **D 5, B.1 4, C.2 4, B.2 3, A.3 3, B.3 3, C.3 1, B.4 1**. A.1, A.2, B.4 and
C.1 are nearly clean.

Disagreement pattern of the 24:

| Rep 1 / Rep 2 (after gating) | n |
|---|---:|
| UNCERTAIN / UNCERTAIN | 10 |
| NO_EVIDENCE_FOUND / UNCERTAIN | 7 |
| EVIDENCE_FOUND / UNCERTAIN | 6 |
| EVIDENCE_FOUND / NO_EVIDENCE_FOUND | 1 |

**Only one cell is a straight contradiction.** The other 23 involve at least one
`UNCERTAIN` — the auditor declining to decide rather than two repetitions asserting
opposite things. This is the single most actionable finding in Stage 1.

---

## 9. Evidence on adjacent-subtheme confusion — two evaluators

> **Correction. An earlier version of this section stated that the original coder's
> per-code quotations were unavailable and that no direct comparison against its evidence
> could be made. That was wrong and is withdrawn.** I had checked only the aggregated CSVs
> under `results/`; every COMPLETE batch record in `evaluator_cache/` carries
> `tier1.codes[].supporting_quotes` with quote, turn and speaker. The analysis below is
> the comparison that was said to be impossible. It changes no Stage-1 metric.

**Reconstruction.** One COMPLETE cache record was selected per document by an objective
rule — frozen input `sha256`, `completeness.status == COMPLETE`, and a presence pattern
reproducing the frozen grid — never by timestamp. `human::fg1` has three cached records;
exactly one qualifies. **35/35 documents resolved, 2 records rejected on stated grounds.**

**Original coder quotations: 356 across the corpus**, of which **174 belong to the 63
Stage-1 positive controls**.

| Verification of the 63 controls | |
|---|---|
| Controls with supporting quotations | **63/63** |
| Every quotation carries a `turn_id` | **63/63** |
| Every quotation carries a speaker | **63/63** |

### 9.1 The two evaluators do not share a turn numbering

This had to be resolved before any comparison, and it invalidated my first attempt.
Measured over all 356 quotations, the difference between the original coder's turn label
and the audit turn actually holding that text is **+1 for all five human documents but
varies within every synthetic document, from −6 to +14**. It is not an index base that
could be corrected by addition, and the two label spaces cannot be compared at all.
Comparing them directly — which my first run did — manufactures both agreement and
disagreement out of nothing.

**The quote text is the reliable anchor.** Each original quotation is located in the audit
rendering by exact normalised substring match, and the audit's own turn id and speaker are
read off from where it lands. All comparison happens in that one space.

- **173 of 174** control quotations projected successfully.
- **1 is `UNLOCALISED_FOR_CROSS_EVALUATOR_COMPARISON`**: a B.4 quotation in
  `DOC_62191FF7A9` (`"I eat meat because I like it and it's practical…"`) that the
  normalised substring match could not place in the audit rendering. **This is a
  limitation of the cross-evaluator projection, not a judgement about the quotation.** It
  is not called fabricated, invalid or absent; the original coder's B.4 code and its
  evidence stand entirely unchanged, and the cell is simply excluded from the turn-level
  comparison.
- Speaker correspondence (`Participant N` → `PN`) resolved **unambiguously in all 14
  documents**.

### 9.2 Agreement between the evaluators

Identical quotations were never required — a different valid passage supporting the same
code is reported as its own outcome, not as disagreement.

| Per control (best match over the cell's evidence) | n |
|---|---:|
| `SAME_TURN_SAME_SPEAKER` | **61** |
| `ADJACENT_CODE_DIVERGENCE` | 1 |
| `CLAUDE_PRODUCED_NO_GATED_EVIDENCE` | 1 |

| Per evidence item (unaggregated) | n |
|---|---:|
| `SAME_TURN_SAME_SPEAKER` | **116** |
| `DIFFERENT_VALID_EVIDENCE_SAME_SPEAKER` | 2 |
| `DIFFERENT_VALID_EVIDENCE_DIFFERENT_SPEAKER` | 2 |
| `ADJACENT_CODE_DIVERGENCE` | 2 |

**61 of 63 controls land on the same turn and the same speaker as the original coder.**
Two independent models, one never seeing the other's output, converged on the same
sentence of the same participant in 97% of cases. The per-item view is reported beside the
per-control view because a best-match rule would otherwise hide a cell where one
repetition matched and the other diverged; only 6 of 122 items diverge at all, and 4 of
those are a different valid passage rather than a conflict.

### 9.3 Adjacent-code divergence

**One control diverges: B.2 in `DOC_62191FF7A9`.** Claude cited turn T018 (P3) in **both**
repetitions — a turn the original coder used for **B.4**, its sibling, not for B.2. The
original coder's own B.2 evidence sits at T014/T017/T019/T020/T024. This is a stable
reading, not sampling noise.

The same document holds the **B.1 control that Claude left unresolved**, where the
original coder had three quotations at T022/T023/T024. And the single unlocalisable
quotation is also a B.4 in this document.

**The original coder shows the same tendency.** In the 14 Stage-1 documents it used **one
turn to support two codes of the same family 11 times**:

| Document | Turn | Codes |
|---|---|---|
| `human::fg3` | T047 | A.1, A.3 |
| `human::fg2` | T014, T015 | A.2, A.3 |
| `human::fg2` | T021 | C.1, C.3 |
| `human::fg1` | T053 | C.1, C.3 |
| `human::fg5` | T063 | B.2, B.4 |
| `macho_meals_fg1_run02` | T019 | B.2, B.4 |
| `macho_meals_fg2_run02` | T014 | B.2, B.4 |

**This reframes the finding.** Adjacent-code overlap is not a Claude artefact — the
original coder does it too, and on the same pairs: **B.2/B.4**, **C.1/C.3**, **A.2/A.3**.
The B family, where Stage-1 indecision concentrated (11 of 24 unresolved cells), is also
where both evaluators most often read one passage as satisfying two definitions. That
suggests potential overlap or legitimate co-occurrence at the B.2/B.4 boundary and therefore requires interpretive caution; it does not establish that either evaluator misclassified the passage.

For completeness, the Claude-only view reported earlier still holds: within-family turn
reuse 3 instances, across-family 9 — reuse is *less* common within a family than across
one, which argues against wholesale adjacent-code collapse in either evaluator.

## 10. Tokens and cost

| | Estimated | Measured | Error |
|---|---:|---:|---|
| Input tokens | 438,342 | **426,734** | +2.7% |
| Output tokens | 64,680 | **122,817** | **−47.3%** |
| Cost (list Batch) | $1.90 | **$2.60** | +37% |

The input model held well. **The output estimate was badly wrong**: I assumed 210 tokens
per assessment; the measured figure is 399. Under `effort: high` the auditor wrote far
fuller reasoning than the prior corpus suggested. Carrying that forward, a Stage-2
estimate should use ~399 tokens/assessment, which moves the projected Stage-2 incremental
cost from $2.98 to roughly **$4.10**, and the full-corpus figure from $4.89 to about
**$6.70**. Cost calculated at published list rate, not necessarily the amount charged.

---

## 11. Reading this honestly

- The auditor **detects well** (60/63) and is **stable** (140/154). Neither figure is the
  problem.
- It is **indecisive**: 24/154 unresolved, upper bound 0.2214 against a 0.20 ceiling.
  Band B follows from that single axis, missed by 0.0214.
- **Nothing is corroborated.** All 64 candidate corroborations are reported as
  `AUDITOR_DID_NOT_FIND_EVIDENCE`.
- **6 contested cells stand**, and they are the informative output of Stage 1 — but they
  remain contested, not converted.
- **All 11 subtheme controls passed**, so no subtheme is blocked by the eligibility rule.
- The **B family** is where indecision and adjacent-code signals concentrate — and the
  two-evaluator comparison shows the original coder overlapping B.2/B.4 on a single turn
  as well. This suggests potential overlap or legitimate co-occurrence at the B.2/B.4 boundary and therefore requires interpretive caution; it does not establish that either evaluator misclassified the passage.
- **61 of 63 positive controls land on the same turn and the same speaker for both
  evaluators**, which is strong convergent evidence that the two codings are reading the
  same passages.
- One earlier claim in this report was wrong and is withdrawn (§9): the original coder's
  quotations were always recoverable from the evaluator cache.

## 12. Artefacts

| File | Contents |
|---|---|
| `stage1_batch_job.json` | job id, config, custom_id map |
| `stage1_raw_responses.json` | 28 raw responses, unchanged |
| `stage1_calibration_results.json` | validation, gating, reconciliation, gate, eligibility, adjacency, tokens |
| `stage1_cells_long.csv` | 154 cells with both repetitions, gate outcomes and final labels |
| `stage1_designated_controls.csv` | the 11 designated controls and eligibility |
| `stage1_two_evaluator_evidence.json` | cache reconstruction, audit-space projection, two-evaluator comparison |
| `stage1_two_evaluator_controls.csv` | the 63 controls with both evaluators' evidence |
| `STAGE1_CALIBRATION_REPORT.md` | this document |

---

**Stopped after Stage 1, as instructed. Stage 2 not submitted despite no Band-C failure.
Awaiting review.**
