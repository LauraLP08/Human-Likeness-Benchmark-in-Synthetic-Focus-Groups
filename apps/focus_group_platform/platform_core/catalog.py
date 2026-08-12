"""
Metric catalogue and the eight-status model (ADR-004 + Amendment 1).

The catalogue is a READ-ONLY projection of
`analysis/production_evaluation/metric_registry.csv` plus this application's status.
No metric is defined here; definitions, denominators, aggregation and caveats are the
registry's own text and are surfaced verbatim.

Two statuses have no code path to a value: NOT_IN_REPORTED_INSTRUMENT and
RETIRED_NOT_FOR_FIDELITY. `assert_computable` raises for both, and their
`permitted_outputs` is `("catalogue_only",)`.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import REPO_ROOT

REGISTRY_PATH = REPO_ROOT / "analysis" / "production_evaluation" / "metric_registry.csv"


class Status(str, Enum):
    """Catalogue statuses - the ceiling for a metric."""

    AVAILABLE_VALIDATED = "AVAILABLE_VALIDATED"
    AVAILABLE_EXPLORATORY = "AVAILABLE_EXPLORATORY"
    NOT_IN_REPORTED_INSTRUMENT = "NOT_IN_REPORTED_INSTRUMENT"
    DEFERRED_NOT_IMPLEMENTED = "DEFERRED_NOT_IMPLEMENTED"
    NOT_APPLICABLE_MISSING_INPUT = "NOT_APPLICABLE_MISSING_INPUT"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    REQUIRES_RESEARCHER_ADJUDICATION = "REQUIRES_RESEARCHER_ADJUDICATION"
    RETIRED_NOT_FOR_FIDELITY = "RETIRED_NOT_FOR_FIDELITY"


class RuntimeStatus(str, Enum):
    """Statuses a RESULT can take that a catalogue entry cannot."""

    NOT_APPLICABLE_MISSING_INPUT = "NOT_APPLICABLE_MISSING_INPUT"
    NOT_APPLICABLE_MISSING_HUMAN_REFERENCE = "NOT_APPLICABLE_MISSING_HUMAN_REFERENCE"
    NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE = "NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE"
    REQUIRES_RESEARCHER_ADJUDICATION = "REQUIRES_RESEARCHER_ADJUDICATION"


# Registry evidence_class -> catalogue status. Explicit; no fallback guessing.
EVIDENCE_CLASS_TO_STATUS = {
    "AUTOMATIC_VALIDATED": Status.AVAILABLE_VALIDATED,
    "AUTOMATIC_DIAGNOSTIC": Status.AVAILABLE_EXPLORATORY,
    "LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC": Status.AVAILABLE_EXPLORATORY,
    "EXPLORATORY": Status.AVAILABLE_EXPLORATORY,
    "NOT_IN_REPORTED_INSTRUMENT": Status.NOT_IN_REPORTED_INSTRUMENT,
    "REPORTED_VIA_AUTOMATIC_PRODUCER": Status.AVAILABLE_VALIDATED,
    "DEFERRED_NOT_IMPLEMENTED": Status.DEFERRED_NOT_IMPLEMENTED,
    "RETIRED_NOT_FOR_FIDELITY": Status.RETIRED_NOT_FOR_FIDELITY,
}

STATUS_REASON = {
    Status.AVAILABLE_VALIDATED:
        "Validated for primary reporting.",
    Status.AVAILABLE_EXPLORATORY:
        "Computed, but reportable only as exploratory or diagnostic - never as a "
        "primary claim.",
    Status.NOT_IN_REPORTED_INSTRUMENT:
        "Designed and not adopted. The reported benchmark measures this construct "
        "with a deterministic automatic producer that transfers to any corpus; this "
        "operationalisation is kept in the catalogue as a record of the alternative. "
        "No value is computed.",
    Status.DEFERRED_NOT_IMPLEMENTED:
        "Defined in the registry with no working producer. Nothing to compute.",
    Status.RETIRED_NOT_FOR_FIDELITY:
        "Retired as a fidelity indicator. It remains in the registry as a record of "
        "what was tried and withdrawn. No value is computed.",
    Status.SYNTHETIC_ONLY:
        "Defined only for synthetic runs, over the full run rather than the "
        "comparable window. A human transcript cannot produce it.",
    Status.NOT_APPLICABLE_MISSING_INPUT:
        "A required input is absent for this dataset.",
    Status.REQUIRES_RESEARCHER_ADJUDICATION:
        "Computed, but this corpus produced a condition the metric itself flags as "
        "invalid or ambiguous.",
}

# permitted_outputs per status. Enforced, not advisory.
PERMITTED_OUTPUTS = {
    Status.AVAILABLE_VALIDATED: ("primary_table", "exploratory_table", "figure",
                                 "report_body"),
    Status.AVAILABLE_EXPLORATORY: ("exploratory_table", "figure", "report_body"),
    Status.SYNTHETIC_ONLY: ("exploratory_table", "figure", "report_body"),
    Status.NOT_IN_REPORTED_INSTRUMENT: ("catalogue_only",),
    Status.RETIRED_NOT_FOR_FIDELITY: ("catalogue_only",),
    Status.DEFERRED_NOT_IMPLEMENTED: ("catalogue_only",),
    Status.NOT_APPLICABLE_MISSING_INPUT: ("exploratory_table",),
    Status.REQUIRES_RESEARCHER_ADJUDICATION: ("catalogue_only",),
}

NEVER_COMPUTABLE = (Status.NOT_IN_REPORTED_INSTRUMENT,
                    Status.RETIRED_NOT_FOR_FIDELITY,
                    Status.DEFERRED_NOT_IMPLEMENTED)

# Stable internal family identifiers. The thesis level NUMBER is a display concern -
# it changes when the framework is re-presented, and burning it into an identifier is
# what made `level3_agent` and `PRODUCER_INVENTORY_LEVELS_1_3_4` age badly.
class Family(str, Enum):
    THEMATIC_FIDELITY = "THEMATIC_FIDELITY"
    INTERACTION_PROCESS = "INTERACTION_PROCESS"
    AGENT_FIDELITY = "AGENT_FIDELITY"
    OPERATIONAL = "OPERATIONAL"


# Display configuration, changeable without touching a single identifier.
FAMILY_DISPLAY = {
    Family.THEMATIC_FIDELITY: {"display_order": 1,
                               "display_label": "Level 1 - Thematic fidelity"},
    Family.INTERACTION_PROCESS: {"display_order": 2,
                                 "display_label": "Level 2 - Interaction process"},
    Family.AGENT_FIDELITY: {"display_order": 3,
                            "display_label": "Level 3 - Agent fidelity "
                                             "(exploratory)"},
    Family.OPERATIONAL: {"display_order": 4,
                         "display_label": "Operational diagnostics"},
}

REGISTRY_TIER_TO_FAMILY = {
    "Tier 1": Family.THEMATIC_FIDELITY,
    "Tier 2": Family.THEMATIC_FIDELITY,
    "Tier 2b": Family.THEMATIC_FIDELITY,
    "D2 proxy": Family.THEMATIC_FIDELITY,
    "structural": Family.INTERACTION_PROCESS,
    "interaction": Family.INTERACTION_PROCESS,
    "interpretive": Family.INTERACTION_PROCESS,
    "exploratory": Family.AGENT_FIDELITY,
    "operational": Family.OPERATIONAL,
}

# Retained so existing callers keep working; derived from the family, not parallel.
BENCHMARK_LEVEL = {
    "Tier 1": "level1_thematic",
    "Tier 2": "level2b_accumulation",
    "Tier 2b": "level2b_accumulation",
    "D2 proxy": "level2b_accumulation",
    "structural": "level2_interaction",
    "interaction": "level2_interaction",
    "interpretive": "level2_interaction",
    "exploratory": "level3_agent",
    "operational": "operational",
}

# Metrics whose registry namespace makes them synthetic-only regardless of class.
_FULL_RUN_NAMESPACE = "_full_run_operational"

# Comparative by construction: without a paired human file they resolve to
# NOT_APPLICABLE_MISSING_HUMAN_REFERENCE.
REQUIRES_HUMAN_REFERENT = {
    "tier1_subtheme_recall", "tier1_matched_theme_precision", "tier1_f1",
    "tier1_theme_level_recall", "tier1_theme_level_precision",
    "tier1_participant_reach", "tier1_salience_hierarchy",
    "tier1_coverage_by_word_count_curve", "tier1_length_matched_recall",
    "tier1_length_matched_precision", "length_ratio_synthetic_to_human",
    "tier2_open_themes", "tier2_not_observed_in_human_themes",
    "tier2_missed_themes", "evidence_localized_length_matched_recall",
    "evidence_localized_length_matched_precision",
}

# Metrics that ship their own validity flag and can require adjudication.
SELF_INVALIDATING = {"reference_density"}


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogEntry:
    metric_id: str
    display_name: str
    definition: str
    benchmark_level: str
    family: str
    display_order: int
    display_label: str
    registry_tier: str
    registry_evidence_class: str
    status: Status
    status_reason: str
    unit_of_analysis: str
    denominator_definition: str
    aggregation_hierarchy: str
    namespace: str
    requires_human_referent: bool
    requires_human_review: bool
    limitations: str
    permitted_outputs: tuple[str, ...]
    metric_version: str

    @property
    def computable(self) -> bool:
        return self.status not in NEVER_COMPUTABLE


@dataclass
class MetricCatalog:
    entries: dict[str, CatalogEntry] = field(default_factory=dict)
    registry_sha256: str = ""
    registry_path: str = ""

    def get(self, metric_id: str) -> CatalogEntry:
        try:
            return self.entries[metric_id]
        except KeyError:
            raise CatalogError(f"unknown metric_id {metric_id!r}") from None

    def by_status(self, status: Status) -> list[CatalogEntry]:
        return sorted((e for e in self.entries.values() if e.status == status),
                      key=lambda e: e.metric_id)

    def by_level(self, level: str) -> list[CatalogEntry]:
        return sorted((e for e in self.entries.values()
                       if e.benchmark_level == level), key=lambda e: e.metric_id)

    def by_family(self, family: "Family | str") -> list[CatalogEntry]:
        want = family.value if isinstance(family, Family) else family
        return sorted((e for e in self.entries.values() if e.family == want),
                      key=lambda e: e.metric_id)

    def assert_computable(self, metric_id: str) -> CatalogEntry:
        """
        The gate. Raises for WITHHELD, RETIRED and DEFERRED metrics.

        There is no flag, advanced mode or override that gets past this - which is the
        point. A withheld metric awaits a validation that could be obtained; a retired
        metric was judged unsuitable and withdrawn; neither may produce a value.
        """
        entry = self.get(metric_id)
        if not entry.computable:
            raise CatalogError(
                f"{metric_id} is {entry.status.value} and cannot be computed. "
                f"{entry.status_reason}")
        return entry

    def assert_output_allowed(self, metric_id: str, output: str) -> None:
        entry = self.get(metric_id)
        if output not in entry.permitted_outputs:
            raise CatalogError(
                f"{metric_id} ({entry.status.value}) may not appear in {output!r}; "
                f"permitted: {list(entry.permitted_outputs)}")


def _display_name(metric_id: str) -> str:
    return metric_id.replace("_", " ").strip()


def load_catalog(registry_path: Path | None = None) -> MetricCatalog:
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    raw_bytes = path.read_bytes()
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    if not rows:
        raise CatalogError(f"metric registry is empty: {path}")

    entries: dict[str, CatalogEntry] = {}
    for row in rows:
        metric_id = row["metric_id"].strip()
        evidence = row["evidence_class"].strip()
        namespace = row["namespace"].strip()
        try:
            status = EVIDENCE_CLASS_TO_STATUS[evidence]
        except KeyError:
            raise CatalogError(
                f"{metric_id}: unmapped registry evidence_class {evidence!r}. "
                f"Add an explicit mapping rather than guessing a status."
            ) from None
        if namespace == _FULL_RUN_NAMESPACE:
            status = Status.SYNTHETIC_ONLY

        tier = row["tier"].strip()
        if tier not in BENCHMARK_LEVEL:
            raise CatalogError(f"{metric_id}: unmapped registry tier {tier!r}")

        entries[metric_id] = CatalogEntry(
            metric_id=metric_id,
            display_name=_display_name(metric_id),
            definition=row["definition"].strip(),
            benchmark_level=BENCHMARK_LEVEL[tier],
            family=REGISTRY_TIER_TO_FAMILY[tier].value,
            display_order=FAMILY_DISPLAY[REGISTRY_TIER_TO_FAMILY[tier]][
                "display_order"],
            display_label=FAMILY_DISPLAY[REGISTRY_TIER_TO_FAMILY[tier]][
                "display_label"],
            registry_tier=tier,
            registry_evidence_class=evidence,
            status=status,
            status_reason=STATUS_REASON[status],
            unit_of_analysis=row["unit_of_analysis"].strip(),
            denominator_definition=row["denominator"].strip(),
            aggregation_hierarchy=row["aggregation"].strip(),
            namespace=namespace,
            requires_human_referent=metric_id in REQUIRES_HUMAN_REFERENT,
            requires_human_review=metric_id in SELF_INVALIDATING,
            limitations=row["notes_and_caveats"].strip(),
            permitted_outputs=PERMITTED_OUTPUTS[status],
            metric_version="registry@" + hashlib.sha256(raw_bytes).hexdigest()[:12],
        )

    return MetricCatalog(
        entries=entries,
        registry_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        registry_path=str(path),
    )


def resolve_runtime_status(entry: CatalogEntry, *, has_human_referent: bool,
                           instrument_available: bool = True,
                           self_reported_valid: bool = True
                           ) -> tuple[Status | RuntimeStatus, str | None]:
    """
    The catalogue status is the ceiling; this is what actually happened.

    A missing human referent NEVER yields zero - it yields a null value carrying
    NOT_APPLICABLE_MISSING_HUMAN_REFERENCE.
    """
    if not entry.computable:
        return entry.status, entry.status_reason
    if entry.requires_human_referent and not has_human_referent:
        return (RuntimeStatus.NOT_APPLICABLE_MISSING_HUMAN_REFERENCE,
                "no paired human transcript for this file; the metric is comparative "
                "by construction, so the value is undefined - not zero")
    if entry.benchmark_level == "level1_thematic" and not instrument_available:
        return (RuntimeStatus.NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE,
                "the required evaluator model is unavailable. The evaluator version "
                "is part of the instrument, so no substitute model is used")
    if entry.requires_human_review and not self_reported_valid:
        return (RuntimeStatus.REQUIRES_RESEARCHER_ADJUDICATION,
                "the metric reported itself invalid for this corpus; a researcher "
                "decision is required before any value is shown")
    return entry.status, None
