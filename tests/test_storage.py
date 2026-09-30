import sqlite3
from pathlib import Path

from rca import storage
from rca.storage import load_sources

ROOT = Path(__file__).resolve().parents[1]


def test_validated_sources_load_into_sqlite(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    load_sources(db_path, ROOT / "data" / "sources")

    with sqlite3.connect(db_path) as connection:
        payment = connection.execute(
            "SELECT incident_id, service FROM incidents WHERE incident_id = ?",
            ("INC-2026-00482",),
        ).fetchone()
        change = connection.execute(
            "SELECT change_id, implemented_at FROM changes WHERE change_id = ?",
            ("CHG-2026-00871",),
        ).fetchone()
        log = connection.execute(
            "SELECT log_id FROM logs WHERE log_id = ?",
            ("LOG-PAY-20260714-14",),
        ).fetchone()
        ci = connection.execute(
            "SELECT ci_id FROM cmdb_items WHERE ci_id = ?",
            ("CI-PAYMENT-API",),
        ).fetchone()

    assert payment == ("INC-2026-00482", "Payment API")
    assert change == ("CHG-2026-00871", "2026-07-14T13:58:00+00:00")
    assert log == ("LOG-PAY-20260714-14",)
    assert ci == ("CI-PAYMENT-API",)


def test_incident_events_are_loaded_and_read_in_time_order(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")

    events = storage.get_incident_events(db_path, "INC-2026-00482")

    assert [event.action for event in events][:2] == ["opened", "assigned"]
    assert events == sorted(events, key=lambda event: event.timestamp)
    assert storage.get_incident_events(db_path, "INC-2099-00001") == []


def test_clearing_the_sources_keeps_nothing_old(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")

    storage.clear_sources(db_path)

    assert storage.list_incidents(db_path) == []
