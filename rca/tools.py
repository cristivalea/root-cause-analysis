"""Deterministic investigation tools: CMDB lookup, change lookup and log lookup.

Ordinary Python functions over the SQLite source database: the same input always gives the
same output, and no model is involved. They can be tested without Groq or Ollama.
"""

from datetime import datetime
from pathlib import Path

from rca import storage
from rca.config import DB_PATH
from rca.models import Change, Dependency, LogEntry, LogGroup, ServiceDependencies

MAX_LOG_EXAMPLES = 3
DEFAULT_LOG_LEVELS = ("ERROR", "WARN")


def find_dependencies(service: str, db_path: Path = DB_PATH) -> ServiceDependencies:
    """CMDB lookup: the components of a service and their direct dependencies."""
    components = storage.get_config_items_for_service(db_path, service)
    relationships = storage.get_relationships(db_path, [item.ci_id for item in components])
    targets = {
        item.ci_id: item
        for item in storage.get_config_items(db_path, [relationship.target_ci for relationship in relationships])
    }
    by_id = {item.ci_id: item for item in components}

    dependencies = [
        Dependency(
            component=by_id[relationship.source_ci],
            depends_on=targets[relationship.target_ci],
            relationship_type=relationship.relationship_type,
        )
        for relationship in relationships
        if relationship.target_ci in targets  # a relationship to an unknown component is skipped
    ]
    return ServiceDependencies(service=service, components=components, dependencies=dependencies)


def find_changes(
    services: list[str],
    window_start: datetime,
    window_end: datetime,
    db_path: Path = DB_PATH,
) -> list[Change]:
    """Change lookup: the changes on the service and its dependencies inside the window, oldest first."""
    return storage.get_changes(db_path, sorted(set(services)), window_start, window_end)


def find_logs(
    service: str,
    window_start: datetime,
    window_end: datetime,
    levels: tuple[str, ...] = DEFAULT_LOG_LEVELS,
    db_path: Path = DB_PATH,
) -> list[LogGroup]:
    """Log lookup: the log lines of a service inside the window, grouped by level and error type.

    Only the groups and a few example lines go further, so thousands of lines never reach the
    model. The ERROR groups come first, then the largest groups.
    """
    entries = storage.get_logs(db_path, service, window_start, window_end, list(levels))

    grouped: dict[tuple[str, str | None], list[LogEntry]] = {}
    for entry in entries:
        grouped.setdefault((entry.level, entry.error_type), []).append(entry)

    groups = [
        LogGroup(
            service=service,
            level=level,
            error_type=error_type,
            count=len(lines),
            first_seen=lines[0].timestamp,
            last_seen=lines[-1].timestamp,
            hosts=sorted({line.host for line in lines}),
            examples=lines[:MAX_LOG_EXAMPLES],
        )
        for (level, error_type), lines in grouped.items()
    ]
    return sorted(groups, key=lambda group: (group.level != "ERROR", -group.count, group.first_seen))
