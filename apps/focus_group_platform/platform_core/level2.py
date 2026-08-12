"""
Level 2 runner - structural and interaction metrics.

REUSES the repository's producers; it does not reimplement a metric. There are TWO of
them, and the split is not cosmetic - the frozen results were produced by both:

  human side      `scripts.structural_metrics_transportability.compute(turns, roster)`
                  reads speaker_role / canonical_speaker_id / content / speaker_name
  synthetic side  `scripts.aggregate_production_results.compute_structural_metrics(entries)`
                  over one comparable window, deriving the role from
                  `speaker_id == "MODERATOR"` and filtering empty turns first

Routing by side is therefore a requirement, not a convenience: running the human
producer over a synthetic window would not reproduce the frozen values.

Only metrics the catalogue permits are computed. Withheld and retired metrics have no
code path here. `reference_density` keeps its self-invalidating behaviour and becomes
REQUIRES_RESEARCHER_ADJUDICATION when the producer reports itself invalid.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import CatalogEntry, MetricCatalog, RuntimeStatus, Status, load_catalog
from .catalog import resolve_runtime_status
from .config import REPO_ROOT
from .provenance import ProvenanceBlock, code_content_hash
from .transcripts import (CanonicalTranscript, to_human_producer_turns,
                          to_synthetic_producer_entries)

_SCRIPTS = REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

AGGREGATION_PATH = "run -> focus group -> study replicate"

# Phase 2B.1: the only methodological mode implemented. It reproduces the thesis by
# routing to the SAME two producers the frozen results came from. A harmonised
# structural producer is deliberately NOT built: it would be a new instrument, and a
# new instrument cannot reproduce a frozen result.
FROZEN_COMPATIBILITY = "FROZEN_COMPATIBILITY"

PRODUCER_RULES = {
    "human": {
        "producer": "scripts.structural_metrics_transportability.compute",
        "moderator_rule": "speaker_role == 'moderator', read from the transcript",
        "entry_exclusion_rule": "none; every entry counts",
        "word_count_rule": "whitespace split of the entry content",
        "reference_density": ("first-name token match on the participant roster; the "
                              "producer reports reference_density_valid and flags "
                              "collapsed or unrepresentable labels"),
    },
    "synthetic": {
        "producer": ("scripts.aggregate_production_results."
                     "compute_structural_metrics"),
        "moderator_rule": "speaker_id.upper() == 'MODERATOR'",
        "entry_exclusion_rule": ("blind_included_entries: entries whose content is "
                                 "empty after stripping are excluded, matching what "
                                 "the evaluator saw"),
        "word_count_rule": "whitespace split of the entry content",
        "reference_density": ("explicit first-name token match on the run roster; a "
                              "LOWER BOUND when roster names are ambiguous"),
    },
}

NEW_CORPUS_NOTICE = (
    "Metrics are computed under FROZEN_COMPATIBILITY rules - the two producers the "
    "thesis results came from. Those rules encode decisions made for the Macho Meals "
    "corpus (how the moderator is identified, which entries are excluded, how words "
    "are counted). They are not automatically transportable to a new corpus without "
    "additional validation, and reference_density in particular is a lower bound "
    "whenever roster names are ambiguous.")


def producer_metadata(side: str, producer_module) -> dict:
    """Everything a reader needs to know which instrument produced a number."""
    import hashlib
    import inspect
    rules = dict(PRODUCER_RULES[side])
    try:
        src = inspect.getsource(producer_module).encode("utf-8")
        rules["producer_sha256"] = hashlib.sha256(src).hexdigest()[:16]
    except (OSError, TypeError):
        rules["producer_sha256"] = "unavailable"
    rules["mode"] = FROZEN_COMPATIBILITY
    return rules

# Metric ids this runner can produce, by side. Read from the producers themselves;
# anything outside the catalogue's permitted set is dropped before it reaches a result.
STRUCTURAL_METRIC_IDS = (
    "words_per_turn_median", "words_per_turn_iqr",
    "short_turn_proportion_25w", "short_turn_proportion_10w",
    "short_turn_proportion_50w",
    "turn_balance_gini", "word_balance_gini",
    "moderator_turn_share", "moderator_word_share",
    "participant_participant_adjacency", "reference_density", "chain_depth",
)

# Counts the producers also emit. They are not registry metrics; they travel as
# denominators and diagnostics, never as results.
COUNT_KEYS = ("participant_turns", "moderator_turns", "participant_words",
              "total_words", "chain_depth_max", "chain_depth_n_chains",
              "reference_density_ambiguous_names_excluded")


class Level2Error(RuntimeError):
    pass


@dataclass
class MetricResult:
    metric_id: str
    status: str
    scope: str
    value: float | int | None
    denominator: dict
    transcript_id: str
    transcript_type: str
    condition: str | None = None
    focus_group: str | None = None
    replicate_label: str | None = None
    exclusions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    review_items: list[str] = field(default_factory=list)
    aggregation_path: str = AGGREGATION_PATH
    provenance: dict = field(default_factory=dict)


@dataclass
class Level2Run:
    transcript_id: str
    transcript_type: str
    producer: str
    results: list[MetricResult]
    counts: dict
    blocked: list[str] = field(default_factory=list)
    review_items: list[str] = field(default_factory=list)
    mode: str = FROZEN_COMPATIBILITY
    producer_rules: dict = field(default_factory=dict)
    transportability_notice: str = NEW_CORPUS_NOTICE


def _human_producer():
    import structural_metrics_transportability as S      # noqa: N813
    return S


def _synthetic_producer():
    import aggregate_production_results as A             # noqa: N813
    return A


def _denominator_for(metric_id: str, counts: dict) -> dict:
    p, m = counts.get("participant_turns"), counts.get("moderator_turns")
    total_turns = None if p is None or m is None else p + m
    table = {
        "words_per_turn_median": (p, "participant turns"),
        "words_per_turn_iqr": (p, "participant turns"),
        "short_turn_proportion_25w": (p, "participant turns"),
        "short_turn_proportion_10w": (p, "participant turns"),
        "short_turn_proportion_50w": (p, "participant turns"),
        "reference_density": (p, "participant turns"),
        "turn_balance_gini": (p, "participant turns, grouped by speaker"),
        "word_balance_gini": (p, "participant turns, grouped by speaker"),
        "moderator_turn_share": (total_turns, "all turns in the window"),
        "moderator_word_share": (counts.get("total_words"), "all words in the window"),
        "participant_participant_adjacency": (
            None if total_turns is None else max(total_turns - 1, 0),
            "turn transitions"),
        "chain_depth": (counts.get("chain_depth_n_chains"),
                        "participant-to-participant chains"),
    }
    value, definition = table.get(metric_id, (None, "see the metric registry"))
    return {"value": value, "definition": definition}


def _provenance(entry: CatalogEntry, catalog: MetricCatalog, status: str,
                source_path: str, source_sha: str, denominator: dict,
                producer: str) -> dict:
    block = ProvenanceBlock(
        metric_id=entry.metric_id,
        status=status,
        code_content_hash=code_content_hash(),
        metric_registry_hash=catalog.registry_sha256,
        metric_version=entry.metric_version,
        inputs=[{"path": source_path, "sha256": source_sha, "role": "transcript"}],
        parameters={"producer": producer},
        denominator=denominator,
        aggregation_path=AGGREGATION_PATH,
        result_class=("primary" if entry.status is Status.AVAILABLE_VALIDATED
                      else "exploratory"),
    ).stamp()
    return block.to_dict()


def run_level2(transcript: CanonicalTranscript, *,
               roster_names: list[str] | None = None,
               catalog: MetricCatalog | None = None,
               window_source: str | None = None,
               window_sha256: str | None = None) -> Level2Run:
    """
    Compute the permitted Level 2 metrics for one transcript.

    Blocks - rather than guessing - when normalisation left a required field
    unresolved: `structural_metrics_transportability.compute` needs `speaker_role`
    and `canonical_speaker_id`, so an unresolved turn makes the whole side
    unavailable with that reason stated.
    """
    cat = catalog or load_catalog()
    blocked: list[str] = []
    reviews = [f"{r.kind}:{r.subject}" for r in transcript.review_items]

    unresolved = transcript.blocked_fields()
    if unresolved:
        blocked = sorted(unresolved)
        results = []
        for metric_id in STRUCTURAL_METRIC_IDS:
            entry = cat.get(metric_id)
            results.append(MetricResult(
                metric_id=metric_id,
                status=RuntimeStatus.NOT_APPLICABLE_MISSING_INPUT.value,
                scope=entry.unit_of_analysis,
                value=None,
                denominator={"value": None,
                             "definition": "unavailable: normalisation incomplete"},
                transcript_id=transcript.transcript_id,
                transcript_type=transcript.transcript_type,
                condition=transcript.condition,
                focus_group=transcript.focus_group,
                replicate_label=transcript.replicate_label,
                warnings=[f"unresolved field(s) {blocked} in "
                          f"{len(transcript.unresolved_turn_ids)} turn(s); no value "
                          f"is assigned by position"],
                review_items=reviews,
            ))
        return Level2Run(transcript.transcript_id, transcript.transcript_type,
                         producer="none", results=results, counts={},
                         blocked=blocked, review_items=reviews)

    if transcript.transcript_type == "human":
        producer = "structural_metrics_transportability.compute"
        S = _human_producer()
        if roster_names is None:
            raise Level2Error(
                "the human producer needs the participant roster; pass roster_names "
                "read from participant_metadata.json")
        raw = S.compute(to_human_producer_turns(transcript), roster_names)
        producer_rules = producer_metadata("human", S)
        counts = {k: raw.get(k) for k in COUNT_KEYS}
        values = {k: raw.get(k) for k in STRUCTURAL_METRIC_IDS}
        ref_valid = bool(raw.get("reference_density_valid", True))
    else:
        producer = "aggregate_production_results.compute_structural_metrics"
        A = _synthetic_producer()
        out = A.compute_structural_metrics(to_synthetic_producer_entries(transcript))
        producer_rules = producer_metadata("synthetic", A)
        rows = {r["metric_id"]: r for r in out["metrics"]}
        values = {k: (rows[k]["value"] if k in rows else None)
                  for k in STRUCTURAL_METRIC_IDS}
        counts = {k: (rows[k]["value"] if k in rows else None) for k in COUNT_KEYS}
        ref = rows.get("reference_density", {})
        ref_valid = bool(ref.get("valid", True)) if "valid" in ref else True

    results: list[MetricResult] = []
    for metric_id in STRUCTURAL_METRIC_IDS:
        entry = cat.assert_computable(metric_id)          # withheld/retired raise
        denominator = _denominator_for(metric_id, counts)
        status, reason = resolve_runtime_status(
            entry, has_human_referent=True,
            self_reported_valid=(ref_valid if metric_id == "reference_density"
                                 else True))
        value = values.get(metric_id)
        warnings: list[str] = []
        if reason:
            warnings.append(reason)
        if status is RuntimeStatus.REQUIRES_RESEARCHER_ADJUDICATION:
            value = None                                   # computed, not reported
            reviews.append(f"METRIC_INVALID:{metric_id}")

        results.append(MetricResult(
            metric_id=metric_id,
            status=status.value if hasattr(status, "value") else str(status),
            scope=entry.unit_of_analysis,
            value=value,
            denominator=denominator,
            transcript_id=transcript.transcript_id,
            transcript_type=transcript.transcript_type,
            condition=transcript.condition,
            focus_group=transcript.focus_group,
            replicate_label=transcript.replicate_label,
            warnings=warnings,
            review_items=[r for r in reviews if r.endswith(metric_id)],
            provenance=_provenance(
                entry, cat,
                status.value if hasattr(status, "value") else str(status),
                window_source or transcript.source_file,
                window_sha256 or transcript.source_sha256,
                denominator, producer),
        ))

    return Level2Run(transcript.transcript_id, transcript.transcript_type,
                     producer=producer, results=results, counts=counts,
                     blocked=blocked, review_items=sorted(set(reviews)),
                     mode=FROZEN_COMPATIBILITY, producer_rules=producer_rules)
