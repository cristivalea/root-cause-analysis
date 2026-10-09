"""The cause diagram: 5 Whys for one clearly best cause, Fishbone for causes equally supported (audit P.4)."""

from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

from rca.diagram import choose_diagram, drawn_chain
from rca.guardrails import check_draft
from rca.models import AssessedHypothesis, CauseFactor, DraftRCA, WhyStep

CHAIN = [
    WhyStep(why="Why did payments fail?", because="No database connection was free.", evidence=["EV-002"]),
    WhyStep(why="Why was none free?", because="The retry handler kept them.", evidence=["EV-003"]),
    WhyStep(why="Why did it keep them?", because="v4.18.2 does not close the session.", evidence=[]),
    WhyStep(why="Why was it released?", because="No test for the retry path.", evidence=["EV-007"]),
]
FACTORS = [CauseFactor(category="Change / Release", factor="Deploy v4.18.2", evidence=["EV-007"]),
           CauseFactor(category="Monitoring", factor="Leak detection does not page", evidence=[])]


def hypothesis(hypothesis_id, level, chain=(), factors=()):
    return AssessedHypothesis(hypothesis_id=hypothesis_id, candidate_root_cause=f"Cause {hypothesis_id}.", reasons=[],
                              supporting_evidence=["EV-002"], contradicting_evidence=[], recommended_validation=[],
                              why_chain=list(chain), factors=list(factors), confidence=level, confidence_points=0,
                              confidence_reasons=[])


def test_one_clearly_best_cause_gets_its_5_whys_up_to_the_first_open_question():
    diagram = choose_diagram([hypothesis("HYP-001", "HIGH", CHAIN, FACTORS), hypothesis("HYP-002", "LOW")])

    assert (diagram.kind, diagram.hypothesis_id) == ("five_whys", "HYP-001")
    assert [step.because for step in diagram.steps] == [step.because for step in CHAIN[:3]]  # stops at the open question


def test_causes_equally_supported_get_a_fishbone_with_the_factors_of_all_of_them():
    other = [CauseFactor(category="Capacity", factor="Easter traffic", evidence=["EV-004"])]

    diagram = choose_diagram([hypothesis("HYP-001", "MEDIUM", CHAIN, FACTORS), hypothesis("HYP-002", "MEDIUM", factors=other),
                              hypothesis("HYP-003", "LOW", factors=[CauseFactor(category="Process", factor="x")])])

    assert diagram.kind == "fishbone"
    assert [(hypothesis_id, factor.factor) for hypothesis_id, factor in diagram.factors] == [
        ("HYP-001", "Deploy v4.18.2"), ("HYP-001", "Leak detection does not page"), ("HYP-002", "Easter traffic")]


def test_no_structure_means_no_diagram():
    assert choose_diagram([hypothesis("HYP-001", "HIGH"), hypothesis("HYP-002", "LOW")]) is None
    assert choose_diagram([]) is None
    assert drawn_chain(CHAIN[:2]) == CHAIN[:2]


def test_an_evidence_id_invented_in_the_chain_is_refused():
    bad = hypothesis("HYP-001", "LOW", [WhyStep(why="Why?", because="Because.", evidence=["EV-099"])])
    draft = DraftRCA(incident_id="INC-1", investigation_summary="", observed_patterns=[], hypotheses=[bad],
                     single_hypothesis_reason="Only one.", not_checked=[], suggested_workaround=None,
                     change_likely_required=False)

    assert any("EV-099" in problem for problem in check_draft(draft, {"EV-002"}))


APP = '''
from datetime import datetime, timezone
from rca.models import AssessedHypothesis, Evidence, RCARecord, WhyStep
from rca.ui.components import rca_diagram, rca_draft
at = datetime(2026, 7, 15, tzinfo=timezone.utc)
chain = [WhyStep(why="Why did payments fail?", because="No connection was free.", evidence=["EV-002"]),
         WhyStep(why="Why?", because="The session is never closed.", evidence=[])]
main = AssessedHypothesis(hypothesis_id="HYP-001", candidate_root_cause="The retry handler leaks connections.",
                          reasons=["A reason only the expert reads."], supporting_evidence=["EV-002"],
                          contradicting_evidence=[], recommended_validation=[], why_chain=chain,
                          confidence="HIGH", confidence_points=8, confidence_reasons=[])
record = RCARecord(rca_id="RCA-2026-00001", incident_id="INC-2026-00857", status="DRAFT", owner="pm", created_at=at,
                   hypotheses=[main], single_hypothesis_reason="Only one.",
                   evidence=[Evidence(evidence_id="EV-002", type="LOG", source="h", description="x",
                                      citation="LOG-PAY-20260714-14")])
rca_diagram.rca_diagram(record, "Payment API intermittent failures")
st_dot = rca_diagram.dot(record)
import streamlit as st
st.session_state["dot"] = st_dot
rca_draft.rca_draft(record, brief=True)
'''


def test_the_expert_sees_the_5_whys_with_its_evidence_and_the_problem_manager_a_brief_draft():
    app = AppTest.from_string(APP).run()

    assert not app.exception
    drawing = app.session_state["dot"]
    assert "LOG-PAY-20260714-14" in drawing and "dashed" in drawing and "to check" in drawing
    assert any(item.value == "5 Whys" for item in app.subheader)
    text = " ".join(item.value for item in app.markdown)
    assert "The retry handler leaks connections." in text  # the cause and its confidence...
    assert "A reason only the expert reads." not in text  # ...but not the reasons, in the brief draft
