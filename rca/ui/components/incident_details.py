"""Everything the application knows about one incident, grouped so it can be read.

Only fields that exist in the incident record are shown, plus the owner teams, which come
from the CMDB, and the analyses already made for this incident. Nothing is invented and
nothing is dumped as raw data.
"""

import streamlit as st

from rca.models import Incident
from rca.ui import formatting, services
from rca.ui.components import badges
from rca.ui.strings import t


def _field(label: str, value: str | None) -> None:
    st.caption(label)
    st.markdown(value or t("common.unknown"))


def _summary(incident: Incident) -> None:
    st.markdown(f"### {incident.title}")
    with st.container(horizontal=True, gap="small"):
        badges.severity_badge(incident.severity)
        badges.incident_status_badge(incident.status)
    st.markdown(incident.description)


def _what_happened(incident: Incident) -> None:
    if incident.symptoms:
        st.caption(t("details.symptoms"))
        for symptom in incident.symptoms:
            st.markdown(f"- {symptom}")
    if incident.initial_mitigation:
        _field(t("details.mitigation"), incident.initial_mitigation)


def _service(incident: Incident) -> None:
    st.subheader(t("details.service_context"))
    left, right = st.columns(2)
    with left:
        _field(t("common.service"), incident.service)
        _field(t("details.business_service"), incident.business_service)
    with right:
        _field(t("details.environment"), incident.environment)
        teams = services.teams_for_service(incident.service)
        _field(t("details.teams"), ", ".join(teams) if teams else None)
        if teams:
            st.caption(t("details.teams_source"))


def _timing(incident: Incident) -> None:
    st.subheader(t("details.timing"))
    detected, resolved, duration = st.columns(3)
    with detected:
        _field(t("details.detected"), formatting.date_time(incident.detected_at))
    with resolved:
        _field(t("details.resolved"), formatting.date_time(incident.resolved_at))
    with duration:
        _field(t("details.duration"), formatting.minutes(incident.duration_minutes))


def _impact(incident: Incident) -> None:
    impact = incident.impact
    if impact is None and not incident.affected_regions:
        return
    st.subheader(t("details.impact"))
    columns = st.columns(4)
    with columns[0]:
        _field(t("details.failed_transactions"), formatting.number(impact.failed_transactions) if impact else None)
    with columns[1]:
        _field(t("details.customers"), formatting.number(impact.estimated_customers_affected) if impact else None)
    with columns[2]:
        _field(t("details.error_rate"), impact.error_rate_peak if impact else None)
    with columns[3]:
        _field(t("details.regions"), ", ".join(incident.affected_regions) if incident.affected_regions else None)


def _why_an_analysis(incident: Incident) -> None:
    if not (incident.rca_reason or incident.reported_by):
        return
    st.subheader(t("details.why_rca"))
    if incident.rca_reason:
        st.markdown(incident.rca_reason)
    if incident.reported_by:
        st.caption(f"{t('details.reported_by')}: {incident.reported_by}")


def _past_analyses(incident: Incident) -> None:
    st.subheader(t("details.past_analyses"))
    try:
        records = services.rcas_for_incident(incident.incident_id)
    except services.ServiceError:
        st.caption(t("state.error_data"))
        return
    if not records:
        st.caption(t("details.no_past_analyses"))
        return
    for record in records:
        st.markdown(
            f"`{record.rca_id}` · {badges.rca_status_chip(record.status)} · "
            f"{formatting.date_time(record.created_at)}"
        )


def incident_details(incident: Incident) -> None:
    """The whole incident, in the order a person asks about it."""
    _summary(incident)
    _what_happened(incident)
    _service(incident)
    _timing(incident)
    _impact(incident)
    _why_an_analysis(incident)
    _past_analyses(incident)


@st.dialog(t("details.title"), width="large")
def incident_details_dialog(incident: Incident) -> None:
    """The same details, opened from the list without leaving it."""
    st.caption(incident.incident_id)
    incident_details(incident)
