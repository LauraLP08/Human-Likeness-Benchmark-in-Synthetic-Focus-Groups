"""
Macho Meals production evaluation — Phase 0: read-only readiness audit.

Produces the canonical experiment manifest and the readiness/failure audits, then
stops. Makes NO evaluator API call, writes nothing outside
`analysis/production_evaluation/`, and never modifies `core/`, prompts, agents,
configs, human transcripts, the codebook or raw session logs.

WHITELIST IS EXPLICIT. Every canonical session is named literally below. There is
no globbing over `output/session_logs/`, so no directory can be silently added to
the experiment by appearing on disk. `scripts/assess_session_batch.py` is NOT used
for exactly this reason — it discovers all directories under the session-log root.

CANONICAL REPLICATION INDEX is carried separately from the physical run name.
Enriched FG4 maps run01/run04/run03 and enriched FG5 maps run01/run03/run04 to
canonical replication 1/2/3, because each had its physical run02 archived
pre-analytically. Nothing downstream should key on the physical suffix.

Findings are classified, not thresholded:
    HARD_EXCLUSION                 — run cannot enter the corpus
    MATERIAL_COMPARABILITY_WARNING — usable but may not be comparable like-for-like
    NONFATAL_RUNTIME_WARNING       — runtime noise, recovered
    INFO                           — recorded for provenance only

Usage:
    py scripts/phase0_macho_meals_readiness_audit.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"
_CONFIG_DIR = _REPO_ROOT / "configs" / "experiment"
_GUIDE_YAML = _REPO_ROOT / "configs" / "guides" / "macho_meals_plant_based_masculinity_uk.yaml"
_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation"

_EXPECTED_SECTIONS = 7
_EXPECTED_FINAL_SECTION_INDEX = 6


# ---------------------------------------------------------------------------
# The frozen whitelist — 30 canonical sessions, named literally
# ---------------------------------------------------------------------------
# (condition, fg, canonical_replication_index, physical run directory)
WHITELIST: list[tuple[str, str, int, str]] = []
for _fg in ("fg1", "fg2", "fg3"):
    for _i, _run in enumerate(("run01", "run02", "run03"), start=1):
        WHITELIST.append(("enriched", _fg, _i, f"macho_meals_{_fg}_{_run}"))
# enriched FG4: run02 archived as a technical outlier (9.38% forced-silence rate,
# more than twice the next-highest enriched run) by a pre-outcome researcher
# decision; run04 is a NEW stochastic replicate generated under the current code,
# not a repair of run02, and takes canonical replication index 2.
WHITELIST.append(("enriched", "fg4", 1, "macho_meals_fg4_run01"))
WHITELIST.append(("enriched", "fg4", 2, "macho_meals_fg4_run04"))
WHITELIST.append(("enriched", "fg4", 3, "macho_meals_fg4_run03"))
# enriched FG5: run02 archived (lost reflection cycle); run04 is its replacement.
WHITELIST.append(("enriched", "fg5", 1, "macho_meals_fg5_run01"))
WHITELIST.append(("enriched", "fg5", 2, "macho_meals_fg5_run03"))
WHITELIST.append(("enriched", "fg5", 3, "macho_meals_fg5_run04"))
for _fg in ("fg1", "fg2", "fg3", "fg4", "fg5"):
    for _i, _run in enumerate(("run01", "run02", "run03"), start=1):
        WHITELIST.append(("demographics-only", _fg, _i, f"macho_meals_{_fg}_demoonly_{_run}"))

# Audited for documentation only — visible in the readiness and API audits, absent
# from the canonical manifest, contributing no artefact to metrics, coding, caches
# or summaries. Config, transcript, states and logs stay intact on disk.
ARCHIVED_RUNS: list[tuple[str, str]] = [
    ("macho_meals_fg4_run02", "ARCHIVED_TECHNICAL_OUTLIER"),
    ("macho_meals_fg5_run02", "ARCHIVED_LOST_REFLECTION_CYCLE"),
]

# Patterns that must never be treated as canonical, checked against what is on disk.
EXCLUDE_MARKERS = ("presynthesisfix", "failed_auth", "partial", "killed", "nobudget",
                   "validation", "test", "emergent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str | None:
    if not path.exists() or path.is_dir():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:               # noqa: BLE001 — audit must not crash on bad input
        return None, f"{type(exc).__name__}: {exc}"


def _last_state_file(run_dir: Path) -> Path | None:
    states = []
    for p in run_dir.glob("state_turn_*.json"):
        m = re.search(r"state_turn_(\d+)\.json$", p.name)
        if m:
            states.append((int(m.group(1)), p))
    return max(states)[1] if states else None


def _finding(level: str, code: str, detail: str) -> dict:
    return {"level": level, "code": code, "detail": detail}


# ---------------------------------------------------------------------------
# Per-run gates
# ---------------------------------------------------------------------------

def audit_run(condition: str, fg: str, rep_index: int | None, run_name: str) -> dict:
    run_dir = _SESSION_LOGS / run_name
    cfg_path = _CONFIG_DIR / f"{run_name}.json"
    findings: list[dict] = []

    row: dict = {
        "condition": condition,
        "fg": fg,
        "canonical_replication_index": rep_index,
        "physical_run": run_name,
        "run_dir_present": run_dir.is_dir(),
        "config_present": cfg_path.exists(),
    }

    if not run_dir.is_dir():
        findings.append(_finding("HARD_EXCLUSION", "DIR_MISSING",
                                 f"{run_dir} does not exist"))
        row["findings"] = findings
        row["verdict"] = "HARD_EXCLUSION"
        return row

    # --- transcript ---------------------------------------------------------
    tpath = run_dir / "transcript.json"
    transcript, terr = _load_json(tpath) if tpath.exists() else (None, "file missing")
    row["transcript_parseable"] = transcript is not None
    if transcript is None:
        findings.append(_finding("HARD_EXCLUSION", "TRANSCRIPT_UNREADABLE", str(terr)))
        row["findings"] = findings
        row["verdict"] = "HARD_EXCLUSION"
        return row
    if not transcript:
        findings.append(_finding("HARD_EXCLUSION", "TRANSCRIPT_EMPTY", "0 entries"))

    entries = transcript
    row["transcript_entries"] = len(entries)
    row["transcript_words"] = sum(len((e.get("content") or "").split()) for e in entries)
    mod_entries = [e for e in entries if (e.get("speaker_name") or "").lower() == "moderator"]
    par_entries = [e for e in entries if (e.get("speaker_name") or "").lower() != "moderator"]
    row["moderator_turns"] = len(mod_entries)
    row["participant_turns"] = len(par_entries)
    row["moderator_words"] = sum(len((e.get("content") or "").split()) for e in mod_entries)
    row["participant_words"] = sum(len((e.get("content") or "").split()) for e in par_entries)
    row["empty_content_entries"] = sum(1 for e in entries if not (e.get("content") or "").strip())

    # --- final state --------------------------------------------------------
    spath = _last_state_file(run_dir)
    row["last_state_file"] = spath.name if spath else None
    state, serr = _load_json(spath) if spath else (None, "no state_turn_*.json found")
    row["final_state_parseable"] = state is not None
    if state is None:
        findings.append(_finding("HARD_EXCLUSION", "FINAL_STATE_UNREADABLE", str(serr)))
        row["findings"] = findings
        row["verdict"] = "HARD_EXCLUSION"
        return row

    sm = state.get("session_meta", {})
    guide = state.get("discussion_guide", []) or []
    row["current_section_index"] = sm.get("current_section_index")
    row["guide_sections"] = len(guide)
    completed = [bool(s.get("completed")) for s in guide]
    row["sections_completed"] = sum(completed)
    row["all_sections_completed"] = len(completed) == _EXPECTED_SECTIONS and all(completed)
    row["inject_participant_intro"] = sm.get("inject_participant_intro")
    row["participation_mode"] = sm.get("participation_mode")
    row["moderator_model"] = sm.get("moderator_model")
    row["temperature"] = sm.get("temperature")
    row["participant_response_max_tokens"] = sm.get("participant_response_max_tokens")
    row["session_id"] = sm.get("id")
    row["run_label"] = sm.get("run_label")
    row["total_turns"] = sm.get("total_turns")

    if row["current_section_index"] != _EXPECTED_FINAL_SECTION_INDEX:
        findings.append(_finding(
            "HARD_EXCLUSION", "SECTION_INDEX_NOT_FINAL",
            f"current_section_index={row['current_section_index']}, expected {_EXPECTED_FINAL_SECTION_INDEX}"))
    if not row["all_sections_completed"]:
        findings.append(_finding(
            "HARD_EXCLUSION", "SECTIONS_INCOMPLETE",
            f"{row['sections_completed']}/{len(completed)} completed=true"))
    if sm.get("inject_participant_intro") is not False:
        findings.append(_finding(
            "HARD_EXCLUSION", "INJECT_PARTICIPANT_INTRO_NOT_FALSE",
            f"inject_participant_intro={sm.get('inject_participant_intro')!r}"))

    # --- roster vs config ---------------------------------------------------
    state_roster = sorted(state.get("participants", {}).keys())
    row["state_roster"] = "|".join(state_roster)
    row["state_roster_n"] = len(state_roster)

    cfg, cerr = _load_json(cfg_path) if cfg_path.exists() else (None, "config missing")
    if cfg is None:
        findings.append(_finding("HARD_EXCLUSION", "CONFIG_UNREADABLE", str(cerr)))
        cfg_roster = []
    else:
        cfg_roster = []
        for p in cfg.get("participants", []):
            if "agent_payload_path" in p:
                cfg_roster.append(Path(p["agent_payload_path"]).stem)
            elif "id" in p:
                cfg_roster.append(p["id"])
        cfg_roster = sorted(cfg_roster)
    row["config_roster"] = "|".join(cfg_roster)
    row["roster_matches_config"] = bool(cfg_roster) and cfg_roster == state_roster
    if cfg is not None and not row["roster_matches_config"]:
        findings.append(_finding(
            "HARD_EXCLUSION", "ROSTER_MISMATCH",
            f"config={cfg_roster} state={state_roster}"))

    # --- all expected participants contributed ------------------------------
    spoke = {e.get("speaker_id") for e in par_entries if (e.get("content") or "").strip()}
    silent = [p for p in state_roster if p not in spoke]
    row["participants_who_spoke"] = len(spoke & set(state_roster))
    row["silent_participants"] = "|".join(silent)
    row["all_participants_contributed"] = not silent
    if silent:
        findings.append(_finding(
            "MATERIAL_COMPARABILITY_WARNING", "PARTICIPANT_NEVER_SPOKE",
            f"{len(silent)} roster member(s) contributed no turn: {silent}"))

    # --- config consistency between state and config ------------------------
    if cfg is not None:
        for key, state_key in (("temperature", "temperature"),
                               ("participation_mode", "participation_mode"),
                               ("participant_response_max_tokens", "participant_response_max_tokens")):
            if key in cfg and cfg[key] != sm.get(state_key):
                findings.append(_finding(
                    "MATERIAL_COMPARABILITY_WARNING", "CONFIG_STATE_DIVERGENCE",
                    f"{key}: config={cfg[key]!r} state={sm.get(state_key)!r}"))

    # --- termination --------------------------------------------------------
    mlog, _ = _load_json(run_dir / "moderator_log.json") if (run_dir / "moderator_log.json").exists() else (None, None)
    transitions = [e for e in (mlog or []) if e.get("action") == "section_transition"]
    row["section_transitions"] = len(transitions)
    row["moderator_log_entries"] = len(mlog or [])
    # A run that reached the final section AND fired a closing transition ended naturally.
    natural = (row["current_section_index"] == _EXPECTED_FINAL_SECTION_INDEX
               and len(transitions) >= _EXPECTED_SECTIONS - 1)
    row["termination"] = "natural" if natural else "indeterminate"
    if not natural:
        findings.append(_finding(
            "MATERIAL_COMPARABILITY_WARNING", "TERMINATION_INDETERMINATE",
            f"section_transitions={len(transitions)}, current_section_index={row['current_section_index']}"))

    # --- hashes -------------------------------------------------------------
    row["transcript_sha256"] = _sha256(tpath)
    row["config_sha256"] = _sha256(cfg_path)
    row["final_state_sha256"] = _sha256(spath)
    row["guide_yaml_sha256"] = _sha256(_GUIDE_YAML)
    row["guide_in_config_sha256"] = (
        _sha256_text(json.dumps(cfg.get("discussion_guide"), sort_keys=True, ensure_ascii=False))
        if cfg and cfg.get("discussion_guide") is not None else None)

    agent_hashes = {}
    if cfg is not None:
        for p in cfg.get("participants", []):
            ap = p.get("agent_payload_path")
            if ap:
                agent_hashes[Path(ap).stem] = _sha256(_REPO_ROOT / ap)
    row["agents_sha256_combined"] = (
        _sha256_text(json.dumps(agent_hashes, sort_keys=True)) if agent_hashes else None)
    row["agents_resolved"] = sum(1 for v in agent_hashes.values() if v)
    row["agents_missing"] = sum(1 for v in agent_hashes.values() if not v)
    if row["agents_missing"]:
        findings.append(_finding("HARD_EXCLUSION", "AGENT_PAYLOAD_MISSING",
                                 f"{row['agents_missing']} agent payload file(s) not found"))

    prompt_override = (cfg or {}).get("moderator_prompt_override")
    row["moderator_prompt_override"] = prompt_override
    row["moderator_prompt_sha256"] = (
        _sha256(_REPO_ROOT / "prompts" / prompt_override) if prompt_override else None)
    if prompt_override and row["moderator_prompt_sha256"] is None:
        findings.append(_finding("MATERIAL_COMPARABILITY_WARNING", "PROMPT_FILE_NOT_FOUND",
                                 f"moderator_prompt_override={prompt_override!r} not resolvable under prompts/"))

    row["findings"] = findings
    levels = {f["level"] for f in findings}
    row["verdict"] = ("HARD_EXCLUSION" if "HARD_EXCLUSION" in levels
                      else "PASS_WITH_WARNINGS" if levels - {"INFO"}
                      else "PASS")
    return row


# ---------------------------------------------------------------------------
# API / fallback audit
# ---------------------------------------------------------------------------

def audit_api(run_name: str) -> dict:
    run_dir = _SESSION_LOGS / run_name
    path = run_dir / "api_calls.jsonl"
    row: dict = {"physical_run": run_name, "api_calls_present": path.exists()}
    if not path.exists():
        return row

    total = 0
    by_event = Counter()
    errors = Counter()
    retries = 0
    validation_fallbacks = 0
    truncated = 0
    resp_gen = 0
    engagement_total = 0
    engagement_faults = 0
    coerced = 0
    episodic_dropped_calls = 0
    stop_reasons = Counter()
    models = Counter()
    tokens_in = tokens_out = 0
    malformed_lines = 0
    fields_coerced_key_present = 0
    forced_silences = 0
    first_attempt_faults = 0
    recovered_on_retry = 0
    engagement_retry_events = 0

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        total += 1
        ev = e.get("event_type")
        by_event[ev] += 1
        models[e.get("model")] += 1
        tokens_in += e.get("input_tokens") or 0
        tokens_out += e.get("output_tokens") or 0

        et = e.get("error_type")
        if et and et != "none":
            errors[et] += 1
        if (e.get("attempt_number") or 1) > 1:
            retries += 1
        if e.get("validation_fallback") is True:
            validation_fallbacks += 1
        # `fields_coerced` is logged as the literal string "none" when nothing was
        # coerced, so a plain truthiness test counts every call as a coercion.
        fc = e.get("fields_coerced")
        if fc and fc != "none":
            coerced += 1
        if "fields_coerced" in e:
            fields_coerced_key_present += 1
        if (e.get("episodic_entries_dropped") or 0) > 0:
            episodic_dropped_calls += 1

        if ev == "participant_response_generation":
            resp_gen += 1
            if e.get("response_truncated") is True:
                truncated += 1
            if e.get("stop_reason"):
                stop_reasons[e["stop_reason"]] += 1
        if ev == "participant_engagement_assessment":
            if (e.get("attempt_number") or 1) == 1:
                engagement_total += 1
            if et and et != "none":
                engagement_faults += 1
            # Forced silence = participant silenced by a technical fault rather
            # than a modelled choice. Which errors count depends on the code path
            # this run executed, so both tallies are collected here and resolved
            # after the pass, once the path is known.
            if et in ("engagement_fallback_after_retry", "engagement_api_error"):
                forced_silences += 1
            elif et == "recovered_on_retry":
                recovered_on_retry += 1
            elif et and et != "none":
                # A first-attempt fault. Terminal under the pre-fix path; merely
                # the trigger for a retry under the post-fix path.
                first_attempt_faults += 1
        if ev == "participant_engagement_assessment_retry":
            engagement_retry_events += 1
            # The retry's own outcome is logged on this event, not on the
            # first-attempt record.
            if et == "recovered_on_retry":
                recovered_on_retry += 1
            elif et in ("engagement_fallback_after_retry", "engagement_api_error"):
                forced_silences += 1

    def _pct(num, den):
        return round(num / den, 4) if den else None

    # `fields_coerced` is emitted on EVERY engagement call by the post-fix code
    # (as the literal "none" when nothing was coerced) and not at all by the
    # pre-fix code, so its presence identifies which path the run executed.
    retry_path = fields_coerced_key_present > 0
    total_forced = forced_silences if retry_path else first_attempt_faults + forced_silences

    row.update({
        "api_calls_total": total,
        "malformed_log_lines": malformed_lines,
        "models_used": "|".join(f"{m}:{c}" for m, c in sorted(models.items(), key=lambda x: -x[1]) if m),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "error_calls": sum(errors.values()),
        "error_rate_of_all_calls": _pct(sum(errors.values()), total),
        "error_types": "|".join(f"{k}:{v}" for k, v in sorted(errors.items())) or "none",
        "retry_calls": retries,
        "retry_rate_of_all_calls": _pct(retries, total),
        "moderator_validation_fallbacks": validation_fallbacks,
        "moderator_decision_attempts": by_event.get("moderator_decision_attempt", 0),
        "validation_fallback_rate_of_moderator_attempts":
            _pct(validation_fallbacks, by_event.get("moderator_decision_attempt", 0)),
        "participant_response_generations": resp_gen,
        "responses_truncated": truncated,
        "truncation_rate_of_responses": _pct(truncated, resp_gen),
        "stop_reasons": "|".join(f"{k}:{v}" for k, v in sorted(stop_reasons.items())) or "none",
        "engagement_assessments": engagement_total,
        "engagement_faults": engagement_faults,
        "engagement_fault_rate": _pct(engagement_faults, engagement_total),
        "engagement_calls_with_coerced_fields": coerced,
        "engagement_coercion_rate": _pct(coerced, engagement_total),
        "fields_coerced_key_present_calls": fields_coerced_key_present,
        "engagement_retry_path": retry_path,
        "engagement_retry_events": engagement_retry_events,
        "engagement_first_attempt_faults": first_attempt_faults,
        "engagement_recovered_on_retry": recovered_on_retry,
        # Participants silenced by a technical fault rather than a modelled choice,
        # resolved against the code path this run actually executed.
        "forced_silences": total_forced,
        "forced_silence_rate": _pct(total_forced, engagement_total),
        "calls_with_episodic_entries_dropped": episodic_dropped_calls,
    })

    mlog_path = run_dir / "moderator_log.json"
    if mlog_path.exists():
        mlog, _ = _load_json(mlog_path)
        mlog = mlog or []
        row["moderator_log_validation_fallbacks"] = sum(1 for e in mlog if e.get("validation_fallback"))
        row["moderator_log_compressed"] = sum(1 for e in mlog if e.get("compressed"))
        row["moderator_observe_turns"] = sum(1 for e in mlog if e.get("intervention_mode") == "observe")
        row["moderator_speak_turns"] = sum(1 for e in mlog if e.get("intervention_mode") == "speak")

    launcher = run_dir / "launcher_stdout.log"
    row["launcher_log_present"] = launcher.exists()
    # Markers scanned literally. "Connection error" / "call/parse failed" indicate a
    # cycle was lost outright, which is materially different from a recovered retry.
    markers = ["Connection error", "call/parse failed", "Traceback",
               "Pydantic validation failed", "JSON parse failed",
               "defaulting to stay_silent", "exceeded the 80-word",
               "safety cap reached"]
    if launcher.exists():
        txt = launcher.read_text(encoding="utf-8", errors="replace")
        row["launcher_log_bytes"] = len(txt)
        found = {m: txt.count(m) for m in markers if txt.count(m)}
        row["launcher_markers"] = "|".join(f"{k}:{v}" for k, v in found.items()) or "none"
        row["launcher_lost_cycle"] = bool(
            found.get("Connection error") or found.get("call/parse failed")
            or found.get("Traceback"))
        row["launcher_stay_silent_lines"] = found.get("defaulting to stay_silent", 0)
    else:
        row["launcher_markers"] = "LOG_ABSENT"
        row["launcher_lost_cycle"] = None
    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("  MACHO MEALS — PHASE 0 READ-ONLY READINESS AUDIT")
    print(f"  {len(WHITELIST)} candidate sessions; no evaluator API call is made")
    print("=" * 78)

    rows = [audit_run(cond, fg, idx, run) for cond, fg, idx, run in WHITELIST]
    api_rows = [audit_api(run) for _, _, _, run in WHITELIST]
    api_by_run = {a["physical_run"]: a for a in api_rows}

    # --- cross-condition findings folded back onto each run -----------------
    # These are properties of the CORPUS, not of a single run, but they must ride
    # on each affected run so nothing downstream can read a run row in isolation
    # and conclude it is comparable.
    for r in rows:
        a = api_by_run.get(r["physical_run"], {})
        instrumented = (a.get("fields_coerced_key_present_calls") or 0) > 0
        r["engagement_retry_path_available"] = instrumented
        fs = a.get("forced_silences") or 0
        r["forced_silences"] = fs
        r["forced_silence_rate"] = a.get("forced_silence_rate")

        if not instrumented:
            r["findings"].append(_finding(
                "MATERIAL_COMPARABILITY_WARNING", "ENGAGEMENT_RETRY_PATH_ABSENT",
                "Run executed the pre-fix engagement path: any engagement validation "
                "fault silenced the participant immediately, with no retry. Runs in "
                "the other condition executed the post-fix path (retry, then silence). "
                "Participation-dependent metrics are not like-for-like across conditions."))
        if fs:
            r["findings"].append(_finding(
                "MATERIAL_COMPARABILITY_WARNING", "FORCED_SILENCES_PRESENT",
                f"{fs} participant speaking opportunit(ies) suppressed by a technical "
                f"fault rather than a modelled choice "
                f"({a.get('forced_silence_rate')} of engagement assessments)."))
        if a.get("launcher_lost_cycle"):
            r["findings"].append(_finding(
                "MATERIAL_COMPARABILITY_WARNING", "LAUNCHER_LOST_CYCLE",
                f"launcher log records a lost cycle: {a.get('launcher_markers')}"))
        if a.get("launcher_markers") == "LOG_ABSENT":
            r["findings"].append(_finding(
                "NONFATAL_RUNTIME_WARNING", "LAUNCHER_LOG_ABSENT",
                "launcher_stdout.log missing; runtime warnings cannot be cross-checked "
                "against stdout for this run."))
        levels = {f["level"] for f in r["findings"]}
        r["verdict"] = ("HARD_EXCLUSION" if "HARD_EXCLUSION" in levels
                        else "PASS_WITH_WARNINGS" if levels - {"INFO"}
                        else "PASS")

    # Archived runs — documented, never analytic.
    archived_rows = []
    archived_apis = []
    for run_name, reason in ARCHIVED_RUNS:
        fg = "fg4" if "fg4" in run_name else "fg5"
        a = audit_run(f"enriched(ARCHIVED:{reason})", fg, None, run_name)
        a["archive_reason"] = reason
        a["verdict"] = f"EXCLUDED_{reason}"
        archived_rows.append(a)
        ap = audit_api(run_name)
        ap["archive_reason"] = reason
        archived_apis.append(ap)

    # Which on-disk macho_meals dirs are NOT in the whitelist?
    whitelisted = {r for _, _, _, r in WHITELIST}
    on_disk = sorted(p.name for p in _SESSION_LOGS.glob("macho_meals*") if p.is_dir())
    not_whitelisted = [d for d in on_disk if d not in whitelisted]

    # --- manifest -----------------------------------------------------------
    manifest = []
    for r in rows:
        manifest.append({
            "condition": r["condition"],
            "fg": r["fg"],
            "canonical_replication_index": r["canonical_replication_index"],
            "physical_run": r["physical_run"],
            "session_id": r.get("session_id"),
            "run_label": r.get("run_label"),
            "verdict": r["verdict"],
            "transcript_entries": r.get("transcript_entries"),
            "participant_turns": r.get("participant_turns"),
            "moderator_turns": r.get("moderator_turns"),
            "roster_n": r.get("state_roster_n"),
            "transcript_sha256": r.get("transcript_sha256"),
            "config_sha256": r.get("config_sha256"),
            "agents_sha256_combined": r.get("agents_sha256_combined"),
            "guide_in_config_sha256": r.get("guide_in_config_sha256"),
            "guide_yaml_sha256": r.get("guide_yaml_sha256"),
            "moderator_prompt_sha256": r.get("moderator_prompt_sha256"),
        })

    def _write_csv(path: Path, records: list[dict]) -> None:
        if not records:
            return
        fields: list[str] = []
        for rec in records:
            for k in rec:
                if k not in fields:
                    fields.append(k)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for rec in records:
                w.writerow({k: rec.get(k) for k in fields})

    _write_csv(_OUT_DIR / "canonical_experiment_manifest.csv", manifest)
    (_OUT_DIR / "canonical_experiment_manifest.json").write_text(json.dumps({
        "generated_utc": datetime.now(UTC).isoformat(),
        "study": "macho_meals",
        "design": "5 focus groups x 3 stochastic replicates x 2 conditions = 30 canonical sessions",
        "primary_unit": "focus group",
        "evaluator_decision": {
            "model": "gemini-3.5-flash",
            "thinking_level": "medium",
            "evaluator_config_key": "gemininext",
            "applies_to": "Tier 1 production coding",
            "basis": "docs/findings/2026-07-18_evaluator_model_comparison.md",
            "rationale": (
                "Fixed by an a priori rule. gemini-2.5-flash scored 81.8% worst pairwise "
                "Gate-1 agreement, below the 85% repeatability threshold, and is "
                "DISQUALIFIED as primary evaluator. gemini-3.5-flash scored 100% Gate-1 "
                "agreement, 100% quote verification and 100% code preservation. Both "
                "achieved the same discrimination margin (+0.111)."),
            "not_to_be_reopened": (
                "Do not rebuild an ensemble or silently substitute gemini-2.5-flash. If "
                "preflight shows gemini-3.5-flash is unavailable or its configuration "
                "cannot be reproduced, stop and ask the researcher."),
            "reproducibility_caveat": (
                "EVALUATOR_CONFIGS['gemininext'] records thinking_level='medium' for "
                "logging only — the value is the model default and is NOT sent in the "
                "API request, and temperature is unsupported and omitted. Reproducibility "
                "therefore depends on the model's default thinking level being stable. "
                "Verify at Phase 4 preflight."),
        },
        "prior_artefact_reuse_rule": (
            "Tier 1 reach, Tier 2 and Tier 2b artefacts on disk were produced with "
            "gemini-2.5-flash and are pilot/historical evidence only. They do not make "
            "gemini-2.5-flash the production evaluator. Before reusing any prior coding, "
            "require exact match on model ID, parameters, transcript hash, codebook hash "
            "and prompt hash; otherwise recode with the frozen evaluator or mark the "
            "artefact non-reusable."),
        "replication_index_note": (
            "canonical_replication_index is independent of the physical run suffix. "
            "enriched FG5 maps run01->1, run03->2, run04->3 because macho_meals_fg5_run02 "
            "was archived after a generation failure and replaced by run04."),
        "archived_excluded_runs": [
            {
                "run": "macho_meals_fg4_run02",
                "reason_code": "ARCHIVED_TECHNICAL_OUTLIER",
                "status": "pre-analytically excluded by researcher decision, before any thematic or condition outcome was evaluated",
                "evidence": "6 forced technical silences in 64 engagement assessments = 9.38%, more than twice the next-highest enriched rate (3.90%)",
                "replaced_by": "macho_meals_fg4_run04",
                "replacement_nature": "a NEW stochastic replicate generated under current code, not a repair of run02",
                "note": "config, transcript, states and logs remain intact on disk; contributes no artefact to metrics, coding, caches or summaries",
            },
            {
                "run": "macho_meals_fg5_run02",
                "reason_code": "ARCHIVED_LOST_REFLECTION_CYCLE",
                "status": "pre-analytically excluded by researcher decision",
                "evidence": "launcher log records '[moderator reflection] call/parse failed, skipping this cycle: Connection error.' — the only lost cycle in the corpus",
                "replaced_by": "macho_meals_fg5_run04",
                "note": "may remain on disk; contributes no artefact to metrics, coding, caches or summaries",
            },
        ],
        "sessions": manifest,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    readiness = []
    for r in rows + archived_rows:
        rec = {k: v for k, v in r.items() if k != "findings"}
        rec["n_findings"] = len(r["findings"])
        rec["hard_exclusions"] = "|".join(f["code"] for f in r["findings"] if f["level"] == "HARD_EXCLUSION") or ""
        rec["material_warnings"] = "|".join(f["code"] for f in r["findings"] if f["level"] == "MATERIAL_COMPARABILITY_WARNING") or ""
        rec["runtime_warnings"] = "|".join(f["code"] for f in r["findings"] if f["level"] == "NONFATAL_RUNTIME_WARNING") or ""
        rec["finding_detail"] = " ;; ".join(f"[{f['level']}] {f['code']}: {f['detail']}" for f in r["findings"])
        readiness.append(rec)
    _write_csv(_OUT_DIR / "run_readiness_audit.csv", readiness)
    _write_csv(_OUT_DIR / "api_failure_and_fallback_audit.csv", api_rows + archived_apis)

    print(f"\nWrote 4 data files to {_OUT_DIR.relative_to(_REPO_ROOT)}")

    # --- console summary ----------------------------------------------------
    verdicts = Counter(r["verdict"] for r in rows)
    print(f"\nVerdicts across {len(rows)} candidates: {dict(verdicts)}")
    for r in rows:
        if r["verdict"] != "PASS":
            print(f"  {r['verdict']:<20} {r['physical_run']}")
            for f in r["findings"]:
                print(f"      [{f['level']}] {f['code']}: {f['detail'][:110]}")
    print("\nArchived (documentation only, never analytic):")
    for a in archived_rows:
        print(f"  {a['physical_run']:<26} {a['verdict']}")
    print(f"On-disk macho_meals dirs not in whitelist: {len(not_whitelisted)}")

    return rows, api_rows, archived_rows, archived_apis, not_whitelisted, on_disk


if __name__ == "__main__":
    main()
