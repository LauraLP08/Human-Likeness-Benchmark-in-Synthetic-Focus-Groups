# Transportability comparison — protocol and schemas, NOT EXECUTED

**Nothing in this document has been run.** No extractor, no matching, no Gemini call.
It fixes the shape of the comparison *before* any result exists, so the design cannot
be adjusted to the answer later.

---

## 1. Relationship to the primary calibration sample

| | Primary | Supplementary |
|---|---|---|
| Units | **U01–U07** | **S01–S06** |
| Guide question | **Q3** only | **Q1, Q2, Q4, Q5** |
| Coders | **two**, independent | **one** |
| Human clustering | adjudicated | none |
| Classification | PRIMARY EMERGENT CALIBRATION SAMPLE | `SUPPLEMENTARY_SINGLE_CODER_TRANSPORTABILITY_SAMPLE` |
| Agreement statistics | possible after adjudication | **impossible — one coder** |

**They are never pooled.** Not the units, not the themes, not recall or precision.
Blind ids cannot collide (`U…` vs `S…`), which is deliberate.

The supplementary sample does **not** validate the extractor across all questions. It
covers four questions with one unit or two each, coded once. Any finding from it is
**exploratory evidence of transportability**, reported **per question**, and never as
a general claim about the extractor.

---

## 2. Human consolidation comes BEFORE anything automatic

**The coder's raw rows are not the human reference.** One theme may be entered twice
in different words; two rows may look alike while making different claims. Using raw
rows as the recall denominator would let a coder's duplication move every downstream
number without the extractor changing at all.

So, after the workbook returns and `--validate` reports READY, **a person
consolidates** — in `Transportability_Consolidation.xlsx`:

* work one unit at a time, reading all of its raw rows first;
* **merge** rows that make the same claim about the same thing in different words;
* **keep separate** rows that differ in the claim, the agent, or the position taken,
  however similar the wording;
* every consolidated theme records the `source_row_ids` it came from;
* **no raw row is deleted or edited** — the mapping records how they group, not what
  they should have said;
* **relevance/centrality is NOT_ASSESSED and is not set at all** (see Amendment 1).

### How the raw rows get there

Nothing is transcribed by hand. Once the coder workbook passes `--validate`:

```bash
py scripts/build_transportability_consolidation.py --import-raw <returned.xlsx>
```

imports every complete theme into `Raw_To_Consolidated`, assigns each a **stable,
unit-prefixed `source_row_id`** (`S01_slot_03`, `S01_ovf_01`), locks the six imported
columns, and writes `transportability_raw_rows_seal.json` with the exact id set and a
content hash per row. Only `consolidated_theme_id` and `consolidator_note` stay
editable.

**The sealed mapping is the authority.** `source_row_ids` typed on
`Consolidated_Themes` is a human restatement and may be wrong; where the two disagree
the workbook is **rejected**, not reconciled in favour of either. Silently trusting
one would let a mistyped id drop a theme from the denominator.

`consolidated_theme_id` must be **unit-prefixed** — `S01_T1`, `S02_T1` — so "unique
within a unit" and "never crosses units" are both true by construction.

### What `--freeze` requires

Exactly S01–S06 · the raw-row set identical to the seal, none missing, added or
duplicated · every raw row assigned to exactly one theme · every theme id unique in
its unit and unit-prefixed · every declared `source_row_id` real and in the same unit
· declared ids and mapping agreeing **in both directions** · no raw row claimed by two
themes · no theme without raw rows · unknown
units **rejected, never ignored** · no partially completed row · at least one theme
per unit.

### Integrity checks at freeze time

**Content hashes are re-verified, not trusted to Excel.** Sheet protection can be
switched off and an xlsx can be edited by anything; the hash is what holds. Each
mapping row's `_row_content_sha` is recomputed over exactly `RAW_COLS` and compared
to the seal. Any edit to `blind_unit_id`, `raw_theme_label`, `raw_theme_description`,
`raw_supporting_quote` or `raw_relevance` is rejected, naming the `source_row_id` and
both hashes. Edits to `consolidator_note` are unaffected — the hash covers only the
imported columns.

**Orphan assignments are rejected in both directions.** A mapping row pointing at a
`consolidated_theme_id` with no row in `Consolidated_Themes` would otherwise be
invisible: its key never entered the comparison, so the raw row silently left the
denominator. The check now requires:

```
set(sealed source_row_ids)
  == set(declared source_row_ids across consolidated themes)
  == set(assigned source_row_ids in the mapping)
```

verified **before** anything is written, together with exact correspondence between
the mapping's `unit::theme` keys and the theme rows.

### Writing is atomic, and a frozen reference is not silently replaced

The reference is written to a `.json.tmp` beside the target and renamed with
`os.replace` only after every check passes, so a crash cannot leave a half-written
file that later reads as authoritative. On failure nothing is written and any temp
file is removed.

**An existing `human_reference_themes.json` is refused** unless `force=True` is passed
deliberately. A frozen reference fixes the recall denominator; replacing it quietly
would let the denominator move after results existed.

`human_reference_themes` is then **frozen per unit** — before the extractor runs.

Classification of the resulting reference:

> **`SINGLE_CODER_HUMAN_REFERENCE_WITH_POST_CODING_CONSOLIDATION`**

This is **not inter-coder agreement** and is **not calibration-grade**. One coder
produced the themes; one person consolidated them. Relabelling cannot make it either.

## 3. What runs after consolidation is frozen

1. The **emergent extractor** processes **exactly these six units**, from the same
   blinded unit text the coder saw, **without a codebook**.
2. Machine themes are matched to **consolidated human themes**, per unit.
3. Metrics are computed **per question**, then reported.

Nothing is computed for a unit whose human coding is missing, rejected, or not yet
consolidated.

---

## 4. Matching — reviewable, not string similarity alone

A match must be inspectable and reversible. The record for each candidate pair:

```
{
  "blind_unit_id":        "S0N",
  "consolidated_theme_id": "T1",           # NOT a raw coder row
  "source_row_ids":        ["S0N_slot_3", "S0N_slot_9"],
  "machine_theme_index":  0..M,
  "human_label":          "...",
  "machine_label":        "...",
  "human_quote":          "...",
  "machine_quote":        "...",
  "quote_overlap":        0.0-1.0,      # evidence overlap, not label similarity
  "label_similarity":     0.0-1.0,      # reported, never decisive on its own
  "proposed_match":       true | false,
  "match_basis":          "shared_evidence" | "label_and_evidence" | "label_only",
  "human_adjudicated":    null,          # a person confirms or overturns
  "adjudicator_note":     null
}
```

Rules fixed now:

* `label_only` matches are **never** auto-accepted — they are proposed for human
  review and nothing else.
* Quote overlap is computed on the **unit text spans**, so two themes citing the same
  turns are visible as related even when worded differently.
* Every proposed match, and every non-match, is written out. A pair that was
  considered and rejected is part of the record.
* A human can overturn any proposal, and the overturn is stored beside it.

---

## 5. Metrics — per question, exploratory

**Every human-side denominator is CONSOLIDATED themes. Raw coder rows are never a
denominator.**

| Metric | Denominator |
|---|---|
| `recall` | **consolidated** human themes for that unit |
| `precision` | machine themes for that unit |
| `quote_validity` | machine themes whose quote is literal in the unit |
| `omissions` | **consolidated** human themes with no machine match — **listed, not just counted** |
| `machine_only_themes` | machine themes with no match — **not called errors** |
| `over_merging` | one machine theme matched to ≥2 **consolidated** human themes |
| `fragmentation` | one **consolidated** human theme matched to ≥2 machine themes |

Reported **per question** and per unit. Never averaged with the U01–U07 results, and
never presented as a single "transportability score".

`machine_only_themes` are recorded as **not observed in the human coding** — one
coder, one pass. That phrasing is not optional.

---

## 6. Output separation

```
analysis/production_evaluation/transportability_sample/
  transportability_matching.json        proposed + adjudicated matches
  transportability_metrics_by_question.csv
  transportability_omissions.csv
  transportability_machine_only.csv
```

None of these may be written into `results/`, which holds the primary evaluation.

---

## 7. Gates before any of it runs

1. Human coding returned and `--validate` READY.
2. **Human consolidation complete and `human_reference_themes` frozen** —
   `build_transportability_consolidation.py --freeze` refuses until every unit has at
   least one consolidated theme and every raw row is assigned.
3. Extractor run on the **same six unit texts**, verified by
   `unit_text_sha256` from the package seal.
4. No codebook supplied to the extractor.
5. Matching proposals generated **before** any metric is computed, so the metric
   cannot influence the match.
6. Human adjudication of all `label_only` proposals.
7. Only then, metrics.

Steps 3 onward require explicit authorisation. Step 3 is the only one that costs
evaluator calls; the count will be stated before it is requested.

---

## Amendment 1 — relevance is NOT_ASSESSED (2026-08-02)

The researcher reviewed all six units and decided **not to adjudicate `central` vs
`secondary`**: the distinction could not be determined reliably from this material, and it
is not needed for the supplementary transportability objective.

This is a **methodological decision, not missing data**. It is recorded as
`relevance_status = NOT_ASSESSED`.

Consequences, all enforced in code and tests:

* `relevance` is **optional** and **does not gate**. A row carrying `theme_label`,
  `theme_description` and a literal `supporting_quote` is substantively complete.
* Still **required**: `theme_label`, `theme_description`, a **literal**
  `supporting_quote`, and **at least one theme per unit**.
* Empty relevance is rendered as `NOT_ASSESSED` in derived artefacts. It is **never**
  written back into the coder workbook and never rendered as `secondary`, `false`, `0`,
  or as an absent theme.
* Any relevance value that survived would be preserved verbatim, reported as a
  non-blocking review flag, and **never used analytically**. (In fact none exists: 0 of
  72 cells.)
* **No result about centrality, relevance, salience, `central`/`secondary` or thematic
  hierarchy may be reported from this sample.**

### Two failure modes that must not be confused

| | Meaning | Gate |
|---|---|---|
| `relevance` empty | judgement declined by decision — `NOT_ASSESSED` | **passes** |
| `theme_label`, `theme_description` or `supporting_quote` empty | the theme is genuinely incomplete | **rejected** |
