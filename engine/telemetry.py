"""Tracing set-up: export only to a local collector (Q3 ruling, PS-1.5).

The exporter is chosen from `Settings` alone (`choose_exporter`), and the
engine builds its own provider; it never calls `harness_telemetry.setup_tracing`
(which reads the environment itself). An already-installed provider is
verified, never trusted.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as _OtlpType
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


def _exporters_of(provider: TracerProvider) -> list[Any]:
    """Exporters behind an SDK provider's processors; None marks an unreadable one.

    Reads private SDK attributes; tests pin every shape so an upgrade that
    moves them fails there instead of silently accepting."""
    found: list[Any] = []
    for processor in provider._active_span_processor._span_processors:
        exporter = None
        if isinstance(processor, SimpleSpanProcessor):
            exporter = getattr(processor, "span_exporter", None)
        elif isinstance(processor, BatchSpanProcessor):
            exporter = getattr(getattr(processor, "_batch_processor", None), "_exporter", None)
        found.append(exporter)
    return found


def _sessions_of(node: Any, depth: int = 4) -> list[requests.Session]:
    """Every requests.Session reachable through OTel objects (the private
    path is today `_client._transport._session`; walking survives a move)."""
    found: list[requests.Session] = []
    seen: set[int] = set()

    def walk(item: Any, level: int) -> None:
        if id(item) in seen:
            return
        seen.add(id(item))
        if isinstance(item, requests.Session):
            found.append(item)
            return
        if level == 0 or not type(item).__module__.startswith("opentelemetry"):
            return
        for value in (vars(item).values() if hasattr(item, "__dict__") else ()):
            walk(value, level - 1)

    walk(node, depth)
    return found


def _ignores_proxy_env(exporter: Any) -> bool:
    sessions = _sessions_of(exporter)
    return bool(sessions) and all(s.trust_env is False for s in sessions)


def verify_provider(service_names: list[str]) -> None:
    """Accept the proxy provider (nothing installed) or an SDK provider whose
    exporters are all known to be local; refuse anything else."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, ProxyTracerProvider):
        return
    if not isinstance(provider, TracerProvider):
        raise StartupRefused(
            "telemetry.tracing", "an installed tracer provider is not the SDK provider")
    _verify_installed(provider, service_names)


def _verify_installed(provider: TracerProvider, service_names: list[str]) -> None:
    for exporter in _exporters_of(provider):
        if isinstance(exporter, (ConsoleSpanExporter, InMemorySpanExporter)):
            continue
        if (isinstance(exporter, _OtlpType)
                and is_local_endpoint(str(getattr(exporter, "_endpoint", "")), service_names)
                and _ignores_proxy_env(exporter)):
            continue
        raise StartupRefused(
            "telemetry.tracing",
            "an installed tracer provider has an exporter that is not known to be local")


def configure_tracing(settings: Settings) -> bool:
    """Write the resolved hide flags, then verify the installed provider or
    install the engine's own; True if the engine installed one."""
    telemetry = settings.telemetry
    # harness_telemetry reads the hide flags from the environment.
    os.environ["OPENINFERENCE_HIDE_INPUTS"] = str(telemetry.hide_inputs).lower()
    os.environ["OPENINFERENCE_HIDE_OUTPUTS"] = str(telemetry.hide_outputs).lower()
    current = trace.get_tracer_provider()
    if not isinstance(current, ProxyTracerProvider):
        verify_provider(settings.stack.service_names)
        return False
    exporter = choose_exporter(settings)
    if exporter is None:
        return False
    provider = TracerProvider(resource=Resource.create(
        {"service.name": PROJECT_NAME, ResourceAttributes.PROJECT_NAME: PROJECT_NAME}))
    if isinstance(exporter, ConsoleSpanExporter):
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        # Batched so tracing never blocks the work.
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return True
