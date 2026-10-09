"""Tests for rca.evidence: ids are given in order, can be checked, and a record counts once."""

from datetime import datetime

from rca.evidence import EvidenceLedger, add_dependencies
from rca.models import ConfigItem, Dependency, ServiceDependencies


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


def ci(ci_id, name, type_="application"):
    return ConfigItem(ci_id=ci_id, name=name, type=type_, service="Payroll Service", environment="production",
                      owner_team="HR Systems Engineering", criticality="high")


def test_two_components_depending_on_the_same_one_are_both_kept():
    app, worker, db = ci("CI-PAYROLL-APP", "payroll-app"), ci("CI-PAYROLL-WORKER", "payroll-worker"), ci("CI-PAYROLL-DB", "payroll-postgresql", "database")
    sftp = ci("CI-PAYROLL-SFTP", "payroll-sftp", "storage")
    dependencies = ServiceDependencies(service="Payroll Service", components=[app, worker], dependencies=[
        Dependency(component=app, depends_on=db, relationship_type="connects_to"),
        Dependency(component=worker, depends_on=db, relationship_type="connects_to"),
        Dependency(component=worker, depends_on=sftp, relationship_type="depends_on"),
    ])
    ledger = EvidenceLedger()

    add_dependencies(ledger, dependencies)

    assert [item.citation for item in ledger.items()] == ["CI-PAYROLL-DB", "CI-PAYROLL-SFTP"]
    database = ledger.items()[0].description
    assert "CI-PAYROLL-APP" in database and "CI-PAYROLL-WORKER" in database


def test_a_log_group_keeps_every_line_as_a_related_id():
    from datetime import datetime, timezone

    from rca.evidence import add_log_groups
    from rca.models import LogEntry, LogGroup

    at = datetime(2026, 7, 14, 14, 5, tzinfo=timezone.utc)
    lines = [LogEntry(log_id=f"LOG-PAY-20260714-{n}", timestamp=at, service="Payment API", host="h", level="ERROR",
                      message="timeout", error_type="ConnectionTimeout") for n in (14, 20, 21)]
    group = LogGroup(service="Payment API", level="ERROR", error_type="ConnectionTimeout", count=3, first_seen=at,
                     last_seen=at, hosts=["h"], examples=lines[:1], log_ids=[line.log_id for line in lines])
    ledger = EvidenceLedger()

    add_log_groups(ledger, [group], at)

    assert ledger.items()[0].citation == "LOG-PAY-20260714-14"
    assert ledger.items()[0].related_ids == ["LOG-PAY-20260714-20", "LOG-PAY-20260714-21"]
