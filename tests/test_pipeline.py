"""Tests for rca.pipeline: the whole investigation, from the problem to the saved draft.

The case is the Payment API problem: INC-2026-00482 (14 July) and its recurrence INC-2026-00857
(15 July, the reference incident). Starting from INC-2026-00482 investigates the whole problem.

Offline, the three agents and the ChromaDB search are replaced with fixed answers; the tools,
the ledger, the guardrail, the confidence rules and the store are the real code, on the mock
data loaded into a temporary SQLite database. The live test runs everything for real:
GROQ_MODEL=openai/gpt-oss-20b python -m pytest -m live tests/test_pipeline.py -s
"""

from datetime import datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from rca import config, pipeline, storage, store
from rca.agents import historical, planner, reasoning
from rca.agents.historical import HistoricalRCADecision, HistoricalRCAReview
from rca.agents.planner import PlannerAnswer
from rca.llm import LLMOutputError
from rca.models import DraftRCA, Hypothesis

ROOT = Path(__file__).resolve().parents[1]
INCIDENT_ID = "INC-2026-00482"
REFERENCE_ID = "INC-2026-00857"  # the most recent incident of the problem
REFERENCE_DETECTED = "2026-07-15T09:48:00+00:00"
PAYMENT_RCA_DATE = 1763647200  # 2025-11-20


def results(*rows):
    """What rca.rag.query_collection returns: one dict per record, the closest first."""
    return [
        {"id": row[0], "document": row[1], "metadata": row[2], "score": row[3]}
        for row in rows
    ]


INCIDENT_RESULTS = results(
    ("INC-2025-00401", "Payment API card authorisation slow", {"service": "Payment API"}, 0.11),
    ("INC-2026-00106", "Billing Service batch failure", {"service": "Billing Service"}, 0.26),
)
# As in a real run: the closest section of the Payment API RCA is its Timeline, which has no symptoms.
RCA_RESULTS = results(
    ("RCA-2025-00114::Timeline", "13:58 UTC: Release deployment completed on Payment API pods.",
     {"document_id": "RCA-2025-00114", "section_name": "Timeline", "service": "Payment API",
      "completion_date": PAYMENT_RCA_DATE}, 0.25),
    ("RCA-2025-00042::Timeline", "Payroll batch waits on PostgreSQL connections.",
     {"document_id": "RCA-2025-00042", "section_name": "Timeline", "service": "Payroll Service",
      "completion_date": 1750000000}, 0.30),
)


# The sections read from the index for the RCAs found. RCA-2025-00042 has none, to test the fallback.
RCA_SECTIONS = {
    "RCA-2025-00114": {
        "Summary": "Intermittent HTTP 500 errors and latency above 5 seconds.",
        "Timeline": "13:58 UTC: Release deployment completed on Payment API pods.",
        "Root Cause": "Connection pool exhaustion from unclosed SQL sessions in the retry handler.",
    },
}


def plan_answer(queries=("payment requests fail with database connection timeouts",)) -> PlannerAnswer:
    return PlannerAnswer(search_queries=list(queries), rationale="Both incidents show database connection timeouts.")


HISTORY_REVIEW = HistoricalRCAReview(decisions=[
    HistoricalRCADecision(citation="RCA-2025-00114", relevant=True, reason="Same service and same symptoms."),
    HistoricalRCADecision(citation="RCA-2025-00042", relevant=False, reason="Payroll Service, a different service."),
    HistoricalRCADecision(citation="INC-2025-00401", relevant=True, reason="Same service, same timeouts."),
    HistoricalRCADecision(citation="INC-2026-00106", relevant=False, reason="Billing Service, a different failure."),
])


def hypothesis(hypothesis_id, supporting, contradicting=()) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        candidate_root_cause="A candidate cause.",
        reasons=["A reason."],
        supporting_evidence=list(supporting),
        contradicting_evidence=list(contradicting),
        recommended_validation=["A check."],
    )


def draft(*hypotheses: Hypothesis) -> DraftRCA:
    return DraftRCA(
        incident_id=INCIDENT_ID,
        investigation_summary="The deploy is followed by connection pool timeouts.",
        observed_patterns=["Timeouts start 7 minutes after the deploy."],
        hypotheses=list(hypotheses),
        not_checked=["No database metrics."],
        suggested_workaround="Raise the pool size.",
        change_likely_required=True,
    )


# The ledger of the problem: EV-001..002 logs around INC-2026-00482, EV-003..004 logs around INC-2026-00857,
# EV-005..008 changes (EV-006 the deploy CHG-2026-00871), EV-009..010 CMDB, EV-011 INC-2026-00482 (same
# problem), EV-012 RCA-2025-00114, EV-013 INC-2025-00401.
LEDGER = [
    "LOG-PAY-20260714-14", "LOG-PAY-20260714-15", "LOG-PAY-20260715-06", "LOG-PAY-20260715-01",
    "CHG-2026-00845", "CHG-2026-00871", "CHG-2026-00873", "CHG-2026-00876",
    "CI-PAYMENT-DB", "CI-PAYMENT-QUEUE", "INC-2026-00482", "RCA-2025-00114", "INC-2025-00401",
]
GOOD_DRAFT = draft(
    hypothesis("HYP-001", ["EV-001", "EV-002", "EV-006", "EV-009", "EV-012", "EV-013"]),
    hypothesis("HYP-002", ["EV-001", "EV-009"], contradicting=["EV-012"]),
)
TOOLS_ONLY_DRAFT = draft(hypothesis("HYP-001", ["EV-001", "EV-006"]), hypothesis("HYP-002", ["EV-003"]))
INVENTED_DRAFT = draft(hypothesis("HYP-001", ["EV-099"]), hypothesis("HYP-002", ["EV-001"]))


class Fake:
    """Replaces ask_json: returns the given answers in order (the last one again when they run out)
    and remembers every request."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests: list[str] = []

    def __call__(self, instructions, user_input, schema):
        self.requests.append(user_input)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "rca.sqlite3"
    storage.load_sources(path, ROOT / "data" / "sources")
    return path


@pytest.fixture
def fakes(monkeypatch):
    """The Payment API case with well-behaved agents. A test can replace any of the answers."""

    class Fakes:
        search_calls: list[str] = []
        search_error: Exception | None = None
        planner = Fake(plan_answer())
        historical = Fake(HISTORY_REVIEW)
        reasoning = Fake(GOOD_DRAFT)

    def fake_query_collection(collection_name, query_text, limit=5, before_timestamp=None, **kwargs):
        Fakes.search_calls.append(collection_name)
        if Fakes.search_error:
            raise Fakes.search_error
        assert before_timestamp == int(datetime.fromisoformat(REFERENCE_DETECTED).timestamp())
        return INCIDENT_RESULTS if collection_name == "historical_incidents" else RCA_RESULTS

    monkeypatch.setattr(pipeline.rag, "query_collection", fake_query_collection)
    monkeypatch.setattr(pipeline, "_rca_sections", lambda rca_ids: {key: RCA_SECTIONS[key] for key in rca_ids if key in RCA_SECTIONS})
    monkeypatch.setattr(planner, "ask_json", lambda *args: Fakes.planner(*args))
    monkeypatch.setattr(historical, "ask_json", lambda *args, **kwargs: Fakes.historical(*kwargs.values()))
    monkeypatch.setattr(reasoning, "ask_json", lambda *args: Fakes.reasoning(*args))
    return Fakes


def run(db_path):
    steps = []
    record = pipeline.run_investigation(INCIDENT_ID, owner="Test Manager", db_path=db_path, on_step=steps.append)
    return record, steps


# The normal path -----------------------------------------------------------------------


def test_the_payment_api_draft_is_built_and_saved(db_path, fakes):
    record, steps = run(db_path)

    assert record.status == "DRAFT"  # the Problem Manager sends it to the expert, never the graph
    assert record.rca_id == f"RCA-{datetime.now().year}-00001"
    assert record.owner == "Test Manager"
    assert record.incident_id == REFERENCE_ID
    assert record.problem_id == storage.get_problem_id_for_incident(db_path, INCIDENT_ID)
    assert record.context.incident_ids == [INCIDENT_ID, REFERENCE_ID]
    assert [item.citation for item in record.evidence] == LEDGER
    assert [(item.hypothesis_id, item.confidence, item.confidence_points) for item in record.hypotheses] == [
        ("HYP-001", "HIGH", 8), ("HYP-002", "LOW", 3),
    ]
    assert record.linked_incidents == ["INC-2025-00401"]
    assert record.not_checked == ["No database metrics."]
    assert record.final_root_cause is None and record.review is None
    assert record.duration_seconds is not None
    assert store.get_rca(record.rca_id, db_path=db_path) == record


def test_the_steps_are_reported_in_order_as_they_finish(db_path, fakes):
    record, steps = run(db_path)

    names = ["similar_incidents", "investigation_planner", "tools", "historical_rca_agent",
             "rca_reasoning_agent", "guardrail", "confidence"]
    assert [step.name for step in steps] == names
    assert steps == record.trace


def test_the_plan_takes_its_window_from_the_context_and_the_queries_from_the_planner(db_path, fakes):
    record, steps = run(db_path)

    assert record.plan.window_start == record.context.change_window.start
    assert record.plan.search_queries == ["payment requests fail with database connection timeouts"]
    assert fakes.search_calls == ["historical_incidents", "historical_rcas"]  # one RCA search per query
    history_request = fakes.historical.requests[0]
    # Cited by the RCA id, not by the section, and sent once.
    assert history_request.count('"citation": "RCA-2025-00114"') == 1


def test_the_agent_judges_the_summary_and_root_cause_not_only_the_closest_section(db_path, fakes):
    run(db_path)

    history_request = fakes.historical.requests[0]
    assert "Summary: Intermittent HTTP 500 errors and latency above 5 seconds." in history_request
    assert "Root Cause: Connection pool exhaustion" in history_request
    assert "13:58 UTC" not in history_request  # the Timeline that matched is not the text judged
    assert '"matched_section": "Timeline"' in history_request
    assert "Payroll batch waits on PostgreSQL connections." in history_request  # no sections: closest one
    assert "INC-2025-00401" in history_request


def test_the_distractors_do_not_become_evidence(db_path, fakes):
    record, _ = run(db_path)

    citations = {item.citation for item in record.evidence}
    assert "RCA-2025-00042" not in citations and "INC-2026-00106" not in citations
    history_step = record.trace[3]
    assert [item["id"] for item in history_step.details["dropped"]] == ["RCA-2025-00042", "INC-2026-00106"]


def test_the_reasoning_agent_receives_the_ledger_with_times_relative_to_the_incidents(db_path, fakes):
    run(db_path)

    request = fakes.reasoning.requests[0]
    # the deploy CHG-2026-00871 at 13:58, 34 minutes before the first incident at 14:32
    assert "34 minutes before the first incident of the problem (INC-2026-00482)" in request
    assert "before the detection of INC-2026-00857" in request  # a log line of the recurrence
    assert "Judged relevant because: Same service and same symptoms." in request


# The context fixes what is searched -----------------------------------------------------


def test_every_source_is_checked_around_every_incident_of_the_problem(db_path, fakes):
    record, _ = run(db_path)

    tools_step = record.trace[2]
    assert [window["incident_id"] for window in tools_step.details["log_windows"]] == [INCIDENT_ID, REFERENCE_ID]
    assert set(tools_step.details["found"]) == {"logs", "changes", "cmdb", "problem_incidents"}
    assert tools_step.details["found"]["problem_incidents"] == [INCIDENT_ID]
    # the change on the API Gateway is not on the Payment API or a service it depends on
    assert "CHG-2026-00872" not in tools_step.details["found"]["changes"]
    assert record.plan.sources == ["logs", "changes", "cmdb", "historical_rcas", "historical_incidents"]
    assert not any("were not checked" in item for item in record.not_checked)


def test_the_incidents_of_the_problem_are_not_searched_as_similar_incidents(db_path, fakes, monkeypatch):
    member = results((INCIDENT_ID, "Payment API intermittent failures", {"service": "Payment API"}, 0.05))
    original = pipeline.rag.query_collection
    monkeypatch.setattr(pipeline.rag, "query_collection",
                        lambda name, *args, **kwargs: member + original(name, *args, **kwargs) if name == "historical_incidents"
                        else original(name, *args, **kwargs))

    record, _ = run(db_path)

    assert INCIDENT_ID not in record.trace[0].details["found"]


def test_the_investigation_continues_when_the_search_is_down(db_path, fakes):
    fakes.search_error = RuntimeError("Unable to generate embeddings via Ollama.")
    fakes.reasoning = Fake(TOOLS_ONLY_DRAFT)

    record, _ = run(db_path)

    assert record.status == "DRAFT"
    assert fakes.historical.requests == []
    assert "Similar past incidents could not be searched" in record.not_checked[0]
    assert "Past RCAs could not be searched" in record.not_checked[1]


# The guardrail loop and the escalations -------------------------------------------------


def test_a_refused_draft_is_asked_again_with_the_problems(db_path, fakes):
    fakes.reasoning = Fake(LLMOutputError("The answer is not valid JSON.", "not json"), INVENTED_DRAFT, GOOD_DRAFT)

    record, _ = run(db_path)

    assert record.status == "DRAFT"
    assert [step.name for step in record.trace[4:]] == [
        "rca_reasoning_agent", "guardrail", "rca_reasoning_agent", "guardrail",
        "rca_reasoning_agent", "guardrail", "confidence",
    ]
    assert "Your previous answer was refused" not in fakes.reasoning.requests[0]
    assert "not valid JSON" in fakes.reasoning.requests[1]
    assert "EV-099" in fakes.reasoning.requests[2]


def test_three_refused_drafts_escalate_and_the_case_is_saved(db_path, fakes):
    fakes.reasoning = Fake(INVENTED_DRAFT)

    record, _ = run(db_path)

    assert record.status == "ESCALATED"
    assert len(fakes.reasoning.requests) == 3
    assert record.hypotheses == []
    assert "did not produce a valid draft in 3 attempts" in record.investigation_summary
    assert store.list_rcas("ESCALATED", db_path=db_path) == [record]


def test_a_plan_refused_three_times_escalates_before_any_tool(db_path, fakes):
    fakes.planner = Fake(plan_answer(queries=[" "]))

    record, _ = run(db_path)

    assert record.status == "ESCALATED"
    assert len(fakes.planner.requests) == 3
    assert "search_queries" in fakes.planner.requests[1]
    assert record.evidence == [] and record.plan is None
    assert fakes.reasoning.requests == []


# Several runs in the same thread, as in LangGraph Studio ---------------------------------


def run_in_thread(graph, db_path, thread_id="studio-thread"):
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke({"incident_id": INCIDENT_ID, "db_path": str(db_path)}, config)["record"]


def test_a_second_run_in_the_same_thread_starts_from_zero(db_path, fakes):
    graph = pipeline.build_graph(checkpointer=InMemorySaver())
    first = run_in_thread(graph, db_path)
    fakes.reasoning = Fake(LLMOutputError("The answer is not valid JSON.", "not json"), INVENTED_DRAFT, GOOD_DRAFT)

    second = run_in_thread(graph, db_path)

    assert first.status == "DRAFT"
    # The attempts are counted again from 1, so the third attempt is still allowed and accepted.
    assert second.status == "DRAFT"
    reasoning_steps = [step.summary for step in second.trace if step.name == "rca_reasoning_agent"]
    assert [summary.split(":")[0] for summary in reasoning_steps] == ["Attempt 1", "Attempt 2", "Attempt 3"]
    # Only the steps and notes of the second run are saved with it.
    assert [step.name for step in second.trace][:4] == ["similar_incidents", "investigation_planner", "tools", "historical_rca_agent"]
    assert len(second.trace) == 11
    assert second.not_checked == ["No database metrics."]
    assert [item.evidence_id for item in second.evidence] == [item.evidence_id for item in first.evidence]


def test_a_run_after_an_escalated_run_in_the_same_thread_is_not_escalated(db_path, fakes):
    graph = pipeline.build_graph(checkpointer=InMemorySaver())
    fakes.planner = Fake(plan_answer(queries=[" "]))
    first = run_in_thread(graph, db_path)
    fakes.planner = Fake(plan_answer())

    second = run_in_thread(graph, db_path)

    assert first.status == "ESCALATED"
    assert second.status == "DRAFT"
    assert second.investigation_summary == GOOD_DRAFT.investigation_summary
    assert second.plan is not None and len(second.hypotheses) == 2


def test_an_unknown_incident_stops_with_an_error(db_path, fakes):
    with pytest.raises(ValueError, match="INC-2099-00001"):
        pipeline.run_investigation("INC-2099-00001", db_path=db_path)


def test_starting_from_the_problem_gives_the_same_investigation(db_path, fakes):
    problem_id = storage.get_problem_id_for_incident(db_path, INCIDENT_ID)

    record = pipeline.run_investigation(problem_id=problem_id, db_path=db_path)

    assert record.problem_id == problem_id and record.incident_id == REFERENCE_ID
    assert [item.citation for item in record.evidence] == LEDGER


def test_the_graph_has_the_retry_loop_and_both_escalation_paths():
    edges = {(edge.source, edge.target) for edge in pipeline.graph.get_graph().edges}

    assert ("guardrail", "rca_reasoning_agent") in edges
    assert ("guardrail", "save_rca") in edges
    assert ("investigation_planner", "save_rca") in edges


# Real model, real search -----------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
@pytest.mark.skipif(not (ROOT / "chroma_db").exists(), reason="run scripts/ingest_chroma.py first")
def test_live_payment_api_end_to_end(db_path):
    record = pipeline.run_investigation(INCIDENT_ID, db_path=db_path, on_step=lambda step: print(f"{step.name}: {step.summary}"))

    print(f"\nMODEL: {config.GROQ_MODEL}, {record.duration_seconds} s")
    for item in record.hypotheses:
        print(f"{item.hypothesis_id} {item.confidence} ({item.confidence_points}): {item.candidate_root_cause}")

    assert record.status == "DRAFT"
    citations = {item.citation for item in record.evidence}
    assert {"CHG-2026-00871", "LOG-PAY-20260714-14", "CI-PAYMENT-DB", "RCA-2025-00114"} <= citations
    assert "RCA-2025-00042" not in citations
    # The answers vary a little between runs; the deploy must support a hypothesis that is not LOW.
    deploy = next(item.evidence_id for item in record.evidence if item.citation == "CHG-2026-00871")
    assert any(deploy in item.supporting_evidence and item.confidence != "LOW" for item in record.hypotheses)
    assert store.get_rca(record.rca_id, db_path=db_path) == record
