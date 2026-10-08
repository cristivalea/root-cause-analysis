"""Grouping suggestions for the incidents in no problem (audit_rca_project.md, P.3).

For an incident in no problem the code finds the alike incidents and the closest one decides:
- it is in an open problem: propose that problem;
- it is in a closed problem: propose it as a possible recurrence (the fix may not have worked);
- it is in no problem: propose a new problem with the alike incidents in no problem.
Groups of at least MIN_PROPOSED_PROBLEM alike incidents in no problem are also listed as proposed problems.

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
from contextlib import closing
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

from rca import rag, storage
from rca.config import DB_PATH
from rca.models import Incident

TEXT_ALIKE = 0.88
TEXT_ALIKE_SAME_CI = 0.85
MIN_PROPOSED_PROBLEM = 3  # incidents in no problem that look alike, before a new problem is proposed
LOG_LEVELS = ["ERROR", "WARN"]


@dataclass
class Suggestion:
    incident_id: str
    kind: Literal["open_problem", "closed_problem", "new_problem"]
    problem_id: str | None  # the problem to attach to, or the closed problem that may have come back
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


def proposed_problems(db_path: Path = DB_PATH, embeddings: dict[str, list[float]] | None = None) -> list[list[str]]:
    """Groups of at least MIN_PROPOSED_PROBLEM incidents in no problem that look alike, linked step by step
    (A like B, B like C), each group in time order, the largest first. Shown as proposed problems."""
    world = _World(db_path, embeddings if embeddings is not None else load_embeddings())
    parent = {incident_id: incident_id for incident_id in world.unassigned}

    def root(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for incident_id in world.unassigned:
        for other, _ in world.alike(incident_id):
            if other in parent:
                parent[root(other)] = root(incident_id)
    groups: dict[str, list[str]] = {}
    for incident_id in world.unassigned:
        groups.setdefault(root(incident_id), []).append(incident_id)
    found = [sorted(group, key=lambda item: world.incidents[item].detected_at)
             for group in groups.values() if len(group) >= MIN_PROPOSED_PROBLEM]
    return sorted(found, key=lambda group: (-len(group), group[0]))


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
            dismissed = {row[0] for row in connection.execute("SELECT incident_id FROM dismissed_incidents")}
            self.rejected = {(row[0], row[1]) for row in connection.execute(
                "SELECT incident_id, target FROM rejected_suggestions")}
        self.unassigned = sorted(
            (item for item in self.incidents if item not in self.owner and item not in dismissed),
            key=lambda item: self.incidents[item].detected_at, reverse=True,
        )
        self.dismissed = dismissed
        self.vectors = {key: np.array(value) / np.linalg.norm(value) for key, value in embeddings.items() if key in self.incidents}

    def alike(self, incident_id: str) -> list[tuple[str, float]]:
        """The incidents alike this one, the closest first."""
        incident, vector = self.incidents[incident_id], self.vectors.get(incident_id)
        if vector is None:
            return []
        found = []
        for other_id, other in self.incidents.items():
            if other_id == incident_id or other.service != incident.service or other_id in self.dismissed:
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
        kind = "open_problem" if self.status.get(problem_id) == "Open" else "closed_problem"
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
        return Suggestion(incident_id, kind, problem_id, [item for item, _ in members], round(similarity, 3), reasons)

    def _error_types(self, incident: Incident) -> set[str]:
        logs = storage.get_logs(self.db_path, incident.service, incident.detected_at - timedelta(hours=2),
                                incident.detected_at + timedelta(hours=1), LOG_LEVELS)
        return {item.error_type for item in logs if item.error_type}
