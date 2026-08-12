# Clustering guide — `Clustering_U01_U07.xlsx`

**Material: PARTIAL_EMERGENT_HUMAN_REVIEW.** Two coders, seven shared units
(U01–U07), 76 pooled themes, authorship removed and order shuffled.

**This is not a gold standard** and must not be described as one anywhere. Seven of
fifteen issued units were coded. Nothing here validates the codebook.

**This work must be done by a person.** No LLM completed or may complete the
clustering: the whole point is an independent human judgement about which labels
denote the same theme. An automated pass would produce a similarity artefact and
destroy the only thing this exercise provides.

---

## 1. Assigning `cluster_id`

Work **unit by unit**, reading all pooled themes for a unit before deciding anything.

* Every row gets a `cluster_id`. Use `C01`, `C02`, … .
* **Ids are global, not per-unit.** If a theme in U05 is the same theme you saw in
  U02, it takes the **same id**. This is the single most important rule here: the
  cumulative-cluster curve and the saturation reading are computed by counting when
  each id **first** appears, so per-unit numbering would make every unit look novel.
* Fill `cluster_label` **on the same row**, using the same wording each time that id
  recurs. `cluster_id` and `cluster_label` are **global** properties of the theme.
* A theme raised by only one coder still gets its own id. Do not drop it.

Suggested order: cluster U01 fully, then U02 while re-reading your U01 labels, and so
on. Keep your own running list of ids as you go — `Cluster_Definitions` is generated
afterwards and is not a place to work.

## 2. Merging equivalent themes without erasing real differences

Merge when the two rows make the **same claim about the same object**, differing only
in wording.

Do **not** merge when:

* one is a **subset or a special case** of the other (record as separate clusters and
  note the relation in `adjudicator_notes`);
* they share a topic but make **different or opposing claims** — e.g. "gender shapes
  what I eat" and "gender does not shape what I eat" are one topic and **two**
  themes;
* they differ in **who or what is the agent** (the speaker's own choice vs a
  partner's planning vs a social expectation);
* you are merging mainly because the labels share vocabulary.

If a merge feels close but not clean, keep them separate and say why in
`adjudicator_notes`. A split that is documented can be merged later; a merge that is
undocumented cannot be recovered.

## 3. Duplicates within one coder

A coder may have entered near-identical themes in two slots of the same unit.

* Give them the **same `cluster_id`** — they are one theme.
* Do **not** delete either row. The workbook is a record of what was returned.
* Note `duplicate within coder` in `adjudicator_notes` on the second row.

This matters for the presence matrix: a cluster is present for a coder in a unit or
it is not; it is not "present twice".

## 4. Recording disagreement

Disagreement is a finding, not a defect, and it is why the two coders were
independent.

* Where only one coder raised a theme, the cluster simply has one contributing row —
  that asymmetry **is** the record. Do not add a row for the other coder.
* Where you judged two labels *not* to be the same theme and expect that to be
  contested, write your reasoning in `adjudicator_notes`.
* Where a row is ambiguous enough that a different adjudicator might cluster it
  elsewhere, say so. Later readers need to know which boundaries were close calls.

## 4b. Centrality is judged PER UNIT

`is_central` is **not** a property of the cluster. It belongs to
**cluster × unit**.

* The **same** theme may be **central in U02 and peripheral in U05**. That is a real
  finding about where a theme carries weight, and the validator permits it.
* What must be consistent is one cluster **within one unit**: if a cluster has two
  rows in U03, both must carry the same decision.
* Judge each unit on its own reading. Do not copy a unit's decision forward because
  the same theme appeared earlier.

## 5. P034 and P040 — centrality MISSING

Two pooled rows (unit **U04**) show `relevance` as
`MISSING - not supplied by coder`. One coder supplied the theme, description and
quote but left the relevance field blank.

* These rows **do** take part in thematic clustering — the substantive content is
  there.
* Leave **`is_central` blank** for them. Do not mark them central, do not mark them
  peripheral, and do not treat blank as peripheral by default.
* If that coder later supplies the values, they can be added; until then the cells
  stay empty and any count of central clusters must state that two rows are
  unresolved.

**If P034 or P040 shares a cluster with another U04 row that you have marked:** that
cluster × unit cell takes the decision you recorded on the row(s) that have one, and
the missing rows are counted separately in `n_rows_with_missing_centrality`. If every
contributing row in a cell is missing, the cell is reported as `MISSING` — it is
never filled in from the same cluster's value in another unit.

## 6. Scope — do not extend it

* **U01–U07** — in scope, coded by both coders.
* **U08** — Coder A only. **OUT OF SCOPE.** Not clustered, and excluded from any
  future agreement computation: a unit one coder saw carries no agreement
  information.
* **U09–U15** — **NOT_REVIEWED.** Not thematic absences, not zeros, not denominators.
  Do not add rows for them and do not infer anything about them.

## 7. What can be produced once clustering is complete

None of these exist yet; all follow from your decisions:

1. counts of shared vs coder-exclusive themes;
2. a cluster × (unit, coder) presence matrix, built from your ids plus the sealed
   authorship map;
3. the cumulative new-cluster curve across U01 → U07;
4. the count of new **central** clusters introduced by each unit;
5. a **preliminary** saturation reading — specifically whether U06 and U07 still
   introduce new clusters, and whether any are central;
6. an **exploratory** comparison against the sealed codebook — to be done **last**,
   on the `Codebook_Comparison` sheet, and only after emergent clustering is
   finished. Consulting the codebook while clustering would convert an inductive
   exercise into a deductive one.

**Agreement may only be computed after step 1**, and only over U01–U07. Computing it
on raw free-text labels beforehand would measure string similarity, not agreement.

## 8. Claims that remain prohibited

Regardless of what the curve shows:

* **No claim of complete saturation.** Seven units cannot establish it. At most:
  "new clusters were/were not still appearing at U06–U07".
* **No claim that the codebook is validated**, in whole or in part. The comparison in
  step 6 is exploratory and one-directional — it can suggest gaps, not confirm
  coverage.
* **No generalisation to the 15 issued units**, and none to the wider corpus. U08–U15
  were not reviewed; nothing here describes them.
* **No agreement figure quoted without n = 7 units and the fact that it follows a
  single adjudicator's clustering.**

---

## 9. Which columns are yours

On the **Clustering** sheet, columns A–G are issued content — **do not edit them**.
A validator fingerprints those seven columns and will reject the workbook if any
character changes. Your columns are the four shaded ones:

| Column | Required? | Notes |
|---|---|---|
| `cluster_id` | **yes**, every row | `C01`, `C02`, … — **global across units** |
| `cluster_label` | **yes**, every row | identical wording for every row of a cluster |
| `is_central` | **yes**, except P034 / P040 | dropdown: `central` / `peripheral`, judged **per unit** |
| `adjudicator_notes` | optional | close calls, merges you rejected, duplicates |

**`Cluster_Definitions` is generated, not filled in.** It is produced automatically
once the Clustering sheet validates, from the labels you entered there. Restating a
label on a second sheet would create two human sources for one decision. `is_central`
does not appear on it at all, because centrality belongs to cluster × unit rather
than to the cluster.

Leave `Cluster_Definitions`, `Presence_Matrix` and `Saturation` alone. Only
`Codebook_Comparison` needs you again — last, after clustering.

## 10. Completion checklist

Run through this before returning the workbook:

- [ ] every one of the **76** rows has a `cluster_id`;
- [ ] every row has a `cluster_label`, and **the same wording** wherever an id repeats;
- [ ] a theme recurring across units carries the **same id** in every unit;
- [ ] `is_central` is filled for all rows **except P034 and P040**, which stay **empty**;
- [ ] `is_central` is **one value per cluster × unit** — a cluster may be central in
      one unit and peripheral in another, but not both within the same unit;
- [ ] no rows added, deleted or reordered; no edits to columns A–G;
- [ ] only U01–U07 appear — no U08, no U09–U15;
- [ ] the codebook was **not** consulted while clustering.

Then have the validator confirm it:

```bash
py scripts/partial_emergent_clustering_pipeline.py --validate
```

It prints `READY` or lists every problem by `pooled_id`. Nothing downstream will run
until it prints READY — a half-finished workbook cannot silently produce a saturation
curve.

---

**When you have finished**, return the workbook without renaming it. The presence
matrix and the curve will be built from your `cluster_id` column and the sealed
authorship map, which is deliberately not in this file.
