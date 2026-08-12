# Length Diagnostics: By Section + By Conversational Position

**Date:** 2026-06-28
**Extends:** `docs/findings/2026-06-28_length_measurement_uniform_rule.md`
**Method:** Read-only. Uniform counting rule (`docs/length_measurement_rule.md`). No transcripts edited. Human-baseline hashes confirmed intact (28/28 match).

---

## 1. General Baseline by Section (QESB)

The three QESB transcripts have explicit section markers (7–8 sections each). The four WAH transcripts have none; they are included in the position analysis (Part 2) but cannot be analyzed by section.

### QESB response length by section

| Section | n | Median | Mean | Range |
|---|---|---|---|---|
| Your Voting Story (opening) | 25 | **132** | 149 | 1–328 |
| Your Voting Outcome Story | 22 | **162** | 160 | 1–313 |
| Song of the Election | 14 | **32** | 55 | 3–186 |
| Impressions of Results by Party | 41 | **159** | 189 | 2–563 |
| One Word to Describe the Election | 7 | **11** | 36 | 1–139 |
| Standout Moments from the Campaign | 7 | **216** | 212 | 69–356 |
| What's Next for the Parties | 15 | **117** | 163 | 24–499 |
| Advice for Parties (closing) | 18 | **31** | 107 | 1–480 |
| Turnout Impressions | 8 | **280** | 463 | 7–1513 |

**Pattern:** Highly variable across sections. Narrative-eliciting sections (Voting Story, Impressions, Standout Moments) produce long responses (medians 132–280). Prompt-specific sections (One Word, Song) produce short ones (medians 11–32). The closing section (Advice) drops to median 31.

### Does the section breakdown explain the 136-vs-40 gap?

**Partially, but the gap is structural, not section-driven.** QESB is uniformly longer than Macho Meals even in comparable section types:

| Section type | QESB median | Macho Meals median |
|---|---|---|
| Opening / warm-up | 132 | 52 |
| Main discussion | 159 | 52–75 |
| Short-answer prompt | 11 | 22 |
| Closing | 31 | 22 |

The QESB guide elicits **personal narratives** ("tell us the story of your voting day"), which produce extended responses (median 132+). The Macho Meals guide elicits **opinions and reactions** ("what's your favourite place?", "do you think your gender influences what you eat?"), which produce shorter conversational turns. WAH falls between the two (aggregate median 149), also relying on opinion/reaction questions but with a verbal moderator who probes individual participants for elaboration.

**Candidate explanation (not causal — a hypothesis):** The 136-vs-40 gap likely reflects three compounding factors: (1) the guide design (narrative-elicitation vs opinion-exchange), (2) moderation style (verbal probing moderators in QESB/WAH vs self-directed prompt-only in Macho Meals FG2/FG5), and (3) group size (3–5 participants in QESB vs 3–8 in Macho Meals — larger groups produce more frequent, briefer contributions).

---

## 2. Conversational Position (Quartile Bins)

Participant turns ordered by position within each focus group, binned into quartiles (first 25%, second, third, last 25%).

### General baseline (all 7 FGs)

| Quartile | n | Median | Mean | Range |
|---|---|---|---|---|
| Q1 (first 25%) | 79 | **124** | 127 | 1–394 |
| Q2 (second 25%) | 75 | **153** | 203 | 1–1513 |
| Q3 (third 25%) | 78 | **200** | 195 | 1–563 |
| Q4 (last 25%) | 74 | **118** | 118 | 1–480 |

**Arc: 124 → 153 → 200 → 118 (inverted-U).** Participants warm up through Q1–Q3, then wind down in the final quarter.

Subgroup patterns:
- **QESB:** 141 → 118 → 200 → 90. Peak in Q3, steep wind-down.
- **WAH:** 90 → 175 → 201 → 131. Classic warm-up into Q2–Q3, then moderate wind-down.

### Macho Meals human (matched FGs: FG1, FG2, FG4, FG5) — POOLED

| Quartile | n | Median | Mean | Range |
|---|---|---|---|---|
| Q1 (first 25%) | 63 | **56** | 63 | 1–194 |
| Q2 (second 25%) | 62 | **40** | 59 | 1–252 |
| Q3 (third 25%) | 63 | **53** | 81 | 1–333 |
| Q4 (last 25%) | 60 | **18** | 44 | 1–287 |

**Pooled arc: 56 → 40 → 53 → 18. Roughly flat across Q1–Q3 (no clear peak), with a late drop in Q4.**

**Correction (Issue 1):** This is NOT an inverted-U. Q1–Q3 bounce within a narrow band (40–56) with no systematic rise or peak. Only Q4 drops. The general baseline shows a genuine inverted-U; the Macho Meals data does not.

**However, the pooled arc masks large between-group variation — see the per-group robustness check (Section 4) below.**

### Synthetic agents (verbosity baseline, 4 runs — truncated early slices)

| Quartile | n | Median | Mean | Range |
|---|---|---|---|---|
| Q1 (first 25%) | 24 | **59** | 77 | 13–213 |
| Q2 (second 25%) | 20 | **130** | 136 | 76–194 |
| Q3 (third 25%) | 20 | **176** | 171 | 87–243 |
| Q4 (last 25%) | 20 | **176** | 182 | 117–253 |

**Arc: 59 → 130 → 176 → 176. Monotonic escalation, then flat at the top. No wind-down.**

**Caveat:** These are truncated early slices (~15–22 turns). The Q4 here is still within the opening/context sections, not the closing. A complete synthetic run might show different late-discussion behavior. The positional analysis of synthetic data is necessarily partial.

---

## The verbosity conclusion (corrected)

### Magnitude gap (confirmed per-group, but range varies widely)

The pooled "agents ~3–4x too verbose" finding holds as a central tendency but masks large between-group variation:

| FG | Size | Age | Mod style | Real median | Synth median | Ratio |
|---|---|---|---|---|---|---|
| FG1 | 5 | 18–29 | verbal + prompts | 38 | 152 | **3.9x** |
| FG2 | 5 | 30–39 | prompts only | 90 | 152 | **1.7x** |
| FG4 | 3 | 50–59 | verbal + prompts | 47 | 152 | **3.2x** |
| FG5 | 4 | 60+ | chat + prompts | 22 | 152 | **6.9x** |

The gap ranges from **1.7x** (FG2) to **6.9x** (FG5). FG2 is the outlier — the only prompt-only-moderated group and the only one where the gap is modest. The magnitude claim is robust for FG1/FG4/FG5 (3.2–6.9x) and weaker for FG2 (1.7x).

### Early-discussion escalation (confirmed within the covered range)

Within the early portion that both corpora cover, the synthetic agents start at a realistic length then escalate rapidly:

| Position | Real Macho Meals (pooled) | Synthetic | Ratio |
|---|---|---|---|
| Q1 (early) | 56 | 59 | **1.1x** (near-parity) |
| Q2 | 40 | 130 | 3.3x |
| Q3 | 53 | 176 | 3.3x |

The Q1 near-parity → Q2–Q3 divergence is a real finding: agents escalate where real participants stay flat (or dip). This holds within the discussion range both corpora cover.

### ~~Q4 / "agents never wind down"~~ — WITHDRAWN (Issue 2)

The Q4 comparison (real 18 vs synthetic 176 = 9.8x) and the "agents never wind down" claim are **withdrawn**. Quartiles are relative bins: real Q4 = the closing section of a complete discussion; synthetic Q4 = the last quarter of a truncated early fragment, still in opening/context. The 9.8x figure compares non-comparable positions and is partly an artifact of truncation.

Whether agents would wind down in a closing section **cannot be assessed** without a complete synthetic run (flagged future task). The defensible claim is limited to the early-to-middle range where both corpora overlap.

### ~~"Two distinct fidelity gaps"~~ — QUALIFIED (Issues 1 + 3)

The original claim of "magnitude plus a missing temporal dynamic" is **qualified**:

1. **Magnitude gap: confirmed per-group** (1.7x to 6.9x, with FG2 as a mild outlier).
2. **Missing temporal dynamic: not robustly established.** The per-group arcs are inconsistent (see Section 4 below), so no reliable "human pattern" exists for the agents to be missing. The defensible statement: within the early discussion, agents escalate while at least some real groups stay flat or decline — but the per-group shapes vary too much to call this a universal human dynamic.

---

## 4. Per-Group Robustness Check (Issue 3 — group-size confound)

### Per-group arcs (do the per-group shapes agree?)

| FG | Size | Q1 | Q2 | Q3 | Q4 | Shape |
|---|---|---|---|---|---|---|
| FG1 | 5 | 39 | 55 | 44 | 20 | flat + late drop |
| FG2 | 5 | 83 | 56 | 152 | 130 | irregular (Q3 spike) |
| FG4 | 3 | 70 | 30 | 142 | 36 | irregular (Q3 spike, Q4 drop) |
| FG5 | 4 | 56 | 33 | 12 | 12 | declining throughout |

**The per-group arcs do not agree.** FG1 is flat-with-late-drop; FG2 and FG4 are irregular with Q3 spikes; FG5 declines monotonically. The pooled "flat across Q1–Q3, drop in Q4" was a composition artifact — no single per-group shape dominates. **The pooled arc is not a reliable finding.**

### Per-group general-baseline arcs

| Group | Size | Q1 | Q2 | Q3 | Q4 | Shape |
|---|---|---|---|---|---|---|
| QESB Arden | 4 | 141 | 117 | 167 | 69 | peak Q3, late drop |
| QESB Greta | 3 | 79 | 120 | 356 | 104 | peak Q3 |
| QESB Jeremy | 3 | 161 | 124 | 124 | 92 | declining |
| WAH emp1 | 8 | 91 | 175 | 204 | 132 | peak Q3 |
| WAH emp2 | 7 | 100 | 159 | 256 | 102 | peak Q3 |
| WAH er1 | 5 | 45 | 135 | 195 | 131 | peak Q3 |
| WAH er3 | 8 | 124 | 289 | 171 | 137 | peak Q2 |

The general baseline shows more consistency: 5 of 7 groups peak at Q2 or Q3 then drop, supporting the inverted-U characterization. But it is not universal (Jeremy declines from Q1).

### Group size vs median length

| Group | Size | Median | Corpus |
|---|---|---|---|
| MM FG4 | 3 | 47 | Macho Meals |
| QESB Greta | 3 | 124 | General |
| QESB Jeremy | 3 | 126 | General |
| MM FG5 | 4 | 22 | Macho Meals |
| QESB Arden | 4 | 128 | General |
| MM FG1 | 5 | 38 | Macho Meals |
| MM FG2 | 5 | 90 | Macho Meals |
| WAH er1 | 5 | 128 | General |
| WAH emp2 | 7 | 150 | General |
| WAH emp1 | 8 | 144 | General |
| WAH er3 | 8 | 170 | General |

**Within** Macho Meals, no clear group-size-to-length trend (size 3 = median 47; size 5 = medians 38 and 90; size 4 = median 22). **Across** corpora, same-size groups differ dramatically (size 5: MM FG1 = 38, WAH er1 = 128). Group size does not explain the 136-vs-40 gap; the study/guide/moderation-style difference dominates. Group size remains a candidate factor but not an isolated one — it co-varies with age band, moderation style, and topic.

---

## 5. What survives, what is qualified, what is withdrawn

| Claim | Status after corrections |
|---|---|
| Magnitude gap: agents too verbose vs matched Macho Meals | **Confirmed per-group.** Range 1.7x–6.9x; robust for FG1/FG4/FG5 (3.2–6.9x); weaker for FG2 (1.7x). Pooled ~3–4x is a reasonable central tendency but hides between-group spread. |
| Early-discussion escalation (Q1 near-parity → Q2–Q3 divergence) | **Confirmed** within the covered range. |
| Q4 9.8x / "agents never wind down" | **Withdrawn.** Truncation-confounded; cannot be assessed without a complete synthetic run. |
| "All human corpora show inverted-U" | **Corrected.** General baseline: inverted-U (5/7 groups). Macho Meals: NOT inverted-U; per-group shapes disagree (flat / irregular / declining). |
| "Two distinct fidelity gaps (magnitude + temporal)" | **Qualified.** Magnitude gap confirmed per-group. Temporal-dynamic claim not robustly established — per-group arcs are too inconsistent to define a reliable human pattern. |
| Missing long tail (general comparison) | **Reversed under matched comparison** (prior finding, unchanged). |
| Set A vs Set B age effect (1.6x) | **Unaffected** — within-synthetic, same truncation both sets. |
| Annotation counting negligible | **Confirmed** (0.37% human, 0.11% MM). |
| Group size explains the 136-vs-40 gap | **Not supported.** Same-size groups differ dramatically across corpora. Study/guide/moderation-style dominates. |

---

## Provenance

Human-baseline manifest: 28/28 SHA-256 hashes match. No transcript was edited.
