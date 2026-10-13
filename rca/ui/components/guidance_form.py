"""The guidance for the investigation of a problem (models.InvestigationGuidance): notes, instructions or
questions, more services to search, wider windows.

Everything is optional and checked by the backend. The guidance is saved on the problem: the form shows
what was saved, and Start RCA uses what the form holds. Only what was filled in is sent, so the rules of
the investigation apply to anything left as it is.
"""

import streamlit as st

from rca.ui import services
from rca.ui.strings import t

DEFAULT_CHANGE_DAYS = 7  # the rule of rca/context.py when nothing is given
DEFAULT_LOG_HOURS = 2


def guidance_form(key: str = "guidance", initial=None, expanded: bool = False) -> dict | None:
    """The guidance as a dict for the API, or None when nothing is filled in. initial: the guidance saved on
    the problem (models.InvestigationGuidance), shown as the starting values."""
    with st.expander(t("guidance.title"), icon=":material/tune:", expanded=expanded):
        st.caption(t("guidance.hint"))
        notes = st.text_area(t("guidance.notes"), value=(initial.notes if initial else None) or "",
                             help=t("guidance.notes_help"), key=f"{key}_notes")
        instructions = st.text_area(t("guidance.instructions"), value=(initial.instructions if initial else None) or "",
                                    help=t("guidance.instructions_help"), key=f"{key}_instructions")
        try:
            options = services.cmdb_services()
        except services.ServiceError:
            options = []
        chosen = [item for item in (initial.extra_services if initial else []) if item in options]
        extra = st.multiselect(t("guidance.services"), options, default=chosen, help=t("guidance.services_help"),
                               key=f"{key}_services")
        days = st.number_input(t("guidance.change_days"), min_value=7, max_value=90,
                               value=(initial.change_window_days if initial else None) or DEFAULT_CHANGE_DAYS, step=1,
                               help=t("guidance.change_days_help"), key=f"{key}_days")
        hours = st.number_input(t("guidance.log_hours"), min_value=2, max_value=168,
                                value=(initial.log_hours_before if initial else None) or DEFAULT_LOG_HOURS, step=1,
                                help=t("guidance.log_hours_help"), key=f"{key}_hours")
    guidance = {
        "notes": notes.strip() or None,
        "instructions": instructions.strip() or None,
        "extra_services": extra,
        "change_window_days": int(days) if days != DEFAULT_CHANGE_DAYS else None,
        "log_hours_before": int(hours) if hours != DEFAULT_LOG_HOURS else None,
    }
    return guidance if any(guidance.values()) else None


def guidance_lines(guidance) -> list[str]:
    """The guidance in words, one line per value given: for the history and for a guidance that cannot change."""
    if guidance is None:
        return []
    value = guidance if isinstance(guidance, dict) else guidance.model_dump()
    lines = []
    if value.get("notes"):
        lines.append(f"{t('guidance.notes')}: {value['notes']}")
    if value.get("instructions"):
        lines.append(f"{t('guidance.instructions')}: {value['instructions']}")
    if value.get("extra_services"):
        lines.append(f"{t('guidance.services')}: {', '.join(value['extra_services'])}")
    if value.get("change_window_days"):
        lines.append(f"{t('guidance.change_days')}: {value['change_window_days']}")
    if value.get("log_hours_before"):
        lines.append(f"{t('guidance.log_hours')}: {value['log_hours_before']}")
    return lines
