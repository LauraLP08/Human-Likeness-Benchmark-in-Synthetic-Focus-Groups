# Correction log — Level 2 coverage accumulation and lexical diagnostics

Records every claim withdrawn or reworded after the NO-GO review, with its replacement.
No API call was made, no human artefact was touched, and no deductive source metric
changed. All figures below are from `saturation_analysis.json` and
`lexical_analysis.json` as rebuilt.

---

## 1. Unit of accumulation — the defect that changed the numbers

| | Before | After |
|---|---|---|
| Unit | replicates unioned within each focus group, one curve per condition | **study replicate × condition**: one complete pass over FG1–FG5 at a single replication index |
| Curves | 3 (human, enriched, demographics-only) | **7** (1 human, 3 enriched, 3 demographics-only) |
| Enriched result | "reaches 9/11" | **4–7 of 11** per replicate (mean 5.67) |
| Demographics-only result | "reaches 6/11" | **4–6 of 11** per replicate (mean 4.67) |
| 9/11 and 6/11 | presented as condition repertoires | retained **only** as `CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS` |

**Withdrawn:** "Coverage accumulation flattens at different ceilings. Human transcripts
reach all 11 codebook subthemes, enriched reaches 9 and demographics-only 6."

**Replacement:** "A single study replicate recovers far less of the codebook than the
human reference. The human curve reaches all 11 subthemes; enriched replicates reach 4–7
and demographics-only 4–6, with overlapping ranges. The 9/11 and 6/11 figures are the
condition-wide maximum observed across 15 sessions, not what one study of five groups
recovers."

**Consequence for the condition comparison.** The two ranges now overlap, and the gap
between condition means (5.67 vs 4.67) is smaller than the spread across replicates
within either condition. The earlier framing implied a clean 9-vs-6 separation that a
realisable study would not experience.

---

## 2. Source shape

| Before | After |
|---|---|
| "31 runs × 11" | **35 documents (5 human focus groups + 30 synthetic runs) × 11 subthemes = 385 rows** |

The earlier count came from `physical_run`, which is empty for human rows and therefore
collapsed the five human focus groups into one value.

---

## 3. Between-replicate accumulation

**Withdrawn:** "Between-run saturation is not reached at three replicates in either
condition (+38.5% / +37.8% from one run to three)."

**Replacement:** "Coverage continued to increase through the third observed replicate;
the data do not establish how many replicates would be sufficient."

The percentage gains were computed over replicate-unioned cells and are not reported.

---

## 4. Plateau language

**Withdrawn:** "All three conditions flatten within five groups"; "the human curve reaches
80% at two groups and 90% at three" used as evidence of saturation.

**Replacement:** the endpoint of a curve is stated to be the total observed for that
replicate and explicitly **not** evidence of a plateau. Where a plateau is referred to at
all, the criterion is stated — mean increment to every later focus group below 0.5
subthemes — and is labelled **post hoc, arbitrary and non-substantive**. It supports
no conclusion. *(Round three removed the criterion from both drafts entirely; see §15.)*

---

## 5. Theme recurrence

| Before | After |
|---|---|
| "present in any replicate" used as the primary datum | per subtheme × per **study replicate**: human, enriched R1–R3, demographics-only R1–R3 |

The two subthemes never observed in any synthetic session (`B.3`, `C.2`) survive the
correction, and are now verifiable per replicate rather than only in aggregate.

---

## 6. Prevalence bands

**Withdrawn:** the 4/4/3 salience terciles and the claim "both synthetic conditions
recover the most prevalent human subthemes better than the least prevalent ones, and
enriched exceeds demographics-only in every tercile."

**Reason:** the split separated codes with identical human prevalence by alphabetical
order, so the tercile boundaries were an artefact of sorting.

**Replacement:** prevalence reported code by code. Tie-preserving bands (grouping exact
ties only) are retained in the artefact and marked exploratory.

---

## 7. Lexical distinctiveness

**Withdrawn:** "Synthetic agents' voices are markedly less differentiated than human
participants', sharing about twice the content vocabulary."

**Replacement, for the unadjusted diagnostic:** "The unadjusted vocabulary-overlap
diagnostic was higher in synthetic sessions, but the comparison remains potentially
confounded by unequal speaker output."

**Sensitivity analysis added.** Equal per-participant token budgets (100/200/400), up
to ten deterministic offsets each used exactly once (see §12), three tokenisation arms, and three measures on the identical
budgeted samples — Jaccard, Jensen–Shannon distance, cosine similarity. No embeddings.

| | Result |
|---|---|
| Decisive specifications (n_fg = 5 in every condition) | **12 of 12 agree** |
| Excluded as thin (human side rests on 1 of 5 FGs) | 9 |
| Effect of equalisation | enriched-minus-human gap falls from +0.1498 to +0.0490 *(revised in §12; +0.0489 before the offset fix)* |

**Reportable statement:** the direction survived every specification that could bear it.
It is a sensitivity check on five focus groups, not a validated measure of voice, and the
residual limitation is recorded: equalising tokens does not equalise topical dispersion.

---

## 8. Lexical diversity

| Before | After |
|---|---|
| "MATTR is the length-insensitive figure" | "MATTR is **less length-sensitive** than raw TTR — not length-insensitive" |
| one window (100) | windows **50, 100 and 200**; direction stable across all three |
| implied support for the voice finding | stated to be a diversity diagnostic and **not evidence about voice distinctiveness** |

---

## 9. Hyper-exactness

Unchanged in substance and reaffirmed: the numeral count is a **descriptive proxy only**
and does **not** discharge the registry indicator, which remains
`NOT_IN_REPORTED_INSTRUMENT`. The earlier draft already said this; the
framework-coverage sentence has been corrected so the indicator is not counted as
addressed.

---

## 10. Temporal transparency

Added to both artefacts and to both drafts:

> The general indicators appear in the original methodology, but these specific
> operationalisations — study-replicate accumulation, exhaustive ordering, the plateau
> criterion, tie-preserving bands, token budgeting, the subsample scheme, the MATTR
> window set — were finalised **after the main results were known**. They are
> **exploratory** and were not pre-registered in this form.

---

## Integrity

13 artefacts verified byte-identical before and after: the five deductive source tables
(`thematic_code_presence_long.csv`, `primary_effects_by_fg.csv`,
`primary_effects_summary.csv`, `structural_interaction_metrics_long.csv`,
`per_run_metrics.csv`), the four closed final products, and the four human artefacts
(`Transportability_Emergent_SingleCoder.xlsx`, `supplementary_human_reference.json`,
`Emergent_Matching_Q3_RESEARCHER_V2.xlsx`, `Clustering_U01_U07.xlsx`).

`output/session_logs/` untouched at 131 entries. The methodology `.docx` was never
written to. Full suite: 1176 passed, 1 skipped.

---

# Second correction round

## 11. Claim matrix C26 contradicted C28–C35

**Withdrawn:** "Level 1 thematic fidelity and Level 3 structural are reported; Level 2
saturation, Level 3 interpretive and Level 4 agent fidelity are not… saturation metrics
remain `EXPLORATORY` with no result rows."

That row was written before the Level 2 and lexical work existed and was never revised,
so the matrix asserted in C26 that Level 2 had no results while C28–C35 reported them.

**Replacement** distinguishes six statuses: Level 1 *reported*; Level 2 fixed-codebook
coverage accumulation *addressed exploratorily*; Level 3 structural *reported*; Level 3
interpretive *retained and not reported*; Level 4 lexical distinctiveness *addressed
exploratorily*; the remaining three Level 4 indicators *not substantively reported*.
Status changed from `SCOPE GAP` to `PARTIAL COVERAGE — specified in full, implemented in
part; two areas addressed exploratorily`.

A regression test (`test_c26_does_not_contradict_the_level2_claims`) fails if C26 again
asserts that Level 2 is unreported or has no result rows while C28–C35 are present.

## 12. Repeated subsample offsets

**Defect.** `_offsets()` returns only distinct start positions, but `_budgeted_overlap()`
cycled them (`offs[s % len(offs)]`) to reach a fixed count of ten and recorded
`n_subsamples = 10` regardless. A speaker with few feasible positions therefore had the
same window resampled and counted as new evidence, which understates the spread.

**Concrete case.** Human FG2, budget 100, both content-tokenisation arms: speaker
`mm_fg2_bilal` has 104 tokens, so only **5** distinct offsets exist (`[0,1,2,3,4]`). Each
was used twice.

**Fix.** The number of distinct subsamples is capped by the least well-supplied speaker;
every speaker's offsets are recomputed at exactly that count, so each offset is used once
and none repeats. Now recorded per session: `n_requested_subsamples`,
`n_unique_subsamples`, `offsets_used` per participant, `offset_step_per_speaker`,
`windows_overlap_per_speaker`, `any_windows_overlap`, `limiting_speaker`, and
`subsamples_were_padded_by_repetition: false`.

Mean, SD, min and max are computed over unique windows only. The SD key is named
`sd_across_unique_windows` and carries an `independence_note`: overlapping slices of one
stream are **not** independent observations, and no confidence interval or p-value is
derived from them. A test asserts the measure blocks expose no CI, standard-error or
p-value keys.

**Observed distribution of `n_unique_subsamples`** across 280 feasible session ×
arm × budget cells: 10 in 276 cells, 5 in 2, 4 in 1, 3 in 1. No real session degenerates
to a single feasible offset, so that boundary is tested directly against the production
functions instead.

### Before / after — every lexical figure

Six figures changed, all on the human side of the two content arms at budget 100 —
precisely the specifications where FG2's short speaker was being resampled.

| Figure | Before | After |
|---|---|---|
| `content_min3_nostop@100::jaccard` human | 0.1139 | **0.1138** |
| `content_min3_nostop@100::jensen_shannon_distance` human | 0.8701 | **0.8703** |
| `content_min3_nostop@100::cosine_similarity` human | 0.2805 | **0.2800** |
| `content_min1_nostop@100::jaccard` human | 0.1128 | **0.1127** |
| `content_min1_nostop@100::jensen_shannon_distance` human | 0.8715 | **0.8716** |
| `content_min1_nostop@100::cosine_similarity` human | 0.2773 | **0.2770** |

**Unchanged:** every enriched and demographics-only figure; all unadjusted Jaccard
figures; all MATTR and TTR figures; the numeral proxy; and the verdict —
**12 of 12 decisive specifications still agree**, 9 still excluded as thin,
`unadjusted_direction_confirmed` still `True`.

**One headline number moved:** the budget-equalised enriched-minus-human gap at 100
tokens, quoted in both drafts, changes from **+0.0489 to +0.0490**. The unadjusted gap
(+0.1498) is unchanged. (The value 0.0489 still appears in the drafts as the *enriched
numeral density per 1,000 words* — an unrelated coincidence.)

## 13. Meaning-saturation wording

**Withdrawn:** "meaning saturation … requires a judgement about whether an issue is fully
understood, which no automated method supplies."

**Replacement, used in the Results draft, Discussion draft and traceability index:**
"meaning saturation was not assessed in this study and cannot be inferred from
fixed-codebook coverage counts."

## 14. Plateau criterion — status at the end of round two

At the end of round two the criterion was labelled **post hoc, arbitrary and
non-substantive**, and it supported no conclusion, no synthesis item and no claim-matrix
result field.

**Correction to this entry.** An earlier version of §14 stated that the criterion
"remains in the artefact and in the traceability index only". That was inaccurate when
written: the criterion was still quoted in the body of both drafts — Results §4a.1 ("On
the shape of the curves") and Discussion §4a ("No plateau is claimed"). It was labelled
in both places, but it was present. Round three removed it; see §15.


---

# Third correction round — documentation cleanup

## 15. Plateau criterion removed from the drafts

**Withdrawn from the body of Results and Discussion:** the criterion itself — "mean
increment to every later focus group below 0.5 subthemes" — together with the sentences
that introduced it ("Where a plateau is referred to at all, the criterion is stated
explicitly…"). It was also removed from the list of post-hoc operationalisations in the
Results §4a status paragraph.

**Retained** in `saturation_analysis.json` under `plateau_criterion`, where it carries
its own status field, and in `RESULTS_TRACEABILITY_INDEX.md`, where it is now flagged
**`POST_HOC_ARBITRARY_NON_SUBSTANTIVE`** and explicitly noted as absent from the drafts
and as supporting no claim. It exists for audit only.

**What the drafts now say about curve shape**, and nothing more:

- the endpoint of a curve is the total observed for that replicate and does not
  demonstrate a plateau;
- neither code saturation nor meaning saturation was assessed;
- the data do not establish how many replicates would be sufficient.

Claim-matrix row C32 already recorded "No plateau claimed" and was not changed.

**No figure, analytic script, human artefact or source metric was touched in this
round.** `saturation_analysis.py` and `lexical_analysis.py` are unchanged, so
`saturation_analysis.json` and `lexical_analysis.json` are byte-identical to round two.
