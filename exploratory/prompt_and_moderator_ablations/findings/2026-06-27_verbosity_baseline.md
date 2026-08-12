# Verbosity Baseline Measurement

**Date:** 2026-06-27
**Purpose:** Measure natural (uncapped) response-length distribution before any verbosity fix. No length behavior was changed.

---

## 1. Configuration

- **Ceiling:** `participant_response_max_tokens: 4000` (effectively uncapped; set via session config)
- **Mode:** emergent, `inject_participant_intro: false`
- **Run label:** 42 (recorded as `generation_seed` in the original config — renamed `run_label` 2026-06-29; recording-only, no effect on generation, since the Anthropic API has no seed parameter)
- **Guide:** `macho_meals_plant_based_masculinity_uk` (7 sections)
- **Turns:** 22 per run
- **Moderator model:** `claude-sonnet-4-6` (default)
- **Participant model:** `claude-haiku-4-5-20251001` (from agent files)

### Agent rosters

**Set A — younger (FG1, ages 20–27)**

| Agent | Age | Region | Diet | MascNorm | MascMeat | MeatAtt | DairyAtt | VegThreat |
|-------|-----|--------|------|----------|----------|---------|----------|-----------|
| David | 27 | Scotland | Meat eater | 2.7 | 1.7 | 3.6 | 4.2 | 1.8 |
| Isaiah | 26 | Yorkshire | Meat eater | 4.5 | 4.6 | 4.2 | 4.2 | 3.6 |
| Amir | 20 | West Midlands | Meat eater | 4.0 | 5.0 | 5.0 | 4.4 | 3.0 |
| Ibrahim | 24 | North East | Meat eater | 4.4 | 1.4 | 4.2 | 2.6 | 1.4 |

**Set B — older (FG5, ages 64–73)**

| Agent | Age | Region | Diet | MascNorm | MascMeat | MeatAtt | DairyAtt | VegThreat |
|-------|-----|--------|------|----------|----------|---------|----------|-----------|
| Fletcher | 64 | Scotland | Meat eater | 3.1 | 2.3 | 4.2 | 4.8 | 1.9 |
| Toby | 68 | South West | Meat eater | 2.5 | 1.1 | 4.4 | 4.0 | 1.6 |
| Keith | 72 | North West | Flexitarian | 4.5 | 3.6 | 4.0 | 3.0 | 1.9 |
| Patrick | 73 | South East | Meat eater | 3.2 | 2.4 | 3.6 | 3.4 | 1.5 |

### Run matrix

| Run | Agents | Run label | Turns | Sections reached | Log directory |
|-----|--------|-----------|-------|------------------|---------------|
| A1 | Set A | 42 | 22 | 3/7 (main_topic) | `output/session_logs/verbosity_baseline_A1/` |
| A2 | Set A | 42 | 22 | 3/7 (main_topic) | `output/session_logs/verbosity_baseline_A2/` |
| B1 | Set B | 42 | 22 | 2/7 (context) | `output/session_logs/verbosity_baseline_B1/` |
| B2 | Set B | 42 | 22 | 2/7 (context) | `output/session_logs/verbosity_baseline_B2/` |

---

## 2. Response-Length Distribution (84 responses, uncapped at 4000)

### Overall

| Metric | Tokens | Words |
|--------|--------|-------|
| Median | 202 | 152 |
| Mean | 188 | 140 |
| Min | 24 | 13 |
| Max | 332 | 255 |
| Std dev | 83 | 64 |

### Per run

| Run | n | Tokens median | Tokens mean | Token range | Words median | Words mean |
|-----|---|---------------|-------------|-------------|--------------|------------|
| A1 | 21 | 157 | 146 | 24–245 | 119 | 109 |
| A2 | 21 | 151 | 143 | 29–232 | 111 | 105 |
| B1 | 21 | 252 | 240 | 55–332 | 188 | 181 |
| B2 | 21 | 232 | 223 | 45–323 | 179 | 167 |

### Per agent

| Agent | Age | n | Tokens median | Tokens mean | Token range | Words median | Words mean |
|-------|-----|---|---------------|-------------|-------------|--------------|------------|
| Amir | 20 | 9 | 153 | 126 | 29–232 | 110 | 91 |
| Ibrahim | 24 | 11 | 189 | 166 | 32–236 | 145 | 123 |
| Isaiah | 26 | 9 | 151 | 141 | 30–227 | 107 | 106 |
| David | 27 | 13 | 149 | 141 | 24–245 | 109 | 104 |
| Fletcher | 64 | 12 | 248 | 218 | 48–291 | 182 | 164 |
| Toby | 68 | 12 | 236 | 210 | 55–291 | 174 | 158 |
| Keith | 72 | 9 | 232 | 231 | 45–318 | 182 | 173 |
| Patrick | 73 | 9 | 295 | 278 | 195–332 | 218 | 208 |

---

## 3. Reproducibility Finding

| Pair | Mean tokens | Difference | % of average |
|------|-------------|------------|--------------|
| A1 vs A2 | 146 vs 143 | 3 | 2% |
| B1 vs B2 | 240 vs 223 | 18 | 8% |

Run-to-run noise is small: 2% for Set A, 8% for Set B. The length difference between Set A and Set B (80+ tokens) is far larger than the within-set noise (3–18 tokens). The measurement is stable enough to draw conclusions.

---

## 4. Persona Finding

| Set | Age range | n | Tokens median | Tokens mean |
|-----|-----------|---|---------------|-------------|
| Set A (younger) | 20–27 | 42 | 152 | 145 |
| Set B (older) | 64–73 | 42 | 250 | 231 |
| **Ratio** | | | **1.6x** | **1.6x** |

Response length is **strongly persona-driven**. Set B (older) produces responses 1.6x longer than Set A (younger) by both median and mean tokens. This holds consistently across all four agents in each set:

- The 4 younger agents cluster at 126–166 mean tokens.
- The 4 older agents cluster at 210–278 mean tokens.
- Patrick (73) averages 278 tokens — 2.2x longer than Amir (20) at 126 tokens.

The length difference is not explained by the profile data (both sets have similar amounts of demographics, food consumption, and notes). The model appears to give older personas longer, more discursive turns — likely interpreting the age signal as more life experience and willingness to elaborate.

**Secondary effect — pace:** Set B's longer responses slow section progression. In 22 turns, Set A reached 3/7 sections (into main_topic) while Set B reached only 2/7 (still in context). Longer individual responses mean fewer turns available for the moderator to advance the discussion.

---

## 5. Ceiling Impact

### Uncapped runs (this measurement)

- Responses exceeding 400 tokens: **0/84 (0%)**
- Maximum response: **332 tokens** (Patrick, Set B)
- The model's natural stopping point is well under 400 tokens.

### Past runs at 400-token ceiling

| Run | Ceiling | Responses | Truncated | Rate |
|-----|---------|-----------|-----------|------|
| `macho_meals_emergent_full_run_02` | 400 | 42 | 0 | 0% |
| `verification_emergent_25` | 400 | 28 | 0 | 0% |
| `verify_handoff` | 400 | 11 | 0 | 0% |
| `verify_direct_address` | 400 | 7 | 0 | 0% |
| `food_mood_eating__diverse_4__emergent_seed42` | 400 | 15 | 0 | 0% |
| **Total** | | **103** | **0** | **0%** |

The 400-token ceiling has **never truncated a response** in any recorded run. It is completely inert — the model's natural stopping point (max observed: 332 tokens) is always below the ceiling.

Note: some past runs used `claude-sonnet-4-6` for participants (via the validation script's runtime patching); this measurement used `claude-haiku-4-5-20251001` (the agent-file default). Both models stay well under 400 tokens.

---

## 6. Plain-Language Summary

Uncapped, Macho Meals participant responses run roughly **100–250 words** (median 152 words / 202 tokens). Length is **strongly persona-driven**: older participants (64–73) produce responses 1.6x longer than younger ones (20–27), with the longest individual averages around 210 words. The current 400-token ceiling has **never truncated a response** in any recorded run — the model naturally stops well below it. Any verbosity concern is about the model's *chosen* length, not about ceiling-imposed truncation.

---

## 7. Not a Fix

This document measures the baseline. No verbosity fix was applied — no `max_tokens` change, no length instruction added, no prompt edited. The fix is a separate task to be designed against these results.

---

## 8. Run Artifacts

Session configs: `examples/verbosity_baseline_{A1,A2,B1,B2}.json`
Session logs: `output/session_logs/verbosity_baseline_{A1,A2,B1,B2}/`
Run label: 42 (all runs; recording-only — see terminology note below)

> **Terminology corrected (2026-06-29):** these runs were replicated under
> identical configuration, not seed-matched — the system has no functional
> seed (the Anthropic API exposes none). The field then called
> `generation_seed` (now `run_label`) had zero effect on generation. All
> measured numbers in this document are unchanged; only this terminology
> was corrected.
