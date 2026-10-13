"""The only module that talks to the language models.

The model proposes, the code validates: every answer is parsed into a Pydantic model
before any other part of the application can use it.

The agents use config.GROQ_MODEL. With LLM_FALLBACK=true, a model that has reached its daily
limit is set aside and the next one of config.FALLBACK_MODELS answers (Groq, then Gemini, then
OpenRouter), so manual tests can go on when one free budget is spent. Every answer records the
model that gave it (see recording), so the interface can show which model each agent used, and
every request can be measured (see metering): tokens, latency and whether the answer was valid.
"""

import contextvars
import json
import logging
import re
import time
from collections.abc import Callable
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
# one entry per request sent inside metering(), in order
_calls: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar("llm_calls", default=None)
# the seconds the current request spent waiting for a rate limit, kept apart from its latency
_waited: contextvars.ContextVar[list[float] | None] = contextvars.ContextVar("llm_waited", default=None)


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


@contextmanager
def metering() -> Iterator[list[dict]]:
    """Collect one entry per request sent inside the block, for the measurements of the agents:
    model, input_tokens, output_tokens (None when the provider did not say), latency_seconds (the
    request itself), waited_seconds (rate limit pauses) and outcome: "valid", "invalid" (an answer
    that does not match the schema) or the name of the error that stopped the request."""
    calls: list[dict] = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


def _meter(model: str, started: float, waits: list[float], outcome: str, completion=None) -> None:
    calls = _calls.get()
    if calls is None:
        return
    waited = sum(waits)
    usage = getattr(completion, "usage", None)
    choices = getattr(completion, "choices", None) or [None]
    calls.append({
        "model": model,
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        # of the output, the tokens a reasoning model (gpt-oss) spent thinking before it wrote the answer
        "reasoning_tokens": getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None),
        "finish_reason": getattr(choices[0], "finish_reason", None),  # "length": the answer was cut
        "latency_seconds": round(time.monotonic() - started - waited, 2),
        "waited_seconds": round(waited, 2),
        "outcome": outcome,
    })


def compact_schema(schema: type[BaseModel]) -> str:
    """The JSON schema of the answer, as the model needs it: without the titles pydantic adds (the field
    names already say them) and without the docstrings of the models, which are notes for the developers;
    the descriptions of the fields stay. Written without spaces (V3 of E10)."""

    def strip(node, in_properties=False):
        if isinstance(node, dict):
            return {key: strip(value, key == "properties") for key, value in node.items()
                    if in_properties or (key != "title" and not (key == "description" and "properties" in node))}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return json.dumps(strip(schema.model_json_schema()), separators=(",", ":"))


def build_system_prompt(instructions: str, schema: type[BaseModel]) -> str:
    """Add the answer format to the agent instructions."""
    written = compact_schema(schema) if config.LLM_COMPACT_SCHEMA else json.dumps(schema.model_json_schema())
    return (
        f"{instructions}\n\n"
        "Answer with one JSON object only, with no other text. "
        f"The object must match this JSON schema:\n{written}"
    )


# Characters per token of the requests of this application (JSON, ids, English), measured on the requests of
# the baseline (3.36); a little lower, so the estimate errs on the side of a smaller request.
CHARS_PER_TOKEN = 3.2
BUDGET_MARGIN_TOKENS = 300


def request_limit(model: str | None = None) -> int:
    """The most tokens one request to the model may count, its answer included: the 8000 tokens of the Groq
    free tier, or the larger limit of the other providers. Without a model: the model that answers next."""
    if model is None:
        usable = [item for item in models() if _exhausted.get(item, 0) <= time.time()]
        model = (usable or models())[0]
    if split_model(model)[0] == "groq":
        return config.LLM_REQUEST_LIMIT_TOKENS
    return config.LLM_LARGE_REQUEST_LIMIT_TOKENS


def input_budget(instructions: str, schema: type[BaseModel]) -> int:
    """The characters the user input of a request may have, so that the whole request (instructions, schema,
    input and the answer the provider reserves) stays under the request limit of the model (request_limit)."""
    tokens = request_limit() - config.LLM_OUTPUT_RESERVE_TOKENS - BUDGET_MARGIN_TOKENS
    return max(0, int(tokens * CHARS_PER_TOKEN) - len(build_system_prompt(instructions, schema)))


def fit(build: Callable[[int | None], str], limits: list[int | None], budget: int) -> tuple[str, int | None]:
    """The user input built with the first limit (on the length of the long texts in it) that fits the budget,
    or with the last one. Returns the input and the limit used (None: nothing was shortened)."""
    text = ""
    for limit in limits:
        text = build(limit)
        if len(text) <= budget:
            return text, limit
    return text, limits[-1]


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


def _reasoning_options(provider: str, name: str) -> dict:
    """reasoning_effort for the gpt-oss models on Groq, when config.LLM_REASONING_EFFORT sets it; nothing for
    the other models, which do not accept it."""
    if config.LLM_REASONING_EFFORT and provider == "groq" and "gpt-oss" in name:
        return {"reasoning_effort": config.LLM_REASONING_EFFORT}
    return {}


def _output_limit(model: str, system_prompt: str, user_input: str) -> dict:
    """With config.LLM_EXPLICIT_OUTPUT_LIMIT (V4 of E10): the longest answer the request limit leaves after the
    input, estimated from its length, never less than config.LLM_OUTPUT_RESERVE_TOKENS. Without it the provider
    chooses, and a long answer may be cut (measured in E10: at 3072 tokens)."""
    if not config.LLM_EXPLICIT_OUTPUT_LIMIT:
        return {}
    estimated = int((len(system_prompt) + len(user_input)) / CHARS_PER_TOKEN)
    room = request_limit(model) - estimated - BUDGET_MARGIN_TOKENS
    return {"max_completion_tokens": min(max(room, config.LLM_OUTPUT_RESERVE_TOKENS), MAX_OUTPUT_TOKENS)}


MAX_OUTPUT_TOKENS = 8192  # an answer of the agents is far shorter; more only lets a model ramble


# With LANGSMITH_TRACING=true every request is saved in LangSmith, inside the graph node that sent it:
# the prompts, the raw answer and the tokens. Without it the decorator does nothing.
@traceable(run_type="llm", name="LLM")
def _create_completion(model: str, system_prompt: str, user_input: str):
    """Send the request to one model, waiting and sending it again while the per-minute limit is reached."""
    provider, name = split_model(model)
    extra = _reasoning_options(provider, name) | _output_limit(model, system_prompt, user_input)
    attempt = 0
    while True:
        try:
            return _client(provider).chat.completions.create(
                model=name,
                temperature=0,
                **extra,
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
            waited = _waited.get()
            if waited is not None:
                waited.append(wait)
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
        started, waits = time.monotonic(), []
        waiting = _waited.set(waits)
        try:
            completion = _send(model, system_prompt, user_input)
        except LLMOutputError:
            _meter(model, started, waits, "invalid")
            raise
        except DailyLimitReached as exc:
            _meter(model, started, waits, "DailyLimitReached")
            _exhausted[model] = time.time() + exc.pause
            last_error = exc.error
            if not is_last:
                log.warning("%s reached its limit; set aside for %.0f min, trying %s", model, exc.pause / 60,
                            chain[index + 1])
            continue
        except Exception as exc:
            _meter(model, started, waits, type(exc).__name__)
            if is_last or not _can_fall_back(exc):
                raise
            last_error = exc
            log.warning("%s failed (%s); trying %s", model, type(exc).__name__, chain[index + 1])
            continue
        finally:
            _waited.reset(waiting)

        _record(model)
        try:
            answer = parse_output(completion.choices[0].message.content or "", schema)
        except LLMOutputError:
            _meter(model, started, waits, "invalid", completion)
            raise
        _meter(model, started, waits, "valid", completion)
        return answer

    if last_error is None:
        raise RuntimeError("No model can be used: set GROQ_API_KEY (and the keys of the fallback models) in .env.")
    raise last_error
