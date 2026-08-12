# Cross-domain transportability check — DS05 mindfulness

`CLASSIFICATION = EXPLORATORY_OUT_OF_DOMAIN_TRANSPORTABILITY_CHECK`

Date: 2026-08-03; corrected 2026-08-04. Single focus group, single run, no replication.

---

## 0. What this is, and what it is not

This is a **bounded, exploratory check** of whether the apparatus built for
DS03 Macho Meals (UK) operates on a corpus from a different domain, country,
register and speech genre — DS05, a focus group of certified mindfulness
instructors discussing the design of a self-administered online intervention.

**Never write, on the basis of this document:** "transportability established",
"the system generalises", "validated", "equivalent", "invariant". One group, one
run, no replication, and a human baseline whose speaker identities cannot be
mapped to real people (Section 2.3) — though the labels are stable enough to
count speakers, which is what reach needs (Section 7b.5).

The Macho Meals figures appear only as a **descriptive reference band**. No test
is run between the two domains and the results are never pooled. This follows
the precedent set for the out-of-Q3 check in
`analysis/production_evaluation/transportability_sample/`.

**Three conclusions must always be reported together**, because any one of them
alone misleads:

1. The apparatus largely ported; three components did not, and are named
   (Section 4).
2. The two human corpora are **not the same speech genre** (Section 6).
3. The Mindfulness run **reproduced part of the structural signature** observed
   in Macho Meals — 6 of 9 selected metrics inside the prior synthetic range —
   while the human baselines differ sharply. Several fidelity ratios therefore
   look better here than in Macho Meals without the system having changed. This
   is one run against a descriptive range from 15; it is not evidence of
   invariance or generalisation (Section 7.4).

---

## 1. Design

| | |
|---|---|
| Human baseline | DS05 mindfulness FG1 — 67 turns, 5 participants, 18 moderator turns |
| Reference band | DS03 Macho Meals FG1–FG5 human transcripts |
| Synthetic run | `mindfulness_fg1_run01`, 5 agents, emergent mode, max 90 turns |
| Instrument | **Byte-identical** to the Macho Meals production runs |

The group size match is the reason this dataset was chosen over the deepfakes
corpus: Macho Meals FG1 is 64 turns / 5 participants, DS05 is 67 turns /
5 participants. Only the **domain** varies. The deepfakes corpus would have
varied domain, group size (12), register and persona richness simultaneously,
leaving nothing attributable.

### 1.1 Instrument parity — the decision and its rationale

Every moderator and session knob in `configs/experiment/mindfulness_fg1_run01.json`
is copied unchanged from `configs/experiment/macho_meals_fg1_run01.json`. Only
domain content differs (`session_id`, `research_objective`, `topic_domain`,
`participant_collective_identity`, `moderator_knowledge_brief`, `participants`,
`discussion_guide`). This is enforced programmatically, not by inspection:
`scripts/build_mindfulness_fg1_config.py --check` fails if any instrument knob
diverges.

The prompts were **not** cleaned, despite carrying Macho Meals residue
(Section 3). Rationale: a prompt edited for this run would become a rival
explanation for any observed difference. Instrument parity was chosen over
instrument purity, and the residue is measured and disclosed instead.

---

## 2. Source integrity of the human baseline — read this before using any number

Three source conditions are recorded in `SOURCE_INTEGRITY_FLAGS` of
`data/datasets_transcripts/standardized/mindfulness/fg1/baseline_metadata.json`.

### 2.1 An isolated editorial preamble, removed traceably

Paragraph 34 of the source `.docx`, **mid-dialogue**, reads verbatim:

> "Here's the transcript with the spelling mistakes corrected:"

**The researcher confirmed that the transcript preserves the original speech.
One isolated editorial preamble was removed from the analytical copy and did not
form part of the focus-group dialogue.**

> **Correction.** An earlier version of this report inferred, from the presence
> of this preamble alone, that the dialogue itself had been altered, and on that
> basis declared lexical and stylometric measurement impossible. **Both claims
> are withdrawn in full.** The transcript preserves the original speech; the
> preamble was an isolated editorial artefact and never part of the dialogue.
> Lexical measurement is not impeded — it proceeds in Section 6b, limited only
> by corpus size, which is a feasibility constraint and nothing to do with the
> integrity of the text.

The removal is hash-anchored and reversible on inspection. Record:
`data/datasets_transcripts/standardized/mindfulness/fg1/editorial_removal_record.json`,
produced by `scripts/mindfulness_editorial_removal_record.py`.

| | |
|---|---|
| Status | `EDITORIAL_PREAMBLE_REMOVED — RESEARCHER_CONFIRMED_NOT_PART_OF_SPEECH` |
| Source `.docx` | **never modified**; SHA-256 `1fb240a5…5fd7ca` recorded before any processing |
| Location | non-empty paragraph index 34 |
| Paragraphs before → after | 70 → 69 |
| Paragraphs otherwise modified | **0** |
| Text SHA-256 before | `cd02952a…8d6f7017` |
| Text SHA-256 after | `c6de3a7d…5e1c95ac` |
| Applied to | `transcript.json`, `clean_transcript.txt`, `transcript.txt` |
| Deliberately **not** applied to | `raw_extracted_transcript.txt` — the provenance anchor stays byte-faithful, so the delta remains auditable |

Verified by `tests/test_mindfulness_editorial_removal.py` (12 tests, all passing),
which asserts that the preamble is absent from every analytical artefact, that
every other paragraph is character-identical, that no dialogue was lost with it,
and that the retracted claim no longer appears in `baseline_metadata.json`.

For context: the Macho Meals baselines also carry researcher edits (timestamps
removed, disfluency markers removed in FG2–FG5), documented in their
`researcher_edit_note`. Both corpora are edited; both edits are now documented.

### 2.2 The corpus is not fully de-identified

First names are spoken in the dialogue. Separately, **exactly two agent payloads
carry a personal name**, identified precisely and **left unmodified** pending
authorisation:

| File | Field | Identifier | Provenance of the field |
|---|---|---|---|
| `agents/mindfulness/mf_p2.json` | `opening_intro.text` | **Joanne King** | `observed_external_profile` |
| `agents/mindfulness/mf_p3.json` | `opening_intro.text` | **Erin** (self-introduced) | `observed_external_profile` |

Both payloads carry an `anonymisation_note` asserting the real name was withheld
because the participant is identifiable from their certificate and public
profile. **The `opening_intro.text` field contradicts that note.**

`opening_intro.text` is rendered into the participant system prompt, so both
names were transmitted to the generation model during `mindfulness_fg1_run01`.

Recommended correction, **not applied here**: replace the personal name inside
`opening_intro.text` only, leaving every other field and the professional
description intact, then re-run the contamination audit. Full record in
`thematic_package_corrected.json` → `privacy`
(`PRIVACY_FINDING_IDENTIFIED_NOT_MODIFIED`).

### 2.3 Identity mapping was not established

Transcript speakers are `Speaker 2`..`Speaker 6`; agent payloads are
`MF_P1`..`MF_P5`. **No evidence in either artefact supports any particular
assignment.** The counts match (5 and 5) and that is all that is recorded.
`identity_reconciliation.json` reports `matched: false` for every speaker, with
the reason stated.

**Consequence, stated precisely.** No **persona-fidelity** claim can be made:
nothing links `Speaker 4` to `MF_P2`, unlike Macho Meals where every synthetic
agent corresponds to a named human participant.

**But the labels are stable**, and that is enough for anything that needs only
*counting distinct speakers*. Two measures must therefore be kept apart, because
an earlier version of this report wrongly treated them alike:

| Measure | Status | Why |
|---|---|---|
| **Participant reach, salience rank** | **computable** (Section 7b.5) | needs only distinct-speaker counts, which stable labels give |
| **`reference_density`** | not recoverable (Section 5.1) | needs speakers to be *mutually distinguishable by name in running speech*; `Speaker 2`..`Speaker 6` all reduce to the token `speaker` |

---

## 3. Contamination audit — measured, not assumed

Prompts were **rendered** through the same functions the live run uses, so what
is scanned is what the model receives. This matters:
`core.prompt_renderer.load_system_prompt` strips the file-level comment header,
so provenance comments that mention `macho_meals_fg1_run01` never reach the
model and are correctly absent from the results.

Full record: `analysis/transportability_mindfulness/contamination_audit_mindfulness.json`.

| Surface | Hits | What |
|---|---|---|
| Moderator system prompt | 3 | `new_contradictions` illustrative example: *"gender doesn't influence food choices; just said they'd feel judged ordering a salad in front of mates"* |
| Moderator reflection prompt | 4 | *"shopping habits"*, plus a forbidden-example sentence naming **David, Sam and Isaiah** — real Macho Meals participants |
| Session opening prompt | 0 | clean |
| Participant system prompts (×5) | **0** | **clean** |

**Total: 7 residues, all inside illustrative examples of output *format*, none in
any participant prompt.**

An initial case-insensitive scan of these same rendered surfaces produced 22
hits. All 15 of the difference were the ordinary modal verb *"will"* colliding
with the Macho Meals participant name *Will*; participant names are therefore
matched case-sensitively, capitalisation being the only available signal that
separates a name from its homograph. A separate file-level grep over the other
runtime prompts produced two further false positives of the same kind —
`"TEM`**`PLATE`**`"` and `"rep`**`eating`**`"` — which is why the audit matches
on word boundaries rather than substrings.

The naive scan's 68% false-positive rate is worth recording in its own right: a
contamination audit that has not been checked against its own false positives
will mislead, and in the direction of false alarm.

**Why the residue was left in place:** the moderator system prompt could have
been swapped via the existing `moderator_prompt_override` mechanism without
touching any original file. The reflection prompt could not — it has no override
parameter, and adding one means modifying Stage 1–6 code, which the project's
standing constraints prohibit. A partial clean would have produced an instrument
that neither preserves parity with Macho Meals nor is domain-neutral. Full
parity was chosen deliberately.

**How to report it:** these same 7 residues were present, identically, in every
Macho Meals run. What differs is their *effect*: in Macho Meals the examples
were in-domain and contaminated nothing; here they are foreign content. Equal
bytes, unequal effect. This is a limitation of the instrument, not of the
comparison, and it should be stated in those terms.

---

## 4. Cost of porting the apparatus — what did not transfer

This section is a finding, not housekeeping. It quantifies what a new domain
actually costs.

| Component | Ported? | Detail |
|---|---|---|
| Session config schema | **Yes, unchanged** | All instrument knobs copied; only domain content differs |
| Agent payload loading | **Yes, unchanged** | `agent_payload_path`, no code change |
| Guide → config | **Yes** | Krueger phase mapping applied as documented |
| Moderator/participant prompts | **Yes, unchanged** | Byte-identical; carries 7 residues (Section 3) |
| Human transcript standardizer | **No** | `scripts/standardize_human_focus_group_transcript.py` has dataset-specific branches for QESB and PHIND. A new script was written for DS05: `scripts/standardize_mindfulness_baseline.py` |
| Comparable-window builder | **No** | `scripts/build_comparable_window.py` has a hardcoded `WHITELIST` of the 30 Macho Meals runs, and `comparable_window_boundary.Q1_DISTINCTIVE` is the token set `{favourite, favorite, place, city, friends, spend, male}` — the content words of the Macho Meals Question 1. The algorithm was re-implemented with a mindfulness token set; neither original file was modified |
| Metric **definitions** | **Yes** | Reproduced exactly against the frozen values (Section 5) |
| Metric **aggregator** | **No** | `scripts/aggregate_production_results.py` hardcodes the shape of the Macho Meals design and gates on it: `EXPECTED_HUMAN_TRANSCRIPTS = 5`, `EXPECTED_SYNTHETIC_RUNS = 30`, `EXPECTED_RUNS_PER_GROUP_CONDITION = 3`, `CONDITIONS = ("enriched", "demographics-only")`. A one-group, one-run, single-condition study fails those gates by construction |

**Three of seven components did not transfer.** The reasons differ in kind, and
the distinction matters:

- The standardizer and the window builder hardcode **domain vocabulary** (speaker
  label conventions; Question-1 content words) where a parameter belonged.
- The aggregator hardcodes the **shape of the study design** — five groups, three
  replicates, two conditions. This is the deeper of the two problems: it means
  the analysis layer cannot express a study that is not Macho Meals-shaped, so
  any future domain needs either a design of identical shape or new aggregation
  code.

Notably, the **generation** side ported completely and the **measurement
definitions** ported exactly. What did not port is the **plumbing around** them.
None of this was visible until a second domain was attempted, which is itself
the argument for having attempted one.

---

## 5. Validation of the measurement implementation

The structural metrics were re-implemented rather than imported, so they were
checked against the frozen values before being trusted.
`scripts/structural_metrics_transportability.py --validate` recomputes every
frozen **human** Macho Meals value from
`analysis/production_evaluation/results/structural_interaction_metrics_long.csv`
and refuses to emit mindfulness numbers unless all reproduce.

**Result: PASS — every frozen human value reproduced across FG1–FG5.**

Reaching that required matching three implementation details that were not
documented and had to be recovered from `scripts/aggregate_production_results.py`:

1. **Word counting uses a plain `str.split()`**, *not* `core.session_state.count_words`
   — the project's own documented uniform word-counting rule
   (`docs/length_measurement_rule.md`). `str.split()` counts transcription
   annotations such as `(.)` and `[inaudible]` as words. The two differ by about
   0.3% of total words on these transcripts. **This is a genuine inconsistency
   inside the frozen apparatus.** It was reproduced, not corrected, because
   comparability with the existing results takes precedence — but it should be
   recorded as a defect.
2. `statistics.quantiles` default method (`"exclusive"`) for the IQR.
3. The specific 56-name `AMBIGUOUS_FIRST_NAMES` exclusion list for
   `reference_density`.

Only `AUTOMATIC_VALIDATED` and `AUTOMATIC_DIAGNOSTIC` metrics are computed.
Every `LLM_CODED_HUMAN_VALIDATION_REQUIRED` metric (agreement, disagreement,
challenge, specificity, `profile_*`, `hyper_exactness`) is **absent by design**:
those remain withheld pending the two-coder gold standard, and a new domain does
not change that. Section 5.1 lists everything excluded and why.

### 5.1 `reference_density` fails silently out of domain — a second defect

The frozen `reference_density` returned **0.0** on both DS05 sides. That is not a
result; the metric **could not run**, and said nothing about it. Two independent
failure modes, both new to this domain:

1. **Unrepresentable labels.** The frozen tokenizer is `[a-z]+`, so the synthetic
   roster label `MF_P2` tokenizes to `["mf", "p"]` and the roster key `mf_p2` can
   never match anything. Five of five synthetic labels are unrepresentable. The
   true value is **0.6429**, not 0.0.
2. **Collapsed labels.** The frozen code keys on `key.split()[0]`, so the human
   roster `Speaker 2`..`Speaker 6` all reduce to `"speaker"`. The five
   participants become mutually indistinguishable and the metric degenerates into
   "does this turn contain the word *speaker*". The human figure is therefore
   uninterpretable, and no corrected value can be recovered from this transcript.

Neither case is detected by the frozen implementation, which is the important
part: the registry documents `reference_density` as a **lower bound** when
ambiguous names are excluded, and that caveat is honest — but it does not cover
either failure here, and both return a clean-looking `0.0`.

This script now reports `reference_density` (frozen tokenizer, for
comparability), `reference_density_label_aware`, and two flags —
`reference_density_unrepresentable_names` and `reference_density_labels_collapsed`
— that make `reference_density_valid` false whenever the figure must not be read.
On Macho Meals FG1–FG5 all five are valid and unchanged, so the frozen values
stand.

**A metric that cannot run should say so. This one returned zero.** Any future
domain using coded participant labels — DS04 deepfakes uses `P1.1` — will hit
the same failure.

---

## 6. Human-side result — the two corpora are not the same speech genre

Source: `analysis/transportability_mindfulness/structural_human_side.json`.
`MF` = mindfulness FG1 (Q1-trimmed); `fg1`–`fg5` = Macho Meals human band.

| Metric | MF | fg1 | fg2 | fg3 | fg4 | fg5 | MF vs band |
|---|---|---|---|---|---|---|---|
| participant_turns | 48 | 58 | 28 | 98 | 39 | 123 | inside |
| moderator_turns | 18 | 6 | 5 | 6 | 5 | 5 | **far above** |
| words_per_turn_median | 76.5 | 38.5 | 89.5 | 47.5 | 47 | 22 | inside |
| words_per_turn_iqr | 111.75 | 62.5 | 91.25 | 116.5 | 132.0 | 80.0 | inside |
| short_turn_proportion_25w | 0.208 | 0.431 | 0.036 | 0.367 | 0.359 | 0.529 | inside |
| turn_balance_gini | 0.317 | 0.269 | 0.100 | 0.269 | 0.154 | 0.185 | just above |
| word_balance_gini | 0.362 | 0.196 | 0.200 | 0.218 | 0.283 | 0.281 | above |
| **moderator_turn_share** | **0.269** | 0.094 | 0.152 | 0.058 | 0.114 | 0.039 | **far above** |
| **moderator_word_share** | **0.187** | 0.044 | 0.030 | 0.013 | 0.026 | 0.013 | **4–14×** |
| **participant_participant_adjacency** | **0.455** | 0.825 | 0.719 | 0.893 | 0.791 | 0.929 | **far below** |
| **chain_depth** | **2.67** | 9.67 | 5.6 | 16.33 | 7.8 | 24.6 | **far below** |
| chain_depth_max | 6 | 17 | 7 | 31 | 12 | 36 | far below |

**The pattern is sharp and one-directional.** On measures of *how individual
participants talk* — turn length, its spread, the proportion of short turns —
DS05 sits **inside** the Macho Meals band. On measures of *how the conversation
is structured* — moderator share, participant-to-participant adjacency, chain
depth — DS05 is **far outside** it.

The interpretation is straightforward from reading the transcript: the DS05
moderator is the researcher, who actively participates — answering design
questions about his own trial, defending methodological choices, being
interrogated by the participants. This is an **expert consultation**, closer to
a design review than to the low-intervention consumer focus group DS03
represents.

**This is a property of the human corpus, discovered by the instrument, before
any synthetic data existed.** It is the single most important thing to carry
into Section 7: the synthetic moderator is driven by a prompt whose behaviour
was tuned in a low-intervention genre. If the synthetic run does not reproduce a
27% moderator turn share, that is evidence about *genre mismatch between the two
human corpora*, not evidence that the system fails to transport. Any reading
that conflates the two is wrong.

---

## 6b. Lexical distinctiveness

`CLASSIFICATION = EXPLORATORY_OUT_OF_DOMAIN_LEXICAL_TRANSPORTABILITY_CHECK`

Admissible only because the researcher confirmed the transcript preserves the
original speech (Section 2.1). Every measure is **imported** from
`scripts/lexical_analysis.py` — same tokenisation arms, budgets, deterministic
offsets, Jaccard / Jensen-Shannon / cosine and MATTR windows — so no
specification can drift. Script: `scripts/lexical_transportability_mindfulness.py`.

### 6b.1 Feasibility preflight — 1 of 9 specifications is comparable

The budget-equalised design requires **every** participant on **both** sides to
supply at least `budget` tokens. On DS05 that is a severe constraint:

| Side | Arm | Participants | Min tokens | Limiting speaker | Feasible budgets |
|---|---|---|---|---|---|
| human | content_min3_nostop | 5 | **72** | Speaker 3 | none |
| human | content_min1_nostop | 5 | **72** | Speaker 3 | none |
| human | all_min3_withstop | 5 | 140 | Speaker 3 | 100 |
| synthetic | content_min3_nostop | 5 | 370 | MF_P4 | 100, 200 |
| synthetic | content_min1_nostop | 5 | 381 | MF_P4 | 100, 200 |
| synthetic | all_min3_withstop | 5 | 630 | MF_P4 | 100, 200, 400 |

**Comparable: 1 of 9 — `all_min3_withstop::budget100`.** Eight specifications are
reported infeasible and are **not** computed. No budget was silently lowered, no
value imputed, and the limiting speaker was not dropped to unlock a
specification.

**What that costs.** The Macho Meals analysis derives its confidence from
agreement *across* specifications — a sensitivity verdict. DS05 supports one
specification, and it is the weakest arm (stopwords retained, minimum length 3).
**No sensitivity verdict is possible for DS05**, and none is reported. The single
result below is a point observation, not a sensitivity-confirmed direction.

### 6b.2 Result on the one comparable specification

Within-domain, DS05 human vs DS05 synthetic:

| Measure | Human | Synthetic | Direction |
|---|---|---|---|
| Jaccard (higher = **less** distinct) | 0.1409 | **0.1674** | synthetic less distinct |
| Jensen-Shannon distance (higher = **more** distinct) | 0.8314 | **0.7967** | synthetic less distinct |
| Cosine similarity (higher = **less** distinct) | 0.3822 | **0.4891** | synthetic less distinct |

All three agree. Jaccard ignores word frequency and the other two do not, so
their agreement is the informative case; disagreement would have been a warning.

**Macho Meals on the identical specification — descriptive reference only, never
pooled with DS05, no test run between them:**

| Measure | MM human | MM enriched | DS05 human | DS05 synthetic |
|---|---|---|---|---|
| Jaccard | 0.1686 | 0.2045 | 0.1409 | 0.1674 |
| Jensen-Shannon | 0.8007 | 0.7664 | 0.8314 | 0.7967 |
| Cosine | 0.4241 | 0.4898 | 0.3822 | **0.4891** |

The direction — synthetic participants lexically less distinct from one another
than human participants — holds in both domains. The synthetic cosine values are
near-identical across domains (0.4898 / 0.4891), which is descriptive and not a
tested equivalence.

### 6b.3 Diversity (MATTR) runs the other way

MATTR is a **less** length-sensitive diversity diagnostic. It is **not** evidence
about voice distinctiveness and is reported separately for that reason.

| | DS05 human | DS05 synthetic | MM human | MM enriched |
|---|---|---|---|---|
| MATTR w50 | 0.7912 | **0.8394** | 0.7496 | 0.8203 |
| MATTR w100 | 0.6849 | **0.7374** | 0.6373 | 0.7080 |
| MATTR w200 | 0.5720 | **0.6153** | 0.5225 | 0.5758 |
| TTR (length-sensitive, context only) | 0.1776 | 0.1199 | 0.1730 | 0.1200 |

Synthetic text is **more** lexically varied word-to-word while its five speakers
are **less** distinguishable from one another — in both domains, and by a similar
margin (≈ +0.05 MATTR w50). Rich vocabulary, converging voices. TTR is shown only
for context: synthetic transcripts are longer, and TTR falls with length by
construction.

---

## 7. Synthetic vs human

### 7.1 The run

`mindfulness_fg1_run01` completed the guide **naturally after 41 turns**, all
5/5 sections, without hitting the 90-turn safety cap. 302 API calls, 1,129,198
input tokens, 76,559 output tokens, 29.5 minutes wall clock. For comparison,
`macho_meals_fg1_run01` used 358 calls and 1,134,224 input tokens over 42
minutes — near-identical consumption in a different domain.

One `forced_silence` occurred (`mf_p4`, `engagement_fallback_after_retry`), the
same operational fault class documented for the Macho Meals corpus. It belongs
to the `_full_run_operational` namespace and is never pooled with window metrics.

### 7.2 Comparable window

Derived by `scripts/transportability_synthetic_window.py`. **The keyword
anchoring approach failed and was replaced.** A Q1 token set built from the
mindfulness guide's first question also matched the *opening* entry — the
welcome text contains "mindfulness" and "components" — placing the boundary at
turn 0 and admitting the welcome, the instructions and the closing into the
window. Detected by the residue gate, which returned
`REVIEW [instruction_confidentiality, self_introduction, welcome]`.

The boundary was rebuilt on **recorded section indices** from the per-turn state
snapshots, which carry no domain vocabulary at all. Intro (turns 0–9) and
closing (turns 38–41) excluded; window = turns 10–37, 42 entries, residue gate
**PASS**.

That failure is worth reporting: the frozen apparatus's boundary rule depends on
the guide's first question being lexically distinct from its own welcome text.
In Macho Meals it is; in DS05 it is not. A domain-neutral signal was available
and should be preferred.

### 7.3 Result

`H` = human DS05 (Q1-trimmed). `S` = synthetic DS05 window. `Macho S` = the 15
canonical enriched Macho Meals synthetic runs (range and median).

| Metric | H | S | S/H | Macho S range (med) | S inside Macho S range? |
|---|---|---|---|---|---|
| words_per_turn_median | 76.5 | 326.5 | **4.27×** | 208–284 (235.5) | above |
| short_turn_proportion_25w | 0.208 | **0.000** | 0.00× | 0.000–0.000 (0.000) | **identical** |
| words_per_turn_iqr | 111.75 | 36.75 | 0.33× | — | — |
| moderator_turn_share | 0.269 | 0.333 | 1.24× | 0.306–0.380 (0.320) | **inside** |
| moderator_word_share | 0.187 | 0.162 | 0.86× | 0.080–0.152 (0.104) | just above |
| participant_participant_adjacency | 0.455 | 0.342 | 0.75× | 0.245–0.400 (0.367) | **inside** |
| chain_depth | 2.67 | 2.00 | 0.75× | 1.63–2.27 (2.13) | **inside** |
| chain_depth_max | 6 | 5 | 0.83× | — | — |
| turn_balance_gini | 0.317 | 0.214 | 0.68× | 0.021–0.183 (0.065) | above |
| word_balance_gini | 0.362 | 0.196 | 0.54× | 0.004–0.250 (0.088) | **inside** |
| reference_density (label-aware) | n/r¹ | 0.643 | — | 0.276–0.871 (0.594) | **inside** |
| participant_turns | 48 | 28 | 0.58× | — | — |
| total_words (= length_ratio) | 6671 | 11212 | **1.68×** | — | — |

¹ `NOT_RECOVERABLE_FROM_ANONYMISED_SPEAKER_LABELS` — see Section 5.1.

**`reference_density` must be reported as three separate results, never merged:**

| Result | Value | Status |
|---|---|---|
| Frozen implementation, both sides | `0.0` | **`INVALID_FOR_CODED_LABELS`** — do not interpret |
| Synthetic, label-aware | 18/28 = **0.6429** | valid |
| Human DS05 | — | **`NOT_RECOVERABLE_FROM_ANONYMISED_SPEAKER_LABELS`** |

> Synthetic reference density in Mindfulness (0.643) fell within the range
> observed in Macho Meals synthetic sessions (0.276–0.871) and above the Macho
> Meals human range (0.000–0.187). The corresponding Mindfulness human value was
> not recoverable, so no within-domain synthetic-to-human ratio could be
> estimated.

### 7.4 The finding: partial reproduction of the prior structural signature

**The Mindfulness run reproduced part of the structural signature observed in
Macho Meals: 6 of 9 selected metrics fell within the prior synthetic range.**
The nine indicators, individually, so the count is verifiable:

| # | Metric | Synthetic DS05 | Macho Meals synthetic range | Inside? |
|---|---|---|---|---|
| 1 | short_turn_proportion_25w | 0.000 | 0.000–0.000 | **yes** |
| 2 | moderator_turn_share | 0.333 | 0.306–0.380 | **yes** |
| 3 | participant_participant_adjacency | 0.342 | 0.245–0.400 | **yes** |
| 4 | chain_depth | 2.00 | 1.63–2.27 | **yes** |
| 5 | word_balance_gini | 0.196 | 0.004–0.250 | **yes** |
| 6 | reference_density (label-aware) | 0.643 | 0.276–0.871 | **yes** |
| 7 | words_per_turn_median | 326.5 | 208–284 | no (above) |
| 8 | moderator_word_share | 0.162 | 0.080–0.152 | no (above) |
| 9 | turn_balance_gini | 0.214 | 0.021–0.183 | no (above) |

**What this is not.** It is **one run** compared against a **descriptive range
built from 15 runs**. It is **not** a test of invariance, equivalence or
generalisation, and no such test was performed. A single realisation falling
inside a prior range is consistent with a stable generator; it does not
establish one. The `6/9` count also **incorporates the post hoc repair of
`reference_density`** described in Section 5.1 — that indicator was added to the
comparison after the defect was found, not specified in advance, and the count
would be 5/8 without it.

The one exact correspondence worth noting separately:
`short_turn_proportion_25w` is 0.000 in all 15 Macho Meals enriched runs and
0.000 here. Across 16 synthetic sessions in two domains, **no turn under 25
words has been observed**.

Meanwhile the two *human* corpora are far apart (Section 6): moderator turn
share 0.039–0.151 versus 0.269; adjacency 0.719–0.929 versus 0.455; chain depth
5.6–24.6 versus 2.67.

The two facts together give the central result:

> The human baselines moved a great deal across domains. The synthetic output
> barely moved at all.

**This has a consequence that must not be missed.** On Macho Meals, synthetic
moderator turn share (~0.32) was **3–8× the human** — a large fidelity gap. Here
it is **1.24×**, which read naively looks like *better* fidelity in the new
domain. It is not. The synthetic system produced its usual ~0.33; only the human
baseline moved, because DS05 happens to be a high-intervention genre. The
apparent improvement is an artefact of which human corpus the same fixed
synthetic behaviour is being measured against.

**Therefore: a synthetic-to-human structural gap measured in one domain is not a
property of the system alone, and must never be reported as if it were.** This
is a methodological finding that applies retrospectively to the Macho Meals
results as well, and it is arguably the most useful thing this exercise produced.

### 7.5 Prompt residue did not reach the output

The 7 Macho Meals residues in the moderator scaffolding (Section 3) were scanned
for in the generated text: **0 hits across all 63 entries of the full run**, for
both domain vocabulary (`meat`, `food`, `salad`, `masculin*`, `shopping`, …) and
Macho Meals participant names (`David`, `Sam`, `Isaiah`, `Amir`, `Ibrahim`).

The residue did not propagate. This does not establish that such residue is
harmless in general — only that it did not surface here.

### 7.6 What transported and what did not

**Transported:** the pipeline ran a new domain to natural guide completion at
comparable cost, with well-formed turn-taking, on-topic discussion, and no
degeneration. Nothing about the generation broke.

**Did not transport — and was not expected to, but is now measured:** the
system's structural profile does not track the human baseline of the domain it
is simulating. Verbosity (4.27× the human median), absence of short turns
(0.000 versus 0.208), and shallow participant-to-participant chains (2.0 versus
2.67 here, against 5.6–24.6 in the Macho Meals human corpus) are stable
properties of the generator, not responses to the target corpus.

---

## 7b. Thematic fidelity

`CLASSIFICATION = EXPLORATORY_OUT_OF_DOMAIN_THEMATIC_FIDELITY_CHECK`

### 7b.1 The frame

`HUMAN_DERIVED_RETROSPECTIVE_CODING_FRAME_V1` — **not a validated codebook**, and
it must not be called one. Derived deterministically by
`scripts/build_mindfulness_coding_frame.py` from the researcher's findings
summary (SHA-256 `9637506c…5a1ed27`, never modified): **10 parent themes, 26
codes**. Study objectives, section banners, container headings and the closing
synthesis were **not** treated as codes; 20 paragraphs are excluded with a
recorded reason each. One duplicate label (`Psychoeducation`, under both T06 and
T07) is flagged and deliberately **not merged**.

### 7b.2 Frame verification — four disjoint strata, not one number

Each code required at least one **literal, gate-passing participant quote** in
the human transcript. The gates: the quote must be an exact substring of the turn
it cites; the turn must exist; the turn must be a **participant** turn.

The result is reported as **four disjoint strata**, because collapsing them into
a single "23 verified" figure and then quoting a coverage fraction against a
different denominator would be an error:

| Stratum | n | What it is | Usable as a denominator? |
|---|---|---|---|
| 1 — any valid quote in **some** repetition | 23 | includes codes that were unstable across repetitions | **No** |
| 2 — **stable in both repetitions** | **21** | the codes that are a dependable human reference point | **Yes — the coverage denominator** |
| 3 — unstable between repetitions | 2 | `T05_visualization_as_a_control`, `T07_self_reflection` | No — held `UNRESOLVED` |
| 4 — excluded, no participant speech | 3 | `T09_informed_consent`, `T09_participant_safety`, `T10_multi_site_approach` | No — `UNVERIFIED_SUMMARY_CLAIM` |

**The coverage denominator is 21, not 23.** A code present in only one of two
repetitions is not a stable reference point and cannot sit in a denominator.

Stratum 4 is informative in its own right: two of the three are the whole of
theme T09 (*Ethical Considerations*), which the summary asserts was discussed but
which no participant quote supports. `T10_multi_site_approach` is the cleanest
demonstration that the speaker gate does real work — the multi-site design *is*
in the transcript, but only in the researcher's own turns.

The frame was frozen and hashed (`3f014e35…791ed9`) before the synthetic
transcript was coded.

### 7b.3 Coverage, and what cannot be computed

**Gemini remains the primary evaluator.** Against the 21-code denominator it
placed **1 code** present in both repetitions on both sides
(`T03_importance_of_consistency`): **coverage 1/21 = 0.0476**.

Three quantities that an earlier version of this report published are
**withdrawn**, because the instrument cannot identify them:

| Declaration | Why |
|---|---|
| `PRECISION_NOT_IDENTIFIABLE_UNDER_CLOSED_FRAME` | The instrument is a **closed** human-derived frame: the coder is asked only whether each of 26 predefined codes is present. A synthetic passage matching no code is never surfaced, so the synthetic present-set is bounded by the frame and cannot serve as a precision denominator. The earlier **precision = 1.0 was an artefact of that closure** and is withdrawn. |
| `F1_NOT_IDENTIFIABLE` | F1 requires an identifiable precision. No value should be quoted. |
| `SYNTHETIC_NOVELTY_NOT_ASSESSED` | The earlier statement that there were **no** synthetic themes without a human counterpart is withdrawn. A closed frame cannot detect a theme outside itself, so an empty list is a property of the design, not a finding. Assessing novelty needs an open inductive pass, which was not run. |

### 7b.4 Cross-model semantic disagreements, and the sensitivity envelope

An independent lexical probe contradicted the primary result — the synthetic
transcript carries 49 mentions of sham/control material, 32 of duration and 10 of
"body scan". A **blind Claude audit** was therefore run over every negative
(22 calls, no sampling).

**Claude is a cross-model auditor only. It is not a second primary evaluator and
its output is not a correction to the primary result.** It disagreed on **7 of
22**:

`T01_mind_wandering_awareness`, `T02_formal_practice`, `T02_informal_practice`,
`T04_flexibility`, `T04_gradual_progression`, `T05_difficulties`, `T06_frequency`.

**These are `CROSS_MODEL_SEMANTIC_DISAGREEMENTS`, not validated presences.** The
distinction matters and was previously blurred:

| The gates verify | The gates do **not** verify |
|---|---|
| the quote is an exact substring of the cited turn | **that the quoted passage satisfies the code's operational definition** |
| the cited turn exists | |
| the cited turn belongs to a participant, not the moderator | |

A literal, gate-passing quote is therefore **not** automatic semantic
validation. **No Claude quote is converted into a presence.** All seven remain
`AWAITING_HUMAN_ADJUDICATION`.

Granting the contested assignments arithmetically produces an upper figure:

**`AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE = [0.048, 0.429]`, denominator 21**

| Bound | Value | Derivation |
|---|---|---|
| Lower | 0.048 (1/21) | primary evaluator alone |
| Upper | **0.429 (9/21)** | what follows from accepting **simultaneously and without any human adjudication** the 7 cross-model semantic disagreements **plus** the 1 additional code unstable across the synthetic repetitions (`T10_control_group_design`) |

**This envelope is not a confidence interval, not a reliability band, and not a
range within which a true recall lies.** No evidence establishes that any
contested assignment is correct. The distance between the ends measures
**sensitivity to assignment decisions**, nothing else.

### 7b.5 Participant reach and salience — computable after all

An earlier version declared reach and salience `NOT_RECOVERABLE`. **That verdict
is withdrawn.** It conflated *mapping a label to a real identity* — still
impossible, still not attempted — with *counting distinct speakers*, which the
stable anonymous labels `Speaker 2`..`Speaker 6` fully support.

Human side, denominator **5** identified participants. The single `Unknown
Speaker` turn is unattributed, excluded from the denominator, and contributes no
verified quote. Scored over the 21 stable codes; **mean reach 0.4286**.

| Code | Theme | Speakers | Reach | Salience rank |
|---|---|---|---|---|
| Formal Practice | T02 | 4/5 | 0.80 | 1 |
| Non-reactivity | T01 | 3/5 | 0.60 | 2 |
| Informal Practice | T02 | 3/5 | 0.60 | 2 |
| Flexibility | T04 | 3/5 | 0.60 | 2 |
| Frequency | T06 | 3/5 | 0.60 | 2 |
| Psychoeducation | T06 | 3/5 | 0.60 | 2 |
| Separate Tracks | T06 | 3/5 | 0.60 | 2 |
| Control Group Design | T10 | 3/5 | 0.60 | 2 |
| Importance of Consistency | T03 | 2/5 | 0.40 | 3 |
| Core Components | T04 | 2/5 | 0.40 | 3 |
| Gradual Progression | T04 | 2/5 | 0.40 | 3 |
| Duration | T06 | 2/5 | 0.40 | 3 |
| Metaphors and Analogy | T06 | 2/5 | 0.40 | 3 |
| Focus on Non-Clinical Populations | T08 | 2/5 | 0.40 | 3 |
| Screening | T08 | 2/5 | 0.40 | 3 |
| Focused Attention | T01 | 1/5 | 0.20 | 4 |
| Mind Wandering Awareness | T01 | 1/5 | 0.20 | 4 |
| Difficulties | T05 | 1/5 | 0.20 | 4 |
| Misconceptions | T05 | 1/5 | 0.20 | 4 |
| Contingency Management | T07 | 1/5 | 0.20 | 4 |
| Psychoeducation | T07 | 1/5 | 0.20 | 4 |

Salience tiers: rank 1 → 1 code, rank 2 → 7, rank 3 → 7, rank 4 → 6.

**Synthetic side, `EXPLORATORY_ONLY`.** Denominator 5. Only
`T03_importance_of_consistency` was placed present in both repetitions, reaching
1 of 5 speakers (reach 0.20) against the human 2 of 5 (0.40). **One scored code
carries no weight**, the two sides are not matched participant-to-participant,
and no test is run between them. Shown for completeness, not as a result.

### 7b.6 What this establishes

**The finding is about the instrument, not the system.** A single-evaluator
thematic comparison did not survive an independent read in this domain: roughly a
third of its negatives were contested, and three of the quantities it appeared to
yield — precision, F1 and synthetic novelty — turn out not to be identifiable
under a closed frame at all.

Two caveats bound even the coverage figure:

1. **The frame is human-derived and retrospective**, extracted from a summary *of
   the human transcript*, so the 21-code denominator is partly true by
   construction. It is not a neutral target and it is **not a validated
   codebook**.
2. **Nothing here locates the system's thematic fidelity.** The envelope
   describes how much the answer moves with contested assignment decisions, not
   where the answer lies.

## 8. Limitations

1. **One group, one run, no replication.** No variance estimate. Macho Meals has
   3 replicates × 5 groups; this has 1 × 1.
2. **Speaker labels are anonymous and cannot be mapped to real identities**
   (Section 2.3). This bounds persona-level claims — but **not** speaker
   counting: the labels are stable, so reach and salience are computable
   (Section 7b.5).
4. **The two human corpora are different speech genres** (Section 6), which is
   a confound for any synthetic-vs-human comparison in this domain.
5. **The instrument carries 7 Macho Meals residues** (Section 3), deliberately
   retained for parity.
6. **The apparatus required 3 new components** to run at all (Section 4), one of
   which — the aggregator — is bound to the shape of the Macho Meals design, not
   merely to its vocabulary. "It transports" is true only with those named.
7. **Personas are thinner than Macho Meals'**: DS05 agents carry gender,
   professional profile and years of experience, but no psychometric
   instrumentation comparable to the MRNI scales in DS03, and all five are
   marked `provisional: true`. The synthetic condition here is therefore not the
   same enrichment condition as the DS03 main arm.
8. **The thematic comparison yields an assignment-sensitivity envelope, not an
   estimate** (Section 7b.4). Coverage against the 21-code stable denominator is
   0.048 on the primary evaluator; granting all 7 cross-model semantic
   disagreements plus the 1 unstable synthetic code — none adjudicated — would
   give 0.429. The envelope is not a confidence interval and not a range for a
   true recall.
8b. **Precision, F1 and synthetic novelty are not identifiable** under a closed
   human-derived frame (Section 7b.3). The earlier precision of 1.0 was an
   artefact of frame closure and is withdrawn.
9. **The coding frame is human-derived and retrospective** (Section 7b.1),
   extracted from a summary of the human transcript, so the human denominator is
   partly true by construction. It is not a validated codebook.
10. **Lexical comparison rests on one of nine specifications** (Section 6b.1).
    DS05's least talkative participant supplies 72 content tokens, which makes
    eight specifications infeasible. No sensitivity verdict is possible.

---

## 9. What may be claimed

**May be claimed:**
- The generation pipeline accepted a new domain with no modification to Stage 1–6
  code and no change to any moderator or session parameter, and ran the guide to
  natural completion at consumption comparable to the Macho Meals runs.
- The structural measurement implementation reproduces the frozen human values
  exactly, and applies to an out-of-domain corpus.
- Four of seven apparatus components ported unchanged, and the metric definitions
  reproduced exactly; the three that did not port are identified, with the
  specific hardcoding named in each case.
- The instrument detected a genre difference between the two human corpora
  before any synthetic data existed.
- The measured Macho Meals residue in the moderator scaffolding did not reach
  the generated text in this run (0 hits, 63 entries).
- That the Mindfulness run **reproduced part of the prior structural signature**:
  6 of 9 selected metrics fell inside the Macho Meals synthetic range, and
  `short_turn_proportion_25w` was 0.000 in all 16 synthetic sessions across both
  domains. This is one run against a descriptive range, and the 6/9 count
  includes a post hoc repaired indicator.
- **A synthetic-to-human structural gap measured in one domain does not isolate a
  property of the system**, because the gap moves when the human baseline moves
  even though synthetic behaviour does not. This is a methodological claim and it
  applies retrospectively to the Macho Meals results.

**May not be claimed:**
- That transportability, generalisation, invariance or equivalence is
  established. One run against a 15-run descriptive range supports none of these.
- That `reference_density` differs "three to six times" between synthetic and
  human "in both domains" — the DS05 human value is not recoverable, so no
  within-domain ratio exists for Mindfulness.
- That structural fidelity is *better* in this domain because several ratios sit
  closer to 1. Section 7.4 shows why that reading is wrong.
- A point estimate of thematic recall in this domain, nor that thematic fidelity
  is low — the envelope measures sensitivity to contested assignments, not a
  located value (Section 7b.4).
- Any value for precision, F1, or the number of synthetic-only themes: all three
  are unidentifiable under a closed frame (Section 7b.3).
- That the 7 cross-model disagreements are real presences. They passed the
  literality, turn and speaker gates, which do **not** test correspondence with a
  code's operational definition (Section 7b.4).
- A sensitivity-confirmed lexical direction (Section 6b.1): one specification of
  nine was feasible.
- Codebook validation, thematic equivalence, saturation or meaning saturation.
- Anything about individual persona fidelity in this domain (Section 2.3).
- Anything about thematic fidelity in this domain (Limitation 8).

---

## 10. Artefacts

| Path | Contents |
|---|---|
| `scripts/build_mindfulness_fg1_config.py` | Config builder + instrument-parity checker |
| `scripts/standardize_mindfulness_baseline.py` | DS05 human baseline standardizer |
| `scripts/contamination_audit_mindfulness.py` | Rendered-prompt contamination audit |
| `scripts/structural_metrics_transportability.py` | Metrics + frozen-value validation gate |
| `scripts/transportability_synthetic_window.py` | Synthetic comparable window + comparison |
| `scripts/mindfulness_editorial_removal_record.py` | Editorial-preamble removal record (Section 2.1) |
| `scripts/lexical_transportability_mindfulness.py` | Lexical preflight + analysis (Section 6b) |
| `scripts/build_mindfulness_coding_frame.py` | Derived coding frame v1 (Section 7b.1) |
| `scripts/thematic_transportability_mindfulness.py` | Frame verification, thematic evaluation, QC audit |
| `tests/test_mindfulness_editorial_removal.py` | 12 focused tests for the removal |
| `analysis/transportability_mindfulness/coding_frame/` | Frame, frozen frame, raw Gemini/Claude results, QC audit |
| `.../coding_frame/thematic_package_corrected.json` | **Corrected package**: strata, denominator, sensitivity envelope, reach, closed-frame limits, privacy record |
| `scripts/mindfulness_corrections.py` | Re-derives the corrected package offline |
| `tests/test_mindfulness_thematic_corrections.py` | 38 tests guarding the corrections |
| `configs/experiment/mindfulness_fg1_run01.json` | Session config |
| `data/datasets_transcripts/standardized/mindfulness/fg1/` | Standardized human baseline |
| `analysis/transportability_mindfulness/` | Audit, metrics and this report |
