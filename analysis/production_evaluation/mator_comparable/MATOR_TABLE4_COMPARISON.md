# Mator et al. (2025) Table 4 — comparable metrics on this corpus

> **Read `MATOR_REPLICATION_REPORT.md` alongside this file.** It records what was attempted, how each row was operationalised, what the figures mean, and why this layer was retained as a documented exploration rather than adopted as evaluation evidence. This document holds the numbers only.

**What this is.** Mator et al. (2025) published a five-row table comparing one AI-generated focus group against one human focus group on automatic measures. This is an attempt to compute the same five measures over the present corpus (5 human groups, 30 synthetic sessions) as an external point of comparison.

*Namespace `_comparable_window`. Evidence class `AUTOMATIC_PROXY_EXPLORATORY`. Zero API calls. GENERATED FILE — edit `scripts/mator_comparison_table.py`, not this document.*
*BERTScore: `bert-score` 0.3.13 on transformers 5.13.1 / torch 2.13.0, hash `roberta-large_L17_no-idf_version=0.3.12(hug_trans=5.13.1)` (roberta-large, layer 17, no idf), CPU, fully local.*
*Agreement rows use `paraphrase-multilingual-mpnet-base-v2` cosine, not BERTScore; the bridged variant is read unchanged from `scripts/consensus_dynamics_metrics.py`.*
*Corpus: 5 human focus groups and 30 synthetic sessions, pinned by SHA-256 to `frozen_evaluator_inputs.json`. 1330 relevance pairs and 5011 between-participant pairs over 1816 distinct turns.*

## How to read the raw BERTScore column

**Short version: a raw BERTScore of 83% does not mean 83% of anything.** Two sentences of fluent English that have nothing to do with each other already score about 0.83, because they share grammar, function words and register. The number to read is the *rescaled* one directly underneath each raw row, where 0 means "like two unrelated sentences" and 1 means "identical".

With this model the *expected* raw F1 for a pair of **unrelated** fluent English sentences is **0.8312** — that is the package's own rescaling baseline, i.e. a mean over a random-pair corpus, **not a hard floor**. The self-check demonstrates the point: a deliberately unrelated pair scored 0.8250 raw, which is *below* the baseline (-0.037 rescaled). So a raw figure inside the 0.80–0.95 band is **not** by itself evidence of relevance or similarity. The raw column is kept as the primary because it is the scale Mator's published 82–91% figures live on; the rescaled row underneath each is what should carry any substantive claim.

**Do not over-read the comparison with Mator's absolute percentages.** Mator do not report which BERTScore backbone or layer they used, and the unrelated-pair expectation varies enormously across ordinary choices:

| backbone (default layer) | unrelated-pair expectation (F1) |
|---|---|
| roberta-large_L17 | 0.8312 |
| roberta-base_L10 | 0.8145 |
| distilbert-base-uncased_L5 | 0.6662 |
| bert-base-multilingual-cased_L9 | 0.6315 |
| bert-large-uncased_L18 | 0.4265 |
| bert-base-uncased_L9 | 0.3522 |

*If* they used the package's default English configuration without rescaling, their 83%/82% relevance figures would sit essentially at the unrelated-pair expectation. If they used `bert-base-uncased` — the obvious naive choice for a paper that says only "BERTScore" — 83% would be far above it. Their configuration is not reported, so this comparison is conditional and is stated that way wherever it appears.

**Length control.** truncate every turn on BOTH sides to W words, W = median human participant turn length for that FG (the R3 rule already used by scripts/consensus_dynamics_metrics.py). W per FG: fg1 38, fg2 89, fg3 47, fg4 47, fg5 22.

## Envelope reading

| Metric | Human mean [min–max] | Enriched | Demographics-only | Inside human envelope | Mator AI | Mator Human | n units (H / E / D) |
|---|---|---|---|---|---|---|---|
| Conversational completeness (guide topics reached / 5) | 96.0% [80.0%–100.0%] | 100.0% | 100.0% | yes | 100% | 100% | 5 / 15 / 15 |
| Relevance of Response — BERTScore F1, raw | 83.5% [82.5%–84.0%] | 82.4% | 82.4% | no | 83% | 82% | 5 / 15 / 15 |
|   ... baseline-rescaled | +0.021 [-0.035–+0.055] | -0.044 | -0.045 | no |  |  | 5 / 15 / 15 |
|   ... raw, length-matched (both sides truncated to W) | 84.0% [83.1%–84.3%] | 83.9% | 84.1% | yes |  |  | 5 / 15 / 15 |
|   ... raw, vs the section-opening question only | 83.5% [82.5%–84.0%] | 82.3% | 82.4% | no |  |  | 5 / 15 / 15 |
| Response similarity between participants — BERTScore F1, raw | 84.1% [83.7%–84.7%] | 85.3% | 85.1% | no | 91% | 83% | 5 / 15 / 13 |
|   ... baseline-rescaled | +0.059 [+0.037–+0.092] | +0.131 | +0.120 | no |  |  | 5 / 15 / 13 |
|   ... raw, length-matched (both sides truncated to W) | 84.7% [84.1%–85.1%] | 85.5% | 85.3% | no |  |  | 5 / 15 / 13 |
| Agreement among participants — cosine, strict adjacency, whole turn [PRIMARY] | 53.7% [47.5%–64.1%] | 87.0% | 86.2% | no | 92% | 42% | 5 / 15 / 15 |
|   ... strict adjacency, length-matched | 42.9% [35.5%–54.6%] | 55.8% | 53.2% | partial |  |  | 5 / 15 / 15 |
|   ... bridged universe (existing consensus layer), whole turn | 53.8% [47.6%–64.1%] | 87.0% | 85.8% | no |  |  | 5 / 15 / 15 |
|   ... bridged universe, length-matched | 43.0% [35.5%–54.6%] | 54.5% | 52.0% | yes |  |  | 5 / 15 / 15 |
| Conversational distribution — moderator word share | 2.5% [1.3%–4.4%] | 10.8% | 11.6% | no |  |  | 5 / 15 / 15 |

## Paired reading (n=5 FG pairs)


**Relevance of Response — BERTScore F1, raw** — Δ = synthetic condition mean minus its own human pair

| FG | human | enriched | demographics-only | Δ enr | Δ demo |
|---|---|---|---|---|---|
| fg1 | 84.0% | 82.2% | 82.4% | -1.9 pp | -1.6 pp |
| fg2 | 82.5% | 82.5% | 82.5% | +0.0 pp | -0.0 pp |
| fg3 | 83.5% | 82.5% | 82.2% | -1.0 pp | -1.3 pp |
| fg4 | 83.7% | 82.3% | 82.4% | -1.4 pp | -1.3 pp |
| fg5 | 83.7% | 82.3% | 82.3% | -1.3 pp | -1.4 pp |
| **direction** | | | | **4/5 lower** | **5/5 lower** |

**raw, length-matched (both sides truncated to W)** — Δ = synthetic condition mean minus its own human pair

| FG | human | enriched | demographics-only | Δ enr | Δ demo |
|---|---|---|---|---|---|
| fg1 | 84.3% | 84.0% | 84.0% | -0.4 pp | -0.3 pp |
| fg2 | 83.1% | 83.5% | 83.5% | +0.4 pp | +0.4 pp |
| fg3 | 84.1% | 84.0% | 84.2% | -0.0 pp | +0.2 pp |
| fg4 | 84.2% | 83.7% | 84.1% | -0.5 pp | -0.1 pp |
| fg5 | 84.2% | 84.4% | 84.5% | +0.2 pp | +0.3 pp |
| **direction** | | | | **3/5 lower** | **3/5 higher** |

**Response similarity between participants — BERTScore F1, raw** — Δ = synthetic condition mean minus its own human pair

| FG | human | enriched | demographics-only | Δ enr | Δ demo |
|---|---|---|---|---|---|
| fg1 | 84.7% | 85.2% | 85.2% | +0.5 pp | +0.6 pp |
| fg2 | 83.8% | 85.7% | 85.3% | +2.0 pp | +1.5 pp |
| fg3 | 84.2% | 85.4% | 84.9% | +1.2 pp | +0.8 pp |
| fg4 | 83.7% | 85.2% | 85.2% | +1.4 pp | +1.5 pp |
| fg5 | 84.3% | 85.1% | 85.1% | +0.9 pp | +0.8 pp |
| **direction** | | | | **5/5 higher** | **5/5 higher** |

**raw, length-matched (both sides truncated to W)** — Δ = synthetic condition mean minus its own human pair

| FG | human | enriched | demographics-only | Δ enr | Δ demo |
|---|---|---|---|---|---|
| fg1 | 85.1% | 85.8% | 85.2% | +0.7 pp | +0.2 pp |
| fg2 | 84.1% | 85.5% | 85.1% | +1.5 pp | +1.0 pp |
| fg3 | 84.8% | 85.3% | 85.2% | +0.6 pp | +0.4 pp |
| fg4 | 84.6% | 85.1% | 85.4% | +0.6 pp | +0.9 pp |
| fg5 | 85.0% | 85.5% | 85.7% | +0.5 pp | +0.7 pp |
| **direction** | | | | **5/5 higher** | **5/5 higher** |

**Agreement among participants — cosine, strict adjacency, whole turn [PRIMARY]** — Δ = synthetic condition mean minus its own human pair

| FG | human | enriched | demographics-only | Δ enr | Δ demo |
|---|---|---|---|---|---|
| fg1 | 49.9% | 85.4% | 85.6% | +35.5 pp | +35.7 pp |
| fg2 | 64.1% | 87.4% | 85.1% | +23.3 pp | +21.0 pp |
| fg3 | 50.4% | 87.9% | 87.8% | +37.5 pp | +37.4 pp |
| fg4 | 56.4% | 86.1% | 86.9% | +29.7 pp | +30.4 pp |
| fg5 | 47.5% | 88.2% | 85.6% | +40.7 pp | +38.1 pp |
| **direction** | | | | **5/5 higher** | **5/5 higher** |

**strict adjacency, length-matched** — Δ = synthetic condition mean minus its own human pair

| FG | human | enriched | demographics-only | Δ enr | Δ demo |
|---|---|---|---|---|---|
| fg1 | 43.8% | 54.2% | 53.1% | +10.4 pp | +9.3 pp |
| fg2 | 54.6% | 65.3% | 59.0% | +10.7 pp | +4.3 pp |
| fg3 | 38.8% | 55.2% | 55.1% | +16.4 pp | +16.2 pp |
| fg4 | 41.5% | 58.2% | 53.1% | +16.6 pp | +11.6 pp |
| fg5 | 35.5% | 46.3% | 45.6% | +10.7 pp | +10.1 pp |
| **direction** | | | | **5/5 higher** | **5/5 higher** |

No significance tests. n=5 pairs; replicates are generator variability, never 15 independent observations. Directional consistency only.


### Sensitivity: minimal turns (≤5 words)

Short turns are not distributed evenly between the sides, and they do not score like ordinary turns, so this is a property of the corpus rather than a nuisance to be silently trimmed. Both columns are shown; the metric reported everywhere else is the *all pairs* one.

| Metric | Side | share of pairs that are minimal | all pairs | excluding minimal | Δ |
|---|---|---|---|---|---|
| Relevance of Response | human | 15.9% | 83.5% | 83.1% | -0.4 pp |
| Relevance of Response | enriched | 0.4% | 82.4% | 82.4% | +0.0 pp |
| Relevance of Response | demographics-only | 0.0% | 82.4% | 82.4% | +0.0 pp |
| Between participants | human | 31.0% | 84.1% | 83.7% | -0.5 pp |
| Between participants | enriched | 0.0% | 85.3% | 85.3% | +0.0 pp |
| Between participants | demographics-only | 0.0% | 85.1% | 85.1% | +0.0 pp |

### Conversational completeness — which topics were reached

| Unit | side | topics reached | missing |
|---|---|---|---|
| fg5 | human | 4/5 | 4 |

A topic counts as reached when its guide section carries at least one participant turn. A missing `Question N.` header on the human side makes the topic **unmeasurable, not proven absent**. Every section-opening moderator turn in every unit is listed in `mator_completeness_openers.csv` so the section→question correspondence can be checked by eye; an automatic token-overlap cross-check was built and removed because it flagged all 35 units and discriminated nothing (see `scripts/mator_completeness.py`).

### Conversational distribution — Mator's row format

| Side | Moderator word share | Participants (word share, min–max across participants, mean over units) | n participants |
|---|---|---|---|
| Human (5 FG) | 3% | 10–37% each | 3–5 |
| Synthetic — enriched (15 runs) | 11% | 17–26% each | 3–5 |
| Synthetic — demographics-only (15 runs) | 12% | 15–26% each | 3–5 |

*Mator et al.: AI — M 18%, 3 participants 24-29% each; Human — M 32%, 3 participants 18-26% each. Rosters here are 3–5 participants, not their fixed 3, so the per-participant column is not directly comparable to theirs.*

### What is not in these numbers

- **7 run directories on disk are outside the frozen corpus** and were excluded by name: `macho_meals_fg3_twinpop_run01`, `macho_meals_fg3_twinpop_run02`, `macho_meals_fg3_twinpop_run03`, `macho_meals_fg3_twinpop_run04`, `macho_meals_fg4_twinpop_run01`, `macho_meals_fg4_twinpop_run02`, `macho_meals_fg4_twinpop_run03`. The run list comes from `frozen_evaluator_inputs.json` and every input is SHA-256 verified, so the twin-population arm cannot leak in.
- **2 run(s) are excluded from the section-indexed metric** (`Response similarity between participants`) because the moderator asked guide question 1 while still inside guide section 0, so from that point every section label names a different guide question than its index — and in both runs two consecutive labels carry the same question. Affected: `macho_meals_fg1_demoonly_run01`, `macho_meals_fg4_demoonly_run01`. They remain in the turn-indexed metric (`Relevance of Response`), which does not use section labels. Counts per row are in the `n units` column.
- **2 section×unit cells** fell below the Tier 2b data floor (≥3 participant turns, ≥150 words) or held a single speaker; each is listed individually in `mator_section_floor_skips.csv`.

## Relationship to the existing cosine replication

`analysis/production_evaluation/consensus_dynamics/MATOR_D4_D5_RESULTS.md` (3 August 2026, `scripts/consensus_dynamics_metrics.py`) already reports three Mator rows under Mator's own names, computed with `paraphrase-multilingual-mpnet-base-v2` **cosine similarity**. This document does not supersede it wholesale; the two answer different questions and both should be cited:

| Row | Existing cosine layer | Here |
|---|---|---|
| Agreement | consecutive participant turns, **bridged** universe, R1/R2/R3 | same model and R2/R3 rule on the **strict** participant-follows-participant universe; the bridged figures are carried across unchanged for comparison |
| Relevance | cosine of the turn against the guide's **scripted question** | **BERTScore** of the turn against the **actual preceding moderator turn** — a different construct as well as a different method |
| Between participants | cosine over all cross-speaker pairs, pooled flat | **BERTScore**, averaged within section then across sections, as Mator describe |

The numbers therefore differ by construction and are not interchangeable. Cosine and BERTScore are different methods on different scales: only the two rows Mator explicitly attribute to BERTScore (Zhang et al., 2019) are comparable to their published 83/82% and 91/83%, and only the versions in this document are computed with the actual `bert-score` package.

**A hazard worth recording while the consensus layer is open:** both `scripts/consensus_dynamics_events.py` and `scripts/consensus_dynamics_metrics.py` enumerate runs by listing `comparable_transcripts/`, which now holds 7 `*_twinpop_*` directories that did not exist when those scripts last ran. `_condition_of()` labels anything without `demoonly` as `enriched`, so re-running them today would fold the twin-population arm into the enriched condition mean. The committed outputs (35 units, no twinpop) are clean; the hazard is prospective. Nothing here modifies those scripts.

## Encoder truncation

`roberta-large` truncates at 512 tokens. 1 of 1816 distinct turns (0.06%) reach that limit; the longest turn observed is 512 tokens, median 217. The caveat the consensus layer raised for a 128-token encoder applies here at a higher ceiling: where truncation bites, it bites the long (synthetic) side.

