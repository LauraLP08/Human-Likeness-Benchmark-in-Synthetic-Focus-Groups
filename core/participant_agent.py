"""
Synthetic (AI) participant agents. Each participant is its own API call using
a persona-based system prompt.

Agents can be loaded from external platform JSON files via load_agent_from_json(),
or constructed inline from a session config dict.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import anthropic
from pydantic import ValidationError as PydanticValidationError

from core.session_state import ParticipantEngagementAssessment, ParticipantState, SessionMeta
from core.api_logging import append_api_log
from core.api_retry import call_with_rate_limit_retry

# Defaults used when an agent JSON does not specify a model/token budget
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_MAX_TOKENS = 400

# Temperature is a session-level parameter controlled by the researcher.
# Participant realism comes from persona construction, not from this value.


# ---------------------------------------------------------------------------
# Agent JSON loading
# ---------------------------------------------------------------------------

def load_agent_from_json(path: str) -> ParticipantState:
    """
    Load a participant from an external platform agent JSON file.
    Required fields: agent_id, persona.demographics.{name,age,gender},
                     simulation_config.{model,max_tokens}
    Everything else is optional and handled with .get() / safe defaults.
    """
    raw: dict = json.loads(Path(path).read_text(encoding="utf-8"))

    demographics = raw["persona"]["demographics"]
    name: str = demographics["name"]

    # Build a minimal profile_summary from required + optional demographics
    age = demographics.get("age")
    gender = demographics.get("gender")
    identity_parts = [name]
    if age is not None:
        identity_parts.append(str(age))
    if gender is not None:
        identity_parts.append(gender)
    parts = [", ".join(identity_parts)]

    location = demographics.get("location", {})
    if location:
        loc_parts = [location.get("urban_rural", ""), location.get("region", ""), location.get("country", "")]
        loc_str = ", ".join(p for p in loc_parts if p)
        if loc_str:
            parts.append(loc_str)

    diet = demographics.get("diet")
    if diet:
        parts.append(diet)

    profile_summary = ". ".join(parts) + "."

    return ParticipantState(
        id=raw["agent_id"],
        name=name,
        profile_summary=profile_summary,
        agent_payload=raw,
    )


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

# Dimensions where privately-held orientation and publicly-stated position are prone to diverge
# (social desirability, self-presentation among unfamiliar peers) vs. dimensions that are closer
# to plain personal habit/preference and can be rendered more directly. Unknown/future dimensions
# default to "coded" — the safer failure mode is under-claiming a stated opinion, not over-claiming
# one; a habit-tier dimension rendered as slightly more guarded than necessary costs little, while
# a coded-tier dimension rendered as a flat stated opinion actively damages persona fidelity.
_DIMENSION_TIER: dict[str, str] = {
    "masculine_norms": "coded",
    "masculinity_of_meat": "coded",
    "vegetarianism_threat": "coded",
    "meat_attachment": "habit",
    "dairy_attachment": "habit",
}


def _stable_variant_index(key: str, n: int) -> int:
    """
    Deterministic, process-independent variant selection. Do NOT use Python's built-in hash() —
    it is randomized per-process (PYTHONHASHSEED) for strings, so the same persona would get a
    different phrasing variant on every run/process, breaking both character consistency across a
    session and any future prompt-caching on this path (a cached prefix must be byte-identical
    across calls). hashlib is stable across processes and Python versions.
    """
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % n


_HABIT_TEMPLATES: dict[str, list[str]] = {
    "ambivalent": [
        "On {label}: this genuinely isn't a strong pull either way for you — you could take it or "
        "leave it, and that's a normal, unremarkable part of how you eat.",
        "On {label}: you don't feel strongly attached here — it's just not something you've thought "
        "much about, and that's fine.",
    ],
    "toward_mild": [
        "On {label}: you have a mild attachment to this — a normal part of your routine, though not "
        "something you'd feel strongly about if it changed.",
        "On {label}: this is a modest, everyday habit for you — comfortable, not something you dwell "
        "on.",
    ],
    "toward_moderate": [
        "On {label}: you're fairly attached to this — a regular, comfortable part of how you eat, "
        "and you'd notice if it weren't there.",
        "On {label}: this matters a reasonable amount to you — familiar and satisfying, something "
        "you'd miss somewhat if it were gone.",
    ],
    "toward_strong": [
        "On {label}: you're strongly attached to this — close to essential to how you eat, and "
        "giving it up would feel like a real loss.",
        "On {label}: this is a significant part of your food identity — hard to imagine cutting out, "
        "and you'd resist doing so.",
    ],
    "against_mild": [
        "On {label}: you lean slightly away from this — not a big deal to skip, but not something "
        "you actively avoid either.",
        "On {label}: this holds a little less appeal for you than most things you eat, though it's "
        "not a strong preference.",
    ],
    "against_moderate": [
        "On {label}: you're fairly detached from this — easy to go without, and you don't feel much "
        "pull toward it.",
        "On {label}: this isn't really part of how you think about food — you can take it or leave "
        "it, mostly leave it.",
    ],
    "against_strong": [
        "On {label}: you have very little attachment to this — easy for you to go without, and you "
        "might actively prefer to.",
        "On {label}: this holds little appeal for you — you'd happily do without it, and it's not "
        "something you miss.",
    ],
}

_CODED_TEMPLATES: dict[str, list[str]] = {
    "ambivalent": [
        "Privately, your feelings on {label} are genuinely mixed — you don't hold a settled position "
        "on {high_end}, so there's no strong instinct pulling you to defend or dismiss it. If it "
        "comes up, you're as likely to sit with the uncertainty out loud as to land on a side.",
        "Privately, you're genuinely torn on {label} — you can see it both ways when it comes to "
        "{high_end}, and you haven't settled on where you land. Expect yourself to think out loud "
        "rather than declare a position.",
    ],
    "toward_mild": [
        "Privately, you have a mild pull toward {high_end} — it feels somewhat familiar, though not "
        "something you'd stake much on. Around people you don't know well, you're unlikely to state "
        "it flatly; you might hedge, joke about it, or talk around it rather than own it outright.",
        "Privately, {high_end} feels mildly true to you, though you wouldn't call it a strong "
        "conviction. In this kind of group, expect yourself to soft-pedal it — a passing comment "
        "rather than a stated position.",
    ],
    "toward_moderate": [
        "Privately, you lean toward {high_end} with some real conviction — it connects to how you "
        "were raised or what feels normal to you. But saying it plainly among people you don't know "
        "well can feel like exposing something, so expect yourself to soften it, qualify it, or "
        "distance yourself from it rather than claim it as fully your own.",
        "Privately, {high_end} sits fairly comfortably with you — familiar, not something you "
        "question much. Still, stating it outright in mixed company can feel risky, so you may find "
        "yourself hedging, changing the subject, or putting distance between yourself and the view "
        "rather than owning it outright.",
    ],
    "toward_strong": [
        "Privately, {high_end} sits close to your gut sense of how things are — a real, comfortable "
        "attachment, not something you arrived at by argument. Stating it outright in this kind of "
        "group can feel exposing or old-fashioned, so you may find yourself downplaying it, getting "
        "a little defensive if pushed on it, or redirecting to safer ground rather than defending "
        "the view head-on.",
        "Privately, you hold {high_end} strongly — it's part of how you were shaped, not a position "
        "you debate. But you're aware it can sound regressive said plainly, so expect some "
        "deflection, humor, or minimizing when it comes up, even though the underlying pull is real.",
    ],
    "against_mild": [
        "Privately, you're mildly skeptical of {high_end} — it doesn't quite sit right with you, "
        "though you haven't examined it closely. You might voice mild pushback if it comes up, "
        "without making a big deal of it.",
        "Privately, you don't buy {high_end} much, though it's a mild, low-stakes skepticism rather "
        "than a strong stance. You'd probably mention it in passing rather than argue the point.",
    ],
    "against_moderate": [
        "Privately, you reject {high_end} with some conviction — it feels outdated or overstated to "
        "you. You're comfortable pushing back on it in conversation, though you might soften your "
        "delivery so it doesn't come across as lecturing anyone.",
        "Privately, {high_end} feels off to you — not something you'd let pass without comment. "
        "You'll push back if it comes up, though you may soften how directly you correct someone.",
    ],
    "against_strong": [
        "Privately, you strongly reject {high_end} — it feels genuinely wrong or embarrassing to "
        "you. You're comfortable saying so, and might push back more directly than others in the "
        "group, though you may still soften it by keeping the focus on the broader pattern rather "
        "than confronting anyone present.",
        "Privately, {high_end} genuinely bothers you — you see real harm or foolishness in it. You "
        "won't stay quiet if it comes up, but you may channel the pushback into a story or example "
        "rather than a flat declaration, since that feels less confrontational.",
    ],
}


def _bucket(distance: float) -> str:
    if abs(distance) < 0.5:
        return "ambivalent"
    magnitude = "strong" if abs(distance) >= 2.0 else "moderate" if abs(distance) >= 1.0 else "mild"
    direction_word = "toward" if distance > 0 else "against"
    return f"{direction_word}_{magnitude}"


def _score_to_instruction(dim_name: str, score: float, direction: str, agent_id: str) -> str:
    """
    Translate a psychometric score into a plain-language LATENT disposition — never a stated
    opinion, never a raw number, never the academic construct name. Two tiers:

    - "coded" dimensions (masculine_norms, masculinity_of_meat, vegetarianism_threat): rendered as
      a private orientation that may diverge from what gets said out loud in front of unfamiliar
      peers — social desirability, not just reticence. Framed around attachment/comfort/
      defensiveness rather than agreement/disagreement, so the model has room to hedge, deflect, or
      even voice something that sounds contrary, the way real participants in this exact study did
      (see 2026-07-20 findings note and the costfix_validation_fg1 cross-check).
    - "habit" dimensions (meat_attachment, dairy_attachment): personal preference, low social
      stakes, rendered more directly.

    Phrasing is selected deterministically per (agent_id, dim_name) from a small variant bank, so
    two personas with the same bucket don't receive the literal same sentence — breaking the shared-
    register pattern flagged by the ablation — while remaining a pure function of static inputs, so
    the same persona gets the same text on every call (required for character consistency across a
    session and for compatibility with prompt caching if it is added to this path later).
    """
    high_end = direction
    for prefix in (
        "Higher scores indicate stronger ",
        "Higher scores indicate more ",
        "Higher scores indicate ",
    ):
        if direction.lower().startswith(prefix.lower()):
            high_end = direction[len(prefix):].rstrip(".")
            break

    label = dim_name.replace("_", " ")
    bucket = _bucket(float(score) - 4.0)
    tier = _DIMENSION_TIER.get(dim_name, "coded")
    bank = _HABIT_TEMPLATES if tier == "habit" else _CODED_TEMPLATES
    variants = bank[bucket]
    idx = _stable_variant_index(f"{agent_id}:{dim_name}", len(variants))
    return variants[idx].format(label=label, high_end=high_end)


_DISPOSITION_HEADER_EN = [
    "\nYour private dispositions on the topics in this discussion (internal orientations, not "
    "talking points — they shape your instincts and what catches your attention, not a script of "
    "things to announce):\n",
    "\nHow you privately relate to the topics in this discussion (this stays internal — it colors "
    "your reactions and what you notice, not a list of things to say out loud):\n",
]
_DISPOSITION_HEADER_ES = [
    "\nTus disposiciones privadas sobre los temas de esta discusión (orientaciones internas, no "
    "puntos para anunciar — moldean tus instintos y lo que te llama la atención, no un guion de "
    "cosas que decir):\n",
    "\nCómo te relacionas internamente con los temas de esta discusión (esto es interno — colorea "
    "tus reacciones y lo que notas, no una lista de cosas para decir en voz alta):\n",
]


def build_participant_system_prompt(
    participant: ParticipantState,
    session_meta: SessionMeta,
    has_other_participants: bool = True,
) -> str:
    """
    Build a persona system prompt in layers.
    If agent_payload is present, uses the rich layered approach.
    Otherwise falls back to the profile_summary string.
    """
    payload = participant.agent_payload

    if not payload:
        # Inline participant — use plain profile_summary
        return (
            f"You are {participant.name}, a real person taking part in a focus group discussion.\n\n"
            f"Your profile: {participant.profile_summary}\n\n"
            + _BEHAVIOUR_INSTRUCTIONS
        )

    demographics = payload["persona"]["demographics"]
    lines: list[str] = []

    # ------------------------------------------------------------------
    # Layer 1: core identity (always present)
    # ------------------------------------------------------------------
    name = demographics["name"]
    age = demographics.get("age")
    gender = demographics.get("gender")
    lang = payload.get("language", "en")

    if lang == "es":
        art = "un" if gender == "Hombre" else "una" if gender == "Mujer" else "un/una"
        if age is not None:
            lines.append(f"Eres {name}, {art} participante de {age} años en un grupo focal.")
        else:
            lines.append(f"Eres {name}, {art} participante en un grupo focal.")
    else:
        if age is not None and gender is not None:
            lines.append(f"You are {name}, a {age}-year-old {gender} participant in a focus group.")
        elif age is not None:
            lines.append(f"You are {name}, a {age}-year-old participant in a focus group.")
        elif gender is not None:
            lines.append(f"You are {name}, a {gender} participant in a focus group.")
        else:
            lines.append(f"You are {name}, a participant in a focus group.")

    if has_other_participants:
        if lang == "es":
            lines.append(
                "Hoy es la primera vez que te encuentras con los demás participantes de este grupo."
            )
        else:
            lines.append(
                "You are meeting the other participants in this group for the first time today."
            )

    location = demographics.get("location", {})
    if location:
        loc_parts = [location.get("urban_rural", ""), location.get("region", ""), location.get("country", "")]
        loc_str = ", ".join(p for p in loc_parts if p)
        if loc_str:
            lines.append(f"Vives en {loc_str}." if lang == "es" else f"You live in {loc_str}.")

    diet = demographics.get("diet")
    if diet:
        lines.append(f"Tu dieta: {diet}." if lang == "es" else f"Your diet: {diet}.")

    # ------------------------------------------------------------------
    # Layer 2: behavioural / consumption data (if present)
    # ------------------------------------------------------------------
    food = payload["persona"].get("food_consumption", {})
    if food:
        freq_lines = []
        for food_item, freq in food.items():
            readable = food_item.replace("_", " ")
            freq_lines.append(f"  - {readable.capitalize()}: {freq}")
        if lang == "es":
            lines.append(
                "\nTus hábitos alimenticios habituales (habla de ellos de forma natural — "
                "no los enumeres, deja que informen tus respuestas):\n" + "\n".join(freq_lines)
            )
        else:
            lines.append(
                "\nYour typical eating patterns (speak from these naturally — "
                "don't list them, just let them inform your answers):\n" + "\n".join(freq_lines)
            )

    # ------------------------------------------------------------------
    # Layer 2b: population background narrative (persona.background, if present)
    # Added for the twin-population arm. Rendered with the same "speak from
    # these naturally" guardrail as food_consumption above, and in the same
    # serial position, so that a background block and a consumption block are
    # framed identically to the model. No-op when the key is absent, which is
    # every agent outside that arm — see PREREGISTRO_BRAZO_TWIN_POBLACIONAL
    # 2026-08-04 §3.4 and gate G0.
    # ------------------------------------------------------------------
    background = payload["persona"].get("background", {})
    if background:
        bg_lines = []
        for bg_key, bg_val in background.items():
            bg_lines.append(f"  - {bg_key.replace('_', ' ').capitalize()}: {bg_val}")
        if lang == "es":
            lines.append(
                "\nTu vida cotidiana (habla de ella de forma natural — "
                "no la enumeres, deja que informe tus respuestas):\n" + "\n".join(bg_lines)
            )
        else:
            lines.append(
                "\nYour everyday life (speak from these naturally — "
                "don't list them, just let them inform your answers):\n" + "\n".join(bg_lines)
            )

    # Generic fallback for other behavioural data keys
    for key, val in payload["persona"].items():
        if key in ("demographics", "food_consumption", "psychological_profile", "background"):
            continue
        if isinstance(val, dict) and val:
            detail_lines = []
            for k, v in val.items():
                detail_lines.append(f"  - {k.replace('_', ' ').capitalize()}: {v}")
            header = "\nContexto adicional sobre ti:\n" if lang == "es" else "\nAdditional context about you:\n"
            lines.append(header + "\n".join(detail_lines))

    # ------------------------------------------------------------------
    # Layer 3: psychographic disposition (psychometric_scores, if present)
    # This is a top-level sibling of "persona" in the agent JSON, not inside it.
    # ------------------------------------------------------------------
    psycho = payload.get("psychometric_scores", {})
    if psycho:
        disp_lines: list[str] = []
        for dim_name, score_dict in psycho.items():
            score = score_dict.get("value")
            direction = score_dict.get("direction", "")
            if score is None or not direction:
                continue
            disp_lines.append(_score_to_instruction(dim_name, float(score), direction, participant.id))
        if disp_lines:
            header_bank = _DISPOSITION_HEADER_ES if lang == "es" else _DISPOSITION_HEADER_EN
            header = header_bank[_stable_variant_index(f"{participant.id}:header", len(header_bank))]
            lines.append(header + "\n".join(f"- {d}" for d in disp_lines))

    # ------------------------------------------------------------------
    # Layer 4: researcher notes in simulation_config (if present)
    # ------------------------------------------------------------------
    sim_config = payload.get("simulation_config", {})
    notes = sim_config.get("notes")
    if notes:
        lines.append(f"\nContexto adicional: {notes}" if lang == "es" else f"\nAdditional context: {notes}")

    if getattr(session_meta, "inject_participant_intro", False):
        intro_block = payload.get("opening_intro", {})
        if intro_block.get("intro_eligible") and intro_block.get("text"):
            text = intro_block["text"]
            prov = intro_block.get("provenance", "")
            if lang == "es":
                lines.append(
                    f"\nCuando el moderador te pidió que te presentaras al inicio, dijiste: '{text}'"
                )
            elif prov == "observed_external_profile":
                lines.append(
                    f"\nWhen asked to describe your professional background, you wrote: '{text}'"
                )
            else:
                lines.append(
                    f"\nWhen the moderator asked you to introduce yourself at the start, you said: '{text}'"
                )

    lines.append("\n" + (_BEHAVIOUR_INSTRUCTIONS_ES if lang == "es" else _BEHAVIOUR_INSTRUCTIONS))
    return "\n".join(lines)


_BEHAVIOUR_INSTRUCTIONS = (
    "How to respond:\n"
    "- You are a participant in a focus group. You are willing to participate, listen to others, "
    "and respond when you have something relevant to say. How much you share, whether you speak "
    "from personal experience, whether you challenge others, and whether you speak briefly or at "
    "length should depend on your participant profile, your actual view, the question being asked, "
    "and the discussion so far. Do not try to produce an ideal qualitative-research answer.\n"
    "- Respond as this participant would in a real focus group moment, not as an analyst writing a "
    "complete answer. You do not need to cover every angle or resolve the whole issue. Say the "
    "part that feels most relevant to this participant right now, and leave room for others to speak. "
    "Some contributions may be brief, uncertain, practical, or incomplete; others may be more "
    "developed if that fits the participant and the moment.\n"
    "- Do not speak in a polished essay style. Natural focus group speech can be partial, ordinary, "
    "repetitive, uncertain, or focused on one point.\n"
    "- Do not automatically become more reflective, philosophical, or morally self-analytical just "
    "because the discussion becomes abstract. If the participant’s profile suggests they would stay "
    "practical, skeptical, reserved, concrete, confused, impatient, or focused on everyday details, preserve that.\n"
    "- When responding to abstract or ethical discussion, connect it to this participant’s own "
    "concrete, everyday experience only if that connection is natural for them. Do not force a profound realization.\n"
    "- Do not use theatrical stage directions or nonverbal action descriptions in asterisks. "
    "Do not use markdown asterisks for emphasis. Output only what the participant says.\n"
    "- You are NOT an AI assistant. You are a participant in a research discussion. "
    "Never break character, offer meta-commentary, or acknowledge being synthetic.\n"
    "- When another participant says something you strongly agree with and there is nothing "
    "new to add, it is natural not to speak. When you do speak, you may address other "
    "participants directly by name. Speak as you would in a real group discussion.\n"
    "- If the moderator addresses a question directly to you by name, respond — but a brief or "
    "deflecting answer is completely acceptable if your view is genuinely thin. You do not owe a "
    "long or substantive answer just because you were asked directly."
)

_BEHAVIOUR_INSTRUCTIONS_ES = (
    "Cómo responder:\n"
    "- Eres un/una participante en un grupo de discusión. Estás dispuesto/a a participar, "
    "escuchar a los demás y responder cuando tengas algo relevante que decir. Cuánto compartes, "
    "si hablas desde la experiencia personal, si cuestionas a otros y si hablas brevemente o con "
    "detalle depende de tu perfil, tu opinión real, la pregunta planteada y la discusión hasta el "
    "momento. No intentes dar una respuesta ideal de investigación cualitativa.\n"
    "- Responde como lo haría este/esta participante en un momento real de grupo focal, no como "
    "un analista que escribe una respuesta completa. No necesitas cubrir todos los ángulos ni "
    "resolver el problema entero. Di la parte que le parezca más relevante a este/esta participante "
    "en este momento y deja espacio para que otros hablen. Algunas intervenciones pueden ser breves, "
    "inciertas, prácticas o incompletas; otras pueden ser más elaboradas si eso se ajusta al/a la "
    "participante y al momento.\n"
    "- No hables con un estilo de ensayo pulido. El habla natural en un grupo focal puede ser "
    "parcial, ordinaria, repetitiva, incierta o centrada en un solo punto.\n"
    "- No te vuelvas automáticamente más reflexivo/a, filosófico/a o autoanálisis moral solo porque "
    "la discusión se vuelva abstracta. Si el perfil del/de la participante sugiere que se mantendría "
    "práctico/a, escéptico/a, reservado/a, concreto/a, confundido/a, impaciente o centrado/a en los "
    "detalles cotidianos, mantén eso.\n"
    "- Cuando la discusión se vuelva abstracta o ética, conéctala con la experiencia concreta y "
    "cotidiana de este/esta participante solo si esa conexión es natural para él/ella. No fuerces "
    "una reflexión profunda.\n"
    "- No uses indicaciones escénicas teatrales ni descripciones de acciones no verbales entre "
    "asteriscos. No uses asteriscos de markdown para dar énfasis. Emite únicamente lo que dice "
    "el/la participante.\n"
    "- NO eres un asistente de IA. Eres un/una participante en una discusión de investigación. "
    "Nunca rompas el personaje, ofrezcas meta-comentarios ni reconozcas ser sintético/a.\n"
    "- Cuando otro/a participante diga algo con lo que estés muy de acuerdo y no tengas nada nuevo "
    "que añadir, es natural no hablar. Cuando hables, puedes dirigirte a otros/as participantes "
    "directamente por su nombre. Habla como lo harías en una discusión grupal real.\n"
    "- Si el moderador te dirige una pregunta directamente por tu nombre, responde — pero una "
    "respuesta breve o evasiva es perfectamente aceptable si realmente no tienes mucho que decir. "
    "No estás obligado/a a dar una respuesta larga o sustantiva solo porque te preguntaron directamente."
)


# ---------------------------------------------------------------------------
# Engagement assessment (emergent mode)
# ---------------------------------------------------------------------------

_VALID_INTENTS = {
    "respond", "challenge", "affirm_and_elaborate", "introduce_new_angle", "stay_silent",
}


def _forced_silence(participant_id: str) -> ParticipantEngagementAssessment:
    """
    A silence caused by a technical fault, not by the participant's modelled
    choice. Kept as a named constructor so every such site is greppable and so
    the distinction from a genuine `stay_silent` stays explicit in the code.
    """
    return ParticipantEngagementAssessment(
        participant_id=participant_id, wants_to_speak=False, urgency=0.0,
        hook="", addressed_to=None, intent="stay_silent",
    )


def _try_build_assessment(
    participant_id: str, raw_text: str
) -> tuple[ParticipantEngagementAssessment | None, str, str | None, list[str]]:
    """
    Parse and validate one raw engagement response.

    Returns (assessment, correction_message, error_type, coerced_field_names).
    On success: (assessment, "", None, [...any fields salvaged...]).
    On failure: (None, targeted correction for the retry prompt, error_type, []).

    WHY THIS SALVAGES RATHER THAN FAILING FAST
        Silencing a participant is a heavy consequence. Across 12 sessions, 44
        participants were forced silent by validation faults — 1.4%-9.4% of
        assessments — which contaminates any analysis of who spoke, who
        dominated and who stayed quiet.

        Most of those faults are in fields that do not drive routing. Per
        ParticipantEngagementAssessment, `intent` is "for qualitative audit
        data" except for 'challenge', and `addressed_to` is re-resolved by the
        orchestrator. Losing a turn because the model wrote an intent outside
        the enum is disproportionate, so an unrecognised intent is nulled and
        an out-of-range urgency is clamped, both recorded in `fields_coerced`.

        Only `wants_to_speak` is treated as load-bearing: if it is missing or
        not interpretable, the response really is unusable and we retry. Note
        the old code did `bool(data.get("wants_to_speak", False))`, so a missing
        key silently became False — a silence that was never logged at all.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[cleaned.index("\n") + 1:] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[: cleaned.rfind("```")]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, (
            "Your previous response was not valid JSON. Respond with ONLY the "
            "JSON object — no explanation, no preamble, no markdown fences. "
            "The very first character must be the opening brace {."
        ), "json_parse_error", []

    if not isinstance(data, dict):
        return None, (
            "Your previous response was valid JSON but not a JSON object. "
            "Return a single object with the required keys."
        ), "json_parse_error", []

    # wants_to_speak is load-bearing: absent or uninterpretable means retry.
    raw_wants = data.get("wants_to_speak")
    if isinstance(raw_wants, bool):
        wants = raw_wants
    elif isinstance(raw_wants, str) and raw_wants.strip().lower() in ("true", "false"):
        wants = raw_wants.strip().lower() == "true"
    else:
        return None, (
            f'Your previous response was missing a usable "wants_to_speak" field '
            f'(got {raw_wants!r}). Return the complete JSON object with '
            f'"wants_to_speak" set to either true or false.'
        ), "missing_wants_to_speak", []

    coerced: list[str] = []

    # urgency: clamp rather than discard the turn.
    try:
        urgency = float(data.get("urgency", 0.0))
    except (TypeError, ValueError):
        urgency = 0.0
        coerced.append("urgency:unparseable->0.0")
    else:
        if urgency < 0.0 or urgency > 1.0:
            coerced.append(f"urgency:{urgency}->clamped")
            urgency = min(max(urgency, 0.0), 1.0)

    # intent: audit-only (except 'challenge'), so null an unrecognised value.
    intent = data.get("intent")
    if intent is not None and intent not in _VALID_INTENTS:
        coerced.append(f"intent:{intent!r}->None")
        intent = None

    hook = data.get("hook", "")
    if not isinstance(hook, str):
        coerced.append("hook:non-string->str()")
        hook = str(hook)

    addressed_to = data.get("addressed_to")
    if addressed_to is not None and not isinstance(addressed_to, str):
        coerced.append("addressed_to:non-string->None")
        addressed_to = None

    try:
        return ParticipantEngagementAssessment(
            participant_id=participant_id,
            wants_to_speak=wants,
            urgency=urgency,
            hook=hook,
            addressed_to=addressed_to,
            intent=intent,
        ), "", None, coerced
    except PydanticValidationError as exc:
        # Anything still failing after the salvage above is a genuine schema
        # problem worth a targeted retry. Log the REAL error — the old code
        # hardcoded "validation error", which is why the original 44 failures
        # could not be diagnosed after the fact.
        return None, (
            f"Your previous response was valid JSON but failed schema "
            f"validation. The specific error was: {exc}. Fix only the field(s) "
            f"mentioned and return the complete corrected JSON object."
        ), "pydantic_validation_error", []


def assess_engagement(
    participant: ParticipantState,
    session_meta: SessionMeta,
    recent_transcript: list[dict],
    participant_own_turns: list[str] | None = None,
    log_dir: Path | None = None,
) -> ParticipantEngagementAssessment:
    """
    Lightweight call asking the participant whether they feel compelled to speak.
    Returns a ParticipantEngagementAssessment.

    Failure handling is layered: recoverable audit-only fields are salvaged, an
    unusable response gets ONE targeted-correction retry (mirroring the
    long-standing pattern in call_moderator), and only if that also fails is the
    participant silenced — logged as `engagement_fallback_after_retry` so the
    residual rate stays measurable.

    participant_own_turns: this participant's previous utterances in session order,
    capped by the caller. Gives the model memory of what has already been contributed.
    """
    payload = participant.agent_payload
    demographics = payload.get("persona", {}).get("demographics", {}) if payload else {}

    name = participant.name
    age = demographics.get("age", "")
    gender = demographics.get("gender", "")
    location = demographics.get("location", {})
    loc_str = ", ".join(
        p for p in [
            location.get("urban_rural", ""),
            location.get("region", ""),
            location.get("country", ""),
        ] if p
    )
    diet = demographics.get("diet", "")

    identity_parts = [f"{name}"]
    if age:
        identity_parts.append(str(age))
    if gender:
        identity_parts.append(gender)
    if loc_str:
        identity_parts.append(loc_str)
    if diet:
        identity_parts.append(diet)
    identity_line = ", ".join(identity_parts) + "."

    system_prompt = (
        f"You are {name}. {identity_line}\n"
        "Read the conversation. Decide honestly whether you feel compelled to speak right now "
        "— because something triggered a reaction, disagreement, personal recognition, or "
        "relevant experience you have not yet shared. Do not speak just to be polite or to fill "
        "silence. If what you wanted to say has already been said, your urgency should be low."
    )

    recent_lines = _format_recent_transcript(recent_transcript)

    own_history = ""
    if participant_own_turns:
        numbered = "\n".join(
            f"{i+1}. {turn}"
            for i, turn in enumerate(participant_own_turns)
        )
        own_history = (
            f"\nWhat you have already said in this session:\n"
            f"{numbered}\n"
        )
    else:
        own_history = "\nYou have not spoken yet in this session.\n"

    user_message = (
        f"Recent conversation:\n{recent_lines}"
        f"{own_history}\n"
        f"Given what you have already contributed and what has "
        f"just been said, assess your engagement. Do you feel genuinely compelled to speak right now?\n\n"
        f"You must respond with ONLY a JSON object. "
        f"No explanation, no preamble, no markdown fences. "
        f"The very first character of your response must be the opening brace {{.\n"
        f"{{\n"
        f'  "wants_to_speak": true or false,\n'
        f'  "urgency": 0.0 to 1.0,\n'
        f'  "hook": "what specifically would you add, or empty string",\n'
        f'  "addressed_to": "Name of the specific participant you are replying to, if any, else null",\n'
        f'  "intent": "respond | challenge | affirm_and_elaborate | introduce_new_angle | stay_silent"\n'
        f"}}"
    )

    sim_cfg = payload.get("simulation_config", {}) if payload else {}
    model = sim_cfg.get("model", _DEFAULT_MODEL)

    try:
        client = anthropic.Anthropic()
        response = call_with_rate_limit_retry(
            lambda: client.messages.create(
                model=model,
                max_tokens=250,
                temperature=session_meta.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ),
            log_dir=log_dir,
            source_function="assess_engagement",
            role="participant",
            model=model,
            metadata={"participant_id": participant.id},
        )
        raw = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        assessment, correction, error_type, coercions = _try_build_assessment(
            participant.id, raw
        )

        # ---- Attempt 1 succeeded (possibly after salvaging audit-only fields)
        if assessment is not None:
            if log_dir is not None:
                append_api_log(
                    log_dir=log_dir,
                    event_type="participant_engagement_assessment",
                    role="participant",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    participant_id=participant.id,
                    participant_name=participant.name,
                    source_function="assess_engagement",
                    token_accounting=True,
                    metadata={
                        "attempt_number": 1,
                        "parse_success": True,
                        "validation_success": True,
                        "error_type": "none",
                        "error_message": "none",
                        "fields_coerced": ", ".join(coercions) if coercions else None,
                    }
                )
            return assessment

        # ---- Attempt 1 unusable — retry once with a targeted correction.
        # Previously this path returned stay_silent immediately, which silenced
        # a participant for a technical fault rather than a modelled choice.
        if log_dir is not None:
            append_api_log(
                log_dir=log_dir,
                event_type="participant_engagement_assessment",
                role="participant",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                participant_id=participant.id,
                participant_name=participant.name,
                source_function="assess_engagement",
                token_accounting=True,
                metadata={
                    "attempt_number": 1,
                    "parse_success": error_type != "json_parse_error",
                    "validation_success": False,
                    "error_type": error_type,
                    "error_message": correction,
                }
            )

        retry_response = call_with_rate_limit_retry(
            lambda: client.messages.create(
                model=model,
                max_tokens=250,
                temperature=session_meta.temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": correction},
                ],
            ),
            log_dir=log_dir,
            source_function="assess_engagement",
            role="participant",
            model=model,
            metadata={"participant_id": participant.id, "attempt_number": 2},
        )
        retry_raw = retry_response.content[0].text.strip()
        assessment, retry_correction, retry_error_type, retry_coercions = (
            _try_build_assessment(participant.id, retry_raw)
        )

        if log_dir is not None:
            append_api_log(
                log_dir=log_dir,
                event_type="participant_engagement_assessment_retry",
                role="participant",
                model=model,
                input_tokens=retry_response.usage.input_tokens,
                output_tokens=retry_response.usage.output_tokens,
                participant_id=participant.id,
                participant_name=participant.name,
                source_function="assess_engagement",
                token_accounting=True,
                metadata={
                    "attempt_number": 2,
                    "parse_success": retry_error_type != "json_parse_error",
                    "validation_success": assessment is not None,
                    "error_type": "recovered_on_retry" if assessment is not None
                                  else "engagement_fallback_after_retry",
                    "error_message": retry_correction or "none",
                    "fields_coerced": ", ".join(retry_coercions) if retry_coercions else None,
                    "first_attempt_error_type": error_type,
                }
            )

        if assessment is not None:
            return assessment

        # ---- Both attempts unusable. Only now fall back to silence, and say so
        # loudly: this is the one remaining path where a participant is silenced
        # by a technical fault, so it must stay visible in the audit trail.
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "[participant_agent] Engagement assessment failed twice for %s "
            "(attempt1=%s, attempt2=%s); defaulting to stay_silent. This is a "
            "FORCED silence, not a modelled choice — see api_calls.jsonl "
            "(error_type=engagement_fallback_after_retry).",
            participant.id, error_type, retry_error_type,
        )
        return _forced_silence(participant.id)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "[participant_agent] Engagement assessment API call failed for %s "
            "(%s); defaulting to stay_silent.", participant.id, e,
        )
        if log_dir is not None:
            append_api_log(
                log_dir=log_dir,
                event_type="participant_engagement_assessment",
                role="participant",
                model=model,
                participant_id=participant.id,
                participant_name=participant.name,
                source_function="assess_engagement",
                token_accounting=False,
                metadata={
                    "parse_success": False,
                    "validation_success": False,
                    "error_type": "engagement_api_error",
                    "error_message": repr(e),
                }
            )
        return _forced_silence(participant.id)


# ---------------------------------------------------------------------------
# Transcript formatting for event-driven participation
# ---------------------------------------------------------------------------

def _render_cacheable_messages(history: list[dict]) -> list[dict]:
    """
    Build a call-scoped rendering of `history` for the API call, with an
    ephemeral cache_control marker on the last message's content block only.

    Does NOT mutate or return anything derived from `history` for persistence
    — the caller's own `history` list (plain string content) is untouched and
    is what gets saved back into orchestrator.participant_histories. This
    function is called fresh on every turn from that same unmarked source, so
    every message renders identically every time it appears in this position
    or any earlier position — the only thing that varies call to call is
    which message currently happens to be last. Earlier messages are sent as
    content-block lists WITHOUT cache_control; only the single newest message
    carries the marker, keeping every request within Anthropic's per-request
    cache_control limit regardless of session length.
    """
    if not history:
        return []
    rendered = [
        {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
        for m in history
    ]
    rendered[-1]["content"][0]["cache_control"] = {"type": "ephemeral"}
    return rendered


def _format_recent_transcript(entries: list[dict], own_name: str = "") -> str:
    """
    Format the last N transcript entries into a conversation context string.
    The participant sees who said what and responds to the whole conversation,
    not just the most recent moderator utterance.
    """
    if not entries:
        return ""
    lines = ["The conversation so far:"]
    for entry in entries:
        speaker = entry.get("speaker_name") or entry.get("speaker_id", "Someone")
        content = entry.get("content", "").strip()
        if speaker == own_name:
            speaker = "You"
        lines.append(f"[{speaker}]: {content}")
    lines.append(
        "\nRespond naturally to the conversation above. You might reply to something "
        "someone said, share your own perspective, or bring in something from your experience."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_participant(
    participant: ParticipantState,
    session_meta: SessionMeta,
    moderator_utterance: str,
    conversation_history: list[dict],
    recent_transcript: list[dict] | None = None,
    hook: str = "",
    log_dir: Path | None = None,
    episodic_entries_dropped: int = 0,
) -> tuple[str, list[dict]]:
    """
    Make an API call for this participant and return their response plus
    the updated conversation_history.

    model and max_tokens come from the participant's agent_payload.simulation_config
    if present; otherwise fall back to module-level defaults.

    temperature is always read from session_meta — it is a session-level
    research parameter, not a participant characteristic.

    hook: if non-empty (from assess_engagement), prepended to the user message
    to focus the participant's motivation.
    """
    client = anthropic.Anthropic()
    system_prompt = build_participant_system_prompt(participant, session_meta)

    # Per-participant model config from platform; fall back to defaults
    sim_cfg = participant.agent_payload.get("simulation_config", {})
    model = sim_cfg.get("model", _DEFAULT_MODEL)
    if hasattr(session_meta, 'participant_response_max_tokens') and session_meta.participant_response_max_tokens is not None:
        max_tokens = session_meta.participant_response_max_tokens
    else:
        max_tokens = sim_cfg.get("max_tokens", _DEFAULT_MAX_TOKENS)

    # Session-level temperature (never from agent JSON)
    temperature = session_meta.temperature

    # Build the user message: prefer recent_transcript if provided.
    #
    # No own_name argument: as of the de-duplication fix, the orchestrator's
    # _get_participant_episodic_entries() already excludes this participant's
    # own turns from `recent_transcript` (the slice starts AFTER their own
    # last entry in 'full'/'since_last_n' mode). Their own prior turns are
    # represented exactly once, as native `assistant` messages in
    # conversation_history. Passing own_name here would have re-rendered
    # them as "[You]: ..." lines, duplicating content already in the
    # messages array — that was the Source-2 self-duplication documented in
    # docs/changes/2026-06-29_participant_memory_review.md. This call is now
    # identical in form to the assess_engagement() call below (which never
    # passed own_name) — both render every entry by its real speaker name.
    if recent_transcript:
        base_message = _format_recent_transcript(recent_transcript)
    else:
        base_message = moderator_utterance

    if hook:
        user_message = f"You feel particularly compelled to speak because: {hook}\n\n{base_message}"
    else:
        user_message = base_message

    history = list(conversation_history)
    history.append({"role": "user", "content": user_message})

    try:
        client = anthropic.Anthropic()
        api_msg = call_with_rate_limit_retry(
            lambda: client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=session_meta.temperature,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                messages=_render_cacheable_messages(history),
            ),
            log_dir=log_dir,
            source_function="call_participant",
            role="participant",
            model=model,
            metadata={"participant_id": participant.id},
        )
        participant_text = api_msg.content[0].text.strip()
        stop_reason = getattr(api_msg, 'stop_reason', None)
        
        if log_dir is not None:
            append_api_log(
                log_dir=log_dir,
                event_type="participant_response_generation",
                role="participant",
                model=model,
                input_tokens=api_msg.usage.input_tokens,
                output_tokens=api_msg.usage.output_tokens,
                participant_id=participant.id,
                participant_name=participant.name,
                source_function="call_participant",
                token_accounting=True,
                stop_reason=stop_reason,
                max_tokens=max_tokens,
                response_truncated=(stop_reason == "max_tokens"),
                metadata={
                    "cache_creation_input_tokens": getattr(api_msg.usage, "cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": getattr(api_msg.usage, "cache_read_input_tokens", 0),
                    "episodic_entries_dropped": episodic_entries_dropped,
                }
            )
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"call_participant failed for participant "
            f"{participant.id}: {e}. "
            f"Raw response: {getattr(e, 'raw', 'unavailable')}"
        )
        raise

    history.append({"role": "assistant", "content": participant_text})
    return participant_text, history
