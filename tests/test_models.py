"""Tests for rca.models: the examples from the documentation load, wrong data is refused."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rca.models import (
    Change,
    CIRelationship,
    ConfigItem,
    DraftRCA,
    Evidence,
    Incident,
    InvestigationPlan,
    LogEntry,
    RCARecord,
    ReviewDecision,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# Source data ---------------------------------------------------------------------------


def test_incident_from_the_documentation_loads():
    incident = Incident.model_validate(load_fixture("incident_example.json"))

    assert incident.incident_id == "INC-2026-00482"
    assert incident.detected_at.isoformat() == "2026-07-14T14:32:00+00:00"
    assert incident.impact.failed_transactions == 18420


def test_incident_cannot_carry_the_root_cause():
    data = load_fixture("incident_example.json") | {"root_cause": "connection pool exhaustion"}

    with pytest.raises(ValidationError, match="root_cause"):
        Incident.model_validate(data)


def test_incident_with_an_unknown_severity_is_refused():
    data = load_fixture("incident_example.json") | {"severity": "critical"}

    with pytest.raises(ValidationError, match="severity"):
        Incident.model_validate(data)


def test_cmdb_change_and_log_records_load():
    ConfigItem(
        ci_id="CI-PAYMENT-API", name="payment-api", type="application", service="Payment API",
        environment="production", owner_team="Payments Platform Engineering", criticality="high",
    )
    CIRelationship(source_ci="CI-PAYMENT-API", target_ci="CI-PAYMENT-DB", relationship_type="depends_on")
    Change(
        change_id="CHG-2026-00871", title="Deploy Payment API v4.18.2", type="normal", service="Payment API",
        ci_id="CI-PAYMENT-API", version="4.18.2", implemented_at="2026-07-14T13:58:00Z",
        implemented_by="Payments Platform Engineering", risk="medium", rollback=False,
    )
    LogEntry(
        log_id="LOG-PAY-20260714-14", timestamp="2026-07-14T14:05:12Z", service="Payment API",
        host="payment-api-prod-03", level="ERROR", error_type="ConnectionTimeout",
        message="HikariPool-1 - Connection is not available, request timed out after 30000ms.",
    )


# Application data ----------------------------------------------------------------------


def test_evidence_id_must_follow_the_ledger_format():
    with pytest.raises(ValidationError, match="evidence_id"):
        Evidence(evidence_id="E1", type="LOG", source="payment-api-prod", description="x", citation="LOG-PAY-20260714-14")


def test_plan_window_must_start_before_it_ends():
    with pytest.raises(ValidationError, match="window_start must be before window_end"):
        InvestigationPlan(
            service="Payment API", window_start="2026-07-14T15:00:00Z", window_end="2026-07-14T14:00:00Z",
            sources=["logs"], search_queries=["timeouts"], rationale="x",
        )


def test_plan_with_an_unknown_source_is_refused():
    with pytest.raises(ValidationError, match="sources"):
        InvestigationPlan(
            service="Payment API", window_start="2026-07-14T11:00:00Z", window_end="2026-07-14T15:00:00Z",
            sources=["monitoring_dashboards"], search_queries=["timeouts"], rationale="x",
        )


def test_draft_from_the_reasoning_agent_has_no_confidence_field():
    draft = DraftRCA.model_validate({
        "incident_id": "INC-2026-00482",
        "investigation_summary": "Timeouts started after the v4.18.2 deployment.",
        "observed_patterns": ["Timeouts started 7 minutes after the deployment."],
        "hypotheses": [{
            "hypothesis_id": "HYP-001",
            "candidate_root_cause": "Connection pool exhaustion introduced by Payment API v4.18.2.",
            "reasons": ["Strong temporal correlation with CHG-2026-00871."],
            "supporting_evidence": ["EV-001", "EV-002"],
            "contradicting_evidence": [],
            "recommended_validation": ["Compare connection usage before and after v4.18.2."],
            "confidence": "HIGH",
        }],
        "not_checked": ["No database metrics were available."],
        "suggested_workaround": "Temporarily raise the connection pool limit.",
        "change_likely_required": True,
    })

    assert not hasattr(draft.hypotheses[0], "confidence")


def test_sample_rca_record_loads_and_its_citations_exist():
    record = RCARecord.model_validate(load_fixture("sample_rca_record.json"))

    evidence_ids = {evidence.evidence_id for evidence in record.evidence}
    for hypothesis in record.hypotheses:
        assert set(hypothesis.supporting_evidence + hypothesis.contradicting_evidence) <= evidence_ids
    assert record.status == "PENDING_REVIEW"
    assert record.final_root_cause is None


# The human approval rule ---------------------------------------------------------------

APPROVAL = ReviewDecision(
    reviewer="Technical Expert", decision="APPROVE", hypothesis_id="HYP-001",
    comment="Confirmed in the v4.18.2 code review.", decided_at="2026-09-14T11:00:00Z",
)


def test_final_root_cause_cannot_be_set_before_approval():
    data = load_fixture("sample_rca_record.json") | {"final_root_cause": "Connection pool exhaustion."}

    with pytest.raises(ValidationError, match="approved by a Technical Expert"):
        RCARecord.model_validate(data)


def test_rca_cannot_be_final_without_approval():
    data = load_fixture("sample_rca_record.json") | {"status": "FINAL"}

    with pytest.raises(ValidationError, match="needs an approval"):
        RCARecord.model_validate(data)


def test_rca_can_be_final_after_approval():
    data = load_fixture("sample_rca_record.json") | {
        "status": "FINAL",
        "review": APPROVAL.model_dump(),
        "final_root_cause": "Connection pool exhaustion caused by connections not released in v4.18.2.",
        "completed_at": "2026-09-14T11:00:00Z",
    }

    assert RCARecord.model_validate(data).status == "FINAL"
