# Macho Meals Transcript Standardization Report

**Date:** 2026-06-28
**Dataset:** DS03_MACHO_MEALS_UK (5 focus groups, 22 participants, 22 agents matched)
**Output:** `data/datasets_transcripts/standardized/macho_meals/{fg1..fg5}/`
**Raw files modified:** No. All 5 SHA-256 hashes match stored metadata.

---

## 1. Inventory

| FG | Age range | Raw file | Participants | Agents | Turns |
|---|---|---|---|---|---|
| FG1 | 18–29 | `18-29 FG Transcript - CLEAN, ANON_MachoMeals.docx` | David, Isaiah, Amir, Ibrahim, Will | 5 matched | 64 |
| FG2 | 30–39 | `30-39 FG Transcript - CLEAN, ANON_MachoMeals.docx` | Bilal, Connor, Henry, Noah, Sam | 5 matched | 33 |
| FG3 | 40–49 | `40-49 FG Transcript - CLEAN, ANON_MachoMeals.docx` | Andrew, Daniel, John, Nick, Paul | 5 matched | 104 |
| FG4 | 50–59 | `50-59 FG Transcript - CLEAN, ANON_MachoMeals.docx` | Gregor, James, Mark | 3 matched | 44 |
| FG5 | 60+ | `60+ FG Transcript - CLEAN, ANON_MachoMeals.docx` | Fletcher, Keith, Patrick, Toby | 4 matched | 128 |

**Total:** 373 turns across 5 FGs. 22 participants matched to 22 agents; 0 unmatched.

> **FG3 carries a provenance limitation — see §7.1.** Its agent payloads hold genuine FG3
> survey data, but the person-to-row correspondence is a random 1:1 assignment, so FG3
> supports group-level comparison only.

---

## 2. Provenance: Researcher Edits

The raw transcripts at `data/datasets_transcripts/MachoMeals_raw transcripts/` are **edited** versions. The filenames contain "CLEAN, ANON" indicating anonymization and cleanup. The researcher applied the following edits before standardization:

- **Timestamps removed** (e.g., `[00:09:00]` removed from all FGs)
- **"Host" → "Moderator"** relabeling applied in FG1, FG3, FG5
- **Disfluency markers removed** from FG2–FG5 (`(.)`, `(h)` removed). **FG1 retains disfluency markers** — this is an inconsistency across FGs.
- **FG4 reformatted** from name-on-separate-line to `Name:` format

**Original unedited files do not exist** in the repository. The edited versions are the only available raw source. The faithfulness check is therefore "standardized output vs edited-raw DOCX," not vs the original unedited transcript.

**Annotation difference from human baseline:** The human-baseline transcripts (`data/human_baseline/`) preserve disfluency markers `(.)` throughout. The Macho Meals dataset transcripts have them removed (except FG1). This means response-length statistics between the two are not directly comparable at the word level for disfluency-heavy passages. This difference is documented, not corrected.

---

## 3. Faithfulness Validation

### Hop 1: Raw DOCX → stored `raw_extracted_transcript.txt`

| FG | Result | Evidence |
|---|---|---|
| FG1 | **PASS** | Byte-identical extraction |
| FG2 | **PASS** | Byte-identical extraction |
| FG3 | **PASS** | Byte-identical extraction |
| FG4 | **PASS** | Byte-identical extraction |
| FG5 | **PASS** | Byte-identical extraction |

### Hop 2: Extracted text → `transcript.json`

| FG | Turns | Fabricated words | Missing words | Explanation |
|---|---|---|---|---|
| FG1 | 64 | 0 | 4 (amir, isaiah, ibrahim, moderator) | Speaker labels stripped from content — expected |
| FG2 | 33 | 0 | 2 (connor, henry) | Speaker labels stripped — expected |
| FG3 | 104 | 0 | 2 (moderator, daniel) | Speaker labels stripped — expected |
| FG4 | 44 | 0 | 1 (gregor) | Speaker label stripped — expected |
| FG5 | 128 | 0 | 1 (moderator) | Speaker label stripped — expected |

All "missing" words are speaker names that were correctly extracted into `speaker_name`/`speaker_id` fields rather than kept in `content`. Zero fabricated content across all 5 FGs.

### Hop 3: `transcript.json` → `clean_transcript.txt` / `transcript.txt`

| FG | clean == transcript.txt |
|---|---|
| All 5 | **IDENTICAL** (SHA-256 match) |

---

## 4. Segmentation Verification

| FG | Consecutive same-speaker | Merges (embedded labels) | Verdict |
|---|---|---|---|
| FG1 | 0 | 0 | **CLEAN** |
| FG2 | 0 | 0 | **CLEAN** |
| FG3 | 0 | 0 | **CLEAN** |
| FG4 | 0 | 0 | **CLEAN** |
| FG5 | 1 (Patrick turns 65–66) | 0 | **CLEAN** (legitimate continuation) |

The FG5 Patrick consecutive turns are a short acknowledgment ("Yes. Oh, definitely.") followed by a longer elaboration ("Yeah, yeah, yeah. But certainly, as I said...") — a legitimate two-part contribution, not a false split.

---

## 5. Moderator Verification

### Moderator types across FGs

| FG | Moderator label in edited raw | Type | Standardized as |
|---|---|---|---|
| FG1 | `Moderator:` (verbal) + `Question N.` (prompts) | Verbal + prompts | MODERATOR |
| FG2 | `Question N.` (prompts only) | Prompts only (no verbal moderator) | MODERATOR |
| FG3 | `Moderator:` (verbal) + `Question N.` (prompts) | Verbal + prompts | MODERATOR |
| FG4 | `Question N.` (prompts only) | Prompts only | MODERATOR |
| FG5 | `Moderator:` (chat-based) + `Question N.` (prompts) | Chat + prompts | MODERATOR |

All moderator turns — verbal, chat, and question-prompt — are tagged as `MODERATOR` with `speaker_role: "moderator"`. No sub-typing.

### Evidence that `Moderator:` labels are correct

FG1: `"Moderator: How has how has meat specifically played a role in the times that you spend with your male friends?"` — poses guide questions, doesn't share personal experience.

FG3: `"Moderator: Mark, I think you're muted."` — manages the session, directs participants.

FG5: `"Moderator: Question 5. What might make plant-based foods more appealing to you or other men you know?"` — reads guide questions.

---

## 6. Identity Reconciliation

### FG1 (18–29) — 5/5 matched

| Transcript speaker | Agent ID | Matched |
|---|---|---|
| Amir | `mm_fg1_amir` | Yes |
| David | `mm_fg1_david` | Yes |
| Ibrahim | `mm_fg1_ibrahim` | Yes |
| Isaiah | `mm_fg1_isaiah` | Yes |
| Will | `mm_fg1_will` | Yes |

### FG2 (30–39) — 5/5 matched

| Transcript speaker | Agent ID | Matched |
|---|---|---|
| Bilal | `mm_fg2_bilal` | Yes |
| Connor | `mm_fg2_connor` | Yes |
| Henry | `mm_fg2_henry` | Yes |
| Noah | `mm_fg2_noah` | Yes |
| Sam | `mm_fg2_sam` | Yes |

### FG3 (40–49) — 5/5 matched

| Transcript speaker | Agent ID | Matched |
|---|---|---|
| Andrew | `mm_fg3_andrew` | Yes |
| Daniel | `mm_fg3_daniel` | Yes |
| John | `mm_fg3_john` | Yes |
| Nick | `mm_fg3_nick` | Yes |
| Paul | `mm_fg3_paul` | Yes |

The FG3 pairing is a **random 1:1 assignment** of the five genuine FG3 survey rows to the
five named FG3 transcript speakers, recorded in
`data/manifests/focus_group_dataset_manifest_v5.xlsx`, sheet `DS03_MACHO_MEALS_UK`. See
§7.1 for what that allows and forbids.

### FG4 (50–59) — 3/3 matched

| Transcript speaker | Agent ID | Matched |
|---|---|---|
| Gregor | `mm_fg4_gregor` | Yes |
| James | `mm_fg4_james` | Yes |
| Mark | `mm_fg4_mark` | Yes |

### FG5 (60+) — 4/4 matched

| Transcript speaker | Agent ID | Matched |
|---|---|---|
| Fletcher | `mm_fg5_fletcher` | Yes |
| Keith | `mm_fg5_keith` | Yes |
| Patrick | `mm_fg5_patrick` | Yes |
| Toby | `mm_fg5_toby` | Yes |

**Summary:** 22/22 agents have matched transcript speakers, and no agent lacks a transcript counterpart.

---

## 7. Provenance Confirmation

The standardization script is deterministic (no randomness, no external state). Re-running the script on the same raw DOCX files produces byte-identical `transcript.json` and `clean_transcript.txt` for all 5 FGs.

Raw file integrity confirmed: all 5 SHA-256 hashes match the values stored in `baseline_metadata.json`.

---

### 7.1 FG3 provenance limitation

The five FG3 agent payloads pair **genuine, unaltered FG3 survey data** — every
demographic value, consumption frequency and psychometric score — with the five named FG3
transcript speakers through a **random 1:1 assignment**. The pairing is recorded in
`data/manifests/focus_group_dataset_manifest_v5.xlsx`, sheet `DS03_MACHO_MEALS_UK`, whose
FG3 `Pseudonym` column carries the speaker names. Only the person-to-row correspondence is
arbitrary; the data itself is real.

What follows from that:

- **FG3 individual-level persona-to-transcript correspondence is not genuine.** Any
  analysis that treats an individual FG3 agent's psychometric profile as predictive of, or
  comparable to, that same named speaker's statements in the human FG3 transcript is
  invalid at the individual level. Per-participant fidelity scoring, individual
  persona-adherence checks and speaker-level survey↔transcript correlations must exclude
  FG3 or report this caveat. The dissertation's analyses are group-level, so this does not
  affect the reported results.
- **FG3 group-level data is genuine.** All five rows are real FG3 data, so the group's
  composition, score distribution, means and spread are exactly what a correct matching
  would have produced. Group-level synthetic↔human FG3 comparison is valid.
- **FG1, FG2, FG4 and FG5 are unaffected** — those 17 pairings are genuine.

Each `mm_fg3_*.json` carries this machine-readably at
`study_context.identity_metadata_linkage` (`"researcher_random_assignment"`) and
`study_context.identity_metadata_linkage_note`. Both sit under `study_context`, which the
participant prompt renderer never reads, so the caveat is never shown to the simulated
participant.

---

## 8. Output Files per FG

Each `data/datasets_transcripts/standardized/macho_meals/{fg}/` contains:

- `transcript.json` — authoritative structured turn array
- `transcript.txt` — clean dialogue-only plain text
- `clean_transcript.txt` — byte-identical to `transcript.txt`
- `raw_extracted_transcript.txt` — verbatim DOCX extraction
- `front_matter.txt` — header lines (e.g., "18-29 (5 participants)")
- `back_matter.txt` — empty (no back matter in these transcripts)
- `participant_metadata.json` — speaker roster with agent IDs and turn counts
- `baseline_metadata.json` — pipeline metadata including researcher-edit note
- `identity_reconciliation.json` — per-speaker mapping to agent IDs

---
