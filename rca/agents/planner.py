"""Investigation Planner: reads the problem and its incidents and writes the search queries.

The facts are not asked from the model. The services, the time windows and the sources come
from the investigation context, built by code (rca/context.py), and every source is always
checked. The model only writes the queries for the search in past incidents and RCAs, and
explains them. A plan without a usable query is refused with LLMOutputError, the same error as
an invalid answer, so the retry in the guardrail can handle both the same way.
"""

import json

from pydantic import BaseModel, Field

from rca.llm import LLMOutputError, ask_json, with_feedback
from rca.models import Incident, InvestigationContext, InvestigationPlan, SourceName

MAX_SEARCH_QUERIES = 5
ALL_SOURCES: list[SourceName] = ["logs", "changes", "cmdb", "historical_rcas", "historical_incidents"]

INSTRUCTIONS = f"""You are the Investigation Planner in a Root Cause Analysis application for IT incidents.
You receive a problem: one or more incidents that share the same unknown cause, and the past
incidents that look similar. The services, the time windows and the sources to check are already
fixed by the application; you do not choose them. You do not investigate and you do not guess the cause.

Write:
1. search_queries: 1 to {MAX_SEARCH_QUERIES} short queries for the search in past incidents and RCAs.
   The search compares meaning, not keywords, so write each query as a plain sentence that
   describes the symptoms, for example "payment requests fail with database connection timeouts".
   Cover the different symptoms of the incidents. Do not use query syntax such as AND, OR,
   quotes, wildcards or field:value.
2. rationale: two or three sentences explaining which symptoms the queries look for and why.

Never state or suggest a root cause, in any field. The plan says what to look for, not what happened."""


class PlannerAnswer(BaseModel):
    """What the model is asked to return."""

    search_queries: list[str] = Field(min_length=1, max_length=MAX_SEARCH_QUERIES)
    rationale: str = Field(min_length=1)


def _incident_for_prompt(incident: Incident) -> dict:
    return incident.model_dump(mode="json", exclude_none=True)


def _similar_incident_for_prompt(incident: Incident) -> dict:
    return incident.model_dump(
        mode="json",
        include={"incident_id", "title", "description", "service", "detected_at", "duration_minutes", "symptoms"},
    )


def build_user_input(context: InvestigationContext, incidents: list[Incident], similar_incidents: list[Incident]) -> str:
    return json.dumps(
        {
            "problem_id": context.problem_id,
            "incidents_of_the_problem": [_incident_for_prompt(item) for item in incidents],
            "services": context.services,
            "similar_past_incidents": [_similar_incident_for_prompt(item) for item in similar_incidents],
        },
        indent=2,
        ensure_ascii=False,
    )


def check_answer(answer: PlannerAnswer, context: InvestigationContext, incidents: list[Incident]) -> InvestigationPlan:
    """Turn the model answer into a plan, or refuse it with the list of problems.

    The service, the window and the sources of the plan are copied from the context: the service of
    the reference incident and the change window, which covers every log window too."""
    queries = [query.strip() for query in answer.search_queries if query.strip()]
    if not queries:
        raise LLMOutputError("The investigation plan was refused: search_queries must contain at least one non-empty query",
                             answer.model_dump_json())
    reference = next(item for item in incidents if item.incident_id == context.reference_incident_id)
    return InvestigationPlan(
        service=reference.service,
        related_services=context.related_services,
        window_start=min(context.change_window.start, *(window.start for window in context.log_windows)),
        window_end=max(context.change_window.end, *(window.end for window in context.log_windows)),
        sources=list(ALL_SOURCES),
        search_queries=queries,
        rationale=answer.rationale.strip(),
    )


def plan_investigation(
    context: InvestigationContext,
    incidents: list[Incident],
    similar_incidents: list[Incident],
    feedback: str | None = None,
) -> InvestigationPlan:
    """Ask the model for the search queries and return the plan after the checks.

    feedback is the reason the previous answer was refused, added on a retry.
    Raises LLMOutputError when the answer is not valid JSON, does not match the schema or has no query.
    """
    user_input = with_feedback(build_user_input(context, incidents, similar_incidents), feedback)
    answer = ask_json(INSTRUCTIONS, user_input, PlannerAnswer)
    return check_answer(answer, context, incidents)
