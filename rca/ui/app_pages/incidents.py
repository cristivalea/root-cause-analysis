"""Incidents in no problem, each with a grouping suggestion and the reasons behind it.

The system only proposes (rca/suggestions.py); the Problem Manager decides: add the incident to the
suggested problem, create a new problem (from the suggestion or from any incidents selected),
reject the suggestion, or mark the incident as needing no problem.
"""

import pandas as pd
import streamlit as st

from rca.ui import navigation, services, theme
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

FLASH_KEY = "incidents_flash"
SUGGESTIONS_KEY = "incidents_suggestions"  # computed once per change: the API needs a few seconds


def flash(warnings: list[str] | None = None, error: str | None = None) -> None:
    st.session_state[FLASH_KEY] = {"warnings": warnings or [], "error": error}


def show_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if not message:
        return
    if message["error"]:
        st.error(message["error"], icon=theme.ICONS["error"])
    for warning in message["warnings"]:
        st.warning(warning, icon=":material/warning:")


def changed() -> None:
    """After any change the suggestions are computed again."""
    st.session_state.pop(SUGGESTIONS_KEY, None)
    st.rerun()


def load_suggestions() -> dict | None:
    if SUGGESTIONS_KEY not in st.session_state:
        try:
            st.session_state[SUGGESTIONS_KEY] = services.suggestions()
        except services.ServiceError:
            st.session_state[SUGGESTIONS_KEY] = None
    return st.session_state[SUGGESTIONS_KEY]


def label(suggestion: dict | None) -> str:
    if not suggestion:
        return t("suggestion.none")
    if suggestion["kind"] == "new_problem":
        return t("suggestion.new_problem", count=len(suggestion["incident_ids"]))
    return t(f"suggestion.{suggestion['kind']}", problem=suggestion["problem_id"])


def open_created(problem_id: str) -> None:
    st.query_params.clear()
    st.query_params["problem"] = problem_id
    st.switch_page(navigation.PROBLEMS)


def create(incident_ids: list[str], title: str | None = None) -> None:
    try:
        problem, warnings = services.create_problem(incident_ids, title or None)
    except services.ServiceError as error:
        flash(error=services.user_message(error))
        changed()
    flash(warnings=warnings)
    st.session_state.pop(SUGGESTIONS_KEY, None)
    open_created(problem.problem_id)


def suggestion_card(incident, suggestion: dict | None, unassigned_ids: set[str]) -> None:
    with st.container(border=True):
        st.markdown(f"**{t('incidents.suggestion_title', incident=incident.incident_id)}**")
        st.caption(f"{incident.service} · {incident.severity} · {incident.title}")
        if not suggestion:
            st.caption(t("incidents.no_suggestion"))
        else:
            st.markdown(label(suggestion))
            with st.expander(t("incidents.why"), icon=":material/info:"):
                for reason in suggestion["reasons"]:
                    st.markdown(f"- {reason}")
            kind, problem_id = suggestion["kind"], suggestion["problem_id"]
            if kind == "open_problem":
                if st.button(t("incidents.accept_open", problem=problem_id), type="primary", key="accept_open"):
                    try:
                        _, warnings = services.attach_incident(problem_id, incident.incident_id)
                        flash(warnings=warnings)
                    except services.ServiceError as error:
                        flash(error=services.user_message(error))
                    changed()
            elif kind == "closed_problem":
                reason = st.text_input(t("incidents.reopen_reason", problem=problem_id), key="reopen_reason")
                if st.button(t("incidents.accept_closed_reopen", problem=problem_id), type="primary", key="accept_closed"):
                    if not reason.strip():
                        st.error(t("problems.reason_required"), icon=theme.ICONS["error"])
                    else:
                        try:
                            services.reopen_problem(problem_id, reason.strip())
                            _, warnings = services.attach_incident(problem_id, incident.incident_id)
                            flash(warnings=warnings)
                        except services.ServiceError as error:
                            flash(error=services.user_message(error))
                        changed()
            # a new problem is always possible: with the alike incidents still in no problem
            partners = [item for item in suggestion["incident_ids"] if item in unassigned_ids]
            if kind == "new_problem" or partners:
                if st.button(t("incidents.accept_new"), key="accept_new"):
                    create([incident.incident_id, *partners])
            if st.button(t("incidents.reject"), type="tertiary", key="reject"):
                targets = [problem_id] if problem_id else suggestion["incident_ids"]
                try:
                    services.reject_suggestion(incident.incident_id, targets)
                except services.ServiceError as error:
                    flash(error=services.user_message(error))
                changed()

        with st.expander(t("incidents.dismiss_title"), icon=":material/block:"):
            reason = st.text_input(t("incidents.dismiss_reason"), key="dismiss_reason")
            if st.button(t("incidents.dismiss_action"), key="dismiss"):
                if not reason.strip():
                    st.error(t("problems.reason_required"), icon=theme.ICONS["error"])
                else:
                    try:
                        services.dismiss_incident(incident.incident_id, reason.strip())
                    except services.ServiceError as error:
                        flash(error=services.user_message(error))
                    changed()


page_header(t("incidents.title"), t("incidents.subtitle"))
show_flash()

try:
    incidents = services.unassigned_incidents()
except services.ServiceError as error:
    st.error(t("state.error_data"), icon=theme.ICONS["error"])
    st.caption(t("state.error_detail", detail=error))
    st.stop()
if not incidents:
    st.info(t("incidents.none"), icon=":material/inbox:")
    st.stop()

found = load_suggestions()
if found is None:
    st.warning(t("incidents.suggestions_missing"), icon=":material/warning:")
    found = {}

frame = pd.DataFrame({
    "incident": [item.incident_id for item in incidents],
    "description": [item.title for item in incidents],
    "service": [item.service for item in incidents],
    "severity": [item.severity for item in incidents],
    "detected": [item.detected_at for item in incidents],
    "suggestion": [label(found.get(item.incident_id)) for item in incidents],
})
st.caption(t("incidents.select_hint"))
event = st.dataframe(
    frame, hide_index=True, on_select="rerun", selection_mode="multi-row", key="incidents_table",
    column_config={
        "incident": st.column_config.TextColumn(t("table.incident"), width=140, pinned=True),
        "description": st.column_config.TextColumn(t("table.description"), width="large"),
        "service": st.column_config.TextColumn(t("table.service"), width=130),
        "severity": st.column_config.TextColumn(t("table.severity"), width=80),
        "detected": st.column_config.DatetimeColumn(t("table.date"), format="D MMM YYYY, HH:mm", width=150),
        "suggestion": st.column_config.TextColumn(t("incidents.col.suggestion"), width="medium"),
    },
)

chosen = [incidents[row] for row in event.selection.rows]
if chosen:
    st.caption(t("incidents.selected", count=len(chosen)))
    if len(chosen) == 1:
        suggestion_card(chosen[0], found.get(chosen[0].incident_id), {item.incident_id for item in incidents})
    with st.container(border=True):
        st.markdown(f"**{t('incidents.create_title')}**")
        title = st.text_input(t("incidents.create_name"), key="create_title")
        if st.button(t("incidents.create_action"), type="primary" if len(chosen) > 1 else "secondary", key="create"):
            create([item.incident_id for item in chosen], title.strip() or None)
