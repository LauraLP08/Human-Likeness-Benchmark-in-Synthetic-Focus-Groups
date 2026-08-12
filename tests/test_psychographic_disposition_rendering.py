"""
Tests for the psychographic disposition rendering rewrite: latent
attachment/comfort/defensiveness framing (not stated opinion), split into
"coded" (social-desirability-prone) vs "habit" (low-stakes) tiers, with
deterministic per-persona phrasing variation.

Pure string-generation logic + file reads. Zero network calls, zero API calls.
See INSTRUCTIONS_PSYCHOGRAPHIC_DISPOSITION_RENDERING.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.participant_agent import (
    _CODED_TEMPLATES,
    _score_to_instruction,
    build_participant_system_prompt,
    load_agent_from_json,
)
from core.session_state import SessionMeta

_AGENTS_DIR = Path("agents/macho_meals")
_PARTICIPANT_AGENT_SOURCE = Path("core/participant_agent.py")


def _session_meta() -> SessionMeta:
    return SessionMeta(
        id="test_psychographic",
        research_objective="test",
        topic_domain="test",
        participant_collective_identity="test participants",
        moderator_knowledge_brief="",
    )


def _load(agent_filename: str):
    return load_agent_from_json(str(_AGENTS_DIR / agent_filename))


def test_build_participant_system_prompt_is_deterministic():
    """The literal property required for future cache_control compatibility:
    byte-identical output across repeated calls with the same inputs."""
    participant = _load("mm_fg1_amir.json")
    meta = _session_meta()

    first = build_participant_system_prompt(participant, meta)
    second = build_participant_system_prompt(participant, meta)

    assert first == second


def test_variant_selection_differs_across_personas():
    """Two different agent_ids with the same score on the same dimension get
    different rendered text — proves the hash-based variant selection varies
    across personas, not just across dimensions."""
    text_a = _score_to_instruction(
        "masculinity_of_meat", 5.0, "Higher scores indicate stronger perceived masculinity-meat link.", "agent_a"
    )
    text_b = _score_to_instruction(
        "masculinity_of_meat", 5.0, "Higher scores indicate stronger perceived masculinity-meat link.", "agent_b"
    )
    assert text_a != text_b


def test_coded_tier_signals_private_public_gap():
    coded_text = _score_to_instruction(
        "masculinity_of_meat", 5.0, "Higher scores indicate stronger perceived masculinity-meat link.", "agent_x"
    )
    assert "Privately," in coded_text


def test_habit_tier_does_not_signal_private_public_gap():
    habit_text = _score_to_instruction(
        "meat_attachment", 5.0, "Higher scores indicate stronger attachment to eating meat.", "agent_x"
    )
    assert "Privately," not in habit_text


def test_all_twentytwo_real_agents_produce_valid_nonempty_prompt():
    """Was 17 until 2026-07-24, when the 5 FG3 agents were built once the
    researcher resolved the PID-matching gap (see
    docs/changes/2026-07-24_macho_meals_fg3_agent_build.md). 22 = the study's
    22 real participants (FG1 5, FG2 5, FG3 5, FG4 3, FG5 4)."""
    agent_files = sorted(
        f for f in _AGENTS_DIR.glob("*.json") if f.name != "_manifest.json"
    )
    assert len(agent_files) == 22, f"Expected 22 agent files, found {len(agent_files)}"

    meta = _session_meta()
    for f in agent_files:
        participant = load_agent_from_json(str(f))
        prompt = build_participant_system_prompt(participant, meta)
        assert isinstance(prompt, str)
        assert prompt.strip(), f"{f.name} produced an empty prompt"


def test_fg3_identity_linkage_caveat_never_reaches_the_prompt():
    """The FG3 agents' survey-row-to-name pairing is a researcher random
    assignment, recorded in study_context.identity_metadata_linkage{,_note}.
    study_context is never read by build_participant_system_prompt(), whereas
    any other dict-valued key directly under `persona` IS rendered as
    "Additional context about you". Guard against the caveat migrating there."""
    fg3_files = sorted(_AGENTS_DIR.glob("mm_fg3_*.json"))
    assert len(fg3_files) == 5, f"Expected 5 FG3 agent files, found {len(fg3_files)}"

    meta = _session_meta()
    for f in fg3_files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        study_context = payload["study_context"]
        assert study_context["identity_metadata_linkage"] == "researcher_random_assignment"
        assert study_context["identity_metadata_linkage_note"]
        assert "identity_metadata_linkage" not in payload["persona"]
        assert "identity_metadata_linkage_note" not in payload["persona"]

        prompt = build_participant_system_prompt(load_agent_from_json(str(f)), meta).lower()
        for leaked in ("identity_metadata_linkage", "random", "assign", "pid",
                       "additional context about you"):
            assert leaked not in prompt, f"{f.name} leaked {leaked!r} into the prompt"


def test_amir_ibrahim_render_opposite_masculinity_of_meat_disposition():
    """Cross-check against the real transcript divergence this change is
    meant to make plausible: Amir (5.0, high) denied the link out loud;
    Ibrahim (1.4, low) affirmed it out loud. The rendered text at least
    must not collapse both into the same stated-opinion instruction."""
    amir = _load("mm_fg1_amir.json")
    ibrahim = _load("mm_fg1_ibrahim.json")
    meta = _session_meta()

    amir_prompt = build_participant_system_prompt(amir, meta)
    ibrahim_prompt = build_participant_system_prompt(ibrahim, meta)

    assert amir_prompt != ibrahim_prompt
    # Both reference the same underlying construct (via the direction-derived
    # "high_end" phrase), but land in opposite toward/against buckets so the
    # rendered instruction text differs meaningfully, not just cosmetically.
    assert "masculinity-meat link" in amir_prompt.lower()
    assert "masculinity-meat link" in ibrahim_prompt.lower()
    amir_line = next(l for l in amir_prompt.splitlines() if "masculinity-meat link" in l.lower())
    ibrahim_line = next(l for l in ibrahim_prompt.splitlines() if "masculinity-meat link" in l.lower())
    assert amir_line != ibrahim_line


def test_scripted_hedging_exemplars_removed():
    """None of the specific, quoted discursive strategies removed by
    INSTRUCTIONS_STRIP_SCRIPTED_HEDGING_CONTENT.md should still be present in
    the source — they scripted a specific *content* of hedging, not just the
    disposition to hedge, which would contaminate downstream thematic coding
    (scripts/thematic_coding.py) with a finding the prompt authored rather
    than the simulation produced."""
    source = _PARTICIPANT_AGENT_SOURCE.read_text(encoding="utf-8")
    removed_phrases = [
        "older generations",
        "some blokes",
        "it's just what I grew up with",
        "that's changed a lot",
        "how things used to be",
        "'some people think that'",
    ]
    for phrase in removed_phrases:
        assert phrase not in source, f"Scripted hedging exemplar {phrase!r} still present in source"


def test_coded_templates_contain_no_quoted_exemplars():
    """General guard against reintroducing this pattern: a single-quoted
    fragment inside a coded-tier template is exactly the shape of the bug —
    a specific, scripted discursive move handed to the model — regardless of
    which words are used. Stronger than the six-phrase literal check above.

    Note on the pattern: the instruction spec's literal r"'[^']+'" false-
    positives on ordinary English contractions (e.g. "you don't ... there's"
    parses as a "quoted" span from the apostrophe in "don't" to the one in
    "there's"), which would fail 8 of the 14 current entries — including
    ones the same instruction explicitly reviewed and left untouched as not
    having this problem. Contraction apostrophes always sit directly between
    two letters; a genuine quoted exemplar's apostrophes sit at a word
    boundary (preceded by whitespace/punctuation, or followed by it). Using
    that boundary distinction here so the guard actually matches its stated
    intent instead of flagging every contraction as a scripted exemplar.
    """
    quote_pattern = re.compile(r"(?<!\w)'[^']+'(?!\w)")
    for bucket, variants in _CODED_TEMPLATES.items():
        for i, variant in enumerate(variants):
            assert not quote_pattern.search(variant), (
                f"_CODED_TEMPLATES[{bucket!r}][{i}] contains a quoted exemplar: {variant!r}"
            )
