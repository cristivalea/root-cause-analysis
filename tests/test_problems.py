"""The Problem Manager's operations on problems, and the rules that protect them (final_project_steps.md, E2)."""

import json
import threading
from pathlib import Path

import pytest

from rca import problems, storage, store
from rca_helpers import make_rca
from rca.models import Incident, InvestigationGuidance, RCARecord
from rca.problems import ProblemConflict, ProblemError

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


def free_incidents(db, count):
    """Incidents in no problem, other than LOOK_ALIKES."""
    return [item.incident_id for item in problems.unassigned_incidents(db) if item.incident_id not in LOOK_ALIKES][:count]


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


def test_an_incident_of_another_problem_is_refused_never_moved(db):
    source = payment_problem(db)
    other = problems.create_problem(LOOK_ALIKES, "pm", db_path=db).problem.problem_id

    free = free_incidents(db, 1)[0]
    with pytest.raises(ProblemConflict, match="already in the open problem"):
        problems.create_problem(["INC-2026-00857", free], "pm", db_path=db)
    with pytest.raises(ProblemConflict, match="belongs to one problem only"):
        problems.attach_incident(other, "INC-2026-00857", "pm", reason="Same acquirer errors.", db_path=db)

    # nothing changed: the incident is still in its problem, and the refused problem was not created
    assert storage.get_problem_id_for_incident(db, "INC-2026-00857") == source
    assert storage.get_problem_id_for_incident(db, free) is None
    assert [link.incident_id for link in storage.get_problem(db, source).incidents] == PAYMENT_PROBLEM_INCIDENTS


def test_an_incident_of_a_closed_problem_is_refused_too(db):
    with pytest.raises(ProblemConflict, match="already in the closed problem"):
        problems.create_problem(["INC-2025-00401"], "pm", db_path=db)
    with pytest.raises(ProblemError, match="closed"):
        problems.detach_incident(closed_problem(db), "INC-2025-00401", "pm", "Not related.", db_path=db)


def test_a_wrong_link_is_undone_by_removing_with_a_reason_then_adding(db):
    source = payment_problem(db)
    other = problems.create_problem(LOOK_ALIKES, "pm", db_path=db).problem.problem_id

    problems.detach_incident(source, "INC-2026-00857", "pm", "Different cause: acquirer outage.", db_path=db)
    problems.attach_incident(other, "INC-2026-00857", "pm", reason="Same acquirer outage.", db_path=db)

    assert storage.get_problem_id_for_incident(db, "INC-2026-00857") == other
    assert problems.problem_events(source, db)[-1].reason == "Different cause: acquirer outage."
    assert problems.problem_events(other, db)[-1].reason == "Same acquirer outage."


def test_a_problem_is_never_left_empty(db):
    source = payment_problem(db)

    problems.detach_incident(source, "INC-2026-00857", "pm", "Different cause.", db_path=db)
    with pytest.raises(ProblemError, match="only incident"):
        problems.detach_incident(source, "INC-2026-00482", "pm", "Different cause.", db_path=db)


def run_together(work, arguments):
    """Run work(argument) for every argument in its own thread, all starting at the same moment."""
    start = threading.Barrier(len(arguments))

    def run(argument):
        start.wait()
        work(argument)

    threads = [threading.Thread(target=run, args=(argument,)) for argument in arguments]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_two_requests_at_the_same_time_never_link_one_incident_twice(db):
    """Two Problem Managers add the same incident to two problems at the same moment: one wins, the other
    is refused, and the incident is in exactly one problem."""
    one, two = free_incidents(db, 2)
    first = problems.create_problem([one], "pm", db_path=db).problem.problem_id
    second = problems.create_problem([two], "pm", db_path=db).problem.problem_id
    outcomes = []

    def add(problem_id):
        try:
            problems.attach_incident(problem_id, "INC-2026-00371", "pm", db_path=db)
            outcomes.append(("added", problem_id))
        except ProblemConflict:
            outcomes.append(("refused", problem_id))

    run_together(add, [first, second])

    assert sorted(kind for kind, _ in outcomes) == ["added", "refused"]
    winner = next(problem_id for kind, problem_id in outcomes if kind == "added")
    assert storage.get_problem_id_for_incident(db, "INC-2026-00371") == winner
    added = [event for problem_id in (first, second) for event in problems.problem_events(problem_id, db)
             if event.incident_id == "INC-2026-00371"]
    assert len(added) == 1  # the refused request left no trace in the history


def test_the_database_itself_refuses_a_second_link_of_one_incident(db, monkeypatch):
    """Even if the check in the code were skipped, the primary key of problem_incidents refuses the link,
    and the refusal comes back as a conflict, with nothing saved."""
    other = problems.create_problem(LOOK_ALIKES, "pm", db_path=db).problem.problem_id
    monkeypatch.setattr(problems, "_check_free", lambda connection, incident_id: None)

    with pytest.raises(ProblemConflict, match="conflicts with a change made at the same time"):
        problems.attach_incident(other, "INC-2026-00857", "pm", db_path=db)

    assert storage.get_problem_id_for_incident(db, "INC-2026-00857") == payment_problem(db)
    assert "INC-2026-00857" not in [event.incident_id for event in problems.problem_events(other, db)]


def test_problems_created_at_the_same_time_get_different_ids(db):
    created, errors = [], []

    def create(incident_id):
        try:
            created.append(problems.create_problem([incident_id], "pm", db_path=db).problem)
        except Exception as exc:  # noqa: BLE001 - the test reports any failure
            errors.append(exc)

    run_together(create, free_incidents(db, 4))

    assert errors == []
    assert len({problem.problem_id for problem in created}) == 4
    for problem in created:  # each one kept its own incident: no problem overwrote another
        saved = storage.get_problem(db, problem.problem_id)
        assert [link.incident_id for link in saved.incidents] == [link.incident_id for link in problem.incidents]


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


def test_no_incident_is_added_or_removed_while_the_rca_of_the_problem_is_in_progress(db):
    source = payment_problem(db)
    store.begin_rca(source, "pm", None, db_path=db)
    assert storage.get_problem(db, source).status == "In investigation"

    with pytest.raises(ProblemError, match="in investigation"):
        problems.detach_incident(source, "INC-2026-00857", "pm", "Different acquirer.", db_path=db)
    with pytest.raises(ProblemError, match="in investigation"):
        problems.attach_incident(source, "INC-2026-00411", "pm", "Same timeouts.", db_path=db)

    assert {link.incident_id for link in storage.get_problem(db, source).incidents} == {
        "INC-2026-00482", "INC-2026-00857"}

def test_different_services_or_incidents_far_apart_are_allowed_with_a_warning(db):
    other_service = next(item.incident_id for item in problems.unassigned_incidents(db) if item.service != "Payment API")
    old = next(item.incident_id for item in problems.unassigned_incidents(db)
               if item.service == "Payment API" and item.detected_at.year == 2024)

    result = problems.create_problem(["INC-2026-00371", other_service, old], "pm", db_path=db)

    assert any("different services" in item for item in result.warnings)
    assert any("days apart" in item for item in result.warnings)


def test_an_rca_in_progress_blocks_closing_and_adding_an_incident(db):
    source = payment_problem(db)
    make_rca(db, source, sample_record(), "draft")

    with pytest.raises(ProblemError, match="still in progress"):
        problems.close_problem(source, "pm", "Known vendor bug.", db_path=db)
    with pytest.raises(ProblemError, match="in investigation"):
        problems.attach_incident(source, "INC-2026-00371", "pm", db_path=db)

    assert storage.get_problem(db, source).status == "In investigation"


def test_a_problem_can_be_closed_with_a_reason_when_no_rca_is_needed(db):
    created = problems.create_problem(LOOK_ALIKES, "pm", db_path=db).problem

    closed = problems.close_problem(created.problem_id, "pm", "Vendor outage, confirmed by the vendor.", db_path=db).problem

    assert closed.status == "Closed" and closed.close_reason == "Vendor outage, confirmed by the vendor."
    assert closed.closed_at is not None
    assert created.problem_id in [item.problem_id for item in problems.list_problems("Closed", db_path=db)]


def test_an_incident_removed_from_a_problem_is_in_no_problem_again(db):
    source = payment_problem(db)
    problems.attach_incident(source, "INC-2026-00371", "pm", db_path=db)
    assert "INC-2026-00371" not in [item.incident_id for item in problems.unassigned_incidents(db)]

    problems.detach_incident(source, "INC-2026-00371", "pm", "Wrong problem.", db_path=db)

    assert "INC-2026-00371" in [item.incident_id for item in problems.unassigned_incidents(db)]
    assert not hasattr(problems, "dismiss_incident")  # no incident is set aside as needing no problem


def test_an_incident_on_its_own_cannot_be_rejected(db):
    from rca import suggestions

    key = suggestions.proposal_key("single", ["INC-2026-00371"])
    with pytest.raises(ProblemError, match="cannot be rejected"):
        problems.reject_proposal(key, "single", ["INC-2026-00371"], "pm", db_path=db)

def test_an_incident_is_added_with_an_optional_reason_kept_in_the_history(db):
    source = payment_problem(db)

    problems.attach_incident(source, "INC-2026-00371", "pm", reason="  Same acquirer timeouts. ", db_path=db)
    problems.attach_incident(source, "INC-2026-00411", "pm", db_path=db)

    added = [event for event in problems.problem_events(source, db) if event.action == "incident_added"][-2:]
    assert [(event.incident_id, event.by, event.reason) for event in added] == [
        ("INC-2026-00371", "pm", "Same acquirer timeouts."), ("INC-2026-00411", "pm", None)]


def test_the_guidance_is_saved_on_the_problem_with_its_history(db):
    source = payment_problem(db)
    first = InvestigationGuidance(notes=" Check the acquirer certificates. ", change_window_days=30)

    problems.set_guidance(source, first, "pm", db_path=db)
    problems.set_guidance(source, first, "pm", db_path=db)  # the same guidance: nothing changes
    problems.set_guidance(source, InvestigationGuidance(instructions="Why only on Mondays?",
                                                        extra_services=["Network Services"]), "pm2", db_path=db)
    result = problems.set_guidance(source, InvestigationGuidance(notes="  "), "pm", db_path=db)  # empty: cleared

    assert result.problem.guidance is None
    changes = [(event.by, event.details.get("guidance")) for event in problems.problem_events(source, db)
               if event.action == "guide_updated"]
    assert [by for by, _ in changes] == ["pm", "pm2", "pm"]
    assert changes[0][1]["notes"] == "Check the acquirer certificates." and changes[0][1]["change_window_days"] == 30
    assert changes[1][1]["extra_services"] == ["Network Services"] and changes[2][1] is None


def test_the_guidance_is_checked_and_a_closed_problem_keeps_its_own(db):
    with pytest.raises(ProblemError, match="too long"):
        problems.set_guidance(payment_problem(db), InvestigationGuidance(notes="x" * (problems.MAX_GUIDE_LENGTH + 1)),
                              "pm", db_path=db)
    with pytest.raises(ProblemError, match="not in the CMDB"):
        problems.set_guidance(payment_problem(db), InvestigationGuidance(extra_services=["Mainframe"]), "pm", db_path=db)
    with pytest.raises(ProblemError, match="stays as it was"):
        problems.set_guidance(closed_problem(db), InvestigationGuidance(notes="Check again."), "pm", db_path=db)


@pytest.mark.parametrize("severities, priority", [
    (["SEV-1"], "P1"), (["SEV-4"], "P4"), (["SEV-3", "SEV-2"], "P2"), (["SEV-4", "SEV-3", "SEV-1"], "P1"),
])
def test_the_priority_is_the_severity_of_the_most_severe_incident(severities, priority):
    assert problems._priority([Incident.model_construct(severity=severity) for severity in severities]) == priority


def test_the_problems_of_the_source_data_have_an_imported_created_event(db):
    problem_id = payment_problem(db)
    events = problems.problem_events(problem_id, db)

    assert events[0].action == "created" and events[0].details == {"imported": True}
    assert events[0].at == storage.get_problem(db, problem_id).created_at


def test_unknown_ids_are_refused(db):
    with pytest.raises(ProblemError, match="INC-2099-00001"):
        problems.create_problem(["INC-2099-00001"], "pm", db_path=db)
    with pytest.raises(ProblemError, match="PRB-2099-00001"):
        problems.attach_incident("PRB-2099-00001", "INC-2026-00371", "pm", db_path=db)
    with pytest.raises(ProblemError, match="at least one incident"):
        problems.create_problem([" "], "pm", db_path=db)


# Starting an RCA (check_can_start, called by store.start_rca) and what the decisions do to the problem ----


def sample_record() -> RCARecord:
    return RCARecord.model_validate(json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(
        encoding="utf-8")))


def test_only_one_rca_at_a_time_and_its_next_revision_continues_it(db):
    problem_id = payment_problem(db)
    rca = make_rca(db, problem_id, sample_record(), "draft", "submit", "more")

    with pytest.raises(ProblemError, match="one RCA at a time"):
        problems.check_can_start(problem_id, db_path=db)
    assert store.start_next_revision(rca.rca_id, "pm", db_path=db).revision == 2  # the same RCA continues


def test_a_failed_run_keeps_the_rca_in_progress_and_is_run_again_not_started_again(db):
    problem_id = payment_problem(db)
    rca = make_rca(db, problem_id, sample_record(), "fail")

    with pytest.raises(ProblemError, match="in progress \\(FAILED\\)"):
        problems.check_can_start(problem_id, db_path=db)
    store.start_next_revision(rca.rca_id, "pm", db_path=db)


def test_after_a_rejection_a_new_rca_needs_something_new(db):
    problem_id = payment_problem(db)
    make_rca(db, problem_id, sample_record(), "draft", "submit", "reject")

    with pytest.raises(ProblemError, match="same input would give the same answer"):
        problems.check_can_start(problem_id, db_path=db)
    problems.check_can_start(problem_id, InvestigationGuidance(notes="Check the retry handler."), db_path=db)
    problems.attach_incident(problem_id, "INC-2026-00371", "pm", db_path=db)
    problems.check_can_start(problem_id, db_path=db)  # a new incident is something new too


def test_changed_guidance_after_a_rejection_is_something_new(db):
    problem_id = payment_problem(db)
    make_rca(db, problem_id, sample_record(), "draft", "submit", "reject")

    problems.set_guidance(problem_id, InvestigationGuidance(notes="Look at the acquirer side."), "pm", db_path=db)

    problems.check_can_start(problem_id, db_path=db)


def test_the_second_rejected_rca_sends_the_problem_to_manual_review(db):
    problem_id = payment_problem(db)
    make_rca(db, problem_id, sample_record(), "draft", "submit", "reject")
    assert storage.get_problem(db, problem_id).status == "Open"  # one rejection: open again

    make_rca(db, problem_id, sample_record(), "draft", "submit", "reject",
             guidance=InvestigationGuidance(change_window_days=30))

    assert storage.get_problem(db, problem_id).status == "Manual"
    assert problems.problem_events(problem_id, db)[-1].action == "manual"
    with pytest.raises(ProblemError, match="manual review"):
        problems.check_can_start(problem_id, InvestigationGuidance(notes="Try again."), db_path=db)
    with pytest.raises(ProblemError, match="manual review"):
        problems.reopen_problem(problem_id, "pm", "Try again.", db_path=db)
    with pytest.raises(ProblemError, match="manual review"):
        problems.attach_incident(problem_id, "INC-2026-00371", "pm", db_path=db)
    closed = problems.close_problem(problem_id, "pm", "Fixed by the vendor, confirmed manually.", db_path=db).problem
    assert closed.status == "Closed"


def test_an_rca_escalated_after_its_last_decision_sends_the_problem_to_manual_review(db):
    problem_id = payment_problem(db)

    make_rca(db, problem_id, sample_record(), "draft", "submit", "more", "next", "draft", "submit", "more", "next",
             "draft", "submit", "more")

    assert storage.get_problem(db, problem_id).status == "Manual"


def test_a_problem_in_investigation_is_not_closed_or_reopened_by_hand(db):
    problem_id = payment_problem(db)
    make_rca(db, problem_id, sample_record(), "draft")

    with pytest.raises(ProblemError, match="in investigation"):
        problems.reopen_problem(problem_id, "pm", "Again.", db_path=db)


def test_a_closed_problem_gets_no_rca(db):
    with pytest.raises(ProblemError, match="closed; reopen it first"):
        problems.check_can_start(closed_problem(db), db_path=db)
