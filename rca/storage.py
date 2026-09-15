"""SQLite storage for validated structured source data."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from rca.models import Change, CIRelationship, ConfigItem, Incident, LogEntry


SCHEMAS = {
    "incidents": """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            service TEXT NOT NULL,
            business_service TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            environment TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            resolved_at TEXT,
            payload TEXT NOT NULL
        )
    """,
    "cmdb_items": """
        CREATE TABLE IF NOT EXISTS cmdb_items (
            ci_id TEXT PRIMARY KEY,
            service TEXT NOT NULL,
            type TEXT NOT NULL,
            environment TEXT NOT NULL,
            criticality TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """,
    "cmdb_relationships": """
        CREATE TABLE IF NOT EXISTS cmdb_relationships (
            source_ci TEXT NOT NULL,
            target_ci TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            PRIMARY KEY (source_ci, target_ci, relationship_type)
        )
    """,
    "changes": """
        CREATE TABLE IF NOT EXISTS changes (
            change_id TEXT PRIMARY KEY,
            service TEXT NOT NULL,
            ci_id TEXT NOT NULL,
            implemented_at TEXT NOT NULL,
            type TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """,
    "logs": """
        CREATE TABLE IF NOT EXISTS logs (
            log_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            level TEXT NOT NULL,
            host TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """,
}


def _read_records(sources_dir: Path, filename: str) -> list[dict[str, Any]]:
    return json.loads((sources_dir / filename).read_text(encoding="utf-8"))


def initialize_database(connection: sqlite3.Connection) -> None:
    for schema in SCHEMAS.values():
        connection.execute(schema)
    connection.commit()


def load_sources(db_path: Path, sources_dir: Path) -> None:
    incidents = [Incident.model_validate(item) for item in _read_records(sources_dir, "incidents.json")]
    cmdb_items = [ConfigItem.model_validate(item) for item in _read_records(sources_dir, "cmdb_items.json")]
    relationships = [CIRelationship.model_validate(item) for item in _read_records(sources_dir, "cmdb_relationships.json")]
    changes = [Change.model_validate(item) for item in _read_records(sources_dir, "changes.json")]
    logs = [LogEntry.model_validate(item) for item in _read_records(sources_dir, "logs.json")]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        initialize_database(connection)
        connection.executemany(
            """INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(incident_id) DO UPDATE SET
               service=excluded.service, business_service=excluded.business_service,
               severity=excluded.severity, status=excluded.status,
               environment=excluded.environment, detected_at=excluded.detected_at,
               resolved_at=excluded.resolved_at, payload=excluded.payload""",
            [
                (
                    item.incident_id, item.service, item.business_service, item.severity,
                    item.status, item.environment, item.detected_at.isoformat(),
                    item.resolved_at.isoformat() if item.resolved_at else None,
                    json.dumps(item.model_dump(mode="json")),
                )
                for item in incidents
            ],
        )
        connection.executemany(
            """INSERT INTO cmdb_items VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(ci_id) DO UPDATE SET
               service=excluded.service, type=excluded.type,
               environment=excluded.environment, criticality=excluded.criticality,
               payload=excluded.payload""",
            [
                (item.ci_id, item.service, item.type, item.environment, item.criticality,
                 json.dumps(item.model_dump(mode="json")))
                for item in cmdb_items
            ],
        )
        connection.executemany(
            """INSERT INTO cmdb_relationships VALUES (?, ?, ?)
               ON CONFLICT(source_ci, target_ci, relationship_type) DO NOTHING""",
            [(item.source_ci, item.target_ci, item.relationship_type) for item in relationships],
        )
        connection.executemany(
            """INSERT INTO changes VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(change_id) DO UPDATE SET
               service=excluded.service, ci_id=excluded.ci_id,
               implemented_at=excluded.implemented_at, type=excluded.type,
               payload=excluded.payload""",
            [
                (item.change_id, item.service, item.ci_id, item.implemented_at.isoformat(),
                 item.type, json.dumps(item.model_dump(mode="json")))
                for item in changes
            ],
        )
        connection.executemany(
            """INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(log_id) DO UPDATE SET
               timestamp=excluded.timestamp, service=excluded.service,
               level=excluded.level, host=excluded.host, payload=excluded.payload""",
            [
                (item.log_id, item.timestamp.isoformat(), item.service, item.level, item.host,
                 json.dumps(item.model_dump(mode="json")))
                for item in logs
            ],
        )
        connection.commit()
