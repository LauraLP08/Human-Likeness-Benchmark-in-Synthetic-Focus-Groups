# Transferability evidence

The reported benchmark measures one corpus: five Macho Meals focus groups and their thirty
synthetic re-simulations. Two further exercises were run to see how far the apparatus and the
persona construction reach beyond that corpus. Both produced results, and both are published
here with the caveats that govern them.

They answer different questions:

| Folder | Question | What varies |
|---|---|---|
| `another_discussion_guide/` | Does the measurement apparatus work on a different topic, with a different discussion guide? | The domain and the guide |
| `census_built_personas/` | Can agents be built from population statistics instead of participant metadata, and does the thematic gap follow richness or construct relevance? | The source of the persona content |

Neither is a validation. A single run against a descriptive range, or an arm whose personas
were rendered by the same model family as the generator, cannot establish that the benchmark
generalises. What they do is put a bound on what the reported results isolate.

---

## `another_discussion_guide/` — the apparatus on a different topic

One synthetic session was generated on a mindfulness dataset (DS05) using that study's own
discussion guide, and put through the same measurement pipeline.
Classification: `EXPLORATORY_OUT_OF_DOMAIN_TRANSPORTABILITY_CHECK`.

**Why this dataset.** DS05 is 67 turns across 5 participants, against Macho Meals FG1's 64
turns across 5. Only the domain and the guide vary. A larger alternative corpus would have
varied group size, register and persona richness at the same time, and no single result could
then be attributed to the change of topic.

**What it found, and the limit on reading it.** Six of nine selected structural metrics fell
inside the range of the fifteen enriched Macho Meals runs. This is one run against a
descriptive range drawn from fifteen; it is not evidence of invariance or equivalence.

One correspondence stands out and is worth more than the count: `short_turn_proportion_25w`
is **0.000 in all sixteen synthetic sessions across both domains** — the architecture has
never produced a participant turn under 25 words. The two *human* baselines, by contrast,
differ sharply from each other. The consequence matters for how the main results are read:
the synthetic moderator's turn share was 3–8× the human's in Macho Meals but only 1.24× here,
which looks like better fidelity and is not. Only the human side moved. **A
synthetic-to-human structural gap measured in one domain does not isolate a property of the
system**, and that applies to the Macho Meals results as well.

**Thematic recall is reported as a band, not an estimate.** An assignment-sensitivity
envelope of [0.048, 0.429] on a denominator of 21 stable codes — not a confidence interval,
not a reliability band. A blind cross-model audit disagreed with 7 of 22 evaluator negatives;
all 7 are held as `CROSS_MODEL_SEMANTIC_DISAGREEMENTS` `AWAITING_HUMAN_ADJUDICATION` and none
is counted as present. Precision, F1 and synthetic novelty are not identifiable under a
closed frame, so no value is given for them.

**Three components of the apparatus did not port, and that is itself the finding.** The
transcript standardiser carries dataset-specific branches; the comparable-window builder
carries a hardcoded run whitelist and a Macho Meals token set; and the results aggregator
gates on the *shape* of the study design — thirty runs, two named conditions, three
replicates. Keyword-anchored window derivation also failed here, because the guide's welcome
text shares vocabulary with its first question; recorded section indices are the
domain-neutral signal and should be preferred.

**Prompts were left byte-identical** to the Macho Meals runs even though an audit found seven
domain residues in them. Editing them would have made the prompt a rival explanation for any
observed difference. The residues did not reach the generated text: zero hits across 63
entries.

Start at
`another_discussion_guide/analysis/transportability_mindfulness/TRANSPORTABILITY_MINDFULNESS_REPORT.md`.

---

## `census_built_personas/` — agents without participant metadata

A placebo arm on FG3 and FG4. The personas carry the same *volume* of content as the enriched
condition, but their content is drawn from **2021 census cells and microdata** — occupation,
household composition, education — with nothing about diet or masculinity. Seven sessions
were generated and coded. Pre-registered as `EXPLORATORY_NOT_CONFIRMATORY`, outside the frozen
specification.

**The question it answers.** Not "are human participants still necessary" — that is
unanswerable here, since every indicator in the benchmark is a distance to a human reference.
It is narrower and answerable: is the enriched − demographics-only recall gap driven by
persona *richness per se*, or by richness that is *relevant to the construct*? Census-sampled
personas are rich and irrelevant, which places a third point on the gradient
`demographics-only → census-built → enriched`.

**Design decisions fixed in advance.** FG3 is the primary discriminating case, not FG4: both
of FG4's channels rest on a single run. The codebook could **stop** the arm but could never
**select** personas, so that the measured themes could not shape the agents that produce
them. `persona.background` had to be a dict, because a prose string under `persona` is
silently dropped by the renderer.

**A declared confounder.** The personas were rendered by Claude, the same model family as the
generator, because no third-family credential existed. What is preserved is measurement-side
independence: the generator is Claude and the evaluator is Gemini.

**Why this arm is kept apart from the reported corpus.** Its seven runs, their comparable
windows and their evaluator-cache entries all live inside this folder and are deliberately
absent from `analysis/production_evaluation/`. Several consumers in `scripts/` enumerate runs
by listing a directory rather than reading `frozen_evaluator_inputs.json`, and would fold
these runs into the enriched condition mean if they sat in the main tree.

The census sampling apparatus is in `census_built_personas/scripts/`
(`twinpop_census_sample.py`, `twinpop_microdata_sample.py`), its manifests and drawn cells in
`analysis/production_evaluation/twinpop/`, and the pre-registration with its frozen addenda
and SHA-256 deposits at the top of the folder. The ONS source tables themselves are not
redistributed; the download manifest records what was fetched.

---

## Re-running either strand

Both folders mirror the repository layout they were written against: `scripts/` as it sits at
the repository root, `analysis/` as it sits under `analysis/`, and so on. To re-run one, copy
its subtrees back over the repository root preserving the relative paths. The scripts resolve
paths from the root and were not modified when they were moved here.
