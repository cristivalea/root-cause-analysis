"""The RCAs of the problems: their revisions, their status and its history (final_project_steps.md, E3).

An RCA belongs to one problem. Each run of the graph is a revision of the RCA (RCA-2026-00001-R1, -R2,
...): it is saved when the run starts (RUNNING) and once more when it ends (COMPLETED or FAILED), and
never changed after that. The status of the RCA lives in the table rcas and changes only through the
functions below, each one checking the transition, in one transaction with the status of the problem:

    created ──► DRAFT ──submit──► AWAITING_TECHNICAL_REVIEW ──expert──┬─► VALIDATED         problem Closed
                 │ ▲                                                   ├─► REJECTED          problem Open, or
                 │ └── next revision ◄── REQUEST_MORE_DETAILS ◄────────┤                     Manual at the 2nd
                 │ └── run again ◄────── FAILED (technical error)      └─► ESCALATED_MANUAL  problem Manual
                 └─► ESCALATED_MANUAL (the guardrail refused the draft in every attempt of a run)
                 └─► FAILED

- Starting an RCA puts its problem In investigation; only an open problem gets one (problems.check_can_start).
- A request for more details on the MAX_REVISIONS-th decision of the expert escalates the RCA instead
  (ESCALATED_MANUAL). Only the decisions of the expert count: a FAILED run is a technical error, not an attempt.
- Every change of status is a row of rca_status_history, the decisions of the expert with their content,
  and an event of the problem (problem_events, action rca_status), so the history of the problem tells
  what happened to its RCAs.

status, review and final_root_cause are filled in on every revision when it is read (_complete): the
saved revision stays as the run left it, the decisions are kept apart.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from rca import storage
from rca.config import DB_PATH
from rca.models import (RCA, InvestigationGuidance, RCARecord, RCAStatus, RCAStatusChange, ReviewDecision,
                        revision_id)

# The expert decides at most this many times on one RCA. A request for more details at the last
# decision escalates the RCA to people (ESCALATED_MANUAL) instead of a new revision.
MAX_REVISIONS = 3
# The RCA of a problem is in progress in these statuses: the problem has no other RCA meanwhile.
ACTIVE_RCA = ("DRAFT", "AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS", "FAILED")
# The changes the store makes, and nothing else.
TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"AWAITING_TECHNICAL_REVIEW", "ESCALATED_MANUAL", "FAILED"},
    "AWAITING_TECHNICAL_REVIEW": {"VALIDATED", "REJECTED", "REQUEST_MORE_DETAILS", "ESCALATED_MANUAL"},
    "REQUEST_MORE_DETAILS": {"DRAFT"},
    "FAILED": {"DRAFT"},
    "VALIDATED": set(),
    "REJECTED": set(),
    "ESCALATED_MANUAL": set(),
}
LOCK_TIMEOUT = 10.0


class RCAError(ValueError):
    """A rule refused the operation. The message is written for the user."""


class TransitionError(RCAError):
    """The RCA is not in a status that allows the operation (for example, a decision on an RCA that is
    not waiting for one). Comes back as 409."""


class RCANotFound(LookupError):
    """No RCA, or no revision, with this id."""


# --------------------------------------------------------------------------------------
# Changes
# --------------------------------------------------------------------------------------


def start_rca(problem_id: str, by: str, guidance: InvestigationGuidance | None = None,
              db_path: Path = DB_PATH, request_key: str | None = None) -> RCARecord:
    return begin_rca(problem_id, by, guidance, db_path, request_key)[0]


def begin_rca(problem_id: str, by: str, guidance: InvestigationGuidance | None = None,
              db_path: Path = DB_PATH, request_key: str | None = None) -> tuple[RCARecord, bool]:
    """Create the RCA of a problem with its first revision, RUNNING, and put the problem In investigation.
    The rules of problems.check_can_start apply: they are checked under the write lock, so two requests
    at the same time cannot both start an RCA for the problem. A request repeated with the same request_key
    (a double click, a retry of the browser) gets the revision the first one created. Returns the revision."""
    from rca import problems

    with _transaction(db_path) as connection:
        repeated = _by_request_key(connection, request_key)
        if repeated is not None:
            return repeated, False
        problems.check_can_start(problem_id, guidance, db_path=db_path)
        if guidance is not None:  # the guidance of the start is the one the problem keeps for the next one
            problems.save_guidance(connection, problem_id, guidance, by, db_path)
        problem = storage.get_problem(db_path, problem_id)
        now = _now()
        rca_id = _next_rca_id(connection, now.year)
        rca = RCA(rca_id=rca_id, problem_id=problem_id, title=problem.title, status="DRAFT", created_at=now,
                  created_by=by, updated_at=now)
        connection.execute("INSERT INTO rcas VALUES (?, ?, ?, ?, ?, ?)",
                           [rca_id, problem_id, rca.status, now.isoformat(), now.isoformat(), rca.model_dump_json()])
        _history(connection, rca_id, None, None, "DRAFT", by, "RCA started.")
        revision = _new_revision(connection, rca, 1, None, by, guidance, problem, request_key)
        problems.rca_event(connection, problem_id, by, rca_id, None, "DRAFT", "RCA started.")
        problems.change_status(connection, problem_id, "In investigation", by, rca_id=rca_id,
                               reason=f"{rca_id} started.")
    return revision, True


def start_next_revision(rca_id: str, by: str, guidance: InvestigationGuidance | None = None,
                        db_path: Path = DB_PATH, request_key: str | None = None) -> RCARecord:
    return begin_next_revision(rca_id, by, guidance, db_path, request_key)[0]


def begin_next_revision(rca_id: str, by: str, guidance: InvestigationGuidance | None = None,
                        db_path: Path = DB_PATH, request_key: str | None = None) -> tuple[RCARecord, bool]:
    """A new revision of an RCA the expert sent back for more details, or whose last run FAILED. Without
    guidance, the guidance of the previous revision is used again. A request repeated with the same
    request_key gets the revision the first one created. Returns the new revision, RUNNING."""
    from rca import problems

    with _transaction(db_path) as connection:
        repeated = _by_request_key(connection, request_key)
        if repeated is not None:
            return repeated, False
        rca = _read_rca(connection, rca_id)
        if rca.status not in ("REQUEST_MORE_DETAILS", "FAILED"):
            raise TransitionError(f"{rca_id} is {rca.status}: a new revision starts only after the expert asked for "
                                  "more details, or after a failed run.")
        previous = _read_revision(connection, rca.latest_revision_id)
        problem = storage.get_problem(db_path, rca.problem_id)
        revision = _new_revision(connection, rca, rca.revisions + 1, previous.revision_id, by,
                                 guidance if guidance is not None else previous.guidance, problem, request_key)
        reason = (f"Revision {revision.revision} started: the expert asked for more details."
                  if rca.status == "REQUEST_MORE_DETAILS" else f"Revision {revision.revision} started after a failed run.")
        _set_status(connection, rca_id, rca.status, "DRAFT", by, reason, revision.revision_id)
        problems.rca_event(connection, rca.problem_id, by, rca_id, rca.status, "DRAFT", reason)
    return revision, True


def complete_revision(record: RCARecord, outcome: Literal["DRAFT", "ESCALATED_MANUAL", "FAILED"],
                      reason: str | None = None, db_path: Path = DB_PATH) -> RCARecord:
    """Save the result of a run on its RUNNING revision, once. outcome: DRAFT (a draft to send to the
    expert), ESCALATED_MANUAL (the guardrail refused the draft in every attempt: the problem goes to manual
    review) or FAILED (a technical error, reason says which). Saving the same result again does nothing,
    so a technical retry of the save never makes a second revision. Returns the revision as read."""
    from rca import problems

    with _transaction(db_path) as connection:
        row = connection.execute("SELECT run_status, payload FROM rca_revisions WHERE revision_id = ?",
                                 [record.revision_id]).fetchone()
        if row is None:
            raise RCANotFound(f"Revision '{record.revision_id}' was not found.")
        result = record.model_copy(update={
            "status": outcome, "run_status": "FAILED" if outcome == "FAILED" else "COMPLETED",
            "review": None, "final_root_cause": None, "review_rounds": 0, "current_step": None,
            "completed_at": record.completed_at or _now(),
        })
        if row[0] != "RUNNING":
            saved = RCARecord.model_validate_json(row[1])
            if saved.model_dump(exclude={"completed_at"}) == result.model_dump(exclude={"completed_at"}):
                return get_rca(record.revision_id, db_path=db_path)  # the same save again: nothing to do
            raise TransitionError(f"{record.revision_id} already ended ({row[0]}): a revision is never changed.")
        connection.execute("UPDATE rca_revisions SET run_status = ?, payload = ? WHERE revision_id = ?",
                           [result.run_status, result.model_dump_json(), record.revision_id])
        rca = _read_rca(connection, record.rca_id)
        if outcome != "DRAFT":  # the RCA changes first, then what it does to the problem
            _set_status(connection, rca.rca_id, rca.status, outcome, record.owner, reason, record.revision_id)
            problems.rca_event(connection, rca.problem_id, record.owner, rca.rca_id, rca.status, outcome, reason)
            if outcome == "ESCALATED_MANUAL":
                problems.change_status(connection, rca.problem_id, "Manual", record.owner, rca_id=rca.rca_id,
                                       reason=f"{rca.rca_id}: {reason or 'escalated to manual review.'}")
        else:
            _touch(connection, rca.rca_id)
    return get_rca(record.revision_id, db_path=db_path)


def record_step(revision_id_: str, step, db_path: Path = DB_PATH) -> None:
    """Add a finished step to a RUNNING revision, so the interface shows the run while it happens. A step
    is added only after it finished: nothing is shown as done before it ran. An ended revision is not touched."""
    with _transaction(db_path) as connection:
        row = connection.execute("SELECT run_status, payload FROM rca_revisions WHERE revision_id = ?",
                                 [revision_id_]).fetchone()
        if row is None or row[0] != "RUNNING":
            return
        record = RCARecord.model_validate_json(row[1])
        record = record.model_copy(update={"trace": [*record.trace, step]})
        connection.execute("UPDATE rca_revisions SET payload = ? WHERE revision_id = ?",
                           [record.model_dump_json(), revision_id_])
        _touch(connection, record.rca_id)


def record_current_step(revision_id_: str, name: str, db_path: Path = DB_PATH) -> None:
    """The node of the graph that started now, on a RUNNING revision: the interface shows it as running
    because LangGraph says so, not because the step before it ended."""
    with _transaction(db_path) as connection:
        row = connection.execute("SELECT run_status, payload FROM rca_revisions WHERE revision_id = ?",
                                 [revision_id_]).fetchone()
        if row is None or row[0] != "RUNNING":
            return
        record = RCARecord.model_validate_json(row[1]).model_copy(update={"current_step": name})
        connection.execute("UPDATE rca_revisions SET payload = ? WHERE revision_id = ?",
                           [record.model_dump_json(), revision_id_])


def running_revisions(db_path: Path = DB_PATH) -> list[str]:
    with closing(_connect(db_path)) as connection:
        return [row[0] for row in connection.execute(
            "SELECT revision_id FROM rca_revisions WHERE run_status = 'RUNNING' ORDER BY created_at")]


def recover_interrupted(db_path: Path = DB_PATH) -> list[str]:
    """At the start of the application: a revision still RUNNING was stopped with the application (a restart,
    a crash), since no run survives it. Each one is saved FAILED with the reason, so it can be run again
    instead of staying "in progress" forever. Returns the revisions it ended."""
    ended = []
    for revision in running_revisions(db_path):
        fail_revision(revision, "Interrupted: the application stopped while this run was in progress. Run it again.",
                      db_path=db_path)
        ended.append(revision)
    return ended


def fail_revision(revision_id_: str, error: str, db_path: Path = DB_PATH) -> RCARecord | None:
    """Mark a RUNNING revision as FAILED after a technical error, with the error. A revision that already
    ended is left as it is. Returns the revision as read, or None when there is no such revision."""
    current = get_rca(revision_id_, db_path=db_path)
    if current is None:
        return None
    if current.run_status != "RUNNING":
        return current
    from rca.redaction import redact

    failed = current.model_copy(update={"error": redact(error)[:2000]})
    return complete_revision(failed, "FAILED", reason=f"Technical error: {error[:300]}", db_path=db_path)


def submit_for_review(rca_id: str, by: str, db_path: Path = DB_PATH) -> RCARecord:
    """Send the draft of the latest revision to the Technical Expert (AWAITING_TECHNICAL_REVIEW)."""
    from rca import problems

    with _transaction(db_path) as connection:
        rca = _read_rca(connection, rca_id)
        if rca.status != "DRAFT":
            raise TransitionError(f"{rca_id} is {rca.status}: only a draft is sent to the Technical Expert.")
        latest = _read_revision(connection, rca.latest_revision_id)
        if latest.run_status != "COMPLETED":
            raise TransitionError(f"{latest.revision_id} is still {latest.run_status.lower()}: wait for its draft.")
        if not latest.hypotheses:
            raise RCAError(f"{latest.revision_id} has no hypothesis to review.")
        _set_status(connection, rca_id, "DRAFT", "AWAITING_TECHNICAL_REVIEW", by, "Sent to the Technical Expert.",
                    latest.revision_id, sent_to_expert=True)
        problems.rca_event(connection, rca.problem_id, by, rca_id, "DRAFT", "AWAITING_TECHNICAL_REVIEW",
                           f"Revision {latest.revision} sent to the Technical Expert.")
    return get_rca(rca_id, db_path=db_path)


def apply_review(
    rca_id: str,
    reviewer: str,
    decision: str,
    comment: str,
    hypothesis_id: str | None = None,
    db_path: Path = DB_PATH,
    requested_checks: list[str] | None = None,
    guidance: InvestigationGuidance | None = None,
) -> RCARecord:
    """The decision of the Technical Expert on the latest revision of an RCA waiting for it.

    APPROVE needs the id of a hypothesis of the revision: the RCA is VALIDATED and closes its problem.
    REJECT needs a comment: the RCA is REJECTED, and the problem is open again, or goes to manual review
    at its MAX_REJECTED_CASES-th rejected RCA. REQUEST_MORE_DETAILS needs a comment, may list checks and
    wider searches (guidance), and is the input of the next revision; at the MAX_REVISIONS-th decision the
    RCA is ESCALATED_MANUAL instead and the problem goes to manual review. The revision itself is not changed.
    """
    from rca import problems

    text = (comment or "").strip()
    if decision not in ("APPROVE", "REJECT", "REQUEST_MORE_DETAILS"):
        raise RCAError(f"Unknown decision '{decision}'.")
    if decision != "APPROVE" and not text:
        raise RCAError("Explain the decision: the comment is required to reject or to ask for more details.")
    with _transaction(db_path) as connection:
        rca = _read_rca(connection, rca_id)
        if rca.status != "AWAITING_TECHNICAL_REVIEW":
            raise TransitionError(f"{rca_id} is {rca.status}: the expert decides only on an RCA waiting for review.")
        latest = _read_revision(connection, rca.latest_revision_id)
        now = _now()
        review = ReviewDecision(reviewer=reviewer, decision=decision, comment=text, decided_at=now,
                                hypothesis_id=hypothesis_id if decision == "APPROVE" else None,
                                requested_checks=[item.strip() for item in requested_checks or [] if item.strip()]
                                if decision == "REQUEST_MORE_DETAILS" else [],
                                guidance=guidance if decision == "REQUEST_MORE_DETAILS" else None)
        rounds = rca.review_rounds + 1
        problem: tuple | None = None  # what the decision does to the problem: (status, reason, closing fields)
        if decision == "APPROVE":
            hypothesis = next((item for item in latest.hypotheses if item.hypothesis_id == hypothesis_id), None)
            if hypothesis is None:
                raise RCAError(f"Hypothesis '{hypothesis_id}' was not found on {latest.revision_id}.")
            status = "VALIDATED"
            problem = ("Closed", f"Root cause validated in {rca_id}: {hypothesis.candidate_root_cause}",
                       {"closed_at": now, "close_reason": f"Root cause validated in {rca_id}."})
        elif decision == "REJECT":
            status = "REJECTED"
            rejected = 1 + sum(1 for item in list_summaries(problem_id=rca.problem_id, db_path=db_path)
                               if item.status == "REJECTED" and item.rca_id != rca_id)
            problem = (("Manual", f"{problems.MAX_REJECTED_CASES} RCAs were rejected, the last one {rca_id}.", {})
                       if rejected >= problems.MAX_REJECTED_CASES else ("Open", f"{rca_id} was rejected.", {}))
        elif rounds >= MAX_REVISIONS:
            status = "ESCALATED_MANUAL"
            problem = ("Manual", f"{rca_id}: the expert asked for more details at decision {rounds} of "
                                 f"{MAX_REVISIONS}, the last one.", {})
        else:
            status = "REQUEST_MORE_DETAILS"
        _set_status(connection, rca_id, rca.status, status, reviewer, text or None, latest.revision_id,
                    decision=review, review_rounds=rounds)
        problems.rca_event(connection, rca.problem_id, reviewer, rca_id, rca.status, status, text or None)
        if problem is not None:
            problems.change_status(connection, rca.problem_id, problem[0], reviewer, rca_id=rca_id, reason=problem[1],
                                   **problem[2])
    return get_rca(rca_id, db_path=db_path)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


def get_summary(rca_id: str, db_path: Path = DB_PATH) -> RCA | None:
    with closing(_connect(db_path)) as connection:
        row = connection.execute("SELECT payload FROM rcas WHERE rca_id = ?", [rca_id]).fetchone()
    return RCA.model_validate_json(row[0]) if row else None


def list_summaries(status: RCAStatus | None = None, problem_id: str | None = None,
                   db_path: Path = DB_PATH) -> list[RCA]:
    """The RCAs, the most recently created first."""
    sql, params = "SELECT payload FROM rcas WHERE 1 = 1", []
    if status:
        sql, params = sql + " AND status = ?", [*params, status]
    if problem_id:
        sql, params = sql + " AND problem_id = ?", [*params, problem_id]
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(sql + " ORDER BY created_at DESC, rca_id DESC", params).fetchall()
    return [RCA.model_validate_json(row[0]) for row in rows]


def get_rca(rca_or_revision_id: str, db_path: Path = DB_PATH) -> RCARecord | None:
    """A revision, by its id (RCA-2026-00001-R2), or the latest revision of an RCA (RCA-2026-00001)."""
    with closing(_connect(db_path)) as connection:
        if "-R" in rca_or_revision_id[9:]:
            row = connection.execute("SELECT payload FROM rca_revisions WHERE revision_id = ?",
                                     [rca_or_revision_id]).fetchone()
        else:
            row = connection.execute("SELECT payload FROM rca_revisions WHERE rca_id = ? ORDER BY number DESC LIMIT 1",
                                     [rca_or_revision_id]).fetchone()
        if row is None:
            return None
        return _complete(connection, RCARecord.model_validate_json(row[0]))


def list_rcas(status: RCAStatus | None = None, db_path: Path = DB_PATH, problem_id: str | None = None,
              sent_to_expert: bool | None = None) -> list[RCARecord]:
    """The latest revision of every RCA, filtered by the status of the RCA, the most recent RCA first."""
    summaries = [item for item in list_summaries(status, problem_id, db_path)
                 if sent_to_expert is None or item.sent_to_expert == sent_to_expert]
    return [record for record in (get_rca(item.rca_id, db_path=db_path) for item in summaries) if record]


def list_revisions(rca_id: str, db_path: Path = DB_PATH) -> list[RCARecord]:
    """Every revision of an RCA, the first one first."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute("SELECT payload FROM rca_revisions WHERE rca_id = ? ORDER BY number",
                                  [rca_id]).fetchall()
        return [_complete(connection, RCARecord.model_validate_json(row[0])) for row in rows]


def list_cases(db_path: Path = DB_PATH, sent_to_expert: bool | None = None) -> list[list[RCARecord]]:
    """Every RCA as the list of its revisions, the most recent RCA first."""
    return [list_revisions(item.rca_id, db_path=db_path) for item in list_summaries(db_path=db_path)
            if sent_to_expert is None or item.sent_to_expert == sent_to_expert]


def status_history(rca_id: str, db_path: Path = DB_PATH) -> list[RCAStatusChange]:
    """Every change of the status of an RCA, the oldest first."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT rca_id, revision_id, from_status, to_status, by_user, at, comment, decision, details "
            "FROM rca_status_history WHERE rca_id = ? ORDER BY change_id", [rca_id]).fetchall()
    return [RCAStatusChange(rca_id=row[0], revision_id=row[1], from_status=row[2], to_status=row[3], by=row[4],
                            at=row[5], comment=row[6], decision=json.loads(row[7]) if row[7] else None,
                            details=json.loads(row[8]) if row[8] else {}) for row in rows]


def expert_request(review: ReviewDecision) -> str:
    """The request of the expert as the next revision reads it: the comment and the checks asked for."""
    checks = [check.strip() for check in review.requested_checks if check.strip()]
    lines = [review.comment.strip(), *(f"- {check}" for check in checks if check != review.comment.strip())]
    return "\n".join(line for line in lines if line)


def open_request(rca_id: str, db_path: Path = DB_PATH) -> ReviewDecision | None:
    """The request for more details the next revision of the RCA must answer: the latest decision of the
    expert, when it asked for more details. None for a first revision, or after any other decision."""
    decisions = [item.decision for item in status_history(rca_id, db_path) if item.decision is not None]
    return decisions[-1] if decisions and decisions[-1].decision == "REQUEST_MORE_DETAILS" else None


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
            raise TransitionError(f"The change conflicts with a change made at the same time: {exc}.") from exc
        except BaseException:
            connection.rollback()
            raise


def _next_rca_id(connection: sqlite3.Connection, year: int) -> str:
    """The next free id of the year, under the write lock. The ids of the RCAs saved before E3 count too."""
    numbers = [0]
    for table in ("rcas", "rca_records"):
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", [table]).fetchone()
        if exists:
            row = connection.execute(f"SELECT MAX(CAST(substr(rca_id, 10, 5) AS INTEGER)) FROM {table} "
                                     "WHERE rca_id LIKE ?", [f"RCA-{year}-%"]).fetchone()
            numbers.append(row[0] or 0)
    return f"RCA-{year}-{max(numbers) + 1:05d}"


def _read_rca(connection: sqlite3.Connection, rca_id: str) -> RCA:
    row = connection.execute("SELECT payload FROM rcas WHERE rca_id = ?", [rca_id]).fetchone()
    if row is None:
        raise RCANotFound(f"RCA '{rca_id}' was not found.")
    return RCA.model_validate_json(row[0])


def _read_revision(connection: sqlite3.Connection, revision: str | None) -> RCARecord:
    row = connection.execute("SELECT payload FROM rca_revisions WHERE revision_id = ?", [revision]).fetchone()
    if row is None:
        raise RCANotFound(f"Revision '{revision}' was not found.")
    return RCARecord.model_validate_json(row[0])


def _write_rca(connection: sqlite3.Connection, rca: RCA) -> None:
    connection.execute("UPDATE rcas SET status = ?, updated_at = ?, payload = ? WHERE rca_id = ?",
                       [rca.status, rca.updated_at.isoformat(), rca.model_dump_json(), rca.rca_id])


def _touch(connection: sqlite3.Connection, rca_id: str) -> None:
    _write_rca(connection, _read_rca(connection, rca_id).model_copy(update={"updated_at": _now()}))


def _by_request_key(connection: sqlite3.Connection, request_key: str | None) -> RCARecord | None:
    """The revision a request with this key already created, as read."""
    if not request_key:
        return None
    row = connection.execute("SELECT payload FROM rca_revisions WHERE json_extract(payload, '$.request_key') = ?",
                             [request_key]).fetchone()
    return _complete(connection, RCARecord.model_validate_json(row[0])) if row else None


def _new_revision(connection: sqlite3.Connection, rca: RCA, number: int, previous: str | None, by: str,
                  guidance: InvestigationGuidance | None, problem, request_key: str | None = None) -> RCARecord:
    reference = problem.incidents[-1]  # the incidents of a problem are read in the order they happened
    now = _now()
    revision = RCARecord(rca_id=rca.rca_id, revision=number, previous_revision_id=previous, run_status="RUNNING",
                         incident_id=reference.incident_id, status="DRAFT", owner=by, created_at=now,
                         problem_id=rca.problem_id, guidance=guidance, request_key=request_key)
    connection.execute("INSERT INTO rca_revisions VALUES (?, ?, ?, ?, ?, ?)",
                       [revision.revision_id, rca.rca_id, number, "RUNNING", now.isoformat(), revision.model_dump_json()])
    _write_rca(connection, rca.model_copy(update={"revisions": number, "latest_revision_id": revision.revision_id,
                                                  "updated_at": now}))
    return revision


def _set_status(connection: sqlite3.Connection, rca_id: str, current: RCAStatus, new: RCAStatus, by: str,
                comment: str | None, revision: str | None, decision: ReviewDecision | None = None, **fields) -> None:
    """Change the status of an RCA, if the transition is allowed, and keep the change in its history."""
    if new not in TRANSITIONS[current]:
        raise TransitionError(f"{rca_id} cannot go from {current} to {new}.")
    rca = _read_rca(connection, rca_id)
    _write_rca(connection, rca.model_copy(update={"status": new, "updated_at": _now(), **fields}))
    _history(connection, rca_id, revision, current, new, by, comment, decision)


def _history(connection: sqlite3.Connection, rca_id: str, revision: str | None, current: str | None, new: str,
             by: str, comment: str | None, decision: ReviewDecision | None = None, at: datetime | None = None,
             details: dict | None = None) -> None:
    connection.execute(
        "INSERT INTO rca_status_history (rca_id, revision_id, from_status, to_status, by_user, at, comment, decision, "
        "details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [rca_id, revision, current, new, by, (at or _now()).isoformat(), comment,
         decision.model_dump_json() if decision else None, json.dumps(details) if details else None],
    )


def _complete(connection: sqlite3.Connection, record: RCARecord) -> RCARecord:
    """The revision as the interface reads it: the status of the RCA on its latest revision, the status
    the decision of the expert gave to an older one, and the decision with the validated root cause."""
    rca = _read_rca(connection, record.rca_id)
    row = connection.execute(
        "SELECT to_status, decision FROM rca_status_history WHERE revision_id = ? AND decision IS NOT NULL "
        "ORDER BY change_id DESC LIMIT 1", [record.revision_id]).fetchone()
    review = ReviewDecision.model_validate_json(row[1]) if row else None
    if record.revision_id == rca.latest_revision_id:
        status = rca.status
    elif row:
        status = row[0]
    else:
        status = "FAILED" if record.run_status == "FAILED" else record.status
    final = None
    if status == "VALIDATED" and review is not None and review.decision == "APPROVE":
        final = next((item.candidate_root_cause for item in record.hypotheses
                      if item.hypothesis_id == review.hypothesis_id), None)
    return record.model_copy(update={"status": status, "review": review, "final_root_cause": final,
                                     "review_rounds": rca.review_rounds})
