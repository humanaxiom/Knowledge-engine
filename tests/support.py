"""One in-memory tracer provider shared by all tests (OTel allows one global).

platform-stack-up, ruling R3 (docs/handoffs/platform-stack.md) and the
ADR-KE-010 M5 amendment: startup() accepts only a provider the engine built,
so this provider is built by `engine.telemetry.build_provider` and installed
with `trace.set_tracer_provider`, instead of `harness_telemetry.setup_tracing`.

`build_provider` has existed since platform-stack-up, so the former
`setup_tracing` fallback (a TDD-RED import guard) was dead and is removed.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from engine.telemetry import build_provider

EXPORTER = InMemorySpanExporter()
PROVIDER = build_provider(EXPORTER, project_name="harness-tests")
trace.set_tracer_provider(PROVIDER)


def finished_spans():
    return {span.name: span for span in EXPORTER.get_finished_spans()}
