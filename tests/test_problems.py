"""The Problem Manager's operations on problems, and the rules that protect them (audit O.10)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from rca import problems, storage, store
from rca.models import RCARecord
from rca.problems import ProblemError

ROOT = Path(__file__).resolve().parents[1]
PAYMENT_PROBLEM_INCIDENTS = ["INC-2026-00482", "INC-2026-00857"]  # STORY-002
LOOK_ALIKES = ["INC-2026-00371", "INC-2026-00411"]  # unassigned Payment API incidents with other causes


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


def payment_problem(db) -> str:
    return storage.get_problem_id_for_incident(db, "INC-2026-00482")


def closed_problem(db) -> str:
    return storage.get_problem_id_for_incident(db, "INC-2025-00401")  # linked by RCA-2025-00114


def actions(problem_id, db):
    return [(event.action, event.incident_id) for event in problems.problem_events(problem_id, db)]


def test_a_problem_is_created_from_incidents_in_no_problem(db):
    result = problems.create_problem(LOOK_ALIKES, "pm", db_path=db)
    problem = result.problem

    assert problem.status == "Open" and problem.created_by == "pm"
    assert [link.incident_id for link in problem.incidents] == LOOK_ALIKES  # in the order they happened
    assert problem.title == storage.get_incident(db, "INC-2026-00411").title  # the most recent incident
    assert problem.priority == "P2" and problem.services == ["Payment API"]
    assert all(link.linked_by == "pm" for link in problem.incidents)
    assert actions(problem.problem_id, db) == [("created", None), ("incident_added", "INC-2026-00371"),
                                               ("incident_added", "INC-2026-00411")]
    assert problem.problem_id > max(item.problem_id for item in problems.list_problems(db_path=db)
                                    if item.problem_id != problem.problem_id and item.problem_id[4:8] == problem.problem_id[4:8])


def test_an_incident_of_another_problem_moves_only_with_a_reason(db):
    source = payment_problem(db)

    with pytest.raises(ProblemError, match="Give a reason to move it"):
        problems.create_problem(["INC-2026-00857", "INC-2026-00371"], "pm", db_path=db)

    moved = problems.create_problem(["INC-2026-00857", "INC-2026-00371"], "pm", move_reason="Same acquirer errors.", db_path=db)

    assert storage.get_problem_id_for_incident(db, "INC-2026-00857") == moved.problem.problem_id
    assert [link.incident_id for link in storage.get_problem(db, source).incidents] == ["INC-2026-00482"]
    assert ("incident_moved_out", "INC-2026-00857") in actions(source, db)
    assert problems.problem_events(source, db)[-1].reason == "Same acquirer errors."


def test_a_problem_is_never_left_empty(db):
    source = payment_problem(db)

    with pytest.raises(ProblemError, match="all the incidents"):
        problems.create_problem(PAYMENT_PROBLEM_INCIDENTS, "pm", move_reason="Regroup.", db_path=db)
    problems.detach_incident(source, "INC-2026-00857", "pm", "Different cause.", db_path=db)
    with pytest.raises(ProblemError, match="only incident"):
        problems.detach_incident(source, "INC-2026-00482", "pm", "Different cause.", db_path=db)
    with pytest.raises(ProblemError, match="only incident"):
        problems.create_problem(["INC-2026-00482"], "pm", move_reason="Regroup.", db_path=db)


def test_the_incidents_of_a_closed_problem_stay_where_its_rca_put_them(db):
    with pytest.raises(ProblemError, match="closed problem"):
        problems.create_problem(["INC-2025-00401"], "pm", move_reason="Looks the same.", db_path=db)
    with pytest.raises(ProblemError, match="closed"):
        problems.detach_incident(closed_problem(db), "INC-2025-00401", "pm", "Not related.", db_path=db)


def test_a_closed_problem_gets_no_new_incident_until_it_is_reopened(db):
    target = closed_problem(db)

    with pytest.raises(ProblemError, match="Reopen it"):
        problems.attach_incident(target, "INC-2026-00371", "pm", db_path=db)

    problems.reopen_problem(target, "pm", "Came back after the fix.", db_path=db)
    result = problems.attach_incident(target, "INC-2026-00371", "pm", db_path=db)

    assert "INC-2026-00371" in [link.incident_id for link in result.problem.incidents]
    assert actions(target, db)[-2:] == [("reopened", None), ("incident_added", "INC-2026-00371")]


def test_removing_an_incident_needs_a_reason_and_updates_the_priority(db):
    source = payment_problem(db)  # INC-2026-00482 is SEV-1, INC-2026-00857 SEV-2

    with pytest.raises(ProblemError, match="reason"):
        problems.detach_incident(source, "INC-2026-00482", "pm", " ", db_path=db)
    result = problems.detach_incident(source, "INC-2026-00482", "pm", "Separate outage.", db_path=db)

    assert [link.incident_id for link in result.problem.incidents] == ["INC-2026-00857"]
    assert result.problem.priority == "P2"


def test_different_services_or_incidents_far_apart_are_allowed_with_a_warning(db):
    other_service = next(item.incident_id for item in problems.unassigned_incidents(db) if item.service != "Payment API")
    old = next(item.incident_id for item in problems.unassigned_incidents(db)
               if item.service == "Payment API" and item.detected_at.year == 2024)

    result = problems.create_problem(["INC-2026-00371", other_service, old], "pm", db_path=db)

    assert any("different services" in item for item in result.warnings)
    assert any("days apart" in item for item in result.warnings)


def test_an_rca_in_progress_blocks_closing_and_is_named_when_an_incident_is_added(db):
    source = payment_problem(db)
    now = datetime.now(timezone.utc)
    store.save_rca(RCARecord(rca_id="RCA-2026-00001", incident_id="INC-2026-00857", status="DRAFT", owner="pm",
                             created_at=now, problem_id=source), db_path=db)

    with pytest.raises(ProblemError, match="still in progress"):
        problems.close_problem(source, "pm", "Known vendor bug.", db_path=db)
    result = problems.attach_incident(source, "INC-2026-00371", "pm", db_path=db)

    assert any("RCA-2026-00001 is in progress" in item for item in result.warnings)


def test_a_problem_can_be_closed_with_a_reason_when_no_rca_is_needed(db):
    created = problems.create_problem(LOOK_ALIKES, "pm", db_path=db).problem

    closed = problems.close_problem(created.problem_id, "pm", "Vendor outage, confirmed by the vendor.", db_path=db).problem

    assert closed.status == "Closed" and closed.close_reason == "Vendor outage, confirmed by the vendor."
    assert closed.closed_at is not None
    assert created.problem_id in [item.problem_id for item in problems.list_problems("Closed", db_path=db)]


def test_an_incident_marked_as_needing_no_problem_is_no_longer_listed(db):
    assert "INC-2026-00371" in [item.incident_id for item in problems.unassigned_incidents(db)]

    problems.dismiss_incident("INC-2026-00371", "pm", "Vendor slowdown, no action on our side.", db_path=db)

    assert "INC-2026-00371" not in [item.incident_id for item in problems.unassigned_incidents(db)]
    with pytest.raises(ProblemError, match="remove it from the problem first"):
        problems.dismiss_incident("INC-2026-00482", "pm", "Not needed.", db_path=db)
    # attaching it later undoes the mark
    problems.attach_incident(payment_problem(db), "INC-2026-00371", "pm", db_path=db)
    problems.detach_incident(payment_problem(db), "INC-2026-00371", "pm", "Wrong problem.", db_path=db)
    assert "INC-2026-00371" in [item.incident_id for item in problems.unassigned_incidents(db)]


def test_unknown_ids_are_refused(db):
    with pytest.raises(ProblemError, match="INC-2099-00001"):
        problems.create_problem(["INC-2099-00001"], "pm", db_path=db)
    with pytest.raises(ProblemError, match="PRB-2099-00001"):
        problems.attach_incident("PRB-2099-00001", "INC-2026-00371", "pm", db_path=db)
    with pytest.raises(ProblemError, match="at least one incident"):
        problems.create_problem([" "], "pm", db_path=db)
