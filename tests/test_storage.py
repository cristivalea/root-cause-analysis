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


def test_a_problem_is_read_with_its_incidents_in_time_order(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")
    with sqlite3.connect(db_path) as connection:
        problem_id = connection.execute(
            "SELECT problem_id FROM problem_incidents WHERE incident_id = ?", ("INC-2026-00482",)
        ).fetchone()[0]

    problem = storage.get_problem(db_path, problem_id)

    assert problem.status == "Open"
    assert [link.incident_id for link in problem.incidents] == ["INC-2026-00482", "INC-2026-00857"]
    assert storage.get_problem(db_path, "PRB-2099-00001") is None


def test_an_incident_cannot_be_in_two_problems(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")

    with sqlite3.connect(db_path) as connection:
        try:
            connection.execute("INSERT INTO problem_incidents VALUES ('INC-2026-00482', 'PRB-2099-00001', '2026-07-15', 'x')")
            raise AssertionError("the database accepted a second problem for the same incident")
        except sqlite3.IntegrityError:
            pass


def test_the_services_of_the_cmdb_are_listed_once_in_order(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    storage.load_sources(db_path, ROOT / "data" / "sources")

    services = storage.list_services(db_path)

    assert services == sorted(set(services))
    assert {"Payment API", "Network Services", "Kubernetes Platform"} <= set(services)


# Sources and application data are kept apart (final_project_steps.md, E2) ---------------


def _work_in_the_application(db_path):
    """A problem closed by hand, and an RCA in progress on another problem, made by the application."""
    import json

    from rca import problems
    from rca.models import RCARecord
    from rca_helpers import make_rca

    problem_id = storage.get_problem_id_for_incident(db_path, "INC-2026-00482")
    problems.close_problem(problem_id, "pm", "Known vendor bug.", db_path=db_path)
    record = RCARecord.model_validate(json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(
        encoding="utf-8")))
    other = next(item.problem_id for item in problems.list_problems("Open", db_path=db_path))
    make_rca(db_path, other, record, "draft")
    return problem_id


def test_reloading_the_sources_keeps_the_work_of_the_application(tmp_path):
    from rca import store

    db_path = tmp_path / "sources.sqlite3"
    assert load_sources(db_path, ROOT / "data" / "sources") is True  # an empty database gets the problems
    problem_id = _work_in_the_application(db_path)

    assert load_sources(db_path, ROOT / "data" / "sources") is False
    assert load_sources(db_path, ROOT / "data" / "sources", reset=True) is False

    assert storage.get_problem(db_path, problem_id).status == "Closed"  # not reverted to the source data
    assert store.get_rca("RCA-2026-00001", db_path=db_path) is not None  # the RCA and its revision
    assert storage.get_incident(db_path, "INC-2026-00482") is not None


def test_a_reload_that_would_leave_a_problem_without_its_incident_changes_nothing(tmp_path):
    import json
    import shutil

    import pytest

    db_path = tmp_path / "sources.sqlite3"
    load_sources(db_path, ROOT / "data" / "sources")
    sources = tmp_path / "sources"
    shutil.copytree(ROOT / "data" / "sources", sources)
    incidents = json.loads((sources / "incidents.json").read_text(encoding="utf-8"))
    (sources / "incidents.json").write_text(
        json.dumps([item for item in incidents if item["incident_id"] != "INC-2026-00482"]), encoding="utf-8")

    with pytest.raises(ValueError, match="INC-2026-00482"):
        load_sources(db_path, sources, reset=True)

    assert storage.get_incident(db_path, "INC-2026-00482") is not None  # the reset was undone with the load
    assert len(storage.list_incidents(db_path)) == len(incidents)


def test_starting_the_application_data_again_removes_problems_and_rcas_together_after_a_copy(tmp_path):
    from rca import migrations, problems, store

    db_path = tmp_path / "sources.sqlite3"
    load_sources(db_path, ROOT / "data" / "sources")
    problem_id = _work_in_the_application(db_path)

    copy = storage.clear_application_state(db_path)

    assert copy is not None and copy.parent.name == migrations.BACKUP_DIR and copy.exists()
    assert store.list_rcas(db_path=db_path) == [] and problems.list_problems(db_path=db_path) == []
    assert load_sources(db_path, ROOT / "data" / "sources", reset=True) is True
    assert storage.get_problem(db_path, problem_id).status == "Open"  # the problem of the source data again


def test_an_incident_of_a_problem_is_never_deleted(tmp_path):
    import pytest

    db_path = tmp_path / "sources.sqlite3"
    load_sources(db_path, ROOT / "data" / "sources")

    with pytest.raises(ValueError, match="never deleted"):
        storage.delete_incident(db_path, "INC-2026-00482")
    assert storage.get_incident(db_path, "INC-2026-00482") is not None
