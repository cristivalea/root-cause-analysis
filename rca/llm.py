"""The only module that talks to the language model (Groq).

The model proposes, the code validates: every answer is parsed into a Pydantic model
before any other part of the application can use it.
"""

import json
import logging
import time
from functools import lru_cache
from typing import TypeVar

from groq import BadRequestError, Groq, RateLimitError
from pydantic import BaseModel, ValidationError

from rca import config

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

# The Groq free tier allows a few thousand tokens per minute. When the limit is reached, the
# request waits and is sent again: 5 s, 10 s, 15 s, ... at most RATE_LIMIT_RETRIES times.
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_WAIT_STEP = 5.0
# A longer wait means the daily limit was reached; waiting inside a request does not help.
MAX_RATE_LIMIT_WAIT = 60.0
MAX_FEEDBACK_LENGTH = 2000
_sleep = time.sleep  # replaced in the tests


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


def with_feedback(user_input: str, feedback: str | None) -> str:
    """Add to the request why the previous answer was refused, so the model can correct it."""
    if not feedback:
        return user_input
    if len(feedback) > MAX_FEEDBACK_LENGTH:
        feedback = feedback[:MAX_FEEDBACK_LENGTH] + " ..."
    return (
        f"{user_input}\n\n"
        f"Your previous answer was refused for these reasons:\n{feedback}\n\n"
        "Answer again with a corrected JSON object."
    )


def _retry_after(exc: RateLimitError) -> float:
    try:
        return float(exc.response.headers.get("retry-after", 0))
    except ValueError:
        return 0.0


def _create_completion(system_prompt: str, user_input: str):
    """Send the request, waiting and sending it again while the per-minute limit is reached."""
    attempt = 0
    while True:
        try:
            return _client().chat.completions.create(
                model=config.GROQ_MODEL,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            )
        except RateLimitError as exc:
            attempt += 1
            wait = max(_retry_after(exc), RATE_LIMIT_WAIT_STEP * attempt)
            if attempt > RATE_LIMIT_RETRIES or wait > MAX_RATE_LIMIT_WAIT:
                raise
            log.warning("Groq rate limit reached, waiting %.0f s (attempt %d of %d)", wait, attempt, RATE_LIMIT_RETRIES)
            _sleep(wait)


def ask_json(instructions: str, user_input: str, schema: type[T]) -> T:
    """Send one request to the model and return the answer, validated against the schema.

    Raises LLMOutputError when the answer is not valid, so the caller can decide what to do.
    Raises groq.RateLimitError when the limit is still reached after waiting.
    """
    try:
        completion = _create_completion(build_system_prompt(instructions, schema), user_input)
    except BadRequestError as exc:
        # Groq refuses an answer that is not valid JSON and returns the failed attempt.
        error = exc.body.get("error", {}) if isinstance(exc.body, dict) else {}
        if error.get("code") != "json_validate_failed":
            raise
        raise LLMOutputError("The answer is not valid JSON.", error.get("failed_generation", "")) from exc

    return parse_output(completion.choices[0].message.content or "", schema)
