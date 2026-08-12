# Participant breadth and recurrence hierarchy similarity

**`PARTICIPANT_BREADTH_AND_RECURRENCE_HIERARCHY_SIMILARITY`**

**Status: EXPLORATORY.** Post-result operationalisation, built 2026-08-03T05:03:01.161797+00:00 from the existing Tier-1 results. No API call, no new coding, no researcher task.

> This operationalisation evaluates whether themes have a similar hierarchy of participant breadth and across-group recurrence. It does not establish that the themes had equivalent interpretive importance, centrality or meaning.

Reach-based automated salience is kept **separate from the researcher decision `CENTRALITY_NOT_ASSESSED`**, which this analysis neither uses nor supersedes.

---

## 1. Why the previous metric is not the headline

`tier1_salience_hierarchy` correlated ranks over subthemes present on **both** sides. That silently deletes every synthetic omission from the comparison, so a run that reproduced two of a human group's nine themes could score a perfect correlation on those two.

It is **retained** and reclassified as **`LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC`**. It is never reported as a primary result.

| | Legacy shared-only | This operationalisation |
|---|---|---|
| Universe | subthemes present on both sides | **every subtheme the human FG expressed** |
| Synthetic omission | dropped from the comparison | **scored 0** |
| Defined in | **16 of 30** sessions | **27 of 30** sessions |
| Primary statistic | Spearman | **Kendall tau-b**, tie-aware |

Across the 30 runs, **148 of 216 scored cells are human themes the synthetic run did not produce.** The legacy metric discarded all of them; here they carry their proper weight as zeros.

---

## 2. Group-level participant-breadth hierarchy

For each human FG × synthetic run: the universe is every subtheme the human focus group expressed. Human score is human participant reach. Synthetic score is observed reach where the theme is present, **0 where it is genuinely absent**, and null only where a result or denominator was not measured — of which there are **none** in this corpus.

**Table 1. Kendall tau-b per focus group and condition. Median of three replicates, with the full range shown.**

| FG | Condition | R1 | R2 | R3 | Median | Min | Max | Defined |
|---|---|---|---|---|---|---|---|---|
| fg1 | demographics-only | 0.1345 | 0.0000 | 0.1345 | **0.1345** | 0.0000 | 0.1345 | 3/3 |
| fg1 | enriched | -0.2941 | -0.1765 | -0.2941 | **-0.2941** | -0.2941 | -0.1765 | 3/3 |
| fg2 | demographics-only | -0.3043 | -0.1925 | -0.1890 | **-0.1925** | -0.3043 | -0.1890 | 3/3 |
| fg2 | enriched | -0.2843 | 0.0000 | -0.1925 | **-0.1925** | -0.2843 | 0.0000 | 3/3 |
| fg3 | demographics-only | 0.2704 | 0.2704 | 0.2704 | **0.2704** | 0.2704 | 0.2704 | 3/3 |
| fg3 | enriched | 0.5422 | 0.5074 | 0.3916 | **0.5074** | 0.3916 | 0.5422 | 3/3 |
| fg4 | demographics-only | — | — | — | **—** | — | — | 0/3 |
| fg4 | enriched | -0.2697 | 0.1818 | -0.2697 | **-0.2697** | -0.2697 | 0.1818 | 3/3 |
| fg5 | demographics-only | 0.0000 | 0.0000 | -0.3086 | **0.0000** | -0.3086 | 0.0000 | 3/3 |
| fg5 | enriched | 0.1361 | 0.4330 | -0.3086 | **0.1361** | -0.3086 | 0.4330 | 3/3 |

Correlations are **not averaged**; the median is the summary and the minimum and maximum are printed so no replicate is hidden.

**3 of 30 runs are undefined**, all for the same reason: `SYNTHETIC_SIDE_CONSTANT` — the synthetic run produced no variation in reach across the human themes, so no hierarchy exists to compare. Every one is FG4 demographics-only, consistent with that cell's known subtheme-level result. An undefined correlation is reported as undefined, never as zero.

**Table 2. Paired difference, enriched minus demographics-only, using each cell's median. Five focus groups — never fifteen sessions.**

| FG | Enriched median | Demographics-only median | Difference | Direction |
|---|---|---|---|---|
| fg1 | -0.2941 | 0.1345 | -0.4286 | demographics-only |
| fg2 | -0.1925 | -0.1925 | 0.0000 | tie |
| fg3 | 0.5074 | 0.2704 | 0.2370 | enriched |
| fg4 | -0.2697 | — | — | undefined |
| fg5 | 0.1361 | 0.0000 | 0.1361 | enriched |

Direction counts: **enriched 2, demographics-only 1, tie 1, undefined 1**. Median difference 0.068, range -0.4286 to 0.237 over the 4 defined pairs.

**This is a direction and a distribution, not a test.** Four defined pairs cannot support inference and none is offered.

**Sensitivities**, reported per run in `salience_hierarchy_per_run.csv`: Spearman on average ranks, normalised mean absolute reach difference, and tie-aware top-theme overlap.

---

## 3. Study-level recurrence hierarchy

Each row is **one complete realisation of the study** — five focus groups at a single replication index. The fifteen sessions of a condition are never treated as fifteen independent groups.

**Table 3. Recurrence hierarchy against the human study.**

| Condition | Replicate | tau-b on n_FGs_present | tau-b on mean reach | Top-3 overlap (n_FGs) | Top-3 overlap (mean reach) |
|---|---|---|---|---|---|
| enriched | R1 | 0.2125 | 0.1005 | 0.2857 | 0.2000 |
| enriched | R2 | 0.4272 | 0.3660 | 0.2857 | 0.2000 |
| enriched | R3 | 0.1027 | 0.0462 | 0.2857 | 0.2000 |
| demographics-only | R1 | 0.1349 | 0.0407 | 0.2500 | 0.1667 |
| demographics-only | R2 | 0.3287 | 0.2312 | 0.2857 | 0.2000 |
| demographics-only | R3 | 0.3337 | 0.2582 | 0.4286 | 0.4000 |

Median tau-b on recurrence: enriched 0.2125, demographics-only 0.3287. All six values are positive but modest, and the two conditions overlap.

Tie-aware top-3 overlap sits between 0.25 and 0.43 throughout: the subthemes that recur most across human groups are only partly the ones that recur most across synthetic groups.

A recurrence heatmap is in `salience_recurrence_heatmap.png` and in workbook sheet `10_Salience_Hierarchy`.

---

## 4. Union sensitivity

As a secondary sensitivity the comparison is repeated over the union of human and synthetic themes, reported per run as `union_kendall_tau_b`.

**This variant mixes fidelity with synthetic thematic proliferation** — a synthetic run that produces themes the human group did not is rewarded on coverage while being penalised on hierarchy, and the two effects are not separable in a single coefficient. It is never a primary result.

---

## 5. Verification performed before any workbook write

- **125 reach rows** checked against `thematic_reach_long.csv`, including that `reach == voiced_by_n / participants_n` and that every denominator is positive.
- **260 true absences** scored 0, matching the presence table exactly.
- **0 unmeasured nulls**, and a test asserts no null is ever coerced to 0 and no true absence is ever left null.
- The primary universe is complete for every run: scored + unmeasured equals the number of human-present themes, and recovered + zero equals scored.
- Edge cases tested directly: ties, true absence, unmeasured, and all-equal ranks (undefined, never 0).

---

## 6. Limitations

- **One human transcript per focus group.** Every human score rests on a single realisation; there is no human-side replicate against which to judge its stability.
- **Reach depends on quotes the evaluator selected.** Participant breadth is counted from attributed quotations, so it inherits the evaluator's selection.
- **A representative quotation is not an exhaustive enumeration.** The coding asked for representative evidence, so reach may understate how many participants touched a theme.
- **Group sizes differ.** Denominators are 5, 4 and 3 participants across cells, so reach is a proportion over unequal bases and small groups move in coarser steps.
- **Ties are abundant with only 11 subthemes.** Kendall tau-b is tie-aware, which is why it is the primary statistic, but many cells share values and the resolution of any hierarchy is correspondingly low.
- **The forced-silence implementation caveat applies.** 14 canonical enriched runs executed the pre-fix engagement path, and reach depends on who spoke — recorded on every row of `thematic_reach_long.csv` and in the frozen specification.
- **Post-result and exploratory.** This operationalisation was specified after the main results were known and was not pre-registered in this form.

---

## 7. Outputs

| File | Rows | Contents |
|---|---:|---|
| `salience_hierarchy_per_run.csv` | 30 | one row per human FG × synthetic run |
| `salience_hierarchy_by_fg_condition.csv` | 10 | median, min, max and each replicate |
| `salience_hierarchy_study_replicates.csv` | 6 | one row per complete study realisation |
| `salience_hierarchy_theme_scores_long.csv` | 385 | every score with its status |
| `salience_hierarchy.json` | — | full derivation including verification |
| `salience_recurrence_heatmap.png` | — | recurrence heatmap |
| `FINAL_RESULTS_TABLES.xlsx` → `10_Salience_Hierarchy` | — | new sheet; no existing sheet modified |

This analysis is independent of the inductive-accumulation work, which remains at NO-GO. The two are not combined.
