# `LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION` — design v5

**Status: DESIGN ONLY. No API call has been made.**

Supersedes v4. The segmentation gate now passes 30/30 synthetic runs and 174/174 units.

---

## 0. What the analysis is, and is not (unchanged)

- **Not exclusively human inductive coding** — themes are extracted and consolidated by a
  language model; a human audits a stratified sample.
- **Does not demonstrate prospective saturation** — the corpus is closed at five paired
  groups.
- **Does not assess meaning saturation** — not assessed, and not inferable from
  open-theme counts.
- **What it describes**: the observed rate at which open themes are incorporated as focus
  groups accumulate **within a closed corpus**, retrospectively.

---

## 1. What changed from v3

| # | Defect in v3 | Correction |
|---|---|---|
| 1 | `NEW_CLUSTER` allowed in E2/F2 with no rule for incorporating or counting it | **`E3_BALANCED_NEW_CLUSTER_CONSOLIDATION`** added — §2 |
| 2 | Section lengths estimated as `document_words / n_questions` | **All 174 units really segmented**, reconciled, with provenance — §3 |
| 3 | 531 calls presented as a derived total | **Phased budget**; 531 relabelled `PLANNING_ESTIMATE_V3_SUPERSEDED` — §5 |

---

## 2. `NEW_CLUSTER` resolution — Stage E3

v3 let E2 and F2 return `NEW_CLUSTER` but gave no rule for incorporating it into a
taxonomy or counting it in a curve. Three failure modes follow from that gap: a
`NEW_CLUSTER` silently becoming one distinct theme each, `UNCERTAIN` silently vanishing
from denominators, and E1 being extended in place.

### `E3_BALANCED_NEW_CLUSTER_CONSOLIDATION` — 5 calls

1. **E1 stays frozen and is never overwritten.** `consolidate_new_clusters()` recomputes
   E1's hash and raises if it has changed.
2. Gathers the raw themes E2 marked `NEW_CLUSTER`.
3. Consolidates them **among themselves**, so duplicates and fragmentations collapse.
4. Emits a versioned derived taxonomy, **`BALANCED_TAXONOMY_EXTENDED_V1`**, carrying
   E1's clusters unchanged plus the consolidated new ones, and recording
   `parent_taxonomy_sha256` = E1's hash.
5. **Never counts each `NEW_CLUSTER` as a distinct theme automatically.** The grouping is
   adjudicated. A test shows three `NEW_CLUSTER`s yielding one extended cluster or three,
   depending on the adjudication — the verdict alone does not decide.
6. **Never drops `NEW_CLUSTER` or `UNCERTAIN` from denominators without showing them.**
   `curve_denominators()` reports both exclusions explicitly.

### Curves reported separately

| Family | Clusters available | Counts |
|---|---|---|
| **Strict vs E1** | E1 only | raw themes assigned to an E1 cluster; `NEW_CLUSTER` and `UNCERTAIN` excluded **and shown** |
| **Extended vs `BALANCED_TAXONOMY_EXTENDED_V1`** | E1 + consolidated E3 | adds the `NEW_CLUSTER` themes; `UNCERTAIN` still excluded **and shown** |

Reported alongside: **n NEW_CLUSTER raw themes**, **n consolidated extended clusters**,
**n collapsed** (the difference), and **n UNCERTAIN** with their ids.

### Stage F `NEW_CLUSTER`

A pass-2 theme may be `NEW_CLUSTER`. **It must not extend the canonical taxonomy the
pass-1 curves were built on** — that would let a re-extraction silently change the
instrument. `stage_f_assignment_problems()` rejects any `NEW_CLUSTER` record that names a
canonical cluster. Pass-2 `NEW_CLUSTER`s are counted as an instability signal — the
extractor produced something the taxonomy has no home for — and reported as a rate, not
folded into any taxonomy.

---

## 3. Real segmentation (defect 2)

v3 estimated each unit's length as `document_words / n_questions`. **That was not a
measurement.** All 174 units are now segmented from the text, offline, read-only.

- **Human**: literal `Question N.` moderator headers, matching
  `gold_standard_boundary_audit.csv`.
- **Synthetic**: the **comparable window** — never the full transcript — split on
  `moderator_log.section_transition`, read-only from `output/session_logs/`.

`final/inductive_segments.json` records per unit: `unit_id`, question, condition, FG,
`canonical_replication_index`, `source_sha256`, `section_sha256`, turns,
`participant_words`, `moderator_words`, `total_words`, `length_tercile` and full boundary
provenance.

**Reconciliation: 35/35 documents.** Segment word counts sum exactly to each document's
own total.

### The even split was materially wrong

| Question | Units | Total words | **Real mean** |
|---|---:|---:|---:|
| Q1 | 35 | 30,132 | **861** |
| Q2 | 35 | 39,514 | **1,129** |
| Q3 | 35 | 64,575 | **1,845** |
| Q4 | 34 | 69,851 | **2,054** |
| Q5 | 35 | 68,208 | **1,949** |

An even split would have said **1,565 words everywhere**. Real means span **861 to
2,054 — a 2.4× range**. Every
length-dependent quantity moved:

- expected raw themes per question: v3 said a flat 189; corrected lengths give
  **142 / 159 / 204 / 211 / 210**;
- length terciles are now computed within question × condition from real counts, and
  Stage F draws 45 **named** units rather than a notional mean-length unit;
- largest prompt: **19,251 tokens**, not 17,718.

### Boundary gate — 30 of 30 synthetic runs anchored

Every non-empty moderator-log utterance is inspected. The latest explicit guide-question
ask anchors the section; reformulations open nothing, closing residue is excluded, and
position is never used as a fallback. The two formerly ambiguous runs reproduce the
researcher-reviewed boundaries exactly:

| Run | Q1 | Q2 | Q3 | Q4 | Q5 | Closing excluded |
|---|---:|---:|---:|---:|---:|---:|
| `macho_meals_fg1_demoonly_run01` | 0–8 | 9–18 | 19–33 | 34–45 | 46–51 | 52+ |
| `macho_meals_fg4_demoonly_run01` | 0–5 | 6–14 | 15–19 | 20–23 | 24–27 | 28+ |

Gate result: **30/30 runs, 174/174 units, 35/35 source documents reconciled, zero
unresolved boundaries**.

---

### Canonical corpus (unchanged from v3, re-verified)

The 30 synthetic documents come from **`analysis/production_evaluation/frozen_evaluator_inputs.json`**
and nowhere else, each with `condition`, `fg`, `canonical_replication_index`,
`physical_run`, `path` and `sha256`. Every path is verified to exist and to match its
recorded hash before extraction.

A `run0{1..3}` glob would build a **different corpus**: it would miss
`macho_meals_fg4_run04` and `macho_meals_fg5_run04` and wrongly include
`macho_meals_fg4_run02` and `macho_meals_fg5_run02` — four of thirty documents.

The 5 human documents are the standardized Macho Meals transcripts; human FG5 has no Q4.

---

## 4. Stages A–C, E1–E2, F1–F2 (unchanged from v3)

**A** — 174 extraction calls, open coding, codebook never shown (split leak gate).
**B** — 5 canonical taxonomies, canonical content-hash order.
**C** — 10 reassignment audits against the frozen canonical taxonomy; ids shared by
construction.
**D** — Claude, contested subset only, **retained as the main option**.
**E1** — sees **only** the balanced subsample; gate fires on any out-of-subsample leak;
output frozen and hash-keyed.
**E2** — all raw themes against the **frozen** E1 taxonomy; E1 never revised.
**F1** — 45 re-extractions, one per question × condition × real length tercile.
**F2** — pass-2 themes assigned **directly** against the canonical taxonomy; no
nearest-neighbour matching; similarity may order candidates, never select.

---

## 5. Phased budget (defect 3)

**`531 calls` from v3 is `PLANNING_ESTIMATE_V3_SUPERSEDED`.** It was presented as derived
when three of its inputs were assumptions: the raw-theme count, `UNSTABLE_SHARE = 0.15`,
and an unbudgeted E3.

### `PHASE_A_MANIFEST` — EXACT

**174 extraction calls.** A count of segmented units, not an estimate.

### `POST_A_REPLAN` — DEFERRED

Recomputes **B, C, E1, E2, E3, F1, F2** once the *real* raw themes exist. Every
downstream size depends on the observed theme count.

### `POST_C_STAGE_D_MANIFEST` — DEFERRED

Recomputes **D** from the **observed** number of unstable cases. The share below is a
hypothesis and is never used as if it were a measurement.

### `PLANNING_ESTIMATE` — for scale only

| Stage | Model | Calls | Input | Output |
|---|---|---:|---:|---:|
| `A_EXTRACTION` | Gemini | 174 | 457,703 | 198,435 |
| `B_CANONICAL_TAXONOMY` | Gemini | 5 | 70,757 | 33,152 |
| `C_REASSIGNMENT_AUDITS` | Gemini | 10 | 174,515 | 33,304 |
| `D_UNSTABLE_ADJUDICATION` | Claude | 278 | 834,000 | 83,400 |
| `E1_BALANCED_TAXONOMY_CONSTRUCTION` | Gemini | 5 | 27,462 | 22,019 |
| `E2_FULL_REASSIGNMENT_TO_BALANCED_TAXONOMY` | Gemini | 5 | 87,257 | 16,652 |
| `E3_BALANCED_NEW_CLUSTER_CONSOLIDATION` | Gemini | 5 | 27,680 | 8,832 |
| `F1_INSTABILITY_REEXTRACTION` | Gemini | 45 | 120,593 | 51,830 |
| `F2_PASS2_ASSIGNMENT_TO_CANONICAL_TAXONOMY` | Gemini | 5 | 39,414 | 4,349 |
| **Gemini** | | **254** | **1,005,381** | **368,573** |
| **Claude** | | **278** | **834,000** | **83,400** |
| **Total** | | **532** | **1,839,381** | **451,973** |

### Stage D instability scenarios

| Scenario | Unstable cases | Claude calls | Claude cost |
|---|---:|---:|---:|
| 5% | 46 | 92 | **$1.04** |
| 15% *(planning)* | 139 | 278 | **$3.13** |
| 30% | 278 | 556 | **$6.25** |

**Gemini: not costed.** 254 calls, 1,005,381 input and 368,573 output tokens. No
published Batch rate for `gemini-3.5-flash` has been verified in this project and none is
invented. The Claude figure is **not** the project cost.

**Context.** Largest prompt **19,251 tokens**, **90.4% headroom** against 200k. This is now
computed from real segment lengths, so unlike v3's 17,718 it rests on measurements — but
it is still a projection of prompt size from expected theme counts, and is verified only
once Stage A produces real themes.

---

## 6. Offline verification gates — no API call

| Group | Covers |
|---|---|
| Universe | 174 units; human FG5 has no Q4, verified twice; missing section never a zero |
| Q4 | 4 FGs, **24 orderings**, 28 in curve, 6 out; FG5 absent from human Q4 units and Stage F cells |
| Canonical paths | 30 from the frozen manifest; glob would swap 4 documents |
| Codebook absence | gate fires on each planted class; ordinary words in participant speech not flagged |
| Cluster alignment | id equality alone scores identical partitions as zero agreement |
| E1/E2 | out-of-subsample leak detected; revised E1 detected; `NEW_CLUSTER`/`UNCERTAIN` remain available |
| Stage F | nearest-neighbour rejected; similarity may rank the substantively wrong cluster first and the record still passes |
| **Real segmentation** | **lengths are not document/5** (2.4× range); 35/35 documents reconcile; 30/30 synthetic runs and 174/174 units anchored; full provenance per segment; window never the full transcript; zero unresolved boundaries |
| **E3** | E1 hash-identical after E3; two equivalent `NEW_CLUSTER`s collapse to one; `NEW_CLUSTER` not automatically distinct; ungrouped/double-grouped rejected; `UNCERTAIN` never folded in; strict and extended curves separate; exclusions shown |
| **Phased budget** | Phase A exact; later phases deferred; Stage D from observed cases with 5/15/30% scenarios; E3 budgeted; budget uses real segment lengths |

---

## 7. Separation from existing results

| Analysis | Instrument | Status |
|---|---|---|
| Deductive fixed-codebook coverage accumulation | 11 a-priori subthemes | exists; exploratory; **unchanged** |
| **LLM-assisted retrospective open thematic accumulation** | pooled emergent taxonomy | this design |
| Meaning saturation | — | **NOT ASSESSED** |

Deductive figures (human 11/11; enriched [6,7,4]; demographics-only [6,4,4]) are not
recomputed, superseded or merged.

---

## 8. Recommendation: **GO for Phase A only**

All three v3 defects are corrected in code with tests that fail when the rule is broken.
Real segmentation changed material numbers, which is the clearest evidence the defect was
worth fixing.

**Approve Phase A (174 extraction calls) alone.** B through F should be re-planned from
the observed raw themes rather than approved now on estimates — that is what the phased
budget is for, and it is the honest reading of how much is actually known before Stage A
runs.

The segmentation gate is now complete. No boundary decision remains outstanding before
Phase A or before the curves.

**Still uncosted:** the Gemini share, 254 calls and ~1.4M tokens. If a hard budget
matters, verify the rate before Phase A or set a token cap.

### Approvals needed

1. **Phase A: 174 extraction calls** (Gemini, Batch, codebook-blind).
2. Reading `output/session_logs/*/moderator_log.json`, read-only, for synthetic
   boundaries.
3. Stage E3 design — `BALANCED_TAXONOMY_EXTENDED_V1`, strict and extended curves reported
   separately.
4. Deferring B–F to `POST_A_REPLAN` and Stage D to `POST_C_STAGE_D_MANIFEST`.
5. Gemini uncosted, or a token cap.

Nothing runs until these are settled.
