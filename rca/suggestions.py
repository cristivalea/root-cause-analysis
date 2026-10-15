"""Grouping suggestions for the incidents in no problem (audit_rca_project.md, P.3).

For an incident in no problem the code finds the alike incidents and the closest one decides:
- it is in an open problem: propose that problem;
- it is in a closed problem: propose it as a possible recurrence (the fix may not have worked);
- it is in no problem: propose a new problem with the alike incidents in no problem.
The Proposed Problem Records page lists them as proposals (proposals, below).

Nothing is decided by a model and nothing is applied by itself: the Problem Manager accepts a
suggestion (rca/problems.py), rejects it (it is not proposed again) or marks the incident as needing
no problem. Every suggestion says why, with the signals below.

When two incidents count as alike, all computed by code:
- the same service, always (past records of other services are never evidence in this project);
- their texts are close: the cosine similarity of their embeddings, already stored in ChromaDB, is
  at least TEXT_ALIKE, or at least TEXT_ALIKE_SAME_CI when they are on the same CMDB item.
The thresholds were measured on the mock data (data/evaluation/grouping_truth.json): at these values
the first suggestion was right for 443 of the 445 incidents in no problem; see
tests/test_suggestions.py. The error types in the logs and the distance in time are shown as reasons,
not used to decide.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_left, bisect_right
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from rca import rag, storage
from rca.config import DB_PATH
from rca.models import Incident

TEXT_ALIKE = 0.88
TEXT_ALIKE_SAME_CI = 0.85
MIN_GROUP = 2  # alike incidents of the Proposed Problem Records page: two already make a recurrence
LOG_LEVELS = ["ERROR", "WARN"]


@dataclass
class Suggestion:
    incident_id: str
    kind: Literal["open_problem", "closed_problem", "busy_problem", "new_problem"]
    # the problem to attach to (open), the closed problem that may have come back, or a problem that takes no
    # incident now (busy: in investigation, or in manual review)
    problem_id: str | None
    incident_ids: list[str]  # the alike incidents behind the suggestion, the closest first
    similarity: float  # of the closest one
    reasons: list[str] = field(default_factory=list)


def load_embeddings() -> dict[str, list[float]]:
    """The embedding of every incident, as stored by scripts/ingest_chroma.py."""
    import chromadb

    collection = chromadb.PersistentClient(path=str(rag.ROOT / "chroma_db")).get_collection("historical_incidents")
    result = collection.get(include=["embeddings"])
    return {incident_id: list(vector) for incident_id, vector in zip(result["ids"], result["embeddings"])}


def suggest_all(db_path: Path = DB_PATH, embeddings: dict[str, list[float]] | None = None) -> dict[str, Suggestion | None]:
    """A suggestion, or None, for every incident in no problem that was not marked as needing none."""
    world = _World(db_path, embeddings if embeddings is not None else load_embeddings())
    return {incident_id: world.suggest(incident_id) for incident_id in world.unassigned}


def suggest(incident_id: str, db_path: Path = DB_PATH, embeddings: dict[str, list[float]] | None = None) -> Suggestion | None:
    world = _World(db_path, embeddings if embeddings is not None else load_embeddings())
    return world.suggest(incident_id)


@dataclass
class Candidate:
    """An incident that may be added to a problem, with how close it is to the problem."""

    incident_id: str
    title: str
    service: str
    severity: str
    detected_at: str
    # cosine similarity (0 to 1) between the text of the incident and the closest incident of the problem,
    # from their embeddings. It measures how alike the texts are; it is not a probability.
    similarity: float | None  # None: the incident has no embedding yet (scripts/ingest_chroma.py)
    closest_incident_id: str | None
    alike: bool  # the same rule as the suggestions: same service and similarity above the thresholds


def candidates_for_problem(problem_id: str, db_path: Path = DB_PATH, embeddings: dict[str, list[float]] | None = None,
                           limit: int = 50) -> list[Candidate]:
    """The incidents that may be added to a problem (every incident in no problem), the
    most alike first: those that meet the rule of the suggestions, then by similarity."""
    world = _World(db_path, embeddings if embeddings is not None else load_embeddings())
    members = [incident_id for incident_id, owner in world.owner.items() if owner == problem_id]
    found = []
    for incident_id in world.unassigned:
        incident, vector = world.incidents[incident_id], world.vectors.get(incident_id)
        best: tuple[float, str] | None = None
        for member in members:
            other = world.vectors.get(member)
            if vector is not None and other is not None:
                similarity = float(vector @ other)
                if best is None or similarity > best[0]:
                    best = (similarity, member)
        alike = best is not None and incident.service == world.incidents[best[1]].service and (
            best[0] >= TEXT_ALIKE or (best[0] >= TEXT_ALIKE_SAME_CI and bool(incident.ci_id)
                                      and incident.ci_id == world.incidents[best[1]].ci_id))
        found.append(Candidate(incident_id, incident.title, incident.service, incident.severity,
                               incident.detected_at.isoformat(), round(best[0], 3) if best else None,
                               best[1] if best else None, alike))
    found.sort(key=lambda item: (not item.alike, -(item.similarity if item.similarity is not None else -1)))
    return found[:limit]


class _World:
    """Everything a suggestion needs, read once."""

    def __init__(self, db_path: Path, embeddings: dict[str, list[float]]) -> None:
        import numpy as np

        self.db_path = db_path
        self.incidents = {item.incident_id: item for item in storage.list_incidents(db_path)}
        with closing(sqlite3.connect(db_path)) as connection:
            storage.initialize_database(connection)
            self.owner = dict(connection.execute("SELECT incident_id, problem_id FROM problem_incidents").fetchall())
            self.status = dict(connection.execute("SELECT problem_id, status FROM problems").fetchall())
            self.rca_of = {problem_id: storage.get_problem(db_path, problem_id).rca_id for problem_id in self.status}
            self.rejected = {(row[0], row[1]) for row in connection.execute(
                "SELECT incident_id, target FROM rejected_suggestions")}
        self.unassigned = sorted(
            (item for item in self.incidents if item not in self.owner),
            key=lambda item: self.incidents[item].detected_at, reverse=True,
        )
        self._types: dict[str, set[str]] = {}
        self._log_index: dict[str, tuple[list[datetime], list[str | None]]] | None = None
        self.vectors = {key: np.array(value) / np.linalg.norm(value) for key, value in embeddings.items() if key in self.incidents}

    def alike(self, incident_id: str) -> list[tuple[str, float]]:
        """The incidents alike this one, the closest first."""
        incident, vector = self.incidents[incident_id], self.vectors.get(incident_id)
        if vector is None:
            return []
        found = []
        for other_id, other in self.incidents.items():
            if other_id == incident_id or other.service != incident.service:
                continue
            other_vector = self.vectors.get(other_id)
            if other_vector is None:
                continue
            similarity = float(vector @ other_vector)
            if similarity >= TEXT_ALIKE or (similarity >= TEXT_ALIKE_SAME_CI and other.ci_id and other.ci_id == incident.ci_id):
                found.append((other_id, similarity))
        return sorted(found, key=lambda item: -item[1])

    def suggest(self, incident_id: str) -> Suggestion | None:
        """The closest alike incident decides: its problem when it has one, else a new problem with the
        alike incidents in no problem. Preferring any problem over a closer incident was measured worse
        (403 of 445 right instead of 443): a weaker match in a problem then beat the real one."""
        alike = [(other_id, similarity) for other_id, similarity in self.alike(incident_id)
                 if (incident_id, self.owner.get(other_id) or other_id) not in self.rejected]
        if not alike:
            return None
        problem_id = self.owner.get(alike[0][0])
        if problem_id is None:
            partners = [(other_id, similarity) for other_id, similarity in alike if other_id not in self.owner]
            return self._suggestion(incident_id, "new_problem", None, partners)
        members = [(other_id, similarity) for other_id, similarity in alike if self.owner.get(other_id) == problem_id]
        status = self.status.get(problem_id)
        kind = "open_problem" if status in EDITABLE_PROBLEM else "closed_problem" if status == "Closed" else "busy_problem"
        return self._suggestion(incident_id, kind, problem_id, members)

    def _suggestion(self, incident_id: str, kind: str, problem_id: str | None, members: list[tuple[str, float]]) -> Suggestion:
        incident = self.incidents[incident_id]
        closest_id, similarity = members[0]
        closest = self.incidents[closest_id]
        reasons = [f"Same service: {incident.service}."]
        if incident.ci_id and incident.ci_id == closest.ci_id:
            reasons.append(f"Same CMDB item as {closest_id}: {incident.ci_id}.")
        reasons.append(f"Text similar to {closest_id} ({similarity:.2f}): \"{closest.title}\".")
        shared = self._error_types(incident) & self._error_types(closest)
        if shared:
            reasons.append(f"Same error types in the logs around both incidents: {', '.join(sorted(shared))}.")
        days = abs((incident.detected_at - closest.detected_at).days)
        reasons.append(f"{days} days from {closest_id}.")
        if len(members) > 1:
            reasons.append(f"{len(members) - 1} more alike incident(s): {', '.join(item for item, _ in members[1:4])}"
                           + ("..." if len(members) > 4 else "") + ".")
        if kind == "closed_problem":
            rca = self.rca_of.get(problem_id)
            reasons.append(f"{problem_id} is closed{f' by {rca}' if rca else ''}: the problem may have come back after the fix.")
        if kind == "busy_problem":
            reasons.append(f"{problem_id} is {self.status.get(problem_id, '').lower()}: it takes no incident now.")
        return Suggestion(incident_id, kind, problem_id, [item for item, _ in members], round(similarity, 3), reasons)

    def _error_types(self, incident: Incident) -> set[str]:
        """The error types logged on the service of the incident, from 2 hours before its detection to 1 hour
        after (edges included), as storage.get_logs would find them."""
        if incident.incident_id not in self._types:
            times, kinds = self._logs().get(incident.service, ([], []))
            start = bisect_left(times, incident.detected_at - timedelta(hours=2))
            end = bisect_right(times, incident.detected_at + timedelta(hours=1))
            self._types[incident.incident_id] = {kind for kind in kinds[start:end] if kind}
        return self._types[incident.incident_id]

    def _logs(self) -> dict[str, tuple[list[datetime], list[str | None]]]:
        """Every ERROR / WARN line, by service and in time order, read once: one query instead of one per
        incident (each of those scanned the whole log table)."""
        if self._log_index is None:
            with closing(sqlite3.connect(self.db_path)) as connection:
                rows = connection.execute(
                    f"SELECT service, timestamp, json_extract(payload, '$.error_type') FROM logs "
                    f"WHERE level IN ({', '.join('?' for _ in LOG_LEVELS)})", LOG_LEVELS).fetchall()
            by_service: dict[str, list[tuple[datetime, str | None]]] = {}
            for service, timestamp, kind in rows:
                by_service.setdefault(service, []).append((datetime.fromisoformat(timestamp), kind))
            self._log_index = {}
            for service, entries in by_service.items():
                entries.sort(key=lambda entry: entry[0])
                self._log_index[service] = ([entry[0] for entry in entries], [entry[1] for entry in entries])
        return self._log_index

    def evidence(self, incident_ids: list[str]) -> list[str]:
        """The facts behind a proposal, from the sources: the CMDB items, the error types logged around the
        detections, the severities and the dates. Shown with the reasons, never used to decide."""
        items = [self.incidents[item] for item in incident_ids if item in self.incidents]
        facts = []
        for ci_id, count in Counter(item.ci_id for item in items if item.ci_id).most_common(2):
            facts.append(f"CMDB item {ci_id}: {count} of {len(items)} incident(s).")
        types = Counter(kind for item in items for kind in self._error_types(item))
        if types:
            facts.append("Error types logged around the detections: "
                         + ", ".join(f"{kind} ({count})" for kind, count in  # ties in name order: the same text every time
                                     sorted(types.items(), key=lambda pair: (-pair[1], pair[0]))[:4]) + ".")
        severities = Counter(item.severity for item in items)
        facts.append("Severity: " + ", ".join(f"{count} {severity}" for severity, count in sorted(severities.items())) + ".")
        first, last = min(item.detected_at for item in items), max(item.detected_at for item in items)
        facts.append(f"Detected {first:%Y-%m-%d}" + (f" to {last:%Y-%m-%d}." if last.date() != first.date() else "."))
        return facts


# --------------------------------------------------------------------------------------
# Proposed Problem Records (final_project_steps.md, E6)
# --------------------------------------------------------------------------------------

SCORE_LABEL = "Text similarity (cosine, 0 to 1)"
SCORE_MEANING = ("How alike the texts of the incidents are, from their embeddings: 1 is the same wording. It ranks "
                 "the proposals; it is not a probability that they share a cause. A proposal is made only from "
                 f"{TEXT_ALIKE} (or {TEXT_ALIKE_SAME_CI} on the same CMDB item), and always on the same service.")
EDITABLE_PROBLEM = ("Open",)  # a problem that may still receive incidents (rca/problems.INCIDENTS_EDITABLE)


@dataclass
class Proposal:
    """One proposal of the Proposed Problem Records page. key is stable while its incidents (and its problem)
    stay the same, so a repeated accept is recognised and a rejected proposal is not shown again."""

    key: str
    kind: Literal["group", "attach", "single"]  # new problem from alike incidents / add to an open problem /
    #                                              new problem from one incident on its own (a major one first)
    incident_ids: list[str]
    problem_id: str | None  # the open problem to add to (attach)
    score: float | None  # see SCORE_LABEL and SCORE_MEANING; None for a single incident with nothing alike
    reasons: list[str] = field(default_factory=list)  # why it is proposed
    evidence: list[str] = field(default_factory=list)  # the facts behind it: CMDB item, log error types, dates
    recurrence_of: str | None = None  # a closed problem the incidents look like: the problem may have come back
    score_label: str = SCORE_LABEL
    score_meaning: str = SCORE_MEANING


def proposal_key(kind: str, incident_ids: list[str], problem_id: str | None = None) -> str:
    """PP- and 10 hex characters, from the kind, the problem and the incidents (in any order)."""
    import hashlib

    text = "|".join([kind, problem_id or "", *sorted(incident_ids)])
    return "PP-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def proposals(db_path: Path = DB_PATH, embeddings: dict[str, list[float]] | None = None) -> list[Proposal]:
    """The three kinds of proposals for the incidents in no problem, the strongest first in each kind:

    - attach: an incident whose closest alike incident is in an Open problem;
    - group: alike incidents in no problem, linked step by step (A like B, B like C): a new problem;
    - single: any other incident, a new problem with this incident only; the major ones (rca_required, or
      SEV-1) first.

    Every incident in no problem is in exactly one proposal, an incident removed from a problem included: an
    incident of a rejected group, or whose proposal to join a problem was rejected, comes back on its own. A
    single proposal cannot be rejected (problems.reject_proposal).

    An incident whose closest alike incident is in a closed problem is proposed in a new problem too (group or
    single), with the closed problem named as a possible recurrence: a closed problem is not reopened by a
    proposal. Proposals the Problem Manager rejected are not listed again (problems.reject_proposal).
    """
    world = _World(db_path, embeddings if embeddings is not None else load_embeddings())
    rejected = _rejected_keys(db_path)
    suggested = {incident_id: world.suggest(incident_id) for incident_id in world.unassigned}
    found: list[Proposal] = []

    attached = set()
    for incident_id, suggestion in suggested.items():
        if suggestion is None or suggestion.kind != "open_problem":
            continue
        attached.add(incident_id)
        found.append(Proposal(proposal_key("attach", [incident_id], suggestion.problem_id), "attach", [incident_id],
                              suggestion.problem_id, suggestion.similarity, suggestion.reasons,
                              world.evidence([incident_id, *suggestion.incident_ids[:1]])))

    remaining = [item for item in world.unassigned if item not in attached]
    parent = {item: item for item in remaining}

    def root(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    links: dict[str, float] = {}  # the strongest link of every incident to another incident of its group
    for incident_id in remaining:
        for other, similarity in world.alike(incident_id):
            if other in parent and (incident_id, other) not in world.rejected:
                parent[root(other)] = root(incident_id)
                links[incident_id] = max(links.get(incident_id, 0.0), similarity)
    groups: dict[str, list[str]] = {}
    for incident_id in remaining:
        groups.setdefault(root(incident_id), []).append(incident_id)

    for members in groups.values():
        members = sorted(members, key=lambda item: world.incidents[item].detected_at)
        closed = _closed_problem(members, suggested)
        if len(members) >= MIN_GROUP:
            score = round(min(links[item] for item in members), 3)  # the weakest link of the chain
            first, last = world.incidents[members[0]], world.incidents[members[-1]]
            reasons = [f"{len(members)} incidents in no problem, all on {first.service}, each one's text alike another's "
                       f"(weakest link {score:.2f})."]
            if closed:
                reasons.append(f"They look like the closed problem {closed}: the problem may have come back after its fix.")
            found.append(Proposal(proposal_key("group", members), "group", members, None, score, reasons,
                                  world.evidence(members), closed))
            continue
        found.append(_single(world, members[0], suggested))

    was_rejected = {incident_id: item for item in found if item.key in rejected for incident_id in item.incident_ids}
    found = [item for item in found if item.key not in rejected]
    covered = {incident_id for item in found for incident_id in item.incident_ids}
    found += [_single(world, incident_id, suggested, was_rejected.get(incident_id))
              for incident_id in world.unassigned if incident_id not in covered]
    order = {"group": 0, "attach": 1, "single": 2}
    return sorted(found, key=lambda item: (order[item.kind], not (item.kind == "single" and _major(world, item)),
                                           -(item.score or 0), -len(item.incident_ids), item.key))


def _major(world: _World, proposal: Proposal) -> bool:
    incident = world.incidents[proposal.incident_ids[0]]
    return bool(incident.rca_required or incident.severity == "SEV-1")


def _single(world: _World, incident_id: str, suggested: dict[str, Suggestion | None],
            rejected: Proposal | None = None) -> Proposal:
    """A new problem with this incident only: a major incident, one no other incident is alike, or one whose
    proposal the Problem Manager rejected (rejected)."""
    incident, suggestion = world.incidents[incident_id], suggested.get(incident_id)
    closed = _closed_problem([incident_id], suggested)
    if rejected is not None and rejected.kind == "group":
        others = [item for item in rejected.incident_ids if item != incident_id]
        reasons = [f"Its group with {', '.join(others[:4])}{'...' if len(others) > 4 else ''} was rejected. The "
                   "group is proposed again, with them, when another alike incident arrives."]
    elif rejected is not None:
        reasons = [f"Adding it to {rejected.problem_id} was rejected: that problem is not proposed for it again."]
    elif incident.rca_required or incident.severity == "SEV-1":
        reasons = [f"{incident.severity} incident that needs an analysis on its own"
                   + (f": {incident.rca_reason}" if incident.rca_reason else ".")]
    else:
        reasons = [f"{incident.severity} incident that is alike no other incident in no problem: a problem with this "
                   "incident only."]
    if closed:
        reasons.append(f"It looks like the closed problem {closed}: the problem may have come back after its fix.")
    elif suggestion is not None and suggestion.kind == "busy_problem":
        reasons.append(f"It looks like {suggestion.problem_id}, which takes no incident now "
                       f"({world.status.get(suggestion.problem_id, '').lower()}).")
    return Proposal(proposal_key("single", [incident_id]), "single", [incident_id], None,
                    suggestion.similarity if closed and suggestion else None, reasons,
                    world.evidence([incident_id]), closed)


def _closed_problem(members: list[str], suggested: dict[str, Suggestion | None]) -> str | None:
    """The closed problem the closest alike incident of a member belongs to, if any."""
    return next((item.problem_id for item in (suggested.get(member) for member in members)
                 if item is not None and item.kind == "closed_problem"), None)


def _rejected_keys(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        storage.initialize_database(connection)
        return {row[0] for row in connection.execute(
            "SELECT proposal_key FROM proposal_decisions WHERE decision = 'rejected'")}
