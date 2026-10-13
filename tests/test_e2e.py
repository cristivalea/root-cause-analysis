"""End to end through the API (final_project_prompt.md, section 12.3; final_project_steps.md, E12).

Every step goes through the HTTP endpoints the interface calls, signed in as the Problem Manager or the
Technical Expert, on the mock data loaded into a temporary SQLite database. The investigation runs the real
graph (tools, ledger, guardrail, confidence, store) in the background task of the API; only the three agents
and the ChromaDB search answer with the fixed answers of tests/test_pipeline.py, so no model is called.

The 13 scenarios, in the order of the prompt:
 1. a problem from a major incident          8. the draft is sent to the expert
 2. a problem from recurring incidents       9. the expert asks for more details
 3. incidents added and removed             10. the request is read by the next investigation
 4. no incident in two problems             11. a new revision is saved
 5. the RCA starts for a problem            12. the RCA is validated, rejected or escalated
 6. the RCA is in RCA History at once       13. the status of the problem and its whole history
 7. a draft is generated and saved
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

import api  # noqa: E402
from rca import storage, store  # noqa: E402
from test_pipeline import INCIDENT_ID, fakes  # noqa: E402,F401  (fakes is the fixture of the agents)

ROOT = Path(__file__).resolve().parents[1]
MAJOR_INCIDENT = "INC-2026-00712"  # SEV-1, Payment API, in no problem
RECURRING = ["INC-2026-01080", "INC-2026-01180"]  # Billing Service, customers received two payment reminders
OTHER_INCIDENT = "INC-2026-00411"  # Payment API, in no problem, older than the incidents of the Payment problem
PM_NOTES = "Look at the connection pool settings first."
EXPERT_REQUEST = "Check the connection pool of payment-db-prod-01."


@pytest.fixture
def http(tmp_path, monkeypatch, fakes):  # noqa: F811
    db = tmp_path / "rca.sqlite3"
    storage.load_sources(db, ROOT / "data" / "sources")
    monkeypatch.setattr(api, "DB_PATH", db)
    user = {"username": "pm", "role": "problem_manager", "active": True}
    api.app.dependency_overrides[api.get_current_user] = lambda: user
    client = fastapi_testclient.TestClient(api.app)
    client.user = user
    client.fakes = fakes
    yield client
    api.app.dependency_overrides.clear()


def as_role(http, role):
    http.user.update(username={"problem_manager": "pm", "technical_expert": "expert"}[role], role=role)


def payment_problem(http) -> str:
    return storage.get_problem_id_for_incident(api.DB_PATH, INCIDENT_ID)


def run_first_revision(http, problem_id, **body) -> dict:
    """Start RCA (5): the API answers with the revision RUNNING; the TestClient runs the background task
    before it returns, as the server does after its answer."""
    started = http.post(f"/api/v1/problems/{problem_id}/rcas", json=body)
    assert started.status_code == 202, started.text
    assert started.json()["run_status"] == "RUNNING"
    return started.json()


def send_to_expert(http, rca_id):
    as_role(http, "problem_manager")
    sent = http.post(f"/api/v1/rcas/{rca_id}/submit-review")
    assert sent.status_code == 200, sent.text
    return sent.json()


def decide(http, rca_id, decision, comment="", **extra):
    as_role(http, "technical_expert")
    decided = http.post(f"/api/v1/rcas/{rca_id}/review", json={"decision": decision, "comment": comment, **extra})
    as_role(http, "problem_manager")
    assert decided.status_code == 200, decided.text
    return decided.json()


def next_revision(http, rca_id, key):
    as_role(http, "problem_manager")
    started = http.post(f"/api/v1/rcas/{rca_id}/revisions", json={"request_key": key})
    assert started.status_code == 202, started.text
    return started.json()


def events(http, problem_id):
    return http.get(f"/api/v1/problems/{problem_id}").json()["events"]


def problem_of(http, problem_id) -> dict:
    return http.get(f"/api/v1/problems/{problem_id}").json()["problem"]


# 1-4: the problems and their incidents --------------------------------------------------------------


def test_problems_from_a_major_incident_and_from_recurring_incidents_then_incidents_added_and_removed(http):
    # 1. a problem from one major incident: its priority comes from the severity (SEV-1 is P1)
    major = http.post("/api/v1/problems", json={"incident_ids": [MAJOR_INCIDENT], "reason": "Major incident."})
    assert major.status_code == 200, major.text
    major = major.json()["problem"]
    assert ([link["incident_id"] for link in major["incidents"]], major["priority"], major["status"]) == (
        [MAJOR_INCIDENT], "P1", "Open")

    # 2. a problem from recurring incidents
    recurring = http.post("/api/v1/problems", json={"incident_ids": RECURRING, "title": "Duplicate payment reminders",
                                                    "reason": "The same reminders sent twice, twice."})
    assert recurring.status_code == 200, recurring.text
    recurring = recurring.json()["problem"]
    assert sorted(link["incident_id"] for link in recurring["incidents"]) == sorted(RECURRING)
    assert recurring["title"] == "Duplicate payment reminders"
    free = {item["incident_id"] for item in http.get("/api/v1/incidents/unassigned").json()}
    assert not ({MAJOR_INCIDENT, *RECURRING} & free)

    # 3. an incident added, then removed with its reason; it is free again
    problem_id = recurring["problem_id"]
    added = http.post(f"/api/v1/problems/{problem_id}/incidents",
                      json={"incident_id": "INC-2026-01132", "reason": "Billing too."})
    assert added.status_code == 200, added.text
    assert http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-01132/remove",
                     json={"reason": " "}).status_code == 400  # the reason is required
    removed = http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-01132/remove",
                        json={"reason": "Another cause: invoices, not reminders."})
    assert removed.status_code == 200, removed.text
    assert "INC-2026-01132" in {item["incident_id"] for item in http.get("/api/v1/incidents/unassigned").json()}

    # 4. an incident of a problem cannot go into another one, whichever way it is tried
    taken = http.post(f"/api/v1/problems/{problem_id}/incidents", json={"incident_id": MAJOR_INCIDENT, "reason": "x"})
    again = http.post("/api/v1/problems", json={"incident_ids": [RECURRING[0], "INC-2026-01132"]})
    assert taken.status_code == again.status_code == 409
    assert [link["incident_id"] for link in problem_of(http, major["problem_id"])["incidents"]] == [
        MAJOR_INCIDENT]

    # the history keeps what was added and removed, with the reasons
    history = [(item["action"], item["incident_id"], item["reason"]) for item in events(http, problem_id)]
    assert history[0] == ("created", None, "The same reminders sent twice, twice.")
    assert sorted(history[1:3]) == [("incident_added", incident, "The same reminders sent twice, twice.")
                                    for incident in sorted(RECURRING)]
    assert history[3:] == [("incident_added", "INC-2026-01132", "Billing too."),
                           ("incident_removed", "INC-2026-01132", "Another cause: invoices, not reminders.")]


# 5-13: one RCA through its whole life ---------------------------------------------------------------


def test_an_rca_from_its_start_to_its_validation_with_a_request_of_the_expert_between(http):
    problem_id = payment_problem(http)

    # 3 on the problem the RCA runs on: added and removed before the start, the problem is as it was
    http.post(f"/api/v1/problems/{problem_id}/incidents", json={"incident_id": OTHER_INCIDENT, "reason": "Payment API."})
    http.post(f"/api/v1/problems/{problem_id}/incidents/{OTHER_INCIDENT}/remove", json={"reason": "Other region."})

    # 5. the RCA starts for the problem, with the notes of the Problem Manager
    started = run_first_revision(http, problem_id, guidance={"notes": PM_NOTES}, request_key="start-1")
    rca_id = started["rca_id"]
    assert problem_of(http, problem_id)["status"] == "In investigation"
    assert http.post(f"/api/v1/problems/{problem_id}/rcas", json={}).status_code == 409  # one RCA at a time

    # 6. it is in RCA History
    summaries = {item["rca_id"]: item for item in http.get("/api/v1/rcas/summaries").json()}
    assert summaries[rca_id]["problem_id"] == problem_id

    # 7. the draft is generated and saved, every node of the graph with it
    first = http.get(f"/api/v1/rcas/{rca_id}-R1").json()
    assert (first["run_status"], first["status"], first["revision"]) == ("COMPLETED", "DRAFT", 1)
    assert first["hypotheses"] and first["evidence"]
    assert {"build_context", "investigation_planner", "gather_evidence", "rca_reasoning_agent", "guardrail",
            "confidence"} <= {step["name"] for step in first["trace"]}
    assert PM_NOTES in first["context"]["guidance"]["notes"]
    assert PM_NOTES in http.fakes.planner.requests[0]

    # 8. sent to the expert, who sees it now and not before
    as_role(http, "technical_expert")
    assert rca_id not in {item["rca_id"] for item in http.get("/api/v1/rcas/summaries").json()}
    assert send_to_expert(http, rca_id)["status"] == "AWAITING_TECHNICAL_REVIEW"
    as_role(http, "technical_expert")
    waiting = http.get("/api/v1/rcas", params={"status": "AWAITING_TECHNICAL_REVIEW"}).json()
    assert [item["rca_id"] for item in waiting] == [rca_id]
    as_role(http, "problem_manager")

    # 9. the expert asks for more details
    asked = decide(http, rca_id, "REQUEST_MORE_DETAILS", EXPERT_REQUEST, requested_checks=["pool size"])
    assert asked["status"] == "REQUEST_MORE_DETAILS"

    # 10-11. the next revision reads the request, and is saved next to the first one
    second = next_revision(http, rca_id, "next-1")
    assert second["revision"] == 2
    second = http.get(f"/api/v1/rcas/{rca_id}-R2").json()
    assert (second["run_status"], second["status"], second["previous_revision_id"]) == (
        "COMPLETED", "DRAFT", f"{rca_id}-R1")
    assert second["context"]["expert_request"].startswith(EXPERT_REQUEST)
    for agent in (http.fakes.planner, http.fakes.historical, http.fakes.reasoning):
        assert EXPERT_REQUEST in agent.requests[-1]
    assert [item["revision"] for item in http.get(f"/api/v1/rcas/{rca_id}/revisions").json()] == [1, 2]
    assert http.get(f"/api/v1/rcas/{rca_id}-R1").json()["hypotheses"] == first["hypotheses"]  # R1 is kept as it was

    # 12. validated, on one hypothesis of the revision
    send_to_expert(http, rca_id)
    validated = decide(http, rca_id, "APPROVE", "The pool is the cause.",
                       hypothesis_id=second["hypotheses"][0]["hypothesis_id"])
    assert validated["status"] == "VALIDATED"

    # 13. the problem is closed by this RCA, and its history tells the whole story
    problem = problem_of(http, problem_id)
    assert (problem["status"], problem["rca_id"]) == ("Closed", rca_id)
    rca_steps = [(item["details"]["from"], item["details"]["to"]) for item in events(http, problem_id)
                 if item["action"] == "rca_status" and item["rca_id"] == rca_id]
    assert rca_steps == [(None, "DRAFT"), ("DRAFT", "AWAITING_TECHNICAL_REVIEW"),
                         ("AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS"), ("REQUEST_MORE_DETAILS", "DRAFT"),
                         ("DRAFT", "AWAITING_TECHNICAL_REVIEW"), ("AWAITING_TECHNICAL_REVIEW", "VALIDATED")]
    actions = [item["action"] for item in events(http, problem_id)]
    assert {"incident_added", "incident_removed", "status_changed", "closed"} <= set(actions)
    history = http.get(f"/api/v1/rcas/{rca_id}/history").json()
    assert [item["to_status"] for item in history["history"]] == [to for _, to in rca_steps]
    assert [item["decision"]["decision"] for item in history["history"] if item["decision"]] == [
        "REQUEST_MORE_DETAILS", "APPROVE"]
    assert history["rca"]["revisions"] == 2
    summary = {item["rca_id"]: item for item in http.get("/api/v1/rcas/summaries").json()}[rca_id]
    assert summary["status"] == "VALIDATED"


def test_a_rejected_rca_opens_its_problem_again_and_a_new_rca_can_start(http):
    problem_id = payment_problem(http)
    rca_id = run_first_revision(http, problem_id)["rca_id"]
    send_to_expert(http, rca_id)

    assert http.post(f"/api/v1/rcas/{rca_id}/review", json={"decision": "REJECT", "comment": ""}).status_code in (
        400, 403)  # a rejection needs a comment, and only the expert decides
    rejected = decide(http, rca_id, "REJECT", "The evidence does not support the pool.")

    assert rejected["status"] == "REJECTED"
    assert problem_of(http, problem_id)["status"] == "Open"
    assert http.post(f"/api/v1/rcas/{rca_id}/revisions", json={}).status_code == 409  # a rejected RCA stays closed
    same_input = http.post(f"/api/v1/problems/{problem_id}/rcas", json={})
    assert same_input.status_code == 400 and "same input would give the same answer" in same_input.json()["detail"]
    new_rca = run_first_revision(http, problem_id, guidance={"notes": "Look at the acquirer this time."})["rca_id"]
    assert new_rca != rca_id
    statuses = {item["rca_id"]: item["status"] for item in http.get("/api/v1/rcas/summaries").json()}
    assert (statuses[rca_id], statuses[new_rca]) == ("REJECTED", "DRAFT")


def test_a_request_at_the_last_revision_escalates_the_rca_and_the_problem_goes_to_manual_review(http):
    problem_id = payment_problem(http)
    rca_id = run_first_revision(http, problem_id)["rca_id"]
    for number in range(2, store.MAX_REVISIONS + 1):
        send_to_expert(http, rca_id)
        decide(http, rca_id, "REQUEST_MORE_DETAILS", f"Request {number - 1}.")
        assert next_revision(http, rca_id, f"next-{number}")["revision"] == number
    send_to_expert(http, rca_id)

    escalated = decide(http, rca_id, "REQUEST_MORE_DETAILS", "Still not enough.")

    assert escalated["status"] == "ESCALATED_MANUAL"
    assert problem_of(http, problem_id)["status"] == "Manual"
    assert events(http, problem_id)[-1]["action"] == "manual"
    assert http.post(f"/api/v1/rcas/{rca_id}/revisions", json={}).status_code == 409
    assert [item["revision"] for item in http.get(f"/api/v1/rcas/{rca_id}/revisions").json()] == list(
        range(1, store.MAX_REVISIONS + 1))


def test_a_repeated_click_starts_one_rca_and_one_revision(http):
    problem_id = payment_problem(http)
    first = run_first_revision(http, problem_id, request_key="click-1")
    again = http.post(f"/api/v1/problems/{problem_id}/rcas", json={"request_key": "click-1"})

    assert again.status_code == 202 and (again.json()["rca_id"], again.json()["revision"]) == (
        first["rca_id"], first["revision"])
    assert len([item for item in http.get("/api/v1/rcas/summaries").json() if item["problem_id"] == problem_id]) == 1
    assert len(http.fakes.reasoning.requests) == 1  # the graph ran once


# What the Problem Manager gives at Start RCA, and the incidents added or removed before it ------------------


def test_every_field_of_start_rca_and_the_incidents_added_and_removed_reach_the_investigation(http):
    problem_id = payment_problem(http)
    for incident_id in (OTHER_INCIDENT, "INC-2026-00371"):
        assert http.post(f"/api/v1/problems/{problem_id}/incidents",
                         json={"incident_id": incident_id, "reason": "Payment API timeouts."}).status_code == 200
    assert http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-00371/remove",
                     json={"reason": "Another acquirer."}).status_code == 200
    guidance = {"notes": PM_NOTES, "instructions": "Why does it come back after every deployment?",
                "extra_services": ["Network Services"], "change_window_days": 30, "log_hours_before": 12}

    rca_id = run_first_revision(http, problem_id, guidance=guidance)["rca_id"]
    record = http.get(f"/api/v1/rcas/{rca_id}-R1").json()
    context = record["context"]

    # the incidents: the one added is investigated, the one removed is not
    incidents = {item: storage.get_incident(api.DB_PATH, item) for item in (OTHER_INCIDENT, INCIDENT_ID, "INC-2026-00857")}
    assert context["incident_ids"] == sorted(incidents, key=lambda item: incidents[item].detected_at)
    assert "INC-2026-00371" not in context["incident_ids"]
    # every field of the guidance, applied by code
    assert (context["notes"], context["instructions"]) == (guidance["notes"], guidance["instructions"])
    assert "Network Services" in context["services"]
    first = min(item.detected_at for item in incidents.values())
    assert context["change_window"]["start"] == (first - timedelta(days=30)).isoformat().replace("+00:00", "Z") or \
        datetime.fromisoformat(context["change_window"]["start"]) == first - timedelta(days=30)
    for window in context["log_windows"]:
        detected = incidents[window["incident_id"]].detected_at
        assert datetime.fromisoformat(window["start"]) == detected - timedelta(hours=12)
    assert "Problem Manager" in context["sources"]["change_window"] and "Problem Manager" in context["sources"]["log_windows"]
    # the extra service is searched, and the texts reach the agents
    assert any(run["arguments"].get("service") == "Network Services" for run in record["tool_runs"])
    for agent in (http.fakes.planner, http.fakes.reasoning):
        assert PM_NOTES in agent.requests[-1] and guidance["instructions"] in agent.requests[-1]
    given = next(step for step in record["trace"] if step["name"] == "build_context")["details"]["given_text"]
    assert given == {"notes": PM_NOTES, "instructions": guidance["instructions"]}
    # the guidance is kept on the problem for the next start
    kept = problem_of(http, problem_id)["guidance"]
    assert {key: kept[key] for key in guidance} == guidance
