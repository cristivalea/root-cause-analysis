"""The only place the interface reads or writes application data.

Every screen calls these functions; no page imports `rca.storage`, `rca.store` or
`rca.pipeline` directly. That keeps the pages free of data handling, and it is what makes
the planned move to a FastAPI backend a change to this one module instead of a rewrite of
every screen.

The functions return the application's own models (`Incident`, `RCARecord`), which are the
same objects an API would serialise, so nothing here invents a second shape for the data.
"""

from collections.abc import Callable

import streamlit as st

from rca import storage, store
from rca.config import DB_PATH
from rca.models import Incident, InvestigationStep, RCARecord, RCAStatus

INCIDENT_CACHE_SECONDS = 300


class ServiceError(Exception):
    """The data could not be read or written. Screens turn this into an error state."""


# --------------------------------------------------------------------------------------
# Incidents — the ITSM data the investigation starts from. Read only, by design.
# --------------------------------------------------------------------------------------


@st.cache_data(ttl=INCIDENT_CACHE_SECONDS, show_spinner=False)
def list_incidents() -> list[Incident]:
    """Every incident, newest first. Incidents arrive from outside; the app never edits them."""
    try:
        incidents = storage.list_incidents(DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc
    return sorted(incidents, key=lambda incident: incident.detected_at, reverse=True)


def get_incident(incident_id: str) -> Incident | None:
    try:
        return storage.get_incident(DB_PATH, incident_id)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


@st.cache_data(ttl=INCIDENT_CACHE_SECONDS, show_spinner=False)
def services() -> list[str]:
    """The services that appear in the incidents, for the filters."""
    return sorted({incident.service for incident in list_incidents()})


@st.cache_data(ttl=INCIDENT_CACHE_SECONDS, show_spinner=False)
def teams_for_service(service: str) -> list[str]:
    """The teams that own the components of a service, read from the CMDB.

    The incident itself does not record a team, so this is derived rather than invented.
    """
    try:
        items = storage.get_config_items_for_service(DB_PATH, service)
    except Exception:
        return []
    return sorted({item.owner_team for item in items})


def refresh_incidents() -> None:
    """Forget the cached incidents, after the source data changed."""
    list_incidents.clear()
    services.clear()
    teams_for_service.clear()


# --------------------------------------------------------------------------------------
# RCA records — what the investigation produces and the expert decides on.
# --------------------------------------------------------------------------------------


def list_rcas(status: RCAStatus | None = None) -> list[RCARecord]:
    """The stored RCAs, newest first. Not cached: the review screens must see every change."""
    try:
        return store.list_rcas(status=status, db_path=DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


def get_rca(rca_id: str) -> RCARecord | None:
    try:
        return store.get_rca(rca_id, db_path=DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


def rcas_for_incident(incident_id: str) -> list[RCARecord]:
    """Every analysis made for one incident, newest first."""
    return [record for record in list_rcas() if record.incident_id == incident_id]


def submit_for_review(rca_id: str) -> RCARecord:
    """Send a finished draft to the Technical Expert."""
    try:
        return store.submit_for_review(rca_id, db_path=DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


def apply_review(
    rca_id: str,
    reviewer: str,
    decision: str,
    comment: str,
    hypothesis_id: str | None = None,
    requested_checks: list[str] | None = None,
) -> RCARecord:
    """Record the Technical Expert's decision on an analysis."""
    try:
        return store.apply_review(
            rca_id, reviewer, decision, comment, hypothesis_id,
            db_path=DB_PATH, requested_checks=requested_checks,
        )
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


def list_case(case_id: str) -> list[RCARecord]:
    """Every analysis of one case, oldest first."""
    try:
        return store.list_case(case_id, db_path=DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


def list_cases() -> list[list[RCARecord]]:
    """The cases, newest first, each as its list of analyses."""
    try:
        return store.list_cases(db_path=DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


def link_to_case(previous_rca_id: str, new_rca_id: str) -> RCARecord:
    """Make a new analysis the next cycle of the case the previous one belongs to."""
    try:
        return store.start_next_cycle(previous_rca_id, new_rca_id, db_path=DB_PATH)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc


# --------------------------------------------------------------------------------------
# The investigation itself.
# --------------------------------------------------------------------------------------


def start_investigation(
    incident_id: str,
    owner: str,
    on_step: Callable[[InvestigationStep], None] | None = None,
) -> RCARecord:
    """Run the whole investigation for one incident and return the analysis it saved.

    `on_step` receives every step as soon as it finishes, which is how the investigation
    screen shows the work while it happens.
    """
    from rca.pipeline import run_investigation  # imported late: it loads the agents

    try:
        return run_investigation(incident_id, owner=owner, db_path=DB_PATH, on_step=on_step)
    except Exception as exc:
        raise ServiceError(str(exc)) from exc
