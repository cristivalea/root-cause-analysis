"""The evidence step shows every search: where it looked, when, and what it found, even nothing."""

from streamlit.testing.v1 import AppTest

APP = '''
from datetime import datetime, timezone
from rca.models import InvestigationStep
from rca.ui.components.investigation_timeline import timeline

at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
step = InvestigationStep(name="tools", summary="Logs: 4 pattern(s).", started_at=at, finished_at=at, details={
    "evidence": 13,
    "services": ["Payment API", "Payment Database"],
    "log_windows": [
        {"start": "2026-07-14T12:32:00+00:00", "end": "2026-07-14T15:32:00+00:00", "incident_id": "INC-2026-00482"},
        {"start": "2026-07-15T07:48:00+00:00", "end": "2026-07-15T10:48:00+00:00", "incident_id": "INC-2026-00857"},
    ],
    "change_window": {"start": "2026-07-07T14:32:00+00:00", "end": "2026-07-15T10:31:00+00:00", "incident_id": None},
    "found": {"logs": ["LOG-PAY-20260714-14"], "changes": ["CHG-2026-00871", "CHG-2026-00876"], "cmdb": [],
              "problem_incidents": ["INC-2026-00482"]},
})
timeline([step], running=False)
'''


def test_the_evidence_step_shows_every_search_and_what_it_found():
    app = AppTest.from_string(APP).run()

    assert not app.exception
    text = " ".join(item.value for item in app.markdown) + " " + " ".join(item.value for item in app.caption)
    assert "Payment API, Payment Database" in text
    assert "INC-2026-00482: 14 Jul 2026, 12:32 UTC - 14 Jul 2026, 15:32 UTC" in text
    assert "INC-2026-00857" in text
    assert "Changes found (2)" in text and "`CHG-2026-00876`" in text
    assert "Components depended on, from the CMDB (0)" in text
    assert "Nothing found" in text  # an empty search is shown, not hidden
    assert "Other incidents of the problem (1)" in text


AGENT_APP = '''
from datetime import datetime, timezone
from rca.models import InvestigationStep
from rca.ui.components.investigation_timeline import timeline

at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
timeline([
    InvestigationStep(name="investigation_planner", summary="Plan.", started_at=at, finished_at=at,
                      details={"models": ["groq:openai/gpt-oss-120b"]}),
    InvestigationStep(name="rca_reasoning_agent", summary="Attempt 1: 2 hypothesis(es) proposed.", started_at=at,
                      finished_at=at, details={"models": ["gemini:gemini-3.5-flash"]}),
], running=False)
'''


def test_each_agent_step_shows_the_model_that_answered():
    app = AppTest.from_string(AGENT_APP).run()

    assert not app.exception
    captions = [item.value for item in app.caption]
    assert "Model: Groq · openai/gpt-oss-120b" in captions
    assert "Model: Gemini · gemini-3.5-flash" in captions
