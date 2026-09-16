import pytest

from rca import config
from rca.agents import historical
from rca.agents.historical import HistoricalRCAReview, HistoricalRCADecision, review_historical_rcas
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


def test_historical_agent_keeps_payment_rca_and_rejects_payroll_distractor(monkeypatch):
    def fake_ask_json(instructions, user_input, schema):
        assert schema is HistoricalRCAReview
        return HistoricalRCAReview(decisions=[
            HistoricalRCADecision(
                citation="RCA-2025-00114::Root Cause",
                relevant=True,
                reason="Same service and matching connection timeout symptoms.",
            ),
            HistoricalRCADecision(
                citation="RCA-2025-00042::Root Cause",
                relevant=False,
                reason="The RCA belongs to Payroll Service, not Payment API.",
            ),
        ])

    monkeypatch.setattr(historical, "ask_json", fake_ask_json)

    review, evidence = review_historical_rcas(PLAN, RESULTS)

    assert [decision.citation for decision in review.decisions if decision.relevant] == [
        "RCA-2025-00114::Root Cause"
    ]
    assert len(evidence) == 1
    assert evidence[0].citation == "RCA-2025-00114::Root Cause"
    assert evidence[0].type == "HISTORICAL_RCA"
    assert evidence[0].evidence_id == "EV-001"


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_historical_agent_live_keeps_payment_rca_and_rejects_payroll_distractor():
    review, evidence = historical.review_historical_rcas(PLAN, RESULTS)

    decisions = {decision.citation: decision for decision in review.decisions}

    assert decisions["RCA-2025-00114::Root Cause"].relevant is True
    assert decisions["RCA-2025-00042::Root Cause"].relevant is False
    assert [item.citation for item in evidence] == ["RCA-2025-00114::Root Cause"]
