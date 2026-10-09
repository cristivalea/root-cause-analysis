"""Evidence Ledger: every fact found during the investigation gets an evidence id.

The RCA Reasoning Agent receives only this list, and its hypotheses may cite only ids that
exist here. The guardrail checks the citations with `has`.

The functions at the end turn the tool results into evidence. The Reasoning Agent sees only
the descriptions they write, so a description must carry what the agent needs to judge the
order of events: the time, and how long before the detection it happened.
"""

from datetime import datetime

from rca.models import Change, Evidence, EvidenceType, LogGroup, ServiceDependencies


class EvidenceLedger:
    """A numbered list of evidence for one investigation: EV-001, EV-002, ..."""

    def __init__(self, items: list[Evidence] | None = None) -> None:
        """Start empty, or continue a ledger from the evidence found in an earlier step."""
        self._items: list[Evidence] = list(items or [])

    def add(
        self,
        evidence_type: EvidenceType,
        source: str,
        description: str,
        citation: str,
        timestamp: datetime | None = None,
        related_ids: list[str] | None = None,
        service: str | None = None,
    ) -> Evidence:
        """Record a fact and return it with its id.

        The same original record (same type and citation) is recorded only once, so it cannot
        count twice in the confidence calculation. Adding it again returns the existing evidence.
        """
        for item in self._items:
            if item.type == evidence_type and item.citation == citation:
                return item

        evidence = Evidence(
            evidence_id=f"EV-{len(self._items) + 1:03d}",
            type=evidence_type,
            source=source,
            description=description,
            citation=citation,
            timestamp=timestamp,
            related_ids=[item for item in related_ids or [] if item != citation],
            service=service,
        )
        self._items.append(evidence)
        return evidence

    def items(self) -> list[Evidence]:
        """All evidence, in the order it was found."""
        return list(self._items)

    def get(self, evidence_id: str) -> Evidence | None:
        return next((item for item in self._items if item.evidence_id == evidence_id), None)

    def has(self, evidence_id: str) -> bool:
        return self.get(evidence_id) is not None

    def __len__(self) -> int:
        return len(self._items)


def relative_to_detection(moment: datetime, detected_at: datetime, of: str = "detection") -> str:
    """For example "34 minutes before detection", "5 hours after detection", "4 days before detection".
    `of` names what the time is compared with, for example "the detection of INC-2026-00482"."""
    minutes = round((detected_at - moment).total_seconds() / 60)
    side = "before" if minutes >= 0 else "after"
    minutes = abs(minutes)
    if minutes < 120:
        amount = f"{minutes} minutes"
    elif minutes < 48 * 60:
        amount = f"{round(minutes / 60)} hours"
    else:
        amount = f"{round(minutes / (24 * 60))} days"
    return f"{amount} {side} {of}"


def add_log_groups(ledger: EvidenceLedger, groups: list[LogGroup], detected_at: datetime, of: str = "detection",
                   dependency: bool = False) -> None:
    """One evidence per log group, cited by its first line; the other lines are kept as related ids.
    dependency: the lines come from a service the problem depends on, which the description says."""
    for group in groups:
        first = group.examples[0]
        where = f"On {group.service}, a dependency: " if dependency else ""
        ledger.add(
            "LOG",
            ", ".join(group.hosts),
            f"{where}{group.count} {group.level} log line(s) of type {group.error_type} between "
            f"{group.first_seen:%Y-%m-%d %H:%M} and {group.last_seen:%H:%M} UTC, the first "
            f"{relative_to_detection(group.first_seen, detected_at, of)}. Example: \"{first.message}\"",
            first.log_id,
            group.first_seen,
            group.log_ids,
            group.service,
        )


def add_changes(ledger: EvidenceLedger, changes: list[Change], detected_at: datetime, of: str = "detection") -> None:
    """One evidence per change."""
    for change in changes:
        ledger.add(
            "CHANGE",
            change.change_id,
            f"{change.title} on {change.ci_id}: {change.description} Implemented at "
            f"{change.implemented_at:%Y-%m-%d %H:%M} UTC, {relative_to_detection(change.implemented_at, detected_at, of)}.",
            change.change_id,
            change.implemented_at,
        )


def add_dependencies(ledger: EvidenceLedger, dependencies: ServiceDependencies) -> None:
    """One evidence per component depended on, cited by its CMDB id, naming every component of the
    service that depends on it. One evidence per relationship would lose all but the first when two
    components depend on the same one, because the ledger keeps one evidence per citation."""
    by_target: dict[str, list] = {}
    for dependency in dependencies.dependencies:
        by_target.setdefault(dependency.depends_on.ci_id, []).append(dependency)
    for group in by_target.values():
        target = group[0].depends_on
        sources = " and ".join(f"{item.component.name} ({item.component.ci_id}) {item.relationship_type}" for item in group)
        ledger.add("CMDB", "CMDB", f"{sources} {target.name} ({target.ci_id}, {target.type}).", target.ci_id)
