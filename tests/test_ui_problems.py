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
    monkeypatch.setattr(services, "get_problem", lambda problem_id: {"problem": PAYMENT, "events": [], "rcas": []})
    monkeypatch.setattr(services, "get_incident", lambda incident_id: INCIDENTS.get(incident_id))
    monkeypatch.setattr(services, "unassigned_incidents", lambda: LOOK_ALIKES)
    monkeypatch.setattr(services, "cmdb_services", lambda: ["Network Services", "Payment API"])
    monkeypatch.setattr(services, "suggestions", lambda: {
        "INC-2026-00371": {"incident_id": "INC-2026-00371", "kind": "new_problem", "problem_id": None,
                           "incident_ids": ["INC-2025-01508"], "similarity": 0.86, "reasons": ["Same service: Payment API."]},
        "INC-2026-00411": None,
    })
    for name in ("close_problem", "create_problem", "attach_incident", "detach_incident",
                 "reject_suggestion", "reopen_problem"):
        monkeypatch.setattr(services, name, lambda *args, _name=name: calls.append((_name, args)) or (PAYMENT, []))
    return calls


def test_the_problem_list_shows_the_open_problems_and_leads_to_the_proposed_ones(api):
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30).run()

    assert not app.exception
    shown = app.dataframe[0].value
    assert set(shown["problem"]) == {item.problem_id for item in PROBLEMS if item.status == "Open"}
    assert any(button.label == "Proposed problems" for button in app.button)


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


def test_a_case_in_progress_replaces_the_start_button(api, monkeypatch):
    from datetime import datetime, timezone

    from rca.models import RCARecord

    draft = RCARecord(rca_id="RCA-2026-00001", incident_id="INC-2026-00857", status="DRAFT", owner="pm",
                      created_at=datetime.now(timezone.utc), problem_id=PAYMENT.problem_id)
    monkeypatch.setattr(services, "get_problem", lambda problem_id: {"problem": PAYMENT, "events": [], "rcas": [draft]})
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    app.run()

    assert not app.exception
    assert not any(button.label == "Start RCA" for button in app.button)
    assert any("RCA-2026-00001 is in progress" in item.value for item in app.info)


def test_a_problem_in_manual_resolution_can_only_be_closed(api, monkeypatch):
    manual = PAYMENT.model_copy(update={"status": "Manual"})
    monkeypatch.setattr(services, "get_problem", lambda problem_id: {"problem": manual, "events": [], "rcas": []})
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    app.run()

    assert not app.exception
    assert any("solved by people" in item.value for item in app.warning)
    assert not any(button.label in ("Start RCA", "Reopen") for button in app.button)
    assert any(button.label == "Close the problem" for button in app.button)


def test_the_history_says_which_problems_were_imported_and_shows_the_guide(api, monkeypatch):
    from rca.models import ProblemEvent

    events = [
        ProblemEvent(problem_id=PAYMENT.problem_id, at=PAYMENT.created_at, by="source data", action="created",
                     details={"imported": True}),
        ProblemEvent(problem_id=PAYMENT.problem_id, at="2026-10-13T10:00:00+00:00", by="pm", action="incident_added",
                     incident_id="INC-2026-00371", reason="Same acquirer timeouts."),
        ProblemEvent(problem_id=PAYMENT.problem_id, at="2026-10-13T10:05:00+00:00", by="pm", action="guide_updated",
                     details={"guide": "Check the acquirer certificates."}),
    ]
    monkeypatch.setattr(services, "get_problem", lambda problem_id: {"problem": PAYMENT, "events": events, "rcas": []})
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    app.run()

    assert not app.exception
    text = " ".join(item.value for item in [*app.markdown, *app.caption])
    assert "created the problem (imported from the source data)" in text
    assert "added INC-2026-00371" in text and "Same acquirer timeouts." in text
    assert "updated the guidance for the investigation" in text and "Check the acquirer certificates." in text


def test_start_rca_sends_the_problem_with_the_guidance_and_one_key_per_start(api, monkeypatch):
    from datetime import datetime, timezone

    from rca.models import RCARecord

    started = []

    def start_rca(problem_id, guidance, request_key):
        started.append((problem_id, guidance, request_key))
        return RCARecord(rca_id="RCA-2026-00001", incident_id="INC-2026-00857", status="DRAFT", owner="pm",
                         created_at=datetime.now(timezone.utc), problem_id=problem_id, run_status="RUNNING")

    monkeypatch.setattr(services, "start_rca", start_rca)
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    app.run()
    form = f"guidance_{PAYMENT.problem_id}"
    app.text_area(key=f"{form}_notes").input("Check the connection pool.").run()
    app.text_area(key=f"{form}_instructions").input("Why only on Mondays?").run()
    services_box = app.multiselect(key=f"{form}_services")
    if services_box.options:
        services_box.select(services_box.options[0]).run()
    app.number_input(key=f"{form}_days").set_value(30).run()
    app.number_input(key=f"{form}_hours").set_value(12).run()

    next(button for button in app.button if button.label == "Start RCA").click().run()

    assert len(started) == 1
    problem_id, guidance, key = started[0]
    assert problem_id == PAYMENT.problem_id
    assert (guidance["notes"], guidance["instructions"], guidance["change_window_days"], guidance["log_hours_before"]) == (
        "Check the connection pool.", "Why only on Mondays?", 30, 12)
    assert guidance["extra_services"] == services_box.options[:1]
    assert key  # the same key for a repeated click, so the API returns the same RCA


# One problem: the incident cards, adding with the score, the guide (E7) ------------------------------

CANDIDATES = [
    {"incident_id": "INC-2026-00371", "title": "Card payments slow", "service": "Payment API", "severity": "SEV-2",
     "detected_at": "2026-07-01T10:00:00+00:00", "similarity": 0.93, "alike": True, "closest_incident_id": "INC-2026-00482"},
    {"incident_id": "INC-2026-00411", "title": "Refunds delayed", "service": "Payment API", "severity": "SEV-3",
     "detected_at": "2026-07-02T10:00:00+00:00", "similarity": 0.71, "alike": False, "closest_incident_id": "INC-2026-00857"},
]


def open_payment(api, monkeypatch, problem=None):
    monkeypatch.setattr(services, "problem_candidates", lambda problem_id: CANDIDATES)
    for name in ("set_guidance",):
        monkeypatch.setattr(services, name, lambda *args, _name=name: api.append((_name, args)) or (PAYMENT, []))
    if problem is not None:
        monkeypatch.setattr(services, "get_problem", lambda problem_id: {"problem": problem, "events": [], "rcas": []})
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    return app.run()


def test_every_incident_is_a_card_with_its_details_and_a_remove_that_needs_a_confirmed_reason(api, monkeypatch):
    app = open_payment(api, monkeypatch)

    assert not app.exception
    app.button(key="remove_INC-2026-00857").click().run()
    assert any("Remove INC-2026-00857 from" in item.value for item in app.markdown)  # the confirmation
    app.button(key="remove_confirm_INC-2026-00857").click().run()
    assert app.error and api == []  # no reason: nothing is sent

    app.text_area(key="remove_reason_INC-2026-00857").input("Different acquirer.").run()
    app.button(key="remove_confirm_INC-2026-00857").click().run()
    assert api == [("detach_incident", (PAYMENT.problem_id, "INC-2026-00857", "Different acquirer."))]


def test_the_last_incident_cannot_be_removed(api, monkeypatch):
    alone = PAYMENT.model_copy(update={"incidents": PAYMENT.incidents[:1]})

    app = open_payment(api, monkeypatch, alone)

    remove = app.button(key=f"remove_{alone.incidents[0].incident_id}")
    assert remove.disabled


def test_the_incidents_to_add_come_with_their_similarity_and_an_optional_reason(api, monkeypatch):
    app = open_payment(api, monkeypatch)

    table = app.dataframe[0].value
    assert list(table["incident"]) == ["INC-2026-00371", "INC-2026-00411"]
    assert list(table["similarity"]) == [0.93, 0.71]
    app.selectbox(key="problem_add_choice").select("INC-2026-00371 · Card payments slow · 0.93").run()
    app.text_input(key="add_reason_INC-2026-00371").input("Same acquirer timeouts.").run()
    app.button(key="problem_add").click().run()

    assert api == [("attach_incident", (PAYMENT.problem_id, "INC-2026-00371", "Same acquirer timeouts."))]


def test_without_the_search_index_the_incidents_are_offered_without_a_score(api, monkeypatch):
    def unavailable(problem_id):
        raise services.ServiceError("API Error (503): Similarity scores are not available")

    monkeypatch.setattr(services, "problem_candidates", unavailable)
    app = AppTest.from_file(str(PAGES / "problems.py"), default_timeout=30)
    app.query_params["problem"] = PAYMENT.problem_id
    app.run()

    assert not app.exception
    assert any("not available" in item.value for item in app.caption)
    assert "similarity" not in app.dataframe[0].value.columns or app.dataframe[0].value["similarity"].isna().all()


def test_the_guidance_saved_on_the_problem_is_shown_and_saved_again(api, monkeypatch):
    from rca.models import InvestigationGuidance

    guided = PAYMENT.model_copy(update={"guidance": InvestigationGuidance(notes="Look at the acquirer side.",
                                                                          change_window_days=30)})
    app = open_payment(api, monkeypatch, guided)

    notes = app.text_area(key=f"guidance_{PAYMENT.problem_id}_notes")
    assert notes.value == "Look at the acquirer side."
    assert app.number_input(key=f"guidance_{PAYMENT.problem_id}_days").value == 30
    assert app.button(key="guidance_save").disabled  # nothing changed yet
    notes.input("Look at the acquirer side, and the retry handler.").run()
    app.button(key="guidance_save").click().run()

    assert api == [("set_guidance", (PAYMENT.problem_id, {
        "notes": "Look at the acquirer side, and the retry handler.", "instructions": None, "extra_services": [],
        "change_window_days": 30, "log_hours_before": None}))]


def test_there_is_one_guidance_and_no_separate_guide(api, monkeypatch):
    app = open_payment(api, monkeypatch)

    labels = [item.label for item in app.text_area]
    assert "Investigation guide" not in " ".join(item.value for item in app.markdown)
    assert labels.count("Notes for the investigation") == 1
