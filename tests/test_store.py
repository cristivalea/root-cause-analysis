"""The lifecycle of an RCA (rca/store.py): every allowed change, every refused one, and the problem with it."""

import json
import threading
from pathlib import Path

import pytest

from rca import problems, storage, store
from rca.models import InvestigationGuidance, RCARecord
from rca.store import TransitionError
from rca_helpers import make_rca

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def sample_record() -> RCARecord:
    return RCARecord.model_validate(json.loads((FIXTURES / "sample_rca_record.json").read_text(encoding="utf-8")))


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


@pytest.fixture
def problem(db):
    return storage.get_problem_id_for_incident(db, "INC-2026-00482")


def status_of(db, problem_id):
    return storage.get_problem(db, problem_id).status


def transitions(db, rca_id):
    return [(item.from_status, item.to_status) for item in store.status_history(rca_id, db)]


# ---- Starting ----


def test_starting_an_rca_creates_its_first_revision_and_puts_the_problem_in_investigation(db, problem):
    revision = store.start_rca(problem, "pm", InvestigationGuidance(notes="Check the pool."), db_path=db)

    assert (revision.rca_id, revision.revision_id, revision.run_status) == ("RCA-2026-00001", "RCA-2026-00001-R1", "RUNNING")
    assert revision.guidance.notes == "Check the pool."
    summary = store.get_summary(revision.rca_id, db)
    assert (summary.status, summary.problem_id, summary.revisions, summary.created_by) == ("DRAFT", problem, 1, "pm")
    assert status_of(db, problem) == "In investigation"
    assert problem not in [item.problem_id for item in problems.list_problems("Open", db_path=db)]
    assert problem in [item.problem_id for item in problems.list_problems("In investigation", db_path=db)]
    events = problems.problem_events(problem, db)[-2:]
    assert [(event.action, event.rca_id, event.details["to"]) for event in events] == [
        ("rca_status", "RCA-2026-00001", "DRAFT"), ("status_changed", "RCA-2026-00001", "In investigation")]


def test_a_problem_has_one_rca_at_a_time_even_for_two_requests_at_the_same_moment(db, problem):
    start, outcomes = threading.Barrier(2), []

    def begin():
        start.wait()
        try:
            outcomes.append(store.start_rca(problem, "pm", db_path=db).rca_id)
        except problems.ProblemError as exc:
            outcomes.append(str(exc))

    threads = [threading.Thread(target=begin) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes)[0] == "RCA-2026-00001"
    assert "one RCA at a time" in sorted(outcomes)[1]
    assert len(store.list_summaries(db_path=db)) == 1


def test_the_ids_continue_the_rcas_saved_before_the_redesign(db, problem):
    import sqlite3

    with sqlite3.connect(db) as connection:  # the table of the older version, as a migrated database keeps it
        connection.execute("CREATE TABLE rca_records (rca_id TEXT PRIMARY KEY, incident_id TEXT, status TEXT, "
                           "created_at TEXT, updated_at TEXT, payload TEXT)")
        connection.execute("INSERT INTO rca_records VALUES ('RCA-2026-00137', 'x', 'x', 'x', 'x', '{}')")

    assert store.start_rca(problem, "pm", db_path=db).rca_id == "RCA-2026-00138"


# ---- The end of a run ----


def test_a_draft_is_saved_once_and_never_changed(db, problem):
    rca = make_rca(db, problem, sample_record(), "draft")

    assert (rca.status, rca.run_status) == ("DRAFT", "COMPLETED")
    store.complete_revision(rca, "DRAFT", db_path=db)  # the same save again, after a technical retry: nothing happens
    assert len(store.list_revisions(rca.rca_id, db)) == 1
    with pytest.raises(TransitionError, match="never changed"):
        store.complete_revision(rca.model_copy(update={"investigation_summary": "Other."}), "DRAFT", db_path=db)


def test_a_draft_refused_by_the_guardrail_in_every_attempt_escalates_the_rca_and_the_problem(db, problem):
    rca = make_rca(db, problem, sample_record(), "escalate")

    assert rca.status == "ESCALATED_MANUAL"
    assert status_of(db, problem) == "Manual"
    with pytest.raises(problems.ProblemError, match="manual review"):
        store.start_rca(problem, "pm", db_path=db)


def test_a_technical_error_is_failed_kept_with_its_error_and_can_run_again(db, problem):
    rca = make_rca(db, problem, sample_record(), "fail")

    assert (rca.status, rca.run_status, rca.error) == ("FAILED", "FAILED", "ConnectionError after investigation_planner")
    assert status_of(db, problem) == "In investigation"  # nothing was concluded: the problem waits
    again = store.start_next_revision(rca.rca_id, "pm", db_path=db)
    assert (again.revision_id, again.previous_revision_id) == ("RCA-2026-00001-R2", "RCA-2026-00001-R1")
    assert store.get_summary(rca.rca_id, db).status == "DRAFT"
    assert store.get_rca("RCA-2026-00001-R1", db).status == "FAILED"  # the failed run stays as it was


def test_fail_revision_ends_only_a_running_revision(db, problem):
    revision = store.start_rca(problem, "pm", db_path=db)

    failed = store.fail_revision(revision.revision_id, "RateLimitError after rca_reasoning_agent: limit", db_path=db)

    assert (failed.status, failed.error) == ("FAILED", "RateLimitError after rca_reasoning_agent: limit")
    assert store.fail_revision(revision.revision_id, "again", db_path=db).error == failed.error


# ---- Sending to the expert and the decisions ----


def test_only_a_completed_draft_is_sent_and_only_once(db, problem):
    revision = store.start_rca(problem, "pm", db_path=db)
    with pytest.raises(TransitionError, match="still running"):
        store.submit_for_review(revision.rca_id, "pm", db_path=db)

    rca = make_rca(db, storage.get_problem_id_for_incident(db, "INC-2026-00101"), sample_record(), "draft", "submit")
    assert rca.status == "AWAITING_TECHNICAL_REVIEW"
    assert store.get_summary(rca.rca_id, db).sent_to_expert
    with pytest.raises(TransitionError, match="only a draft"):
        store.submit_for_review(rca.rca_id, "pm", db_path=db)


def test_the_expert_decides_only_on_an_rca_waiting_for_a_decision(db, problem):
    draft = make_rca(db, problem, sample_record(), "draft")
    with pytest.raises(TransitionError, match="waiting for review"):
        store.apply_review(draft.rca_id, "expert", "APPROVE", "", "HYP-001", db_path=db)

    other = storage.get_problem_id_for_incident(db, "INC-2026-00101")
    rejected = make_rca(db, other, sample_record(), "draft", "submit", "reject")
    with pytest.raises(TransitionError, match="REJECTED"):  # a rejected RCA is never approved afterwards
        store.apply_review(rejected.rca_id, "expert", "APPROVE", "", "HYP-001", db_path=db)


def test_validating_closes_the_problem_with_the_rca_and_its_root_cause(db, problem):
    record = sample_record()
    rca = make_rca(db, problem, record, "draft", "submit", "approve")

    assert rca.status == "VALIDATED"
    assert rca.final_root_cause == record.hypotheses[0].candidate_root_cause
    assert (rca.review.decision, rca.review.reviewer) == ("APPROVE", "expert")
    closed = storage.get_problem(db, problem)
    assert (closed.status, closed.rca_id) == ("Closed", rca.rca_id)
    assert transitions(db, rca.rca_id) == [(None, "DRAFT"), ("DRAFT", "AWAITING_TECHNICAL_REVIEW"),
                                           ("AWAITING_TECHNICAL_REVIEW", "VALIDATED")]


def test_a_rejection_reopens_the_problem_and_the_second_one_sends_it_to_manual_review(db, problem):
    first = make_rca(db, problem, sample_record(), "draft", "submit", "reject")
    assert (first.status, status_of(db, problem)) == ("REJECTED", "Open")

    problems.set_guidance(problem, InvestigationGuidance(notes="Check the retry handler."), "pm", db_path=db)  # new
    second = make_rca(db, problem, sample_record(), "draft", "submit", "reject")

    assert second.status == "REJECTED" and status_of(db, problem) == "Manual"


def test_a_decision_needs_its_comment_and_a_known_hypothesis(db, problem):
    rca = make_rca(db, problem, sample_record(), "draft", "submit")

    with pytest.raises(store.RCAError, match="comment is required"):
        store.apply_review(rca.rca_id, "expert", "REJECT", "  ", db_path=db)
    with pytest.raises(store.RCAError, match="HYP-099"):
        store.apply_review(rca.rca_id, "expert", "APPROVE", "", "HYP-099", db_path=db)
    with pytest.raises(store.RCAError, match="Unknown decision"):
        store.apply_review(rca.rca_id, "expert", "MAYBE", "Hmm.", db_path=db)
    assert store.get_summary(rca.rca_id, db).status == "AWAITING_TECHNICAL_REVIEW"  # nothing changed


def test_a_request_for_more_details_starts_a_new_revision_and_keeps_the_previous_one_as_it_was(db, problem):
    rca = make_rca(db, problem, sample_record(), "draft", "submit")
    before = store.get_rca("RCA-2026-00001-R1", db).model_dump(exclude={"status", "review", "review_rounds"})

    asked = store.apply_review(rca.rca_id, "expert", "REQUEST_MORE_DETAILS", "Check the pool size.", db_path=db,
                               requested_checks=["pool size"], guidance=InvestigationGuidance(change_window_days=30))
    assert (asked.status, asked.review.requested_checks) == ("REQUEST_MORE_DETAILS", ["pool size"])
    assert store.open_request(rca.rca_id, db).comment == "Check the pool size."
    assert status_of(db, problem) == "In investigation"

    store.start_next_revision(rca.rca_id, "pm", db_path=db)
    first = store.get_rca("RCA-2026-00001-R1", db)
    assert first.model_dump(exclude={"status", "review", "review_rounds"}) == before  # the revision itself never changes
    assert (first.status, first.review.comment) == ("REQUEST_MORE_DETAILS", "Check the pool size.")
    assert store.get_rca(rca.rca_id, db).revision_id == "RCA-2026-00001-R2"


def test_the_third_request_for_more_details_escalates_and_failed_runs_do_not_count(db, problem):
    rca = make_rca(db, problem, sample_record(), "draft", "submit", "more", "next", "fail", "next", "draft", "submit",
                   "more", "next", "draft", "submit")
    assert (rca.revision, rca.review_rounds) == (4, 2)  # 4 runs, one failed; 2 decisions so far

    escalated = store.apply_review(rca.rca_id, "expert", "REQUEST_MORE_DETAILS", "Still unclear.", db_path=db)

    assert escalated.status == "ESCALATED_MANUAL"
    assert status_of(db, problem) == "Manual"
    assert len(store.list_revisions(rca.rca_id, db)) == 4  # every revision is kept
    with pytest.raises(TransitionError):
        store.start_next_revision(rca.rca_id, "pm", db_path=db)


@pytest.mark.parametrize("steps, operation", [
    (("draft",), "next"), (("draft", "submit"), "next"), (("draft", "submit"), "submit"),
    (("draft", "submit", "approve"), "next"), (("draft", "submit", "approve"), "submit"),
    (("draft", "submit", "reject"), "next"), (("draft", "submit", "more"), "submit"),
    (("draft", "submit", "more"), "approve"), (("fail",), "submit"), (("escalate",), "next"),
])
def test_every_change_the_lifecycle_does_not_allow_is_refused(db, problem, steps, operation):
    rca = make_rca(db, problem, sample_record(), *steps)
    status = rca.status
    actions = {
        "next": lambda: store.start_next_revision(rca.rca_id, "pm", db_path=db),
        "submit": lambda: store.submit_for_review(rca.rca_id, "pm", db_path=db),
        "approve": lambda: store.apply_review(rca.rca_id, "expert", "APPROVE", "", "HYP-001", db_path=db),
    }

    with pytest.raises(store.RCAError):
        actions[operation]()

    assert store.get_summary(rca.rca_id, db).status == status


def test_the_history_of_the_problem_tells_what_happened_to_its_rca(db, problem):
    rca = make_rca(db, problem, sample_record(), "draft", "submit", "more", "next", "draft", "submit", "approve")

    changes = [(event.details.get("from"), event.details.get("to")) for event in problems.problem_events(problem, db)
               if event.action == "rca_status" and event.rca_id == rca.rca_id]
    assert changes == [(None, "DRAFT"), ("DRAFT", "AWAITING_TECHNICAL_REVIEW"),
                       ("AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS"), ("REQUEST_MORE_DETAILS", "DRAFT"),
                       ("DRAFT", "AWAITING_TECHNICAL_REVIEW"), ("AWAITING_TECHNICAL_REVIEW", "VALIDATED")]
    assert problems.problem_events(problem, db)[-1].action == "closed"


def test_the_expert_request_reads_as_the_comment_and_the_checks():
    from datetime import datetime, timezone

    from rca.models import ReviewDecision

    review = ReviewDecision(reviewer="expert", decision="REQUEST_MORE_DETAILS", comment="Check the pool.",
                            decided_at=datetime.now(timezone.utc), requested_checks=["pool size", "Check the pool."])

    assert store.expert_request(review) == "Check the pool.\n- pool size"  # a check equal to the comment is said once

    lines = ReviewDecision(reviewer="expert", decision="REQUEST_MORE_DETAILS", comment="check the secrets\ncheck the DNS changes",
                           decided_at=datetime.now(timezone.utc), requested_checks=["check the secrets", "check the DNS changes"])
    assert store.expert_request(lines) == "check the secrets\ncheck the DNS changes"  # a request on several lines: once
