"""Tag OpenTelemetry spans with OpenInference conventions so Arize Phoenix
renders a pure-Python agent loop as a nested AGENT/RETRIEVER/LLM/TOOL tree.

Configuration (environment):
- ``HARNESS_TRACING``: ``otlp`` (default), ``console``, or ``off``.
- ``PHOENIX_COLLECTOR_ENDPOINT``: Phoenix base URL, default ``http://localhost:6006``.
- ``OPENINFERENCE_HIDE_INPUTS`` / ``OPENINFERENCE_HIDE_OUTPUTS``: ``true`` to
  redact input/output values (prompts, queries, documents) before export.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from openinference.semconv.resource import ResourceAttributes
from openinference.semconv.trace import (
    DocumentAttributes,
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    SpanAttributes,
)
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.trace import Span, Status, StatusCode

DEFAULT_COLLECTOR = "http://localhost:6006"
REDACTED = "__REDACTED__"

_tracer = trace.get_tracer("harness_telemetry")


def setup_tracing(
    project_name: str = "harness", exporter: SpanExporter | None = None
) -> TracerProvider | None:
    """Install the global tracer provider; idempotent. Returns None when tracing is off."""
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    mode = os.getenv("HARNESS_TRACING", "otlp").lower()
    if exporter is None and mode == "off":
        return None

    provider = TracerProvider(
        resource=Resource.create({ResourceAttributes.PROJECT_NAME: project_name})
    )
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif mode == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", DEFAULT_COLLECTOR).rstrip("/")
        # Batch so tracing never blocks the agent loop; short timeout so a
        # missing Phoenix instance costs seconds, not minutes.
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(f"{endpoint}/v1/traces", timeout=5))
        )
    trace.set_tracer_provider(provider)
    return provider


def _hidden(env_var: str) -> bool:
    return os.getenv(env_var, "").lower() in {"1", "true", "yes"}


def _set_value(span: Span, value_key: str, mime_key: str, value: Any, hide_env: str) -> None:
    if _hidden(hide_env):
        span.set_attribute(value_key, REDACTED)
        return
    if isinstance(value, str):
        span.set_attribute(value_key, value)
        span.set_attribute(mime_key, OpenInferenceMimeTypeValues.TEXT.value)
    else:
        span.set_attribute(value_key, json.dumps(value, default=str))
        span.set_attribute(mime_key, OpenInferenceMimeTypeValues.JSON.value)


def set_input(span: Span, value: Any) -> None:
    """Record exactly what the step received (text, or JSON for anything else)."""
    _set_value(
        span, SpanAttributes.INPUT_VALUE, SpanAttributes.INPUT_MIME_TYPE, value,
        "OPENINFERENCE_HIDE_INPUTS",
    )


def set_output(span: Span, value: Any) -> None:
    """Record exactly what the step produced (text, or JSON for anything else)."""
    _set_value(
        span, SpanAttributes.OUTPUT_VALUE, SpanAttributes.OUTPUT_MIME_TYPE, value,
        "OPENINFERENCE_HIDE_OUTPUTS",
    )


def record_documents(span: Span, documents: Sequence[Mapping[str, Any]]) -> None:
    """Record retrieved documents (``id``, ``content``, optional ``score``/``metadata``)
    so Phoenix lists them individually under the RETRIEVER span."""
    hide = _hidden("OPENINFERENCE_HIDE_OUTPUTS")
    for i, doc in enumerate(documents):
        prefix = f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}."
        if "id" in doc:
            span.set_attribute(prefix + DocumentAttributes.DOCUMENT_ID, str(doc["id"]))
        if "score" in doc:
            span.set_attribute(prefix + DocumentAttributes.DOCUMENT_SCORE, float(doc["score"]))
        content = REDACTED if hide else str(doc.get("content", ""))
        span.set_attribute(prefix + DocumentAttributes.DOCUMENT_CONTENT, content)
        if doc.get("metadata") and not hide:
            span.set_attribute(
                prefix + DocumentAttributes.DOCUMENT_METADATA,
                json.dumps(doc["metadata"], default=str),
            )


def record_token_usage(span: Span, prompt: int, completion: int) -> None:
    """Record token counts so Phoenix can aggregate cost per trace and session."""
    span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, prompt)
    span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, completion)
    span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_TOTAL, prompt + completion)


@contextmanager
def _span(
    name: str,
    kind: OpenInferenceSpanKindValues,
    input: Any = None,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    # start_as_current_span already records exceptions and sets ERROR status;
    # only a clean exit needs an explicit OK.
    with _tracer.start_as_current_span(name) as span:
        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, kind.value)
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        if input is not None:
            set_input(span, input)
        yield span
        if span.status.status_code is StatusCode.UNSET:
            span.set_status(Status(StatusCode.OK))


def agent_span(
    name: str,
    input: Any = None,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
):
    """Root of an agent run. ``session_id`` groups runs in Phoenix's Sessions view."""
    return _span(name, OpenInferenceSpanKindValues.AGENT, input, {
        SpanAttributes.SESSION_ID: session_id,
        SpanAttributes.USER_ID: user_id,
        SpanAttributes.TAG_TAGS: list(tags) if tags else None,
        SpanAttributes.METADATA: json.dumps(metadata, default=str) if metadata else None,
    })


def chain_span(name: str, input: Any = None):
    """A deterministic step (routing, parsing, prompt assembly)."""
    return _span(name, OpenInferenceSpanKindValues.CHAIN, input)


def retriever_span(name: str, input: Any = None):
    """A lookup (graph/vector/keyword search); pair with ``record_documents``."""
    return _span(name, OpenInferenceSpanKindValues.RETRIEVER, input)


def llm_span(name: str, input: Any = None, model: str | None = None):
    """A model call; pair with ``record_token_usage``."""
    return _span(name, OpenInferenceSpanKindValues.LLM, input, {
        SpanAttributes.LLM_MODEL_NAME: model,
    })


def tool_span(name: str, input: Any = None):
    """A tool invocation chosen by the agent."""
    return _span(name, OpenInferenceSpanKindValues.TOOL, input, {
        SpanAttributes.TOOL_NAME: name,
    })
