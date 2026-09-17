import pytest

from rca import config
from rca.agents import historical
from rca.agents.historical import HistoricalRCAReview, HistoricalRCADecision, review_historical_rcas
from rca.llm import LLMOutputError
from rca.models import InvestigationPlan


PLAN = InvestigationPlan(
    service="Payment API",
    window_start="2026-07-14T10:00:00Z",
    window_end="2026-07-14T16:05:00Z",
    sources=["historical_rcas"],
    search_queries=["Payment API database connection timeout after deployment"],
    rationale="Compare the current payment symptoms with older RCA sections.",
)


RESULTS = [
    {
        "id": "RCA-2025-00114::Root Cause",
        "document": "Database connection pool exhaustion caused by unclosed SQL sessions.",
        "metadata": {
            "document_id": "RCA-2025-00114",
            "section_name": "Root Cause",
            "service": "Payment API",
            "completion_date": 1763647200,
        },
    },
    {
        "id": "RCA-2025-00042::Root Cause",
        "document": "PostgreSQL connection pool exhaustion during payroll batch processing.",
        "metadata": {
            "document_id": "RCA-2025-00042",
            "section_name": "Root Cause",
            "service": "Payroll Service",
            "completion_date": 1750000000,
        },
    },
]


def decisions(*pairs) -> HistoricalRCAReview:
    return HistoricalRCAReview(decisions=[
        HistoricalRCADecision(citation=citation, relevant=relevant, reason=reason)
        for citation, relevant, reason in pairs
    ])


GOOD_REVIEW = decisions(
    ("RCA-2025-00114::Root Cause", True, "Same service and matching connection timeout symptoms."),
    ("RCA-2025-00042::Root Cause", False, "The RCA belongs to Payroll Service, not Payment API."),
)


def fake_answer(review: HistoricalRCAReview):
    def fake_ask_json(instructions, user_input, schema):
        assert schema is HistoricalRCAReview
        return review
    return fake_ask_json


def test_historical_agent_keeps_the_payment_rca_and_drops_the_payroll_distractor(monkeypatch):
    monkeypatch.setattr(historical, "ask_json", fake_answer(GOOD_REVIEW))

    review, evidence = review_historical_rcas(PLAN, RESULTS)

    assert [decision.citation for decision in review.decisions if decision.relevant] == [
        "RCA-2025-00114::Root Cause"
    ]
    # The evidence cites the RCA, not the section that was found.
    assert [(item.citation, item.type, item.evidence_id) for item in evidence] == [
        ("RCA-2025-00114", "HISTORICAL_RCA", "EV-001")
    ]


def test_the_same_rca_found_in_two_sections_becomes_one_evidence(monkeypatch):
    results = [*RESULTS, {**RESULTS[0], "id": "RCA-2025-00114::Summary",
                          "metadata": {**RESULTS[0]["metadata"], "section_name": "Summary"}}]
    monkeypatch.setattr(historical, "ask_json", fake_answer(decisions(
        ("RCA-2025-00114::Root Cause", True, "Same service."),
        ("RCA-2025-00042::Root Cause", False, "Another service."),
        ("RCA-2025-00114::Summary", True, "Same service."),
    )))

    _, evidence = review_historical_rcas(PLAN, results)

    assert [item.citation for item in evidence] == ["RCA-2025-00114"]


def test_a_missing_decision_is_refused(monkeypatch):
    monkeypatch.setattr(historical, "ask_json", fake_answer(decisions(
        ("RCA-2025-00114::Root Cause", True, "Same service."),
    )))

    with pytest.raises(LLMOutputError, match="RCA-2025-00042::Root Cause"):
        review_historical_rcas(PLAN, RESULTS)


def test_an_invented_citation_is_refused(monkeypatch):
    monkeypatch.setattr(historical, "ask_json", fake_answer(decisions(
        ("RCA-2025-00114::Root Cause", True, "Same service."),
        ("RCA-2025-00042::Root Cause", False, "Another service."),
        ("RCA-2099-00999::Root Cause", True, "A record nobody retrieved."),
    )))

    with pytest.raises(LLMOutputError, match="RCA-2099-00999"):
        review_historical_rcas(PLAN, RESULTS)


def test_nothing_retrieved_means_no_call_and_no_evidence(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the model must not be called when the search found nothing")

    monkeypatch.setattr(historical, "ask_json", fail)

    review, evidence = review_historical_rcas(PLAN, [])

    assert review.decisions == [] and evidence == []


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_historical_agent_live_keeps_payment_rca_and_rejects_payroll_distractor():
    review, evidence = historical.review_historical_rcas(PLAN, RESULTS)

    decided = {decision.citation: decision for decision in review.decisions}

    assert decided["RCA-2025-00114::Root Cause"].relevant is True
    assert decided["RCA-2025-00042::Root Cause"].relevant is False
    assert [item.citation for item in evidence] == ["RCA-2025-00114"]
