"""Tests for rca.evidence: ids are given in order, can be checked, and a record counts once."""

from datetime import datetime

from rca.evidence import EvidenceLedger


def test_evidence_gets_consecutive_ids():
    ledger = EvidenceLedger()

    first = ledger.add("CHANGE", "CHG-2026-00871", "Payment API v4.18.2 deployed.", "CHG-2026-00871",
                       datetime.fromisoformat("2026-07-14T13:58:00+00:00"))
    second = ledger.add("CMDB", "CMDB", "Payment API depends on its database.", "CI-PAYMENT-DB")

    assert (first.evidence_id, second.evidence_id) == ("EV-001", "EV-002")
    assert [item.evidence_id for item in ledger.items()] == ["EV-001", "EV-002"]
    assert len(ledger) == 2


def test_ledger_says_which_ids_exist():
    ledger = EvidenceLedger()
    ledger.add("LOG", "payment-api-prod-03", "HikariCP connection timeouts.", "LOG-PAY-20260714-14")

    assert ledger.has("EV-001")
    assert not ledger.has("EV-002")
    assert ledger.get("EV-001").citation == "LOG-PAY-20260714-14"
    assert ledger.get("EV-099") is None


def test_the_same_record_is_recorded_once():
    ledger = EvidenceLedger()

    first = ledger.add("HISTORICAL_RCA", "RCA-2025-00114", "Root cause section.", "RCA-2025-00114")
    again = ledger.add("HISTORICAL_RCA", "RCA-2025-00114", "Timeline section.", "RCA-2025-00114")

    assert again.evidence_id == first.evidence_id
    assert len(ledger) == 1


def test_the_list_cannot_be_changed_from_outside():
    ledger = EvidenceLedger()
    ledger.add("CMDB", "CMDB", "Payment API depends on its database.", "CI-PAYMENT-DB")

    ledger.items().clear()

    assert len(ledger) == 1
