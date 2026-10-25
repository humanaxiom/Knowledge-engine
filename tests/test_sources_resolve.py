"""platform-sbom U7b: the source lock's resolver and its maintainer tool
(PSC-15, PSC-23; design-notes N5 and its U7 amendment: item 1's U7b row,
item 3 "where the lock tool runs", item 4 checksums, provenance, messages and
exit codes, "Resolution endpoints", rework rounds 1-2 for the entry shapes).
Orchestrator U7b rulings 1-4 (2026-10-25).

No network: `scripts/sources_resolve.py` is imported by path and its one
opener, the module-level `OPENER(url, timeout)`, is replaced by a fake that
serves canned responses (an object with `status`, `headers` with lower-case
keys, and `body`, an iterable of byte chunks; a timeout raises TimeoutError).
That hook is the tester's reading of N5's "every request goes through one
opener": there is no `--fake-net` flag and nothing read from the environment.

Interface pinned (tester, U7b RED, 2026-10-25; names the developer keeps):
- `sources_resolve.py`: `ResolveError`; `fetch(url, allow)`; `stream(url,
  allow, algs) -> (digests, size)`; `parse_sha256_txt(body, asset)`;
  `parse_sha1(body, label, name)`; `uv_lock_sdist(uv_lock_text, name, ver)`;
  `pypi_json_sdist(doc, name, ver)`; `temurin_tag(release_text,
  sbom_version)`; `resolve(needs, lock, policy, uv_lock_text, arch,
  refresh=False) -> (lock, neo4j_candidates, skipped_keys)`; `main(argv)`.
- `sbom_check.py`: `tar_file_text(tar, member)`, `lock_needs_doc(policy, docs,
  releases) -> (needs_doc, problems)`, subcommand `lock-needs`.
- needs.json: `{"format": 1, "needs": {key: {"kind", "packages", "route"}}}`;
  temurin's route is `{"sbom_version", "release"}` (the release file text),
  so the resolver derives the tag (ruling 1) and its service mounts no tar.

Fixtures: tests/fixtures/sbom-u3, docker/source-policy.json, uv.lock; never
docs/evidence.
"""

from __future__ import annotations

import contextlib
import email.message
import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock
from urllib.parse import urljoin

import yaml

from tests import compose_support as cs
from tests import fake_docker
from tests import sbom_support as ss
from tests.engine_support import ROOT
from tests.test_offline_bundle import _BundleBase
from tests.test_sbom_bundle import load_sbom_check
from tests.test_sources_lock import FIXTURE_KEYS, fixture_docs, good_lock, policy

RESOLVER = ROOT / "scripts" / "sources_resolve.py"
LOCK_SH = ROOT / "scripts" / "sources_lock.sh"
SOURCES_COMPOSE = ROOT / "docker-compose.sources.yml"
ARCH = "amd64"
TEM_KEY = "temurin:jdk-21.0.12.1+1"
TEM_ASSET = "OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz"
TEM_URL = f"https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/{TEM_ASSET}"
JAXB_KEY = "maven:javax.xml.bind:jaxb-api@2.2.12"
JAXB_JAR = "jaxb-api-2.2.12-sources.jar"
JAXB_URL = f"https://repo1.maven.org/maven2/javax/xml/bind/jaxb-api/2.2.12/{JAXB_JAR}"
NEO_KEY = "neo4j:neo4j@5.26.32"
NEO_URL = "https://github.com/neo4j/neo4j/archive/refs/tags/5.26.32.tar.gz"
RELEASE = ('IMPLEMENTOR="Eclipse Adoptium"\nIMPLEMENTOR_VERSION="Temurin-21.0.12.1+1"\n'
           'JAVA_RUNTIME_VERSION="21.0.12.1+1-LTS"\nJAVA_VERSION="21.0.12.1"\n')
PANDAS_SDIST = ("https://files.pythonhosted.org/packages/33/01/" + "d" * 60 + "/pandas-2.3.3.tar.gz")


_LOADED: dict[tuple[str, str], ModuleType] = {}


def load_resolver() -> ModuleType:
    """The module, loaded once per file content (so a test's ResolveError and
    patched OPENER belong to the module its functions use)."""
    if not RESOLVER.is_file():
        raise AssertionError("scripts/sources_resolve.py is missing (platform-sbom U7b; design-notes N5 amendment U7, "
                             "items 3-4)")
    key = (str(RESOLVER), hashlib.sha256(RESOLVER.read_bytes()).hexdigest())
    if key not in _LOADED:
        spec = importlib.util.spec_from_file_location(f"ke_sources_resolve_under_test_{key[1][:12]}", RESOLVER)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _LOADED[key] = mod
    return _LOADED[key]


def rfn(name: str) -> Any:
    got = getattr(load_resolver(), name, None)
    if got is None:
        raise AssertionError(f"scripts/sources_resolve.py has no {name} (U7b interface, tests/test_sources_resolve.py)")
    return got


class FakeNet:
    """url -> (status, headers, body) or "timeout"; records each call."""

    def __init__(self, routes: dict[str, Any]):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> Any:
        self.calls.append(url)
        spec = self.routes.get(url)
        if spec is None:
            return SimpleNamespace(status=404, headers={}, body=[b"not found"])
        if spec == "timeout":
            raise TimeoutError("timed out")
        status, headers, body = spec
        data = body.encode() if isinstance(body, str) else body
        return SimpleNamespace(status=status, headers={k.lower(): v for k, v in headers.items()},
                               body=[data[i:i + 7] for i in range(0, len(data), 7)] or [b""])


def ok(body: bytes | str) -> tuple[int, dict[str, str], bytes | str]:
    return 200, {}, body


def moved(to: str) -> tuple[int, dict[str, str], bytes]:
    return 302, {"Location": to}, b""


@contextlib.contextmanager
def network(mod: ModuleType, routes: dict[str, Any]) -> Any:
    net = FakeNet(routes)
    with mock.patch.object(mod, "OPENER", net):
        yield net


ALLOW = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com", "codeload.github.com",
         "repo1.maven.org", "files.pythonhosted.org", "pypi.org"}
ASSET_BODY = b"jdk sources tarball bytes"
JAR_BODY = b"jaxb sources jar bytes"
NEO_BODY = b"neo4j tag tarball bytes"
PANDAS_BODY = b"pandas sdist bytes"


def sha(alg: str, data: bytes) -> str:
    return hashlib.new(alg, data).hexdigest()


def temurin_routes(sidecar_hash: str | None = None) -> dict[str, Any]:
    redirect = "https://release-assets.githubusercontent.com/github-production-release-asset/1/asset"
    return {TEM_URL + ".sha256.txt": ok(f"{sidecar_hash or sha('sha256', ASSET_BODY)}  {TEM_ASSET}\n"),
            TEM_URL: moved(redirect), redirect: ok(ASSET_BODY)}


def maven_routes(sidecar: str | None = None) -> dict[str, Any]:
    return {JAXB_URL + ".sha1": ok(f"{sidecar or sha('sha1', JAR_BODY)}  {JAXB_JAR}\n"), JAXB_URL: ok(JAR_BODY)}


def pandas_json(n_sdist: int = 1, digest: str | None = None) -> str:
    urls = [{"packagetype": "bdist_wheel", "url": "https://files.pythonhosted.org/packages/aa/bb/" + "e" * 60 + "/x.whl",
             "digests": {"sha256": "e" * 64}}]
    urls += [{"packagetype": "sdist", "url": PANDAS_SDIST, "digests": {"sha256": digest or sha("sha256", PANDAS_BODY)},
              "size": len(PANDAS_BODY)}] * n_sdist
    return json.dumps({"info": {"name": "pandas", "version": "2.3.3"}, "urls": urls})


def need(key: str, image: str, purl: str, route: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": key.split(":", 1)[0], "packages": [{"image": image, "purl": purl, "spdxid": "SPDXRef-x"}],
            "route": route or {}}


def tem_need() -> dict[str, Any]:
    return need(TEM_KEY, "ke-neo4j", "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS",
                {"sbom_version": "21.0.12.1+1-LTS", "release": RELEASE})


EMPTY_LOCK = {"format": 1, "components": {}}


def docs_for(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {image: ss.spdx_doc(image, r) for image, r in rows.items()}


def lock_ok(test: unittest.TestCase, lock: dict[str, Any], docs: dict[str, Any]) -> None:
    """U7a's check on what the resolver produced (the orchestrator's brief)."""
    check = load_sbom_check()
    problems = check.lock_problems(check.lock_text(lock), policy(), docs, ARCH)
    test.assertEqual(problems, [], "a resolved entry fails sbom_check.py lock_problems")


# --------------------------------------------------------------------------
# The opener: hop-by-hop redirects (item 3.5, item 4 messages)
# --------------------------------------------------------------------------

class ResolverHopsTest(unittest.TestCase):

    def test_hop_rules_and_messages(self):
        mod = load_resolver()
        err, fetch, stream = rfn("ResolveError"), rfn("fetch"), rfn("stream")
        url = "https://github.com/a/b"
        with self.subTest(case="a redirect inside the allowlist is followed and streamed"):
            with network(mod, {url: moved("https://objects.githubusercontent.com/x"),
                               "https://objects.githubusercontent.com/x": ok(ASSET_BODY)}) as net:
                digests, size = stream(url, ALLOW, ("sha256", "sha1"))
            self.assertEqual((digests["sha256"], digests["sha1"], size),
                             (sha("sha256", ASSET_BODY), sha("sha1", ASSET_BODY), len(ASSET_BODY)))
            self.assertEqual(net.calls, [url, "https://objects.githubusercontent.com/x"])
        five = {f"https://github.com/h{i}": moved(f"https://github.com/h{i + 1}") for i in range(5)}
        six = {f"https://github.com/h{i}": moved(f"https://github.com/h{i + 1}") for i in range(6)}
        rows = {
            "a redirect to a host outside hosts": ({url: moved("https://evil.example.com/x")},
                                                   url, "redirect to evil.example.com refused: not in hosts"),
            "a redirect to http": ({url: moved("http://objects.githubusercontent.com/x")}, url,
                                   "redirect to a non-https URL refused: http://objects.githubusercontent.com/x"),
            "six redirects": (dict(six, **{"https://github.com/h6": ok(b"x")}), "https://github.com/h0",
                              "more than 5 redirects: https://github.com/h0"),
            "a 404": ({}, url, f"github.com: HTTP 404: {url}"),
            "a timeout": ({url: "timeout"}, url, f"github.com: timeout after 60 s: {url}"),
        }
        for case, (routes, start, want) in rows.items():
            with self.subTest(case=case):
                with network(mod, routes) as net:
                    with self.assertRaises(err) as caught:
                        fetch(start, ALLOW)
                self.assertEqual(str(caught.exception), want)
                self.assertEqual(len(net.calls), len(set(net.calls)), "a URL was requested twice (no retry, Q61)")
        with self.subTest(case="five redirects are allowed"):
            with network(mod, dict(five, **{"https://github.com/h5": ok(b"x")})):
                self.assertEqual(stream("https://github.com/h0", ALLOW)[1], 1)
        with self.subTest(case="the first url is checked too"):
            with network(mod, {}) as net:
                with self.assertRaises(err):
                    fetch("https://evil.example.com/x", ALLOW)
                with self.assertRaises(err):
                    fetch("http://github.com/x", ALLOW)
            self.assertEqual(net.calls, [], "a refused url was requested")


# --------------------------------------------------------------------------
# Parsers (pure)
# --------------------------------------------------------------------------

class ResolverParsersTest(unittest.TestCase):

    def test_sidecar_parsers(self):
        err = rfn("ResolveError")
        p256, p1 = rfn("parse_sha256_txt"), rfn("parse_sha1")
        h = "a" * 64
        self.assertEqual(p256(f"{h}  {TEM_ASSET}\n", TEM_ASSET), h)
        self.assertEqual(p256(f"{h} {TEM_ASSET}", TEM_ASSET), h)
        for case, body in {"two lines": f"{h}  {TEM_ASSET}\n{h}  other\n", "another asset": f"{h}  other.tar.gz\n",
                           "upper-case hex": f"{h.upper()}  {TEM_ASSET}\n", "63 hex": f"{h[:63]}  {TEM_ASSET}\n",
                           "empty": ""}.items():
            with self.subTest(sha256_txt=case):
                with self.assertRaises(err):
                    p256(body, TEM_ASSET)
        s1 = "b" * 40
        self.assertEqual(p1(f"{s1}  {JAXB_JAR}\n", "javax.xml.bind:jaxb-api@2.2.12", JAXB_JAR), s1)
        self.assertEqual(p1(s1, "javax.xml.bind:jaxb-api@2.2.12", JAXB_JAR), s1)
        with self.assertRaises(err) as caught:
            p1("c" * 64, "javax.xml.bind:jaxb-api@2.2.12", JAXB_JAR)
        self.assertEqual(str(caught.exception),
                         f"maven javax.xml.bind:jaxb-api@2.2.12: {JAXB_JAR}.sha1 is not 40 hex")

    def test_uv_lock_and_pypi_json(self):
        err = rfn("ResolveError")
        uv = (ROOT / "uv.lock").read_text(encoding="utf-8")
        ver = ss.locked_version("psycopg")
        sd = rfn("uv_lock_sdist")(uv, "psycopg", ver)
        self.assertTrue(sd and re.fullmatch(r"https://files\.pythonhosted\.org/packages/.+/psycopg-[^/]+\.tar\.gz",
                                            sd["url"]), sd)
        self.assertRegex(sd["sha256"], r"^[0-9a-f]{64}$")
        self.assertIsInstance(sd["size"], int)
        self.assertIsNone(rfn("uv_lock_sdist")(uv, "pandas", "2.3.3"), "pandas is not in uv.lock (phoenix's, O2)")
        pj = rfn("pypi_json_sdist")
        self.assertEqual(pj(json.loads(pandas_json()), "pandas", "2.3.3")["url"], PANDAS_SDIST)
        for n in (0, 2):
            with self.subTest(sdists=n):
                with self.assertRaises(err) as caught:
                    pj(json.loads(pandas_json(n)), "pandas", "2.3.3")
                self.assertEqual(str(caught.exception), f"pypi pandas 2.3.3: {n} sdists, want 1")
        with self.subTest(case="an sdist off files.pythonhosted.org"):
            doc = json.loads(pandas_json())
            doc["urls"][1]["url"] = PANDAS_SDIST.replace("files.pythonhosted.org", "evil.example.com")
            with self.assertRaises(err):
                pj(doc, "pandas", "2.3.3")

    def test_release_file_and_tag(self):
        err, tag = rfn("ResolveError"), rfn("temurin_tag")
        self.assertEqual(tag(RELEASE, "21.0.12.1+1-LTS"), "jdk-21.0.12.1+1")
        with self.assertRaises(err) as caught:
            tag(RELEASE, "21.0.11+9-LTS")
        self.assertEqual(str(caught.exception), "temurin: release file says 21.0.12.1+1, SBOM says 21.0.11+9")
        with self.subTest(case="a release file without IMPLEMENTOR_VERSION"):
            with self.assertRaises(err):
                tag('JAVA_RUNTIME_VERSION="21.0.12.1+1-LTS"\n', "21.0.12.1+1-LTS")


# --------------------------------------------------------------------------
# Routes: every produced entry passes U7a's lock_problems
# --------------------------------------------------------------------------

def resolve(mod: ModuleType, needs: dict[str, Any], lock: dict[str, Any] | None = None, *, refresh: bool = False
            ) -> tuple[dict[str, Any], list[Any], list[str]]:
    uv = (ROOT / "uv.lock").read_text(encoding="utf-8")
    return mod.resolve(needs, lock or EMPTY_LOCK, policy(), uv, ARCH, refresh)


TEM_DOCS = {"ke-neo4j": [{"purl": "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS", "declared": "NOASSERTION"}]}
JAXB_DOCS = {"ke-neo4j": [{"purl": "pkg:maven/javax.xml.bind/jaxb-api@2.2.12", "declared": "GPL-2.0-only"}]}
PANDAS_DOCS = {"phoenix": [{"purl": "pkg:pypi/pandas@2.3.3", "declared": "GPL-2.0-only"}]}


class ResolverRoutesTest(unittest.TestCase):

    def test_temurin(self):
        mod = load_resolver()
        rfn("resolve")
        with network(mod, temurin_routes()):
            lock, cands, skipped = resolve(mod, {TEM_KEY: tem_need()})
        e = lock["components"][TEM_KEY]
        self.assertEqual([f["url"] for f in e["files"]], [TEM_URL], "the asset url is U7a's exact form")
        self.assertEqual(e["files"][0]["upstream"], {"alg": "sha256", "value": sha("sha256", ASSET_BODY),
                                                    "from": f"{TEM_ASSET}.sha256.txt"})
        lock_ok(self, lock, docs_for(TEM_DOCS))
        with self.subTest(case="a mismatching sidecar"):
            with network(mod, temurin_routes("f" * 64)):
                with self.assertRaises(rfn("ResolveError")) as caught:
                    resolve(mod, {TEM_KEY: tem_need()})
            self.assertIn(f"{TEM_ASSET}: sha256 mismatch: got {sha('sha256', ASSET_BODY)}, {TEM_ASSET}.sha256.txt says "
                          + "f" * 64, str(caught.exception))
        with self.subTest(case="the release file disagrees with the SBOM"):
            bad = tem_need()
            bad["route"]["sbom_version"] = "21.0.11+9-LTS"
            with network(mod, temurin_routes()) as net:
                with self.assertRaises(rfn("ResolveError")) as caught:
                    resolve(mod, {TEM_KEY: bad})
            self.assertIn("temurin: release file says 21.0.12.1+1, SBOM says 21.0.11+9", str(caught.exception))
            self.assertEqual(net.calls, [], "the tag check runs before any request")

    def test_maven(self):
        mod = load_resolver()
        with network(mod, maven_routes()):
            lock, _, _ = resolve(mod, {JAXB_KEY: need(JAXB_KEY, "ke-neo4j", "pkg:maven/javax.xml.bind/jaxb-api@2.2.12")})
        e = lock["components"][JAXB_KEY]
        self.assertEqual(e["files"][0]["upstream"], {"alg": "sha1", "value": sha("sha1", JAR_BODY),
                                                    "from": f"{JAXB_JAR}.sha1"})
        self.assertEqual(e["files"][0]["sha256"], sha("sha256", JAR_BODY))
        lock_ok(self, lock, docs_for(JAXB_DOCS))
        with self.subTest(case="a .sha1 mismatch"):
            with network(mod, maven_routes("0" * 40)):
                with self.assertRaises(rfn("ResolveError")) as caught:
                    resolve(mod, {JAXB_KEY: need(JAXB_KEY, "ke-neo4j", "pkg:maven/javax.xml.bind/jaxb-api@2.2.12")})
            self.assertIn(f"{JAXB_JAR}: sha1 mismatch: got {sha('sha1', JAR_BODY)}, {JAXB_JAR}.sha1 says " + "0" * 40,
                          str(caught.exception))

    def test_pypi(self):
        mod = load_resolver()
        ver = ss.locked_version("psycopg")
        key = f"pypi:psycopg@{ver}"
        with self.subTest(case="ke-app's from uv.lock, no request"):
            with network(mod, {}) as net:
                lock, _, _ = resolve(mod, {key: need(key, "ke-app", f"pkg:pypi/psycopg@{ver}")})
            self.assertEqual(net.calls, [], "a uv.lock package made a request (N0, ADR-KE-016 point 4)")
            self.assertEqual(lock["components"][key]["files"][0]["upstream"]["from"], "uv.lock")
            lock_ok(self, lock, docs_for({"ke-app": [{"purl": f"pkg:pypi/psycopg@{ver}", "declared": "LGPL-3.0-only"}]}))
        pkey = "pypi:pandas@2.3.3"
        json_url = "https://pypi.org/pypi/pandas/2.3.3/json"
        with self.subTest(case="phoenix's from pypi.org JSON (O2)"):
            with network(mod, {json_url: ok(pandas_json()), PANDAS_SDIST: ok(PANDAS_BODY)}) as net:
                lock, _, _ = resolve(mod, {pkey: need(pkey, "phoenix", "pkg:pypi/pandas@2.3.3")})
            self.assertEqual(net.calls, [json_url, PANDAS_SDIST])
            self.assertEqual(lock["components"][pkey]["files"][0]["upstream"],
                             {"alg": "sha256", "value": sha("sha256", PANDAS_BODY), "from": "pypi.org JSON pandas 2.3.3"})
            self.assertNotIn("pypi.org/", json.dumps(lock).replace("files.pythonhosted.org", ""),
                             "pypi.org is a resolution host only, never a lock file url (O2)")
            lock_ok(self, lock, docs_for(PANDAS_DOCS))
        with self.subTest(case="a JSON with no sdist"):
            with network(mod, {json_url: ok(pandas_json(0))}):
                with self.assertRaises(rfn("ResolveError")) as caught:
                    resolve(mod, {pkey: need(pkey, "phoenix", "pkg:pypi/pandas@2.3.3")})
            self.assertIn("pypi pandas 2.3.3: 0 sdists, want 1", str(caught.exception))
        with self.subTest(case="the sdist does not match the JSON's sha256"):
            with network(mod, {json_url: ok(pandas_json(digest="9" * 64)), PANDAS_SDIST: ok(PANDAS_BODY)}):
                with self.assertRaises(rfn("ResolveError")) as caught:
                    resolve(mod, {pkey: need(pkey, "phoenix", "pkg:pypi/pandas@2.3.3")})
            self.assertIn("pandas-2.3.3.tar.gz: sha256 mismatch", str(caught.exception))

    def test_neo4j_candidate_is_printed_never_written(self):
        mod = load_resolver()
        redirect = "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"
        with network(mod, {NEO_URL: moved(redirect), redirect: ok(NEO_BODY)}):
            lock, cands, _ = resolve(mod, {NEO_KEY: need(NEO_KEY, "ke-neo4j", "pkg:maven/org.neo4j/neo4j@5.26.32",
                                                         {"ver": "5.26.32"})})
        self.assertNotIn(NEO_KEY, lock["components"], "the TOFU entry was written (item 4: by hand only)")
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual((c["key"], c["url"], c["name"], c["sha256"], c["size"], c["host"]),
                         (NEO_KEY, NEO_URL, "5.26.32.tar.gz", sha("sha256", NEO_BODY), len(NEO_BODY), "codeload.github.com"))
        self.assertRegex(c["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("manual", c["origin"])


class ResolverMergeTest(unittest.TestCase):
    """Item 3.5 and the N5 `arches` merge."""

    def test_merge_rules(self):
        mod = load_resolver()
        manual = {"kind": "neo4j", "arches": ["amd64"], "origin": "manual", "files": [{"name": "keep-me"}]}
        old_tem = {"kind": "temurin", "arches": ["arm64"], "origin": "generated", "files": [{"name": "old"}]}
        stale_gen = {"kind": "maven", "arches": ["amd64", "arm64"], "origin": "generated", "files": []}
        stale_gen1 = {"kind": "maven", "arches": ["amd64"], "origin": "generated", "files": []}
        stale_manual = {"kind": "neo4j", "arches": ["amd64"], "origin": "manual", "files": []}
        deb_old = {"kind": "deb", "arches": ["amd64"], "origin": "generated", "files": [{"name": "deb-kept"}]}
        lock = {"format": 1, "components": {NEO_KEY: manual, TEM_KEY: old_tem, "maven:a:b@1": stale_gen,
                                            "maven:a:c@1": stale_gen1, "neo4j:neo4j@1.0": stale_manual,
                                            "deb:bash@5.2.15-2": deb_old}}
        needs = {NEO_KEY: need(NEO_KEY, "ke-neo4j", "pkg:maven/org.neo4j/neo4j@5.26.32", {"ver": "5.26.32"}),
                 TEM_KEY: tem_need(),
                 "deb:bash@5.2.15-2": need("deb:bash@5.2.15-2", "postgres", "pkg:deb/debian/bash@5.2.15-2"),
                 "deb:zlib@1:1.2.13.dfsg-1": need("deb:zlib@1:1.2.13.dfsg-1", "postgres", "pkg:deb/debian/zlib1g@1")}
        with network(mod, temurin_routes()) as net:
            new, cands, skipped = resolve(mod, needs, lock)
        comps = new["components"]
        self.assertEqual(comps[NEO_KEY], manual, "a manual entry is kept byte-identical")
        self.assertEqual(cands, [], "a needed manual entry is not fetched again")
        self.assertNotIn(NEO_URL, net.calls)
        self.assertEqual(comps[TEM_KEY]["arches"], ["amd64", "arm64"], "arches merge (N5)")
        self.assertEqual(comps["maven:a:b@1"]["arches"], ["arm64"], "an unneeded generated entry loses this arch")
        self.assertNotIn("maven:a:c@1", comps, "an entry left with no arch is removed")
        self.assertEqual(comps["neo4j:neo4j@1.0"], stale_manual, "an unneeded manual entry is kept (lock-check reports it)")
        self.assertEqual(comps["deb:bash@5.2.15-2"], deb_old, "a needed deb entry of U7c's kind is left untouched")
        self.assertIn("deb:zlib@1:1.2.13.dfsg-1", skipped, "a needed key of a kind with no route is named as skipped")
        self.assertNotIn("deb:zlib@1:1.2.13.dfsg-1", comps, "a kind with no route yet is never invented")
        with self.subTest(case="--refresh never rewrites a manual entry"):
            with network(mod, temurin_routes()) as net:
                again, cands, _ = resolve(mod, {NEO_KEY: needs[NEO_KEY]}, {"format": 1, "components": {NEO_KEY: manual}},
                                          refresh=True)
            self.assertEqual(again["components"][NEO_KEY], manual)
            self.assertEqual((net.calls, cands), ([], []), "a manual entry was fetched again on --refresh")
        with self.subTest(case="an entry for this arch is not fetched again without --refresh"):
            have = {"format": 1, "components": {TEM_KEY: dict(old_tem, arches=["amd64"])}}
            with network(mod, temurin_routes()) as net:
                again, _, _ = resolve(mod, {TEM_KEY: tem_need()}, have)
            self.assertEqual(net.calls, [])
            self.assertEqual(again["components"][TEM_KEY], have["components"][TEM_KEY])
            with network(mod, temurin_routes()) as net:
                fresh, _, _ = resolve(mod, {TEM_KEY: tem_need()}, have, refresh=True)
            self.assertTrue(net.calls, "--refresh fetches again")
            self.assertEqual(fresh["components"][TEM_KEY]["files"][0]["url"], TEM_URL)


class ResolverMainTest(unittest.TestCase):
    """The CLI: writes only <out>/lock.new.json (ruling 2), canonical text,
    exit 0/1/2/3 (item 4)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "in").mkdir()
        (self.tmp / "out").mkdir()

    def _main(self, needs: dict[str, Any], routes: dict[str, Any], *, lock: dict[str, Any] | None = None,
              args: list[str] | None = None) -> tuple[int, str, str]:
        mod = load_resolver()
        (self.tmp / "in" / "needs.json").write_text(json.dumps({"format": 1, "needs": needs}), encoding="utf-8")
        (self.tmp / "in" / "lock.json").write_text(json.dumps(lock or EMPTY_LOCK), encoding="utf-8")
        argv = args if args is not None else [
            "--needs", str(self.tmp / "in" / "needs.json"), "--lock", str(self.tmp / "in" / "lock.json"),
            "--policy", str(ROOT / "docker" / "source-policy.json"), "--uv-lock", str(ROOT / "uv.lock"),
            "--out", str(self.tmp / "out"), "--arch", ARCH]
        out, err = io.StringIO(), io.StringIO()
        with network(mod, routes), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = mod.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_writes_only_the_out_lock(self):
        code, out, err = self._main({TEM_KEY: tem_need(), JAXB_KEY: need(JAXB_KEY, "ke-neo4j",
                                                                         "pkg:maven/javax.xml.bind/jaxb-api@2.2.12")},
                                    dict(temurin_routes(), **maven_routes()))
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(os.listdir(self.tmp / "out")), ["lock.new.json"], "the resolver wrote something else")
        self.assertEqual(sorted(os.listdir(self.tmp / "in")), ["lock.json", "needs.json"], "an input was changed")
        text = (self.tmp / "out" / "lock.new.json").read_text(encoding="utf-8")
        check = load_sbom_check()
        self.assertEqual(text, check.lock_text(json.loads(text)), "lock.new.json is not canonical")

    def test_neo4j_candidate_exit_3(self):
        redirect = "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"
        code, out, err = self._main({NEO_KEY: need(NEO_KEY, "ke-neo4j", "pkg:maven/org.neo4j/neo4j@5.26.32",
                                                   {"ver": "5.26.32"})},
                                    {NEO_URL: moved(redirect), redirect: ok(NEO_BODY)})
        self.assertEqual(code, 3, err)
        lines = [ln for ln in out.splitlines() if ln.startswith("neo4j candidate: ")]
        self.assertEqual(len(lines), 1, out)
        c = json.loads(lines[0][len("neo4j candidate: "):])
        self.assertEqual(c["sha256"], sha("sha256", NEO_BODY))
        written = json.loads((self.tmp / "out" / "lock.new.json").read_text(encoding="utf-8"))
        self.assertNotIn(NEO_KEY, written["components"])

    def test_failure_writes_nothing(self):
        code, out, err = self._main({TEM_KEY: tem_need()}, temurin_routes("f" * 64))
        self.assertEqual(code, 1)
        self.assertEqual(os.listdir(self.tmp / "out"), [], "a failed run wrote into the out dir")
        lines = [ln for ln in err.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, err)
        self.assertRegex(lines[0], r"^sources_lock: FAIL \(resolve: temurin:jdk-21\.0\.12\.1\+1: "
                                   r".+ sha256 mismatch: .+; the lock is unchanged\)$")

    def test_resolver_bad_arguments_exit_2(self):
        good = ["--needs", "n", "--lock", "l", "--policy", "p", "--uv-lock", "u", "--out", str(self.tmp / "out")]
        for case, args in {"no --arch": good, "a bad arch": good + ["--arch", "x86_64"],
                           "an unknown option": good + ["--arch", ARCH, "--fake-net", "x"]}.items():
            with self.subTest(case=case):
                code, _, _ = self._main({}, {}, args=args)
                self.assertEqual(code, 2)


# --------------------------------------------------------------------------
# sbom_check.py lock-needs (item 3.3)
# --------------------------------------------------------------------------

def save_tar_with(path: Path, layers: list[dict[str, bytes]]) -> Path:
    """A `docker save` tar whose layers hold these files (bottom first)."""
    blobs, names = {}, []
    for files in layers:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        data = buf.getvalue()
        name = f"blobs/sha256/{hashlib.sha256(data).hexdigest()}"
        blobs[name] = data
        names.append(name)
    with tarfile.open(path, "w") as t:
        for name, data in list(blobs.items()) + [("manifest.json", json.dumps(
                [{"Config": "blobs/sha256/" + "c" * 64, "RepoTags": ["ke-neo4j:local"], "Layers": names}]).encode())]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return path


class LockNeedsTest(unittest.TestCase):

    def _fn(self, name: str) -> Any:
        got = getattr(load_sbom_check(), name, None)
        if not callable(got):
            raise AssertionError(f"scripts/sbom_check.py has no {name}() (U7b: lock-needs, N5 amendment U7 item 3.3)")
        return got

    def test_lock_needs_doc_on_the_fixtures(self):
        doc, problems = self._fn("lock_needs_doc")(policy(), fixture_docs(), {"ke-neo4j": RELEASE})
        self.assertEqual(problems, [])
        needs = doc["needs"]
        self.assertEqual(doc["format"], 1)
        self.assertEqual(set(needs), FIXTURE_KEYS)
        self.assertEqual(needs[TEM_KEY]["route"], {"sbom_version": "21.0.12.1+1-LTS", "release": RELEASE})
        self.assertEqual(needs[NEO_KEY]["route"], {"ver": "5.26.32"})
        self.assertEqual(needs[JAXB_KEY]["route"], {"g": "javax.xml.bind", "a": "jaxb-api", "v": "2.2.12"})
        self.assertEqual(needs["pypi:pandas@2.3.3"]["route"], {"name": "pandas", "ver": "2.3.3"})
        self.assertEqual(needs["deb:attr@1:2.5.1-4"]["route"], {"src": "attr", "ver": "1:2.5.1-4"})
        self.assertEqual(needs["apk:gcc@15.2.0-r2"]["route"], {"origin": "gcc", "ver": "15.2.0-r2"})
        self.assertEqual(len(needs[NEO_KEY]["packages"]), 73)
        with self.subTest(case="no release file for the image"):
            _, problems = self._fn("lock_needs_doc")(policy(), fixture_docs(), {})
            self.assertTrue(problems and "--tar ke-neo4j=" in problems[0], problems)

    def test_release_from_the_saved_tar(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        tar = save_tar_with(tmp / "ke-neo4j.tar", [{"opt/java/openjdk/release": b'IMPLEMENTOR_VERSION="old"\n'},
                                                   {"etc/x": b"x"},
                                                   {"opt/java/openjdk/release": RELEASE.encode()}])
        self.assertEqual(self._fn("tar_file_text")(str(tar), "opt/java/openjdk/release"), RELEASE,
                         "the top layer's copy wins")
        self.assertIsNone(self._fn("tar_file_text")(str(tar), "opt/java/openjdk/missing"))
        with self.subTest(case="the CLI"):
            for image, d in fixture_docs().items():
                ss.write_json(tmp / f"{image}.spdx.json", d)
            r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-needs",
                                "--policy", str(ROOT / "docker" / "source-policy.json"),
                                *[a for image in fixture_docs() for a in ("--sbom", f"{image}={tmp / f'{image}.spdx.json'}")],
                                "--tar", f"ke-neo4j={tar}"], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            doc = json.loads(r.stdout)
            self.assertEqual(set(doc["needs"]), FIXTURE_KEYS)
            self.assertEqual(doc["needs"][TEM_KEY]["route"]["release"], RELEASE)
            self.assertEqual(r.stdout, load_sbom_check().lock_text(doc), "needs.json is not canonical text")
            bad = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-needs",
                                  "--policy", str(ROOT / "docker" / "source-policy.json"), "--sbom", "no-equals-sign"],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(bad.returncode, 2, bad.stderr)


# --------------------------------------------------------------------------
# docker-compose.sources.yml: the `sources-resolve` service (item 3.4)
# --------------------------------------------------------------------------

def _mounts(svc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for v in svc.get("volumes") or []:
        if isinstance(v, str):
            parts = v.split(":")
            out.append({"type": "bind", "source": parts[0], "target": parts[1] if len(parts) > 1 else "",
                        "read_only": len(parts) > 2 and "ro" in parts[2].split(",")})
        else:
            out.append({"type": v.get("type", "volume"), "source": str(v.get("source", "")),
                        "target": str(v.get("target", "")), "read_only": bool(v.get("read_only"))})
    return out


def sources_compose_problems(data: Any) -> list[str]:
    svc = ((data or {}).get("services") or {}).get("sources-resolve")
    if not isinstance(svc, dict):
        return ["docker-compose.sources.yml defines no `sources-resolve` service (N5 amendment U7, item 3.4)"]
    p: list[str] = []
    if svc.get("image") != "ke-gates:${KE_IMAGE_TAG:-local}":
        p.append(f"sources-resolve: image is {svc.get('image')!r}, want the gates image ke-gates:${{KE_IMAGE_TAG:-local}}")
    if svc.get("pull_policy") != "never":
        p.append("sources-resolve: pull_policy is not never")
    if not re.fullmatch(r"\$\{KE_SOURCES_USER:\?[^}]*\}", str(svc.get("user", ""))):
        p.append("sources-resolve: user is not ${KE_SOURCES_USER:?...} (the caller's uid:gid)")
    if svc.get("read_only") is not True:
        p.append("sources-resolve: read_only is not true")
    tmpfs = [str(t).split(":", 1)[0] for t in (svc.get("tmpfs") or [])] if isinstance(svc.get("tmpfs"), list) \
        else [str(svc.get("tmpfs", "")).split(":", 1)[0]] if svc.get("tmpfs") else []
    if tmpfs != ["/tmp"]:
        p.append(f"sources-resolve: tmpfs is {tmpfs}, want exactly ['/tmp']")
    if svc.get("cap_drop") != ["ALL"]:
        p.append("sources-resolve: cap_drop is not [ALL]")
    if "cap_add" in svc or svc.get("privileged"):
        p.append("sources-resolve: adds capabilities or is privileged")
    if "no-new-privileges:true" not in [str(o).replace("=", ":") for o in svc.get("security_opt") or []]:
        p.append("sources-resolve: security_opt lacks no-new-privileges:true")
    for key in ("network_mode", "networks", "ports", "expose", "devices", "env_file", "build", "profiles", "secrets",
                "extra_hosts", "dns", "volumes_from", "pid", "ipc", "userns_mode", "restart", "container_name"):
        if key in svc:
            p.append(f"sources-resolve: sets {key} (the project default bridge is its only route; a one-shot)")
    if (data or {}).get("name"):
        p.append("docker-compose.sources.yml sets a top-level name (the run's -p must win)")
    env = svc.get("environment") or {}
    items = list(env.items()) if isinstance(env, dict) else [(str(e).split("=", 1)[0],
                                                              str(e).split("=", 1)[1] if "=" in str(e) else None)
                                                             for e in env]
    for key, value in items:
        if value is None or "$" in str(value):
            p.append(f"sources-resolve: environment {key} is passed through or interpolated (literals only)")
        if str(key).startswith(("KE_", "OPENAI", "ANTHROPIC")) or re.search(r"TOKEN|KEY|SECRET|PASSWORD", str(key)):
            p.append(f"sources-resolve: environment holds {key} (no KE_* key, model key or token; PSC-6, PSC-23)")
    mounts = _mounts(svc)
    for m in mounts:
        if "docker.sock" in m["source"] or "docker.sock" in m["target"]:
            p.append("sources-resolve: mounts the Docker socket")
    by_target = {m["target"]: m for m in mounts}
    want_ro = {"/opt/ke/sources_resolve.py": "./scripts/sources_resolve.py",
               "/opt/ke/source-policy.json": "./docker/source-policy.json", "/opt/ke/uv.lock": "./uv.lock"}
    for target, source in want_ro.items():
        m = by_target.get(target)
        if not m or m["source"] != source or not m["read_only"] or m["type"] != "bind":
            p.append(f"sources-resolve: {target} is not a read-only bind of {source}")
    m_in = by_target.get("/in")
    if not m_in or not re.fullmatch(r"\$\{KE_SOURCES_IN:\?[^}]*\}", m_in["source"]) or not m_in["read_only"]:
        p.append("sources-resolve: /in is not a read-only bind of ${KE_SOURCES_IN:?...} (needs.json, the lock copy)")
    m_out = by_target.get("/out")
    if not m_out or not re.fullmatch(r"\$\{KE_SOURCES_OUT:\?[^}]*\}", m_out["source"]):
        p.append("sources-resolve: /out is not a bind of ${KE_SOURCES_OUT:?...}")
    writable = sorted(m["target"] for m in mounts if not m["read_only"] and m["type"] != "tmpfs")
    if writable != ["/out"]:
        p.append(f"sources-resolve: writable mounts are {writable}, want only /out (ruling 2)")
    entry = svc.get("entrypoint")
    if not isinstance(entry, list) or entry[:3] != ["python3", "-I", "/opt/ke/sources_resolve.py"]:
        p.append(f"sources-resolve: entrypoint is {entry!r}, want python3 -I /opt/ke/sources_resolve.py ...")
    elif not {"/in/needs.json", "/out"} <= set(entry):
        p.append("sources-resolve: the entrypoint does not read /in/needs.json and write /out")
    return p


class SourcesComposeTest(unittest.TestCase):

    def test_sources_resolve_service_hardening(self):
        self.assertTrue(SOURCES_COMPOSE.is_file(), "docker-compose.sources.yml is missing (U7b, N5 amendment U7 item 3.4)")
        data = yaml.safe_load(SOURCES_COMPOSE.read_text(encoding="utf-8"))
        self.assertEqual(sources_compose_problems(data), [])
        self.assertEqual(sorted((data.get("services") or {})), ["sources-resolve"], "U8 adds sources-fetch, not U7b")

    def test_hardening_check_rejects_loosened_services(self):
        base = {"services": {"sources-resolve": {
            "image": "ke-gates:${KE_IMAGE_TAG:-local}", "pull_policy": "never", "user": "${KE_SOURCES_USER:?x}",
            "read_only": True, "tmpfs": ["/tmp"], "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "entrypoint": ["python3", "-I", "/opt/ke/sources_resolve.py", "--needs", "/in/needs.json", "--out", "/out"],
            "volumes": [{"type": "bind", "source": "./scripts/sources_resolve.py", "target": "/opt/ke/sources_resolve.py",
                         "read_only": True},
                        {"type": "bind", "source": "./docker/source-policy.json", "target": "/opt/ke/source-policy.json",
                         "read_only": True},
                        {"type": "bind", "source": "./uv.lock", "target": "/opt/ke/uv.lock", "read_only": True},
                        {"type": "bind", "source": "${KE_SOURCES_IN:?x}", "target": "/in", "read_only": True},
                        {"type": "bind", "source": "${KE_SOURCES_OUT:?x}", "target": "/out"}],
            "environment": {"PYTHONDONTWRITEBYTECODE": "1"}}}}
        self.assertEqual(sources_compose_problems(base), [], "the oracle's good service fails")

        def change(fn: Any) -> Any:
            d = json.loads(json.dumps(base))
            fn(d["services"]["sources-resolve"])
            return d
        bad = {
            "a KE_* key": change(lambda s: s["environment"].update(KE_MODEL_UPSTREAM="x")),
            "a passed-through key": change(lambda s: s.update(environment=["HOME"])),
            "an interpolated value": change(lambda s: s["environment"].update(X="${HOME}")),
            "a token": change(lambda s: s["environment"].update(GITHUB_TOKEN="t")),
            "host networking": change(lambda s: s.update(network_mode="host")),
            "a second network": change(lambda s: s.update(networks=["backend"])),
            "writable root": change(lambda s: s.update(read_only=False)),
            "a capability": change(lambda s: s.update(cap_add=["NET_ADMIN"])),
            "no no-new-privileges": change(lambda s: s.update(security_opt=[])),
            "the policy writable": change(lambda s: s["volumes"][1].update(read_only=False)),
            "a socket": change(lambda s: s["volumes"].append({"type": "bind", "source": "/var/run/docker.sock",
                                                              "target": "/var/run/docker.sock"})),
            "pulls": change(lambda s: s.update(pull_policy="always")),
            "root user": change(lambda s: s.update(user="0:0")),
            "an env_file": change(lambda s: s.update(env_file=[".env"])),
        }
        for case, data in bad.items():
            with self.subTest(case=case):
                self.assertNotEqual(sources_compose_problems(data), [], case)


# --------------------------------------------------------------------------
# scripts/sources_lock.sh (item 3): statically, and with the fake docker
# --------------------------------------------------------------------------

def lock_sh_static_problems(text: str) -> list[str]:
    p = []
    if not re.search(r"(?m)^set -euo pipefail$", text):
        p.append("no `set -euo pipefail`")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    i_check, i_tmp = code.find("lock-check --lock"), code.find("mktemp docker/.sources.lock.json.")
    mv = re.search(r"mv -f -- \"\$tmp\" docker/sources\.lock\.json", code)
    if not mv:
        p.append("the lock is not written by `mv -f -- \"$tmp\" docker/sources.lock.json` (a temp file in docker/)")
    if i_tmp < 0:
        p.append("no temp file `mktemp docker/.sources.lock.json.XXXXXXXX` in docker/ (item 3.6)")
    writes = [m.start() for m in re.finditer(r"(?m)^[^\n]*(?:\b(?:mv|cp)\b[^\n]*\s|>\s*)docker/sources\.lock\.json\s*$",
                                             code)]
    if len(writes) != 1:
        p.append(f"the lock is written {len(writes)} times, want once (the move of the checked temp file)")
    if i_check < 0 or any(w < i_check for w in writes) or (i_tmp >= 0 and mv and i_tmp > mv.start()):
        p.append("lock-check does not run before the lock is written")
    if not re.search(r"git diff --stat -- docker/sources\.lock\.json", code):
        p.append("no `git diff --stat -- docker/sources.lock.json` after the write")
    if not re.search(r"(?m)^\s*exit 3$", code):
        p.append("no exit 3 (written, neo4j entries pending)")
    if "run --rm --pull never sources-resolve" not in code or "-f docker-compose.sources.yml" not in code:
        p.append("the resolver is not run as `compose -f docker-compose.sources.yml run --rm --pull never sources-resolve`")
    if "run --rm --pull never sbom" not in code:
        p.append("the SBOMs are not made by the pinned `sbom` service (`run --rm --pull never sbom`)")
    for m in re.finditer(r"--env-file\s+([^\s)\"']+)", code):
        if m.group(1) != ".env.example":
            p.append(f"an --env-file other than .env.example: {m.group(1)}")
    if re.search(r"(?m)(^|\s)(-e|--env)\s", code):
        p.append("passes an environment value into a container (-e/--env)")
    if re.search(r"\bdocker\b[^\n]*\s(?:image\s+)?pull\s", code):
        p.append("pulls an image (it never pulls)")
    if "trap " not in code:
        p.append("no trap: the work dir and the compose project are not cleaned on every exit path")
    if "7 GiB" not in text:
        p.append("no 7 GiB floor check on the work dir (R6)")
    return p


def callers_of_lock_sh(files: dict[str, str]) -> list[str]:
    return [rel for rel, t in files.items() if rel != "scripts/sources_lock.sh" and "sources_lock.sh" in t
            and not rel.endswith(".py")]


class SourcesLockScriptStaticTest(unittest.TestCase):

    def test_sources_lock_sh_shape(self):
        self.assertTrue(LOCK_SH.is_file(), "scripts/sources_lock.sh is missing (U7b, N5 amendment U7 item 3)")
        self.assertEqual(lock_sh_static_problems(LOCK_SH.read_text(encoding="utf-8")), [])

    def test_never_run_by_verify_or_ci(self):
        # Ruling 4: a maintainer tool; verify.sh, the gate scripts and CI never call it.
        files = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                 for p in list((ROOT / "scripts").glob("*.sh")) + list((ROOT / ".github").rglob("*.yml"))
                 + [ROOT / "docker-compose.yml", ROOT / "docker-compose.verify.yml"] if p.is_file()}
        self.assertEqual(callers_of_lock_sh(files), [])
        self.assertTrue(callers_of_lock_sh({"scripts/verify.sh": "scripts/sources_lock.sh --arch amd64"}),
                        "the check finds a caller (control)")


class SourcesLockScriptRunTest(_BundleBase, unittest.TestCase):
    """sources_lock.sh with tests/fake_docker.py: the refusals, before any
    save, with the lock untouched (item 3.1)."""

    def setUp(self) -> None:
        super().setUp()
        self.assertTrue((self.repo / "scripts" / "sources_lock.sh").is_file(),
                        "scripts/sources_lock.sh is missing (U7b, N5 amendment U7 item 3)")
        self.lock = self.repo / "docker" / "sources.lock.json"
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text('{\n "components": {},\n "format": 1\n}\n', encoding="utf-8", newline="\n")
        self.before = self.lock.read_bytes()

    def _lock_run(self, args: tuple[str, ...], images: dict[str, Any] | None = None, **env: str
                  ) -> tuple[subprocess.CompletedProcess, list[list[str]]]:
        for f in (self.log, self.json, self.df_log):
            f.write_text("", encoding="utf-8")
        run_env = {"PATH": self.path, "HOME": str(self.tmp), "TMPDIR": str(self.tmp),
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "FAKE_DOCKER_LOG": str(self.log), "FAKE_DOCKER_JSON": str(self.json), "FAKE_DF_LOG": str(self.df_log),
                   "FAKE_COMPOSE_IMAGES": json.dumps(self.stack),
                   "FAKE_DOCKER_IMAGES": json.dumps(self._images_table(self.stack) if images is None else images)}
        run_env.update(env)
        r = subprocess.run(["bash", "scripts/sources_lock.sh", *args], env=run_env, cwd=self.repo,
                           capture_output=True, text=True, timeout=180)
        from tests import fake_docker
        return r, [rec["argv"] for rec in fake_docker.records(self.json)]

    def test_refuses_when_an_image_is_missing(self):
        table = self._images_table(self.stack)
        missing = sorted(r for r in self.stack.values() if r.split("/")[-1].startswith("ke-"))[0]
        del table[missing]
        r, calls = self._lock_run(("--arch", "amd64"), images=table)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"sources_lock: FAIL (images: {missing} not found: run scripts/build.sh first; the lock is unchanged)",
                      r.stderr)
        self.assertFalse([c for c in calls if c[:1] == ["save"] or "run" in c], f"it went on after the refusal: {calls}")
        self.assertEqual(self.lock.read_bytes(), self.before, "the lock changed")

    def test_bad_arguments_exit_2(self):
        for case, args in {"no --arch": (), "a bad arch": ("--arch", "x86_64"), "an unknown option": ("--fake-net", "x"),
                           "--arch without a value": ("--arch",)}.items():
            with self.subTest(case=case):
                r, calls = self._lock_run(args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(calls, [], "docker was called on a bad argument")
                self.assertEqual(self.lock.read_bytes(), self.before)

    def test_refuses_below_the_floor(self):
        r, calls = self._lock_run(("--arch", "amd64"), FAKE_DF_AVAIL_KB="1000")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("7 GiB", r.stderr)
        self.assertFalse([c for c in calls if c[:1] == ["save"]], "it saved an image below the floor")
        self.assertEqual(self.lock.read_bytes(), self.before)


# ==========================================================================
# U7b rework round 1 (design-notes "U7b rework round 1", orchestrator rulings
# 2026-10-25; u7b/review.md B1, B2, N1-N6; u7b/security.md M-1 = B2, L-1 = N1,
# L-2, L-3/L-4 = B1, L-5, I-1, I-3; the A34 finding, item 12). Every rule
# fails closed: a named failure, never a traceback and never a pass.
# Interface added (tester, U7b r1 RED): `DEADLINE` (600, seconds per file),
# `MAX_BYTES` (4294967296) and `ERROR_BODY_LIMIT` (1048576), module-level
# constants read when used (tests patch them); the default `OPENER`.
# ==========================================================================

MAVEN = "repo1.maven.org"
JAXB_NEED = {JAXB_KEY: need(JAXB_KEY, "ke-neo4j", "pkg:maven/javax.xml.bind/jaxb-api@2.2.12")}


class Opener:
    """A fake OPENER: url -> a zero-argument callable giving the response
    (or raising); any other url is a 404. Records each call."""

    def __init__(self, routes: dict[str, Any]):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> Any:
        self.calls.append(url)
        make = self.routes.get(url)
        if make is None:
            return SimpleNamespace(status=404, headers={}, body=[b""])
        return make()


def body_of(chunks: list[bytes], *, then: BaseException | None = None, sleep: float = 0.0,
            seen: list[bytes] | None = None) -> Any:
    """A 200 response whose body yields `chunks` (sleeping before each),
    recording each chunk handed out in `seen`, then raises `then`."""
    def gen() -> Any:
        for c in chunks:
            if sleep:
                time.sleep(sleep)
            if seen is not None:
                seen.append(c)
            yield c
        if then is not None:
            raise then
    return lambda: SimpleNamespace(status=200, headers={}, body=gen())


def raising(exc: BaseException) -> Any:
    def make() -> Any:
        raise exc
    return make


def sidecar() -> Any:
    return lambda: SimpleNamespace(status=200, headers={}, body=[f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}".encode()])


def fail_lines(err: str) -> list[str]:
    return [ln for ln in err.splitlines() if ln.strip()]


class ReworkR1TransportTest(unittest.TestCase):
    """Item 1 (B1, L-3, L-4): every error opening a URL or reading its body is
    a ResolveError with item 4's text: `<host>: timeout after <n> s: <url>`
    for timeouts, `<host>: <error class>: <url>` for the rest."""

    def _stream_error(self, routes: dict[str, Any], url: str = JAXB_URL) -> str:
        mod = load_resolver()
        with mock.patch.object(mod, "OPENER", Opener(routes)):
            with self.assertRaises(rfn("ResolveError")) as caught:
                rfn("stream")(url, ALLOW)
        return str(caught.exception)

    def test_errors_while_opening(self):
        rows = {
            "TimeoutError": (TimeoutError("timed out"), f"{MAVEN}: timeout after 60 s: {JAXB_URL}"),
            "socket.timeout": (socket.timeout("timed out"), f"{MAVEN}: timeout after 60 s: {JAXB_URL}"),
            "ConnectionResetError": (ConnectionResetError(104, "reset"), f"{MAVEN}: ConnectionResetError: {JAXB_URL}"),
            "OSError": (OSError("no route to host"), f"{MAVEN}: OSError: {JAXB_URL}"),
            "BadStatusLine": (http.client.BadStatusLine("garbage"), f"{MAVEN}: BadStatusLine: {JAXB_URL}"),
            "RemoteDisconnected": (http.client.RemoteDisconnected("closed"), f"{MAVEN}: RemoteDisconnected: {JAXB_URL}"),
            "InvalidURL": (http.client.InvalidURL("nonnumeric port"), f"{MAVEN}: InvalidURL: {JAXB_URL}"),
            "ValueError": (ValueError("bad"), f"{MAVEN}: ValueError: {JAXB_URL}"),
        }
        for case, (exc, want) in rows.items():
            with self.subTest(case=case):
                self.assertEqual(self._stream_error({JAXB_URL: raising(exc)}), want)

    def test_errors_while_reading_the_body(self):
        rows = {
            "TimeoutError mid-body": (TimeoutError("timed out"), f"{MAVEN}: timeout after 60 s: {JAXB_URL}"),
            "ConnectionResetError mid-body": (ConnectionResetError(104, "reset"),
                                              f"{MAVEN}: ConnectionResetError: {JAXB_URL}"),
            "IncompleteRead mid-body": (http.client.IncompleteRead(b"ab", 10), f"{MAVEN}: IncompleteRead: {JAXB_URL}"),
            "ValueError mid-body": (ValueError("I/O operation on closed file"), f"{MAVEN}: ValueError: {JAXB_URL}"),
        }
        for case, (exc, want) in rows.items():
            with self.subTest(case=case):
                self.assertEqual(self._stream_error({JAXB_URL: body_of([b"abc"], then=exc)}), want)
        with self.subTest(case="the host named is the hop's, after a redirect"):
            hop = "https://objects.githubusercontent.com/x"
            got = self._stream_error({"https://github.com/a/b": lambda: SimpleNamespace(
                status=302, headers={"location": hop}, body=[b""]), hop: body_of([b"abc"], then=TimeoutError())},
                url="https://github.com/a/b")
            self.assertEqual(got, f"objects.githubusercontent.com: timeout after 60 s: {hop}")

    def test_the_deadline(self):
        mod = load_resolver()
        self.assertEqual(getattr(mod, "DEADLINE", None), 600, "600 s per file (item 1)")
        with mock.patch.object(mod, "DEADLINE", 1, create=True):
            got = self._stream_error({JAXB_URL: body_of([b"a", b"b", b"c"], sleep=0.6)})
        self.assertEqual(got, f"{MAVEN}: deadline 1 s passed: {JAXB_URL}")
        with self.subTest(case="a body inside the deadline streams"):
            with mock.patch.object(mod, "DEADLINE", 30, create=True), mock.patch.object(
                    mod, "OPENER", Opener({JAXB_URL: body_of([b"ab", b"c"])})):
                self.assertEqual(rfn("stream")(JAXB_URL, ALLOW)[1], 3)

    def test_the_byte_cap(self):
        mod = load_resolver()
        self.assertEqual(getattr(mod, "MAX_BYTES", None), 4294967296, "4 GiB, as U7a round 1 item 10")
        seen: list[bytes] = []
        with mock.patch.object(mod, "MAX_BYTES", 10, create=True):
            got = self._stream_error({JAXB_URL: body_of([b"x" * 6] * 4, seen=seen)})
        self.assertEqual(got, f"{MAVEN}: more than 10 bytes: {JAXB_URL}")
        self.assertEqual(len(seen), 2, "the read went on past the cap")
        with self.subTest(case="exactly the cap is allowed"):
            with mock.patch.object(mod, "MAX_BYTES", 10, create=True), mock.patch.object(
                    mod, "OPENER", Opener({JAXB_URL: body_of([b"x" * 5] * 2)})):
                self.assertEqual(rfn("stream")(JAXB_URL, ALLOW)[1], 10)


def run_main(tmp: Path, needs: Any, opener: Any, *, out: Path | None = None, raw_needs: str | None = None
             ) -> tuple[Any, str, str]:
    """`main` on needs.json and an empty lock in `tmp/in`, with `opener`;
    (exit code, or "raised ..." for any escape; stdout; stderr)."""
    mod = load_resolver()
    (tmp / "in").mkdir(exist_ok=True)
    (tmp / "out").mkdir(exist_ok=True)
    (tmp / "in" / "needs.json").write_text(raw_needs if raw_needs is not None else json.dumps(
        {"format": 1, "needs": needs}), encoding="utf-8")
    (tmp / "in" / "lock.json").write_text(json.dumps(EMPTY_LOCK), encoding="utf-8")
    argv = ["--needs", str(tmp / "in" / "needs.json"), "--lock", str(tmp / "in" / "lock.json"),
            "--policy", str(ROOT / "docker" / "source-policy.json"), "--uv-lock", str(ROOT / "uv.lock"),
            "--out", str(out or tmp / "out"), "--arch", ARCH]
    o, e = io.StringIO(), io.StringIO()
    with mock.patch.object(mod, "OPENER", opener), contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        try:
            code: Any = mod.main(argv)
        except BaseException as exc:  # noqa: BLE001 - the finding is any escape
            code = f"raised {type(exc).__name__}: {exc}"
    return code, o.getvalue(), e.getvalue()


class ReworkR1MainTest(unittest.TestCase):
    """Item 1, `main` (N6): every exception is the one line `sources_lock:
    FAIL (resolve: <key or "-">: <message>; the lock is unchanged)`, exit 1,
    no traceback, and no lock.new.json."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "in").mkdir()
        (self.tmp / "out").mkdir()

    def _main_with(self, needs: Any, opener: Any, *, out: Path | None = None, raw_needs: str | None = None
                   ) -> tuple[Any, str, str]:
        return run_main(self.tmp, needs, opener, out=out, raw_needs=raw_needs)

    def _one_fail_line(self, got: tuple[Any, str, str], start: str) -> None:
        code, _, err = got
        self.assertEqual(code, 1, err[-800:])
        self.assertNotIn("Traceback", err)
        lines = fail_lines(err)
        self.assertEqual(len(lines), 1, err[-800:])
        self.assertTrue(lines[0].startswith(start) and lines[0].endswith("; the lock is unchanged)"), lines[0])
        self.assertNotIn("lock.new.json", os.listdir(self.tmp / "out"))

    def test_a_body_error_is_one_fail_line(self):
        got = self._main_with(JAXB_NEED, Opener({JAXB_URL + ".sha1": sidecar(),
                                                 JAXB_URL: body_of([b"abc"], then=http.client.IncompleteRead(b"a"))}))
        self._one_fail_line(got, "sources_lock: FAIL (resolve: ")
        self.assertEqual(fail_lines(got[2])[0], f"sources_lock: FAIL (resolve: {JAXB_KEY}: {MAVEN}: IncompleteRead: "
                                               f"{JAXB_URL}; the lock is unchanged)")
        for case, exc, word in (("a mid-body timeout", TimeoutError(), "timeout after 60 s"),
                                ("an InvalidURL at open", http.client.InvalidURL("x"), "InvalidURL")):
            with self.subTest(case=case):
                make = body_of([b"abc"], then=exc) if "body" in case else raising(exc)
                got = self._main_with(JAXB_NEED, Opener({JAXB_URL + ".sha1": sidecar(), JAXB_URL: make}))
                self._one_fail_line(got, f"sources_lock: FAIL (resolve: {JAXB_KEY}: {MAVEN}: {word}")

    def test_an_error_writing_out_is_one_fail_line(self):
        got = self._main_with({}, Opener({}), out=self.tmp / "no-such-dir")
        self._one_fail_line(got, "sources_lock: FAIL (resolve: ")

    def test_wrong_typed_needs_are_one_fail_line(self):
        rows = {
            "an entry that is a string": ({TEM_KEY: "x"}, None, f"sources_lock: FAIL (resolve: {TEM_KEY}: "),
            "a route that is a string": ({TEM_KEY: {"kind": "temurin", "packages": [], "route": "x"}}, None,
                                         f"sources_lock: FAIL (resolve: {TEM_KEY}: "),
            "needs that is a list": (None, json.dumps({"format": 1, "needs": [1, 2]}), "sources_lock: FAIL (resolve: "),
            "a needs.json that is a list": (None, "[]", "sources_lock: FAIL (resolve: "),
        }
        for case, (needs, raw, start) in rows.items():
            with self.subTest(case=case):
                net = Opener({})
                self._one_fail_line(self._main_with(needs, net, raw_needs=raw), start)
                self.assertEqual(net.calls, [], "a request was made for a malformed needs entry")


class ReworkR1RealOpenerTest(unittest.TestCase):
    """Item 10 (security I-1): the real opener reads a 3xx or 4xx body only up
    to 1 MiB (ERROR_BODY_LIMIT) and discards it. The network is never used:
    urllib's build_opener is replaced by one whose open raises the HTTPError."""

    def _fresh(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location("ke_sources_resolve_real_opener", RESOLVER)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_error_bodies_are_read_to_1_mib_only(self):
        mod = self._fresh()
        self.assertEqual(getattr(mod, "ERROR_BODY_LIMIT", None), 1048576, "the I-1 limit constant")
        for status in (302, 404):
            with self.subTest(status=status):
                fp = io.BytesIO(b"x" * (3 << 20))
                hdrs = email.message.Message()
                hdrs["Location"] = "https://objects.githubusercontent.com/x"
                err = urllib.error.HTTPError(JAXB_URL, status, "status", hdrs, fp)
                fake = SimpleNamespace(open=mock.Mock(side_effect=err))
                with mock.patch("urllib.request.build_opener", return_value=fake):
                    r = mod.OPENER(JAXB_URL, 5)
                self.assertEqual(r.status, status)
                self.assertLessEqual(fp.tell(), 1048576, "more than 1 MiB of an error body was read (I-1)")
                self.assertLessEqual(sum(len(c) for c in r.body), 1048576)
                if status == 302:
                    self.assertEqual({k.lower(): v for k, v in r.headers.items()}.get("location"),
                                     "https://objects.githubusercontent.com/x")


class ReworkR1HopRulesTest(unittest.TestCase):
    """Item 3 (N1, L-1): every redirect hop, once joined, is refused unless it
    is printable, a literal lower-case `https://`, with no userinfo, port or
    fragment, a plain path with no `%`, and its host in `hosts`. A hop may
    carry a query (signed release-asset URLs). The resolver's own first URLs
    pass every rule but the path `%` one (their fixed encodings)."""

    BASE = "https://repo1.maven.org/maven2/a.jar"

    def test_bad_hops_are_refused_and_never_requested(self):
        mod = load_resolver()
        err = rfn("ResolveError")
        bad = {
            "a port": "https://repo1.maven.org:8443/x.jar",
            "an empty port": "https://repo1.maven.org:/x.jar",
            "userinfo": "https://user:pw@repo1.maven.org/x.jar",
            "a user only": "https://user@repo1.maven.org/x.jar",
            "a fragment": "https://repo1.maven.org/x.jar#f",
            "an encoded dot segment": "https://repo1.maven.org/a/%2e%2e/x.jar",
            "a percent in the path": "https://repo1.maven.org/a%2Fb.jar",
            "a dot segment": "https://repo1.maven.org/a/../x.jar",
            "an empty segment": "https://repo1.maven.org/a//x.jar",
            "a backslash": "https://repo1.maven.org/a" + chr(92) + "x.jar",
            "a tab": "https://repo1.maven.org/a" + chr(9) + "x.jar",
            "a space": "https://repo1.maven.org/a x.jar",
            "non-ASCII": "https://repo1.maven.org/" + chr(233) + ".jar",
            "an upper-case scheme": "HTTPS://repo1.maven.org/x.jar",
        }
        for case, loc in bad.items():
            with self.subTest(case=case):
                with network(mod, {self.BASE: moved(loc), urljoin(self.BASE, loc): ok(JAR_BODY)}) as net:
                    with self.assertRaises(err) as caught:
                        rfn("stream")(self.BASE, ALLOW)
                self.assertTrue(str(caught.exception).startswith("redirect to ")
                                and "refused" in str(caught.exception), str(caught.exception))
                self.assertEqual(net.calls, [self.BASE], "a refused hop was requested")

    def test_a_hop_may_carry_a_query(self):
        mod = load_resolver()
        hop = "https://release-assets.githubusercontent.com/github-production-release-asset/1/a?sp=r&sig=abc&se=1"
        with network(mod, {TEM_URL: moved(hop), hop: ok(ASSET_BODY)}) as net:
            digests, size = rfn("stream")(TEM_URL, ALLOW)
        self.assertEqual((digests["sha256"], size), (sha("sha256", ASSET_BODY), len(ASSET_BODY)))
        self.assertEqual(net.calls, [TEM_URL, hop])

    def test_the_first_url(self):
        mod = load_resolver()
        err = rfn("ResolveError")
        for case, url in {"a port": "https://repo1.maven.org:8443/x.jar",
                          "userinfo": "https://user:pw@repo1.maven.org/x.jar",
                          "a fragment": "https://repo1.maven.org/x.jar#f",
                          "a backslash": "https://repo1.maven.org/a" + chr(92) + "x.jar",
                          "a tab": "https://repo1.maven.org/a" + chr(9) + "x.jar",
                          "an upper-case scheme": "HTTPS://repo1.maven.org/x.jar"}.items():
            with self.subTest(case=case):
                with network(mod, {url: ok(JAR_BODY)}) as net:
                    with self.assertRaises(err):
                        rfn("fetch")(url, ALLOW)
                self.assertEqual(net.calls, [], "a refused first url was requested")
        with self.subTest(case="a first url keeps its own percent-encoding (GitLab, snapshot)"):
            url = "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/x"
            with network(mod, {url: ok(b"x")}) as net:
                rfn("stream")(url, ALLOW | {"gitlab.alpinelinux.org"})
            self.assertEqual(net.calls, [url])


class ReworkR1PypiScopeTest(unittest.TestCase):
    """Item 8 (security L-2): `pypi.org` only for the pypi JSON request; every
    other request, and every redirect hop of every request, uses the policy
    `hosts` alone."""

    def test_a_maven_redirect_to_pypi_org_is_refused(self):
        mod = load_resolver()
        to = "https://pypi.org/x.jar"
        with network(mod, dict(maven_routes(), **{JAXB_URL: moved(to), to: ok(JAR_BODY)})) as net:
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(mod, JAXB_NEED)
        self.assertIn("redirect to pypi.org refused: not in hosts", str(caught.exception))
        self.assertNotIn(to, net.calls)

    def test_a_redirect_of_the_json_request_to_pypi_org_is_refused(self):
        mod = load_resolver()
        key = "pypi:pandas@2.3.3"
        url = "https://pypi.org/pypi/pandas/2.3.3/json"
        to = "https://pypi.org/pypi/pandas/json"
        with network(mod, {url: moved(to), to: ok(pandas_json()), PANDAS_SDIST: ok(PANDAS_BODY)}) as net:
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(mod, {key: need(key, "phoenix", "pkg:pypi/pandas@2.3.3", {"name": "pandas", "ver": "2.3.3"})})
        self.assertIn("redirect to pypi.org refused: not in hosts", str(caught.exception))
        self.assertEqual(net.calls, [url])

    def test_the_json_request_itself_is_allowed(self):
        mod = load_resolver()
        key = "pypi:pandas@2.3.3"
        with network(mod, {"https://pypi.org/pypi/pandas/2.3.3/json": ok(pandas_json()),
                           PANDAS_SDIST: ok(PANDAS_BODY)}):
            lock, _, _ = resolve(mod, {key: need(key, "phoenix", "pkg:pypi/pandas@2.3.3",
                                                 {"name": "pandas", "ver": "2.3.3"})})
        self.assertIn(key, lock["components"])


class ReworkR1KeysTest(unittest.TestCase):
    """Item 11 (security I-3): each needs key is checked against U7a's key
    grammar for its kind before any URL is built: `<key>: not a valid lock
    key`, no request, the run ends with item 1's line."""

    BAD = ("temurin:jdk-21.0.12.1+1/../../x", "maven:javax.xml.bind:jaxb-api@2.2.12/../../x", "maven:g@1",
           "pypi:Pandas@2.3.3", "pypi:pandas@2.3.3/../../x", "neo4j:neo4j@5.26.32/../x", "neo4j:other@5.26.32",
           "deb:../x@1", "deb:libpq5@17.6-1.pgdg120+1", "apk:x@1", "pgdg:bash@5.2.15-2", "rpm:x@1.0")

    def test_bad_keys_are_refused_before_any_request(self):
        mod = load_resolver()
        for key in self.BAD:
            with self.subTest(key=key):
                with network(mod, {}) as net:
                    with self.assertRaises(rfn("ResolveError")) as caught:
                        resolve(mod, {key: need(key, "ke-neo4j", "pkg:generic/x@1")})
                self.assertEqual(str(caught.exception), f"{key}: not a valid lock key")
                self.assertEqual(net.calls, [], "a request was made for a bad key")

    def test_the_main_line(self):
        key = "maven:javax.xml.bind:jaxb-api@2.2.12/../../x"
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        net = Opener({})
        code, _, err = run_main(tmp, {key: need(key, "ke-neo4j", "pkg:generic/x@1")}, net)
        self.assertEqual(net.calls, [])
        self.assertEqual(code, 1, err)
        self.assertEqual(fail_lines(err), [f"sources_lock: FAIL (resolve: {key}: not a valid lock key; "
                                           "the lock is unchanged)"])


# --------------------------------------------------------------------------
# sources_lock.sh end to end with tests/fake_docker.py (items 2, 4, 5, 6, 9,
# 12): save, sbom, lock-needs, resolve, lock-check --pending-neo4j, chmod
# 0644, the temp-file move, `git diff --stat`; exit 0 and 3.
# --------------------------------------------------------------------------

SOURCES_YML = "docker-compose.sources.yml"
HAPPY_ROWS: dict[str, list[dict[str, Any]]] = {
    "postgres": [{"purl": ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"), "declared": "GPL-3.0-or-later"}],
    "valkey": [{"purl": "pkg:apk/alpine/readline@8.2.13-r1?arch=x86_64&distro=alpine-3.23.3",
                "declared": "GPL-3.0-or-later"}],
    "ke-neo4j": [{"purl": "pkg:maven/javax.xml.bind/jaxb-api@2.2.12", "declared": "GPL-2.0-only"}],
    "ke-app": [{"purl": "pkg:pypi/psycopg@3.3.6", "declared": "LGPL-3.0-only"}],
    "ke-gateway": [],
    "phoenix": [],
}
HAPPY_KEYS = {"deb:bash@5.2.15-2", "apk:readline@8.2.13-r1", JAXB_KEY, "pypi:psycopg@3.3.6"}
NEO_ROW = {"purl": "pkg:maven/org.neo4j/neo4j@5.26.32", "declared": "GPL-3.0-only"}


def with_rows(extra: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {img: rows + extra.get(img, []) for img, rows in HAPPY_ROWS.items()}


class ReworkR1LockScriptRunTest(_BundleBase, unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        for rel in ("docker/source-policy.json", SOURCES_YML):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.repo / rel)
        self.lock = self.repo / "docker" / "sources.lock.json"
        self.check = load_sbom_check()
        self.syft_log = self.tmp / "syft.jsonl"
        self.resolve_log = self.tmp / "resolve.log"

    def _commit_lock(self, rows: dict[str, list[dict[str, Any]]], drop: frozenset[str] | set[str] = frozenset()
                     ) -> tuple[dict[str, Any], dict[str, Any], bytes]:
        """(the lock, the docs, the committed bytes): a valid lock for `rows`
        without `drop`, committed in a non-canonical layout so the rewrite
        shows in `git diff --stat`."""
        docs = {img: ss.spdx_doc(img, r) for img, r in rows.items()}
        needs, problems = self.check.lock_needs(policy(), docs)
        self.assertEqual(problems, [], "fixture: every row maps to a lock key")
        lock = good_lock(set(needs) - drop)
        if not drop:
            self.assertEqual(self.check.lock_problems(self.check.lock_text(lock), policy(), docs, ARCH), [],
                             "fixture: the committed lock is complete")
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "lock")
        return lock, docs, self.lock.read_bytes()

    def _run(self, docs: dict[str, Any], *, net: dict[str, Any] | None = None, stack: dict[str, str] | None = None,
             path: str | None = None, args: tuple[str, ...] = ("--arch", "amd64")
             ) -> tuple[subprocess.CompletedProcess, list[list[str]]]:
        for f in (self.log, self.json, self.df_log, self.syft_log, self.resolve_log):
            f.write_text("", encoding="utf-8")
        stack = self.stack if stack is None else stack
        env = {"PATH": path or self.path, "HOME": str(self.tmp), "TMPDIR": str(self.tmp),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "FAKE_DOCKER_LOG": str(self.log), "FAKE_DOCKER_JSON": str(self.json), "FAKE_DF_LOG": str(self.df_log),
               "FAKE_COMPOSE_IMAGES": json.dumps(stack),
               "FAKE_DOCKER_IMAGES": json.dumps(self._images_table(stack)),
               "FAKE_COMPOSE_FILE_IMAGES": json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": self.sbom_ref},
                                                       SOURCES_YML: {"sources-resolve": "ke-gates:local"}}),
               "FAKE_COMPOSE_FILE_REQUIRED": json.dumps({cs.SBOM_COMPOSE_NAME: self.sbom_required,
                                                         SOURCES_YML: ["KE_SOURCES_IN", "KE_SOURCES_OUT",
                                                                       "KE_SOURCES_USER"]}),
               "FAKE_DOCKER_SAVE_TAR": "oci",
               "FAKE_IMAGE_PATHS": json.dumps({"/opt/venv": str(self.venv)}),
               "FAKE_SYFT_RAW": json.dumps({img: json.dumps(doc) for img, doc in docs.items()}),
               "FAKE_SYFT_LOG": str(self.syft_log),
               "FAKE_RESOLVE_NET": json.dumps(net or {}), "FAKE_RESOLVE_LOG": str(self.resolve_log)}
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        r = subprocess.run([str(bash), "scripts/sources_lock.sh", *args], env=env, cwd=self.repo,
                           capture_output=True, text=True, timeout=300)
        return r, [rec["argv"] for rec in fake_docker.records(self.json)]

    @staticmethod
    def _steps(calls: list[list[str]]) -> list[tuple[str, list[str]]]:
        out = []
        for c in calls:
            if c[:1] == ["save"]:
                out.append(("save", c))
            elif c[:1] == ["compose"] and "run" in c and cs.SBOM_COMPOSE_NAME in c:
                out.append(("sbom", c))
            elif c[:1] == ["compose"] and "run" in c and SOURCES_YML in c:
                out.append(("resolve", c))
            elif c[:1] == ["run"] and "lock-needs" in c:
                out.append(("lock-needs", c))
            elif c[:1] == ["run"] and "lock-check" in c:
                out.append(("lock-check", c))
        return out

    def _temps(self) -> list[str]:
        return sorted(p.name for p in (self.repo / "docker").iterdir() if p.name.startswith(".sources.lock.json."))

    def _assert_written(self, r: subprocess.CompletedProcess, calls: list[list[str]], lock: dict[str, Any]) -> None:
        self.assertEqual(self.lock.read_text(encoding="utf-8"), self.check.lock_text(lock),
                         "the lock written is not the resolver's canonical lock.new.json")
        self.assertEqual(stat.S_IMODE(self.lock.stat().st_mode), 0o644, "item 9: chmod 0644 before the mv")
        self.assertEqual(self._temps(), [], "a temp lock file was left in docker/")
        self.assertIn("docker/sources.lock.json", r.stdout, "no `git diff --stat` output")
        self.assertIn("1 file changed", r.stdout, "no `git diff --stat` output")
        steps = self._steps(calls)
        names = [n for n, _ in steps]
        self.assertEqual((names.count("save"), names.count("sbom")), (6, 6), names)
        self.assertEqual(names[12:], ["lock-needs", "resolve", "lock-check"], names)
        self.assertEqual(set(names[:12]), {"save", "sbom"}, names)
        needs_call = steps[12][1]
        self.assertIn("ke-neo4j=/tars/ke-neo4j.tar", needs_call, "lock-needs reads ke-neo4j's saved tar")
        self.assertIn("--pending-neo4j", steps[14][1], "item 2: lock-check decides pending")
        syft = [json.loads(ln) for ln in self.syft_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(syft), 6)
        self.assertTrue(all(s["tmp_entries"] is not None for s in syft), "item 12: <work>/sboms/tmp before syft")

    def test_happy_path_exit_0(self):
        lock, docs, _ = self._commit_lock(HAPPY_ROWS)
        self.assertEqual(set(lock["components"]), HAPPY_KEYS, "fixture")
        r, calls = self._run(docs)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        self._assert_written(r, calls, lock)
        self.assertEqual(self.resolve_log.read_text(encoding="utf-8"), "", "a complete lock needs no request")

    def test_neo4j_pending_exit_3(self):
        lock, docs, _ = self._commit_lock(with_rows({"ke-neo4j": [NEO_ROW]}), drop={NEO_KEY})
        self.assertEqual(set(lock["components"]), HAPPY_KEYS, "fixture")
        r, calls = self._run(docs, net={NEO_URL: [200, {}, NEO_BODY.decode()]})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr[-3000:])
        self._assert_written(r, calls, lock)
        self.assertIn("neo4j candidate: ", r.stdout)
        self.assertIn(NEO_URL, self.resolve_log.read_text(encoding="utf-8"))

    def test_a_truncated_neo4j_list_is_not_pending(self):
        """B2 / M-1 end to end: more than 20 neo4j misses print first and hide
        a later non-neo4j miss; the script must fail, lock untouched."""
        neo = [NEO_ROW] + [{"purl": f"pkg:maven/org.neo4j/neo4j-part{i:02d}@5.26.32", "declared": "GPL-3.0-only"}
                           for i in range(24)]
        pg = {"purl": ss.deb("libpq5", "17.6-1.pgdg120+1"), "declared": "GPL-2.0-only"}
        rows = with_rows({"ke-neo4j": neo, "postgres": [pg]})
        docs = {img: ss.spdx_doc(img, r) for img, r in rows.items()}
        pg_keys = {k for k in self.check.lock_needs(policy(), docs)[0] if k.startswith("pgdg:")}
        self.assertEqual(len(pg_keys), 1, "fixture: one pgdg key")
        lock, docs, before = self._commit_lock(rows, drop={NEO_KEY} | pg_keys)
        problems = self.check.lock_problems(self.check.lock_text(lock), policy(), docs, ARCH)
        self.assertGreater(len(problems), 20, "fixture")
        self.assertTrue(all(f"the lock has no {NEO_KEY} for" in x for x in problems[:20]), "fixture")
        self.assertIn("the lock has no pgdg:", problems[-1], "fixture")
        r, _ = self._run(docs, net={NEO_URL: [200, {}, NEO_BODY.decode()]})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
        self.assertIn("sources_lock: FAIL (check: ", r.stderr)
        self.assertEqual(self.lock.read_bytes(), before, "the lock changed")
        self.assertEqual(self._temps(), [])

    def test_tools_first(self):
        self._commit_lock(HAPPY_ROWS)
        before = self.lock.read_bytes()
        found = {t: shutil.which(t) for t in ("jq", "git", "dirname")}
        self.assertTrue(all(found.values()), f"fixture: tools on this PATH: {found}")
        found["docker"] = str(self.tmp / "fakebin" / "docker")
        for tool in ("jq", "git", "docker"):
            with self.subTest(tool=tool):
                bindir = self.tmp / f"tools-without-{tool}"
                bindir.mkdir()
                for name, src in found.items():
                    if name != tool:
                        os.symlink(str(src), bindir / name)
                r, calls = self._run({}, path=str(bindir))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(f"sources_lock: FAIL (tools: {tool} not on PATH; the lock is unchanged)",
                              r.stderr.splitlines())
                self.assertEqual(calls, [], "docker was called before the tools check")
                self.assertEqual(self.lock.read_bytes(), before)

    def test_exactly_the_six_images(self):
        self._commit_lock(HAPPY_ROWS)
        before = self.lock.read_bytes()
        extra = dict(self.stack, redis="redis:7-alpine@sha256:" + "a" * 64)
        missing = {svc: ref for svc, ref in self.stack.items() if not ref.startswith("valkey/")}
        self.assertEqual(len(missing), len(self.stack) - 1, "fixture: one valkey service")
        for case, stack, name in (("an extra image", extra, "redis"), ("a missing image", missing, "valkey")):
            with self.subTest(case=case):
                r, calls = self._run({}, stack=stack)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                lines = [ln for ln in r.stderr.splitlines() if ln.startswith("sources_lock: FAIL (images: ")
                         and ln.endswith("; the lock is unchanged)")]
                self.assertTrue(lines and name in lines[0], r.stderr)
                self.assertFalse([c for c in calls if c[:1] == ["save"]], "it saved an image")
                self.assertEqual(self.lock.read_bytes(), before)

    def test_the_temp_file_is_removed_on_failure(self):
        lock, docs, before = self._commit_lock(HAPPY_ROWS)
        for tool in ("chmod", "mv"):
            with self.subTest(tool=tool):
                real = shutil.which(tool)
                self.assertIsNotNone(real)
                shims = self.tmp / f"shim-{tool}"
                shims.mkdir()
                log = self.tmp / f"shim-{tool}.log"
                (shims / tool).write_text(
                    "#!/bin/sh\n"
                    "for a in \"$@\"; do\n"
                    "  case \"$a\" in\n"
                    f"    *.sources.lock.json.*) echo \"$a\" >> '{log}'; echo '{tool}: injected failure' >&2; exit 1 ;;\n"
                    "  esac\n"
                    "done\n"
                    f"exec '{real}' \"$@\"\n", encoding="utf-8", newline="\n")
                (shims / tool).chmod(0o755)
                r, _ = self._run(docs, path=f"{shims}{os.pathsep}{self.path}")
                self.assertTrue(log.is_file() and log.read_text(encoding="utf-8").strip(),
                                f"the script never ran {tool} on its temp file: " + r.stderr[-2000:])
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self._temps(), [], "item 5: the EXIT trap removes the temp lock file")
                self.assertEqual(self.lock.read_bytes(), before, "the lock changed")

    def test_the_neo4j_tar_is_not_a_literal(self):
        self.assertNotIn("ke-neo4j.tar", LOCK_SH.read_text(encoding="utf-8"),
                         "item 6 (N4): the ke-neo4j tar path is derived from the image list")


if __name__ == "__main__":
    unittest.main()
