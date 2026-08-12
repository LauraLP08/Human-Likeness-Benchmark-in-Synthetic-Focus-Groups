"""
Entry point.

    py -m streamlit run apps/focus_group_platform/app/streamlit_app.py

Internal navigation rather than Streamlit's `pages/` directory, so the three views
share ONE state dictionary. With multipage files each page re-derives what it needs
on every switch, and the first thing that drifts is which project is open.

This module owns navigation and state. It computes nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st                                             # noqa: E402

from app.views import (frozen_benchmark, generate, home,           # noqa: E402
                       new_evaluation)

HOME = "Home / Projects"
BENCHMARK = "Frozen benchmark"
NEW_EVALUATION = "New evaluation"
GENERATE = "Generate focus groups"
VIEWS = {HOME: home, BENCHMARK: frozen_benchmark,
         NEW_EVALUATION: new_evaluation, GENERATE: generate}

# ONE key holds the current view. The sidebar radio reads and writes it directly, and
# a button that navigates writes the same key through `state["goto"]`. An earlier
# version kept `state["view"]` beside an unkeyed radio: the radio remembered its own
# selection, so once the sidebar had been touched the "Open frozen benchmark" button
# silently did nothing. Two copies of one fact is the bug, not the symptom.
NAV_KEY = "nav"
NAV_REQUEST_KEY = "nav_request"


def _request_view(name: str) -> None:
    """
    A button asks for a view; it does not set one.

    Streamlit refuses a write to a widget key after that widget has been created, and
    the navigation buttons live below the sidebar radio. So a button records a
    REQUEST, and the request is applied at the top of the next run - before the radio
    exists. Same single source of truth, one frame later.
    """
    st.session_state[NAV_REQUEST_KEY] = name


def main() -> None:
    st.set_page_config(page_title="Synthetic focus group platform",
                       page_icon="◧", layout="wide")

    if "app_state" not in st.session_state:
        st.session_state["app_state"] = {"project_id": None}
    if NAV_KEY not in st.session_state:
        st.session_state[NAV_KEY] = HOME
    requested = st.session_state.pop(NAV_REQUEST_KEY, None)
    if requested in VIEWS:
        st.session_state[NAV_KEY] = requested

    state = st.session_state["app_state"]
    state["goto"] = _request_view

    # Read before the sidebar renders: the sidebar's own caption depends on which
    # screen the researcher is looking at.
    view = st.session_state[NAV_KEY]

    with st.sidebar:
        st.markdown("### Focus group platform")
        st.radio("Go to", list(VIEWS), key=NAV_KEY)
        st.divider()
        if state.get("project_id"):
            st.caption(f"Open project: **{state['project_id']}**")
        # THE CAPTION MUST MATCH THE SCREEN. This said "Offline. No model is called
        # and no external request is made in this phase." on EVERY view — including
        # the one whose Start queue button spends real money. It was written when the
        # application genuinely could not call a model, and it survived into the phase
        # where it is false. A tool that asserts "offline" while billing forfeits
        # every other careful label on it.
        if view == GENERATE:
            st.caption("**This screen spends money.** Starting the queue runs real "
                       "sessions against a paid provider. Nothing launches until you "
                       "type the plan id and press Start.")
        else:
            st.caption("Read-only. This screen calls no model and makes no external "
                       "request; it only reads what is already on disk.")

    state["view"] = view                       # read-only mirror, for the views
    VIEWS[view].render(state)


if __name__ == "__main__":
    main()
