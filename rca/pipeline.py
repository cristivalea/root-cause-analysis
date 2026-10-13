"""The end-to-end investigation: one LangGraph graph, from the problem to the saved revision (E5).

The graph only routes. Every judgement is made by one of the three agents and every check by
ordinary code in the other modules; each node calls them and writes what it found into the
state. The nine nodes, in order:

    build_context (code) → investigation_planner (agent) ─┬─► gather_evidence (code) → build_timeline (code)
                                                          └─► save_revision            (no plan: FAILED)
    → historical_review (agent) → rca_reasoning_agent (agent) → guardrail (code) ─┬─► confidence (code) → save_revision (code)
                                        ▲                                        ├─► save_revision (refused 3 times)
                                        └────────────────────────────────────────┘   refused: ask again with the problems

- build_context: the revision of this run (rca/store.py) and the context of the problem (rca/context.py):
  its incidents and windows, its investigation guide, the notes and instructions of the Problem Manager,
  the request of the expert and what experts concluded about earlier RCAs of the problem.
- investigation_planner: the search queries, and extra searches checked by code before they run.
- gather_evidence: every tool, each call a ToolRun; every fact in the Evidence Ledger with a stable id,
  the time it happened and the time it was found. The similar past incidents are searched here too.
- build_timeline: the facts in time order, the first error marked.
- historical_review: past RCAs, past incidents and RCAs validated in the application, of the services of the
  problem only; for each one kept, what it shares with the problem, how it differs and what was done then.
- rca_reasoning_agent: the hypotheses, from the ledger, with a brief of what the investigation must answer.
- guardrail: the checks of rca/guardrails.py; a refused draft is asked again, at most 3 attempts in a run.
- confidence: HIGH / MEDIUM / LOW from rules on the cited evidence (rca/confidence.py), a heuristic.
- save_revision: the revision ends (store.complete_revision): a draft (DRAFT; the Problem Manager sends it
  to the expert), ESCALATED_MANUAL (the guardrail refused the draft in every attempt) or FAILED (no usable
  answer from the agents: a technical failure). A run stopped by an error is saved FAILED by
  run_investigation, with the error. The decision of the Technical Expert is outside the graph
  (store.apply_review).

`graph` is what LangGraph Studio opens (langgraph.json). `run_investigation` runs the same
graph from Python, for the command line (scripts/run_rca.py), the API and the scripts.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import chromadb
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace

from rca import rag, storage, store
from rca.agents import historical, planner, reasoning
from rca.confidence import assess_draft, first_error_time, is_weakly_supported
from rca.config import DB_PATH
from rca.context import build_context as build_context_of, merge_guidance
from rca.evidence import EvidenceLedger, add_changes, add_dependencies, add_log_groups
from rca.guardrails import MAX_ATTEMPTS, check_draft, format_feedback, run_with_retries, text_warnings
from rca.llm import LLMOutputError, metering, recording
from rca.models import (
    AssessedHypothesis,
    HistoricalFinding,
    ToolRun,
    DraftRCA,
    Evidence,
    Incident,
    TimelineEntry,
    InvestigationContext,
    InvestigationGuidance,
    InvestigationPlan,
    InvestigationStep,
    RCARecord,
)
from rca.timeline import as_lines, build_timeline as timeline_of
from rca.tools import find_changes, find_dependencies, find_logs
from rca.observability import tracer
from rca.redaction import redact

DEFAULT_OWNER = "Problem Manager"
MAX_SIMILAR_INCIDENTS = 5
GIVEN_TEXT_LIMIT = 2000  # characters of each text given to the agents kept on the build_context step, to show it
MAX_PAST_RCAS = 5
MAX_SECTION_LENGTH = 800  # characters of a past RCA section sent to the Historical RCA Agent
# What the agent reads of each past RCA: the symptoms, the cause, and the fix that was meant to stop it.
MAX_CONCLUSIONS = 3  # earlier RCAs of the problem given to the agents
MAX_CONCLUSION = 400  # characters of each
MAX_SYMPTOMS = 8  # symptoms of the problem given to the historical review
JUDGED_SECTIONS = ("Summary", "Root Cause", "Corrective Actions")


class Restart(list):
    """A list that replaces the one in the state instead of being added to it: build_context starts the
    trace of a run with its own step, whatever an earlier run in the same thread left (LangGraph Studio)."""


def _add_or_clear(current: list, update: list | None) -> list:
    """Add the update to the list; None empties it and a Restart replaces it, so every run starts anew."""
    if update is None:
        return []
    return list(update) if isinstance(update, Restart) else current + update


class InvestigationInput(TypedDict, total=False):
    """What starts an investigation: problem_id, or incident_id (the investigation then covers the
    whole problem of that incident); rca_id for the next revision of an RCA; or revision_id, a revision
    already created by store.start_rca or store.start_next_revision."""

    problem_id: str
    incident_id: str
    rca_id: str  # an RCA the expert sent back for more details, or whose last run failed: its next revision
    previous_rca_id: str  # the older name of rca_id
    revision_id: str
    guidance: dict  # models.InvestigationGuidance, optional
    owner: str
    db_path: str


class InvestigationState(InvestigationInput, total=False):
    """Everything the investigation found so far. Each node returns only the fields it changes."""

    started_at: datetime
    revision: RCARecord  # the revision this run fills in, RUNNING until save_revision
    context: InvestigationContext
    incidents: list[Incident]  # the incidents of the problem, in the order they happened
    incident: Incident  # the reference incident: the most recent one
    similar_incidents: list[Incident]
    plan: InvestigationPlan
    evidence: list[Evidence]
    timeline: list[TimelineEntry]
    tool_runs: list[ToolRun]
    historical_findings: list[HistoricalFinding]
    linked_incidents: list[str]
    draft: DraftRCA | None
    attempts: int
    problems: list[str]
    feedback: str | None
    hypotheses: list[AssessedHypothesis]
    weakly_supported: bool
    status: Literal["RUNNING", "READY", "ESCALATED"]  # of this run: READY when the draft passed the guardrail
    escalation_reason: str
    invalid_answers: int  # answers of the RCA Reasoning Agent that were not a valid draft at all
    # These two are added to by several nodes, not replaced. build_context starts them again.
    not_checked: Annotated[list[str], _add_or_clear]
    trace: Annotated[list[InvestigationStep], _add_or_clear]
    record: RCARecord


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _step(name: str, started_at: datetime, summary: str, **details: Any) -> InvestigationStep:
    """A finished step, as it is saved and shown: its summary and its details, secrets redacted (rca/redaction.py).
    details["input"] is what the node read, in short (ids and counts, not the texts); evidence_ids the evidence
    it found or cited."""
    return InvestigationStep(name=name, summary=redact(summary), started_at=started_at, finished_at=_now(),
                             details=redact(details))


def _db_path(state: InvestigationState) -> Path:
    return Path(state.get("db_path") or DB_PATH)


def _not_chosen(what: str) -> str:
    return f"{what} were not checked: the investigation plan did not choose this source."


def _window(start: datetime, end: datetime, incident_id: str | None = None) -> dict[str, str | None]:
    return {"start": start.isoformat(), "end": end.isoformat(), "incident_id": incident_id}


def _incident_text(incident: Incident) -> str:
    """The same text that represents an incident in the search index (rag.build_incident_records)."""
    parts = [incident.title, incident.description, incident.service, incident.business_service, " | ".join(incident.symptoms)]
    return " | ".join(part for part in parts if part)


def _search(collection: str, text: str, before: datetime, limit: int) -> list[dict[str, Any]]:
    """Search ChromaDB for records older than `before`, as a flat list, the closest first."""
    results = rag.query_collection(collection, text, limit=limit, before_timestamp=int(before.timestamp()))
    return [
        {
            "id": item["id"],
            "document": item.get("document", ""),
            "metadata": item.get("metadata", {}) or {},
            "distance": item.get("score", 0.0),
        }
        for item in results
    ]


def _rca_sections(rca_ids: list[str]) -> dict[str, dict[str, str]]:
    """All the sections of the given past RCAs, read from the ChromaDB index: {rca_id: {section: text}}."""
    if not rca_ids:
        return {}
    collection = chromadb.PersistentClient(path=str(rag.ROOT / "chroma_db")).get_collection("historical_rcas")
    result = collection.get(where={"document_id": {"$in": rca_ids}}, include=["metadatas", "documents"])
    sections: dict[str, dict[str, str]] = {}
    for metadata, document in zip(result["metadatas"], result["documents"]):
        sections.setdefault(metadata["document_id"], {})[metadata["section_name"]] = document
    return sections


def _past_rca_candidates(plan: InvestigationPlan, before: datetime, linked_to: list[str] | None = None) -> list[dict[str, Any]]:
    """The past RCAs closest to the search queries of the plan, and the past RCAs that link an incident
    of the problem or a similar incident (linked_to), each with the text the agent judges.

    The search works on sections, but the evidence is the RCA: the candidate is cited by the RCA
    id (RCA-2025-00114), so the same RCA found in several sections is judged and counted once.
    The agent judges the Summary and the Root Cause of each RCA, not only the closest section:
    a Timeline alone has no symptoms, and a relevant RCA was dropped because of it.
    """
    best: dict[str, dict[str, Any]] = {}
    for query in plan.search_queries:
        for result in _search("historical_rcas", query, before, MAX_PAST_RCAS):
            rca_id = result["metadata"].get("document_id") or result["id"].split("::")[0]
            if rca_id not in best or result["distance"] < best[rca_id]["distance"]:
                best[rca_id] = {**result, "id": rca_id}

    closest = sorted(best.values(), key=lambda item: item["distance"])[:MAX_PAST_RCAS]
    for item in closest:
        item["found_by"] = "search"
    # An RCA that links one of these incidents is found by the link, whatever its wording.
    for rca_id, link in rag.rcas_linked_to(linked_to or [], int(before.timestamp())).items():
        reason = f"links {', '.join(link['incidents'])}"
        known = next((item for item in closest if item["id"] == rca_id), None)
        if known is not None:
            known["found_by"] = f"search, and {reason}"
        else:
            metadata = {"document_id": rca_id, "service": link["service"], "completion_date": link["completion_date"]}
            closest.append({"id": rca_id, "document": "", "metadata": metadata, "distance": None, "found_by": reason})
    sections = _rca_sections([item["id"] for item in closest])

    candidates = []
    for item in closest:
        found = sections.get(item["id"], {})
        judged = [f"{name}: {found[name][:MAX_SECTION_LENGTH]}" for name in JUDGED_SECTIONS if name in found]
        metadata = {key: value for key, value in item["metadata"].items() if key != "section_name"}
        candidates.append({
            "id": item["id"],
            # Without these sections in the index, the closest section is the only text there is.
            "document": "\n".join(judged) or item["document"][:MAX_SECTION_LENGTH],
            "metadata": {**metadata, "matched_section": item["metadata"].get("section_name"), "source_type": "rca",
                         "found_by": item["found_by"]},
        })
    return candidates


def _incident_candidate(incident: Incident) -> dict[str, Any]:
    done = f" | What was done then: {incident.initial_mitigation}" if incident.initial_mitigation else ""
    return {
        "id": incident.incident_id,
        "document": _incident_text(incident) + done,
        "metadata": {
            "source_type": "incident",
            "service": incident.service,
            "detected_at": incident.detected_at.isoformat(),
        },
    }


def _findings_text(finding: HistoricalFinding) -> str:
    parts = [f"Judged relevant because: {finding.reason}"]
    if finding.similarities:
        parts.append(f"Alike: {'; '.join(finding.similarities)}")
    if finding.differences:
        parts.append(f"Different: {'; '.join(finding.differences)}")
    if finding.remediation:
        parts.append(f"Done then: {finding.remediation}")
    if finding.outcome:
        parts.append(f"Outcome: {finding.outcome}")
    return ". ".join(part.rstrip(".") for part in parts) + "."


def _add_history(ledger: EvidenceLedger, candidate: dict[str, Any], finding: HistoricalFinding,
                 incidents: dict[str, Incident], first_incident: datetime) -> bool:
    """Record a past record the review kept, with what the review found. Returns True for a past RCA completed
    before the first incident of the problem: the problem came back after it, so its corrective action did not
    prevent it (a fact computed here from the dates, not judged by the model)."""
    metadata = candidate["metadata"]
    judged = _findings_text(finding)
    if metadata["source_type"] == "incident":
        incident = incidents[candidate["id"]]
        done = f" What was done then: {incident.initial_mitigation}" if incident.initial_mitigation else ""
        ledger.add(
            "HISTORICAL_INCIDENT",
            incident.incident_id,
            f"Past {incident.service} incident {incident.incident_id}, detected {incident.detected_at:%Y-%m-%d}: "
            f"{incident.title}. {incident.description} Symptoms: {'; '.join(incident.symptoms)}.{done} {judged}",
            incident.incident_id,
            incident.detected_at,
        )
        return False
    if metadata["source_type"] == "application_rca":
        validated = datetime.fromisoformat(metadata["validated_at"])
        ledger.add(
            "HISTORICAL_RCA",
            candidate["id"],
            f"RCA {candidate['id']} validated in this application for problem {metadata['problem_id']} "
            f"({metadata['service']}), {validated:%Y-%m-%d}. {candidate['document']} {judged}",
            candidate["id"],
            validated,
        )
        return False

    completed = metadata.get("completion_date")
    completed_at = datetime.fromtimestamp(completed, tz=timezone.utc) if isinstance(completed, (int, float)) else None
    came_back = completed_at is not None and completed_at < first_incident
    recurrence = (f" The problem came back after this RCA: it was completed {completed_at:%Y-%m-%d}, before the first "
                  f"incident of this problem ({first_incident:%Y-%m-%d}), so its corrective action did not prevent it."
                  if came_back else "")
    ledger.add(
        "HISTORICAL_RCA",
        candidate["id"],
        f"Past RCA {candidate['id']} for {metadata.get('service', 'an unknown service')}"
        f"{f', completed {completed_at:%Y-%m-%d}' if completed_at else ''}. "
        f"{candidate['document']} {judged}{recurrence}",
        candidate["id"],
        completed_at,
    )
    return came_back


# --------------------------------------------------------------------------------------
# The nodes
# --------------------------------------------------------------------------------------


def build_context(state: InvestigationState) -> dict:
    """Node 1, code: the revision this run fills in, and the context built from the problem (rca/context.py):
    its incidents, the windows, the guide of the problem, the notes and instructions of the Problem Manager,
    the request of the expert and what earlier RCAs of the problem concluded. A rule that refuses the RCA,
    or an unknown problem or incident, stops the run.

    LangGraph Studio keeps the state of a thread between runs. Without the reset, a second run in
    the same thread would continue the attempt count, the steps and the status of the first one.
    """
    started = _now()
    db_path = _db_path(state)
    owner = state.get("owner") or DEFAULT_OWNER
    guidance = InvestigationGuidance.model_validate(state["guidance"]) if state.get("guidance") else None
    revision = _revision(state, owner, guidance, db_path)
    try:
        guidance, request, guidance_by = revision.guidance, None, "Problem Manager"
        review = store.open_request(revision.rca_id, db_path=db_path)
        if review is not None:  # the expert asked for more details: the request and the wider searches
            guidance = merge_guidance(guidance, review.guidance)
            request = store.expert_request(review)
            if review.guidance:
                guidance_by = "Problem Manager and Technical Expert"
        context, incidents = build_context_of(db_path, problem_id=revision.problem_id, guidance=guidance,
                                              expert_request=request, guidance_by=guidance_by,
                                              previous_conclusions=previous_conclusions(revision, db_path))
    except Exception as exc:
        store.fail_revision(revision.revision_id, f"build_context: {type(exc).__name__}: {exc}", db_path=db_path)
        raise
    reference = incidents[-1]
    given_text = {name: "\n".join(value) if isinstance(value, list) else value
                  for name, value in (("notes", context.notes), ("instructions", context.instructions),
                                      ("expert request", context.expert_request),
                                      ("earlier conclusions", context.previous_conclusions)) if value}
    given = list(given_text)
    summary = (f"{len(incidents)} incident(s) of {context.problem_id} on {', '.join(context.services)}; logs around every "
               f"incident, changes from {context.change_window.start:%Y-%m-%d}. "
               + (f"Given to the agents: {', '.join(given)}." if given else "No guide, notes or requests."))
    return {
        "revision": revision,
        "problem_id": context.problem_id,
        "incident_id": reference.incident_id,
        "owner": owner,
        "context": context,
        "incidents": incidents,
        "incident": reference,
        "started_at": started,
        "status": "RUNNING",
        "similar_incidents": [],
        "plan": None,
        "evidence": [],
        "tool_runs": [],
        "timeline": [],
        "linked_incidents": [],
        "historical_findings": [],
        "draft": None,
        "attempts": 0,
        "invalid_answers": 0,
        "problems": [],
        "feedback": None,
        "hypotheses": [],
        "weakly_supported": False,
        "escalation_reason": "",
        "record": None,
        "not_checked": None,
        "trace": Restart([_step("build_context", started, summary, problem_id=context.problem_id,
                        incidents=context.incident_ids, services=context.services, given=given,
                        given_text={name: text[:GIVEN_TEXT_LIMIT] for name, text in given_text.items()},
                        revision=revision.revision_id,
                        input={"problem_id": revision.problem_id, "revision": revision.revision_id,
                               "rca_id": revision.rca_id, "guidance": bool(revision.guidance),
                               "expert_request": bool(request)})]),
    }


def previous_conclusions(revision: RCARecord, db_path: Path) -> list[str]:
    """What experts concluded about the earlier RCAs of the problem (the RCA being run excluded): the cause
    they rejected and why, or validated. Read by the agents so a rejected cause is not proposed again blindly."""
    conclusions = []
    for summary in store.list_summaries(problem_id=revision.problem_id, db_path=db_path):
        if summary.rca_id == revision.rca_id or summary.status not in ("REJECTED", "VALIDATED"):
            continue
        latest = store.get_rca(summary.rca_id, db_path=db_path)
        if latest is None or latest.review is None:
            continue
        main = latest.final_root_cause or (latest.hypotheses[0].candidate_root_cause if latest.hypotheses else "none")
        verb = "validated" if summary.status == "VALIDATED" else "rejected"
        conclusions.append(f"{summary.rca_id} was {verb} by the Technical Expert"
                           f"{f': {latest.review.comment}' if latest.review.comment else '.'} "
                           f"Its main hypothesis: {main}"[:MAX_CONCLUSION])
    return conclusions[:MAX_CONCLUSIONS]


def _revision(state: InvestigationState, owner: str, guidance: InvestigationGuidance | None, db_path: Path) -> RCARecord:
    """The RUNNING revision of this run: the one given, the next one of an RCA, or the first one of a new RCA."""
    if (state.get("revision_id") or "").strip():
        revision = store.get_rca(state["revision_id"].strip(), db_path=db_path)
        if revision is None or revision.run_status != "RUNNING":
            raise ValueError(f"Revision '{state['revision_id']}' is not waiting for a run.")
        return revision
    rca_id = (state.get("rca_id") or state.get("previous_rca_id") or "").strip()
    if rca_id:
        if store.get_summary(rca_id, db_path=db_path) is None:  # a revision id of an older interface
            rca_id = rca_id.rsplit("-R", 1)[0]
        return store.start_next_revision(rca_id, owner, guidance, db_path=db_path)
    problem_id = (state.get("problem_id") or "").strip() or None
    incident_id = (state.get("incident_id") or "").strip() or None
    if problem_id is None and incident_id:
        if storage.get_incident(db_path, incident_id) is None:
            raise ValueError(f"Incident '{incident_id}' was not found.")
        problem_id = storage.get_problem_id_for_incident(db_path, incident_id)
        if problem_id is None:
            raise ValueError(f"{incident_id} is in no problem. An RCA investigates a problem: create a problem "
                             "for the incident first (a problem may hold a single incident).")
    if problem_id is None:
        raise ValueError("Give the problem to investigate.")
    return store.start_rca(problem_id, owner, guidance, db_path=db_path)


def _windows_of(context: InvestigationContext) -> tuple[int, int]:
    """The hours of logs before each detection and the days of changes before the first incident that the
    context already searches."""
    guidance = context.guidance or InvestigationGuidance()
    return guidance.log_hours_before or 2, guidance.change_window_days or 7


def investigation_planner(state: InvestigationState) -> dict:
    """Node 2, agent: the search queries and the extra searches, checked by code. A plan the model fails to
    give is asked again with the problems, at most 3 times."""
    started = _now()
    context, incidents = state["context"], state["incidents"]
    log_hours, change_days = _windows_of(context)
    known = storage.list_services(_db_path(state))
    # the model that answered each attempt, shown in the interface, and the measures of each request
    with recording() as models, metering() as llm_calls:
        result = run_with_retries(
            ask=lambda feedback: planner.plan_investigation(context, incidents, known, log_hours, change_days, feedback),
            check=lambda plan: [],  # the plan is checked inside plan_investigation
        )
    attempts = [{"attempt": attempt.number, "problems": attempt.problems} for attempt in result.attempts]

    if result.escalated:
        reason = f"The Investigation Planner did not produce a valid plan in {len(result.attempts)} attempts."
        return {
            "status": "ESCALATED",
            "escalation_reason": reason,
            "invalid_answers": len(result.attempts),  # no plan at all: a technical failure, not a judgement
            "attempts": len(result.attempts),
            "trace": [_step("investigation_planner", started, reason, attempts=attempts, models=models, llm_calls=llm_calls)],
        }

    plan = result.value
    read = {"incidents": context.incident_ids, "known_services": len(known), "log_hours_before": log_hours,
            "change_days_before": change_days, "notes": bool(context.notes),
            "instructions": bool(context.instructions), "expert_request": bool(context.expert_request),
            "earlier_conclusions": len(context.previous_conclusions)}
    summary = f"{len(plan.search_queries)} search queries."
    if plan.extra_searches:
        summary += " Extra searches: " + "; ".join(f"{item.source} of {item.service}" for item in plan.extra_searches) + "."
    if plan.refused_searches:
        summary += f" Refused: {len(plan.refused_searches)} request(s) outside the rules."
    return {
        "plan": plan,
        "trace": [_step(
            "investigation_planner", started, summary,
            attempts=attempts, search_queries=plan.search_queries, rationale=plan.rationale,
            extra_searches=[item.model_dump() for item in plan.extra_searches], refused_searches=plan.refused_searches,
            models=models, llm_calls=llm_calls, input=read,
        )],
    }


def after_planner(state: InvestigationState) -> Literal["gather_evidence", "save_revision"]:
    return "save_revision" if state.get("status") == "ESCALATED" else "gather_evidence"


class _Runs:
    """The ToolRuns of gather_evidence: every call of a tool, its arguments, its result or its error."""

    def __init__(self) -> None:
        self.runs: list[ToolRun] = []

    def run(self, tool: str, source: str, arguments: dict, call: Callable[[str], Any], *, requested_by: str = "rule",
            reason: str | None = None) -> Any:
        """Call the tool with its run id, record the run, and return its result, or None after an error (an
        error is a fact about the investigation, never evidence that nothing happened)."""
        run_id = f"TR-{len(self.runs) + 1:02d}"
        started = _now()
        with tracer().start_as_current_span(f"tool.{tool}") as span:
            for key, value in arguments.items():
                span.set_attribute(f"tool.{key}", str(value))
            try:
                found, evidence = call(run_id)
            except Exception as exc:  # a source down: recorded, and the investigation goes on without it
                self.runs.append(ToolRun(run_id=run_id, tool=tool, source=source, arguments=arguments,
                                         requested_by=requested_by, reason=reason, status="error",
                                         error=f"{type(exc).__name__}: {exc}", started_at=started, finished_at=_now()))
                return None
            span.set_attribute("tool.result_count", found)
        self.runs.append(ToolRun(run_id=run_id, tool=tool, source=source, arguments=arguments, requested_by=requested_by,
                                 reason=reason, status="ok", result_count=found,
                                 evidence_ids=list(dict.fromkeys(item.evidence_id for item in evidence)),
                                 started_at=started, finished_at=_now()))
        return found

    def refused(self, tool: str, source: str, arguments: dict, reason: str, why: str) -> None:
        now = _now()
        self.runs.append(ToolRun(run_id=f"TR-{len(self.runs) + 1:02d}", tool=tool, source=source, arguments=arguments,
                                 requested_by="planner", reason=reason, status="refused", error=why,
                                 started_at=now, finished_at=now))


def gather_evidence(state: InvestigationState) -> dict:
    """Node 3, code: every source, with the services and the windows of the context, and the extra searches
    of the plan the code accepted. Every fact goes into the ledger with a stable id, the time it happened and
    the time it was found; every call of a tool is a ToolRun (source, arguments, result, time, error)."""
    started = _now()
    db_path = _db_path(state)
    context, plan, incidents = state["context"], state["plan"], state["incidents"]
    by_id = {item.incident_id: item for item in incidents}
    several = len(incidents) > 1
    ledger = EvidenceLedger()
    runs = _Runs()
    not_checked: list[str] = []
    found: dict[str, list[str]] = {"logs": [], "dependency_logs": [], "changes": [], "cmdb": [], "problem_incidents": []}
    first, change_window = incidents[0], context.change_window
    first_of = f"the first incident of the problem ({first.incident_id})" if several else "detection"
    rule = context.sources

    # First the incident itself: its symptoms are what the hypotheses must explain (no confidence points).
    reference = by_id[context.reference_incident_id]
    ledger.add(
        "INCIDENT",
        reference.incident_id,
        f"The incident under investigation, {reference.incident_id} on {reference.service} ({reference.severity}), "
        f"detected {reference.detected_at:%Y-%m-%d %H:%M} UTC: {reference.title}. {reference.description} "
        f"Symptoms: {'; '.join(reference.symptoms)}.",
        reference.incident_id,
        reference.detected_at,
    )

    # The past incidents that look like the reference incident, only older than its detection; read by
    # historical_review. The incidents of the problem are not searched for: they are part of it already.
    members = set(context.incident_ids)
    similar: list[Incident] = []

    def search_similar(run_id):
        results = _search("historical_incidents", _incident_text(reference), reference.detected_at,
                          MAX_SIMILAR_INCIDENTS + len(members))
        items = [storage.get_incident(db_path, item["id"]) for item in results if item["id"] not in members]
        similar.extend(item for item in items[:MAX_SIMILAR_INCIDENTS] if item is not None)
        return len(similar), []

    if runs.run("search_similar_incidents", "historical_incidents",
                {"incident_id": reference.incident_id, "before": reference.detected_at.isoformat()}, search_similar,
                reason="rule: past incidents like the reference incident, older than its detection") is None:
        not_checked.append(f"Similar past incidents could not be searched ({runs.runs[-1].error}).")

    dependencies = []
    for service in context.services:
        def cmdb(run_id, service=service):
            result = find_dependencies(service, db_path=db_path)
            dependencies.append((result, run_id))
            return len(result.components), []
        if runs.run("find_dependencies", "cmdb", {"service": service}, cmdb, reason=f"rule: {rule.get('services', '')}") is None:
            not_checked.append(f"The CMDB of {service} could not be read ({runs.runs[-1].error}).")
        elif not dependencies[-1][0].components:
            not_checked.append(f"The CMDB has no components for {service}, so its dependencies are unknown.")

    def logs(service, start, end, incident, dependency, requested_by="rule", reason=None):
        def call(run_id):
            groups = find_logs(service, start, end, db_path=db_path)
            added = add_log_groups(ledger, groups, incident.detected_at,
                                   f"the detection of {incident.incident_id}" if several else "detection", dependency,
                                   tool_run=run_id)
            found["dependency_logs" if dependency else "logs"].extend(group.examples[0].log_id for group in groups)
            return len(groups), added
        arguments = {"service": service, "start": start.isoformat(), "end": end.isoformat(), "incident_id": incident.incident_id}
        if runs.run("find_logs", "logs", arguments, call, requested_by=requested_by,
                    reason=reason or f"rule: {rule.get('log_windows', '')}") is None:
            not_checked.append(f"The logs of {service} around {incident.incident_id} could not be read "
                               f"({runs.runs[-1].error}).")

    for window in context.log_windows:
        incident = by_id[window.incident_id]
        for service in [*context.services, *context.related_services]:
            logs(service, window.start, window.end, incident, service not in context.services)

    def changes(services, start, end, requested_by="rule", reason=None):
        def call(run_id):
            items = find_changes(services, start, end, db_path=db_path)
            added = add_changes(ledger, items, first.detected_at, first_of, tool_run=run_id)
            found["changes"].extend(item.change_id for item in items if item.change_id not in found["changes"])
            return len(items), added
        arguments = {"services": services, "start": start.isoformat(), "end": end.isoformat()}
        if runs.run("find_changes", "changes", arguments, call, requested_by=requested_by,
                    reason=reason or f"rule: {rule.get('change_window', '')}") is None:
            not_checked.append(f"The changes of {', '.join(services)} could not be read ({runs.runs[-1].error}).")

    services = [*context.services, *context.related_services]
    changes(services, change_window.start, change_window.end)

    # The searches the planner asked for, already checked by code (planner.check_extra_searches).
    for search in plan.extra_searches:
        why = f"planner: {search.reason}"
        if search.source == "logs":
            for incident in incidents:
                logs(search.service, incident.detected_at - timedelta(hours=search.hours_before),
                     incident.detected_at + timedelta(hours=1), incident, search.service not in context.services,
                     "planner", why)
        else:
            changes([search.service], first.detected_at - timedelta(days=search.days_before), change_window.end,
                    "planner", why)
    for refused in plan.refused_searches:
        runs.refused("find_logs" if refused["source"] == "logs" else "find_changes", refused["source"],
                     {key: refused.get(key) for key in ("service", "hours_before", "days_before")},
                     f"planner: {refused.get('reason', '')}", refused["refused"])

    for result, run_id in dependencies:
        added = add_dependencies(ledger, result, tool_run=run_id)
        found["cmdb"].extend(item.citation for item in added if item.citation not in found["cmdb"])
        run = next(item for item in runs.runs if item.run_id == run_id)
        run.evidence_ids = [item.evidence_id for item in added]

    # The other incidents of the problem are facts too: the same failure, seen again.
    for item in incidents:
        if item.incident_id == context.reference_incident_id:
            continue
        ledger.add(
            "HISTORICAL_INCIDENT",
            item.incident_id,
            # the title and the symptoms only: the reference incident carries the full description, and the
            # request to the Reasoning Agent must stay under the 8000 tokens of the free tier of Groq
            f"Incident {item.incident_id} of the same problem {context.problem_id}, {item.service}, detected "
            f"{item.detected_at:%Y-%m-%d %H:%M} UTC: {item.title}. Symptoms: {'; '.join(item.symptoms)}.",
            item.incident_id,
            item.detected_at,
        )
        found["problem_incidents"].append(item.incident_id)

    ok = sum(1 for run in runs.runs if run.status == "ok")
    failed = [run.run_id for run in runs.runs if run.status == "error"]
    summary = (
        f"{len(runs.runs)} tool run(s), {ok} ok. Logs: {len(found['logs'])} ERROR/WARN pattern(s) around "
        f"{len(context.log_windows)} incident(s), {len(found['dependency_logs'])} on the services it depends on. "
        f"Changes: {len(found['changes'])} ({', '.join(found['changes']) or 'none'}). "
        f"CMDB: {len(found['cmdb'])} component(s) depended on. Similar past incidents: {len(similar)}."
    )
    if failed:
        summary += f" Failed: {', '.join(failed)}."
    if found["problem_incidents"]:
        summary += f" Other incidents of the problem: {', '.join(found['problem_incidents'])}."
    span = trace.get_current_span()
    span.set_attribute("rca.evidence_ids", [item.evidence_id for item in ledger.items()])
    span.set_attribute("rca.tool_runs", len(runs.runs))
    return {
        "evidence": ledger.items(),
        "tool_runs": runs.runs,
        "similar_incidents": similar,
        "not_checked": not_checked,
        "trace": [_step(
            "gather_evidence", started, summary,
            evidence=len(ledger),
            services=services,
            log_windows=[_window(item.start, item.end, item.incident_id) for item in context.log_windows],
            change_window=_window(change_window.start, change_window.end),
            found={**found, "similar_incidents": [item.incident_id for item in similar]},
            tool_runs=[run.model_dump(mode="json") for run in runs.runs],
            evidence_ids=[item.evidence_id for item in ledger.items()],
            input={"services": context.services, "related_services": context.related_services,
                   "log_windows": len(context.log_windows), "change_window": _window(change_window.start, change_window.end),
                   "extra_searches": len(plan.extra_searches)},
        )],
    }


def _other_service(candidate: dict[str, Any], services: set[str]) -> str | None:
    """The service of a past record when it is not a service of the problem, else None."""
    service = candidate["metadata"].get("service")
    return service if service and service not in services else None


def build_timeline(state: InvestigationState) -> dict:
    """Node 4, code: the facts found so far on one time axis, with the first error marked (rca/timeline.py).
    Each moment keeps the time it happened (from the source), when it was found and its evidence id."""
    started = _now()
    entries = timeline_of(state["evidence"], state["context"].incident_ids, state["incidents"][0].detected_at,
                          state["context"].services)
    first = next((entry for entry in entries if entry.marker == "first error"), None)
    before = [entry.citation for entry in entries if entry.marker == "before the first error"]
    summary = f"{len(entries)} moment(s) on the timeline."
    if first:
        summary += f" First error {first.at:%Y-%m-%d %H:%M} UTC ({first.citation})."
    summary += f" Changes before it: {', '.join(before) or 'none'}."
    return {"timeline": entries, "trace": [_step("build_timeline", started, summary, moments=len(entries),
                                                  first_error=first.citation if first else None,
                                                  changes_before=before,
                                                  evidence_ids=[entry.evidence_id for entry in entries],
                                                  input={"evidence": len(state["evidence"])})]}


def _application_rca_candidates(state: InvestigationState) -> list[dict[str, Any]]:
    """RCAs validated in the application for earlier problems of the same services: their validated cause,
    the decision of the expert and what was recommended. Only problems whose incidents all happened before the
    first incident of this one: what was known then, not what this problem taught later."""
    db_path = _db_path(state)
    context, first = state["context"], state["incidents"][0]
    candidates = []
    for summary in store.list_summaries("VALIDATED", db_path=db_path):
        if summary.problem_id == context.problem_id:
            continue
        problem = storage.get_problem(db_path, summary.problem_id)
        record = store.get_rca(summary.rca_id, db_path=db_path)
        if problem is None or record is None or not set(problem.services) & set(context.services):
            continue
        detected = [storage.get_incident(db_path, link.incident_id) for link in problem.incidents]
        if any(item is None or item.detected_at >= first.detected_at for item in detected):
            continue
        review = record.review
        text = (f"Validated root cause: {record.final_root_cause}. Expert {review.reviewer}: {review.comment}. "
                f"Workaround then: {record.suggested_workaround or 'none recorded'}.")
        candidates.append({"id": summary.rca_id, "document": text[:MAX_SECTION_LENGTH], "metadata": {
            "source_type": "application_rca", "service": problem.services[0], "problem_id": summary.problem_id,
            "validated_at": review.decided_at.isoformat()}})
    return candidates[:MAX_PAST_RCAS]


def _current_problem(state: InvestigationState) -> dict[str, Any]:
    """The current problem as the historical review compares it: short, its symptoms and what is asked."""
    context = state["context"]
    symptoms = list(dict.fromkeys(symptom for item in state["incidents"] for symptom in item.symptoms))[:MAX_SYMPTOMS]
    return {"title": context.title, "symptoms": symptoms,
            **({"expert_request": context.expert_request} if context.expert_request else {})}


def historical_review(state: InvestigationState) -> dict:
    """Node 5, agent: RAG over past RCAs and incidents, and the RCAs validated in the application; the agent
    keeps only what is really alike and says how it is alike, how it differs, what was done then and how it
    ended. The rule that past records of other services are never evidence is applied by code first, so it does
    not depend on the model. An invalid answer is asked again (at most 3 times) before the history is given up.
    """
    started = _now()
    incident, plan = state["incident"], state["plan"]
    ledger = EvidenceLedger(state["evidence"])
    not_checked: list[str] = []
    candidates: list[dict[str, Any]] = []

    try:
        linked_to = [*state["context"].incident_ids, *(item.incident_id for item in state["similar_incidents"])]
        candidates += _past_rca_candidates(plan, incident.detected_at, linked_to)
    except Exception as exc:  # Ollama or ChromaDB is not available: the investigation continues without them
        not_checked.append(f"Past RCAs could not be searched ({type(exc).__name__}: {exc}).")
    candidates += [_incident_candidate(item) for item in state["similar_incidents"]]
    candidates += _application_rca_candidates(state)

    services = set(state["context"].services)
    dropped: list[dict[str, str]] = [
        {"id": item["id"], "reason": f"Another service ({_other_service(item, services)}): past records of other "
                                     "services are never evidence."}
        for item in candidates if _other_service(item, services)
    ]
    candidates = [item for item in candidates if not _other_service(item, services)]

    if not candidates:
        summary = "No past RCA or incident of the services of the problem to review."
        if dropped:
            summary += f" Dropped {', '.join(item['id'] for item in dropped)}."
        return {
            "linked_incidents": [],
            "historical_findings": [],
            "not_checked": not_checked,
            "trace": [_step("historical_review", started, summary, kept=[], dropped=dropped)],
        }

    # The agent also returns its own evidence list; the pipeline uses only its decisions and
    # records the kept results in the shared ledger, so the evidence ids stay unique.
    current = _current_problem(state)
    with recording() as models, metering() as llm_calls:
        result = run_with_retries(ask=lambda feedback: historical.review_historical_rcas(plan, candidates, current)[0],
                                  check=lambda review: [])
    attempts = [{"attempt": attempt.number, "problems": attempt.problems} for attempt in result.attempts]
    if result.escalated:
        note = (f"The Historical Review Agent did not return a valid answer in {len(result.attempts)} attempts, so past "
                f"RCAs and incidents were not used ({result.attempts[-1].problems[0]}).")
        return {
            "linked_incidents": [],
            "historical_findings": [],
            "not_checked": [*not_checked, note],
            "trace": [_step("historical_review", started, note, attempts=attempts, kept=[], dropped=dropped,
                            models=models, llm_calls=llm_calls)],
        }

    decisions = {decision.citation: decision for decision in result.value.decisions}
    incidents = {item.incident_id: item for item in state["similar_incidents"]}
    kept: list[dict[str, Any]] = []
    findings: list[HistoricalFinding] = []
    for candidate in candidates:
        decision = decisions.get(candidate["id"])
        if decision is None:
            dropped.append({"id": candidate["id"], "reason": "The agent gave no decision for this result."})
        elif not decision.relevant:
            dropped.append({"id": candidate["id"], "reason": decision.reason})
        else:
            kind = {"incident": "incident", "application_rca": "application_rca"}.get(
                candidate["metadata"]["source_type"], "rca")
            finding = HistoricalFinding(citation=candidate["id"], kind=kind, reason=decision.reason,
                                        similarities=_listed(decision.similarities),
                                        differences=_listed(decision.differences),
                                        remediation=decision.remediation, outcome=decision.outcome)
            came_back = _add_history(ledger, candidate, finding, incidents, state["incidents"][0].detected_at)
            findings.append(finding.model_copy(update={"came_back_after": came_back}))
            kept.append({"id": candidate["id"], "reason": decision.reason, "came_back_after": came_back})

    kept_ids = [item["id"] for item in kept]
    summary = f"Kept {', '.join(kept_ids) or 'nothing'}. Dropped {', '.join(item['id'] for item in dropped) or 'nothing'}."
    came_back = [item["id"] for item in kept if item["came_back_after"]]
    if came_back:
        summary += f" The problem came back after {', '.join(came_back)}: its corrective action did not prevent it."
    return {
        "evidence": ledger.items(),
        "linked_incidents": [item_id for item_id in kept_ids if item_id in incidents],
        "historical_findings": findings,
        "not_checked": not_checked,
        "trace": [_step("historical_review", started, summary, kept=kept, dropped=dropped, attempts=attempts,
                        findings=[item.model_dump() for item in findings], models=models, llm_calls=llm_calls,
                        evidence_ids=[item.evidence_id for item in ledger.items()
                                      if item.citation in {kept_item["id"] for kept_item in kept}],
                        input={"candidates": [item["id"] for item in candidates], "current_problem": current.get("title")})],
    }


def _listed(values: list[str]) -> list[str]:
    """The items of a list the model wrote, each one on its own: a model sometimes writes several items in one
    string, joined by '","' as in JSON (seen with gpt-oss-120b)."""
    items = [part.strip().strip('"').strip() for value in values for part in value.split('","')]
    return [item for item in items if item][:3]


def brief_of(context: InvestigationContext) -> dict[str, Any]:
    """What the investigation must answer, for the RCA Reasoning Agent: built by code from the context, short,
    and only what was given. The request of the expert is sent on its own, as before."""
    return {key: value for key, value in {
        "problem_title": context.title,
        "problem_manager_notes": context.notes,
        "problem_manager_instructions": context.instructions,
        "earlier_rcas_of_the_problem": context.previous_conclusions,
    }.items() if value}


def rca_reasoning_agent(state: InvestigationState) -> dict:
    """Agent 3: the draft, from the evidence ledger only. On a retry it also gets the problems."""
    started = _now()
    attempt = state.get("attempts", 0) + 1
    shortened: list[str] = []
    cleaned: list[str] = []
    try:
        with recording() as models, metering() as llm_calls:
            draft = reasoning.propose_draft(state["incident_id"], state["evidence"], state.get("feedback"),
                                            state["context"].expert_request, as_lines(state.get("timeline") or []),
                                            brief_of(state["context"]), shortened, cleaned)
    except LLMOutputError as exc:
        return {
            "attempts": attempt,
            "invalid_answers": state.get("invalid_answers", 0) + 1,
            "draft": None,
            "problems": [str(exc)],
            "trace": [_step("rca_reasoning_agent", started, f"Attempt {attempt}: the answer is not a valid draft.",
                           models=models, llm_calls=llm_calls, input_shortened=shortened, attempt=attempt,
                           problems=[str(exc)[:500]], input=_reasoning_input(state, attempt))],
        }
    summary = f"Attempt {attempt}: {len(draft.hypotheses)} hypothesis(es) proposed."
    cited = sorted({item for hypothesis in draft.hypotheses
                    for item in hypothesis.supporting_evidence + hypothesis.contradicting_evidence})
    span = trace.get_current_span()
    span.set_attribute("rca.attempt", attempt)
    span.set_attribute("rca.hypotheses_count", len(draft.hypotheses))
    span.set_attribute("rca.top_hypothesis", draft.hypotheses[0].candidate_root_cause if draft.hypotheses else "")
    return {"attempts": attempt, "draft": draft, "problems": [],
            "trace": [_step("rca_reasoning_agent", started, summary, models=models, llm_calls=llm_calls,
                            input_shortened=shortened, ids_cleaned=cleaned, attempt=attempt, evidence_ids=cited,
                            input=_reasoning_input(state, attempt))]}


def _reasoning_input(state: InvestigationState, attempt: int) -> dict:
    return {"attempt": attempt, "evidence": len(state["evidence"]), "timeline": len(state.get("timeline") or []),
            "brief": sorted(brief_of(state["context"])), "expert_request": bool(state["context"].expert_request),
            "feedback": bool(state.get("feedback"))}


def guardrail(state: InvestigationState) -> dict:
    """The checks on the draft: accept it, ask again with the problems, or escalate after 3 attempts."""
    started = _now()
    attempt, draft = state["attempts"], state.get("draft")
    evidence_ids = {item.evidence_id for item in state["evidence"]}
    first_error = first_error_time(state["evidence"], state["incidents"][0].detected_at, state["context"].services)
    problems = state["problems"] if draft is None else check_draft(draft, evidence_ids, state["evidence"], first_error)

    if not problems:
        cited = {item for hypothesis in draft.hypotheses for item in hypothesis.supporting_evidence + hypothesis.contradicting_evidence}
        summary = f"Draft accepted on attempt {attempt}: the schema is valid and all {len(cited)} cited evidence ids exist."
        trace.get_current_span().set_attribute("rca.guardrail", "accepted")
        return {"feedback": None, "trace": [_step("guardrail", started, summary, attempt=attempt,
                                                  warnings=text_warnings(draft), next="confidence",
                                                  input={"hypotheses": [item.hypothesis_id for item in draft.hypotheses]})]}

    if attempt >= MAX_ATTEMPTS:
        reason = f"The RCA Reasoning Agent did not produce a valid draft in {attempt} attempts."
        trace.get_current_span().set_attribute("rca.guardrail", "escalated")  # linia ~455
        return {
            "status": "ESCALATED",
            "escalation_reason": reason,
            "trace": [_step("guardrail", started, f"Draft refused. {reason} Escalated.", attempt=attempt, problems=problems,
                            next="save_revision")],
        }

    summary = f"Draft refused on attempt {attempt}; asking again with the problems."
    trace.get_current_span().set_attribute("rca.guardrail", "retry")    
    return {
        "feedback": format_feedback(problems),
        "trace": [_step("guardrail", started, summary, attempt=attempt, problems=problems,
                        next="rca_reasoning_agent")],
    }


def after_guardrail(state: InvestigationState) -> Literal["confidence", "rca_reasoning_agent", "save_revision"]:
    if state.get("status") == "ESCALATED":
        return "save_revision"
    return "rca_reasoning_agent" if state.get("feedback") else "confidence"


def confidence(state: InvestigationState) -> dict:
    """The rules: HIGH / MEDIUM / LOW for each hypothesis, and the weakly supported mark."""
    started = _now()
    # without log evidence, the first error is the detection of the first incident of the problem
    hypotheses = assess_draft(state["draft"], state["evidence"], state["incidents"][0].detected_at,
                              state["context"].services)
    weak = is_weakly_supported(hypotheses)
    summary = " ".join(f"{item.hypothesis_id}: {item.confidence} ({item.confidence_points} points)." for item in hypotheses)
    if weak:
        summary += " No hypothesis is above LOW: weakly supported, more evidence is recommended before approval."
    span = trace.get_current_span()
    for item in hypotheses:
        span.set_attribute(f"rca.confidence.{item.hypothesis_id}", item.confidence)
        span.set_attribute(f"rca.points.{item.hypothesis_id}", item.confidence_points)
    span.set_attribute("rca.weakly_supported", weak)
    return {
        "hypotheses": hypotheses,
        "weakly_supported": weak,
        "status": "READY",
        "trace": [_step("confidence", started, summary,
                        levels={item.hypothesis_id: item.confidence for item in hypotheses},
                        input={"hypotheses": [item.hypothesis_id for item in hypotheses],
                               "evidence": len(state["evidence"])})],
    }


def save_revision(state: InvestigationState) -> dict:
    """Node 9, code: end the revision of this run (store.complete_revision): a draft, or the escalation.
    Saved once: a technical retry of the save never makes a second revision.

    A draft that passed the guardrail is saved as DRAFT: the Problem Manager sends it to the Technical
    Expert explicitly (store.submit_for_review), never automatically. When the guardrail refused a draft
    in every attempt, the RCA is ESCALATED_MANUAL; when no attempt gave a usable answer at all (the plan
    or every draft was not valid JSON), nothing was concluded: the run is FAILED and can be started again.
    """
    db_path = _db_path(state)
    now = _now()
    ready = state["status"] == "READY"
    draft = state["draft"] if ready else None
    if ready:
        outcome = "DRAFT"
    elif state.get("attempts") and state.get("invalid_answers", 0) >= state["attempts"]:
        outcome = "FAILED"
    else:
        outcome = "ESCALATED_MANUAL"
    reason = None if ready else state.get("escalation_reason") or None
    revision: RCARecord = state["revision"]
    record = revision.model_copy(update=dict(
        incident_id=state["incident_id"],
        owner=state["owner"],
        completed_at=now,
        duration_seconds=round((now - state["started_at"]).total_seconds(), 1),
        linked_incidents=state.get("linked_incidents", []),
        problem_id=state.get("problem_id"),
        context=state.get("context"),
        plan=state.get("plan"),
        evidence=state.get("evidence", []),
        timeline=state.get("timeline", []),
        tool_runs=state.get("tool_runs", []),
        historical_findings=state.get("historical_findings", []),
        trace=state["trace"],
        investigation_summary=draft.investigation_summary if draft else state.get("escalation_reason", ""),
        observed_patterns=draft.observed_patterns if draft else [],
        hypotheses=state.get("hypotheses", []) if draft else [],
        single_hypothesis_reason=draft.single_hypothesis_reason if draft else None,
        not_checked=state["not_checked"] + (draft.not_checked if draft else []),
        weakly_supported=state.get("weakly_supported", False),
        suggested_workaround=draft.suggested_workaround if draft else None,
        change_likely_required=draft.change_likely_required if draft else False,
        error=None if outcome != "FAILED" else reason,
    ))
    return {"record": store.complete_revision(record, outcome, reason, db_path=db_path)}


# --------------------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------------------


def build_graph(checkpointer=None):
    """The compiled graph. The checkpointer keeps the state between runs (Studio adds its own)."""
    builder = StateGraph(InvestigationState, input_schema=InvestigationInput)
    for node in (build_context, investigation_planner, gather_evidence, build_timeline, historical_review,
                 rca_reasoning_agent, guardrail, confidence, save_revision):
        builder.add_node(node.__name__, node)

    builder.add_edge(START, "build_context")
    builder.add_edge("build_context", "investigation_planner")
    builder.add_conditional_edges("investigation_planner", after_planner, ["gather_evidence", "save_revision"])
    builder.add_edge("gather_evidence", "build_timeline")
    builder.add_edge("build_timeline", "historical_review")
    builder.add_edge("historical_review", "rca_reasoning_agent")
    builder.add_edge("rca_reasoning_agent", "guardrail")
    builder.add_conditional_edges("guardrail", after_guardrail, ["confidence", "rca_reasoning_agent", "save_revision"])
    builder.add_edge("confidence", "save_revision")
    builder.add_edge("save_revision", END)
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()


def run_investigation(
    incident_id: str | None = None,
    owner: str = DEFAULT_OWNER,
    db_path: Path = DB_PATH,
    on_step: Callable[[InvestigationStep], None] | None = None,
    problem_id: str | None = None,
    guidance: InvestigationGuidance | None = None,
    previous_rca_id: str | None = None,
    rca_id: str | None = None,
    revision_id: str | None = None,
    on_node_start: Callable[[str], None] | None = None,
) -> RCARecord:
    """Run the whole investigation of a problem and return the saved revision.

    Give problem_id, or incident_id (the investigation then covers the whole problem of that incident):
    a new RCA starts, with the rules of problems.check_can_start. Give rca_id (previous_rca_id is its
    older name) for the next revision of an RCA the expert sent back for more details, or whose last run
    failed: the request of the expert is then an input of the run. Give revision_id for a revision already
    created. guidance is what the Problem Manager adds (notes, more services, wider windows), checked when
    the context is built. on_step is called with every step as soon as it finishes, and on_node_start with
    the name of every node LangGraph starts, so the command line and the interface can show the
    investigation while it runs.

    An error that stops the run (a provider down, a limit reached) is saved on the revision, FAILED with
    the error, and raised again: nothing is lost and the run can be started again.
    """
    inputs: InvestigationInput = {"owner": owner, "db_path": str(db_path)}
    if problem_id:
        inputs["problem_id"] = problem_id
    if incident_id:
        inputs["incident_id"] = incident_id
    if guidance is not None:
        inputs["guidance"] = guidance.model_dump()
    if rca_id or previous_rca_id:
        inputs["rca_id"] = rca_id or previous_rca_id
    if revision_id:
        inputs["revision_id"] = revision_id
    state: dict = {}
    with tracer().start_as_current_span("rca.investigation") as span:
        span.set_attribute("rca.problem_id", problem_id or "")
        span.set_attribute("rca.incident_id", incident_id or "")
        span.set_attribute("rca.owner", owner)
        try:
            for mode, chunk in graph.stream(inputs, stream_mode=["updates", "values", "tasks"]):
                if mode == "values":
                    state = chunk
                elif mode == "tasks":
                    if on_node_start is not None and "triggers" in chunk:  # a node starts (no result yet)
                        on_node_start(chunk["name"])
                elif on_step is not None:
                    for update in chunk.values():
                        for step in (update or {}).get("trace") or []:  # `start` sends None to empty the list
                            on_step(step)
        except Exception as exc:
            revision = state.get("revision")
            if revision is not None and state.get("record") is None:
                last = (state.get("trace") or [None])[-1]
                where = f" after {last.name}" if last else ""
                store.fail_revision(revision.revision_id, f"{type(exc).__name__}{where}: {exc}", db_path=db_path)
            raise
        record = state["record"]
        span.set_attribute("rca.id", record.rca_id)
        span.set_attribute("rca.status", record.status)
    return record
