"""Technical review: the Technical Expert reads an analysis and decides on it.

Two views in one screen. Without an analysis chosen it is the queue of what is waiting.
With one chosen it is that analysis: what it is about, how its findings connect, the
analysis itself, and the three decisions.

The three decisions are deliberately not equal. Approving is the primary action. Asking for
more detail is an ordinary one. Rejecting is quiet, and both it and the request explain, in
their own words, that a further investigation will be needed. Nothing is decided without a
confirmation step, and nothing overwrites the analysis that was read.
"""

import streamlit as st

from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components import rca_draft
from rca.ui.components.cause_diagram import cause_diagram
from rca.ui.components.incident_card import incident_summary
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

REVIEWER_KEY = "reviewer_name"
OUTCOME_KEY = "review_outcome"
DECIDABLE = ("PENDING_REVIEW",)


def chosen_rca() -> str | None:
    """The analysis being reviewed, kept in the address so a review can be reopened later."""
    from_url = st.query_params.get("rca")
    if from_url:
        return from_url
    return None


def open_review(rca_id: str) -> None:
    st.query_params["rca"] = rca_id
    st.rerun()


def back_to_queue() -> None:
    st.query_params.pop("rca", None)
    st.session_state.pop(OUTCOME_KEY, None)
    st.rerun()


def reviewer_name() -> str:
    return (st.session_state.get(REVIEWER_KEY) or "").strip() or state.role_name(state.TECHNICAL_EXPERT)


def requested_checks(decision: str, comment: str) -> list[str] | None:
    """A request written as several lines becomes several checks; one line stays one request."""
    if decision != "REQUEST_MORE_DETAILS":
        return None
    lines = [line.strip("-* ").strip() for line in comment.splitlines() if line.strip()]
    return lines if len(lines) > 1 else None


def decide(rca_id: str, decision: str, comment: str, hypothesis_id: str | None = None) -> bool:
    """Record a decision. The screen shows what happened next, so it only reports success."""
    try:
        services.apply_review(
            rca_id, reviewer_name(), decision, comment, hypothesis_id,
            requested_checks=requested_checks(decision, comment),
        )
    except services.ServiceError as error:
        st.error(t("review.decision_failed"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return False
    st.session_state[OUTCOME_KEY] = decision
    return True


# --------------------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------------------


def queue() -> None:
    st.subheader(t("review.queue_title"))
    try:
        waiting = services.list_rcas(status="PENDING_REVIEW")
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return

    if not waiting:
        st.info(t("review.queue_empty"), icon=":material/inbox:")
        st.caption(t("review.queue_hint"))
        return

    for record in waiting:
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
                st.markdown(f"`{record.rca_id}` · {t('review.for_incident')} `{record.incident_id}`")
                if st.button(t("review.open"), key=f"open-{record.rca_id}", type="primary",
                             icon=theme.ICONS["review"]):
                    open_review(record.rca_id)
            summary = record.investigation_summary or ""
            st.caption(f"{t('review.created')}: {formatting.date_time(record.created_at)} · "
                       f"{t('draft.evidence_count')}: {len(record.evidence)} · "
                       f"{t('cycle.number', number=record.cycle)}")
            if summary:
                st.markdown(summary[:200] + ("..." if len(summary) > 200 else ""))
            if record.weakly_supported:
                st.caption(t("draft.weak"))


# --------------------------------------------------------------------------------------
# The decisions
# --------------------------------------------------------------------------------------


@st.dialog(t("approve.title"))
def approve_dialog(record) -> None:
    st.caption(t("approve.choose"))
    choices = {
        f"{hypothesis.confidence} - {hypothesis.candidate_root_cause[:90]}": hypothesis.hypothesis_id
        for hypothesis in record.hypotheses
    }
    chosen = st.radio(t("approve.choose"), list(choices), label_visibility="collapsed")
    comment = st.text_area(t("approve.comment"))
    st.text_input(t("review.reviewer"), key=REVIEWER_KEY, placeholder=state.role_name(state.TECHNICAL_EXPERT))
    if st.button(t("approve.confirm"), type="primary", icon=":material/check:"):
        if decide(record.rca_id, "APPROVE", comment or t("approve.confirm"), choices[chosen]):
            st.rerun()


@st.dialog(t("request.title"))
def request_dialog(record) -> None:
    st.caption(t("request.intro"))
    st.caption(t("request.current"))
    for hypothesis in record.hypotheses:
        st.markdown(f"- **{hypothesis.confidence}** - {hypothesis.candidate_root_cause}")
    question = st.text_area(t("request.question"), placeholder=t("request.placeholder"))
    st.text_input(t("review.reviewer"), key=REVIEWER_KEY, placeholder=state.role_name(state.TECHNICAL_EXPERT))
    if st.button(t("request.send"), type="primary", icon=":material/send:"):
        if not question.strip():
            st.error(t("review.comment_required"), icon=theme.ICONS["error"])
            return
        if decide(record.rca_id, "REQUEST_MORE_DETAILS", question.strip()):
            st.rerun()


@st.dialog(t("reject.title"))
def reject_dialog(record) -> None:
    st.warning(t("reject.warning"), icon=":material/warning:")
    comment = st.text_area(t("reject.comment"))
    st.text_input(t("review.reviewer"), key=REVIEWER_KEY, placeholder=state.role_name(state.TECHNICAL_EXPERT))
    if st.button(t("reject.confirm"), icon=":material/block:"):
        if not comment.strip():
            st.error(t("review.comment_required"), icon=theme.ICONS["error"])
            return
        if decide(record.rca_id, "REJECT", comment.strip()):
            st.rerun()


def decisions(record) -> None:
    """The three ways this review can end, in the order of how often they are right."""
    with st.container(border=True):
        st.caption(t("review.instructions"))
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
            if st.button(t("decision.approve"), type="primary", icon=":material/check_circle:",
                         help=t("decision.approve_help"), disabled=not record.hypotheses):
                approve_dialog(record)
            if st.button(t("decision.request"), icon=":material/help:", help=t("decision.request_help")):
                request_dialog(record)
            if st.button(t("decision.reject"), type="tertiary", icon=":material/block:",
                         help=t("decision.reject_help")):
                reject_dialog(record)


def outcome(record) -> None:
    """What the decision means, once it is taken."""
    review = record.review
    if review is None:
        return
    with st.container(border=True):
        if record.status == "FINAL":
            st.markdown(f"**{t('approve.done_title')}**")
            st.caption(t("approve.done_text"))
            st.caption(t("approve.final_cause"))
            st.markdown(f"**{record.final_root_cause}**")
        elif record.status == "MORE_DETAILS_REQUESTED":
            st.markdown(f"**{t('request.done_title')}**")
            st.caption(t("request.done_text"))
            checks = rca_draft.extra_checks(review)
            if checks:
                st.caption(t("review.requested_checks"))
                for item in checks:
                    st.markdown(f"- {item}")
        elif record.status == "REJECTED":
            st.markdown(f"**{t('reject.done_title')}**")
            st.caption(t("reject.done_text"))

        st.caption(t("review.decided_by", name=review.reviewer, date=formatting.date_time(review.decided_at)))
        if review.comment:
            st.caption(t("review.comment"))
            st.markdown(review.comment)


# --------------------------------------------------------------------------------------
# One analysis
# --------------------------------------------------------------------------------------


def review(rca_id: str) -> None:
    try:
        record = services.get_rca(rca_id)
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return

    if record is None:
        st.info(t("review.not_found"), icon=":material/info:")
        if st.button(t("review.back_to_queue"), icon=theme.ICONS["back"]):
            back_to_queue()
        return

    incident = services.get_incident(record.incident_id)

    if st.button(t("review.back_to_queue"), icon=theme.ICONS["back"], type="tertiary"):
        back_to_queue()

    left, right = st.columns([5, 4], gap="large")

    with left:
        rca_draft.header(record)
        st.caption(f"{t('review.for_incident')} `{record.incident_id}` · "
                   f"{t('cycle.number', number=record.cycle)}")
        if record.status in DECIDABLE:
            decisions(record)
        else:
            outcome(record)
        rca_draft.rca_draft(record)

    with right:
        if incident is not None:
            with st.container(border=True):
                incident_summary(incident)
        cause_diagram(record, incident.title if incident else None)


page_header(
    t("review.title"),
    t("review.subtitle"),
    back_to=navigation.HOME,
)

if not state.is_technical_expert():
    st.info(t("review.wrong_role"), icon=":material/badge:")
    if st.button(t("review.switch_role"), type="primary", icon=theme.ICONS["role"]):
        state.request_role(state.TECHNICAL_EXPERT)
        st.rerun()
    st.stop()

rca_id = chosen_rca()
if rca_id:
    review(rca_id)
else:
    queue()
