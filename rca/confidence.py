"""Confidence calculation: HIGH, MEDIUM or LOW, from rules on the cited evidence (doc 06, 6.5).

The model writes the reasons; the code decides the level, so the level can be explained,
tuned and defended. Points are counted once per kind of evidence:

| Supporting evidence                                                        | Points |
|----------------------------------------------------------------------------|--------|
| Log lines of the symptom                                                   | 2      |
| A change on the service or a direct dependency, made before the first error | 2      |
| A past RCA with the same cause on the same service                         | 2      |
| A similar past incident                                                    | 1      |
| A CMDB dependency that confirms the technical path                         | 1      |

Levels: 5 or more points from at least 3 kinds of evidence is HIGH; 5 or more from only 2
kinds, or 3-4 points, is MEDIUM; 2 or less is LOW. Without log evidence the level cannot be
HIGH. Contradicting evidence lowers the level by one band.

Decision of the team (differs from doc 06, which says "before detection"): a change earns
points only if it was made before the first error in the logs. A change made after the first
error cannot have caused it. Without log evidence, the detection time is used.
"""

from datetime import datetime, timezone

from rca.models import AssessedHypothesis, ConfidenceLevel, DraftRCA, Evidence, EvidenceType, Hypothesis

POINTS: dict[EvidenceType, int] = {
    "LOG": 2,
    "CHANGE": 2,
    "HISTORICAL_RCA": 2,
    "HISTORICAL_INCIDENT": 1,
    "CMDB": 1,
}
REASONS: dict[EvidenceType, str] = {
    "LOG": "Log evidence of the symptom",
    "CHANGE": "Change on the affected service or a direct dependency, before the first error",
    "HISTORICAL_RCA": "Past RCA with the same cause on the same service",
    "HISTORICAL_INCIDENT": "Similar past incident",
    "CMDB": "CMDB dependency confirms the technical path",
}
HIGH_MIN_POINTS = 5
HIGH_MIN_SOURCES = 3
MEDIUM_MIN_POINTS = 3
BANDS: list[ConfidenceLevel] = ["LOW", "MEDIUM", "HIGH"]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def first_error_time(evidence: list[Evidence], detected_at: datetime) -> datetime:
    """The earliest log evidence in the ledger, or the detection time when there is none."""
    log_times = [_as_utc(item.timestamp) for item in evidence if item.type == "LOG" and item.timestamp]
    return min(log_times, default=_as_utc(detected_at))


def assess_hypothesis(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    first_error: datetime,
) -> AssessedHypothesis:
    reasons: list[str] = []
    kinds: set[EvidenceType] = set()

    for evidence_id in hypothesis.supporting_evidence:
        item = evidence_by_id.get(evidence_id)
        if item is None:  # the guardrail already refuses unknown ids
            continue
        if item.type == "CHANGE":
            if item.timestamp is None:
                reasons.append(f"Change {evidence_id} has no time, so it earns no points.")
                continue
            if _as_utc(item.timestamp) >= first_error:
                reasons.append(
                    f"Change {evidence_id} was made after the first error ({first_error:%H:%M} UTC), "
                    "so it earns no points."
                )
                continue
        kinds.add(item.type)

    points = sum(POINTS[kind] for kind in kinds)
    reasons = [f"{REASONS[kind]} (+{POINTS[kind]})." for kind in POINTS if kind in kinds] + reasons

    if points >= HIGH_MIN_POINTS and len(kinds) >= HIGH_MIN_SOURCES:
        level: ConfidenceLevel = "HIGH"
        reasons.append(f"{points} points from {len(kinds)} different sources: HIGH.")
    elif points >= HIGH_MIN_POINTS:
        level = "MEDIUM"
        reasons.append(f"{points} points but from only {len(kinds)} different sources: MEDIUM.")
    elif points >= MEDIUM_MIN_POINTS:
        level = "MEDIUM"
        reasons.append(f"{points} points: MEDIUM.")
    else:
        level = "LOW"
        reasons.append(f"{points} points: LOW.")

    if level == "HIGH" and "LOG" not in kinds:
        level = "MEDIUM"
        reasons.append("No log evidence, so it cannot be HIGH: MEDIUM.")

    if hypothesis.contradicting_evidence:
        level = BANDS[max(BANDS.index(level) - 1, 0)]
        reasons.append(
            f"Contradicting evidence {', '.join(hypothesis.contradicting_evidence)} "
            f"lowers the level by one band: {level}."
        )

    return AssessedHypothesis(
        **hypothesis.model_dump(),
        confidence=level,
        confidence_points=points,
        confidence_reasons=reasons,
    )


def assess_draft(draft: DraftRCA, evidence: list[Evidence], detected_at: datetime) -> list[AssessedHypothesis]:
    """All hypotheses with their confidence, the strongest first."""
    evidence_by_id = {item.evidence_id: item for item in evidence}
    first_error = first_error_time(evidence, detected_at)
    assessed = [assess_hypothesis(hypothesis, evidence_by_id, first_error) for hypothesis in draft.hypotheses]
    return sorted(assessed, key=lambda item: (-BANDS.index(item.confidence), -item.confidence_points))


def is_weakly_supported(hypotheses: list[AssessedHypothesis]) -> bool:
    """A draft is weakly supported when no hypothesis is better than LOW."""
    return all(item.confidence == "LOW" for item in hypotheses)
