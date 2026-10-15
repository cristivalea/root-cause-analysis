"""The problem endpoints: the Problem Manager only; a refused rule comes back as 400 with its message,
a conflict with the current state (an incident already in a problem) as 409."""

from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

import api  # noqa: E402
from rca import storage  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "rca.sqlite3"
    storage.load_sources(db, ROOT / "data" / "sources")
    monkeypatch.setattr(api, "DB_PATH", db)
    user = {"username": "pm", "role": "problem_manager", "active": True}
    api.app.dependency_overrides[api.get_current_user] = lambda: user
    yield fastapi_testclient.TestClient(api.app), user
    api.app.dependency_overrides.clear()


def test_the_problem_manager_creates_and_changes_a_problem(client):
    http, _ = client

    created = http.post("/api/v1/problems", json={"incident_ids": ["INC-2026-00371", "INC-2026-00411"],
                                                  "reason": "Same acquirer timeouts."})
    assert created.status_code == 200, created.text
    problem_id = created.json()["problem"]["problem_id"]

    assert "INC-2026-00371" not in [item["incident_id"] for item in http.get("/api/v1/incidents/unassigned").json()]
    removed = http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-00371/remove", json={"reason": "Other cause."})
    assert removed.status_code == 200
    detail = http.get(f"/api/v1/problems/{problem_id}").json()
    assert [item["action"] for item in detail["events"]] == ["created", "incident_added", "incident_added", "incident_removed"]
    assert detail["events"][0]["details"] == {"manual": True}  # created here, not from a proposal
    assert detail["rcas"] == []


def test_an_incident_of_another_problem_comes_back_as_409(client):
    http, _ = client

    response = http.post("/api/v1/problems", json={"incident_ids": ["INC-2026-00857"], "reason": "Test."})

    assert response.status_code == 409
    assert "belongs to one problem only" in response.json()["detail"]


def test_a_rule_comes_back_as_400_with_its_message(client):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")

    response = http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-00482/remove", json={"reason": " "})

    assert response.status_code == 400
    assert "Give a reason" in response.json()["detail"]


def test_an_incident_is_added_with_its_reason_and_the_guidance_is_kept(client):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")

    added = http.post(f"/api/v1/problems/{problem_id}/incidents",
                      json={"incident_id": "INC-2026-00371", "reason": "Same acquirer timeouts."})
    guide = http.put(f"/api/v1/problems/{problem_id}/guidance",
                     json={"guidance": {"notes": "Check the acquirer certificates.", "change_window_days": 30}})

    assert added.status_code == 200 and guide.status_code == 200
    assert guide.json()["problem"]["guidance"]["notes"] == "Check the acquirer certificates."
    assert guide.json()["problem"]["guidance"]["change_window_days"] == 30
    events = http.get(f"/api/v1/problems/{problem_id}").json()["events"]
    assert (events[-2]["action"], events[-2]["incident_id"], events[-2]["reason"]) == (
        "incident_added", "INC-2026-00371", "Same acquirer timeouts.")
    assert events[-1]["action"] == "guide_updated"
    assert events[-1]["details"]["guidance"]["notes"] == "Check the acquirer certificates."


def test_the_technical_expert_cannot_change_problems(client):
    http, user = client
    user["role"] = "technical_expert"

    assert http.post("/api/v1/problems", json={"incident_ids": ["INC-2026-00371"]}).status_code == 403
    assert http.get("/api/v1/problems").status_code == 403


def test_an_unknown_problem_is_404(client):
    http, _ = client
    assert http.get("/api/v1/problems/PRB-2099-00001").status_code == 404


@pytest.mark.skipif(not (ROOT / "chroma_db").exists(), reason="run scripts/ingest_chroma.py first")
def test_suggestions_and_proposed_problems_come_with_their_reasons(client):
    http, _ = client

    found = http.get("/api/v1/incidents/unassigned/suggestions").json()
    some = next(item for item in found.values() if item)
    assert some["kind"] in ("open_problem", "closed_problem", "new_problem") and some["reasons"]
    proposals = http.get("/api/v1/proposals").json()
    assert proposals and all(item["reasons"] and item["evidence"] and item["key"].startswith("PP-") for item in proposals)

    rejected = http.post(f"/api/v1/incidents/{some['incident_id']}/reject-suggestion",
                         json={"targets": [some["problem_id"] or some["incident_ids"][0]]})
    assert rejected.status_code == 200


def test_starting_an_rca_follows_the_rules_of_the_problem(client, monkeypatch):
    import json

    from rca.models import RCARecord
    from rca_helpers import make_rca

    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    record = RCARecord.model_validate(json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(
        encoding="utf-8")))
    make_rca(api.DB_PATH, problem_id, record, "draft")
    monkeypatch.setattr("rca.pipeline.build_context", lambda *args, **kwargs: pytest.fail("the investigation must not run"))

    response = http.post(f"/api/v1/problems/{problem_id}/rcas", json={})

    assert response.status_code == 409  # a conflict with the RCA already in progress
    assert "one RCA at a time" in response.json()["detail"]


def test_an_rca_starts_only_from_a_problem_never_from_an_incident(client):
    http, _ = client

    assert http.post("/api/v1/investigations/start", json={"incident_id": "INC-2026-00482"}).status_code == 404
    assert http.post("/api/v1/problems/PRB-2099-99999/rcas", json={}).status_code == 404


# Every route needs a signed-in user, and the RCA endpoints follow the lifecycle --------------


PUBLIC = {"/", "/health", "/api/v1/auth/login", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}


def test_every_route_but_the_sign_in_needs_a_signed_in_user(tmp_path, monkeypatch):
    from fastapi.routing import APIRoute

    monkeypatch.setattr(api, "DB_PATH", tmp_path / "empty.sqlite3")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    http = fastapi_testclient.TestClient(api.app)
    routes = [route for route in api.app.routes if isinstance(route, APIRoute) and route.path not in PUBLIC]

    assert len(routes) > 20
    for route in routes:
        path = route.path.replace("{", "").replace("}", "")  # any value: the request must stop before it is read
        for method in route.methods - {"HEAD", "OPTIONS"}:
            response = http.request(method, path, json={})
            assert response.status_code == 401, f"{method} {route.path} answered {response.status_code}"


def sample_rca(problem_id, *steps):
    import json

    from rca.models import RCARecord
    from rca_helpers import make_rca

    record = RCARecord.model_validate(json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(
        encoding="utf-8")))
    return make_rca(api.DB_PATH, problem_id, record, *steps)


def test_the_rca_endpoints_refuse_what_the_lifecycle_does_not_allow(client):
    http, user = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    rca = sample_rca(problem_id, "draft")

    user["role"] = "technical_expert"
    assert http.get(f"/api/v1/rcas/{rca.rca_id}").status_code == 404  # a draft not sent yet stays with the manager
    assert http.get("/api/v1/rcas").json() == []
    review = {"decision": "APPROVE", "comment": "", "hypothesis_id": "HYP-001"}
    assert http.post(f"/api/v1/rcas/{rca.rca_id}/review", json=review).status_code == 409

    user["role"] = "problem_manager"
    sent = http.post(f"/api/v1/rcas/{rca.rca_id}/submit-review")
    assert sent.status_code == 200 and sent.json()["status"] == "AWAITING_TECHNICAL_REVIEW"
    assert http.post(f"/api/v1/rcas/{rca.rca_id}/submit-review").status_code == 409  # not twice
    assert http.post("/api/v1/rcas/RCA-2099-00001/submit-review").status_code == 404

    user["role"] = "technical_expert"
    decided = http.post(f"/api/v1/rcas/{rca.rca_id}/review", json={**review, "reviewer": "someone else"})
    assert decided.status_code == 200 and decided.json()["status"] == "VALIDATED"
    assert decided.json()["review"]["reviewer"] == "pm"  # the signed-in user, never a name sent by the browser
    history = http.get(f"/api/v1/rcas/{rca.rca_id}/history").json()["history"]
    assert [item["to_status"] for item in history] == ["DRAFT", "AWAITING_TECHNICAL_REVIEW", "VALIDATED"]
    user["role"] = "problem_manager"
    assert http.get(f"/api/v1/problems/{problem_id}").json()["problem"]["status"] == "Closed"


def test_the_revisions_of_an_rca_are_listed_and_each_one_can_be_read(client):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    rca = sample_rca(problem_id, "draft", "submit", "more", "next", "draft")

    revisions = http.get(f"/api/v1/rcas/{rca.rca_id}/revisions").json()

    assert [(item["revision"], item["status"]) for item in revisions] == [(1, "REQUEST_MORE_DETAILS"), (2, "DRAFT")]
    assert http.get(f"/api/v1/rcas/{rca.rca_id}-R1").json()["review"]["decision"] == "REQUEST_MORE_DETAILS"


# Start RCA: saved at once, run in the background, never twice (E4) ----------------------------


@pytest.fixture
def no_background_run(monkeypatch):
    """The runs the API starts, kept instead of run: the test sees the RCA as it is before its run."""
    started = []
    monkeypatch.setattr(api, "_run", lambda revision_id, owner: started.append((revision_id, owner)))
    return started


def test_start_rca_answers_at_once_and_the_rca_is_already_listed(client, no_background_run):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")

    response = http.post(f"/api/v1/problems/{problem_id}/rcas",
                         json={"guidance": {"notes": "Pool?", "instructions": "Answer: why only on Mondays?"}})

    assert response.status_code == 202
    revision = response.json()
    assert (revision["revision"], revision["run_status"], revision["status"]) == (1, "RUNNING", "DRAFT")
    assert revision["guidance"]["instructions"] == "Answer: why only on Mondays?"  # kept with the RCA
    assert no_background_run == [(revision["rca_id"] + "-R1", "pm")]
    listed = http.get("/api/v1/cases").json()  # RCA History lists it before its run ended
    assert [[item["run_status"] for item in case] for case in listed] == [["RUNNING"]]
    assert http.get(f"/api/v1/problems/{problem_id}").json()["problem"]["status"] == "In investigation"


def test_a_repeated_start_with_the_same_key_returns_the_same_rca_and_runs_once(client, no_background_run):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    body = {"request_key": "click-1"}

    first = http.post(f"/api/v1/problems/{problem_id}/rcas", json=body)
    second = http.post(f"/api/v1/problems/{problem_id}/rcas", json=body)
    other = http.post(f"/api/v1/problems/{problem_id}/rcas", json={"request_key": "click-2"})

    assert first.status_code == second.status_code == 202
    assert first.json()["rca_id"] == second.json()["rca_id"]
    assert len(no_background_run) == 1
    assert other.status_code == 409  # a new start while the RCA runs: one RCA at a time
    assert len(http.get("/api/v1/rcas").json()) == 1


def test_two_starts_at_the_same_moment_create_one_rca(client, no_background_run):
    import threading

    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    begin, codes = threading.Barrier(2), []

    def start():
        begin.wait()
        codes.append(http.post(f"/api/v1/problems/{problem_id}/rcas", json={}).status_code)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(codes) == [202, 409]
    assert len(http.get("/api/v1/rcas").json()) == 1


def test_a_run_that_cannot_even_start_is_saved_failed(client, monkeypatch):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")

    def broken(**kwargs):
        raise RuntimeError("the graph could not be built")

    monkeypatch.setattr(api, "run_investigation", broken)

    revision = http.post(f"/api/v1/problems/{problem_id}/rcas", json={}).json()

    saved = http.get(f"/api/v1/rcas/{revision['rca_id']}").json()
    assert (saved["status"], saved["run_status"]) == ("FAILED", "FAILED")
    assert "the graph could not be built" in saved["error"]


def test_the_next_revision_starts_in_the_background_too(client, no_background_run):
    from rca import store

    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    rca = sample_rca(problem_id, "fail")

    response = http.post(f"/api/v1/rcas/{rca.rca_id}/revisions", json={"request_key": "again-1"})

    assert response.status_code == 202
    assert (response.json()["revision"], response.json()["run_status"]) == (2, "RUNNING")
    assert no_background_run == [(f"{rca.rca_id}-R2", "pm")]
    assert store.get_summary(rca.rca_id, api.DB_PATH).status == "DRAFT"


def test_a_run_stopped_by_a_restart_is_saved_failed_when_the_application_starts(client, no_background_run):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    revision = http.post(f"/api/v1/problems/{problem_id}/rcas", json={}).json()  # its run never happens

    with fastapi_testclient.TestClient(api.app):  # the start of the application
        pass

    saved = http.get(f"/api/v1/rcas/{revision['rca_id']}").json()
    assert (saved["status"], saved["run_status"]) == ("FAILED", "FAILED")
    assert saved["error"].startswith("Interrupted")


# Proposed Problem Records: accept once, atomically, after checking again (E6) -----------------------


def proposal(kind, incident_ids, problem_id=None, **extra):
    from rca import suggestions

    return {"key": suggestions.proposal_key(kind, incident_ids, problem_id), "kind": kind,
            "incident_ids": incident_ids, "problem_id": problem_id, **extra}


def free(http, count):
    return [item["incident_id"] for item in http.get("/api/v1/incidents/unassigned").json()][:count]


def test_accepting_a_group_creates_its_problem_once(client):
    http, _ = client
    incident_ids = free(http, 3)
    body = proposal("group", incident_ids, title="Card payments time out", reason="Same timeouts every week.")

    first = http.post("/api/v1/proposals/accept", json=body)
    again = http.post("/api/v1/proposals/accept", json=body)

    assert first.status_code == again.status_code == 200
    created = first.json()["problem"]
    assert first.json()["created"] is True and again.json()["created"] is False
    assert again.json()["problem"]["problem_id"] == created["problem_id"]  # no second problem
    assert sorted(link["incident_id"] for link in created["incidents"]) == sorted(incident_ids)
    assert created["title"] == "Card payments time out"
    events = http.get(f"/api/v1/problems/{created['problem_id']}").json()["events"]
    assert (events[0]["action"], events[0]["details"], events[0]["reason"]) == (
        "created", {"proposal": body["key"]}, "Same timeouts every week.")
    assert not set(incident_ids) & set(free(http, 500))


def test_a_proposal_changed_on_the_way_is_refused(client):
    http, _ = client
    body = proposal("group", free(http, 2))
    body["incident_ids"] = body["incident_ids"] + ["INC-2026-00482"]  # one more incident, same key

    response = http.post("/api/v1/proposals/accept", json=body)

    assert response.status_code == 400 and "does not match its key" in response.json()["detail"]


def test_an_incident_taken_meanwhile_stops_the_whole_proposal_and_nothing_is_half_done(client):
    http, _ = client
    one, two = free(http, 2)
    http.post("/api/v1/problems", json={"incident_ids": [two], "reason": "Test."})  # someone else, meanwhile
    before = len(http.get("/api/v1/problems").json())

    response = http.post("/api/v1/proposals/accept", json=proposal("group", [one, two]))

    assert response.status_code == 409
    assert len(http.get("/api/v1/problems").json()) == before
    assert one in free(http, 500)  # the other incident was not taken either
    retry = http.post("/api/v1/proposals/accept", json=proposal("group", [one, two]))
    assert retry.status_code == 409  # the proposal was not marked as accepted


def test_a_single_major_incident_and_an_incident_for_an_open_problem_are_accepted(client):
    http, _ = client
    single = free(http, 1)
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-00857/remove", json={"reason": "Test."})

    made = http.post("/api/v1/proposals/accept", json=proposal("single", single))
    added = http.post("/api/v1/proposals/accept", json=proposal("attach", ["INC-2026-00857"], problem_id,
                                                                reason="Same acquirer timeouts."))

    assert made.status_code == 200 and [link["incident_id"] for link in made.json()["problem"]["incidents"]] == single
    assert added.status_code == 200
    assert "INC-2026-00857" in [link["incident_id"] for link in added.json()["problem"]["incidents"]]


def test_a_rejected_proposal_cannot_be_accepted_and_an_accepted_one_cannot_be_rejected(client):
    http, _ = client
    rejected = proposal("group", free(http, 2), reason="Different causes.")
    assert http.post("/api/v1/proposals/reject", json=rejected).status_code == 200
    assert http.post("/api/v1/proposals/accept", json=rejected).status_code == 409

    accepted = proposal("group", free(http, 4)[2:])  # two other incidents
    assert http.post("/api/v1/proposals/accept", json=accepted).status_code == 200
    assert http.post("/api/v1/proposals/reject", json=accepted).status_code == 409

    alone = proposal("single", free(http, 1)[:1])  # every incident in no problem needs a problem
    refused = http.post("/api/v1/proposals/reject", json=alone)
    assert refused.status_code == 400 and "cannot be rejected" in refused.json()["detail"]
    assert http.post("/api/v1/incidents/INC-2026-00371/dismiss", json={"reason": "x"}).status_code in (404, 405)


def test_two_accepts_of_one_proposal_at_the_same_moment_make_one_problem(client):
    import threading

    http, _ = client
    body = proposal("group", free(http, 3))
    begin, answers = threading.Barrier(2), []

    def accept():
        begin.wait()
        answers.append(http.post("/api/v1/proposals/accept", json=body).json())

    threads = [threading.Thread(target=accept) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({item["problem"]["problem_id"] for item in answers}) == 1
    assert sorted(item["created"] for item in answers) == [False, True]


def test_a_problem_created_manually_needs_a_reason(client):
    http, _ = client

    refused = http.post("/api/v1/problems", json={"incident_ids": ["INC-2026-00371"], "reason": " "})

    assert refused.status_code == 400 and "Give a reason" in refused.json()["detail"]
    assert "INC-2026-00371" in [item["incident_id"] for item in http.get("/api/v1/incidents/unassigned").json()]


# Read-only views for the React interface: the rule stays in Python, the interface draws ------------


def test_the_diagram_of_a_revision_is_the_one_rca_diagram_chooses(client):
    from rca.diagram import choose_diagram

    http, user = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    rca = sample_rca(problem_id, "draft")

    answer = http.get(f"/api/v1/rcas/{rca.rca_id}/diagram")

    assert answer.status_code == 200
    expected = choose_diagram(rca.hypotheses)
    if expected is None:
        assert answer.json() is None
    else:
        assert answer.json()["kind"] == expected.kind
        assert [step["because"] for step in answer.json()["steps"]] == [step.because for step in expected.steps]
        assert len(answer.json()["factors"]) == len(expected.factors)
    user["role"] = "technical_expert"  # a draft not sent yet stays with the manager, its diagram too
    assert http.get(f"/api/v1/rcas/{rca.rca_id}/diagram").status_code == 404
    assert http.get(f"/api/v1/rcas/{rca.rca_id}/comparison").status_code == 404


def test_the_comparison_is_empty_for_a_first_revision_and_filled_for_the_next(client):
    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    rca = sample_rca(problem_id, "draft", "submit", "more", "next", "draft")

    assert http.get(f"/api/v1/rcas/{rca.rca_id}-R1/comparison").json() is None
    found = http.get(f"/api/v1/rcas/{rca.rca_id}/comparison").json()

    assert found["previous_revision"] == 1 and found["current_id"].endswith("-R2")
    assert {item["kind"] for item in found["hypotheses"]} <= {"kept", "new", "dropped"}
    assert http.get("/api/v1/rcas/RCA-2099-00001/comparison").status_code == 404
