"""platform-config rework 2: the trace exporter cannot be rerouted or pre-empted.

Findings (docs/evidence/platform-config/security-rework1.md, review-rework1.md;
orchestrator "rework round 2 of 5" in docs/handoffs/platform-config.md):
- H2: the engine's OTLP exporter must ignore proxy env (`HTTP_PROXY`,
  `http_proxy`, `ALL_PROXY`): its requests session has `trust_env` False, and
  the only host it ever dials is the collector's. An already-installed local
  OTLP exporter whose session trusts proxy env is refused with
  `StartupRefused("telemetry.tracing", ...)`.
- M3 + R1: `startup()` verifies whatever provider is already installed before
  any span opens, whether or not the settings pass `check()`. A provider that
  fails verification, or is not an SDK provider at all, is refused and gets
  zero spans. A `ProxyTracerProvider` (nothing installed) is accepted.
- R2: the engine's provider resource carries the OpenInference project name.
- platform-stack-up, PS-2.17 / security M5 (ADR-KE-010 M5 amendment, option
  (c); orchestrator ruling R3 in docs/handoffs/platform-stack.md): only a
  provider built by `engine.telemetry.build_provider` (or nothing installed)
  is accepted. Tests that pinned foreign shapes as accepted were flipped to
  refused under R3, and their controls now use `build_provider`.

How spans are routed here: harness_telemetry's module tracer (`_tracer`) is a
ProxyTracer that resolves to the first global provider (tests/support.py's).
To model "a foreign provider was installed before startup()", these tests
point `_tracer` at the foreign provider and make `trace.get_tracer_provider`
return it; `trace.set_tracer_provider` only records. Every real OTLP exporter
runs under a SocketSpy, which refuses and records every resolve/connect.
"""

from __future__ import annotations

import importlib
import io
import unittest
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator
from unittest import mock

from tests.engine_support import SocketSpy, base_env, config_error, environ, load_settings

LOCAL = "http://localhost:47101"
REMOTE = "http://collector.example.com:6006"
PROXY = "http://evil.example:3128"
PROXY_HOST = "evil.example"

# (case, collector endpoint, expected collector host, proxy env) -- security P8e.
PROXY_CASES = (
    ("localhost, HTTP_PROXY", "http://localhost:6006", "localhost", {"HTTP_PROXY": PROXY}),
    ("phoenix, HTTP_PROXY", "http://phoenix:6006", "phoenix", {"HTTP_PROXY": PROXY}),
    ("phoenix, http_proxy + NO_PROXY=localhost", "http://phoenix:6006", "phoenix",
     {"http_proxy": PROXY, "NO_PROXY": "localhost,127.0.0.1"}),
    ("127.0.0.1, ALL_PROXY", "http://127.0.0.1:6006", "127.0.0.1", {"ALL_PROXY": PROXY}),
)


def _refused() -> type[Exception]:
    from engine.startup import StartupRefused

    return StartupRefused


def exporters_of(provider: Any) -> list[Any]:
    found = []
    for processor in provider._active_span_processor._span_processors:
        exporter = getattr(processor, "span_exporter", None)
        if exporter is None:
            exporter = getattr(getattr(processor, "_batch_processor", None), "_exporter", None)
        found.append(exporter)
    return found


def sessions_of(obj: Any, depth: int = 4) -> list[Any]:
    """Every requests.Session reachable from an exporter through OTel objects.

    Walks attributes instead of naming the private path (today
    `_client._transport._session`), so an SDK upgrade that moves it still
    finds the session; an empty result fails the caller's assertion."""
    import requests

    found: list[Any] = []
    seen: set[int] = set()

    def walk(node: Any, level: int) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, requests.Session):
            found.append(node)
            return
        if level == 0 or not type(node).__module__.startswith("opentelemetry"):
            return
        for value in vars(node).values() if hasattr(node, "__dict__") else ():
            walk(value, level - 1)

    walk(obj, depth)
    return found


def dialled_hosts(spy: SocketSpy) -> list[str]:
    hosts = []
    for kind, args in spy.attempts:
        if kind == "getaddrinfo":
            hosts.append(str(args[0]))
        elif kind == "create_connection":
            hosts.append(str(args[0][0]))
        else:  # socket.connect / connect_ex: (sock, address)
            hosts.append(str(args[-1][0]))
    return hosts


def a_finished_span() -> Any:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    with provider.get_tracer("probe").start_as_current_span("probe.export"):
        pass
    provider.shutdown()
    return memory.get_finished_spans()[0]


def export_once(exporter: Any, env: dict[str, str]) -> list[str]:
    """Drive the exporter's real export path once (no retry backoff) under a
    SocketSpy with `env` as the whole environment; the hosts it tried to dial."""
    import opentelemetry.exporter.otlp.common.http as otlp_http

    span = a_finished_span()
    spy = SocketSpy()
    with environ(env), spy.active(), mock.patch.object(otlp_http, "_MAX_RETRIES", 1):
        exporter.export([span])
    return dialled_hosts(spy)


@contextmanager
def globals_patched(current: Any) -> Iterator[list[Any]]:
    """get_tracer_provider returns `current`; set_tracer_provider records.

    As in real OTel, once something is installed get_tracer_provider returns
    it (security M-1: configure_tracing checks the global after installing)."""
    from opentelemetry import trace

    installed: list[Any] = []
    with mock.patch.object(trace, "get_tracer_provider",
                           lambda: installed[-1] if installed else current), \
            mock.patch.object(trace, "set_tracer_provider", installed.append):
        try:
            yield installed
        finally:
            for provider in installed:
                try:
                    provider.shutdown()
                except Exception:
                    pass


def _proxy_env(endpoint: str, proxy_env: dict[str, str]) -> dict[str, str]:
    return base_env(KE_ENV="ci", HARNESS_TRACING="otlp",
                    KE_TELEMETRY__COLLECTOR_ENDPOINT=endpoint, **proxy_env)


class ExporterIgnoresProxyEnvTest(unittest.TestCase):
    """H2: the engine's OTLP exporter never follows proxy env off-host."""

    def test_chosen_exporter_session_does_not_trust_env(self):  # kills "session not passed"
        from engine.telemetry import choose_exporter

        for case, endpoint, _, proxy_env in PROXY_CASES:
            with self.subTest(case=case):
                env = _proxy_env(endpoint, proxy_env)
                with environ(env):
                    exporter = choose_exporter(load_settings(env))
                self.assertIsNotNone(exporter, "a local collector got no exporter")
                sessions = sessions_of(exporter)
                self.assertTrue(sessions, "no requests.Session found on the OTLP exporter")
                for session in sessions:
                    self.assertIs(session.trust_env, False,
                                  "the OTLP session reads proxy env (trust_env is True)")
                exporter.shutdown()

    def test_chosen_exporter_dials_only_the_collector(self):
        from engine.telemetry import choose_exporter

        for case, endpoint, host, proxy_env in PROXY_CASES:
            with self.subTest(case=case):
                env = _proxy_env(endpoint, proxy_env)
                with environ(env):
                    exporter = choose_exporter(load_settings(env))
                hosts = export_once(exporter, env)
                exporter.shutdown()
                self.assertTrue(hosts, "the export never reached the socket layer")
                self.assertNotIn(PROXY_HOST, hosts, f"export went through the proxy: {hosts}")
                self.assertEqual(set(hosts), {host}, hosts)

    def test_configured_exporter_dials_only_the_collector(self):
        from engine.telemetry import configure_tracing

        for case, endpoint, host, proxy_env in PROXY_CASES:
            with self.subTest(case=case):
                env = _proxy_env(endpoint, proxy_env)
                settings = load_settings(env)
                from opentelemetry import trace

                with globals_patched(trace.ProxyTracerProvider()) as installed, environ(env):
                    configure_tracing(settings)
                    self.assertEqual(len(installed), 1, "no provider was installed")
                    exporters = [e for e in exporters_of(installed[0]) if e is not None]
                    self.assertEqual(len(exporters), 1, exporters)
                    for session in sessions_of(exporters[0]) or [None]:
                        self.assertIsNotNone(session, "no requests.Session on the exporter")
                        self.assertIs(session.trust_env, False)
                    hosts = export_once(exporters[0], env)
                self.assertTrue(hosts, "the export never reached the socket layer")
                self.assertNotIn(PROXY_HOST, hosts, f"export went through the proxy: {hosts}")
                self.assertEqual(set(hosts), {host}, hosts)


def _real_otlp(url: str, trust_env: bool) -> Any:
    """A real OTLP exporter that can never send (export replaced)."""
    import requests
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    if trust_env:
        exporter = OTLPSpanExporter(url, timeout=5)  # default session: trusts env
    else:
        session = requests.Session()
        session.trust_env = False
        exporter = OTLPSpanExporter(url, timeout=5, session=session)
    exporter.export = mock.MagicMock(name="export")  # type: ignore[method-assign]
    return exporter


def _make_session_unreachable(exporter: Any) -> Any:
    """Review B-R2-1 (W3): replace every requests.Session reachable through the
    exporter's OTel objects with a plain object, as if an SDK upgrade moved the
    session out of the walk. The session itself ignores proxy env, so the only
    thing that can refuse this exporter is "no reachable session"."""
    import requests

    class Moved:  # not a requests.Session; close() keeps shutdown quiet
        def close(self) -> None:
            pass

    seen: set[int] = set()

    def walk(node: Any, level: int) -> None:
        if id(node) in seen or level == 0:
            return
        seen.add(id(node))
        if not type(node).__module__.startswith("opentelemetry") or not hasattr(node, "__dict__"):
            return
        for key, value in list(vars(node).items()):
            if isinstance(value, requests.Session):
                setattr(node, key, Moved())
            else:
                walk(value, level - 1)

    walk(exporter, 6)
    assert sessions_of(exporter) == [], "the session is still reachable"
    return exporter


def _ship_anywhere_processor() -> Any:
    """Review B-R2-1 (E1): a custom SpanProcessor, neither Simple nor Batch,
    that would ship spans anywhere (as vendor distros do). Records what it got."""
    from opentelemetry.sdk.trace import SpanProcessor

    class ShipAnywhere(SpanProcessor):
        def __init__(self) -> None:
            self.shipped: list[Any] = []

        def on_end(self, span: Any) -> None:
            self.shipped.append(span)

    return ShipAnywhere()


def _unknown_exporter() -> Any:
    """An exporter to an unknown destination."""
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class Unknown(SpanExporter):
        def export(self, spans: Any) -> SpanExportResult:
            return SpanExportResult.SUCCESS

    return Unknown()


def _engine_built(exporter: Any, **kwargs: Any) -> Any:
    """A provider from the engine's only constructor (ADR-KE-010 M5 amendment)."""
    from engine.telemetry import build_provider

    return build_provider(exporter, **kwargs)


def _vendor_provider(inner: Any) -> Any:
    """A non-SDK API TracerProvider (e.g. a vendor distro) wrapping `inner`."""
    from opentelemetry import trace

    class VendorTracerProvider(trace.TracerProvider):
        def get_tracer(self, *args: Any, **kwargs: Any) -> Any:
            return inner.get_tracer(*args, **kwargs)

    return VendorTracerProvider()


MODES = {
    "off": base_env(HARNESS_TRACING="off"),
    "console": base_env(HARNESS_TRACING="console"),
    "otlp local": base_env(HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=LOCAL),
}


class InstalledProviderGuardTest(unittest.TestCase):
    """H2 and R1 on configure_tracing(settings) itself."""

    def _configure(self, env: dict[str, str], current: Any) -> tuple[BaseException | None, list]:
        from engine.telemetry import configure_tracing

        settings = load_settings(env)
        spy = SocketSpy()
        with globals_patched(current) as installed, environ(env), spy.active():
            try:
                configure_tracing(settings)
            except Exception as exc:
                return exc, list(installed)
            return None, list(installed)

    def _sdk(self, processor: Any) -> Any:
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        provider.add_span_processor(processor)
        self.addCleanup(provider.shutdown)
        return provider

    def test_local_otlp_that_trusts_proxy_env_is_refused(self):  # H2
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

        shapes = {
            "simple otlp localhost": lambda: SimpleSpanProcessor(
                _real_otlp(f"{LOCAL}/v1/traces", trust_env=True)),
            "batch otlp service name": lambda: BatchSpanProcessor(
                _real_otlp("http://phoenix:6006/v1/traces", trust_env=True)),
        }
        for shape, build in shapes.items():
            for mode, env in MODES.items():
                with self.subTest(shape=shape, mode=mode):
                    error, _ = self._configure(env, self._sdk(build()))
                    self.assertIsInstance(error, _refused(), f"{shape} trusted in {mode}")
                    self.assertEqual(error.setting, "telemetry.tracing")

    def test_local_otlp_that_ignores_proxy_env_is_refused_unless_engine_built(self):
        # Flipped from "..._is_accepted" (platform-config H2 control) by
        # orchestrator ruling R3 (docs/handoffs/platform-stack.md) and the
        # ADR-KE-010 M5 amendment: a provider built outside the engine is
        # refused whatever its exporters; the same exporter in a provider
        # from `engine.telemetry.build_provider` is the accepted control.
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        for mode, env in MODES.items():
            with self.subTest(mode=mode, built="outside the engine"):
                provider = self._sdk(SimpleSpanProcessor(
                    _real_otlp(f"{LOCAL}/v1/traces", trust_env=False)))
                error, _ = self._configure(env, provider)
                self.assertIsInstance(error, _refused(), "a foreign provider was trusted")
                self.assertEqual(error.setting, "telemetry.tracing")
            with self.subTest(mode=mode, built="by build_provider"):
                provider = _engine_built(_real_otlp(f"{LOCAL}/v1/traces", trust_env=False))
                self.addCleanup(provider.shutdown)
                error, _ = self._configure(env, provider)
                self.assertIsNone(error, repr(error))

    def test_custom_span_processor_is_refused(self):  # review B-R2-1, E1
        for mode, env in MODES.items():
            with self.subTest(mode=mode):
                shipper = _ship_anywhere_processor()
                error, installed = self._configure(env, self._sdk(shipper))
                self.assertIsInstance(error, _refused(),
                                      f"a custom SpanProcessor was trusted in {mode}")
                self.assertEqual(error.setting, "telemetry.tracing")
                self.assertEqual(installed, [])
                self.assertEqual(shipper.shipped, [])

    def test_local_otlp_with_unreachable_session_is_refused(self):  # review B-R2-1, W3
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

        shapes = {
            "simple otlp localhost": lambda: SimpleSpanProcessor(_make_session_unreachable(
                _real_otlp(f"{LOCAL}/v1/traces", trust_env=False))),
            "batch otlp service name": lambda: BatchSpanProcessor(_make_session_unreachable(
                _real_otlp("http://phoenix:6006/v1/traces", trust_env=False))),
        }
        for shape, build in shapes.items():
            for mode, env in MODES.items():
                with self.subTest(shape=shape, mode=mode):
                    error, _ = self._configure(env, self._sdk(build()))
                    self.assertIsInstance(error, _refused(),
                                          f"{shape} with no reachable session trusted in {mode}")
                    self.assertEqual(error.setting, "telemetry.tracing")

    def test_non_sdk_provider_is_refused(self):  # R1
        from opentelemetry.sdk.trace import TracerProvider

        inner = TracerProvider()
        self.addCleanup(inner.shutdown)
        for mode, env in MODES.items():
            with self.subTest(mode=mode):
                error, installed = self._configure(env, _vendor_provider(inner))
                self.assertIsInstance(error, _refused(),
                                      f"a non-SDK provider was trusted in {mode}")
                self.assertEqual(error.setting, "telemetry.tracing")
                self.assertEqual(installed, [], "tried to install over a foreign provider")

    def test_proxy_provider_is_accepted(self):  # R1 control: nothing installed
        from opentelemetry import trace

        for mode, env in MODES.items():
            with self.subTest(mode=mode):
                error, _ = self._configure(env, trace.ProxyTracerProvider())
                self.assertIsNone(error, repr(error))


class ResourceProjectNameTest(unittest.TestCase):
    """R2: product traces land in the `knowledge-engine` Phoenix project."""

    def test_provider_resource_carries_openinference_project_name(self):
        from openinference.semconv.resource import ResourceAttributes
        from opentelemetry import trace

        from engine.telemetry import configure_tracing

        self.assertEqual(ResourceAttributes.PROJECT_NAME, "openinference.project.name")
        for mode in ("console", "otlp local"):
            env = MODES[mode]
            with self.subTest(mode=mode):
                settings = load_settings(env)
                with globals_patched(trace.ProxyTracerProvider()) as installed, \
                        environ(env), SocketSpy().active():
                    configure_tracing(settings)
                    self.assertEqual(len(installed), 1)
                    attributes = dict(installed[0].resource.attributes)
                self.assertEqual(attributes.get("openinference.project.name"),
                                 "knowledge-engine", attributes)


# Environments for M3: passing ones, and ones check() refuses or cannot load.
PASSING = {
    "ci, passing": base_env(KE_ENV="ci"),
    "dev, auth off (warns only)": base_env(KE_ENV="dev", KE_AUTH__ENABLED="false"),
}
REFUSING = {
    "ci, auth off": base_env(KE_ENV="ci", KE_AUTH__ENABLED="false"),
    "ci, placeholder secret": base_env(KE_ENV="ci",
                                       KE_STORES__POSTGRES__PASSWORD="changeme-x"),
    "ci, otlp to a non-local collector": base_env(
        KE_ENV="ci", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=REMOTE),
    "ci, settings do not load": base_env(KE_ENV="ci", KE_API__LISTEN_PORT="notint"),
}


class StartupVerifiesProviderFirstTest(unittest.TestCase):
    """M3 + R1: no span reaches an unverified, already-installed provider."""

    def _foreign(self, shape: str) -> tuple[Any, Any]:
        """(the installed provider, the in-memory exporter that sees its spans)."""
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        memory = InMemorySpanExporter()
        sdk = TracerProvider()
        self.addCleanup(sdk.shutdown)
        extra = {
            "sdk, unknown exporter": _unknown_exporter,
            "sdk, otlp to an external collector": lambda: _real_otlp(
                f"{REMOTE}/v1/traces", trust_env=False),
            "sdk, local otlp that trusts proxy env": lambda: _real_otlp(
                f"{LOCAL}/v1/traces", trust_env=True),
            "non-sdk vendor provider": None,
            "sdk, in-memory only": None,
            "sdk, custom span processor": None,
        }[shape]
        if extra is not None:
            sdk.add_span_processor(SimpleSpanProcessor(extra()))
        if shape == "sdk, custom span processor":  # review B-R2-1, E1
            shipper = _ship_anywhere_processor()
            sdk.add_span_processor(shipper)
            self.addCleanup(lambda: self.assertEqual(shipper.shipped, [],
                                                     "spans reached the custom processor"))
        sdk.add_span_processor(SimpleSpanProcessor(memory))
        if shape == "non-sdk vendor provider":
            return _vendor_provider(sdk), memory
        return sdk, memory

    def _startup(self, env: dict[str, str], installed: Any) -> tuple[BaseException | None, list]:
        from engine.startup import startup

        tracing = importlib.import_module("harness_telemetry.tracing")
        spy = SocketSpy()
        with ExitStack() as stack:
            stack.enter_context(globals_patched(installed))
            stack.enter_context(mock.patch.object(
                tracing, "_tracer", installed.get_tracer("harness_telemetry")))
            stack.enter_context(environ(env))
            stack.enter_context(spy.active())
            try:
                startup()
            except Exception as exc:
                return exc, spy.attempts
        return None, spy.attempts

    # "sdk, in-memory only" was the accepted control until ruling R3
    # (docs/handoffs/platform-stack.md, ADR-KE-010 M5 amendment): built
    # outside the engine, it is now a foreign provider like the rest.
    FOREIGN = ("sdk, unknown exporter", "sdk, otlp to an external collector",
               "sdk, local otlp that trusts proxy env", "non-sdk vendor provider",
               "sdk, custom span processor", "sdk, in-memory only")

    def test_control_spans_do_reach_an_accepted_provider(self):
        # Ruling R3: the control is now built by engine.telemetry.build_provider.
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        memory = InMemorySpanExporter()
        provider = _engine_built(memory)
        self.addCleanup(provider.shutdown)
        error, _ = self._startup(PASSING["ci, passing"], provider)
        self.assertIsNone(error, repr(error))
        names = [s.name for s in memory.get_finished_spans()]
        self.assertIn("engine.startup", names, "span routing in this test is broken")

    def test_foreign_provider_refused_before_any_span_passing_settings(self):
        for shape in self.FOREIGN:
            for case, env in PASSING.items():
                with self.subTest(provider=shape, env=case):
                    provider, memory = self._foreign(shape)
                    error, attempts = self._startup(env, provider)
                    self.assertIsInstance(error, _refused(), f"{shape} trusted ({case})")
                    self.assertEqual(error.setting, "telemetry.tracing")
                    self.assertEqual([s.name for s in memory.get_finished_spans()], [],
                                     "spans reached the unverified provider")
                    self.assertEqual(attempts, [])

    def test_foreign_provider_gets_no_span_with_refusing_settings(self):
        refused = (_refused(), config_error())
        for shape in self.FOREIGN:
            for case, env in REFUSING.items():
                with self.subTest(provider=shape, env=case):
                    provider, memory = self._foreign(shape)
                    error, attempts = self._startup(env, provider)
                    self.assertIsInstance(error, refused, repr(error))
                    self.assertEqual([s.name for s in memory.get_finished_spans()], [],
                                     "spans reached the unverified provider")
                    self.assertEqual(attempts, [])


def _run_startup(env: dict[str, str], installed: Any) -> tuple[BaseException | None, list]:
    """startup() with `installed` as the global provider (see the module docstring)."""
    from engine.startup import startup

    tracing = importlib.import_module("harness_telemetry.tracing")
    spy = SocketSpy()
    with ExitStack() as stack:
        stack.enter_context(globals_patched(installed))
        stack.enter_context(mock.patch.object(
            tracing, "_tracer", installed.get_tracer("harness_telemetry")))
        stack.enter_context(environ(env))
        stack.enter_context(spy.active())
        try:
            startup()
        except Exception as exc:
            return exc, spy.attempts
    return None, spy.attempts


def _proxied_session() -> Any:
    import requests

    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": PROXY, "https": PROXY, "all": PROXY}
    return session


def _rerouting_session() -> Any:
    import requests
    from requests.adapters import HTTPAdapter

    class Reroute(HTTPAdapter):  # sends every request to the proxy host instead
        def send(self, request: Any, **kwargs: Any) -> Any:
            request.url = f"{PROXY}/v1/traces"
            return super().send(request, **kwargs)

    session = requests.Session()
    session.trust_env = False
    session.mount("http://", Reroute())
    session.mount("https://", Reroute())
    return session


def _otlp_with(url: str, session: Any) -> Any:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    exporter = OTLPSpanExporter(url, timeout=5, session=session)
    exporter.export = mock.MagicMock(name="export")  # type: ignore[method-assign]
    return exporter


def _rewritten_endpoint() -> Any:
    """Built for an external collector, then `_endpoint` rewritten to localhost
    (the real URL stays on the client; security M5 shape 3)."""
    import requests

    session = requests.Session()
    session.trust_env = False
    exporter = _otlp_with(f"{REMOTE}/v1/traces", session)
    exporter._endpoint = f"{LOCAL}/v1/traces"
    return exporter


class ProviderIdentityTest(unittest.TestCase):
    """PS-2.17 / security M5, ADR-KE-010 M5 amendment option (c), ruling R3:
    startup() accepts a ProxyTracerProvider or a provider that *is* one built
    by `engine.telemetry.build_provider`, and refuses every other provider,
    whatever its exporters look like."""

    # (shape, exporter factory or None). Every provider here is an SDK
    # TracerProvider built outside the engine, with an in-memory exporter
    # alongside so any span that reaches it is seen.
    OUTSIDE = {
        "local otlp, trust_env False, explicit session.proxies": lambda: _otlp_with(
            f"{LOCAL}/v1/traces", _proxied_session()),
        "local otlp, trust_env False, rerouting adapter mounted": lambda: _otlp_with(
            f"{LOCAL}/v1/traces", _rerouting_session()),
        "otlp with _endpoint rewritten to localhost": _rewritten_endpoint,
        "plain in-memory provider built outside the engine": None,
    }

    def _outside(self, make: Any) -> tuple[Any, Any, Any]:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        memory = InMemorySpanExporter()
        provider = TracerProvider()
        self.addCleanup(provider.shutdown)
        exporter = make() if make is not None else None
        if exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        provider.add_span_processor(SimpleSpanProcessor(memory))
        return provider, memory, exporter

    def test_provider_not_built_by_engine_is_refused(self):
        for shape, make in self.OUTSIDE.items():
            for case, env in PASSING.items():
                with self.subTest(shape=shape, env=case):
                    provider, memory, exporter = self._outside(make)
                    error, attempts = _run_startup(env, provider)
                    self.assertIsInstance(error, _refused(), f"{shape} was trusted ({case})")
                    self.assertEqual(error.setting, "telemetry.tracing")
                    self.assertEqual([s.name for s in memory.get_finished_spans()], [],
                                     "spans reached a provider the engine did not build")
                    if exporter is not None:
                        exporter.export.assert_not_called()
                    self.assertEqual(attempts, [])
        # Security M-1: a ProxyTracerProvider subclass that hands out tracers
        # from its own SDK provider is not "nothing installed". Only
        # type(provider) is ProxyTracerProvider is.
        for case, env in {**PASSING, "console, passing": base_env(
                KE_ENV="ci", HARNESS_TRACING="console")}.items():
            with self.subTest(shape="ProxyTracerProvider subclass with its own sink", env=case):
                provider, memory = _proxy_subclass(self)
                error, attempts = _run_startup(env, provider)
                self.assertIsInstance(error, _refused(), f"the proxy subclass was trusted ({case})")
                self.assertEqual(error.setting, "telemetry.tracing")
                self.assertEqual([s.name for s in memory.get_finished_spans()], [],
                                 "spans reached the proxy subclass's sink")
                self.assertEqual(attempts, [])

    def test_decoy_equal_to_an_engine_provider_is_refused(self):  # security L-2
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        from engine.telemetry import verify_provider

        live = _engine_built(InMemorySpanExporter())  # kept alive for the whole test
        self.addCleanup(live.shutdown)

        class Decoy(TracerProvider):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash(live)

        memory = InMemorySpanExporter()
        decoy = Decoy()
        decoy.add_span_processor(SimpleSpanProcessor(memory))
        self.addCleanup(decoy.shutdown)
        with globals_patched(decoy):
            with self.assertRaises(_refused()) as ctx:
                verify_provider([])
        self.assertEqual(ctx.exception.setting, "telemetry.tracing")
        error, attempts = _run_startup(PASSING["ci, passing"], decoy)
        self.assertIsInstance(error, _refused(), "a decoy equal to an engine provider was trusted")
        self.assertEqual([s.name for s in memory.get_finished_spans()], [])
        self.assertEqual(attempts, [])

    def test_configure_tracing_refuses_if_its_provider_is_not_the_global(self):  # M-1
        # OTel sets the global only once. If set_tracer_provider is ignored, or
        # another provider wins, configure_tracing must refuse, not return True.
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        from engine.telemetry import configure_tracing

        env = MODES["console"]
        settings = load_settings(env)
        foreign = TracerProvider()
        self.addCleanup(foreign.shutdown)
        proxy = trace.ProxyTracerProvider()
        winners = {"set ignored (global stays the proxy)": lambda built: proxy,
                   "another provider won the race": lambda built: foreign}
        for case, winner in winners.items():
            with self.subTest(case=case):
                built: list[Any] = []

                def get() -> Any:
                    return winner(built) if built else proxy

                with mock.patch.object(trace, "get_tracer_provider", get), \
                        mock.patch.object(trace, "set_tracer_provider", built.append), \
                        environ(env):
                    with self.assertRaises(_refused()) as ctx:
                        configure_tracing(settings)
                for provider in built:
                    provider.shutdown()
                self.assertEqual(ctx.exception.setting, "telemetry.tracing")

    def test_engine_built_provider_is_accepted(self):
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        for case, env in PASSING.items():
            with self.subTest(exporter="in-memory", env=case):
                memory = InMemorySpanExporter()
                provider = _engine_built(memory)
                self.addCleanup(provider.shutdown)
                error, attempts = _run_startup(env, provider)
                self.assertIsNone(error, repr(error))
                self.assertIn("engine.startup", [s.name for s in memory.get_finished_spans()])
                self.assertEqual(attempts, [])
        others = {
            "console": lambda: ConsoleSpanExporter(out=io.StringIO()),
            "local otlp": lambda: _otlp_with(f"{LOCAL}/v1/traces", _plain_session()),
        }
        for name, make in others.items():
            with self.subTest(exporter=name):
                provider = _engine_built(make())
                self.addCleanup(provider.shutdown)
                error, _ = _run_startup(PASSING["ci, passing"], provider)
                self.assertIsNone(error, repr(error))

    def test_build_provider_resource_and_processors(self):
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        from engine.telemetry import PROJECT_NAME

        cases = {
            "console": (ConsoleSpanExporter, SimpleSpanProcessor),
            "in-memory": (InMemorySpanExporter, SimpleSpanProcessor),
            "otlp": (lambda: _otlp_with(f"{LOCAL}/v1/traces", _plain_session()),
                     BatchSpanProcessor),
        }
        for name, (make, processor_type) in cases.items():
            with self.subTest(exporter=name):
                exporter = make()
                provider = _engine_built(exporter)
                self.addCleanup(provider.shutdown)
                processors = provider._active_span_processor._span_processors
                self.assertEqual([type(p) for p in processors], [processor_type])
                self.assertIn(exporter, exporters_of(provider))
                attributes = dict(provider.resource.attributes)
                self.assertEqual(attributes.get("openinference.project.name"), PROJECT_NAME)
                self.assertTrue(attributes.get("service.name"), attributes)
        provider = _engine_built(InMemorySpanExporter(), project_name="harness-tests")
        self.addCleanup(provider.shutdown)
        self.assertEqual(provider.resource.attributes.get("openinference.project.name"),
                         "harness-tests")

    def test_build_provider_does_not_install_globally(self):
        # The caller installs it (tests/support.py, configure_tracing).
        from opentelemetry import trace
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        with mock.patch.object(trace, "set_tracer_provider") as install:
            provider = _engine_built(InMemorySpanExporter())
        self.addCleanup(provider.shutdown)
        install.assert_not_called()

    def test_private_attribute_inspection_removed(self):
        # ADR-KE-010 M5 amendment: identity replaces the private-attribute walk.
        import engine.telemetry as telemetry

        for name in ("_verify_installed", "_exporters_of", "_sessions_of", "_ignores_proxy_env"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(telemetry, name), f"engine.telemetry.{name} still exists")

    def test_configure_tracing_installs_an_engine_built_provider(self):
        # The provider configure_tracing installs is itself accepted on a
        # second startup (it goes through build_provider).
        from opentelemetry import trace

        from engine.telemetry import configure_tracing, verify_provider

        env = MODES["console"]
        settings = load_settings(env)
        with globals_patched(trace.ProxyTracerProvider()) as installed, environ(env):
            configure_tracing(settings)
        self.assertEqual(len(installed), 1)
        with globals_patched(installed[0]):
            verify_provider([])  # must not raise

    def test_support_provider_is_engine_built(self):
        # tests/support.py builds the suite's provider with build_provider (ruling R3).
        from opentelemetry import trace

        from engine.telemetry import verify_provider
        from tests import support

        self.assertIsNone(support.BUILD_PROVIDER_ERROR,
                          f"tests/support.py fell back to setup_tracing: {support.BUILD_PROVIDER_ERROR!r}")
        self.assertIs(trace.get_tracer_provider(), support.PROVIDER)
        verify_provider([])  # the real global, unpatched: must not raise


def _proxy_subclass(test: unittest.TestCase) -> tuple[Any, Any]:
    """Security M-1: a ProxyTracerProvider subclass whose tracers come from
    its own SDK provider (an in-memory sink), so it passes an isinstance check."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    memory = InMemorySpanExporter()
    sink = TracerProvider()
    sink.add_span_processor(SimpleSpanProcessor(memory))
    test.addCleanup(sink.shutdown)

    class Sneaky(trace.ProxyTracerProvider):
        def get_tracer(self, *args: Any, **kwargs: Any) -> Any:
            return sink.get_tracer(*args, **kwargs)

    return Sneaky(), memory


def _plain_session() -> Any:
    import requests

    session = requests.Session()
    session.trust_env = False
    return session


if __name__ == "__main__":
    unittest.main()
