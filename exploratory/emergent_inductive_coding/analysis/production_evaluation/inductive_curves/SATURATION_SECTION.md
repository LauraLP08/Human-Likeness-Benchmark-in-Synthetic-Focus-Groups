# Retrospective inductive theme accumulation

**Main figure:** `analysis/figures/inductive_theme_accumulation_main.png`
**Technical supplement:** `inductive_theme_accumulation.png` (five per-question panels)
**Source:** `inductive_endpoints_by_replicate.csv`, `inductive_curves_v2_full.json`

The main figure carries the same values in two panels — cumulative percentage of each
realisation's own final repertoire, and new clusters at the final position — with the
technical identifiers moved to
`analysis/figures/inductive_theme_accumulation_main_TRACEABILITY.md`. The five-panel
figure below remains the per-question record.

This section uses the **inductive analysis only**. Deductive coverage of the fixed
a-priori codebook belongs to the thematic-fidelity section and is not reported here as a
measure of saturation: it is bounded at 11 by construction and counts how much of a
closed scheme has been seen, which is a different quantity from the emergence of new
categories.

## Figure caption

Cumulative classified open-theme clusters against the number of focus groups included,
per guide question, under `CANONICAL_RESOLVED_LOWER`. The human line is **one
realisation** (FG1–FG5). Each synthetic condition is **three independent study
realisations**: the line is their median and the shaded band their full range.
Replicates are never pooled. Within a realisation the value at each position is the mean
over that realisation's own orderings — 120 for Q1, Q2, Q3 and Q5, and 24 for Q4. **Q4
ends at four focus groups** (FG1–FG4); synthetic FG5 Q4 units were extracted but stay
outside the curve because no paired human FG5 Q4 exists.

Shaded synthetic bands are ranges across three study realisations, **not confidence
intervals**. Curves cover the 440 of 526 raw themes classified under LOWER; the 86
unresolved raw themes are excluded and reported separately.

## Descriptive table

Cumulative percentage of each realisation's own final repertoire, and the mean number of
new clusters appearing at the final focus-group position. Endpoints are sums of
question-specific repertoire endpoints within one realisation.

| Condition | Realisation | After 3 FGs | After 4 FGs | Endpoint |
|---|---|---:|---:|---:|
| human | single | **79.4%** | **91.6%** | **31** |
| enriched | R1 | 77.7% | 91.6% | 31 |
| enriched | R2 | 72.2% | 89.0% | 40 |
| enriched | R3 | 74.9% | 90.0% | 38 |
| demographics-only | R1 | 71.0% | 87.6% | 42 |
| demographics-only | R2 | 68.8% | 85.6% | 36 |
| demographics-only | R3 | 72.9% | 89.7% | 35 |

Endpoints R1–R3: enriched **[31, 40, 38]**, median 38. Demographics-only
**[42, 36, 35]**, median 36. Human **[31]**.

### Mean new clusters at the final focus-group position

Synthetic values are the median across R1–R3.

| Question | human | enriched | demographics-only |
|---|---:|---:|---:|
| Q1 | 1.4 | 1.2 | 1.4 |
| Q2 | 0.6 | 0.6 | 1.2 |
| Q3 | 0.4 | 1.0 | 0.8 |
| Q4 | 0.5 | 1.25 | 1.0 |
| Q5 | 0.2 | 0.8 | 1.2 |

All fifteen values are above zero.

## Results text

Under `CANONICAL_RESOLVED_LOWER`, most of the resolved repertoire was identified by the
fourth focus group: 91.6% for the human realisation, 89.0–91.6% across the three enriched
realisations and 85.6–89.7% across the three demographics-only realisations. After three
focus groups the corresponding figures were 79.4%, 72.2–77.7% and 68.8–72.9%.

Themes nevertheless continued to accumulate at the final focus-group position in every
question and condition. The mean number of new clusters appearing at the last position
ranged from 0.2 to 1.4, and no value reached zero. The human realisation showed the
smallest final increments in Q3 and Q5 (0.4 and 0.2) and the largest in Q1 (1.4).

Between-realisation variation was of the same order as the difference between conditions:
enriched endpoints spanned 31 to 40 and demographics-only 35 to 42, against a human
endpoint of 31. Any comparison between conditions must therefore report all three
realisation values rather than a single summary.

## Discussion text

Most of the resolved repertoire was identified by the fourth focus group, but themes
continued to accumulate at the final focus-group position in every question and
condition. These two observations together mean that **code-emergence stabilisation was
not established** by this study. A curve that is still rising at its last observed
position provides no basis for asserting that further groups would have added nothing,
and the design offers no position beyond the fifth (fourth for Q4) at which the question
could be settled.

**Meaning saturation was not assessed.** What was measured is the appearance of new
classified open-theme clusters, not whether the interpretive content of existing themes
had been fully developed. The two are distinct, and nothing in this analysis speaks to
the second.

Four limitations bound every figure above:

1. **The main curve covers 440 of 526 raw themes.** The remaining **86 are unresolved**
   after three independent passes and enter no scenario. They are not noise: they
   concentrate in Q2 (26) and Q3 (22).
2. **In F2, 36 of 139 second-extraction themes were not accommodated by the
   first-extraction canonical taxonomy.** A taxonomy induced from one extraction did not
   cover roughly a quarter of what a second extraction produced from the same units, so
   these repertoires are properties of this execution rather than fixed properties of the
   corpus.
3. **The analysis is retrospective and LLM-assisted.** Extraction, taxonomy construction
   and assignment were all model-performed; Gemini was the primary extractor and Claude
   served only as cross-model adjudicator of the ambiguous Stage D cases.
4. **The full taxonomy was not human-validated.** The two-coder human review covers
   U01–U07 for Q3 and calibrates the extraction procedure; it does not validate this
   taxonomy, and it does not extend to Q1, Q2, Q4 or Q5.

## Conclusion

- Most of the resolved repertoire was identified by the fourth focus group.
- Themes continued to accumulate at the final focus-group position.
- Code-emergence stabilisation was not established.
- Meaning saturation was not assessed.
