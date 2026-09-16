"""Tests for the Investigation Planner.

The offline tests replace the model with a fixed answer and check what the code does with it.
The live test calls Groq on the Payment API incident: python -m pytest -m live
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from rca import config
from rca.agents import planner
from rca.agents.planner import PlannerAnswer, build_user_input, check_answer, plan_investigation
from rca.llm import LLMOutputError
from rca.models import Incident

ROOT = Path(__file__).resolve().parents[1]

# Incident INC-2026-00482 was detected at 14:32. The deploy CHG-2026-00871 was 34 minutes earlier.
DEPLOY_AT = datetime.fromisoformat("2026-07-14T13:58:00+00:00")
SIMILAR_IDS = ["INC-2025-00401", "INC-2026-00371", "INC-2026-00411"]


def load_incidents() -> dict[str, Incident]:
    data = json.loads((ROOT / "data" / "sources" / "incidents.json").read_text(encoding="utf-8"))
    return {item["incident_id"]: Incident.model_validate(item) for item in data}


@pytest.fixture(scope="module")
def payment_case():
    incidents = load_incidents()
    return incidents["INC-2026-00482"], [incidents[incident_id] for incident_id in SIMILAR_IDS]


def answer(**changes) -> PlannerAnswer:
    values = {
        "service": "Payment API",
        "window_start": "2026-07-14T10:30:00Z",
        "window_end": "2026-07-14T15:17:00Z",
        "sources": ["changes", "logs", "cmdb", "historical_rcas"],
        "search_queries": ["payment requests fail with database connection timeouts"],
        "rationale": "The failure started suddenly, so a few hours before detection are enough.",
    }
    return PlannerAnswer.model_validate(values | changes)


# What the model receives ---------------------------------------------------------------


def test_the_model_receives_the_incident_and_the_similar_incidents(payment_case):
    incident, similar = payment_case

    data = json.loads(build_user_input(incident, similar))

    assert data["incident"]["incident_id"] == "INC-2026-00482"
    assert data["incident"]["detected_at"] == "2026-07-14T14:32:00Z"
    assert [item["incident_id"] for item in data["similar_past_incidents"]] == SIMILAR_IDS


# What the code does with the answer ----------------------------------------------------


def test_a_good_answer_becomes_a_plan(payment_case):
    incident, similar = payment_case

    plan = check_answer(answer(), incident, similar)

    assert plan.service == "Payment API"
    assert plan.window_start <= DEPLOY_AT < incident.detected_at <= plan.window_end
    assert plan.related_services == []  # filled from the CMDB, not by the model


def test_service_name_is_matched_to_the_known_spelling(payment_case):
    incident, similar = payment_case

    plan = check_answer(answer(service=" payment api "), incident, similar)

    assert plan.service == "Payment API"


def test_an_invented_service_is_refused(payment_case):
    incident, similar = payment_case

    with pytest.raises(LLMOutputError, match="Load Balancer"):
        check_answer(answer(service="Load Balancer"), incident, similar)


@pytest.mark.parametrize(
    "window, problem",
    [
        ({"window_start": "2026-07-14T14:40:00Z", "window_end": "2026-07-14T16:00:00Z"}, "window_start"),
        ({"window_start": "2026-07-14T10:00:00Z", "window_end": "2026-07-14T14:00:00Z"}, "window_end"),
        ({"window_start": "2026-07-01T00:00:00Z", "window_end": "2026-07-14T15:00:00Z"}, "7 days"),
    ],
)
def test_a_window_that_misses_the_incident_is_refused(payment_case, window, problem):
    incident, similar = payment_case

    with pytest.raises(LLMOutputError, match=problem):
        check_answer(answer(**window), incident, similar)


def test_all_problems_are_reported_together_with_the_answer(payment_case):
    incident, similar = payment_case
    bad = answer(service="Auth Service", window_start="2026-07-14T15:00:00Z", window_end="2026-07-14T16:00:00Z")

    with pytest.raises(LLMOutputError) as error:
        check_answer(bad, incident, similar)

    assert "service" in str(error.value) and "window_start" in str(error.value)
    assert json.loads(error.value.raw_output)["service"] == "Auth Service"  # kept for the retry


def test_times_without_a_time_zone_are_taken_as_utc(payment_case):
    incident, similar = payment_case

    plan = check_answer(answer(window_start="2026-07-14T10:30:00", window_end="2026-07-14T15:17:00"), incident, similar)

    assert plan.window_start.isoformat() == "2026-07-14T10:30:00+00:00"


def test_duplicate_sources_and_empty_queries_are_removed(payment_case):
    incident, similar = payment_case

    plan = check_answer(
        answer(sources=["logs", "changes", "logs"], search_queries=["  timeouts on payments ", " "]),
        incident,
        similar,
    )

    assert plan.sources == ["logs", "changes"]
    assert plan.search_queries == ["timeouts on payments"]


def test_answer_without_sources_does_not_match_the_schema():
    with pytest.raises(ValueError, match="sources"):
        answer(sources=[])


def test_plan_investigation_asks_the_model_and_checks_the_answer(payment_case, monkeypatch):
    incident, similar = payment_case
    calls = []

    def fake_ask_json(instructions, user_input, schema):
        calls.append((instructions, user_input, schema))
        return answer()

    monkeypatch.setattr(planner, "ask_json", fake_ask_json)

    plan = plan_investigation(incident, similar)

    assert plan.service == "Payment API"
    assert calls[0][2] is PlannerAnswer
    assert "INC-2026-00482" in calls[0][1]


# Real model ----------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_live_plan_for_the_payment_api_incident(payment_case):
    incident, similar = payment_case

    plan = plan_investigation(incident, similar)

    print("\n" + plan.model_dump_json(indent=2))
    assert plan.service == "Payment API"
    assert plan.window_start <= DEPLOY_AT, "the window must include the deploy 34 minutes before detection"
    assert plan.window_end >= incident.detected_at
    assert {"changes", "logs"} <= set(plan.sources)
    assert plan.search_queries
