"""The only module that talks to the language models.

The model proposes, the code validates: every answer is parsed into a Pydantic model
before any other part of the application can use it.

The agents use config.GROQ_MODEL. With LLM_FALLBACK=true, a model that has reached its daily
limit is set aside and the next one of config.FALLBACK_MODELS answers (Groq, then Gemini, then
OpenRouter), so manual tests can go on when one free budget is spent. Every answer records the
model that gave it (see recording), so the interface can show which model each agent used.
"""

import contextvars
import json
import logging
import re
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator, TypeVar

import groq
import openai
from langsmith import traceable
from pydantic import BaseModel, ValidationError

from rca import config

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

# The free tiers allow a few thousand tokens or a few requests per minute. When the limit is reached,
# the request waits and is sent again: 5 s, 10 s, 15 s, ... at most RATE_LIMIT_RETRIES times.
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_WAIT_STEP = 5.0
# A longer wait means the daily limit was reached; waiting inside a request does not help.
MAX_RATE_LIMIT_WAIT = 60.0
# How long a model that reached its daily limit is set aside when the provider does not say.
DAILY_LIMIT_PAUSE = 3600.0
MAX_FEEDBACK_LENGTH = 2000
_sleep = time.sleep  # replaced in the tests

# Gemini and OpenRouter are reached through their OpenAI-compatible addresses.
OPENAI_COMPATIBLE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
}
RATE_LIMIT_ERRORS = (groq.RateLimitError, openai.RateLimitError)
STATUS_ERRORS = (groq.APIStatusError, openai.APIStatusError)
CONNECTION_ERRORS = (groq.APIConnectionError, openai.APIConnectionError)

# model -> the time (time.time()) until which it is set aside because its daily limit was reached
_exhausted: dict[str, float] = {}
# the models that answered inside recording(), in order
_used: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar("llm_models_used", default=None)


class LLMOutputError(Exception):
    """The model answered, but the answer is not valid for the requested schema.

    The raw answer is kept, so the guardrail can show the model its mistake and retry.
    """

    def __init__(self, message: str, raw_output: str):
        super().__init__(message)
        self.raw_output = raw_output


def _api_key(provider: str) -> str:
    return {"groq": config.GROQ_API_KEY, "gemini": config.GEMINI_API_KEY,
            "openrouter": config.OPENROUTER_API_KEY}.get(provider, "")


@lru_cache(maxsize=None)
def _client(provider: str):
    key = _api_key(provider)
    if not key:
        raise RuntimeError(f"The API key for {provider} is not set. Copy .env.example to .env and add your key.")
    if provider == "groq":
        return groq.Groq(api_key=key)
    if provider not in OPENAI_COMPATIBLE_URLS:
        raise RuntimeError(f"Unknown model provider '{provider}'; use groq, gemini or openrouter.")
    # max_retries=0: the waiting is done here, the same way for every provider
    return openai.OpenAI(api_key=key, base_url=OPENAI_COMPATIBLE_URLS[provider], max_retries=0)


def split_model(model: str) -> tuple[str, str]:
    """'gemini:gemini-3.5-flash' -> ('gemini', 'gemini-3.5-flash'); a name without a provider is a Groq model.
    Only the first ':' separates them: OpenRouter names end in ':free'."""
    provider, _, name = model.partition(":")
    if provider in ("groq", *OPENAI_COMPATIBLE_URLS) and name:
        return provider, name
    return "groq", model


def models() -> list[str]:
    """The models the agents may use, in order: config.GROQ_MODEL, then the fallbacks when they are on."""
    chain = [f"groq:{config.GROQ_MODEL}"] if ":" not in config.GROQ_MODEL else [config.GROQ_MODEL]
    if config.LLM_FALLBACK:
        chain += config.FALLBACK_MODELS
    unique = []
    for model in chain:
        model = "%s:%s" % split_model(model)
        if model not in unique:
            unique.append(model)
    return unique


@contextmanager
def recording() -> Iterator[list[str]]:
    """Collect the models that answer the requests sent inside the block (an agent may ask several times)."""
    used: list[str] = []
    token = _used.set(used)
    try:
        yield used
    finally:
        _used.reset(token)


def build_system_prompt(instructions: str, schema: type[BaseModel]) -> str:
    """Add the answer format to the agent instructions."""
    return (
        f"{instructions}\n\n"
        "Answer with one JSON object only, with no other text. "
        f"The object must match this JSON schema:\n{json.dumps(schema.model_json_schema())}"
    )


def parse_output(raw_output: str, schema: type[T]) -> T:
    """Validate the raw model answer against the schema. Some models wrap the JSON in a ```json block."""
    fenced = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", raw_output, re.DOTALL)
    try:
        return schema.model_validate_json(fenced.group(1) if fenced else raw_output)
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


def _retry_after(exc: Exception) -> float:
    try:
        return float(exc.response.headers.get("retry-after", 0))
    except (AttributeError, TypeError, ValueError):
        return 0.0


class DailyLimitReached(Exception):
    """The model keeps refusing for its rate limit: waiting inside the request does not help."""

    def __init__(self, error: Exception, pause: float):
        super().__init__(str(error))
        self.error = error
        self.pause = pause


# With LANGSMITH_TRACING=true every request is saved in LangSmith, inside the graph node that sent it:
# the prompts, the raw answer and the tokens. Without it the decorator does nothing.
@traceable(run_type="llm", name="LLM")
def _create_completion(model: str, system_prompt: str, user_input: str):
    """Send the request to one model, waiting and sending it again while the per-minute limit is reached."""
    provider, name = split_model(model)
    attempt = 0
    while True:
        try:
            return _client(provider).chat.completions.create(
                model=name,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            )
        except RATE_LIMIT_ERRORS as exc:
            attempt += 1
            asked = _retry_after(exc)
            wait = max(asked, RATE_LIMIT_WAIT_STEP * attempt)
            if attempt > RATE_LIMIT_RETRIES or wait > MAX_RATE_LIMIT_WAIT:
                raise DailyLimitReached(exc, asked if asked > MAX_RATE_LIMIT_WAIT else DAILY_LIMIT_PAUSE) from exc
            log.warning("%s rate limit reached, waiting %.0f s (attempt %d of %d)", model, wait, attempt,
                        RATE_LIMIT_RETRIES)
            _sleep(wait)


def _record(model: str) -> None:
    used = _used.get()
    if used is not None:
        used.append(model)


def _send(model: str, system_prompt: str, user_input: str):
    provider, name = split_model(model)
    try:
        return _create_completion(model, system_prompt, user_input,
                                  langsmith_extra={"metadata": {"ls_provider": provider, "ls_model_name": name}})
    except groq.BadRequestError as exc:
        # Groq refuses an answer that is not valid JSON and returns the failed attempt.
        error = exc.body.get("error", {}) if isinstance(exc.body, dict) else {}
        if error.get("code") != "json_validate_failed":
            raise
        _record(model)
        raise LLMOutputError("The answer is not valid JSON.", error.get("failed_generation", "")) from exc


def _can_fall_back(exc: Exception) -> bool:
    """A failure that another model may not have: a request too large for this model (413),
    a model that is not available (404) or a provider that is down (5xx, no connection)."""
    if isinstance(exc, CONNECTION_ERRORS):
        return True
    return isinstance(exc, STATUS_ERRORS) and (exc.status_code in (404, 413) or exc.status_code >= 500)


def ask_json(instructions: str, user_input: str, schema: type[T]) -> T:
    """Send one request and return the answer, validated against the schema.

    The first model of models() that is not set aside answers. Raises LLMOutputError when the answer
    is not valid, so the caller can decide what to do; raises the rate limit error of the last model
    when every model has reached its limit.
    """
    system_prompt = build_system_prompt(instructions, schema)
    chain = models()
    last_error: Exception | None = None
    for index, model in enumerate(chain):
        is_last = index == len(chain) - 1
        if _exhausted.get(model, 0) > time.time() and not is_last:
            continue
        if len(chain) > 1 and not _api_key(split_model(model)[0]):
            log.warning("%s skipped: its API key is not set", model)
            continue
        try:
            completion = _send(model, system_prompt, user_input)
        except DailyLimitReached as exc:
            _exhausted[model] = time.time() + exc.pause
            last_error = exc.error
            if not is_last:
                log.warning("%s reached its limit; set aside for %.0f min, trying %s", model, exc.pause / 60,
                            chain[index + 1])
            continue
        except Exception as exc:
            if is_last or not _can_fall_back(exc):
                raise
            last_error = exc
            log.warning("%s failed (%s); trying %s", model, type(exc).__name__, chain[index + 1])
            continue

        _record(model)
        return parse_output(completion.choices[0].message.content or "", schema)

    if last_error is None:
        raise RuntimeError("No model can be used: set GROQ_API_KEY (and the keys of the fallback models) in .env.")
    raise last_error
