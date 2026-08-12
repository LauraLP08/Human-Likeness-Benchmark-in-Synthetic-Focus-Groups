"""
Comparable windows.

Propose a window, look at what it keeps and what it drops, lock it. All the rules live
in `window_service`; this file arranges widgets.
"""
from __future__ import annotations

import streamlit as st

from platform_core import analysis_window as AW
from platform_core.services import import_service, structural_service, window_service

from .. import ui

STATUS_HELP = {
    AW.WindowStatus.RAW_FULL_TRANSCRIPT.value:
        "No window yet. Results over this transcript are descriptive only.",
    AW.WindowStatus.PROPOSED.value:
        "Boundaries set and unambiguous. Lock it to make it comparable.",
    AW.WindowStatus.UNDER_REVIEW.value:
        "A boundary could not be resolved. Fix it, or record a positional decision.",
    AW.WindowStatus.LOCKED.value:
        "Immutable and comparable. To change it, create a new version.",
    AW.WindowStatus.REJECTED.value: "Set aside. Not used by anything.",
    AW.WindowStatus.SUPERSEDED.value:
        "Replaced by a later version. Kept so its results still mean something.",
}

PAGE_SIZE = 25


def render(state, project) -> None:
    stored = import_service.stored_transcripts(project)
    if not stored:
        st.info("Import a transcript first.")
        return

    results = structural_service.restore_results(project)
    by_input = {r.analysis_input_id: r for r in results.values()}

    st.caption("Both sides need a window. A human transcript is not assumed "
               "comparable just for being human, and a declaration made at import is "
               "not a reviewed decision.")

    rows = []
    for record in stored:
        s = window_service.window_state(project, record["transcript_id"])
        result = by_input.get(s.analysis_input_id)
        rows.append({
            "transcript_id": record["transcript_id"],
            "side": s.side,
            "source_turns": record["n_turns"],
            "active_window": s.window.window_id if s.window else "—",
            "status": s.window_status,
            "retained_turns": s.window.n_retained_turns if s.window else "—",
            "source_hash": (record["canonical_sha256"] or "")[:12] + "…",
            "window_hash": ((s.window.window_artifact_sha256 or "")[:12] + "…"
                            if s.window else "—"),
            "level2": (result.freshness if result else "not computed"),
            "eligible": "yes" if s.comparison_eligible else "no",
        })
    ui.table(rows, [("transcript_id", "Transcript"), ("side", "Side"),
                    ("source_turns", "Source turns"),
                    ("active_window", "Active window"), ("status", "Status"),
                    ("retained_turns", "Retained"), ("source_hash", "Source hash"),
                    ("window_hash", "Window hash"), ("level2", "Level 2"),
                    ("eligible", "Comparable")])

    st.divider()
    ids = [r["transcript_id"] for r in stored]
    chosen = st.selectbox("Transcript", ids, key="window_transcript")
    state_now = window_service.window_state(project, chosen)
    st.caption(STATUS_HELP.get(state_now.window_status, ""))
    if state_now.versions:
        st.caption(f"Versions: {', '.join(state_now.versions)}")

    _create(project, chosen, state_now)
    if state_now.window is not None:
        _review(project, state_now)


def _create(project, transcript_id, state_now) -> None:
    payload = import_service.load_canonical(project, transcript_id)
    turns = payload["turns"]
    superseding = state_now.window.window_id if (
        state_now.window and state_now.window.locked) else None

    if superseding:
        st.info(f"**{superseding}** is locked. Anything you create here becomes a "
                f"new version and supersedes it once locked; the previous window is "
                f"kept.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Confirm the entire transcript**")
        st.caption("Use this when the file already contains only the comparable "
                   "segment. It records boundaries, a hash and your name — which a "
                   "declaration at upload never did.")
        label = st.text_input("Your name or initials", key="confirm_label")
        note = st.text_input("Note", key="confirm_note",
                             placeholder="e.g. trimmed at source by the transcriber")
        if st.button("Confirm entire transcript as window",
                     disabled=not label.strip()):
            try:
                window_service.confirm_whole_transcript(
                    project, transcript_id, researcher_label=label.strip(),
                    researcher_note=note.strip(),
                    supersedes_window_id=superseding)
            except (AW.WindowError, window_service.WindowServiceError) as exc:
                st.error(f"**Window not created**\n\n{exc}")
            else:
                st.rerun()

    with right:
        st.markdown("**Create a manual window**")
        options = ["—"] + [f"{i}: {t['turn_id']} · "
                           f"{(t.get('canonical_speaker_id') or '?')} · "
                           f"{(t.get('text') or '')[:40]}"
                           for i, t in enumerate(turns)]
        start = st.selectbox("First retained turn", options, key="w_start")
        end = st.selectbox("Last retained turn", options,
                           index=len(options) - 1, key="w_end")
        offsets = st.checkbox("Trim inside the boundary turns", key="w_offsets")
        start_offset = end_offset = None
        if offsets:
            columns = st.columns(2)
            start_offset = columns[0].number_input("Start char offset", 0,
                                                   value=0, key="w_so")
            end_offset = columns[1].number_input("End char offset", 0,
                                                 value=0, key="w_eo")
        m_label = st.text_input("Your name or initials", key="manual_label")
        m_note = st.text_input("Note", key="manual_note")
        positional = st.checkbox(
            "Record this as a positional decision", key="w_positional",
            help="Only when the boundary cannot be located by text. Requires a name "
                 "and a note, and is written to the audit log.")

        if st.button("Propose window"):
            def turn_of(choice):
                if choice == "—":
                    return None
                return turns[int(choice.split(":")[0])]["turn_id"]
            try:
                window_service.propose_manual_window(
                    project, transcript_id,
                    start_turn_id=turn_of(start), end_turn_id=turn_of(end),
                    start_char_offset=int(start_offset) if offsets else None,
                    end_char_offset=int(end_offset) if offsets else None,
                    researcher_label=m_label.strip(),
                    researcher_note=m_note.strip(),
                    positional_fallback_used=positional,
                    supersedes_window_id=superseding)
            except (AW.WindowError, window_service.WindowServiceError) as exc:
                st.error(f"**Window not created**\n\n{exc}")
            else:
                st.rerun()


def _review(project, state_now) -> None:
    window = state_now.window
    st.divider()
    st.subheader(f"{window.window_id} — {window.status}")

    columns = st.columns(4)
    columns[0].metric("Source turns", window.n_source_turns)
    columns[1].metric("Retained", window.n_retained_turns)
    columns[2].metric("Dropped", window.n_source_turns - window.n_retained_turns)
    columns[3].metric("Comparable", "Yes" if state_now.comparison_eligible else "No")

    if window.review_problems:
        st.warning("**Under review**\n\n"
                   + "\n".join(f"- {p}" for p in window.review_problems))
    if window.positional_fallback_used:
        st.warning(f"Positional boundary, recorded by **{window.researcher_label}**: "
                   f"{window.researcher_note}")
    if not state_now.comparison_eligible:
        st.caption(state_now.reason)

    with st.expander("Preview", expanded=True):
        view = window_service.preview(project, window.window_id)
        st.caption(f"{view['n_retained']} retained turn(s); showing "
                   f"{view['n_shown']}. Context: {len(view['before'])} before, "
                   f"{len(view['after'])} after.")
        ui.table(view["before"] + view["retained"] + view["after"],
                 [("section", "Section"), ("position", "#"), ("turn_id", "Turn"),
                  ("speaker", "Speaker"), ("role", "Role"), ("text", "Text")],
                 height=360)
        if view["retained_truncated"]:
            st.caption("Long window: the retained turns are truncated in this "
                       "preview. The window itself keeps all of them.")

    actions = st.columns(3)
    if not window.locked:
        if actions[0].button("Lock window", type="primary"):
            try:
                window_service.lock_window(project, window.window_id)
            except window_service.WindowServiceError as exc:
                st.error(f"**Not locked**\n\n{exc}")
            else:
                st.rerun()
        if actions[1].button("Reject window"):
            window_service.reject_window(project, window.window_id)
            st.rerun()
    else:
        actions[0].caption("Locked windows are immutable. Create a new version "
                           "above to change the boundaries.")

    with st.expander("Window record"):
        ui.detail_rows({
            "derivation method": window.derivation_method,
            "start": window.start_boundary,
            "end": window.end_boundary,
            "unambiguous": window.unambiguous,
            "researcher": window.researcher_label,
            "note": window.researcher_note,
            "window artefact sha256": window.window_artifact_sha256,
            "source canonical sha256": window.source_canonical_sha256,
            "supersedes": window.supersedes_window_id,
            "superseded by": window.superseded_by_window_id,
            "locked utc": window.locked_utc,
        })
        st.caption("The artefact hash covers order, turn ids, speakers, roles, text "
                   "and the boundaries — not the concatenated content alone.")
