# Hyper-exactness: blinded contextual audit — result

**Classification:** `LLM_ASSISTED_EXPLORATORY_CONTEXTUAL_AUDIT`
**Jobs:** `msgbatch_0147xfGjpZLEzaz2X4sK9JHH` (original, 24 provider requests) and
`msgbatch_014Uk1AkMuX6GTRy5z13HPGL` (`TECHNICAL_TRUNCATION_REPAIR`, 5 requests).
**Artefacts:** `v2_hyper_exactness_results.json`, `v2_hyper_exactness_items_blinded.json`,
`v2_hyper_exactness_sealed_reference.json`, the two manifests, and the two job records.

---

## Result

> **No corroborated hyper-exactness case was identified among the 127 audited corpus
> turns. This is a detected lower-bound result, not evidence of absence across the full
> 1,301-turn corpus. The 1,174 unaudited turns are not classified as negative.**

### Separated reporting

| Stratum | n | corroborated | unresolved | hyper-exact |
|---|---:|---:|---:|---:|
| detector-proposed candidates | 67 | 64 | 3 | **0** |
| `RANDOM_NONDETECTED_CONTROL_TURNS` | 60 | 57 | 3 | **0** |
| **audited universe** | **127** | **121** | **6** | **0** |

- corroborated: **121 / 127**
- unresolved: **6 / 127** (5 disagreements + 1 `UNRESOLVED_INCOMPLETE_EVIDENCE`)
- exact agreement between repetitions: **0.9528**
- fixtures: **excluded from every rate**
- corpus-wide prevalence estimate: **none produced**

Corroborated categories, candidates: `ORDINARY_EVERYDAY_SPECIFICITY` 53,
`PLAUSIBLE_PERSONAL_RECALL` 11. Controls: 44 and 13.

By condition (corroborated). Candidates — enriched 25/5, demographics-only 21/3, human
7/3. Controls — enriched 18/2, demographics-only 13/7, human 13/4.

Disagreement matrix: 4 × `ORDINARY_EVERYDAY_SPECIFICITY | PLAUSIBLE_PERSONAL_RECALL`,
1 × `ORDINARY_EVERYDAY_SPECIFICITY | UNCERTAIN`. No disagreement crossed into a
hyper-exact category. `UNCERTAIN` rate 0.0079.

### Technical validation fixtures — 8 / 10 correct in both repetitions

Fixtures govern the technical gate only and enter no rate.

| Fixture | expected | returned |
|---|---|---|
| `HXF-EPI-2` | `IMPLAUSIBLY_PRECISE_EPISODIC_RECALL` | `HYPER_EXACT_STATISTICAL_CLAIM`, then correct |
| `HXF-UNC-1` | `UNCERTAIN` | `ORDINARY_EVERYDAY_SPECIFICITY`, then correct |

The first miss is a confusion between two categories that are **both hyper-exact**; the
second crosses the boundary between hyper-exact and not. All four hyper-exact fixtures
were identified as hyper-exact in both repetitions.

### What this result does not say

- It does not say that no hyper-exactness exists.
- It does not say that the detector missed none.
- It is not a statement about specificity.
- It is not a validated absence.

The audited universe is 127 of 1,301 participant turns, and the 60 controls are 20 per
condition rather than a probability sample, so the only reportable quantity is
`DETECTED_LOWER_BOUND_RATE`.

Numeral density remains `NUMERAL_DENSITY_DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS`.

---

## Amendment A — `UNRESOLVED_INCOMPLETE_EVIDENCE`

**Status: POST-RESULT AMENDMENT. This rule was formalised AFTER the case was observed in
the returned data. It was not pre-specified.**

> A decision that carries a category and localisable evidence but leaves a required
> reasoning field empty is retained as `UNRESOLVED_INCOMPLETE_EVIDENCE`. It does not
> trigger a third call, it does not enter a substantive category, and it does not
> invalidate other valid decisions.

**Why the rule was needed.** The frozen gate-failure triggers are exactly three:
non-literal quote, wrong speaker, invalid turn id. One returned decision had a valid
category and a literal quote but an empty `justification`. The first scorer counted that
as a gate failure, which would have blocked an audit of 274 adjudications over a single
missing prose field. Treating it as complete would have been worse: a category with no
stated reasoning is not an adjudication.

**Effect on this audit.** One item moved from corroborated to
`UNRESOLVED_INCOMPLETE_EVIDENCE`, lowering exact agreement from 0.9606 to **0.9528** and
raising unresolved from 5 to 6. The reported figures are the post-amendment ones.

---

## Amendment B — `TECHNICAL_TRUNCATION_REPAIR`

`max_output_tokens` was sized at 1024 + 260 per item, giving 4,144 for a batch of twelve.
Each decision carries a verbatim quote of up to 220 words plus three prose fields, so a
full batch needs several times that. Five of twenty-four requests were cut mid-string and
returned unparseable JSON, taking 60 adjudications with them.

The only change in the repair was `max_output_tokens` 4,144 → 16,384. Prompt, schema,
items, item order, model and effort were identical. The nineteen intact requests were
**reused as returned and never resent**. The scorer merges the two jobs and discards a
truncated original only for the custom_ids that were repaired.

This is a sizing defect in the request builder, not an auditor failure.

---

## Traceability

- Retrieval is by `custom_id`, never by response position.
- Every decision was validated against the item it claims to answer: literal quote, exact
  `turn_id`, exact opaque speaker.
- The union of returned adjudications equals the item manifest exactly: 274 / 274.
- Blinding: no payload carried condition, focus group, replicate, human/synthetic status,
  model, profile, run name or detector stratum. Candidates and controls were
  indistinguishable in the prompt.
- Repetition rules applied: agreement → `CORROBORATED`; disagreement → `UNRESOLVED`; a
  single `UNCERTAIN` repetition kept and never converted to absence; no third call; no
  confidence or majority resolution.
