"""Evidence Ledger: every fact found during the investigation gets an evidence id.

The RCA Reasoning Agent receives only this list, and its hypotheses may cite only ids that
exist here. The guardrail checks the citations with `has`.
"""

from datetime import datetime

from rca.models import Evidence, EvidenceType


class EvidenceLedger:
    """A numbered list of evidence for one investigation: EV-001, EV-002, ..."""

    def __init__(self) -> None:
        self._items: list[Evidence] = []

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
