"""Problems: the list, the proposed ones, and one problem with its incidents, its RCAs and its history.

The Problem Manager starts the RCA from here. Every change goes through the API, which applies the
rules (rca/problems.py); a refused change shows its reason, and a warning is shown after a change
that is allowed but worth a second look.
"""

import pandas as pd
import streamlit as st

from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components.guidance_form import guidance_form
from rca.ui.components.page_header import page_header
from rca.ui.strings import t, t_or_value

FLASH_KEY = "problems_flash"  # what the last change said, shown once after the rerun


def open_problem(problem_id: str | None) -> None:
    if problem_id:
        st.query_params["problem"] = problem_id
    else:
        st.query_params.pop("problem", None)
    st.rerun()


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


def act(change, *args) -> bool:
    """Run a change through the API; keep its warnings or its refusal for the next run."""
    try:
        result = change(*args)
    except services.ServiceError as error:
        flash(error=services.user_message(error))
        return False
    flash(warnings=result[1] if isinstance(result, tuple) else [])
    return True


# --------------------------------------------------------------------------------------
# The list
# --------------------------------------------------------------------------------------


def problem_list() -> None:
    choice = st.segmented_control(t("problems.filter"), ["Open", "Closed", "all"], default="Open",
                                  format_func=lambda value: t(f"problems.filter.{value}"), key="problems_filter")
    try:
        found = services.list_problems(None if choice in (None, "all") else choice)
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return

    proposed_section()

    if not found:
        st.info(t("problems.none"), icon=":material/info:")
        return
    st.caption(t("problems.select_hint"))
    frame = pd.DataFrame({
        "problem": [item.problem_id for item in found],
        "title": [item.title for item in found],
        "priority": [item.priority for item in found],
        "incidents": [len(item.incidents) for item in found],
        "services": [", ".join(item.services) for item in found],
        "status": [t_or_value(f"problems.filter.{item.status}", item.status) for item in found],
        "created": [item.created_at for item in found],
    })
    event = st.dataframe(
        frame, hide_index=True, on_select="rerun", selection_mode="single-row", key="problems_table",
        column_config={
            "problem": st.column_config.TextColumn(t("problems.col.problem"), width=140, pinned=True),
            "title": st.column_config.TextColumn(t("problems.col.title"), width="large"),
            "priority": st.column_config.TextColumn(t("problems.col.priority"), width=70),
            "incidents": st.column_config.NumberColumn(t("problems.col.incidents"), width=80),
            "services": st.column_config.TextColumn(t("problems.col.services"), width=150),
            "status": st.column_config.TextColumn(t("problems.col.status"), width=80),
            "created": st.column_config.DatetimeColumn(t("problems.col.created"), format="D MMM YYYY", width=110),
        },
    )
    if event.selection.rows:
        open_problem(found[event.selection.rows[0]].problem_id)


def proposed_section() -> None:
    try:
        groups = services.proposed_problems()
    except services.ServiceError:
        return
    if not groups:
        return
    with st.expander(t("problems.proposed_title", count=len(groups)), icon=":material/lightbulb:"):
        st.caption(t("problems.proposed_hint"))
        for index, group in enumerate(groups):
            with st.container(border=True):
                st.markdown(", ".join(f"`{item}`" for item in group))
                if st.button(t("problems.proposed_create"), key=f"proposed_{index}", icon=":material/add:"):
                    try:
                        problem, warnings = services.create_problem(group)
                    except services.ServiceError as error:
                        flash(error=services.user_message(error))
                        st.rerun()
                    flash(warnings=warnings)
                    open_problem(problem.problem_id)


# --------------------------------------------------------------------------------------
# One problem
# --------------------------------------------------------------------------------------


def problem_detail(problem_id: str) -> None:
    if st.button(t("problems.back"), icon=theme.ICONS["back"], type="tertiary"):
        open_problem(None)
    try:
        data = services.get_problem(problem_id)
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return
    if data is None:
        st.info(t("problems.none"), icon=":material/info:")
        return
    problem, events, rcas = data["problem"], data["events"], data["rcas"]
    is_open = problem.status == "Open"

    st.subheader(f"{problem.problem_id} · {problem.title}")
    st.caption(f"{t('problems.status')}: {t_or_value(f'problems.filter.{problem.status}', problem.status)} · "
               f"{t('problems.priority')}: {problem.priority} · {t('problems.services')}: {', '.join(problem.services)}")
    st.caption(t("problems.opened_by", name=problem.created_by, date=formatting.date_time(problem.created_at)))
    if problem.rca_id:
        st.caption(t("problems.closed_by_rca", rca=problem.rca_id))
    elif problem.close_reason:
        st.caption(t("problems.closed_because", date=formatting.date_time(problem.closed_at), reason=problem.close_reason))
    st.markdown(problem.description)

    left, right = st.columns([3, 2], gap="large")
    with left:
        incidents_section(problem, is_open)
        rcas_section(rcas)
        history_section(events)
    with right:
        if is_open:
            start_section(problem)
            add_section(problem)
            remove_section(problem)
            close_section(problem)
        else:
            reopen_section(problem)


def incidents_section(problem, is_open: bool) -> None:
    st.markdown(f"**{t('problems.incidents_title', count=len(problem.incidents))}**")
    for link in problem.incidents:
        incident = services.get_incident(link.incident_id)
        with st.container(border=True):
            title = incident.title if incident else ""
            st.markdown(f"`{link.incident_id}` · {title}")
            if incident:
                st.caption(f"{incident.service} · {incident.severity} · {formatting.date_time(incident.detected_at)}")
            st.caption(t("problems.linked", name=link.linked_by, date=formatting.date_time(link.linked_at)))


def rcas_section(rcas) -> None:
    st.markdown(f"**{t('problems.rcas_title')}**")
    if not rcas:
        st.caption(t("problems.rcas_none"))
        return
    for record in sorted(rcas, key=lambda item: item.created_at, reverse=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(t("problems.rca_line", rca=record.rca_id, cycle=record.cycle,
                          status=t_or_value(f"rca_status.{record.status}", record.status)))
            if st.button(t("problems.open_rca"), key=f"open_{record.rca_id}", type="tertiary"):
                state.set_active_rca(record.rca_id)
                st.switch_page(navigation.INVESTIGATION)


def history_section(events) -> None:
    with st.expander(t("problems.history_title"), icon=theme.ICONS["history"]):
        for event in events:
            action = t(f"event.{event.action}", incident=event.incident_id or "")
            st.markdown(t("problems.event", date=formatting.date_time(event.at), name=event.by, action=action)
                        + (f" — {event.reason}" if event.reason else ""))


def start_section(problem) -> None:
    with st.container(border=True):
        st.markdown(f"**{t('problems.start_title')}**")
        reference = problem.incidents[-1].incident_id
        st.caption(t("problems.start_hint", incident=reference))
        guidance = guidance_form(key="problem_guidance")
        if st.button(t("problems.start_action"), type="primary", icon=theme.ICONS["investigation"]):
            # an incident of a problem brings the whole problem into the investigation
            state.select_incident(reference)
            state.set_active_rca(None)
            state.request_investigation(guidance)
            st.switch_page(navigation.INVESTIGATION)


def add_section(problem) -> None:
    with st.expander(t("problems.add_title"), icon=":material/add:"):
        try:
            candidates = services.unassigned_incidents()
        except services.ServiceError:
            candidates = []
        options = {f"{item.incident_id} · {item.service} · {item.title}": item.incident_id for item in candidates}
        chosen = st.selectbox(t("problems.add_choose"), list(options), index=None, key="problem_add_choice")
        if st.button(t("problems.add_action"), disabled=chosen is None, key="problem_add"):
            act(services.attach_incident, problem.problem_id, options[chosen])
            st.rerun()


def remove_section(problem) -> None:
    with st.expander(t("problems.remove_title"), icon=":material/remove:"):
        if len(problem.incidents) == 1:
            st.caption(t("problems.remove_last"))
            return
        chosen = st.selectbox(t("problems.remove_choose"), [link.incident_id for link in problem.incidents],
                              index=None, key="problem_remove_choice")
        reason = st.text_input(t("problems.remove_reason"), key="problem_remove_reason")
        if st.button(t("problems.remove_action"), disabled=chosen is None, key="problem_remove"):
            if not reason.strip():
                st.error(t("problems.reason_required"), icon=theme.ICONS["error"])
                return
            act(services.detach_incident, problem.problem_id, chosen, reason.strip())
            st.rerun()


def close_section(problem) -> None:
    with st.expander(t("problems.close_title"), icon=":material/task_alt:"):
        reason = st.text_input(t("problems.close_reason"), key="problem_close_reason")
        if st.button(t("problems.close_action"), key="problem_close"):
            if not reason.strip():
                st.error(t("problems.reason_required"), icon=theme.ICONS["error"])
                return
            act(services.close_problem, problem.problem_id, reason.strip())
            st.rerun()


def reopen_section(problem) -> None:
    with st.container(border=True):
        st.markdown(f"**{t('problems.reopen_title')}**")
        reason = st.text_input(t("problems.reopen_reason"), key="problem_reopen_reason")
        if st.button(t("problems.reopen_action"), key="problem_reopen"):
            if not reason.strip():
                st.error(t("problems.reason_required"), icon=theme.ICONS["error"])
                return
            act(services.reopen_problem, problem.problem_id, reason.strip())
            st.rerun()


page_header(t("problems.title"), t("problems.subtitle"))
show_flash()
selected = st.query_params.get("problem")
if selected:
    problem_detail(selected)
else:
    problem_list()
