"""Which cause diagram an analysis gets, and what it holds (audit_rca_project.md, P.4).

The Reasoning Agent gives the structure as data (Hypothesis.why_chain and Hypothesis.factors);
the code chooses the diagram from the shape of the result and the interface draws it:
- 5 Whys, when one candidate cause is better supported than every other (a higher confidence
  level): the chain of that cause, from the symptom down;
- Fishbone, when several candidate causes are equally supported: the factors of all of them,
  by category, each with the hypothesis it comes from.

A 5 Whys chain stops where the evidence stops: it is drawn up to the first step without evidence,
included as the open question, and not further, so no "why" is invented to reach five.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from rca.models import AssessedHypothesis, CauseFactor, WhyStep

LEVELS = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass
class Diagram:
    kind: Literal["five_whys", "fishbone"]
    hypothesis_id: str | None = None  # the cause of a 5 Whys diagram
    steps: list[WhyStep] = field(default_factory=list)
    factors: list[tuple[str, CauseFactor]] = field(default_factory=list)  # (hypothesis id, factor)


def drawn_chain(steps: list[WhyStep]) -> list[WhyStep]:
    """The chain up to the first step without evidence, that one included."""
    for index, step in enumerate(steps):
        if not step.evidence:
            return steps[: index + 1]
    return list(steps)


def distinct_factors(factors: list[tuple[str, CauseFactor]]) -> list[tuple[str, CauseFactor]]:
    """Each factor once per category: two causes that name the same factor (the same words, whatever the case
    and spacing) share one box, with the evidence of both and the first cause that named it."""
    found: dict[tuple[str, str], tuple[str, CauseFactor]] = {}
    for hypothesis_id, factor in factors:
        key = (factor.category, " ".join(factor.factor.lower().split()))
        if key in found:
            first_id, first = found[key]
            evidence = first.evidence + [item for item in factor.evidence if item not in first.evidence]
            found[key] = (first_id, first.model_copy(update={"evidence": evidence}))
        else:
            found[key] = (hypothesis_id, factor)
    return list(found.values())


def choose_diagram(hypotheses: list[AssessedHypothesis]) -> Diagram | None:
    """The diagram for these hypotheses (the strongest first, as rca/confidence.py orders them), or None
    when the agent gave no structure to draw."""
    if not hypotheses:
        return None
    main = hypotheses[0]
    clearly_best = len(hypotheses) == 1 or LEVELS[main.confidence] > LEVELS[hypotheses[1].confidence]
    if clearly_best and main.why_chain:
        return Diagram("five_whys", hypothesis_id=main.hypothesis_id, steps=drawn_chain(main.why_chain))
    level = LEVELS[main.confidence]
    tied = [item for item in hypotheses if LEVELS[item.confidence] == level] if not clearly_best else [main]
    factors = distinct_factors([(item.hypothesis_id, factor) for item in tied for factor in item.factors])
    if factors:
        return Diagram("fishbone", factors=factors)
    if main.why_chain:  # no factors given: the chain of the strongest cause is still worth drawing
        return Diagram("five_whys", hypothesis_id=main.hypothesis_id, steps=drawn_chain(main.why_chain))
    return None
