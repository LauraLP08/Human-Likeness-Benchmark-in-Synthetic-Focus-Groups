# Exploratory analyses

Everything here **was actually run and produced results**. None of it is reported in
detail in the dissertation. It is published because a negative or unstable result that
shaped a methodological decision is evidence, and because several of these strands are
the strongest available argument for why the reported route was taken and not another.

**Read this first:** none of these strands is part of the reported instrument, and
several were closed by an explicit decision not to carry them into the Results. Do not
quote a number from this directory as a finding of the study. Where a strand carries a
formal status label, it is reproduced below.

---

## How this directory is organised

Each strand mirrors the repository layout it was written against:

```
exploratory/<strand>/
  scripts/     the producers, as they sit in scripts/ at the repository root
  analysis/    the artefacts, as they sit under analysis/ at the repository root
  tests/       the tests, as they sit in tests/
  ...          configs, agents, data or session logs where a strand needed its own
```

**To re-run a strand**, copy its subtrees back over the repository root, preserving the
relative paths — `exploratory/<strand>/scripts/x.py` → `scripts/x.py`,
`exploratory/<strand>/analysis/...` → `analysis/...`. The scripts resolve paths from the
repository root and were not modified when they were moved here.

**Two exceptions**, because the frozen metric registry declares them and an integrity
test checks that every declared producer and artefact exists:

- `scripts/d2_length_diagnostics.py` and `scripts/mator_*.py` stayed in the main
  `scripts/`.
- `analysis/production_evaluation/mator_comparable/` stayed in the main tree.

Two further single files were left in the main tree because reported tests assert on
them: `analysis/production_evaluation/inductive_phase_a/POST_A_REPLAN.json` and
`analysis/production_evaluation/emergent_calibration_q3/cross_model_manifest_q3.json`.
Each sits beside a README saying so.

---

## The strands

### `emergent_inductive_coding/` — open coding instead of a fixed codebook

The dissertation's Level 1 is **deductive**: a fixed 11-subtheme codebook from the
original study. This strand asked the complementary question — what does an evaluator
find when it is *not* given a codebook — through a Q3 emergent-calibration exercise
(U01–U07) and a multi-stage inductive pipeline (phase A, stages B–F).

Results, stated with their own caveats:

- **Q3 emergent calibration** closed as `CLOSED_WITH_UNRESOLVED_CASES_NO_FURTHER_HUMAN_ADJUDICATION`.
  Recall 0.6818, strict precision 0.8000 over 44 theme × unit instances.
- The Claude cross-model judge is rated **`USABLE_FOR_CORROBORATION_ONLY`**: it produced
  8 non-verbatim quotations in 315, two of them outright fabricated.
- A metric originally called `grounded_theme_rate` was renamed
  **`literal_evidence_attachment_rate`** because 30 of 30 cases measured quotation
  *literalness*, not substantive warrant. Never describe it as groundedness.
- The inductive accumulation curves have their own figure
  (`analysis/figures/inductive_theme_accumulation_main.png`) and design record
  (`analysis/production_evaluation/final/RETROSPECTIVE_INDUCTIVE_ACCUMULATION_DESIGN.md`);
  they are not the dissertation's Figure 5, which is fixed-codebook coverage.

158 files. Start at `exploratory/emergent_inductive_coding/analysis/production_evaluation/emergent_calibration_q3/`.

### `transportability_within_domain/` — does the Q3 result hold outside Q3?

`EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK`, over guide questions Q1/Q2/Q4/Q5:
18 human themes against 30 Gemini candidates, **all 93 within-unit pairs adjudicated**.

- Recall band **[0.8889, 0.8889]**; strict confirmed precision **0.6000**, upper bound
  0.7667; adjusted precision 0.9667 as an optimistic ceiling.
- `FROZEN_RULE_CLASSIFICATION = DESCRIPTIVELY_COMPATIBLE_WITH_Q3`, reported only
  alongside `BALANCED_INTERPRETATION`: recall-compatible, but with lower strict precision
  and greater thematic proliferation. **The frozen rule keys on recall only** — a
  precision-keyed rule would return a different class on identical data.
- These denominators are **never pooled** with Q3 or with the deductive results.
- The methodological lesson is recorded in `.../hybrid_evaluation/PROTOCOL_DEVIATIONS.md`: the first
  computation used 61 of the 93 pairs, because a similarity screener had excluded 32 and
  its exclusions were treated as adjudications. Auditing the missing 32 left recall
  unchanged and widened the precision band from [0.6000, 0.6333] to [0.6000, 0.7667].
  A screener proposes; only the adjudicator decides.

Start at `exploratory/transportability_within_domain/analysis/production_evaluation/transportability_sample/hybrid_evaluation/HYBRID_TRANSPORTABILITY_RESULTS.md`.

### `transportability_cross_domain_mindfulness/` — the same apparatus, a different topic

One synthetic session on a mindfulness dataset (DS05: 67 turns, 5 participants) chosen
because it matches Macho Meals FG1 in size, so only the *domain* varies.
`EXPLORATORY_OUT_OF_DOMAIN_TRANSPORTABILITY_CHECK`.

- **Six of nine** selected structural metrics fell inside the range of the 15 enriched
  Macho Meals runs. This is one run against a descriptive range from 15. It is not
  evidence of invariance, equivalence or generalisation.
- One exact correspondence stands out: `short_turn_proportion_25w` is **0.000 in all 16
  synthetic sessions across both domains** — the system has never produced a turn under
  25 words. The two *human* baselines differ sharply. Consequence: the synthetic
  moderator's turn share was 3–8× the human's in Macho Meals but only 1.24× here, which
  looks like better fidelity and is not — only the human side moved. **A
  synthetic-to-human structural gap measured in one domain does not isolate a property of
  the system**, and that applies retrospectively to the Macho Meals results.
- Thematic recall is reported as an **assignment-sensitivity envelope [0.048, 0.429]** on
  a denominator of 21 stable codes — not a confidence interval, not a reliability band,
  not a range for a true recall. A blind cross-model audit disagreed with 7 of 22
  evaluator negatives; all 7 are held as `CROSS_MODEL_SEMANTIC_DISAGREEMENTS`
  `AWAITING_HUMAN_ADJUDICATION` and none is counted as present.
- Precision, F1 and synthetic novelty were **withdrawn as not identifiable under a closed
  frame**.
- **Three apparatus components did not port**, and that is itself a reportable cost:
  the transcript standardiser (dataset-specific branches), the comparable-window builder
  (a hardcoded run whitelist and a Macho Meals token set) and the results aggregator
  (which gates on the *shape* of the study design — 30 runs, two named conditions, three
  replicates).
- Prompts were left byte-identical to the Macho Meals runs even though an audit found 7
  domain residues in them, because editing them would have made the prompt a rival
  explanation for any observed difference. The residues did not reach the generated text
  (0 hits across 63 entries).

Start at `exploratory/transportability_cross_domain_mindfulness/analysis/transportability_mindfulness/TRANSPORTABILITY_MINDFULNESS_REPORT.md`.

### `twin_population_arm/` — richness per se, or construct-relevant richness?

A placebo arm on FG3 and FG4: personas with the same *volume* of content as `enriched`,
but thematically irrelevant (census-sampled occupation, household, education — no diet,
no masculinity). A third point on the gradient `demographics-only → twinpop → enriched`.
Pre-registered as `EXPLORATORY_NOT_CONFIRMATORY`, outside the frozen spec.

- The question it answers is *not* "do I still need humans" — that is unanswerable here,
  since every metric in the framework is a distance to the human reference. It is whether
  the `enriched − demographics-only` recall gap is caused by richness itself or by
  richness that is relevant to the construct.
- FG3 is the primary discriminating case, not FG4: both of FG4's channels rest on a
  single run.
- Declared confounder: the placebo personas were rendered by Claude, the same family as
  the generator, because no third-family credential existed. Measurement-side
  independence (generator Claude ≠ evaluator Gemini) is what is preserved.
- 7 sessions were generated (FG3 ×4, FG4 ×3) with Tier-1 coding. **Their session logs,
  comparable windows and evaluator-cache entries are all inside this strand** and are
  deliberately *not* in the main tree — several consumers in `scripts/` enumerate runs by
  listing a directory rather than reading `frozen_evaluator_inputs.json`, and would fold
  this arm into the enriched condition mean if it were left there.
- The pre-registration, four frozen addenda and their SHA-256 deposits are at the top of
  the strand directory.

### `mator_external_benchmark/` — comparison with Mator et al. (2025) Table 4

Five Mator-comparable metrics, registered as `AUTOMATIC_PROXY_EXPLORATORY`. The
artefacts stay in the main tree (`analysis/production_evaluation/mator_comparable/`)
because the frozen registry declares them; only the tests live here.

The findings are largely negative, and that is the point:

- **Raw BERTScore F1 is pinned to a ~0.83 baseline** — roberta-large L17's own
  unrelated-pair expectation. This corpus reproduces Mator's relevance figures to within
  ~1.5 pp (83.5% human / 82.4% synthetic against their 82/83) *while both sides sit at
  that expectation*. The row is close to uninformative, not a successful replication. The
  baseline is model-dependent (0.35 for bert-base-uncased) and Mator do not report their
  configuration, so any claim about where their numbers sit must stay conditional.
- **Only 2 of Mator's 5 rows discriminate.** Completeness and relevance saturate;
  distribution is not comparable across transcription conventions.
- **Between-participant similarity survives every control**: +1.2 pp, 5/5 paired,
  survives length-matching, widens to +1.6 pp excluding minimal turns — but about one
  fifth of Mator's published +8 pp.
- **Agreement replicates in shape then loses two thirds to length** (+33 pp → +11 pp).

Do not cite "Relevance of Response" without rescaling. The authored discussion is in
`analysis/production_evaluation/mator_comparable/MATOR_REPLICATION_REPORT.md`.

### `consensus_llm_coding/` — LLM-coded conversational function

A multi-label turn-function scheme (`agreement`, `disagreement`, `challenge`,
`neutral_elaboration`, with `mixed` **derived** as agreement ∧ disagreement, never
assigned). Status: **`LLM_CODED_HUMAN_VALIDATION_REQUIRED`**. Only an FG1 pilot ran;
FGs 2–5 were never run.

The pilot's headline and the caveat that governs it:

- Per **turn**, synthetic looks far more relational (83.5% / 84.8% against 29.3% human)
  and `mixed` is 18.4% against **0 of 58** human turns.
- Per **clause the contrast inverts** — human 15.82 labels per 100 clauses against 4.99
  and 5.76. The coder assigns ~1–2 labels per turn regardless of turn length, so a
  24-clause synthetic turn saturates. A length-matched sensitivity run is mandatory
  before the per-turn table is quotable, and it was not done.
- A repeatability probe found 83.3% of turns identical across four observations, but
  **both diverging turns diverged on `mixed`**, and the cached baseline was the minority
  answer in both. The reported mixed rate is an under-count.
- Enriched and demographics-only are indistinguishable from each other; all their gaps
  are smaller than the between-run spread within a condition.

**A constraint worth not rediscovering:** `temperature=0` is impossible on
`gemini-3.5-flash` in this project — the parameter is not supported and is omitted from
the request. Every LLM-coded result in this repository therefore runs under unpinned
sampling. Caches freeze a first answer; they do not prove reproducibility.

**A second one:** blind LLM coding across this project is *procedurally* blind, not
*perceptually* blind. Em dashes alone are 100% diagnostic of condition in FG1 (0.00 per
100 participant words human, 0.95–1.46 in all six synthetic runs), and turn length
(48 against 229 words) gives it away too.

Also here: `consensus_scale`, a scale-based coding design that never went past dry run.

### `persona_stress_test/` — persona robustness under adversarial probes

216 generations and 348 adjudications, run live. All 37 preflight gates, both completeness
gates and 24/24 fixtures passed with zero technical repairs.

- False-premise resistance **44/44** and factual calibration **44/44**, both perfect in
  both repetitions.
- The **INSTRUCTION** probe is where the persona actually fails: only ~21/44 hold
  character, and 4/44 quote or claim their system instructions — two of them naming the
  model and its provider explicitly.
- The methodological finding: the boundary between "breaks character without disclosure"
  and "maintains persona and does not disclose" is **unstable**, at generation (2 of 10
  pairs agree) and at judging (41 of 54). All 13 judge flips clustered into 3 of the 7
  request chunks, so batching 8 items per request creates a shared context in which the
  judge's stance can shift for a whole request.

**Closed as `EXPLORATORY_INTERNAL_DIAGNOSTIC_NOT_REPORTED`.** The gates passed, but the
category boundary proved unstable between repetitions and the protocol pre-specified no
substantive thresholds, so it supports no defensible persona-fidelity inference. It discharges no framework indicator, and its rates stay out of the Results
chapter, out of `FINAL_RESULTS_TABLES.xlsx` and out of `metric_registry.csv`. Reopening
it is a new study, not a rerun. The decision record is
`exploratory/persona_stress_test/analysis/production_evaluation/persona_stress_test/PERSONA_STRESS_TEST_V2_EXCLUSION_RECORD.md`.

### `prompt_and_moderator_ablations/` — how the architecture was tuned

The prompt-engineering and moderator-behaviour experiments that shaped the system before
the production campaign: verbosity baselines, length by guide section and position,
moderator over-intervention, moderator drift, attribution ablation, sycophancy re-runs,
memory de-duplication and probing-depth work.

These matter to one dissertation claim: the verbosity difference **persisted across
prompt versions that substantially reduced verbosity**, so it cannot be attributed to a
single badly calibrated prompt. The evidence is in `exploratory/prompt_and_moderator_ablations/findings/`. The 86 configs
in `exploratory/prompt_and_moderator_ablations/examples/` are the ablation run definitions.

### `tier2b_guide_question/` — guide-question-level thematic lists

Registered as `RETIRED_NOT_FOR_FIDELITY`. Section-level theme lists, a discrimination
control, a cross-section control and a human ceiling estimate. Retired because the
construct it measured was not the one the framework needed; the segmentation utility it
produced (`scripts/tier2b_segmentation.py`) is still used by the gold-standard package
builder and therefore stayed in the main tree.

### `length_matched_diagnostics/` — is the gap just length?

`tier1_coverage_by_word_count_curve` and the evidence-localised length-matched proxies,
registered as `AUTOMATIC_DIAGNOSTIC` and `EXPLORATORY`. The producer
(`scripts/d2_length_diagnostics.py`) and the outputs
(`analysis/production_evaluation/results/d2_*.csv`) stayed in the main tree because the
registry declares them; only the test lives here.

The registry's own `tier1_length_matched_recall` and `tier1_length_matched_precision`
remain **`DEFERRED_NOT_IMPLEMENTED`** — the properly length-matched versions were never
built.

### `_design_notes/`

Five research memos in Spanish, written while these strands were being designed:
two integral reviews of the evaluation, the verified-saturation and automatic-consensus
addendum, the consensus-facility design, and an annex of **early, non-systematised
evidence**. That last one is exactly what its title says and should be read as a working
note, not as a result.
