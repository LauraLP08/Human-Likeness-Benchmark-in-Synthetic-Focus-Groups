# Exploratory out-of-Q3 transportability check — results

**Classification — `EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK`**

This is not a formal validation and its numbers are never pooled with the U01–U07/Q3 calibration or with the deductive analysis. It asks one narrow question: when the same emergent extraction and the same blinded cross-model adjudication are pointed at six supplementary units drawn from four *other* guide questions, does the procedure behave in a way that is descriptively compatible with what Q3 showed?

Built 2026-08-02T21:34:14.092392+00:00. Supersedes an earlier version computed over an incomplete correspondence space — see §2 and `PROTOCOL_DEVIATIONS.md`.

## 1. What was analysed

| Unit | Question | Human reference themes | Candidate themes | Pairs |
|---|---|---:|---:|---:|
| S01 | Q1 | 4 | 4 | 16 |
| S02 | Q4 | 3 | 7 | 21 |
| S03 | Q1 | 2 | 4 | 8 |
| S04 | Q4 | 1 | 4 | 4 |
| S05 | Q2 | 4 | 5 | 20 |
| S06 | Q5 | 4 | 6 | 24 |
| **total** | 4 questions | **18** | **30** | **93** |

The 18 human themes are the single-coder supplementary reference, frozen before any model ran and never edited by this check. Centrality and relevance remain `NOT_ASSESSED` throughout.

## 2. The correspondence space is now complete

An earlier version of this document computed recall and precision from **61 of the 93** possible within-unit pairs. The other 32 had been dropped by a deterministic similarity screener whose documented role is to *propose* pairs, never to decide one. Treating its exclusions as settled non-correspondences promoted a heuristic into an adjudicator, and made the recall band, the claim of zero unresolved human themes, and the closure of the classification unsupported at the time they were published.

All 32 omitted pairs have since been adjudicated under the same model, mode, effort, prompt, schema, blinding, categories and gates as the original 61. No historical decision was re-run or re-interpreted.

| Source | Confirmed match | Confirmed non-correspondence | Unresolved | Total |
|---|---:|---:|---:|---:|
| `ORIGINAL_SCREENED_61` | 19 | 35 | 7 | 61 |
| `COMPLEMENT_32` | 0 | 25 | 7 | 32 |
| **all 93** | **19** | **60** | **14** | **93** |

**What the 32 changed.** They produced no new confirmed matches, so recall did not move. They produced 25 further confirmed non-correspondences and 7 further unresolved pairs, and those unresolved pairs changed the precision picture substantially: the number of candidate themes that might yet correspond to a human theme rose from 1 to 5, widening the precision band from [0.6000, 0.6333] to [0.6000, 0.7667].

**What they also did is make the recall claim legitimate.** Under the screened set, the two unrecovered human themes had been judged against only 2 of 4 and 4 of 6 candidates in their units. Each has now been judged against its complete local universe, and every pair came back a confirmed non-correspondence. The same figure that was previously asserted is now earned.

## 3. Headline figures

| Metric | Value |
|---|---|
| Confirmed recall (lower bound) | **0.8889** (16/18) |
| Possible recall (upper bound) | **0.8889** |
| Strict confirmed precision | **0.6000** (18/30) |
| Possible precision (upper bound) | **0.7667** (+5 unresolved) |
| Exploratory adjusted precision, counting corroborated novelty | 0.9667 |
| Literal evidence attachment | 1.0000 (30/30) |

Theme-level states, from the complete universe:

| Side | State | n |
|---|---|---:|
| human | RECOVERED | 16 |
| human | CONFIRMED_NOT_RECOVERED | 2 |
| candidate | MATCHED | 18 |
| candidate | CONFIRMED_UNMATCHED | 7 |
| candidate | UNRESOLVED_POSSIBLY_MATCHED | 5 |

**The recall band is zero-width and this time that is a finding.** All 18 human themes were adjudicated against every candidate in their unit. 16 have at least one confirmed match; 2 — `S01::S01_slot_02`, `S06::S06_slot_03` — have a confirmed non-correspondence with every single candidate in their unit and nothing unresolved. No human theme sits in between, so there is no uncertainty for the band to express. Every unresolved pair in the study attaches to a human theme that is already recovered through another candidate.

**Precision is the weaker axis and carries a real band.** 18 of 30 candidates correspond to a human theme, 7 are confirmed to match nothing, and 5 hold at least one unsettled pair and could fall either way. The honest statement is the interval [0.6000, 0.7667], not a point.

Four of those open candidates — `S01::M3`, `S02::M6`, `S03::M2`, `S04::M4` — were separately judged `VALID_NOVEL_THEME` when shown the unit's complete reference inventory, while their pairwise correspondence against one specific reference theme stayed unsettled. Those are different questions and the tension is left standing rather than resolved by fiat: a corroborated novel theme is never converted into a human correspondence.

The adjusted figure of 0.9667 counts the 11 candidates a blinded auditor twice judged to be valid themes the human coder did not record. That is a claim about *the auditor's* reading, not evidence that the coder missed something — a single coder working to a defined scope is entitled to leave material uncoded. Read it as an upper envelope, not a correction to the reference.

## 4. By question

| Q | Units | Human | Cand. | Recall lower | Recall upper | Prec. lower | Prec. upper | Prec. band | Corrob. novel |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1 | S01, S03 | 6 | 8 | 0.8333 | 0.8333 | 0.5000 | 0.7500 | 0.250 | 4 |
| Q2 | S05 | 4 | 5 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.000 | 0 |
| Q4 | S02, S04 | 4 | 11 | 1.0000 | 1.0000 | 0.5455 | 0.7273 | 0.182 | 5 |
| Q5 | S06 | 4 | 6 | 0.7500 | 0.7500 | 0.5000 | 0.6667 | 0.167 | 2 |

Recall is at or above 0.75 in every question and reaches 1.00 in Q2 and Q4. Precision is the axis that moves, and it moves downward everywhere except Q2. The pattern has one straightforward reading: the extractor is generous. It recovers nearly everything the coder recorded and then proposes more besides — most visibly in Q4, where eleven candidates stand against four human themes.

**These four rows must not be compared with one another statistically.** Each rests on one or two units and between three and six human themes; a difference of one theme moves a per-question rate by 0.17 to 0.33.

## 5. Adjudication outcomes

| Stage | Outcome | n |
|---|---|---:|
| correspondence, all 93 pairs | HYBRID_CONFIRMED_NON_CORRESPONDENCE | 60 |
| correspondence, all 93 pairs | HYBRID_CONFIRMED_MATCH | 19 |
| correspondence, all 93 pairs | HYBRID_UNRESOLVED | 14 |
| candidate-only status | HYBRID_CORROBORATED_NOVEL | 11 |
| candidate-only status | HYBRID_UNRESOLVED_MACHINE_ONLY | 1 |
| granularity | CORROBORATED → LEGITIMATE_GRANULARITY_DIFFERENCE | 3 |

Granularity and candidate-only status were **re-derived from the complete 93-pair universe**. Because all 19 confirmed matches come from the original 61 pairs, the fragmentation and fusion multiplicities are unchanged and the set of candidates with no confirmed match is unchanged, so the complement created no new cases of either kind. Nothing already corroborated was re-audited.

14 of the 93 pairs remain `HYBRID_UNRESOLVED`: 9 because the two repetitions disagreed — typically `RELATED_BUT_DISTINCT` against a partial overlap, the boundary the rubric is least sharp at — 4 because a cited quotation was not literal, and 1 because a request errored and was retained rather than resent. They are listed individually in the tables workbook and none is resolved by inference.

## 6. Comparison with Q3 — two conclusions

Q3 reference, descriptive only: recall 0.6818, strict precision 0.8000. Those figures come from a different question, a different denominator (44 theme × unit instances) and a two-coder reference. They are a landmark, not a control condition, and no test is run against them.

Superseded historical result: `DESCRIPTIVELY_COMPATIBLE_WITH_Q3` — **PROVISIONAL_SUPERSEDED — based on 61/93 screened pairs**. Computed before the 32 omitted pairs were adjudicated, so its recall band and its claim of zero unresolved human themes rested on unjudged pairs. It is retained for the record and must never be cited as a current figure.

### 6.1 Frozen-rule classification

> **`DESCRIPTIVELY_COMPATIBLE_WITH_Q3`** — every question's recall band reaches 0.6818 and no unsupported theme recurs in >=2 units.

The rule was fixed before any result existed and keys on **recall only**. It has not been retrofitted to include precision, because rewriting a predefined rule after seeing the data would destroy the reason for freezing it. Applied to the corrected figures: unresolved share of human themes 0/18 = 0%, well under the 40% ceiling; mean per-question recall band 0.000, far under 0.35; every question's band at or above 0.6818; no unsupported theme corroborated in two or more units.

### 6.2 Balanced interpretation

> Recall-compatible with Q3 under the frozen rule, but with lower strict precision and greater thematic proliferation; evidence of transportability is mixed across fidelity dimensions.

| Dimension | Outside Q3 | Q3 landmark |
|---|---|---|
| Recall band | [0.8889, 0.8889] | 0.6818 |
| Strict precision | 0.6000 | 0.8000 |
| Precision band | [0.6000, 0.7667] | — |
| Candidates per human theme | 1.667 | — |
| Corroborated novel candidates | 11 | — |
| Unresolved pairs | 14 of 93 | — |

Strict precision outside Q3 sits 0.2000 below the Q3 landmark, and even the optimistic end of the precision band (0.7667) does not reach it. The frozen rule returns compatibility because it measures recall; it is not a summary of overall fidelity, and reporting it alone would overstate the finding. Both conclusions are reported together for that reason.

This check does **not** establish transportability, validate the procedure, or show the two settings to be equivalent. Six units, 18 human themes, one coder, no second human adjudicator, and an auditor rated `USABLE_FOR_CORROBORATION_ONLY` in the Q3 phase after producing non-verbatim quotations of its own.

### 6.3 Substantive conclusion

Across the six supplementary units, the automatic extractor recovered **16 of 18** human themes. The 2 it did not recover — `S01::S01_slot_02`, `S06::S06_slot_03` — were each adjudicated against **every** candidate theme in their own unit, and every one of those pairs returned a confirmed non-correspondence. Their absence is a measured result, not a gap in the adjudication.

Precision is the weaker axis. **Strict confirmed precision is 18/30 = 0.6000** — this is the primary precision estimate. **5 candidate themes hold a correspondence that is still uncertain**, so the possible upper bound is 23/30 = 0.7667. Both ends of that interval are below the Q3 landmark of 0.8000.

A further **11 candidates were corroborated by Claude as novel themes** — valid, distinct, and absent from the coder's record for that unit. That is **automated corroboration, not human validation**: no researcher adjudicated them, and a single coder working to a defined scope is entitled to leave material uncoded. The resulting **adjusted precision of 29/30 = 0.9667 is an optimistic exploratory ceiling, not the headline estimate** — the headline estimate is 0.6000.

By question, **Q2 was the cleanest case**: 4 human themes, 5 candidates, recall 1.0000 and precision 1.0000, with no unresolved pair and no surplus candidate. **Q4 showed the greatest thematic proliferation**: 11 candidates against 4 human themes, precision 0.5455 and 5 corroborated novel themes. The extractor's characteristic behaviour outside Q3 is generosity: it recovers nearly everything the coder recorded, and proposes a good deal more.

Taken together, the two conclusions in §6.1 and §6.2 stand as the finding. The frozen rule returns compatibility because it measures recall, and recall is genuinely comparable to Q3. Precision is not. **Neither equivalence nor established transportability is demonstrated**, and this check is not a validation of the procedure.

## 7. Cost

- audit round 1: 122 requests, 561,503 in / 86,340 out — `msgbatch_01RgXvJrPHyUZfaTimUzw1Bf`
- audit round 2: 30 requests, 162,598 in / 31,067 out — `msgbatch_01LSVnMiM5BgYx5kiHX5pBdp`
- complementary audit (32 omitted pairs): 64 requests, 289,964 in / 47,945 out — `msgbatch_01CkAwX2ruMRSV5yGRnxKfv6`
- **Total Claude: 1,014,065 in / 165,352 out → $4.60** at the verified list Batch rate.
- Gemini extraction, 14,005 in / 6,434 out → cost **not calculated**: no published Batch rate for `gemini-3.5-flash` was verified, and an unsourced rate would be worse than none. Gemini was **not** re-run for the complement.
- Calculated figures, not invoices. The Console is authoritative.

## 8. Limitations

- Six units, 18 human themes, one coder. Every rate here has an integer numerator small enough that a single reclassification moves it visibly.
- The human reference is single-coded. There is no inter-coder agreement figure for these units and none can be produced without new human work.
- Relevance and centrality are `NOT_ASSESSED` by methodological decision.
- The adjudicator is an LLM. It was blinded and required to agree with itself across two order-reversed repetitions with literal evidence, which is why 14 pairs and 1 candidate remain unresolved rather than forced.
- One round-1 request errored and was retained as unresolved rather than stopping the run, contrary to the stopping rule as written. Recorded as `PROTOCOL_DEVIATION_01`.
- The first published version of these metrics used an incomplete correspondence space. Recorded as `PROTOCOL_DEVIATION_02`.
- `literal_evidence_attachment_rate` = 1.0000 means every candidate carries a quotation verbatim in its own unit and not the moderator's. It says nothing about whether the theme is a warranted reading of that quotation.
- The frozen rule keys on recall only. A precision-keyed rule would return a different class on identical data — hence the balanced interpretation in §6.2.
