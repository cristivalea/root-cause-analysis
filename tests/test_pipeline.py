"""Tests for rca.pipeline: the whole investigation, from the problem to the saved draft.

The case is the Payment API problem: INC-2026-00482 (14 July) and its recurrence INC-2026-00857
(15 July, the reference incident). Starting from INC-2026-00482 investigates the whole problem.

Offline, the three agents and the ChromaDB search are replaced with fixed answers; the tools,
the ledger, the guardrail, the confidence rules and the store are the real code, on the mock
data loaded into a temporary SQLite database. The live test runs everything for real:
GROQ_MODEL=openai/gpt-oss-20b python -m pytest -m live tests/test_pipeline.py -s
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from rca import config, pipeline, storage, store
from rca.agents import historical, planner, reasoning
from rca.agents.historical import HistoricalRCADecision, HistoricalRCAReview
from rca.agents.planner import PlannerAnswer
from rca.llm import LLMOutputError
from rca.models import DraftRCA, Hypothesis, InvestigationGuidance

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
    ("RCA-2024-00999::Timeline", "Payment API gateway errors during a certificate rotation.",
     {"document_id": "RCA-2024-00999", "section_name": "Timeline", "service": "Payment API",
      "completion_date": 1720000000}, 0.33),
)


# The sections read from the index for the RCAs found. RCA-2024-00999 has none, to test the fallback.
RCA_SECTIONS = {
    "RCA-2025-00114": {
        "Summary": "Intermittent HTTP 500 errors and latency above 5 seconds.",
        "Timeline": "13:58 UTC: Release deployment completed on Payment API pods.",
        "Root Cause": "Connection pool exhaustion from unclosed SQL sessions in the retry handler.",
        "Corrective Actions": "try-with-resources in every repository method; leak detection enabled.",
    },
}


def plan_answer(queries=("payment requests fail with database connection timeouts",)) -> PlannerAnswer:
    return PlannerAnswer(search_queries=list(queries), rationale="Both incidents show database connection timeouts.")


# RCA-2025-00042 (Payroll) and INC-2026-00106 (Billing) never reach the agent: the code drops other services.
HISTORY_REVIEW = HistoricalRCAReview(decisions=[
    HistoricalRCADecision(citation="RCA-2025-00114", relevant=True, reason="Same service and same symptoms."),
    HistoricalRCADecision(citation="RCA-2024-00999", relevant=False, reason="Certificate rotation, different symptoms."),
    HistoricalRCADecision(citation="INC-2025-00401", relevant=True, reason="Same service, same timeouts."),
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


# The ledger of the problem: EV-001 the incident itself (INC-2026-00857, type INCIDENT), EV-002..003 logs
# around INC-2026-00482, EV-004..005 logs around INC-2026-00857, EV-006..009 changes (EV-007 the deploy
# CHG-2026-00871), EV-010..011 CMDB, EV-012 INC-2026-00482 (same problem), EV-013 RCA-2025-00114,
# EV-014 INC-2025-00401.
LEDGER = [
    "INC-2026-00857",
    "LOG-PAY-20260714-14", "LOG-PAY-20260714-15", "LOG-PAY-20260715-06", "LOG-PAY-20260715-01",
    "CHG-2026-00845", "CHG-2026-00871", "CHG-2026-00873", "CHG-2026-00876",
    "CI-PAYMENT-DB", "CI-PAYMENT-QUEUE", "INC-2026-00482", "RCA-2025-00114", "INC-2025-00401",
]
GOOD_DRAFT = draft(
    hypothesis("HYP-001", ["EV-002", "EV-003", "EV-007", "EV-010", "EV-013", "EV-014"]),
    hypothesis("HYP-002", ["EV-002", "EV-010"], contradicting=["EV-013"]),
)
TOOLS_ONLY_DRAFT = draft(hypothesis("HYP-001", ["EV-002", "EV-007"]), hypothesis("HYP-002", ["EV-004"]))
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
        linked: dict = {}  # what rag.rcas_linked_to answers
        linked_calls: list = []

    def fake_query_collection(collection_name, query_text, limit=5, before_timestamp=None, **kwargs):
        Fakes.search_calls.append(collection_name)
        if Fakes.search_error:
            raise Fakes.search_error
        assert before_timestamp == int(datetime.fromisoformat(REFERENCE_DETECTED).timestamp())
        return INCIDENT_RESULTS if collection_name == "historical_incidents" else RCA_RESULTS

    monkeypatch.setattr(pipeline.rag, "query_collection", fake_query_collection)

    def fake_linked(incident_ids, before_timestamp=None):
        Fakes.linked_calls.append((list(incident_ids), before_timestamp))
        return Fakes.linked

    monkeypatch.setattr(pipeline.rag, "rcas_linked_to", fake_linked)
    monkeypatch.setattr(pipeline, "_rca_sections", lambda rca_ids: {key: RCA_SECTIONS[key] for key in rca_ids if key in RCA_SECTIONS})
    monkeypatch.setattr(planner, "ask_json", lambda *args: Fakes.planner(*args))
    monkeypatch.setattr(historical, "ask_json", lambda *args, **kwargs: Fakes.historical(*kwargs.values()))
    monkeypatch.setattr(reasoning, "ask_json", lambda *args: Fakes.reasoning(*args))
    return Fakes


def step_of(record, name):
    """The last run of a step, found by its name rather than its position."""
    return [step for step in record.trace if step.name == name][-1]


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

    names = ["build_context", "investigation_planner", "gather_evidence", "build_timeline", "historical_review",
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
    assert "Payment API gateway errors during a certificate rotation." in history_request  # no sections: closest one
    assert "INC-2025-00401" in history_request


def test_the_distractors_do_not_become_evidence(db_path, fakes):
    record, _ = run(db_path)

    citations = {item.citation for item in record.evidence}
    assert "RCA-2025-00042" not in citations and "INC-2026-00106" not in citations and "RCA-2024-00999" not in citations
    history_step = step_of(record, "historical_review")
    assert [item["id"] for item in history_step.details["dropped"]] == ["RCA-2025-00042", "INC-2026-00106", "RCA-2024-00999"]


def test_past_records_of_other_services_are_dropped_by_code_before_the_agent(db_path, fakes):
    record, _ = run(db_path)

    history_request = fakes.historical.requests[0]
    assert "RCA-2025-00042" not in history_request and "INC-2026-00106" not in history_request
    reasons = {item["id"]: item["reason"] for item in step_of(record, "historical_review").details["dropped"]}
    assert reasons["RCA-2025-00042"].startswith("Another service (Payroll Service)")
    assert reasons["INC-2026-00106"].startswith("Another service (Billing Service)")


def test_an_invalid_answer_of_the_historical_agent_is_asked_again_instead_of_losing_the_history(db_path, fakes):
    fakes.historical = Fake(LLMOutputError("The answer is not valid JSON.", "not json"), HISTORY_REVIEW)

    record, _ = run(db_path)

    assert len(fakes.historical.requests) == 2
    assert {"RCA-2025-00114", "INC-2025-00401"} <= {item.citation for item in record.evidence}
    assert [item["attempt"] for item in step_of(record, "historical_review").details["attempts"]] == [1, 2]


def test_three_invalid_answers_continue_without_history_and_say_why(db_path, fakes):
    fakes.historical = Fake(LLMOutputError("The answer is not valid JSON.", "not json"))
    fakes.reasoning = Fake(TOOLS_ONLY_DRAFT)

    record, _ = run(db_path)

    assert len(fakes.historical.requests) == 3
    assert record.status == "DRAFT"
    assert not {"RCA-2025-00114", "INC-2025-00401"} & {item.citation for item in record.evidence}
    assert any("did not return a valid answer in 3 attempts" in item for item in record.not_checked)


def test_the_reasoning_agent_receives_the_ledger_with_times_relative_to_the_incidents(db_path, fakes):
    run(db_path)

    request = fakes.reasoning.requests[0]
    # the deploy CHG-2026-00871 at 13:58, 34 minutes before the first incident at 14:32
    assert "34 minutes before the first incident of the problem (INC-2026-00482)" in request
    assert "before the detection of INC-2026-00857" in request  # a log line of the recurrence
    assert "Judged relevant because: Same service and same symptoms." in request


def test_the_ledger_starts_with_the_incident_and_the_guardrail_keeps_its_warnings(db_path, fakes):
    named = hypothesis("HYP-001", ["EV-002", "EV-007"]).model_copy(update={"reasons": ["EV-013 had the same cause."]})
    fakes.reasoning = Fake(draft(named, hypothesis("HYP-002", ["EV-004"])))

    record, _ = run(db_path)

    assert (record.evidence[0].type, record.evidence[0].citation) == ("INCIDENT", REFERENCE_ID)
    assert "Symptoms:" in record.evidence[0].description
    guardrail = next(step for step in record.trace if step.name == "guardrail")
    assert guardrail.details["warnings"] == ["HYP-001 names EV-013 in its text without citing it."]


def test_a_past_rca_that_links_an_incident_is_found_even_when_its_text_is_not(db_path, fakes):
    fakes.linked = {
        "RCA-2025-00114": {"incidents": ["INC-2025-00401"], "service": "Payment API", "completion_date": PAYMENT_RCA_DATE},
        "RCA-2024-00500": {"incidents": ["INC-2025-00401"], "service": "Payment API", "completion_date": 1710000000},
        "RCA-2024-00600": {"incidents": ["INC-2025-00401"], "service": "Billing Service", "completion_date": 1710000000},
    }
    fakes.historical = Fake(HistoricalRCAReview(decisions=[*HISTORY_REVIEW.decisions,
        HistoricalRCADecision(citation="RCA-2024-00500", relevant=False, reason="Different symptoms.")]))

    record, _ = run(db_path)

    incidents, before = fakes.linked_calls[0]
    assert {"INC-2026-00482", "INC-2026-00857", "INC-2025-00401"} <= set(incidents)  # the problem and the similar ones
    assert before == int(datetime.fromisoformat(REFERENCE_DETECTED).timestamp())
    request = fakes.historical.requests[0]
    assert '"found_by": "search, and links INC-2025-00401"' in request  # RCA-2025-00114, found both ways
    assert '"found_by": "links INC-2025-00401"' in request  # RCA-2024-00500, found by the link only
    dropped = {item["id"]: item["reason"] for item in step_of(record, "historical_review").details["dropped"]}
    assert dropped["RCA-2024-00600"].startswith("Another service (Billing Service)")  # the rule holds for links too


def test_the_timeline_is_saved_and_sent_to_the_reasoning_agent(db_path, fakes):
    record, _ = run(db_path)

    markers = {entry.citation: entry.marker for entry in record.timeline}
    assert markers["CHG-2026-00871"] == "before the first error"  # the deploy, 7 minutes before the first timeout
    assert markers["CHG-2026-00876"] == "after the first error"  # the rollback
    assert markers["LOG-PAY-20260714-14"] == "first error"
    assert markers["INC-2026-00482"] == markers[REFERENCE_ID] == "incident detected"
    assert "RCA-2025-00114" not in markers  # history is not on the timeline of this problem
    assert step_of(record, "build_timeline").details["first_error"] == "LOG-PAY-20260714-14"
    assert '"timeline"' in fakes.reasoning.requests[0] and "(first error)" in fakes.reasoning.requests[0]


def test_the_history_says_what_was_done_then_and_that_the_problem_came_back_after_the_rca(db_path, fakes):
    record, _ = run(db_path)

    request = fakes.historical.requests[0]
    assert "Corrective Actions: try-with-resources" in request  # the agent judges the fix too
    assert "What was done then: Rolling restart" in request  # the mitigation of the past incident
    by_citation = {item.citation: item for item in record.evidence}
    # RCA-2025-00114 was completed in November 2025, the problem started in July 2026: it came back after it
    assert "The problem came back after this RCA" in by_citation["RCA-2025-00114"].description
    assert "What was done then: Rolling restart" in by_citation["INC-2025-00401"].description
    kept = {item["id"]: item for item in step_of(record, "historical_review").details["kept"]}
    assert kept["RCA-2025-00114"]["came_back_after"] is True and kept["INC-2025-00401"]["came_back_after"] is False
    assert "came back after RCA-2025-00114" in step_of(record, "historical_review").summary


def test_the_logs_of_the_services_the_problem_depends_on_are_read_and_labelled(db_path, fakes):
    record, _ = run(db_path)

    tools_step = step_of(record, "gather_evidence")
    assert set(record.context.related_services) <= set(tools_step.details["services"])
    for item in record.evidence:
        if item.type == "LOG" and item.service not in record.context.services:
            assert item.description.startswith(f"On {item.service}, a dependency: ")
            assert item.citation in tools_step.details["found"]["dependency_logs"]
    # whatever the dependencies log, the first error is still the Payment API's own
    assert step_of(record, "build_timeline").details["first_error"] == "LOG-PAY-20260714-14"


def test_the_coredns_errors_of_the_reporting_problem_are_found_on_its_kubernetes_dependency(db_path, fakes, monkeypatch):
    # STORY-009: the cause is on the shared Kubernetes platform; the evidence is kept even if the draft fails
    monkeypatch.setattr(pipeline.rag, "query_collection", lambda *args, **kwargs: [])
    fakes.reasoning = Fake(INVENTED_DRAFT)

    record = pipeline.run_investigation("INC-2026-00109", db_path=db_path)

    dependency_logs = [item for item in record.evidence if item.type == "LOG" and item.service == "Kubernetes Platform"]
    assert dependency_logs
    assert dependency_logs[0].description.startswith("On Kubernetes Platform, a dependency: ")
    assert {item.service for item in record.evidence if item.type == "LOG"} >= {"Reporting Service", "Kubernetes Platform"}


# The context fixes what is searched -----------------------------------------------------


def test_every_source_is_checked_around_every_incident_of_the_problem(db_path, fakes):
    record, _ = run(db_path)

    tools_step = step_of(record, "gather_evidence")
    assert [window["incident_id"] for window in tools_step.details["log_windows"]] == [INCIDENT_ID, REFERENCE_ID]
    assert set(tools_step.details["found"]) == {"logs", "dependency_logs", "changes", "cmdb", "problem_incidents",
                                                "similar_incidents"}
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

    assert INCIDENT_ID not in step_of(record, "gather_evidence").details["found"]["similar_incidents"]


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
    assert [step.name for step in record.trace[5:]] == [
        "rca_reasoning_agent", "guardrail", "rca_reasoning_agent", "guardrail",
        "rca_reasoning_agent", "guardrail", "confidence",
    ]
    assert "Your previous answer was refused" not in fakes.reasoning.requests[0]
    assert "not valid JSON" in fakes.reasoning.requests[1]
    assert "EV-099" in fakes.reasoning.requests[2]


def test_three_drafts_refused_by_the_guardrail_escalate_the_rca_for_manual_review(db_path, fakes):
    fakes.reasoning = Fake(INVENTED_DRAFT)

    record, _ = run(db_path)

    assert (record.status, record.run_status) == ("ESCALATED_MANUAL", "COMPLETED")
    assert len(fakes.reasoning.requests) == 3
    assert record.hypotheses == []
    assert "did not produce a valid draft in 3 attempts" in record.investigation_summary
    assert store.list_rcas("ESCALATED_MANUAL", db_path=db_path) == [record]
    assert storage.get_problem(db_path, record.problem_id).status == "Manual"


def test_three_answers_that_are_no_draft_at_all_fail_the_run_instead(db_path, fakes):
    """Not one answer was valid JSON: nothing was concluded, so it is a technical failure, not a judgement."""
    fakes.reasoning = Fake(LLMOutputError("The answer is not valid JSON.", "not json"))

    record, _ = run(db_path)

    assert (record.status, record.run_status) == ("FAILED", "FAILED")
    assert "did not produce a valid draft in 3 attempts" in record.error
    assert storage.get_problem(db_path, record.problem_id).status == "In investigation"


def test_a_technical_error_during_the_run_is_saved_on_the_revision_and_the_run_can_start_again(db_path, fakes):
    fakes.reasoning = Fake(RuntimeError("Groq is down"))

    with pytest.raises(RuntimeError, match="Groq is down"):
        run(db_path)

    failed = store.list_rcas(db_path=db_path)[0]
    assert (failed.status, failed.run_status) == ("FAILED", "FAILED")
    assert failed.error == "RuntimeError after historical_review: Groq is down"
    fakes.reasoning = Fake(GOOD_DRAFT)
    again = pipeline.run_investigation(rca_id=failed.rca_id, db_path=db_path)
    assert (again.revision, again.status) == (2, "DRAFT")


def test_a_plan_refused_three_times_fails_the_run_before_any_tool(db_path, fakes):
    fakes.planner = Fake(plan_answer(queries=[" "]))

    record, _ = run(db_path)

    assert record.status == "FAILED"
    assert len(fakes.planner.requests) == 3
    assert "search_queries" in fakes.planner.requests[1]
    assert record.evidence == [] and record.plan is None
    assert fakes.reasoning.requests == []


def test_the_guidance_of_the_problem_manager_reaches_the_context_and_the_planner(db_path, fakes):
    guidance = InvestigationGuidance(notes="Check the retry handler.", extra_services=["Network Services"])

    record = pipeline.run_investigation(INCIDENT_ID, db_path=db_path, guidance=guidance)

    assert record.context.notes == "Check the retry handler."
    assert "Network Services" in record.context.services
    assert "Check the retry handler." in fakes.planner.requests[0]
    assert "Network Services" in step_of(record, "gather_evidence").details["services"]


# The revisions of a case ----------------------------------------------------------------


def send_back(record, db_path, comment="Check the database changes of the last month.", guidance=None):
    store.submit_for_review(record.rca_id, "pm", db_path=db_path)
    return store.apply_review(record.rca_id, "expert", "REQUEST_MORE_DETAILS", comment, db_path=db_path,
                              requested_checks=["database changes", "pool settings"], guidance=guidance)


def test_the_request_of_the_expert_starts_the_next_revision_of_the_same_case(db_path, fakes):
    first = pipeline.run_investigation(INCIDENT_ID, db_path=db_path)
    send_back(first, db_path, guidance=InvestigationGuidance(change_window_days=30))

    second = pipeline.run_investigation(rca_id=first.rca_id, db_path=db_path)

    assert (second.rca_id, second.revision, second.previous_revision_id) == (first.rca_id, 2, first.revision_id)
    assert store.get_rca(first.revision_id, db_path=db_path).status == "REQUEST_MORE_DETAILS"
    assert second.problem_id == first.problem_id
    # what the expert asked is part of the context, and both agents read it
    assert second.context.expert_request.startswith("Check the database changes of the last month.")
    assert "- pool settings" in second.context.expert_request
    assert "Check the database changes" in fakes.planner.requests[-1]
    assert "Check the database changes" in fakes.reasoning.requests[-1]
    # the wider window the expert asked for is applied by code
    first_detected = datetime.fromisoformat("2026-07-14T14:32:00+00:00")
    assert second.context.change_window.start == first_detected - timedelta(days=30)
    assert "Technical Expert" in second.context.sources["change_window"]


def test_the_guidance_of_the_problem_manager_stays_in_the_next_revision(db_path, fakes):
    first = pipeline.run_investigation(INCIDENT_ID, db_path=db_path,
                                       guidance=InvestigationGuidance(extra_services=["Network Services"]))
    send_back(first, db_path)

    second = pipeline.run_investigation(rca_id=first.rca_id, db_path=db_path)

    assert "Network Services" in second.context.services


def test_only_an_rca_sent_back_for_more_details_gets_a_next_revision(db_path, fakes):
    draft_record = pipeline.run_investigation(INCIDENT_ID, db_path=db_path)

    with pytest.raises(store.TransitionError, match="a new revision starts only after"):
        pipeline.run_investigation(rca_id=draft_record.rca_id, db_path=db_path)
    assert len(store.list_revisions(draft_record.rca_id, db_path)) == 1  # nothing was created


def test_after_the_third_revision_a_new_request_escalates_the_case_to_people(db_path, fakes):
    record = pipeline.run_investigation(INCIDENT_ID, db_path=db_path)
    for _ in range(store.MAX_REVISIONS - 1):
        send_back(record, db_path)
        record = pipeline.run_investigation(rca_id=record.rca_id, db_path=db_path)
    assert record.revision == store.MAX_REVISIONS

    last = send_back(record, db_path)

    assert last.status == "ESCALATED_MANUAL"
    assert storage.get_problem(db_path, last.problem_id).status == "Manual"
    with pytest.raises(ValueError):
        pipeline.run_investigation(rca_id=last.rca_id, db_path=db_path)
    assert [item.revision for item in store.list_revisions(last.rca_id, db_path=db_path)] == [1, 2, 3]


# Several runs in the same thread, as in LangGraph Studio ---------------------------------


def run_in_thread(graph, db_path, thread_id="studio-thread", **inputs):
    config = {"configurable": {"thread_id": thread_id}}
    inputs = inputs or {"incident_id": INCIDENT_ID}
    return graph.invoke({**inputs, "db_path": str(db_path)}, config)["record"]


def test_a_second_run_in_the_same_thread_starts_from_zero(db_path, fakes):
    graph = pipeline.build_graph(checkpointer=InMemorySaver())
    first = run_in_thread(graph, db_path)
    send_back(first, db_path)  # the second run is the next revision of the same RCA
    fakes.reasoning = Fake(LLMOutputError("The answer is not valid JSON.", "not json"), INVENTED_DRAFT, GOOD_DRAFT)

    second = run_in_thread(graph, db_path, rca_id=first.rca_id)

    assert first.status == "DRAFT"
    # The attempts are counted again from 1, so the third attempt is still allowed and accepted.
    assert second.status == "DRAFT"
    reasoning_steps = [step.summary for step in second.trace if step.name == "rca_reasoning_agent"]
    assert [summary.split(":")[0] for summary in reasoning_steps] == ["Attempt 1", "Attempt 2", "Attempt 3"]
    # Only the steps and notes of the second run are saved with it.
    assert [step.name for step in second.trace][:5] == ["build_context", "investigation_planner", "gather_evidence",
                                                        "build_timeline", "historical_review"]
    assert len(second.trace) == 12
    assert second.not_checked == ["No database metrics."]
    assert [item.evidence_id for item in second.evidence] == [item.evidence_id for item in first.evidence]


def test_a_run_after_an_escalated_run_in_the_same_thread_is_not_escalated(db_path, fakes):
    graph = pipeline.build_graph(checkpointer=InMemorySaver())
    fakes.planner = Fake(plan_answer(queries=[" "]))
    first = run_in_thread(graph, db_path)
    fakes.planner = Fake(plan_answer())

    second = run_in_thread(graph, db_path, rca_id=first.rca_id)  # a failed run is run again

    assert first.status == "FAILED"
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
    assert ("guardrail", "save_revision") in edges
    assert ("investigation_planner", "save_revision") in edges


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


# Measures of the language model requests -----------------------------------------------


def test_every_agent_step_keeps_the_measures_of_its_own_requests(db_path, fakes, monkeypatch):
    """The baseline of the agents is read from the trace: each agent step holds only its own requests."""
    from types import SimpleNamespace

    from rca import llm

    def measured(fake, tokens):
        def ask(*args, **kwargs):
            usage = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=tokens, completion_tokens=10))
            llm._meter("groq:test-model", 0.0, [], "valid", usage)
            return fake(*(args or kwargs.values()))
        return ask

    monkeypatch.setattr(planner, "ask_json", measured(fakes.planner, 100))
    monkeypatch.setattr(historical, "ask_json", measured(fakes.historical, 200))
    monkeypatch.setattr(reasoning, "ask_json", measured(fakes.reasoning, 300))

    record, _ = run(db_path)

    tokens = {name: [call["input_tokens"] for call in step_of(record, name).details["llm_calls"]]
              for name in ("investigation_planner", "historical_review", "rca_reasoning_agent")}
    assert tokens == {"investigation_planner": [100], "historical_review": [200], "rca_reasoning_agent": [300]}


# A revision created first and run afterwards, as the API does it (E4) --------------------------


def test_each_step_is_saved_on_the_revision_as_soon_as_it_finished(db_path, fakes):
    problem_id = storage.get_problem_id_for_incident(db_path, INCIDENT_ID)
    revision = store.start_rca(problem_id, "pm", db_path=db_path)
    seen = []  # what anyone reading the revision saw after each step

    def on_step(finished):
        store.record_step(revision.revision_id, finished, db_path=db_path)
        saved = store.get_rca(revision.revision_id, db_path=db_path)
        seen.append((saved.run_status, [item.name for item in saved.trace]))

    record = pipeline.run_investigation(revision_id=revision.revision_id, db_path=db_path, on_step=on_step)

    assert seen[0] == ("RUNNING", ["build_context"])
    assert seen[2] == ("RUNNING", ["build_context", "investigation_planner", "gather_evidence"])
    assert all(status == "RUNNING" for status, _ in seen)  # nothing is shown as ended before the run ended
    assert (record.revision_id, record.status, record.run_status) == (revision.revision_id, "DRAFT", "COMPLETED")
    assert [item.name for item in record.trace] == seen[-1][1]
    store.record_step(revision.revision_id, record.trace[0], db_path=db_path)  # an ended revision is never changed
    assert store.get_rca(revision.revision_id, db_path=db_path).trace == record.trace


def test_a_revision_that_ended_is_not_run_again(db_path, fakes):
    problem_id = storage.get_problem_id_for_incident(db_path, INCIDENT_ID)
    revision = store.start_rca(problem_id, "pm", db_path=db_path)
    pipeline.run_investigation(revision_id=revision.revision_id, db_path=db_path)

    with pytest.raises(ValueError, match="not waiting for a run"):
        pipeline.run_investigation(revision_id=revision.revision_id, db_path=db_path)


# The graph of E5: what each node receives and gives, link by link -------------------------------


def problem_of(db_path):
    return storage.get_problem_id_for_incident(db_path, INCIDENT_ID)


def test_the_problem_and_the_guidance_of_the_problem_manager_reach_every_agent(db_path, fakes):
    from rca import problems

    problem_id = problem_of(db_path)
    guidance = InvestigationGuidance(notes="The retry handler changed recently.", instructions="Why only on Mondays?")

    record = pipeline.run_investigation(problem_id=problem_id, db_path=db_path, guidance=guidance)

    context = record.context
    assert (context.title, context.notes, context.instructions) == (
        storage.get_problem(db_path, problem_id).title, "The retry handler changed recently.", "Why only on Mondays?")
    for request in (fakes.planner.requests[-1], fakes.reasoning.requests[-1]):
        for text in ("The retry handler changed recently.", "Why only on Mondays?"):
            assert text in request
    assert step_of(record, "build_context").details["given"] == ["notes", "instructions"]
    # the texts themselves are kept on the step, so the Investigation page shows what the agents were given
    assert step_of(record, "build_context").details["given_text"] == {
        "notes": "The retry handler changed recently.", "instructions": "Why only on Mondays?"}
    # the guidance the RCA started with is kept on the problem, for the next start
    assert storage.get_problem(db_path, problem_id).guidance == guidance


def test_the_request_of_the_expert_reaches_the_historical_review_too(db_path, fakes):
    first = pipeline.run_investigation(INCIDENT_ID, db_path=db_path)
    send_back(first, db_path, comment="Is the retry storm the same as in RCA-2025-00114?")

    pipeline.run_investigation(rca_id=first.rca_id, db_path=db_path)

    for agent in (fakes.planner, fakes.historical, fakes.reasoning):
        assert "Is the retry storm the same as in RCA-2025-00114?" in agent.requests[-1]


def test_what_the_expert_concluded_about_an_earlier_rca_reaches_the_next_one(db_path, fakes):
    from rca import problems

    first = pipeline.run_investigation(INCIDENT_ID, db_path=db_path)
    store.submit_for_review(first.rca_id, "pm", db_path=db_path)
    store.apply_review(first.rca_id, "expert", "REJECT", "The deploy is not on the failing path.", db_path=db_path)
    problems.set_guidance(problem_of(db_path), InvestigationGuidance(notes="Look beyond the deploy."), "pm", db_path=db_path)

    second = pipeline.run_investigation(INCIDENT_ID, db_path=db_path)

    assert second.rca_id != first.rca_id
    conclusion = second.context.previous_conclusions[0]
    assert conclusion.startswith(f"{first.rca_id} was rejected by the Technical Expert: The deploy is not on the failing path.")
    assert "The deploy is not on the failing path." in fakes.planner.requests[-1]
    assert "The deploy is not on the failing path." in fakes.reasoning.requests[-1]


def test_an_extra_search_runs_only_after_the_code_accepted_it(db_path, fakes):
    fakes.planner = Fake(PlannerAnswer(
        search_queries=["payment requests fail with database connection timeouts"],
        extra_searches=[{"source": "logs", "service": "Network Services", "hours_before": 48,
                         "reason": "the notes point at the egress proxy"},
                        {"source": "logs", "service": "Mainframe", "hours_before": 24, "reason": "a guess"}],
        rationale="Timeouts, and the proxy the notes name."))

    record, _ = run(db_path)

    by_planner = [item for item in record.tool_runs if item.requested_by == "planner"]
    assert [(item.status, item.arguments.get("service")) for item in by_planner] == [
        ("ok", "Network Services"), ("ok", "Network Services"), ("refused", "Mainframe")]  # one run per incident
    assert by_planner[0].reason == "planner: the notes point at the egress proxy"
    assert "not a service of the CMDB" in by_planner[-1].error
    assert [item.service for item in record.plan.extra_searches] == ["Network Services"]


def test_every_tool_call_is_a_tool_run_and_every_fact_keeps_when_it_happened_and_when_it_was_found(db_path, fakes):
    record, _ = run(db_path)

    runs = {item.run_id: item for item in record.tool_runs}
    assert {item.tool for item in runs.values()} == {"search_similar_incidents", "find_dependencies", "find_logs",
                                                     "find_changes"}
    assert all(item.status == "ok" and item.finished_at >= item.started_at for item in runs.values())
    found = [item for item in record.evidence if item.type in ("LOG", "CHANGE", "CMDB")]
    assert found and all(item.tool_run in runs and item.evidence_id in runs[item.tool_run].evidence_ids
                         for item in found)
    assert all(item.collected_at is not None for item in record.evidence)
    log = next(item for item in record.timeline if item.type == "LOG")
    assert log.collected_at is not None and log.collected_at > log.at  # found long after it happened


def test_a_source_that_fails_is_recorded_and_the_investigation_goes_on(db_path, fakes, monkeypatch):
    original = pipeline.find_logs

    def find_logs(service, *args, **kwargs):
        if service == "Payment API":
            raise ConnectionError("the log store does not answer")
        return original(service, *args, **kwargs)

    monkeypatch.setattr(pipeline, "find_logs", find_logs)

    record, _ = run(db_path)

    failed = [item for item in record.tool_runs if item.status == "error"]
    assert failed and all(item.error == "ConnectionError: the log store does not answer" for item in failed)
    assert any("The logs of Payment API" in item and "could not be read" in item for item in record.not_checked)
    # the run went on to its end: an error is a fact about the run, not evidence that nothing happened (here the
    # fixed draft of the fake agent cites evidence ids that the missing logs no longer give, so it is refused)
    assert record.run_status == "COMPLETED" and step_of(record, "guardrail")


def test_what_the_historical_review_found_is_kept_and_reaches_the_reasoning_agent(db_path, fakes):
    fakes.historical = Fake(HistoricalRCAReview(decisions=[
        HistoricalRCADecision(citation="RCA-2025-00114", relevant=True, reason="Same service and same symptoms.",
                              similarities=["HTTP 500 after a release"], differences=["no batch then"],
                              remediation="try-with-resources in every repository method",
                              outcome="fixed until the retry handler changed"),
        HistoricalRCADecision(citation="RCA-2024-00999", relevant=False, reason="Certificate rotation."),
        HistoricalRCADecision(citation="INC-2025-00401", relevant=True, reason="Same service, same timeouts."),
    ]))

    record, _ = run(db_path)

    finding = next(item for item in record.historical_findings if item.citation == "RCA-2025-00114")
    assert (finding.kind, finding.similarities, finding.differences) == ("rca", ["HTTP 500 after a release"],
                                                                         ["no batch then"])
    assert finding.came_back_after  # completed before the first incident of the problem
    past = next(item for item in record.evidence if item.citation == "RCA-2025-00114")
    assert "Alike: HTTP 500 after a release" in past.description and "Different: no batch then" in past.description
    assert "Done then: try-with-resources" in fakes.reasoning.requests[-1]
    assert "Payment API" in fakes.historical.requests[-1] and "current_problem" in fakes.historical.requests[-1]


def test_an_rca_validated_in_the_application_for_an_earlier_problem_is_reviewed(db_path, fakes):
    import json as json_

    from rca import problems
    from rca.models import RCARecord
    from rca_helpers import make_rca

    old = [item.incident_id for item in problems.unassigned_incidents(db_path)
           if item.service == "Payment API" and item.detected_at.year == 2024][:1]
    earlier = problems.create_problem(old, "pm", db_path=db_path).problem.problem_id
    template = RCARecord.model_validate(json_.loads((ROOT / "tests" / "fixtures" / "sample_rca_record.json").read_text(
        encoding="utf-8")))
    validated = make_rca(db_path, earlier, template, "draft", "submit", "approve")

    run(db_path)

    assert validated.rca_id in fakes.historical.requests[-1]
    assert "Validated root cause:" in fakes.historical.requests[-1]


def test_the_guardrail_asks_again_when_a_hypothesis_cites_one_fact_for_and_against_it(db_path, fakes):
    contradicting = draft(hypothesis("HYP-001", ["EV-002", "EV-007"], contradicting=["EV-002"]),
                          hypothesis("HYP-002", ["EV-004"]))
    fakes.reasoning = Fake(contradicting, GOOD_DRAFT)

    record, _ = run(db_path)

    assert record.status == "DRAFT"
    assert "both as supporting and as contradicting" in fakes.reasoning.requests[1]


def test_list_items_a_model_joined_in_one_string_are_split():
    joined = ['TLS handshake failures","Certificate validation errors","Edge node certificate issue']

    assert pipeline._listed(joined) == ["TLS handshake failures", "Certificate validation errors",
                                        "Edge node certificate issue"]
    assert pipeline._listed(["one", "two"]) == ["one", "two"]


# Observability of every node (E8) ---------------------------------------------------------------


def test_every_node_says_what_it_read_and_the_running_node_comes_from_langgraph(db_path, fakes):
    started = []

    record = pipeline.run_investigation(INCIDENT_ID, db_path=db_path, on_node_start=started.append)

    assert started == ["build_context", "investigation_planner", "gather_evidence", "build_timeline",
                       "historical_review", "rca_reasoning_agent", "guardrail", "confidence", "save_revision"]
    for item in record.trace:
        assert "input" in item.details, item.name
    gathered = step_of(record, "gather_evidence").details["evidence_ids"]
    kept = step_of(record, "historical_review").details["evidence_ids"]
    assert gathered + kept == [item.evidence_id for item in record.evidence]  # each node names what it added
    assert step_of(record, "rca_reasoning_agent").details["evidence_ids"]  # what the draft cited


def test_a_secret_in_an_error_is_never_saved(db_path, fakes, monkeypatch):
    def find_logs(*args, **kwargs):
        raise ConnectionError("denied for key gsk_abcdefghijklmnopqrstuv in org_01kv7s5kaef5zrph")

    monkeypatch.setattr(pipeline, "find_logs", find_logs)
    fakes.reasoning = Fake(RuntimeError("Bearer abcdefghijklmnop.qrstuvwx failed"))

    with pytest.raises(RuntimeError):
        run(db_path)

    failed = store.list_rcas(db_path=db_path)[0]
    saved = failed.model_dump_json()
    assert "gsk_" not in saved and "org_01kv" not in saved and "abcdefghijklmnop.qrstuvwx" not in saved
    assert "[redacted]" in failed.error


def test_the_request_of_the_expert_reaches_every_agent_of_the_next_revision_through_the_api(db_path, fakes,
                                                                                         monkeypatch):
    """E9 from end to end: the Problem Manager starts the RCA and sends it to review, the expert asks for more
    details, the next revision starts; its planner, historical agent and reasoning agent all read the request."""
    testclient = pytest.importorskip("fastapi.testclient")
    import api

    monkeypatch.setattr(api, "DB_PATH", db_path)
    user = {"username": "pm", "role": "problem_manager", "active": True}
    api.app.dependency_overrides[api.get_current_user] = lambda: user
    http = testclient.TestClient(api.app)
    try:
        problem_id = storage.get_problem_id_for_incident(db_path, INCIDENT_ID)
        started = http.post(f"/api/v1/problems/{problem_id}/rcas", json={}).json()  # the run ends with the response
        rca_id = started["rca_id"]
        assert http.get(f"/api/v1/rcas/{rca_id}-R1").json()["run_status"] == "COMPLETED"
        assert http.post(f"/api/v1/rcas/{rca_id}/submit-review").status_code == 200

        user.update(username="expert", role="technical_expert")
        decided = http.post(f"/api/v1/rcas/{rca_id}/review", json={
            "decision": "REQUEST_MORE_DETAILS", "comment": "Check the connection pool of payment-db-prod-01.",
            "requested_checks": ["pool size"]})
        assert decided.status_code == 200 and decided.json()["status"] == "REQUEST_MORE_DETAILS"

        user.update(username="pm", role="problem_manager")
        assert http.post(f"/api/v1/rcas/{rca_id}/revisions", json={"request_key": "next-1"}).status_code == 202
        second = http.get(f"/api/v1/rcas/{rca_id}-R2").json()
    finally:
        api.app.dependency_overrides.clear()

    assert (second["revision"], second["run_status"], second["status"]) == (2, "COMPLETED", "DRAFT")
    assert second["context"]["expert_request"].startswith("Check the connection pool of payment-db-prod-01.")
    for agent in (fakes.planner, fakes.historical, fakes.reasoning):
        assert "Check the connection pool of payment-db-prod-01." in agent.requests[-1]
        assert "Check the connection pool of payment-db-prod-01." not in agent.requests[0]


def test_a_draft_whose_ids_carry_their_explanation_passes_the_first_time_and_the_cleaning_is_kept(db_path, fakes):
    written = draft(hypothesis("HYP-001", ["EV-002", "EV-003 (timeouts)", "EV-007 (the deploy)", "EV-010"]),
                    hypothesis("HYP-002", ["EV-002", "EV-010"], contradicting=["EV-013 (a different cause then)"]))
    fakes.reasoning = Fake(written)

    record, _ = run(db_path)

    assert record.status == "DRAFT"
    assert sum(1 for step in record.trace if step.name == "rca_reasoning_agent") == 1
    assert record.hypotheses[0].supporting_evidence == ["EV-002", "EV-003", "EV-007", "EV-010"]
    assert len(step_of(record, "rca_reasoning_agent").details["ids_cleaned"]) == 3
