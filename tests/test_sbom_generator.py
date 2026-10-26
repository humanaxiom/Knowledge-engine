"""platform-sbom U2: the pinned SBOM generator, its compose service and the
bundle's refusal when it is absent (PSC-20).

Criteria: docs/requirements.md § "Item: platform-sbom" PSC-20, which reuses
PSC-1 (pin and provenance), PSC-2/PSC-3 (no network, no socket, read-only
input) and PSC-8 (not in the bundle). Design: docs/architecture.md
ADR-KE-016 point 1; docs/evidence/platform-sbom/design-notes.md N1 (the
`sbom` service and the presence check) and N2 (provenance). Test names are
PSC-20's tags. The grype precedent is tests/test_image_scan.py
(ScanComposeTest, ScanBundleTest); its compose helpers are reused here.

Interface pinned by these tests (tester, RED U2, 2026-10-23):
- `docker-compose.sbom.yml` at the repository root, standalone, no profiles.
  Its services are `sbom` and, from U8, `sources-fetch` (N4); nothing else.
- `sbom`'s image is `anchore/syft:v<X.Y.Z>@sha256:<64 hex>` (the multi-arch
  index digest). That line is the only place in the repository, outside
  docs/ and tests/, that names an `anchore/syft` reference or the digest.
  bundle.sh (and U8's bundle_fetch.sh) read it through compose.
- docs/evidence/platform-sbom/generator-provenance.md names `anchore/syft`,
  the pinned `v<X.Y.Z>` and the index digest (shape only; its content is
  security's, N2).
- `sbom` row by row (N1): `network_mode: none` and no `networks`;
  `read_only: true`; tmpfs exactly `/tmp`; `cap_drop: [ALL]`, no `cap_add`;
  `security_opt` holds `no-new-privileges:true` and nothing unconfined; not
  privileged; no ports, devices, volumes_from, extra_hosts, secrets,
  configs, env_file, build, restart policy or host namespaces.
  Mounts are exactly two binds: `${KE_SBOM_IN:?...}` at `/in` read-only (the
  saved image tars) and `${KE_SBOM_OUT:?...}` at `/out` read-write, the only
  writable mount. No Docker socket, no DOCKER_* key.
  Environment is literals only and holds N1's keys with N1's values
  (U2 re-target, design-notes "N1 amendment, U2" *Env keys*): TMPDIR=/out/tmp
  and eight SYFT_* keys, each `false`: SYFT_CHECK_FOR_APP_UPDATE,
  SYFT_JAVA_USE_NETWORK, SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES,
  SYFT_GOLANG_SEARCH_REMOTE_LICENSES, SYFT_GOLANG_USE_PACKAGES_LIB,
  SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES, SYFT_PYTHON_SEARCH_REMOTE_LICENSES,
  SYFT_CPP_VCPKG_ALLOW_GIT_CLONE. N1's fallback HOME and
  XDG_CACHE_HOME are allowed only at or under /tmp, the container's tmpfs,
  never under /out (security I-2, carried to U3 by the orchestrator's U2
  commit gate: syft's config search path must not sit in the host-writable
  work dir; tester, U3 RED, 2026-10-23). Any further SYFT_* key must be
  the literal `false` (switching a feature off); no other key is allowed.
  Its own label (PSC-20): the file sets no top-level `name`, no
  `container_name` and no `com.docker.compose.*` label, so the project label
  is the one `compose -p <project>-sbom` gives it at run time (N1; the run is
  U3's, and U3 tests the `-p`).
- bundle.sh, before anything is written to --out, reads the reference with
  `docker compose --env-file .env.example -f docker-compose.sbom.yml config
  ...` (the `sbom` service's image only; the file may hold a second
  service), requires one line with a `@sha256:` pin, and runs
  `docker image inspect <ref>`. Every compose call naming the file carries
  `--env-file .env.example`, so the repo-root `.env` (model keys) is never
  loaded for it (N1 amendment, U2). Absent (or tag-only): it exits non-zero
  naming the reference, with --out untouched, no record file, no tag, save
  or pull. Absent, stderr holds exactly (N1, from U2 until U8):
  `bundle: the SBOM generator image is not present (<ref>); pull it first
  with: docker pull <ref>; this script never pulls`. Real compose refuses to
  load the file while `${KE_SBOM_IN:?}` / `${KE_SBOM_OUT:?}` are unset, and so
  does the fake (tests/fake_docker.py FAKE_COMPOSE_FILE_REQUIRED): N1 sets
  them to dummy values for the read (`--no-interpolate` would also load it).
- bundle.sh has no pull in it: no `pull` word outside a `die`/`echo` message
  and comments, and no `--pull` value but `never`.
- The bundle (PSC-8 form) holds no file named after syft or the sbom compose
  file, no content naming `anchore/syft`, `docker-compose.sbom` or the
  pinned digest, and no manifest entry for the generator.

Every check is a function returning a list of problems, so the U2 controls
(docs/evidence/platform-sbom/u2/red-mutants.txt) can run each on mutants.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests import compose_support as cs
from tests.engine_support import ROOT
from tests.test_image_scan import _env_entries, _mounts, _tmpfs_targets
from tests.test_offline_bundle import _BundleBase, _rel

SBOM_COMPOSE = ROOT / cs.SBOM_COMPOSE_NAME
BUNDLE_SH = ROOT / "scripts" / "bundle.sh"
PROVENANCE = ROOT / "docs" / "evidence" / "platform-sbom" / "generator-provenance.md"

COMPOSE_MISSING = "docker-compose.sbom.yml is missing (PSC-20; ADR-KE-016 point 1, design-notes N1)"
GENERATOR_REF = re.compile(r"^anchore/syft:v(\d+\.\d+\.\d+)@sha256:([0-9a-f]{64})$")
# Any written reference to the generator image: a tag or a digest after the name.
SYFT_REF_ANY = re.compile(r"(?i)anchore/syft(?::[A-Za-z0-9._-]+|@sha256:)")
# N1 (two services) and N4 (sources-fetch, U8).
ALLOWED_SERVICES = {"sbom", "sources-fetch"}
# N1 Environment row, literal values (U2 re-target: the eight SYFT_* keys of
# design-notes "N1 amendment, U2" *Env keys*, from `syft config` of v1.54.1,
# docs/evidence/platform-sbom/u2/syft-v1.54.1-config.txt).
REQUIRED_ENV = {
    "TMPDIR": "/out/tmp",
    "SYFT_CHECK_FOR_APP_UPDATE": "false",
    "SYFT_JAVA_USE_NETWORK": "false",
    "SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES": "false",
    "SYFT_GOLANG_SEARCH_REMOTE_LICENSES": "false",
    "SYFT_GOLANG_USE_PACKAGES_LIB": "false",
    "SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES": "false",
    "SYFT_PYTHON_SEARCH_REMOTE_LICENSES": "false",
    "SYFT_CPP_VCPKG_ALLOW_GIT_CLONE": "false",
}
# N1 presence check, absent (U2 until U8; U8 swaps the middle clause for
# `run scripts/bundle_fetch.sh first` in the commit that adds that script).
REFUSAL = ("bundle: the SBOM generator image is not present ({ref}); "
           "pull it first with: docker pull {ref}; this script never pulls")
# N1 *Confirm at GREEN* fallback: a literal HOME / XDG_CACHE_HOME. Security
# I-2 (u2/security.md; U2 commit gate carry list): at or under /tmp (tmpfs),
# never under the host-writable /out (U3 RED, 2026-10-23).
FALLBACK_ENV = {"HOME", "XDG_CACHE_HOME"}
IN_SOURCE = re.compile(r"^\$\{KE_SBOM_IN:\?[^}]*\}$")
OUT_SOURCE = re.compile(r"^\$\{KE_SBOM_OUT:\?[^}]*\}$")
SOCKET_MARKERS = (*cs.SOCKET_MARKERS, "docker.sock")
# Paths where a pin may be quoted (records, criteria, tests); everything else
# in the repository is "committed configuration" for the one-place rule.
PIN_EXEMPT_PREFIXES = ("docs/", "tests/")


# --------------------------------------------------------------------------
# Checks (each returns problems; [] is a pass)
# --------------------------------------------------------------------------

def generator_ref(data: Mapping[str, Any]) -> str:
    svc = ((data.get("services") or {}).get("sbom")) or {}
    return str(svc.get("image", ""))


def pin_problems(data: Mapping[str, Any]) -> list[str]:
    """PSC-20 bullet 1 in the compose file: the `sbom` service exists and its
    image is anchore/syft:v<X.Y.Z>@sha256:<64 hex>."""
    services = data.get("services") or {}
    if "sbom" not in services:
        return ["docker-compose.sbom.yml defines no `sbom` service (N1)"]
    problems = []
    extra = sorted(set(services) - ALLOWED_SERVICES)
    if extra:
        problems.append(f"docker-compose.sbom.yml defines {extra}; N1/N4 allow only sbom and sources-fetch")
    ref = generator_ref(data)
    if not GENERATOR_REF.match(ref):
        problems.append(f"sbom image {ref!r} is not anchore/syft:v<X.Y.Z>@sha256:<64 hex> (PSC-20, PSC-1 form)")
    if "latest" in ref:
        problems.append("sbom image uses a latest tag")
    return problems


def pin_place_problems(files: Mapping[str, str], digest: str | None) -> list[str]:
    """PSC-20/PSC-1: the pin is held in exactly one committed place,
    docker-compose.sbom.yml, once. `files` is rel path -> text."""
    problems = []
    for rel, text in sorted(files.items()):
        if rel.startswith(PIN_EXEMPT_PREFIXES):
            continue
        refs = len(SYFT_REF_ANY.findall(text))
        digests = text.count(digest) if digest else 0
        if rel == cs.SBOM_COMPOSE_NAME:
            if refs != 1:
                problems.append(f"{rel} names an anchore/syft reference {refs} times, want exactly 1")
            if digest and digests != 1:
                problems.append(f"{rel} holds the generator digest {digests} times, want exactly 1")
            continue
        if refs:
            problems.append(f"{rel} names an anchore/syft reference; the pin lives only in "
                            f"{cs.SBOM_COMPOSE_NAME} (read it through compose)")
        if digests:
            problems.append(f"{rel} holds the generator's digest; the pin lives only in {cs.SBOM_COMPOSE_NAME}")
    if cs.SBOM_COMPOSE_NAME not in files:
        problems.append(f"{cs.SBOM_COMPOSE_NAME} is not a committed (or new, unignored) file")
    return problems


def provenance_problems(ref: str, text: str | None) -> list[str]:
    """N2 shape: the record exists and names the image, the tag and the digest."""
    if text is None:
        return [f"{_rel(PROVENANCE, ROOT)} is missing: security records the generator's provenance "
                "(PSC-1 form, design-notes N2) before the pin is committed"]
    m = GENERATOR_REF.match(ref)
    if not m:
        return ["no valid pin to compare the provenance record with"]
    problems = []
    if "anchore/syft" not in text:
        problems.append("the provenance record does not name anchore/syft")
    if not re.search(rf"\bv{re.escape(m.group(1))}\b", text):
        problems.append(f"the provenance record does not name the pinned release v{m.group(1)}")
    if m.group(2) not in text:
        problems.append("the provenance record does not hold the pinned index digest")
    return problems


def hardening_problems(data: Mapping[str, Any]) -> list[str]:
    """PSC-20 bullets 2 and 3, N1 row by row, for the `sbom` service."""
    svc = ((data.get("services") or {}).get("sbom"))
    if not isinstance(svc, dict):
        return ["docker-compose.sbom.yml defines no `sbom` service (N1)"]
    p: list[str] = []
    # Network (PSC-20: network_mode none).
    if svc.get("network_mode") != "none":
        p.append("sbom: network_mode is not `none`")
    if "networks" in svc:
        p.append("sbom: joins a network")
    # Root filesystem.
    if svc.get("read_only") is not True:
        p.append("sbom: read_only is not true")
    if _tmpfs_targets(svc) != ["/tmp"]:
        p.append(f"sbom: tmpfs is {_tmpfs_targets(svc)}, want exactly ['/tmp']")
    # Privileges.
    if svc.get("cap_drop") != ["ALL"]:
        p.append("sbom: cap_drop is not [ALL]")
    if "cap_add" in svc:
        p.append("sbom: sets cap_add")
    opts = [str(o).replace("=", ":") for o in svc.get("security_opt") or []]
    if "no-new-privileges:true" not in opts:
        p.append("sbom: security_opt lacks no-new-privileges:true")
    loosened = [o for o in opts if "unconfined" in o or o == "label:disable"]
    if loosened:
        p.append(f"sbom: security_opt loosens confinement: {loosened}")
    if svc.get("privileged") in (True, "true"):
        p.append("sbom: privileged")
    if cs.port_entries(svc) or "expose" in svc:
        p.append("sbom: publishes or exposes a port")
    for key in ("devices", "volumes_from", "extra_hosts", "secrets", "configs", "env_file", "build",
                "profiles", "container_name", "links", "external_links", "device_cgroup_rules"):
        if svc.get(key):
            p.append(f"sbom: sets {key}")
    if svc.get("restart") not in (None, "no"):
        p.append("sbom: has a restart policy (it is a one-shot)")
    for key in ("pid", "ipc", "userns_mode", "uts", "cgroup", "network_mode"):
        if str(svc.get(key, "")).startswith(("host", "container:", "service:")):
            p.append(f"sbom: {key} shares a namespace ({svc.get(key)})")
    # Its own label: the project label comes from `compose -p <project>-sbom`.
    if data.get("name"):
        p.append("docker-compose.sbom.yml sets a top-level `name` (the run's `-p <project>-sbom` must win)")
    labels = svc.get("labels") or {}
    label_keys = list(labels) if isinstance(labels, dict) else [str(x).split("=", 1)[0] for x in labels]
    if [k for k in label_keys if str(k).startswith("com.docker.compose.")]:
        p.append("sbom: sets a com.docker.compose.* label")
    # Mounts: exactly /in (read-only) and /out (the only writable one).
    mounts = [m for m in _mounts(svc) if m["type"] != "tmpfs"]
    by_target = {m["target"]: m for m in mounts}
    if sorted(m["target"] for m in mounts) != ["/in", "/out"]:
        p.append(f"sbom: mounts {sorted(m['target'] for m in mounts)}, want exactly /in and /out")
    for m in mounts:
        if any(s in m["source"] or s in m["target"] for s in SOCKET_MARKERS):
            p.append(f"sbom: mounts the Docker socket ({m['source']})")
    tar_in = by_target.get("/in")
    if tar_in is not None:
        if tar_in["type"] != "bind" or not IN_SOURCE.match(tar_in["source"]):
            p.append(f"sbom: /in is not a bind of ${{KE_SBOM_IN:?...}} ({tar_in['type']} {tar_in['source']})")
        if not tar_in["read_only"]:
            p.append("sbom: the image tar mount /in is not read-only")
    work = by_target.get("/out")
    if work is not None:
        if work["type"] != "bind" or not OUT_SOURCE.match(work["source"]):
            p.append(f"sbom: /out is not a bind of ${{KE_SBOM_OUT:?...}} ({work['type']} {work['source']})")
    writable = sorted(m["target"] for m in mounts if not m["read_only"])
    if writable != ["/out"]:
        p.append(f"sbom: writable mounts are {writable}, want only /out (the SBOM output)")
    # Environment: literals, N1's keys and values, nothing that turns a lookup on.
    entries = _env_entries(svc)
    keys = [k for k, _ in entries]
    if len(keys) != len(set(keys)):
        p.append("sbom: an environment key is repeated")
    env: dict[str, str] = {}
    for key, value in entries:
        if value is None:
            p.append(f"sbom: `{key}` is passed through from the host")
            continue
        if "$" in value:
            p.append(f"sbom: `{key}` interpolates a host value")
        env[key] = value
    for key in keys:
        if key.upper().startswith("DOCKER_"):
            p.append(f"sbom: sets {key} (no DOCKER_HOST, no Docker client settings)")
    for key, want in REQUIRED_ENV.items():
        got = env.get(key)
        got_cmp = got.lower() if (got is not None and want in ("true", "false")) else got
        if got_cmp != want:
            p.append(f"sbom: {key} is {got!r}, want {want!r} (N1 Environment row)")
    for key, value in env.items():
        if key in REQUIRED_ENV or key.upper().startswith("DOCKER_"):
            continue
        if key in FALLBACK_ENV:
            if not (value == "/tmp" or value.startswith("/tmp/")) or "/../" in f"{value}/":
                p.append(f"sbom: {key}={value!r} is not at or under /tmp (N1 fallback; security I-2: "
                         "never under the host-writable /out)")
            continue
        if key.upper().startswith("SYFT_"):
            if value.lower() != "false":
                p.append(f"sbom: {key}={value!r}; a SYFT_* key beyond N1's may only switch a feature off (false)")
            continue
        p.append(f"sbom: sets {key}, which N1's Environment row does not name")
    return p


def standalone_problems(paths: list[Path]) -> list[str]:
    """N1: the generator lives only in its own file; no other compose file,
    and no stack COMPOSE_FILE, names it."""
    p = []
    for path in paths:
        if path.name == cs.SBOM_COMPOSE_NAME:
            continue
        text = path.read_text(encoding="utf-8")
        if "sbom" in cs.services(path):
            p.append(f"{path.name} defines an `sbom` service")
        for word in ("anchore/syft", cs.SBOM_COMPOSE_NAME, "KE_SBOM_", "SYFT_"):
            if word in text:
                p.append(f"{path.name} names {word}")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    if cs.SBOM_COMPOSE_NAME in env_example:
        p.append(".env.example names docker-compose.sbom.yml (never in the stack's COMPOSE_FILE)")
    return p


def _strip_messages(text: str) -> str:
    """bundle.sh without comments and without the text of die/echo/printf
    messages (they may say "pull it first" or "never pulls")."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        line = re.sub(r"""\b(?:die|echo|printf)\s+(["']).*$""", "", line)
        out.append(line)
    return "\n".join(out)


def bundle_static_problems(text: str) -> list[str]:
    """PSC-20 bullet 4, statically: bundle.sh reads the generator through its
    compose file and never pulls."""
    p = []
    body = _strip_messages(text)
    if cs.SBOM_COMPOSE_NAME not in body:
        p.append("bundle.sh does not read docker-compose.sbom.yml (N1 presence check)")
    for m in re.finditer(r"(?<![-\w])pull\b", body):
        line = body[:m.start()].count("\n") + 1
        p.append(f"bundle.sh line {line} (comments and messages stripped) has a pull: "
                 f"{body.splitlines()[line - 1].strip()!r}")
    for m in re.finditer(r"--pull(?:=|\s+)(\S+)", body):
        if m.group(1).strip("'\"") != "never":
            p.append(f"bundle.sh passes --pull {m.group(1)}")
    if not re.search(r"\bimage\s+inspect\b", body):
        p.append("bundle.sh has no `docker image inspect` (N1 presence check)")
    return p


def _repo_files() -> dict[str, str]:
    """Tracked and new unignored files' text (as test_engine_hardcoded)."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, check=True)
    out: dict[str, str] = {}
    for rel in sorted({p for p in result.stdout.decode("utf-8").split("\0") if p}):
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            out[rel] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary: cannot hold a written pin
    return out


# --------------------------------------------------------------------------
# PSC-20 bullets 1-3: docker-compose.sbom.yml (static)
# --------------------------------------------------------------------------

class SbomComposeTest(unittest.TestCase):
    """N1 row by row and the one-place pin, as ScanComposeTest does for grype."""

    def _data(self) -> dict[str, Any]:
        if not SBOM_COMPOSE.is_file():
            self.fail(COMPOSE_MISSING)
        return cs.load(SBOM_COMPOSE)

    def test_sbom_generator_is_pinned(self):
        data = self._data()
        ref = generator_ref(data)
        with self.subTest(part="anchore/syft:vX.Y.Z@sha256:<64 hex> (index digest)", image=ref):
            self.assertEqual(pin_problems(data), [])
        m = GENERATOR_REF.match(ref)
        with self.subTest(part="one committed place: docker-compose.sbom.yml, once"):
            self.assertEqual(pin_place_problems(_repo_files(), m.group(2) if m else None), [])
        with self.subTest(part="provenance recorded before the pin (PSC-1 form, N2)"):
            text = PROVENANCE.read_text(encoding="utf-8") if PROVENANCE.is_file() else None
            self.assertEqual(provenance_problems(ref, text), [])

    def test_sbom_generator_runs_without_network_or_privileges(self):
        data = self._data()
        with self.subTest(part="sbom: N1 hardening, mounts and environment"):
            self.assertEqual(hardening_problems(data), [])
        with self.subTest(part="standalone: no other compose file or the stack's COMPOSE_FILE names it"):
            self.assertEqual(standalone_problems(cs.compose_files()), [])


# --------------------------------------------------------------------------
# PSC-20 bullets 4 and 5: bundle.sh against the fake docker
# --------------------------------------------------------------------------

_SBOM_NAMES = re.compile(r"(?i)syft|docker-compose\.sbom")
_SBOM_CONTENT = re.compile(r"(?i)anchore/syft|docker-compose\.sbom")


class SbomBundleTest(_BundleBase, unittest.TestCase):
    """bundle.sh (fake docker, the BundleScriptTest harness, which holds the
    generator on the fake daemon by default) refuses without the generator
    and never ships it."""

    def _no_pull(self, calls: list[list[str]]) -> None:
        pulls = [c for c in calls if c[:1] == ["pull"] or c[:2] == ["image", "pull"]
                 or (c[:1] == ["compose"] and "pull" in c)
                 or any(a.startswith("--pull") and a not in ("--pull=never",) and
                        not (a == "--pull" and i + 1 < len(c) and c[i + 1] == "never")
                        for i, a in enumerate(c))]
        self.assertEqual(pulls, [], "bundle.sh pulled (PSC-20: it never pulls the generator)")

    def _reads_env_example(self, calls: list[list[str]]) -> None:
        """N1 amendment, U2: every compose call that names docker-compose.sbom.yml
        passes `--env-file .env.example`, so the repo-root `.env` (it holds the
        model keys) is never loaded for this file. At least one such call (the read)."""
        def files(c: list[str]) -> list[str]:
            got = [b for a, b in zip(c, c[1:]) if a in ("-f", "--file")]
            got += [a.split("=", 1)[1] for a in c if a.startswith(("-f=", "--file="))]
            return [Path(f).name for f in got]

        def env_files(c: list[str]) -> list[str]:
            got = [b for a, b in zip(c, c[1:]) if a == "--env-file"]
            got += [a.split("=", 1)[1] for a in c if a.startswith("--env-file=")]
            return got

        reads = [c for c in calls if c[:1] == ["compose"] and cs.SBOM_COMPOSE_NAME in files(c)]
        self.assertTrue(reads, f"bundle.sh never ran `docker compose -f {cs.SBOM_COMPOSE_NAME} config` (N1)")
        for c in reads:
            self.assertEqual(env_files(c), [".env.example"],
                             f"a compose call on {cs.SBOM_COMPOSE_NAME} must pass exactly "
                             f"`--env-file .env.example` (N1 amendment, U2): {c}")

    def _refused(self, result: subprocess.CompletedProcess, calls: list[list[str]], out: Path,
                 ref: str) -> None:
        self._assert_no_bundle(result, calls, out, ref)
        self.assertFalse(out.exists() and any(out.iterdir()),
                         f"--out was written before the refusal: {sorted(p.name for p in out.iterdir())}"
                         if out.exists() else "")
        self.assertFalse(Path(str(out) + ".manifest.sha256").exists(), "a release record was written")
        self.assertEqual([c for c in calls if c[:1] == ["tag"] or c[:2] == ["image", "tag"]], [],
                         "bundle.sh tagged an image before the refusal")
        self._no_pull(calls)
        runs = [c for c in calls if ("run" in c and (cs.SBOM_COMPOSE_NAME in c or ref in c))]
        self.assertEqual(runs, [], "bundle.sh ran the generator although it is absent")

    def test_bundle_refuses_when_sbom_generator_absent(self):
        with self.subTest(part="static: bundle.sh reads docker-compose.sbom.yml, inspects, never pulls"):
            self.assertEqual(bundle_static_problems(BUNDLE_SH.read_text(encoding="utf-8")), [])
        ref = self.sbom_ref
        with self.subTest(case="generator absent, --out does not exist"):
            images = self._images_table(self.stack)
            del images[ref]
            result, calls, out = self._bundle(images=images)
            self._refused(result, calls, out, ref)
            self.assertIn(REFUSAL.format(ref=ref), result.stderr, "N1's refusal message, exactly")
            self._reads_env_example(calls)
            inspected = [c for c in calls if (c[:2] == ["image", "inspect"] or c[:1] == ["inspect"]) and ref in c]
            self.assertTrue(inspected, f"bundle.sh never ran `docker image inspect {ref}` (N1)")
        with self.subTest(case="generator absent, --out exists and is empty"):
            out = self.tmp / "empty-out" / "bundle-amd64"
            out.mkdir(parents=True)
            images = self._images_table(self.stack)
            del images[ref]
            result, calls, out = self._bundle(out, images=images)
            self._refused(result, calls, out, ref)
            self.assertEqual(list(out.iterdir()), [], "--out is untouched")
            self.assertIn(REFUSAL.format(ref=ref), result.stderr, "N1's refusal message, exactly")
        with self.subTest(case="the reference is the one docker-compose.sbom.yml gives"):
            other = "anchore/syft:v9.9.9@sha256:" + hashlib.sha256(b"another syft").hexdigest()
            result, calls, out = self._bundle(
                FAKE_COMPOSE_FILE_IMAGES=json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": other}}))
            self._refused(result, calls, out, other)
            self.assertIn(REFUSAL.format(ref=other), result.stderr,
                          "the message names the reference compose gives, twice (N1)")
        with self.subTest(case="a tag-only reference is refused even when present"):
            tag_only = "anchore/syft:latest"
            images = self._images_table(self.stack)
            images[tag_only] = images[ref]
            result, calls, out = self._bundle(
                images=images, FAKE_COMPOSE_FILE_IMAGES=json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": tag_only}}))
            self._refused(result, calls, out, tag_only)
        with self.subTest(case="present, with a second service in the file: the bundle is written"):
            files = {cs.SBOM_COMPOSE_NAME: {"sbom": ref, "sources-fetch": "ke-gates:local"}}
            images = self._images_table(self.stack)
            images["ke-gates:local"] = images[ref]
            _, calls, _, _ = self._ok(images=images, FAKE_COMPOSE_FILE_IMAGES=json.dumps(files))
            self._no_pull(calls)
            self._reads_env_example(calls)

    def test_bundle_has_no_sbom_generator(self):
        self.assertTrue(SBOM_COMPOSE.is_file(), "precondition: " + COMPOSE_MISSING
                        + "; the bundle could pick it up from the checkout")
        tracked = set(self._git("ls-files").split())
        with self.subTest(part="harness: the build tree tracks docker-compose.sbom.yml"):
            self.assertIn(cs.SBOM_COMPOSE_NAME, tracked)
        ref = self.sbom_ref
        digest = ref.rsplit("@sha256:", 1)[-1]
        _, calls, out, data = self._ok()
        files = sorted(p for p in out.rglob("*") if p.is_file())
        with self.subTest(part="no bundled path names syft or the sbom compose file"):
            hits = [_rel(p, out) for p in files if _SBOM_NAMES.search(_rel(p, out))]
            self.assertEqual(hits, [], "the bundle ships a generator file")
        with self.subTest(part="no bundled file's content names the generator, its file or digest"):
            hits = []
            for p in files:
                text = p.read_bytes().decode("utf-8", errors="replace")
                if _SBOM_CONTENT.search(text) or digest in text:
                    hits.append(_rel(p, out))
            self.assertEqual(hits, [], "a bundled file names anchore/syft, docker-compose.sbom.yml or the digest")
        with self.subTest(part="no manifest entry is the generator image (PSC-8 form)"):
            for e in data.get("images", []):
                self.assertNotRegex(json.dumps(e), r"(?i)syft|anchore", "bundle.json lists the generator")
            touched = [c for c in calls if (c[:1] in (["save"], ["tag"], ["pull"], ["load"])
                                            or c[:2] in (["image", "save"], ["image", "tag"], ["image", "pull"]))
                       and any(re.search(r"(?i)syft|anchore", a) for a in c)]
            self.assertEqual(touched, [], "bundle.sh tagged, saved, loaded or pulled the generator image")


if __name__ == "__main__":
    unittest.main()
