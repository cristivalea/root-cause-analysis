"""What the Problem Manager may add when starting an investigation (models.InvestigationGuidance).

Everything is optional and checked by the backend; only what was filled in is sent, so the rules of
the investigation apply to anything left as it is.
"""

import streamlit as st

from rca.ui import services
from rca.ui.strings import t


def guidance_form(key: str = "guidance") -> dict | None:
    """The guidance as a dict for the API, or None when nothing was changed."""
    with st.expander(t("guidance.title"), icon=":material/tune:"):
        st.caption(t("guidance.hint"))
        notes = st.text_area(t("guidance.notes"), help=t("guidance.notes_help"), key=f"{key}_notes")
        try:
            options = services.cmdb_services()
        except services.ServiceError:
            options = []
        extra = st.multiselect(t("guidance.services"), options, help=t("guidance.services_help"), key=f"{key}_services")
        days = st.number_input(t("guidance.change_days"), min_value=7, max_value=90, value=7, step=1,
                               help=t("guidance.change_days_help"), key=f"{key}_days")
        hours = st.number_input(t("guidance.log_hours"), min_value=2, max_value=168, value=2, step=1,
                                help=t("guidance.log_hours_help"), key=f"{key}_hours")
    guidance = {
        "notes": notes.strip() or None,
        "extra_services": extra,
        "change_window_days": int(days) if days != 7 else None,
        "log_hours_before": int(hours) if hours != 2 else None,
    }
    return guidance if any(guidance.values()) else None
