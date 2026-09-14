"""Test that calls the real Groq API. Run it with: python -m pytest -m live"""

import pytest
from pydantic import BaseModel

from rca import config
from rca.llm import ask_json

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not config.GROQ_API_KEY, reason="GROQ_API_KEY is not set"),
]


class IncidentSummary(BaseModel):
    service: str
    symptoms: list[str]


def test_model_returns_a_valid_structured_answer():
    answer = ask_json(
        instructions="You read IT incidents and extract the affected service and the symptoms.",
        user_input=(
            "Payment API intermittent failures. Customers saw HTTP 500 responses, "
            "database connection timeouts and latency above 5 seconds."
        ),
        schema=IncidentSummary,
    )

    assert isinstance(answer, IncidentSummary)
    assert "payment" in answer.service.lower()
    assert len(answer.symptoms) >= 2
