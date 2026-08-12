# Emergent extractor calibration — U01–U07 / Q3

**Classification:** `PRIMARY_EMERGENT_AUTOMATION_CALIBRATION_Q3`
**Status:** human clustering INCORPORATED and VALIDATED. Extractor NOT RUN. No Gemini call has been made.
**Scope:** exactly U01–U07, guide question Q3. Nothing here transfers to another question or study.
**Module:** `scripts/emergent_calibration_q3.py` · `scripts/partial_emergent_clustering_pipeline.py`

---

## 1. Centrality was not assessed — `NOT_ASSESSED`

The researcher decided **not** to classify clusters as `central` or `peripheral`, because
that distinction could not be determined reliably from the available material.

This is a **methodological decision, not missing data**. It is recorded as
`NOT_ASSESSED` and is never rendered as `peripheral`, `false`, `0`, or an empty set of
central themes — each of those would convert a declined judgement into a substantive
claim.

**The human review validates:** theme identification · theme description · textual
evidence · the grouping of similar thematic contributions.
**It does not validate:** hierarchy, relative importance, or thematic salience.

Consequences, all enforced in code and tests:

- `is_central` is optional, is absent from `REQUIRED_OF_ADJUDICATOR`, and **does not
  gate**. No row can fail for its absence — verified across all 76 rows, not a sample.
- `P034` and `P040` receive **exactly the same treatment as every other row**. Their
  former exemption is gone, in both directions.
- Any centrality value that already existed is preserved verbatim and is **never used
  analytically**; a surviving value raises a review flag, not a gate failure.
- Derived artefacts report `NOT_ASSESSED`; **nothing is written into the original
  workbook.**
- **There is no `central_reference`.** Where a schema requires the field it holds the
  string `NOT_AVAILABLE — CENTRALITY_NOT_ASSESSED` — deliberately not an empty list, so
  it cannot be read as "a reference containing zero central themes".
- Automated `reach`-based salience remains a **separate automated result** and is **not**
  validated by this human clustering.

---

## 2. Clustering validation — `READY`

`validate()` returns **0 problems**.

### Amendment 01 — authorised human correction (2026-07-31)

The researcher confirmed that the use of `C13` in `U06` was an **identifier error**.
Exactly one cell was changed under explicit authorisation:

| | |
|---|---|
| Cell | `Clustering!H58` |
| `pooled_id` / `unit_id` | `P057` / `U06` |
| Field | `cluster_id` |
| Previous → new | `C13` → **`C16`** |
| Reason | accidental cluster-id reuse confirmed by researcher |
| `cluster_label` | unchanged |
| `U07::C13` | untouched |

**Proof of minimality:** 981 cells compared across all seven sheets before and after —
**exactly 1 changed**, with number format, font, fill, wrapping and lock state identical,
and no change to sheet names, dimensions, freeze panes, autofilter, protection, data
validations or column widths.

**Seal impact: none.** `cluster_id` is an *adjudicator* column; the issued row
fingerprint covers `ISSUED_COLS` only, and all 76 fingerprints still match.

| | SHA-256 |
|---|---|
| Before (baseline, preserved) | `7a6ed1dd45d46a1be1bc534fa8d86b4f64a21aebd53ca7ce10b308363ad35570` |
| After (amendment 01) | `d5dd0c452287387182b8dadaa10ebefdab765b7c4aa2aab1648db313d720f3ab` |

The pre-amendment workbook is preserved byte-identical as
`Clustering_U01_U07.PRE_AMENDMENT_01.xlsx`; the original baseline record was **not**
overwritten. Amendment record: `AMENDMENT_01_P057_cluster_id.json`.

| Check | Result |
|---|---|
| Rows returned vs sealed | 76 / 76 |
| `pooled_id` set identical to seal | yes |
| Rows with altered issued content | **none** |
| Issued columns present, in order | yes (7 issued + 4 adjudicator) |
| Rows with `cluster_id` | 76 / 76 |
| Rows with `cluster_label` | 76 / 76 |
| Rows with `is_central` | 0 / 76 → `NOT_ASSESSED` |
| Unit set | U01–U07 exactly |
| Row ↔ unit ↔ cluster consistency | verified |
| Distinct `(unit_id, cluster_id)` pairs | 44 |
| Every row in exactly one pair | yes |

Row/unit consistency is covered by the seal: `unit_id` is one of the issued columns and
sits inside each row's fingerprint, and all 76 fingerprints match.

### Cluster identity is always `(unit_id, cluster_id)`

The same `cluster_id` text may appear in different units without denoting the same
analytic cluster. `cluster_label` must therefore be single-valued **within** a
`(unit_id, cluster_id)`; divergence **across** units is not a defect and does not gate.

**Review flags: 0.** The `C13` reuse flag has been withdrawn — it was raised, confirmed
by the researcher as an identifier error, and corrected under Amendment 01. All 16
`cluster_id` texts now carry exactly one label each. The fusion and fragmentation flags
in §3 are **retained**: they have not been reviewed and must not be cleared without a
human decision.

### Three distinct quantities — do not conflate them

| Level | n | What it is |
|---|---|---|
| **Thematic categories** | **16** | distinct `cluster_id` texts; the general themes the two coders' material resolves into across U01–U07 |
| **Theme × unit instances** | **44** | distinct `(unit_id, cluster_id)` pairs; a category counted once per unit in which it appears. **This is the analytic unit and the recall denominator.** |
| **Original coding rows** | **76** | the coders' raw pooled entries, before grouping |

The reference denominator is the **44 theme × unit instances**, never the 76 raw rows
(two rows merged into one theme must count once) and never the 16 categories (a category
present in four units is four distinct opportunities for the extractor to find it).

---

## 3. Human reference — exported

`analysis/production_evaluation/emergent_calibration_q3/human_reference_q3.json`,
written atomically (temp + `os.replace`).

| View | n | Role |
|---|---|---|
| `union_reference` | **44** | **PRIMARY AND ONLY reference for coverage** |
| `coder_a_view` | 28 | subset of the union; for Coder A's own recall |
| `coder_b_view` | 32 | subset of the union; for Coder B's own recall |

The coder views are **not alternative references**. They exist so each coder's recall
against the *same* union can be computed. They are never used as denominators and never
pooled. Every record carries `human_key = "UNIT::CLUSTER"`.

### Descriptive summary

`human_reference_q3_summary.json`. **16 thematic categories**, appearing as **44 theme ×
unit instances**, grouped from **76 original coding rows**.

| Unit | Clusters | Source rows |
|---|---|---|
| U01 | 7 | 12 |
| U02 | 6 | 10 |
| U03 | 7 | 11 |
| U04 | 3 | 7 |
| U05 | 7 | 14 |
| U06 | 5 | 10 |
| U07 | 9 | 12 |

**Rows per cluster:** 1 row → 25 clusters · 2 → 9 · 3 → 7 · 4 → 3 (max 4).
**Coders per cluster:** 1 coder → 28 clusters · 2 coders → 16.
**Shared by both coders:** 16. **Single-coder:** 28 (A only 12, B only 16).

**Possible thematic fusion — 10 flags, review only.** Clusters built from ≥3 source rows,
largest: `U05::C01` (4 rows), `U05::C06` (4), `U06::C02` (4).

**Possible thematic fragmentation — 1 flag, review only.** `U07`: `C01` "the safe choice
is to settle for social expectations" vs `C13` "opt to ignore social expectations"
(similarity 0.64) — plausibly opposing positions rather than a split, which is why it is
flagged and not merged.

Fusion and fragmentation are **flagged for review, never corrected automatically.**

**Not reported, because centrality was not assessed:** central/peripheral clusters ·
recall, precision or coverage of central themes · central-vs-peripheral differences ·
thematic saturation · any generalisation beyond U01–U07 / Q3.

---

## 4. Matching system — identity corrected

Entity identity is now always the pair:

- human theme → `(unit_id, human_cluster_id)`
- machine theme → `(unit_id, machine_theme_id)`

`assert_matching_complete()` **refuses bare ids outright**. `validate_matching()` detects
and rejects, each with a test:

| # | Rejected |
|---|---|
| 1 | unknown keys |
| 2 | duplicate pairings within a unit |
| 3 | relations between themes in different units |
| 4 | orphan matching rows |
| 5 | decisions with no relation |
| 6 | relations with no decision |
| 7 | relation/decision conflicts |
| 8 | a theme marked both matched and not matched |
| 9 | one-to-many / many-to-one declared inconsistently with the rows present |

**Cross-unit independence is proved directly.** With `M01` and `C01` existing in both
`U01` and `U02`, adjudicating `U01::M01` leaves `U02::M01` undecided and the gate stays
shut; the two units can reach *opposite* decisions for the same id text without being
recorded as a contradiction. Under the old bare-id keying, `U02` would never have been
adjudicated at all.

**The real matching has not been run.**

---

## 5. Metrics to be computed later

All keep explicit numerators and denominators, are reported **per unit and aggregated**,
and treat **units — not individual themes — as the closest independent basis** (themes
within a unit are not independent).

Recall vs `union_reference` · precision vs `union_reference` (kept conceptually separate
from the validity of novel themes) · grounded-theme rate · unsupported-or-spurious rate ·
duplicate-machine-theme rate · uncertainty rate · count and proportion of
`VALID_NOVEL_THEME` · fragmentation patterns · fusion patterns.

---

## 6. Rule B+ — final, executable

Replaces the earlier rule B.

### 6.1 Necessary coverage benchmark

> **machine recall vs `union_reference` ≥ the LOWER of the two coders' own recalls vs the
> same `union_reference`.**

From the exported reference:

| | numerator | denominator | rate |
|---|---|---|---|
| Coder A | 28 | 44 | **0.6364** |
| Coder B | 32 | 44 | 0.7273 |

**Benchmark = 0.6364** (28/44, set by Coder A).

This is **necessary but not sufficient**. It is **not a "human ceiling"**: the union is
constructed *from* both coders, so neither coder's recall against it is a ceiling. The
lower individual recall functions only as an **empirical coverage benchmark in this
sample**.

### 6.2 Machine-only themes are adjudicated, not assumed wrong

Every theme found only by the machine receives a human verdict:

`VALID_NOVEL_THEME` · `UNSUPPORTED_OR_SPURIOUS` · `DUPLICATE_MACHINE_THEME` · `UNCERTAIN`

Absence from the human reference is **not** automatically a false positive: the union
comes from two coders over seven units and may contain human omissions.

### 6.3 Final states

- `PASS_WITH_SAMPLED_HUMAN_VERIFICATION`
- `BORDERLINE — FALL_BACK_TO_ASSISTIVE_REVIEW`
- `FAIL — FALL_BACK_TO_ASSISTIVE_REVIEW`
- `UNRESOLVED_AT_THIS_SAMPLE_SIZE`

A `PASS` **does not authorise unsupervised automatic use.** It permits the extractor with
**sampled human verification** only. `BORDERLINE`, `FAIL`, ambiguous or unresolved all
lead to option **C — extractor as assistive proposer with complete human review**.

### 6.4 The one open component — unsupported themes — **APPROVAL REQUIRED**

The coverage benchmark in 6.1 is fixed by the data. What is *not* yet fixed is how many
unsupported or spurious themes are too many. I am not setting that number silently.

**Alternative 1 — qualitative gate on presence, recurrence and severity.**
No numeric cut. `FAIL` if unsupported themes are *recurrent* (in most units) **or**
*severe* (a claim the transcript does not support, as opposed to an over-broad label).
Isolated, mild cases do not fail.

- *Benefit:* matches what n=7 can actually support, and distinguishes a systematically
  hallucinating extractor from an occasionally clumsy one — which a rate cannot.
- *Arbitrariness:* moderate, and located in judgement rather than in a number. "Severe"
  needs its examples fixed in advance.
- *Risk:* less auditable; two readers could reach different verdicts. Mitigated by
  recording the verdict per theme with reasons before aggregating.

**Alternative 2 — pragmatic numeric threshold, declared as an analytical decision.**
E.g. `FAIL` if unsupported-or-spurious rate > 0.20 of machine themes.

- *Benefit:* unambiguous, auditable, decided in advance, trivially reported.
- *Arbitrariness:* high and unavoidable. 0.20 has no basis in this study; it would be a
  convention presented as a standard, and must be labelled an analytical decision, **not
  a validated standard**.
- *Risk:* with ~44-ish machine themes expected, one or two themes move the rate by
  several points, so the threshold can flip on noise. It also treats a mild over-broad
  label and a fabricated claim as equivalent.

**Recommendation: Alternative 1**, with the severity examples fixed before the extractor
runs and every machine-only theme's verdict recorded individually. It is the honest fit
for this sample size: a rate computed over a few dozen non-independent themes from seven
units projects a precision the design cannot deliver, whereas presence-recurrence-severity
is exactly the evidence a reader can check. Alternative 2 remains available and would be
reported as an analytical decision if you prefer auditability over fit.

**Not frozen. No extraction runs until you choose.**

---

## 7. Release-gate test repaired

The failing test was a **true positive**. `gold_standard_package/Coder_A_Part1_Emergent.xlsx`
is the path the gate treats as the *issued* template, but the coders returned their
completed work by saving in place — 43 and 36 real themes. Planting a "partly filled" row
into slot 2 was overwriting a slot that already held a complete theme, so nothing was
partly filled and the gate correctly reported no defect.

A live file containing completed human work can never be the reference for an
immutability check: it is precisely the thing allowed to change.

**Fix:** a `DETERMINISTIC_CANONICAL_TEST_FIXTURE`, rebuilt in `tmp_path` from the
canonical sources — the untouched `U*.txt` excerpts plus the sealed 15 × 12
`(unit_id, theme_slot)` grid — and genuinely empty.

Proved by test: the fixture reproduces the issued `Units` grid **row-for-row** (all 204
turns, including paragraph breaks inside turns); the grid is exactly the 180 sealed
slots; the fixture carries **no** human coding; the partly-filled test **asserts the cell
is empty before planting**; both acceptance and rejection are exercised; and the coders'
returned workbooks are byte-identical afterwards.

**The returned workbooks were not modified or replaced.**

---

## 8. Standing prohibitions observed

No Gemini calls · no automatic emergent extraction · no real matching · no final
calibration metrics · no change to earlier statistical results · no change to
transcripts, comparable windows, caches or `output/session_logs/`.
