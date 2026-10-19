"""platform-config PS-1.3 / PS-1.4: the egress guard (DR30, ADR-KE-010).

Unit tests run with no network. Every test that could reach the socket layer
runs under a SocketSpy that records and refuses each resolve/connect attempt,
so "raises before any socket is opened" is asserted as zero attempts.

Contract used here (from docs/architecture.md §2.3):
- `engine.startup.check(settings)` raises `engine.startup.StartupRefused`;
- `engine.egress.EgressPolicy(allowlist)`, `EgressDenied`,
  `GuardedTransport(policy, inner_transport)` (an httpx transport);
- `engine.llm.client.ModelClient(settings, pass_name)` exposes its guarded
  `httpx.Client` as `.http_client` (the client a later `openai` SDK is given).
"""

from __future__ import annotations

import unittest
from typing import Any

from tests.engine_support import SocketSpy, base_env, load_settings

DENIED = "denied.example"
ALLOWED = "model-host.internal"


def _check(settings: Any) -> None:
    from engine.startup import check

    check(settings)


def _refused() -> type[Exception]:
    from engine.startup import StartupRefused

    return StartupRefused


def _guarded_client(allowlist: list[str], inner: Any = None) -> Any:
    import httpx

    from engine.egress import EgressPolicy, GuardedTransport

    transport = GuardedTransport(EgressPolicy(allowlist), inner or httpx.HTTPTransport())
    return httpx.Client(transport=transport, trust_env=False, follow_redirects=True)


def assert_denied_without_socket(test: unittest.TestCase, client: Any, url: str) -> None:
    """The DR38 core: a denied URL raises EgressDenied naming the host, and
    nothing reaches the socket layer."""
    from engine.egress import EgressDenied

    spy = SocketSpy()
    raised: BaseException | None = None
    with spy.active():
        try:
            client.get(url)
        except Exception as exc:  # judged below, after the socket check
            raised = exc
    test.assertEqual(spy.attempts, [], "a socket was touched before the guard refused")
    test.assertIsInstance(raised, EgressDenied)
    host = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
    test.assertIn(host, str(raised))


class EgressStartupTest(unittest.TestCase):
    def test_egress_guard_startup(self):
        refused = _refused()
        cases = {
            "pass base_url, empty allowlist": dict(
                KE_MODELS__COMPOSE__BASE_URL=f"http://{DENIED}:9000/v1"),
            "pass base_url, other host allowed": dict(
                KE_EGRESS_ALLOWLIST=ALLOWED,
                KE_MODELS__EMBED__BASE_URL=f"http://{DENIED}:9000/v1"),
            "one of several passes off-list": dict(
                KE_EGRESS_ALLOWLIST=ALLOWED,
                KE_MODELS__COMPOSE__BASE_URL=f"http://{ALLOWED}:9000/v1",
                KE_MODELS__AUDIT__BASE_URL=f"http://{DENIED}:9000/v1"),
            "model upstream, empty allowlist": dict(
                KE_MODEL_UPSTREAM=f"{DENIED}:9000"),
            "model upstream off-list": dict(
                KE_EGRESS_ALLOWLIST=ALLOWED, KE_MODEL_UPSTREAM=f"{DENIED}:9000"),
            "allowlist is exact, no suffix match": dict(
                KE_EGRESS_ALLOWLIST="example",
                KE_MODELS__REWRITE__BASE_URL=f"http://{DENIED}:9000/v1"),
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                settings = load_settings(base_env(**overrides))
                spy = SocketSpy()
                with spy.active(), self.assertRaises(refused) as ctx:
                    _check(settings)
                self.assertIn(DENIED, str(ctx.exception))
                self.assertEqual(spy.attempts, [])

        accepted = {
            "no host configured, empty allowlist": dict(),
            "every host on the list": dict(
                KE_EGRESS_ALLOWLIST=f"{ALLOWED},upstream.internal",
                KE_MODELS__COMPOSE__BASE_URL=f"http://{ALLOWED}:9000/v1",
                KE_MODELS__EMBED__BASE_URL=f"http://{ALLOWED}:9000/v1",
                KE_MODEL_UPSTREAM="upstream.internal:9001"),
            "case-folded match": dict(
                KE_EGRESS_ALLOWLIST="Model-Host.Internal",
                KE_MODELS__COMPOSE__BASE_URL=f"http://{ALLOWED}:9000/v1"),
        }
        for name, overrides in accepted.items():
            with self.subTest(case=name):
                # KE_ENV=ci, not the defaults' prod: prod is refused until
                # auth-audit (orchestrator ruling 2026-10-19, platform-offline
                # smoke loop 2; docs/architecture.md line 3900, ADR-KE-010).
                settings = load_settings(base_env(KE_ENV="ci", **overrides))
                spy = SocketSpy()
                with spy.active():
                    _check(settings)  # must not raise
                self.assertEqual(spy.attempts, [])


    def test_egress_startup_check_refuses_in_every_env(self):
        # Review B3 (kills M15): DR30 has no dev exemption. .env.example ships
        # KE_ENV=dev, so a dev bypass would ship in the template.
        refused = _refused()
        cases = {
            "pass base_url, empty allowlist": dict(
                KE_MODELS__COMPOSE__BASE_URL=f"http://{DENIED}:9000/v1"),
            "pass base_url off-list": dict(
                KE_EGRESS_ALLOWLIST=ALLOWED,
                KE_MODELS__EMBED__BASE_URL=f"http://{DENIED}:9000/v1"),
            "model upstream off-list": dict(
                KE_EGRESS_ALLOWLIST=ALLOWED, KE_MODEL_UPSTREAM=f"{DENIED}:9000"),
        }
        for env_name in ("dev", "ci", "prod"):
            for name, overrides in cases.items():
                with self.subTest(env=env_name, case=name):
                    settings = load_settings(base_env(KE_ENV=env_name, **overrides))
                    spy = SocketSpy()
                    with spy.active(), self.assertRaises(refused) as ctx:
                        _check(settings)
                    self.assertIn(DENIED, str(ctx.exception))
                    self.assertEqual(spy.attempts, [])


class EgressRuntimeTest(unittest.TestCase):
    def test_egress_guard_runtime(self):
        client = _guarded_client([ALLOWED])
        for url in (f"http://{DENIED}/v1/chat/completions",
                    f"https://{DENIED}:8443/v1/models",
                    "http://203.0.113.7:9000/v1/models",
                    f"http://{ALLOWED}.{DENIED}/v1/models"):
            with self.subTest(url=url):
                assert_denied_without_socket(self, client, url)

        # Empty allowlist denies everything.
        assert_denied_without_socket(self, _guarded_client([]), f"http://{ALLOWED}/v1/models")

    def test_egress_guard_allows_listed_host(self):
        import httpx

        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url.host))
            return httpx.Response(200, json={"ok": True})

        client = _guarded_client(["MODEL-HOST.internal"], httpx.MockTransport(handler))
        spy = SocketSpy()
        with spy.active():
            response = client.get(f"http://{ALLOWED}:9000/v1/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, [ALLOWED])
        self.assertEqual(spy.attempts, [])

    def test_egress_guard_checks_every_redirect_hop(self):
        import httpx

        from engine.egress import EgressDenied

        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url.host))
            return httpx.Response(302, headers={"location": f"http://{DENIED}/steal"})

        client = _guarded_client([ALLOWED], httpx.MockTransport(handler))
        spy = SocketSpy()
        with spy.active(), self.assertRaises(EgressDenied):
            client.get(f"http://{ALLOWED}/v1/models")
        self.assertEqual(seen, [ALLOWED], "the redirect target reached the inner transport")
        self.assertEqual(spy.attempts, [])

    def test_model_client_uses_guarded_transport(self):
        from engine.egress import GuardedTransport
        from engine.llm.client import ModelClient

        settings = load_settings(base_env(
            KE_EGRESS_ALLOWLIST=ALLOWED,
            KE_MODELS__COMPOSE__BASE_URL=f"http://{ALLOWED}:9000/v1"))
        client = ModelClient(settings, "compose")
        http_client = client.http_client
        self.assertIs(http_client.trust_env, False, "proxy env vars could reroute the client")
        self.assertIsInstance(http_client._transport, GuardedTransport)
        assert_denied_without_socket(self, http_client, f"http://{DENIED}/v1/models")

    def test_egress_guard_mutant_goes_red(self):
        """DR38: the runtime assertion fails when the guard is removed."""
        import httpx

        from engine.egress import EgressPolicy, GuardedTransport

        class GuardRemoved(GuardedTransport):  # the mutant: skips the check
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return self._mutant_inner.handle_request(request)

        inner = httpx.HTTPTransport()
        mutant = GuardRemoved(EgressPolicy([ALLOWED]), inner)
        mutant._mutant_inner = inner
        client = httpx.Client(transport=mutant, trust_env=False)
        with self.assertRaises(AssertionError):
            assert_denied_without_socket(self, client, f"http://{DENIED}/v1/models")


class LocalEndpointTest(unittest.TestCase):
    def test_is_local_endpoint(self):
        from engine.egress import is_local_endpoint

        service_names = ["gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix"]
        local = ["http://localhost:47101", "http://127.0.0.1:6006", "http://127.3.4.5:1",
                 "http://[::1]:6006", "http://phoenix:6006", "http://PHOENIX:6006/"]
        remote = ["http://collector.example.com:6006", "http://203.0.113.5:6006",
                  "https://phoenix.example.com", "http://localhost.example.com:6006",
                  "http://10.0.0.5:6006", "http://phoenix-evil:6006"]
        for url in local:
            with self.subTest(local=url):
                self.assertTrue(is_local_endpoint(url, service_names))
        for url in remote:
            with self.subTest(remote=url):
                self.assertFalse(is_local_endpoint(url, service_names))


if __name__ == "__main__":
    unittest.main()
