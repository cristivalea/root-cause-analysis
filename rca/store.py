"""RCA record store: saves and reads the generated RCAs in SQLite.

The pipeline and the interface use only these functions, so they do not depend on how the
RCAs are stored. Each RCA is kept whole as JSON in `payload`; the other columns are there to
search and sort (for example, the drafts waiting for review).
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from rca.config import DB_PATH
from rca.models import RCARecord, RCAStatus

SCHEMA = """
    CREATE TABLE IF NOT EXISTS rca_records (
        rca_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute(SCHEMA)
    return connection


def save_rca(record: RCARecord, db_path: Path = DB_PATH) -> None:
    """Save a new RCA, or replace the stored version of an existing one."""
    with closing(_connect(db_path)) as connection:
        connection.execute(
            """INSERT INTO rca_records VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(rca_id) DO UPDATE SET
               incident_id=excluded.incident_id, status=excluded.status,
               updated_at=excluded.updated_at, payload=excluded.payload""",
            (
                record.rca_id,
                record.incident_id,
                record.status,
                record.created_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                record.model_dump_json(),
            ),
        )
        connection.commit()


def get_rca(rca_id: str, db_path: Path = DB_PATH) -> RCARecord | None:
    with closing(_connect(db_path)) as connection:
        row = connection.execute("SELECT payload FROM rca_records WHERE rca_id = ?", (rca_id,)).fetchone()
    return RCARecord.model_validate(json.loads(row[0])) if row else None


def list_rcas(status: RCAStatus | None = None, db_path: Path = DB_PATH) -> list[RCARecord]:
    """The stored RCAs, newest first, optionally only those with one status."""
    sql = "SELECT payload FROM rca_records"
    params: tuple = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY julianday(created_at) DESC"

    with closing(_connect(db_path)) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [RCARecord.model_validate(json.loads(row[0])) for row in rows]


def next_rca_id(year: int, db_path: Path = DB_PATH) -> str:
    """The id for a new RCA in the given year: RCA-2026-00001, RCA-2026-00002, ..."""
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            "SELECT rca_id FROM rca_records WHERE rca_id LIKE ? ORDER BY rca_id DESC LIMIT 1",
            (f"RCA-{year}-%",),
        ).fetchone()
    number = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
    return f"RCA-{year}-{number:05d}"


def apply_review(
    rca_id: str,
    reviewer: str,
    decision: str,
    comment: str,
    hypothesis_id: str | None = None,
    db_path: Path = DB_PATH,
    requested_checks: list[str] | None = None,
) -> RCARecord:
    """Apply the Technical Expert's decision to a stored RCA and return the updated record.

    APPROVE needs the id of the approved hypothesis and makes the RCA FINAL with its
    candidate root cause. REJECT marks the record REJECTED. REQUEST_MORE_DETAILS records
    what the expert wants verified and marks the record MORE_DETAILS_REQUESTED; the next
    investigation of the case answers it (see `start_next_cycle`).

    Each decision is stored as a ReviewDecision, so who decided, when and why stays with
    the record. "REANALYZE" is still accepted as the older name of REQUEST_MORE_DETAILS.
    """
    from datetime import datetime, timezone

    from rca.models import ReviewDecision

    record = get_rca(rca_id, db_path=db_path)
    if record is None:
        raise ValueError(f"RCA '{rca_id}' was not found.")

    now = datetime.now(timezone.utc)
    if decision == "APPROVE":
        hypothesis = next((h for h in record.hypotheses if h.hypothesis_id == hypothesis_id), None)
        if hypothesis is None:
            raise ValueError(f"Hypothesis '{hypothesis_id}' was not found on {rca_id}.")
        record.review = ReviewDecision(
            reviewer=reviewer, decision="APPROVE", hypothesis_id=hypothesis_id,
            comment=comment, decided_at=now,
        )
        record.final_root_cause = hypothesis.candidate_root_cause
        record.status = "FINAL"
        record.completed_at = now
    elif decision == "REJECT":
        record.review = ReviewDecision(
            reviewer=reviewer, decision="REJECT", hypothesis_id=None,
            comment=comment, decided_at=now,
        )
        record.status = "REJECTED"
        record.completed_at = now
    elif decision in ("REQUEST_MORE_DETAILS", "REANALYZE"):
        record.review = ReviewDecision(
            reviewer=reviewer, decision="REQUEST_MORE_DETAILS", hypothesis_id=None,
            comment=comment, decided_at=now, requested_checks=requested_checks or [],
        )
        record.status = "MORE_DETAILS_REQUESTED"
        record.not_checked = record.not_checked + [f"Technical Expert asked for more detail: {comment}"]
    else:
        raise ValueError(f"Unknown decision '{decision}'.")

    save_rca(record, db_path=db_path)
    return record


def submit_for_review(rca_id: str, db_path: Path = DB_PATH) -> RCARecord:
    """Mark a stored DRAFT record as sent to the Technical Expert (PENDING_REVIEW).

    The pipeline saves the result as a draft; the Problem Manager sends it to the
    expert explicitly, from the interface. A record that already left the draft
    state is returned unchanged.
    """
    record = get_rca(rca_id, db_path=db_path)
    if record is None:
        raise ValueError(f"RCA '{rca_id}' was not found.")
    if record.status == "DRAFT":
        record.status = "PENDING_REVIEW"
        save_rca(record, db_path=db_path)
    return record


def start_next_cycle(previous_rca_id: str, new_rca_id: str, db_path: Path = DB_PATH) -> RCARecord:
    """Tie a new analysis to the case of the one before it, and return the new record.

    An incident can be investigated several times: rejected, or sent back for more detail.
    Each investigation is kept whole; the case is what holds them together, in order.
    """
    previous = get_rca(previous_rca_id, db_path=db_path)
    new_record = get_rca(new_rca_id, db_path=db_path)
    if previous is None or new_record is None:
        raise ValueError(f"Both '{previous_rca_id}' and '{new_rca_id}' must exist.")

    case_id = previous.case
    if previous.case_id != case_id:
        previous.case_id = case_id
        save_rca(previous, db_path=db_path)

    new_record.case_id = case_id
    new_record.cycle = previous.cycle + 1
    new_record.parent_rca_id = previous.rca_id
    save_rca(new_record, db_path=db_path)
    return new_record


def list_case(case_id: str, db_path: Path = DB_PATH) -> list[RCARecord]:
    """Every analysis of one case, oldest cycle first."""
    records = [record for record in list_rcas(db_path=db_path) if record.case == case_id]
    return sorted(records, key=lambda record: (record.cycle, record.created_at))


def list_cases(db_path: Path = DB_PATH) -> list[list[RCARecord]]:
    """The cases, newest first, each one as its list of analyses."""
    cases: dict[str, list[RCARecord]] = {}
    for record in list_rcas(db_path=db_path):
        cases.setdefault(record.case, []).append(record)
    ordered = [sorted(items, key=lambda item: (item.cycle, item.created_at)) for items in cases.values()]
    return sorted(ordered, key=lambda items: items[-1].created_at, reverse=True)
