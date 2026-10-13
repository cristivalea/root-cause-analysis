"""Tests for rca.llm that run without calling the model."""

from types import SimpleNamespace

import httpx
import openai
import pytest
from groq import RateLimitError
from pydantic import BaseModel

from rca import config, llm
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


@pytest.fixture(autouse=True)
def one_model(monkeypatch):
    """Every test starts with only GROQ_MODEL and no model set aside."""
    monkeypatch.setattr(config, "GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(config, "LLM_FALLBACK", False)
    monkeypatch.setattr(llm, "_exhausted", {})


@pytest.fixture
def fake_groq(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(llm, "_sleep", waits.append)

    def install(*results):
        completions = FakeCompletions(*results)
        monkeypatch.setattr(llm, "_client",
                            lambda provider: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
        return completions, waits

    return install


@pytest.fixture
def fake_providers(monkeypatch):
    """One fake client per model: {model name: [results]}. Returns the model names in the order they were asked."""
    asked: list[str] = []
    monkeypatch.setattr(llm, "_sleep", lambda seconds: None)
    monkeypatch.setattr(config, "LLM_FALLBACK", True)
    monkeypatch.setattr(config, "FALLBACK_MODELS", ["groq:openai/gpt-oss-20b", "gemini:gemini-3.5-flash",
                                                    "openrouter:nvidia/nemotron-3-super-120b-a12b:free"])
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setattr(config, key, "test-key")

    def install(results: dict[str, list]):
        def create(model, **kwargs):
            asked.append(model)
            result = results[model].pop(0)
            if isinstance(result, Exception):
                raise result
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=result))])
        completions = SimpleNamespace(create=create)
        monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
        return asked

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


# Fallback to the next model ------------------------------------------------------------

VALID = '{"service": "Payment API", "symptoms": []}'


def status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return openai.APIStatusError("error", response=httpx.Response(status, request=request), body=None)


def test_without_fallback_only_groq_model_is_used():
    assert llm.models() == ["groq:openai/gpt-oss-120b"]


def test_fallback_order_groq_then_gemini_then_openrouter(monkeypatch):
    monkeypatch.setattr(config, "LLM_FALLBACK", True)
    monkeypatch.setattr(config, "FALLBACK_MODELS", ["openai/gpt-oss-20b", "gemini:gemini-3.5-flash",
                                                    "openrouter:nvidia/nemotron-3-super-120b-a12b:free"])

    assert llm.models() == ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b", "gemini:gemini-3.5-flash",
                            "openrouter:nvidia/nemotron-3-super-120b-a12b:free"]
    assert llm.split_model("openrouter:nvidia/nemotron-3-super-120b-a12b:free") == (
        "openrouter", "nvidia/nemotron-3-super-120b-a12b:free")


def test_daily_limit_moves_to_the_next_model_and_sets_the_first_aside(fake_providers):
    asked = fake_providers({"openai/gpt-oss-120b": [rate_limit_error("3600")],
                            "openai/gpt-oss-20b": [VALID, VALID]})

    with llm.recording() as used:
        ask_json("instructions", "input", Answer)
        ask_json("instructions", "input", Answer)

    assert asked == ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "openai/gpt-oss-20b"]  # 120b is not asked again
    assert used == ["groq:openai/gpt-oss-20b", "groq:openai/gpt-oss-20b"]


def test_every_model_at_its_limit_raises_the_rate_limit_error(fake_providers):
    fake_providers({"openai/gpt-oss-120b": [rate_limit_error("3600")], "openai/gpt-oss-20b": [rate_limit_error("3600")],
                    "gemini-3.5-flash": [openai.RateLimitError("quota", response=httpx.Response(
                        429, request=httpx.Request("POST", "https://x")), body=None)] * 6,
                    "nvidia/nemotron-3-super-120b-a12b:free": [rate_limit_error("3600")]})

    with pytest.raises(RateLimitError):
        ask_json("instructions", "input", Answer)


def test_request_too_large_or_provider_down_moves_on_without_setting_aside(fake_providers):
    asked = fake_providers({"openai/gpt-oss-120b": [status_error(413), VALID],
                            "openai/gpt-oss-20b": [status_error(503)],
                            "gemini-3.5-flash": [VALID]})

    ask_json("instructions", "input", Answer)
    ask_json("instructions", "input", Answer)

    assert asked == ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "gemini-3.5-flash", "openai/gpt-oss-120b"]


def test_an_invalid_answer_is_not_sent_to_another_model(fake_providers):
    asked = fake_providers({"openai/gpt-oss-120b": ["not json"]})

    with llm.recording() as used, pytest.raises(LLMOutputError):
        ask_json("instructions", "input", Answer)

    assert asked == ["openai/gpt-oss-120b"]  # the guardrail asks again, with the problems
    assert used == ["groq:openai/gpt-oss-120b"]


def test_json_in_a_code_block_is_accepted():
    assert parse_output('```json\n{"service": "Payment API", "symptoms": []}\n```', Answer).service == "Payment API"


# Metering ------------------------------------------------------------------------------

def with_usage(content: str, prompt_tokens: int, completion_tokens: int, reasoning_tokens: int | None = None,
               finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
                           usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                                                 completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens)))


def test_metering_records_the_tokens_and_the_outcome_of_each_request(monkeypatch):
    results = [with_usage(VALID, 1200, 80, 30), with_usage("not json", 1300, 40, 40, "length")]
    completions = SimpleNamespace(create=lambda **kwargs: results.pop(0))
    monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(chat=SimpleNamespace(completions=completions)))

    with llm.metering() as calls:
        ask_json("instructions", "input", Answer)
        with pytest.raises(LLMOutputError):
            ask_json("instructions", "input", Answer)

    assert [(c["model"], c["input_tokens"], c["output_tokens"], c["outcome"]) for c in calls] == [
        ("groq:openai/gpt-oss-120b", 1200, 80, "valid"),
        ("groq:openai/gpt-oss-120b", 1300, 40, "invalid"),
    ]
    # the thinking of a reasoning model and an answer cut by the output limit are kept apart
    assert [(c["reasoning_tokens"], c["finish_reason"]) for c in calls] == [(30, "stop"), (40, "length")]
    assert all(call["latency_seconds"] >= 0 and call["waited_seconds"] == 0 for call in calls)


def test_metering_keeps_the_rate_limit_waits_apart_from_the_latency(fake_groq):
    fake_groq(rate_limit_error("1"), VALID)

    with llm.metering() as calls:
        ask_json("instructions", "input", Answer)

    assert len(calls) == 1
    assert calls[0]["waited_seconds"] == 5.0  # the wait is counted, not slept: _sleep is replaced
    assert calls[0]["input_tokens"] is None  # the fake answer says nothing about the tokens
    assert calls[0]["latency_seconds"] < 5.0


def test_metering_records_the_error_of_a_model_that_failed(fake_providers):
    fake_providers({"openai/gpt-oss-120b": [status_error(503)], "openai/gpt-oss-20b": [VALID]})

    with llm.metering() as calls:
        ask_json("instructions", "input", Answer)

    assert [(call["model"], call["outcome"]) for call in calls] == [
        ("groq:openai/gpt-oss-120b", "APIStatusError"), ("groq:openai/gpt-oss-20b", "valid")]


def test_without_metering_nothing_is_recorded(fake_groq):
    fake_groq(VALID)

    ask_json("instructions", "input", Answer)  # no error: the measures are only kept inside metering()


def test_the_reasoning_effort_is_sent_only_to_the_gpt_oss_models_and_only_when_set(monkeypatch):
    sent = []
    completions = SimpleNamespace(create=lambda **kwargs: sent.append(kwargs) or with_usage(VALID, 10, 5))
    monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(chat=SimpleNamespace(completions=completions)))

    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "")
    ask_json("instructions", "input", Answer)
    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "low")
    ask_json("instructions", "input", Answer)
    monkeypatch.setattr(config, "GROQ_MODEL", "groq:llama-3.3-70b-versatile")
    ask_json("instructions", "input", Answer)

    assert [call.get("reasoning_effort") for call in sent] == [None, "low", None]


def test_the_compact_schema_drops_titles_and_developer_notes_but_keeps_every_field(monkeypatch):
    from rca.models import DraftRCA

    full = build_system_prompt("Do it.", DraftRCA)
    monkeypatch.setattr(config, "LLM_COMPACT_SCHEMA", True)
    compact = build_system_prompt("Do it.", DraftRCA)

    assert len(compact) < len(full) - 1000  # about 270 tokens fewer on every request of the reasoning agent
    assert '"title"' not in compact and "a model writes in the order" not in compact
    for field in ("supporting_evidence", "contradicting_evidence", "why_chain", "single_hypothesis_reason"):
        assert f'"{field}"' in compact


def test_the_output_limit_is_sent_only_when_asked_and_fills_what_the_request_limit_leaves(monkeypatch):
    sent = []
    completions = SimpleNamespace(create=lambda **kwargs: sent.append(kwargs) or with_usage(VALID, 10, 5))
    monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(chat=SimpleNamespace(completions=completions)))

    ask_json("instructions", "input", Answer)
    monkeypatch.setattr(config, "LLM_EXPLICIT_OUTPUT_LIMIT", True)
    ask_json("instructions", "x" * 16000, Answer)  # about 5000 tokens of input

    assert "max_completion_tokens" not in sent[0]
    assert config.LLM_OUTPUT_RESERVE_TOKENS <= sent[1]["max_completion_tokens"] < 8000 - 5000


def test_the_groq_free_tier_has_a_smaller_request_limit_than_the_other_providers():
    assert llm.request_limit("groq:openai/gpt-oss-120b") == config.LLM_REQUEST_LIMIT_TOKENS
    assert llm.request_limit("gemini:gemini-3.6-flash") == config.LLM_LARGE_REQUEST_LIMIT_TOKENS
