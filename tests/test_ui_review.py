"""The technical review: the queue, the three decisions, and the picture of the findings."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from rca.ui import navigation, services, state
from rca.ui.components import cause_diagram
from rca.ui.strings import t

MAIN = str(Path(__file__).resolve().parents[1] / "rca" / "ui" / "main.py")


def open_review(rca_id: str | None = None, *, as_expert: bool = True) -> AppTest:
    app = AppTest.from_file(MAIN, default_timeout=60)
    if as_expert:  # the review page is a page of the expert's navigation only
        app.session_state[state.ROLE_KEY] = state.TECHNICAL_EXPERT
    app.run()
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
    waiting = services.list_rcas(status="AWAITING_TECHNICAL_REVIEW")
    assert [button.label for button in app.button].count(t("review.open")) == len(waiting)


def test_a_review_can_be_opened_by_its_link_in_a_new_session():
    """A Technical Expert may come back a day later, from a link, in a fresh browser, once signed in."""
    record = stored("AWAITING_TECHNICAL_REVIEW")
    app = open_review(record.rca_id)
    assert not app.exception
    assert app.session_state["role"] == state.TECHNICAL_EXPERT
    assert any(button.label == t("decision.approve") for button in app.button)


def test_the_expert_sees_what_was_decided_but_not_the_drafts_not_sent_yet():
    """After a decision the review shows its outcome; a draft the Problem Manager has not sent stays private."""
    assert "could not be found" not in " ".join(item.value for item in open_review(stored("VALIDATED").rca_id).info)
    draft = open_review(stored("DRAFT").rca_id)
    assert any(t("review.not_found") in item.value for item in draft.info)


# ---- The decisions ----


def test_an_analysis_waiting_for_a_decision_offers_exactly_three():
    record = stored("AWAITING_TECHNICAL_REVIEW")
    if record is None:
        return
    app = open_review(record.rca_id)
    labels = [button.label for button in app.button]
    for decision in ("decision.approve", "decision.request", "decision.reject"):
        assert labels.count(t(decision)) == 1


def test_a_decided_analysis_shows_what_was_decided_instead_of_the_buttons():
    record = stored("VALIDATED") or stored("REJECTED") or stored("REQUEST_MORE_DETAILS")
    if record is None:
        return
    app = open_review(record.rca_id)
    labels = [button.label for button in app.button]
    assert t("decision.approve") not in labels
    assert record.review is not None
    assert any(record.review.reviewer in caption.value for caption in app.caption)


def test_an_approved_analysis_names_the_root_cause_it_validated():
    record = stored("VALIDATED")
    if record is None:
        return
    app = open_review(record.rca_id)
    assert record.final_root_cause
    assert any(record.final_root_cause in item.value for item in app.markdown)
    assert any(t("approve.done_title") in item.value for item in app.markdown)


def test_a_request_for_more_details_keeps_what_was_asked():
    record = stored("REQUEST_MORE_DETAILS")
    if record is None:
        return
    assert record.review is not None
    assert record.review.decision == "REQUEST_MORE_DETAILS"
    assert record.review.requested_checks
    app = open_review(record.rca_id)
    assert any(t("request.done_title") in item.value for item in app.markdown)


# ---- The picture ----


def test_the_diagram_is_drawn_from_the_analysis_and_nothing_else():
    record = stored("VALIDATED") or stored("AWAITING_TECHNICAL_REVIEW")
    if record is None or not record.hypotheses:
        return
    drawing = cause_diagram.dot(record, "Payment API intermittent failures")

    assert record.incident_id in drawing
    assert drawing.count("possible cause") == len(record.hypotheses)

    # Every piece of evidence a cause cites is drawn (grouped by type, see tests/test_cause_diagram.py).
    known = {item.evidence_id: item for item in record.evidence}
    drawn = [
        known[evidence_id]
        for hypothesis in record.hypotheses
        for evidence_id in hypothesis.supporting_evidence
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


# ---- What changed, and one diagram at a time (E9) ----


def waiting_with_revisions(count: int):
    return next(record for record in services.list_rcas(status="AWAITING_TECHNICAL_REVIEW") if record.revision == count)


def test_a_new_revision_shows_what_changed_since_the_one_sent_back_and_what_was_asked():
    record = waiting_with_revisions(2)
    app = open_review(record.rca_id)

    assert not app.exception
    captions = [item.value for item in app.caption]
    assert t("compare.request") in captions and t("compare.main_same") in captions
    assert any("Check the pool size." in item.value for item in app.markdown)  # the request of the expert


def test_a_first_revision_has_nothing_to_compare_with():
    app = open_review(waiting_with_revisions(1).rca_id)
    assert not app.exception
    assert t("compare.main_same") not in [item.value for item in app.caption]


def test_the_two_diagrams_are_never_shown_together():
    record = waiting_with_revisions(1)
    app = open_review(record.rca_id)
    control = app.segmented_control(key=f"diagram-{record.rca_id}")

    assert control.value == "evidence_map"
    assert any(item.value == t("diagram.title") for item in app.subheader)  # the evidence map

    control.set_value("causal").run()
    assert not app.exception
    assert not any(item.value == t("diagram.title") for item in app.subheader)
    shown = [item.value for item in app.subheader] + [item.value for item in app.info]
    assert any(value in shown for value in (t("diagram.five_whys_title"), t("diagram.fishbone_title"),
                                            t("diagram.none")))
