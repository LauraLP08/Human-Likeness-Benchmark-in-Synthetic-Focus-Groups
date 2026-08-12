# Evaluation benchmark — summary

The benchmark measures the extent to which synthetic focus groups replicate the properties
of the human focus groups used as reference. Because focus-group data are constructed in a
situated and collective manner, the evaluation does not verify whether the synthetic data
meet a predefined quality standard; it contrasts them with human data. Each indicator
expresses a gap between the two, and the human transcripts set the benchmark.

The indicators follow the differences the literature documents between synthetic and human
participants — greater verbosity, homogenisation of voices, less dissent, moderator
prominence, lower specificity — and incorporate findings from earlier work on synthetic
focus groups and the evaluation of persona agents (Zhang et al., 2024; Mator et al., 2025;
Novelli et al., 2026; Amirova et al., 2024).

**The comparison is always made at group level, never at participant level.** Each human
group has a single transcript; the five taken together show the extent to which groups
differ, and where a metric allows it that variation becomes the criterion for judging the
distance between a synthetic group and its human counterpart.

## The three levels

| Level | What it asks |
|---|---|
| **1 — Thematic fidelity** | Do the themes the human participants raised reappear in the synthetic sessions, with what precision, across how many participants, and how does the repertoire accumulate as groups are added? |
| **2 — Interaction process** | Do those themes emerge through a recognisable group discussion, or as isolated answers to the moderator? |
| **3 — Speaker distinctiveness** | Did participants maintain unique, recognisable identities, or did they blend into a single generic voice? |

## The twelve indicators

This is the benchmark as reported. Column headings follow the dissertation's Appendix D.

### Level 1 — Thematic fidelity

| # | Indicator | What it compares | Operational evaluation | Evidence source |
|---|---|---|---|---|
| 1 | Thematic repertoire coverage | The proportion of a fixed thematic universe observed across all focus groups in one complete replicate. | Take the union of verified themes across the G focus groups belonging to replicate r. Keep synthetic replicates separate. If no defensible fixed thematic universe exists, report only the number of distinct themes observed. | LLM or human coding applied identically to both corpora; every positive decision supported by a verified quotation. |
| 2 | Theme recurrence across focus groups | Whether each theme appears with comparable regularity across focus groups. | For every theme *t* and replicate *r*, count the focus groups containing verified evidence. Compare theme-level recurrence profiles rather than pooling themes or synthetic replicates. | Verified deductive theme-by-focus-group presence matrix. |
| 3 | Theme coverage accumulation | How quickly the observed fixed-codebook repertoire accumulates across ordered focus groups. | Cumulatively unite themes after each focus group under a declared ordering π. Normalise by that replicate's final repertoire when comparing curve shape. Test alternative orderings when the sequence is not intrinsic. | Verified presence matrix + declared focus-group ordering. |
| 4 | Thematic recall | How much of the paired human theme set is recovered by the synthetic session. | Compute within each paired human–synthetic session before aggregating across focus groups, replicates or conditions. An empty human denominator is undefined, not zero. | Verified deductive coding. |
| 5 | Thematic precision | How much of the synthetic theme set also occurs in the paired human reference. | Compute within each paired session. An empty synthetic denominator is undefined. A non-empty but disjoint pair of sets produces measured zeros. | Verified deductive coding. |
| 6 | Participant reach | How widely each present theme is voiced within a session. | For every present theme, count distinct speakers with verified evidence. Use the actual session participant count as denominator; summarise across present themes and optionally report whole-focus-group reach. | Speaker-linked verified quotations. |

### Level 2 — Interaction process

| # | Indicator | What it compares | Operational evaluation | Evidence source |
|---|---|---|---|---|
| 7 | Turn-length distribution | Whether synthetic participant turns are longer or less concise than human turns. | Count words per participant turn inside the comparable transcript window. Report prespecified length bands and summarise each session by its median before condition-level aggregation. | Standardised participant-turn records. |
| 8 | Between-focus-group variation in turn length | Whether sessions develop different conversational rhythms, or whether one output style is applied regardless of group identity. | Average the three replicates within each focus group first, so that each focus group has one median turn length. Calculate the coefficient of variation across those focus-group values, within each condition. Report the mean, SD and range next to it. | Focus-group median participant-turn lengths, replicates averaged within focus group. |
| 9 | Internally resolved contrast | Whether a turn rhetorically frames multiple positions within itself rather than advancing one for the group to take up. | Count internal contrastive markers with a frozen word list, skipping the opening acknowledgement so that replies to the previous speaker do not count as internal. Report the share of turns that set out two or more positions, and optionally the same count per clause. | Automatic rule-based analysis; construct motivated by qualitative coding. |
| 10 | Contextual-reference density | How densely discourse is anchored in concrete contextual details. | Extract prespecified entity categories, remove direct address and profile fields mechanically restated by agents, and normalise retained mentions by participant words. Report category-specific densities. | Model-extracted entities + deterministic exclusion rules. |

### Level 3 — Speaker distinctiveness

| # | Indicator | What it compares | Operational evaluation | Evidence source |
|---|---|---|---|---|
| 11 | Cross-question speaker attribution | Whether a participant's language is distinguishable from peers and recognisable across guide questions. | Use leave-one-question-out folds: build profiles from other questions and attribute an equal-length held-out fragment. Compare accuracy with fold-specific chance while preserving within-fold clustering. | Offline stylometric classification. |
| 12 | Within-question lexical similarity | Whether participants answering the same question use unusually similar wording. | Create equal-length fragments, calculate every cross-speaker pair within each question, and aggregate question-level medians to the session level. | Offline lexical geometry. |

Appendix D carries one footnote to this table: consensus — the proportion of responses to
another participant expressing agreement, disagreement or neither, compared across focus
groups and conditions — is noted there as a further indicator to measure where feasible. It
is not among the twelve and no value for it is reported.

## Instrument selection

The benchmark favours **automatic, deterministic measures**. This is a design decision: an
instrument that depends on a coding exercise per corpus does not transfer to other
populations, topics, models or architectures, which is what the benchmark exists to enable.
Where a construct admitted both an automatic and an LLM-coded operationalisation, the
automatic one was adopted and the alternative is recorded in
`analysis/production_evaluation/metric_registry.csv` with the state
`NOT_IN_REPORTED_INSTRUMENT`.

## The registry is wider than the benchmark

`metric_registry.csv` is the operational ledger, not the benchmark: its 51 rows also carry
operational diagnostics of the runs (API error rate, forced silences, truncation), length
proxies, the five Mator comparability rows, and retired or superseded entries. The twelve
indicators above are the reported benchmark. Each registry row's `evidence_class` says what
it is:

- `AUTOMATIC_VALIDATED` — reported in the comparative core.
- `AUTOMATIC_DIAGNOSTIC`, `EXPLORATORY`, `AUTOMATIC_PROXY_EXPLORATORY` — computed and
  reported as diagnostic or exploratory, never as a primary claim.
- `REPORTED_VIA_AUTOMATIC_PRODUCER` — the construct is reported and its adopted
  operationalisation is a dedicated automatic producer.
- `NOT_IN_REPORTED_INSTRUMENT` — an alternative operationalisation of a construct the
  benchmark measures another way; kept so the choice of instrument is on the record.
- `DEFERRED_NOT_IMPLEMENTED`, `RETIRED_NOT_FOR_FIDELITY` — specified without a producer, or
  withdrawn as a fidelity indicator.

`persona_stress_test` is an agent-level internal diagnostic that ran outside the reported
benchmark and is kept in `exploratory/persona_stress_test/` with the state
`EXPLORATORY_INTERNAL_DIAGNOSTIC_NOT_REPORTED`. It discharges no indicator and its rates do
not enter the results.
