"""Problems: the list, the proposed ones, and one problem with its incidents, its RCAs and its history.

The Problem Manager starts the RCA from here. Every change goes through the API, which applies the
rules (rca/problems.py); a refused change shows its reason, and a warning is shown after a change
that is allowed but worth a second look.
"""

import pandas as pd
from uuid import uuid4

import streamlit as st

from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components.guidance_form import guidance_form, guidance_lines
from rca.ui.components.incident_details import incident_details_dialog
from rca.ui.components.page_header import page_header
from rca.ui.strings import t, t_or_value

FLASH_KEY = "problems_flash"  # what the last change said, shown once after the rerun
REMOVING_KEY = "problems_removing"  # the incident whose removal is being confirmed
ACTIVE_RCA = ("DRAFT", "AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS", "FAILED")  # as rca/store.py
MAX_REJECTED_CASES = 2  # as rca/problems.py: the interface talks to the API only
MAX_GUIDE_LENGTH = 4000  # as rca/problems.py
CANDIDATES_SHOWN = 15  # the most alike incidents offered for adding


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
    choice = st.segmented_control(t("problems.filter"), ["Open", "In investigation", "Manual", "Closed", "all"], default="Open",
                                  format_func=lambda value: t(f"problems.filter.{value}"), key="problems_filter")
    try:
        found = services.list_problems(None if choice in (None, "all") else choice)
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return

    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(t("problems.proposals_hint"))
        if st.button(t("problems.proposals_link"), icon=theme.ICONS["proposals"], type="tertiary", key="to_proposals"):
            st.switch_page(navigation.PROPOSALS)

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
            "priority": st.column_config.TextColumn(t("problems.col.priority"), width=70,
                                                    help=t("problems.priority_rule")),
            "incidents": st.column_config.NumberColumn(t("problems.col.incidents"), width=80),
            "services": st.column_config.TextColumn(t("problems.col.services"), width=150),
            "status": st.column_config.TextColumn(t("problems.col.status"), width=80),
            "created": st.column_config.DatetimeColumn(t("problems.col.created"), format="D MMM YYYY", width=110),
        },
    )
    if event.selection.rows:
        open_problem(found[event.selection.rows[0]].problem_id)


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
    is_open = problem.status in ("Open", "In investigation")  # its incidents and its guidance may change

    st.subheader(f"{problem.problem_id} · {problem.title}")
    st.caption(f"{t('problems.status')}: {t_or_value(f'problems.filter.{problem.status}', problem.status)} · "
               f"{t('problems.priority')}: {problem.priority} · {t('problems.services')}: {', '.join(problem.services)}",
               help=t("problems.priority_rule"))
    st.caption(t("problems.opened_by", name=problem.created_by, date=formatting.date_time(problem.created_at)))
    if problem.rca_id:
        st.caption(t("problems.closed_by_rca", rca=problem.rca_id))
    elif problem.close_reason:
        st.caption(t("problems.closed_because", date=formatting.date_time(problem.closed_at), reason=problem.close_reason))
    st.markdown(problem.description)

    left, right = st.columns([3, 2], gap="large")
    with left:
        incidents_section(problem, is_open)
        if problem.status == "Open":  # in investigation the RCA waits for the expert: no incident changes
            add_section(problem)
        rcas_section(rcas)
        history_section(events)
    with right:
        if is_open:
            start_section(problem, rcas)
            if problem.status == "Open":
                close_section(problem)
        elif problem.status == "Manual":
            st.warning(t("problems.manual"), icon=":material/support_agent:")
            close_section(problem)
        else:
            reopen_section(problem)


def _stop_removing() -> None:
    st.session_state.pop(REMOVING_KEY, None)


@st.dialog(" ", on_dismiss=_stop_removing)
def remove_dialog(problem, incident_id: str) -> None:
    """Removing an incident needs a confirmation and a reason; the incident itself is kept."""
    st.markdown(f"### {t('problems.remove_confirm_title', incident=incident_id, problem=problem.problem_id)}")
    st.caption(t("problems.remove_confirm_text"))
    reason = st.text_area(t("problems.remove_reason"), key=f"remove_reason_{incident_id}")
    confirm, cancel = st.columns(2)
    confirmed = confirm.button(t("problems.remove_action"), type="primary", key=f"remove_confirm_{incident_id}")
    if cancel.button(t("problems.cancel"), key=f"remove_cancel_{incident_id}"):
        _stop_removing()
        st.rerun()
    if confirmed:
        if not reason.strip():
            st.error(t("problems.reason_required"), icon=theme.ICONS["error"])
            return
        _stop_removing()
        act(services.detach_incident, problem.problem_id, incident_id, reason.strip())
        st.rerun()


def incidents_section(problem, is_open: bool) -> None:
    """One card per incident: what it is, who linked it, its details, and removing it."""
    st.markdown(f"**{t('problems.incidents_title', count=len(problem.incidents))}**")
    last = len(problem.incidents) == 1
    removable = problem.status == "Open"  # in investigation the RCA in progress covers these incidents
    if is_open and not removable:
        st.caption(t("problems.remove_in_investigation"))
    for link in problem.incidents:
        incident = services.get_incident(link.incident_id)
        with st.container(border=True):
            st.markdown(f"`{link.incident_id}` · {incident.title if incident else ''}")
            if incident:
                st.caption(f"{incident.service} · {incident.severity} · {formatting.date_time(incident.detected_at)}")
            st.caption(t("problems.linked", name=link.linked_by, date=formatting.date_time(link.linked_at)))
            with st.container(horizontal=True, gap="small"):
                if incident and st.button(t("selection.view_details"), key=f"details_{link.incident_id}",
                                          icon=":material/info:", type="tertiary"):
                    incident_details_dialog(incident)
                if removable and st.button(t("problems.remove_button"), key=f"remove_{link.incident_id}",
                                         icon=":material/remove_circle:", type="tertiary", disabled=last,
                                         help=t("problems.remove_last") if last else None):
                    st.session_state[REMOVING_KEY] = link.incident_id
    # the confirmation stays open across reruns until it is confirmed, cancelled or dismissed
    removing = st.session_state.get(REMOVING_KEY)
    if removable and removing in {link.incident_id for link in problem.incidents}:
        remove_dialog(problem, removing)


def add_section(problem) -> None:
    """The incidents that may be added, the most alike first, with their similarity to the problem."""
    with st.expander(t("problems.add_title"), icon=":material/add:"):
        st.caption(t("problems.add_hint"))
        try:
            candidates = services.problem_candidates(problem.problem_id)[:CANDIDATES_SHOWN]
            scored = True
        except services.ServiceError:  # the search index is not built: the incidents, without their score
            candidates = [{"incident_id": item.incident_id, "title": item.title, "service": item.service,
                           "severity": item.severity, "detected_at": item.detected_at.isoformat(),
                           "similarity": None, "alike": False} for item in services.unassigned_incidents()]
            scored = False
            st.caption(t("problems.add_no_scores"))
        if not candidates:
            st.info(t("problems.add_none"), icon=":material/info:")
            return
        frame = pd.DataFrame({
            "incident": [item["incident_id"] for item in candidates],
            "title": [item["title"] for item in candidates],
            "service": [item["service"] for item in candidates],
            "severity": [item["severity"] for item in candidates],
            "similarity": [item["similarity"] for item in candidates],
            "alike": [item["alike"] for item in candidates],
        })
        st.dataframe(
            frame, hide_index=True, key="problem_add_table",
            column_config={
                "incident": st.column_config.TextColumn(t("problems.col.incident"), width=140),
                "title": st.column_config.TextColumn(t("problems.col.title"), width="medium"),
                "service": st.column_config.TextColumn(t("problems.col.services"), width=120),
                "severity": st.column_config.TextColumn(t("table.severity"), width=70),
                "similarity": st.column_config.NumberColumn(t("problems.col.similarity"), format="%.2f", width=90,
                                                            help=t("problems.similarity_help")),
                "alike": st.column_config.CheckboxColumn(t("problems.col.alike"), width=70,
                                                         help=t("problems.alike_help")),
            },
            # the score first: it is what the list is ordered by
            column_order=["incident", *(["similarity", "alike"] if scored else []), "severity", "title", "service"],
        )
        labels = {(f"{item['incident_id']} · {item['title']}"
                   + (f" · {item['similarity']:.2f}" if item["similarity"] is not None else "")): item["incident_id"]
                  for item in candidates}
        label = st.selectbox(t("problems.add_choose"), list(labels), index=None, key="problem_add_choice")
        if label is None:
            return
        chosen = labels[label]
        incident = services.get_incident(chosen)
        if incident and st.button(t("selection.view_details"), key="add_details", icon=":material/info:", type="tertiary"):
            incident_details_dialog(incident)
        reason = st.text_input(t("problems.add_reason"), key=f"add_reason_{chosen}")
        if st.button(t("problems.add_action_for", incident=chosen), key="problem_add", type="primary"):
            act(services.attach_incident, problem.problem_id, chosen, reason.strip() or None)
            st.rerun()


def rcas_section(rcas) -> None:
    st.markdown(f"**{t('problems.rcas_title')}**")
    if not rcas:
        st.caption(t("problems.rcas_none"))
        return
    for record in sorted(rcas, key=lambda item: item.created_at, reverse=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(t("problems.rca_line", rca=record.rca_id, cycle=record.revision,
                          status=t_or_value(f"rca_status.{record.status}", record.status)))
            if st.button(t("problems.open_rca"), key=f"open_{record.rca_id}", type="tertiary"):
                state.set_active_rca(record.rca_id)
                st.switch_page(navigation.INVESTIGATION)


def history_section(events) -> None:
    with st.expander(t("problems.history_title"), icon=theme.ICONS["history"]):
        for event in events:
            to = event.details.get("to") or ""
            to = t_or_value(f"rca_status.{to}", to) if event.action == "rca_status" else \
                t_or_value(f"problems.filter.{to}", to)
            action = t(f"event.{event.action}", incident=event.incident_id or "", rca=event.rca_id or "", to=to)
            if event.details.get("imported"):
                action += " " + t("event.imported")
            if event.details.get("migrated"):
                action += " " + t("event.migrated")
            st.markdown(t("problems.event", date=formatting.date_time(event.at), name=event.by, action=action)
                        + (f" — {event.reason}" if event.reason else ""))
            if event.action == "guide_updated":  # the guidance as saved; an older text guide as it was
                lines = guidance_lines(event.details.get("guidance")) if "guidance" in event.details else \
                    [event.details.get("guide") or ""]
                st.caption("  \n".join(line for line in lines if line) or t("guidance.cleared"))


def cases(rcas) -> list:
    """The last revision of every RCA case of the problem."""
    last: dict = {}
    for record in sorted(rcas, key=lambda item: (item.revision, item.created_at)):
        last[record.rca_id] = record
    return list(last.values())


def start_section(problem, rcas) -> None:
    with st.container(border=True):
        st.markdown(f"**{t('problems.start_title')}**")
        latest = cases(rcas)
        active = [record for record in latest if record.status in ACTIVE_RCA]
        if active:
            # one case at a time: the case in progress is continued, not doubled
            st.info(t("problems.active_case", rca=active[0].rca_id,
                      status=t_or_value(f"rca_status.{active[0].status}", active[0].status)), icon=":material/info:")
            if st.button(t("problems.open_rca"), key="open_active", type="primary"):
                state.set_active_rca(active[0].rca_id)
                st.switch_page(navigation.INVESTIGATION)
            saved = guidance_lines(problem.guidance)
            if saved:  # the guidance this RCA started with, kept on the problem for the next one
                st.caption(t("guidance.saved_title"))
                st.markdown("  \n".join(saved))
            return
        rejected = [record for record in latest if record.status == "REJECTED"]
        if rejected:
            st.caption(t("problems.rejected_count", count=len(rejected), maximum=MAX_REJECTED_CASES))
            st.warning(t("problems.after_rejection", rca=rejected[-1].rca_id), icon=":material/warning:")
        reference = problem.incidents[-1].incident_id
        st.caption(t("problems.start_hint", incident=reference))
        guidance = guidance_form(key=f"guidance_{problem.problem_id}", initial=problem.guidance)
        saved = problem.guidance.model_dump(mode="json") if problem.guidance else None
        with st.container(horizontal=True, gap="small"):
            save = st.button(t("guidance.save"), key="guidance_save", disabled=guidance == saved,
                             help=t("guidance.save_help"))
            start = st.button(t("problems.start_action"), type="primary", icon=theme.ICONS["investigation"])
        if save:
            act(services.set_guidance, problem.problem_id, guidance)
            st.rerun()
        if start:
            # the RCA is saved at once and investigated on the server; one key per start, so a second
            # click returns the same RCA instead of starting another one
            key = st.session_state.setdefault(f"start_rca_{problem.problem_id}", uuid4().hex)
            try:
                revision = services.start_rca(problem.problem_id, guidance, key)
            except services.ServiceError as error:
                st.session_state.pop(f"start_rca_{problem.problem_id}", None)
                flash(error=services.user_message(error))
                st.rerun()
            st.session_state.pop(f"start_rca_{problem.problem_id}", None)
            state.set_active_rca(revision.rca_id)
            st.switch_page(navigation.INVESTIGATION, query_params={"rca": revision.rca_id})


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
