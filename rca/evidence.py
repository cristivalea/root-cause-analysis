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


def relative_to_detection(moment: datetime, detected_at: datetime) -> str:
    """For example "34 minutes before detection"."""
    minutes = round((detected_at - moment).total_seconds() / 60)
    return f"{minutes} minutes before detection" if minutes >= 0 else f"{-minutes} minutes after detection"


def add_log_groups(ledger: EvidenceLedger, groups: list[LogGroup], detected_at: datetime) -> None:
    """One evidence per log group, cited by its first line."""
    for group in groups:
        first = group.examples[0]
        ledger.add(
            "LOG",
            ", ".join(group.hosts),
            f"{group.count} {group.level} log line(s) of type {group.error_type} between "
            f"{group.first_seen:%H:%M} and {group.last_seen:%H:%M} UTC, the first "
            f"{relative_to_detection(group.first_seen, detected_at)}. Example: \"{first.message}\"",
            first.log_id,
            group.first_seen,
        )


def add_changes(ledger: EvidenceLedger, changes: list[Change], detected_at: datetime) -> None:
    """One evidence per change."""
    for change in changes:
        ledger.add(
            "CHANGE",
            change.change_id,
            f"{change.title} on {change.ci_id}: {change.description} Implemented at "
            f"{change.implemented_at:%H:%M} UTC, {relative_to_detection(change.implemented_at, detected_at)}.",
            change.change_id,
            change.implemented_at,
        )


def add_dependencies(ledger: EvidenceLedger, dependencies: ServiceDependencies) -> None:
    """One evidence per direct dependency, cited by the component depended on."""
    for dependency in dependencies.dependencies:
        ledger.add(
            "CMDB",
            "CMDB",
            f"{dependency.component.name} ({dependency.component.ci_id}) {dependency.relationship_type} "
            f"{dependency.depends_on.name} ({dependency.depends_on.ci_id}, {dependency.depends_on.type}).",
            dependency.depends_on.ci_id,
        )
