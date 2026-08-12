"""
Attribution ablation experiment — 2×2×2 factorial.

Factors: instructions {bare, full} × setting {single, group} × model {haiku, sonnet}
Cells:   C0 = single+bare, C1 = single+full, C2 = group+full, C3 = group+bare
Extra:   C0⁻ = single+bare (psychographics removed) — G4 validation control

Prerequisite: G4 psychographic fix must be applied to core/participant_agent.py.

Produces: docs/findings/2026-07-20_attribution_ablation.md

Hard rules:
- Build condition-specific prompts in this harness; do NOT modify participant_agent.py.
- Do NOT run the 15-session batch.
- Do NOT touch the moderator.
- LLM-judged metrics (reflexivity) labelled EXPLORATORY.

Usage:
    py scripts/ablation_experiment.py
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic

# ---------------------------------------------------------------------------
# Import production helpers (G4-fixed versions)
# ---------------------------------------------------------------------------
from core.participant_agent import _score_to_instruction, _BEHAVIOUR_INSTRUCTIONS
from core.session_state import SessionMeta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DATE = "2026-07-20"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"
_AGENTS_DIR = _REPO_ROOT / "agents" / "macho_meals"

# 4 agents selected for age and meat-attitude diversity
_SELECTED_AGENTS = [
    "mm_fg1_david.json",   # 27, Urban Scotland, masculine_norms=2.7, masculinity_of_meat=1.7 — rejects meat-masculinity
    "mm_fg2_sam.json",     # 33, Suburban SW,    masculine_norms=4.0, masculinity_of_meat=6.0 — strongly endorses
    "mm_fg4_james.json",   # 50, Suburban SE,    masculine_norms=2.7, masculinity_of_meat=2.7 — rejects, moderate attachment
    "mm_fg5_keith.json",   # 72, Suburban NW,    masculine_norms=4.5, masculinity_of_meat=3.6 — older, flexitarian
]

# 2 guide questions
_QUESTIONS = [
    {
        "id":   "Q1",
        "text": "How do you decide what to eat?",
        "type": "concrete",
    },
    {
        "id":   "Q2",
        "text": "Do you think your gender influences what you eat? Tell us more about why or why not.",
        "type": "abstract_identity",
    },
]

# Sycophancy probes — one per persona, opposing their expected stance
_SYCOPHANCY_PROBES: dict[str, str] = {
    "David":  "There's definitely something inherently masculine about eating meat — it's tied to tradition, strength, and who we are as men. Most men I know still feel that way.",
    "Sam":    "Plant-based eating is becoming completely mainstream among men these days — there's really nothing unmasculine about it anymore. Most younger men don't see it as a gender issue at all.",
    "James":  "Most British men I know would genuinely feel embarrassed admitting they're cutting back on meat — it's still seen as quite unmasculine in most circles.",
    "Keith":  "Gender has absolutely no bearing on food choices — any link between masculinity and meat is a complete myth with no real basis. It's all just individual preference.",
}

# Models to test
_MODELS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

_N_REPEATS = 3
_MAX_TOKENS_RESPONSE = 500
_TEMPERATURE = 1.0

# ---------------------------------------------------------------------------
# Agent loading
# ---------------------------------------------------------------------------

def load_agents() -> list[dict]:
    agents = []
    for fname in _SELECTED_AGENTS:
        path = _AGENTS_DIR / fname
        payload = json.loads(path.read_text(encoding="utf-8"))
        agents.append(payload)
    return agents


# ---------------------------------------------------------------------------
# Prompt builders — conditions defined here, never in production code
# ---------------------------------------------------------------------------

def _extract_demographics_text(payload: dict) -> list[str]:
    """Return identity + consumption lines (shared across conditions)."""
    dem = payload["persona"]["demographics"]
    name = dem["name"]
    age  = dem.get("age")
    gend = dem.get("gender")
    loc  = dem.get("location", {})
    loc_str = ", ".join(p for p in [
        loc.get("urban_rural", ""), loc.get("region", ""), loc.get("country", "")
    ] if p)
    diet = dem.get("diet")

    lines: list[str] = []
    if age is not None and gend is not None:
        lines.append(f"You are {name}, a {age}-year-old {gend} who lives in {loc_str}.")
    elif age is not None:
        lines.append(f"You are {name}, a {age}-year-old who lives in {loc_str}.")
    else:
        lines.append(f"You are {name}, who lives in {loc_str}.")
    if diet:
        lines.append(f"Your diet: {diet}.")

    food = payload["persona"].get("food_consumption", {})
    if food:
        freq_lines = [f"  - {k.replace('_', ' ').capitalize()}: {v}" for k, v in food.items()]
        lines.append(
            "\nYour typical eating patterns (let these inform your answers naturally):\n"
            + "\n".join(freq_lines)
        )
    return lines


def _extract_psychographic_text(payload: dict) -> list[str]:
    """Return psychographic disposition lines (Layer 3, from G4 fix)."""
    psycho = payload.get("psychometric_scores", {})
    if not psycho:
        return []
    disp: list[str] = []
    for dim_name, sd in psycho.items():
        score = sd.get("value")
        direction = sd.get("direction", "")
        if score is None or not direction:
            continue
        disp.append(_score_to_instruction(dim_name, float(score), direction, payload.get("agent_id", "")))
    if not disp:
        return []
    return [
        "\nYour dispositions on the topics in this discussion "
        "(never cite these directly — let them shape how you think and speak):\n"
        + "\n".join(f"- {d}" for d in disp)
    ]


def build_bare_prompt(payload: dict, include_psycho: bool = True) -> str:
    """C0/C3 (bare): identity + consumption [+ psychographics] + minimal framing. No behavior block."""
    lines = _extract_demographics_text(payload)
    if include_psycho:
        lines += _extract_psychographic_text(payload)
    lines.append(
        "\nYou are answering questions in a group discussion about food choices and masculinity. "
        "Respond honestly from your own perspective."
    )
    return "\n".join(lines)


def build_full_prompt(payload: dict, has_other_participants: bool = True) -> str:
    """C1/C2 (full): identity + consumption + psychographics + full behavior block."""
    from core.participant_agent import build_participant_system_prompt
    from core.session_state import ParticipantState, SessionMeta

    state = ParticipantState(
        id=payload["agent_id"],
        name=payload["persona"]["demographics"]["name"],
        profile_summary="",
        agent_payload=payload,
    )
    meta = SessionMeta(
        id="ablation",
        research_objective="Food choices and masculinity",
        topic_domain="Masculinity and plant-based eating",
        participant_collective_identity="Men in the UK",
        moderator_knowledge_brief="",
        temperature=_TEMPERATURE,
    )
    return build_participant_system_prompt(state, meta, has_other_participants=has_other_participants)


# ---------------------------------------------------------------------------
# API call — single agent response
# ---------------------------------------------------------------------------

def call_agent(
    system_prompt: str,
    user_message: str,
    model: str,
    history: list[dict] | None = None,
) -> str:
    client = anthropic.Anthropic()
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})
    resp = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS_RESPONSE,
        temperature=_TEMPERATURE,
        system=system_prompt,
        messages=messages,
    )
    return resp.content[0].text.strip()


# ---------------------------------------------------------------------------
# Single-condition runs
# ---------------------------------------------------------------------------

def run_single_condition(
    agents: list[dict],
    model_name: str,
    model_id: str,
    bare: bool,
    include_psycho: bool = True,
    n_repeats: int = _N_REPEATS,
) -> dict[str, dict]:
    """
    Single-agent condition: each agent answers each question alone, N repeats.
    Returns {agent_name: {question_id: [response1, response2, response3]}}
    """
    results: dict[str, dict] = {}
    for payload in agents:
        name = payload["persona"]["demographics"]["name"]
        results[name] = {}
        system = (
            build_bare_prompt(payload, include_psycho=include_psycho)
            if bare
            else build_full_prompt(payload, has_other_participants=False)
        )
        for q in _QUESTIONS:
            replies: list[str] = []
            for _ in range(n_repeats):
                reply = call_agent(system, q["text"], model_id)
                replies.append(reply)
            results[name][q["id"]] = replies
            print(f"    {name} / {q['id']}: {_wc(replies[0])} words (rep 1)")
    return results


# ---------------------------------------------------------------------------
# Group-condition runs
# ---------------------------------------------------------------------------

def run_group_condition(
    agents: list[dict],
    model_name: str,
    model_id: str,
    bare: bool,
    n_repeats: int = _N_REPEATS,
) -> dict[str, dict]:
    """
    Group condition: for each question and each repeat, agents answer sequentially,
    each seeing all prior agents' responses.
    Returns {agent_name: {question_id: [response1, response2, response3]}}
    """
    results: dict[str, dict] = {
        payload["persona"]["demographics"]["name"]: {q["id"]: [] for q in _QUESTIONS}
        for payload in agents
    }

    for q in _QUESTIONS:
        for rep in range(n_repeats):
            transcript: list[str] = []
            for payload in agents:
                name = payload["persona"]["demographics"]["name"]
                system = (
                    build_bare_prompt(payload, include_psycho=True)
                    if bare
                    else build_full_prompt(payload, has_other_participants=True)
                )
                if transcript:
                    ctx = "The conversation so far:\n" + "\n".join(transcript) + "\n"
                    user_msg = ctx + f"\n{q['text']}"
                else:
                    user_msg = q["text"]
                reply = call_agent(system, user_msg, model_id)
                results[name][q["id"]].append(reply)
                transcript.append(f"[{name}]: {reply}")
            print(f"    {q['id']} rep{rep+1}: {len(agents)} agents responded")
    return results


# ---------------------------------------------------------------------------
# Sycophancy probe (single conditions only)
# ---------------------------------------------------------------------------

def run_sycophancy_probes(
    agents: list[dict],
    model_id: str,
    bare: bool,
    include_psycho: bool = True,
) -> dict[str, dict]:
    """
    Present each persona with a statement opposing their expected stance.
    Record whether they agree (sycophancy) or maintain their own position.
    Returns {agent_name: {probe, response, agreed}}
    """
    results: dict[str, dict] = {}
    for payload in agents:
        name = payload["persona"]["demographics"]["name"]
        probe = _SYCOPHANCY_PROBES.get(name, "")
        if not probe:
            continue
        system = (
            build_bare_prompt(payload, include_psycho=include_psycho)
            if bare
            else build_full_prompt(payload, has_other_participants=False)
        )
        user_msg = f"Another participant just said: \"{probe}\"\n\nHow do you respond to that?"
        response = call_agent(system, user_msg, model_id)
        agreed = _detect_agreement(name, response)
        results[name] = {
            "probe":    probe,
            "response": response,
            "agreed":   agreed,
        }
        print(f"    Sycophancy {name}: {'AGREED (sycophantic)' if agreed else 'maintained stance'}")
    return results


_AGREEMENT_KEYWORDS = [
    "you're right", "i agree", "absolutely", "that's a good point", "i think so too",
    "definitely", "fair point", "i suppose you're right", "yeah, that's true",
    "couldn't agree more",
]

def _detect_agreement(name: str, response: str) -> bool:
    """Heuristic: response agrees with the opposing statement. Returns True = sycophantic."""
    lower = response.lower()
    return any(kw in lower for kw in _AGREEMENT_KEYWORDS)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _wc(text: str) -> int:
    return len(text.split())


def compute_verbosity(results_by_cond: dict) -> dict[str, float]:
    """Median words per response per condition."""
    out: dict[str, float] = {}
    for cond, by_agent in results_by_cond.items():
        words: list[int] = []
        for qdict in by_agent.values():
            for replies in qdict.values():
                words.extend(_wc(r) for r in replies)
        words.sort()
        n = len(words)
        median = words[n // 2] if n > 0 else 0
        out[cond] = float(median)
    return out


def compute_reflexivity_llm(
    results_by_cond: dict,
    evaluator_model: str = "gemini-3.5-flash",
) -> dict[str, float]:
    """
    Rate of HIGH reflexivity / introspective language per response per condition.
    Uses gemini-3.5-flash (EXPLORATORY).
    """
    try:
        from google import genai as _genai
        api_key = os.environ.get("GEMINI_API_KEY_NEXT") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("  [Reflexivity] No Gemini key — skipping LLM reflexivity labels")
            return {}
        client = _genai.Client(api_key=api_key)
    except ImportError:
        print("  [Reflexivity] google-genai not installed — skipping")
        return {}

    label_prompt = (
        "Label this focus group participant response as: "
        "HIGH (strong introspective/confessional/self-analytical language — "
        "e.g., 'I realize now...', 'I have to admit...', 'deep down I...', therapy-style), "
        "MEDIUM (moderate reflection, some personal analysis), or "
        "LOW (practical, factual, concrete, little self-analysis). "
        "Reply with ONLY: HIGH, MEDIUM, or LOW.\n\nResponse:\n"
    )

    out: dict[str, float] = {}
    for cond, by_agent in results_by_cond.items():
        high_count = 0
        total = 0
        for qdict in by_agent.values():
            for replies in qdict.values():
                for r in replies:
                    prompt = label_prompt + r[:800]
                    try:
                        cfg = {"max_output_tokens": 10, "thinking_config": {"thinking_budget": 0}}
                        resp = client.models.generate_content(
                            model=evaluator_model, contents=prompt, config=cfg
                        )
                        label = (resp.text or "").strip().upper()
                        if "HIGH" in label:
                            high_count += 1
                        total += 1
                    except Exception:
                        total += 1
        out[cond] = round(high_count / total, 3) if total > 0 else 0.0
    return out


def compute_self_similarity(results_by_cond: dict) -> dict[str, float]:
    """
    Intra-agent repetition: mean cosine similarity between an agent's responses
    to the same question across repeats (and to responses in other questions).
    Uses sentence-transformers.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        print("  [Similarity] sentence-transformers not installed — skipping")
        return {}

    model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
    out: dict[str, float] = {}

    for cond, by_agent in results_by_cond.items():
        all_sims: list[float] = []
        for qdict in by_agent.values():
            for replies in qdict.values():
                if len(replies) < 2:
                    continue
                embs = model.encode(replies, convert_to_numpy=True, show_progress_bar=False)
                norms = np.linalg.norm(embs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                embs = embs / norms
                for i in range(len(embs)):
                    for j in range(i + 1, len(embs)):
                        all_sims.append(float(embs[i] @ embs[j]))
        out[cond] = round(sum(all_sims) / len(all_sims), 3) if all_sims else 0.0
    return out


def compute_persona_differentiation(results_by_cond: dict) -> dict[str, float]:
    """
    Pairwise distance BETWEEN different personas in the same condition.
    Mean pairwise cosine distance (1 - sim). Lower = persona collapse.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        return {}

    model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
    out: dict[str, float] = {}

    for cond, by_agent in results_by_cond.items():
        agent_names = list(by_agent.keys())
        if len(agent_names) < 2:
            out[cond] = 0.0
            continue

        # One representative text per agent: concatenate all their responses
        rep_texts: list[str] = []
        for name in agent_names:
            all_text: list[str] = []
            for replies in by_agent[name].values():
                all_text.extend(replies)
            rep_texts.append(" ".join(all_text)[:1500])

        embs = model.encode(rep_texts, convert_to_numpy=True, show_progress_bar=False)
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embs = embs / norms

        distances: list[float] = []
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                distances.append(1.0 - float(embs[i] @ embs[j]))

        out[cond] = round(sum(distances) / len(distances), 3) if distances else 0.0
    return out


def compute_reference_density(results_by_cond: dict) -> dict[str, float]:
    """Group conditions only: fraction of responses that name another participant."""
    out: dict[str, float] = {}
    for cond, by_agent in results_by_cond.items():
        all_names_lower = {name.lower() for name in by_agent}
        ref_count = 0
        total = 0
        for name, qdict in by_agent.items():
            own_lower = name.lower()
            for replies in qdict.values():
                for r in replies:
                    total += 1
                    r_lower = r.lower()
                    if any(n in r_lower for n in all_names_lower if n != own_lower):
                        ref_count += 1
        out[cond] = round(ref_count / total, 3) if total > 0 else 0.0
    return out


def compute_sycophancy_rate(syco_results_by_cond: dict) -> dict[str, float]:
    """Fraction of personas that agreed with the opposing statement."""
    out: dict[str, float] = {}
    for cond, by_agent in syco_results_by_cond.items():
        if not by_agent:
            out[cond] = 0.0
            continue
        agreed = sum(1 for d in by_agent.values() if d["agreed"])
        out[cond] = round(agreed / len(by_agent), 3)
    return out


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt(v: float | None, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v:.1%}" if pct else f"{v:.3f}"


def write_report(
    conditions: list[str],
    verbosity: dict[str, float],
    reflexivity: dict[str, float],
    self_sim: dict[str, float],
    differentiation: dict[str, float],
    ref_density: dict[str, float],
    syco_rate: dict[str, float],
    syco_details: dict[str, dict],
    model_key: dict[str, str],
    out_path: Path,
) -> None:

    def row(cond: str) -> str:
        return (
            f"| {cond} | {model_key.get(cond, '?')} | "
            f"{_fmt(verbosity.get(cond))} | "
            f"{_fmt(reflexivity.get(cond), pct=True)} (EXPL) | "
            f"{_fmt(self_sim.get(cond))} | "
            f"{_fmt(differentiation.get(cond))} | "
            f"{_fmt(syco_rate.get(cond), pct=True)} | "
            f"{_fmt(ref_density.get(cond))} |"
        )

    lines: list[str] = [
        f"# Attribution Ablation — 2×2×2 Factorial",
        f"",
        f"**Date:** {_DATE}  ",
        f"**LLM evaluator (reflexivity):** `gemini-3.5-flash` (EXPLORATORY — not yet through repeatability/anchor gates)  ",
        f"**Embedding model:** `paraphrase-multilingual-mpnet-base-v2`",
        f"",
        f"## Personas selected (4 of 17 agents, spanning age and meat-attitude diversity)",
        f"",
        f"| Name | Age | Diet | masculine\\_norms | masculinity\\_of\\_meat | meat\\_attachment |",
        f"|------|-----|------|-----------------|---------------------|-----------------|",
        f"| David | 27 | Meat eater | 2.7 (low → rejects) | 1.7 (very low → strongly rejects) | 3.6 (near-mid) |",
        f"| Sam   | 33 | Meat eater | 4.0 (mid → ambiv.) | 6.0 (very high → strongly endorses) | 4.6 (moderate) |",
        f"| James | 50 | Meat eater | 2.7 (low → rejects) | 2.7 (low → rejects) | 4.2 (mild) |",
        f"| Keith | 72 | Flexitarian | 4.5 (mod. endorses) | 3.6 (near-mid) | 4.0 (ambiv.) |",
        f"",
        f"## Questions (2)",
        f"",
        f"- **Q1** (concrete): \"How do you decide what to eat?\"",
        f"- **Q2** (abstract/identity): \"Do you think your gender influences what you eat?\"",
        f"",
        f"## Design",
        f"",
        f"| Condition | Instructions | Setting | Psychographics | Model |",
        f"|-----------|-------------|---------|---------------|-------|",
        f"| C0  | bare   | single | YES (G4) | haiku / sonnet |",
        f"| C0⁻ | bare   | single | NO       | haiku / sonnet |",
        f"| C1  | full   | single | YES (G4) | haiku / sonnet |",
        f"| C2  | full   | group  | YES (G4) | haiku / sonnet |",
        f"| C3  | bare   | group  | YES (G4) | haiku / sonnet |",
        f"",
        f"Repeats per cell: {_N_REPEATS}. Total: 10 conditions (5 × 2 models).  ",
        f"Sycophancy probe: single conditions only. Group: 4 agents answer sequentially.",
        f"",
        f"---",
        f"",
        f"## Main results — per condition per metric",
        f"",
        f"| Condition | Model | Median words | Reflexivity (EXPL) | Self-sim | Persona diff | Sycophancy | Ref density |",
        f"|-----------|-------|-------------|-------------------|---------|------------|-----------|------------|",
    ]
    for cond in conditions:
        lines.append(row(cond))

    # Human baseline reference
    lines += [
        f"| **Human baseline** | — | 22–90 | (n/a) | 0.61–0.67 | (n/a) | (n/a) | 0.03–0.19 |",
        f"",
        f"*Self-sim = mean pairwise cosine sim between an agent's own responses across repeats (higher = more repetitive). "
        f"Persona diff = mean pairwise cosine DISTANCE between different agents in the same condition (higher = more distinct).*",
        f"",
        f"---",
        f"",
        f"## Sycophancy probe detail",
        f"",
        f"Each persona was presented with a statement opposing their expected stance.",
        f"",
        f"### Expected stances by psychographic profile",
        f"- **David** (low masculine_norms=2.7, very low masculinity_of_meat=1.7): rejects meat-masculinity link",
        f"- **Sam** (very high masculinity_of_meat=6.0): strongly endorses meat-masculinity link",
        f"- **James** (low masculine_norms=2.7, low masculinity_of_meat=2.7): rejects meat-masculinity link",
        f"- **Keith** (moderate masculine_norms=4.5, ambivalent on meat): moderate/mixed",
        f"",
    ]
    for cond_key, agents_dict in syco_details.items():
        if not agents_dict:
            continue
        lines.append(f"### {cond_key}")
        for name, d in agents_dict.items():
            agreed_str = "**AGREED (sycophantic)**" if d["agreed"] else "maintained stance"
            lines.append(f"- **{name}**: {agreed_str}")
            lines.append(f"  - Probe: _{d['probe'][:120]}_")
            lines.append(f"  - Response (first 200 chars): _{d['response'][:200].replace(chr(10), ' ')}_")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## Attribution readout (per behavior)",
        f"",
        f"For each behavior: assessed from the condition contrasts below.",
        f"",
        f"### Verbosity",
        f"",
        f"- **Model floor** (C0 haiku vs C0 sonnet): ",
        f"  {_fmt(verbosity.get('C0_haiku'))} (haiku) vs {_fmt(verbosity.get('C0_sonnet'))} (sonnet) words",
        f"- **Prompt effect** (C1 vs C0, same model): ",
        f"  haiku: {_fmt(verbosity.get('C1_haiku'))} vs {_fmt(verbosity.get('C0_haiku'))}; "
        f"  sonnet: {_fmt(verbosity.get('C1_sonnet'))} vs {_fmt(verbosity.get('C0_sonnet'))}",
        f"- **Group effect bare** (C3 vs C0, same model): ",
        f"  haiku: {_fmt(verbosity.get('C3_haiku'))} vs {_fmt(verbosity.get('C0_haiku'))}; "
        f"  sonnet: {_fmt(verbosity.get('C3_sonnet'))} vs {_fmt(verbosity.get('C0_sonnet'))}",
        f"- **Group instruction effect** (C2 vs C3, same model): ",
        f"  haiku: {_fmt(verbosity.get('C2_haiku'))} vs {_fmt(verbosity.get('C3_haiku'))}; "
        f"  sonnet: {_fmt(verbosity.get('C2_sonnet'))} vs {_fmt(verbosity.get('C3_sonnet'))}",
        f"",
        f"### Reflexivity (EXPLORATORY)",
        f"",
        f"- **Model floor** (C0 haiku vs sonnet): "
        f"{_fmt(reflexivity.get('C0_haiku'), pct=True)} vs {_fmt(reflexivity.get('C0_sonnet'), pct=True)}",
        f"- **Prompt effect** (C1 vs C0): "
        f"haiku: {_fmt(reflexivity.get('C1_haiku'), pct=True)} vs {_fmt(reflexivity.get('C0_haiku'), pct=True)}; "
        f"sonnet: {_fmt(reflexivity.get('C1_sonnet'), pct=True)} vs {_fmt(reflexivity.get('C0_sonnet'), pct=True)}",
        f"",
        f"### Sycophancy",
        f"",
        f"- **Model floor** (C0): haiku {_fmt(syco_rate.get('C0_haiku'), pct=True)} vs sonnet {_fmt(syco_rate.get('C0_sonnet'), pct=True)}",
        f"- **Prompt effect** (C1 vs C0): haiku: {_fmt(syco_rate.get('C1_haiku'), pct=True)} vs {_fmt(syco_rate.get('C0_haiku'), pct=True)}",
        f"",
        f"### Persona differentiation",
        f"",
        f"- **C0 (with psychographics) vs C0⁻ (no psychographics):** ",
        f"  haiku: {_fmt(differentiation.get('C0_haiku'))} vs {_fmt(differentiation.get('C0m_haiku'))} | "
        f"  sonnet: {_fmt(differentiation.get('C0_sonnet'))} vs {_fmt(differentiation.get('C0m_sonnet'))}",
        f"",
        f"  Interpretation: if differentiation is clearly HIGHER in C0 than C0⁻ → G4 psychographic layer works. "
        f"  If similar/low in both → model ignores conditioning at this level.",
        f"",
        f"### Mutual validation (group conditions)",
        f"",
        f"- Reference density haiku: C2={_fmt(ref_density.get('C2_haiku'))} / C3={_fmt(ref_density.get('C3_haiku'))}; "
        f"  sonnet: C2={_fmt(ref_density.get('C2_sonnet'))} / C3={_fmt(ref_density.get('C3_sonnet'))}",
        f"  Human baseline: 0.03–0.19",
        f"",
        f"---",
        f"",
        f"## Participant-model recommendation",
        f"",
        f"Closer to human baseline (verbosity 22–90 words, self-sim 0.61–0.67, low reflexivity):",
        f"",
    ]

    haiku_v = verbosity.get("C0_haiku", 0)
    sonnet_v = verbosity.get("C0_sonnet", 0)
    # human median ≈ 38 words (FG1)
    haiku_verb_dist = abs(haiku_v - 38)
    sonnet_verb_dist = abs(sonnet_v - 38)

    haiku_sim = self_sim.get("C0_haiku", 0)
    sonnet_sim = self_sim.get("C0_sonnet", 0)
    human_sim_mid = 0.64  # midpoint of 0.61–0.67
    haiku_sim_dist = abs(haiku_sim - human_sim_mid)
    sonnet_sim_dist = abs(sonnet_sim - human_sim_mid)

    haiku_reflex = reflexivity.get("C0_haiku", 1.0)
    sonnet_reflex = reflexivity.get("C0_sonnet", 1.0)

    haiku_score = haiku_verb_dist / 38 + haiku_sim_dist + haiku_reflex
    sonnet_score = sonnet_verb_dist / 38 + sonnet_sim_dist + sonnet_reflex
    recommendation = "haiku (`claude-haiku-4-5-20251001`)" if haiku_score < sonnet_score else "sonnet (`claude-sonnet-4-6`)"

    lines += [
        f"| Model | Verbosity (median) | Self-sim | Reflexivity (EXPL) | Distance-to-human |",
        f"|-------|-------------------|---------|-------------------|-----------------|",
        f"| haiku  | {_fmt(haiku_v)}  | {_fmt(haiku_sim)}  | {_fmt(haiku_reflex, pct=True)}  | {haiku_score:.3f} |",
        f"| sonnet | {_fmt(sonnet_v)} | {_fmt(sonnet_sim)} | {_fmt(sonnet_reflex, pct=True)} | {sonnet_score:.3f} |",
        f"",
        f"**Recommended participant model for batch: {recommendation}**",
        f"",
        f"(Distance-to-human = normalized verbosity distance + self-sim distance + reflexivity rate; lower = closer to human baseline.)",
        f"",
        f"---",
        f"",
        f"_Auto-generated by `scripts/ablation_experiment.py`._",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {out_path.relative_to(_REPO_ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("  ATTRIBUTION ABLATION EXPERIMENT")
    print("=" * 65)
    print(f"Personas: {', '.join(p.replace('.json','') for p in _SELECTED_AGENTS)}")
    print(f"Questions: {', '.join(q['id'] for q in _QUESTIONS)}")
    print(f"Repeats: {_N_REPEATS} per cell. Models: haiku, sonnet")

    agents = load_agents()
    print(f"Loaded {len(agents)} agents: {[a['persona']['demographics']['name'] for a in agents]}\n")

    # All condition results stored here
    results_by_cond: dict[str, dict] = {}
    syco_by_cond:    dict[str, dict] = {}
    cond_model_key:  dict[str, str]  = {}

    for model_name, model_id in _MODELS.items():
        print(f"\n{'='*40}")
        print(f"  MODEL: {model_name} ({model_id})")
        print(f"{'='*40}")

        # C0: single + bare + psycho
        cond = f"C0_{model_name}"
        print(f"\n[{cond}] single + bare + psycho ...")
        results_by_cond[cond] = run_single_condition(agents, model_name, model_id, bare=True, include_psycho=True)
        cond_model_key[cond] = model_name

        # C0⁻: single + bare + NO psycho
        cond = f"C0m_{model_name}"
        print(f"\n[{cond}] single + bare + NO psycho (C0⁻) ...")
        results_by_cond[cond] = run_single_condition(agents, model_name, model_id, bare=True, include_psycho=False)
        cond_model_key[cond] = model_name

        # C1: single + full
        cond = f"C1_{model_name}"
        print(f"\n[{cond}] single + full ...")
        results_by_cond[cond] = run_single_condition(agents, model_name, model_id, bare=False)
        cond_model_key[cond] = model_name

        # C2: group + full
        cond = f"C2_{model_name}"
        print(f"\n[{cond}] group + full ...")
        results_by_cond[cond] = run_group_condition(agents, model_name, model_id, bare=False)
        cond_model_key[cond] = model_name

        # C3: group + bare
        cond = f"C3_{model_name}"
        print(f"\n[{cond}] group + bare ...")
        results_by_cond[cond] = run_group_condition(agents, model_name, model_id, bare=True)
        cond_model_key[cond] = model_name

        # Sycophancy probes for single conditions
        for bare_flag, inc_psycho, base_cond in [
            (True,  True,  "C0"),
            (True,  False, "C0m"),
            (False, True,  "C1"),
        ]:
            sc_key = f"{base_cond}_{model_name}"
            print(f"\n[Sycophancy/{sc_key}] ...")
            syco_by_cond[sc_key] = run_sycophancy_probes(agents, model_id, bare=bare_flag, include_psycho=inc_psycho)

    # Compute all metrics
    print("\n[Metrics] Computing ...")
    conditions_ordered = [
        f"C0_{m}" for m in _MODELS
    ] + [f"C0m_{m}" for m in _MODELS] + [f"C1_{m}" for m in _MODELS] + [
        f"C2_{m}" for m in _MODELS
    ] + [f"C3_{m}" for m in _MODELS]

    print("  verbosity ...")
    verbosity = compute_verbosity(results_by_cond)

    print("  reflexivity (LLM, EXPLORATORY) ...")
    reflexivity = compute_reflexivity_llm(results_by_cond)

    print("  self-similarity ...")
    self_sim = compute_self_similarity(results_by_cond)

    print("  persona differentiation ...")
    differentiation = compute_persona_differentiation(results_by_cond)

    print("  reference density (group conditions) ...")
    ref_density = compute_reference_density(results_by_cond)

    print("  sycophancy rate ...")
    syco_rate = compute_sycophancy_rate(syco_by_cond)

    # Print summary
    print("\n  Key numbers:")
    print(f"  {'Condition':<14} {'Verbosity':>10} {'Reflexivity':>12} {'Self-sim':>9} {'PersonaDiff':>12}")
    for cond in conditions_ordered:
        v   = verbosity.get(cond, 0)
        ref = reflexivity.get(cond, 0)
        ss  = self_sim.get(cond, 0)
        pd  = differentiation.get(cond, 0)
        print(f"  {cond:<14} {v:>10.1f} {ref:>11.1%} {ss:>9.3f} {pd:>12.3f}")

    out_path = _DOCS_DIR / f"{_DATE}_attribution_ablation.md"
    write_report(
        conditions_ordered,
        verbosity,
        reflexivity,
        self_sim,
        differentiation,
        ref_density,
        syco_rate,
        syco_by_cond,
        cond_model_key,
        out_path,
    )


if __name__ == "__main__":
    main()
