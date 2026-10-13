"""Tests for the comparison of two revisions of an RCA (rca/compare.py): computed by code, never by a model."""

from pathlib import Path

from rca.compare import compare, previous_revision
from rca.models import InvestigationContext, RCARecord

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_rca_record.json"


def record(revision: int = 1, **changes) -> RCARecord:
    base = RCARecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    return base.model_copy(update={"revision": revision, "run_status": "COMPLETED", **changes})


def test_the_same_revision_twice_changes_nothing():
    first = record(1)

    found = compare(first, record(2))

    assert found.new_evidence == [] and found.dropped_evidence == []
    assert [change.kind for change in found.hypotheses] == ["kept", "kept"]
    assert not found.main_changed and found.newly_not_checked == []


def test_evidence_is_compared_by_the_record_it_cites_not_by_its_id():
    first = record(1)
    renumbered = [item.model_copy(update={"evidence_id": f"EV-{index + 50:03d}"})
                  for index, item in enumerate(first.evidence)]
    extra = first.evidence[0].model_copy(update={"evidence_id": "EV-099", "citation": "LOG-PAY-20260714-99"})

    found = compare(first, record(2, evidence=renumbered[1:] + [extra]))

    assert found.new_evidence == ["LOG-PAY-20260714-99"]
    assert found.dropped_evidence == [first.evidence[0].citation]


def test_a_reworded_cause_is_kept_a_different_one_is_new_and_the_missing_one_is_dropped():
    first = record(1)
    main, other = first.hypotheses
    reworded = main.model_copy(update={"hypothesis_id": "HYP-001", "confidence": "MEDIUM",
                                       "candidate_root_cause": main.candidate_root_cause.replace("caused by", "due to")})
    different = other.model_copy(update={"hypothesis_id": "HYP-002",
                                         "candidate_root_cause": "A retry storm from the mobile client after the proxy update."})

    found = compare(first, record(2, hypotheses=[reworded, different]))

    assert [change.kind for change in found.hypotheses] == ["kept", "new", "dropped"]
    kept = found.hypotheses[0]
    assert (kept.previous.confidence, kept.current.confidence) == ("HIGH", "MEDIUM")
    assert found.hypotheses[2].previous is other
    assert not found.main_changed  # the main hypothesis is the same one, reworded


def test_the_main_hypothesis_changes_when_another_one_comes_first():
    first = record(1)
    main, other = first.hypotheses

    found = compare(first, record(2, hypotheses=[other, main]))

    assert found.main_changed


def test_the_request_and_what_is_newly_not_checked_are_shown():
    first = record(1)
    current = record(2, context=InvestigationContext.model_construct(expert_request="Check the pool size."),
                     not_checked=first.not_checked + ["The pool metrics of the replica."])

    found = compare(first, current)

    assert found.request == "Check the pool size."
    assert found.newly_not_checked == ["The pool metrics of the replica."]


def test_the_previous_revision_is_the_latest_earlier_one_with_an_analysis():
    first, failed, third = record(1), record(2, run_status="FAILED", hypotheses=[]), record(3)

    assert previous_revision([first, failed, third], third) is first
    assert previous_revision([first, failed, third], first) is None


def test_without_the_request_in_the_context_the_comment_of_the_previous_decision_is_shown():
    from datetime import datetime, timezone

    from rca.models import ReviewDecision

    asked = ReviewDecision(reviewer="expert", decision="REQUEST_MORE_DETAILS", comment="Check the replica.",
                           decided_at=datetime(2026, 10, 13, tzinfo=timezone.utc))
    approved = asked.model_copy(update={"decision": "APPROVE", "comment": "Fine."})

    assert compare(record(1, review=asked), record(2, context=None)).request == "Check the replica."
    assert compare(record(1, review=approved), record(2, context=None)).request is None
