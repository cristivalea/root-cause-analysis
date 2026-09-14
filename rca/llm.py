"""The only module that talks to the language model (Groq).

The model proposes, the code validates: every answer is parsed into a Pydantic model
before any other part of the application can use it.
"""

import json
from functools import lru_cache
from typing import TypeVar

from groq import BadRequestError, Groq
from pydantic import BaseModel, ValidationError

from rca import config

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    """The model answered, but the answer is not valid for the requested schema.

    The raw answer is kept, so the guardrail can show the model its mistake and retry.
    """

    def __init__(self, message: str, raw_output: str):
        super().__init__(message)
        self.raw_output = raw_output


@lru_cache(maxsize=1)
def _client() -> Groq:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
    return Groq(api_key=config.GROQ_API_KEY)


def build_system_prompt(instructions: str, schema: type[BaseModel]) -> str:
    """Add the answer format to the agent instructions."""
    return (
        f"{instructions}\n\n"
        "Answer with one JSON object only, with no other text. "
        f"The object must match this JSON schema:\n{json.dumps(schema.model_json_schema())}"
    )


def parse_output(raw_output: str, schema: type[T]) -> T:
    """Validate the raw model answer against the schema."""
    try:
        return schema.model_validate_json(raw_output)
    except ValidationError as exc:
        raise LLMOutputError(f"The answer does not match {schema.__name__}: {exc}", raw_output) from exc


def ask_json(instructions: str, user_input: str, schema: type[T]) -> T:
    """Send one request to the model and return the answer, validated against the schema.

    Raises LLMOutputError when the answer is not valid, so the caller can decide what to do.
    """
    try:
        completion = _client().chat.completions.create(
            model=config.GROQ_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": build_system_prompt(instructions, schema)},
                {"role": "user", "content": user_input},
            ],
        )
    except BadRequestError as exc:
        # Groq refuses an answer that is not valid JSON and returns the failed attempt.
        error = exc.body.get("error", {}) if isinstance(exc.body, dict) else {}
        if error.get("code") != "json_validate_failed":
            raise
        raise LLMOutputError("The answer is not valid JSON.", error.get("failed_generation", "")) from exc

    return parse_output(completion.choices[0].message.content or "", schema)
