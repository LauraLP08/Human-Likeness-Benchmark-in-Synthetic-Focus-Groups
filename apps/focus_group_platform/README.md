# Synthetic focus group platform

**This document is for the researcher using the tool.** Everything else in `docs/` is
written for auditors and engineers; if you are here to run a study, you only need this
page.

---

## 1. What this tool does, and what it does not

It generates synthetic focus groups with LLM participants, and it computes
**structural** measures over transcripts — human or synthetic — so you can ask whether
a synthetic discussion behaves like a real one.

**What you get for your own corpus, today:**

| Measure | What it is |
|---|---|
| Words per turn (and its distribution) | How long interventions are |
| Participation share, Gini | How evenly people speak |
| Moderator share | How much of the discussion is the moderator |
| Adjacency, chain depth | Whether participants respond to each other or only to the moderator |
| Turn counts, session length | Producer counts, labelled as such |

**What you do NOT get for your own corpus, today:** thematic fidelity — subtheme
recall, precision, F1, participant reach. Those exist in this tool **only for the
frozen Macho Meals benchmark**, where a validated codebook and a completed coding
procedure already exist. For your study they would need a codebook and a coding
procedure of your own, and that layer is not built. The interface will tell you this
where it applies; this page says it once, plainly, so you know before you start.

If your research question is *"do synthetic groups reproduce the themes my humans
raised?"*, this tool cannot answer it for your data yet. If it is *"do synthetic groups
reproduce the interactional structure?"*, it can.

---

## 2. Running it

```bash
py -m streamlit run app/streamlit_app.py
```

Dependencies: `pip install -r requirements.txt` (Streamlit, pandas, altair, PyYAML,
psutil). Your projects are stored **outside this repository**, under your user
application-data directory — the Home screen shows the exact path.

**One screen spends money.** *Generate focus groups* launches real sessions against a
paid provider. Every other screen only reads files. The sidebar tells you which one
you are on.

---

## 3. The files you have to supply

The tool refuses files it cannot read rather than guessing. Here is exactly what each
one must contain.

### 3.1 A human transcript

Every turn needs six fields. `canonical_speaker_id` and `speaker_role` are required on
**human** transcripts specifically, because the tool will not infer who is a moderator
from position in the file.

```json
[
  {
    "turn": 1,
    "speaker_id": "MODERATOR",
    "speaker_name": "Moderator",
    "canonical_speaker_id": "MOD",
    "speaker_role": "moderator",
    "content": "To start, what does a normal weeknight dinner look like?"
  },
  {
    "turn": 2,
    "speaker_id": "P1",
    "speaker_name": "Alex",
    "canonical_speaker_id": "P1",
    "speaker_role": "participant",
    "content": "I keep a rotation of about five meals I can do easily."
  }
]
```

`speaker_role` is `moderator` or `participant`. `canonical_speaker_id` is the identity
you use consistently across all your transcripts — it is what lets the tool follow the
same person between sessions.

**Converting from Word.** There is no importer for `.docx`. You will need to produce
the JSON yourself — a short script, or a spreadsheet exported and reshaped. This is
real work and the tool does not currently help with it.

### 3.2 An agent payload (a synthetic participant)

```json
{
  "schema_version": "fg_agents_v1",
  "agent_id": "p_alex",
  "language": "en",
  "persona": {
    "demographics": {"name": "Alex", "age": 29, "gender": "man"},
    "background": {"work": "full time, fixed hours", "commute": "drives"}
  },
  "simulation_config": {"model": "claude-haiku-4-5-20251001", "max_tokens": 700}
}
```

Only `agent_id` and `persona.demographics.name` are required. `age`, `gender` and
everything else are optional — the architecture handles their absence.

**The one rule that matters:** `background`, `food_consumption`, `location` and
`psychometric_scores` must be **objects of labelled entries**, never plain strings.
Writing `"background": "Alex drives to work"` passes every schema check and then
crashes the session partway through, after you have already paid for the calls that
ran. The tool now refuses that shape up front — this is why.

### 3.3 A discussion guide (YAML)

```yaml
guide_id: weeknight_guide_v1
title: Weeknight cooking
sections:
  - label: Warm up
    phase: intro
    scripted_question: To start, what does a normal weeknight dinner look like?
    suggested_probes:
      - Who usually cooks?
  - label: Everyday choices
    phase: main_topic
    scripted_question: Walk me through deciding what to cook last Tuesday.
  - label: Closing
    phase: closing
    scripted_question: Is there anything we have not covered?
```

`phase` is `intro`, `main_topic` or `closing`. The number of sections drives how long a
session runs — and therefore what it costs (see below).

---

## 4. What it will cost you

The tool **will not estimate a cost before a run**, and that refusal is deliberate:
the only number available beforehand is `--max-turns`, which is a ceiling, not a
prediction. Pricing a ceiling produces a figure that reads like a forecast and is not
one.

What it will tell you is what a run **actually** cost, from the session's own call
ledger. Here are real figures from this project's own pilot — three sessions, four
participants, a three-section guide:

| | Per session |
|---|---|
| Cost | **USD 1.17 – 1.19** |
| Duration | 8 – 12 minutes |
| Billed calls | 41 – 57 |

Three things about that number, all of which matter more than the number itself:

1. **Cost grows with roughly the SQUARE of the turn count.** Every turn re-sends the
   whole discussion so far, so a session twice as long costs about four times as much.
   A figure measured at one guide length does not transfer to another.
2. **The moderator dominates.** In the pilot, 836k of 921k input tokens were moderator
   calls. Choosing a cheaper participant model barely moves the total; choosing a
   cheaper moderator model moves it a lot.
3. **You must enter the rates yourself.** The tool fetches nothing. It prices what ran
   against a rate table you type in, and records when you entered it.

**Budget by measuring, not by estimating:** run one session, read its real cost, then
multiply — knowing that the multiplication is a scenario and not a quote. The tool
labels it `SCENARIO_NOT_BUDGET` for that reason.

---

## 5. Words the interface uses

| Term | What it means |
|---|---|
| **Comparable window** | The trimmed stretch of a session that you compare across sides — so that consent scripts, warm-up chatter and closing admin do not distort the measures. You choose it and you sign it; the tool never picks one for you. |
| **Undefined** | Not measured, not measurable, or not defined for this cell. It is **never** shown as zero, because zero is a finding and "we don't know" is not. |
| **GUIDE_COMPLETED** | The session reached the end of its discussion guide. |
| **MAX_TURNS_REACHED** | The session stopped at the safety cap with the guide unfinished. |
| **Evidence** (`STRUCTURED_STATE` / `STDOUT_CORROBORATED`) | What the completion verdict rests on. `STRUCTURED_STATE` — the session's own saved state says so. `STDOUT_CORROBORATED` — its printed output agreed as well. |
| **CONFLICTING_EVIDENCE** | The state and the printed output disagree about how the session ended. The run is not used. |
| **REQUIRES_RECOVERY** | Output exists on disk, but the durable record of how the session ended does not — so the tool will not say whether it finished. Nothing is deleted; look at the output yourself and decide. |
| **CACHE_WRITE_TTL_UNKNOWN** | The provider bills two caching modes at different rates, and the log does not record which was used. The true cost is inside the range shown. It is a bound, not a failure. |
| **SCENARIO_NOT_BUDGET** | A cost projected from sessions that already ran. It assumes the next sessions resemble them. It is not a quote. |
| **Route A / Route B** | Two ways to group synthetic sessions. **A** groups the repeats within one focus group and condition — use it to ask how variable the generator is for a given cell. **B** groups the *k*-th run across every focus group — use it to ask about a whole study replicate. Report the one your question is about, not both. |
| **EXPLORATORY_NOT_THESIS_DATA** | A run that exercised the machinery and answers no research question. Kept as evidence, excluded from every result. |

---

## 6. What is deliberately not here

- **No cost estimate before a run.** See §4.
- **No thematic fidelity for your own corpus.** See §1.
- **No automatic window detection.** Where a discussion properly begins and ends is a
  methodological judgement, and the tool records yours rather than making one.
- **No comparability by default.** A human transcript is not assumed comparable to a
  synthetic one just for being human; you declare the correspondence and the tool
  records that you did.
- **No filename inference.** Conditions, focus groups and replicates are never read
  from a file name.

---

## 7. Where the rest of the documentation is

`docs/` is written for auditors, not users. The two files worth knowing about:

- `AUDIT_HANDOFF_AND_CONTINUATION.md` — the engineering record, including every known
  open defect. Read §19 and §20 if you want to know what is still wrong.
- `EXPLORATORY_RUNS_MANIFEST.json` — every real run this project has ever made,
  hashed, and marked as not being study data.
