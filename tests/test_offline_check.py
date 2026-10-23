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
FIRST_PARTY = {"app.Dockerfile": "ke-app", "gateway.Dockerfile": "ke-gateway",
               "gates.Dockerfile": "ke-gates"}
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
        for name in ("gateway", "api", "worker"):
            with self.subTest(live=name):
                self.assertRegex(str(live_images.get(name)), r"^ke-(?:app|gateway):local$",
                                 "the live stack's first-party images resolve to the :local tag")
        verify = self._config(["docker-compose.yml", "docker-compose.verify.yml"], profile=True,
                              KE_IMAGE_TAG=WT_TAG, KE_OFFLINE_BUNDLE=bundle)
        built = {name: svc.get("image") for name, svc in (verify.get("services") or {}).items()
                 if svc.get("build") or str(svc.get("image", "")).startswith("ke-")}
        self.assertTrue({"gateway", "api", "worker", "gates", "gates-it"} <= set(built), built)
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
if [ -n "$out" ]; then mkdir -p "$out" && echo '{}' > "$out/bundle.json"; fi'''

_INSTALL_PRE = r'''parent_mode="$(stat -c %a "$(dirname "$1")" 2>/dev/null || echo missing)"'''

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
PG_REF = "postgres:16-bookworm@sha256:" + "a" * 64
VK_REF = "valkey/valkey:8-alpine@sha256:" + "b" * 64
AS_PG = "ke-vendor/postgres:aaaaaaaaaaaa"
AS_VK = "ke-vendor/valkey:bbbbbbbbbbbb"
BUNDLE_ENTRIES = [
    {"file": "images/ke-app.tar", "ref": "ke-app:wt-0123456789ab", "as": AS_APP, "services": "api worker"},
    {"file": "images/ke-gateway.tar", "ref": "ke-gateway:wt-0123456789ab", "as": AS_GATEWAY,
     "services": "gateway"},
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
        _executable(repo / "scripts" / "bundle.sh", _stub("bundle.sh", pre=_BUNDLE_PRE))
        _executable(repo / "scripts" / "teardown.sh", _stub("teardown.sh"))
        _executable(repo / "scripts" / "net_isolated.sh", _stub("net_isolated.sh"))
        return repo

    def _host(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        repo = self._host_setup()
        self.json.write_text("", encoding="utf-8")
        env_vars = {"FAKE_DOCKER_ROOT_DIR": str(self.tmp / "no-such-docker-root")}
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
                                     FAKE_DOCKER_ROOT_DIR=str(self.tmp / "no-such-docker-root"))
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
                                     FAKE_DOCKER_ROOT_DIR=str(self.tmp / "no-such-docker-root"))
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
  for f in images/ke-app.tar images/valkey.tar app/compose.yml MANIFEST.sha256; do
    printf 'x\n' > "$out/$f"; chmod 600 "$out/$f"
  done
  for f in install.sh app/scripts/launch.sh; do
    printf '#!/bin/sh\n' > "$out/$f"; chmod 700 "$out/$f"
  done
  chmod 600 "$out/bundle.json"
  chmod 700 "$out" "$out/images" "$out/app" "$out/app/scripts"
  printf 'h\n' > "$out.manifest.sha256"; chmod 600 "$out.manifest.sha256"
fi'''

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
                             KE_TEST_SNAP_LOG=str(log))
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

    # ---- platform-sbom U2: the interim SBOM generator pull --------------------
    # PSC-20; design-notes "N1 amendment, U2" *Interim pull (U2 to U8)*: the host
    # half pulls the generator through its own compose file, after the Compose
    # version check and immediately before bundle.sh (which never pulls). U8
    # replaces this step with scripts/bundle_fetch.sh.

    SBOM_PULL_FAIL = "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry"

    def _event_u2(self, record: dict) -> str | None:
        """`_event`, plus any pull: "pull sbom" when it names the generator's
        compose file or service, else "pull" (any other pull is out of order)."""
        argv = record["argv"]
        if argv[:1] != ["STUB"] and ("pull" in argv or argv[:2] == ["image", "pull"]):
            names = cs.SBOM_COMPOSE_NAME in " ".join(argv) or argv[-1:] == ["sbom"]
            return "pull sbom" if names else "pull"
        return self._event(record)

    def _events_u2(self, records: list[dict]) -> list[str]:
        return [e for e in (self._event_u2(r) for r in records) if e and e != "df"]

    def test_offline_check_pulls_sbom_generator_before_bundle(self):
        result, records, repo = self._host()
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self._events_u2(records),
                         ["pull sbom", "bundle", "up dind", "net_isolated", "run client", "teardown"], out)
        pulls = [r for r in records if self._event_u2(r) == "pull sbom"]
        self.assertEqual(len(pulls), 1, "one pull of the generator")
        argv, env = pulls[0]["argv"], pulls[0]["env"]
        self.assertEqual(argv[:1], ["compose"], f"the pull goes through compose, not `docker pull`: {argv}")
        self.assertIn(("--env-file", ".env.example"), self._pairs(argv),
                      "--env-file .env.example: the repo-root .env (model keys) is never loaded")
        files = [b for a, b in self._pairs(argv) if a in ("-f", "--file")]
        self.assertEqual(files, [cs.SBOM_COMPOSE_NAME],
                         "-f docker-compose.sbom.yml only (it overrides the exported COMPOSE_FILE)")
        self.assertEqual(argv[-2:], ["pull", "sbom"], "pulls the `sbom` service only")
        self.assertNotIn("--profile", argv)
        for var in ("KE_SBOM_IN", "KE_SBOM_OUT"):
            # Git Bash may rewrite /nonexistent to <git root>/nonexistent (N1 amendment).
            self.assertTrue(env.get(var, "").endswith("/nonexistent"),
                            f"{var} is the dummy /nonexistent for the pull (the file's ${{{var}:?}}): "
                            f"{env.get(var)!r}")
        # platform-sbom U3 (security L-2): the `user:` of the sbom service is
        # ${KE_SBOM_USER:?}, and compose refuses to load the file for the pull
        # while any ${VAR:?} it names is unset or empty (tester, U3 RED).
        for var in sorted((set(cs.required_vars()) | {"KE_SBOM_USER"}) - {"KE_SBOM_IN", "KE_SBOM_OUT"}):
            self.assertTrue(env.get(var), f"{var} is set (non-empty) for the pull, or compose refuses "
                                          f"docker-compose.sbom.yml (its ${{{var}:?}}): {env.get(var)!r}")
        version = [i for i, r in enumerate(records) if r["argv"][:2] == ["compose", "version"]]
        self.assertTrue(version and version[0] < records.index(pulls[0]),
                        "the pull comes after the Compose version check")
        self.assertEqual(self._bundle_dirs(repo), [])

    def test_offline_check_stops_when_sbom_pull_fails(self):
        with self.subTest(case="the pull fails"):
            result, records, repo = self._host(FAKE_DOCKER_FAIL="pull sbom")
            out = self._out(result)
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn(self.SBOM_PULL_FAIL, result.stderr, out)
            self.assertNotRegex(out, r"(?i)\bpass(?:ed)?\b")
            self.assertEqual(self._events_u2(records), ["pull sbom", "teardown"],
                             "bundle.sh ran after a failed pull, the pull was retried, or teardown did not run once")
            teardown = next(r for r in records if self._event(r) == "teardown")
            self.assertEqual(teardown["argv"][2:], ["--volumes", "--profile", "offline"])
            self.assertEqual(self._bundle_dirs(repo), [], "the bundle directory was left behind")
        for case, extra in (("below the disk floor", {"FAKE_DF_AVAIL_KB": str(3 * GIB_KB)}),
                            ("Compose below 2.27", {"FAKE_COMPOSE_VERSION": "2.20.0"})):
            with self.subTest(case=f"{case}: no pull"):
                result, records, _ = self._host(**extra)
                self.assertNotEqual(result.returncode, 0, self._out(result))
                self.assertEqual(self._events_u2(records), ["teardown"],
                                 "the generator is pulled only after the disk and Compose checks")

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


if __name__ == "__main__":
    unittest.main()
