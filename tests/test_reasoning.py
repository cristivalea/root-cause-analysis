"""Tests for the RCA Reasoning Agent.

The Payment API ledger comes from tests/conftest.py.
The live test calls Groq: python -m pytest -m live
"""

import json

import pytest

from rca import config
from rca.agents import reasoning
from rca.agents.reasoning import build_user_input, propose_draft
from rca.models import DraftRCA, Evidence, Hypothesis

INCIDENT_ID = "INC-2026-00482"


def test_payment_ledger_contains_the_facts_needed_for_the_demo(payment_ledger):
    citations = {item.citation for item in payment_ledger.items()}

    assert {"LOG-PAY-20260714-14", "CHG-2026-00871", "CI-PAYMENT-DB", "RCA-2025-00114"} <= citations
    assert "CHG-2026-00873" in citations  # the innocent change is in the ledger too


def test_the_model_receives_only_the_incident_id_and_the_ledger(payment_ledger):
    data = json.loads(build_user_input(INCIDENT_ID, payment_ledger.items()))

    assert set(data) == {"incident_id", "evidence_ledger"}
    assert [item["evidence_id"] for item in data["evidence_ledger"]] == [
        item.evidence_id for item in payment_ledger.items()
    ]


def test_the_draft_is_attached_to_the_investigated_incident(payment_ledger, monkeypatch):
    calls = []

    def fake_ask_json(instructions, user_input, schema):
        calls.append(schema)
        return DraftRCA(
            incident_id="INC-2099-99999",  # a wrong id written by the model
            investigation_summary="Summary.",
            observed_patterns=["Errors started after a deployment."],
            hypotheses=[
                Hypothesis(
                    hypothesis_id="HYP-001", candidate_root_cause="Cause.", reasons=["Reason."],
                    supporting_evidence=["EV-001"], contradicting_evidence=[], recommended_validation=["Check."],
                )
            ],
            single_hypothesis_reason="Only one explanation.",
            not_checked=[],
            suggested_workaround=None,
            change_likely_required=False,
        )

    monkeypatch.setattr(reasoning, "ask_json", fake_ask_json)

    draft = propose_draft(INCIDENT_ID, payment_ledger.items())

    assert calls == [DraftRCA]
    assert draft.incident_id == INCIDENT_ID


# Real model ----------------------------------------------------------------------------


def cited_ids(draft: DraftRCA) -> set[str]:
    return {
        evidence_id
        for hypothesis in draft.hypotheses
        for evidence_id in [*hypothesis.supporting_evidence, *hypothesis.contradicting_evidence]
    }


@pytest.mark.live
@pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set")
def test_live_draft_for_payment_api_cites_only_the_ledger(payment_ledger):
    evidence: list[Evidence] = payment_ledger.items()
    print("\nLEDGER:\n" + "\n".join(f"{item.evidence_id} {item.type} {item.citation}" for item in evidence))

    draft = propose_draft(INCIDENT_ID, evidence)

    print("\nDRAFT:\n" + draft.model_dump_json(indent=2))
    assert len(draft.hypotheses) >= 2 or draft.single_hypothesis_reason
    assert all(hypothesis.supporting_evidence for hypothesis in draft.hypotheses)
    assert cited_ids(draft) <= {item.evidence_id for item in evidence}, "a hypothesis cites an unknown id"
