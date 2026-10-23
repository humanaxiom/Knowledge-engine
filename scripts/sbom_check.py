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
(`validate`) and exits 1 naming the first failures.

(tester's reach target for U3 RED; the developer owns the real file)
"""

from __future__ import annotations

import argparse
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
    its uv.lock version."""
    with open(lock_path, "rb") as fh:
        lock = {_norm(p["name"]): p["version"] for p in tomllib.load(fh).get("package", [])}
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
        if dist.version != want:
            p.append(f"{name} is installed at {dist.version}, uv.lock has {want}")
        if want not in listed.get(name, set()):
            p.append(f"the SBOM does not list pkg:pypi/{name}@{want} (it lists {sorted(listed.get(name, []))})")
    if not found:
        p.append(f"no installed distribution found in {site}")
    return p


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
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sbom_check.py")
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("finish")
    for opt in ("--name", "--ref", "--arch", "--git-sha", "--raw", "--tar"):
        f.add_argument(opt, required=True)
    f.add_argument("--site")
    f.add_argument("--lock")
    args = parser.parse_args(argv)
    if args.command == "finish":
        return finish(args)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
