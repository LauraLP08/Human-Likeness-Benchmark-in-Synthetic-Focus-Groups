# Uniform Length Measurement + Section-Matched Comparison

**Date:** 2026-06-28
**Rule spec:** `docs/length_measurement_rule.md`
**Method:** Read-only on all transcripts. Human-baseline provenance confirmed intact (28/28 SHA-256 hashes match).

---

## 1. Part 1: Were annotations counted as words?

**Yes.** The prior measurements (VALIDATION_REPORT.md Part 4 and verbosity baseline) both used `len(content.split())` — whitespace-split token counting. Annotation tokens like `(.)`, `{laughs}`, `[inaudible]` were counted as words.

**Magnitude: negligible.** Human baseline: 185 annotation tokens / 49,492 words = 0.37%. Macho Meals: 25 / 22,952 = 0.11%. The median changes by less than 1 word under the uniform rule.

**Prior numbers were essentially correct.** The annotation inconsistency (human baseline preserves `(.)`, Macho Meals FG2–FG5 stripped them) does not materially affect any finding.

---

## 2. The uniform counting rule

Defined in `docs/length_measurement_rule.md`. Summary:
- **Count:** whitespace-delimited tokens containing at least one alphabetic character.
- **Exclude:** tokens wholly enclosed in `()`, `[]`, or `{}` (annotation markers), standalone punctuation, standalone numbers.
- Contractions and hyphenated words count as one token each.
- Works for Spanish (alphabetic character class includes accented Latin).

---

## 3. Re-measured distributions (uniform rule)

### General human baseline (QESB + Work-at-home, 7 focus groups)

| Focus group | n | Median | Mean | Range | SD |
|---|---|---|---|---|---|
| QESB Arden | 70 | 128 | 138 | 1–563 | 111 |
| QESB Greta | 43 | 124 | 243 | 1–1513 | 302 |
| QESB Jeremy | 57 | 126 | 134 | 1–345 | 89 |
| WAH emp1 | 46 | 144 | 147 | 2–431 | 97 |
| WAH emp2 | 24 | 150 | 182 | 2–518 | 140 |
| WAH er1 | 36 | 128 | 144 | 1–413 | 112 |
| WAH er3 | 30 | 170 | 170 | 5–305 | 87 |
| **Aggregate** | **306** | **136** | **161** | **1–1513** | **152** |

P10=7, P25=69, P75=222, P90=301.

### Macho Meals human (matched reference, 5 focus groups)

| FG | n | Median | Mean | Range | SD | ≤20w | ≤50w | >100w | >200w |
|---|---|---|---|---|---|---|---|---|---|
| FG1 (18–29) | 58 | **38** | 48 | 1–252 | 49 | 41% | 60% | 12% | 2% |
| FG2 (30–39) | 28 | **90** | 102 | 19–199 | 53 | 4% | 21% | 43% | 0% |
| FG3 (40–49, excluded) | 98 | 48 | 77 | 1–465 | 86 | — | — | — | — |
| FG4 (50–59) | 39 | **47** | 86 | 1–333 | 93 | 36% | 54% | 33% | 10% |
| FG5 (60+) | 123 | **22** | 52 | 1–252 | 60 | 50% | 63% | 18% | 2% |
| **Matched (FG1+2+4+5)** | **248** | **40** | **62** | **1–333** | **66** | | | | |

### Synthetic Macho Meals agents (from verbosity baseline, no annotations in AI output)

| Set | n | Median | Mean | Range |
|---|---|---|---|---|
| Set A (ages 20–27) | 42 | **115** | 109 | 13–178 |
| Set B (ages 64–73) | 42 | **184** | 174 | 28–255 |
| Overall | 84 | **152** | 140 | 13–255 |

---

## 4. The section-position diagnostic and section-matched comparison

### 4a. Does real response length vary by section?

| Section | Phase | n | Median | Mean | Range | SD |
|---|---|---|---|---|---|---|
| Q1: Male friendship | context | 43 | 52 | 55 | 1–194 | 45 |
| Q2: Food decisions | context | 73 | 39 | 60 | 1–199 | 57 |
| Q3: Gender & food | main_topic | 86 | 52 | 69 | 1–465 | 78 |
| Q4: Plant-based shift | main_topic | 55 | **75** | 95 | 1–337 | 97 |
| Q5: More appealing | main_topic | 89 | **22** | 56 | 1–287 | 67 |

**Section medians Q1→Q5:** 52, 39, 52, 75, 22.

**Finding: no simple increasing trend.** Q4 (plant-based shift) is the longest section (median 75), but Q5 (more appealing) drops to the shortest (median 22). The pattern is irregular, not a monotonic arc. The truncation confound is **minor to non-existent** — later sections are NOT systematically longer than earlier ones.

**Long-tail distribution by position:**
- Early sections (Q1+Q2): 0 responses >200 words out of 116 (0%)
- Later sections (Q3+Q4+Q5): 15 responses >200 words out of 230 (7%)

The few long responses ARE concentrated in later sections, but they are rare (7%) and the median of later sections (38 words) is actually LOWER than early sections (48 words).

### 4b. Section-matched comparison

Comparing synthetic responses against real responses from the **same sections the synthetic runs actually reached** (Q1+Q2, plus some Q3):

| Corpus | Sections | n | Median | Mean | Range |
|---|---|---|---|---|---|
| **Real Macho Meals Q1+Q2** | context | 116 | **48** | 58 | 1–199 |
| **Real Macho Meals Q3+Q4+Q5** | main_topic | 230 | **38** | 70 | 1–465 |
| **Synthetic overall** | context+some main | 84 | **152** | 140 | 13–255 |
| **Synthetic Set A (young)** | context+some main | 42 | **115** | 109 | 13–178 |
| **Synthetic Set B (older)** | context+some main | 42 | **184** | 174 | 28–255 |

**The synthetic agents are 3–4x more verbose than the real Macho Meals participants, even section-matched.** Real early-section responses have a median of 48 words; synthetic responses from the same sections have a median of 152 words. The truncation confound does NOT explain this gap — if anything, real responses get slightly shorter in later sections.

### The "missing long tail" re-examined

The earlier verbosity baseline noted that synthetic responses (range 13–255) lacked the long tail seen in the general human baseline (range 1–1513). Under the matched comparison, this finding **reverses**:

- Real Macho Meals responses range 1–333 (matched FGs), with only 2–10% exceeding 200 words.
- Synthetic responses range 13–255, with 0% exceeding 255 words.

The "missing long tail" was an artifact of comparing synthetic agents against the wrong human reference (the general QESB/WAH baseline, which happens to produce much longer responses). Against the matched Macho Meals reference, the synthetic agents are too LONG, not too short.

### 4c. What survives and what is still untested

**Survives regardless of the confound:**
- The within-synthetic findings (Set A vs Set B age effect = 1.6x, A1 vs A2 reproducibility = 2% noise) are unaffected — both sets were sliced identically.
- The synthetic agents lack short conversational reactions entirely (minimum 13 words vs real minimum 1 word).

**Not yet tested:**
- A complete synthetic Macho Meals session (all sections, no early cap) has not been run. The section-matched comparison uses existing truncated runs. A complete-synthetic-run comparison is flagged as a future task.

**Reference types (keep distinct):**
- **General reference** (QESB/WAH): median 136 words. Different study, different moderators, different group dynamics. Useful as a cross-study calibration but NOT for matched fidelity claims.
- **Matched reference** (Macho Meals human): median 40 words. Same study, same participants, directly comparable to the synthetic Macho Meals agents.

---

## 5. What changed vs the earlier numbers

| Finding | Earlier (pre-uniform-rule) | Now (uniform rule + matched comparison) |
|---|---|---|
| **Annotation counting** | Counted as words | Excluded — effect < 1 word (negligible) |
| **Human-baseline median** | 136 words | 136 words (unchanged) |
| **Synthetic median** | 152 words | 152 words (unchanged — no annotations in AI output) |
| **General comparison** | "Synthetic length is in the same order of magnitude as human" | **Still true for the general baseline, but misleading for fidelity** |
| **Matched comparison** | Not done | **Real Macho Meals median = 40 words; synthetic median = 152 words. Synthetic agents are 3–4x too verbose.** |
| **"Missing long tail"** | "Synthetic agents lack the long responses humans produce" | **Reverses under matched comparison.** The long tail was in the wrong reference corpus. Against matched data, synthetic agents are too long, and real Macho Meals has almost no >200-word responses (2–10% of turns). |
| **Truncation confound** | Not assessed | **Minor.** Real responses do not get systematically longer in later sections. Section-matched comparison confirms the 3–4x gap is real, not a sampling artifact. |

---

## 6. Provenance confirmation

Human-baseline manifest: 28/28 SHA-256 hashes match. No transcript was edited.

---

## 7. Plain-language summary

Real Macho Meals focus group participants produce a **median of 40 words per turn** (matched FGs). Nearly half of all turns are 20 words or fewer — brief reactions, agreements, and short additions that are natural in a group discussion. The synthetic Macho Meals agents, running uncapped, produce a **median of 152 words** — about 3–4 times longer. The synthetic agents never produce the very short (1–20 word) conversational reactions that make up 40–50% of real turns.

The earlier comparison against the general human baseline (QESB/WAH, median 136 words) was misleading: those were different studies with longer, more structured responses. The matched comparison tells a different story.

This is **not a fix recommendation** — the verbosity fix is a separate task. This is a measurement establishing the magnitude of the gap.
