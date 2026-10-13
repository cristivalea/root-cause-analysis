"""Proposed Problem Records: where the Problem Manager decides what the analysis of the incidents proposes.

Three kinds of proposals, computed by code (rca/suggestions.proposals), never by a model:
groups of alike incidents for a new problem, an incident for an open problem, and an incident on its own
for a new problem (the major ones first). Every incident in no problem is in one of them, an incident removed
from a problem included. Each one shows its incidents, its score with what the score means, its reasons and
its evidence. Accepting creates the problem (or adds the incident) in one step on the server, after the rules
are checked again; the confirmation names the problem and leads to it. Rejecting a group or an attach keeps it out of
the list while its incidents stay the same, and its incidents come back on their own; an incident on its own
cannot be rejected.
"""

import streamlit as st

from rca.ui import formatting, navigation, services, theme
from rca.ui.components.incident_details import incident_details_dialog
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

CREATED_KEY = "proposal_created"  # the problem the last accept made or changed, for the confirmation
ERROR_KEY = "proposal_error"
KINDS = ("group", "attach", "single")


@st.dialog(" ")
def confirmation(problem_id: str, kind: str, created: bool) -> None:
    """The problem the proposal made or changed, and the way to it."""
    title = t("proposals.done_attach", problem=problem_id) if kind == "attach" else t("proposals.done_created",
                                                                                    problem=problem_id)
    st.markdown(f"### {title}")
    st.caption(t("proposals.done_text") if created else t("proposals.done_again"))
    if st.button(t("proposals.open_problems"), type="primary", icon=theme.ICONS["problems"]):
        st.session_state.pop(CREATED_KEY, None)
        st.switch_page(navigation.PROBLEMS, query_params={"problem": problem_id})
    if st.button(t("proposals.stay"), type="tertiary"):
        st.session_state.pop(CREATED_KEY, None)
        st.rerun()


def incident_line(incident_id: str, incidents: dict, key: str) -> None:
    incident = incidents.get(incident_id)
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        if incident is None:
            st.markdown(f"`{incident_id}`")
            return
        st.markdown(f"`{incident_id}` · {incident.title}  \n"
                    f":gray[{incident.service} · {incident.severity} · {formatting.date_time(incident.detected_at)}]")
        if st.button(t("selection.view_details"), key=f"details-{key}-{incident_id}", icon=":material/info:",
                     type="tertiary"):
            incident_details_dialog(incident)


def proposal_card(proposal: dict, incidents: dict) -> None:
    key = proposal["key"]
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            if proposal["kind"] == "attach":
                st.markdown(f"**{t('proposals.attach_title', problem=proposal['problem_id'])}**")
            else:
                st.markdown(f"**{t('proposals.new_title', count=len(proposal['incident_ids']))}**")
            if proposal["score"] is not None:
                # an incident on its own has a score only when it looks like a closed problem: the score is that
                label = (t("proposals.score_to", problem=proposal["recurrence_of"])
                         if proposal["kind"] == "single" and proposal.get("recurrence_of") else t("proposals.score"))
                st.metric(label, f"{proposal['score']:.2f}", help=proposal["score_meaning"], width="content")
            else:
                st.caption(t("proposals.no_score"), help=proposal["score_meaning"])
        for incident_id in proposal["incident_ids"]:
            incident_line(incident_id, incidents, key)
        st.caption(t("proposals.reasons"))
        for reason in proposal["reasons"]:
            st.markdown(f"- {reason}")
        st.caption(t("proposals.evidence"))
        for fact in proposal["evidence"]:
            st.markdown(f"- {fact}")
        actions(proposal)


def actions(proposal: dict) -> None:
    key = proposal["key"]
    accept, reject = st.columns(2, gap="medium")
    with accept:
        title = None
        if proposal["kind"] != "attach":
            title = st.text_input(t("proposals.title_input"), key=f"title-{key}", placeholder=t("proposals.title_hint"))
        reason = st.text_input(t("proposals.reason_input"), key=f"reason-{key}")
        label = t("proposals.accept_attach") if proposal["kind"] == "attach" else t("proposals.accept_new")
        if st.button(label, key=f"accept-{key}", type="primary", icon=":material/check:"):
            try:
                problem, _, created = services.accept_proposal(proposal, title or None, reason or None)
            except services.ServiceError as error:
                st.session_state[ERROR_KEY] = services.user_message(error)
                st.rerun()
            st.session_state[CREATED_KEY] = (problem.problem_id, proposal["kind"], created)
            st.rerun()
    if proposal["kind"] == "single":  # every incident in no problem needs a problem
        return
    with reject:
        why = st.text_input(t("proposals.reject_reason"), key=f"why-{key}")
        if st.button(t("proposals.reject"), key=f"reject-{key}", icon=":material/close:"):
            try:
                services.reject_proposal(proposal, why or None)
            except services.ServiceError as error:
                st.session_state[ERROR_KEY] = services.user_message(error)
            st.rerun()


page_header(t("proposals.title"), t("proposals.subtitle"))

if st.session_state.get(CREATED_KEY):
    confirmation(*st.session_state[CREATED_KEY])
if st.session_state.get(ERROR_KEY):
    st.error(st.session_state.pop(ERROR_KEY), icon=theme.ICONS["error"])

try:
    with st.spinner(t("proposals.loading")):
        found = services.list_proposals()
        incidents = {item.incident_id: item for item in services.list_incidents()}
except services.ServiceError as error:
    st.error(t("state.error_data"), icon=theme.ICONS["error"])
    st.caption(t("state.error_detail", detail=error))
    st.stop()

st.caption(t("proposals.score_hint"))
tabs = st.tabs([t(f"proposals.kind.{kind}", count=sum(1 for item in found if item["kind"] == kind)) for kind in KINDS])
for tab, kind in zip(tabs, KINDS):
    with tab:
        st.caption(t(f"proposals.kind_hint.{kind}"))
        listed = [item for item in found if item["kind"] == kind]
        if not listed:
            st.info(t(f"proposals.none.{kind}"), icon=":material/info:")
        for proposal in listed:
            proposal_card(proposal, incidents)
