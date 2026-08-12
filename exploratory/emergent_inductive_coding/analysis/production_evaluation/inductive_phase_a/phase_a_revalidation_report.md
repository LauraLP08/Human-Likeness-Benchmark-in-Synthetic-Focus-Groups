# Phase A revalidation — theme-level policy and count discrepancy

**Status: STOPPED before any API call.** The expected theme-level counts are not reproduced, and the instruction requires stopping and reporting when they are not.

`phase_a_raw_responses.json` was read only. It is byte-identical, SHA-256 `cc34ad0113e22a22…`.

---

## 1. What reproduces exactly

| Quantity | Expected | Recomputed | |
|---|---:|---:|---|
| Themes returned | 526 | **526** | match |
| Quotes returned | 1,398 | **1,398** | match |

Both structural totals agree exactly, so both validators are reading the same 174 responses and parsing the same theme and quote objects. The divergence is confined to the literality verdict.

## 2. What does not reproduce

| Quantity | Expected | Recomputed |
|---|---:|---:|
| Themes with all quotes valid | 276 | **513** |
| Themes with valid and invalid quotes | 214 | **12** |
| Themes with no valid quote | 36 | **1** |
| Units where every theme keeps evidence | 146 | **173** |
| Units requiring repair | 28 | **1** |
| Invalid quotes | 342 | **14** |

## 3. Diagnostic — the divergence is a rendering question, not a policy question

Invalid-quote counts under progressively stricter comparison, all against the unit rendering the extractor actually received:

| Comparison | Invalid quotes |
|---|---:|
| Raw, exact, no normalisation | 31 |
| NFKC only | 31 |
| + whitespace collapse | 31 |
| + quotation marks, dashes, ellipsis | 31 |
| + case (the frozen policy) | **14** |

**No normalisation setting produces 342.** Even a byte-exact comparison yields 31. Tightening normalisation cannot explain a 24-fold difference.

Comparing instead against the **source transcript file** rather than the rendered unit gives **130** invalid quotes under exact comparison and 31 under whitespace collapse. The figure 130 coincides with the reported count of rejected units, which suggests the other validator compares quotes against source text that still carries its original line breaks and spacing, while the extractor was shown a whitespace-collapsed rendering. A quote copied faithfully from what the model saw would then fail against text it never saw.

Other failure modes were checked and are empty: **0** quotes name a turn outside their unit, **0** are attributed to the moderator, **0** carry a mismatched speaker.

**This is a statement about two validators, not about the data.** Which rendering is authoritative is a decision, and it is yours: the extractor saw the collapsed rendering, so validating against it is self-consistent, but validating against the unmodified source is the stricter reading.

## 4. The frozen policy, applied

A quote is valid only if it is a contiguous substring, located entirely in the turn_id it names, attributed to the speaker who holds that turn, spoken by a participant, and free of paraphrase or inserted words. Normalisation is limited to NFKC, quotation marks, dashes, ellipsis, whitespace and case, and **never bridges an elision** — a contiguous test after normalisation still fails on any omitted word.

At theme level: invalid quotes are moved to the audit and never deleted; a theme survives on at least one valid quote; a theme with none is `EVIDENCE_REPAIR_REQUIRED`; **an extra invalid quote never removes a theme that keeps another valid one**.

Under this policy: **1,384 valid quotes**, **14 rejected** (all `NOT_CONTIGUOUS_IN_NAMED_TURN`, i.e. internal elision), **525 themes retained**, **1 theme requiring repair**, **1 unit** not complete.

The previous unit-level result of 162/12 is superseded: it rejected a whole unit for one bad quote. Under the theme-level policy the same 14 bad quotes cost 1 theme instead of 12 units.

## 5. Artefacts

| File | Contents |
|---|---|
| `phase_a_theme_level_validation.json` | every unit, theme and surviving quote |
| `rejected_quotes_audit.json` | all rejected quotes, retained with their verdict |
| `evidence_repair_manifest.json` | repair requests, **derived and NOT submitted** |
| `phase_a_revalidation_report.md` | this document |

Unchanged: original manifest, job record, raw responses, original quarantine. `phase_a_accepted.json` is marked `PROVISIONAL_SUPERSEDED` with its counts retained; it was not deleted or destructively edited. The job record keeps `state_at_creation: JOB_STATE_PENDING` and adds `final_observed_state: JOB_STATE_SUCCEEDED` separately.

The repair manifest carries **1 request** over **1 unit**, derived from the revalidation rather than from the expected figure of 36 themes over 28 units. It is **not submitted**.

## 6. Why this stops here

Building a 28-unit repair batch when the revalidation identifies one would be fabricating work to match a number. Submitting a 1-theme batch when 36 are expected would silently adopt my rendering as authoritative. Either way the count question must be settled first.
