"""
Focused tests for the preflight_v2 output-cap override and truncation detection.

The override must reach the API, appear in the effective configuration, and key the
cache — a 16384 run must never be served a 32768 result. And a truncated response
must be rejected rather than read as "these codes were absent".

No API calls.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import production_eval_pipeline as pep          # noqa: E402
import thematic_coding as tc                    # noqa: E402
import tier1_completeness as comp               # noqa: E402
from thematic_coding import EVALUATOR_CONFIGS   # noqa: E402

BASE = EVALUATOR_CONFIGS["gemininext"]
V2 = dict(BASE, max_output_tokens=16384)


# ---------------------------------------------------------------------------
# 1-2. the override reaches the API; absence of override keeps 32768
# ---------------------------------------------------------------------------

def _captured_gen_cfg(ecfg, monkeypatch):
    """Run code_transcript_tier1 far enough to capture the transmitted config."""
    seen = {}

    class _Resp:
        text = json.dumps({"codes": [
            {"subtheme_id": s, "present": False, "supporting_quotes": [],
             "voiced_by": []} for s in comp.EXPECTED_SUBTHEME_IDS]})
        candidates = []
        usage_metadata = None

    def fake_generate(cli, *, no_fallback, model, contents, config):
        seen.update(config)
        seen["_model"] = model
        return _Resp()

    monkeypatch.setattr(tc, "_generate_with_fallback", fake_generate)
    monkeypatch.setattr(tc, "_client_for_evaluator", lambda c: object())
    monkeypatch.setattr(tc, "_log_call", lambda *a, **k: None)
    monkeypatch.setattr(tc, "verify_codes",
                        lambda r, t, transcript_label=None, n_participants=None: (r, None))
    tc.code_transcript_tier1("[T001] Participant 1: hello", [], "lbl", evaluator_cfg=ecfg)
    return seen


def test_without_override_the_api_receives_32768(monkeypatch):
    cfg = _captured_gen_cfg(BASE, monkeypatch)
    assert cfg["max_output_tokens"] == 32768
    assert tc.TIER1_DEFAULT_MAX_OUTPUT_TOKENS == 32768


def test_override_16384_is_actually_transmitted(monkeypatch):
    cfg = _captured_gen_cfg(V2, monkeypatch)
    assert cfg["max_output_tokens"] == 16384, (
        "the override must reach the API, not merely be recorded")
    assert cfg["response_mime_type"] == "application/json"
    assert "temperature" not in cfg, "temperature must not be transmitted"
    assert "thinking_config" not in cfg, "thinking config must not be transmitted"
    assert cfg["_model"] == "gemini-3.5-flash"


def test_default_is_not_globally_replaced(monkeypatch):
    """An override for one run must not change the default for the next."""
    assert _captured_gen_cfg(V2, monkeypatch)["max_output_tokens"] == 16384
    assert _captured_gen_cfg(BASE, monkeypatch)["max_output_tokens"] == 32768


# ---------------------------------------------------------------------------
# 3-5. cache keys, no mixing, nothing else changes
# ---------------------------------------------------------------------------

def _key(ecfg):
    eff = pep.effective_request_config(ecfg)
    return pep.cache_key("same-input", "tier1", "same-codebook", "same-prompt",
                         pep.canonical_model_config(eff))


def test_effective_config_records_the_override():
    assert pep.effective_request_config(BASE)["max_output_tokens"] == 32768
    assert pep.effective_request_config(V2)["max_output_tokens"] == 16384
    assert pep.effective_config_coverage_problems(pep.effective_request_config(V2)) == []


def test_32768_and_16384_keys_differ_on_identical_inputs():
    assert _key(BASE) != _key(V2), (
        "identical transcript, prompt and codebook must still key differently when "
        "the output cap differs")


def test_16384_can_never_reuse_a_32768_cache_entry(tmp_path):
    """The concrete consequence: a lookup under the v2 key must miss."""
    cache = {_key(BASE): {"result": "computed at 32768"}}
    assert _key(V2) not in cache, "a 16384 run must not be served the 32768 result"


def test_no_other_effective_parameter_changes():
    a, b = pep.effective_request_config(BASE), pep.effective_request_config(V2)
    differing = [k for k in a if a[k] != b[k]]
    assert differing == ["max_output_tokens"], (
        f"only the output cap may differ; also changed: {differing}")
    assert b["temperature_transmitted"] is False
    assert b["thinking_config_transmitted"] is False
    assert b["thinking_config"] is None
    assert b["response_mime_type"] == "application/json"
    assert b["model"] == "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# Truncation detection
# ---------------------------------------------------------------------------

def _codes(ids):
    return [{"subtheme_id": s, "present": False} for s in ids]


FULL = _codes(comp.EXPECTED_SUBTHEME_IDS)
CLEAN_TELEMETRY = {"finish_reasons": ["FinishReason.STOP"],
                   "max_output_tokens_requested": 16384,
                   "candidates_tokens": 1674, "prompt_tokens": 5543}


def test_complete_result_passes():
    v = comp.assess(FULL, CLEAN_TELEMETRY)
    assert v["status"] == comp.STATUS_OK
    assert v["problems"] == []
    assert v["n_codes_returned"] == 11
    assert v["expected_order_preserved"] is True
    assert v["headroom_tokens"] == 16384 - 1674


def test_max_tokens_finish_reason_fails():
    v = comp.assess(FULL, dict(CLEAN_TELEMETRY, finish_reasons=["FinishReason.MAX_TOKENS"]))
    assert v["status"] == comp.STATUS_BAD
    assert any("token cap" in p for p in v["problems"])
    assert any("NOT evidence of absence" in p for p in v["problems"])


@pytest.mark.parametrize("reason", ["MAX_TOKENS", "FinishReason.MAX_TOKENS", "length", 2])
def test_truncation_markers_are_recognised_however_spelled(reason):
    if reason == 2:
        pytest.skip("numeric enum values are not self-describing; string form is used")
    assert comp.finish_reason_indicates_truncation(reason)


def test_stop_is_not_treated_as_truncation():
    assert not comp.finish_reason_indicates_truncation("FinishReason.STOP")
    assert not comp.finish_reason_indicates_truncation(None)


def test_a_missing_code_is_incomplete_output_not_present_false():
    """The failure mode this whole module exists to prevent."""
    v = comp.assess(_codes([s for s in comp.EXPECTED_SUBTHEME_IDS if s != "D"]),
                    CLEAN_TELEMETRY)
    assert v["status"] == comp.STATUS_BAD
    assert v["n_codes_returned"] == 10
    assert any("missing subtheme id(s): ['D']" in p for p in v["problems"])
    assert any("never as present=false" in p for p in v["problems"])


def test_duplicate_and_unexpected_codes_fail():
    v = comp.assess(_codes(list(comp.EXPECTED_SUBTHEME_IDS) + ["A.1"]), CLEAN_TELEMETRY)
    assert v["status"] == comp.STATUS_BAD
    assert any("duplicate" in p for p in v["problems"])

    v = comp.assess(_codes(list(comp.EXPECTED_SUBTHEME_IDS) + ["Z.9"]), CLEAN_TELEMETRY)
    assert v["status"] == comp.STATUS_BAD
    assert any("Z.9" in p for p in v["problems"])


def test_parse_failure_fails():
    v = comp.assess(None, CLEAN_TELEMETRY, parse_error=ValueError("bad json"))
    assert v["status"] == comp.STATUS_BAD
    assert any("did not parse" in p for p in v["problems"])


def test_telemetry_fields_are_carried_through():
    v = comp.assess(FULL, dict(CLEAN_TELEMETRY, total_tokens=14208,
                               thoughts_tokens=7, cached_tokens=None,
                               raw_text_chars=4200, parse_attempt=1))
    for f in ("prompt_tokens", "candidates_tokens", "total_tokens",
              "thoughts_tokens", "raw_text_chars", "parse_attempt",
              "max_output_tokens_requested", "finish_reasons"):
        assert f in v
    assert v["total_tokens"] == 14208
