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
