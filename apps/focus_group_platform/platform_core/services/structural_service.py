"""
Level 2 for a user's corpus.

Runs the SAME two producers the thesis used, routed by side, and says so on every
result. It does not harmonise them into one instrument: a harmonised producer would be
a new instrument, and a new instrument cannot reproduce a frozen number.

EVERY STORED RESULT CARRIES THE HASH IT WAS COMPUTED FROM. When a transcript is
re-imported, its old Level 2 result does not disappear and does not quietly apply to
the new bytes - it becomes STALE, is shown as STALE, and is excluded from every
aggregate until it is recomputed. A result that outlives its input is the most
convincing wrong number a platform can produce.

What this service will not do:

  * compare an uploaded transcript with the frozen human referent. The referent is
    reachable only through `benchmark_service`, and the comparison functions here take
    a `StudyContext` and refuse unless the user declared the sets homologues.
  * apply the Macho Meals comparable window to another corpus.
  * choose which transcripts to compare. The single-session diagnostic takes two
    explicit ids; there is no `human[0]` anywhere in this module.
  * run any inferential test, or make any thematic claim.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import theme
from ..atomic import OnExists, atomic_write_text
from ..analysis_window import (COMPARABLE_NAMESPACE, FULL_RUN_NAMESPACE,
                               CalculationStatus)
from ..level2 import (FROZEN_COMPATIBILITY, Level2Error, Level2Run,
                      NEW_CORPUS_NOTICE, run_level2)
from ..paths import safe_component, safe_path
from ..projects import Project
from ..transcripts import CanonicalTranscript
from . import audit, import_service
from .context import ComparabilityStatus, StudyContext
from .import_service import ImportProblem

RUNS_DIRNAME = "level2"

FRESH = "FRESH"
STALE = "STALE"
MISSING = "MISSING"


class StructuralError(RuntimeError):
    pass


@dataclass
class StructuralOutcome:
    ok: bool
    run: Level2Run | None
    rows: list[dict] = field(default_factory=list)
    problems: list[ImportProblem] = field(default_factory=list)
    result_path: str | None = None
    window_declaration: str | None = None
    descriptive_only: bool = True
    canonical_sha256: str | None = None
    analysis_input_id: str | None = None
    window_id: str | None = None
    namespace: str | None = None
    comparison_eligible: bool = False
    notice: str = NEW_CORPUS_NOTICE


def _restrict(transcript: CanonicalTranscript,
              turns: list[dict]) -> CanonicalTranscript:
    """
    A copy of the transcript carrying only the window's turns, in source order.

    Nothing is reordered and no provenance is dropped: each retained turn keeps its
    canonical id, its original index, its speaker and its role. Only the text of the
    boundary turns may differ, and only by the offsets the researcher set.
    """
    import copy
    by_id = {t.turn_id: t for t in transcript.turns}
    restricted = []
    for row in turns:
        original = by_id.get(row["turn_id"])
        if original is None:
            raise StructuralError(
                f"the window names turn {row['turn_id']!r}, which is not in the "
                f"canonical transcript")
        cloned_turn = copy.deepcopy(original)
        cloned_turn.text = row.get("text", cloned_turn.text)
        restricted.append(cloned_turn)
    cloned = copy.copy(transcript)
    cloned.turns = restricted
    return cloned


# Counts the producers emit alongside the registry metrics. `level2.py` keeps them
# out of `results` on purpose - they are denominators and diagnostics, not registry
# metrics - but two of them (`total_words`, `participant_turns`) are columns of the
# frozen structural table, so a new corpus needs them too. They travel as rows with
# kind="count" and a status that says what they are; nothing treats them as validated
# metrics.
COUNT_ROW_STATUS = "COUNT_NOT_A_REGISTRY_METRIC"
COUNT_DEFINITION = ("a count reported by the producer; it is a denominator or "
                    "diagnostic, not a registry metric")


def _row(result) -> dict:
    return {
        "metric_id": result.metric_id,
        "metric": theme.metric_label(result.metric_id),
        "kind": "metric",
        "value": result.value,
        "value_display": theme.format_value(result.value),
        "status": result.status,
        "scope": result.scope,
        "denominator": result.denominator.get("value"),
        "denominator_definition": result.denominator.get("definition"),
        "denominator_display": theme.format_value(result.denominator.get("value")),
        "warnings": list(result.warnings),
        "review_items": list(result.review_items),
        "transcript_id": result.transcript_id,
        "transcript_type": result.transcript_type,
        "provenance": result.provenance,
    }


def _count_rows(counts: dict, transcript_id: str, transcript_type: str,
                blocked: bool) -> list[dict]:
    out = []
    for key, value in (counts or {}).items():
        out.append({
            "metric_id": key,
            "metric": theme.metric_label(key),
            "kind": "count",
            "value": None if blocked else value,
            "value_display": theme.format_value(None if blocked else value),
            "status": COUNT_ROW_STATUS,
            "scope": "one transcript",
            "denominator": None,
            "denominator_definition": COUNT_DEFINITION,
            "denominator_display": theme.format_value(None),
            "warnings": [],
            "review_items": [],
            "transcript_id": transcript_id,
            "transcript_type": transcript_type,
            "provenance": {},
        })
    return out


def run_structural(project: Project, transcript: CanonicalTranscript, *,
                   roster_names: list[str] | None = None,
                   window_declaration: str | None = None,
                   canonical_sha256: str | None = None,
                   analysis_input=None,
                   turns_override: list[dict] | None = None) -> StructuralOutcome:
    """
    Compute Level 2 for ONE ANALYTICAL INPUT and store it under that input's id.

    `analysis_input` says what was analysed: a locked window, or the whole session.
    The result is filed under `analysis_input_id`, so a second window over the same
    transcript produces a second result rather than overwriting the first - and a
    comparison can name the segment it used.

    A blocked transcript still returns a result set - every metric present, valued
    None, with the reason attached. An empty table would say "nothing to report"; this
    says "here is what could not be computed and why".
    """
    problems: list[ImportProblem] = []
    if canonical_sha256 is None:
        stored = {t["transcript_id"]: t
                  for t in import_service.stored_transcripts(project)}
        record = stored.get(transcript.transcript_id)
        canonical_sha256 = record["canonical_sha256"] if record else None
        if window_declaration is None and record:
            window_declaration = record.get("window_declaration")
        if roster_names is None and record:
            roster_names = record.get("roster_names") or None

    if turns_override is not None:
        transcript = _restrict(transcript, turns_override)

    try:
        run = run_level2(transcript, roster_names=roster_names)
    except Level2Error as exc:
        return StructuralOutcome(False, None, [], [ImportProblem(
            code="missing_roster", message=str(exc),
            remedy="supply the participant roster for this focus group")],
            window_declaration=window_declaration,
            canonical_sha256=canonical_sha256)

    rows = [_row(r) for r in run.results]
    rows += _count_rows(run.counts, transcript.transcript_id,
                        transcript.transcript_type, bool(run.blocked))
    if run.blocked:
        problems.append(ImportProblem(
            code="unresolved_participant_identity",
            message=(f"normalisation left {', '.join(run.blocked)} unresolved, so no "
                     f"structural metric could be computed."),
            remedy="resolve the field in the source; no value is assigned by "
                   "position"))
    undefined = [r["metric"] for r in rows
                 if r["value"] is None and r["kind"] == "metric"
                 and not run.blocked]
    if undefined:
        problems.append(ImportProblem(
            code="metric_undefined",
            message=f"{len(undefined)} metric(s) are undefined for this transcript: "
                    f"{', '.join(undefined)}.",
            remedy="see the per-metric warning; an undefined value is reported as "
                   "Undefined and never as 0",
            blocking=False))

    result_id = (getattr(analysis_input, "analysis_input_id", None)
                 or f"{transcript.transcript_id}__fullrun")
    result_path = save_structural(project, result_id, run,
                                  window_declaration=window_declaration,
                                  canonical_sha256=canonical_sha256,
                                  analysis_input=analysis_input)
    audit.record(project.path, audit.COMPUTE, project_id=project.project_id,
                 subject=result_id,
                 detail={"producer": run.producer, "mode": run.mode,
                         "source_transcript_id": transcript.transcript_id,
                         "window_id": getattr(analysis_input, "window_id", None),
                         "namespace": getattr(analysis_input, "namespace",
                                              FULL_RUN_NAMESPACE),
                         "canonical_sha256": canonical_sha256,
                         "window_artifact_sha256": getattr(
                             analysis_input, "window_artifact_sha256", None),
                         "n_metrics": len(rows), "blocked": bool(run.blocked)})

    return StructuralOutcome(
        ok=not run.blocked, run=run, rows=rows, problems=problems,
        result_path=str(result_path), window_declaration=window_declaration,
        descriptive_only=True, canonical_sha256=canonical_sha256,
        analysis_input_id=result_id,
        window_id=getattr(analysis_input, "window_id", None),
        namespace=getattr(analysis_input, "namespace", FULL_RUN_NAMESPACE),
        comparison_eligible=bool(getattr(analysis_input, "comparison_eligible",
                                         False)))


def runs_dir(project: Project) -> Path:
    return safe_path(project.subdir("runs"), RUNS_DIRNAME)


def producer_module(side: str):
    from ..level2 import _human_producer, _synthetic_producer
    return _human_producer() if side == "human" else _synthetic_producer()


def producer_fingerprint(side: str) -> dict:
    """
    Identify the metric producer for a side WITHOUT running it.

    Reads the module's own source and hashes it. No subprocess, no API call, no
    metric computed - the question "which instrument would run now" must be
    answerable while merely listing results on a screen.
    """
    import hashlib
    import inspect

    from ..level2 import PRODUCER_RULES

    module = producer_module(side)
    name = PRODUCER_RULES[side]["producer"]
    try:
        source = inspect.getsource(module).encode("utf-8")
        digest = hashlib.sha256(source).hexdigest()[:16]
        path = inspect.getsourcefile(module) or ""
    except (OSError, TypeError):
        digest, path = "unavailable", ""
    return {"producer_name": name,
            "producer_source_path": Path(path).name if path else "",
            "producer_sha256": digest,
            "producer_identity": f"{name}@{digest}"}


def expected_producer_identity(side: str) -> str:
    return producer_fingerprint(side)["producer_identity"]


def producer_identity(run: Level2Run) -> str:
    """Which instrument produced these numbers. A change makes results stale."""
    sha = (run.producer_rules or {}).get("producer_sha256", "?")
    return f"{run.producer}@{sha}"


def save_structural(project: Project, result_id: str, run: Level2Run, *,
                    window_declaration: str | None = None,
                    canonical_sha256: str | None = None,
                    analysis_input=None) -> Path:
    safe_component(result_id, field="analysis_input_id")
    directory = runs_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "analysis_input_id": result_id,
        "source_transcript_id": run.transcript_id,
        "window_id": getattr(analysis_input, "window_id", None),
        "namespace": getattr(analysis_input, "namespace", FULL_RUN_NAMESPACE),
        "window_artifact_sha256": getattr(analysis_input,
                                          "window_artifact_sha256", None),
        "comparison_eligible": bool(getattr(analysis_input, "comparison_eligible",
                                            False)),
        "calculation_status": getattr(analysis_input, "calculation_status",
                                      CalculationStatus.DESCRIPTIVE_ONLY.value),
        **producer_fingerprint(run.transcript_type),
        "producer_identity_at_compute": producer_identity(run),
        "transcript_id": run.transcript_id,
        "transcript_type": run.transcript_type,
        "canonical_sha256": canonical_sha256,
        "computed_utc": datetime.now(UTC).isoformat(),
        "producer": run.producer,
        "mode": run.mode,
        "producer_rules": run.producer_rules,
        "counts": run.counts,
        "blocked": run.blocked,
        "review_items": run.review_items,
        "window_declaration": window_declaration,
        "transportability_notice": run.transportability_notice,
        "results": [asdict(r) for r in run.results],
    }
    target = safe_path(directory, f"{result_id}.json")
    atomic_write_text(target, json.dumps(payload, indent=1, ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_structural(project: Project, result_id: str) -> dict:
    safe_component(result_id, field="analysis_input_id")
    return json.loads(safe_path(runs_dir(project), f"{result_id}.json",
                                must_exist=True).read_text(encoding="utf-8"))


def stored_runs(project: Project) -> list[str]:
    directory = runs_dir(project)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


# --------------------------------------------------------- state from disk
@dataclass
class StoredResult:
    transcript_id: str
    freshness: str
    rows: list[dict] = field(default_factory=list)
    canonical_sha256_at_compute: str | None = None
    canonical_sha256_now: str | None = None
    computed_utc: str | None = None
    producer: str | None = None
    window_declaration: str | None = None
    blocked: list[str] = field(default_factory=list)
    analysis_input_id: str | None = None
    window_id: str | None = None
    namespace: str | None = None
    window_artifact_sha256_at_compute: str | None = None
    window_artifact_sha256_now: str | None = None
    producer_identity_at_compute: str | None = None
    comparison_eligible: bool = False
    calculation_status: str = CalculationStatus.DESCRIPTIVE_ONLY.value
    stale_reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.freshness == FRESH and not self.blocked

    @property
    def aggregation_eligible(self) -> bool:
        """
        The five conditions, together: a current result, over a locked window, in the
        comparable namespace, marked eligible, and not blocked.
        """
        return (self.freshness == FRESH and self.comparison_eligible
                and self.namespace == COMPARABLE_NAMESPACE
                and self.calculation_status == CalculationStatus.COMPARABLE.value
                and not self.blocked)

    def to_dict(self) -> dict:
        return asdict(self)


def _rows_from_payload(payload: dict) -> list[dict]:
    rows = []
    for result in payload.get("results", []):
        denominator = result.get("denominator") or {}
        rows.append({
            "metric_id": result["metric_id"],
            "metric": theme.metric_label(result["metric_id"]),
            "kind": "metric",
            "value": result.get("value"),
            "value_display": theme.format_value(result.get("value")),
            "status": result.get("status"),
            "scope": result.get("scope"),
            "denominator": denominator.get("value"),
            "denominator_definition": denominator.get("definition"),
            "denominator_display": theme.format_value(denominator.get("value")),
            "warnings": list(result.get("warnings") or []),
            "review_items": list(result.get("review_items") or []),
            "transcript_id": result.get("transcript_id"),
            "transcript_type": result.get("transcript_type"),
            "provenance": result.get("provenance") or {},
        })
    rows += _count_rows(payload.get("counts"), payload.get("transcript_id", ""),
                        payload.get("transcript_type", ""),
                        bool(payload.get("blocked")))
    return rows


def restore_results(project: Project) -> dict[str, StoredResult]:
    """
    Rebuild the project's Level 2 state FROM DISK, keyed by analysis_input_id.

    Session state is an interaction cache. Reopening the application must not lose a
    computed result - and must not present one computed from inputs that have since
    changed. FOUR things can invalidate a result and all four are checked: the source
    canonical, the window artefact, the window's status, and the producer.
    """
    from . import window_service

    current = import_service.current_canonical_hashes(project)
    windows = {w.window_id: w for w in window_service.all_windows(project)}

    out: dict[str, StoredResult] = {}
    for result_id in stored_runs(project):
        try:
            payload = load_structural(project, result_id)
        except (json.JSONDecodeError, OSError):
            continue

        transcript_id = payload.get("source_transcript_id") or \
            payload.get("transcript_id") or result_id
        at_compute = payload.get("canonical_sha256")
        now = current.get(transcript_id)
        window_id = payload.get("window_id")
        window = windows.get(window_id) if window_id else None
        window_hash_now = window.window_artifact_sha256 if window else None
        window_hash_then = payload.get("window_artifact_sha256")

        legacy = "analysis_input_id" not in payload
        freshness, reason = FRESH, None
        if now is None:
            freshness, reason = MISSING, "the source transcript is no longer stored"
        elif at_compute is None or at_compute != now:
            freshness, reason = STALE, "the source transcript changed"
        elif window_id and window is None:
            freshness, reason = STALE, "the window artefact no longer exists"
        elif window_id and window_hash_then and window_hash_now != window_hash_then:
            freshness, reason = STALE, "the window changed after this was computed"
        elif window is not None and not window.locked:
            freshness, reason = STALE, (f"the window is now {window.status}, so this "
                                        f"result no longer describes a locked "
                                        f"comparable unit")
        else:
            # The instrument itself. A producer whose source changed is a different
            # instrument, and numbers from the old one are not this platform's
            # current answer - even though every input is untouched.
            side = payload.get("transcript_type") or "synthetic"
            recorded = payload.get("producer_identity")
            expected = expected_producer_identity(side)
            if recorded and recorded != expected:
                freshness, reason = STALE, "the metric producer changed"

        # A Phase 3B result carries no analysis input. It stays readable and is
        # never promoted: a declaration is not a reviewed window.
        if legacy:
            declared = payload.get("window_declaration")
            status = (CalculationStatus.LEGACY_UNVERIFIED_WINDOW.value
                      if declared == "comparable_window"
                      else CalculationStatus.DESCRIPTIVE_ONLY.value)
            eligible, namespace = False, FULL_RUN_NAMESPACE
            reason = reason or ("computed before windows existed; the old "
                                "declaration is not a reviewed window")
        else:
            status = payload.get("calculation_status",
                                 CalculationStatus.DESCRIPTIVE_ONLY.value)
            eligible = bool(payload.get("comparison_eligible"))
            namespace = payload.get("namespace", FULL_RUN_NAMESPACE)

        out[result_id] = StoredResult(
            transcript_id=transcript_id, freshness=freshness,
            rows=_rows_from_payload(payload),
            canonical_sha256_at_compute=at_compute, canonical_sha256_now=now,
            computed_utc=payload.get("computed_utc"),
            producer=payload.get("producer"),
            window_declaration=payload.get("window_declaration"),
            blocked=list(payload.get("blocked") or []),
            analysis_input_id=payload.get("analysis_input_id", result_id),
            window_id=window_id, namespace=namespace,
            window_artifact_sha256_at_compute=window_hash_then,
            window_artifact_sha256_now=window_hash_now,
            producer_identity_at_compute=payload.get("producer_identity"),
            comparison_eligible=eligible, calculation_status=status,
            stale_reason=reason)
    return out


def results_by_transcript(project: Project) -> dict[str, list[StoredResult]]:
    out: dict[str, list[StoredResult]] = {}
    for result in restore_results(project).values():
        out.setdefault(result.transcript_id, []).append(result)
    return out


def fresh_run_results(project: Project) -> dict[str, list[dict]]:
    """Every current result, keyed by analysis input. Not filtered for eligibility."""
    return {k: r.rows for k, r in restore_results(project).items()
            if r.freshness == FRESH}


def comparable_run_results(project: Project) -> dict[str, list[dict]]:
    """
    ONLY what may enter a comparison: fresh, locked, comparable, eligible.

    A full-session result and a proposed window are both excluded here, and both stay
    readable elsewhere. Mixing analytical namespaces inside one mean is the failure
    this function exists to make impossible.
    """
    return {k: r.rows for k, r in restore_results(project).items()
            if r.aggregation_eligible}


def stale_problem(result: StoredResult) -> ImportProblem:
    return ImportProblem(
        code="stale_result",
        message=(f"the stored Level 2 result "
                 f"{result.analysis_input_id or result.transcript_id} is no longer "
                 f"current: {result.stale_reason or 'its inputs changed'}. It is not "
                 f"shown as a current result and is excluded from every aggregate."),
        remedy="recompute Level 2 for this analytical input")


def ineligible_problem(result: StoredResult) -> ImportProblem:
    return ImportProblem(
        code="not_comparison_eligible",
        message=(f"{result.analysis_input_id} is in namespace {result.namespace} "
                 f"({result.calculation_status}). It is descriptive and does not "
                 f"enter a comparison."),
        remedy=("create a comparable window for this transcript and lock it, then "
                "recompute"),
        blocking=False)


# ---------------------------------------------------------------- comparison
@dataclass
class StructuralComparison:
    allowed: bool
    reason: str
    context_id: str | None = None
    comparability_status: str | None = None
    rows: list[dict] = field(default_factory=list)
    declaration_by_user: str | None = None
    human_transcript_id: str | None = None
    synthetic_transcript_id: str | None = None
    caveats: list[str] = field(default_factory=list)


COMPARISON_CAVEATS = [
    "descriptive only: no inferential test is performed and none is implied",
    "the two sides carry their own denominators; they are shown separately and are "
    "never pooled",
    "structural correspondence is not thematic fidelity; no claim about themes "
    "follows from this table",
    f"both sides are computed under {FROZEN_COMPATIBILITY} rules, which encode "
    f"decisions made for the Macho Meals corpus",
]

SINGLE_SESSION_CAVEAT = (
    "SINGLE-SESSION DIAGNOSTIC: one human transcript against one synthetic "
    "transcript. It is not the study-level comparison, has no replicate structure, "
    "and must not be reported as a result for the corpus")


def compare_single_session(context: StudyContext, *,
                           human_transcript_id: str,
                           synthetic_transcript_id: str,
                           human_rows: list[dict],
                           synthetic_rows: list[dict]) -> StructuralComparison:
    """
    One named human transcript against one named synthetic transcript.

    BOTH IDS ARE REQUIRED. An earlier version took the first human and the first
    synthetic in the project, which meant that declaring ten synthetic transcripts and
    comparing only one looked identical, on screen, to comparing the right one. The
    pair is now stated by the caller and echoed back in the result.
    """
    if not human_transcript_id or not synthetic_transcript_id:
        raise StructuralError(
            "compare_single_session needs both transcript ids; the pair is chosen by "
            "the user, never by position in a list")

    if not context.structural_comparison_allowed:
        return StructuralComparison(
            allowed=False,
            reason=("; ".join(context.comparability_reasons)
                    or "the study context does not permit a structural comparison"),
            context_id=context.context_id,
            comparability_status=context.comparability_status,
            human_transcript_id=human_transcript_id,
            synthetic_transcript_id=synthetic_transcript_id)

    if context.comparability_status == \
            ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value:
        return StructuralComparison(
            allowed=False,
            reason=("this is the frozen benchmark; its comparison is served by "
                    "benchmark_service, not recomputed from uploads"),
            context_id=context.context_id,
            comparability_status=context.comparability_status)

    human = {r["metric_id"]: r for r in human_rows}
    synthetic = {r["metric_id"]: r for r in synthetic_rows}
    rows = []
    for metric_id in sorted(set(human) | set(synthetic)):
        h, s = human.get(metric_id), synthetic.get(metric_id)
        rows.append({
            "metric_id": metric_id,
            "metric": theme.metric_label(metric_id),
            "human_transcript_id": human_transcript_id,
            "synthetic_transcript_id": synthetic_transcript_id,
            "human_value": (h or {}).get("value"),
            "human_display": theme.format_value((h or {}).get("value")),
            "human_denominator": (h or {}).get("denominator"),
            "human_denominator_definition": (h or {}).get(
                "denominator_definition"),
            "synthetic_value": (s or {}).get("value"),
            "synthetic_display": theme.format_value((s or {}).get("value")),
            "synthetic_denominator": (s or {}).get("denominator"),
            "synthetic_denominator_definition": (s or {}).get(
                "denominator_definition"),
            # No difference when either side is undefined: a difference against
            # Undefined is not zero, it is nothing.
            "difference": (None if (h or {}).get("value") is None
                           or (s or {}).get("value") is None
                           else s["value"] - h["value"]),
            "warnings": sorted(set((h or {}).get("warnings", [])
                                   + (s or {}).get("warnings", []))),
        })
    for row in rows:
        row["difference_display"] = theme.format_value(row["difference"])

    return StructuralComparison(
        allowed=True,
        reason="the user declared the two sets homologues",
        context_id=context.context_id,
        comparability_status=context.comparability_status,
        rows=rows, declaration_by_user=context.declaration_by_user,
        human_transcript_id=human_transcript_id,
        synthetic_transcript_id=synthetic_transcript_id,
        caveats=[SINGLE_SESSION_CAVEAT] + list(COMPARISON_CAVEATS))


def comparison_unavailable_problem(context: StudyContext) -> ImportProblem:
    return ImportProblem(
        code="methodological_comparison_unavailable",
        message=("a structural comparison is not available for this project: "
                 + "; ".join(context.comparability_reasons)),
        remedy=("import both a human and a synthetic set, then declare on what "
                "grounds they are homologues"))
