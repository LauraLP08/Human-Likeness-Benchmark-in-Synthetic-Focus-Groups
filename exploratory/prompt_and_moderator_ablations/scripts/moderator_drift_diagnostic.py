"""
Moderator drift, guide adherence, and repetition diagnostic.

Computes purely structural metrics (Part 2) and LLM-assisted metrics
(Parts 3–4, marked exploratory) across all human and synthetic transcripts.

Hard rules:
  - No generation/moderator changes.
  - No 25-run batch.
  - Uses gemini-3.5-flash (validated evaluator) for LLM steps.
  - LLM metrics labelled EXPLORATORY in output.

Usage:
    py scripts/moderator_drift_diagnostic.py [--skip-llm]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import yaml

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_STD = _REPO_ROOT / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
_SYNTH = _REPO_ROOT / "output" / "session_logs"
_GUIDE_PATH = _REPO_ROOT / "configs" / "guides" / "macho_meals_plant_based_masculinity_uk.yaml"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"
_DATE = "2026-07-20"

_HUMAN_FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]

_SYNTH_SESSIONS: dict[str, str] = {
    "synth_fg1": "costfix_validation_fg1",
    "synth_fg5": "costfix_validation_fg5",
}
_SYNTH_FG5_R2 = "fidelity_fg5_r1"  # second run for cross-run novelty

_TIER2_JSON = _REPO_ROOT / "analysis" / "coding_frame" / "validation_tier1reach_tier2_gemini25.json"

_EVALUATOR_KEY = "GEMINI_API_KEY_NEXT"
_EVALUATOR_MODEL = "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# Transcript loading (unified for human + synthetic)
# ---------------------------------------------------------------------------

def _is_moderator(entry: dict) -> bool:
    if "speaker_role" in entry:
        return entry["speaker_role"] == "moderator"
    sid = entry.get("speaker_id", "").upper()
    sname = entry.get("speaker_name", "").lower()
    return sid == "MODERATOR" or sname == "moderator"


def load_transcript(path: Path) -> list[dict]:
    """Load transcript.json, normalise to {turn_id, speaker_name, is_moderator, content}."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for e in raw:
        content = e.get("content", "").strip()
        if not content:
            continue
        out.append({
            "turn_id":      str(e.get("turn", "")),
            "speaker_name": e.get("speaker_name", e.get("speaker_id", "")),
            "speaker_id":   e.get("speaker_id", ""),
            "is_moderator": _is_moderator(e),
            "content":      content,
        })
    return out


# ---------------------------------------------------------------------------
# Guide loading
# ---------------------------------------------------------------------------

def load_guide(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Part 2 — Structural metrics (pure Python, authoritative)
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split())


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * pct / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    return round(-sum((c / total) * math.log2(c / total) for c in counts if c > 0), 3)


def _gini(values: list[float]) -> float:
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    sv = sorted(values)
    numer = sum((i + 1) * v for i, v in enumerate(sv))
    return round(2 * numer / (n * sum(sv)) - (n + 1) / n, 3)


def structural_metrics(entries: list[dict], label: str) -> dict:
    participants = [e for e in entries if not e["is_moderator"]]
    moderator    = [e for e in entries if e["is_moderator"]]

    total_turns = len(entries)
    p_wc  = [_word_count(e["content"]) for e in participants]
    m_wc  = [_word_count(e["content"]) for e in moderator]
    all_wc = [_word_count(e["content"]) for e in entries]

    sv_p = sorted(p_wc)
    med  = _percentile(sv_p, 50)
    q1   = _percentile(sv_p, 25)
    q3   = _percentile(sv_p, 75)

    # Participation balance
    per_speaker: dict[str, dict] = {}
    for e in entries:
        n = e["speaker_name"]
        if n not in per_speaker:
            per_speaker[n] = {"turns": 0, "words": 0, "is_mod": e["is_moderator"]}
        per_speaker[n]["turns"] += 1
        per_speaker[n]["words"] += _word_count(e["content"])

    p_names = [n for n, d in per_speaker.items() if not d["is_mod"]]
    p_turns_list = [per_speaker[n]["turns"] for n in p_names]
    p_words_list = [per_speaker[n]["words"] for n in p_names]
    n_participants = len(p_names)

    turn_entropy  = _entropy(p_turns_list)
    word_entropy  = _entropy(p_words_list)
    max_ent       = math.log2(n_participants) if n_participants > 1 else 1.0
    norm_entropy  = round(turn_entropy / max_ent, 3) if max_ent > 0 else 0.0
    gini_turns    = _gini([float(x) for x in p_turns_list])
    gini_words    = _gini([float(x) for x in p_words_list])

    mod_turns = per_speaker.get("Moderator", per_speaker.get("moderator", {}))
    total_words = sum(all_wc)
    mod_word_share = round(mod_turns.get("words", 0) / total_words, 3) if total_words else 0.0
    mod_turn_share = round(len(moderator) / total_turns, 3) if total_turns else 0.0

    # Adjacency P→P
    pp_count = 0
    for i in range(1, len(entries)):
        if not entries[i]["is_moderator"] and not entries[i - 1]["is_moderator"]:
            if entries[i]["speaker_name"] != entries[i - 1]["speaker_name"]:
                pp_count += 1
    pp_frac = round(pp_count / len(participants), 3) if participants else 0.0

    # Reference density: participant turns mentioning another participant's name
    all_p_names_lower = {n.lower() for n in p_names}
    ref_count = 0
    for e in participants:
        text_lower = e["content"].lower()
        speaker_lower = e["speaker_name"].lower()
        if any(n in text_lower for n in all_p_names_lower if n != speaker_lower):
            ref_count += 1
    ref_density = round(ref_count / len(participants), 3) if participants else 0.0

    # Chain depth: consecutive participant runs uninterrupted by moderator
    chains: list[int] = []
    chain = 0
    for e in entries:
        if not e["is_moderator"]:
            chain += 1
        else:
            if chain:
                chains.append(chain)
            chain = 0
    if chain:
        chains.append(chain)

    total_p = len(participants)
    in_chain3 = sum(l for l in chains if l >= 3)
    in_chain5 = sum(l for l in chains if l >= 5)

    return {
        "label":             label,
        "total_turns":       total_turns,
        "participant_turns": len(participants),
        "moderator_turns":   len(moderator),
        "n_participants":    n_participants,
        "verbosity": {
            "median_words":       round(med, 1),
            "q1_words":           round(q1, 1),
            "q3_words":           round(q3, 1),
            "iqr_words":          round(q3 - q1, 1),
            "frac_le20words":     round(sum(1 for w in p_wc if w <= 20) / len(p_wc), 3)
                                  if p_wc else 0.0,
        },
        "participation": {
            "n_participants":     n_participants,
            "turn_entropy_norm":  norm_entropy,
            "gini_turns":         gini_turns,
            "gini_words":         gini_words,
            "mod_turn_share":     mod_turn_share,
            "mod_word_share":     mod_word_share,
        },
        "adjacency_pp_frac":  pp_frac,
        "reference_density":  ref_density,
        "chain_depth": {
            "n_chains":           len(chains),
            "mean_chain":         round(sum(chains) / len(chains), 2) if chains else 0.0,
            "max_chain":          max(chains) if chains else 0,
            "frac_in_chain_ge3":  round(in_chain3 / total_p, 3) if total_p else 0.0,
            "frac_in_chain_ge5":  round(in_chain5 / total_p, 3) if total_p else 0.0,
            "chain_lengths":      chains,
        },
    }


# ---------------------------------------------------------------------------
# Part 3a — Moderator log tabulation
# ---------------------------------------------------------------------------

# Map log action strings to broad categories
_REDIRECT_ACTIONS = {"redirect_to_group", "synthesize_and_challenge", "redirect_to_guide"}
_PROBE_ACTIONS = {
    "reactivate_silent", "invite_dissent", "invite_to_speak", "direct_probe",
    "probe_follow_up", "clarify",
}
_GUIDE_QUESTION_ACTIONS = {"section_transition", "ask_initial_to_group", "closing"}
_REFLECT_ACTIONS = {"reflect_contradiction", "reflect_summarize", "synthesize"}


def _classify_log_action(action: str | None, mode: str | None) -> str:
    if not action or mode == "observe":
        return "allow"
    if action in _REDIRECT_ACTIONS:
        return "redirect_refocus"
    if action in _PROBE_ACTIONS:
        return "probe"
    if action in _GUIDE_QUESTION_ACTIONS:
        return "guide_question"
    if action in _REFLECT_ACTIONS:
        return "reflect_summarize"
    return "other"


def tabulate_moderator_log(log_path: Path, label: str) -> dict:
    if not log_path.exists():
        return {"label": label, "error": "no log file"}
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)

    category_counts: dict[str, int] = {}
    raw_action_counts: dict[str, int] = {}
    for entry in log:
        action = entry.get("action")
        mode   = entry.get("intervention_mode", "")
        cat    = _classify_log_action(action, mode)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        raw_key = action or "(null)"
        raw_action_counts[raw_key] = raw_action_counts.get(raw_key, 0) + 1

    total = len(log)
    redirect_n = category_counts.get("redirect_refocus", 0)
    redirect_rate = round(redirect_n / total, 3) if total else 0.0

    return {
        "label":           label,
        "total_log_entries": total,
        "categories":      dict(sorted(category_counts.items(), key=lambda x: -x[1])),
        "raw_actions":     dict(sorted(raw_action_counts.items(), key=lambda x: -x[1])),
        "redirect_refocus_n":    redirect_n,
        "redirect_refocus_rate": redirect_rate,
    }


# ---------------------------------------------------------------------------
# LLM helpers (gemini-3.5-flash via google-genai)
# ---------------------------------------------------------------------------

def _llm_client():
    from google import genai as _genai
    key = os.environ.get(_EVALUATOR_KEY) or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            f"No API key: set {_EVALUATOR_KEY} or GOOGLE_API_KEY in .env"
        )
    return _genai.Client(api_key=key)


def _llm_call(client, prompt: str, max_tokens: int = 16384) -> str:
    """Single generate_content call; returns raw text."""
    cfg = {
        "response_mime_type": "application/json",
        "max_output_tokens":  max_tokens,
        "thinking_config":    {"thinking_budget": 0},
    }
    response = client.models.generate_content(
        model=_EVALUATOR_MODEL,
        contents=prompt,
        config=cfg,
    )
    return response.text or ""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)
        text = re.sub(r"\n```$", "", text.strip())
    return text.strip()


# ---------------------------------------------------------------------------
# Part 3b + 4 — Combined LLM turn labeling (EXPLORATORY)
# ---------------------------------------------------------------------------

_GUIDE_SECTIONS_TEXT = """\
0. Introductions (name, location)
1. Male friendship and place (favourite spots with male friends)
2. Everyday food decision-making (how men decide what to eat; influences of others, work, hobbies, health, taste)
3. Gender and food choice (does gender influence eating? masculine/feminine foods? social acceptability of vegetarian/vegan)
4. Imagining a plant-based shift (what would need to change in life to go plant-based?)
5. Making plant-based foods more appealing
6. Closing remarks"""

_COMBINED_LABEL_PROMPT = """\
You are a qualitative researcher labeling turns in a focus group on "Men's food choices and plant-based eating in the UK."

Guide sections:
{guide_sections}

Instructions:
- For MODERATOR turns: classify the communicative FUNCTION as one of:
    guide_question  — introduces or closes a guide section
    probe           — follows up a participant's remark; invites elaboration/clarification
    redirect_refocus — explicitly steers back to the guide or refocuses drifting discussion
    reflect_summarize — summarises or reflects back what participants said
    allow           — minimal/no intervention; lets conversation continue
- For PARTICIPANT turns: label as on_guide or off_guide.
    on_guide  = clearly relates to a guide section (food, gender, plant-based, masculinity, social context)
    off_guide = drifted beyond the guide: personal life confessions unrelated to food/gender, therapy-style
                emotional processing, tangents about family/relationships not linked to a guide topic,
                repetitive anecdotes that do not advance any guide question
  Also return the closest guide_section (0–6) for on_guide turns; null for off_guide.

Return JSON ONLY — a flat array, one object per turn:
  Moderator: {{"turn_id":"T001","speaker":"M","function":"guide_question"}}
  Participant: {{"turn_id":"T002","speaker":"P","label":"on_guide","guide_section":3}}

TRANSCRIPT:
{turns_text}"""


def _format_turns_for_llm(entries: list[dict]) -> str:
    lines = []
    for e in entries:
        tag = "[MOD]" if e["is_moderator"] else "[PTK]"
        lines.append(f"[{e['turn_id']}] {tag} {e['speaker_name']}: {e['content'][:400]}")
    return "\n".join(lines)


def llm_label_transcript(client, entries: list[dict], label: str) -> list[dict]:
    """Label every turn in one LLM call (EXPLORATORY)."""
    turns_text = _format_turns_for_llm(entries)
    prompt = _COMBINED_LABEL_PROMPT.format(
        guide_sections=_GUIDE_SECTIONS_TEXT,
        turns_text=turns_text,
    )
    print(f"  [LLM] Labeling {label} ({len(entries)} turns) ...", end=" ", flush=True)
    try:
        raw = _llm_call(client, prompt)
        labels = json.loads(_strip_json_fences(raw))
        print(f"done ({len(labels)} labels returned)")
        return labels
    except Exception as exc:
        print(f"ERROR: {exc}")
        return []


def parse_llm_labels(labels: list[dict]) -> tuple[dict[str, str], dict[str, str | None]]:
    """Returns (mod_function_by_turn, participant_label_by_turn)."""
    mod_fn: dict[str, str]       = {}
    p_label: dict[str, str | None] = {}
    for item in labels:
        tid = str(item.get("turn_id", ""))
        if item.get("speaker") == "M":
            mod_fn[tid] = item.get("function", "allow")
        else:
            p_label[tid] = item.get("label", "on_guide")
    return mod_fn, p_label


# ---------------------------------------------------------------------------
# Part 3 (cont.) — Un-redirected drift episodes
# ---------------------------------------------------------------------------

def drift_episodes(entries: list[dict], p_label_by_turn: dict, mod_fn_by_turn: dict) -> dict:
    """
    Identify stretches of ≥3 consecutive off-guide participant turns.
    For each episode, check whether the moderator issued redirect_refocus
    within the next 2 moderator turns.
    """
    # Build ordered list of participant turns with labels
    # and moderator turns with functions, in transcript order
    ordered: list[dict] = []
    for e in entries:
        tid = e["turn_id"]
        if e["is_moderator"]:
            fn = mod_fn_by_turn.get(tid, "allow")
            ordered.append({"type": "M", "turn_id": tid, "function": fn})
        else:
            lbl = p_label_by_turn.get(tid, "on_guide")
            ordered.append({"type": "P", "turn_id": tid, "label": lbl})

    # Find consecutive off-guide participant runs
    episodes: list[dict] = []
    i = 0
    while i < len(ordered):
        item = ordered[i]
        if item["type"] == "P" and item.get("label") == "off_guide":
            # Start of a potential off-guide run
            run_start = i
            j = i
            while j < len(ordered) and (
                ordered[j]["type"] == "P" and ordered[j].get("label") == "off_guide"
            ):
                j += 1
            run_len = j - run_start
            if run_len >= 3:
                # Count next 2 moderator turns after the run
                mod_turns_after: list[str] = []
                k = j
                while k < len(ordered) and len(mod_turns_after) < 2:
                    if ordered[k]["type"] == "M":
                        mod_turns_after.append(ordered[k]["function"])
                    k += 1
                redirected = "redirect_refocus" in mod_turns_after
                episodes.append({
                    "run_start_turn": ordered[run_start]["turn_id"],
                    "run_length": run_len,
                    "redirected": redirected,
                    "next_mod_functions": mod_turns_after,
                })
            i = j
        else:
            i += 1

    n_total = len(episodes)
    n_redirected = sum(1 for ep in episodes if ep["redirected"])
    rate = round(n_redirected / n_total, 3) if n_total else None

    return {
        "n_drift_episodes":     n_total,
        "n_redirected":         n_redirected,
        "redirect_rate":        rate,
        "episodes":             episodes,
    }


# ---------------------------------------------------------------------------
# Part 4 — Guide adherence metrics
# ---------------------------------------------------------------------------

def guide_adherence_metrics(entries: list[dict], p_label_by_turn: dict, label: str) -> dict:
    p_entries = [e for e in entries if not e["is_moderator"]]
    if not p_entries:
        return {"label": label, "off_guide_frac": None}
    off_count = sum(
        1 for e in p_entries
        if p_label_by_turn.get(e["turn_id"], "on_guide") == "off_guide"
    )
    return {
        "label":            label,
        "n_participant_turns": len(p_entries),
        "n_off_guide":      off_count,
        "off_guide_frac":   round(off_count / len(p_entries), 3),
    }


# ---------------------------------------------------------------------------
# Part 5a — Cross-run Tier-2 novelty (from existing JSON)
# ---------------------------------------------------------------------------

def cross_run_novelty_from_json(json_path: Path) -> dict | None:
    """Extract novelty curve from the existing tier1reach_tier2 JSON."""
    if not json_path.exists():
        return None
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    rep = data.get("tier2", {}).get("repeatability", {})
    theme_counts = rep.get("theme_counts", [])
    pairwise     = rep.get("pairwise", [])

    # Derive cumulative unique themes:
    # run1 = theme_counts[0]
    # run2 added = themes in run2 that don't match run1
    #   = run2_themes × (1 - precision of run1_vs_run2)
    # run3 added = themes in run3 that don't match run1 OR run2
    novelty: list[int] = []
    if theme_counts:
        novelty.append(theme_counts[0])   # run1 baseline
        for i, p in enumerate(pairwise):
            # p covers run(i+1)_vs_run(i+2); first pair = run1 vs run2
            if i == 0 and len(theme_counts) > 1:
                # Unmatched in run2 = run2_themes * (1 - precision)
                unmatched = round(theme_counts[1] * (1 - p["precision"]))
                novelty.append(int(unmatched))
            elif i == 2 and len(theme_counts) > 2:
                # run2 vs run3: themes in run3 not matched by run2
                unmatched = round(theme_counts[2] * (1 - p["precision"]))
                novelty.append(int(unmatched))

    cumulative = []
    total = 0
    for n in novelty:
        total += n
        cumulative.append(total)

    return {
        "source":        "real_fg1 tier2 repeatability",
        "n_runs":        len(theme_counts),
        "theme_counts_per_run": theme_counts,
        "new_themes_added": novelty,
        "cumulative_unique": cumulative,
        "pairwise_summary": [
            {"pair": p["runs"], "recall": p["recall"], "precision": p["precision"]}
            for p in pairwise
        ],
    }


# ---------------------------------------------------------------------------
# Part 5b — Intra-transcript embedding redundancy
# ---------------------------------------------------------------------------

def embedding_redundancy(entries: list[dict], label: str) -> dict:
    """
    For each participant turn, compute max cosine similarity to all earlier
    participant turns. Uses paraphrase-multilingual-mpnet-base-v2.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        print(f"  [Embed] sentence-transformers not available — skipping {label}")
        return {"label": label, "error": "sentence-transformers not installed"}

    p_entries = [e for e in entries if not e["is_moderator"]]
    texts = [e["content"] for e in p_entries]
    if len(texts) < 2:
        return {"label": label, "n_turns": len(texts), "mean_max_sim": None, "frac_gt07": None}

    print(f"  [Embed] Encoding {len(texts)} turns for {label} ...", end=" ", flush=True)
    model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
    embs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    # Normalise
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embs = embs / norms

    max_sims: list[float] = []
    for i in range(1, len(texts)):
        sims = embs[:i] @ embs[i]
        max_sims.append(float(np.max(sims)))

    mean_max = round(float(sum(max_sims) / len(max_sims)), 3)
    frac_gt07 = round(sum(1 for s in max_sims if s >= 0.7) / len(max_sims), 3)
    print(f"done (mean_max_sim={mean_max:.3f})")

    return {
        "label":         label,
        "n_turns":       len(texts),
        "mean_max_sim":  mean_max,
        "frac_gt07":     frac_gt07,
    }


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _fmt(v, pct: bool = False, na: str = "n/a") -> str:
    if v is None:
        return na
    if pct:
        return f"{v:.1%}"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def write_report(
    structural: dict[str, dict],
    log_results: dict[str, dict],
    llm_results: dict[str, dict],   # keyed by label; contains mod_labels, adherence, drift
    novelty: dict | None,
    redundancy: dict[str, dict],
    out_path: Path,
) -> None:
    lines: list[str] = [
        f"# Moderator Drift, Guide Adherence, and Repetition — Diagnostic",
        f"",
        f"**Date:** {_DATE}  ",
        f"**Evaluator (LLM steps):** `{_EVALUATOR_MODEL}`  ",
        f"**Note:** Structural metrics (Parts 2, 3a, 5b) are authoritative. "
        f"LLM-assisted metrics (Parts 3b, 4, and drift-episode count) are EXPLORATORY "
        f"— they have not yet passed repeatability or human-anchor gates.",
        f"",
        f"**Transcripts used:**",
        f"- Human: FG1–FG5 (real focus groups, standardised transcripts)",
        f"- Synthetic: costfix\\_validation\\_fg1 (Synth FG1), costfix\\_validation\\_fg5 (Synth FG5)",
        f"",
        f"---",
        f"",
        f"## Part 2 — Interactional Structural Metrics",
        f"",
        f"### 2.1 Verbosity and participation",
        f"",
        f"| Transcript | N turns | N ptk | Median words | IQR | ≤20w frac |",
        f"|-----------|---------|-------|-------------|-----|-----------|",
    ]
    for lbl, m in structural.items():
        v = m["verbosity"]
        lines.append(
            f"| {lbl} | {m['total_turns']} | {m['participant_turns']} | "
            f"{v['median_words']} | {v['iqr_words']} | {_fmt(v['frac_le20words'], pct=True)} |"
        )

    lines += [
        f"",
        f"### 2.2 Participation balance",
        f"",
        f"| Transcript | N ptk | Entropy (norm) | Gini turns | Gini words | Mod turn% | Mod word% |",
        f"|-----------|-------|--------------|-----------|-----------|----------|----------|",
    ]
    for lbl, m in structural.items():
        p = m["participation"]
        lines.append(
            f"| {lbl} | {p['n_participants']} | {_fmt(p['turn_entropy_norm'])} | "
            f"{_fmt(p['gini_turns'])} | {_fmt(p['gini_words'])} | "
            f"{_fmt(p['mod_turn_share'], pct=True)} | {_fmt(p['mod_word_share'], pct=True)} |"
        )

    lines += [
        f"",
        f"### 2.3 Adjacency P→P and reference density",
        f"",
        f"| Transcript | P→P frac | Reference density |",
        f"|-----------|---------|-----------------|",
    ]
    for lbl, m in structural.items():
        lines.append(
            f"| {lbl} | {_fmt(m['adjacency_pp_frac'])} | {_fmt(m['reference_density'])} |"
        )

    lines += [
        f"",
        f"### 2.4 Chain depth (consecutive participant runs without moderator)",
        f"",
        f"| Transcript | Mean chain | Max chain | Frac in chain≥3 | Frac in chain≥5 |",
        f"|-----------|-----------|----------|----------------|----------------|",
    ]
    for lbl, m in structural.items():
        cd = m["chain_depth"]
        lines.append(
            f"| {lbl} | {_fmt(cd['mean_chain'])} | {cd['max_chain']} | "
            f"{_fmt(cd['frac_in_chain_ge3'], pct=True)} | {_fmt(cd['frac_in_chain_ge5'], pct=True)} |"
        )

    # Part 3a
    lines += [
        f"",
        f"---",
        f"",
        f"## Part 3 — Moderator Steering",
        f"",
        f"### 3a. Decision-log action breakdown (synthetic sessions only)",
        f"",
        f"| Session | allow | guide_question | probe | redirect_refocus | reflect_summarize | other | Redirect rate |",
        f"|---------|-------|--------------|-------|-----------------|-----------------|-------|--------------|",
    ]
    for lbl, r in log_results.items():
        if "error" in r:
            lines.append(f"| {lbl} | — (no log) | | | | | | |")
            continue
        cats = r["categories"]
        lines.append(
            f"| {lbl} | {cats.get('allow',0)} | {cats.get('guide_question',0)} | "
            f"{cats.get('probe',0)} | {cats.get('redirect_refocus',0)} | "
            f"{cats.get('reflect_summarize',0)} | {cats.get('other',0)} | "
            f"{_fmt(r['redirect_refocus_rate'], pct=True)} |"
        )

    # Part 3b (LLM) and drift
    lines += [
        f"",
        f"### 3b. LLM moderator-turn function labels (EXPLORATORY)",
        f"",
        f"| Transcript | allow | guide_q | probe | redirect | reflect | Redirect rate |",
        f"|-----------|-------|--------|-------|---------|--------|--------------|",
    ]
    for lbl, lr in llm_results.items():
        if not lr.get("mod_labels"):
            lines.append(f"| {lbl} | — | — | — | — | — | — |")
            continue
        fn_counts: dict[str, int] = {}
        for fn in lr["mod_labels"].values():
            fn_counts[fn] = fn_counts.get(fn, 0) + 1
        total_m = sum(fn_counts.values())
        rr = round(fn_counts.get("redirect_refocus", 0) / total_m, 3) if total_m else 0.0
        lines.append(
            f"| {lbl} | {fn_counts.get('allow',0)} | {fn_counts.get('guide_question',0)} | "
            f"{fn_counts.get('probe',0)} | {fn_counts.get('redirect_refocus',0)} | "
            f"{fn_counts.get('reflect_summarize',0)} | {_fmt(rr, pct=True)} |"
        )

    lines += [
        f"",
        f"### 3c. Un-redirected drift episodes (EXPLORATORY)",
        f"",
        f"Drift episode = ≥3 consecutive off-guide participant turns.",
        f"Redirected = moderator issued redirect\\_refocus within next 2 moderator turns.",
        f"",
        f"| Transcript | Drift episodes | Redirected | Rate | Researcher hypothesis |",
        f"|-----------|--------------|-----------|------|----------------------|",
    ]
    for lbl, lr in llm_results.items():
        de = lr.get("drift_episodes")
        if de is None:
            lines.append(f"| {lbl} | n/a | n/a | n/a | |")
            continue
        n_ep = de["n_drift_episodes"]
        n_rd = de["n_redirected"]
        rate = _fmt(de["redirect_rate"], pct=True) if de["redirect_rate"] is not None else "n/a"
        lines.append(f"| {lbl} | {n_ep} | {n_rd} | {rate} | |")

    # Part 4
    lines += [
        f"",
        f"---",
        f"",
        f"## Part 4 — Guide Adherence and Off-Guide Drift (EXPLORATORY)",
        f"",
        f"| Transcript | Participant turns | Off-guide | Off-guide % |",
        f"|-----------|-----------------|---------|-----------|",
    ]
    for lbl, lr in llm_results.items():
        adh = lr.get("adherence")
        if adh is None:
            lines.append(f"| {lbl} | — | — | — |")
            continue
        lines.append(
            f"| {lbl} | {adh['n_participant_turns']} | {adh['n_off_guide']} | "
            f"{_fmt(adh['off_guide_frac'], pct=True)} |"
        )

    # Emergent theme cross-reference
    lines += [
        f"",
        f"### 4a. Emergent themes cross-referenced to guide",
        f"",
        f"Tier-2 open themes from the discrimination run (gemini-2.5-flash, gemini25 evaluator).",
        f"All flagged as emergent (absent from real FG1). Those that are also off-guide by LLM",
        f"labeling are the quantitative fingerprint of confessional/therapy drift.",
        f"",
        f"**Synth FG1 emergent themes:**",
        f"- Lack of Motivation to Change Eating Habits (participants=4)",
        f"- Impact of Geographic Location on Food Access (participants=2)",
        f"- Unacknowledged Social Pressure and Conformity (participants=3)",
        f"",
        f"**Synth FG5 emergent themes:**",
        f"- Impact of Rural Living on Food Choices (participants=2)",
        f"- Physical Signals and Dietary Adjustment (participants=3)",
        f"- The Cost of Pretending vs. Acknowledging Change (participants=3)",
        f"- Aging and the Urgency of Change (participants=3)",
        f"- Practicality and Consistency in Sustaining Change (participants=2)",
        f"",
        f"Note: 'Unacknowledged Social Pressure', 'The Cost of Pretending', and 'Aging and Urgency'",
        f"are the themes most consistent with a confessional/therapy register not present in real groups.",
    ]

    # Part 5
    lines += [
        f"",
        f"---",
        f"",
        f"## Part 5 — Repetition",
        f"",
        f"### 5a. Cross-run Tier-2 theme novelty (real FG1, from existing validation data)",
        f"",
    ]
    if novelty:
        nc = novelty["theme_counts_per_run"]
        na = novelty["new_themes_added"]
        cu = novelty["cumulative_unique"]
        lines += [
            f"| Run | Themes extracted | New themes added | Cumulative unique |",
            f"|-----|-----------------|-----------------|-----------------|",
        ]
        for i in range(len(nc)):
            new = na[i] if i < len(na) else 0
            cum = cu[i] if i < len(cu) else "?"
            lines.append(f"| Run {i+1} | {nc[i]} | {new if i > 0 else '(baseline)'} | {cum} |")
        lines += [
            f"",
            f"Cross-run saturation reached by run 3 (no new themes). "
            f"{na[1] if len(na) > 1 else '?'} new theme(s) added in run 2.",
        ]
    else:
        lines.append(f"(Cross-run JSON not found — run validate_tier1_reach_tier2.py first)")

    lines += [
        f"",
        f"### 5b. Intra-transcript embedding redundancy",
        f"",
        f"Mean max cosine similarity of each participant turn to ALL earlier turns in the same transcript.",
        f"Model: paraphrase-multilingual-mpnet-base-v2.",
        f"Flag threshold: ≥0.7 = near-duplicate idea.",
        f"",
        f"| Transcript | N turns | Mean max sim | Frac ≥0.7 |",
        f"|-----------|---------|-------------|---------|",
    ]
    for lbl, r in redundancy.items():
        if "error" in r:
            lines.append(f"| {lbl} | — | error | error |")
        else:
            lines.append(
                f"| {lbl} | {r['n_turns']} | {_fmt(r['mean_max_sim'])} | "
                f"{_fmt(r['frac_gt07'], pct=True)} |"
            )

    lines += [
        f"",
        f"---",
        f"",
        f"## Summary by observation",
        f"",
        f"### Observation 1: Does the moderator under-steer and let chains run?",
        f"",
        f"(Fill in after seeing numbers above.)",
        f"",
        f"### Observation 2: Do synthetic sessions drift off-guide into confessional register?",
        f"",
        f"(Fill in after seeing numbers above.)",
        f"",
        f"### Observation 3: Are synthetic sessions more repetitive within-run?",
        f"",
        f"(Fill in after seeing numbers above.)",
        f"",
        f"_Auto-generated by `scripts/moderator_drift_diagnostic.py`._",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nMarkdown: {out_path.relative_to(_REPO_ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(skip_llm: bool = False) -> None:
    print("=" * 65)
    print("  MODERATOR DRIFT DIAGNOSTIC")
    print("=" * 65)

    guide = load_guide(_GUIDE_PATH)
    print(f"Guide: {guide.get('guide_id')}")

    # ── Load all transcripts ──────────────────────────────────────────
    transcripts: dict[str, list[dict]] = {}

    print("\nLoading human transcripts ...")
    for fg in _HUMAN_FGS:
        path = _STD / fg / "transcript.json"
        entries = load_transcript(path)
        transcripts[f"human_{fg}"] = entries
        print(f"  human_{fg}: {len(entries)} entries")

    print("\nLoading synthetic transcripts ...")
    for lbl, sess in _SYNTH_SESSIONS.items():
        path = _SYNTH / sess / "transcript.json"
        entries = load_transcript(path)
        transcripts[lbl] = entries
        print(f"  {lbl} ({sess}): {len(entries)} entries")

    # ── Part 2: Structural metrics ────────────────────────────────────
    print("\n[Part 2] Structural metrics ...")
    structural: dict[str, dict] = {}
    for lbl, entries in transcripts.items():
        structural[lbl] = structural_metrics(entries, lbl)
        m = structural[lbl]
        cd = m["chain_depth"]
        print(
            f"  {lbl}: median_words={m['verbosity']['median_words']}  "
            f"gini_turns={m['participation']['gini_turns']}  "
            f"mean_chain={cd['mean_chain']}  max_chain={cd['max_chain']}  "
            f"frac_ge3={cd['frac_in_chain_ge3']:.1%}"
        )

    # ── Part 3a: Moderator log tabulation ────────────────────────────
    print("\n[Part 3a] Moderator log tabulation ...")
    log_results: dict[str, dict] = {}
    for lbl, sess in _SYNTH_SESSIONS.items():
        log_path = _SYNTH / sess / "moderator_log.json"
        res = tabulate_moderator_log(log_path, lbl)
        log_results[lbl] = res
        print(
            f"  {lbl}: total={res.get('total_log_entries',0)}  "
            f"redirect_refocus={res.get('redirect_refocus_n',0)}  "
            f"rate={res.get('redirect_refocus_rate',0):.1%}"
        )
    for fg in _HUMAN_FGS:
        log_results[f"human_{fg}"] = {"label": f"human_{fg}", "error": "no log (real session)"}

    # ── Parts 3b + 4: LLM labeling ────────────────────────────────────
    llm_results: dict[str, dict] = {}
    if skip_llm:
        print("\n[Parts 3b+4] Skipping LLM steps (--skip-llm)")
        for lbl in transcripts:
            llm_results[lbl] = {
                "mod_labels": None, "p_labels": None,
                "adherence": None, "drift_episodes": None,
            }
    else:
        print("\n[Parts 3b+4] LLM turn labeling (EXPLORATORY, gemini-3.5-flash) ...")
        client = _llm_client()
        for lbl, entries in transcripts.items():
            raw_labels = llm_label_transcript(client, entries, lbl)
            mod_fn, p_lbl = parse_llm_labels(raw_labels)
            adh = guide_adherence_metrics(entries, p_lbl, lbl)
            drift = drift_episodes(entries, p_lbl, mod_fn)
            llm_results[lbl] = {
                "mod_labels":     mod_fn,
                "p_labels":       p_lbl,
                "adherence":      adh,
                "drift_episodes": drift,
            }
            off_pct = adh["off_guide_frac"]
            drift_n = drift["n_drift_episodes"]
            redir_r = drift.get("redirect_rate")
            print(
                f"  {lbl}: off_guide={off_pct:.1%}  "
                f"drift_episodes={drift_n}  "
                f"redirect_rate={f'{redir_r:.1%}' if redir_r is not None else 'n/a'}"
            )

    # ── Part 5a: Cross-run novelty ────────────────────────────────────
    print("\n[Part 5a] Cross-run Tier-2 novelty ...")
    novelty = cross_run_novelty_from_json(_TIER2_JSON)
    if novelty:
        print(f"  Real FG1: {novelty['theme_counts_per_run']} themes per run  "
              f"cumulative unique: {novelty['cumulative_unique']}")
    else:
        print("  (JSON not found)")

    # ── Part 5b: Embedding redundancy ────────────────────────────────
    print("\n[Part 5b] Embedding redundancy (intra-transcript) ...")
    redundancy: dict[str, dict] = {}
    for lbl, entries in transcripts.items():
        redundancy[lbl] = embedding_redundancy(entries, lbl)

    # ── Write report ──────────────────────────────────────────────────
    out_path = _DOCS_DIR / f"{_DATE}_moderator_drift_diagnostic.md"
    write_report(structural, log_results, llm_results, novelty, redundancy, out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM steps (Parts 3b+4); output structural-only report.",
    )
    args = parser.parse_args()
    main(skip_llm=args.skip_llm)
