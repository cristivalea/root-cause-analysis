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
        (navigation.START_RCA, "start_rca.title"),
        (navigation.INVESTIGATION, "investigation.title"),
        (navigation.HISTORY, "history.title"),
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
    assert "More details requested" in badges.rca_status_chip("MORE_DETAILS_REQUESTED")


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


def test_the_home_button_opens_the_incident_selection():
    app = run_app()
    next(button for button in app.button if button.label == t("home.cta")).click().run()
    assert not app.exception
    assert app.title[0].value == t("start_rca.title")


def test_only_the_expert_is_told_what_is_waiting_for_review():
    app = run_app()
    assert not any(t("home.expert.open_review") == button.label for button in app.button)

    app = run_app(state.TECHNICAL_EXPERT)
    waiting = len(services.list_rcas(status="PENDING_REVIEW"))
    labels = [button.label for button in app.button]
    if waiting:
        assert t("home.expert.open_review") in labels
    else:
        assert any(t("home.expert.waiting_none") in item.value for item in app.markdown)


def test_the_role_survives_moving_to_another_page():
    """Widget state is dropped between pages, so the role is kept under its own key."""
    app = run_app(state.TECHNICAL_EXPERT)
    [button for button in app.button if button.label == t("home.expert.open_review")][0].click().run()
    assert app.title[0].value == t("review.title")
    assert app.session_state["role"] == state.TECHNICAL_EXPERT
