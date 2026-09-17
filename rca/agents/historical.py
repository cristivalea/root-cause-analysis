"""Historical RCA Agent: classify retrieved RCA sections and create evidence records."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from rca.llm import LLMOutputError, ask_json
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
    return str(result.get("id") or "")


def _result_text(result: dict[str, Any]) -> str:
    return str(result.get("document") or result.get("text") or "")


def _result_metadata(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") or result.get("metadatas") or {}
    return metadata if isinstance(metadata, dict) else {}


def _normalize_rca_id(raw_id: str) -> str:
    """Extract clean document ID (e.g., 'RCA-2025-00114') stripping section suffixes."""
    cleaned = raw_id.strip()
    match = re.match(r"(RCA-\d{4}-\d+)", cleaned)
    if match:
        return match.group(1)
    return cleaned.split("::")[0].strip()


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
    if not results:
        return HistoricalRCAReview(decisions=[]), []

    result_by_id = {_result_id(result): result for result in results}

    review = ask_json(
        instructions=(
            "You are the Historical RCA Agent. Review each retrieved past record (an RCA or an "
            "incident) against the investigation service and search queries. "
            "A record is relevant only when it is about the same service as the investigation and "
            "its symptoms meaningfully match. The search finds records that use similar words, and "
            "similar words are not enough: a past record about another service is not relevant, "
            "however close its wording is (for example a connection pool problem in a payroll batch "
            "is not evidence about a payment service). "
            "Return one decision for every input result, using the exact citation provided, and "
            "explain every decision briefly."
        ),
        user_input=_prompt_input(plan, results),
        schema=HistoricalRCAReview,
    )

    # 1. Validare anti-halucinare și decizii lipsă.
    # Greșelile modelului sunt raportate cu LLMOutputError, ca în restul aplicației: pipeline-ul le
    # tratează la fel ca pe un răspuns invalid și continuă investigația fără istoric.
    expected_citations = set(result_by_id.keys())
    received_citations = {decision.citation for decision in review.decisions}

    invented_citations = received_citations - expected_citations
    if invented_citations:
        raise LLMOutputError(
            f"The answer cites results that were not retrieved: {sorted(invented_citations)}",
            review.model_dump_json(),
        )

    missing_citations = expected_citations - received_citations
    if missing_citations:
        raise LLMOutputError(
            f"The answer has no decision for these results: {sorted(missing_citations)}",
            review.model_dump_json(),
        )

    # 2. Agregare evidențe per document_id (pentru a evita creșterea artificială a încrederii)
    evidence: list[Evidence] = []
    seen_rca_ids: set[str] = set()

    for decision in review.decisions:
        if not decision.relevant:
            continue

        result = result_by_id[decision.citation]
        metadata = _result_metadata(result)
        
        # ID-ul curat: preferăm metadata['document_id'], altfel fallback pe parsarea citation-ului
        raw_doc_id = metadata.get("document_id") or decision.citation
        clean_rca_id = _normalize_rca_id(str(raw_doc_id))

        if clean_rca_id in seen_rca_ids:
            continue

        seen_rca_ids.add(clean_rca_id)
        section_name = metadata.get("section_name", "historical context")
        description = f"Relevant historical RCA '{clean_rca_id}' ({section_name}): {decision.reason}"

        evidence.append(
            Evidence(
                evidence_id=f"EV-{len(evidence) + 1:03d}",
                type="HISTORICAL_RCA",
                source=clean_rca_id,
                description=description,
                citation=clean_rca_id,
                timestamp=_timestamp(metadata),
            )
        )

    return review, evidence
