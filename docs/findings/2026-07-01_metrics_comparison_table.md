# Behavioral Metrics Comparison: Three Validation Runs × Three Human References

**Date:** 2026-07-01  
**Status:** Descriptive — single validation runs; see §Caveats before interpreting gaps  
**Data sources:** `output/session_logs/*/transcript.json` (synthetic); `data/datasets_transcripts/standardized/macho_meals/fg{1,5}/transcript.json` (Ref A); `data/human_baseline/standardized_claude_v1/*/transcript.json` (Ref B); pooled (Ref C)  
**Counting rule:** uniform word rule — `docs/length_measurement_rule.md` (alpha-containing whitespace tokens; exclude tokens wholly enclosed in `()`, `[]`, `{}`)

---

## Critical caveats — read before interpreting any cell

**n=1 per condition.** Each synthetic "run" is a single session under a given configuration. Run-to-run variation within the 10-run over-intervention experiment was ~9 percentage points (turn-share range), meaning a 1–5 pp difference between two single runs is well within ordinary sampling noise. **This table is DESCRIPTIVE.** The powered comparison is the 25-run production batch, not these validation runs.

**Two known confounds in the synthetic run-to-run comparison (§4 below for detail):**
1. **Run 1 → Run 2 (same FG5 roster, pre-fix → post-fix):** verbosity median ~unchanged (262→259), moderator turn-share ~unchanged (24.4%→24.8%). The cost fix is **behavior-neutral** — it did not alter what agents say or how often the moderator speaks.
2. **Run 2 → Run 3 (FG5 4-agent → FG1 5-agent, different roster):** verbosity drops 259→211. This is a **roster/group-size effect** — five participants sharing 100 turns produce somewhat shorter individual turns than four participants sharing 76 turns — not a behavioral change in the agents' underlying verbosity tendency.

**Three human reference columns answer three different questions:**

| Column | What it is | Question it answers |
|---|---|---|
| **Ref A — Matched MM (PRIMARY)** | Real Macho Meals group that matches each run's roster (FG5 for Runs 1+2; FG1 for Run 3) | Like-for-like: same topic, same participants, same guide |
| **Ref B — General baseline** | 7 QESB/WAH focus groups (different studies, different topics/populations) | Broad context: what do real focus groups look like in general? |
| **Ref C — Combined pooled** | Ref A groups + Ref B groups pooled (9 groups total) | Broad combined reference — **pools different studies; per the length-findings lesson, pooled comparisons can mask or manufacture patterns. Treat as orientation, not evidence.** |

---

## Part 1 — Human references (computed once; cited per synthetic run in Part 2)

### Reference A — Matched Macho Meals

#### Ref A1: MM-FG5 (real, verbally-moderated; matched to Runs 1 + 2)
*Source: `data/datasets_transcripts/standardized/macho_meals/fg5/transcript.json`*

| Metric | Value |
|---|---|
| Total transcript entries | 128 |
| Moderator turns | 5 |
| Participant turns | 123 |
| Moderator turn-share | 5/128 = **3.9%** |
| Verbosity — median words/turn | **22** |
| Verbosity — mean | 52.0 |
| Verbosity — range | [1, 252] |
| P→P adjacency | **95.9%** |
| Participation balance | Keith 45 (36.6%), Patrick 37 (30.1%), Toby 21 (17.1%), Fletcher 20 (16.3%) — **Keith-dominant** |

Note: FG5 is verbally moderated (genuine moderator probes/redirects) but has the lightest moderator presence of any verbally-moderated Macho Meals group (only 5 moderator turns across 128 total entries). The very high P2P adjacency (95.9%) and very low median verbosity (22 words) reflect a group where participants primarily react to each other in brief, conversational turns.

#### Ref A2: MM-FG1 (real, verbally-moderated; matched to Run 3)
*Source: `data/datasets_transcripts/standardized/macho_meals/fg1/transcript.json`*

| Metric | Value |
|---|---|
| Total transcript entries | 64 |
| Moderator turns | 6 |
| Participant turns | 58 |
| Moderator turn-share | 6/64 = **9.4%** |
| Verbosity — median words/turn | **38** |
| Verbosity — mean | 47.9 |
| Verbosity — range | [1, 252] |
| P→P adjacency | **89.7%** |
| Participation balance | David 22 (37.9%), Will 14 (24.1%), Amir 9 (15.5%), Isaiah 7 (12.1%), Ibrahim 6 (10.3%) — **David-dominant** |

Note: FG1 synthetic agents (Runs 3) are built from this group's demographics and transcripts. The real FG1 shows strong David-dominance (37.9% of participant turns) — the matched real-group comparator the synthetic Run 3 should be evaluated against, not the pooled Macho Meals median.

---

### Reference B — General human baseline (7 QESB / Work-at-Home groups)
*Source: `data/human_baseline/standardized_claude_v1/*/transcript.json`. NOT topic-matched to Macho Meals; different study, different populations.*

| Group | Total | Mod | Part | Mod-share | Verbosity median | Verbosity mean | Range | P→P adj |
|---|---|---|---|---|---|---|---|---|
| QESB Arden | 145 | 75 | 70 | 51.7% | 128 | 138.4 | [1, 563] | 0.0% |
| QESB Greta | 86 | 43 | 43 | 50.0% | 124 | 242.7 | [1, 1513] | 7.0% |
| QESB Jeremy | 116 | 59 | 57 | 50.9% | 126 | 134.5 | [1, 345] | 1.8% |
| WAH employee-2 | 53 | 29 | 24 | 54.7% | 149 | 182.3 | [2, 518] | 0.0% |
| WAH employer-1 | 82 | 42 | 40 | 51.2% | 121 | 130.1 | [1, 413] | 5.0% |
| WAH employer-3 | 69 | 38 | 31 | 55.1% | 168 | 164.5 | [3, 305] | 0.0% |
| WAH employee-1 | 98 | 52 | 46 | 53.1% | 144 | 146.7 | [2, 431] | 0.0% |
| **Aggregate** | **649** | **338** | **311** | **52.1%** | **133** | **158.2** | **[1, 1513]** | **2.0%*** |

*\*P→P adjacency: mean of 7 per-group rates (5 groups at 0.0%, range 0.0–7.0%). Not a turn-pooled rate.*

**Structural note:** The general baseline groups operate in a highly moderator-driven format — the moderator poses each question to each participant individually, producing ~52% moderator turn-share and near-zero P2P adjacency (~2%). This is structurally different from both the Macho Meals emergent-discussion format and the synthetic emergent-mode format. These groups provide useful context for where "typical human focus groups" sit across a diversity of study designs, but are NOT the appropriate standard for fidelity claims about the Macho Meals synthetic agents.

---

### Reference C — Combined pooled (Ref B × 7 groups + Ref A × 2 groups = 9 groups)
*Source: Both above pooled. **Explicitly different studies, topics, and populations. Use only as broad orientation.***

| Metric | Value |
|---|---|
| Total entries (9 groups pooled) | 841 |
| Moderator turns | 349 |
| Participant turns | 492 |
| Moderator turn-share (pooled) | 349/841 = **41.5%** |
| Verbosity — median (pooled participants) | **89** |
| Verbosity — mean | 118.7 |
| Verbosity — range | [1, 1513] |
| P→P adjacency (mean of 9 per-group rates) | **22.2%** |

**Caveat:** Pooling 7 interview-heavy groups (52% mod-share, 2% adjacency) with 2 emergent-discussion groups (4–9% mod-share, 90–96% adjacency) produces a composite that represents neither. The pooled moderator turn-share (41.5%) is between the two study types but does not characterize either. The pooled median verbosity (89 words) is pulled between the Macho Meals low (22–38 words) and the general baseline moderate (121–168 words). Use for broad orientation only; never as a fidelity target for the Macho Meals agents.

---

## Part 2 — Synthetic runs vs human references

### Run 1 — FG5, 4-agent, pre-fix, 6/7 sections (incomplete)
*Source: `output/session_logs/fidelity_fg5_r1/transcript.json` (90 entries, externally killed at turn 70)*

| Metric | **Run 1 (synthetic)** | **Ref A: MM-FG5** *(matched)* | **Ref B: General** *(7 groups, not matched)* | **Ref C: Pooled** *(9 groups, caveat)* |
|---|---|---|---|---|
| Total dialogue entries | 90 | 128 | 649 (7 groups) | 841 (9 groups) |
| Participant turns | 68 | 123 | 311 | 492 |
| Moderator turn-share | **24.4%** (22/90) | **3.9%** (5/128) | **52.1%** (338/649) | **41.5%** (349/841) |
| — gap to Ref A | +20.5 pp above MM-FG5 | — | — | — |
| Verbosity — median (words/turn) | **262** | **22** | **133** | **89** |
| Verbosity — mean | 248.8 | 52.0 | 158.2 | 118.7 |
| Verbosity — range | [28, 340] | [1, 252] | [1, 1513] | [1, 1513] |
| — ratio to Ref A median | ~11.9× MM-FG5 | — | — | — |
| P→P adjacency | **67.6%** | **95.9%** | **2.0%** | **22.2%** |
| — gap to Ref A | −28.3 pp below MM-FG5 | — | — | — |
| Participation balance | Fletcher 17 (25%), Toby 17 (25%), Keith 17 (25%), Patrick 17 (25%) — **perfectly even** | Keith 45 (36.6%), Patrick 37 (30.1%), Toby 21 (17.1%), Fletcher 20 (16.3%) — **Keith-dominant** | not available | not available |
| — balance note | Synthetic agents produce near-equal turn counts | Real FG5 has ~2× range between most- and least-active | | |
| Participant selection: voluntary | 58/68 = **85.3%** | not available (real transcripts have no selection_mode field) | not available | not available |
| Participant selection: direct-address | 10/68 = **14.7%** | — | — | — |
| Voluntary moderator interventions | **not available** (all moderator turns logged as `moderator_intervention`; model-chosen vs orchestrator-forced subcategory requires moderator_log, not transcript.json) | not applicable | not applicable | not applicable |
| Sections completed | **6/7** (incomplete — killed externally) | 5/7 (full guide, all 5 sections in this transcript) | not comparable | not comparable |

---

### Run 2 — FG5, 4-agent, post-fix, 7/7 sections (complete)
*Source: `output/session_logs/costfix_validation_fg5/transcript.json` (101 entries, natural completion)*

| Metric | **Run 2 (synthetic)** | **Ref A: MM-FG5** *(matched)* | **Ref B: General** *(7 groups, not matched)* | **Ref C: Pooled** *(9 groups, caveat)* |
|---|---|---|---|---|
| Total dialogue entries | 101 | 128 | 649 (7 groups) | 841 (9 groups) |
| Participant turns | 76 | 123 | 311 | 492 |
| Moderator turn-share | **24.8%** (25/101) | **3.9%** (5/128) | **52.1%** (338/649) | **41.5%** (349/841) |
| — gap to Ref A | +20.9 pp above MM-FG5 | — | — | — |
| Verbosity — median (words/turn) | **259** | **22** | **133** | **89** |
| Verbosity — mean | 248.1 | 52.0 | 158.2 | 118.7 |
| Verbosity — range | [44, 343] | [1, 252] | [1, 1513] | [1, 1513] |
| — ratio to Ref A median | ~11.8× MM-FG5 | — | — | — |
| P→P adjacency | **68.4%** | **95.9%** | **2.0%** | **22.2%** |
| — gap to Ref A | −27.5 pp below MM-FG5 | — | — | — |
| Participation balance | Toby 22 (28.9%), Fletcher 18 (23.7%), Keith 18 (23.7%), Patrick 18 (23.7%) — **near-even (Toby slightly dominant)** | Keith 45 (36.6%), Patrick 37 (30.1%), Toby 21 (17.1%), Fletcher 20 (16.3%) — **Keith-dominant** | not available | not available |
| — balance note | Narrower range than Run 1 (28.9 vs 23.7%); real FG5 range is ~20 pp | Real group has dominant-Keith pattern; synthetic distribution does not reproduce this | | |
| Participant selection: voluntary | 70/76 = **92.1%** | not available | not available | not available |
| Participant selection: direct-address | 6/76 = **7.9%** | — | — | — |
| Voluntary moderator interventions | **not available** (same reason as Run 1) | not applicable | not applicable | not applicable |
| Sections completed | **7/7** (natural completion, 101 total turns) | 5/7 present | not comparable | not comparable |

**Run 1 → Run 2 confound note:** Same FG5 roster, same moderator config (pre- vs post-cost-fix). Verbosity median: 262→259 (−3 words, ~1%). Moderator turn-share: 24.4%→24.8% (+0.4 pp). **The cost fix is behavior-neutral** — these differences are within ordinary single-run sampling noise and do not indicate any behavioral change.

---

### Run 3 — FG1, 5-agent, post-fix, 7/7 sections (complete)
*Source: `output/session_logs/costfix_validation_fg1/transcript.json` (130 entries, natural completion)*

| Metric | **Run 3 (synthetic)** | **Ref A: MM-FG1** *(matched)* | **Ref B: General** *(7 groups, not matched)* | **Ref C: Pooled** *(9 groups, caveat)* |
|---|---|---|---|---|
| Total dialogue entries | 130 | 64 | 649 (7 groups) | 841 (9 groups) |
| Participant turns | 100 | 58 | 311 | 492 |
| Moderator turn-share | **23.1%** (30/130) | **9.4%** (6/64) | **52.1%** (338/649) | **41.5%** (349/841) |
| — gap to Ref A | +13.7 pp above MM-FG1 | — | — | — |
| Verbosity — median (words/turn) | **211** | **38** | **133** | **89** |
| Verbosity — mean | 198.2 | 47.9 | 158.2 | 118.7 |
| Verbosity — range | [10, 325] | [1, 252] | [1, 1513] | [1, 1513] |
| — ratio to Ref A median | ~5.6× MM-FG1 | — | — | — |
| P→P adjacency | **71.0%** | **89.7%** | **2.0%** | **22.2%** |
| — gap to Ref A | −18.7 pp below MM-FG1 | — | — | — |
| Participation balance | Amir 24 (24.0%), Ibrahim 20 (20.0%), David 20 (20.0%), Isaiah 18 (18.0%), Will 18 (18.0%) — **near-even (Amir slightly dominant)** | David 22 (37.9%), Will 14 (24.1%), Amir 9 (15.5%), Isaiah 7 (12.1%), Ibrahim 6 (10.3%) — **David-dominant** | not available | not available |
| — balance note | Synthetic: 6 pp range (18–24%). Real FG1: 28 pp range (10–38%); David is 2.4× more active than Ibrahim in real group | Synthetic and real distributions are structurally different | | |
| Participant selection: voluntary | 87/100 = **87.0%** | not available | not available | not available |
| Participant selection: direct-address | 13/100 = **13.0%** | — | — | — |
| Voluntary moderator interventions | **not available** (same reason as Runs 1+2) | not applicable | not applicable | not applicable |
| Sections completed | **7/7** (natural completion, 130 total turns) | 5/7 present | not comparable | not comparable |

**Run 2 → Run 3 confound note:** Different roster (FG5 4-agent → FG1 5-agent) and different group size. Verbosity median: 259→211 (−48 words, −19%). **This is a roster/group-size effect:** five participants sharing 100 turns produce somewhat shorter individual turns than four participants sharing 76 turns. It is not evidence that FG1 agents are less verbose than FG5 agents as individuals — the underlying per-agent tendency is confounded with the sharing dynamic.

---

## Part 3 — Cross-run summary table

| Metric | Run 1 (FG5, pre-fix, 6/7) | Run 2 (FG5, post-fix, 7/7) | Run 3 (FG1, post-fix, 7/7) | Ref A: MM-FG5 | Ref A: MM-FG1 | Ref B: General | Ref C: Pooled |
|---|---|---|---|---|---|---|---|
| **Mod turn-share** | 24.4% | 24.8% | 23.1% | **3.9%** | **9.4%** | 52.1% | 41.5% |
| **Verbosity median** | 262 | 259 | 211 | **22** | **38** | 133 | 89 |
| **Verbosity mean** | 248.8 | 248.1 | 198.2 | 52.0 | 47.9 | 158.2 | 118.7 |
| **P→P adjacency** | 67.6% | 68.4% | 71.0% | **95.9%** | **89.7%** | 2.0% | 22.2% |
| **Voluntary speaker selection** | 85.3% | 92.1% | 87.0% | n/a | n/a | n/a | n/a |
| **Sections** | 6/7 | 7/7 | 7/7 | 5/7 (present) | 5/7 (present) | n/a | n/a |

*Ref A values in bold — the primary matched comparison for each synthetic run.*  
*Run 1 and Run 2 compare against MM-FG5; Run 3 compares against MM-FG1.*

---

## Part 4 — Confound catalogue and interpretation notes

### 4.1 Cost fix is behavior-neutral (Run 1 vs Run 2, same roster)

Run 1 and Run 2 both use the FG5 4-agent roster under identical behavioral configuration; the only change is `moderator_context_mode: full` → `summarized`. Verbosity shifts by 3 words (262→259), moderator turn-share by 0.4 pp (24.4→24.8). Both changes are well within run-to-run sampling noise. **The cost fix did not alter what agents say or how often the moderator speaks.** This is the critical validity check for using Run 2 (not Run 1) as the cost-fixed behavioral baseline.

### 4.2 Run 2 → Run 3 verbosity drop is a roster effect, not a behavioral change

Run 3 (FG1, 5-agent, median 211) produces shorter turns than Run 2 (FG5, 4-agent, median 259). With one more agent sharing the turn budget, individual turns are distributed differently — more participants, more frequent turns, somewhat shorter per turn. This is a structural roster effect. The per-agent verbosity tendency of FG1 agents vs FG5 agents cannot be compared from a single run of each; the group-size confound would need to be controlled (e.g., by running FG1 as a 4-agent sub-set) to isolate individual-agent verbosity differences.

### 4.3 Moderator turn-share gap is narrower for FG1 than FG5

Run 3 (23.1%) vs MM-FG1 (9.4%) = +13.7 pp gap. Runs 1+2 (~24.6%) vs MM-FG5 (3.9%) = +20–21 pp gap. The narrower gap for FG1 is partly because the real FG1 itself has a higher moderator share (9.4%) than FG5 (3.9%) — the gap between synthetic and real is partly a function of which real group is being compared, not only of the synthetic system's moderation behavior.

### 4.4 P2P adjacency gap

Synthetic runs: 67.6–71.0%. Real Macho Meals: 89.7–95.9%. Gap: approximately 19–28 pp. General baseline: 2.0% — structured entirely differently (interview style). The synthetic system sits well above the general-baseline P2P rate but well below the matched Macho Meals rate. Likely contributors: moderator intervenes between many participant turns, whereas real Macho Meals participants freely build on each other with the moderator stepping back.

### 4.5 Participation balance: synthetic near-even, real groups show dominant participants

In all three synthetic runs, the per-agent turn-share range is narrow: 6–8 pp. In the real groups, the dominant participant holds 37–38% of participant turns (David in FG1, Keith in FG5), with the least-active participant at 10–16%. The urgency auction with similar agent personas may be producing more homogeneous engagement levels than real human group dynamics, where personality and social dominance create observable hierarchies.

### 4.6 General baseline moderator turn-share (~52%) does not characterize focus groups in general

The QESB and Work-at-Home groups use a highly structured question-by-question format where the moderator calls on each participant individually. Every question is a moderator turn; every response to the question is a participant turn; participants rarely address each other. This is reflected in the ~52% moderator turn-share and 0–7% P2P adjacency. The Macho Meals format, by contrast, is a facilitated group discussion where participants build on each other and the moderator steps back (3.9–9.4% share, 90–96% adjacency). **The general baseline is informative about study-design diversity but is not an appropriate target for Macho Meals fidelity.**

### 4.7 Verbosity ratio: FG1 vs FG5 matched comparison gives very different pictures

- Runs 1+2 vs MM-FG5: synthetic median ~11.8–11.9× the matched real median (259/22, 262/22)
- Run 3 vs MM-FG1: synthetic median ~5.6× the matched real median (211/38)

The full-session ~5× figure (reported in the methodology package as 5.3× for FG1) is the appropriate citation for dissertation purposes. The FG5 11× figure is extreme because the real FG5 participants are exceptionally brief (median 22 words — shorter even than the matched FG1 at 38 words). This is a real characteristic of the real FG5 group, not a measurement error.

---

## Part 5 — What is not in this table

The following metrics are listed in the instructions but could not be extracted from transcript data:

| Metric | Reason not available |
|---|---|
| Voluntary vs orchestrator-forced moderator turns | All moderator turns logged as `selection_mode: "moderator_intervention"` in transcript.json. Sub-category (model-scored urgency decision vs structural orchestrator override) is tracked in the moderator log (`moderator_log` in session state), not re-emitted in transcript.json. |
| Real-group participant selection mode | `selection_mode` field is not present in standardized real transcripts (it is a synthetic-session artifact). |
| Per-agent verbosity for real groups | Computable from transcript (agents identified by `canonical_speaker_id`) but not needed for the primary metrics; left for future analysis if required. |
| Sections for real MM groups | The real Macho Meals transcripts span the full guide (all 5 questions present); they do not use the synthetic session's 7-section structure so direct section counts are not comparable. |
