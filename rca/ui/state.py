"""What the interface remembers between reruns, and who is using it.

There is no login in this application. The person says which role they are working in, and
the interface follows it: the Problem Manager starts investigations, the Technical Expert
reviews them. This is a convention that shapes the interface, not a security boundary.
"""

from typing import Literal

import streamlit as st

from rca.ui.strings import t

Role = Literal["problem_manager", "technical_expert"]

PROBLEM_MANAGER: Role = "problem_manager"
TECHNICAL_EXPERT: Role = "technical_expert"
ROLES: tuple[Role, ...] = (PROBLEM_MANAGER, TECHNICAL_EXPERT)

# Session keys, named once so no screen invents a second spelling.
#
# The role is kept under our own key, not under the key of the selector widget. Streamlit
# drops widget state when the widget is not part of a run, which happens while moving from
# one page to another; a role that lived in the widget key was lost on every page switch.
ROLE_KEY = "role"
ROLE_WIDGET_KEY = "role_selector"
SELECTED_INCIDENT_KEY = "selected_incident_id"
ACTIVE_RCA_KEY = "active_rca_id"
RUN_REQUEST_KEY = "investigation_requested"
RUN_ERROR_KEY = "investigation_error"


def initialise() -> None:
    """Set the defaults once per session. Called by the entry point before anything else."""
    st.session_state.setdefault(ROLE_KEY, PROBLEM_MANAGER)


def current_role() -> Role:
    """The role in use. The selector can be cleared, which means back to the default."""
    return st.session_state.get(ROLE_KEY) or PROBLEM_MANAGER


def is_technical_expert() -> bool:
    return current_role() == TECHNICAL_EXPERT


def role_widget_key() -> str:
    """The key of the role selector, which carries the role in it.

    The browser keeps the value of a widget by its key. If the role changes anywhere other
    than in the selector itself, the selector has to be a new widget, or the browser sends
    the old role back on the next click and undoes the change.
    """
    return f"{ROLE_WIDGET_KEY}:{current_role()}"


def request_role(role: Role) -> None:
    """Change the role from inside a page. The selector follows on the next run."""
    st.session_state[ROLE_KEY] = role


def apply_role_selection(widget_key: str) -> None:
    """Keep the chosen role: the selector only reports it, the application stores it."""
    st.session_state[ROLE_KEY] = st.session_state.get(widget_key) or PROBLEM_MANAGER


def role_name(role: Role) -> str:
    """The name of a role as the user reads it."""
    return t(f"role.{role}")


def selected_incident_id() -> str | None:
    return st.session_state.get(SELECTED_INCIDENT_KEY)


def select_incident(incident_id: str | None) -> None:
    st.session_state[SELECTED_INCIDENT_KEY] = incident_id


def active_rca_id() -> str | None:
    """The RCA the investigation and review screens are working on."""
    return st.session_state.get(ACTIVE_RCA_KEY)


def set_active_rca(rca_id: str | None) -> None:
    st.session_state[ACTIVE_RCA_KEY] = rca_id


def request_investigation() -> None:
    """Ask for an investigation to run. The investigation screen picks this up once."""
    st.session_state[RUN_REQUEST_KEY] = True


def take_investigation_request() -> bool:
    """True once, for the screen that runs the investigation."""
    return bool(st.session_state.pop(RUN_REQUEST_KEY, False))


def investigation_error() -> str | None:
    return st.session_state.get(RUN_ERROR_KEY)


def set_investigation_error(message: str | None) -> None:
    if message is None:
        st.session_state.pop(RUN_ERROR_KEY, None)
    else:
        st.session_state[RUN_ERROR_KEY] = message
