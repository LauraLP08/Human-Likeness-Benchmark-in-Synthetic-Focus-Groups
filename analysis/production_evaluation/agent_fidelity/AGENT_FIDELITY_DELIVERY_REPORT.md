# Level 3 — Agent fidelity: initial delivery, before any API call

**Status:** offline work complete. **No API call was made and no new human task was
opened.** Nothing in `analysis/production_evaluation/results/`,
`analysis/production_evaluation/final/`, `metric_registry.csv`,
`FINAL_RESULTS_TABLES.xlsx` was modified.

**Tests:** `tests/test_agent_fidelity.py`, 42 passing.

---

## B. The conceptual correction, applied throughout

The expression *"the LLM understands each agent as an independent person"* is not used
anywhere in this package. The observable property is:

> **LEXICALLY_INDIVIDUALISABLE_AGENT_VOICE** — the capacity to distinguish a
> participant's text from that of their fellow participants, and to recognise the same
> participant across different guide questions.

Four quantities are held apart and never substituted for one another:

| Quantity | Where it is measured | What it cannot show |
|---|---|---|
| between-speaker lexical differentiation | Panel A; within a question | whether anyone keeps a recognisable voice across questions |
| within-speaker cross-question continuity | leave-one-question-out speaker identification | psychological or biographical continuity |
| topical / semantic difference | controlled for by holding the question pair fixed | identity |
| substantive profile consistency | not measured offline at all | anything lexical |

Lexical diversity, MATTR, TTR and lower vocabulary overlap are **not** presented as
evidence of an individual identity anywhere.

---

## 1. Feasibility report

Source: `agent_fidelity_preflight.json`, `agent_fidelity_cell_tokens.csv`.

- **35 documents, 586 participant × question cells, all 174 segmentation units
  reconcile** against `inductive_segments.json` on both coordinate systems.
- **Leakage: clean.** 0 name leaks, 0 provenance identifiers, 0 turn ids in analysed
  text. 1,366 roster-name mentions were scrubbed.
- **Human FG5 Q4 remains `NOT_ASKED_IN_FIELDWORK`** — not a fold, not a zero, not a
  budget exclusion.

### Words per participant × question cell

| Condition | n | min | p25 | median | max |
|---|---:|---:|---:|---:|---:|
| human | 103 | **27** | 79 | 145 | 1216 |
| enriched | 243 | 123 | 256 | 398 | 1422 |
| demographics-only | 240 | 151 | 262 | 433 | 1205 |

**100 tokens is not viable at participant × question level.** The budget binds entirely
on the human side; any budget humans can meet, synthetic participants meet with room to
spare, so equalisation removes text from synthetic participants only.

### The eligibility rule that had to be rejected

The natural rule — a participant counts only if they meet the budget in *every* question
— was implemented first and then set aside, because of an asymmetry that runs opposite to
expectation:

| Condition | documents keeping ≥2 participants present in every question |
|---|---|
| human | **5 / 5** |
| enriched | **3 / 15** |
| demographics-only | **2 / 15** |

Synthetic participants are frequently silent in a question. The strict rule would have
compared five human focus groups against roughly three synthetic documents. The main rule
is therefore **PER_FOLD**: eligible for the fold holding out question *q* if the
participant meets the budget in *q* and in at least two other questions.

### Budget curve (folds eligible / folds total)

| Budget | human | enriched | demo-only | FGs H/E/D |
|---:|---|---|---|---|
| 25 | 24/24 | 73/75 | 69/75 | 5/5/5 |
| **50** | **24/24** | **73/75** | **69/75** | **5/5/5** |
| 60 | 23/24 | 73/75 | 69/75 | 5/5/5 |
| 75 | 22/24 | 73/75 | 69/75 | 5/5/5 |
| 100 | 18/24 | 73/75 | 69/75 | 5/5/5 |

**Main budget 50 words** — the largest that costs no human fold. **Sensitivity 25 words.**
Thin arms at 60/75/100 are reported but cannot carry a verdict: they drop human folds.

### Exclusions

- 180 participant × question absences (participant silent in that question) — an absence,
  not a zero.
- `D::fg1::R2` yields no eligible fold at the main budget and is reported as excluded, so
  demographics-only rests on 14 of 15 documents.

---

## 2. Offline lexical-distinctiveness results

Source: `agent_fidelity_stylometry.json`, `agent_fidelity_speaker_id_by_document.csv`,
`agent_fidelity_trials_long.csv`, `agent_fidelity_stylometry_sensitivity.json`.
Figure: `analysis/figures/agent_fidelity_lexical_distinctiveness.png` (+ `.csv`).

Character n-gram TF-IDF (`char_wb`, 3–5), lowercase, fitted on the training fold only.
Nearest-centroid cosine. One deterministic centred window per cell; offsets are never
repeated.

### Leave-one-question-out speaker identification — 551 trials, 166 folds

| Condition | n | accuracy | chance | chance-corrected | macro-F1 | balanced acc. |
|---|---:|---:|---:|---:|---:|---:|
| human | 94 | 0.468 | 0.255 | **+0.286** | 0.415 | 0.439 |
| enriched | 234 | 0.325 | 0.312 | **+0.019** | 0.279 | 0.302 |
| demographics-only | 223 | 0.377 | 0.309 | **+0.097** | 0.320 | 0.343 |

Per focus group, chance-corrected, replicates separate:

- human: fg1 +0.41, fg2 +0.20, fg3 +0.22, fg4 +0.22, fg5 +0.36 — **all five positive**
- enriched: 15 sessions spanning **−0.30 to +0.33**; 6 at or below zero
- demographics-only: 14 sessions spanning **−0.33 to +0.50**; 5 at or below zero

### Between-speaker lexical similarity within a question (higher = more alike)

| Condition | median | range | n documents |
|---|---:|---|---:|
| human | 0.179 | 0.172 – 0.203 | 5 |
| enriched | 0.268 | 0.215 – 0.323 | 15 |
| demographics-only | 0.258 | 0.221 – 0.326 | 14 |

The human range does not overlap either synthetic range at equal token budget.

### Identity gap, question pair held fixed

| Condition | median | range | n documents |
|---|---:|---|---:|
| human | +0.0055 | −0.0033 – +0.0145 | 5 |
| enriched | −0.0048 | −0.0221 – +0.0403 | 15 |
| demographics-only | −0.0014 | −0.0276 – +0.0233 | 14 |

A symmetric comparison **was** constructible: same-speaker observations always span two
questions, so every contrast fixes an unordered question pair {qa, qb} and compares
same-speaker cos(qa,qb) against different-speaker cos(qa,qb) inside that same pair. The
topical distance is then common to both sides. The gap is **effectively null in every
condition, including the human one**, so speaker identification — not the gap — is the
primary estimand.

### Sensitivity

| Specification | accuracy | chance-corrected | n |
|---|---:|---:|---:|
| char_wb 3–5 @ 50 (**main**) | 0.370 | +0.099 | 551 |
| char_wb 3–5 alphabetic only @ 50 | 0.379 | +0.112 | 551 |
| word-level content @ 50 | 0.365 | +0.091 | 551 |
| char_wb 3–5 @ 25 | 0.350 | +0.076 | 560 |
| char_wb 3–5 @ 75 *(thin)* | 0.384 | +0.107 | 529 |
| char_wb 3–5 @ 100 *(thin)* | 0.393 | +0.117 | 511 |

Direction is stable across every representation and budget.

### Strictly descriptive statement of the result

At an equal 50-word budget per participant and question, held-out answers were matched to
their own author above the per-fold chance baseline in all five human sessions
(chance-corrected +0.20 to +0.41). Across the thirty synthetic sessions the same
procedure produced values spanning roughly −0.33 to +0.50, with eleven of twenty-nine
eligible sessions at or below chance. Participants within a synthetic session also
resembled each other more lexically than participants within a human session, and the
human range did not overlap either synthetic range.

**No causal or mechanistic claim is attached to this.** It is an automatic stylometric
automatic stylometric diagnostic, computed on short equalised windows, and the
between-session spread within each synthetic condition is wider than the distance between
the two synthetic conditions.

---

## 3. Blinded candidate inventory — hyper-exactness

Source: `hyper_exactness_candidates_blinded.json` (payload),
`agent_fidelity_audit_sealed_reference.json` (provenance, separate file),
`hyper_exactness_candidates.csv`.

1,301 participant turns scanned → **67 candidates**: human 11, enriched 31,
demographics-only 25.

| Detector | hits |
|---|---:|
| SPECIFIC_QUANTITY_OR_PRICE | 50 |
| SPECIFIC_FREQUENCY_OR_DURATION | 16 |
| PRECISE_EPISODIC_MARKER | 2 |
| PERCENTAGE_OR_DECIMAL | 1 |
| EXACT_DATE_OR_TIME | 1 |
| STATISTICAL_FIGURE | 0 |

Two detector defects were found and fixed during construction, both of which would have
produced a plausible but meaningless inventory:

1. **Digits are the wrong surface.** Only **50 of 1,301** turns contain any digit, while
   **567** contain a spelled-out number. A digit-only detector was nearly blind. Every
   quantity pattern now accepts both forms.
2. **"exactly" is an intensifier here, not a precision marker.** It occurs 162 times, in
   constructions like *"not exactly the healthiest"* and *"tasted exactly like beef"*.
   Used as a standalone trigger it generated 163 of 167 candidates and buried the numeric
   ones. It now fires only before a quantity.

The detector **proposes and classifies nothing.** The audit payload carries item id,
verbatim quote, turn id and opaque speaker label only — no condition, focus group,
replicate, human/synthetic status, model or profile.

---

## 4. Candidate inventory — profile consistency

Source: `profile_consistency_pairs_blinded.json`.

**802 candidate pairs**: 742 screener-proposed + **60 random controls the screener did
not propose**, drawn with a fixed seed from a population of 1,962. Without the control
sample a screener's silence would be mistaken for consistency.

By condition: human 214, enriched 261, demographics-only 327.

The screener is vocabulary overlap only. No embedding and no NLI model may dictate a
verdict — they may propose candidates and nothing more.

---

## 5. Cost and exact plan for any LLM audit

Token model: measured `tokens = 1.7502 × words + 1620` (R² 0.9989). Claude Batch rate
$2.50 / $12.50 per MTok, verified 2026-08-02. **Gemini:
`NOT_CALCULATED_RATE_NOT_VERIFIED` — no verified rate exists and none is invented.**

| Audit | items | requests | input tok | output tok | Claude Batch USD |
|---|---:|---:|---:|---:|---:|
| hyper-exactness, full | 67 | 6 | 36,306 | 14,740 | **0.28** |
| profile consistency, full | 802 | 81 | 251,667 | 160,400 | **2.63** |
| **combined** | 869 | 87 | 287,973 | 175,140 | **≈ 2.91** |

An "efficient scheme" prioritising severe detector families was implemented but is
**unnecessary**: the full hyper-exactness audit is six requests. Recommendation is to run
the full inventory rather than sample it.

Gemini remains the study's primary evaluator; a second model is proposed only as blinded
auditor where contextual classification is indispensable, which is the case for both
audits above.

---

## 6. What can be claimed

### CAN_BE_REPORTED_NOW

| Item | Basis |
|---|---|
| Feasibility, token budgets, eligible folds, exclusions | fully offline, reconciled against the frozen segmentation |
| That 100-token equalisation is infeasible at participant × question level | measured: smallest human cell is 27 words |
| That synthetic participants are frequently silent in a question (3/15 and 2/15 documents keep 2+ participants present throughout) | measured |
| Leave-one-question-out speaker-identification accuracy, chance baselines, chance-corrected accuracy, macro-F1, balanced accuracy, confusion matrices, per FG, per question, per replicate | fully offline, reproducible, leakage-tested |
| Between-speaker lexical similarity within a question | fully offline |
| That the identity gap is effectively null in every condition | fully offline |
| That only 50 of 1,301 turns contain a digit | measured |

### EXPLORATORY_ONLY

| Item | Why |
|---|---|
| Any interpretation of the speaker-identification contrast between conditions | `EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC`; no human validation; operationalisation chosen after the main results were known |
| Between-speaker differentiation as a statement about "voice" | it measures how alike session members are, nothing more |
| Anything derived from the thin budgets (60/75/100) | they drop human folds |

### CANNOT_BE_CLAIMED

| Claim | Why not |
|---|---|
| that a model understands or represents an agent as an independent person | not an observable property of this design |
| hyper-exactness rates of any kind | the audit has not been run; only candidates exist |
| that lower numeral density means less hyper-exactness | density counts figures, not how they are used, and this corpus states quantities in words |
| profile consistency, validated | no audit has run, and even when it does it is `LLM_ASSISTED_EXPLORATORY_PROFILE_CONSISTENCY_AUDIT` |
| input-profile adherence compared against humans | no equivalent input sheet exists for a human; the human value is undefined, not zero |
| that the two-coder review validates any of this | it partially validates thematic extraction in Q3 only |
| psychological or biographical continuity from lexical continuity | different constructs |

---

## 7. GO / NO-GO by component

| Component | Recommendation |
|---|---|
| **C. Lexical distinctiveness** (C1 rename, C2 representation, C3 speaker ID, C4 gap) | **GO — complete and reportable now** as an exploratory automatic diagnostic |
| **D. Figure** | **GO — delivered** |
| **E. Hyper-exactness** | **GO for the blinded audit** (67 items, 6 requests, ≈ USD 0.28). NO-GO on reporting any rate until it runs |
| **F.1 lexical identity continuity** | **GO** — it is the C3 result |
| **F.2 input-profile adherence** | **NO-GO pending your decision.** Profiles exist at `agents/macho_meals_*/`; synthetic-only by construction. Prepared, not built |
| **F.3 expressed-position continuity** | **NO-GO** — needs the same contextual audit as G; not separately packaged |
| **G. Profile consistency** | **GO for the blinded audit** (802 pairs incl. 60 controls, 81 requests, ≈ USD 2.63). NO-GO on any consistency figure until it runs |
| **H. Registry** | **GO on the diff as a proposal**; the frozen registry is untouched and awaits approval |

### Mandatory defects (found and fixed in this delivery)

1. Participant labels were derived from a per-question speaker ordering, so `S03` meant a
   different person in any question where somebody stayed silent. Now document-level;
   guarded by `test_participant_labels_mean_one_person_across_questions`.
2. The digit-only hyper-exactness detector missed the form in which this corpus states
   quantities.
3. `exactly` as a standalone trigger produced 163 of 167 candidates from an intensifier
   reading.
4. `to the day` matched *"start to the day"*; the precision idioms now require either an
   unambiguous noun (minute/second/penny) or an intensifier.

### Recommended improvements

1. **Run both audits together** — 87 requests, ≈ USD 2.91, one blinding scheme, one
   sealed reference.
2. **Report `D::fg1::R2` explicitly as excluded** wherever demographics-only is
   summarised, so 14/15 is never read as 15/15.
3. **State the identity gap as null rather than omitting it.** A constructible symmetric
   comparison that returns nothing is a result, and dropping it would leave the reader
   assuming it favoured one side.

### Optional expansions

1. Input-profile adherence (F.2) as a synthetic-only descriptive inventory.
2. A within-condition permutation control: shuffle speaker labels inside a document and
   re-run the identification to show the pipeline returns chance when identity is
   destroyed.
3. Turn-level rather than question-level profiles, to test whether the human advantage
   survives at a finer grain.
