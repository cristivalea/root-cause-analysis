"""What changed from one revision of an RCA to the next (final_project_steps.md, E9).

The Technical Expert reads a new revision next to the one sent back. Computed by code from the two saved
revisions, never by a model:

- the evidence: compared by the original record it cites (LOG-…, CHG-…, RCA-…), because the evidence ids
  (EV-…) are numbered again in every run: what is new, and what is no longer in the ledger;
- the hypotheses: their ids start again at HYP-001 in every run, so a hypothesis is paired with the one of
  the previous revision whose candidate cause reads most alike (SIMILAR_CAUSE): kept (with its confidence
  before and after), new, or no longer proposed. Wording that changed a lot counts as new: the expert reads both;
- the main hypothesis: the same or another one;
- what the new revision was asked: the request of the expert it answers (as the context of the run has it, or
  else the comment of the decision on the previous revision).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from rca.models import AssessedHypothesis, RCARecord

SIMILAR_CAUSE = 0.6  # two candidate causes this alike (difflib ratio, 0 to 1) are the same hypothesis reworded


@dataclass
class HypothesisChange:
    kind: str  # "kept", "new" or "dropped"
    current: AssessedHypothesis | None
    previous: AssessedHypothesis | None
    similarity: float | None = None  # of the two texts, for a kept one


@dataclass
class Comparison:
    previous_id: str
    current_id: str
    request: str | None  # what the expert asked the new revision to answer
    new_evidence: list[str] = field(default_factory=list)  # original records, in the order of the new ledger
    dropped_evidence: list[str] = field(default_factory=list)
    hypotheses: list[HypothesisChange] = field(default_factory=list)
    main_changed: bool = False
    newly_not_checked: list[str] = field(default_factory=list)


def _alike(first: str, second: str) -> float:
    return SequenceMatcher(None, first.lower(), second.lower()).ratio()


def compare(previous: RCARecord, current: RCARecord) -> Comparison:
    before = [item.citation for item in previous.evidence]
    after = [item.citation for item in current.evidence]
    asked = previous.review.comment if previous.review and previous.review.decision == "REQUEST_MORE_DETAILS" else None
    result = Comparison(previous.revision_id, current.revision_id,
                        (current.context.expert_request if current.context else None) or asked,
                        [item for item in after if item not in before], [item for item in before if item not in after])

    unpaired = list(previous.hypotheses)
    for hypothesis in current.hypotheses:
        scored = [(_alike(hypothesis.candidate_root_cause, item.candidate_root_cause), item) for item in unpaired]
        best = max(scored, key=lambda pair: pair[0], default=(0.0, None))
        if best[1] is not None and best[0] >= SIMILAR_CAUSE:
            unpaired.remove(best[1])
            result.hypotheses.append(HypothesisChange("kept", hypothesis, best[1], round(best[0], 2)))
        else:
            result.hypotheses.append(HypothesisChange("new", hypothesis, None))
    result.hypotheses += [HypothesisChange("dropped", None, item) for item in unpaired]

    if previous.hypotheses and current.hypotheses:
        first = result.hypotheses[0]
        result.main_changed = not (first.kind == "kept" and first.previous is previous.hypotheses[0])
    else:
        result.main_changed = bool(previous.hypotheses) != bool(current.hypotheses)
    result.newly_not_checked = [item for item in current.not_checked if item not in previous.not_checked]
    return result


def previous_revision(revisions: list[RCARecord], current: RCARecord) -> RCARecord | None:
    """The revision the current one is compared with: the latest earlier revision with an analysis (a failed run
    has none). revisions: every revision of the RCA."""
    earlier = [item for item in revisions if item.revision < current.revision and item.run_status == "COMPLETED"
               and item.hypotheses]
    return max(earlier, key=lambda item: item.revision, default=None)
