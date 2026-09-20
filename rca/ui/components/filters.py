"""Search and filters for the incident list.

Search is always visible because it is the fastest way in. The filters live behind one
button, so the screen stays calm, and whatever is active is shown as a chip that can be
removed on its own.
"""

from datetime import date as date_type

import streamlit as st

from rca.models import Incident
from rca.ui.components import badges
from rca.ui.filtering import IncidentFilters
from rca.ui.strings import t

TEXT_KEY = "incidents_search"
SEVERITY_KEY = "incidents_severity"
SERVICE_KEY = "incidents_service"
STATUS_KEY = "incidents_status"
DATES_KEY = "incidents_dates"

SEVERITIES = ("SEV-1", "SEV-2", "SEV-3", "SEV-4")
STATUSES = ("Resolved", "Closed")


def _chosen_dates() -> tuple[date_type | None, date_type | None]:
    """The date filter, which is empty, half chosen while the person picks, or a range."""
    chosen = st.session_state.get(DATES_KEY)
    if isinstance(chosen, date_type):
        return chosen, chosen
    dates = tuple(chosen or ())
    return (dates[0] if dates else None), (dates[1] if len(dates) > 1 else None)


def current_filters() -> IncidentFilters:
    """What the controls are asking for right now."""
    date_from, date_to = _chosen_dates()
    return IncidentFilters(
        text=st.session_state.get(TEXT_KEY) or "",
        severities=tuple(st.session_state.get(SEVERITY_KEY) or ()),
        services=tuple(st.session_state.get(SERVICE_KEY) or ()),
        statuses=tuple(st.session_state.get(STATUS_KEY) or ()),
        date_from=date_from,
        date_to=date_to,
    )


def _remove_value(key: str, value: str) -> None:
    st.session_state[key] = [item for item in st.session_state.get(key, []) if item != value]
    st.rerun()


def _clear_dates() -> None:
    st.session_state.pop(DATES_KEY, None)
    st.rerun()


def clear_all() -> None:
    """Back to the whole list."""
    st.session_state[TEXT_KEY] = ""
    st.session_state[SEVERITY_KEY] = []
    st.session_state[SERVICE_KEY] = []
    st.session_state[STATUS_KEY] = []
    st.session_state.pop(DATES_KEY, None)
    st.rerun()


def _panel(incidents: list[Incident]) -> None:
    """What sits inside the Filters button: four filters, nothing else."""
    st.multiselect(
        t("filters.severity"),
        options=list(SEVERITIES),
        format_func=badges.severity_label,
        key=SEVERITY_KEY,
    )
    st.multiselect(
        t("filters.service"),
        options=sorted({incident.service for incident in incidents}),
        key=SERVICE_KEY,
    )
    st.multiselect(
        t("filters.status"),
        options=list(STATUSES),
        format_func=badges.incident_status_label,
        key=STATUS_KEY,
    )
    detected = [incident.detected_at.date() for incident in incidents]
    st.date_input(
        t("filters.date"),
        value=(),  # an empty range: the filter starts off, not on today
        min_value=min(detected) if detected else None,
        max_value=max(detected) if detected else None,
        key=DATES_KEY,
    )


def _chips(filters: IncidentFilters) -> None:
    """One removable chip per active filter, so it is clear what is narrowing the list."""
    if not filters.is_active:
        return
    with st.container(horizontal=True, gap="small", wrap=True):
        for severity in filters.severities:
            label = f"{t('filters.severity')}: {badges.severity_label(severity)}"
            if st.button(label, key=f"chip-sev-{severity}", icon=":material/close:", help=t("filters.remove")):
                _remove_value(SEVERITY_KEY, severity)
        for service in filters.services:
            label = f"{t('filters.service')}: {service}"
            if st.button(label, key=f"chip-svc-{service}", icon=":material/close:", help=t("filters.remove")):
                _remove_value(SERVICE_KEY, service)
        for status in filters.statuses:
            label = f"{t('filters.status')}: {badges.incident_status_label(status)}"
            if st.button(label, key=f"chip-sta-{status}", icon=":material/close:", help=t("filters.remove")):
                _remove_value(STATUS_KEY, status)
        if filters.date_from or filters.date_to:
            parts = []
            if filters.date_from:
                parts.append(t("filters.chip_date_from", date=filters.date_from.strftime("%d %b %Y")))
            if filters.date_to:
                parts.append(t("filters.chip_date_to", date=filters.date_to.strftime("%d %b %Y")))
            label = t("filters.chip_date", range=" ".join(parts))
            if st.button(label, key="chip-dates", icon=":material/close:", help=t("filters.remove")):
                _clear_dates()
        if st.button(t("filters.clear_all"), key="chip-clear-all", type="tertiary"):
            clear_all()


def _active_count(filters: IncidentFilters) -> int:
    count = len(filters.severities) + len(filters.services) + len(filters.statuses)
    return count + (1 if (filters.date_from or filters.date_to) else 0)


def search_and_filters(incidents: list[Incident]) -> IncidentFilters:
    """The search field, the Filters button and the active chips. Returns what to show."""
    count = _active_count(current_filters())
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        st.text_input(
            t("search.label"),
            placeholder=t("search.placeholder"),
            key=TEXT_KEY,
            icon=":material/search:",
            width="stretch",
        )
        label = t("filters.active", count=count) if count else t("filters.button")
        with st.popover(label, icon=":material/filter_list:"):
            _panel(incidents)

    filters = current_filters()
    _chips(filters)
    return filters
