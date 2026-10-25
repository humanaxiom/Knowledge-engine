"""The source lock's resolver (platform-sbom U7b; PSC-15, PSC-23; design-notes
N5 and its U7 amendment, items 3-5, "Resolution endpoints", rework rounds 1-2).

Standard library only, Python 3.12, run as `python3 -I` inside the
`sources-resolve` service (docker-compose.sources.yml), which mounts this file,
needs.json, the committed lock, the policy and uv.lock read-only and one out
dir read-write. It writes nothing but `<out>/lock.new.json`.

  sources_resolve.py --needs NEEDS --lock LOCK --policy POLICY --uv-lock UVLOCK
                     --out DIR --arch amd64|arm64 [--refresh]

Routes: `temurin`, `maven`, `pypi`, `neo4j` (U7b); `deb` and `apk` (U7c,
design-notes "U7c precision" D1-D7 and A1-A5). `pgdg` waits on Q71: such keys
are skipped and named on stderr. Every request
goes through `OPENER(url, timeout)`; redirects are followed by hand, at most 5,
each hop passing rework round 1's rules (item 3: printable, `https://`, no
userinfo, port or fragment, a plain path; a query allowed) with its host in
the policy `hosts`; `pypi.org` only for the pypi JSON request (item 8). A
file is streamed into the hashers and never stored, within a 600 s deadline
and a 4 GiB cap (item 1). Every key is checked against U7a's grammar before
any URL is built (item 11). One call per file, no retry (Q61).

- temurin: the tag comes from the image's /opt/java/openjdk/release (passed in
  needs.json by `sbom_check.py lock-needs --tar`), cross-checked with the SBOM;
  the asset is checked against its `.sha256.txt`.
- maven: the `-sources.jar` against its `.sha1`.
- pypi: from uv.lock (no call) or pypi.org's JSON (exactly one sdist), then the
  sdist streamed and checked.
- deb: snapshot.debian.org's srcfiles?fileinfo=1 (name -> sha1), then the
  `.dsc` alone from /file/<sha1> (sha1 checked, 1 MiB); the other files are
  recorded from its Checksums-Sha256 and never fetched. Snapshot requests are
  spaced by SNAPSHOT_PAUSE.
- apk: the aports tree at the commit (main, then community), the APKBUILD by
  the files API's content_sha256, then every sha512sums name streamed from
  GitLab raw (in the tree) or distfiles (not in it), sha512 checked.
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
import http.client
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
DEADLINE = 600  # seconds per file, wall clock (U7b rework round 1, item 1)
MAX_BYTES = 4294967296  # 4 GiB, the U7a size cap (round 1, item 1)
ERROR_BODY_LIMIT = 1048576  # a 3xx/4xx body is read up to 1 MiB, then dropped (round 1, item 10)
CHUNK = 1 << 16
TEXT_LIMIT = 1048576  # the .dsc, the APKBUILD and every JSON body (U7c D1, D3, A3)
SNAPSHOT_PAUSE = 1.0  # seconds between snapshot.debian.org requests (U7c D7)
SNAPSHOT = "snapshot.debian.org"
GITLAB = "gitlab.alpinelinux.org"
DISTFILES = "distfiles.alpinelinux.org"
APORTS_API = f"https://{GITLAB}/api/v4/projects/alpine%2Faports/repository"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~-]{0,254}")  # the U7a lock name rule
_LAST_SNAPSHOT: list[float] = []
ARCHES = ("amd64", "arm64")
PYPI_JSON_HOST = "pypi.org"  # resolution only, never a lock file URL (O2)
GITHUB = "github.com"
MAVEN = "repo1.maven.org"
ROUTES = ("temurin", "maven", "pypi", "neo4j", "deb", "apk")
HEX = {"sha1": 40, "sha256": 64, "sha512": 128}
# U7a's key grammar (item 6 (c)), a minimal copy: sbom_check.py is not mounted
# in the sources-resolve service (round 1, items 3 and 11).
KEY_RES = {
    "deb": re.compile(r"deb:[a-z0-9][a-z0-9+.-]+@([0-9]+:)?[0-9][A-Za-z0-9.+~-]*"),
    "pgdg": re.compile(r"pgdg:[a-z0-9][a-z0-9+.-]+@([0-9]+:)?[0-9][A-Za-z0-9.+~-]*"),
    "apk": re.compile(r"apk:[a-z0-9][a-z0-9+._-]*@[0-9][A-Za-z0-9._+]*-r[0-9]+"),
    "neo4j": re.compile(r"neo4j:neo4j@\d+(\.\d+)+"),
    "temurin": re.compile(r"temurin:jdk-\d+(\.\d+)*\+\d+"),
    "pypi": re.compile(r"pypi:[a-z0-9]+(-[a-z0-9]+)*@[0-9][A-Za-z0-9.+!-]*"),
    "maven": re.compile(r"maven:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+@[A-Za-z0-9_.+-]+"),
}
PRINTABLE = re.compile(r"[\x21-\x7e]+")


def valid_key(key: Any) -> bool:
    if not isinstance(key, str) or ":" not in key:
        return False
    kind = key.split(":", 1)[0]
    rx = KEY_RES.get(kind)
    if rx is None or not rx.fullmatch(key):
        return False
    return kind not in ("deb", "pgdg") or ((".pgdg" in key) == (kind == "pgdg"))


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
        exc.read(ERROR_BODY_LIMIT)  # read up to 1 MiB and drop it: never parsed or printed (I-1)
        return Response(exc.code, dict(exc.headers or {}), b"")

    def chunks() -> Iterable[bytes]:
        while True:
            data = r.read1(CHUNK)  # one recv per call (U7c C2, security U7b R1-L1)
            if not data:
                return
            yield data
    return Response(r.status, dict(r.headers), chunks())


OPENER: Callable[[str, float], Response] = _default_opener


def _clean(value: Any) -> str:
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", lambda m: f"\\x{ord(m.group()):02x}", str(value))


def _hop_refusal(url: str, first: bool) -> str | None:
    """Round 1, item 3: printable, lower-case https, no userinfo, port or
    fragment, a plain path (no `%` but in the resolver's own first URLs); a
    query is allowed (signed release-asset redirects)."""
    if not PRINTABLE.fullmatch(url):
        return "not printable ASCII"
    if not url.startswith("https://"):
        return "not https"
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        return "does not parse"
    if "@" in u.netloc:
        return "userinfo"
    if port is not None or u.netloc.endswith(":"):
        return "a port"
    if "#" in url:
        return "a fragment"
    segs = u.path.split("/")
    if ("\\" in url or not u.path.startswith("/") or any(seg == "" for seg in segs[1:])
            or any(seg in (".", "..") for seg in segs) or (not first and "%" in u.path)):
        return "not a plain path"
    return None


def _transport(host: str, url: str, exc: BaseException, timeout: float) -> ResolveError:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return ResolveError(f"{host}: timeout after {timeout:g} s: {_clean(url)}")
    return ResolveError(f"{host}: {type(exc).__name__}: {_clean(url)}")


def _guarded(r: Response, host: str, url: str, started: float, timeout: float) -> Iterable[bytes]:
    """The body with item 1's guards: transport errors, the per-file deadline
    and the byte cap (checked before a chunk past the cap is hashed)."""
    size = 0
    it = iter(r.body)
    while True:
        if time.monotonic() - started > DEADLINE:
            raise ResolveError(f"{host}: deadline {DEADLINE:g} s passed: {_clean(url)}")
        try:
            chunk = next(it)
        except StopIteration:
            return
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise _transport(host, url, exc, timeout) from None
        size += len(chunk)
        if size > MAX_BYTES:
            raise ResolveError(f"{host}: more than {MAX_BYTES} bytes: {_clean(url)}")
        yield chunk


def fetch(url: str, allow: set[str], *, timeout: float = TIMEOUT, hops: list[str] | None = None,
          first_allow: set[str] | frozenset[str] = frozenset(), supplied: bool = False,
          missing_ok: bool = False) -> Response | None:
    """GET with hop-by-hop redirects: at most 5, each passing `_hop_refusal`
    and its host in `allow` (exact, lower-cased); `first_allow` widens only
    the first request (pypi.org's JSON, round 1, item 8). Item 4's messages;
    every transport error is a ResolveError (round 1, item 1)."""
    current = url
    started = time.monotonic()
    for hop in range(MAX_HOPS + 1):
        # U7c C1: a url taken from a response body (supplied) gets the hop rules.
        refusal = _hop_refusal(current, first=hop == 0 and not supplied)
        if refusal == "not https":
            raise ResolveError(f"redirect to a non-https URL refused: {_clean(current)}" if hop
                               else f"not an https URL: {_clean(current)}")
        if refusal:
            raise ResolveError(f"redirect to {_clean(current)} refused: {refusal}" if hop
                               else f"{_clean(current)}: refused: {refusal}")
        u = urlsplit(current)
        host = (u.hostname or "").lower()
        if host not in (allow | set(first_allow) if hop == 0 else allow):
            raise ResolveError(f"redirect to {_clean(host)} refused: not in hosts" if hop
                               else f"{_clean(host)}: not in hosts: {_clean(current)}")
        if hops is not None:
            hops.append(host)
        if time.monotonic() - started > DEADLINE:
            raise ResolveError(f"{host}: deadline {DEADLINE:g} s passed: {_clean(current)}")
        try:
            r = OPENER(current, timeout)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise _transport(host, current, exc, timeout) from None
        if 300 <= r.status < 400:
            loc = r.headers.get("location")
            if not loc:
                raise ResolveError(f"{host}: HTTP {r.status}: {_clean(current)}")
            if hop == MAX_HOPS:
                break
            if not PRINTABLE.fullmatch(loc):  # before the join, which drops tabs and newlines
                raise ResolveError(f"redirect to {_clean(loc)} refused: not printable ASCII")
            if ":" in loc.split("/", 1)[0] and not loc.startswith("https://"):  # the join lower-cases a scheme
                raise ResolveError(f"redirect to a non-https URL refused: {_clean(loc)}")
            current = urljoin(current, loc)
            continue
        if missing_ok and r.status == 404:
            return None
        if not 200 <= r.status < 300:
            raise ResolveError(f"{host}: HTTP {r.status}: {_clean(current)}")
        return Response(r.status, r.headers, _guarded(r, host, current, started, timeout))
    raise ResolveError(f"more than {MAX_HOPS} redirects: {_clean(url)}")


def stream(url: str, allow: set[str], algs: tuple[str, ...] = ("sha256",),
           hops: list[str] | None = None, supplied: bool = False) -> tuple[dict[str, str], int]:
    """The body's digests and size; the bytes are hashed, never stored."""
    r = fetch(url, allow, hops=hops, supplied=supplied)
    assert r is not None
    hashers = {a: hashlib.new(a) for a in set(algs) | {"sha256"}}
    size = 0
    for chunk in r.body:
        size += len(chunk)
        for h in hashers.values():
            h.update(chunk)
    return {a: h.hexdigest() for a, h in hashers.items()}, size


def text(url: str, allow: set[str], limit: int = 1 << 20, first_allow: frozenset[str] = frozenset()) -> str:
    r = fetch(url, allow, first_allow=first_allow)
    assert r is not None
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
        doc = json.loads(text(f"https://{PYPI_JSON_HOST}/pypi/{quote(name, safe='')}/{quote(ver, safe='')}/json", allow,
                              first_allow=frozenset({PYPI_JSON_HOST})))
    except ValueError:
        raise ResolveError(f"pypi {_clean(name)} {_clean(ver)}: the pypi.org JSON does not parse") from None
    sd = pypi_json_sdist(doc, name, ver)
    got, size = stream(sd["url"], allow, supplied=True)  # U7c C1: a server-supplied url
    fname = sd["url"].rsplit("/", 1)[-1]
    if got["sha256"] != sd["sha256"]:
        raise ResolveError(f"{fname}: sha256 mismatch: got {got['sha256']}, pypi.org JSON {name} {ver} says "
                           f"{sd['sha256']}")
    return _entry("pypi", arch, [_file(fname, sd["url"], sd["sha256"], size, "sha256", sd["sha256"],
                                       f"pypi.org JSON {name} {ver}")])



# --- U7c: the deb route (design-notes "U7c precision" D1-D7) -----------------

def safe_name(name: Any) -> bool:
    return isinstance(name, str) and bool(NAME_RE.fullmatch(name)) and ".." not in name


def _snapshot_wait() -> None:
    """D7: SNAPSHOT_PAUSE seconds between snapshot requests (monotonic)."""
    if _LAST_SNAPSHOT:
        wait = SNAPSHOT_PAUSE - (time.monotonic() - _LAST_SNAPSHOT[-1])
        if wait > 0:
            time.sleep(wait)
    _LAST_SNAPSHOT[:] = [time.monotonic()]


def capped(url: str, allow: set[str], name: str, limit: int = TEXT_LIMIT,
           algs: tuple[str, ...] = ("sha256",), missing_ok: bool = False) -> tuple[bytes, dict[str, str]] | None:
    """The body, at most `limit` bytes (`<name>: more than <limit> bytes`),
    hashed while read."""
    r = fetch(url, allow, missing_ok=missing_ok)
    if r is None:
        return None
    hashers = {a: hashlib.new(a) for a in set(algs) | {"sha256"}}
    data = bytearray()
    for chunk in r.body:
        data += chunk
        if len(data) > limit:
            raise ResolveError(f"{_clean(name)}: more than {limit} bytes")
        for h in hashers.values():
            h.update(chunk)
    return bytes(data), {a: h.hexdigest() for a, h in hashers.items()}


def srcfiles_map(doc: Any) -> dict[str, str]:
    """D1: name -> sha1 from snapshot's `fileinfo`, every archive."""
    bad = ResolveError(f"{SNAPSHOT} srcfiles is not the expected JSON")
    info = doc.get("fileinfo") if isinstance(doc, dict) else None
    if not isinstance(info, dict):
        raise bad
    out: dict[str, str] = {}
    for sha1, entries in info.items():
        if not isinstance(sha1, str) or not re.fullmatch(r"[0-9a-f]{40}", sha1) or not isinstance(entries, list):
            raise bad
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get("name"), str):
                raise bad
            if out.get(e["name"], sha1) != sha1:
                raise ResolveError(f"two files named {_clean(e['name'])} in snapshot's srcfiles")
            out[e["name"]] = sha1
    return out


def parse_dsc(body: str) -> dict[str, str]:
    """D4: the deb822 fields of a `.dsc` (clearsign armour stripped, `- `
    dash-escapes undone, the signature not verified). A field's value is its
    first line and its continuation lines, joined with newlines and stripped."""
    lines = body.splitlines()
    if lines and lines[0].startswith("-----BEGIN PGP SIGNED MESSAGE"):
        rest = lines[1:]
        start = rest.index("") + 1 if "" in rest else len(rest)
        rest = rest[start:]
        for i, ln in enumerate(rest):
            if ln.startswith("-----BEGIN PGP SIGNATURE"):
                rest = rest[:i]
                break
        lines = [ln[2:] if ln.startswith("- ") else ln for ln in rest]
    fields: dict[str, list[str]] = {}
    current = None
    for ln in lines:
        if not ln.strip():
            current = None
            continue
        if ln[0] in " \t" and current is not None:
            fields[current].append(ln.strip())
            continue
        name, sep, value = ln.partition(":")
        if not sep or not name or " " in name:
            current = None
            continue
        current = name
        fields[current] = [value.strip()]
    return {k: "\n".join(v).strip() for k, v in fields.items()}


def _dsc_lines(dsc: str, fields: dict[str, str], field: str, hexlen: int) -> list[tuple[str, int, str]]:
    out = []
    for ln in fields.get(field, "").splitlines():
        parts = ln.split()
        if (len(parts) != 3 or not re.fullmatch(f"[0-9a-f]{{{hexlen}}}", parts[0])
                or not re.fullmatch(r"[0-9]+", parts[1])):
            raise ResolveError(f"{_clean(dsc)}: bad {field} line")
        out.append((parts[0], int(parts[1]), parts[2]))
    return out


def dsc_files(fields: dict[str, str], dsc: str, src: str, ver: str, names: dict[str, str]) -> list[dict[str, Any]]:
    """D4-D6: the files the `.dsc` lists, as lock file entries."""
    if (fields.get("Source"), fields.get("Version")) != (src, ver):
        raise ResolveError(f"{_clean(dsc)}: Source/Version is {_clean(fields.get('Source'))}/"
                           f"{_clean(fields.get('Version'))}, want {src}/{ver}")
    if not fields.get("Checksums-Sha256"):
        raise ResolveError(f"{_clean(dsc)}: no Checksums-Sha256")
    if not fields.get("Files"):
        raise ResolveError(".dsc has no Files")  # ruling 4
    sha256s = _dsc_lines(dsc, fields, "Checksums-Sha256", 64)
    md5s = _dsc_lines(dsc, fields, "Files", 32)
    sha1s = _dsc_lines(dsc, fields, "Checksums-Sha1", 40) if "Checksums-Sha1" in fields else []
    for _, _, name in sha256s + md5s + sha1s:
        if not safe_name(name):
            raise ResolveError(f"{_clean(name)}: not a safe file name")
    if sorted((n, z) for _, z, n in sha256s) != sorted((n, z) for _, z, n in md5s) or \
            len({n for _, _, n in sha256s}) != len(sha256s):
        raise ResolveError(f"{_clean(dsc)}: Checksums-Sha256 and Files list different files")
    for _, _, name in sha256s:
        if name not in names:
            raise ResolveError(f"{_clean(name)} is in the .dsc but not in snapshot's srcfiles")
    for h, _, name in sha1s:
        if names.get(name) != h:
            raise ResolveError(f"{_clean(name)}: Checksums-Sha1 says {h}, {SNAPSHOT} says {names.get(name)}")
    return [_file(name, f"https://{SNAPSHOT}/file/{names[name]}", h, size, "sha256", h, f"{dsc} Checksums-Sha256")
            for h, size, name in sha256s]


def resolve_deb(key: str, arch: str, allow: set[str]) -> dict[str, Any]:
    src, _, ver = key.split(":", 1)[1].rpartition("@")
    url = f"https://{SNAPSHOT}/mr/package/{quote(src, safe='')}/{quote(ver, safe='')}/srcfiles?fileinfo=1"
    _snapshot_wait()
    try:
        doc = json.loads(text(url, allow, TEXT_LIMIT))
    except ValueError:
        raise ResolveError(f"{SNAPSHOT} srcfiles is not the expected JSON") from None
    names = srcfiles_map(doc)
    dsc = f"{src}_{ver.split(':', 1)[1] if ':' in ver else ver}.dsc"
    if dsc not in names:
        raise ResolveError(f"{SNAPSHOT} has no {dsc} in srcfiles")
    durl = f"https://{SNAPSHOT}/file/{names[dsc]}"
    _snapshot_wait()
    got = capped(durl, allow, dsc, TEXT_LIMIT, ("sha1", "sha256"))
    assert got is not None
    data, digests = got
    if digests["sha1"] != names[dsc]:
        raise ResolveError(f"{dsc}: sha1 mismatch: got {digests['sha1']}, {SNAPSHOT} says {names[dsc]}")
    try:
        body = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ResolveError(f"{dsc}: not UTF-8 text") from None
    others = dsc_files(parse_dsc(body), dsc, src, ver, names)
    return _entry("deb", arch, [_file(dsc, durl, digests["sha256"], len(data), "sha1", names[dsc],
                                      f"{SNAPSHOT} mr/package fileinfo")] + others)


# --- U7c: the apk route (design-notes "U7c precision" A1-A5) -----------------

def parse_apkbuild(body: str, commit: str, ver: str) -> list[tuple[str, str]]:
    """A4: (name, sha512) per `sha512sums` line; pkgver/pkgrel literals equal
    to `ver`. Read as text, never sourced."""
    def literal(field: str) -> str | None:
        m = re.search(rf"(?m)^{field}=(.*)$", body)
        if not m:
            return None
        v = m.group(1).strip()
        return v if v and not re.search(r"[$\"'`\s]", v) else None
    pv, pr = literal("pkgver"), literal("pkgrel")
    raw_v = re.search(r"(?m)^pkgver=(.*)$", body)
    raw_r = re.search(r"(?m)^pkgrel=(.*)$", body)
    shown = f"{raw_v.group(1).strip() if raw_v else '(none)'}-r{raw_r.group(1).strip() if raw_r else '(none)'}"
    if pv is None or pr is None or f"{pv}-r{pr}" != ver:
        raise ResolveError(f"APKBUILD at {commit}: pkgver/pkgrel {_clean(shown)} is not {ver}")
    m = re.search(r"(?ms)^sha512sums=([\"'])(.*?)\1", body)
    if not m:
        raise ResolveError(f"APKBUILD at {commit}: no sha512sums")
    block = m.group(2)
    if "$" in block or "`" in block:
        raise ResolveError(f"APKBUILD at {commit}: sha512sums is not a literal")
    out: list[tuple[str, str]] = []
    for ln in block.splitlines():
        if not ln.strip():
            continue
        lm = re.fullmatch(r"\s*([0-9a-f]{128})[ \t]+(\S+)\s*", ln)
        if not lm:
            raise ResolveError(f"APKBUILD at {commit}: a sha512sums line is not `<128 hex> <name>`")
        if not safe_name(lm.group(2)):
            raise ResolveError(f"{_clean(lm.group(2))}: not a safe file name")
        if lm.group(2) in {n for n, _ in out}:
            raise ResolveError(f"APKBUILD at {commit}: {lm.group(2)} is listed twice in sha512sums")
        out.append((lm.group(2), lm.group(1)))
    if not out:
        raise ResolveError(f"APKBUILD at {commit}: no sha512sums")
    return out


def _json(url: str, allow: set[str], what: str, missing_ok: bool = False) -> tuple[Any, dict[str, str]] | None:
    r = fetch(url, allow, missing_ok=missing_ok)
    if r is None:
        return None
    data = bytearray()
    for chunk in r.body:
        data += chunk
        if len(data) > TEXT_LIMIT:
            raise ResolveError(f"{what}: more than {TEXT_LIMIT} bytes")
    try:
        return json.loads(bytes(data).decode("utf-8")), r.headers
    except ValueError:
        raise ResolveError(f"{what} is not the expected JSON") from None


def _tree_blobs(listing: Any, repo: str, origin: str, commit: str) -> dict[str, str]:
    """A2 (ruling 1): basename -> path under `<repo>/<origin>/` of every blob
    of the recursive listing; each path segment passes the lock name rule;
    two blobs with one basename fail."""
    if not isinstance(listing, list):
        raise ResolveError(f"{GITLAB} tree listing is not the expected JSON")
    prefix = f"{repo}/{origin}/"
    out: dict[str, str] = {}
    for e in listing:
        if not isinstance(e, dict):
            raise ResolveError(f"{GITLAB} tree listing is not the expected JSON")
        if e.get("type") == "tree":
            continue
        path, name = e.get("path"), e.get("name")
        if not isinstance(path, str) or not isinstance(name, str) or not path.startswith(prefix):
            raise ResolveError(f"{GITLAB} tree listing is not the expected JSON")
        if e.get("type") != "blob" or e.get("mode") not in ("100644", "100755"):
            raise ResolveError(f"{origin}: {_clean(path)} at {commit} is not a regular file")
        rel = path[len(prefix):]
        segs = rel.split("/")
        if segs[-1] != name or not all(safe_name(x) for x in segs):
            raise ResolveError(f"{_clean(rel)}: not a safe file name")
        if name in out:
            raise ResolveError(f"{origin}: two files named {name} at {commit}")
        out[name] = rel
    return out


def resolve_apk(key: str, route: dict[str, Any], arch: str, allow: set[str]) -> dict[str, Any]:
    origin, _, ver = key.split(":", 1)[1].rpartition("@")
    commit, branch = route.get("commit"), route.get("branch")
    for field, value, rx in (("origin", route.get("origin"), re.escape(origin)), ("ver", route.get("ver"), re.escape(ver)),
                             ("commit", commit, r"[0-9a-f]{40}"), ("branch", branch, r"v\d+\.\d+")):
        if not isinstance(value, str) or not re.fullmatch(rx, value):
            raise ResolveError(f"apk {key}: route is malformed ({field})")
    found: dict[str, dict[str, str]] = {}
    for repo in ("main", "community"):
        got = _json(f"{APORTS_API}/tree?path={repo}/{origin}&ref={commit}&recursive=true&per_page=100", allow,
                    f"{GITLAB} tree listing", missing_ok=True)
        if got is None:
            continue
        listing, headers = got
        if headers.get("x-next-page"):
            raise ResolveError(f"{origin}: more than 100 files at {commit}")
        blobs = _tree_blobs(listing, repo, origin, commit)
        if blobs:  # ruling 2: an empty listing is "not here"
            found[repo] = blobs
    if len(found) == 2:
        raise ResolveError(f"{origin}: in both main and community at {commit}")
    if not found:
        raise ResolveError(f"{origin}: in neither main nor community at {commit}")
    repo, blobs = next(iter(found.items()))
    raw = f"https://{GITLAB}/alpine/aports/-/raw/{commit}/{repo}/{origin}"
    gl_from = f"gitlab files API content_sha256 at {commit}"

    def content_sha256(rel: str) -> str:
        meta = _json(f"{APORTS_API}/files/{quote(f'{repo}/{origin}/{rel}', safe='')}?ref={commit}", allow,
                     f"{GITLAB} files API")
        assert meta is not None
        want = meta[0].get("content_sha256") if isinstance(meta[0], dict) else None
        if not isinstance(want, str) or not re.fullmatch(r"[0-9a-f]{64}", want):
            raise ResolveError(f"{GITLAB} files API is not the expected JSON")
        return want
    if "APKBUILD" not in blobs or blobs["APKBUILD"] != "APKBUILD":
        raise ResolveError(f"{origin}: no APKBUILD at {commit}")
    want = content_sha256("APKBUILD")
    got = capped(f"{raw}/APKBUILD", allow, "APKBUILD")
    assert got is not None
    data, digests = got
    if digests["sha256"] != want:
        raise ResolveError(f"APKBUILD: sha256 mismatch: got {digests['sha256']}, gitlab files API says {want}")
    try:
        body = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ResolveError("APKBUILD: not UTF-8 text") from None
    sums = dict(parse_apkbuild(body, commit, ver))
    files = [_file("APKBUILD", f"{raw}/APKBUILD", want, len(data), "sha256", want, gl_from)]
    # Ruling 3: every regular file of the package directory is locked.
    for name, rel in sorted(blobs.items(), key=lambda kv: kv[1]):
        if name == "APKBUILD":
            continue
        url = f"{raw}/{rel}"
        if name in sums:
            hashed, size = stream(url, allow, ("sha512", "sha256"))
            if hashed["sha512"] != sums[name]:
                raise ResolveError(f"{name}: sha512 mismatch: got {hashed['sha512']}, APKBUILD sha512sums at {commit} "
                                   f"says {sums[name]}")
            files.append(_file(name, url, hashed["sha256"], size, "sha512", sums[name],
                               f"APKBUILD sha512sums at {commit}"))
        else:
            cs = content_sha256(rel)
            hashed, size = stream(url, allow)
            if hashed["sha256"] != cs:
                raise ResolveError(f"{name}: sha256 mismatch: got {hashed['sha256']}, gitlab files API says {cs}")
            files.append(_file(name, url, cs, size, "sha256", cs, gl_from))
    for name, sha512 in sums.items():
        if name in blobs:
            continue
        url = f"https://{DISTFILES}/distfiles/{branch}/{name}"
        hashed, size = stream(url, allow, ("sha512", "sha256"))
        if hashed["sha512"] != sha512:
            raise ResolveError(f"{name}: sha512 mismatch: got {hashed['sha512']}, APKBUILD sha512sums at {commit} "
                               f"says {sha512}")
        files.append(_file(name, url, hashed["sha256"], size, "sha512", sha512, f"APKBUILD sha512sums at {commit}"))
    entry = _entry("apk", arch, files)
    entry.update({"commit": commit, "branch": branch, "repo": repo})
    return entry


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
    # Round 1, item 8: pypi.org only for the pypi JSON request (first_allow).
    allow = {h for h in policy.get("hosts") or [] if isinstance(h, str)}
    if not isinstance(needs, dict):
        raise ResolveError("-: needs is not an object")
    for key in sorted(needs, key=str):  # round 1, item 11: every key first, before any URL
        if not valid_key(key):
            raise ResolveError(f"{_clean(key)}: not a valid lock key")
        if not isinstance(needs[key], dict) or not isinstance(needs[key].get("route", {}), dict):
            raise ResolveError(f"{_clean(key)}: the needs entry is not an object")
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
            elif kind == "deb":
                entry = resolve_deb(key, arch, allow)
            elif kind == "apk":
                entry = resolve_apk(key, (needs[key] or {}).get("route") or {}, arch, allow)
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
            needs_doc = json.load(fh)
        needs = needs_doc.get("needs") if isinstance(needs_doc, dict) else None
        with open(a.lock, encoding="utf-8") as fh:
            lock = json.load(fh)
        with open(a.policy, encoding="utf-8") as fh:
            policy = json.load(fh)
        with open(a.uv_lock, encoding="utf-8") as fh:
            uv = fh.read()
    except Exception as exc:  # noqa: BLE001 - round 1, item 1
        print(f"sources_lock: FAIL (resolve: -: {type(exc).__name__}: {_clean(exc)}; the lock is unchanged)",
              file=sys.stderr)
        return 1
    try:
        new, candidates, skipped = resolve(needs, lock, policy, uv, a.arch, a.refresh)
        tmp = os.path.join(a.out, ".lock.new.json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(lock_text(new))
        os.replace(tmp, os.path.join(a.out, "lock.new.json"))
    except ResolveError as exc:
        print(f"sources_lock: FAIL (resolve: {exc}; the lock is unchanged)", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - round 1, item 1: one FAIL line, never a traceback
        print(f"sources_lock: FAIL (resolve: -: {type(exc).__name__}: {_clean(exc)}; the lock is unchanged)",
              file=sys.stderr)
        return 1
    for key in skipped:
        print(f"sources_resolve: skip: {_clean(key)} (no {key.split(':', 1)[0]} route until Q71)", file=sys.stderr)
    for c in candidates:
        print("neo4j candidate: " + json.dumps(c, sort_keys=True))
    return 3 if candidates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
