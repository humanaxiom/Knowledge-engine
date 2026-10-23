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
        p.append(f"spdxVersion is {doc.get('spdxVersion')!r}, want SPDX-2.3")
    if doc.get("dataLicense") != "CC0-1.0":
        p.append(f"dataLicense is {doc.get('dataLicense')!r}, want CC0-1.0")
    if doc.get("SPDXID") != "SPDXRef-DOCUMENT":
        p.append(f"SPDXID is {doc.get('SPDXID')!r}, want SPDXRef-DOCUMENT")
    if not isinstance(doc.get("name"), str) or not doc.get("name"):
        p.append("name is empty")
    ns = doc.get("documentNamespace")
    if not isinstance(ns, str) or not NAMESPACE_RE.fullmatch(ns):
        p.append(f"documentNamespace {ns!r} is not urn:uuid:<lower-case uuid4>")
    info = doc.get("creationInfo")
    if not isinstance(info, dict):
        p.append("creationInfo is missing")
        info = {}
    if not RFC3339_UTC.match(str(info.get("created", ""))):
        p.append(f"creationInfo.created {info.get('created')!r} is not an RFC 3339 UTC time")
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
        if not isinstance(sid, str) or not SPDXID_RE.match(sid):
            p.append(f"package {i} has SPDXID {sid!r}")
        elif sid in ids:
            p.append(f"package SPDXID {sid} is not unique")
        else:
            ids.add(sid)
        if not pkg.get("name"):
            p.append(f"package {sid} has no name")
        if not pkg.get("downloadLocation"):
            p.append(f"package {sid} has no downloadLocation")
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
                p.append(f"relationship end {end!r} does not resolve")
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


# --- PSC-14/22 B3, N7: the image-side drift check (U4) ----------------------

def _named(doc: dict[str, Any], ptype: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for pkg in _packages(doc):
        m = PURL_RE.match(_purl(pkg) or "")
        if m and m.group("type") == ptype:
            n = unquote(m.group("name"))
            out.setdefault(_norm(n) if ptype == "pypi" else n, set()).add(unquote(m.group("version")))
    return out


def drift_problems(app: dict[str, Any], base: dict[str, Any], added: frozenset[str] | set[str],
                   licence_texts: dict[str, str]) -> list[str]:
    p = []
    debs = set(_named(app, "deb")) - set(_named(base, "deb"))
    for n in sorted(debs - set(added)):
        p.append(f"ke-app adds the Debian package {n}, which ADDED_PACKAGES does not name")
    for n in sorted(set(added) - debs):
        p.append(f"ADDED_PACKAGES names {n}, which the ke-app SBOM does not add to its base")
    pypi = _named(app, "pypi")
    if "pip" in pypi:
        p.append(f"the ke-app SBOM lists pip {sorted(pypi['pip'])} (pip is not shipped)")
    py = set()
    for pkg in _packages(app):
        m = PURL_RE.match(_purl(pkg) or "")
        if m and m.group("type") == "generic" and not m.group("ns") and m.group("name") == "python":
            py.add(unquote(m.group("version")))
    if len(py) != 1:
        p.append(f"the ke-app SBOM lists CPython (pkg:generic/python) at {sorted(py)}, want exactly one version")
    for path, text in sorted(licence_texts.items()):
        m = re.match(r"^CPython (\d+\.\d+\.\d+):", text.split("\n", 1)[0])
        if not m:
            p.append(f"{path}: line 1 does not start `CPython X.Y.Z:`")
        elif len(py) == 1 and m.group(1) not in py:
            p.append(f"{path} names CPython {m.group(1)}, the ke-app SBOM lists {sorted(py)[0]}")
    return p


def psycopg_problems(app: dict[str, Any], libpq_pin: str, psycopg_c_version: str | set[str] | frozenset[str]
                     ) -> list[str]:
    p = []
    major = libpq_pin.split(".", 1)[0]
    libpq = [(unquote(m.group("version")), _qualifiers(purl).get("upstream", "").split("@", 1)[0])
             for purl in (_purl(x) or "" for x in _packages(app))
             for m in [PURL_RE.match(purl)] if m and m.group("type") == "deb" and m.group("name") == "libpq5"]
    if (libpq_pin, f"postgresql-{major}") not in libpq:
        p.append(f"the ke-app SBOM does not list libpq5 {libpq_pin} (upstream postgresql-{major}): {libpq}")
    pypi = _named(app, "pypi")
    want = {psycopg_c_version} if isinstance(psycopg_c_version, str) else set(psycopg_c_version)
    if not want & pypi.get("psycopg-c", set()):
        p.append(f"the ke-app SBOM does not list psycopg-c at a locked version {sorted(want)}: "
                 f"{sorted(pypi.get('psycopg-c', []))}")
    if "psycopg-binary" in pypi:
        p.append(f"the ke-app SBOM lists psycopg-binary {sorted(pypi['psycopg-binary'])} (PSC-25)")
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
    py = sorted(_named(docs[0], "generic").get("python", set()))
    pc = sorted(locked & _named(docs[0], "pypi").get("psycopg-c", set()))
    major = a.libpq.split(".", 1)[0]
    print(f"sbom_check: drift: ok: added {', '.join(sorted(added))}; no pip; CPython {', '.join(py)} "
          f"({len(texts)} licence files); libpq5 {a.libpq} (postgresql-{major}); psycopg-c {', '.join(pc)}, "
          "no psycopg-binary")
    return 0


def finish(a: argparse.Namespace) -> int:
    for label, value, rx in (("--name", a.name, NAME_RE), ("--git-sha", a.git_sha, SHA_RE)):
        if not rx.match(value):
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
    args = parser.parse_args(argv)
    if args.command == "finish":
        return finish(args)
    if args.command == "drift":
        return drift(args)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
