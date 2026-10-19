"""One in-memory tracer provider shared by all tests (OTel allows one global).

platform-stack-up, ruling R3 (docs/handoffs/platform-stack.md) and the
ADR-KE-010 M5 amendment: startup() accepts only a provider the engine built,
so this provider is built by `engine.telemetry.build_provider` and installed
with `trace.set_tracer_provider`, instead of `harness_telemetry.setup_tracing`.

The import is guarded so a missing `build_provider` (TDD RED) fails the one
test that checks it (`test_support_provider_is_engine_built`) instead of
erroring every module that imports this one. The fallback is the previous
set-up, unchanged; nothing else may depend on it.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

EXPORTER = InMemorySpanExporter()
BUILD_PROVIDER_ERROR: Exception | None = None

try:
    from engine.telemetry import build_provider
except ImportError as exc:  # RED until build_provider exists
    BUILD_PROVIDER_ERROR = exc
    from harness_telemetry import setup_tracing

    PROVIDER = setup_tracing(project_name="harness-tests", exporter=EXPORTER)
else:
    PROVIDER = build_provider(EXPORTER, project_name="harness-tests")
    trace.set_tracer_provider(PROVIDER)


def finished_spans():
    return {span.name: span for span in EXPORTER.get_finished_spans()}
