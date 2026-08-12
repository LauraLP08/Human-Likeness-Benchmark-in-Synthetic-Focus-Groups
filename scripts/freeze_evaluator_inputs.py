"""
Freeze the evaluator inputs for the Macho Meals production evaluation.

Records the exact identity of everything the production evaluator will read, so
that a later run can prove it scored the same material with the same instrument:

  * 5 standardized human transcripts, used COMPLETE (they already begin at
    Question 1 and contain no introduction or closing section);
  * 30 derived synthetic `comparable_transcript.json` windows;
  * the codebook, the evaluator prompts, and the frozen evaluator configuration.

Also emits the per-(input, tier) CACHE KEY. A cached coding may be reused only
when every component of that key matches exactly — transcript hash, codebook
hash, evaluator prompt hash and model configuration. The synthetic side keys on
the COMPARABLE-window hash, never the full-transcript hash, so no full-session
artefact can satisfy a comparable-window lookup.

Read-only with respect to source data: nothing under `output/session_logs/`,
`data/`, `agents/`, `configs/` or `prompts/` is written.

Usage:
    py scripts/freeze_evaluator_inputs.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import thematic_coding as tc                                   # noqa: E402
from phase0_macho_meals_readiness_audit import WHITELIST       # noqa: E402

_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation"
_DERIVED_DIR = _OUT_DIR / "comparable_transcripts"
_HUMAN_DIR = _REPO_ROOT / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
_CODEBOOK = _REPO_ROOT / "analysis" / "coding_frame" / "CodeBook_Macho Meals.xlsx"

# Frozen production evaluator — docs/findings/2026-07-18_evaluator_model_comparison.md
EVALUATOR_KEY = "gemininext"


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _counts(entries: list[dict]) -> dict:
    mod = [e for e in entries
           if (e.get("speaker_name") or e.get("speaker_role") or "").lower() == "moderator"]
    par = [e for e in entries if e not in mod]
    return {
        "entries": len(entries),
        "moderator_turns": len(mod),
        "participant_turns": len(par),
        "total_words": sum(len((e.get("content") or "").split()) for e in entries),
        "participant_words": sum(len((e.get("content") or "").split()) for e in par),
        "distinct_participants": len({
            e.get("speaker_name") or e.get("speaker_id") for e in par
        }),
    }


def cache_key(transcript_sha: str, tier: str, codebook_sha: str,
              prompt_sha: str, model_cfg: str) -> str:
    """Cache key = transcript hash + codebook hash + evaluator prompt hash + model config."""
    return hashlib.sha256(
        "|".join([transcript_sha, tier, codebook_sha, prompt_sha, model_cfg]).encode()
    ).hexdigest()


def effective_request_config(ecfg: dict) -> dict:
    """
    The configuration ACTUALLY transmitted to the API, not the labels recorded in
    EVALUATOR_CONFIGS.

    `thematic_coding` attaches a `thinking_config` only when "2.5" is in the model
    id. For `gemini-3.5-flash` nothing is sent, so `thinking_level` is a logging
    label and the effective value is the model default. `temperature` is likewise
    omitted from the request when the config carries None.

    The cache key is built from THIS dict, so a key can never claim a parameter
    that was not actually sent.
    """
    model = ecfg["model"]
    sends_thinking = "2.5" in model
    return {
        "model": model,
        "temperature_transmitted": ecfg.get("temperature") is not None,
        "temperature": ecfg.get("temperature"),
        "thinking_config_transmitted": sends_thinking,
        "thinking_level_effective": (
            ecfg.get("thinking_level") if sends_thinking else "model_default_unpinned"),
        "thinking_level_label_in_config": ecfg.get("thinking_level"),
    }


def main() -> None:
    ecfg = tc.EVALUATOR_CONFIGS[EVALUATOR_KEY]
    effective = effective_request_config(ecfg)
    model_cfg = json.dumps(effective, sort_keys=True)

    codebook_sha = _sha_file(_CODEBOOK)
    prompts = {
        "tier1": _sha_text(tc._TIER1_SYSTEM),
        "tier2": _sha_text(tc._TIER2_SYSTEM),
        "tier2_judge": _sha_text(tc._TIER2_JUDGE_SYSTEM),
    }

    human_inputs = []
    for fg in ("fg1", "fg2", "fg3", "fg4", "fg5"):
        p = _HUMAN_DIR / fg / "transcript.json"
        entries = json.loads(p.read_text(encoding="utf-8"))
        sha = _sha_file(p)
        human_inputs.append({
            "side": "human",
            "fg": fg,
            "path": str(p.relative_to(_REPO_ROOT)),
            "sha256": sha,
            "window": "complete_standardized_transcript",
            "window_rationale": (
                "The standardized human transcript already begins at 'Question 1.' and "
                "contains no general introduction, no participant name/location round and "
                "no formal closing section, so no window is applied."),
            **_counts(entries),
            "cache_keys": {t: cache_key(sha, t, codebook_sha, prompts[t], model_cfg)
                           for t in prompts},
        })

    synth_inputs = []
    for cond, fg, rep, run in WHITELIST:
        p = _DERIVED_DIR / run / "comparable_transcript.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        prov = payload["_provenance"]
        entries = payload["transcript"]
        sha = _sha_file(p)
        synth_inputs.append({
            "side": "synthetic",
            "condition": cond,
            "fg": fg,
            "canonical_replication_index": rep,
            "physical_run": run,
            "path": str(p.relative_to(_REPO_ROOT)),
            "sha256": sha,
            "window": prov["window"],
            "boundary_algorithm": prov.get("boundary_algorithm"),
            "source_transcript": prov["source_transcript"],
            "source_transcript_sha256": prov["source_transcript_sha256"],
            "source_entry_index": prov["source_entry_index"],
            "source_character_start": prov["source_character_start"],
            "original_boundary_entry_sha256": prov["original_boundary_entry_sha256"],
            "retained_boundary_text_sha256": prov["retained_boundary_text_sha256"],
            "boundary_review_status": prov["boundary_review_status"],
            **_counts(entries),
            "cache_keys": {t: cache_key(sha, t, codebook_sha, prompts[t], model_cfg)
                           for t in prompts},
        })

    payload = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "study": "macho_meals",
        "status": "FROZEN — approved at Mandatory Human Stop 1 and boundary sign-off",
        "evaluator": {
            "config_key": EVALUATOR_KEY,
            "model": ecfg["model"],
            "key_env": ecfg.get("key_env"),
            "basis": "docs/findings/2026-07-18_evaluator_model_comparison.md",
            "effective_request_config": effective,
            "thinking_level_resolution": (
                "RESOLVED, unpinned. The SDK (google-genai 2.10.0) DOES support pinning "
                "via types.ThinkingConfig(thinking_level=ThinkingLevel.MEDIUM), but "
                "thematic_coding.py attaches a thinking_config only when '2.5' is in the "
                "model id, so nothing is transmitted for gemini-3.5-flash. The "
                "'thinking_level: medium' in EVALUATOR_CONFIGS is therefore a LOGGING "
                "LABEL, not a request parameter. Critically, the evaluator-selection "
                "validation (validation_stage1_gemininext.json) ran under this same "
                "unpinned path, so the 100% Gate-1 result that qualified this model was "
                "obtained with the model default — NOT with a pinned MEDIUM. The frozen "
                "configuration is therefore recorded as explicitly unpinned/default, "
                "which is the configuration that was actually validated. Pinning MEDIUM "
                "is technically available but would run production under a configuration "
                "that has never been validated; that is a researcher decision."),
        },
        "codebook": {"path": str(_CODEBOOK.relative_to(_REPO_ROOT)),
                     "sha256": codebook_sha,
                     "subthemes": len(tc.load_codebook())},
        "evaluator_prompt_sha256": prompts,
        "cache_key_definition": (
            "sha256(transcript_sha256 | tier | codebook_sha256 | evaluator_prompt_sha256 "
            "| model_config_json). Reuse requires an exact match on every component. The "
            "synthetic side keys on the COMPARABLE-WINDOW hash, never the full-transcript "
            "hash, so no full-session artefact can satisfy a comparable-window lookup."),
        "prior_artefacts_not_reusable": (
            "Every coding artefact currently in analysis/coding_frame/ was produced with "
            "gemini-2.5-flash (pilot/historical) except validation_stage1_gemininext.json, "
            "which is gemini-3.5-flash evaluator-selection evidence over different "
            "material. None satisfies these cache keys; production Tier 1 is coded fresh."),
        "evaluator_receives_only": [
            "the 5 complete standardized human transcripts",
            "the 30 derived synthetic comparable_transcript.json windows",
        ],
        "human_inputs": human_inputs,
        "synthetic_inputs": synth_inputs,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _OUT_DIR / "frozen_evaluator_inputs.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Frozen {len(human_inputs)} human + {len(synth_inputs)} synthetic inputs")
    print(f"  evaluator : {ecfg['model']} (thinking_level={ecfg.get('thinking_level')})")
    print(f"  codebook  : {codebook_sha[:16]}  ({len(tc.load_codebook())} subthemes)")
    print(f"  prompts   : " + "  ".join(f"{k}={v[:12]}" for k, v in prompts.items()))
    print(f"  wrote {out.relative_to(_REPO_ROOT)}")

    # Human vs synthetic volume, per FG — a structural asymmetry the spec must carry.
    print("\n  Volume asymmetry (total words, human complete vs synthetic window):")
    print(f"    {'FG':<5}{'human':>8}{'enr mean':>11}{'demo mean':>11}{'enr/human':>11}")
    for fg in ("fg1", "fg2", "fg3", "fg4", "fg5"):
        h = next(x["total_words"] for x in human_inputs if x["fg"] == fg)
        e = [x["total_words"] for x in synth_inputs
             if x["fg"] == fg and x["condition"] == "enriched"]
        d = [x["total_words"] for x in synth_inputs
             if x["fg"] == fg and x["condition"] == "demographics-only"]
        print(f"    {fg:<5}{h:>8,}{sum(e)/len(e):>11,.0f}{sum(d)/len(d):>11,.0f}"
              f"{sum(e)/len(e)/h:>10.1f}x")


if __name__ == "__main__":
    main()
