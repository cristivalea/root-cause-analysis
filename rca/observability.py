import os
from opentelemetry import trace

_tracer = None

def setup():
    global _tracer
    if _tracer or not os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
        return
    from phoenix.otel import register
    provider = register(
        project_name=os.getenv("PHOENIX_PROJECT_NAME", "rca"),
        auto_instrument=True,   # instrumentează automat Groq/LangChain dacă pachetele sunt instalate
    )
    _tracer = provider.get_tracer("rca")

def tracer():
    return trace.get_tracer("rca")