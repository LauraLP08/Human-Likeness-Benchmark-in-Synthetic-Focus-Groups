"""
The effective request configuration must describe the REAL call, and the cache key
must depend on all of it.

This exists because `max_output_tokens=32768` was transmitted on every Tier-1 call
while appearing in neither `effective_request_config` nor the cache key. Two runs
made under materially different output caps would have collided on one cache entry
and been indistinguishable in the audit trail.

No API calls.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import production_eval_pipeline as pep       # noqa: E402
from thematic_coding import EVALUATOR_CONFIGS  # noqa: E402

ECFG = EVALUATOR_CONFIGS["gemininext"]


def _eff():
    return pep.effective_request_config(ECFG)


# ---------------------------------------------------------------------------
# Every transmitted parameter must be present
# ---------------------------------------------------------------------------

def test_transmitted_keys_are_read_from_the_real_call_not_restated():
    """A second hand-written copy of the request config is what drifted before."""
    keys = pep.tier1_transmitted_generation_config()
    assert "max_output_tokens" in keys
    assert "response_mime_type" in keys
    assert keys["response_mime_type"] == "application/json"
    # `max_output_tokens` now resolves at call time from evaluator_cfg, so the AST
    # value is a call expression rather than a literal. What must hold is that the
    # key is detected as transmitted and that the DEFAULT is still 32768.
    assert keys["max_output_tokens"] is None, "resolved at call time, not a literal"
    import thematic_coding as tc
    assert tc.TIER1_DEFAULT_MAX_OUTPUT_TOKENS == 32768


def test_no_transmitted_parameter_is_missing_from_effective_config():
    """The regression guard: this is the check that max_output_tokens failed."""
    assert pep.effective_config_coverage_problems(_eff()) == []


def test_coverage_check_fails_when_a_parameter_is_dropped():
    """The guard must actually fire, not pass vacuously."""
    crippled = {k: v for k, v in _eff().items() if k != "max_output_tokens"}
    problems = pep.effective_config_coverage_problems(crippled)
    assert problems, "dropping a transmitted parameter must be detected"
    assert any("max_output_tokens" in p for p in problems)


def test_coverage_check_fails_for_response_mime_type_too():
    crippled = {k: v for k, v in _eff().items() if k != "response_mime_type"}
    assert any("response_mime_type" in p
               for p in pep.effective_config_coverage_problems(crippled))


def test_system_instruction_is_excused_only_with_a_stated_reason():
    """It is keyed separately as evaluator_prompt_sha256 — that must be declared."""
    assert "system_instruction" in pep.tier1_transmitted_generation_config()
    assert "system_instruction" in pep.TRANSMITTED_BUT_KEYED_SEPARATELY
    assert pep.TRANSMITTED_BUT_KEYED_SEPARATELY["system_instruction"]


def test_effective_config_records_the_real_values():
    eff = _eff()
    assert eff["model"] == "gemini-3.5-flash"
    assert eff["max_output_tokens"] == 32768
    assert eff["response_mime_type"] == "application/json"
    # gemini-3.5-flash: neither temperature nor thinking config is transmitted
    assert eff["temperature_transmitted"] is False
    assert eff["thinking_config_transmitted"] is False
    assert eff["thinking_config"] is None
    assert eff["thinking_level_effective"] == "model_default_unpinned"
    assert eff["thinking_level_label_in_config"] == "medium", (
        "the config label is retained, but only as a label")


def test_thinking_config_is_transmitted_for_a_25_class_model():
    eff = pep.effective_request_config({"model": "gemini-2.5-flash", "temperature": None,
                                        "thinking_level": "medium"})
    assert eff["thinking_config_transmitted"] is True
    assert eff["thinking_config"] == {"thinking_budget": 0}


# ---------------------------------------------------------------------------
# The cache key must depend on the whole effective configuration
# ---------------------------------------------------------------------------

def _key(effective):
    return pep.cache_key("sha-input", "tier1", "sha-codebook", "sha-prompt",
                         pep.canonical_model_config(effective))


def test_changing_max_output_tokens_changes_the_cache_key():
    """The specific collision this work exists to prevent."""
    a = _eff()
    b = dict(a, max_output_tokens=16384)
    assert a["max_output_tokens"] != b["max_output_tokens"]
    assert _key(a) != _key(b), (
        "32768 and 16384 must not share a cache entry: a smaller cap can truncate "
        "the JSON and drop codes or quotes")


def test_changing_response_mime_type_changes_the_cache_key():
    assert _key(_eff()) != _key(dict(_eff(), response_mime_type="text/plain"))


def test_changing_model_or_temperature_changes_the_cache_key():
    a = _eff()
    assert _key(a) != _key(dict(a, model="gemini-2.5-flash"))
    assert _key(a) != _key(dict(a, temperature=0.0, temperature_transmitted=True))


def test_changing_thinking_config_changes_the_cache_key():
    a = _eff()
    assert _key(a) != _key(dict(a, thinking_config_transmitted=True,
                                thinking_config={"thinking_budget": 0}))


def test_identical_config_gives_an_identical_key():
    assert _key(_eff()) == _key(_eff())


def test_canonical_serialisation_is_order_independent():
    a = _eff()
    shuffled = dict(reversed(list(a.items())))
    assert pep.canonical_model_config(a) == pep.canonical_model_config(shuffled)
    assert _key(a) == _key(shuffled)


def test_every_effective_field_participates_in_the_key():
    """No field may be decorative: changing any one must move the hash."""
    base = _eff()
    unchanged = []
    for field, value in base.items():
        altered = dict(base)
        altered[field] = "SENTINEL" if value != "SENTINEL" else "OTHER"
        if _key(altered) == _key(base):
            unchanged.append(field)
    assert not unchanged, f"fields absent from the cache key: {unchanged}"


def test_cache_key_still_depends_on_input_prompt_and_codebook():
    eff = pep.canonical_model_config(_eff())
    base = pep.cache_key("i", "tier1", "c", "p", eff)
    assert base != pep.cache_key("i2", "tier1", "c", "p", eff)
    assert base != pep.cache_key("i", "tier2", "c", "p", eff)
    assert base != pep.cache_key("i", "tier1", "c2", "p", eff)
    assert base != pep.cache_key("i", "tier1", "c", "p2", eff)
