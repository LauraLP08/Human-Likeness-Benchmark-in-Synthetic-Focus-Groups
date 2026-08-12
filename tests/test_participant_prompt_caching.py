"""
Tests for Anthropic prompt caching on the participant path (call_participant
only, not assess_engagement). Structural verification only — no live API
calls, no claim about actual cache hits (that's confirmed later during the
sandbox pilot).

Mocked-client tests. Zero network calls, zero API calls.
See INSTRUCTIONS_PARTICIPANT_PROMPT_CACHING.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.participant_agent import (
    _render_cacheable_messages,
    build_participant_system_prompt,
    call_participant,
    load_agent_from_json,
)
from core.session_state import SessionMeta

_AGENTS_DIR = Path("agents/macho_meals")


def _session_meta() -> SessionMeta:
    return SessionMeta(
        id="test_caching",
        research_objective="test",
        topic_domain="test",
        participant_collective_identity="test participants",
        moderator_knowledge_brief="",
    )


@patch("core.participant_agent.anthropic.Anthropic")
def test_call_participant_sends_ephemeral_cache_control_system_block(mock_anthropic, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="I think it's fine.")]
    mock_message.usage = MagicMock(
        input_tokens=500,
        output_tokens=20,
        cache_creation_input_tokens=480,
        cache_read_input_tokens=0,
    )
    mock_message.stop_reason = "end_turn"
    mock_client.messages.create.return_value = mock_message

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_amir.json"))
    meta = _session_meta()
    expected_prompt = build_participant_system_prompt(participant, meta)

    call_participant(
        participant=participant,
        session_meta=meta,
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=tmp_path,
    )

    _, kwargs = mock_client.messages.create.call_args
    system = kwargs["system"]

    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0] == {
        "type": "text",
        "text": expected_prompt,
        "cache_control": {"type": "ephemeral"},
    }


@patch("core.participant_agent.anthropic.Anthropic")
def test_call_participant_logs_cache_metadata(mock_anthropic, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Sure, I guess.")]
    mock_message.usage = MagicMock(
        input_tokens=20,
        output_tokens=15,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=480,
    )
    mock_message.stop_reason = "end_turn"
    mock_client.messages.create.return_value = mock_message

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_ibrahim.json"))
    meta = _session_meta()

    call_participant(
        participant=participant,
        session_meta=meta,
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=tmp_path,
    )

    log_file = tmp_path / "api_calls.jsonl"
    assert log_file.exists()
    data = json.loads(log_file.read_text().strip())

    assert data["source_function"] == "call_participant"
    assert data["cache_creation_input_tokens"] == 0
    assert data["cache_read_input_tokens"] == 480
    # §3.5: always present, zero when nothing was dropped — same shape as the
    # two cache-token fields, so the drop rate is computable from the log
    # without treating a missing key as ambiguous.
    assert data["episodic_entries_dropped"] == 0


@patch("core.participant_agent.anthropic.Anthropic")
def test_call_participant_defaults_missing_cache_fields_to_zero(mock_anthropic, tmp_path):
    """Defensive against SDK versions where the cache usage fields are absent
    (caching wasn't used on that particular call) — must not crash."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    mock_message = MagicMock(spec=["content", "usage", "stop_reason"])
    mock_message.content = [MagicMock(text="Not sure.")]
    mock_message.usage = MagicMock(spec=["input_tokens", "output_tokens"])
    mock_message.usage.input_tokens = 20
    mock_message.usage.output_tokens = 10
    mock_message.stop_reason = "end_turn"
    mock_client.messages.create.return_value = mock_message

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_david.json"))
    meta = _session_meta()

    call_participant(
        participant=participant,
        session_meta=meta,
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=tmp_path,
    )

    log_file = tmp_path / "api_calls.jsonl"
    data = json.loads(log_file.read_text().strip())
    assert data["cache_creation_input_tokens"] == 0
    assert data["cache_read_input_tokens"] == 0


# ---------------------------------------------------------------------------
# INSTRUCTIONS_PARTICIPANT_MEMORY_TRACKING_AND_CACHING.md
#
# Part B — the participant's own growing conversation is cached, not just the
# system prompt. The marker goes on a call-scoped rendering built fresh each
# turn; conversation_history / participant_histories stay plain-string and are
# never persisted with a cache_control key on them. Two properties keep the
# prefix stable: every message renders identically wherever it appears, and
# exactly one block per request carries the marker (so the 4-per-request limit
# can't be exceeded no matter how long the session runs).
#
# Part A — episodic_entries_dropped rides through to append_api_log().
# ---------------------------------------------------------------------------

def _mock_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage = MagicMock(
        input_tokens=100,
        output_tokens=20,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    msg.stop_reason = "end_turn"
    return msg


@patch("core.participant_agent.anthropic.Anthropic")
def test_call_participant_caches_single_turn_with_no_prior_history(mock_anthropic, tmp_path):
    """§3.1 — one message, wrapped as a content block, marker on it."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _mock_message("Yeah, probably.")

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_amir.json"))

    call_participant(
        participant=participant,
        session_meta=_session_meta(),
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=tmp_path,
    )

    _, kwargs = mock_client.messages.create.call_args
    messages = kwargs["messages"]

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == [
        {
            "type": "text",
            "text": "What do you think?",
            "cache_control": {"type": "ephemeral"},
        }
    ]


@patch("core.participant_agent.anthropic.Anthropic")
def test_call_participant_marks_only_newest_message_across_turns(mock_anthropic, tmp_path):
    """
    §3.2 — after a second turn built on the first turn's returned history:
    the first message carries NO cache_control, the last one does, and every
    message's text matches verbatim what was in the returned history. That
    last part is the load-bearing check: the rendering wraps content, it never
    alters it, so the prefix stays byte-identical turn to turn.
    """
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _mock_message("First reply.")

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_amir.json"))
    meta = _session_meta()

    _, history_after_turn_1 = call_participant(
        participant=participant,
        session_meta=meta,
        moderator_utterance="Opening question?",
        conversation_history=[],
        log_dir=tmp_path,
    )

    mock_client.messages.create.return_value = _mock_message("Second reply.")
    call_participant(
        participant=participant,
        session_meta=meta,
        moderator_utterance="Follow-up question?",
        conversation_history=history_after_turn_1,
        log_dir=tmp_path,
    )

    _, kwargs = mock_client.messages.create.call_args
    messages = kwargs["messages"]

    # user, assistant, user
    assert len(messages) == 3

    # (a) first message: wrapped, no marker at all
    assert messages[0]["content"] == [{"type": "text", "text": "Opening question?"}]
    assert "cache_control" not in messages[0]["content"][0]

    # (b) last message: marker present
    assert messages[-1]["content"][0]["cache_control"] == {"type": "ephemeral"}

    # (c) content is never altered by the rendering — compare against the
    #     history the caller actually holds, message for message.
    sent_history = history_after_turn_1 + [
        {"role": "user", "content": messages[-1]["content"][0]["text"]}
    ]
    for sent, rendered in zip(sent_history, messages):
        assert rendered["role"] == sent["role"]
        assert rendered["content"][0]["text"] == sent["content"]

    # Exactly one marker in the whole request, on the newest message.
    marked = [m for m in messages if "cache_control" in m["content"][0]]
    assert len(marked) == 1
    assert marked[0] is messages[-1]


@patch("core.participant_agent.anthropic.Anthropic")
def test_returned_history_is_plain_strings_never_the_rendered_form(mock_anthropic, tmp_path):
    """
    §3.3 — what gets persisted into orchestrator.participant_histories must
    stay plain-string content. If the rendered form ever leaked into the
    return value, markers would accumulate in stored state and the same
    message would serialize differently depending on when it was sent.
    """
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _mock_message("A reply.")

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_david.json"))

    _, history = call_participant(
        participant=participant,
        session_meta=_session_meta(),
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=tmp_path,
    )

    assert len(history) == 2  # user + assistant
    for message in history:
        assert isinstance(message["content"], str)
        assert "cache_control" not in message
    assert history[-1] == {"role": "assistant", "content": "A reply."}


def test_render_cacheable_messages_never_exceeds_one_marker():
    """
    §3.4 — the per-request cache_control limit is 4; this rendering uses
    exactly 1 regardless of session length. 12 entries ~= 6 turns, well past
    the point where a naive persist-the-marker approach would break.
    """
    history = []
    for i in range(6):
        history.append({"role": "user", "content": f"question {i}"})
        history.append({"role": "assistant", "content": f"answer {i}"})

    rendered = _render_cacheable_messages(history)

    assert len(rendered) == 12
    marked = [
        block
        for message in rendered
        for block in message["content"]
        if "cache_control" in block
    ]
    assert len(marked) == 1
    assert rendered[-1]["content"][0]["cache_control"] == {"type": "ephemeral"}

    # The source history is untouched — still plain strings, no markers.
    assert all(isinstance(m["content"], str) for m in history)


def test_render_cacheable_messages_handles_empty_history():
    assert _render_cacheable_messages([]) == []


@patch("core.participant_agent.anthropic.Anthropic")
def test_call_participant_logs_nonzero_episodic_entries_dropped(mock_anthropic, tmp_path):
    """§3.6 — a nonzero drop count passes through to the log unchanged."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _mock_message("Right.")

    participant = load_agent_from_json(str(_AGENTS_DIR / "mm_fg1_will.json"))

    call_participant(
        participant=participant,
        session_meta=_session_meta(),
        moderator_utterance="What do you think?",
        conversation_history=[],
        log_dir=tmp_path,
        episodic_entries_dropped=7,
    )

    data = json.loads((tmp_path / "api_calls.jsonl").read_text().strip())
    assert data["episodic_entries_dropped"] == 7
