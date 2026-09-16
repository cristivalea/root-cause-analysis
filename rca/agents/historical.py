"""Historical RCA Agent: classify retrieved RCA sections and create evidence records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from rca.llm import ask_json
from rca.models import Evidence, InvestigationPlan


class HistoricalRCADecision(BaseModel):
    """LLM decision for one retrieved historical RCA section."""

    citation: str
    relevant: bool
    reason: str = Field(min_length=1)


class HistoricalRCAReview(BaseModel):
    """Validated classification of all historical RCA results."""

    decisions: list[HistoricalRCADecision]


def _result_id(result: dict[str, Any]) -> str:
    return str(result.get("id") or result.get("citation") or result.get("document_id") or "")


def _result_text(result: dict[str, Any]) -> str:
    return str(result.get("document") or result.get("text") or result.get("description") or "")


def _result_metadata(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") or result.get("metadatas") or {}
    return metadata if isinstance(metadata, dict) else {}


def _timestamp(metadata: dict[str, Any]) -> datetime | None:
    value = metadata.get("completion_date")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _prompt_input(plan: InvestigationPlan, results: list[dict[str, Any]]) -> str:
    payload = {
        "service": plan.service,
        "search_queries": plan.search_queries,
        "historical_results": [
            {
                "citation": _result_id(result),
                "text": _result_text(result),
                "metadata": _result_metadata(result),
            }
            for result in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def review_historical_rcas(
    plan: InvestigationPlan,
    results: list[dict[str, Any]],
) -> tuple[HistoricalRCAReview, list[Evidence]]:
    """Classify retrieved RCA sections and convert relevant ones into ledger evidence."""

    review = ask_json(
        instructions=(
            "You are the Historical RCA Agent. Review each retrieved historical RCA section "
            "against the investigation service and search queries. Mark a result relevant only "
            "when its service and symptoms meaningfully match the investigation. A similar word "
            "from another service is not enough. Return one decision for every input result, "
            "using the exact citation provided. Explain every decision briefly."
        ),
        user_input=_prompt_input(plan, results),
        schema=HistoricalRCAReview,
    )

    result_by_id = {_result_id(result): result for result in results}
    evidence: list[Evidence] = []
    for decision in review.decisions:
        result = result_by_id.get(decision.citation)
        if not decision.relevant or result is None:
            continue

        metadata = _result_metadata(result)
        section_name = metadata.get("section_name", "unknown section")
        description = f"Relevant historical RCA section '{section_name}': {decision.reason}"
        evidence.append(
            Evidence(
                evidence_id=f"EV-{len(evidence) + 1:03d}",
                type="HISTORICAL_RCA",
                source=str(metadata.get("document_id", decision.citation)),
                description=description,
                citation=decision.citation,
                timestamp=_timestamp(metadata),
            )
        )

    return review, evidence
