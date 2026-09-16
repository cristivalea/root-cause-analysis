"""RCA Reasoning Agent: the only place where hypotheses about the cause are formed.

It receives the evidence ledger and nothing else, so every statement it makes can be traced
to an evidence id. It proposes candidate root causes; it never writes a confidence level
(the code calculates it) and never declares a final root cause (a person approves it).

The checks on its answer (citations that exist, evidence for every hypothesis, at least two
hypotheses) and the retry are in the guardrail, step 11.
"""

import json

from rca.llm import ask_json, with_feedback
from rca.models import DraftRCA, Evidence

INSTRUCTIONS = """You are the RCA Reasoning Agent in a Root Cause Analysis application for IT incidents.
You receive the evidence ledger of one investigation: the facts found in the logs, the changes,
the CMDB and the past incidents and RCAs. Each fact has an evidence id such as EV-001.
The ledger is the only information you have. Do not use anything that is not in it.

Work in this order:
1. Observed patterns: what the evidence has in common, for example the timing of the errors
   compared with the changes. Write them in observed_patterns, as plain facts.
2. Hypotheses: what could explain the evidence. Propose at least two different candidate
   root causes. Do not stop at the first explanation that sounds reasonable. If the evidence
   really allows only one explanation, give one hypothesis and explain why in
   single_hypothesis_reason; otherwise leave single_hypothesis_reason null.
3. For every hypothesis, go back through the whole ledger and look for the facts that argue
   against it, for example: the change the hypothesis blames was made after the first error,
   the component it blames is not on the failing path, a similar past incident had a different
   cause, the same errors also appear when there was no incident. Put their ids in
   contradicting_evidence. An empty list is allowed only after you looked.
4. What could not be checked: the information an expert would need that is not in the ledger,
   for example missing metrics, sources that were not searched, a short log window, or no
   data from other environments. Write it in not_checked.
5. Next steps: a temporary workaround a person could consider (or null), and whether fixing
   the cause is likely to require a change (change_likely_required).

Rules for every hypothesis:
- hypothesis_id is HYP-001, HYP-002, ... in order, the best supported first.
- candidate_root_cause is one sentence describing a possible cause. It is a candidate, not a
  conclusion: never call it "the root cause" and never say it is confirmed.
- reasons explains, in short sentences, how the cited evidence supports it.
- supporting_evidence and contradicting_evidence contain only evidence ids that exist in the
  ledger (EV-...), never the ids of the original records such as CHG-... or LOG-....
  Every hypothesis needs at least one supporting evidence id.
- supporting_evidence cites every fact the hypothesis really relies on, including the CMDB
  dependency that connects the failing component to the suspected cause, and nothing else.
- recommended_validation lists concrete checks a Technical Expert can do to confirm or reject it.
- A change close in time is not a cause by itself: some changes in the window are innocent.
  A change made after the first error cannot have caused that error, so it is never supporting
  evidence for a cause.
- contradicting_evidence contains only facts that argue against this specific hypothesis.
  A fact that is simply unrelated to the hypothesis goes in neither list.
- Do not write any confidence level. The application calculates it from the evidence.

incident_id is the id given in the input. Write in English."""


def build_user_input(incident_id: str, evidence: list[Evidence]) -> str:
    return json.dumps(
        {
            "incident_id": incident_id,
            "evidence_ledger": [item.model_dump(mode="json") for item in evidence],
        },
        indent=2,
        ensure_ascii=False,
    )


def propose_draft(incident_id: str, evidence: list[Evidence], feedback: str | None = None) -> DraftRCA:
    """Ask the model for the draft RCA, based only on the evidence ledger.

    feedback is the reason the previous answer was refused, added by the guardrail on a retry.
    Raises LLMOutputError when the answer is not valid JSON or does not match DraftRCA.
    """
    draft = ask_json(INSTRUCTIONS, with_feedback(build_user_input(incident_id, evidence), feedback), DraftRCA)
    # The incident id is known by the code, so the model cannot attach the draft to another incident.
    return draft.model_copy(update={"incident_id": incident_id})
