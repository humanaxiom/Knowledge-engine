"""platform-sbom U4: an obligation is not hidden by what the generator reports
(PSC-22), the image-side drift check (PSC-14/22, review B3), and the U3 carry
list.

Criteria: docs/requirements.md PSC-22 (tags
`test_named_gpl_components_need_source_whatever_the_generator_says`,
`test_unlicensed_packages_are_reported`, and the two `[full: ...]` checks on
ke-app's SBOM), PSC-14's "U4 adds the image-side check". Design:
ADR-KE-016 points 1, 2 and 8; design-notes N1, N3, N7, N8, N8a items 4-6,
N10 (`always`, the B3 image-side checks) and N15's U4 row. Carry list
(docs/handoffs/platform-sbom.md, U3; docs/evidence/platform-sbom/u3/review.md):
ruling 5 item 6 (XDG_CACHE_HOME), review N4 (cygpath, MSYS_NO_PATHCONV,
chmod 0700), N6 (the SBOM work dir and the disk floor), N7 (two versions of
one name in uv.lock).

Interface pinned by these tests (tester, U4 RED, 2026-10-23; names the
developer may not change without the orchestrator):
- `scripts/sbom_check.py` (standard library, imported by path) gains pure
  functions:
  - `unlicensed_report(doc) -> dict`: `{"count": int, "by_type": {purl
    type: int, ...}, "packages": [{"spdxid": str, "name": str, "purl":
    str | None}, ...]}` over every package but the one the document
    DESCRIBES (N8a 4). A package is unlicensed when `licenseDeclared` and
    `licenseConcluded` are each missing (absent, null, not a string, or
    exactly "", "NONE" or "NOASSERTION", case-sensitive) and
    `licenseInfoFromFiles` is absent, null, not a list, or a list whose
    every entry is missing (N8 exact rule, architect U4); it never raises.
    `by_type` counts rows by purl type (N8a 5); a row with no purl is
    listed with its SPDXID and name, and may be counted under one extra
    key, so `count` is the number of rows.
  - `always_matches(image, doc, always) -> (flagged SPDXIDs, problems)`
    for the `always` entries of that image (N10 shape: `{"image", "match",
    "why"}`; `match` is a purl without version, `pkg:<type>/<ns>/<name>`,
    matching that package at any version and qualifiers but no other name,
    or `upstream=<source>`, matching every package whose purl's `upstream`
    qualifier names that source). Flagging ignores the licence the
    generator reports. An entry with no match in its image is a problem
    naming the image and the entry ("expected component not catalogued").
  - `drift_problems(app, base, added, licence_texts) -> list[str]`: the
    ke-app document's dpkg names (purl type `deb`) minus the base
    document's equal `added`; no `pkg:pypi/pip` (PEP 503) at any version;
    exactly one CPython version (`pkg:generic/python@X.Y.Z`, syft's binary
    cataloguer, U3 evidence) and it equals the `CPython X.Y.Z:` of line 1
    of each licence text (`{path: text}`). Each problem names the package,
    version or file.
  - `psycopg_problems(app, libpq_pin, psycopg_c_version) -> list[str]`
    (N7): `pkg:deb/debian/libpq5@<pin>` with `upstream=postgresql-<major>`,
    `pkg:pypi/psycopg-c@<version>`, and no psycopg-binary (PEP 503).
  - `added_packages(source_text) -> frozenset[str]`: the literal
    `ADDED_PACKAGES = frozenset({...})` of tests/test_notice_ke_app.py,
    read without importing it (ast); ValueError when absent or not a
    literal.
- `docker/source-policy.json` holds `always` (N10; the rest of its schema
  is U6's): entries for busybox, apk-tools and ssl_client (valkey,
  ke-gateway), the Temurin JVM and Neo4j Community (neo4j), psycopg,
  psycopg-c, libldap-2.5-0, libsasl2-2 and libsasl2-modules-db (ke-app;
  security u1 I-1, PSC-22 last bullet) and glibc in every Debian image
  (ke-app, postgres, neo4j, phoenix).
- `scripts/bundle.sh` prints, for every image, a line naming the image,
  the word "unlicensed" and the count, with the per-purl-type counts
  (`<type>: <n>`, `<type>=<n>` or `<n> <type>`), then each unlicensed
  row: its purl (with or without qualifiers), or its SPDXID and name on
  one line. The DESCRIBES root and licensed packages are not printed
  (PSC-22: "in the bundle output and the evidence"; the index copy is
  U9's, N9).
- `scripts/offline_check.sh` host half (ci/deployable-offline, full):
  right after the generator pull and before bundle.sh, one `docker pull`
  (or `docker image pull`) of the runtime stage's base reference of
  docker/app.Dockerfile, which must carry a tag and an `@sha256:` digest and
  not start with `-` (else it stops naming docker/app.Dockerfile, before
  any pull); the pull's last argument ends `@sha256:<digest>`; a failed
  pull dies with "pulling the ke-app base failed (<ref>); no retry",
  before bundle.sh, teardown still run (orchestrator U4 ruling 6; design
  notes "N1 amendment, U4"). After bundle.sh and before dind: `docker save`
  of that reference; the generator run on that tar through docker-compose.sbom.yml
  (`--env-file .env.example`, `run --rm --pull never sbom
  docker-archive:/in/<name>.tar --scope all-layers -o
  spdx-json=/out/<file>`, the three KE_SBOM_* keys set); then the drift
  and psycopg checks on the bundle's `app/sboms/ke-app.spdx.json`. The
  base tar and its SBOM are never inside the bundle directory and nothing
  is left under dist/. Any problem fails the check naming it, before dind.
- Carry: `sbom`'s environment has `XDG_CACHE_HOME: /tmp/cache` and no
  `SYFT_CACHE_DIR`; with a `cygpath` on PATH, bundle.sh hands
  `KE_SBOM_IN`, `KE_SBOM_OUT` and every checker `-v` source through
  `cygpath -m --`; `MSYS_NO_PATHCONV=1` is set on the generator run and the
  checker run and on no `save`; each image's work dir and its tmp/ are
  0700 when syft starts (umask 022); the work dir is outside --out but on
  --out's filesystem, under dirname(--out), not under TMPDIR (review N6;
  N1 amendment, U4); `runtime_problems` reads uv.lock as name -> set of
  versions and accepts a name locked at two versions whichever is
  installed, while a version outside the set still fails (review N7,
  architect U4).

U4 rework round 1 (orchestrator, 2026-10-23; docs/evidence/platform-sbom/u4/
review.md B1, N1-N4, N6, N7 and security.md H-1, M-1, M-2, L-1, L-3), pinned
by the tests below the "rework round 1" banner (tester, U4 rework RED):
- H-1 (design-notes N8 "Hash-only ids"): a licence field is missing, like
  NOASSERTION, when its ids, after splitting on whitespace and parentheses
  and dropping AND/OR/WITH (any case) and the exception id after each WITH,
  are at least one and all match `^LicenseRef-[0-9a-f]{64}$` (exact,
  case-sensitive); such a package is unlicensed and reported. A value with
  any other id (`MIT AND <hash>`, upper-case hex, 63 or 65 hex) is not. Each
  printed report row of a package with such a field (declared, concluded or
  a licenseInfoFromFiles entry) carries the marker
  `(unidentified licence text)` on its line; no other row line does.
- L-3: no string `report_lines` returns holds a C0 or C1 control character
  (U+0000-U+001F, U+007F-U+009F); generator-supplied names and purls are
  escaped or stripped, never split across lines. Printable purls are
  printed unchanged.
- B1: `sbom`'s tmpfs is exactly `["/tmp:mode=1777"]` (no `exec`), and no
  generator run of bundle.sh or of the offline drift step prints syft's
  `unable to get filesystem cache` line (tests/fake_docker.py models it from
  the compose file).
- M-1, M-2, L-1: `always` gains `upstream=gcc-12` (ke-app, postgres),
  `upstream=gcc-14` (neo4j, phoenix), `upstream=busybox` and
  `upstream=apk-tools` (valkey, ke-gateway) and an entry flagging neo4j's
  `pkg:maven/jrt-fs/jrt-fs`; on the real U3 package lists
  (tests/fixtures/sbom-u3/) every committed entry matches a package of its
  image.
- N1: `drift` reads psycopg-c's uv.lock versions as a set and passes when
  the SBOM lists one of them. N2: `psycopg_problems` compares libpq5's
  `upstream` qualifier up to any "@". N3: `added_packages` raises ValueError
  (never SyntaxError or TypeError), and `drift` then exits 1. N4:
  `unlicensed_report` never raises on a non-list `externalRefs` or a
  non-string locator; such a row has purl None.
- N6: on success `drift` prints exactly one non-empty line, naming every
  ADDED_PACKAGES name, `no pip`, the CPython version, the libpq5 pin and the
  psycopg-c version the SBOM lists. N7: offline_check.sh's drift checker
  `docker run` carries `--label com.docker.compose.project=<offline
  project>[-<suffix>]`.
- Review N5 (design-notes "N1 amendment, U4 rework"): bundle.sh runs the
  7 GiB floor (nearest existing ancestor, `df -Pk`) on `--out` and on
  `dirname(--out)`, refusing with `need 7 GiB free on <path>, found <N>
  GiB` naming the path that is short, before any save, with `--out` left
  empty and no record; one `df` call when both resolve to the same probe.

Every check helper returns problems so the U4 controls
(docs/evidence/platform-sbom/u4/red-mutants.txt) can run them on mutants.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from tests import compose_support as cs
from tests import fake_docker
from tests import sbom_support as ss
from tests import test_offline_check as toc
from tests.engine_support import ROOT
from tests.test_offline_bundle import _BundleBase, _stack_images
from tests.test_sbom_bundle import (SBOM_COMPOSE, compose_split, load_sbom_check, names_sbom_file,
                                    run_option_problems)

POLICY = ROOT / "docker" / "source-policy.json"
POLICY_MISSING = "docker/source-policy.json is missing (PSC-22 `always`; ADR-KE-016 point 8, design-notes N10)"
PROJECT = "ke-u4proj"


def fn(name: str) -> Any:
    """A function of scripts/sbom_check.py, or a failure naming it."""
    module = load_sbom_check()
    got = getattr(module, name, None)
    if not callable(got):
        raise AssertionError(f"scripts/sbom_check.py has no {name}() (U4 interface, tests/test_sbom_obligations.py)")
    return got


def bundled_names() -> set[str]:
    """The image names bundle.sh saves (images/<name>.tar), from the stack."""
    out = set()
    for ref in _stack_images().values():
        base = ref.split("@", 1)[0]
        repo = base if ":" not in base.rsplit("/", 1)[-1] else base.rsplit(":", 1)[0]
        out.add(repo.rsplit("/", 1)[-1])
    return out


_PURL = re.compile(r"^pkg:(?P<type>[a-z0-9.+-]+)/")


def described(doc: dict[str, Any]) -> set[str]:
    return {r.get("relatedSpdxElement") for r in doc.get("relationships") or []
            if r.get("relationshipType") == "DESCRIBES" and r.get("spdxElementId") == "SPDXRef-DOCUMENT"}


def pkg_purl(pkg: dict[str, Any]) -> str | None:
    for ref in pkg.get("externalRefs") or []:
        if ref.get("referenceType") == "purl":
            return str(ref.get("referenceLocator"))
    return None


HASH_ID = re.compile(r"LicenseRef-[0-9a-f]{64}")


def hash_only(value: Any) -> bool:
    """Security U4 H-1, design-notes N8 "Hash-only ids" (architect, U4
    rework): the value's licence ids, after splitting on whitespace and
    parentheses and dropping AND/OR/WITH (any case) and the exception id
    after each WITH, are at least one and all match
    `^LicenseRef-[0-9a-f]{64}$` (exact, case-sensitive)."""
    if not isinstance(value, str):
        return False
    ids: list[str] = []
    tokens = [t for t in re.split(r"[\s()]+", value) if t]
    i = 0
    while i < len(tokens):
        word = tokens[i].upper()
        if word == "WITH":
            i += 2
            continue
        if word not in ("AND", "OR"):
            ids.append(tokens[i])
        i += 1
    return bool(ids) and all(HASH_ID.fullmatch(t) for t in ids)


def oracle_unlicensed(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The tester's own reading of N8 "all three missing" (independent of
    sbom_check.py): rows the report must list. N8 exact rule (architect,
    U4): a wrong-typed value is missing; keywords are exact, case-sensitive.
    H-1 (rework round 1): a value made only of hash ids is missing too."""
    def missing(v: Any) -> bool:
        return not isinstance(v, str) or v in ("", "NONE", "NOASSERTION") or hash_only(v)
    root = described(doc)
    out = []
    for pkg in doc.get("packages") or []:
        if pkg.get("SPDXID") in root:
            continue
        raw = pkg.get("licenseInfoFromFiles")
        files = [f for f in raw if not missing(f)] if isinstance(raw, list) else []
        if missing(pkg.get("licenseDeclared")) and missing(pkg.get("licenseConcluded")) and not files:
            out.append({"spdxid": pkg.get("SPDXID"), "name": pkg.get("name"), "purl": pkg_purl(pkg)})
    return out


def report_problems(report: Any, want: list[dict[str, Any]]) -> list[str]:
    """unlicensed_report's return value against the oracle's rows."""
    if not isinstance(report, dict):
        return [f"unlicensed_report returned {type(report).__name__}, want a dict"]
    p = []
    if report.get("count") != len(want):
        p.append(f"count is {report.get('count')!r}, want {len(want)}")
    got = sorted((r.get("spdxid"), r.get("name"), r.get("purl")) for r in report.get("packages") or [])
    exp = sorted((r["spdxid"], r["name"], r["purl"]) for r in want)
    if got != exp:
        p.append(f"packages are {got}, want {exp}")
    typed: dict[str, int] = {}
    for r in want:
        m = _PURL.match(r["purl"] or "")
        if m:
            typed[m.group("type")] = typed.get(m.group("type"), 0) + 1
    by_type = report.get("by_type")
    if not isinstance(by_type, dict):
        return p + [f"by_type is {by_type!r}, want a dict of purl type -> count"]
    for t, n in typed.items():
        if by_type.get(t) != n:
            p.append(f"by_type[{t!r}] is {by_type.get(t)!r}, want {n} (rows per purl type, N8a 5)")
    extra = {k: v for k, v in by_type.items() if k not in typed}
    nopurl = sum(1 for r in want if not r["purl"])
    if extra and (len(extra) != 1 or list(extra.values())[0] != nopurl or nopurl == 0):
        p.append(f"by_type has {extra} beyond the purl types {sorted(typed)} (only one key, for the "
                 f"{nopurl} rows with no purl, is allowed)")
    return p


# --------------------------------------------------------------------------
# PSC-22: unlicensed packages, per image, with a count (fast, stubbed)
# --------------------------------------------------------------------------

def neo4j_unlicensed_doc() -> dict[str, Any]:
    """neo4j-shaped (N8a 4): maven jars and the JVM with no licence, a row
    with no purl, licensed rows in every field, and the image root."""
    rows = [
        {"purl": "pkg:maven/org.neo4j.bolt/bolt-connection@12.0.0", "declared": "NOASSERTION",
         "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/com.neo4j/fleet-management@1.2.0", "declared": None, "concluded": None},
        {"purl": "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS?repository_url=https%3A%2F%2Fgithub.com%2F"
                 "adoptium%2Fjdk21u.git", "declared": "", "concluded": "NONE"},
        {"purl": None, "name": "UNKNOWN", "spdxid": "SPDXRef-Package-binary-UNKNOWN-0f0f0f0f0f0f0f0f",
         "declared": "NOASSERTION", "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/net.java.dev.jna/jna@5.15.0", "declared": "NOASSERTION",
         "concluded": "Apache-2.0 AND LGPL-2.1-only"},
        {"purl": "pkg:maven/org.neo4j/neo4j@5.26.32", "declared": "Apache-2.0 AND GPL-3.0-only"},
        {"purl": ss.deb("libc6", "2.41-12+deb13u4", upstream="glibc", distro="debian-13.7"),
         "declared": "NOASSERTION", "concluded": "LicenseRef-40c7e1f2118531f0"},
    ]
    return ss.spdx_doc("neo4j", rows)


class UnlicensedReportTest(unittest.TestCase):

    def test_unlicensed_packages_are_reported(self):
        """PSC-22 bullet 2, N8a 4-5, by rule: every unlicensed row but the
        DESCRIBES root, counted per purl type, no-purl rows by SPDXID and
        name."""
        report = fn("unlicensed_report")
        doc = neo4j_unlicensed_doc()
        want = oracle_unlicensed(doc)
        with self.subTest(part="precondition: the oracle finds 4 rows (2 maven, 1 generic, 1 no purl)"):
            self.assertEqual(len(want), 4)
        with self.subTest(part="neo4j-shaped document"):
            self.assertEqual(report_problems(report(copy.deepcopy(doc)), want), [])
        with self.subTest(part="the root is excluded wherever it sits in packages"):
            moved = copy.deepcopy(doc)
            moved["packages"] = moved["packages"][1:] + moved["packages"][:1]
            self.assertEqual(report_problems(report(moved), want), [])
        with self.subTest(part="the root is excluded by DESCRIBES, not by its licence or purl type"):
            other = copy.deepcopy(doc)
            other["packages"][0]["licenseDeclared"] = "MIT"
            self.assertEqual(report_problems(report(other), want), [])
            other = copy.deepcopy(doc)
            other["relationships"] = [r for r in other["relationships"] if r["relationshipType"] != "DESCRIBES"]
            other["relationships"].append({"spdxElementId": "SPDXRef-DOCUMENT",
                                           "relatedSpdxElement": other["packages"][2]["SPDXID"],
                                           "relationshipType": "DESCRIBES"})
            self.assertEqual(report_problems(report(other), oracle_unlicensed(other)), [],
                             "the image root (not described here) is a row; the described package is not")
        with self.subTest(part="a document with no unlicensed row reports 0"):
            clean = ss.spdx_doc("valkey", [{"purl": "pkg:apk/alpine/musl@1.2.5-r10", "declared": "MIT"}])
            self.assertEqual(report_problems(report(clean), []), [])
        with self.subTest(part="N8: a licence in licenseInfoFromFiles is a licence (the third field)"):
            files = ss.spdx_doc("phoenix", [{"purl": "pkg:pypi/aiosqlite@0.22.1", "declared": "NOASSERTION",
                                             "concluded": "NOASSERTION", "files": ["MIT"]},
                                            {"purl": "pkg:pypi/jinja2@3.1.6", "declared": "NOASSERTION",
                                             "concluded": "NOASSERTION", "files": ["NOASSERTION"]}])
            self.assertEqual(report_problems(report(files), oracle_unlicensed(files)), [])
            self.assertEqual(len(oracle_unlicensed(files)), 1)
        with self.subTest(part="N8 type rule: a wrong-typed field is missing, never an exception"):
            odd = ss.spdx_doc("phoenix", [
                {"purl": "pkg:pypi/a@1", "declared": ["MIT"], "concluded": "NOASSERTION"},
                {"purl": "pkg:pypi/b@1", "declared": "NOASSERTION", "concluded": 5},
                {"purl": "pkg:pypi/c@1", "declared": None, "concluded": None, "files": "MIT"},
                {"purl": "pkg:pypi/d@1", "declared": "NONE", "concluded": "", "files": [1, None, {"id": "MIT"}]},
                {"purl": "pkg:pypi/e@1", "declared": {"id": "MIT"}, "concluded": "NOASSERTION", "files": [["MIT"]]},
                {"purl": "pkg:pypi/f@1", "declared": "noassertion", "concluded": "NOASSERTION"},
                {"purl": "pkg:pypi/g@1", "declared": "NOASSERTION", "concluded": "NOASSERTION", "files": [3, "MIT"]},
            ])
            odd["packages"][1]["licenseConcluded"] = None  # row a: an explicit null, not an absent key
            want = oracle_unlicensed(odd)
            self.assertEqual(sorted(r["purl"] for r in want),
                             [f"pkg:pypi/{n}@1" for n in "abcde"],
                             "precondition: a-e are unlicensed; f (lower-case keyword) and g (a string entry) are not")
            try:
                got = report(copy.deepcopy(odd))
            except Exception as exc:  # noqa: BLE001 - the contract is "report, not raise"
                self.fail(f"unlicensed_report raised {type(exc).__name__}: {exc}")
            self.assertEqual(report_problems(got, want), [])


def _token(purl: str) -> re.Pattern[str]:
    """purl as printed: with its qualifiers or without them."""
    base = purl.split("?", 1)[0]
    return re.compile(r"(?<!\S)" + re.escape(base) + r"(?:\?\S*)?(?![^\s,;)\]])")


def output_report_problems(output: str, name: str, doc: dict[str, Any]) -> list[str]:
    """bundle.sh's printed report for one image, against the oracle."""
    want = oracle_unlicensed(doc)
    p = []
    word = re.compile(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])")
    lines = [ln for ln in output.splitlines() if re.search(r"(?i)\bunlicensed\b", ln) and word.search(ln)]
    if not lines:
        return [f"no output line names {name} and `unlicensed` (PSC-22: listed per image, with a count)"]
    line = lines[0]
    if not re.search(rf"(?<![\w.]){len(want)}(?![\w.])", word.sub(" ", line)):
        p.append(f"{name}: the report line {line!r} does not give the count {len(want)}")
    typed: dict[str, int] = {}
    for r in want:
        m = _PURL.match(r["purl"] or "")
        if m:
            typed[m.group("type")] = typed.get(m.group("type"), 0) + 1
    for t, n in typed.items():
        if not re.search(rf"\b{re.escape(t)}\b\W{{0,3}}\b{n}\b|\b{n}\b\W{{0,3}}\b{re.escape(t)}\b", line):
            p.append(f"{name}: the report line {line!r} lacks the count {n} for purl type {t} (N8a 5)")
    for r in want:
        if r["purl"]:
            if not _token(r["purl"]).search(output):
                p.append(f"{name}: unlicensed {r['purl']} is not printed")
        elif not any(r["spdxid"] in ln and str(r["name"]) in ln for ln in output.splitlines()):
            p.append(f"{name}: the no-purl row {r['spdxid']} ({r['name']}) is not printed with its SPDXID and name")
    listed = {r["spdxid"] for r in want}
    for pkg in doc.get("packages") or []:
        if pkg.get("SPDXID") in listed:
            continue
        purl = pkg_purl(pkg)
        if purl and _token(purl).search(output):
            why = "the DESCRIBES root" if pkg.get("SPDXID") in described(doc) else "a licensed package"
            p.append(f"{name}: {purl} is printed as unlicensed but is {why}")
        if pkg.get("SPDXID") in described(doc) and str(pkg.get("SPDXID")) in output:
            p.append(f"{name}: the root {pkg.get('SPDXID')} is printed")
    return p


class UnlicensedBundleOutputTest(_BundleBase, unittest.TestCase):
    """bundle.sh prints the report for every image (fake docker; the real
    scripts/sbom_check.py)."""

    def test_bundle_output_lists_unlicensed_packages_per_image(self):
        # Platform-sbom U4b (PSC-26 *Bundled as first-party*): the neo4j service's image is
        # saved as ke-neo4j (images/ke-neo4j.tar, app/sboms/ke-neo4j.spdx.json); re-targeted
        # by the tester, U4b RED.
        raw = neo4j_unlicensed_doc()
        result, _, out = self._bundle(COMPOSE_PROJECT_NAME=PROJECT,
                                      FAKE_SYFT_RAW=json.dumps({"ke-neo4j": json.dumps(raw)}))
        output = self._out(result)
        self.assertEqual(result.returncode, 0, "bundle.sh failed on a fit build host:\n" + output)
        data = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        names = sorted(Path(e["file"]).stem for e in data["images"])
        self.assertIn("ke-neo4j", names)
        for name in names:
            with self.subTest(image=name):
                doc = json.loads((out / "app" / "sboms" / f"{name}.spdx.json").read_text(encoding="utf-8"))
                self.assertEqual(output_report_problems(output, name, doc), [])
        with self.subTest(part="precondition: the stub neo4j document reaches the bundle with 4 rows"):
            doc = json.loads((out / "app" / "sboms" / "ke-neo4j.spdx.json").read_text(encoding="utf-8"))
            self.assertEqual(len(oracle_unlicensed(doc)), 4)


# --------------------------------------------------------------------------
# PSC-22 bullet 1: named components need source whatever the generator says
# --------------------------------------------------------------------------

SYNTH_ALWAYS = [
    {"image": "valkey", "match": "pkg:apk/alpine/busybox", "why": "PSC-22"},
    {"image": "valkey", "match": "pkg:apk/alpine/ssl_client", "why": "PSC-22"},
    {"image": "postgres", "match": "upstream=glibc", "why": "PSC-22"},
]
ALP = "?arch=x86_64&distro=alpine-3.24.2"


def _rows_doc(name: str, rows: list[tuple[str, str]]) -> tuple[dict[str, Any], dict[str, str]]:
    """(document, purl -> SPDXID)."""
    doc = ss.spdx_doc(name, [{"purl": p, "declared": lic, "concluded": "NOASSERTION"} for p, lic in rows])
    return doc, {pkg_purl(p): p["SPDXID"] for p in doc["packages"][1:]}


# PSC-22's components, as syft writes them in the U3 SBOMs (fresh images,
# docs/evidence/platform-sbom/u3/sboms/*.pkgs.tsv), per image.
D12 = "debian-12.15"
D13 = "debian-13.7"
PSC22_COMPONENTS: dict[str, list[tuple[str, str]]] = {
    "valkey": [("busybox", f"pkg:apk/alpine/busybox@1.37.0-r31{ALP}"),
               ("apk-tools", f"pkg:apk/alpine/apk-tools@3.0.8-r0{ALP}"),
               ("ssl_client", f"pkg:apk/alpine/ssl_client@1.37.0-r31{ALP}&upstream=busybox")],
    "ke-gateway": [("busybox", "pkg:apk/alpine/busybox@1.37.0-r30?arch=x86_64&distro=alpine-3.23.3"),
                   ("apk-tools", "pkg:apk/alpine/apk-tools@3.0.3-r1?arch=x86_64&distro=alpine-3.23.3"),
                   ("ssl_client", "pkg:apk/alpine/ssl_client@1.37.0-r30?arch=x86_64&distro=alpine-3.23.3"
                                  "&upstream=busybox")],
    # platform-sbom U4b (PSC-26, N16): the neo4j entries name ke-neo4j, whose
    # packages are the official image's minus products/ (re-targeted, U4b RED).
    "ke-neo4j": [("Temurin", "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS?repository_url=https%3A%2F%2Fgithub.com"
                          "%2Fadoptium%2Fjdk21u.git"),
              ("Neo4j Community", "pkg:maven/org.neo4j/neo4j@5.26.32"),
              ("glibc", ss.deb("libc6", "2.41-12+deb13u4", upstream="glibc", distro=D13))],
    "ke-app": [("psycopg", "pkg:pypi/psycopg@3.3.6"), ("psycopg-c", "pkg:pypi/psycopg-c@3.3.6"),
               ("glibc", ss.deb("libc6", "2.36-9+deb12u14", upstream="glibc", distro=D12)),
               ("libldap-2.5-0", ss.deb("libldap-2.5-0", "2.5.13+dfsg-5", upstream="openldap", distro=D12)),
               ("libsasl2-2", ss.deb("libsasl2-2", "2.1.28+dfsg-10", upstream="cyrus-sasl2", distro=D12)),
               ("libsasl2-modules-db", ss.deb("libsasl2-modules-db", "2.1.28+dfsg-10", upstream="cyrus-sasl2",
                                              distro=D12))],
    "postgres": [("glibc", ss.deb("libc6", "2.36-9+deb12u14", upstream="glibc", distro=D12)),
                 ("glibc", ss.deb("libc-bin", "2.36-9+deb12u14", upstream="glibc", distro=D12))],
    "phoenix": [("glibc", ss.deb("libc6", "2.41-12+deb13u4", upstream="glibc", distro=D13))],
}
DECOYS = {"valkey": f"pkg:apk/alpine/musl@1.2.5-r10{ALP}", "ke-gateway": f"pkg:apk/alpine/musl@1.2.5-r10{ALP}",
          "ke-neo4j": "pkg:maven/org.slf4j/slf4j-api@2.0.17", "ke-app": "pkg:pypi/httpx@0.28.1",
          "postgres": ss.deb("tzdata", "2025b-0+deb12u2", distro=D12),
          "phoenix": ss.deb("tzdata", "2025b-4", distro=D13)}


def always_problems(always: Any) -> list[str]:
    """The committed `always` list (N10 shape; the rest of the schema is U6's)."""
    if not isinstance(always, list) or not always:
        return ["docker/source-policy.json has no non-empty `always` list (PSC-22, N10)"]
    p = []
    names = bundled_names()
    for i, e in enumerate(always):
        if not isinstance(e, dict):
            p.append(f"always[{i}] is not an object")
            continue
        for key in ("image", "match", "why"):
            if not isinstance(e.get(key), str) or not e.get(key, "").strip():
                p.append(f"always[{i}] has no non-blank `{key}` (N10)")
        if e.get("image") not in names:
            p.append(f"always[{i}] names image {e.get('image')!r}, not a bundled image {sorted(names)}")
    return p


def coverage_problems(always: list[dict[str, Any]], matches: Any) -> list[str]:
    """Each PSC-22 component, licensed as permissive or as nothing, is
    flagged in its image; a permissive decoy is not."""
    p = []
    for image, comps in PSC22_COMPONENTS.items():
        rows = [(purl, lic) for (_, purl), lic in zip(comps, ["MIT", "NOASSERTION", "Apache-2.0"] * 3)]
        doc, ids = _rows_doc(image, rows + [(DECOYS[image], "MIT")])
        flagged, _ = matches(image, doc, always)
        for comp, purl in comps:
            if ids[purl] not in flagged:
                p.append(f"{image}: {comp} ({purl}) is not flagged by `always` (PSC-22)")
        if ids[DECOYS[image]] in flagged:
            p.append(f"{image}: the permissive decoy {DECOYS[image]} is flagged (an `always` match is too wide)")
    return p


class NamedComponentsTest(unittest.TestCase):

    def test_named_gpl_components_need_source_whatever_the_generator_says(self):
        matches = fn("always_matches")
        valkey, vid = _rows_doc("valkey", [
            (f"pkg:apk/alpine/busybox@1.37.0-r31{ALP}", "MIT"),
            (f"pkg:apk/alpine/ssl_client@1.37.0-r31{ALP}&upstream=busybox", "NOASSERTION"),
            (f"pkg:apk/alpine/busyboxx@1.0-r0{ALP}", "GPL-2.0-only"),
            (f"pkg:apk/alpine/musl@1.2.5-r10{ALP}", "MIT")])
        with self.subTest(part="purl match: flagged whatever the licence; no other name"):
            flagged, problems = matches("valkey", copy.deepcopy(valkey), SYNTH_ALWAYS)
            self.assertEqual(sorted(flagged), sorted([vid[f"pkg:apk/alpine/busybox@1.37.0-r31{ALP}"],
                                                      vid[f"pkg:apk/alpine/ssl_client@1.37.0-r31{ALP}"
                                                          "&upstream=busybox"]]))
            self.assertEqual(problems, [])
        with self.subTest(part="licence fields absent: still flagged"):
            bare = copy.deepcopy(valkey)
            for pkg in bare["packages"]:
                pkg.pop("licenseDeclared", None)
                pkg.pop("licenseConcluded", None)
            self.assertEqual(len(matches("valkey", bare, SYNTH_ALWAYS)[0]), 2)
        pg, pid = _rows_doc("postgres", [
            (ss.deb("libc6", "2.36-9+deb12u14", upstream="glibc"), "NOASSERTION"),
            (ss.deb("libc-bin", "2.36-9+deb12u14", upstream="glibc"), "MIT"),
            (ss.deb("locales", "2.36-9+deb12u14", upstream="glibc"), "NOASSERTION"),
            (ss.deb("libglib2.0-0", "2.74.6-2+deb12u5", upstream="glib2.0"), "LGPL-2.1-or-later"),
            (ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"), "GPL-3.0-or-later")])
        with self.subTest(part="upstream match: every package of that source, none other"):
            flagged, problems = matches("postgres", pg, SYNTH_ALWAYS)
            want = [pid[ss.deb(n, "2.36-9+deb12u14", upstream="glibc")] for n in ("libc6", "libc-bin", "locales")]
            self.assertEqual(sorted(flagged), sorted(want))
            self.assertEqual(problems, [])
        with self.subTest(part="another image's entries do not apply"):
            self.assertEqual(matches("valkey", pg, SYNTH_ALWAYS)[0], [],
                             "postgres's glibc entry flagged a package when checking valkey")
        with self.subTest(part="an entry with no match in its image is a problem naming both"):
            gone = copy.deepcopy(valkey)
            gone["packages"] = [p for p in gone["packages"] if p["name"] != "ssl_client"]
            flagged, problems = matches("valkey", gone, SYNTH_ALWAYS)
            self.assertEqual(len(flagged), 1, "busybox is still flagged")
            self.assertTrue(problems and any("valkey" in m and "ssl_client" in m for m in problems),
                            f"no problem names valkey and ssl_client: {problems} (expected component not catalogued)")
            self.assertFalse(any("glibc" in m for m in problems), "postgres's entry is not checked for valkey")

    def test_source_policy_always_covers_psc22_components(self):
        self.assertTrue(POLICY.is_file(), POLICY_MISSING)
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        always = data.get("always") if isinstance(data, dict) else None
        with self.subTest(part="shape (N10)"):
            self.assertEqual(always_problems(always), [])
        with self.subTest(part="every PSC-22 component is flagged in its image, licence aside"):
            self.assertEqual(coverage_problems(always if isinstance(always, list) else [], fn("always_matches")), [])


# --------------------------------------------------------------------------
# PSC-14/22, B3: the image-side drift check, its logic on stubs (fast)
# --------------------------------------------------------------------------

def mutate(doc: dict[str, Any], purl: str, *, version: str | None = None, upstream: str | None = None) -> dict:
    """Change the version or upstream of the package with this purl name."""
    out = copy.deepcopy(doc)
    for pkg in out["packages"]:
        p = pkg_purl(pkg) or ""
        if p.split("@", 1)[0] == purl:
            new = p
            if version is not None:
                new = re.sub(r"@[^?]+", "@" + version.replace("+", "%2B"), new)
            if upstream is not None:
                new = re.sub(r"upstream=[^&]+", "upstream=" + upstream, new)
            pkg["externalRefs"][0]["referenceLocator"] = new
    return out


def with_row(doc: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return ss.spdx_doc("ke-app", [{"purl": pkg_purl(p), "name": p["name"], "declared": p.get("licenseDeclared")}
                                  for p in doc["packages"][1:]] + [row])


class DriftLogicTest(unittest.TestCase):
    """The checks `full` runs on the real ke-app SBOM (offline_check.sh), on
    stubs here."""

    def setUp(self) -> None:
        self.drift = fn("drift_problems")
        self.base = ss.fake_base_doc()
        self.app = ss.ke_app_doc()
        self.added = ss.added_packages()
        self.texts = ss.licence_texts()

    def _run(self, app: dict | None = None, base: dict | None = None, added: Any = None,
             texts: dict | None = None) -> list[str]:
        return self.drift(app if app is not None else copy.deepcopy(self.app),
                          base if base is not None else copy.deepcopy(self.base),
                          added if added is not None else self.added,
                          texts if texts is not None else dict(self.texts))

    def _fails(self, problems: list[str], *words: str) -> None:
        self.assertTrue(problems, "the drift check passed")
        joined = "\n".join(problems)
        for w in words:
            self.assertIn(w, joined, f"no problem names {w!r}: {problems}")

    def test_ke_app_sbom_added_dpkg_set_equals_added_packages(self):
        with self.subTest(case="matching SBOMs"):
            self.assertEqual(self._run(), [])
        with self.subTest(case="ke-app adds a package ADDED_PACKAGES lacks"):
            self._fails(self._run(app=with_row(self.app, {"purl": ss.deb("libzz9", "1.0-1"), "declared": "MIT"})),
                        "libzz9")
        with self.subTest(case="ADDED_PACKAGES names a package ke-app does not add"):
            self._fails(self._run(added=self.added | {"libyy8"}), "libyy8")
        with self.subTest(case="ke-app lacks one of ADDED_PACKAGES"):
            self._fails(self._run(app=ss.ke_app_doc(drop=("libsasl2-2",))), "libsasl2-2")
        with self.subTest(case="the base already holds libpq5, so ke-app does not add it"):
            base = ss.spdx_doc("base", [{"purl": pkg_purl(p), "declared": "MIT"} for p in self.base["packages"][1:]]
                               + [{"purl": ss.deb("libpq5", ss.libpq_pin()), "declared": "PostgreSQL"}])
            self._fails(self._run(base=base), "libpq5")
        with self.subTest(case="dpkg means purl type deb (a pypi libzz9 is not a dpkg package)"):
            self.assertEqual(self._run(app=with_row(self.app, {"purl": ss.pypi("libzz9", "1.0"),
                                                                "declared": "MIT"})), [])

    def test_ke_app_sbom_lists_no_pip(self):
        for case, purl in (("pip", "pkg:pypi/pip@25.0.1"), ("PEP 503 spelling", "pkg:pypi/Pip@24.0")):
            with self.subTest(case=case):
                self._fails(self._run(app=with_row(self.app, {"purl": purl, "declared": "MIT"})), "pip")
        with self.subTest(case="pip-tools is not pip"):
            self.assertEqual(self._run(app=with_row(self.app, {"purl": "pkg:pypi/pip-tools@7.4.1",
                                                                "declared": "BSD-3-Clause"})), [])

    def test_ke_app_sbom_cpython_matches_licence_files(self):
        want = ss.licence_version()
        with self.subTest(case="precondition: the three licence files name one version"):
            self.assertEqual({ss.licence_version(r) for r in ss.LICENCE_FILES}, {want})
        with self.subTest(case="SBOM CPython differs"):
            self._fails(self._run(app=ss.ke_app_doc(cpython="3.12.14")), "3.12.14", want)
        with self.subTest(case="no CPython package"):
            self._fails(self._run(app=ss.ke_app_doc(drop=("python",))), "python")
        with self.subTest(case="two CPython versions"):
            self._fails(self._run(app=with_row(self.app, {"purl": "pkg:generic/python@3.11.2", "name": "python"})),
                        "3.11.2")
        for rel in ss.LICENCE_FILES:
            with self.subTest(case=f"{rel} names another version"):
                texts = dict(self.texts)
                texts[rel] = texts[rel].replace(f"CPython {want}:", "CPython 3.12.16:", 1)
                self._fails(self._run(texts=texts), Path(rel).name)
            with self.subTest(case=f"{rel} line 1 does not parse"):
                texts = dict(self.texts)
                texts[rel] = "garbage\n" + texts[rel]
                self._fails(self._run(texts=texts), Path(rel).name)

    def test_ke_app_sbom_lists_libpq5_and_psycopg_c_not_binary(self):
        check = fn("psycopg_problems")
        pin, ver = ss.libpq_pin(), ss.locked_version("psycopg-c")
        major = pin.split(".", 1)[0]
        good = ss.ke_app_doc()
        with self.subTest(case="good"):
            self.assertEqual(check(copy.deepcopy(good), pin, ver), [])
        cases = {
            "libpq5 missing": (ss.ke_app_doc(drop=("libpq5",)), "libpq5"),
            "libpq5 at another version": (mutate(good, "pkg:deb/debian/libpq5", version="15.18-0+deb12u1"), "libpq5"),
            "libpq5 from another upstream": (mutate(good, "pkg:deb/debian/libpq5",
                                                    upstream=f"postgresql-{int(major) + 1}"), "libpq5"),
            "psycopg-c missing": (ss.ke_app_doc(drop=("psycopg-c",)), "psycopg-c"),
            "psycopg-c at another version": (mutate(good, "pkg:pypi/psycopg-c", version="3.3.5"), "psycopg-c"),
            "psycopg-binary present": (with_row(good, {"purl": "pkg:pypi/psycopg-binary@3.3.6"}), "psycopg"),
            "psycopg_binary spelled with _": (with_row(good, {"purl": "pkg:pypi/psycopg_binary@3.3.6"}), "psycopg"),
        }
        for case, (doc, word) in cases.items():
            with self.subTest(case=case):
                got = check(doc, pin, ver)
                self.assertTrue(got, f"psycopg_problems passed: {case}")
                self.assertIn(word, "\n".join(got))

    def test_added_packages_read_from_notice_test_module(self):
        read = fn("added_packages")
        source = (ROOT / "tests" / "test_notice_ke_app.py").read_text(encoding="utf-8")
        with self.subTest(case="the committed module"):
            self.assertEqual(read(source), ss.added_packages())
        with self.subTest(case="read without importing it"):
            self.assertEqual(read("import nonexistent_module_u4\n" + source), ss.added_packages())
        for case, text in (("absent", "X = frozenset({'a'})\n"),
                           ("not a literal", "ADDED_PACKAGES = frozenset(sorted(['a']))\n"),
                           ("another call", "ADDED_PACKAGES = make_added()\n"),
                           ("not strings", "ADDED_PACKAGES = frozenset({1, 2})\n")):
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    read(text)
        with self.subTest(case="precondition: the module's literal parses with ast"):
            tree = ast.parse(source)
            self.assertTrue(any(isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "ADDED_PACKAGES"
                                                                   for t in n.targets) for n in tree.body))


# --------------------------------------------------------------------------
# The same checks in full: offline_check.sh's host half (fake docker here)
# --------------------------------------------------------------------------

class DriftOfflineCheckTest(toc._OfflineBase):
    """ci/deployable-offline runs the image-side checks on the real bundle
    (`scripts/verify.sh full`); here, the wiring against the fake daemon."""

    _host_setup = toc.OfflineCheckScriptTest._host_setup
    _sbom_env = toc.OfflineCheckScriptTest._sbom_env
    _host = toc.OfflineCheckScriptTest._host
    _event = staticmethod(toc.OfflineCheckScriptTest._event)
    _events = toc.OfflineCheckScriptTest._events
    _bundle_dirs = toc.OfflineCheckScriptTest._bundle_dirs

    def _table(self, *, base: bool = True) -> str:
        refs = [cs.sbom_generator_ref(SBOM_COMPOSE)] + ([ss.base_ref()] if base else [])
        return json.dumps({r: {"Id": "sha256:" + "1" * 64, "Os": "linux", "Architecture": "amd64",
                               "RepoDigests": [r]} for r in refs})

    def _digest(self) -> str:
        return ss.base_ref().rsplit("@", 1)[1]

    def _drift_records(self, records: list[dict]) -> tuple[list[int], list[int]]:
        saves = [i for i, r in enumerate(records) if (r["argv"][:1] == ["save"] or r["argv"][:2] == ["image", "save"])
                 and any(a.endswith(self._digest()) for a in r["argv"])]
        runs = [i for i, r in enumerate(records) if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "run"]
        return saves, runs

    @staticmethod
    def _base_pulls(records: list[dict]) -> list[int]:
        """Every daemon-level pull (`docker pull` / `docker image pull`) of the
        host half: the generator is pulled through compose, so these are the
        ke-app base pulls (orchestrator U4 ruling 6). Platform-sbom U4b
        (PSC-26 `[full: ke-neo4j config matches the pinned official image]`):
        the one pull of the official neo4j image by its pinned digest, for the
        ke-neo4j step, is not one; tests/test_neo4j_image.py pins it
        (re-targeted by the tester, U4b RED). Any other pull still counts here,
        so `_pull_problems` still refuses it."""
        from tests import neo4j_support as ns
        return [i for i, r in enumerate(records) if (r["argv"][:1] == ["pull"] or r["argv"][:2] == ["image", "pull"])
                and r["argv"][-1] != ns.OFFICIAL_REF]

    def _pull_problems(self, records: list[dict]) -> list[str]:
        """Ruling 6: by its pinned digest, never by a tag alone."""
        p = []
        for i in self._base_pulls(records):
            ref = records[i]["argv"][-1]
            if not ref.endswith("@" + self._digest()):
                p.append(f"the base pull names {ref!r}, not the pinned {ss.base_ref()} (never a tag alone)")
        return p

    def _stopped(self, result: subprocess.CompletedProcess, records: list[dict], repo: Path, *words: str) -> None:
        out = self._out(result)
        self.assertNotEqual(result.returncode, 0, out)
        for w in words:
            self.assertIn(w, out, f"the failure does not name {w!r}")
        events = self._events(records)
        self.assertNotIn("up dind", events, "dind started after a failed drift check")
        self.assertNotIn("run client", events)
        self.assertEqual(events.count("teardown"), 1, f"teardown did not run once: {events}")
        self.assertNotRegex(out, r"(?i)\bpass(?:ed)?\b")
        self.assertIsNone(toc.SKIP_RX.search(out), "never a skip")
        self.assertEqual(self._bundle_dirs(repo), [])

    def test_offline_check_runs_image_side_drift_check(self):
        result, records, repo = self._host(FAKE_DOCKER_IMAGES=self._table())
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        events = [(i, self._event(r)) for i, r in enumerate(records)]
        at = {e: i for i, e in reversed(events) if e}
        saves, runs = self._drift_records(records)
        pulls = self._base_pulls(records)
        sbom_pulls = [i for i, r in enumerate(records) if names_sbom_file(r["argv"]) and "pull" in r["argv"]]
        with self.subTest(part="ruling 6 (N1 am. U4): one pull of the base by its digest, after the generator "
                               "pull, before bundle.sh (a no-op when the daemon already holds it)"):
            self.assertEqual(len(pulls), 1, f"want one `docker pull {ss.base_ref()}`: "
                                            f"{[records[i]['argv'] for i in pulls]}")
            self.assertEqual(self._pull_problems(records), [])
            if pulls:
                self.assertTrue(sbom_pulls and sbom_pulls[0] < pulls[0] < at["bundle"],
                                f"order: pull sbom, pull base, bundle: {events}")
        with self.subTest(part="the base is saved by its pinned reference, after bundle.sh, before dind"):
            self.assertEqual(len(saves), 1, f"want one `docker save` of {ss.base_ref()}: "
                                            f"{[r['argv'] for r in records if 'save' in r['argv'][:2]]}")
            if saves:
                self.assertTrue(at["bundle"] < saves[0] < at["up dind"], f"order: {events}")
        bundle_rel = ""
        bundle = next((r["argv"] for r in records if self._event(r) == "bundle"), [])
        if "--out" in bundle:
            bundle_rel = os.path.normpath(bundle[bundle.index("--out") + 1]).replace(os.sep, "/")
        with self.subTest(part="the base tar is outside the bundle directory"):
            if saves:
                argv = records[saves[0]]["argv"]
                target = argv[argv.index("-o") + 1] if "-o" in argv else argv[argv.index("--output") + 1]
                rel = os.path.relpath(os.path.join(records[saves[0]]["cwd"], target), repo).replace(os.sep, "/")
                self.assertFalse(rel == bundle_rel or rel.startswith(bundle_rel + "/"),
                                 f"the base tar {rel} is inside the bundle {bundle_rel} (install refuses unlisted files)")
        with self.subTest(part="the generator reads the base tar: --pull never, its own file, KE_SBOM_* set"):
            base_runs = [i for i in runs if saves and i > saves[0]]
            self.assertEqual(len(base_runs), 1, f"want one generator run after the base save: {runs}")
            for i in base_runs:
                argv, env = records[i]["argv"], records[i]["env"]
                globs, _, _, rest = compose_split(argv)
                self.assertIn(("-f", cs.SBOM_COMPOSE_NAME), globs)
                self.assertIn(("--env-file", ".env.example"), globs)
                src = next((a for a in rest if a.startswith("docker-archive:/in/")), "")
                name = src[len("docker-archive:/in/"):-len(".tar")] if src.endswith(".tar") else "?"
                self.assertEqual(run_option_problems(rest, name), [])
                for var in ("KE_SBOM_IN", "KE_SBOM_OUT", "KE_SBOM_USER"):
                    self.assertTrue(env.get(var), f"{var} is not set for the base generator run")
                work = os.path.relpath(os.path.join(records[i]["cwd"], env.get("KE_SBOM_OUT", "")), repo)
                work = work.replace(os.sep, "/")
                self.assertFalse(work == bundle_rel or work.startswith(bundle_rel + "/"),
                                 f"the base SBOM work dir {work} is inside the bundle")
                self.assertLess(i, at["up dind"])
        with self.subTest(part="nothing is left under dist/"):
            left = sorted(str(p.relative_to(repo)) for p in (repo / "dist").rglob("*")) if (repo / "dist").exists() else []
            self.assertEqual(left, [])

    def test_offline_check_fails_on_image_side_drift(self):
        cases = {
            "ke-app adds libzz9": ({"extra": ({"purl": ss.deb("libzz9", "1.0-1"), "declared": "MIT"},)}, "libzz9"),
            "pip in ke-app": ({"extra": ({"purl": "pkg:pypi/pip@25.0.1", "declared": "MIT"},)}, "pip"),
            "CPython 3.12.14": ({"cpython": "3.12.14"}, "3.12.14"),
            "psycopg-binary in ke-app": ({"extra": ({"purl": "pkg:pypi/psycopg-binary@3.3.6", "declared": "LGPL-3.0-only"},)},
                                         "psycopg-binary"),
            "libpq5 missing": ({"drop": ("libpq5",)}, "libpq5"),
        }
        for case, (kw, word) in cases.items():
            with self.subTest(case=case):
                sbom = ss.write_json(self.tmp / f"bad-{len(word)}-{abs(hash(case))}.json", ss.ke_app_doc(**kw))
                result, records, repo = self._host(FAKE_DOCKER_IMAGES=self._table(), FAKE_STUB_KE_APP_SBOM=str(sbom))
                self._stopped(result, records, repo, word)

    def test_offline_check_pulls_ke_app_base_absent_locally(self):
        """Ruling 6: the check never relies on the BuildKit cache; a daemon
        without the base gets it from the pull, and the drift step runs."""
        result, records, repo = self._host(FAKE_DOCKER_IMAGES=self._table(base=False))
        self.assertEqual(result.returncode, 0, self._out(result))
        saves, _ = self._drift_records(records)
        pulls = self._base_pulls(records)
        self.assertEqual(len(pulls), 1)
        self.assertEqual(self._pull_problems(records), [])
        self.assertTrue(saves and pulls[0] < saves[0], "the base was saved before it was pulled")

    def test_offline_check_fails_when_ke_app_base_pull_fails(self):
        """Ruling 6 (replaces U4 RED's "absent base fails, no pull"): a failed
        pull fails the check closed, naming the reference, with no retry and
        no drift step, even though the daemon holds a (possibly stale) copy."""
        result, records, repo = self._host(FAKE_DOCKER_IMAGES=self._table(base=True), FAKE_DOCKER_PULL_OK="")
        self._stopped(result, records, repo, f"pulling the ke-app base failed ({ss.base_ref()}); no retry")
        pulls = self._base_pulls(records)
        self.assertEqual(len(pulls), 1, f"the base pull was retried or never made: {[records[i]['argv'] for i in pulls]}")
        self.assertEqual(self._pull_problems(records), [])
        saves, runs = self._drift_records(records)
        self.assertEqual(saves, [], "the drift step ran after the base pull failed")
        self.assertNotIn("bundle", self._events(records), "bundle.sh ran after the base pull failed (N1 am. U4)")

    def _host_dockerfile(self, dockerfile: str, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict], Path]:
        """`_host` with the checkout's docker/app.Dockerfile replaced."""
        repo = self._host_setup()
        (repo / "docker" / "app.Dockerfile").write_text(dockerfile, encoding="utf-8", newline="\n")
        self.json.write_text("", encoding="utf-8")
        env_vars = {"FAKE_DOCKER_ROOT_DIR": str(self.tmp / "no-such-docker-root")}
        env_vars.update(self._sbom_env(repo))
        env_vars.update(extra)
        env = self._base_env(COMPOSE_PROJECT_NAME="ke-verify-1234", KE_SMOKE_OWNS_PROJECT="1", **env_vars)
        result = subprocess.run(["bash", "scripts/offline_check.sh"], cwd=repo, env=env,
                                capture_output=True, text=True, timeout=120)
        return result, fake_docker.records(self.json), repo

    def test_offline_check_refuses_an_unpinned_base_reference(self):
        """N1 am. U4: the runtime stage's FROM needs a tag and an @sha256
        digest, and may not start with `-`; anything else stops the check
        before any pull and before bundle.sh."""
        ref = ss.base_ref()
        text = ss.DOCKERFILE.read_text(encoding="utf-8")
        self.assertEqual(text.count(f"FROM {ref} AS runtime"), 1, "precondition: one runtime FROM")
        name, digest = ref.split("@", 1)
        for case, bad in (("leading -", "-" + ref), ("tag only", name), ("digest only", f"python@{digest}"),
                          ("short digest", ref[:-1])):
            with self.subTest(case=case):
                result, records, repo = self._host_dockerfile(text.replace(f"FROM {ref} AS runtime",
                                                                           f"FROM {bad} AS runtime"),
                                                              FAKE_DOCKER_IMAGES=self._table())
                self._stopped(result, records, repo, "app.Dockerfile")
                self.assertEqual(self._base_pulls(records), [], "a pull ran with an unpinned base reference")
                self.assertNotIn("bundle", self._events(records))


# --------------------------------------------------------------------------
# Carry list from U3
# --------------------------------------------------------------------------

def cache_problems(data: dict[str, Any]) -> list[str]:
    """Ruling 5 item 6 (N8a): syft's cache under the tmpfs, by the XDG key."""
    env = ((data.get("services") or {}).get("sbom") or {}).get("environment") or {}
    if isinstance(env, list):
        env = dict(str(e).split("=", 1) if "=" in str(e) else (str(e), None) for e in env)
    p = []
    if env.get("XDG_CACHE_HOME") != "/tmp/cache":
        p.append(f"sbom: XDG_CACHE_HOME is {env.get('XDG_CACHE_HOME')!r}, want '/tmp/cache' (ruling 5 item 6)")
    if "SYFT_CACHE_DIR" in env:
        p.append("sbom: sets SYFT_CACHE_DIR (ruling 5 item 6: a ninth SYFT_* key U2's pin does not know)")
    return p


_CYGPATH = r'''#!/usr/bin/env bash
# Fake cygpath (platform-sbom U4, review N4): logs its argv and prints the path
# with "/." appended, a different spelling of the same directory.
printf '%s\n' "$*" >> "$FAKE_CYGPATH_LOG"
last=""; for a in "$@"; do last="$a"; done
printf '%s/.' "${last%/}"
'''


class SbomCarryU4Test(_BundleBase, unittest.TestCase):

    def test_sbom_generator_cache_under_tmp(self):
        self.assertEqual(cache_problems(cs.load(SBOM_COMPOSE)), [])

    def _syft_log(self) -> Path:
        return self.tmp / f"syft-u4-{self.n + 1}.jsonl"

    def _good(self, **kw: Any) -> tuple[subprocess.CompletedProcess, list[dict], Path, list[dict]]:
        log = self._syft_log()
        kw.setdefault("COMPOSE_PROJECT_NAME", PROJECT)
        kw.setdefault("FAKE_SYFT_LOG", str(log))
        result, _, out = self._bundle(**kw)
        self.assertEqual(result.returncode, 0, "bundle.sh failed on a fit build host:\n" + self._out(result))
        syft = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return result, fake_docker.records(self.json), out, syft

    def test_bundle_hands_host_paths_through_cygpath(self):
        """Review N4: the Git Bash branch of hostpath(), with a fake cygpath."""
        fake = self.tmp / "cygbin" / "cygpath"
        toc._executable(fake, _CYGPATH)
        log = self.tmp / "cygpath.log"
        log.write_text("", encoding="utf-8")
        _, recs, out, _ = self._good(PATH=f"{fake.parent}{os.pathsep}{self.path}", FAKE_CYGPATH_LOG=str(log))
        calls = [ln.split() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        with self.subTest(part="cygpath -m -- <path>"):
            self.assertTrue(calls, "cygpath was never called although it is on PATH")
            for c in calls:
                self.assertEqual(c[:2], ["-m", "--"], f"cygpath called as {c}, want `cygpath -m -- <path>`")
        runs = [r for r in recs if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "run"]
        self.assertTrue(runs)
        for r in runs:
            with self.subTest(part="KE_SBOM_IN and KE_SBOM_OUT are cygpath's output", argv=r["argv"][-5]):
                self.assertEqual(r["env"].get("KE_SBOM_IN"), f"{out}/images/.")
                self.assertTrue(str(r["env"].get("KE_SBOM_OUT", "")).endswith("/."),
                                f"KE_SBOM_OUT {r['env'].get('KE_SBOM_OUT')!r} did not pass through cygpath")
        checks = [r["argv"] for r in recs if r["argv"][:1] == ["run"]
                  and any(a.endswith("sbom_check.py") for a in r["argv"])]
        self.assertTrue(checks)
        for argv in checks:
            mounts = [b for a, b in zip(argv, argv[1:]) if a in ("-v", "--volume")]
            with self.subTest(part="every checker -v source is cygpath's output", mounts=len(mounts)):
                self.assertTrue(mounts)
                for m in mounts:
                    src = m.rsplit(":", 2)[0] if m.endswith(":ro") else m.rsplit(":", 1)[0]
                    self.assertTrue(src.endswith("/.") or "/./" in src,
                                    f"-v {m}: the host source did not pass through cygpath")

    def test_bundle_sets_msys_no_pathconv_on_container_runs_only(self):
        _, recs, _, _ = self._good(FAKE_DOCKER_RECORD_ENV="MSYS_NO_PATHCONV")
        runs = [r for r in recs if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "run"]
        checks = [r for r in recs if r["argv"][:1] == ["run"] and any(a.endswith("sbom_check.py") for a in r["argv"])]
        saves = [r for r in recs if r["argv"][:1] == ["save"]]
        self.assertTrue(runs and checks and saves)
        for what, group, want in (("generator run", runs, "1"), ("checker run", checks, "1"), ("save", saves, None)):
            for r in group:
                with self.subTest(call=what):
                    self.assertEqual(r["env"].get("MSYS_NO_PATHCONV"), want,
                                     f"{what}: MSYS_NO_PATHCONV is {r['env'].get('MSYS_NO_PATHCONV')!r}, want "
                                     f"{want!r} (Git Bash must still convert `save -o`'s host path)")

    def test_bundle_sbom_work_dir_is_private(self):
        old = os.umask(0o022)
        try:
            _, _, _, syft = self._good()
        finally:
            os.umask(old)
        self.assertTrue(syft, "no generator run was logged")
        for entry in syft:
            with self.subTest(image=entry.get("name")):
                self.assertEqual((entry.get("out_mode"), entry.get("tmp_mode")), (0o700, 0o700),
                                 "the work dir and its tmp/ are 0700 when syft starts (umask 022; review N4)")

    def test_bundle_sbom_work_dir_on_out_filesystem(self):
        """Review N6 (tester's default, pending the architect): the 1-2 GB
        unpack lands next to --out, which the 7 GiB floor measures, not
        under TMPDIR."""
        elsewhere = self.tmp / "tmpdir-elsewhere"
        elsewhere.mkdir()
        _, recs, out, _ = self._good(TMPDIR=str(elsewhere))
        runs = [r for r in recs if names_sbom_file(r["argv"]) and compose_split(r["argv"])[2] == "run"]
        self.assertTrue(runs)
        for r in runs:
            work = Path(r["env"].get("KE_SBOM_OUT", "")).resolve()
            with self.subTest(work=str(work)):
                parents = [work, *work.parents]
                self.assertIn(out.parent.resolve(), parents, "the work dir is not under dirname(--out)")
                self.assertNotIn(out.resolve(), parents, "the work dir is inside --out")
                self.assertNotIn(elsewhere.resolve(), parents, "the work dir is under TMPDIR")
        with self.subTest(part="nothing is left beside --out"):
            self.assertEqual(sorted(p.name for p in out.parent.iterdir()),
                             sorted([out.name, out.name + ".manifest.sha256"]))

    def test_runtime_check_accepts_a_name_locked_at_two_versions(self):
        """Review N7 (architect U4, design-notes N7 "Forked lock"): uv.lock is
        read as name -> set of versions; an installed version in the set
        passes, whichever it is; one outside the set still fails, naming it."""
        check = fn("runtime_problems")
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        lock = work / "uv.lock"
        lock.write_text('version = 1\n\n[[package]]\nname = "foo"\nversion = "1.0"\n\n'
                        '[[package]]\nname = "foo"\nversion = "2.0"\n', encoding="utf-8")
        for installed, want_ok in (("1.0", True), ("2.0", True), ("3.0", False)):
            with self.subTest(installed=installed):
                site = work / f"site-{installed}"
                dist = site / f"foo-{installed}.dist-info"
                dist.mkdir(parents=True)
                (dist / "METADATA").write_text(f"Metadata-Version: 2.1\nName: foo\nVersion: {installed}\n\n",
                                               encoding="utf-8")
                doc = ss.spdx_doc("ke-app", [{"purl": ss.pypi("foo", installed), "declared": "MIT"}])
                got = check(doc, str(site), str(lock))
                if want_ok:
                    self.assertEqual(got, [], f"foo {installed} is locked (1.0 and 2.0) and listed, but was refused")
                else:
                    self.assertTrue(got and any("foo" in m and "3.0" in m for m in got),
                                    f"foo 3.0 is not in uv.lock's {{1.0, 2.0}}; want a problem naming it: {got}")


# ==========================================================================
# U4 rework round 1 (tester, 2026-10-23): security H-1, M-1, M-2, L-1, L-3;
# review B1, N1-N4, N6, N7. Interface: the module docstring's last section.
# ==========================================================================

UNIDENTIFIED = "(unidentified licence text)"
CACHE_WARNING = "unable to get filesystem cache"
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# H1 is a real syft hash id (postgres base-files, tests/fixtures/sbom-u3).
H1 = "LicenseRef-fd7e4aae7e7b05f217bcf2d02322825c360e66c52c4c2f1b28d784d6297a1c23"
H2 = "LicenseRef-" + "0123456789abcdef" * 4


def hash_rows() -> list[dict[str, Any]]:
    """H-1 rows (N8 rule): hash-only in each field, joined by AND/OR in any
    case, in parentheses, or WITH an exception (unlicensed, marked); a plain
    NOASSERTION row (unlicensed, not marked); near-misses that are licensed:
    a hash mixed with a real id either way, a real id WITH a hash-shaped
    exception, upper-case hex, 63 or 65 hex, 16 hex."""
    return [
        {"purl": "pkg:maven/x.with/with@1.0", "declared": f"{H1} WITH Classpath-exception-2.0",
         "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.parens/parens@1.0", "declared": "NOASSERTION", "concluded": f"({H1} OR {H2})"},
        {"purl": "pkg:maven/x.lowerops/lowerops@1.0", "declared": f"{H1} and ({H2} or {H1})",
         "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.mitand/mitand@1.0", "declared": f"MIT AND {H1}", "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.gplwith/gplwith@1.0", "declared": f"GPL-2.0-only WITH {H2}",
         "concluded": "NOASSERTION"},
        {"purl": ss.deb("wget", "1.25.0-2", distro=D13), "declared": "NOASSERTION", "concluded": H1},
        {"purl": ss.deb("libgcc-s1", "14.2.0-19", upstream="gcc-14", distro=D13), "declared": H1,
         "concluded": "NOASSERTION"},
        {"purl": ss.deb("libtasn1-6", "4.20.0-2", distro=D13), "declared": f"{H1} AND {H2}", "concluded": f"{H2} OR {H1}"},
        {"purl": "pkg:maven/x.files/files-hash@1.0", "declared": "NOASSERTION", "concluded": "NOASSERTION",
         "files": [H2, "NOASSERTION"]},
        {"purl": "pkg:maven/x.plain/plain@1.0", "declared": "NOASSERTION", "concluded": "NOASSERTION"},
        {"purl": ss.deb("libgnutls30t64", "3.8.9-3", distro=D13), "declared": f"{H1} AND GPL-3.0-or-later",
         "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.upper/upper@1.0", "declared": "LicenseRef-" + H1[len("LicenseRef-"):].upper(),
         "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.short/short@1.0", "declared": H1[:-1], "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.long/long@1.0", "declared": H1 + "0", "concluded": "NOASSERTION"},
        {"purl": "pkg:maven/x.sixteen/sixteen@1.0", "declared": "NOASSERTION", "concluded": "LicenseRef-40c7e1f2118531f0"},
    ]


HASH_UNLICENSED = {"wget", "libgcc-s1", "libtasn1-6", "files-hash", "with", "parens", "lowerops"}  # marked
PLAIN_UNLICENSED = {"plain"}  # listed, not marked
LICENSED_NEAR_MISSES = ("libgnutls30t64", "mitand", "gplwith", "upper", "short", "long", "sixteen")


def _purl_name(purl: str) -> str:
    return unquote(purl.split("?", 1)[0].split("@", 1)[0].rsplit("/", 1)[-1])


def marker_problems(lines: list[str], doc: dict[str, Any]) -> list[str]:
    """Each unlicensed row's printed line carries UNIDENTIFIED exactly when
    one of its licence fields is hash-only (oracle), and no other does."""
    p = []
    rows = {r["spdxid"]: r for r in oracle_unlicensed(doc)}
    for pkg in doc["packages"]:
        r = rows.get(pkg.get("SPDXID"))
        if r is None or not r["purl"]:
            continue
        fields = [pkg.get("licenseDeclared"), pkg.get("licenseConcluded"), *(pkg.get("licenseInfoFromFiles") or [])]
        want = any(hash_only(f) for f in fields)
        hits = [ln for ln in lines if _token(r["purl"]).search(ln)]
        if len(hits) != 1:
            p.append(f"{r['purl']} is printed on {len(hits)} lines, want 1: {hits}")
            continue
        if want and UNIDENTIFIED not in hits[0]:
            p.append(f"{r['purl']} has a hash-only licence field; its line {hits[0]!r} lacks {UNIDENTIFIED!r} (H-1)")
        if not want and "unidentified" in hits[0]:
            p.append(f"{r['purl']} has no hash-only field, but its line {hits[0]!r} is marked unidentified")
    return p


EVIL_NAME = "evil\x1b[31mRED\nneo4j:   pkg:maven/injected/line@1"
EVIL_PURL = "pkg:maven/evil/esc\x1b[31m@1\x9b2J\nINJECTED line"


def evil_rows() -> list[dict[str, Any]]:
    return [{"purl": None, "name": EVIL_NAME, "declared": "NOASSERTION", "concluded": "NOASSERTION"},
            {"purl": EVIL_PURL, "declared": "NOASSERTION", "concluded": "NOASSERTION"}]


def escape_problems(text_lines: list[str], *, rows: int | None = None) -> list[str]:
    p = []
    for ln in text_lines:
        bad = sorted({f"U+{ord(c):04X}" for c in CONTROL.findall(ln)})
        if bad:
            p.append(f"report line {ln!r} holds control characters {bad} (security L-3)")
    if rows is not None and len(text_lines) != rows:
        p.append(f"report_lines gave {len(text_lines)} strings, want {rows} (one header + one per row)")
    for ln in text_lines:
        for part in ln.splitlines()[1:]:
            p.append(f"a generator newline starts a line of its own: {part!r}")
    return p


class ReworkR1UnlicensedTest(unittest.TestCase):

    def test_hash_only_licences_count_as_unlicensed(self):
        """H-1: syft's `LicenseRef-<64 hex>` (unidentified text) is not a licence."""
        report = fn("unlicensed_report")
        doc = ss.spdx_doc("neo4j", hash_rows())
        want = oracle_unlicensed(doc)
        with self.subTest(part="precondition: the oracle lists the 7 hash rows and the plain row, nothing else"):
            self.assertEqual({_purl_name(r["purl"]) for r in want}, HASH_UNLICENSED | PLAIN_UNLICENSED)
        with self.subTest(part="report"):
            self.assertEqual(report_problems(report(copy.deepcopy(doc)), want), [])
        for field in ("licenseDeclared", "licenseConcluded"):
            with self.subTest(part=f"one hash in {field}, NOASSERTION in the other"):
                one = ss.spdx_doc("postgres", [{"purl": ss.deb("base-files", "12.4+deb12u15"),
                                                "declared": "NOASSERTION", "concluded": "NOASSERTION"}])
                one["packages"][1][field] = H1
                self.assertEqual(report_problems(report(one), oracle_unlicensed(one)), [])
                self.assertEqual(len(oracle_unlicensed(one)), 1)

    def test_hash_rows_marked_unidentified_in_report_lines(self):
        lines_of = fn("report_lines")
        doc = ss.spdx_doc("neo4j", hash_rows())
        lines = lines_of("neo4j", fn("unlicensed_report")(copy.deepcopy(doc)))
        self.assertTrue(isinstance(lines, list) and all(isinstance(x, str) for x in lines))
        self.assertEqual(marker_problems(lines, doc), [])
        with self.subTest(part="licensed near-misses are not printed"):
            for name in LICENSED_NEAR_MISSES:
                self.assertFalse([ln for ln in lines if f"/{name}@" in ln], f"{name} is licensed but printed")

    def test_real_package_lists_report_hash_only_rows(self):
        """The U3 SBOMs' real hash rows (security probe 1) are reported; the
        counts per image are evidence (u4/r1-*), not pinned here."""
        report = fn("unlicensed_report")
        seen = 0
        for image in ss.U3_IMAGES:
            doc = ss.u3_doc(image)
            seen += sum(1 for p in doc["packages"][1:]
                        if hash_only(p.get("licenseDeclared")) or hash_only(p.get("licenseConcluded")))
            with self.subTest(image=image):
                self.assertEqual(report_problems(report(doc), oracle_unlicensed(doc)), [])
        with self.subTest(part="precondition: the fixtures hold hash-only rows"):
            self.assertGreater(seen, 0)

    def test_report_lines_escape_control_characters(self):
        """L-3: a crafted name or purl cannot drive the terminal or forge a line."""
        doc = ss.spdx_doc("neo4j", evil_rows())
        report = fn("unlicensed_report")(copy.deepcopy(doc))
        with self.subTest(part="precondition: both rows are unlicensed"):
            self.assertEqual(len(oracle_unlicensed(doc)), 2)
        lines = fn("report_lines")("neo4j", report)
        self.assertEqual(escape_problems(lines, rows=3), [])
        with self.subTest(part="the rows are still recognisable"):
            self.assertEqual(len([ln for ln in lines if "evil" in ln]), 2, lines)

    def test_unlicensed_report_survives_odd_external_refs(self):
        """Review N4: never raise; a row without a usable purl has purl None."""
        report = fn("unlicensed_report")
        doc = ss.spdx_doc("phoenix", [{"purl": f"pkg:pypi/r{i}@1", "declared": "NOASSERTION"} for i in range(4)])
        pk = doc["packages"]
        pk[1]["externalRefs"] = 5
        pk[2]["externalRefs"] = {"referenceType": "purl", "referenceLocator": "pkg:pypi/r1@1"}
        pk[3]["externalRefs"] = [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                                  "referenceLocator": None}]
        try:
            got = report(copy.deepcopy(doc))
            lines = fn("report_lines")("phoenix", got)
        except Exception as exc:  # noqa: BLE001 - the contract is "report, not raise"
            self.fail(f"unlicensed_report/report_lines raised {type(exc).__name__}: {exc}")
        rows = {r.get("spdxid"): r.get("purl") for r in got.get("packages") or []}
        self.assertEqual(got.get("count"), 4)
        for i in (1, 2, 3):
            with self.subTest(row=i):
                self.assertIsNone(rows.get(pk[i]["SPDXID"], "absent"),
                                  "a row with no usable purl is reported with purl None (listed by SPDXID and name)")
        self.assertEqual(rows.get(pk[4]["SPDXID"]), "pkg:pypi/r3@1")
        self.assertFalse([ln for ln in lines if "None" in ln.split()], f"a None locator is printed as text: {lines}")


# -- M-1, M-2, L-1: `always` against the real package lists ------------------

def _upstream(purl: str) -> str:
    q = purl.split("?", 1)[1] if "?" in purl else ""
    for part in q.split("&"):
        k, _, v = part.partition("=")
        if k == "upstream":
            return unquote(v).split("@", 1)[0]
    return ""


# (image, exact `match`) pairs the rework adds (security M-1, L-1).
# Platform-sbom U4b (PSC-26, N16): neo4j's entries name ke-neo4j (re-targeted, U4b RED).
R1_ENTRIES = [("ke-app", "upstream=gcc-12"), ("postgres", "upstream=gcc-12"), ("ke-neo4j", "upstream=gcc-14"),
              ("phoenix", "upstream=gcc-14"), ("valkey", "upstream=busybox"), ("valkey", "upstream=apk-tools"),
              ("ke-gateway", "upstream=busybox"), ("ke-gateway", "upstream=apk-tools")]


def r1_required(image: str, purl: str) -> str | None:
    """Why a real package must be flagged after the rework, or None."""
    up = _upstream(purl)
    if image in ("ke-app", "postgres") and up == "gcc-12":
        return "M-1 GCC 12 runtime"
    if image in ("ke-neo4j", "phoenix") and up == "gcc-14":
        return "M-1 GCC 14 runtime"
    if image == "ke-neo4j" and purl.split("@", 1)[0] == "pkg:maven/jrt-fs/jrt-fs":
        return "M-2 Temurin jrt-fs.jar"
    if image in ("valkey", "ke-gateway") and _purl_name(purl) in ("busybox-binsh", "libapk"):
        return "L-1 " + _purl_name(purl)
    return None


# U3 fixture name -> the image name the policy uses (platform-sbom U4b, PSC-26).
U4B_POLICY_NAME = {"neo4j": "ke-neo4j"}


def real_always_problems(always: list[dict[str, Any]], matches: Any) -> list[str]:
    p = []
    have = {(e.get("image"), e.get("match")) for e in always if isinstance(e, dict)}
    for pair in R1_ENTRIES:
        if pair not in have:
            p.append(f"`always` has no {{image: {pair[0]}, match: {pair[1]}}} (security U4 M-1/L-1)")
    for fixture in ss.U3_IMAGES:
        # Platform-sbom U4b (PSC-26, N16): the U3 neo4j list is the official
        # image's; ke-neo4j's is that list minus the two products/ plugins,
        # which no `always` entry matches, so it stands in for ke-neo4j.
        image = U4B_POLICY_NAME.get(fixture, fixture)
        doc = ss.u3_doc(fixture)
        flagged, problems = matches(image, doc, always)
        p += [f"real {image} package list: {m}" for m in problems]
        required = 0
        for pkg in doc["packages"][1:]:
            purl = pkg_purl(pkg) or ""
            why = r1_required(image, purl)
            if why:
                required += 1
                if pkg["SPDXID"] not in flagged:
                    p.append(f"{image}: {purl} ({why}) is not flagged by `always`")
            elif image == "ke-neo4j" and purl.startswith("pkg:maven/") and pkg["SPDXID"] in flagged \
                    and purl.split("@", 1)[0] != "pkg:maven/org.neo4j/neo4j":
                p.append(f"ke-neo4j: {purl} is flagged; an `always` match is too wide (only neo4j and jrt-fs)")
        if image != "ke-gateway" and image != "valkey" and not required:
            p.append(f"precondition: the real {image} list has no package the rework must flag")
    return p


class ReworkR1PolicyTest(unittest.TestCase):

    def test_always_flags_gcc_runtime_jrt_fs_and_alpine_subpackages(self):
        self.assertTrue(POLICY.is_file(), POLICY_MISSING)
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        always = data.get("always") if isinstance(data, dict) else None
        with self.subTest(part="shape (N10)"):
            self.assertEqual(always_problems(always), [])
        with self.subTest(part="every entry matches a real package; the rework's components are flagged"):
            self.assertEqual(real_always_problems(always if isinstance(always, list) else [], fn("always_matches")),
                             [])
        with self.subTest(part="precondition: the Alpine fixtures hold busybox-binsh and libapk"):
            for image in ("valkey", "ke-gateway"):
                names = {_purl_name(pkg_purl(p) or "") for p in ss.u3_doc(image)["packages"][1:]}
                self.assertLessEqual({"busybox-binsh", "libapk"}, names, image)


# -- N1-N3, N6: the drift check's robustness and its success line -------------

def _lock_with_psycopg_c(versions: list[str]) -> str:
    """uv.lock with psycopg-c's block at versions[0] and one extra block per
    further version (a forked lock, design-notes N7)."""
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    real = ss.locked_version("psycopg-c")
    head = f'name = "psycopg-c"\nversion = "{real}"\n'
    assert text.count(head) == 1, "precondition: one psycopg-c block in uv.lock"
    text = text.replace(head, f'name = "psycopg-c"\nversion = "{versions[0]}"\n')
    for v in versions[1:]:
        text += f'\n[[package]]\nname = "psycopg-c"\nversion = "{v}"\nsource = {{ registry = "https://pypi.org/simple" }}\n'
    return text


class ReworkR1DriftTest(unittest.TestCase):

    def _cli(self, *, lock: str | None = None, app: dict | None = None, added_text: str | None = None
             ) -> tuple[Any, str]:
        import contextlib
        import io
        module = load_sbom_check()
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        app_p = ss.write_json(work / "app.json", app if app is not None else ss.ke_app_doc())
        base_p = ss.write_json(work / "base.json", ss.fake_base_doc())
        lock_p = work / "uv.lock"
        lock_p.write_text(lock if lock is not None else (ROOT / "uv.lock").read_text(encoding="utf-8"),
                          encoding="utf-8", newline="\n")
        added = ROOT / "tests" / "test_notice_ke_app.py"
        if added_text is not None:
            added = work / "added.py"
            added.write_text(added_text, encoding="utf-8")
        argv = ["drift", "--sbom", str(app_p), "--base", str(base_p), "--added-from", str(added),
                "--libpq", ss.libpq_pin(), "--lock", str(lock_p)]
        for rel in ss.LICENCE_FILES:
            argv += ["--licence", str(ROOT / rel)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = module.main(argv)
            except SystemExit as exc:
                code = exc.code
            except Exception as exc:  # noqa: BLE001 - drift must fail closed, not raise
                code = f"raised {type(exc).__name__}: {exc}"
        return code, out.getvalue() + err.getvalue()

    def _summary_problems(self, code: Any, output: str, psycopg_c: str) -> list[str]:
        if code != 0:
            return [f"drift exit {code!r}, want 0: {output}"]
        lines = [ln for ln in output.splitlines() if ln.strip()]
        if len(lines) != 1:
            return [f"drift printed {len(lines)} lines on success, want one summary line (review N6): {lines}"]
        p = []
        for word in [*sorted(ss.added_packages()), "no pip", ss.licence_version(), ss.libpq_pin(), psycopg_c]:
            if word not in lines[0]:
                p.append(f"the summary line {lines[0]!r} does not name {word!r} (review N6)")
        return p

    def test_drift_prints_one_summary_line_on_success(self):
        code, output = self._cli()
        self.assertEqual(self._summary_problems(code, output, ss.locked_version("psycopg-c")), [])

    def test_drift_accepts_forked_psycopg_c_lock(self):
        """Review N1 (N7 rule): the SBOM's psycopg-c is one of the locked versions."""
        real = ss.locked_version("psycopg-c")
        with self.subTest(case="locked at the listed version and another"):
            code, output = self._cli(lock=_lock_with_psycopg_c([real, "3.3.5"]))
            self.assertEqual(self._summary_problems(code, output, real), [])
        with self.subTest(case="the other order"):
            code, output = self._cli(lock=_lock_with_psycopg_c(["3.3.5", real]))
            self.assertEqual(self._summary_problems(code, output, real), [])
        with self.subTest(case="control: locked at two versions, neither listed"):
            code, output = self._cli(lock=_lock_with_psycopg_c(["3.3.5", "3.3.4"]))
            self.assertEqual(code, 1, output)
            self.assertIn("psycopg-c", output)

    def test_psycopg_check_splits_upstream_at_at(self):
        """Review N2: syft writes `upstream=<source>@<version>` when the source
        version differs; libpq5 is still from postgresql-<major>."""
        check = fn("psycopg_problems")
        pin, ver = ss.libpq_pin(), ss.locked_version("psycopg-c")
        major = int(pin.split(".", 1)[0])

        def doc(upstream: str) -> dict[str, Any]:
            rows = [r for r in ss.ke_app_rows() if "/libpq5@" not in (r["purl"] or "")]
            return ss.spdx_doc("ke-app", rows + [{"purl": ss.deb("libpq5", pin, upstream=upstream),
                                                  "declared": "PostgreSQL"}])
        with self.subTest(case=f"postgresql-{major}@{pin}"):
            self.assertEqual(check(doc(f"postgresql-{major}@{pin}"), pin, ver), [])
        for bad in (f"postgresql-{major + 1}@{pin}", f"postgresql-{major}0@{pin}", f"@postgresql-{major}"):
            with self.subTest(case=f"control: {bad}"):
                got = check(doc(bad), pin, ver)
                self.assertTrue(got and "libpq5" in "\n".join(got), f"upstream {bad!r} passed")

    def test_added_packages_errors_are_value_errors(self):
        """Review N3: the interface says ValueError; drift then exits 1."""
        read = fn("added_packages")
        for case, text in (("syntax error", "ADDED_PACKAGES = frozenset({'a'\n"),
                           ("unhashable element", "ADDED_PACKAGES = frozenset({('a', ['b'])})\n")):
            with self.subTest(case=case):
                try:
                    read(text)
                except ValueError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"added_packages raised {type(exc).__name__}, want ValueError: {exc}")
                else:
                    self.fail("added_packages accepted a broken ADDED_PACKAGES")
            with self.subTest(case=f"drift CLI: {case}"):
                code, output = self._cli(added_text=text)
                self.assertEqual(code, 1, output)
                self.assertNotIn("Traceback", output)


# -- B1, L-3, H-1 through bundle.sh (fake docker, real sbom_check.py) ----------

def tmpfs_mode_problems(data: dict[str, Any]) -> list[str]:
    """Review B1, security L-2 (u4/windows-run.txt 3c): /tmp is a 1777 tmpfs,
    so syft's uid can create XDG_CACHE_HOME=/tmp/cache; never exec."""
    svc = (data.get("services") or {}).get("sbom") or {}
    raw = svc.get("tmpfs")
    entries = [raw] if isinstance(raw, str) else [str(t) for t in raw or []]
    p = []
    if entries != ["/tmp:mode=1777"]:
        p.append(f"sbom: tmpfs is {entries}, want exactly ['/tmp:mode=1777'] (review B1)")
    for e in entries:
        if "exec" in (e.split(":", 1)[1].split(",") if ":" in e else []):
            p.append(f"sbom: tmpfs entry {e!r} is exec (keep the default noexec)")
    return p


class ReworkR1BundleTest(_BundleBase, unittest.TestCase):

    _syft_log = SbomCarryU4Test._syft_log
    _good = SbomCarryU4Test._good

    def test_sbom_tmp_tmpfs_is_mode_1777_not_exec(self):
        self.assertEqual(tmpfs_mode_problems(cs.load(SBOM_COMPOSE)), [])
        with self.subTest(part="the U2 pin still holds (tmpfs target exactly /tmp)"):
            from tests.test_sbom_generator import hardening_problems
            self.assertEqual(hardening_problems(cs.load(SBOM_COMPOSE)), [])

    def test_bundle_syft_runs_print_no_cache_warning(self):
        result, _, _, syft = self._good()
        self.assertTrue(syft, "precondition: the generator ran")
        warned = [ln for ln in self._out(result).splitlines() if CACHE_WARNING in ln]
        self.assertEqual(warned, [], "syft could not create its cache (review B1)")

    def _fake_syft(self, *, tmpfs: list[str], user: str, drop_env: tuple[str, ...] = ()) -> str:
        import yaml
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        data = cs.load(SBOM_COMPOSE)
        svc = data["services"]["sbom"]
        svc["tmpfs"] = tmpfs
        for k in drop_env:
            svc["environment"].pop(k, None)
        (d / cs.SBOM_COMPOSE_NAME).write_text(yaml.safe_dump(data), encoding="utf-8")
        shutil.copyfile(ROOT / ".env.example", d / ".env.example")
        (d / "in").mkdir()
        (d / "in" / "x.tar").write_bytes(b"not a real tar\n")
        (d / "out" / "tmp").mkdir(parents=True)
        env = {"PATH": self.path, "HOME": str(self.tmp),
               "FAKE_COMPOSE_FILE_IMAGES": json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": self.sbom_ref}}),
               "KE_SBOM_IN": str(d / "in"), "KE_SBOM_OUT": str(d / "out"), "KE_SBOM_USER": user}
        done = subprocess.run([str(self.tmp / "fakebin" / "docker"), "compose", "--env-file", ".env.example",
                               "-f", cs.SBOM_COMPOSE_NAME, "run", "--rm", "--pull", "never", "sbom",
                               "docker-archive:/in/x.tar", "--scope", "all-layers", "-o",
                               "spdx-json=/out/raw.spdx.json"],
                              cwd=d, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stderr

    def test_fake_syft_models_the_cache_warning(self):
        """Harness control (green on arrival): the fake warns exactly where
        the real syft did (u4/windows-run.txt 3c, security probe 5), so the
        no-warning tests above can fail."""
        cases = [("tmpfs /tmp (0755 root), uid 1000", ["/tmp"], "1000:1000", (), "mkdir /tmp/cache: permission denied"),
                 ("tmpfs /tmp:mode=0755, uid 1000", ["/tmp:mode=0755"], "1000:1000", (), "permission denied"),
                 ("tmpfs /tmp:mode=1777, uid 1000", ["/tmp:mode=1777"], "1000:1000", (), None),
                 ("tmpfs /tmp, root", ["/tmp"], "0:0", (), None),
                 ("no XDG_CACHE_HOME: /.cache on the read-only root", ["/tmp:mode=1777"], "1000:1000",
                  ("XDG_CACHE_HOME",), "mkdir /.cache: read-only file system")]
        for case, tmpfs, user, drop, want in cases:
            with self.subTest(case=case):
                err = self._fake_syft(tmpfs=tmpfs, user=user, drop_env=drop)
                warned = [ln for ln in err.splitlines() if CACHE_WARNING in ln]
                if want is None:
                    self.assertEqual(warned, [])
                else:
                    self.assertEqual(len(warned), 1, err)
                    self.assertIn(want, warned[0])

    def test_bundle_output_marks_unidentified_and_escapes_generator_text(self):
        """H-1 and L-3 end to end: bundle.sh prints the checker's report."""
        # Platform-sbom U4b (PSC-26 *Bundled as first-party*): the neo4j service's image is
        # saved as ke-neo4j (images/ke-neo4j.tar, app/sboms/ke-neo4j.spdx.json); re-targeted
        # by the tester, U4b RED.
        raw = ss.spdx_doc("ke-neo4j", hash_rows() + evil_rows())
        result, _, out, _ = self._good(FAKE_SYFT_RAW=json.dumps({"ke-neo4j": json.dumps(raw)}))
        output = self._out(result)
        doc = json.loads((out / "app" / "sboms" / "ke-neo4j.spdx.json").read_text(encoding="utf-8"))
        with self.subTest(part="count: the hash rows are unlicensed"):
            line = next((ln for ln in output.splitlines() if re.search(r"(?i)\bunlicensed\b", ln)
                         and re.search(r"(?<![\w.-])ke-neo4j(?![\w.-])", ln)), "")
            n = len(oracle_unlicensed(doc))
            self.assertEqual(n, len(HASH_UNLICENSED | PLAIN_UNLICENSED) + 2, "precondition")
            self.assertRegex(line.replace("ke-neo4j", " "), rf"(?<![\w.]){n}(?![\w.])")
        with self.subTest(part="H-1 marker"):
            plain = copy.deepcopy(doc)
            plain["packages"] = [p for p in plain["packages"] if "evil" not in json.dumps(p)]
            self.assertEqual(marker_problems(output.splitlines(), plain), [])
        with self.subTest(part="L-3: no control character from the generator reaches the output"):
            self.assertNotIn("\x1b", output)
            self.assertNotIn("\x9b", output)
            self.assertFalse([ln for ln in output.splitlines() if ln.startswith("INJECTED")
                              or (ln.lstrip().startswith("ke-neo4j:   pkg:maven/injected/line@1"))
                              or ln.startswith("RED")], "a generator newline forged an output line")


GIB_KB = 1024 * 1024  # df -Pk reports 1024-byte blocks


class ReworkR1DiskFloorTest(_BundleBase, unittest.TestCase):
    """Review N5 (design-notes "N1 amendment, U4 rework"): the 7 GiB floor is
    measured on --out and on dirname(--out), where the SBOM work dir unpacks."""

    def _df_paths(self) -> list[str]:
        return [ln.split()[-1] for ln in self.df_log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _floor(self, out_gib: int, parent_gib: int) -> tuple[subprocess.CompletedProcess, list[list[str]], Path]:
        """--out pre-created empty (a mount point, say) on its own filesystem."""
        out = self.tmp / f"floor{self.n + 1}" / "bundle-amd64"
        out.mkdir(parents=True)
        return self._bundle(out, FAKE_DF_AVAIL_KB=str(50 * GIB_KB),
                            FAKE_DF_AVAIL_BY_PATH=json.dumps({str(out): out_gib * GIB_KB,
                                                              str(out.parent): parent_gib * GIB_KB}))

    def _refused(self, result: subprocess.CompletedProcess, calls: list[list[str]], out: Path, path: Path) -> None:
        output = self._out(result)
        self.assertNotEqual(result.returncode, 0, "bundled with 3 GiB free:\n" + output)
        self.assertRegex(output, rf"need 7 GiB free on {re.escape(str(path))}, found 3 GiB\b",
                         f"the refusal does not name {path}")
        self.assertEqual(self._saves(calls), [], "docker save ran below the disk floor")
        self.assertTrue(out.is_dir() and not any(out.iterdir()), "--out is not left empty")
        self.assertFalse((out.parent / f"{out.name}.manifest.sha256").exists(), "a record was written")
        self.assertEqual([p.name for p in out.parent.iterdir()], [out.name], "something was left beside --out")

    def test_bundle_floor_on_out_parent_when_out_exists(self):
        result, calls, out = self._floor(out_gib=50, parent_gib=3)
        self._refused(result, calls, out, out.parent)

    def test_bundle_floor_on_out_when_out_exists(self):
        result, calls, out = self._floor(out_gib=3, parent_gib=50)
        self._refused(result, calls, out, out)

    def test_bundle_floor_both_filesystems_fit(self):
        result, _, out = self._floor(out_gib=50, parent_gib=50)
        self.assertEqual(result.returncode, 0, self._out(result))
        self.assertEqual(sorted(self._df_paths()), sorted([str(out), str(out.parent)]),
                         "df probes --out and dirname(--out), once each")

    def test_bundle_floor_probes_once_on_one_filesystem(self):
        """--out absent: both checks resolve to dirname(--out), so one df."""
        result, _, out = self._bundle(FAKE_DF_AVAIL_KB=str(50 * GIB_KB))
        self.assertEqual(result.returncode, 0, self._out(result))
        self.assertEqual(self._df_paths(), [str(out.parent)])


class ReworkR1OfflineTest(toc._OfflineBase):
    """The offline drift step: N6 summary, N7 label, B1 (fake docker)."""

    _host_setup = toc.OfflineCheckScriptTest._host_setup
    _sbom_env = toc.OfflineCheckScriptTest._sbom_env
    _host = toc.OfflineCheckScriptTest._host
    _event = staticmethod(toc.OfflineCheckScriptTest._event)
    _project = staticmethod(toc.OfflineCheckScriptTest._project)
    _table = DriftOfflineCheckTest._table

    def test_offline_drift_step_labelled_summarised_and_quiet(self):
        result, records, _ = self._host(FAKE_DOCKER_IMAGES=self._table())
        output = self._out(result)
        self.assertEqual(result.returncode, 0, output)
        checks = [r for r in records if r["argv"][:1] == ["run"] and "drift" in r["argv"]
                  and any(a.endswith("sbom_check.py") for a in r["argv"])]
        self.assertEqual(len(checks), 1, "precondition: one drift checker run")
        project = next((self._project(r) for r in records if self._event(r) == "up dind"), None)
        self.assertTrue(project, "precondition: the dind project is known")
        with self.subTest(part="N7: the checker run carries the offline project's compose label"):
            argv = checks[0]["argv"]
            image_at = next((i for i, a in enumerate(argv) if a.startswith("ke-app:")), len(argv))
            head = argv[:image_at]
            labels = [b for a, b in zip(head, head[1:]) if a in ("--label", "-l")]
            labels += [a.split("=", 1)[1] for a in head if a.startswith("--label=")]
            want = f"com.docker.compose.project={project}"
            self.assertTrue(any(lab == want or lab.startswith(want + "-") for lab in labels),
                            f"labels {labels}, want {want}[-<suffix>] (review N7)")
        with self.subTest(part="N6: the summary line reaches the check's output"):
            self.assertTrue([ln for ln in output.splitlines() if "no pip" in ln and ss.libpq_pin() in ln],
                            "no drift summary line naming `no pip` and the libpq5 pin")
        with self.subTest(part="B1: the base generator run prints no cache warning"):
            self.assertEqual([ln for ln in output.splitlines() if CACHE_WARNING in ln], [])


if __name__ == "__main__":
    unittest.main()
