# Blinded cross-model audit of deductive absences

**Status: PRE-SUBMISSION. No API call has been made.**
Built 2026-08-03 by `scripts/absence_audit_build.py` and `scripts/absence_audit_rules.py`.
Offline tests: `tests/test_absence_audit.py`.

Seven corrections were applied before Stage 1 — **[C1]**–**[C4]** in the first round and
**[C5]**–**[C7]** in the second. Each is marked where it takes effect, and each is
demonstrated to fail under a planted violation (§13).

---

## 1. What this audit is, and what it is not

The deductive coding recorded 260 absences: subtheme–document cells where the original
coder found no qualifying evidence. Those absences do real work in the results. They are
the zeros in the participant-breadth hierarchy, they drive the recall figure, and they
carry the condition comparison. Nothing has yet tested them.

This audit asks one question of each absence: **does an independent cross-model auditor,
reading the same text under the same definition, find transcript-grounded evidence that
contradicts it?**

It is **not** a new thematic analysis (the codebook is fixed and no new code can be
created), **not** proof of absolute absence, and **not** a replacement for the original
coding.

**The auditor is `claude-opus-5`.** The original deductive coder was Gemini, so Gemini
cannot supply independent cross-model evidence and is not used anywhere in this audit.

### 1.1 What "repetition" means here **[C3]**

Each request is run twice. These are **two separately keyed stochastic repetitions of an
independent cross-model auditor**.

The independence this design claims is between `claude-opus-5` and Gemini. The two
repetitions share a model, a prompt, a schema and a rendering, and differ only in the
repetition index carried in the cache key; they resample one model's stochasticity.
Agreement between them measures the **stability of a single auditor** and must never be
described as the concurrence of two auditors. A checker bans the overstated phrasings
from every artefact and every document, and a planted-violation test proves the checker
is not vacuous.

---

## 2. The universe is derived, never hard-coded

```
35 documents  ×  11 subthemes  −  125 verified-present instances  =  260 absences
```

Recomputed from `results/thematic_code_presence_long.csv` at build time. A cell counts as
present only when `present == True` **and** `quote_verified == True`. If the grid is not
exactly 385 cells, if any cell is missing, or if the row count does not equal the derived
count, the build aborts.

A mutation test flips one present cell and asserts the universe becomes 261 — a
hard-coded 260 would survive that. A second test asserts the 260 rows are the same 260
cells the source records, not merely the same count.

---

## 3. Request shape: the full codebook, every time

Every request carries **all 11 candidate codes** for its document, not only the codes
recorded as absent. Sending only the absent codes would have given every production
request an all-absent structural signature and a candidate count varying from 1 to 10,
while calibration requests carried a mixture. Identical shape everywhere removes that
signature, and the **125 originally-present cells return as a concurrence control** at
the cost of output tokens only.

- 35 documents × 11 candidates = 385 assessments per repetition
- 2 repetitions → **70 requests, 770 assessments**

---

## 4. Blinding: a split check

| Region | Contents | Rule |
|---|---|---|
| **Scaffold** | system prompt, wrapper, candidate blocks, codebook labels and definitions | full forbidden list, 37 terms |
| **Verbatim** | the transcript exactly as the original evaluator received it | hard provenance leaks only, 14 terms |

The transcript cannot be altered without destroying the thing being audited, and ordinary
English inevitably contains the task vocabulary. Participants in this corpus say *"missing
out on certain nutrients"*, *"more room for error"*, *"we reach for all the reasons why we
can't"*, *"that's sort of the baseline"*, *"it's very hard to replicate that"*. Twenty-five
documents trip the full list on speech alone. Applying it verbatim would either block the
audit or force edits to the evidence.

**Result: 0 scaffold failures, 0 verbatim leaks.**

A defect was found here by mutation testing and fixed: the word boundary originally
treated `_` as a word character, so `macho_meals_fg4_run01` — the exact shape a real leak
takes — did not match. The boundary now excludes alphanumerics only.

Documents are addressed by opaque ids (`DOC_` + 10 hex, salted). Speakers are
pseudonymised to `P1..Pn`; the moderator is labelled `Moderator`. Candidate order is
shuffled deterministically per document.

**Residual risk, stated rather than hidden:** participant first names occasionally occur
inside utterances. They identify no condition, and the auditor holds no reference set
against which to match them.

---

## 5. The manifest split **[C2]**

The calibration manifest is split so that no single publishable file functions as an
answer key.

| File | Contents |
|---|---|
| `calibration_request_manifest.json` | opaque ids, hashes, request metadata **only** |
| `sealed/calibration_reference_SEALED.json` | original status, side, document key, provenance |
| `sealed/sealed_document_mapping.json` | opaque id → provenance |

**The request builder has no read dependency on the sealed files.** `render_store()` is
the single privileged step: it reads the frozen inputs by path and returns a structure
keyed by opaque id alone. `build_requests()` consumes that store and the public manifest,
and has no parameter, no import and no path by which a sealed file could be read.

This is enforced two ways, not asserted: one test points the sealed directory at a
non-existent path and confirms all 35 requests still build; another inspects the
builder's source and fails if it so much as names a sealed path or an answer-key field.
A third test poisons the public manifest with `original_status` and confirms the purity
check catches it.

### 5.1 Calibration labels are not ground truth **[C2]**

| Label | Warrant |
|---|---|
| `ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED` | the original coder localised a quotation that was verified verbatim — a usable positive control |
| `ORIGINAL_GEMINI_ABSENCE` | the original coder's absence decision — **not a known negative and not ground truth**, since it is the thing under audit |

The absent cells were previously called reference-negatives. That name claimed a warrant
they do not have: a cell the auditor contests may be an original omission rather than an
auditor error, which is precisely the question the audit exists to ask. They are renamed
throughout, and the concurrence rate computed over them is **not** reported as a
specificity.

---

## 6. Rules frozen before submission

The order cannot be rearranged.

### 6.1 Local evidence gate — applied per repetition, before any comparison

An `EVIDENCE_FOUND` verdict survives only if its quotation is a contiguous substring of an
utterance in the **named turn of that document**, after normalising whitespace, case and
typography. Normalisation adds, removes and reorders no word, and applies no stemming.

| Reason | Meaning |
|---|---|
| `UNCERTAIN_NO_QUOTATION_SUPPLIED` | verdict asserted without evidence |
| `UNCERTAIN_TURN_NOT_FOUND` | the turn id does not exist in this document |
| `UNCERTAIN_QUOTATION_NOT_IN_NAMED_TURN` | paraphrased, or reconstructed from memory |
| `UNCERTAIN_SPEAKER_MISMATCH` | real quotation, wrong attribution |
| `UNCERTAIN_EVIDENCE_ATTRIBUTED_TO_MODERATOR` | only participant speech can express a code |

The gate **downgrades only** — it never upgrades a verdict, never repairs a quotation, and
**emits no speaker on failure**, so a failed assessment can never reach a reach bound.

### 6.2 Repetition rule

| Repetition 1 | Repetition 2 | Reconciled |
|---|---|---|
| `EVIDENCE_FOUND` | `EVIDENCE_FOUND` | `AUDITOR_EVIDENCE_FOUND` |
| `NO_EVIDENCE_FOUND` | `NO_EVIDENCE_FOUND` | `AUDITOR_DID_NOT_FIND_EVIDENCE` |
| anything else | | `AUDITOR_UNRESOLVED` |

Never settled by confidence, quotation length, ordering, or a third tie-breaking call.
Gating runs first: an ungated `EVIDENCE_FOUND` paired with a gated one must not reconcile
to agreement, and a test asserts it does not.

### 6.3 Cross-model rule

Absences → `ABSENCE_CORROBORATED` / `ABSENCE_CONTESTED` / `ABSENCE_UNRESOLVED`.
Present controls → `PRESENCE_CONCURRED` / `PRESENCE_NOT_CONCURRED` / `PRESENCE_UNRESOLVED`.
The original decision is the reference throughout and is never overwritten.

---

## 7. The exact Stage-1 gate **[C1]**

Prospective, stated in integer counts, and expressed through Wilson score intervals
(z = 1.96). **No universal 0.80 convention is used.**

### 7.0 What the Wilson intervals are, and are not

They are **operational gate summaries**, not confirmatory confidence intervals. They
convert a count into a decision band and nothing more, and must never be reported as
inferential statistics about the auditor's accuracy.

The binomial assumption does not hold here. The 63 positive-control cells are **clustered
within 14 documents**, and the 11 assessments for one document arrive in a **single
response** — sharing a context, a rendering and a generation, so they are **dependent**.
Clustered, dependent observations make a binomial interval **anticonservative**: the true
interval is wider than the one printed. The approximation is tolerable only because the
thresholds are stipulated in advance rather than estimated from the data, and because the
figures are used solely to place a count into band A, B or C.

### 7.1 The denominator, and why it is 63 and not 11

The gate is computed over **every** `ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED` cell the
Stage-1 documents return, not over the 11 designated present cases.

This is not a convenience. **At n = 11 a flawless 11/11 yields a Wilson lower bound of
0.7412** — below `THRESHOLD_A`. A gate stated on the designated set alone could not be
passed by any performance whatsoever. That is a property of the interval at n = 11, not
of the auditor. The 22 designated cases guarantee balanced subtheme coverage and are
reported separately; they are never the denominator.

```
Stage-1 documents                          14
cells returned                            154
ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED     63   ← detection denominator
ORIGINAL_GEMINI_ABSENCE                    91   ← scored against nothing
```

### 7.2 Thresholds, and where they come from

**`THRESHOLD_A = 1/1.20 = 0.8333`.** The audit estimates how many of the 260 absences are
contestable. If the auditor detects a fraction *s* of demonstrably locatable evidence, an
observed count *C* of contested cells implies roughly *C/s* contestable absences. Fixing a
declared tolerance that this inflation may not exceed **20%** gives a required detection
rate of 1/1.20 on the lower bound. The 20% tolerance is a stipulated choice, declared here
in advance; the threshold follows from it arithmetically.

**`THRESHOLD_B = 0.50`** is a property of the **instrument**, not of any cell. Below one
half, the auditor **fails to detect more known-localisable positive controls than it
detects**. An instrument in that state produces non-detections carrying too little
information to license a corroboration label of any kind.

**No claim is made about any individual cell.** This audit cannot say that a given
`AUDITOR_DID_NOT_FIND_EVIDENCE` is more probably an auditor failure than a true absence —
that would require knowing how many absences are genuinely contestable, which is the
unknown the audit exists to bound and cannot assume. The threshold governs whether the
instrument may license a corroboration label at all, never the status of one cell.

**Detections are unaffected by a low detection rate** — a gate-passed quotation is
verified against the transcript itself, not against the auditor. That asymmetry is what
band B exploits.

**`MAX_UNRESOLVED_UPPER_A = 0.20`** on the upper bound of the unresolved rate.

### 7.3 The gate

| Band | Requires | Outcome | Permits |
|---|---|---|---|
| **A** | detections ≥ **59/63** and agreement ≥ **138/154** and unresolved ≤ **21/154** | `PROCEED_WITH_ABSENCE_CORROBORATION` | `ABSENCE_CORROBORATED` — **only where §7.4 is also satisfied** — printed with the residual miss rate |
| **B** | detections ≥ **40/63** and agreement ≥ **90/154**, band A not met | `PROCEED_DETECTION_ONLY` | **only** `AUDITOR_DID_NOT_FIND_EVIDENCE`; "corroborated", "confirmed" and "validated" are unavailable for absences. Contested cells stand. |
| **C** | anything below band B on either axis | `STOP_AUDITOR_UNUSABLE` | Stage 2 is **not** submitted; the calibration failure is itself the reported result and no absence figure is revised |

Both axes must clear a band; the lower of the two governs. Every reported figure carries
its Wilson interval, and the denominator is always printed.

### 7.4 Subtheme-specific eligibility **[C5]**

**Band A is necessary but not sufficient.** A global pass shows the auditor works *across*
the codebook; it does not show the auditor can recognise any *particular* subtheme. An
auditor could reach band A while being blind to one definition — and every absence for
that definition would then be "corroborated" by an instrument demonstrably unable to
detect it.

An `ORIGINAL_GEMINI_ABSENCE` may be labelled `ABSENCE_CORROBORATED` only if **both** hold:

1. the global gate reaches band A; **and**
2. the auditor detected the designated `ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED` control
   for **that same subtheme**, under the reconciled two-repetition rule.

If a subtheme's designated control is **not detected** or is **unresolved**, every
non-detection for that subtheme remains `AUDITOR_DID_NOT_FIND_EVIDENCE` — **even under a
global band A**.

**Contested cells are untouched.** A valid contested absence with gate-passed evidence
remains contestable regardless of this rule, because it is verified against the transcript
rather than against the auditor. That holds under band B and band C too.

The rule is enforceable because coverage is complete: the 22 designated cases include
exactly **one positive control per subtheme, all 11 subthemes**.

| Control verdict for the subtheme | Status | Corroboration |
|---|---|---|
| `AUDITOR_EVIDENCE_FOUND` | `SUBTHEME_CONTROL_DETECTED` | permitted (with band A) |
| `AUDITOR_DID_NOT_FIND_EVIDENCE` | `SUBTHEME_CONTROL_NOT_DETECTED` | **blocked** |
| `AUDITOR_UNRESOLVED` | `SUBTHEME_CONTROL_UNRESOLVED` | **blocked** |
| no control returned | `SUBTHEME_CONTROL_MISSING` | **blocked** |

A test drives the global gate to exactly 59/63 and 138/154 — band A — with one complete
subtheme control failing, and asserts that subtheme's absences cannot become
`ABSENCE_CORROBORATED` while the other ten subthemes corroborate normally.

### 7.5 What calibration can and cannot establish

The detection rate on originally-present quote-verified cells is **the only quantity
scored against an external warrant**. The concurrence rate on `ORIGINAL_GEMINI_ABSENCE`
cells is not a specificity and not an accuracy — those cells are the original coder's
decisions. Unresolved cells are their own category and are never redistributed into
either direction.

---

## 8. Two stages

**Stage 1 — calibration.** 14 documents, 154 cells, 28 requests. The 22 designated cases
(11 `ORIGINAL_GEMINI_PRESENT_QUOTE_VERIFIED` and 11 `ORIGINAL_GEMINI_ABSENCE`, all 11
subthemes, deliberately including the adjacent-code families A.1/A.2/A.3, B.1–B.4 and
C.1–C.3) guarantee coverage.

**Stage 2 — complete audit.** The remaining 21 documents, submitted only if the gate
returns band A or B. Stage 1 documents are not re-sent: their requests would be
byte-identical, so the cache key matches and the stored result is reused.

Cache key = SHA-256 over classification, stage, blinded document id, rendered document
hash, candidate-code-set hash, prompt hash, schema hash, model, effort, execution mode and
repetition index. **70 keys, 0 collisions**, verified.

---

## 9. Sensitivity: two separate outputs **[C4]**

Participant breadth and across-group recurrence are different quantities and take
different treatments. They are reported as **two outputs and are never merged**.

### 9.1 `participant_breadth_bounds` — LOWER / MID / UPPER

| Treatment | Contested cell scored as |
|---|---|
| **LOWER** | 0 — original coding unchanged. **Primary; the reported result does not move.** |
| **MID** | **1/n** for that document |
| **UPPER** | **deduplicated union** of speakers supported by evidence-gated quotations **across both repetitions**, over n |

### 9.2 `across_group_recurrence_sensitivity` — ORIGINAL vs CONTESTED_AS_PRESENT

Recurrence is a count of focus groups, so **there is no MID treatment**: a focus group
either counts or it does not, and there is no fractional group. Only `ORIGINAL` (primary)
and `CONTESTED_AS_PRESENT` exist.

### 9.3 Frozen speaker handling

- **MID = 1/n.** A contested cell warrants exactly one participant by construction.
- **UPPER = |union of gate-passed speakers across both repetitions| / n**, deduplicated.
- **Speaker intersection is recorded separately** for every contested cell, and is
  **never used as a bound**.
- **Failed or unresolved evidence contributes no speaker**, in either direction. A
  gate failure emits no speaker at all, so it cannot enter a union.
- A contested cell with an empty union raises an error rather than silently scoring 1/n;
  so does an intersection that is not a subset of its union, and a zero denominator.
- `UNRESOLVED` cells enter no treatment in either output.

The width of the band, together with the unresolved count, is the honest statement of how
much the results depend on the absence decisions.

---

## 10. Estimated volume and cost — no call has been made

The token model is **measured, not assumed**: ordinary least squares over the 121
successful requests of batch `msgbatch_01RgXvJrPHyUZfaTimUzw1Bf` (same model, execution
mode, effort and corpus), prompts re-rendered from the stored job manifest and regressed
on the recorded per-request `input_tokens`.

```
input_tokens = 1.7502 × words + 1620          R² = 0.9989,  n = 121
```

**Caveat:** the fit covers prompts of 1,135–3,387 words. This audit's prompts are roughly
8,300 words, so the slope is **extrapolated**, and the intercept absorbs a response schema
of a different size. A ±20% band is carried on every figure. These are estimates, not
measurements.

| Stage | Docs | Requests | Assessments | Input tok | Output tok | Cost | Band |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 — calibration | 14 | 28 | 308 | 438,342 | 64,680 | $1.90 | $1.52–2.29 |
| 2 — incremental | 21 | 42 | 462 | 708,556 | 97,020 | $2.98 | $2.39–3.58 |
| **Total corpus** | **35** | **70** | **770** | **1,146,898** | **161,700** | **$4.89** | **$3.91–5.87** |

Of the 770 assessments, **520 are the absence universe** (260 × 2) and **250 are present
controls** (125 × 2).

Rates are the published list Batch rates, `$2.50 / $12.50` per MTok, verified 2026-08-02.
**Cost calculated at list rate, not necessarily the amount charged.** No Gemini rate is
quoted anywhere, because none has been verified.

---

## 11. Configuration

```
model              claude-opus-5
execution_mode     batch
effort             high
output_config      format: json_schema (verdict, turn_id, speaker, quotation,
                   reasoning, confidence — one entry per candidate)
temperature        NOT transmitted
top_p              NOT transmitted
top_k              NOT transmitted
repetitions        2 per request — two separately keyed stochastic repetitions of an
                   independent cross-model auditor
```

---

## 12. Outputs

**Produced now (pre-submission):**

| File | Contents |
|---|---|
| `AUDIT_PROTOCOL.md` | this document |
| `absence_universe.csv` | the 260 derived absence cells |
| `calibration_request_manifest.json` | opaque ids, hashes, request metadata only |
| `stage1_gate.json` | the exact gate, resolved to integer counts |
| `batch_manifest.json` | 35 requests, cache keys, blinding report, estimates |
| `sealed/calibration_reference_SEALED.json` | **SEALED** — original status and provenance |
| `sealed/sealed_document_mapping.json` | **SEALED** — blinded id → provenance |

**Specified, produced only after submission is approved:**

`calibration_results.json`, `calibration_scores.json`, `audit_results_long.csv`,
`absence_adjudication.csv`, `evidence_gate_report.json`,
`participant_breadth_bounds.csv`, `across_group_recurrence_sensitivity.csv`,
`ABSENCE_AUDIT_REPORT.md`.

---

## 13. Each correction fails under a planted violation

| Correction | Planted violation | Test asserts |
|---|---|---|
| **C1** gate | `THRESHOLD_A` swapped to 0.80 | the exact required count moves off 59; hard-coded counts would not |
| **C1** gate | the phrase the correction removed | absent from protocol, gate file and rules module |
| **C2** split | `original_status` injected into the public manifest | the purity check catches it |
| **C2** split | sealed directory pointed at a non-existent path | all 35 requests still build |
| **C2** split | builder source inspected | fails if it names a sealed path or answer-key field |
| **C3** language | the overstated phrasing injected | the checker catches it; the stripper that excises the ban definition is itself tested not to hide real prose |
| **C4** speakers | a paraphrased (gate-failed) quotation | contributes no speaker to the union |
| **C4** speakers | moderator-attributed evidence | contributes no speaker |
| **C4** speakers | contested cell with an empty union | raises, rather than silently scoring 1/n |
| **C4** speakers | intersection wider than its union | raises |
| **C4** outputs | both outputs compared | different names, disjoint treatment sets |
| **C5** eligibility | global gate driven to exactly 59/63 and 138/154 with one subtheme control failing | that subtheme's absences cannot become `ABSENCE_CORROBORATED`; the other ten do |
| **C5** eligibility | subtheme control unresolved, or never returned | equally blocked |
| **C5** eligibility | contested cell under a failed control, and under bands B and C | stays `ABSENCE_CONTESTED` |
| **C6** intervals | caveat text inspected | names clustering, dependence and anticonservatism; reaches gate file and protocol |
| **C7** per-cell claim | the forbidden phrasing injected | the checker catches it; the stripper excising the ban definition is itself tested not to hide real prose |

---

## 14. Stopping points

1. **Universe derivation reconciles.** ✅ 260, derived; mutation-tested.
2. **Blinding, manifests, frozen rules and the exact gate built; estimates reported; no
   API call.** ✅ **← here, for the second time, after the four corrections**
3. Stage 1 submitted and scored against the gate in §7.3.
4. Stage 2 — only on band A or B.
5. Sensitivity outputs computed; report written.

**Awaiting review before any request is sent.** The final heatmap, the workbook and the
reported products are untouched and stay untouched until the complete audit and the
sensitivity analysis have been reviewed.
