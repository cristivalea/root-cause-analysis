import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace

from rca import observability


def _reset_observability(monkeypatch):
    monkeypatch.setattr(observability, "_tracer", None)
    monkeypatch.setattr(observability, "_sdk_enabled", False)


def test_sdk_workflow_captures_prompts_for_revision(monkeypatch):
    _reset_observability(monkeypatch)
    monkeypatch.setenv("AI_OBSERVABILITY_API_KEY", "test-key")
    monkeypatch.setenv("AI_OBSERVABILITY_ENDPOINT", "http://observability.test")
    calls = {}

    class Provider:
        def get_tracer(self, name):
            calls["tracer_name"] = name
            return "sdk-tracer"

        def add_span_processor(self, processor):
            calls["processor"] = processor

    sdk = ModuleType("ai_observability")
    sdk.init = lambda **kwargs: calls.setdefault("init", kwargs)
    sdk.get_state = lambda: SimpleNamespace(provider=Provider())

    @contextmanager
    def workflow(**kwargs):
        calls["workflow"] = kwargs
        yield

    sdk.workflow = workflow
    monkeypatch.setitem(sys.modules, "ai_observability", sdk)

    observability.setup()
    with observability.workflow_context("rca-investigation", "revision-123"):
        calls["inside"] = True

    assert calls["init"] == {"service_name": "root-cause-analysis"}
    assert calls["workflow"] == {
        "name": "rca-investigation",
        "workflow_id": "revision-123",
        "capture_prompts": True,
    }
    assert calls["tracer_name"] == "rca"
    assert calls["inside"] is True


def test_sdk_and_phoenix_share_the_sdk_provider(monkeypatch):
    _reset_observability(monkeypatch)
    monkeypatch.setenv("AI_OBSERVABILITY_API_KEY", "test-key")
    monkeypatch.setenv("AI_OBSERVABILITY_ENDPOINT", "http://observability.test")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix.test:6006")
    calls = {}

    class Provider:
        def get_tracer(self, name):
            calls["tracer_name"] = name
            return "shared-tracer"

        def add_span_processor(self, processor):
            calls["processor"] = processor

    sdk = ModuleType("ai_observability")
    sdk.init = lambda **kwargs: calls.setdefault("init", kwargs)
    sdk.get_state = lambda: SimpleNamespace(provider=Provider())
    monkeypatch.setitem(sys.modules, "ai_observability", sdk)

    phoenix_otel = ModuleType("phoenix.otel")
    phoenix_otel.HTTPSpanExporter = lambda: "phoenix-exporter"
    monkeypatch.setitem(sys.modules, "phoenix.otel", phoenix_otel)

    processor = ModuleType("opentelemetry.sdk.trace.export")
    processor.BatchSpanProcessor = lambda exporter: ("batch-processor", exporter)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.export", processor)

    observability.setup()

    assert calls["processor"] == ("batch-processor", "phoenix-exporter")
    assert observability.tracer() == "shared-tracer"


def test_workflow_context_is_inert_without_sdk_configuration(monkeypatch):
    _reset_observability(monkeypatch)
    monkeypatch.delenv("AI_OBSERVABILITY_API_KEY", raising=False)
    monkeypatch.delenv("AI_OBSERVABILITY_ENDPOINT", raising=False)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)

    with observability.workflow_context("rca-investigation", "revision-123"):
        assert not observability._sdk_enabled
