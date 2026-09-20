"""The investigation screen: the steps as they are shown, and the analysis they produce."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest

from rca.models import InvestigationStep, RCARecord
from rca.ui import navigation, services, state
from rca.ui.components import investigation_timeline as timeline
from rca.ui.strings import t

MAIN = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "main.py")


def step(name: str, summary: str = "Done.", seconds: int = 2) -> InvestigationStep:
    started = datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)
    return InvestigationStep(
        name=name, summary=summary, started_at=started,
        finished_at=started + timedelta(seconds=seconds),
    )


def open_investigation(rca_id: str | None = None, incident_id: str | None = None) -> AppTest:
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    if rca_id:
        app.session_state[state.ACTIVE_RCA_KEY] = rca_id
    if incident_id:
        app.session_state[state.SELECTED_INCIDENT_KEY] = incident_id
    app.switch_page(navigation.INVESTIGATION).run()
    return app


def stored(status: str) -> RCARecord | None:
    return next((record for record in services.list_rcas(status=status)), None)


# ---- The steps ----


def test_every_step_is_named_in_words_a_person_understands():
    for name in timeline.STEPS:
        title = timeline.step_title(name)
        assert title and "_" not in title and name != title


def test_a_step_the_interface_does_not_know_still_gets_a_readable_name():
    assert timeline.step_title("some_new_step") == "Some new step"


def test_the_steps_that_ran_are_shown_before_the_ones_still_waiting():
    finished = [step("similar_incidents"), step("investigation_planner")]
    done = {item.name for item in finished}
    remaining = [name for name in timeline.STEPS if name not in done]
    assert remaining[0] == "tools"


# ---- The screen ----


def test_without_an_incident_the_screen_offers_one_instead_of_an_empty_pane():
    app = open_investigation()
    assert not app.exception
    assert any(t("investigation.nothing_selected") in info.value for info in app.info)
    assert any(button.label == t("investigation.choose_incident") for button in app.button)


def test_with_an_incident_and_no_analysis_the_screen_offers_to_start_one():
    app = open_investigation(incident_id="INC-2026-00482")
    assert not app.exception
    assert any(button.label == t("investigation.start") for button in app.button)


def test_a_finished_analysis_shows_its_candidate_causes_and_one_way_forward():
    record = stored("DRAFT")
    if record is None:
        return
    app = open_investigation(rca_id=record.rca_id)
    assert not app.exception
    assert any(t("draft.candidate_causes") in header.value for header in app.subheader)
    assert [button.label for button in app.button].count(t("send.action")) == 1


def test_an_analysis_already_sent_says_so_and_cannot_be_sent_twice():
    record = stored("PENDING_REVIEW")
    if record is None:
        return
    app = open_investigation(rca_id=record.rca_id)
    assert not app.exception
    assert not any(button.label == t("send.action") for button in app.button)
    assert any(t("send.sent_title") in item.value for item in app.markdown)


def test_an_escalated_investigation_explains_itself_and_can_be_run_again():
    record = stored("ESCALATED")
    if record is None:
        return
    app = open_investigation(rca_id=record.rca_id)
    assert not app.exception
    assert any(t("investigation.escalated") in warning.value for warning in app.warning)
    assert any(button.label == t("investigation.try_again") for button in app.button)


def test_the_analysis_never_calls_a_candidate_cause_the_root_cause():
    """The product rule: the investigation proposes, a Technical Expert decides."""
    record = stored("DRAFT") or stored("PENDING_REVIEW")
    if record is None:
        return
    assert record.final_root_cause is None
    app = open_investigation(rca_id=record.rca_id)
    assert any(t("draft.candidate_note") in caption.value for caption in app.caption)


def test_an_address_pointing_at_no_analysis_says_so():
    """A stale link should explain itself, not look like an empty screen."""
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    app.query_params["rca"] = "RCA-2099-99999"
    app.switch_page(navigation.INVESTIGATION).run()

    assert not app.exception
    assert any(t("investigation.not_found") in info.value for info in app.info)
    assert any(button.label == t("investigation.choose_incident") for button in app.button)
