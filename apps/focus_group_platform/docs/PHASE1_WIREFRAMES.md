# Phase 1 — Wireframes

**Status: SPECIFICATION.** Low-fidelity, structural. They fix information hierarchy
and gating, not visual design. Streamlit's own components supply the look; what
matters here is what appears, in what order, and what is blocked.

Conventions: `[button]` · `(•) radio` · `[x] checkbox` · `▸` collapsible ·
`⛔` blocked/disabled with a stated reason · `⚠` warning · `▣` status badge.

---

## 1. Projects

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Projects                                          [+ New project]          │
├────────────────────────────────────────────────────────────────────────────┤
│ ⚠ Demo mode is ON — fabricated data, no API calls.        [Configuration]  │
├────────────────────────────────────────────────────────────────────────────┤
│ Name              Created      Profiles  Guides  Runs  Evals  Last activity│
│ ─────────────────────────────────────────────────────────────────────────  │
│ Macho Meals (RO)  2026-08-04   44        1       30    2      2 min ago     │
│    read-only external corpus · nothing is written to it                     │
│    [Open]  [Export bundle]                                                  │
│ Pilot study       2026-08-02   12        2       6     1      yesterday     │
│    [Open]  [Duplicate settings]  [Export bundle]  [Delete…]                 │
├────────────────────────────────────────────────────────────────────────────┤
│ ▸ Trash (2)   restore or delete permanently                                 │
└────────────────────────────────────────────────────────────────────────────┘
```

Delete opens a dialog requiring the project name to be typed, and states that the
project moves to `trash/` and can be restored.

---

## 2. Generate focus groups

Four gated steps. A step is reachable only when the previous one validates; the
reason for a block is always shown next to the disabled control.

### Step A — Define the study

```
┌ A. Study ──────────────────────────────────────────────────────────────────┐
│ Study name        [________________]  Description [__________________]      │
│ Research objective          [__________________________________________]    │
│ Topic domain                [__________________________________________]    │
│ Participant collective id   [__________________________________________]    │
│ Moderator knowledge brief   [__________________________________________]    │
│ Researcher notes (optional) [__________________________________________]    │
│                                                                             │
│ Participant model [claude-haiku-4-5 ▾]   Moderator model [claude-sonnet-4-6▾]│
│ Temperature [1.0]   Participant max tokens [800]   Participation [orchestr.▾]│
│ ▸ Advanced (episodic depth, moderator context mode, restraint, reflection)   │
│    each control shows the architecture's own description, unedited           │
│                                                                             │
│ Focus groups [5]   Replicates per group [3]   Max turns [90]                │
│ Condition labels  [enriched] [demographics-only] [+ add]                     │
│                                                                             │
│ ℹ Replicates are independent executions. The provider API exposes no seed;   │
│   two runs of the same configuration will differ. Replicate labels r1…r3     │
│   identify runs; they do not reproduce them.                                 │
│                                                                             │
│ Output → workspace/pilot_study/runs/   (fixed)                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step B — Participants

```
┌ B. Participants ───────────────────────────────────────────────────────────┐
│ Source:  (•) Upload profiles   ( ) Repository populations   ( ) Twin2K      │
│                                                                             │
│ [ Drop JSON files ]      CSV and YAML: not in this version — a table cannot │
│                          express field provenance, and the application must │
│                          not invent it.                                     │
│                                                                             │
│ Twin2K: ⛔ agents/twin2k500/ not found in this checkout.                     │
│    To enable: pip install -r requirements-twin2k500.txt                     │
│               py scripts/twin2k500_etl.py                                   │
│    Contract and integration are specified; wiring is post-MVP.              │
├─ Validation ───────────────────────────────────────────────────────────────┤
│ ▣ schema ok 44/44   ▣ unique ids ok   ▣ accepted by architecture 44/44      │
│ ⚠ missing optional: psychometric_scores (12 profiles)   [show list]         │
│ ⚠ personal data: 2 findings                              [review]           │
├─ Field provenance ─────────────────────────────────────────────────────────┤
│ agent_id     field                          provenance      value           │
│ mm_fg1_amir  persona.demographics.age       from_file       20              │
│ mm_fg1_amir  …location.country              transformed     derived from    │
│                                                             region          │
│ mm_fg1_amir  psychometric_scores            undefined       —               │
│              ↑ never filled in. Stays undefined through to the run manifest.│
├─ Enriched vs demographics-only diff ───────────────────────────────────────┤
│ present in enriched only: persona.food_consumption, psychometric_scores     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step C — Guide

```
┌ C. Discussion guide ───────────────────────────────────────────────────────┐
│ ( ) Upload YAML   ( ) Build with the form   ( ) Reuse a project guide       │
│ [ guide.yaml ]                              [Download validated YAML]       │
├─ Validation ───────────────────────────────────────────────────────────────┤
│ ▣ 7 sections   ▣ phases map to SectionPhase   ⚠ section 4: no probes        │
│ ⛔ section 2: phase "introductory" is not a SectionPhase value.             │
│    Krueger-format mapping: introductory → context. Fix in the YAML.         │
├─ Compilation ──────────────────────────────────────────────────────────────┤
│ [Compile to discussion_guide JSON]                                          │
│ source YAML   sha256 3f9c…a12   compiler v1.0.0                             │
│ compiled JSON sha256 88b1…4de   compiled 2026-08-04 10:22 UTC               │
│ ▣ correspondence ok — recompiling reproduces the same hash                  │
├─ Preview ──────────────────────────────────────────────────────────────────┤
│ ▸ 0 · intro · "Welcome. Before we start…"                                   │
│ ▸ 1 · context · "What's your favourite place…"   probes(2) transitions(1)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step D — Run

```
┌ D. Run ────────────────────────────────────────────────────────────────────┐
│ Plan: 2 conditions × 5 groups × 3 replicates = 30 independent runs          │
│                                                                             │
│ ┌ Cost consent ───────────────────────────────────────────────────────────┐│
│ │ Estimated calls ~2,400   est. input ~3.9M tok   est. output ~0.5M tok    ││
│ │ Pricing table 2026-08-04.1                        Estimate: USD 6.40     ││
│ │ This is an estimate computed from a local rate table, not a quotation.   ││
│ │ [x] I understand this will make paid API calls        [Start 30 runs]    ││
│ └─────────────────────────────────────────────────────────────────────────┘│
├─ Live ─────────────────────────────────────────────────────────────────────┤
│ session                     cond   fg   rep  status    turns  elapsed  tok │
│ pilot__enriched__fg1__r1    enr    fg1  r1   running   18/~   04:12    62k │
│      active: participant mm_fg1_amir                                        │
│ pilot__enriched__fg1__r2    enr    fg1  r2   completed 46     11:03   151k │
│ pilot__enriched__fg1__r3    enr    fg1  r3   ⚠ orphaned 22    —       71k  │
│      process no longer alive; artefacts retained  [inspect] [mark failed]   │
│                                                                             │
│ tokens 284k · est. cost USD 0.71 (estimate, table 2026-08-04.1)             │
│ ℹ Progress is read from the run's own artefacts. Closing this page does not │
│   stop a run; reopening restores the view.                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Evaluate transcripts

```
┌ 1 Files ───────────────────────────────────────────────────────────────────┐
│ Human transcripts  [ drop files ]    Synthetic transcripts [ drop files ]   │
│ Guide [guide.yaml ▾]  Codebook [codebook.json ▾]  Profiles [set ▾ optional] │
│ Correspondence file [optional — or map below]                               │
├ 2 Study context and comparison instructions ───────────────────────────────┤
│ [ free text …                                                            ]  │
│ ℹ Context for the reader and for your own record. It does not set metadata, │
│   does not change any denominator, and is not parsed.                       │
├ 3 Normalisation ───────────────────────────────────────────────────────────┤
│ file                 detected schema          canonical  derived fields     │
│ fg1_human.json       standardized_human       ▣ ok       —                  │
│ run01/transcript.json synthetic_session_log   ▣ ok       canonical_speaker_ │
│                                                          id, speaker_role   │
│ notes.json           generic_json             ⛔ no speaker role — Level 2  │
│                                                  unavailable for this file  │
├ 4 Comparable window ───────────────────────────────────────────────────────┤
│ raw → normalised → proposed → review → locked → benchmark                   │
│ fg1_human   locked    (frozen artefact, read as-is)                         │
│ run01       proposed  start: turn 3, offset 412                             │
│    “…so, Question 1. What's your favourite place in your city…”            │
│    rule: substantive Q1 ask inside the fused entry · confidence heuristic   │
│    [Accept]  [Adjust]  [Send to review]                                     │
│ run07       ⚠ ambiguous — two candidate starts   → review queue             │
├ 5 Matching ────────────────────────────────────────────────────────────────┤
│ file          type   cond  fg   rep  guide  human referent   status         │
│ fg1_human     human  —     fg1  —    g1     —                ▣ OK           │
│ run01         synth  enr   fg1  r1   g1     fg1_human        ▣ OK           │
│ run07         synth  ?     ?    ?    g1     —                ⚠ AMBIGUOUS    │
│ extra.json    synth  demo  fg9  r1   g1     (none)           ⚠ MISSING_REF  │
│    comparative metrics → NOT_APPLICABLE_MISSING_HUMAN_REFERENCE             │
│    independent descriptive metrics still run                                │
├────────────────────────────────────────────────────────────────────────────┤
│ ⛔ [Run benchmark]  1 row is AMBIGUOUS and 1 window awaits review.          │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Results

```
┌ Results ───────────────────────────────────────────────────────────────────┐
│ [Summary] [By focus group] [Study level] [Human vs synthetic] [Conditions]  │
├────────────────────────────────────────────────────────────────────────────┤
│ n groups = 5 · replicates kept separate · run → focus group → study replicate│
│ ⚠ no inferential test is offered at n = 5                                   │
├ Level 2 · interaction ─────────────────────────────────────────────────────┤
│ words_per_turn_median   ▣ AVAILABLE_VALIDATED                               │
│    ● human 96.0   ● enriched 141.5   ● demographics-only 138.0              │
│    (points = focus groups, small hollow = replicates)                       │
│ reference_density       ▣ REQUIRES_RESEARCHER_ADJUDICATION                  │
│    labels collapsed for 2 sessions → 1 review item                          │
│ specificity             ▣ NOT_IN_REPORTED_INSTRUMENT                      │
│    Retained in the framework and excluded prospectively: the two-coder      │
│    gold-standard human validation this metric requires was never opened.    │
│    No value is computed.                                                    │
├ Level 3 · agent fidelity (exploratory) ────────────────────────────────────┤
│ Q1 varied vocabulary? · Q2 speakers differ? · Q3 voice recognisable? ·      │
│ Q4 positions compatible?                                                    │
│ ℹ These four questions are answered separately. A high Q1 result is not     │
│   evidence for Q2 or Q3.                                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

Colours in every new figure: Human `#52525B`, Enriched `#176B87`,
Demographics-only `#D27D2D`.

---

## 5. Human review queue

```
┌ Human review queue (4 open) ───────────────────────────────────────────────┐
│ [open] [resolved] [all]                                                     │
│                                                                             │
│ ▸ WINDOW_AMBIGUOUS · run07 · opened 2026-08-04                              │
│    proposed: turn 3 offset 412 | alternative: turn 4 offset 0               │
│    “…Question 1. What's your favourite place…” / “Right, Question 1…”       │
│    decision ( ) accept proposed  ( ) accept alternative  ( ) manual         │
│    justification [__________________________]        [Record decision]      │
│                                                                             │
│ ▸ METRIC_INVALID · reference_density · fg3 enriched r2                      │
│    reference_density_valid = false; labels collapsed: ["Dave","David"]      │
│    ( ) supply label mapping   ( ) mark not applicable for this corpus       │
│                                                                             │
│ ▸ QUOTE_UNVERIFIED · tier1 · fg2 · code B.3                                 │
│ ▸ RUN_INTERRUPTED · pilot__enriched__fg1__r3 · exit code —, orphaned        │
├────────────────────────────────────────────────────────────────────────────┤
│ Every decision records who, when, what was proposed, what was chosen and    │
│ why. Nothing here is resolved by re-running the model.                      │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Exports

```
┌ Exports ───────────────────────────────────────────────────────────────────┐
│ Scope  (•) whole project  ( ) one evaluation  ( ) one figure                │
│ [x] tables CSV   [x] tables XLSX   [x] figures PNG   [x] figures SVG        │
│ [x] HTML report  [ ] PDF (post-MVP)  [ ] DOCX (post-MVP)                    │
│ [x] results JSON [x] provenance record  [x] warnings & undefined register   │
│ [x] human review list                                                       │
│                                                                             │
│ Every export embeds: application version, code content hash, metric         │
│ registry hash, schema versions, pricing table version, denominators,        │
│ exclusions, statuses. No API key is ever written.                           │
│                                        [Build export]                       │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Configuration and provenance

```
┌ Configuration and provenance ──────────────────────────────────────────────┐
│ Demo mode  [x] on — no external API call is possible                        │
│ API keys   ANTHROPIC_API_KEY  sk-…a91f (from environment)                   │
│            GEMINI_API_KEY_NEXT  not set                                     │
│            Keys are read from the environment only and are never written    │
│            to project files, logs or exports.                               │
├ Versions ──────────────────────────────────────────────────────────────────┤
│ application_version        0.1.0                                            │
│ code content hash          cch:9f21c4e0a7b3d158                             │
│    (no git repository present — this is a content hash, not a commit)       │
│ metric_registry_hash       sha256 c41d…                                     │
│ guide_compiler_version     1.0.0                                            │
│ pricing_table_version      2026-08-04.1  effective 2026-08-04               │
│ profile_schema_version     1.0.0   transcript_schema_version 1.0.0          │
├ Pricing table ─────────────────────────────────────────────────────────────┤
│ model                    mode      in $/Mtok   out $/Mtok                   │
│ claude-haiku-4-5         batch     0.50        2.50                         │
│ claude-opus-5            batch     2.50        12.50                        │
│ ⚠ a model missing from this table yields an undefined cost, never zero      │
├ Storage ───────────────────────────────────────────────────────────────────┤
│ workspace/  412 MB   uploads 88 · derived 140 · cache 31 · exports 12       │
│ Frozen paths (read-only, guarded): core/ agents/ configs/ prompts/          │
│ output/session_logs/ data/datasets_transcripts/standardized/ analysis/      │
└────────────────────────────────────────────────────────────────────────────┘
```


---

# AMENDMENT 1 - Phase 1 conditional approval (2026-08-04)

The decisions below **supersede** the text above where they conflict. Superseded text
is left in place so the review history stays legible.

## A1.1 Projects screen - no Macho Meals row

The "Macho Meals (RO)" row in section 1 is **removed**. The acceptance corpus is not a
project. Under `FOCUS_GROUP_PLATFORM_DEV_REFERENCE=1` a separate, clearly labelled
panel appears below the project list:

```
+- Developer reference (read-only, not a project) ---------------------------+
| Macho Meals acceptance corpus - 5 human - 30 synthetic - frozen manifest    |
| Visible because FOCUS_GROUP_PLATFORM_DEV_REFERENCE=1. Not copied, not       |
| exported, not distributed.                                     [Inspect]    |
+----------------------------------------------------------------------------+
```

## A1.2 Participants step - YAML accepted, model note corrected

```
| [ Drop JSON or YAML files ]   Same nested schema, same validation.          |
| CSV: not in this version - a flat table cannot carry per-field provenance   |
| without a column-mapping layer.                                             |
```

The model control moves out of the study form and into the participants step:

```
| Participant model  [claude-haiku-4-5 v]                                     |
| i Read from each profile's simulation_config.model. Choosing a model here   |
|   writes a derived copy of each profile inside this project. The originals  |
|   in agents/ and uploads/ are not modified.                                 |
|                                                                             |
| Max output tokens per participant turn [800]                                |
| i A technical ceiling, not a target length. It does not ask for longer or   |
|   more uniform answers.                                                     |
```

## A1.3 Run step - destination shown before launch

```
| Destination  output/session_logs/pilot__enriched__fg1__r1                   |
| [ok] no collision   [ok] not in the frozen manifest   [ok] session_id unique|
| [BLOCKED] pilot__enriched__fg1__r2 - a directory already exists there.      |
|    Refused. The application never overwrites or resumes a run directory.    |
```

## A1.4 Configuration - data directory and frozen manifest

```
+- Data directory -----------------------------------------------------------+
| C:\Users\<user>\AppData\Local\FocusGroupPlatform                            |
| source: OS application-data directory (FOCUS_GROUP_PLATFORM_DATA_DIR unset) |
| Nothing is stored inside the repository.                                    |
+- Frozen sessions ----------------------------------------------------------+
| 47 protected paths - 30 acceptance sessions - 5 human transcript sets       |
| New runs may create new directories under output/session_logs/.             |
|                                                     [View manifest]         |
+----------------------------------------------------------------------------+
```

## A1.5 Results - figure provenance

Each figure shows a compact footer - `metric_id - status - unit/denominator` - and a
`[provenance]` link opening the sidecar JSON. The full block is not printed on the
image.


---

# AMENDMENT 2 - Phase 2A.1 hardening (2026-08-04)

Findings from an independent security review of the Phase 2A code. These supersede the
text above where they conflict; the superseded text stays so the review history is
legible.

## A2.1 Identifier errors are shown, not silently fixed

Wherever a profile or guide is uploaded, an invalid identifier renders as a blocking
row naming the file, the field and the rule:

```
| [BLOCKED] participant_3.json                                                |
|    agent_id: unsafe identifier '../../outside'. Allowed: ASCII letters,     |
|    digits, dot, underscore and hyphen; 1-128 characters. Spaces, Unicode,   |
|    separators and drive letters are refused.                                |
|    The identifier is not rewritten - fix it in the file.                    |
```

## A2.2 Overwrites are a decision, never a default

```
| [BLOCKED] mm_fg1_amir.json already exists in this project's derived         |
|    profiles. Overwriting a derived artefact is not implicit - a previous    |
|    run's provenance points at it.        [Replace]  [Write a new name]      |
```
