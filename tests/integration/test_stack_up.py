"""platform-stack-up (2a), integration: the gates-it boundary and /healthz.

- `test_gates_it_has_no_route_out` (F-A, architecture §2.2, ruling R1/R2):
  from gates-it a raw TCP connect to a TEST-NET-1 address fails, while the
  gateway's model listen port accepts (the control, so a network-less
  container cannot pass it). Rework 1: the failure must be an immediate
  ENETUNREACH/EHOSTUNREACH, not a timeout (review B1). The backend bridge
  gateway (the Docker host) must not answer either (security M-2).
  Rework 2 (ruling R1-B1 option (ii)): the backend has no fixed ipam pool, so
  with gateway_mode_ipv4=isolated Docker may hand the subnet's first address
  to a stack container. An address owned by a container of this project is
  skipped; any other first address must not answer (no RST). The decisive
  M-2 proof is now the smoke.sh host check of `docker network inspect`
  (tests/test_stack_scripts.py SmokeBackendIsolatedTest).
- `test_egress_allowlist_holds_with_network_access` (PS-2.7, DR30, DR38):
  with real network access to a stack host, the model client still refuses a
  host that is not on `KE_EGRESS_ALLOWLIST` before any connection; a mutant
  guard that allows everything does connect (the test can go red).
- `test_healthz` (PS-2.4, §2.4): `GET /healthz` on api returns 200
  `{"status": "ok"}`.
"""

from __future__ import annotations

import errno
import ipaddress
import json
import socket
import time
import unittest
import urllib.request
from contextlib import contextmanager
from typing import Any, Iterator
from unittest import mock

from tests.engine_support import base_env, load_settings
from tests.integration.stack import api_port, env_example_value, require_reachable

TEST_NET_1 = "192.0.2.1"  # RFC 5737: documentation only, never routed


UNREACHABLE = {errno.ENETUNREACH, errno.EHOSTUNREACH}
CONNECT_TIMEOUT_S = 2.0


def _bridge_gateways() -> list[str]:
    """The first host address of every directly connected IPv4 subnet: Docker's
    IPAM gives that address to the bridge (the host side) unless the network is
    created with gateway_mode_ipv4=isolated."""
    found: list[str] = []
    with open("/proc/net/route", encoding="ascii") as handle:
        next(handle)
        for line in handle:
            fields = line.split()
            iface, dest_hex, gw_hex, mask_hex = fields[0], fields[1], fields[2], fields[7]
            if iface == "lo" or gw_hex != "00000000" or dest_hex == "00000000":
                continue
            dest = int.from_bytes(bytes.fromhex(dest_hex), "little")
            mask = int.from_bytes(bytes.fromhex(mask_hex), "little")
            if mask == 0xFFFFFFFF:
                continue
            gateway = ipaddress.IPv4Address((dest & mask) + 1)
            found.append(str(gateway))
    return sorted(set(found))


STACK_HOSTS = ("gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix")


def _container_addresses() -> set[str]:
    """IPv4 addresses held by this project's containers on our networks:
    every stack service, and this gates-it container itself."""
    owned: set[str] = set()
    for name in (*STACK_HOSTS, socket.gethostname()):
        try:
            for info in socket.getaddrinfo(name, None, socket.AF_INET):
                owned.add(str(info[4][0]))
        except OSError:
            continue
    return owned


class NoRouteOutTest(unittest.TestCase):
    def _connect_error(self, host: str, port: int) -> tuple[BaseException | None, float]:
        started = time.monotonic()
        try:
            socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S).close()
        except OSError as exc:
            return exc, time.monotonic() - started
        return None, time.monotonic() - started

    def test_gates_it_has_no_route_out(self):
        model_port = int(env_example_value("KE_GATEWAY_MODEL_LISTEN", self))
        require_reachable(self, "gateway", model_port, "the gateway's model forward")
        # Review B1: a route out makes this connect time out (nothing answers
        # at TEST-NET-1); no route fails at once with ENETUNREACH/EHOSTUNREACH.
        # Only the immediate unreachable error passes.
        for port in (80, 443):
            with self.subTest(target=f"{TEST_NET_1}:{port}"):
                error, elapsed = self._connect_error(TEST_NET_1, port)
                self.assertIsNotNone(error, "gates-it reached an outside address")
                self.assertNotIsInstance(error, TimeoutError,
                                         "the connect timed out: gates-it has a route out")
                self.assertIn(getattr(error, "errno", None), UNREACHABLE,
                              f"expected ENETUNREACH/EHOSTUNREACH, got {error!r}")
                self.assertLess(elapsed, CONNECT_TIMEOUT_S)
        # Security M-2: the backend bridge must not give the host a foothold.
        # Reachable host: connect succeeds or is refused (RST). Isolated: no
        # answer at all.
        gateways = _bridge_gateways()
        self.assertTrue(gateways, "no directly connected subnet in /proc/net/route")
        owned = _container_addresses()
        self.assertTrue(owned, "precondition: stack service names resolve from gates-it")
        for gateway in gateways:
            if gateway in owned:
                continue  # isolated: Docker gave .1 to a container, not the host
            for port in (22, 80, 443, 6006, 11434):
                with self.subTest(bridge_gateway=f"{gateway}:{port}"):
                    error, _ = self._connect_error(gateway, port)
                    self.assertIsNotNone(error, f"gates-it reached the Docker host at {gateway}:{port}")
                    self.assertNotIsInstance(
                        error, ConnectionRefusedError,
                        f"the Docker host answered at {gateway}:{port} (RST): backend is not "
                        "isolated (gateway_mode_ipv4=isolated, security M-2)")


class _ConnectRecorder:
    """Records every outbound connect and lets it through (real network)."""

    def __init__(self) -> None:
        self.hosts: list[Any] = []

    @contextmanager
    def active(self) -> Iterator["_ConnectRecorder"]:
        real_connect = socket.socket.connect
        real_create = socket.create_connection
        recorder = self

        def connect(sock: socket.socket, address: Any) -> Any:
            recorder.hosts.append(address)
            return real_connect(sock, address)

        def create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
            recorder.hosts.append(address)
            return real_create(address, *args, **kwargs)

        with mock.patch.object(socket.socket, "connect", connect), \
                mock.patch.object(socket, "create_connection", create_connection):
            yield self


class EgressWithNetworkAccessTest(unittest.TestCase):
    def _client(self) -> Any:
        from engine.llm.client import ModelClient

        # api is reachable on backend, but only gateway is on the allowlist.
        env = base_env(KE_ENV="ci", KE_EGRESS_ALLOWLIST="gateway",
                       KE_MODELS__COMPOSE__BASE_URL=f"http://api:{api_port()}/v1")
        settings = load_settings(env)
        client = ModelClient(settings, "compose")
        self.addCleanup(client.close)
        return client

    def test_egress_allowlist_holds_with_network_access(self):
        from engine.egress import EgressDenied, EgressPolicy

        require_reachable(self, "api", api_port(), "the api service (network access control)")
        client = self._client()
        recorder = _ConnectRecorder()
        with recorder.active(), self.assertRaises(EgressDenied) as ctx:
            client.complete([{"role": "user", "content": "ping"}])
        self.assertEqual(ctx.exception.host, "api")
        self.assertEqual(recorder.hosts, [], "a connection was opened before the guard refused")

        # DR38: with the guard disabled, the same call does reach api, so this
        # test would go red if the guard were removed.
        mutant = _ConnectRecorder()
        with mock.patch.object(EgressPolicy, "require", lambda self, host: None), \
                mutant.active():
            try:
                self._client().complete([{"role": "user", "content": "ping"}])
            except Exception:
                pass  # api has no chat endpoint; the connection is what counts
        self.assertTrue(mutant.hosts, "the mutant opened no connection: the check is vacuous")


class HealthzTest(unittest.TestCase):
    def test_healthz(self):
        port = api_port()
        require_reachable(self, "api", port, "the api service")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # no proxy env
        with opener.open(f"http://api:{port}/healthz", timeout=5) as response:
            status = response.status
            body = json.loads(response.read().decode("utf-8"))
            content_type = response.headers.get("Content-Type", "")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})
        self.assertIn("application/json", content_type)


if __name__ == "__main__":
    unittest.main()
