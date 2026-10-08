"""The diagram draws every piece of evidence a cause cites, grouped by type."""

import json
from pathlib import Path

from rca.models import RCARecord
from rca.ui.components import cause_diagram

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORD = RCARecord.model_validate(json.loads((FIXTURES / "sample_rca_record.json").read_text(encoding="utf-8")))


def test_every_cited_piece_of_evidence_is_drawn_even_when_a_cause_cites_many():
    # HYP-001 of the sample cites 5 pieces of evidence of 4 types; the old diagram drew only 4 of them
    drawing = cause_diagram.dot(RECORD, "Payment API intermittent failures")
    known = {item.evidence_id: item for item in RECORD.evidence}

    for hypothesis in RECORD.hypotheses:
        for evidence_id in hypothesis.supporting_evidence + hypothesis.contradicting_evidence:
            assert known[evidence_id].citation in drawing, evidence_id


def test_the_evidence_of_one_cause_is_grouped_by_type():
    drawing = cause_diagram.dot(RECORD)
    main = RECORD.hypotheses[0]
    types = {item.type for item in RECORD.evidence if item.evidence_id in main.supporting_evidence}

    # one box per type for the main cause, not one box per piece of evidence
    assert drawing.count("cause0_ev") == 2 * len(types)  # each box: its node line and its edge line
    assert "Log lines (1)" in drawing
