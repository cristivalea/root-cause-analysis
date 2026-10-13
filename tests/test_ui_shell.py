"""The interface shell: the pages open, the roles see the right ones, and the badges hold.

These tests keep the redesign honest without a browser: they run the real Streamlit script
and check what it produced.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rca.models import RCAStatus
from rca.ui import navigation, services, state, theme
from rca.ui.components import badges
from rca.ui.strings import EN, t

MAIN = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "main.py")


def run_app(role: str = state.PROBLEM_MANAGER) -> AppTest:
    """The application, signed in with the given role (tests/conftest.py signs every AppTest in)."""
    app = AppTest.from_file(MAIN, default_timeout=60)
    app.session_state[state.ROLE_KEY] = role
    return app.run()


def labels(app: AppTest) -> list[str]:
    """The buttons of the page, without the sign-out button of the shell."""
    return [button.label for button in app.button if not button.label.startswith("Deconectare")]


# ---- The shell ----


def test_home_opens_without_errors():
    app = run_app()
    assert not app.exception
    assert app.title[0].value == t("home.title")


@pytest.mark.parametrize(
    "page, title_key",
    [
        (navigation.KPIS, "kpis.title"),
        (navigation.INVESTIGATION, "investigation.title"),
        (navigation.HISTORY, "history.title"),
        (navigation.PROBLEMS, "problems.title"),
        (navigation.PROPOSALS, "proposals.title"),
    ],
)
def test_every_page_of_the_problem_manager_opens(page, title_key):
    app = run_app()
    app.switch_page(page).run()
    assert not app.exception
    assert app.title[0].value == t(title_key)


def test_the_review_page_belongs_to_the_technical_expert():
    """Since the sign-in, each role has its own pages: the Problem Manager has no review page."""
    with pytest.raises(ValueError, match="Could not find a navigation page"):
        run_app().switch_page(navigation.REVIEW)

    app = run_app(state.TECHNICAL_EXPERT)
    app.switch_page(navigation.REVIEW).run()
    assert not app.exception
    assert app.title[0].value == t("review.title")


def test_the_role_comes_from_the_sign_in_and_cannot_be_changed_on_a_page():
    for role in state.ROLES:
        app = run_app(role)
        assert not app.exception
        assert not app.segmented_control  # no role selector any more
        assert any(button.label == "Deconectare (tester)" for button in app.button)


# ---- The design system ----


def test_every_stored_status_has_a_word_and_a_style():
    for status in RCAStatus.__args__:
        assert f"rca_status.{status}" in EN
        assert status in theme.RCA_STATUS


def test_severity_and_status_do_not_share_a_visual_language():
    assert badges.severity_chip("SEV-1") != badges.incident_status_chip("Resolved")
    assert all(style.icon is None for style in theme.SEVERITY.values())


def test_a_badge_never_breaks_on_a_value_the_interface_does_not_know_yet():
    assert badges.severity_chip("SEV-9") == ":gray-badge[SEV-9]"
    assert "More details requested" in badges.rca_status_chip("REQUEST_MORE_DETAILS")


def test_every_badge_carries_its_label_as_text():
    for severity in theme.SEVERITY:
        assert badges.severity_label(severity) in badges.severity_chip(severity)


# ---- Home ----


def test_home_explains_the_four_steps_and_offers_one_way_to_start():
    app = run_app()
    texts = [item.value for item in app.markdown] + [item.value for item in app.caption]
    for step in ("home.step_1", "home.step_2", "home.step_3", "home.step_4"):
        assert any(t(f"{step}.title") in text for text in texts)
    assert labels(app) == [t("home.cta")]


def test_the_home_button_opens_the_problems_where_an_rca_starts():
    app = run_app()
    next(button for button in app.button if button.label == t("home.cta")).click().run()
    assert not app.exception
    assert app.title[0].value == t("problems.title")


def test_the_incidents_and_start_an_rca_pages_are_gone_from_the_navigation():
    pages = Path(navigation.__file__).parent / "app_pages"
    assert not hasattr(navigation, "INCIDENTS") and not hasattr(navigation, "START_RCA")
    assert not (pages / "incidents.py").exists() and not (pages / "start_rca.py").exists()
    for page in (navigation.HOME, navigation.PROBLEMS, navigation.PROPOSALS, navigation.INVESTIGATION,
                 navigation.HISTORY, navigation.KPIS):
        app = run_app()
        app.switch_page(page).run()
        assert not app.exception


def test_the_kpi_page_shows_no_invented_number():
    app = run_app()
    app.switch_page(navigation.KPIS).run()
    assert not app.exception
    assert not app.metric and not app.dataframe
    assert any(t("kpis.not_defined") in item.value for item in app.info)


def test_only_the_expert_is_told_what_is_waiting_for_review():
    app = run_app()
    assert not any(t("home.expert.open_review") == button.label for button in app.button)

    app = run_app(state.TECHNICAL_EXPERT)
    waiting = len(services.list_rcas(status="AWAITING_TECHNICAL_REVIEW"))
    labels = [button.label for button in app.button]
    if waiting:
        assert t("home.expert.open_review") in labels
    else:
        assert any(t("home.expert.waiting_none") in item.value for item in app.markdown)


def test_the_expert_is_notified_of_each_rca_waiting_and_of_a_revision_that_answers_a_request():
    app = run_app(state.TECHNICAL_EXPERT)
    waiting = services.list_rcas(status="AWAITING_TECHNICAL_REVIEW")

    assert not app.exception
    assert {button.key for button in app.button if button.key and button.key.startswith("notify-")} == {
        f"notify-{record.rca_id}" for record in waiting}
    answered = next(record for record in waiting if record.revision > 1)
    assert any(t("home.expert.answers_request", revision=answered.revision) in item.value for item in app.markdown)


def test_the_role_survives_moving_to_another_page():
    """Widget state is dropped between pages, so the role is kept under its own key."""
    app = run_app(state.TECHNICAL_EXPERT)
    [button for button in app.button if button.label == t("home.expert.open_review")][0].click().run()
    assert app.title[0].value == t("review.title")
    assert app.session_state["role"] == state.TECHNICAL_EXPERT


def test_a_server_running_older_code_says_so(monkeypatch):
    from datetime import datetime

    from rca.ui import code_check

    monkeypatch.setattr(code_check, "changed_since_start", lambda: datetime(2026, 10, 13, 17, 39))
    app = run_app()

    assert any("Restart Streamlit" in item.value and "17:39" in item.value for item in app.warning)


def test_a_server_running_the_current_code_says_nothing(monkeypatch):
    from rca.ui import code_check

    monkeypatch.setattr(code_check, "changed_since_start", lambda: None)
    app = run_app()

    assert not any("Restart Streamlit" in item.value for item in app.warning)
