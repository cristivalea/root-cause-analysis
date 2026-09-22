"""The RCA investigation: the incident, the work as it happens, and the analysis it produces.

The screen is split the way the work is split. On the left is what the analysis is about
and what it concluded; on the right is the investigation itself, step by step, updating
while it runs. One action closes the screen: sending the analysis to a Technical Expert.

The investigation runs in this browser tab, so the tab has to stay open while it works.
"""

import streamlit as st

from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components import rca_draft
from rca.ui.components.incident_card import incident_summary
from rca.ui.components.incident_details import incident_details_dialog
from rca.ui.components.investigation_timeline import timeline
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

SENT_KEY = "investigation_sent"
NEXT_CYCLE_KEY = "next_cycle_after"


def show(rca_id: str | None) -> None:
    """Point the screen at an analysis, address included, so the two never disagree."""
    state.set_active_rca(rca_id)
    if rca_id:
        st.query_params["rca"] = rca_id
    else:
        st.query_params.pop("rca", None)


def active_record():
    """The analysis this screen is showing, kept in the address so the page can be reopened."""
    from_url = st.query_params.get("rca")
    if from_url and not state.active_rca_id():
        state.set_active_rca(from_url)
    rca_id = state.active_rca_id()
    if not rca_id:
        st.query_params.pop("rca", None)
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


def incident_panel(incident) -> None:
    """The context: enough of the incident to know what is being investigated."""
    if incident is None:
        st.caption(t("investigation.incident_missing"))
        return
    with st.container(border=True):
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


def run_investigation(incident_id: str, right) -> None:
    """Run the investigation, showing each step on the right as it finishes."""
    finished: list = []
    slot = right.empty()

    def draw() -> None:
        with slot.container():
            st.subheader(t("investigation.steps_title"))
            timeline(finished, running=True)

    draw()

    def on_step(step) -> None:
        finished.append(step)
        draw()

    try:
        record = services.start_investigation(
            incident_id,
            owner=state.role_name(state.PROBLEM_MANAGER),
            on_step=on_step,
        )
    except services.ServiceError as error:
        state.set_investigation_error(str(error))
        st.rerun()

    state.set_investigation_error(None)
    previous = st.session_state.pop(NEXT_CYCLE_KEY, None)
    if previous:
        try:
            services.link_to_case(previous, record.rca_id)
        except services.ServiceError:
            pass  # the analysis is saved either way; only the link to the case is lost
    show(record.rca_id)
    st.session_state.pop(SENT_KEY, None)
    st.rerun()


def failure_panel(message: str, incident_id: str | None) -> None:
    st.error(t("investigation.failed"), icon=theme.ICONS["error"])
    st.caption(t("investigation.failed_hint"))
    if incident_id and st.button(t("investigation.try_again"), type="primary", icon=":material/refresh:"):
        state.set_investigation_error(None)
        state.request_investigation()
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

    if record.status == "PENDING_REVIEW":
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
        if st.button(t("cycle.start_next"), type="primary", icon=theme.ICONS["investigation"],
                     help=t("cycle.start_next_help")):
            st.session_state[NEXT_CYCLE_KEY] = record.rca_id
            state.select_incident(record.incident_id)
            show(None)
            state.request_investigation()
            st.rerun()


def analysis_panel(record) -> None:
    """The result: what it is, what can be done with it, then the analysis itself."""
    if record.status == "ESCALATED":
        st.warning(t("investigation.escalated"), icon=":material/warning:")
        st.caption(t("investigation.escalated_hint"))
        rca_draft.metadata(record)
        if st.button(t("investigation.try_again"), icon=":material/refresh:"):
            state.request_investigation()
            show(None)
            st.rerun()
        if record.investigation_summary:
            with st.expander(t("investigation.technical_detail")):
                st.markdown(record.investigation_summary)
        return

    rca_draft.rca_draft(
        record,
        with_metadata=True,
        context=t("cycle.number", number=record.cycle) if record.cycle > 1 else None,
    )
    # What happens next comes after the whole analysis, never before it.
    if record.status in ("REJECTED", "MORE_DETAILS_REQUESTED"):
        next_cycle_panel(record)
    else:
        send_panel(record)


page_header(t("investigation.title"), t("investigation.subtitle"))

record = active_record()
asked_for = st.query_params.get("rca")
missing_record = bool(asked_for) and record is None
incident_id = record.incident_id if record else state.selected_incident_id()
incident = incident_for(incident_id)
starting = state.take_investigation_request() and bool(incident_id)

left, right = st.columns([5, 4], gap="large")

if st.session_state.pop(SENT_KEY, False):
    st.toast(t("send.confirmation"), icon=":material/send:")

if missing_record:
    show(None)
    with left:
        st.info(t("investigation.not_found"), icon=":material/info:")
        st.caption(t("investigation.not_found_hint"))
        if st.button(t("investigation.choose_incident"), type="primary", icon=theme.ICONS["start_rca"]):
            st.switch_page(navigation.START_RCA)
    with right:
        steps_panel()

elif incident is None and record is None:
    with left:
        st.info(t("investigation.nothing_selected"), icon=":material/info:")
        if st.button(t("investigation.choose_incident"), type="primary", icon=theme.ICONS["start_rca"]):
            st.switch_page(navigation.START_RCA)
    with right:
        steps_panel()

elif starting:
    with left:
        incident_panel(incident)
        st.info(t("investigation.running"), icon=":material/hourglass_top:")
        st.caption(t("investigation.running_hint"))
    run_investigation(incident_id, right)

elif state.investigation_error():
    with left:
        incident_panel(incident)
        failure_panel(state.investigation_error(), incident_id)
    with right:
        steps_panel(failed=True)

elif record is None:
    with left:
        incident_panel(incident)
        if st.button(t("investigation.start"), type="primary", icon=theme.ICONS["investigation"]):
            state.request_investigation()
            st.rerun()
    with right:
        steps_panel()

else:
    with left:
        incident_panel(incident)
        analysis_panel(record)
    with right:
        steps_panel(record)
