"""Tracing set-up: export only to a local collector (Q3 ruling, PS-1.5).

The exporter is chosen from `Settings` alone (`choose_exporter`), and the
engine builds its own provider; it never calls `harness_telemetry.setup_tracing`
(which reads the environment itself). An already-installed provider is
verified by identity (built by `build_provider`), never trusted.
"""

from __future__ import annotations

import os
import weakref

import requests
from opentelemetry import trace
from openinference.semconv.resource import ResourceAttributes
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import ProxyTracerProvider

from engine.config import Settings
from engine.egress import is_local_endpoint
from engine.errors import StartupRefused

PROJECT_NAME = "knowledge-engine"


def choose_exporter(settings: Settings) -> SpanExporter | None:
    """The span exporter the settings allow: OTLP to a local collector only,
    console, or none. Pure: no global provider is read or written."""
    telemetry = settings.telemetry
    if telemetry.tracing == "console":
        return ConsoleSpanExporter()
    if telemetry.tracing == "otlp":
        endpoint = str(telemetry.collector_endpoint)
        if not is_local_endpoint(endpoint, settings.stack.service_names):
            return None
        from opentelemetry.exporter.otlp.proto.http import trace_exporter

        # Proxy env vars must not reroute the export (H2).
        session = requests.Session()
        session.trust_env = False
        return trace_exporter.OTLPSpanExporter(
            f"{endpoint.rstrip('/')}/v1/traces", timeout=5, session=session)
    return None


_ENGINE_PROVIDERS: weakref.WeakSet[TracerProvider] = weakref.WeakSet()


def build_provider(exporter: SpanExporter, *, project_name: str = PROJECT_NAME) -> TracerProvider:
    """The engine's only tracer-provider constructor (PS-2.17, ADR-KE-010 M5).

    The provider is remembered by identity in a weak registry, so
    `verify_provider` can tell it from any provider built elsewhere without
    reading SDK internals. It is not installed globally; the caller does that.
    """
    provider = TracerProvider(resource=Resource.create(
        {"service.name": PROJECT_NAME, ResourceAttributes.PROJECT_NAME: project_name}))
    if isinstance(exporter, (ConsoleSpanExporter, InMemorySpanExporter)):
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        # Batched so tracing never blocks the work.
        provider.add_span_processor(BatchSpanProcessor(exporter))
    _ENGINE_PROVIDERS.add(provider)
    return provider


def _nothing_installed(provider: object) -> bool:
    # Exact type: a ProxyTracerProvider subclass can hand out its own tracers.
    return type(provider) is ProxyTracerProvider


def _built_by_engine(provider: object) -> bool:
    # Identity, not membership: a decoy's __eq__/__hash__ must not count.
    return any(provider is built for built in list(_ENGINE_PROVIDERS))


def verify_provider() -> None:
    """Accept nothing installed, or a provider built by `build_provider`;
    refuse any other (identity, not inspection)."""
    provider = trace.get_tracer_provider()
    if _nothing_installed(provider) or _built_by_engine(provider):
        return
    raise StartupRefused(
        "telemetry.tracing", "an installed tracer provider was not built by the engine")


def configure_tracing(settings: Settings) -> bool:
    """Write the resolved hide flags, then verify the installed provider or
    install the engine's own; True if the engine installed one."""
    telemetry = settings.telemetry
    # harness_telemetry reads the hide flags from the environment.
    os.environ["OPENINFERENCE_HIDE_INPUTS"] = str(telemetry.hide_inputs).lower()
    os.environ["OPENINFERENCE_HIDE_OUTPUTS"] = str(telemetry.hide_outputs).lower()
    current = trace.get_tracer_provider()
    if not _nothing_installed(current):
        verify_provider()
        return False
    exporter = choose_exporter(settings)
    if exporter is None:
        return False
    built = build_provider(exporter)
    trace.set_tracer_provider(built)
    if trace.get_tracer_provider() is not built:
        built.shutdown()
        raise StartupRefused(
            "telemetry.tracing", "the engine's tracer provider is not the installed one")
    return True
