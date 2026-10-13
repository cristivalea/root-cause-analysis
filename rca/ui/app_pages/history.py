"""RCA history: every RCA of every problem, from the moment it starts, and everything that happened to it.

An RCA investigates one problem. Each run of the investigation is a revision of it (RCA-…-R1, -R2, …),
saved and never changed: a draft sent back for more details, or a run that failed, stays next to the
revision that followed it, with the decision taken on it. The list shows one card per RCA, listed as
soon as it starts; the RCA itself shows the history of its status and every revision, with its inputs,
its analysis, its timeline, its diagrams and its steps.
"""

import streamlit as st

from rca.models import RCA, RCARecord
from rca.ui import formatting, navigation, services, state, theme
from rca.ui.components import badges, rca_draft
from rca.ui.components.cause_diagram import cause_diagram
from rca.ui.components.guidance_form import guidance_lines
from rca.ui.components.investigation_timeline import timeline
from rca.ui.components.page_header import page_header
from rca.ui.components.rca_diagram import rca_diagram
from rca.ui.components.search_box import filter_while_typing, search_field
from rca.ui.components.timeline_view import timeline_view
from rca.ui.strings import t, t_or_value

SEARCH_KEY = "history_search"
STATUS_KEY = "history_status"
SERVICE_KEY = "history_service"

STATUSES = ("DRAFT", "AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS", "VALIDATED", "REJECTED", "FAILED",
            "ESCALATED_MANUAL")


# --------------------------------------------------------------------------------------
# The list
# --------------------------------------------------------------------------------------


def matches(rca: RCA, revisions: list[RCARecord], text: str, statuses: set, problems_of_service: set) -> bool:
    needle = text.strip().lower()
    incidents = {item for record in revisions for item in ([record.incident_id] + (
        record.context.incident_ids if record.context else []))}
    found = not needle or any(needle in value.lower() for value in [
        rca.rca_id, rca.problem_id, rca.title, *(record.revision_id for record in revisions), *incidents])
    return (found and (not statuses or rca.status in statuses)
            and (not problems_of_service or rca.problem_id in problems_of_service))


def search_and_filters(rcas: list[RCA], revisions: dict[str, list[RCARecord]], services_of: dict[str, list[str]]) -> list[RCA]:
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        search_field(t("history.search"), key=SEARCH_KEY, placeholder=t("history.search_placeholder"), hide_label=True)
        with st.popover(t("filters.button"), icon=":material/filter_list:", key="history-filters"):
            st.multiselect(t("history.filter_status"), options=list(STATUSES), format_func=badges.rca_status_label,
                           key=STATUS_KEY)
            st.multiselect(t("history.filter_service"),
                           options=sorted({name for names in services_of.values() for name in names}), key=SERVICE_KEY)
    filter_while_typing(SEARCH_KEY)
    chosen = set(st.session_state.get(SERVICE_KEY) or ())
    problems_of_service = {problem_id for problem_id, names in services_of.items() if chosen & set(names)} if chosen else set()
    return [rca for rca in rcas
            if matches(rca, revisions.get(rca.rca_id, []), st.session_state.get(SEARCH_KEY) or "",
                       set(st.session_state.get(STATUS_KEY) or ()), problems_of_service)]


def outcome_line(rca: RCA, latest: RCARecord | None) -> str:
    """Where the RCA stands, for the person reading the list."""
    if latest is not None and latest.run_status == "RUNNING":
        return t("history.running", revision=latest.revision)
    if rca.status == "AWAITING_TECHNICAL_REVIEW":
        return t("history.awaiting")
    review = latest.review if latest else None
    if review is not None:
        return t("history.decision_line", decision=t_or_value(f"decision.{review.decision}", review.decision),
                 name=review.reviewer, date=formatting.date(review.decided_at))
    return t("history.no_decision")


def rca_card(rca: RCA, revisions: list[RCARecord]) -> None:
    latest = revisions[-1] if revisions else None
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown(f"`{rca.rca_id}` · `{rca.problem_id}` **{rca.title}**")
            if st.button(t("history.open_case"), key=f"case-{rca.rca_id}", icon=":material/folder_open:"):
                st.query_params["case"] = rca.rca_id
                st.rerun()
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
            badges.rca_status_badge(rca.status)
            count = t("history.revisions_one") if rca.revisions == 1 else t("history.revisions_many", count=rca.revisions)
            st.caption(f"{count} · {t('history.started')}: {formatting.date(rca.created_at)} · "
                       f"{t('history.updated')}: {formatting.date_time(rca.updated_at)}",
                       help=t("history.revisions_help"))
        st.caption(outcome_line(rca, latest))


def rca_list() -> None:
    try:
        rcas = services.list_rca_summaries()
        revisions = {case[0].rca_id: case for case in services.list_cases() if case}
        services_of = {problem.problem_id: problem.services for problem in services.list_problems()}
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return
    if not rcas:
        st.info(t("history.none"), icon=":material/history:")
        st.caption(t("history.none_hint"))
        if st.button(t("history.to_problems"), type="primary", icon=theme.ICONS["problems"]):
            st.switch_page(navigation.PROBLEMS)
        return
    visible = search_and_filters(rcas, revisions, services_of)
    st.caption(t("history.count", count=len(visible)))
    if not visible:
        st.info(t("history.no_matches"), icon=":material/search_off:")
        return
    for rca in visible:
        rca_card(rca, revisions.get(rca.rca_id, []))


# --------------------------------------------------------------------------------------
# One RCA
# --------------------------------------------------------------------------------------


def decision_line(record: RCARecord) -> None:
    """What the Technical Expert decided on this revision, if anything."""
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


def inputs(record: RCARecord) -> None:
    """What this run was given: the guidance of the Problem Manager (notes, instructions, more services, wider
    windows), the request of the expert and what earlier RCAs concluded."""
    context = record.context
    given = [(key, value) for key, value in (
        ("case.notes", context.notes if context else None),
        ("case.instructions", context.instructions if context else None),
        ("case.expert_request", context.expert_request if context else None),
    ) if value]
    if record.guidance is not None:
        extra = [line for line in guidance_lines(record.guidance)
                 if not line.startswith((t("guidance.notes"), t("guidance.instructions")))]
        if extra:
            given.append(("case.searches", "  \n".join(extra)))
    if context and context.previous_conclusions:
        given.append(("case.previous_conclusions", "\n".join(f"- {item}" for item in context.previous_conclusions)))
    if not given:
        st.caption(t("case.no_inputs"))
        return
    for key, value in given:
        st.caption(t(key))
        st.markdown(value)


def guardrail_line(record: RCARecord) -> None:
    """The last decision of the guardrail on this run: accepted, or what it refused."""
    checks = [step for step in record.trace if step.name == "guardrail"]
    if not checks:
        st.caption(t("case.no_guardrail"))
        return
    last = checks[-1]
    st.markdown(last.summary)
    for problem in (last.details or {}).get("problems", []):
        st.markdown(f"- {problem}")
    for warning in (last.details or {}).get("warnings", []):
        st.markdown(f"- {warning}")


def revision_block(record: RCARecord, problem_title: str) -> None:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown(f"**{t('case.cycle', number=record.revision)}** · `{record.revision_id}`")
            with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
                if record.run_status != "COMPLETED":
                    st.badge(t(f"run_status.{record.run_status}"), color="blue" if record.run_status == "RUNNING" else "red")
                badges.rca_status_badge(record.status)
        st.caption(f"{t('history.started')}: {formatting.date_time(record.created_at)} · "
                   f"{t('draft.duration')}: {formatting.seconds(record.duration_seconds)} · "
                   f"{t('draft.evidence_count')}: {len(record.evidence)}")
        if record.error:
            st.error(record.error, icon=theme.ICONS["error"])
        decision_line(record)
        with st.container(horizontal=True, gap="small"):
            if st.button(t("case.open_investigation"), key=f"open-inv-{record.revision_id}",
                         icon=theme.ICONS["investigation"], type="tertiary"):
                state.set_active_rca(record.revision_id)  # this revision, not only the latest one
                st.query_params.clear()
                st.query_params["rca"] = record.revision_id
                st.switch_page(navigation.INVESTIGATION)
        with st.expander(t("case.show_analysis")):
            tabs = st.tabs([t("case.tab_inputs"), t("case.tab_analysis"), t("case.tab_timeline"),
                            t("case.tab_evidence_map"), t("case.tab_causal"), t("case.tab_checks"), t("case.tab_steps")])
            with tabs[0]:
                inputs(record)
            with tabs[1]:
                rca_draft.rca_draft(record)
            with tabs[2]:
                timeline_view(record) if record.timeline else st.caption(t("case.no_timeline"))
            with tabs[3]:
                cause_diagram(record, problem_title)
            with tabs[4]:
                rca_diagram(record, problem_title)
            with tabs[5]:
                guardrail_line(record)
            with tabs[6]:
                timeline(list(record.trace), running=record.run_status == "RUNNING", failed=record.run_status == "FAILED",
                         plan=record.plan, current=record.current_step)


def status_history(rca_id: str) -> None:
    """Every change of the status of the RCA, the decisions of the expert with their comments."""
    try:
        changes = services.rca_history(rca_id)["history"]
    except services.ServiceError:
        return
    with st.expander(t("case.status_history", count=len(changes)), icon=theme.ICONS["history"]):
        for change in changes:
            before = t_or_value(f"rca_status.{change.from_status}", change.from_status) if change.from_status else "—"
            after = t_or_value(f"rca_status.{change.to_status}", change.to_status)
            line = t("case.change_line", date=formatting.date_time(change.at), name=change.by, before=before, after=after)
            st.markdown(line + (f" — {change.comment}" if change.comment else "")
                        + (f" {t('event.migrated')}" if change.details.get("migrated") else ""))


def rca_view(rca_id: str) -> None:
    if st.button(t("history.back_to_list"), icon=theme.ICONS["back"], type="tertiary"):
        st.query_params.pop("case", None)
        st.rerun()
    try:
        revisions = services.list_case(rca_id)
        summary = next((item for item in services.list_rca_summaries() if item.rca_id == rca_id), None)
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        return
    if not revisions or summary is None:
        st.info(t("case.not_found"), icon=":material/info:")
        return

    st.subheader(summary.title)
    with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
        st.markdown(f"`{summary.rca_id}`")
        if st.button(summary.problem_id, key="open-problem", icon=theme.ICONS["problems"], type="tertiary",
                     help=t("case.open_problem")):
            st.switch_page(navigation.PROBLEMS, query_params={"problem": summary.problem_id})
        badges.rca_status_badge(summary.status)
    count = t("history.revisions_one") if summary.revisions == 1 else t("history.revisions_many", count=summary.revisions)
    st.caption(f"{count} · {t('case.decisions', count=summary.review_rounds)} · "
               f"{t('history.started')}: {formatting.date_time(summary.created_at)} · "
               f"{t('history.updated')}: {formatting.date_time(summary.updated_at)}", help=t("history.revisions_help"))

    final = next((item for item in revisions if item.status == "VALIDATED"), None)
    if final is not None and final.final_root_cause:
        with st.container(border=True):
            st.markdown(f"**{t('case.final_title')}**")
            st.markdown(final.final_root_cause)
            st.caption(t("case.final_text"))

    status_history(rca_id)
    for record in reversed(revisions):  # the latest revision first
        revision_block(record, summary.title)


page_header(t("history.title"), t("history.subtitle"))

case_id = st.query_params.get("case")
if case_id:
    rca_view(case_id)
else:
    rca_list()
