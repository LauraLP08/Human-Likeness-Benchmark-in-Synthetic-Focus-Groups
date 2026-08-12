# Main figure — Theme accumulation across focus groups

**Figure:** `inductive_theme_accumulation_main.png`
**Script:** `render_inductive_theme_accumulation_main.py`
**Plotted values:** `inductive_theme_accumulation_main.csv`
**Tests:** `tests/test_main_accumulation_figure.py`

This is the reader-facing figure. The technical identifiers are recorded here rather than
on its face.

## Provenance

| Item | Value |
|---|---|
| Panel A source | `analysis/production_evaluation/inductive_curves/inductive_curves_v2_full.json` |
| Panel B source | `analysis/production_evaluation/inductive_curves/inductive_endpoints_by_replicate.csv` |
| Scenario | `CANONICAL_RESOLVED_LOWER` |
| Analysis label | `LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION` |
| Panel A metric | `mean_cumulative_by_position` ÷ `endpoint`, per realisation |
| Panel B metric | `endpoint`, per question and realisation |
| Narrative-support metric | `mean_new_at_position[-1]` |
| Technical supplement | `analysis/production_evaluation/inductive_curves/inductive_theme_accumulation.png` (five per-question panels) |
| Narrative section | `analysis/production_evaluation/inductive_curves/SATURATION_SECTION.md` |

No API call and no recomputation: the script reads the frozen artefacts and draws them.
Panel B reads the endpoint table and cross-checks every value against the curve JSON;
a disagreement between the two raises rather than drawing
(`test_a_drift_between_the_two_endpoint_sources_is_detected`).

## Panel A — two construction rules

1. **Percentages are taken within a study realisation** and only then summarised across
   realisations. Replicates are never pooled before a percentage is computed. The
   synthetic line is the median of R1–R3 and the band is their full min–max range.
2. **Q4 ends at four focus groups.** When the five questions are combined, Q4 contributes
   its position-4 value again at position 5 — it holds its endpoint. It is neither
   dropped nor extrapolated. `test_q4_holds_its_endpoint_at_position_five` plants the
   dropped-Q4 alternative and requires it to differ from what is plotted.

The combined quantity in Panel A is a **sum of question-specific repertoire endpoints
within each study realisation**. It is not a count of distinct themes in the study:
cluster identifiers belong to a separate taxonomy for each question.

## Panel B — final classified repertoire by guide question

`CANONICAL_RESOLVED_LOWER`. Endpoints as recorded in the authoritative table.

| Question | human | enriched (R1, R2, R3) | median | demographics-only (R1, R2, R3) | median |
|---|---:|---|---:|---|---:|
| Q1 | 9 | 5, 9, 9 | 9 | 8, 10, 8 | 8 |
| Q2 | 6 | 4, 10, 5 | 5 | 10, 6, 6 | 6 |
| Q3 | 4 | 9, 7, 9 | 9 | 7, 8, 5 | 7 |
| Q4 | 5 | 7, 7, 8 | 7 | 7, 4, 8 | 7 |
| Q5 | 7 | 6, 7, 7 | 7 | 10, 8, 8 | 8 |

**Only the human series is connected across questions.** Guide questions are not an
ordered variable and the synthetic min–max ranges are not interval estimates, so joining
the synthetic points would invite exactly the reading the figure must avoid.
`test_only_the_human_series_is_connected_in_panel_b` inspects the drawing calls and
fails if any non-human polyline is drawn inside Panel B.

The annotated spreads are recomputed, not typed: human medians span 4–9 and
demographics-only medians span 6–8
(`test_the_annotated_spreads_are_the_ones_in_the_data`). The caveat beneath is likewise
earned from the data — at least one synthetic replicate profile is as uneven as the
human profile, which is why the pattern is exploratory rather than universal
(`test_the_exploratory_caveat_is_earned_by_replicate_level_variation`).

**The uneven-versus-even contrast is descriptive of these seven realisations.** It does
not establish that enrichment or demographics-only prompting produces evenness, and it
may partly reflect question-specific taxonomy granularity rather than anything about the
groups.

## Supporting values moved to the narrative — mean new clusters at the final position

These values are retained in the plotted-values CSV but deliberately omitted from the
figure face. Synthetic values are medians of R1–R3.

| Question | human | enriched | demographics-only |
|---|---:|---:|---:|
| Q1 | 1.4 | 1.2 | 1.4 |
| Q2 | 0.6 | 0.6 | 1.2 |
| Q3 | 0.4 | 1.0 | 0.8 |
| Q4 | 0.5 | 1.25 | 1.0 |
| Q5 | 0.2 | 0.8 | 1.2 |

All fifteen values are above zero.

## What the figure does not state

- It does not state that saturation was achieved, reached or demonstrated.
- The 100% at position 5 in Panel A is the definition of the observed endpoint, not a
  threshold.
- Meaning saturation was not assessed; only the appearance of new classified clusters
  was measured.
- The synthetic ranges are ranges over three study realisations, not confidence
  intervals.
- The curves cover 440 of 526 raw themes; the 86 unresolved themes enter no scenario.

## Question titles

The five short titles under Panel B are derived from the literal `Question N.` moderator
headers in the human transcripts. Every content word is taken from the guide;
`test_question_titles_are_derived_from_the_guide_and_not_invented` asserts this word by
word, allowing only "whether" as a grammatical connective.

| Panel B label | Literal guide question |
|---|---|
| Favourite place with male friends | What's your favourite place in your city to spend time with your male friends? Why - feel free to be specific? |
| How you decide what to eat | How do you decide what to eat? |
| Whether gender influences what you eat | Do you think your gender influences what you eat? Tell us more about why or why not? |
| What would need to change to go plant-based | Imagine you decided to go plant-based - what would need to change in your life for you to do that? |
| What might make plant-based foods more appealing | What might make plant-based foods more appealing to you or other men you know? |
