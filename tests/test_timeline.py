"""The timeline: the facts of the ledger in time order, with the first error and the changes marked."""

from datetime import datetime

from rca.models import Evidence
from rca.timeline import as_lines, build_timeline


def at(value: str) -> datetime:
    return datetime.fromisoformat(value + "+00:00")


def evidence(evidence_id, kind, citation, when, description="A fact. More detail."):
    return Evidence(evidence_id=evidence_id, type=kind, source="test", description=description, citation=citation,
                    timestamp=at(when) if when else None)


LEDGER = [
    evidence("EV-001", "INCIDENT", "INC-2026-00857", "2026-07-15T09:48:00"),
    evidence("EV-002", "LOG", "LOG-1", "2026-07-14T14:05:00", "24 ERROR lines of ConnectionTimeout. Example: x"),
    evidence("EV-003", "LOG", "LOG-2", "2026-07-15T09:40:00"),
    evidence("EV-004", "CHANGE", "CHG-2026-00871", "2026-07-14T13:58:00"),
    evidence("EV-005", "CHANGE", "CHG-2026-00876", "2026-07-15T10:19:00"),
    evidence("EV-006", "CMDB", "CI-PAYMENT-DB", None),
    evidence("EV-007", "HISTORICAL_INCIDENT", "INC-2026-00482", "2026-07-14T14:32:00"),  # of the same problem
    evidence("EV-008", "HISTORICAL_INCIDENT", "INC-2025-00401", "2025-11-20T15:06:00"),  # a past one, other problem
    evidence("EV-009", "HISTORICAL_RCA", "RCA-2025-00114", "2025-11-20T14:00:00"),
]


def test_the_facts_of_the_problem_are_in_time_order_with_their_markers():
    entries = build_timeline(LEDGER, ["INC-2026-00482", "INC-2026-00857"], at("2026-07-14T14:32:00"))

    assert [(entry.citation, entry.marker) for entry in entries] == [
        ("CHG-2026-00871", "before the first error"),
        ("LOG-1", "first error"),
        ("INC-2026-00482", "incident detected"),
        ("LOG-2", None),
        ("INC-2026-00857", "incident detected"),
        ("CHG-2026-00876", "after the first error"),
    ]
    assert entries[1].what == "24 ERROR lines of ConnectionTimeout"  # the first sentence of the description


def test_without_logs_the_first_incident_is_the_first_error():
    no_logs = [item for item in LEDGER if item.type != "LOG"]

    entries = build_timeline(no_logs, ["INC-2026-00482", "INC-2026-00857"], at("2026-07-14T14:32:00"))

    markers = {entry.citation: entry.marker for entry in entries}
    assert markers["CHG-2026-00871"] == "before the first error"
    assert markers["CHG-2026-00876"] == "after the first error"


def test_the_lines_for_the_reasoning_agent_name_the_evidence_and_the_marker():
    lines = as_lines(build_timeline(LEDGER, ["INC-2026-00482", "INC-2026-00857"], at("2026-07-14T14:32:00")))

    assert lines[0] == "2026-07-14 13:58 UTC EV-004 CHANGE (before the first error)"
    assert lines[3] == "2026-07-15 09:40 UTC EV-003 LOG"


def test_the_expert_sees_the_timeline_with_its_markers():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
from datetime import datetime, timezone
from rca.models import RCARecord, TimelineEntry
from rca.ui.components.timeline_view import timeline_view
at = datetime(2026, 7, 14, 13, 58, tzinfo=timezone.utc)
record = RCARecord(rca_id="RCA-2026-00001", incident_id="INC-2026-00857", status="PENDING_REVIEW", owner="pm",
                   created_at=at, timeline=[
    TimelineEntry(at=at, evidence_id="EV-007", type="CHANGE", citation="CHG-2026-00871",
                  what="Deploy Payment API v4.18.2", marker="before the first error")])
timeline_view(record)
''').run()

    assert not app.exception
    line = " ".join(item.value for item in app.markdown)
    assert "`CHG-2026-00871`" in line and "before the first error" in line
    assert "Deploy Payment API v4.18.2" in [item.value for item in app.caption]
