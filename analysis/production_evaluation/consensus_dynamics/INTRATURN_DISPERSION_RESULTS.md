# Intra-turn semantic dispersion

*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Zero API calls.*
*Model `paraphrase-multilingual-mpnet-base-v2`. Turns with >=3 sentences.*

Formalises, geometrically and independently of the D1 dictionary, the coder's observation:
synthetic turns traverse several positions at once and land on a midpoint; human turns take
fewer positions and hold a clearer stance.

The human envelope is the [min-max] range of the five human groups.

## Distribution of sentences per turn

| Side | n turns | min | p25 | median | p75 | max |
|---|---|---|---|---|---|---|
| human | 190 | 3 | 4 | 5 | 8 | 21 |
| synthetic | 915 | 6 | 14 | 17 | 20 | 38 |

**The two corpora only overlap from 6 sentences upward.** The 3–5 band contains 101 human
turns and 0 synthetic ones: at the short end they are not matchable, because synthetic turns
are never short. That limits what can be controlled by matching and what only by truncation.

## ALL (unmatched)

*turns: human 190, synthetic 915*

| Metric | Human mean [min-max by FG] | Enriched | Demo-only | Inside envelope |
|---|---|---|---|---|
| mean intra-turn dispersion | 0.626 [0.614-0.643] | 0.656 | 0.664 | no |
| maximum intra-turn distance (extremes) | 0.838 [0.816-0.875] | 0.944 | 0.960 | no |
| dispersion around the turn centroid | 0.302 [0.281-0.327] | 0.380 | 0.389 | no |
| centrality of the closing sentence (lands in the middle) | -0.008 [-0.027-0.017] | 0.015 | 0.019 | partial |
| dispersion, first 3 sentences | 0.626 [0.614-0.633] | 0.638 | 0.638 | no |
| maximum distance, first 3 sentences | 0.738 [0.724-0.750] | 0.732 | 0.736 | yes |

## MATCHED 6–9 sentences

*turns: human 48, synthetic 53*

| Metric | Human mean [min-max by FG] | Enriched | Demo-only | Inside envelope |
|---|---|---|---|---|
| mean intra-turn dispersion | 0.628 [0.594-0.672] | 0.615 | 0.636 | yes |
| maximum intra-turn distance (extremes) | 0.868 [0.841-0.904] | 0.832 | 0.874 | partial |
| dispersion around the turn centroid | 0.321 [0.294-0.345] | 0.320 | 0.335 | yes |
| centrality of the closing sentence (lands in the middle) | -0.011 [-0.048-0.053] | 0.038 | -0.042 | yes |
| dispersion, first 3 sentences | 0.633 [0.551-0.678] | 0.620 | 0.571 | yes |
| maximum distance, first 3 sentences | 0.740 [0.662-0.795] | 0.703 | 0.680 | yes |

## MATCHED 6–14 sentences

*turns: human 79, synthetic 236*

| Metric | Human mean [min-max by FG] | Enriched | Demo-only | Inside envelope |
|---|---|---|---|---|
| mean intra-turn dispersion | 0.637 [0.609-0.674] | 0.639 | 0.643 | yes |
| maximum intra-turn distance (extremes) | 0.894 [0.882-0.925] | 0.896 | 0.909 | yes |
| dispersion around the turn centroid | 0.337 [0.312-0.358] | 0.354 | 0.360 | partial |
| centrality of the closing sentence (lands in the middle) | -0.009 [-0.056-0.055] | 0.017 | -0.011 | yes |
| dispersion, first 3 sentences | 0.644 [0.577-0.672] | 0.631 | 0.630 | yes |
| maximum distance, first 3 sentences | 0.758 [0.690-0.790] | 0.726 | 0.736 | yes |

---

## Synthesis: two instruments, one informative disagreement

The coder's observation was measured along two independent routes. **They do not agree, and
the disagreement is the finding.**

| Route | Normalisation | Result |
|---|---|---|
| D1 lexical | internal contrastives **per clause** | synthetic **5.2×** more; multi-position turns **31×** more (0.3% vs 9.8%) |
| Geometric | dispersion **per sentence**, matched bands 6–9 and 6–14 | **no difference**: everything inside the human envelope |

Read together: synthetic turns **signal** contrast far more than they **traverse** semantic
distance. The scaffolding "on the one hand / on the other / that said" appears 5× more per
clause, but the two sides that scaffolding announces are no further apart than those of a
human turn of the same length. It is rhetorical marking of balance, not breadth of positions.

That fits the register homogenisation documented in the qualitative validation of 29 July
("Yeah... but I think... [reflective example]") and explains the coding difficulty better
than the breadth hypothesis: what exhausts the coder is not that the turn covers very
different positions, but that it continually announces that it does.

### What still stands from the original observation

Unmatched, the maximum intra-turn distance **is** greater in synthetic turns (0.944/0.960 vs
0.838, outside the human envelope). That is real and it is what the coder faces, but its
mechanism is **volume**: 17 sentences against 5 give more opportunities to contain a distant
pair. At equal sentence counts the effect disappears.

For coding, volume is exactly what matters: the unit to which **one** stance must be
assigned is 3.4× larger. The observation holds as a property of the
turn-as-unit-of-coding; it does not hold as a property of per-sentence style.

### A structural limit worth reporting

The two corpora **do not overlap below 6 sentences**: 101 human turns and 0 synthetic ones in
the 3–5 band. The short human turn — the brief intervention, the qualified agreement —
simply does not exist on the synthetic side. Methodological consequence: control by matching
is only possible on the long half of the human distribution, and any control over the short
half requires truncation, which changes what the turn is. Both are reported and the limit is
declared.

### Status

Exploratory. n=5 pairs, no tests. A single geometric operationalisation of the
"multi-position" construct: that this one does not detect it does not prove the phenomenon
absent, only that it does not manifest as semantic dispersion between sentences.
