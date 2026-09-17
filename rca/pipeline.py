"""The end-to-end investigation: one LangGraph graph, from the incident to the saved draft RCA.

The graph only routes. Every judgement is made by one of the three agents and every check by
ordinary code in the other modules; each node calls them and writes what it found into the
state. The path:

    start → similar_incidents → investigation_planner ─┬─► tools → historical_rca_agent
                                                       └─► save_rca            (escalated)

    historical_rca_agent → rca_reasoning_agent → guardrail ─┬─► confidence → save_rca
                                  ▲                         ├─► save_rca    (escalated)
                                  └─────────────────────────┘   refused: ask again with the problems

The graph ends with the draft saved as PENDING_REVIEW, or as ESCALATED. The decision of the
Technical Expert is a separate action on the saved record (steps 13-14). Pausing the graph and
resuming it after that decision is outside the MVP.

`graph` is what LangGraph Studio opens (langgraph.json). `run_investigation` runs the same
graph from Python, for the command line (scripts/run_rca.py) and the interface.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import chromadb
from langgraph.graph import END, START, StateGraph

from rca import rag, storage, store
from rca.agents import historical, planner, reasoning
from rca.confidence import assess_draft, is_weakly_supported
from rca.config import DB_PATH
from rca.evidence import EvidenceLedger, add_changes, add_dependencies, add_log_groups
from rca.guardrails import MAX_ATTEMPTS, check_draft, format_feedback, run_with_retries
from rca.llm import LLMOutputError
from rca.models import (
    AssessedHypothesis,
    DraftRCA,
    Evidence,
    Incident,
    InvestigationPlan,
    InvestigationStep,
    RCARecord,
    RCAStatus,
)
from rca.tools import find_changes, find_dependencies, find_logs

DEFAULT_OWNER = "Problem Manager"
MAX_SIMILAR_INCIDENTS = 5
MAX_PAST_RCAS = 5
MAX_SECTION_LENGTH = 800  # characters of a past RCA section sent to the Historical RCA Agent
JUDGED_SECTIONS = ("Summary", "Root Cause")  # what the agent reads of each past RCA: the symptoms and the cause


def _add_or_clear(current: list, update: list | None) -> list:
    """Add the update to the list; None empties it, so every run starts with an empty list."""
    return [] if update is None else current + update


class InvestigationInput(TypedDict, total=False):
    """What starts an investigation. Only incident_id is required."""

    incident_id: str
    owner: str
    db_path: str


class InvestigationState(InvestigationInput, total=False):
    """Everything the investigation found so far. Each node returns only the fields it changes."""

    started_at: datetime
    incident: Incident
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
    """Load the incident and start the run from a clean state. An unknown incident stops the run.

    LangGraph Studio keeps the state of a thread between runs. Without the reset, a second run in
    the same thread would continue the attempt count, the steps and the status of the first one.
    """
    db_path = _db_path(state)
    incident_id = (state.get("incident_id") or "").strip()
    incident = storage.get_incident(db_path, incident_id)
    if incident is None:
        raise ValueError(f"Incident '{incident_id}' was not found in {db_path}.")
    return {
        "incident_id": incident.incident_id,
        "owner": state.get("owner") or DEFAULT_OWNER,
        "incident": incident,
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


def similar_incidents(state: InvestigationState) -> dict:
    """RAG: the past incidents that look like this one, only older than its detection."""
    started = _now()
    incident = state["incident"]
    try:
        results = _search("historical_incidents", _incident_text(incident), incident.detected_at, MAX_SIMILAR_INCIDENTS)
    except Exception as exc:  # Ollama or ChromaDB is not available: the investigation continues without them
        note = f"Similar past incidents could not be searched ({type(exc).__name__}: {exc})."
        return {"similar_incidents": [], "not_checked": [note], "trace": [_step("similar_incidents", started, note)]}

    found = [storage.get_incident(_db_path(state), result["id"]) for result in results]
    similar = [item for item in found if item is not None]
    ids = [item.incident_id for item in similar]
    summary = f"Found {len(ids)} past incident(s) that look similar: {', '.join(ids)}." if ids else "No similar past incident found."
    return {"similar_incidents": similar, "trace": [_step("similar_incidents", started, summary, found=ids)]}


def investigation_planner(state: InvestigationState) -> dict:
    """Agent 1: the plan. A refused plan is asked again with the problems, at most 3 times."""
    started = _now()
    incident, similar = state["incident"], state["similar_incidents"]
    result = run_with_retries(
        ask=lambda feedback: planner.plan_investigation(incident, similar, feedback),
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
    """The deterministic tools, only for the sources the plan chose. Every fact goes into the ledger."""
    started = _now()
    db_path = _db_path(state)
    incident, plan = state["incident"], state["plan"]
    ledger = EvidenceLedger()
    not_checked: list[str] = []
    found: list[str] = []

    # The CMDB runs first: its dependencies say which other services the change lookup covers.
    dependencies = None
    if "cmdb" in plan.sources:
        dependencies = find_dependencies(plan.service, db_path=db_path)
        plan = plan.model_copy(update={"related_services": dependencies.related_services})
        if not dependencies.components:
            not_checked.append(f"The CMDB has no components for {plan.service}, so its dependencies are unknown.")
    else:
        not_checked.append(_not_chosen("CMDB dependencies") + " Changes on dependent services were not searched.")

    if "logs" in plan.sources:
        groups = find_logs(plan.service, plan.window_start, plan.window_end, db_path=db_path)
        add_log_groups(ledger, groups, incident.detected_at)
        found.append(f"Logs: {len(groups)} ERROR/WARN pattern(s).")
    else:
        not_checked.append(_not_chosen("Logs"))

    if "changes" in plan.sources:
        services = [plan.service, *plan.related_services]
        changes = find_changes(services, plan.window_start, plan.window_end, db_path=db_path)
        add_changes(ledger, changes, incident.detected_at)
        found.append(f"Changes: {len(changes)} in the window ({', '.join(item.change_id for item in changes) or 'none'}).")
    else:
        not_checked.append(_not_chosen("Changes"))

    if dependencies is not None:
        add_dependencies(ledger, dependencies)
        found.append(f"CMDB: {len(dependencies.dependencies)} direct dependenc(ies).")

    summary = " ".join(found) or "No tool was run."
    return {
        "plan": plan,
        "evidence": ledger.items(),
        "not_checked": not_checked,
        "trace": [_step("tools", started, summary, evidence=len(ledger))],
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
        draft = reasoning.propose_draft(state["incident_id"], state["evidence"], state.get("feedback"))
    except LLMOutputError as exc:
        return {
            "attempts": attempt,
            "draft": None,
            "problems": [str(exc)],
            "trace": [_step("rca_reasoning_agent", started, f"Attempt {attempt}: the answer is not a valid draft.")],
        }
    summary = f"Attempt {attempt}: {len(draft.hypotheses)} hypothesis(es) proposed."
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
        return {"feedback": None, "trace": [_step("guardrail", started, summary, attempt=attempt)]}

    if attempt >= MAX_ATTEMPTS:
        reason = f"The RCA Reasoning Agent did not produce a valid draft in {attempt} attempts."
        return {
            "status": "ESCALATED",
            "escalation_reason": reason,
            "trace": [_step("guardrail", started, f"Draft refused. {reason} Escalated.", attempt=attempt, problems=problems)],
        }

    summary = f"Draft refused on attempt {attempt}; asking again with the problems."
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
    hypotheses = assess_draft(state["draft"], state["evidence"], state["incident"].detected_at)
    weak = is_weakly_supported(hypotheses)
    summary = " ".join(f"{item.hypothesis_id}: {item.confidence} ({item.confidence_points} points)." for item in hypotheses)
    if weak:
        summary += " No hypothesis is above LOW: weakly supported, more evidence is recommended before approval."
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
    incident_id: str,
    owner: str = DEFAULT_OWNER,
    db_path: Path = DB_PATH,
    on_step: Callable[[InvestigationStep], None] | None = None,
) -> RCARecord:
    """Run the whole investigation for one incident and return the saved RCA record.

    on_step is called with every step as soon as it finishes, so the command line and the
    interface can show the investigation while it runs.
    """
    inputs: InvestigationInput = {"incident_id": incident_id, "owner": owner, "db_path": str(db_path)}
    state: dict = {}
    for mode, chunk in graph.stream(inputs, stream_mode=["updates", "values"]):
        if mode == "values":
            state = chunk
        elif on_step is not None:
            for update in chunk.values():
                for step in (update or {}).get("trace") or []:  # `start` sends None to empty the list
                    on_step(step)
    return state["record"]
