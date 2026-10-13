"""The migrations of an existing database (rca/migrations.py): they only add, run once, and keep a copy."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from rca import migrations, problems, storage

ROOT = Path(__file__).resolve().parents[1]

# problem_events as it was before version 1
OLD_EVENTS = """
    CREATE TABLE problem_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        problem_id TEXT NOT NULL,
        at TEXT NOT NULL,
        by_user TEXT NOT NULL,
        action TEXT NOT NULL,
        incident_id TEXT,
        reason TEXT
    )
"""


@pytest.fixture
def old_db(tmp_path):
    """A database as the application saved it before version 1: the problems of the source data and one
    change made in the application, no "created" event for the imported problems, no rca_id or details."""
    current = tmp_path / "current.sqlite3"
    storage.load_sources(current, ROOT / "data" / "sources")
    old = tmp_path / "data" / "old.sqlite3"
    old.parent.mkdir()
    with closing(sqlite3.connect(old)) as connection:
        for name, schema in storage.SCHEMAS.items():
            connection.execute(OLD_EVENTS if name == "problem_events" else schema)
        connection.execute("ATTACH DATABASE ? AS current", [str(current)])
        for name in storage.SCHEMAS:
            if name != "problem_events":
                connection.execute(f"INSERT INTO {name} SELECT * FROM current.{name}")
        problem_id = connection.execute("SELECT problem_id FROM problems ORDER BY problem_id LIMIT 1").fetchone()[0]
        connection.execute("INSERT INTO problem_events (problem_id, at, by_user, action, incident_id, reason) "
                           "VALUES (?, '2026-09-01T10:00:00+00:00', 'pm', 'incident_removed', 'INC-2026-00001', 'Other cause.')",
                           [problem_id])
        connection.commit()
    return old


def columns(db, table):
    with closing(sqlite3.connect(db)) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_an_old_database_is_brought_to_the_current_version(old_db):
    with closing(sqlite3.connect(old_db)) as connection:
        assert migrations.version(connection) == 0
        problem_count = connection.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
        storage.initialize_database(connection)
        assert migrations.version(connection) == migrations.CURRENT_VERSION

    assert {"rca_id", "details"} <= columns(old_db, "problem_events")
    with closing(sqlite3.connect(old_db)) as connection:
        created = connection.execute("SELECT problem_id, at, by_user, details FROM problem_events "
                                     "WHERE action = 'created'").fetchall()
        kept = connection.execute("SELECT reason FROM problem_events WHERE action = 'incident_removed'").fetchall()
    assert len(created) == problem_count  # one per problem, marked as imported
    assert all(details == '{"imported": true}' for *_, details in created)
    assert kept == [("Other cause.",)]  # what was saved before is still there, unchanged


def test_the_created_event_uses_the_saved_author_and_date(old_db):
    with closing(sqlite3.connect(old_db)) as connection:
        storage.initialize_database(connection)
    problem = problems.list_problems(db_path=old_db)[0]

    first = problems.problem_events(problem.problem_id, old_db)[0]

    assert (first.action, first.by, first.at, first.details) == ("created", problem.created_by, problem.created_at,
                                                                  {"imported": True})


def test_a_copy_is_written_before_and_the_migration_runs_once(old_db):
    for _ in range(3):
        with closing(sqlite3.connect(old_db)) as connection:
            storage.initialize_database(connection)

    copies = list((old_db.parent / migrations.BACKUP_DIR).iterdir())
    assert len(copies) == 1  # only the first connection migrated
    with closing(sqlite3.connect(copies[0])) as copy:
        assert migrations.version(copy) == 0  # the copy is the database as it was: the rollback
        assert copy.execute("SELECT COUNT(*) FROM problem_events WHERE action = 'created'").fetchone()[0] == 0
    with closing(sqlite3.connect(old_db)) as connection:
        events = connection.execute("SELECT COUNT(*) FROM problem_events WHERE action = 'created'").fetchone()[0]
        problem_count = connection.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
    assert events == problem_count  # not added twice


def test_a_new_database_needs_no_copy(tmp_path):
    db = tmp_path / "new.sqlite3"

    storage.load_sources(db, ROOT / "data" / "sources")

    assert not (tmp_path / migrations.BACKUP_DIR).exists()
    with closing(sqlite3.connect(db)) as connection:
        assert migrations.version(connection) == migrations.CURRENT_VERSION


# Version 2: the RCAs saved before E3 ---------------------------------------------------------


def old_record(rca_id, status, problem_id, **changes):
    """An RCA as it was saved before E3: one analysis, its case, its old status, its decision inside."""
    import json

    record = json.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(encoding="utf-8"))
    for key in ("revision", "previous_revision_id", "run_status", "error", "guidance", "review_rounds"):
        record.pop(key, None)
    return {**record, "rca_id": rca_id, "status": status, "problem_id": problem_id, "case_id": None, "cycle": 1,
            "parent_rca_id": None, **changes}


def add_old_rcas(db, *records):
    import json

    with closing(sqlite3.connect(db)) as connection:
        connection.execute("CREATE TABLE rca_records (rca_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, status TEXT "
                           "NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL)")
        for record in records:
            connection.execute("INSERT INTO rca_records VALUES (?, ?, ?, ?, ?, ?)",
                               [record["rca_id"], record["incident_id"], record["status"], record["created_at"],
                                "2026-09-20T10:00:00+00:00", json.dumps(record)])
        connection.commit()


def test_the_rcas_saved_before_become_rcas_with_revisions_and_their_problems_follow(old_db):
    from rca import store

    with closing(sqlite3.connect(old_db)) as connection:
        open_problems = [row[0] for row in connection.execute(
            "SELECT problem_id FROM problems WHERE status = 'Open' ORDER BY problem_id LIMIT 3")]
    approve = {"reviewer": "expert1", "decision": "APPROVE", "hypothesis_id": "HYP-001", "comment": "Approved.",
               "decided_at": "2026-09-16T10:00:00+00:00", "requested_checks": [], "guidance": None}
    more = {**approve, "decision": "REQUEST_MORE_DETAILS", "hypothesis_id": None, "comment": "Check the pool."}
    validated = old_record("RCA-2026-00001", "FINAL", open_problems[0], review=approve)
    validated["final_root_cause"] = next(h["candidate_root_cause"] for h in validated["hypotheses"]
                                         if h["hypothesis_id"] == "HYP-001")
    add_old_rcas(old_db,
                 validated,
                 old_record("RCA-2026-00002", "PENDING_REVIEW", open_problems[1]),
                 old_record("RCA-2026-00003", "MORE_DETAILS_REQUESTED", open_problems[2], review=more),
                 old_record("RCA-2026-00004", "PENDING_REVIEW", open_problems[2], case_id="RCA-2026-00003", cycle=2,
                            parent_rca_id="RCA-2026-00003"))

    with closing(sqlite3.connect(old_db)) as connection:
        storage.initialize_database(connection)

    found = {item.rca_id: (item.status, item.revisions) for item in store.list_summaries(db_path=old_db)}
    assert found == {"RCA-2026-00001": ("VALIDATED", 1), "RCA-2026-00002": ("AWAITING_TECHNICAL_REVIEW", 1),
                     "RCA-2026-00003": ("AWAITING_TECHNICAL_REVIEW", 2)}
    first = store.get_rca("RCA-2026-00003-R1", db_path=old_db)
    assert (first.status, first.review.comment) == ("REQUEST_MORE_DETAILS", "Check the pool.")
    assert store.get_rca("RCA-2026-00003", db_path=old_db).previous_revision_id == "RCA-2026-00003-R1"
    assert store.get_rca("RCA-2026-00001", db_path=old_db).final_root_cause == validated["final_root_cause"]
    assert all(change.details == {"migrated": True} for change in store.status_history("RCA-2026-00001", old_db))
    closed = storage.get_problem(old_db, open_problems[0])
    assert (closed.status, closed.rca_id) == ("Closed", "RCA-2026-00001")
    assert storage.get_problem(old_db, open_problems[1]).status == "In investigation"
    assert storage.get_problem(old_db, open_problems[2]).status == "In investigation"
    with closing(sqlite3.connect(old_db)) as connection:  # the old table itself is kept as it was, for a rollback
        assert connection.execute("SELECT COUNT(*) FROM rca_records").fetchone()[0] == 4
    # the next RCA continues the numbering
    free = next(item.problem_id for item in problems.list_problems("Open", db_path=old_db))
    assert store.start_rca(free, "pm", db_path=old_db).rca_id == "RCA-2026-00005"


# Version 3: one guidance per problem ---------------------------------------------------------------


def test_a_text_guide_saved_before_becomes_the_notes_of_the_guidance(old_db):
    import json

    with closing(sqlite3.connect(old_db)) as connection:
        problem_id, payload = connection.execute("SELECT problem_id, payload FROM problems LIMIT 1").fetchone()
        connection.execute("UPDATE problems SET payload = ? WHERE problem_id = ?",
                           [json.dumps({**json.loads(payload), "investigation_guide": "Look at the acquirer."}), problem_id])
        connection.commit()
        storage.initialize_database(connection)

    problem = storage.get_problem(old_db, problem_id)
    assert problem.guidance.notes == "Look at the acquirer." and problem.investigation_guide is None
