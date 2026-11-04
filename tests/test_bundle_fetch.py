"""platform-sbom U8b: the `sources-fetch` service, `scripts/bundle_fetch.sh`,
and the docs that name the route out (PSC-15, PSC-23 "U8 precision" U8-1,
U8-2, U8-6, U8-7, U8-9 and U8-13; design-notes "N4 amendment, U8" items 3,
6, 7, 9 and 12; ADR-KE-016 "Amended U8"; orchestrator rulings A75 and A76;
human ruling A73 = Q73 option 2; Q61: no retry).

The offline_check.sh wiring (U8-8) is in tests/test_offline_check.py
(`test_offline_check_fetches_the_sample`, `..._stops_when_the_fetch_fails`);
the lock tool's SBOM copies (U8-12) in tests/test_sources_resolve.py
(`U8bLockSbomsTest`); the bind-rule exemption in tests/test_stack_compose.py;
`bundle.sh`'s refusal text in tests/test_sbom_generator.py.

No daemon and no network: the script runs against tests/fake_docker.py,
which models `compose -f docker-compose.sources.yml run ... sources-fetch`
with the real scripts/sources_fetch.py from its bind and its `R.OPENER`
replaced by FAKE_RESOLVE_NET (the synthetic lock's bytes, built here with
tests/test_sources_fetch.py's LockBuilder). Never docs/evidence.

Interface pinned (tester, U8b RED, 2026-10-28; design item 3 unless noted):
- `scripts/bundle_fetch.sh --set sample|full --out DIR [--arch amd64|arm64]`.
  A missing `--set` or `--out`, another `--set` or `--arch` value, or an
  unknown argument exits 2 with a `usage: scripts/bundle_fetch.sh ...` line
  and no docker call. `docker` not on PATH exits 1 before any docker call.
- The arch is the daemon's (`docker info`); `--arch` only asserts it: a
  value that differs exits 1 naming both (U8-1 / A75, as `bundle.sh --arch`),
  before `--out` is made and before any pull or run.
- `--out`: a symlink, a non-directory or a non-empty directory exits 1, one
  `bundle_fetch: FAIL (...; no retry)` line naming it, untouched, before any
  pull or run. Absent: created 0700. Empty: used in place.
- `ke-gates:${KE_IMAGE_TAG:-local}` must be on the daemon, else exactly
  `bundle_fetch: FAIL (stage images: ke-gates:<tag> not found: run
  scripts/build.sh first; no retry)`. The caller's uid:gid must match
  `^[0-9]+:[0-9]+$`.
- Stage pull: one `docker compose --env-file .env.example -f
  docker-compose.sbom.yml pull sbom` (KE_SBOM_IN/OUT the dummy
  `/nonexistent`, KE_SBOM_USER set), the ref read from that file's `sbom`
  service; failing: exactly `bundle_fetch: FAIL (stage pull: pulling the
  SBOM generator <ref> failed; no retry)`, exit 1.
- Stage fetch: one `docker compose -p ke-fetch-<8 hex> --env-file
  .env.example -f docker-compose.sources.yml run --rm --pull never
  sources-fetch` with `--arch <daemon arch> --set <set>` after the service,
  KE_SOURCES_IN the dummy `/nonexistent`, KE_SOURCES_OUT the out dir,
  KE_SOURCES_USER the caller's uid:gid; COMPOSE_PROFILES and
  COMPOSE_PATH_SEPARATOR unset. The client's lines pass through. A non-zero
  client exit adds exactly `bundle_fetch: FAIL (stage fetch: sources_fetch.py
  exited <rc>; no retry)` after the client's own FAIL line, exit 1.
- `fetch.json` must then be a regular file (not a link), else exit 1.
- Markers on stdout: `== sources: pull ==`, `== sources: fetch ==`, `==
  sources: done (pull <a> s, fetch <b> s) ==`.
- On every exit path the project is brought `down --volumes` (with the
  dummies); on a failure (error, INT, TERM, HUP) a created `--out` is
  removed and a given one is emptied.
- `docker-compose.sources.yml` service `sources-fetch` row by row (design
  item 3, U8-7): see `fetch_service_problems`.
- CLAUDE.md § Verification holds Q73 option 2's sentence (A73), verbatim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

import yaml

from tests import compose_support as cs
from tests import fake_docker
from tests.engine_support import ROOT
from tests.test_image_scan import _function_body, _trap_words
from tests.test_sbom_generator import _strip_messages
from tests.test_sources_fetch import ARCH, NEO_KEY, LockBuilder, h, host_of, plan_of, wide

BUNDLE_FETCH = ROOT / "scripts" / "bundle_fetch.sh"
SOURCES_COMPOSE = ROOT / "docker-compose.sources.yml"
SOURCES_YML = "docker-compose.sources.yml"
CLAUDE_MD = ROOT / "CLAUDE.md"
README_MD = ROOT / "README.md"
BUNDLE_SH = ROOT / "scripts" / "bundle.sh"
POLICY = ROOT / "docker" / "source-policy.json"
GATES = "ke-gates:local"
SCRIPT_MISSING = ("scripts/bundle_fetch.sh is missing (platform-sbom U8b: PSC-23 U8-1; design-notes "
                  "N4 amendment U8 item 3)")
# Q73 option 2 (docs/open-questions.md), ruled by the human 2026-10-28 (A73):
# CLAUDE.md § Verification's host-half sentence, verbatim.
A73_SENTENCE = (
    "In `full` the host half also builds and pulls images, runs the smoke check's network-control probe on "
    "the stack's `edge` network, runs `scan-db`, a one-shot that fetches the image scanner's vulnerability "
    "database, and runs `sources-fetch`, a one-shot that pulls nothing and fetches a fixed sample of the "
    "bundle's third-party source code over HTTPS, only from the hosts listed in `docker/source-policy.json`, "
    "checking every file against `docker/sources.lock.json`; a failed or mismatched fetch fails the run, with "
    "no retry. The scan itself runs with no network.")
# The sentence before A73 (U8 replaces it).
PRE_A73 = "network-control probe on the stack's `edge` network, and runs `scan-db`"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DONE_RX = re.compile(r"^== sources: done \(pull [0-9]+ s, fetch [0-9]+ s\) ==$")
FETCH_EXITED = "bundle_fetch: FAIL (stage fetch: sources_fetch.py exited {rc}; no retry)"
PULL_FAIL = "bundle_fetch: FAIL (stage pull: pulling the SBOM generator {ref} failed; no retry)"
IMAGES_FAIL = "bundle_fetch: FAIL (stage images: {img} not found: run scripts/build.sh first; no retry)"
RUN_FETCH_RX = r"\brun\b.*\bsources-fetch\b"
PULL_SBOM_RX = r"docker-compose\.sbom\.yml.*\bpull\b"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _code(text: str) -> str:
    """A shell script without its comment lines."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def _header(text: str) -> str:
    """The leading comment block of a script or compose file, `#` removed."""
    out = []
    for ln in text.splitlines():
        if ln.startswith("#!"):
            continue
        if not ln.startswith("#"):
            break
        out.append(ln.lstrip("#").strip())
    return " ".join(" ".join(out).split())


# --------------------------------------------------------------------------
# docker-compose.sources.yml: the `sources-fetch` service (design item 3, U8-7)
# --------------------------------------------------------------------------

FETCH_ENTRYPOINT = ["python3", "-I", "/opt/ke/sources_fetch.py", "--lock", "/opt/ke/sources.lock.json",
                    "--policy", "/opt/ke/source-policy.json", "--out", "/out"]
FETCH_RO_BINDS = {
    "/opt/ke/sources_fetch.py": "./scripts/sources_fetch.py",
    "/opt/ke/sources_resolve.py": "./scripts/sources_resolve.py",
    "/opt/ke/sbom_check.py": "./scripts/sbom_check.py",
    "/opt/ke/sources.lock.json": "./docker/sources.lock.json",
    "/opt/ke/source-policy.json": "./docker/source-policy.json",
}
FORBIDDEN_KEYS = ("network_mode", "networks", "ports", "expose", "devices", "env_file", "build", "profiles",
                  "secrets", "configs", "extra_hosts", "dns", "dns_search", "dns_opt", "links", "external_links",
                  "volumes_from", "pid", "ipc", "userns_mode", "restart", "container_name", "cap_add", "privileged",
                  "working_dir", "command", "healthcheck", "depends_on", "labels", "hostname", "domainname",
                  "sysctls", "devices_cgroup_rules", "group_add")


def fetch_service_problems(data: Any) -> list[str]:
    """Design item 3 and U8-7, row by row; [] is a pass."""
    svc = ((data or {}).get("services") or {}).get("sources-fetch")
    if not isinstance(svc, dict):
        return ["docker-compose.sources.yml defines no `sources-fetch` service (U8-7; N4 amendment U8 item 3)"]
    p: list[str] = []
    if svc.get("image") != "ke-gates:${KE_IMAGE_TAG:-local}":
        p.append(f"sources-fetch: image is {svc.get('image')!r}, want ke-gates:${{KE_IMAGE_TAG:-local}}")
    if svc.get("pull_policy") != "never":
        p.append("sources-fetch: pull_policy is not never (it pulls nothing)")
    if not re.fullmatch(r"\$\{KE_SOURCES_USER:\?[^}]*\}", str(svc.get("user", ""))):
        p.append("sources-fetch: user is not ${KE_SOURCES_USER:?...} (the caller's uid:gid, set by the script)")
    if svc.get("read_only") is not True:
        p.append("sources-fetch: read_only is not true")
    raw = svc.get("tmpfs")
    tmpfs = [str(t).split(":", 1)[0] for t in raw] if isinstance(raw, list) else ([str(raw).split(":", 1)[0]]
                                                                                  if raw else [])
    if tmpfs != ["/tmp"]:
        p.append(f"sources-fetch: tmpfs is {tmpfs}, want exactly ['/tmp']")
    if svc.get("cap_drop") != ["ALL"]:
        p.append("sources-fetch: cap_drop is not [ALL]")
    if "no-new-privileges:true" not in [str(o).replace("=", ":") for o in svc.get("security_opt") or []]:
        p.append("sources-fetch: security_opt lacks no-new-privileges:true")
    if [o for o in svc.get("security_opt") or [] if "unconfined" in str(o)]:
        p.append("sources-fetch: security_opt holds an unconfined profile")
    allowed = {"image", "pull_policy", "user", "read_only", "tmpfs", "cap_drop", "security_opt", "entrypoint",
               "volumes", "environment"}
    for key in sorted(set(svc) - allowed):
        p.append(f"sources-fetch: sets {key}, which is not in the allowlist {sorted(allowed)} (security L-2)")
    for v in svc.get("volumes") or []:
        if isinstance(v, dict) and set(v) - {"type", "source", "target", "read_only"}:
            p.append(f"sources-fetch: bind {v.get('target')!r} sets {sorted(set(v) - {'type', 'source', 'target', 'read_only'})} "
                     "(a bind is exactly type, source, target and optional read_only; security L-2)")
    for key in FORBIDDEN_KEYS:
        if key in svc:
            p.append(f"sources-fetch: sets {key} (the project's default bridge is its only route; a hardened one-shot)")
    if (data or {}).get("name"):
        p.append("docker-compose.sources.yml sets a top-level name (the run's -p must win)")
    env = svc.get("environment")
    items = (list(env.items()) if isinstance(env, dict) else
             [(str(e).split("=", 1)[0], str(e).split("=", 1)[1] if "=" in str(e) else None) for e in env or []])
    for key, value in items:
        if value is None or "$" in str(value):
            p.append(f"sources-fetch: environment {key} is passed through or interpolated (literals only)")
        if (str(key).startswith(("KE_", "DOCKER_", "OPENAI", "ANTHROPIC", "HTTP", "HTTPS", "http", "https",
                                 "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy", "SSL_", "CURL", "REQUESTS_"))
                or re.search(r"TOKEN|KEY|SECRET|PASSWORD|PROXY", str(key), re.I)):
            p.append(f"sources-fetch: environment holds {key} (no KE_* key, model key, token, proxy or DOCKER_*)")
    if dict(items) != {"PYTHONDONTWRITEBYTECODE": "1"}:
        p.append(f"sources-fetch: environment is {dict(items)!r}, want exactly PYTHONDONTWRITEBYTECODE=1")
    mounts = []
    for v in svc.get("volumes") or []:
        if not isinstance(v, dict) or v.get("type") != "bind":
            p.append(f"sources-fetch: {v!r} is not a long-form bind")
            continue
        mounts.append((str(v.get("source", "")), str(v.get("target", "")), bool(v.get("read_only"))))
    for s, tgt, _ in mounts:
        if any(m in s or m in tgt for m in cs.SOCKET_MARKERS):
            p.append("sources-fetch: mounts the Docker socket")
        if s in (".", "./") or tgt in ("/work", "/repo"):
            p.append(f"sources-fetch: mounts the checkout ({s} -> {tgt})")
    by_target = {tgt: (s, ro) for s, tgt, ro in mounts}
    for target, source in FETCH_RO_BINDS.items():
        if by_target.get(target) != (source, True):
            p.append(f"sources-fetch: {target} is not a read-only bind of {source}")
    out = by_target.get("/out")
    if not out or not re.fullmatch(r"\$\{KE_SOURCES_OUT:\?[^}]*\}", out[0]) or out[1]:
        p.append("sources-fetch: /out is not a read-write bind of ${KE_SOURCES_OUT:?...}")
    if sorted(tgt for _, tgt, _ in mounts) != sorted([*FETCH_RO_BINDS, "/out"]):
        p.append(f"sources-fetch: mounts {sorted(tgt for _, tgt, _ in mounts)}, want exactly the five read-only "
                 "binds and /out (no checkout, no uv.lock, no /in)")
    writable = sorted(tgt for _, tgt, ro in mounts if not ro)
    if writable != ["/out"]:
        p.append(f"sources-fetch: writable mounts are {writable}, want only /out")
    if svc.get("entrypoint") != FETCH_ENTRYPOINT:
        p.append(f"sources-fetch: entrypoint is {svc.get('entrypoint')!r}, want {FETCH_ENTRYPOINT!r}")
    return p


GOOD_FETCH_SERVICE: dict[str, Any] = {
    "image": "ke-gates:${KE_IMAGE_TAG:-local}", "pull_policy": "never",
    "user": "${KE_SOURCES_USER:?set by scripts/bundle_fetch.sh or scripts/sources_lock.sh}",
    "read_only": True, "tmpfs": ["/tmp"], "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
    "entrypoint": list(FETCH_ENTRYPOINT),
    "volumes": [{"type": "bind", "source": s, "target": t, "read_only": True} for t, s in FETCH_RO_BINDS.items()]
    + [{"type": "bind", "source": "${KE_SOURCES_OUT:?set by scripts/bundle_fetch.sh}", "target": "/out"}],
    "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
}


class SourcesFetchServiceTest(unittest.TestCase):

    def _data(self) -> dict[str, Any]:
        self.assertTrue(SOURCES_COMPOSE.is_file(), "docker-compose.sources.yml is missing (U7b)")
        return yaml.safe_load(SOURCES_COMPOSE.read_text(encoding="utf-8")) or {}

    def test_sources_fetch_service_is_hardened(self):
        data = self._data()
        self.assertEqual(fetch_service_problems(data), [])
        self.assertEqual(sorted(data.get("services") or {}), ["sources-fetch", "sources-resolve"],
                         "U8b adds sources-fetch beside sources-resolve, nothing else")
        self.assertNotIn("DOCKER_HOST", SOURCES_COMPOSE.read_text(encoding="utf-8"), "U8-7: no DOCKER_HOST")

    def test_hardening_check_rejects_loosened_fetch_services(self):
        """The oracle passes the design's service and fails each loosening
        (a control; green before U8b)."""
        def wrap(svc: dict[str, Any]) -> dict[str, Any]:
            return {"services": {"sources-fetch": svc}}
        self.assertEqual(fetch_service_problems(wrap(GOOD_FETCH_SERVICE)), [], "the oracle's good service fails")

        def change(fn: Any) -> dict[str, Any]:
            svc = json.loads(json.dumps(GOOD_FETCH_SERVICE))
            fn(svc)
            return wrap(svc)
        bad = {
            "a KE_* key": change(lambda s: s["environment"].update(KE_MODEL_UPSTREAM="x")),
            "a passed-through key": change(lambda s: s.update(environment=["HOME"])),
            "an interpolated value": change(lambda s: s["environment"].update(X="${HOME}")),
            "a proxy": change(lambda s: s["environment"].update(HTTPS_PROXY="p")),
            "a token": change(lambda s: s["environment"].update(GITHUB_TOKEN="t")),
            "DOCKER_HOST": change(lambda s: s["environment"].update(DOCKER_HOST="tcp://x")),
            "host networking": change(lambda s: s.update(network_mode="host")),
            "the backend network": change(lambda s: s.update(networks=["backend"])),
            "the edge network": change(lambda s: s.update(networks=["edge"])),
            "a port": change(lambda s: s.update(ports=["8080:80"])),
            "writable root": change(lambda s: s.update(read_only=False)),
            "a capability": change(lambda s: s.update(cap_add=["NET_ADMIN"])),
            "privileged": change(lambda s: s.update(privileged=True)),
            "no no-new-privileges": change(lambda s: s.update(security_opt=[])),
            "the lock writable": change(lambda s: s["volumes"][3].update(read_only=False)),
            "the checkout mounted": change(lambda s: s["volumes"].append({"type": "bind", "source": ".",
                                                                          "target": "/work", "read_only": True})),
            "uv.lock mounted": change(lambda s: s["volumes"].append({"type": "bind", "source": "./uv.lock",
                                                                      "target": "/opt/ke/uv.lock",
                                                                      "read_only": True})),
            "a socket": change(lambda s: s["volumes"].append({"type": "bind", "source": "/var/run/docker.sock",
                                                              "target": "/var/run/docker.sock"})),
            "a short-form bind": change(lambda s: s["volumes"].append("./x:/x:ro")),
            "pulls": change(lambda s: s.update(pull_policy="always")),
            "root user": change(lambda s: s.update(user="0:0")),
            "an env_file": change(lambda s: s.update(env_file=[".env"])),
            "another entrypoint": change(lambda s: s["entrypoint"].__setitem__(2, "/opt/ke/sources_resolve.py")),
            "no tmpfs": change(lambda s: s.pop("tmpfs")),
            "a top-level name": {"name": "x", "services": {"sources-fetch": GOOD_FETCH_SERVICE}},
        }
        for case, data in bad.items():
            with self.subTest(case=case):
                self.assertNotEqual(fetch_service_problems(data), [], case)

    def test_hardening_check_rejects_extra_service_and_bind_keys(self):
        """Security L-2 (U8b rework 1): the check is an allowlist, not a
        denylist. The service may set exactly image, pull_policy, user,
        read_only, tmpfs, cap_drop, security_opt, entrypoint, volumes and
        environment; each bind exactly type, source, target and (optionally)
        read_only. Any other key, on the service or on a bind, is a problem."""
        def wrap(svc: dict[str, Any]) -> dict[str, Any]:
            return {"services": {"sources-fetch": svc}}
        self.assertEqual(fetch_service_problems(wrap(GOOD_FETCH_SERVICE)), [], "the oracle's good service fails")

        def change(fn: Any) -> dict[str, Any]:
            svc = json.loads(json.dumps(GOOD_FETCH_SERVICE))
            fn(svc)
            return wrap(svc)
        bad = {
            "pids_limit": change(lambda s: s.update(pids_limit=-1)),
            "uts": change(lambda s: s.update(uts="host")),
            "cgroup": change(lambda s: s.update(cgroup="host")),
            "runtime": change(lambda s: s.update(runtime="runc")),
            "platform": change(lambda s: s.update(platform="linux/arm64")),
            "ulimits": change(lambda s: s.update(ulimits={"nofile": 1048576})),
            "shm_size": change(lambda s: s.update(shm_size="8g")),
            "init": change(lambda s: s.update(init=True)),
            "stdin_open": change(lambda s: s.update(stdin_open=True)),
            "tty": change(lambda s: s.update(tty=True)),
            "mem_limit": change(lambda s: s.update(mem_limit="0")),
            "a read-only bind with bind.propagation": change(
                lambda s: s["volumes"][0].update(bind={"propagation": "rshared"})),
            "the /out bind with bind.propagation": change(
                lambda s: s["volumes"][-1].update(bind={"propagation": "rshared"})),
            "the /out bind with bind.create_host_path": change(
                lambda s: s["volumes"][-1].update(bind={"create_host_path": True})),
            "a bind with consistency": change(lambda s: s["volumes"][1].update(consistency="delegated")),
            "a bind with a volume sub-key": change(lambda s: s["volumes"][2].update(volume={"nocopy": True})),
        }
        for case, data in bad.items():
            with self.subTest(case=case):
                self.assertNotEqual(fetch_service_problems(data), [],
                                    f"the hardening check passes a sources-fetch service with {case} (security L-2)")

    def test_sources_compose_header_names_both_starters(self):
        """U8-7: the file's header, which said only the lock tool starts it, is
        corrected: two services, one started by scripts/sources_lock.sh, one
        by scripts/bundle_fetch.sh."""
        head = _header(SOURCES_COMPOSE.read_text(encoding="utf-8"))
        for word in ("sources-fetch", "scripts/bundle_fetch.sh", "sources-resolve", "scripts/sources_lock.sh"):
            with self.subTest(word=word):
                # assertTrue, not assertIn: a failure must not dump the whole header.
                self.assertTrue(word in head, f"the docker-compose.sources.yml header does not name {word}")
        self.assertFalse("U8 adds `sources-fetch` here" in head, "the header still says U8 is to come")


# --------------------------------------------------------------------------
# scripts/bundle_fetch.sh, statically
# --------------------------------------------------------------------------

class BundleFetchStaticTest(unittest.TestCase):

    def _text(self) -> str:
        self.assertTrue(BUNDLE_FETCH.is_file(), SCRIPT_MISSING)
        return BUNDLE_FETCH.read_text(encoding="utf-8")

    def test_bundle_fetch_sh_shape(self):
        """The rules every script under scripts/ keeps: LF, `#!/usr/bin/env
        bash`, `set -euo pipefail`, parses with `bash -n`, executable in the
        index (Git for Windows adds a new file as 100644: `git add
        --chmod=+x`), and a trap for EXIT, INT, TERM and HUP (U8-6, as scan.sh)."""
        text = self._text()
        raw = BUNDLE_FETCH.read_bytes()
        self.assertNotIn(b"\r", raw, "CRLF line endings (.gitattributes: *.sh eol=lf)")
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n"), "no `#!/usr/bin/env bash` first line")
        self.assertRegex(text, r"(?m)^set -euo pipefail$")
        done = subprocess.run(["bash", "-n", str(BUNDLE_FETCH)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "--", "scripts/bundle_fetch.sh"],
                                capture_output=True, text=True, timeout=60)
        self.assertRegex(listed.stdout, r"^100755 ",
                         "scripts/bundle_fetch.sh is not in the index as executable (100755); "
                         f"git ls-files -s says {listed.stdout.strip()!r}")
        code = _code(text)
        traps = " ".join(re.findall(r"(?m)^\s*trap\s+.*$", code))
        for sig in ("EXIT", "INT", "TERM", "HUP"):
            with self.subTest(trap=sig):
                self.assertRegex(traps, rf"\b{sig}\b", f"no trap on {sig} (U8-6: every exit path the script can trap)")

    def test_bundle_fetch_has_no_network_step_but_the_service(self):
        """U8-1/U8-4/U8-7, item 3: the only route out is the `sources-fetch`
        run (and the generator pull, N1 amendment U2); no URL, host, curl or
        wget in the script; compose only with `--env-file .env.example`; no
        `-e`; never `--pull` other than never; no --evidence-dir (A75)."""
        text = self._text()
        code = _code(text)
        self.assertIsNone(re.search(r"https?://", text), "a URL literal (hosts come from the policy only)")
        hosts = json.loads(POLICY.read_text(encoding="utf-8")).get("hosts") or []
        self.assertTrue(hosts, "fixture: the policy lists hosts")
        for host in hosts:
            with self.subTest(host=host):
                self.assertNotIn(host, text, "a policy host is written into the script")
        self.assertIsNone(re.search(r"\b(curl|wget|ncat|socat)\b", code), "a network tool")
        self.assertIn("-f docker-compose.sources.yml", code)
        self.assertRegex(code, r"run --rm --pull never sources-fetch\b",
                         "the fetch is not `compose ... run --rm --pull never sources-fetch`")
        self.assertIn("-f docker-compose.sbom.yml", code, "the generator is not pulled through its compose file")
        self.assertRegex(code, r"\bpull sbom\b", "the generator is not pulled as `compose ... pull sbom`")
        for m in re.finditer(r"--env-file\s+([^\s)\"']+)", code):
            self.assertEqual(m.group(1), ".env.example", "an --env-file other than .env.example")
        # `-e` is also a `[ -e path ]` test: only docker command lines (continuations joined) count.
        docker_lines = [ln for ln in code.replace("\\\n", " ").splitlines() if re.search(r"\bdocker\b", ln)]
        self.assertEqual([ln for ln in docker_lines if re.search(r"\s(-e|--env)(\s|=)", ln)], [],
                         "passes a value into a container (-e/--env)")
        for m in re.finditer(r"--pull(?:=|\s+)(\S+)", code):
            self.assertEqual(m.group(1).strip("'\""), "never", "a --pull other than never")
        self.assertIsNone(re.search(r"\bdocker\s+(?:image\s+)?pull\b", code), "a plain `docker pull` (compose only)")
        self.assertIsNone(re.search(r"\bdocker\s+(?:container\s+)?run\b", code), "a plain `docker run`")
        self.assertNotIn("--evidence-dir", text, "A75: no --evidence-dir; the stdout lines are the record")
        self.assertNotIn("COMPOSE_FILE=", code.replace("unset COMPOSE_FILE", ""),
                         "the script sets a COMPOSE_FILE (it names its files with -f)")
        self.assertIn("MSYS_NO_PATHCONV=1", code, "item 3 step 5: the container paths survive Git Bash")

    def test_bundle_fetch_is_a_host_tool_only(self):
        """U8-1: never bundled, never copied by bundle.sh, never in a stack
        COMPOSE_FILE; only offline_check.sh calls it (a control: green
        before U8b)."""
        bundle_code = _strip_messages(BUNDLE_SH.read_text(encoding="utf-8"))
        self.assertNotIn("bundle_fetch", bundle_code, "bundle.sh's code names bundle_fetch.sh (it is never copied)")
        for rel in (".env.example", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.offline.yml"):
            with self.subTest(file=rel):
                text = (ROOT / rel).read_text(encoding="utf-8") if (ROOT / rel).is_file() else ""
                self.assertNotIn(SOURCES_YML, text, f"{rel} names docker-compose.sources.yml")
                self.assertNotIn("bundle_fetch", text, f"{rel} names bundle_fetch.sh")
        callers = sorted(p.relative_to(ROOT).as_posix()
                         for p in [*(ROOT / "scripts").glob("*.sh"), *(ROOT / "scripts").glob("*.ps1"),
                                   *(ROOT / ".github").rglob("*.yml")]
                         if p.name != "bundle_fetch.sh" and "bundle_fetch.sh" in _code(p.read_text(encoding="utf-8"))
                         and p.name != "bundle.sh")
        self.assertTrue(set(callers) <= {"scripts/offline_check.sh"}, f"callers of bundle_fetch.sh: {callers}")

    def test_bundle_fetch_cleanup_ignores_signals_before_clearing_exit_trap(self):
        """Review B-2 (U8b rework 1; design item 3 "as scan.sh", security I-4):
        in the EXIT-trap function, INT, TERM and HUP are ignored (`trap ''
        INT TERM HUP`) before the EXIT trap is cleared (`trap - EXIT`), and
        the function never resets INT, TERM or HUP to their default, so a
        second signal cannot cut the teardown short. Mirrors
        test_scan_cleanup_ignores_signals_before_clearing_exit_trap."""
        lines = _code(self._text()).splitlines()
        handlers = [w[1] for w in (_trap_words(line) for line in lines if not line[:1].isspace())
                    if w and len(w) >= 3 and "EXIT" in w[2:] and w[1] not in ("", "-")]
        self.assertEqual(len(handlers), 1, "harness: bundle_fetch.sh installs one EXIT trap function at top level")
        body = _function_body(lines, handlers[0]) if handlers else []
        self.assertTrue(body, f"harness: the body of the EXIT trap function {handlers[:1]} was not found")
        traps = [w for w in (_trap_words(line) for line in body) if w]
        self.assertTrue(traps, "the EXIT trap function sets no trap")
        if traps:
            first = traps[0]
            self.assertTrue(first[1] == "" and {"INT", "TERM", "HUP"} <= set(first[2:]),
                            f"the first trap in {handlers[0]}() is `{' '.join(first)}`: it must be "
                            "`trap '' INT TERM HUP`, before `trap - EXIT` (review B-2, as scan.sh)")
        self.assertTrue([w for w in traps if w[1] in ("", "-") and "EXIT" in w[2:]],
                        f"{handlers[:1]}() never clears the EXIT trap (`trap - EXIT`)")
        reset = [" ".join(w) for w in traps if w[1] == "-" and {"INT", "TERM", "HUP"} & set(w[2:])]
        self.assertEqual(reset, [], f"{handlers[:1]}() resets a signal to its default during teardown (review B-2)")


# --------------------------------------------------------------------------
# Docs: CLAUDE.md (A73), README, bundle.sh's header (U8-9, N13)
# --------------------------------------------------------------------------

class BundleFetchDocsTest(unittest.TestCase):

    @staticmethod
    def _section(text: str, title: str) -> str:
        m = re.search(rf"(?ms)^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", text)
        return m.group(1) if m else ""

    def test_claude_md_names_the_source_fetch(self):
        """A73 (Q73 option 2, the human's ruling): CLAUDE.md § Verification's
        host-half sentence, verbatim; the gate services stay networkless."""
        section = _flat(self._section(CLAUDE_MD.read_text(encoding="utf-8"), "Verification: one entry point"))
        self.assertTrue(section, "CLAUDE.md has no `## Verification: one entry point` section")
        # assertTrue, not assertIn: a failure must not dump the whole section.
        self.assertTrue(A73_SENTENCE in section,
                        "CLAUDE.md § Verification does not hold Q73 option 2's sentence (A73), verbatim")
        self.assertFalse(PRE_A73 in section, "CLAUDE.md § Verification still holds the pre-U8 sentence")
        self.assertTrue("Networking is disabled for the gate services" in section,
                        "CLAUDE.md § Verification no longer says the gate services have no network")

    def test_readme_names_the_route_out_and_the_operator_order(self):
        """U8-9: README says where the route out is (the fetch, the hosts in
        docker/source-policy.json) and gives the operator order: build.sh,
        then bundle_fetch.sh, then bundle.sh."""
        text = README_MD.read_text(encoding="utf-8")
        verification = _flat(self._section(text, "Verification"))
        for word in ("scripts/bundle_fetch.sh", "docker/source-policy.json"):
            with self.subTest(section="Verification", word=word):
                self.assertTrue(word in verification, f"README § Verification does not name {word}")
        ordered = []
        for para in re.split(r"\n\s*\n", text):
            flat = _flat(para)
            if re.search(r"scripts/build\.sh.*scripts/bundle_fetch\.sh.*scripts/bundle\.sh", flat):
                ordered.append(flat[:120])
        self.assertTrue(ordered, "no README paragraph gives the operator order build.sh, then bundle_fetch.sh, "
                                 "then bundle.sh (U8-9)")

    def test_bundle_header_names_the_fetch_step(self):
        """U8-9 (N13): bundle.sh's header keeps "makes no network call" and
        names scripts/bundle_fetch.sh as the only bundle step with a route out."""
        head = _header(BUNDLE_SH.read_text(encoding="utf-8"))
        for phrase in ("makes no network call", "scripts/bundle_fetch.sh", "the only bundle step with a route out"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in head, f"bundle.sh's header does not say {phrase!r}")


# --------------------------------------------------------------------------
# scripts/bundle_fetch.sh on the fake daemon
# --------------------------------------------------------------------------

def _net(b: LockBuilder) -> dict[str, list[Any]]:
    """LockBuilder routes in FAKE_RESOLVE_NET's form: url -> [status, headers, body text]."""
    out: dict[str, list[Any]] = {}
    for url, spec in b.routes().items():
        if isinstance(spec, bytes):
            out[url] = [200, {}, spec.decode("utf-8")]
        else:
            status, headers, body = spec
            out[url] = [status, headers, body.decode("utf-8")]
    return out


def _image(arch: str = "amd64") -> dict[str, str]:
    return {"Id": "sha256:" + "1" * 64, "Os": "linux", "Architecture": arch}


class _FetchScriptBase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        if not BUNDLE_FETCH.is_file():
            self.fail(SCRIPT_MISSING)
        self.tmp = Path(tempfile.mkdtemp(prefix="ke-u8b-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        for rel in ("scripts/bundle_fetch.sh", "scripts/sources_fetch.py", "scripts/sources_resolve.py",
                    "scripts/sbom_check.py", SOURCES_YML, cs.SBOM_COMPOSE_NAME, ".env.example",
                    "docker/source-policy.json"):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.repo / rel)
        (self.repo / "scripts" / "bundle_fetch.sh").chmod(0o755)
        self.b = wide()
        self.lock_text = self.b.text()
        (self.repo / "docker" / "sources.lock.json").write_text(self.lock_text, encoding="utf-8", newline="\n")
        fake_docker.install(self.tmp / "fakebin")
        self.json = self.tmp / "docker.jsonl"
        self.resolve_log = self.tmp / "resolve.log"
        self.path = f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
        sbom_file = ROOT / cs.SBOM_COMPOSE_NAME
        self.sbom_ref = cs.sbom_generator_ref(sbom_file)
        self.sbom_required = cs.required_vars(sbom_file)
        self.n = 0

    # --- the run -------------------------------------------------------------
    def _env(self, *, arch: str = "x86_64", images: dict[str, Any] | None = None, net: dict[str, Any] | None = None,
             path: str | None = None, **extra: str) -> dict[str, str]:
        imgs = {GATES: _image(), self.sbom_ref: _image()} if images is None else images
        env = {"PATH": path or self.path, "HOME": str(self.tmp), "TMPDIR": str(self.tmp), "LC_ALL": "C",
               "FAKE_DOCKER_JSON": str(self.json), "FAKE_DOCKER_ARCH": arch,
               "FAKE_DOCKER_IMAGES": json.dumps(imgs),
               "FAKE_COMPOSE_FILE_IMAGES": json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": self.sbom_ref},
                                                       SOURCES_YML: {"sources-resolve": GATES,
                                                                     "sources-fetch": GATES}}),
               "FAKE_COMPOSE_FILE_REQUIRED": json.dumps({cs.SBOM_COMPOSE_NAME: self.sbom_required,
                                                         SOURCES_YML: ["KE_SOURCES_IN", "KE_SOURCES_OUT",
                                                                       "KE_SOURCES_USER"]}),
               "FAKE_RESOLVE_NET": json.dumps(_net(self.b) if net is None else net),
               "FAKE_RESOLVE_LOG": str(self.resolve_log)}
        env.update(extra)
        return env

    def _fresh_logs(self) -> None:
        for f in (self.json, self.resolve_log):
            f.write_text("", encoding="utf-8")

    def _run(self, *args: str, **kw: Any) -> tuple[subprocess.CompletedProcess, list[dict[str, Any]]]:
        self._fresh_logs()
        r = subprocess.run(["bash", "scripts/bundle_fetch.sh", *args], cwd=self.repo, env=self._env(**kw),
                           capture_output=True, text=True, timeout=300)
        return r, fake_docker.records(self.json)

    def _out(self) -> Path:
        self.n += 1
        return self.tmp / f"out-{self.n}"

    # --- reading the call log -------------------------------------------------
    @staticmethod
    def _files(argv: list[str]) -> list[str]:
        got = [b for a, b in zip(argv, argv[1:]) if a in ("-f", "--file")]
        return [os.path.basename(f) for f in got + [a.split("=", 1)[1] for a in argv if a.startswith(("-f=", "--file="))]]

    @staticmethod
    def _opt(argv: list[str], name: str) -> list[str]:
        return [b for a, b in zip(argv, argv[1:]) if a == name] + [a.split("=", 1)[1] for a in argv
                                                                    if a.startswith(name + "=")]

    def _runs(self, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in recs if r["argv"][:1] == ["compose"] and re.search(RUN_FETCH_RX, " ".join(r["argv"]))]

    def _downs(self, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in recs if r["argv"][:1] == ["compose"] and "down" in r["argv"]
                and SOURCES_YML in self._files(r["argv"])]

    def _no_pull_or_run(self, recs: list[dict[str, Any]]) -> None:
        self.assertEqual([r["argv"] for r in recs if "pull" in r["argv"] or "run" in r["argv"]
                          or r["argv"][:2] == ["image", "pull"]], [], "a pull or run happened before the refusal")

    @staticmethod
    def _fail_lines(r: subprocess.CompletedProcess) -> list[str]:
        return [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("bundle_fetch: FAIL")]

    def _requested(self) -> list[str]:
        return [ln for ln in self.resolve_log.read_text(encoding="utf-8").splitlines() if ln]

    def _want(self, arch: str, which: str) -> tuple[set[str], set[str]]:
        """(the distinct sha256 of the plan, every URL the plan may request)."""
        plan = plan_of(self.b, arch, which)
        urls: set[str] = set()
        for _, f in plan:
            urls.update(self.b.chain(f["url"]))
        return {f["sha256"] for _, f in plan}, urls

    def _assert_complete(self, out: Path, arch: str, which: str) -> None:
        shas, urls = self._want(arch, which)
        names = sorted(os.listdir(out))
        self.assertEqual(sorted(names), sorted([*shas, "fetch.json"]),
                         "--out is not exactly one file per distinct sha256 of the plan plus fetch.json")
        for n in names:
            p = out / n
            self.assertTrue(p.is_file() and not p.is_symlink(), f"{n} is not a regular file")
            if n != "fetch.json":
                self.assertRegex(n, HEX64)
                self.assertEqual(h("sha256", p.read_bytes()), n, f"{n}: the bytes do not hash to the name")
        record = json.loads((out / "fetch.json").read_text(encoding="utf-8"))
        self.assertEqual((record.get("set"), record.get("arch"), record.get("lock_sha256")),
                         (which, arch, hashlib.sha256(self.lock_text.encode("utf-8")).hexdigest()),
                         "A76: the record names the set, the arch and the lock's sha256")
        requested = self._requested()
        self.assertEqual(len(requested), len(set(requested)), f"a URL was requested twice: {requested}")
        self.assertTrue(set(requested) <= urls, f"requests outside the plan: {sorted(set(requested) - urls)}")


class BundleFetchRunTest(_FetchScriptBase):

    def test_bundle_fetch_refuses_bad_arguments(self):
        out = self._out()
        cases = {
            "no arguments": (),
            "no --set": ("--out", str(out)),
            "no --out": ("--set", "sample"),
            "another --set": ("--set", "partial", "--out", str(out)),
            "--set without a value": ("--out", str(out), "--set"),
            "--out without a value": ("--set", "sample", "--out"),
            "an unknown argument": ("--set", "sample", "--out", str(out), "--evidence-dir", str(self.tmp)),
            "another --arch value": ("--set", "sample", "--out", str(out), "--arch", "x86_64"),
        }
        for case, args in cases.items():
            with self.subTest(case=case):
                r, recs = self._run(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertTrue([ln for ln in r.stderr.splitlines() if ln.startswith("usage: scripts/bundle_fetch.sh")],
                                f"no usage line: {r.stderr!r}")
                self.assertEqual(recs, [], "docker was called on a bad argument")
                self.assertFalse(out.exists() or out.is_symlink(), "--out was created on a bad argument")

    def test_bundle_fetch_tools_first(self):
        """Item 3 step 1: `docker` on PATH before any docker call or write."""
        bindir = self.tmp / "no-docker-bin"
        bindir.mkdir()
        for d in ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"):
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                if name != "docker" and not (bindir / name).exists():
                    os.symlink(os.path.join(d, name), bindir / name)
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), path=str(bindir))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        lines = self._fail_lines(r)
        self.assertTrue(len(lines) == 1 and "docker" in lines[0] and lines[0].endswith("; no retry)"), lines)
        self.assertEqual(recs, [])
        self.assertFalse(out.exists())

    def test_bundle_fetch_refuses_an_unsafe_out(self):
        """U8-1: a symlink, a non-directory or a non-empty directory exits 1
        naming it, untouched, before any pull or request."""
        target = self.tmp / "link-target"
        target.mkdir()
        link = self.tmp / "out-link"
        os.symlink(target, link)
        afile = self.tmp / "out-file"
        afile.write_bytes(b"operator file\n")
        full = self.tmp / "out-full"
        full.mkdir()
        (full / "operator.txt").write_text("keep\n", encoding="utf-8")
        hidden = self.tmp / "out-hidden"
        hidden.mkdir()
        (hidden / ".keep").write_text("keep\n", encoding="utf-8")
        for case, out in (("a symlink to an empty dir", link), ("a regular file", afile),
                          ("a non-empty dir", full), ("a dir holding only a dotfile", hidden)):
            with self.subTest(case=case):
                before = (os.readlink(out) if out.is_symlink() else
                          out.read_bytes() if out.is_file() else sorted(os.listdir(out)))
                r, recs = self._run("--set", "sample", "--out", str(out))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                lines = self._fail_lines(r)
                self.assertTrue(len(lines) == 1 and str(out) in lines[0] and lines[0].endswith("; no retry)"),
                                f"want one FAIL line naming {out}: {lines}")
                self._no_pull_or_run(recs)
                self.assertEqual(self._requested(), [])
                after = (os.readlink(out) if out.is_symlink() else
                         out.read_bytes() if out.is_file() else sorted(os.listdir(out)))
                self.assertEqual(after, before, "--out was touched")
        self.assertEqual(os.listdir(target), [], "the symlink's target was written")

    def test_bundle_fetch_accepts_an_absent_or_empty_out(self):
        with self.subTest(case="absent: created 0700"):
            out = self._out()
            r, _ = self._run("--set", "sample", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700, "item 3 step 2: mkdir, then chmod 0700")
            self._assert_complete(out, ARCH, "sample")
        with self.subTest(case="an empty directory: used in place"):
            out = self._out()
            out.mkdir()
            ino = out.stat().st_ino
            r, _ = self._run("--set", "sample", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
            self.assertEqual(out.stat().st_ino, ino, "the given directory was replaced")
            self._assert_complete(out, ARCH, "sample")

    def test_bundle_fetch_arch_is_the_daemons(self):
        """A75: the arch is the daemon's, passed to the client as `--arch`;
        `--arch` on the command line only asserts it."""
        for daemon, arch in (("x86_64", "amd64"), ("amd64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")):
            with self.subTest(daemon=daemon):
                out = self._out()
                r, recs = self._run("--set", "sample", "--out", str(out), arch=daemon)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
                runs = self._runs(recs)
                self.assertEqual(len(runs), 1, [x["argv"] for x in recs])
                tail = runs[0]["argv"][runs[0]["argv"].index("sources-fetch") + 1:]
                self.assertEqual(dict(zip(tail[::2], tail[1::2])), {"--arch": arch, "--set": "sample"},
                                 f"the client is not run with --arch {arch} --set sample: {tail}")
                self.assertEqual(len(tail), 4, tail)
                self._assert_complete(out, arch, "sample")
        with self.subTest(case="--arch equal to the daemon's"):
            out = self._out()
            r, _ = self._run("--set", "sample", "--out", str(out), "--arch", "amd64")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        for daemon, asserted in (("x86_64", "arm64"), ("aarch64", "amd64")):
            with self.subTest(case=f"--arch {asserted} on a {daemon} daemon"):
                out = self._out()
                r, recs = self._run("--set", "sample", "--out", str(out), "--arch", asserted, arch=daemon)
                # U8-1 / A75: exit 1 naming both, as `bundle.sh --arch` (design item 3 says 2; flagged).
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                lines = self._fail_lines(r)
                self.assertTrue(lines and "amd64" in lines[0] and "arm64" in lines[0], f"names both: {lines}")
                self._no_pull_or_run(recs)
                self.assertFalse(out.exists(), "--out was created before the arch check")
        with self.subTest(case="an unsupported daemon arch"):
            out = self._out()
            r, recs = self._run("--set", "sample", "--out", str(out), arch="s390x")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue([ln for ln in self._fail_lines(r) if "s390x" in ln], r.stderr)
            self._no_pull_or_run(recs)
            self.assertFalse(out.exists())

    def test_bundle_fetch_pulls_then_fetches(self):
        """Items 3 and 7, U8-2, U8-7: the order of the calls, their form, the
        markers and the record lines of a good `--set sample` run."""
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        self._assert_complete(out, ARCH, "sample")
        argvs = [x["argv"] for x in recs]
        # Every call is one of these; nothing else reaches the daemon or a registry.
        for a in argvs:
            with self.subTest(call=" ".join(a)):
                ok = (a[:1] in (["info"], ["version"]) or a[:2] in (["image", "inspect"],) or a[:1] == ["inspect"]
                      or (a[:1] == ["compose"] and any(v in a for v in ("config", "pull", "run", "down", "version"))))
                self.assertTrue(ok, "an unexpected docker call")
                if a[:1] == ["compose"] and "pull" in a:
                    self.assertEqual(self._files(a), [cs.SBOM_COMPOSE_NAME], "a compose pull of another file")
                if a[:1] == ["compose"] and "run" in a:
                    self.assertTrue(re.search(RUN_FETCH_RX, " ".join(a)), "a compose run of another service")
        info = [i for i, a in enumerate(argvs) if a[:1] == ["info"]]
        inspect = [i for i, a in enumerate(argvs) if (a[:2] == ["image", "inspect"] or a[:1] == ["inspect"])
                   and GATES in a]
        pulls = [i for i, a in enumerate(argvs) if a[:1] == ["compose"] and "pull" in a]
        runs = [i for i, a in enumerate(argvs) if a[:1] == ["compose"] and re.search(RUN_FETCH_RX, " ".join(a))]
        downs = [i for i, rec in enumerate(recs) if rec in self._downs(recs)]
        self.assertTrue(info and inspect and len(pulls) == 1 and len(runs) == 1 and downs,
                        f"want info, inspect {GATES}, one pull, one run, a down: {argvs}")
        self.assertTrue(info[0] < inspect[0] < pulls[0] < runs[0] < downs[-1], f"order: {argvs}")
        with self.subTest(stage="pull: N1 amendment U2's form"):
            pull = recs[pulls[0]]
            a, env = pull["argv"], pull["env"]
            self.assertEqual(self._opt(a, "--env-file"), [".env.example"], a)
            self.assertEqual(a[-2:], ["pull", "sbom"], "pulls the `sbom` service only")
            for var in ("KE_SBOM_IN", "KE_SBOM_OUT"):
                self.assertTrue(env.get(var, "").endswith("/nonexistent"), f"{var}: {env.get(var)!r}")
            for var in sorted((set(self.sbom_required) | {"KE_SBOM_USER"}) - {"KE_SBOM_IN", "KE_SBOM_OUT"}):
                self.assertTrue(env.get(var), f"{var} is not set for the pull (the file's ${{{var}:?}})")
            configs = [x for x in argvs[:pulls[0]] if x[:1] == ["compose"] and "config" in x
                       and self._files(x) == [cs.SBOM_COMPOSE_NAME]]
            self.assertTrue(configs, "the generator ref is not read from docker-compose.sbom.yml before the pull")
        with self.subTest(stage="fetch: the run line"):
            run = recs[runs[0]]
            a, env = run["argv"], run["env"]
            self.assertEqual(self._files(a), [SOURCES_YML], a)
            self.assertEqual(self._opt(a, "--env-file"), [".env.example"], a)
            project = (self._opt(a, "-p") + self._opt(a, "--project-name") + [""])[0]
            self.assertRegex(project, r"^ke-fetch-[0-9a-f]{8}$", "the run's own project ke-fetch-<8 hex>")
            self.assertIn("--rm", a)
            self.assertEqual(self._opt(a, "--pull"), ["never"], a)
            self.assertTrue(env.get("KE_SOURCES_IN", "").endswith("/nonexistent"), env.get("KE_SOURCES_IN"))
            self.assertEqual(os.path.normpath(os.path.join(run["cwd"], env.get("KE_SOURCES_OUT", ""))),
                             os.path.normpath(str(out)), "KE_SOURCES_OUT is not the out dir")
            self.assertEqual(env.get("KE_SOURCES_USER"), f"{os.getuid()}:{os.getgid()}", "the caller's uid:gid")
            down = recs[downs[-1]]
            self.assertIn(project, self._opt(down["argv"], "-p") + self._opt(down["argv"], "--project-name"),
                          "the run's project is not the one torn down")
            self.assertIn("--volumes", down["argv"])
        with self.subTest(stage="markers and record lines (U8-2)"):
            lines = r.stdout.splitlines()
            self.assertIn("== sources: pull ==", lines)
            self.assertIn("== sources: fetch ==", lines)
            done = [i for i, ln in enumerate(lines) if DONE_RX.match(ln)]
            self.assertEqual(len(done), 1, f"no `== sources: done (pull <a> s, fetch <b> s) ==` line: {lines[-5:]}")
            self.assertTrue(lines.index("== sources: pull ==") < lines.index("== sources: fetch ==") < done[0])
            kept = {tuple(ln.split()[2:4]) for ln in lines if ln.startswith(("bundle_fetch: ok ", "bundle_fetch: held "))}
            self.assertEqual(kept, {(k, f["name"]) for k, f in plan_of(self.b, ARCH, "sample")},
                             "one `ok` or `held` line per planned file, on stdout (the record the caller tees)")
            neo = [ln for ln in lines if ln.startswith(f"bundle_fetch: ok {NEO_KEY} ")]
            self.assertTrue(neo and neo[0].endswith(" hops=github.com,codeload.github.com"), neo)
            self.assertNotIn("FAIL", r.stdout + r.stderr)

    def test_bundle_fetch_full_set(self):
        out = self._out()
        r, recs = self._run("--set", "full", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        runs = self._runs(recs)
        self.assertEqual(len(runs), 1)
        self.assertIn(("--set", "full"), list(zip(runs[0]["argv"], runs[0]["argv"][1:])))
        self._assert_complete(out, ARCH, "full")
        arm_only = {f["url"] for k, e in self.b.components.items() if e["arches"] == ["arm64"] for f in e["files"]}
        self.assertTrue(arm_only, "fixture: an arm64-only entry")
        self.assertFalse(arm_only & set(self._requested()), "an entry of the other arch was requested")

    def test_bundle_fetch_stops_when_the_pull_fails(self):
        for case, given in (("--out absent", False), ("--out an empty dir", True)):
            with self.subTest(case=case):
                out = self._out()
                if given:
                    out.mkdir()
                r, recs = self._run("--set", "sample", "--out", str(out), FAKE_DOCKER_FAIL_NTH=f"{PULL_SBOM_RX}#1")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(PULL_FAIL.format(ref=self.sbom_ref), (r.stdout + r.stderr).splitlines())
                self.assertEqual(len([x for x in recs if x["argv"][:1] == ["compose"] and "pull" in x["argv"]]), 1,
                                 "the pull was retried")
                self.assertEqual(self._runs(recs), [], "the fetch ran after a failed pull")
                self.assertEqual(self._requested(), [])
                if given:
                    self.assertTrue(out.is_dir() and os.listdir(out) == [], "the given --out is not returned empty")
                else:
                    self.assertFalse(out.exists() or out.is_symlink(), "the --out the script created was left")
                self.assertNotRegex(r.stdout, DONE_RX)

    def _bad_middle_file(self) -> tuple[dict[str, Any], str, str]:
        """FAKE_RESOLVE_NET with the sample's middle file served with wrong
        bytes; returns (net, its host, its name)."""
        plan = plan_of(self.b, ARCH, "sample")
        _, f = plan[len(plan) // 2]
        net = _net(self.b)
        url = self.b.chain(f["url"])[-1]
        status, headers, body = net[url]
        net[url] = [status, headers, ("X" if body[:1] != "X" else "Y") + body[1:]]
        return net, host_of(f["url"]), f["name"]

    def test_bundle_fetch_leaves_no_out_on_a_failed_fetch(self):
        """U8-6: a fault on a middle file of the set leaves no --out the
        script created, and a given --out empty; no record; the client's
        FAIL line then the script's; the project torn down."""
        net, host, name = self._bad_middle_file()
        for case, given in (("--out absent", False), ("--out an empty dir", True)):
            with self.subTest(case=case):
                out = self._out()
                if given:
                    out.mkdir()
                r, recs = self._run("--set", "sample", "--out", str(out), net=net)
                text = r.stdout + r.stderr
                self.assertEqual(r.returncode, 1, text)
                lines = self._fail_lines(r)
                client = [i for i, ln in enumerate(lines) if ln.startswith(f"bundle_fetch: FAIL (stage fetch: {host}: {name}: ")]
                script = [i for i, ln in enumerate(lines) if ln == FETCH_EXITED.format(rc=1)]
                self.assertTrue(len(client) == 1 and len(script) == 1 and client[0] < script[0],
                                f"want the client's FAIL line, then `{FETCH_EXITED.format(rc=1)}`: {lines}")
                self.assertNotIn("Traceback", text)
                self.assertNotRegex(r.stdout, DONE_RX)
                if given:
                    self.assertTrue(out.is_dir() and os.listdir(out) == [],
                                    f"the given --out is not returned empty: {sorted(os.listdir(out)) if out.is_dir() else out}")
                else:
                    self.assertFalse(out.exists() or out.is_symlink(),
                                     f"the --out the script created was left: {sorted(os.listdir(out)) if out.is_dir() else out}")
                runs = self._runs(recs)
                self.assertEqual(len(runs), 1, "the fetch was retried")
                project = (self._opt(runs[0]["argv"], "-p") + [""])[0]
                downs = [d for d in self._downs(recs) if project in self._opt(d["argv"], "-p")]
                self.assertTrue(downs and recs.index(downs[-1]) > recs.index(runs[0]), "the project was not torn down")
                for var in ("KE_SOURCES_IN", "KE_SOURCES_OUT", "KE_SOURCES_USER"):
                    self.assertTrue(downs[-1]["env"].get(var), f"the down has no dummy {var} (the file's ${{{var}:?}})")

    def test_bundle_fetch_never_retries(self):
        """Q61: one pull and one fetch run per invocation, also when one fails;
        each URL at most once."""
        net, _, _ = self._bad_middle_file()
        for case, kw in (("the pull fails", {"FAKE_DOCKER_FAIL_NTH": f"{PULL_SBOM_RX}#1"}),
                         ("the fetch fails", {"net": net}),
                         ("the fetch run itself fails", {"FAKE_DOCKER_FAIL_NTH": f"{RUN_FETCH_RX}#1"})):
            with self.subTest(case=case):
                r, recs = self._run("--set", "sample", "--out", str(self._out()), **kw)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                pulls = [x for x in recs if x["argv"][:1] == ["compose"] and "pull" in x["argv"]]
                self.assertEqual(len(pulls), 1, "the generator pull ran more than once")
                self.assertLessEqual(len(self._runs(recs)), 1, "the fetch ran more than once")
                requested = self._requested()
                self.assertEqual(len(requested), len(set(requested)), "a URL was requested twice")

    def test_bundle_fetch_writes_the_record_last(self):
        """A76 and item 3 step 6: a good run's fetch.json names set, arch and
        the lock's sha256 (U9 checks them); a failed run leaves none; a
        missing or linked fetch.json after the client fails the run."""
        with self.subTest(case="a good run"):
            out = self._out()
            r, _ = self._run("--set", "sample", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
            self._assert_complete(out, ARCH, "sample")
        net, _, _ = self._bad_middle_file()
        with self.subTest(case="a failed run"):
            out = self._out()
            out.mkdir()
            r, _ = self._run("--set", "sample", "--out", str(out), net=net)
            self.assertEqual(r.returncode, 1)
            self.assertFalse((out / "fetch.json").exists())
        fake = self.tmp / "fakebin" / "docker"
        for i, (case, action) in enumerate((
                ("fetch.json removed after the client", 'rm -f -- "$KE_SOURCES_OUT/fetch.json"'),
                ("fetch.json a link after the client",
                 'mv -- "$KE_SOURCES_OUT/fetch.json" "$KE_SOURCES_OUT/../moved.json" && '
                 'ln -s ../moved.json "$KE_SOURCES_OUT/fetch.json"'))):
            with self.subTest(case=case):
                d = self.tmp / f"record-wrap-{i}"
                d.mkdir()
                (d / "docker").write_text(
                    "#!/bin/bash\n" f"'{fake}' \"$@\"\nrc=$?\n"
                    "if [ \"$rc\" -eq 0 ]; then case \" $* \" in *\" run \"*\" sources-fetch \"*) "
                    + action + " ;; esac; fi\n"
                    "exit $rc\n", encoding="utf-8", newline="\n")
                (d / "docker").chmod(0o755)
                out = self._out()
                r, _ = self._run("--set", "sample", "--out", str(out), path=f"{d}{os.pathsep}{self.path}")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertTrue(self._fail_lines(r), r.stderr)
                self.assertNotRegex(r.stdout, DONE_RX)
                self.assertFalse(out.exists() or out.is_symlink(), "the --out the script created was left")

    def test_bundle_fetch_needs_the_gates_image(self):
        for case, tag in (("the default tag", None), ("KE_IMAGE_TAG", "wt-0123456789ab")):
            with self.subTest(case=case):
                img = f"ke-gates:{tag or 'local'}"
                out = self._out()
                extra = {"KE_IMAGE_TAG": tag} if tag else {}
                r, recs = self._run("--set", "sample", "--out", str(out), images={self.sbom_ref: _image()}, **extra)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(IMAGES_FAIL.format(img=img), (r.stdout + r.stderr).splitlines())
                self._no_pull_or_run(recs)
                self.assertFalse(out.exists(), "the --out the script created was left")
        with self.subTest(case="KE_IMAGE_TAG present"):
            out = self._out()
            r, recs = self._run("--set", "sample", "--out", str(out), KE_IMAGE_TAG="wt-0123456789ab",
                                images={"ke-gates:wt-0123456789ab": _image(), self.sbom_ref: _image()})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])

    def test_bundle_fetch_refuses_a_bad_user(self):
        """U8-7: the uid:gid set as the service's user must match ^[0-9]+:[0-9]+$."""
        d = self.tmp / "id-shim"
        d.mkdir()
        real = shutil.which("id")
        self.assertIsNotNone(real)
        (d / "id").write_text("#!/bin/bash\n" "case \"$1\" in -u) echo '1000 0' ;; -g) echo 1000 ;; "
                              f"*) exec '{real}' \"$@\" ;; esac\n", encoding="utf-8", newline="\n")
        (d / "id").chmod(0o755)
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), path=f"{d}{os.pathsep}{self.path}")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(len(self._fail_lines(r)), 1, r.stderr)
        self._no_pull_or_run(recs)
        self.assertFalse(out.exists(), "the --out the script created was left")

    def test_bundle_fetch_takes_no_caller_key(self):
        """U8-7, item 3: the caller's COMPOSE_* and KE_SOURCES_* never reach
        the run; -f/-p/--env-file name the script's own; the repo-root .env
        is never read (PSC-6)."""
        (self.repo / ".env").write_text("KE_MODEL_UPSTREAM=from-dotenv\nKE_SOURCES_USER=0:0\n", encoding="utf-8")
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), COMPOSE_FILE="docker-compose.yml",
                            COMPOSE_PROFILES="gates", COMPOSE_PATH_SEPARATOR=";", COMPOSE_PROJECT_NAME="caller",
                            KE_SOURCES_IN="/etc", KE_SOURCES_OUT="/etc", KE_SOURCES_USER="0:0",
                            KE_MODEL_UPSTREAM="caller-model-host")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        for rec in [x for x in recs if x["argv"][:1] == ["compose"]]:
            a, env = rec["argv"], rec["env"]
            with self.subTest(call=" ".join(a[:8])):
                self.assertNotIn("COMPOSE_PROFILES", env, "COMPOSE_PROFILES reaches compose")
                self.assertNotIn("COMPOSE_PATH_SEPARATOR", env, "COMPOSE_PATH_SEPARATOR reaches compose")
                if "version" not in a:
                    self.assertTrue(self._files(a), "a compose call without -f (the caller's COMPOSE_FILE would win)")
                    self.assertEqual(self._opt(a, "--env-file"), [".env.example"], "the repo-root .env may be read")
        run = self._runs(recs)[0]
        self.assertTrue(self._opt(run["argv"], "-p"), "the run has no -p (the caller's project would win)")
        self.assertTrue(run["env"]["KE_SOURCES_IN"].endswith("/nonexistent"))
        self.assertEqual(os.path.normpath(os.path.join(run["cwd"], run["env"]["KE_SOURCES_OUT"])),
                         os.path.normpath(str(out)))
        self.assertEqual(run["env"]["KE_SOURCES_USER"], f"{os.getuid()}:{os.getgid()}")
        self._assert_complete(out, ARCH, "sample")

    def test_bundle_fetch_cleans_up_on_a_signal(self):
        """U8-6: INT, TERM or HUP during the fetch: the run exits non-zero,
        removes the --out it created (with what the client had written) and
        tears its project down."""
        if not hasattr(os, "killpg"):  # pragma: no cover - the gates image is Linux
            self.skipTest("os.killpg is POSIX only")
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                out = self._out()
                marker = self.tmp / f"in-fetch-{sig.name}"
                hooks = [{"on": RUN_FETCH_RX, "write": {str(out / ("a" * 64)): "partial\n", str(marker): "x"},
                          "sleep": 60}]
                self._fresh_logs()
                env = self._env(FAKE_DOCKER_HOOKS=json.dumps(hooks))
                proc = subprocess.Popen(["bash", "scripts/bundle_fetch.sh", "--set", "sample", "--out", str(out)],
                                        cwd=self.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=True)
                text = ""
                try:
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline and proc.poll() is None and not marker.exists():
                        time.sleep(0.1)
                    if not marker.exists():
                        if proc.poll() is None:
                            os.killpg(proc.pid, signal.SIGKILL)
                        stdout, stderr = proc.communicate(timeout=60)
                        self.fail(f"the script never reached the fetch run: {stdout}{stderr}")
                    time.sleep(0.3)
                    os.killpg(proc.pid, sig)
                    stdout, stderr = proc.communicate(timeout=60)
                    text = stdout + stderr
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                self.assertNotEqual(proc.returncode, 0, f"exit 0 after {sig.name}:\n{text}")
                self.assertNotRegex(text, r"(?m)^== sources: done")
                self.assertFalse(out.exists() or out.is_symlink(), f"--out was left after {sig.name}")
                recs = fake_docker.records(self.json)
                runs = self._runs(recs)
                project = (self._opt(runs[0]["argv"], "-p") + [""])[0] if runs else ""
                self.assertTrue([d for d in self._downs(recs) if project and project in self._opt(d["argv"], "-p")],
                                f"the project was not torn down after {sig.name}")

    # --- U8b rework 1 (review B-1, B-2, N-2, N-3, N-5; security L-1) ------------

    def _assert_refused_untouched(self, r: subprocess.CompletedProcess, recs: list[dict[str, Any]],
                                  *, contains: tuple[str, ...]) -> None:
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
        lines = self._fail_lines(r)
        self.assertTrue(len(lines) == 1 and lines[0].startswith("bundle_fetch: FAIL (stage out: ")
                        and lines[0].endswith("; no retry)") and all(c in lines[0] for c in contains),
                        f"want one `bundle_fetch: FAIL (stage out: ...; no retry)` line holding {contains}: {lines}")
        self._no_pull_or_run(recs)
        self.assertEqual(self._requested(), [])
        self.assertNotRegex(r.stdout, DONE_RX)

    def test_bundle_fetch_refuses_an_unlistable_out(self):
        """Review B-1: a non-empty --out the caller can write and search but
        not list (mode 0300) is refused untouched, `stage out: cannot list`,
        before any pull or run (U8-1; the emptiness check must not fail open
        when `ls` fails)."""
        if not hasattr(os, "geteuid"):
            self.skipTest("mode bits on a directory need POSIX (the gates image runs this row)")
        if os.geteuid() == 0:
            self.skipTest("uid 0 lists any directory whatever its mode (the gates image runs as uid 10001)")
        out = self.tmp / "out-unlistable"
        out.mkdir()
        (out / "operator.txt").write_text("keep\n", encoding="utf-8")
        os.chmod(out, 0o300)
        self.addCleanup(os.chmod, out, 0o700)
        r, recs = self._run("--set", "sample", "--out", str(out))
        mode = stat.S_IMODE(out.stat().st_mode)
        os.chmod(out, 0o700)
        self._assert_refused_untouched(r, recs, contains=("stage out: cannot list", str(out)))
        self.assertEqual(mode, 0o300, "the unlistable --out's mode was changed")
        self.assertEqual(sorted(os.listdir(out)), ["operator.txt"], "the unlistable --out was written to or emptied")
        self.assertEqual((out / "operator.txt").read_text(encoding="utf-8"), "keep\n")

    def test_bundle_fetch_refuses_a_linked_out_behind_slashes_or_dot(self):
        """Security L-1: every trailing `/` is stripped before the symlink
        check, so `--out link//` is refused as a symlink; a last component
        of `.` (`--out link/.`, `--out dir/.`) is refused. Untouched, before
        any pull or run; the link's target is never written."""
        if os.name == "nt":
            self.skipTest("symlinks are not made on a Windows host (the gates image runs this row)")
        for i, (case, suffix, via_link, contains) in enumerate((
                ("link//", "//", True, ("symlink",)),
                ("link///", "///", True, ("symlink",)),
                ("link/.", "/.", True, ()),
                ("link/./", "/./", True, ()),
                ("an empty dir/.", "/.", False, ()))):
            with self.subTest(case=case):
                target = self.tmp / f"l1-target-{i}"
                target.mkdir()
                tmode = stat.S_IMODE(target.stat().st_mode)
                link = self.tmp / f"l1-link-{i}"
                if via_link:
                    try:
                        os.symlink(target, link, target_is_directory=True)
                    except (OSError, NotImplementedError) as exc:  # pragma: no cover - the gates image is Linux
                        self.skipTest(f"symlinks cannot be made here ({type(exc).__name__})")
                base = link if via_link else target
                r, recs = self._run("--set", "sample", "--out", f"{base}{suffix}")
                self._assert_refused_untouched(r, recs, contains=(*contains, str(base)))
                self.assertEqual(os.listdir(target), [], f"{case}: the directory behind --out was written")
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), tmode, f"{case}: its mode was changed")
                if via_link:
                    self.assertTrue(link.is_symlink() and os.readlink(link) == str(target), "the link was changed")

    def test_bundle_fetch_leaves_an_out_that_appears_after_the_check(self):
        """Review N-3: the cleanup empties a given --out only when stage 2
        saw it there. An --out absent at stage 2 that appears before the
        script's mkdir (here: during the stage-3 image check) makes the run
        fail, and the cleanup leaves it and its contents alone."""
        fake = self.tmp / "fakebin" / "docker"
        d = self.tmp / "race-wrap"
        d.mkdir()
        (d / "docker").write_text(
            "#!/bin/bash\n" f"'{fake}' \"$@\"\nrc=$?\n"
            "case \" $* \" in *\" image inspect \"*) mkdir -p -- \"$FAKE_RACE_OUT\" && "
            "printf 'keep\\n' > \"$FAKE_RACE_OUT/operator.txt\" ;; esac\n"
            "exit $rc\n", encoding="utf-8", newline="\n")
        (d / "docker").chmod(0o755)
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), path=f"{d}{os.pathsep}{self.path}",
                            FAKE_RACE_OUT=str(out))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
        self.assertEqual(len(self._fail_lines(r)), 1, r.stderr)
        self._no_pull_or_run(recs)
        self.assertTrue(out.is_dir() and sorted(os.listdir(out)) == ["operator.txt"],
                        f"an --out the script never checked was emptied: "
                        f"{sorted(os.listdir(out)) if out.is_dir() else 'gone'}")
        self.assertEqual((out / "operator.txt").read_text(encoding="utf-8"), "keep\n")

    def test_bundle_fetch_passes_the_clients_bad_argument_exit_through(self):
        """Review N-5 / O-5: a client exit of 2 (a bad argument) is passed
        through as the script's exit status, after exactly one script line
        naming the stage and the code; a created --out is removed."""
        hooks = [{"on": RUN_FETCH_RX, "exit": 2}]
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr[-3000:])
        self.assertEqual(self._fail_lines(r), [FETCH_EXITED.format(rc=2)])
        self.assertEqual(len(self._runs(recs)), 1, "the fetch was retried")
        self.assertFalse(out.exists() or out.is_symlink(), "the --out the script created was left")
        self.assertNotRegex(r.stdout, DONE_RX)

    def test_bundle_fetch_names_compose_when_compose_itself_fails(self):
        """Review N-5: when `docker compose run` fails with a code the client
        never uses (125: compose or the daemon, not sources_fetch.py, which
        exits 0, 1 or 2), the script's one line names compose, not
        `sources_fetch.py exited`."""
        hooks = [{"on": RUN_FETCH_RX, "exit": 125}]
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        lines = self._fail_lines(r)
        self.assertTrue(len(lines) == 1 and lines[0].startswith("bundle_fetch: FAIL (stage fetch: ")
                        and "compose" in lines[0] and "sources_fetch.py exited" not in lines[0]
                        and "125" in lines[0] and lines[0].endswith("; no retry)"),
                        f"want one stage-fetch line naming compose and its code 125: {lines}")
        self.assertEqual(len(self._runs(recs)), 1, "the fetch was retried")
        self.assertFalse(out.exists() or out.is_symlink(), "the --out the script created was left")

    def test_bundle_fetch_keeps_the_callers_platform_and_env_files_out(self):
        """Review N-2 (as scan.sh; "takes no caller key"): the caller's
        DOCKER_DEFAULT_PLATFORM and COMPOSE_ENV_FILES reach no docker call."""
        env_file = self.tmp / "caller.env"
        env_file.write_text("KE_SOURCES_USER=0:0\n", encoding="utf-8")
        out = self._out()
        r, recs = self._run("--set", "sample", "--out", str(out), DOCKER_DEFAULT_PLATFORM="linux/arm64",
                            COMPOSE_ENV_FILES=str(env_file), FAKE_DOCKER_RECORD_ENV="DOCKER_DEFAULT_PLATFORM")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        self.assertTrue(recs, "harness: no docker call was recorded")
        for rec in recs:
            with self.subTest(call=" ".join(rec["argv"][:8])):
                for var in ("DOCKER_DEFAULT_PLATFORM", "COMPOSE_ENV_FILES"):
                    self.assertNotIn(var, rec["env"], f"the caller's {var} reaches docker")
        self._assert_complete(out, ARCH, "sample")

    def test_bundle_fetch_cleanup_survives_a_second_signal(self):
        """Review B-2: a second INT, TERM or HUP while the cleanup brings the
        project down (a double Ctrl-C, a supervisor's TERM after INT) does
        not cut the cleanup short: the --out it created is still removed."""
        if not hasattr(os, "killpg"):  # pragma: no cover - the gates image is Linux
            self.skipTest("os.killpg is POSIX only")
        for second in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(second=second.name):
                out = self._out()
                in_fetch = self.tmp / f"b2-in-fetch-{second.name}"
                in_down = self.tmp / f"b2-in-down-{second.name}"
                hooks = [{"on": RUN_FETCH_RX, "write": {str(out / ("a" * 64)): "partial\n", str(in_fetch): "x"},
                          "sleep": 60},
                         {"on": r"docker-compose\.sources\.yml down\b", "touch": str(in_down), "sleep": 3}]
                self._fresh_logs()
                env = self._env(FAKE_DOCKER_HOOKS=json.dumps(hooks))
                proc = subprocess.Popen(["bash", "scripts/bundle_fetch.sh", "--set", "sample", "--out", str(out)],
                                        cwd=self.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=True)
                text = ""
                try:
                    for marker, sig in ((in_fetch, signal.SIGINT), (in_down, second)):
                        deadline = time.monotonic() + 60
                        while time.monotonic() < deadline and proc.poll() is None and not marker.exists():
                            time.sleep(0.1)
                        if not marker.exists():
                            if proc.poll() is None:
                                os.killpg(proc.pid, signal.SIGKILL)
                            stdout, stderr = proc.communicate(timeout=60)
                            self.fail(f"the script never reached {marker.name}: {stdout}{stderr}")
                        time.sleep(0.3)
                        os.killpg(proc.pid, sig)
                    stdout, stderr = proc.communicate(timeout=60)
                    text = stdout + stderr
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                self.assertNotEqual(proc.returncode, 0, f"exit 0 after INT then {second.name}:\n{text}")
                self.assertFalse(out.exists() or out.is_symlink(),
                                 f"--out was left after a second {second.name} during the teardown (review B-2)")


if __name__ == "__main__":
    unittest.main()
