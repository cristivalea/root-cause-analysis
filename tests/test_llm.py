"""Tests for rca.llm that run without calling the model."""

from types import SimpleNamespace

import httpx
import pytest
from groq import RateLimitError
from pydantic import BaseModel

from rca import llm
from rca.llm import LLMOutputError, ask_json, build_system_prompt, parse_output, with_feedback


class Answer(BaseModel):
    service: str
    symptoms: list[str]


def test_valid_answer_is_parsed():
    answer = parse_output('{"service": "Payment API", "symptoms": ["HTTP 500"]}', Answer)

    assert answer == Answer(service="Payment API", symptoms=["HTTP 500"])


def test_text_that_is_not_json_is_refused():
    with pytest.raises(LLMOutputError) as error:
        parse_output("The affected service is Payment API.", Answer)

    assert error.value.raw_output == "The affected service is Payment API."


def test_json_with_a_missing_field_is_refused():
    with pytest.raises(LLMOutputError, match="symptoms"):
        parse_output('{"service": "Payment API"}', Answer)


def test_json_with_a_wrong_type_is_refused():
    with pytest.raises(LLMOutputError, match="symptoms"):
        parse_output('{"service": "Payment API", "symptoms": "HTTP 500"}', Answer)


def test_system_prompt_contains_instructions_and_schema():
    prompt = build_system_prompt("You plan RCA investigations.", Answer)

    assert prompt.startswith("You plan RCA investigations.")
    assert '"service"' in prompt
    assert '"symptoms"' in prompt


# Rate limit and feedback ---------------------------------------------------------------

def rate_limit_error(retry_after: str) -> RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, headers={"retry-after": retry_after}, request=request)
    return RateLimitError("Rate limit reached", response=response, body=None)


class FakeCompletions:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=result))])


@pytest.fixture
def fake_groq(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(llm, "_sleep", waits.append)

    def install(*results):
        completions = FakeCompletions(*results)
        monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
        return completions, waits

    return install


def test_rate_limit_waits_and_sends_the_request_again(fake_groq):
    completions, waits = fake_groq(
        rate_limit_error("1"), rate_limit_error("12"), '{"service": "Payment API", "symptoms": []}'
    )

    answer = ask_json("instructions", "input", Answer)

    assert answer.service == "Payment API"
    assert completions.calls == 3
    assert waits == [5.0, 12.0]  # at least 5 s, 10 s, ... or longer when Groq asks for it


def test_daily_limit_is_not_waited_for(fake_groq):
    completions, waits = fake_groq(rate_limit_error("3600"))

    with pytest.raises(RateLimitError):
        ask_json("instructions", "input", Answer)

    assert waits == []


def test_rate_limit_gives_up_after_the_retries(fake_groq):
    errors = [rate_limit_error("0") for _ in range(llm.RATE_LIMIT_RETRIES + 1)]
    completions, waits = fake_groq(*errors)

    with pytest.raises(RateLimitError):
        ask_json("instructions", "input", Answer)

    assert completions.calls == llm.RATE_LIMIT_RETRIES + 1
    assert len(waits) == llm.RATE_LIMIT_RETRIES


def test_feedback_is_added_to_the_request():
    assert with_feedback("input", None) == "input"

    request = with_feedback("input", "- HYP-001 cites EV-099")

    assert request.startswith("input")
    assert "Your previous answer was refused" in request and "EV-099" in request
    assert len(with_feedback("input", "x" * 10_000)) < 2_300
