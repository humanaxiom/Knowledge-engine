"""platform-stack-ready (2b), PS-2.5: `/readyz` and the readiness CLI (fast).

Design: docs/architecture.md §2.4 "/readyz" and "Smoke, host half";
ADR-KE-011 amendment "platform-stack-ready (2b plan)". Names adopted by the
orchestrator (handoff, "rulings on architect plan"): the reason vocabulary
includes `unreachable` and `not_configured`.

Contract used here:
- `engine.readiness.classify(exc) -> str`, one fixed vocabulary:
  `timeout | refused | unreachable | auth_failed | egress_denied |
  not_configured | error:<ExceptionClass>`; never message text.
- `engine.readiness.check_all(settings) -> dict`, shaped
  `{"ready": bool, "checks": {"postgres"|"neo4j"|"valkey"|"model_host":
  {"ok": bool, "reason": str|None, ...}}}`; `model_host` carries
  `"required": false` and never changes `ready`.
- `engine.api` adds `GET /readyz` (200 ready, 503 not) and the FastAPI
  dependency `get_settings`, which tests override.
- The I/O seams the probes use, as §2.4 names them, are what these tests
  stub: `socket.create_connection` (the raw dial), `psycopg.connect`,
  `neo4j.GraphDatabase.driver`, `redis.Redis` and
  `engine.llm.client.ModelClient.probe`. The implementation must call them
  through those module attributes (`import socket`, `import psycopg`,
  `import redis`, `neo4j.GraphDatabase`), so a patch reaches them.
- Spans: `api.readyz` CHAIN with one `readyz.<dep>` TOOL child per dependency;
  a failed check is ERROR with the reason (vocabulary only) as description.
- `python -m engine.readiness --wait-for ready|not-ready:<dep> --within N`
  polls `http://127.0.0.1:<api.listen_port>/readyz` once a second, with no
  proxy, exit 0 when met, 1 when not met within N (stderr: last status and
  body, no traceback), 2 for a dependency outside the four names.
"""

from __future__ import annotations

import errno
import http.server
import json
import re
import socket
import subprocess
import sys
import threading
import time
import unittest
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator
from unittest import mock

from tests.engine_support import ROOT, base_env, load_settings

DEPS = ("postgres", "neo4j", "valkey", "model_host")
STORES = ("postgres", "neo4j", "valkey")
VOCABULARY = re.compile(
    r"^(?:timeout|refused|unreachable|auth_failed|egress_denied|not_configured"
    r"|error:[A-Za-z_][A-Za-z0-9_]*)$")
MARKER = "pg-marker-pw-7f3a"  # a postgres password no body, span or log may show
MODEL_URL = "http://gateway:8102/v1"


MODEL_UPSTREAM = "modelhost.example:11434"


def _settings(**extra: str) -> Any:
    # Rework 1, Windows proof F1 (orchestrator ruling, handoff "rework round 1
    # of 5"): the model host counts as configured only when KE_MODEL_UPSTREAM
    # is set, since compose always points the base URL at the gateway. These
    # fixtures probe the model host, so they now set it too.
    env = base_env(KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD=MARKER,
                   KE_MODELS__COMPOSE__BASE_URL=MODEL_URL, KE_EGRESS_ALLOWLIST="gateway",
                   KE_MODEL_UPSTREAM=MODEL_UPSTREAM)
    env.update(extra)
    return load_settings(env)


def _refused_connect_error() -> Exception:
    import httpx

    error = httpx.ConnectError(f"[Errno 111] Connection refused {MARKER}")
    error.__cause__ = ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
    return error


@contextmanager
def stubbed_probes(settings: Any, refuse: tuple[str, ...] = (),
                   driver_errors: dict[str, BaseException] | None = None,
                   model_error: BaseException | None = None) -> Iterator[dict[str, mock.MagicMock]]:
    """Patch every I/O seam the probes use. `refuse` names stores whose raw
    dial is refused; `driver_errors` makes a store's driver step raise."""
    driver_errors = driver_errors or {}
    ports = {getattr(settings.stores, s).port: s for s in STORES}

    def dial(address: Any, *args: Any, **kwargs: Any) -> Any:
        store = ports.get(address[1])
        if store in refuse:
            raise ConnectionRefusedError(errno.ECONNREFUSED, f"Connection refused {MARKER}")
        return mock.MagicMock(name=f"socket to {store}")

    def raising(store: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            if store in driver_errors:
                raise driver_errors[store]
            return mock.MagicMock(name=f"{store} client")
        return call

    mocks = {
        "dial": mock.MagicMock(side_effect=dial),
        "postgres": mock.MagicMock(side_effect=raising("postgres")),
        "neo4j": mock.MagicMock(side_effect=raising("neo4j")),
        "valkey": mock.MagicMock(side_effect=raising("valkey")),
        "model": mock.MagicMock(side_effect=model_error, return_value=None),
    }
    with ExitStack() as stack:
        stack.enter_context(mock.patch("socket.create_connection", mocks["dial"]))
        stack.enter_context(mock.patch("psycopg.connect", mocks["postgres"]))
        stack.enter_context(mock.patch("neo4j.GraphDatabase.driver", mocks["neo4j"]))
        stack.enter_context(mock.patch("redis.Redis", mocks["valkey"]))
        stack.enter_context(mock.patch("engine.llm.client.ModelClient.probe", mocks["model"],
                                       create=True))
        yield mocks


@contextmanager
def readyz_client(settings: Any) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from engine.api import app, get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_settings, None)


class ReasonVocabularyTest(unittest.TestCase):
    def _classify(self, exc: BaseException) -> str:
        from engine.readiness import classify

        return classify(exc)

    def _assert(self, exc: BaseException, expected: str) -> None:
        reason = self._classify(exc)
        self.assertEqual(reason, expected)
        self.assertRegex(reason, VOCABULARY)
        self.assertNotIn(MARKER, reason)

    def test_readyz_reason_vocabulary(self):
        import httpx

        request = httpx.Request("GET", "http://gateway:8102/v1/models")

        def status(code: int) -> Exception:
            return httpx.HTTPStatusError(f"{code} {MARKER}", request=request,
                                         response=httpx.Response(code, request=request))

        def gaierror() -> Exception:
            return socket.gaierror(socket.EAI_NONAME, f"Name not known {MARKER}")

        cases: dict[str, tuple[Any, str]] = {
            "ConnectionRefusedError": (lambda: ConnectionRefusedError(errno.ECONNREFUSED, MARKER),
                                       "refused"),
            "httpx.ConnectError caused by a refusal": (_refused_connect_error, "refused"),
            "TimeoutError": (lambda: TimeoutError(MARKER), "timeout"),
            "socket.timeout": (lambda: socket.timeout(MARKER), "timeout"),
            "httpx.ConnectTimeout": (lambda: httpx.ConnectTimeout(MARKER), "timeout"),
            "httpx.ReadTimeout": (lambda: httpx.ReadTimeout(MARKER), "timeout"),
            "socket.gaierror": (gaierror, "unreachable"),
            "OSError EHOSTUNREACH": (lambda: OSError(errno.EHOSTUNREACH, MARKER), "unreachable"),
            "OSError ENETUNREACH": (lambda: OSError(errno.ENETUNREACH, MARKER), "unreachable"),
            "HTTP 401": (lambda: status(401), "auth_failed"),
            "HTTP 403": (lambda: status(403), "auth_failed"),
            "HTTP 500": (lambda: status(500), "error:HTTPStatusError"),
            "EgressDenied": (lambda: __import__("engine.egress", fromlist=["EgressDenied"])
                             .EgressDenied(MARKER), "egress_denied"),
            "anything else": (lambda: ValueError(f"postgresql://engine:{MARKER}@postgres/engine"),
                              "error:ValueError"),
        }
        for case, (build, expected) in cases.items():
            with self.subTest(case=case):
                self._assert(build(), expected)

    def test_readyz_reason_vocabulary_for_store_drivers(self):
        def psycopg_timeout() -> Exception:
            import psycopg

            return psycopg.errors.ConnectionTimeout(MARKER)

        def psycopg_bad_password() -> Exception:
            import psycopg

            return psycopg.errors.InvalidPassword(
                f'password authentication failed for user "engine" {MARKER}')

        def psycopg_bad_authorization() -> Exception:
            import psycopg

            return psycopg.errors.InvalidAuthorizationSpecification(MARKER)

        def psycopg_operational() -> Exception:
            import psycopg

            return psycopg.OperationalError(f"connection to server failed: {MARKER}")

        def neo4j_auth() -> Exception:
            import neo4j.exceptions

            return neo4j.exceptions.AuthError(MARKER)

        def redis_auth() -> Exception:
            import redis.exceptions

            return redis.exceptions.AuthenticationError(MARKER)

        cases = {
            "psycopg ConnectionTimeout": (psycopg_timeout, "timeout"),
            "psycopg sqlstate 28P01": (psycopg_bad_password, "auth_failed"),
            "psycopg sqlstate 28000": (psycopg_bad_authorization, "auth_failed"),
            "psycopg OperationalError, no sqlstate": (psycopg_operational, "error:OperationalError"),
            "neo4j AuthError": (neo4j_auth, "auth_failed"),
            "redis AuthenticationError": (redis_auth, "auth_failed"),
        }
        for case, (build, expected) in cases.items():
            with self.subTest(case=case):
                self._assert(build(), expected)


class ReadyzRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests import support

        cls.support = support

    def _get(self, settings: Any, **stubs: Any) -> tuple[Any, dict[str, mock.MagicMock]]:
        with stubbed_probes(settings, **stubs) as mocks, readyz_client(settings) as client:
            response = client.get("/readyz")
        return response, mocks

    def _assert_shape(self, body: dict[str, Any]) -> None:
        self.assertEqual(set(body), {"ready", "checks"})
        self.assertEqual(set(body["checks"]), set(DEPS))
        for dep, check in body["checks"].items():
            with self.subTest(dep=dep):
                if check["ok"]:
                    self.assertIsNone(check["reason"])
                else:
                    self.assertRegex(str(check["reason"]), VOCABULARY)
        self.assertIs(body["checks"]["model_host"]["required"], False)

    def test_readyz_is_traced(self):
        settings = _settings()
        self.support.EXPORTER.clear()
        response, _ = self._get(settings, refuse=("postgres",))
        self.assertEqual(response.status_code, 503)
        spans = self.support.EXPORTER.get_finished_spans()
        parents = [s for s in spans if s.name == "api.readyz"]
        self.assertEqual(len(parents), 1, f"one api.readyz span per request: {[s.name for s in spans]}")
        parent = parents[0]
        self.assertEqual(parent.attributes.get("openinference.span.kind"), "CHAIN")
        self.assertIs(parent.attributes.get("ke.readyz.ready"), False)
        from opentelemetry.trace import StatusCode

        for dep in DEPS:
            with self.subTest(dep=dep):
                children = [s for s in spans if s.name == f"readyz.{dep}"]
                self.assertEqual(len(children), 1)
                child = children[0]
                self.assertEqual(child.attributes.get("openinference.span.kind"), "TOOL")
                self.assertIsNotNone(child.parent)
                self.assertEqual(child.parent.span_id, parent.context.span_id)
                self.assertEqual(child.context.trace_id, parent.context.trace_id)
        failing = next(s for s in spans if s.name == "readyz.postgres")
        self.assertEqual(failing.status.status_code, StatusCode.ERROR)
        self.assertEqual(failing.status.description, "refused")
        self.assertIs(failing.attributes.get("ke.readyz.ok"), False)
        self.assertEqual(failing.attributes.get("ke.readyz.reason"), "refused")
        model = next(s for s in spans if s.name == "readyz.model_host")
        self.assertIs(model.attributes.get("ke.readyz.required"), False)
        for span in spans:
            if not span.name.startswith(("api.readyz", "readyz.")):
                continue
            with self.subTest(span=span.name):
                text = json.dumps({k: str(v) for k, v in (span.attributes or {}).items()})
                self.assertNotIn(MARKER, text + str(span.status.description))
                self.assertFalse([e for e in span.events if e.name == "exception"],
                                 "no record_exception on readyz spans (message text could leak)")

    def test_readyz_ready_excludes_model_host(self):
        settings = _settings()
        with self.subTest(case="stores ok, model host refused"):
            response, _ = self._get(settings, model_error=_refused_connect_error())
            body = response.json()
            self.assertEqual(response.status_code, 200, body)
            self._assert_shape(body)
            self.assertIs(body["ready"], True)
            self.assertEqual(body["checks"]["model_host"]["reason"], "refused")
            self.assertIs(body["checks"]["model_host"]["ok"], False)
        with self.subTest(case="all ok"):
            response, _ = self._get(settings)
            body = response.json()
            self.assertEqual(response.status_code, 200, body)
            self._assert_shape(body)
            self.assertTrue(all(c["ok"] for c in body["checks"].values()), body)
        for store in STORES:
            with self.subTest(case=f"{store} refused"):
                response, _ = self._get(settings, refuse=(store,))
                body = response.json()
                self.assertEqual(response.status_code, 503, body)
                self._assert_shape(body)
                self.assertIs(body["ready"], False)
                self.assertEqual(body["checks"][store]["reason"], "refused")
                for other in set(STORES) - {store}:
                    self.assertIs(body["checks"][other]["ok"], True, other)
        with self.subTest(case="model host not configured"):
            unset = load_settings(base_env(KE_ENV="ci"))
            self.assertIsNone(unset.models.compose.base_url, "precondition: defaults.yaml has null")
            response, mocks = self._get(unset)
            body = response.json()
            self.assertEqual(response.status_code, 200, body)
            self.assertEqual(body["checks"]["model_host"],
                             {"ok": False, "reason": "not_configured", "required": False})
            mocks["model"].assert_not_called()

    def test_readyz_body_never_carries_error_text(self):
        settings = _settings()
        errors = {"postgres": RuntimeError(f"postgresql://engine:{MARKER}@postgres:5432/engine")}
        response, _ = self._get(settings, driver_errors=errors)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(MARKER, response.text)
        self.assertNotIn("postgresql://", response.text)
        self.assertEqual(response.json()["checks"]["postgres"]["reason"], "error:RuntimeError")


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class StoreProbeTest(unittest.TestCase):
    def test_store_probe_classifies_closed_port(self):
        # `gates` has `lo` under network_mode: none, so a closed loopback port
        # refuses at once: no stub, the real dial.
        from engine.readiness import check_all

        ports = [_closed_port() for _ in STORES]
        env = {}
        for store, port in zip(STORES, ports):
            env[f"KE_STORES__{store.upper()}__HOST"] = "127.0.0.1"
            env[f"KE_STORES__{store.upper()}__PORT"] = str(port)
        settings = load_settings(base_env(KE_ENV="ci", **env))
        started = time.monotonic()
        result = check_all(settings)
        elapsed = time.monotonic() - started
        for store in STORES:
            with self.subTest(store=store):
                self.assertEqual(result["checks"][store]["reason"], "refused", result)
        self.assertIs(result["ready"], False)
        self.assertEqual(result["checks"]["model_host"]["reason"], "not_configured")
        self.assertLess(elapsed, settings.readiness.timeout_s,
                        f"a refused port must answer at once, took {elapsed:.2f}s")


# --------------------------------------------------------------------------
# The readiness CLI the smoke runs inside `api` (§2.4 Smoke).
# --------------------------------------------------------------------------

READY_BODY = {"ready": True, "checks": {d: {"ok": d != "model_host", "reason": None if d != "model_host"
                                           else "not_configured"} for d in DEPS}}


def _body(failing: str) -> dict[str, Any]:
    checks = {d: {"ok": True, "reason": None} for d in DEPS}
    checks[failing] = {"ok": False, "reason": "refused"}
    checks["model_host"]["required"] = False  # type: ignore[index]
    return {"ready": failing == "model_host", "checks": checks}


class _Server:
    """A loopback HTTP server that answers GET /readyz from a script of
    (status, body) pairs, repeating the last one."""

    def __init__(self, script: list[tuple[int, dict[str, Any]]]) -> None:
        self.script = list(script)
        self.requests = 0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                outer.requests += 1
                status, body = outer.script[min(outer.requests, len(outer.script)) - 1]
                data = json.dumps(body).encode()
                self.send_response(status if self.path == "/readyz" else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:
                return

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self.httpd.server_address[1])
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "_Server":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class ReadinessCliTest(unittest.TestCase):
    def _cli(self, port: int, *args: str) -> tuple[subprocess.CompletedProcess, float]:
        env = base_env(KE_ENV="ci", KE_API__LISTEN_PORT=str(port), PYTHONPATH=str(ROOT),
                       # A proxy the CLI must ignore: a client that honoured it
                       # would never reach the server.
                       http_proxy="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9",
                       no_proxy="", NO_PROXY="")
        started = time.monotonic()
        result = subprocess.run([sys.executable, "-m", "engine.readiness", *args], cwd=ROOT,
                                env=env, capture_output=True, text=True, timeout=60)
        return result, time.monotonic() - started

    def test_readiness_cli_condition_met(self):
        cases = {
            "ready at once": (["--wait-for", "ready"], [(200, READY_BODY)]),
            "ready after two not-ready answers": (
                ["--wait-for", "ready"], [(503, _body("postgres")), (503, _body("postgres")),
                                          (200, READY_BODY)]),
            "not-ready:postgres": (["--wait-for", "not-ready:postgres"], [(503, _body("postgres"))]),
        }
        for case, (args, script) in cases.items():
            with self.subTest(case=case), _Server(script) as server:
                result, _ = self._cli(server.port, *args, "--within", "15")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertGreaterEqual(server.requests, len(script),
                                        "the CLI did not poll the route (or went through a proxy)")

    def test_readiness_cli_condition_never_met(self):
        cases = {
            "ready, store down": (["--wait-for", "ready"], [(503, _body("postgres"))]),
            "not-ready:postgres, neo4j down instead": (
                ["--wait-for", "not-ready:postgres"], [(503, _body("neo4j"))]),
            "not-ready:postgres, all ready": (["--wait-for", "not-ready:postgres"], [(200, READY_BODY)]),
        }
        for case, (args, script) in cases.items():
            with self.subTest(case=case), _Server(script) as server:
                result, elapsed = self._cli(server.port, *args, "--within", "2")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertLess(elapsed, 2 + 8, "the CLI must stop at --within (plus a margin)")
                self.assertRegex(result.stderr, r"\b(?:503|200)\b", "stderr names the last status")
                self.assertNotIn("Traceback", result.stderr)

    def test_readiness_cli_api_unreachable(self):
        result, elapsed = self._cli(_closed_port(), "--wait-for", "ready", "--within", "2")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertLess(elapsed, 2 + 8)
        self.assertNotIn("Traceback", result.stderr)

    def test_readiness_cli_unknown_dependency_is_a_usage_error(self):
        for arg in ("not-ready:mysql", "not-ready:", "sometimes"):
            with self.subTest(arg=arg):
                result, elapsed = self._cli(_closed_port(), "--wait-for", arg, "--within", "30")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertLess(elapsed, 15, "a usage error must not wait")


# --------------------------------------------------------------------------
# Rework 1 (handoff "orchestrator: rework round 1 of 5").
# - Windows proof F1: compose always sets the base URLs to the gateway's model
#   forward, so "not configured" means KE_MODEL_UPSTREAM is empty. Then the
#   model check is `not_configured` and makes no probe call.
# - Review R-B2 (mutants MP1, RZ9, MP2): the real `ModelClient.probe`, with
#   no socket: an off-list host is denied by the egress guard before any
#   connection (with the DR38 control: guard disabled, a connection is
#   attempted), HTTP errors are raised and classified, and the readiness
#   timeout reaches the request.
# - Security L-13: postgres connections pass gssencmode=disable.
# --------------------------------------------------------------------------

OFF_LIST_URL = "http://model.offlist.example:8102/v1"
STORE_PORTS = {5432: "postgres", 7687: "neo4j", 6379: "valkey"}


@contextmanager
def stores_ok(settings: Any) -> Iterator[list[Any]]:
    """Every store answers; any other dial (the model probe's) is recorded
    in the yielded list and refused. The model probe itself is NOT stubbed."""
    ports = {getattr(settings.stores, s).port: s for s in STORES}
    other_dials: list[Any] = []

    def dial(address: Any, *args: Any, **kwargs: Any) -> Any:
        if address[1] in ports:
            return mock.MagicMock(name=f"socket to {ports[address[1]]}")
        other_dials.append(address)
        raise OSError(errno.ENETUNREACH, "network disabled in unit tests")

    with ExitStack() as stack:
        stack.enter_context(mock.patch("socket.create_connection", side_effect=dial))
        stack.enter_context(mock.patch("psycopg.connect"))
        stack.enter_context(mock.patch("neo4j.GraphDatabase.driver"))
        stack.enter_context(mock.patch("redis.Redis"))
        yield other_dials


@contextmanager
def model_answers(status: int = 200) -> Iterator[list[Any]]:
    """Every httpx.HTTPTransport the code builds is a MockTransport that
    answers `status` and records each request it gets."""
    import httpx

    requests: list[Any] = []

    def handler(request: Any) -> Any:
        requests.append(request)
        return httpx.Response(status, json={"data": []})

    with mock.patch("httpx.HTTPTransport", side_effect=lambda *a, **k: httpx.MockTransport(handler)):
        yield requests


def _model_client(settings: Any) -> Any:
    from engine.llm.client import ModelClient

    return ModelClient(settings, "compose")


class ModelHostNotConfiguredTest(unittest.TestCase):  # Windows proof F1
    def test_readyz_model_host_not_configured_without_upstream(self):
        from engine.readiness import check_all

        cases = {"KE_MODEL_UPSTREAM unset": None, "KE_MODEL_UPSTREAM empty": ""}
        for case, upstream in cases.items():
            with self.subTest(case=case):
                env_extra ={} if upstream is None else {"KE_MODEL_UPSTREAM": upstream}
                env = base_env(KE_ENV="ci", KE_MODELS__COMPOSE__BASE_URL=MODEL_URL,
                               KE_EGRESS_ALLOWLIST="gateway", **env_extra)
                settings = load_settings(env)
                self.assertIsNotNone(settings.models.compose.base_url,
                                     "precondition: the base URL points at the gateway, as compose sets it")
                self.assertFalse(settings.models.model_upstream, "precondition: no upstream")
                with stubbed_probes(settings) as mocks:
                    result = check_all(settings)
                self.assertEqual(result["checks"]["model_host"],
                                 {"ok": False, "reason": "not_configured", "required": False},
                                 "an empty KE_MODEL_UPSTREAM must read as not_configured (F1)")
                mocks["model"].assert_not_called()
                self.assertIs(result["ready"], True)

    def test_readyz_model_host_not_configured_without_base_url(self):  # review N-R4, mutant F1b
        # The upstream is set but the base URL is null: still not_configured
        # (not error:<Class>), and no client is built, no socket dialled and
        # no request sent. The real probe path is left in place.
        import engine.readiness as readiness

        env = base_env(KE_ENV="ci", KE_EGRESS_ALLOWLIST="gateway", KE_MODEL_UPSTREAM=MODEL_UPSTREAM)
        settings = load_settings(env)
        self.assertIsNone(settings.models.compose.base_url, "precondition: defaults.yaml has null")
        self.assertEqual(settings.models.model_upstream, MODEL_UPSTREAM, "precondition: upstream set")
        with stores_ok(settings) as other_dials, model_answers() as requests, \
                mock.patch.object(readiness, "ModelClient", wraps=readiness.ModelClient) as client:
            result = readiness.check_all(settings)
        self.assertEqual(result["checks"]["model_host"],
                         {"ok": False, "reason": "not_configured", "required": False},
                         "a null base URL must read as not_configured even with an upstream set")
        client.assert_not_called()
        self.assertEqual(other_dials, [], "no socket may be dialled for an unconfigured model host")
        self.assertEqual(requests, [], "no request may be sent for an unconfigured model host")
        self.assertIs(result["ready"], True)

    def test_readyz_model_host_probed_when_upstream_set(self):  # control for F1
        from engine.readiness import check_all

        settings = _settings()
        self.assertEqual(settings.models.model_upstream, MODEL_UPSTREAM)
        with stubbed_probes(settings) as mocks:
            result = check_all(settings)
        mocks["model"].assert_called_once()
        self.assertEqual(result["checks"]["model_host"], {"ok": True, "reason": None, "required": False})


class ModelProbeTest(unittest.TestCase):  # review R-B2
    def test_model_probe_off_list_host_is_denied_before_any_socket(self):  # MP1
        from engine.egress import EgressDenied
        from tests.engine_support import SocketSpy

        settings = _settings(KE_MODELS__COMPOSE__BASE_URL=OFF_LIST_URL)
        self.assertNotIn("model.offlist.example", settings.egress_allowlist)
        client = _model_client(settings)
        self.addCleanup(client.close)
        spy = SocketSpy()
        with spy.active(), self.assertRaises(EgressDenied):
            client.probe(1.0)
        self.assertEqual(spy.attempts, [], "the probe reached the socket layer for an off-list host")

        # DR38 control: with the guard disabled, the same probe does attempt a
        # connection, so the spy would have seen one had the guard not held.
        control = _model_client(settings)
        self.addCleanup(control.close)
        control_spy = SocketSpy()
        with mock.patch("engine.egress.EgressPolicy.require", return_value=None), \
                control_spy.active():
            with self.assertRaises(Exception) as raised:
                control.probe(1.0)
        self.assertNotIsInstance(raised.exception, EgressDenied)
        self.assertTrue(control_spy.attempts,
                        "control: with the guard off the probe must attempt a connection")

    def test_readyz_reports_egress_denied_through_the_real_probe(self):  # MP1
        from engine.readiness import check_all

        settings = _settings(KE_MODELS__COMPOSE__BASE_URL=OFF_LIST_URL)
        with stores_ok(settings) as other_dials:
            result = check_all(settings)
        self.assertEqual(result["checks"]["model_host"]["reason"], "egress_denied", result)
        self.assertEqual(other_dials, [], "the model probe dialled an off-list host")
        self.assertIs(result["ready"], True)

    def test_model_probe_http_errors_are_raised_and_classified(self):  # RZ9
        import httpx

        from engine.readiness import check_all

        cases = {200: None, 401: "auth_failed", 403: "auth_failed", 404: "error:HTTPStatusError",
                 500: "error:HTTPStatusError"}
        for status, reason in cases.items():
            with self.subTest(status=status):
                settings = _settings()
                with model_answers(status) as requests:
                    client = _model_client(settings)
                    try:
                        if reason is None:
                            client.probe(1.0)
                        else:
                            with self.assertRaises(httpx.HTTPStatusError):
                                client.probe(1.0)
                    finally:
                        client.close()
                    self.assertEqual(len(requests), 1)
                    self.assertEqual(requests[0].method, "GET")
                    self.assertEqual(str(requests[0].url), f"{MODEL_URL}/models")
                with model_answers(status), stores_ok(settings):
                    result = check_all(settings)
                model = result["checks"]["model_host"]
                self.assertEqual(model["reason"], reason, result)
                self.assertIs(model["ok"], reason is None)
                self.assertIs(result["ready"], True, "the model host never changes ready")

    def test_model_probe_passes_its_timeout(self):  # MP2
        settings = _settings(KE_MODELS__COMPOSE__TIMEOUT_S="120",
                             KE_READINESS__TIMEOUT_S="1.5")
        with model_answers() as requests:
            client = _model_client(settings)
            try:
                client.probe(1.25)
            finally:
                client.close()
        timeout = requests[0].extensions.get("timeout", {})
        self.assertTrue(timeout, "the request carries no timeout")
        self.assertEqual(set(timeout.values()), {1.25},
                         f"probe(1.25) must bound every phase by 1.25 s, not the pass's 120 s: {timeout}")

        from engine.readiness import check_all

        with model_answers() as requests, stores_ok(settings):
            check_all(settings)
        self.assertEqual(len(requests), 1)
        timeout = requests[0].extensions.get("timeout", {})
        self.assertEqual(set(timeout.values()), {1.5},
                         f"/readyz must probe with readiness.timeout_s (1.5 s): {timeout}")


class PostgresGssencTest(unittest.TestCase):  # security L-13
    def test_postgres_probe_disables_gss_encryption(self):
        from engine.readiness import check_all

        settings = _settings()
        with stubbed_probes(settings) as mocks:
            check_all(settings)
        mocks["postgres"].assert_called_once()
        call = mocks["postgres"].call_args
        conninfo = " ".join(str(a) for a in call.args)
        self.assertTrue(call.kwargs.get("gssencmode") == "disable"
                        or re.search(r"\bgssencmode=disable\b", conninfo),
                        f"psycopg.connect must pass gssencmode=disable (L-13): {call}")

    def test_every_postgres_connect_in_engine_disables_gss_encryption(self):
        calls = 0
        for path in sorted((ROOT / "engine").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"psycopg\.(?:connect|Connection\.connect|AsyncConnection\.connect)\(",
                                     text):
                calls += 1
                depth, end = 0, match.end() - 1
                for end in range(match.end() - 1, len(text)):
                    depth += {"(": 1, ")": -1}.get(text[end], 0)
                    if depth == 0:
                        break
                with self.subTest(file=str(path.relative_to(ROOT)), at=match.start()):
                    self.assertIn("gssencmode", text[match.start():end + 1],
                                  "every postgres connection passes gssencmode=disable (L-13)")
        self.assertGreater(calls, 0, "no psycopg connect call found: the scan is stale")


if __name__ == "__main__":
    unittest.main()
