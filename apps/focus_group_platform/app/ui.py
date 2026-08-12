"""
Small rendering helpers shared by the three views.

The rule for this whole package: it turns service output into widgets. It computes
nothing, reads no artefact, and decides no methodology. If a helper here ever needs
to know what a metric means, that knowledge belongs in a service instead.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from platform_core import theme

# One line per problem code, so the same fault reads the same way everywhere.
PROBLEM_TITLES = {
    "invalid_file": "File could not be read",
    "unsupported_schema": "Unsupported transcript schema",
    "unresolved_participant_identity": "Participant identity unresolved",
    "missing_roster": "Participant roster required",
    "incomplete_comparable_window": "Comparable window not established",
    "metric_undefined": "Some metrics are undefined",
    "methodological_comparison_unavailable": "Comparison not available",
    "protected_benchmark_source_changed": "Benchmark source changed",
}


def problem_block(problems) -> None:
    """Actionable messages. Never a traceback, never a bare exception string."""
    for problem in problems:
        title = PROBLEM_TITLES.get(problem.code, problem.code)
        body = f"**{title}**\n\n{problem.message}\n\n*What to do:* {problem.remedy}"
        (st.error if problem.blocking else st.warning)(body)


def frame(rows, columns) -> pd.DataFrame:
    """A display frame with the given columns, in the given order."""
    if not rows:
        return pd.DataFrame(columns=[label for _, label in columns])
    data = {label: [r.get(key) for r in rows] for key, label in columns}
    return pd.DataFrame(data)


def table(rows, columns, *, height: int | None = None) -> None:
    # `height=None` is rejected by Streamlit; omit the argument instead of passing it.
    extra = {"height": height} if height else {}
    st.dataframe(frame(rows, columns), width="stretch", hide_index=True, **extra)


def _long_frame(bins, series):
    ordered = [c for c in theme.CONDITION_ORDER if c in series]
    records = [{"bin": str(b), "condition": theme.condition_label(c),
                "value": series[c][i]}
               for c in ordered for i, b in enumerate(bins)]
    return pd.DataFrame(records), ordered


def _colour_scale(ordered):
    return alt.Scale(domain=[theme.condition_label(c) for c in ordered],
                     range=[theme.condition_colour(c) for c in ordered])


def condition_chart(bins, series, *, kind: str = "bar", y_label: str = "",
                    percent: bool = True) -> None:
    """
    A chart whose colours come from the shared palette, never from a local literal.

    The x order is PINNED to the order the service returned. Streamlit's built-in
    charts sort a categorical axis alphabetically, which put `100-199w` between
    `10-24w` and `200-249w` - a words-per-turn axis that reads as if the corpus were
    bimodal when it is not. Altair with an explicit `sort` is the fix.

    Series are ordered human, enriched, demographics-only so the legend never changes
    order between charts.
    """
    data, ordered = _long_frame(bins, series)
    order = [str(b) for b in bins]
    axis = alt.Axis(format="%") if percent else alt.Axis()
    encoding = {
        "x": alt.X("bin:N", sort=order, title=y_label or None,
                   axis=alt.Axis(labelAngle=0)),
        "y": alt.Y("value:Q", title=None, axis=axis),
        "color": alt.Color("condition:N", scale=_colour_scale(ordered),
                           title="Condition",
                           sort=[theme.condition_label(c) for c in ordered]),
    }
    base = alt.Chart(data)
    if kind == "bar":
        chart = base.mark_bar().encode(
            xOffset=alt.XOffset("condition:N",
                                sort=[theme.condition_label(c) for c in ordered]),
            **encoding)
    else:
        chart = base.mark_line(point=True).encode(**encoding)
    st.altair_chart(chart.properties(height=320), width="stretch")


def details_toggle(key: str, label: str = "Show methodological details") -> bool:
    return st.toggle(label, key=key, value=False)


def detail_rows(details: dict) -> None:
    """Render a details mapping without letting a long note break the layout."""
    for name, value in details.items():
        if value is None or value == "" or value == []:
            continue
        st.markdown(f"- **{name.replace('_', ' ')}**: {value}")


def status_caption(*parts: str) -> None:
    st.caption(" · ".join(p for p in parts if p))


def download_files(files, *, key_prefix: str) -> None:
    columns = st.columns(min(len(files), 3))
    for index, export in enumerate(files):
        with columns[index % len(columns)]:
            st.download_button(export.filename, data=export.data,
                               file_name=export.filename,
                               mime=export.media_type,
                               key=f"{key_prefix}_{export.filename}",
                               width="stretch")


def palette_legend() -> None:
    chips = " ".join(
        f"<span style='display:inline-block;width:10px;height:10px;"
        f"background:{theme.condition_colour(c)};margin-right:4px;"
        f"border-radius:2px'></span>{theme.condition_label(c)}"
        for c in theme.CONDITION_ORDER)
    st.markdown(f"<div style='font-size:0.85em;color:#64748b'>{chips}</div>",
                unsafe_allow_html=True)
