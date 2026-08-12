# Level 3 — Agent fidelity: corrected preflight

**Status:** corrections applied. **No API call was made.** The 87 prepared requests were
not sent; they are superseded by the two packages below, which now total 35 requests.

**Not modified:** `FINAL_RESULTS_TABLES.xlsx`, deductive results,
inductive results, transcripts, human workbooks, closed evaluator cache,
`metric_registry.csv`.

---

## 1. Unit of analysis and aggregation — corrected

The primary comparative estimand is now hierarchical:

**trial → document → focus group → study replicate.**

All seven values were reproduced by recomputation from the per-document estimates, not
read from constants:

| Condition | Realisation | chance-corrected accuracy | coverage |
|---|---|---:|---|
| human | FG1–FG5 (one realisation) | **0.2840** | 5/5 |
| enriched | R1 | **0.0176** | 5/5 |
| enriched | R2 | **−0.0933** | 5/5 |
| enriched | R3 | **0.1144** | 5/5 |
| demographics-only | R1 | **−0.0120** | 5/5 |
| demographics-only | R2 | **0.1411** | **4/5 — `D::fg1::R2` produced no eligible fold** |
| demographics-only | R3 | **0.1835** | 5/5 |

Human per focus group: FG1 0.4118, FG2 0.2000, FG3 0.2222, FG4 0.2223, FG5 0.3636.

`D::fg1::R2` is **absent**, not imputed and not zero. A test plants the zero-imputed
alternative and requires it to differ from what is reported.

The figures pooled over 551 trials are retained as technical information only, labelled
**`TRIAL_WEIGHTED_DIAGNOSTIC_NOT_PRIMARY_CONDITION_ESTIMATE`**, with the reason recorded:
pooling weights each document by how many speakers and eligible folds it contains, which
is a property of the transcript rather than of the condition.

No inferential test is derived from five focus groups or three realisations. Values,
direction, between-realisation dispersion and coverage are reported; nothing else.

New artefact: `agent_fidelity_hierarchical_estimates.csv` (34 focus-group rows +
7 study-replicate rows).

## 2. Terminology — words, not tokens

Every methodological and visual description now says **words**. The budget is 50 words
cut by the project lexical tokeniser; it is not a model-token budget. "Token" survives
only where it means API cost or model tokenisation.

A test scans the artefacts for the misuse and is itself checked against three planted
phrases (`50-token budget`, `tokens per participant`, `100 tokens is not viable`) so a
guard that never fires cannot pass silently. No computed value changed.

## 3. Identity gap — corrected interpretation

Withdrawn: "null identity gap", "the identity gap is null", and every equivalence or
absence-of-difference formulation. No equivalence margin was defined and no equivalence
test was run.

The wording now used, verbatim:

> The median identity-separation gap was close to zero in all three conditions and did
> not provide additional evidence of persistent speaker differentiation.

Observed values are kept unchanged: human +0.0055 (−0.0033 to +0.0145), enriched −0.0048
(−0.0221 to +0.0403), demographics-only −0.0014 (−0.0276 to +0.0233).

Speaker identification remains the primary estimand because it evaluates directly whether
a held-out text can be attributed to its own speaker among the eligible participants of
the same session.

## 4. Figure — corrected

`analysis/figures/agent_fidelity_lexical_distinctiveness.png` and its script.

- **Panel A** unchanged in substance: between-speaker lexical similarity, one point per
  document, higher = participants more lexically alike, labelled a differentiation
  diagnostic and not evidence of persistent identity.
- **Panel B** now plots **chance-corrected accuracy per document** against a zero line.
  The averaged chance line is gone: each session has its own baseline, so a single
  average would misstate every session but the average one. Labelled `human n=5`,
  `enriched n=15`, `demo-only n=14`, with the ineligible demographics-only session
  declared on the face of the panel.
- **Panel C** renamed **Identity-separation gap**, with the zero line, the per-document
  values, and two notes: close to zero is not an equivalence result, and internal pairs
  are not independent observations.
- **Panel D** shows the five human focus-group values and the synthetic values by focus
  group with R1/R2/R3 identifiable and never joined. Study-replicate roll-ups sit beside
  the panel and in the CSV, with demographics-only R2 marked `4/5 FGs`.
- Ranges are called **observed range**, never a confidence interval.

Entirely in English.

## 5. Hyper-exactness — false-negative controls added

| | n |
|---|---:|
| detector-proposed candidates | 67 |
| `RANDOM_NONDETECTED_CONTROL_TURNS` | 60 (20 human, 20 enriched, 20 demographics-only) |
| **audited universe** | **127** |

Control selection is deterministic: non-candidate turns of at least 15 words, ordered by a
stable hash and taken round-robin across focus groups. A test verifies that **no control
fires any detector** and that candidates and controls do not overlap.

**They are not known negatives.** They have not been judged; their function is to measure
hyper-exact cases the detector missed.

**The stratum is invisible to the auditor.** Detector fields are stripped from *every*
payload, so a candidate and a control are indistinguishable in the request. Each item
carries only `item_id`, `turn_id`, opaque `speaker`, `quote`, `n_words`.

Categories and required decision fields unchanged. Future results must distinguish
detector candidate yield, adjudicated cases among candidates, cases found in the
controls, and the estimated or detected corpus rate. If the controls cannot support a
prevalence estimate, only **`DETECTED_LOWER_BOUND_RATE`** is reported. Unaudited turns are
`NOT_AUDITED`, never negative.

Numeral density remains `NUMERAL_DENSITY_DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS`.

**Volume:** 127 items → **11 requests**, 64,251 input tokens, 27,940 output tokens,
**USD 0.51** Claude Batch. Gemini: `NOT_CALCULATED_RATE_NOT_VERIFIED`.

## 6. Profile consistency — pilot before the 802

The 802 pairs are **not** sent. The pilot is:

| | n |
|---|---:|
| random controls (not screener-proposed) | 60 |
| screener-proposed, stratified | 60 |
| **pairs** | **120** |
| repetitions | 2 |
| **adjudications** | **240** |

Stratification of the proposed 60: condition × similarity tercile × focus group,
round-robin over 45 available strata; tercile bounds [0.0882, 0.1064].

**The 60 controls are not balanced by condition** — they were drawn at random from the
unscreened population (human 25 / enriched 32 / demographics-only 63 across the whole
pilot). Any false-negative estimate must therefore be reported per condition with its own
denominator. This is recorded in the manifest.

**240 distinct cache keys**, one per item × repetition. A test asserts all 240 differ and
that each item has exactly two: a shared key would serve one cached answer twice and read
as perfect agreement.

Blinding: the payload carries `item_id`, opaque `speaker`, `statement_a`, `statement_b`.
`source` and the screener score are stripped — they would reveal the stratum.

**Volume:** 240 adjudications → **24 requests**, 76,248 input tokens, 48,000 output
tokens, **USD 0.79**. The remaining **682 pairs are blocked** until the gate passes; the
full audit would be 81 requests, USD 2.65.

### Auditor technical validation (8 cases, run with the pilot)

| Case | Must return |
|---|---|
| direct contradiction | `UNEXPLAINED_CONTRADICTION` |
| explained change | `POSITION_CHANGED_WITH_EXPLANATION` |
| different contexts | `CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY` |
| evidence from another speaker | REJECT |
| non-literal quote | REJECT |
| unknown turn id | REJECT |
| no justification | REJECT |
| `UNCERTAIN` without explanation | REJECT |

### Prospective gate — `PROFILE_CONSISTENCY_PILOT_GATE_V1`

Fixed before any result is seen. **0.80 is not adopted as a default**; every bound is
argued from what the interpretation needs.

| Criterion | Bound | Why that bound |
|---|---|---|
| planted-contradiction recall | both repetitions | an auditor that misses a contradiction built to be unmissable cannot support a claim about contradictions |
| contradiction vs context separation | never confused, either repetition | the indicator rests entirely on this distinction, and confusing them inflates contradiction in the direction under study |
| malformed-response rejection | all 5 REJECT cases | a verdict resting on a misattributed or paraphrased quote is not evidence |
| exact agreement between repetitions | ≥ 0.60 detection-only, ≥ 0.75 full audit | below 0.60 the repetitions disagree on more than a third of items and no rate is interpretable; 0.75 is where a five-category judgement can carry a distribution rather than a flag |
| `UNCERTAIN` rate | ≤ 0.30 | above that the audit is mostly declining to decide and the rest describes a self-selected subset |
| verbatim evidence validity | ≥ 0.95 | quote verification is mechanical; anything less means reconstruction, not citation |
| control behaviour | same field completeness as proposed pairs | otherwise the false-negative estimate is unusable |

Outcomes: `AUDITOR_USABLE_FOR_EXPLORATORY_FULL_AUDIT`, `AUDITOR_USABLE_FOR_DETECTION_ONLY`,
`AUDITOR_USABLE_FOR_CORROBORATION_ONLY`, `AUDITOR_UNSTABLE_STOP`.

**Disagreements are never resolved** by model confidence, modal vote, a third call,
similarity scores or unrecorded manual choice. Items where the two repetitions disagree
stay `UNRESOLVED` and are reported as such.

If the gate fails, the 682 remaining pairs are not executed and the instability is the
pilot result.

## 7. Profile continuity — scope

Closed now: **`LEXICAL_IDENTITY_CONTINUITY`**, classified
`EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC`, operationalised as leave-one-question-out
speaker identification.

Not executed, left as optional expansions: `INPUT_PROFILE_ADHERENCE` (synthetic-only, no
human counterpart) and `EXPRESSED_POSITION_CONTINUITY` (a different family of contextual
decisions). Neither may be combined with lexical identity continuity into a composite
index. Lexical continuity is not psychological, biographical or attitudinal continuity.

## 8. Metric registry — revised diff

`metric_registry.csv` remains **untouched**.

**Proposable now** (their evidence exists and is offline):

| metric | proposed class |
|---|---|
| `lexical_identity_continuity` | `EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC` |
| `between_speaker_lexical_differentiation` | `EXPLORATORY_AUTOMATIC_LEXICAL_DIAGNOSTIC` |
| `numeral_density` | `DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS` |

**`PROPOSED_PENDING_AUDIT`** (6): `hyper_exactness`, `profile_consistency`,
`input_profile_adherence`, `expressed_position_continuity`, and the two frozen rows
`profile_continuity_group` and `profile_consistency_group`.

**Nothing is superseded yet.** Retiring a frozen row now would leave the indicator with no
live entry while its replacement is still unaudited.

The two-coder review of U01–U07 in Q3 partially validates thematic extraction in Q3. It
validates neither stylometry, nor hyper-exactness, nor lexical continuity, nor
contradiction.

## 9. `POST_A_REPLAN.json`

Added, without rewriting history:

```
"snapshot_taken_at": "STAGE_B_LAUNCH"
"snapshot_note": "Historical planning snapshot; not a statement of current execution status."
```

`stages_executed_here` and `stages_not_executed` are untouched and still record what was
true when the snapshot was taken. A test asserts both the new marker and the preserved
historical content.

---

## 10. Files created or modified in this turn

**Modified**

| File | Change |
|---|---|
| `scripts/agent_fidelity_stylometry.py` | hierarchical aggregation; pooled figures relabelled; words-not-tokens; identity-gap wording; hierarchical CSV |
| `analysis/figures/render_agent_fidelity_lexical_distinctiveness.py` | Panel B rebuilt, Panel C renamed, Panel D roll-ups, wording, canvas height |
| `scripts/agent_fidelity_audit_packages.py` | non-detected controls; pilot construction; cache keys; validation cases; gate; stratum stripped from payloads |
| `scripts/agent_fidelity_registry_diff.py` | `PROPOSED_PENDING_AUDIT`; nothing superseded |
| `tests/test_agent_fidelity.py` | updated for the renamed artefacts and the new pilot schema |
| `analysis/production_evaluation/inductive_phase_a/POST_A_REPLAN.json` | two additive snapshot fields |
| `analysis/production_evaluation/agent_fidelity/agent_fidelity_stylometry.json` | regenerated |
| `.../agent_fidelity_audit_packages.json`, `.../agent_fidelity_audit_sealed_reference.json`, `.../profile_consistency_pairs_blinded.json`, `.../metric_registry_diff_proposal.json`, `.../metric_registry_proposed_rows.csv` | regenerated |
| `analysis/figures/agent_fidelity_lexical_distinctiveness.png` / `.csv` | regenerated |

**Created**

- `tests/test_agent_fidelity_corrections.py` (51 tests)
- `analysis/production_evaluation/agent_fidelity/agent_fidelity_hierarchical_estimates.csv`
- `.../hyper_exactness_universe_blinded.json`, `.../hyper_exactness_universe.csv`
- `.../profile_consistency_pilot_blinded.json`, `.../profile_consistency_pilot_manifest.json`
- `.../AGENT_FIDELITY_CORRECTED_PREFLIGHT.md`

**Deleted (renamed supersessions, not results)**

- `.../hyper_exactness_candidates_blinded.json` → `hyper_exactness_universe_blinded.json`
- `.../hyper_exactness_candidates.csv` → `hyper_exactness_universe.csv`

---

## 11. Updated volume and cost

| Package | items | requests | input tok | output tok | Claude Batch USD |
|---|---:|---:|---:|---:|---:|
| hyper-exactness universe | 127 | 11 | 64,251 | 27,940 | 0.51 |
| profile-consistency pilot | 240 adjudications | 24 | 76,248 | 48,000 | 0.79 |
| **authorisation bundle** | | **35** | **140,499** | **75,940** | **1.30** |
| *(deferred)* full consistency audit if the gate passes | 802 | 81 | 251,667 | 160,400 | 2.65 |

Claude Batch rate $2.50 / $12.50 per MTok, verified 2026-08-02. Gemini:
`NOT_CALCULATED_RATE_NOT_VERIFIED`.

The previously prepared 87-request bundle is superseded and must not be sent.

---

## 12. GO / NO-GO

| Component | Recommendation |
|---|---|
| **Lexical distinctiveness** | **GO — reportable now** as `EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC`, at the hierarchical level only |
| **Hyper-exactness audit** | **GO pending your authorisation** — 127 items, 11 requests, USD 0.51 |
| **Profile-consistency pilot** | **GO pending your authorisation** — 120 pairs × 2, 24 requests, USD 0.79 |
| **Full profile-consistency audit** | **NO-GO** — blocked behind the pilot gate |
| **Input-profile adherence** | **NO-GO** — optional expansion, not executed |
| **Expressed-position continuity** | **NO-GO** — optional expansion, not executed |

### Mandatory defects found and fixed in this turn

1. **The primary estimand was trial-weighted.** Sessions with more speakers and more
   eligible folds carried more weight in the condition figure — a property of the
   transcript, not of the condition.
2. **A single averaged chance line was drawn across sessions with different baselines**
   in Panel B, which misstated every session but the average one.
3. **The identity gap was stated as null**, which is an equivalence claim that no
   equivalence margin and no equivalence test supported.
4. **The hyper-exactness audit had no way to measure what the detector missed.**
5. **802 pairs were prepared for an auditor whose stability had never been checked.**
6. **Two of my own guards were miswritten** and are now fixed: the token-misuse detector
   failed to match one of the three phrases it claims to guard, and the identity-gap
   scanner flagged the artefacts' own disclaimers.

### Recommended improvements

1. **Authorise both packages together** — 35 requests, USD 1.30, one blinding scheme.
2. **Report demographics-only R2 as 4/5 wherever it appears**, including in prose.
3. **Report the per-condition control denominators** for any false-negative estimate,
   given the controls are unbalanced by condition.

### Optional expansions

1. A permutation control: shuffle speaker labels inside a document and re-run
   identification, to show the pipeline returns chance when identity is destroyed.
2. Input-profile adherence as a synthetic-only descriptive inventory.
3. Turn-level rather than question-level profiles.

---

**Stopped. Awaiting explicit authorisation to execute the hyper-exactness audit and the
profile-consistency pilot.**
