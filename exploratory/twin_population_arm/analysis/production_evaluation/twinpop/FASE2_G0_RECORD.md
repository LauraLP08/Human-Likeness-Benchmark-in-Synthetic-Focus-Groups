# Phase 2 — Code change and gate G0

*4 August 2026. Evidence record for the twin-population arm.
Pre-registration: `PREREGISTRO_BRAZO_TWIN_POBLACIONAL_2026-08-04.md` §3.4 and §9 (G0).*

**Result: G0 PASS on all four sub-gates. The change stands as applied.**

---

## 1. The change

Single file modified: `core/participant_agent.py`, inside
`build_participant_system_prompt`. Two modifications, both specified verbatim in §3.4 of the
pre-registration:

1. **New "Layer 2b" branch** for `persona.background`, inserted **immediately after the
   `food_consumption` block and before the generic loop**, so that it occupies the same
   serial position as the `full` enrichment. It renders with the **same guardrail** as the
   consumption block (*"speak from these naturally — don't list them, just let them inform
   your answers"*), in EN and ES. It is a no-op when the key is absent
   (`payload["persona"].get("background", {})`).
2. **`"background"` added to the skip tuple** of the generic loop, which goes from
   `("demographics", "food_consumption", "psychological_profile")` to include it. **Without
   this step the block would be emitted twice** — once by the new branch and once by the loop
   — pushing volume to ~2× and invalidating G4 without any other gate noticing.

Not touched: `orchestrator.py`, any prompt, any test, any existing config, any existing
agent.

---

## 2. G0.a + G0.b — 111 agents, both intro settings

Harness: `scripts/twinpop_g0_render_hashes.py` (new, additive, read-only over the pipeline).
Captures: `g0_before.json` / `g0_after.json` in this same directory.

| | Value |
|---|---|
| Agents covered | **111**, 0 omitted |
| Breakdown | macho_meals 22 · macho_meals_demoonly 22 · deepfakes 39 · mindfulness 5 · sustainable_fashion 23 |
| Per agent | SHA-256 of the rendered prompt with `inject_participant_intro=False` **and** `=True`, plus SHA-256 of `profile_summary` |
| Differences | **0** |

Covering 111 rather than 44 is the point: `deepfakes.study_profile` and
`mindfulness.professional_profile` are dictionaries that render **through the same generic
branch that was modified**, and mindfulness is DS05, an already-reported result. A G0 limited
to macho_meals would not have detected damage to them.

`profile_summary` covers the moderator path (`moderator_brain.py:490`), which consumes that
field.

## 3. G0.c — code not touched

15 objects verified by SHA-256 of `inspect.getsource` / `repr`, all identical:

- Functions: `load_agent_from_json`, `assess_engagement`, `call_participant`,
  `_render_cacheable_messages`, `_format_recent_transcript`, `_score_to_instruction`,
  `_bucket`, `_stable_variant_index`.
- Constants: `_BEHAVIOUR_INSTRUCTIONS`, `_BEHAVIOUR_INSTRUCTIONS_ES`, `_DIMENSION_TIER`,
  `_HABIT_TEMPLATES`, `_CODED_TEMPLATES`, `_DISPOSITION_HEADER_EN`, `_DISPOSITION_HEADER_ES`.

`build_participant_system_prompt` is deliberately **outside** the list: it is the only thing
that changes.

## 4. G0.d — existing suite unmodified, executed and green

| Moment | Result |
|---|---|
| Before the change | **159 passed** |
| After the change | **159 passed** |

Files: `test_psychographic_disposition_rendering.py`, `test_participant_prompt_caching.py`,
`test_macho_meals_emergent_run_validation.py`, `test_agent_fidelity.py`,
`test_agent_fidelity_audit_v2.py`, `test_agent_fidelity_corrections.py`. None was edited.

---

## 5. Positive control — the change does what it should

G0 demonstrates that it **breaks nothing**; it is also necessary to demonstrate that it
**works**. Probe over `mm_fg3_andrew` from `demoonly` with a `background` block of markers
injected in memory (no agent file created; that is phase 3):

- Each of the three prose strings appears in the prompt **exactly once** — this is the
  assertion G1 will require, and the direct proof that the skip tuple prevented double
  rendering.
- Guardrail present in the block.
- **Diff against the same agent without `background`: the only difference is the `background`
  block** (header + 3 bullets). That is exactly G1's mechanical negative assertion, already
  validated as a procedure.

Rendering obtained:

```
Your everyday life (speak from these naturally — don't list them, just let them inform your answers):
  - Working life: ...
  - Home and household: ...
  - Week and hobbies: ...
```

## 6. A measurement that refines — without altering — the frozen addendum

Actual framing and label overhead of the `background` block: **28 words** (header plus the
three labels). The frozen addendum estimated *"~25 words"*.

**The addendum is not reopened.** The binding entry is G4's band — **220–300 net words
measured over the complete rendered block** — and that does not change. The only thing that
shifts is the derived per-key guidance: to avoid exceeding the ceiling of 300, read
**64–90 words per key** instead of 65–92 (3 × 92 + 28 = 304, four words above the ceiling).
G4 measures the rendered block, so an out-of-band candidate is resampled anyway: the band is
self-correcting and the frozen rule operates intact.

This is recorded here rather than edited there, in accordance with the addendum's
modification rule: nothing is edited silently.

---

## 7. Status

Phases 0, 1 and 2 complete. **Nothing generated, no session run, zero API spend.**

Next: **phase 3** — census download with its manifest, sampling with seed `20260804`,
generation of the 24 candidates and their 24 gender-inverted twins, and gates G1, G2, G3, G4
and G4b. Estimated cost < $2 in short generation calls; no sessions.
