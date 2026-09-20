"""The technical review: the queue, the three decisions, and the picture of the findings."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from rca.ui import navigation, services, state
from rca.ui.components import cause_diagram
from rca.ui.strings import t

MAIN = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "main.py")


def open_review(rca_id: str | None = None, *, as_expert: bool = True) -> AppTest:
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    if as_expert:
        app.session_state[state.ROLE_KEY] = state.TECHNICAL_EXPERT
    if rca_id:
        app.query_params["rca"] = rca_id
    app.switch_page(navigation.REVIEW).run()
    return app


def stored(status: str):
    return next((record for record in services.list_rcas(status=status)), None)


# ---- Getting to a review ----


def test_the_queue_lists_what_is_waiting_for_a_decision():
    app = open_review()
    assert not app.exception
    waiting = services.list_rcas(status="PENDING_REVIEW")
    assert [button.label for button in app.button].count(t("review.open")) == len(waiting)


def test_a_review_can_be_opened_by_its_link_in_a_new_session():
    """A Technical Expert may come back a day later, from a link, in a fresh browser."""
    record = stored("PENDING_REVIEW")
    if record is None:
        return
    app = open_review(record.rca_id, as_expert=False)
    assert not app.exception
    assert any(button.label == t("review.switch_role") for button in app.button)

    app.button[0].click().run()
    assert app.session_state["role"] == state.TECHNICAL_EXPERT
    assert any(button.label == t("decision.approve") for button in app.button)


# ---- The decisions ----


def test_an_analysis_waiting_for_a_decision_offers_exactly_three():
    record = stored("PENDING_REVIEW")
    if record is None:
        return
    app = open_review(record.rca_id)
    labels = [button.label for button in app.button]
    for decision in ("decision.approve", "decision.request", "decision.reject"):
        assert labels.count(t(decision)) == 1


def test_a_decided_analysis_shows_what_was_decided_instead_of_the_buttons():
    record = stored("FINAL") or stored("REJECTED") or stored("MORE_DETAILS_REQUESTED")
    if record is None:
        return
    app = open_review(record.rca_id)
    labels = [button.label for button in app.button]
    assert t("decision.approve") not in labels
    assert record.review is not None
    assert any(record.review.reviewer in caption.value for caption in app.caption)


def test_an_approved_analysis_names_the_root_cause_it_validated():
    record = stored("FINAL")
    if record is None:
        return
    app = open_review(record.rca_id)
    assert record.final_root_cause
    assert any(record.final_root_cause in item.value for item in app.markdown)
    assert any(t("approve.done_title") in item.value for item in app.markdown)


def test_a_request_for_more_details_keeps_what_was_asked():
    record = stored("MORE_DETAILS_REQUESTED")
    if record is None:
        return
    assert record.review is not None
    assert record.review.decision == "REQUEST_MORE_DETAILS"
    assert record.review.requested_checks
    app = open_review(record.rca_id)
    assert any(t("request.done_title") in item.value for item in app.markdown)


# ---- The picture ----


def test_the_diagram_is_drawn_from_the_analysis_and_nothing_else():
    record = stored("FINAL") or stored("PENDING_REVIEW")
    if record is None or not record.hypotheses:
        return
    drawing = cause_diagram.dot(record, "Payment API intermittent failures")

    assert record.incident_id in drawing
    assert drawing.count("possible cause") == len(record.hypotheses)

    # A cause shows the first few pieces of evidence behind it, not an unreadable fan of them.
    known = {item.evidence_id: item for item in record.evidence}
    drawn = [
        known[evidence_id]
        for hypothesis in record.hypotheses
        for evidence_id in hypothesis.supporting_evidence[:cause_diagram.MAX_EVIDENCE_PER_CAUSE]
        if evidence_id in known
    ]
    assert drawn, "the analysis cites no evidence that the diagram could draw"
    for item in drawn:
        assert item.citation in drawing


def test_an_analysis_without_candidate_causes_gets_no_diagram():
    record = stored("ESCALATED")
    if record is None:
        return
    assert not record.hypotheses
    drawing = cause_diagram.dot(record)
    assert "possible cause" not in drawing
