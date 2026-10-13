"""Changes to the structure of an existing database, applied once and in order (final_project_steps.md, E2).

The version of a database is kept in PRAGMA user_version. Every connection that writes calls migrate()
(through storage.initialize_database), so an older database is brought up to date the first time the
application uses it; a database already at CURRENT_VERSION is left alone after one cheap read.

The rules every migration follows:
- it never deletes; it adds columns and rows, and changes a saved row only where its version says so,
  with an event that tells it (version 2: the status of a problem with an RCA);
- it can run twice without harm (it checks before it adds), and two processes cannot run it at the
  same time (BEGIN IMMEDIATE, then the version is read again);
- before a migration touches a database that holds problems, a copy of the whole file is written to
  backups/ next to it. Rollback: stop the application and put the copy back in place of the file.

Version 1: problem_events gets rca_id and details (a JSON object). Every problem without a "created"
event gets one, from its own created_at and created_by, marked {"imported": true}: these problems came
from the source data (data/sources/problems.json), so the history says so instead of inventing an author.

Version 2: the RCAs saved before E3 (table rca_records, one row per analysis, grouped in cases) become
RCAs with revisions (tables rcas, rca_revisions, rca_status_history; rca/store.py). Each case is one RCA
with the id of its first analysis, each analysis a revision (RCA-…-R1, -R2, …), each decision of the
expert a row of the status history, and every status is renamed (models.LEGACY_RCA_STATUS). The rows
of the history and the events written for them are marked {"migrated": true}; a moment that was never
saved (when a decided RCA was sent to the expert) is left out rather than invented. The problem of each
RCA takes the status the new rules give it (closed by a validated RCA, In investigation while its RCA is
in progress, Manual after an escalation), with an event. rca_records itself is left unchanged.

Version 3: the investigation guide of a problem (a text) and the guidance of Start RCA become one guidance,
saved on the problem. A guide already saved becomes the notes of the guidance; its history stays as it was.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

CURRENT_VERSION = 3
BACKUP_DIR = "backups"


def version(connection: sqlite3.Connection) -> int:
    return connection.execute("PRAGMA user_version").fetchone()[0]


def migrate(connection: sqlite3.Connection) -> None:
    """Bring the database of the connection to CURRENT_VERSION. The tables must exist already."""
    if version(connection) >= CURRENT_VERSION:
        return
    if connection.in_transaction:
        connection.commit()
    # The copy is taken before the write lock: a connection cannot copy a database it holds locked.
    # If another process migrates in between, this copy is one more of the same data, nothing worse.
    if connection.execute("SELECT COUNT(*) FROM problems").fetchone()[0]:
        backup(connection, f"v{version(connection)}")
    connection.execute("BEGIN IMMEDIATE")
    try:
        current = version(connection)  # another process may have migrated while this one waited
        if current < CURRENT_VERSION:
            if current < 1:
                _to_version_1(connection)
            if current < 2:
                _to_version_2(connection)
            if current < 3:
                _to_version_3(connection)
            connection.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def backup(connection: sqlite3.Connection, label: str) -> Path | None:
    """A copy of the whole database file in backups/ next to it, named with the label and the time.
    Returns its path, or None for a database in memory."""
    path = Path(connection.execute("PRAGMA database_list").fetchone()[2] or "")
    if not path.name:  # a database in memory: nothing to copy
        return None
    folder = path.parent / BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{path.stem}-{label}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}{path.suffix}"
    with closing(sqlite3.connect(target)) as copy:
        connection.backup(copy)
    return target


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _to_version_1(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "problem_events")
    if "rca_id" not in columns:
        connection.execute("ALTER TABLE problem_events ADD COLUMN rca_id TEXT")
    if "details" not in columns:
        connection.execute("ALTER TABLE problem_events ADD COLUMN details TEXT")
    add_imported_created_events(connection)


def add_imported_created_events(connection: sqlite3.Connection) -> int:
    """A "created" event, marked as imported, for every problem that has none. Returns how many were added."""
    rows = connection.execute(
        "SELECT problem_id, created_at, payload FROM problems WHERE problem_id NOT IN "
        "(SELECT problem_id FROM problem_events WHERE action = 'created') ORDER BY problem_id"
    ).fetchall()
    for problem_id, created_at, payload in rows:
        created_by = json.loads(payload).get("created_by") or "source data"
        connection.execute(
            "INSERT INTO problem_events (problem_id, at, by_user, action, incident_id, reason, rca_id, details) "
            "VALUES (?, ?, ?, 'created', NULL, NULL, NULL, ?)",
            [problem_id, created_at, created_by, json.dumps({"imported": True})],
        )
    return len(rows)


def _to_version_2(connection: sqlite3.Connection) -> None:
    """The RCAs saved before E3 become RCAs with revisions (see the module text)."""
    from rca.models import LEGACY_RCA_STATUS, RCA, RCARecord, revision_id

    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'rca_records'").fetchone():
        return
    cases: dict[str, list[tuple[dict, str]]] = {}
    for payload, updated_at in connection.execute("SELECT payload, updated_at FROM rca_records"):
        record = json.loads(payload)
        cases.setdefault(record.get("case_id") or record["rca_id"], []).append((record, updated_at))
    migrated = {"migrated": True}
    for rca_id, rows in sorted(cases.items()):
        if connection.execute("SELECT 1 FROM rcas WHERE rca_id = ?", [rca_id]).fetchone():
            continue  # already migrated
        rows.sort(key=lambda item: (item[0].get("cycle") or 1, item[0]["created_at"]))
        first = rows[0][0]
        problem_id = first.get("problem_id") or _problem_of(connection, first["incident_id"])
        if problem_id is None:
            continue  # an RCA of an incident in no problem: it stays in rca_records only
        problem_row = connection.execute("SELECT payload FROM problems WHERE problem_id = ?", [problem_id]).fetchone()
        title = json.loads(problem_row[0])["title"] if problem_row else first["incident_id"]
        history: list[tuple] = [(None, None, "DRAFT", first["owner"], first["created_at"], "RCA started.", None)]
        previous, status, rounds, sent = None, "DRAFT", 0, False
        for number, (record, updated_at) in enumerate(rows, start=1):
            old = record["status"]
            mapped = LEGACY_RCA_STATUS.get(old, "FAILED")
            review = record.get("review")
            current = revision_id(rca_id, number)
            if number > 1:
                history.append((current, "REQUEST_MORE_DETAILS", "DRAFT", record["owner"], record["created_at"],
                                f"Revision {number} started: the expert asked for more details.", None))
            if old == "ESCALATED":  # the guardrail refused every draft, or the planner gave no plan
                guardrail = any(step.get("name") == "guardrail" and "Escalated" in step.get("summary", "")
                                for step in record.get("trace", []))
                mapped = "ESCALATED_MANUAL" if guardrail else "FAILED"
            outcome = mapped if mapped in ("ESCALATED_MANUAL", "FAILED") and not review else "DRAFT"
            revision = {key: value for key, value in record.items() if key not in ("case_id", "cycle", "parent_rca_id")}
            revision |= {"rca_id": rca_id, "revision": number, "previous_revision_id": previous,
                         "run_status": "FAILED" if outcome == "FAILED" else "COMPLETED", "status": outcome,
                         "review": None, "final_root_cause": None, "problem_id": problem_id}
            saved = RCARecord.model_validate(revision)
            connection.execute("INSERT INTO rca_revisions VALUES (?, ?, ?, ?, ?, ?)",
                               [current, rca_id, number, saved.run_status, saved.created_at.isoformat(),
                                saved.model_dump_json()])
            if outcome != "DRAFT":
                history.append((current, "DRAFT", outcome, record["owner"], record.get("completed_at") or updated_at,
                                "Escalated before E3.", None))
            elif review:
                rounds, sent = rounds + 1, True
                history.append((current, "AWAITING_TECHNICAL_REVIEW", mapped, review["reviewer"], review["decided_at"],
                                review.get("comment"), json.dumps(review)))
            elif mapped == "AWAITING_TECHNICAL_REVIEW":
                sent = True
                history.append((current, "DRAFT", mapped, record["owner"], updated_at, "Sent to the Technical Expert.", None))
            status, previous = mapped, current
        last_at = max(item[4] for item in history)
        rca = RCA(rca_id=rca_id, problem_id=problem_id, title=title, status=status, created_at=first["created_at"],
                  created_by=first["owner"], updated_at=last_at, revisions=len(rows), review_rounds=rounds,
                  sent_to_expert=sent, latest_revision_id=previous)
        connection.execute("INSERT INTO rcas VALUES (?, ?, ?, ?, ?, ?)",
                           [rca_id, problem_id, status, rca.created_at.isoformat(), rca.updated_at.isoformat(),
                            rca.model_dump_json()])
        for revision, current, new, by, at, comment, decision in history:
            connection.execute(
                "INSERT INTO rca_status_history (rca_id, revision_id, from_status, to_status, by_user, at, comment, "
                "decision, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [rca_id, revision, current, new, by, at, comment, decision, json.dumps(migrated)])
            _problem_event(connection, problem_id, at, by, "rca_status", comment, rca_id,
                           {"from": current, "to": new, **migrated})
        _align_problem(connection, problem_id, rca_id, status, history[-1])


def _problem_of(connection: sqlite3.Connection, incident_id: str) -> str | None:
    row = connection.execute("SELECT problem_id FROM problem_incidents WHERE incident_id = ?", [incident_id]).fetchone()
    return row[0] if row else None


def _problem_event(connection: sqlite3.Connection, problem_id: str, at: str, by: str, action: str, reason: str | None,
                   rca_id: str | None, details: dict) -> None:
    connection.execute(
        "INSERT INTO problem_events (problem_id, at, by_user, action, incident_id, reason, rca_id, details) "
        "VALUES (?, ?, ?, ?, NULL, ?, ?, ?)", [problem_id, at, by, action, reason, rca_id, json.dumps(details)])


def _align_problem(connection: sqlite3.Connection, problem_id: str, rca_id: str, status: str, last: tuple) -> None:
    """The status the rules of E3 give to the problem of a migrated RCA, when the problem is still Open."""
    row = connection.execute("SELECT payload FROM problems WHERE problem_id = ?", [problem_id]).fetchone()
    if row is None:
        return
    problem = json.loads(row[0])
    if problem["status"] != "Open":
        return
    _, _, _, by, at, _, _ = last
    if status == "VALIDATED":
        target, action = "Closed", "closed"
        problem |= {"closed_at": at, "close_reason": f"Root cause validated in {rca_id}.", "rca_id": rca_id}
        reason = f"Root cause validated in {rca_id}."
    elif status in ("DRAFT", "AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS", "FAILED"):
        target, action, reason = "In investigation", "status_changed", f"{rca_id} is in progress."
        at = datetime.now(timezone.utc).isoformat()  # the rule is new: the change happens now
        by = "migration"
    elif status == "ESCALATED_MANUAL":
        target, action, reason = "Manual", "manual", f"{rca_id} was escalated to manual review."
    else:
        return
    problem["status"] = target
    connection.execute("UPDATE problems SET status = ?, payload = ? WHERE problem_id = ?",
                       [target, json.dumps(problem), problem_id])
    _problem_event(connection, problem_id, at, by, action, reason, rca_id,
                   {"from": "Open", "to": target, "migrated": True})


def _to_version_3(connection: sqlite3.Connection) -> None:
    """A text guide saved before becomes the notes of the guidance of its problem (see the module text)."""
    for problem_id, payload in connection.execute("SELECT problem_id, payload FROM problems").fetchall():
        problem = json.loads(payload)
        guide = (problem.get("investigation_guide") or "").strip()
        if not guide or problem.get("guidance"):
            continue
        problem["guidance"] = {"notes": guide, "instructions": None, "extra_services": [], "change_window_days": None,
                               "log_hours_before": None}
        problem["investigation_guide"] = None
        connection.execute("UPDATE problems SET payload = ? WHERE problem_id = ?", [json.dumps(problem), problem_id])
