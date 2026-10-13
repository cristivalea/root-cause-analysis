"""RCA history: the cases, their investigations, and the decisions taken on them."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rca.ui import navigation, services, state
from rca.ui.app_pages import history as history_page
from rca.ui.strings import t

MAIN = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "main.py")


def open_history(case_id: str | None = None, *, search: str | None = None) -> AppTest:
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    if case_id:
        app.query_params["case"] = case_id
    if search is not None:
        app.session_state[history_page.SEARCH_KEY] = search
    app.switch_page(navigation.HISTORY).run()
    return app


def a_case_with_several_investigations():
    return next((case for case in services.list_cases() if len(case) > 1), None)


# ---- The list ----


def test_the_list_shows_one_row_for_each_case_not_for_each_investigation():
    app = open_history()
    assert not app.exception
    cases = services.list_cases()
    assert [button.label for button in app.button].count(t("history.open_case")) == len(cases)
    assert any(t("history.count", count=len(cases)) in caption.value for caption in app.caption)


def test_searching_narrows_the_list_and_says_so_when_nothing_matches():
    app = open_history(search="no such case at all")
    assert not app.exception
    assert any(t("history.no_matches") in info.value for info in app.info)
    assert not any(button.label == t("history.open_case") for button in app.button)


def test_a_case_can_be_found_by_the_id_of_any_of_its_investigations():
    case = a_case_with_several_investigations()
    if case is None:
        return
    app = open_history(search=case[-1].rca_id)
    assert [button.label for button in app.button].count(t("history.open_case")) == 1


# ---- One case ----


def test_a_case_keeps_every_investigation_instead_of_overwriting_the_last():
    case = a_case_with_several_investigations()
    if case is None:
        return
    app = open_history(case[0].rca_id)
    assert not app.exception
    for record in case:
        assert any(record.rca_id in item.value for item in app.markdown)
        assert any(t("case.cycle", number=record.revision) in item.value for item in app.markdown)


def test_the_decision_taken_on_each_investigation_is_part_of_the_case():
    case = a_case_with_several_investigations()
    if case is None:
        return
    app = open_history(case[0].rca_id)
    for record in case:
        if record.review is None:
            continue
        assert any(record.review.reviewer in caption.value for caption in app.caption)
        if record.review.comment:
            assert any(record.review.comment in item.value for item in app.markdown)


def test_a_validated_case_shows_the_root_cause_that_was_agreed():
    case = next((case for case in services.list_cases()
                 if any(record.status == "VALIDATED" for record in case)), None)
    if case is None:
        return
    final = next(record for record in case if record.status == "VALIDATED")
    app = open_history(case[0].rca_id)
    assert any(t("case.final_title") in item.value for item in app.markdown)
    assert any(final.final_root_cause in item.value for item in app.markdown)


def test_history_is_a_page_of_the_problem_manager():
    """Since the sign-in, the Technical Expert has Home and Review only; the earlier revisions of a case
    are shown to the expert on the review page."""
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    app.switch_page(navigation.HISTORY).run()
    assert not app.exception
    assert app.title[0].value == t("history.title")

    expert = AppTest.from_file(MAIN, default_timeout=60)
    expert.session_state[state.ROLE_KEY] = state.TECHNICAL_EXPERT
    expert.run()
    with pytest.raises(ValueError, match="Could not find a navigation page"):
        expert.switch_page(navigation.HISTORY)


def test_an_address_pointing_at_no_case_says_so():
    app = open_history("RCA-2099-99999")
    assert not app.exception
    assert any(t("case.not_found") in info.value for info in app.info)
    assert any(button.label == t("history.back_to_list") for button in app.button)


# ---- One card per RCA, listed from its start; everything about it inside (E8) ----


def test_every_rca_is_listed_with_its_problem_status_revisions_and_dates_even_while_it_runs():
    summaries = services.list_rca_summaries()
    running = next(item for item in services.list_rcas() if item.run_status == "RUNNING")

    app = open_history()

    text = " ".join(item.value for item in app.markdown)
    for summary in summaries:
        assert f"`{summary.rca_id}` · `{summary.problem_id}` **{summary.title}**" in text
    captions = " ".join(item.value for item in app.caption)
    assert t("history.running", revision=running.revision) in captions
    assert t("history.revisions_many", count=2) in captions  # the RCA with two revisions


def test_searching_by_problem_finds_its_rca():
    summary = services.list_rca_summaries()[0]

    app = open_history(search=summary.problem_id)

    assert [button.label for button in app.button].count(t("history.open_case")) == 1


def test_an_rca_shows_its_status_history_and_every_revision_with_its_parts():
    case = a_case_with_several_investigations()
    app = open_history(case[0].rca_id)

    assert not app.exception
    history = services.rca_history(case[0].rca_id)["history"]
    assert any(t("case.status_history", count=len(history)) in item.label for item in [*app.expander, *app.status])
    text = " ".join(item.value for item in app.markdown)
    for record in case:
        assert f"`{record.revision_id}`" in text
    labels = [tab.label for tab in app.tabs]
    assert labels.count(t("case.tab_evidence_map")) == len(case) and labels.count(t("case.tab_causal")) == len(case)
    assert t("case.tab_steps") in labels and t("case.tab_inputs") in labels
