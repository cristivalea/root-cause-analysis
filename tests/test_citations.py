import json
from pathlib import Path

from rca.citations import CITED_BY_MAIN, CITED_BY_OTHER, NOT_CITED, NOT_IN_LEDGER, record_for_story, trace_story
from rca.models import RCARecord

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# the sample record: plan on Payment API, 2026-07-14 11:32 - 15:17
RECORD = RCARecord.model_validate(json.loads((FIXTURES / "sample_rca_record.json").read_text(encoding="utf-8")))

LOGS = {
    "LOG-PAY-20260713-03": {"timestamp": "2026-07-13T10:18:00Z", "service": "Payment API", "level": "INFO"},
    "LOG-PAY-20260714-30": {"timestamp": "2026-07-14T14:20:00Z", "service": "Payment API", "level": "ERROR"},
    "LOG-GW-20260714-01": {"timestamp": "2026-07-14T14:20:00Z", "service": "API Gateway", "level": "ERROR"},
}
CHANGES = {"CHG-2026-00845": {"implemented_at": "2026-07-08T09:30:00Z", "service": "Payment API"}}


def story(expected, red_herrings=()):
    return {
        "story_id": "STORY-T", "target_incident": "INC-2026-00482", "problem_incidents": ["INC-2026-00482"],
        "expected_citations": expected, "red_herrings": [{"citation": item, "why": ""} for item in red_herrings],
        "five_whys": [], "fishbone": {}, "timeline": [],
    }


def stages(trace):
    return {item.citation: item.stage for item in trace.citations}


def test_each_citation_gets_the_last_stage_it_reached():
    trace = trace_story(story(["LOG-PAY-20260714-14", "CI-PAYMENT-API", "LOG-PAYDB-20260714-03", "RCA-2099-00001"]),
                        RECORD, LOGS, CHANGES)

    assert stages(trace) == {
        "LOG-PAY-20260714-14": CITED_BY_MAIN,       # EV-001, cited by HYP-001
        "CI-PAYMENT-API": CITED_BY_MAIN,            # EV-004
        "LOG-PAYDB-20260714-03": NOT_CITED,         # EV-007, cited by no hypothesis
        "RCA-2099-00001": NOT_IN_LEDGER,
    }
    assert trace.preserved == 3
    assert trace.cited_by_main == 2


def test_a_citation_used_only_by_a_weaker_hypothesis_is_not_counted_as_used():
    record = RECORD.model_copy(deep=True)
    record.hypotheses[0].supporting_evidence.remove("EV-004")

    trace = trace_story(story(["CI-PAYMENT-API"]), record, LOGS, CHANGES)

    assert trace.citations[0].stage == CITED_BY_OTHER
    assert trace.citations[0].cited_by == ["HYP-002"]


def test_the_plan_tells_why_a_log_line_or_a_change_never_reached_the_ledger():
    trace = trace_story(story(["CHG-2026-00845", "LOG-GW-20260714-01", "LOG-PAY-20260713-03", "LOG-PAY-20260714-30"]),
                        RECORD, LOGS, CHANGES)
    reasons = {item.citation: item.reason for item in trace.citations}

    assert "outside the window" in reasons["CHG-2026-00845"]
    assert "belongs to API Gateway" in reasons["LOG-GW-20260714-01"]
    assert "outside the window" in reasons["LOG-PAY-20260713-03"]
    assert "first line of its log group" in reasons["LOG-PAY-20260714-30"]


def test_red_herrings_cited_by_the_main_hypothesis_are_reported():
    trace = trace_story(story([], red_herrings=["INC-2025-00401", "CHG-2026-00868"]), RECORD, LOGS, CHANGES)

    assert trace.red_herrings_cited_by_main == ["INC-2025-00401"]  # EV-006 is cited, EV-005 is not


def test_the_investigation_of_a_story_is_found_through_any_incident_of_its_problem():
    other = RECORD.model_copy(update={"incident_id": "INC-2026-00857"})
    entry = story([]) | {"problem_incidents": ["INC-2026-00482", "INC-2026-00857"], "target_incident": "INC-2026-00482"}

    assert record_for_story(entry, [other]) is other
    assert record_for_story(story([]) | {"problem_incidents": []}, [other]) is None


def test_a_log_line_that_is_not_the_first_of_its_group_is_in_the_ledger_through_the_group():
    record = RECORD.model_copy(deep=True)
    record.evidence[0].related_ids = ["LOG-PAY-20260714-30"]  # EV-001: its group also holds this line

    trace = trace_story(story(["LOG-PAY-20260714-30"]), record, LOGS, CHANGES)

    assert (trace.citations[0].stage, trace.citations[0].evidence_id) == (CITED_BY_MAIN, "EV-001")
