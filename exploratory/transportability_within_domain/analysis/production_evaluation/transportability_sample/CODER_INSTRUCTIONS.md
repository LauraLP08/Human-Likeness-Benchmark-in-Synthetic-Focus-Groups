# Emergent coding — supplementary sample (6 units)

**Workbook:** `Transportability_Emergent_SingleCoder.xlsx`
**Estimated time: 2–3 hours** (see the note at the end).

---

## What you are doing

Six short discussion extracts. For each, write down the themes you see — working
**inductively**, describing what is actually there. **There is no codebook** and you
are not matching against one.

You are not told where any extract comes from. Speakers are `Participant 1`,
`Participant 2`, and so on. That is deliberate.

## How to complete it

1. Read the whole extract on **Units** before writing anything.
2. On **Emergent_Coding**, use the twelve rows belonging to that unit. Leave unused
   slots blank — blank rows are expected.
3. Each theme needs **all four** of:
   * `theme_label` — a short name;
   * `theme_description` — **one sentence**;
   * `supporting_quote` — copied **verbatim** from that unit;
   * `relevance` — `central` (a main idea of the extract) or `secondary`.
   A row with some fields filled and others empty will be **rejected**. Complete it
   or clear it.
4. **At least one complete theme per unit.**
5. More than twelve themes for a unit? Use **Overflow_Themes**, and put the
   `blind_unit_id` on **every** overflow row.
6. `coder_note` is optional — use it for anything you want on record.

## What the validator will reject

Quotes that are not literal · partially completed rows · a unit with no themes ·
edits to the unit text · rows added, deleted or reordered in the fixed grid ·
overflow rows with data but no `blind_unit_id` · an unrecognised `blind_unit_id`.

Run it yourself before returning:

```bash
py scripts/build_transportability_package.py --validate
```

## What this is, and is not

This is a **supplementary, single-coder sample**. It is **not a gold standard** and
no agreement statistic will be computed from it — with one coder, none exists.

It complements the separate seven-unit sample that two coders worked on. The two are
kept apart and are never pooled.

## Time estimate

Six units, 7–17 turns each, roughly 900–3,000 words. Allow **20–30 minutes per unit**
for a careful reading plus writing 4–8 themes with verbatim quotes: **2–3 hours** in
total. One unit is noticeably longer than the others; budget nearer 40 minutes for it.

Do not rush to fill twelve slots. Fewer well-evidenced themes are more useful than
twelve thin ones.

---

## Amendment 1 — relevance is NOT_ASSESSED (2026-08-02)

**The instructions above are preserved exactly as they were issued to the coder**, including
rule 3, which asked for all four fields. They are the record of what was requested and are
not rewritten retrospectively.

After the return, the researcher decided **not to adjudicate `central` vs `secondary`**,
because that distinction could not be determined reliably from this material and is not
needed for the supplementary transportability objective.

`relevance` is therefore **optional in the return gate**, recorded as
`relevance_status = NOT_ASSESSED`, and never imputed. The other three fields and the
"at least one theme per unit" rule remain fully required.
