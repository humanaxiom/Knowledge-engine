"""platform-offline, the offline check (PS-3.2 `ci/deployable-offline`, PS-3.9
N6, the `offline-client` half of PS-3.10): statically, against real
`docker compose config` (no daemon) and against the fake docker.

Criteria: docs/requirements.md PS-3.2 additions (*Inner daemon*, *Clean daemon
precondition*, *No privileged daemon is a blocker*, *Nothing left behind*,
*No pull happened*, *Free disk*, *Disk logging*), PS-3.9 *N6*, PS-3.10 *Client
only in the gate services* (the `offline-client` half). Design:
docs/architecture.md §2.5 "`ci/deployable-offline` (PS-3.2)" (compose
additions, host half, client half, `df` log), ADR-KE-009 *Clean daemon*, §2.6
items 7, 9 and 12; rulings S3, R2, R6 (docs/handoffs/platform-offline.md).
Test names: the requirements' names are canonical; the rest follow §2.6.

Interface pinned by these tests (tester, RED offline check, 2026-10-19):
- `bash scripts/offline_check.sh` from the repository root is the host half.
- The client half is the same script with KE_OFFLINE_CLIENT=1. It reads the
  bundle from `${KE_OFFLINE_BUNDLE_DIR:-/bundle}` and installs under
  `${KE_OFFLINE_INSTALL_ROOT:-/install}`. The two overrides exist only so the
  client half can run outside the `offline-client` container in a test.
- Rework round 1 (security L-OCb): the client half exits non-zero, naming the
  path, before any docker call, if `${DOCKER_CERT_PATH}/ca` or
  `${DOCKER_CERT_PATH}/server` exists (any kind, a dangling link included).
  DOCKER_CERT_PATH is /certs/client in offline-client; no new seam.
- `bash scripts/net_isolated.sh <network>` exits 0 only for a network that is
  `Internal` and has `gateway_mode_ipv4=isolated`, from one inspect.
- Below the disk floor the message says "need 7 GiB free" and "found <N>
  GiB" (rounded down), as bundle.sh does (review N8). The floor was 10 GiB
  until orchestrator ruling 1 after CI run 39359710258 (handoff, 2026-10-20;
  docs/evidence/platform-offline/ci-39359710258.log).

Full tier: what only a real `dind` run proves (the containerd store of the
pinned Engine, the TLS alias, `volume.subpath` honoured, no pull, the stack
starting inside `dind`) is `ci/deployable-offline`, which the developer's
`scripts/verify.sh full` runs. These fast tests do not stand in for it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from tests import compose_support as cs
from tests import fake_docker
from tests.engine_support import ROOT, read_env_example

GIB_KB = 1024 * 1024
OFFLINE_CHECK = ROOT / "scripts" / "offline_check.sh"
NET_ISOLATED = ROOT / "scripts" / "net_isolated.sh"
ISOLATED_KEY = "com.docker.network.bridge.gateway_mode_ipv4"
# platform-sbom U4b (PSC-26, N16 *First failing tests*): ke-neo4j joins the
# first-party images, built from docker/neo4j.Dockerfile (tester, U4b RED).
FIRST_PARTY = {"app.Dockerfile": "ke-app", "gateway.Dockerfile": "ke-gateway",
               "gates.Dockerfile": "ke-gates", "neo4j.Dockerfile": "ke-neo4j"}
TAG_VAR = "${KE_IMAGE_TAG:-local}"
WT_TAG = "wt-0123456789ab"
DOCKER_MISSING = ("docker (CLI + compose plugin) is not on PATH: the gates image carries both "
                  "(PS-3.10), and `docker compose config` needs no daemon")
SCRIPT_MISSING = "scripts/offline_check.sh is missing (architecture §2.5 ci/deployable-offline)"
SKIP_RX = re.compile(r"(?i)\bskip(?:ped|ping)?\b")


def _clean_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir()}
    env.update(extra)
    return env


def _executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


# --------------------------------------------------------------------------
# Compose helpers: the offline services may live in any compose file.
# --------------------------------------------------------------------------

def _service(name: str) -> tuple[str, dict[str, Any]] | None:
    for path in cs.compose_files():
        svc = cs.services(path).get(name)
        if svc and ("image" in svc or "build" in svc):
            return path.name, svc
    return None


def _network_defs() -> dict[str, dict[str, Any]]:
    defs: dict[str, dict[str, Any]] = {}
    for path in cs.compose_files():
        for name, definition in (cs.load(path).get("networks") or {}).items():
            defs.setdefault(name, {}).update(definition or {})
    return defs


def _mounts(svc: dict[str, Any]) -> list[dict[str, Any]]:
    """Every volume entry as {type, source, target, read_only, subpath}."""
    out: list[dict[str, Any]] = []
    for entry in svc.get("volumes") or []:
        if isinstance(entry, dict):
            out.append({"type": str(entry.get("type", "volume")),
                        "source": str(entry.get("source", "")),
                        "target": str(entry.get("target", "")),
                        "read_only": entry.get("read_only") is True,
                        "subpath": str(((entry.get("volume") or {}).get("subpath")) or "")})
            continue
        parts = str(entry).split(":")
        if re.match(r"^[A-Za-z]$", parts[0]) and len(parts) > 1:  # a Windows drive letter
            parts = [parts[0] + ":" + parts[1], *parts[2:]]
        if len(parts) == 1:
            out.append({"type": "volume", "source": "", "target": parts[0],
                        "read_only": False, "subpath": ""})
            continue
        source, target = parts[0], parts[1]
        opts = parts[2].split(",") if len(parts) > 2 else []
        bind = bool(re.match(r"^(?:[./~$\\]|[A-Za-z]:[\\/])", source)) or "/" in source
        out.append({"type": "bind" if bind else "volume", "source": source, "target": target,
                    "read_only": "ro" in opts, "subpath": ""})
    return out


def _tmpfs(svc: dict[str, Any]) -> list[str]:
    raw = svc.get("tmpfs") or []
    return [raw] if isinstance(raw, str) else [str(t) for t in raw]


def _network_entry(svc: dict[str, Any], network: str) -> dict[str, Any]:
    networks = svc.get("networks")
    if isinstance(networks, dict):
        return networks.get(network) or {}
    return {}


class OfflineComposeTest(unittest.TestCase):
    """§2.6 item 7, PS-3.2 *Inner daemon*, rulings S3 (alias `docker`, only the
    certs `client` subpath read-only, never `ca/`, inner networks internal)."""

    def _both(self) -> tuple[dict[str, Any], dict[str, Any]]:
        dind = _service("dind")
        client = _service("offline-client")
        self.assertIsNotNone(dind, "no compose file defines the `dind` service (§2.5 compose additions)")
        self.assertIsNotNone(client, "no compose file defines the `offline-client` service (§2.5)")
        assert dind is not None and client is not None
        return dind[1], client[1]

    def test_compose_offline_services(self):
        dind, client = self._both()
        with self.subTest(service="dind"):
            self.assertIs(dind.get("privileged"), True, "dind must be privileged (§2.5)")
            self.assertIn("offline", dind.get("profiles") or [], "dind is profile `offline` only")
            self.assertEqual(cs.service_networks(dind), ["offline"], "dind joins `offline` only")
            self.assertEqual(cs.port_entries(dind), [], "dind publishes nothing")
            self.assertIn(dind.get("restart"), (None, "no"), "dind has no restart policy")
            self.assertRegex(str(dind.get("image", "")), r"^docker:[^@\s]*dind[^@\s]*@sha256:[0-9a-f]{64}$",
                             "dind is the official docker:<ver>-dind image, digest pinned")
            self.assertNotIn("build", dind)
            self.assertEqual(cs.environment(dind).get("DOCKER_TLS_CERTDIR"), "/certs")
            certs = [m for m in _mounts(dind) if m["type"] == "volume" and m["source"] == "offline-certs"]
            self.assertEqual([m["target"] for m in certs], ["/certs"],
                             "dind keeps its certs on the named volume offline-certs:/certs")
            self.assertFalse([m for m in _mounts(dind) if m["target"].rstrip("/") == "/var/lib/docker"
                              and m["source"]],
                             "/var/lib/docker stays dind's anonymous volume, empty on every run")
            self.assertFalse([m for m in _mounts(dind) if m["type"] == "bind"], "dind has no bind mount")
            health = json.dumps(dind.get("healthcheck") or {})
            self.assertRegex(health, r"docker\b[^\"]*\binfo\b", "dind's healthcheck is `docker info`")
        with self.subTest(network="offline"):
            offline = _network_defs().get("offline")
            self.assertIsNotNone(offline, "the `offline` network is not defined")
            assert offline is not None
            self.assertIs(offline.get("internal"), True, "offline must be internal: true")
            self.assertEqual(str((offline.get("driver_opts") or {}).get(ISOLATED_KEY)), "isolated")
        with self.subTest(service="offline-client"):
            self.assertEqual(client.get("image"), f"ke-gates:{TAG_VAR}",
                             "offline-client runs the gates image at the per-run tag (§2.5, N6)")
            self.assertNotIn("build", client, "offline-client is not the x-gates anchor")
            self.assertIn(str(client.get("user", "")), ("10001", "10001:10001"),
                          "offline-client runs as uid 10001 (S3)")
            self.assertIn("offline", client.get("profiles") or [])
            self.assertEqual(cs.service_networks(client), ["offline"], "offline-client joins `offline` only")
            self.assertNotIn(client.get("privileged"), (True,), "only dind is privileged")
            self.assertEqual(cs.port_entries(client), [])
            self.assertIn(client.get("restart"), (None, "no"), "offline-client has no restart policy")
            env = cs.environment(client)
            self.assertEqual(env.get("DOCKER_HOST"), "tcp://docker:2376")
            self.assertEqual(env.get("DOCKER_TLS_VERIFY"), "1")
            self.assertEqual(env.get("DOCKER_CERT_PATH"), "/certs/client")
            self.assertIn("KE_IN_GATES", env, "offline-client must empty KE_IN_GATES explicitly")
            self.assertEqual(env.get("KE_IN_GATES"), "", "KE_IN_GATES must be empty in offline-client")
            self.assertEqual(env.get("KE_OFFLINE_CLIENT"), "1")
            self.assertNotIn("COMPOSE_FILE", env, "offline-client sets no COMPOSE_FILE")
            mounts = _mounts(client)
            binds = [m for m in mounts if m["type"] == "bind"]
            for m in binds:
                with self.subTest(bind=m["source"]):
                    self.assertTrue(m["read_only"], f"bind {m['source']} -> {m['target']} is writable")
                    self.assertIn(m["target"], ("/bundle", "/opt/ke/offline_check.sh"),
                                  "no checkout mount: only the bundle and offline_check.sh are bound")
                    self.assertNotIn(m["source"].rstrip("/"), (".", "", "..", "${PWD}"),
                                     "the checkout is mounted: the run would test the tree, not the bundle")
            bundle = [m for m in binds if m["target"] == "/bundle"]
            self.assertEqual(len(bundle), 1, "the bundle is mounted read-only at /bundle")
            self.assertIn("KE_OFFLINE_BUNDLE", bundle[0]["source"])
            script = [m for m in binds if m["target"] == "/opt/ke/offline_check.sh"]
            self.assertEqual([m["source"] for m in script], ["./scripts/offline_check.sh"])
            tmpfs = _tmpfs(client)
            self.assertTrue([t for t in tmpfs if t.split(":", 1)[0] == "/install"], "tmpfs on /install")
            tmp = [t for t in tmpfs if t.split(":", 1)[0] == "/tmp"]
            self.assertTrue(tmp and "exec" in tmp[0].split(":", 1)[-1].split(",")
                            and "noexec" not in tmp[0], "/tmp is an exec tmpfs (as L-5)")
        for name, svc in (("dind", dind), ("offline-client", client)):
            for _, source in cs.volume_sources(svc):
                with self.subTest(service=name, socket=source):
                    self.assertFalse(any(m in source for m in cs.SOCKET_MARKERS),
                                     f"{name} mounts the host Docker socket (ADR-KE-009)")

    def test_offline_dind_has_network_alias_docker(self):
        dind, client = self._both()
        aliases = _network_entry(dind, "offline").get("aliases") or []
        self.assertIn("docker", aliases,
                      "dind needs the alias `docker` on `offline`: its TLS cert names only the "
                      "container id, docker and localhost (spike S3)")
        host = cs.environment(client).get("DOCKER_HOST", "")
        self.assertEqual(host, "tcp://docker:2376", "the client reaches dind by the alias the cert covers")
        self.assertNotIn("DOCKER_TLS_SAN", cs.environment(dind), "the alias was chosen over DOCKER_TLS_SAN")

    def test_offline_client_mounts_only_client_certs_read_only(self):
        _, client = self._both()
        certs = [m for m in _mounts(client) if m["source"] == "offline-certs"]
        self.assertEqual(len(certs), 1, "offline-client mounts the certs volume exactly once")
        mount = certs[0]
        self.assertEqual(mount["type"], "volume")
        self.assertEqual(mount["target"], "/certs/client")
        self.assertEqual(mount["subpath"], "client", "only the `client` subpath (volume.subpath)")
        self.assertTrue(mount["read_only"], "the client certs are mounted read-only")
        for m in _mounts(client):
            with self.subTest(target=m["target"]):
                self.assertFalse(m["target"] in ("/certs", "/certs/") or "/ca" in m["target"]
                                 or m["subpath"].strip("/").split("/")[:1] == ["ca"],
                                 "a mount reaches the CA directory (its private key): never mount ca/")
        for file, name, svc in cs.all_services():
            if name == "dind":
                continue
            for m in _mounts(svc):
                if m["source"] != "offline-certs":
                    continue
                with self.subTest(file=file, service=name):
                    self.assertEqual(name, "offline-client",
                                     f"{name} mounts offline-certs; only dind and offline-client may")

    def test_offline_client_never_pulls(self):
        # Security I-OC5 (rework round 1): a missing ke-gates:<tag> must not
        # send Compose to docker.io; the client image is always the local build.
        _, client = self._both()
        self.assertEqual(client.get("pull_policy"), "never",
                         "offline-client needs `pull_policy: never` (I-OC5)")

    def test_offline_inner_networks_are_internal(self):
        defs = _network_defs()
        self.assertIn("offline", defs, "the `offline` network is not defined (§2.5)")
        for path in cs.compose_files():
            for name, definition in (cs.load(path).get("networks") or {}).items():
                opts = (definition or {}).get("driver_opts") or {}
                if str(opts.get(ISOLATED_KEY)) != "isolated":
                    continue
                with self.subTest(file=path.name, network=name):
                    self.assertIs((definition or {}).get("internal"), True,
                                  "gateway_mode_ipv4=isolated needs internal: true (spike S3)")
        offline = defs.get("offline") or {}
        self.assertIs(offline.get("internal"), True)
        self.assertEqual(str((offline.get("driver_opts") or {}).get(ISOLATED_KEY)), "isolated")
        for script in sorted((ROOT / "scripts").glob("*.sh")):
            body = "\n".join(l for l in script.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith("#"))
            for call in re.findall(r"\bnetwork\s+create\b[^\n]*", body):
                with self.subTest(script=script.name, call=call):
                    self.assertIn("--internal", call, "an inner network the check creates is --internal")

    def test_stack_compose_has_no_required_variable(self):
        # Architecture §2.5 writes the bundle mount as `${KE_OFFLINE_BUNDLE:?}`.
        # Compose interpolates every service, profile or not, so a required
        # variable in docker-compose.yml makes `compose config`, `launch.sh`,
        # `smoke.sh` and `teardown.sh` fail whenever it is unset (probe with
        # Compose 5.1.4: docs/evidence/platform-offline/red-oc-compose-required-var.txt).
        # PS-2.2 *Resolves without .env* needs the stack file to resolve with
        # no env at all. A required variable may live only in a file that
        # only offline_check.sh loads.
        text = cs.MAIN_COMPOSE.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?\?", text),
                          "docker-compose.yml uses a required variable (${VAR:?}); every stack "
                          "command then fails when it is unset")


# --------------------------------------------------------------------------
# PS-3.9 N6 and §2.6 item 9: first-party images carry ${KE_IMAGE_TAG:-local}
# --------------------------------------------------------------------------

def _docker_config_env(tmp: Path, **extra: str) -> dict[str, str]:
    env = _clean_env(DOCKER_CONFIG=str(tmp / "docker-config"), **extra)
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "COMPOSE_FILE", "COMPOSE_PROFILES",
                "COMPOSE_PROJECT_NAME"):
        env.pop(key, None)
    return env


class ImageTagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _config(self, files: list[str], profile: bool, **env: str) -> dict[str, Any]:
        if shutil.which("docker") is None:
            self.fail(DOCKER_MISSING)
        argv = ["docker", "compose"]
        for f in files:
            argv += ["-f", f]
        argv += ["--env-file", ".env.example"]
        if profile:
            argv += ["--profile", "*"]
        argv += ["config", "--format", "json"]
        result = subprocess.run(argv, cwd=ROOT, env=_docker_config_env(self.tmp, **env),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, f"{' '.join(argv)} failed:\n{result.stderr}")
        return json.loads(result.stdout)

    def test_first_party_images_use_image_tag(self):  # §2.6 item 9
        self.assertEqual(read_env_example().get("KE_IMAGE_TAG"), "local",
                         ".env.example must set KE_IMAGE_TAG=local")
        seen: set[str] = set()
        for file, name, svc in cs.all_services():
            build = svc.get("build")
            if not build:
                continue
            dockerfile = Path(str(build.get("dockerfile", "Dockerfile") if isinstance(build, dict)
                                  else "Dockerfile")).name
            repo = FIRST_PARTY.get(dockerfile)
            with self.subTest(file=file, service=name):
                self.assertIsNotNone(repo, f"{name} builds an unexpected Dockerfile {dockerfile}")
                self.assertEqual(svc.get("image"), f"{repo}:{TAG_VAR}",
                                 f"{name} must be image {repo}:{TAG_VAR} (N6)")
                seen.add(str(repo))
        self.assertEqual(seen, set(FIRST_PARTY.values()), "every first-party image is built in compose")

    def test_verify_does_not_retag_live_images(self):  # PS-3.9 N6
        # Compose config with and without the verify overlay. The live stack
        # resolves with .env.example and no KE_IMAGE_TAG in the environment;
        # verify sets a per-worktree tag (the B6 half is
        # VerifyHostHalfTest.test_verify_full_uses_per_worktree_image_tag).
        bundle = str(self.tmp / "bundle")
        live = self._config(["docker-compose.yml"], profile=False, KE_OFFLINE_BUNDLE=bundle)
        live_images = {name: svc.get("image") for name, svc in (live.get("services") or {}).items()}
        # platform-sbom U4b (PSC-26 *Tags*): neo4j is ke-neo4j:local live and
        # ke-neo4j:wt-<12 hex> under verify (tester, U4b RED).
        for name in ("gateway", "api", "worker", "neo4j"):
            with self.subTest(live=name):
                self.assertRegex(str(live_images.get(name)), r"^ke-(?:app|gateway|neo4j):local$",
                                 "the live stack's first-party images resolve to the :local tag")
        verify = self._config(["docker-compose.yml", "docker-compose.verify.yml"], profile=True,
                              KE_IMAGE_TAG=WT_TAG, KE_OFFLINE_BUNDLE=bundle)
        built = {name: svc.get("image") for name, svc in (verify.get("services") or {}).items()
                 if svc.get("build") or str(svc.get("image", "")).startswith("ke-")}
        self.assertTrue({"gateway", "api", "worker", "neo4j", "gates", "gates-it"} <= set(built), built)
        for name, image in sorted(built.items()):
            with self.subTest(verify=name, image=image):
                self.assertEqual(str(image).rsplit(":", 1)[-1], WT_TAG,
                                 "a verify-built image carries the per-run tag")
                self.assertNotIn(image, set(live_images.values()),
                                 "verify would move a tag the live stack resolves to (N6)")


# --------------------------------------------------------------------------
# §2.5 `scripts/net_isolated.sh <network>` (shared by smoke.sh and the check)
# --------------------------------------------------------------------------

class NetIsolatedScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.assertTrue(NET_ISOLATED.is_file(),
                        "scripts/net_isolated.sh is missing (architecture §2.5 ci/offline)")
        (self.tmp / "scripts").mkdir()
        shutil.copy(NET_ISOLATED, self.tmp / "scripts" / "net_isolated.sh")
        fake_docker.install(self.tmp / "fakebin")
        self.json = self.tmp / "docker.jsonl"

    def _run(self, network: str = "ke-verify-test_backend", **extra: str):
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), COMPOSE_PROJECT_NAME="ke-verify-test", **extra)
        result = subprocess.run(["bash", "scripts/net_isolated.sh", network], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=60)
        return result, fake_docker.records(self.json)

    def test_net_isolated_passes_an_internal_isolated_network(self):
        result, records = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        inspects = [r["argv"] for r in records if r["argv"][:2] == ["network", "inspect"]]
        self.assertEqual(len(inspects), 1, f"one inspect, parsed once (§2.5, R2-N8): {inspects}")
        self.assertIn("ke-verify-test_backend", inspects[0])
        self.assertTrue(any(re.fullmatch(r"\{\{\s*json\s+\.\s*\}\}", a) for a in inspects[0])
                        or "--format={{json .}}" in inspects[0], inspects[0])

    def test_net_isolated_refuses_not_internal_or_not_isolated(self):
        cases = {
            "not internal": {"FAKE_DOCKER_BACKEND_INTERNAL": "false"},
            "nat": {"FAKE_DOCKER_BACKEND_OPTIONS": json.dumps({ISOLATED_KEY: "nat"})},
            "option absent": {"FAKE_DOCKER_BACKEND_OPTIONS": "{}"},
            "isolated on ipv6 only": {"FAKE_DOCKER_BACKEND_OPTIONS": json.dumps(
                {"com.docker.network.bridge.gateway_mode_ipv6": "isolated"})},
            "inspect fails": {"FAKE_DOCKER_FAIL": "network inspect"},
        }
        for case, extra in cases.items():
            with self.subTest(case=case):
                result, _ = self._run(**extra)
                self.assertNotEqual(result.returncode, 0, f"{case} accepted:\n{result.stdout}{result.stderr}")
                self.assertIn("ke-verify-test_backend", result.stdout + result.stderr,
                              "the refusal names the network")
        with self.subTest(case="unknown network"):
            result, _ = self._run("ke-verify-test_nonesuch")
            self.assertNotEqual(result.returncode, 0)


# --------------------------------------------------------------------------
# §2.6 item 12: OfflineCheckScriptTest (fake docker, fake df)
# --------------------------------------------------------------------------

_STUB = r'''#!/usr/bin/env bash
# Stand-in for @NAME@: one JSON record in the fake docker's call log.
@PRE@
# platform-sbom U9d rework 1 (O-23, A9): the stub FAKE_STUB_WAIT_NAME names
# waits, before its record, up to 10 s for the fixed string FAKE_STUB_WAIT_FOR
# in the call log, then FAKE_STUB_WAIT_THEN seconds. Inert unless both are set.
if [ -n "${FAKE_STUB_WAIT_FOR:-}" ] && [ "${FAKE_STUB_WAIT_NAME:-}" = "@NAME@" ]; then
  _w=0
  while [ "$_w" -lt 100 ] && ! grep -qF -- "$FAKE_STUB_WAIT_FOR" "$FAKE_DOCKER_JSON" 2> /dev/null; do
    sleep 0.1
    _w=$((_w + 1))
  done
  sleep "${FAKE_STUB_WAIT_THEN:-0}"
fi
args=""
for a in "$@"; do args="$args, \"$a\""; done
printf '{"argv": ["STUB", "@NAME@"%s], "env": {"COMPOSE_PROJECT_NAME": "%s", "KE_SMOKE_OWNS_PROJECT": "%s", "PARENT_MODE": "%s"}, "cwd": "%s", "project_dir": "", "dotenv_present": false}\n' \
  "$args" "${COMPOSE_PROJECT_NAME-}" "${KE_SMOKE_OWNS_PROJECT-<unset>}" "${parent_mode-}" "$PWD" >> "$FAKE_DOCKER_JSON"
@POST@
case "|${FAKE_STUB_FAIL:-}|" in *"|@NAME@|"*) echo "stub @NAME@: failing" >&2; exit 7 ;; esac
exit 0
'''

_BUNDLE_PRE = r'''out=""; prev=""
for a in "$@"; do [ "$prev" = "--out" ] && out="$a"; prev="$a"; done
if [ -n "$out" ]; then mkdir -p "$out" && echo '{}' > "$out/bundle.json"; fi
@SBOM_STUB@'''

# platform-sbom U4 (PSC-14/22 image-side drift check, design-notes N7, N10 B3):
# the stub bundle also writes a bundle.json naming the stack images and the
# ke-app SBOM the real bundle.sh writes (app/sboms/ke-app.spdx.json), from the
# files the harness names (FAKE_STUB_BUNDLE_JSON, FAKE_STUB_KE_APP_SBOM), so
# the host half's drift step has a real document to check.
_SBOM_STUB = r'''if [ -n "$out" ] && [ -n "${FAKE_STUB_BUNDLE_JSON:-}" ]; then cp "$FAKE_STUB_BUNDLE_JSON" "$out/bundle.json"; fi
if [ -n "$out" ] && [ -n "${FAKE_STUB_KE_APP_SBOM:-}" ]; then
  mkdir -p "$out/app/sboms" && cp "$FAKE_STUB_KE_APP_SBOM" "$out/app/sboms/ke-app.spdx.json"
fi
if [ -n "$out" ] && [ -n "${FAKE_STUB_KE_NEO4J_SBOM:-}" ]; then
  mkdir -p "$out/app/sboms" && cp "$FAKE_STUB_KE_NEO4J_SBOM" "$out/app/sboms/ke-neo4j.spdx.json"
fi
if [ -n "$out" ] && [ -n "${FAKE_STUB_KE_NEO4J_TAR:-}" ]; then
  mkdir -p "$out/images" && cp "$FAKE_STUB_KE_NEO4J_TAR" "$out/images/ke-neo4j.tar"
fi'''
_BUNDLE_PRE = _BUNDLE_PRE.replace("@SBOM_STUB@", _SBOM_STUB)
# Files the host half's U4 drift step reads from the checkout, and (U4b,
# PSC-26) the ke-neo4j step: docker/neo4j.Dockerfile's FROM is the official
# reference it pulls and compares with. The stub bundle also writes the
# ke-neo4j SBOM and saved tar (FAKE_STUB_KE_NEO4J_SBOM, FAKE_STUB_KE_NEO4J_TAR).
_U4_HOST_FILES = ("scripts/sbom_check.py", cs.SBOM_COMPOSE_NAME, "docker/app.Dockerfile", "licenses",
                  "tests/test_notice_ke_app.py", "uv.lock", "pyproject.toml", "docker/neo4j.Dockerfile")

_INSTALL_PRE = r'''parent_mode="$(stat -c %a "$(dirname "$1")" 2>/dev/null || echo missing)"'''

# platform-sbom U8b (PSC-23 U8-8; design-notes N4 amendment U8 item 8; tester,
# U8b RED): the stand-in for scripts/bundle_fetch.sh writes its --out dir (a
# completion record in it), so the host half's EXIT trap has something to
# remove; when FAKE_STUB_FAIL names it, it prints a fetch FAIL line first.
_FETCH_PRE = r'''out=""; prev=""
for a in "$@"; do [ "$prev" = "--out" ] && out="$a"; prev="$a"; done
if [ -n "$out" ]; then mkdir -p "$out" && echo '{}' > "$out/fetch.json"; fi
case "|${FAKE_STUB_FAIL:-}|" in *"|bundle_fetch.sh|"*) echo "bundle_fetch: FAIL (stage fetch: stub; no retry)" >&2 ;; esac'''

_INSTALL_POST = r'''mkdir -p "$1/scripts"
for s in launch smoke teardown; do
  sed "s/@NAME@/$s.sh/g" "$(dirname "$0")/stub.template" > "$1/scripts/$s.sh"
  chmod 755 "$1/scripts/$s.sh"
done'''


def _stub(name: str, pre: str = "", post: str = "") -> str:
    # NAME first: _INSTALL_POST holds a literal @NAME@ that install.sh's sed rewrites at run time.
    return _STUB.replace("@NAME@", name).replace("@PRE@", pre).replace("@POST@", post)


AS_APP = "ke-app:bundle-0123456789ab"
AS_GATEWAY = "ke-gateway:bundle-0123456789ab"
AS_NEO4J = "ke-neo4j:bundle-0123456789ab"
NEO4J_WT = "ke-neo4j:wt-0123456789ab"
PG_REF = "postgres:16-bookworm@sha256:" + "a" * 64
VK_REF = "valkey/valkey:8-alpine@sha256:" + "b" * 64
AS_PG = "ke-vendor/postgres:aaaaaaaaaaaa"
AS_VK = "ke-vendor/valkey:bbbbbbbbbbbb"
BUNDLE_ENTRIES = [
    {"file": "images/ke-app.tar", "ref": "ke-app:wt-0123456789ab", "as": AS_APP, "services": "api worker"},
    {"file": "images/ke-gateway.tar", "ref": "ke-gateway:wt-0123456789ab", "as": AS_GATEWAY,
     "services": "gateway"},
    {"file": "images/ke-neo4j.tar", "ref": NEO4J_WT, "as": AS_NEO4J, "services": "neo4j"},
    {"file": "images/postgres.tar", "ref": PG_REF, "as": AS_PG, "services": "postgres"},
    {"file": "images/valkey.tar", "ref": VK_REF, "as": AS_VK, "services": "valkey"},
]
AS_SET = [e["as"] for e in BUNDLE_ENTRIES]


def _bundle_json(entries: list[dict[str, str]]) -> str:
    head = ('{"format": 1, "git_sha": "%s", "dirty": false, "created": "2026-10-19T00:00:00Z", '
            '"arch": "amd64", "images": [' % ("0" * 40))
    return head + "\n" + ",\n".join(json.dumps(e) for e in entries) + "\n]}\n"


class _OfflineBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.json = self.tmp / "docker.jsonl"
        fake_docker.install(self.tmp / "fakebin")
        fake_docker.install_df(self.tmp / "fakebin")

    def _require_script(self) -> None:
        if not OFFLINE_CHECK.is_file():
            self.fail(SCRIPT_MISSING)

    def _base_env(self, **extra: str) -> dict[str, str]:
        return _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                          FAKE_DOCKER_JSON=str(self.json), FAKE_DF_JSON=str(self.json), **extra)

    @staticmethod
    def _out(result: subprocess.CompletedProcess) -> str:
        return result.stdout + result.stderr


class OfflineCheckScriptTest(_OfflineBase):
    """§2.6 item 12 and the PS-3.2 additions; host half and client half."""

    # ---- host half ---------------------------------------------------------

    def _host_setup(self) -> Path:
        self._require_script()
        repo = self.tmp / "repo"
        shutil.rmtree(repo, True)  # subTests call this again in one test
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(OFFLINE_CHECK, repo / "scripts" / "offline_check.sh")
        for rel in ("docker-compose.yml", ".env.example"):
            shutil.copy(ROOT / rel, repo / rel)
        for rel in _U4_HOST_FILES:
            src = ROOT / rel
            if src.is_dir():
                shutil.copytree(src, repo / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.is_file():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, repo / rel)
        _executable(repo / "scripts" / "bundle.sh", _stub("bundle.sh", pre=_BUNDLE_PRE))
        # platform-sbom U8b (U8-8): the sample fetch's script, as a stub (tests/test_bundle_fetch.py
        # tests the real one).
        _executable(repo / "scripts" / "bundle_fetch.sh", _stub("bundle_fetch.sh", pre=_FETCH_PRE))
        _executable(repo / "scripts" / "teardown.sh", _stub("teardown.sh"))
        _executable(repo / "scripts" / "net_isolated.sh", _stub("net_isolated.sh"))
        return repo

    def _sbom_env(self, repo: Path) -> dict[str, str]:
        """platform-sbom U4: what the host half's drift step needs from the
        fake daemon: the generator's compose file modelled (syft writes a
        base SBOM; tests/fake_docker.py), the stub bundle's bundle.json and
        ke-app SBOM (a document the drift check accepts), and the ke-app
        image's /app (uv.lock) mapped for a checker run in that image."""
        from tests import sbom_support as ss
        bundle_json = self.tmp / "stub-bundle.json"
        if not bundle_json.exists():
            bundle_json.write_text(_bundle_json(BUNDLE_ENTRIES), encoding="utf-8")
        sbom = self.tmp / "stub-ke-app.spdx.json"
        if not sbom.exists():
            ss.write_json(sbom, ss.ke_app_doc())
        sbom_file = ROOT / cs.SBOM_COMPOSE_NAME
        # platform-sbom U4b (PSC-26, N16): a clean ke-neo4j SBOM and saved tar,
        # and both images' configs (ke-neo4j's with the labels compose adds).
        from tests import neo4j_support as ns
        neo4j_sbom = self.tmp / "stub-ke-neo4j.spdx.json"
        if not neo4j_sbom.exists():
            ss.write_json(neo4j_sbom, ns.ke_neo4j_doc())
        neo4j_tar = self.tmp / "stub-ke-neo4j.tar"
        if not neo4j_tar.exists():
            ns.save_tar(neo4j_tar, [ns.CLEAN_LAYER])
        official = ns.dockerfile_base_ref(repo / "docker" / "neo4j.Dockerfile") or ns.OFFICIAL_REF
        configs = {official: ns.OFFICIAL_CONFIG, NEO4J_WT: dict(ns.OFFICIAL_CONFIG, Labels=ns.COMPOSE_LABELS)}
        # The host half has a route out: its `docker pull` of the ke-app base
        # (orchestrator U4 ruling 6) succeeds unless a test says otherwise.
        return {"FAKE_DOCKER_PULL_OK": "1",
                "FAKE_STUB_KE_NEO4J_SBOM": str(neo4j_sbom), "FAKE_STUB_KE_NEO4J_TAR": str(neo4j_tar),
                "FAKE_IMAGE_CONFIGS": json.dumps(configs),
                "FAKE_COMPOSE_FILE_IMAGES": json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": cs.sbom_generator_ref(sbom_file)}}),
                "FAKE_COMPOSE_FILE_REQUIRED": json.dumps({cs.SBOM_COMPOSE_NAME: cs.required_vars(sbom_file)}),
                "FAKE_STUB_BUNDLE_JSON": str(bundle_json), "FAKE_STUB_KE_APP_SBOM": str(sbom),
                "FAKE_IMAGE_PATHS": json.dumps({"/app": str(repo)})}

    def _host(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        repo = self._host_setup()
        self.json.write_text("", encoding="utf-8")
        env_vars = {"FAKE_DOCKER_ROOT_DIR": str(self.tmp / "no-such-docker-root")}
        env_vars.update(self._sbom_env(repo))
        env_vars.update(extra)  # a test may point the daemon's root dir somewhere real
        env = self._base_env(COMPOSE_PROJECT_NAME="ke-verify-1234", KE_SMOKE_OWNS_PROJECT="1", **env_vars)
        result = subprocess.run(["bash", "scripts/offline_check.sh"], cwd=repo, env=env,
                                capture_output=True, text=True, timeout=120)
        return result, fake_docker.records(self.json), repo

    @staticmethod
    def _event(record: dict) -> str | None:
        argv = record["argv"]
        if argv[:1] == ["DF"]:
            return "df"
        if argv[:2] == ["STUB", "bundle_fetch.sh"]:
            return None  # platform-sbom U8b: the sample fetch is an `_event_u2` event ("fetch") only
        if argv[:1] == ["STUB"]:
            return {"bundle.sh": "bundle", "net_isolated.sh": "net_isolated",
                    "teardown.sh": "teardown"}.get(argv[1], argv[1])
        if argv[:1] == ["compose"] and "up" in argv and "dind" in argv:
            return "up dind"
        if argv[:1] == ["compose"] and "run" in argv and "offline-client" in argv:
            return "run client"
        return None

    def _events(self, records: list[dict], df: bool = False) -> list[str]:
        out = [e for e in (self._event(r) for r in records) if e]
        return out if df else [e for e in out if e != "df"]

    @staticmethod
    def _project(record: dict) -> str | None:
        argv = record["argv"]
        for flag in ("-p", "--project-name"):
            if flag in argv[:-1]:
                return argv[argv.index(flag) + 1]
        for a in argv:
            if a.startswith("--project-name="):
                return a.split("=", 1)[1]
        return record["env"].get("COMPOSE_PROJECT_NAME")

    @staticmethod
    def _pairs(argv: list[str]) -> list[tuple[str, str]]:
        return list(zip(argv, argv[1:]))

    def _bundle_dirs(self, repo: Path) -> list[Path]:
        return sorted((repo / "dist").glob("ke-offline-*")) if (repo / "dist").exists() else []

    def test_offline_check_host_half_runs_stages_in_order(self):
        for arch, suffix in (("x86_64", "amd64"), ("aarch64", "arm64")):
            with self.subTest(arch=arch):
                result, records, repo = self._host(FAKE_DOCKER_ARCH=arch)
                out = self._out(result)
                self.assertEqual(result.returncode, 0, out)
                self.assertEqual(self._events(records),
                                 ["bundle", "up dind", "net_isolated", "run client", "teardown"], out)
                compose = [r for r in records if r["argv"][:1] == ["compose"]]
                projects = {self._project(r) for r in compose}
                teardown = next(r for r in records if self._event(r) == "teardown")
                projects.add(teardown["env"].get("COMPOSE_PROJECT_NAME"))
                self.assertEqual(len(projects), 1, f"one project for every stage: {projects}")
                project = projects.pop() or ""
                self.assertRegex(project, r"^ke-offline-[a-z0-9]+$",
                                 "the check runs its own ke-offline-<random> project, never the caller's")
                bundle = next(r["argv"] for r in records if self._event(r) == "bundle")
                self.assertNotIn("--arch", bundle, "the arch comes from the daemon, no --arch (§2.5 step 3)")
                out_dir = bundle[bundle.index("--out") + 1] if "--out" in bundle else ""
                self.assertRegex(out_dir, rf"(?:^|/)dist/{re.escape(project)}-{suffix}$")
                up = next(r["argv"] for r in records if self._event(r) == "up dind")
                self.assertIn(("--profile", "offline"), self._pairs(up))
                for flag in ("-d", "--wait"):
                    self.assertIn(flag, up)
                isolated = next(r["argv"] for r in records if self._event(r) == "net_isolated")
                self.assertEqual(isolated[2:], [f"{project}_offline"])
                run = next(r for r in records if self._event(r) == "run client")
                self.assertIn(("--profile", "offline"), self._pairs(run["argv"]))
                self.assertIn("--rm", run["argv"])
                mounted = run["env"].get("KE_OFFLINE_BUNDLE", "")
                self.assertTrue(mounted, "KE_OFFLINE_BUNDLE is not set for `run offline-client`")
                self.assertEqual(os.path.normpath(os.path.join(run["cwd"], mounted)),
                                 os.path.normpath(os.path.join(str(repo), out_dir)),
                                 "offline-client mounts the bundle bundle.sh just wrote")
                self.assertEqual(teardown["argv"][2:], ["--volumes", "--profile", "offline"],
                                 "the trap runs teardown.sh --volumes --profile offline")
                self.assertEqual(self._bundle_dirs(repo), [], "the bundle directory was left behind")

    def test_offline_check_fails_below_free_disk(self):
        # Orchestrator ruling 1 after CI run 39359710258 (docs/handoffs/platform-offline.md,
        # 2026-10-20; log docs/evidence/platform-offline/ci-39359710258.log: the check
        # refused with "need 10 GiB free on dist, found 9 GiB"): the floor is 7 GiB in
        # offline_check.sh and bundle.sh alike (was 10 GiB).
        for label, avail_kb, found in (
                ("7 GiB less 1 KiB (above 7 GB decimal, below 7 GiB)", 7 * GIB_KB - 1, 6),
                ("3 GiB", 3 * GIB_KB, 3)):
            with self.subTest(free=label):
                result, records, _ = self._host(FAKE_DF_AVAIL_KB=str(avail_kb))
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, "the check ran below the 7 GiB floor:\n" + out)
                self.assertNotIn("bundle", self._events(records), "bundle.sh ran below the floor")
                self.assertNotIn("up dind", self._events(records))
                self.assertRegex(out, r"need 7 GiB free")
                self.assertRegex(out, rf"found {found} GiB\b", "the figure found, rounded down")
                self.assertIsNone(SKIP_RX.search(out), "below the floor is a failure, never a skip")
                self.assertNotRegex(out, r"(?i)\bpass(?:ed)?\b")
                self.assertTrue([r for r in records if r["argv"][:1] == ["DF"]], "df was not consulted")
        with self.subTest(free="exactly 7 GiB (accepted)"):
            result, records, _ = self._host(FAKE_DF_AVAIL_KB=str(7 * GIB_KB))
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertIn("bundle", self._events(records))
        with self.subTest(free="9 GiB (accepted: the CI runner's free space, run 39359710258)"):
            result, records, _ = self._host(FAKE_DF_AVAIL_KB=str(9 * GIB_KB))
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertIn("bundle", self._events(records))
        with self.subTest(free="DockerRootDir on the host at 7 GiB less 1 KiB"):
            root_dir = self.tmp / "docker-root"
            root_dir.mkdir(exist_ok=True)
            result, records, _ = self._host(FAKE_DOCKER_ROOT_DIR=str(root_dir),
                                            FAKE_DF_AVAIL_BY_PATH=json.dumps({str(root_dir): 7 * GIB_KB - 1}))
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, "DockerRootDir below the floor was accepted:\n" + out)
            self.assertNotIn("bundle", self._events(records))
            self.assertIn(str(root_dir), out, "the message names the DockerRootDir path")
        with self.subTest(free="DockerRootDir not on the host (Docker Desktop)"):
            result, records, _ = self._host()
            out = self._out(result)
            self.assertEqual(result.returncode, 0, out)
            self.assertRegex(out, r"(?i)not measurable", "a DockerRootDir inside a VM is reported "
                             "as not measurable, not as a failure (§2.5 host step 2)")

    def test_offline_check_logs_disk_around_each_stage(self):
        for case, extra in (("pass", {}), ("client run fails", {"FAKE_DOCKER_FAIL": "offline-client"})):
            with self.subTest(case=case):
                result, records, _ = self._host(**extra)
                out = self._out(result)
                events = self._events(records, df=True)
                stages = [e for e in events if e != "df"]
                self.assertIn("run client", stages, out)
                if case == "pass":
                    self.assertEqual(result.returncode, 0, out)
                else:
                    self.assertNotEqual(result.returncode, 0, out)

                def df_between(a: str | None, b: str | None) -> bool:
                    lo = events.index(a) if a else -1
                    hi = events.index(b) if b else len(events)
                    return "df" in events[lo + 1:hi]

                self.assertTrue(df_between(None, "bundle"), f"no df before the disk check: {events}")
                self.assertTrue(df_between("bundle", "up dind"), f"no df after bundle: {events}")
                self.assertTrue(df_between("up dind", "run client"), f"no df after dind up: {events}")
                self.assertTrue(df_between("run client", "teardown"), f"no df after the client run: {events}")
                self.assertTrue(df_between("teardown", None), f"no df after teardown: {events}")
                blocks = [l for l in result.stdout.splitlines() if l.startswith("offline: df")]
                self.assertGreaterEqual(len(blocks), 5, f"one `offline: df <stage>` block per stage:\n{out}")
                for r in records:
                    if r["argv"][:1] == ["DF"]:
                        flags = "".join(a.lstrip("-") for a in r["argv"][1:] if a.startswith("-"))
                        self.assertTrue("P" in flags and "k" in flags, f"df -Pk expected: {r['argv']}")

    def test_offline_check_tears_down_on_failure(self):
        cases = {
            "below the disk floor": ({"FAKE_DF_AVAIL_KB": str(3 * GIB_KB)}, None),
            "bundle.sh fails": ({"FAKE_STUB_FAIL": "bundle.sh"}, "bundle"),
            "dind does not come up": ({"FAKE_DOCKER_FAIL": "dind"}, "up dind"),
            "offline network not isolated": ({"FAKE_STUB_FAIL": "net_isolated.sh"}, "net_isolated"),
            "client run fails": ({"FAKE_DOCKER_FAIL": "offline-client"}, "run client"),
        }
        order = ["bundle", "up dind", "net_isolated", "run client"]
        for case, (extra, failing) in cases.items():
            with self.subTest(case=case):
                result, records, repo = self._host(**extra)
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"{case} but the check exited 0:\n{out}")
                self.assertNotRegex(out, r"(?i)\bpass(?:ed)?\b")
                stages = self._events(records)
                ran = order[: order.index(failing) + 1] if failing else []
                self.assertEqual(stages, ran + ["teardown"],
                                 "later stages ran after a failure, or teardown did not run once")
                teardown = next(r for r in records if self._event(r) == "teardown")
                self.assertEqual(teardown["argv"][2:], ["--volumes", "--profile", "offline"])
                self.assertEqual(self._bundle_dirs(repo), [], "the bundle directory was left behind")

    def test_offline_check_tears_down_on_interrupt(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig.name):
                repo = self._host_setup()
                self.json.write_text("", encoding="utf-8")
                hooks = json.dumps([{"on": "offline-client", "sleep": 60}])
                env = self._base_env(FAKE_DOCKER_HOOKS=hooks,
                                     FAKE_DOCKER_ROOT_DIR=str(self.tmp / "no-such-docker-root"),
                                     **self._sbom_env(repo))
                proc = subprocess.Popen(["bash", "scripts/offline_check.sh"], cwd=repo, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        start_new_session=True)
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if any(self._event(r) == "run client" for r in fake_docker.records(self.json)):
                            break
                        time.sleep(0.1)
                    else:
                        self.fail("the check never reached `run offline-client`")
                    time.sleep(0.3)
                    os.killpg(proc.pid, sig)
                    proc.communicate(timeout=30)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(self._events(fake_docker.records(self.json)).count("teardown"), 1)
                self.assertEqual(self._bundle_dirs(repo), [])
                shutil.rmtree(repo, True)

    def test_offline_check_signal_exits_with_its_status_and_no_pass(self):
        """Security L-4 (docs/evidence/platform-supply-chain/security-u4-r1.md;
        orchestrator unit-5 ruling 2026-10-22): INT, TERM or HUP to the process
        group during the client run make the check exit 130/143/129 (a death
        by signal n reads 128 + n, as `$?` reports it), tear its project down
        once, remove the bundle, and never print "== offline_check: PASS".
        Before unit 5 a HUP ran the EXIT trap with $? = 0, and the trap printed
        PASS before the script died 129."""
        if not hasattr(os, "killpg"):  # pragma: no cover - the gates image is Linux
            self.skipTest("os.killpg is POSIX only")
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                repo = self._host_setup()
                self.json.write_text("", encoding="utf-8")
                hooks = json.dumps([{"on": "offline-client", "sleep": 60}])
                env = self._base_env(FAKE_DOCKER_HOOKS=hooks,
                                     FAKE_DOCKER_ROOT_DIR=str(self.tmp / "no-such-docker-root"),
                                     **self._sbom_env(repo))
                proc = subprocess.Popen(["bash", "scripts/offline_check.sh"], cwd=repo, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        start_new_session=True)
                out = ""
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline and proc.poll() is None:
                        if any(self._event(r) == "run client" for r in fake_docker.records(self.json)):
                            break
                        time.sleep(0.1)
                    else:
                        proc.kill()
                        proc.communicate(timeout=30)
                        self.fail("the check never reached `run offline-client`")
                    time.sleep(0.3)
                    os.killpg(proc.pid, sig)
                    stdout, stderr = proc.communicate(timeout=30)
                    out = stdout + stderr
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                rc = proc.returncode
                status = 128 - rc if rc < 0 else rc
                self.assertEqual(status, 128 + sig.value,
                                 f"offline_check on {sig.name} must exit {128 + sig.value} (L-4):\n{out}")
                self.assertNotIn("offline_check: PASS", out,
                                 f"offline_check printed PASS after {sig.name} during the client run "
                                 f"(security L-4):\n{out}")
                self.assertEqual(self._events(fake_docker.records(self.json)).count("teardown"), 1,
                                 f"teardown on {sig.name}")
                self.assertEqual(self._bundle_dirs(repo), [], "the bundle directory was left behind")
                shutil.rmtree(repo, True)

    def test_offline_check_fails_without_privileged_daemon(self):
        result, records, _ = self._host(FAKE_DOCKER_FAIL="dind")
        out = self._out(result)
        self.assertNotEqual(result.returncode, 0, out)
        self.assertRegex(out, r"(?i)privileged", "the message names the privileged dind container")
        self.assertRegex(out, r"(?i)blocker", "a daemon that refuses dind is a blocker (F5)")
        self.assertIsNone(SKIP_RX.search(out), "never a skip")
        self.assertNotRegex(out, r"(?i)\bpass(?:ed)?\b", "never a pass")
        self.assertNotIn("run client", self._events(records))

    # ---- host half: the throwaway bundle is opened to the client's uid -------
    # Orchestrator ruling after CI run 39364201188 (docs/handoffs/platform-offline.md,
    # 2026-10-20; log docs/evidence/platform-offline/ci-39364201188.log, "Permission
    # denied" on /bundle/images/*.tar): bundle.sh writes its output private (0600
    # files, 0700 dirs, owned by the host user) and stays so; offline-client runs
    # as uid 10001. The host half therefore runs `chmod -R a+rX` on exactly its own
    # $bundle_rel directory, after bundle.sh and before the client starts. Nothing
    # else changes mode: not dist/, not a sibling bundle, not <out>.manifest.sha256.
    # Docker Desktop bind mounts hide file modes, so only Linux CI saw the bug.

    _SNAP = r'''import json, os, stat, sys
root = os.environ["KE_TEST_SNAP_ROOT"]
tree = {}
for here, dirs, files in os.walk(root):
    for name in dirs + files:
        path = os.path.join(here, name)
        st = os.lstat(path)
        tree[os.path.relpath(path, root).replace(os.sep, "/")] = [stat.S_IMODE(st.st_mode), stat.S_ISDIR(st.st_mode)]
with open(os.environ["KE_TEST_SNAP_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"label": sys.argv[1], "tree": tree}) + "\n")
'''

    # bundle.sh stand-in that writes what the real one does on Linux: private
    # files and dirs, and the manifest hash beside (not inside) the bundle.
    _PRIVATE_BUNDLE_PRE = r'''out=""; prev=""
for a in "$@"; do [ "$prev" = "--out" ] && out="$a"; prev="$a"; done
if [ -n "$out" ]; then
  umask 077
  mkdir -p "$out/images" "$out/app/scripts"
  echo '{}' > "$out/bundle.json"
  @SBOM_STUB@
  for f in images/ke-app.tar images/valkey.tar app/compose.yml MANIFEST.sha256; do
    printf 'x\n' > "$out/$f"; chmod 600 "$out/$f"
  done
  for f in install.sh app/scripts/launch.sh; do
    printf '#!/bin/sh\n' > "$out/$f"; chmod 700 "$out/$f"
  done
  chmod 600 "$out/bundle.json"
  chmod 700 "$out" "$out/images" "$out/app" "$out/app/scripts"
  printf 'h\n' > "$out.manifest.sha256"; chmod 600 "$out.manifest.sha256"
fi'''.replace("@SBOM_STUB@", _SBOM_STUB.replace("\n", "\n  "))

    _DECOY = "dist/ke-offline-decoy-amd64"

    def _host_private_bundle(self) -> tuple[subprocess.CompletedProcess, list[dict], dict, list[dict]]:
        """Run the host half under umask 077 with a private-writing bundle.sh,
        a decoy sibling bundle, and a snapshot of every mode under the repo at
        the end of bundle.sh, at each docker call, and in the teardown trap."""
        repo = self._host_setup()
        snap = self.tmp / "snap.py"
        _executable(snap, f"#!{os.path.realpath(sys.executable)}\n" + self._SNAP)
        call_snap = '"$KE_TEST_SNAP" "@WHAT@"'
        _executable(repo / "scripts" / "bundle.sh",
                    _stub("bundle.sh", pre=self._PRIVATE_BUNDLE_PRE,
                          post=call_snap.replace("@WHAT@", "bundle.sh done")))
        _executable(repo / "scripts" / "teardown.sh",
                    _stub("teardown.sh", pre=call_snap.replace("@WHAT@", "teardown")))
        wrap = self.tmp / "wrapbin" / "docker"
        _executable(wrap, '#!/usr/bin/env bash\n"$KE_TEST_SNAP" "docker $*"\n'
                          f'exec "{self.tmp / "fakebin" / "docker"}" "$@"\n')
        decoy = repo / self._DECOY
        (decoy / "images").mkdir(parents=True)
        (decoy / "images" / "ke-app.tar").write_text("decoy\n", encoding="utf-8")
        (decoy / "bundle.json").write_text("{}\n", encoding="utf-8")
        (repo / f"{self._DECOY}.manifest.sha256").write_text("d\n", encoding="utf-8")
        for path, mode in ((decoy / "images" / "ke-app.tar", 0o600), (decoy / "bundle.json", 0o600),
                           (repo / f"{self._DECOY}.manifest.sha256", 0o600), (decoy / "images", 0o700),
                           (decoy, 0o700), (repo / "dist", 0o700)):
            path.chmod(mode)
        log = self.tmp / "snap.jsonl"
        log.write_text("", encoding="utf-8")
        self.json.write_text("", encoding="utf-8")
        env = self._base_env(COMPOSE_PROJECT_NAME="ke-verify-1234", KE_SMOKE_OWNS_PROJECT="1",
                             FAKE_DOCKER_ROOT_DIR=str(self.tmp / "no-such-docker-root"),
                             KE_TEST_SNAP=str(snap), KE_TEST_SNAP_ROOT=str(repo),
                             KE_TEST_SNAP_LOG=str(log), **self._sbom_env(repo))
        env["PATH"] = f"{wrap.parent}{os.pathsep}{env['PATH']}"
        baseline_log = self.tmp / "baseline.jsonl"
        subprocess.run([str(snap), "baseline"], env={**env, "KE_TEST_SNAP_LOG": str(baseline_log)},
                       check=True, timeout=60)
        baseline = json.loads(baseline_log.read_text(encoding="utf-8"))["tree"]
        result = subprocess.run(["bash", "-c", "umask 077 && exec bash scripts/offline_check.sh"],
                                cwd=repo, env=env, capture_output=True, text=True, timeout=120)
        snaps = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        return result, fake_docker.records(self.json), baseline, snaps

    def _bundle_rel(self, records: list[dict]) -> str:
        argv = next(r["argv"] for r in records if self._event(r) == "bundle")
        self.assertIn("--out", argv)
        return os.path.normpath(argv[argv.index("--out") + 1]).replace(os.sep, "/")

    @staticmethod
    def _snap(snaps: list[dict], pattern: str) -> dict[str, list]:
        found = [s["tree"] for s in snaps if re.search(pattern, s["label"])]
        if not found:
            raise AssertionError(f"no snapshot matching {pattern!r}: {[s['label'] for s in snaps]}")
        return found[0]

    @staticmethod
    def _opened(mode: int, is_dir: bool) -> int:
        """What `chmod a+rX` makes of mode: r for all; x for all on a dir or
        on a file some class can already execute; no write bit added."""
        return mode | 0o444 | (0o111 if is_dir or mode & 0o111 else 0)

    def _inside(self, rel: str, bundle_rel: str) -> bool:
        return rel == bundle_rel or rel.startswith(bundle_rel + "/")

    def _assert_private(self, tree: dict[str, list], bundle_rel: str) -> None:
        own = {k: v for k, v in tree.items() if self._inside(k, bundle_rel)}
        self.assertIn(f"{bundle_rel}/images/ke-app.tar", own, f"the stub bundle is missing: {sorted(own)}")
        for rel, (mode, _) in own.items():
            self.assertEqual(mode & 0o077, 0, f"the stub bundle.sh did not write {rel} private "
                             f"({oct(mode)}): the test would prove nothing")

    def _assert_opened(self, tree: dict[str, list], private: dict[str, list], bundle_rel: str,
                       when: str) -> None:
        own = sorted(k for k in private if self._inside(k, bundle_rel))
        self.assertTrue(own)
        for rel in own:
            mode, is_dir = private[rel]
            with self.subTest(when=when, path=rel):
                self.assertIn(rel, tree, f"{rel} vanished before {when}")
                got = tree[rel][0]
                self.assertEqual(oct(got), oct(self._opened(mode, is_dir)),
                                 f"{when}: {rel} is {oct(got)}; the client (uid 10001) needs "
                                 f"`chmod -R a+rX {bundle_rel}` (r for all, x on dirs, no write added): "
                                 "CI run 39364201188 failed with Permission denied on /bundle/images/*.tar")

    def test_offline_check_opens_its_own_bundle_to_the_client_only(self):
        result, records, baseline, snaps = self._host_private_bundle()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        bundle_rel = self._bundle_rel(records)
        self.assertRegex(bundle_rel, r"^dist/ke-offline-[a-z0-9]+-amd64$")
        self.assertNotEqual(bundle_rel, self._DECOY)
        private = self._snap(snaps, r"^bundle\.sh done$")
        self._assert_private(private, bundle_rel)
        final = self._snap(snaps, r"^teardown$")
        self._assert_opened(final, private, bundle_rel, "at teardown")
        # Nothing outside $bundle_rel changes mode: every path that existed
        # before the run (dist/, the decoy bundle and its hash, the scripts),
        # and the hash file bundle.sh wrote beside the bundle.
        outside = {k: v for k, v in baseline.items() if not self._inside(k, bundle_rel)}
        outside[f"{bundle_rel}.manifest.sha256"] = private[f"{bundle_rel}.manifest.sha256"]
        self.assertIn(f"{self._DECOY}/images/ke-app.tar", outside)
        for rel, (mode, _) in sorted(outside.items()):
            with self.subTest(outside=rel):
                self.assertIn(rel, final, f"{rel} vanished")
                self.assertEqual(oct(final[rel][0]), oct(mode),
                                 f"{rel} changed mode outside the check's own bundle dir {bundle_rel}: "
                                 "the chmod must name exactly $bundle_rel")

    def test_offline_check_opens_bundle_before_the_client_starts(self):
        result, records, _, snaps = self._host_private_bundle()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self._events(records),
                         ["bundle", "up dind", "net_isolated", "run client", "teardown"], out)
        bundle_rel = self._bundle_rel(records)
        private = self._snap(snaps, r"^bundle\.sh done$")
        self._assert_private(private, bundle_rel)
        # The wrapper snapshots before the fake docker runs, so this is the
        # tree the client would see: it must already be open, not opened by
        # the cleanup trap after the client has failed.
        for start in (r"^docker compose\b.*\brun\b.*\boffline-client\b",
                      r"^docker compose\b.*\bup\b.*\boffline-client\b"):
            if any(re.search(start, s["label"]) for s in snaps):
                self._assert_opened(self._snap(snaps, start), private, bundle_rel,
                                    "when the client starts")
                break
        else:
            self.fail(f"no `compose run|up offline-client` call: {[s['label'] for s in snaps]}")

    # ---- platform-sbom U8b: the source sample fetch (was U2's interim pull) ----
    # PSC-20; design-notes "N1 amendment, U2" *Interim pull (U2 to U8)*: the host
    # half pulled the generator through its own compose file, after the Compose
    # version check and immediately before bundle.sh (which never pulls).
    # PSC-23 U8-8 (design-notes "N4 amendment, U8" item 8; re-pinned by the
    # tester, U8b RED): one `bash scripts/bundle_fetch.sh --set sample --out
    # <dir>` replaces that pull at the same place; bundle_fetch.sh pulls the
    # generator (tests/test_bundle_fetch.py). The interim pull's events become
    # the "fetch" event; the base-pull rows stay.

    FETCH_FAIL = "offline_check: FAIL (scripts/bundle_fetch.sh failed (see its FAIL line above); no retry)"

    def _event_u2(self, record: dict) -> str | None:
        """`_event`, plus any pull: "pull sbom" when it names the generator's
        compose file or service, "pull base" when it names the ke-app base by
        its pinned digest (platform-sbom U4, orchestrator ruling 6), else
        "pull" (any other pull is out of order); and "drift" for the `docker
        save` of that base (the start of the U4 drift step). Platform-sbom
        U4b (PSC-26, N16): "pull neo4j base" when a pull names the official
        neo4j image by its pinned digest, and "neo4j" for the checker run
        `sbom_check.py neo4j` (tester, U4b RED)."""
        from tests import neo4j_support as ns
        from tests import sbom_support as ss
        argv = record["argv"]
        if argv[:2] == ["STUB", "bundle_fetch.sh"]:
            return "fetch"  # platform-sbom U8b (U8-8)
        digest = ss.base_ref().rsplit("@", 1)[1]
        neo4j_digest = ns.OFFICIAL_CONFIG_DIGEST
        if argv[:1] != ["STUB"] and ("pull" in argv or argv[:2] == ["image", "pull"]):
            names = cs.SBOM_COMPOSE_NAME in " ".join(argv) or argv[-1:] == ["sbom"]
            if names:
                return "pull sbom"
            if any(a.endswith("@" + neo4j_digest) for a in argv):
                return "pull neo4j base"
            return "pull base" if any(a.endswith("@" + digest) for a in argv) else "pull"
        if argv[:1] == ["run"] and any(a.replace("\\", "/").endswith("/sbom_check.py") for a in argv):
            tail = argv[[i for i, a in enumerate(argv) if a.replace("\\", "/").endswith("/sbom_check.py")][-1] + 1:]
            if tail[:1] == ["neo4j"]:
                return "neo4j"
        if (argv[:1] == ["save"] or argv[:2] == ["image", "save"]) and any(a.endswith("@" + digest) for a in argv):
            return "drift"
        return self._event(record)

    def _events_u2(self, records: list[dict]) -> list[str]:
        return [e for e in (self._event_u2(r) for r in records) if e and e != "df"]

    def _fetch_dir(self, record: dict, repo: Path) -> str:
        argv = record["argv"][2:]
        self.assertEqual(sorted(argv[::2]), ["--out", "--set"], f"want --set and --out only: {argv}")
        pairs = dict(zip(argv[::2], argv[1::2]))
        self.assertEqual(pairs.get("--set"), "sample", "verify and CI only ever fetch the sample (Q63, U8-8)")
        return os.path.normpath(os.path.join(record["cwd"], pairs.get("--out", "")))

    def test_offline_check_fetches_the_sample(self):
        """PSC-23 U8-8 (design-notes N4 amendment U8 item 8), which replaces
        the U2 interim-pull rows (test_offline_check_pulls_sbom_generator_before_bundle;
        tester, U8b RED): one `bash scripts/bundle_fetch.sh --set sample --out
        <dir>` at the interim pull's place (after the Compose version check,
        before the ke-app and ke-neo4j base pulls); <dir> under dist/, outside
        the bundle, removed by the EXIT trap; the host half no longer pulls the
        generator itself (bundle_fetch.sh does)."""
        result, records, repo = self._host()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        # The order U4/U4b pinned, with the interim pull's event replaced by the fetch.
        self.assertEqual(self._events_u2(records),
                         ["fetch", "pull base", "pull neo4j base", "bundle", "drift", "neo4j", "up dind",
                          "net_isolated", "run client", "teardown"], out)
        fetches = [r for r in records if self._event_u2(r) == "fetch"]
        self.assertEqual(len(fetches), 1, "one call of scripts/bundle_fetch.sh, never retried")
        fetch_dir = self._fetch_dir(fetches[0], repo)
        dist = os.path.normpath(os.path.join(str(repo), "dist"))
        self.assertTrue(fetch_dir.startswith(dist + os.sep), f"the sample dir {fetch_dir} is not under dist/")
        bundle = next(r for r in records if self._event(r) == "bundle")
        bundle_dir = os.path.normpath(os.path.join(bundle["cwd"], bundle["argv"][bundle["argv"].index("--out") + 1]))
        self.assertFalse(fetch_dir == bundle_dir or fetch_dir.startswith(bundle_dir + os.sep)
                         or bundle_dir.startswith(fetch_dir + os.sep),
                         f"the sample dir {fetch_dir} and the bundle {bundle_dir} overlap")
        project = next(r for r in records if self._event(r) == "teardown")["env"].get("COMPOSE_PROJECT_NAME") or "?"
        self.assertIn(project, os.path.basename(fetch_dir), "the sample dir is the run's own (named by its project)")
        self.assertFalse(os.path.exists(fetch_dir), "the EXIT trap did not remove the sample dir")
        generator_pulls = [r["argv"] for r in records if r["argv"][:1] == ["compose"] and "pull" in r["argv"]
                           and cs.SBOM_COMPOSE_NAME in " ".join(r["argv"])]
        self.assertEqual(generator_pulls, [], "the host half still pulls the generator (U8: bundle_fetch.sh does)")
        version = [i for i, r in enumerate(records) if r["argv"][:2] == ["compose", "version"]]
        self.assertTrue(version and version[0] < records.index(fetches[0]),
                        "the fetch comes after the Compose version check")
        self.assertIn("offline: fetching the source sample (scripts/bundle_fetch.sh --set sample)",
                      result.stdout.splitlines(), "design item 8's stage line")
        self.assertIn("offline: df after fetch", result.stdout.splitlines(), "df is logged after the fetch")
        self.assertEqual(self._bundle_dirs(repo), [])
        text = OFFLINE_CHECK.read_text(encoding="utf-8")
        head = "\n".join(ln for ln in text.splitlines()[:40] if ln.startswith("#"))
        self.assertIn("bundle_fetch.sh", head, "the header's host-half stage list names the fetch (item 8)")

    def test_offline_check_stops_when_the_fetch_fails(self):
        """U8-8: a fetch failure fails offline_check.sh before bundle.sh runs,
        with the fetch's FAIL line in the output; no retry; the trap tears
        down and removes the sample dir (replaces
        test_offline_check_stops_when_sbom_pull_fails; tester, U8b RED)."""
        with self.subTest(case="the fetch fails"):
            result, records, repo = self._host(FAKE_STUB_FAIL="bundle_fetch.sh")
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn(self.FETCH_FAIL, result.stderr.splitlines(), out)
            self.assertIn("bundle_fetch: FAIL (stage fetch: stub; no retry)", result.stderr.splitlines(),
                          "the fetch's own FAIL line is not in the output")
            self.assertNotRegex(out, r"(?i)\bpass(?:ed)?\b")
            self.assertEqual(self._events_u2(records), ["fetch", "teardown"],
                             "bundle.sh ran after a failed fetch, the fetch was retried, or teardown did not run once")
            teardown = next(r for r in records if self._event(r) == "teardown")
            self.assertEqual(teardown["argv"][2:], ["--volumes", "--profile", "offline"])
            self.assertEqual(self._bundle_dirs(repo), [], "the bundle or the sample dir was left behind")
            self.assertEqual(sorted((repo / "dist").glob("*sources*")), [], "the sample dir was left behind")
        for case, extra in (("below the disk floor", {"FAKE_DF_AVAIL_KB": str(3 * GIB_KB)}),
                            ("Compose below 2.27", {"FAKE_COMPOSE_VERSION": "2.20.0"})):
            with self.subTest(case=f"{case}: no fetch"):
                result, records, _ = self._host(**extra)
                self.assertNotEqual(result.returncode, 0, self._out(result))
                self.assertEqual(self._events_u2(records), ["teardown"],
                                 "the sample is fetched only after the disk and Compose checks")

    # ---- platform-sbom U9b: bundle.sh bundles the fetched sample ----------------

    def test_offline_check_bundles_the_sample_sources(self):
        """U9-12 (design-notes "N9 amendment, U9" items 2 and 14; Q63; tester,
        U9b RED): offline_check.sh passes `--sources <the dir bundle_fetch.sh
        wrote> --sources-set sample` to bundle.sh, each once; and a bundle.sh
        failure still stops the check before the offline client (no retry)."""
        result, records, repo = self._host()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        fetch = next(r for r in records if self._event_u2(r) == "fetch")
        fetch_dir = self._fetch_dir(fetch, repo)
        bundles = [r for r in records if self._event(r) == "bundle"]
        self.assertEqual(len(bundles), 1, "one bundle.sh call")
        argv = bundles[0]["argv"][2:]
        self.assertEqual(argv.count("--sources"), 1, f"want one --sources: {argv}")
        self.assertEqual(argv.count("--sources-set"), 1, f"want one --sources-set: {argv}")
        pairs = dict(zip(argv, argv[1:]))
        self.assertEqual(pairs.get("--sources-set"), "sample", "verify and CI bundle the sample only (Q63, U9-12)")
        given = os.path.normpath(os.path.join(bundles[0]["cwd"], pairs.get("--sources", "")))
        self.assertEqual(given, fetch_dir, "bundle.sh is not given the directory bundle_fetch.sh wrote")
        with self.subTest(case="bundle.sh fails"):
            result, records, repo = self._host(FAKE_STUB_FAIL="bundle.sh")
            self.assertNotEqual(result.returncode, 0, self._out(result))
            self.assertEqual(self._events_u2(records), ["fetch", "pull base", "pull neo4j base", "bundle", "teardown"],
                             "the check went on after bundle.sh failed, or retried it")
            self.assertEqual(self._bundle_dirs(repo), [], "the bundle was left behind")
            self.assertEqual(sorted((repo / "dist").glob("*sources*")), [], "the sample dir was left behind")

    # ---- client half ---------------------------------------------------------

    def _client(self, entries: list[dict[str, str]] | None = None,
                **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        self._require_script()
        bundle = self.tmp / "bundle"
        shutil.rmtree(bundle, True)
        bundle.mkdir()
        (bundle / "bundle.json").write_text(_bundle_json(entries or BUNDLE_ENTRIES), encoding="utf-8")
        (bundle / "stub.template").write_text(_stub("@NAME@"), encoding="utf-8", newline="\n")
        _executable(bundle / "install.sh", _stub("install.sh", pre=_INSTALL_PRE, post=_INSTALL_POST))
        install_root = self.tmp / "install"
        shutil.rmtree(install_root, True)
        install_root.mkdir()
        script = self.tmp / "opt" / "ke" / "offline_check.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(OFFLINE_CHECK, script)
        work = self.tmp / "work"
        work.mkdir(exist_ok=True)
        self.json.write_text("", encoding="utf-8")
        defaults = {"FAKE_DOCKER_LS_AFTER": json.dumps(AS_SET), "DOCKER_CERT_PATH": "/certs/client"}
        defaults.update(extra)
        env = self._base_env(KE_OFFLINE_CLIENT="1", KE_IN_GATES="",
                             KE_OFFLINE_BUNDLE_DIR=str(bundle), KE_OFFLINE_INSTALL_ROOT=str(install_root),
                             DOCKER_HOST="tcp://docker:2376", DOCKER_TLS_VERIFY="1",
                             **defaults)
        result = subprocess.run(["bash", str(script)], cwd=work, env=env,
                                capture_output=True, text=True, timeout=120)
        return result, fake_docker.records(self.json), install_root

    @staticmethod
    def _client_event(record: dict) -> str | None:
        argv = record["argv"]
        if argv[:1] == ["STUB"]:
            return argv[1].removesuffix(".sh")
        if argv[:1] == ["images"] or argv[:2] in (["image", "ls"], ["image", "list"]):
            return "ls"
        if argv[:1] == ["pull"] or argv[:2] == ["image", "pull"]:
            return "pull"
        if argv[:1] == ["info"]:
            return "info"
        return None

    def _client_events(self, records: list[dict]) -> list[str]:
        return [e for e in (self._client_event(r) for r in records) if e]

    def test_offline_check_client_half_runs_install_launch_smoke_teardown(self):
        result, records, root = self._client()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        events = self._client_events(records)
        stubs = [e for e in events if e in ("install", "launch", "smoke", "teardown")]
        self.assertEqual(stubs, ["install", "launch", "smoke", "teardown"], out)
        first_install = events.index("install")
        self.assertIn("ls", events[:first_install], "the store is listed before install")
        self.assertIn("pull", events[:first_install], "the pull probe runs before install")
        self.assertIn("ls", events[events.index("teardown") + 1:], "the tag set is read after teardown")
        target = root / "op" / "ke"
        install = next(r for r in records if r["argv"][:2] == ["STUB", "install.sh"])
        self.assertEqual(install["argv"][2:], [str(target)], "bash <bundle>/install.sh <root>/op/ke")
        self.assertEqual(install["env"]["PARENT_MODE"], "755",
                         "the client makes an operator-owned 0755 parent first (round 4)")
        for name in ("launch", "smoke", "teardown"):
            rec = next(r for r in records if r["argv"][:2] == ["STUB", f"{name}.sh"])
            with self.subTest(step=name):
                self.assertEqual(os.path.realpath(rec["cwd"]), os.path.realpath(target),
                                 f"{name}.sh runs in the installed tree")
        smoke = next(r for r in records if r["argv"][:2] == ["STUB", "smoke.sh"])
        self.assertEqual(smoke["env"]["KE_SMOKE_OWNS_PROJECT"], "1",
                         "the inner smoke owns its project (store stop/start runs)")
        teardown = next(r for r in records if r["argv"][:2] == ["STUB", "teardown.sh"])
        self.assertIn("--volumes", teardown["argv"])
        pull = next(r["argv"] for r in records if self._client_event(r) == "pull")
        self.assertIn(PG_REF, pull, "the pull probe uses the first vendor reference in bundle.json")

    def test_offline_check_asserts_clean_daemon(self):
        for case, before in (("a tagged image", ["leftover/img:1"]), ("a dangling image", ["<none>:<none>"])):
            with self.subTest(case=case):
                result, records, _ = self._client(FAKE_DOCKER_LS_BEFORE=json.dumps(before))
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"installed into a daemon holding {case}:\n{out}")
                self.assertRegex(out, r"(?i)not clean")
                self.assertNotIn("install", self._client_events(records), "install ran on a dirty daemon")
        with self.subTest(case="the registry pull succeeds"):
            result, records, _ = self._client(FAKE_DOCKER_PULL_OK="1")
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, f"the daemon has egress but the check went on:\n{out}")
            self.assertRegex(out, r"(?i)inconclusive", "egress makes the gate inconclusive, never passed")
            self.assertNotIn("install", self._client_events(records))
        with self.subTest(case="the pull is bounded by timeout"):
            self._require_script()
            body ="\n".join(l for l in OFFLINE_CHECK.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith("#"))
            self.assertRegex(body, r"\btimeout\s+(?:-\S+\s+)*\d+[smh]?\s+docker\s+(?:image\s+)?pull\b",
                             "the pull probe is bounded by `timeout <n> docker pull`")

    def test_offline_dind_uses_containerd_store(self):
        classic = json.dumps([["Backing Filesystem", "extfs"], ["Supports d_type", "true"],
                              ["Using metacopy", "false"], ["Native Overlay Diff", "true"],
                              ["userxattr", "false"]])
        with self.subTest(case="classic store (overlay2)"):
            result, records, _ = self._client(FAKE_DOCKER_STORAGE_DRIVER="overlay2",
                                              FAKE_DOCKER_DRIVER_STATUS=classic)
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, f"the classic store was accepted:\n{out}")
            self.assertRegex(out, r"(?i)inconclusive")
            self.assertRegex(out, r"(?i)containerd")
            self.assertNotIn("install", self._client_events(records), "install ran before the store check")
        with self.subTest(case="containerd store (control)"):
            result, records, _ = self._client()
            self.assertEqual(result.returncode, 0, self._out(result))
            events = self._client_events(records)
            self.assertIn("info", events[: events.index("install")], "the store is asserted before install")
        with self.subTest(case="compose: Engine >= 29 dind, store not overridden"):
            found = _service("dind")
            self.assertIsNotNone(found, "no compose file defines `dind`")
            assert found is not None
            dind = found[1]
            match = re.match(r"^docker:(\d+)", str(dind.get("image", "")))
            self.assertTrue(match and int(match.group(1)) >= 29,
                            "the pinned dind Engine's default store is containerd from 29 (spike S1)")
            text = json.dumps({k: dind.get(k) for k in ("command", "entrypoint", "environment")})
            self.assertNotRegex(text, r"storage-driver|containerd-snapshotter\W+false",
                                "dind must keep its default (containerd) image store")

    def test_offline_check_fails_when_tag_set_differs_from_as_set(self):
        with self.subTest(case="equal sets, dangling ignored (control)"):
            result, _, _ = self._client(FAKE_DOCKER_LS_AFTER=json.dumps(AS_SET + ["<none>:<none>"]))
            self.assertEqual(result.returncode, 0, self._out(result))
        extra = "postgres:16-bookworm"
        with self.subTest(case="an extra name (a pull happened)"):
            result, _, _ = self._client(FAKE_DOCKER_LS_AFTER=json.dumps(AS_SET + [extra]))
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, f"an extra tag was accepted:\n{out}")
            self.assertIn(extra, out, "the failure names the differing tag")
        with self.subTest(case="a missing name"):
            result, _, _ = self._client(FAKE_DOCKER_LS_AFTER=json.dumps(AS_SET[:-1]))
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, f"a missing tag was accepted:\n{out}")
            self.assertIn(AS_SET[-1], out, "the failure names the missing tag")
        with self.subTest(case="same names, one swapped"):
            swapped = AS_SET[:-1] + ["ke-vendor/valkey:cccccccccccc"]
            result, _, _ = self._client(FAKE_DOCKER_LS_AFTER=json.dumps(swapped))
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("ke-vendor/valkey:cccccccccccc", out)
            self.assertIn(AS_SET[-1], out)
        # Review B1 / security M-OCa (rework round 1): on the containerd store a
        # digest-pinned pull (`name:tag@sha256:...`, the form of every vendor
        # ref here) lists as `name:<none>`. Only the dangling `<none>:<none>`
        # is excluded from the comparison (PS-3.2 *No pull happened*, §2.5
        # client step 6); any other `<none>` row is an extra name.
        for pulled in ("postgres:<none>", "docker:<none>"):
            with self.subTest(case=f"a digest-pinned pull lands as {pulled}"):
                result, _, _ = self._client(FAKE_DOCKER_LS_AFTER=json.dumps(AS_SET + [pulled]))
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"{pulled} after install was accepted:\n{out}")
                self.assertIn(pulled, out, "the failure names the `<none>`-tagged entry")
                self.assertNotIn("nothing was pulled", out)

    def test_offline_check_client_refuses_ca_or_server_certs(self):
        # Security L-OCb (rework round 1): the CA key stays out of the client
        # only because Compose applies `volume.subpath: client`. The client
        # half fails closed, before it touches the inner daemon, if its TLS
        # directory ${DOCKER_CERT_PATH} (/certs/client in offline-client) holds
        # a `ca` or a `server` entry of any kind.
        def certs(*entries: str) -> Path:
            d = self.tmp / "certs-client"
            shutil.rmtree(d, True)
            d.mkdir()
            for f in ("ca.pem", "cert.pem", "key.pem"):  # what dind writes into client/
                (d / f).write_text("x\n", encoding="utf-8")
            for e in entries:
                kind, name = e.split(":", 1)
                if kind == "dir":
                    (d / name).mkdir()
                    (d / name / "key.pem").write_text("k\n", encoding="utf-8")
                elif kind == "file":
                    (d / name).write_text("k\n", encoding="utf-8")
                else:
                    os.symlink(str(self.tmp / "nowhere"), d / name)
            return d

        with self.subTest(case="client certs only (control: ca.pem is not ca/)"):
            d = certs()
            result, records, _ = self._client(DOCKER_CERT_PATH=str(d))
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertIn("install", self._client_events(records))
        for entry in ("dir:ca", "dir:server", "file:ca", "file:server", "link:ca"):
            name = entry.split(":", 1)[1]
            with self.subTest(case=entry):
                d = certs(entry)
                result, records, _ = self._client(DOCKER_CERT_PATH=str(d))
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0,
                                    f"the client ran with {d / name} present:\n{out}")
                self.assertIn(str(d / name), out, "the refusal names the path it found")
                events = self._client_events(records)
                self.assertNotIn("install", events, "install ran with CA/server material mounted")
                self.assertNotIn("pull", events, "the check went on to the pull probe")
                self.assertEqual([r["argv"] for r in records if r["argv"][:1] != ["STUB"]], [],
                                 "the cert check comes before any call to the inner daemon")
                self.assertIsNone(SKIP_RX.search(out), "never a skip")
                self.assertNotIn("nothing was pulled", out)


    # ---- platform-sbom U9d: the launch diagnostic and the runner measurements --
    # Criteria: docs/requirements.md "U9d precision" U9d-1..U9d-5 (A82a). Design:
    # design-notes "N9 amendment, U9d" items 5-13 and ruling O-22 (Health.Log
    # output JSON-quoted on one prefixed line; KE_OFFLINE_MEMINFO a client-only
    # seam). Fake knobs: tests/fake_docker.py "platform-sbom U9d". Tester, U9d
    # RED. No existing row above changes (expected re-pins: none).

    def _u9d_meminfo(self, text: str = "", name: str = "meminfo") -> Path:
        path = self.tmp / name
        path.write_text(text or U9D_MEMINFO, encoding="utf-8")
        return path

    def _client_u9d(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        """The client half with fixed measurement sources: a meminfo file, df
        figures for `/` and the install root, and four `system df` rows."""
        defaults = {"KE_OFFLINE_MEMINFO": str(self._u9d_meminfo()),
                    "FAKE_DF_TOTAL_KB": str(U9D_DF_TOTAL_KB),
                    "FAKE_DF_AVAIL_BY_PATH": json.dumps({"/": U9D_ROOT_AVAIL_KB,
                                                         str(self.tmp / "install"): U9D_INSTALL_AVAIL_KB}),
                    "FAKE_DOCKER_SYSTEM_DF": json.dumps(U9D_SYSTEM_DF)}
        defaults.update(extra)
        return self._client(**defaults)

    def _launch_failure(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        env = {"FAKE_STUB_FAIL": "launch.sh", "FAKE_DOCKER_CONTAINERS": json.dumps(U9D_CONTAINERS),
               "FAKE_COMPOSE_LOGS": json.dumps(U9D_LOGS)}
        env.update(extra)
        return self._client_u9d(**env)

    def _host_merged(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        """`_host` with stderr merged into stdout, so the order of a stdout
        line and the FAIL line (stderr) can be read (design item 13)."""
        repo = self._host_setup()
        self.json.write_text("", encoding="utf-8")
        env_vars = {"FAKE_DOCKER_ROOT_DIR": str(self.tmp / "no-such-docker-root")}
        env_vars.update(self._sbom_env(repo))
        env_vars.update(extra)
        env = self._base_env(COMPOSE_PROJECT_NAME="ke-verify-1234", KE_SMOKE_OWNS_PROJECT="1", **env_vars)
        result = subprocess.run(["bash", "scripts/offline_check.sh"], cwd=repo, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        return result, fake_docker.records(self.json), repo

    def _point(self, lines: list[str], prefix: str, point: str) -> tuple[int, int, list[str]]:
        """The contiguous block of `<prefix><point> ...` lines, ending with
        `<prefix><point> done in <N> s` (U9d-2, U9d-4)."""
        idx = [i for i, line in enumerate(lines) if line.startswith(f"{prefix}{point} ")]
        self.assertTrue(idx, f"no `{prefix}{point} ...` line (U9d-2):\n" + "\n".join(lines))
        self.assertEqual(idx, list(range(idx[0], idx[-1] + 1)),
                         f"{point} is not one contiguous block (U9d-2):\n" + "\n".join(lines))
        block = [lines[i] for i in idx]
        self.assertRegex(block[-1], rf"^{re.escape(prefix)}{point} done in \d+ s$",
                         f"{point}'s last line gives its elapsed whole seconds (U9d-4)")
        for line in block:
            self.assertIsNone(U9D_BANNED.search(line), f"a measure line uses a gate word: {line}")
        return idx[0], idx[-1], block

    def _no_point(self, lines: list[str], prefix: str, point: str) -> None:
        self.assertEqual([line for line in lines if line.startswith(f"{prefix}{point} ")], [],
                         f"{point} printed where it must not be")

    def _assert_client_figures(self, block: list[str], point: str, root: Path) -> None:
        p = f"offline-client: measure: {point} "
        used = U9D_DF_TOTAL_KB - U9D_ROOT_AVAIL_KB
        slash = [line for line in block if re.match(rf"{re.escape(p)}df /[ :(]", line)]
        self.assertEqual(len(slash), 1, f"{point}: one `df /` line (the host daemon's storage, QD-3): {block}")
        self.assertIn(f"used {used} KiB", slash[0], "used space of `/`, in KiB")
        self.assertIn(f"available {U9D_ROOT_AVAIL_KB} KiB", slash[0], "free space of `/`, in KiB")
        inst = [line for line in block if line.startswith(f"{p}df {root}")]
        self.assertEqual(len(inst), 1, f"{point}: one `df -Pk /install` line: {block}")
        self.assertIn(f"used {U9D_DF_TOTAL_KB - U9D_INSTALL_AVAIL_KB} KiB", inst[0])
        self.assertIn(f"available {U9D_INSTALL_AVAIL_KB} KiB", inst[0])
        mem = [line for line in block if line.startswith(f"{p}memory")]
        self.assertEqual(len(mem), 1, f"{point}: one memory line: {block}")
        self.assertIn("MemAvailable 1234567 kB", mem[0], "MemAvailable in kB, as /proc/meminfo states it")
        self.assertIn("SwapFree 2048 kB", mem[0], "SwapFree in kB, as /proc/meminfo states it")
        for row in U9D_SYSTEM_DF:
            rx = (rf"system df\b.*\b{re.escape(row['Type'])}\b.*\b{row['TotalCount']}\b.*"
                  rf"{re.escape(row['Size'])}.*{re.escape(row['Reclaimable'])}")
            with self.subTest(point=point, system_df=row["Type"]):
                self.assertEqual(len([line for line in block if re.search(rx, line)]), 1,
                                 f"{point}: the inner `docker system df` {row['Type']} row (count, size, "
                                 f"reclaimable, Docker's units): {block}")

    @staticmethod
    def _measure_calls(records: list[dict]) -> list[int]:
        return [i for i, r in enumerate(records) if r["argv"][:1] == ["DF"] or r["argv"][:2] == ["system", "df"]]

    @staticmethod
    def _stub_at(records: list[dict], name: str) -> int:
        return next(i for i, r in enumerate(records) if r["argv"][:2] == ["STUB", name])

    @staticmethod
    def _diag_calls(records: list[dict]) -> list[list[str]]:
        out = []
        for r in records:
            a = r["argv"]
            if (a[:1] in (["ps"], ["inspect"]) or a[:2] in (["container", "inspect"], ["container", "ls"],
                                                             ["container", "list"], ["container", "ps"])
                    or (a[:1] == ["compose"] and "logs" in a)):
                out.append(a)
        return out

    def _diag_block(self, stdout: str) -> list[str]:
        lines = stdout.splitlines()
        idx = [i for i, line in enumerate(lines) if line.startswith(U9D_DIAG)]
        self.assertTrue(idx, "no `offline-client: diag:` line after a launch failure (U9d-1):\n" + stdout)
        self.assertEqual(idx, list(range(idx[0], idx[-1] + 1)),
                         "the diagnostic is not one block of prefixed lines: a line inside it lacks "
                         "`offline-client: diag: ` (U9d-1):\n" + stdout)
        self.assertEqual(idx[-1], len(lines) - 1, "the client printed after its diagnostic:\n" + stdout)
        return [lines[i][len(U9D_DIAG):] for i in idx]

    def _containers(self, diag: list[str]) -> dict[str, list[str]]:
        heads = [(k, m.group(1)) for k, line in enumerate(diag) if (m := re.match(r"container (\S+)", line))]
        names = [name for _, name in heads]
        self.assertEqual(sorted(names), sorted(c["Names"] for c in U9D_CONTAINERS),
                         "one block per container of the stack, each once (U9d-1):\n" + "\n".join(diag))
        out = {}
        for n, (k, name) in enumerate(heads):
            end = heads[n + 1][0] if n + 1 < len(heads) else len(diag)
            out[name] = diag[k:end]
        return out

    def _has_state(self, block: list[str], field: str, value: str) -> None:
        self.assertTrue([line for line in block if re.fullmatch(rf"\s*{re.escape(field)}: {re.escape(value)}", line)],
                        f"`{field}: {value}` missing (U9d-1):\n" + "\n".join(block))

    def test_offline_client_prints_diag_on_launch_failure(self):
        """U9d-1, U9d-5: on a launch failure, one prefixed block per container
        with the allowed State fields (`<absent>` for one it lacks), Health.Log
        entries JSON-quoted on one line each (O-22), and the last 50 log lines
        of each non-healthy service only; nothing private; launch's status."""
        result, records, root = self._launch_failure()
        out = self._out(result)
        self.assertEqual(result.returncode, 7, "the client exits with launch's own status (QD-6):\n" + out)
        self.assertNotIn("smoke", self._client_events(records), "smoke ran after a failed launch")
        diag = self._diag_block(result.stdout)
        blocks = self._containers(diag)
        pg, neo, worker = (blocks["knowledge-engine-postgres-1"], blocks["knowledge-engine-neo4j-1"],
                           blocks["knowledge-engine-worker-1"])
        with self.subTest(container="healthy (postgres)"):
            for field, value in (("State.Status", "running"), ("State.ExitCode", "0"),
                                 ("State.OOMKilled", "false"), ("State.Health.Status", "healthy")):
                self._has_state(pg, field, value)
            self.assertNotIn("pg-ok-1", out, "a healthy container's logs are printed (U9d-1)")
        with self.subTest(container="unhealthy (neo4j)"):
            for field, value in (("State.Status", "running"), ("State.ExitCode", "0"),
                                 ("State.OOMKilled", "false"), ("State.Health.Status", "unhealthy")):
                self._has_state(neo, field, value)
            for entry in U9D_CONTAINERS[1]["State"]["Health"]["Log"]:
                quoted = json.dumps(entry["Output"])
                hits = [line for line in neo if entry["End"] in line and quoted in line
                        and re.search(rf"\bexit {entry['ExitCode']}\b", line)]
                self.assertEqual(len(hits), 1, f"Health.Log entry {entry['End']}: its end time, exit code and "
                                 f"output JSON-quoted on one line (O-22):\n" + "\n".join(neo))
            self.assertEqual([line for line in result.stdout.splitlines() if "Unable to connect" in line],
                             [U9D_DIAG + next(line for line in neo if "Unable to connect" in line)],
                             "a multi-line probe output is one prefixed line")
            kept, cut = U9D_LOGS["neo4j"][-50:], U9D_LOGS["neo4j"][:-50]
            for line in kept[:-1]:
                self.assertTrue([d for d in neo if d.endswith(line)], f"neo4j log line missing: {line}")
            for line in cut:
                self.assertFalse([d for d in neo if d.endswith(line)], f"more than 50 log lines: {line}")
            self.assertTrue([d for d in neo if "java.lang.OutOfMemoryError: Java heap space" in d],
                            "neo4j's last log line (its last words) is printed")
        with self.subTest(container="exited, OOM-killed, no healthcheck (worker)"):
            for field, value in (("State.Status", "exited"), ("State.ExitCode", "137"),
                                 ("State.OOMKilled", "true"), ("State.Health.Status", "<absent>"),
                                 ("State.Health.Log", "<absent>")):
                self._has_state(worker, field, value)
            for line in ("worker starting", "::error::worker last words", "::warning::forged"):
                self.assertTrue([d for d in worker if line in d], f"worker log line missing: {line}")
        with self.subTest(check="logs calls"):
            logs = [a for a in self._diag_calls(records) if a[:1] == ["compose"]]
            services = sorted(a[-1] for a in logs)
            self.assertEqual(services, ["neo4j", "worker"], "logs of the non-healthy services only (U9d-1)")
            for a in logs:
                self.assertTrue(("--tail", "50") in self._pairs(a) or "--tail=50" in a, f"--tail 50: {a}")
                self.assertFalse({"-f", "--follow"} & set(a), f"a following logs call never returns: {a}")
        with self.subTest(check="every line prefixed; nothing private; control characters"):
            for line in result.stdout.splitlines():
                self.assertTrue(line.startswith(("offline-client: ")), f"an unprefixed stdout line: {line!r}")
            self.assertNotIn(U9D_SECRET, out, "a secret from Config.Env, Args, Mounts or a label was printed")
            self.assertNotIn("com.example.secret", out, "a label other than the service name was printed")
            self.assertNotIn("\x1b", out, "a control character reached the log (design item 10)")
            for line in diag:
                self.assertIsNone(U9D_BANNED.search(line), f"a diag line uses a gate word: {line}")
        with self.subTest(check="C2 with the diagnostic"):
            lines = result.stdout.splitlines()
            self._point(lines, U9D_CM, "C1")
            _, c2_end, c2 = self._point(lines, U9D_CM, "C2")
            self._assert_client_figures(c2, "C2", root)
            self.assertLess(c2_end, lines.index(U9D_DIAG + diag[0]), "C2 comes before the diagnostic")
            self._no_point(lines, U9D_CM, "C3")

    def test_offline_client_diag_survives_a_failing_inspect(self):
        """U9d-1: a diagnostic command that fails prints a named `diag:` line;
        the other blocks still print and the client still exits non-zero."""
        with self.subTest(case="the first container inspect fails"):
            result, _, _ = self._launch_failure(FAKE_DOCKER_FAIL_NTH="inspect#1")
            out = self._out(result)
            self.assertEqual(result.returncode, 7, out)
            diag = self._diag_block(result.stdout)
            self.assertTrue([line for line in diag if re.search(r"inspect\b.*\bexit 1\b", line)],
                            "no named line for the failing inspect:\n" + "\n".join(diag))
            blocks = self._containers(diag)
            with_state = [n for n, b in blocks.items() if [line for line in b if "State.Status:" in line]]
            self.assertEqual(len(with_state), len(U9D_CONTAINERS) - 1, "the other blocks still print")
            failed = next(n for n in blocks if n not in with_state)
            svc = next(c["Labels"]["com.docker.compose.service"] for c in U9D_CONTAINERS if c["Names"] == failed)
            self.assertTrue([line for line in blocks[failed] if U9D_LOG_MARK[svc] in line],
                            f"{failed}: an unreadable container's logs still print (design item 7)")
        with self.subTest(case="the container list fails"):
            result, _, _ = self._launch_failure(FAKE_DOCKER_FAIL="label=com.docker.compose.project")
            self.assertEqual(result.returncode, 7, self._out(result))
            diag = self._diag_block(result.stdout)
            self.assertTrue([line for line in diag if re.search(r"(?:cannot list|\bps\b).*\bexit 1\b", line)],
                            "no named line for the failing container list:\n" + "\n".join(diag))
        with self.subTest(case="a logs call fails"):
            logs = {k: v for k, v in U9D_LOGS.items() if k != "worker"}
            result, _, _ = self._launch_failure(FAKE_COMPOSE_LOGS=json.dumps(logs))
            self.assertEqual(result.returncode, 7, self._out(result))
            diag = self._diag_block(result.stdout)
            self.assertTrue([line for line in diag if re.search(r"logs\b.*\bexit 1\b", line)],
                            "no named line for the failing logs call:\n" + "\n".join(diag))
            self.assertEqual(len(self._containers(diag)), len(U9D_CONTAINERS))

    def test_offline_measure_points_on_a_pass(self):
        """U9d-2, U9d-4: C1 after install and before launch, C3 after smoke and
        before teardown, no C2 and no diagnostic call; H1 after dind up, H3
        after the client run. Every figure carries its unit."""
        result, records, root = self._client_u9d()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        lines = result.stdout.splitlines()
        with self.subTest(half="client"):
            c1_start, c1_end, c1 = self._point(lines, U9D_CM, "C1")
            c3_start, c3_end, c3 = self._point(lines, U9D_CM, "C3")
            self._no_point(lines, U9D_CM, "C2")
            self.assertLess(lines.index("offline-client: install"), c1_start, "C1 comes after install")
            self.assertLess(c1_end, lines.index("offline-client: launch"), "C1 comes before launch")
            self.assertLess(lines.index("offline-client: smoke (ci/offline included)"), c3_start, "C3 after smoke")
            self.assertLess(c3_end, lines.index("offline-client: teardown"), "C3 comes before teardown")
            self._assert_client_figures(c1, "C1", root)
            self._assert_client_figures(c3, "C3", root)
            self.assertEqual([line for line in lines if line.startswith(U9D_DIAG)], [], "a diag line on a pass")
            self.assertEqual(self._diag_calls(records), [], "an inspect, ps or logs call on a pass (U9d-4)")
            calls = self._measure_calls(records)
            install, launch = self._stub_at(records, "install.sh"), self._stub_at(records, "launch.sh")
            smoke, teardown = self._stub_at(records, "smoke.sh"), self._stub_at(records, "teardown.sh")
            self.assertTrue([i for i in calls if install < i < launch], "no measurement between install and launch")
            self.assertTrue([i for i in calls if smoke < i < teardown], "no measurement between smoke and teardown")
            self.assertEqual([i for i in calls if not (install < i < launch or smoke < i < teardown)], [],
                             "a measurement outside C1 and C3 on a pass")
            for r in records:
                if r["argv"][:2] == ["system", "df"]:
                    self.assertFalse({"-v", "--verbose"} & set(r["argv"]), "`docker system df -v` (U9d-3)")
        for case, on_host in (("DockerRootDir not on this host", False), ("DockerRootDir on this host", True)):
            with self.subTest(half="host", case=case):
                env = {}
                if on_host:
                    root_dir = self.tmp / "docker-root"
                    root_dir.mkdir(exist_ok=True)
                    env["FAKE_DOCKER_ROOT_DIR"] = str(root_dir)
                result, _, _ = self._host(**env)
                self.assertEqual(result.returncode, 0, self._out(result))
                lines = result.stdout.splitlines()
                h1_start, h1_end, h1 = self._point(lines, U9D_HM, "H1")
                h3_start, h3_end, h3 = self._point(lines, U9D_HM, "H3")
                self._no_point(lines, U9D_HM, "H2")
                self.assertLess(lines.index("offline: df after dind up"), h1_start, "H1 comes after dind up")
                self.assertLess(h1_end, lines.index("offline: running the offline client"))
                self.assertLess(lines.index("offline: running the offline client"), h3_start)
                self.assertLess(h3_end, lines.index("offline: df after client run"), "H3 after the client run")
                for point, block in (("H1", h1), ("H3", h3)):
                    mem = [line for line in block if line.startswith(f"{U9D_HM}{point} memory")]
                    self.assertEqual(len(mem), 1, f"{point}: one memory line: {block}")
                    if on_host:
                        self.assertRegex(mem[0], r"MemAvailable \d+ kB\b.*\bSwapFree \d+ kB\b")
                    else:
                        self.assertIn("not measurable", mem[0], "the daemon's memory is not this host's")
                        self.assertNotRegex(mem[0], r"MemAvailable \d", "a figure from the wrong machine")

    def test_offline_measure_points_on_a_launch_failure(self):
        """U9d-2, U9d-1 scope: a launch failure prints C1 and C2, no C3; the host
        prints H1 and H2, H2 before the unchanged FAIL line; a failure at any
        other step prints no diagnostic."""
        with self.subTest(case="client, launch fails"):
            result, records, root = self._client_u9d(FAKE_STUB_FAIL="launch.sh")
            self.assertEqual(result.returncode, 7, self._out(result))
            lines = result.stdout.splitlines()
            c1_start, c1_end, _ = self._point(lines, U9D_CM, "C1")
            c2_start, c2_end, c2 = self._point(lines, U9D_CM, "C2")
            self._no_point(lines, U9D_CM, "C3")
            self.assertLess(lines.index("offline-client: install"), c1_start)
            self.assertLess(c1_end, lines.index("offline-client: launch"))
            self.assertLess(lines.index("offline-client: launch"), c2_start, "C2 is taken after the failure")
            self._assert_client_figures(c2, "C2", root)
            diag = [i for i, line in enumerate(lines) if line.startswith(U9D_DIAG)]
            self.assertTrue(diag and c2_end < diag[0], "C2, then the diagnostic (design item 8)")
            launch = self._stub_at(records, "launch.sh")
            self.assertTrue([i for i in self._measure_calls(records) if i > launch], "no C2 measurement")
        for case, extra, points in (
                ("smoke fails", {"FAKE_STUB_FAIL": "smoke.sh"}, ["C1"]),
                ("teardown fails", {"FAKE_STUB_FAIL": "teardown.sh"}, ["C1", "C3"]),
                ("the image names differ", {"FAKE_DOCKER_LS_AFTER": json.dumps(AS_SET[:-1])}, ["C1", "C3"]),
                ("the daemon is not clean", {"FAKE_DOCKER_LS_BEFORE": json.dumps(["leftover/img:1"])}, [])):
            with self.subTest(case=f"client, {case}"):
                result, records, _ = self._client_u9d(**extra)
                self.assertNotEqual(result.returncode, 0, self._out(result))
                lines = result.stdout.splitlines()
                for point in ("C1", "C2", "C3"):
                    if point in points:
                        self._point(lines, U9D_CM, point)
                    else:
                        self._no_point(lines, U9D_CM, point)
                self.assertEqual([line for line in lines if line.startswith(U9D_DIAG)], [],
                                 "a diagnostic outside the launch step (QD-5: launch only)")
                self.assertEqual(self._diag_calls(records), [])
        with self.subTest(case="host, the client fails (merged streams)"):
            result, _, _ = self._host_merged(FAKE_DOCKER_FAIL="offline-client")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            lines = result.stdout.splitlines()
            _, h1_end, _ = self._point(lines, U9D_HM, "H1")
            h2_start, h2_end, _ = self._point(lines, U9D_HM, "H2")
            self._no_point(lines, U9D_HM, "H3")
            run = lines.index("offline: running the offline client")
            self.assertLess(h1_end, run)
            self.assertLess(run, h2_start)
            fail = lines.index(U9D_FAIL_LINE)
            self.assertLess(h2_end, fail, "H2 comes before the FAIL line (U9d-2)")
            self.assertEqual(lines[fail + 1], "offline: df before teardown",
                             "the FAIL line is followed by the existing df lines and the teardown")
        with self.subTest(case="host, the client fails (stderr apart)"):
            result, _, _ = self._host(FAKE_DOCKER_FAIL="offline-client")
            self.assertEqual(result.stderr.splitlines(),
                             ["fake docker: failing on 'offline-client'", U9D_FAIL_LINE],
                             "the host's stderr on a client failure is unchanged, FAIL line byte for byte")

    def test_offline_measure_never_changes_the_outcome(self):
        """U9d-2: every measurement source failing (df, the meminfo file,
        `docker system df`) prints named `measure:` lines; a pass stays a pass
        with the same output, and a launch failure keeps launch's status."""
        sources = {"FAKE_DF_FAIL": "1", "KE_OFFLINE_MEMINFO": str(self.tmp / "no-such-meminfo"),
                   "FAKE_DOCKER_FAIL": "system df"}
        for case, extra in (("every source fails", sources),
                            ("meminfo without MemAvailable or SwapFree",
                             {"KE_OFFLINE_MEMINFO": str(self._u9d_meminfo("MemTotal: 16384000 kB\n", "short"))})):
            with self.subTest(case=case):
                result, _, root = self._client_u9d(**extra)
                self.assertEqual(result.returncode, 0, "a failed measurement changed a pass:\n" + self._out(result))
                lines = result.stdout.splitlines()
                self.assertEqual([line for line in lines if not line.startswith(U9D_CM)], U9D_CLIENT_PASS,
                                 "a pass with failing measurements prints the same lines otherwise")
                for point in ("C1", "C3"):
                    _, _, block = self._point(lines, U9D_CM, point)
                    p = f"{U9D_CM}{point} "
                    wanted = {"memory": rf"{re.escape(p)}memory\b.*not measured"}
                    if extra is sources:
                        wanted.update({"df /": rf"{re.escape(p)}df /[ :(].*not measured",
                                       "df /install": rf"{re.escape(p)}df {re.escape(str(root))}\b.*not measured",
                                       "system df": rf"{re.escape(p)}.*system df\b.*not measured"})
                    for source, rx in wanted.items():
                        self.assertEqual(len([line for line in block if re.match(rx, line)]), 1,
                                         f"{point}: no named `not measured` line for {source}: {block}")
        with self.subTest(case="every source fails on a launch failure"):
            result, _, _ = self._launch_failure(**sources)
            self.assertEqual(result.returncode, 7, self._out(result))
            lines = result.stdout.splitlines()
            self._point(lines, U9D_CM, "C2")
            self.assertEqual(len(self._containers(self._diag_block(result.stdout))), len(U9D_CONTAINERS))

    def test_offline_check_output_unchanged_but_for_measure_lines(self):
        """U9d-5 control: a run's output with the `measure:` lines removed is
        the pre-U9d sequence (captured at RED from the unchanged script;
        project names, image references, df rows, the tmp dir and checker
        detail normalised). Green at RED by construction."""
        with self.subTest(run="client pass"):
            result, _, _ = self._client()
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertEqual([line for line in result.stdout.splitlines() if not line.startswith(U9D_CM)],
                             U9D_CLIENT_PASS)
            self.assertEqual(result.stderr, "")
        with self.subTest(run="host pass"):
            result, _, _ = self._host()
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertEqual(_u9d_normalise(result.stdout, self.tmp), U9D_HOST_PASS)
            self.assertEqual(result.stderr, "")
        with self.subTest(run="host, the client fails"):
            result, _, _ = self._host(FAKE_DOCKER_FAIL="offline-client")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_u9d_normalise(result.stdout, self.tmp), U9D_HOST_CLIENT_FAILS)

    # ---- U9d static rows -----------------------------------------------------

    def test_offline_check_has_no_ci_only_branch(self):
        """U9d-3: the diagnostic and the measurements run the same everywhere;
        no branch on CI, GITHUB_* or RUNNER_* (comments excluded)."""
        self._require_script()
        body = _u9d_code()
        for rx in (r"\$\{?CI\b", r"\bCI\b", r"\bGITHUB_[A-Z_]*", r"\bRUNNER_[A-Z_]*"):
            with self.subTest(pattern=rx):
                self.assertNotRegex(body, rx, "offline_check.sh branches on a runner variable")

    def test_offline_diag_and_measure_docker_calls_are_bounded(self):
        """U9d-4: every docker call of the diagnostic and the measurements
        (`ps`, `container inspect`, `compose logs`, `system df`) runs as
        `timeout <N> docker ...` with N <= 30, as the pull probe does.
        U9d-4 as amended (O-23; A2, A8, A9): the event stream runs as
        `timeout 900 docker events` with exactly the stack's container
        die/oom/kill filters, a `--since` and `--format "$events_fmt"`."""
        self._require_script()
        found: dict[str, list[re.Match]] = {k: [] for k in U9D_KINDS}
        for m in U9D_DOCKER_CALL.finditer(_u9d_code()):
            for kind, rx in U9D_KINDS.items():
                if re.match(rx, m.group("rest")):
                    found[kind].append(m)
        for kind, calls in found.items():
            with self.subTest(call=kind):
                self.assertTrue(calls, f"offline_check.sh has no `docker {kind}` call (U9d-1, U9d-2)")
                for m in calls:
                    self.assertEqual(m.group("timeout"), "timeout", f"unbounded: docker {m.group('rest')}")
                    if kind == "events":
                        self._assert_events_call(m)
                        continue
                    self.assertLessEqual(int(m.group("secs")), 30, f"over 30 s: {m.group(0)}")
                    if kind == "system df":
                        self.assertNotRegex(m.group("rest"), r"\s(?:-v|--verbose)\b", "summary form only (U9d-3)")

    def test_offline_diag_template_prints_only_allowed_fields(self):
        """U9d-1 never-printed list, design item 10: the inspect template is the
        State-only template, and the client half names no Config, Mounts,
        Args, Path, HostConfig or NetworkSettings field, no `{{json .}}`, no
        inspect without --format and no `compose config`. Amended (O-23; A2,
        A7, A9): the event format is the design's (`fake_docker.EVENTS_FORMAT`:
        time, action, name, exitCode, signal), the client half reads no
        attribute map, `.Actor.ID` or `--until`, and has one `docker events`
        call."""
        self._require_script()
        _, client, _ = _u9d_halves()
        m = re.search(r"'([^']*\{\{\s*\.State\.Status\s*\}\}[^']*)'", client)
        self.assertIsNotNone(m, "the client half holds no inspect template with {{.State.Status}} (U9d-1)")
        assert m is not None
        self.assertEqual(m.group(1), fake_docker.DIAG_TEMPLATE, "the template is the design's (item 7)")
        code = _u9d_strip(client)
        for token in ("json .}}", ".Config", ".Mounts", ".Args", ".Path", ".HostConfig", ".NetworkSettings",
                      "compose config", "--verbose"):
            with self.subTest(token=token):
                self.assertNotIn(token, code, f"the client half reads {token} (never printed, U9d-1)")
        for call in U9D_DOCKER_CALL.finditer(code):
            if re.match(U9D_KINDS["container inspect"], call.group("rest")):
                self.assertIn("--format", call.group("rest"), f"inspect without --format: {call.group(0)}")
        with self.subTest(check="the event format (O-23, A2, A7)"):
            fmt = re.search(r"(?m)^\s*events_fmt='([^']*)'", client)
            self.assertIsNotNone(fmt, "the client half defines no events_fmt (A2)")
            assert fmt is not None
            self.assertEqual(fmt.group(1), fake_docker.EVENTS_FORMAT,
                             "the event format is the design's: time, action, name, exitCode, signal (A2)")
        for token in (".Actor.Attributes}}", "json .Actor", ".Actor.ID", "--until"):
            with self.subTest(token=token):
                self.assertNotIn(token, code, f"the client half reads {token} (an event prints five fields only; "
                                 "no history query, A7)")
        with self.subTest(check="one docker events call (A2, A7)"):
            events = [c for c in U9D_DOCKER_CALL.finditer(code) if re.match(U9D_KINDS["events"], c.group("rest"))]
            self.assertEqual(len(events), 1, "exactly one `docker events` call: no second, history call (A7)")

    def test_offline_measure_and_diag_lines_use_neutral_words(self):
        """Design item 11: every new line starts with `offline-client: measure:`,
        `offline-client: diag:` or `offline: measure:`, and none says pass,
        skip, FAIL, inconclusive, "not clean" or "nothing was pulled"."""
        self._require_script()
        say = re.compile(r"(?:^|[;&|]|\b(?:then|else|do)\b)\s*(?:m|diag)\s+\"")
        lines = [line for line in _u9d_code().splitlines()
                 if re.search(r"offline(?:-client)?: (?:measure|diag):", line) or say.search(line)]
        for prefix in ("offline-client: measure:", "offline-client: diag:", "offline: measure:"):
            with self.subTest(prefix=prefix):
                self.assertTrue([line for line in lines if prefix in line], f"offline_check.sh prints no `{prefix}` line")
        for line in lines:
            with self.subTest(line=line.strip()):
                self.assertIsNone(U9D_BANNED.search(line), "a new line uses a gate word")

    def test_offline_meminfo_seam_is_client_only(self):
        """Ruling O-22 (3), design item 6: KE_OFFLINE_MEMINFO is a client-only
        test seam, listed in the header; the host half reads /proc/meminfo."""
        self._require_script()
        header, client, host = _u9d_halves()
        self.assertIn("KE_OFFLINE_MEMINFO", header, "the header lists the test seam")
        self.assertIn("KE_OFFLINE_MEMINFO", _u9d_strip(client), "the client half reads the seam")
        self.assertNotIn("KE_OFFLINE_MEMINFO", _u9d_strip(host), "the host half reads no seam")
        self.assertIn("/proc/meminfo", _u9d_strip(host), "the host half reads /proc/meminfo (H-points)")

    # ---- U9d rework 1 (O-23) -------------------------------------------------
    # Criteria: docs/requirements.md "U9d precision" U9d-1, U9d-4, U9d-6 as
    # amended 2026-10-30 (O-23). Design: design-notes "Amendment, rework 1
    # (O-23)" A1-A3, A7-A9, and the O-23 precision folding in security L-1,
    # L-2 and I-1 (u9d/security.md). Fake knobs: tests/fake_docker.py
    # "platform-sbom U9d rework 1" and the stub's FAKE_STUB_WAIT_* (_STUB).
    # Tester, U9d rework-1 RED. Re-pinned rows (A9): the bounded-calls row and
    # the allowed-fields row above.

    def _restarted_failure(self, events: list[dict[str, Any]] | None,
                           containers: list[dict[str, Any]] | None = None,
                           **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        """A launch failure whose launch stub returns only once the event
        stream is up (A9), so the kill never races the fake's start."""
        env = {"FAKE_DOCKER_CONTAINERS": json.dumps(containers or _u9d_restarted()),
               "FAKE_STUB_WAIT_NAME": "launch.sh", "FAKE_STUB_WAIT_FOR": U9D_EVENTS_READY}
        if events is not None:
            env["FAKE_DOCKER_EVENTS"] = json.dumps(events)
        env.update(extra)
        return self._launch_failure(**env)

    @staticmethod
    def _event_lines(diag: list[str]) -> list[tuple[int, str]]:
        """(index, event) of each `events | <event>` line of the diagnostic (A3)."""
        return [(k, m.group(1)) for k, line in enumerate(diag) if (m := re.fullmatch(r"\s*events \| (.*)", line))]

    @staticmethod
    def _first_container(diag: list[str]) -> int:
        return next((k for k, line in enumerate(diag) if line.startswith("container ")), len(diag))

    def _all_prefixed(self, result: subprocess.CompletedProcess) -> None:
        for line in result.stdout.splitlines():
            self.assertTrue(line.startswith("offline-client: "), f"an unprefixed stdout line: {line!r}")

    def _assert_events_call(self, m: re.Match) -> None:
        rest = m.group("rest")
        self.assertEqual(int(m.group("secs")), 900, f"the stream is bounded by `timeout 900` (A2, A8): {m.group(0)}")
        filters = sorted(f.strip("'\"") for f in re.findall(r"--filter(?:=|\s+)(\S+)", rest))
        self.assertEqual(filters, sorted(U9D_EVENT_FILTERS),
                         f"exactly the stack's container die, oom and kill filters (A2): {rest}")
        self.assertRegex(rest, r"--since(?:=|\s+)\S", f"`--since` the stream's start (A2): {rest}")
        self.assertIn('--format "$events_fmt"', rest, f"the fixed event format (A2, A7): {rest}")
        self.assertNotIn("--until", rest, "a history query (A7)")

    def test_offline_diag_names_the_deaths_of_a_restarted_container(self):
        """U9d-1 as amended (O-23), A1-A3, A9: a neo4j that Docker restarted
        reads `running / 0 / false`; its block gives RestartCount, StartedAt,
        FinishedAt and State.Error, and the events section, printed first,
        gives each death's own lines from a stream started before launch and
        killed when launch exited, before any diagnostic call. Of an event,
        only the time, action, name, exitCode and signal print."""
        neo4j = "knowledge-engine-neo4j-1"
        with self.subTest(case="an oom kill, then a restart"):
            result, records, _ = self._restarted_failure([_u9d_event("oom"), _u9d_event("die", exitCode="137")])
            out = self._out(result)
            self.assertEqual(result.returncode, 7, "the client exits with launch's own status:\n" + out)
            self._all_prefixed(result)
            diag = self._diag_block(result.stdout)
            neo = self._containers(diag)[neo4j]
            for field, value in (("State.Status", "running"), ("State.ExitCode", "0"), ("State.OOMKilled", "false"),
                                 ("RestartCount", "1"), ("State.StartedAt", U9D_RESTARTED_STATE["StartedAt"]),
                                 ("State.FinishedAt", U9D_RESTARTED_STATE["FinishedAt"]),
                                 ("State.Error", "<absent>")):
                self._has_state(neo, field, value)
            events = self._event_lines(diag)
            self.assertEqual([e for _, e in events], [f"{U9D_EVENT_TIME} oom {neo4j} exitCode= signal=",
                                                      f"{U9D_EVENT_TIME} die {neo4j} exitCode=137 signal="],
                             "the death's oom and die events, one `events | ` line each (A2, A3):\n" + "\n".join(diag))
            first = self._first_container(diag)
            for k, _ in events:
                self.assertTrue(0 < k < first, "the events print after the diagnostic's first line and before the "
                                "first container block (A3):\n" + "\n".join(diag))
            self.assertEqual([line for line in diag if re.search(r"\bevents:.*\bended\b", line)], [],
                             "the stream still ran at launch's exit: no `ended` line (A3)")
            self.assertEqual([line for line in diag if re.fullmatch(r"\s*events: none", line)], [])
            stopped = [i for i, r in enumerate(records) if r["argv"] == ["EVENTS", "stopped"]]
            ps = [i for i, r in enumerate(records) if r["argv"][:1] == ["ps"]]
            self.assertEqual(len(stopped), 1, "the stream was not killed when launch exited (A2 events_stop)")
            self.assertTrue(ps and stopped[0] < ps[0], "the stream is stopped before the first diagnostic call (A2)")
            for leak in (U9D_SECRET, U9D_EVENT_IMAGE, U9D_EVENT_ACTOR):
                self.assertNotIn(leak, out, "an event field other than time, action, name, exitCode and signal "
                                 "printed (A7)")
        with self.subTest(case="a crash (a die with no oom)"):
            result, _, _ = self._restarted_failure([_u9d_event("die", exitCode="1")])
            self.assertEqual(result.returncode, 7, self._out(result))
            diag = self._diag_block(result.stdout)
            self.assertEqual([e for _, e in self._event_lines(diag)],
                             [f"{U9D_EVENT_TIME} die {neo4j} exitCode=1 signal="],
                             "one die line with the process's own exit code and no oom line (A6):\n" + "\n".join(diag))
        with self.subTest(case="more events than the cap"):
            many = [_u9d_event("die", time=U9D_EVENT_TIME + i, exitCode=str(i)) for i in range(130)]
            result, _, _ = self._restarted_failure(many)
            self.assertEqual(result.returncode, 7, self._out(result))
            diag = self._diag_block(result.stdout)
            events = self._event_lines(diag)
            self.assertEqual([e for _, e in events],
                             [f"{U9D_EVENT_TIME + i} die {neo4j} exitCode={i} signal=" for i in range(100)],
                             "the first 100 events, in stream order (A3)")
            cap = [k for k, line in enumerate(diag) if re.match(r"\s*events: 30 more lines not printed\b", line)]
            self.assertEqual(len(cap), 1, "a named line gives the 30 events not printed (A3):\n" + "\n".join(diag))
            self.assertTrue(events[-1][0] < cap[0] < self._first_container(diag), "the cap line follows the 100 lines")
        with self.subTest(case="a start error and a never-started container"):
            never = {"Status": "created", "ExitCode": 0, "OOMKilled": False, "StartedAt": U9D_ZERO_TIME,
                     "FinishedAt": U9D_ZERO_TIME, "Error": ""}
            failed = {"Status": "exited", "ExitCode": 128, "OOMKilled": False, "StartedAt": "2026-10-30T10:00:40.1Z",
                      "FinishedAt": "2026-10-30T10:00:47.9Z", "Error": U9D_START_ERROR}
            containers = [_u9d_container("a", "postgres", never), _u9d_restarted()[1],
                          dict(_u9d_container("c", "worker", failed), RestartCount=3)]
            result, _, _ = self._restarted_failure([], containers)
            self.assertEqual(result.returncode, 7, self._out(result))
            self._all_prefixed(result)
            diag = self._diag_block(result.stdout)
            blocks = self._containers(diag)
            with self.subTest(container="start error (worker)"):
                worker = blocks["knowledge-engine-worker-1"]
                self._has_state(worker, "State.Error", json.dumps(U9D_START_ERROR))
                self._has_state(worker, "RestartCount", "3")
                self.assertEqual(len([line for line in result.stdout.splitlines() if "no space left" in line]), 1,
                                 "the start error is one JSON-quoted line; its CR never reaches the log raw (A1)")
            with self.subTest(container="never started (postgres)"):
                pg = blocks["knowledge-engine-postgres-1"]
                for field, value in (("State.StartedAt", "<absent>"), ("State.FinishedAt", "<absent>"),
                                     ("RestartCount", "0"), ("State.Error", "<absent>")):
                    self._has_state(pg, field, value)
            with self.subTest(check="no event"):
                self.assertEqual(len([line for line in diag if re.fullmatch(r"\s*events: none", line)]), 1,
                                 "a stream with no event prints `events: none` (A3):\n" + "\n".join(diag))
        with self.subTest(case="the stream ended before launch exited"):
            result, _, _ = self._restarted_failure([_u9d_event("die", exitCode="137")], FAKE_DOCKER_FAIL="event=oom",
                                                   FAKE_STUB_WAIT_FOR=U9D_EVENTS_CALLED, FAKE_STUB_WAIT_THEN="1")
            self.assertEqual(result.returncode, 7, self._out(result))
            diag = self._diag_block(result.stdout)
            ended = [line for line in diag
                     if re.match(r"\s*events: the stream ended before launch exited \(exit 1\b", line)]
            self.assertEqual(len(ended), 1, "a named line for a stream that ended early (A3):\n" + "\n".join(diag))
            blocks = self._containers(diag)
            self.assertEqual(len([n for n, b in blocks.items() if [line for line in b if "State.Status:" in line]]),
                             len(U9D_CONTAINERS), "the container blocks still print")

    def test_offline_events_stream_is_stopped_and_silent_on_a_pass(self):
        """U9d-1 as amended (O-23), A2, A3, A8: on a passing launch the stream
        starts after install and before launch, is killed after launch exits
        and before smoke, and nothing of it prints: the output is the pre-U9d
        pass but for the measure lines, and stderr is empty."""
        result, records, _ = self._client_u9d(
            FAKE_DOCKER_EVENTS=json.dumps([_u9d_event("oom"), _u9d_event("die", exitCode="137")]),
            FAKE_STUB_WAIT_NAME="launch.sh", FAKE_STUB_WAIT_FOR=U9D_EVENTS_READY)
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        lines = result.stdout.splitlines()
        self.assertEqual([line for line in lines if "events" in line or line.startswith(U9D_DIAG)], [],
                         "an events or diag line on a pass (A3)")
        self.assertNotIn(str(U9D_EVENT_TIME), out, "an event printed on a pass")
        self.assertEqual([line for line in lines if not line.startswith(U9D_CM)], U9D_CLIENT_PASS)
        self.assertEqual(result.stderr, "")
        calls = [i for i, r in enumerate(records) if r["argv"][:1] == ["events"]]
        self.assertEqual(len(calls), 1, "one `docker events` call (A2)")
        install, launch = self._stub_at(records, "install.sh"), self._stub_at(records, "launch.sh")
        smoke = self._stub_at(records, "smoke.sh")
        self.assertTrue(install < calls[0] < launch, "the stream starts after install and before launch (A2)")
        stopped = [i for i, r in enumerate(records) if r["argv"] == ["EVENTS", "stopped"]]
        self.assertEqual(len(stopped), 1, "the stream was not killed when launch exited (A2 events_stop)")
        self.assertTrue(launch < stopped[0] < smoke, "the stream is stopped after launch and before smoke (A2)")

    def test_offline_diag_sanitises_container_names_and_service_labels(self):
        """Security L-1 (O-23 precision): a container name and a service label
        from `docker ps` print through the control-character sanitiser; logs
        are fetched only for a label that is a compose service name
        (`^[A-Za-z0-9][A-Za-z0-9._-]*$`), passed after `--`, so a label can
        neither forge a runner line nor become a `compose logs` option."""
        exited = {"Status": "exited", "ExitCode": 1, "OOMKilled": False}
        odd = _u9d_container("d", "odd", exited)
        odd["Names"] = U9D_ODD_NAME
        odd["Labels"]["com.docker.compose.service"] = U9D_ODD_LABEL
        follow = _u9d_container("e", "follow", exited)
        follow["Labels"]["com.docker.compose.service"] = "--follow"
        logs = {"worker": U9D_LOGS["worker"], "--follow": ["follow-log-marker"], U9D_ODD_LABEL: ["odd-log-marker"]}
        result, records, _ = self._launch_failure(FAKE_DOCKER_CONTAINERS=json.dumps([odd, follow, U9D_CONTAINERS[2]]),
                                                  FAKE_COMPOSE_LOGS=json.dumps(logs))
        out = self._out(result)
        self.assertEqual(result.returncode, 7, out)
        self._all_prefixed(result)
        self.assertNotIn("\x1b", out, "a control character from a name or label reached the log")
        diag = self._diag_block(result.stdout)
        for text, what in ((U9D_ODD_NAME_SHOWN, "the container name"), (U9D_ODD_LABEL_SHOWN, "the service label")):
            self.assertTrue([line for line in diag if text in line],
                            f"{what} prints with its control characters as `?`:\n" + "\n".join(diag))
        calls = [r["argv"] for r in records if r["argv"][:1] == ["compose"] and "logs" in r["argv"]]
        self.assertEqual([a[-1] for a in calls], ["worker"], "logs only for a label that is a compose service name")
        for a in calls:
            self.assertEqual(a[-2], "--", f"the service name is passed after `--`: {a}")
            self.assertFalse({"-f", "--follow"} & set(a[:-2]), f"a label became a logs option: {a}")
        self.assertNotIn("follow-log-marker", out)
        self.assertNotIn("odd-log-marker", out)
        heads = [k for k, line in enumerate(diag) if line.startswith("container ")]
        for name in (U9D_ODD_NAME_SHOWN, "knowledge-engine-follow-1"):
            with self.subTest(container=name):
                k = next((k for k in heads if diag[k].startswith(f"container {name} ")), None)
                self.assertIsNotNone(k, f"no block for {name}:\n" + "\n".join(diag))
                assert k is not None
                end = next((j for j in heads if j > k), len(diag))
                self.assertTrue([line for line in diag[k:end] if "no logs" in line],
                                f"{name}: a named `no logs` line for a label that is not a service name")

    def test_offline_printed_lines_neutralise_runner_markers(self):
        """Security L-2 (O-23 precision): `##[` anywhere in a printed diag or
        measure line is rewritten to `#?[`, so the runner's legacy parser sees
        no marker: probe output, a log line, State.Error, an event line (its
        CR and ESC as `?`) and a `docker system df` row."""
        neo_state = dict(U9D_RESTARTED_STATE, Health={"Status": "starting", "Log": [
            {"End": "2026-10-30 10:00:55.5 +0000 UTC", "ExitCode": 1, "Output": "x ##[section]probe-marker"}]})
        worker_state = {"Status": "exited", "ExitCode": 1, "OOMKilled": False, "Error": "start ##[error]error-marker"}
        containers = [U9D_CONTAINERS[0], dict(_u9d_container("b", "neo4j", neo_state), RestartCount=1),
                      _u9d_container("c", "worker", worker_state)]
        logs = dict(U9D_LOGS, worker=["##[add-mask]logs-marker"])
        system_df = [dict(U9D_SYSTEM_DF[0], Type="Images ##[group]df-marker"), *U9D_SYSTEM_DF[1:]]
        result, _, _ = self._restarted_failure([_u9d_event("die", name="ev\r##[warning]event-marker\x1b[0m",
                                                           exitCode="137")], containers,
                                               FAKE_COMPOSE_LOGS=json.dumps(logs),
                                               FAKE_DOCKER_SYSTEM_DF=json.dumps(system_df))
        out = self._out(result)
        self.assertEqual(result.returncode, 7, out)
        self.assertNotIn("##[", out, "a `##[` marker reached the log")
        for source, marker in (("Health.Log output", "#?[section]probe-marker"),
                               ("a log line", "#?[add-mask]logs-marker"),
                               ("State.Error", "#?[error]error-marker"), ("a system df row", "#?[group]df-marker")):
            with self.subTest(source=source):
                self.assertTrue([line for line in result.stdout.splitlines()
                                 if line.startswith("offline-client: ") and marker in line],
                                f"{source}: `##[` printed as `#?[`:\n" + result.stdout)
        with self.subTest(source="an event line"):
            events = self._event_lines(self._diag_block(result.stdout))
            self.assertEqual([e for _, e in events], [f"{U9D_EVENT_TIME} die ev?#?[warning]event-marker?[0m "
                                                      "exitCode=137 signal="],
                             "an event line goes through the same sanitiser (A3)")

    def test_offline_meminfo_read_is_bounded(self):
        """Security I-1 (O-23 precision): meminfo_line reads at most 64 KiB
        (`timeout 5 head -c 65536`), so a huge KE_OFFLINE_MEMINFO cannot stall
        a point: figures past the first 64 KiB are never read, the point prints
        `not measured` within its 5 s bound (U9d-4), and the pass is unchanged."""
        self._require_script()
        with self.subTest(check="the read is bounded (static)"):
            m = re.search(r"(?ms)^meminfo_line\(\) \{.*?^\}", OFFLINE_CHECK.read_text(encoding="utf-8"))
            self.assertIsNotNone(m, "offline_check.sh defines no meminfo_line")
            assert m is not None
            self.assertRegex(m.group(0), r'timeout 5 head -c 65536 -- "\$1"', "meminfo_line reads at most 64 KiB")
        big = self.tmp / "meminfo-large"
        with big.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("Filler: " + "x" * (4 * 1024 * 1024) + " kB\n")
            fh.write("MemAvailable:    1234567 kB\nSwapFree:           2048 kB\n")
        with self.subTest(check="a large meminfo file"):
            result, _, _ = self._client_u9d(KE_OFFLINE_MEMINFO=str(big))
            self.assertEqual(result.returncode, 0, self._out(result))
            lines = result.stdout.splitlines()
            self.assertEqual([line for line in lines if not line.startswith(U9D_CM)], U9D_CLIENT_PASS)
            self.assertNotIn("MemAvailable 1234567", result.stdout, "figures past the first 64 KiB were read (I-1)")
            for point in ("C1", "C3"):
                _, _, block = self._point(lines, U9D_CM, point)
                p = f"{U9D_CM}{point} "
                mem = [line for line in block if re.match(rf"{re.escape(p)}memory\b.*not measured", line)]
                self.assertEqual(len(mem), 1, f"{point}: a named `not measured` memory line: {block}")
                secs = int(block[-1].rsplit(" ", 2)[-2])
                self.assertLessEqual(secs, 5, f"{point} took {secs} s on a large meminfo file (U9d-4: 5 s per point)")


# --------------------------------------------------------------------------
# platform-sbom U9d fixtures and helpers (tester, U9d RED)
# --------------------------------------------------------------------------

U9D_CM = "offline-client: measure: "
U9D_HM = "offline: measure: "
U9D_DIAG = "offline-client: diag: "
U9D_FAIL_LINE = "offline_check: FAIL (the offline client failed (see its output above))"
U9D_BANNED = re.compile(r"(?i:\b(?:pass(?:ed)?|skip(?:ped|ping)?|inconclusive)\b|not clean|nothing was pulled)"
                        r"|\bFAIL\b")
U9D_SECRET = "u9d-sentinel-secret-7f3a9c"
U9D_MEMINFO = ("MemTotal:       16384000 kB\nMemFree:          512000 kB\nMemAvailable:    1234567 kB\n"
               "Buffers:           10000 kB\nSwapTotal:       4194300 kB\nSwapFree:           2048 kB\n")
U9D_DF_TOTAL_KB = 75085112
U9D_ROOT_AVAIL_KB = 47196
U9D_INSTALL_AVAIL_KB = 900000
U9D_SYSTEM_DF = [
    {"Type": "Images", "TotalCount": "7", "Active": "2", "Size": "3.214GB", "Reclaimable": "1.07GB (33%)"},
    {"Type": "Containers", "TotalCount": "3", "Active": "1", "Size": "12.5MB", "Reclaimable": "4.1MB (32%)"},
    {"Type": "Local Volumes", "TotalCount": "4", "Active": "4", "Size": "812.3MB", "Reclaimable": "0B (0%)"},
    {"Type": "Build Cache", "TotalCount": "0", "Active": "0", "Size": "0B", "Reclaimable": "0B"},
]


def _u9d_container(cid: str, svc: str, state: dict[str, Any]) -> dict[str, Any]:
    return {"ID": cid * 64, "Names": f"knowledge-engine-{svc}-1",
            "Labels": {"com.docker.compose.project": "knowledge-engine", "com.docker.compose.service": svc,
                       "com.example.secret": U9D_SECRET},
            "Config": {"Env": [f"NEO4J_AUTH=neo4j/{U9D_SECRET}", "PATH=/usr/bin"]},
            "Args": ["--password", U9D_SECRET], "Path": "/startup/docker-entrypoint.sh",
            "Mounts": [{"Source": f"/srv/{U9D_SECRET}", "Destination": "/data"}], "State": state}


U9D_CONTAINERS = [
    _u9d_container("a", "postgres", {"Status": "running", "ExitCode": 0, "OOMKilled": False, "Health": {
        "Status": "healthy", "Log": [{"End": "2026-10-30 10:00:05.5 +0000 UTC", "ExitCode": 0,
                                      "Output": "/var/run/postgresql:5432 - accepting connections\n"}]}}),
    _u9d_container("b", "neo4j", {"Status": "running", "ExitCode": 0, "OOMKilled": False, "Health": {
        "Status": "unhealthy", "Log": [
            {"End": "2026-10-30 10:00:31.25 +0000 UTC", "ExitCode": 1,
             "Output": "Connection refused\nUnable to connect to localhost:7687"},
            {"End": "2026-10-30 10:00:41.75 +0000 UTC", "ExitCode": 1, "Output": "Connection refused"}]}}),
    _u9d_container("c", "worker", {"Status": "exited", "ExitCode": 137, "OOMKilled": True}),
]
U9D_LOGS = {
    "postgres": ["pg-ok-1 database system is ready to accept connections"],
    "neo4j": [f"neo4j log line {i:02d}" for i in range(1, 56)]
             + ["\x1b[31mjava.lang.OutOfMemoryError: Java heap space\x1b[0m"],
    "worker": ["worker starting", "::error::worker last words\r::warning::forged"],
}
U9D_LOG_MARK = {"postgres": "pg-ok-1", "neo4j": "neo4j log line 55", "worker": "worker starting"}

# The pre-U9d client and host output (captured at RED, 2026-10-30, from the
# unchanged scripts/offline_check.sh under this file's fakes).
U9D_CLIENT_PASS = [
    "offline-client: inner daemon uses the containerd image store",
    "offline-client: a registry pull fails, as expected with no route out",
    "offline-client: install",
    "offline-client: launch",
    "offline-client: smoke (ci/offline included)",
    "offline-client: teardown",
    "offline-client: image names equal the bundle's; nothing was pulled",
]


def _u9d_df(stage: str) -> list[str]:
    return [f"offline: df {stage}", "Filesystem     1024-blocks      Used Available Capacity Mounted on", "<df row>"]


_U9D_HOST_HEAD = [
    *_u9d_df("start"),
    "offline: the daemon's DockerRootDir (<tmp>/no-such-docker-root) is not on this host (Docker Desktop "
    "keeps it in a VM): not measurable, only dist/ is checked",
    "offline: fetching the source sample (scripts/bundle_fetch.sh --set sample)",
    *_u9d_df("after fetch"),
    "offline: pulling the ke-app base (<ref>)",
    "offline: pulling the ke-neo4j base (<ref>)",
    *_u9d_df("after bundle"),
    "sbom_check: drift:",
    "offline: image-side drift check: the ke-app SBOM matches its base (<ref>)",
    *_u9d_df("after drift check"),
    "sbom_check: ke-neo4j:",
    "offline: ke-neo4j check: config equals <ref>; no products/ or fleet-management plugin in its tar or SBOM",
    *_u9d_df("after ke-neo4j check"),
    "offline: starting dind (privileged) in project ke-offline-<N>",
    *_u9d_df("after dind up"),
    "offline: running the offline client",
]
U9D_HOST_PASS = [*_U9D_HOST_HEAD, *_u9d_df("after client run"), *_u9d_df("before teardown"),
                 *_u9d_df("after teardown"), "== offline_check: PASS (<N>s) =="]
U9D_HOST_CLIENT_FAILS = [*_U9D_HOST_HEAD, *_u9d_df("before teardown"), *_u9d_df("after teardown")]


def _u9d_normalise(text: str, tmp: Path) -> list[str]:
    out = []
    for line in text.splitlines():
        if line.startswith((U9D_HM, U9D_CM)):
            continue
        line = line.replace(str(tmp), "<tmp>")
        line = re.sub(r"ke-offline-\d+", "ke-offline-<N>", line)
        line = re.sub(r"[A-Za-z0-9][\w./:-]*@sha256:[0-9a-f]{64}", "<ref>", line)
        line = re.sub(r"^== offline_check: PASS \(\d+s\) ==$", "== offline_check: PASS (<N>s) ==", line)
        line = re.sub(r"^(sbom_check: [^:]+:).*$", r"\1", line)
        if re.match(r"/dev/fake\s", line):
            line = "<df row>"
        out.append(line)
    return out


def _u9d_strip(text: str) -> str:
    """Comment lines dropped, backslash continuations joined."""
    text = text.replace("\\\n", " ")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _u9d_code() -> str:
    return _u9d_strip(OFFLINE_CHECK.read_text(encoding="utf-8"))


def _u9d_halves() -> tuple[str, str, str]:
    """(header comment, client half, host half) of offline_check.sh."""
    text = OFFLINE_CHECK.read_text(encoding="utf-8")
    client = text.index('if [ "${KE_OFFLINE_CLIENT:-}" = 1 ]; then')
    host = text.index("\n# Host half\n")  # the section marker, not the header's "# Host half (...)" line
    if host < client:
        raise AssertionError("offline_check.sh: the host-half section marker precedes the client half")
    return text[:text.index("set -euo pipefail")], text[client:host], text[host:]


# A docker call at a command position (line start, `$(`, after ; & | ! or a
# keyword, past VAR=value words), optionally under `timeout [opts] <N>`. Text
# that mentions docker inside a message is not at a command position.
U9D_DOCKER_CALL = re.compile(
    r"(?:^|\$\(|[;&|!]|\b(?:then|do|else|if|while|until)\b)\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
    r"(?:(?P<timeout>timeout)\s+(?:-\S+\s+)*(?P<secs>\d+)s?\s+)?docker\s+(?P<rest>[^\n]*)", re.M)
U9D_KINDS = {
    "ps": r"(?:ps|container\s+(?:ls|list|ps))\b",
    "container inspect": r"(?:container\s+)?inspect\b",
    "compose logs": r"compose\b.*\blogs\b",
    "system df": r"system\s+df\b",
    "events": r"events\b",  # U9d rework 1 (O-23, A9): its own ceiling, N == 900
}

# platform-sbom U9d rework 1 fixtures (O-23; tester, U9d rework-1 RED)
U9D_EVENT_TIME = 1793354444
U9D_EVENT_IMAGE = "ke-neo4j:u9d-event-image-sentinel"
U9D_EVENT_ACTOR = "f" * 64
U9D_EVENTS_READY = '"argv": ["EVENTS", "ready"]'
U9D_EVENTS_CALLED = '"argv": ["events"'
U9D_EVENT_FILTERS = ("type=container", "label=com.docker.compose.project", "event=die", "event=oom", "event=kill")
U9D_ZERO_TIME = "0001-01-01T00:00:00Z"
U9D_START_ERROR = ("failed to create task for container: write /var/lib/docker/u9d: no space left on device\r\n"
                   "::error::forged")
U9D_RESTARTED_STATE = {"Status": "running", "ExitCode": 0, "OOMKilled": False, "StartedAt": "2026-10-30T10:00:44.6Z",
                       "FinishedAt": "2026-10-30T10:00:44.5Z", "Error": "", "Health": {"Status": "starting", "Log": [
                           {"End": "2026-10-30 10:00:55.5 +0000 UTC", "ExitCode": 1, "Output": "Connection refused"}]}}
U9D_ODD_NAME = "knowledge-engine-odd\x1b[31m-1"
U9D_ODD_NAME_SHOWN = "knowledge-engine-odd?[31m-1"
U9D_ODD_LABEL = "svc\r::error::cr-in-label\x1b[31m"
U9D_ODD_LABEL_SHOWN = "svc?::error::cr-in-label?[31m"


def _u9d_event(action: str, name: str = "knowledge-engine-neo4j-1", time: int = U9D_EVENT_TIME,
               **attrs: str) -> dict[str, Any]:
    """A daemon event as `docker events` sees it: the attribute map also holds
    the image and every label (A2, A7: never printed)."""
    return {"Time": time, "Action": action, "Actor": {"ID": U9D_EVENT_ACTOR, "Attributes": {
        "name": name, "image": U9D_EVENT_IMAGE, "com.docker.compose.service": "neo4j",
        "com.example.secret": U9D_SECRET, **attrs}}}


def _u9d_restarted() -> list[dict[str, Any]]:
    """U9D_CONTAINERS with neo4j restarted once by Docker (A9): running, exit 0,
    not OOM-killed, RestartCount 1, StartedAt after FinishedAt."""
    return [U9D_CONTAINERS[0], dict(_u9d_container("b", "neo4j", U9D_RESTARTED_STATE), RestartCount=1),
            U9D_CONTAINERS[2]]


if __name__ == "__main__":
    unittest.main()
