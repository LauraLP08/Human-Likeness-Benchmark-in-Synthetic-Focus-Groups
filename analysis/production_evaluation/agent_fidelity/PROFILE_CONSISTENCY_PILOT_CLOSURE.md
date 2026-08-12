# Profile-consistency pilot — closure

**Job:** `msgbatch_01KstMdLsHQnjrRciHDEdFfG` — 26 provider requests, 256 adjudications
(120 real pairs + 8 fixtures, two repetitions). 256/256 returned; the union equals the
item manifest exactly.

**Status:**
`TECHNICAL_PILOT_GATE_PASS`
`AUDITOR_USABLE_FOR_EXPLORATORY_CORROBORATION_ONLY`
`SCREENER_NOT_DEMONSTRATED_TO_ENRICH_FOR_CONTRADICTIONS`

**`FULL_PROFILE_CONSISTENCY_AUDIT = DECLINED_AFTER_PILOT`.** The 682 remaining pairs were
never sent, and no further profile-consistency call will be made.

---

## 1. The governing gate criterion, and the rule that did not govern

The prospective criterion was **verbatim evidence validity ≥ 0.95**. Observed:
**0.9875** (3 invalid of 240 real adjudications). That criterion **passes**.

**POST-RESULT SCORER CORRECTION.** The first scorer treated any single non-literal quote
as a whole-pilot gate failure. That stricter rule was written after the results were seen
and cannot retroactively replace the frozen criterion. It has been withdrawn as a
governing rule.

The three affected decisions are now `UNRESOLVED_INVALID_EVIDENCE`: they enter no
substantive category, are not repaired, trigger no third call, and do not invalidate any
other decision.

### Effect on the reported counts — read this before citing figures

Applying the correction **changes the headline counts**, because the three
invalid-evidence items had previously been counted as corroborated:

| | before the correction | **after (authoritative)** |
|---|---:|---:|
| corroborated | 103 | **100 / 120** |
| unresolved | 17 | **20 / 120** |
| exact agreement | 0.8583 | **0.8333** |

Unresolved breaks down as 15 disagreements + 3 `UNRESOLVED_INVALID_EVIDENCE` +
2 `UNRESOLVED_INCOMPLETE_EVIDENCE`.

The figures 103 / 17 / 0.8583 describe the state *before* the correction ordered in §1
was applied. They should not be cited.

## 2. Fixtures

Four fixtures expected a `REJECT` verdict, but `REJECT` was never in the transmitted
schema enum, so the auditor could not return it however it behaved. They are
**`INVALID_AUDITOR_FIXTURE_SCHEMA_MISMATCH`**: excluded from the auditor's denominator,
retained as scorer tests, and never counted as substantive failures of the auditor.

> **4 / 4 executable substantive fixtures passed in both repetitions**, with four further
> fixtures excluded for schema incompatibility.

The planted contradiction was returned as `UNEXPLAINED_CONTRADICTION` in both
repetitions, twice; the context-not-contradiction case was never returned as a
contradiction; the explained change was classified correctly in both repetitions.

## 3. Results

| Stratum | n | corroborated | unresolved | candidate contradictions |
|---|---:|---:|---:|---:|
| screener-proposed | 60 | 54 | 6 | **0** |
| random controls | 60 | 46 | 14 | **2** |
| **total** | **120** | **100** | **20** | **2** |

`UNCERTAIN` rate 0. Disagreement matrix: 9 × `CONSISTENT | CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY`,
6 × `CONSISTENT | POSITION_CHANGED_WITH_EXPLANATION`.

**No claim is made that the control stratum contains a higher contradiction rate.** Two
cases out of sixty, against zero out of sixty, does not support that inference at this
sample size. What can be said is narrower: the screener was **not demonstrated to enrich
for contradictions**, because none of its proposed pairs produced one.

## 4. The two cases

Both are **`CROSS_REPETITION_CORROBORATED_CANDIDATE_CONTRADICTION`**.

| item | condition | stratum | focus group |
|---|---|---|---|
| `PC2-3ACF00CBD709C356` | enriched | control | fg3 |
| `PC2-F512A327E4B4F438` | demographics-only | control | fg1 |

They are **not** confirmed, validated, true or human-verified contradictions. Two
repetitions of the same auditor measure **the stability of that auditor**, not independent
validation. At least one of the two admits an alternative contextual reading — the
distinction between an unexplained contradiction and two statements about different
situations is exactly the boundary the disagreement matrix shows the auditor finds
hardest. Full quotes and reasoning are in `v2_profile_consistency_results.json` under
`per_item` and the sealed reference.

## 5. Schema correction

`n_corroborated_hyper_exact` → **`n_corroborated_unexplained_contradictions`** in the
results file and in the generator. No value changed. A test forbids hyper-exactness
metric names from appearing inside the profile-consistency block.

## 6. Why the full audit is declined

> The screener did not demonstrate enrichment for unexplained contradictions: no proposed
> pair yielded a corroborated candidate contradiction, while two emerged in the control
> stratum. Auditing the remaining screener-selected pairs would therefore be costly and
> would not support a corpus-wide prevalence estimate.

This is an **exploratory diagnostic, not a prevalence estimate**. 120 of 2,611 screened
pairs were adjudicated, drawn 20 per condition per role rather than as a probability
sample. **The 2,491 unaudited pairs are not negative.**
