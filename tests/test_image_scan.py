"""platform-supply-chain unit 2: the `ke-app` image scan (PS-3.6), statically
and against the fake docker.

Criteria: docs/requirements.md § "Item: platform-supply-chain" PSC-1 (pinned
scanner), PSC-2 (`ke-app` only, native arch, from a read-only image tar, no
socket), PSC-3 (fresh database, one network step, fail closed), PSC-5
(justified exceptions) and PSC-8 (not in the bundle). Design:
docs/architecture.md ADR-KE-013 amendment 1, D1 (compose), D2 (pin), D3
(fetch), D4 (scan.sh), D5 (ignore file); test names from §2.6
"platform-supply-chain" item 3. PSC-4, PSC-6, PSC-7 and PSC-9 are later
steps and are not tested here.

Interface pinned by these tests (tester, RED unit 2, 2026-10-21):
- `bash scripts/scan.sh` from the repository root, with KE_IMAGE_TAG exported
  (verify.sh exports it). The caller's COMPOSE_FILE / COMPOSE_PROJECT_NAME
  (verify full has its own) are ignored: scan.sh sets both unconditionally.
- Compose calls may name the file and project by `-f`/`-p` or by the
  COMPOSE_FILE / COMPOSE_PROJECT_NAME environment; either way the file is
  exactly `docker-compose.scan.yml` and the project `ke-scan-<digits>`.
- The scanner image is pulled by `docker compose pull scan-db` (or a plain
  `docker pull <ref>`); the two runs are `docker compose run ... scan-db` and
  `docker compose run ... scan`, with nothing after the service name (the
  commands live in the compose file, D1).
- `scripts/teardown.sh --volumes` is replaced here by a stub that logs its
  argv and the COMPOSE_FILE, COMPOSE_PROJECT_NAME, KE_ENV_FILE and KE_SCAN_IN
  it inherited (D4: teardown inherits them).
- The database URL is one constant, `SCAN_DB_URL=https://...`, in scan.sh (D3).
- The scanner's provenance record is
  docs/evidence/platform-supply-chain/scanner-provenance.md (D2, PSC-1); the
  pinned tag and index digest must appear in it.
- The ignore file is docker/scan-ignore.yaml (D5). It must exist; an empty
  list (`ignore: []`, the committed start) or a null `ignore:` passes; an
  empty file or a missing `ignore` key fails (exactly one top-level key).

Added by U2 rework 1 (tester, 2026-10-21; review B1, N2-N4, security M-1,
L-1..L-3, orchestrator rulings in the handoff):
- Cleanup, before teardown.sh, force-removes the containers labelled
  `com.docker.compose.project=<its project>`: `docker ps -aq --filter
  label=com.docker.compose.project=<project>` (or `container ls`), then
  `docker rm -f <ids>`. It never names another project's container, filter
  or a prune. Then it ignores INT and TERM until it exits (L-1).
- After `docker save` and before the first `docker compose`, one
  `chmod 0644 -- "$KE_SCAN_IN/ke-app.tar"` (M-1); no other chmod, no
  cap_add / privileged.
- `dist/<project>` is created by `mkdir` without -p (an existing path fails
  before save, L-2); DOCKER_DEFAULT_PLATFORM is unset (L-3).
- INT/TERM exit 130/143 through the EXIT trap (D4); a failed teardown fails
  the run naming the project and `down --volumes` (N2).
- Signal tests run scan.sh in its own process group and signal the group.

Added by unit 3 (tester, 2026-10-21; PSC-4, PSC-17 / D10, and the carry-ins
review N1, r1-a, r1-b, security I-4, I-6):
- PSC-4: the `scan` command is exactly SCAN_POLICY_COMMAND (D1/D5, N1), with
  no entrypoint and no GRYPE_* key beyond D1's three; `run scan` passes only
  `--rm --pull never`. A fake grype (hook "stdout"/"exit") that exits 2 on a
  fixed High fails the run naming `stage scan: grype exited 2`; one that exits
  0 passes; either way every table row is in scan.sh's output.
- r1-a: a failing container listing in cleanup prints `scan: FAIL (...)`
  naming the project and the run exits 1. r1-b: a failing `docker rm -f`
  prints a `docker rm ...` hand command that, run as is, removes exactly the
  project's containers (running and created).
- I-4: the first `trap` in the EXIT-trap function is `trap '' INT TERM`
  (EXIT may be in the same command). I-6: `COMPOSE_PROJECT_NAME=ke-scan-${SRANDOM}`.
- PSC-17 (D10 tests 1 and 1b): static checks of docker/app.Dockerfile and the
  uv pin shared with docker/gates.Dockerfile. uv.lock's certifi version is
  manual evidence (D10 test 2, u3-no-uv-in-ke-app.txt), not a unit test.
- `test_verify_full_fails_when_image_scan_fails` (§2.6 item 5) needs scan.sh
  wired into verify.sh; it is in tests/test_stack_scripts.py (PSC-6, unit 4).

Added by unit 4 (tester, 2026-10-21; PSC-6 carry-ins review r3-1, r3-2, r3-3,
security L-1, I-1; the verify.sh wiring itself is tested in
tests/test_stack_scripts.py `VerifyHostHalfTest`):
- r3-1: with only other projects' containers in the daemon, cleanup's listing
  is empty, so it makes no `docker rm` call and a passing scan exits 0.
- L-1: before any docker call, `mkdir` or trap, scan.sh checks the project
  against `^ke-scan-[0-9]+$` and otherwise prints `scan: FAIL (...)` and
  exits non-zero. Older bash is simulated with BASH_ENV (see the test). The
  I-6 assignment may read `${SRANDOM-}` or `${SRANDOM:-}` so the check, not
  `set -u`, reports an unset SRANDOM.
- r3-2: the `builder` stage puts no uv under /opt/venv or /app (the final
  stage copies both whole). I-1: the builder removes /opt/venv/.lock after
  its last uv command.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tests import compose_support as cs
from tests import fake_docker
from tests.engine_support import ROOT
from tests.test_offline_bundle import _BundleBase, _rel

SCAN_COMPOSE = ROOT / "docker-compose.scan.yml"
SCAN_SH = ROOT / "scripts" / "scan.sh"
IGNORE_FILE = ROOT / "docker" / "scan-ignore.yaml"
PROVENANCE = ROOT / "docs" / "evidence" / "platform-supply-chain" / "scanner-provenance.md"
BUNDLE_SH = ROOT / "scripts" / "bundle.sh"

SCAN_FILE_NAME = "docker-compose.scan.yml"
SCAN_SERVICES = {"scan-db", "scan"}
SCANNER_REF = re.compile(r"^anchore/grype:v(\d+\.\d+\.\d+)@sha256:([0-9a-f]{64})$")
WT_TAG = "wt-0123456789ab"
PROJECT_RE = re.compile(r"^ke-scan-[0-9]+$")
SKIP_RX = re.compile(r"(?i)\bskip(?:ped|ping)?\b")
SOCKET_MARKERS = (*cs.SOCKET_MARKERS, "docker.sock")

COMPOSE_MISSING = "docker-compose.scan.yml is missing (ADR-KE-013 amendment 1, D1)"
SCRIPT_MISSING = "scripts/scan.sh is missing (ADR-KE-013 amendment 1, D4)"
IGNORE_MISSING = "docker/scan-ignore.yaml is missing (ADR-KE-013 amendment 1, D5; it starts as `ignore: []`)"

# A placeholder pin for the harness when the compose file is absent; the
# tests that need the real file fail before using it.
PLACEHOLDER_REF = "anchore/grype:v0.0.0@sha256:" + "0" * 64

# PSC-4 (D1 Command row, D5): the one gating and reporting grype run, word for
# word and in order (review N1: an exact list, as scan-db's `db update` is).
SCAN_POLICY_COMMAND = ["docker-archive:/in/ke-app.tar", "--config", "/cfg/scan-ignore.yaml", "--only-fixed",
                       "--fail-on", "high", "--show-suppressed", "-o", "table"]
# D1 Environment row for `scan`: the only GRYPE_* keys (a GRYPE_* key can set
# a policy option, e.g. the fail-on severity or the ignore rules).
SCAN_GRYPE_ENV = {"GRYPE_DB_CACHE_DIR", "GRYPE_DB_AUTO_UPDATE", "GRYPE_CHECK_FOR_APP_UPDATE"}


# --------------------------------------------------------------------------
# Compose helpers
# --------------------------------------------------------------------------

def _scan_compose() -> dict[str, Any]:
    return cs.load(SCAN_COMPOSE)


def _scan_services() -> dict[str, dict[str, Any]]:
    return cs.services(SCAN_COMPOSE)


def _scanner_ref() -> str:
    if not SCAN_COMPOSE.is_file():
        return PLACEHOLDER_REF
    return str((_scan_services().get("scan-db") or {}).get("image", PLACEHOLDER_REF))


_SHORT_MOUNT = re.compile(r"^(\$\{[^}]*\}|[^:]+):([^:]+)(?::(.+))?$")


def _mounts(svc: dict[str, Any]) -> list[dict[str, Any]]:
    """Every `volumes` entry as {type, source, target, read_only, extra}."""
    out: list[dict[str, Any]] = []
    for entry in svc.get("volumes") or []:
        if isinstance(entry, dict):
            extra = sorted(set(entry) - {"type", "source", "target", "read_only"})
            out.append({"type": str(entry.get("type", "volume")), "source": str(entry.get("source", "")),
                        "target": str(entry.get("target", "")), "read_only": entry.get("read_only") is True,
                        "extra": extra})
            continue
        text = str(entry)
        m = _SHORT_MOUNT.match(text)
        if not m:
            out.append({"type": "volume", "source": "", "target": text, "read_only": False, "extra": []})
            continue
        source, target, opts = m.group(1), m.group(2), (m.group(3) or "").split(",")
        bind = bool(re.match(r"^(?:[./~$\\]|[A-Za-z]:[\\/])", source)) or "/" in source
        out.append({"type": "bind" if bind else "volume", "source": source, "target": target,
                    "read_only": "ro" in opts, "extra": []})
    return out


def _tmpfs_targets(svc: dict[str, Any]) -> list[str]:
    raw = svc.get("tmpfs") or []
    found = [raw] if isinstance(raw, str) else [str(t) for t in raw]
    found = [t.split(":", 1)[0] for t in found]
    found += [m["target"] for m in _mounts(svc) if m["type"] == "tmpfs"]
    return found


def _env_entries(svc: dict[str, Any]) -> list[tuple[str, str | None]]:
    """(key, value) per environment entry; value None for a bare pass-through."""
    env = svc.get("environment") or {}
    if isinstance(env, dict):
        return [(str(k), None if v is None else str(v)) for k, v in env.items()]
    out: list[tuple[str, str | None]] = []
    for item in env:
        key, sep, value = str(item).partition("=")
        out.append((key, value if sep else None))
    return out


def _command_words(svc: dict[str, Any]) -> list[str]:
    cmd = svc.get("command")
    if cmd is None:
        return []
    if isinstance(cmd, list):
        return [str(c) for c in cmd]
    return str(cmd).split()


def _norm_path(value: str) -> str:
    v = value.replace("\\", "/")
    while v.startswith("./"):
        v = v[2:]
    return v


# --------------------------------------------------------------------------
# Fake-docker call parsing
# --------------------------------------------------------------------------

_GLOBAL_TAKES = {"-f", "--file", "-p", "--project-name", "--env-file", "--profile", "--project-directory",
                 "--ansi", "--progress", "--parallel"}
_RUN_TAKES = {"-e", "--env", "--pull", "--name", "-u", "--user", "-w", "--workdir", "-v", "--volume",
              "--entrypoint", "-l", "--label", "-p", "--publish", "--env-from-file", "--cap-add",
              "--cap-drop"}
_PULL_TAKES = {"--policy"}


def _compose_call(argv: list[str]) -> dict[str, Any] | None:
    """Split `compose [global opts] <sub> [opts] [service] [rest]`."""
    if argv[:1] != ["compose"]:
        return None

    def opts(i: int, takes: set[str]) -> tuple[dict[str, list[str]], int]:
        found: dict[str, list[str]] = {}
        while i < len(argv) and argv[i].startswith("-"):
            a = argv[i]
            if a.startswith("--") and "=" in a:
                k, v = a.split("=", 1)
                found.setdefault(k, []).append(v)
                i += 1
            elif a in takes and i + 1 < len(argv):
                found.setdefault(a, []).append(argv[i + 1])
                i += 2
            else:
                found.setdefault(a, []).append("")
                i += 1
        return found, i

    glob, i = opts(1, _GLOBAL_TAKES)
    sub = argv[i] if i < len(argv) else None
    takes = _RUN_TAKES if sub == "run" else _PULL_TAKES if sub == "pull" else set()
    sub_opts, j = opts(i + 1, takes)
    service = argv[j] if j < len(argv) else None
    return {"global": glob, "sub": sub, "opts": sub_opts, "service": service, "rest": argv[j + 1:]}


def _project(record: dict[str, Any]) -> str | None:
    call = _compose_call(record["argv"])
    if call:
        for flag in ("-p", "--project-name"):
            if call["global"].get(flag):
                return call["global"][flag][-1]
    return record.get("env", {}).get("COMPOSE_PROJECT_NAME")


def _compose_files(record: dict[str, Any]) -> list[str]:
    call = _compose_call(record["argv"])
    files: list[str] = []
    if call:
        files = call["global"].get("-f", []) + call["global"].get("--file", [])
    if not files:
        raw = record.get("env", {}).get("COMPOSE_FILE", "")
        sep = record.get("env", {}).get("COMPOSE_PATH_SEPARATOR") or ":"
        files = [f for f in raw.split(sep) if f]
    return [_norm_path(f) for f in files]


def _env_values(call: dict[str, Any]) -> list[str]:
    return call["opts"].get("-e", []) + call["opts"].get("--env", [])


def _event(record: dict[str, Any], scanner: str) -> str | None:
    argv = record["argv"]
    if argv[:1] == ["STUB"]:
        return argv[1] if len(argv) > 1 else "stub"
    if argv[:1] == ["save"] or argv[:2] == ["image", "save"]:
        return "save"
    if argv[:1] == ["pull"] or argv[:2] == ["image", "pull"]:
        return "pull" if scanner in argv else "pull other"
    if argv[:1] == ["run"] or argv[:2] == ["container", "run"]:
        return "docker run"
    call = _compose_call(argv)
    if call and call["sub"] == "pull":
        return "pull" if call["service"] == "scan-db" else f"compose pull {call['service']}"
    if call and call["sub"] == "run":
        return f"run {call['service']}"
    return None


def _save_parts(argv: list[str]) -> tuple[list[str], list[str]]:
    """(output paths, image refs) of a `docker save` call."""
    args = argv[1:] if argv[0] == "save" else argv[2:]
    outs: list[str] = []
    refs: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-o", "--output") and i + 1 < len(args):
            outs.append(args[i + 1])
            i += 2
            continue
        if a.startswith("--output="):
            outs.append(a.split("=", 1)[1])
        elif a == "--platform" and i + 1 < len(args):
            i += 2
            continue
        elif not a.startswith("-"):
            refs.append(a)
        i += 1
    return outs, refs


_TEARDOWN_STUB = r'''#!/usr/bin/env bash
# Stand-in for scripts/teardown.sh: one JSON record in the fake docker's log.
# FAKE_TEARDOWN_MARKER: touch it, sleep FAKE_TEARDOWN_SLEEP (default 3) and
# then log a ["STUB", "teardown-end"] record (a teardown in progress).
# FAKE_TEARDOWN_EXIT: its exit status (default 0).
args=""
for a in "$@"; do args="$args, \"$a\""; done
printf '{"argv": ["STUB", "teardown.sh"%s], "env": {"COMPOSE_FILE": "%s", "COMPOSE_PROJECT_NAME": "%s", "KE_ENV_FILE": "%s", "KE_SCAN_IN": "%s", "COMPOSE_PROFILES": "%s", "COMPOSE_ENV_FILES": "%s", "DOCKER_DEFAULT_PLATFORM": "%s"}, "cwd": "%s", "project_dir": "", "dotenv_present": false}\n' \
  "$args" "${COMPOSE_FILE-<unset>}" "${COMPOSE_PROJECT_NAME-<unset>}" "${KE_ENV_FILE-<unset>}" \
  "${KE_SCAN_IN-<unset>}" "${COMPOSE_PROFILES-<unset>}" "${COMPOSE_ENV_FILES-<unset>}" \
  "${DOCKER_DEFAULT_PLATFORM-<unset>}" "$PWD" >> "$FAKE_DOCKER_JSON"
if [ -n "${FAKE_TEARDOWN_MARKER-}" ]; then
  : > "$FAKE_TEARDOWN_MARKER"
  sleep "${FAKE_TEARDOWN_SLEEP:-3}"
  printf '{"argv": ["STUB", "teardown-end"], "env": {}, "cwd": "%s", "project_dir": "", "dotenv_present": false}\n' \
    "$PWD" >> "$FAKE_DOCKER_JSON"
fi
exit "${FAKE_TEARDOWN_EXIT:-0}"
'''

# L-2 planter, installed as `sed`, `head`, `cat` and `mkdir` ahead of the real
# tools on PATH. The first time one of them runs with KE_SCAN_IN exported (or
# `mkdir` is asked for a dist/ke-scan-* path), it plants that path: an empty
# directory, or a symlink to one. So the path exists before scan.sh's own
# rm/mkdir, as a pre-existing dist/<project> would. It then runs the real tool.
_PLANTER = r'''#!/usr/bin/env bash
plant=""
if [ -n "${KE_SCAN_IN-}" ]; then plant="$KE_SCAN_IN"; fi
if [ -z "$plant" ] && [ "$(basename -- "$0")" = mkdir ]; then
  for a in "$@"; do
    case "$a" in *dist/ke-scan-*) plant="$a" ;; esac
  done
fi
# mkdir of the marker is the lock: `sed | head` run at the same time.
if [ -n "$plant" ] && PATH="$FAKE_REAL_PATH" mkdir -- "$FAKE_PLANT_ONCE" 2>/dev/null; then
  plant="${plant%/}"
  PATH="$FAKE_REAL_PATH" mkdir -p -- "$(dirname -- "$plant")"
  if [ "$FAKE_PLANT_KIND" = symlink ]; then
    PATH="$FAKE_REAL_PATH" mkdir -p -- "$FAKE_PLANT_TARGET"
    PATH="$FAKE_REAL_PATH" ln -s -- "$FAKE_PLANT_TARGET" "$plant"
  else
    PATH="$FAKE_REAL_PATH" mkdir -p -- "$plant"
  fi
fi
PATH="$FAKE_REAL_PATH" exec "$(basename -- "$0")" "$@"
'''
_PLANTED_TOOLS = ("sed", "head", "cat", "mkdir")

# The scan.sh lines, comments dropped (static checks).
def _script_lines() -> list[str]:
    return [line for line in SCAN_SH.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")]


# B1 fixture: the containers the fake daemon reports. The scan's own project
# has two: the one-off scan-db run container a TERM leaves running, and one
# created but never started (a signal between create and start; it holds the
# volume just the same). The others carry another project's label, one of them
# under a look-alike name.
OWN_CONTAINERS = [
    {"ID": "f00d5ca7db000001", "Names": "{run_project}-scan-db-run-1b3becfb12b4",
     "Labels": {"com.docker.compose.project": "{run_project}", "com.docker.compose.service": "scan-db",
                "com.docker.compose.oneoff": "True"},
     "State": "running"},
    {"ID": "f00d5ca7db000002", "Names": "{run_project}-scan-db-run-2c4cfc0d23c5",
     "Labels": {"com.docker.compose.project": "{run_project}", "com.docker.compose.service": "scan-db",
                "com.docker.compose.oneoff": "True"},
     "State": "created"},
]
DECOY_CONTAINERS = [
    {"ID": "dec0ver1f1000001", "Names": "ke-verify-1234-api-1",
     "Labels": {"com.docker.compose.project": "ke-verify-1234", "com.docker.compose.service": "api"},
     "State": "running"},
    {"ID": "dec05ca7000000001", "Names": "ke-scan-1-scan-db-run-0123456789ab",
     "Labels": {"com.docker.compose.project": "ke-scan-1", "com.docker.compose.service": "scan-db",
                "com.docker.compose.oneoff": "True"},
     "State": "running"},
    {"ID": "dec0a11ke0000001", "Names": "{run_project}-scan-db-run-ffffffffffff",
     "Labels": {"com.docker.compose.project": "someone-else"}, "State": "exited"},
]


def _scan_db_url() -> str | None:
    """The one literal `SCAN_DB_URL=https://...` assignment in scan.sh (D3)."""
    if not SCAN_SH.is_file():
        return None
    found = re.findall(r"""(?m)^\s*(?:readonly\s+|declare\s+-r\s+)?SCAN_DB_URL=["']?(https://[^\s"'$`]+)["']?\s*$""",
                       SCAN_SH.read_text(encoding="utf-8"))
    return found[0] if len(found) == 1 else None


# --------------------------------------------------------------------------
# PSC-1, PSC-2 (static), PSC-3 (static): docker-compose.scan.yml
# --------------------------------------------------------------------------

class ScanComposeTest(unittest.TestCase):
    """D1 row by row, D2's pin, PSC-2's no-socket rule."""

    def _services(self) -> dict[str, dict[str, Any]]:
        if not SCAN_COMPOSE.is_file():
            self.fail(COMPOSE_MISSING)
        services = _scan_services()
        self.assertEqual(set(services), SCAN_SERVICES,
                         "docker-compose.scan.yml defines exactly scan-db and scan (D1)")
        return services

    def _hardening(self, name: str, svc: dict[str, Any]) -> None:
        with self.subTest(service=name, part="hardening (D1)"):
            self.assertIs(svc.get("read_only"), True, f"{name}: read_only: true")
            self.assertIn("/tmp", _tmpfs_targets(svc), f"{name}: tmpfs /tmp under the read-only root")
            self.assertEqual(svc.get("cap_drop"), ["ALL"], f"{name}: cap_drop: [ALL]")
            self.assertNotIn("cap_add", svc, f"{name}: no cap_add")
            opts = [str(o).replace("=", ":") for o in svc.get("security_opt") or []]
            self.assertIn("no-new-privileges:true", opts, f"{name}: security_opt no-new-privileges:true")
            self.assertNotIn(svc.get("privileged"), (True, "true"), f"{name}: not privileged")
            self.assertEqual(cs.port_entries(svc), [], f"{name}: publishes nothing")
            self.assertFalse(svc.get("profiles"), f"{name}: no profiles (D1: only `compose run` starts it)")
            self.assertIn(svc.get("restart"), (None, "no"), f"{name}: one-shot, no restart policy")
            self.assertNotIn("build", svc, f"{name}: the pulled scanner image, never a build")
            self.assertNotIn("env_file", svc, f"{name}: no env_file (literal environment only)")

    def _literal_env(self, name: str, svc: dict[str, Any], required: dict[str, str]) -> None:
        entries = _env_entries(svc)
        with self.subTest(service=name, part="environment literals only (D1)"):
            for key, value in entries:
                self.assertIsNotNone(value, f"{name}: `{key}` is passed through from the host")
                self.assertNotIn("$", str(value), f"{name}: `{key}` interpolates a host value")
            keys = [k for k, _ in entries]
            self.assertEqual(len(keys), len(set(keys)), f"{name}: an environment key is repeated")
            got = dict(entries)
            for key, value in required.items():
                self.assertEqual(str(got.get(key)).lower() if value in ("true", "false") else got.get(key),
                                 value, f"{name}: {key}={value}")
            self.assertNotIn("GRYPE_DB_UPDATE_URL", got,
                             f"{name}: the compose file never sets the database URL (D3: scan.sh passes it)")

    # ---- PSC-1 ---------------------------------------------------------------

    def test_image_scanner_is_pinned(self):
        services = self._services()
        images = {name: str(svc.get("image", "")) for name, svc in services.items()}
        with self.subTest(part="one image for both services"):
            self.assertEqual(len(set(images.values())), 1, f"scan-db and scan use one image: {images}")
        ref = images.get("scan-db", "")
        m = SCANNER_REF.match(ref)
        with self.subTest(part="anchore/grype:vX.Y.Z@sha256:<64 hex> (D2)", image=ref):
            self.assertIsNotNone(m, "the scanner is anchore/grype:v<X.Y.Z>@sha256:<64 hex>")
            self.assertNotIn("latest", ref, "no latest tag")
        with self.subTest(part="provenance recorded before the pin (D2, PSC-1)"):
            self.assertTrue(PROVENANCE.is_file(),
                            f"{_rel(PROVENANCE, ROOT)} is missing: security records the provenance check (D2) "
                            "before the pin is committed")
            if m and PROVENANCE.is_file():
                text = PROVENANCE.read_text(encoding="utf-8")
                self.assertIn(m.group(2), text, "the pinned index digest is not in the provenance record")
                self.assertRegex(text, rf"\bv{re.escape(m.group(1))}\b",
                                 "the pinned release tag is not in the provenance record")
                self.assertIn("anchore/grype", text)

    # ---- PSC-3 ---------------------------------------------------------------

    def test_compose_scan_db_has_only_db_volume(self):
        services = self._services()
        svc = services["scan-db"]
        with self.subTest(part="exactly the scan-db volume at /db, read-write, no checkout"):
            mounts = [m for m in _mounts(svc) if m["type"] != "tmpfs"]
            self.assertEqual(len(mounts), 1, f"scan-db mounts exactly one volume: {mounts}")
            if mounts:
                m = mounts[0]
                self.assertEqual((m["type"], m["source"], m["target"]), ("volume", "scan-db", "/db"),
                                 "scan-db mounts the named volume scan-db at /db")
                self.assertFalse(m["read_only"], "scan-db writes the database (read-write)")
            self.assertNotIn("volumes_from", svc)
        with self.subTest(part="the only route out: the project's default bridge"):
            self.assertNotIn("network_mode", svc, "scan-db stays on the default bridge (no network_mode)")
            self.assertNotIn("networks", svc, "scan-db joins no named network (D1)")
            self.assertNotIn("networks", _scan_compose(), "the scan file defines no networks (D1)")
            others = [n for n, s in services.items() if n != "scan-db" and s.get("network_mode") != "none"]
            self.assertEqual(others, [], "scan-db is the only service in the file with a route out")
        with self.subTest(part="command db update"):
            self.assertEqual(_command_words(svc), ["db", "update"], "scan-db runs `db update` (D1)")
        self._hardening("scan-db", svc)
        self._literal_env("scan-db", svc, {"GRYPE_DB_CACHE_DIR": "/db", "GRYPE_CHECK_FOR_APP_UPDATE": "false"})

    def test_compose_scan_has_no_network(self):
        services = self._services()
        svc = services["scan"]
        with self.subTest(part="network_mode none"):
            self.assertEqual(svc.get("network_mode"), "none", "scan has network_mode: none (Q56(a))")
            self.assertNotIn("networks", svc)
        with self.subTest(part="mounts: all read-only, exactly /db, /in and the ignore file"):
            mounts = {m["target"]: m for m in _mounts(svc) if m["type"] != "tmpfs"}
            self.assertEqual(sorted(mounts), ["/cfg/scan-ignore.yaml", "/db", "/in"],
                             "scan mounts the database, the image tar dir and the ignore file only")
            for target, m in mounts.items():
                self.assertTrue(m["read_only"], f"scan's {target} mount is not read-only")
            if "/db" in mounts:
                self.assertEqual((mounts["/db"]["type"], mounts["/db"]["source"]), ("volume", "scan-db"))
            if "/cfg/scan-ignore.yaml" in mounts:
                cfg = mounts["/cfg/scan-ignore.yaml"]
                self.assertEqual((cfg["type"], _norm_path(cfg["source"])), ("bind", "docker/scan-ignore.yaml"),
                                 "the only checkout mount is the one ignore file (D1)")
            self.assertNotIn("volumes_from", svc)
        self._hardening("scan", svc)
        self._literal_env("scan", svc, {"GRYPE_DB_CACHE_DIR": "/db", "GRYPE_DB_AUTO_UPDATE": "false",
                                        "GRYPE_CHECK_FOR_APP_UPDATE": "false"})
        with self.subTest(part="gates and gates-it unchanged; the scan services live only here (Q56(a))"):
            for path in cs.compose_files():
                if path.name == SCAN_FILE_NAME:
                    continue
                for name, other in cs.services(path).items():
                    self.assertNotIn(name, SCAN_SERVICES, f"{path.name} defines {name}; D1 keeps it standalone")
                    if name not in cs.ONE_SHOT_SERVICES:
                        continue
                    text = json.dumps(other)
                    for word in ("grype", "scan-db", "KE_SCAN_IN", "GRYPE_", SCAN_FILE_NAME):
                        self.assertNotIn(word, text, f"{path.name}:{name} gained a scan setting ({word})")
                self.assertNotIn("scan-db", cs.load(path).get("volumes") or {},
                                 f"{path.name} declares the scan-db volume")

    # ---- PSC-2 ---------------------------------------------------------------

    def test_scan_services_have_no_docker_socket(self):
        services = self._services()
        for name, svc in services.items():
            with self.subTest(service=name):
                for m in _mounts(svc):
                    self.assertFalse(any(s in m["source"] or s in m["target"] for s in SOCKET_MARKERS),
                                     f"{name} mounts the Docker socket: {m}")
                keys = [k for k, _ in _env_entries(svc)]
                self.assertNotIn("DOCKER_HOST", keys, f"{name} sets DOCKER_HOST (ADR-KE-009)")
                self.assertFalse([k for k in keys if k.startswith("DOCKER_")], f"{name} sets a DOCKER_* key")
                self.assertNotIn(svc.get("privileged"), (True, "true"), f"{name} is privileged")
                self.assertEqual(cs.port_entries(svc), [], f"{name} publishes a port")
                for key in ("devices", "volumes_from", "extra_hosts"):
                    self.assertNotIn(key, svc, f"{name} sets {key}")
                for key in ("pid", "ipc", "userns_mode", "uts", "cgroup"):
                    self.assertNotEqual(str(svc.get(key, "")), "host", f"{name}: {key}: host")

    # ---- PSC-4 (unit 3; review N1) -------------------------------------------

    def test_scan_command_is_exactly_the_d5_policy(self):
        """PSC-4, D5 (Q42), review N1: the `scan` command is D1's list exactly,
        in order. Without `--fail-on high` grype exits 0 on every finding;
        without `--only-fixed` an unfixed High fails; without `--config` the
        ignore file is not applied; without `--show-suppressed` or `-o table`
        the CI log loses the suppressed rows or the table (PSC-7)."""
        svc = self._services()["scan"]
        with self.subTest(part="command, word for word (D1 Command row, D5)"):
            self.assertEqual(_command_words(svc), SCAN_POLICY_COMMAND,
                             "the scan command must be exactly `" + " ".join(SCAN_POLICY_COMMAND) + "` (PSC-4, D5; "
                             "review N1)")
        with self.subTest(part="no entrypoint override (the command is grype's arguments)"):
            self.assertNotIn("entrypoint", svc, "scan overrides the scanner image's entrypoint")
        with self.subTest(part="no GRYPE_* key but D1's three (no policy option through the environment)"):
            keys = sorted(k for k, _ in _env_entries(svc) if k.upper().startswith("GRYPE"))
            self.assertEqual(keys, sorted(SCAN_GRYPE_ENV), "scan sets a GRYPE_* key outside D1's Environment row")


# --------------------------------------------------------------------------
# PSC-2, PSC-3: scripts/scan.sh against the fake docker
# --------------------------------------------------------------------------

class ScanScriptTest(unittest.TestCase):
    """D3 and D4 steps 1, 3-5 (fake docker; teardown.sh stubbed)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.json = self.tmp / "docker.jsonl"
        fake_docker.install(self.tmp / "fakebin")
        self.scanner = _scanner_ref()

    def _repo(self) -> Path:
        for path, message in ((SCAN_SH, SCRIPT_MISSING), (SCAN_COMPOSE, COMPOSE_MISSING),
                              (IGNORE_FILE, IGNORE_MISSING)):
            if not path.is_file():
                self.fail(message)
        repo = self.tmp / "repo"
        shutil.rmtree(repo, True)
        shutil.copytree(ROOT / "scripts", repo / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (repo / "docker").mkdir()
        shutil.copyfile(IGNORE_FILE, repo / "docker" / "scan-ignore.yaml")
        for rel in (SCAN_FILE_NAME, ".env.example"):
            shutil.copyfile(ROOT / rel, repo / rel)
        stub = repo / "scripts" / "teardown.sh"
        stub.write_text(_TEARDOWN_STUB, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
        return repo

    def _run(self, repo: Path, tag: str | None = WT_TAG, **extra: str
             ) -> tuple[subprocess.CompletedProcess, list[dict[str, Any]]]:
        env = self._env(tag, **extra)
        result = subprocess.run(["bash", "scripts/scan.sh"], cwd=repo, env=env, capture_output=True,
                                text=True, timeout=120)
        return result, fake_docker.records(self.json)

    def _run_signalled(self, repo: Path, steps: list[tuple[int, Path]], **extra: str
                       ) -> tuple[subprocess.CompletedProcess, list[dict[str, Any]]]:
        """Run scan.sh in its own process group; for each (signal, marker),
        wait for the marker file, then send the signal to the whole group (as
        Ctrl-C, `timeout` or a CI cancel does). INT and TERM start at their
        default disposition in the child, whatever the test runner's are."""
        if not hasattr(os, "killpg"):
            self.skipTest("POSIX process groups are needed; verify.sh runs this in the Linux gates image")
        import signal

        def _default_signals() -> None:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

        env = self._env(WT_TAG, **extra)
        proc = subprocess.Popen(["bash", "scripts/scan.sh"], cwd=repo, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True,
                                preexec_fn=_default_signals)
        try:
            for sig, marker in steps:
                deadline = time.monotonic() + 60
                while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if not marker.exists():
                    os.killpg(proc.pid, signal.SIGKILL)
                    out, err = proc.communicate(timeout=30)
                    self.fail(f"scan.sh never reached {marker.name} (exit {proc.returncode}):\n{out}{err}")
                os.killpg(proc.pid, sig)
            out, err = proc.communicate(timeout=120)
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.communicate()
            raise
        return (subprocess.CompletedProcess(proc.args, proc.returncode, out, err),
                fake_docker.records(self.json))

    def _scan_db_hang(self) -> tuple[Path, str]:
        """A fake `compose run ... scan-db` that touches a marker and hangs
        (the database fetch in progress); returns (marker, FAKE_DOCKER_HOOKS)."""
        marker = self.tmp / "scan-db-running"
        return marker, json.dumps([{"on": r"\brun\b.*\sscan-db$", "touch": str(marker), "sleep": 60}])

    def _env(self, tag: str | None = WT_TAG, **extra: str) -> dict[str, str]:
        self.json.write_text("", encoding="utf-8")
        env = {
            "PATH": f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp),
            "FAKE_DOCKER_JSON": str(self.json),
            "FAKE_DOCKER_PULL_OK": "1",
            "FAKE_COMPOSE_IMAGES": json.dumps({"scan-db": self.scanner, "scan": self.scanner}),
            # What verify.sh full has exported when it calls scan.sh: scan.sh
            # must not reuse the verify project or its compose files.
            "COMPOSE_PROJECT_NAME": "ke-verify-1234",
            "COMPOSE_FILE": "docker-compose.yml:docker-compose.verify.yml",
            "COMPOSE_PATH_SEPARATOR": ":",
            "KE_ENV_FILE": ".env.example",
        }
        if tag is not None:
            env["KE_IMAGE_TAG"] = tag
        env.update(extra)
        return env

    @staticmethod
    def _out(result: subprocess.CompletedProcess) -> str:
        return (result.stdout or "") + (result.stderr or "")

    def _events(self, records: list[dict[str, Any]]) -> list[str]:
        return [e for e in (_event(r, self.scanner) for r in records) if e]

    def _docker_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in records if r["argv"][:1] != ["STUB"]]

    def _scan_calls(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The compose pull/run records of the scan services."""
        return [r for r in records if (_event(r, self.scanner) or "") in ("pull", "run scan-db", "run scan")
                and r["argv"][:1] == ["compose"]]

    @staticmethod
    def _left(repo: Path) -> list[str]:
        dist = repo / "dist"
        return sorted(p.name for p in dist.iterdir()) if dist.is_dir() else []

    def _assert_one_scan_project(self, records: list[dict[str, Any]]) -> str:
        calls = self._scan_calls(records)
        self.assertTrue(calls, "no compose call of the scan services was made")
        projects = {_project(r) for r in calls}
        self.assertEqual(len(projects), 1, f"the scan's compose calls use one project: {projects}")
        project = str(next(iter(projects)))
        self.assertRegex(project, PROJECT_RE, "the scan project is ke-scan-<digits> (D4 step 1)")
        for r in calls:
            self.assertEqual(_compose_files(r), [SCAN_FILE_NAME],
                             f"`{' '.join(r['argv'])}` does not use docker-compose.scan.yml alone")
        return project

    def _assert_torn_down(self, records: list[dict[str, Any]], project: str | None, repo: Path) -> None:
        downs = [r for r in records if r["argv"][:2] == ["STUB", "teardown.sh"]]
        self.assertEqual(len(downs), 1, "scripts/teardown.sh must run exactly once (D4 every exit path)")
        self.assertEqual(downs[0]["argv"][2:], ["--volumes"], "teardown.sh --volumes (D3: the volume goes)")
        self.assertEqual(_norm_path(downs[0]["env"]["COMPOSE_FILE"]), SCAN_FILE_NAME,
                         "teardown inherits COMPOSE_FILE=docker-compose.scan.yml (D4)")
        if project is not None:
            self.assertEqual(downs[0]["env"]["COMPOSE_PROJECT_NAME"], project,
                             "teardown inherits the scan project's name (D4)")
        self.assertEqual([n for n in self._left(repo) if n.startswith("ke-scan-")], [],
                         "dist/<scan project> (the tar) was left behind")

    # ---- PSC-2 ---------------------------------------------------------------

    def test_scan_order_is_save_then_db_then_scan(self):
        repo = self._repo()
        result, records = self._run(repo)
        out = self._out(result)
        self.assertEqual(result.returncode, 0, "scan.sh failed on a clean fake run:\n" + out)
        steps = [e for e in self._events(records) if e != "teardown.sh"]
        self.assertEqual(steps, ["save", "pull", "run scan-db", "run scan"],
                         "the order is save ke-app, pull the scanner, run scan-db, run scan (PSC-2, D4)")
        self._assert_one_scan_project(records)
        for r in self._scan_calls(records):
            call = _compose_call(r["argv"])
            assert call is not None
            if call["sub"] != "run":
                continue
            with self.subTest(service=call["service"]):
                self.assertIn("--rm", call["opts"], "compose run --rm")
                self.assertEqual(call["opts"].get("--pull"), ["never"], "compose run --pull never (D3)")
                self.assertEqual(call["rest"], [], "the command comes from the compose file (D1), "
                                 "nothing follows the service name")
        downs = [i for i, e in enumerate(self._events(records)) if e == "teardown.sh"]
        self.assertEqual(len(downs), 1, "teardown.sh --volumes runs once, after the scan")
        self.assertEqual(downs[0], len(self._events(records)) - 1, "teardown runs after the scan")

    def test_scan_input_is_read_only_ke_app_tar(self):
        repo = self._repo()
        result, records = self._run(repo)
        self.assertEqual(result.returncode, 0, self._out(result))
        project = self._assert_one_scan_project(records)
        saves = [r for r in records if _event(r, self.scanner) == "save"]
        with self.subTest(part="one save, of ke-app:<KE_IMAGE_TAG>, into dist/<project>/ke-app.tar"):
            self.assertEqual(len(saves), 1, "exactly one image is saved (ke-app only, R3)")
            if saves:
                outs, refs = _save_parts(saves[0]["argv"])
                self.assertEqual(refs, [f"ke-app:{WT_TAG}"], "the one image saved is ke-app:<KE_IMAGE_TAG>")
                self.assertEqual(len(outs), 1, "docker save -o <tar>")
                if outs:
                    target = Path(os.path.normpath(os.path.join(saves[0]["cwd"], outs[0])))
                    self.assertEqual(target, (repo / "dist" / project / "ke-app.tar"),
                                     "the tar is dist/<scan project>/ke-app.tar (D4 step 3)")
        with self.subTest(part="native architecture: no --platform (Q59)"):
            for r in self._docker_records(records):
                self.assertFalse([a for a in r["argv"] if a == "--platform" or a.startswith("--platform=")],
                                 f"`{' '.join(r['argv'])}` passes --platform")
        with self.subTest(part="no other image: no plain docker run, no other pull"):
            others = [e for e in self._events(records) if e in ("docker run", "pull other")
                      or e.startswith("compose pull ") or (e.startswith("run ") and e not in
                                                            ("run scan-db", "run scan"))]
            self.assertEqual(others, [], "a call other than the scan services ran an image")
        with self.subTest(part="KE_SCAN_IN points at the tar's directory when scan runs"):
            runs = [r for r in records if _event(r, self.scanner) == "run scan"]
            self.assertEqual(len(runs), 1)
            if runs:
                scan_in = runs[0]["env"].get("KE_SCAN_IN")
                self.assertTrue(scan_in, "KE_SCAN_IN is not exported to `compose run scan`")
                self.assertEqual(Path(os.path.normpath(os.path.join(runs[0]["cwd"], str(scan_in)))),
                                 repo / "dist" / project, "KE_SCAN_IN is ./dist/<scan project> (D4 step 1)")
                call = _compose_call(runs[0]["argv"])
                assert call is not None
                self.assertFalse(call["opts"].get("-v") or call["opts"].get("--volume"),
                                 "scan's mounts come from the compose file only")
        with self.subTest(part="static: /in is a read-only bind of ${KE_SCAN_IN:?}, input docker-archive"):
            svc = _scan_services()["scan"]
            ins = [m for m in _mounts(svc) if m["target"] == "/in"]
            self.assertEqual(len(ins), 1, "scan mounts /in once")
            if ins:
                self.assertEqual(ins[0]["type"], "bind")
                self.assertTrue(ins[0]["source"].startswith("${KE_SCAN_IN:?"),
                                "/in is ${KE_SCAN_IN:?...}: an unset KE_SCAN_IN fails compose")
                self.assertTrue(ins[0]["read_only"], "/in is read-only")
            words = _command_words(svc)
            self.assertIn("docker-archive:/in/ke-app.tar", words, "scan reads the image tar (D1)")
            sources = [w for w in words if re.match(r"^(?:docker|docker-archive|oci-archive|oci-dir|"
                                                    r"registry|podman|dir|file|sbom|singularity):", w)
                       or ("/" in w and ":" in w and not w.startswith("/"))]
            self.assertEqual(sources, ["docker-archive:/in/ke-app.tar"], "scan names one input, the tar")
            text = SCAN_COMPOSE.read_text(encoding="utf-8")
            names = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", text))
            self.assertEqual(names, {"KE_SCAN_IN"}, "KE_SCAN_IN is the only interpolated variable (D1)")

    def test_scan_refuses_malformed_image_tag(self):
        repo = self._repo()
        bad = {
            "unset": None, "empty": "", "local": "local", "uppercase hex": "wt-0123456789AB",
            "11 hex": "wt-0123456789a", "13 hex": "wt-0123456789abc", "no prefix": "0123456789ab",
            "trailing newline": WT_TAG + "\n", "second line": WT_TAG + "\n" + WT_TAG,
            "shell metacharacter": WT_TAG + ";true", "leading space": " " + WT_TAG,
            "path": "../" + WT_TAG, "non-ASCII digit": "wt-0123456789a١",
        }
        for case, tag in bad.items():
            with self.subTest(case=case):
                result, records = self._run(repo, tag=tag)
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"{case}: scan.sh accepted KE_IMAGE_TAG={tag!r}")
                self.assertEqual([r["argv"] for r in self._docker_records(records)], [],
                                 f"{case}: docker was called before the tag was checked (D4 step 1)")
                self.assertIn("KE_IMAGE_TAG", out, f"{case}: the refusal names KE_IMAGE_TAG")
                self.assertEqual([n for n in self._left(repo) if n.startswith("ke-scan-")], [],
                                 f"{case}: a dist/ke-scan-* directory was left behind")
        with self.subTest(case="control: wt-<12 hex> reaches docker"):
            result, records = self._run(repo)
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertTrue(self._docker_records(records), "a valid tag made no docker call")

    # ---- PSC-3 ---------------------------------------------------------------

    def test_scan_updates_db_every_run(self):
        url = _scan_db_url()
        with self.subTest(part="static: one literal https SCAN_DB_URL (D3)"):
            if not SCAN_SH.is_file():
                self.fail(SCRIPT_MISSING)
            self.assertIsNotNone(url, "scan.sh assigns SCAN_DB_URL=https://... exactly once, as a literal")
        with self.subTest(part="static: the database volume is new with each project"):
            if not SCAN_COMPOSE.is_file():
                self.fail(COMPOSE_MISSING)
            data = _scan_compose()
            self.assertNotIn("name", data, "a top-level `name:` would pin the project (D3: new every run)")
            vol = (data.get("volumes") or {}).get("scan-db", {}) or {}
            self.assertIn("scan-db", data.get("volumes") or {}, "the scan-db volume is declared")
            self.assertNotIn("name", vol, "scan-db with a fixed `name:` is shared across projects")
            self.assertNotIn("external", vol, "an external scan-db volume outlives the project")
            self.assertEqual(sorted(data.get("volumes") or {}), ["scan-db"], "the file declares one volume")
        repo = self._repo()
        projects = []
        hostile = {"SCAN_DB_URL": "https://attacker.invalid/listing.json",
                   "GRYPE_DB_UPDATE_URL": "https://attacker.invalid/listing.json"}
        for n, extra in enumerate(({}, hostile), start=1):
            with self.subTest(run=n, caller_env=sorted(extra)):
                result, records = self._run(repo, **extra)
                self.assertEqual(result.returncode, 0, self._out(result))
                projects.append(self._assert_one_scan_project(records))
                db_runs = [r for r in records if _event(r, self.scanner) == "run scan-db"]
                self.assertEqual(len(db_runs), 1, "exactly one `run scan-db` (db update) per invocation")
                if db_runs and url:
                    call = _compose_call(db_runs[0]["argv"])
                    assert call is not None
                    self.assertIn(f"GRYPE_DB_UPDATE_URL={url}", _env_values(call),
                                  "run scan-db carries -e GRYPE_DB_UPDATE_URL=<the scan.sh constant> (D3)")
                    self.assertNotIn("attacker.invalid", " ".join(db_runs[0]["argv"]),
                                     "a caller value reached the database fetch")
        self.assertEqual(len(set(projects)), 2, f"two runs, two projects (no database reused): {projects}")

    def test_scan_db_failure_fails_closed_naming_host_and_stage(self):
        url = _scan_db_url()
        repo = self._repo()
        self.assertIsNotNone(url, "scan.sh assigns SCAN_DB_URL=https://... exactly once, as a literal")
        host = urlparse(str(url)).hostname or "<no host>"
        cases = {
            # FAKE_DOCKER_FAIL_NTH items are `<regex>#<n>` split on `|`, so
            # neither regex may hold a `|` or `#`.
            "pull": (r"(?<!-)\bpull\b#1", "pull", self.scanner),
            "fetch": (r"\brun\b.*\sscan-db(?:\s.*)?$#1", "run scan-db", host),
        }
        for stage, (rule, failing, named) in cases.items():
            with self.subTest(failing=stage):
                result, records = self._run(repo, FAKE_DOCKER_FAIL_NTH=rule)
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"a failed {stage} must fail the scan:\n{out}")
                self.assertRegex(out, r"(?i)\bstage\s+scan-db\b", "the message names stage scan-db (D3)")
                self.assertIn(named, out, f"the message names {named} (Q56(b))")
                events = self._events(records)
                self.assertEqual(events.count(failing), 1, f"the failing {stage} call is made once (no retry)")
                self.assertNotIn("run scan", events, "scan ran after the database stage failed")
                if stage == "pull":
                    self.assertNotIn("run scan-db", events, "the fetch ran after the pull failed")
                self.assertIsNone(SKIP_RX.search(out), "no skip path (Q56(b))")
                self.assertNotRegex(out, r"(?i)\bscan: (?:pass|ok)\b", "never a pass")
                calls = self._scan_calls(records)
                project = _project(calls[0]) if calls else None
                self._assert_torn_down(records, project, repo)

    # ---- U2 rework 1 (review B1, N2-N4; security M-1, L-1..L-3) -------------
    # Orchestrator rulings, handoff 2026-10-21 "U2 review CHANGES REQUESTED".

    def test_scan_interrupt_removes_own_project_containers_before_teardown(self):
        """B1 (PSC-3, D4): a signal during scan-db kills the compose client but
        the one-off scan-db container keeps running, so teardown cannot remove
        the volume or network. Cleanup force-removes the containers labelled
        com.docker.compose.project=<its own project> (`docker ps -aq --filter
        label=...`, then `docker rm -f`) before teardown.sh, and never touches
        another project's container."""
        import signal

        repo = self._repo()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sig.name):
                marker, hooks = self._scan_db_hang()
                marker.unlink(missing_ok=True)
                result, records = self._run_signalled(
                    repo, [(sig, marker)], FAKE_DOCKER_HOOKS=hooks,
                    FAKE_DOCKER_CONTAINERS=json.dumps([*OWN_CONTAINERS, *DECOY_CONTAINERS]))
                out = self._out(result)
                self.assertNotEqual(result.returncode, 0, f"an interrupted scan exited 0:\n{out}")
                project = self._assert_one_scan_project(records)
                self.assertNotIn("run scan", self._events(records), "scan ran after the interrupt")
                own_each = [{c["ID"], c["Names"].replace("{run_project}", project)} for c in OWN_CONTAINERS]
                own = set().union(*own_each)
                decoys = ({d["ID"] for d in DECOY_CONTAINERS}
                          | {d["Names"].replace("{run_project}", project) for d in DECOY_CONTAINERS})
                downs = [i for i, r in enumerate(records) if r["argv"][:2] == ["STUB", "teardown.sh"]]
                self.assertEqual(len(downs), 1, "scripts/teardown.sh must run exactly once")
                calls = [' '.join(r['argv']) for r in self._docker_records(records)]
                for names, spec in zip(own_each, OWN_CONTAINERS):
                    removed = [i for i, r in enumerate(records) if _is_rm(r["argv"]) and _rm_forced(r["argv"])
                               and names & set(_rm_targets(r["argv"]))]
                    self.assertTrue(removed, f"cleanup left the scan's own {spec['State']} scan-db container: it "
                                    "must `docker rm -f` every container (running or not) labelled "
                                    "com.docker.compose.project=<project> before teardown.sh (review B1). "
                                    f"Docker calls: {calls}")
                    if removed and downs:
                        self.assertLess(removed[0], downs[0], "the project's containers go before teardown.sh runs")
                for r in self._docker_records(records):
                    argv = r["argv"]
                    self.assertFalse(decoys & set(argv), f"`{' '.join(argv)}` names another project's container")
                    self.assertNotIn("prune", argv, f"`{' '.join(argv)}`: a prune is not scoped to the scan project")
                    for f in _filter_values(argv):
                        if f.startswith("label=com.docker.compose.project="):
                            self.assertEqual(f.split("=", 2)[2], project,
                                             f"`{' '.join(argv)}` filters on another project's label")
                    if _is_rm(argv):
                        self.assertFalse(set(_rm_targets(argv)) - own,
                                         f"`{' '.join(argv)}` removes something that is not the scan's container")
                self._assert_torn_down(records, project, repo)

    def test_scan_tar_is_world_readable_before_any_compose_call(self):
        """M-1: on a Linux engine `docker save -o` writes the tar 0600 and the
        `scan` service (root, cap_drop ALL) cannot read it. After the save and
        before any compose call, scan.sh runs `chmod 0644` on the tar."""
        repo = self._repo()
        modes = self.tmp / "tar-modes.jsonl"
        once = self.tmp / "first-compose-call"
        hooks = json.dumps([{"on": r"^compose\b", "once": str(once),
                             "stat": [str(repo / "dist" / "ke-scan-*" / "ke-app.tar"), str(modes)]}])
        result, records = self._run(repo, FAKE_DOCKER_SAVE_MODE="600", FAKE_DOCKER_HOOKS=hooks)
        self.assertEqual(result.returncode, 0, self._out(result))
        with self.subTest(part="the tar's mode when the first compose call runs"):
            seen = [json.loads(line) for line in modes.read_text(encoding="utf-8").splitlines()
                    if line.strip()] if modes.is_file() else []
            self.assertEqual(len(seen), 1, "harness: the first compose call was not seen")
            tars = seen[0] if seen else {}
            self.assertEqual(len(tars), 1, f"exactly one dist/ke-scan-*/ke-app.tar exists then: {tars}")
            for path, mode in tars.items():
                self.assertEqual(oct(mode), oct(0o644),
                                 f"{Path(path).name} is {oct(mode)} at the first compose call: the cap-dropped "
                                 "scan cannot read a 0600 tar on Linux; chmod 0644 after save (security M-1)")
        with self.subTest(part="static: chmod 0644 of the tar after `docker save`, before the first `docker compose`"):
            lines = _script_lines()
            # Command lines only (an `echo` naming the hand command does not count).
            saves = [i for i, line in enumerate(lines) if re.match(r"\s*docker\s+(?:image\s+)?save\b", line)]
            composes = [i for i, line in enumerate(lines) if re.match(r"\s*docker\s+compose\b", line)]
            chmods = [i for i, line in enumerate(lines) if re.match(r"\s*" + _TAR_CHMOD.pattern, line)]
            self.assertTrue(saves and composes, "harness: no `docker save` / `docker compose` command line found")
            self.assertEqual(len(chmods), 1, 'scan.sh runs `chmod 0644 -- "$KE_SCAN_IN/ke-app.tar"` once')
            if chmods and saves and composes:
                self.assertLess(saves[0], chmods[0], "the chmod comes after `docker save`")
                self.assertLess(chmods[0], composes[0], "the chmod comes before the first `docker compose`")

    def test_scan_does_not_widen_scanner_privileges(self):
        """M-1 guard: the fix is the tar's mode, never more privilege: no
        cap_add, privileged, extra capability, read-only root off, or a chmod
        other than 0644 (no 777)."""
        for path, message in ((SCAN_SH, SCRIPT_MISSING), (SCAN_COMPOSE, COMPOSE_MISSING)):
            if not path.is_file():
                self.fail(message)
        compose_text = "\n".join(line for line in SCAN_COMPOSE.read_text(encoding="utf-8").splitlines()
                                 if not line.lstrip().startswith("#"))
        texts = {"scripts/scan.sh": "\n".join(_script_lines()), SCAN_FILE_NAME: compose_text}
        forbidden = {
            "cap_add": r"(?i)\bcap_add\b|--cap-add\b",
            "privileged": r"(?i)\bprivileged\b",
            "a DAC or admin capability": r"(?i)\b(?:CAP_)?(?:DAC_OVERRIDE|DAC_READ_SEARCH|FOWNER|SYS_ADMIN)\b",
            "read-only root off": r"(?i)\bread_only:\s*false\b|--read-only=false",
            "unconfined": r"(?i)unconfined",
        }
        for name, text in texts.items():
            for what, rx in forbidden.items():
                with self.subTest(file=name, forbidden=what):
                    self.assertIsNone(re.search(rx, text), f"{name} uses {what} (security M-1: chmod 0644 only)")
        with self.subTest(part="every chmod in scan.sh is 0644 (never 777, a+w, -R)"):
            for line in _script_lines():
                if re.search(r"\bchmod\b", line):
                    self.assertRegex(line, r"\bchmod\s+(?:--\s+)?0?644\s", f"scan.sh: {line.strip()}")

    def test_scan_second_signal_does_not_abort_cleanup(self):
        """L-1: once cleanup starts it ignores INT and TERM, so a second
        signal (to the whole process group) cannot stop teardown.sh halfway
        or skip removing dist/<project>."""
        import signal

        repo = self._repo()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sig.name):
                db_marker, hooks = self._scan_db_hang()
                db_marker.unlink(missing_ok=True)
                td_marker = self.tmp / "teardown-running"
                td_marker.unlink(missing_ok=True)
                result, records = self._run_signalled(
                    repo, [(sig, db_marker), (sig, td_marker)], FAKE_DOCKER_HOOKS=hooks,
                    FAKE_TEARDOWN_MARKER=str(td_marker), FAKE_TEARDOWN_SLEEP="3")
                out = self._out(result)
                events = self._events(records)
                self.assertEqual(events.count("teardown.sh"), 1, "teardown.sh starts once")
                self.assertIn("teardown-end", events,
                              f"a second {sig.name} during cleanup killed teardown.sh halfway (security L-1): "
                              f"cleanup must ignore INT and TERM (exit {result.returncode}):\n{out}")
                self.assertEqual([n for n in self._left(repo) if n.startswith("ke-scan-")], [],
                                 "dist/<project> was left: cleanup was aborted before `rm -rf`")
                self.assertNotEqual(result.returncode, 0, "an interrupted scan exited 0")
                shutil.rmtree(repo / "dist", True)

    def test_scan_refuses_existing_scan_dir(self):
        """L-2: dist/<project> must be new. A path already there (a planted
        directory, or a symlink to one) fails the run before `docker save`."""
        repo = self._repo()
        plantbin = self.tmp / "plantbin"
        plantbin.mkdir(exist_ok=True)
        for tool in _PLANTED_TOOLS:
            (plantbin / tool).write_text(_PLANTER, encoding="utf-8", newline="\n")
            (plantbin / tool).chmod(0o755)
        real_path = os.pathsep.join([str(self.tmp / "fakebin"), os.environ.get("PATH", "/usr/bin:/bin")])
        for kind in ("directory", "symlink"):
            with self.subTest(planted=kind):
                once = self.tmp / f"planted-{kind}"
                shutil.rmtree(once, True)
                result, records = self._run(repo, PATH=os.pathsep.join([str(plantbin), real_path]),
                                            FAKE_REAL_PATH=real_path, FAKE_PLANT_ONCE=str(once),
                                            FAKE_PLANT_KIND=kind,
                                            FAKE_PLANT_TARGET=str(self.tmp / f"elsewhere-{kind}"))
                out = self._out(result)
                self.assertTrue(once.exists(), "harness: no dist/ke-scan-* path was planted")
                self.assertNotEqual(result.returncode, 0,
                                    f"scan.sh accepted a pre-existing dist/<project> ({kind}) (security L-2: "
                                    f"`mkdir -m 0755 -- \"$KE_SCAN_IN\"`, no -p):\n{out}")
                self.assertNotIn("save", self._events(records), "the image was saved into a pre-existing path")
                self.assertEqual(self._scan_calls(records), [], "a scan compose call ran")
                shutil.rmtree(repo / "dist", True)

    def test_scan_clears_caller_docker_default_platform(self):
        """L-3: a caller DOCKER_DEFAULT_PLATFORM (an unverified architecture
        such as linux/s390x) never reaches any docker call or teardown.sh."""
        repo = self._repo()
        with self.subTest(part="harness: the fake records the variable when it is set"):
            env = {**self._env(), "DOCKER_DEFAULT_PLATFORM": "linux/s390x",
                   "FAKE_DOCKER_RECORD_ENV": "DOCKER_DEFAULT_PLATFORM"}
            subprocess.run(["docker", "version"], env=env, capture_output=True, text=True, timeout=60,
                           executable=str(self.tmp / "fakebin" / "docker"))
            recs = fake_docker.records(self.json)
            self.assertEqual([r["env"].get("DOCKER_DEFAULT_PLATFORM") for r in recs], ["linux/s390x"])
        result, records = self._run(repo, DOCKER_DEFAULT_PLATFORM="linux/s390x",
                                    FAKE_DOCKER_RECORD_ENV="DOCKER_DEFAULT_PLATFORM")
        self.assertEqual(result.returncode, 0, self._out(result))
        self.assertTrue(self._docker_records(records), "no docker call was made")
        leaked = [" ".join(r["argv"]) for r in self._docker_records(records)
                  if "DOCKER_DEFAULT_PLATFORM" in r["env"]]
        self.assertEqual(leaked, [], "the caller's DOCKER_DEFAULT_PLATFORM reached these docker calls "
                         "(security L-3: unset it with the other caller keys)")
        downs = [r for r in records if r["argv"][:2] == ["STUB", "teardown.sh"]]
        self.assertEqual(len(downs), 1)
        if downs:
            self.assertEqual(downs[0]["env"]["DOCKER_DEFAULT_PLATFORM"], "<unset>",
                             "teardown.sh inherited the caller's DOCKER_DEFAULT_PLATFORM")

    def test_scan_fails_when_teardown_fails(self):
        """N2 (D4): a failed teardown fails an otherwise passing scan, naming
        the project and the hand command."""
        repo = self._repo()
        result, records = self._run(repo, FAKE_TEARDOWN_EXIT="1")
        out = self._out(result)
        project = self._assert_one_scan_project(records)
        self.assertNotEqual(result.returncode, 0, f"a failed teardown.sh let the scan pass (review N2):\n{out}")
        self.assertIn(project, out, "the failure names the scan project")
        self.assertIn("down --volumes", out, "the failure gives the hand command (D4)")
        self.assertEqual([n for n in self._left(repo) if n.startswith("ke-scan-")], [],
                         "dist/<project> was left after the failed teardown")

    def test_scan_removes_tar_on_every_exit(self):
        """N3, PSC-6 (§2.6 item 5): pass, a failure at each stage, INT and
        TERM all end with teardown.sh --volumes once under the scan project
        and dist/<project> gone. A save failure makes no compose call; a scan
        failure fails naming `stage scan`; INT and TERM exit 130 and 143."""
        import signal

        repo = self._repo()
        cases = {
            "pass": (None, None),
            "save fails": (r"^save\b#1", "save"),
            "pull fails": (r"(?<!-)\bpull\b#1", "scan-db"),
            "fetch fails": (r"\brun\b.*\sscan-db$#1", "scan-db"),
            "scan fails": (r"\brun\b.*\sscan$#1", "scan"),
        }
        for case, (rule, stage) in cases.items():
            with self.subTest(exit=case):
                result, records = self._run(repo, **({"FAKE_DOCKER_FAIL_NTH": rule} if rule else {}))
                out = self._out(result)
                calls = self._scan_calls(records)
                project = _project(calls[0]) if calls else None
                if stage is None:
                    self.assertEqual(result.returncode, 0, out)
                else:
                    self.assertNotEqual(result.returncode, 0, f"{case}: the scan passed:\n{out}")
                    self.assertRegex(out, rf"(?i)\bstage\s+{re.escape(stage)}(?![\w-])",
                                     f"{case}: the message names stage {stage}")
                    self.assertNotIn("== scan: done ==", out, f"{case}: the script went on to the end")
                if case == "save fails":
                    self.assertEqual([" ".join(r["argv"]) for r in records if r["argv"][:1] == ["compose"]], [],
                                     "a compose call followed the failed save (review N3)")
                self._assert_torn_down(records, project, repo)
        for sig, code in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            with self.subTest(exit=sig.name):
                marker, hooks = self._scan_db_hang()
                marker.unlink(missing_ok=True)
                result, records = self._run_signalled(repo, [(sig, marker)], FAKE_DOCKER_HOOKS=hooks)
                self.assertEqual(result.returncode, code,
                                 f"{sig.name}: the INT/TERM traps `exit {code}` so the EXIT trap runs (D4); "
                                 f"exit {result.returncode}:\n{self._out(result)}")
                self.assertNotIn("run scan", self._events(records), "scan ran after the interrupt")
                self._assert_torn_down(records, self._assert_one_scan_project(records), repo)

    def test_scan_ignores_caller_env_file_and_compose_settings(self):
        """N4 (D4: no caller value reaches the scan): a hostile KE_ENV_FILE,
        COMPOSE_PROFILES and COMPOSE_ENV_FILES, and a repo .env, change
        neither the project, the files nor the env file."""
        repo = self._repo()
        (repo / ".env").write_text("COMPOSE_PROFILES=evil\nKE_SCAN_IN=/etc\nCOMPOSE_FILE=docker-compose.yml\n",
                                   encoding="utf-8", newline="\n")
        result, records = self._run(repo, KE_ENV_FILE=".env", COMPOSE_PROFILES="evil,gates",
                                    COMPOSE_ENV_FILES=".env")
        self.assertEqual(result.returncode, 0, self._out(result))
        self._assert_one_scan_project(records)
        compose = [r for r in self._docker_records(records) if r["argv"][:1] == ["compose"]]
        self.assertTrue(compose, "no compose call was made")
        for r in compose:
            call = _compose_call(r["argv"])
            assert call is not None
            with self.subTest(call=" ".join(r["argv"])):
                self.assertEqual(call["global"].get("--env-file"), [".env.example"],
                                 "every compose call passes --env-file .env.example, never the caller's (N4)")
                self.assertNotIn("--profile", call["global"], "a compose call activates a profile")
                for key in ("COMPOSE_PROFILES", "COMPOSE_ENV_FILES"):
                    self.assertNotIn(key, r["env"], f"the caller's {key} reached `{' '.join(r['argv'])}`")
                if "KE_ENV_FILE" in r["env"]:
                    self.assertEqual(r["env"]["KE_ENV_FILE"], ".env.example")
        downs = [r for r in records if r["argv"][:2] == ["STUB", "teardown.sh"]]
        self.assertEqual(len(downs), 1)
        if downs:
            self.assertEqual(downs[0]["env"]["KE_ENV_FILE"], ".env.example", "teardown gets the caller's env file")
            for key in ("COMPOSE_PROFILES", "COMPOSE_ENV_FILES"):
                self.assertEqual(downs[0]["env"][key], "<unset>", f"teardown.sh inherited the caller's {key}")

    # ---- PSC-4 (unit 3): the policy's outcome, against a fake scanner ---------

    @staticmethod
    def _scan_hook(table: str, code: int) -> str:
        """The fake `compose run ... scan` prints `table` and exits `code`."""
        return json.dumps([{"on": r"\brun\b.*\sscan$", "stdout": table, "exit": code}])

    def _assert_one_gating_run(self, records: list[dict[str, Any]]) -> None:
        runs = [r for r in records if _event(r, self.scanner) == "run scan"]
        self.assertEqual(len(runs), 1, "one grype run gates and reports (D5); no retry, no second run")
        if runs:
            call = _compose_call(runs[0]["argv"])
            assert call is not None
            self.assertEqual(sorted(call["opts"]), ["--pull", "--rm"],
                             f"`{' '.join(runs[0]['argv'])}`: run scan takes only --rm and --pull never; no -e, "
                             "--entrypoint or other option can change the policy (D5)")
            self.assertEqual(call["rest"], [], "nothing follows the service name: the policy is the compose "
                             "command (D1)")

    def test_scan_fails_on_fixed_high(self):
        """PSC-4 (§2.6 item 4): grype finds a fixed High and exits non-zero
        (2, as `--fail-on` does): scan.sh exits non-zero naming `stage scan`
        and grype's status, after printing grype's whole table."""
        repo = self._repo()
        result, records = self._run(repo, FAKE_DOCKER_HOOKS=self._scan_hook(FIXED_HIGH_TABLE, 2))
        out = self._out(result)
        self.assertNotEqual(result.returncode, 0, f"a fixed High let the scan pass (PSC-4):\n{out}")
        with self.subTest(part="names stage scan and grype's exit status (D4 step 5)"):
            self.assertRegex(out, r"scan: FAIL \(stage scan: grype exited 2\b",
                             "the failure reads `scan: FAIL (stage scan: grype exited <n>: ...)` (D4 step 5)")
            self.assertNotIn("== scan: done ==", out, "the script went on to the end after a failed scan")
        with self.subTest(part="the table is in scan.sh's output, every row (PSC-7: the CI log holds it)"):
            for row in FIXED_HIGH_TABLE.splitlines():
                self.assertIn(row, out, "a row of grype's table is missing from scan.sh's output")
        self._assert_one_gating_run(records)
        self._assert_torn_down(records, self._assert_one_scan_project(records), repo)

    def test_scan_reports_but_passes_unfixed_and_lower(self):
        """PSC-4: only suppressed (unfixed, ignored) rows and fixed rows below
        High: grype exits 0, scan.sh exits 0 and prints every row."""
        repo = self._repo()
        result, records = self._run(repo, FAKE_DOCKER_HOOKS=self._scan_hook(BELOW_THRESHOLD_TABLE, 0))
        out = self._out(result)
        self.assertEqual(result.returncode, 0, f"unfixed and lower matches failed the scan (PSC-4):\n{out}")
        with self.subTest(part="every row printed, the run reaches the end"):
            for row in BELOW_THRESHOLD_TABLE.splitlines():
                self.assertIn(row, out, "a row of grype's table is missing from scan.sh's output (PSC-4: "
                              "every other match is printed)")
            self.assertIn("== scan: done ==", out)
            self.assertNotIn("scan: FAIL", out)
        self._assert_one_gating_run(records)
        self._assert_torn_down(records, self._assert_one_scan_project(records), repo)

    # ---- unit 3 carry-ins (review r1-a, r1-b; security I-4, I-6) -------------

    def test_scan_fails_when_container_listing_fails(self):
        """Review r1-a: cleanup lists the project's containers with `docker ps`
        (or `container ls`). If that listing fails, cleanup cannot know what
        is left: it prints a `scan: FAIL (...)` line naming the project and
        the run exits 1, even when everything else passed."""
        repo = self._repo()
        listing = "|".join(rx + "#1" for rx in (r"^ps\b", r"^container ls\b", r"^container list\b",
                                                r"^container ps\b"))
        result, records = self._run(repo, FAKE_DOCKER_FAIL_NTH=listing)
        out = self._out(result)
        project = self._assert_one_scan_project(records)
        lists = [r for r in self._docker_records(records)
                 if r["argv"][:1] == ["ps"] or r["argv"][:2] in (["container", "ls"], ["container", "list"],
                                                                 ["container", "ps"])]
        self.assertTrue(lists, "harness: cleanup made no container listing call")
        self.assertEqual(result.returncode, 1, f"a failed `docker ps` in cleanup was silent (review r1-a: the "
                         f"process substitution hides its status); exit {result.returncode}:\n{out}")
        fails = [line for line in result.stderr.splitlines() if line.startswith("scan: FAIL (")]
        self.assertTrue([line for line in fails if project in line],
                        f"no `scan: FAIL (...)` line names project {project} (review r1-a):\n{out}")
        self._assert_torn_down(records, project, repo)

    def test_scan_container_removal_failure_gives_working_hand_command(self):
        """Review r1-b: when `docker rm -f` fails, the message gives a hand
        command that removes the project's containers, running or not, and
        nothing else, e.g. `docker rm -f $(docker ps -aq --filter
        label=com.docker.compose.project=<project>)`. The command is taken
        from the output and run against a fresh fake daemon holding the same
        containers."""
        repo = self._repo()
        containers = json.dumps([*OWN_CONTAINERS, *DECOY_CONTAINERS])
        result, records = self._run(repo, FAKE_DOCKER_CONTAINERS=containers,
                                    FAKE_DOCKER_FAIL_NTH=r"^rm\b#1|^container rm\b#1")
        out = self._out(result)
        project = self._assert_one_scan_project(records)
        self.assertTrue([r for r in self._docker_records(records) if _is_rm(r["argv"])],
                        "harness: cleanup made no `docker rm` call")
        self.assertNotEqual(result.returncode, 0, f"a failed `docker rm -f` let the scan pass:\n{out}")
        commands = _hand_rm_commands(out)
        self.assertTrue(commands, f"the removal failure gives no `docker rm` hand command (review r1-b):\n{out}")
        own = {c["ID"] for c in OWN_CONTAINERS} | {c["Names"].replace("{run_project}", project)
                                                   for c in OWN_CONTAINERS}
        decoys = ({d["ID"] for d in DECOY_CONTAINERS}
                  | {d["Names"].replace("{run_project}", project) for d in DECOY_CONTAINERS})
        seed = "".join(json.dumps(r) + "\n" for r in records
                       if r["argv"][:1] == ["compose"] and "run" in r["argv"])
        verdicts: list[str] = []
        for cmd in commands:
            hand_log = self.tmp / "hand.jsonl"
            hand_log.write_text(seed, encoding="utf-8")
            env = {"PATH": f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
                   "HOME": str(self.tmp), "FAKE_DOCKER_JSON": str(hand_log), "FAKE_DOCKER_CONTAINERS": containers}
            ran = subprocess.run(["bash", "-c", cmd], cwd=self.tmp, env=env, capture_output=True, text=True,
                                 timeout=60)
            rms = [r for r in fake_docker.records(hand_log) if _is_rm(r["argv"]) and _rm_forced(r["argv"])]
            targets = {t for r in rms for t in _rm_targets(r["argv"])}
            removed = [spec for spec in OWN_CONTAINERS
                       if {spec["ID"], spec["Names"].replace("{run_project}", project)} & targets]
            if ran.returncode == 0 and len(removed) == len(OWN_CONTAINERS) and not targets & decoys \
                    and not targets - own:
                verdicts = []
                break
            verdicts.append(f"`{cmd}`: exit {ran.returncode}, forced rm of {sorted(targets)} "
                            f"(own: {sorted(own)}; must not touch {sorted(decoys)}) {ran.stderr.strip()}")
        self.assertEqual(verdicts, [], "no hand command in the output removes exactly the project's containers, "
                         "running and created (review r1-b)")

    def test_scan_cleanup_ignores_signals_before_clearing_exit_trap(self):
        """Security I-4: in the EXIT-trap function, INT and TERM are ignored
        before (or in the same `trap` as) the EXIT trap is cleared, so no
        signal lands between the two and exits with no cleanup left."""
        if not SCAN_SH.is_file():
            self.fail(SCRIPT_MISSING)
        lines = _script_lines()
        handlers = [w[1] for w in (_trap_words(line) for line in lines if not line[:1].isspace())
                    if w and len(w) >= 3 and "EXIT" in w[2:] and w[1] not in ("", "-")]
        self.assertEqual(len(handlers), 1, "harness: scan.sh installs one EXIT trap function at top level")
        body = _function_body(lines, handlers[0]) if handlers else []
        self.assertTrue(body, f"harness: the body of the EXIT trap function {handlers[:1]} was not found")
        traps = [w for w in (_trap_words(line) for line in body) if w]
        self.assertTrue(traps, "the EXIT trap function sets no trap")
        if traps:
            first = traps[0]
            self.assertTrue(first[1] == "" and {"INT", "TERM"} <= set(first[2:]),
                            f"the first trap in {handlers[0]}() is `{' '.join(first)}`: it must be "
                            "`trap '' INT TERM` (or `trap '' INT TERM EXIT`), before `trap - EXIT` (security I-4)")

    def test_scan_project_name_uses_srandom(self):
        """Security I-6: the project name is `ke-scan-${SRANDOM}` (32 bits
        from the OS, bash >= 5.1), not the 15-bit `RANDOM` LCG. It still
        matches ke-scan-<digits> (the run tests check that)."""
        if not SCAN_SH.is_file():
            self.fail(SCRIPT_MISSING)
        lines = _script_lines()
        sets = [line for line in lines if re.match(r"\s*(?:export\s+)?COMPOSE_PROJECT_NAME=", line)]
        self.assertEqual(len(sets), 1, "scan.sh assigns COMPOSE_PROJECT_NAME once")
        if sets:
            self.assertRegex(sets[0].strip(),
                             # `${SRANDOM-}` / `${SRANDOM:-}` allowed since unit 4: the L-1
                             # check (orchestrator ruling, handoff 2026-10-21 "U3 review
                             # APPROVED") then reports an unset SRANDOM, not `set -u`.
                             r"""^(?:export\s+)?COMPOSE_PROJECT_NAME=(["']?)ke-scan-(?:\$\{SRANDOM(?::?-)?\}|\$SRANDOM)+\1$""",
                             "the project is ke-scan-${SRANDOM} (security I-6)")
        self.assertEqual([line.strip() for line in lines if re.search(r"(?<![A-Za-z_])RANDOM\b", line)], [],
                         "scan.sh still uses bash's 15-bit RANDOM (security I-6)")
        with self.subTest(part="harness: this bash has SRANDOM (5.1 or later)"):
            v = subprocess.run(["bash", "-c", 'echo "${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"'],
                               capture_output=True, text=True, timeout=30).stdout.split()
            self.assertGreaterEqual((int(v[0]), int(v[1])), (5, 1), "bash < 5.1 has no SRANDOM")

    # ---- unit 4 carry-ins (review r3-1; security L-1, review r3-5) ----------

    def test_scan_cleanup_with_only_other_projects_containers_removes_nothing(self):
        """Review r3-1: the daemon holds only other projects' containers (one
        under a look-alike name), so cleanup's own-label listing is empty. It
        then makes no `docker rm` call at all (a real `docker rm -f ""` exits
        1: "container name cannot be empty"), prints no `scan: FAIL` line, and
        the passing scan exits 0. Kills the reviewer's m1 (`elif` -> `else`)."""
        repo = self._repo()
        result, records = self._run(repo, FAKE_DOCKER_CONTAINERS=json.dumps(DECOY_CONTAINERS))
        out = self._out(result)
        project = self._assert_one_scan_project(records)
        lists = [r for r in self._docker_records(records)
                 if r["argv"][:1] == ["ps"] or r["argv"][:2] in (["container", "ls"], ["container", "list"],
                                                                 ["container", "ps"])]
        self.assertTrue(lists, "harness: cleanup made no container listing call")
        rms = [" ".join(r["argv"]) for r in self._docker_records(records) if _is_rm(r["argv"])]
        self.assertEqual(rms, [], "cleanup ran `docker rm` with no container of its own project to remove "
                         "(review r3-1: an empty listing must make no rm call)")
        self.assertNotIn("scan: FAIL", out, "a clean scan with only other projects' containers printed a FAIL line")
        self.assertEqual(result.returncode, 0, out)
        self._assert_torn_down(records, project, repo)

    # Older bash, simulated under the gates image's bash 5.2 by BASH_ENV (read
    # before the script runs): `unset SRANDOM` drops bash's special variable,
    # as on bash < 5.1; assigning it afterwards makes it a plain variable that
    # holds the caller's value, as bash 5.0 does with SRANDOM in the
    # environment (security L-1 probe: `SRANDOM=evil/../..` gives
    # `ke-scan-evil/../..`).
    _OLD_BASH_ENV = 'unset SRANDOM\nif [ "${SIM_SRANDOM+x}" = x ]; then SRANDOM="$SIM_SRANDOM"; fi\n'
    _BAD_SRANDOM = {
        "bash < 5.1: SRANDOM unset": None,
        "bash 5.0: SRANDOM empty": "",
        "bash 5.0: SRANDOM a path": "evil/../..",
        "bash 5.0: SRANDOM a command separator": "1;id",
        "bash 5.0: SRANDOM a substitution": "$(id)",
        "bash 5.0: SRANDOM with a space": "1 2",
        "bash 5.0: SRANDOM with a newline": "1\n2",
        "bash 5.0: SRANDOM digits then letters": "12ab",
        "bash 5.0: SRANDOM negative": "-1",
    }

    def _old_bash_env(self, value: str | None) -> dict[str, str]:
        env_file = self.tmp / "old-bash-env.sh"
        env_file.write_text(self._OLD_BASH_ENV, encoding="utf-8", newline="\n")
        extra = {"BASH_ENV": str(env_file)}
        if value is not None:
            extra["SIM_SRANDOM"] = value
        return extra

    def test_scan_refuses_a_project_name_that_is_not_ke_scan_digits(self):
        """Security L-1 (review r3-5): `${SRANDOM}` exists only in bash >= 5.1.
        On an older bash it is unset (`set -u` stops with a bare "unbound
        variable") or a caller's SRANDOM is used verbatim in
        COMPOSE_PROJECT_NAME, KE_SCAN_IN (`mkdir`, `rm -rf`) and the hand
        commands. Orchestrator ruling: scan.sh fails with a clear
        `scan: FAIL (...)` line unless the project matches ^ke-scan-[0-9]+$,
        before any docker call (so before the cleanup trap, which lists and
        tears down the project) and before creating dist/."""
        with self.subTest(case="control: bash 5.0 with SRANDOM=4242 in the environment runs as ke-scan-4242"):
            repo = self._repo()
            result, records = self._run(repo, **self._old_bash_env("4242"))
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertEqual(self._assert_one_scan_project(records), "ke-scan-4242",
                             "harness: the BASH_ENV simulation did not set the project")
        for case, value in self._BAD_SRANDOM.items():
            with self.subTest(case=case):
                repo = self._repo()
                # The raw call log, not fake_docker.records(): a project with a
                # newline in it would break the log's JSON lines.
                result = subprocess.run(["bash", "scripts/scan.sh"], cwd=repo,
                                        env=self._env(WT_TAG, **self._old_bash_env(value)),
                                        capture_output=True, text=True, timeout=120)
                out = self._out(result)
                calls = self.json.read_text(encoding="utf-8").strip()
                self.assertNotEqual(result.returncode, 0, f"{case}: scan.sh ran with a malformed project:\n{out}")
                self.assertEqual(calls, "",
                                 f"{case}: docker (or teardown.sh) was called with a project that is not "
                                 f"ke-scan-<digits> (security L-1):\n{out}")
                self.assertFalse((repo / "dist").exists(),
                                 f"{case}: dist/ was created before the project name was checked (L-1)")
                fails = [line for line in result.stderr.splitlines() if line.startswith("scan: FAIL (")]
                self.assertTrue([line for line in fails if re.search(r"(?i)project|ke-scan|SRANDOM|bash", line)],
                                f"{case}: no `scan: FAIL (...)` line names the malformed project or the bash "
                                f"version (security L-1: a clear message, not a bare unbound variable):\n{out}")


# PSC-4 fake grype tables (`-o table` with `--show-suppressed`). Ids are made
# up; only the shape matters.
FIXED_HIGH_TABLE = (
    "NAME         INSTALLED  FIXED IN   TYPE        VULNERABILITY        SEVERITY\n"
    "quinn-proto  0.11.14    0.11.15    rust-crate  GHSA-aaaa-bbbb-cccc  High\n"
    "pip          25.0.1     25.3       python      GHSA-dddd-eeee-ffff  Medium\n"
    "libc6        2.36-9                deb         CVE-2099-0001        High (suppressed)\n"
)
BELOW_THRESHOLD_TABLE = (
    "NAME         INSTALLED  FIXED IN   TYPE        VULNERABILITY        SEVERITY\n"
    "pip          25.0.1     25.3       python      GHSA-dddd-eeee-ffff  Medium\n"
    "libc6        2.36-9                deb         CVE-2099-0001        Critical (suppressed)\n"
    "zlib1g       1.2.13                deb         CVE-2099-0002        High (suppressed)\n"
)


def _trap_words(line: str) -> list[str] | None:
    """`trap ACTION SIG...` as words (SIG prefixes dropped), else None."""
    import shlex

    if not re.match(r"\s*trap\s", line):
        return None
    try:
        words = shlex.split(line.strip(), comments=True)
    except ValueError:
        return None
    if len(words) < 2:
        return None
    return words[:2] + [w.upper().removeprefix("SIG") for w in words[2:]]


def _function_body(lines: list[str], name: str) -> list[str]:
    """The lines of `name() {` ... the closing `}` at column 0."""
    start = [i for i, line in enumerate(lines)
             if re.match(rf"\s*(?:function\s+)?{re.escape(name)}\s*(?:\(\s*\))?\s*\{{\s*$", line)]
    if not start:
        return []
    body: list[str] = []
    for line in lines[start[0] + 1:]:
        if line.rstrip() == "}":
            return body
        body.append(line)
    return []


_HAND_RM = re.compile(r"docker\s+(?:container\s+)?rm\b")


def _hand_rm_commands(text: str) -> list[str]:
    """Each `docker rm ...` in a message, up to the end of its line or an
    unbalanced `)` (the message's own closing parenthesis)."""
    found: list[str] = []
    for m in _HAND_RM.finditer(text):
        end = text.find("\n", m.start())
        end = len(text) if end < 0 else end
        depth, i = 0, m.start()
        while i < end:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        found.append(text[m.start():i].rstrip().rstrip(".,;").rstrip("'\"`").rstrip())
    return found


_TAR_CHMOD = re.compile(r'\bchmod\s+(?:--\s+)?0?644\s+(?:--\s+)?"?\$(?:KE_SCAN_IN|\{KE_SCAN_IN\})/ke-app\.tar"?')


def _is_rm(argv: list[str]) -> bool:
    return argv[:1] == ["rm"] or argv[:2] == ["container", "rm"]


def _rm_forced(argv: list[str]) -> bool:
    return "--force" in argv or any(a.startswith("-") and not a.startswith("--") and "f" in a[1:] for a in argv)


def _rm_targets(argv: list[str]) -> list[str]:
    return [a for a in argv[1 if argv[:1] == ["rm"] else 2:] if not a.startswith("-")]


def _filter_values(argv: list[str]) -> list[str]:
    out: list[str] = []
    for i, a in enumerate(argv):
        if a in ("--filter", "-f") and i + 1 < len(argv):
            out.append(argv[i + 1])
        elif a.startswith("--filter="):
            out.append(a.split("=", 1)[1])
    return out


# --------------------------------------------------------------------------
# PSC-5: docker/scan-ignore.yaml
# --------------------------------------------------------------------------

ENTRY_KEYS = {"vulnerability", "package", "reason", "until"}
REQUIRED_KEYS = ("vulnerability", "reason", "until")
CVE_RE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}", re.ASCII)
GHSA_RE = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}", re.ASCII)
CAP_DAYS = 90


def check_scan_ignores(data: Any, today: dt.date) -> list[str]:
    """Every rule D5 sets for the parsed ignore file; [] when it is valid."""
    errors: list[str] = []
    if not isinstance(data, dict) or set(data) != {"ignore"}:
        keys = sorted(map(str, data)) if isinstance(data, dict) else type(data).__name__
        return [f"the top level must be exactly one key, `ignore` (found {keys})"]
    entries = data["ignore"]
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        return [f"`ignore` must be a list (found {type(entries).__name__})"]
    seen: set[tuple[str, str | None]] = set()
    for i, entry in enumerate(entries):
        where = f"ignore[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where} is not a mapping")
            continue
        unknown = sorted(map(str, set(entry) - ENTRY_KEYS))
        if unknown:
            errors.append(f"{where} has unknown key(s) {unknown}")
        for key in REQUIRED_KEYS:
            if key not in entry:
                errors.append(f"{where} has no `{key}`")
        vuln = entry.get("vulnerability")
        if "vulnerability" in entry and not (isinstance(vuln, str) and (CVE_RE.fullmatch(vuln)
                                                                         or GHSA_RE.fullmatch(vuln))):
            errors.append(f"{where} vulnerability {vuln!r} is not a CVE or GHSA id")
        reason = entry.get("reason")
        if "reason" in entry and not (isinstance(reason, str) and reason.strip()):
            errors.append(f"{where} reason is blank or not a string")
        until = entry.get("until")
        if "until" in entry:
            if not isinstance(until, dt.date) or isinstance(until, dt.datetime):
                errors.append(f"{where} until {until!r} is not a YAML date")
            elif until < today:
                errors.append(f"{where} until {until} has passed (today {today}, UTC)")
            elif until > today + dt.timedelta(days=CAP_DAYS):
                errors.append(f"{where} until {until} is more than {CAP_DAYS} days out (today {today}, UTC)")
        name: str | None = None
        if "package" in entry:
            pkg = entry["package"]
            if not isinstance(pkg, dict) or set(pkg) != {"name"}:
                errors.append(f"{where} package must have exactly one key, `name`")
            elif not (isinstance(pkg["name"], str) and pkg["name"].strip()):
                errors.append(f"{where} package.name is blank or not a string")
            else:
                name = pkg["name"]
        key_pair = (str(vuln), name)
        if key_pair in seen:
            errors.append(f"{where} duplicates vulnerability {vuln} for package {name}")
        seen.add(key_pair)
    return errors


class ScanIgnoreTest(unittest.TestCase):
    """PSC-5, D5: the repository file, and the controls on a fixed today."""

    FIXED = dt.date(2026, 1, 15)

    @staticmethod
    def _load(text: str) -> Any:
        import yaml

        return yaml.safe_load(text)

    def _controls(self) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        t = self.FIXED
        ok_until = (t + dt.timedelta(days=30)).isoformat()

        def entry(**over: Any) -> str:
            fields = {"vulnerability": "CVE-2024-12345", "package": "{name: krb5}",
                      "reason": "gssencmode=disable, the GSSAPI path is not reached (L-13)", "until": ok_until}
            fields.update(over)
            lines = []
            for k, v in fields.items():
                if v is None:
                    continue
                lines.append(f"{k}: {v}" if k != "reason" else f"{k}: {json.dumps(v) if v != '' else chr(39)*2}")
            return "ignore:\n  - " + "\n    ".join(lines) + "\n"

        valid = [
            ("empty list (the committed start)", "ignore: []\n"),
            ("null list", "ignore:\n"),
            ("a valid CVE entry", entry()),
            ("package omitted (every package)", entry(package=None)),
            ("a GHSA id", entry(vulnerability="GHSA-abcd-1234-wxyz")),
            ("until today (valid through its day)", entry(until=t.isoformat())),
            ("until today + 90 days", entry(until=(t + dt.timedelta(days=90)).isoformat())),
            ("same id, two packages", entry() + "  - " + entry(package="{name: cyrus-sasl}")
             .split("  - ", 1)[1]),
        ]
        invalid = [
            ("no reason", entry(reason=None), "reason"),
            ("blank reason", entry(reason="   "), "reason"),
            ("empty reason", entry(reason=""), "reason"),
            ("no until", entry(until=None), "until"),
            ("until passed", entry(until=(t - dt.timedelta(days=1)).isoformat()), "passed"),
            ("until 91 days out", entry(until=(t + dt.timedelta(days=91)).isoformat()), "90 days"),
            ("until as a string", entry(until=json.dumps(ok_until)), "date"),
            ("until as a datetime", entry(until=ok_until + " 10:00:00"), "date"),
            ("unknown entry key", entry() + "    severity: low\n", "unknown"),
            ("second top-level key", entry() + "exclude: ['**/x']\n", "top level"),
            ("no ignore key", "match:\n  python:\n    using-cpes: false\n", "top level"),
            ("empty file", "", "top level"),
            ("ignore not a list", "ignore: {vulnerability: CVE-2024-12345}\n", "list"),
            ("malformed id (lowercase)", entry(vulnerability="cve-2024-12345"), "CVE or GHSA"),
            ("malformed id (short)", entry(vulnerability="CVE-2024-123"), "CVE or GHSA"),
            ("malformed id (GHSA case)", entry(vulnerability="GHSA-ABCD-1234-wxyz"), "CVE or GHSA"),
            ("no vulnerability", entry(vulnerability=None), "vulnerability"),
            ("package with a version key", entry(package="{name: krb5, version: 1.0}"), "package"),
            ("package without name", entry(package="{type: deb}"), "package"),
            ("package as a string", entry(package="krb5"), "package"),
            ("blank package name", entry(package="{name: ' '}"), "package.name"),
            ("duplicate", entry() + "  - " + entry().split("  - ", 1)[1], "duplicate"),
            ("duplicate, package omitted", entry(package=None) + "  - " + entry(package=None)
             .split("  - ", 1)[1], "duplicate"),
            ("entry not a mapping", "ignore:\n  - CVE-2024-12345\n", "mapping"),
        ]
        return valid, invalid

    def test_scan_ignores_are_justified(self):
        valid, invalid = self._controls()
        for case, text in valid:
            with self.subTest(control=case, expect="pass"):
                self.assertEqual(check_scan_ignores(self._load(text), self.FIXED), [], text)
        for case, text, rule in invalid:
            with self.subTest(control=case, expect="fail"):
                errors = check_scan_ignores(self._load(text), self.FIXED)
                self.assertTrue(errors, f"the checker accepted:\n{text}")
                self.assertRegex("\n".join(errors), rf"(?i){re.escape(rule)}", f"wrong rule for:\n{text}")
        with self.subTest(file="docker/scan-ignore.yaml"):
            if not IGNORE_FILE.is_file():
                self.fail(IGNORE_MISSING)
            today = dt.datetime.now(dt.timezone.utc).date()
            errors = check_scan_ignores(self._load(IGNORE_FILE.read_text(encoding="utf-8")), today)
            self.assertEqual(errors, [], "docker/scan-ignore.yaml breaks D5:\n" + "\n".join(errors))


# --------------------------------------------------------------------------
# PSC-8: the bundle carries no scanner
# --------------------------------------------------------------------------

_SCAN_NAMES = re.compile(r"(?i)grype|scan-db|docker-compose\.scan|(?<![\w.-])scan\.sh\b")
_IGNORE_NAME = re.compile(r"(?i)scan-ignore")


def _strip_shell_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


class ScanBundleTest(_BundleBase, unittest.TestCase):
    """PSC-8 and §2.6 item 3: bundle.sh (fake docker, BundleScriptTest
    harness) ships neither the scanner, its database, its compose file, its
    script nor its ignore file."""

    def test_bundle_has_no_scanner_or_db(self):
        missing = [_rel(p, ROOT) for p in (SCAN_COMPOSE, SCAN_SH, IGNORE_FILE) if not p.is_file()]
        self.assertEqual(missing, [], "precondition: the scan files exist in the checkout, so the bundle "
                         "could pick them up (ADR-KE-013 amendment 1, D1/D4/D5)")
        # The build tree holds them, tracked, as a real checkout would
        # (_REPO_COPY brings config/ and scripts/, not docker/).
        shutil.copyfile(SCAN_COMPOSE, self.repo / SCAN_FILE_NAME)
        (self.repo / "docker").mkdir(exist_ok=True)
        shutil.copyfile(IGNORE_FILE, self.repo / "docker" / "scan-ignore.yaml")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture: the scan files")
        tracked = set(self._git("ls-files").split())
        with self.subTest(part="harness: the build tree tracks the scan files"):
            for rel in (SCAN_FILE_NAME, "scripts/scan.sh", "docker/scan-ignore.yaml"):
                self.assertIn(rel, tracked)
        scanner = _scanner_ref()
        _, calls, out, data = self._ok()
        files = sorted(p for p in out.rglob("*") if p.is_file())
        with self.subTest(part="no bundled path names the scanner, its DB, compose file or script"):
            hits = [_rel(p, out) for p in files if _SCAN_NAMES.search(_rel(p, out))]
            self.assertEqual(hits, [], "the bundle ships a scan file")
        with self.subTest(part="no bundled file's content names them"):
            hits = [_rel(p, out) for p in files
                    if _SCAN_NAMES.search(p.read_bytes().decode("utf-8", errors="replace"))]
            self.assertEqual(hits, [], "a bundled file names grype, scan-db, the scan compose file or scan.sh")
        with self.subTest(part="the ignore file is not shipped (§2.6: no file names scan-ignore)"):
            hits = [_rel(p, out) for p in files if _IGNORE_NAME.search(_rel(p, out))
                    or _IGNORE_NAME.search(p.read_bytes().decode("utf-8", errors="replace"))]
            self.assertEqual(hits, [], "the bundle ships docker/scan-ignore.yaml or names it")
        with self.subTest(part="no manifest entry is the scanner image"):
            for e in data.get("images", []):
                text = json.dumps(e)
                self.assertNotIn(scanner.split("@", 1)[0], text, "bundle.json lists the scanner image")
                self.assertNotRegex(text, r"(?i)grype|anchore", "bundle.json lists the scanner image")
            touched = [c for c in calls if c[:1] in (["save"], ["tag"], ["pull"]) and
                       any(re.search(r"(?i)grype|anchore", a) for a in c)]
            self.assertEqual(touched, [], "bundle.sh tagged, saved or pulled the scanner image")
        with self.subTest(part="bundle.sh never names the scan compose file, scan.sh or grype"):
            text = _strip_shell_comments(BUNDLE_SH.read_text(encoding="utf-8"))
            self.assertIsNone(_SCAN_NAMES.search(text), "bundle.sh refers to the scanner")


# --------------------------------------------------------------------------
# PSC-17 (unit 3, D10): ke-app ships without uv
# --------------------------------------------------------------------------

APP_DOCKERFILE = ROOT / "docker" / "app.Dockerfile"
GATES_DOCKERFILE = ROOT / "docker" / "gates.Dockerfile"
UV_LOCK = ROOT / "uv.lock"
PYTHON_BASE_RE = re.compile(r"^python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}$")
UV_PIN_RE = re.compile(r"^ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")
UV_REF_ANY = re.compile(r"(?i)(?:[\w.-]+/)*astral-sh/uv\b[^\s\"',\]]*")
# A word that is the uv or uvx binary, or a path to it.
UV_WORD = re.compile(r"(?:.*/)?uvx?")


def _instructions(path: Path) -> list[tuple[str, str]]:
    """Dockerfile instructions as (KEYWORD, rest): continuation lines joined,
    comment lines dropped."""
    out: list[tuple[str, str]] = []
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#") or (not current and not stripped):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        current += stripped
        keyword, _, rest = current.strip().partition(" ")
        out.append((keyword.upper(), rest.strip()))
        current = ""
    if current.strip():
        keyword, _, rest = current.strip().partition(" ")
        out.append((keyword.upper(), rest.strip()))
    return out


def _stages(path: Path) -> list[dict[str, Any]]:
    """[{"ref": FROM reference, "name": AS name or None, "body": [(KW, rest)]}]."""
    stages: list[dict[str, Any]] = []
    for keyword, rest in _instructions(path):
        if keyword == "FROM":
            words = [w for w in rest.split() if not w.startswith("--")]
            name = words[2] if len(words) >= 3 and words[1].lower() == "as" else None
            stages.append({"ref": words[0] if words else "", "name": name, "body": []})
        elif stages:
            stages[-1]["body"].append((keyword, rest))
    return stages


def _words(text: str) -> list[str]:
    """Words of an instruction, split on blanks, shell operators, quotes and
    `=` (so `--from=uv` and `KEY=/x/uv` expose their values)."""
    return [w for w in re.split(r"[\s;&|()<>\"'`=,\[\]{}]+", text) if w]


def _env_pairs(rest: str) -> list[tuple[str, str]]:
    """ENV KEY=VALUE ... (or the legacy ENV KEY VALUE) as pairs."""
    import shlex

    words = shlex.split(rest, posix=True)
    if words and "=" not in words[0]:
        return [(words[0], " ".join(words[1:]))]
    return [tuple(w.split("=", 1)) for w in words if "=" in w]  # type: ignore[misc]


def _copies(body: list[tuple[str, str]]) -> list[tuple[str, ...]]:
    return sorted((keyword, *rest.split()) for keyword, rest in body if keyword in ("COPY", "ADD"))


def _uv_in_stage(stage: dict[str, Any], label: str) -> list[str]:
    """D10: no COPY/ADD --from the uv stage or the uv image, and no uv or uvx
    path or command word in any instruction of a stage whose files ship."""
    problems = []
    for keyword, rest in stage["body"]:
        if keyword in ("COPY", "ADD"):
            for src in re.findall(r"--from=(\S+)", rest):
                if src.lower() == "uv" or "astral-sh/uv" in src.lower():
                    problems.append(f"{label}: `{keyword} {rest}` (D10: no uv)")
        if any(UV_WORD.fullmatch(w) for w in _words(rest)):
            problems.append(f"{label}: `{keyword} {rest}` names the uv binary (D10: the shipped stage has no uv)")
    return problems


def final_stage_problems(path: Path) -> list[str]:
    """D10 test 1 on `path`. Two shapes ship the same files:
    - ADR-KE-013 am. 1 D10: the last stage is FROM the builder's python base;
    - ADR-KE-016 point 9 / design-notes N10a (U1 round 2, amends D10): the
      last stage is `FROM scratch` whose first instruction is `COPY
      --from=runtime / /` (once), and `runtime` is FROM the builder's base,
      byte for byte, with no COPY/ADD (its whole `/` ships).
    Either way: no uv in a stage whose files ship, the last stage's other
    copies are exactly /opt/venv and /app from `builder`, PATH starts
    /opt/venv/bin:, PYTHONUNBUFFERED=1, no UV_*, and the runtime contract."""
    problems: list[str] = []
    stages = _stages(path)
    if not stages:
        return ["docker/app.Dockerfile has no FROM"]
    final = stages[-1]
    body = final["body"]
    builders = [s for s in stages if (s["name"] or "").lower() == "builder"]
    if len(builders) != 1:
        problems.append(f"app.Dockerfile has {len(builders)} stages `AS builder`, want 1 (D10)")
    if (final["name"] or "").lower() == "builder":
        problems.append("the last stage ships; it is not builder")
    builder_ref = builders[0]["ref"] if len(builders) == 1 else None
    shipped = [(final, "final stage")]
    copies = _copies(body)
    if final["ref"] == "scratch":
        roots = [(n, keyword, rest) for n, (keyword, rest) in enumerate(body)
                 if keyword in ("COPY", "ADD") and [w for w in rest.split() if not w.startswith("--")][:1] == ["/"]]
        if [(n, keyword, rest.split()) for n, keyword, rest in roots] != [(0, "COPY", ["--from=runtime", "/", "/"])]:
            problems.append(f"the last stage is FROM scratch: its first instruction, and its only copy of `/`, is "
                            f"`COPY --from=runtime / /` (N10a); got {[f'{k} {r}' for _, k, r in roots]}")
        runtimes = [s for s in stages[:-1] if (s["name"] or "").lower() == "runtime"]
        if len(runtimes) != 1:
            problems.append(f"app.Dockerfile has {len(runtimes)} stages `AS runtime`, want 1 (N10a)")
        else:
            runtime = runtimes[0]
            shipped.append((runtime, "runtime stage"))
            if not PYTHON_BASE_RE.match(runtime["ref"]):
                problems.append(f"the runtime FROM {runtime['ref']!r} is not the pinned "
                                f"python:3.12-slim-bookworm@sha256 image (N10a)")
            if builder_ref is not None and runtime["ref"] != builder_ref:
                problems.append("the runtime FROM is not byte for byte the builder's (venv interpreter paths, D10)")
            if _copies(runtime["body"]):
                problems.append(f"the runtime stage copies files in {_copies(runtime['body'])}; its whole `/` ships, "
                                f"so it copies nothing (N10a, D10)")
        copies = [c for c in copies if list(c) != ["COPY", "--from=runtime", "/", "/"]]
    else:
        if not PYTHON_BASE_RE.match(final["ref"]):
            problems.append(f"the final FROM {final['ref']!r} is neither the pinned "
                            f"python:3.12-slim-bookworm@sha256 image nor scratch (D10, N10a)")
        if builder_ref is not None and final["ref"] != builder_ref:
            problems.append("the final FROM is not byte for byte the builder's (venv interpreter paths, D10)")
    for stage, label in shipped:
        problems += _uv_in_stage(stage, label)
    if copies != [("COPY", "--from=builder", "/app", "/app"), ("COPY", "--from=builder", "/opt/venv", "/opt/venv")]:
        problems.append(f"the final stage's only other COPYs are `COPY --from=builder /opt/venv /opt/venv` and "
                        f"`COPY --from=builder /app /app` (D10; root-owned, read-only to ke): {copies}")
    env = dict(pair for keyword, rest in body if keyword == "ENV" for pair in _env_pairs(rest))
    if not env.get("PATH", "").startswith("/opt/venv/bin:"):
        problems.append(f"the final stage's PATH starts with /opt/venv/bin: (got {env.get('PATH')!r})")
    if env.get("PYTHONUNBUFFERED") != "1":
        problems.append(f"the final stage sets PYTHONUNBUFFERED=1 (got {env.get('PYTHONUNBUFFERED')!r})")
    if [k for k in env if k.upper().startswith("UV_")]:
        problems.append("the final stage sets a UV_* variable (D10: nothing reads them)")
    if ("WORKDIR", "/app") not in body:
        problems.append("the final stage has no `WORKDIR /app` (PSC-17)")
    runs = " && ".join(rest for keyword, rest in body if keyword == "RUN")
    if not re.search(r"\buseradd\b[^;&|]*--uid[= ]10001\b[^;&|]*\bke\b", runs):
        problems.append("the final stage does not create user ke with uid 10001")
    if [rest for keyword, rest in body if keyword == "USER"][-1:] != ["ke"]:
        problems.append("the final stage does not end as USER ke")
    cmds = [rest for keyword, rest in body if keyword == "CMD"]
    try:
        cmd = json.loads(cmds[-1]) if cmds else None
    except ValueError:
        cmd = cmds[-1]
    if cmd != ["python", "-m", "engine.api"]:
        problems.append(f"the final stage's CMD is not [\"python\", \"-m\", \"engine.api\"] (got {cmd!r})")
    if len(builders) == 1:
        b = builders[0]["body"]
        b_env = dict(pair for keyword, rest in b if keyword == "ENV" for pair in _env_pairs(rest))
        if b_env.get("UV_PROJECT_ENVIRONMENT") != "/opt/venv":
            problems.append("builder: UV_PROJECT_ENVIRONMENT is not /opt/venv")
        syncs = [rest for keyword, rest in b if keyword == "RUN" and re.search(r"\buv\s+sync\b", rest)]
        if not [s for s in syncs if "--locked" in s.split() and "--no-dev" in s.split()]:
            problems.append("the builder runs no `uv sync --locked --no-dev` (D10)")
    return problems


_D10_BASE = "python:3.12-slim-bookworm@sha256:" + "5" * 64
_D10_BUILDER = f"""FROM ghcr.io/astral-sh/uv:0.11.21@sha256:{"f" * 64} AS uv

FROM {_D10_BASE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-editable && rm -f /opt/venv/.lock

"""
_D10_CONTRACT = """COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
WORKDIR /app
RUN useradd --no-create-home --uid 10001 ke
USER ke
CMD ["python", "-m", "engine.api"]
"""
# D10's shape (ADR-KE-013 am. 1) and N10a's (ADR-KE-016 point 9).
D10_LEGACY = (_D10_BUILDER + f"FROM {_D10_BASE}\nRUN apt-get update && apt-get install -y libpq5\n"
              "ENV PATH=/opt/venv/bin:$PATH \\\n    PYTHONUNBUFFERED=1\n" + _D10_CONTRACT)
D10_FLAT = (_D10_BUILDER + f"FROM {_D10_BASE} AS runtime\nRUN apt-get update && apt-get install -y libpq5\n"
            "RUN python -m pip uninstall -y pip && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl\n\n"
            "FROM scratch\nCOPY --from=runtime / /\n"
            "ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \\\n    LANG=C.UTF-8 \\\n"
            "    PYTHONUNBUFFERED=1\n" + _D10_CONTRACT)


def _d10_controls() -> tuple[dict[str, str], dict[str, str]]:
    """(must pass, must fail) for D10 test 1. D10's controls run on both
    shapes (`flat:` on N10a's), so the re-target still catches them."""
    other = "python:3.12-slim-bookworm@sha256:" + "6" * 64
    passing = {"D10 shape (last stage FROM the base)": D10_LEGACY,
               "N10a shape (FROM scratch + COPY --from=runtime / /)": D10_FLAT}
    d10 = {
        "COPY --from=uv in the final stage": lambda t: t.replace(
            "WORKDIR /app\nRUN useradd", "COPY --from=uv /uv /usr/local/bin/uv\nWORKDIR /app\nRUN useradd"),
        "COPY from the uv image in the final stage": lambda t: t.replace(
            "WORKDIR /app\nRUN useradd",
            "COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv\nWORKDIR /app\nRUN useradd"),
        "uv command in a final RUN": lambda t: t.replace("RUN useradd", "RUN uv --version && useradd"),
        "an extra COPY in the final stage": lambda t: t.replace("COPY --from=builder /app /app\n",
                                                                "COPY --from=builder /app /app\nCOPY config /config\n"),
        "COPY --chown on the venv": lambda t: t.replace("COPY --from=builder /opt/venv /opt/venv",
                                                        "COPY --chown=ke --from=builder /opt/venv /opt/venv"),
        "PATH without /opt/venv/bin first": lambda t: t.replace("ENV PATH=/opt/venv/bin:", "ENV PATH=/usr/bin:"),
        "UV_ variable in the final stage": lambda t: t.replace("    PYTHONUNBUFFERED=1\n",
                                                               "    PYTHONUNBUFFERED=1 \\\n    UV_LINK_MODE=copy\n"),
        "no PYTHONUNBUFFERED": lambda t: t.replace(" \\\n    PYTHONUNBUFFERED=1\n", "\n"),
        "no WORKDIR /app": lambda t: t.replace("WORKDIR /app\nRUN useradd", "RUN useradd"),
        "user ke with another uid": lambda t: t.replace("--uid 10001", "--uid 1000"),
        "ends as root": lambda t: t.replace("USER ke\n", ""),
        "CMD runs another module": lambda t: t.replace('"engine.api"', '"engine.worker"'),
        "builder without --locked": lambda t: t.replace("uv sync --locked --no-dev", "uv sync --no-dev"),
        "two builder stages": lambda t: t.replace("FROM ghcr.io", f"FROM {_D10_BASE} AS builder\nFROM ghcr.io"),
    }
    failing: dict[str, str] = {}
    for name, mutate in d10.items():
        for shape, base in (("", D10_LEGACY), ("flat: ", D10_FLAT)):
            text = mutate(base)
            assert text != base, shape + name
            failing[shape + name] = text
    failing.update({
        "the final FROM is another digest": D10_LEGACY.replace(f"FROM {_D10_BASE}\nRUN", f"FROM {other}\nRUN"),
        "the final FROM is builder": D10_LEGACY.replace(f"FROM {_D10_BASE}\nRUN", "FROM builder\nRUN"),
        "flat: the final FROM is runtime (its layers would ship)": D10_FLAT.replace(
            "FROM scratch\nCOPY --from=runtime / /\n", "FROM runtime\n"),
        "flat: runtime FROM another digest": D10_FLAT.replace(f"FROM {_D10_BASE} AS runtime",
                                                              f"FROM {other} AS runtime"),
        "flat: runtime FROM an unpinned base": D10_FLAT.replace(f"FROM {_D10_BASE} AS runtime",
                                                                "FROM python:3.12-slim-bookworm AS runtime"),
        "flat: COPY --from=builder / / (uv and the compiler ship)": D10_FLAT.replace(
            "COPY --from=runtime / /", "COPY --from=builder / /"),
        "flat: COPY --from=runtime / / not first": D10_FLAT.replace(
            "COPY --from=runtime / /\nENV PATH", "ENV PATH").replace(
            "COPY --from=builder /opt/venv", "COPY --from=runtime / /\nCOPY --from=builder /opt/venv"),
        "flat: COPY --from=runtime / / twice": D10_FLAT.replace(
            "COPY --from=builder /opt/venv", "COPY --from=runtime / /\nCOPY --from=builder /opt/venv"),
        "flat: FROM scratch with no copy of /": D10_FLAT.replace("COPY --from=runtime / /\n", ""),
        "flat: only part of runtime copied": D10_FLAT.replace("COPY --from=runtime / /", "COPY --from=runtime /usr /usr"),
        "flat: two runtime stages": D10_FLAT.replace(f"FROM {_D10_BASE} AS runtime",
                                                     f"FROM {_D10_BASE} AS runtime\nFROM {_D10_BASE} AS runtime"),
        "flat: runtime copies uv in": D10_FLAT.replace("AS runtime\n", "AS runtime\nCOPY --from=uv /uv /usr/local/bin/uv\n"),
        "flat: runtime RUN uses uv": D10_FLAT.replace("RUN python -m pip", "RUN uv --version && python -m pip"),
        "flat: runtime copies a file in": D10_FLAT.replace("AS runtime\n", "AS runtime\nCOPY config /config\n"),
    })
    return passing, failing


D10_PASSING, D10_CONTROLS = _d10_controls()


class AppImageTest(unittest.TestCase):
    """PSC-17, ADR-KE-013 amendment 1 D10 first tests 1 and 1b (static)."""

    def test_app_image_final_stage_has_no_uv(self):
        """D10 test 1: the shipped (last) stage of docker/app.Dockerfile has no
        uv: it copies only /opt/venv and /app from a `builder` stage on the
        same pinned python base, and keeps the runtime contract. RED until
        D10: today the final stage holds `COPY --from=uv /uv /usr/local/bin/uv`.

        Re-targeted in U1 round 2 (ADR-KE-016 point 9, N10a; it amends D10):
        the last stage may instead be `FROM scratch` starting with `COPY
        --from=runtime / /` (once), where `runtime` is FROM the builder's base
        byte for byte and holds no uv and no COPY; both shapes pass, and D10's
        controls run on both (D10_CONTROLS)."""
        with tempfile.TemporaryDirectory() as d:
            for n, (name, text) in enumerate([*D10_PASSING.items(), *D10_CONTROLS.items()]):
                path = Path(d) / f"{n:03d}.Dockerfile"
                path.write_text(text, encoding="utf-8", newline="\n")
                with self.subTest(control=name):
                    if name in D10_PASSING:
                        self.assertEqual(final_stage_problems(path), [], f"a control that must pass failed: {name}")
                    else:
                        self.assertNotEqual(final_stage_problems(path), [],
                                            f"the check passed a control that must fail: {name}")
        self.assertEqual(final_stage_problems(APP_DOCKERFILE), [])
        with self.subTest(part="the venv copied from builder cannot carry uv: uv.lock has no uv package"):
            self.assertIsNone(re.search(r'(?m)^name = "uvx?"$', UV_LOCK.read_text(encoding="utf-8")),
                              "uv.lock installs a uv package into /opt/venv")

    def test_uv_pin_matches_in_app_and_gates_images(self):
        """D10 test 1b (guard): the ghcr.io/astral-sh/uv:<v>@sha256:<64 hex>
        reference appears exactly once in each of app.Dockerfile and
        gates.Dockerfile, as a FROM, and the two are identical (one version,
        one digest; a uv bump changes both in one commit)."""
        refs: dict[str, str] = {}
        for path in (APP_DOCKERFILE, GATES_DOCKERFILE):
            found = [(keyword, ref) for keyword, rest in _instructions(path) for ref in UV_REF_ANY.findall(rest)]
            with self.subTest(file=path.name):
                self.assertEqual(len(found), 1, f"{path.name} names the uv image once: {found}")
                if found:
                    keyword, ref = found[0]
                    self.assertEqual(keyword, "FROM", f"{path.name}: the uv image is a FROM stage")
                    self.assertRegex(ref, UV_PIN_RE, f"{path.name}: uv is pinned as ghcr.io/astral-sh/uv:<v>@sha256")
                    refs[path.name] = ref
        self.assertEqual(len(set(refs.values())), 1,
                         f"app.Dockerfile and gates.Dockerfile pin different uv images: {refs} (D10 point 4)")

    # ---- unit 4 carry-ins (review r3-2; security I-1) ------------------------

    def _builder(self) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
        stages = _stages(APP_DOCKERFILE)
        builders = [s for s in stages if (s["name"] or "").lower() == "builder"]
        self.assertEqual(len(builders), 1, "app.Dockerfile has one stage `AS builder` (D10)")
        return stages, (builders[0]["body"] if builders else [])

    def test_app_image_builder_puts_no_uv_under_shipped_paths(self):
        """Review r3-2 (guard; kills the reviewer's m8 and m9): the final stage
        copies /opt/venv and /app from `builder` whole, so the builder must
        not put uv under either. In `builder`:
        - the one COPY from the uv stage (or the uv image) is
          `/uv /usr/local/bin/uv`, and no other COPY/ADD names a uv binary;
        - no COPY/ADD writes an absolute path under /opt/venv (only `uv sync`
          fills the venv);
        - every uv word in a RUN is the `uv sync` command (no cp, mv, ln or
          install of the binary, no `uv pip`/`uv tool`), and no cp, mv, ln,
          install, rsync or tar writes under /opt/venv or /app;
        - no UV_* ENV but UV_PROJECT_ENVIRONMENT points under /opt/venv or /app
          (a tool bin or cache dir there would ship).
        A `--mount=...` cache option on a RUN is allowed."""
        stages, body = self._builder()
        uv_stages = {"uv"} | {(s["name"] or "").lower() for s in stages
                              if "astral-sh/uv" in s["ref"].lower() and s["name"]}
        with self.subTest(part="the one COPY from uv is `/uv /usr/local/bin/uv`; no other COPY/ADD names uv"):
            from_uv, other = [], []
            for keyword, rest in body:
                if keyword not in ("COPY", "ADD"):
                    continue
                words = rest.split()
                srcs = [w.split("=", 1)[1].lower() for w in words if w.startswith("--from=")]
                operands = [w for w in words if not w.startswith("--")]
                if any(s in uv_stages or "astral-sh/uv" in s for s in srcs):
                    from_uv.append((f"{keyword} {rest}", operands))
                elif any(UV_WORD.fullmatch(w) for w in _words(" ".join(operands))):
                    other.append(f"{keyword} {rest}")
            self.assertEqual([ops for _, ops in from_uv], [["/uv", "/usr/local/bin/uv"]],
                             f"builder: the uv binary may only be copied to /usr/local/bin/uv, once "
                             f"(review r3-2): {[line for line, _ in from_uv]}")
            self.assertEqual(other, [], "builder: a COPY/ADD names a uv binary (review r3-2)")
        with self.subTest(part="no COPY/ADD into an absolute path under /opt/venv"):
            into_venv = [f"{keyword} {rest}" for keyword, rest in body if keyword in ("COPY", "ADD")
                         and _under_shipped([w for w in rest.split() if not w.startswith("--")][-1:], ("/opt/venv",))]
            self.assertEqual(into_venv, [], "builder: only `uv sync` fills /opt/venv (review r3-2)")
        commands = _run_commands(body)
        with self.subTest(part="every uv word in a RUN is the `uv sync` command"):
            bad = []
            for cmd in commands:
                words = _words(cmd)
                for i, w in enumerate(words):
                    if UV_WORD.fullmatch(w) and words[i + 1:i + 2] != ["sync"]:
                        bad.append(cmd)
                        break
            self.assertEqual(bad, [], "builder: a RUN uses uv other than as `uv sync` (it could copy, link or "
                             "install uv into /opt/venv or /app; review r3-2)")
        with self.subTest(part="no cp/mv/ln/install/rsync/tar writes under /opt/venv or /app"):
            writers = [cmd for cmd in commands if _words(cmd)[:1] and _words(cmd)[0] in _COPIERS
                       and _under_shipped(_words(cmd)[1:], ("/opt/venv", "/app"))]
            self.assertEqual(writers, [], "builder: a RUN copies files into /opt/venv or /app (review r3-2)")
        with self.subTest(part="no UV_* ENV but UV_PROJECT_ENVIRONMENT points under /opt/venv or /app"):
            env = [pair for keyword, rest in body if keyword == "ENV" for pair in _env_pairs(rest)]
            bad_env = [f"{k}={v}" for k, v in env if k.upper().startswith("UV_") and k != "UV_PROJECT_ENVIRONMENT"
                       and _under_shipped([v], ("/opt/venv", "/app"))]
            self.assertEqual(bad_env, [], "builder: a uv directory under /opt/venv or /app would ship (review r3-2)")

    def test_app_image_builder_drops_world_writable_venv_lock(self):
        """Security I-1: uv leaves an empty `/opt/venv/.lock`, mode 0666, the one
        path outside tmp the runtime user (uid 10001) can write. D10 keeps the
        final stage to its two COPYs, and a `rm` there would leave the file in
        the COPY layer of the image tar anyway, so the builder removes it: a
        `rm` naming /opt/venv/.lock in the builder, after its last uv command
        (each uv run recreates the file). Confirm at GREEN: the built ke-app has
        no /opt/venv/.lock (evidence)."""
        stages, body = self._builder()
        commands = _run_commands(body)
        uv_at = [i for i, cmd in enumerate(commands) if any(UV_WORD.fullmatch(w) for w in _words(cmd))]
        self.assertTrue(uv_at, "harness: the builder runs no uv command")
        rm_at = [i for i, cmd in enumerate(commands)
                 if _words(cmd)[:1] == ["rm"] and "/opt/venv/.lock" in _words(cmd)]
        self.assertTrue(rm_at, "the builder never removes /opt/venv/.lock (security I-1: mode 0666, writable by "
                        "the runtime user); add `rm -f /opt/venv/.lock` after the last `uv sync`")
        if uv_at and rm_at:
            self.assertGreater(max(rm_at), max(uv_at),
                               "the builder removes /opt/venv/.lock before its last uv command, which "
                               "recreates it (security I-1)")
        with self.subTest(part="the final stage still copies the venv from builder (the removal ships)"):
            final = stages[-1]["body"]
            self.assertIn(("COPY", "--from=builder /opt/venv /opt/venv"), final)


# RUN flags that come before the command (BuildKit).
_RUN_FLAG = re.compile(r"^--(?:mount|network|security)=\S+$")
# Commands that copy or unpack files to a destination.
_COPIERS = {"cp", "mv", "ln", "install", "rsync", "tar"}


def _run_commands(body: list[tuple[str, str]]) -> list[str]:
    """The builder's RUN instructions, in order, split into simple commands on
    `&&`, `||`, `;`, `|` and newlines, with leading BuildKit flags dropped."""
    out: list[str] = []
    for keyword, rest in body:
        if keyword != "RUN":
            continue
        words = rest.split()
        while words and _RUN_FLAG.match(words[0]):
            words.pop(0)
        for cmd in re.split(r"&&|\|\||;|\||\n", " ".join(words)):
            if cmd.strip():
                out.append(cmd.strip())
    return out


def _under_shipped(words: list[str], roots: tuple[str, ...]) -> bool:
    """True if a word is one of the roots or a path below one."""
    return any(w.rstrip("/") == r or w.startswith(r + "/") for w in words for r in roots)


if __name__ == "__main__":
    unittest.main()
