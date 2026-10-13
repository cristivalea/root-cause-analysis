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


def open_investigation(rca_id: str | None = None) -> AppTest:
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    if rca_id:
        app.session_state[state.ACTIVE_RCA_KEY] = rca_id
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
    finished = [step("build_context"), step("investigation_planner")]
    done = {item.name for item in finished}
    remaining = [name for name in timeline.STEPS if name not in done]
    assert remaining[0] == "gather_evidence"


def test_the_steps_of_an_rca_saved_before_e5_keep_a_readable_name():
    for old in ("similar_incidents", "tools", "historical_rca_agent"):
        assert "_" not in timeline.step_title(old)


# ---- The screen ----


def test_without_an_rca_the_screen_sends_to_the_problems_where_an_rca_starts():
    app = open_investigation()
    assert not app.exception
    assert any(t("investigation.nothing_open") in info.value for info in app.info)
    assert [button.label for button in app.button if not button.label.startswith("Deconectare")] == [
        t("investigation.open_problems")]  # no way to start an RCA from an incident any more

    next(button for button in app.button if button.label == t("investigation.open_problems")).click().run()
    assert app.title[0].value == t("problems.title")


def test_an_rca_shows_its_problem_with_the_way_back_to_it_and_its_most_recent_incident():
    record = stored("DRAFT")
    app = open_investigation(rca_id=record.rca_id)

    assert not app.exception
    assert any(f"`{record.problem_id}`" in item.value for item in app.markdown)
    assert any(t("investigation.reference_incident") == item.value for item in app.caption)

    next(button for button in app.button if button.label == t("investigation.open_problem")).click().run()
    assert app.title[0].value == t("problems.title")
    assert app.query_params["problem"] == [record.problem_id]  # the problem itself, not the list


def test_the_next_revision_starts_from_the_rca_the_expert_sent_back(monkeypatch):
    import api

    started = []
    monkeypatch.setattr(api, "_run", lambda revision_id, owner: started.append(revision_id))  # no model call
    record = stored("REQUEST_MORE_DETAILS")
    app = open_investigation(rca_id=record.rca_id)

    next(button for button in app.button if button.label == t("cycle.start_next")).click().run()

    assert not app.exception
    assert started == [f"{record.rca_id}-R{record.revision + 1}"]
    assert any(t("investigation.running") in item.value for item in app.info)


def test_a_finished_analysis_shows_its_candidate_causes_and_one_way_forward():
    record = stored("DRAFT")
    if record is None:
        return
    app = open_investigation(rca_id=record.rca_id)
    assert not app.exception
    assert any(t("draft.candidate_causes") in header.value for header in app.subheader)
    assert [button.label for button in app.button].count(t("send.action")) == 1


def test_an_analysis_already_sent_says_so_and_cannot_be_sent_twice():
    record = stored("AWAITING_TECHNICAL_REVIEW")
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
    record = stored("DRAFT") or stored("AWAITING_TECHNICAL_REVIEW")
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
    assert any(button.label == t("investigation.open_problems") for button in app.button)


# ---- A run that is still going on (E4) ----


def test_a_running_investigation_shows_only_the_steps_that_finished():
    running = next(record for record in services.list_rcas(status="DRAFT") if record.run_status == "RUNNING")

    app = open_investigation(rca_id=running.rca_id)

    assert not app.exception
    assert any(t("investigation.running") in item.value for item in app.info)
    assert any(t("investigation.running_revision", revision=1, rca=running.rca_id) in item.value for item in app.caption)
    text = " ".join(item.value for item in app.markdown)
    assert timeline.step_title("similar_incidents") in text
    assert not any(button.label == t("send.action") for button in app.button)  # nothing to send while it runs


def test_the_steps_of_a_running_revision_are_marked_done_only_when_they_finished():
    running = next(record for record in services.list_rcas(status="DRAFT") if record.run_status == "RUNNING")

    done = [item.name for item in running.trace]

    assert done == ["similar_incidents", "investigation_planner"]


# ---- What every node shows (E8) ----


def render_steps(steps, running=False, current=None):
    def page(steps, running, current):
        from rca.ui.components.investigation_timeline import timeline

        timeline(steps, running=running, current=current)

    return AppTest.from_function(page, args=(steps, running, current), default_timeout=30).run()


def test_a_node_shows_what_it_read_its_requests_its_evidence_and_where_the_graph_went_next():
    reasoning = step("rca_reasoning_agent", "Attempt 1: 2 hypothesis(es) proposed.")
    reasoning.details = {"input": {"attempt": 1, "evidence": 14, "brief": ["investigation_guide"]},
                         "evidence_ids": ["EV-002", "EV-007"],
                         "llm_calls": [{"model": "groq:openai/gpt-oss-120b", "input_tokens": 3768, "output_tokens": 2048,
                                        "latency_seconds": 8.5, "waited_seconds": 0, "outcome": "valid",
                                        "reasoning_tokens": 1500, "finish_reason": "length"}],
                         "ids_cleaned": ["'EV-007 (the deploy)' read as EV-007"]}
    steps = [step("build_context"), step("investigation_planner"), step("gather_evidence"), step("build_timeline"),
             step("historical_review"), reasoning, step("guardrail", "Draft accepted on attempt 1.")]

    app = render_steps(steps)

    assert not app.exception
    text = " ".join(item.value for item in [*app.markdown, *app.caption])
    assert "attempt: 1" in text and "evidence: 14" in text
    assert t("step.llm_line", count=1, tokens_in=3768, tokens_out=2048, seconds="8.5") in text
    assert "`EV-002`, `EV-007`" in text
    assert t("step.llm_reasoning", tokens=1500) in text and t("step.llm_cut", count=1) in text
    assert "read as EV-007" in text  # an id the code cleaned is shown, not hidden
    assert t("step.next", step=timeline.step_title("guardrail")) in text


def test_the_running_node_is_the_one_langgraph_names_even_when_it_runs_again():
    steps = [step("build_context"), step("investigation_planner"), step("gather_evidence"), step("build_timeline"),
             step("historical_review"), step("rca_reasoning_agent"), step("guardrail", "Draft refused on attempt 1.")]

    app = render_steps(steps, running=True, current="rca_reasoning_agent")

    running = [item.value for item in app.caption if item.value == t("step.state.running")]
    assert len(running) == 1  # one node runs: the agent asked again, not the confidence after the guardrail
    headings = [item.value for item in app.markdown if item.value.startswith(":material/")]
    assert any(timeline.step_title("rca_reasoning_agent") in heading and "progress_activity" in heading
               for heading in headings)


def test_the_texts_given_to_the_agents_are_shown_and_the_planner_says_it_received_them():
    context = step("build_context", "1 incident(s). Given to the agents: notes, instructions.")
    context.details = {"given": ["notes", "instructions"],
                       "given_text": {"notes": "Check the connection pool after the deployment.",
                                      "instructions": "Why only during busy hours?"}}
    planner = step("investigation_planner", "2 search queries.")
    planner.details = {"input": {"notes": True, "instructions": True, "expert_request": False},
                       "search_queries": ["connection pool exhausted after deployment"],
                       "rationale": "The notes point at the pool after the deployment."}

    app = render_steps([context, planner])

    assert not app.exception
    shown = [item.value for item in app.text]
    assert "Check the connection pool after the deployment." in shown and "Why only during busy hours?" in shown
    captions = [item.value for item in app.caption]
    assert t("step.planner_read", items="notes, instructions") in captions


def test_opened_from_the_menu_the_screen_does_not_show_the_last_rca_again():
    record = stored("DRAFT")
    app = open_investigation(record.rca_id)
    assert not any(t("investigation.nothing_open") in info.value for info in app.info)  # the RCA another page opened

    app.switch_page(navigation.HOME).run()
    app.query_params.clear()  # a click in the menu leaves the address without ?rca= (AppTest keeps it)
    app.switch_page(navigation.INVESTIGATION).run()

    assert not app.exception
    assert any(t("investigation.nothing_open") in info.value for info in app.info)
    assert any(button.label == t("investigation.open_problems") for button in app.button)
