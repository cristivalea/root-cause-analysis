"""Guardrail: the checks on the model answer and the retry with the error included.

An answer from a model is untrusted until it passes the checks (doc 06, 6.4):
1. the shape: the answer matches the Pydantic schema (done in rca.llm, LLMOutputError);
2. the citations: every evidence id exists in the evidence ledger;
3. every hypothesis has at least one supporting evidence;
4. at least two hypotheses, or a written reason why there is only one.

If a check fails, the model is asked again with the problems included in the request.
After MAX_ATTEMPTS failed attempts the case is escalated to a person.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from rca.agents.reasoning import propose_draft
from rca.llm import LLMOutputError
from rca.models import DraftRCA, Evidence

T = TypeVar("T")

MAX_ATTEMPTS = 3


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


def check_draft(draft: DraftRCA, evidence_ids: set[str]) -> list[str]:
    """Checks 2, 3 and 4 on a draft whose shape is already valid. Returns the problems found."""
    problems: list[str] = []

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
