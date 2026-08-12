"""
Frozen benchmark, read-only.

Everything the benchmark screens show comes from here. The interface never opens a
protected artefact, never chooses an aggregation and never decides what a status
means; it receives rows that already carry their value, their n, their calculation
status and their reader-facing labels.

PRIMARY IS THE DEFAULT AND THE ONLY DEFAULT. `level1_rows()` returns primary coding.
The sensitivity re-coding is reachable only through `level1_sensitivity_rows()`, which
returns a different row type carrying BOTH values side by side - so there is no shape
of data in this module that could be dropped into the primary table by mistake.
"""
from __future__ import annotations

import statistics

from .. import theme
from ..aggregate import (CONDITIONS, FGS, REPLICATES, CalculationStatus,
                         CoveragePolicy, aggregate_focus_group_condition,
                         aggregate_study_replicates, aggregate_words_per_turn,
                         check_integrity, frozen_workbook_route,
                         load_frozen_metric_rows)
from .. import thematic as TH

FOCUS_GROUP_VIEW = "focus_group"
STUDY_REPLICATE_VIEW = "study_replicate"
VIEWS = (FOCUS_GROUP_VIEW, STUDY_REPLICATE_VIEW)

# The seven metrics of the frozen structural table, in the sheet's own order.
LEVEL2_SHEET_METRICS = ("total_words", "participant_turns", "words_per_turn_iqr",
                        "short_turn_proportion_25w", "turn_balance_gini",
                        "chain_depth", "moderator_word_share")

LEVEL1_METRICS = ("tier1_subtheme_recall", "tier1_matched_theme_precision",
                  "tier1_f1_secondary", "tier1_participant_reach",
                  "tier1_participant_reach_shared_only")

# Known disagreements BETWEEN FROZEN ARTEFACTS. Recorded here, shown under
# methodological details, and deliberately not raised as a run-time error: the
# platform is not broken, two published tables are 1e-4 apart.
KNOWN_ARTEFACT_DISCREPANCIES = [
    {
        "metric_id": "tier1_f1_secondary",
        "summary": "two frozen artefacts differ by 0.0001 in one cell",
        "detail": ("`primary_effects_by_fg.csv` computes F1 from full-precision "
                   "recall and precision; `study_replication_summary.csv` averages "
                   "the values already rounded to 4 decimals in "
                   "`per_run_metrics.csv`. In demographics-only study replicate 2 "
                   "they read 0.3641 and 0.3642."),
        "resolution": ("this platform computes F1 from the numerator and denominator "
                       "at full precision - the definition - and shows that single "
                       "value. The alternative rounding is not displayed as a second "
                       "number and is not an error."),
        "affects_displayed_value": False,
    },
]


class BenchmarkError(RuntimeError):
    pass


class BenchmarkSourceChanged(BenchmarkError):
    """A protected source no longer matches its pinned hash."""


# ------------------------------------------------------------------- integrity
def check_sources() -> dict:
    """
    Verify every protected Level 1 source and the Level 2 coverage before anything is
    displayed. A changed benchmark source is an actionable condition, not a crash.
    """
    level1 = TH.verify_sources()
    problems = [f"{r['key']}: {'; '.join(r.get('problems') or ['missing'])}"
                for r in level1 if not r.get("ok")]

    rows = load_frozen_metric_rows()
    coverage = check_integrity(rows)
    if not coverage.complete:
        problems.extend(coverage.problems())

    return {"ok": not problems, "problems": problems,
            "n_level1_sources": len(level1),
            "n_level2_metrics": len(coverage.per_metric),
            "code": "protected benchmark source changed" if problems else None}


def assert_sources_ok() -> None:
    report = check_sources()
    if not report["ok"]:
        raise BenchmarkSourceChanged(
            "the protected benchmark sources no longer match their pinned state: "
            + "; ".join(report["problems"][:5]))


# ============================================================== LEVEL 1 (frozen)
def _level1_row(metric_id, condition, unit_label, unit_value, value, n_valid,
                n_expected, calculation_status, coding_basis, warnings,
                details) -> dict:
    return {
        "metric_id": metric_id,
        "metric": theme.metric_label(metric_id),
        "condition": condition,
        "condition_label": theme.condition_label(condition),
        "unit": unit_label,
        "unit_value": unit_value,
        "value": value,
        "value_display": theme.format_value(value),
        "n_valid": n_valid,
        "n_expected": n_expected,
        "calculation_status": calculation_status,
        "calculation_status_label": theme.calculation_status_label(
            calculation_status),
        "coding_basis": coding_basis,
        "coding_basis_label": theme.CODING_BASIS_LABELS.get(coding_basis,
                                                            coding_basis),
        "warnings": list(warnings or []),
        "details": details or {},
    }


def _primary_results():
    """
    The canonical Level 1 results. F1 comes from `thematic.f1_results`, which computes
    it from the counts at full precision - see KNOWN_ARTEFACT_DISCREPANCIES.
    """
    return TH.primary_results(LEVEL1_METRICS)


def level1_rows(view: str = FOCUS_GROUP_VIEW,
                metric_ids=None) -> list[dict]:
    """PRIMARY coding. There is no `basis` argument, on purpose."""
    if view not in VIEWS:
        raise BenchmarkError(f"unknown view {view!r}; expected one of {list(VIEWS)}")
    metric_ids = tuple(metric_ids or LEVEL1_METRICS)
    results = [r for r in _primary_results() if r.metric_id in metric_ids]

    rows: list[dict] = []
    if view == FOCUS_GROUP_VIEW:
        for cell in TH.aggregate_thematic_focus_group_condition(results):
            spec = TH.METRIC_SPECS[cell.metric_id]
            rows.append(_level1_row(
                cell.metric_id, cell.condition, "Focus group", cell.focus_group,
                cell.summary.mean, cell.summary.n_valid, cell.summary.n_expected,
                cell.calculation_status, cell.coding_basis,
                ([cell.summary.undefined_reason] if cell.summary.undefined_reason
                 else []) + cell.caveats,
                {"statistic": spec.statistic_name or "mean of the three runs",
                 "numerator": spec.numerator, "denominator": spec.denominator,
                 "estimand": spec.estimand,
                 "aggregation_rule": spec.aggregation_rule,
                 "human_reference": cell.human_reference,
                 "human_reference_note": cell.human_reference_note,
                 "source_artifact": TH.SOURCES[spec.source_key].relative_path,
                 "source_hash": TH.SOURCES[spec.source_key].sha256(),
                 "run_values": cell.summary.values}))
    else:
        for rep in TH.aggregate_thematic_study_replicates(results):
            spec = TH.METRIC_SPECS[rep.metric_id]
            rows.append(_level1_row(
                rep.metric_id, rep.condition, "Study replicate",
                rep.replicate_index, rep.summary.mean, rep.summary.n_valid,
                rep.summary.n_expected, rep.calculation_status, rep.coding_basis,
                [rep.note] + ([rep.summary.undefined_reason]
                              if rep.summary.undefined_reason else []),
                {"statistic": "mean across the five focus groups",
                 "numerator": spec.numerator, "denominator": spec.denominator,
                 "estimand": spec.estimand,
                 "aggregation_rule": spec.aggregation_rule,
                 "fgs_included": rep.fgs_included,
                 "source_artifact": TH.SOURCES[spec.source_key].relative_path,
                 "source_hash": TH.SOURCES[spec.source_key].sha256(),
                 "focus_group_values": rep.summary.values}))
    return rows


def level1_condition_summary(view: str = FOCUS_GROUP_VIEW) -> list[dict]:
    """One row per metric x condition: the mean of the cells, with the n."""
    rows = level1_rows(view)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        grouped.setdefault((r["metric_id"], r["condition"]), []).append(r)

    out = []
    for (metric_id, condition), group in sorted(grouped.items()):
        values = [g["value"] for g in group if g["value"] is not None]
        out.append(_level1_row(
            metric_id, condition,
            "Focus groups" if view == FOCUS_GROUP_VIEW else "Study replicates",
            f"{len(values)} of {len(group)}",
            statistics.mean(values) if values else None,
            len(values), len(group), group[0]["calculation_status"],
            group[0]["coding_basis"],
            [] if len(values) == len(group)
            else [f"{len(group) - len(values)} cell(s) undefined; the mean is over "
                  f"n={len(values)}, not imputed"],
            dict(group[0]["details"], cell_values=[g["value"] for g in group])))
    return out


def level1_recurrence_rows() -> list[dict]:
    """Thematic recurrence: counted across focus groups, not across participants."""
    out = []
    for r in TH.recurrence_across_focus_groups():
        subtheme = r.caveats[0].removeprefix("subtheme ")
        out.append({
            "metric_id": r.metric_id,
            "metric": theme.metric_label(r.metric_id),
            "condition": r.condition,
            "condition_label": theme.condition_label(r.condition),
            "replicate_index": r.replicate_index,
            "subtheme_id": subtheme,
            "n_focus_groups": r.numerator,
            "value": r.value,
            "value_display": theme.format_percent(r.value, digits=0),
            "coding_basis": r.coding_basis,
            "calculation_status": r.calculation_status,
            "calculation_status_label": theme.calculation_status_label(
                r.calculation_status),
            "details": {"denominator": "the five focus groups of one realisation",
                        "counted_across": "FOCUS GROUPS, not participants",
                        "source_artifact": r.source_artifact,
                        "source_hash": r.source_hash},
        })
    return out


def level1_ordering_rows(view: str = FOCUS_GROUP_VIEW) -> list[dict]:
    """
    Agreement in thematic ordering. The statistical name lives in `details`.
    """
    rows = []
    if view == FOCUS_GROUP_VIEW:
        for r in TH.salience_ordering_by_focus_group():
            rows.append({
                "metric_id": r["metric_id"],
                "metric": r["label"],
                "condition": r["condition"],
                "condition_label": theme.condition_label(r["condition"]),
                "unit": "Focus group",
                "unit_value": r["focus_group"],
                "value": r["median"],
                "value_display": theme.format_value(r["median"]),
                "n_valid": r["n_defined"],
                "n_expected": r["n_replicates"],
                "calculation_status": r["calculation_status"],
                "calculation_status_label": theme.calculation_status_label(
                    r["calculation_status"]),
                "coding_basis": r["coding_basis"],
                "warnings": ([] if r["n_defined"] == r["n_replicates"] else
                             [f"{r['n_replicates'] - r['n_defined']} run(s) have no "
                              f"defined value; the cell is summarised over "
                              f"n={r['n_defined']}"]),
                "details": {"statistic": "Kendall tau-b",
                            "range": "-1 to 1",
                            "minimum": r["minimum"], "maximum": r["maximum"],
                            "zero_means": "no association in ordering, NOT 'no "
                                          "themes in common'",
                            "verification": r["verification"]},
            })
        return rows

    for r in TH.salience_ordering_agreement():
        rows.append({
            "metric_id": r["metric_id"], "metric": r["label"],
            "condition": r["condition"],
            "condition_label": theme.condition_label(r["condition"]),
            "unit": "Study replicate", "unit_value": r["replicate_index"],
            "focus_group": r["focus_group"],
            "value": r["value"], "value_display": theme.format_value(r["value"]),
            "n_valid": 1 if r["value"] is not None else 0, "n_expected": 1,
            "calculation_status": r["calculation_status"],
            "calculation_status_label": theme.calculation_status_label(
                r["calculation_status"]),
            "coding_basis": r["coding_basis"],
            "warnings": [r["undefined_reason"]] if r["undefined_reason"] else [],
            "details": dict(r["metadata"], source_artifact=r["source_artifact"],
                            source_hash=r["source_hash"],
                            verification=r["verification"]),
        })
    return rows


def level1_accumulation() -> dict:
    """Inductive theme accumulation: the curve per condition and its realisations."""
    by_condition = TH.accumulation_by_condition()
    series = {}
    for row in by_condition:
        series[row["condition"]] = [p["mean"] for p in row["per_position"]]
    return {
        "positions": list(TH.ACCUMULATION_POSITIONS),
        "series": series,
        "colours": {c: theme.condition_colour(c) for c in series},
        "labels": {c: theme.condition_label(c) for c in series},
        "per_condition": by_condition,
        "unit": "% of that condition's final repertoire",
        "calculation_status": CalculationStatus.DERIVED_FROM_FROZEN.value,
        "calculation_status_label": theme.calculation_status_label(
            CalculationStatus.DERIVED_FROM_FROZEN.value),
        "caveat": ("each condition's percentage is of its OWN final repertoire; "
                   "equal accumulation speed does not mean the same categories"),
    }


def level1_sensitivity_rows(treatment: str = "CONTESTED_AS_PRESENT") -> list[dict]:
    """
    The adjudicated sensitivity, as a SEPARATE view.

    Every row carries both values under their own names. Nothing here has the shape of
    a primary row, so it cannot be rendered in the primary table by accident.
    """
    out = []
    for c in TH.recurrence_sensitivity(treatment):
        out.append({
            "metric_id": c.metric_id,
            "metric": theme.metric_label(c.metric_id),
            "condition": c.condition,
            "condition_label": theme.condition_label(c.condition),
            "replicate_index": c.replicate_index,
            "subtheme_id": c.subtheme_id,
            "primary_value": c.primary_value,
            "primary_display": theme.format_percent(c.primary_value, digits=0),
            "sensitivity_value": c.sensitivity_value,
            "sensitivity_display": theme.format_percent(c.sensitivity_value,
                                                        digits=0),
            "delta": c.delta,
            "changed": bool(c.delta),
            "treatment": c.treatment,
            "coding_basis": "SENSITIVITY",
            "primary_is_unmodified": c.primary_is_unmodified,
            "note": c.note,
            "source_artifact": c.source_artifact,
            "source_hash": c.source_hash,
        })
    return out


def level1_ordering_sensitivity() -> dict:
    return TH.ordering_agreement_sensitivity()


def guide_coverage_notice() -> dict:
    status = TH.guide_coverage_status()
    return {
        "metric_id": "guide_coverage",
        "metric": "Guide coverage",
        "display": "Not available — no validated definition or source artefact",
        "blocks_other_metrics": status["blocks_other_metrics"],
        "reason": status["reason"],
        "explicitly_not_done": status["explicitly_not_done"],
        "to_implement_it_would_need": status["to_implement_it_would_need"],
    }


# ============================================================== LEVEL 2 (frozen)
def _level2_row(metric_id, condition, unit_label, unit_value, value, n_valid,
                n_expected, provenance, warnings, details) -> dict:
    status = (provenance or {}).get("calculation_status")
    return {
        "metric_id": metric_id,
        "metric": theme.metric_label(metric_id),
        "condition": condition,
        "condition_label": theme.condition_label(condition),
        "unit": unit_label,
        "unit_value": unit_value,
        "value": value,
        "value_display": theme.format_value(value),
        "n_valid": n_valid,
        "n_expected": n_expected,
        "calculation_status": status,
        "calculation_status_label": theme.calculation_status_label(status),
        "warnings": list(warnings or []),
        "details": dict(details or {}, **(provenance or {})),
    }


def level2_rows(view: str = FOCUS_GROUP_VIEW, metric_ids=None) -> list[dict]:
    if view not in VIEWS:
        raise BenchmarkError(f"unknown view {view!r}; expected one of {list(VIEWS)}")
    metric_ids = tuple(metric_ids or LEVEL2_SHEET_METRICS)
    rows = load_frozen_metric_rows()

    out: list[dict] = []
    if view == FOCUS_GROUP_VIEW:
        cells = aggregate_focus_group_condition(rows, metric_ids,
                                                policy=CoveragePolicy.STRICT)
        # The human side of a focus group is one value, carried on every cell of that
        # focus group; emit it once, as its own row, so the table has three
        # conditions rather than a synthetic row with a human column bolted on.
        seen_human = set()
        for cell in cells:
            out.append(_level2_row(
                cell.metric_id, cell.condition, "Focus group", cell.focus_group,
                cell.summary.mean, cell.summary.n_valid, cell.summary.n_expected,
                cell.provenance,
                [cell.summary.undefined_reason] if cell.summary.undefined_reason
                else [],
                {"run_values": cell.summary.values, "runs": cell.runs,
                 "minimum": cell.summary.minimum, "maximum": cell.summary.maximum,
                 "aggregation_rule": cell.aggregation_rule}))
            key = (cell.metric_id, cell.focus_group)
            if key not in seen_human:
                seen_human.add(key)
                out.append(_level2_row(
                    cell.metric_id, theme.HUMAN, "Focus group", cell.focus_group,
                    cell.human_value, 1 if cell.human_value is not None else 0, 1,
                    dict(cell.provenance, aggregation_rule="single human focus group"),
                    [], {"aggregation_rule": "one human focus group; not a mean"}))
    else:
        for rep in aggregate_study_replicates(rows, metric_ids,
                                              policy=CoveragePolicy.STRICT):
            out.append(_level2_row(
                rep.metric_id, rep.condition, "Study replicate",
                rep.replicate_index, rep.summary.mean, rep.summary.n_valid,
                rep.summary.n_expected, rep.provenance,
                [rep.summary.undefined_reason] if rep.summary.undefined_reason
                else [],
                {"fgs_included": rep.fgs_included,
                 "focus_group_values": rep.summary.values,
                 "minimum": rep.summary.minimum, "maximum": rep.summary.maximum}))
    return out


def level2_condition_summary(metric_ids=None) -> list[dict]:
    """
    The frozen structural table itself: human, enriched and demographics-only means
    over the five focus groups, with the count of focus groups where enriched is
    closer to human.
    """
    metric_ids = tuple(metric_ids or LEVEL2_SHEET_METRICS)
    rows = load_frozen_metric_rows()
    out = []
    for record in frozen_workbook_route(rows, metric_ids,
                                        policy=CoveragePolicy.STRICT):
        out.append({
            "metric_id": record["metric"],
            "metric": theme.metric_label(record["metric"]),
            "human": record["human_mean"],
            "enriched": record["enriched_mean"],
            "demographics-only": record["demographics_only_mean"],
            "human_display": theme.format_value(record["human_mean"]),
            "enriched_display": theme.format_value(record["enriched_mean"]),
            "demographics-only_display": theme.format_value(
                record["demographics_only_mean"]),
            "enriched_minus_demographics_only": record["enriched_minus_demo"],
            "n_fg_enriched_closer_to_human": record["n_fg_enriched_closer_to_human"],
            "n_fgs": record["n_fgs"],
            "coverage_status": record["coverage_status"],
            "calculation_status": record["calculation_status"],
            "calculation_status_label": theme.calculation_status_label(
                record["calculation_status"]),
            "details": {"source_artifact": record["source_artifact"],
                        "aggregation_rule": record["aggregation_rule"],
                        "aggregation_version": record["aggregation_version"]},
        })
    return out


def level2_words_per_turn() -> dict:
    """
    The binned distribution, from the existing hierarchical aggregation.

    Percentages come from `aggregate_words_per_turn`, which computes them INSIDE each
    run and then averages. Nothing is recomputed here from pooled turns.
    """
    payload = aggregate_words_per_turn()
    bins = payload["bins"]

    series: dict[str, list[float]] = {}
    for condition in CONDITIONS:
        cond = payload["synthetic"]["per_condition"][condition]
        series[condition] = [cond["bins"][b]["mean_percent"] for b in bins]
    human = payload["human_reference"]["per_condition"][theme.HUMAN]
    series[theme.HUMAN] = [human["bins"][b]["mean_percent"] for b in bins]

    ordered = [c for c in theme.CONDITION_ORDER if c in series]
    return {
        "bins": bins,
        "series": {c: series[c] for c in ordered},
        "colours": {c: theme.condition_colour(c) for c in ordered},
        "labels": {c: theme.condition_label(c) for c in ordered},
        "unit": "% of that run's participant turns",
        "calculation_status": payload["calculation_status"],
        "calculation_status_label": theme.calculation_status_label(
            payload["calculation_status"]),
        "aggregation_rule": payload["aggregation_rule"],
        "source_artifact": payload["source_artifact"],
        "denominators": payload["denominators"],
        "bins_are_fixed": payload["bins_are_fixed"],
        "n_focus_groups": {c: payload["synthetic"]["per_condition"][c][
            "n_focus_groups"] for c in CONDITIONS},
    }


def benchmark_overview() -> dict:
    return {
        "study_name": "Macho Meals",
        "conditions": [theme.condition_label(c) for c in theme.CONDITION_ORDER],
        "n_focus_groups": len(FGS),
        "n_study_replicates": len(REPLICATES),
        "n_synthetic_runs": len(FGS) * len(REPLICATES) * len(CONDITIONS),
        "level1_metrics": [theme.metric_label(m) for m in LEVEL1_METRICS],
        "level2_metrics": [theme.metric_label(m) for m in LEVEL2_SHEET_METRICS],
        "read_only": True,
        "known_discrepancies": KNOWN_ARTEFACT_DISCREPANCIES,
        "source_inventory": TH.source_inventory(),
    }
