"""The Proposed Problem Records page, with the API replaced by fixed answers (no login, no server)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rca.models import Incident, Problem
from rca.suggestions import SCORE_LABEL, SCORE_MEANING
from rca.ui import services
from rca.ui.strings import t

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "rca" / "ui" / "app_pages" / "proposals.py")
INCIDENTS = [Incident.model_validate(item) for item in json.loads((ROOT / "data/sources/incidents.json").read_text(encoding="utf-8"))]
PROBLEM = Problem.model_validate(json.loads((ROOT / "data/sources/problems.json").read_text(encoding="utf-8"))[0])


def proposal(kind, incident_ids, problem_id=None, score=0.93):
    return {"key": f"PP-{kind}", "kind": kind, "incident_ids": incident_ids, "problem_id": problem_id, "score": score,
            "reasons": [f"Reason of the {kind} proposal."], "evidence": [f"Evidence of the {kind} proposal."],
            "recurrence_of": None, "score_label": SCORE_LABEL, "score_meaning": SCORE_MEANING}


PROPOSALS = [
    proposal("group", ["INC-2026-00371", "INC-2026-00411"]),
    proposal("attach", ["INC-2026-00857"], "PRB-2026-00001", 0.97),
]


@pytest.fixture
def api(monkeypatch):
    calls = []
    monkeypatch.setattr(services, "list_proposals", lambda: PROPOSALS)
    monkeypatch.setattr(services, "list_incidents", lambda: INCIDENTS)
    monkeypatch.setattr(services, "accept_proposal",
                        lambda item, title=None, reason=None: calls.append(("accept", item["key"], title, reason))
                        or (PROBLEM, [], True))
    monkeypatch.setattr(services, "reject_proposal",
                        lambda item, reason=None: calls.append(("reject", item["key"], reason)))
    return calls


def test_the_three_kinds_are_listed_with_their_score_explained_reasons_and_evidence(api):
    app = AppTest.from_file(PAGE, default_timeout=30).run()

    assert not app.exception
    labels = [tab.label for tab in app.tabs]
    assert labels == [t("proposals.kind.group", count=1), t("proposals.kind.attach", count=1),
                      t("proposals.kind.single", count=0)]  # no tab to create a problem by hand
    text = " ".join(item.value for item in app.markdown)
    assert "Reason of the group proposal." in text and "Evidence of the attach proposal." in text
    assert "`INC-2026-00371`" in text
    assert [metric.value for metric in app.metric] == ["0.93", "0.97"]
    assert any("not the probability" in caption.value for caption in app.caption)
    assert any(t("proposals.none.single") in item.value for item in app.info)


def test_accepting_sends_the_proposal_and_names_the_problem_it_made(api):
    app = AppTest.from_file(PAGE, default_timeout=30).run()
    app.text_input(key="title-PP-group").input("Card payments time out").run()

    app.button(key="accept-PP-group").click().run()

    assert api == [("accept", "PP-group", "Card payments time out", None)]
    assert any(t("proposals.done_created", problem=PROBLEM.problem_id) in item.value for item in app.markdown)
    assert any(button.label == t("proposals.open_problems") for button in app.button)


def test_rejecting_sends_the_reason(api):
    app = AppTest.from_file(PAGE, default_timeout=30).run()
    app.text_input(key="why-PP-attach").input("Different acquirer.").run()

    app.button(key="reject-PP-attach").click().run()

    assert api == [("reject", "PP-attach", "Different acquirer.")]


def test_a_refused_accept_says_why(api, monkeypatch):
    def refuse(item, title=None, reason=None):
        raise services.ServiceError("API Error (409): INC-2026-00371 is already in the open problem PRB-2026-00009.")

    monkeypatch.setattr(services, "accept_proposal", refuse)
    app = AppTest.from_file(PAGE, default_timeout=30).run()

    app.button(key="accept-PP-group").click().run()

    assert any("already in the open problem PRB-2026-00009" in item.value for item in app.error)


@pytest.mark.skipif(not (ROOT / "chroma_db").exists(), reason="run scripts/ingest_chroma.py first")
def test_through_the_real_api_accepting_a_group_makes_its_problem():
    """No fixed answers: the page, the API and a copy of the data (tests/conftest.py, ui_through_the_api)."""
    found = services.list_proposals()
    group = next(item for item in found if item["kind"] == "group")
    app = AppTest.from_file(PAGE, default_timeout=60).run()

    app.button(key=f"accept-{group['key']}").click().run()

    assert not app.exception
    created = next(problem for problem in services.list_problems() if
                   {link.incident_id for link in problem.incidents} == set(group["incident_ids"]))
    assert any(t("proposals.done_created", problem=created.problem_id) in item.value for item in app.markdown)
    assert group["key"] not in {item["key"] for item in services.list_proposals()}


def test_an_incident_on_its_own_can_be_accepted_but_not_rejected(api, monkeypatch):
    monkeypatch.setattr(services, "list_proposals", lambda: PROPOSALS + [proposal("single", ["INC-2026-00482"], score=None)])

    app = AppTest.from_file(PAGE, default_timeout=30).run()

    assert not app.exception
    keys = [button.key for button in app.button]
    assert "accept-PP-single" in keys and "reject-PP-single" not in keys
    assert "reject-PP-group" in keys and "reject-PP-attach" in keys


def test_an_incident_on_its_own_names_the_closed_problem_its_score_compares_it_to(api, monkeypatch):
    alone = proposal("single", ["INC-2026-00482"], score=0.98)
    alone["recurrence_of"] = "PRB-2025-00010"
    monkeypatch.setattr(services, "list_proposals", lambda: [alone])

    app = AppTest.from_file(PAGE, default_timeout=30).run()

    assert not app.exception
    assert [metric.label for metric in app.metric] == [t("proposals.score_to", problem="PRB-2025-00010")]
