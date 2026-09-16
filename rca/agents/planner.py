"""Investigation Planner: reads the incident and decides what to look for.

The model proposes the service, the time window, the sources and the search queries. The code
then checks the facts it can check: the service must come from the input and the window must
contain the moment the incident was detected. A plan that fails a check is refused with
LLMOutputError, the same error as an invalid answer, so the retry in the guardrail can handle
both the same way.

The related services are not asked from the model: they come from the CMDB lookup.
"""

import json
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from rca.llm import LLMOutputError, ask_json, with_feedback
from rca.models import Incident, InvestigationPlan, SourceName

MAX_WINDOW = timedelta(days=7)
MAX_SEARCH_QUERIES = 5

INSTRUCTIONS = f"""You are the Investigation Planner in a Root Cause Analysis application for IT incidents.
You receive one incident and the past incidents that look similar to it. You decide what the
investigation should look at. You do not investigate and you do not guess the cause.

Decide:
1. service: the technical service to investigate. Use the exact name of a service that appears
   in the input, normally the service of the incident.
2. window_start and window_end: the time window to search, in UTC, ISO 8601 with a Z suffix.
   - The window must start before the incident was detected and must contain the detection time.
   - Start early enough to include recent changes and deployments that could have caused the
     failure, usually a few hours before detection.
   - A sudden failure needs a short window. A slow degradation needs a wider one.
   - The window can end when the incident was resolved.
   - The window cannot be longer than {MAX_WINDOW.days} days.
3. sources: which sources to check. Choose only the ones that can help:
   - "cmdb": the components of the service and what they depend on;
   - "changes": changes and deployments inside the window;
   - "logs": ERROR and WARN log lines inside the window;
   - "historical_rcas": root cause analyses written for past incidents;
   - "historical_incidents": past incidents with similar symptoms.
4. search_queries: 1 to {MAX_SEARCH_QUERIES} short queries for the search in past incidents and RCAs.
   The search compares meaning, not keywords, so write each query as a plain sentence that
   describes the symptoms, for example "payment requests fail with database connection timeouts".
   Do not use query syntax such as AND, OR, quotes, wildcards or field:value.
5. rationale: two or three sentences explaining why you chose this window and these sources.

Never state or suggest a root cause, in any field. The plan says where to look, not what happened."""


class PlannerAnswer(BaseModel):
    """What the model is asked to return."""

    service: str
    window_start: datetime
    window_end: datetime
    sources: list[SourceName] = Field(min_length=1)
    search_queries: list[str] = Field(min_length=1, max_length=MAX_SEARCH_QUERIES)
    rationale: str = Field(min_length=1)


def _incident_for_prompt(incident: Incident) -> dict:
    return incident.model_dump(mode="json", exclude_none=True)


def _similar_incident_for_prompt(incident: Incident) -> dict:
    return incident.model_dump(
        mode="json",
        include={"incident_id", "title", "description", "service", "detected_at", "duration_minutes", "symptoms"},
    )


def build_user_input(incident: Incident, similar_incidents: list[Incident]) -> str:
    return json.dumps(
        {
            "incident": _incident_for_prompt(incident),
            "similar_past_incidents": [_similar_incident_for_prompt(item) for item in similar_incidents],
        },
        indent=2,
        ensure_ascii=False,
    )


def _as_utc(value: datetime) -> datetime:
    """A time written without a time zone is taken as UTC, like everything in the data."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def check_answer(answer: PlannerAnswer, incident: Incident, similar_incidents: list[Incident]) -> InvestigationPlan:
    """Turn the model answer into a plan, or refuse it with the list of problems."""
    problems: list[str] = []

    known_services = {item.service.lower(): item.service for item in [incident, *similar_incidents]}
    service = known_services.get(answer.service.strip().lower())
    if service is None:
        problems.append(
            f"service '{answer.service}' does not appear in the input; use one of: {sorted(known_services.values())}"
        )

    detected_at = _as_utc(incident.detected_at)
    window_start = _as_utc(answer.window_start)
    window_end = _as_utc(answer.window_end)
    if window_start >= detected_at:
        problems.append(f"window_start must be before the detection time {detected_at.isoformat()}")
    if window_end < detected_at:
        problems.append(f"window_end must not be before the detection time {detected_at.isoformat()}")
    if window_end - window_start > MAX_WINDOW:
        problems.append(f"the window cannot be longer than {MAX_WINDOW.days} days")

    queries = [query.strip() for query in answer.search_queries if query.strip()]
    if not queries:
        problems.append("search_queries must contain at least one non-empty query")

    if problems:
        raise LLMOutputError("The investigation plan was refused: " + "; ".join(problems), answer.model_dump_json())

    return InvestigationPlan(
        service=service,
        window_start=window_start,
        window_end=window_end,
        sources=list(dict.fromkeys(answer.sources)),  # without duplicates, in the chosen order
        search_queries=queries,
        rationale=answer.rationale.strip(),
    )


def plan_investigation(
    incident: Incident,
    similar_incidents: list[Incident],
    feedback: str | None = None,
) -> InvestigationPlan:
    """Ask the model for a plan and return it after the checks.

    feedback is the reason the previous answer was refused, added on a retry.
    Raises LLMOutputError when the answer is not valid JSON, does not match the schema or fails
    a check.
    """
    user_input = with_feedback(build_user_input(incident, similar_incidents), feedback)
    answer = ask_json(INSTRUCTIONS, user_input, PlannerAnswer)
    return check_answer(answer, incident, similar_incidents)
