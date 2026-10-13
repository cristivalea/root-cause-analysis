"""The RAGAS evaluation (rca/evaluation.py), without Groq and without Ollama.

The judge is replaced by a fake LLM with fixed answers, and the keyword search runs on a small
database built here, so the tests check our part of the work: building the samples, scoring
them and summing them up.
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

pytest.importorskip("ragas", reason="install requirements-eval.txt")

from ragas.llms.base import InstructorBaseRagasLLM  # noqa: E402
from ragas.metrics.collections import Faithfulness  # noqa: E402

from rca import evaluation  # noqa: E402
from rca.models import Evidence, RCARecord  # noqa: E402

QUESTION = {
    "question_id": "RQ-900",
    "incident_id": "INC-2026-00900",
    "before": "2026-07-14T14:32:00Z",
    "query": "Payment API card payments failing | Customers could not pay by card. | HTTP 500",
    "relevant_incidents": ["INC-2025-00401", "INC-2025-00402"],
    "relevant_rcas": [],
    "misleading_records": ["INC-2026-00371"],
}


# --------------------------------------------------------------------------------------
# the search
# --------------------------------------------------------------------------------------


def test_recall_and_precision_come_from_the_ids():
    result = evaluation.score_retrieval(
        QUESTION, "historical_incidents", "semantic",
        ["INC-2025-00401", "INC-2026-00371", "INC-2024-00001"], 0.45,
    )
    assert result.recall == pytest.approx(1 / 2)  # one of the two right records was found
    assert result.precision == pytest.approx(1 / 3)  # one of the three returned records is right
    assert result.misleading_found == ["INC-2026-00371"]


def test_a_question_with_nothing_to_find_has_no_recall():
    result = evaluation.score_retrieval(QUESTION, "historical_rcas", "semantic", [], 0.45)
    assert result.expects_nothing
    assert result.recall is None and result.precision is None


def test_the_summary_counts_a_correct_empty_answer_separately():
    found = evaluation.score_retrieval(QUESTION, "historical_incidents", "semantic", ["INC-2025-00401"], 0.45)
    empty = evaluation.score_retrieval(QUESTION, "historical_rcas", "semantic", [], 0.45)
    noisy = evaluation.score_retrieval(QUESTION, "historical_rcas", "semantic", ["RCA-2024-00088"], 0.45)

    summaries = {item.collection: item for item in evaluation.summarize_retrieval([found, empty, noisy])}
    assert summaries["historical_incidents"].recall == 0.5
    assert summaries["historical_incidents"].precision == 1.0
    assert summaries["historical_rcas"].recall is None  # nothing to find in either question
    assert summaries["historical_rcas"].empty_expected == 2
    assert summaries["historical_rcas"].empty_correct == 1


def test_a_threshold_keeps_only_the_records_close_enough():
    candidates = [("INC-1", 0.20), ("INC-2", 0.41), ("INC-3", 0.52)]
    assert evaluation.apply_threshold(candidates, 0.45) == ["INC-1", "INC-2"]
    assert evaluation.apply_threshold(candidates, 0.10) == []
    assert evaluation.apply_threshold(candidates, None) == ["INC-1", "INC-2", "INC-3"]


def test_every_threshold_is_scored_on_one_search(monkeypatch):
    calls = []

    def fake_candidates(question, collection, limit):
        calls.append(collection)
        return [("INC-2025-00401", 0.30), ("INC-2026-00371", 0.50)]

    monkeypatch.setattr(evaluation, "semantic_candidates", fake_candidates)
    results = evaluation.evaluate_thresholds([QUESTION], [0.40, 0.55])

    assert calls == ["historical_incidents", "historical_rcas"]  # one search per collection
    incidents = {item.max_distance: item for item in results if item.collection == "historical_incidents"}
    assert incidents[0.40].retrieved == ["INC-2025-00401"]
    assert incidents[0.55].retrieved == ["INC-2025-00401", "INC-2026-00371"]
    assert incidents[0.55].misleading_found == ["INC-2026-00371"]


def test_keywords_are_the_words_of_the_title():
    assert evaluation.keywords(QUESTION["query"]) == ["payment", "api", "card", "payments", "failing"]


def _incident(incident_id, title, detected_at):
    return (incident_id, detected_at, json.dumps({"title": title, "description": ""}))


def test_the_keyword_search_finds_shared_words_in_older_records_only(tmp_path):
    db_path = tmp_path / "sources.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE incidents (incident_id TEXT, detected_at TEXT, payload TEXT)")
        connection.executemany("INSERT INTO incidents VALUES (?, ?, ?)", [
            _incident("INC-2025-00401", "Card payments failing on Payment API", "2025-11-20T14:32:00Z"),
            _incident("INC-2025-00402", "Payment API slow", "2025-12-01T10:00:00Z"),
            _incident("INC-2025-00403", "No free database connections", "2025-12-02T10:00:00Z"),
            _incident("INC-2026-00999", "Card payments failing again", "2026-08-01T10:00:00Z"),  # after the incident
        ])

    found = evaluation.keyword_search(QUESTION, "historical_incidents", db_path=db_path)

    # most shared words first; a record with other words for the same thing is not found
    assert found == ["INC-2025-00401", "INC-2025-00402"]


def test_the_keyword_search_reads_the_completion_date_of_the_rcas(tmp_path):
    (tmp_path / "RCA-2025-00114.md").write_text(
        "# RCA-2025-00114\n**Completion Date:** 2025-12-10T10:00:00Z\nPayment API card payments failed.", encoding="utf-8")
    (tmp_path / "RCA-2026-00500.md").write_text(
        "# RCA-2026-00500\n**Completion Date:** 2026-08-10T10:00:00Z\nPayment API card payments failed.", encoding="utf-8")

    found = evaluation.keyword_search(QUESTION, "historical_rcas", rca_folder=tmp_path)

    assert found == ["RCA-2025-00114"]  # the other RCA was written after the incident


# --------------------------------------------------------------------------------------
# the hypotheses
# --------------------------------------------------------------------------------------


def _record(**hypothesis_changes):
    hypothesis = {
        "hypothesis_id": "HYP-001",
        "candidate_root_cause": "The pool size reduced by CHG-2026-00871 left too few connections.",
        "reasons": ["Timeouts started seven minutes after the change."],
        "supporting_evidence": ["EV-001", "EV-002"],
        "contradicting_evidence": [],
        "recommended_validation": ["Compare the pool settings before and after the change."],
        "confidence": "HIGH",
        "confidence_points": 5,
        "confidence_reasons": [],
        **hypothesis_changes,
    }
    now = datetime(2026, 7, 14, 15, 0, tzinfo=timezone.utc)
    return RCARecord.model_validate({
        "rca_id": "RCA-2026-00900",
        "incident_id": "INC-2026-00482",
        "status": "DRAFT",
        "owner": "test",
        "created_at": now,
        "evidence": [
            Evidence(evidence_id="EV-001", type="CHANGE", source="changes", citation="CHG-2026-00871",
                     description="Pool max size changed from 50 to 20 at 13:58.", timestamp=now),
            Evidence(evidence_id="EV-002", type="LOG", source="logs", citation="LOG-PAY-20260714-1",
                     description="24 ERROR ConnectionTimeout lines from 14:05.", timestamp=now),
            Evidence(evidence_id="EV-003", type="CMDB", source="cmdb", citation="CI-PAY-DB",
                     description="Payment API depends on CI-PAY-DB.", timestamp=None),
        ],
        "hypotheses": [hypothesis],
    })


def test_a_sample_holds_the_hypothesis_and_only_the_evidence_it_cites():
    [sample] = evaluation.faithfulness_samples(_record())

    assert sample.hypothesis_id == "HYP-001"
    assert sample.response.startswith("The pool size reduced by CHG-2026-00871")
    assert "Timeouts started seven minutes after the change." in sample.response
    assert sample.cited == ["EV-001", "EV-002"]
    assert sample.contexts[0] == "EV-001 (CHANGE, CHG-2026-00871): Pool max size changed from 50 to 20 at 13:58."
    assert not any("CI-PAY-DB" in context for context in sample.contexts)  # not cited, so not shown


def test_the_evidence_against_the_hypothesis_is_part_of_its_context():
    [sample] = evaluation.faithfulness_samples(_record(supporting_evidence=["EV-001"], contradicting_evidence=["EV-003"]))

    assert sample.cited == ["EV-001", "EV-003"]
    assert sample.contexts[1].startswith("EV-003 (CMDB, CI-PAY-DB)")


def test_a_hypothesis_without_known_evidence_is_not_judged():
    assert evaluation.faithfulness_samples(_record(supporting_evidence=["EV-099"])) == []


class FakeJudge(InstructorBaseRagasLLM):
    """Splits the answer into two statements and supports only the first one."""

    def generate(self, prompt, response_model):
        raise NotImplementedError

    async def agenerate(self, prompt, response_model):
        if response_model.__name__ == "StatementGeneratorOutput":  # step 1: split into statements
            return response_model(statements=["The pool size was reduced.", "A memory leak crashed the hosts."])
        return response_model(statements=[
            {"statement": "The pool size was reduced.", "reason": "EV-001 says so.", "verdict": 1},
            {"statement": "A memory leak crashed the hosts.", "reason": "Not in the evidence.", "verdict": 0},
        ])


def test_the_score_is_the_share_of_supported_statements_and_the_verdicts_are_kept():
    [result] = evaluation.evaluate_faithfulness([_record()], FakeJudge(), pause_seconds=0)

    assert result.score == 0.5
    assert [verdict.supported for verdict in result.verdicts] == [True, False]
    assert result.verdicts[1].reason == "Not in the evidence."


def test_our_three_steps_give_the_same_score_as_ragas_itself():
    import asyncio

    [sample] = evaluation.faithfulness_samples(_record())
    metric = Faithfulness(llm=FakeJudge())
    ours = asyncio.run(evaluation.judge_faithfulness(metric, sample)).score
    theirs = asyncio.run(metric.ascore(user_input=sample.user_input, response=sample.response,
                                       retrieved_contexts=sample.contexts)).value
    assert ours == theirs


def test_the_story_incidents_come_from_the_answer_key():
    incidents = evaluation.story_incidents()
    assert len(incidents) == 13
    assert "INC-2026-00482" in incidents
