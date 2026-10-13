"""The RCA investigation: the problem, the work as it happens, and the analysis it produces.

The screen is split the way the work is split. On the left is what the analysis is about (the problem and
its most recent incident) and what it concluded; on the right is the investigation itself, step by step,
updating while it runs. One action closes the screen: sending the analysis to a Technical Expert.

An RCA always starts from a problem, on the Problems page; this screen follows it, and starts its next
revision when the expert asked for more details or the last run failed.

The investigation runs on the server (api.py): starting it saves the RCA at once, and this screen follows
the saved revision, step by step, until the run ends. Nothing is shown as done before it has run.
"""

from uuid import uuid4

import streamlit as st

from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components import rca_draft
from rca.ui.components.incident_card import incident_summary
from rca.ui.components.incident_details import incident_details_dialog
from rca.ui.components.investigation_timeline import timeline
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

SENT_KEY = "investigation_sent"
REQUEST_KEY = "investigation_request_key"  # one per start: a repeated click gets the same RCA back
POLL_SECONDS = 2


def show(rca_id: str | None) -> None:
    """Point the screen at an analysis, address included, so the two never disagree."""
    state.set_active_rca(rca_id)
    if rca_id:
        st.query_params["rca"] = rca_id
    else:
        st.query_params.pop("rca", None)


def active_record():
    """The analysis this screen is showing: the one another page has just opened (Problems, History), then
    kept in the address only. Opened from the menu, the address has none and the screen shows no RCA: the
    last investigation is not shown again on its own."""
    opened = st.session_state.pop(state.ACTIVE_RCA_KEY, None)
    rca_id = opened or st.query_params.get("rca")
    if not rca_id:
        return None
    if st.query_params.get("rca") != rca_id:
        st.query_params["rca"] = rca_id
    try:
        return services.get_rca(rca_id)
    except services.ServiceError:
        return None


def incident_for(incident_id: str | None):
    if not incident_id:
        return None
    try:
        return services.get_incident(incident_id)
    except services.ServiceError:
        return None


def problem_for(problem_id: str | None):
    if not problem_id:
        return None
    try:
        found = services.get_problem(problem_id)
    except services.ServiceError:
        return None
    return found["problem"] if found else None


def context_panel(record, problem, incident) -> None:
    """What is being investigated: the problem, with the way back to it, and its most recent incident."""
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown(f"`{record.problem_id}` **{problem.title if problem else ''}**")
            if record.problem_id and st.button(t("investigation.open_problem"), icon=theme.ICONS["problems"],
                                               type="tertiary"):
                st.switch_page(navigation.PROBLEMS, query_params={"problem": record.problem_id})
        if problem is not None:
            st.caption(t("investigation.problem_line", count=len(problem.incidents), status=problem.status,
                         priority=problem.priority))
    if incident is None:
        st.caption(t("investigation.incident_missing"))
        return
    with st.container(border=True):
        st.caption(t("investigation.reference_incident"))
        incident_summary(incident)
        if st.button(t("selection.view_details"), icon=":material/info:", type="tertiary"):
            incident_details_dialog(incident)


def steps_panel(record=None, *, running: bool = False, failed: bool = False) -> None:
    finished = record is not None and not running and not failed
    st.subheader(t("investigation.steps_title_done") if finished else t("investigation.steps_title"))
    timeline(
        list(record.trace) if record else [],
        running=running,
        failed=failed,
        plan=record.plan if record else None,
    )


def start_next(record) -> None:
    """Start the next revision of this RCA on the server (the expert asked for more details, or the last run
    failed) and follow it. A repeated click gets the same revision back."""
    key = st.session_state.setdefault(REQUEST_KEY, uuid4().hex)
    try:
        revision = services.start_next_revision(record.rca_id, request_key=key)
    except services.ServiceError as error:
        st.session_state.pop(REQUEST_KEY, None)
        state.set_investigation_error(services.user_message(error))
        st.rerun()
    st.session_state.pop(REQUEST_KEY, None)
    state.set_investigation_error(None)
    show(revision.rca_id)
    st.session_state.pop(SENT_KEY, None)
    st.rerun()


@st.fragment(run_every=POLL_SECONDS)
def progress(rca_id: str) -> None:
    """The steps of the running revision, read again every few seconds from what the server saved."""
    current = services.get_rca(rca_id)
    if current is None or current.run_status != "RUNNING":
        st.rerun()  # the run ended: the whole screen shows the result
    st.subheader(t("investigation.steps_title"))
    timeline(list(current.trace), running=True, plan=current.plan, current=current.current_step)


def running_panel(record) -> None:
    st.info(t("investigation.running"), icon=":material/hourglass_top:")
    st.caption(t("investigation.running_revision", revision=record.revision, rca=record.rca_id))
    st.caption(t("investigation.running_hint"))


def failure_panel(message: str, record) -> None:
    st.error(t("investigation.failed"), icon=theme.ICONS["error"])
    st.caption(t("investigation.failed_hint"))
    if st.button(t("investigation.try_again"), type="primary", icon=":material/refresh:"):
        state.set_investigation_error(None)
        if record.status in ("FAILED", "REQUEST_MORE_DETAILS"):
            start_next(record)
        st.rerun()
    with st.expander(t("investigation.technical_detail")):
        st.code(message)


def send_panel(record) -> None:
    """The one action of this screen, and what it leads to.

    It stands at the end of the analysis, on its own: the next step is taken once the
    whole investigation has been read.
    """
    if record.status == "DRAFT":
        if st.button(t("send.action"), type="primary", icon=":material/send:", help=t("send.help")):
            try:
                services.submit_for_review(record.rca_id)
            except services.ServiceError as error:
                st.error(t("state.error_data"), icon=theme.ICONS["error"])
                st.caption(t("state.error_detail", detail=error))
                return
            st.session_state[SENT_KEY] = True
            st.rerun()
        return

    if record.status == "AWAITING_TECHNICAL_REVIEW":
        with st.container(border=True):
            st.markdown(f"**{t('send.sent_title')}**")
            st.caption(t("send.sent_text"))
            st.page_link(navigation.HISTORY, label=t("send.open_history"), icon=theme.ICONS["history"])


def next_cycle_panel(record) -> None:
    """An analysis the Technical Expert sent back, and the way to the next investigation."""
    title = t("cycle.rejected_title") if record.status == "REJECTED" else t("cycle.more_details_title")
    with st.container(border=True):
        st.markdown(f"**{title}**")
        review = record.review
        if review is not None:
            if review.comment:
                st.markdown(review.comment)
            st.caption(t("review.decided_by", name=review.reviewer,
                         date=formatting.date_time(review.decided_at)))
        if record.status == "REJECTED" and record.problem_id:
            # a new case needs something new (guidance or incidents), which is given on the problem page
            st.caption(t("cycle.rejected_next"))
            if st.button(t("cycle.open_problem", problem=record.problem_id), type="primary", icon=theme.ICONS["problems"]):
                st.switch_page(navigation.PROBLEMS, query_params={"problem": record.problem_id})
            return
        if st.button(t("cycle.start_next"), type="primary", icon=theme.ICONS["investigation"],
                     help=t("cycle.start_next_help")):
            start_next(record)


def analysis_panel(record) -> None:
    """The result: what it is, what can be done with it, then the analysis itself."""
    if record.status == "ESCALATED_MANUAL":
        st.warning(t("investigation.escalated_manual"), icon=":material/warning:")
        st.caption(t("investigation.escalated_manual_hint"))
        rca_draft.rca_draft(record, with_metadata=True, context=t("cycle.number", number=record.revision), brief=True)
        return
    if record.status == "FAILED":
        st.warning(t("investigation.escalated"), icon=":material/warning:")
        st.caption(t("investigation.escalated_hint"))
        rca_draft.metadata(record)
        if st.button(t("investigation.try_again"), icon=":material/refresh:"):
            start_next(record)
        if record.error or record.investigation_summary:
            with st.expander(t("investigation.technical_detail")):
                st.markdown(record.error or record.investigation_summary)
        return

    rca_draft.rca_draft(
        record,
        with_metadata=True,
        context=t("cycle.number", number=record.revision) if record.revision > 1 else None,
        brief=True,
    )
    # What happens next comes after the whole analysis, never before it.
    if record.status in ("REJECTED", "REQUEST_MORE_DETAILS"):
        next_cycle_panel(record)
    else:
        send_panel(record)


page_header(t("investigation.title"), t("investigation.subtitle"))

record = active_record()
asked_for = st.query_params.get("rca")
missing_record = bool(asked_for) and record is None

left, right = st.columns([5, 4], gap="large")

if st.session_state.pop(SENT_KEY, False):
    st.toast(t("send.confirmation"), icon=":material/send:")

if record is None:
    if missing_record:
        show(None)
    with left:
        st.info(t("investigation.not_found") if missing_record else t("investigation.nothing_open"),
                icon=":material/info:")
        st.caption(t("investigation.start_from_problem"))
        if st.button(t("investigation.open_problems"), type="primary", icon=theme.ICONS["problems"]):
            st.switch_page(navigation.PROBLEMS)
    with right:
        steps_panel()

else:
    problem = problem_for(record.problem_id)
    incident = incident_for(record.incident_id)
    with left:
        context_panel(record, problem, incident)
    if state.investigation_error():
        with left:
            failure_panel(state.investigation_error(), record)
        with right:
            steps_panel(failed=True)
    elif record.run_status == "RUNNING":
        with left:
            running_panel(record)
        with right:
            progress(record.rca_id)
    else:
        with left:
            analysis_panel(record)
        with right:
            steps_panel(record)
