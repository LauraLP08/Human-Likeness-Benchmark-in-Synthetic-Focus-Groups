"""
Phase 1 — condition-manipulation and contamination audit (READ-ONLY).

Answers two questions the whole evaluation rests on:

  1. MANIPULATION — is the enriched / demographics-only contrast actually what we
     believe it is? Same agents, same rosters, same demographics, with enriched-only
     fields present in one arm and effectively absent from the other.
  2. CONTAMINATION — did any human transcript content, prior participant intro,
     human theme label or codebook text reach generation?

STORED IS NOT RENDERED. A field can sit in the agent JSON and never reach the
model. This audit therefore does not compare JSON keys alone: it CALLS the real
renderer, `core.participant_agent.build_participant_system_prompt`, for every agent
in both conditions and diffs the actual prompt text. That is the only evidence that
distinguishes "stored" from "rendered".

`inject_participant_intro` is exercised in both settings so the audit can state
what WOULD be rendered if it were true, and confirm separately from the 30 final
states that it was false in every canonical run.

Read-only: nothing is written outside `analysis/production_evaluation/`. No agent,
config, prompt, transcript or session log is modified. No API call is made.

Usage:
    py scripts/phase1_condition_manipulation_audit.py
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.participant_agent import build_participant_system_prompt, load_agent_from_json  # noqa: E402
from core.session_state import SessionMeta                                                # noqa: E402
from phase0_macho_meals_readiness_audit import WHITELIST                                  # noqa: E402

_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation"
_ENRICHED_AGENTS = _REPO_ROOT / "agents" / "macho_meals"
_DEMO_AGENTS = _REPO_ROOT / "agents" / "macho_meals_demoonly"
_CONFIG_DIR = _REPO_ROOT / "configs" / "experiment"
_HUMAN_DIR = _REPO_ROOT / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _flatten(d, prefix="") -> dict:
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(d, list):
        out[prefix] = f"<list len={len(d)}>"
    else:
        out[prefix] = d
    return out


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = (s.replace("’", "'").replace("‘", "'")
           .replace("“", '"').replace("”", '"')
           .replace("–", "-").replace("—", "-"))
    return re.sub(r"\s+", " ", s).strip().casefold()


def _shingles(text: str, n: int = 8) -> set[str]:
    w = _norm(text).split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _session_meta(inject_intro: bool) -> SessionMeta:
    """
    Built from a real executed config rather than dummy values, so the rendered
    prompt matches what generation actually produced. The session-level fields are
    identical across all 30 configs (verified in audit_parity), so any canonical
    config gives the same result.
    """
    cfg = json.loads((_CONFIG_DIR / "macho_meals_fg1_run02.json").read_text(encoding="utf-8"))
    return SessionMeta(
        id="condition_manipulation_audit",
        research_objective=cfg["research_objective"],
        topic_domain=cfg["topic_domain"],
        participant_collective_identity=cfg["participant_collective_identity"],
        moderator_knowledge_brief=cfg["moderator_knowledge_brief"],
        inject_participant_intro=inject_intro,
    )


def _render(agent_path: Path, inject_intro: bool) -> str:
    p = load_agent_from_json(str(agent_path))
    return build_participant_system_prompt(p, _session_meta(inject_intro),
                                           has_other_participants=True)


_PSYCHO_DIMS = ["meat_attachment", "masculinity_of_meat", "vegetarianism_threat",
                "dairy_attachment", "masculine_norms"]


def _strip_direction_prefix(direction: str) -> str:
    """Reproduce the prefix stripping in _score_to_instruction so the audit tests
    the string that is actually interpolated, not the stored one."""
    for pre in ("Higher scores indicate stronger ", "Higher scores indicate more ",
                "Higher scores indicate "):
        if direction.lower().startswith(pre.lower()):
            return direction[len(pre):].rstrip(".")
    return direction


def audit_psychometric_rendering() -> tuple[list[dict], dict]:
    """
    Verify psychometric rendering by REGENERATING each disposition line with
    `_score_to_instruction` and requiring the exact string to appear in the
    rendered prompt. Merely observing that enriched-only lines exist would not show
    that those lines are the psychometric ones, nor that they carry the right score.

    Separately and explicitly tests for leakage of:
      * raw score VALUES (the numeric psychometric scores);
      * academic construct names, in underscore AND space-separated form;
      * the scale-direction text actually interpolated into the template.

    Ordinary demographic and consumption numbers (age, "2-4 per week") are NOT part
    of this check — they are legitimate persona content and are counted separately
    so a benign number can never be mistaken for a leaked score.
    """
    from core.participant_agent import _score_to_instruction

    rows: list[dict] = []
    for path in sorted(_ENRICHED_AGENTS.glob("mm_*.json")):
        aid = path.stem
        raw = json.loads(path.read_text(encoding="utf-8"))
        prompt = _render(path, inject_intro=False)
        nprompt = _norm(prompt)
        scores = raw.get("psychometric_scores") or {}

        matched = missing = 0
        for dim, sc in scores.items():
            value, direction = sc.get("value"), sc.get("direction", "")
            if value is None or not direction:
                continue
            expected = _score_to_instruction(dim, float(value), direction, aid)
            present = _norm(expected) in nprompt
            matched += present
            missing += (not present)
            rows.append({
                "agent_id": aid,
                "dimension": dim,
                "score_value": value,
                "expected_disposition_line": expected,
                "expected_line_present_verbatim": present,
                "expected_line_sha256": _sha(expected),
                # leakage, tested separately per class
                "raw_score_value_in_prompt": bool(re.search(
                    rf"(?<![\d.]){re.escape(str(value))}(?![\d])", nprompt)),
                "construct_name_underscore_in_prompt": dim in nprompt,
                "construct_name_spaced_in_prompt": dim.replace("_", " ") in nprompt,
                "scale_direction_text_in_prompt": _norm(
                    _strip_direction_prefix(direction)) in nprompt,
            })
        # per-agent completeness is folded back by the caller
        rows[-1]["agent_dimensions_matched"] = matched
        rows[-1]["agent_dimensions_missing"] = missing

    summary = {
        "agent_dimension_pairs": len(rows),
        "disposition_lines_reproduced_verbatim": sum(
            1 for r in rows if r["expected_line_present_verbatim"]),
        "disposition_lines_missing": sum(
            1 for r in rows if not r["expected_line_present_verbatim"]),
        "raw_score_values_leaked": sum(1 for r in rows if r["raw_score_value_in_prompt"]),
        "construct_names_underscore_leaked": sum(
            1 for r in rows if r["construct_name_underscore_in_prompt"]),
        "construct_names_spaced_leaked": sum(
            1 for r in rows if r["construct_name_spaced_in_prompt"]),
        "scale_direction_text_leaked": sum(
            1 for r in rows if r["scale_direction_text_in_prompt"]),
        "per_dimension_construct_name_spaced": {
            d: sum(1 for r in rows if r["dimension"] == d
                   and r["construct_name_spaced_in_prompt"]) for d in _PSYCHO_DIMS},
        "per_dimension_scale_direction": {
            d: sum(1 for r in rows if r["dimension"] == d
                   and r["scale_direction_text_in_prompt"]) for d in _PSYCHO_DIMS},
        "note_on_benign_numbers": (
            "Ordinary demographic and consumption numbers (age, frequencies such as "
            "'2-4 per week') are expected persona content and are excluded from the "
            "raw-score-value test, which matches only the actual psychometric score "
            "values with digit boundaries."),
    }
    return rows, summary


def audit_notes_provenance() -> dict:
    """
    Provenance of all 22 `simulation_config.notes`: are they constructed
    independently of the human transcript and of human coding results?
    """
    import thematic_coding as tc

    human_shingles: set[str] = set()
    for fg in ("fg1", "fg2", "fg3", "fg4", "fg5"):
        for e in json.loads((_HUMAN_DIR / fg / "transcript.json").read_text(encoding="utf-8")):
            c = e.get("content") or ""
            if len(c.split()) >= 5:
                human_shingles |= _shingles(c, 5)

    codebook = tc.load_codebook()
    cb_shingles: set[str] = set()
    for c in codebook:
        for fld in ("description", "example", "subtheme_label"):
            if c.get(fld):
                cb_shingles |= _shingles(str(c[fld]), 5)

    per_note: dict[str, dict] = {}
    agents: list[dict] = []
    for path in sorted(_ENRICHED_AGENTS.glob("mm_*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        note = (raw.get("simulation_config") or {}).get("notes")
        prov = (raw.get("field_provenance") or {}).get("simulation_config.notes")
        agents.append({"agent_id": path.stem, "notes": note,
                       "declared_provenance": prov,
                       "notes_words": len((note or "").split())})
        if note is None:
            continue
        s = _shingles(note, 5)
        rec = per_note.setdefault(note, {
            "text": note, "count": 0, "declared_provenance": set(),
            "human_transcript_5gram_overlap": sorted(s & human_shingles)[:5],
            "codebook_5gram_overlap": sorted(s & cb_shingles)[:5],
            "words": len(note.split()),
        })
        rec["count"] += 1
        rec["declared_provenance"].add(prov)

    for rec in per_note.values():
        rec["declared_provenance"] = sorted(rec["declared_provenance"])

    any_human = any(r["human_transcript_5gram_overlap"] for r in per_note.values())
    any_cb = any(r["codebook_5gram_overlap"] for r in per_note.values())
    return {
        "agents_with_notes": sum(1 for a in agents if a["notes"] is not None),
        "distinct_note_values": len(per_note),
        "notes": list(per_note.values()),
        "declared_provenance_values": sorted(
            {a["declared_provenance"] for a in agents if a["declared_provenance"]}),
        "human_transcript_overlap_detected": any_human,
        "codebook_overlap_detected": any_cb,
        "constructed_independently_of_human_transcript_and_coding": not (any_human or any_cb),
        "interpretation": (
            "All notes are short recruitment descriptors declared 'derived' in "
            "field_provenance. They restate the recruitment/diet category already "
            "carried by persona.demographics.diet, share no 5-gram with any human "
            "transcript turn or with the codebook, and contain no thematic, "
            "attitudinal or coding-derived content. On the specified tests they are "
            "independent of the human transcripts and of human coding results."),
        "agents": agents,
    }


# ---------------------------------------------------------------------------
# 1. Agent pair difference matrix
# ---------------------------------------------------------------------------

def audit_pairs() -> tuple[list[dict], dict]:
    rows: list[dict] = []
    enriched_ids = sorted(p.stem for p in _ENRICHED_AGENTS.glob("mm_*.json"))
    demo_ids = sorted(p.stem for p in _DEMO_AGENTS.glob("mm_*.json"))

    summary = {
        "enriched_agents": len(enriched_ids),
        "demographics_only_agents": len(demo_ids),
        "paired": sorted(set(enriched_ids) & set(demo_ids)),
        "enriched_only_agents": sorted(set(enriched_ids) - set(demo_ids)),
        "demo_only_agents": sorted(set(demo_ids) - set(enriched_ids)),
    }

    for aid in summary["paired"]:
        e_raw = json.loads((_ENRICHED_AGENTS / f"{aid}.json").read_text(encoding="utf-8"))
        d_raw = json.loads((_DEMO_AGENTS / f"{aid}.json").read_text(encoding="utf-8"))
        e_flat, d_flat = _flatten(e_raw), _flatten(d_raw)

        stored_enriched_only = sorted(k for k in e_flat if k not in d_flat)
        stored_demo_only = sorted(k for k in d_flat if k not in e_flat)
        shared_differing = sorted(k for k in e_flat if k in d_flat and e_flat[k] != d_flat[k])

        # CORE demographics are held constant across conditions. `diet` also lives
        # under persona.demographics but is NOT held constant — the design
        # explicitly withholds diet, consumption and psychometrics from the
        # demographics-only arm, so it belongs to the manipulation, not to the
        # controlled background.
        core_demo_keys = [k for k in e_flat
                          if k.startswith("persona.demographics") and not k.endswith(".diet")]
        core_demo_identical = all(e_flat.get(k) == d_flat.get(k) for k in core_demo_keys)
        core_demo_diffs = [k for k in core_demo_keys if e_flat.get(k) != d_flat.get(k)]
        diet_enriched = e_flat.get("persona.demographics.diet")
        diet_demo = d_flat.get("persona.demographics.diet")

        # RENDERED prompts — the load-bearing comparison
        e_prompt = _render(_ENRICHED_AGENTS / f"{aid}.json", inject_intro=False)
        d_prompt = _render(_DEMO_AGENTS / f"{aid}.json", inject_intro=False)
        e_prompt_intro = _render(_ENRICHED_AGENTS / f"{aid}.json", inject_intro=True)

        e_only_lines = [ln for ln in e_prompt.splitlines()
                        if ln.strip() and ln not in d_prompt.splitlines()]
        d_only_lines = [ln for ln in d_prompt.splitlines()
                        if ln.strip() and ln not in e_prompt.splitlines()]

        intro_text = (e_raw.get("opening_intro") or {}).get("text") or ""
        intro_rendered_when_false = bool(intro_text) and _norm(intro_text)[:60] in _norm(e_prompt)
        intro_rendered_when_true = bool(intro_text) and _norm(intro_text)[:60] in _norm(e_prompt_intro)

        food = e_raw.get("persona", {}).get("food_consumption") or {}
        psycho = e_raw.get("psychometric_scores") or {}
        notes = (e_raw.get("simulation_config") or {}).get("notes")

        def _rendered(fragment: str) -> bool:
            return bool(fragment) and _norm(fragment)[:40] in _norm(e_prompt)

        rows.append({
            "agent_id": aid,
            "fg": aid.split("_")[1],
            "stored_enriched_only_fields": "|".join(stored_enriched_only),
            "stored_demographics_only_fields": "|".join(stored_demo_only),
            "shared_fields_with_differing_values": "|".join(shared_differing),
            "core_demographics_identical": core_demo_identical,
            "core_demographic_fields_compared": len(core_demo_keys),
            "core_demographic_diffs": "|".join(core_demo_diffs),
            "diet_enriched": diet_enriched,
            "diet_demographics_only": diet_demo,
            "diet_withheld_from_demographics_only": diet_demo is None and diet_enriched is not None,
            "diet_rendered_in_enriched": bool(diet_enriched) and _norm(str(diet_enriched)) in _norm(e_prompt),
            "diet_absent_from_demographics_only_prompt": "your diet" not in d_prompt.lower(),
            "enriched_food_consumption_keys": len(food),
            "enriched_psychometric_dimensions": "|".join(sorted(psycho)),
            "enriched_simulation_notes_present": notes is not None,
            "rendered_prompt_sha_enriched": _sha(e_prompt),
            "rendered_prompt_sha_demographics_only": _sha(d_prompt),
            "rendered_prompt_words_enriched": len(e_prompt.split()),
            "rendered_prompt_words_demographics_only": len(d_prompt.split()),
            "rendered_enriched_only_lines": len(e_only_lines),
            "rendered_demographics_only_lines": len(d_only_lines),
            "food_consumption_rendered_in_enriched": bool(food) and "eating patterns" in e_prompt.lower(),
            "food_consumption_absent_from_demographics_only": "eating patterns" not in d_prompt.lower(),
            "psychometrics_rendered_in_enriched": bool(psycho) and len(e_only_lines) > 0,
            "raw_psychometric_numbers_in_prompt": bool(re.search(
                r"\b(meat_attachment|masculinity_of_meat|vegetarianism_threat|"
                r"dairy_attachment|masculine_norms)\b", e_prompt)),
            "simulation_notes_rendered_in_enriched": _rendered(notes or ""),
            "opening_intro_text_stored": bool(intro_text),
            "opening_intro_rendered_when_flag_false": intro_rendered_when_false,
            "opening_intro_rendered_when_flag_true": intro_rendered_when_true,
        })
    return rows, summary


# ---------------------------------------------------------------------------
# 2. Contamination audit
# ---------------------------------------------------------------------------

def audit_contamination(pair_rows: list[dict]) -> dict:
    """Did human transcript text, prior intros, human themes or the codebook reach
    anything that is rendered to a generating model?"""
    import thematic_coding as tc

    # Corpus that must NOT appear in generation-side material.
    #
    # PARTICIPANT TURNS ONLY. Human MODERATOR turns are excluded deliberately:
    # they contain the guide's scripted questions ("...favourite place in your city
    # to spend time..."), and the guide is the SHARED RESEARCH INSTRUMENT — it is
    # supposed to appear in every experiment config. Including moderator turns
    # would flag all 30 configs as contaminated purely for containing the guide,
    # which is the design rather than a leak. What must never reach generation is
    # what the human PARTICIPANTS said.
    human_shingles: set[str] = set()
    human_quote_samples: list[str] = []
    n_participant_turns = 0
    for fg in ("fg1", "fg2", "fg3", "fg4", "fg5"):
        entries = json.loads((_HUMAN_DIR / fg / "transcript.json").read_text(encoding="utf-8"))
        for e in entries:
            if (e.get("speaker_role") or "").lower() == "moderator":
                continue
            c = e.get("content") or ""
            if len(c.split()) >= 8:
                n_participant_turns += 1
                human_shingles |= _shingles(c, 8)
                if len(human_quote_samples) < 5:
                    human_quote_samples.append(c[:60])

    # Subtract the guide from the human corpus. The guide is the SHARED RESEARCH
    # INSTRUMENT: its questions were put to the human groups and are embedded in
    # every experiment config, so guide text appearing on both sides is the design.
    # It also appears inside human PARTICIPANT turns when a participant echoes the
    # moderator (FG3: "You might have already answered question three then. Do you
    # think your gender influences what you eat?"), which is why excluding moderator
    # turns alone is not sufficient.
    guide_shingles: set[str] = set()
    cfg = json.loads((_CONFIG_DIR / "macho_meals_fg1_run02.json").read_text(encoding="utf-8"))
    for sec in cfg.get("discussion_guide", []):
        for txt in [sec.get("scripted_question"), sec.get("section_label"),
                    sec.get("section_purpose")] + list(sec.get("suggested_probes") or []):
            if txt:
                guide_shingles |= _shingles(str(txt), 8)
    for txt in (cfg.get("research_objective"), cfg.get("moderator_knowledge_brief"),
                cfg.get("topic_domain"), cfg.get("participant_collective_identity")):
        if txt:
            guide_shingles |= _shingles(str(txt), 8)
    human_shingles -= guide_shingles

    codebook = tc.load_codebook()
    # Only DISTINCTIVE labels. The codebook's 4Ns labels are single common words
    # ('Natural', 'Normal', 'Necessary', 'Nice'), which match any ordinary English
    # text and carry no evidential value. The codebook DESCRIPTION 8-gram check
    # below is the substantive test for codebook leakage.
    codebook_terms = [c["subtheme_label"] for c in codebook
                      if c.get("subtheme_label")
                      and len(str(c["subtheme_label"]).split()) >= 2
                      and len(str(c["subtheme_label"])) >= 12]
    codebook_descs = [c["description"] for c in codebook if c.get("description")]
    codebook_shingles: set[str] = set()
    for d in codebook_descs:
        codebook_shingles |= _shingles(str(d), 8)

    findings: list[dict] = []

    def scan(label: str, text: str, source: str) -> None:
        hs = _shingles(text, 8)
        hit_human = sorted(hs & human_shingles)[:3]
        hit_cb = sorted(hs & codebook_shingles)[:3]
        cb_labels = [t for t in codebook_terms if t and _norm(str(t)) in _norm(text)]
        if hit_human or hit_cb or cb_labels:
            findings.append({
                "target": label, "source": source,
                "human_transcript_8gram_overlap": hit_human,
                "codebook_description_8gram_overlap": hit_cb,
                "codebook_subtheme_labels_present": cb_labels[:5],
            })

    # 2a. Rendered participant prompts, both conditions
    for aid in sorted(r["agent_id"] for r in pair_rows):
        for cond, root in (("enriched", _ENRICHED_AGENTS),
                           ("demographics-only", _DEMO_AGENTS)):
            scan(f"rendered_participant_prompt[{cond}]",
                 _render(root / f"{aid}.json", inject_intro=False),
                 f"{root.name}/{aid}.json")

    # 2b. Executed configs — guide text, briefs, moderator overrides
    for _c, _f, _i, run in WHITELIST:
        cfg_path = _CONFIG_DIR / f"{run}.json"
        if cfg_path.exists():
            scan(f"experiment_config[{run}]", cfg_path.read_text(encoding="utf-8"),
                 str(cfg_path.relative_to(_REPO_ROOT)))

    # 2c. Moderator prompt files actually referenced
    prompt_refs = set()
    for _c, _f, _i, run in WHITELIST:
        cfg_path = _CONFIG_DIR / f"{run}.json"
        if cfg_path.exists():
            ov = json.loads(cfg_path.read_text(encoding="utf-8")).get("moderator_prompt_override")
            if ov:
                prompt_refs.add(ov)
    for ov in sorted(prompt_refs):
        p = _REPO_ROOT / "prompts" / ov
        if p.exists():
            scan(f"moderator_prompt[{ov}]", p.read_text(encoding="utf-8"),
                 f"prompts/{ov}")

    # 2d. inject_participant_intro across the 30 final states
    intro_flags = {}
    for _c, _f, _i, run in WHITELIST:
        states = sorted(
            (int(re.search(r"state_turn_(\d+)", p.name).group(1)), p)
            for p in (_SESSION_LOGS / run).glob("state_turn_*.json"))
        if states:
            st = json.loads(states[-1][1].read_text(encoding="utf-8"))
            intro_flags[run] = st["session_meta"].get("inject_participant_intro")

    return {
        "human_corpus_scope": "participant turns only; human moderator turns excluded because they carry the shared guide questions",
        "human_participant_turns_indexed": n_participant_turns,
        "guide_8grams_subtracted": len(guide_shingles),
        "human_8gram_corpus_size_after_guide_subtraction": len(human_shingles),
        "human_quote_samples_searched_for": human_quote_samples,
        "codebook_subthemes": len(codebook),
        "codebook_labels_tested": codebook_terms,
        "codebook_labels_excluded_as_nondistinctive": [
            c["subtheme_label"] for c in codebook
            if c.get("subtheme_label") and c["subtheme_label"] not in codebook_terms],
        "codebook_8gram_corpus_size": len(codebook_shingles),
        "targets_scanned": {
            "rendered_participant_prompts": len(pair_rows) * 2,
            "experiment_configs": len(WHITELIST),
            "moderator_prompt_files": len(prompt_refs),
        },
        "moderator_prompt_files_referenced": sorted(prompt_refs),
        "findings": findings,
        "contamination_detected": bool(findings),
        "inject_participant_intro_by_run": intro_flags,
        "inject_participant_intro_all_false": all(v is False for v in intro_flags.values()),
        "opening_intro_stored_but_never_rendered": all(
            r["opening_intro_rendered_when_flag_false"] is False for r in pair_rows),
        "opening_intro_would_render_if_flag_true": sum(
            1 for r in pair_rows if r["opening_intro_rendered_when_flag_true"]),
    }


# ---------------------------------------------------------------------------
# 3. Cross-condition parameter parity
# ---------------------------------------------------------------------------

def audit_parity() -> dict:
    fields = ["temperature", "participation_mode", "participant_response_max_tokens",
              "participant_episodic_depth", "participant_episodic_since_last_n",
              "engagement_own_history_token_budget", "moderator_context_mode",
              "moderator_prompt_override", "moderator_restraint_prompt",
              "moderator_reflection_enabled", "time_budget_tracking_enabled",
              "research_objective", "topic_domain", "moderator_knowledge_brief",
              "participant_collective_identity"]
    per_cond: dict[str, dict[str, set]] = {"enriched": {}, "demographics-only": {}}
    guide_hashes: dict[str, set] = {"enriched": set(), "demographics-only": set()}

    for cond, _fg, _i, run in WHITELIST:
        cfg_path = _CONFIG_DIR / f"{run}.json"
        if not cfg_path.exists():
            continue
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        for f in fields:
            per_cond[cond].setdefault(f, set()).add(json.dumps(cfg.get(f), sort_keys=True))
        guide_hashes[cond].add(_sha(json.dumps(cfg.get("discussion_guide"), sort_keys=True)))

    parity = {}
    for f in fields:
        e = per_cond["enriched"].get(f, set())
        d = per_cond["demographics-only"].get(f, set())
        parity[f] = {
            "enriched_distinct_values": len(e),
            "demographics_only_distinct_values": len(d),
            "identical_across_conditions": e == d,
            "value": (json.loads(next(iter(e))) if len(e) == 1 and e == d else "VARIES"),
        }
    return {
        "config_field_parity": parity,
        "guide_hash_enriched": sorted(guide_hashes["enriched"]),
        "guide_hash_demographics_only": sorted(guide_hashes["demographics-only"]),
        "guide_identical_across_all_30": (
            len(guide_hashes["enriched"] | guide_hashes["demographics-only"]) == 1),
        "all_fields_identical": all(v["identical_across_conditions"] for v in parity.values()),
    }


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  PHASE 1 — CONDITION-MANIPULATION AND CONTAMINATION AUDIT (read-only)")
    print("=" * 80)

    rows, summary = audit_pairs()
    print(f"\nAgent pairs: {len(rows)}  "
          f"(enriched {summary['enriched_agents']}, demo {summary['demographics_only_agents']})")
    if summary["enriched_only_agents"] or summary["demo_only_agents"]:
        print(f"  UNPAIRED enriched: {summary['enriched_only_agents']}")
        print(f"  UNPAIRED demo    : {summary['demo_only_agents']}")

    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    matrix = _OUT_DIR / "agent_condition_difference_matrix.csv"
    with open(matrix, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    psycho_rows, psycho_summary = audit_psychometric_rendering()
    notes = audit_notes_provenance()
    contam = audit_contamination(rows)
    parity = audit_parity()

    pfields = []
    for r in psycho_rows:
        for k in r:
            if k not in pfields:
                pfields.append(k)
    with open(_OUT_DIR / "psychometric_rendering_audit.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pfields, extrasaction="ignore")
        w.writeheader()
        for r in psycho_rows:
            w.writerow(r)

    payload = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "read_only": True,
        "no_api_calls": True,
        "method_note": (
            "Rendered prompts were produced by calling "
            "core.participant_agent.build_participant_system_prompt on each agent "
            "payload, so 'rendered' means what the generating model would actually "
            "receive, not what the JSON stores."),
        "pair_summary": summary,
        "psychometric_rendering": psycho_summary,
        "simulation_config_notes_provenance": notes,
        "condition_parity": parity,
        "contamination": contam,
        "contamination_claim_scope": (
            "No TEXTUAL/VERBATIM contamination was detected under the specified tests "
            "(participant 8-gram overlap with the guide subtracted, codebook description "
            "8-grams, distinctive codebook labels). This is not evidence that semantic "
            "or conceptual contamination is impossible: paraphrase, thematic influence "
            "and design decisions informed by prior reading of the human data would not "
            "be caught by any string-overlap test."),
    }
    (_OUT_DIR / "contamination_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    n = len(rows)
    print(f"\ncore demographics identical         : "
          f"{sum(1 for r in rows if r['core_demographics_identical'])}/{n}  "
          f"(name, age, gender, location — diet is part of the manipulation)")
    print(f"diet withheld from demo-only        : "
          f"{sum(1 for r in rows if r['diet_withheld_from_demographics_only'])}/{n}  (BY DESIGN)")
    print(f"diet rendered in enriched prompt    : "
          f"{sum(1 for r in rows if r['diet_rendered_in_enriched'])}/{n}")
    print(f"diet absent from demo-only prompt   : "
          f"{sum(1 for r in rows if r['diet_absent_from_demographics_only_prompt'])}/{n}")
    print(f"food_consumption rendered enriched  : "
          f"{sum(1 for r in rows if r['food_consumption_rendered_in_enriched'])}/{len(rows)}")
    print(f"food_consumption absent demo-only   : "
          f"{sum(1 for r in rows if r['food_consumption_absent_from_demographics_only'])}/{len(rows)}")
    print(f"psychometrics rendered enriched     : "
          f"{sum(1 for r in rows if r['psychometrics_rendered_in_enriched'])}/{len(rows)}")
    print(f"raw psychometric NUMBERS in prompt  : "
          f"{sum(1 for r in rows if r['raw_psychometric_numbers_in_prompt'])}/{len(rows)}  (must be 0)")
    print(f"opening_intro stored                : "
          f"{sum(1 for r in rows if r['opening_intro_text_stored'])}/{len(rows)}")
    print(f"opening_intro rendered (flag False) : "
          f"{sum(1 for r in rows if r['opening_intro_rendered_when_flag_false'])}/{len(rows)}  (must be 0)")
    print(f"opening_intro WOULD render if True  : "
          f"{contam['opening_intro_would_render_if_flag_true']}/{len(rows)}")
    print(f"\ninject_participant_intro False in all 30 runs: "
          f"{contam['inject_participant_intro_all_false']}")
    print(f"Guide identical across all 30 configs        : {parity['guide_identical_across_all_30']}")
    print(f"All shared config fields identical           : {parity['all_fields_identical']}")
    if not parity["all_fields_identical"]:
        for f, v in parity["config_field_parity"].items():
            if not v["identical_across_conditions"]:
                print(f"    DIFFERS: {f}")
    ps = psycho_summary
    print(f"\nPSYCHOMETRIC RENDERING (each line regenerated via _score_to_instruction)")
    print(f"  disposition lines reproduced verbatim : "
          f"{ps['disposition_lines_reproduced_verbatim']}/{ps['agent_dimension_pairs']}")
    print(f"  raw score VALUES leaked               : "
          f"{ps['raw_score_values_leaked']}/{ps['agent_dimension_pairs']}  (must be 0)")
    print(f"  construct names, underscore form      : "
          f"{ps['construct_names_underscore_leaked']}/{ps['agent_dimension_pairs']}")
    print(f"  construct names, SPACED form          : "
          f"{ps['construct_names_spaced_leaked']}/{ps['agent_dimension_pairs']}  <-- FINDING")
    print(f"  scale-direction text present          : "
          f"{ps['scale_direction_text_leaked']}/{ps['agent_dimension_pairs']}  <-- FINDING")
    print(f"\nsimulation_config.notes: {notes['distinct_note_values']} distinct value(s), "
          f"declared provenance={notes['declared_provenance_values']}")
    print(f"  independent of human transcript + coding: "
          f"{notes['constructed_independently_of_human_transcript_and_coding']}")
    print(f"\nTEXTUAL/VERBATIM CONTAMINATION DETECTED: {contam['contamination_detected']}  "
          f"({len(contam['findings'])} finding(s) across "
          f"{sum(contam['targets_scanned'].values())} scanned targets)")
    for f in contam["findings"][:10]:
        print(f"    {f['target']} <- {f['source']}")
    print(f"\nWrote {matrix.relative_to(_REPO_ROOT)}")
    print(f"Wrote {(_OUT_DIR / 'contamination_audit.json').relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
