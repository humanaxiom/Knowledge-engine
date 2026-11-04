"""platform-sbom U3: one SPDX 2.3 SBOM per bundled image (PSC-13), the
generator run and the `finish` step (orchestrator rulings 1 and 5).

Criteria: docs/requirements.md § "Item: platform-sbom" PSC-13 (with PSC-20's
run rules and PSC-21's "each SBOM records that architecture"). Design:
docs/architecture.md ADR-KE-016 points 1, 2 and 6; design-notes N1 (the run
form), N3 (`scripts/sbom_check.py`), N6 (the final document), N7 (ke-app's
runtime packages) and N15's U3 row. Carried from the U2 commit gate
(docs/handoffs/platform-sbom.md): review N1 (--env-file and KE_SBOM_* on the
run and its `down`), N2 (the generator is linux/$arch), N3 (offline_check
header); security L-1 (no include/extends), L-2 (run as the caller's uid:gid),
I-1 (`ref_re` leading `-`), I-2 (in tests/test_sbom_generator.py). Test names
are PSC-13's tags plus one per carried item.

Interface pinned by these tests (tester, RED U3, 2026-10-23):
- After the saves, for each image in bundle.json (`images/<name>.tar`),
  bundle.sh runs the generator once, exactly as
    docker compose -p <project>-sbom --env-file .env.example
      -f docker-compose.sbom.yml run --rm --pull never [-T|--no-TTY|--no-deps]
      sbom docker-archive:/in/<name>.tar --scope all-layers
      -o spdx-json=/out/raw.spdx.json
  (the three global options in any order, long spellings allowed), where
  <project> is the stack model's name, with KE_SBOM_IN = <out>/images,
  KE_SBOM_OUT = a fresh work dir of that image only (outside --out, holding
  just an empty `tmp/` when syft starts, gone when bundle.sh exits) and
  KE_SBOM_USER = `$(id -u):$(id -g)`. The only compose subcommands on the
  file are `config`, `run` and `down`. After the last run (and on a failure)
  bundle.sh runs `docker compose -p <project>-sbom --env-file .env.example
  -f docker-compose.sbom.yml down [--remove-orphans|-v|--volumes]` with every
  `${VAR:?}` of the file set non-empty.
- The `sbom` service's `user:` is `${KE_SBOM_USER:?...}` (security L-2).
- Before any write, the generator image is linux/<daemon arch>, else the
  bundle is refused naming the reference and `linux/<arch>` (review N2,
  PSC-21). `ref_re` refuses a reference starting with `-` ("fails its
  pattern") before any `docker image inspect` of it (security I-1).
- Then, per image, the checker runs in the ke-app image being bundled
  (N3): `docker run --rm --network none --read-only --cap-drop ALL
  --security-opt no-new-privileges --pull never --label
  com.docker.compose.project=<project>-sbomcheck --entrypoint python
  -v <checkout>/scripts/sbom_check.py:<path>:ro -v ...:ro <ke-app ref>
  -I <path>/sbom_check.py finish ...`; every mount read-only, no socket.
  Every path the checker reads is on its command line (the fake docker maps
  mount targets and the image's /opt/venv and /app). Its CLI (architect's N6
  amendment) is `finish --name N --ref R --arch A --git-sha S --raw PATH
  --tar PATH [--site DIR --lock PATH]`; `--uuid` is an unknown option (exit 2),
  and two runs on the same inputs print different namespaces. Its stdout is
  `app/sboms/<name>.spdx.json`, which MANIFEST.sha256 lists.
- The final document (N6): syft's packages, files, relationships and other
  fields kept; `name` = the bundle.json ref; `documentNamespace` =
  `urn:uuid:<uuid4>`, lower-case, a fresh `uuid.uuid4()` per document drawn
  in sbom_check.py (orchestrator ruling on the U3 RED blocker, 2026-10-23,
  option b: no URL literal, no NAMESPACE_BASE), so namespaces differ across
  a bundle's documents and again on every run; creators keep syft's
  `Tool: syft-<pinned version>` and add `Tool: knowledge-engine-bundle-
  <git_sha[:12]>`; document `annotations` hold exactly one each of
  `ke:ref=<ref>`, `ke:arch=<arch>` and `ke:image-config=sha256:<64 hex>` (the
  tar's manifest.json `Config`, docker 25+ `blobs/sha256/<hex>` or older
  `<hex>.json`), each `annotationType: OTHER`, annotator that tool, an RFC 3339
  UTC `annotationDate`. A tar whose manifest.json does not hold exactly one
  image is refused.
- ke-app's document lists, as `pkg:pypi/<name>@<version>` (names PEP 503
  compared, versions percent-decoded), every package of PSC-13's runtime set
  (the builder's final `uv sync --locked --no-dev --group pq-c
  --no-binary-package psycopg-c`, read from uv.lock with markers evaluated
  for linux CPython 3.12, the project excluded) at its locked version; an
  installed package missing from the SBOM or at another version refuses the
  bundle, naming it (N7).
- Any SBOM failure (syft exits non-zero, a raw document that is not JSON,
  empty, not SPDX-2.3 or with a dangling relationship, the runtime check)
  exits non-zero naming the image, with no MANIFEST.sha256 and no release
  record (PSC-24's spirit; PSC-24's own test and the other paths are U9's).
- `scripts/sbom_check.py`: standard library only, never shipped, never
  imported by engine/ or harness_telemetry/, no Dockerfile copies it; it has
  `validate(doc) -> list[str]` (N6's required-field validator; [] = valid).
- docker-compose.sbom.yml has only `services` and `x-*` at its top level,
  docker-compose.scan.yml only `services`, `volumes` and `x-*`; no service
  of either has `extends` (security L-1).
- offline_check.sh's header stage list names the generator pull before
  bundle.sh (review N3).

Neo4j's jars (ruling 5) are not decided by these tests: they are stubbed, and
what syft reports for the real neo4j tar is first seen in the developer's
GREEN `verify full` (handed to the architect if any is GPL-family).

Every check is a function returning a list of problems, so the U3 controls
(docs/evidence/platform-sbom/u3/red-mutants.txt) can run each on mutants.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import unquote

from tests import compose_support as cs
from tests import fake_docker
from tests.engine_support import ROOT
from tests.test_offline_bundle import _BundleBase, _norm, _rel

SBOM_COMPOSE = ROOT / cs.SBOM_COMPOSE_NAME
SCAN_COMPOSE = ROOT / "docker-compose.scan.yml"
SBOM_CHECK = ROOT / "scripts" / "sbom_check.py"
OFFLINE_CHECK = ROOT / "scripts" / "offline_check.sh"
CHECK_MISSING = "scripts/sbom_check.py is missing (PSC-13; ADR-KE-016 point 2, design-notes N3)"

PROJECT = "ke-u3proj"
SBOM_PROJECT = f"{PROJECT}-sbom"
CHECK_LABEL = f"com.docker.compose.project={PROJECT}-sbomcheck"
TOOL_PREFIX = "Tool: knowledge-engine-bundle-"
# Orchestrator ruling (U3 RED blocker, option b): a version-4 UUID URN, lower
# case, nothing after it. Matched with fullmatch, so a trailing newline fails.
NAMESPACE_RE = re.compile(
    r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
VALID_NAMESPACE = "urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e"
RFC3339_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
USER_SOURCE = re.compile(r"^\$\{KE_SBOM_USER:\?[^}]*\}$")
GLOBAL_OPTS = {"-p": "-p", "--project-name": "-p", "-f": "-f", "--file": "-f", "--env-file": "--env-file"}
WANT_GLOBALS = {("-p", SBOM_PROJECT), ("--env-file", ".env.example"), ("-f", cs.SBOM_COMPOSE_NAME)}
RUN_OPTS_ALLOWED = {"-T", "--no-TTY", "--no-deps"}
DOWN_OPTS_ALLOWED = {"--remove-orphans", "-v", "--volumes"}
SBOM_SUBCOMMANDS = {"config", "run", "down"}
DESCRIBES = "DESCRIBES"


def run_tail(name: str) -> list[str]:
    return [f"docker-archive:/in/{name}.tar", "--scope", "all-layers", "-o", "spdx-json=/out/raw.spdx.json"]


def pinned_syft_version() -> str:
    m = re.search(r":v(\d+\.\d+\.\d+)@", cs.sbom_generator_ref(SBOM_COMPOSE))
    return m.group(1) if m else "0.0.0"


# --------------------------------------------------------------------------
# PSC-13's runtime set, from uv.lock
# --------------------------------------------------------------------------

# The ke-app image: Debian 12, CPython 3.12 (docker/app.Dockerfile).
LINUX_MARKERS = {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix",
                 "implementation_name": "cpython", "platform_python_implementation": "CPython"}
_CLAUSE = re.compile(r"\s*([a-z_]+)\s*(==|!=)\s*'([^']*)'\s*")


def marker_true(marker: str) -> bool:
    """uv.lock markers of the forms `<var> ==|!= '<value>'` joined by `and`/`or`
    (the lock has no other form today); anything else fails loudly, so a new
    form is noticed rather than guessed."""
    def clause(text: str) -> bool:
        m = _CLAUSE.fullmatch(text)
        if not m or m.group(1) not in LINUX_MARKERS or "(" in text:
            raise AssertionError(f"marker form not understood by the test: {marker!r}; extend LINUX_MARKERS")
        got = LINUX_MARKERS[m.group(1)]
        return (got == m.group(3)) if m.group(2) == "==" else (got != m.group(3))
    return any(all(clause(c) for c in part.split(" and ")) for part in marker.split(" or "))


def locked_runtime_packages(lock_text: str | None = None) -> dict[str, str]:
    """PSC-13: name -> locked version of every package the ke-app builder's
    final sync (`uv sync --locked --no-dev --group pq-c --no-binary-package
    psycopg-c`) installs into /opt/venv on linux CPython 3.12: the project's
    dependencies and its pq-c group, their extras, transitively, the project
    itself excluded (N7)."""
    lock = tomllib.loads(lock_text if lock_text is not None else (ROOT / "uv.lock").read_text(encoding="utf-8"))
    pkgs = {p["name"]: p for p in lock["package"]}
    root = pkgs["knowledge-engine"]
    todo = list(root.get("dependencies", [])) + list(root.get("dev-dependencies", {}).get("pq-c", []))
    seen: dict[str, str] = {}
    done: set[tuple[str, str]] = set()
    while todo:
        dep = todo.pop()
        if "marker" in dep and not marker_true(dep["marker"]):
            continue
        name = dep["name"]
        for extra in [""] + list(dep.get("extra", [])):
            if (name, extra) in done:
                continue
            done.add((name, extra))
            pkg = pkgs[name]
            seen[name] = pkg["version"]
            todo += pkg.get("dependencies", []) if not extra else pkg.get("optional-dependencies", {}).get(extra, [])
    seen.pop("knowledge-engine", None)
    return seen


# --------------------------------------------------------------------------
# SPDX helpers
# --------------------------------------------------------------------------

_PURL = re.compile(r"^pkg:(?P<type>[a-z0-9.+-]+)/(?:(?P<ns>[^@?#]+)/)?(?P<name>[^/@?#]+)@(?P<version>[^?#]+)")


def purls(doc: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """(type, name, version) of every package purl, decoded."""
    out = []
    for pkg in doc.get("packages") or []:
        for ref in pkg.get("externalRefs") or []:
            if ref.get("referenceType") == "purl":
                m = _PURL.match(str(ref.get("referenceLocator", "")))
                if m:
                    out.append((m.group("type"), unquote(m.group("name")), unquote(m.group("version"))))
    return out


def tar_config_digest(path: Path) -> str:
    """`sha256:<hex>` from the tar's manifest.json `Config` (PSC-13)."""
    with tarfile.open(path) as tar:
        member = tar.extractfile("manifest.json")
        assert member is not None
        manifest = json.load(member)
    cfg = manifest[0]["Config"]
    m = re.fullmatch(r"blobs/sha256/([0-9a-f]{64})", cfg) or re.fullmatch(r"([0-9a-f]{64})\.json", cfg)
    assert m, f"the fake tar's Config is {cfg!r}"
    return "sha256:" + m.group(1)


def annotation_problems(doc: Mapping[str, Any], git_sha: str) -> tuple[dict[str, str], list[str]]:
    """N6 annotations: exactly one each of ke:ref, ke:arch, ke:image-config."""
    found: dict[str, str] = {}
    problems: list[str] = []
    annotator = TOOL_PREFIX + git_sha[:12]
    for a in doc.get("annotations") or []:
        m = re.fullmatch(r"ke:(ref|arch|image-config)=(.+)", str(a.get("comment", "")))
        if not m:
            continue
        key = m.group(1)
        if key in found:
            problems.append(f"annotation ke:{key} appears twice")
        found[key] = m.group(2)
        if a.get("annotationType") != "OTHER":
            problems.append(f"annotation ke:{key} has annotationType {a.get('annotationType')!r}, want OTHER")
        if a.get("annotator") != annotator:
            problems.append(f"annotation ke:{key} has annotator {a.get('annotator')!r}, want {annotator!r}")
        if not RFC3339_UTC.match(str(a.get("annotationDate", ""))):
            problems.append(f"annotation ke:{key} has annotationDate {a.get('annotationDate')!r} (RFC 3339 UTC)")
    for key in ("ref", "arch", "image-config"):
        if key not in found:
            problems.append(f"no document annotation `ke:{key}=...` (N6, ADR-KE-016 point 6)")
    return found, problems


def document_problems(doc: Any, *, ref: str, arch: str, name: str, git_sha: str,
                      syft_version: str) -> list[str]:
    """PSC-13's required fields and N6's identity on one final document."""
    if not isinstance(doc, dict):
        return ["the SBOM is not a JSON object"]
    p = []
    if doc.get("spdxVersion") != "SPDX-2.3":
        p.append(f"spdxVersion is {doc.get('spdxVersion')!r}, want 'SPDX-2.3'")
    if doc.get("dataLicense") != "CC0-1.0":
        p.append(f"dataLicense is {doc.get('dataLicense')!r}, want 'CC0-1.0'")
    if doc.get("SPDXID") != "SPDXRef-DOCUMENT":
        p.append(f"SPDXID is {doc.get('SPDXID')!r}")
    if doc.get("name") != ref:
        p.append(f"name is {doc.get('name')!r}, want the bundle.json ref {ref!r} (N6)")
    if not NAMESPACE_RE.fullmatch(str(doc.get("documentNamespace", ""))):
        p.append(f"documentNamespace {doc.get('documentNamespace')!r} is not urn:uuid:<lower-case uuid4> "
                 "(orchestrator ruling, option b)")
    info = doc.get("creationInfo") or {}
    creators = info.get("creators") or []
    if f"Tool: syft-{syft_version}" not in creators:
        p.append(f"creationInfo.creators {creators} do not name the pinned generator `Tool: syft-{syft_version}`")
    if TOOL_PREFIX + git_sha[:12] not in creators:
        p.append(f"creationInfo.creators {creators} lack `{TOOL_PREFIX}{git_sha[:12]}` (N6)")
    if not RFC3339_UTC.match(str(info.get("created", ""))):
        p.append(f"creationInfo.created {info.get('created')!r} is not an RFC 3339 UTC time")
    values, ann = annotation_problems(doc, git_sha)
    p += ann
    if values.get("ref") not in (None, ref):
        p.append(f"ke:ref is {values.get('ref')!r}, want {ref!r}")
    if values.get("arch") not in (None, arch):
        p.append(f"ke:arch is {values.get('arch')!r}, want {arch!r} (PSC-21)")
    if "image-config" in values and not re.fullmatch(r"sha256:[0-9a-f]{64}", values["image-config"]):
        p.append(f"ke:image-config is {values['image-config']!r}, want sha256:<64 hex>")
    return p


def raw_doc(name: str, syft_version: str) -> dict[str, Any]:
    """A syft-shaped raw SPDX 2.3 document (independent of the fake's)."""
    root = f"SPDXRef-DocumentRoot-Image-{name}"
    deb = [("musl", "1.2.5-r10", "MIT"), ("busybox", "1.37.0-r19", "GPL-2.0-only")]
    pkgs = [{"name": f"/in/{name}.tar", "SPDXID": root, "versionInfo": "sha256:" + "a" * 64,
             "downloadLocation": "NOASSERTION", "filesAnalyzed": False, "primaryPackagePurpose": "CONTAINER"}]
    rels = [{"spdxElementId": "SPDXRef-DOCUMENT", "relatedSpdxElement": root, "relationshipType": DESCRIBES}]
    for i, (n, v, lic) in enumerate(deb):
        sid = f"SPDXRef-Package-apk-{n}-{i:016x}"
        pkgs.append({"name": n, "SPDXID": sid, "versionInfo": v, "downloadLocation": "NOASSERTION",
                     "filesAnalyzed": False, "licenseDeclared": lic, "licenseConcluded": "NOASSERTION",
                     "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                                       "referenceLocator": f"pkg:apk/alpine/{n}@{v}?arch=x86_64&distro=alpine-3.22"}]})
        rels.append({"spdxElementId": root, "relatedSpdxElement": sid, "relationshipType": "CONTAINS"})
        rels.append({"spdxElementId": sid, "relatedSpdxElement": "SPDXRef-File-lib-apk-db-installed-0",
                     "relationshipType": "OTHER", "comment": "evident-by"})
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"/in/{name}.tar",
            "documentNamespace": f"https://anchore.com/syft/file/in/{name}.tar-00000000-0000-4000-8000-000000000000",
            "creationInfo": {"licenseListVersion": "3.27",
                             "creators": ["Organization: Anchore, Inc", f"Tool: syft-{syft_version}"],
                             "created": "2026-10-23T10:00:00Z"},
            "packages": pkgs,
            "files": [{"fileName": "/lib/apk/db/installed", "SPDXID": "SPDXRef-File-lib-apk-db-installed-0",
                       "checksums": [{"algorithm": "SHA1", "checksumValue": "0" * 40}]}],
            "relationships": rels}


def load_sbom_check() -> ModuleType:
    if not SBOM_CHECK.is_file():
        raise AssertionError(CHECK_MISSING)
    spec = importlib.util.spec_from_file_location("ke_sbom_check_under_test", SBOM_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Static checks (each returns problems; [] is a pass)
# --------------------------------------------------------------------------

def user_problems(data: Mapping[str, Any]) -> list[str]:
    """Security L-2: syft runs as the caller's uid:gid, from a ${...:?} var."""
    svc = ((data.get("services") or {}).get("sbom")) or {}
    user = svc.get("user")
    if user is None:
        return ["sbom: no `user:` (security L-2: syft must run as the caller's uid:gid, "
                "`user: ${KE_SBOM_USER:?...}`)"]
    if not USER_SOURCE.match(str(user)):
        return [f"sbom: user is {user!r}, want `${{KE_SBOM_USER:?...}}` (set by bundle.sh to $(id -u):$(id -g))"]
    return []


def top_level_problems(data: Mapping[str, Any], text: str, file: str, allowed: set[str]) -> list[str]:
    """Security L-1: compose `config` fetches a remote top-level `include`, and
    `extends` merges another service's settings in unseen by the raw-YAML
    checks, so neither may appear."""
    p = []
    for key in data:
        if key not in allowed and not str(key).startswith("x-"):
            p.append(f"{file}: top-level `{key}` (only {sorted(allowed)} and x-* are allowed; security L-1)")
    for name, svc in (data.get("services") or {}).items():
        if isinstance(svc, dict) and "extends" in svc:
            p.append(f"{file}: service {name} uses `extends` (security L-1)")
    for m in re.finditer(r"(?m)^\s*-?\s*(include|extends)\s*:", text):
        p.append(f"{file}: a line sets `{m.group(1)}:` (security L-1)")
    return p


def stdlib_problems(source: str) -> list[str]:
    """N3: standard library only."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"scripts/sbom_check.py does not parse: {exc}"]
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    p = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                p.append("scripts/sbom_check.py uses a relative import")
                continue
            names = [node.module or ""]
        for n in names:
            if n.split(".", 1)[0] not in allowed:
                p.append(f"scripts/sbom_check.py imports {n}, which is not in the standard library (N3)")
    if "__main__" not in source:
        p.append("scripts/sbom_check.py has no `if __name__ == \"__main__\":` entry point (it is run as a script)")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "validate" for n in tree.body):
        p.append("scripts/sbom_check.py defines no top-level `validate(doc)` (N6's validator)")
    return p


def shipped_problems(root: Path) -> list[str]:
    """N3: never shipped in an image, never imported by the product."""
    p = []
    for pkg in ("engine", "harness_telemetry"):
        for f in sorted((root / pkg).rglob("*.py")):
            if "sbom_check" in f.read_text(encoding="utf-8"):
                p.append(f"{_rel(f, root)} names sbom_check (never imported by the product, N3)")
    for f in sorted((root / "docker").glob("*Dockerfile")):
        text = f.read_text(encoding="utf-8")
        if "sbom_check" in text or re.search(r"(?m)^\s*COPY\b[^\n]*\bscripts\b", text):
            p.append(f"{_rel(f, root)} copies scripts/ or sbom_check.py into an image (N3: never shipped)")
    bundle = (root / "scripts" / "bundle.sh").read_text(encoding="utf-8")
    for line in bundle.splitlines():
        if re.match(r"\s*cp\b", line) and "sbom_check" in line:
            p.append(f"bundle.sh copies sbom_check.py into the bundle: {line.strip()!r}")
    return p


def offline_header_problems(text: str) -> list[str]:
    """Review N3: the host-half stage list names the generator pull before
    bundle.sh."""
    header = []
    for line in text.splitlines()[1:]:
        if not line.startswith("#"):
            break
        header.append(line.lstrip("#").strip())
    flat = " ".join(header)
    if not re.search(r"(?i)(?:pull[^>]{0,60}(?:sbom|generator)|(?:sbom|generator)[^>]{0,60}pull)[^>]{0,40}->\s*bundle\.sh",
                     flat):
        return ["offline_check.sh's header stage list does not name the SBOM generator pull before "
                "bundle.sh (review N3, U2)"]
    return []


def validate_cases(valid: dict[str, Any]) -> dict[str, tuple[Any, bool]]:
    """name -> (document, want problems). N6's required-field set."""
    import copy

    def edit(fn: Any) -> Any:
        d = copy.deepcopy(valid)
        fn(d)
        return d

    pkg1 = valid["packages"][1]["SPDXID"]
    pkg2 = valid["packages"][2]["SPDXID"]

    def rename(d: dict[str, Any], old: str, new: str) -> None:
        """Give packages[2] a new id everywhere, so only the id rule is broken."""
        d["packages"][2]["SPDXID"] = new
        for r in d["relationships"]:
            for end in ("spdxElementId", "relatedSpdxElement"):
                if r[end] == old:
                    r[end] = new

    return {
        "valid": (valid, False),
        "valid, relationship to a file id": (edit(lambda d: d["relationships"].append(
            {"spdxElementId": pkg1, "relatedSpdxElement": d["files"][0]["SPDXID"], "relationshipType": "CONTAINS"})),
            False),
        "valid, extra creators": (edit(lambda d: d["creationInfo"]["creators"].append("Person: someone")), False),
        "spdxVersion SPDX-2.2": (edit(lambda d: d.update(spdxVersion="SPDX-2.2")), True),
        "spdxVersion missing": (edit(lambda d: d.pop("spdxVersion")), True),
        "dataLicense MIT": (edit(lambda d: d.update(dataLicense="MIT")), True),
        "SPDXID not SPDXRef-DOCUMENT": (edit(lambda d: d.update(SPDXID="SPDXRef-DOC")), True),
        "name empty": (edit(lambda d: d.update(name="")), True),
        "namespace an https URL": (edit(lambda d: d.update(
            documentNamespace="https://spdx.knowledge-engine.invalid/" + "0" * 40
                              + "/amd64/valkey/0f8fad5b-d9cb-469f-a165-70867728950e")), True),
        "namespace upper-case hex": (edit(lambda d: d.update(documentNamespace=VALID_NAMESPACE.upper()
                                                             .replace("URN:UUID:", "urn:uuid:"))), True),
        "namespace a version-1 uuid": (edit(lambda d: d.update(
            documentNamespace=VALID_NAMESPACE.replace("-469f-", "-169f-"))), True),
        "namespace a non-RFC-4122 variant": (edit(lambda d: d.update(
            documentNamespace=VALID_NAMESPACE.replace("-a165-", "-c165-"))), True),
        "namespace with a '#'": (edit(lambda d: d.update(documentNamespace=VALID_NAMESPACE + "#x")), True),
        "namespace with a trailing newline": (edit(lambda d: d.update(documentNamespace=VALID_NAMESPACE + "\n")),
                                              True),
        "namespace a bare uuid": (edit(lambda d: d.update(documentNamespace=VALID_NAMESPACE[len("urn:uuid:"):])),
                                  True),
        "namespace missing": (edit(lambda d: d.pop("documentNamespace")), True),
        "created not RFC 3339": (edit(lambda d: d["creationInfo"].update(created="2026-10-23 10:00:00")), True),
        "created not UTC": (edit(lambda d: d["creationInfo"].update(created="2026-10-23T10:00:00+02:00")), True),
        "creators without Tool: syft-": (edit(lambda d: d["creationInfo"].update(
            creators=["Organization: Anchore, Inc"])), True),
        "creationInfo missing": (edit(lambda d: d.pop("creationInfo")), True),
        "duplicate package SPDXID": (edit(lambda d: rename(d, pkg2, pkg1)), True),
        "package SPDXID with an underscore": (edit(lambda d: rename(d, pkg2, "SPDXRef-a_b")), True),
        "valid, package renamed to a good id": (edit(lambda d: rename(d, pkg2, "SPDXRef-Package-ok-1.2")), False),
        "package without name": (edit(lambda d: d["packages"][1].pop("name")), True),
        "package without downloadLocation": (edit(lambda d: d["packages"][1].pop("downloadLocation")), True),
        "no DESCRIBES": (edit(lambda d: d.update(relationships=[r for r in d["relationships"]
                                                                 if r["relationshipType"] != DESCRIBES])), True),
        "two DESCRIBES": (edit(lambda d: d["relationships"].append(
            {"spdxElementId": "SPDXRef-DOCUMENT", "relatedSpdxElement": pkg1, "relationshipType": DESCRIBES})), True),
        "relationship to an unknown id": (edit(lambda d: d["relationships"].append(
            {"spdxElementId": pkg1, "relatedSpdxElement": "SPDXRef-nope", "relationshipType": "CONTAINS"})), True),
        "relationship from an unknown id": (edit(lambda d: d["relationships"].append(
            {"spdxElementId": "SPDXRef-nope", "relatedSpdxElement": pkg1, "relationshipType": "CONTAINS"})), True),
        "not an object": ([], True),
    }


# --------------------------------------------------------------------------
# PSC-13: scripts/sbom_check.py (fast, imported by path)
# --------------------------------------------------------------------------

class SbomCheckModuleTest(unittest.TestCase):

    def test_sbom_is_spdx_2_3(self):
        """N6's validator, table-driven: [] for a valid document, problems
        (never an exception) for each missing or wrong required field."""
        module = load_sbom_check()
        validate = getattr(module, "validate", None)
        self.assertTrue(callable(validate), "scripts/sbom_check.py has no validate(doc) (N6)")
        valid = raw_doc("valkey", "1.54.1")
        valid["documentNamespace"] = VALID_NAMESPACE
        for case, (doc, want_problems) in validate_cases(valid).items():
            with self.subTest(case=case):
                try:
                    got = validate(doc)
                except Exception as exc:  # noqa: BLE001 - the contract is "problems, not exceptions"
                    self.fail(f"validate raised {type(exc).__name__}: {exc}")
                self.assertIsInstance(got, list)
                if want_problems:
                    self.assertTrue(got, f"validate accepted a document with {case}")
                else:
                    self.assertEqual(got, [], f"validate refused a valid document ({case})")

    def _finish(self, *extra: str) -> subprocess.CompletedProcess:
        """`finish` run directly (no docker) on a raw document and an image tar.
        Architect's N6 amendment: no `--uuid`; the namespace is a fresh uuid4."""
        if not SBOM_CHECK.is_file():
            self.fail(CHECK_MISSING)
        import tempfile
        work = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, work, True)
        raw = work / "raw.spdx.json"
        raw.write_text(json.dumps(raw_doc("valkey", "1.54.1")), encoding="utf-8")
        tar_path = work / "valkey.tar"
        import io
        with tarfile.open(tar_path, "w") as tar:
            data = json.dumps([{"Config": "blobs/sha256/" + "b" * 64, "RepoTags": ["x:y"], "Layers": []}]).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        argv = [sys.executable, "-I", str(SBOM_CHECK), "finish", "--name", "valkey",
                "--ref", "valkey/valkey:8@sha256:" + "c" * 64, "--arch", "amd64", "--git-sha", "d" * 40,
                "--raw", str(raw), "--tar", str(tar_path), *extra]
        return subprocess.run(argv, capture_output=True, text=True, timeout=60)

    def test_finish_namespace_is_fresh_per_run(self):
        runs = [self._finish() for _ in range(2)]
        spaces = []
        for i, done in enumerate(runs):
            with self.subTest(run=i):
                self.assertEqual(done.returncode, 0, done.stderr)
                ns = json.loads(done.stdout).get("documentNamespace") if done.returncode == 0 else None
                self.assertTrue(NAMESPACE_RE.fullmatch(str(ns)), f"namespace {ns!r} is not urn:uuid:<uuid4>")
                spaces.append(ns)
        self.assertNotEqual(spaces[0], spaces[1], "two finish runs gave the same namespace")

    def test_finish_refuses_uuid_option(self):
        with self.subTest(part="precondition: the same command without --uuid succeeds"):
            ok = self._finish()
            self.assertEqual(ok.returncode, 0, ok.stderr)
        with self.subTest(part="--uuid is an unknown option (exit 2)"):
            done = self._finish("--uuid", "0f8fad5b-d9cb-469f-a165-70867728950e")
            self.assertEqual(done.returncode, 2, f"finish accepted --uuid (N6 amendment): {done.stderr}")
            self.assertIn("--uuid", done.stderr, "the error names the unknown option")
            self.assertEqual(done.stdout, "", "no document is printed")

    def test_sbom_check_is_stdlib_and_never_shipped(self):
        with self.subTest(part="present"):
            self.assertTrue(SBOM_CHECK.is_file(), CHECK_MISSING)
        with self.subTest(part="standard library only, a script with validate()"):
            source = SBOM_CHECK.read_text(encoding="utf-8") if SBOM_CHECK.is_file() else ""
            self.assertEqual(stdlib_problems(source) if source else [CHECK_MISSING], [])
        with self.subTest(part="never shipped, never imported by the product"):
            self.assertEqual(shipped_problems(ROOT), [])


# --------------------------------------------------------------------------
# Static: the compose files and offline_check.sh
# --------------------------------------------------------------------------

class SbomStaticU3Test(unittest.TestCase):

    def test_sbom_generator_runs_as_caller(self):
        self.assertTrue(SBOM_COMPOSE.is_file(), "docker-compose.sbom.yml is missing")
        with self.subTest(part="user: ${KE_SBOM_USER:?...}"):
            self.assertEqual(user_problems(cs.load(SBOM_COMPOSE)), [])
        with self.subTest(part="KE_SBOM_USER is a required variable of the file"):
            self.assertIn("KE_SBOM_USER", cs.required_vars(SBOM_COMPOSE))

    def test_compose_files_have_no_include_or_extends(self):
        for path, allowed in ((SBOM_COMPOSE, {"services"}), (SCAN_COMPOSE, {"services", "volumes"})):
            with self.subTest(file=path.name):
                self.assertTrue(path.is_file(), f"{path.name} is missing")
                text = path.read_text(encoding="utf-8")
                self.assertEqual(top_level_problems(cs.load(path), text, path.name, allowed), [])

    def test_offline_check_header_names_sbom_pull(self):
        self.assertEqual(offline_header_problems(OFFLINE_CHECK.read_text(encoding="utf-8")), [])


# --------------------------------------------------------------------------
# PSC-13: bundle.sh against the fake docker
# --------------------------------------------------------------------------

def _pairs(argv: list[str]) -> set[tuple[str, str]]:
    out = set(zip(argv, argv[1:]))
    out |= {tuple(a.split("=", 1)) for a in argv if a.startswith("--") and "=" in a}  # type: ignore[misc]
    return out


def compose_split(argv: list[str]) -> tuple[set[tuple[str, str]], list[str], str | None, list[str]]:
    """(global option pairs, other global tokens, subcommand, the rest) of a
    `compose ...` call."""
    globs: set[tuple[str, str]] = set()
    extras: list[str] = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in GLOBAL_OPTS and i + 1 < len(argv):
            globs.add((GLOBAL_OPTS[a], argv[i + 1]))
            i += 2
            continue
        if "=" in a and a.split("=", 1)[0] in GLOBAL_OPTS:
            k, v = a.split("=", 1)
            globs.add((GLOBAL_OPTS[k], v))
            i += 1
            continue
        if a.startswith("-"):
            extras.append(a)
            i += 1
            continue
        return globs, extras, a, argv[i + 1:]
    return globs, extras, None, []


def names_sbom_file(argv: list[str]) -> bool:
    if argv[:1] != ["compose"]:
        return False
    globs, _, _, _ = compose_split(argv)
    return any(k == "-f" and Path(v).name == cs.SBOM_COMPOSE_NAME for k, v in globs)


def run_option_problems(rest: list[str], name: str) -> list[str]:
    """`run` options, then `sbom` and the exact syft arguments."""
    p = []
    if "sbom" not in rest:
        return [f"the run names no `sbom` service: {rest}"]
    at = rest.index("sbom")
    opts, tail = rest[:at], rest[at + 1:]
    if "--rm" not in opts:
        p.append("the generator run lacks --rm")
    pull = ("--pull", "never") in _pairs(opts)
    if not pull:
        p.append("the generator run lacks --pull never (PSC-20: bundle.sh never pulls)")
    extra = []
    i = 0
    while i < len(opts):
        a = opts[i]
        if a == "--rm" or a == "--pull=never":
            i += 1
            continue
        if a == "--pull" and i + 1 < len(opts) and opts[i + 1] == "never":
            i += 2
            continue
        if a not in RUN_OPTS_ALLOWED:
            extra.append(a)
        i += 1
    if extra:
        p.append(f"the generator run passes {extra}; only --rm, --pull never and {sorted(RUN_OPTS_ALLOWED)} "
                 "are allowed (mounts, user and environment come from the compose file)")
    if tail != run_tail(name):
        p.append(f"the syft arguments are {tail}, want exactly {run_tail(name)} (N1)")
    return p


def _checker_subcommand(argv: list[str]) -> str | None:
    """The word after the last `.../sbom_check.py` in a `docker run` argv."""
    at = [i for i, a in enumerate(argv) if a.replace("\\", "/").rsplit("/", 1)[-1] == "sbom_check.py"]
    return argv[at[-1] + 1] if at and at[-1] + 1 < len(argv) else None


def finish_run_problems(argv: list[str], app_refs: set[str], repo: Path) -> list[str]:
    """N3: the checker's `docker run` in the ke-app image."""
    p = []
    pairs = _pairs(argv)
    if "--rm" not in argv:
        p.append("the checker run lacks --rm")
    if not ({("--network", "none"), ("--net", "none")} & pairs):
        p.append("the checker run lacks --network none")
    if "--read-only" not in argv:
        p.append("the checker run lacks --read-only")
    if not ({("--cap-drop", "ALL"), ("--cap-drop", "all")} & pairs):
        p.append("the checker run lacks --cap-drop ALL")
    if not ({("--security-opt", "no-new-privileges"), ("--security-opt", "no-new-privileges:true"),
             ("--security-opt", "no-new-privileges=true")} & pairs):
        p.append("the checker run lacks --security-opt no-new-privileges")
    if ("--pull", "never") not in pairs:
        p.append("the checker run lacks --pull never")
    labels = [b for a, b in zip(argv, argv[1:]) if a in ("--label", "-l")]
    labels += [a.split("=", 1)[1] for a in argv if a.startswith("--label=")]
    if CHECK_LABEL not in labels:
        p.append(f"the checker run lacks --label {CHECK_LABEL} (its own label, N3): {labels}")
    if not ({("--entrypoint", "python"), ("--entrypoint", "python3")} & pairs):
        p.append("the checker run lacks --entrypoint python")
    if any(a in ("--privileged", "--cap-add") or a.startswith(("--cap-add=", "--privileged=")) for a in argv):
        p.append("the checker run adds privileges")
    mounts = [b for a, b in zip(argv, argv[1:]) if a in ("-v", "--volume", "--mount")]
    mounts += [a.split("=", 1)[1] for a in argv if a.startswith(("--volume=", "--mount="))]
    for m in mounts:
        if "docker.sock" in m or "docker_engine" in m:
            p.append(f"the checker run mounts the Docker socket: {m}")
        ro = m.endswith((":ro", ":ro,z", ":ro,Z")) or ",readonly" in m or ",ro" in m or m.startswith("ro,")
        if not ro:
            p.append(f"the checker run has a writable mount: {m} (every mount is read-only, N3)")
    script = [m for m in mounts if m.split(":", 1)[0].replace("\\", "/").endswith("/scripts/sbom_check.py")]
    if not script:
        p.append("the checker run does not mount <checkout>/scripts/sbom_check.py")
    else:
        src = script[0].split(":", 1)[0]
        if Path(src).resolve() != (repo / "scripts" / "sbom_check.py").resolve():
            p.append(f"the checker is mounted from {src}, not the checkout's scripts/sbom_check.py")
    images = [a for a in argv if a in app_refs]
    if not images:
        p.append(f"the checker does not run in the ke-app image being bundled ({sorted(app_refs)})")
    else:
        tail = argv[argv.index(images[0]) + 1:]
        at = [i for i, a in enumerate(tail) if a.replace("\\", "/").rsplit("/", 1)[-1] == "sbom_check.py"]
        if not at:
            p.append(f"no sbom_check.py after the image: {tail}")
        else:
            if "-I" not in tail[:at[0]]:
                p.append(f"python runs the checker without -I (isolated mode, N3): {tail[:at[0] + 1]}")
            if tail[at[0] + 1:at[0] + 2] != ["finish"]:
                p.append(f"the checker subcommand is {tail[at[0] + 1:at[0] + 2]}, want finish (N3)")
    return p


class SbomBundleRunTest(_BundleBase, unittest.TestCase):
    """bundle.sh writes one SBOM per image through syft (fake) and the
    checker (the real scripts/sbom_check.py, run by the fake docker)."""

    def setUp(self) -> None:
        super().setUp()
        self.user = subprocess.run(["bash", "-c", 'printf "%s:%s" "$(id -u)" "$(id -g)"'],
                                   capture_output=True, text=True, check=True).stdout
        self.syft_version = pinned_syft_version()

    def _run(self, **kw: Any) -> tuple[subprocess.CompletedProcess, list[dict], Path, list[dict]]:
        log = self.tmp / f"syft-{self.n + 1}.jsonl"
        kw.setdefault("COMPOSE_PROJECT_NAME", PROJECT)
        kw.setdefault("FAKE_SYFT_LOG", str(log))
        result, _, out = self._bundle(**kw)
        recs = fake_docker.records(self.json)
        syft = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return result, recs, out, syft

    def _good(self, **kw: Any) -> tuple[list[dict], Path, dict[str, Any], list[dict]]:
        result, recs, out, syft = self._run(**kw)
        self.assertEqual(result.returncode, 0, "bundle.sh failed on a fit build host:\n" + self._out(result))
        return recs, out, json.loads((out / "bundle.json").read_text(encoding="utf-8")), syft

    @staticmethod
    def _images(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {Path(e["file"]).stem: e for e in data.get("images", [])}

    def _doc(self, out: Path, name: str) -> dict[str, Any]:
        path = out / "app" / "sboms" / f"{name}.spdx.json"
        self.assertTrue(path.is_file(), f"no app/sboms/{name}.spdx.json (PSC-13; ADR-KE-016 point 6)")
        return json.loads(path.read_text(encoding="utf-8"))

    def _app_refs(self) -> set[str]:
        refs = {r for r in self.stack.values() if r.split("@")[0].rsplit(":", 1)[0].rsplit("/", 1)[-1] == "ke-app"}
        return refs | {f"ke-app:bundle-{self.sha[:12]}"}

    def _no_bundle(self, result: subprocess.CompletedProcess, out: Path, names: str) -> None:
        self.assertNotEqual(result.returncode, 0, "bundle.sh passed:\n" + self._out(result))
        self.assertFalse((out / "MANIFEST.sha256").exists(), "a MANIFEST.sha256 was written after an SBOM failure")
        self.assertFalse(Path(str(out) + ".manifest.sha256").exists(), "a release record was written")
        self.assertNotIn("bundle written", result.stdout)
        self.assertRegex(result.stderr, names, "the refusal must name the image (PSC-24 form)")

    def _downs_after_runs(self, recs: list[dict]) -> list[str]:
        """Review N1: the teardown targets <project>-sbom with --env-file and
        every ${VAR:?} of the file set; it follows the last run."""
        p = []
        runs = [i for i, r in enumerate(recs) if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "run"]
        downs = [i for i, r in enumerate(recs) if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "down"]
        if not downs or (runs and max(downs) < max(runs)):
            return [f"no `compose -p {SBOM_PROJECT} -f docker-compose.sbom.yml down` after the last generator run"]
        required = set(cs.required_vars(SBOM_COMPOSE)) | {"KE_SBOM_IN", "KE_SBOM_OUT", "KE_SBOM_USER"}
        for i in downs:
            globs, extras, _, rest = compose_split(recs[i]["argv"])
            if globs != WANT_GLOBALS or extras:
                p.append(f"the down's global options are {sorted(globs)} {extras}, want {sorted(WANT_GLOBALS)}")
            if [a for a in rest if a not in DOWN_OPTS_ALLOWED]:
                p.append(f"the down passes {rest}")
            missing = sorted(v for v in required if not recs[i]["env"].get(v))
            if missing:
                p.append(f"the down runs with {missing} unset or empty (compose refuses the file)")
        return p

    # ---- PSC-13 bullet 1, 3: one document per image, listed, annotated --------

    def test_bundle_has_sbom_per_image(self):
        recs, out, data, _ = self._good()
        images = self._images(data)
        self.assertTrue(images, "precondition: bundle.json lists images")
        sboms = out / "app" / "sboms"
        with self.subTest(part="one app/sboms/<name>.spdx.json per bundle.json image, nothing else"):
            got = sorted(p.name for p in sboms.iterdir()) if sboms.is_dir() else []
            self.assertEqual(got, sorted(f"{n}.spdx.json" for n in images))
        listed = {}
        if (out / "MANIFEST.sha256").is_file():
            for line in (out / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
                h, _, rel = line.partition("  ")
                listed[rel] = h
        for name, entry in sorted(images.items()):
            rel = f"app/sboms/{name}.spdx.json"
            with self.subTest(image=name, part="listed in MANIFEST.sha256 with its hash"):
                self.assertTrue(rel in listed, f"{rel} is not in MANIFEST.sha256")
                if (out / rel).is_file() and rel in listed:
                    self.assertEqual(listed[rel], hashlib.sha256((out / rel).read_bytes()).hexdigest())
            with self.subTest(image=name, part="names its ref, arch and the tar's config digest (ruling 1)"):
                doc = self._doc(out, name)
                self.assertEqual(doc.get("name"), entry["ref"], "document name is the bundle.json ref (N6)")
                values, problems = annotation_problems(doc, self.sha)
                self.assertEqual(problems, [])
                self.assertEqual(values.get("ref"), entry["ref"])
                self.assertEqual(values.get("arch"), data["arch"])
                want = tar_config_digest(out / entry["file"])
                self.assertEqual(values.get("image-config"), want,
                                 "ke:image-config is the tar's manifest.json Config digest, not an image ID")
                self.assertNotEqual(want, self._images_table(self.stack)[entry["ref"]]["Id"],
                                    "precondition: the fake's config digest differs from the daemon's Id")
        with self.subTest(part="no checker, raw document or unpack file is shipped"):
            stray = [_rel(p, out) for p in out.rglob("*")
                     if p.name in ("sbom_check.py", "raw.spdx.json") or "stereoscope" in _rel(p, out)]
            self.assertEqual(stray, [])
        with self.subTest(part="legacy save layout (Config <hex>.json)"):
            _, out2, data2, _ = self._good(FAKE_DOCKER_SAVE_TAR="legacy")
            for name, entry in sorted(self._images(data2).items()):
                values, _ = annotation_problems(self._doc(out2, name), self.sha)
                self.assertEqual(values.get("image-config"), tar_config_digest(out2 / entry["file"]), name)
        with self.subTest(part="arm64 daemon: each SBOM records arm64 (PSC-21)"):
            images3 = self._images_table(self.stack, default="arm64")
            _, out3, data3, _ = self._good(FAKE_DOCKER_ARCH="aarch64", images=images3)
            self.assertEqual(data3.get("arch"), "arm64")
            for name, entry in sorted(self._images(data3).items()):
                doc = self._doc(out3, name)
                values, _ = annotation_problems(doc, self.sha)
                self.assertEqual(values.get("arch"), "arm64", name)
        with self.subTest(part="a tar whose manifest.json holds two images is refused"):
            result, _, out4, _ = self._run(FAKE_DOCKER_SAVE_TAR="two")
            self._no_bundle(result, out4, "|".join(re.escape(n) for n in images))

    # ---- PSC-13 bullet 4: SPDX 2.3 required fields, N6 ------------------------

    def test_sbom_is_spdx_2_3(self):
        recs, out, data, _ = self._good()
        images = self._images(data)
        spaces = []
        for name, entry in sorted(images.items()):
            with self.subTest(image=name):
                doc = self._doc(out, name)
                self.assertEqual(document_problems(doc, ref=entry["ref"], arch=data["arch"], name=name,
                                                   git_sha=self.sha, syft_version=self.syft_version), [])
                spaces.append(doc.get("documentNamespace"))
                if SBOM_CHECK.is_file():
                    self.assertEqual(load_sbom_check().validate(doc), [], "validate() refuses the shipped SBOM")
        with self.subTest(part="namespace: distinct across the bundle's documents"):
            self.assertEqual(len(set(spaces)), len(spaces), f"two documents share a namespace: {spaces}")
        with self.subTest(part="namespace: a second run of the same tree gives new ones"):
            _, out2, _, _ = self._good()
            again = [self._doc(out2, name).get("documentNamespace") for name in sorted(images)]
            self.assertEqual(sorted(set(again) & set(spaces)), [], "a namespace repeats on a second run")
        with self.subTest(part="finish changes only name, namespace, creators and annotations (N6)"):
            raw = raw_doc("valkey", self.syft_version)
            self.assertIn("valkey", images, "precondition: valkey is a bundled image")
            # platform-sbom U9b (design item 14 *Controls*): the synthetic lock covers this document too.
            self._relock_for({"valkey": raw})
            _, out3, _, _ = self._good(FAKE_SYFT_RAW=json.dumps({"valkey": json.dumps(raw)}))
            doc = self._doc(out3, "valkey")
            for key in sorted(set(raw) | set(doc)):
                if key in ("name", "documentNamespace", "creationInfo", "annotations"):
                    continue
                self.assertEqual(doc.get(key), raw.get(key), f"finish changed `{key}`")
            info, raw_info = doc.get("creationInfo") or {}, raw["creationInfo"]
            for c in raw_info["creators"]:
                self.assertIn(c, info.get("creators") or [], "finish dropped a syft creator")
            for key in raw_info:
                if key != "creators":
                    self.assertEqual(info.get(key), raw_info[key], f"finish changed creationInfo.{key}")

    # ---- PSC-13 bullet 5: ke-app's runtime packages ---------------------------

    def test_sbom_lists_every_locked_runtime_package(self):
        expected = locked_runtime_packages()
        with self.subTest(part="precondition: the PSC-13 set from uv.lock"):
            self.assertIn("psycopg-c", expected, "psycopg-c is a runtime package (PSC-25)")
            self.assertIn("psycopg", expected)
            for name, version in expected.items():
                self.assertEqual(self.packages.get(name), version,
                                 f"the fake venv lacks {name} {version} (tests/test_offline_bundle.py _make_site)")
        _, out, _, _ = self._good()
        doc = self._doc(out, "ke-app")
        pypi = {_norm(n): v for t, n, v in purls(doc) if t == "pypi"}
        for name, version in sorted(expected.items()):
            with self.subTest(package=name):
                self.assertEqual(pypi.get(_norm(name)), version,
                                 f"ke-app's SBOM does not list pkg:pypi/{name}@{version}")
        for case, env, word in (
                ("syft misses psycopg-c", {"FAKE_SYFT_DROP": "psycopg-c"}, "psycopg-c"),
                ("syft misses PyYAML (spelled as its METADATA)", {"FAKE_SYFT_DROP": "pyyaml"}, "(?i)pyyaml"),
                ("syft reports another httpx version", {"FAKE_SYFT_PYPI_VERSIONS": json.dumps({"httpx": "0.0.1"})},
                 "httpx")):
            with self.subTest(case=f"refused: {case}"):
                result, _, out2, _ = self._run(**env)
                self._no_bundle(result, out2, "ke-app")
                self.assertRegex(result.stderr, word, "the refusal names the package (N7)")

    # ---- reviewer's condition: the exact run, its project and teardown ---------

    def test_sbom_generator_run_is_pinned(self):
        recs, out, data, syft = self._good()
        images = self._images(data)
        sbom_recs = [(i, r) for i, r in enumerate(recs) if names_sbom_file(r["argv"])]
        with self.subTest(part="compose subcommands on the file: config, run, down"):
            subs = sorted({compose_split(r["argv"])[2] or "" for _, r in sbom_recs})
            self.assertEqual([s for s in subs if s not in SBOM_SUBCOMMANDS], [], subs)
        runs = [(i, r) for i, r in sbom_recs if compose_split(r["argv"])[2] == "run"]
        with self.subTest(part="one generator run per image"):
            named = sorted(next((a[len("docker-archive:/in/"):-4] for a in r["argv"]
                                 if a.startswith("docker-archive:/in/")), "?") for _, r in runs)
            self.assertEqual(named, sorted(images))
        outs = []
        for i, r in runs:
            argv, env = r["argv"], r["env"]
            name = next((a[len("docker-archive:/in/"):-4] for a in argv if a.startswith("docker-archive:/in/")), "?")
            globs, extras, _, rest = compose_split(argv)
            with self.subTest(image=name, part="argv"):
                self.assertEqual((sorted(globs), extras), (sorted(WANT_GLOBALS), []),
                                 "want -p <project>-sbom --env-file .env.example -f docker-compose.sbom.yml")
                self.assertEqual(run_option_problems(rest, name), [])
            with self.subTest(image=name, part="KE_SBOM_IN is the bundle's images/"):
                self.assertTrue(env.get("KE_SBOM_IN"), "KE_SBOM_IN is not set for the run")
                if env.get("KE_SBOM_IN"):
                    self.assertEqual(Path(env["KE_SBOM_IN"]).resolve(), (out / "images").resolve())
            with self.subTest(image=name, part="KE_SBOM_OUT: a work dir outside --out, removed afterwards"):
                work = env.get("KE_SBOM_OUT", "")
                self.assertTrue(work and Path(work).is_absolute(), f"KE_SBOM_OUT is {work!r}")
                if work:
                    w = Path(work).resolve()
                    self.assertNotIn(out.resolve(), [w, *w.parents], "the work dir is inside --out")
                    self.assertFalse(Path(work).exists(), "the work dir was left behind")
                    outs.append(w)
            with self.subTest(image=name, part="KE_SBOM_USER is the caller's uid:gid (security L-2)"):
                self.assertEqual(env.get("KE_SBOM_USER"), self.user)
            with self.subTest(image=name, part="after the image's save"):
                saves = [j for j, s in enumerate(recs) if s["argv"][:1] == ["save"]
                         and any(a.endswith(f"/images/{name}.tar") for a in s["argv"])]
                self.assertTrue(saves and saves[0] < i, "the generator ran before the image was saved")
        with self.subTest(part="a fresh work dir per image (only an empty tmp/ when syft starts)"):
            self.assertEqual(len(set(outs)), len(outs), "two images share a work dir")
            for entry in syft:
                self.assertEqual((entry.get("out_entries"), entry.get("tmp_entries")), (["tmp"], []),
                                 f"{entry.get('name')}: the work dir held {entry.get('out_entries')} "
                                 f"(tmp: {entry.get('tmp_entries')}) when syft started")
        with self.subTest(part="project <project>-sbom, distinct from the stack's and the notices run's"):
            self.assertNotIn(SBOM_PROJECT, (PROJECT, f"{PROJECT}-notices"))
        with self.subTest(part="teardown (review N1)"):
            self.assertEqual(self._downs_after_runs(recs), [])
        # platform-sbom U9b (tester, U9b RED; contradiction resolved here, design-notes "N9
        # amendment, U9" item 1): `sources-check`, `index` and `notices` also run sbom_check.py in
        # the ke-app image, so this count is of the `finish` runs (the subcommand after the
        # script); tests/test_bundle_sources.py pins the three new runs' hardening.
        checks = [(i, r) for i, r in enumerate(recs) if r["argv"][:1] == ["run"]
                  and any(a.replace("\\", "/").rsplit("/", 1)[-1] == "sbom_check.py" for a in r["argv"])
                  and _checker_subcommand(r["argv"]) == "finish"]
        with self.subTest(part="one checker run per image, after its generator run"):
            self.assertEqual(len(checks), len(images), [c["argv"] for _, c in checks])
            for name in images:
                gen = [i for i, r in runs if f"docker-archive:/in/{name}.tar" in r["argv"]]
                fin = [i for i, c in checks if any(f"/{name}.tar" in a or a == name for a in c["argv"])]
                self.assertTrue(gen and fin and gen[0] < fin[0], f"{name}: no checker run after its generator run")
        for _, c in checks:
            with self.subTest(part="checker run hardening (N3)", argv=" ".join(c["argv"])[:120]):
                self.assertEqual(finish_run_problems(c["argv"], self._app_refs(), self.repo), [])

    # ---- review N2, PSC-21: the generator is the daemon's arch ----------------

    def test_sbom_generator_is_daemon_arch(self):
        for case, daemon, stack_arch, gen_arch in (("amd64 daemon, arm64 generator", "x86_64", "amd64", "arm64"),
                                                   ("arm64 daemon, amd64 generator", "aarch64", "arm64", "amd64")):
            with self.subTest(case=case):
                images = self._images_table(self.stack, default=stack_arch)
                images[self.sbom_ref] = dict(images[self.sbom_ref], Architecture=gen_arch)
                result, recs, out, _ = self._run(FAKE_DOCKER_ARCH=daemon, images=images)
                calls = [r["argv"] for r in recs]
                self._assert_no_bundle(result, calls, out, self.sbom_ref)
                self.assertIn(f"linux/{stack_arch}", result.stderr, "the refusal names the daemon's platform")
                self.assertFalse(out.exists() and any(out.iterdir()), "--out was written before the refusal")
                self.assertFalse(Path(str(out) + ".manifest.sha256").exists())
                self.assertEqual([c for c in calls if c[:1] == ["tag"]], [], "tagged before the refusal")
                self.assertEqual([c for c in calls if names_sbom_file(c) and compose_split(c)[2] == "run"], [])

    # ---- security I-1: a reference may not start with `-` ---------------------

    def test_bundle_refuses_ref_starting_with_dash(self):
        dash_gen = "-anchore/syft:v1.54.1@sha256:" + hashlib.sha256(b"dash").hexdigest()
        stack = dict(self.stack)
        pg_svc = next(s for s, r in stack.items() if "postgres" in r)
        dash_pg = "-" + stack[pg_svc]
        for case, kw, ref in (
                ("generator", {"FAKE_COMPOSE_FILE_IMAGES": json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": dash_gen}})},
                 dash_gen),
                ("stack image", {"stack": dict(stack, **{pg_svc: dash_pg})}, dash_pg)):
            with self.subTest(case=case):
                images = self._images_table(self.stack)
                images[ref] = dict(images[self.sbom_ref])
                result, recs, out, _ = self._run(images=images, **kw)
                self.assertNotEqual(result.returncode, 0, self._out(result))
                self.assertIn("fails its pattern", result.stderr, "ref_re refuses a leading '-' (security I-1)")
                self.assertEqual([r["argv"] for r in recs if ref in r["argv"]], [],
                                 "a '-'-led reference reached a docker call")
                self.assertFalse(out.exists() and any(out.iterdir()), "--out was written")

    # ---- PSC-24's spirit, the part U3 owns -------------------------------------

    def test_bundle_refuses_on_sbom_failure(self):
        # Platform-sbom U4b (PSC-26 *Bundled as first-party*): the neo4j service's image is
        # saved as ke-neo4j (images/ke-neo4j.tar, app/sboms/ke-neo4j.spdx.json); re-targeted
        # by the tester, U4b RED.
        bad22 = raw_doc("ke-neo4j", self.syft_version)
        bad22["spdxVersion"] = "SPDX-2.2"
        dangling = raw_doc("ke-neo4j", self.syft_version)
        dangling["relationships"].append({"spdxElementId": dangling["packages"][1]["SPDXID"],
                                          "relatedSpdxElement": "SPDXRef-nope", "relationshipType": "CONTAINS"})
        cases = {
            "syft fails for ke-neo4j": {"FAKE_DOCKER_FAIL": "docker-archive:/in/ke-neo4j.tar"},
            "ke-neo4j's raw document is not JSON": {"FAKE_SYFT_RAW": json.dumps({"ke-neo4j": "{"})},
            "ke-neo4j's raw document is empty": {"FAKE_SYFT_RAW": json.dumps({"ke-neo4j": ""})},
            "ke-neo4j's raw document is SPDX-2.2": {"FAKE_SYFT_RAW": json.dumps({"ke-neo4j": json.dumps(bad22)})},
            "ke-neo4j's raw document has a dangling relationship":
                {"FAKE_SYFT_RAW": json.dumps({"ke-neo4j": json.dumps(dangling)})},
        }
        for case, env in cases.items():
            with self.subTest(case=case):
                result, recs, out, _ = self._run(**env)
                self._no_bundle(result, out, "ke-neo4j")
                self.assertEqual(self._downs_after_runs(recs), [], "the teardown runs on a failure too")
                for r in recs:
                    if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "run":
                        work = r["env"].get("KE_SBOM_OUT", "")
                        self.assertFalse(work and Path(work).exists(), f"work dir {work} left after the failure")


if __name__ == "__main__":
    unittest.main()
