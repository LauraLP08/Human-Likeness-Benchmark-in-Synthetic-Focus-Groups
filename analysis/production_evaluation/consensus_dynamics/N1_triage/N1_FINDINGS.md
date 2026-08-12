# N1 — triage result and the associated qualitative finding

*3 August 2026. Decision criterion frozen before coding, in `FROZEN_SPEC.md`.
Namespace `CONSENSUS_DYNAMICS_EXPLORATORY`.*

## 1. What was coded

**42 of 80 units (53%).** Coding stopped at N1-042, that is, a prefix of the presented
order. Because the order was randomised under a fixed seed and independently of stratum and
side, the prefix is a random subsample of the sample; Horvitz–Thompson weights were
recomputed over what was **actually coded** (`N_stratum / n_coded`), not over what was
drawn. Using the original weights would have over-weighted the strata left unfinished.

**A single coder. There was no double coding, so there is no κ.** That is the principal
limitation of this result and it cannot be argued away: the reference label has no
demonstrated reliability.

| Side | Coded | divergence | alignment | none |
|---|---|---|---|---|
| Human | 21 | **0** | 7 | 14 |
| Synthetic | 21 | 4 | 13 | 4 |

## 2. Verdict against the frozen criterion: INDETERMINATE

The pre-registered criterion was the recall gap between sides. **It is not computable: the
human side has not a single true positive**, so human recall is undefined (0/0). The formal
verdict is INDETERMINATE and is recorded as such. N1 does not license the claim it was
designed to license.

HT prevalences, with the imprecision appropriate to 21 units per side:

| Side | HT prevalence of divergence | 95% CI (Wilson on effective n) |
|---|---|---|
| Human | 0.000 | [0.00, 0.29] |
| Synthetic | 0.214 | [0.07, 0.48] |

The intervals overlap completely, and the synthetic figure is carried by **2 units weighted
39.5 each**. It is not a citable estimate. It is reported to place its imprecision on
record, not to be used.

## 3. What is established

**(a) D1 has precision 0 on the human side.** Of the 9 human units D1 flagged as divergence
and that were coded, the coder returned **none in 8 and alignment in 1**. Zero hits. On the
synthetic side D1 was right in 2 of 4. The precision asymmetry (0/9 vs 2/4) runs in the
direction the design feared: **D1's human 3.1% is essentially lexical noise.**

**(b) The direction of the raw contrast does not invert; it strengthens.** D1 reported
synthetic 8.5% against human 3.1%. Human coding suggests the human side is closer to a true
~0% and the synthetic side clearly above zero. The a priori prediction M1 (less divergence
in the synthetic side) remains **falsified** after contact with human labels.

**(c) No divergence was found in 21 human response acts — in a sample biased *toward*
divergence.** Nine of those 21 were drawn from the stratum D1 had flagged as divergence,
deliberately over-represented. That none appears even so is informative.

The honest formulation, which is as far as the data reaches: *no divergence was found in 21
human response acts sampled with a bias toward divergence, including the 9 coded units the
lexical detector had flagged.* It does **not** license "humans never disagree": of the
majority human stratum (N=297) only 8 units were coded.

If it held up under more coding, it would reframe the research question: in this corpus it
is the **human** groups that barely disagree in adjacent response acts, and the question
stops being "do synthetic participants reach consensus more easily?" and becomes "what kind
of dissent does each side produce?".

## 4. The coder's qualitative finding (analysis memo)

Recorded verbatim, during coding and without prompting (translated from the original
Spanish):

> There are synthetic turns that are hard to follow because they sometimes try to see every
> side of the matter within a single turn, to address the extremes and then arrive at a
> balance. Humans address fewer points at a time and with clearer positions.

This is not colour: **it explains all three anomalous results of this layer at once.**

1. It explains why D1 fired at 31.3% on the whole turn: mid-turn contrastive markers
   (`that's not the same as saying…`) are the internal articulation of "on the one hand / on
   the other", not a stance toward the previous speaker.
2. It explains the between-response similarity of the Mator metric: if every turn contains
   every position, any two turns necessarily overlap. High "agreement" may be *coverage*,
   not convergence.
3. It explains the coding difficulty: the ternary label presupposes that a turn holds *one*
   stance relative to the previous turn. For a turn that covers the extremes and lands in
   the middle, that presupposition fails — and that is a **codability** problem, which
   affects the gold standard in the field as well.

### Quantification (length-normalised, over the 779 acts)

Contrastive markers **outside the opening window** = internal articulation of the turn:

| Measure | Human (n=319) | Synthetic (n=460) | Ratio |
|---|---|---|---|
| Internal contrastives per turn | 0.02 | 0.42 | 21× |
| Internal contrastives **per clause** | 0.0034 | 0.0177 | **5.2×** |
| Turns with both agreement **and** disagreement markers | 0.3% | 2.4% | 8× |
| Turns with ≥2 internal contrastives (multi-position) | **0.3%** (1/319) | **9.8%** (45/460) | **31×** |

Per-clause normalisation is the one that matters: it removes the length confound that sank
the whole-turn variant. **At equal clause counts, a synthetic turn articulates 5.2× more
internal contrast than a human one**, and the multi-position form is 31× more frequent.

The qualitative observation is thereby converted into an indicator with a numerical anchor,
measured over the complete corpus rather than over the sample. It is the most solid result
this coding session produced — more so than the verdict N1 was meant to deliver.

## 5. What would be needed to close N1

- **38 remaining units** (~35 min) to complete the sample as designed.
- **Double coding of 20 units** (~20 min of a second person) to obtain κ. Without it the
  result has no demonstrated reliability, whether or not the sample is completed.
- Even complete, the recall gap will probably remain indeterminate on the human side: if
  human divergence is this rare, **the chosen estimand is not the right one for this
  corpus**. The correct alternative would be to estimate prevalence per side with sampling
  directed at the majority stratum, rather than the detector's recall.
