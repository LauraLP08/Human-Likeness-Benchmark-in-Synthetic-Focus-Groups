# Automatic consensus metrics — Mator replicated, D4 and D5

*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Zero API calls.*
*Model: `paraphrase-multilingual-mpnet-base-v2`, max_seq_length=128 tokens.*
*Units: 5 human groups, 30 synthetic sessions. W per FG: {'fg1': 38, 'fg2': 89, 'fg3': 47, 'fg4': 47, 'fg5': 22}.*

The human envelope is the [min-max] range of the five human groups: the question is not
whether the synthetic side differs from the human mean, but whether it falls outside the
natural variation between human groups. Mator et al. had a single human group and could
not compute it.

> **Note added 2026-08-07.** The two rows this document labels *relevance to the question*
> and *similarity between participants* are computed here with sentence-transformer cosine
> similarity. Mator et al. attribute those two rows specifically to BERTScore (Zhang et al.,
> 2019), which is a different method on a different scale. They were subsequently recomputed
> with the actual `bert-score` package in
> `analysis/production_evaluation/mator_comparable/`; see `MATOR_REPLICATION_REPORT.md`
> there for the comparison against the published figures and for the disposition of that
> layer. The figures below remain valid as cosine similarities and are not superseded as
> such, but they are not comparable to Mator's published percentages.

### R1 naive (encoder truncates at 128 tokens)

| Metric | Human mean [min-max] | Enriched | Demo-only | Synthetic inside human envelope |
|---|---|---|---|---|
| Mator: agreement (similarity between consecutive responses) | 0.448 [0.402-0.547] | 0.629 | 0.583 | no |
| Mator: similarity between participants | 0.397 [0.322-0.549] | 0.599 | 0.548 | partial |
| Mator: relevance to the question | 0.408 [0.290-0.550] | 0.412 | 0.355 | yes |
| D4: mean similarity to the first speaker | 0.444 [0.364-0.566] | 0.584 | 0.547 | partial |
| D4: rho(position, similarity to the first speaker) | -0.281 [-0.652--0.010] | -0.169 | -0.296 | yes |
| D5: mean displacement | 0.641 [0.500-0.695] | 0.435 | 0.466 | no |
| D5: Gini of displacement | 0.122 [0.083-0.162] | 0.139 | 0.139 | yes |
| D5: proportion moving toward the centroid | 0.368 [0.235-0.500] | 0.446 | 0.408 | yes |

### R2 sentence-pooled (whole turn)

| Metric | Human mean [min-max] | Enriched | Demo-only | Synthetic inside human envelope |
|---|---|---|---|---|
| Mator: agreement (similarity between consecutive responses) | 0.538 [0.476-0.641] | 0.870 | 0.858 | no |
| Mator: similarity between participants | 0.506 [0.420-0.633] | 0.848 | 0.834 | no |
| Mator: relevance to the question | 0.381 [0.282-0.506] | 0.422 | 0.386 | yes |
| D4: mean similarity to the first speaker | 0.551 [0.519-0.623] | 0.817 | 0.812 | no |
| D4: rho(position, similarity to the first speaker) | -0.271 [-0.573-0.033] | -0.263 | -0.205 | yes |
| D5: mean displacement | 0.517 [0.409-0.570] | 0.175 | 0.175 | no |
| D5: Gini of displacement | 0.168 [0.146-0.213] | 0.183 | 0.144 | partial |
| D5: proportion moving toward the centroid | 0.280 [0.000-0.438] | 0.544 | 0.603 | no |

### R3 length-matched (same rule on both sides)

| Metric | Human mean [min-max] | Enriched | Demo-only | Synthetic inside human envelope |
|---|---|---|---|---|
| Mator: agreement (similarity between consecutive responses) | 0.430 [0.355-0.546] | 0.545 | 0.520 | yes |
| Mator: similarity between participants | 0.384 [0.291-0.548] | 0.517 | 0.490 | yes |
| Mator: relevance to the question | 0.388 [0.252-0.551] | 0.354 | 0.308 | yes |
| D4: mean similarity to the first speaker | 0.417 [0.327-0.565] | 0.508 | 0.483 | yes |
| D4: rho(position, similarity to the first speaker) | -0.256 [-0.653-0.107] | -0.061 | -0.217 | yes |
| D5: mean displacement | 0.650 [0.503-0.697] | 0.518 | 0.519 | yes |
| D5: Gini of displacement | 0.109 [0.080-0.163] | 0.130 | 0.115 | yes |
| D5: proportion moving toward the centroid | 0.399 [0.250-0.500] | 0.476 | 0.550 | partial |

---

## Paired reading by FG (n=5) — the correct unit of analysis

The envelope table answers "does the synthetic side fall outside the natural variation
between human groups". The paired table answers "is each synthetic group more aligned than
ITS OWN human counterpart". They are different questions and here they give different
answers. Both are reported.

**Mator: agreement (similarity between consecutive responses)** — delta = synthetic minus its own human pair

| FG | human | enriched | demo-only | d enr | d demo | | human | enriched | demo-only | d enr | d demo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | *R2 whole turn* | | | | | | *R3 length-matched* | | | | |
| fg1 | 0.505 | 0.855 | 0.848 | +0.350 | +0.343 | | 0.445 | 0.529 | 0.505 | +0.084 | +0.061 |
| fg2 | 0.641 | 0.876 | 0.852 | +0.235 | +0.211 | | 0.546 | 0.642 | 0.585 | +0.096 | +0.039 |
| fg3 | 0.504 | 0.874 | 0.871 | +0.370 | +0.367 | | 0.390 | 0.536 | 0.535 | +0.146 | +0.145 |
| fg4 | 0.564 | 0.866 | 0.865 | +0.302 | +0.301 | | 0.415 | 0.563 | 0.511 | +0.147 | +0.096 |
| fg5 | 0.476 | 0.877 | 0.855 | +0.402 | +0.379 | | 0.355 | 0.455 | 0.462 | +0.099 | +0.106 |
| **direction** | | | | **5/5** | **5/5** | | | | | **5/5** | **5/5** |

**D5: mean displacement of position within a section**

| FG | *R2* human | enr | demo | d enr | d demo | | *R3* human | enr | demo | d enr | d demo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fg1 | 0.570 | 0.186 | 0.188 | -0.384 | -0.382 | | 0.677 | 0.559 | 0.517 | -0.118 | -0.160 |
| fg2 | 0.409 | 0.186 | 0.185 | -0.223 | -0.223 | | 0.503 | 0.432 | 0.442 | -0.071 | -0.060 |
| fg3 | 0.570 | 0.172 | 0.152 | -0.398 | -0.418 | | 0.683 | 0.544 | 0.539 | -0.139 | -0.144 |
| fg4 | 0.478 | 0.175 | 0.180 | -0.303 | -0.297 | | 0.691 | 0.505 | 0.571 | -0.185 | -0.119 |
| fg5 | 0.561 | 0.157 | 0.168 | -0.403 | -0.393 | | 0.697 | 0.550 | 0.524 | -0.146 | -0.173 |
| **direction** | | | | **0/5** | **0/5** | | | | | **0/5** | **0/5** |

No tests. n=5 pairs; the replicates are generator variability, never 15 independent
observations. Directional consistency is reported, not significance.

---

## What holds and what does not

**1. The main finding of Mator et al. replicates — and is then explained away in two thirds
of its magnitude.** With the honest whole-turn representation (R2), synthetic agreement is
0.87 against 0.54 human: the same shape as their 92% vs 42%. Under a length control applied
by an identical rule on both sides (R3), the paired gap falls from **+0.30 to +0.11**.
Approximately **two thirds of the published effect is length and answer exhaustiveness, not
consensus.**

**2. But it is not purely an artefact.** The +0.11 residual is directionally **stable across
all 5 pairs and both conditions (5/5)**. What changes under the length control is the
magnitude and the envelope reading: the residual is small relative to the variation between
human groups (human range 0.355–0.546, width 0.19), so under R3 the synthetic side **falls
inside** the human envelope while remaining consistently higher than its own pair. Both
things are true and both have to be stated.

**3. Prediction M5 (anchoring to the first speaker) is FALSIFIED.** rho(position, similarity
to the first speaker) is **negative on both sides** (human -0.271, synthetic -0.263/-0.205)
and inside the human envelope in all three representations. Later speakers resemble the
first one *less*, in humans and in agents alike: ordinary thematic drift. **There is no
signature of consensus by echo of the first speaker.** The over-validation hypothesis, in
the concrete form in which it was operationalised, does not hold.

**4. Prediction M6 is partly met, with an interesting nuance.** Synthetic participants
displace **less** within a section (0/5 in the direction of more movement; R3: 0.52 vs 0.65
human), but a **larger proportion** of what little movement there is goes **toward the group
centroid** (R3: 0.48/0.55 vs 0.40 human). The portrait is "more static positions that also
drift toward the centre", not "everyone moves a lot toward the centre".

**5. A methodological note worth reporting.** R1 and R2 differ because the encoder truncates
at 128 tokens (~90–100 words): a naive replication with this model **already applies, without
knowing it, a partial length control**. Anyone replicating similarity metrics over long turns
without inspecting `max_seq_length` is not measuring what they think they are measuring.

## Limits of this layer

- **Similarity is not agreement.** None of these metrics distinguishes "sharing a stance"
  from "talking about the same topic". That is what D1+N1 resolve, and in due course the
  gold standard.
- **R3 is a strong control on form**: it also truncates the human turns (half of them, by
  construction of the median) and discards most of the synthetic turn. The truth lies
  between R2 and R3; both are reported for exactly that reason.
- **Post-result and exploratory.** Namespace `CONSENSUS_DYNAMICS_EXPLORATORY`; it does not
  touch the WITHHELD interpretive metrics.
