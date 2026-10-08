"""What the Problem Manager does with problems (audit_rca_project.md, O.10 and P.3).

Create a problem from incidents, add and remove incidents, move an incident from one problem to
another, close and reopen a problem, and mark an incident as needing no problem. The system only
proposes links (the suggestions); every link here is made by a person and keeps who made it and when.

The rules, enforced here and not by the interface:
- an incident belongs to one problem at most; moving it needs a reason;
- a problem never becomes empty: its last incident cannot be removed or moved, close it instead;
- a closed problem gets no new incident: reopen it, or create a new problem;
- the incidents of a closed problem stay where they are: its RCA linked them;
- incidents of different services, or far apart in time, are allowed with a warning;
- an incident added while an RCA of the problem is in progress is not in that draft: a warning
  says so, and a new revision can include it.

Every change is written to problem_events and never rewritten, so the history of a problem shows
what was done, by whom and why. A rule that refuses an operation raises ProblemError.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rca import storage, store
from rca.config import DB_PATH
from rca.models import Incident, Problem, ProblemEvent

ACTIVE_RCA = ("INVESTIGATING", "DRAFT", "PENDING_REVIEW", "MORE_DETAILS_REQUESTED")
FAR_APART = timedelta(days=180)


class ProblemError(ValueError):
    """A rule refused the operation. The message is written for the Problem Manager."""


@dataclass
class Result:
    problem: Problem
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


def list_problems(status: str | None = None, db_path: Path = DB_PATH) -> list[Problem]:
    """The problems, the most recently created first."""
    with closing(_connect(db_path)) as connection:
        sql = "SELECT problem_id FROM problems" + (" WHERE status = ?" if status else "") + " ORDER BY created_at DESC"
        ids = [row[0] for row in connection.execute(sql, [status] if status else [])]
    return [storage.get_problem(db_path, problem_id) for problem_id in ids]


def problem_events(problem_id: str, db_path: Path = DB_PATH) -> list[ProblemEvent]:
    """The history of a problem, oldest first."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT problem_id, at, by_user, action, incident_id, reason FROM problem_events "
            "WHERE problem_id = ? ORDER BY event_id", [problem_id],
        ).fetchall()
    return [ProblemEvent(problem_id=row[0], at=row[1], by=row[2], action=row[3], incident_id=row[4], reason=row[5])
            for row in rows]


def unassigned_incidents(db_path: Path = DB_PATH) -> list[Incident]:
    """The incidents in no problem that were not marked as needing none, the most recent first."""
    with closing(_connect(db_path)) as connection:
        taken = {row[0] for row in connection.execute("SELECT incident_id FROM problem_incidents")}
        taken |= {row[0] for row in connection.execute("SELECT incident_id FROM dismissed_incidents")}
    incidents = [item for item in storage.list_incidents(db_path) if item.incident_id not in taken]
    return sorted(incidents, key=lambda item: item.detected_at, reverse=True)


def rcas_of(problem_id: str, db_path: Path = DB_PATH):
    return [record for record in store.list_rcas(db_path=db_path) if record.problem_id == problem_id]


# --------------------------------------------------------------------------------------
# Changes
# --------------------------------------------------------------------------------------


def create_problem(
    incident_ids: list[str],
    by: str,
    title: str | None = None,
    description: str | None = None,
    move_reason: str | None = None,
    db_path: Path = DB_PATH,
) -> Result:
    """A new open problem with the given incidents. The title and description come from the most
    recent incident unless given. An incident already in another problem is moved only with a reason."""
    ids = list(dict.fromkeys(item.strip() for item in incident_ids if item.strip()))
    if not ids:
        raise ProblemError("A problem needs at least one incident.")
    incidents = [_incident(incident_id, db_path) for incident_id in ids]
    with closing(_connect(db_path)) as connection:
        for incident in incidents:
            _check_can_move(connection, incident.incident_id, move_reason)
        # moving every incident of a problem at once would leave it empty, even if each one alone may move
        moving: dict[str, int] = {}
        for incident in incidents:
            owner = _owner(connection, incident.incident_id)
            if owner:
                moving[owner] = moving.get(owner, 0) + 1
        for owner, count in moving.items():
            total = connection.execute("SELECT COUNT(*) FROM problem_incidents WHERE problem_id = ?", [owner]).fetchone()[0]
            if count == total:
                raise ProblemError(f"These are all the incidents of {owner}. Close {owner} instead of emptying it.")
        latest = max(incidents, key=lambda item: item.detected_at)
        now = _now()
        problem = Problem(
            problem_id=_next_problem_id(connection, now.year),
            title=(title or "").strip() or latest.title,
            description=(description or "").strip() or latest.description,
            status="Open",
            priority=_priority(incidents),
            services=sorted({item.service for item in incidents}),
            created_at=now,
            created_by=by,
            incidents=[{"incident_id": item.incident_id, "linked_at": now, "linked_by": by} for item in incidents],
        )
        _write_problem(connection, problem)
        _event(connection, problem.problem_id, by, "created")
        for incident in incidents:
            _link(connection, problem.problem_id, incident.incident_id, by, move_reason)
        connection.commit()
    return Result(storage.get_problem(db_path, problem.problem_id), _warnings(incidents))


def attach_incident(problem_id: str, incident_id: str, by: str, move_reason: str | None = None,
                    db_path: Path = DB_PATH) -> Result:
    """Add an incident to an open problem."""
    problem = _problem(problem_id, db_path)
    incident = _incident(incident_id, db_path)
    if problem.status != "Open":
        raise ProblemError(f"{problem_id} is closed. Reopen it, or create a new problem for {incident_id}.")
    if incident_id in {link.incident_id for link in problem.incidents}:
        raise ProblemError(f"{incident_id} is already in {problem_id}.")
    with closing(_connect(db_path)) as connection:
        _check_can_move(connection, incident_id, move_reason)
        _link(connection, problem_id, incident_id, by, move_reason)
        _refresh(connection, problem_id, db_path)
        connection.commit()
    updated = _problem(problem_id, db_path)
    warnings = _warnings([_incident(link.incident_id, db_path) for link in updated.incidents])
    active = [record.rca_id for record in rcas_of(problem_id, db_path) if record.status in ACTIVE_RCA]
    if active:
        warnings.append(f"{', '.join(active)} is in progress and does not include {incident_id}. "
                        "Start a new revision to include it.")
    return Result(updated, warnings)


def detach_incident(problem_id: str, incident_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> Result:
    """Remove an incident from an open problem, with a reason. The saved RCAs stay as they were."""
    problem = _problem(problem_id, db_path)
    if not (reason or "").strip():
        raise ProblemError("Give a reason to remove an incident from a problem.")
    if problem.status != "Open":
        raise ProblemError(f"{problem_id} is closed: its incidents stay as they were.")
    if incident_id not in {link.incident_id for link in problem.incidents}:
        raise ProblemError(f"{incident_id} is not in {problem_id}.")
    if len(problem.incidents) == 1:
        raise ProblemError(f"{incident_id} is the only incident of {problem_id}. Close the problem instead.")
    with closing(_connect(db_path)) as connection:
        connection.execute("DELETE FROM problem_incidents WHERE incident_id = ?", [incident_id])
        _event(connection, problem_id, by, "incident_removed", incident_id, reason.strip())
        _refresh(connection, problem_id, db_path)
        connection.commit()
    return Result(_problem(problem_id, db_path))


def close_problem(problem_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> Result:
    """Close an open problem with a reason, for example when the cause is already known."""
    problem = _problem(problem_id, db_path)
    if not (reason or "").strip():
        raise ProblemError("Give a reason to close a problem.")
    if problem.status != "Open":
        raise ProblemError(f"{problem_id} is already closed.")
    active = [record.rca_id for record in rcas_of(problem_id, db_path) if record.status in ACTIVE_RCA]
    if active:
        raise ProblemError(f"{', '.join(active)} of {problem_id} is still in progress. Finish it first.")
    return _set_status(problem, "Closed", by, reason.strip(), db_path)


def reopen_problem(problem_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> Result:
    """Reopen a closed problem, for example when it came back after the fix."""
    problem = _problem(problem_id, db_path)
    if not (reason or "").strip():
        raise ProblemError("Give a reason to reopen a problem.")
    if problem.status == "Open":
        raise ProblemError(f"{problem_id} is already open.")
    return _set_status(problem, "Open", by, reason.strip(), db_path)


def dismiss_incident(incident_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> None:
    """Mark an incident in no problem as needing none: it is no longer listed or suggested."""
    _incident(incident_id, db_path)
    if not (reason or "").strip():
        raise ProblemError("Give a reason why the incident needs no problem.")
    with closing(_connect(db_path)) as connection:
        owner = _owner(connection, incident_id)
        if owner:
            raise ProblemError(f"{incident_id} is in {owner}; remove it from the problem first.")
        connection.execute("INSERT OR REPLACE INTO dismissed_incidents VALUES (?, ?, ?, ?)",
                           [incident_id, _now().isoformat(), by, reason.strip()])
        connection.commit()


def reject_suggestion(incident_id: str, targets: list[str], by: str, db_path: Path = DB_PATH) -> None:
    """Remember that the Problem Manager rejected a suggestion for an incident, so it is not proposed
    again (audit O.10, case 14). targets: the suggested problem, or the incidents of a proposed new problem."""
    _incident(incident_id, db_path)
    if not targets:
        raise ProblemError("Say which suggestion is rejected.")
    with closing(_connect(db_path)) as connection:
        for target in targets:
            connection.execute("INSERT OR REPLACE INTO rejected_suggestions VALUES (?, ?, ?, ?)",
                               [incident_id, target, _now().isoformat(), by])
        connection.commit()


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    storage.initialize_database(connection)
    return connection


def _incident(incident_id: str, db_path: Path) -> Incident:
    incident = storage.get_incident(db_path, incident_id)
    if incident is None:
        raise ProblemError(f"Incident '{incident_id}' was not found.")
    return incident


def _problem(problem_id: str, db_path: Path) -> Problem:
    problem = storage.get_problem(db_path, problem_id)
    if problem is None:
        raise ProblemError(f"Problem '{problem_id}' was not found.")
    return problem


def _owner(connection: sqlite3.Connection, incident_id: str) -> str | None:
    row = connection.execute("SELECT problem_id FROM problem_incidents WHERE incident_id = ?", [incident_id]).fetchone()
    return row[0] if row else None


def _check_can_move(connection: sqlite3.Connection, incident_id: str, move_reason: str | None) -> None:
    """An incident in another problem may be moved only with a reason, never out of a closed problem,
    and never when it is the last incident of its problem."""
    owner = _owner(connection, incident_id)
    if owner is None:
        return
    status = connection.execute("SELECT status FROM problems WHERE problem_id = ?", [owner]).fetchone()[0]
    if status != "Open":
        raise ProblemError(f"{incident_id} belongs to the closed problem {owner}, linked by its RCA. It stays there.")
    if not (move_reason or "").strip():
        raise ProblemError(f"{incident_id} is already in {owner}. Give a reason to move it.")
    count = connection.execute("SELECT COUNT(*) FROM problem_incidents WHERE problem_id = ?", [owner]).fetchone()[0]
    if count == 1:
        raise ProblemError(f"{incident_id} is the only incident of {owner}. Close {owner} instead of emptying it.")


def _link(connection: sqlite3.Connection, problem_id: str, incident_id: str, by: str, move_reason: str | None) -> None:
    owner = _owner(connection, incident_id)
    now = _now().isoformat()
    if owner is not None:
        _event(connection, owner, by, "incident_moved_out", incident_id, move_reason)
        _event(connection, problem_id, by, "incident_moved_in", incident_id, move_reason)
    else:
        _event(connection, problem_id, by, "incident_added", incident_id)
    connection.execute("INSERT OR REPLACE INTO problem_incidents VALUES (?, ?, ?, ?)", [incident_id, problem_id, now, by])
    connection.execute("DELETE FROM dismissed_incidents WHERE incident_id = ?", [incident_id])
    if owner is not None:
        _refresh(connection, owner, None)


def _event(connection: sqlite3.Connection, problem_id: str, by: str, action: str,
           incident_id: str | None = None, reason: str | None = None) -> None:
    connection.execute(
        "INSERT INTO problem_events (problem_id, at, by_user, action, incident_id, reason) VALUES (?, ?, ?, ?, ?, ?)",
        [problem_id, _now().isoformat(), by, action, incident_id, reason],
    )


def _write_problem(connection: sqlite3.Connection, problem: Problem) -> None:
    connection.execute(
        """INSERT INTO problems VALUES (?, ?, ?, ?)
           ON CONFLICT(problem_id) DO UPDATE SET status=excluded.status, payload=excluded.payload""",
        [problem.problem_id, problem.status, problem.created_at.isoformat(),
         json.dumps(problem.model_dump(mode="json", exclude={"incidents"}))],
    )


def _refresh(connection: sqlite3.Connection, problem_id: str, db_path: Path | None) -> None:
    """Recompute the priority and the services of a problem from its incidents."""
    payload = json.loads(connection.execute("SELECT payload FROM problems WHERE problem_id = ?", [problem_id]).fetchone()[0])
    ids = [row[0] for row in connection.execute("SELECT incident_id FROM problem_incidents WHERE problem_id = ?", [problem_id])]
    rows = [json.loads(row[0]) for row in connection.execute(
        f"SELECT payload FROM incidents WHERE incident_id IN ({','.join('?' * len(ids))})", ids)] if ids else []
    if rows:
        incidents = [Incident.model_validate(row) for row in rows]
        payload["priority"] = _priority(incidents)
        payload["services"] = sorted({item.service for item in incidents})
    connection.execute("UPDATE problems SET payload = ? WHERE problem_id = ?", [json.dumps(payload), problem_id])


def _set_status(problem: Problem, status: str, by: str, reason: str, db_path: Path) -> Result:
    now = _now()
    updated = problem.model_copy(update={
        "status": status,
        "closed_at": now if status == "Closed" else None,
        "close_reason": reason if status == "Closed" else None,
    })
    with closing(_connect(db_path)) as connection:
        _write_problem(connection, updated)
        _event(connection, problem.problem_id, by, "closed" if status == "Closed" else "reopened", reason=reason)
        connection.commit()
    return Result(_problem(problem.problem_id, db_path))


def _next_problem_id(connection: sqlite3.Connection, year: int) -> str:
    row = connection.execute(
        "SELECT problem_id FROM problems WHERE problem_id LIKE ? ORDER BY problem_id DESC LIMIT 1", [f"PRB-{year}-%"]
    ).fetchone()
    number = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
    return f"PRB-{year}-{number:05d}"


def _priority(incidents: list[Incident]) -> str:
    return f"P{min(int(item.severity[-1]) for item in incidents)}"


def _warnings(incidents: list[Incident]) -> list[str]:
    """What the Problem Manager should know about the incidents of one problem, without blocking."""
    warnings = []
    services = sorted({item.service for item in incidents})
    if len(services) > 1:
        warnings.append(f"The incidents are on different services ({', '.join(services)}): the RCA will search all of them.")
    times = sorted(item.detected_at for item in incidents)
    if times and times[-1] - times[0] > FAR_APART:
        warnings.append(f"The incidents are {(times[-1] - times[0]).days} days apart: check that they share one cause.")
    return warnings
