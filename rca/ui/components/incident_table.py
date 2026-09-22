"""The incident list: one row per incident, one incident selected at a time.

The table is the main way to read the incidents, so it shows only what helps to choose
one: which incident, what happened, which service, how bad it was, where it stands and
when. Severity and status keep their own colours and always carry their words.

Selecting is single by design — the investigation runs on one incident.
"""

import pandas as pd
import streamlit as st

from rca.models import Incident
from rca.ui import theme
from rca.ui.components import badges
from rca.ui.strings import t

DETAILS_CLICK_KEY = "incident_table_details_click"
DETAILS_REQUEST_KEY = "incident_details_requested_for"
# The table keeps its own selection in the browser, under its key. Clearing the selection
# in the application is not enough to empty it, so the table is drawn again under a new
# key, which is what this number counts.
TABLE_GENERATION_KEY = "incident_table_generation"

DETAILS_ICON = ":material/info:"

SEVERITIES = ("SEV-1", "SEV-2", "SEV-3", "SEV-4")
STATUSES = ("Resolved", "Closed")


def _frame(incidents: list[Incident]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "incident": [incident.incident_id for incident in incidents],
            "description": [incident.title for incident in incidents],
            "service": [incident.service for incident in incidents],
            "severity": [[badges.severity_label(incident.severity)] for incident in incidents],
            "status": [[badges.incident_status_label(incident.status)] for incident in incidents],
            "detected": [incident.detected_at for incident in incidents],
            "details": [DETAILS_ICON for _ in incidents],
        }
    )


def _column_config() -> dict:
    return {
        "incident": st.column_config.TextColumn(t("table.incident"), width=140, pinned=True),
        "description": st.column_config.TextColumn(t("table.description"), width="medium"),
        "service": st.column_config.TextColumn(t("table.service"), width=130),
        "severity": st.column_config.MultiselectColumn(
            t("table.severity"),
            width=95,
            options=[badges.severity_label(severity) for severity in SEVERITIES],
            color=[theme.SEVERITY[severity].color for severity in SEVERITIES],
        ),
        "status": st.column_config.MultiselectColumn(
            t("table.status"),
            width=105,
            options=[badges.incident_status_label(status) for status in STATUSES],
            color=[theme.INCIDENT_STATUS[status].color for status in STATUSES],
        ),
        "detected": st.column_config.DatetimeColumn(t("table.date"), width=105, format="DD MMM YYYY"),
        "details": st.column_config.ButtonColumn(
            t("table.details"),
            width=85,
            help=t("selection.view_details"),
            type="tertiary",
            key=DETAILS_CLICK_KEY,
            on_click=_details_clicked,
        ),
    }


def _details_clicked() -> None:
    """A click on a Details button: remember which incident it was for."""
    click = st.session_state.get(DETAILS_CLICK_KEY)
    shown = st.session_state.get("_incident_table_ids") or []
    if click is None:
        return
    row = click["row"] if isinstance(click, dict) else click.row
    if 0 <= row < len(shown):
        st.session_state[DETAILS_REQUEST_KEY] = shown[row]


def clear_selection() -> None:
    """Forget what the table has selected, in the table as well as in the application."""
    st.session_state[TABLE_GENERATION_KEY] = st.session_state.get(TABLE_GENERATION_KEY, 0) + 1


def requested_details() -> str | None:
    """The incident whose details were asked for, once. Cleared as it is read."""
    return st.session_state.pop(DETAILS_REQUEST_KEY, None)


def incident_table(incidents: list[Incident], *, selected_id: str | None) -> str | None:
    """Draw the table and return the incident that is selected after this run.

    The table is redrawn whenever the rows change — another page, another filter — so the
    selection it reports is compared with the selection it was given. Only a real change
    by the person changes the answer; paging away from a selected incident keeps it.
    """
    shown_ids = [incident.incident_id for incident in incidents]
    st.session_state["_incident_table_ids"] = shown_ids
    default_rows = [shown_ids.index(selected_id)] if selected_id in shown_ids else []

    event = st.dataframe(
        _frame(incidents),
        column_config=_column_config(),
        hide_index=True,
        width="stretch",
        selection_mode="single-row",
        on_select="rerun",
        selection_default={"selection": {"rows": default_rows}} if default_rows else None,
        key=f"incident_table_{st.session_state.get(TABLE_GENERATION_KEY, 0)}_{hash(tuple(shown_ids))}",
    )

    rows = list(event.selection.rows)
    if rows == default_rows:
        return selected_id
    return shown_ids[rows[0]] if rows else None
