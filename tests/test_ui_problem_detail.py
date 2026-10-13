"""One problem, through the real API on a copy of the data (tests/conftest.py, ui_through_the_api): the
changes made on the page reach the database and come back in the history of the problem."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from rca.ui import services

PAGE = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "app_pages" / "problems.py")


def open_problem(problem_id):
    app = AppTest.from_file(PAGE, default_timeout=60)
    app.query_params["problem"] = problem_id
    return app.run()


def test_adding_removing_and_the_guidance_reach_the_database_and_its_history():
    # an Open problem: while its RCA is in progress a problem keeps its incidents (see the test below)
    problem = next(problem for problem in services.list_problems("Open") if len(problem.incidents) >= 2)
    removed = problem.incidents[-1].incident_id
    app = open_problem(problem.problem_id)
    assert not app.exception

    choice = app.selectbox(key="problem_add_choice")
    label = choice.options[0]  # the most alike incident
    added = label.split(" · ")[0]
    choice.select(label).run()
    app.text_input(key=f"add_reason_{added}").input("Same acquirer timeouts.").run()
    app.button(key="problem_add").click().run()

    app.button(key=f"remove_{removed}").click().run()
    app.text_area(key=f"remove_reason_{removed}").input("Different acquirer.").run()
    app.button(key=f"remove_confirm_{removed}").click().run()

    assert not app.exception
    data = services.get_problem(problem.problem_id)
    ids = [link.incident_id for link in data["problem"].incidents]
    assert added in ids and removed not in ids
    history = [(event.action, event.incident_id, event.reason) for event in data["events"]][-2:]
    assert history == [("incident_added", added, "Same acquirer timeouts."),
                       ("incident_removed", removed, "Different acquirer.")]
    assert "Different acquirer." in " ".join(item.value for item in [*app.markdown, *app.caption])


def test_a_problem_in_investigation_shows_no_remove_button_and_says_why():
    from rca.ui.strings import t

    problem = services.list_problems("In investigation")[0]
    app = open_problem(problem.problem_id)

    assert not app.exception
    assert not [button for button in app.button if (button.key or "").startswith("remove_")]
    assert t("problems.remove_in_investigation") in [item.value for item in app.caption]


def test_the_guidance_is_saved_on_an_open_problem_and_shown_again():
    problem = services.list_problems("Open")[0]  # no RCA in progress: the guidance can change
    app = open_problem(problem.problem_id)

    app.text_area(key=f"guidance_{problem.problem_id}_notes").input("Look at the acquirer side first.").run()
    app.number_input(key=f"guidance_{problem.problem_id}_days").set_value(30).run()
    app.button(key="guidance_save").click().run()

    assert not app.exception
    data = services.get_problem(problem.problem_id)
    assert (data["problem"].guidance.notes, data["problem"].guidance.change_window_days) == (
        "Look at the acquirer side first.", 30)
    assert data["events"][-1].action == "guide_updated"
    again = open_problem(problem.problem_id)  # shown again, as saved
    assert again.text_area(key=f"guidance_{problem.problem_id}_notes").value == "Look at the acquirer side first."
