"""
Truncation and completeness detection for a Tier-1 result.

WHY THIS EXISTS
A smaller output cap does not fail loudly. It produces JSON that stops early, and a
code that never got written looks exactly like a code the evaluator judged absent.
Under `present=false` semantics a truncated response reads as a substantive finding —
"the synthetic group did not express this theme" — which is the single most damaging
way this evaluation could go wrong.

So absence is never inferred. A result is rejected as OUTPUT_TRUNCATED_OR_INCOMPLETE
whenever any of these holds:

  * a candidate finish_reason indicates MAX_TOKENS;
  * any of the 11 codebook subtheme ids is missing from the response;
  * a subtheme id appears more than once;
  * a subtheme id appears that is not in the codebook;
  * the JSON did not parse/validate after the parse retries.

No API call is made here; this inspects a result that already exists.
"""

from __future__ import annotations

from typing import Any

STATUS_OK = "COMPLETE"
STATUS_BAD = "OUTPUT_TRUNCATED_OR_INCOMPLETE"

# The 11 frozen codebook subthemes, in codebook order.
EXPECTED_SUBTHEME_IDS = ("A.1", "A.2", "A.3", "B.1", "B.2", "B.3", "B.4",
                         "C.1", "C.2", "C.3", "D")

_MAX_TOKEN_MARKERS = ("MAX_TOKENS", "MAXTOKENS", "LENGTH")


def finish_reason_indicates_truncation(reason: Any) -> bool:
    """True when the reason names a token-cap stop, however the SDK spells it."""
    if reason is None:
        return False
    text = str(reason).upper()
    return any(m in text for m in _MAX_TOKEN_MARKERS)


def assess(result_codes: list[dict] | None,
           telemetry: dict,
           parse_error: Exception | None = None,
           expected: tuple[str, ...] = EXPECTED_SUBTHEME_IDS) -> dict:
    """
    Returns a verdict dict. `status` is STATUS_OK only when nothing is wrong.

    `result_codes` is the parsed `codes` list, or None when parsing failed.
    """
    problems: list[str] = []

    reasons = telemetry.get("finish_reasons") or []
    truncated_reasons = [r for r in reasons if finish_reason_indicates_truncation(r)]
    if truncated_reasons:
        problems.append(
            f"finish_reason indicates the token cap was hit: {truncated_reasons} "
            f"(max_output_tokens={telemetry.get('max_output_tokens_requested')}). "
            f"Codes absent from this response are NOT evidence of absence.")

    if parse_error is not None:
        problems.append(f"JSON did not parse/validate after parse retries: "
                        f"{type(parse_error).__name__}: {str(parse_error)[:200]}")

    ids: list[str] = []
    if result_codes is None:
        problems.append("no parsed result object to inspect")
    else:
        ids = [str(c.get("subtheme_id")) for c in result_codes]
        missing = [s for s in expected if s not in ids]
        if missing:
            problems.append(
                f"missing subtheme id(s): {missing} — treated as INCOMPLETE OUTPUT, "
                f"never as present=false")
        dupes = sorted({s for s in ids if ids.count(s) > 1})
        if dupes:
            problems.append(f"duplicate subtheme id(s): {dupes}")
        unexpected = [s for s in ids if s not in expected]
        if unexpected:
            problems.append(f"unexpected subtheme id(s) not in the codebook: {unexpected}")

    return {
        "status": STATUS_BAD if problems else STATUS_OK,
        "problems": problems,
        "n_codes_returned": len(ids),
        "n_codes_expected": len(expected),
        "subtheme_ids_returned": ids,
        "expected_order_preserved": ids == list(expected),
        "finish_reasons": reasons,
        "max_output_tokens_requested": telemetry.get("max_output_tokens_requested"),
        "prompt_tokens": telemetry.get("prompt_tokens"),
        "candidates_tokens": telemetry.get("candidates_tokens"),
        "total_tokens": telemetry.get("total_tokens"),
        "thoughts_tokens": telemetry.get("thoughts_tokens"),
        "cached_tokens": telemetry.get("cached_tokens"),
        "raw_text_chars": telemetry.get("raw_text_chars"),
        "parse_attempt": telemetry.get("parse_attempt"),
        "headroom_tokens": (
            None if (telemetry.get("candidates_tokens") is None
                     or telemetry.get("max_output_tokens_requested") is None)
            else telemetry["max_output_tokens_requested"] - telemetry["candidates_tokens"]),
    }
