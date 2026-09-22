"""RCA history: the cases that were investigated, and what happened to each of them.

A case is one incident investigated one or more times. A rejected analysis, or one sent
back for more detail, is never overwritten: it stays in the case with the decision taken on
it, and the next investigation sits next to it. That is what this screen shows.

Both roles read it. The Problem Manager follows their own cases; the Technical Expert comes
back to a review they left, sometimes days later, which is why a case has its own address.
"""

import streamlit as st

from rca.models import RCARecord
from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components import badges, rca_draft
from rca.ui.components.page_header import page_header
from rca.ui.components.search_box import filter_while_typing, search_field
from rca.ui.strings import t

SEARCH_KEY = "history_search"
STATUS_KEY = "history_status"
SERVICE_KEY = "history_service"

STATUSES = ("FINAL", "PENDING_REVIEW", "MORE_DETAILS_REQUESTED", "DRAFT", "REJECTED", "ESCALATED")


def incident_titles() -> dict[str, str]:
    try:
        return {incident.incident_id: incident.title for incident in services.list_incidents()}
    except services.ServiceError:
        return {}


def latest(case: list[RCARecord]) -> RCARecord:
    """The investigation that says where the case stands: the last one."""
    return case[-1]


def matches(case: list[RCARecord], titles: dict[str, str], text: str, statuses, service_names) -> bool:
    record = latest(case)
    title = titles.get(record.incident_id, "")
    needle = text.strip().lower()
    found = (
        not needle
        or needle in record.incident_id.lower()
        or needle in title.lower()
        or any(needle in item.rca_id.lower() for item in case)
    )
    return (
        found
        and (not statuses or record.status in statuses)
        and (not service_names or record.incident_id in service_names)
    )


def search_and_filters(cases: list[list[RCARecord]], titles: dict[str, str]):
    """One search field and two filters: enough to find a case, no more."""
    services_by_incident: dict[str, str] = {}
    try:
        for incident in services.list_incidents():
            services_by_incident[incident.incident_id] = incident.service
    except services.ServiceError:
        pass

    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        search_field(t("history.search"), key=SEARCH_KEY,
                     placeholder=t("history.search_placeholder"), hide_label=True)
        with st.popover(t("filters.button"), icon=":material/filter_list:",
                        key="history-filters"):
            st.multiselect(
                t("history.filter_status"),
                options=list(STATUSES),
                format_func=badges.rca_status_label,
                key=STATUS_KEY,
            )
            st.multiselect(
                t("history.filter_service"),
                options=sorted(set(services_by_incident.values())),
                key=SERVICE_KEY,
            )
    filter_while_typing(SEARCH_KEY)

    chosen_services = set(st.session_state.get(SERVICE_KEY) or ())
    incidents_of_service = {
        incident_id for incident_id, service in services_by_incident.items()
        if service in chosen_services
    } if chosen_services else set()

    return [
        case for case in cases
        if matches(case, titles, st.session_state.get(SEARCH_KEY) or "",
                   set(st.session_state.get(STATUS_KEY) or ()), incidents_of_service)
    ]


def outcome_line(record: RCARecord) -> str:
    """One sentence for where the case stands, written for the person reading the list."""
    review = record.review
    if record.status == "FINAL" and review is not None:
        return t("review.decided_by", name=review.reviewer, date=formatting.date(review.decided_at))
    if record.status == "PENDING_REVIEW":
        return t("history.awaiting")
    if review is not None:
        return t("review.decided_by", name=review.reviewer, date=formatting.date(review.decided_at))
    return t("history.no_decision")


def case_row(case: list[RCARecord], titles: dict[str, str]) -> None:
    record = latest(case)
    title = titles.get(record.incident_id, record.incident_id)
    count = (t("history.investigations_one") if len(case) == 1
             else t("history.investigations_many", count=len(case)))

    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown(f"`{record.incident_id}` **{title}**")
            if st.button(t("history.open_case"), key=f"case-{record.case}", icon=":material/folder_open:"):
                st.query_params["case"] = record.case
                st.rerun()
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
            badges.rca_status_badge(record.status)
            st.caption(f"{count} · {t('history.started')}: {formatting.date(case[0].created_at)}")
        st.caption(outcome_line(record))


def case_list() -> None:
    try:
        cases = services.list_cases()
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return

    if not cases:
        st.info(t("history.none"), icon=":material/history:")
        st.caption(t("history.none_hint"))
        if st.button(t("home.cta"), type="primary", icon=theme.ICONS["start_rca"]):
            st.switch_page(navigation.START_RCA)
        return

    titles = incident_titles()
    visible = search_and_filters(cases, titles)
    st.caption(t("history.count", count=len(visible)))

    if not visible:
        st.info(t("history.no_matches"), icon=":material/search_off:")
        return

    for case in visible:
        case_row(case, titles)


# --------------------------------------------------------------------------------------
# One case
# --------------------------------------------------------------------------------------


def decision_line(record: RCARecord) -> None:
    """What the Technical Expert decided on this investigation, if they decided anything."""
    review = record.review
    if review is None:
        st.caption(t("case.no_review"))
        return

    st.caption(t("review.decided_by", name=review.reviewer, date=formatting.date_time(review.decided_at)))
    if review.comment:
        st.markdown(review.comment)
    checks = rca_draft.extra_checks(review)
    if checks:
        st.caption(t("review.requested_checks"))
        for item in checks:
            st.markdown(f"- {item}")


def cycle_block(record: RCARecord) -> None:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown(f"**{t('case.cycle', number=record.cycle)}** · `{record.rca_id}`")
            badges.rca_status_badge(record.status)
        st.caption(
            f"{t('history.started')}: {formatting.date_time(record.created_at)} · "
            f"{t('draft.duration')}: {formatting.seconds(record.duration_seconds)} · "
            f"{t('draft.evidence_count')}: {len(record.evidence)}"
        )
        decision_line(record)

        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
            if st.button(t("case.open_investigation"), key=f"open-inv-{record.rca_id}",
                         icon=theme.ICONS["investigation"], type="tertiary"):
                state.set_active_rca(record.rca_id)
                st.query_params.clear()
                st.query_params["rca"] = record.rca_id
                st.switch_page(navigation.INVESTIGATION)
            if record.status == "PENDING_REVIEW" and st.button(
                t("case.open_review"), key=f"open-rev-{record.rca_id}",
                icon=theme.ICONS["review"], type="tertiary",
            ):
                st.query_params.clear()
                st.query_params["rca"] = record.rca_id
                st.switch_page(navigation.REVIEW)

        with st.expander(t("case.show_analysis")):
            rca_draft.rca_draft(record)


def case_view(case_id: str) -> None:
    try:
        case = services.list_case(case_id)
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return

    if not case:
        st.info(t("case.not_found"), icon=":material/info:")
        if st.button(t("history.back_to_list"), icon=theme.ICONS["back"]):
            st.query_params.pop("case", None)
            st.rerun()
        return

    record = latest(case)
    titles = incident_titles()

    if st.button(t("history.back_to_list"), icon=theme.ICONS["back"], type="tertiary"):
        st.query_params.pop("case", None)
        st.rerun()

    st.subheader(titles.get(record.incident_id, record.incident_id))
    with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
        st.markdown(f"`{record.incident_id}`")
        badges.rca_status_badge(record.status)
    count = (t("history.investigations_one") if len(case) == 1
             else t("history.investigations_many", count=len(case)))
    st.caption(f"{count} · {t('history.started')}: {formatting.date_time(case[0].created_at)}")

    final = next((item for item in case if item.status == "FINAL"), None)
    if final is not None and final.final_root_cause:
        with st.container(border=True):
            st.markdown(f"**{t('case.final_title')}**")
            st.markdown(final.final_root_cause)
            st.caption(t("case.final_text"))

    for item in case:
        cycle_block(item)


page_header(t("history.title"), t("history.subtitle"))

case_id = st.query_params.get("case")
if case_id:
    case_view(case_id)
else:
    case_list()
