"""The end-to-end investigation: one LangGraph graph, from the problem to the saved draft RCA.

The graph only routes. Every judgement is made by one of the three agents and every check by
ordinary code in the other modules; each node calls them and writes what it found into the
state. The path:

    start → similar_incidents → investigation_planner ─┬─► tools → historical_rca_agent
                                                       └─► save_rca            (escalated)

    historical_rca_agent → rca_reasoning_agent → guardrail ─┬─► confidence → save_rca
                                  ▲                         ├─► save_rca    (escalated)
                                  └─────────────────────────┘   refused: ask again with the problems

The graph ends with the draft saved as DRAFT (the Problem Manager then sends it to the expert),
or as ESCALATED. The decision of the
Technical Expert is a separate action on the saved record (steps 13-14). Pausing the graph and
resuming it after that decision is outside the MVP.

`start` builds the investigation context with code (rca/context.py): the incidents of the
problem, their services, a log window around every incident and one change window from 7 days
before the first incident. The Planner only writes the search queries, and every source is
always checked. An investigation started from an incident covers the whole problem of that
incident; the most recent incident of the problem is the reference.

`graph` is what LangGraph Studio opens (langgraph.json). `run_investigation` runs the same
graph from Python, for the command line (scripts/run_rca.py) and the interface.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import chromadb
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace

from rca import rag, storage, store
from rca.agents import historical, planner, reasoning
from rca.confidence import assess_draft, is_weakly_supported
from rca.config import DB_PATH
from rca.context import build_context, merge_guidance
from rca.evidence import EvidenceLedger, add_changes, add_dependencies, add_log_groups
from rca.guardrails import MAX_ATTEMPTS, check_draft, format_feedback, run_with_retries
from rca.llm import LLMOutputError
from rca.models import (
    AssessedHypothesis,
    DraftRCA,
    Evidence,
    Incident,
    InvestigationContext,
    InvestigationGuidance,
    InvestigationPlan,
    InvestigationStep,
    RCARecord,
    RCAStatus,
)
from rca.tools import find_changes, find_dependencies, find_logs
from rca.observability import tracer

DEFAULT_OWNER = "Problem Manager"
MAX_SIMILAR_INCIDENTS = 5
MAX_PAST_RCAS = 5
MAX_SECTION_LENGTH = 800  # characters of a past RCA section sent to the Historical RCA Agent
JUDGED_SECTIONS = ("Summary", "Root Cause")  # what the agent reads of each past RCA: the symptoms and the cause


def _add_or_clear(current: list, update: list | None) -> list:
    """Add the update to the list; None empties it, so every run starts with an empty list."""
    return [] if update is None else current + update


class InvestigationInput(TypedDict, total=False):
    """What starts an investigation: problem_id, or incident_id (the investigation then covers the
    whole problem of that incident)."""

    problem_id: str
    incident_id: str
    previous_rca_id: str  # the revision the expert sent back: this run is the next revision of its case
    guidance: dict  # models.InvestigationGuidance, optional
    owner: str
    db_path: str


class InvestigationState(InvestigationInput, total=False):
    """Everything the investigation found so far. Each node returns only the fields it changes."""

    started_at: datetime
    previous: RCARecord | None  # the revision this one answers, in a later revision of a case
    context: InvestigationContext
    incidents: list[Incident]  # the incidents of the problem, in the order they happened
    incident: Incident  # the reference incident: the most recent one
    similar_incidents: list[Incident]
    plan: InvestigationPlan
    evidence: list[Evidence]
    linked_incidents: list[str]
    draft: DraftRCA | None
    attempts: int
    problems: list[str]
    feedback: str | None
    hypotheses: list[AssessedHypothesis]
    weakly_supported: bool
    status: RCAStatus
    escalation_reason: str
    # These two are added to by several nodes, not replaced. `start` empties them.
    not_checked: Annotated[list[str], _add_or_clear]
    trace: Annotated[list[InvestigationStep], _add_or_clear]
    record: RCARecord


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _step(name: str, started_at: datetime, summary: str, **details: Any) -> InvestigationStep:
    return InvestigationStep(name=name, summary=summary, started_at=started_at, finished_at=_now(), details=details)


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


def _past_rca_candidates(plan: InvestigationPlan, before: datetime) -> list[dict[str, Any]]:
    """The past RCAs closest to the search queries of the plan, each with the text the agent judges.

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
            "metadata": {**metadata, "matched_section": item["metadata"].get("section_name"), "source_type": "rca"},
        })
    return candidates


def _incident_candidate(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.incident_id,
        "document": _incident_text(incident),
        "metadata": {
            "source_type": "incident",
            "service": incident.service,
            "detected_at": incident.detected_at.isoformat(),
        },
    }


def _add_history(ledger: EvidenceLedger, candidate: dict[str, Any], reason: str, incidents: dict[str, Incident]) -> None:
    metadata = candidate["metadata"]
    if metadata["source_type"] == "incident":
        incident = incidents[candidate["id"]]
        ledger.add(
            "HISTORICAL_INCIDENT",
            incident.incident_id,
            f"Past {incident.service} incident {incident.incident_id}, detected {incident.detected_at:%Y-%m-%d}: "
            f"{incident.title}. {incident.description} Symptoms: {'; '.join(incident.symptoms)}. "
            f"Judged similar because: {reason}",
            incident.incident_id,
            incident.detected_at,
        )
        return

    completed = metadata.get("completion_date")
    completed_at = datetime.fromtimestamp(completed, tz=timezone.utc) if isinstance(completed, (int, float)) else None
    ledger.add(
        "HISTORICAL_RCA",
        candidate["id"],
        f"Past RCA {candidate['id']} for {metadata.get('service', 'an unknown service')}"
        f"{f', completed {completed_at:%Y-%m-%d}' if completed_at else ''}. "
        f"{candidate['document']} Judged relevant because: {reason}",
        candidate["id"],
        completed_at,
    )


# --------------------------------------------------------------------------------------
# The nodes
# --------------------------------------------------------------------------------------


def start(state: InvestigationState) -> dict:
    """Build the context from the problem and start the run from a clean state. An unknown problem
    or incident stops the run.

    LangGraph Studio keeps the state of a thread between runs. Without the reset, a second run in
    the same thread would continue the attempt count, the steps and the status of the first one.
    """
    db_path = _db_path(state)
    incident_id = (state.get("incident_id") or "").strip() or None
    problem_id = (state.get("problem_id") or "").strip() or None
    guidance = InvestigationGuidance.model_validate(state["guidance"]) if state.get("guidance") else None
    previous, request, guidance_by = None, None, "Problem Manager"

    previous_id = (state.get("previous_rca_id") or "").strip()
    if previous_id:
        previous = _previous_revision(previous_id, db_path)
        # the same problem as before, the guidance of the previous revision, and what the expert added
        problem_id, incident_id = previous.problem_id, previous.incident_id
        earlier = guidance or (previous.context.guidance if previous.context else None)
        guidance = merge_guidance(earlier, previous.review.guidance)
        request = store.expert_request(previous.review)
        if previous.review.guidance:
            guidance_by = "Problem Manager and Technical Expert"

    context, incidents = build_context(db_path, incident_id=incident_id, problem_id=problem_id, guidance=guidance,
                                       expert_request=request, guidance_by=guidance_by)
    reference = incidents[-1]
    return {
        "previous": previous,
        "problem_id": context.problem_id,
        "incident_id": reference.incident_id,
        "owner": state.get("owner") or DEFAULT_OWNER,
        "context": context,
        "incidents": incidents,
        "incident": reference,
        "started_at": _now(),
        "status": "INVESTIGATING",
        "similar_incidents": [],
        "plan": None,
        "evidence": [],
        "linked_incidents": [],
        "draft": None,
        "attempts": 0,
        "problems": [],
        "feedback": None,
        "hypotheses": [],
        "weakly_supported": False,
        "escalation_reason": "",
        "record": None,
        "not_checked": None,
        "trace": None,
    }


def _previous_revision(rca_id: str, db_path: Path) -> RCARecord:
    """The revision the expert sent back. Only a request for more details continues a case, and only
    while the case has revisions left (store.MAX_REVISIONS)."""
    previous = store.get_rca(rca_id, db_path=db_path)
    if previous is None:
        raise ValueError(f"RCA '{rca_id}' was not found.")
    if previous.status != "MORE_DETAILS_REQUESTED" or previous.review is None:
        raise ValueError(f"RCA '{rca_id}' is {previous.status}: only an RCA sent back for more details gets a next revision.")
    if previous.cycle >= store.MAX_REVISIONS:
        raise ValueError(f"RCA '{rca_id}' is revision {previous.cycle}, the last of {store.MAX_REVISIONS}.")
    return previous


def similar_incidents(state: InvestigationState) -> dict:
    """RAG: the past incidents that look like the reference incident, only older than its detection.
    The incidents of the problem are not searched for: they are already part of the investigation."""
    started = _now()
    incident = state["incident"]
    members = set(state["context"].incident_ids)
    try:
        results = _search("historical_incidents", _incident_text(incident), incident.detected_at,
                          MAX_SIMILAR_INCIDENTS + len(members))
    except Exception as exc:  # Ollama or ChromaDB is not available: the investigation continues without them
        note = f"Similar past incidents could not be searched ({type(exc).__name__}: {exc})."
        return {"similar_incidents": [], "not_checked": [note], "trace": [_step("similar_incidents", started, note)]}

    found = [storage.get_incident(_db_path(state), result["id"]) for result in results if result["id"] not in members]
    similar = [item for item in found if item is not None][:MAX_SIMILAR_INCIDENTS]
    ids = [item.incident_id for item in similar]
    summary = f"Found {len(ids)} past incident(s) that look similar: {', '.join(ids)}." if ids else "No similar past incident found."
    return {"similar_incidents": similar, "trace": [_step("similar_incidents", started, summary, found=ids)]}


def investigation_planner(state: InvestigationState) -> dict:
    """Agent 1: the search queries. A refused plan is asked again with the problems, at most 3 times."""
    started = _now()
    context, incidents, similar = state["context"], state["incidents"], state["similar_incidents"]
    result = run_with_retries(
        ask=lambda feedback: planner.plan_investigation(context, incidents, similar, feedback),
        check=lambda plan: [],  # the plan is checked inside plan_investigation
    )
    attempts = [{"attempt": attempt.number, "problems": attempt.problems} for attempt in result.attempts]

    if result.escalated:
        reason = f"The Investigation Planner did not produce a valid plan in {len(result.attempts)} attempts."
        return {
            "status": "ESCALATED",
            "escalation_reason": reason,
            "trace": [_step("investigation_planner", started, reason, attempts=attempts)],
        }

    plan = result.value
    summary = (
        f"Plan: {plan.service}, {plan.window_start:%Y-%m-%d %H:%M} to {plan.window_end:%Y-%m-%d %H:%M} UTC, "
        f"sources: {', '.join(plan.sources)}."
    )
    return {
        "plan": plan,
        "trace": [_step(
            "investigation_planner", started, summary,
            attempts=attempts, search_queries=plan.search_queries, rationale=plan.rationale,
        )],
    }


def after_planner(state: InvestigationState) -> Literal["tools", "save_rca"]:
    return "save_rca" if state.get("status") == "ESCALATED" else "tools"


def tools(state: InvestigationState) -> dict:
    """The deterministic tools on every source, with the services and the windows of the context.
    Every fact goes into the ledger; the step records what was searched and what was found."""
    started = _now()
    db_path = _db_path(state)
    context, plan, incidents = state["context"], state["plan"], state["incidents"]
    by_id = {item.incident_id: item for item in incidents}
    several = len(incidents) > 1
    ledger = EvidenceLedger()
    not_checked: list[str] = []
    found: dict[str, list[str]] = {}

    dependencies = []
    for service in context.services:
        with tracer().start_as_current_span("tool.find_dependencies") as span:
            span.set_attribute("tool.service", service)
            result = find_dependencies(service, db_path=db_path)
            span.set_attribute("tool.result_count", len(result.components))
        if not result.components:
            not_checked.append(f"The CMDB has no components for {service}, so its dependencies are unknown.")
        dependencies.append(result)

    found["logs"] = []
    for window in context.log_windows:
        incident = by_id[window.incident_id]
        for service in context.services:
            with tracer().start_as_current_span("tool.find_logs") as span:
                span.set_attribute("tool.service", service)
                span.set_attribute("tool.window_start", window.start.isoformat())
                span.set_attribute("tool.window_end", window.end.isoformat())
                groups = find_logs(service, window.start, window.end, db_path=db_path)
                span.set_attribute("tool.result_count", len(groups))
            add_log_groups(ledger, groups, incident.detected_at,
                           f"the detection of {incident.incident_id}" if several else "detection")
            found["logs"] += [group.examples[0].log_id for group in groups]

    first, window = incidents[0], context.change_window
    services = [*context.services, *context.related_services]
    with tracer().start_as_current_span("tool.find_changes") as span:
        span.set_attribute("tool.services", services)
        span.set_attribute("tool.window_start", window.start.isoformat())
        span.set_attribute("tool.window_end", window.end.isoformat())
        changes = find_changes(services, window.start, window.end, db_path=db_path)
        span.set_attribute("tool.result_count", len(changes))
    add_changes(ledger, changes, first.detected_at,
                f"the first incident of the problem ({first.incident_id})" if several else "detection")
    found["changes"] = [item.change_id for item in changes]

    for result in dependencies:
        add_dependencies(ledger, result)
    found["cmdb"] = list(dict.fromkeys(item.depends_on.ci_id for result in dependencies for item in result.dependencies))

    # The other incidents of the problem are facts too: the same failure, seen again.
    found["problem_incidents"] = []
    for item in incidents:
        if item.incident_id == context.reference_incident_id:
            continue
        ledger.add(
            "HISTORICAL_INCIDENT",
            item.incident_id,
            f"Incident {item.incident_id} of the same problem {context.problem_id}, {item.service}, detected "
            f"{item.detected_at:%Y-%m-%d %H:%M} UTC: {item.title}. {item.description} Symptoms: {'; '.join(item.symptoms)}.",
            item.incident_id,
            item.detected_at,
        )
        found["problem_incidents"].append(item.incident_id)

    summary = (
        f"Logs: {len(found['logs'])} ERROR/WARN pattern(s) around {len(context.log_windows)} incident(s). "
        f"Changes: {len(found['changes'])} from {window.start:%Y-%m-%d} to {window.end:%Y-%m-%d} "
        f"({', '.join(found['changes']) or 'none'}). CMDB: {len(found['cmdb'])} component(s) depended on."
    )
    if found["problem_incidents"]:
        summary += f" Other incidents of the problem: {', '.join(found['problem_incidents'])}."
    span = trace.get_current_span()
    span.set_attribute("rca.evidence_ids", [item.evidence_id for item in ledger.items()])
    span.set_attribute("rca.sources_run", list(plan.sources))
    return {
        "evidence": ledger.items(),
        "not_checked": not_checked,
        "trace": [_step(
            "tools", started, summary,
            evidence=len(ledger),
            services=services,
            log_windows=[_window(item.start, item.end, item.incident_id) for item in context.log_windows],
            change_window=_window(window.start, window.end),
            found=found,
        )],
    }


def historical_rca_agent(state: InvestigationState) -> dict:
    """Agent 2: RAG over past RCAs, then the agent keeps only what is really similar."""
    started = _now()
    incident, plan = state["incident"], state["plan"]
    ledger = EvidenceLedger(state["evidence"])
    not_checked: list[str] = []
    candidates: list[dict[str, Any]] = []

    if "historical_rcas" in plan.sources:
        try:
            candidates += _past_rca_candidates(plan, incident.detected_at)
        except Exception as exc:  # Ollama or ChromaDB is not available: the investigation continues without them
            not_checked.append(f"Past RCAs could not be searched ({type(exc).__name__}: {exc}).")
    else:
        not_checked.append(_not_chosen("Past RCAs"))

    if "historical_incidents" in plan.sources:
        candidates += [_incident_candidate(item) for item in state["similar_incidents"]]
    else:
        not_checked.append(_not_chosen("Past incidents"))

    if not candidates:
        return {
            "linked_incidents": [],
            "not_checked": not_checked,
            "trace": [_step("historical_rca_agent", started, "No past RCA or incident to review.")],
        }

    try:
        # The agent also returns its own evidence list; the pipeline uses only its decisions and
        # records the kept results in the shared ledger, so the evidence ids stay unique.
        review, _ = historical.review_historical_rcas(plan, candidates)
    except LLMOutputError as exc:
        note = f"The Historical RCA Agent did not return a valid answer, so past RCAs and incidents were not used ({exc})."
        return {
            "linked_incidents": [],
            "not_checked": [*not_checked, note],
            "trace": [_step("historical_rca_agent", started, note)],
        }

    decisions = {decision.citation: decision for decision in review.decisions}
    incidents = {item.incident_id: item for item in state["similar_incidents"]}
    kept: list[dict[str, str]] = []
    dropped: list[dict[str, str]] = []
    for candidate in candidates:
        decision = decisions.get(candidate["id"])
        if decision is None:
            dropped.append({"id": candidate["id"], "reason": "The agent gave no decision for this result."})
        elif not decision.relevant:
            dropped.append({"id": candidate["id"], "reason": decision.reason})
        else:
            kept.append({"id": candidate["id"], "reason": decision.reason})
            _add_history(ledger, candidate, decision.reason, incidents)

    kept_ids = [item["id"] for item in kept]
    summary = f"Kept {', '.join(kept_ids) or 'nothing'}. Dropped {', '.join(item['id'] for item in dropped) or 'nothing'}."
    return {
        "evidence": ledger.items(),
        "linked_incidents": [item_id for item_id in kept_ids if item_id in incidents],
        "not_checked": not_checked,
        "trace": [_step("historical_rca_agent", started, summary, kept=kept, dropped=dropped)],
    }


def rca_reasoning_agent(state: InvestigationState) -> dict:
    """Agent 3: the draft, from the evidence ledger only. On a retry it also gets the problems."""
    started = _now()
    attempt = state.get("attempts", 0) + 1
    try:
        draft = reasoning.propose_draft(state["incident_id"], state["evidence"], state.get("feedback"),
                                        state["context"].expert_request)
    except LLMOutputError as exc:
        return {
            "attempts": attempt,
            "draft": None,
            "problems": [str(exc)],
            "trace": [_step("rca_reasoning_agent", started, f"Attempt {attempt}: the answer is not a valid draft.")],
        }
    summary = f"Attempt {attempt}: {len(draft.hypotheses)} hypothesis(es) proposed."
    span = trace.get_current_span()
    span.set_attribute("rca.attempt", attempt)
    span.set_attribute("rca.hypotheses_count", len(draft.hypotheses))
    span.set_attribute("rca.top_hypothesis", draft.hypotheses[0].candidate_root_cause if draft.hypotheses else "")
    return {"attempts": attempt, "draft": draft, "problems": [], "trace": [_step("rca_reasoning_agent", started, summary)]}


def guardrail(state: InvestigationState) -> dict:
    """The checks on the draft: accept it, ask again with the problems, or escalate after 3 attempts."""
    started = _now()
    attempt, draft = state["attempts"], state.get("draft")
    evidence_ids = {item.evidence_id for item in state["evidence"]}
    problems = state["problems"] if draft is None else check_draft(draft, evidence_ids)

    if not problems:
        cited = {item for hypothesis in draft.hypotheses for item in hypothesis.supporting_evidence + hypothesis.contradicting_evidence}
        summary = f"Draft accepted on attempt {attempt}: the schema is valid and all {len(cited)} cited evidence ids exist."
        trace.get_current_span().set_attribute("rca.guardrail", "accepted")
        return {"feedback": None, "trace": [_step("guardrail", started, summary, attempt=attempt)]}

    if attempt >= MAX_ATTEMPTS:
        reason = f"The RCA Reasoning Agent did not produce a valid draft in {attempt} attempts."
        trace.get_current_span().set_attribute("rca.guardrail", "escalated")  # linia ~455
        return {
            "status": "ESCALATED",
            "escalation_reason": reason,
            "trace": [_step("guardrail", started, f"Draft refused. {reason} Escalated.", attempt=attempt, problems=problems)],
        }

    summary = f"Draft refused on attempt {attempt}; asking again with the problems."
    trace.get_current_span().set_attribute("rca.guardrail", "retry")    
    return {
        "feedback": format_feedback(problems),
        "trace": [_step("guardrail", started, summary, attempt=attempt, problems=problems)],
    }


def after_guardrail(state: InvestigationState) -> Literal["confidence", "rca_reasoning_agent", "save_rca"]:
    if state.get("status") == "ESCALATED":
        return "save_rca"
    return "rca_reasoning_agent" if state.get("feedback") else "confidence"


def confidence(state: InvestigationState) -> dict:
    """The rules: HIGH / MEDIUM / LOW for each hypothesis, and the weakly supported mark."""
    started = _now()
    # without log evidence, the first error is the detection of the first incident of the problem
    hypotheses = assess_draft(state["draft"], state["evidence"], state["incidents"][0].detected_at)
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
        "status": "PENDING_REVIEW",
        "trace": [_step("confidence", started, summary)],
    }


def save_rca(state: InvestigationState) -> dict:
    """Save the RCA record: the draft result, or the escalated case.

    A finished investigation is stored as DRAFT: the Problem Manager sends it to the
    Technical Expert explicitly (store.submit_for_review), never automatically.
    """
    db_path = _db_path(state)
    now = _now()
    draft = state["draft"] if state["status"] == "PENDING_REVIEW" else None
    if draft is not None:
        state["status"] = "DRAFT"

    record = RCARecord(
        rca_id=store.next_rca_id(now.year, db_path=db_path),
        incident_id=state["incident_id"],
        status=state["status"],
        owner=state["owner"],
        created_at=state["started_at"],
        duration_seconds=round((now - state["started_at"]).total_seconds(), 1),
        linked_incidents=state.get("linked_incidents", []),
        problem_id=state.get("problem_id"),
        context=state.get("context"),
        plan=state.get("plan"),
        evidence=state.get("evidence", []),
        trace=state["trace"],
        investigation_summary=draft.investigation_summary if draft else state.get("escalation_reason", ""),
        observed_patterns=draft.observed_patterns if draft else [],
        hypotheses=state.get("hypotheses", []) if draft else [],
        single_hypothesis_reason=draft.single_hypothesis_reason if draft else None,
        not_checked=state["not_checked"] + (draft.not_checked if draft else []),
        weakly_supported=state.get("weakly_supported", False),
        suggested_workaround=draft.suggested_workaround if draft else None,
        change_likely_required=draft.change_likely_required if draft else False,
    )
    previous = state.get("previous")
    if previous is not None:
        # the next revision of the same case, linked here and not by the interface after the run
        record.case_id, record.cycle, record.parent_rca_id = previous.case, previous.cycle + 1, previous.rca_id
        if previous.case_id is None:
            previous.case_id = previous.case
            store.save_rca(previous, db_path=db_path)
    store.save_rca(record, db_path=db_path)
    return {"record": record}


# --------------------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------------------


def build_graph(checkpointer=None):
    """The compiled graph. The checkpointer keeps the state between runs (Studio adds its own)."""
    builder = StateGraph(InvestigationState, input_schema=InvestigationInput)
    for node in (start, similar_incidents, investigation_planner, tools, historical_rca_agent,
                 rca_reasoning_agent, guardrail, confidence, save_rca):
        builder.add_node(node.__name__, node)

    builder.add_edge(START, "start")
    builder.add_edge("start", "similar_incidents")
    builder.add_edge("similar_incidents", "investigation_planner")
    builder.add_conditional_edges("investigation_planner", after_planner, ["tools", "save_rca"])
    builder.add_edge("tools", "historical_rca_agent")
    builder.add_edge("historical_rca_agent", "rca_reasoning_agent")
    builder.add_edge("rca_reasoning_agent", "guardrail")
    builder.add_conditional_edges("guardrail", after_guardrail, ["confidence", "rca_reasoning_agent", "save_rca"])
    builder.add_edge("confidence", "save_rca")
    builder.add_edge("save_rca", END)
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
) -> RCARecord:
    """Run the whole investigation for a problem and return the saved RCA record.

    Give problem_id, or incident_id: the investigation then covers the whole problem of that incident
    (or the incident alone, when it belongs to no problem). guidance is what the Problem Manager adds
    (notes, more services, wider windows), checked when the context is built. previous_rca_id is an RCA
    the expert sent back for more details: the run is then the next revision of its case, with the
    request of the expert as input. on_step is called with every step as soon
    as it finishes, so the command line and the interface can show the investigation while it runs.
    """
    inputs: InvestigationInput = {"owner": owner, "db_path": str(db_path)}
    if problem_id:
        inputs["problem_id"] = problem_id
    if incident_id:
        inputs["incident_id"] = incident_id
    if guidance is not None:
        inputs["guidance"] = guidance.model_dump()
    if previous_rca_id:
        inputs["previous_rca_id"] = previous_rca_id
    state: dict = {}
    with tracer().start_as_current_span("rca.investigation") as span:
        span.set_attribute("rca.problem_id", problem_id or "")
        span.set_attribute("rca.incident_id", incident_id or "")
        span.set_attribute("rca.owner", owner)
        for mode, chunk in graph.stream(inputs, stream_mode=["updates", "values"]):
            if mode == "values":
                state = chunk
            elif on_step is not None:
                for update in chunk.values():
                    for step in (update or {}).get("trace") or []:  # `start` sends None to empty the list
                        on_step(step)
        record = state["record"]
        span.set_attribute("rca.id", record.rca_id)
        span.set_attribute("rca.status", record.status)
    return record
