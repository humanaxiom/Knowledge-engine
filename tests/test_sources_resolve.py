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

import base64
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
import ssl
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
from urllib.parse import quote, unquote, urljoin

import yaml

from tests import compose_support as cs
from tests import fake_docker
from tests import sbom_support as ss
from tests.engine_support import ROOT
from tests.test_offline_bundle import _BundleBase
from tests.test_sbom_bundle import load_sbom_check
from tests.test_sources_lock import FIXTURE_KEYS, fixture_docs, good_entry, good_lock, policy

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
PGDG_KEY = "pgdg:postgresql-common@293.pgdg12+1"


def aports_commit(origin: str, ver: str) -> str:
    """A synthetic aports commit, one per origin@ver (U7c A1 fixtures)."""
    return hashlib.sha1(f"aports {origin}@{ver}".encode()).hexdigest()


def apk_inputs(docs: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Per Alpine image of `docs`, what lock-needs reads from its saved tar
    (U7c A1): a `lib/apk/db/installed` with one stanza per apk purl (`o:` the
    purl's origin, `c:` aports_commit) and `etc/alpine-release` from the purl
    `distro`."""
    out: dict[str, dict[str, str]] = {}
    for image, doc in docs.items():
        stanzas, release = [], ""
        for p in doc.get("packages") or []:
            for ref in p.get("externalRefs") or []:
                purl = str(ref.get("referenceLocator", ""))
                if not purl.startswith("pkg:apk/alpine/"):
                    continue
                body, _, q = purl.partition("?")
                name, _, ver = body[len("pkg:apk/alpine/"):].rpartition("@")
                name, ver = unquote(name), unquote(ver)
                quals = {k: unquote(v) for k, _, v in (x.partition("=") for x in q.split("&") if x)}
                origin = quals.get("upstream", name).split("@", 1)[0]
                release = quals.get("distro", "alpine-").split("-", 1)[1]
                stanzas.append(f"C:Q1fake=\nP:{name}\nV:{ver}\nA:x86_64\no:{origin}\nc:{aports_commit(origin, ver)}\n")
        if stanzas:
            out[image] = {"installed": "\n".join(stanzas), "release": release + "\n"}
    return out


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
    # U7d R4: the retry waits go through the module's SLEEP; route tests never wait,
    # and their retry lines are not printed.
    with mock.patch.object(mod, "SLEEP", lambda s: None, create=True), contextlib.redirect_stderr(io.StringIO()):
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
                 # U7d (A71): pgdg has a route now, so no kind is left without one; the
                 # "no route" rows (deb:zlib until U7b, pgdg until U7d) are gone.
                 }
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
        self.assertEqual(skipped, [], "U7d: every kind has a route")
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
        # U7c A1 (design-notes "U7c precision"): the apk route adds commit and
        # branch, read from each Alpine image's tar (the `apk` argument).
        doc, problems = self._fn("lock_needs_doc")(policy(), fixture_docs(), {"ke-neo4j": RELEASE},
                                                   apk_inputs(fixture_docs()))
        self.assertEqual(problems, [])
        needs = doc["needs"]
        self.assertEqual(doc["format"], 1)
        self.assertEqual(set(needs), FIXTURE_KEYS)
        self.assertEqual(needs[TEM_KEY]["route"], {"sbom_version": "21.0.12.1+1-LTS", "release": RELEASE})
        self.assertEqual(needs[NEO_KEY]["route"], {"ver": "5.26.32"})
        self.assertEqual(needs[JAXB_KEY]["route"], {"g": "javax.xml.bind", "a": "jaxb-api", "v": "2.2.12"})
        self.assertEqual(needs["pypi:pandas@2.3.3"]["route"], {"name": "pandas", "ver": "2.3.3"})
        self.assertEqual(needs["deb:attr@1:2.5.1-4"]["route"], {"src": "attr", "ver": "1:2.5.1-4"})
        self.assertEqual(needs["apk:gcc@15.2.0-r2"]["route"], {"origin": "gcc", "ver": "15.2.0-r2",
                                                               "commit": aports_commit("gcc", "15.2.0-r2"),
                                                               "branch": "v3.23"})
        self.assertEqual(len(needs[NEO_KEY]["packages"]), 73)
        with self.subTest(case="no release file for the image"):
            _, problems = self._fn("lock_needs_doc")(policy(), fixture_docs(), {}, apk_inputs(fixture_docs()))
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
            # U7c A1: the Alpine images' tars carry the installed db and alpine-release.
            alpine = [a for image, inp in apk_inputs(fixture_docs()).items()
                      for a in ("--tar", "{}={}".format(image, save_tar_with(tmp / f"{image}.tar", [
                          {"lib/apk/db/installed": inp["installed"].encode(),
                           "etc/alpine-release": inp["release"].encode()}])))]
            r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-needs",
                                "--policy", str(ROOT / "docker" / "source-policy.json"),
                                *[a for image in fixture_docs() for a in ("--sbom", f"{image}={tmp / f'{image}.spdx.json'}")],
                                "--tar", f"ke-neo4j={tar}", *alpine], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            doc = json.loads(r.stdout)
            self.assertEqual(set(doc["needs"]), FIXTURE_KEYS)
            self.assertEqual(doc["needs"][TEM_KEY]["route"]["release"], RELEASE)
            self.assertEqual(doc["needs"]["apk:gcc@15.2.0-r2"]["route"]["commit"], aports_commit("gcc", "15.2.0-r2"),
                             "U7c A1: the apk commit comes from the image's saved tar")
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
        # Re-pinned by the tester, U8b RED (PSC-23 U8-7; design-notes N4 amendment U8 item 3): U8b adds
        # `sources-fetch` beside `sources-resolve`, and nothing else (was ["sources-resolve"] at U7b).
        self.assertEqual(sorted((data.get("services") or {})), ["sources-fetch", "sources-resolve"],
                         "docker-compose.sources.yml holds exactly sources-resolve and, from U8b, sources-fetch")

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
        r, calls = self._lock_run(("--arch", "amd64", "--evidence-dir", str(self.tmp)), images=table)
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
        r, calls = self._lock_run(("--arch", "amd64", "--evidence-dir", str(self.tmp)), FAKE_DF_AVAIL_KB="1000")
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
    with mock.patch.object(mod, "OPENER", opener), contextlib.redirect_stdout(o), contextlib.redirect_stderr(e), \
            mock.patch.object(mod, "SLEEP", lambda s: None, create=True):  # U7d R4: never wait in tests
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
        with self.subTest(case="an InvalidURL at open"):
            got = self._main_with(JAXB_NEED, Opener({JAXB_URL + ".sha1": sidecar(),
                                                     JAXB_URL: raising(http.client.InvalidURL("x"))}))
            self._one_fail_line(got, f"sources_lock: FAIL (resolve: {JAXB_KEY}: {MAVEN}: InvalidURL")
        with self.subTest(case="a mid-body timeout"):
            # U7d R2/R5 (Q72, P-R2): a timeout is retried 3 times, each with its retry
            # line, then the one FAIL line (until U7d: the FAIL line alone).
            got = self._main_with(JAXB_NEED, Opener({JAXB_URL + ".sha1": sidecar(),
                                                     JAXB_URL: body_of([b"abc"], then=TimeoutError())}))
            code, _, err = got
            lines = fail_lines(err)
            self.assertEqual(code, 1, err)
            self.assertEqual([ln.split(" s: ", 1)[0] for ln in lines[:-1]],
                             ["retry 1/3 in 10", "retry 2/3 in 30", "retry 3/3 in 60"], err)
            self.assertTrue(lines[-1].startswith(f"sources_lock: FAIL (resolve: {JAXB_KEY}: {MAVEN}: timeout after 60 s"),
                            lines[-1])

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
             path: str | None = None, args: tuple[str, ...] | None = None, extra_env: dict[str, str] | None = None
             ) -> tuple[subprocess.CompletedProcess, list[list[str]]]:
        # U7d rework round 1, item 4: --evidence-dir is required (was --arch alone).
        if args is None:
            # U8b RED (tester; PSC-23 U8-12, design-notes N4 amendment U8 item 9): a fresh, empty
            # evidence dir per run, because the script now refuses an existing <evdir>/sboms (was one
            # dir, tmp/evidence, reused by every run of a test).
            self.evdir = Path(tempfile.mkdtemp(prefix="evidence-", dir=self.tmp))
            args = ("--arch", "amd64", "--evidence-dir", str(self.evdir))
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
               # U7c A1: the Alpine images' saved tars carry the apk route inputs.
               "FAKE_IMAGE_TAR_FILES": json.dumps({img: {"lib/apk/db/installed": inp["installed"],
                                                         "etc/alpine-release": inp["release"]}
                                                   for img, inp in apk_inputs(docs).items()}),
               "FAKE_RESOLVE_NET": json.dumps(net or {}), "FAKE_RESOLVE_LOG": str(self.resolve_log)}
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        env.update(extra_env or {})
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
        # U7d (A71): a pgdg miss is resolvable now, so the hidden non-neo4j problem
        # is a stale manual entry, which the resolver keeps and lock-check reports
        # after every miss (was a pgdg miss until U7d).
        rows = with_rows({"ke-neo4j": neo})
        lock, docs, _ = self._commit_lock(rows, drop={NEO_KEY})
        stale = "neo4j:neo4j@9.9.9"
        lock["components"][stale] = good_entry(stale)
        self.lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "a stale manual entry")
        before = self.lock.read_bytes()
        problems = self.check.lock_problems(self.check.lock_text(lock), policy(), docs, ARCH)
        self.assertGreater(len(problems), 20, "fixture")
        self.assertTrue(all(f"the lock has no {NEO_KEY} for" in x for x in problems[:20]), "fixture")
        self.assertIn(f"lock: {stale} is listed for amd64 but no image needs it", problems[-1], "fixture")
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


# ==========================================================================
# U7c: the deb and apk routes (design-notes "U7c precision": D1-D7, A1-A5,
# C1-C3; orchestrator rulings R-1 (a) and R-2 (c), 2026-10-25). Fake network
# only; no real fetch.
# Interface added (tester, U7c RED): `SNAPSHOT_PAUSE` (1.0 s, a module
# constant read when used; tests patch it to 0); `parse_dsc(text) -> {field:
# value}` (a field's first line and continuation lines joined with "\n",
# stripped); sbom_check.py `lock_needs_doc(policy, docs, releases, apk)` with
# `apk` = {image: {"installed": <lib/apk/db/installed>, "release":
# <etc/alpine-release>}}, and `tar_file_text(tar, member, limit)`.
# ==========================================================================

SNAP = "snapshot.debian.org"
GL = "gitlab.alpinelinux.org"
APORTS = f"https://{GL}/api/v4/projects/alpine%2Faports/repository"
BASH_KEY = "deb:bash@5.2.15-2"
BASH_DOCS = {"postgres": [{"purl": ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"),
                           "declared": "GPL-3.0-or-later"}]}
RL_KEY = "apk:readline@8.2.13-r1"
RL_PURL = "pkg:apk/alpine/readline@8.2.13-r1?arch=x86_64&distro=alpine-3.23.3"
RL_DOCS = {"valkey": [{"purl": RL_PURL, "declared": "GPL-3.0-or-later"}]}
RL_COMMIT = aports_commit("readline", "8.2.13-r1")


def snap_url(src: str, ver: str) -> str:
    return f"https://{SNAP}/mr/package/{quote(src, safe='')}/{quote(ver, safe='')}/srcfiles?fileinfo=1"


def snap_file(sha1: str) -> str:
    return f"https://{SNAP}/file/{sha1}"


def no_pause(test: unittest.TestCase, mod: ModuleType) -> None:
    p = mock.patch.object(mod, "SNAPSHOT_PAUSE", 0, create=True)
    p.start()
    test.addCleanup(p.stop)


class DebFixture:
    """A snapshot.debian.org source package for one deb key: the srcfiles
    JSON (fileinfo) and a `.dsc` listing its files (D1-D6)."""

    def __init__(self, key: str, files: dict[str, bytes] | None = None):
        self.key = key
        self.src, _, self.ver = key.split(":", 1)[1].rpartition("@")
        nover = self.ver.split(":", 1)[1] if ":" in self.ver else self.ver
        self.dsc = f"{self.src}_{nover}.dsc"
        if files is None:
            if "-" in nover:
                up = nover.rsplit("-", 1)[0]
                files = {f"{self.src}_{up}.orig.tar.xz": f"orig of {key}".encode(),
                         f"{self.src}_{nover}.debian.tar.xz": f"debian of {key}".encode()}
            else:
                files = {f"{self.src}_{nover}.tar.xz": f"native {key}".encode()}
        self.files = files

    def lines(self, alg: str, files: dict[str, bytes] | None = None) -> str:
        return "".join(f" {hashlib.new(alg, b).hexdigest()} {len(b)} {n}\n" for n, b in (files or self.files).items())

    def text(self, *, armour: bool = True, source: str | None = None, version: str | None = None,
             drop: tuple[str, ...] = (), replace: dict[str, str] | None = None, dash: bool = False) -> str:
        head = [f"Format: 3.0 (quilt)", f"Source: {source or self.src}", f"Binary: {self.src}", "Architecture: any",
                f"Version: {version or self.ver}", "Maintainer: Fixture <fixture@example.invalid>",
                "Build-Depends: debhelper-compat (= 13),\n autoconf"]
        if dash:
            head[1] = "- " + head[1]
        body = "\n".join(head) + "\n"
        for field, alg in (("Checksums-Sha1", "sha1"), ("Checksums-Sha256", "sha256"), ("Files", "md5")):
            if field in drop:
                continue
            body += f"{field}:\n" + ((replace or {}).get(field) or self.lines(alg))
        if not armour:
            return body
        return ("-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n" + body
                + "\n-----BEGIN PGP SIGNATURE-----\nComment: fixture-signature\n\niQIzBAEBCgAdFiEEfixture\n=abcd\n-----END PGP SIGNATURE-----\n")

    def fileinfo(self, dsc_body: bytes, files: dict[str, bytes] | None = None) -> dict[str, Any]:
        info: dict[str, Any] = {sha("sha1", dsc_body): [{"archive_name": "debian", "first_seen": "20230101T000000Z",
                                                         "name": self.dsc, "path": f"/pool/main/x/{self.src}",
                                                         "size": len(dsc_body)}]}
        for n, b in (self.files if files is None else files).items():
            info.setdefault(sha("sha1", b), []).append({"archive_name": "debian", "first_seen": "20230101T000000Z",
                                                        "name": n, "path": f"/pool/main/x/{self.src}", "size": len(b)})
        return info

    def routes(self, dsc_text: str | None = None, *, fileinfo: dict[str, Any] | None = None,
               dsc_served: bytes | None = None) -> dict[str, Any]:
        body = (dsc_text if dsc_text is not None else self.text()).encode()
        info = self.fileinfo(body) if fileinfo is None else fileinfo
        doc = {"_comment": "foo", "package": self.src, "version": self.ver,
               "result": [{"hash": h} for h in sorted(info)], "fileinfo": info}
        return {snap_url(self.src, self.ver): ok(json.dumps(doc)),
                snap_file(sha("sha1", body)): ok(body if dsc_served is None else dsc_served)}

    def entry(self) -> dict[str, Any]:
        body = self.text().encode()
        d1 = sha("sha1", body)
        files = [{"name": self.dsc, "url": snap_file(d1), "sha256": sha("sha256", body), "size": len(body),
                  "upstream": {"alg": "sha1", "value": d1, "from": f"{SNAP} mr/package fileinfo"}}]
        for n, b in self.files.items():
            h = sha("sha256", b)
            files.append({"name": n, "url": snap_file(sha("sha1", b)), "sha256": h, "size": len(b),
                          "upstream": {"alg": "sha256", "value": h, "from": f"{self.dsc} Checksums-Sha256"}})
        return {"kind": "deb", "arches": [ARCH], "origin": "generated", "files": files}


def by_name(entry: dict[str, Any]) -> dict[str, Any]:
    return dict(entry, files=sorted(entry["files"], key=lambda f: f["name"]))


def deb_need(key: str) -> dict[str, Any]:
    src, _, ver = key.split(":", 1)[1].rpartition("@")
    return need(key, "postgres", f"pkg:deb/debian/{src}@{quote(ver, safe='')}", {"src": src, "ver": ver})


class U7cDebRouteTest(unittest.TestCase):
    """D1-D7: srcfiles, then the `.dsc` alone; the other files are recorded
    from its Checksums-Sha256 and never fetched."""

    def setUp(self) -> None:
        self.mod = load_resolver()
        no_pause(self, self.mod)

    def _resolve(self, key: str, routes: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        with network(self.mod, routes) as net:
            lock, _, skipped = resolve(self.mod, {key: deb_need(key)})
        self.assertEqual(skipped, [], "a deb key was skipped (U7c: deb has a route)")
        return lock, net

    def test_the_entry(self):
        fx = DebFixture(BASH_KEY)
        lock, net = self._resolve(BASH_KEY, fx.routes())
        self.assertEqual(by_name(lock["components"][BASH_KEY]), by_name(fx.entry()))
        self.assertEqual(net.calls, [snap_url("bash", "5.2.15-2"), snap_file(sha("sha1", fx.text().encode()))],
                         "only srcfiles and the .dsc are requested; orig and debian tarballs are not streamed (D6)")
        lock_ok(self, lock, docs_for(BASH_DOCS))

    def test_dsc_forms(self):
        rows = {
            "an epoch: the .dsc name drops it, Version keeps it": ("deb:attr@1:2.5.1-4", {}),
            "a native package": ("deb:adduser@3.134", {}),
            "a version with + and ~": ("deb:openldap@2.5.13+dfsg-5~bpo1", {}),
            "no clearsign armour": (BASH_KEY, {"armour": False}),
            "a dash-escaped line": (BASH_KEY, {"dash": True}),
        }
        for case, (key, opts) in rows.items():
            with self.subTest(case=case):
                fx = DebFixture(key)
                lock, net = self._resolve(key, fx.routes(fx.text(**opts)))
                e = lock["components"][key]
                self.assertEqual({f["name"] for f in e["files"]}, {fx.dsc} | set(fx.files))
                self.assertEqual(net.calls[0], snap_url(fx.src, fx.ver))
        self.assertEqual(DebFixture("deb:attr@1:2.5.1-4").dsc, "attr_2.5.1-4.dsc")
        self.assertIn("1%3A2.5.1-4", snap_url("attr", "1:2.5.1-4"))

    def test_failures(self):
        err = rfn("ResolveError")
        fx = DebFixture(BASH_KEY)
        good = fx.text()
        gbody = good.encode()
        orig, debian = list(fx.files)
        sha1 = fx.lines("sha1")
        rows: dict[str, tuple[dict[str, Any], str]] = {
            "srcfiles 404": ({}, f"{SNAP}: HTTP 404: {snap_url('bash', '5.2.15-2')}"),
            "srcfiles not JSON": ({snap_url("bash", "5.2.15-2"): ok("<html>")}, f"{SNAP} srcfiles is not the expected JSON"),
            "fileinfo with a key that is not 40 hex": (
                {snap_url("bash", "5.2.15-2"): ok(json.dumps({"fileinfo": {"../../x": [{"name": fx.dsc}]}}))},
                f"{SNAP} srcfiles is not the expected JSON"),
            "fileinfo entry without a name": (
                {snap_url("bash", "5.2.15-2"): ok(json.dumps({"fileinfo": {"a" * 40: [{"size": 1}]}}))},
                f"{SNAP} srcfiles is not the expected JSON"),
            "a name with two sha1s": (fx.routes(fileinfo=dict(fx.fileinfo(gbody), **{"b" * 40: [{"name": orig}]})),
                                      f"two files named {orig} in snapshot's srcfiles"),
            "no .dsc in srcfiles": (fx.routes(fileinfo={k: v for k, v in fx.fileinfo(gbody).items()
                                                        if v[0]["name"] != fx.dsc}),
                                    f"{SNAP} has no {fx.dsc} in srcfiles"),
            ".dsc sha1 mismatch": (fx.routes(dsc_served=gbody + b"tampered"),
                                   f"{fx.dsc}: sha1 mismatch: got {sha('sha1', gbody + b'tampered')}, {SNAP} says "
                                   f"{sha('sha1', gbody)}"),
            ".dsc over 1 MiB": (fx.routes(good + "X-Pad: " + "x" * 1048576 + "\n"), f"{fx.dsc}: more than 1048576 bytes"),
            "Source/Version": (fx.routes(fx.text(version="5.2.15-3")),
                               f"{fx.dsc}: Source/Version is bash/5.2.15-3, want bash/5.2.15-2"),
            "no Checksums-Sha256": (fx.routes(fx.text(drop=("Checksums-Sha256",))), f"{fx.dsc}: no Checksums-Sha256"),
            "no Files (gap ruling 4)": (fx.routes(fx.text(drop=("Files",))), ".dsc has no Files"),
            "a bad Checksums-Sha256 line": (fx.routes(fx.text(replace={"Checksums-Sha256": " abc 12 x.tar.xz\n"})),
                                            f"{fx.dsc}: bad Checksums-Sha256 line"),
            "a bad Files line": (fx.routes(fx.text(replace={"Files": " " + "a" * 32 + " twelve x.tar.xz\n"})),
                                 f"{fx.dsc}: bad Files line"),
            "different files": (fx.routes(fx.text(replace={"Files": fx.lines("md5", {orig: fx.files[orig]})})),
                                f"{fx.dsc}: Checksums-Sha256 and Files list different files"),
            "different sizes": (fx.routes(fx.text(replace={"Files": fx.lines("md5").replace(
                f" {len(fx.files[orig])} {orig}", f" {len(fx.files[orig]) + 1} {orig}")})),
                f"{fx.dsc}: Checksums-Sha256 and Files list different files"),
            "a Checksums-Sha1 that is not snapshot's": (
                fx.routes(fx.text(replace={"Checksums-Sha1": sha1.replace(sha("sha1", fx.files[orig]), "c" * 40)})),
                f"{orig}: Checksums-Sha1 says {'c' * 40}, {SNAP} says {sha('sha1', fx.files[orig])}"),
            "a listed file absent from srcfiles": (
                fx.routes(fileinfo={k: v for k, v in fx.fileinfo(gbody).items() if v[0]["name"] != debian}),
                f"{debian} is in the .dsc but not in snapshot's srcfiles"),
        }
        unsafe = DebFixture(BASH_KEY, files={"../evil.tar.xz": b"evil"})
        rows["an unsafe name in the .dsc"] = (unsafe.routes(), "../evil.tar.xz: not a safe file name")
        colon = DebFixture(BASH_KEY, files={"a::b.tar.xz": b"evil"})
        rows["a name with ::"] = (colon.routes(), "a::b.tar.xz: not a safe file name")
        bad_utf8 = gbody + b"\xff\xfe\n"
        rows[".dsc not UTF-8"] = (fx.routes(fileinfo=dict(fx.fileinfo(bad_utf8)), dsc_served=bad_utf8) |
                                  {snap_file(sha("sha1", bad_utf8)): ok(bad_utf8)}, f"{fx.dsc}: not UTF-8 text")
        for case, (routes, why) in rows.items():
            with self.subTest(case=case):
                with network(self.mod, routes) as net:
                    with self.assertRaises(err) as caught:
                        resolve(self.mod, {BASH_KEY: deb_need(BASH_KEY)})
                self.assertEqual(str(caught.exception), f"{BASH_KEY}: {why}")
                self.assertFalse([c for c in net.calls if "evil" in c or c.endswith(("orig.tar.xz", "debian.tar.xz"))],
                                 "a listed file was requested")

    def test_parse_dsc(self):
        fx = DebFixture(BASH_KEY)
        for case, text in {"armoured": fx.text(), "plain": fx.text(armour=False),
                           "dash-escaped": fx.text(dash=True)}.items():
            with self.subTest(case=case):
                f = rfn("parse_dsc")(text)
                self.assertEqual((f["Source"], f["Version"]), ("bash", "5.2.15-2"))
                # Gap rulings, interface pins: the Checksums fields come back in a
                # parsed form of the developer's choice; every line's hash, size and
                # name must be in it (continuation lines read).
                for field, alg in (("Checksums-Sha256", "sha256"), ("Files", "md5"), ("Checksums-Sha1", "sha1")):
                    got = json.dumps(f[field])
                    for n, b in fx.files.items():
                        self.assertTrue(hashlib.new(alg, b).hexdigest() in got and n in got and str(len(b)) in got,
                                        f"{field}: {n} missing from {got}")
                self.assertNotIn("iQIzBAEBCgAdFiEEfixture", json.dumps(f), "the signature is not part of the fields")
                self.assertNotIn("Comment", f, "the signature's armour header is not a field")


class ApkFixture:
    """An aports directory at a commit (A2-A5 with the U7c gap rulings 1-3):
    the recursive tree listing; the APKBUILD and an install script (files API
    content_sha256); a local patch and a patch in a subdirectory (GitLab raw,
    sha512sums); an upstream tarball (distfiles, sha512sums)."""

    def __init__(self, key: str = RL_KEY, *, commit: str = RL_COMMIT, branch: str = "v3.23", repo: str = "main"):
        self.key, self.commit, self.branch, self.repo = key, commit, branch, repo
        self.origin, _, self.ver = key.split(":", 1)[1].rpartition("@")
        self.pkgver, _, self.pkgrel = self.ver.rpartition("-r")
        # rel path -> bytes: the regular files beside the APKBUILD
        self.local = {"fix-build.patch": f"--- a\n+++ b\n{key}\n".encode(),
                      "patches/sub-fix.patch": f"--- c\n+++ d\n{key}\n".encode()}
        self.extra = {f"{self.origin}.post-install": f"#!/bin/sh\n# {key}\n".encode()}
        self.upstream = {f"{self.origin}-{self.pkgver}.tar.gz": f"upstream tarball of {key}".encode()}

    def summed(self) -> dict[str, bytes]:
        """basename -> bytes of every sha512sums name."""
        return {**self.upstream, **{rel.rsplit("/", 1)[-1]: b for rel, b in self.local.items()}}

    def sums(self) -> str:
        return "".join(f"{sha('sha512', b)}  {n}\n" for n, b in self.summed().items())

    def apkbuild(self, *, pkgver: str | None = None, pkgrel: str | None = None, sums: str | None = None,
                 quote_char: str = '"') -> str:
        block = "" if sums == "" else f"sha512sums={quote_char}\n{self.sums() if sums is None else sums}{quote_char}\n"
        return (f"# Contributor: Fixture <fixture@example.invalid>\npkgname={self.origin}\n"
                f"pkgver={self.pkgver if pkgver is None else pkgver}\npkgrel={self.pkgrel if pkgrel is None else pkgrel}\n"
                f'pkgdesc="fixture"\nurl="https://example.invalid/{self.origin}"\narch="all"\n'
                f'license="GPL-3.0-or-later"\ninstall="$pkgname.post-install"\n'
                f'source="https://example.invalid/{self.origin}-$pkgver.tar.gz\n'
                f'\tfix-build.patch\n\tpatches/sub-fix.patch\n\t"\n\nbuild() {{\n\t./configure --prefix=/usr\n\tmake\n}}\n\n'
                f"{block}")

    def tree(self, repo: str) -> str:
        # U7c rework round 1, item 8 (security I-1): the path value is percent-encoded
        # (was the raw `<repo>/<origin>` until round 1).
        return (f"{APORTS}/tree?path={quote(f'{repo}/{self.origin}', safe='')}&ref={self.commit}"
                "&recursive=true&per_page=100")

    def files_api(self, rel: str = "APKBUILD", repo: str | None = None) -> str:
        return f"{APORTS}/files/{quote(f'{repo or self.repo}/{self.origin}/{rel}', safe='')}?ref={self.commit}"

    def raw(self, rel: str, repo: str | None = None) -> str:
        # U7c rework round 1, item 9: the API raw endpoint (was /alpine/aports/-/raw/<commit>/...,
        # which sits behind a bot challenge: u7c/windows-run.txt).
        return f"{APORTS}/files/{quote(f'{repo or self.repo}/{self.origin}/{rel}', safe='')}/raw?ref={self.commit}"

    def dist(self, name: str) -> str:
        return f"https://distfiles.alpinelinux.org/distfiles/{self.branch}/{name}"

    def listing(self, repo: str, extra: list[dict[str, Any]] | None = None) -> str:
        rels = ["APKBUILD", *self.local, *self.extra]
        items: list[dict[str, Any]] = [{"id": "d" * 40, "name": "patches", "type": "tree",
                                        "path": f"{repo}/{self.origin}/patches", "mode": "040000"}]
        items += [{"id": sha("sha1", (repo + r).encode()), "name": r.rsplit("/", 1)[-1], "type": "blob",
                   "path": f"{repo}/{self.origin}/{r}", "mode": "100755" if r in self.extra else "100644"}
                  for r in rels]
        return json.dumps(items + (extra or []))

    def meta(self, rel: str, body: bytes, content_sha256: str | None = None) -> Any:
        return ok(json.dumps({"file_name": rel.rsplit("/", 1)[-1], "file_path": f"{self.repo}/{self.origin}/{rel}",
                              "size": len(body), "encoding": "base64", "ref": self.commit,
                              "content_sha256": content_sha256 or sha("sha256", body)}))

    def routes(self, apkbuild: str | None = None, *, content_sha256: str | None = None,
               listing: str | None = None) -> dict[str, Any]:
        text_ = (self.apkbuild() if apkbuild is None else apkbuild).encode()
        r: dict[str, Any] = {
            self.tree(self.repo): (200, {"X-Next-Page": "", "X-Total": "6"},
                                   self.listing(self.repo) if listing is None else listing),
            self.files_api(): self.meta("APKBUILD", text_, content_sha256),
            self.raw("APKBUILD"): ok(text_)}
        r.update({self.raw(rel): ok(b) for rel, b in {**self.local, **self.extra}.items()})
        r.update({self.files_api(rel): self.meta(rel, b) for rel, b in self.extra.items()})
        r.update({self.dist(n): ok(b) for n, b in self.upstream.items()})
        return r

    def entry(self) -> dict[str, Any]:
        text_ = self.apkbuild().encode()
        gl = f"gitlab files API content_sha256 at {self.commit}"
        files = [{"name": "APKBUILD", "url": self.raw("APKBUILD"), "sha256": sha("sha256", text_), "size": len(text_),
                  "upstream": {"alg": "sha256", "value": sha("sha256", text_), "from": gl}}]
        for rel, b in self.extra.items():
            files.append({"name": rel, "url": self.raw(rel), "sha256": sha("sha256", b), "size": len(b),
                          "upstream": {"alg": "sha256", "value": sha("sha256", b), "from": gl}})
        for rel, b in {**self.upstream, **self.local}.items():
            files.append({"name": rel.rsplit("/", 1)[-1], "url": self.raw(rel) if rel in self.local else self.dist(rel),
                          "sha256": sha("sha256", b), "size": len(b),
                          "upstream": {"alg": "sha512", "value": sha("sha512", b),
                                       "from": f"APKBUILD sha512sums at {self.commit}"}})
        return {"kind": "apk", "arches": [ARCH], "origin": "generated", "commit": self.commit, "branch": self.branch,
                "repo": self.repo, "files": files}


def apk_need(fx: ApkFixture, **route: Any) -> dict[str, Any]:
    r = {"origin": fx.origin, "ver": fx.ver, "commit": fx.commit, "branch": fx.branch}
    r.update(route)
    return need(fx.key, "valkey", RL_PURL, {k: v for k, v in r.items() if v is not ...})


class U7cApkRouteTest(unittest.TestCase):
    """A2-A5, R-1 (a) and the U7c gap rulings 1-4: every regular file of the
    package directory is locked, every URL fetched once."""

    def setUp(self) -> None:
        self.mod = load_resolver()

    def test_the_entry(self):
        for repo in ("main", "community"):
            with self.subTest(repo=repo):
                fx = ApkFixture(repo=repo)
                with network(self.mod, fx.routes()) as net:
                    lock, _, skipped = resolve(self.mod, {RL_KEY: apk_need(fx)})
                self.assertEqual(skipped, [], "an apk key was skipped (U7c: apk has a route)")
                self.assertEqual(by_name(lock["components"][RL_KEY]), by_name(fx.entry()))
                self.assertEqual(len(net.calls), len(set(net.calls)), "a URL was requested twice")
                self.assertEqual(set(net.calls), {fx.tree("main"), fx.tree("community"), fx.files_api(),
                                                  fx.files_api("readline.post-install"), fx.raw("APKBUILD"),
                                                  fx.raw("fix-build.patch"), fx.raw("patches/sub-fix.patch"),
                                                  fx.raw("readline.post-install"), fx.dist("readline-8.2.13.tar.gz")})
                lock_ok(self, lock, docs_for(RL_DOCS))
        with self.subTest(case="single-quoted sha512sums"):
            fx = ApkFixture()
            with network(self.mod, fx.routes(fx.apkbuild(quote_char="'"))):
                lock, _, _ = resolve(self.mod, {RL_KEY: apk_need(fx)})
            self.assertEqual(len(lock["components"][RL_KEY]["files"]), 5)
        with self.subTest(case="an empty main listing is not here (gap ruling 2)"):
            fx = ApkFixture(repo="community")
            with network(self.mod, dict(fx.routes(), **{fx.tree("main"): (200, {"X-Next-Page": ""}, "[]")})):
                lock, _, _ = resolve(self.mod, {RL_KEY: apk_need(fx)})
            self.assertEqual(lock["components"][RL_KEY]["repo"], "community")

    def test_failures(self):
        err = rfn("ResolveError")
        fx = ApkFixture()
        c = fx.commit
        good = fx.routes()
        com = ApkFixture(repo="community")
        tree_main = fx.tree("main")
        patch_bad = dict(good, **{fx.raw("fix-build.patch"): ok(b"tampered")})
        post = "readline.post-install"

        def listed(*extra: dict[str, Any]) -> dict[str, Any]:
            return fx.routes(listing=fx.listing("main", list(extra)))
        rows: dict[str, tuple[dict[str, Any], str]] = {
            "in both main and community": (good | com.routes(), f"readline: in both main and community at {c}"),
            "in neither": ({}, f"readline: in neither main nor community at {c}"),
            "empty listings in both": ({tree_main: (200, {}, "[]"), fx.tree("community"): (200, {}, "[]")},
                                       f"readline: in neither main nor community at {c}"),
            "a tree 500": (dict(good, **{tree_main: (500, {}, b"")}), f"{GL}: HTTP 500: {tree_main}"),
            "more than 100 files": (dict(good, **{tree_main: (200, {"X-Next-Page": "2"}, fx.listing("main"))}),
                                    f"readline: more than 100 files at {c}"),
            # U7d rework round 1, item 8: a link is checked through its files-API metadata now; a
            # link to a missing name is still not a regular file (until U7d every link failed).
            "a symlink": (dict(listed({"id": "e" * 40, "name": "link", "type": "blob", "path": "main/readline/link",
                                       "mode": "120000"}), **{fx.files_api("link"): link_meta(b"missing.patch")}),
                          f"readline: main/readline/link at {c} is not a regular file"),
            "a submodule": (listed({"id": "e" * 40, "name": "sub", "type": "commit", "path": "main/readline/sub",
                                    "mode": "160000"}), f"readline: main/readline/sub at {c} is not a regular file"),
            "two blobs with one basename": (listed({"id": "e" * 40, "name": "fix-build.patch", "type": "blob",
                                                    "path": "main/readline/patches/fix-build.patch",
                                                    "mode": "100644"}),
                                            f"readline: two files named fix-build.patch at {c}"),
            "content_sha256 mismatch": (fx.routes(content_sha256="e" * 64),
                                        f"APKBUILD: sha256 mismatch: got {sha('sha256', fx.apkbuild().encode())}, "
                                        f"gitlab files API says {'e' * 64}"),
            "an install script's content_sha256 mismatch": (
                dict(good, **{fx.files_api(post): fx.meta(post, fx.extra[post], "f" * 64)}),
                f"{post}: sha256 mismatch: got {sha('sha256', fx.extra[post])}, gitlab files API says {'f' * 64}"),
            "an install script not retrievable": ({k: v for k, v in good.items() if k != fx.raw(post)},
                                                  f"{GL}: HTTP 404: {fx.raw(post)}"),
            "an install script with no files API answer": ({k: v for k, v in good.items() if k != fx.files_api(post)},
                                                           f"{GL}: HTTP 404: {fx.files_api(post)}"),
            "pkgver is not the key's": (fx.routes(fx.apkbuild(pkgver="8.2.12")),
                                        f"APKBUILD at {c}: pkgver/pkgrel 8.2.12-r1 is not 8.2.13-r1"),
            "pkgrel is not the key's": (fx.routes(fx.apkbuild(pkgrel="2")),
                                        f"APKBUILD at {c}: pkgver/pkgrel 8.2.13-r2 is not 8.2.13-r1"),
            "no sha512sums": (fx.routes(fx.apkbuild(sums="")), f"APKBUILD at {c}: no sha512sums"),
            "an empty sha512sums": (fx.routes(fx.apkbuild(sums="\n")), f"APKBUILD at {c}: no sha512sums"),
            "sha512sums not a literal": (fx.routes(fx.apkbuild(sums=fx.sums() + "$_extra  x.patch\n")),
                                         f"APKBUILD at {c}: sha512sums is not a literal"),
            "an unsafe sha512sums name": (fx.routes(fx.apkbuild(sums=fx.sums() + "a" * 128 + "  ../evil.tar.gz\n")),
                                          "../evil.tar.gz: not a safe file name"),
            "a :: name": (fx.routes(fx.apkbuild(sums=fx.sums() + "a" * 128 + "  evil.tar.gz::https\n")),
                          "evil.tar.gz::https: not a safe file name"),
            "a local file's sha512": (patch_bad, f"fix-build.patch: sha512 mismatch: got {sha('sha512', b'tampered')}, "
                                                 f"APKBUILD sha512sums at {c} says "
                                                 f"{sha('sha512', fx.local['fix-build.patch'])}"),
            "a distfile's sha512": (dict(good, **{fx.dist("readline-8.2.13.tar.gz"): ok(b"tampered")}),
                                    f"readline-8.2.13.tar.gz: sha512 mismatch: got {sha('sha512', b'tampered')}, "
                                    f"APKBUILD sha512sums at {c} says {sha('sha512', fx.upstream['readline-8.2.13.tar.gz'])}"),
            "not in the tree and not on distfiles": (
                {k: v for k, v in good.items() if k != fx.dist("readline-8.2.13.tar.gz")},
                f"distfiles.alpinelinux.org: HTTP 404: {fx.dist('readline-8.2.13.tar.gz')}"),
        }
        for case, (routes, why) in rows.items():
            with self.subTest(case=case):
                with network(self.mod, routes) as net:
                    with self.assertRaises(err) as caught:
                        resolve(self.mod, {RL_KEY: apk_need(fx)})
                self.assertEqual(str(caught.exception), f"{RL_KEY}: {why}")
                self.assertFalse([u for u in net.calls if "evil" in u], "a URL was built from an unsafe name")
        with self.subTest(case="an unsafe path in the listing"):
            with network(self.mod, listed({"id": "e" * 40, "name": "evil.patch", "type": "blob",
                                           "path": "main/readline/../evil.patch", "mode": "100644"})) as net:
                with self.assertRaises(err):
                    resolve(self.mod, {RL_KEY: apk_need(fx)})
            self.assertFalse([u for u in net.calls if "evil" in u], "a URL was built from an unsafe listing path")
        with self.subTest(case="a non-literal pkgver"):
            with network(self.mod, fx.routes(fx.apkbuild(pkgver="$_ver"))):
                with self.assertRaises(err) as caught:
                    resolve(self.mod, {RL_KEY: apk_need(fx)})
            msg = str(caught.exception)
            self.assertTrue(msg.startswith(f"{RL_KEY}: APKBUILD at {c}: pkgver/pkgrel ") and
                            msg.endswith(" is not 8.2.13-r1"), msg)
        for field, route in (("origin", {"origin": "ncurses"}), ("origin", {"origin": ...}), ("ver", {"ver": "1-r0"}),
                             ("commit", {"commit": None}), ("commit", {"commit": "../x"}),
                             ("branch", {"branch": "master"}), ("branch", {"branch": 3})):
            with self.subTest(field=field, route=repr(route)):
                with network(self.mod, good) as net:
                    with self.assertRaises(err) as caught:
                        resolve(self.mod, {RL_KEY: apk_need(fx, **route)})
                self.assertEqual(str(caught.exception), f"{RL_KEY}: apk {RL_KEY}: route is malformed ({field})")
                self.assertEqual(net.calls, [], "a request was made with a malformed route")


class U7cCoverageTest(unittest.TestCase):
    """Ruling 3: the 153 deb and 19 apk fixture keys all resolve (none is
    skipped) and every entry passes U7a's lock_problems."""

    def test_the_fixture_keys(self):
        mod = load_resolver()
        no_pause(self, mod)
        check = load_sbom_check()
        docs = fixture_docs()
        needs_all, problems = check.lock_needs(policy(), docs)
        self.assertEqual(problems, [])
        needs: dict[str, Any] = {}
        routes: dict[str, Any] = {}
        for key, e in sorted(needs_all.items()):
            kind = key.split(":", 1)[0]
            name, _, ver = key.split(":", 1)[1].rpartition("@")
            if kind == "deb":
                needs[key] = {"kind": kind, "packages": e["packages"], "route": {"src": name, "ver": ver}}
                routes.update(DebFixture(key).routes())
            elif kind == "apk":
                distro = {unquote(q.partition("=")[2]) for p in e["packages"]
                          for q in str(p["purl"]).partition("?")[2].split("&") if q.startswith("distro=")}
                self.assertEqual(len(distro), 1, key)
                x, y, _ = distro.pop().split("-", 1)[1].split(".")
                fx = ApkFixture(key, commit=aports_commit(name, ver), branch=f"v{x}.{y}")
                needs[key] = {"kind": kind, "packages": e["packages"], "route": {
                    "origin": name, "ver": ver, "commit": fx.commit, "branch": fx.branch}}
                routes.update(fx.routes())
        # deb 152 -> 153 in U7e: u7e/key-diff.txt l.6-8 (+openssl~deb12u2, +ca-certificates~deb12u2,
        # -ca-certificates~deb12u1; base-dpkg-diff.txt).
        self.assertEqual((sum(k.startswith("deb:") for k in needs), sum(k.startswith("apk:") for k in needs)), (153, 19))
        with network(mod, routes):
            lock, _, skipped = resolve(mod, needs)
        self.assertEqual(skipped, [])
        self.assertEqual(set(lock["components"]), set(needs), "a deb or apk key got no entry")
        bad = [p for p in check.lock_problems(check.lock_text(lock), policy(), docs, ARCH)
               if p.startswith(("lock: deb:", "lock: apk:"))]
        self.assertEqual(bad, [], "a resolved deb or apk entry fails lock_problems")


class U7cCarriedTest(unittest.TestCase):
    """C1 (review U7b R1-N1), C2 (security U7b R1-L1), pgdg (interface pins
    item 3)."""

    def test_a_server_supplied_url_gets_the_hop_rules(self):
        mod = load_resolver()
        bad = "https://files.pythonhosted.org/packages/33/01/%2e%2e/%2e%2e/" + "d" * 60 + "/pandas-2.3.3.tar.gz"
        doc = json.loads(pandas_json())
        doc["urls"][1]["url"] = bad
        key = "pypi:pandas@2.3.3"
        with network(mod, {"https://pypi.org/pypi/pandas/2.3.3/json": ok(json.dumps(doc)), bad: ok(PANDAS_BODY)}) as net:
            with self.assertRaises(rfn("ResolveError")):
                resolve(mod, {key: need(key, "phoenix", "pkg:pypi/pandas@2.3.3", {"name": "pandas", "ver": "2.3.3"})})
        self.assertNotIn(bad, net.calls, "R1-N1: the server-supplied url was requested")

    def test_the_real_opener_reads_with_read1(self):
        spec = importlib.util.spec_from_file_location("ke_sources_resolve_read1", RESOLVER)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        chunks = [b"ab", b"c", b""]

        class Resp:
            status, headers = 200, {}

            def read(self, n: int = -1) -> bytes:
                raise AssertionError("read(n) loops over recv until n bytes: use read1 (security U7b R1-L1)")

            def read1(self, n: int = -1) -> bytes:
                return chunks.pop(0)
        fake = SimpleNamespace(open=mock.Mock(return_value=Resp()))
        with mock.patch("urllib.request.build_opener", return_value=fake):
            r = mod.OPENER(JAXB_URL, 5)
            self.assertEqual(b"".join(r.body), b"abc")

    def test_snapshot_pause(self):
        mod = load_resolver()
        self.assertEqual(getattr(mod, "SNAPSHOT_PAUSE", None), 1.0, "D7: 1 s between snapshot requests")
        fx, fx2 = DebFixture(BASH_KEY), DebFixture("deb:attr@1:2.5.1-4")
        times: list[float] = []

        class Timed(FakeNet):
            def __call__(self, url: str, timeout: float) -> Any:
                times.append(time.monotonic())
                return super().__call__(url, timeout)
        with mock.patch.object(mod, "SNAPSHOT_PAUSE", 0.3), mock.patch.object(mod, "OPENER",
                                                                              Timed(fx.routes() | fx2.routes())):
            resolve(mod, {BASH_KEY: deb_need(BASH_KEY), fx2.key: deb_need(fx2.key)})
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertEqual(len(times), 4)
        self.assertTrue(all(g >= 0.28 for g in gaps), f"snapshot requests not spaced by SNAPSHOT_PAUSE: {gaps}")

    def test_pgdg_is_no_longer_skipped(self):
        """U7d (A71) supersedes "pgdg is skipped until Q71": the key resolves
        through the pgdg route and no skip line is printed."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        fx = PgdgFixture((PGDG_KEY,))
        code, _, err = run_main(tmp, {PGDG_KEY: pg_need(PGDG_KEY)}, FakeNet(fx.routes()))
        self.assertEqual(code, 0, err)
        self.assertFalse([ln for ln in err.splitlines() if "skip:" in ln], err)
        self.assertIn(PGDG_KEY, json.loads((tmp / "out" / "lock.new.json").read_text(encoding="utf-8"))["components"])


# --------------------------------------------------------------------------
# U7c A1: lock-needs reads the apk route inputs from the saved tar
# --------------------------------------------------------------------------

RL_DEV_PURL = "pkg:apk/alpine/readline-static@8.2.13-r1?arch=x86_64&distro=alpine-3.23.3&upstream=readline"


def rl_docs() -> dict[str, Any]:
    return docs_for({"valkey": [{"purl": RL_PURL, "declared": "GPL-3.0-or-later"},
                                {"purl": RL_DEV_PURL, "declared": "GPL-3.0-or-later"}]})


def rl_db(*, static_origin: str = "readline", static_commit: str = RL_COMMIT, drop_static: bool = False) -> str:
    db = f"C:Q1a=\nP:readline\nV:8.2.13-r1\nA:x86_64\no:readline\nm:Fixture\nc:{RL_COMMIT}\n\n"
    if not drop_static:
        db += f"C:Q1b=\nP:readline-static\nV:8.2.13-r1\nA:x86_64\no:{static_origin}\nc:{static_commit}\n\n"
    return db + f"C:Q1c=\nP:musl\nV:1.2.5-r21\nA:x86_64\no:musl\nc:{'0' * 40}\n"


class U7cLockNeedsTest(unittest.TestCase):

    def _doc(self, apk: Any) -> tuple[dict[str, Any], list[str]]:
        fn_ = getattr(load_sbom_check(), "lock_needs_doc")
        return fn_(policy(), rl_docs(), {}, apk)

    def test_the_apk_route(self):
        doc, problems = self._doc({"valkey": {"installed": rl_db(), "release": "3.23.3\n"}})
        self.assertEqual(problems, [])
        self.assertEqual(doc["needs"][RL_KEY]["route"], {"origin": "readline", "ver": "8.2.13-r1", "commit": RL_COMMIT,
                                                         "branch": "v3.23"})

    def test_problems(self):
        miss = (f"{RL_KEY}: valkey: readline-static 8.2.13-r1 has no installed-db stanza with origin readline "
                "and an aports commit")
        other = "a" * 40
        rows = {
            "a package with no stanza": ({"installed": rl_db(drop_static=True), "release": "3.23.3\n"}, miss),
            "a stanza with another origin": ({"installed": rl_db(static_origin="ncurses"), "release": "3.23.3\n"}, miss),
            "a commit that is not 40 hex": ({"installed": rl_db(static_commit="abc"), "release": "3.23.3\n"}, miss),
            "two commits": ({"installed": rl_db(static_commit=other), "release": "3.23.3\n"},
                            f"{RL_KEY}: two aports commits {min(other, RL_COMMIT)}, {max(other, RL_COMMIT)}"),
            "alpine-release and the purl disagree": ({"installed": rl_db(), "release": "3.24.2\n"},
                                                     f"{RL_KEY}: valkey: alpine-release 3.24.2, purl distro alpine-3.23.3"),
        }
        for case, (inputs, want) in rows.items():
            with self.subTest(case=case):
                doc, problems = self._doc({"valkey": inputs})
                self.assertIn(want, problems)
                self.assertNotIn(RL_KEY, doc["needs"], "a key with a problem got a route")
        with self.subTest(case="no tar inputs for the image"):
            doc, problems = self._doc({})
            self.assertTrue([p for p in problems if p.startswith(f"{RL_KEY}: ")], problems)

    def _cli(self, tmp: Path, tar: Path, image: str = "valkey") -> subprocess.CompletedProcess:
        docs = rl_docs()
        if image == "ke-neo4j":
            docs = docs_for(TEM_DOCS)
        for img, d in docs.items():
            ss.write_json(tmp / f"{img}.spdx.json", d)
        return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-needs",
                               "--policy", str(ROOT / "docker" / "source-policy.json"),
                               *[a for img in docs for a in ("--sbom", f"{img}={tmp / f'{img}.spdx.json'}")],
                               "--tar", f"{image}={tar}"], capture_output=True, text=True, timeout=120)

    def test_the_cli_reads_the_tar(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        tar = save_tar_with(tmp / "valkey.tar", [{"lib/apk/db/installed": rl_db(static_commit="b" * 40).encode(),
                                                  "etc/alpine-release": b"3.22.1\n"},
                                                 {"lib/apk/db/installed": rl_db().encode(),
                                                  "etc/alpine-release": b"3.23.3\n"}])
        r = self._cli(tmp, tar)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual(json.loads(r.stdout)["needs"][RL_KEY]["route"]["commit"], RL_COMMIT, "the top layer wins")
        with self.subTest(case="an installed db over 16 MiB"):
            big = save_tar_with(tmp / "big.tar", [{"lib/apk/db/installed": rl_db().encode() + b"x" * (16 << 20),
                                                   "etc/alpine-release": b"3.23.3\n"}])
            r = self._cli(tmp, big)
            self.assertEqual(r.returncode, 1, r.stderr[-800:])
            self.assertIn("valkey: /lib/apk/db/installed larger than 16 MiB", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
        with self.subTest(case="a release file over 1 MiB"):
            big = save_tar_with(tmp / "neo.tar", [{"opt/java/openjdk/release": RELEASE.encode() + b"#" * (1 << 20)}])
            r = self._cli(tmp, big, image="ke-neo4j")
            self.assertEqual(r.returncode, 1, r.stderr[-800:])
            self.assertIn("ke-neo4j: /opt/java/openjdk/release larger than 1 MiB", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


class U7cLockScriptRunTest(_BundleBase, unittest.TestCase):
    """A1 in sources_lock.sh: `--tar` for every image; R-2 (c): the literal
    six equals the stack's bundled names."""

    def setUp(self) -> None:
        super().setUp()
        for rel in ("docker/source-policy.json", SOURCES_YML):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.repo / rel)
        self.lock = self.repo / "docker" / "sources.lock.json"
        self.check = load_sbom_check()
        self.syft_log = self.tmp / "syft.jsonl"
        self.resolve_log = self.tmp / "resolve.log"

    _commit_lock = ReworkR1LockScriptRunTest._commit_lock
    _run = ReworkR1LockScriptRunTest._run
    _steps = staticmethod(ReworkR1LockScriptRunTest._steps)

    def test_lock_needs_gets_every_tar(self):
        lock, docs, _ = self._commit_lock(HAPPY_ROWS)
        r, calls = self._run(docs)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        needs_call = [c for n, c in self._steps(calls) if n == "lock-needs"]
        self.assertEqual(len(needs_call), 1)
        tars = [needs_call[0][i + 1] for i, a in enumerate(needs_call[0]) if a == "--tar"]
        self.assertEqual(sorted(tars), sorted(f"{n}=/tars/{n}.tar" for n in HAPPY_ROWS), "A1: --tar for every image")

    def test_the_six_equal_the_bundled_names(self):
        from tests.test_sbom_obligations import bundled_names
        m = re.search(r"(?m)^six=\(([^)]*)\)$", LOCK_SH.read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "scripts/sources_lock.sh has no `six=(...)` literal (R-2 (c))")
        assert m is not None
        self.assertEqual(set(m.group(1).split()), bundled_names(),
                         "R-2 (c): the six=(...) guard in scripts/sources_lock.sh and the stack compose config "
                         "(bundle.sh's image set) disagree: change both")


# ==========================================================================
# U7c rework round 1 (design-notes "U7c rework round 1", orchestrator rulings
# 2026-10-25; u7c/review.md B1, N1, N2; u7c/security.md L-2, L-3, I-1).
# ==========================================================================

class ReworkR1U7cApkbuildTest(unittest.TestCase):
    """Item 1 (B1), resolver side: the APKBUILD is the top-level blob."""

    def test_only_a_subdirectory_apkbuild(self):
        mod = load_resolver()
        fx = ApkFixture()
        items = json.loads(fx.listing("main"))
        for it in items:
            if it["name"] == "APKBUILD":
                it["path"] = "main/readline/tests/APKBUILD"
        with network(mod, fx.routes(listing=json.dumps(items))) as net:
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(mod, {RL_KEY: apk_need(fx)})
        self.assertEqual(str(caught.exception), f"{RL_KEY}: readline: no APKBUILD at main/readline at {fx.commit}")
        self.assertFalse([u for u in net.calls if "APKBUILD" in u], "a subdirectory APKBUILD was requested")

    def test_a_subdirectory_apkbuild_beside_the_top_one(self):
        mod = load_resolver()
        fx = ApkFixture()
        extra = {"id": "e" * 40, "name": "APKBUILD", "type": "blob", "path": "main/readline/tests/APKBUILD",
                 "mode": "100644"}
        with network(mod, fx.routes(listing=fx.listing("main", [extra]))):
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(mod, {RL_KEY: apk_need(fx)})
        self.assertEqual(str(caught.exception), f"{RL_KEY}: readline: two files named APKBUILD at {fx.commit}")


class ReworkR1U7cDscTest(unittest.TestCase):
    """Items 2 (N1) and 6 (L-2): duplicate fields, CRLF, control characters."""

    def setUp(self) -> None:
        self.mod = load_resolver()
        no_pause(self, self.mod)
        self.fx = DebFixture(BASH_KEY)

    def _why(self, text: str) -> str:
        with network(self.mod, self.fx.routes(text)):
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(self.mod, {BASH_KEY: deb_need(BASH_KEY)})
        msg = str(caught.exception)
        self.assertTrue(msg.startswith(f"{BASH_KEY}: "), msg)
        return msg[len(BASH_KEY) + 2:]

    def test_duplicate_fields(self):
        fx, dsc = self.fx, self.fx.dsc
        good = fx.text()
        rows = {
            "two Version lines": (good.replace("Maintainer:", "Version: 9.9-9\nMaintainer:", 1), "Version"),
            "two Files blocks": (good.replace("\n-----BEGIN PGP SIGNATURE", "Files:\n" + fx.lines("md5")
                                              + "\n-----BEGIN PGP SIGNATURE", 1), "Files"),
            "Checksums-Sha256 and checksums-sha256": (good.replace(
                "\n-----BEGIN PGP SIGNATURE", "checksums-sha256:\n" + fx.lines("sha256") + "\n-----BEGIN PGP SIGNATURE", 1),
                "checksums-sha256"),
        }
        for case, (text, field) in rows.items():
            with self.subTest(case=case):
                self.assertEqual(self._why(text), f"{dsc}: duplicate field {field}")

    def test_crlf_parses_like_lf(self):
        fx = self.fx
        text = fx.text().replace("\n", "\r\n")
        with network(self.mod, fx.routes(text)):
            lock, _, _ = resolve(self.mod, {BASH_KEY: deb_need(BASH_KEY)})
        e = lock["components"][BASH_KEY]
        self.assertEqual([f for f in e["files"] if f["name"] != fx.dsc],
                         [f for f in fx.entry()["files"] if f["name"] != fx.dsc])

    def test_control_characters(self):
        fx, dsc = self.fx, self.fx.dsc
        good = fx.text()
        self.assertEqual(self._why(good.replace("Architecture: any", "Homepage: a\u2028Source: evil\nArchitecture: any")),
                         f"{dsc}: control character in field Homepage")
        first = fx.lines("sha256").split("\n")[0]
        for ch in ("\u0085", "\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\r"):
            with self.subTest(char=hex(ord(ch))):
                bad = first[:65] + ch + first[65:]  # after the hash, inside the line
                self.assertEqual(self._why(good.replace(first, bad, 1)),
                                 f"{dsc}: control character in field Checksums-Sha256")


class ReworkR1U7cApkbuildAssignTest(unittest.TestCase):
    """Item 3 (N2): one top-level pkgver, pkgrel and sha512sums."""

    def test_repeated_assignments(self):
        mod = load_resolver()
        fx = ApkFixture()
        good = fx.apkbuild()
        rows = {
            "a later pkgver=9.0": (good + "pkgver=9.0\n", "pkgver"),
            "a second pkgrel": (good.replace("pkgdesc=", "pkgrel=7\npkgdesc=", 1), "pkgrel"),
            "a second sha512sums block": (good + 'sha512sums="\n' + fx.sums() + '"\n', "sha512sums"),
        }
        for case, (text, name) in rows.items():
            with self.subTest(case=case):
                with network(mod, fx.routes(text)):
                    with self.assertRaises(rfn("ResolveError")) as caught:
                        resolve(mod, {RL_KEY: apk_need(fx)})
                self.assertEqual(str(caught.exception), f"{RL_KEY}: readline: APKBUILD assigns {name} more than once")
        with self.subTest(case="an indented sha512sums in prepare() is not top-level"):
            text = good.replace("build() {", 'prepare() {\n\tsha512sums="x"\n\tdefault_prepare\n}\n\nbuild() {', 1)
            with network(mod, fx.routes(text)):
                lock, _, _ = resolve(mod, {RL_KEY: apk_need(fx)})
            self.assertIn(RL_KEY, lock["components"])


class ReworkR1U7cListingTest(unittest.TestCase):
    """Items 7 (L-3) and 8 (I-1): a full page; the encoded path."""

    def _padded(self, fx: ApkFixture, total: int) -> str:
        items = json.loads(fx.listing("main"))
        items += [{"id": f"{i:040x}", "name": f"d{i}", "type": "tree", "path": f"main/readline/d{i}", "mode": "040000"}
                  for i in range(total - len(items))]
        self.assertEqual(len(items), total)
        return json.dumps(items)

    def test_a_full_page(self):
        mod = load_resolver()
        fx = ApkFixture()
        for case, total, headers, fails in (("100, no header", 100, {}, True),
                                            ("100, x-next-page 2", 100, {"X-Next-Page": "2"}, True),
                                            ("100, an empty x-next-page", 100, {"X-Next-Page": ""}, False),
                                            ("99, no header", 99, {}, False)):
            with self.subTest(case=case):
                routes = dict(fx.routes(), **{fx.tree("main"): (200, headers, self._padded(fx, total))})
                with network(mod, routes):
                    if fails:
                        with self.assertRaises(rfn("ResolveError")) as caught:
                            resolve(mod, {RL_KEY: apk_need(fx)})
                        self.assertEqual(str(caught.exception),
                                         f"{RL_KEY}: readline: listing may be truncated at {fx.commit}")
                    else:
                        lock, _, _ = resolve(mod, {RL_KEY: apk_need(fx)})
                        self.assertIn(RL_KEY, lock["components"])

    def test_the_path_is_encoded(self):
        mod = load_resolver()
        fx = ApkFixture("apk:libsigc++@3.6.0-r1", commit=aports_commit("libsigc++", "3.6.0-r1"))
        purl = "pkg:apk/alpine/libsigc%2B%2B@3.6.0-r1?arch=x86_64&distro=alpine-3.23.3"
        with network(mod, fx.routes()) as net:
            lock, _, _ = resolve(mod, {fx.key: need(fx.key, "valkey", purl, {
                "origin": fx.origin, "ver": fx.ver, "commit": fx.commit, "branch": fx.branch})})
        self.assertIn("path=main%2Flibsigc%2B%2B&", net.calls[0])
        self.assertIn(fx.key, lock["components"])


class ReworkR1U7cApiUrlResolverTest(unittest.TestCase):
    """Item 9 (the A34 finding), resolver side: requests at exactly the API
    raw form, the metadata request without /raw, and a bot challenge (307 to
    a challenge url, then 418) as one FAIL line with nothing written."""

    def test_the_request_forms(self):
        mod = load_resolver()
        fx = ApkFixture()
        with network(mod, fx.routes()) as net:
            lock, _, _ = resolve(mod, {RL_KEY: apk_need(fx)})
        gl = [u for u in net.calls if u.startswith(f"https://{GL}/")]
        self.assertFalse([u for u in gl if "/-/raw/" in u], "the old /-/raw/ form was requested")
        api = f"{APORTS}/files/"
        self.assertEqual(sorted(u for u in gl if u.startswith(api) and "/raw?" in u),
                         sorted(fx.raw(r) for r in ["APKBUILD", *fx.local, *fx.extra]))
        self.assertEqual(sorted(u for u in gl if u.startswith(api) and "/raw?" not in u),
                         sorted([fx.files_api(), *(fx.files_api(r) for r in fx.extra)]))
        self.assertTrue(all(f["url"].endswith(f"/raw?ref={fx.commit}") for f in lock["components"][RL_KEY]["files"]
                            if f["url"].startswith(f"https://{GL}/")))
        lock_ok(self, lock, docs_for(RL_DOCS))

    def test_a_bot_challenge(self):
        """Both fail closed with one line and write nothing. A challenge that
        redirects to a plain path gives item 9's HTTP 418 line; one that keeps
        the API path (%2F) is refused by the hop rules (U7b rework round 1
        item 3: a hop path has no %), which item 9 keeps."""
        fx = ApkFixture()
        gid = "__goaway_id=0000synthetic0nonce0000000000000"
        plain = f"https://{GL}/.within.website/challenge?__goaway_challenge=cookie&{gid}"
        same = fx.raw("APKBUILD") + f"&__goaway_challenge=cookie&{gid}"
        for case, location, why in (
                ("to a plain path", plain, f"{GL}: HTTP 418: {plain}"),
                ("on the same API path", same, f"redirect to {same} refused: not a plain path")):
            with self.subTest(case=case):
                routes = dict(fx.routes(), **{fx.raw("APKBUILD"): (307, {"Location": location}, b""),
                                             location: (418, {}, b"challenge page")})
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp, True)
                code, _, err = run_main(tmp, {RL_KEY: apk_need(fx)}, FakeNet(routes))
                self.assertEqual(code, 1, err)
                self.assertEqual(fail_lines(err), [f"sources_lock: FAIL (resolve: {RL_KEY}: {why}; the lock is unchanged)"])
                self.assertNotIn("lock.new.json", os.listdir(tmp / "out"))


# ==========================================================================
# U7d (design-notes "U7d precision" P1-P6, R1-R6; "P2 amended"; the security
# design review adopted, items 1-7; human rulings A71, A72; orchestrator
# P-R1, P-R2). Fake network only.
# Interface added (tester, U7d RED): `RETRIES` (3), `RETRY_WAITS` (10, 30,
# 60), `SLEEP` (time.sleep), `RUN_RETRIES` (20), `RUN_DEADLINE` (10800),
# module constants read when used; `fetch(url, allow, ..., retries=0)`;
# `parse_deb822(text, label) -> list[dict]`; `parse_dsc` line numbers count
# from the top of the file; main writes `<out>/pgdg-<suite>.InRelease`.
# ==========================================================================

PGDG_HOSTNAME = "apt-archive.postgresql.org"
SUITE = "bookworm-pgdg-archive"
PG_BASE = f"https://{PGDG_HOSTNAME}/pub/repos/apt"
PG_KEYS = ("pgdg:postgresql-16@16.15-1.pgdg12+2", "pgdg:postgresql-18@18.6-1.pgdg12+2",
           "pgdg:postgresql-common@293.pgdg12+1")


def u7d_policy() -> dict[str, Any]:
    """The committed policy; U7d's GREEN adds the tenth host to the file."""
    return policy()


class Recorder:
    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, s: float) -> None:
        self.waits.append(s)


class Seq:
    """A fake OPENER whose url maps to a list of responses, one per call (the
    last repeats); a response is a make() callable or a (status, headers,
    body) tuple."""

    def __init__(self, routes: dict[str, list[Any]]):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> Any:
        self.calls.append(url)
        seq = self.routes.get(url)
        if not seq:
            return SimpleNamespace(status=404, headers={}, body=[b""])
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if callable(item):
            return item()
        status, headers, body = item
        data = body.encode() if isinstance(body, str) else body
        return SimpleNamespace(status=status, headers={k.lower(): v for k, v in headers.items()}, body=[data])


def resolve_raw(mod: ModuleType, needs: dict[str, Any], opener: Any, sleep: Any, *, pol: Any = None
                ) -> tuple[Any, str]:
    """mod.resolve with `opener` and `sleep`; (the result or the ResolveError, stderr)."""
    uv = (ROOT / "uv.lock").read_text(encoding="utf-8")
    e = io.StringIO()
    with mock.patch.object(mod, "OPENER", opener), mock.patch.object(mod, "SLEEP", sleep, create=True), \
            contextlib.redirect_stderr(e):
        try:
            got: Any = mod.resolve(needs, EMPTY_LOCK, pol or u7d_policy(), uv, ARCH, False)
        except rfn("ResolveError") as exc:
            got = exc
    return got, e.getvalue()


def retry_lines(err: str) -> list[str]:
    return [ln for ln in err.splitlines() if ln.startswith("retry ")]


class U7dRetryConstantsTest(unittest.TestCase):

    def test_constants(self):
        mod = load_resolver()
        for name, want in (("RETRIES", 3), ("RETRY_WAITS", (10, 30, 60)), ("RUN_RETRIES", 20), ("RUN_DEADLINE", 10800)):
            with self.subTest(name=name):
                self.assertEqual(getattr(mod, name, None), want)
        self.assertIs(getattr(mod, "SLEEP", None), time.sleep, "R4: SLEEP is time.sleep (tests patch it)")

    def test_fetch_retries_nothing_by_default(self):
        mod = load_resolver()
        rec = Recorder()
        net = Seq({JAXB_URL: [(503, {}, b""), (200, {}, JAR_BODY)]})
        with mock.patch.object(mod, "OPENER", net), mock.patch.object(mod, "SLEEP", rec, create=True):
            with self.assertRaises(rfn("ResolveError")) as caught:
                rfn("fetch")(JAXB_URL, ALLOW)
        self.assertEqual(str(caught.exception), f"{MAVEN}: HTTP 503: {JAXB_URL}")
        self.assertEqual((net.calls, rec.waits), ([JAXB_URL], []), "R1: fetch() is Q61's single call unless asked")

    def test_fetch_with_retries(self):
        mod = load_resolver()
        rec = Recorder()
        net = Seq({JAXB_URL: [(503, {}, b""), (503, {}, b""), (200, {}, JAR_BODY)]})
        e = io.StringIO()
        with mock.patch.object(mod, "OPENER", net), mock.patch.object(mod, "SLEEP", rec, create=True), \
                contextlib.redirect_stderr(e):
            r = rfn("fetch")(JAXB_URL, ALLOW, retries=3)
        self.assertEqual(b"".join(r.body), JAR_BODY)
        self.assertEqual(rec.waits, [10, 30])


class U7dRetryTest(unittest.TestCase):
    """R1-R6 and the security review's items 3-6, through resolve() (RETRIES)."""

    def _maven(self, jar: list[Any], *, sidecar_ok: bool = True) -> tuple[Any, str, Recorder, Seq]:
        mod = load_resolver()
        rec = Recorder()
        net = Seq({JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY) if sidecar_ok else 'f' * 40}  {JAXB_JAR}\n")],
                   JAXB_URL: jar})
        got, err = resolve_raw(mod, JAXB_NEED, net, rec)
        return got, err, rec, net

    def test_retried_statuses(self):
        for code in (500, 502, 503, 504):
            with self.subTest(code=code):
                got, err, rec, net = self._maven([(code, {}, b""), (200, {}, JAR_BODY)])
                self.assertNotIsInstance(got, Exception, str(got))
                self.assertEqual(rec.waits, [10])
                self.assertEqual(retry_lines(err), [f"retry 1/3 in 10 s: {MAVEN}: HTTP {code}: {JAXB_URL}"])
                self.assertEqual(got[0]["components"][JAXB_KEY]["files"][0]["sha256"], sha("sha256", JAR_BODY))

    def test_the_lines_and_waits(self):
        got, err, rec, net = self._maven([(503, {}, b""), (503, {}, b""), (200, {}, JAR_BODY)])
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertEqual(rec.waits, [10, 30])
        self.assertEqual(retry_lines(err), [f"retry 1/3 in 10 s: {MAVEN}: HTTP 503: {JAXB_URL}",
                                            f"retry 2/3 in 30 s: {MAVEN}: HTTP 503: {JAXB_URL}"])

    def test_the_budget_is_exhausted(self):
        got, err, rec, net = self._maven([(503, {}, b"")])
        self.assertIsInstance(got, rfn("ResolveError"))
        self.assertEqual(str(got), f"{JAXB_KEY}: {MAVEN}: HTTP 503: {JAXB_URL}")
        self.assertEqual(rec.waits, [10, 30, 60])
        self.assertEqual(net.calls.count(JAXB_URL), 4)
        self.assertEqual(len(retry_lines(err)), 3)

    def test_timeouts_are_retried(self):
        for case, first in (("socket.timeout at open", raising(socket.timeout("timed out"))),
                            ("a timeout mid-body", body_of([b"partial "], then=TimeoutError()))):
            with self.subTest(case=case):
                got, err, rec, net = self._maven([first, (200, {}, JAR_BODY)])
                self.assertNotIsInstance(got, Exception, str(got))
                self.assertEqual(retry_lines(err), [f"retry 1/3 in 10 s: {MAVEN}: timeout: {JAXB_URL}"])
                f = got[0]["components"][JAXB_KEY]["files"][0]
                self.assertEqual((f["sha256"], f["size"]), (sha("sha256", JAR_BODY), len(JAR_BODY)),
                                 "P-R2: a restart with fresh hashers and size")

    def test_a_5xx_at_a_hop_restarts_from_the_first_url(self):
        mod = load_resolver()
        hop = "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"
        rec = Recorder()
        net = Seq({NEO_URL: [moved(hop)], hop: [(503, {}, b""), (200, {}, NEO_BODY)]})
        got, err = resolve_raw(mod, {NEO_KEY: need(NEO_KEY, "ke-neo4j", "pkg:maven/org.neo4j/neo4j@5.26.32",
                                                   {"ver": "5.26.32"})}, net, rec)
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertEqual(net.calls, [NEO_URL, hop, NEO_URL, hop])
        self.assertEqual(got[1][0]["sha256"], sha("sha256", NEO_BODY))

    def test_a_query_is_omitted_from_retry_lines(self):
        mod = load_resolver()
        hop = "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32?token=signed-abc"
        rec = Recorder()
        net = Seq({NEO_URL: [moved(hop)], hop: [(503, {}, b"")]})
        got, err = resolve_raw(mod, {NEO_KEY: need(NEO_KEY, "ke-neo4j", "pkg:maven/org.neo4j/neo4j@5.26.32",
                                                   {"ver": "5.26.32"})}, net, rec)
        self.assertEqual(retry_lines(err)[0], "retry 1/3 in 10 s: codeload.github.com: HTTP 503: "
                                              "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"
                                              "?<query omitted>")
        self.assertFalse([ln for ln in retry_lines(err) if "signed-abc" in ln])
        self.assertIn("signed-abc", str(got), "security item 5: the FAIL line keeps the url as is")

    def test_never_retried(self):
        mod = load_resolver()
        far = "https://evil.example.com/x.jar"
        six = {f"https://repo1.maven.org/h{i}": [moved(f"https://repo1.maven.org/h{i + 1}")] for i in range(6)}
        rows: dict[str, Any] = {
            "400": [(400, {}, b"")], "403": [(403, {}, b"")], "404": [(404, {}, b"")], "418": [(418, {}, b"")],
            "429 with Retry-After": [(429, {"Retry-After": "1"}, b"")],
            "a 3xx with no Location": [(302, {}, b"")],
            "a non-https Location": [moved("http://repo1.maven.org/x.jar")],
            "an unprintable Location": [moved("https://repo1.maven.org/a" + chr(9) + "b.jar")],
            "a hop to an unlisted host": [moved(far)],
            "a hop with a non-plain path": [moved("https://repo1.maven.org/a%2Fb.jar")],
            "ssl.SSLError": [raising(ssl.SSLError("bad record mac"))],
            "ssl.SSLCertVerificationError": [raising(ssl.SSLCertVerificationError("self signed"))],
            "ConnectionResetError": [raising(ConnectionResetError(104, "reset"))],
            "another OSError": [raising(OSError("no route to host"))],
            "IncompleteRead": [body_of([b"ab"], then=http.client.IncompleteRead(b"ab", 9))],
            "BadStatusLine": [raising(http.client.BadStatusLine("x"))],
        }
        for case, jar in rows.items():
            with self.subTest(case=case):
                rec = Recorder()
                net = Seq(dict({JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}\n")], JAXB_URL: jar}))
                got, err = resolve_raw(mod, JAXB_NEED, net, rec)
                self.assertIsInstance(got, rfn("ResolveError"), case)
                self.assertEqual((net.calls.count(JAXB_URL), rec.waits, retry_lines(err)), (1, [], []), str(got))
        with self.subTest(case="a sixth redirect"):
            rec = Recorder()
            net = Seq(dict(six, **{JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}\n")],
                                   JAXB_URL: [moved("https://repo1.maven.org/h0")]}))
            got, err = resolve_raw(mod, JAXB_NEED, net, rec)
            self.assertIsInstance(got, rfn("ResolveError"))
            self.assertEqual((net.calls.count(JAXB_URL), rec.waits), (1, []))
        with self.subTest(case="the byte cap"):
            rec = Recorder()
            with mock.patch.object(mod, "MAX_BYTES", 100):
                net = Seq({JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}\n")],
                           JAXB_URL: [body_of([b"x" * 60] * 3)]})
                got, err = resolve_raw(mod, JAXB_NEED, net, rec)
            self.assertIn("more than 100 bytes", str(got))
            self.assertEqual((net.calls.count(JAXB_URL), rec.waits), (1, []))
        with self.subTest(case="the per-file deadline"):
            rec = Recorder()
            with mock.patch.object(mod, "DEADLINE", 0.05):
                net = Seq({JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}\n")],
                           JAXB_URL: [body_of([b"a", b"b"], sleep=0.1)]})
                got, err = resolve_raw(mod, JAXB_NEED, net, rec)
            self.assertIn("deadline", str(got))
            self.assertEqual((net.calls.count(JAXB_URL), rec.waits), (1, []))
        with self.subTest(case="a hash mismatch"):
            got, err, rec, net = self._maven([(200, {}, JAR_BODY)], sidecar_ok=False)
            self.assertIn("sha1 mismatch", str(got))
            self.assertEqual((net.calls.count(JAXB_URL), rec.waits), (1, []))

    def test_the_run_budget(self):
        mod = load_resolver()
        rec = Recorder()
        net = Seq({JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}\n")], JAXB_URL: [(503, {}, b"")]})
        with mock.patch.object(mod, "RUN_RETRIES", 2, create=True):
            got, err = resolve_raw(mod, JAXB_NEED, net, rec)
        self.assertEqual(str(got), f"{JAXB_KEY}: retry budget exhausted (2)")
        self.assertEqual(rec.waits, [10, 30])

    def test_the_run_deadline(self):
        mod = load_resolver()
        for case, deadline, want_waits in (("already passed", -1, []), ("a wait that would end past it", 5, [])):
            with self.subTest(case=case):
                rec = Recorder()
                net = Seq({JAXB_URL + ".sha1": [ok(f"{sha('sha1', JAR_BODY)}  {JAXB_JAR}\n")],
                           JAXB_URL: [(503, {}, b"")]})
                with mock.patch.object(mod, "RUN_DEADLINE", deadline, create=True):
                    got, err = resolve_raw(mod, JAXB_NEED, net, rec)
                self.assertEqual(str(got), f"{JAXB_KEY}: run deadline {deadline:g} s passed")
                self.assertEqual(rec.waits, want_waits, "no wait that ends past the run deadline")

    def test_the_snapshot_pause_holds_for_retries(self):
        mod = load_resolver()
        fx = DebFixture(BASH_KEY)
        routes = fx.routes()
        su = snap_url("bash", "5.2.15-2")
        times: list[float] = []

        class Timed(Seq):
            def __call__(self, url: str, timeout: float) -> Any:
                times.append(time.monotonic())
                return super().__call__(url, timeout)
        net = Timed({su: [(503, {}, b""), routes[su]], **{u: [v] for u, v in routes.items() if u != su}})
        with mock.patch.object(mod, "SNAPSHOT_PAUSE", 0.3):
            got, err = resolve_raw(mod, {BASH_KEY: deb_need(BASH_KEY)}, net, Recorder())
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertEqual(len(times), 3)
        self.assertTrue(all(b - a >= 0.28 for a, b in zip(times, times[1:])), f"R6: {times}")


class U7dCarriedTest(unittest.TestCase):
    """U7c review R1-N2 and the security review's item 1 (per-stanza
    duplicates); the shared parse_deb822 (P2 amended (3))."""

    def setUp(self) -> None:
        self.mod = load_resolver()
        no_pause(self, self.mod)

    def test_a_line_that_is_not_a_field(self):
        fx = DebFixture(BASH_KEY)
        text_ = fx.text(armour=False)
        lines = text_.split("\n")
        lines.insert(3, "this is not a field")
        with network(self.mod, fx.routes("\n".join(lines))):
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(self.mod, {BASH_KEY: deb_need(BASH_KEY)})
        self.assertEqual(str(caught.exception), f"{BASH_KEY}: {fx.dsc}: line 4 is not a field or continuation")

    def test_parse_deb822(self):
        p = rfn("parse_deb822")
        two = "Package: a\nVersion: 1\n\nPackage: b\nVersion: 2\n Files: x\n"
        self.assertEqual([x["Package"] for x in p(two, "Sources")], ["a", "b"], "two stanzas each with Package")
        with self.assertRaises(rfn("ResolveError")) as caught:
            p("Package: a\nPackage: b\n", "x Sources")
        self.assertEqual(str(caught.exception), "x Sources: duplicate field Package")
        on_line = p("Checksums-Sha256: " + "a" * 64 + " 3 x.dsc\n " + "b" * 64 + " 4 y.tar\n", "s")[0]
        continued = p("Checksums-Sha256:\n " + "a" * 64 + " 3 x.dsc\n " + "b" * 64 + " 4 y.tar\n", "s")[0]
        self.assertEqual(on_line, continued, "a first entry on the field line parses as a continuation does")

    def test_a_dsc_with_its_first_entry_on_the_field_line(self):
        fx = DebFixture(BASH_KEY)
        good = fx.text(armour=False)
        on_line = good.replace("Checksums-Sha256:\n ", "Checksums-Sha256: ", 1)
        with network(self.mod, fx.routes(on_line)):
            lock, _, _ = resolve(self.mod, {BASH_KEY: deb_need(BASH_KEY)})
        self.assertEqual(sorted(f["name"] for f in lock["components"][BASH_KEY]["files"]),
                         sorted([fx.dsc, *fx.files]))
        bad = good.replace("Checksums-Sha256:\n ", "Checksums-Sha256: abc 12 x.tar.xz\n ", 1)
        with network(self.mod, fx.routes(bad)):
            with self.assertRaises(rfn("ResolveError")) as caught:
                resolve(self.mod, {BASH_KEY: deb_need(BASH_KEY)})
        self.assertEqual(str(caught.exception), f"{BASH_KEY}: {fx.dsc}: bad Checksums-Sha256 line")


# --------------------------------------------------------------------------
# The pgdg route (P1-P6 with "P2 amended" and the security review's item 2)
# --------------------------------------------------------------------------

def pg_pool(src: str) -> str:
    return src[:4] if src.startswith("lib") else src[:1]


class PgdgFixture:
    """apt-archive.postgresql.org for a suite: a clearsigned InRelease whose
    SHA256 binds the uncompressed Sources (first entries on the field line,
    as the real index), the .dsc files in the pool."""

    def __init__(self, keys: tuple[str, ...] = PG_KEYS, suite: str = SUITE):
        self.suite = suite
        self.debs: dict[str, DebFixture] = {}
        for key in keys:
            fx = DebFixture("deb:" + key.split(":", 1)[1])
            fx.key = key
            self.debs[key] = fx

    def dsc_text(self, key: str) -> str:
        return self.debs[key].text()

    def stanza(self, key: str, *, directory: str | None = None, with_dsc: bool = True, dsc_sha: str | None = None,
               dup_package: bool = False) -> str:
        fx = self.debs[key]
        body = self.dsc_text(key).encode()
        listed = ([(dsc_sha or sha("sha256", body), len(body), fx.dsc)] if with_dsc else []) + [
            (sha("sha256", b), len(b), n) for n, b in fx.files.items()]
        md5 = [(hashlib.md5(body).hexdigest(), len(body), fx.dsc)] + [
            (hashlib.md5(b).hexdigest(), len(b), n) for n, b in fx.files.items()]
        lines = [f"Package: {fx.src}"] + (["Package: dup"] if dup_package else []) + [
            "Format: 3.0 (quilt)", f"Binary: {fx.src}", "Architecture: any", f"Version: {fx.ver}",
            "Maintainer: Fixture <fixture@example.invalid>",
            f"Package-List: {fx.src} deb database optional arch=any", f" {fx.src}-doc deb doc optional arch=all",
            f"Directory: {directory or f'pool/main/{pg_pool(fx.src)}/{fx.src}'}"]
        for field, rows in (("Files", md5), ("Checksums-Sha256", listed)):
            lines.append(f"{field}: {rows[0][0]} {rows[0][1]} {rows[0][2]}")
            lines += [f" {h} {z} {n}" for h, z, n in rows[1:]]
        return "\n".join(lines) + "\n"

    def sources(self, **kw: Any) -> bytes:
        other = ("Package: pgadmin4\nVersion: 9.9-1.pgdg12+1\nDirectory: pool/main/p/pgadmin4\n"
                 "Checksums-Sha256: " + "c" * 64 + " 10 pgadmin4_9.9-1.pgdg12+1.dsc\n")
        stanzas = [other] + [self.stanza(k, **(kw.get(k) or {})) for k in self.debs]
        return "\n".join(stanzas).encode()

    def inrelease(self, sources: bytes, *, entries: list[str] | None = None) -> bytes:
        rows = entries if entries is not None else [
            f" {'d' * 64} 1234 main/binary-amd64/Packages",
            f" {sha('sha256', sources)} {len(sources)} main/source/Sources",
            f" {'e' * 64} 99 main/source/Sources.bz2"]
        body = ("Origin: apt-archive.postgresql.org\nLabel: PostgreSQL for Debian/Ubuntu archive repository\n"
                f"Suite: {self.suite}\nCodename: {self.suite}\nMD5Sum:\n {'f' * 32} {len(sources)} main/source/Sources\n"
                "SHA256:\n" + "\n".join(rows) + "\n")
        return ("-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n" + body
                + "-----BEGIN PGP SIGNATURE-----\n\niQIzBAEBCgAdFiEEfixture\n=abcd\n-----END PGP SIGNATURE-----\n").encode()

    def urls(self) -> dict[str, str]:
        return {"inrelease": f"{PG_BASE}/dists/{self.suite}/InRelease",
                "sources": f"{PG_BASE}/dists/{self.suite}/main/source/Sources"}

    def pool(self, key: str, name: str) -> str:
        fx = self.debs[key]
        return f"{PG_BASE}/pool/main/{pg_pool(fx.src)}/{fx.src}/{name}"

    def routes(self, *, sources: bytes | None = None, inrelease: bytes | None = None,
               dsc: dict[str, bytes] | None = None) -> dict[str, Any]:
        src = self.sources() if sources is None else sources
        r: dict[str, Any] = {self.urls()["inrelease"]: ok(inrelease if inrelease is not None else self.inrelease(src)),
                             self.urls()["sources"]: ok(src)}
        for key, fx in self.debs.items():
            r[self.pool(key, fx.dsc)] = ok((dsc or {}).get(key, self.dsc_text(key).encode()))
        return r

    def entry(self, key: str) -> dict[str, Any]:
        fx = self.debs[key]
        body = self.dsc_text(key).encode()
        files = [{"name": fx.dsc, "url": self.pool(key, fx.dsc), "sha256": sha("sha256", body), "size": len(body),
                  "upstream": {"alg": "sha256", "value": sha("sha256", body), "from": f"{PGDG_HOSTNAME} {self.suite} Sources"}}]
        for n, b in fx.files.items():
            files.append({"name": n, "url": self.pool(key, n), "sha256": sha("sha256", b), "size": len(b),
                          "upstream": {"alg": "sha256", "value": sha("sha256", b), "from": f"{fx.dsc} Checksums-Sha256"}})
        return {"kind": "pgdg", "arches": [ARCH], "origin": "generated", "suite": self.suite, "files": files}


def pg_need(key: str, suite: str = SUITE, **route: Any) -> dict[str, Any]:
    src, _, ver = key.split(":", 1)[1].rpartition("@")
    r = {"src": src, "ver": ver, "suite": suite}
    r.update(route)
    return need(key, "postgres", f"pkg:deb/debian/{src}@{quote(ver, safe='')}?arch=amd64&distro=debian-12.15",
                {k: v for k, v in r.items() if v is not ...})


PG_DOCS = {"postgres": [{"purl": f"pkg:deb/debian/{k.split(':', 1)[1].rpartition('@')[0]}@"
                                 f"{quote(k.rpartition('@')[2], safe='')}?arch=amd64&distro=debian-12.15",
                         "declared": "GPL-2.0-only"} for k in PG_KEYS]}


class U7dPgdgRouteTest(unittest.TestCase):

    def setUp(self) -> None:
        self.mod = load_resolver()

    def _resolve(self, routes: dict[str, Any], keys: tuple[str, ...] = PG_KEYS) -> tuple[Any, FakeNet]:
        with network(self.mod, routes) as net:
            try:
                got: Any = resolve(self.mod, {k: pg_need(k) for k in keys})
            except rfn("ResolveError") as exc:
                got = exc
        return got, net

    def test_the_entries(self):
        fx = PgdgFixture()
        got, net = self._resolve(fx.routes())
        self.assertNotIsInstance(got, Exception, str(got))
        lock, _, skipped = got
        self.assertEqual(skipped, [], "U7d: pgdg is not skipped")
        for key in PG_KEYS:
            with self.subTest(key=key):
                self.assertEqual(by_name(lock["components"][key]), by_name(fx.entry(key)))
        self.assertEqual(net.calls.count(fx.urls()["inrelease"]), 1, "one InRelease fetch per suite per run")
        self.assertEqual(net.calls.count(fx.urls()["sources"]), 1, "one Sources fetch per suite per run")
        self.assertEqual(net.calls[:2], [fx.urls()["inrelease"], fx.urls()["sources"]], "InRelease before Sources")
        self.assertEqual(sorted(net.calls[2:]), sorted(fx.pool(k, fx.debs[k].dsc) for k in PG_KEYS),
                         "only the .dsc files are fetched from the pool")
        lock_ok(self, lock, docs_for(PG_DOCS))

    def test_the_pool_rule(self):
        key = "pgdg:libpqxx@7.8.1-1.pgdg12+1"
        fx = PgdgFixture((key,))
        got, net = self._resolve(fx.routes(), (key,))
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertTrue(all(f["url"].startswith(f"{PG_BASE}/pool/main/libp/libpqxx/")
                            for f in got[0]["components"][key]["files"]))

    def test_main_writes_the_inrelease(self):
        fx = PgdgFixture()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        code, _, err = run_main(tmp, {k: pg_need(k) for k in PG_KEYS}, FakeNet(fx.routes()))
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(os.listdir(tmp / "out")), ["lock.new.json", f"pgdg-{SUITE}.InRelease"])
        self.assertEqual((tmp / "out" / f"pgdg-{SUITE}.InRelease").read_bytes(), fx.inrelease(fx.sources()),
                         "security R-1: the raw InRelease the run used")

    def test_failures(self):
        fx = PgdgFixture()
        k = "pgdg:postgresql-common@293.pgdg12+1"
        dsc = fx.debs[k].dsc
        src = fx.sources()
        n = len(src)
        good = fx.routes()
        bad_dsc = fx.dsc_text(k).encode() + b"tampered"
        rows: dict[str, tuple[dict[str, Any], str]] = {
            "InRelease without a Sources entry": (fx.routes(inrelease=fx.inrelease(src, entries=[
                f" {'d' * 64} 1 main/binary-amd64/Packages"])), "Release lists no Sources sha256"),
            "a Sources entry without a valid hash": (fx.routes(inrelease=fx.inrelease(src, entries=[
                f" xyz {n} main/source/Sources"])), "Release lists no Sources sha256"),
            "two Sources entries": (fx.routes(inrelease=fx.inrelease(src, entries=[
                f" {sha('sha256', src)} {n} main/source/Sources", f" {'a' * 64} {n} main/source/Sources"])),
                "Release lists Sources sha256 more than once"),
            "Sources one byte longer": (dict(fx.routes(inrelease=fx.inrelease(src)), **{
                fx.urls()["sources"]: ok(src + b"x")}), f"{SUITE} Sources: size {n + 1} differs from Release {n}"),
            "Sources one byte shorter": (dict(fx.routes(inrelease=fx.inrelease(src)), **{
                fx.urls()["sources"]: ok(src[:-1])}), f"{SUITE} Sources: size {n - 1} differs from Release {n}"),
            "Sources with a flipped byte": (dict(fx.routes(inrelease=fx.inrelease(src)), **{
                fx.urls()["sources"]: ok(src[:-2] + bytes([src[-2] ^ 1]) + src[-1:])}),
                f"{SUITE} Sources: sha256 mismatch against Release"),
            "no stanza": (fx.routes(sources=PgdgFixture(PG_KEYS[:2]).sources()),
                          f"{SUITE} Sources has no postgresql-common 293.pgdg12+1"),
            "the stanza twice": (fx.routes(sources=src + b"\n" + fx.stanza(k).encode()),
                                 f"{SUITE} Sources lists postgresql-common 293.pgdg12+1 more than once"),
            "a wrong Directory": (fx.routes(sources=fx.sources(**{k: {"directory": "pool/main/q/postgresql-common"}})),
                                  "postgresql-common: Sources Directory pool/main/q/postgresql-common is not "
                                  "pool/main/p/postgresql-common"),
            "no .dsc in the stanza": (fx.routes(sources=fx.sources(**{k: {"with_dsc": False}})),
                                      f"{SUITE} Sources: no .dsc for postgresql-common 293.pgdg12+1"),
            "a duplicate field in a stanza": (fx.routes(sources=fx.sources(**{k: {"dup_package": True}})),
                                              f"{SUITE} Sources: duplicate field Package"),
            "the .dsc sha256": (dict(good, **{fx.pool(k, dsc): ok(bad_dsc)}),
                                f"{dsc}: sha256 mismatch: got {sha('sha256', bad_dsc)}, {SUITE} Sources says "
                                f"{sha('sha256', fx.dsc_text(k).encode())}"),
        }
        other = PgdgFixture()
        other.debs[k].files = {f"postgresql-common_293.pgdg12+1.tar.xz": b"another tarball"}
        rows["Sources and .dsc list different files"] = (
            dict(fx.routes(sources=other.sources(**{k: {"dsc_sha": sha("sha256", fx.dsc_text(k).encode())}})),
                 **{fx.pool(k, dsc): ok(fx.dsc_text(k).encode())}),
            f"{dsc}: Sources and .dsc list different files")
        for case, (routes, why) in rows.items():
            with self.subTest(case=case):
                got, net = self._resolve(routes, (k,))
                self.assertIsInstance(got, rfn("ResolveError"), case)
                self.assertEqual(str(got), f"{k}: {why}")
                self.assertFalse([u for u in net.calls if u.endswith(".tar.xz") or u.endswith(".tar.bz2")])

    def test_the_caps(self):
        fx = PgdgFixture()
        k = "pgdg:postgresql-common@293.pgdg12+1"
        with self.subTest(case="Sources over 64 MiB"):
            huge = 64 * 1048576 + 7
            inrel = fx.inrelease(b"", entries=[f" {'a' * 64} {huge} main/source/Sources"])
            routes = {fx.urls()["inrelease"]: lambda: SimpleNamespace(status=200, headers={}, body=[inrel]),
                      fx.urls()["sources"]: body_of([b"\0" * 1048576] * 65)}
            mod = self.mod
            with mock.patch.object(mod, "OPENER", Opener(routes)), mock.patch.object(mod, "SLEEP", lambda s: None,
                                                                                    create=True):
                with self.assertRaises(rfn("ResolveError")) as caught:
                    mod.resolve({k: pg_need(k)}, EMPTY_LOCK, u7d_policy(), "", ARCH, False)
            self.assertEqual(str(caught.exception), f"{k}: {SUITE} Sources: more than 67108864 bytes")
        with self.subTest(case="a .dsc over 1 MiB"):
            pad = PgdgFixture()
            big = pad.debs[k].text() + "X-Pad: " + "x" * 1048576 + "\n"
            pad.dsc_text = lambda key, _t=big, _k=k, _o=pad.dsc_text: _t if key == _k else _o(key)  # type: ignore
            got, net = self._resolve(pad.routes(), (k,))
            self.assertEqual(str(got), f"{k}: {pad.debs[k].dsc}: more than 1048576 bytes")

    def test_a_malformed_route(self):
        for field, route in (("suite", {"suite": ...}), ("suite", {"suite": "bookworm-pgdg"}), ("src", {"src": "x"})):
            with self.subTest(field=field, route=repr(route)):
                with network(self.mod, PgdgFixture().routes()) as net:
                    with self.assertRaises(rfn("ResolveError")) as caught:
                        resolve(self.mod, {PG_KEYS[2]: pg_need(PG_KEYS[2], **route)})
                self.assertTrue(str(caught.exception).startswith(f"{PG_KEYS[2]}: "), str(caught.exception))
                self.assertEqual(net.calls, [], "a request was made with a malformed route")


class U7dLockNeedsTest(unittest.TestCase):
    """P1: the pgdg route {src, ver, suite}, the suite from the purl distro major."""

    def _doc(self, rows: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any], list[str]]:
        return getattr(load_sbom_check(), "lock_needs_doc")(policy(), docs_for(rows), {}, {})

    def test_the_fixture_routes(self):
        doc, problems = getattr(load_sbom_check(), "lock_needs_doc")(policy(), fixture_docs(), {"ke-neo4j": RELEASE},
                                                                    apk_inputs(fixture_docs()))
        self.assertEqual(problems, [])
        for key in PG_KEYS:
            src, _, ver = key.split(":", 1)[1].rpartition("@")
            self.assertEqual(doc["needs"][key]["route"], {"src": src, "ver": ver, "suite": SUITE})

    def test_trixie_and_unknown(self):
        k = "pgdg:postgresql-common@293.pgdg13+1"
        purl = "pkg:deb/debian/postgresql-common@293.pgdg13%2B1?arch=amd64&distro=debian-{}"
        doc, problems = self._doc({"postgres": [{"purl": purl.format("13.1"), "declared": "GPL-2.0-only"}]})
        self.assertEqual((problems, doc["needs"][k]["route"]["suite"]), ([], "trixie-pgdg-archive"))
        doc, problems = self._doc({"postgres": [{"purl": purl.format("11.9"), "declared": "GPL-2.0-only"}]})
        self.assertIn(f"{k}: postgres: no pgdg suite for distro debian-11.9", problems)
        self.assertNotIn(k, doc["needs"])
        client = ("pkg:deb/debian/postgresql-client-common@293.pgdg13%2B1?arch=all&distro=debian-13.1"
                  "&upstream=postgresql-common")
        doc, problems = self._doc({"postgres": [{"purl": purl.format("12.1"), "declared": "GPL-2.0-only"},
                                                {"purl": client, "declared": "GPL-2.0-only"}]})
        # U7d rework round 1, item 3: one shared derivation, its text (was "no pgdg suite for distro ...").
        self.assertIn(f"{k}: packages derive suites bookworm-pgdg-archive, trixie-pgdg-archive", problems)
        self.assertNotIn(k, doc["needs"])


class U7dCoverageTest(unittest.TestCase):
    """The orchestrator's item 6: with the fixture docs and the ten-host
    policy, every fixture key (183 since U7e, 182 in U7d; the count is
    pinned in the method, not its name) resolves in the fake network (neo4j as the TOFU
    candidate, written by hand) and the lock passes lock_problems."""

    def test_every_fixture_key_resolves(self):
        mod = load_resolver()
        no_pause(self, mod)
        check = load_sbom_check()
        docs = fixture_docs()
        needs_all, problems = check.lock_needs(policy(), docs)
        # 182 -> 183 in U7e: u7e/key-diff.txt l.6-8 (+2 -1 deb keys; base-dpkg-diff.txt).
        self.assertEqual((problems, len(needs_all)), ([], 183))
        needs: dict[str, Any] = {}
        routes: dict[str, Any] = {}
        pg = PgdgFixture(tuple(k for k in needs_all if k.startswith("pgdg:")))
        routes.update(pg.routes())
        routes.update(maven_routes())
        routes.update(temurin_routes())
        routes[NEO_URL] = ok(NEO_BODY)
        for key, e in sorted(needs_all.items()):
            kind = key.split(":", 1)[0]
            name, _, ver = key.split(":", 1)[1].rpartition("@")
            route: dict[str, Any] = {}
            if kind == "deb":
                route = {"src": name, "ver": ver}
                routes.update(DebFixture(key).routes())
            elif kind == "pgdg":
                route = {"src": name, "ver": ver, "suite": SUITE}
            elif kind == "apk":
                distro = {unquote(q.partition("=")[2]) for p in e["packages"]
                          for q in str(p["purl"]).partition("?")[2].split("&") if q.startswith("distro=")}
                x, y, _ = distro.pop().split("-", 1)[1].split(".")
                fx = ApkFixture(key, commit=aports_commit(name, ver), branch=f"v{x}.{y}")
                route = {"origin": name, "ver": ver, "commit": fx.commit, "branch": fx.branch}
                routes.update(fx.routes())
            elif kind == "temurin":
                route = {"sbom_version": "21.0.12.1+1-LTS", "release": RELEASE}
            elif kind == "neo4j":
                route = {"ver": ver}
            elif kind == "maven":
                g, _, a = name.partition(":")
                route = {"g": g, "a": a, "v": ver}
            elif kind == "pypi":
                route = {"name": name, "ver": ver}
                body = f"sdist of {key}".encode()
                dist = f"{name}-{ver}.tar.gz"
                url = "https://files.pythonhosted.org/packages/ab/cd/" + sha("sha256", body)[:60] + "/" + dist
                routes[f"https://pypi.org/pypi/{name}/{ver}/json"] = ok(json.dumps({
                    "info": {"name": name, "version": ver},
                    "urls": [{"packagetype": "sdist", "url": url, "digests": {"sha256": sha("sha256", body)},
                              "size": len(body)}]}))
                routes[url] = ok(body)
            needs[key] = {"kind": kind, "packages": e["packages"], "route": route}
        with network(mod, routes):
            lock, cands, skipped = resolve(mod, needs)
        self.assertEqual(skipped, [])
        self.assertEqual([c["key"] for c in cands], [NEO_KEY])
        lock["components"][NEO_KEY] = good_entry(NEO_KEY)
        self.assertEqual(set(lock["components"]), set(needs_all))
        self.assertEqual(check.lock_problems(check.lock_text(lock), u7d_policy(), docs, ARCH), [])


class U7dScriptStaticTest(unittest.TestCase):
    """Security item 2: sources_lock.sh keeps the run's InRelease for gpgv."""

    def test_the_inrelease_is_copied(self):
        # U7d rework round 1, items 4 and 6: to --evidence-dir, before the move, regular files only
        # (was: any cp of pgdg-*.InRelease within 4 lines).
        code = "\n".join(ln for ln in LOCK_SH.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
        self.assertIn("pgdg-*.InRelease", code)
        self.assertIn("cp -P -- ", code)
        self.assertIn('[ -L "$f" ]', code)
        self.assertIn("--evidence-dir", code)
        self.assertNotIn("u7d", code, "no evidence path is hard-coded")
        self.assertLess(code.index("cp -P -- "), code.index('mv -f -- "$tmp" docker/sources.lock.json'),
                        "the InRelease is copied before the lock moves")


# ==========================================================================
# U7d rework round 1 (design-notes "U7d rework round 1", items 1-4, 6, 8;
# u7d/review.md B1, B2, N1, N2; security L-1, I-2; u7d/lock-run-1.raw).
# ==========================================================================

def link_meta(target: bytes, **override: Any) -> Any:
    """The files-API metadata of a symlink blob (its content is the target)."""
    doc = {"file_name": "link", "encoding": "base64", "size": len(target),
           "content": base64.b64encode(target).decode(), "content_sha256": sha("sha256", target)}
    doc.update(override)
    return ok(json.dumps(doc))


def link_item(origin: str, name: str, rel: str | None = None, repo: str = "main") -> dict[str, Any]:
    return {"id": sha("sha1", name.encode()), "name": name, "type": "blob", "path": f"{repo}/{origin}/{rel or name}",
            "mode": "120000"}


class ReworkR1U7dUrlErrorTest(unittest.TestCase):
    """Item 1 (B1): the real opener unwraps URLError; a timeout reason is
    retried, any other reason is not."""

    def _fresh(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location("ke_sources_resolve_urlerror", RESOLVER)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    REASONS = (("TimeoutError", TimeoutError("timed out"), TimeoutError),
               ("socket.timeout", socket.timeout("timed out"), TimeoutError),
               ("SSLCertVerificationError", ssl.SSLCertVerificationError("bad cert"), ssl.SSLCertVerificationError),
               ("ConnectionRefusedError", ConnectionRefusedError(111, "refused"), ConnectionRefusedError),
               ("a string", "x", urllib.error.URLError))

    def test_the_mapping(self):
        mod = self._fresh()
        for case, reason, cls in self.REASONS:
            with self.subTest(case=case):
                fake = SimpleNamespace(open=mock.Mock(side_effect=urllib.error.URLError(reason)))
                with mock.patch("urllib.request.build_opener", return_value=fake):
                    with self.assertRaises(cls) as caught:
                        mod.OPENER(JAXB_URL, 5)
                if cls is not urllib.error.URLError:
                    self.assertNotIsInstance(caught.exception, urllib.error.URLError, "the URLError was not unwrapped")

    def test_through_resolve(self):
        mod = self._fresh()
        sidecar_url = JAXB_URL + ".sha1"
        for case, reason, cls in self.REASONS:
            with self.subTest(case=case):
                fake = SimpleNamespace(open=mock.Mock(side_effect=urllib.error.URLError(reason)))
                rec = Recorder()
                e = io.StringIO()
                got: Any = None
                with mock.patch("urllib.request.build_opener", return_value=fake),                         mock.patch.object(mod, "SLEEP", rec), contextlib.redirect_stderr(e):
                    try:
                        mod.resolve(JAXB_NEED, EMPTY_LOCK, u7d_policy(), "", ARCH, False)
                    except mod.ResolveError as exc:
                        got = exc
                err = e.getvalue()
                self.assertIsInstance(got, mod.ResolveError)
                if cls is TimeoutError:
                    self.assertEqual(str(got), f"{JAXB_KEY}: {MAVEN}: timeout after 60 s: {sidecar_url}")
                    self.assertEqual((rec.waits, fake.open.call_count), ([10, 30, 60], 4))
                    self.assertEqual(retry_lines(err)[0], f"retry 1/3 in 10 s: {MAVEN}: timeout: {sidecar_url}")
                else:
                    self.assertEqual(str(got), f"{JAXB_KEY}: {MAVEN}: {cls.__name__}: {sidecar_url}")
                    self.assertEqual((rec.waits, fake.open.call_count, retry_lines(err)), ([], 1, []))


class ReworkR1U7dSymlinkTest(unittest.TestCase):
    """Item 8 (u7d/lock-run-1.raw): a mode-120000 entry is skipped when it
    names a regular blob in its own directory; anything else is refused."""

    KEY = "apk:alpine-baselayout@3.7.2-r1"

    def _fx(self) -> ApkFixture:
        fx = ApkFixture(self.KEY, commit=aports_commit("alpine-baselayout", "3.7.2-r1"), branch="v3.24")
        return fx

    def _resolve(self, fx: ApkFixture, routes: dict[str, Any]) -> tuple[Any, str]:
        mod = load_resolver()
        seq = Seq({u: [v] for u, v in routes.items()})
        need_ = need(fx.key, "valkey", "pkg:apk/alpine/alpine-baselayout@3.7.2-r1?arch=x86_64&distro=alpine-3.24.2",
                     {"origin": fx.origin, "ver": fx.ver, "commit": fx.commit, "branch": fx.branch})
        return resolve_raw(mod, {fx.key: need_}, seq, Recorder())

    def _routes(self, fx: ApkFixture, links: list[dict[str, Any]], metas: dict[str, Any],
                apkbuild: str | None = None) -> dict[str, Any]:
        r = fx.routes(apkbuild, listing=fx.listing("main", links))
        r.update(metas)
        return r

    def test_the_real_shape(self):
        fx = self._fx()
        up, inst = "alpine-baselayout.post-upgrade", "alpine-baselayout.post-install"
        routes = self._routes(fx, [link_item(fx.origin, up)], {fx.files_api(up): link_meta(inst.encode())})
        got, err = self._resolve(fx, routes)
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertEqual(by_name(got[0]["components"][self.KEY]), by_name(fx.entry()), "the link is not locked")
        # U7d rework round 1, item 10: the line starts with the key (was the origin).
        self.assertEqual([ln for ln in err.splitlines() if "symlink" in ln],
                         [f"{self.KEY}: main/alpine-baselayout/{up} -> {inst} (symlink to a locked file, skipped)"])
        lock_ok(self, got[0], docs_for({"valkey": [
            {"purl": "pkg:apk/alpine/alpine-baselayout@3.7.2-r1?arch=x86_64&distro=alpine-3.24.2",
             "declared": "GPL-2.0-only"}]}))

    def test_refused_links(self):
        fx = self._fx()
        c = fx.commit
        ln = "alpine-baselayout.post-upgrade"
        inst = b"alpine-baselayout.post-install"
        refused = f"alpine-baselayout: main/alpine-baselayout/{ln} at {c} is not a regular file"
        rows: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {
            "a link to another directory": ([], {fx.files_api(ln): link_meta(b"../other/x")}),
            "an absolute target": ([], {fx.files_api(ln): link_meta(b"/etc/passwd")}),
            "a missing name": ([], {fx.files_api(ln): link_meta(b"missing.patch")}),
            "a tree": ([], {fx.files_api(ln): link_meta(b"patches")}),
            "a target in a subdirectory": ([], {fx.files_api(ln): link_meta(b"sub-fix.patch")}),
            "a dot": ([], {fx.files_api(ln): link_meta(b".")}),
            "a target with a newline": ([], {fx.files_api(ln): link_meta(b"alpine-baselayout.post-install\n")}),
            "invalid base64": ([], {fx.files_api(ln): link_meta(inst, content="!!!not base64!!!")}),
            "over 1 KiB": ([], {fx.files_api(ln): link_meta(b"a" * 1025)}),
            "not base64 encoded": ([], {fx.files_api(ln): link_meta(inst, encoding="text")}),
            "content_sha256 mismatch": ([], {fx.files_api(ln): link_meta(inst, content_sha256="0" * 64)}),
            "a chain": ([link_item(fx.origin, "second.link")], {fx.files_api(ln): link_meta(b"second.link"),
                                                                 fx.files_api("second.link"): link_meta(inst)}),
        }
        for case, (extra_links, metas) in rows.items():
            with self.subTest(case=case):
                routes = self._routes(fx, [link_item(fx.origin, ln)] + extra_links, metas)
                got, err = self._resolve(fx, routes)
                self.assertIsInstance(got, rfn("ResolveError"), case)
                self.assertIn(str(got), (f"{self.KEY}: {refused}",
                                         f"{self.KEY}: alpine-baselayout: main/alpine-baselayout/second.link at {c} "
                                         "is not a regular file"))
        with self.subTest(case="a link named in sha512sums"):
            sums = fx.sums() + f"{'a' * 128}  {ln}\n"
            routes = self._routes(fx, [link_item(fx.origin, ln)], {fx.files_api(ln): link_meta(inst)},
                                  apkbuild=fx.apkbuild(sums=sums))
            got, err = self._resolve(fx, routes)
            self.assertEqual(str(got), f"{self.KEY}: alpine-baselayout: {ln} is a symlink named in sha512sums")
        with self.subTest(case="a submodule still fails"):
            sub = {"id": "e" * 40, "name": "sub", "type": "commit", "path": "main/alpine-baselayout/sub", "mode": "160000"}
            got, err = self._resolve(fx, self._routes(fx, [sub], {}))
            self.assertEqual(str(got), f"{self.KEY}: alpine-baselayout: main/alpine-baselayout/sub at {c} is not a "
                                       "regular file")


class ReworkR1U7dScriptTest(_BundleBase, unittest.TestCase):
    """Items 2 (B2), 4 (N2) and 6 (security L-1), through sources_lock.sh on
    fake docker."""

    def setUp(self) -> None:
        super().setUp()
        for rel in ("docker/source-policy.json", SOURCES_YML):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.repo / rel)
        self.lock = self.repo / "docker" / "sources.lock.json"
        self.check = load_sbom_check()
        self.syft_log = self.tmp / "syft.jsonl"
        self.resolve_log = self.tmp / "resolve.log"
        self.evdir = self.tmp / "evidence"
        self.evdir.mkdir()

    _commit_lock = ReworkR1LockScriptRunTest._commit_lock
    _run = ReworkR1LockScriptRunTest._run
    _steps = staticmethod(ReworkR1LockScriptRunTest._steps)

    def _temps(self) -> list[str]:
        return sorted(p.name for p in (self.repo / "docker").iterdir() if p.name.startswith(".sources.lock.json."))

    def _shims(self, plant: str | None = None, fail_cp: bool = False) -> tuple[str, Path]:
        """A PATH with: a docker wrapper that plants `<out>/pgdg-...InRelease`
        after the sources-resolve run, and cp/mv wrappers that log their calls."""
        d = self.tmp / f"shims-{plant}-{fail_cp}"
        d.mkdir()
        log = d / "calls.log"
        fake = self.tmp / "fakebin" / "docker"
        planting = {"file": "printf 'signed release text\\n' > \"$KE_SOURCES_OUT/pgdg-bookworm-pgdg-archive.InRelease\"",
                    "link": "ln -s /etc/hostname \"$KE_SOURCES_OUT/pgdg-bookworm-pgdg-archive.InRelease\"",
                    "dir": "mkdir \"$KE_SOURCES_OUT/pgdg-bookworm-pgdg-archive.InRelease\"",
                    None: ":"}[plant]
        (d / "docker").write_text("#!/bin/bash\n" f"'{fake}' \"$@\"\nrc=$?\n"
                                  "case \" $* \" in *\" docker-compose.sources.yml run \"*) " + planting + " ;; esac\n"
                                  "exit $rc\n", encoding="utf-8", newline="\n")
        for tool in ("cp", "mv"):
            real = shutil.which(tool)
            fail = ("for a in \"$@\"; do case \"$a\" in *InRelease*) echo 'cp: injected failure' >&2; exit 1 ;; esac; done\n"
                    if (tool == "cp" and fail_cp) else "")
            (d / tool).write_text("#!/bin/bash\n" f"echo \"{tool} $*\" >> '{log}'\n" + fail + f"exec '{real}' \"$@\"\n",
                                  encoding="utf-8", newline="\n")
        for f in d.iterdir():
            f.chmod(0o755)
        return f"{d}{os.pathsep}{self.path}", log

    def test_the_option_is_required(self):
        self._commit_lock(HAPPY_ROWS)
        r, calls = self._run({}, args=("--arch", "amd64"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(calls, [], "docker was called without --evidence-dir")

    def test_the_directory_must_be_writable(self):
        _, docs, before = self._commit_lock(HAPPY_ROWS)
        ro = self.tmp / "read-only"
        ro.mkdir()
        ro.chmod(0o555)
        self.addCleanup(ro.chmod, 0o755)
        for case, path in (("missing", self.tmp / "nowhere"), ("read-only", ro)):
            with self.subTest(case=case):
                if case == "read-only" and os.access(ro, os.W_OK):
                    self.skipTest("running as root: a 0555 directory is writable")
                r, calls = self._run(docs, args=("--arch", "amd64", "--evidence-dir", str(path)))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(f"sources_lock: FAIL (evidence: {path} is not a writable directory; the lock is unchanged)",
                              r.stderr.splitlines())
                self.assertFalse([c for c in calls if c[:1] == ["save"]], "it saved an image")
                self.assertEqual(self.lock.read_bytes(), before)

    def test_the_inrelease_is_copied_before_the_move(self):
        _, docs, _ = self._commit_lock(HAPPY_ROWS)
        path, log = self._shims("file")
        r, _ = self._run(docs, path=path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        self.assertEqual((self.evdir / "pgdg-bookworm-pgdg-archive.InRelease").read_text(encoding="utf-8"),
                         "signed release text\n")
        lines = log.read_text(encoding="utf-8").splitlines()
        cp_at = next(i for i, ln in enumerate(lines) if ln.startswith("cp ") and "InRelease" in ln)
        mv_at = next(i for i, ln in enumerate(lines) if ln.startswith("mv ") and ln.endswith("docker/sources.lock.json"))
        self.assertLess(cp_at, mv_at, "the InRelease was copied after the lock moved")
        self.assertIn("cp -P -- ", lines[cp_at] + " ", "copied with cp -P")

    def test_failures_leave_the_lock(self):
        _, docs, before = self._commit_lock(HAPPY_ROWS)
        for case, plant, fail_cp, why in (("a failed copy", "file", True, "copy of "),
                                          ("a symlink", "link", False, "is a link"),
                                          ("a directory", "dir", False, "is not a regular file")):
            with self.subTest(case=case):
                path, _ = self._shims(plant, fail_cp)
                r, _ = self._run(docs, path=path)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
                lines = [ln for ln in r.stderr.splitlines() if ln.startswith("sources_lock: FAIL (evidence: ")]
                self.assertTrue(lines and why in lines[0] and lines[0].endswith("; the lock is unchanged)"), r.stderr)
                self.assertEqual(self.lock.read_bytes(), before, "the lock changed")
                self.assertEqual(self._temps(), [], "a temp lock file was left")
                # Re-pinned by the tester, U8b RED (PSC-23 U8-12; design-notes N4 amendment U8 item 9):
                # the run's SBOMs go to <evdir>/sboms/ before the InRelease copies, so only that
                # directory may be there; no InRelease was copied (was: the dir is empty).
                self.assertEqual([n for n in sorted(os.listdir(self.evdir)) if n != "sboms"], [],
                                 "something was copied")

    def test_docker_save_gets_the_host_path(self):
        """Item 2 (B2): `docker save -o` takes `hostpath` (cygpath -m)."""
        _, docs, _ = self._commit_lock(HAPPY_ROWS)
        d = self.tmp / "cygpath-shim"
        d.mkdir()
        (d / "cygpath").write_text("#!/bin/sh\n[ \"$1\" = -m ] && shift\n[ \"$1\" = -- ] && shift\nprintf 'M:%s' \"$1\"\n",
                                   encoding="utf-8", newline="\n")
        (d / "cygpath").chmod(0o755)
        r, calls = self._run(docs, path=f"{d}{os.pathsep}{self.path}")
        if r.returncode == 2 and not calls:
            # A script before round 1's --evidence-dir (the B2 fix landed first): its own arguments.
            r, calls = self._run(docs, path=f"{d}{os.pathsep}{self.path}", args=("--arch", "amd64"))
        saves = [c for c in calls if c[:1] == ["save"]]
        self.assertTrue(saves, r.stderr[-2000:])
        out = saves[0][saves[0].index("-o") + 1]
        self.assertTrue(out.startswith("M:") and out.endswith(".tar"), f"save -o {out!r} is not the cygpath -m form")
        with self.subTest(case="no cygpath: the POSIX path unchanged"):
            r, calls = self._run(docs)
            if r.returncode == 2 and not calls:
                r, calls = self._run(docs, args=("--arch", "amd64"))
            saves = [c for c in calls if c[:1] == ["save"]]
            out = saves[0][saves[0].index("-o") + 1]
            self.assertTrue(out.startswith(str(self.tmp)) and out.endswith(".tar"), out)


# --------------------------------------------------------------------------
# U7d rework round 1, item 10 (u7d/lock-run-2.txt; u7d/aports-probe.txt): a
# leading `_` in file names; the symlink skip line names its key.
# --------------------------------------------------------------------------

ITEM10_NAME = "[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}"


class ReworkR1U7dUnderscoreTest(unittest.TestCase):
    """Item 10: one file-name pattern, `[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}`,
    in sbom_check.py and in the resolver's copy; a leading `-` or `.` and
    `..` anywhere still fail. The probe's real names: apk-tools `_apk`, musl
    `__stack_chk_fail_local.c` and `__NR_riscv_hwprobe.patch`."""

    def test_one_pattern(self):
        res, chk = load_resolver(), load_sbom_check()
        self.assertEqual(chk.LOCK_FILE_NAME_RE.pattern, ITEM10_NAME)
        self.assertEqual(res.NAME_RE.pattern, chk.LOCK_FILE_NAME_RE.pattern,
                         "the resolver's copy of the lock file-name pattern drifted from sbom_check.py's")

    def test_safe_name(self):
        mod = load_resolver()
        for name in ("_apk", "_x.patch", "__stack_chk_fail_local.c", "__NR_riscv_hwprobe.patch", "a_b"):
            with self.subTest(name=name):
                self.assertTrue(mod.safe_name(name), name)
        for name in ("-x", ".x", "a..b", "_..x", "_/x", "_x/", "", "_x y", "_" + "a" * 255):
            with self.subTest(name=name):
                self.assertFalse(mod.safe_name(name), name)

    def _resolve(self, fx: ApkFixture, image: str, purl: str, routes: dict[str, Any]) -> tuple[Any, str]:
        need_ = need(fx.key, image, purl, {"origin": fx.origin, "ver": fx.ver, "commit": fx.commit,
                                           "branch": fx.branch})
        return resolve_raw(load_resolver(), {fx.key: need_}, Seq({u: [v] for u, v in routes.items()}), Recorder())

    def test_the_real_shapes(self):
        shapes = {
            "apk-tools _apk": ("apk:apk-tools@3.0.3-r1", "v3.23", "ke-gateway", "alpine-3.23.3",
                               {"_apk": b"#compdef apk\n"}),
            "musl __ names": ("apk:musl@1.2.5-r21", "v3.23", "ke-gateway", "alpine-3.23.3",
                              {"__stack_chk_fail_local.c": b"void __stack_chk_fail_local(void) {}\n",
                               "__NR_riscv_hwprobe.patch": b"--- a\n+++ b\n"}),
            "a leading _ directory segment": ("apk:musl@1.2.6-r2", "v3.24", "valkey", "alpine-3.24.2",
                                              {"_patches/_y.patch": b"--- y\n+++ y\n"}),
        }
        for case, (key, branch, image, distro, local) in shapes.items():
            with self.subTest(case=case):
                origin, _, ver = key.split(":", 1)[1].rpartition("@")
                fx = ApkFixture(key, commit=aports_commit(origin, ver), branch=branch)
                fx.local.update(local)
                purl = f"pkg:apk/alpine/{origin}@{ver}?arch=x86_64&distro={distro}"
                got, err = self._resolve(fx, image, purl, fx.routes())
                self.assertNotIsInstance(got, Exception, str(got))
                self.assertEqual(by_name(got[0]["components"][key]), by_name(fx.entry()))
                lock_ok(self, got[0], docs_for({image: [{"purl": purl, "declared": "GPL-2.0-only"}]}))

    def test_still_refused(self):
        key = "apk:apk-tools@3.0.3-r1"
        for bad in ("-x", ".x", "a..b"):
            with self.subTest(where="a tree file", name=bad):
                fx = ApkFixture(key, commit=aports_commit("apk-tools", "3.0.3-r1"))
                fx.local[bad] = b"x"
                got, _ = self._resolve(fx, "ke-gateway", "pkg:apk/alpine/apk-tools@3.0.3-r1?arch=x86_64&distro=alpine-3.23.3",
                                       fx.routes())
                self.assertIsInstance(got, rfn("ResolveError"))
                self.assertEqual(str(got), f"{key}: {bad}: not a safe file name")
            with self.subTest(where="a directory segment", name=bad):
                fx = ApkFixture(key, commit=aports_commit("apk-tools", "3.0.3-r1"))
                fx.local[f"{bad}/y.patch"] = b"y"
                got, _ = self._resolve(fx, "ke-gateway", "pkg:apk/alpine/apk-tools@3.0.3-r1?arch=x86_64&distro=alpine-3.23.3",
                                       fx.routes())
                self.assertIsInstance(got, rfn("ResolveError"))
                self.assertEqual(str(got), f"{key}: {bad}/y.patch: not a safe file name")
            with self.subTest(where="a sha512sums name", name=bad):
                mod = load_resolver()
                with self.assertRaises(mod.ResolveError) as cm:
                    mod.parse_apkbuild(f"pkgver=3.0.3\npkgrel=1\nsha512sums=\"\n{'a' * 128}  {bad}\n\"\n",
                                       "c" * 40, "3.0.3-r1", "apk-tools")
                self.assertEqual(str(cm.exception), f"{bad}: not a safe file name")

    def test_a_link_to_an_underscore_name(self):
        key = "apk:apk-tools@3.0.3-r1"
        fx = ApkFixture(key, commit=aports_commit("apk-tools", "3.0.3-r1"))
        fx.local["_apk"] = b"#compdef apk\n"
        routes = fx.routes(listing=fx.listing("main", [link_item(fx.origin, "apk.zsh")]))
        routes[fx.files_api("apk.zsh")] = link_meta(b"_apk")
        got, err = self._resolve(fx, "ke-gateway", "pkg:apk/alpine/apk-tools@3.0.3-r1?arch=x86_64&distro=alpine-3.23.3",
                                 routes)
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertEqual(by_name(got[0]["components"][key]), by_name(fx.entry()), "the link is not locked")
        self.assertEqual([ln for ln in err.splitlines() if "symlink" in ln],
                         [f"{key}: main/apk-tools/apk.zsh -> _apk (symlink to a locked file, skipped)"])

    def test_the_skip_line_names_the_key(self):
        """Item 10 (the "printed twice" reading): run 2's two lines were two
        keys with the same link; one line per link per key, starting with the
        key, never deduplicated across keys."""
        up, inst = "alpine-baselayout.post-upgrade", "alpine-baselayout.post-install"
        needs, routes = {}, {}
        for ver, branch, image, distro in (("3.7.1-r8", "v3.23", "ke-gateway", "alpine-3.23.3"),
                                           ("3.7.2-r1", "v3.24", "valkey", "alpine-3.24.2")):
            fx = ApkFixture(f"apk:alpine-baselayout@{ver}", commit=aports_commit("alpine-baselayout", ver), branch=branch)
            routes.update(fx.routes(listing=fx.listing("main", [link_item(fx.origin, up)])))
            routes[fx.files_api(up)] = link_meta(inst.encode())
            needs[fx.key] = need(fx.key, image, f"pkg:apk/alpine/alpine-baselayout@{ver}?arch=x86_64&distro={distro}",
                                 {"origin": fx.origin, "ver": fx.ver, "commit": fx.commit, "branch": fx.branch})
        got, err = resolve_raw(load_resolver(), needs, Seq({u: [v] for u, v in routes.items()}), Recorder())
        self.assertNotIsInstance(got, Exception, str(got))
        self.assertEqual([ln for ln in err.splitlines() if "symlink" in ln], [
            f"apk:alpine-baselayout@3.7.1-r8: main/alpine-baselayout/{up} -> {inst} (symlink to a locked file, skipped)",
            f"apk:alpine-baselayout@3.7.2-r1: main/alpine-baselayout/{up} -> {inst} (symlink to a locked file, skipped)"])


class ReworkR1U7dEmptyFileTest(unittest.TestCase):
    """U7d rework round 1, item 12 (the aports probe's flag 1): an empty
    aports file (GitLab API raw form) is locked with size 0 and passes
    lock_problems; its sha256 is the empty string's."""

    def test_an_empty_aports_file(self):
        key = "apk:apk-tools@3.0.3-r1"
        fx = ApkFixture(key, commit=aports_commit("apk-tools", "3.0.3-r1"))
        fx.extra["apk-tools.trigger"] = b""  # a files-API (content_sha256) file
        fx.local["empty.patch"] = b""  # a sha512sums file
        purl = "pkg:apk/alpine/apk-tools@3.0.3-r1?arch=x86_64&distro=alpine-3.23.3"
        need_ = need(key, "ke-gateway", purl, {"origin": fx.origin, "ver": fx.ver, "commit": fx.commit,
                                               "branch": fx.branch})
        got, _ = resolve_raw(load_resolver(), {key: need_}, Seq({u: [v] for u, v in fx.routes().items()}), Recorder())
        self.assertNotIsInstance(got, Exception, str(got))
        entry = got[0]["components"][key]
        self.assertEqual(by_name(entry), by_name(fx.entry()))
        empty = {f["name"]: (f["size"], f["sha256"]) for f in entry["files"] if f["size"] == 0}
        self.assertEqual(empty, {n: (0, sha("sha256", b"")) for n in ("apk-tools.trigger", "empty.patch")})
        lock_ok(self, got[0], docs_for({"ke-gateway": [{"purl": purl, "declared": "GPL-2.0-only"}]}))


# ==========================================================================
# U8b (PSC-23 "U8 precision" U8-12; design-notes "N4 amendment, U8" item 9,
# U7d item 13, the S6 carry): sources_lock.sh keeps the run's SBOMs. After
# lock-check decides (exit 0 or 3) and before the InRelease copies and the
# lock move, `mkdir -- "$evdir/sboms"` (an existing one fails: `evidence:
# <evdir>/sboms exists`), then each `$work/sboms/<image>.spdx.json` (the
# files lock-needs and lock-check read) is copied with item 6's rules (a
# link or anything but a regular file fails; a failed copy fails), the lock
# unchanged on any failure (tester, U8b RED).
# ==========================================================================

SIX_SBOMS = sorted(f"{img}.spdx.json" for img in HAPPY_ROWS)


class U8bLockSbomsTest(_BundleBase, unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        for rel in ("docker/source-policy.json", SOURCES_YML):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.repo / rel)
        self.lock = self.repo / "docker" / "sources.lock.json"
        self.check = load_sbom_check()
        self.syft_log = self.tmp / "syft.jsonl"
        self.resolve_log = self.tmp / "resolve.log"
        self.shims = 0

    _commit_lock = ReworkR1LockScriptRunTest._commit_lock
    _run = ReworkR1LockScriptRunTest._run

    def _temps(self) -> list[str]:
        return sorted(p.name for p in (self.repo / "docker").iterdir() if p.name.startswith(".sources.lock.json."))

    def _evdir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="u8b-evidence-", dir=self.tmp))

    def _shims(self, evdir: Path, *, link: str | None = None, fail_cp: bool = False) -> tuple[str, Path, Path]:
        """A PATH with: an `mv` that lists <evdir>/sboms when the lock moves; a
        `cp` that logs (and, with fail_cp, fails on an .spdx.json); a docker
        wrapper that, with `link`, turns the run's <link>.spdx.json into a
        symlink to a copy right after its `sbom` run."""
        self.shims += 1
        d = self.tmp / f"u8b-shims-{self.shims}"
        d.mkdir()
        at_move, cp_log = d / "sboms-at-move.txt", d / "cp.log"
        real_mv, real_cp = shutil.which("mv"), shutil.which("cp")
        self.assertTrue(real_mv and real_cp)
        (d / "mv").write_text(
            "#!/bin/bash\n"
            "for a in \"$@\"; do case \"$a\" in *docker/sources.lock.json)\n"
            f"  if [ -d '{evdir}/sboms' ]; then ls -A '{evdir}/sboms' > '{at_move}'; "
            f"else echo '<absent>' > '{at_move}'; fi ;;\n"
            "esac; done\n"
            f"exec '{real_mv}' \"$@\"\n", encoding="utf-8", newline="\n")
        fail = ("for a in \"$@\"; do case \"$a\" in *.spdx.json) echo 'cp: injected failure' >&2; exit 1 ;; "
                "esac; done\n" if fail_cp else "")
        (d / "cp").write_text("#!/bin/bash\n" f"echo \"cp $*\" >> '{cp_log}'\n" + fail + f"exec '{real_cp}' \"$@\"\n",
                              encoding="utf-8", newline="\n")
        fake = self.tmp / "fakebin" / "docker"
        planting = ":"
        if link:
            planting = (f"case \" $* \" in *\"spdx-json=/out/{link}.spdx.json\"*) "
                        f"f=\"$KE_SBOM_OUT/{link}.spdx.json\"; '{real_mv}' \"$f\" \"$f.real\" && "
                        "ln -s \"$f.real\" \"$f\" ;; esac")
        (d / "docker").write_text("#!/bin/bash\n" f"'{fake}' \"$@\"\nrc=$?\n" + planting + "\nexit $rc\n",
                                  encoding="utf-8", newline="\n")
        for f in d.iterdir():
            f.chmod(0o755)
        return f"{d}{os.pathsep}{self.path}", at_move, cp_log

    def _kept(self, evdir: Path, docs: dict[str, Any], at_move: Path) -> None:
        sboms = evdir / "sboms"
        self.assertTrue(sboms.is_dir() and not sboms.is_symlink(), "no <evidence-dir>/sboms directory (U8-12)")
        self.assertEqual(sorted(os.listdir(sboms)), SIX_SBOMS, "exactly the six bundled images' SPDX documents")
        for img, doc in docs.items():
            with self.subTest(image=img):
                f = sboms / f"{img}.spdx.json"
                self.assertTrue(f.is_file() and not f.is_symlink(), f"{f.name} is not a regular file")
                self.assertEqual(f.read_bytes(), json.dumps(doc).encode("utf-8"),
                                 f"{f.name} is not byte-identical to the document the run's generator wrote")
        self.assertTrue(at_move.is_file(), "the lock never moved through mv")
        self.assertEqual(sorted(at_move.read_text(encoding="utf-8").split()), SIX_SBOMS,
                         "the SBOMs were not all in <evidence-dir>/sboms when the lock moved (copied before the move)")

    def test_sources_lock_keeps_the_run_sboms(self):
        lock, docs, _ = self._commit_lock(HAPPY_ROWS)
        evdir = self._evdir()
        path, at_move, _ = self._shims(evdir)
        r, _ = self._run(docs, path=path, args=("--arch", "amd64", "--evidence-dir", str(evdir)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
        self.assertEqual(self.lock.read_text(encoding="utf-8"), self.check.lock_text(lock))
        self._kept(evdir, docs, at_move)

    def test_sources_lock_keeps_the_run_sboms_when_neo4j_is_pending(self):
        _, docs, _ = self._commit_lock(with_rows({"ke-neo4j": [NEO_ROW]}), drop={NEO_KEY})
        evdir = self._evdir()
        path, at_move, _ = self._shims(evdir)
        r, _ = self._run(docs, net={NEO_URL: [200, {}, NEO_BODY.decode()]}, path=path,
                         args=("--arch", "amd64", "--evidence-dir", str(evdir)))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr[-3000:])
        self._kept(evdir, docs, at_move)

    def test_sources_lock_refuses_an_existing_sboms_dir(self):
        _, docs, before = self._commit_lock(HAPPY_ROWS)
        evdir = self._evdir()
        (evdir / "sboms").mkdir()
        r, _ = self._run(docs, args=("--arch", "amd64", "--evidence-dir", str(evdir)))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
        self.assertIn(f"sources_lock: FAIL (evidence: {evdir}/sboms exists; the lock is unchanged)",
                      r.stderr.splitlines())
        self.assertEqual(self.lock.read_bytes(), before, "the lock changed")
        self.assertEqual(self._temps(), [], "a temp lock file was left")
        self.assertEqual(os.listdir(evdir / "sboms"), [], "something was written into the existing sboms dir")

    def test_sources_lock_refuses_a_linked_sbom(self):
        _, docs, before = self._commit_lock(HAPPY_ROWS)
        evdir = self._evdir()
        path, _, _ = self._shims(evdir, link="ke-app")
        r, _ = self._run(docs, path=path, args=("--arch", "amd64", "--evidence-dir", str(evdir)))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
        lines = [ln for ln in r.stderr.splitlines() if ln.startswith("sources_lock: FAIL (evidence: ")]
        self.assertTrue(lines and "ke-app.spdx.json" in lines[0] and "is a link" in lines[0]
                        and lines[0].endswith("; the lock is unchanged)"), r.stderr[-3000:])
        self.assertEqual(self.lock.read_bytes(), before, "the lock changed")
        self.assertEqual(self._temps(), [], "a temp lock file was left")
        self.assertFalse((evdir / "sboms" / "ke-app.spdx.json").exists(), "the link was followed and copied")

    def test_sources_lock_fails_when_an_sbom_copy_fails(self):
        _, docs, before = self._commit_lock(HAPPY_ROWS)
        evdir = self._evdir()
        path, at_move, cp_log = self._shims(evdir, fail_cp=True)
        r, _ = self._run(docs, path=path, args=("--arch", "amd64", "--evidence-dir", str(evdir)))
        self.assertTrue(cp_log.is_file() and ".spdx.json" in cp_log.read_text(encoding="utf-8"),
                        "the script never copied an .spdx.json with cp (item 6's rules: cp -P): "
                        + r.stderr[-2000:])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-3000:])
        lines = [ln for ln in r.stderr.splitlines() if ln.startswith("sources_lock: FAIL (evidence: ")]
        self.assertTrue(lines and lines[0].endswith("; the lock is unchanged)"), r.stderr[-3000:])
        self.assertEqual(self.lock.read_bytes(), before, "the lock changed")
        self.assertEqual(self._temps(), [], "a temp lock file was left")
        self.assertFalse(at_move.exists(), "the lock moved after a failed SBOM copy")


if __name__ == "__main__":
    unittest.main()
