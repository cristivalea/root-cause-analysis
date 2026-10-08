"""The investigation context: what is known for sure before anything is searched.

Built by code, never by a model, from the problem and its incidents (audit_rca_project.md, P.1):

- the incidents: all the incidents of the problem, in the order they happened. An incident
  that belongs to no problem is investigated alone;
- the reference incident: the most recent one;
- the services: the services of the incidents; the related services come from the CMDB;
- the log windows: one around every incident, from 2 hours before its detection to 1 hour after;
- the change window: from 7 days before the first incident to the resolution of the last one,
  so the change that introduced the problem is found, not only what changed on the last day.

Every value records where it comes from, so the expert can see what the investigation started with.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from rca import storage
from rca.models import Incident, InvestigationContext, TimeWindow
from rca.tools import find_dependencies

LOGS_BEFORE_DETECTION = timedelta(hours=2)
LOGS_AFTER_DETECTION = timedelta(hours=1)
CHANGES_BEFORE_FIRST_INCIDENT = timedelta(days=7)


def build_context(db_path: Path, incident_id: str | None = None, problem_id: str | None = None) -> tuple[InvestigationContext, list[Incident]]:
    """The context and the incidents it covers. Start from a problem, or from an incident: an incident
    attached to a problem brings the whole problem. Raises ValueError for an unknown id."""
    if problem_id is None and incident_id:
        problem_id = storage.get_problem_id_for_incident(db_path, incident_id)

    if problem_id is not None:
        problem = storage.get_problem(db_path, problem_id)
        if problem is None:
            raise ValueError(f"Problem '{problem_id}' was not found in {db_path}.")
        ids = [link.incident_id for link in problem.incidents]
        origin = f"problem {problem_id}"
    else:
        ids = [incident_id or ""]
        origin = "the incident (it belongs to no problem)"

    incidents = []
    for item_id in ids:
        incident = storage.get_incident(db_path, item_id)
        if incident is None:
            raise ValueError(f"Incident '{item_id}' was not found in {db_path}.")
        incidents.append(incident)
    incidents.sort(key=lambda item: item.detected_at)

    services = list(dict.fromkeys(item.service for item in incidents))
    related = []
    for service in services:
        related += [name for name in find_dependencies(service, db_path=db_path).related_services if name not in services]
    first, last = incidents[0], incidents[-1]

    context = InvestigationContext(
        problem_id=problem_id,
        incident_ids=[item.incident_id for item in incidents],
        reference_incident_id=last.incident_id,
        services=services,
        related_services=list(dict.fromkeys(related)),
        log_windows=[
            TimeWindow(start=item.detected_at - LOGS_BEFORE_DETECTION, end=item.detected_at + LOGS_AFTER_DETECTION,
                       incident_id=item.incident_id)
            for item in incidents
        ],
        change_window=TimeWindow(
            start=first.detected_at - CHANGES_BEFORE_FIRST_INCIDENT,
            end=max(item.resolved_at or item.detected_at for item in incidents),
        ),
        sources={
            "incidents": origin,
            "reference_incident": "rule: the most recent incident",
            "services": "the incidents",
            "related_services": "CMDB: the services the incident services depend on",
            "log_windows": "rule: 2 hours before to 1 hour after the detection of every incident",
            "change_window": "rule: 7 days before the first incident to the resolution of the last one",
        },
    )
    return context, incidents
