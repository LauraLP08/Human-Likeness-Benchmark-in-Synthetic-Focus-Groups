"""Home / Projects."""
from __future__ import annotations

import streamlit as st

from platform_core.config import DataDirError, resolve_data_dir
from platform_core.paths import PathValidationError
from platform_core.projects import ProjectError
from platform_core.services import import_service
from platform_core.services.context import ComparabilityStatus

from .. import ui

FROZEN_BENCHMARK = "Frozen benchmark"
NEW_EVALUATION = "New evaluation"


def _data_dir():
    try:
        return resolve_data_dir(), None
    except DataDirError as exc:
        return None, str(exc)


def render(state) -> None:
    st.title("Synthetic focus group platform")
    st.caption("Analysis is read-only. Generation is the one thing here that calls a "
               "model and spends money, it lives behind its own screen, and it never "
               "starts because a page was opened.")

    left, right = st.columns(2)
    with left:
        st.subheader("Frozen benchmark")
        st.markdown(
            "The **Macho Meals** study from the thesis. Human, enriched and "
            "demographics-only conditions with their frozen results.\n\n"
            "- Level 1 (thematic) and Level 2 (structural) available\n"
            "- protected artefacts, read-only\n"
            "- transcripts cannot be replaced and results cannot be overwritten")
        if st.button("Open frozen benchmark", type="primary", width="stretch"):
            state["goto"](FROZEN_BENCHMARK)
            st.rerun()

    with right:
        st.subheader("New project")
        st.markdown(
            "Your own corpus. **Nothing is assumed to be comparable with Macho "
            "Meals.**\n\n"
            "- Level 2 structural available once the inputs are sufficient\n"
            "- Level 1 unavailable until there is a codebook and a thematic "
            "procedure for your study\n"
            "- a synthetic transcript on its own gets descriptive results only\n"
            "- a human/synthetic comparison requires you to declare and document "
            "the correspondence")

    st.divider()
    data_dir, error = _data_dir()
    if error:
        st.error(f"**Data directory unavailable**\n\n{error}")
        return

    st.subheader("Projects")
    st.caption(f"Stored in `{data_dir.path}` — outside the repository.")

    projects = import_service.all_projects(data_dir)
    if projects:
        ui.table(projects, [("name", "Project"), ("project_id", "Id"),
                            ("n_transcripts", "Transcripts"),
                            ("updated_at", "Last modified"),
                            ("description", "Description")])
        names = [p["project_id"] for p in projects]
        chosen = st.selectbox("Open a project", names,
                              index=names.index(state["project_id"])
                              if state.get("project_id") in names else 0)
        if st.button("Open project", width="stretch"):
            state["project_id"] = chosen
            state["goto"](NEW_EVALUATION)
            st.rerun()
    else:
        st.info("No projects yet. Create one below.")

    with st.form("create_project"):
        st.markdown("**Create a project**")
        name = st.text_input("Name", placeholder="My study")
        description = st.text_input("Description (optional)")
        submitted = st.form_submit_button("Create project")
    if submitted:
        if not name.strip():
            st.warning("A project needs a name.")
        else:
            try:
                project = import_service.new_project(
                    name.strip(), resolve_data_dir(ensure=True),
                    description=description.strip())
            except (ProjectError, PathValidationError, DataDirError) as exc:
                st.error(f"**Project not created**\n\n{exc}")
            else:
                state["project_id"] = project.project_id
                state["goto"](NEW_EVALUATION)
                st.rerun()

    st.divider()
    st.caption(
        "Generation of focus groups, thematic evaluation of new corpora and agent "
        "fidelity are not part of this phase. "
        f"Uploaded corpora start at `{ComparabilityStatus.REQUIRES_REVIEW.value}` "
        "and never inherit the frozen human referent.")
