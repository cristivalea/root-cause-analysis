"""The judge of the evaluations: an LLM that compares an answer of the application with the answer key.

Only the evaluation scripts use it, never the agents. By default it is a Gemini model (config.JUDGE_MODEL)
reached through the OpenAI-compatible address of Google AI Studio, for two reasons: a judge of another
family than the agents does not favour their way of writing, and its free budget is separate from the
Groq budget the agents need. A model whose name does not start with "gemini" is sent to Groq instead.
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from rca import config
from rca.llm import LLMOutputError

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_OPENAI_URL = "https://api.groq.com/openai/v1"
MAX_RETRIES = 6  # the OpenAI client waits and retries on 429 (rate limit) and on server errors

T = TypeVar("T", bound=BaseModel)


def connection(model: str) -> tuple[str, str]:
    """The API key and the address for a judge model."""
    if model.startswith("gemini"):
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set; add it to .env.")
        return config.GEMINI_API_KEY, GEMINI_OPENAI_URL
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set; add it to .env.")
    return config.GROQ_API_KEY, GROQ_OPENAI_URL


def ask_json(instructions: str, user_input: str, schema: type[T], model: str | None = None) -> T:
    """Ask the judge and return its answer as the schema. Raises LLMOutputError for an invalid answer."""
    from openai import OpenAI

    model = model or config.JUDGE_MODEL
    api_key, base_url = connection(model)
    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=MAX_RETRIES)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": f"{instructions}\n\nAnswer with one JSON object that matches this JSON "
                                          f"schema, and nothing else:\n{json.dumps(schema.model_json_schema())}"},
            {"role": "user", "content": user_input},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    try:
        return schema.model_validate_json(raw)
    except ValidationError as exc:
        raise LLMOutputError(f"The judge answer does not match {schema.__name__}: {exc}", raw) from exc
