# CONSENSUS_FUNCTION_LLM_EXPLORATORY — pilot results, FG1

*6 August 2026. Evaluator `gemini-3.5-flash`, prompt and configuration frozen before the first
call (`prompt_sha256 = b15c48e0bdaef169…`). 30 successful API calls: 27 coding + 3
repeatability probe. Design: `DESIGN_AND_CODING_SCHEME.md`.*

**Status: `LLM_CODED_HUMAN_VALIDATION_REQUIRED`.** Nothing below is a validated measure. Not
reported with Tier 1 / Tier 2 / Tier 2B, and not merged with
`CONSENSUS_DYNAMICS_EXPLORATORY`. One focus group — descriptive only, no inference.

## 1. Headline table

**Denominator: participant turns only.** Moderator turns excluded: 6 (human), 18/15/16
(enriched runs), 22/17/15 (demographics-only runs).

`agreement_only`, `disagreement_only`, `mixed` and `no_code` are mutually exclusive.
`challenge_any`, `neutral_elaboration_any` and `relational_any` overlap with them.
**Percentages do not sum to 100 by design.**

| | human | enriched | demographics-only |
|---|---|---|---|
| participant turns (denominator) | **58** | **103** (3 runs) | **125** (3 runs) |
| mean words / turn | 48.1 | 232.2 | 232.2 |
| mean clauses / turn | 5.1 | 23.9 | 24.2 |
| agreement only | 27.6% (16/58) | 45.6% (47/103) | 44.0% (55/125) |
| disagreement only | 1.7% (1/58) | 17.5% (18/103) | 20.8% (26/125) |
| **mixed (agreement ∧ disagreement)** | **0.0% (0/58)** | **18.4% (19/103)** | **18.4% (23/125)** |
| challenge (any) | 0.0% (0/58) | 1.9% (2/103) | 1.6% (2/125) |
| neutral elaboration only | 48.3% (28/58) | 15.5% (16/103) | 15.2% (19/125) |
| relational (any of the three) | 29.3% (17/58) | 83.5% (86/103) | 84.8% (106/125) |
| no code applicable | 19.0% (11/58) | 0.0% (0/103) | 0.0% (0/125) |
| **labels per 100 clauses** | **15.82** | **4.99** | **5.76** |
| turns with an evidence failure | 3.4% (2/58) | 1.0% (1/103) | 0.0% (0/125) |
| turns with a normalised quote | 0.0% | 0.0% | 0.0% |

Per-run figures are in `summary_by_condition.csv`. Between-run spread within a condition is
substantial — `agreement_only` ranges 31.2%–61.8% across the three enriched runs and
39.2%–48.6% across the three demographics-only runs — which is the only variance visible at
n = 1 focus group and is larger than the enriched vs demographics-only gap on every row.

## 2. The result that governs how the table may be read

**Per turn, synthetic turns look overwhelmingly more relational (83.5% / 84.8% vs 29.3%).
Per clause, the human side produces 2.7–3.2× MORE labels (15.82 vs 4.99 / 5.76). The contrast
inverts under normalisation.**

The mechanism is visible in the data and is not subtle: the coder assigns roughly one to two
labels per turn **regardless of how long the turn is**. Labels are bounded per turn; text is
not. A 232-word, 24-clause synthetic turn therefore saturates — the question "does this turn
contain agreement anywhere?" is almost trivially yes — while a 48-word, 5-clause human turn
gets one label for far less text.

So the per-turn contrast largely measures **turn length**, not consensus behaviour. This is
the same artefact, in a new method, that the lexical layer documented when its whole-turn
variant produced 33.7% vs 5.0% divergence (`consensus_dynamics/FROZEN_SPEC.md`). The design
anticipated it (§6.1) and required the normalisation that now shows it.

**Consequence:** the length-matched sensitivity described in §6.1 of the design is no longer
optional. The primary result shows a condition gap, which is exactly the trigger condition.
Until it is run, the honest reading of the table is: *the per-turn contrast is confounded with
turn length; the per-clause figure is the one that survives normalisation, and it points the
other way.*

## 3. `mixed` — the finding the metric was built for

**0/58 human turns vs 18.4% in both synthetic conditions.** Direction and rough magnitude
agree with the independent lexical prior (turns bearing both an agreement and a disagreement
marker: 0.3% human vs 2.4% synthetic), and with the N1 coder's unprompted observation that
synthetic turns "buscan ver en un mismo turno el lado de todo". Three methods now point the
same way.

Two things it does **not** establish:

* It is **not** independent corroboration in the strong sense. The lexical layer already found
  this direction, and this layer read the same corpus, so this is the same finding measured
  differently, not a second finding.
* It is length-exposed like everything else in §2: a human turn averaging 5.1 clauses has far
  less room to host two opposed positions than a 24-clause synthetic turn. The mixed rate
  needs the length-matched run before it can be quoted.

`mixed` should be reported on its own axis as **complexity** — multi-position turns — and not
as consensus or dissent. No composite consensus score was computed (design §8.1).

## 4. Reliability: the repeatability probe

Chunk 0 of `macho_meals_fg1_run01`, 12 turns, 4 observations (1 cached primary + 3 repeats).

* **10/12 turns (83.3%) identical across all four observations**; mean Jaccard vs baseline
  **0.917**.
* **Both diverging turns diverged on `mixed`.** T003 and T011: the baseline answer was
  `{disagreement}`, all three repeats returned `{agreement, disagreement}`.

This matters more than the headline number. `mixed` — the metric this layer exists to
measure — is **the least stable label**, and in both cases **the cached baseline is the
minority answer (1 of 4)**. The reported 18.4% mixed rate is built from baseline answers and
is therefore, if anything, an **under**-count.

This is the direct consequence of `temperature=0` being untransmittable on `gemini-3.5-flash`
(design §2.1). The probe did its job: it converted an unverifiable assumption into a measured
17% per-turn flip rate concentrated on the label of interest. One chunk, one condition — it
does not license a corpus-wide reliability claim.

## 5. Losses, and why their direction matters

| Loss | Count | Where |
|---|---|---|
| Turns not returned by the model | 2 | human T024 (4 words), T025 (15 words) |
| Quote shorter than the 3-word minimum | 1 | `fg1_run02` T016, `"Exactly, yeah."` |

Both mechanisms bite **short turns**, and short turns are overwhelmingly human (48 vs 232 mean
words). The dropped human T024 is `"Yeah, I would agree."` — a canonical short agreement, i.e.
precisely the turn type whose loss deflates the human agreement and relational rates. Coverage
was 56/58 human turns vs 228/228 synthetic.

The effect here is small (2 turns, 3.4% of the human side) but it runs **in the same direction
as the headline contrast**, so it cannot be waved off as noise: it is a candidate partial
explanation, not an unrelated defect. The 3-word minimum should be revisited — a genuine
two-word agreement is not weaker evidence than a three-word one.

## 6. Human vs enriched, human vs demographics-only

Descriptive, one focus group, no significance testing.

* **human vs enriched** and **human vs demographics-only** differ on the same rows, in the same
  direction, by similar magnitudes. On every row the human/synthetic gap is far larger than the
  enriched/demographics-only gap.
* **enriched vs demographics-only are close to indistinguishable here**: agreement only 45.6 vs
  44.0, disagreement only 17.5 vs 20.8, mixed 18.4 vs 18.4, relational 83.5 vs 84.8. All of
  these gaps are smaller than the between-run spread *within* each condition (§1).
* The one row where a condition difference exceeds within-condition spread is
  `neutral_elaboration_any` (16.5% enriched vs 35.2% demographics-only) — but `neutral_only` is
  effectively identical (15.5 vs 15.2), so the gap is in *co-occurrence* of neutral elaboration
  with relational labels, not in neutral turns as such. Not interpreted further at n = 1.

**Read at this stage: this layer separates human from synthetic, and does not separate the two
synthetic conditions.** Whether the first separation is about consensus or about turn length is
exactly what §2 leaves open.

## 7. What must happen before any of this is quotable

1. **Length-matched sensitivity run** (design §6.1) — mandatory now, not optional. Synthetic
   turns truncated to the median human participant turn length for FG1, identical rule per
   side, ~22 calls. Until then the per-turn table is not interpretable.
2. **Human validation** (design §9, D2) — the `LLM_CODED_HUMAN_VALIDATION_REQUIRED` flag is not
   lifted by anything in this document.
3. **The other four focus groups are not run** pending review of this pilot.

## 8. Artefacts

| File | Contents |
|---|---|
| `codings_long.csv` | 369 rows, one per turn per label; includes `NONE` and failure rows so the denominator is recoverable from the file |
| `evidence_failures.csv` | the 3 losses in §5, never silently dropped |
| `summary.json` | by-condition and by-run summaries, probe, per-call token log, effective request config |
| `summary_by_condition.csv` | the §1 table plus per-run rows |
| `cache/` | 27 chunk results keyed by blinded-transcript + prompt + effective-config hash; `cache/probe/` holds the 3 repeats |
| `prompt_frozen.txt`, `dry_run_manifest.json` | the frozen prompt and the pre-run manifest |
