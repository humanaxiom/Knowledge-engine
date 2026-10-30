"""The SBOM checker (platform-sbom; ADR-KE-016 point 2, design-notes N3).

Standard library only, Python 3.12, always run with `python -I`. Never
imported by engine/ and never shipped in an image. Every subcommand reads
read-only inputs and writes only stdout; the calling shell writes files.
Build-time tool, not an agent step: no spans.

  sbom_check.py finish --name N --ref R --arch A --git-sha S
                       --raw PATH --tar PATH [--site DIR --lock PATH]

`finish` (N6) reads syft's raw SPDX document and the image tar's
manifest.json (no extraction), and prints the final document: syft's
packages, files and relationships kept; `name` the bundle.json ref;
`documentNamespace` a fresh urn:uuid:<uuid4> (orchestrator ruling, U3); the
bundle tool added to the creators; three document
annotations (ke:ref, ke:arch, ke:image-config). With --site and --lock (the
ke-app image) it also checks that every installed distribution but the
project is in the SBOM at its uv.lock version (N7). It validates the result
(`validate`) and exits 1 naming the first failures. On success it prints
the unlicensed report (PSC-22, N8a 4-5) to stderr.

  sbom_check.py drift --sbom APP --base BASE --added-from PY --libpq PIN
                      --lock LOCK --licence PATH [--licence PATH ...]

`drift` (PSC-14/22, N7, N10 B3) checks the ke-app SBOM against an SBOM of
its base: the added dpkg set equals ADDED_PACKAGES, no pip, the CPython
version equals each licence file's line 1, libpq5 at the pin, psycopg-c at
its lock version and no psycopg-binary. Exit 1 naming each problem; on
success one summary line on stdout.

  sbom_check.py neo4j --official-config CFG --config CFG --sbom SBOM --tar TAR

`neo4j` (PSC-26, U4b, N16) checks ke-neo4j against the pinned official
image: the `docker image inspect .Config` fields equal (Labels aside),
no /var/lib/neo4j/products path, whiteout or fleet-management plugin file
in any layer of the saved tar, and the SBOM lists no fleet-management
plugin but lists Neo4j Community and the Temurin OpenJDK. Exit 1 naming
each problem; on success one summary line on stdout.

  sbom_check.py tree --official EXPORT --image EXPORT

  sbom_check.py lock-check --lock LOCK --policy POLICY --arch amd64|arm64
                           --sbom IMAGE=PATH [--sbom IMAGE=PATH ...] [--pending-neo4j]

`lock-check` (PSC-15, U7a; design-notes N5 and its U7 amendment) checks
docker/sources.lock.json against the policy and the bundled images' SBOMs:
schema, canonical text, file hosts, per-kind file rules, and coverage both
ways for the arch. Exit 0 with one summary line, 1 naming the first 20
problems, 2 on a bad argument. With `--pending-neo4j` (U7b rework round 1,
item 2) it exits 3 when the full problem list is non-empty and every problem
is a coverage miss for a `neo4j:` key (security's second fetch pending).

  sbom_check.py lock-needs --policy POLICY --sbom IMAGE=PATH [--sbom ...]
                           [--tar IMAGE=SAVED_TAR ...]

`lock-needs` (U7b; N5 amendment U7, item 3.3) prints needs.json for
scripts/sources_resolve.py: per lock key its kind, packages and route
inputs; Temurin's release file is read from the image's saved tar. Exit 1
naming the first 20 problems, 2 on a bad argument.

  sbom_check.py sources-check --lock LOCK --policy POLICY --dir DIR --arch A --set full|sample
  sbom_check.py index --lock LOCK --policy POLICY --arch A --set S --git-sha G
                      --files DIR --sbom IMAGE=PATH [--sbom ...]
  sbom_check.py notices --index PATH

U9a (design-notes "N9 amendment, U9"). `sources-check` runs before any write:
fetch.json canonical and matching this bundle, the directory's exact listing,
every planned file re-hashed; it prints the sorted distinct sha256 list.
`index` (after the SBOMs) prints app/sources/index.json: validate first, the
lock both ways, always/exempt problems, the copied listing. `notices` prints
the "Source code" section from that index, refusing (never escaping) any text
that could add a column or row. Exit 0, 1 (one FAIL line for an exception,
never a traceback) or 2 (bad argument).

`tree` compares two `docker export` tars: ke-neo4j equals the official
image minus /var/lib/neo4j/products (type, mode, owner, group, size, link;
a hard link counts as its target file in both, U5).

The licence classifier (PSC-15, PSC-22; design-notes N8, N8a, "N8
amendment, U5") is pure functions for U9's `index`: `licence_input`,
`is_gpl_id`, `needs_source`, `classify_package`, `classify_document`.
"""

from __future__ import annotations

import argparse
import ast
import errno
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import sys
import tarfile
import time
import tomllib
import uuid
from typing import Any
from urllib.parse import unquote

PROJECT_DIST = "knowledge-engine"
NAMESPACE_RE = re.compile(r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SPDXID_RE = re.compile(r"^SPDXRef-[A-Za-z0-9.-]+$")
RFC3339_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PURL_RE = re.compile(r"^pkg:(?P<type>[a-z0-9.+-]+)/(?:(?P<ns>[^@?#]+)/)?(?P<name>[^/@?#]+)@(?P<version>[^?#]+)")
PURL_TYPE_RE = re.compile(r"^pkg:([a-z0-9.+-]+)/")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def validate(doc: Any) -> list[str]:
    """N6: the SPDX 2.3 required-field set PSC-13 tests ([] = valid)."""
    if not isinstance(doc, dict):
        return ["the document is not a JSON object"]
    p: list[str] = []
    if doc.get("spdxVersion") != "SPDX-2.3":
        p.append(f"spdxVersion is {_clean(repr(doc.get('spdxVersion')))}, want SPDX-2.3")
    if doc.get("dataLicense") != "CC0-1.0":
        p.append(f"dataLicense is {_clean(repr(doc.get('dataLicense')))}, want CC0-1.0")
    if doc.get("SPDXID") != "SPDXRef-DOCUMENT":
        p.append(f"SPDXID is {_clean(repr(doc.get('SPDXID')))}, want SPDXRef-DOCUMENT")
    if not isinstance(doc.get("name"), str) or not doc.get("name"):
        p.append("name is empty")
    ns = doc.get("documentNamespace")
    if not isinstance(ns, str) or not NAMESPACE_RE.fullmatch(ns):
        p.append(f"documentNamespace {_clean(repr(ns))} is not urn:uuid:<lower-case uuid4>")
    info = doc.get("creationInfo")
    if not isinstance(info, dict):
        p.append("creationInfo is missing")
        info = {}
    if not RFC3339_UTC.fullmatch(str(info.get("created", ""))):
        p.append(f"creationInfo.created {_clean(repr(info.get('created')))} is not an RFC 3339 UTC time")
    creators = info.get("creators") if isinstance(info.get("creators"), list) else []
    if not any(isinstance(c, str) and c.startswith("Tool: syft-") for c in creators):
        p.append("creationInfo.creators has no `Tool: syft-<version>` entry")
    ids = {"SPDXRef-DOCUMENT"}
    packages = doc.get("packages") if isinstance(doc.get("packages"), list) else []
    for i, pkg in enumerate(packages):
        if not isinstance(pkg, dict):
            p.append(f"package {i} is not an object")
            continue
        sid = pkg.get("SPDXID")
        if not isinstance(sid, str) or not SPDXID_RE.fullmatch(sid):
            p.append(f"package {i} has SPDXID {_clean(repr(sid))}")
        elif sid in ids:
            p.append(f"package SPDXID {_clean(sid)} is not unique")
        else:
            ids.add(sid)
        if not pkg.get("name"):
            p.append(f"package {_clean(sid)} has no name")
        if not pkg.get("downloadLocation"):
            p.append(f"package {_clean(sid)} has no downloadLocation")
    for f in doc.get("files") if isinstance(doc.get("files"), list) else []:
        if isinstance(f, dict) and isinstance(f.get("SPDXID"), str):
            ids.add(f["SPDXID"])
    rels = doc.get("relationships") if isinstance(doc.get("relationships"), list) else []
    describes = 0
    for r in rels:
        if not isinstance(r, dict):
            p.append("a relationship is not an object")
            continue
        a, b = r.get("spdxElementId"), r.get("relatedSpdxElement")
        if r.get("relationshipType") == "DESCRIBES" and a == "SPDXRef-DOCUMENT":
            describes += 1
        for end in (a, b):
            if end not in ids and end not in ("NOASSERTION", "NONE"):
                p.append(f"relationship end {_clean(repr(end))} does not resolve")
    if describes != 1:
        p.append(f"the document DESCRIBES {describes} elements, want exactly 1")
    return p


def config_digest(tar_path: str) -> str:
    with tarfile.open(tar_path) as tar:
        member = tar.extractfile("manifest.json")
        if member is None:
            raise ValueError("manifest.json is not a file in the tar")
        manifest = json.load(member)
    if not isinstance(manifest, list) or len(manifest) != 1:
        raise ValueError(f"the tar's manifest.json holds {len(manifest) if isinstance(manifest, list) else '?'} "
                         "images, want exactly 1")
    cfg = str(manifest[0].get("Config", ""))
    m = re.fullmatch(r"blobs/sha256/([0-9a-f]{64})", cfg) or re.fullmatch(r"([0-9a-f]{64})\.json", cfg)
    if not m:
        raise ValueError(f"the tar's manifest.json Config {cfg!r} is not a sha256 digest")
    return "sha256:" + m.group(1)


def runtime_problems(doc: dict[str, Any], site: str, lock_path: str) -> list[str]:
    """N7: every installed distribution but the project is in the SBOM at
    its installed version, which is one of its uv.lock versions (the lock is
    name -> set of versions; a forked name is accepted, U4 review N7)."""
    with open(lock_path, "rb") as fh:
        entries = tomllib.load(fh).get("package", [])
    lock: dict[str, set[str]] = {}
    for entry in entries:
        lock.setdefault(_norm(entry["name"]), set()).add(entry["version"])
    listed: dict[str, set[str]] = {}
    for pkg in doc.get("packages") or []:
        for ref in pkg.get("externalRefs") or []:
            if ref.get("referenceType") != "purl":
                continue
            m = PURL_RE.match(str(ref.get("referenceLocator", "")))
            if m and m.group("type") == "pypi":
                listed.setdefault(_norm(unquote(m.group("name"))), set()).add(unquote(m.group("version")))
    p = []
    found = 0
    for dist in importlib.metadata.distributions(path=[site]):
        name = _norm(dist.metadata["Name"] or "")
        if not name or name == PROJECT_DIST:
            continue
        found += 1
        want = lock.get(name)
        if want is None:
            p.append(f"{name} {dist.version} is installed but not in uv.lock")
            continue
        if dist.version not in want:
            p.append(f"{name} is installed at {dist.version}, uv.lock has {sorted(want)}")
            continue
        if dist.version not in listed.get(name, set()):
            p.append(f"the SBOM does not list pkg:pypi/{name}@{dist.version} (it lists {sorted(listed.get(name, []))})")
    if not found:
        p.append(f"no installed distribution found in {site}")
    return p


# --- PSC-22: what the generator reports does not hide an obligation (U4) ----

MISSING = ("", "NONE", "NOASSERTION")
# syft's id for licence text it could not identify (security U4 H-1, N8).
HASH_ID_RE = re.compile(r"LicenseRef-[0-9a-f]{64}")
UNIDENTIFIED = "(unidentified licence text)"
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _hash_only(value: Any) -> bool:
    """N8 (H-1): the ids, split on whitespace and parentheses, without
    AND/OR/WITH (any case) and the exception after each WITH, are at least
    one and all syft hash ids."""
    if not isinstance(value, str):
        return False
    ids: list[str] = []
    skip = False
    for tok in (t for t in re.split(r"[\s()]+", value) if t):
        if skip:
            skip = False
        elif tok.upper() == "WITH":
            skip = True
        elif tok.upper() not in ("AND", "OR"):
            ids.append(tok)
    return bool(ids) and all(HASH_ID_RE.fullmatch(i) for i in ids)


def _missing(value: Any) -> bool:
    """N8 exact rule (U4): absent, null or not a string, or exactly one of
    MISSING (case-sensitive, no strip); H-1: or made only of hash ids."""
    return not isinstance(value, str) or value in MISSING or _hash_only(value)


def _purl(pkg: dict[str, Any]) -> str | None:
    refs = pkg.get("externalRefs")
    for ref in refs if isinstance(refs, list) else []:
        if isinstance(ref, dict) and ref.get("referenceType") == "purl":
            loc = ref.get("referenceLocator")
            return loc if isinstance(loc, str) and loc else None
    return None


def _clean(value: Any) -> str:
    return CONTROL_RE.sub(lambda m: f"\\x{ord(m.group()):02x}", str(value))


def _roots(doc: dict[str, Any]) -> set[str]:
    return {str(r.get("relatedSpdxElement")) for r in doc.get("relationships") or []
            if isinstance(r, dict) and r.get("relationshipType") == "DESCRIBES"
            and r.get("spdxElementId") == "SPDXRef-DOCUMENT"}


def _packages(doc: dict[str, Any]) -> list[dict[str, Any]]:
    roots = _roots(doc)
    return [p for p in doc.get("packages") or [] if isinstance(p, dict) and p.get("SPDXID") not in roots]


def unlicensed_report(doc: dict[str, Any]) -> dict[str, Any]:
    """N8 "all three missing", every package but the DESCRIBES root (N8a 4);
    rows counted per purl type, no-purl rows under "none" (N8a 5)."""
    rows: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}
    for pkg in _packages(doc):
        raw = pkg.get("licenseInfoFromFiles")
        files = [f for f in raw if not _missing(f)] if isinstance(raw, list) else []
        if _missing(pkg.get("licenseDeclared")) and _missing(pkg.get("licenseConcluded")) and not files:
            purl = _purl(pkg)
            m = PURL_TYPE_RE.match(purl or "")
            key = m.group(1) if m else "none"
            by_type[key] = by_type.get(key, 0) + 1
            fields = [pkg.get("licenseDeclared"), pkg.get("licenseConcluded")] + (raw if isinstance(raw, list) else [])
            rows.append({"spdxid": pkg.get("SPDXID"), "name": pkg.get("name"), "purl": purl,
                         "unidentified": any(_hash_only(f) for f in fields)})
    return {"count": len(rows), "by_type": by_type, "packages": rows}


def report_lines(name: str, report: dict[str, Any]) -> list[str]:
    types = ", ".join(f"{t}: {n}" for t, n in sorted(report["by_type"].items()))
    out = [f"{name}: unlicensed packages (no licence, NOASSERTION or unidentified text): {report['count']}"
           + (f" ({types})" if types else "")]
    for r in report["packages"]:
        line = (f"{name}:   {_clean(r['purl'])}" if r["purl"]
                else f"{name}:   {_clean(r['spdxid'])} {_clean(r['name'])} (no purl)")
        out.append(line + (f" {UNIDENTIFIED}" if r.get("unidentified") else ""))
    return out


def _qualifiers(purl: str) -> dict[str, str]:
    q = purl.split("?", 1)[1].split("#", 1)[0] if "?" in purl else ""
    return {k: unquote(v) for k, _, v in (part.partition("=") for part in q.split("&") if part)}


def always_matches(image: str, doc: dict[str, Any], always: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """N10 `always` for one image: (flagged SPDXIDs, problems)."""
    flagged: list[str] = []
    problems: list[str] = []
    pkgs = [(p, _purl(p) or "") for p in _packages(doc)]
    for entry in always:
        if entry.get("image") != image:
            continue
        match = str(entry.get("match", ""))
        hits = []
        for pkg, purl in pkgs:
            if match.startswith("upstream="):
                up = _qualifiers(purl).get("upstream", "").split("@", 1)[0]
                ok = bool(up) and up == match[len("upstream="):]
            else:
                ok = purl.split("@", 1)[0] == match and "@" in purl
            if ok:
                hits.append(str(pkg.get("SPDXID")))
        if not hits:
            problems.append(f"{image}: expected component not catalogued: {match} ({entry.get('why', '')})")
        flagged += [h for h in hits if h not in flagged]
    return flagged, problems


# --- PSC-15, PSC-22: the licence classifier (U5; N8, N8a, N8 amendment U5) ---

# N8: the anchored GPL-family pattern, on the lower-cased id without a
# leading `licenseref-`; N8a ruling 5: the token rule, any token of the
# lower-cased text split on [^a-z0-9]+.
GPL_ID_RE = re.compile(r"(a|l)?gpl(-?v?\d+(\.\d+)*)?(\+|-only|-or-later)?(-with-[a-z0-9-]+-exception)?")
# Rework round 1 (security L-1): a token containing `gpl`, the token
# `affero`, or the consecutive tokens `general public licen[cs]e[s]`.
GPL_PHRASE_RE = re.compile(r"(?:^| )general public licen[cs]es?(?: |$)")
UNKNOWN_LEAVES = ("NONE", "NOASSERTION")
# Rework round 2 (review R1-B1): a leaf is an SPDX 2.3 idstring, with an
# optional DocumentRef-<id>: prefix and the `+` suffix; any other leaf makes
# the text unparseable (the token-or-unknown fallback).
LEAF_RE = re.compile(r"(DocumentRef-[A-Za-z0-9.-]+:)?[A-Za-z0-9.-]+\+?")
DOCREF_RE = re.compile(r"DocumentRef-[A-Za-z0-9.-]+:")
# Runs of unparseable text: split on anything outside [A-Za-z0-9.-], so `+`
# and `:` split runs too (rework round 3, review R2-B2).
RUN_SPLIT_RE = re.compile(r"[^A-Za-z0-9.-]+")
# A hash id anywhere in a leaf or run (rework round 3, security R2-L1); 64
# hex exactly, so 65 hex digits are still not a hash (round 3 item 4).
HASH_IN_RE = re.compile(r"LicenseRef-[0-9a-f]{64}(?![0-9a-f])")


class _Unparsed(Exception):
    pass


def _set(value: Any) -> bool:
    """The classifier's "set" (N8 amendment, U5, item 1): a string, not
    exactly "", NONE or NOASSERTION. A hash-only value is set (unknown ids)."""
    return isinstance(value, str) and value not in MISSING


def _input_parts(pkg: Any) -> list[str]:
    if not isinstance(pkg, dict):
        return []
    declared, concluded = pkg.get("licenseDeclared"), pkg.get("licenseConcluded")
    parts = [v for v in (declared, concluded) if _set(v)]
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    if not parts:
        raw = pkg.get("licenseInfoFromFiles")
        parts = [f for f in raw if _set(f)] if isinstance(raw, list) else []
    return parts


def licence_input(pkg: Any) -> str | None:
    """N8 input selection: declared, concluded, or both (`(d) AND (c)`), else
    the set licenseInfoFromFiles entries; None when nothing is set."""
    parts = _input_parts(pkg)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else " AND ".join(f"({x})" for x in parts)


def _token_hit(text: str) -> bool:
    tokens = [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]
    return (any("gpl" in t or t == "affero" for t in tokens)
            or bool(GPL_PHRASE_RE.search(" ".join(tokens))))


def _bare(id_: str) -> str:
    """The id without a leading DocumentRef-<id>: (rework round 2)."""
    m = DOCREF_RE.match(id_)
    return id_[m.end():] if m else id_


def _unknown_id(id_: str) -> bool:
    """A hash id anywhere in it (round 3), or NONE/NOASSERTION under ASCII
    case-fold (round 1) once the DocumentRef-<id>: prefix (round 2) and
    leading/trailing `.`, `-`, `+` (round 3, review R2-B1) are removed."""
    bare = _bare(id_).strip(".-+")
    if HASH_IN_RE.search(id_):
        return True
    if not bare.isascii():
        return False
    if bare.upper() in UNKNOWN_LEAVES:
        return True
    # U6 (review I-r3-1, security I-9): outside a LicenseRef- id, a `.`- or
    # `-`-separated segment equal to NONE/NOASSERTION is unknown too.
    return (not bare.lower().startswith("licenseref-")
            and any(seg.upper() in UNKNOWN_LEAVES for seg in re.split(r"[.-]", bare)))


def _unknown_in_text(text: str) -> bool:
    return bool(HASH_ID_RE.search(text)) or any(_unknown_id(r) for r in RUN_SPLIT_RE.split(text) if r)


def _pattern_hit(id_: str) -> bool:
    low = _bare(id_).lower()
    if low.startswith("licenseref-"):
        low = low[len("licenseref-"):]
    return bool(GPL_ID_RE.fullmatch(low))


def is_gpl_id(id_: Any) -> bool:
    """N8 pattern, or else the N8a token rule (fail closed)."""
    return isinstance(id_, str) and (_pattern_hit(id_) or _token_hit(id_))


def _parse(tokens: list[str]) -> Any:
    """SPDX 2.3 Annex D: WITH > AND > OR, parentheses override; operators
    any case. Nodes: ("leaf", id), ("and"|"or", [children])."""
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def kw(t: str | None) -> str:
        return t.upper() if t is not None and t.isascii() else ""

    def is_op(t: str | None) -> bool:
        return kw(t) in ("AND", "OR", "WITH")

    def take() -> str:
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def binary(op: str, sub: Any) -> Any:
        children = [sub()]
        while kw(peek()) == op:
            take()
            children.append(sub())
        return children[0] if len(children) == 1 else (op.lower(), children)

    def primary() -> Any:
        t = peek()
        if t is None or t == ")" or is_op(t):
            raise _Unparsed
        if t == "(":
            take()
            node = expr()
            if peek() != ")":
                raise _Unparsed
            take()
            return node
        leaf = take()
        if not LEAF_RE.fullmatch(leaf):  # rework round 2: not an SPDX idstring
            raise _Unparsed
        if kw(peek()) == "WITH":
            take()
            e = peek()
            if e is None or e in ("(", ")") or is_op(e) or not LEAF_RE.fullmatch(e):
                raise _Unparsed
            return ("with", leaf, take())
        return ("leaf", leaf)

    def expr() -> Any:
        return binary("OR", lambda: binary("AND", primary))

    node = expr()
    if pos != len(tokens):
        raise _Unparsed
    return node


def _url_ref(id_: str) -> bool:
    """A LicenseRef- id holding http (N8a 2-4), DocumentRef prefix aside."""
    bare = _bare(id_).lower()
    return bare.startswith("licenseref-") and "http" in bare


def _leaf(id_: str) -> tuple[bool, bool, bool]:
    """(needs, unparsed, unidentified) of one id."""
    url = _url_ref(id_)
    if _unknown_id(id_):
        return True, url, True
    if _pattern_hit(id_):
        return True, url, False
    if _token_hit(id_):
        return True, True, False
    return False, url, False


def _evaluate(node: Any) -> tuple[bool, bool, bool]:
    if node[0] == "leaf":
        return _leaf(node[1])
    if node[0] == "with":
        needs, unparsed, unidentified = _leaf(node[1])
        exc = node[2]
        if _unknown_id(exc):  # addition b: an unknown exception id
            return True, unparsed, True
        if _pattern_hit(exc) or _token_hit(exc):  # ruling 4: a GPL-family exception slot (malformed)
            return True, True, unidentified
        return needs, unparsed or _url_ref(exc), unidentified  # round 2 (R1-N1): an http ref is listed
    results = [_evaluate(c) for c in node[1]]
    needs = any(r[0] for r in results) if node[0] == "and" else all(r[0] for r in results)
    return needs, any(r[1] for r in results), any(r[2] for r in results)


def needs_source(expr: Any) -> tuple[bool, dict[str, bool]]:
    """N8: needs(OR) = all, needs(AND) = any, needs(X WITH e) = needs(X);
    unknown leaves (hash ids, NONE, NOASSERTION) need source, unidentified.
    Unparseable text needs source if the token rule hits it or it holds a
    hash id or a NONE/NOASSERTION run (any case); non-ASCII text needs
    source; both are listed unparsed (N8 amendment, U5, rework round 1)."""
    if not isinstance(expr, str):
        return True, {"unparsed": True, "unidentified": False}
    if not expr.isascii():  # rework ruling 3 (security L-3): SPDX ids are ASCII
        return True, {"unparsed": True, "unidentified": _unknown_in_text(expr)}
    try:
        needs, unparsed, unidentified = _evaluate(_parse(re.findall(r"\(|\)|[^\s()]+", expr)))
    except (_Unparsed, RecursionError):
        unknown = _unknown_in_text(expr)  # a hash id or a NONE/NOASSERTION run (rework ruling 1)
        return _token_hit(expr) or unknown, {"unparsed": True, "unidentified": unknown}
    return needs, {"unparsed": unparsed, "unidentified": unidentified}


def classify_package(pkg: dict[str, Any]) -> dict[str, Any]:
    """needs = any over licence_input's parts, flags OR-ed (N8 amendment, U5).
    U9's index takes `needs` from here and never re-derives it from
    `expression`, which is a record only (rework round 1, review N5)."""
    needs = unparsed = unidentified = False
    parts = _input_parts(pkg)
    for part in parts:
        n, info = needs_source(part)
        needs, unparsed, unidentified = needs or n, unparsed or info["unparsed"], unidentified or info["unidentified"]
    return {"needs": needs, "expression": licence_input(pkg), "unlicensed": not parts, "unparsed": unparsed,
            "unidentified": unidentified, "purl": _purl(pkg), "spdxid": pkg.get("SPDXID"), "name": pkg.get("name")}


def classify_document(image: str, doc: dict[str, Any], always: list[dict[str, Any]],
                      exempt: Any = ()) -> list[dict[str, Any]]:
    """One row per package but the DESCRIBES root; an `always` match (N10)
    needs source whatever the licence says; a reviewed `exempt` match (U6)
    clears the package, also when `always` matches it (both flags set; U9
    lists it as "always, cleared by exemption"). `always` overrides only
    the classifier (orchestrator correction to U6 ruling 1)."""
    flagged, _ = always_matches(image, doc, always)
    exempted, _ = exempt_matches(image, doc, list(exempt))
    rows = []
    for pkg in _packages(doc):
        row = classify_package(pkg)
        sid = str(pkg.get("SPDXID"))
        row["always"] = sid in flagged
        row["exempt"] = sid in exempted
        if row["exempt"]:
            row["needs"] = False  # a reviewed exemption clears it, `always` or not
        elif row["always"]:
            row["needs"] = True
        rows.append(row)
    return rows


def _purl_base(purl: str) -> str:
    """The purl without qualifiers and subpath, as written (U6: literal)."""
    return purl.split("?", 1)[0].split("#", 1)[0]


def exempt_matches(image: str, doc: dict[str, Any], exempt: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """N10 `exempt` for one image: (flagged SPDXIDs, problems). An entry names
    a versioned purl without qualifiers and matches a package whose purl,
    qualifiers and subpath removed, equals it as a string; an entry with no
    such package in its image is a problem, so a version bump voids the
    exemption (U6; N10 amendment, U6, item 1)."""
    flagged: list[str] = []
    problems: list[str] = []
    keys = [(str(p.get("SPDXID")), _purl_base(_purl(p) or "")) for p in _packages(doc)]
    for entry in exempt:
        if not isinstance(entry, dict) or entry.get("image") != image:
            continue
        want = entry.get("package")
        if not isinstance(want, str) or not PURL_RE.match(want) or "?" in want or "#" in want:
            problems.append(f"{image}: exempt entry is not a versioned purl: {_clean(want)}")
            continue
        hits = [sid for sid, key in keys if key == want]
        if not hits:
            problems.append(f"{image}: exempt entry matches nothing: {_clean(want)}; the version moved or the "
                            "package left: review again")
        elif len(hits) > 1:  # U9 item 6 (security U6 L-1): an exemption clears exactly one package
            problems.append(f"{image}: exempt entry matches {len(hits)} packages: {_clean(want)} "
                            f"({', '.join(_clean(h) for h in hits)}); an exemption clears exactly one package: "
                            "review again")
        flagged += [h for h in hits if h not in flagged]
    return flagged, problems


# --- PSC-14/22 B3, N7: the image-side drift check (U4) ----------------------

def _named(doc: dict[str, Any], ptype: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for pkg in _packages(doc):
        m = PURL_RE.match(_purl(pkg) or "")
        if m and m.group("type") == ptype:
            n = unquote(m.group("name"))
            out.setdefault(_norm(n) if ptype == "pypi" else n, set()).add(unquote(m.group("version")))
    return out


def _cpython(app: dict[str, Any]) -> set[str]:
    """CPython versions: the non-namespaced pkg:generic/python rows (syft's
    binary cataloguer, U3), the set drift checks and prints (U5 review B3)."""
    py = set()
    for pkg in _packages(app):
        m = PURL_RE.match(_purl(pkg) or "")
        if m and m.group("type") == "generic" and not m.group("ns") and m.group("name") == "python":
            py.add(unquote(m.group("version")))
    return py


def drift_problems(app: dict[str, Any], base: dict[str, Any], added: frozenset[str] | set[str],
                   licence_texts: dict[str, str]) -> list[str]:
    p = []
    debs = set(_named(app, "deb")) - set(_named(base, "deb"))
    for n in sorted(debs - set(added)):
        p.append(f"ke-app adds the Debian package {_clean(n)}, which ADDED_PACKAGES does not name")
    for n in sorted(set(added) - debs):
        p.append(f"ADDED_PACKAGES names {_clean(n)}, which the ke-app SBOM does not add to its base")
    pypi = _named(app, "pypi")
    if "pip" in pypi:
        p.append(f"the ke-app SBOM lists pip {_clean(sorted(pypi['pip']))} (pip is not shipped)")
    py = _cpython(app)
    if len(py) != 1:
        p.append(f"the ke-app SBOM lists CPython (pkg:generic/python) at {_clean(sorted(py))}, want exactly one version")
    for path, text in sorted(licence_texts.items()):
        m = re.match(r"^CPython (\d+\.\d+\.\d+):", text.split("\n", 1)[0])
        if not m:
            p.append(f"{path}: line 1 does not start `CPython X.Y.Z:`")
        elif len(py) == 1 and m.group(1) not in py:
            p.append(f"{path} names CPython {m.group(1)}, the ke-app SBOM lists {_clean(sorted(py)[0])}")
    return p


def psycopg_problems(app: dict[str, Any], libpq_pin: str, psycopg_c_version: str | set[str] | frozenset[str]
                     ) -> list[str]:
    p = []
    major = libpq_pin.split(".", 1)[0]
    libpq = [(unquote(m.group("version")), _qualifiers(purl).get("upstream", "").split("@", 1)[0])
             for purl in (_purl(x) or "" for x in _packages(app))
             for m in [PURL_RE.match(purl)] if m and m.group("type") == "deb" and m.group("name") == "libpq5"]
    if (libpq_pin, f"postgresql-{major}") not in libpq:
        p.append(f"the ke-app SBOM does not list libpq5 {libpq_pin} (upstream postgresql-{major}): {_clean(libpq)}")
    pypi = _named(app, "pypi")
    want = {psycopg_c_version} if isinstance(psycopg_c_version, str) else set(psycopg_c_version)
    if not want & pypi.get("psycopg-c", set()):
        p.append(f"the ke-app SBOM does not list psycopg-c at a locked version {sorted(want)}: "
                 f"{_clean(sorted(pypi.get('psycopg-c', [])))}")
    if "psycopg-binary" in pypi:
        p.append(f"the ke-app SBOM lists psycopg-binary {_clean(sorted(pypi['psycopg-binary']))} (PSC-25)")
    return p


def added_packages(source_text: str) -> frozenset[str]:
    """ADDED_PACKAGES of tests/test_notice_ke_app.py, by ast (never imported)."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        raise ValueError(f"the ADDED_PACKAGES source does not parse: {exc}") from exc
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ADDED_PACKAGES" for t in node.targets):
            v = node.value
            if (isinstance(v, ast.Call) and getattr(v.func, "id", "") == "frozenset" and len(v.args) == 1
                    and not v.keywords):
                try:
                    items = ast.literal_eval(v.args[0])
                except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
                    raise ValueError(f"ADDED_PACKAGES is not a literal: {exc}") from exc
                if isinstance(items, (set, list, tuple)) and all(isinstance(i, str) for i in items):
                    return frozenset(items)
            raise ValueError("ADDED_PACKAGES is not frozenset({<string literals>})")
    raise ValueError("no ADDED_PACKAGES assignment")


def drift(a: argparse.Namespace) -> int:
    try:
        docs = []
        for path in (a.sbom, a.base):
            with open(path, encoding="utf-8") as fh:
                docs.append(json.load(fh))
        with open(a.added_from, encoding="utf-8") as fh:
            added = added_packages(fh.read())
        with open(a.lock, "rb") as fh:
            locked = {p["version"] for p in tomllib.load(fh).get("package", []) if _norm(p["name"]) == "psycopg-c"}
        texts = {}
        for path in a.licence:
            with open(path, encoding="utf-8") as fh:
                texts[path] = fh.read()
    except (OSError, ValueError, KeyError) as exc:
        print(f"sbom_check: drift: {exc}", file=sys.stderr)
        return 1
    problems = drift_problems(docs[0], docs[1], added, texts)
    problems += psycopg_problems(docs[0], a.libpq, locked)
    for line in problems:
        print(f"sbom_check: drift: {line}", file=sys.stderr)
    if problems:
        return 1
    py = sorted(_cpython(docs[0]))
    pc = sorted(locked & _named(docs[0], "pypi").get("psycopg-c", set()))
    major = a.libpq.split(".", 1)[0]
    print(f"sbom_check: drift: ok: added {', '.join(sorted(added))}; no pip; CPython {_clean(', '.join(py))} "
          f"({len(texts)} licence files); libpq5 {a.libpq} (postgresql-{major}); psycopg-c {', '.join(pc)}, "
          "no psycopg-binary")
    return 0


def finish(a: argparse.Namespace) -> int:
    for label, value, rx in (("--name", a.name, NAME_RE), ("--git-sha", a.git_sha, SHA_RE)):
        if not rx.fullmatch(value):
            print(f"sbom_check: {label} {value!r} fails its pattern", file=sys.stderr)
            return 2
    if a.arch not in ("amd64", "arm64"):
        print(f"sbom_check: --arch {a.arch!r} is not amd64 or arm64", file=sys.stderr)
        return 2
    try:
        with open(a.raw, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"sbom_check: {a.name}: the generator's document is unreadable: {exc}", file=sys.stderr)
        return 1
    if not isinstance(doc, dict):
        print(f"sbom_check: {a.name}: the generator's document is not a JSON object", file=sys.stderr)
        return 1
    try:
        digest = config_digest(a.tar)
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"sbom_check: {a.name}: cannot read the image config digest: {exc}", file=sys.stderr)
        return 1
    tool = f"Tool: knowledge-engine-bundle-{a.git_sha[:12]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    doc["name"] = a.ref
    doc["documentNamespace"] = f"urn:uuid:{uuid.uuid4()}"
    info = doc.get("creationInfo") if isinstance(doc.get("creationInfo"), dict) else {}
    creators = list(info.get("creators") or [])
    if tool not in creators:
        creators.append(tool)
    info["creators"] = creators
    doc["creationInfo"] = info
    doc["annotations"] = list(doc.get("annotations") or []) + [
        {"annotationDate": now, "annotationType": "OTHER", "annotator": tool, "comment": f"ke:{k}={v}"}
        for k, v in (("ref", a.ref), ("arch", a.arch), ("image-config", digest))]
    problems = validate(doc)
    if a.site or a.lock:
        if not (a.site and a.lock):
            problems.append("--site and --lock go together")
        else:
            problems += runtime_problems(doc, a.site, a.lock)
    if problems:
        for line in problems[:20]:
            print(f"sbom_check: {a.name}: {line}", file=sys.stderr)
        return 1
    print(json.dumps(doc, indent=2))
    for line in report_lines(a.name, unlicensed_report(doc)):
        print(f"sbom_check: {line}", file=sys.stderr)
    return 0


# --- PSC-26 (U4b, Q67; design-notes N16): ke-neo4j against the official image -

PRODUCTS = "var/lib/neo4j/products"
FLEET = "neo4j-fleet-management-plugin"
FLEET_PURL = "pkg:maven/com.neo4j/neo4j-fleet-management-plugin"
# PSC-26 *Image config carried over*. Labels are not compared: compose adds
# its com.docker.compose.* labels to every image it builds (ke-app has them).
NEO4J_CONFIG_FIELDS = ("Entrypoint", "Cmd", "Env", "User", "WorkingDir", "ExposedPorts", "Volumes",
                       "Healthcheck", "StopSignal", "OnBuild", "Shell")
NEO4J_REQUIRED = (("Neo4j Community", "pkg:maven/org.neo4j/neo4j"),
                  ("the Temurin OpenJDK", "pkg:generic/oracle/openjdk"))


def _unset(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def neo4j_config_problems(official: Any, image: Any) -> list[str]:
    """Each NEO4J_CONFIG_FIELDS value of `docker image inspect .Config` equal
    in both; absent, null and empty are one "unset" value (PSC-26)."""
    if not isinstance(official, dict) or not isinstance(image, dict):
        return ["a config is not a JSON object (docker image inspect --format '{{json .Config}}')"]
    problems = []
    for key in NEO4J_CONFIG_FIELDS:
        want, have = official.get(key), image.get(key)
        if _unset(want) and _unset(have):
            continue
        if want != have:
            problems.append(f"config {key}: ke-neo4j has {_clean(json.dumps(have))}, "
                            f"the official image has {_clean(json.dumps(want))}")
    return problems


def _rel(name: str) -> str:
    while name.startswith(("./", "/")):
        name = name[2:] if name.startswith("./") else name[1:]
    return name.rstrip("/")


def _in_products(rel: str) -> bool:
    return rel == PRODUCTS or rel.startswith(PRODUCTS + "/")


def _plugin_name(rel: str) -> bool:
    return FLEET in rel.rsplit("/", 1)[-1].lower()


def _layer_problems(label: str, layer: tarfile.TarFile) -> list[str]:
    problems = []
    for member in layer:
        rel = _rel(member.name)
        base = rel.rsplit("/", 1)[-1]
        if _in_products(rel):
            problems.append(f"{label}: {_clean(rel)} is under /{PRODUCTS}")
        elif base == ".wh.products" and rel.rsplit("/", 1)[0] == "var/lib/neo4j":
            problems.append(f"{label}: {_clean(rel)} is a whiteout of /{PRODUCTS}: the jar is hidden, not gone")
        elif _plugin_name(rel):
            problems.append(f"{label}: {_clean(rel)} is the fleet-management plugin")
    return problems


def neo4j_tar_problems(tar_path: str) -> list[str]:
    """No /var/lib/neo4j/products path, whiteout of it, or file named for the
    fleet-management plugin in any layer manifest.json lists (PSC-26)."""
    problems: list[str] = []
    checked = 0
    with tarfile.open(tar_path) as tar:
        member = tar.extractfile("manifest.json")
        if member is None:
            return ["manifest.json is not a file in the tar"]
        manifest = json.load(member)
        if not isinstance(manifest, list) or not manifest:
            return ["the tar's manifest.json lists no image"]
        for entry in manifest:
            layers = entry.get("Layers") if isinstance(entry, dict) else None
            if not isinstance(layers, list) or not layers:
                problems.append("a manifest.json entry lists no layers")
                continue
            for name in layers:
                try:
                    blob = tar.extractfile(str(name))
                except KeyError:
                    blob = None
                if blob is None:
                    problems.append(f"layer {_clean(name)} is listed in manifest.json but not in the tar")
                    continue
                try:
                    with tarfile.open(fileobj=blob, mode="r:*") as layer:
                        problems += _layer_problems(f"layer {_clean(name)}", layer)
                except tarfile.TarError as exc:
                    problems.append(f"layer {_clean(name)} cannot be read: {_clean(exc)}")
                checked += 1
    if not checked and not problems:
        problems.append("no layer was checked")
    return problems


def neo4j_sbom_problems(doc: Any) -> list[str]:
    """No fleet-management plugin package, by purl (any version) or by name;
    Neo4j Community and the Temurin OpenJDK still listed (PSC-26)."""
    if not isinstance(doc, dict):
        return ["the SBOM is not a JSON object"]
    problems = []
    found = {purl: False for _, purl in NEO4J_REQUIRED}
    for pkg in _packages(doc):
        purls = [str(r.get("referenceLocator", "")) for r in pkg.get("externalRefs") or []
                 if isinstance(r, dict) and r.get("referenceType") == "purl"]
        names = [unquote(p).lower() for p in purls]
        if (any(n.split("@", 1)[0].split("?", 1)[0] == FLEET_PURL for n in names)
                or FLEET in str(pkg.get("name", "")).lower()):
            problems.append(f"the SBOM lists the fleet-management plugin: {_clean(pkg.get('name'))} "
                            f"{_clean(' '.join(purls) or '(no purl)')}")
        for purl in found:
            if any(p.split("@", 1)[0] == purl and "@" in p for p in purls):
                found[purl] = True
    for label, purl in NEO4J_REQUIRED:
        if not found[purl]:
            problems.append(f"the SBOM does not list {label} ({purl})")
    return problems


TreeEntry = tuple[str, int, int, int, int, str]


def tree_listing(tar_path: str) -> dict[str, TreeEntry]:
    """path -> (type, mode, uid, gid, size, link target) of a `docker export`
    tar; size is a regular file's (0 otherwise); a hard link's target is
    its path through _rel (U5, U4b review N6)."""
    kinds = {tarfile.REGTYPE: "file", tarfile.AREGTYPE: "file", tarfile.DIRTYPE: "dir", tarfile.SYMTYPE: "symlink",
             tarfile.LNKTYPE: "hardlink", tarfile.CHRTYPE: "char", tarfile.BLKTYPE: "block", tarfile.FIFOTYPE: "fifo"}
    out: dict[str, TreeEntry] = {}
    with tarfile.open(tar_path, mode="r:*") as tar:
        for m in tar:
            rel = _rel(m.name) or "."
            kind = kinds.get(m.type, "other")
            link = m.linkname if kind == "symlink" else (_rel(m.linkname) if kind == "hardlink" else "")
            out[rel] = (kind, m.mode & 0o7777, m.uid, m.gid, m.size if kind == "file" else 0, link)
    return out


def _resolve_hardlinks(listing: dict[str, TreeEntry]) -> dict[str, TreeEntry]:
    """A hard link becomes its target's regular file (its size); a target
    absent or not a file leaves it a hardlink, so it differs (fail closed)."""
    out = dict(listing)
    for rel, entry in listing.items():
        if entry[0] == "hardlink":
            target = listing.get(entry[5])
            if target is not None and target[0] == "file":
                out[rel] = ("file", entry[1], entry[2], entry[3], target[4], "")
    return out


def neo4j_tree_problems(official: dict[str, TreeEntry], image: dict[str, TreeEntry]) -> list[str]:
    """Every official path outside /var/lib/neo4j/products is in ke-neo4j
    with the same type, mode, owner, group, size and link target, and
    ke-neo4j adds no path (PSC-26). A hard link and a regular file are the
    same file when the link's target is (N16; both ways, U5)."""
    official, image = _resolve_hardlinks(official), _resolve_hardlinks(image)
    problems = []
    for rel, want in sorted(official.items()):
        if _in_products(rel):
            continue
        have = image.get(rel)
        if have is None:
            problems.append(f"/{_clean(rel)} is in the official image, not in ke-neo4j")
            continue
        if tuple(have) != tuple(want):
            problems.append(f"/{_clean(rel)}: ke-neo4j has {tuple(have)}, the official image has {tuple(want)}")
    for rel in sorted(set(image) - set(official)):
        problems.append(f"/{_clean(rel)} is in ke-neo4j, not in the official image")
    for rel in sorted(r for r in image if _in_products(r) or _plugin_name(r)):
        problems.append(f"/{_clean(rel)} is in ke-neo4j: products/ or the fleet-management plugin")
    return problems


def neo4j(a: argparse.Namespace) -> int:
    try:
        docs = []
        for path in (a.official_config, a.config, a.sbom):
            with open(path, encoding="utf-8") as fh:
                docs.append(json.load(fh))
        problems = neo4j_config_problems(docs[0], docs[1])
        problems += neo4j_tar_problems(a.tar)
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"sbom_check: ke-neo4j: {_clean(exc)}", file=sys.stderr)
        return 1
    problems += neo4j_sbom_problems(docs[2])
    for line in problems:
        print(f"sbom_check: ke-neo4j: {line}", file=sys.stderr)
    if problems:
        return 1
    print("sbom_check: ke-neo4j: ok: config equals the official image's "
          f"({', '.join(NEO4J_CONFIG_FIELDS)}); no /{PRODUCTS} or fleet-management plugin in the saved tar "
          "or the SBOM; the SBOM lists Neo4j Community and the Temurin OpenJDK")
    return 0


def tree(a: argparse.Namespace) -> int:
    try:
        problems = neo4j_tree_problems(tree_listing(a.official), tree_listing(a.image))
    except (OSError, tarfile.TarError) as exc:
        print(f"sbom_check: tree: {_clean(exc)}", file=sys.stderr)
        return 1
    for line in problems:
        print(f"sbom_check: tree: {line}", file=sys.stderr)
    if problems:
        return 1
    print("sbom_check: tree: ok: ke-neo4j equals the official image minus /" + PRODUCTS)
    return 0


# --- PSC-15: the source lock, pure half (U7a; design-notes N5 and its U7 amendment) -

LOCK_ARCHES = ("amd64", "arm64")
LOCK_KINDS = ("deb", "pgdg", "apk", "neo4j", "temurin", "pypi", "maven")
LOCK_KEY_RES = {
    "deb": re.compile(r"deb:[a-z0-9][a-z0-9+.-]+@([0-9]+:)?[0-9][A-Za-z0-9.+~-]*"),
    "pgdg": re.compile(r"pgdg:[a-z0-9][a-z0-9+.-]+@([0-9]+:)?[0-9][A-Za-z0-9.+~-]*"),
    "apk": re.compile(r"apk:[a-z0-9][a-z0-9+._-]*@[0-9][A-Za-z0-9._+]*-r[0-9]+"),
    "neo4j": re.compile(r"neo4j:neo4j@\d+(\.\d+)+"),
    "temurin": re.compile(r"temurin:jdk-\d+(\.\d+)*\+\d+"),
    "pypi": re.compile(r"pypi:[a-z0-9]+(-[a-z0-9]+)*@[0-9][A-Za-z0-9.+!-]*"),
    "maven": re.compile(r"maven:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+@[A-Za-z0-9_.+-]+"),
}
LOCK_FILE_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}")  # U7d round 1, item 10: a leading _
HEX_RE = re.compile(r"[0-9a-f]+")
ALG_LEN = {"sha1": 40, "sha256": 64, "sha512": 128}
NEO4J_FROM_RE = re.compile(r"second fetch: security (\d{4}-\d{2}-\d{2}), docs/evidence/platform-sbom/sources-provenance\.md")
# PS-1.2 (rule 2): no URL literal in Python; the deb file URL is checked as
# https (by _url_problems), this host, and this path.
SNAPSHOT_HOST = "snapshot.debian.org"
SNAPSHOT_PATH_RE = re.compile(r"/file/([0-9a-f]{40})")


def _snapshot_sha1(url: Any) -> str | None:
    """The sha1 of a snapshot.debian.org /file/<sha1> URL, else None."""
    from urllib.parse import urlsplit
    if not isinstance(url, str):
        return None
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    m = SNAPSHOT_PATH_RE.fullmatch(u.path)
    if u.scheme != "https" or u.netloc != SNAPSHOT_HOST or u.query or u.fragment or not m:
        return None
    return m.group(1)
NEO4J_GROUPS = ("org.neo4j", "com.neo4j")


def _neo4j_group(group: str) -> bool:
    return group in NEO4J_GROUPS or group.startswith(tuple(g + "." for g in NEO4J_GROUPS))


def _image_versions(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """(the image's Neo4j version, its Temurin openjdk version) from its rows."""
    neo4j = openjdk = None
    for r in rows:
        m = PURL_RE.match(str(r.get("purl") or ""))
        if not m:
            continue
        if m.group("type") == "maven" and m.group("ns") == "org.neo4j" and m.group("name") == "neo4j":
            neo4j = unquote(m.group("version"))
        if m.group("type") == "generic" and m.group("ns") == "oracle" and m.group("name") == "openjdk":
            openjdk = unquote(m.group("version"))
    return neo4j, openjdk


def component_key(image: str, row: dict[str, Any], ctx: dict[str, Any]) -> tuple[str | None, str | None]:
    """N5 amendment, U7, item 2: the lock key for one `needs` row, read from
    its purl only; (None, problem) when it maps to no kind."""
    purl = row.get("purl")
    if not isinstance(purl, str) or not purl:
        return None, (f"{image}: {_clean(row.get('spdxid'))} {_clean(row.get('name'))} (no purl) needs source "
                      "and maps to no lock kind: back to the architect")
    m = PURL_RE.match(purl)
    unmapped = f"{image}: {_clean(purl)} needs source and maps to no lock kind: back to the architect"
    if not m:
        return None, unmapped
    ptype, ns, name = m.group("type"), unquote(m.group("ns") or ""), unquote(m.group("name"))
    ver = unquote(m.group("version"))
    q = _qualifiers(purl)
    if ptype == "deb" and ns == "debian":
        up = q.get("upstream", "")
        src, _, srcver = up.partition("@") if up else (name, "", ver)
        srcver = srcver or ver
        return (f"pgdg:{src}@{srcver}" if ".pgdg" in srcver else f"deb:{src}@{srcver}"), None
    if ptype == "apk" and ns == "alpine":
        origin = q.get("upstream", "").partition("@")[0] or name
        return f"apk:{origin}@{ver}", None
    if ptype == "generic" and ns == "oracle" and name == "openjdk":
        return f"temurin:jdk-{ver[:-len('-LTS')] if ver.endswith('-LTS') else ver}", None
    if ptype == "maven" and ns == "jrt-fs" and name == "jrt-fs":
        openjdk = ctx.get("openjdk")
        build = openjdk.split("+", 1)[0] if openjdk else None
        if build is None or ver != build:
            return None, f"{image}: jrt-fs {_clean(ver)} is not the image's Temurin build {_clean(openjdk)}"
        return f"temurin:jdk-{openjdk[:-len('-LTS')] if openjdk.endswith('-LTS') else openjdk}", None
    if ptype == "maven":
        if _neo4j_group(ns):
            if ctx.get("neo4j") is None:
                return None, (f"{image}: {_clean(purl)} is a Neo4j artifact but the image lists no "
                              "pkg:maven/org.neo4j/neo4j: back to the architect")
            if ver == ctx["neo4j"]:
                return f"neo4j:neo4j@{ver}", None
        return f"maven:{ns}:{name}@{ver}", None
    if ptype == "pypi":
        return f"pypi:{_norm(name)}@{ver}", None
    return None, unmapped


def lock_needs(policy: dict[str, Any], docs: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Which lock keys the bundled images need: per key its kind and the
    packages (image, purl, SPDXID) of every row `classify_document` marks
    `needs` (N5 amendment, U7, item 2); and the mapping problems."""
    always = policy.get("always") or []
    exempt = policy.get("exempt") or []
    needs: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for image in sorted(docs):
        rows = classify_document(image, docs[image], always, exempt)
        neo4j, openjdk = _image_versions(rows)
        ctx = {"neo4j": neo4j, "openjdk": openjdk}
        for row in rows:
            if not row["needs"]:
                continue
            key, problem = component_key(image, row, ctx)
            if problem:
                problems.append(problem)
                continue
            assert key is not None
            entry = needs.setdefault(key, {"kind": key.split(":", 1)[0], "packages": []})
            entry["packages"].append({"image": image, "purl": row.get("purl"), "spdxid": row.get("spdxid")})
    return needs, problems


def lock_text(lock: Any) -> str:
    """The lock's canonical text (N5 amendment, U7, item 6 (c))."""
    return json.dumps(lock, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def _key_parts(key: str) -> tuple[str, str]:
    """(name part, version) of `<kind>:<name>@<version>`."""
    body = key.split(":", 1)[1]
    name, _, ver = body.rpartition("@")
    return name, ver


# Rework round 1 (N5 amendment U7): every string field is printable ASCII
# 0x21-0x7e (upstream.from 0x20-0x7e), checked before any parsing.
PRINTABLE_RE = re.compile(r"[\x21-\x7e]+")
FROM_PRINTABLE_RE = re.compile(r"[\x20-\x7e]+")
MAX_FILE_SIZE = 4294967296  # 4 GiB (security U7a I-2)
ENTRY_KEYS = {"kind", "arches", "origin", "files"}
APK_KEYS = {"commit", "branch", "repo"}
FILE_KEYS = {"name", "url", "sha256", "size", "upstream"}
# U7d round 1, item 12: the SHA-256 and SHA-512 of the empty string.
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
EMPTY_SHA512 = ("cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
                "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e")
UPSTREAM_KEYS = {"alg", "value", "from"}
# Per-kind file hosts (N4; N10 am. U6 item 2); pgdg's from Q71 (U7d P5).
PGDG_HOST = "apt-archive.postgresql.org"
PGDG_SUITE_RE = re.compile(r"[a-z]+-pgdg-archive")
PGDG_SUITES = {12: "bookworm", 13: "trixie"}  # U7d P1: the purl distro major -> its codename


def pgdg_suite(distro: str) -> str | None:
    """U7d P1 / rework round 1 item 3: `debian-<major>[.<minor>]` -> the
    `<codename>-pgdg-archive` suite, or None."""
    m = re.fullmatch(r"debian-(\d+)(\.\d+)*", distro)
    code = PGDG_SUITES.get(int(m.group(1))) if m else None
    return f"{code}-pgdg-archive" if code else None


def _pgdg_key_suite(key: str, packages: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """The one suite every package of a pgdg key derives, or the problems."""
    problems, suites = [], set()
    for pkg in packages:
        distro = _qualifiers(str(pkg.get("purl"))).get("distro", "")
        suite = pgdg_suite(distro)
        if suite is None:
            problems.append(f"{_clean(key)}: {_clean(pkg['image'])}: no pgdg suite for distro {_clean(distro)}")
        else:
            suites.add(suite)
    if problems:
        return None, problems
    if len(suites) != 1:
        return None, [f"{_clean(key)}: packages derive suites {', '.join(sorted(suites))}"]
    return suites.pop(), []
# U9c (A81): the two hosts an apk file may have. The sample plan keeps only
# the files on the distfiles host (`fetch_plan`).
APK_API_HOST = "gitlab.alpinelinux.org"
APK_DISTFILES_HOST = "distfiles.alpinelinux.org"
KIND_HOSTS = {"deb": ("snapshot.debian.org",), "pgdg": (PGDG_HOST,), "apk": (APK_API_HOST, APK_DISTFILES_HOST),
              "neo4j": ("github.com",), "temurin": ("github.com",), "pypi": ("files.pythonhosted.org",),
              "maven": ("repo1.maven.org",)}
# Rework round 2 (security R1-L1): the sdist name is split at its last `-`
# (no nested quantifier), and the dist part checked by a linear pattern.
PYPI_DIST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
# Rework round 2, item 5: Warehouse's content-addressed file layout.
PYPI_PATH_RE = re.compile(r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/")


def _pypi_parts(name: str) -> tuple[str, str] | None:
    """(dist, version) of `<dist>-<version>.tar.gz`, else None."""
    if not name.endswith(".tar.gz"):
        return None
    dist, sep, ver = name[:-len(".tar.gz")].rpartition("-")
    if not sep or not ver or not PYPI_DIST_RE.fullmatch(dist):
        return None
    return dist, ver


def _str_problems(where: str, field: str, value: Any, *, space: bool = False) -> list[str]:
    if not isinstance(value, str):
        return [f"{where}: {field} is not a string"]
    if not (FROM_PRINTABLE_RE if space else PRINTABLE_RE).fullmatch(value):
        return [f"{where}: {field} is not printable ASCII ({'0x20' if space else '0x21'}-0x7e)"]
    return []


def _split(url: str) -> Any:
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url)
        u.port  # noqa: B018 - raises on a bad port
        return u
    except ValueError:
        return None


TEMURIN_TAG_SEGMENT = 5  # /adoptium/temurin<N>-binaries/releases/download/<tag>/<asset>


def _plain_path(path: str, url: str, kind: str | None) -> bool:
    """Rework round 2 (review R1-B1): a plain path. Segments are non-empty,
    none is `.` or `..`, no backslash anywhere in the url, and no `%` in the
    path but the literal `%2B` inside temurin's tag segment."""
    segs = path.split("/")
    if not path.startswith("/") or "\\" in url or any(seg == "" for seg in segs[1:]):
        return False
    if any(seg in (".", "..") for seg in segs):
        return False
    for i, seg in enumerate(segs):
        if "%" in seg and not (kind == "temurin" and i == TEMURIN_TAG_SEGMENT and "%" not in seg.replace("%2B", "")):
            return False
    return True


# U7c rework round 1, item 9: the one GitLab form an apk file may have (the
# API raw endpoint); its query and its %-encoded path segment are checked by
# the apk binding, never accepted anywhere else.
APK_API_PATH_RE = re.compile(r"/api/v4/projects/alpine%2Faports/repository/files/([^/?#]+)/raw")
APK_API_QUERY_RE = re.compile(r"ref=([^&#=]*)")


def _apk_api_shape(url: str) -> tuple[str, str] | None:
    """(<P>, <C>) when `url` has the item-9 shape, else None. Scheme, host,
    path and query are compared separately (PS-1.2: no URL literal)."""
    head, sep, query = url.partition("?")
    scheme, _, rest = head.partition("://")
    host, slash, path = rest.partition("/")
    m = APK_API_PATH_RE.fullmatch(slash + path)
    q = APK_API_QUERY_RE.fullmatch(query)
    if scheme != "https" or host != APK_API_HOST or not sep or not m or not q:
        return None
    return m.group(1), q.group(1)


def _url_problems(where: str, url: Any, hosts: set[str], kind: str | None = None) -> list[str]:
    from urllib.parse import urlunsplit
    p = _str_problems(where, "url", url)
    if p:
        return p
    u = _split(url)
    if u is None:
        return [f"{where}: url does not parse"]
    if urlunsplit(u) != url:
        p.append(f"{where}: url does not round-trip (urlunsplit(urlsplit(url)) differs)")
    if not url.startswith("https://"):
        p.append(f"{where}: url scheme is not https")
    if u.username is not None or u.password is not None or "@" in u.netloc:
        p.append(f"{where}: url carries userinfo")
    if u.port is not None or u.netloc.endswith(":"):
        p.append(f"{where}: url carries a port")
    api = kind == "apk" and _apk_api_shape(url) is not None
    if (u.query or "?" in url) and not api:
        p.append(f"{where}: url carries a query")
    if u.fragment or "#" in url:
        p.append(f"{where}: url carries a fragment")
    host = u.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    if host not in hosts:
        p.append(f"{where}: url host {_clean(host)} is not in docker/source-policy.json hosts")
    if not api and not _plain_path(u.path, url, kind):
        p.append(f"{where}: url path is not a plain path")
    return p


def _file_problems(where: str, f: Any, hosts: set[str], kind: str | None = None) -> list[str]:
    if not isinstance(f, dict):
        return [f"{where}: a file is not an object"]
    p = [f"{where}: a file has an unexpected key {_clean(k)}" for k in sorted(set(f) - FILE_KEYS, key=str)]
    p += [f"{where}: a file has no {k}" for k in sorted(FILE_KEYS - set(f))]
    if p:
        return p
    name = f["name"]
    p += _str_problems(where, "name", name)
    if not p and (not LOCK_FILE_NAME_RE.fullmatch(name) or ".." in name):
        p.append(f"{where}: {_clean(name)}: not a safe file name")
    p += _url_problems(where, f["url"], hosts, kind)
    p += _str_problems(where, "sha256", f["sha256"])
    if isinstance(f["sha256"], str) and not re.fullmatch(r"[0-9a-f]{64}", f["sha256"]):
        p.append(f"{where}: sha256 is not 64 lower-case hex")
    # U7d round 1, item 12: an apk file at the GitLab API raw form may be empty (its sha256 and the
    # files-API content_sha256 still bind it); every other file keeps 0 < size.
    low = 0 if kind == "apk" and isinstance(f["url"], str) and _apk_api_shape(f["url"]) is not None else 1
    if type(f["size"]) is not int or not low <= f["size"] <= MAX_FILE_SIZE:
        p.append(f"{where}: size {_clean(repr(f['size']))} is not an int in {low}..{MAX_FILE_SIZE}")
    elif f["size"] == 0:  # item 12, architect's precision: the empty hashes
        up0 = f["upstream"] if isinstance(f["upstream"], dict) else {}
        if name == "APKBUILD":  # review R1-N1: an empty APKBUILD has no pkgver
            p.append(f"{where}: APKBUILD: size 0")
        if f["sha256"] != EMPTY_SHA256:
            p.append(f"{where}: {_clean(name)}: size 0 but sha256 is not the empty hash")
        if up0.get("alg") == "sha512" and up0.get("value") != EMPTY_SHA512:
            p.append(f"{where}: {_clean(name)}: size 0 but sha512 is not the empty hash")
    up = f["upstream"]
    if not isinstance(up, dict):
        return p + [f"{where}: upstream is not an object"]
    p += [f"{where}: upstream has an unexpected key {_clean(k)}" for k in sorted(set(up) - UPSTREAM_KEYS, key=str)]
    p += [f"{where}: upstream has no {k}" for k in sorted(UPSTREAM_KEYS - set(up))]
    if set(up) != UPSTREAM_KEYS:
        return p
    q = _str_problems(where, "upstream.alg", up["alg"]) + _str_problems(where, "upstream.value", up["value"])
    q += _str_problems(where, "upstream.from", up["from"], space=True)
    p += q
    if q:
        return p
    if up["alg"] not in ALG_LEN:
        p.append(f"{where}: upstream alg {_clean(repr(up['alg']))} is not sha1, sha256 or sha512")
    elif len(up["value"]) != ALG_LEN[up["alg"]] or not HEX_RE.fullmatch(up["value"]):
        p.append(f"{where}: upstream value is not {ALG_LEN[up['alg']]} lower-case hex")
    elif up["alg"] == "sha256" and up["value"] != f["sha256"]:
        p.append(f"{where}: upstream sha256 differs from the file's sha256")
    if not up["from"].strip():
        p.append(f"{where}: upstream from is blank")
    return p


def _apk_api_problem(url: str, entry: dict[str, Any], origin: str, name: str) -> str | None:
    """Item 9 (a), (b), (d): why `url` is not this file's GitLab API raw url."""
    from urllib.parse import quote, unquote
    shape = _apk_api_shape(url)
    if shape is None:
        return "want .../repository/files/<repo>%2F<origin>%2F<name>/raw?ref=<commit>"
    seg, ref = shape
    if not re.fullmatch(r"[0-9a-f]{40}", ref) or ref != entry.get("commit"):
        return "the ref is not the entry's commit"
    decoded = unquote(seg)
    if quote(decoded, safe="") != seg:
        return "the path segment is not canonical (quote(unquote(P), safe='') != P)"
    if "%" in decoded or "\\" in decoded or not re.fullmatch(r"[\x21-\x7e]+", decoded):
        return "the decoded path holds %, a backslash or a non-printable character"
    parts = decoded.split("/")
    if (len(parts) < 3 or parts[0] != entry.get("repo") or parts[1] != origin or parts[-1] != name
            or any(x in ("", ".", "..") for x in parts)):
        return "the decoded path is not <repo>/<origin>(/<segment>)*/<name>"
    if not all(LOCK_FILE_NAME_RE.fullmatch(x) for x in parts[2:-1]):  # U7c review R1-N1
        return "a subdirectory segment fails the lock file-name rule"
    if name == "APKBUILD" and len(parts) != 3:
        return "the APKBUILD is not at <repo>/<origin>/APKBUILD"
    return None


def _binding_problems(where: str, key: str, kind: str, entry: dict[str, Any], f: dict[str, Any]) -> list[str]:
    """Rework round 1, item 3 (review N1, security L-2): the url host and path
    and the file name fit the entry's kind and key."""
    name, url = f.get("name"), f.get("url")
    if not isinstance(name, str) or not isinstance(url, str):
        return []
    if not LOCK_FILE_NAME_RE.fullmatch(name) or ".." in name:
        return []  # already "not a safe file name"; no regex on it (security R1-L1)
    u = _split(url)
    if u is None:
        return []
    host, path = u.netloc, u.path
    name_part, ver = _key_parts(key)
    if host not in KIND_HOSTS[kind]:
        return [f"{where}: {_clean(name)}: url host {_clean(host)} is not a {kind} file host"]
    if kind == "pgdg":  # U7d P5: exactly the pool url; + and ~ literal, no % escape
        p_ = name_part[:4] if name_part.startswith("lib") else name_part[:1]
        want_path = f"/pub/repos/apt/pool/main/{p_}/{name_part}/{name}"
        if path != want_path:
            return [f"{where}: {_clean(name)}: not a pgdg file url (want path {_clean(want_path)})"]
        return []
    if kind == "deb":
        if not SNAPSHOT_PATH_RE.fullmatch(path):
            return [f"{where}: {_clean(name)}: not a deb file url (snapshot.debian.org /file/<sha1>)"]
        return []
    p = []
    if path.rsplit("/", 1)[-1] != name and not (kind == "apk" and host == "gitlab.alpinelinux.org"):
        p.append(f"{where}: {_clean(name)}: url path does not end in /{_clean(name)}")
    if kind == "apk":
        if host == "gitlab.alpinelinux.org":
            # U7c rework round 1, item 9: exactly .../files/<P>/raw?ref=<commit>; the old /-/raw/ form is gone.
            why = _apk_api_problem(url, entry, name_part, name)
            if why:
                p.append(f"{where}: {_clean(name)}: not a apk file url ({why})")
            return p
        else:
            want = f"/distfiles/{entry.get('branch')}/{name}"
            if name == "APKBUILD":
                p.append(f"{where}: APKBUILD: not a apk file url (the APKBUILD comes from gitlab.alpinelinux.org)")
        if path != want:
            p.append(f"{where}: {_clean(name)}: not a apk file url (want path {_clean(want)})")
    elif kind == "neo4j":
        if path != f"/neo4j/neo4j/archive/refs/tags/{ver}.tar.gz" or name != f"{ver}.tar.gz":
            p.append(f"{where}: {_clean(name)}: not a neo4j file url (github.com/neo4j/neo4j/archive/refs/tags/{ver}.tar.gz)")
    elif kind == "temurin":
        # Rework round 2 (review R1-N1): the path and asset bound exactly to the
        # key `temurin:jdk-<ver>` (U7b confirms the real asset name).
        tver = key.split("jdk-", 1)[-1]
        feature = tver.split(".", 1)[0]
        asset = f"OpenJDK{feature}U-jdk-sources_{tver.replace('+', '_')}.tar.gz"
        want = f"/adoptium/temurin{feature}-binaries/releases/download/jdk-{tver.replace('+', '%2B')}/{asset}"
        if path != want or name != asset:
            p.append(f"{where}: {_clean(name)}: not a temurin file url (want path {_clean(want)})")
        up = f.get("upstream") if isinstance(f.get("upstream"), dict) else {}
        if up.get("from") != f"{asset}.sha256.txt":
            p.append(f"{where}: {_clean(name)}: temurin upstream from is not {_clean(asset)}.sha256.txt")
    elif kind == "pypi":
        if not PYPI_PATH_RE.fullmatch(path.rsplit("/", 1)[0] + "/") or path.rsplit("/", 1)[-1] != name:
            p.append(f"{where}: {_clean(name)}: not a pypi file url (/packages/<2 hex>/<2 hex>/<60 hex>/<name>)")
        parts = _pypi_parts(name)
        if parts is None or _norm(parts[0]) != name_part or parts[1] != ver:
            p.append(f"{where}: {_clean(name)}: not a pypi file of {_clean(name_part)} {_clean(ver)}")
    elif kind == "maven":
        g, _, a = name_part.partition(":")
        want = f"/maven2/{g.replace('.', '/')}/{a}/{ver}/{a}-{ver}-sources.jar"
        if path != want or name != f"{a}-{ver}-sources.jar":
            p.append(f"{where}: {_clean(name)}: not a maven file url (want path {_clean(want)})")
    return p


def _kind_problems(key: str, kind: str, entry: dict[str, Any], today: Any) -> list[str]:
    import datetime
    where = f"lock: {_clean(key)}"
    files = [f for f in entry["files"] if isinstance(f, dict)]
    names = [str(f.get("name")) for f in files]

    def alg(f: dict[str, Any]) -> Any:
        return f["upstream"].get("alg") if isinstance(f.get("upstream"), dict) else None
    p = []
    for f in files:
        p += _binding_problems(where, key, kind, entry, f)
    name_part, ver = _key_parts(key)
    if kind == "deb":
        dscs = [f for f in files if str(f.get("name")).endswith(".dsc")]
        if len(dscs) != 1:
            p.append(f"{where}: {len(dscs)} .dsc files, want exactly 1")
        else:
            dsc = dscs[0]
            want = f"{name_part}_{ver.split(':', 1)[1] if ':' in ver else ver}.dsc"
            if dsc.get("name") != want:
                p.append(f"{where}: the .dsc is {_clean(dsc.get('name'))}, want {_clean(want)}")
            up = dsc.get("upstream") if isinstance(dsc.get("upstream"), dict) else {}
            sha1 = _snapshot_sha1(dsc.get("url"))
            if up.get("alg") != "sha1" or sha1 is None or sha1 != up.get("value"):
                p.append(f"{where}: the .dsc is not sha1 with a {SNAPSHOT_HOST} /file/<that sha1> url")
            others = [f for f in files if f is not dsc]
            if not others:
                p.append(f"{where}: deb: no file besides the .dsc")
            for f in others:
                fup = f.get("upstream") if isinstance(f.get("upstream"), dict) else {}
                if (fup.get("alg") != "sha256" or fup.get("from") != f"{dsc.get('name')} Checksums-Sha256"
                        or _snapshot_sha1(f.get("url")) is None):
                    p.append(f"{where}: {_clean(f.get('name'))} is not sha256 from {_clean(dsc.get('name'))} "
                             "Checksums-Sha256 with a snapshot.debian.org/file/<sha1> url")
    elif kind == "pgdg":  # U7d P5
        suite = entry.get("suite")
        if not isinstance(suite, str) or not PGDG_SUITE_RE.fullmatch(suite):
            p.append(f"{where}: suite {_clean(repr(suite))} is missing or malformed")
        dscs = [f for f in files if str(f.get("name")).endswith(".dsc")]
        want = f"{name_part}_{ver.split(':', 1)[1] if ':' in ver else ver}.dsc"
        if len(dscs) != 1 or dscs[0].get("name") != want:
            p.append(f"{where}: pgdg: not exactly one .dsc named {_clean(want)}")
        if len(files) - len(dscs) < 1:
            p.append(f"{where}: pgdg: no file besides the .dsc")
        for f in files:
            fup = f.get("upstream") if isinstance(f.get("upstream"), dict) else {}
            frm = f"{PGDG_HOST} {suite} Sources" if f in dscs else f"{want} Checksums-Sha256"
            if fup.get("alg") != "sha256" or fup.get("from") != frm:
                p.append(f"{where}: {_clean(f.get('name'))} is not sha256 from {_clean(frm)}")
    elif kind == "apk":
        for field, rx in (("commit", r"[0-9a-f]{40}"), ("branch", r"v\d+\.\d+"), ("repo", r"main|community")):
            if not isinstance(entry.get(field), str) or not re.fullmatch(rx, entry[field]):
                p.append(f"{where}: {field} {_clean(repr(entry.get(field)))} is missing or malformed")
        apkbuilds = [f for f in files if f.get("name") == "APKBUILD"]
        if len(apkbuilds) != 1 or alg(apkbuilds[0]) != "sha256":
            p.append(f"{where}: not exactly one APKBUILD with sha256")
        gl_from = f"gitlab files API content_sha256 at {entry.get('commit')}"
        for f in apkbuilds[:1]:
            fup = f.get("upstream") if isinstance(f.get("upstream"), dict) else {}
            if fup.get("from") != gl_from:  # U7c gap rulings item 3: replaces A3's text
                p.append(f"{where}: the APKBUILD upstream from is not `gitlab files API content_sha256 at <commit>`")
        for f in files:
            fup = f.get("upstream") if isinstance(f.get("upstream"), dict) else {}
            fu = _split(f.get("url")) if isinstance(f.get("url"), str) else None
            on_gitlab = fu is not None and fu.netloc == "gitlab.alpinelinux.org"
            # U7c ruling 3: a package-directory file outside sha512sums is sha256 by the files API.
            if f.get("name") != "APKBUILD" and alg(f) != "sha512" and not (
                    alg(f) == "sha256" and fup.get("from") == gl_from and on_gitlab):
                p.append(f"{where}: {_clean(f.get('name'))} is not sha512 (APKBUILD sha512sums) or sha256 "
                         "(gitlab files API content_sha256)")
    elif kind == "maven":
        if len(files) != 1 or not names[0].endswith("-sources.jar") or alg(files[0]) != "sha1":
            p.append(f"{where}: not one -sources.jar with sha1")
    elif kind in ("temurin", "pypi"):
        if len(files) != 1 or alg(files[0]) != "sha256":
            p.append(f"{where}: not one file with sha256")
    elif kind == "neo4j":
        if len(entry["files"]) != 1:
            p.append(f"{where}: neo4j: not exactly one file")
        for f in files:
            fup = f.get("upstream") if isinstance(f.get("upstream"), dict) else {}
            if fup.get("alg") != "sha256":
                p.append(f"{where}: neo4j: upstream alg is not sha256")
            elif fup.get("value") != f.get("sha256"):
                p.append(f"{where}: neo4j: upstream value is not the file's sha256")
            m = NEO4J_FROM_RE.fullmatch(str(fup.get("from")))
            if not m:
                p.append(f"{where}: upstream from is not `second fetch: security YYYY-MM-DD, "
                         "docs/evidence/platform-sbom/sources-provenance.md`")
                continue
            try:
                when = datetime.date.fromisoformat(m.group(1))
            except ValueError:
                p.append(f"{where}: the second-fetch date {m.group(1)} is not a date")
                continue
            if when > today:
                p.append(f"{where}: the second-fetch date {m.group(1)} is after today (UTC)")
    return p


def _entry_problems(key: Any, entry: Any, hosts: set[str], today: Any) -> list[str]:
    p = _str_problems(f"lock: {_clean(key)}", "key", key)
    if p:
        return p
    if ":" not in key or key.split(":", 1)[0] not in LOCK_KEY_RES:
        return [f"lock: {_clean(key)}: not a lock key of a known kind"]
    kind = key.split(":", 1)[0]
    where = f"lock: {_clean(key)}"
    if not LOCK_KEY_RES[kind].fullmatch(key) or (kind in ("deb", "pgdg") and ((".pgdg" in key) != (kind == "pgdg"))):
        p.append(f"{where}: not a valid {kind} key")
    if not isinstance(entry, dict):
        return p + [f"{where}: the entry is not an object"]
    want = ENTRY_KEYS | (APK_KEYS if kind == "apk" else set()) | ({"suite"} if kind == "pgdg" else set())
    extra = [f"{where}: unexpected key {_clean(k)}" for k in sorted(set(entry) - want, key=str)]
    missing = [f"{where}: missing key {k}" for k in sorted(want - set(entry))]
    p += extra + missing
    for field in ("kind", "origin") + (tuple(sorted(APK_KEYS)) if kind == "apk" else ()) + (
            ("suite",) if kind == "pgdg" else ()):
        if field in entry:
            p += _str_problems(where, field, entry[field])
    if entry.get("kind") != kind:
        p.append(f"{where}: kind {_clean(repr(entry.get('kind')))} is not {kind}")
    arches = entry.get("arches")
    if not isinstance(arches, list) or not all(isinstance(a, str) for a in arches):
        p.append(f"{where}: arches is not a list of strings")
    else:
        for a in arches:
            p += _str_problems(where, "arches item", a)
        if not arches or arches != sorted(set(arches)) or not set(arches) <= set(LOCK_ARCHES):
            p.append(f"{where}: arches {_clean(repr(arches))} is not a sorted, unique, non-empty subset "
                     f"of {list(LOCK_ARCHES)}")
    origin = entry.get("origin")
    if origin != ("manual" if kind == "neo4j" else "generated"):
        p.append(f"{where}: origin {_clean(repr(origin))}; neo4j is manual, every other kind generated")
    files = entry.get("files")
    if not isinstance(files, list):
        return p + [f"{where}: files is not a list"]
    if not files:
        return p + [f"{where}: no files"]
    seen = set()
    for f in files:
        p += _file_problems(where, f, hosts, kind)
        n = f.get("name") if isinstance(f, dict) else None
        if isinstance(n, str):
            if n in seen:
                p.append(f"{where}: {_clean(n)} is listed twice")
            seen.add(n)
    if not missing:
        p += _kind_problems(key, kind, entry, today)
    return p


def _entry_stage(lock: Any, policy: dict[str, Any], today: Any) -> tuple[list[str], dict[str, Any] | None]:
    """The lock's own rules, before any SBOM is read: canonical text, the
    top-level keys, `format` and every entry (`_entry_problems`). The second
    value is the components object, or None when the text stopped the checks."""
    import datetime
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    if not isinstance(lock, str):
        return ["lock: the lock is not text"], None
    try:
        data = json.loads(lock)
    except (ValueError, RecursionError) as exc:
        return [f"lock: not JSON: {_clean(exc)}"], None
    p = []
    try:
        if lock != lock_text(data):
            p.append("lock: not in canonical form: regenerate")
    except (ValueError, RecursionError):
        p.append("lock: not in canonical form: regenerate")
    if not isinstance(data, dict) or set(data) != {"format", "components"}:
        return p + ["lock: top-level keys are not exactly format and components"], None
    if data["format"] != 1 or type(data["format"]) is not int:
        p.append(f"lock: format {_clean(repr(data['format']))} is not 1")
    comps = data["components"]
    if not isinstance(comps, dict):
        return p + ["lock: components is not an object"], None
    hosts = {h for h in policy.get("hosts") or [] if isinstance(h, str)}
    for key, entry in sorted(comps.items()):
        p += _entry_problems(key, entry, hosts, today)
    return p + _shared_sha256_problems(comps), comps


def _shared_sha256_problems(comps: dict[str, Any]) -> list[str]:
    """U8 (security M-2): one sha256 carries one size, one upstream alg and
    one upstream value across every entry and arch, so a file the fetch holds
    once stands for the same size and digests wherever the lock lists it. The
    reference is the first entry in lock order holding that sha256 (for a
    digest, the first holding it under that alg). Malformed rows are left to
    `_entry_problems`."""
    p: list[str] = []
    sizes: dict[str, tuple[int, str]] = {}
    algs: dict[str, tuple[str, str]] = {}
    values: dict[tuple[str, str], tuple[str, str]] = {}
    for key, entry in sorted(comps.items()):
        files = entry.get("files") if isinstance(entry, dict) else None
        for f in files if isinstance(files, list) else []:
            up = f.get("upstream") if isinstance(f, dict) else None
            if not (isinstance(up, dict) and isinstance(f.get("sha256"), str) and type(f.get("size")) is int
                    and isinstance(f.get("name"), str) and isinstance(up.get("alg"), str)
                    and isinstance(up.get("value"), str)):
                continue
            sha, size = f["sha256"], f["size"]
            where = f"lock: {_clean(key)}: {_clean(f['name'])}: sha256 {_clean(sha)}"
            first = sizes.setdefault(sha, (size, key))
            if first[0] != size:
                p.append(f"{where} is size {size} here but {first[0]} in {_clean(first[1])}")
            alg0, key0 = algs.setdefault(sha, (up["alg"], key))
            if alg0 != up["alg"] and size > 0:  # an empty file is one content under any alg (U7d size-0 rule)
                p.append(f"{where} has upstream alg {_clean(up['alg'])} here but {_clean(alg0)} in {_clean(key0)}")
                continue
            if alg0 != up["alg"]:
                continue
            ref = values.setdefault((sha, up["alg"]), (up["value"], key))
            if ref[0] != up["value"]:
                p.append(f"{where} has {_clean(up['alg'])} {_clean(up['value'])} here but {_clean(ref[0])} in {_clean(ref[1])}")
    return p


def lock_entry_problems(lock: Any, policy: dict[str, Any], today: Any = None) -> list[str]:
    """`lock_problems` without the SBOM half (U8, design item 1): the lock's
    text and every entry's rules, no coverage and no pgdg suite binding. The
    fetch client runs it before any request."""
    return _entry_stage(lock, policy, today)[0]


def lock_problems(lock: Any, policy: dict[str, Any], docs: dict[str, Any], arch: str,
                  today: Any = None) -> list[str]:
    """The lock's text checked: schema, canonical form, every URL host in
    the policy `hosts` and in its kind's hosts, per-kind file rules, and
    coverage both ways for `arch` against what `docs` need (N5 amendment,
    U7, items 2, 4, 6 and rework round 1). Wrong types are problems, never
    exceptions."""
    if arch not in LOCK_ARCHES:
        return [f"lock: arch {_clean(repr(arch))} is not amd64 or arm64"]
    p, comps = _entry_stage(lock, policy, today)
    if comps is None:
        return p
    needs, mapping = lock_needs(policy, docs)
    p += mapping
    for key in sorted(k for k in comps if isinstance(k, str) and k.startswith("pgdg:") and k in needs):
        # U7d rework round 1, item 3 (review N1, security I-2): the suite is bound to the image.
        e = comps[key]
        suite, why = _pgdg_key_suite(key, needs[key]["packages"])
        p += why
        if suite is not None and isinstance(e, dict) and e.get("suite") != suite:
            pkg = needs[key]["packages"][0]
            p.append(f"lock: {_clean(key)}: suite {_clean(e.get('suite'))} is not {suite} (from {_clean(pkg['image'])} "
                     f"distro {_clean(_qualifiers(str(pkg.get('purl'))).get('distro', ''))})")
    covered = {k for k, e in comps.items() if isinstance(e, dict) and isinstance(e.get("arches"), list)
               and arch in e["arches"]}
    p += [line for _, line in _coverage_misses(needs, covered, arch)]
    for key in sorted(covered - set(needs)):
        p.append(f"lock: {_clean(key)} is listed for {arch} but no image needs it: "
                 f"run scripts/sources_lock.sh --arch {arch}")
    return p


def _coverage_misses(needs: dict[str, Any], covered: set[str], arch: str) -> list[tuple[str, str]]:
    out = []
    for key in sorted(needs):
        if key not in covered:
            for pkg in needs[key]["packages"]:
                out.append((key, f"{pkg['image']}: {_clean(pkg['purl'])} needs source; the lock has no {_clean(key)} "
                                 f"for {arch}: run scripts/sources_lock.sh --arch {arch}"))
    return out


def only_neo4j_misses(problems: list[str], text: str, policy: dict[str, Any], docs: dict[str, Any],
                      arch: str) -> bool:
    """U7b rework round 1, item 2: True exactly when the full list is
    non-empty and every problem is a coverage miss for a `neo4j:` key."""
    if not problems:
        return False
    comps = json.loads(text).get("components")
    covered = {k for k, e in comps.items() if isinstance(e, dict) and isinstance(e.get("arches"), list)
               and arch in e["arches"]}
    needs, _ = lock_needs(policy, docs)
    neo = {line for key, line in _coverage_misses(needs, covered, arch) if key.startswith("neo4j:")}
    return all(x in neo for x in problems)


def sample_keys(lock: dict[str, Any], arch: str) -> list[str]:
    """Q63 sample: per kind present for `arch`, the entry with the smallest
    total size, ties broken by key (N5; amendment U7, item 5). The sample of
    an `apk` key is its distfiles files only (A81, `fetch_plan`). Call it only
    on a lock `lock_problems` passed (security U7a I-4)."""
    best: dict[str, tuple[int, str]] = {}
    for key, entry in (lock.get("components") or {}).items():
        if not isinstance(entry, dict) or arch not in (entry.get("arches") or []):
            continue
        total = sum(f.get("size", 0) for f in entry.get("files") or [] if isinstance(f, dict))
        kind = key.split(":", 1)[0]
        if kind not in best or (total, key) < best[kind]:
            best[kind] = (total, key)
    return sorted(k for _, k in best.values())


def fetch_plan(lock: dict[str, Any], arch: str, which: str) -> list[tuple[str, dict[str, Any]]]:
    """U8: the (key, file) pairs the fetch client requests, sorted by key then
    the entry's file order. `sample` is `sample_keys`; `full` is every key
    listed for `arch`; any other set is a ValueError. A81: in `sample`, an
    `apk` key keeps only the files whose URL host is `APK_DISTFILES_HOST`
    (file order), and a ValueError names the key when none is left. Call it
    only on a lock `lock_entry_problems` passed."""
    if which not in ("sample", "full"):
        raise ValueError(f"set {which!r} is not sample or full")
    comps = lock.get("components") or {}
    keys = sample_keys(lock, arch) if which == "sample" else sorted(
        k for k, e in comps.items() if arch in (e.get("arches") or []))
    plan = []
    for k in keys:
        files = comps[k]["files"]
        if which == "sample" and k.split(":", 1)[0] == "apk":
            files = [f for f in files if _split(f["url"]).hostname == APK_DISTFILES_HOST]
            if not files:
                raise ValueError(f"{_clean(k)}: the apk sample key has no file on {APK_DISTFILES_HOST}; "
                                 "the sample needs one (A81)")
        plan.extend((k, f) for f in files)
    return plan


def lock_check(a: argparse.Namespace) -> int:
    if a.arch not in LOCK_ARCHES:
        print(f"sbom_check: lock-check: --arch {a.arch!r} is not amd64 or arm64", file=sys.stderr)
        return 2
    docs = {}
    for spec in a.sbom:
        image, sep, path = spec.partition("=")
        if not sep or not NAME_RE.fullmatch(image) or not path:
            print(f"sbom_check: lock-check: --sbom {spec!r} is not IMAGE=PATH", file=sys.stderr)
            return 2
        docs[image] = path
    try:
        with open(a.lock, encoding="utf-8", newline="") as fh:
            text = fh.read()
        json.loads(text)  # read errors and deep nesting are a FAIL line here (rework round 2, item 3)
        with open(a.policy, encoding="utf-8") as fh:
            policy = json.load(fh)
        for image, path in list(docs.items()):
            with open(path, encoding="utf-8") as fh:
                docs[image] = json.load(fh)
    except (OSError, ValueError, RecursionError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        print(f"lock-check: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)
        return 1
    try:
        problems = lock_problems(text, policy, docs, a.arch)
    except Exception as exc:  # noqa: BLE001 - fail closed with one message, never a traceback (rework r1, N5)
        print(f"lock-check: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)
        return 1
    try:
        pending = bool(a.pending_neo4j) and only_neo4j_misses(problems, text, policy, docs, a.arch)
    except Exception as exc:  # noqa: BLE001 - fail closed
        print(f"lock-check: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)
        return 1
    if problems:
        for line in problems[:20]:
            print(f"sbom_check: lock-check: {line}", file=sys.stderr)
        return 3 if pending else 1
    print(f"lock-check: ok ({len(json.loads(text)['components'])} components, {a.arch})")
    return 0


# --- PSC-15: lock-needs, the resolver's input (U7b; N5 amendment U7, item 3.3) --

TEMURIN_RELEASE = "opt/java/openjdk/release"


class TarMemberTooLarge(ValueError):
    """A tar member over its read limit: a failure, never a truncation (U7c A1)."""


def tar_file_text(tar_path: str, member: str, limit: int = 1 << 20) -> str | None:
    """The text of `member` in a `docker save` tar, the top layer's copy
    winning; None when no layer holds it. Read only, never extracted. A
    member larger than `limit` raises TarMemberTooLarge (U7c A1)."""
    found: bytes | None = None
    with tarfile.open(tar_path) as tar:
        m = tar.extractfile("manifest.json")
        if m is None:
            raise ValueError("manifest.json is not a file in the tar")
        manifest = json.load(m)
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise ValueError("the tar's manifest.json does not hold exactly one image")
        for name in manifest[0].get("Layers") or []:
            blob = tar.extractfile(str(name))
            if blob is None:
                raise ValueError(f"layer {_clean(name)} is not a file in the tar")
            with tarfile.open(fileobj=blob, mode="r:*") as layer:
                for item in layer:
                    if _rel(item.name) == member and item.isfile():
                        if item.size > limit:
                            raise TarMemberTooLarge(f"/{member} larger than {limit // (1 << 20)} MiB")
                        data = layer.extractfile(item)
                        found = data.read(limit + 1) if data is not None else None
                        if found is not None and len(found) > limit:
                            raise TarMemberTooLarge(f"/{member} larger than {limit // (1 << 20)} MiB")
    return None if found is None else found.decode("utf-8", errors="replace")


APK_DB = "lib/apk/db/installed"
ALPINE_RELEASE = "etc/alpine-release"


def apk_stanzas(db_text: str) -> list[dict[str, str]]:
    """`lib/apk/db/installed`: stanzas split on blank lines, `X:value` fields
    (the first of each letter kept)."""
    out = []
    for block in re.split(r"\n\s*\n", db_text):
        st: dict[str, str] = {}
        for line in block.splitlines():
            if len(line) >= 2 and line[1] == ":":
                st.setdefault(line[0], line[2:])
        if st:
            out.append(st)
    return out


def _apk_route(key: str, origin: str, ver: str, packages: list[dict[str, Any]],
               apk: dict[str, dict[str, str]]) -> tuple[dict[str, Any] | None, list[str]]:
    """U7c A1: {origin, ver, commit, branch} from each image's installed db
    and alpine-release."""
    problems, commits, branches = [], set(), set()
    for pkg in packages:
        image = pkg["image"]
        m = PURL_RE.match(str(pkg.get("purl") or ""))
        name = unquote(m.group("name")) if m else ""
        pver = unquote(m.group("version")) if m else ""
        db = (apk.get(image) or {}).get("installed") or ""
        hits = [st for st in apk_stanzas(db) if st.get("P") == name and st.get("V") == pver
                and st.get("o") == origin and re.fullmatch(r"[0-9a-f]{40}", st.get("c", ""))]
        if not hits:
            problems.append(f"{_clean(key)}: {_clean(image)}: {_clean(name)} {_clean(pver)} has no installed-db stanza "
                            f"with origin {_clean(origin)} and an aports commit")
            continue
        commits.add(hits[0]["c"])
        release = ((apk.get(image) or {}).get("release") or "").strip()
        distro = _qualifiers(str(pkg.get("purl"))).get("distro", "")
        rm = re.fullmatch(r"(\d+)\.(\d+)\.\d+", release)
        if not rm or distro != f"alpine-{release}":
            problems.append(f"{_clean(key)}: {_clean(image)}: alpine-release {_clean(release or '(none)')}, "
                            f"purl distro {_clean(distro or '(none)')}")
            continue
        branches.add(f"v{rm.group(1)}.{rm.group(2)}")
    if len(commits) > 1:
        a, b = sorted(commits)[:2]
        problems.append(f"{_clean(key)}: two aports commits {a}, {b}")
    if len(branches) > 1:
        problems.append(f"{_clean(key)}: two Alpine branches {', '.join(sorted(branches))}")
    if problems or not commits or not branches:
        return None, problems
    return {"origin": origin, "ver": ver, "commit": commits.pop(), "branch": branches.pop()}, []


def lock_needs_doc(policy: dict[str, Any], docs: dict[str, Any], releases: dict[str, str],
                   apk: dict[str, dict[str, str]] | None = None) -> tuple[dict[str, Any], list[str]]:
    """needs.json: per key its kind, packages and route inputs (item 3.3):
    deb/pgdg {src, ver}; apk {origin, ver, commit, branch} (U7c A1: `apk` maps
    an image to {"installed": <lib/apk/db/installed text>, "release":
    <etc/alpine-release text>}); neo4j {ver}; temurin {sbom_version, release}
    (the release file text of the image's tar); pypi {name, ver}; maven
    {g, a, v}."""
    needs, problems = lock_needs(policy, docs)
    out: dict[str, Any] = {}
    for key, entry in sorted(needs.items()):
        kind = entry["kind"]
        name, ver = _key_parts(key)
        route: dict[str, Any]
        if kind == "deb":
            route = {"src": name, "ver": ver}
        elif kind == "pgdg":  # U7d P1: the suite from the purls' distro major (shared, round 1 item 3)
            suite, why = _pgdg_key_suite(key, entry["packages"])
            problems += why
            if suite is None:
                continue
            route = {"src": name, "ver": ver, "suite": suite}
        elif kind == "apk":
            apk_route, why = _apk_route(key, name, ver, entry["packages"], apk or {})
            problems += why
            if apk_route is None:
                continue
            route = apk_route
        elif kind == "neo4j":
            route = {"ver": ver}
        elif kind == "pypi":
            route = {"name": name, "ver": ver}
        elif kind == "maven":
            g, _, a = name.partition(":")
            route = {"g": g, "a": a, "v": ver}
        else:  # temurin
            jdk = [p for p in entry["packages"] if str(p.get("purl") or "").startswith("pkg:generic/oracle/openjdk@")]
            if not jdk:
                problems.append(f"{_clean(key)}: no pkg:generic/oracle/openjdk package")
                continue
            m = PURL_RE.match(str(jdk[0]["purl"]))
            image = jdk[0]["image"]
            release = releases.get(image)
            if release is None:
                problems.append(f"{_clean(key)}: {image}: no /{TEMURIN_RELEASE} (pass --tar {image}=<saved tar>)")
                continue
            route = {"sbom_version": unquote(m.group("version")) if m else "", "release": release}
        out[key] = {"kind": kind, "packages": entry["packages"], "route": route}
    return {"format": 1, "needs": out}, problems


def lock_needs_cli(a: argparse.Namespace) -> int:
    docs: dict[str, Any] = {}
    tars: dict[str, str] = {}
    for opt, specs, into in (("--sbom", a.sbom, docs), ("--tar", a.tar or [], tars)):
        for spec in specs:
            image, sep, path = spec.partition("=")
            if not sep or not NAME_RE.fullmatch(image) or not path:
                print(f"lock-needs: {opt} {spec!r} is not IMAGE=PATH", file=sys.stderr)
                return 2
            into[image] = path
    try:
        with open(a.policy, encoding="utf-8") as fh:
            policy = json.load(fh)
        for image, path in list(docs.items()):
            with open(path, encoding="utf-8") as fh:
                docs[image] = json.load(fh)
        # U7c A1: a tar is read only for the kinds its image needs.
        wanted: dict[str, set[str]] = {}
        for entry in lock_needs(policy, docs)[0].values():
            for pkg in entry["packages"]:
                wanted.setdefault(pkg["image"], set()).add(entry["kind"])
        releases: dict[str, str] = {}
        apk: dict[str, dict[str, str]] = {}
        too_large = []
        for image, path in tars.items():
            kinds = wanted.get(image, set())
            try:
                if "temurin" in kinds:
                    body = tar_file_text(path, TEMURIN_RELEASE)
                    if body is not None:
                        releases[image] = body
                if "apk" in kinds:
                    apk[image] = {"installed": tar_file_text(path, APK_DB, 16 << 20) or "",
                                  "release": tar_file_text(path, ALPINE_RELEASE) or ""}
            except TarMemberTooLarge as exc:
                too_large.append(f"{_clean(image)}: {exc}")
        doc, problems = lock_needs_doc(policy, docs, releases, apk)
        problems = too_large + problems
    except Exception as exc:  # noqa: BLE001 - one FAIL line, never a traceback (as lock-check)
        print(f"lock-needs: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)
        return 1
    if problems:
        for line in problems[:20]:
            print(f"sbom_check: lock-needs: {line}", file=sys.stderr)
        return 1
    print(lock_text(doc), end="")
    return 0


# --- PSC-15, PSC-24: the source set, the index and the notices (U9a) ---------
# Design-notes "N9 amendment, U9" items 1, 3, 5, 6, 7. Pure functions; the
# CLI wrappers below do the reads and the directory listing.

SHA64_RE = re.compile(r"[0-9a-f]{64}")
RECORD_KEYS = {"format", "set", "arch", "lock_sha256", "components"}
RECORD_FILE_KEYS = ("name", "sha256", "size")
RECORD_MAX = 4 * 1024 * 1024
UNSAFE_CELL_RE = re.compile(r"[|`<>\\]")
MARKDOWN_RE = re.compile(r"[\[\]()!*_#]")
INDEX_MAX = 16 * 1024 * 1024
HASH_CHUNK = 1 << 20


def _show(value: Any) -> str:
    return _clean(value)[:120]


def _lock_sha256(lock_src: str) -> str:
    return hashlib.sha256(lock_src.encode("utf-8")).hexdigest()


def fetch_record_problems(record_text: str, lock_src: str, policy: dict[str, Any], arch: str,
                          which: str) -> list[str]:
    """Item 3 a-d, in order; the first failing stage stops the run. `a`: the
    record's text (canonical, exactly these keys, format 1); `b`: it matches
    this bundle (set, arch, the lock's sha256); `c`: the lock passes
    `lock_entry_problems`; `d`: components equal `fetch_plan` grouped by key."""
    if not isinstance(policy, dict):
        return ["policy: not a JSON object"]
    try:
        rec = json.loads(record_text)
    except (ValueError, RecursionError):
        return ["fetch.json: not valid JSON"]
    if not isinstance(rec, dict):
        return ["fetch.json: not a JSON object"]
    try:
        canonical = lock_text(rec) == record_text
    except RecursionError:
        return ["fetch.json: nested too deeply to check"]
    if not canonical:
        return ["fetch.json: not in the canonical form (the fetch client's own text)"]
    if set(rec) != RECORD_KEYS:
        missing, extra = sorted(RECORD_KEYS - set(rec)), sorted(set(rec) - RECORD_KEYS)
        return [f"fetch.json: key {_show(k)} is missing" for k in missing] + [
            f"fetch.json: key {_show(k)} is not allowed" for k in extra]
    if type(rec["format"]) is not int or rec["format"] != 1:
        return [f"fetch.json: format is {_show(rec['format'])}, want 1"]
    p = []
    if rec["set"] != which:
        p.append(f"fetch.json: set is {_show(rec['set'])}, this bundle needs {which}")
    if rec["arch"] != arch:
        p.append(f"fetch.json: arch is {_show(rec['arch'])}, this bundle is {arch}")
    want_sha = _lock_sha256(lock_src)
    if rec["lock_sha256"] != want_sha:
        p.append(f"fetch.json: lock_sha256 {_show(rec['lock_sha256'])} is not the lock's {want_sha}: "
                 "fetch again after the re-lock")
    if p:
        return p
    entry_problems = lock_entry_problems(lock_src, policy)
    if entry_problems:
        return [entry_problems[0]]
    plan = fetch_plan(json.loads(lock_src), arch, which)
    expected: dict[str, list[dict[str, Any]]] = {}
    for key, f in plan:
        expected.setdefault(key, []).append({k: f[k] for k in RECORD_FILE_KEYS})
    comps = rec["components"]
    if not isinstance(comps, dict):
        return ["fetch.json: components is not an object"]
    for key in sorted(set(expected) - set(comps)):
        return [f"fetch.json: {_show(key)}: missing, the lock's {which} plan has it"]
    for key in sorted(set(comps) - set(expected)):
        return [f"fetch.json: {_show(key)}: not in the lock's {which} plan"]
    for key in sorted(expected):
        got, want = comps[key], expected[key]
        if not isinstance(got, list):
            return [f"fetch.json: {_show(key)}: files is not a list"]
        if len(got) != len(want):
            return [f"fetch.json: {_show(key)}: lists {len(got)} files, the lock's {which} plan says {len(want)}"]
        for g, w in zip(got, want):
            if not isinstance(g, dict) or set(g) != set(RECORD_FILE_KEYS):
                return [f"fetch.json: {_show(key)}: a file is not an object with exactly name, sha256 and size"]
            for field in RECORD_FILE_KEYS:
                if type(g[field]) is not type(w[field]) or g[field] != w[field]:
                    return [f"fetch.json: {_show(key)}: {field} is {_show(g[field])}, the lock's {which} plan says "
                            f"{_show(w[field])}"]
    return []


def _planned(plan: list[tuple[str, dict[str, Any]]]) -> dict[str, tuple[str, dict[str, Any]]]:
    """The distinct planned sha256 values, each with its first (key, file)."""
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for key, f in plan:
        out.setdefault(f["sha256"], (key, f))
    return out


def listing_problems(listing: Any, plan: list[tuple[str, dict[str, Any]]], record: bool,
                     where: str = ".") -> list[str]:
    """Item 3 e and item 5 stage 5: `listing` is `{name: (kind, size)}` (kind
    file, link, dir or other, from `lstat`); it must hold exactly one regular
    file per distinct planned sha256 at the lock's size, plus `fetch.json`
    when `record`. An OSError while the listing is read is one problem."""
    try:
        entries = dict(listing)
    except OSError:
        return [f"{_clean(where)}: cannot list"]
    planned = _planned(plan)
    p: list[str] = []
    for name in sorted(entries):
        kind = entries[name][0]
        shown = _clean(name)
        if name == "fetch.json":
            if not record:
                p.append("fetch.json: not part of the shipped source files")
            elif kind != "file":
                p.append(f"fetch.json: is not a regular file ({kind})")
            continue
        if not SHA64_RE.fullmatch(name):
            p.append(f"{shown}: not a planned source file (a name is 64 lower-case hex digits)")
        elif name not in planned:
            p.append(f"{shown}: not in the lock's plan")
        elif kind == "link":
            p.append(f"{shown}: is a link, not a regular file")
        elif kind != "file":
            p.append(f"{shown}: is not a regular file ({kind})")
    if record and "fetch.json" not in entries:
        p.append("fetch.json: missing; run scripts/bundle_fetch.sh first")
    for sha, (key, f) in sorted(planned.items()):
        label = f"{sha} ({_clean(key)} {_clean(f['name'])})"
        if sha not in entries:
            p.append(f"{label}: missing")
        elif entries[sha][0] == "file" and entries[sha][1] != f["size"]:
            p.append(f"{label}: size is {entries[sha][1]}, the lock's is {f['size']}")
    return p


def _licence_raw(pkg: dict[str, Any], field: str) -> Any:
    value = pkg.get(field)
    return value if isinstance(value, str) else None


def _policy_shape_problems(policy: Any) -> list[str]:
    if not isinstance(policy, dict):
        return ["policy: not a JSON object"]
    p = []
    for field in ("always", "exempt"):
        rows = policy.get(field)
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            p.append(f"policy: {field} is not a list of objects")
    if not p:
        for e in policy["exempt"]:
            if not all(isinstance(e.get(k), str) for k in ("image", "package", "reason", "reviewed")):
                p.append("policy: an exempt entry lacks a string image, package, reason or reviewed")
                break
    return p


def source_index(docs: dict[str, Any], lock_src: str, policy: dict[str, Any], arch: str, which: str,
                 git_sha: str, listing: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Item 5: (index, []) or (None, problems), stopping at the first failing
    stage: read, `validate` of every SBOM, `lock_problems` both ways,
    `always`/`exempt` problems, the copied listing, then the build."""
    try:
        return _source_index(docs, lock_src, policy, arch, which, git_sha, listing)
    except Exception as exc:  # noqa: BLE001 - fail closed: a problem, never an exception
        return None, [f"index: {type(exc).__name__}: {_clean(exc)}"]


def _source_index(docs: dict[str, Any], lock_src: str, policy: dict[str, Any], arch: str, which: str,
                  git_sha: str, listing: Any) -> tuple[dict[str, Any] | None, list[str]]:
    if arch not in LOCK_ARCHES or which not in ("full", "sample"):
        return None, [f"index: arch {_show(arch)} or set {_show(which)} is not valid"]
    if not isinstance(git_sha, str) or not SHA_RE.fullmatch(git_sha):
        return None, [f"index: git sha {_show(git_sha)} is not 40 lower-case hex digits"]
    try:
        lock = json.loads(lock_src)
    except (ValueError, RecursionError):
        return None, ["index: the lock is not valid JSON"]
    bad = _policy_shape_problems(policy)
    if bad or not isinstance(docs, dict) or not isinstance(lock, dict):
        return None, bad or ["index: the lock or the SBOMs are not objects"]
    p = [f"{_clean(image)}: {line}" for image in sorted(docs) for line in validate(docs[image])]
    if p:
        return None, p
    p = lock_problems(lock_src, policy, docs, arch)
    if p:
        return None, p
    always, exempt = policy["always"], policy["exempt"]
    for image in sorted(docs):
        p += always_matches(image, docs[image], always)[1] + exempt_matches(image, docs[image], exempt)[1]
    if p:
        return None, p
    plan = fetch_plan(lock, arch, which)
    p = listing_problems(listing, plan, False, "--files")
    if p:
        return None, p
    planned = {(k, f["name"]) for k, f in plan}
    needs, _ = lock_needs(policy, docs)
    rows: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    ordered: dict[str, list[dict[str, Any]]] = {}
    for image in sorted(docs):
        pkgs = {str(pk.get("SPDXID")): pk for pk in _packages(docs[image])}
        ordered[image] = classify_document(image, docs[image], always, exempt)
        for row in ordered[image]:
            rows[(image, str(row["spdxid"]))] = (row, pkgs[str(row["spdxid"])])

    def package(image: str, spdxid: Any) -> dict[str, Any]:
        row, pkg = rows[(image, str(spdxid))]
        return {"image": image, "spdxid": row["spdxid"], "purl": row["purl"], "name": row["name"],
                "always": row["always"], "expression": row["expression"],
                "licence": {"declared": _licence_raw(pkg, "licenseDeclared"),
                            "concluded": _licence_raw(pkg, "licenseConcluded")}}

    components: list[dict[str, Any]] = []
    for key in sorted(needs):
        entry = lock["components"][key]
        kind = key.split(":", 1)[0]
        fetched = [(key, f["name"]) in planned for f in entry["files"]]
        status = "shipped" if fetched and all(fetched) else "partial" if any(fetched) else "not-shipped"
        if which == "full" and status == "not-shipped":
            p.append(f"index: {_clean(key)} is not shipped in a full bundle")
        elif which == "full" and status == "partial":
            p.append(f"index: {_clean(key)} is partial in a full bundle")
        elif status == "partial" and kind != "apk":
            p.append(f"index: {_clean(key)} is partial, and only the apk sample key may be (A81)")
        files = [dict(f, path=f"sources/files/{f['sha256']}" if got else None)
                 for f, got in zip(entry["files"], fetched)]
        components.append({"key": key, "kind": kind,
                           "status": status,
                           "packages": [package(pk["image"], pk["spdxid"]) for pk in needs[key]["packages"]],
                           "files": files})
    if p:
        return None, p
    exempt_components = []
    for image in sorted(docs):
        for row in ordered[image]:
            if not row["exempt"]:
                continue
            entry = next(e for e in exempt if e["image"] == image and e["package"] == _purl_base(row["purl"] or ""))
            how = "always, cleared by exemption" if row["always"] else "exempt, reviewed"
            exempt_components.append({
                "key": None, "kind": None, "status": "exempt", "files": [],
                "packages": [package(image, row["spdxid"])],
                "exempt": {"image": image, "package": entry["package"], "reason": entry["reason"],
                           "reviewed": entry["reviewed"]},
                "listing": f"{how} {entry['reviewed']}"})
    exempt_components.sort(key=lambda c: (c["exempt"]["image"], c["exempt"]["package"]))
    flagged = {field: [{"image": image, "spdxid": r["spdxid"], "purl": r["purl"], "name": r["name"],
                        "needs": r["needs"]} for image in sorted(docs) for r in ordered[image] if r[field]]
               for field in ("unparsed", "unidentified")}
    return {"format": 1, "set": which, "arch": arch, "git_sha": git_sha,
            "lock_sha256": _lock_sha256(lock_src),
            "components": components + exempt_components, "unparsed": flagged["unparsed"],
            "unidentified": flagged["unidentified"],
            "unlicensed": {image: unlicensed_report(docs[image]) for image in sorted(docs)}}, []


def _cell_problem(what: str, value: Any, pattern: re.Pattern[str] = PRINTABLE_RE,
                  markdown: bool = True) -> str | None:
    if not isinstance(value, str) or not pattern.fullmatch(value) or UNSAFE_CELL_RE.search(value)             or (markdown and MARKDOWN_RE.search(value)):
        return f"notices: {what} {_show(repr(value))} cannot be printed in the Markdown table: refused, not escaped"
    return None


SECTION_INTRO = (
    "Where the Source column says \"source in `sources/`\", this bundle carries the complete corresponding\n"
    "source of that component, at the version its images hold, in `sources/files/`, each file named by its\n"
    "SHA-256. `sources/index.json` lists each file's upstream name, URL and checksums and the SBOM packages\n"
    "it covers.")
SECTION_PATHS = ("Paths here are relative to the bundle's `app/` directory, which install publishes as the "
                 "install directory.")
SECTION_SAMPLE = ("Verification bundle: this source set is a sample and is not complete; do not distribute "
                  "this bundle.")


def source_section(index: Any) -> tuple[str | None, list[str]]:
    """Item 7: the generated "Source code" section. It prints no generator
    text: only lock keys and URLs, image names, the policy entry's package and
    reviewed, and fixed text. Any value that could add a column or row is a
    problem, never escaped (U9-7)."""
    try:
        return _source_section(index)
    except Exception as exc:  # noqa: BLE001 - a problem, never an exception
        return None, [f"notices: {type(exc).__name__}: {_clean(exc)}"]


def _source_section(index: Any) -> tuple[str | None, list[str]]:
    if not isinstance(index, dict) or index.get("set") not in ("full", "sample") \
            or not isinstance(index.get("components"), list):
        return None, ["notices: the index is not a source index (set, components)"]
    rows: list[str] = []
    p: list[str] = []

    def check(what: str, value: Any, pattern: re.Pattern[str] = PRINTABLE_RE, markdown: bool = True) -> str:
        problem = _cell_problem(what, value, pattern, markdown)
        if problem:
            p.append(problem)
        return str(value)

    for c in index["components"]:
        status = c.get("status")
        if status == "partial":
            key = check("component key", c.get("key"), markdown=False)
            images = sorted({check("image", pk.get("image")) for pk in c.get("packages") or []})
            if not images:
                p.append(f"notices: {_show(key)} has no packages")
            files = c.get("files") or []
            rest = [f for f in files if f.get("path") is None]
            if index["set"] != "sample":
                p.append(f"notices: {_show(key)} is partial in a full index")
            if not rest or len(rest) == len(files):
                p.append(f"notices: {_show(key)} is partial but lists no fetched file or no unfetched file")
            url = check("URL", rest[0].get("url") if rest else None, markdown=False)
            rows.append(f"| `{key}` | {', '.join(images)} | partial source (verification sample): only the files "
                        f"that `sources/index.json` lists with a path are in `sources/files/`; "
                        f"Upstream source of the rest: {url} |")
        elif status in ("shipped", "not-shipped"):
            key = check("component key", c.get("key"), markdown=False)
            images = sorted({check("image", pk.get("image")) for pk in c.get("packages") or []})
            if not images:
                p.append(f"notices: {_show(key)} has no packages")
            if status == "shipped":
                source = "source in `sources/` (see `sources/index.json`)"
            else:
                files = c.get("files") or [{}]
                source = f"Upstream source: {check('URL', files[0].get('url'), markdown=False)}"
            rows.append(f"| `{key}` | {', '.join(images)} | {source} |")
        elif status == "exempt":
            ex = c.get("exempt") or {}
            package = check("exempt package", ex.get("package"))
            image = check("exempt image", ex.get("image"))
            check("reviewed", ex.get("reviewed"), FROM_PRINTABLE_RE)
            listing = check("listing", c.get("listing"), FROM_PRINTABLE_RE)
            rows.append(f"| `{package}` | {image} | no source in this bundle: cleared by a reviewed exemption "
                        f"({listing}) |")
        else:
            p.append(f"notices: a component has status {_show(repr(status))}")
    if p:
        return None, p
    out = ["## Source code", ""]
    if index["set"] == "sample":
        out += [SECTION_SAMPLE, ""]
    out += [SECTION_PATHS, "", SECTION_INTRO, "", "| Component | Images | Source |", "|---|---|---|"] + rows
    return "\n".join(out) + "\n", []


def _lstat_listing(directory: str) -> dict[str, tuple[str, int]]:
    """`{name: (kind, size)}` by `scandir` and `lstat`; never follows a link.
    An OSError propagates: a failed listing is a refusal, never an empty one."""
    out: dict[str, tuple[str, int]] = {}
    with os.scandir(directory) as it:
        for entry in it:
            st = os.lstat(os.path.join(directory, entry.name))
            kind = ("file" if stat.S_ISREG(st.st_mode) else "link" if stat.S_ISLNK(st.st_mode)
                    else "dir" if stat.S_ISDIR(st.st_mode) else "other")
            out[entry.name] = (kind, st.st_size)
    return out


def _fail(command: str, exc: BaseException) -> int:
    print(f"{command}: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)
    return 1


def _refuse(command: str, problems: list[str]) -> int:
    for line in problems[:20]:
        print(f"sbom_check: {command}: {line}", file=sys.stderr)
    return 1


def _open_regular(path: str) -> tuple[int, int]:
    """Open `path` for reading without following a link or blocking on a
    FIFO; the open fd must be a regular file. Returns (fd, size); an OSError
    when it cannot be opened or is not a regular file."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(errno.EINVAL, "is not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd, st.st_size


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _sha256_of(path: str) -> str:
    fd, _ = _open_regular(path)
    h = hashlib.sha256()
    with os.fdopen(fd, "rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _record_text(directory: str) -> tuple[str | None, list[str]]:
    path = os.path.join(directory, "fetch.json")
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None, ["fetch.json: missing; run scripts/bundle_fetch.sh first"]
    if not stat.S_ISREG(st.st_mode):
        return None, ["fetch.json: is not a regular file"]
    if st.st_size > RECORD_MAX:
        return None, [f"fetch.json is {st.st_size} bytes, over 4 MiB"]
    try:
        fd, size = _open_regular(path)
    except OSError as exc:
        return None, [f"fetch.json: cannot read ({type(exc).__name__}): is not a regular file or cannot be opened"]
    if size > RECORD_MAX:
        os.close(fd)
        return None, [f"fetch.json is {size} bytes, over 4 MiB"]
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(RECORD_MAX + 1)
    if len(data) > RECORD_MAX:
        return None, [f"fetch.json is {len(data)} bytes, over 4 MiB"]
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError:
        return None, ["fetch.json: not UTF-8"]


def sources_check(a: argparse.Namespace) -> int:
    try:
        text = _read_text(a.lock)
        json.loads(text)
        with open(a.policy, encoding="utf-8") as fh:
            policy = json.load(fh)
        if not stat.S_ISDIR(os.lstat(a.dir).st_mode):
            return _refuse("sources-check", [f"--dir {_clean(a.dir)} is not a directory (or is a link)"])
        record, problems = _record_text(a.dir)
        if record is not None:
            problems = fetch_record_problems(record, text, policy, a.arch, a.set)
        if problems:
            return _refuse("sources-check", problems)
        plan = fetch_plan(json.loads(text), a.arch, a.set)
        try:
            listing = _lstat_listing(a.dir)
        except OSError:
            return _refuse("sources-check", [f"{_clean(a.dir)}: cannot list"])
        problems = listing_problems(listing, plan, True, a.dir)
        if problems:
            return _refuse("sources-check", problems)
        planned = _planned(plan)
        for sha, (key, f) in sorted(planned.items()):
            label = f"--sources: {sha} ({_clean(key)} {_clean(f['name'])})"
            try:
                got = _sha256_of(os.path.join(a.dir, sha))
            except OSError as exc:
                problems.append(f"{label}: cannot read ({type(exc).__name__})")
                continue
            if got != sha:
                problems.append(f"{label}: sha256 mismatch: got {got}")
        if problems:
            return _refuse("sources-check", problems)
    except Exception as exc:  # noqa: BLE001 - one FAIL line, never a traceback (as lock-check)
        return _fail("sources-check", exc)
    for sha in sorted(planned):
        print(sha)
    print(f"sources-check: ok {len(planned)} files, {sum(f['size'] for _, f in planned.values())} bytes, "
          f"{len({k for k, _ in plan})} components ({a.set}, {a.arch})", file=sys.stderr)
    return 0


def index_cli(a: argparse.Namespace) -> int:
    if not SHA_RE.fullmatch(a.git_sha):
        print(f"sbom_check: index: --git-sha {a.git_sha!r} is not 40 lower-case hex digits", file=sys.stderr)
        return 2
    paths: dict[str, str] = {}
    for spec in a.sbom:
        image, sep, path = spec.partition("=")
        if not sep or not NAME_RE.fullmatch(image) or not path or image in paths:
            print(f"sbom_check: index: --sbom {spec!r} is not a new IMAGE=PATH", file=sys.stderr)
            return 2
        paths[image] = path
    try:
        text = _read_text(a.lock)
        json.loads(text)
        with open(a.policy, encoding="utf-8") as fh:
            policy = json.load(fh)
        docs = {}
        for image, path in paths.items():
            with open(path, encoding="utf-8") as fh:
                docs[image] = json.load(fh)
        try:
            listing = _lstat_listing(a.files)
        except OSError:
            return _refuse("index", [f"{_clean(a.files)}: cannot list"])
        index, problems = source_index(docs, text, policy, a.arch, a.set, a.git_sha, listing)
        if index is None:
            return _refuse("index", problems)
        out = lock_text(index)
    except Exception as exc:  # noqa: BLE001 - one FAIL line, never a traceback
        return _fail("index", exc)
    for c in index["components"]:
        if c["status"] == "exempt":
            print(f"index: {_clean(c['exempt']['image'])}: {_clean(c['exempt']['package'])}: {_clean(c['listing'])}",
                  file=sys.stderr)
    sys.stdout.write(out)
    return 0


def notices_cli(a: argparse.Namespace) -> int:
    try:
        fd, size = _open_regular(a.index)
        if size > INDEX_MAX:
            os.close(fd)
            return _refuse("notices", [f"--index {_clean(a.index)} is {size} bytes, over 16 MiB"])
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            index = json.load(fh)
        text, problems = source_section(index)
    except Exception as exc:  # noqa: BLE001 - one FAIL line, never a traceback
        return _fail("notices", exc)
    if text is None:
        return _refuse("notices", problems)
    sys.stdout.write(text)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sbom_check.py")
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("finish")
    for opt in ("--name", "--ref", "--arch", "--git-sha", "--raw", "--tar"):
        f.add_argument(opt, required=True)
    f.add_argument("--site")
    f.add_argument("--lock")
    d = sub.add_parser("drift")
    for opt in ("--sbom", "--base", "--added-from", "--libpq", "--lock"):
        d.add_argument(opt, required=True)
    d.add_argument("--licence", action="append", required=True)
    n = sub.add_parser("neo4j")
    for opt in ("--official-config", "--config", "--sbom", "--tar"):
        n.add_argument(opt, required=True)
    t = sub.add_parser("tree")
    for opt in ("--official", "--image"):
        t.add_argument(opt, required=True)
    lc = sub.add_parser("lock-check")
    for opt in ("--lock", "--policy", "--arch"):
        lc.add_argument(opt, required=True)
    lc.add_argument("--sbom", action="append", required=True)
    lc.add_argument("--pending-neo4j", action="store_true")
    ln = sub.add_parser("lock-needs")
    ln.add_argument("--policy", required=True)
    ln.add_argument("--sbom", action="append", required=True)
    ln.add_argument("--tar", action="append")
    sc = sub.add_parser("sources-check")
    for opt in ("--lock", "--policy", "--dir"):
        sc.add_argument(opt, required=True)
    sc.add_argument("--arch", required=True, choices=LOCK_ARCHES)
    sc.add_argument("--set", required=True, choices=("full", "sample"))
    ix = sub.add_parser("index")
    for opt in ("--lock", "--policy", "--git-sha", "--files"):
        ix.add_argument(opt, required=True)
    ix.add_argument("--arch", required=True, choices=LOCK_ARCHES)
    ix.add_argument("--set", required=True, choices=("full", "sample"))
    ix.add_argument("--sbom", action="append", required=True)
    nt = sub.add_parser("notices")
    nt.add_argument("--index", required=True)
    args = parser.parse_args(argv)
    if args.command == "finish":
        return finish(args)
    if args.command == "drift":
        return drift(args)
    if args.command == "neo4j":
        return neo4j(args)
    if args.command == "tree":
        return tree(args)
    if args.command == "lock-check":
        return lock_check(args)
    if args.command == "lock-needs":
        return lock_needs_cli(args)
    if args.command == "sources-check":
        return sources_check(args)
    if args.command == "index":
        return index_cli(args)
    if args.command == "notices":
        return notices_cli(args)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
