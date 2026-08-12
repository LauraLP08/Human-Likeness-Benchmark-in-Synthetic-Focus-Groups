# Changelog

All notable changes to this project are recorded here. Newest first.

## 2026-08-04 — `persona_stress_test` closed as an internal diagnostic, not reported; Level 3 closure position recorded

**Scope:** `analysis/production_evaluation/persona_stress_test/PERSONA_STRESS_TEST_V2_EXCLUSION_RECORD.md`
(new), `.../pst_v2_closure_status.json` (new), `analysis/production_evaluation/metric_registry.csv`
(caveats only), `docs/evaluation_framework_summary.md`, `docs/evaluation_framework.md`,
`scripts/persona_stress_test_v2.py` (docstring). **No API calls, no new adjudications,
no run artefact modified or deleted, no historical result rewritten.**

**Decision:** `EXPLORATORY_PERSONA_ROBUSTNESS_STRESS_TEST` is closed with status
`EXPLORATORY_INTERNAL_DIAGNOSTIC_NOT_REPORTED`. It passed all technical gates and gave
consistent evidence on resistance to false autobiographical premises and on epistemic
calibration, but character-maintenance classification was insufficiently stable in the
`INSTRUCTION` family, the maintain/break boundary needs human validation that is not
available, and the protocol pre-specified no substantive pass thresholds. It therefore
supports no defensible inference about persona fidelity and stays outside the reported
corpus: nothing enters `FINAL_RESULTS_TABLES.xlsx`, `metric_registry.csv`, the Results
chapter or any confirmatory result, and it discharges no framework indicator. This is a
scope decision, not a failed experiment.

**Taxonomy:** `persona_stress_test` sits in the complementary agent-fidelity layer,
**Level 4** — not Level 3 interactional. Its unit of analysis is an individual agent
probed outside a group discussion.

**Framework closure position:** Level 3 structural is **reported**; Level 3 interpretive
is **`NOT_IN_REPORTED_INSTRUMENT`**, retained in the framework and excluded
**prospectively** for want of human validation, without reference to its values.
Confirmatory coverage of the interactional level is therefore limited to Level 3
structural, and it must not be stated that Level 3 was completed. Persona fidelity,
profile continuity and profile consistency were **not validated**; the final documents
were swept to confirm none claims otherwise.

**Traceability:** all twelve run artefacts are preserved unaltered, with sha256 hashes
recorded at closure in `pst_v2_closure_status.json`.

## 2026-07-24 — Macho Meals FG3 agents built (17 → 22); FG3 identity linkage is a researcher random assignment

**Scope:** `agents/macho_meals/mm_fg3_{andrew,daniel,john,nick,paul}.json` (new),
`agents/macho_meals/_manifest.json`,
`data/datasets_transcripts/standardized/macho_meals/fg3/{identity_reconciliation,participant_metadata,baseline_metadata}.json`,
`data/datasets_transcripts/standardized/macho_meals/MACHO_MEALS_STANDARDIZATION_REPORT.md` (addendum),
`scripts/build_macho_meals_fg3_agents.py` (new). Data-only — **no `core/` file touched, no API calls.**

**Motivation:** The original build (`scripts/build_fg_agents.py`) skipped all five
`Focus Group == 3` rows of `DS03_MACHO_MEALS_UK` because a PID recording error made it
impossible to tie a survey row to a named FG3 transcript speaker; the rows carried dash
placeholders and the manifest recorded them as excluded. The researcher has since
resolved this by **randomly assigning**, 1:1, the five real FG3 survey rows to the five
known FG3 speaker names (Andrew, Daniel, John, Nick, Paul). The resolution is recorded
in `data/manifests/focus_group_dataset_manifest_v5.xlsx`, sheet `DS03_MACHO_MEALS_UK`,
where the FG3 `Pseudonym` column now holds those real names. This is a deliberate
deviation from the neutral-label fallback of `INSTRUCTIONS_AGENT_BUILD.md` §4/§7.

**Change 1 — five FG3 agents built.** Same `fg_agents_v1` shape as the other 17.
Fixed construct/direction/scale boilerplate is copied verbatim from the on-disk
`mm_fg1_amir.json` by the build script (25/25 dimension comparisons byte-identical),
so only `value` varies. All five intro cells are empty, so the `opening_intro` key —
and its two `field_provenance` entries — are omitted entirely, following
`sf_fg3_angel.json` rather than emitting an `intro_eligible: false` stub.
Roster is now **22** = the study's 22 real participants (FG1 5, FG2 5, FG3 5, FG4 3, FG5 4).

**Change 2 — machine-readable linkage caveat, deliberately outside the prompt path.**
Each FG3 agent carries `study_context.identity_metadata_linkage:
"researcher_random_assignment"` plus a full `identity_metadata_linkage_note`, and a new
`field_provenance` entry `"study_context.identity_metadata_linkage": "researcher_declared"`.
Placement matters: `build_participant_system_prompt()` never reads `study_context`, but it
*does* render any other dict-valued key directly under `persona` into the prompt as
"Additional context about you" (generic fallback loop, `core/participant_agent.py:355`).
Placing the caveat under `persona` would have told the simulated participant its own
identity was randomly assigned. Verified empirically — see Change 4.

**Change 3 — history preserved, not overwritten.** `_manifest.json`'s original
`excluded` object is renamed to `excluded_historical` with its wording byte-identical and
a `status: "superseded — see fg3_resolution above"` added; a new `fg3_resolution` block
records the resolution and the five agent_ids. In `baseline_metadata.json` the original
`fg3_exclusion_note` is kept verbatim and a `fg3_resolution_note` is appended alongside it.
The 2026-06-28 body of `MACHO_MEALS_STANDARDIZATION_REPORT.md` is left intact; a dated
addendum records the new status.

**Change 4 — verification, all no-API.** Schema validation against
`scripts/twin2k500_schema_mirror.py::AgentPayload`: new 5/5 valid, all 22 valid, 0 invalid.
Count check: 22 files, 22 unique agent_ids, 0 duplicates, every filename matching its
`agent_id`. Render test on `mm_fg3_paul` with `inject_participant_intro=True` (worst case):
the strings `identity_metadata_linkage`, `random`, `assign`, `PID`, `survey`, `arbitrary`
and the block `"Additional context about you"` are all **absent** from the rendered prompt;
layer order is identical to `mm_fg1_amir` apart from the expected missing intro line.
Load test: all five `agent_payload_path`s construct valid `ParticipantState` objects via
`core.orchestrator._build_state_from_config`.

**Methodological limitation (must reach the dissertation write-up, not just this file):**
**FG3 individual-level persona-to-transcript correspondence is not genuine** — per-participant
fidelity scoring, individual persona-adherence checks, and speaker-level survey↔transcript
correlations must exclude FG3 or carry this caveat. **FG3 group-level/aggregate data is
genuine** (all five rows are real FG3 data, so composition, means and spread are unchanged),
and group-level synthetic↔human FG3 comparison remains valid. FG1/FG2/FG4/FG5 are unaffected.

Full detail: `docs/changes/2026-07-24_macho_meals_fg3_agent_build.md`.

## 2026-07-17 — Gate 1 normalization-robust quote matching + 5-run repeatability + --out fix

**Scope:** `scripts/thematic_coding.py`, `scripts/validate_thematic_measure.py`,
`analysis/coding_frame/quote_match_audit.jsonl` (created on first run).

**Motivation (diagnosed mechanism, not tuned to threshold):** Gate 1 repeatability
previously failed at worst-pairwise 0.8182 < 0.85. Diagnostic instrumentation
(`disagreement_diagnostic` block added in prior pass) confirmed this was an
**artifact**, not genuine coding instability: Gemini's semantic judgment of codes
C.2 and D was unanimous "present" across all 3 runs, but in one stochastically
varying run the model rendered a supporting quote with minor punctuation/quote-character
differences, failing the old `q.strip() in blind_text` exact-substring check and
demoting those codes to `present=False`. The disagreeing runs were exactly the two
demoted codes — the mechanism was unambiguous.

**Change 1 — normalization-robust quote matching (`thematic_coding.py`):**
Added `_normalize_for_match(s)` (NFKC → curly-quote mapping → dash/ellipsis mapping
→ NBSP collapse → whitespace collapse → casefold → strip punctuation) and replaced
`_is_verified_quote()` to match on canonicalized forms of both quote and transcript.
This is **exact-after-normalization** — zero fuzzy/edit-distance tolerance added.
A fabricated quote does not normalize into real transcript text; the guardrail against
fabricated evidence is preserved.

**Change 2 — integrity reporting + audit trail (`thematic_coding.py`):**
`QuoteValidityStats` gains `raw_exact_quotes` and `normalized_recovered_quotes`
fields so the loosening is fully visible. `verify_codes()` tracks which quotes passed
raw vs only after normalization, and appends one JSON line per recovered quote to
`analysis/coding_frame/quote_match_audit.jsonl` (eyeballed to confirm near-verbatim,
not fabricated). Headline verification/preservation rates are now computed on the
normalization-robust check; raw-exact counts are also surfaced.

**Change 3 — 5-run repeatability (`validate_thematic_measure.py`):**
`run_gate1()` now codes real FG1 `N_REPEAT=5` times (was 3), computing agreement
over all 10 pairwise combinations (`itertools.combinations`). `three_way_agreement`
renamed to `all_way_agreement` (unanimous across all 5). Pre-fix worst pairwise was
0.8182; post-fix result is reported in full alongside audit log in the session where
this was run (2026-07-17). REPEATABILITY_THRESHOLD unchanged at 0.85.

**Change 4 — fix pre-existing `--out` crash (`validate_thematic_measure.py`):**
`out_path.relative_to(_REPO_ROOT)` raised `ValueError` when `--out` received a
relative path. Fixed by resolving to absolute at parse time and wrapping the display
line in `try/except ValueError` (falls back to printing the full absolute path).

## 2026-06-30 — Full-session cost fix: summary-accumulation compression + targeted caps

**Scope:** `core/session_state.py`, `core/orchestrator.py`, `core/moderator_brain.py`,
`core/prompt_renderer.py`; new `scripts/run_full_session.py`;
`prompts/06_MODERATOR_REFLECTION_PROMPT.md` updated.

**What changed:** Fixed the full-session token-growth blocker
(`docs/findings/2026-06-30_full_session_token_growth_issue.md`) with four
targeted, independently-toggleable changes built on one shared primitive.
(0) `GroupState.section_summaries` now **accumulates** one summary per
completed section (was a single overwritten slot). (1) **Dominant fix** —
new `moderator_context_mode: "summarized"|"full"` (default `"full"`,
behavior-preserving): in `"summarized"` mode the moderator's regular
decision call receives only the current section's verbatim transcript +
all accumulated summaries, instead of the full untrimmed session —
explicitly reversing the "moderator sees everything, it's not
context-starved" decision from the prior moderator review, now made
deliberate and cost-justified. (2) Engagement's `own_history` gets an
optional token-budget cap (`engagement_own_history_token_budget`, default
`None`), recency-biased, preserving the field's repetition-suppression
purpose. (3) Reflection now summarizes only the since-last-reflection
slice + carries prior summaries forward, instead of re-sending the full
transcript every call. (4) Participant `episodic_depth` set to
`since_last_n` for full-session configs (already-built mechanism, just
applied).

**Why:** The killed full-session smoke test showed moderator calls growing
linearly to 93,505+ tokens with no ceiling, projected past 100K before
natural completion — full natural-completion sessions (required by the
thematic-fidelity experiment) were not affordable without this.

**Validated, not assumed:** a real full FG5 session ran with all four
fixes on and **completed naturally — 7/7 sections, 78 turns**, total
4.1M input tokens (vs. 5.59M for the old approach's *incomplete*, shorter,
still-climbing 70-turn/6-section run). Final moderator call: 34,951 tokens
vs. the old run's 93,505 at a comparable point — a 62.6% reduction, for the
end of a *finished* session vs. an unfinished one. Themes proven preserved
(the actual turn-75 closing synthesis traces clause-by-clause to all 6
prior accumulated summaries — quoted in full in the deliverable).
Repetition-suppression proven intact (max pairwise utterance similarity
0.696 across 153-231 pairs per participant; no near-duplicates). Honestly
reported: the moderator-side bound is real but not perfectly flat (small,
structurally-bounded residual growth from the summaries themselves); the
participant-side fix bounds the worst case (32×→~1.25× residual drift) but
doesn't fully flatten, since utterance length itself grew ~46% over the
session and `since_last_n` caps entry count, not entry length.

**Trace:** `docs/changes/2026-06-30_full_session_cost_fix.md`

---

## 2026-06-30 — Moderator duplication fix + reflection mechanism + restraint language (A), n=10×3 experiment

**Scope:** `core/session_state.py`, `core/moderator_brain.py`, `core/orchestrator.py`,
`core/prompt_renderer.py`, `core/config.py`; new `prompts/05_MODERATOR_RESTRAINT_BLOCK.md`,
`prompts/06_MODERATOR_REFLECTION_PROMPT.md`.

**What changed:** Fixed a narrow moderator self-duplication (own last-3
utterances appeared in both `transcript` and `moderator_log` window) —
folded into baseline, not assumed neutral. Built two independently
toggleable mechanisms (both default OFF, verified byte-identical to prior
behavior when off): (1) a reflection mechanism — a deterministic
`GroupState.moderator_turn_share_overall`/`_recent` field (the moderator's
own turn-share, computed every turn, no LLM call — closing the diagnostic's
Candidate-C gap) plus two ≤80-word LLM summaries regenerated fresh at
section boundaries only (thematic discussion synthesis + strategy
synthesis, ordered before the transcript, one-channel rule — no
coverage/participation restated); (2) a restraint-language block
(`moderator_restraint_prompt`) added to the system prompt, calibrated
against the real-human 4-15% turn-share baseline, balancing the existing
one-sided "be active" language (Candidate A) without relaxing any existing
rule.

**Why:** Diagnosed in
`docs/changes/2026-06-30_moderator_overintervention_diagnostic.md` — the
moderator's over-intervention is the model's own voluntary choice (93-95%
of interventions), driven primarily by one-sided prompt tone (A, strong)
and the absence of any self-participation-awareness signal (C, strong).

**Experiment:** n=10 × 3 conditions (Baseline / +A / +A+Reflection), same
agents/guide/turn-budget, replicated not seeded. Restraint language (A)
produced a real, meaningfully-sized effect (72-75% pairwise dominance over
baseline on turn-share and adjacency — median/spread alone was inconclusive
at this discrete, n=10 scale, resolved via a rank-based test). Reflection's
marginal effect on top of A was not distinguishable from chance (54%/44%)
on these two metrics at a 14-turn budget (1-2 reflection firings/run).
Gap to the matched human baseline (FG1, corrected from the instructions'
group pairing — see findings doc) narrowed but did not close (10.6-18.0pp
remaining, depending on metric/statistic).

**Not addressed:** Candidate B (missing lightweight backchannel action) —
explicitly out of scope for this task.

**Trace:** `docs/changes/2026-06-30_moderator_dedup_A_reflection.md`,
`docs/findings/2026-06-30_moderator_overintervention_experiment.md`

---

## 2026-06-29 — Renamed `generation_seed` → `run_label`; corrected "seed" terminology in findings

**Scope:** `core/session_state.py`, `core/orchestrator.py`, 18 example session
configs, `ARCHITECTURE.md`, `docs/operational_flow.md`,
`docs/operational_flow_verification.md`,
`docs/changes/2026-06-27_architecture_reconciliation.md`,
`docs/findings/2026-06-27_verbosity_baseline.md`,
`docs/changes/2026-06-29_participant_memory_dedup_fix.md`,
`methodology_package/` (matching copies).

**What changed:** Renamed the `generation_seed` field to `run_label` and
changed its type from `int | None` to `str | None` (a label is more
naturally a string than an int). Behavior-preserving: a config omitting the
field still gets `None`; a config setting it now records that value in
state, exactly as before — only the name and type changed, not the
(non-)effect. Swept "same seed" / "seed 42" / "seeded" language in findings
docs to accurate terminology ("replicated runs under identical
configuration"); no measured numbers altered.

**Why:** Verified against Anthropic's API documentation — the Messages API
exposes no `seed` parameter, and even at temperature 0 output is not fully
deterministic. `generation_seed` always had zero functional effect
(confirmed: never read anywhere that touches an API call), but its name
falsely implied a determinism control the system cannot have. This led to
"same seed" language appearing in findings for runs that were never
seeded — a terminology bug, not a measurement bug.

**Verification:** Re-confirmed no functional reader of the old field ever
existed — grepped `core/` and `scripts/` for both `generation_seed` and any
`seed=` parameter passed to an API call; the only `seed=` usage anywhere in
the codebase is the unrelated stratified sampler's own Python
`random.seed()` for deterministic agent-panel composition
(`scripts/twin2k500_sample.py`), which is accurately named and untouched.

**Not touched:** `output/session_logs/**` (historical run artifacts —
recorded fact of what those runs' state contained, not revised),
`docs/testing/macho_meals_emergent_run_validation/**` (same), and any
`INSTRUCTIONS_*.md` file (historical task instructions, not revised).

**Trace:** `docs/changes/2026-06-29_rename_seed_to_run_label.md`

---

## 2026-06-29 — Participant memory de-duplication fix + episodic depth parameter

**Scope:** `core/orchestrator.py`, `core/participant_agent.py`, `core/session_state.py`.
New: `scripts/collapse_metric.py`.

**What changed:** Fixed two confirmed duplication sources in participant
response generation: (1) window-overlap between consecutive calls'
recent-transcript slices, (2) the participant's own prior turn re-rendered
as `[You]: ...` despite already being present as a native `assistant`
message. Fix: each call now receives only transcript entries since the
participant last spoke (full episodic memory, no fixed window, no
re-inclusion). Added `participant_episodic_depth` session-config parameter
(`full` default, `since_last_n`, `recent_k`) so depth is a tunable
parameter, not an assumption. Also wired `inject_participant_intro` and
`generation_seed` (renamed `run_label` later the same day — see the
2026-06-29 rename entry below) into config loading — both were defined on
`SessionMeta` but silently ignored before this fix; defaults set to match
confirmed prior effective behavior (behavior-preserving).

**Why:** Diagnosed in `docs/changes/2026-06-29_participant_memory_review.md`.
Per Chen et al. (ACE), redundant context degrades output quality, not just
cost. Per Bhattacharyya, more context is not assumed monotonically better —
episodic depth needed to be a testable parameter, not a hardcoded "full."

**Verification:** Duplication elimination proven by reconstructed real
messages array (zero overlap, zero self-duplication, clean boundary).
Engagement assessment's code path proven structurally unchanged (zero
lines touched in `assess_engagement`, `_recent_transcript`,
`_get_participant_own_turns`, or their call site) — the decisive proof,
since a cross-run empirical comparison was found to be fundamentally
confounded by hosted-LLM non-determinism (two PRE-FIX runs of identical
config diverge by a comparable or greater amount than any before/after
comparison).

**Verbosity re-measurement:** 3 replications per condition (before/after
fix), Set A and Set B. Before→after difference (-4 to -8 words) is smaller
than within-condition run-to-run spread (7-85 words) — not distinguishable
from noise at this replication count.

**Collapse pilot:** TF-IDF-based inter-agent distinctiveness metric
(documented lexical-embedding limitation — no semantic embedding library
configured in this environment). 3 depth levels × 3 reps. Trend
(full − recent_k = +0.029) smaller than noise SD (0.084) — no detectable
collapse effect within this short-run range (~15 turns). Reported as a
pilot; the complete-session test remains the definitive version.

**Reversibility:** Set `participant_episodic_depth: "recent_k"` with
`participant_episodic_recent_k: 6` in session config to approximate prior
(buggy) windowing behavior, minus the self-duplication (which has no
clean revert — it was strictly a defect).

**Trace:** `docs/changes/2026-06-29_participant_memory_dedup_fix.md`

---

## 2026-06-27 — Architecture reconciliation (documentation only)

**Scope:** `ARCHITECTURE.md`, `docs/operational_flow.md`,
`docs/operational_flow_verification.md` (header added).

**What changed:** Corrected all stale claims in `ARCHITECTURE.md` identified by
the verification task; upgraded `docs/operational_flow.md` into the single
authoritative operational reference with [observed]/[static]/[dormant] status
tags on every claim. No code or behavior changed.

**Corrections to `ARCHITECTURE.md`:**
- Removed all `next_speaker` field documentation (field does not exist).
- Replaced `_get_requested_next_speaker` references with the direct-address
  floor-handoff mechanism; noted the function as dormant.
- Updated moderator model from hardcoded `claude-sonnet-4-20250514` to
  configurable `session_meta.moderator_model` (default `claude-sonnet-4-6`).
- Fixed "never populated" annotations on `last_response_quality`,
  `engagement_signal`, `topics_covered`, `emergent_themes`,
  `group_has_agreed_easily_on` — all are populated via the feedback loop.
- Fixed phase modifier and conflict injection claims — both now fire.
- Removed stale "2–5 sentences" quoted block; documented current behaviour
  instructions (no sentence-count rule).
- Marked Layer 3 `psychological_profile` render path as removed.
- Updated `participant_collective_identity` — no longer in participant prompts.
- Added `inject_participant_intro`, `generation_seed` (renamed `run_label`
  2026-06-29), `moderator_model` to the SessionMeta table.
- Fixed api_calls.jsonl description — now logs participant and engagement calls.
- Updated Last-updated date.

**`docs/operational_flow.md` upgrade:** Restructured into 9 required sections
(Inputs, Outputs, Order of actions, Decision branches, How decisions are made,
Model vs hard-coded table, Model freedom vs constraints, Flowchart, Verification
status key). Added Appendix (worked example). Every claim tagged [observed],
[static], or [dormant].

**Disposition of verification doc:** `docs/operational_flow_verification.md`
retained as the evidence appendix; header added pointing to the authoritative
`operational_flow.md`.

**Trace:** `docs/changes/2026-06-27_architecture_reconciliation.md`

---

## 2026-06-26 — Configurable moderator model, A11 exit-code fix, direct-address speaking

**Scope:** `core/moderator_brain.py`, `core/session_state.py`, `core/orchestrator.py`,
`core/participant_agent.py`, `run_session.py`.

**What changed:**

1. **Configurable moderator model.** The moderator model was hardcoded as
   `claude-sonnet-4-20250514` (returned HTTP 404 from the current API key,
   making `run_session.py` unusable). Added `moderator_model` field to
   `SessionMeta` (default `claude-sonnet-4-6`), read from session config.
   `moderator_brain._call_api` now accepts a `model` parameter passed from
   `call_moderator`. Mirrors the proven participant model pattern
   (`simulation_config.model` → fallback default).

2. **A11 exit-code fix.** `run_session.py` summary printing crashed with
   `AttributeError` when `entry.action` was `None` (observe/yield turns).
   Guarded with a conditional: `None` actions print as `"observe_yield"`.
   The session now exits 0 on successful completion.

3. **Direct-address speaking.** When the moderator addresses a single
   participant by name (any action with a single resolved target), that
   participant is hard-handed the floor on the next step, bypassing the
   urgency auction. When the moderator addresses multiple participants
   (comma-separated target), each receives the invite bonus (+0.15) and
   the normal auction runs. General questions (target `"group"` or `None`)
   are unaffected. Added `_resolve_moderator_targets` helper to the
   orchestrator. Added a behaviour-instruction line (English + Spanish)
   telling addressed participants that a brief or deflecting answer is
   acceptable.

**Verification:**
- 12-turn emergent run via `run_session.py` (no runtime patching): exit 0,
  three `moderator_direct_address` hard handoffs observed in transcript
  (turns 7, 11, 12), all seated the correct participant.
- General-question turns (target=group) produced `voluntary` selections.
- Moderator prompt was NOT edited; no frequency cap added.

**Trace:** `docs/changes/2026-06-26_moderator_model_and_direct_address.md`

---

## 2026-06-11 — Twin-2K-500 agent files retired; legacy agent schema superseded

**Scope:** `agents/twin2k500/` (deleted — 2,058 generated JSON files);
`ARCHITECTURE.md` Appendix B (schema documentation updated).

**What changed:** All 2,058 generated agent JSON files in `agents/twin2k500/`
have been deleted. The Twin-2K-500 agent JSON schema (`schema_version:
"agents_v1"`) is retired. The native focus-group agent schema
(`schema_version: "fg_agents_v1"`) is being designed as a successor.

**What was kept:**
- `scripts/twin2k500_*.py` — ETL pipeline, validator, schema mirror, sampler
- `scripts/panel_specs/` — panel spec YAMLs
- `data/twin2k500/` — raw Parquet dataset
- `examples/twin2k500_smoke.json`, `examples/twin2k500_smoke_v2.json` —
  smoke test configs (paths now dangling; re-runnable after ETL re-run)
- `examples/sessions/food_mood__diverse_4__emergent.json` — generated session
  config (paths dangling; re-generable via sampler after ETL re-run)
- `output/sample_manifests/` and `output/session_logs/` — run artefacts

**Why:** The Twin-2K-500 agents served as the first full-population agent set
for pipeline development but use a schema designed around survey-panel data
(demographic midpoints, Big Five psychology, `simulation_config.notes` as the
rich-persona layer). The four focus-group datasets (Macho Meals, Sustainable
Fashion, Deepfakes, Mindfulness) require a different shape: verbatim
transcript intros, psychometric scores with full interpretive anchors stored
for analysis rather than rendered into prompts, proper provenance tags, and
per-dataset study-context blocks. Retiring the old files removes the legacy
schema constraint before the new schema is finalised, allowing a clean native
design.

**Schema note:** The `persona.psychological_profile` path used by the old
schema's Layer 3 renderer is NOT used by focus-group agents. Psychometric
scores will be stored in a dedicated `psychometric_scores` block with full
construct/direction/scale metadata and are not rendered into participant
prompts by default.

**Downstream impact:**
- Session configs that reference `agents/twin2k500/twin_*.json` via
  `agent_payload_path` will fail to load until the ETL is re-run.
- The sampler (`scripts/twin2k500_sample.py`) requires the agent index to
  be rebuilt before it can produce new configs.
- No `core/` files were modified in this step.

**Reversibility:** Re-run `py scripts/twin2k500_etl.py` to regenerate all
2,058 agent files. The ETL script, raw data, and mapping YAML are all
retained. The generated files were deterministic given the same source data.

**Trace:** `docs/changes/2026-06-11_twin2k500_agents_retired.md`

---

## 2026-06-10 — Stratified sampler + first multi-participant emergent run + probing depth made optional

**Scope:** Three surgical lines in `core/` (`session_state.py`,
`orchestrator.py`, `moderator_brain.py`); new script
`scripts/twin2k500_sample.py`; three starter panel specs in
`scripts/panel_specs/`; `configs/guides/food_mood.yaml`;
`examples/sessions/food_mood__diverse_4__emergent.json` (generated by
sampler); `output/sample_manifests/` (sampler manifest).

**What changed:**

1. `core/session_state.py:124` — `probing_depth_ceiling` field on
   `DiscussionGuideSection` changed from required (`ProbingDepthCeiling`)
   to optional (`ProbingDepthCeiling | None = None`).
2. `core/orchestrator.py:146` — guide-loading dict access guarded so a
   missing key resolves to `None` instead of raising `KeyError`.
3. `core/moderator_brain.py:314` — `.value` access on the ceiling enum
   guarded against `None` in the prompt-state serialisation.
4. `scripts/twin2k500_sample.py` — new sampling script: reads a panel YAML
   and a discussion guide YAML, samples N agents satisfying the panel's
   filters and quotas via seeded rejection sampling, writes a session config
   with `agent_payload_path` entries. CLI: `--panel`, `--guide`, `--out`,
   `--mode`, `--seed`, `--max-tries`, `--manifest-dir`.
5. `scripts/panel_specs/{diverse_4,young_adults_4,older_adults_4}.yaml` —
   three starter panel specs. `diverse_4` (2M/2F, four distinct age buckets)
   is the balanced control. `young_adults_4` and `older_adults_4` form an
   age-cohort comparison pair.
6. `configs/guides/food_mood.yaml` — food/mood discussion guide adapted from
   a Krueger-format qualitative interview schedule. Nine sections (Opening
   through policy-level Closing). No `probing_depth_ceiling` declared — the
   moderator decides depth from `section_phase` and response content.
7. `scripts/twin2k500_sample.py::build_session_config()` — emits
   `probing_depth_ceiling` into generated configs only when the source guide
   explicitly sets it (at the section level or the guide level). Guides that
   omit the field produce sessions where the moderator probes contextually.
8. `examples/sessions/food_mood__diverse_4__emergent.json` — first generated
   multi-participant session config: 4 `agent_payload_path` entries,
   `participation_mode: "emergent"`, 9 sections, zero
   `probing_depth_ceiling` keys.

**Why:** Two blocked workstreams resolved together. The Phase 1 probing-depth
investigation (Bucket C: three hard failure points in `core/`) had to be
resolved before the food/mood guide could omit the ceiling field. The
stratified sampler adds the operational layer for comparative dissertation
work: "panel × guide × mode" session configs are now generated declaratively
rather than hand-authored. The food/mood guide is the first research
instrument in the system; removing the hardcoded ceiling restores the
moderator's ability to probe as deeply as the participant's actual response
warrants, rather than as a configured rule.

**Deviations from specification documents:**

- *Age-bucket strings:* Sampler doc assumed `"30-44"`, `"45-59"`, `"60+"`.
  Actual Twin-2K-500 buckets enumerated at Step 1 are `"18-29"`, `"30-49"`,
  `"50-64"`, `"65+"`. Panel YAMLs written with the correct strings; comments
  note the deviation.
- *Guide phase strings:* Sampler doc used Krueger phase names (`"opening"`,
  `"introductory"`, `"transition"`, `"key"`, `"ending"`). These do not match
  the `SectionPhase` enum. Guide written with correct system values; a
  mapping comment added at the top of `food_mood.yaml` for future guide
  authors.

**Verification:**

- Regression load: `examples/twin2k500_smoke.json` and
  `examples/twin2k500_smoke_v2.json` (both carry explicit
  `probing_depth_ceiling`) still load cleanly — the "field present" branch
  is regression-safe.
- Generated config: 9 sections, all `ceiling_present=False`, Pydantic
  validation clean.
- Smoke test (15 turns, emergent mode, `diverse_4 × food_mood`, seed 42):
  exit code 1 (see Known Issues); 4/4 participants spoke; per-participant
  turn balance 4/4/4/3 (`twin_545`/`twin_1808`/`twin_341`/`twin_1994`);
  single section transition (Opening → Defining healthy/unhealthy); 0
  moderator `validation_fallback` entries; 3 `assess_engagement` Pydantic
  validation failures degraded gracefully (affected participants continued
  to engage normally). Session substantively complete.

**Schema change:** `DiscussionGuideSection.probing_depth_ceiling` is now
`ProbingDepthCeiling | None = None`. Existing session configs that declare
the field with a valid enum value are unaffected.

**Known issues:** Three `assess_engagement` Pydantic validation errors
(`twin_1808` ×2, `twin_341` ×1) caused exit code 1. System degraded
gracefully; no moderator fallbacks; affected participants contributed
normally throughout. Filed for future investigation.

**Reversibility:**
- Revert the three `core/` lines to restore the required field.
- Add `probing_depth_ceiling` declarations to `food_mood.yaml` (top-level
  or per-section) — the field is now optional and the sampler will pass it
  through when present.
- Revert `build_session_config()` to the unconditional emission form.
Each revert zone is independent. No data migration required.

---

## 2026-06-10 — Age bucket bug fixed in Twin-2K-500 ETL

**Scope:** `scripts/twin2k500_etl.py`, `scripts/twin2k500_schema_mirror.py`,
`agents/twin2k500/*.json` (regenerated).

**What changed:** The Twin-2K-500 ETL now parses age buckets correctly.
Source values like `"18-29"` are converted to a midpoint integer (23 for
"18-29") and the original bucket string is preserved in a new optional field
`demographics.age_bucket`. Open-ended top buckets like `"65+"` use the
lower bound (65) as the integer and preserve the bucket string.
Previously, the `_to_int()` fallback coerced every bucket to `0`,
producing participant prompts that began "a 0-year-old Male."

**Why:** The structured `age` field must remain an integer per
ARCHITECTURE.md Appendix B and is read directly by the participant
prompt template in `core/participant_agent.py`. Storing 0 made every
prompt visibly wrong. Storing the midpoint preserves prompt grammar
and downstream filtering, while `age_bucket` preserves the honest
source data for analysis and stratified sampling.

**Verification:**
- ETL re-run: 2,058 produced, 0 skipped.
- Validation: exit 0.
- `agents/twin2k500/twin_574.json` now contains `age: 23, age_bucket: "18-29"`.
- v2 path-based smoke test (`twin2k500_smoke_v2.json`) re-ran; participant
  system prompt first sentence now reads "a 23-year-old Male" (was
  "a 0-year-old Male").
- v1 legacy inline smoke test re-ran cleanly with no regression.

**Schema change:** `Demographics.age_bucket` added as an OPTIONAL `str`
field. Appendix B updated in place to document it.

**Reversibility:** Re-run the ETL with the `_parse_age_bucket` helper
removed; the field will simply not be written. Existing files would
need to be regenerated or deleted.

---

## 2026-06-10 — Path-based agent loading wired

**Scope:** `core/orchestrator.py::_build_state_from_config`

**What changed:** Added a branch that routes `agent_payload_path` and
inline `agent_payload` participant configs through the existing
`load_agent_from_json()` function in `core/participant_agent.py`. The
legacy inline path (`id` / `name` / `profile_summary`) is unchanged.

**Why:** The Twin-2K-500 integration (see 2026-06-10 ETL entry below)
produced 2,058 agent JSON files conforming to ARCHITECTURE.md
Appendix B. Before this change, those files could not be loaded
into a session because `_build_state_from_config` did not call the
existing `load_agent_from_json()`. Sessions had to inline a
hand-condensed `profile_summary`, which meant the rich
`simulation_config.notes` field (Layer 4 of the participant prompt)
was never used.

**Verification:**
- `examples/twin2k500_smoke.json` (legacy inline path) re-ran cleanly;
  transcript equivalent to prior reference run.
- `examples/twin2k500_smoke_v2.json` (new path-based) ran cleanly;
  `agent_payload` populated; `notes` field text present in the
  participant system prompt logged in `api_calls.jsonl`; participant
  utterance in-character.

**Schema/model change:** None. `ParticipantState.agent_payload` was
already defined (ARCHITECTURE.md Section 4.3). This change activates
the dormant code path that consumes it.

**Reversibility:** Revert `_build_state_from_config` to the prior
state. The legacy inline branch is untouched and continues to work
without any other change.

---

## 2026-06-10 — Twin-2K-500 ETL integrated (initial)

**Scope:** Additive — new directories `data/twin2k500/`, `agents/twin2k500/`,
`scripts/twin2k500_*`, and one new example file. No modifications to `core/`,
`prompts/`, or existing examples.

**What changed:** Added an ETL pipeline that downloads the Hugging Face
dataset `LLM-Digital-Twin/Twin-2K-500` and transforms each of 2,058
participants into an agent JSON conforming to ARCHITECTURE.md Appendix B.
Produced agents are written to `agents/twin2k500/`.

**Verification:**
- ETL produced 2,058 files, 0 skipped.
- `scripts/twin2k500_validate.py` exited 0 (all files schema-conformant).
- Smoke test `examples/twin2k500_smoke.json` ran end-to-end through
  unchanged `core/`, producing a coherent in-character utterance from
  `Participant_574`.

**Known limitations:**
- Structured `psychological_profile` block left empty: Twin-2K-500's
  Big Five questions are Matrix-type returning arrays; the current ETL
  consumes single-value answers only. Rich persona content reaches the
  model via `simulation_config.notes` (Layer 4) instead. Documented in
  `scripts/twin2k500_mapping.yaml` comments.
- `region`, `gender`, `age` confirmed mapped. `urbanicity` not yet
  mapped (no matching QID in the dataset).
