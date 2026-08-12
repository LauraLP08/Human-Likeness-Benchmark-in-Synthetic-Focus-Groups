"""Frozen benchmark: Level 1 and Level 2, read-only."""
from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from platform_core.services import benchmark_service as B
from platform_core.services import export_service

from .. import ui

VIEW_LABELS = {B.FOCUS_GROUP_VIEW: "Focus group comparison",
               B.STUDY_REPLICATE_VIEW: "Study replicate comparison"}

LEVEL1_COLUMNS = [("metric", "Metric"), ("condition_label", "Condition"),
                  ("unit_value", "Unit"), ("value_display", "Value"),
                  ("n_valid", "n"), ("n_expected", "of"),
                  ("calculation_status_label", "Status"),
                  ("coding_basis_label", "Coding basis")]

LEVEL2_COLUMNS = [("metric", "Metric"), ("condition_label", "Condition"),
                  ("unit_value", "Unit"), ("value_display", "Value"),
                  ("n_valid", "n"), ("n_expected", "of"),
                  ("calculation_status_label", "Status")]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _view_picker(key: str) -> str:
    label = st.radio("View", list(VIEW_LABELS.values()), horizontal=True, key=key)
    return next(v for v, name in VIEW_LABELS.items() if name == label)


def render(state) -> None:
    st.title("Frozen benchmark — Macho Meals")

    integrity = B.check_sources()
    if not integrity["ok"]:
        st.error("**Benchmark source changed**\n\n"
                 "A protected artefact no longer matches its pinned state, so no "
                 "figure on this page can be trusted.\n\n"
                 + "\n".join(f"- {p}" for p in integrity["problems"][:10])
                 + "\n\n*What to do:* restore the artefact, or update the pinned "
                   "hash deliberately if the change was intended.")
        return

    overview = B.benchmark_overview()
    columns = st.columns(4)
    columns[0].metric("Focus groups", overview["n_focus_groups"])
    columns[1].metric("Study replicates", overview["n_study_replicates"])
    columns[2].metric("Synthetic runs", overview["n_synthetic_runs"])
    columns[3].metric("Protected sources", integrity["n_level1_sources"])
    ui.palette_legend()
    st.caption("Read-only: transcripts cannot be replaced and results cannot be "
               "overwritten from this application.")

    level1, level2, sensitivity = st.tabs(
        ["Level 1 — Thematic fidelity", "Level 2 — Interaction process",
         "Sensitivity (separate view)"])

    with level1:
        _level1(state)
    with level2:
        _level2(state)
    with sensitivity:
        _sensitivity(state)


# ------------------------------------------------------------------- Level 1
def _level1(state) -> None:
    st.caption("Primary coding. The adjudicated sensitivity re-coding is in its own "
               "tab and never replaces these values.")
    view = _view_picker("l1_view")
    details = ui.details_toggle("l1_details")

    st.subheader("Recall, precision, F1, reach")
    rows = B.level1_rows(view)
    ui.table(rows, LEVEL1_COLUMNS, height=320)

    summary = B.level1_condition_summary(view)
    st.markdown("**Mean across cells, by condition**")
    ui.table(summary, [("metric", "Metric"), ("condition_label", "Condition"),
                       ("value_display", "Mean"), ("n_valid", "n"),
                       ("n_expected", "of"),
                       ("calculation_status_label", "Status")])

    st.subheader("Agreement in thematic ordering")
    ordering = B.level1_ordering_rows(view)
    ui.table(ordering, LEVEL1_COLUMNS[:-1], height=260)
    st.caption("Exploratory. A cell with no defined value is shown as Undefined, "
               "never as zero agreement.")

    st.subheader("Inductive theme accumulation")
    accumulation = B.level1_accumulation()
    ui.condition_chart(accumulation["positions"], accumulation["series"],
                       kind="line", y_label="Focus groups seen", percent=False)
    ui.status_caption(accumulation["unit"],
                      accumulation["calculation_status_label"])
    st.caption(accumulation["caveat"])

    st.subheader("Thematic recurrence across groups")
    recurrence = B.level1_recurrence_rows()
    ui.table(recurrence, [("subtheme_id", "Subtheme"),
                          ("condition_label", "Condition"),
                          ("replicate_index", "Replicate"),
                          ("n_focus_groups", "Focus groups"),
                          ("value_display", "Share")], height=260)
    st.caption("Counted across focus groups, not across participants.")

    guide = B.guide_coverage_notice()
    st.info(f"**Guide coverage** — {guide['display']}")

    if details:
        _level1_details(rows, ordering, guide)

    st.divider()
    files = export_service.benchmark_export(
        table_name=f"level1_{view}", rows=rows, generated_utc=_now())
    ui.download_files(files, key_prefix="l1")


def _level1_details(rows, ordering, guide) -> None:
    with st.expander("Methodological details", expanded=True):
        st.markdown("**Metric definitions**")
        seen = set()
        for row in rows:
            if row["metric_id"] in seen:
                continue
            seen.add(row["metric_id"])
            st.markdown(f"**{row['metric']}**")
            ui.detail_rows({k: row["details"].get(k) for k in
                            ("statistic", "numerator", "denominator", "estimand",
                             "aggregation_rule", "human_reference_note",
                             "source_artifact", "source_hash")})
        if ordering:
            st.markdown("**Agreement in thematic ordering**")
            ui.detail_rows(ordering[0]["details"])
        st.markdown("**Guide coverage**")
        st.markdown(f"- {guide['reason']}")
        for item in guide["explicitly_not_done"]:
            st.markdown(f"- {item}")
        st.markdown("**Known disagreements between frozen artefacts**")
        for item in B.KNOWN_ARTEFACT_DISCREPANCIES:
            st.markdown(f"- *{item['summary']}* — {item['detail']} "
                        f"{item['resolution']}")


# ------------------------------------------------------------------- Level 2
def _level2(state) -> None:
    view = _view_picker("l2_view")
    details = ui.details_toggle("l2_details")

    st.subheader("Structural table")
    summary = B.level2_condition_summary()
    ui.table(summary, [("metric", "Metric"), ("human_display", "Human"),
                       ("enriched_display", "Enriched"),
                       ("demographics-only_display", "Demographics-only"),
                       ("n_fg_enriched_closer_to_human", "Enriched closer"),
                       ("n_fgs", "Focus groups"),
                       ("calculation_status_label", "Status")])

    st.markdown(f"**{VIEW_LABELS[view]}**")
    rows = B.level2_rows(view)
    ui.table(rows, LEVEL2_COLUMNS, height=380)

    st.subheader("Words per turn")
    distribution = B.level2_words_per_turn()
    ui.condition_chart(distribution["bins"], distribution["series"], kind="bar",
                       y_label="Words per turn")
    ui.status_caption(distribution["unit"],
                      distribution["calculation_status_label"],
                      distribution["bins_are_fixed"])

    if details:
        with st.expander("Methodological details", expanded=True):
            st.markdown("**Words per turn**")
            ui.detail_rows({
                "aggregation rule": distribution["aggregation_rule"],
                "source artefact": distribution["source_artifact"],
                "within run": distribution["denominators"]["within_run"],
                "within focus group":
                    distribution["denominators"]["within_focus_group"],
                "across focus groups":
                    distribution["denominators"]["across_focus_groups"],
            })
            st.markdown("**Structural table**")
            ui.detail_rows(summary[0]["details"])
            st.caption(
                "Reproduced from frozen benchmark = recomputed here and checked "
                "against the frozen table. Derived from frozen coded data = a new "
                "summary over frozen rows, with no frozen counterpart to check "
                "against.")
            st.markdown("**Other distributions**")
            st.caption("Participant turn counts, participant word counts and chain "
                       "depth are available through the services and the export, "
                       "and are not charted in this phase.")

    st.divider()
    files = export_service.benchmark_export(
        table_name=f"level2_{view}", rows=rows, generated_utc=_now())
    ui.download_files(files, key_prefix="l2")


# --------------------------------------------------------------- sensitivity
def _sensitivity(state) -> None:
    st.warning("This is the adjudicated **sensitivity re-coding**. It is a parallel "
               "view. The primary coding on the Level 1 tab is the result and is "
               "not modified by anything on this tab.")
    treatment = st.selectbox(
        "Treatment", ["CONTESTED_AS_PRESENT", "CROSS_MODEL", "COMBINED"])
    rows = B.level1_sensitivity_rows(treatment)
    changed = [r for r in rows if r["changed"]]
    columns = st.columns(3)
    columns[0].metric("Cells", len(rows))
    columns[1].metric("Changed under this treatment", len(changed))
    columns[2].metric("Primary modified", "No")

    ui.table(rows, [("subtheme_id", "Subtheme"), ("condition_label", "Condition"),
                    ("replicate_index", "Replicate"),
                    ("primary_display", "Primary"),
                    ("sensitivity_display", "Sensitivity"),
                    ("delta", "Delta")], height=380)

    ordering = B.level1_ordering_sensitivity()
    st.markdown("**Agreement in thematic ordering, under sensitivity treatments**")
    ui.detail_rows({
        "primary treatment": ordering["primary_treatment"],
        "primary is unmodified": ordering["primary_is_unmodified"],
        "runs defined by treatment": ordering["n_defined_by_treatment"],
        "contested cells applied": ordering["n_contested_cells_applied"],
        "note": ordering["note"],
    })
