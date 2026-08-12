# Replication of the Mator et al. (2025) automatic metrics: procedure, results, and disposition

*Namespace `_comparable_window`. Evidence class `AUTOMATIC_PROXY_EXPLORATORY`. Fully
offline; zero API calls. Post-result exploration, declared as such under the amendments
policy.*

**Disposition, stated up front: the metrics reported here were computed, validated and
retained as a documented exploration, and were NOT adopted as evaluation evidence.** The
reasons are set out in §7. The evaluation's primary and secondary evidence remains the
existing framework; this layer neither substitutes for the withheld interpretive metrics
nor supplements them.

---

## 1. Purpose and scope

The evaluation framework used in this study is internal: synthetic focus-group sessions are
compared against paired human transcripts drawn from the same study. That design answers
questions about this corpus but provides no anchor to any externally published measurement
of synthetic focus groups.

Mator et al. (2025), *Exploring Accessible Focus Groups with Cognitive Persona Generation
and AI Agents*, report a five-row table (their Table 4) comparing one AI-generated focus
group against one human focus group, three participants per side, on five automatic
measures. It is, to the best of the present survey, the only directly comparable published
benchmark for synthetic versus human focus-group transcripts.

This report records an attempt to compute the same five measures on the present corpus,
what the attempt produced, and why the resulting figures are not carried forward as
evidence.

**Scope.** Five human focus groups and thirty synthetic sessions (fifteen full-profile,
fifteen demographics-only), pinned by SHA-256 to the frozen evaluator inputs. Nothing in
this layer modifies the frozen corpus definition, the gold-standard package, or the
interpretive metrics held back pending human validation.

---

## 2. What Mator et al. report

| Metric | Their stated method | AI | Human |
|---|---|---|---|
| Conversational completeness | % of prompted topics covered | 100% | 100% |
| Relevance of Response | averaged BERTScore similarity of response to moderator's question | 83% | 82% |
| Response similarity between participants | BERTScore between all responses to each question, averaged | 91% | 83% |
| Agreement among participants | averaged stance-aware sentence similarity between subsequent participant responses | 92% | 42% |
| Conversational distribution | proportion of words spoken by moderator vs. each participant | M 18%, 3 participants 24–29% each | M 32%, 3 participants 18–26% each |

Two properties of that table govern how it can be replicated. First, BERTScore (Zhang et
al., 2019) is cited specifically for two rows — Relevance of Response, and Response
similarity between participants. Second, "Agreement among participants" is described only
as *stance-aware sentence similarity*; no method is specified, so that row cannot be
reproduced literally and can only be approximated.

---

## 3. Procedure

### 3.1 What was newly computed and what was reused

Three of the five rows already had a producer in this repository and were not recomputed.

| Row | Treatment | Producer |
|---|---|---|
| Conversational completeness | newly computed | `scripts/mator_completeness.py` |
| Relevance of Response | newly computed, `bert-score` package | `scripts/mator_bertscore_metrics.py` |
| Response similarity between participants | newly computed, `bert-score` package | `scripts/mator_bertscore_metrics.py` |
| Agreement among participants | reused, plus a strict-adjacency variant | `consensus_dynamics_metrics.py`; `scripts/mator_agreement_strict.py` |
| Conversational distribution | reused, reshaped only | `moderator_word_share` and `participant_word_counts`, already frozen |

The two rows Mator attribute to BERTScore were computed with the actual `bert-score`
package rather than with the sentence-transformer cosine similarity already available in
this repository. The two are different methods that produce different numbers on different
scales; labelling a cosine similarity "BERTScore" would misname the method against a
published benchmark, and the study's own methodology treats naming a method for what it
does as a validity safeguard.

Conversely, because Mator do not specify a method for the agreement row, the existing
cosine computation is a legitimate approximation of their construct there — and is labelled
as cosine, not BERTScore, throughout.

### 3.2 Operationalisation

Mator's design used seven fixed questions asked once each. The sessions in this corpus run
in emergent mode against discussion-guide *sections*, so two of their definitions required
a stated translation:

- **Relevance of Response.** Each participant turn is scored against the most recent
  preceding moderator turn within the comparable window. This includes mid-section probes
  and interjections, not only the section-opening question; a sensitivity variant scored
  against the section-opening question alone is reported alongside.
- **Response similarity between participants.** "Responses to the same question" is
  operationalised as "participant turns within the same guide section" — a wider unit than
  theirs. Pairs are formed between distinct speakers only, averaged within a section, then
  averaged across sections, following Mator's stated order of aggregation.

### 3.3 Configuration

`bert-score` 0.3.13, `roberta-large` layer 17 (the package default for English), no IDF
weighting, no baseline rescaling in the primary figure, on CPU. The encoder truncates at
512 tokens; one of 1,816 distinct turns (0.06%) reached that limit.

---

## 4. Validation performed

- Every corpus input is verified by SHA-256 against the frozen manifest before use, and the
  run list is read from that manifest rather than from a directory listing. Seven run
  directories present on disk but outside the frozen corpus were reported as excluded by
  name rather than silently skipped.
- Batched scoring was proven to reproduce pair-at-a-time scoring exactly (maximum absolute
  difference 0.0), and BERTScore F1 was confirmed symmetric in candidate/reference order,
  so pair direction is immaterial.
- The affine rescaling applied throughout reproduces the package's own
  `rescale_with_baseline` output to within 1.5 × 10⁻⁶.
- A deliberately unrelated sentence pair was scored as a control (see §5.1).
- Two of the thirty synthetic runs were found to carry displaced guide-section labels: the
  moderator asked guide question 1 while the session was still inside guide section 0, so
  every later label names a different question than its index implies, and in both runs two
  consecutive labels carry the same question. These runs are excluded from the
  section-indexed metric with the reason recorded, and retained in the turn-indexed metric,
  which does not consult section labels.
- An automatic token-overlap cross-check on completeness was built and then **removed
  rather than reported**: guide question 2 contributes exactly one content token
  (*decide*), which guide question 4 also contains (*decided*), so every threshold setting
  flagged all thirty-five units. A check that fires on every unit discriminates nothing.
  `mator_completeness_openers.csv` — 176 rows pairing each section-opening moderator turn
  with the guide question its label should carry — was emitted in its place.

---

## 5. Results

| Metric | Human | Synthetic (full profile) | Synthetic (demographics-only) | Mator AI | Mator Human |
|---|---|---|---|---|---|
| Conversational completeness | 96% | 100% | 100% | 100% | 100% |
| Relevance of Response (raw F1) | 83.5% | 82.4% | 82.4% | 83% | 82% |
| — baseline-rescaled | +0.021 | −0.044 | −0.045 | — | — |
| Response similarity between participants (raw F1) | 84.1% | 85.3% | 85.1% | 91% | 83% |
| — baseline-rescaled | +0.059 | +0.131 | +0.120 | — | — |
| Agreement, whole turn | 53.7% | 87.0% | 86.2% | 92% | 42% |
| Agreement, length-matched | 42.9% | 55.8% | 53.2% | — | — |
| Moderator word share | 3% | 11% | 12% | 18% | 32% |

Full per-unit values are in `mator_bertscore_by_unit.csv`; the envelope and paired readings
are in `MATOR_TABLE4_COMPARISON.md`.

### 5.1 The measurement scale

Raw BERTScore does not span a usable 0–1 range. Two sentences of fluent English with no
relation to one another already score approximately **0.831** with this model and layer —
that value is the package's own rescaling baseline, an expectation over a random-pair
corpus. The control confirms it: a sentence about annual rainfall in the Atacama desert,
scored against a moderator question about male friendship, returned **0.825** raw.

A raw figure inside the 0.80–0.95 band is therefore not, by itself, evidence of relevance
or similarity. Every raw figure in this layer is reported with its rescaled companion,
`(raw − 0.831) / (1 − 0.831)`, on which 0 denotes "as similar as two unrelated sentences"
and 1 denotes identity.

### 5.2 Controls applied

Three controls were applied that the published table could not carry, having one group per
side:

- **Turn length.** Synthetic participant turns are roughly 3.5× longer than human ones, and
  a longer turn mentions more and therefore has more opportunity to overlap with any other
  text. Both sides were truncated to W words, W being the median human participant turn
  length for that focus group, and rescored under the identical rule.
- **Adjacency.** The pre-existing agreement computation pairs turns that are consecutive
  *among participants*, which also pairs turns separated by an intervening moderator turn.
  That affects 0.9% of human pairs but 40.5% of synthetic ones, so the two sides were
  formally not the same measurement. The metric was recomputed on strict
  participant-follows-participant adjacency.
- **Minimal turns.** 31% of human between-participant pairs involve a turn of five words or
  fewer, against 0% of synthetic pairs, and such pairs score higher than ordinary ones.

---

## 6. Interpretation

**Conversational completeness does not discriminate.** All thirty synthetic sessions reached
all five prompted topics. The human side reads 96%, and the single shortfall is guide
question 4 in FG5, where the transcript carries no `Question 4.` header — which makes the
topic unmeasurable rather than uncovered. Mator likewise report 100% on both sides. A
measure on which every unit saturates carries no information about fidelity.

**Relevance of Response reproduces the published figures and, in doing so, demonstrates that
the row is uninformative.** This corpus returns 83.5% human against 82.4% synthetic; Mator
report 82% and 83%. Four figures from two corpora, two research topics and two independent
moderator designs fall within 1.5 percentage points of one another. Rescaled against the
unrelated-pair expectation, however, this corpus reads +0.021 and −0.044: both sides sit at,
or fractionally below, what two sentences with nothing in common would score. Every one of
the thirty-five units falls in the narrow band 81.9%–84.1%. The convergence across corpora
is what a statistic pinned to its own baseline produces, not evidence that synthetic
participants answer as relevantly as human ones. Under the length control the small human
advantage disappears entirely.

**Response similarity between participants replicates in sign at approximately one fifth of
the published magnitude.** The two corpora agree closely on the human side (84.1% here, 83%
published); the divergence is on the synthetic side, where Mator report 91% and the highest
single synthetic session here reaches 86.1%. The direction is nonetheless robust: synthetic
above human in 5 of 5 focus-group pairs in both conditions, still 5 of 5 under the length
control, and the gap widens from +1.2 to +1.6 percentage points once minimal turns are
excluded — that is, the short-turn artefact was flattering the human side, not the
synthetic one. Rescaled, the synthetic value is roughly twice the human one. The effect is
real and survives every control applied to it, but it is far smaller than the published
figure.

**Agreement among participants replicates in shape, and roughly two thirds of the effect is
attributable to turn length.** Whole-turn values are 53.7% human against 87.0% synthetic,
5 of 5 paired, against the published 42% and 92%. Under the identical-rule length control
the paired gap falls from +33 to +11 percentage points. The residual remains directionally
consistent in all five pairs, but it is small relative to the spread between human groups
(35.5%–54.6%), so under the control the synthetic sessions fall inside or at the edge of the
human envelope while remaining consistently above their own pair. Both statements are true
and both require reporting.

The strict-adjacency recomputation is worth recording precisely because it changed nothing:
0.537 / 0.870 / 0.862 strict against 0.538 / 0.870 / 0.858 bridged. The universes differ
sharply; the contrast does not.

**Conversational distribution diverges in level and inverts in direction, and is not
comparable across corpora.** Mator's AI moderator spoke less than their human moderator
(18% against 32%); here the synthetic moderator speaks three to four times more than the
human one (11% against 3%). Most of that is a property of the transcription convention
rather than of the agents: the standardized human transcripts record the moderator almost
entirely as bare `Question N.` prompts, so genuine moderator talk — probes, back-channels,
clarifications — is largely absent from the record rather than from the room. Comparing a
3% figure produced under that convention with Mator's 32% is not a like-for-like
comparison. Participant rosters also differ (3–5 here against their fixed 3).

---

## 7. Disposition: why these metrics were not adopted

The layer was computed in full, validated, and is retained as a record. It is not used as
evaluation evidence, for four reasons.

1. **Three of the five rows carry no usable signal.** Completeness saturates at or near 100%
   on both sides of both corpora. Relevance sits at the unrelated-pair expectation on both
   sides. Distribution is not comparable across transcription conventions. A benchmark of
   five rows that discriminates on two is a weak instrument on which to rest a claim.
2. **The two rows that do discriminate measure a different construct from the one at issue.**
   Both are similarity measures. Neither distinguishes sharing a stance from discussing the
   same topic, and the question this study asks about synthetic focus groups is
   interpretive, not lexical. Similarity is a proxy for convergence at best, and the
   evaluation already holds the corresponding interpretive metrics back pending human
   validation precisely because that distinction cannot be automated away.
3. **The comparison against the published absolute figures is conditional on information the
   source does not report.** Mator do not state which BERTScore backbone or layer they used,
   and the unrelated-pair expectation ranges from 0.35 (`bert-base-uncased`) to 0.83
   (`roberta-large`) across ordinary choices. Under the package's English default their
   relevance figures sit at the baseline; under a different common choice they would sit
   well above it, and the reading reverses. No claim resting on their absolute percentages
   can be made unconditionally.
4. **The largest published effect is substantially an artefact of response length.** Applying
   an identical-rule length control to both sides removes roughly two thirds of the
   agreement gap. A metric whose headline result is dominated by verbosity is not a
   dependable basis for a fidelity claim, in either direction.

Accordingly the evaluation's conclusions continue to rest on its established benchmark
framework, and the figures in this directory are registered as
`AUTOMATIC_PROXY_EXPLORATORY` — automatic, deterministic, not LLM-judged, and explicitly not
a substitute for any withheld interpretive metric.

**What the exploration nonetheless establishes, and why it is retained.** The path was worth
following and the record is worth publishing: it documents that a published automatic
benchmark for synthetic focus groups reproduces on an independent corpus while two of its
five rows turn out to be uninformative and a third turns out to be largely a length effect.
That is a substantive observation about the state of automatic evaluation in this area, and
it is also the empirical basis for this study's decision not to pursue an automated-only
evaluation route. Reporting a negative result with its full apparatus is preferable to
either quietly discarding it or quietly adopting it.

---

## 8. Limitations

- Mator's corpus is one group per side with three participants; this corpus is five human
  groups and thirty synthetic sessions with three to five participants. Sampling variability
  on their side is unknown and cannot be estimated from the published table.
- The unit of analysis here is the focus-group pair (n = 5). Replicates are generator
  variability, never fifteen independent observations. No significance tests are reported;
  only directional consistency.
- The agreement row approximates an unspecified method and is not a literal reproduction.
- The section-based operationalisation of "responses to the same question" is wider than
  Mator's fixed-question design, which would tend to *reduce* measured within-question
  similarity on both sides of this corpus relative to theirs.
- Two synthetic runs are absent from the section-indexed metric for the reason given in §4.
- The comparison is between different research topics, moderators and recruitment frames;
  only the metric definitions are held constant.

---

## 9. Artefacts

| File | Contents |
|---|---|
| `MATOR_REPLICATION_REPORT.md` | this report |
| `MATOR_TABLE4_COMPARISON.md` | the numbers, in Mator's Table 4 layout, with envelope and paired readings. Generated — regenerate rather than edit |
| `mator_bertscore_by_unit.csv` | one row per unit (5 human, 30 synthetic), all metrics |
| `mator_bertscore_by_section.csv` | per guide-section breakdown |
| `mator_bertscore_pairs.csv` | all 6,341 scored pairs with full text, word counts and scores |
| `mator_example_pairs.md` | lowest, median and highest scoring pair of each metric, for inspection |
| `mator_agreement_strict.csv`, `mator_agreement_strict_spec.json` | strict-adjacency agreement and the bridge rates |
| `mator_completeness_by_unit.csv` | completeness per unit |
| `mator_completeness_openers.csv` | every section-opening moderator turn against the guide question its label should carry |
| `mator_bertscore_spec.json` | provenance: model, package and dependency versions, input SHA-256s, validation results, exclusions |
| `mator_section_floor_skips.csv` | sections excluded for falling below the data floor |

## 10. Reproduction

The first three are independent of one another; the fourth consolidates them.

```bash
py scripts/mator_completeness.py
```

```bash
py scripts/mator_agreement_strict.py
```

```bash
py scripts/mator_bertscore_metrics.py
```

```bash
py scripts/mator_comparison_table.py
```

The third takes approximately 1.5 hours of local CPU; the others complete in seconds. To
validate the BERTScore installation and the scoring path without recomputing the corpus:

```bash
py scripts/mator_bertscore_metrics.py --self-check
```

---

## 11. Open items recorded during this work

Neither item originates in this layer; both are recorded here because they were identified
while it was built and neither was acted on unilaterally.

1. `scripts/consensus_dynamics_events.py` and `scripts/consensus_dynamics_metrics.py`
   enumerate runs by listing the `comparable_transcripts/` directory, which now contains
   seven `*_twinpop_*` directories belonging to a separate arm. Because `_condition_of()`
   labels anything without `demoonly` as `enriched`, re-running either script would fold
   that arm into the enriched condition mean. Their committed outputs predate those
   directories and are unaffected. Both scripts carry frozen hashes in their own specification,
   so pinning them to the frozen manifest is a scope decision rather than a mechanical fix.
2. Two tests fail for the same underlying reason and predate this work:
   `test_batch_corpus_counts::test_remaining_count_is_derived_from_disk_not_a_constant`
   (41 completed batch keys against 35 frozen units) and
   `test_absence_audit_stage1::test_cache_selection_is_objective_and_unique` (expects two
   rejected documents, now eight). The selection logic is behaving correctly — it rejects
   them with the reason "document not in frozen inputs"; only the hard-coded expected counts
   are stale.

---

*References: Mator, J. et al. (2025), Exploring Accessible Focus Groups with Cognitive
Persona Generation and AI Agents. Zhang, T., Kishore, V., Wu, F., Weinberger, K. Q., &
Artzi, Y. (2019), BERTScore: Evaluating Text Generation with BERT.*
