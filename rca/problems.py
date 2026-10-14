"""What the Problem Manager does with problems (final_project_steps.md, E2).

Create a problem from incidents, add and remove incidents, keep the investigation guide of a problem,
close and reopen a problem, and mark an incident as needing no problem. The system only proposes
links (the suggestions); every link here is made by a person and keeps who made it, when and why.

The rules, enforced here and not by the interface:
- an incident belongs to one problem at most, whatever the status of that problem: an incident of
  another problem is refused, never moved. A wrong link is undone by removing the incident from its
  problem, with a reason, and adding it where it belongs. The database enforces it too
  (problem_incidents.incident_id is the primary key), so two requests at the same time cannot both
  link the same incident;
- a problem never becomes empty: its last incident cannot be removed, close the problem instead;
- the incidents of a problem change only while it is Open. In investigation the RCA in progress covers
  its incidents and waits for the expert, so none is added or removed; a closed problem gets no new
  incident: reopen it, or create a new problem. The guide may still change in investigation;
- the incidents of a closed problem stay where they are: its RCA linked them;
- incidents of different services, or far apart in time, are allowed with a warning;
- every incident in no problem is in a proposal of rca/suggestions.py, an incident removed from a problem
  included: none is set aside as needing no problem, and a lone incident cannot be rejected.

And for starting an RCA (check_can_start, called by store.start_rca under its write lock):
- only an Open problem gets an RCA, and one at a time: the RCA puts the problem In investigation until
  the final decision (rca/store.py says which status the problem takes after each decision);
- after a rejected RCA, a new one must start from something new (an incident added or removed, the
  guide changed, or other guidance): the same input would give the same answer;
- after MAX_REJECTED_CASES rejected RCAs, or an RCA escalated to manual review, the problem is in
  manual review (status Manual): it gets no further RCA.

Every change runs in one transaction that holds the write lock from its first read (BEGIN IMMEDIATE),
so the checks and the writes see the same data, and a new id is never given twice. Every change is
written to problem_events and never rewritten, so the history of a problem shows what was done, by
whom and why. A rule that refuses an operation raises ProblemError; ProblemConflict when the
operation conflicts with the current state (an incident already in a problem).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from rca import storage, store
from rca.config import DB_PATH
from rca.models import Incident, InvestigationGuidance, Problem, ProblemEvent, RCARecord
from rca.store import ACTIVE_RCA

EDITABLE = ("Open", "In investigation")  # the statuses in which the guide may change
INCIDENTS_EDITABLE = ("Open",)  # the statuses in which incidents are added or removed
FAR_APART = timedelta(days=180)
MAX_REJECTED_CASES = 2  # after the second rejected RCA the problem goes to manual review
MAX_GUIDE_LENGTH = 4000  # characters of the investigation guide; it is read by the agents
LOCK_TIMEOUT = 10.0  # seconds a change waits for another change to finish before it gives up


class ProblemError(ValueError):
    """A rule refused the operation. The message is written for the Problem Manager."""


class ProblemConflict(ProblemError):
    """The operation conflicts with the current state, for example an incident already in a problem."""


@dataclass
class Result:
    problem: Problem
    warnings: list[str] = field(default_factory=list)
    created: bool = True  # False when a repeated accept of a proposal returned what the first one made


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
            "SELECT problem_id, at, by_user, action, incident_id, reason, rca_id, details FROM problem_events "
            "WHERE problem_id = ? ORDER BY julianday(at), event_id", [problem_id],
        ).fetchall()
    return [ProblemEvent(problem_id=row[0], at=row[1], by=row[2], action=row[3], incident_id=row[4], reason=row[5],
                         rca_id=row[6], details=json.loads(row[7]) if row[7] else {})
            for row in rows]


def unassigned_incidents(db_path: Path = DB_PATH) -> list[Incident]:
    """Every incident in no problem, the most recent first."""
    with closing(_connect(db_path)) as connection:
        taken = {row[0] for row in connection.execute("SELECT incident_id FROM problem_incidents")}
    incidents = [item for item in storage.list_incidents(db_path) if item.incident_id not in taken]
    return sorted(incidents, key=lambda item: item.detected_at, reverse=True)


def rcas_of(problem_id: str, db_path: Path = DB_PATH) -> list[RCARecord]:
    """The latest revision of every RCA of the problem, the most recent RCA first."""
    return store.list_rcas(problem_id=problem_id, db_path=db_path)


def check_can_start(problem_id: str, guidance: InvestigationGuidance | None = None, db_path: Path = DB_PATH) -> None:
    """Refuse, with the reason, an RCA the rules do not allow on this problem (see the module text)."""
    problem = _problem(problem_id, db_path)
    rcas = store.list_summaries(problem_id=problem_id, db_path=db_path)
    active = [item for item in rcas if item.status in ACTIVE_RCA]
    if active:
        raise ProblemConflict(f"{active[0].rca_id} of {problem_id} is in progress ({active[0].status}): one RCA at a "
                              "time. Continue it from the Investigation page.")
    if problem.status != "Open":
        reason = {"Manual": "it is in manual review, outside the application",
                  "Closed": "it is closed; reopen it first"}.get(problem.status, f"it is {problem.status.lower()}")
        raise ProblemError(f"{problem_id} gets no new RCA: {reason}.")
    rejected = [item for item in rcas if item.status == "REJECTED"]
    if len(rejected) >= MAX_REJECTED_CASES:
        raise ProblemError(f"{problem_id} already has {len(rejected)} rejected RCAs: it is in manual review.")
    if rejected:
        last = max(rejected, key=lambda item: item.updated_at)
        changed = [event for event in problem_events(problem_id, db_path)
                   if event.at > last.updated_at and event.action in ("incident_added", "incident_removed", "guide_updated")]
        used = [item.guidance for item in store.list_revisions(last.rca_id, db_path)]
        new_guidance = guidance is not None and guidance != InvestigationGuidance() and guidance not in used
        if not (changed or new_guidance):
            raise ProblemError(f"The last RCA of {problem_id} ({last.rca_id}) was rejected. Add or remove incidents, change "
                               "the investigation guide or give other guidance first: the same input would give the same answer.")


# --------------------------------------------------------------------------------------
# Changes
# --------------------------------------------------------------------------------------


def create_problem(
    incident_ids: list[str],
    by: str,
    title: str | None = None,
    description: str | None = None,
    reason: str | None = None,
    db_path: Path = DB_PATH,
    proposal: tuple[str, str] | None = None,
    manual: bool = False,
) -> Result:
    """A new open problem with the given incidents, none of which may be in a problem already.
    The title and description come from the most recent incident unless given. reason, optional,
    says why these incidents belong together; it is kept in the history.

    proposal, (key, kind), when the problem is made from a proposal of the Proposed Problem Records page:
    the proposal is marked accepted in the same transaction, and accepting it again returns the problem it
    made (created False) instead of a second one.

    manual: the Problem Manager chose the incidents without a proposal. No score supports the grouping, so the
    reason is required; the history says the problem was created manually."""
    ids = list(dict.fromkeys(item.strip() for item in incident_ids if item.strip()))
    if not ids:
        raise ProblemError("A problem needs at least one incident.")
    if manual and not _text(reason):
        raise ProblemError("Give a reason: a problem created manually has no proposal behind it.")
    incidents = [_incident(incident_id, db_path) for incident_id in ids]
    latest = max(incidents, key=lambda item: item.detected_at)
    with _transaction(db_path) as connection:
        made = _accepted(connection, proposal)
        if made is not None:
            return Result(_problem(made, db_path), created=False)
        for incident in incidents:
            _check_free(connection, incident.incident_id)
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
        connection.execute("INSERT INTO problems VALUES (?, ?, ?, ?)",
                           [problem.problem_id, problem.status, problem.created_at.isoformat(), _payload(problem)])
        _event(connection, problem.problem_id, by, "created", reason=_text(reason),
               details={"proposal": proposal[0]} if proposal else {"manual": True} if manual else None)
        for incident in incidents:
            _link(connection, problem.problem_id, incident.incident_id, by, _text(reason))
        _decide(connection, proposal, ids, problem.problem_id, "accepted", by, _text(reason))
    return Result(storage.get_problem(db_path, problem.problem_id), _warnings(incidents))


def attach_incident(problem_id: str, incident_id: str, by: str, reason: str | None = None,
                    db_path: Path = DB_PATH, proposal: tuple[str, str] | None = None) -> Result:
    """Add an incident in no problem to an open problem. reason, optional, is kept in the history.
    proposal, (key, kind): as for create_problem, accepted once in the same transaction."""
    _incident(incident_id, db_path)
    with _transaction(db_path) as connection:
        made = _accepted(connection, proposal)
        if made is not None:
            return Result(_problem(made, db_path), created=False)
        problem = _read_problem(connection, problem_id)
        if problem is None:
            raise ProblemError(f"Problem '{problem_id}' was not found.")
        if problem["status"] == "Manual":
            raise ProblemError(f"{problem_id} is in manual review, outside the application. "
                               f"Create a new problem for {incident_id}.")
        if problem["status"] == "In investigation":
            raise ProblemError(f"{problem_id} is in investigation: its RCA waits for the expert, so no incident is "
                               "added until the RCA is decided.")
        if problem["status"] not in INCIDENTS_EDITABLE:
            raise ProblemError(f"{problem_id} is closed. Reopen it, or create a new problem for {incident_id}.")
        _check_free(connection, incident_id)
        _link(connection, problem_id, incident_id, by, _text(reason))
        _refresh(connection, problem_id)
        _decide(connection, proposal, [incident_id], problem_id, "accepted", by, _text(reason))
    updated = _problem(problem_id, db_path)
    return Result(updated, _warnings([_incident(link.incident_id, db_path) for link in updated.incidents]))


def detach_incident(problem_id: str, incident_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> Result:
    """Remove an incident from an open problem, with a reason. The incident itself is kept, and can be
    proposed and added again. The saved RCAs stay as they were."""
    if not _text(reason):
        raise ProblemError("Give a reason to remove an incident from a problem.")
    with _transaction(db_path) as connection:
        problem = _read_problem(connection, problem_id)
        if problem is None:
            raise ProblemError(f"Problem '{problem_id}' was not found.")
        if problem["status"] == "In investigation":
            raise ProblemError(f"{problem_id} is in investigation: its RCA waits for the expert, so no incident is "
                               "removed until the RCA is decided.")
        if problem["status"] not in INCIDENTS_EDITABLE:
            raise ProblemError(f"{problem_id} is {problem['status'].lower()}: its incidents stay as they were.")
        linked = [row[0] for row in connection.execute(
            "SELECT incident_id FROM problem_incidents WHERE problem_id = ?", [problem_id])]
        if incident_id not in linked:
            raise ProblemError(f"{incident_id} is not in {problem_id}.")
        if len(linked) == 1:
            raise ProblemError(f"{incident_id} is the only incident of {problem_id}. Close the problem instead.")
        connection.execute("DELETE FROM problem_incidents WHERE incident_id = ?", [incident_id])
        _event(connection, problem_id, by, "incident_removed", incident_id, _text(reason))
        _refresh(connection, problem_id)
    return Result(_problem(problem_id, db_path))


def set_guidance(problem_id: str, guidance: InvestigationGuidance | None, by: str, db_path: Path = DB_PATH) -> Result:
    """Save the guidance for the investigation of the problem (notes, instructions or questions, more services,
    wider windows). Shown again at the next start and used by Start RCA; each change is in the history with
    its content. Empty guidance clears it; saving the same guidance changes nothing."""
    with _transaction(db_path) as connection:
        problem = _read_problem(connection, problem_id)
        if problem is None:
            raise ProblemError(f"Problem '{problem_id}' was not found.")
        if problem["status"] not in EDITABLE:
            raise ProblemError(f"{problem_id} is {problem['status'].lower()}: its guidance stays as it was.")
        save_guidance(connection, problem_id, guidance, by, db_path)
    return Result(_problem(problem_id, db_path))


def save_guidance(connection: sqlite3.Connection, problem_id: str, guidance: InvestigationGuidance | None, by: str,
                  db_path: Path) -> bool:
    """Save the guidance inside a transaction, after checking it; returns whether it changed. Called by
    set_guidance and by store.start_rca, so the guidance an RCA starts with is the one the problem keeps."""
    cleaned = _cleaned(guidance)
    for service in cleaned.extra_services if cleaned else []:
        if not storage.get_config_items_for_service(db_path, service):
            raise ProblemError(f"Service '{service}' is not in the CMDB.")
    for text in (cleaned.notes, cleaned.instructions) if cleaned else []:
        if text and len(text) > MAX_GUIDE_LENGTH:
            raise ProblemError(f"The guidance is too long: at most {MAX_GUIDE_LENGTH} characters per text.")
    saved = (_read_problem(connection, problem_id) or {}).get("guidance")
    value = cleaned.model_dump(mode="json") if cleaned else None
    if saved == value:
        return False
    _update_problem(connection, problem_id, guidance=value)
    _event(connection, problem_id, by, "guide_updated", details={"guidance": value})
    return True


def _cleaned(guidance: InvestigationGuidance | None) -> InvestigationGuidance | None:
    """The guidance without spaces around its texts and without duplicate services; None when it is empty."""
    if guidance is None:
        return None
    cleaned = guidance.model_copy(update={
        "notes": _text(guidance.notes), "instructions": _text(guidance.instructions),
        "extra_services": list(dict.fromkeys(item.strip() for item in guidance.extra_services if item.strip())),
    })
    return None if cleaned == InvestigationGuidance() else cleaned


def close_problem(problem_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> Result:
    """Close a problem with a reason: an open one whose cause is already known, or one solved manually."""
    problem = _problem(problem_id, db_path)
    if not _text(reason):
        raise ProblemError("Give a reason to close a problem.")
    if problem.status == "Closed":
        raise ProblemError(f"{problem_id} is already closed.")
    active = [item.rca_id for item in store.list_summaries(problem_id=problem_id, db_path=db_path)
              if item.status in ACTIVE_RCA]
    if active:
        raise ProblemError(f"{', '.join(active)} of {problem_id} is still in progress. Finish it first.")
    return _set_status(problem_id, "Closed", by, _text(reason), db_path)


def reopen_problem(problem_id: str, by: str, reason: str, db_path: Path = DB_PATH) -> Result:
    """Reopen a closed problem, for example when it came back after the fix."""
    problem = _problem(problem_id, db_path)
    if not _text(reason):
        raise ProblemError("Give a reason to reopen a problem.")
    if problem.status == "Open":
        raise ProblemError(f"{problem_id} is already open.")
    if problem.status in ("Manual", "In investigation"):
        raise ProblemError(f"{problem_id} is {'in manual review' if problem.status == 'Manual' else 'in investigation'}: "
                           "it is not closed.")
    return _set_status(problem_id, "Open", by, _text(reason), db_path)


def reject_proposal(key: str, kind: str, incident_ids: list[str], by: str, problem_id: str | None = None,
                    reason: str | None = None, db_path: Path = DB_PATH) -> None:
    """Remember that the Problem Manager rejected a proposal, so it is not proposed again while its incidents stay
    the same. A proposal to add an incident to a problem also stops proposing that problem for the incident."""
    if kind == "single":
        raise ProblemError("An incident on its own cannot be rejected: every incident in no problem needs one. "
                           "Accept it, or add the incident to a problem from that problem's page.")
    with _transaction(db_path) as connection:
        row = connection.execute("SELECT decision FROM proposal_decisions WHERE proposal_key = ?", [key]).fetchone()
        if row and row[0] == "accepted":
            raise ProblemConflict(f"The proposal {key} was already accepted.")
        if row:
            return
        _decide(connection, (key, kind), incident_ids, problem_id, "rejected", by, _text(reason))
        if kind == "attach" and problem_id:
            for incident_id in incident_ids:
                connection.execute("INSERT OR REPLACE INTO rejected_suggestions VALUES (?, ?, ?, ?)",
                                   [incident_id, problem_id, _now().isoformat(), by])


def reject_suggestion(incident_id: str, targets: list[str], by: str, db_path: Path = DB_PATH) -> None:
    """Remember that the Problem Manager rejected a suggestion for an incident, so it is not proposed
    again (audit O.10, case 14). targets: the suggested problem, or the incidents of a proposed new problem."""
    _incident(incident_id, db_path)
    if not targets:
        raise ProblemError("Say which suggestion is rejected.")
    with _transaction(db_path) as connection:
        for target in targets:
            connection.execute("INSERT OR REPLACE INTO rejected_suggestions VALUES (?, ?, ?, ?)",
                               [incident_id, target, _now().isoformat(), by])


# --------------------------------------------------------------------------------------
# Called by rca/store.py, inside its transaction, when an RCA changes the problem
# --------------------------------------------------------------------------------------


def change_status(connection: sqlite3.Connection, problem_id: str, status: str, by: str, rca_id: str | None = None,
                  reason: str | None = None, closed_at: datetime | None = None, close_reason: str | None = None) -> None:
    """Set the status a step of an RCA gives to its problem, with an event. Closed by a validated RCA keeps
    the RCA as the one that closed the problem (Problem.rca_id)."""
    current = (_read_problem(connection, problem_id) or {}).get("status")
    if current == status:
        return
    fields = {"status": status, "closed_at": closed_at if status == "Closed" else None,
              "close_reason": close_reason if status == "Closed" else None}
    if status == "Closed" and rca_id:
        fields["rca_id"] = rca_id
    _update_problem(connection, problem_id, **fields)
    action = {"Closed": "closed", "Manual": "manual"}.get(status, "status_changed")
    _event(connection, problem_id, by, action, reason=reason, rca_id=rca_id, details={"from": current, "to": status})


def rca_event(connection: sqlite3.Connection, problem_id: str, by: str, rca_id: str, current: str | None, new: str,
              comment: str | None) -> None:
    """A change of the status of one RCA of the problem, in the history of the problem."""
    _event(connection, problem_id, by, "rca_status", reason=comment, rca_id=rca_id, details={"from": current, "to": new})


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: str | None) -> str | None:
    """A text the user gave, without the spaces around it; None when there is nothing left."""
    return (value or "").strip() or None


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=LOCK_TIMEOUT)
    storage.initialize_database(connection)
    return connection


@contextmanager
def _transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    """One change: the write lock is taken before the first read, and everything is saved or nothing."""
    with closing(_connect(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ProblemConflict(f"The change conflicts with a change made at the same time: {exc}. "
                                  "Reload and try again.") from exc
        except BaseException:
            connection.rollback()
            raise


def _accepted(connection: sqlite3.Connection, proposal: tuple[str, str] | None) -> str | None:
    """The problem an accepted proposal made, so a repeated accept returns it; a rejected proposal is refused."""
    if proposal is None:
        return None
    row = connection.execute("SELECT decision, problem_id FROM proposal_decisions WHERE proposal_key = ?",
                             [proposal[0]]).fetchone()
    if row and row[0] == "rejected":
        raise ProblemConflict(f"The proposal {proposal[0]} was rejected.")
    return row[1] if row else None


def _decide(connection: sqlite3.Connection, proposal: tuple[str, str] | None, incident_ids: list[str],
            problem_id: str | None, decision: str, by: str, reason: str | None) -> None:
    """Plain INSERT: the key of a proposal is decided once; a second decision at the same time is refused."""
    if proposal is None:
        return
    connection.execute("INSERT INTO proposal_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       [proposal[0], proposal[1], json.dumps(incident_ids), problem_id, decision, by,
                        _now().isoformat(), reason])


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


def _read_problem(connection: sqlite3.Connection, problem_id: str) -> dict | None:
    """The saved fields of a problem (without its incidents), read inside the transaction."""
    row = connection.execute("SELECT payload FROM problems WHERE problem_id = ?", [problem_id]).fetchone()
    return json.loads(row[0]) if row else None


def _owner(connection: sqlite3.Connection, incident_id: str) -> str | None:
    row = connection.execute("SELECT problem_id FROM problem_incidents WHERE incident_id = ?", [incident_id]).fetchone()
    return row[0] if row else None


def _check_free(connection: sqlite3.Connection, incident_id: str) -> None:
    """An incident already in a problem, open or not, cannot go to another one."""
    owner = _owner(connection, incident_id)
    if owner is None:
        return
    status = connection.execute("SELECT status FROM problems WHERE problem_id = ?", [owner]).fetchone()
    shown = {"Open": "open", "Closed": "closed", "Manual": "manual review"}.get(status[0] if status else "", "")
    raise ProblemConflict(f"{incident_id} is already in the {shown} problem {owner}. An incident belongs to one "
                          f"problem only: remove it from {owner} first, with a reason, if it belongs elsewhere.")


def _link(connection: sqlite3.Connection, problem_id: str, incident_id: str, by: str, reason: str | None) -> None:
    """Plain INSERT: if another change linked the incident in the meantime, the primary key refuses it."""
    connection.execute("INSERT INTO problem_incidents VALUES (?, ?, ?, ?)", [incident_id, problem_id, _now().isoformat(), by])
    _event(connection, problem_id, by, "incident_added", incident_id, reason)


def _event(connection: sqlite3.Connection, problem_id: str, by: str, action: str, incident_id: str | None = None,
           reason: str | None = None, rca_id: str | None = None, details: dict | None = None) -> None:
    connection.execute(
        "INSERT INTO problem_events (problem_id, at, by_user, action, incident_id, reason, rca_id, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [problem_id, _now().isoformat(), by, action, incident_id, reason, rca_id,
         json.dumps(details) if details else None],
    )


def _payload(problem: Problem) -> str:
    return json.dumps(problem.model_dump(mode="json", exclude={"incidents"}))


def _update_problem(connection: sqlite3.Connection, problem_id: str, **fields) -> None:
    """Change some saved fields of an existing problem; the status column follows the payload."""
    payload = _read_problem(connection, problem_id)
    payload.update({key: value.isoformat() if isinstance(value, datetime) else value for key, value in fields.items()})
    connection.execute("UPDATE problems SET status = ?, payload = ? WHERE problem_id = ?",
                       [payload["status"], json.dumps(payload), problem_id])


def _refresh(connection: sqlite3.Connection, problem_id: str) -> None:
    """Recompute the priority and the services of a problem from its incidents."""
    ids = [row[0] for row in connection.execute("SELECT incident_id FROM problem_incidents WHERE problem_id = ?", [problem_id])]
    rows = [json.loads(row[0]) for row in connection.execute(
        f"SELECT payload FROM incidents WHERE incident_id IN ({','.join('?' * len(ids))})", ids)] if ids else []
    if rows:
        incidents = [Incident.model_validate(row) for row in rows]
        _update_problem(connection, problem_id, priority=_priority(incidents),
                        services=sorted({item.service for item in incidents}))


def _set_status(problem_id: str, status: str, by: str, reason: str, db_path: Path) -> Result:
    now = _now()
    with _transaction(db_path) as connection:
        _update_problem(connection, problem_id, status=status,
                        closed_at=now if status == "Closed" else None,
                        close_reason=reason if status == "Closed" else None)
        _event(connection, problem_id, by, "closed" if status == "Closed" else "reopened", reason=reason)
    return Result(_problem(problem_id, db_path))


def _next_problem_id(connection: sqlite3.Connection, year: int) -> str:
    """The next free id of the year. Called inside a transaction, so two changes never get the same one."""
    row = connection.execute(
        "SELECT problem_id FROM problems WHERE problem_id LIKE ? ORDER BY problem_id DESC LIMIT 1", [f"PRB-{year}-%"]
    ).fetchone()
    number = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
    return f"PRB-{year}-{number:05d}"


def _priority(incidents: list[Incident]) -> str:
    """The priority of a problem is the severity of its most severe incident: SEV-1 is P1, ..., SEV-4 is P4
    (confirmed rule, final_project_steps.md A.3). Recomputed every time an incident is added or removed."""
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
