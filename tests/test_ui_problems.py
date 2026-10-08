"""The Problems and Incidents pages, with the API replaced by fixed answers (no login, no server)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rca.models import Incident, Problem
from rca.ui import services

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "rca" / "ui" / "app_pages"
PROBLEMS = [Problem.model_validate(item) for item in json.loads((ROOT / "data/sources/problems.json").read_text(encoding="utf-8"))]
INCIDENTS = {item["incident_id"]: Incident.model_validate(item)
             for item in json.loads((ROOT / "data/sources/incidents.json").read_text(encoding="utf-8"))}
PAYMENT = next(item for item in PROBLEMS if "INC-2026-00482" in [link.incident_id for link in item.incidents])
LOOK_ALIKES = [INCIDENTS["INC-2026-00371"], INCIDENTS["INC-2026-00411"]]


def expanders(app):
    """The expandable sections: with an icon, AppTest reports an expander as a status element."""
    return [*app.expander, *app.status]


@pytest.fixture
def api(monkeypatch):
    """The answers of the API, and every change the page asks for."""
    calls = []
    monkeypatch.setattr(services, "list_problems", lambda status=None: [item for item in PROBLEMS if status in (None, item.status)])
    monkeypatch.setattr(services, "proposed_problems", lambda: [["INC-2024-00034", "INC-2024-00074", "INC-2024-00332"]])
    monkeypatch.setattr(services, "get_problem", lambda problem_id: {"problem": PAYMENT, "events": [], "rcas": []})
    monkeypatch.setattr(services, "get_incident", lambda incident_id: INCIDENTS.get(incident_id))
    monkeypatch.setattr(services, "unassigned_incidents", lambda: LOOK_ALIKES)
    monkeypatch.setattr(services, "cmdb_services", lambda: ["Network Services", "Payment API"])
    monkeypatch.setattr(services, "suggestions", lambda: {
        "INC-2026-00371": {"incident_id": "INC-2026-00371", "kind": "new_problem", "problem_id": None,
                           "incident_ids": ["INC-2025-01508"], "similarity": 0.86, "reasons": ["Same service: Payment API."]},
        "INC-2026-00411": None,
    })
    for name in ("close_problem", "create_problem", "attach_incident", "detach_incident", "dismiss_incident",
                 "reject_suggestion", "reopen_problem"):
        monkeypatch.setattr(services, name, lambda *args, _name=name: calls.append((_name, args)) or (PAYMENT, []))
    return calls


def test_the_problem_list_shows_the_open_problems_and_the_proposed_ones(api):
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30).run()

    assert not app.exception
    shown = app.dataframe[0].value
    assert set(shown["problem"]) == {item.problem_id for item in PROBLEMS if item.status == "Open"}
    assert any("Proposed problems (1)" in item.label for item in expanders(app))


def test_a_problem_shows_its_incidents_and_closing_needs_a_reason(api):
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    app.run()

    assert not app.exception
    text = " ".join(item.value for item in app.markdown)
    assert "`INC-2026-00482`" in text and "`INC-2026-00857`" in text
    assert any(button.label == "Start RCA" for button in app.button)

    app.button(key="problem_close").click().run()
    assert app.error and api == []  # no reason: nothing is sent
    app.text_input(key="problem_close_reason").input("Known vendor bug.").run()
    app.button(key="problem_close").click().run()
    assert api == [("close_problem", (PAYMENT.problem_id, "Known vendor bug."))]


def test_the_incidents_page_lists_every_incident_in_no_problem_with_its_suggestion(api):
    app = AppTest.from_file(str(PAGES / "incidents.py"), default_timeout=30).run()

    assert not app.exception
    shown = app.dataframe[0].value
    assert list(shown["incident"]) == ["INC-2026-00371", "INC-2026-00411"]
    assert list(shown["suggestion"]) == ["New problem with 1 alike incident(s)", "-"]


def test_the_suggestion_card_explains_itself_and_rejecting_it_is_sent(api, tmp_path):
    # the card alone: AppTest cannot click rows of a table, so the function is run on its own
    source = (PAGES / "incidents.py").read_text(encoding="utf-8")
    body = source[:source.index('page_header(t("incidents.title")')]
    script = tmp_path / "card.py"
    script.write_text(body + '''
incident = services.unassigned_incidents()[0]
suggestion_card(incident, services.suggestions()[incident.incident_id], {"INC-2026-00371", "INC-2026-00411"})
''', encoding="utf-8")
    app = AppTest.from_file(str(script), default_timeout=30).run()

    assert not app.exception
    assert any(item.label == "Why this suggestion" for item in expanders(app))
    assert "- Same service: Payment API." in [item.value for item in app.markdown]

    app.button(key="reject").click().run()
    assert ("reject_suggestion", ("INC-2026-00371", ["INC-2025-01508"])) in api
