# Findings integration scaffold

**Status: SCAFFOLD ONLY.** No substantive conclusion that depends on the Q3 matching is
written here. Sections marked `BLOCKED` stay empty until the researcher's adjudication of
`Emergent_Matching_Q3_POPULATED.xlsx` is returned.

Research question: *to what extent does enriching agent profiles with the study's
available metadata improve thematic, interactional and group-level correspondence with the
paired human focus group, relative to agents configured with demographic information
only?*

Design: 5 FGs × 3 replicates × 2 conditions = 30 synthetic sessions + 5 human transcripts.

---

## 1. Tier 1 — deductive coding (READY)

Evidence class `NOT_IN_REPORTED_INSTRUMENT`. 35/35 inputs evaluated via Batch,
11 subthemes, quote-verified. Feeds subtheme-level recall/precision/F1 per run, and the
FG-level effects table.

**Contributes:** the primary correspondence measure.
**Constraint:** every figure is LLM-coded; human validation status must be stated wherever
it is reported.

## 2. Emergent calibration — Q3 (BLOCKED on matching)

44 human theme × unit instances (16 categories, 76 coder rows) vs 30 machine themes over
U01–U07. Extraction complete and technically validated; matching in progress.

**Contributes:** whether the automated emergent extractor may be used with sampled
verification, under frozen rule B+.
**Blocked until matching returns:** recall vs `union_reference`, precision, grounded /
unsupported / duplicate / uncertain rates, `VALID_NOVEL_THEME` count, fragmentation and
fusion patterns, and the B+ final state.
**Never:** centrality-based results — centrality is `NOT_ASSESSED`.

## 3. Supplementary transportability (BLOCKED on return gate)

Six units, one coder, Q1/Q2/Q4/Q5, 18 themes. Currently `NOT_READY`.

**Contributes:** a signal on whether the Q3 extractor behaves comparably on other guide
questions.
**Constraint:** single coder, six units, four questions, **no inter-coder agreement**, no
generalisation to all questions. **Never pooled numerically with the Q3 calibration** —
different questions, different design, different denominators.

## 4. Structural and interactional metrics (READY)

Turn counts, words per turn, short-turn sensitivities (10w/50w), reference density
(diagnostic, with caveat), chain depth, salience hierarchy (Spearman).

**Contributes:** the interactional and group-level half of the research question, which
thematic coding alone cannot address.
**Constraint:** `_comparable_window` and `_full_run_operational` namespaces are never
pooled.

## 5. Statistical analysis by FG (READY)

n = 5 FG pairs; each cell is the mean of 3 replicates. Both SD levels reported with n.
No confirmatory p-values. Exact sign test exploratory only, ceiling from `n_effective`.

**Contributes:** the effect estimate and its honest uncertainty.
**Constraint:** with n = 5, this describes; it does not confirm.

## 6. FG4 demographics-only (READY, flagged)

Zero subtheme-level overlap at FG4 is granularity-specific: theme-level recall 0.25–0.50
with precision 1.00. Included in the primary analysis with sensitivity. Item `OCA-001` /
`FG4-DEMO-R01-A1` awaits a human verdict on whether run01's A.1 quotes evidence gender
influence on food choice or domestic division of labour.

**Contributes:** the clearest case that granularity choice drives an apparent null.

## 7. Evaluator limitations and forced silences (READY)

- `gemini-3.5-flash` refused synchronous serving three times (503) and served every input
  via Batch; the model was never substituted.
- Validated for Tier 1 deductive coding; that validation **does not transfer** to open
  inductive extraction — which is what §2 measures.
- Tier 2b retired for fidelity.
- Three D2 diagnostics: coverage-by-word-count producer ready but not run;
  `tier1_length_matched_*` remain `DEFERRED_NOT_IMPLEMENTED`.
- Forced silences: content the design could not elicit, recorded so absence is not read as
  evidence of absence.

---

## Integration order, once matching returns

1. Compute the Q3 metrics with explicit numerators and denominators, per unit and
   aggregated, treating **units** as the closest independent basis.
2. Apply rule B+: coverage benchmark `>= 0.6364` **and** no recurrent severe unsupported
   errors **and** complete machine-only adjudication **and** explicit fragmentation/fusion
   review. Emit one of the four frozen final states.
3. Only then, state what the emergent evidence adds to the Tier 1 picture.
4. Keep the supplementary transportability sample descriptive and separate.

## Standing prohibitions

Never report: central/peripheral results, thematic saturation, generalisation beyond
U01–U07/Q3 for the calibration, or any pooling of the supplementary sample with Q3.
