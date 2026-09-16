"""Tests for rca.tools and the SQLite read functions they use.

Two kinds of data:
- the real mock data from data/sources, for the Payment API scenario;
- a few records written by hand, for the edge cases (window edges, time zones, grouping).
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from rca import storage
from rca.tools import MAX_LOG_EXAMPLES, find_changes, find_dependencies, find_logs

ROOT = Path(__file__).resolve().parents[1]

# Payment API incident INC-2026-00482: detected 14:32, resolved 15:17.
PAYMENT_START = datetime.fromisoformat("2026-07-14T12:00:00+00:00")
PAYMENT_END = datetime.fromisoformat("2026-07-14T15:17:00+00:00")


@pytest.fixture(scope="module")
def payment_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("payment") / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    return db_path


def ci(ci_id, service, type_="application"):
    return {
        "ci_id": ci_id, "name": ci_id.lower(), "type": type_, "service": service,
        "environment": "production", "owner_team": "Team", "criticality": "high",
    }


def change(change_id, service, ci_id, implemented_at):
    return {
        "change_id": change_id, "title": f"Change {change_id}", "type": "normal", "service": service,
        "ci_id": ci_id, "implemented_at": implemented_at, "implemented_by": "Team", "risk": "low",
        "rollback": True,
    }


def log(log_id, timestamp, level, error_type, service="Shop API", host="shop-01"):
    return {
        "log_id": log_id, "timestamp": timestamp, "service": service, "host": host, "level": level,
        "message": f"{error_type or 'normal'} message", "error_type": error_type,
    }


@pytest.fixture
def handwritten_db(tmp_path):
    """A small database for the edge cases, loaded through the same loader as the real data."""
    sources = {
        "incidents.json": [],
        "cmdb_items.json": [
            ci("CI-SHOP-API", "Shop API"),
            ci("CI-SHOP-DB", "Shop API", "database"),
            ci("CI-SHARED-CACHE", "Cache Platform", "cache"),
        ],
        "cmdb_relationships.json": [
            {"source_ci": "CI-SHOP-API", "target_ci": "CI-SHOP-DB", "relationship_type": "depends_on"},
            {"source_ci": "CI-SHOP-API", "target_ci": "CI-SHARED-CACHE", "relationship_type": "connects_to"},
        ],
        "changes.json": [
            change("CHG-2026-00001", "Shop API", "CI-SHOP-API", "2026-07-14T09:59:59Z"),  # before the window
            change("CHG-2026-00002", "Shop API", "CI-SHOP-API", "2026-07-14T10:00:00Z"),  # on the start edge
            change("CHG-2026-00003", "Shop API", "CI-SHOP-DB", "2026-07-14T13:30:00+02:00"),  # 11:30 UTC
            change("CHG-2026-00004", "Cache Platform", "CI-SHARED-CACHE", "2026-07-14T11:00:00Z"),
            change("CHG-2026-00005", "Other Service", "CI-SHOP-API", "2026-07-14T11:00:00Z"),
        ],
        "logs.json": [
            *[log(f"LOG-SHOP-20260714-{i}", f"2026-07-14T10:0{i}:00Z", "ERROR", "Timeout") for i in range(1, 6)],
            log("LOG-SHOP-20260714-6", "2026-07-14T10:30:00Z", "WARN", "SlowQuery", host="shop-02"),
            log("LOG-SHOP-20260714-7", "2026-07-14T10:31:00Z", "WARN", "SlowQuery", host="shop-02"),
            log("LOG-SHOP-20260714-8", "2026-07-14T10:40:00Z", "INFO", None),
            log("LOG-SHOP-20260714-9", "2026-07-14T13:00:00Z", "ERROR", "Timeout"),  # after the window
            log("LOG-CART-20260714-1", "2026-07-14T10:05:00Z", "ERROR", "Timeout", service="Cart"),
        ],
    }
    folder = tmp_path / "sources"
    folder.mkdir()
    for name, records in sources.items():
        (folder / name).write_text(json.dumps(records), encoding="utf-8")

    db_path = tmp_path / "sources.sqlite3"
    storage.load_sources(db_path, folder)
    return db_path


WINDOW_START = datetime.fromisoformat("2026-07-14T10:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-07-14T12:00:00+00:00")


# Payment API scenario (the result required by step 6) ----------------------------------


def test_payment_api_depends_on_its_database(payment_db):
    result = find_dependencies("Payment API", db_path=payment_db)

    dependencies = {(item.component.ci_id, item.depends_on.ci_id) for item in result.dependencies}
    assert ("CI-PAYMENT-API", "CI-PAYMENT-DB") in dependencies
    assert any(item.depends_on.type == "database" for item in result.dependencies)


def test_payment_api_changes_include_the_deploy_before_the_incident(payment_db):
    changes = find_changes(["Payment API"], PAYMENT_START, PAYMENT_END, db_path=payment_db)

    ids = [item.change_id for item in changes]
    assert "CHG-2026-00871" in ids
    assert all(item.service == "Payment API" for item in changes)


def test_payment_api_logs_show_the_hikaricp_timeouts(payment_db):
    groups = find_logs("Payment API", PAYMENT_START, PAYMENT_END, db_path=payment_db)

    first = groups[0]
    assert first.level == "ERROR"
    assert "LOG-PAY-20260714-14" in [line.log_id for line in first.examples]
    assert any("HikariPool" in line.message for group in groups for line in group.examples)
    assert all(group.level in ("ERROR", "WARN") for group in groups)


def test_incident_is_read_back_from_the_database(payment_db):
    incident = storage.get_incident(payment_db, "INC-2026-00482")

    assert incident.service == "Payment API"
    assert storage.get_incident(payment_db, "INC-2099-00001") is None
    assert "INC-2026-00482" in [item.incident_id for item in storage.list_incidents(payment_db)]


# Edge cases ---------------------------------------------------------------------------


def test_dependencies_include_other_services(handwritten_db):
    result = find_dependencies("Shop API", db_path=handwritten_db)

    assert [item.ci_id for item in result.components] == ["CI-SHOP-API", "CI-SHOP-DB"]
    assert {item.depends_on.ci_id for item in result.dependencies} == {"CI-SHOP-DB", "CI-SHARED-CACHE"}
    assert result.related_services == ["Cache Platform"]


def test_unknown_service_has_no_dependencies(handwritten_db):
    result = find_dependencies("Unknown Service", db_path=handwritten_db)

    assert result.components == []
    assert result.dependencies == []


def test_changes_are_filtered_by_service_and_window(handwritten_db):
    changes = find_changes(["Shop API", "Cache Platform"], WINDOW_START, WINDOW_END, db_path=handwritten_db)

    # 00001 is one second too early, 00005 is on another service.
    # 00003 was written with a +02:00 offset and is still found, in the right order.
    assert [item.change_id for item in changes] == ["CHG-2026-00002", "CHG-2026-00004", "CHG-2026-00003"]


def test_logs_are_grouped_by_level_and_error_type(handwritten_db):
    groups = find_logs("Shop API", WINDOW_START, WINDOW_END, db_path=handwritten_db)

    assert [(group.level, group.error_type, group.count) for group in groups] == [
        ("ERROR", "Timeout", 5),
        ("WARN", "SlowQuery", 2),
    ]
    timeout = groups[0]
    assert len(timeout.examples) == MAX_LOG_EXAMPLES
    assert timeout.first_seen.isoformat() == "2026-07-14T10:01:00+00:00"
    assert timeout.last_seen.isoformat() == "2026-07-14T10:05:00+00:00"
    assert groups[1].hosts == ["shop-02"]


def test_info_logs_only_when_asked(handwritten_db):
    groups = find_logs("Shop API", WINDOW_START, WINDOW_END, levels=("INFO",), db_path=handwritten_db)

    assert [(group.level, group.count) for group in groups] == [("INFO", 1)]


def test_missing_database_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="load_sources_sqlite"):
        find_dependencies("Payment API", db_path=tmp_path / "missing.sqlite3")
