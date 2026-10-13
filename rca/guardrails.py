"""Guardrail: the checks on the model answer and the retry with the error included.

An answer from a model is untrusted until it passes the checks (doc 06, 6.4):
1. the shape: the answer matches the Pydantic schema (done in rca.llm, LLMOutputError);
2. the citations: every evidence id exists in the evidence ledger;
3. every hypothesis has at least one supporting evidence;
4. at least two hypotheses, or a written reason why there is only one;
5. no evidence id named by a hypothesis that is not in the ledger (an invented citation): in its text,
   in the steps of its 5 Whys chain or in its fishbone factors;
6. no evidence cited both for and against the same hypothesis (a contradiction);
7. support beyond the incident itself: the incident is what must be explained, so a hypothesis supported
   only by it has no evidence;
8. no change made after the first error cited as support: it cannot have caused that error;
9. no hypothesis presented as a demonstrated cause ("the root cause is", "confirmed", "proven") in its
   candidate_root_cause: it is a candidate until an expert validates it.

An evidence id that exists and is named in the text without being cited is not refused: it is a
warning (text_warnings), saved with the guardrail step for the expert, and so is certain wording in the
reasons of a hypothesis. That the cited evidence really supports the claim is not decided here: the
confidence rules and the Technical Expert judge it.

If a check fails, the model is asked again with the problems included in the request.
After MAX_ATTEMPTS failed attempts the case is escalated to a person.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, TypeVar

from rca.agents.reasoning import propose_draft
from rca.llm import LLMOutputError
from rca.models import DraftRCA, Evidence

T = TypeVar("T")

MAX_ATTEMPTS = 3
EVIDENCE_ID = re.compile(r"\bEV-\d{3}\b")
# Wording that presents a candidate as a demonstrated cause. "not confirmed" and the like are allowed.
CERTAIN = re.compile(r"\b(the (actual |true |real )?root cause (is|was)|(is|was|has been) (confirmed|proven)|"
                     r"confirmed (as|to be)|definitely|certainly|undoubtedly|without (a )?doubt)\b", re.IGNORECASE)


def claims_certainty(text: str) -> bool:
    for match in CERTAIN.finditer(text or ""):
        before = text[max(0, match.start() - 8):match.start()].lower()
        if "not " not in before and "n't " not in before:
            return True
    return False


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _text_ids(hypothesis) -> set[str]:
    """The evidence ids a hypothesis names outside its citation lists: in its words, and in the steps
    and factors of its diagram (rca/diagram.py)."""
    text = " ".join([hypothesis.candidate_root_cause, *hypothesis.reasons, *hypothesis.recommended_validation,
                     *hypothesis.missing_evidence, *(f"{step.why} {step.because}" for step in hypothesis.why_chain),
                     *(factor.factor for factor in hypothesis.factors)])
    named = set(EVIDENCE_ID.findall(text))
    named |= {item for step in hypothesis.why_chain for item in step.evidence}
    named |= {item for factor in hypothesis.factors for item in factor.evidence}
    return named


def text_warnings(draft: DraftRCA) -> list[str]:
    """Evidence named in the text of a hypothesis but not cited by it (the claim may rest on it unseen), and
    certain wording in its reasons."""
    warnings = []
    for hypothesis in draft.hypotheses:
        uncited = sorted(_text_ids(hypothesis) - set(hypothesis.supporting_evidence) - set(hypothesis.contradicting_evidence))
        if uncited:
            warnings.append(f"{hypothesis.hypothesis_id} names {', '.join(uncited)} in its text without citing it.")
        if any(claims_certainty(reason) for reason in hypothesis.reasons):
            warnings.append(f"{hypothesis.hypothesis_id} uses certain wording in its reasons; it is still a candidate.")
    return warnings


@dataclass
class Attempt:
    """One call to the model. problems is empty when the answer was accepted."""

    number: int
    problems: list[str]


@dataclass
class GuardrailResult(Generic[T]):
    """The accepted answer, or None when every attempt failed and the case must be escalated."""

    value: T | None
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def escalated(self) -> bool:
        return self.value is None


def check_draft(draft: DraftRCA, evidence_ids: set[str], evidence: list[Evidence] | None = None,
                first_error: datetime | None = None) -> list[str]:
    """Checks 2 to 9 on a draft whose shape is already valid. Returns the problems found. evidence and
    first_error (the first error of the problem, rca/confidence.first_error_time) enable checks 7 and 8."""
    problems: list[str] = []
    by_id = {item.evidence_id: item for item in evidence or []}

    for hypothesis in draft.hypotheses:
        for kind, cited in (
            ("supporting_evidence", hypothesis.supporting_evidence),
            ("contradicting_evidence", hypothesis.contradicting_evidence),
        ):
            unknown = [evidence_id for evidence_id in cited if evidence_id not in evidence_ids]
            if unknown:
                problems.append(
                    f"{hypothesis.hypothesis_id} cites in {kind} ids that are not in the evidence ledger: "
                    f"{', '.join(unknown)}"
                )
        if not hypothesis.supporting_evidence:
            problems.append(f"{hypothesis.hypothesis_id} has no supporting evidence")
        invented = sorted(_text_ids(hypothesis) - evidence_ids)
        if invented:
            problems.append(f"{hypothesis.hypothesis_id} names in its text evidence ids that are not in the ledger: "
                            f"{', '.join(invented)}")
        both = sorted(set(hypothesis.supporting_evidence) & set(hypothesis.contradicting_evidence))
        if both:
            problems.append(f"{hypothesis.hypothesis_id} cites {', '.join(both)} both as supporting and as "
                            "contradicting evidence: decide which one it is")
        support = [by_id[item] for item in hypothesis.supporting_evidence if item in by_id]
        if support and all(item.type == "INCIDENT" for item in support):
            problems.append(f"{hypothesis.hypothesis_id} is supported only by the incident itself: the incident is "
                            "what must be explained; cite the evidence that supports the cause")
        if first_error is not None:
            late = [item.evidence_id for item in support
                    if item.type == "CHANGE" and item.timestamp and _utc(item.timestamp) > _utc(first_error)]
            if late:
                problems.append(f"{hypothesis.hypothesis_id} cites {', '.join(late)} as supporting evidence, a change "
                                "made after the first error: it cannot have caused it; move it to contradicting_evidence "
                                "or remove it")
        if claims_certainty(hypothesis.candidate_root_cause):
            problems.append(f"{hypothesis.hypothesis_id} presents its cause as demonstrated; write it as a candidate "
                            "(a possible cause), not as the confirmed root cause")

    if not draft.hypotheses:
        problems.append("the draft has no hypotheses")
    elif len(draft.hypotheses) == 1 and not (draft.single_hypothesis_reason or "").strip():
        problems.append("there is only one hypothesis and single_hypothesis_reason does not explain why")

    return problems


def format_feedback(problems: list[str]) -> str:
    """The problems of a refused answer, as they are added to the next request."""
    return "\n".join(f"- {problem}" for problem in problems)


def run_with_retries(
    ask: Callable[[str | None], T],
    check: Callable[[T], list[str]],
    max_attempts: int = MAX_ATTEMPTS,
) -> GuardrailResult[T]:
    """Call ask until check finds no problems, at most max_attempts times.

    ask receives None on the first attempt and the problems of the previous attempt afterwards.
    An invalid answer (LLMOutputError) counts as a failed attempt, like a failed check.
    """
    attempts: list[Attempt] = []
    feedback: str | None = None

    for number in range(1, max_attempts + 1):
        try:
            value = ask(feedback)
            problems = check(value)
        except LLMOutputError as exc:
            value, problems = None, [str(exc)]

        attempts.append(Attempt(number=number, problems=problems))
        if not problems:
            return GuardrailResult(value=value, attempts=attempts)
        feedback = format_feedback(problems)

    return GuardrailResult(value=None, attempts=attempts)


def validated_draft(
    incident_id: str,
    evidence: list[Evidence],
    max_attempts: int = MAX_ATTEMPTS,
) -> GuardrailResult[DraftRCA]:
    """Ask the RCA Reasoning Agent for a draft that passes all the checks, or escalate."""
    evidence_ids = {item.evidence_id for item in evidence}
    return run_with_retries(
        ask=lambda feedback: propose_draft(incident_id, evidence, feedback),
        check=lambda draft: check_draft(draft, evidence_ids),
        max_attempts=max_attempts,
    )
