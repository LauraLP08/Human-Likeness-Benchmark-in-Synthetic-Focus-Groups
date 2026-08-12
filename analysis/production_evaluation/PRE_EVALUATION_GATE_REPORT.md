# Macho Meals — Pre-Evaluation Gate Report

**Date:** 2026-07-30
**Status:** **Three-input preflight COMPLETE via the Batch API — decision GO_TO_BATCH. Synchronous serving returned 503 for the enriched window on three occasions; the Batch path served all three inputs. The remaining 32 inputs (4 human + 28 synthetic) are covered by a separate authorised corpus job.**
**The 30-session evaluation batch has NOT been run.**

---

## 0. Blocking finding — `gemini-3.5-flash` is not serving requests

> **SUPERSEDED, 2026-07-30 late.** This section describes an EARLIER outage, when
> `gemini-3.5-flash` refused even a 16-token probe. That is no longer the state. It
> is retained unaltered below for audit; the current position is in
> *Mandatory Human Stop 2* and *Controlled retry* at the end of this report.
>
> **What changed:** on the later attempt the model **did** serve a probe and **did**
> complete the full human FG1 transcript (5,543 input tokens). It then returned 503
> for the enriched synthetic window on two separate occasions. The earlier claim
> that "a trivial prompt fails identically to a full transcript" no longer holds —
> a trivial prompt and a 5.5k-token transcript both succeeded.

The one-pair preflight **could not complete**. The frozen production evaluator
returned `503 UNAVAILABLE — "This model is currently experiencing high demand"` on
every attempt, including after ~17 minutes of cumulative backoff
(20 s + 60 s + 120 s + 240 s + 300 s + 300 s).

Diagnosis as recorded at that time:

| Check | Result |
|---|---|
| `gemini-3.5-flash` listed for `GEMINI_API_KEY_NEXT` | **yes** — the model is provisioned, not deprovisioned |
| Minimal 16-token probe to `gemini-3.5-flash` × 4 | **0 succeeded / 4 failed**, all 503 |
| Minimal 16-token probe to `gemini-2.5-flash` × 4 | **4 succeeded / 0 failed** |
| Re-probe on a later attempt × 3 | **0 succeeded / 3 failed**, all 503 — outage persists |

**No substitution has been made.** The frozen decision requires stopping and asking
if the evaluator is unavailable, and explicitly forbids silently falling back to
`gemini-2.5-flash`. The pipeline's hard guard would refuse to run on 2.5 in any
case.

### Options — researcher decision required

| # | Option | Notes |
|---|---|---|
| **A** | **Wait and retry.** 503 "high demand" is typically transient; the model is provisioned and was serving on 2026-07-18 (14 logged calls). | Recommended. Costs only time. The preflight is idempotent — re-running resumes from cache. |
| **B** | Retry on a schedule over a longer window and proceed when it clears. | Same as A with automation; no methodological change. |
| **C** | Re-open the evaluator choice. | Would require re-running the evaluator comparison and re-validating; `gemini-2.5-flash` remains **disqualified** at 81.8% Gate-1 agreement against an 85% threshold. Not recommended. |
| **D** | Proceed on 2.5. | **Not available.** Contradicts the frozen decision and is blocked by the pipeline guard. Listed only to record that it was considered and rejected. |

Everything else in this report passed. **The only blocker is provider-side
availability.**

---

## 1. Tests

**Full suite, saved verbatim as
`test_evidence/pytest_full_suite_2026-07-30_d2_proxy_reclassification.txt`:**

```
640 passed, 2 warnings in 35.88s
```

**No failures.** The suite was NOT re-run for the cache-key work; only the focused
tests were, saved as `test_evidence/pytest_focused_2026-07-30_cache_key.txt`:

```
88 passed, 1 warning in 3.07s
```
(15 new effective-config / cache-key tests + 73 aggregation tests.)

### Correction to the previously quoted count

An earlier version of this section quoted `539 passed` from
`test_evidence/pytest_full_suite_2026-07-30.txt` while, in the same breath,
reporting that the new aggregation tests passed. Those two statements did not come
from the same run. That artifact was written at 19:20:25Z; the aggregation test file
was created at 19:43:50Z, 23 minutes later, so the saved run **never collected it**.

Verified rather than inferred: re-running the suite today with that one file ignored
reproduces `1 failed, 539 passed` exactly, and 580 - 539 = 41 was the whole
aggregation file at that point. Earlier artifacts are kept unaltered for audit; they
are simply no longer the quoted evidence. The 640-passed run quoted above is the
current full-suite artifact.

### The former failure — resolved

`test_moderator_prompt_contains_stage_6e_guidance` previously failed on
`"ground the discussion back in grocery-delivery practice"`.

Re-verified before touching it: `run_readiness_audit.csv` shows **32/32 audited runs**
set `moderator_prompt_override = sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md`, so
`prompts/01_MODERATOR_SYSTEM_PROMPT.md` is executed by **zero** canonical runs.

An earlier version of this report said that file lacked the Stage 6E guidance. **It
does not.** The guidance is present; only the domain nouns changed when the prompt
moved off the grocery-delivery study ("concrete food choices and everyday eating
experience"). Six of the eight assertions already passed. The two stale phrases were
updated; **the canonical prompt was not modified.**

---

## 2. Dry-run — exactly 30 synthetic sessions

`py scripts/production_eval_pipeline.py --dry-run`

**35 inputs: 5 human + exactly 30 synthetic.**

| Requirement | Result |
|---|---|
| FG4 enriched = run01 / run04 / run03 | ✓ |
| FG5 enriched = run01 / run03 / run04 | ✓ |
| `macho_meals_fg4_run02` absent | ✓ |
| `macho_meals_fg5_run02` absent | ✓ |
| Cache keys unique | ✓ 105/105 across 3 tiers |
| `assess_session_batch.py` used | ✗ — deliberately not used; it globs the session-log root and would pull in the 12 non-canonical directories |

---

## 3. One-pair preflight — attempted, blocked

Intended: human FG1 vs enriched FG1 canonical replication 2 (`macho_meals_fg1_run02`)
and vs demographics-only FG1 replication 2 (`macho_meals_fg1_demoonly_run02`) —
3 Tier-1 calls.

> **SUPERSEDED.** At the time of writing, the cache was empty. It now holds the
> human FG1 result under the corrected key `068e228d…`. See *Mandatory Human Stop 2*.

Reached the live call and failed on the first, per §0. No partial results were
written at that time.

Everything upstream of the API call was exercised and passed: input loading,
blinding, cache-key derivation, excluded-content verification, and the guard.

---

## 4. Verification checks

### 4.1 Evaluator guard — negative-tested

The guard is verified by attempting to defeat it, not by assertion:

| Scenario | Result |
|---|---|
| `gemini25` (disqualified) | **BLOCKED** |
| `None` → falls back to `thematic_coding._MODEL` | **BLOCKED** |
| Tampered model field | **BLOCKED** |
| Config missing `key_env` | **BLOCKED** |
| `gemininext` | allowed |

This matters because `thematic_coding._MODEL` still defaults to the disqualified
`gemini-2.5-flash` and `validate_tier1_reach_tier2.py` defaults to
`--evaluator gemini25`; a forgotten argument would otherwise select the wrong model
silently.

### 4.2 Effective request configuration

Recorded in every run artefact and encoded in every cache key:

> **SUPERSEDED — this configuration was INCOMPLETE.** It omitted
> `max_output_tokens` and `response_mime_type`, both of which are transmitted. See
> *Effective configuration corrected* at the end of this report. The corrected
> version is:
>
> ```json
> {"max_output_tokens": 32768, "model": "gemini-3.5-flash",
>  "response_mime_type": "application/json", "temperature": null,
>  "temperature_transmitted": false, "thinking_config": null,
>  "thinking_config_transmitted": false,
>  "thinking_level_effective": "model_default_unpinned",
>  "thinking_level_label_in_config": "medium"}
> ```

Originally recorded as (incomplete):

```json
{"model": "gemini-3.5-flash", "temperature_transmitted": false, "temperature": null,
 "thinking_config_transmitted": false, "thinking_level_effective": "model_default_unpinned",
 "thinking_level_label_in_config": "medium"}
```

`thinking_level: "medium"` in `EVALUATOR_CONFIGS` is a **logging label**, never
transmitted — `thematic_coding` attaches a thinking config only for 2.5-class
models. The evaluator-selection validation ran through this same unpinned path, so
the 100% Gate-1 result was obtained under the model default. A cache entry can
therefore never claim a parameter that was not part of the request.

### 4.3 Schema, blinding, quote grounding, denominators

| Check | Result |
|---|---|
| Schema | Tier-1 results validate against `Tier1Result`; unparseable responses retry, then raise |
| Blinding | every speaker label is `Moderator` or `Participant N` in all 35 inputs — **0 violations** |
| Quote grounding | unchanged `verify_codes`: every `present=true` needs a verified substring quote; unverifiable codes are demoted and excluded |
| Denominators | every one of the 44 registry metrics carries an explicit denominator — **0 blank** |

### 4.4 Cache, provenance, no-overwrite

| Property | Implementation |
|---|---|
| Cache key | `sha256(transcript_sha \| tier \| codebook_sha \| prompt_sha \| effective_model_config)` |
| Synthetic keyed on window hash | **verified true for all 30** — no full-session artefact can satisfy a comparable-window lookup |
| No-overwrite | a result is written once per key; an existing file is a cache hit, never a rewrite, with a second existence check before writing |
| Resumable / idempotent | interrupt at any point and re-run; completed inputs return `cache_hit` |
| Provenance per entry | input path, sha, effective config, codebook sha, prompt sha, blind-text sha |
| Prior artefacts reused | **none** — all pre-existing coding is `gemini-2.5-flash` pilot/historical and fails the key |

### 4.5 Non-destructive

Nothing under `output/session_logs/` is written by any pipeline path. Human
transcripts, agents, configs, prompts and the codebook are untouched.

---

## 5. Tier 2b — absent from primary outcomes

**Confirmed.** `metric_registry.csv` contains exactly one Tier 2b entry,
`tier2b_section_theme_lists`, classed `RETIRED_NOT_FOR_FIDELITY`, category
`descriptive`. No Tier 2b recall or precision metric exists in the registry, so
none can enter an outcome, score, recommendation or fidelity claim.

---

## 6. F1 does not replace recall and precision

**Confirmed.** `tier1_f1` is category **`secondary (complementary)`** after the
approved reclassification. The three primary outcomes are `tier1_subtheme_recall`,
`tier1_matched_theme_precision` and `tier1_participant_reach`. The registry entry
states F1 must never substitute for recall and precision nor be a headline number,
and §9 of the specification carries the same wording.

---

## 7. No introduction, participant presentation or closing reached the evaluator

**Confirmed on the text actually queued for the evaluator**, not merely on the
window construction.

- The 30 synthetic inputs are the approved `comparable_transcript.json` windows,
  each beginning at the sub-entry Question-1 offset and ending before the closing
  section.
- The 5 human inputs are complete standardized transcripts, which begin at
  "Question 1." and contain no introduction or closing by nature.
- The pipeline re-checks every blind text for introduction and instruction markers
  (`research purposes`, `no right or wrong`, `45 minutes`, `my name's`,
  `I'll be moderating/facilitating/leading`) and for non-blinded speaker labels:
  **0 problems across all 35 inputs.**
- Window integrity was separately verified by a 335-check hard-fail gate covering
  hashes, verbatim boundary slices, byte-identical subsequent entries, exact closing
  boundary, and per-run plus corpus word reconciliation.

Per-run boundary evidence — original entry, dropped prefix, retained verbatim
substring — is in `comparable_window_boundaries.md` for all 30 runs.

---

## 8. Gold-standard package — two sequential parts, in the field

**Boundary audit passed 15/15** before the package was built
(`gold_standard_boundary_audit.csv`). Same 15 section-3 units; the sample is not
redistributed across guide questions.

| Stratum | n | Source |
|---|---:|---|
| human | 5 | section 3 of FG1–FG5 |
| enriched | 5 | canonical replication 2 — run02 (FG1–FG3), **run04** (FG4), **run03** (FG5) |
| demographics-only | 5 | demoonly_run02 (FG1–FG5) |

Synthetic units are section 3 **intersected with the approved comparable window**,
so coders score exactly the text the evaluator sees.

### 8.1 What is released now — Part 1, emergent

`gold_standard_package/` contains **18 files and nothing else**, enforced by an
allowlist that fails the build on any deviation:

| File | Count |
|---|---:|
| `Coder_A_Part1_Emergent.xlsx`, `Coder_B_Part1_Emergent.xlsx` | 2 |
| `U01.txt` … `U15.txt` | 15 |
| `README.md` | 1 |

Each Part-1 workbook has **Instructions**, **Units** (one row per turn, auto-fitted
so no turn is clipped), **Emergent_Coding** (12 slots per unit,
`central`/`secondary` validation) and **Overflow_Themes** (safe continuation beyond
12). Coders supply a label, a one-sentence description, a verbatim quote and a
relevance rating.

**There is no codebook in the released package.** Part 1 is emergent by design, and
a codebook cannot be unseen.

### 8.2 What is withheld — Part 2, deductive

`gold_standard_part2_withheld/` holds `Coder_A_Part2_Deductive.xlsx` and
`Coder_B_Part2_Deductive.xlsx`. Each adds a **Codebook** sheet and a
**Deductive_Coding** sheet with `0`/`1` validation and a required verbatim quote for
every positive.

Release is per coder and gated:
`build_gold_standard_package.py --release-part2 A|B` refuses unless that coder's
Part 1 has been returned, the **Units sheet is byte-identical to the issued one**,
no rows were added, deleted, duplicated or reordered, every populated theme has all
four fields, every quote is a literal substring **of the issued copy**, every
overflow row carries a `unit_id`, and every unit has at least one theme.
**11 negative tests cover these paths.**

### 8.3 Adjudication — separate workbooks, after the fact

`gold_standard_adjudication/` holds `Adjudication_Part1_Emergent.xlsx` (blinded
theme clustering) and `Adjudication_Part2_Deductive.xlsx` (disagreement
resolution). Neither is coder-facing during coding.

Emergent agreement is **never** computed from unmatched free-text labels: both
coders' themes are pooled per unit, stripped of authorship, randomised, and
clustered by judgement before any comparison with the automated Tier-2 themes.

### 8.4 Scoring

`score_gold_standard.py` runs `structural` → `import` → `emergent-pool` →
`deductive-pool` → `score`. It reports prevalence, raw agreement and Krippendorff's
alpha **globally and per subtheme**, marks codes with insufficient positive
prevalence `NOT_FULLY_VALIDATED`, and treats A.1–A.3 as directly elicited while B–D
are specificity evidence when absent and opportunistic detection when present.
Verified to refuse fabrication: against empty worksheets it reports uncoded cells
and exits non-zero.

All six workbooks were re-opened after writing and scanned for provenance leaks:
**0 across all six**, no hidden sheets, no defined names.

---

### Registry parity is coverage, not completion

`metric_registry.csv` freezes **26** `AUTOMATIC_*` metrics — down from 28, because
the two `tier1_length_matched_*` metrics were reclassified `DEFERRED_NOT_IMPLEMENTED`
(Amendment A1). A test asserts exact set equality, in both directions, between those
26 and what the pipeline accounts for:

| Where | n | Status |
|---|---|---|
| structural/interaction table | 12 | computed here |
| `per_run_metrics.csv` columns | 8 | computed here |
| `_full_run_operational` audits | 5 | already produced, artifact and column verified on disk |
| `tier1_coverage_by_word_count_curve` | 1 | **producer written and tested, NOT YET RUN** |

**Parity is not implementation.** `tier1_coverage_by_word_count_curve` has no value
until the batch produces Tier-1 results; `NOT_YET_RUN_REGISTRY_METRICS` keeps it
separate from the implemented set and a test forbids folding it in. Twenty of 26 are
computed by this aggregator; five more are real numbers in the operational audits
today; one is pending the batch.

**Two metrics are deferred, not delivered.** `tier1_length_matched_recall` and
`tier1_length_matched_precision` need every excerpt coded independently — about 300
further evaluator calls, which are **not scheduled**. They are now
`DEFERRED_NOT_IMPLEMENTED` and sit outside the parity set entirely.

One declared divergence: the registry froze `tier1_f1`, the column is
`tier1_f1_secondary` — the reclassification to secondary is part of the name.
Mapped explicitly in `REGISTRY_METRIC_COLUMNS` rather than left to inference.

### The offline D2 metrics are a proxy, not the specified measurement

`to_blind_text` numbers turns over **non-empty entries only**, so the producer
replicates that filter; indexing raw entries would shift every quote position in any
window containing an empty turn.

The offline metrics measure **where already-coded evidence falls**. The original
specification asked for something else — recomputation on independently coded
excerpts — and this derivation is a **substitute operationalisation**, not what the
spec requested:

| | Deferred `tier1_length_matched_*` | Proxy `evidence_localized_length_matched_*` |
|---|---|---|
| Coder input | the excerpt alone | the whole window |
| Question | what would a coder find here? | where did the cited evidence fall? |
| Code with no quote in the excerpt | may still be found | cannot appear |
| Context effects | absent by construction | fully present |

The proxy is bounded by the evaluator's quote selection: a code supported by a single
quote from turn 4 is invisible in every excerpt excluding turn 4, even where an
independent coder would have coded it. Classified `EXPLORATORY`, excluded from the
`AUTOMATIC_*` set, and a test forbids the deferred names appearing in its output.

### Excerpt construction — one defect corrected

Starts were selected by modular rotation over all entry boundaries. Running forward
only, starts near the **end** cannot reach the target, so they produced excerpts
substantially shorter than it. Wrapping the end back to the start was rejected: that
splices tail onto head and yields an excerpt whose word order never occurred.

Starts now come only from boundaries that can build a contiguous excerpt reaching
**`LENGTH_MATCH_TOLERANCE = 0.90`** — declared, not discovered. K=10 where enough
eligible starts exist; otherwise K and the reason are recorded on every row.
`target_words`, `achieved_words` and `achieved_over_target` are kept per excerpt,
with min/median/max of the ratio per run. A window shorter than the target uses the
whole window and records that exception. An oversized first entry is still included
whole and flagged.

## 9. Carried limitations

1. **Engagement-retry code path** — 14 canonical enriched runs on the earlier path
   (56 forced silences / 2,295 assessments = 2.44%) vs 16 on the current path
   (1 / 2,494 = 0.04%). Direction of thematic bias **indeterminate**.
2. **Volume asymmetry** — synthetic windows run 1.1×–3.0× the human transcripts;
   D2 diagnostics (both arms' ratios, coverage curves, entry-aligned length-matched
   excerpts with target and achieved counts) address but do not remove it.
3. **Psychometric construct vocabulary reaches the enriched prompt** — construct
   names 70/110, scale-direction descriptors 66/110. Raw score values 0/110. The
   claim that psychometrics enter "only as latent dispositions" must not be made.
4. **Contamination scope** — no *textual/verbatim* contamination under the specified
   tests; semantic contamination is not testable by string overlap and is not
   claimed to be absent.
5. **Unpinned thinking level** — a provider-side change to the model default would
   alter evaluator behaviour without changing the cache key. Recorded, not mitigated.

---

## 10. What is ready, and what is needed

**Ready:** frozen inputs (35, hashed), 44-metric registry, whitelist-driven pipeline
with a negative-tested guard, cache and provenance, gold-standard package and
scorer, all Phase 0 and Phase 1 audits.

**Needed before the batch:**

1. **A decision on §0** — the evaluator is not currently serving. Recommended: wait
   and retry (Option A).
2. **Explicit authorisation** to run the 30-session batch, after a successful
   one-pair preflight.

---

## 11. Prepared but NOT executed

Built and verified offline while the evaluator is unavailable. None of it has been
run against the corpus, and none of it touches simulations or original transcripts.

| Artefact | State |
|---|---|
| `scripts/production_eval_pipeline.py` | whitelist-driven, evaluator guard negative-tested, cache/provenance/no-overwrite verified; `--dry-run` lists exactly 30 synthetic sessions |
| `scripts/aggregate_production_results.py` | four levels — session, FG x condition, study replicate, condition — plus paired per-FG effects and a separate enriched-vs-demographics comparison table; **hard completeness gate**; registry-parity check; **71 tests on known values** |
| `scripts/d2_length_diagnostics.py` | `tier1_coverage_by_word_count_curve` plus two **proxy** metrics, derived from verified quote positions with **no evaluator call**; **27 tests on known values**. **Written and tested, NOT YET RUN** — it needs Tier-1 results |
| `analysis/production_evaluation/results/*.csv` (**10 tables**) | **headers only, 0 rows** — schema fixed and reviewable before any number exists; every declared column is populated by the aggregation tests, and a table that stays empty on a complete corpus now fails the suite |
| `results/d2_*.csv` (**3 tables**) | **headers only, 0 rows** — emitted separately by the D2 producer; not part of the 10 aggregator tables. Two are named `d2_evidence_localized_*`, never `length_matched` |
| `results/emergent_and_missed_theme_evidence.json` | schema skeleton, 0 records |
| `results/AGGREGATION_README.md` | the rules the schema encodes |
| `scripts/score_gold_standard.py` | 5 stages: `structural`, `import`, `emergent-pool`, `deductive-pool`, `score`; per-subtheme prevalence/agreement/alpha |
| `scripts/build_gold_standard_package.py --release-part2` | Part-2 release gate, 11 negative tests passing |

### Discipline encoded in the aggregation schema, not left to the write-up

* **Hard completeness gate.** Aggregation refuses to run without exactly 5 human
  transcripts, 3 runs per FG x condition, 5 FGs per study replicate and 3 study
  replicates per condition. A mean over 2 replicates would otherwise read exactly
  like a mean over 3.
* **Every declared column is populated.** Theme-level recall/precision, window word
  and turn counts, study-replicate F1/reach/distinct-subthemes, and `participants_n`
  are all computed. A test asserts no declared column is left entirely blank — an
  empty header reads as a measured quantity that came out null.
* **`within_cell_sd_pooled` is the variance-weighted pooled SD with df**,
  `sqrt(((n1-1)s1^2 + (n2-1)s2^2)/(n1+n2-2))`, not the mean of two SDs. The
  standardised effect `difference_over_pooled_sd` is emitted only when that value is
  defined and non-zero.
* **`n_fgs_favouring_enriched` moved out of the per-condition rows** into
  `condition_comparison.csv`. It is a comparison between conditions; sitting on a
  `demographics-only` row it implied that condition had its own count of FGs
  favouring enriched.
* Replicate values are retained in `*_values` columns; the mean never replaces them.
* The F1 column is named `tier1_f1_secondary`, and recall and precision precede it
  in every table.
* Every reach row carries `reach_implementation_caveat`, with `participants_n` as
  the explicit denominator.
* `namespace` is an explicit column. `_full_run_operational` metrics stay in
  `api_failure_and_fallback_audit.csv` and are never joined into these tables.
* Interpretive metrics have **no column anywhere** — they cannot be reported by
  accident before the gold standard returns.
* A synthetic-only theme is recorded as `synthetic_only_not_observed_in_human`.
* Study replicates are assembled by `canonical_replication_index`; the 15
  transcripts of a condition are never concatenated against 5 humans.

---

## 12. Gold standard — in the field

The two-part package is with the coders. Part 1 (emergent, codebook withheld) is
released; Part 2 (deductive) is withheld until each coder returns Part 1 and it
passes the release gate. The return path is prepared end to end:
`--stage import` -> `--stage emergent-pool` (author-blinded clustering) ->
`--stage deductive-pool` -> `--stage score`.

**No interpretive result withheld by the gold standard is presented anywhere as
validated.** Those metrics are absent from the result schema entirely, so the
question cannot arise by oversight.

---

_No evaluation scoring has been performed. Stopping at Mandatory Human Stop 2._


---

# Mandatory Human Stop 2 — three-input preflight (2026-07-30)

## Recommendation: **NO-GO for the 30-session batch**

Not because of a defect in the pipeline, the inputs or the coding quality — the one
evaluation that completed is clean on every check below. **The provider returned 503
for the one synthetic input that was attempted, and the second was never attempted.**
Two of the three preflight evaluations therefore do not exist, so the preflight has
not been passed and there is nothing to authorise a batch against.

## Model availability

| | |
|---|---|
| Model | `gemini-3.5-flash` — no substitution, no fallback to 2.5 |
| Availability probe | **1 call**, succeeded first attempt (5 in / 1 out tokens) |
| Probe verdict | AVAILABLE |
| Outcome under real load | **503 on the one synthetic input that was attempted** |

The probe succeeded, so the three evaluations were started immediately as
instructed. Availability did not survive contact with the first synthetic payload.

### Failure classification — 503, not a key problem

| Code | Meaning | Observed? |
|---|---|---|
| 401 / 403 | authentication, permissions, API key | **No** — the key authenticated and two calls succeeded |
| 404 | model/endpoint unavailable to the project | **No** — the model resolved and returned normal completions |
| 429 | quota or rate limit | **No** — no quota response was returned |
| 503 | temporary provider unavailability | **Yes** — `"This model is currently experiencing high demand."` |

**The API key was not changed.** A 503 is not evidence about the key.

**What may be said:** one larger synthetic request failed with 503 after a 5-token
probe and a 5,543-token human transcript had both succeeded.

**What may NOT be said:** that request size is associated with the failure. Exactly
one synthetic request was ever issued. With n=1 there is no association to test, and
the second synthetic input was never attempted, so no second observation exists. An
earlier version of this report inferred size-correlation from "the two synthetic
windows"; that inference is withdrawn — see the factual correction below.

**Retries performed: 6** (20/60/120/240/300/300 s — the built-in budget, ~17 min),
all 503. No further probing was done.

## Effective configuration

| Field | Value |
|---|---|
| `model` | `gemini-3.5-flash` |
| `temperature_transmitted` | **false** — not sent |
| `thinking_config_transmitted` | **false** — not sent |
| `thinking_level_effective` | `model_default_unpinned` |
| `thinking_level_label_in_config` | `medium` — a **logging label only**, never a request parameter |

Both temperature and thinking configuration are left at the model's unpinned
default. This is the configuration under which the model was originally qualified.

## Inputs — hashes and cache keys

All three verified present on disk with SHA-256 matching `frozen_evaluator_inputs.json`.

| Input | Path | SHA-256 (first 16) | Tier-1 cache key (first 16) | Status |
|---|---|---|---|---|
| human FG1 | `data/.../standardized/macho_meals/fg1/transcript.json` | `0770659d52d7b2d0` | `3d6fe3bac2248d84` | **computed** |
| enriched FG1 r2 | `.../comparable_transcripts/macho_meals_fg1_run02/comparable_transcript.json` | `a9558195b7692927` | superseded — see below | **attempted, failed 503** |
| demo-only FG1 r2 | `.../comparable_transcripts/macho_meals_fg1_demoonly_run02/comparable_transcript.json` | `f5d5dde7a2d15973` | superseded — see below | **never attempted** |

The synthetic Tier-1 cache keys shown in the original version of this table were
computed under the incomplete effective configuration and no longer apply. See
*Effective configuration corrected* below.

The human input is the complete standardized transcript; both synthetic inputs are
`comparable_transcript.json` windows. **No full synthetic transcript was sent.**

## Tier-1 result — human FG1 (the only one that exists)

| Field | Value |
|---|---|
| Timestamp | 2026-07-30T21:35:06Z |
| Attempts / transient retries | 1 / 0 |
| Elapsed | 43.07 s |
| Input / output / total tokens | 5,543 / 1,674 / 14,208 |
| JSON schema valid | Yes |
| Codes present | **9 / 11** |
| Supporting quotes | 15 |
| Quote verification | **15 / 15 (100%)** |
| Codes demoted or rejected | **0** |
| Participants (reach denominator) | 5 |
| Warnings / undefined results | None |
| Excluded-content problems | 0 |

Recall, precision and F1 are **not computable**: they are defined against a paired
synthetic run, and neither synthetic evaluation exists. No F1 is reported, and none
would be primary if it were — `tier1_f1_secondary` is secondary/complementary.

### Codes and evidence

| Code | Present | Voiced by | Reach | Quotes (turn → speaker) |
|---|---|---|---|---|
| A.1 | yes | P2, P5 | 0.40 | T030 P5, T032 P2 |
| A.2 | yes | P1, P3 | 0.40 | T024 P3, T027 P1 |
| A.3 | yes | P4 | 0.20 | T031 P4 |
| B.1 | yes | P4 | 0.20 | T049 P4 |
| B.2 | yes | P1, P2 | 0.40 | T045 P1, T046 P2 |
| B.3 | yes | P3, P4 | 0.40 | T037 P4, T038 P3 |
| B.4 | yes | P2 | 0.20 | T042 P2 |
| C.1 | yes | P2, P4 | 0.40 | T049 P4, T054 P2 |
| C.3 | yes | P1, P2 | 0.40 | T043 P1, T054 P2 |
| C.2 | **no** | — | — | — |
| D | **no** | — | — | — |

Representative quotes, so this can be reviewed without opening the JSON:

* **A.1** T030 P5 — *"so I feel gender influences what I do eat."*
* **A.2** T027 P1 — *"I don't think I've ever made a decision on where to eat on like, any influences, like gender-wise."*
* **A.3** T031 P4 — *"Um, I don't think gender influences what I eat. Maybe how much I eat with my like guy friends…"*
* **B.2** T045 P1 — *"Certainly like, in Scotland, it's like a proper culture, like eating meat as well, though."*
* **B.3** T037 P4 — *"I'm quite fond of the gym, so I have, like, protein in every meal. So, like, chicken, tuna, beef."*
* **C.1** T054 P2 — *"about the like the actual ingredients… What am I actually eating here?"*
* **C.3** T043 P1 — *"It's just a bit bland, innit, sometimes? It just doesn't taste right."*

## Substantive inspection (human FG1)

Beyond schema validity, each quote was checked against the exact cited turn.

1. **Codes match the cited content** — yes. A.1/A.2/A.3 partition the gender-influence
   question into affirms / denies / denies-for-content-but-affirms-for-quantity, and
   each quote states that position explicitly. A.2 and A.3 are genuinely distinct, not
   a split of one utterance.
2. **Quotes literal and from the right input** — **15/15 literal in their cited turn.**
   Two initially failed my check (B.4 T042, C.3 T054); that was a defect in *my* check,
   which used `splitlines()` on the blind text. Turn content contains newlines, so a
   single turn spans several rendered lines. Re-verified against per-entry records:
   both are exact. No coding defect.
3. **Obvious false positives** — none identified. The weakest is **B.1** (*"just chicken
   is, it's made of chicken"*), which is terse; in context it is a whole-food/processing
   contrast and defensible, but it is the one a human coder is most likely to dispute.
4. **Clearly omitted human themes** — C.2 and D absent. Reviewing the transcript, no
   evident C.2 or D content was missed; this looks like true absence, not under-coding.
   Not independently adjudicated — that is what the two-coder gold standard is for.
5. **Synthetic-only themes** — not applicable: no synthetic result exists. The
   `synthetic_only_not_observed_in_human` labelling is implemented and untriggered.
6. **Length asymmetry inflating recall / deflating precision** — **cannot be assessed,
   and is the single most important open risk.** The inputs are human 2,916 words vs
   enriched 7,880 (**2.70×**) and demographics-only 8,418 (**2.89×**). This is exactly
   the asymmetry D2 exists to characterise, and no synthetic side was coded.
7. **Moderator content coded as participant evidence** — **0 of 15 quotes** come from a
   moderator turn. All 15 are Participants 1–5.
8. **Introduction / presentation / closing leakage** — 0 excluded-content problems. The
   human transcript starts at "Question 1"; the synthetic windows were never sent.

## Tokens, retries, errors

| Input | Attempts | Retries | In | Out | Total | Error |
|---|---|---|---|---|---|---|
| probe | 1 | 0 | 5 | 1 | 83 | — |
| human FG1 | 1 | 0 | 5,543 | 1,674 | 14,208 | — |
| enriched FG1 r2 | 7 | 6 | — | — | — | 503 UNAVAILABLE |
| demo-only FG1 r2 | 0 | 0 | — | — | — | **no request was ever issued** |

**4 Gemini calls billed** (1 probe + 1 completed + retries that returned 503).

## D2

Not run, as instructed — D2 requires Tier-1 results from the full batch. The
`evidence_localized_length_matched_*` proxies are **not** equivalent to
`tier1_length_matched_recall` / `_precision`, which remain
`DEFERRED_NOT_IMPLEMENTED` (Amendment A1).

## What is required before a GO

1. `gemini-3.5-flash` serving ~8,000-word requests without 503.
2. The two missing preflight evaluations completed and inspected as above.
3. A first look at recall/precision under the 2.7×–2.9× length asymmetry.

Nothing in this attempt suggests a pipeline problem. Re-running the preflight when
the provider recovers requires no code change: the human FG1 result is cached under
its Tier-1 cache key and will be reused, so only the two synthetic evaluations will
be billed.


---

## Factual correction (2026-07-30)

An earlier version of this section stated that **both** synthetic windows returned
503, and reasoned from two synthetic failures. **That is wrong.**

| Input | What actually happened |
|---|---|
| enriched FG1 r2 | attempted once, 6 transient retries, all 503 |
| demographics-only FG1 r2 | **never attempted** — no request was issued |

Evidence: the run output contains exactly one `computed` line (`human_fg1`) and
exactly six `[transient]` lines — one input's retry budget. There is no output line
for either synthetic run, and no cache entry or error record exists for
demographics-only. The pipeline aborted when the enriched input exhausted its
retries.

**The size-correlation inference is withdrawn.** It rested on two synthetic failures
that did not occur. With one attempted synthetic request there is nothing to
correlate.

The historical call logs (`gemini_calls.jsonl`, `preflight_availability_probe.jsonl`)
were **not** edited. Only this report-level record was corrected.

---

## Effective configuration corrected (2026-07-30)

`max_output_tokens = 32768` and `response_mime_type = "application/json"` are
transmitted on **every** Tier-1 call, but appeared in neither
`effective_request_config` nor the cache key. Two runs made under different output
caps would have collided on one cache entry, and the audit trail would not have
shown it.

### What changed

`effective_request_config` now reads the transmitted generation-config keys **out of
`thematic_coding.py` by AST**, rather than restating them. A second hand-maintained
copy is exactly how this drifted. The complete effective configuration is:

```
{"max_output_tokens":32768,"model":"gemini-3.5-flash",
 "response_mime_type":"application/json","temperature":null,
 "temperature_transmitted":false,"thinking_config":null,
 "thinking_config_transmitted":false,
 "thinking_level_effective":"model_default_unpinned",
 "thinking_level_label_in_config":"medium"}
```

`system_instruction` is transmitted but keyed separately as
`evaluator_prompt_sha256`; that exemption is declared in
`TRANSMITTED_BUT_KEYED_SEPARATELY`, not silent. **`max_output_tokens` is unchanged
at 32768.**

### Tests (15, all passing)

* every transmitted parameter must appear in `effective_request_config` — and the
  guard is shown to fire when one is removed, not merely to pass;
* changing `max_output_tokens` 32768 → 16384 **changes the cache key**;
* every field of the effective config participates in the key (no decorative field);
* canonical serialisation is order-independent.

### Human FG1 cache migration — proof-gated

| | |
|---|---|
| Old key | `3d6fe3bac2248d84…` |
| New key | `068e228d5b7afbfa…` |
| Recomputed | **No** — re-keyed only; Tier-1 result byte-identical |
| Original | preserved in `evaluator_cache_legacy/` |
| Log | `cache_key_migration_log.json` |

All six required conditions were demonstrated, not assumed:

1. input SHA-256 `0770659d…` — recorded in the artifact;
2. evaluator prompt SHA-256 `321ffd62…` — recorded;
3. codebook SHA-256 `f343ebb1…` — recorded;
4. model `gemini-3.5-flash` — recorded;
5. **`max_output_tokens = 32768`** — `thematic_coding.py` was last modified
   **2026-07-20T14:57:57Z**, ten days *before* the call at **2026-07-30T21:35:06Z**,
   so no other value can have been transmitted;
6. all six stored effective fields equal today's values.

Had any condition failed, the entry would have been marked `legacy_unmigrated` and
recomputed rather than re-keyed on assumption.


---

## Controlled retry (2026-07-30, 23:1x UTC) — still **NO-GO**

Run after the traceability corrections, with a deliberately tighter policy.

| | Previous attempt | Controlled retry |
|---|---|---|
| Availability probe | 1 call | **none** |
| Transient retries | 6 (20/60/120/240/300/300 s, ~17 min) | **2** (30 s, 90 s) |
| Error handling | every `ServerError` treated as 503 | **HTTP status classified specifically** |
| Human input | evaluated | **cache hit — no call** |

### Result

| Input | Status | Attempts | Retries | HTTP |
|---|---|---|---|---|
| human FG1 | **cache hit**, no call | 0 | 0 | — |
| enriched FG1 r2 | **failed** | 3 | 2 | **503** on all three |
| demographics-only FG1 r2 | **not attempted** — no request issued | 0 | 0 | — |

The human result was served from the migrated cache key `068e228d…`, confirming the
migration works in practice: the preflight consumed **zero** calls for it.

Stopped after the second retry. No further retries. **Nothing was substituted** — not
the model, the API key, the thinking configuration, or the transcripts.

### Classification, verified not assumed

`503` was read from the actual HTTP status, not inferred from the exception type. The
classifier distinguishes: **401/403** (authentication or permissions — a key problem),
**404** (model unavailable to the project — not a key problem), **429** (quota or rate
limit — neither downtime nor a key problem), **500/502/503/504** (provider-side,
retryable). Only the last group is retried. Previously a 429 or a 500 would have been
reported as though it were provider downtime.

Observation permitted by the evidence: **two independent attempts, ~2 hours apart, on
the same synthetic input, both 503.** No claim is made about request size — only one
of the two synthetic inputs has ever been requested.

---

## preflight_v2 — proposed, **NOT executed, NOT authorised**

If `max_output_tokens = 32768` continues to fail, the next alternative is
`max_output_tokens = 16384`. It has **not** been run and requires explicit approval.

Conditions, all of which follow from the cache-key correction:

1. **It is a new effective configuration.** `max_output_tokens` is part of the
   effective config and therefore part of the cache key.
2. **It requires a new cache key.** Demonstrated by test: 32768 → 16384 changes the
   key. No 16384 result can land on a 32768 entry.
3. **All three inputs must be re-evaluated at 16384, including the human.** The
   current human result was produced at 32768. Mixing a 32768 human baseline with
   16384 synthetic results would put a configuration difference inside the very
   comparison the study is measuring.
4. **32768 and 16384 results must never be pooled**, for the same reason.
5. **16384 must first be shown sufficient** to hold all 11 codes, their supporting
   quotes and complete, untruncated JSON. If 16384 truncates output, the resulting
   "missing" codes would be indistinguishable from genuine absence — the failure mode
   would look exactly like a fidelity finding. This must be verified before any
   substantive result at 16384 is interpreted.

The current human result at 32768 stays valid and cached under `068e228d…`; a
preflight_v2 run would add a parallel result under a different key, not replace it.

## Standing recommendation: **NO-GO**

Unchanged. Two of three preflight evaluations still do not exist. Nothing observed
implicates the pipeline, the inputs, the coding quality or the API key — the sole
obstacle is that `gemini-3.5-flash` has returned 503 to this request on two separate
occasions.


---

# preflight_v2 (max_output_tokens = 16384) — decision: **NO_GO**

Artifact: `preflight_v2_16384.json`.

## Configuration

`gemini-3.5-flash` · `max_output_tokens=16384` · temperature **not** transmitted ·
thinking config **not** transmitted · `response_mime_type=application/json` · same
frozen inputs, prompt and codebook. **No availability probe.**

```
{"max_output_tokens":16384,"model":"gemini-3.5-flash",
 "response_mime_type":"application/json","temperature":null,
 "temperature_transmitted":false,"thinking_config":null,
 "thinking_config_transmitted":false,
 "thinking_level_effective":"model_default_unpinned",
 "thinking_level_label_in_config":"medium"}
```

The default in `thematic_coding.py` is **unchanged at 32768**; 16384 is supplied per
run via `evaluator_cfg`. `max_output_tokens` is the **only** effective field that
differs from the 32768 configuration — verified by test.

## Result

| Step | Input | Status | Attempts | HTTP |
|---|---|---|---|---|
| 1 | human FG1 | **COMPLETE** | 1 | 200 |
| 2 | enriched FG1 r2 | **failed** | 3 | **503** ×3 |
| 3 | demographics-only FG1 r2 | **not attempted** | 0 | — |

The gate held in both directions: step 2 ran only because the human was complete and
untruncated, and step 3 did not run because step 2 failed.

## Human FG1 at 16384 — no truncation

| | |
|---|---|
| finish_reason | **`FinishReason.STOP`** — not MAX_TOKENS |
| Codes in response | **11 / 11**, correct ids, correct order, no duplicates |
| Output tokens | **1,800 of 16,384** — **11% of the cap** |
| Headroom | **14,584 tokens** |
| Thoughts tokens | 7,294 |
| Prompt tokens | 5,543 |
| Quotes / verified | 16 / 16 (100%) |
| Demoted codes | 0 |
| Moderator-sourced quotes | **0** |
| Excluded-content problems | **0** |
| Present / absent | 9 present; C.2 and D absent |
| Reach denominator | 5 participants |

**16384 is not a constraint on this task.** The response used one ninth of the
reduced cap. Every quote was checked literally against its cited turn: 16/16 exact,
0 from a moderator turn.

### The two caps agree

Same input, same prompt, same codebook, different caps:

| | 32768 | 16384 |
|---|---|---|
| Present codes | 9 | 9 |
| Which | A.1 A.2 A.3 B.1 B.2 B.3 B.4 C.1 C.3 | **identical** |
| Quotes / verified | 15 / 15 | 16 / 16 |
| Demoted | 0 | 0 |

The present-code set is **identical**. The 16384 run cited one additional quote — a
third voice for B.3 — which lifted that subtheme's reach from **0.4 to 0.6** (16
quotes vs 15).

This is recorded as **evaluator variability between two independent generations**. It
is **not** a demonstrated effect of the token cap: two generations under any
configuration can differ in quote selection, and nothing here isolates the cap as the
cause. It is visible at all only because the two results are held under **separate
cache keys** rather than pooled.

## The preflight_v2 hypothesis is disconfirmed

The reason for trying 16384 was that a smaller cap might be admitted. It was not.

| Input | at 32768 | at 16384 |
|---|---|---|
| human FG1 | success | success |
| enriched FG1 r2 | **503** (2 occasions) | **503** (3 attempts) |

**Corrected statement.** Reducing `max_output_tokens` from 32768 to 16384 did not
resolve the 503 for this input under the observed serving conditions. This does not
establish that output reservation can never affect admission.

**What the response actually showed:** no candidate, token usage or partial response
was returned with the 503, so the point at which the request was rejected is not
observable from the response.

Two earlier claims are **withdrawn**:

* *"the output cap is excluded as a factor"* — overreach. One input, one alternative
  cap, one set of serving conditions.
* *"503 is returned before generation begins"* — stated as mechanism without
  evidence. The API returned nothing that would show where the request was rejected.

The human input succeeded at both caps and the enriched input failed at both. No
claim is made about request size: only one of the two synthetic inputs has ever been
requested, at either cap.

## Cache protection

| Entry | Key | State |
|---|---|---|
| human FG1 @ 32768 | `068e228d…` | **intact** — not deleted, not overwritten |
| human FG1 @ 16384 | `32ab309f…` | written separately |
| pre-migration original | `3d6fe3ba…` | intact in `evaluator_cache_legacy/` |

The 16384 run read **no** 32768 result. The two configurations are not mixed
anywhere.

## Truncation detection — built and tested before use

`tier1_completeness.assess` rejects a result as `OUTPUT_TRUNCATED_OR_INCOMPLETE` if
finish_reason indicates MAX_TOKENS, any of the 11 codes is missing, ids are
duplicated or unexpected, or the JSON fails to validate after parse retries. **A
missing code is never read as `present=false`** — under a smaller cap that would turn
a truncated response into a substantive fidelity finding.

Incomplete results are written to a quarantine file, never to the cache, so a later
run cannot reuse one as a finished evaluation.

**32 passed, 1 skipped** (`pytest_focused_2026-07-30_preflight_v2.txt`) — 17 preflight_v2 tests plus the 15 earlier cache-key tests. The skip is a numeric-enum finish_reason case, deliberately not asserted because a bare integer is not self-describing. Coverage:
no override → 32768; override → 16384 actually transmitted; the keys differ; a 16384
lookup cannot hit a 32768 entry; `max_output_tokens` is the only field that differs;
and every truncation trigger, each shown to fire.

## Decision: **NO_GO**

Two of three preflight evaluations still do not exist. Nothing implicates the
pipeline, the inputs, the coding quality, the output cap or the API key. The single
obstacle remains that `gemini-3.5-flash` returns 503 for the enriched synthetic
window — now observed on **three separate occasions across two output caps**.

Recall, precision and F1 remain uncomputable: they require a paired synthetic result.

**The batch has not been run and is not authorised.**

### What would change this

The provider serving that request. Model, key, thinking configuration, transcripts,
windows, prompt and codebook are all frozen and verified. Reducing the output cap did
not help under the conditions observed, which narrows the options but does not prove
the cap is irrelevant in general.


---

# Batch API preflight — decision: **GO_TO_BATCH**

Artifacts: `batch_capability_check.json`, `preflight_batch_manifest.json`,
`batch_job_preflight.json`, `preflight_batch_result.json`.

## Capability check — metadata only

`models.get` and `models.list` both report `batchGenerateContent` among the
supported actions for **`gemini-3.5-flash`** (version `3.5-flash-05-2026`), on the
API version and key in use. No content was generated and no model was substituted.

```
supported_actions: ["generateContent","countTokens","createCachedContent","batchGenerateContent"]
input_token_limit: 1048576   output_token_limit: 65536
```

## Provenance — batch is a distinct configuration

`execution_mode` is now part of `effective_request_config` and therefore part of the
cache key. A batch response cannot satisfy a synchronous lookup, nor the reverse.

Adding the field changed the synchronous keys too, so both existing synchronous
human results were re-keyed with `execution_mode="synchronous"`, proof-gated and
non-destructively (`cache_key_migration_execution_mode.json`). The proof: **no batch
job had ever been submitted at that point**, so no cached entry could be a batch
result. Originals are preserved in `evaluator_cache_legacy/` (3 artifacts).

**The synchronous human results were NOT reused as comparative results.** All three
comparisons below come from the batch job.

## Manifest — validated before submission

Exactly 3 requests, validated: unique custom request keys, unique expected cache
keys, paths present in the frozen inputs with matching SHA-256, and **both synthetic
inputs confirmed to be `comparable_transcript.json` windows** — a full synthetic
transcript would have been refused.

| custom_request_key | side / condition | words | transcript sha | blind sha |
|---|---|---|---|---|
| `human_fg1` | human | 3,102 | `0770659d…` | `0cf562ed…` |
| `enriched_fg1_r2` | synthetic / enriched | 8,006 | `a9558195…` | `7c82a84c…` |
| `demographics_only_fg1_r2` | synthetic / demographics-only | 8,557 | `f5d5dde7…` | `58ad9e7f…` |

Effective configuration (identical for all three):

```
{"execution_mode":"batch","max_output_tokens":16384,"model":"gemini-3.5-flash",
 "response_mime_type":"application/json","temperature":null,
 "temperature_transmitted":false,"thinking_config":null,
 "thinking_config_transmitted":false,
 "thinking_level_effective":"model_default_unpinned",
 "thinking_level_label_in_config":"medium"}
```

## Job — one submission, non-idempotency guarded

| | |
|---|---|
| Job | `batches/el0qvaxk3uqnhjiettuewoeb89cw5jgs0d5e` |
| Requests | 3 |
| State | `JOB_STATE_SUCCEEDED` |

The resource name was written to disk **immediately** on return. A second `--submit`
now refuses rather than creating a duplicate job. `--status` polls without creating.
Responses were matched by `metadata.custom_request_key`, not by position.

**Batch succeeded where synchronous returned 503 three times.** The same model, the
same inputs, the same output cap — a different serving path.

## Results — all three complete

| Input | Codes | finish_reason | in / out tokens | Quotes verified | Demoted |
|---|---|---|---|---|---|
| human FG1 | **11/11** | `STOP` | 5,543 / 1,641 | 15/15 | 0 |
| enriched FG1 r2 | **11/11** | `STOP` | 12,066 / 1,082 | 9/9 | 0 |
| demographics-only FG1 r2 | **11/11** | `STOP` | 12,875 / 1,086 | 9/9 | 0 |

All 11 codebook ids present in every response, correct order, no duplicates, no
unexpected ids, schema valid. Nothing quarantined.

### Substantive inspection

**33/33 quotes literal** in their cited turn, verified against per-entry records.
**0 moderator-sourced quotes** across all three. **0 excluded-content problems** —
no introduction, presentation or closing material reached the evaluator.

| | human | enriched | demographics-only |
|---|---|---|---|
| Present | 8 | 3 | 4 |
| Which | A.1 A.2 B.1 B.2 B.3 B.4 C.1 C.3 | A.1 B.2 B.4 | A.1 B.2 B.4 C.3 |
| Absent | A.3 C.2 D | + A.2 B.1 B.3 C.1 C.3 | + A.2 B.1 B.3 C.1 |
| Reach denominator | 5 | 5 | 5 |

**False positives:** none identified. Both synthetic sides have **precision 1.0** —
every code they asserted is also in the human transcript, and
`synthetic_only_not_observed_in_human` is **empty for both**.

**Omissions:** both synthetic runs miss A.2, B.1, B.3 and C.1; enriched additionally
misses C.3. These are plausible under-coding, not artefacts: nothing was truncated
(1,082 and 1,086 output tokens against a 16,384 cap) and every asserted code carried
verified evidence.

**Note on the human baseline.** This batch run coded the human transcript as **8**
present codes; the two synchronous runs coded **9** (they additionally returned A.3).
Same input, same prompt, same codebook — so this is evaluator variability across
independent generations, not an execution-mode effect. It is visible only because
batch and synchronous results are held under separate keys. It also means the recall
denominator here is 8, not 9.

## Metrics — FG1 preflight only

| | recall | precision | F1 *(secondary)* | salience ρ | n shared |
|---|---|---|---|---|---|
| enriched | **0.375** (3/8) | **1.000** (3/3) | 0.5455 | 0.500 | 3 |
| demographics-only | **0.500** (4/8) | **1.000** (4/4) | 0.6667 | 0.8165 | 4 |

Denominators: recall over the 8 human verified-present codes; precision over each
synthetic side's own verified-present set.

**This is one focus group and one replicate per condition.** It is not a result about
conditions. Demographics-only scoring higher here is a single observation from a
design that assigns 3 replicates × 5 groups per condition precisely because one cell
cannot support such a claim. It is reported as a preflight sanity check — the numbers
are in range and the machinery works end to end.

Worth flagging for the batch: recall is low (0.375–0.500) while precision is perfect
for both conditions. The synthetic windows are 2.6–2.8× longer than the human
transcript yet assert **fewer** codes. Whatever else is true, length is not inflating
recall here.

## Decision: **GO_TO_BATCH**

All three inputs complete, untruncated, schema-valid, with verifiable quotes.

**Count correction.** An earlier version of this section gave the remaining count as
**twenty-seven**. That was wrong. The frozen corpus is **35** inputs (5 human + 30
synthetic); the preflight completed **3** (1 human + 2 synthetic); so exactly **32**
remained — **4 human + 28 synthetic**. The wrong figure came from subtracting 3 from
the 30 synthetic runs, which ignores that the preflight also consumed a human input
and that the 5 human inputs are part of the corpus.

The count is now derived in `scripts/batch_corpus_manifest.py` from
`frozen_evaluator_inputs.json` minus the COMPLETE batch-mode cache keys on disk, and
`tests/test_batch_corpus_counts.py` asserts the derivation and scans these documents
for the stale phrase.
