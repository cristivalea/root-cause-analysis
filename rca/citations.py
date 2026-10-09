"""Where does each expected citation get lost? (audit_rca_project.md, L.1)

For every story of the answer key, every expected citation is followed through the stages of
one investigation:

    in the sources  ->  in the evidence ledger  ->  cited by the main hypothesis

The result says, for each citation, the last stage it reached. When a log line or a change
did not reach the ledger, the plan of the investigation tells why when it can: the record
belongs to another service, or it is outside the time window.

The module only reads. Scripts print and write the results (scripts/trace_citations.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from rca.models import RCARecord

# Stages, from the furthest to the earliest.
CITED_BY_MAIN = "CITED by the main hypothesis"
CITED_BY_OTHER = "cited only by another hypothesis"
NOT_CITED = "in the ledger, NOT CITED"
NOT_IN_LEDGER = "NOT IN THE LEDGER"


@dataclass
class CitationTrace:
    citation: str
    stage: str
    evidence_id: str | None = None
    cited_by: list[str] = field(default_factory=list)
    reason: str | None = None  # why it did not reach the ledger, when the plan can tell


@dataclass
class StoryTrace:
    story_id: str
    rca_id: str
    incident_id: str
    citations: list[CitationTrace]
    ledger_size: int
    relevant_in_ledger: int  # evidence that the answer key names anywhere (citations, 5 whys, fishbone, timeline)
    red_herrings_cited_by_main: list[str]

    def count(self, *stages: str) -> int:
        return sum(1 for item in self.citations if item.stage in stages)

    @property
    def preserved(self) -> int:
        return len(self.citations) - self.count(NOT_IN_LEDGER)

    @property
    def cited_by_main(self) -> int:
        return self.count(CITED_BY_MAIN)


def relevant_citations(story: dict) -> set[str]:
    """Every record the answer key names for a story, not only the expected citations."""
    names = set(story["expected_citations"])
    names |= {item for step in story["five_whys"] for item in step["evidence"]}
    names |= {item for factors in story["fishbone"].values() for factor in factors for item in factor["evidence"]}
    names |= {item["citation"] for item in story["timeline"]}
    return names


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _why_missing(citation: str, record: RCARecord, logs: dict[str, dict], changes: dict[str, dict]) -> str | None:
    """For a log line or a change that is not in the ledger, what in the plan kept it out."""
    plan, context = record.plan, record.context
    source = logs.get(citation) or changes.get(citation)
    if plan is None or source is None:
        return None
    at = _parse(source.get("timestamp") or source["implemented_at"])
    # an investigation with a context searched its own windows; an older one, the window of its plan
    own = context.services if context else [plan.service]
    related = context.related_services if context else plan.related_services
    services = own if citation in logs else [*own, *related]
    if context is None:
        windows = [(plan.window_start, plan.window_end)]
    elif citation in logs:
        windows = [(window.start, window.end) for window in context.log_windows]
    else:
        windows = [(context.change_window.start, context.change_window.end)]
    if source["service"] not in services:
        return f"belongs to {source['service']}, the investigation searched {', '.join(services)}"
    if not any(start <= at <= end for start, end in windows):
        shown = "; ".join(f"{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}" for start, end in windows)
        return f"at {at:%Y-%m-%d %H:%M}, outside the window(s) {shown}"
    if citation in logs:
        if source["level"] not in ("ERROR", "WARN"):
            return f"an {source['level']} line, and the log lookup reads only ERROR and WARN"
        return "in the window, but not the first line of its log group (only the first line is cited)"
    return None


def trace_story(story: dict, record: RCARecord, logs: dict[str, dict], changes: dict[str, dict]) -> StoryTrace:
    # a log line that is not the first of its group is still in the ledger, through the group
    by_citation = {related: item for item in record.evidence for related in item.related_ids}
    by_citation |= {item.citation: item for item in record.evidence}
    main = record.hypotheses[0] if record.hypotheses else None
    citations = []
    for citation in story["expected_citations"]:
        evidence = by_citation.get(citation)
        if evidence is None:
            citations.append(CitationTrace(citation, NOT_IN_LEDGER, reason=_why_missing(citation, record, logs, changes)))
            continue
        cited_by = [item.hypothesis_id for item in record.hypotheses if evidence.evidence_id in item.supporting_evidence]
        if main is not None and main.hypothesis_id in cited_by:
            stage = CITED_BY_MAIN
        else:
            stage = CITED_BY_OTHER if cited_by else NOT_CITED
        citations.append(CitationTrace(citation, stage, evidence.evidence_id, cited_by))

    relevant = relevant_citations(story)
    main_cited = {cited for item in record.evidence if main and item.evidence_id in main.supporting_evidence
                  for cited in (item.citation, *item.related_ids)}
    return StoryTrace(
        story_id=story["story_id"],
        rca_id=record.rca_id,
        incident_id=record.incident_id,
        citations=citations,
        ledger_size=len(record.evidence),
        relevant_in_ledger=sum(1 for item in record.evidence if relevant & {item.citation, *item.related_ids}),
        red_herrings_cited_by_main=[item["citation"] for item in story["red_herrings"] if item["citation"] in main_cited],
    )


def record_for_story(story: dict, records: list[RCARecord]) -> RCARecord | None:
    """The investigation of a story: started from its target incident, or from any incident of its problem."""
    incidents = set(story.get("problem_incidents") or []) | {story["target_incident"]}
    return next((record for record in records if record.incident_id in incidents), None)
