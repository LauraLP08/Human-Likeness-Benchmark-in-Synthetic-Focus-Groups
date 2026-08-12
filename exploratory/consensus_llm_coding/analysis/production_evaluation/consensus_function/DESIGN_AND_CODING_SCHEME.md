# CONSENSUS_FUNCTION_LLM_EXPLORATORY — coding scheme and pilot design

*Drafted 6 August 2026. Nothing has been run against the API. This document is the
object to review before the first live call; the prompt, the categories and the
configuration freeze at that call.*

**Status: `LLM_CODED_HUMAN_VALIDATION_REQUIRED`.** Not a validated measure. No number
produced by this layer may be reported as validated until a sample of it has passed
through the blind human-coder package of the wider evaluation plan.

## 0. Namespace and separation from existing measures

This is a **new, separate layer**. It is not Tier 1, Tier 2 or Tier 2B, and it is not
part of `CONSENSUS_DYNAMICS_EXPLORATORY`.

| Layer | Unit | Method | Relation to this one |
|---|---|---|---|
| Tier 1 / Tier 2 / Tier 2B | theme | LLM extraction + matching | **No overlap.** No theme is extracted or matched here. |
| `CONSENSUS_DYNAMICS_EXPLORATORY` | response act (P→P) | frozen lexicon, deterministic, **zero API calls** | Same construct family, different method. See §1. |
| `CONSENSUS_FUNCTION_LLM_EXPLORATORY` (this) | participant turn | LLM multi-label classification | — |

Results from this layer are **never** aggregated with, averaged into, or reported in the
same table as Tier 1/2/2B metrics.

## 1. The prior layer this must be reconciled with, not silently duplicated

`analysis/production_evaluation/consensus_dynamics/FROZEN_SPEC.md` states, as a design
commitment: *"Ningún juez LLM en el núcleo. Cero llamadas a API"* — markers are counted,
stance is never classified, because a marker count is auditable line by line.

This new layer deliberately crosses that line. That is defensible only if it is declared,
so it is declared here: **this layer introduces the LLM stance judgement the prior layer
refused to make, and therefore inherits a validation burden the prior layer did not have.**
Hence the `LLM_CODED_HUMAN_VALIDATION_REQUIRED` flag, which is not a formality.

Three findings from that prior layer are load-bearing for the design below, and all three
argue *for* running this:

1. **The single-label assumption already failed in the field.** The N1 human coder's memo
   (`N1_triage/N1_FINDINGS.md` §4) records, unprompted: *"Hay turnos sintéticos difíciles de
   entender porque a veces buscan ver en un mismo turno el lado de todo… Los humanos abordan
   menos puntos a la vez y con posiciones más claras."* The report concludes that the ternary
   label "presupone que un turno tiene *una* postura frente al turno previo" and that this
   presupposition fails. Multi-label is the documented fix, not a new idea.

2. **A prior of what "mixed" should look like already exists.** Turns carrying both an
   agreement and a disagreement *marker*: **0.3% human vs 2.4% synthetic (8×)**; turns with
   ≥2 internal contrastive markers: **0.3% human vs 9.8% synthetic (31×)**. If the LLM's
   mixed-rate lands wildly outside this neighbourhood, that is a signal about the coder, not
   a discovery. This is a built-in sanity check the pilot gets for free.

3. **Length confounding has already destroyed one version of this measurement.** The
   whole-turn variant of the lexical detector produced 33.7% synthetic vs 5.0% human
   divergence; inspection showed the gap was carried by mid-turn constructions, and mean
   clauses per act is **6.4 human vs 24.0 synthetic (3.75×)**. Any per-turn rate gives the
   long side ~4× the opportunity to trigger. §6 addresses this directly; ignoring it would
   reproduce a known artefact.

**Consequence to be explicit about:** if this layer finds "more disagreement in synthetic",
that is *the same direction* the lexical detector already found and that N1 already failed to
overturn. It would be corroboration under a different method, not an independent discovery,
and must be written up as such.

## 2. Evaluator: exact identifier and configuration

**Requested:** "Gemini 3.5 Flash, temperature 0."
**Confirmed identifier: `gemini-3.5-flash`** — `scripts/thematic_coding.py:75`,
`EVALUATOR_CONFIGS["gemininext"]`, key env `GEMINI_API_KEY_NEXT`. This is the project's
canonical production evaluator (`production_eval_pipeline.REQUIRED_MODEL`, line 67), and
`gemini-2.5-flash` is **DISQUALIFIED** in this project (81.8% Gate-1 agreement against an
85% threshold) and is still the silent default of `thematic_coding._MODEL`.

### 2.1 Configuration differences vs how `gemini-2.5-flash` is used — read this

The configuration does **not** simply inherit. Four differences, one of them material to the
request as stated:

| Parameter | `gemini-2.5-flash` (as used) | `gemini-3.5-flash` (as used) | Note |
|---|---|---|---|
| `temperature` | `0.0`, **transmitted** | `None`, **NOT transmitted** | **Blocks "temperature 0".** |
| `thinking_config` | `{thinking_budget: 0}`, transmitted | **not transmitted** | `"thinking_level": "medium"` in the config is a **logging label only** |
| `max_output_tokens` | 32768 default / 16384 in production | same | this layer will use **16384** |
| `safety_settings` | never set | never set | **API defaults**, not pinned — verified: no `safety_settings` / `HarmCategory` anywhere in the repo |

**`temperature=0` is not achievable on this model in this project.**
`EVALUATOR_CONFIGS["gemininext"]["temperature"] = None` with the comment *"not supported —
omitted from request"*, and `thematic_coding.py:566-568` only adds the key when the value is
not `None`. `effective_request_config()` records this as
`temperature_transmitted: false`, and that flag is part of the cache key, so a cached
result can never claim a temperature that was not sent.

Two consequences, both of which need your decision (§9, D1):

* **Determinism is not guaranteed.** With temperature unset *and* thinking level unpinned
  (`thinking_level_effective: "model_default_unpinned"`), repeated identical requests may
  differ. Every other LLM-coded result in this project is under the same regime, so this is
  not a new weakness — but a per-turn classification is more exposed to it than a
  transcript-level extraction, because a single sampled token can flip a label.
* The cache therefore **freezes the first answer**; it does not demonstrate reproducibility.
  Reproducibility needs the probe in §9, D1.

### 2.2 What this layer transmits (frozen at first live call)

```
model               = "gemini-3.5-flash"
response_mime_type  = "application/json"
max_output_tokens   = 16384
temperature         = (omitted)
thinking_config     = (omitted)
safety_settings     = (omitted — API defaults)
execution_mode      = "synchronous"
```

This is a **new call site**, not a Tier-1 call. It has its own generation config and its own
prompt, and `effective_request_config()` is re-implemented locally over *this* call's config
rather than imported from the Tier-1 path — importing it would report Tier 1's transmitted
keys for a request that does not make them.

## 3. Unit of coding — recommendation

Three options were considered.

**(A) Whole turn, one label set.** Simple; one row per turn; trivially verifiable. Loses the
location of each function inside the turn — with a mean of 24 clauses per synthetic turn, a
label set `{agreement, disagreement}` on a 230-word turn tells you almost nothing about where
or how.

**(B) Segment into clauses, label each clause.** Maximum granularity. Rejected, and the reason
is not fragility in the abstract — it is **asymmetric** fragility: segmentation is itself a
coding decision, and synthetic turns carry 3.75× more clauses than human turns. Segmentation
error would therefore be systematically larger on one side of the very comparison being made,
which is precisely the failure mode that invalidated the whole-turn lexical variant. A
segmenter would need its own reliability study before any of its output could be used.

**(C) RECOMMENDED — turn is the unit of record; every label is anchored to a verbatim span.**
One row per turn per label. The turn carries a *set* of labels. Each label must carry an
`evidence_quote` that is an exact substring of that turn's text, plus, for relational labels,
the `target_turn_id` it is oriented to.

This is option A's verifiability with most of option B's granularity: the evidence quote *is*
the segment, but it is a segment the model had to find and that a machine can check by
substring match, rather than one imposed by a segmenter whose errors are unbalanced. Quote
spans additionally give the human validator in §8 an exact locus to agree or disagree with,
which a bare label does not.

**Trade-off accepted:** span boundaries are not themselves validated, and two functions
carried by one clause may be anchored to overlapping quotes. Both are acceptable because no
metric below depends on span boundaries — spans are evidence, counts are over labels.

## 4. Categories — operational definitions

Four labels. **Any combination may co-occur on one turn**, including all four. There is no
"exclusive" constraint anywhere in the schema.

Every relational label (`agreement`, `disagreement`, `challenge`) requires a **target**: a
position attributable to *another speaker in the preceding context*. A turn that agrees with
itself, or asserts a position with no prior referent, is not relational.

---

**`agreement`** — endorses, affirms, ratifies or aligns with a position attributable to
another speaker in the preceding context.

*Includes:* explicit endorsement ("yeah, exactly that"); restating another's point approvingly;
extending another's point as correct ("and that's why it's the default for us too").
*Excludes:* mere acknowledgement of having heard ("right", "mm"); politeness with no stance;
agreeing with the moderator's *question* rather than a participant's *position*.

> "Yeah, David's right about the pub thing, it is just where you end up."

---

**`disagreement`** — rejects, contradicts, denies or asserts a counter-position to a position
attributable to another speaker.

*Includes:* direct contradiction; asserting the opposite; denying the applicability of
another's claim; "that's not really it, it's more…".
*Excludes:* disagreeing with a factual detail while endorsing the position (that is
`agreement` + a scoped `disagreement` only if the counter-claim is itself a position);
disagreement with an absent third party or with society at large.

> "I don't think that's it at all — for us it's got nothing to do with money."

---

**`challenge`** — questions, probes, or asks for justification of another speaker's position
**without committing to a counter-position**.

This is the category that most needs its boundary stated, because it is what `disagreement`
collapses into when a coder is careless. The test is: **does the speaker assert something
that could be false?** If yes → `disagreement`. If the speaker only opens the prior position
to question → `challenge`.

*Includes:* "but is that actually true for everyone though?"; "how would that work if you've
got kids?"; requesting evidence or scope limits.
*Excludes:* rhetorical questions that assert a counter-position ("but who can actually afford
that?" asserts that people cannot → `disagreement`); questions directed at the moderator.

> "Yeah but does that hold if you're not drinking though?"

---

**`neutral_elaboration`** — contributes substantive content — own experience, description,
reasoning, example — **without positioning toward another speaker's position**.

*Includes:* answering the moderator's question first-hand; narrating own practice; adding a
new consideration not framed as for/against anyone.
*Excludes:* anything that endorses or contests a prior speaker (those are the labels above);
purely procedural talk (see below).

> "For me it's usually the pub. There's a few we go to round Birmingham, nothing fancy."

---

**No label applicable** — recorded as an empty label set with a required `no_code_reason`
from a closed list: `procedural` (turn-taking, "sorry, you go"), `unintelligible`,
`off_topic`, `moderator_directed_only` (the turn engages only the moderator's question
mechanics), `other` (free text required).

This is a **recorded outcome, not a residual**: an empty label set with no reason is a schema
violation and fails validation.

### 4.1 `mixed` is derived, never assigned

There is **no `mixed` label in the schema.** `mixed` is computed:

```
mixed  ≔  agreement ∈ labels  AND  disagreement ∈ labels
```

Reason: giving the coder a `mixed` bucket makes it compete with its own components — a coder
that reaches for `mixed` stops recording *which* clause agreed and *which* disagreed, and the
evidence anchoring collapses. Deriving it guarantees that every `mixed` turn carries two
separate, separately-verifiable quotes.

Secondary derived patterns, all computed not assigned:

| Derived | Definition | What it is evidence of |
|---|---|---|
| `mixed` | agreement ∧ disagreement | multi-position turn |
| `agreement_only` | agreement ∧ ¬disagreement ∧ ¬challenge | — |
| `disagreement_only` | disagreement ∧ ¬agreement ∧ ¬challenge | — |
| `contested` | disagreement ∨ challenge | any non-endorsing orientation |
| `relational` | agreement ∨ disagreement ∨ challenge | turn is oriented to another speaker at all |
| `label_count` | \|labels\| | turn-level functional density |

## 5. Evidence anchoring — same discipline as Tier 1 / Tier 2

Every label object must carry:

* `evidence_quote` — **an exact substring of the blinded turn text**, ≥ 3 words. Verified
  programmatically after the call: `quote in blinded_turn_text`. Not fuzzy-matched, not
  normalised, not lower-cased.
* `target_turn_id` — required for `agreement` / `disagreement` / `challenge`; must be a
  turn id that was actually present in that chunk's context. Must be **null** for
  `neutral_elaboration`.

Failure handling, and this is the part that matters:

| Failure | Handling |
|---|---|
| Quote is not a substring | Label marked `EVIDENCE_FAIL`, **excluded from the primary table, written to a separate file, counted in the report.** Never silently dropped. |
| Quote matches only after typographic normalisation | Marked `ok_normalized_punctuation`, **counted separately from strict `ok`**. See §5.1. |
| `target_turn_id` not in context | Label marked `TARGET_FAIL`, same treatment. |
| Empty label set with no reason | Chunk marked `SCHEMA_FAIL`, re-requested once, then recorded as failed. |

**The evidence-failure rate is a reported primary result**, not a diagnostic. A coder whose
quotes do not verify has not produced labels that mean anything, and the pilot must be able
to conclude exactly that.

### 5.1 Why the verifier records two verdicts — a real hazard found in the dry run

The blinded FG1 corpus contains **820 em dashes, every single one on the synthetic side**:
1.39 / 1.28 / 1.46 per 100 participant words in the three enriched runs, 1.11 / 0.95 / 0.99
in the three demographics-only runs, and **0.00 in the human transcript**.

A coder copying a quote will often render `a — b` as `a - b`. Under a strict substring check
that fails — and it can only fail **on the synthetic side, because only the synthetic side
has em dashes**. A transcription habit would become an asymmetric measurement artefact, with
the failure rate inflated for exactly the conditions under test. That is the same class of
error that invalidated the whole-turn lexical variant in the prior layer.

The corpus is **not** rewritten to fix this. Instead the verifier records both verdicts:
strict substring is primary (`ok`); a quote matching only after a symmetric typographic
normalisation (em/en dash → hyphen, curly → straight quotes, whitespace collapse) is recorded
as `ok_normalized_punctuation` and **counted separately**. Nothing is fuzzy-matched silently,
and both counts appear in the report. Target validation still applies to normalised matches.

## 6. Blinding, and its honest limits

The evaluator receives, per chunk, only:

```
[T07] Speaker C: <text>
[T08] Speaker A: <text>          ← TO CODE
```

Removed: `timestamp`, `selection_mode`, `source_file`, `page`, `paragraph_indices`,
`source_type`, `standardization_confidence`, `speaker_role`, every provenance field. Speaker
names are mapped to `Speaker A…E` by order of first appearance, and the same mapping is
applied to occurrences of those names **inside** turn text (substitutions counted and logged,
so the mapping is auditable). The blinded text is what is hashed, what is sent, and what
quotes are verified against.

The prompt never mentions humans, AI, synthesis, conditions, or that transcripts differ in
origin. It refers only to "a group discussion".

**Residual leakage that cannot be removed, and must not be claimed away.** FG1 participant
turns average **48 words (human)** vs **228 (enriched run01)** — a 4.7× ratio. Register and
length are perceptible to the evaluator in every chunk. **Blinding here is procedural (no
labels, no metadata), not perceptual.** Any claim of the form "the evaluator could not tell"
is unsupportable and will not be made. What blinding buys is that the evaluator is not *told*,
and that it cannot key on an artefact of file format — which is a real but limited guarantee.

Measured in the dry run, the second hard tell is punctuation: **em dashes are 100% diagnostic
of condition in FG1** (§5.1) — 0.00 per 100 words human, 0.95–1.46 across all six synthetic
runs. One em dash identifies the side.

**Normalising punctuation away is deliberately *not* proposed as a blinding fix.** It would
remove one tell while length (48 vs 229 words per turn) still identifies the side in every
chunk, so it would buy false reassurance rather than blindness. Punctuation normalisation is
used only where it addresses a real measurement hazard — quote verification (§5.1) — and not
as a claim about what the evaluator can perceive.

This is the same limit the rest of the project's blind coding operates under; it is stated
here rather than assumed. **It applies to Tier 1 / Tier 2 / Tier 2B blind coding too**, which
send the same corpus with the same em-dash asymmetry; that is worth a separate look and is
not something this layer can fix.

### 6.1 Length confounding — mandatory reporting rule

Because opportunity scales with turn length, **no per-turn rate is reported alone.** Every
table carries, alongside the per-turn percentage:

* mean words and mean clauses per participant turn, per condition;
* labels per 100 clauses (the normalisation that the prior layer found decisive: it turned an
  uninterpretable 21× raw ratio into an interpretable 5.2× per-clause ratio);
* a **length-matched sensitivity**: the same coding over turns truncated to the median human
  participant turn length for that FG, run only if the primary result shows a condition gap.

## 7. Pilot design

**FG: FG1**, as requested, for consistency with the rest of the work. One qualification: FG1's
human side is on the sparse end of the corpus (58 participant turns, 2,788 participant words —
FG3 has 98/7,531 and FG5 has 123/6,408). Rare labels will have wide bands on the human side.
FG1 is the right *pilot* (it exercises the whole machine at low cost); it is not the FG that
will best estimate a rate. Recommendation: keep FG1, and do not read small human-side
percentages as estimates.

**Cells — the full canonical 3×3 for FG1, 7 transcripts:**

| Condition | Runs | Participant turns |
|---|---|---|
| human | `standardized/macho_meals/fg1` | 58 |
| enriched | `fg1_run01`, `fg1_run02`, `fg1_run03` | 37, 32, 34 |
| demographics-only | `fg1_demoonly_run01/02/03` | 51, 35, 39 |
| | **total** | **286** |

All three replicates per condition are included rather than one: picking a single run would be
arbitrary and would hide between-run variance, which at n=1 FG is the only variance visible.
Per-run figures are reported alongside the condition aggregate.

**Sources are read-only and whitelist-only.** Inputs are exactly the paths recorded in
`analysis/production_evaluation/frozen_evaluator_inputs.json` (5 human + 30 synthetic).
`output/session_logs/` is never read or written. No generation, no regeneration.

**On `macho_meals_fg5_run02` — a correction to the premise.** You asked what I would do about
the missing cell if the pilot later reaches FG5. **There is no missing cell.** The whitelist
is a complete balanced 3×3 grid: FG5's enriched replicates are `run01` (index 1), `run03`
(index 2) and `run04` (index 3). `fg5_run02` (`ARCHIVED_LOST_REFLECTION_CYCLE`) was excluded
pre-analytically and **backfilled by `run04`**; the same is true of `fg4_run02`
(`ARCHIVED_TECHNICAL_OUTLIER`), backfilled by `fg4_run04`. So extending to FG5 needs no
special handling and no imputation — it needs only that the archived run is never read, which
the whitelist enforces by construction.

**Chunking.** Turns are coded in windows of 12 target turns, each preceded by 3 context turns
(context is coded in no window but is visible for target attribution). Context is the 3
immediately preceding turns in transcript order, of any speaker. Guide-section-aware context
was considered and deferred: `tier2b_segmentation` boundaries are derived differently on the
two sides (human `Question N` headers vs moderator log), and adjacency is the local relation
the construct needs. Chunk boundaries are recorded so that a turn's context can be audited.

**Estimated cost: 27 calls** for the whole pilot (5+4+3+3+5+3+4). No batch mode; synchronous,
cached per chunk.

**Cache key** = SHA-256 over `{blinded_transcript_sha256, chunk_index, chunk_turn_ids,
prompt_sha256, canonical_model_config}`, where `canonical_model_config` is the sorted-key
serialisation of what is *actually transmitted* (§2.2), following the pattern in
`production_eval_pipeline.canonical_model_config`. Results are written once per key and never
overwritten.

**Frozen at first live call:** prompt text, category definitions, chunk size, context depth,
speaker-masking rule, generation config. Any later edit invalidates the hash and forces a
re-declaration, exactly as in `FROZEN_SPEC.md`.

## 8. Outputs

**(1) Long-format, one row per turn per label** — `codings_long.csv`:

`fg, condition, run, transcript_sha256, turn_id, speaker_masked, is_participant,
prev_speaker_is_participant, n_words, n_clauses, label, evidence_quote, target_turn_id,
evidence_verified, chunk_index`

Turns with no applicable label appear as a single row with `label = NONE` and the reason, so
the file's turn universe is complete and the denominator is recoverable from the file itself.

**(2) Aggregate by condition** — `summary_by_condition.csv` / `.md`:

`agreement_only, disagreement_only, mixed, challenge, neutral_elaboration, no_code`, each with
an **explicit numerator and denominator printed in the table**, plus the length columns
required by §6.1 and the evidence-failure rate.

**Denominator: participant turns only.** Moderator turns are excluded, and the count of
excluded moderator turns is printed beside every table. Reason: in the synthetic conditions
the moderator is a separate LLM agent driving a scripted guide, so its consensus behaviour is
a property of the moderator implementation, not of the simulated population under study —
mixing it in would let a moderator design choice move a participant-level metric. The human
side would in any case contribute only 6 moderator turns against the synthetic side's 15–22,
so including them would also be structurally unbalanced. Moderator turns remain visible to the
coder as context; they are simply never coded.

Note that the label percentages **do not sum to 100** by design — a turn with three labels
appears in three cells. Every table states its denominator and whether cells are exclusive.

**(3) Descriptive comparison** for FG1: human vs enriched, human vs demographics-only.
Descriptive only — no significance testing, no confidence intervals presented as inference.
n = 1 focus group.

### 8.1 Composite "consensus level" score — NOT built, proposal only

No composite is computed in the pilot. Recording why, and what the candidates would be:

* **`agreement% − disagreement%` — recommended against.** It treats `challenge` as zero
  (a challenge is not neutral), it treats a `mixed` turn as cancelling to zero (a turn that
  does both is not equivalent to a turn that does neither), and both components scale with
  turn length, so the difference inherits the length confound of both.
* **`mixed%` — propose reporting as *complexity*, on its own axis.** A high mixed rate says
  turns carry multiple positions. That is neither consensus nor dissent, and the N1 memo is
  the direct evidence for reading it this way. It should never be summed with the others.
* **`relational%` = (agreement ∨ disagreement ∨ challenge) / participant turns** — the one
  candidate worth considering later. It is valence-free: it measures how much talk is oriented
  to other speakers at all, versus parallel monologue. It is still length-sensitive and would
  need the per-clause normalisation of §6.1.

**Recommendation: report the profile of six proportions, plus `mixed%` explicitly labelled as
complexity, and no scalar.** If you want a scalar, `relational%` is the one I would build, and
I would want your decision before building it.

## 9. Open decisions for you

**D1 — determinism.** `temperature=0` cannot be sent (§2.1). Options: (a) proceed as the rest
of the pipeline does, accepting unpinned sampling, and add a **repeatability probe** — re-code
one 12-turn chunk three times under a cache-bypass flag and report label agreement (**+3
calls**); (b) proceed with no probe; (c) pin thinking level via
`types.ThinkingConfig(thinking_level=MEDIUM)`, which the SDK supports (google-genai 2.10.0,
per `frozen_evaluator_inputs.json`) but which **no other measure in this project transmits** —
it would make this layer's configuration non-comparable to every other LLM-coded result.
**Recommended: (a).** 30 calls total.

**D2 — human validation route.** N1 already has a sealed, stratified, name-masked sample of
80 units with an existing `unit_map_SEALED.json`, of which 42 were coded by one coder. Reusing
that frame for this layer's human validation would give partial comparability with the lexical
detector at low cost. But N1's sample is stratified on the *lexical* label, which would bias a
multi-label validation toward marker-bearing turns. **Recommended: draw a fresh sample
stratified on this layer's derived patterns (over-sampling `mixed`, which is rare), and code a
small overlap with N1's units for cross-walk.** Decide when the pilot's rates are known.

**D3 — scope confirmation.** Pilot is FG1 only, 27 (or 30) calls. The other four FGs are not
run until you have reviewed this document and the pilot output.

**D4 — the em-dash finding beyond this layer.** §6 records that em dashes separate the
conditions perfectly in FG1 and that this affects every blind LLM-coded measure in the
project, not only this one. This layer handles the measurement hazard it creates; it does not
and cannot address what it means for Tier 1 / Tier 2 / Tier 2B blinding claims. Flagging it
for you rather than acting on it — touching those layers is out of scope here.

## 10. Status line for any downstream document

> Consensus function coding (`CONSENSUS_FUNCTION_LLM_EXPLORATORY`) is
> **`LLM_CODED_HUMAN_VALIDATION_REQUIRED`**. Labels are produced by `gemini-3.5-flash` under a
> frozen prompt, with per-label verbatim evidence verified by substring match, and are **not**
> human-validated. They are reported separately from Tier 1, Tier 2 and Tier 2B, and are not
> combined with `CONSENSUS_DYNAMICS_EXPLORATORY` lexical results. No composite consensus score
> is defined.
