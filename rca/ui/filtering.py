"""Finding an incident in the list: the search text and the filters.

This module only decides which incidents match. It draws nothing, so the same rules can be
tested on their own and reused when the interface moves to another framework.
"""

from dataclasses import dataclass, replace
from datetime import date

from rca.models import Incident


@dataclass(frozen=True)
class IncidentFilters:
    """What the person is looking for. Empty means "everything"."""

    text: str = ""
    severities: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None

    @property
    def is_active(self) -> bool:
        return bool(self.text or self.severities or self.services or self.statuses
                    or self.date_from or self.date_to)

    def without(self, field: str) -> "IncidentFilters":
        """The same filters with one of them removed, for the "remove" on a filter chip."""
        empty = {"text": "", "severities": (), "services": (), "statuses": (),
                 "date_from": None, "date_to": None}
        if field == "date":
            return replace(self, date_from=None, date_to=None)
        return replace(self, **{field: empty[field]})

    def without_value(self, field: str, value: str) -> "IncidentFilters":
        """The same filters with one chosen value removed from a multiple-choice filter."""
        kept = tuple(item for item in getattr(self, field) if item != value)
        return replace(self, **{field: kept})


def matches_text(incident: Incident, text: str) -> bool:
    """Search covers the incident id and the title, which is what people have at hand."""
    needle = text.strip().lower()
    return not needle or needle in incident.incident_id.lower() or needle in incident.title.lower()


def matches(incident: Incident, filters: IncidentFilters) -> bool:
    detected = incident.detected_at.date()
    return (
        matches_text(incident, filters.text)
        and (not filters.severities or incident.severity in filters.severities)
        and (not filters.services or incident.service in filters.services)
        and (not filters.statuses or incident.status in filters.statuses)
        and (filters.date_from is None or detected >= filters.date_from)
        and (filters.date_to is None or detected <= filters.date_to)
    )


def apply(incidents: list[Incident], filters: IncidentFilters) -> list[Incident]:
    return [incident for incident in incidents if matches(incident, filters)]
