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
