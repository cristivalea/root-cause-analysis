"""Start an RCA: find the incident to investigate, select one, and begin.

The screen is built around one decision, so it is laid out in the order that decision is
made: search for the incident, see what is selected and what the action will do, then the
list itself. The action stays disabled until exactly one incident is chosen.

Only incidents that need a root cause analysis are listed. Incidents are data from the
wider ITSM environment: this application reads them and never creates, edits or deletes
them.
"""

import streamlit as st

from rca.ui import filtering, navigation, services, state, theme
from rca.ui.components import filters as filter_controls
from rca.ui.components import incident_table as table
from rca.ui.components.incident_card import incident_summary
from rca.ui.components.incident_details import incident_details_dialog
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

PAGE_SIZE = 10
PAGE_KEY = "incidents_page"
FILTER_SIGNATURE_KEY = "incidents_filter_signature"


def load_incidents():
    """Every incident that needs an analysis, or an error state and nothing else."""
    try:
        with st.spinner(t("state.loading_incidents")):
            return [incident for incident in services.list_incidents() if incident.rca_required]
    except services.ServiceError as error:
        st.error(t("state.error_data"), icon=theme.ICONS["error"])
        st.caption(t("state.error_detail", detail=error))
        st.stop()


def current_page(total_pages: int) -> int:
    """The page being shown. A change of filters always brings the person back to the first."""
    page = int(st.session_state.get(PAGE_KEY, 1))
    return min(max(page, 1), max(total_pages, 1))


def reset_page_when_filters_change(filters: filtering.IncidentFilters) -> None:
    signature = repr(filters)
    if st.session_state.get(FILTER_SIGNATURE_KEY) != signature:
        st.session_state[FILTER_SIGNATURE_KEY] = signature
        st.session_state[PAGE_KEY] = 1


def pager(total: int, page: int, total_pages: int, first: int, last: int) -> None:
    """How much of the list is on screen, and the way to the rest of it."""
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        st.caption(t("list.showing", first=first, last=last, total=total))
        if total_pages > 1:
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                if st.button(t("list.previous"), icon=":material/chevron_left:", disabled=page <= 1):
                    st.session_state[PAGE_KEY] = page - 1
                    st.rerun()
                st.caption(t("list.page", page=page, pages=total_pages))
                if st.button(t("list.next"), icon=":material/chevron_right:", disabled=page >= total_pages):
                    st.session_state[PAGE_KEY] = page + 1
                    st.rerun()


def selection_area(incident) -> None:
    """What is selected and what happens next: the compact card and the one action."""
    with st.container(border=True):
        if incident is None:
            st.caption(t("list.select_hint"))
            st.button(
                t("selection.analyze"),
                type="primary",
                icon=theme.ICONS["investigation"],
                disabled=True,
                help=t("selection.analyze_help"),
            )
            return

        st.caption(t("selection.title"))
        incident_summary(incident)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            if st.button(
                t("selection.analyze"),
                type="primary",
                icon=theme.ICONS["investigation"],
                help=t("selection.analyze_help"),
            ):
                state.request_investigation()
                state.set_active_rca(None)
                st.switch_page(navigation.INVESTIGATION)
            if st.button(t("selection.view_details"), icon=":material/info:"):
                incident_details_dialog(incident)
            if st.button(t("selection.clear"), type="tertiary", icon=":material/close:"):
                state.select_incident(None)
                st.rerun()


page_header(t("start_rca.title"), t("start_rca.subtitle"), back_to=navigation.HOME)

incidents = load_incidents()
if not incidents:
    st.info(t("state.no_incidents"), icon=theme.ICONS["scaffold"])
    st.stop()

filters = filter_controls.search_and_filters(incidents)
reset_page_when_filters_change(filters)
visible = filtering.apply(incidents, filters)

# The selected incident is shown here, above the list, but it is only known once the table
# below has reported what the person clicked.
selection = st.container()

if not visible:
    st.info(t("state.no_matches"), icon=":material/search_off:")
    if st.button(t("filters.show_all"), icon=":material/refresh:"):
        filter_controls.clear_all()
else:
    total_pages = max((len(visible) + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = current_page(total_pages)
    first = (page - 1) * PAGE_SIZE
    rows = visible[first:first + PAGE_SIZE]

    chosen = table.incident_table(rows, selected_id=state.selected_incident_id())
    if chosen != state.selected_incident_id():
        state.select_incident(chosen)
        st.rerun()

    pager(len(visible), page, total_pages, first + 1, first + len(rows))
    st.caption(t("list.only_rca_required"))

selected_id = state.selected_incident_id()
selected_incident = next((item for item in incidents if item.incident_id == selected_id), None)
with selection:
    selection_area(selected_incident)

asked_about = table.requested_details()
if asked_about:
    incident = next((item for item in incidents if item.incident_id == asked_about), None)
    if incident is not None:
        incident_details_dialog(incident)
