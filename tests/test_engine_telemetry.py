"""platform-config rework 1: the trace exporter path (review B1, B2; security H1, L6).

Contract (docs/architecture.md §2.3 "Tracing does not leak before the checks
pass", amended rework 1, and ADR-KE-010 "First tests, Rework 1"):
- `engine.telemetry.choose_exporter(settings) -> SpanExporter | None` is pure:
  `otlp` gives an OTLP exporter to `<collector_endpoint>/v1/traces` only when
  the collector is local, `console` gives a `ConsoleSpanExporter`, `off` none.
  It decides from `Settings` alone; `HARNESS_TRACING` and
  `PHOENIX_COLLECTOR_ENDPOINT` reach it only through `Settings`.
- `engine.telemetry.configure_tracing(settings)` writes the resolved hide flags,
  then verifies an already-installed SDK provider (every exporter must be
  positively local, else `StartupRefused("telemetry.tracing", ...)`) or
  installs the engine's own provider.
- `engine.startup.startup()` runs `check()` first and calls
  `configure_tracing` only if it passes (L6).

Why these tests isolate the provider: tests/support.py installs one global SDK
`TracerProvider` (in-memory exporter) for the whole run, so a test that calls
`configure_tracing` against the real global never reaches the exporter path
(review B2: M1, M2, M11 survived). Here `trace.get_tracer_provider` is patched
to return either a fresh `ProxyTracerProvider` (nothing installed) or a
provider the test built, and `trace.set_tracer_provider` is patched to record
what would be installed. `OTLPSpanExporter` is replaced by a mock, so nothing
is ever constructed that could send; a SocketSpy asserts zero socket attempts.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

from tests.engine_support import DEFAULTS, SocketSpy, base_env, environ, load_settings

LOCAL = "http://localhost:47101"
REMOTE = "http://collector.example.com:6006"
REMOTE_HOST = "collector.example.com"


def _refused() -> type[Exception]:
    from engine.startup import StartupRefused

    return StartupRefused


def _env_without(name: str, **overrides: str) -> dict[str, str]:
    env = base_env(**overrides)
    env.pop(name, None)
    return env


def exporters_of(provider: Any) -> list[Any]:
    """The exporters attached to an SDK TracerProvider (Simple and Batch processors)."""
    found = []
    for processor in provider._active_span_processor._span_processors:
        exporter = getattr(processor, "span_exporter", None)
        if exporter is None:
            exporter = getattr(getattr(processor, "_batch_processor", None), "_exporter", None)
        found.append(exporter)
    return found


class Isolated:
    """Patched tracer-provider globals and a mocked OTLPSpanExporter."""

    def __init__(self, current: Any) -> None:
        self.current = current
        self.installed: list[Any] = []
        self.otlp = mock.MagicMock(name="OTLPSpanExporter")
        self.spy = SocketSpy()

    def otlp_urls(self) -> list[str]:
        urls = []
        for call in self.otlp.call_args_list:
            url = call.args[0] if call.args else call.kwargs.get("endpoint")
            urls.append(str(url))
        return urls

    def installed_exporters(self) -> list[Any]:
        return [e for p in self.installed for e in exporters_of(p)]


@contextmanager
def isolated(current: Any = None) -> Iterator[Isolated]:
    """`current` is what get_tracer_provider returns (default: nothing installed)."""
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp_module
    from opentelemetry import trace

    import engine.telemetry as telemetry

    iso = Isolated(current if current is not None else trace.ProxyTracerProvider())
    with ExitStack() as stack:
        # As in real OTel, once installed the global is what was installed
        # (platform-stack-up security M-1: configure_tracing checks it).
        stack.enter_context(mock.patch.object(
            trace, "get_tracer_provider",
            lambda: iso.installed[-1] if iso.installed else iso.current))
        stack.enter_context(mock.patch.object(trace, "set_tracer_provider",
                                              iso.installed.append))
        stack.enter_context(mock.patch.object(otlp_module, "OTLPSpanExporter", iso.otlp))
        if hasattr(telemetry, "OTLPSpanExporter"):  # imported at module top
            stack.enter_context(mock.patch.object(telemetry, "OTLPSpanExporter", iso.otlp))
        stack.enter_context(iso.spy.active())
        try:
            yield iso
        finally:
            for provider in iso.installed:
                try:
                    provider.shutdown()
                except Exception:
                    pass


# The H1 / B1 repro environments: console requested, an external collector in
# the standard variable, HARNESS_TRACING unset or otlp.
CONSOLE_CASES = {
    "KE console, HARNESS_TRACING unset, external PHOENIX endpoint": _env_without(
        "HARNESS_TRACING", KE_ENV="prod", KE_TELEMETRY__TRACING="console",
        PHOENIX_COLLECTOR_ENDPOINT=REMOTE),
    "KE console, HARNESS_TRACING=otlp, external PHOENIX endpoint": base_env(
        KE_ENV="prod", KE_TELEMETRY__TRACING="console", HARNESS_TRACING="otlp",
        PHOENIX_COLLECTOR_ENDPOINT=REMOTE),
    "settings look local, harness env points outside": base_env(
        KE_ENV="ci", KE_TELEMETRY__TRACING="console", HARNESS_TRACING="otlp",
        KE_TELEMETRY__COLLECTOR_ENDPOINT=LOCAL, PHOENIX_COLLECTOR_ENDPOINT=REMOTE),
}


def _yaml_with_console(tmp: str) -> str:
    import yaml

    data = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    data["telemetry"]["tracing"] = "console"
    path = Path(tmp) / "defaults.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


class ChooseExporterTest(unittest.TestCase):
    """B1/H1: the exporter comes from Settings alone (pure, no global provider)."""

    def _choose(self, env: dict[str, str]) -> tuple[Any, Isolated]:
        from engine.telemetry import choose_exporter

        settings = load_settings(env)
        with isolated() as iso, environ(env):
            exporter = choose_exporter(settings)
        return exporter, iso

    def test_console_mode_never_builds_otlp(self):
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        with tempfile.TemporaryDirectory() as tmp:
            cases = dict(CONSOLE_CASES)
            cases["console from the YAML file, external PHOENIX endpoint"] = _env_without(
                "HARNESS_TRACING", KE_CONFIG_FILE=_yaml_with_console(tmp), KE_ENV="prod",
                PHOENIX_COLLECTOR_ENDPOINT=REMOTE)
            for case, env in cases.items():
                with self.subTest(case=case):
                    exporter, iso = self._choose(env)
                    self.assertIsInstance(exporter, ConsoleSpanExporter)
                    iso.otlp.assert_not_called()
                    self.assertEqual(iso.spy.attempts, [])

    def test_off_gives_no_exporter(self):
        for env in (base_env(HARNESS_TRACING="off", PHOENIX_COLLECTOR_ENDPOINT=LOCAL),
                    base_env(KE_TELEMETRY__TRACING="off", HARNESS_TRACING="otlp",
                             PHOENIX_COLLECTOR_ENDPOINT=LOCAL)):
            with self.subTest(env={k: v for k, v in env.items() if "TRAC" in k}):
                exporter, iso = self._choose(env)
                self.assertIsNone(exporter)
                iso.otlp.assert_not_called()

    def test_otlp_to_non_local_collector_gives_none(self):  # kills M1
        for endpoint in (REMOTE, "http://203.0.113.5:6006", "http://10.0.0.5:6006"):
            with self.subTest(endpoint=endpoint):
                exporter, iso = self._choose(base_env(
                    KE_ENV="dev", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=endpoint))
                self.assertIsNone(exporter)
                iso.otlp.assert_not_called()
                self.assertEqual(iso.spy.attempts, [])

    def test_otlp_to_local_collector_builds_traces_url(self):
        for endpoint, url in ((LOCAL, f"{LOCAL}/v1/traces"),
                              ("http://phoenix:6006/", "http://phoenix:6006/v1/traces")):
            with self.subTest(endpoint=endpoint):
                exporter, iso = self._choose(base_env(
                    HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=endpoint))
                self.assertEqual(iso.otlp_urls(), [url])
                self.assertIs(exporter, iso.otlp.return_value)


class ConfigureTracingTest(unittest.TestCase):
    """B2: the installing path itself, with nothing installed beforehand."""

    def _configure(self, env: dict[str, str], current: Any = None) -> Isolated:
        from engine.telemetry import configure_tracing

        settings = load_settings(env)
        with isolated(current) as iso, environ(env):
            configure_tracing(settings)
        return iso

    def test_local_collector_gets_an_otlp_exporter(self):
        iso = self._configure(base_env(HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=LOCAL))
        self.assertEqual(iso.otlp_urls(), [f"{LOCAL}/v1/traces"])
        self.assertEqual(len(iso.installed), 1, "no provider was installed")
        self.assertIn(iso.otlp.return_value, iso.installed_exporters())

    def test_non_local_collector_gets_no_exporter(self):  # kills M1
        from engine.telemetry import configure_tracing

        env = base_env(KE_ENV="dev", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=REMOTE)
        settings = load_settings(env)
        with isolated() as iso, environ(env):
            try:
                configure_tracing(settings)
            except _refused():
                pass  # refusing is also safe; exporting is not
        iso.otlp.assert_not_called()
        self.assertEqual(iso.spy.attempts, [])
        self.assertEqual([e for e in iso.installed_exporters() if e is not None], [])

    def test_console_mode_installs_console_exporter_only(self):  # B1 / H1
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        for case, env in CONSOLE_CASES.items():
            with self.subTest(case=case):
                iso = self._configure(env)
                iso.otlp.assert_not_called()
                self.assertEqual(iso.spy.attempts, [])
                exporters = iso.installed_exporters()
                self.assertTrue(exporters, "console mode installed no exporter")
                for exporter in exporters:
                    self.assertIsInstance(exporter, ConsoleSpanExporter)

    def test_hide_defaults_apply_before_any_span(self):  # kills M2
        """The YAML hide defaults (true) redact span values even when the
        OPENINFERENCE_HIDE_* variables are unset (PS-Q4)."""
        from engine.telemetry import configure_tracing
        from harness_telemetry import chain_span
        from harness_telemetry.tracing import REDACTED
        from tests import support

        env = base_env(KE_ENV="prod")
        for name in ("OPENINFERENCE_HIDE_INPUTS", "OPENINFERENCE_HIDE_OUTPUTS"):
            self.assertNotIn(name, env)
        settings = load_settings(env)
        self.assertIs(settings.telemetry.hide_inputs, True)
        support.EXPORTER.clear()
        with environ(env):
            configure_tracing(settings)
            with chain_span("probe.hide", input="visible-input-value"):
                pass
        span = support.finished_spans()["probe.hide"]
        self.assertEqual(span.attributes.get("input.value"), REDACTED)


class InstalledProviderTest(unittest.TestCase):
    """B1 (N10): an already-installed provider is verified, never trusted.

    Since platform-stack-up (PS-2.17, ADR-KE-010 M5 amendment, ruling R3)
    "verified" means built by `engine.telemetry.build_provider`: every shape
    built outside the engine is refused, and the engine-built ones are the
    accepted controls."""

    MODES = {
        "off": base_env(HARNESS_TRACING="off"),
        "console": base_env(HARNESS_TRACING="console"),
        "otlp local": base_env(HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=LOCAL),
    }

    def _provider(self, processor: Any) -> Any:
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        provider.add_span_processor(processor)
        self.addCleanup(provider.shutdown)
        return provider

    def _real_otlp(self, url: str) -> Any:
        # A real exporter, so the check reads its real endpoint; its export
        # is replaced so it could never send.
        # Rework 2 (security H2, orchestrator ruling "rework round 2 of 5" in
        # docs/handoffs/platform-config.md): an installed OTLP exporter is
        # accepted only if its session ignores proxy env (trust_env False),
        # so the accepted shapes are built the way the engine builds its own.
        # A default session is refused: tests/test_engine_tracing_guard.py.
        import requests
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        session = requests.Session()
        session.trust_env = False
        exporter = OTLPSpanExporter(url, timeout=5, session=session)
        exporter.export = mock.MagicMock(name="export")  # type: ignore[method-assign]
        return exporter

    def _configure(self, env: dict[str, str], provider: Any) -> BaseException | None:
        from engine.telemetry import configure_tracing

        settings = load_settings(env)
        with isolated(provider), environ(env):
            try:
                configure_tracing(settings)
            except Exception as exc:
                return exc
        return None

    def test_formerly_accepted_foreign_shapes_are_refused(self):
        # Was `test_accepted_shapes`. Flipped by orchestrator ruling R3
        # (docs/handoffs/platform-stack.md) and the ADR-KE-010 M5 amendment:
        # a provider built outside the engine is refused whatever its
        # exporters (PS-2.17). The same exporters inside an engine-built
        # provider are the accepted control below.
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        shapes = {
            "simple console": lambda: SimpleSpanProcessor(ConsoleSpanExporter()),
            "simple in-memory": lambda: SimpleSpanProcessor(InMemorySpanExporter()),
            "batch otlp localhost": lambda: BatchSpanProcessor(
                self._real_otlp(f"{LOCAL}/v1/traces")),
            "simple otlp service name": lambda: SimpleSpanProcessor(
                self._real_otlp("http://phoenix:6006/v1/traces")),
        }
        for shape, build in shapes.items():
            for mode, env in self.MODES.items():
                with self.subTest(shape=shape, mode=mode):
                    error = self._configure(env, self._provider(build()))
                    self.assertIsInstance(error, _refused(), f"{shape} trusted in {mode}")
                    self.assertIn("telemetry.tracing", str(error))

    def test_engine_built_shapes_are_accepted(self):
        # The R3 control: the exporters above, in a provider from build_provider.
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        from engine.telemetry import build_provider

        shapes = {
            "console": ConsoleSpanExporter,
            "in-memory": InMemorySpanExporter,
            "otlp localhost": lambda: self._real_otlp(f"{LOCAL}/v1/traces"),
            "otlp service name": lambda: self._real_otlp("http://phoenix:6006/v1/traces"),
        }
        for shape, make in shapes.items():
            for mode, env in self.MODES.items():
                with self.subTest(shape=shape, mode=mode):
                    provider = build_provider(make())
                    self.addCleanup(provider.shutdown)
                    error = self._configure(env, provider)
                    self.assertIsNone(error, f"{shape} refused in {mode}: {error!r}")

    def test_non_local_or_unknown_exporter_is_refused(self):
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SimpleSpanProcessor,
            SpanExporter,
            SpanExportResult,
        )

        class Unknown(SpanExporter):
            def __init__(self) -> None:
                self.calls = 0

            def export(self, spans: Any) -> SpanExportResult:
                self.calls += 1
                return SpanExportResult.SUCCESS

        shapes = {
            "simple otlp external": lambda: (lambda e: (SimpleSpanProcessor(e), e))(
                self._real_otlp(f"{REMOTE}/v1/traces")),
            "batch otlp external ip": lambda: (lambda e: (BatchSpanProcessor(e), e))(
                self._real_otlp("http://203.0.113.5:4318/v1/traces")),
            "unknown exporter": lambda: (lambda e: (SimpleSpanProcessor(e), e))(Unknown()),
        }
        for shape, build in shapes.items():
            for mode, env in self.MODES.items():
                with self.subTest(shape=shape, mode=mode):
                    processor, _ = build()
                    error = self._configure(env, self._provider(processor))
                    self.assertIsInstance(error, _refused(),
                                          f"{shape} was trusted in {mode}")
                    self.assertIn("telemetry.tracing", str(error))


class StartupWiringTest(unittest.TestCase):
    """B2 (M11) and L6: startup() configures tracing, and only after check()."""

    def _startup(self, env: dict[str, str]) -> tuple[Isolated, BaseException | None, dict]:
        from engine.startup import startup

        error = None
        with isolated() as iso, environ(env):
            try:
                startup()
            except Exception as exc:
                error = exc
            after = {k: os.environ.get(k) for k in
                     ("OPENINFERENCE_HIDE_INPUTS", "OPENINFERENCE_HIDE_OUTPUTS")}
        return iso, error, after

    def test_startup_installs_the_exporter(self):  # kills M11
        iso, error, _ = self._startup(base_env(
            KE_ENV="prod", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=LOCAL))
        self.assertIsNone(error)
        self.assertEqual(iso.otlp_urls(), [f"{LOCAL}/v1/traces"])
        self.assertEqual(len(iso.installed), 1)

    def test_refused_startup_installs_nothing(self):  # L6
        cases = {
            "auth off in prod, local collector": base_env(
                KE_ENV="prod", KE_AUTH__ENABLED="false", HARNESS_TRACING="otlp",
                PHOENIX_COLLECTOR_ENDPOINT=LOCAL),
            "non-local collector": base_env(
                KE_ENV="prod", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=REMOTE),
            "placeholder secret, console": base_env(
                KE_ENV="ci", HARNESS_TRACING="console",
                KE_STORES__POSTGRES__PASSWORD="changeme-x"),
        }
        for case, env in cases.items():
            with self.subTest(case=case):
                iso, error, _ = self._startup(env)
                self.assertIsInstance(error, _refused())
                iso.otlp.assert_not_called()
                self.assertEqual(iso.installed, [], "a provider was installed before check()")
                self.assertEqual(iso.spy.attempts, [])

    def test_refused_startup_leaves_hide_env_untouched(self):  # L6
        refused = dict(KE_ENV="prod", KE_AUTH__ENABLED="false")
        cases = {
            "unset stays unset": base_env(**refused),
            "operator values kept verbatim": base_env(
                **refused, OPENINFERENCE_HIDE_INPUTS="1", OPENINFERENCE_HIDE_OUTPUTS="yes"),
        }
        for case, env in cases.items():
            with self.subTest(case=case):
                _, error, after = self._startup(env)
                self.assertIsInstance(error, _refused())
                self.assertEqual(after, {
                    "OPENINFERENCE_HIDE_INPUTS": env.get("OPENINFERENCE_HIDE_INPUTS"),
                    "OPENINFERENCE_HIDE_OUTPUTS": env.get("OPENINFERENCE_HIDE_OUTPUTS"),
                })


if __name__ == "__main__":
    unittest.main()
