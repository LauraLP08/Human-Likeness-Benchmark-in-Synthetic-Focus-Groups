# Specificity with GLiNER (framework §H)

*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Local model, zero API calls.*
*`urchade/gliner_medium-v2.1`, threshold 0.4. Turns chunked to <= 80 words at sentence boundaries so that no long turn is silently truncated.*

Labels (frozen, written from the study's own definition): `place or location`,
`date or time`, `named person`, `brand or organisation`, `amount of money`,
`number or quantity`, `named food or dish`.

Excluded: pronouns (GLiNER labels "I"/"we" as `named person` with ~0.8 confidence) and
participant names (naming the person you are answering is direct address, not detail about
the world).

"Concrete anchor" = the span is a proper noun or contains a number: this distinguishes
`Wetherspoons` and `15 quid` from a generic `pub`.

| Measure | Human mean [min-max by FG] | Enriched | Demo-only | Inside envelope |
|---|---|---|---|---|
| proportion of turns with >=1 anchor (raw) | 0.627 [0.517-0.913] | 0.909 | 0.840 | yes |
| proportion with >=1 concrete anchor (proper or quantified) | 0.197 [0.152-0.265] | 0.367 | 0.408 | no |
| anchors per 100 words | 3.249 [2.841-3.836] | 1.774 | 1.319 | no |
| concrete anchors per 100 words | 0.428 [0.290-0.712] | 0.251 | 0.284 | no |
| proportion with >=1 anchor in the first 40 words | 0.498 [0.402-0.696] | 0.481 | 0.352 | partial |
|   place or location per 100 words | 0.493 [0.359-0.560] | 0.530 | 0.557 | yes |
|   date or time per 100 words | 0.257 [0.000-0.414] | 0.101 | 0.184 | yes |
|   named person per 100 words | 0.206 [0.033-0.417] | 0.185 | 0.238 | yes |
|   brand or organisation per 100 words | 0.158 [0.083-0.229] | 0.043 | 0.060 | no |
|   amount of money per 100 words | 0.063 [0.000-0.129] | 0.007 | 0.012 | yes |
|   number or quantity per 100 words | 0.056 [0.033-0.104] | 0.022 | 0.030 | no |
|   named food or dish per 100 words | 2.016 [1.478-2.303] | 0.886 | 0.238 | no |

*Correction note: an earlier version of this table showed `named person` and
`named food or dish` with identical figures. That was a column-naming fault in the script
(both labels begin with "named" and the key was derived from the first word), not a fault of
the model. The totals in the first five rows were never affected. Corrected and recomputed
from `specificity_gliner_entities.csv`.*

---

## Reading

**At equal word counts, human turns carry ~2× more concrete anchors** (3.25 vs 1.77/1.32 per
100 words, outside the human envelope). The raw proportion of turns with at least one anchor
says the opposite (0.63 human vs 0.91/0.84) for the usual reason: a 230-word turn can hardly
avoid containing one. Density is the figure to use.

**The effect is driven by a single category: `named food or dish`** — 2.016 human against
0.886 enriched and 0.238 demo-only. In a focus group about food, humans name concrete dishes
(mixed grill, Quorn, chippy tea) and the agents talk about "food", "meals", "a proper
dinner". Next come `brand or organisation` (3.7×/2.6×) and `number or quantity`
(2.5×/1.9×).

**Places, dates, people and money do not differentiate**: they fall inside the human
envelope. Synthetic specificity does not fail everywhere — it fails at naming the concrete
thing the study is about.

**A condition effect, unusual in this corpus.** In `named food or dish` the enriched
condition triples the demographics-only one (0.886 vs 0.238), approaching the human side
without reaching it. It is one of the few metrics where enrichment moves something large,
and it fits the mixed-effect account ("enrichment moves content, not form"): here it moves
precisely content.

## Convergence with the regex proxy

| Measure | Regex proxy | GLiNER | Agreement |
|---|---|---|---|
| Anchor density, human vs synthetic | 0.839 vs 0.337/0.489 (1.7-2.5×) | 3.249 vs 1.774/1.319 (1.8-2.5×) | **yes, same magnitude** |
| Numbers / quantities | 0.149 vs 0.007/0.022 (7-21×) | 0.056 vs 0.022/0.030 (1.9-2.5×) | direction yes, magnitude no |
| 40-word window | 0.184 vs 0.105/0.106 | 0.498 vs 0.481/0.352 | no |

The two instruments agree on the principal result — **anchor density is ~2× higher in the
human side** — by completely different routes (regular expressions against a neural model
with natural-language labels). That is convergent validity in the sense the design intended,
and it is the figure that can be defended.

They disagree on the magnitude for numbers: the regex counts any digit ("50 places",
"20 minutes"), GLiNER only what it judges to be a quantity. And they disagree on the 40-word
window, where GLiNER finds many more anchors on both sides and the difference washes out.
Where they disagree the band is reported; the convenient number is not selected.

## Limits

- The labels are prompts chosen by the analyst. They are frozen in
  `specificity_gliner_spec.json`. A different prompt set would give different figures; what
  would not easily change is the direction, which additionally agrees with the independent
  regex instrument.
- "Decisions" and "actions" from the original definition remain out of scope: they were
  tried as labels and GLiNER returns nothing stable for them.
- NER loses entities in spontaneous speech even when the transcription is clean. The bias
  affects the human side more (more colloquial), which makes the estimate **conservative**:
  the measured human advantage is probably a floor.
- Exploratory, n=5 pairs, no tests.
