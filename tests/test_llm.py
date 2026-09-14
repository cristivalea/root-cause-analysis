"""Tests for rca.llm that run without calling the model."""

import pytest
from pydantic import BaseModel

from rca.llm import LLMOutputError, build_system_prompt, parse_output


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
