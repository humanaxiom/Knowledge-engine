"""platform-sbom U8a: the source fetch client `scripts/sources_fetch.py` and
its helpers (PSC-15, PSC-23 "U8 precision" U8-2..U8-6 and U8-13; design-notes
"N4 amendment, U8" items 1, 2, 4, 5, 6, 11 and 12; orchestrator rulings Q75
(A75) and Q76 (A76); Q61: no retry).

No network: `scripts/sources_fetch.py` is loaded by path (as its container
runs it) and loads `scripts/sources_resolve.py` as `R` and
`scripts/sbom_check.py` as `S` from its own directory. The one network hook
is `F.R.OPENER(url, timeout)` (U7b interface pin 1), replaced here by a fake
that serves the synthetic lock's bytes; `socket.create_connection` is also
patched to fail, so a missed hook can never reach a real host.

Interface pinned (tester, U8a RED, 2026-10-28; design item 1 and 2 names):
- `sources_fetch.py`: `R`, `S`, `main(argv) -> int` (0 complete, 1 failure,
  2 bad argument), `CLOCK` (time.monotonic, read for the run deadline),
  `RUN_DEADLINE = {"sample": 300, "full": 10800}`, `DISK_FREE(out)` (the
  free bytes of `--out`; the tests' fake returns an int that also has
  `.free`, so `DISK_FREE(out)` and `DISK_FREE(out).free` both read it).
- `sources_resolve.py`: `download(url, allow, fh, limit, algs, hops) ->
  (digests, size)` (no `retries` parameter, never `_attempts`);
  `dsc_listing(fields, dsc, src, ver) -> [(name, size, sha256)]`.
- `sbom_check.py`: `lock_entry_problems(text, policy, today=None)`;
  `fetch_plan(lock, arch, set) -> [(key, file)]` (called positionally).
Lines: the `ok`, `held` and last `fetched` lines on stdout (the record the
caller tees); a `FAIL` line is looked for in stdout and stderr together. A
`stage fetch` line is `<host>: <file name>: <why>`; where `<why>` itself
starts with that host or file name (the resolver's texts, item 4's check
texts) the tests accept the repeat or its omission (the tester's reading).

Rework round 1 pins (tester, 2026-10-28; orchestrator rulings on security
M-1, M-2, L-1..L-5 and review B-1, N-2..N-9, u8/u8a-security.md and
u8/u8a-review.md):
- an empty plan (no entry for the arch, or no component at all) is
  `stage lock: the lock lists no entry for <arch>` (zero requests);
- a `fetch.json` already in `--out` is `stage lock: --out already holds
  fetch.json` (zero requests; that file untouched);
- one sha256 carries one size and, per upstream alg, one upstream value
  across all entries and arches (`lock_entry_problems`, so `lock_problems`
  too): `lock: <key>: <name>: sha256 <sha> is size <n> here but <m> in
  <key0>` and `lock: <key>: <name>: sha256 <sha> has <alg> <v> here but
  <v0> in <key0>`, where `<key0>` is the first entry in lock order holding
  that sha256 and `<key>` a later one that disagrees with it;
- (rework round 2, security L-6 / review R1-N2) one sha256 carries exactly
  one upstream alg across the whole lock: `lock: <key>: <name>: sha256
  <sha> has upstream alg <alg> here but <alg0> in <key0>`;
- a `.part` or `.fetch.json.part` this run did not create is never written
  or removed: `<host>: <name>: write failed: FileExistsError` and
  `fetch.json: write failed: FileExistsError`;
- a refused Location is quoted without its query by the resolver itself:
  `redirect to <url before ?>?<query omitted> refused: not printable ASCII`;
- `dsc_listing`: a present Checksums-Sha1 (an empty one included) lists the
  same (name, size) rows as Checksums-Sha256, else `<dsc>: Checksums-Sha1
  and Checksums-Sha256 list different files`;
- `fetch_plan` raises ValueError on a set other than sample or full.

Synthetic locks are built here in canonical form (one valid entry per kind,
real bytes, so every sha256, size and upstream digest is true); the
committed lock is read only by the `lock_entry_problems` row (design item
12 row 9). Never docs/evidence.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import inspect
import io
import itertools
import json
import os
import re
import shutil
import ssl
import stat
import sys
import tempfile
import time
import unittest
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Iterable, Iterator
from unittest import mock
from urllib.parse import quote

from tests.engine_support import ROOT
from tests.test_sbom_bundle import load_sbom_check
from tests.test_sources_lock import FROM_NEO4J, canon, policy
from tests.test_sources_resolve import load_resolver

FETCH = ROOT / "scripts" / "sources_fetch.py"
RESOLVER = ROOT / "scripts" / "sources_resolve.py"
SBOM_CHECK = ROOT / "scripts" / "sbom_check.py"
COMMITTED_LOCK = ROOT / "docker" / "sources.lock.json"
ARCH = "amd64"
NEO_KEY = "neo4j:neo4j@5.26.32"
NEO_URL = "https://github.com/neo4j/neo4j/archive/refs/tags/5.26.32.tar.gz"
NEO_HOP = "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"
TEM_KEY = "temurin:jdk-21.0.12.1+1"
TEM_ASSET = "OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz"
TEM_URL = f"https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/{TEM_ASSET}"
SECRET = "SECRETSIGNATURE"
TEM_HOP = ("https://release-assets.githubusercontent.com/github-production-release-asset/602574963/0a1b2c3d"
           f"?sp=r&sv=2018-11-09&sig={SECRET}")
JAXB_KEY = "maven:javax.xml.bind:jaxb-api@2.2.12"
JAXB_JAR = "jaxb-api-2.2.12-sources.jar"
JAXB_URL = f"https://repo1.maven.org/maven2/javax/xml/bind/jaxb-api/2.2.12/{JAXB_JAR}"
MAVEN = "repo1.maven.org"
DEB_KEY = "deb:bash@5.2.15-2"
PGDG_KEY = "pgdg:postgresql-common@293.pgdg12+1"
APK_KEY = "apk:readline@8.2.13-r1"
PYPI_KEY = "pypi:psycopg-c@3.3.6"
STALE = "but no image needs it"
HEX64 = re.compile(r"[0-9a-f]{64}")


# --------------------------------------------------------------------------
# Synthetic locks with real bytes
# --------------------------------------------------------------------------

def h(alg: str, data: bytes) -> str:
    return hashlib.new(alg, data).hexdigest()


def blob(tag: str, size: int) -> bytes:
    unit = (tag + "\n").encode()
    return (unit * (size // len(unit) + 1))[:size]


def dsc_text(src: str, ver: str, rows: list[tuple[str, int, str]], extra: str = "") -> str:
    """A `.dsc` listing `rows` (name, size, sha256) in Checksums-Sha256 and
    Files (the Files hash is any 32 hex; parse_dsc never checks it)."""
    lines = ["Format: 3.0 (quilt)", f"Source: {src}", f"Binary: {src}", "Architecture: any", f"Version: {ver}",
             "Checksums-Sha256:"]
    lines += [f" {sha} {size} {name}" for name, size, sha in rows]
    lines += ["Files:"]
    lines += [f" {h('sha256', name.encode())[:32]} {size} {name}" for name, size, _ in rows]
    return "\n".join(lines) + "\n" + extra


def apkbuild_text(origin: str, pkgver: str, pkgrel: str, sums: list[tuple[str, str]], pad: int = 0) -> str:
    body = "".join(f"{sha}  {name}\n" for name, sha in sums)
    return (f"# Contributor: synthetic\n" + "# padding line\n" * pad + f"pkgname={origin}\npkgver={pkgver}\n"
            f"pkgrel={pkgrel}\npkgdesc=\"synthetic\"\nsha512sums=\"\n{body}\"\n")


def key_parts(key: str) -> tuple[str, str]:
    name, _, ver = key.split(":", 1)[1].rpartition("@")
    return name, ver


class LockBuilder:
    """Entries whose every hash and size is true of `bodies[url]`; `routes`
    adds the redirects (neo4j to codeload, temurin to a signed asset URL)."""

    def __init__(self) -> None:
        self.components: dict[str, Any] = {}
        self.bodies: dict[str, bytes] = {}
        self.redirects: dict[str, str] = {}

    def _file(self, name: str, url: str, data: bytes, alg: str, frm: str) -> dict[str, Any]:
        self.bodies[url] = data
        return {"name": name, "url": url, "sha256": h("sha256", data), "size": len(data),
                "upstream": {"alg": alg, "value": h(alg, data), "from": frm}}

    def _add(self, key: str, files: list[dict[str, Any]], arches: Iterable[str], **extra: Any) -> None:
        kind = key.split(":", 1)[0]
        entry = {"kind": kind, "arches": sorted(arches), "origin": "manual" if kind == "neo4j" else "generated",
                 "files": files}
        entry.update(extra)
        self.components[key] = entry

    def deb(self, key: str, others: list[tuple[str, bytes]], *, arches: Iterable[str] = (ARCH,),
            listed: list[tuple[str, int, str]] | None = None, extra: str = "") -> None:
        src, ver = key_parts(key)
        dsc = f"{src}_{ver}.dsc"
        rows = listed if listed is not None else [(n, len(d), h("sha256", d)) for n, d in others]
        data = dsc_text(src, ver, rows, extra).encode()
        files = [self._file(dsc, f"https://snapshot.debian.org/file/{h('sha1', data)}", data, "sha1",
                            "snapshot.debian.org mr/package fileinfo")]
        files += [self._file(n, f"https://snapshot.debian.org/file/{h('sha1', d)}", d, "sha256",
                             f"{dsc} Checksums-Sha256") for n, d in others]
        self._add(key, files, arches)

    def pgdg(self, key: str, others: list[tuple[str, bytes]], *, arches: Iterable[str] = (ARCH,),
             listed: list[tuple[str, int, str]] | None = None) -> None:
        src, ver = key_parts(key)
        dsc = f"{src}_{ver}.dsc"
        pool = (f"https://apt-archive.postgresql.org/pub/repos/apt/pool/main/"
                f"{src[:4] if src.startswith('lib') else src[0]}/{src}")
        rows = listed if listed is not None else [(n, len(d), h("sha256", d)) for n, d in others]
        data = dsc_text(src, ver, rows).encode()
        files = [self._file(dsc, f"{pool}/{dsc}", data, "sha256",
                            "apt-archive.postgresql.org bookworm-pgdg-archive Sources")]
        files += [self._file(n, f"{pool}/{n}", d, "sha256", f"{dsc} Checksums-Sha256") for n, d in others]
        self._add(key, files, arches, suite="bookworm-pgdg-archive")

    def apk(self, key: str, *, branch: str = "v3.23", patches: Iterable[tuple[str, bytes]] = (),
            plain: Iterable[tuple[str, bytes]] = (), distfiles: Iterable[tuple[str, bytes]] = (),
            sums: list[tuple[str, str]] | None = None, pad: int = 0, arches: Iterable[str] = (ARCH,)) -> str:
        origin, ver = key_parts(key)
        pkgver, pkgrel = ver.rsplit("-r", 1)
        commit = h("sha1", key.encode())
        rows = sums if sums is not None else [(n, h("sha512", d)) for n, d in list(patches) + list(distfiles)]
        apkbuild = apkbuild_text(origin, pkgver, pkgrel, rows, pad).encode()

        def api(rel: str) -> str:
            return ("https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/"
                    + quote(f"main/{origin}/{rel}", safe="") + f"/raw?ref={commit}")
        gl_from = f"gitlab files API content_sha256 at {commit}"
        sums_from = f"APKBUILD sha512sums at {commit}"
        files = [self._file("APKBUILD", api("APKBUILD"), apkbuild, "sha256", gl_from)]
        files += [self._file(n, api(n), d, "sha512", sums_from) for n, d in patches]
        files += [self._file(n, api(n), d, "sha256", gl_from) for n, d in plain]
        files += [self._file(n, f"https://distfiles.alpinelinux.org/distfiles/{branch}/{n}", d, "sha512", sums_from)
                  for n, d in distfiles]
        self._add(key, files, arches, commit=commit, branch=branch, repo="main")
        return commit

    def neo4j(self, data: bytes) -> None:
        self._add(NEO_KEY, [self._file("5.26.32.tar.gz", NEO_URL, data, "sha256", FROM_NEO4J)], (ARCH,))
        self.redirects[NEO_URL] = NEO_HOP

    def temurin(self, data: bytes) -> None:
        self._add(TEM_KEY, [self._file(TEM_ASSET, TEM_URL, data, "sha256", f"{TEM_ASSET}.sha256.txt")], (ARCH,))
        self.redirects[TEM_URL] = TEM_HOP

    def maven(self, data: bytes) -> None:
        self._add(JAXB_KEY, [self._file(JAXB_JAR, JAXB_URL, data, "sha1", f"{JAXB_JAR}.sha1")], (ARCH,))

    def pypi(self, key: str, dist: str, data: bytes) -> None:
        _, ver = key_parts(key)
        name = f"{dist}-{ver}.tar.gz"
        x = h("sha256", key.encode())
        url = f"https://files.pythonhosted.org/packages/{x[:2]}/{x[2:4]}/{x[4:]}/{name}"
        self._add(key, [self._file(name, url, data, "sha256", "uv.lock")], (ARCH,))

    # --- views -------------------------------------------------------------
    def lock(self) -> dict[str, Any]:
        return json.loads(self.text())

    def text(self) -> str:
        return canon({"format": 1, "components": self.components})

    def routes(self) -> dict[str, Any]:
        """url -> body or redirect, served by Net: a redirected lock URL
        answers 302 and its hop serves the bytes."""
        out: dict[str, Any] = {}
        for url, data in self.bodies.items():
            hop = self.redirects.get(url)
            if hop:
                out[url] = (302, {"Location": hop}, b"")
                out[hop] = data
            else:
                out[url] = data
        return out

    def chain(self, url: str) -> list[str]:
        return [url] + ([self.redirects[url]] if url in self.redirects else [])


def with_dsc_bytes(b: LockBuilder, key: str, data: bytes) -> LockBuilder:
    """`b` with the deb entry's `.dsc` replaced by `data`; its url (snapshot
    /file/<sha1>), sha256, size and upstream sha1 stay true of the bytes."""
    f = b.components[key]["files"][0]
    assert f["name"].endswith(".dsc") and f["upstream"]["alg"] == "sha1"
    del b.bodies[f["url"]]
    f["url"] = f"https://snapshot.debian.org/file/{h('sha1', data)}"
    f.update(sha256=h("sha256", data), size=len(data))
    f["upstream"]["value"] = h("sha1", data)
    b.bodies[f["url"]] = data
    return b


def shared_sha256_conflict(field: str, b_arches: Iterable[str] = (ARCH,)) -> tuple[LockBuilder, str]:
    """Security probes Q2/Q2b: two apk entries hold one distfile (one
    sha256); the later entry's lock `size` or upstream sha512 is false of the
    bytes (its APKBUILD agrees with its lock). Returns the lock and the
    pinned lock problem for the later entry."""
    data = blob("readline tarball", 300)
    a0, a1, dist = "apk:readline@8.2.13-r0", "apk:readline@8.2.13-r1", "readline-8.2.13.tar.gz"
    w = LockBuilder()
    w.apk(a0, branch="v3.22", distfiles=[(dist, data)])
    sums = [(dist, "e" * 128)] if field == "sha512" else None
    w.apk(a1, distfiles=[(dist, data)], sums=sums, pad=3, arches=b_arches)
    f1 = next(f for f in w.components[a1]["files"] if f["name"] == dist)
    sha = h("sha256", data)
    if field == "sha512":
        f1["upstream"]["value"] = "e" * 128
        want = f"lock: {a1}: {dist}: sha256 {sha} has sha512 {'e' * 128} here but {h('sha512', data)} in {a0}"
    else:
        f1["size"] = 9999
        want = f"lock: {a1}: {dist}: sha256 {sha} is size 9999 here but {len(data)} in {a0}"
    return w, want


def cross_alg_conflict() -> tuple[LockBuilder, str]:
    """Security re-audit probe R1 as corrected (probe4.py, L-6): a valid
    `apk:aaa` (one sha512 distfile) also holds bytes X as a plain GitLab file
    (upstream alg sha256); `apk:bbb` lists X in its sha512sums with a wrong
    sha512 its APKBUILD agrees with. Returns the lock and the pinned lock
    problem (one sha256, one upstream alg)."""
    x = blob("shared patch", 90)
    w = LockBuilder()
    w.apk("apk:aaa@1.0-r0", plain=[("shared.patch", x)], distfiles=[("aaa-1.0.tar.gz", blob("aaa tarball", 120))])
    w.apk("apk:bbb@1.0-r0", patches=[("shared.patch", x)], sums=[("shared.patch", "e" * 128)])
    for f in w.components["apk:bbb@1.0-r0"]["files"]:
        if f["name"] == "shared.patch":
            f["upstream"]["value"] = "e" * 128
    return w, (f"lock: apk:bbb@1.0-r0: shared.patch: sha256 {h('sha256', x)} has upstream alg sha512 here "
               f"but sha256 in apk:aaa@1.0-r0")


def one_per_kind() -> LockBuilder:
    """Seven amd64 entries, one per kind (the sample is all of them)."""
    b = LockBuilder()
    b.apk(APK_KEY, patches=[("fix-build.patch", blob("readline patch", 90))],
          plain=[("readline.trigger", blob("readline trigger", 40))],
          distfiles=[("readline-8.2.13.tar.gz", blob("readline tarball", 300))])
    b.deb(DEB_KEY, [("bash_5.2.15.orig.tar.gz", blob("bash orig", 400)),
                    ("bash_5.2.15-2.debian.tar.xz", blob("bash debian 2", 120))])
    b.maven(blob("jaxb sources", 150))
    b.neo4j(blob("neo4j tag tarball", 500))
    b.pgdg(PGDG_KEY, [("postgresql-common_293.pgdg12+1.tar.xz", blob("postgresql-common", 200))])
    b.pypi(PYPI_KEY, "psycopg_c", blob("psycopg-c sdist", 250))
    b.temurin(blob("temurin sources", 350))
    return b


def wide() -> LockBuilder:
    """one_per_kind plus larger entries (never the sample), two shared
    sha256 values (a deb orig at one URL, an apk distfile at two URLs) and
    an arm64-only entry."""
    b = one_per_kind()
    b.pypi("pypi:psycopg@3.3.6", "psycopg", blob("psycopg sdist", 900))
    b.deb("deb:bash@5.2.15-2+deb12u1", [("bash_5.2.15.orig.tar.gz", blob("bash orig", 400)),
                                        ("bash_5.2.15-2+deb12u1.debian.tar.xz", blob("bash debian u1", 2000))])
    b.apk("apk:readline@8.2.13-r0", branch="v3.22", distfiles=[("readline-8.2.13.tar.gz", blob("readline tarball", 300))],
          pad=200)
    b.deb("deb:dash@0.5.12-2", [("dash_0.5.12.orig.tar.gz", blob("dash orig", 100)),
                                ("dash_0.5.12-2.debian.tar.xz", blob("dash debian", 50))], arches=("arm64",))
    return b


def only(b: LockBuilder, *keys: str) -> LockBuilder:
    """A copy of `b` holding just `keys` (bodies and redirects kept)."""
    c = LockBuilder()
    c.components = {k: json.loads(json.dumps(b.components[k])) for k in keys}
    c.bodies = dict(b.bodies)
    c.redirects = dict(b.redirects)
    return c


def plan_of(b: LockBuilder, arch: str, which: str) -> list[tuple[str, dict[str, Any]]]:
    lock = b.lock()
    if which == "sample":
        keys = load_sbom_check().sample_keys(lock, arch)
    else:
        keys = sorted(k for k, e in lock["components"].items() if arch in e["arches"])
    return [(k, f) for k in keys for f in lock["components"][k]["files"]]


def dsc_cases(kind: str) -> dict[str, LockBuilder]:
    """Row 4's `.dsc` cases: a control and four differences."""
    key = DEB_KEY if kind == "deb" else PGDG_KEY
    src, ver = key_parts(key)
    if kind == "deb":
        files = [("bash_5.2.15.orig.tar.gz", blob("bash orig", 400)),
                 ("bash_5.2.15-2.debian.tar.xz", blob("bash debian 2", 120))]
    else:
        files = [("postgresql-common_293.pgdg12+1.tar.xz", blob("postgresql-common", 200)),
                 ("postgresql-common_293.pgdg12+1.extra.tar.xz", blob("postgresql-common extra", 60))]
    rows = [(n, len(d), h("sha256", d)) for n, d in files]
    add = getattr(LockBuilder, kind)
    out: dict[str, LockBuilder] = {}
    for case, entry_files, listed in (
            ("control: equal", files, rows),
            ("an extra file in the lock entry", files + [(f"{src}-extra.diff.gz", blob("extra", 30))], rows),
            ("a file the lock entry lacks", files[:1], rows),
            ("a size difference", files, [(rows[0][0], rows[0][1] + 1, rows[0][2])] + rows[1:]),
            ("a sha256 difference", files, [(rows[0][0], rows[0][1], "a" * 64)] + rows[1:])):
        b = LockBuilder()
        add(b, key, entry_files, listed=listed)
        out[case] = b
    return out


def host_of(url: str) -> str:
    return url.split("://", 1)[1].split("/", 1)[0]


# --------------------------------------------------------------------------
# The fake network and the run
# --------------------------------------------------------------------------

class Net:
    """A fake OPENER: url -> bytes (200), (status, headers, body), a list of
    those (one per call, the last repeats), "timeout", or a callable making
    a response. Records each call and whether `fetch.json` existed then."""

    def __init__(self, routes: dict[str, Any], out: Path | None = None):
        self.routes = dict(routes)
        self.calls: list[str] = []
        self.record_seen: list[bool] = []
        self.out = out

    def __call__(self, url: str, timeout: float) -> Any:
        self.calls.append(url)
        if self.out is not None:
            self.record_seen.append((self.out / "fetch.json").exists())
        spec = self.routes.get(url)
        if isinstance(spec, list):
            spec = spec.pop(0) if len(spec) > 1 else spec[0]
        if callable(spec):
            return spec()
        if spec is None:
            return SimpleNamespace(status=404, headers={}, body=[b""])
        if spec == "timeout":
            raise TimeoutError("timed out")
        status, headers, body = (200, {}, spec) if isinstance(spec, bytes) else spec
        return SimpleNamespace(status=status, headers={k.lower(): v for k, v in headers.items()},
                               body=[body[i:i + 7] for i in range(0, len(body), 7)] or [b""])


class Recorder:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def __call__(self, *a: Any, **k: Any) -> None:
        self.calls.append(a)


class Free(int):
    """DISK_FREE's fake: an int that also answers `.free`."""

    @property
    def free(self) -> int:
        return int(self)


def body_then(chunks: list[bytes], exc: BaseException) -> Callable[[], Any]:
    def make() -> Any:
        def gen() -> Iterator[bytes]:
            yield from chunks
            raise exc
        return SimpleNamespace(status=200, headers={}, body=gen())
    return make


_SEQ = itertools.count()


def load_fetch() -> ModuleType:
    """A fresh load per test (module state and patches never leak)."""
    if not FETCH.is_file():
        raise AssertionError("scripts/sources_fetch.py is missing (platform-sbom U8a; design-notes N4 amendment U8, "
                             "items 1-6; tests/test_sources_fetch.py)")
    spec = importlib.util.spec_from_file_location(f"ke_sources_fetch_under_test_{next(_SEQ)}", FETCH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    for name in ("R", "S", "main", "CLOCK", "DISK_FREE", "RUN_DEADLINE"):
        if not hasattr(mod, name):
            raise AssertionError(f"scripts/sources_fetch.py has no {name} (U8a interface, tests/test_sources_fetch.py)")
    return mod


def rfn(name: str) -> Any:
    got = getattr(load_resolver(), name, None)
    if got is None:
        raise AssertionError(f"scripts/sources_resolve.py has no {name} (U8a interface, N4 amendment U8 item 1)")
    return got


def sfn(name: str) -> Any:
    got = getattr(load_sbom_check(), name, None)
    if got is None:
        raise AssertionError(f"scripts/sbom_check.py has no {name} (U8a interface, N4 amendment U8 item 1)")
    return got


@dataclass
class Run:
    rc: int
    out: str
    err: str
    net: Net
    sleeps: Recorder
    outdir: Path

    @property
    def text(self) -> str:
        return self.out + self.err

    @property
    def fail_lines(self) -> list[str]:
        return [ln for ln in self.text.splitlines() if ln.startswith("bundle_fetch: FAIL")]

    def listing(self) -> list[str]:
        return sorted(os.listdir(self.outdir))


def fetch_fail(host: str, name: str, tail: str) -> str:
    """The exact `stage fetch` line; the why's own leading host or file name
    may repeat (design item 2 composes `<host>: <file name>: <why>`)."""
    h_, n_ = re.escape(host), re.escape(name)
    return rf"bundle_fetch: FAIL \(stage fetch: {h_}: {n_}: (?:{h_}: |{n_}: )?{re.escape(tail)}; no retry\)"


class _FetchCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.F = load_fetch()
        self.tmp = Path(tempfile.mkdtemp(prefix="ke-u8a-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_fetch(self, text: str, routes: dict[str, Any], *, arch: str = ARCH, which: str = "sample",
                  pol: dict[str, Any] | None = None, argv: list[str] | None = None,
                  patches: Iterable[Callable[[ModuleType], Any]] = (),
                  pre: Callable[[Path], Any] | None = None) -> Run:
        lock_p = self.tmp / "sources.lock.json"
        lock_p.write_bytes(text.encode("utf-8"))
        pol_p = self.tmp / "source-policy.json"
        pol_p.write_text(json.dumps(pol if pol is not None else policy()), encoding="utf-8")
        out = self.tmp / "out"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir()
        if pre is not None:
            pre(out)
        net = Net(routes, out)
        sleeps = Recorder()
        args = argv if argv is not None else ["--lock", str(lock_p), "--policy", str(pol_p), "--out", str(out),
                                              "--arch", arch, "--set", which]
        o, e = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(self.F.R, "OPENER", net))
            st.enter_context(mock.patch.object(self.F.R, "SLEEP", sleeps))
            st.enter_context(mock.patch("time.sleep", sleeps))
            st.enter_context(mock.patch("socket.create_connection", side_effect=AssertionError("a real connection")))
            for p in patches:
                st.enter_context(p(self.F))
            st.enter_context(contextlib.redirect_stdout(o))
            st.enter_context(contextlib.redirect_stderr(e))
            old = os.umask(0o022)
            try:
                rc = self.F.main(args)
            finally:
                os.umask(old)
        return Run(rc, o.getvalue(), e.getvalue(), net, sleeps, out)

    # --- shared assertions -------------------------------------------------
    def assert_failed(self, run: Run, pattern: str) -> None:
        self.assertEqual(run.rc, 1, run.text)
        self.assertEqual(len(run.fail_lines), 1, run.text)
        self.assertRegex(run.fail_lines[0], "^" + pattern + "$")
        self.assertNotIn("Traceback", run.text)
        self.assertNotIn("bundle_fetch: fetched", run.out)

    def assert_no_partial(self, run: Run, absent: Iterable[str] = ()) -> None:
        """A76 and item 6: no record, no `.part`, nothing unverified; every
        file left is a 64-hex name whose bytes hash to it (the client's own
        files; the script's trap removes them, U8b)."""
        names = run.listing()
        self.assertNotIn("fetch.json", names)
        self.assertEqual([n for n in names if n.startswith(".")], [], names)
        for n in names:
            self.assertRegex(n, "^[0-9a-f]{64}$")
            self.assertEqual(h("sha256", (run.outdir / n).read_bytes()), n)
        for sha in absent:
            self.assertNotIn(sha, names, "a file that failed a check was placed in --out")


# --------------------------------------------------------------------------
# U8a rows: the client
# --------------------------------------------------------------------------

class SourceFetchModuleTest(_FetchCase):
    """Item 1: the module boundaries and hooks."""

    def test_source_fetch_loads_its_siblings_by_path(self):
        F = self.F
        self.assertEqual(Path(F.R.__file__).resolve(), RESOLVER.resolve())
        self.assertEqual(Path(F.S.__file__).resolve(), SBOM_CHECK.resolve())
        self.assertIs(F.R.OPENER, F.R._default_opener, "the one network hook stays sources_resolve.OPENER")
        self.assertIs(F.CLOCK, time.monotonic)
        self.assertEqual(F.RUN_DEADLINE, {"sample": 300, "full": 10800})

    def test_source_fetch_has_no_url_host_or_environment_literal(self):
        text = FETCH.read_text(encoding="utf-8")
        for literal in ("https://", "http://", "environ", "getenv"):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, text, "PS-1.2 / item 1: no URL, host or environment read in the client")
        for host in policy()["hosts"]:
            with self.subTest(host=host):
                self.assertNotIn(host, text, "hosts come from docker/source-policy.json only (U8-4)")


class SourceFetchChecksTest(_FetchCase):
    """Rows 1 and 7: size, sha256 and upstream digest before use; the cap."""

    def test_source_fetch_checks_before_use(self):
        b = only(one_per_kind(), JAXB_KEY)
        good = b.bodies[JAXB_URL]
        short = good[:-3] + b"Z"  # shorter and different: the size is checked first
        flipped = good[:-1] + bytes([good[-1] ^ 1])
        wrong = b.lock()
        wrong["components"][JAXB_KEY]["files"][0]["upstream"]["value"] = "0" * 40
        cases = {
            "size": (short, f"size mismatch: got {len(short)}, lock says {len(good)}", b.text()),
            "sha256": (flipped, f"sha256 mismatch: got {h('sha256', flipped)}, lock says {h('sha256', good)}", b.text()),
            "upstream sha1": (good, f"sha1 mismatch: got {h('sha1', good)}, {JAXB_JAR}.sha1 says {'0' * 40}",
                              canon(wrong)),
        }
        for case, (served, tail, text) in cases.items():
            with self.subTest(case=case):
                run = self.run_fetch(text, {JAXB_URL: served})
                self.assert_failed(run, fetch_fail(MAVEN, JAXB_JAR, tail))
                self.assertEqual(run.listing(), [], "--out holds nothing: no <sha256>, no .part, no fetch.json")
        with self.subTest(case="control: the true bytes"):
            run = self.run_fetch(b.text(), {JAXB_URL: good})
            self.assertEqual(run.rc, 0, run.text)
            self.assertEqual(run.listing(), sorted([h("sha256", good), "fetch.json"]))

    def test_source_fetch_checks_the_apk_sha512_before_use(self):
        b = only(one_per_kind(), APK_KEY)
        lock = b.lock()
        files = lock["components"][APK_KEY]["files"]
        dist = next(f for f in files if f["name"] == "readline-8.2.13.tar.gz")
        files.remove(dist)
        files.insert(0, dist)  # first in the entry, so nothing was placed before it
        real = h("sha512", b.bodies[dist["url"]])
        dist["upstream"]["value"] = "f" * 128
        run = self.run_fetch(canon(lock), b.routes())
        self.assert_failed(run, fetch_fail("distfiles.alpinelinux.org", "readline-8.2.13.tar.gz",
                                           f"sha512 mismatch: got {real}, "
                                           f"{dist['upstream']['from']} says {'f' * 128}"))
        self.assertEqual(run.listing(), [])

    def test_source_fetch_never_parses_a_dsc_that_failed_its_check(self):
        b = only(one_per_kind(), DEB_KEY)
        dsc = b.components[DEB_KEY]["files"][0]
        junk = blob("this line is not a field", dsc["size"])
        routes = b.routes()
        routes[dsc["url"]] = junk
        run = self.run_fetch(b.text(), routes)
        self.assert_failed(run, fetch_fail("snapshot.debian.org", dsc["name"],
                                           f"sha256 mismatch: got {h('sha256', junk)}, "
                                           f"lock says {dsc['sha256']}"))
        self.assertNotIn("not a field", run.text, "the bytes were parsed before their check")
        self.assertEqual(run.listing(), [])

    def test_source_fetch_stops_at_the_byte_cap(self):
        b = only(one_per_kind(), JAXB_KEY)
        good = b.bodies[JAXB_URL]
        pulled: list[int] = []

        def longer() -> Any:
            def gen() -> Iterator[bytes]:
                data = good + b"MORE BYTES PAST THE LOCK SIZE" * 20
                for i in range(0, len(data), 7):
                    pulled.append(i)
                    yield data[i:i + 7]
            return SimpleNamespace(status=200, headers={}, body=gen())
        run = self.run_fetch(b.text(), {JAXB_URL: longer})
        self.assertEqual(run.rc, 1, run.text)
        self.assertEqual(len(run.fail_lines), 1, run.text)
        self.assertTrue(run.fail_lines[0].startswith(f"bundle_fetch: FAIL (stage fetch: {MAVEN}: {JAXB_JAR}: "),
                        run.fail_lines[0])
        self.assertIn(f"more than {len(good)} bytes", run.fail_lines[0])
        self.assertTrue(run.fail_lines[0].endswith("; no retry)"), run.fail_lines[0])
        self.assertEqual(run.listing(), [])
        self.assertLessEqual(len(pulled), -(-len(good) // 7), "the body is read no further than the chunk that crosses the cap")


class SourceFetchHostsTest(_FetchCase):
    """Row 2: https only, to listed hosts; lock rules before any request."""

    def test_source_fetch_is_https_only_to_listed_hosts(self):
        b = only(one_per_kind(), JAXB_KEY)
        good = b.bodies[JAXB_URL]
        hops = {
            "a host not in hosts": ("https://maven.example.org/x.jar", "redirect to maven.example.org refused: not in hosts"),
            "http": ("http://repo1.maven.org/maven2/x.jar", "redirect to a non-https URL refused"),
            "a port": ("https://repo1.maven.org:8443/maven2/x.jar", "refused: a port"),
            "an encoded dot segment": ("https://repo1.maven.org/maven2/%2e%2e/x.jar", "refused: not a plain path"),
        }
        for case, (to, why) in hops.items():
            with self.subTest(hop=case):
                run = self.run_fetch(b.text(), {JAXB_URL: (302, {"Location": to}, b""), to: good})
                self.assertEqual(run.rc, 1, run.text)
                self.assertEqual(len(run.fail_lines), 1, run.text)
                line = run.fail_lines[0]
                self.assertTrue(line.startswith(f"bundle_fetch: FAIL (stage fetch: {MAVEN}: {JAXB_JAR}: "), line)
                self.assertIn(why, line)
                self.assertTrue(line.endswith("; no retry)"), line)
                self.assertEqual(run.net.calls, [JAXB_URL], "a refused hop is never requested")
                self.assertEqual(run.listing(), [])
        pypi = only(one_per_kind(), PYPI_KEY)
        pypi_url = pypi.components[PYPI_KEY]["files"][0]["url"]
        lock_cases: dict[str, tuple[str, dict[str, Any] | None, str]] = {}
        for case, url in (("a lock host not in hosts", JAXB_URL.replace(MAVEN, "maven.example.org")),
                          ("a non-https lock url", JAXB_URL.replace("https://", "http://"))):
            lk = b.lock()
            lk["components"][JAXB_KEY]["files"][0]["url"] = url
            why = ("url host maven.example.org is not in docker/source-policy.json hosts" if "example" in url
                   else "url scheme is not https")
            lock_cases[case] = (canon(lk), None, f"lock: {JAXB_KEY}: {why}")
        lk = pypi.lock()
        lk["components"][PYPI_KEY]["files"][0]["url"] = pypi_url + "?download=1"
        lock_cases["a non-apk lock url with a query"] = (canon(lk), None, f"lock: {PYPI_KEY}: url carries a query")
        narrow = policy()
        narrow["hosts"] = [x for x in narrow["hosts"] if x != MAVEN]
        lock_cases["a policy without the lock's host"] = (
            b.text(), narrow, f"lock: {JAXB_KEY}: url host {MAVEN} is not in docker/source-policy.json hosts")
        lock_cases["a lock not in canonical form"] = (json.dumps(b.lock()) + "\n", None,
                                                      "lock: not in canonical form: regenerate")
        for case, (text, pol, first) in lock_cases.items():
            with self.subTest(lock=case):
                run = self.run_fetch(text, {**b.routes(), **pypi.routes()}, pol=pol)
                self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage lock: {first}; no retry)"))
                self.assertEqual(run.net.calls, [], "a lock that fails its rules makes zero requests")
                self.assertEqual(run.listing(), [])

    def test_source_fetch_prints_the_first_20_lock_problems(self):
        """N-9: the first 20 problems on stderr, each through `_safe`."""
        b = wide()
        lk = b.lock()
        for e in lk["components"].values():
            for f in e["files"]:
                f["url"] = f["url"].replace("https://", "http://")
        lk["components"]["apk:aaa?sig=SECRET" + chr(1) + "x@1-r0"] = json.loads(json.dumps(lk["components"][APK_KEY]))
        text = canon(lk)
        problems = sfn("lock_entry_problems")(text, policy())
        self.assertGreater(len(problems), 20, "fixture: more than 20 problems")
        self.assertTrue(any("?sig=SECRET" in p for p in problems[:20]), "fixture: a problem quotes a query")
        run = self.run_fetch(text, b.routes())
        self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage lock: {self.F._safe(problems[0])}; no retry)"))
        got = [ln for ln in run.err.splitlines() if ln.startswith("bundle_fetch: lock problem: ")]
        self.assertEqual(got, [f"bundle_fetch: lock problem: {self.F._safe(p)}" for p in problems[:20]])
        self.assertNotIn("SECRET", run.text)
        self.assertEqual(run.net.calls, [])
        self.assertEqual(run.listing(), [])


class SourceFetchDroppedHostTest(_FetchCase):
    """U8c O-2 (PSC-23 U8-10; design-notes "N4 amendment, U8" ruling O-2):
    with the committed policy, a Temurin redirect to
    objects.githubusercontent.com (unused by the real fetches, dropped from
    `hosts`) is refused before it is requested; the real redirect target
    release-assets.githubusercontent.com is still followed. Tester, U8c RED,
    2026-10-29."""

    OLD_HOP = "https://objects.githubusercontent.com/github-production-release-asset/602574963/0a1b2c3d"

    def test_source_fetch_refuses_a_temurin_redirect_to_the_dropped_host(self):
        b = only(one_per_kind(), TEM_KEY)
        data = b.bodies[TEM_URL]
        run = self.run_fetch(b.text(), {TEM_URL: (302, {"Location": self.OLD_HOP}, b""), self.OLD_HOP: data})
        self.assert_failed(run, fetch_fail("github.com", TEM_ASSET,
                                           "redirect to objects.githubusercontent.com refused: not in hosts"))
        self.assertEqual(run.net.calls, [TEM_URL], "a refused hop is never requested")
        self.assertEqual(run.listing(), [])

    def test_source_fetch_follows_the_real_temurin_redirect_target(self):
        b = only(one_per_kind(), TEM_KEY)
        run = self.run_fetch(b.text(), b.routes())
        self.assertEqual(run.rc, 0, run.text)
        self.assertIn("hops=github.com,release-assets.githubusercontent.com", run.out)


class SourceFetchRetryTest(_FetchCase):
    """Row 3: Q61, one call, never a sleep."""

    def test_source_fetch_never_retries(self):
        b = only(one_per_kind(), JAXB_KEY)
        good = b.bodies[JAXB_URL]
        cases = {
            "a 503": ([(503, {}, b""), good], f"{MAVEN}: HTTP 503: {JAXB_URL}"),
            "a timeout": (["timeout", good], f"{MAVEN}: timeout after 60 s: {JAXB_URL}"),
            "a mid-body timeout": ([body_then([good[:7]], TimeoutError("timed out")), good],
                                   f"{MAVEN}: timeout after 60 s: {JAXB_URL}"),
        }
        for case, (seq, tail) in cases.items():
            with self.subTest(case=case):
                run = self.run_fetch(b.text(), {JAXB_URL: list(seq)},
                                     patches=[lambda F: mock.patch.object(F.R, "_ACTIVE_RETRIES", [3])])
                self.assert_failed(run, fetch_fail(MAVEN, JAXB_JAR, tail.split(": ", 1)[1]))
                self.assertEqual(run.net.calls, [JAXB_URL], "Q61: exactly one request, no retry")
                self.assertEqual(run.sleeps.calls, [], "never a wait")
                self.assertEqual(run.listing(), [])


class SourceFetchNameCheckTest(_FetchCase):
    """Row 4 (item 5): the `.dsc` (deb and pgdg) and APKBUILD name checks."""

    def test_source_fetch_dsc_names_match_the_lock_entry(self):
        for kind, host in (("deb", "snapshot.debian.org"), ("pgdg", "apt-archive.postgresql.org")):
            key = DEB_KEY if kind == "deb" else PGDG_KEY
            src, ver = key_parts(key)
            dsc = f"{src}_{ver}.dsc"
            for case, b in dsc_cases(kind).items():
                with self.subTest(kind=kind, case=case):
                    run = self.run_fetch(b.text(), b.routes())
                    if case.startswith("control"):
                        self.assertEqual(run.rc, 0, run.text)
                        self.assertIn("fetch.json", run.listing())
                        continue
                    self.assert_failed(run, fetch_fail(host, dsc, "Files/Checksums-Sha256 differ from the lock entry"))
                    self.assert_no_partial(run)
        with self.subTest(case="a parser failure keeps its own text (R1-N2)"):
            b = LockBuilder()
            b.deb(DEB_KEY, [("bash_5.2.15.orig.tar.gz", blob("bash orig", 400))], extra="this line is not a field\n")
            run = self.run_fetch(b.text(), b.routes())
            self.assertEqual(run.rc, 1, run.text)
            self.assertEqual(len(run.fail_lines), 1, run.text)
            self.assertRegex(run.fail_lines[0], r"^bundle_fetch: FAIL \(stage fetch: snapshot\.debian\.org: "
                                                r"bash_5\.2\.15-2\.dsc: .*line \d+ is not a field or continuation; no retry\)$")
            self.assert_no_partial(run)

    def test_source_fetch_apkbuild_names_match_the_lock_entry(self):
        patch_, dist = ("fix-build.patch", blob("readline patch", 90)), ("readline-8.2.13.tar.gz", blob("readline tarball", 300))
        real = [(patch_[0], h("sha512", patch_[1])), (dist[0], h("sha512", dist[1]))]
        for case, sums in (("control: equal; a GitLab file outside sha512sums is in neither set", real),
                           ("sha512sums names a file the lock entry lacks", real + [("gone.patch", h("sha512", b"gone"))]),
                           ("a sha512 lock file not in sha512sums", real[1:]),
                           ("a sha512 value difference", [(patch_[0], h("sha512", b"other"))] + real[1:])):
            with self.subTest(case=case):
                b = LockBuilder()
                commit = b.apk(APK_KEY, patches=[patch_], plain=[("readline.trigger", blob("readline trigger", 40))],
                               distfiles=[dist], sums=sums)
                run = self.run_fetch(b.text(), b.routes())
                if case.startswith("control"):
                    self.assertEqual(run.rc, 0, run.text)
                    self.assertIn("fetch.json", run.listing())
                    continue
                self.assert_failed(run, fetch_fail("gitlab.alpinelinux.org", "APKBUILD",
                                                   f"APKBUILD at {commit}: sha512sums names differ from the lock entry"))
                self.assert_no_partial(run)


class SourceFetchNoPartialTest(_FetchCase):
    """Row 5 and A76: a fault on the n-th file leaves no record."""

    def test_source_fetch_leaves_no_out_on_failure(self):
        b = one_per_kind()
        plan = plan_of(b, ARCH, "sample")
        for where, index in (("a middle file", len(plan) // 2), ("the last file", len(plan) - 1)):
            key, f = plan[index]
            with self.subTest(fault=where, key=key, name=f["name"]):
                routes = b.routes()
                routes[f["url"]] = (404, {}, b"")
                run = self.run_fetch(b.text(), routes)
                self.assert_failed(run, fetch_fail(host_of(f["url"]), f["name"], f"HTTP 404: {f['url']}"))
                self.assert_no_partial(run, absent=[f["sha256"]])
                self.assertEqual(run.net.calls[-1], f["url"], "no request after the fault")


class SourceFetchPlanTest(_FetchCase):
    """Row 6: the set is the plan; a shared sha256 is fetched once."""

    def _expected(self, b: LockBuilder, arch: str, which: str) -> tuple[list[str], list[str], list[str]]:
        calls, ok_lines, held_lines = [], [], []
        first: dict[str, tuple[str, str]] = {}
        for key, f in plan_of(b, arch, which):
            if f["sha256"] in first:
                k0, n0 = first[f["sha256"]]
                held_lines.append(f"bundle_fetch: held {key} {f['name']} sha256={f['sha256']} size={f['size']} "
                                  f"(fetched for {k0} {n0})")
                continue
            first[f["sha256"]] = (key, f["name"])
            chain = b.chain(f["url"])
            calls += chain
            ok_lines.append(f"bundle_fetch: ok {key} {f['name']} sha256={f['sha256']} size={f['size']} "
                            f"hops={','.join(host_of(u) for u in chain)}")
        return calls, ok_lines, held_lines

    def test_source_fetch_set_is_the_plan(self):
        b = wide()
        self.assertEqual(load_sbom_check().sample_keys(b.lock(), ARCH), sorted(one_per_kind().components),
                         "fixture: the sample is the one-per-kind entries")
        for arch, which in ((ARCH, "sample"), (ARCH, "full"), ("arm64", "sample"), ("arm64", "full")):
            with self.subTest(arch=arch, set=which):
                calls, ok_lines, held_lines = self._expected(b, arch, which)
                run = self.run_fetch(b.text(), b.routes(), arch=arch, which=which)
                self.assertEqual(run.rc, 0, run.text)
                self.assertEqual(run.net.calls, calls, "exactly the plan's files, lock URL first, in plan order")
                self.assertEqual(len(set(run.net.calls)), len(run.net.calls), "no URL requested twice")
                lines = run.out.splitlines()
                self.assertEqual([ln for ln in lines if ln.startswith("bundle_fetch: ok ")], ok_lines)
                self.assertEqual([ln for ln in lines if ln.startswith("bundle_fetch: held ")], held_lines)
                verified = {m.group(1): m.group(2) for m in
                            (re.match(r"^bundle_fetch: ok \S+ \S+ sha256=([0-9a-f]{64}) size=([0-9]+) ", ln)
                             for ln in lines) if m}
                for ln in (x for x in lines if x.startswith("bundle_fetch: held ")):
                    m = re.match(r"^bundle_fetch: held \S+ \S+ sha256=([0-9a-f]{64}) size=([0-9]+) ", ln)
                    self.assertIsNotNone(m, ln)
                    self.assertEqual(m.group(2), verified[m.group(1)], "M-2: a held line prints the verified size")
                keys = sorted({k for k, _ in plan_of(b, arch, which)})
                record = json.loads((run.outdir / "fetch.json").read_text(encoding="utf-8"))
                self.assertEqual((record["set"], record["arch"], sorted(record["components"])), (which, arch, keys))
                other = [f["url"] for e in b.components.values() if arch not in e["arches"] for f in e["files"]]
                self.assertEqual([u for u in run.net.calls if u in other], [], "the other arch is never requested")
        with self.subTest(case="fixture: the full amd64 plan holds both kinds of shared sha256"):
            _, _, held = self._expected(b, ARCH, "full")
            self.assertEqual(len(held), 2, held)


class SourceFetchRecordTest(_FetchCase):
    """Row 8 and A76: the lines, the canonical record written last."""

    def test_source_fetch_writes_the_record_last(self):
        b = one_per_kind()
        text = b.text()
        run = self.run_fetch(text, b.routes())
        self.assertEqual(run.rc, 0, run.text)
        plan = plan_of(b, ARCH, "sample")
        record_text = (run.outdir / "fetch.json").read_text(encoding="utf-8")
        record = json.loads(record_text)
        self.assertEqual(record_text, canon(record), "fetch.json is canonical (lock_text form)")
        want = {"format": 1, "set": "sample", "arch": ARCH, "lock_sha256": h("sha256", text.encode("utf-8")),
                "components": {}}
        for key, f in plan:
            want["components"].setdefault(key, []).append({"name": f["name"], "sha256": f["sha256"], "size": f["size"]})
        self.assertEqual(record, want)
        self.assertEqual(run.net.record_seen, [False] * len(run.net.calls), "the record never exists while fetching")
        self.assertEqual(run.listing(), sorted({f["sha256"] for _, f in plan} | {"fetch.json"}))
        for _, f in plan:
            p = run.outdir / f["sha256"]
            self.assertEqual(p.read_bytes(), b.bodies[f["url"]], "the bytes exactly as fetched")
            self.assertTrue(stat.S_ISREG(os.lstat(p).st_mode))
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(os.lstat(p).st_mode), 0o644)
        lines = run.out.splitlines()
        self.assertRegex(lines[-1], rf"^bundle_fetch: fetched {len(plan)} files, {sum(f['size'] for _, f in plan)} bytes, "
                                    rf"{len({k for k, _ in plan})} components \(sample, {ARCH}\) in [0-9]+(\.[0-9]+)? s$")
        self.assertIn("bundle_fetch: ok neo4j:neo4j@5.26.32 5.26.32.tar.gz sha256=" + b.components[NEO_KEY]["files"][0]["sha256"]
                      + f" size={b.components[NEO_KEY]['files'][0]['size']} hops=github.com,codeload.github.com", lines)
        with self.subTest(case="a failure on the last file writes no record"):
            key, f = plan[-1]
            routes = b.routes()
            for u in b.chain(f["url"])[1:] or [f["url"]]:
                routes[u] = (500, {}, b"")
            run = self.run_fetch(text, routes)
            self.assertEqual(run.rc, 1, run.text)
            self.assert_no_partial(run, absent=[f["sha256"]])

    def test_source_fetch_never_prints_a_redirect_query(self):
        b = only(one_per_kind(), TEM_KEY)
        data = b.bodies[TEM_URL]
        cases: dict[str, Any] = {
            "kept": data,
            "a 404 at the signed hop": (404, {}, b""),
            "a 503 at the signed hop": (503, {}, b""),
            "a timeout at the signed hop": "timeout",
            "a refused hop after it": (302, {"Location": f"https://evil.example.org/x?sig={SECRET}"}, b""),
        }
        for case, spec in cases.items():
            with self.subTest(case=case):
                run = self.run_fetch(b.text(), {TEM_URL: (302, {"Location": TEM_HOP}, b""), TEM_HOP: spec})
                self.assertEqual(run.rc, 0 if case == "kept" else 1, run.text)
                self.assertNotIn(SECRET, run.text, "U8-2: a redirect URL's query is never printed")
                if case == "kept":
                    self.assertIn(f"hops=github.com,release-assets.githubusercontent.com", run.out)
                    self.assertNotIn("?", run.out)

    def test_source_fetch_stops_at_the_run_deadline(self):
        b = one_per_kind()
        plan = plan_of(b, ARCH, "sample")
        for which, jump, fails in (("sample", 301, True), ("full", 301, False), ("full", 10801, True)):
            with self.subTest(set=which, jump=jump):
                now = [1000.0]
                routes = b.routes()
                first = plan[0][1]["url"]
                served = routes[first]

                def serve(served: Any = served, jump: int = jump) -> Any:
                    now[0] = 1000.0 + jump
                    return SimpleNamespace(status=200, headers={}, body=[served])
                routes[first] = serve
                run = self.run_fetch(b.text(), routes, which=which,
                                     patches=[lambda F: mock.patch.object(F, "CLOCK", lambda: now[0])])
                if not fails:
                    self.assertEqual(run.rc, 0, run.text)
                    continue
                key, f = plan[1]
                limit = 300 if which == "sample" else 10800
                self.assert_failed(run, fetch_fail(host_of(f["url"]), f["name"], f"run deadline {limit} s passed"))
                self.assertEqual(run.net.calls, b.chain(first), "checked before each request")

    def test_source_fetch_checks_disk_before_any_request(self):
        for which, b in (("sample", one_per_kind()), ("full", wide())):
            plan = plan_of(b, ARCH, which)
            need = sum({f["sha256"]: f["size"] for _, f in plan}.values())  # one size per distinct sha256
            with self.subTest(set=which, free="one byte short"):
                run = self.run_fetch(b.text(), b.routes(), which=which,
                                     patches=[lambda F, n=need: mock.patch.object(F, "DISK_FREE", lambda p: Free(n - 1))])
                self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage disk: need {need} bytes free in --out, "
                                                  f"found {need - 1}; no retry)"))
                self.assertEqual(run.net.calls, [])
                self.assertEqual(run.listing(), [])
            with self.subTest(set=which, free="exactly enough"):
                run = self.run_fetch(b.text(), b.routes(), which=which,
                                     patches=[lambda F, n=need: mock.patch.object(F, "DISK_FREE", lambda p: Free(n))])
                self.assertEqual(run.rc, 0, run.text)


class SourceFetchCliTest(_FetchCase):
    """Row 8 (CLI) and A75: bad arguments exit 2 before anything; every
    exception is one line."""

    def test_source_fetch_refuses_bad_arguments(self):
        b = one_per_kind()
        lock_p, pol_p, out = self.tmp / "sources.lock.json", self.tmp / "source-policy.json", self.tmp / "out"
        base = {"--lock": str(lock_p), "--policy": str(pol_p), "--out": str(out), "--arch": ARCH, "--set": "sample"}

        def argv(drop: str = "", **change: str) -> list[str]:
            got = {**base, **{f"--{k}": v for k, v in change.items()}}
            return [x for k, v in got.items() if k != drop for x in (k, v)]
        cases = {
            "no arguments": [],
            "no --set": argv("--set"),
            "no --out": argv("--out"),
            "no --arch": argv("--arch"),
            "another --set": argv(set="everything"),
            "another --arch (A75: amd64|arm64 only)": argv(arch="riscv64"),
            "an unknown argument": argv() + ["--retries", "3"],
        }
        for case, args in cases.items():
            with self.subTest(case=case):
                run = self.run_fetch(b.text(), b.routes(), argv=args)
                self.assertEqual(run.rc, 2, run.text)
                self.assertEqual(run.net.calls, [])
                self.assertEqual(run.listing(), [])
                self.assertNotIn("Traceback", run.text)

    def test_source_fetch_any_exception_is_one_line(self):
        b = one_per_kind()
        missing = str(self.tmp / "no-such-lock.json")
        cases: dict[str, tuple[dict[str, Any], list[Callable[[ModuleType], Any]]]] = {
            "an unreadable lock": ({"argv_lock": missing}, []),
            "a lock that is not JSON": ({"text": "{not json\n"}, []),
            "an unexpected error inside": ({}, [lambda F: mock.patch.object(F.S, "fetch_plan",
                                                                          side_effect=RuntimeError("boom"))]),
        }
        for case, (opts, patches) in cases.items():
            with self.subTest(case=case):
                argv = None
                if "argv_lock" in opts:
                    argv = ["--lock", opts["argv_lock"], "--policy", str(self.tmp / "source-policy.json"),
                            "--out", str(self.tmp / "out"), "--arch", ARCH, "--set", "sample"]
                run = self.run_fetch(opts.get("text", b.text()), b.routes(), argv=argv, patches=patches)
                self.assertEqual(run.rc, 1, run.text)
                self.assertEqual(len(run.fail_lines), 1, run.text)
                self.assertRegex(run.fail_lines[0], r"^bundle_fetch: FAIL \(stage [a-z]+: .+; no retry\)$")
                self.assertNotIn("Traceback", run.text)
                self.assertFalse(any(ln.startswith('  File "') for ln in run.text.splitlines()), run.text)
                self.assertEqual(run.net.calls, [])
                self.assertEqual(run.listing(), [])


# --------------------------------------------------------------------------
# U8a rework round 1 rows: the client (security M-1, M-2, L-1..L-4; review
# B-1, N-2, N-9; orchestrator rulings 2026-10-28)
# --------------------------------------------------------------------------

class SourceFetchEmptyPlanTest(_FetchCase):
    """M-1: an empty plan is a stage lock failure (exit 1, zero requests,
    no fetch.json), never a vacuous complete record."""

    def test_source_fetch_refuses_an_empty_plan(self):
        b = one_per_kind()
        empty = canon({"format": 1, "components": {}})
        cases = {
            "arm64 sample on an amd64-only lock": (b.text(), "arm64", "sample"),
            "arm64 full on an amd64-only lock": (b.text(), "arm64", "full"),
            "a lock with no components (sample)": (empty, ARCH, "sample"),
            "a lock with no components (full)": (empty, ARCH, "full"),
        }
        for case, (text, arch, which) in cases.items():
            with self.subTest(case=case):
                run = self.run_fetch(text, b.routes(), arch=arch, which=which)
                self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage lock: the lock lists no entry for {arch}; "
                                                  f"no retry)"))
                self.assertEqual(run.net.calls, [], "an empty plan makes zero requests")
                self.assertEqual(run.listing(), [], "no fetch.json for an empty plan")


class SourceFetchSharedSha256Test(_FetchCase):
    """M-2: a sha256 the lock gives two sizes or two upstream values (per
    alg) stops at stage lock, before any request, so a held file can never
    stand for a size or digest nobody checked."""

    def test_source_fetch_refuses_a_lock_whose_shared_sha256_disagrees(self):
        cases = {
            "probe Q2: the held entry's upstream sha512 is false": shared_sha256_conflict("sha512"),
            "probe Q2b: the held entry's lock size is false": shared_sha256_conflict("size"),
            "the disagreeing entry is for the other arch only": shared_sha256_conflict("size", ("arm64",)),
        }
        for case, (w, want) in cases.items():
            for which in ("sample", "full"):
                with self.subTest(case=case, set=which):
                    run = self.run_fetch(w.text(), w.routes(), which=which)
                    self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage lock: {want}; no retry)"))
                    self.assertIn(f"bundle_fetch: lock problem: {want}", run.err.splitlines())
                    self.assertEqual(run.net.calls, [], "a lock that fails its rules makes zero requests")
                    self.assertEqual(run.listing(), [])

    def test_source_fetch_refuses_a_shared_sha256_under_two_algs(self):
        """L-6 (rework round 2): probe R1 stops at stage lock, zero requests,
        no fetch.json (a held copy is never left unchecked for its alg)."""
        w, want = cross_alg_conflict()
        for which in ("sample", "full"):
            with self.subTest(set=which):
                run = self.run_fetch(w.text(), w.routes(), which=which)
                self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage lock: {want}; no retry)"))
                self.assertIn(f"bundle_fetch: lock problem: {want}", run.err.splitlines())
                self.assertEqual(run.net.calls, [], "a lock that fails its rules makes zero requests")
                self.assertEqual(run.listing(), [])


class SourceFetchWriteTest(_FetchCase):
    """B-1 / L-2 / N-3 (U8-4 `write failed: <OSError class>`): files this
    run did not create are never written or removed; O_EXCL on the `.part`
    is what the first row bites (a mutation to O_TRUNC writes through it)."""

    def test_source_fetch_keeps_a_part_file_it_did_not_create(self):
        b = only(one_per_kind(), JAXB_KEY)
        part = f".{b.components[JAXB_KEY]['files'][0]['sha256']}.part"
        foreign = b"a .part file this run did not create"
        run = self.run_fetch(b.text(), b.routes(), pre=lambda out: (out / part).write_bytes(foreign))
        self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage fetch: {MAVEN}: {JAXB_JAR}: "
                                          f"write failed: FileExistsError; no retry)"))
        self.assertEqual(run.net.calls, [], "the .part is opened before the request: no request for that file")
        self.assertEqual(run.listing(), [part], "no record, nothing else")
        self.assertEqual((run.outdir / part).read_bytes(), foreign, "the foreign .part is untouched")

    def test_source_fetch_write_failed_at_the_rename(self):
        b = only(one_per_kind(), JAXB_KEY)
        sha = b.components[JAXB_KEY]["files"][0]["sha256"]

        def taken(out: Path) -> None:
            (out / sha).mkdir()
            (out / sha / "keep").write_bytes(b"not ours")
        run = self.run_fetch(b.text(), b.routes(), pre=taken)
        self.assertEqual(run.rc, 1, run.text)
        self.assertEqual(len(run.fail_lines), 1, run.text)
        self.assertRegex(run.fail_lines[0], rf"^bundle_fetch: FAIL \(stage fetch: {re.escape(MAVEN)}: {re.escape(JAXB_JAR)}: "
                                            r"write failed: [A-Za-z]+Error; no retry\)$")
        self.assertNotIn("Traceback", run.text)
        self.assertEqual(run.listing(), [sha], "no .part and no fetch.json left")
        self.assertTrue((run.outdir / sha).is_dir())
        self.assertEqual((run.outdir / sha / "keep").read_bytes(), b"not ours")

    def test_source_fetch_keeps_a_record_part_file_it_did_not_create(self):
        b = only(one_per_kind(), JAXB_KEY)
        sha = b.components[JAXB_KEY]["files"][0]["sha256"]
        foreign = b"a .fetch.json.part this run did not create"
        run = self.run_fetch(b.text(), b.routes(), pre=lambda out: (out / ".fetch.json.part").write_bytes(foreign))
        self.assert_failed(run, re.escape("bundle_fetch: FAIL (stage fetch: fetch.json: write failed: FileExistsError; "
                                          "no retry)"))
        self.assertEqual(run.listing(), sorted([".fetch.json.part", sha]), "no fetch.json")
        self.assertEqual((run.outdir / ".fetch.json.part").read_bytes(), foreign, "the foreign file is untouched")


class SourceFetchOutTest(_FetchCase):
    """L-3 (orchestrator ruling): the client refuses to start when `--out`
    already holds fetch.json (stage lock, zero requests). The script's
    non-empty `--out` refusal is U8b's (carried)."""

    def test_source_fetch_refuses_an_out_holding_fetch_json(self):
        b = one_per_kind()
        old = b'{"format": 1}\n'
        run = self.run_fetch(b.text(), b.routes(), pre=lambda out: (out / "fetch.json").write_bytes(old))
        self.assert_failed(run, re.escape("bundle_fetch: FAIL (stage lock: --out already holds fetch.json; no retry)"))
        self.assertEqual(run.net.calls, [])
        self.assertEqual(run.listing(), ["fetch.json"])
        self.assertEqual((run.outdir / "fetch.json").read_bytes(), old, "the earlier record is untouched")


class SourceFetchRedactionTest(_FetchCase):
    """L-1: a refused Location whose query holds whitespace or NBSP prints
    `?<query omitted>` and none of the query (redacted at the source)."""

    def test_source_fetch_redacts_a_query_holding_whitespace(self):
        b = only(one_per_kind(), TEM_KEY)
        cases = {
            "a space": ("https://evil.example.org/x", "?sig=AAAA BBBBLEAK&x=1"),
            "an NBSP": ("https://release-assets.githubusercontent.com/x", "?sig=AAAA" + chr(0xA0) + "CCCCLEAK"),
            "a tab": ("https://evil.example.org/x", "?sig=AAAA" + chr(9) + "DDDDLEAK"),
        }
        for case, (head, query) in cases.items():
            with self.subTest(case=case):
                run = self.run_fetch(b.text(), {TEM_URL: (302, {"Location": TEM_HOP}, b""),
                                                TEM_HOP: (302, {"Location": head + query}, b"")})
                self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage fetch: github.com: {TEM_ASSET}: redirect to "
                                                  f"{head}?<query omitted> refused: not printable ASCII; no retry)"))
                for leak in ("AAAA", "LEAK", SECRET):
                    self.assertNotIn(leak, run.text, "U8-2: no part of a redirect query is printed")
                self.assertEqual(run.listing(), [])


class SourceFetchItem11Test(_FetchCase):
    """L-4: design item 11 properties with a static row (no network)."""

    def test_default_opener_is_tls12_without_proxy_or_redirects(self):
        seen: dict[str, Any] = {}

        class Stop(Exception):
            pass

        def fake_open(director: Any, req: Any, data: Any = None, timeout: Any = None) -> Any:
            seen.update(director=director, req=req, timeout=timeout)
            raise Stop()
        asked: list[int] = []

        def getproxies() -> dict[str, str]:
            asked.append(1)
            return {"https": "http://proxy.example.invalid:3128", "http": "http://proxy.example.invalid:3128"}
        # ProxyHandler({}) holds no `<scheme>_open`, so OpenerDirector never lists it; what it does is keep
        # build_opener from adding the default ProxyHandler(), which reads the proxies from the process
        # settings (getproxies). A proxy offered there must be neither read nor installed.
        with mock.patch.object(urllib.request.OpenerDirector, "open", fake_open), \
                mock.patch.object(urllib.request, "getproxies", getproxies), \
                mock.patch("socket.create_connection", side_effect=AssertionError("a real connection")):
            with self.assertRaises(Stop):
                self.F.R._default_opener(JAXB_URL, 7.0)
        handlers = seen["director"].handlers
        self.assertEqual(asked, [], "the proxy settings are never read (ProxyHandler({}))")
        self.assertEqual([x for x in handlers if isinstance(x, urllib.request.ProxyHandler)], [],
                         "no proxying handler is installed")
        redirects = [x for x in handlers if isinstance(x, urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(redirects), 1, handlers)
        self.assertIsNot(type(redirects[0]), urllib.request.HTTPRedirectHandler, "the default redirect handler is replaced")
        self.assertIsNone(redirects[0].redirect_request(seen["req"], None, 302, "Found", {}, "https://evil.example.org/x"),
                          "redirects are never followed by urllib (by hand, under the hop rules)")
        https = [x for x in handlers if isinstance(x, urllib.request.HTTPSHandler)]
        self.assertEqual(len(https), 1, handlers)
        ctx = https[0]._context
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertIn(ctx.minimum_version, (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3), "TLS >= 1.2")
        self.assertEqual((ctx.verify_mode, ctx.check_hostname), (ssl.CERT_REQUIRED, True))
        self.assertEqual(seen["req"].full_url, JAXB_URL)
        self.assertEqual(seen["req"].get_header("User-agent"), "knowledge-engine-sources-lock",
                         "the User-Agent proven at GitLab is unchanged")
        self.assertEqual(seen["timeout"], 7.0)

    def test_source_fetch_unpacks_builds_and_runs_nothing(self):
        tree = ast.parse(FETCH.read_text(encoding="utf-8"))
        mods: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods.add((node.module or "").split(".")[0])
                if node.module == "shutil":
                    self.assertLessEqual({a.name for a in node.names}, {"disk_usage"})
        banned_mods = {"subprocess", "tarfile", "zipfile", "gzip", "bz2", "lzma", "zlib", "shlex", "pty", "ctypes",
                       "multiprocessing", "concurrent", "runpy", "code", "codeop", "compileall", "py_compile",
                       "zipimport", "pickle", "marshal", "shelve", "asyncio", "socket", "http"}
        self.assertEqual(mods & banned_mods, set(), "nothing unpacked, built or run (item 11)")
        names = ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
                 | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)})
        banned = {"exec", "eval", "compile", "__import__", "import_module", "system", "popen", "startfile",
                  "unpack_archive", "make_archive", "fork", "forkpty", "posix_spawn", "posix_spawnp", "run_path",
                  "run_module", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
                  "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"}
        self.assertEqual(names & banned, set(), "nothing unpacked, built or run (item 11)")
        shutil_attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                        and isinstance(n.value, ast.Name) and n.value.id == "shutil"}
        self.assertLessEqual(shutil_attrs, {"disk_usage"}, "shutil only measures free space")
        loaded = [n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_sibling" and n.args and isinstance(n.args[0], ast.Constant)]
        self.assertEqual(sorted(loaded), ["sbom_check", "sources_resolve"], "only the two siblings are loaded")
        execs = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "exec_module"]
        self.assertEqual(len(execs), 1, "one exec_module: the sibling loader")


class SourceFetchTextTest(_FetchCase):
    """N-2 (item 5): the verified `.dsc` is read as UTF-8 text of at most
    `R.TEXT_LIMIT` bytes, else a named stage fetch failure."""

    def test_source_fetch_reads_only_small_utf8_text(self):
        limit = self.F.R.TEXT_LIMIT
        src, ver = key_parts(DEB_KEY)
        dsc = f"{src}_{ver}.dsc"
        others = [("bash_5.2.15.orig.tar.gz", blob("bash orig", 400))]
        base = dsc_text(src, ver, [(n, len(d), h("sha256", d)) for n, d in others])
        big = LockBuilder()
        big.deb(DEB_KEY, others, extra="#" * (limit + 1 - len(base.encode())))
        self.assertEqual(big.components[DEB_KEY]["files"][0]["size"], limit + 1, "fixture: one byte over the limit")
        bad = LockBuilder()
        bad.deb(DEB_KEY, others, extra="Comment: X\n")
        with_dsc_bytes(bad, DEB_KEY, bad.bodies[bad.components[DEB_KEY]["files"][0]["url"]].replace(b"X", b"\xff"))
        for case, b, tail in (("one byte over 1 MiB", big, "over 1 MiB, not checked"),
                              ("a byte that is not UTF-8", bad, "not UTF-8 text")):
            with self.subTest(case=case):
                run = self.run_fetch(b.text(), b.routes())
                self.assert_failed(run, fetch_fail("snapshot.debian.org", dsc, tail))
                self.assert_no_partial(run)
        with self.subTest(case="control: exactly the limit is read"):
            ok = LockBuilder()
            ok.deb(DEB_KEY, others, extra="#" * (limit - len(base.encode())))
            run = self.run_fetch(ok.text(), ok.routes())
            self.assertEqual(run.rc, 1, run.text)
            self.assertNotIn("over 1 MiB", run.text, "a .dsc of exactly 1 MiB is read (then parsed)")


# --------------------------------------------------------------------------
# U8a rows: the split-out helpers (design item 1; item 12 rows 9 and 10)
# --------------------------------------------------------------------------

class DownloadTest(unittest.TestCase):
    """`sources_resolve.download`: one attempt, the byte cap before a chunk
    is hashed or written, the hop rules (item 1)."""

    ALLOW = {MAVEN, "github.com", "codeload.github.com"}

    def _call(self, routes: dict[str, Any], url: str, limit: int, algs: tuple[str, ...] = ("sha1",)
              ) -> tuple[Any, io.BytesIO, list[str], Net, Recorder]:
        mod = load_resolver()
        download = rfn("download")
        net, sleeps, fh, hops = Net(routes), Recorder(), io.BytesIO(), []

        def no_attempts(*a: Any, **k: Any) -> Any:
            raise AssertionError("download() called _attempts (item 1: it never does)")
        with mock.patch.object(mod, "OPENER", net), mock.patch.object(mod, "SLEEP", sleeps), \
                mock.patch.object(mod, "_attempts", no_attempts), mock.patch.object(mod, "_ACTIVE_RETRIES", [3]), \
                mock.patch("time.sleep", sleeps):
            try:
                got: Any = download(url, self.ALLOW, fh, limit, algs, hops)
            except rfn("ResolveError") as exc:
                got = exc
        return got, fh, hops, net, sleeps

    def test_download_has_no_retries_parameter(self):
        params = inspect.signature(rfn("download")).parameters
        self.assertEqual(list(params), ["url", "allow", "fh", "limit", "algs", "hops"])
        self.assertFalse(any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params.values()))

    def test_download_is_one_attempt(self):
        good = blob("jaxb sources", 150)
        for case, seq, want in (("a 503", [(503, {}, b""), good], f"{MAVEN}: HTTP 503: {JAXB_URL}"),
                                ("a timeout", ["timeout", good], f"{MAVEN}: timeout after 60 s: {JAXB_URL}"),
                                ("a mid-body timeout", [body_then([good[:7]], TimeoutError("timed out")), good],
                                 f"{MAVEN}: timeout after 60 s: {JAXB_URL}")):
            with self.subTest(case=case):
                got, fh, hops, net, sleeps = self._call({JAXB_URL: list(seq)}, JAXB_URL, len(good))
                self.assertIsInstance(got, rfn("ResolveError"))
                self.assertEqual(str(got), want)
                self.assertEqual(net.calls, [JAXB_URL])
                self.assertEqual(sleeps.calls, [])

    def test_download_hashes_writes_and_records_hops(self):
        good = blob("neo4j tag tarball", 500)
        got, fh, hops, net, _ = self._call({NEO_URL: (302, {"Location": NEO_HOP}, b""), NEO_HOP: good}, NEO_URL,
                                          len(good), ("sha256",))
        self.assertNotIsInstance(got, Exception, str(got))
        digests, size = got
        self.assertEqual((digests, size), ({"sha256": h("sha256", good)}, len(good)))
        self.assertEqual(fh.getvalue(), good)
        self.assertEqual(hops, ["github.com", "codeload.github.com"])
        jar = blob("jaxb sources", 150)
        got, fh, hops, _, _ = self._call({JAXB_URL: jar}, JAXB_URL, len(jar), ("sha1",))
        self.assertEqual(got, ({"sha256": h("sha256", jar), "sha1": h("sha1", jar)}, len(jar)))
        with self.subTest(case="a refused hop writes nothing"):
            got, fh, hops, net, _ = self._call({JAXB_URL: (302, {"Location": "https://evil.example.org/x"}, b"")},
                                              JAXB_URL, 150)
            self.assertIsInstance(got, rfn("ResolveError"))
            self.assertEqual(str(got), "redirect to evil.example.org refused: not in hosts")
            self.assertEqual((fh.getvalue(), net.calls), (b"", [JAXB_URL]))

    def test_download_stops_at_the_byte_cap(self):
        data = blob("x", 21)
        pulled: list[int] = []

        def make() -> Any:
            def gen() -> Iterator[bytes]:
                for i in range(0, len(data), 7):
                    pulled.append(i)
                    yield data[i:i + 7]
            return SimpleNamespace(status=200, headers={}, body=gen())
        got, fh, _, _, _ = self._call({JAXB_URL: make}, JAXB_URL, 10)
        self.assertIsInstance(got, rfn("ResolveError"))
        self.assertEqual(str(got), f"{MAVEN}: more than 10 bytes: {JAXB_URL}")
        self.assertEqual(fh.getvalue(), data[:7], "the chunk past the cap is never written")
        self.assertEqual(len(pulled), 2, "nothing is read past the chunk that crosses the cap")
        with self.subTest(case="control: a body of exactly the limit"):
            pulled.clear()
            got, fh, _, _, _ = self._call({JAXB_URL: make}, JAXB_URL, 21)
            self.assertEqual(got, ({"sha256": h("sha256", data), "sha1": h("sha1", data)}, 21))
            self.assertEqual(fh.getvalue(), data)

    def test_download_never_quotes_a_refused_query(self):
        """L-1 at the source: the refused-Location text drops the query."""
        for case, query in (("a space", "?sig=AAAA BBBBLEAK"), ("an NBSP", "?sig=AAAA" + chr(0xA0) + "CCCCLEAK")):
            with self.subTest(case=case):
                loc = "https://repo1.maven.org/x.jar" + query
                got, fh, _, net, _ = self._call({JAXB_URL: (302, {"Location": loc}, b"")}, JAXB_URL, 150)
                self.assertIsInstance(got, rfn("ResolveError"))
                self.assertEqual(str(got), "redirect to https://repo1.maven.org/x.jar?<query omitted> refused: "
                                           "not printable ASCII")
                self.assertEqual((fh.getvalue(), net.calls), (b"", [JAXB_URL]))


class DscListingTest(unittest.TestCase):
    """`sources_resolve.dsc_listing`: the part of `dsc_files` that is not
    snapshot-specific (item 1); `dsc_files` keeps its U7c rows (control)."""

    ROWS = [("bash_5.2.15.orig.tar.gz", 400, h("sha256", b"orig")),
            ("bash_5.2.15-2.debian.tar.xz", 120, h("sha256", b"debian"))]
    DSC = "bash_5.2.15-2.dsc"

    def _fields(self, text: str) -> dict[str, str]:
        return rfn("parse_dsc")(text, self.DSC)

    def test_dsc_listing_is_the_snapshot_free_part_of_dsc_files(self):
        fields = self._fields(dsc_text("bash", "5.2.15-2", self.ROWS))
        got = [tuple(x) for x in rfn("dsc_listing")(fields, self.DSC, "bash", "5.2.15-2")]
        self.assertEqual(got, [tuple(r) for r in self.ROWS])
        names = {n: h("sha1", n.encode()) for n, _, _ in self.ROWS}
        files = rfn("dsc_files")(fields, self.DSC, "bash", "5.2.15-2", names)
        self.assertEqual(got, [(f["name"], f["size"], f["sha256"]) for f in files])

    def test_dsc_listing_refusals(self):
        err = rfn("ResolveError")
        listing = rfn("dsc_listing")
        good = dsc_text("bash", "5.2.15-2", self.ROWS)
        cases = {
            "another Source/Version": (good, "bash", "5.2.15-3",
                                       f"{self.DSC}: Source/Version is bash/5.2.15-2, want bash/5.2.15-3"),
            "Files and Checksums-Sha256 differ": (good.replace(" 120 bash_5.2.15-2.debian.tar.xz\nFiles:",
                                                               " 121 bash_5.2.15-2.debian.tar.xz\nFiles:"),
                                                  "bash", "5.2.15-2",
                                                  f"{self.DSC}: Checksums-Sha256 and Files list different files"),
            "an unsafe name": (dsc_text("bash", "5.2.15-2", [("../x.tar.gz", 1, "b" * 64)]), "bash", "5.2.15-2",
                               "../x.tar.gz: not a safe file name"),
            "Checksums-Sha1 names another file": (
                good + "Checksums-Sha1:\n " + "c" * 40 + " 400 bash_5.2.15.orig.tar.gz\n " + "d" * 40
                + " 120 other.tar.xz\n", "bash", "5.2.15-2",
                f"{self.DSC}: Checksums-Sha1 and Checksums-Sha256 list different files"),
        }
        for case, (text, src, ver, want) in cases.items():
            with self.subTest(case=case):
                with self.assertRaises(err) as caught:
                    listing(self._fields(text), self.DSC, src, ver)
                if want is not None:
                    self.assertEqual(str(caught.exception), want)

    def test_dsc_listing_checksums_sha1_rule(self):
        """L-5 / N-8: a present Checksums-Sha1, an empty one included, lists
        the same (name, size) rows as Checksums-Sha256."""
        listing, err = rfn("dsc_listing"), rfn("ResolveError")
        good = dsc_text("bash", "5.2.15-2", self.ROWS)
        sha1 = "".join(f" {'c' * 40} {size} {name}\n" for name, size, _ in self.ROWS)
        want = f"{self.DSC}: Checksums-Sha1 and Checksums-Sha256 list different files"
        cases = {
            "an empty Checksums-Sha1 field (last)": good + "Checksums-Sha1:\n",
            "an empty Checksums-Sha1 field (between others)": good.replace("Files:", "Checksums-Sha1:\nFiles:"),
            "a Checksums-Sha1 size that differs": good + "Checksums-Sha1:\n" + sha1.replace(" 120 ", " 121 "),
            "a Checksums-Sha1 with one file fewer": good + "Checksums-Sha1:\n" + sha1.splitlines(True)[0],
        }
        for case, text in cases.items():
            with self.subTest(case=case):
                with self.assertRaises(err) as caught:
                    listing(self._fields(text), self.DSC, "bash", "5.2.15-2")
                self.assertEqual(str(caught.exception), want)
        for case, text in (("control: an agreeing Checksums-Sha1", good + "Checksums-Sha1:\n" + sha1),
                           ("control: no Checksums-Sha1 field", good)):
            with self.subTest(case=case):
                got = [tuple(x) for x in listing(self._fields(text), self.DSC, "bash", "5.2.15-2")]
                self.assertEqual(got, [tuple(r) for r in self.ROWS])


class LockEntryProblemsTest(unittest.TestCase):
    """`sbom_check.lock_entry_problems`: `lock_problems` without coverage.
    The split itself is pure (every U7a-U7e lock test is its control); the
    shared-sha256 rules (U8a rework rounds 1 and 2) are new in both."""

    def test_lock_entry_problems_passes_the_committed_lock(self):
        text = COMMITTED_LOCK.read_text(encoding="utf-8")
        self.assertEqual(sfn("lock_entry_problems")(text, policy()), [])

    def test_lock_entry_problems_is_lock_problems_without_coverage(self):
        entry_problems, lock_problems = sfn("lock_entry_problems"), sfn("lock_problems")
        b = wide()
        broken_url = b.lock()
        broken_url["components"][JAXB_KEY]["files"][0]["url"] = JAXB_URL.replace("https://", "http://")
        broken_size = b.lock()
        broken_size["components"][PYPI_KEY]["files"][0]["size"] = 0
        texts = {"good (every entry stale against no SBOM)": b.text(), "a bad url": canon(broken_url),
                 "a bad size": canon(broken_size), "not canonical": json.dumps(b.lock()) + "\n",
                 "not JSON": "{", "another format": canon({"format": 2, "components": b.components})}
        for case, text in texts.items():
            with self.subTest(case=case):
                full = lock_problems(text, policy(), {}, ARCH)
                self.assertEqual(entry_problems(text, policy()), [x for x in full if STALE not in x])
        self.assertEqual(entry_problems(b.text(), policy()), [])
        self.assertTrue(any(STALE in x for x in lock_problems(b.text(), policy(), {}, ARCH)),
                        "a stale entry is a lock_problems problem only")

    def test_lock_entry_problems_today(self):
        import datetime
        text = one_per_kind().text()
        got = sfn("lock_entry_problems")(text, policy(), today=datetime.date(2026, 10, 24))
        self.assertEqual(got, [f"lock: {NEO_KEY}: the second-fetch date 2026-10-25 is after today (UTC)"])

    def test_lock_entry_problems_one_sha256_one_upstream_alg(self):
        """L-6 / R1-N2 (orchestrator ruling, rework round 2): one sha256
        carries exactly one upstream alg across the whole lock and arches."""
        entry_problems, lock_problems = sfn("lock_entry_problems"), sfn("lock_problems")
        w, want = cross_alg_conflict()
        self.assertEqual(entry_problems(w.text(), policy()), [want])
        for arch in ("amd64", "arm64"):
            self.assertIn(want, lock_problems(w.text(), policy(), {}, arch))
        with self.subTest(case="the later entry arm64 only"):
            lk = w.lock()
            lk["components"]["apk:bbb@1.0-r0"]["arches"] = ["arm64"]
            self.assertEqual(entry_problems(canon(lk), policy()), [want])
        with self.subTest(case="control: probe R1 with one alg (the true sha512 under sha512 in both) passes"):
            x = blob("shared patch", 90)
            ok = LockBuilder()
            ok.apk("apk:aaa@1.0-r0", patches=[("shared.patch", x)])
            ok.apk("apk:bbb@1.0-r0", patches=[("shared.patch", x)])
            self.assertEqual(entry_problems(ok.text(), policy()), [])

    def test_lock_entry_problems_one_sha256_one_size_and_upstream(self):
        """M-2 (orchestrator ruling): one sha256 carries one size and, per
        upstream alg, one upstream value across all entries and arches; a
        conflict is a named problem of lock_entry_problems and lock_problems."""
        entry_problems, lock_problems = sfn("lock_entry_problems"), sfn("lock_problems")
        cases = {
            "probe Q2: another upstream sha512": shared_sha256_conflict("sha512"),
            "probe Q2b: another size": shared_sha256_conflict("size"),
            "another size, the later entry arm64 only": shared_sha256_conflict("size", ("arm64",)),
            "another upstream sha512, the later entry arm64 only": shared_sha256_conflict("sha512", ("arm64",)),
        }
        for case, (w, want) in cases.items():
            with self.subTest(case=case):
                self.assertEqual(entry_problems(w.text(), policy()), [want])
                for arch in ("amd64", "arm64"):
                    self.assertIn(want, lock_problems(w.text(), policy(), {}, arch))
        with self.subTest(case="a deb orig shared by two entries, another size (probe P2b)"):
            b = LockBuilder()
            orig = ("bash_5.2.15.orig.tar.gz", blob("bash orig", 400))
            b.deb(DEB_KEY, [orig, ("bash_5.2.15-2.debian.tar.xz", blob("d2", 120))])
            b.deb("deb:bash@5.2.15-2+deb12u1", [orig, ("bash_5.2.15-2+deb12u1.debian.tar.xz", blob("d3", 100))])
            lk = b.lock()
            f1 = next(f for f in lk["components"]["deb:bash@5.2.15-2+deb12u1"]["files"] if f["name"] == orig[0])
            f1["size"] = 401
            self.assertEqual(entry_problems(canon(lk), policy()),
                             [f"lock: deb:bash@5.2.15-2+deb12u1: {orig[0]}: sha256 {h('sha256', orig[1])} is size 401 "
                              f"here but 400 in {DEB_KEY}"])
        with self.subTest(case="one sha256 under two upstream algs (apk sha512 first, deb sha256): rework round 2 "
                               "makes this a problem (it was a control in round 1)"):
            b = LockBuilder()
            data = blob("shared tarball", 300)
            b.deb(DEB_KEY, [("bash_5.2.15.orig.tar.gz", data), ("bash_5.2.15-2.debian.tar.xz", blob("d2", 120))])
            b.apk(APK_KEY, distfiles=[("readline-8.2.13.tar.gz", data)])
            want = (f"lock: {DEB_KEY}: bash_5.2.15.orig.tar.gz: sha256 {h('sha256', data)} has upstream alg sha256 "
                    f"here but sha512 in {APK_KEY}")
            self.assertEqual(entry_problems(b.text(), policy()), [want])
            self.assertIn(want, lock_problems(b.text(), policy(), {}, ARCH))
        with self.subTest(case="control: wide()'s two shared sha256 agree"):
            self.assertEqual(entry_problems(wide().text(), policy()), [])


class FetchPlanTest(unittest.TestCase):
    """`sbom_check.fetch_plan(lock, arch, set)`: sample is `sample_keys`;
    full is every key for the arch; sorted by key, then file order."""

    def test_fetch_plan_rows(self):
        fetch_plan, sample_keys = sfn("fetch_plan"), sfn("sample_keys")
        lock = wide().lock()
        comps = lock["components"]
        for arch in ("amd64", "arm64"):
            with self.subTest(arch=arch, set="sample"):
                want = [(k, f) for k in sample_keys(lock, arch) for f in comps[k]["files"]]
                self.assertEqual([tuple(x) for x in fetch_plan(lock, arch, "sample")], want)
            with self.subTest(arch=arch, set="full"):
                want = [(k, f) for k in sorted(comps) if arch in comps[k]["arches"] for f in comps[k]["files"]]
                self.assertEqual([tuple(x) for x in fetch_plan(lock, arch, "full")], want)
        self.assertEqual({k for k, _ in fetch_plan(lock, "arm64", "full")}, {"deb:dash@0.5.12-2"})

    def test_fetch_plan_refuses_an_unknown_set(self):
        """N-4: the documented interface takes sample or full only."""
        fetch_plan = sfn("fetch_plan")
        lock = wide().lock()
        for which in ("everything", "", "Sample", "FULL", "sample "):
            with self.subTest(set=which):
                with self.assertRaises(ValueError):
                    fetch_plan(lock, ARCH, which)


# --------------------------------------------------------------------------
# Fixture controls (green before U8a: the synthetic data is what it claims)
# --------------------------------------------------------------------------

class SyntheticFixtureControlTest(unittest.TestCase):

    def test_synthetic_locks_pass_the_lock_rules(self):
        lock_problems = load_sbom_check().lock_problems
        for name, b in (("one_per_kind", one_per_kind()), ("wide", wide())):
            for arch in ("amd64", "arm64"):
                with self.subTest(lock=name, arch=arch):
                    got = [x for x in lock_problems(b.text(), policy(), {}, arch) if STALE not in x]
                    self.assertEqual(got, [])
                    for e in b.components.values():
                        for f in e["files"]:
                            data = b.bodies[f["url"]]
                            self.assertEqual((h("sha256", data), len(data), h(f["upstream"]["alg"], data)),
                                             (f["sha256"], f["size"], f["upstream"]["value"]))

    def test_name_check_fixtures_are_what_they_claim(self):
        """The existing parsers, read as item 5 says, find the controls equal
        and every other case different (an in-test reading of the check)."""
        R = load_resolver()
        for kind in ("deb", "pgdg"):
            key = DEB_KEY if kind == "deb" else PGDG_KEY
            src, ver = key_parts(key)
            for case, b in dsc_cases(kind).items():
                with self.subTest(kind=kind, case=case):
                    files = b.components[key]["files"]
                    fields = R.parse_dsc(b.bodies[files[0]["url"]].decode(), files[0]["name"])
                    listed = {(f["name"], f["size"], f["sha256"]) for f in
                              R.dsc_files(fields, files[0]["name"], src, ver, {n: "0" * 40 for n in [
                                  ln.split()[2] for ln in fields["Checksums-Sha256"].splitlines()]})}
                    entry = {(f["name"], f["size"], f["sha256"]) for f in files[1:]}
                    self.assertEqual(listed == entry, case.startswith("control"))


if __name__ == "__main__":
    unittest.main()
