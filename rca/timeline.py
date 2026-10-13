"""The timeline of an investigation: the facts of the ledger on one time axis (audit P.1, P.2 step 4).

Built by code from the evidence ledger only, so it adds no fact; each moment keeps its evidence id, the
time it happened (from the source) and the time the investigation found it: it puts in order the detection of
every incident of the problem, the log patterns and the changes, and marks the first error. A change
before the first error can have caused it; a change after it cannot. This is the same rule the
confidence calculation uses (rca/confidence.py), so the expert sees why a change earned points or not.

Past RCAs and similar past incidents of other problems are not on it: they are history, not this problem.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rca.confidence import first_error_time
from rca.models import Evidence, TimelineEntry

MAX_TEXT = 160


def _short(description: str) -> str:
    first = description.split(". ")[0].strip()
    return first if len(first) <= MAX_TEXT else first[: MAX_TEXT - 3].rstrip() + "..."


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def build_timeline(evidence: list[Evidence], problem_incidents: list[str], first_detected: datetime,
                   services: list[str] | None = None) -> list[TimelineEntry]:
    """The entries in time order. problem_incidents: the incidents of the problem, whose detections are on it;
    first_detected: the detection of the first incident, used as the first error when there is no log;
    services: those of the problem, whose logs decide the first error (a dependency's logs are on the
    timeline but do not move it)."""
    first_error = first_error_time(evidence, first_detected, services)
    entries = []
    for item in evidence:
        if item.timestamp is None:
            continue
        at = _utc(item.timestamp)
        if item.type == "INCIDENT" or (item.type == "HISTORICAL_INCIDENT" and item.citation in problem_incidents):
            marker = "incident detected"
        elif item.type == "LOG":
            marker = "first error" if at == first_error else None
        elif item.type == "CHANGE":
            marker = "before the first error" if at < first_error else "after the first error"
        else:
            continue
        entries.append(TimelineEntry(at=at, evidence_id=item.evidence_id, type=item.type, citation=item.citation,
                                     what=_short(item.description), marker=marker, collected_at=item.collected_at))
    return sorted(entries, key=lambda entry: (entry.at, entry.evidence_id))


def as_lines(entries: list[TimelineEntry]) -> list[str]:
    """The timeline as short lines for the Reasoning Agent: time, evidence id, type, marker."""
    return [f"{entry.at:%Y-%m-%d %H:%M} UTC {entry.evidence_id} {entry.type}"
            + (f" ({entry.marker})" if entry.marker else "") for entry in entries]
