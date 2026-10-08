"""The problem endpoints: the Problem Manager only, and the rules come back as 400 with their message."""

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

    created = http.post("/api/v1/problems", json={"incident_ids": ["INC-2026-00371", "INC-2026-00411"]})
    assert created.status_code == 200, created.text
    problem_id = created.json()["problem"]["problem_id"]

    assert "INC-2026-00371" not in [item["incident_id"] for item in http.get("/api/v1/incidents/unassigned").json()]
    removed = http.post(f"/api/v1/problems/{problem_id}/incidents/INC-2026-00371/remove", json={"reason": "Other cause."})
    assert removed.status_code == 200
    detail = http.get(f"/api/v1/problems/{problem_id}").json()
    assert [item["action"] for item in detail["events"]] == ["created", "incident_added", "incident_added", "incident_removed"]
    assert detail["rcas"] == []


def test_a_rule_comes_back_as_400_with_its_message(client):
    http, _ = client

    response = http.post("/api/v1/problems", json={"incident_ids": ["INC-2026-00857"]})

    assert response.status_code == 400
    assert "Give a reason to move it" in response.json()["detail"]


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
    assert all(len(group) >= 3 for group in http.get("/api/v1/problems/proposed").json())

    rejected = http.post(f"/api/v1/incidents/{some['incident_id']}/reject-suggestion",
                         json={"targets": [some["problem_id"] or some["incident_ids"][0]]})
    assert rejected.status_code == 200


def test_starting_an_rca_follows_the_rules_of_the_problem(client, monkeypatch):
    from datetime import datetime, timezone

    from rca import store
    from rca.models import RCARecord

    http, _ = client
    problem_id = storage.get_problem_id_for_incident(api.DB_PATH, "INC-2026-00482")
    store.save_rca(RCARecord(rca_id="RCA-2026-00001", incident_id="INC-2026-00857", status="DRAFT", owner="pm",
                             created_at=datetime.now(timezone.utc), problem_id=problem_id), db_path=api.DB_PATH)
    monkeypatch.setattr(api, "run_investigation", lambda **kwargs: pytest.fail("the investigation must not run"))

    response = http.post("/api/v1/investigations/start", json={"incident_id": "INC-2026-00482", "owner": "pm"})

    assert response.status_code == 400
    assert "only one RCA case at a time" in response.json()["detail"]
