"""Tests for the Investigation Planner.

The services, the windows and the sources come from the context (rca/context.py); the model only
writes the search queries. The offline tests replace the model with a fixed answer and check what
the code does with it. The live test calls Groq on the Payment API problem: python -m pytest -m live
"""

import json
from pathlib import Path

import pytest

from rca import config, storage
from rca.agents import planner
from rca.agents.planner import ALL_SOURCES, PlannerAnswer, build_user_input, check_answer, plan_investigation
from rca.context import build_context
from rca.llm import LLMOutputError

ROOT = Path(__file__).resolve().parents[1]
SIMILAR_IDS = ["INC-2025-00401", "INC-2026-00371", "INC-2026-00411"]


@pytest.fixture(scope="module")
def payment_case(tmp_path_factory):
    """The Payment API problem: INC-2026-00482 and its recurrence INC-2026-00857."""
    db_path = tmp_path_factory.mktemp("planner") / "rca.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    context, incidents = build_context(db_path, incident_id="INC-2026-00482")
    similar = [storage.get_incident(db_path, incident_id) for incident_id in SIMILAR_IDS]
    return context, incidents, similar


def answer(**changes) -> PlannerAnswer:
    values = {
        "search_queries": ["payment requests fail with database connection timeouts"],
        "rationale": "Both incidents show database connection timeouts on card payments.",
    }
    return PlannerAnswer.model_validate(values | changes)


def test_the_model_receives_every_incident_of_the_problem_and_the_similar_ones(payment_case):
    context, incidents, similar = payment_case

    data = json.loads(build_user_input(context, incidents, similar))

    assert [item["incident_id"] for item in data["incidents_of_the_problem"]] == ["INC-2026-00482", "INC-2026-00857"]
    assert data["problem_id"] == context.problem_id
    assert [item["incident_id"] for item in data["similar_past_incidents"]] == SIMILAR_IDS


def test_the_plan_takes_the_facts_from_the_context_not_from_the_model(payment_case):
    context, incidents, _ = payment_case

    plan = check_answer(answer(), context, incidents)

    assert plan.service == "Payment API"  # the service of the reference incident
    assert plan.related_services == context.related_services
    assert plan.sources == ALL_SOURCES  # every source, always
    assert plan.window_start == context.change_window.start
    assert plan.window_end >= max(window.end for window in context.log_windows)


def test_empty_queries_are_removed_and_a_plan_without_any_is_refused(payment_case):
    context, incidents, _ = payment_case

    plan = check_answer(answer(search_queries=["  timeouts on payments ", " "]), context, incidents)
    assert plan.search_queries == ["timeouts on payments"]

    with pytest.raises(LLMOutputError, match="search_queries"):
        check_answer(answer(search_queries=[" "]), context, incidents)


def test_the_model_is_never_asked_for_the_service_the_window_or_the_sources():
    assert set(PlannerAnswer.model_fields) == {"search_queries", "rationale"}


def test_plan_investigation_asks_the_model_and_checks_the_answer(payment_case, monkeypatch):
    context, incidents, similar = payment_case
    calls = []

    def fake_ask_json(instructions, user_input, schema):
        calls.append((instructions, user_input, schema))
        return answer()

    monkeypatch.setattr(planner, "ask_json", fake_ask_json)

    plan = plan_investigation(context, incidents, similar)

    assert plan.search_queries == ["payment requests fail with database connection timeouts"]
    assert calls[0][2] is PlannerAnswer
    assert "INC-2026-00857" in calls[0][1]


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_live_plan_for_the_payment_api_problem(payment_case):
    context, incidents, similar = payment_case

    plan = plan_investigation(context, incidents, similar)

    print("\n" + plan.model_dump_json(indent=2))
    assert plan.service == "Payment API"
    assert plan.search_queries
