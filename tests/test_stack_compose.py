"""platform-stack-up (2a): the compose topology, ports and images, statically.

Criteria: docs/requirements.md PS-2.1 (digests), PS-2.2 (ports), PS-2.3
(restart), PS-2.7 *Mechanism* (gates-it), PS-2.10 (edge), PS-2.11 (socket),
PS-2.12 (named volumes), PS-2.14 (compose passes the bind address), PS-1.9
*Not shipped*. Design: docs/architecture.md §2.1, §2.4, ADR-KE-009, ADR-KE-011
and its 2026-10-19 ports amendment. Test names per ruling R1
(docs/handoffs/platform-stack.md).
"""

from __future__ import annotations

import re
import unittest
from typing import Any

from tests import compose_support as cs
from tests.engine_support import ROOT, read_env_example

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
PUBLISHED = re.compile(
    r"^\$\{KE_BIND_ADDRESS:-127\.0\.0\.1\}:\$\{(KE_[A-Z0-9_]+_PORT):-(\d+)\}:(?P<target>[^:]+)$")
PUBLISHED_PORT = re.compile(r"^\$\{(KE_[A-Z0-9_]+_PORT):-(\d+)\}$")
PORT_RANGE = range(47100, 47200)
FIRST_PARTY_REPOS = {"ke-app", "ke-gateway", "ke-gates"}
OFFLINE_SERVICES = ("dind", "offline-client")  # profile `offline` (architecture §2.5)


def _network_defs() -> dict[str, dict[str, Any]]:
    defs: dict[str, dict[str, Any]] = {}
    for path in cs.compose_files():
        for name, definition in (cs.load(path).get("networks") or {}).items():
            defs[name] = definition or {}
    return defs


def _internal(name: str) -> bool:
    return _network_defs().get(name, {}).get("internal") is True


def _find_service(name: str) -> dict[str, Any] | None:
    # The base file defines each service; overlays (the `.env` mask) hold only
    # partial extras, so a per-service property is read from the base (review B1).
    return cs.services().get(name)


class ServicesTest(unittest.TestCase):
    def test_compose_services_have_restart_policy(self):  # PS-2.3, DR41
        services = cs.services()
        missing = [s for s in cs.STACK_SERVICES if s not in services]
        self.assertEqual(missing, [], f"stack services missing from docker-compose.yml (PS-2.1)")
        for name, svc in services.items():
            with self.subTest(service=name):
                if cs.is_stack_service(svc):
                    self.assertEqual(svc.get("restart"), "unless-stopped",
                                     f"{name} is long-running but has no unless-stopped policy")
                else:
                    self.assertIn(svc.get("restart"), (None, "no"),
                                  f"one-shot {name} must not restart")
        for name in cs.ONE_SHOT_SERVICES:
            with self.subTest(one_shot=name):
                svc = _find_service(name)
                self.assertIsNotNone(svc, f"{name} is not defined in any compose file")
                self.assertTrue(svc.get("profiles"), f"{name} must be profile-only")
        # §2.6 item 7: the offline check's services are profile-only and
        # never restart, in whichever compose file defines them.
        defined = {n: s for _, n, s in cs.all_services() if n in OFFLINE_SERVICES and s.get("image")}
        for name in OFFLINE_SERVICES:
            with self.subTest(offline=name):
                self.assertIn(name, defined, f"{name} is not defined in any compose file (§2.5)")
                self.assertTrue(defined.get(name, {}).get("profiles"), f"{name} must be profile-only")
                self.assertIn(defined.get(name, {}).get("restart"), (None, "no"),
                              f"{name} must not restart")

    def test_compose_images_pinned_by_digest(self):  # PS-2.1
        seen = 0
        pulled_dind = False
        for file, name, svc in cs.all_services():
            image = svc.get("image")
            with self.subTest(file=file, service=name, image=image):
                if "build" in svc:
                    continue  # built locally; its Dockerfile's FROM lines are checked below
                if image is None:
                    continue  # an overlay entry that only changes settings
                # platform-offline (architecture §2.5 compose additions,
                # §2.6 items 7 and 9): `offline-client` runs the locally built
                # ke-gates image at ${KE_IMAGE_TAG:-local} without a `build:`
                # of its own. First-party images are never pulled (their
                # Dockerfile FROM lines are checked below); everything else is.
                if str(image).split(":", 1)[0] in FIRST_PARTY_REPOS:
                    continue
                seen += 1
                if name == "dind":
                    pulled_dind = True
                self.assertRegex(str(image), DIGEST, "image is not pinned by digest")
        self.assertGreater(seen, 0, "no pulled image found in any compose file")
        # §2.6 item 7: the digest check covers the offline check's dind.
        self.assertTrue(pulled_dind, "dind (profile offline) is not defined with a pulled image")

    def test_dockerfiles_pin_base_images_by_digest(self):  # PS-2.1, §2.4 Images
        for required in ("app.Dockerfile", "gateway.Dockerfile", "gates.Dockerfile"):
            with self.subTest(required=required):
                self.assertTrue((ROOT / "docker" / required).is_file(),
                                f"docker/{required} is missing (architecture §2.4 Images)")
        for dockerfile in sorted((ROOT / "docker").rglob("*Dockerfile")):
            text = dockerfile.read_text(encoding="utf-8")
            stages = set(re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", text, re.M | re.I))
            for image in re.findall(r"^FROM\s+(?:--\S+\s+)*(\S+)", text, re.M | re.I):
                with self.subTest(dockerfile=dockerfile.name, image=image):
                    if image in stages:
                        continue
                    self.assertRegex(image, DIGEST, "base image is not pinned by digest")


class PortsTest(unittest.TestCase):
    """PS-2.2 with the port ruling (ADR-KE-011 amendment, §2.4)."""

    def test_published_ports_use_bind_address(self):
        publishers: dict[str, set[str]] = {}
        for file, name, svc in cs.all_services():
            for entry in cs.port_entries(svc):
                with self.subTest(file=file, service=name, entry=entry):
                    self.assertNotIn(":?", str(entry), "`:?` breaks verify.sh and CI (no .env)")
                    if isinstance(entry, dict):
                        self.assertEqual(entry.get("host_ip"), cs.BIND_DEFAULT)
                        match = PUBLISHED_PORT.match(str(entry.get("published", "")))
                        self.assertIsNotNone(match, f"published port is not ${{KE_<X>_PORT:-n}}")
                    else:
                        match = PUBLISHED.match(str(entry))
                        self.assertIsNotNone(
                            match, "not ${KE_BIND_ADDRESS:-127.0.0.1}:${KE_<X>_PORT:-n}:<port>")
                    if match:
                        publishers.setdefault(name, set()).add(match.group(1))
        self.assertEqual(set(publishers), {"gateway"}, "only gateway may publish ports")
        self.assertEqual(publishers.get("gateway"), {"KE_API_PORT", "KE_PHOENIX_PORT"},
                         "gateway publishes the API and Phoenix ports (§2.4)")

    def test_env_example_ports_in_range_and_unique(self):
        env = read_env_example()
        ports = {k: v for k, v in env.items() if re.fullmatch(r"KE_[A-Z0-9_]+_PORT", k)}
        self.assertEqual(ports.get("KE_API_PORT"), "47100", "§2.4: KE_API_PORT=47100")
        self.assertEqual(ports.get("KE_PHOENIX_PORT"), "47101", "§2.4: KE_PHOENIX_PORT=47101")
        for key, value in ports.items():
            with self.subTest(key=key):
                self.assertTrue(value.isdigit() and int(value) in PORT_RANGE,
                                f"{key}={value} is outside 47100-47199")
        values = list(ports.values())
        self.assertEqual(len(values), len(set(values)), f"published ports collide: {ports}")

    def test_compose_defaults_match_env_example(self):
        env = read_env_example()
        found = 0
        for path in cs.compose_files():
            for var, default in cs.compose_defaults(path.read_text(encoding="utf-8")):
                found += 1
                with self.subTest(file=path.name, var=var):
                    self.assertIn(var, env, f"{var} has a compose default but is not in .env.example")
                    self.assertEqual(default, env.get(var),
                                     f"compose default for {var} != .env.example")
        self.assertGreater(found, 0)
        published = {m.group(1) for _, _, svc in cs.all_services()
                     for e in cs.port_entries(svc)
                     for m in [PUBLISHED.match(str(e))] if m}
        for var in published:
            with self.subTest(published=var):
                self.assertIn(var, env, f"published {var} is not set in .env.example")

    def test_env_example_bind_address_is_loopback(self):  # PS-2.2 "Loopback by default"
        value = read_env_example().get("KE_BIND_ADDRESS")
        self.assertIn(value, (None, "127.0.0.1"), f"KE_BIND_ADDRESS={value!r}")
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("KE_BIND_ADDRESS=127.0.0.1", text, "§2.4: .env.example sets it, with a comment")

    def test_compose_passes_bind_address_to_app(self):  # PS-2.14, Q33, R4
        services = cs.services()
        for name in ("api", "worker", "gateway"):
            with self.subTest(service=name):
                env = cs.environment(services.get(name, {}))
                self.assertEqual(env.get("KE_BIND_ADDRESS"), cs.BIND_DEFAULT,
                                 f"{name} must get the same KE_BIND_ADDRESS compose binds with")
                self.assertRegex(env.get("KE_ENV", ""), r"^\$\{KE_ENV[:}-]",
                                 f"{name} must get KE_ENV from .env")


class NetworksTest(unittest.TestCase):
    def test_only_gateway_on_edge_network(self):  # PS-2.10
        services = cs.services()
        self.assertIn("gateway", services)
        gateway = cs.service_networks(services["gateway"])
        self.assertTrue([n for n in gateway if not _internal(n)], "gateway has no route out (edge)")
        self.assertIn("backend", gateway)
        self.assertTrue(_internal("backend"), "backend must be internal: true")
        for name, svc in services.items():
            if name == "gateway" or not cs.is_stack_service(svc):
                continue
            with self.subTest(service=name):
                networks = cs.service_networks(svc)
                self.assertTrue(networks, f"{name} joins no network")
                outside = [n for n in networks if not _internal(n)]
                self.assertEqual(outside, [], f"{name} is on a network with a route out")

    def test_gates_it_internal_only_and_no_socket(self):  # PS-2.7 Mechanism, F-A
        gates_it = _find_service("gates-it")
        self.assertIsNotNone(gates_it, "gates-it is not defined in any compose file")
        self.assertNotIn("network_mode", gates_it)
        networks = cs.service_networks(gates_it)
        self.assertIn("backend", networks)
        for network in networks:
            with self.subTest(network=network):
                self.assertTrue(_internal(network), f"gates-it joins non-internal {network}")
        for kind, source in cs.volume_sources(gates_it):
            with self.subTest(volume=source):
                self.assertFalse(any(m in source for m in cs.SOCKET_MARKERS),
                                 "gates-it mounts the Docker socket")
        gates = _find_service("gates")
        self.assertEqual((gates or {}).get("network_mode"), "none", "gates keeps network_mode: none")
        # F-A: the gateway forward is reachable without a non-internal network.
        services = cs.services()
        for peer in ("gateway", "api", "worker"):
            with self.subTest(shares_internal_with=peer):
                shared = set(networks) & set(cs.service_networks(services.get(peer, {})))
                self.assertTrue([n for n in shared if _internal(n)],
                                f"gates-it shares no internal network with {peer}")

    def test_no_docker_socket_mounted(self):  # PS-2.11
        names = {n for _, n, _ in cs.all_services()}
        for name in OFFLINE_SERVICES:  # §2.6 item 7: the check covers dind and its client
            with self.subTest(covers=name):
                self.assertIn(name, names, f"{name} is not defined in any compose file (§2.5)")
        for file, name, svc in cs.all_services():
            for _, source in cs.volume_sources(svc):
                with self.subTest(file=file, service=name, source=source):
                    self.assertFalse(any(m in source for m in cs.SOCKET_MARKERS),
                                     "Docker socket mounted")

    def test_stack_services_have_no_bind_mounts(self):  # PS-2.12
        declared = set()
        for path in cs.compose_files():
            declared |= set((cs.load(path).get("volumes") or {}))
        for file, name, svc in cs.all_services():
            if not cs.is_stack_service(cs.services().get(name, svc)):
                continue
            for kind, source in cs.volume_sources(svc):
                with self.subTest(file=file, service=name, source=source):
                    self.assertEqual(kind, "volume", "stack services use named volumes only")
                    if source:
                        self.assertIn(source, declared, "volume is not a declared named volume")


class PhoenixPortTest(unittest.TestCase):
    """PS-2.2 *One Phoenix* (PS-Q2)."""

    def test_harness_default_collector_matches_env_example(self):
        from harness_telemetry.tracing import DEFAULT_COLLECTOR

        port = read_env_example().get("KE_PHOENIX_PORT")
        self.assertEqual(DEFAULT_COLLECTOR, f"http://localhost:{port}")

    def test_docs_name_current_phoenix_port(self):
        port = read_env_example().get("KE_PHOENIX_PORT")
        stale = re.compile(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(?:6006|4317)\b|\b(?:6006|4317):(?:6006|4317)\b")
        for rel in ("README.md", "AGENTS.md", "harness_telemetry/tracing.py", "docker-compose.yml"):
            with self.subTest(file=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIsNone(stale.search(text), f"{rel} names a stale Phoenix host port")
        for rel in ("README.md", "AGENTS.md"):
            with self.subTest(states_default=rel):
                self.assertIn(f"localhost:{port}", (ROOT / rel).read_text(encoding="utf-8"))

    def test_compose_phoenix_listen_port_matches_config(self):
        # Replaces platform-config's test_compose_phoenix_defaults_match_config
        # and test_phoenix_published_on_loopback_only (tests/test_engine_deploy_files.py):
        # by the ADR-KE-011 ports amendment and §2.4, phoenix publishes nothing
        # and the gateway publishes its port on KE_BIND_ADDRESS. What remains
        # is phoenix's own listen port, which the engine's collector endpoint
        # (defaults.yaml) and the gateway's proxy both use.
        import yaml
        from urllib.parse import urlsplit

        phoenix = cs.services().get("phoenix", {})
        self.assertEqual(cs.port_entries(phoenix), [], "phoenix must not publish (only gateway does)")
        listen = cs.environment(phoenix).get("PHOENIX_PORT", "")
        match = re.fullmatch(r"\$\{PHOENIX_PORT:-(\d+)\}", listen)
        self.assertIsNotNone(match, f"phoenix PHOENIX_PORT is {listen!r}")
        defaults = yaml.safe_load((ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8"))
        endpoint = urlsplit(defaults["telemetry"]["collector_endpoint"])
        self.assertEqual(match.group(1), str(endpoint.port))


class ImageContentsTest(unittest.TestCase):
    def test_env_example_not_in_app_image(self):  # PS-1.9 *Not shipped*
        app = ROOT / "docker" / "app.Dockerfile"
        self.assertTrue(app.is_file(), "docker/app.Dockerfile is missing (§2.4 Images)")
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        patterns = [p.strip() for p in ignore if p.strip() and not p.startswith("#")]
        self.assertNotIn("!.env.example", patterns, ".dockerignore re-includes .env.example")
        excluded = any(p in (".env*", ".env.example", "**/.env*") for p in patterns)
        for dockerfile in sorted((ROOT / "docker").rglob("*Dockerfile")):
            text = dockerfile.read_text(encoding="utf-8")
            with self.subTest(dockerfile=dockerfile.name):
                for line in re.findall(r"^(?:COPY|ADD)\s.*$", text, re.M | re.I):
                    self.assertNotIn(".env", line, f"{dockerfile.name} copies an env file")
                    if re.search(r"\s\.(?:/)?\s", f"{line} "):
                        self.assertTrue(excluded, "COPY . without .dockerignore excluding .env*")


class Rework1ComposeTest(unittest.TestCase):
    """Rework round 1 (docs/handoffs/platform-stack.md; review.md, security.md)."""

    def test_no_ke_env_default_anywhere_in_compose(self):  # review N2, mutant B5
        # Unset KE_ENV must reach every service unset (not dev): fail closed.
        for path in cs.compose_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(text, r"\$\{KE_ENV:?[-=?+]",
                                    "compose gives KE_ENV a default or modifier")
        services = cs.services()
        for name in ("gateway", "api", "worker"):
            with self.subTest(service=name):
                self.assertEqual(cs.environment(services.get(name, {})).get("KE_ENV"), "${KE_ENV}")

    def test_backend_bridge_gateway_is_isolated(self):  # security M-2
        # Docker >= 28: the bridge gets no host address, so backend containers
        # cannot reach host services bound to 0.0.0.0 through it.
        backend = _network_defs().get("backend", {})
        self.assertIs(backend.get("internal"), True)
        opts = backend.get("driver_opts") or {}
        self.assertEqual(str(opts.get("com.docker.network.bridge.gateway_mode_ipv4")), "isolated",
                         "backend lacks driver_opts com.docker.network.bridge.gateway_mode_ipv4: isolated")

    def test_quickstart_requires_docker_engine_28(self):  # security M-2, orchestrator scope
        text = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?i)Docker(?: Engine)?\s*(?:28|>=\s*28|≥\s*28)",
                         "the quickstart must require Docker Engine 28 or later")

    def test_worker_command_runs_engine_startup(self):  # review B2, PS-2.14 (1)
        worker = cs.services().get("worker", {})
        command = worker.get("command")
        text = " ".join(command) if isinstance(command, list) else str(command or "")
        self.assertRegex(text, r"(?:^|\s)-m\s+engine\.worker(?:\s|$)",
                         f"worker must run `python -m engine.worker` (architecture §2.4), got {text!r}")
        self.assertNotIn("signal.pause", text, "the idle placeholder skips startup()")

    def test_gateway_gets_the_egress_allowlist(self):  # security M-3
        gateway = cs.environment(cs.services().get("gateway", {}))
        self.assertEqual(gateway.get("KE_MODEL_UPSTREAM"), "${KE_MODEL_UPSTREAM:-}")
        self.assertEqual(gateway.get("KE_EGRESS_ALLOWLIST"), "${KE_EGRESS_ALLOWLIST:-}",
                         "the gateway check needs KE_EGRESS_ALLOWLIST to enforce it")


class Rework2ComposeTest(unittest.TestCase):
    """Rework round 2, ruling R1-B1 option (ii) (docs/handoffs/platform-stack.md;
    review-rework1.md R1-B1, windows-proof-rework1.txt F1): no network has a
    fixed address pool. Docker refuses a second network whose pool overlaps
    ("Pool overlaps with other one on this address space"), so a fixed subnet
    stops `verify.sh full` from running while the live stack, or any other
    project of this compose file, is up (§2.2 isolation)."""

    POOL_KEYS = ("subnet", "ip_range", "gateway", "aux_addresses")
    CIDR = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b")

    def test_backend_has_no_ipam_subnet_or_ip_range(self):
        backend = _network_defs().get("backend", {})
        self.assertTrue(backend, "precondition: compose defines the backend network")
        ipam = backend.get("ipam") or {}
        for entry in ipam.get("config") or []:
            for key in self.POOL_KEYS:
                with self.subTest(key=key):
                    self.assertNotIn(key, entry or {}, f"backend ipam fixes {key} (R1-B1)")

    def test_no_fixed_address_pool_anywhere(self):
        # Statically: parallel projects of one compose file can only collide
        # on a pool if some network fixes one. None may, in any compose file.
        for path in cs.compose_files():
            data = cs.load(path)
            for name, definition in (data.get("networks") or {}).items():
                ipam = (definition or {}).get("ipam") or {}
                for entry in ipam.get("config") or []:
                    for key in self.POOL_KEYS:
                        with self.subTest(file=path.name, network=name, key=key):
                            self.assertNotIn(key, entry or {},
                                             f"{path.name}: network {name} fixes {key}")
            with self.subTest(file=path.name, check="CIDR literal"):
                self.assertIsNone(self.CIDR.search(path.read_text(encoding="utf-8")),
                                  f"{path.name} carries an address-pool literal")

    def test_scripts_create_no_fixed_subnet(self):
        for script in sorted((ROOT / "scripts").glob("*")):
            if script.suffix not in {".sh", ".ps1"}:
                continue
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"--subnet|--ip-range",
                                    f"{script.name} creates a network with a fixed pool")


if __name__ == "__main__":
    unittest.main()
