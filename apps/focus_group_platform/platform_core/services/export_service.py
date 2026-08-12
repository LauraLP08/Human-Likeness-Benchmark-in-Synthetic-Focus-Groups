"""
Exports.

Builds file payloads in memory and hands them back as `(filename, media_type, text)`.
It writes nothing by itself, so the interface's download buttons and a future CLI use
the same bytes.

Two rules:

  THE CLOCK TOUCHES THE ENVELOPE ONLY. `generated_utc` sits on the wrapper, never
  inside a result, so the same inputs always produce the same result payload and a
  test can compare two exports byte for byte.

  THE FROZEN SOURCES ARE NEVER COPIED. A benchmark export carries the numbers on
  screen plus each source's path, sha256 and calculation status - enough to trace
  every figure back, without redistributing or duplicating a protected artefact.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from ..aggregate import AGGREGATION_VERSION
from ..provenance import APPLICATION_VERSION, code_content_hash
from .. import thematic as TH

JSON_MEDIA = "application/json"
CSV_MEDIA = "text/csv"


class TraceabilityError(RuntimeError):
    """The pieces of an export do not describe the same transcript."""


def check_traceability(*, transcript_payload: dict, validation_payload: dict,
                       structural_payload: dict) -> list[str]:
    """
    The three parts of a project export must describe ONE transcript.

    Identifier and hashes are compared, not just the identifier: a transcript
    re-imported under the same name has the same id and different bytes, and an
    export that mixed the new canonical with the old validation would look perfectly
    consistent while being wrong.
    """
    problems: list[str] = []
    ids = {
        "canonical": transcript_payload.get("transcript_id"),
        "validation": validation_payload.get("transcript_id"),
        "level2": structural_payload.get("transcript_id"),
    }
    distinct = {v for v in ids.values() if v is not None}
    if len(distinct) != 1:
        problems.append(f"transcript ids disagree: {ids}")
    if None in ids.values():
        problems.append(f"a part carries no transcript id: {ids}")

    canonical_hash = transcript_payload.get("canonical_sha256")
    for name, payload in (("validation", validation_payload),
                          ("level2", structural_payload)):
        recorded = payload.get("canonical_sha256")
        if recorded is None:
            problems.append(f"the {name} record carries no canonical_sha256")
        elif canonical_hash is not None and recorded != canonical_hash:
            problems.append(
                f"the {name} record was produced from canonical "
                f"{recorded[:12]}… but the canonical form is now "
                f"{canonical_hash[:12]}…")

    source_hash = transcript_payload.get("source_sha256")
    recorded_source = validation_payload.get("source_sha256")
    if source_hash and recorded_source and source_hash != recorded_source:
        problems.append(
            f"the validation record was produced from source {recorded_source[:12]}… "
            f"but the canonical form records {source_hash[:12]}…")
    return problems


@dataclass
class ExportFile:
    filename: str
    media_type: str
    text: str

    @property
    def data(self) -> bytes:
        return self.text.encode("utf-8")


def _json(payload) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False)


def envelope(payload: dict, *, generated_utc: str, kind: str) -> dict:
    """The only place a timestamp enters an export."""
    return {
        "generated_utc": generated_utc,
        "export_kind": kind,
        "application_version": APPLICATION_VERSION,
        "aggregation_version": AGGREGATION_VERSION,
        "code_content_hash": code_content_hash(),
        "results": payload,
    }


def _csv_from_rows(rows: list[dict], columns=None) -> str:
    if not rows:
        return ""
    columns = list(columns or rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore",
                           lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c) for c in columns})
    return buffer.getvalue()


# ------------------------------------------------------------ project exports
LEVEL2_CSV_COLUMNS = ("transcript_id", "transcript_type", "metric_id", "metric",
                      "value", "value_display", "status", "scope", "denominator",
                      "denominator_definition", "warnings")


def project_export(*, transcript_payload: dict, validation_report: dict,
                   structural_payload: dict, structural_rows: list[dict],
                   generated_utc: str,
                   context: dict | None = None,
                   validation_payload: dict | None = None) -> list[ExportFile]:
    """
    The five files a new evaluation produces.

    `validation_payload` is the STORED envelope for this transcript, read by id. When
    it is supplied the traceability check runs and refuses to build a package whose
    three parts do not describe the same transcript at the same hash.
    """
    if validation_payload is not None:
        problems = check_traceability(
            transcript_payload=transcript_payload,
            validation_payload=validation_payload,
            structural_payload=structural_payload)
        if problems:
            raise TraceabilityError(
                "refusing to export: the canonical form, the validation report and "
                "the Level 2 result do not describe the same transcript — "
                + "; ".join(problems))
        validation_report = validation_payload.get("validation_report",
                                                   validation_report)

    rows = [dict(r, warnings="; ".join(r.get("warnings") or []))
            for r in structural_rows]

    provenance = {
        "application_version": APPLICATION_VERSION,
        "aggregation_version": AGGREGATION_VERSION,
        "code_content_hash": code_content_hash(),
        "transcript": {
            "transcript_id": transcript_payload.get("transcript_id"),
            "transcript_type": transcript_payload.get("transcript_type"),
            "source_file": transcript_payload.get("source_file"),
            "source_sha256": transcript_payload.get("source_sha256"),
            "schema_detected": (transcript_payload.get("normalisation") or {})
                .get("input_schema_detected"),
            "normaliser_version": (transcript_payload.get("normalisation") or {})
                .get("normaliser_version"),
            "declared_at_upload_not_a_reviewed_window":
                transcript_payload.get("window_declaration"),
        },
        "producer": {
            "producer": structural_payload.get("producer"),
            "mode": structural_payload.get("mode"),
            "rules": structural_payload.get("producer_rules"),
        },
        "denominators": {r["metric_id"]: {
            "value": r.get("denominator"),
            "definition": r.get("denominator_definition")} for r in structural_rows},
        "calculation_status": {r["metric_id"]: r.get("status")
                               for r in structural_rows},
        "transportability_notice": structural_payload.get(
            "transportability_notice"),
        "study_context": context,
        "frozen_benchmark_used": False,
        "frozen_benchmark_note": ("no frozen human referent was used; this export "
                                  "contains only results computed from the "
                                  "transcripts in this project"),
    }

    return [
        ExportFile("canonical_transcript.json", JSON_MEDIA,
                   _json(transcript_payload)),
        ExportFile("validation_report.json", JSON_MEDIA, _json(validation_report)),
        ExportFile("level2_results.json", JSON_MEDIA,
                   _json(envelope(structural_payload,
                                  generated_utc=generated_utc,
                                  kind="level2_results"))),
        ExportFile("level2_results.csv", CSV_MEDIA,
                   _csv_from_rows(rows, LEVEL2_CSV_COLUMNS)),
        ExportFile("provenance.json", JSON_MEDIA,
                   _json(envelope(provenance, generated_utc=generated_utc,
                                  kind="provenance"))),
    ]


# ------------------------------------------------------------- study package
ASSIGNMENT_COLUMNS = ("project_id", "design_id", "transcript_id", "condition_id",
                      "focus_group_id", "replicate_index", "role", "window_status",
                      "source_sha256", "canonical_sha256", "level2_freshness",
                      "assigned_utc")

RUN_COLUMNS = ("project_id", "design_id", "transcript_id", "condition_id",
               "focus_group_id", "replicate_index", "metric_id", "value",
               "denominator", "denominator_definition", "calculation_status",
               "coverage_status", "source_sha256", "canonical_sha256",
               "aggregation_rule")

FG_COLUMNS = ("project_id", "design_id", "unit", "condition_id", "focus_group_id",
              "replicate_index", "metric_id", "value", "median", "sd", "minimum",
              "maximum", "range", "human_reference", "n_valid", "n_expected",
              "calculation_status", "coverage_status", "transcript_ids",
              "aggregation_rule")

REPLICATE_COLUMNS = ("project_id", "design_id", "unit", "condition_id",
                     "focus_group_id", "replicate_index", "metric_id", "value",
                     "sd", "minimum", "maximum", "range", "n_valid", "n_expected",
                     "calculation_status", "coverage_status",
                     "focus_groups_included", "aggregation_rule")

# Every aggregate row is a new summary over the project's own runs; none of them is
# checked against any frozen table, because none exists for a user's corpus.
DERIVED = "DERIVED_FROM_PROJECT_RUNS"
MEASURED = "MEASURED_FROM_TRANSCRIPT"


def _join(value) -> str:
    if isinstance(value, (list, tuple)):
        return "|".join(str(v) for v in value)
    return "" if value is None else str(value)


def study_package(*, project_id: str, design: dict, assignments: list[dict],
                  coverage: dict, aggregation: dict,
                  run_results: dict[str, list[dict]],
                  transcript_index: dict[str, dict],
                  freshness: dict[str, str],
                  audit_summary: dict,
                  generated_utc: str) -> list[ExportFile]:
    """
    The coherent package for a whole study.

    Every row carries the identifiers, the hashes and the denominators, so a row taken
    out of context can still be traced back to the transcript it came from and the
    rule that produced it.
    """
    design_id = design.get("design_id", "")
    by_transcript = {a["transcript_id"]: a for a in assignments}

    assignment_rows = []
    for a in assignments:
        assignment_rows.append({
            "project_id": project_id, "design_id": design_id,
            "transcript_id": a["transcript_id"],
            "condition_id": a["condition_id"],
            "focus_group_id": a["focus_group_id"],
            "replicate_index": a.get("replicate_index"),
            "role": a["role"], "window_status": a.get("window_status"),
            "source_sha256": a.get("source_sha256"),
            "canonical_sha256": a.get("canonical_sha256"),
            "level2_freshness": freshness.get(a["transcript_id"], "MISSING"),
            "assigned_utc": a.get("assigned_utc"),
        })

    run_rows = []
    for transcript_id, rows in sorted(run_results.items()):
        assignment = by_transcript.get(transcript_id, {})
        record = transcript_index.get(transcript_id, {})
        for row in rows:
            run_rows.append({
                "project_id": project_id, "design_id": design_id,
                "transcript_id": transcript_id,
                "condition_id": assignment.get("condition_id"),
                "focus_group_id": assignment.get("focus_group_id"),
                "replicate_index": assignment.get("replicate_index"),
                "metric_id": row.get("metric_id"),
                "value": row.get("value"),
                "denominator": row.get("denominator"),
                "denominator_definition": row.get("denominator_definition"),
                "calculation_status": MEASURED,
                "coverage_status": freshness.get(transcript_id, "MISSING"),
                "source_sha256": record.get("source_sha256"),
                "canonical_sha256": record.get("canonical_sha256"),
                "aggregation_rule": "per-run measurement; not aggregated",
            })

    fg_rows = []
    for cell in aggregation.get("route_a", []):
        stat = cell["stat"]
        fg_rows.append({
            "project_id": project_id, "design_id": design_id,
            "unit": "focus_group_x_condition",
            "condition_id": cell["condition_id"],
            "focus_group_id": cell["focus_group_id"],
            "replicate_index": "",
            "metric_id": cell["metric_id"], "value": stat["mean"],
            "median": stat["median"], "sd": stat["sd"],
            "minimum": stat["minimum"], "maximum": stat["maximum"],
            "range": stat["range"], "human_reference": cell["human_reference"],
            "n_valid": stat["n_valid"], "n_expected": stat["n_expected"],
            "calculation_status": DERIVED,
            "coverage_status": cell["coverage_status"],
            "transcript_ids": _join(cell["transcript_ids"]),
            "aggregation_rule": cell["aggregation_rule_description"],
        })

    replicate_rows = []
    for rep in aggregation.get("route_b", []):
        stat = rep["stat"]
        replicate_rows.append({
            "project_id": project_id, "design_id": design_id,
            "unit": "study_replicate",
            "condition_id": rep["condition_id"], "focus_group_id": "",
            "replicate_index": rep["replicate_index"],
            "metric_id": rep["metric_id"], "value": stat["mean"],
            "sd": stat["sd"], "minimum": stat["minimum"],
            "maximum": stat["maximum"], "range": stat["range"],
            "n_valid": stat["n_valid"], "n_expected": stat["n_expected"],
            "calculation_status": DERIVED,
            "coverage_status": rep["coverage_status"],
            "focus_groups_included": _join(rep["focus_groups_included"]),
            "aggregation_rule": rep["aggregation_rule_description"],
        })

    provenance = {
        "project_id": project_id,
        "design_id": design_id,
        "application_version": APPLICATION_VERSION,
        "aggregation_version": AGGREGATION_VERSION,
        "code_content_hash": code_content_hash(),
        "design": design,
        "coverage_status": coverage.get("status"),
        "route_b_available": aggregation.get("route_b_available"),
        "route_b_reason": aggregation.get("route_b_reason"),
        "excluded_stale": aggregation.get("excluded_stale", []),
        "transcripts": {t: {"source_sha256": r.get("source_sha256"),
                            "canonical_sha256": r.get("canonical_sha256"),
                            "transcript_type": r.get("transcript_type"),
                            "declared_at_upload_not_a_reviewed_window":
                            r.get("window_declaration"),
                            "level2_freshness": freshness.get(t, "MISSING")}
                        for t, r in sorted(transcript_index.items())},
        "audit_log": audit_summary,
        "inference": "none performed; all figures are descriptive",
        "frozen_benchmark_used": False,
        "frozen_benchmark_note": ("no frozen human referent was used; every figure "
                                  "comes from the transcripts in this project"),
        "imputation": "none; a missing transcript reduces n and is listed",
    }

    return [
        ExportFile("study_design.json", JSON_MEDIA, _json(design)),
        ExportFile("transcript_assignments.csv", CSV_MEDIA,
                   _csv_from_rows(assignment_rows, ASSIGNMENT_COLUMNS)),
        ExportFile("coverage_report.json", JSON_MEDIA, _json(coverage)),
        ExportFile("level2_run_results.csv", CSV_MEDIA,
                   _csv_from_rows(run_rows, RUN_COLUMNS)),
        ExportFile("level2_fg_summary.csv", CSV_MEDIA,
                   _csv_from_rows(fg_rows, FG_COLUMNS)),
        ExportFile("level2_study_replicates.csv", CSV_MEDIA,
                   _csv_from_rows(replicate_rows, REPLICATE_COLUMNS)),
        ExportFile("provenance.json", JSON_MEDIA,
                   _json(envelope(provenance, generated_utc=generated_utc,
                                  kind="study_package"))),
    ]


# ---------------------------------------------------------- benchmark exports
BENCHMARK_CSV_COLUMNS = ("metric_id", "metric", "condition", "condition_label",
                         "unit", "unit_value", "value", "value_display", "n_valid",
                         "n_expected", "calculation_status",
                         "calculation_status_label", "coding_basis")


def benchmark_export(*, table_name: str, rows: list[dict], generated_utc: str,
                     columns=None) -> list[ExportFile]:
    """
    Export a benchmark table AS DISPLAYED, plus the hashes behind it.

    The protected sources themselves are neither copied nor modified; what travels is
    the table, the source inventory and each row's calculation status.
    """
    inventory = [{"key": s["key"], "path": s["path"], "sha256": s["sha256"],
                  "producer": s["producer"], "coding_basis": s["coding_basis"],
                  "expected_rows": s["expected_rows"]}
                 for s in TH.source_inventory()]

    payload = {
        "table": table_name,
        "rows": rows,
        "source_inventory": inventory,
        "calculation_status_by_row": [
            {"metric_id": r.get("metric_id"), "condition": r.get("condition"),
             "unit_value": r.get("unit_value"),
             "calculation_status": r.get("calculation_status")} for r in rows],
        "sources_are_read_only": True,
        "note": ("values as displayed; the protected artefacts are referenced by "
                 "hash and are neither copied nor modified by this export"),
    }
    safe_name = table_name.replace(" ", "_").lower()
    return [
        ExportFile(f"{safe_name}.json", JSON_MEDIA,
                   _json(envelope(payload, generated_utc=generated_utc,
                                  kind="benchmark_table"))),
        ExportFile(f"{safe_name}.csv", CSV_MEDIA,
                   _csv_from_rows(rows, columns or BENCHMARK_CSV_COLUMNS)),
    ]
