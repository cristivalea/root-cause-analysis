"""Shared test data: the Payment API evidence ledger (INC-2026-00482).

The ledger is built from the real tools on the mock data, with the same functions as the pipeline.
The historical evidence is written by hand, so these tests need neither Ollama nor the Historical RCA Agent.
"""

import os
from datetime import datetime
from pathlib import Path

# The tests use fake answers: they are not sent to LangSmith, even when .env turns tracing on.
# Set before rca.config reads .env, which never replaces a variable that is already set.
os.environ["LANGSMITH_TRACING"] = "false"

import pytest

from rca import storage
from rca.evidence import EvidenceLedger, add_changes, add_dependencies, add_log_groups
from rca.tools import find_changes, find_dependencies, find_logs

ROOT = Path(__file__).resolve().parents[1]
INCIDENT_ID = "INC-2026-00482"
DETECTED_AT = datetime.fromisoformat("2026-07-14T14:32:00+00:00")
# The window chosen by the Investigation Planner for this incident (step 8).
WINDOW_START = datetime.fromisoformat("2026-07-14T10:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-07-14T15:17:00+00:00")


def build_payment_ledger(db_path: Path) -> EvidenceLedger:
    """The ledger the pipeline builds for INC-2026-00482: tool results first, then history."""
    ledger = EvidenceLedger()
    add_log_groups(ledger, find_logs("Payment API", WINDOW_START, WINDOW_END, db_path=db_path), DETECTED_AT)
    add_changes(ledger, find_changes(["Payment API"], WINDOW_START, WINDOW_END, db_path=db_path), DETECTED_AT)
    add_dependencies(ledger, find_dependencies("Payment API", db_path=db_path))

    ledger.add(
        "HISTORICAL_RCA",
        "RCA-2025-00114",
        "Past Payment API RCA: intermittent HTTP 500 errors and latency above 5 seconds after a release. "
        "Root cause was database connection pool exhaustion from unclosed SQL sessions in the payment "
        "retry handler. Mitigated by restarting pods and increasing the maximum pool size.",
        "RCA-2025-00114",
        datetime.fromisoformat("2025-11-20T14:00:00+00:00"),
    )
    ledger.add(
        "HISTORICAL_INCIDENT",
        "INC-2025-00401",
        "Past Payment API incident: card authorisation requests slow during retry bursts, "
        "intermittent HTTP 500 responses and database timeout warnings.",
        "INC-2025-00401",
        datetime.fromisoformat("2025-11-20T14:32:00+00:00"),
    )
    return ledger


@pytest.fixture(scope="session")
def payment_ledger(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("payment_ledger") / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    return build_payment_ledger(db_path)


# --------------------------------------------------------------------------------------
# The interface tests (tests/test_ui_*.py) run the real pages against the real API, in process:
# - the HTTP requests of rca/ui/services.py go to the FastAPI app through its TestClient, on a
#   temporary copy of the data with RCAs in every status, so no server and no saved RCA are needed;
# - every AppTest starts signed in as the Problem Manager; a test that needs the Technical Expert
#   sets the role in the session, and the role reaches the API with each request.
# --------------------------------------------------------------------------------------

UI_RCA_FIXTURE = ROOT / "tests" / "fixtures" / "sample_rca_record.json"


def seed_ui_rcas(db_path: Path) -> None:
    """One RCA in every status the pages show, one with two revisions, each on its own open problem
    (a problem has one RCA in progress at a time), built through the lifecycle of rca/store.py."""
    import json

    from rca import problems, store
    from rca.models import RCARecord
    from rca_helpers import make_rca

    base = RCARecord.model_validate(json.loads(UI_RCA_FIXTURE.read_text(encoding="utf-8")))
    payment = storage.get_problem_id_for_incident(db_path, "INC-2026-00482")
    others = [item.problem_id for item in problems.list_problems("Open", db_path=db_path) if item.problem_id != payment]
    # first, so it is the oldest: an RCA whose run is still going on, with the two steps it finished
    running = make_rca(db_path, others[5], base)
    for finished in base.trace[:2]:
        store.record_step(running.revision_id, finished, db_path=db_path)
    make_rca(db_path, others[0], base, "draft")
    make_rca(db_path, payment, base, "draft", "submit")
    make_rca(db_path, others[1], base, "fail", investigation_summary="The RCA Reasoning Agent did not produce a "
             "valid draft in 3 attempts.")
    make_rca(db_path, others[2], base, "draft", "submit", "approve")
    make_rca(db_path, others[3], base, "draft", "submit", "more", "next", "draft", "submit")
    make_rca(db_path, others[4], base, "draft", "submit", "reject")
    make_rca(db_path, others[6], base, "draft", "submit", "more")  # waiting for its next revision


@pytest.fixture(autouse=True)
def ui_through_the_api(request, monkeypatch, tmp_path):
    module = request.node.module.__name__
    if not module.startswith("test_ui_") or module == "test_ui_problems":  # test_ui_problems replaces the API itself
        yield
        return

    import requests as http
    import streamlit as st
    from fastapi import Request
    from fastapi.testclient import TestClient
    from streamlit.testing.v1 import AppTest

    import api
    from rca.ui import services, state

    db_path = tmp_path / "ui.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    seed_ui_rcas(db_path)
    monkeypatch.setattr(api, "DB_PATH", db_path)

    def signed_in(request: Request) -> dict:
        return {"username": "tester", "role": request.headers.get("X-Test-Role") or state.PROBLEM_MANAGER, "active": True}

    api.app.dependency_overrides[api.get_current_user] = signed_in
    client = TestClient(api.app)

    class Response:
        """What rca.ui.services expects from requests: raise_for_status, text, json, status_code."""

        def __init__(self, response):
            self.response, self.text, self.status_code = response, response.text, response.status_code

        def json(self):
            return self.response.json()

        def raise_for_status(self):
            if self.status_code >= 400:
                raise http.HTTPError(str(self.status_code))

    class Requests:
        HTTPError = http.HTTPError
        exceptions = http.exceptions

        def get(self, url, headers=None, timeout=None, **kwargs):
            return Response(client.get(url, headers=headers, **kwargs))

        def post(self, url, headers=None, json=None, timeout=None, **kwargs):
            return Response(client.post(url, headers=headers, json=json, **kwargs))

        def put(self, url, headers=None, json=None, timeout=None, **kwargs):
            return Response(client.put(url, headers=headers, json=json, **kwargs))

    def role_header() -> dict:
        try:
            role = st.session_state.get(state.ROLE_KEY)
        except Exception:  # outside a page, in the body of a test
            role = None
        return {"X-Test-Role": role or state.PROBLEM_MANAGER}

    monkeypatch.setattr(services, "requests", Requests())
    monkeypatch.setattr(services, "API_BASE_URL", "")
    monkeypatch.setattr(services, "_auth_headers", role_header)

    original = AppTest.from_file.__func__

    def from_file(cls, *args, **kwargs):
        app = original(cls, *args, **kwargs)
        app.session_state[state.TOKEN_KEY] = "test-token"
        app.session_state[state.USERNAME_KEY] = "tester"
        app.session_state[state.ROLE_KEY] = state.PROBLEM_MANAGER
        return app

    monkeypatch.setattr(AppTest, "from_file", classmethod(from_file))
    yield
    api.app.dependency_overrides.clear()
