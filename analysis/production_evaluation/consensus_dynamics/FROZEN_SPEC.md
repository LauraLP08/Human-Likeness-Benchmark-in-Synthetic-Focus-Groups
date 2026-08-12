# CONSENSUS_DYNAMICS_EXPLORATORY — frozen specification

*Frozen 3 August 2026, before N1 human coding and before any comparative metric was
computed. A post-result decision, declared under the amendments policy.
Design: `diseno_facilidad_de_consenso_2026-08-03.md`.*

## Status

`AUTOMATIC_EXPLORATORY`. It does **not** substitute for the interpretive agreement /
disagreement metrics, which remain `WITHHELD` pending the gold standard. No LLM judge in the
core. Zero API calls.

## Freeze hashes

| Object | SHA-256 |
|---|---|
| D1 dictionary + window (`OPENING_CLAUSES=2`) | `d646bde293cc62d90edb99997059aaf861a244e8b70be6a26be41f749a8a8ee9` |
| `scripts/consensus_dynamics_events.py` | `33b9d2fadd169c4a747a186096e0b00a16119a8bf99f298a34f2a6023bdddb55` |
| `response_acts.csv` | `028cd205bb2cf567b476cca96d2f4d57718868502c635c26de032cdc7e1ac7b1` |

Dictionary: 59 divergence markers, 37 alignment markers, 13 hedges.
Any edit invalidates the hash and forces a re-declaration.

## Unit and universe

Response act (P→P) within a guide section comparable on both sides.
**779 acts: 319 human (5 FG), 460 synthetic (30 sessions).** Sections 1–5; sections 0
(introduction) and 6 (closing) fall outside because they do not exist on the human side.
68 section×run pairs fall outside the universe for having no counterpart or not reaching the
data floor — each recorded individually in `section_skips.json`, none discarded silently.

## Detector D1 (frozen)

- **Primary:** markers in clause-initial position, **within the first 2 clauses** of the
  response turn.
- **Sensitivity:** the same count over the whole turn. Always reported alongside the primary.
- Markers are **counted**; stance is never classified.
- Deterministic: repeatability 1.0 by construction.

### Why the opening window (a construction decision, documented)

The whole-turn variant was computed first. Result: **33.7% of synthetic acts flagged as
divergence against 5.0% of human ones.** Manual inspection showed the gap was carried by
mid-turn contrastive constructions (`that's not the same as saying...`: 155 synthetic
occurrences against 3 human) that mark internal argumentative structure, not a stance toward
the previous speaker. Mean clauses per act: **6.4 human against 24.0 synthetic (3.75×)** —
that is, the whole-turn count hands the long side roughly 4× the opportunities to fire.

The opening window equalises opportunity and targets the construct. **No dictionary entry was
removed** — the adjustment is structural, not a post-hoc pruning of inconvenient markers.

## D1 results over the universe (declared before N1)

| Side | Divergence (opening) | Alignment (opening) | Divergence (whole turn) |
|---|---|---|---|
| Human (n=319) | 10 — **3.1%** | 12 — 3.8% | 15 — 4.7% |
| Synthetic (n=460) | 39 — **8.5%** | 26 — 5.7% | 144 — 31.3% |

**The sign is contrary to the a priori hypothesis** (*less* divergence was predicted in the
synthetic side). The two readings compatible with this datum are:

1. The agents produce more *rhetorical marking* of disagreement — the concessive register
   ("Yeah… but I think…") already detected in the qualitative validation of 29 July — without
   that implying sustained interactional dissent.
2. Humans disagree without a lexical marker (prosody, a flat "no", a change of topic), and D1
   systematically under-detects on that side.

**Both imply the same thing: D1 alone cannot answer the question.** This is exactly the
situation N1 exists to arbitrate, and it is the empirical reason why the "automated-only, as
in Mator et al." route would have produced a confident and wrong answer — in either
direction.

## Directional predictions (frozen, for the metrics not yet computed)

Synthetic relative to human:

| Metric | Prediction |
|---|---|
| M1 risk of first divergence per section | lower |
| M2 half-life of dissent | shorter |
| M3 % of divergences unresolved at close | lower |
| M4 slope of semantic dispersion | steeper |
| M5 anchoring to the first speaker | greater |
| M6 proportion of participants who move | greater (movement spread out = echo) |

Raw D1 has already **falsified** the prediction analogous to M1 in its lexical form. This is
recorded as such.

## N1 — human validation (80 units)

Stratified on the primary D1 label, with known inclusion probabilities:

| Stratum | Side | N corpus | n sample | p inclusion | HT weight |
|---|---|---|---|---|---|
| A divergence | human | 10 | 10 (census) | 1.0000 | 1.00 |
| A divergence | synthetic | 39 | 14 | 0.3590 | 2.79 |
| B alignment | human | 12 | 10 | 0.8333 | 1.20 |
| B alignment | synthetic | 26 | 10 | 0.3846 | 2.60 |
| C none | human | 297 | 20 | 0.0673 | 14.85 |
| C none | synthetic | 395 | 16 | 0.0405 | 24.69 |

Ternary label, one decision per unit. Seed `20260803`, randomised order, masked names, side
hidden. 11,903 words of response text to read (~60–75 min). Double coding: N1-001…N1-020
(Cohen's κ).

**Estimand:** recall and precision of D1 **per side**, by Horvitz–Thompson.
**Decision criterion, fixed in advance:**

| Recall gap between sides | Verdict |
|---|---|
| < 0.15 | PASS — D1's raw contrast is interpretable with its band |
| 0.15–0.30 | MARGINAL — D1 only alongside a second detector |
| > 0.30 | FAIL — D1 measures register; the conclusion must rest on D2/D4/D5 or escalate to N2 |

N1 does **not** produce corrected rates: that is what N2 (240 units) is for. N1 is go/no-go.

## What N1 cannot decide

If N1 passes, what is established is that D1 measures comparably on both sides — not that
lexical divergence is ease of consensus. The dynamic reading (M2–M6) still requires the
embedding detectors and, for the strong claim, the gold standard.
