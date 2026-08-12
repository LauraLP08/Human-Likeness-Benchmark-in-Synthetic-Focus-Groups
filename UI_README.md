# Running the UI — Synthetic Focus Group Platform

The graphical interface lives at [`apps/focus_group_platform/`](apps/focus_group_platform/).
It is a Streamlit application that lets you browse this dissertation's frozen benchmark,
run the same structural measures over **your own** transcripts, and generate synthetic
focus groups.

This page is the setup guide. The application's own
[`apps/focus_group_platform/README.md`](apps/focus_group_platform/README.md) is the user
manual — read it before running a study, especially §3 (the exact file formats it accepts)
and §4 (what a run costs).

---

## 1. Install

From the repository root:

```bash
pip install -r apps/focus_group_platform/requirements.txt
```

That pulls `streamlit`, `pandas`, `altair`, `PyYAML` and `psutil`. If you also intend to
generate sessions from the UI, install the main dependencies too:

```bash
pip install -r requirements.txt
```

Developed and tested on **Python 3.14**; 3.11 is the language floor and was not tested.

---

## 2. Launch

Run it **from the repository root**, not from inside the app directory:

```bash
py -m streamlit run apps/focus_group_platform/app/streamlit_app.py
```

Streamlit prints a local URL (normally <http://localhost:8501>) and opens a browser tab.

**Why the working directory matters.** `platform_core/config.py` resolves the repository
root as three levels above itself — `apps/focus_group_platform/platform_core/` → repo
root. Moving the app to a different depth breaks its access to
`analysis/production_evaluation/`, `scripts/` and `output/session_logs/`. Keep it where
it is.

---

## 3. Where your data is stored

**Your projects are written outside this repository**, under your user application-data
directory:

| OS | Default location |
|---|---|
| Windows | `%LOCALAPPDATA%\FocusGroupPlatform\` |
| macOS | `~/Library/Application Support/FocusGroupPlatform/` |
| Linux | `~/.local/share/focus-group-platform/` |

Override it with an environment variable before launching:

```bash
FOCUS_GROUP_PLATFORM_DATA_DIR=/path/to/my/projects py -m streamlit run apps/focus_group_platform/app/streamlit_app.py
```

The Home screen shows the exact resolved path. Nothing is created until you explicitly
create a project — importing the package or running the tests never leaves data behind.
A path *inside* this repository is refused by design, so the frozen benchmark cannot be
overwritten by ordinary use.

---

## 4. The four screens

| Screen | What it does | Spends money? |
|---|---|---|
| **Home / Projects** | Create, open and list projects; shows the resolved data directory | No |
| **Frozen benchmark** | Read-only view of this dissertation's Level 1 (thematic fidelity) and Level 2 (interaction process) results | No |
| **New evaluation** | Import your transcripts, declare comparability, set a comparable window, compute structural measures, aggregate, export | No |
| **Generate focus groups** | Launches real sessions against a paid provider | **Yes** |

Only *Generate focus groups* costs money. The sidebar tells you which screen you are on.
Generation is a seven-step flow kept deliberately separate from evaluation, because a
launch button on an evaluation screen is a launch button somebody presses by accident.

To generate, set `ANTHROPIC_API_KEY` in the environment **before** launching Streamlit —
the app inherits the shell's environment.

---

## 5. What the UI can and cannot do with your own data

**It can** compute the structural and interactional layer for any corpus you supply:
words per turn and its distribution, participation share and Gini, moderator share,
participant-to-participant adjacency, chain depth, turn counts and session length.

**It cannot** compute thematic fidelity — subtheme recall, precision, F1, participant
reach — for your corpus. Those exist in this tool only for the frozen Macho Meals
benchmark, where a validated codebook and a completed coding procedure already exist.
For your study they would need a codebook and a coding procedure of your own, and that
layer is not built. The interface says so where it applies.

So: if your question is *"do synthetic groups reproduce the themes my humans raised?"*,
the UI cannot answer it for your data — you would run the scripts in `scripts/` with your
own codebook. If your question is *"do synthetic groups reproduce the interactional
structure?"*, it can.

---

## 6. Input formats, in one paragraph each

Full examples are in the app's own README §3.

- **Human transcript** — a JSON array of turns. Every turn needs `turn`, `speaker_id`,
  `speaker_name`, `canonical_speaker_id`, `speaker_role` (`moderator` or `participant`)
  and `content`. `canonical_speaker_id` is the identity you keep consistent across
  sessions; it is what lets the tool follow the same person between them. There is **no
  `.docx` importer** — converting from Word is your work.
- **Agent payload** — a JSON object with `agent_id` and `persona.demographics.name`
  required; everything else optional. The rule that matters: `background`,
  `food_consumption`, `location` and `psychometric_scores` must be **objects of labelled
  entries, never plain strings**. A prose string passes schema validation and then
  crashes the session partway through, after the calls have already been billed. The tool
  now refuses that shape up front.
- **Discussion guide** — YAML with `guide_id`, `title` and a list of `sections`, each with
  `label`, `phase` (`intro` / `main_topic` / `closing`) and `scripted_question`, plus
  optional `suggested_probes`. The number of sections drives session length, and therefore
  cost.

---

## 7. Cost

The tool **refuses to estimate a cost before a run**, deliberately: the only number
available beforehand is `--max-turns`, which is a ceiling, not a prediction, and pricing
a ceiling produces something that reads like a forecast. It reports what a run
*actually* cost from the session's own call ledger, against a rate table you type in
yourself — it fetches no prices.

Real figures from this platform's own three-session pilot (four participants,
three-section guide): **USD 1.17–1.19 per session, 8–12 minutes, 41–57 billed calls.**

Two things matter more than that number:

1. **Cost grows with roughly the square of the turn count.** Every turn re-sends the
   whole discussion, so a session twice as long costs about four times as much. A figure
   measured at one guide length does not transfer to another.
2. **The moderator dominates.** In that pilot, 836k of 921k input tokens were moderator
   calls. A cheaper participant model barely moves the total; a cheaper moderator model
   moves it a lot.

Budget by measuring: run one session, read its real cost, multiply — and treat the
multiplication as a scenario, which is why the tool labels it `SCENARIO_NOT_BUDGET`.

---

## 8. Vocabulary the interface uses

| Term | Meaning |
|---|---|
| **Comparable window** | The trimmed stretch of a session compared across sides, so consent scripts, warm-up chatter and closing admin do not distort the measures. You choose it and you sign it; the tool never picks one for you. |
| **Undefined** | Not measured, not measurable, or not defined for this cell. Never shown as zero — zero is a finding, "we don't know" is not. |
| **GUIDE_COMPLETED** / **MAX_TURNS_REACHED** | The session reached the end of its guide / stopped at the safety cap with the guide unfinished. |
| **STRUCTURED_STATE** / **STDOUT_CORROBORATED** | What a completion verdict rests on: the session's saved state, optionally corroborated by its printed output. |
| **CONFLICTING_EVIDENCE** | State and printed output disagree about how the session ended. The run is not used. |
| **REQUIRES_RECOVERY** | Output exists on disk but the durable record of how the session ended does not. Nothing is deleted; you look and decide. |
| **CACHE_WRITE_TTL_UNKNOWN** | The provider bills two caching modes at different rates and the log does not say which ran. The true cost is inside the range shown — a bound, not a failure. |
| **Route A / Route B** | Two ways to group synthetic sessions. **A** groups repeats within one focus group and condition — how variable is the generator for this cell. **B** groups the *k*-th run across every focus group — a whole study replicate. Report the one your question is about, not both. |
| **EXPLORATORY_NOT_THESIS_DATA** | A run that exercised the machinery and answers no research question. Kept as evidence, excluded from every result. |

---

## 9. Tests and known state

```bash
cd apps/focus_group_platform
py -m pytest tests -q
```

**This suite does not currently pass end to end**, and it does not in the source
repository either — the same failures appear in both. They are concentrated in the
golden-run and app-smoke modules and are documented in
`apps/focus_group_platform/docs/AUDIT_HANDOFF_AND_CONTINUATION.md` §19–§20, which is the
engineering record of every known open defect. Read it before relying on any part of the
tool for a study.

The application's own integrity checks against the frozen benchmark — the protected-path
list in `frozen_sessions.json` — do resolve completely in this repository.

`apps/focus_group_platform/docs/EXPLORATORY_RUNS_MANIFEST.json` lists every real run this
platform has ever made, hashed and marked as not being study data.

---

## 10. Not included: the earlier UI

An earlier generation interface (FastAPI backend + React/Vite frontend, launched by
`start_ui.bat`) was built during the project and is described in `UI_ARCHITECTURE.md` in
the working repository. It is superseded by the platform above and is not published here.
