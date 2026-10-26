"""platform-sbom U4 (PSC-22): SPDX stand-ins shared by the U4 tests.

Test support only (no tests here). Builds syft-shaped SPDX 2.3 documents from
(purl, licenceDeclared, licenceConcluded) rows, and the ke-app document the
image-side drift check (PSC-14/22, design-notes N7 and N10 B3) accepts:
its dpkg set is the fake generator's base set (tests/fake_docker.py
`_syft_doc`: base-files, libc6) plus ADDED_PACKAGES, libpq5 at the
docker/app.Dockerfile pin (upstream postgresql-<major>), psycopg and
psycopg-c at their uv.lock versions, CPython at the version line 1 of
licenses/CPython-3.12-incorporated.txt names, and no pip.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "docker" / "app.Dockerfile"
LICENCE_FILES = ("licenses/CPython-3.12-incorporated.txt", "licenses/CPython-3.12-HACL.txt",
                 "licenses/CPython-3.12-KaRaMeL.txt")
# What tests/fake_docker.py's generator reports for any image but ke-app.
FAKE_BASE_DEBS = (("base-files", "12.4+deb12u13", "GPL-2.0-or-later"),
                  ("libc6", "2.36-9+deb12u13", "GPL-2.0-only AND LGPL-2.1-only"))
DESCRIBES = "DESCRIBES"


def _sid(prefix: str, *parts: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9.-]", "-", parts[0])
    return f"SPDXRef-{prefix}-{stem}-{hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]}"


def spdx_doc(name: str, rows: list[dict[str, Any]], *, syft_version: str = "1.54.1",
             root_licence: str = "NOASSERTION") -> dict[str, Any]:
    """A syft-shaped SPDX 2.3 document for image `name`.

    Each row: {"purl": str|None, "name": str?, "declared": str|None (None =
    key absent), "concluded": str|None, "files": list|None
    (licenseInfoFromFiles), "spdxid": str?}. The root package (the image)
    is DESCRIBED by the document and CONTAINS every row."""
    root_id = "SPDXRef-DocumentRoot-Image-" + re.sub(r"[^A-Za-z0-9.-]", "-", name)
    root = {"name": f"/in/{name}.tar", "SPDXID": root_id, "versionInfo": "sha256:" + "e" * 64,
            "supplier": "NOASSERTION", "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
            "licenseConcluded": root_licence, "licenseDeclared": root_licence, "copyrightText": "NOASSERTION",
            "primaryPackagePurpose": "CONTAINER",
            "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                              "referenceLocator": f"pkg:oci/%2Fin%2F{name}.tar@sha256%3A{'e' * 64}?arch=amd64"}]}
    pkgs: list[dict[str, Any]] = [root]
    rels = [{"spdxElementId": "SPDXRef-DOCUMENT", "relatedSpdxElement": root_id, "relationshipType": DESCRIBES}]
    for i, row in enumerate(rows):
        purl = row.get("purl")
        m = re.match(r"^pkg:[^/]+/(?:.*/)?([^/@?#]+)@([^?#]+)", purl or "")
        pname = row.get("name") or (m.group(1) if m else "UNKNOWN")
        version = m.group(2) if m else "UNKNOWN"
        sid = row.get("spdxid") or _sid("Package", pname, str(purl), str(i))
        pkg: dict[str, Any] = {"name": pname, "SPDXID": sid, "versionInfo": version, "supplier": "NOASSERTION",
                               "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                               "copyrightText": "NOASSERTION"}
        if row.get("declared", "NOASSERTION") is not None:
            pkg["licenseDeclared"] = row.get("declared", "NOASSERTION")
        if row.get("concluded", "NOASSERTION") is not None:
            pkg["licenseConcluded"] = row.get("concluded", "NOASSERTION")
        if row.get("files") is not None:
            pkg["licenseInfoFromFiles"] = row["files"]
        if purl:
            pkg["externalRefs"] = [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                                    "referenceLocator": purl}]
        pkgs.append(pkg)
        rels.append({"spdxElementId": root_id, "relatedSpdxElement": sid, "relationshipType": "CONTAINS"})
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"/in/{name}.tar",
            "documentNamespace": "urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e",
            "creationInfo": {"licenseListVersion": "3.27",
                             "creators": ["Organization: Anchore, Inc", f"Tool: syft-{syft_version}"],
                             "created": "2026-10-23T10:00:00Z"},
            "packages": pkgs, "relationships": rels}


def deb(name: str, version: str, *, upstream: str | None = None, distro: str = "debian-12.15",
        arch: str = "amd64") -> str:
    q = f"arch={arch}&distro={distro}"
    if upstream:
        q += "&upstream=" + quote(upstream, safe="")
    return f"pkg:deb/debian/{name}@{quote(version, safe='')}?{q}"


def pypi(name: str, version: str) -> str:
    return f"pkg:pypi/{name}@{quote(version, safe='')}"


# --------------------------------------------------------------------------
# The committed values the image-side check compares against
# --------------------------------------------------------------------------

def added_packages() -> frozenset[str]:
    from tests.test_notice_ke_app import ADDED_PACKAGES
    return ADDED_PACKAGES


def libpq_pin() -> str:
    m = re.search(r"(?m)^\s*ARG\s+LIBPQ_VERSION=(\S+)\s*$", DOCKERFILE.read_text(encoding="utf-8"))
    assert m, "docker/app.Dockerfile has no ARG LIBPQ_VERSION= (platform-sbom U0)"
    return m.group(1).strip("\"'")


def locked_version(name: str, lock: Path | None = None) -> str:
    data = tomllib.loads((lock or ROOT / "uv.lock").read_text(encoding="utf-8"))
    found = [p["version"] for p in data["package"] if p["name"] == name]
    assert len(found) == 1, f"uv.lock holds {name} {len(found)} times"
    return found[0]


def licence_version(rel: str = LICENCE_FILES[0], root: Path = ROOT) -> str:
    first = (root / rel).read_text(encoding="utf-8").splitlines()[0]
    m = re.match(r"^CPython (\d+\.\d+\.\d+):", first)
    assert m, f"{rel} line 1 does not start `CPython X.Y.Z:` ({first!r})"
    return m.group(1)


def base_ref() -> str:
    from tests.test_notice_ke_app import runtime_stage
    ref, _, problems = runtime_stage(DOCKERFILE)
    assert not problems, problems
    return ref


def ke_app_rows(*, drop: tuple[str, ...] = (), extra: tuple[dict[str, Any], ...] = (),
                cpython: str | None = None, libpq: str | None = None) -> list[dict[str, Any]]:
    """The rows of a ke-app document the image-side check accepts; `drop`
    removes rows by package name, `extra` adds rows, `cpython` and `libpq`
    replace those versions."""
    pin = libpq if libpq is not None else libpq_pin()
    major = libpq_pin().split(".", 1)[0]
    rows: list[dict[str, Any]] = []
    for n, v, lic in FAKE_BASE_DEBS:
        rows.append({"purl": deb(n, v, upstream="glibc" if n == "libc6" else None), "declared": lic})
    for n in sorted(added_packages()):
        if n == "libpq5":
            rows.append({"purl": deb(n, pin, upstream=f"postgresql-{major}"), "declared": "PostgreSQL"})
        else:
            rows.append({"purl": deb(n, "2.5.13+dfsg-5"), "declared": "GPL-2.0-or-later AND BSD-3-Clause"})
    for n in ("psycopg", "psycopg-c"):
        rows.append({"purl": pypi(n, locked_version(n)), "declared": "LGPL-3.0-only"})
    rows.append({"purl": pypi("httpx", locked_version("httpx")), "declared": "BSD-3-Clause"})
    rows.append({"purl": f"pkg:generic/python@{cpython or licence_version()}", "name": "python",
                 "declared": "NOASSERTION", "concluded": "NOASSERTION"})
    rows = [r for r in rows if not any(re.search(rf"/{re.escape(d)}@", r["purl"] or "") for d in drop)]
    return rows + list(extra)


def ke_app_doc(**kw: Any) -> dict[str, Any]:
    return spdx_doc("ke-app", ke_app_rows(**kw))


def fake_base_doc() -> dict[str, Any]:
    """What tests/fake_docker.py's generator reports for the base tar."""
    return spdx_doc("base", [{"purl": deb(n, v, upstream="glibc" if n == "libc6" else None), "declared": lic}
                             for n, v, lic in FAKE_BASE_DEBS])


def licence_texts(root: Path = ROOT) -> dict[str, str]:
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in LICENCE_FILES}


def write_json(path: Path, doc: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------------------
# Real package lists (U4 rework round 1): what syft 1.54.1 wrote for the six
# bundled images at U3, from fresh images. tests/fixtures/sbom-u3/<image>.pkgs.tsv
# are byte copies of docs/evidence/platform-sbom/u3/sboms/<image>.pkgs.tsv
# (tests read committed fixtures, never docs/evidence). One row per package:
# purl ("-" when syft gave none), versionInfo, licenseDeclared|licenseConcluded.
# The pkg:oci row is the image root, which spdx_doc() adds itself.
# --------------------------------------------------------------------------

U3_FIXTURES = ROOT / "tests" / "fixtures" / "sbom-u3"
U3_IMAGES = ("ke-app", "ke-gateway", "neo4j", "phoenix", "postgres", "valkey")


def u3_rows(image: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (U3_FIXTURES / f"{image}.pkgs.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        purl, _version, licences = line.split("\t")
        if purl.startswith("pkg:oci/"):
            continue
        declared, sep, concluded = licences.partition("|")
        assert sep, f"{image}.pkgs.tsv: no declared|concluded in {line!r}"
        rows.append({"purl": None if purl == "-" else purl, "declared": declared, "concluded": concluded})
    return rows


def u3_doc(image: str) -> dict[str, Any]:
    """A syft-shaped document of one bundled image's real U3 package list."""
    return spdx_doc(image, u3_rows(image))
