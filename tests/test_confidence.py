"""Tests for rca.confidence: the level is calculated from the rules of doc 06, 6.5."""

import json
from datetime import datetime
from pathlib import Path

from rca import confidence
from rca.confidence import assess_draft, first_error_time, is_weakly_supported
from rca.models import DraftRCA, Evidence, Hypothesis, RCARecord

FIXTURES = Path(__file__).parent / "fixtures"
DETECTED_AT = datetime.fromisoformat("2026-07-14T14:32:00+00:00")


def at(hour_minute: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-14T{hour_minute}:00+00:00")


LEDGER = [
    Evidence(evidence_id="EV-001", type="LOG", source="payment-api", description="Timeouts.",
             citation="LOG-PAY-20260714-14", timestamp=at("14:05")),
    Evidence(evidence_id="EV-002", type="CHANGE", source="CHG-2026-00871", description="Deploy v4.18.2.",
             citation="CHG-2026-00871", timestamp=at("13:58")),
    Evidence(evidence_id="EV-003", type="CHANGE", source="CHG-2026-00873", description="Dashboard thresholds.",
             citation="CHG-2026-00873", timestamp=at("14:10")),
    Evidence(evidence_id="EV-004", type="CMDB", source="CMDB", description="Depends on the database.",
             citation="CI-PAYMENT-DB"),
    Evidence(evidence_id="EV-005", type="HISTORICAL_RCA", source="RCA-2025-00114", description="Same cause.",
             citation="RCA-2025-00114"),
    Evidence(evidence_id="EV-006", type="HISTORICAL_INCIDENT", source="INC-2025-00401", description="Similar.",
             citation="INC-2025-00401"),
    Evidence(evidence_id="EV-007", type="LOG", source="payment-api", description="Pool at 96%.",
             citation="LOG-PAY-20260714-15", timestamp=at("14:11")),
]


def hypothesis(supporting, contradicting=(), hypothesis_id="HYP-001") -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id, candidate_root_cause="A candidate cause.", reasons=["A reason."],
        supporting_evidence=list(supporting), contradicting_evidence=list(contradicting),
        recommended_validation=["A check."],
    )


def assess(*hypotheses: Hypothesis, evidence=LEDGER):
    draft = DraftRCA(
        incident_id="INC-2026-00482", investigation_summary="", observed_patterns=[], hypotheses=list(hypotheses),
        single_hypothesis_reason=None if len(hypotheses) > 1 else "One.", not_checked=[],
        suggested_workaround=None, change_likely_required=False,
    )
    return assess_draft(draft, evidence, DETECTED_AT)


def test_the_sample_rca_record_gets_the_same_levels():
    record = RCARecord.model_validate(
        json.loads((FIXTURES / "sample_rca_record.json").read_text(encoding="utf-8"))
    )
    draft = DraftRCA(
        incident_id=record.incident_id, investigation_summary="", observed_patterns=[],
        hypotheses=[Hypothesis(**item.model_dump(include=set(Hypothesis.model_fields))) for item in record.hypotheses],
        not_checked=[], suggested_workaround=None, change_likely_required=False,
    )

    assessed = {item.hypothesis_id: item for item in assess_draft(draft, record.evidence, DETECTED_AT)}

    for expected in record.hypotheses:
        assert assessed[expected.hypothesis_id].confidence == expected.confidence
        assert assessed[expected.hypothesis_id].confidence_points == expected.confidence_points


def test_all_kinds_of_evidence_give_high():
    (item,) = assess(hypothesis(["EV-001", "EV-002", "EV-004", "EV-005", "EV-006"]))

    assert (item.confidence, item.confidence_points) == ("HIGH", 8)
    assert item.confidence_reasons[-1] == "8 points from 5 different sources: HIGH."


def test_points_are_counted_once_per_kind_of_evidence():
    (item,) = assess(hypothesis(["EV-001", "EV-007"]))

    assert (item.confidence, item.confidence_points) == ("LOW", 2)


def test_a_change_after_the_first_error_earns_no_points():
    (item,) = assess(hypothesis(["EV-001", "EV-003", "EV-004"]))

    assert (item.confidence, item.confidence_points) == ("MEDIUM", 3)
    assert any("EV-003 was made after the first error (14:05 UTC)" in reason for reason in item.confidence_reasons)


def test_five_points_from_only_two_sources_is_medium(monkeypatch):
    # With the current points, two kinds of evidence give at most 4. The rule matters when the
    # points are tuned later, so the test raises the log points to reach 5 from two kinds.
    monkeypatch.setitem(confidence.POINTS, "LOG", 3)

    (item,) = assess(hypothesis(["EV-001", "EV-002"]))

    assert (item.confidence, item.confidence_points) == ("MEDIUM", 5)
    assert item.confidence_reasons[-1] == "5 points but from only 2 different sources: MEDIUM."


def test_without_log_evidence_it_cannot_be_high():
    (item,) = assess(hypothesis(["EV-002", "EV-004", "EV-005", "EV-006"]))

    assert (item.confidence, item.confidence_points) == ("MEDIUM", 6)
    assert "No log evidence, so it cannot be HIGH: MEDIUM." in item.confidence_reasons


def test_contradicting_evidence_lowers_one_band():
    (high,) = assess(hypothesis(["EV-001", "EV-002", "EV-005"], contradicting=["EV-003"]))
    assert high.confidence == "MEDIUM"

    (low,) = assess(hypothesis(["EV-004"], contradicting=["EV-006"]))
    assert low.confidence == "LOW"


def test_without_logs_the_detection_time_is_the_first_error():
    evidence = [item for item in LEDGER if item.type != "LOG"]

    assert first_error_time(evidence, DETECTED_AT) == DETECTED_AT
    assert first_error_time(LEDGER, DETECTED_AT) == at("14:05")


def test_hypotheses_are_ordered_strongest_first():
    assessed = assess(
        hypothesis(["EV-004"], hypothesis_id="HYP-001"),
        hypothesis(["EV-001", "EV-002", "EV-005"], hypothesis_id="HYP-002"),
    )

    assert [item.hypothesis_id for item in assessed] == ["HYP-002", "HYP-001"]


def test_a_draft_is_weakly_supported_when_nothing_is_better_than_low():
    weak = assess(hypothesis(["EV-004"], hypothesis_id="HYP-001"), hypothesis(["EV-006"], hypothesis_id="HYP-002"))
    strong = assess(hypothesis(["EV-004"], hypothesis_id="HYP-001"), hypothesis(["EV-001", "EV-004"], hypothesis_id="HYP-002"))

    assert is_weakly_supported(weak)
    assert not is_weakly_supported(strong)
