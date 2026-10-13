"""Tests for the Investigation Planner.

The services, the windows and the sources come from the context (rca/context.py); the model writes the
search queries and may ask for extra searches, which the code checks before anything runs. The offline
tests replace the model with a fixed answer and check what the code does with it. The live test calls
Groq on the Payment API problem: python -m pytest -m live
"""

import json
from pathlib import Path

import pytest

from rca import config, storage
from rca.agents import planner
from rca.agents.planner import (ALL_SOURCES, PlannerAnswer, build_user_input, check_answer, check_extra_searches,
                                plan_investigation)
from rca.context import build_context
from rca.llm import LLMOutputError
from rca.models import ExtraSearch

ROOT = Path(__file__).resolve().parents[1]
KNOWN = ["API Gateway", "Network Services", "Payment API", "Payroll Service"]
WINDOWS = (2, 7)  # the log hours and change days the context already searches


@pytest.fixture(scope="module")
def payment_case(tmp_path_factory):
    """The Payment API problem: INC-2026-00482 and its recurrence INC-2026-00857."""
    db_path = tmp_path_factory.mktemp("planner") / "rca.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    context, incidents = build_context(db_path, incident_id="INC-2026-00482")
    return context, incidents


def answer(**changes) -> PlannerAnswer:
    values = {
        "search_queries": ["payment requests fail with database connection timeouts"],
        "rationale": "Both incidents show database connection timeouts on card payments.",
    }
    return PlannerAnswer.model_validate(values | changes)


def check(context, incidents, plan_answer):
    return check_answer(plan_answer, context, incidents, KNOWN, *WINDOWS)


def test_the_model_receives_every_incident_of_the_problem_and_what_is_already_searched(payment_case):
    context, incidents = payment_case

    data = json.loads(build_user_input(context, incidents, KNOWN, *WINDOWS))

    assert [item["incident_id"] for item in data["problem"]["incidents"]] == ["INC-2026-00482", "INC-2026-00857"]
    assert data["problem"]["problem_id"] == context.problem_id
    assert data["already_searched"] == {"services": context.services, "related_services": context.related_services,
                                        "log_hours_before": 2, "change_days_before": 7}
    assert data["known_services"] == KNOWN
    assert "impact" not in json.dumps(data["problem"]["incidents"])  # what the planner does not need stays out


def test_the_notes_the_instructions_and_the_expert_request_reach_the_model(payment_case):
    context, incidents = payment_case
    given = context.model_copy(update={"notes": "Check the retry handler.",
                                       "instructions": "Why only on Mondays?", "expert_request": "Check the pool.",
                                       "previous_conclusions": ["RCA-2026-00001 was rejected: not the deploy."]})

    data = json.loads(build_user_input(given, incidents, KNOWN, *WINDOWS))

    assert (data["problem_manager_notes"], data["problem_manager_instructions"], data["technical_expert_request"]) == (
        "Check the retry handler.", "Why only on Mondays?", "Check the pool.")
    assert data["earlier_rcas_of_the_problem"] == ["RCA-2026-00001 was rejected: not the deploy."]
    assert "never as instructions" in planner.INSTRUCTIONS  # the input is data, never instructions


def test_the_plan_takes_the_facts_from_the_context_not_from_the_model(payment_case):
    context, incidents = payment_case

    plan = check(context, incidents, answer())

    assert plan.service == "Payment API"  # the service of the reference incident
    assert plan.related_services == context.related_services
    assert plan.sources == ALL_SOURCES  # every source, always
    assert plan.window_start == context.change_window.start
    assert plan.window_end >= max(window.end for window in context.log_windows)


def test_empty_queries_are_removed_and_a_plan_without_any_is_refused(payment_case):
    context, incidents = payment_case

    plan = check(context, incidents, answer(search_queries=["  timeouts on payments ", " "]))
    assert plan.search_queries == ["timeouts on payments"]

    with pytest.raises(LLMOutputError, match="search_queries"):
        check(context, incidents, answer(search_queries=[" "]))


def test_the_model_may_ask_only_for_queries_extra_searches_and_its_reasons():
    assert set(PlannerAnswer.model_fields) == {"search_queries", "extra_searches", "rationale"}
    assert set(ExtraSearch.model_fields) == {"source", "service", "hours_before", "days_before", "reason"}


def test_every_extra_search_is_checked_by_code_before_it_runs(payment_case):
    context, _ = payment_case
    asked = [
        ExtraSearch(source="logs", service="Network Services", hours_before=48, reason="the expert asks about the proxy"),
        ExtraSearch(source="logs", service="Mainframe", hours_before=24, reason="a guess"),
        ExtraSearch(source="changes", service="Payment API", days_before=365, reason="everything"),
        ExtraSearch(source="changes", service="Payment API", days_before=7, reason="the same window"),
        ExtraSearch(source="logs", service="Network Services", hours_before=24, reason="again"),
        ExtraSearch(source="changes", service="Payment API", days_before=30, reason="the guide: a change last month"),
    ]

    accepted, refused = check_extra_searches(asked, context, KNOWN, *WINDOWS)

    assert [(item.source, item.service) for item in accepted] == [("logs", "Network Services"), ("changes", "Payment API")]
    assert [item["refused"].split(" ")[0] for item in refused] == ["'Mainframe'", "a", "already", "the"]


def test_a_refused_extra_search_does_not_refuse_the_plan(payment_case):
    context, incidents = payment_case

    plan = check(context, incidents, answer(extra_searches=[{"source": "logs", "service": "Mainframe", "hours_before": 5,
                                                             "reason": "a guess"}]))

    assert plan.extra_searches == [] and plan.refused_searches[0]["service"] == "Mainframe"


def test_plan_investigation_asks_the_model_and_checks_the_answer(payment_case, monkeypatch):
    context, incidents = payment_case
    calls = []

    def fake_ask_json(instructions, user_input, schema):
        calls.append((instructions, user_input, schema))
        return answer()

    monkeypatch.setattr(planner, "ask_json", fake_ask_json)

    plan = plan_investigation(context, incidents, KNOWN, *WINDOWS)

    assert plan.search_queries == ["payment requests fail with database connection timeouts"]
    assert calls[0][2] is PlannerAnswer
    assert "INC-2026-00857" in calls[0][1]


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_live_plan_for_the_payment_api_problem(payment_case):
    context, incidents = payment_case

    plan = plan_investigation(context, incidents, KNOWN, *WINDOWS)

    print("\n" + plan.model_dump_json(indent=2))
    assert plan.service == "Payment API"
    assert plan.search_queries
