"""The source lock's resolver (platform-sbom U7b; PSC-15, PSC-23; design-notes
N5 and its U7 amendment, items 3-5, "Resolution endpoints", rework rounds 1-2).

Standard library only, Python 3.12, run as `python3 -I` inside the
`sources-resolve` service (docker-compose.sources.yml), which mounts this file,
needs.json, the committed lock, the policy and uv.lock read-only and one out
dir read-write. It writes nothing but `<out>/lock.new.json`.

  sources_resolve.py --needs NEEDS --lock LOCK --policy POLICY --uv-lock UVLOCK
                     --out DIR --arch amd64|arm64 [--refresh]

Routes in U7b: `temurin`, `maven`, `pypi`, `neo4j` (U7c adds `deb` and `apk`;
`pgdg` waits on Q71: such keys are skipped and named on stderr). Every request
goes through `OPENER(url, timeout)`; redirects are followed by hand, at most 5,
each hop `https` and its host in the policy `hosts` plus `pypi.org` (O2). A
file is streamed into the hashers and never stored. One call per file, no
retry (Q61).

- temurin: the tag comes from the image's /opt/java/openjdk/release (passed in
  needs.json by `sbom_check.py lock-needs --tar`), cross-checked with the SBOM;
  the asset is checked against its `.sha256.txt`.
- maven: the `-sources.jar` against its `.sha1`.
- pypi: from uv.lock (no call) or pypi.org's JSON (exactly one sdist), then the
  sdist streamed and checked.
- neo4j: no published checksum. The tarball is streamed once and the candidate
  printed (`neo4j candidate: {...}`); the entry is never written (origin
  `manual`, by hand after security's second fetch). Exit 3.

Exit 0: written. 1: a failure, nothing written (`sources_lock: FAIL (resolve:
<key>: <why>; the lock is unchanged)`). 2: a bad argument. 3: written, with
neo4j candidates pending.

The test hook is `OPENER`: tests import this file by path and replace it with
a fake network (no other mechanism; nothing reads the environment).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
import tomllib
from typing import Any, Callable, Iterable
from urllib.parse import quote, urljoin, urlsplit

MAX_HOPS = 5
TIMEOUT = 60
CHUNK = 1 << 16
ARCHES = ("amd64", "arm64")
PYPI_JSON_HOST = "pypi.org"  # resolution only, never a lock file URL (O2)
GITHUB = "github.com"
MAVEN = "repo1.maven.org"
ROUTES = ("temurin", "maven", "pypi", "neo4j")
HEX = {"sha1": 40, "sha256": 64, "sha512": 128}


class ResolveError(Exception):
    """A fail-closed stop; the message is item 4's `<why>`."""


class Response:
    """What OPENER returns: an HTTP status, headers (lower-case keys), and the
    body as an iterable of byte chunks."""

    def __init__(self, status: int, headers: dict[str, str] | None = None, body: Iterable[bytes] | bytes = b""):
        self.status = status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = [body] if isinstance(body, bytes) else body


def _default_opener(url: str, timeout: float) -> Response:  # pragma: no cover - the real network
    import ssl
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=ctx))
    try:
        r = opener.open(urllib.request.Request(url, headers={"User-Agent": "knowledge-engine-sources-lock"}),
                        timeout=timeout)
    except urllib.error.HTTPError as exc:  # 3xx and errors arrive here with NoRedirect
        return Response(exc.code, dict(exc.headers or {}), exc.read())

    def chunks() -> Iterable[bytes]:
        while True:
            data = r.read(CHUNK)
            if not data:
                return
            yield data
    return Response(r.status, dict(r.headers), chunks())


OPENER: Callable[[str, float], Response] = _default_opener


def _clean(value: Any) -> str:
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", lambda m: f"\\x{ord(m.group()):02x}", str(value))


def fetch(url: str, allow: set[str], *, timeout: float = TIMEOUT, hops: list[str] | None = None) -> Response:
    """GET with hop-by-hop redirects: at most 5, each https and its host in
    `allow` (exact, lower-cased). Item 4's messages."""
    current = url
    for hop in range(MAX_HOPS + 1):
        u = urlsplit(current)
        host = (u.hostname or "").lower()
        if u.scheme != "https":
            raise ResolveError(f"redirect to a non-https URL refused: {_clean(current)}" if hop
                               else f"not an https URL: {_clean(current)}")
        if host not in allow:
            raise ResolveError(f"redirect to {_clean(host)} refused: not in hosts" if hop
                               else f"{_clean(host)}: not in hosts: {_clean(current)}")
        if hops is not None:
            hops.append(host)
        try:
            r = OPENER(current, timeout)
        except (TimeoutError, socket.timeout):
            raise ResolveError(f"{host}: timeout after {timeout:g} s: {_clean(current)}") from None
        except OSError as exc:
            raise ResolveError(f"{host}: {_clean(exc)}: {_clean(current)}") from None
        if 300 <= r.status < 400:
            loc = r.headers.get("location")
            if not loc:
                raise ResolveError(f"{host}: HTTP {r.status}: {_clean(current)}")
            if hop == MAX_HOPS:
                break
            current = urljoin(current, loc)
            continue
        if not 200 <= r.status < 300:
            raise ResolveError(f"{host}: HTTP {r.status}: {_clean(current)}")
        return r
    raise ResolveError(f"more than {MAX_HOPS} redirects: {_clean(url)}")


def stream(url: str, allow: set[str], algs: tuple[str, ...] = ("sha256",),
           hops: list[str] | None = None) -> tuple[dict[str, str], int]:
    """The body's digests and size; the bytes are hashed, never stored."""
    r = fetch(url, allow, hops=hops)
    hashers = {a: hashlib.new(a) for a in set(algs) | {"sha256"}}
    size = 0
    for chunk in r.body:
        size += len(chunk)
        for h in hashers.values():
            h.update(chunk)
    return {a: h.hexdigest() for a, h in hashers.items()}, size


def text(url: str, allow: set[str], limit: int = 1 << 20) -> str:
    r = fetch(url, allow)
    data = b""
    for chunk in r.body:
        data += chunk
        if len(data) > limit:
            raise ResolveError(f"{_clean(url)}: more than {limit} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ResolveError(f"{_clean(url)}: not UTF-8 text") from None


# --- parsers (pure) ----------------------------------------------------------

def parse_sha256_txt(body: str, asset: str) -> str:
    """Adoptium's `<asset>.sha256.txt`: exactly one line, 64 hex, whitespace,
    the asset name."""
    m = re.fullmatch(r"([0-9a-f]{64})[ \t]+(\S+)\n?", body)
    if not m or m.group(2) != asset:
        raise ResolveError(f"{_clean(asset)}.sha256.txt is not one line `<sha256> {_clean(asset)}`")
    return m.group(1)


def parse_sha1(body: str, label: str, name: str) -> str:
    """Maven Central's `.sha1`: the first token is 40 hex (`label` is
    `<g>:<a>@<v>`, `name` the jar)."""
    first = body.split(None, 1)[0] if body.split() else ""
    if not re.fullmatch(r"[0-9a-f]{40}", first):
        raise ResolveError(f"maven {_clean(label)}: {_clean(name)}.sha1 is not 40 hex")
    return first


def _pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def uv_lock_sdist(uv_lock_text: str, name: str, ver: str) -> dict[str, Any] | None:
    """`uv.lock`'s sdist of `name` at `ver`: {url, sha256, size}, or None."""
    for pkg in tomllib.loads(uv_lock_text).get("package", []):
        if _pep503(str(pkg.get("name", ""))) == _pep503(name) and pkg.get("version") == ver:
            sd = pkg.get("sdist") or {}
            h = str(sd.get("hash", ""))
            if not (sd.get("url") and h.startswith("sha256:") and isinstance(sd.get("size"), int)):
                raise ResolveError(f"pypi {_clean(name)} {_clean(ver)}: uv.lock has no sdist url, hash and size")
            return {"url": sd["url"], "sha256": h.split(":", 1)[1], "size": sd["size"]}
    return None


def pypi_json_sdist(doc: Any, name: str, ver: str) -> dict[str, Any]:
    """pypi.org's JSON: exactly one `packagetype: sdist` on files.pythonhosted.org."""
    urls = doc.get("urls") if isinstance(doc, dict) else None
    sdists = [u for u in urls or [] if isinstance(u, dict) and u.get("packagetype") == "sdist"]
    if len(sdists) != 1:
        raise ResolveError(f"pypi {_clean(name)} {_clean(ver)}: {len(sdists)} sdists, want 1")
    sd = sdists[0]
    url, digest = str(sd.get("url", "")), str((sd.get("digests") or {}).get("sha256", ""))
    if urlsplit(url).hostname != "files.pythonhosted.org" or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ResolveError(f"pypi {_clean(name)} {_clean(ver)}: the sdist is not a files.pythonhosted.org url "
                           "with a sha256")
    return {"url": url, "sha256": digest}


def parse_release(body: str) -> dict[str, str]:
    """`/opt/java/openjdk/release`: KEY="value" lines."""
    out = {}
    for line in body.splitlines():
        m = re.fullmatch(r'([A-Z_]+)="([^"\n]*)"', line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def temurin_tag(release_text: str, sbom_version: str) -> str:
    """The Temurin release tag (`jdk-<ver>`) from the release file, which must
    agree with the SBOM's openjdk version (item 4)."""
    rel = parse_release(release_text)
    impl = rel.get("IMPLEMENTOR_VERSION", "")
    runtime = rel.get("JAVA_RUNTIME_VERSION", "")
    ver = impl[len("Temurin-"):] if impl.startswith("Temurin-") else ""
    sbom = sbom_version[:-len("-LTS")] if sbom_version.endswith("-LTS") else sbom_version
    run = runtime[:-len("-LTS")] if runtime.endswith("-LTS") else runtime
    if not ver or ver != run or ver != sbom:
        raise ResolveError(f"temurin: release file says {_clean(ver or impl or '(none)')}, SBOM says {_clean(sbom)}")
    return f"jdk-{ver}"


# --- routes -----------------------------------------------------------------

def _file(name: str, url: str, sha256: str, size: int, alg: str, value: str, frm: str) -> dict[str, Any]:
    return {"name": name, "url": url, "sha256": sha256, "size": size,
            "upstream": {"alg": alg, "value": value, "from": frm}}


def _entry(kind: str, arch: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": kind, "arches": [arch], "origin": "generated", "files": files}


def resolve_temurin(key: str, route: dict[str, Any], arch: str, allow: set[str]) -> dict[str, Any]:
    tag = temurin_tag(str(route.get("release", "")), str(route.get("sbom_version", "")))
    if f"temurin:{tag}" != key:
        raise ResolveError(f"temurin: release file says {_clean(tag)}, SBOM says {_clean(key)}")
    ver = tag[len("jdk-"):]
    feature = ver.split(".", 1)[0]
    asset = f"OpenJDK{feature}U-jdk-sources_{ver.replace('+', '_')}.tar.gz"
    url = f"https://{GITHUB}/adoptium/temurin{feature}-binaries/releases/download/{quote(tag, safe='')}/{asset}"
    want = parse_sha256_txt(text(url + ".sha256.txt", allow), asset)
    got, size = stream(url, allow)
    if got["sha256"] != want:
        raise ResolveError(f"{asset}: sha256 mismatch: got {got['sha256']}, {asset}.sha256.txt says {want}")
    return _entry("temurin", arch, [_file(asset, url, want, size, "sha256", want, f"{asset}.sha256.txt")])


def resolve_maven(key: str, arch: str, allow: set[str]) -> dict[str, Any]:
    body = key.split(":", 1)[1]
    ga, _, v = body.rpartition("@")
    g, _, a = ga.partition(":")
    name = f"{a}-{v}-sources.jar"
    url = f"https://{MAVEN}/maven2/{g.replace('.', '/')}/{a}/{v}/{name}"
    want = parse_sha1(text(url + ".sha1", allow), body, name)
    got, size = stream(url, allow, ("sha1", "sha256"))
    if got["sha1"] != want:
        raise ResolveError(f"{name}: sha1 mismatch: got {got['sha1']}, {name}.sha1 says {want}")
    return _entry("maven", arch, [_file(name, url, got["sha256"], size, "sha1", want, f"{name}.sha1")])


def resolve_pypi(key: str, arch: str, allow: set[str], uv_lock_text: str) -> dict[str, Any]:
    name, _, ver = key.split(":", 1)[1].rpartition("@")
    sd = uv_lock_sdist(uv_lock_text, name, ver)
    if sd is not None:
        fname = sd["url"].rsplit("/", 1)[-1]
        return _entry("pypi", arch, [_file(fname, sd["url"], sd["sha256"], sd["size"], "sha256", sd["sha256"],
                                           "uv.lock")])
    try:
        doc = json.loads(text(f"https://{PYPI_JSON_HOST}/pypi/{quote(name, safe='')}/{quote(ver, safe='')}/json", allow))
    except ValueError:
        raise ResolveError(f"pypi {_clean(name)} {_clean(ver)}: the pypi.org JSON does not parse") from None
    sd = pypi_json_sdist(doc, name, ver)
    got, size = stream(sd["url"], allow)
    fname = sd["url"].rsplit("/", 1)[-1]
    if got["sha256"] != sd["sha256"]:
        raise ResolveError(f"{fname}: sha256 mismatch: got {got['sha256']}, pypi.org JSON {name} {ver} says "
                           f"{sd['sha256']}")
    return _entry("pypi", arch, [_file(fname, sd["url"], sd["sha256"], size, "sha256", sd["sha256"],
                                       f"pypi.org JSON {name} {ver}")])


def neo4j_candidate(key: str, allow: set[str]) -> dict[str, Any]:
    """Trust on first use: stream the tag tarball once; the entry is written
    by hand after security's second fetch (item 4)."""
    ver = key.split("@", 1)[1]
    url = f"https://{GITHUB}/neo4j/neo4j/archive/refs/tags/{ver}.tar.gz"
    hops: list[str] = []
    got, size = stream(url, allow, hops=hops)
    return {"key": key, "url": url, "name": f"{ver}.tar.gz", "sha256": got["sha256"], "size": size,
            "date": time.strftime("%Y-%m-%d", time.gmtime()), "host": hops[-1] if hops else "",
            "origin": "manual (pending security's second fetch)"}


# --- the run ----------------------------------------------------------------

def lock_text(lock: Any) -> str:
    return json.dumps(lock, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def resolve(needs: dict[str, Any], lock: dict[str, Any], policy: dict[str, Any], uv_lock_text: str, arch: str,
            refresh: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """(the new lock, the neo4j candidates, the skipped keys). Raises
    ResolveError naming the key."""
    allow = {h for h in policy.get("hosts") or [] if isinstance(h, str)} | {PYPI_JSON_HOST}
    comps: dict[str, Any] = json.loads(json.dumps(lock.get("components") or {}))
    candidates, skipped = [], []
    for key in sorted(needs):
        kind = key.split(":", 1)[0]
        old = comps.get(key)
        if isinstance(old, dict) and old.get("origin") == "manual":
            continue  # never rewritten (item 3.5)
        if kind not in ROUTES:
            skipped.append(key)
            continue
        if isinstance(old, dict) and arch in (old.get("arches") or []) and not refresh:
            continue
        try:
            if kind == "neo4j":
                candidates.append(neo4j_candidate(key, allow))
                continue
            if kind == "temurin":
                entry = resolve_temurin(key, (needs[key] or {}).get("route") or {}, arch, allow)
            elif kind == "maven":
                entry = resolve_maven(key, arch, allow)
            else:
                entry = resolve_pypi(key, arch, allow, uv_lock_text)
        except ResolveError as exc:
            raise ResolveError(f"{_clean(key)}: {exc}") from None
        if isinstance(old, dict):
            entry["arches"] = sorted(set(old.get("arches") or []) | {arch})
        comps[key] = entry
    # Merge (N5 `arches`): a generated entry no image needs loses this arch.
    for key in sorted(comps):
        e = comps[key]
        if key in needs or not isinstance(e, dict) or e.get("origin") == "manual":
            continue
        arches = [a for a in e.get("arches") or [] if a != arch]
        if arches:
            e["arches"] = arches
        else:
            del comps[key]
    return {"format": 1, "components": comps}, candidates, skipped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sources_resolve.py")
    for opt in ("--needs", "--lock", "--policy", "--uv-lock", "--out", "--arch"):
        parser.add_argument(opt, required=True)
    parser.add_argument("--refresh", action="store_true")
    try:
        a = parser.parse_args(argv)
    except SystemExit:
        return 2
    if a.arch not in ARCHES:
        print(f"sources_resolve: --arch {a.arch!r} is not amd64 or arm64", file=sys.stderr)
        return 2
    try:
        with open(a.needs, encoding="utf-8") as fh:
            needs = json.load(fh).get("needs") or {}
        with open(a.lock, encoding="utf-8") as fh:
            lock = json.load(fh)
        with open(a.policy, encoding="utf-8") as fh:
            policy = json.load(fh)
        with open(a.uv_lock, encoding="utf-8") as fh:
            uv = fh.read()
    except (OSError, ValueError, AttributeError) as exc:
        print(f"sources_lock: FAIL (resolve: inputs: {_clean(exc)}; the lock is unchanged)", file=sys.stderr)
        return 1
    try:
        new, candidates, skipped = resolve(needs, lock, policy, uv, a.arch, a.refresh)
    except ResolveError as exc:
        print(f"sources_lock: FAIL (resolve: {exc}; the lock is unchanged)", file=sys.stderr)
        return 1
    for key in skipped:
        print(f"sources_resolve: skip: {_clean(key)} (no {key.split(':', 1)[0]} route until U7c)", file=sys.stderr)
    tmp = os.path.join(a.out, ".lock.new.json.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lock_text(new))
    os.replace(tmp, os.path.join(a.out, "lock.new.json"))
    for c in candidates:
        print("neo4j candidate: " + json.dumps(c, sort_keys=True))
    return 3 if candidates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
