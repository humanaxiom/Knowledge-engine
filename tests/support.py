"""One in-memory tracer provider shared by all tests (OTel allows one global)."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harness_telemetry import setup_tracing

EXPORTER = InMemorySpanExporter()
setup_tracing(project_name="harness-tests", exporter=EXPORTER)


def finished_spans():
    return {span.name: span for span in EXPORTER.get_finished_spans()}
