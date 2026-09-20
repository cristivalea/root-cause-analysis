"""Choosing the incident to investigate: the filters, and the screen that uses them."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rca.models import Incident
from rca.ui import filtering, formatting, navigation, services, state
from rca.ui.components import filters as filter_controls
from rca.ui.strings import t

MAIN = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "main.py")


def incident(incident_id="INC-2026-00001", **changes) -> Incident:
    values = {
        "incident_id": incident_id,
        "title": "Payment API intermittent failures",
        "description": "Card payments failed intermittently.",
        "severity": "SEV-1",
        "status": "Resolved",
        "service": "Payment API",
        "business_service": "Online Payments",
        "environment": "production",
        "detected_at": datetime(2026, 7, 14, 14, 32, tzinfo=timezone.utc),
        "symptoms": ["HTTP 500"],
        "rca_required": True,
    }
    return Incident(**{**values, **changes})


def open_start_rca() -> AppTest:
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    app.switch_page(navigation.START_RCA).run()
    return app


# ---- The filters themselves ----


def test_search_finds_an_incident_by_its_id_or_by_its_title():
    item = incident()
    assert filtering.matches_text(item, "inc-2026-00001")
    assert filtering.matches_text(item, "payment api")
    assert filtering.matches_text(item, "")
    assert not filtering.matches_text(item, "database")


def test_each_filter_narrows_the_list_on_its_own():
    items = [
        incident("INC-2026-00001", severity="SEV-1", service="Payment API", status="Resolved"),
        incident("INC-2026-00002", severity="SEV-3", service="Billing Service", status="Closed"),
    ]
    assert len(filtering.apply(items, filtering.IncidentFilters(severities=("SEV-1",)))) == 1
    assert len(filtering.apply(items, filtering.IncidentFilters(services=("Billing Service",)))) == 1
    assert len(filtering.apply(items, filtering.IncidentFilters(statuses=("Closed",)))) == 1
    assert len(filtering.apply(items, filtering.IncidentFilters())) == 2


def test_the_date_filter_keeps_only_what_was_detected_inside_the_range():
    items = [
        incident("INC-2026-00001", detected_at=datetime(2026, 7, 14, tzinfo=timezone.utc)),
        incident("INC-2026-00002", detected_at=datetime(2026, 1, 5, tzinfo=timezone.utc)),
    ]
    inside = filtering.IncidentFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    assert [item.incident_id for item in filtering.apply(items, inside)] == ["INC-2026-00001"]


def test_one_filter_value_can_be_removed_without_touching_the_others():
    filters = filtering.IncidentFilters(severities=("SEV-1", "SEV-2"), services=("Payment API",))
    assert filters.without_value("severities", "SEV-1").severities == ("SEV-2",)
    assert filters.without_value("severities", "SEV-1").services == ("Payment API",)
    assert not filters.without("services").services
    assert not filtering.IncidentFilters().is_active


# ---- How values are written ----


@pytest.mark.parametrize(
    "value, written",
    [(45, "45 min"), (95, "1 h 35 min"), (120, "2 h"), (None, t("common.unknown"))],
)
def test_a_length_of_time_is_written_the_way_people_say_it(value, written):
    assert formatting.minutes(value) == written


def test_a_moment_is_always_written_in_utc():
    moment = datetime(2026, 7, 14, 14, 32, tzinfo=timezone.utc)
    assert formatting.date_time(moment) == "14 Jul 2026, 14:32 UTC"


# ---- The screen ----


def test_the_screen_lists_only_incidents_that_need_an_analysis():
    app = open_start_rca()
    assert not app.exception
    listed = len(app.dataframe[0].value)
    needing_analysis = [item for item in services.list_incidents() if item.rca_required]
    assert listed == min(10, len(needing_analysis))
    assert any(t("list.only_rca_required") in caption.value for caption in app.caption)


def test_the_action_waits_until_an_incident_is_chosen():
    app = open_start_rca()
    analyze = [button for button in app.button if button.label == t("selection.analyze")][0]
    assert analyze.disabled
    assert any(t("list.select_hint") in caption.value for caption in app.caption)


def test_choosing_an_incident_shows_it_and_frees_the_action():
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    app.session_state[state.SELECTED_INCIDENT_KEY] = "INC-2026-00482"
    app.switch_page(navigation.START_RCA).run()

    analyze = [button for button in app.button if button.label == t("selection.analyze")][0]
    assert not analyze.disabled
    assert any(t("selection.title") in caption.value for caption in app.caption)
    assert any("INC-2026-00482" in item.value for item in app.markdown)


def test_a_search_that_matches_nothing_says_so_instead_of_showing_an_empty_table():
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    app.session_state[filter_controls.TEXT_KEY] = "no such incident"
    app.switch_page(navigation.START_RCA).run()

    assert not app.dataframe
    assert any(t("state.no_matches") in info.value for info in app.info)
    assert any(button.label == t("filters.show_all") for button in app.button)


def test_searching_by_incident_id_finds_that_one_incident():
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    app.session_state[filter_controls.TEXT_KEY] = "INC-2026-00482"
    app.switch_page(navigation.START_RCA).run()

    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value["incident"].tolist() == ["INC-2026-00482"]
