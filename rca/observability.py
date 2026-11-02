import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace

_tracer = None
_sdk_enabled = False
_log = logging.getLogger(__name__)


def setup():
    global _tracer, _sdk_enabled
    if _tracer:
        return

    api_key = os.getenv("AI_OBSERVABILITY_API_KEY")
    endpoint = os.getenv("AI_OBSERVABILITY_ENDPOINT")
    phoenix_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    if api_key and endpoint:
        import ai_observability

        ai_observability.init(service_name="root-cause-analysis")
        _sdk_enabled = True

        provider = ai_observability.get_state().provider
        if provider is None:
            raise RuntimeError("The observability SDK did not initialize a tracer provider.")

        if phoenix_endpoint:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from phoenix.otel import HTTPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(HTTPSpanExporter()))

        _tracer = provider.get_tracer("rca")
        return

    if api_key and not endpoint:
        _log.warning(
            "AI_OBSERVABILITY_API_KEY is set but AI_OBSERVABILITY_ENDPOINT is missing; "
            "using Phoenix tracing instead."
        )

    if phoenix_endpoint:
        from phoenix.otel import register

        provider = register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "rca"),
            auto_instrument=True,
        )
        _tracer = provider.get_tracer("rca")


def tracer():
    return _tracer or trace.get_tracer("rca")


def shutdown() -> None:
    if _sdk_enabled:
        import ai_observability

        ai_observability.shutdown()


@contextmanager
def workflow_context(name: str, workflow_id: str | None = None) -> Iterator[None]:
    if not _sdk_enabled:
        yield
        return

    from ai_observability import workflow

    if workflow_id:
        with workflow(name=name, workflow_id=workflow_id, capture_prompts=True):
            yield
    else:
        with workflow(name=name, capture_prompts=True):
            yield