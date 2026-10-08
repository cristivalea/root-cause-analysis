"""The judge of the evaluations: which service a model goes to, and how its answer is checked."""

from types import SimpleNamespace

import openai
import pytest
from pydantic import BaseModel

from rca import config, judge
from rca.llm import LLMOutputError


class Verdict(BaseModel):
    is_match: bool
    reason: str


def fake_client(answer: str, calls: list):
    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])

    return Client


def test_a_gemini_model_goes_to_google_and_any_other_to_groq(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "groq-key")

    assert judge.connection("gemini-3.5-flash") == ("gemini-key", judge.GEMINI_OPENAI_URL)
    assert judge.connection("openai/gpt-oss-120b") == ("groq-key", judge.GROQ_OPENAI_URL)


def test_a_missing_key_is_reported(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        judge.connection("gemini-3.5-flash")


def test_the_answer_is_checked_against_the_schema(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", fake_client('{"is_match": true, "reason": "Same mechanism."}', calls))

    verdict = judge.ask_json("Compare.", "cause vs hypothesis", Verdict, model="gemini-3.5-flash")

    assert verdict == Verdict(is_match=True, reason="Same mechanism.")
    assert calls[0]["base_url"] == judge.GEMINI_OPENAI_URL
    assert calls[1]["model"] == "gemini-3.5-flash" and calls[1]["temperature"] == 0
    assert '"is_match"' in calls[1]["messages"][0]["content"]  # the schema is part of the instructions


def test_an_answer_that_does_not_match_the_schema_is_refused(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(openai, "OpenAI", fake_client('{"match": "maybe"}', []))

    with pytest.raises(LLMOutputError, match="Verdict"):
        judge.ask_json("Compare.", "cause vs hypothesis", Verdict, model="gemini-3.5-flash")
