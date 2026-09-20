"""The compact picture of one incident: enough context, never the whole record.

Used where an incident has to be recognised rather than studied — under the list once it
is selected, and beside the investigation while it runs.
"""

import streamlit as st

from rca.models import Incident
from rca.ui import formatting
from rca.ui.components import badges
from rca.ui.strings import t


def incident_summary(incident: Incident) -> None:
    """Id and title, the two badges, then service, day and how long it lasted."""
    st.markdown(f"`{incident.incident_id}` **{incident.title}**")
    with st.container(horizontal=True, gap="small"):
        badges.severity_badge(incident.severity)
        badges.incident_status_badge(incident.status)
    facts = [
        f"{t('common.service')}: {incident.service}",
        f"{t('details.detected')}: {formatting.date(incident.detected_at)}",
        f"{t('common.duration')}: {formatting.minutes(incident.duration_minutes)}",
    ]
    st.caption(" · ".join(facts))
