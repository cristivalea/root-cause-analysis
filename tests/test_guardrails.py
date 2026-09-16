"""Tests for rca.guardrails: wrong answers are refused, retried with the error, then escalated.

The model is replaced with fixed answers. The live test uses the Payment API ledger from
tests/conftest.py; to run it on a smaller model:
GROQ_MODEL=openai/gpt-oss-20b python -m pytest -m live tests/test_guardrails.py
"""

from datetime import datetime

import pytest

from rca import config
from rca.agents import reasoning
from rca.confidence import assess_draft
from rca.guardrails import MAX_ATTEMPTS, check_draft, run_with_retries, validated_draft
from rca.llm import LLMOutputError
from rca.models import DraftRCA, Hypothesis

LEDGER_IDS = {"EV-001", "EV-002", "EV-003"}


def hypothesis(hypothesis_id="HYP-001", supporting=("EV-001",), contradicting=()) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        candidate_root_cause="A candidate cause.",
        reasons=["A reason."],
        supporting_evidence=list(supporting),
        contradicting_evidence=list(contradicting),
        recommended_validation=["A check."],
    )


def draft(*hypotheses: Hypothesis, single_reason: str | None = None) -> DraftRCA:
    return DraftRCA(
        incident_id="INC-2026-00482",
        investigation_summary="Summary.",
        observed_patterns=[],
        hypotheses=list(hypotheses),
        single_hypothesis_reason=single_reason,
        not_checked=[],
        suggested_workaround=None,
        change_likely_required=False,
    )


GOOD_DRAFT = draft(hypothesis("HYP-001", ["EV-001", "EV-002"]), hypothesis("HYP-002", ["EV-003"], ["EV-001"]))


# The checks ----------------------------------------------------------------------------


def test_a_good_draft_passes():
    assert check_draft(GOOD_DRAFT, LEDGER_IDS) == []


def test_an_invented_citation_is_refused():
    bad = draft(hypothesis("HYP-001", ["EV-001", "EV-099"]), hypothesis("HYP-002"))

    assert check_draft(bad, LEDGER_IDS) == [
        "HYP-001 cites in supporting_evidence ids that are not in the evidence ledger: EV-099"
    ]


def test_an_invented_contradicting_citation_is_refused():
    bad = draft(hypothesis("HYP-001"), hypothesis("HYP-002", contradicting=["CHG-2026-00871"]))

    assert check_draft(bad, LEDGER_IDS) == [
        "HYP-002 cites in contradicting_evidence ids that are not in the evidence ledger: CHG-2026-00871"
    ]


def test_a_hypothesis_without_evidence_is_refused():
    bad = draft(hypothesis("HYP-001"), hypothesis("HYP-002", supporting=[]))

    assert check_draft(bad, LEDGER_IDS) == ["HYP-002 has no supporting evidence"]


def test_one_hypothesis_needs_a_reason():
    assert check_draft(draft(hypothesis()), LEDGER_IDS) == [
        "there is only one hypothesis and single_hypothesis_reason does not explain why"
    ]
    assert check_draft(draft(hypothesis(), single_reason="Only the deploy fits the timeline."), LEDGER_IDS) == []


def test_a_draft_without_hypotheses_is_refused():
    assert check_draft(draft(single_reason="Nothing found."), LEDGER_IDS) == ["the draft has no hypotheses"]


# The retry -----------------------------------------------------------------------------


class FakeModel:
    """Returns the given answers in order and remembers the feedback of every call."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.feedback: list[str | None] = []

    def __call__(self, feedback):
        self.feedback.append(feedback)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def check(value: DraftRCA) -> list[str]:
    return check_draft(value, LEDGER_IDS)


def test_a_good_first_answer_is_accepted_at_once():
    model = FakeModel(GOOD_DRAFT)

    result = run_with_retries(model, check)

    assert result.value == GOOD_DRAFT
    assert not result.escalated
    assert [attempt.problems for attempt in result.attempts] == [[]]
    assert model.feedback == [None]


def test_a_wrong_answer_is_retried_with_the_problem_included():
    invented = draft(hypothesis("HYP-001", ["EV-042"]), hypothesis("HYP-002"))
    model = FakeModel(invented, GOOD_DRAFT)

    result = run_with_retries(model, check)

    assert result.value == GOOD_DRAFT
    assert len(result.attempts) == 2
    assert "EV-042" in model.feedback[1]


def test_an_invalid_answer_counts_as_a_failed_attempt():
    model = FakeModel(LLMOutputError("The answer is not valid JSON.", "not json"), GOOD_DRAFT)

    result = run_with_retries(model, check)

    assert result.value == GOOD_DRAFT
    assert result.attempts[0].problems == ["The answer is not valid JSON."]
    assert "not valid JSON" in model.feedback[1]


def test_three_failed_attempts_escalate():
    invented = draft(hypothesis("HYP-001", ["EV-042"]), hypothesis("HYP-002"))
    model = FakeModel(invented, invented, invented, GOOD_DRAFT)

    result = run_with_retries(model, check)

    assert result.escalated
    assert result.value is None
    assert len(result.attempts) == MAX_ATTEMPTS
    assert len(model.answers) == 1  # the fourth answer was never asked for


def test_the_reasoning_agent_receives_the_feedback(payment_ledger, monkeypatch):
    requests = []
    answers = [draft(hypothesis("HYP-001", ["EV-042"]), hypothesis("HYP-002")), GOOD_DRAFT]

    def fake_ask_json(instructions, user_input, schema):
        requests.append(user_input)
        return answers.pop(0)

    monkeypatch.setattr(reasoning, "ask_json", fake_ask_json)

    result = validated_draft("INC-2026-00482", payment_ledger.items())

    assert not result.escalated
    assert "refused" not in requests[0]
    assert "Your previous answer was refused" in requests[1] and "EV-042" in requests[1]


# Real model ----------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_live_guardrail_and_confidence_for_payment_api(payment_ledger):
    evidence = payment_ledger.items()

    result = validated_draft("INC-2026-00482", evidence)

    print(f"\nMODEL: {config.GROQ_MODEL}")
    for attempt in result.attempts:
        print(f"attempt {attempt.number}: {attempt.problems or 'accepted'}")
    assert not result.escalated

    detected_at = datetime.fromisoformat("2026-07-14T14:32:00+00:00")
    for item in assess_draft(result.value, evidence, detected_at):
        print(f"{item.hypothesis_id} {item.confidence} ({item.confidence_points} points): {item.candidate_root_cause}")
        print("   supporting", item.supporting_evidence, "contradicting", item.contradicting_evidence)
        for reason in item.confidence_reasons:
            print("   -", reason)
