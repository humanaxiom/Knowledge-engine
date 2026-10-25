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
import importlib.metadata
import json
import re
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
# Runs of unparseable text: split on anything outside the idstring set.
RUN_SPLIT_RE = re.compile(r"[^A-Za-z0-9.+:-]+")


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
    """A hash id, or NONE/NOASSERTION under ASCII case-fold (rework round 1),
    with or without a DocumentRef-<id>: prefix (round 2)."""
    bare = _bare(id_)
    return bool(HASH_ID_RE.fullmatch(bare)) or (bare.isascii() and bare.upper() in UNKNOWN_LEAVES)


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


def classify_document(image: str, doc: dict[str, Any], always: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per package but the DESCRIBES root; an `always` match (N10)
    needs source whatever the licence says."""
    flagged, _ = always_matches(image, doc, always)
    rows = []
    for pkg in _packages(doc):
        row = classify_package(pkg)
        row["always"] = str(pkg.get("SPDXID")) in flagged
        if row["always"]:
            row["needs"] = True
        rows.append(row)
    return rows


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
    args = parser.parse_args(argv)
    if args.command == "finish":
        return finish(args)
    if args.command == "drift":
        return drift(args)
    if args.command == "neo4j":
        return neo4j(args)
    if args.command == "tree":
        return tree(args)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
