"""platform-sbom U1 (PSC-14): NOTICE.md names what ke-app's shipped stage holds.

Criteria: docs/requirements.md PSC-14 (amended 2026-10-22 for PSC-17 and
Q64, 2026-10-23 after the U1 review, and 2026-10-23 for U1 round 2: pip
dropped, human), test tags `test_notice_has_ke_app_base_paragraph`,
`test_notice_names_libpq_as_a_debian_package`,
`test_notice_points_to_generated_source_code_section`,
`test_notice_names_cpython_incorporated_licences` and
`test_notice_cites_no_repo_evidence_path`. Design: docs/architecture.md
ADR-KE-016 point 9 and docs/evidence/platform-sbom/design-notes.md N10 and
N10a (U1 round 2: ke-app ships no pip).

Interface pinned here (tester, U1 RED 2026-10-22; rework round 1 and round 2
2026-10-23 per the orchestrator's rulings on review B1/B3/B4/N3/N4, security
M-1/M-2/L-1/L-3/L-5/L-6/L-8, and the human's ruling to drop pip; round 3
security L-9/I-4; round 4 2026-10-23 security L-9b/I-8, PSC-14 amended round 4):
- The section is a markdown heading `## Base of `ke-app`` (or `Base image
  of`, any level from ## down), running to the next heading of the same or
  a higher level. Its blocks are paragraphs and top-level list items (a
  nested item stays with its parent); an element's words must sit in one
  block.
- Expected values come from committed files, not from copies in this test:
  - the base reference and the libpq pin from docker/app.Dockerfile: the
    FROM of the stage whose files ship, byte for byte, and the global
    `ARG LIBPQ_VERSION=`. That stage is the last one, or, when the last
    stage is `FROM scratch` starting `COPY --from=<stage> / /`, <stage>
    (`runtime`, N10a; tests.test_psycopg_c.shipped_stage);
  - the CPython minor and the Debian codename from that reference, parsed
    strictly as `[registry/]python:X.Y-slim-CODENAME@sha256:<64 hex>` with
    no default: a reference that does not parse is a problem (review B1);
  - the Debian release from DEBIAN_RELEASES; an unknown codename is a
    problem (review B1);
  - the Debian packages the shipped stage adds: the module constant
    ADDED_PACKAGES (security U0 I-5); the shipped stage's apt install names
    must each be in it. No `docs/evidence/**` file is read: evidence is
    history, not a source of truth (orchestrator, U1 RED).
- CPython's licence is SPDX `Python-2.0`, with a pointer to
  `/usr/local/lib/python<X.Y>/LICENSE.txt` that says the file holds that
  licence stack only, and names `licenses/CPython-<X.Y>-incorporated.txt`
  for the code CPython builds in (security M-2, L-5).
- Every SBOM mention in the section is conditional, "where the bundle
  carries one" (security L-1).
- pip is not shipped (human, 2026-10-23): a block of the section says so;
  every block of the section that names pip is negated, and none gives a
  pip version, `vendor.txt`, an MIT/Apache-2.0/MPL-2.0 identifier or a
  `licenses/` path (no pip licence bullet). NOTICE.md never names
  `licenses/MPL-2.0.txt` (PSC-14: reverted), and names
  `licenses/Apache-2.0.txt` only in a block that names KaRaMeL or
  `base-files` and not pip: it ships for KaRaMeL, not for pip (U1 round 4:
  security L-9b fix 5; PSC-14 amended 2026-10-23, round 4, which supersedes
  round 2's "names neither" here).
- The "Source code" block carries security L-6's sentence verbatim
  (whitespace aside), and NOTICE.md nowhere says a bundle "carries no
  third-party source code".
- `licenses/CPython-<X.Y>-incorporated.txt` (N10a): four header lines,
    CPython X.Y.Z: "Licenses and Acknowledgements for Incorporated Software"
    Source: https://raw.githubusercontent.com/python/cpython/vX.Y.Z/Doc/license.rst
    Source sha256: <64 lower-case hex>
    Extract: from that heading line to the end of the file, unmodified.
  then a blank line, then the extract: the heading line, its `=` underline
  (at least as long), the heading only once, and expat and libmpdec named
  (NOTICE.md names both). LF only. The URL's tag equals line 1's version;
  X.Y equals the base tag's minor. A block of NOTICE.md that names the file
  gives the header's source URL. U4 checks the micro against the SBOM.
- `licenses/CPython-<X.Y>-HACL.txt` (U1 round 3, security L-9; N10, N10a):
  four header lines,
    CPython X.Y.Z: HACL* licence header (MIT), Modules/_hacl/
    Source: Python-X.Y.Z/Modules/_hacl/Hacl_Hash_SHA2.c
    Tarball: https://www.python.org/ftp/python/X.Y.Z/Python-X.Y.Z.tar.xz
    Tarball sha256: <64 lower-case hex>
  then a blank line, then the extract: first line exactly `/* MIT License`,
  last line exactly ` */` and no earlier ` */` line (sed stops at the
  first), `HACL* Contributors` in it. LF only. Line 1's version equals the
  incorporated file's line 1 version and the `Source:` and both `Tarball:`
  versions; X.Y equals the base tag's minor. A block of NOTICE.md names the
  file with the header's tarball URL and `Modules/_hacl/Hacl_Hash_SHA2.c`.
- `licenses/CPython-<X.Y>-KaRaMeL.txt` (U1 round 4, security L-9b fix 2):
  four header lines,
    CPython X.Y.Z: KaRaMeL licence header (Apache-2.0), Modules/_hacl/include/krml/
    Source: Python-X.Y.Z/Modules/_hacl/include/krml/internal/target.h
    Tarball: https://www.python.org/ftp/python/X.Y.Z/Python-X.Y.Z.tar.xz
    Tarball sha256: <64 lower-case hex>
  then a blank line, then the 2-line extract: exactly `/* Copyright (c)
  INRIA and Microsoft Corporation. All rights reserved.`, then a line that
  is `Licensed under the Apache 2.0 License. */` after its indent. LF only.
  Line 1's version equals the Source:/Tarball: versions and the
  incorporated and HACL files' line 1; X.Y equals the base tag's minor; the
  Tarball sha256 line equals the HACL file's (the same verified tarball). A
  block of NOTICE.md names the file with
  `Modules/_hacl/include/krml/internal/target.h` and the tarball URL.
- `licenses/Apache-2.0.txt` (security L-9b fix 1): its sha256 is
  APACHE_2_SHA256, the byte copy, with no header, of base-files'
  `/usr/share/common-licenses/Apache-2.0` in the pinned base. A block of
  NOTICE.md names it with `base-files`, that path and that sha256.
- The CPython bullet (each block naming `/usr/local/lib/pythonX.Y/LICENSE.txt`)
  says what each file holds and claims no complete set (N10, round 3): it
  calls the incorporated file CPython's list, names the HACL file with
  `HACL*`, `MIT` and `_md5`, `_sha1`, `_sha2`, `_sha3`, and has none of
  "whose texts are in", all, every, complete, full, entire, whole. Round 4
  (security L-9b fix 3, I-8): its HACL clause reads "the licence of the
  HACL* hash code ... is in" the HACL file, and it names KaRaMeL, INRIA and
  Microsoft, Apache-2.0, the KaRaMeL file and `licenses/Apache-2.0.txt`.
- Every `licenses/...` path NOTICE.md names is listed by `git ls-files --
  licenses` (U1 round 3, security I-4, review N12): bundle.sh ships only
  those. If git cannot run, that is a problem, never a skip.
- NOTICE.md cites no `docs/evidence/` path (review B4, security L-8).
- psycopg-binary may be named only in a block that is dated history: one
  that starts with a date or "History:" (review N4).
- Each check is a `*_problems(paths)` function; each test runs it on a
  target fixture (passes), on controls that must pass, on controls that
  each drop or break one element (each must fail), and then on the
  repository's files.

Retired in U1 round 2 (PSC-14, human ruling 2026-10-23: pip dropped):
`test_licenses_carry_texts_for_pip_vendored_licences` and its check, since
the image carries no pip and licenses/ gains no Apache-2.0 or MPL-2.0 text.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.engine_support import ROOT
from tests.test_image_scan import _stages
from tests.test_psycopg_c import _apt_installs, _packages, _Scratch, libpq_pin, shipped_stage

NOTICE = ROOT / "NOTICE.md"
APP_DOCKERFILE = ROOT / "docker" / "app.Dockerfile"
LICENSES = ROOT / "licenses"
# The Debian packages ke-app's shipped stage adds to its base: libpq5 and what
# apt pulls in for it. Source: docs/evidence/platform-sbom/u0/security.md I-5
# (the krb5 libraries and libkeyutils1 are already in the base). The fast
# tests cannot see the image, so here this constant is checked only against
# the Dockerfile's apt names. U4's SBOM test (PSC-22, full; orchestrator
# ruling on review B3, option (a), 2026-10-23) checks that the real image's
# dpkg packages not in the base equal this set, that it lists no pip, and
# that its CPython version is the one the incorporated-licence file names.
ADDED_PACKAGES = frozenset({"libpq5", "libldap-2.5-0", "libsasl2-2", "libsasl2-modules-db"})
# Debian codename -> release, for the base tag's `-slim-CODENAME` (review B1).
# An unknown codename is a problem: add the row when the base moves.
DEBIAN_RELEASES = {"bookworm": "12", "trixie": "13"}

HEADING_RE = re.compile(r"^(#{2,6})[ \t]+Base (?:image )?of `?ke-app`?[ \t]*$", re.M)
BASE_REF_RE = re.compile(
    r"(?:[a-z0-9][a-z0-9.-]*(?::\d+)?/(?:[a-z0-9._-]+/)*)?"
    r"python:(?P<minor>\d+\.\d+)-slim-(?P<codename>[a-z]+)@sha256:[0-9a-f]{64}")
# Dated history: the block itself starts with a date or "History:" (review N4).
DATED_RE = re.compile(r"^(?:(?:[-*+]|\d+[.)])\s+)?(?:\*\*|_)?(?:20\d{2}-\d{2}-\d{2}\b|History:)")
NEGATION_RE = re.compile(r"(?i)\b(?:no|not|never|without|none|neither|nor)\b|n't\b")
UV_RE = re.compile(r"(?<![\w.-])uv(?![\w-]|\.lock)")
PIP_RE = re.compile(r"(?<![\w.-])pip(?![\w-])")
PIP_VERSION_RE = re.compile(r"(?<![\w-])pip`?\s+(?:version\s+)?`?\d+(?:\.\d+)+")
POSTGRESQL_LICENCE_RE = re.compile(
    r"(?i)PostgreSQL`?\s+licen[cs]e|licen[cs]e[:\s]+`?PostgreSQL\b|\(\s*`?PostgreSQL`?\s*\)")
LICENCE_RE = re.compile(r"(?i)licen[cs]e|/usr/share/doc/")
PYTHON_LICENCE_RE = re.compile(r"(?<![\w.-])Python-2\.0(?![\w.])")
USR_LOCAL_RE = re.compile(r"/usr/local(?![\w/])")
SBOM_RE = re.compile(r"\bSBOM\b")
CONDITIONAL_SBOM_RE = re.compile(r"(?i)where the bundle carries one")
# Security M-2: LICENSE.txt holds the PSF/BeOpen/CNRI/CWI stack only.
STACK_ONLY_RE = re.compile(r"(?i)\blicen[cs]e stack only\b")
LICENCE_TXT_OVERCLAIM_RE = re.compile(r"LICENSE\.txt`?[^.]*\bholds\b[^.]*\b(?:third-party|bundles?|incorporated)\b")
# No pip licence bullet: what a pip block must not carry (human, 2026-10-23).
PIP_BANNED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a pip version", PIP_VERSION_RE),
    ("pip/_vendor/vendor.txt", re.compile(r"vendor\.txt")),
    ("an MIT, Apache-2.0 or MPL-2.0 identifier",
     re.compile(r"(?<![\w.-])(?:MIT|Apache-2\.0|MPL-2\.0)(?![\w.-])")),
    ("a licenses/ path", re.compile(r"licenses/")),
)
# Reverted with pip (PSC-14): NOTICE.md never names MPL-2.0.txt. Apache-2.0.txt
# ships for KaRaMeL (U1 round 4: security L-9b fix 5, PSC-14 amended round 4),
# so NOTICE.md names it only in a block that names KaRaMeL or base-files, and
# never in one that names pip.
PIP_ONLY_LICENCE_FILES = ("licenses/MPL-2.0.txt",)
APACHE_REL = "licenses/Apache-2.0.txt"
# KaRaMeL as a word, not as part of a `licenses/...-KaRaMeL.txt` path.
KARAMEL_RE = re.compile(r"(?<![\w./-])KaRaMeL(?![\w-]|\.\w)")
# The pointer (first sentence): THIRD_PARTY_NOTICES.md's "Source code" section
# and `sources/`, each in its positive form, so the L-6 sentence ("... has no
# "Source code" section has no `sources/`") cannot stand in.
TPN_POINTER_RE = re.compile(r"THIRD_PARTY_NOTICES\.md(?!`?\s+has no)")
SOURCE_CODE_POINTER_RE = re.compile(r"(?<!has no )(?<!has no [\"“])\bSource code\b")
SOURCES_POINTER_RE = re.compile(r"\bin `?sources/")
# Security L-6's sentence, verbatim (it replaced M-1's), and the claim it fixed.
L6_SENTENCE = ('A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has no `sources/`, '
               'so it does not itself provide the source that a GPL-family licence requires.')
NO_SOURCE_CLAIM = "carries no third-party source code"
# Review B4, security L-8: a bundle carries no docs/evidence/.
EVIDENCE_RE = re.compile(r"(?i)docs[/\\]+evidence\b")
# The CPython incorporated-licence file (N10a; security L-5, M-2).
INCORPORATED_HEADING = "Licenses and Acknowledgements for Incorporated Software"
HEADER_1_RE = re.compile(r'CPython (?P<version>(?P<minor>\d+\.\d+)\.\d+): "' + INCORPORATED_HEADING + '"')
HEADER_2_RE = re.compile(r"Source: (?P<url>https://raw\.githubusercontent\.com/python/cpython/"
                         r"v(?P<tag>\d+\.\d+\.\d+)/Doc/license\.rst)")
HEADER_3_RE = re.compile(r"Source sha256: [0-9a-f]{64}")
HEADER_4 = "Extract: from that heading line to the end of the file, unmodified."
INCORPORATED_NAMED = ("expat", "libmpdec")
# The CPython HACL* notice file (U1 round 3, security L-9; N10a).
HACL_HEADER_1_RE = re.compile(r"CPython (?P<version>(?P<minor>\d+\.\d+)\.\d+): HACL\* licence header \(MIT\), "
                              r"Modules/_hacl/")
HACL_HEADER_2_RE = re.compile(r"Source: Python-(?P<version>\d+\.\d+\.\d+)/Modules/_hacl/Hacl_Hash_SHA2\.c")
HACL_HEADER_3_RE = re.compile(r"Tarball: (?P<url>https://www\.python\.org/ftp/python/(?P<dir>\d+\.\d+\.\d+)/"
                              r"Python-(?P<file>\d+\.\d+\.\d+)\.tar\.xz)")
HACL_HEADER_4_RE = re.compile(r"Tarball sha256: [0-9a-f]{64}")
HACL_FIRST = "/* MIT License"
HACL_LAST = " */"
HACL_CONTRIBUTORS = "HACL* Contributors"
HACL_SOURCE_FILE = "Modules/_hacl/Hacl_Hash_SHA2.c"
HACL_MODULES = ("_md5", "_sha1", "_sha2", "_sha3")
# Security I-8: the HACL clause names the licence as what the file holds.
HACL_LICENCE_OF_RE = r"\bthe licen[cs]e of the HACL\* hash code\b[^;]*?\bis in `?"
# The CPython KaRaMeL notice file and the Apache-2.0 text (U1 round 4,
# security L-9b; PSC-14 amended round 4).
KARAMEL_HEADER_1_RE = re.compile(r"CPython (?P<version>(?P<minor>\d+\.\d+)\.\d+): KaRaMeL licence header "
                                 r"\(Apache-2\.0\), Modules/_hacl/include/krml/")
KARAMEL_HEADER_2_RE = re.compile(r"Source: Python-(?P<version>\d+\.\d+\.\d+)/Modules/_hacl/include/krml/internal/"
                                 r"target\.h")
KARAMEL_SOURCE_FILE = "Modules/_hacl/include/krml/internal/target.h"
KARAMEL_FIRST = "/* Copyright (c) INRIA and Microsoft Corporation. All rights reserved."
KARAMEL_LAST = "Licensed under the Apache 2.0 License. */"
# The SPDX identifier, not the `licenses/Apache-2.0.txt` or common-licenses path.
APACHE_SPDX_RE = re.compile(r"(?<![\w./-])Apache-2\.0(?![\w-]|\.\w)")
# base-files 12.4+deb12u15's /usr/share/common-licenses/Apache-2.0 (11358 B) in
# python:3.12-slim-bookworm@sha256:34386ef0...7258 (security re-check 3, L-9b
# fix 1; identical in 2c662c94 and 071866c7). A canonical text, so the exact
# hash is pinned; if a base bump changes it, re-copy the file and update this.
APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
APACHE_SOURCE = "/usr/share/common-licenses/Apache-2.0"
# N10 round 3: the CPython bullet claims no complete set of licences.
COMPLETENESS_RE = re.compile(r"(?i)\bwhose\s+(?:licen[cs]e\s+)?texts?\s+(?:are|is)\s+in\b"
                             r"|\b(?:all|every|complete(?:ly)?|full(?:y)?|entire(?:ly)?|whole)\b")
LIST_RE = re.compile(r"\blist\b")
# Security I-4: a `licenses/` file NOTICE.md names (a trailing full stop is not
# part of the name).
LICENCE_PATH_RE = re.compile(r"(?<![\w./-])licenses/[A-Za-z0-9_+-]+(?:\.[A-Za-z0-9_+-]+)*")
# The work tree whose index the tracked-licence check reads (the u1 driver's
# reach points it at a scratch copy).
GIT_ROOT = ROOT


# --------------------------------------------------------------------------
# Reading the committed sources
# --------------------------------------------------------------------------

def runtime_stage(dockerfile: Path) -> tuple[str, list[str], list[str]]:
    """(the shipped stage's FROM reference, package names its apt installs
    name, problems). The shipped stage is the last stage, or the stage a
    `FROM scratch` last stage copies `/` from (N10a)."""
    stages = _stages(dockerfile)
    if not stages:
        return "", [], [f"{dockerfile.name}: no FROM"]
    shipped, _, problems = shipped_stage(stages)
    if shipped is None:
        return "", [], [f"{dockerfile.name}: {p}" for p in problems]
    names = []
    for keyword, rest in shipped["body"]:
        if keyword == "RUN":
            for words in _apt_installs(rest):
                names += [p.split("=", 1)[0] for p in _packages(words)]
    problems = [] if names else [f"{dockerfile.name}: the shipped stage installs no apt package"]
    return shipped["ref"], names, problems


def parse_base_ref(ref: str) -> tuple[str | None, str | None, str | None, list[str]]:
    """(CPython minor, Debian codename, Debian release, problems); no default."""
    m = BASE_REF_RE.fullmatch(ref)
    if not m:
        return None, None, None, [f"the shipped stage's base reference {ref!r} does not parse as "
                                  f"[registry/]python:X.Y-slim-CODENAME@sha256:<64 hex> (review B1; no default)"]
    codename = m["codename"]
    release = DEBIAN_RELEASES.get(codename)
    if release is None:
        return m["minor"], codename, None, [f"unknown Debian codename {codename!r} in {ref!r}; "
                                            f"DEBIAN_RELEASES knows {sorted(DEBIAN_RELEASES)}"]
    return m["minor"], codename, release, []


# --------------------------------------------------------------------------
# Reading NOTICE.md
# --------------------------------------------------------------------------

def base_section(text: str) -> str | None:
    m = HEADING_RE.search(text)
    if not m:
        return None
    level = len(m.group(1))
    rest = text[m.end():]
    end = re.search(rf"^#{{1,{level}}}[ \t]", rest, re.M)
    return rest[:end.start()] if end else rest


def blocks(text: str) -> list[str]:
    """Paragraphs and top-level list items, whitespace flattened."""
    out: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                out.append(current)
            current = []
            continue
        if re.match(r"^(?:[-*+]|\d+[.)])\s", line) and current:
            out.append(current)
            current = []
        current.append(line)
    if current:
        out.append(current)
    return [" ".join(" ".join(b).split()) for b in out]


def _named(name: str, text: str) -> bool:
    return re.search(rf"(?<![\w.+-]){re.escape(name)}(?![\w+-]|\.\w)", text) is not None


def _has(b: str, p: str | re.Pattern[str]) -> bool:
    return (p.search(b) is not None) if isinstance(p, re.Pattern) else (p in b)


def _any_block(bs: list[str], *patterns: str | re.Pattern[str]) -> bool:
    return any(all(_has(b, p) for p in patterns) for b in bs)


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------

def base_paragraph_problems(notice: Path, dockerfile: Path,
                            added: frozenset[str] = ADDED_PACKAGES) -> list[str]:
    """test_notice_has_ke_app_base_paragraph on these two files and the
    added-package list."""
    ref, runtime_names, problems = runtime_stage(dockerfile)
    pin, pin_problems = libpq_pin(dockerfile)
    problems += pin_problems
    py, codename, release, ref_problems = parse_base_ref(ref)
    problems += ref_problems
    for name in runtime_names:
        if name not in added:
            problems.append(f"{dockerfile.name}: the shipped stage installs {name}, which is not in "
                            f"ADDED_PACKAGES {sorted(added)} (update it from the image, security I-5)")
    text = notice.read_text(encoding="utf-8")
    flat_text = " ".join(text.split())
    for name in PIP_ONLY_LICENCE_FILES:
        if name in flat_text:
            problems.append(f"NOTICE.md names {name}; the pip licence texts are reverted (PSC-14, pip dropped)")
    for b in blocks(text):
        if APACHE_REL in b and (PIP_RE.search(b) or not (KARAMEL_RE.search(b) or "base-files" in b)):
            problems.append(f"NOTICE.md names {APACHE_REL} in a block that names pip, or names neither KaRaMeL "
                            f"nor base-files: it ships for KaRaMeL, not for pip (PSC-14 round 4, security L-9b): "
                            f"{b[:120]!r}")
    section = base_section(text)
    if section is None:
        return problems + ["NOTICE.md has no `## Base of `ke-app`` section (PSC-14, ADR-KE-016 point 9)"]
    flat = " ".join(section.split())
    bs = blocks(section)

    if not ref or ref not in flat:
        problems.append(f"the section does not give the shipped stage's base reference {ref!r} byte for byte "
                        f"(docker/app.Dockerfile)")
    if py is not None:
        licence_txt = f"/usr/local/lib/python{py}/LICENSE.txt"
        incorporated = f"licenses/CPython-{py}-incorporated.txt"
        cpython = re.compile(rf"\bCPython {re.escape(py)}\b")
        if not _any_block(bs, cpython, USR_LOCAL_RE, PYTHON_LICENCE_RE, licence_txt):
            problems.append(f"no block names CPython {py} under /usr/local with its licence Python-2.0 and "
                            f"the pointer {licence_txt} (review N3, security L-3)")
        elif not _any_block(bs, cpython, licence_txt, STACK_ONLY_RE, incorporated):
            problems.append(f"the CPython block does not say that {licence_txt} holds that licence stack only and "
                            f"name {incorporated} for the code CPython builds in (security M-2)")
        for b in bs:
            if licence_txt in b and LICENCE_TXT_OVERCLAIM_RE.search(b):
                problems.append(f"the section says LICENSE.txt holds the licences of the code CPython builds in; "
                                f"it holds the licence stack only (security M-2): {b[:120]!r}")
    if release is not None and codename is not None:
        if not _any_block(bs, re.compile(rf"\bDebian {release} \({re.escape(codename)}\)"),
                          "/usr/share/doc/", "copyright", SBOM_RE):
            problems.append(f"no block names the base's Debian {release} ({codename}) packages with their "
                            f"licences in /usr/share/doc/*/copyright and the SBOM")
    for b in bs:
        if SBOM_RE.search(b) and not CONDITIONAL_SBOM_RE.search(b):
            problems.append(f"the section names the SBOM unconditionally; say \"where the bundle carries one\" "
                            f"(security L-1): {b[:120]!r}")
    for name in sorted(set(added) | set(runtime_names)):
        if not any(_named(name, b) and LICENCE_RE.search(b) for b in bs):
            problems.append(f"the section does not name {name}, a Debian package the shipped stage adds, "
                            f"with its licence")
    for name in runtime_names:
        if pin and not any(_named(name, b) and pin in b for b in bs):
            problems.append(f"the section does not give {name} at the pinned LIBPQ_VERSION {pin}")
    pip_blocks = [b for b in bs if PIP_RE.search(b)]
    if not pip_blocks:
        problems.append("the section does not say pip is not shipped (human ruling 2026-10-23, PSC-14)")
    for b in pip_blocks:
        if not NEGATION_RE.search(b):
            problems.append(f"the section names pip as shipped: {b[:120]!r}")
        for what, pattern in PIP_BANNED:
            if pattern.search(b):
                problems.append(f"a pip block gives {what}: no pip licence bullet, pip is not shipped "
                                f"(PSC-14): {b[:120]!r}")
    uv_blocks = [b for b in bs if UV_RE.search(b)]
    if not uv_blocks:
        problems.append("the section does not say uv is not shipped (it runs only in the builder stage, PSC-17)")
    for b in uv_blocks:
        if not NEGATION_RE.search(b):
            problems.append(f"the section names uv as shipped: {b[:120]!r}")
    return problems


def libpq_debian_problems(notice: Path) -> list[str]:
    """test_notice_names_libpq_as_a_debian_package on `notice`."""
    problems: list[str] = []
    text = notice.read_text(encoding="utf-8")
    bs = blocks(text)
    if not any(_named("libpq5", b) and "Debian" in b and POSTGRESQL_LICENCE_RE.search(b) for b in bs):
        problems.append("no block of NOTICE.md names libpq5 as a Debian package under the PostgreSQL licence")
    for b in bs:
        if re.search(r"(?i)psycopg[-_]binary", b) and not DATED_RE.match(b):
            problems.append(f"NOTICE.md names psycopg-binary outside dated history (a block that starts "
                            f"with a date or \"History:\", review N4): {b[:120]!r}")
    for line in text.splitlines():
        if re.match(r"^\s*#+\s.*(?i:vendored)", line):
            problems.append(f"NOTICE.md has a vendored-libraries heading: {line.strip()!r}")
        if line.lstrip().startswith("|") and re.search(r"\.so\b|\.libs\b", line):
            problems.append(f"NOTICE.md has a table row of vendored libraries: {line.strip()[:120]!r}")
    return problems


def pointer_problems(notice: Path) -> list[str]:
    """test_notice_points_to_generated_source_code_section on `notice`
    (ADR-KE-016 point 9; N10 "and one pointer"; N15 U1; security U1 M-1, L-6)."""
    text = notice.read_text(encoding="utf-8")
    bs = blocks(text)
    problems = []
    if NO_SOURCE_CLAIM in " ".join(text.split()):
        problems.append(f"NOTICE.md says a bundle {NO_SOURCE_CLAIM!r}; the images carry .py source (security L-6)")
    pointer = [b for b in bs if all(_has(b, p) for p in (TPN_POINTER_RE, SOURCE_CODE_POINTER_RE,
                                                          SOURCES_POINTER_RE))]
    if not pointer:
        return problems + ["no block of NOTICE.md points to the \"Source code\" section of THIRD_PARTY_NOTICES.md "
                           "and `sources/` (ADR-KE-016 point 9, N10)"]
    if not any(L6_SENTENCE in b for b in pointer):
        problems.append(f"the \"Source code\" block does not carry security L-6's sentence verbatim: "
                        f"{L6_SENTENCE!r}")
    return problems


def incorporated_licence_problems(notice: Path, licenses: Path, dockerfile: Path) -> list[str]:
    """test_notice_names_cpython_incorporated_licences on these files (N10a;
    security L-5, M-2; PSC-14)."""
    ref, _, problems = runtime_stage(dockerfile)
    py, _, _, ref_problems = parse_base_ref(ref)
    problems += ref_problems
    if py is None:
        return problems
    rel = f"licenses/CPython-{py}-incorporated.txt"
    bs = blocks(notice.read_text(encoding="utf-8"))
    if not any(rel in b for b in bs):
        problems.append(f"NOTICE.md does not name {rel} (PSC-14, security L-5)")
    path = licenses / rel.split("/", 1)[1]
    if not path.is_file():
        return problems + [f"{rel} is missing (the base tag's CPython is {py})"]
    raw = path.read_bytes()
    if b"\r" in raw:
        problems.append(f"{rel} has CR line endings; the extract is the LF bytes of Doc/license.rst")
    lines = raw.decode("utf-8", errors="replace").split("\n")
    if len(lines) < 7:
        return problems + [f"{rel} has {len(lines)} lines: no header and extract"]
    m1, m2 = HEADER_1_RE.fullmatch(lines[0]), HEADER_2_RE.fullmatch(lines[1])
    if not m1:
        problems.append(f'{rel} line 1 is not `CPython X.Y.Z: "{INCORPORATED_HEADING}"`: {lines[0][:100]!r}')
    if not m2:
        problems.append(f"{rel} line 2 is not `Source: https://raw.githubusercontent.com/python/cpython/vX.Y.Z/"
                        f"Doc/license.rst`: {lines[1][:100]!r}")
    if not HEADER_3_RE.fullmatch(lines[2]):
        problems.append(f"{rel} line 3 is not `Source sha256: <64 hex>`: {lines[2][:100]!r}")
    if lines[3] != HEADER_4:
        problems.append(f"{rel} line 4 is not {HEADER_4!r}: {lines[3][:100]!r}")
    if lines[4] != "":
        problems.append(f"{rel} line 5 is not blank: {lines[4][:100]!r}")
    if m1 and m2 and m1["version"] != m2["tag"]:
        problems.append(f"{rel}: line 1 names CPython {m1['version']} but the source URL's tag is v{m2['tag']}")
    if m1 and m1["minor"] != py:
        problems.append(f"{rel}: line 1 names CPython {m1['version']}, not the base tag's {py}")
    extract = lines[5:]
    if extract[0] != INCORPORATED_HEADING or not re.fullmatch(r"=+", extract[1]) \
            or len(extract[1]) < len(INCORPORATED_HEADING):
        problems.append(f"{rel}: the extract does not start with the heading line {INCORPORATED_HEADING!r} and "
                        f"its `=` underline")
    if extract.count(INCORPORATED_HEADING) != 1:
        problems.append(f"{rel}: the heading line occurs {extract.count(INCORPORATED_HEADING)} times in the "
                        f"extract, want once")
    body = "\n".join(extract)
    for word in INCORPORATED_NAMED:
        if word not in body:
            problems.append(f"{rel}: the extract does not name {word} (NOTICE.md says its text is there; M-2)")
    if m2 and not any(rel in b and m2["url"] in b for b in bs):
        problems.append(f"no block of NOTICE.md names {rel} with the header's source URL {m2['url']}")
    return problems


def hacl_licence_problems(notice: Path, licenses: Path, dockerfile: Path) -> list[str]:
    """test_notice_names_cpython_incorporated_licences, round 3 part (security
    L-9; N10, N10a): the CPython bullet's wording, the HACL* file's header and
    extract, and NOTICE.md's Licence-texts block for it."""
    ref, _, problems = runtime_stage(dockerfile)
    py, _, _, ref_problems = parse_base_ref(ref)
    problems += ref_problems
    if py is None:
        return problems
    rel = f"licenses/CPython-{py}-HACL.txt"
    incorporated = f"licenses/CPython-{py}-incorporated.txt"
    licence_txt = f"/usr/local/lib/python{py}/LICENSE.txt"
    bs = blocks(notice.read_text(encoding="utf-8"))
    bullets = [b for b in bs if licence_txt in b]
    if not bullets:
        problems.append(f"no block of NOTICE.md names {licence_txt} (the CPython bullet)")
    for b in bullets:
        needs: tuple[tuple[str, str | re.Pattern[str]], ...] = (
            (incorporated, incorporated), (rel, rel), ("HACL*", "HACL*"), ("MIT", re.compile(r"\bMIT\b")),
            *((m, re.compile(rf"(?<![\w]){m}(?![\w])")) for m in HACL_MODULES),
            ("the word 'list' (the incorporated file is CPython's own list)", LIST_RE))
        for what, needle in needs:
            if not _has(b, needle):
                problems.append(f"the CPython bullet does not name {what}; it says what each file holds "
                                f"(N10 round 3, security L-9): {b[:100]!r}")
        if not re.search(HACL_LICENCE_OF_RE + re.escape(rel), b):
            problems.append(f"the CPython bullet does not say \"the licence of the HACL* hash code ... is in\" {rel}: "
                            f"the file holds the code's licence, not the code (security I-8): {b[:100]!r}")
        claim = COMPLETENESS_RE.search(b)
        if claim:
            problems.append(f"the CPython bullet claims a complete set ({claim.group(0)!r}); CPython's list omits "
                            f"HACL* (N10 round 3, security L-9)")
    path = licenses / rel.split("/", 1)[1]
    if not path.is_file():
        return problems + [f"{rel} is missing (the base tag's CPython is {py}; security L-9)"]
    raw = path.read_bytes()
    if b"\r" in raw:
        problems.append(f"{rel} has CR line endings; the extract is the LF bytes of {HACL_SOURCE_FILE}")
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if text.endswith("\n"):
        lines = lines[:-1]
    if len(lines) < 7:
        return problems + [f"{rel} has {len(lines)} lines: no header and extract"]
    m1, m2, m3 = (HACL_HEADER_1_RE.fullmatch(lines[0]), HACL_HEADER_2_RE.fullmatch(lines[1]),
                  HACL_HEADER_3_RE.fullmatch(lines[2]))
    if not m1:
        problems.append(f"{rel} line 1 is not `CPython X.Y.Z: HACL* licence header (MIT), Modules/_hacl/`: "
                        f"{lines[0][:100]!r}")
    if not m2:
        problems.append(f"{rel} line 2 is not `Source: Python-X.Y.Z/{HACL_SOURCE_FILE}`: {lines[1][:100]!r}")
    if not m3:
        problems.append(f"{rel} line 3 is not `Tarball: https://www.python.org/ftp/python/X.Y.Z/Python-X.Y.Z.tar.xz`: "
                        f"{lines[2][:100]!r}")
    if not HACL_HEADER_4_RE.fullmatch(lines[3]):
        problems.append(f"{rel} line 4 is not `Tarball sha256: <64 lower-case hex>`: {lines[3][:100]!r}")
    if lines[4] != "":
        problems.append(f"{rel} line 5 is not blank: {lines[4][:100]!r}")
    if m1:
        versions = {"Source:": m2["version"] if m2 else None, "Tarball: directory": m3["dir"] if m3 else None,
                    "Tarball: file": m3["file"] if m3 else None}
        for where, version in versions.items():
            if version is not None and version != m1["version"]:
                problems.append(f"{rel}: line 1 names CPython {m1['version']} but {where} names {version}")
        if m1["minor"] != py:
            problems.append(f"{rel}: line 1 names CPython {m1['version']}, not the base tag's {py}")
        inc = licenses / incorporated.split("/", 1)[1]
        inc_m = HEADER_1_RE.fullmatch(inc.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]) \
            if inc.is_file() else None
        if inc_m is None:
            problems.append(f"{rel}: cannot compare line 1 with {incorporated}, which is missing or has no line 1 "
                            f"version")
        elif inc_m["version"] != m1["version"]:
            problems.append(f"{rel}: line 1 names CPython {m1['version']} but {incorporated} names "
                            f"{inc_m['version']}")
    extract = lines[5:]
    if extract[0] != HACL_FIRST:
        problems.append(f"{rel}: the extract's first line is {extract[0][:60]!r}, want {HACL_FIRST!r}")
    if extract[-1] != HACL_LAST:
        problems.append(f"{rel}: the extract's last line is {extract[-1][:60]!r}, want {HACL_LAST!r}")
    if extract.count(HACL_LAST) > 1:
        problems.append(f"{rel}: the extract has {extract.count(HACL_LAST)} {HACL_LAST!r} lines; it ends at the "
                        f"first (sed -n '1,/^ \\*\\/$/p', N10a)")
    if HACL_CONTRIBUTORS not in "\n".join(extract):
        problems.append(f"{rel}: the extract does not hold {HACL_CONTRIBUTORS!r}")
    if m3 and not any(rel in b and m3["url"] in b and HACL_SOURCE_FILE in b for b in bs):
        problems.append(f"no block of NOTICE.md names {rel} with {HACL_SOURCE_FILE} and the header's tarball URL "
                        f"{m3['url']}")
    return problems


def _karamel_file_problems(licenses: Path, rel: str, py: str, bs: list[str]) -> list[str]:
    """The KaRaMeL file's header, its 2-line extract, and NOTICE.md's
    Licence-texts block for it (security L-9b fix 2 and 4)."""
    path = licenses / rel.split("/", 1)[1]
    if not path.is_file():
        return [f"{rel} is missing (the base tag's CPython is {py}; security L-9b)"]
    problems: list[str] = []
    raw = path.read_bytes()
    if b"\r" in raw:
        problems.append(f"{rel} has CR line endings; the extract is the LF bytes of {KARAMEL_SOURCE_FILE}")
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if text.endswith("\n"):
        lines = lines[:-1]
    if len(lines) < 7:
        return problems + [f"{rel} has {len(lines)} lines: not a 4-line header, a blank line and the 2-line extract"]
    m1, m2, m3 = (KARAMEL_HEADER_1_RE.fullmatch(lines[0]), KARAMEL_HEADER_2_RE.fullmatch(lines[1]),
                  HACL_HEADER_3_RE.fullmatch(lines[2]))
    if not m1:
        problems.append(f"{rel} line 1 is not `CPython X.Y.Z: KaRaMeL licence header (Apache-2.0), "
                        f"Modules/_hacl/include/krml/`: {lines[0][:100]!r}")
    if not m2:
        problems.append(f"{rel} line 2 is not `Source: Python-X.Y.Z/{KARAMEL_SOURCE_FILE}`: {lines[1][:100]!r}")
    if not m3:
        problems.append(f"{rel} line 3 is not `Tarball: https://www.python.org/ftp/python/X.Y.Z/Python-X.Y.Z.tar.xz`: "
                        f"{lines[2][:100]!r}")
    m4 = HACL_HEADER_4_RE.fullmatch(lines[3])
    if not m4:
        problems.append(f"{rel} line 4 is not `Tarball sha256: <64 lower-case hex>`: {lines[3][:100]!r}")
    if lines[4] != "":
        problems.append(f"{rel} line 5 is not blank: {lines[4][:100]!r}")
    hacl = licenses / f"CPython-{py}-HACL.txt"
    hacl_lines = hacl.read_text(encoding="utf-8", errors="replace").split("\n") if hacl.is_file() else []
    if m1:
        versions = {"Source:": m2["version"] if m2 else None, "Tarball: directory": m3["dir"] if m3 else None,
                    "Tarball: file": m3["file"] if m3 else None}
        for where, version in versions.items():
            if version is not None and version != m1["version"]:
                problems.append(f"{rel}: line 1 names CPython {m1['version']} but {where} names {version}")
        if m1["minor"] != py:
            problems.append(f"{rel}: line 1 names CPython {m1['version']}, not the base tag's {py}")
        inc = licenses / f"CPython-{py}-incorporated.txt"
        others = (("licenses/" + inc.name, HEADER_1_RE,
                   inc.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0] if inc.is_file() else None),
                  ("licenses/" + hacl.name, HACL_HEADER_1_RE, hacl_lines[0] if hacl_lines else None))
        for other, regex, line1 in others:
            om = regex.fullmatch(line1) if line1 is not None else None
            if om is None:
                problems.append(f"{rel}: cannot compare line 1 with {other}, which is missing or has no line 1 "
                                f"version")
            elif om["version"] != m1["version"]:
                problems.append(f"{rel}: line 1 names CPython {m1['version']} but {other} names {om['version']}")
    if m4 and (len(hacl_lines) < 4 or hacl_lines[3] != lines[3]):
        problems.append(f"{rel}: line 4 is not the HACL file's `Tarball sha256:` line; both come from the same "
                        f"verified tarball (PSC-14 round 4)")
    extract = lines[5:]
    if len(extract) != 2:
        problems.append(f"{rel}: the extract has {len(extract)} lines, want 2 (sed -n '1,/\\*\\//p' of "
                        f"{KARAMEL_SOURCE_FILE}, security L-9b)")
    if extract[0] != KARAMEL_FIRST:
        problems.append(f"{rel}: the extract's first line is {extract[0][:80]!r}, want {KARAMEL_FIRST!r}")
    if extract[-1].strip() != KARAMEL_LAST:
        problems.append(f"{rel}: the extract's last line is {extract[-1][:80]!r}, want {KARAMEL_LAST!r} after "
                        f"its indent")
    if m3 and not any(rel in b and m3["url"] in b and KARAMEL_SOURCE_FILE in b for b in bs):
        problems.append(f"no block of NOTICE.md names {rel} with {KARAMEL_SOURCE_FILE} and the header's tarball "
                        f"URL {m3['url']} (security L-9b fix 4)")
    return problems


def _apache_problems(licenses: Path, apache_sha256: str, bs: list[str]) -> list[str]:
    """licenses/Apache-2.0.txt's sha256 and NOTICE.md's Licence-texts block
    for it (security L-9b fix 1 and 4)."""
    problems: list[str] = []
    path = licenses / APACHE_REL.split("/", 1)[1]
    if not path.is_file():
        problems.append(f"{APACHE_REL} is missing: the Apache License 2.0 that KaRaMeL's notice names "
                        f"(security L-9b)")
    else:
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != apache_sha256:
            problems.append(f"{APACHE_REL} has sha256 {got}, want {apache_sha256}: a byte copy, with no header, "
                            f"of {APACHE_SOURCE} from base-files in the pinned base (security L-9b fix 1)")
    if not any(APACHE_REL in b and "base-files" in b and APACHE_SOURCE in b and apache_sha256 in b for b in bs):
        problems.append(f"no block of NOTICE.md names {APACHE_REL} with base-files, {APACHE_SOURCE} and its "
                        f"sha256 {apache_sha256} (security L-9b fix 4)")
    return problems


def karamel_licence_problems(notice: Path, licenses: Path, dockerfile: Path,
                             apache_sha256: str = APACHE_2_SHA256) -> list[str]:
    """test_notice_names_cpython_incorporated_licences, round 4 part
    (security L-9b; PSC-14 amended round 4): the CPython bullet names
    KaRaMeL, INRIA and Microsoft, Apache-2.0 and both files; the KaRaMeL
    file's header and extract; licenses/Apache-2.0.txt's sha256
    (`apache_sha256`, by default the base-files copy, APACHE_2_SHA256); and
    NOTICE.md's Licence-texts blocks for both."""
    ref, _, problems = runtime_stage(dockerfile)
    py, _, _, ref_problems = parse_base_ref(ref)
    problems += ref_problems
    if py is None:
        return problems
    rel = f"licenses/CPython-{py}-KaRaMeL.txt"
    licence_txt = f"/usr/local/lib/python{py}/LICENSE.txt"
    bs = blocks(notice.read_text(encoding="utf-8"))
    bullets = [b for b in bs if licence_txt in b]
    if not bullets:
        problems.append(f"no block of NOTICE.md names {licence_txt} (the CPython bullet)")
    for b in bullets:
        needs: tuple[tuple[str, str | re.Pattern[str]], ...] = (
            ("KaRaMeL", KARAMEL_RE), ("INRIA and Microsoft", "INRIA and Microsoft"),
            ("the licence Apache-2.0", APACHE_SPDX_RE), (rel, rel), (APACHE_REL, APACHE_REL))
        for what, needle in needs:
            if not _has(b, needle):
                problems.append(f"the CPython bullet does not name {what}: the HACL* code compiles in KaRaMeL "
                                f"headers (INRIA and Microsoft, Apache-2.0; security L-9b fix 3): {b[:100]!r}")
    return problems + _karamel_file_problems(licenses, rel, py, bs) + _apache_problems(licenses, apache_sha256, bs)


def untracked_licence_problems(notice: Path, repo: Path, git: str = "git") -> list[str]:
    """test_notice_named_licence_files_are_tracked on `notice` and the index of
    `repo` (security I-4, review N12): bundle.sh ships only `git ls-files --
    licenses`. A git that cannot run is a problem, never a skip."""
    named = sorted(set(LICENCE_PATH_RE.findall(notice.read_text(encoding="utf-8"))))
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    # Read `repo`'s own index: no discovery of a repository above it.
    env["GIT_CEILING_DIRECTORIES"] = str(Path(repo).resolve().parent)
    try:
        result = subprocess.run([git, "-C", str(repo), "ls-files", "-z", "--", "licenses"],
                                capture_output=True, env=env, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"`git ls-files -- licenses` could not run in {repo} ({exc!r}); this check needs git and the "
                f"work tree (security I-4)"]
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace").strip()[:200]
        return [f"`git ls-files -- licenses` failed in {repo} (exit {result.returncode}): {err}"]
    tracked = {p for p in result.stdout.decode("utf-8").split("\0") if p}
    return [f"NOTICE.md names {p}, which git does not track, so bundle.sh would not ship it "
            f"(`git add` it; security I-4)" for p in named if p not in tracked]


def evidence_path_problems(notice: Path) -> list[str]:
    """test_notice_cites_no_repo_evidence_path on `notice` (review B4,
    security L-8): a bundle carries only app/docs/quickstart.md from docs/."""
    return [f"NOTICE.md cites {m.group(0)!r}, a repository path no bundle carries (review B4, security L-8): "
            f"{line.strip()[:120]!r}"
            for line in notice.read_text(encoding="utf-8").splitlines() for m in EVIDENCE_RE.finditer(line)]


# --------------------------------------------------------------------------
# Fixtures: a target per N10/N10a, and controls. The fixture values (digest,
# pin, CPython micro) are not the repository's, so a check that read a copy
# instead of the given files would be caught.
# --------------------------------------------------------------------------

FIX_DIGEST = "a" * 64
FIX_REF = "python:3.12-slim-bookworm@sha256:" + FIX_DIGEST
FIX_PIN = "15.99-0+deb12u9"
FIX_CPYTHON = "3.12.99"
FIX_URL = f"https://raw.githubusercontent.com/python/cpython/v{FIX_CPYTHON}/Doc/license.rst"
REG_313_REF = "docker.io/library/python:3.13-slim-bookworm@sha256:" + FIX_DIGEST
TRIXIE_REF = "python:3.12-slim-trixie@sha256:" + FIX_DIGEST
# U0's shape: the last stage is FROM the base.
TARGET_DOCKERFILE = f"""\
ARG LIBPQ_VERSION={FIX_PIN}
FROM {FIX_REF} AS builder
ARG LIBPQ_VERSION
RUN apt-get update \\
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
FROM {FIX_REF}
ARG LIBPQ_VERSION
RUN apt-get update \\
 && apt-get install -y --no-install-recommends libpq5=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
USER ke
"""
# N10a's shape: `runtime` ships, the last stage is FROM scratch.
TARGET_DOCKERFILE_FLAT = f"""\
ARG LIBPQ_VERSION={FIX_PIN}
FROM {FIX_REF} AS builder
ARG LIBPQ_VERSION
RUN apt-get update \\
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
FROM {FIX_REF} AS runtime
ARG LIBPQ_VERSION
RUN apt-get update \\
 && apt-get install -y --no-install-recommends libpq5=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
RUN python -m pip uninstall -y pip \\
 && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl
FROM scratch
COPY --from=runtime / /
ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8
USER ke
"""
_HEAD = """\
# Notice

Knowledge Engine is licensed under the MIT licence.

## psycopg (LGPL-3.0-only)

`psycopg-c` is compiled against Debian's `libpq5`.

2026-10-22: `psycopg-c` replaced psycopg-binary (PSC-25).

"""
# N10 round 3 (security L-9): what each file holds, no complete set claimed.
# Round 4 (security L-9b fix 3, I-8): "the licence of the HACL* hash code ...
# is in", and the KaRaMeL clause with its two files.
_KARAMEL_TAIL = (", and that code\n"
                 "  compiles in KaRaMeL headers (Copyright INRIA and Microsoft Corporation,\n"
                 "  Apache-2.0), whose notice is in `licenses/CPython-3.12-KaRaMeL.txt` and\n"
                 "  licence text in `licenses/Apache-2.0.txt`.")
_M2_SENTENCE = (" CPython also builds in third-party code under\n"
                "  its own licences. CPython's own list of it (among them expat and libmpdec)\n"
                "  is in `licenses/CPython-3.12-incorporated.txt`; the licence of\n"
                "  the HACL* hash code (MIT) in `_md5`, `_sha1`, `_sha2` and `_sha3`, which\n"
                "  that list omits, is in `licenses/CPython-3.12-HACL.txt`" + _KARAMEL_TAIL)
# Round 3's sentence (today's NOTICE.md): no KaRaMeL, and "the HACL* hash
# code ... is in" (I-8).
_R3_M2_SENTENCE = (" CPython also builds in third-party code under\n"
                   "  its own licences. CPython's own list of it (among them expat and libmpdec)\n"
                   "  is in `licenses/CPython-3.12-incorporated.txt`; the HACL* hash code (MIT)\n"
                   "  in `_md5`, `_sha1`, `_sha2` and `_sha3`, which that list omits, is in\n"
                   "  `licenses/CPython-3.12-HACL.txt`.")
_OLD_CPYTHON_TAIL = "holds\n  that licence stack only." + _M2_SENTENCE
_CPYTHON = ("- CPython 3.12 under `/usr/local`, under the Python License 2.0 (SPDX\n"
            "  `Python-2.0`: the PSF licence stacked on the BeOpen, CNRI and CWI\n"
            "  licences). `/usr/local/lib/python3.12/LICENSE.txt` inside the image "
            + _OLD_CPYTHON_TAIL + "\n")
# Round 2's sentence (today's NOTICE.md): "whose texts are in" claims the set.
_ROUND2_M2_SENTENCE = (" CPython also builds in third-party code under\n"
                       "  its own licences (among them expat and libmpdec), whose texts are in\n"
                       "  `licenses/CPython-3.12-incorporated.txt`.")
_PIP = ("pip is not shipped: the shipped stage removes the base's pip and\n"
        "`ensurepip`'s bundled pip wheel, so the image carries neither pip nor\n"
        "the packages pip vendors.\n")
_BASE = f"""\
## Base of `ke-app`

The shipped stage of `docker/app.Dockerfile` builds on
`{FIX_REF}`. Besides `/opt/venv` and `/app` it holds:

{_CPYTHON}\
- The Debian 12 (bookworm) packages of the base image, each under its own
  licence in `/usr/share/doc/*/copyright` inside the image and, where the
  bundle carries one, in the image's SBOM.
- The Debian packages the shipped stage adds: `libpq5` {FIX_PIN}, under the
  PostgreSQL licence, and what apt pulls in for it: `libldap-2.5-0`,
  `libsasl2-2` and `libsasl2-modules-db`, with their licences in
  `/usr/share/doc/*/copyright` (and the SBOM where the bundle carries one).

{_PIP}
uv is not shipped: it runs only in the `builder` stage, which does not ship.

"""
_L6 = ('A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has\n'
       "no `sources/`, so it does not itself provide the source that a\n"
       "GPL-family licence requires.\n")
_INCORPORATED_PARA = f"""\
`licenses/CPython-3.12-incorporated.txt` is the "Licenses and
Acknowledgements for Incorporated Software" section of CPython {FIX_CPYTHON}'s
`Doc/license.rst`, unmodified, fetched over HTTPS from
{FIX_URL};
its header gives the fetched file's sha256.
"""
FIX_TARBALL = f"https://www.python.org/ftp/python/{FIX_CPYTHON}/Python-{FIX_CPYTHON}.tar.xz"
_HACL_PARA = f"""\
`licenses/CPython-3.12-HACL.txt` is the MIT licence header of
`Modules/_hacl/Hacl_Hash_SHA2.c` in CPython {FIX_CPYTHON}'s release tarball
{FIX_TARBALL},
unmodified; its header gives the tarball's sha256.
"""
# Security L-9b fix 4. The KaRaMeL paragraph wraps its URL unlike the HACL
# one, so a control can change one without the other.
_KARAMEL_PARA = f"""\
`licenses/CPython-3.12-KaRaMeL.txt` is the licence header of
`Modules/_hacl/include/krml/internal/target.h` in CPython {FIX_CPYTHON}'s release
tarball {FIX_TARBALL}, unmodified;
its header gives the tarball's sha256.
"""
# A stand-in for base-files' 11358-byte text; the repository's file is checked
# against APACHE_2_SHA256 last.
FIX_APACHE_TEXT = ("\n                                 Apache License\n"
                   "                           Version 2.0, January 2004\n"
                   "                        http://www.apache.org/licenses/\n\n"
                   "   (stand-in for the text base-files ships)\n")
FIX_APACHE_SHA = hashlib.sha256(FIX_APACHE_TEXT.encode("utf-8")).hexdigest()
_APACHE_PARA = f"""\
`licenses/Apache-2.0.txt` is the Apache License 2.0 as Debian's
`base-files` ships it at `/usr/share/common-licenses/Apache-2.0` in the
`ke-app` base image, unmodified (sha256
`{FIX_APACHE_SHA}`).
"""
_POINTER = f"""\
## Source code

`THIRD_PARTY_NOTICES.md` says, in its "Source code" section, for each
GPL-family component whether its source is in `sources/` of this bundle.
{_L6}
## Licence texts

`licenses/LGPL-3.0.txt` is the GNU text.

{_INCORPORATED_PARA}
{_HACL_PARA}
{_KARAMEL_PARA}
{_APACHE_PARA}"""
TARGET_NOTICE = _HEAD + _BASE + _POINTER


def incorporated_text(version: str = FIX_CPYTHON, url: str | None = None, sha: str = "b" * 64,
                      extract: str | None = None) -> str:
    """A file in the N10a shape: four header lines, a blank, the extract (a
    stand-in for CPython's text; the repository's file is checked last)."""
    url = url or f"https://raw.githubusercontent.com/python/cpython/v{version}/Doc/license.rst"
    if extract is None:
        extract = (f"{INCORPORATED_HEADING}\n{'=' * len(INCORPORATED_HEADING)}\n\n"
                   "This section is an incomplete, but growing list of licenses and acknowledgements\n"
                   "for third-party software incorporated in the Python distribution.\n\n"
                   "Mersenne Twister\n----------------\n\nA C-program for MT19937.\n\n"
                   "expat\n-----\n\nThe :mod:`pyexpat <xml.parsers.expat>` extension is built using an included copy\n"
                   "of the expat sources unless the build is configured ``--with-system-expat``.\n\n"
                   "libmpdec\n--------\n\nThe :mod:`!_decimal` C extension underlying the :mod:`decimal` module is built\n"
                   "using an included copy of the libmpdec library.\n")
    return (f'CPython {version}: "{INCORPORATED_HEADING}"\nSource: {url}\nSource sha256: {sha}\n'
            f"{HEADER_4}\n\n{extract}")


TARGET_INCORPORATED = incorporated_text()


def _swap(old: str, new: str, text: str = TARGET_NOTICE) -> str:
    assert old in text, old
    return text.replace(old, new)


def _ref(new_ref: str, notice: str = TARGET_NOTICE, dockerfile: str = TARGET_DOCKERFILE) -> tuple[str, str]:
    """(NOTICE, Dockerfile) with the base reference replaced in both."""
    assert FIX_REF in dockerfile
    return _swap(FIX_REF, new_ref, notice), dockerfile.replace(FIX_REF, new_ref)


def _runtime_ref(new_ref: str) -> str:
    """The N10a Dockerfile with only `runtime`'s FROM changed (the builder keeps FIX_REF)."""
    old = f"FROM {FIX_REF} AS runtime"
    assert old in TARGET_DOCKERFILE_FLAT
    return TARGET_DOCKERFILE_FLAT.replace(old, f"FROM {new_ref} AS runtime")


def _to_313(text: str) -> str:
    return _swap("python3.12/LICENSE.txt", "python3.13/LICENSE.txt",
                 _swap("CPython 3.12", "CPython 3.13", _swap("CPython-3.12-incorporated", "CPython-3.13-incorporated",
                                                             text)))


_A = ADDED_PACKAGES
# Today's (round 1) pip bullet, which round 2 removes.
_OLD_PIP_BULLET = (
    "- The base's own pip 25.0.1 in the system site-packages (MIT). It is outside\n"
    "  `uv.lock`, so it is not in the generated table of `THIRD_PARTY_NOTICES.md`.\n"
    "  The packages pip vendors, listed in `pip/_vendor/vendor.txt`, keep their\n"
    "  own licences (among them Apache-2.0 and MPL-2.0); pip 25.0.1 ships no\n"
    "  licence files for them, so the bundle carries those two texts as\n"
    "  `licenses/Apache-2.0.txt` and `licenses/MPL-2.0.txt`.\n")
_ADDED_END = "carries one).\n\n"
# name -> (NOTICE.md, app.Dockerfile, added packages); each must fail.
BASE_CONTROLS: dict[str, tuple[str, str, frozenset[str]]] = {
    "no Base of ke-app heading": (_swap("## Base of `ke-app`", "## The ke-app image"), TARGET_DOCKERFILE, _A),
    "elements under another heading": (_swap("## Base of `ke-app`\n", "## Base of `ke-app`\n\n## Other\n"),
                                       TARGET_DOCKERFILE, _A),
    "base digest differs in NOTICE": (_swap(FIX_REF, FIX_REF[:-1] + "b"), TARGET_DOCKERFILE, _A),
    "base digest differs in Dockerfile": (TARGET_NOTICE, TARGET_DOCKERFILE.replace(FIX_DIGEST, "c" * 64), _A),
    "unparseable ref: no codename (B1)": (*_ref("python:3.12-slim@sha256:" + FIX_DIGEST), _A),
    "unparseable ref: no digest (B1)": (*_ref("python:3.12-slim-bookworm"), _A),
    "unparseable ref: short digest (B1)": (*_ref("python:3.12-slim-bookworm@sha256:" + "a" * 63), _A),
    "unparseable ref: not python (B1)": (*_ref("pypy:3.10-slim-bookworm@sha256:" + FIX_DIGEST), _A),
    "unknown codename sid (B1)": (*_ref("python:3.12-slim-sid@sha256:" + FIX_DIGEST), _A),
    "no CPython": (_swap("CPython 3.12 under", "Python under"), TARGET_DOCKERFILE, _A),
    "CPython licence PSF-2.0, not Python-2.0 (N3)": (_swap("`Python-2.0`", "`PSF-2.0`"), TARGET_DOCKERFILE, _A),
    "CPython without the LICENSE.txt pointer (N3)": (
        _swap("`/usr/local/lib/python3.12/LICENSE.txt` inside the image holds", "The image holds"),
        TARGET_DOCKERFILE, _A),
    "LICENSE.txt pointer names another minor (N3)": (_swap("python3.12/LICENSE.txt", "python3.13/LICENSE.txt"),
                                                     TARGET_DOCKERFILE, _A),
    "CPython without /usr/local": (_swap("CPython 3.12 under `/usr/local`,", "CPython 3.12,"),
                                   TARGET_DOCKERFILE, _A),
    "CPython minor is not the base tag's": (*_ref(FIX_REF.replace("python:3.12", "python:3.13")), _A),
    "registry-prefixed 3.13 ref, NOTICE still says 3.12 (B1 P1)": (*_ref(REG_313_REF), _A),
    "trixie ref, NOTICE still says Debian 12 (B1 P2)": (*_ref(TRIXIE_REF), _A),
    "M-2: today's LICENSE.txt overclaim": (
        _swap(_OLD_CPYTHON_TAIL, "holds\n  the full licence stack and the licences of the third-party code CPython\n"
                                 "  bundles."), TARGET_DOCKERFILE, _A),
    "M-2: LICENSE.txt without 'licence stack only'": (_swap("that licence stack only.", "that licence stack."),
                                                      TARGET_DOCKERFILE, _A),
    "M-2: CPython block without the incorporated file": (_swap(_M2_SENTENCE, ""), TARGET_DOCKERFILE, _A),
    "M-2: the incorporated file for another minor": (
        _swap("`licenses/CPython-3.12-incorporated.txt`; the licence of",
              "`licenses/CPython-3.13-incorporated.txt`; the licence of"), TARGET_DOCKERFILE, _A),
    "M-2: the incorporated file named outside the CPython block": (
        _swap(_M2_SENTENCE, "", _swap(_PIP, _M2_SENTENCE.strip() + "\n\n" + _PIP)), TARGET_DOCKERFILE, _A),
    "M-2: 'stack only', and LICENSE.txt also holds the incorporated licences": (
        _swap("that licence stack only.", "that licence stack only and the licences of the\n  incorporated code."),
        TARGET_DOCKERFILE, _A),
    "no Debian 12": (_swap("The Debian 12 (bookworm) packages", "The packages"), TARGET_DOCKERFILE, _A),
    "Debian 12 without codename (B1)": (_swap("Debian 12 (bookworm)", "Debian 12"), TARGET_DOCKERFILE, _A),
    "Debian 12 without copyright path": (_swap("licence in `/usr/share/doc/*/copyright` inside the image and,",
                                               "licence and,"), TARGET_DOCKERFILE, _A),
    "Debian 12 without SBOM": (_swap("inside the image and, where the\n  bundle carries one, in the image's SBOM.",
                                     "inside the image."), TARGET_DOCKERFILE, _A),
    "Debian 12 SBOM unconditional (L-1)": (
        _swap("inside the image and, where the\n  bundle carries one, in the image's SBOM.",
              "inside the image and in the\n  image's SBOM."), TARGET_DOCKERFILE, _A),
    "added packages SBOM unconditional (L-1)": (_swap("(and the SBOM where the bundle carries one)", "and the SBOM"),
                                                TARGET_DOCKERFILE, _A),
    "libpq5 not named": (_swap("`libpq5` " + FIX_PIN + ", under the", "the client library, under the"),
                         TARGET_DOCKERFILE, _A),
    "libpq5 pin missing": (_swap("`libpq5` " + FIX_PIN, "`libpq5`"), TARGET_DOCKERFILE, _A),
    "libpq5 pin differs in Dockerfile": (TARGET_NOTICE, TARGET_DOCKERFILE.replace(FIX_PIN, "15.98-0+deb12u9"), _A),
    "libsasl2-modules-db missing": (_swap("`libsasl2-2` and `libsasl2-modules-db`", "`libsasl2-2`"),
                                    TARGET_DOCKERFILE, _A),
    "libldap-2.5-0 missing": (_swap("`libldap-2.5-0`,\n  ", ""), TARGET_DOCKERFILE, _A),
    "ADDED_PACKAGES names libzz9 the NOTICE lacks": (TARGET_NOTICE, TARGET_DOCKERFILE, _A | {"libzz9"}),
    "Dockerfile adds a package outside ADDED_PACKAGES": (TARGET_NOTICE, TARGET_DOCKERFILE.replace(
        "libpq5=${LIBPQ_VERSION}", "libpq5=${LIBPQ_VERSION} libzz9"), _A),
    "pip: no 'not shipped' statement": (_swap(_PIP + "\n", ""), TARGET_DOCKERFILE, _A),
    "pip: today's pip bullet back": (_swap(_ADDED_END, "carries one).\n" + _OLD_PIP_BULLET + "\n"),
                                     TARGET_DOCKERFILE, _A),
    "pip: named as shipped": (_swap(_ADDED_END, "carries one).\n- The base's pip in the system site-packages.\n\n"),
                              TARGET_DOCKERFILE, _A),
    "pip: negated, with a version": (_swap("pip is not shipped:", "pip 25.0.1 is not shipped:"),
                                     TARGET_DOCKERFILE, _A),
    "pip: negated, naming vendor.txt": (_swap("the packages pip vendors.", "the packages in `pip/_vendor/vendor.txt`."),
                                        TARGET_DOCKERFILE, _A),
    "pip: negated, naming MIT": (_swap("pip is not shipped:", "pip (MIT) is not shipped:"), TARGET_DOCKERFILE, _A),
    "pip: negated, naming Apache-2.0 and MPL-2.0": (
        _swap("the packages pip vendors.", "the packages pip vendors (Apache-2.0, MPL-2.0)."), TARGET_DOCKERFILE, _A),
    "pip: NOTICE names licenses/Apache-2.0.txt (reverted)": (
        _swap("## Licence texts\n", "## Licence texts\n\n`licenses/Apache-2.0.txt` is the Apache text.\n"),
        TARGET_DOCKERFILE, _A),
    # Round 4 (PSC-14 amended, security L-9b fix 5): Apache-2.0.txt ships for
    # KaRaMeL, so NOTICE.md may name it, but never beside pip.
    "pip: NOTICE names licenses/Apache-2.0.txt with base-files, beside pip (L-9b)": (
        _swap("## Licence texts\n", "## Licence texts\n\n`licenses/Apache-2.0.txt` is the text from `base-files`; "
                                    "pip is not\nshipped.\n"), TARGET_DOCKERFILE, _A),
    "pip: NOTICE names licenses/Apache-2.0.txt for KaRaMeL and for pip (L-9b)": (
        _swap("licence text in `licenses/Apache-2.0.txt`.", "licence text, and pip's, in `licenses/Apache-2.0.txt`."),
        TARGET_DOCKERFILE, _A),
    "pip: NOTICE names licenses/MPL-2.0.txt (reverted)": (
        _swap("## Licence texts\n", "## Licence texts\n\n`licenses/MPL-2.0.txt` is the Mozilla text.\n"),
        TARGET_DOCKERFILE, _A),
    "uv named as shipped": (_swap("uv is not shipped: it runs only in the `builder` stage, which does not ship.",
                                  "uv is not shipped.\n\n- uv 0.11.21 under `/usr/local/bin` (MIT OR Apache-2.0)."),
                            TARGET_DOCKERFILE, _A),
    "no uv statement": (_swap("uv is not shipped: it runs only in the `builder` stage, which does not ship.\n\n", ""),
                        TARGET_DOCKERFILE, _A),
    # Re-target (N10a): the base is read from `runtime`, and the U0-shape
    # controls above still fail when the Dockerfile is flattened.
    "flat: runtime digest differs from NOTICE": (TARGET_NOTICE, _runtime_ref(FIX_REF[:-1] + "c"), _A),
    "flat: NOTICE gives the builder's ref, runtime's differs": (TARGET_NOTICE, _runtime_ref(
        "python:3.12-slim-bookworm@sha256:" + "d" * 64), _A),
    "flat: unparseable runtime ref (B1)": (TARGET_NOTICE, _runtime_ref("python:3.12-slim@sha256:" + FIX_DIGEST), _A),
    "flat: runtime minor 3.13, NOTICE says 3.12": (*_ref(FIX_REF.replace("python:3.12", "python:3.13"),
                                                         dockerfile=TARGET_DOCKERFILE_FLAT), _A),
    "flat: runtime adds a package outside ADDED_PACKAGES": (TARGET_NOTICE, TARGET_DOCKERFILE_FLAT.replace(
        "libpq5=${LIBPQ_VERSION}", "libpq5=${LIBPQ_VERSION} libzz9"), _A),
    "flat: libpq5 pin differs": (TARGET_NOTICE, TARGET_DOCKERFILE_FLAT.replace(FIX_PIN, "15.98-0+deb12u9"), _A),
    "flat: scratch stage copies / from a missing stage": (TARGET_NOTICE, TARGET_DOCKERFILE_FLAT.replace(
        "COPY --from=runtime / /", "COPY --from=nosuch / /"), _A),
    "flat: scratch stage does not start with COPY / /": (TARGET_NOTICE, TARGET_DOCKERFILE_FLAT.replace(
        "COPY --from=runtime / /\n", ""), _A),
}
# Controls that must pass: an honest update after a base bump (review B1 P3),
# and the N10a Dockerfile (re-target).
BASE_PASSING: dict[str, tuple[str, str, frozenset[str]]] = {
    "trixie ref, NOTICE says Debian 13 (trixie) (B1 P3)": (
        *_ref(TRIXIE_REF, _swap("Debian 12 (bookworm)", "Debian 13 (trixie)")), _A),
    "registry-prefixed 3.13 ref, NOTICE says 3.13 (B1)": (*_ref(REG_313_REF, _to_313(TARGET_NOTICE)), _A),
    "N10a Dockerfile (runtime + FROM scratch)": (TARGET_NOTICE, TARGET_DOCKERFILE_FLAT, _A),
    "N10a Dockerfile, registry-prefixed 3.13 runtime, NOTICE says 3.13": (
        *_ref(REG_313_REF, _to_313(TARGET_NOTICE), TARGET_DOCKERFILE_FLAT), _A),
}

LIBPQ_CONTROLS: dict[str, str] = {
    "libpq5 without the PostgreSQL licence": _swap("`libpq5` " + FIX_PIN + ", under the\n  PostgreSQL licence,",
                                                   "`libpq5` " + FIX_PIN + ","),
    "libpq5 under another licence": _swap("under the\n  PostgreSQL licence,", "under the\n  MIT licence,"),
    "libpq5 not a Debian package": _swap("The Debian packages the shipped stage adds:", "The shipped stage adds:"),
    "vendored-libraries heading": _swap("## Licence texts", "## Vendored libraries\n\nNone.\n\n## Licence texts"),
    "vendored-libraries table": _swap("## Licence texts", "| Library | Licence |\n|---|---|\n"
                                      "| `libpq-9b38f5e3.so.5.16` | PostgreSQL |\n\n## Licence texts"),
    "psycopg_binary undated": _swap("## Licence texts", "The image has no `psycopg_binary.libs`.\n\n## Licence texts"),
    "psycopg-binary in a block dated mid-text (N4)": _swap(
        "## Licence texts", "Rebuilt on 2026-10-22, without psycopg-binary.\n\n## Licence texts"),
}
LIBPQ_PASSING: dict[str, str] = {
    "History: block names psycopg-binary (N4)": _swap(
        "## Licence texts", "History: on 2026-10-22 psycopg-c replaced psycopg-binary.\n\n## Licence texts"),
}

_M1_SENTENCE = ('A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has\n'
                "no `sources/` and carries no third-party source code, so it does not\n"
                "itself provide the source that any of these licences requires.\n")
POINTER_CONTROLS: dict[str, str] = {
    "no pointer": _swap(_POINTER.split("## Licence texts")[0], ""),
    "pointer without Source code": _swap('in its "Source code" section,', "in a section,"),
    "pointer without sources/": _swap("whether its source is in `sources/` of this bundle.",
                                      "whether its source is shipped."),
    "pointer without THIRD_PARTY_NOTICES.md": _swap("`THIRD_PARTY_NOTICES.md` says, in its", "The bundle says, in its"),
    "no L-6 sentence": _swap(_L6, ""),
    "L-6 sentence in its own paragraph": _swap(_L6, "\n" + _L6),
    "today's M-1 sentence ('carries no third-party source code', L-6)": _swap(_L6, _M1_SENTENCE),
    "L-6 with 'any of these licences' (no antecedent, L-6)": _swap("that a\nGPL-family licence requires.",
                                                                   "that any of these licences requires."),
    "L-6 without the no-section condition": _swap(
        'A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has\nno', "This bundle has\nno"),
    "L-6 without has no sources/": _swap("section has\nno `sources/`, so", "section, so"),
    "L-6 says the bundle provides the source": _swap("so it does not itself provide the source",
                                                     "so it itself provides the source"),
    "L-6 with curly quotes (verbatim)": _swap('has no "Source code" section has\nno `sources/`, so',
                                              "has no “Source code” section has\nno `sources/`, so"),
    "L-6 kept, the old claim elsewhere": _swap("## Licence texts\n",
                                               "## Licence texts\n\nThe bundle carries no third-party source code.\n"),
}

# name -> (NOTICE.md, incorporated file text or None, app.Dockerfile); must fail.
_I = TARGET_INCORPORATED
_REL = "licenses/CPython-3.12-incorporated.txt"
INCORPORATED_CONTROLS: dict[str, tuple[str, str | None, str]] = {
    "NOTICE does not name the file": (_swap(_REL, "the incorporated-licence file"), _I, TARGET_DOCKERFILE_FLAT),
    "the file is missing": (TARGET_NOTICE, None, TARGET_DOCKERFILE_FLAT),
    "file and NOTICE for 3.13, base 3.12": (_swap(_REL, _REL.replace("3.12", "3.13")), incorporated_text("3.13.0"),
                                            TARGET_DOCKERFILE_FLAT),
    "line 1 3.13.0 with its URL, base 3.12": (TARGET_NOTICE, incorporated_text("3.13.0"), TARGET_DOCKERFILE_FLAT),
    "URL tag is not line 1's version": (TARGET_NOTICE, incorporated_text(url=FIX_URL.replace("v3.12.99", "v3.12.98")),
                                        TARGET_DOCKERFILE_FLAT),
    "URL over http": (TARGET_NOTICE, incorporated_text(url=FIX_URL.replace("https://", "http://")),
                      TARGET_DOCKERFILE_FLAT),
    "URL on another host": (TARGET_NOTICE, incorporated_text(url=FIX_URL.replace("raw.githubusercontent.com",
                                                                                  "example.com")),
                            TARGET_DOCKERFILE_FLAT),
    "URL to another file": (TARGET_NOTICE, incorporated_text(url=FIX_URL.replace("license.rst", "LICENSE")),
                            TARGET_DOCKERFILE_FLAT),
    "line 1 without the section title": (TARGET_NOTICE, _I.replace(f'CPython {FIX_CPYTHON}: "{INCORPORATED_HEADING}"',
                                                                   f"CPython {FIX_CPYTHON}"), TARGET_DOCKERFILE_FLAT),
    "line 1 names Python, not CPython": (TARGET_NOTICE, _I.replace("CPython 3.12.99:", "Python 3.12.99:", 1),
                                         TARGET_DOCKERFILE_FLAT),
    "sha256 short": (TARGET_NOTICE, incorporated_text(sha="b" * 63), TARGET_DOCKERFILE_FLAT),
    "sha256 upper-case": (TARGET_NOTICE, incorporated_text(sha="B" * 64), TARGET_DOCKERFILE_FLAT),
    "no sha256 line": (TARGET_NOTICE, _I.replace(f"Source sha256: {'b' * 64}\n", ""), TARGET_DOCKERFILE_FLAT),
    "Extract line reworded": (TARGET_NOTICE, _I.replace(HEADER_4, "Extract: the incorporated-software section."),
                              TARGET_DOCKERFILE_FLAT),
    "no blank line after the header": (TARGET_NOTICE, _I.replace(HEADER_4 + "\n\n", HEADER_4 + "\n"),
                                       TARGET_DOCKERFILE_FLAT),
    "extract starts at a subsection": (TARGET_NOTICE, _I.replace(
        f"{INCORPORATED_HEADING}\n{'=' * len(INCORPORATED_HEADING)}\n\n", "", 1), TARGET_DOCKERFILE_FLAT),
    "heading underlined with -": (TARGET_NOTICE, _I.replace("=" * len(INCORPORATED_HEADING),
                                                            "-" * len(INCORPORATED_HEADING)), TARGET_DOCKERFILE_FLAT),
    "underline too short": (TARGET_NOTICE, _I.replace("=" * len(INCORPORATED_HEADING), "=" * 10),
                            TARGET_DOCKERFILE_FLAT),
    "heading twice": (TARGET_NOTICE, _I + f"\n{INCORPORATED_HEADING}\n{'=' * len(INCORPORATED_HEADING)}\n",
                      TARGET_DOCKERFILE_FLAT),
    "extract cut before libmpdec": (TARGET_NOTICE, _I[:_I.index("libmpdec\n--------")], TARGET_DOCKERFILE_FLAT),
    "extract without expat": (TARGET_NOTICE, _I.replace("expat", "xml"), TARGET_DOCKERFILE_FLAT),
    "CRLF line endings": (TARGET_NOTICE, _I.replace("\n", "\r\n"), TARGET_DOCKERFILE_FLAT),
    "NOTICE gives another tag's URL": (_swap(FIX_URL, FIX_URL.replace("v3.12.99", "v3.12.98")), _I,
                                       TARGET_DOCKERFILE_FLAT),
    "NOTICE names the file without its URL": (_swap(f"fetched over HTTPS from\n{FIX_URL};", "fetched over HTTPS;"), _I,
                                              TARGET_DOCKERFILE_FLAT),
    "unparseable base ref (B1)": (TARGET_NOTICE, _I, _runtime_ref("python:3.12-slim@sha256:" + FIX_DIGEST)),
}
INCORPORATED_PASSING: dict[str, tuple[str, str | None, str]] = {
    "U0-shape Dockerfile": (TARGET_NOTICE, _I, TARGET_DOCKERFILE),
    "honest bump: 3.13 base, 3.13.1 file, NOTICE names it": (
        _swap(_REL, _REL.replace("3.12", "3.13"), _swap(FIX_URL, FIX_URL.replace("v3.12.99", "v3.13.1"))),
        incorporated_text("3.13.1"), _runtime_ref(REG_313_REF)),
}

# The HACL* file (U1 round 3, security L-9; N10a). A stand-in extract with the
# real one's shape: first line `/* MIT License`, the contributors line, last
# line ` */` (the repository's file is checked last).
HACL_EXTRACT = ("/* MIT License\n *\n * Copyright (c) 2016-2022 INRIA, CMU and Microsoft Corporation\n"
                " * Copyright (c) 2022-2023 HACL* Contributors\n *\n"
                " * Permission is hereby granted, free of charge, to any person obtaining a copy\n"
                " * of this software (stand-in for the 23-line header).\n"
                " * SOFTWARE.\n */\n")


def hacl_text(version: str = FIX_CPYTHON, source: str | None = None, tar_dir: str | None = None,
              tar_file: str | None = None, url: str | None = None, sha: str = "c" * 64,
              extract: str = HACL_EXTRACT) -> str:
    """A file in N10a's HACL shape: four header lines, a blank, the extract."""
    url = url or (f"https://www.python.org/ftp/python/{tar_dir or version}/"
                  f"Python-{tar_file or version}.tar.xz")
    return (f"CPython {version}: HACL* licence header (MIT), Modules/_hacl/\n"
            f"Source: Python-{source or version}/Modules/_hacl/Hacl_Hash_SHA2.c\n"
            f"Tarball: {url}\nTarball sha256: {sha}\n\n{extract}")


TARGET_HACL = hacl_text()
_H = TARGET_HACL
_HREL = "licenses/CPython-3.12-HACL.txt"
_F = TARGET_DOCKERFILE_FLAT
_HACL_MODULES_TEXT = "`_md5`, `_sha1`, `_sha2` and `_sha3`"
# name -> (NOTICE.md, incorporated file or None, HACL file or None, app.Dockerfile); must fail.
HACL_CONTROLS: dict[str, tuple[str, str | None, str | None, str]] = {
    # NOTICE.md's CPython bullet (N10 round 3).
    "I-8: round 3's 'the HACL* hash code ... is in' (the code, not its licence)": (
        _swap("; the licence of\n  the HACL* hash code", ";\n  the HACL* hash code"), _I, _H, _F),
    "I-8: round 3's whole sentence (today's NOTICE.md)": (_swap(_M2_SENTENCE, _R3_M2_SENTENCE), _I, _H, _F),
    "round 2's bullet: 'whose texts are in', no HACL file named": (
        _swap(_M2_SENTENCE, _ROUND2_M2_SENTENCE), _I, _H, _F),
    "NOTICE names the HACL file nowhere": (_swap(_HREL, "the HACL* licence file"), _I, _H, _F),
    "the bullet does not name the HACL file (Licence texts does)": (
        _swap("is in `licenses/CPython-3.12-HACL.txt`, and that code",
              "is under Licence texts, and that code"), _I, _H, _F),
    "the bullet does not name the incorporated file": (
        _swap("is in `licenses/CPython-3.12-incorporated.txt`; the", "is in the bundle; the"), _I, _H, _F),
    "the bullet without HACL*": (_swap("the HACL* hash code (MIT)", "the hash code (MIT)"), _I, _H, _F),
    "the bullet without MIT": (_swap("the HACL* hash code (MIT)", "the HACL* hash code"), _I, _H, _F),
    "the bullet without _sha3": (_swap(_HACL_MODULES_TEXT, "`_md5`, `_sha1` and `_sha2`"), _I, _H, _F),
    "the bullet without _md5": (_swap(_HACL_MODULES_TEXT, "`_sha1`, `_sha2` and `_sha3`"), _I, _H, _F),
    "the bullet does not call the incorporated file a list": (
        _swap("that list omits", "it omits", _swap("CPython's own list of it", "The licences of it")),
        _I, _H, _F),
    "completeness: 'all of it'": (_swap("CPython's own list of it", "CPython's list of all of it"), _I, _H, _F),
    "completeness: 'the complete list'": (_swap("CPython's own list of it", "CPython's complete list of it"),
                                          _I, _H, _F),
    "completeness: 'every licence'": (_swap("`licenses/Apache-2.0.txt`.\n- The Debian",
                                            "`licenses/Apache-2.0.txt`. Every licence of that code is in\n"
                                            "  these files.\n- The Debian"), _I, _H, _F),
    "completeness: 'whose texts are in' beside the HACL file": (
        _swap("its own licences. CPython's", "its own licences, whose texts are in these files. CPython's"),
        _I, _H, _F),
    # The file.
    "the HACL file is missing": (TARGET_NOTICE, _I, None, _F),
    "line 1 reworded": (TARGET_NOTICE, _I, _H.replace("HACL* licence header (MIT)", "HACL* licence"), _F),
    "line 1 names Python, not CPython": (TARGET_NOTICE, _I, _H.replace("CPython 3.12.99:", "Python 3.12.99:", 1), _F),
    "Source: version differs": (TARGET_NOTICE, _I, hacl_text(source="3.12.98"), _F),
    "Tarball: directory version differs": (TARGET_NOTICE, _I, hacl_text(tar_dir="3.12.98"), _F),
    "Tarball: file version differs": (TARGET_NOTICE, _I, hacl_text(tar_file="3.12.98"), _F),
    "the HACL file's 3.12.98 throughout, incorporated 3.12.99": (
        _swap(FIX_TARBALL, FIX_TARBALL.replace("3.12.99", "3.12.98")), _I, hacl_text("3.12.98"), _F),
    "the incorporated file is missing (no line 1 to compare)": (TARGET_NOTICE, None, _H, _F),
    "minor 3.13 in both files, base 3.12": (
        _swap(FIX_TARBALL, FIX_TARBALL.replace("3.12.99", "3.13.0")), incorporated_text("3.13.0"),
        hacl_text("3.13.0"), _F),
    "Source: another file (Hacl_Hash_SHA1.c)": (TARGET_NOTICE, _I, _H.replace("Hacl_Hash_SHA2.c", "Hacl_Hash_SHA1.c"),
                                                _F),
    "Source: without the Python-X.Y.Z/ prefix": (TARGET_NOTICE, _I, _H.replace("Source: Python-3.12.99/", "Source: "),
                                                 _F),
    "Tarball over http": (TARGET_NOTICE, _I, hacl_text(url=FIX_TARBALL.replace("https://", "http://")), _F),
    "Tarball on another host": (TARGET_NOTICE, _I, hacl_text(url=FIX_TARBALL.replace("www.python.org",
                                                                                      "example.com")), _F),
    "Tarball .tgz": (TARGET_NOTICE, _I, hacl_text(url=FIX_TARBALL.replace(".tar.xz", ".tgz")), _F),
    "sha256 short": (TARGET_NOTICE, _I, hacl_text(sha="c" * 63), _F),
    "sha256 upper-case": (TARGET_NOTICE, _I, hacl_text(sha="C" * 64), _F),
    "line 4 'Source sha256:', not 'Tarball sha256:'": (TARGET_NOTICE, _I, _H.replace("Tarball sha256:",
                                                                                      "Source sha256:"), _F),
    "no blank line after the header": (TARGET_NOTICE, _I, _H.replace("c" * 64 + "\n\n", "c" * 64 + "\n"), _F),
    "a fifth header line": (TARGET_NOTICE, _I, _H.replace("c" * 64 + "\n\n", "c" * 64 + "\nExtract: lines 1-23.\n\n"),
                            _F),
    "extract does not start `/* MIT License`": (TARGET_NOTICE, _I, _H.replace("/* MIT License\n", "/*\n"), _F),
    "extract starts at the copyright line": (TARGET_NOTICE, _I, _H.replace("/* MIT License\n *\n", ""), _F),
    "extract cut before ` */`": (TARGET_NOTICE, _I, _H[:-len(" */\n")], _F),
    "extract runs into the code": (TARGET_NOTICE, _I, _H + '\n#include "internal/Hacl_Hash_SHA2.h"\n', _F),
    "extract runs on to a second ` */`": (TARGET_NOTICE, _I, _H + "\n/* Hacl_Hash_SHA2.h */\n */\n", _F),
    "no HACL* Contributors": (TARGET_NOTICE, _I, _H.replace("HACL* Contributors", "Contributors"), _F),
    "CRLF line endings": (TARGET_NOTICE, _I, _H.replace("\n", "\r\n"), _F),
    # NOTICE.md's Licence-texts block.
    "NOTICE gives no tarball URL for the HACL file": (_swap(f"release tarball\n{FIX_TARBALL},", "release tarball,"),
                                                      _I, _H, _F),
    "NOTICE gives another version's tarball URL": (_swap(FIX_TARBALL, FIX_TARBALL.replace("3.12.99", "3.12.98")),
                                                   _I, _H, _F),
    "NOTICE's HACL block without Hacl_Hash_SHA2.c": (_swap("`Modules/_hacl/Hacl_Hash_SHA2.c`", "a HACL* source"),
                                                     _I, _H, _F),
    "unparseable base ref (B1)": (TARGET_NOTICE, _I, _H, _runtime_ref("python:3.12-slim@sha256:" + FIX_DIGEST)),
}
HACL_PASSING: dict[str, tuple[str, str | None, str | None, str]] = {
    "U0-shape Dockerfile": (TARGET_NOTICE, _I, _H, TARGET_DOCKERFILE),
    "no trailing newline after ` */`": (TARGET_NOTICE, _I, _H[:-1], _F),
    "honest bump: 3.13 base, 3.13.1 files, NOTICE names them": (
        _swap(_HREL, _HREL.replace("3.12", "3.13"), _swap(FIX_TARBALL, FIX_TARBALL.replace("3.12.99", "3.13.1"),
                                                          _to_313(TARGET_NOTICE))),
        incorporated_text("3.13.1"), hacl_text("3.13.1"), _runtime_ref(REG_313_REF)),
}

# The KaRaMeL file and licenses/Apache-2.0.txt (U1 round 4, security L-9b).
# The extract is the real one (sed -n '1,/\*\//p' of krml/internal/target.h,
# 116 B, sha256 6b7cb4bd...8a26).
KARAMEL_EXTRACT = KARAMEL_FIRST + "\n   " + KARAMEL_LAST + "\n"


def karamel_text(version: str = FIX_CPYTHON, source: str | None = None, tar_dir: str | None = None,
                 tar_file: str | None = None, url: str | None = None, sha: str = "c" * 64,
                 extract: str = KARAMEL_EXTRACT) -> str:
    """A file in the KaRaMeL shape: four header lines, a blank, the extract."""
    url = url or (f"https://www.python.org/ftp/python/{tar_dir or version}/"
                  f"Python-{tar_file or version}.tar.xz")
    return (f"CPython {version}: KaRaMeL licence header (Apache-2.0), Modules/_hacl/include/krml/\n"
            f"Source: Python-{source or version}/Modules/_hacl/include/krml/internal/target.h\n"
            f"Tarball: {url}\nTarball sha256: {sha}\n\n{extract}")


TARGET_KARAMEL = karamel_text()
_K = TARGET_KARAMEL
_KREL = "licenses/CPython-3.12-KaRaMeL.txt"
_AP = FIX_APACHE_TEXT
_KPARA_URL = f"tarball {FIX_TARBALL}, unmodified"
# name -> (NOTICE.md, incorporated, HACL, KaRaMeL, Apache-2.0 text (each None if
# absent), app.Dockerfile); must fail. The check gets FIX_APACHE_SHA as the
# Apache sha256 (one more control, in the test, uses the pinned default).
KARAMEL_CONTROLS: dict[str, tuple[str, str | None, str | None, str | None, str | None, str]] = {
    # NOTICE.md's CPython bullet (security L-9b fix 3).
    "round 3's bullet (today's): KaRaMeL not named": (_swap(_M2_SENTENCE, _R3_M2_SENTENCE), _I, _H, _K, _AP, _F),
    "the bullet without KaRaMeL": (_swap("compiles in KaRaMeL headers", "compiles in header files"),
                                   _I, _H, _K, _AP, _F),
    "the bullet without INRIA and Microsoft": (
        _swap("(Copyright INRIA and Microsoft Corporation,\n  Apache-2.0)", "(Apache-2.0)"), _I, _H, _K, _AP, _F),
    "the bullet without the licence Apache-2.0": (_swap("Corporation,\n  Apache-2.0)", "Corporation)"),
                                                  _I, _H, _K, _AP, _F),
    "the bullet does not name the KaRaMeL file (Licence texts does)": (
        _swap("whose notice is in `licenses/CPython-3.12-KaRaMeL.txt` and", "whose notice is under Licence texts and"),
        _I, _H, _K, _AP, _F),
    "the bullet does not name licenses/Apache-2.0.txt (Licence texts does)": (
        _swap("licence text in `licenses/Apache-2.0.txt`.", "licence text under Licence texts."),
        _I, _H, _K, _AP, _F),
    "the KaRaMeL clause in a paragraph of its own, not the bullet": (
        _swap(_KARAMEL_TAIL, ".", _swap(_PIP, "That code compiles in KaRaMeL headers (Copyright INRIA and Microsoft\n"
                                              "Corporation, Apache-2.0), whose notice is in\n"
                                              "`licenses/CPython-3.12-KaRaMeL.txt` and licence text in\n"
                                              "`licenses/Apache-2.0.txt`.\n\n" + _PIP)), _I, _H, _K, _AP, _F),
    # The KaRaMeL file.
    "the KaRaMeL file is missing": (TARGET_NOTICE, _I, _H, None, _AP, _F),
    "line 1 without (Apache-2.0)": (TARGET_NOTICE, _I, _H, _K.replace("licence header (Apache-2.0)", "licence header"),
                                    _AP, _F),
    "line 1 copied from the HACL file": (TARGET_NOTICE, _I, _H, _K.replace(
        "KaRaMeL licence header (Apache-2.0), Modules/_hacl/include/krml/", "HACL* licence header (MIT), Modules/_hacl/"),
        _AP, _F),
    "line 1 names Python, not CPython": (TARGET_NOTICE, _I, _H, _K.replace("CPython 3.12.99:", "Python 3.12.99:", 1),
                                         _AP, _F),
    "Source: version differs": (TARGET_NOTICE, _I, _H, karamel_text(source="3.12.98"), _AP, _F),
    "Source: another krml header (types.h)": (TARGET_NOTICE, _I, _H, _K.replace("krml/internal/target.h",
                                                                                 "krml/types.h"), _AP, _F),
    "Source: the HACL file's source": (TARGET_NOTICE, _I, _H, _K.replace(KARAMEL_SOURCE_FILE, HACL_SOURCE_FILE),
                                       _AP, _F),
    "Tarball: directory version differs": (TARGET_NOTICE, _I, _H, karamel_text(tar_dir="3.12.98"), _AP, _F),
    "Tarball: file version differs": (TARGET_NOTICE, _I, _H, karamel_text(tar_file="3.12.98"), _AP, _F),
    "Tarball over http": (TARGET_NOTICE, _I, _H, karamel_text(url=FIX_TARBALL.replace("https://", "http://")), _AP, _F),
    "sha256 short": (TARGET_NOTICE, _I, _H, karamel_text(sha="c" * 63), _AP, _F),
    "sha256 upper-case": (TARGET_NOTICE, _I, _H, karamel_text(sha="C" * 64), _AP, _F),
    "Tarball sha256 differs from the HACL file's (one tarball)": (TARGET_NOTICE, _I, _H, karamel_text(sha="d" * 64),
                                                                  _AP, _F),
    "line 4 'Source sha256:', not 'Tarball sha256:'": (TARGET_NOTICE, _I, _H, _K.replace("Tarball sha256:",
                                                                                          "Source sha256:"), _AP, _F),
    "no blank line after the header": (TARGET_NOTICE, _I, _H, _K.replace("c" * 64 + "\n\n", "c" * 64 + "\n"), _AP, _F),
    "a fifth header line": (TARGET_NOTICE, _I, _H, _K.replace("c" * 64 + "\n\n", "c" * 64 + "\nExtract: lines 1-2.\n\n"),
                            _AP, _F),
    "the KaRaMeL file's 3.12.98 throughout, the others 3.12.99": (
        _swap(_KPARA_URL, _KPARA_URL.replace("3.12.99", "3.12.98")), _I, _H, karamel_text("3.12.98"), _AP, _F),
    "the HACL file 3.12.98, KaRaMeL and incorporated 3.12.99": (TARGET_NOTICE, _I, hacl_text("3.12.98"), _K, _AP, _F),
    "the incorporated file 3.12.98, KaRaMeL and HACL 3.12.99": (TARGET_NOTICE, incorporated_text("3.12.98"), _H, _K,
                                                                _AP, _F),
    "the HACL file is missing (no line 1 to compare)": (TARGET_NOTICE, _I, None, _K, _AP, _F),
    "the incorporated file is missing (no line 1 to compare)": (TARGET_NOTICE, None, _H, _K, _AP, _F),
    "minor 3.13 in all three files, base 3.12": (
        _swap(FIX_TARBALL, FIX_TARBALL.replace("3.12.99", "3.13.0")), incorporated_text("3.13.0"),
        hacl_text("3.13.0"), karamel_text("3.13.0"), _AP, _F),
    "extract without 'All rights reserved.'": (TARGET_NOTICE, _I, _H, _K.replace(" All rights reserved.", ""), _AP, _F),
    "extract starts at the Licensed line": (TARGET_NOTICE, _I, _H, karamel_text(extract="   " + KARAMEL_LAST + "\n"),
                                            _AP, _F),
    "extract's last line without ` */`": (TARGET_NOTICE, _I, _H, _K.replace("License. */", "License."), _AP, _F),
    "extract's last line with text before 'Licensed'": (TARGET_NOTICE, _I, _H, _K.replace(
        "   Licensed under", "   This file is Licensed under"), _AP, _F),
    "extract runs into the code": (TARGET_NOTICE, _I, _H, _K + "\n#ifndef __KRML_TARGET_H\n", _AP, _F),
    "extract is the HACL MIT header": (TARGET_NOTICE, _I, _H, karamel_text(extract=HACL_EXTRACT), _AP, _F),
    "extract names another licence (Apache 2.1)": (TARGET_NOTICE, _I, _H, _K.replace("Apache 2.0 License",
                                                                                      "Apache 2.1 License"), _AP, _F),
    "CRLF line endings": (TARGET_NOTICE, _I, _H, _K.replace("\n", "\r\n"), _AP, _F),
    # NOTICE.md's KaRaMeL Licence-texts block (security L-9b fix 4).
    "NOTICE names the KaRaMeL file nowhere": (_swap(_KREL, "the KaRaMeL notice file"), _I, _H, _K, _AP, _F),
    "NOTICE's KaRaMeL paragraph without the tarball URL": (_swap(_KPARA_URL, "tarball, unmodified"),
                                                           _I, _H, _K, _AP, _F),
    "NOTICE's KaRaMeL paragraph gives another version's tarball URL": (
        _swap(_KPARA_URL, _KPARA_URL.replace("3.12.99", "3.12.98")), _I, _H, _K, _AP, _F),
    "NOTICE's KaRaMeL paragraph without target.h": (
        _swap("`Modules/_hacl/include/krml/internal/target.h`", "a KaRaMeL header"), _I, _H, _K, _AP, _F),
    # licenses/Apache-2.0.txt (security L-9b fix 1) and its block (fix 4).
    "licenses/Apache-2.0.txt is missing": (TARGET_NOTICE, _I, _H, _K, None, _F),
    "licenses/Apache-2.0.txt with an added header line": (TARGET_NOTICE, _I, _H, _K,
                                                          "Apache-2.0, from base-files\n" + _AP, _F),
    "licenses/Apache-2.0.txt with CRLF line endings": (TARGET_NOTICE, _I, _H, _K, _AP.replace("\n", "\r\n"), _F),
    "licenses/Apache-2.0.txt is another text (the MIT header)": (TARGET_NOTICE, _I, _H, _K, HACL_EXTRACT, _F),
    "NOTICE has no Apache-2.0.txt Licence-texts paragraph": (_swap("\n" + _APACHE_PARA, ""), _I, _H, _K, _AP, _F),
    "NOTICE's Apache paragraph without base-files": (_swap("`base-files` ships it", "Debian ships it"),
                                                     _I, _H, _K, _AP, _F),
    "NOTICE's Apache paragraph without the common-licenses path": (
        _swap(" at `/usr/share/common-licenses/Apache-2.0` in", " in"), _I, _H, _K, _AP, _F),
    "NOTICE's Apache paragraph gives another sha256": (_swap(FIX_APACHE_SHA, "e" * 64), _I, _H, _K, _AP, _F),
    "unparseable base ref (B1)": (TARGET_NOTICE, _I, _H, _K, _AP, _runtime_ref("python:3.12-slim@sha256:" + FIX_DIGEST)),
}
KARAMEL_PASSING: dict[str, tuple[str, str | None, str | None, str | None, str | None, str]] = {
    "U0-shape Dockerfile": (TARGET_NOTICE, _I, _H, _K, _AP, TARGET_DOCKERFILE),
    "no trailing newline after ` */`": (TARGET_NOTICE, _I, _H, _K[:-1], _AP, _F),
    "honest bump: 3.13 base, 3.13.1 files, NOTICE names them": (
        _swap(_KREL, _KREL.replace("3.12", "3.13"), _swap(FIX_TARBALL, FIX_TARBALL.replace("3.12.99", "3.13.1"),
                                                          _to_313(TARGET_NOTICE))),
        incorporated_text("3.13.1"), hacl_text("3.13.1"), karamel_text("3.13.1"), _AP, _runtime_ref(REG_313_REF)),
}

# Security I-4 (tracked licence files). name -> NOTICE.md text naming paths
# under the scratch repository's licenses/ (TRACKED_FILES are `git add`ed,
# UNTRACKED_FILES only written).
TRACKED_FILES = ("licenses/GPL-3.0.txt", "licenses/LGPL-3.0.txt", "licenses/CPython-3.12-incorporated.txt",
                 _HREL, _KREL, APACHE_REL)
# Round 3's case: an incorporated-licence file written but never `git add`ed.
# Round 4: a KaRaMeL file likewise, and a scratch-only name that no real
# licence file has (security L-9b fix 5: not `licenses/Apache-2.0.txt`).
_SCRATCH_UNTRACKED = "licenses/Scratch-untracked-example.txt"
UNTRACKED_FILES = ("licenses/CPython-3.13-incorporated.txt", "licenses/CPython-3.13-KaRaMeL.txt", _SCRATCH_UNTRACKED)
TRACKED_CONTROLS: dict[str, str] = {
    "the target NOTICE with an untracked incorporated file": TARGET_NOTICE.replace(
        "CPython-3.12-incorporated", "CPython-3.13-incorporated"),
    "the target NOTICE with an untracked KaRaMeL file (round 4)": TARGET_NOTICE.replace(
        "CPython-3.12-KaRaMeL", "CPython-3.13-KaRaMeL"),
    "names an untracked file that exists": f"`{_SCRATCH_UNTRACKED}` is a scratch text.\n",
    "names a tracked file and an untracked one": (f"`licenses/GPL-3.0.txt` and `{_SCRATCH_UNTRACKED}`"
                                                  " are texts.\n"),
    "names a file that does not exist": "`licenses/MPL-2.0.txt` is the Mozilla text.\n",
    "names a tracked file in another case": "`licenses/gpl-3.0.txt` is the GNU text.\n",
    "names an untracked file in a bare sentence": "See licenses/CPython-3.13-incorporated.txt.\n",
}
TRACKED_PASSING: dict[str, str] = {
    "names only tracked files, with a full stop after one": (
        "`licenses/GPL-3.0.txt` is the GNU text. See licenses/CPython-3.12-incorporated.txt.\n"),
    "names the licenses/ directory only": "The texts are in `licenses/`.\n",
}

EVIDENCE_CONTROLS: dict[str, str] = {
    "today's provenance pointer": _swap("## Licence texts\n", "## Licence texts\n\nSee\n"
                                        "`docs/evidence/platform-sbom/u1/licence-texts-provenance.md`.\n"),
    "a bare path": _swap("its header gives", "docs/evidence/platform-sbom/u1/r2-pip-probe.txt and its header gives"),
    "a repository URL": _swap("its header gives", "https://github.com/humanaxiom/Knowledge-engine/blob/main/"
                                                  "docs/evidence/platform-sbom/ and its header gives"),
    "a Windows path": _swap("its header gives", r"docs\evidence\platform-sbom and its header gives"),
    "upper case": _swap("its header gives", "DOCS/EVIDENCE/x and its header gives"),
}
EVIDENCE_PASSING: dict[str, str] = {
    "the word evidence and app/docs/quickstart.md": _swap(
        "its header gives", "the evidence is in its header, as in `app/docs/quickstart.md`, and its header gives"),
}


# --------------------------------------------------------------------------
# The tests
# --------------------------------------------------------------------------

class NoticeKeAppBaseTest(unittest.TestCase):
    """PSC-14: NOTICE.md's ke-app base paragraph, libpq5, the pointer, the
    CPython incorporated licences, and no repository evidence path."""

    def _controls(self, check, target: tuple[object, ...], controls: dict[str, tuple[object, ...]],
                  passing: dict[str, tuple[object, ...]] | None = None) -> None:
        with self.subTest(control="target shape (N10, N10a) passes"):
            self.assertEqual(check(*target), [])
        for name, args in (passing or {}).items():
            with self.subTest(control=name):
                self.assertEqual(check(*args), [], f"the check failed a control that must pass: {name}")
        for name, args in controls.items():
            with self.subTest(control=name):
                self.assertNotEqual(check(*args), [], f"the check passed a control that must fail: {name}")

    def test_notice_has_ke_app_base_paragraph(self):
        """PSC-14 (ADR-KE-016 point 9, N10, N10a; U1 review B1, N3; security
        L-1, L-3, M-2; human 2026-10-23, pip dropped): a "Base of `ke-app`"
        section naming the shipped stage's base reference byte for byte (the
        stage a FROM scratch last stage copies / from, N10a), which parses
        strictly as [registry/]python:X.Y-slim-CODENAME@sha256:<64 hex>;
        CPython X.Y under /usr/local (Python-2.0) with a pointer to
        /usr/local/lib/pythonX.Y/LICENSE.txt, which holds that licence stack
        only, and licenses/CPython-X.Y-incorporated.txt for the code CPython
        builds in; the base's "Debian <release> (<codename>)" packages with
        their licences in /usr/share/doc/*/copyright and, where the bundle
        carries one, the SBOM (every SBOM mention conditional); libpq5 at the
        pinned LIBPQ_VERSION and every package apt added with it
        (ADDED_PACKAGES), each with its licence; pip only as not shipped, with
        no pip licence bullet, and no pip licence texts named; uv only as not
        shipped. RED (round 2): NOTICE.md's CPython bullet says LICENSE.txt
        holds the licences of the code CPython bundles (M-2), and its pip
        bullet ships pip 25.0.1 with its vendored licences and names
        licenses/Apache-2.0.txt and licenses/MPL-2.0.txt.
        Round 4 (PSC-14 amended round 4; security L-9b fix 5; this resolves a
        contradiction with round 2's "names neither"): licenses/Apache-2.0.txt
        ships for KaRaMeL, so NOTICE.md may name it in a block that names
        KaRaMeL or base-files and not pip; licenses/MPL-2.0.txt never."""
        s = _Scratch(self)

        def files(n: str, d: str, a: frozenset[str]) -> tuple[Path, Path, frozenset[str]]:
            return s.write(n, "NOTICE.md"), s.write(d, "app.Dockerfile"), a

        self._controls(base_paragraph_problems, files(TARGET_NOTICE, TARGET_DOCKERFILE, ADDED_PACKAGES),
                       {k: files(*v) for k, v in BASE_CONTROLS.items()},
                       {k: files(*v) for k, v in BASE_PASSING.items()})
        self.assertEqual(base_paragraph_problems(NOTICE, APP_DOCKERFILE), [])

    def test_notice_names_libpq_as_a_debian_package(self):
        """PSC-14 (Q64; review N4): NOTICE.md names libpq5 as a Debian
        package under the PostgreSQL licence, has no table or heading of
        vendored libraries, and names psycopg-binary only in dated history
        (a block that starts with a date or "History:")."""
        s = _Scratch(self)
        self._controls(libpq_debian_problems, (s.write(TARGET_NOTICE, "NOTICE.md"),),
                       {k: (s.write(v, "NOTICE.md"),) for k, v in LIBPQ_CONTROLS.items()},
                       {k: (s.write(v, "NOTICE.md"),) for k, v in LIBPQ_PASSING.items()})
        self.assertEqual(libpq_debian_problems(NOTICE), [])

    def test_notice_points_to_generated_source_code_section(self):
        """PSC-14 tag; ADR-KE-016 point 9 and N10 (U1 per N15); security U1
        M-1, L-6: NOTICE.md points to the "Source code" section that
        bundle.sh generates in THIRD_PARTY_NOTICES.md and to `sources/`, and
        the same block carries L-6's sentence verbatim: "A bundle whose
        `THIRD_PARTY_NOTICES.md` has no "Source code" section has no
        `sources/`, so it does not itself provide the source that a
        GPL-family licence requires." NOTICE.md nowhere says a bundle carries
        no third-party source code. RED (round 2): NOTICE.md has M-1's
        sentence ("carries no third-party source code", "any of these
        licences")."""
        s = _Scratch(self)
        self._controls(pointer_problems, (s.write(TARGET_NOTICE, "NOTICE.md"),),
                       {k: (s.write(v, "NOTICE.md"),) for k, v in POINTER_CONTROLS.items()})
        self.assertEqual(pointer_problems(NOTICE), [])

    def test_notice_names_cpython_incorporated_licences(self):
        """PSC-14 (security L-5, M-2; N10a): NOTICE.md names
        licenses/CPython-X.Y-incorporated.txt, X.Y the base tag's minor, in a
        block that gives the header's source URL; the file has N10a's
        four-line header (line 1 `CPython X.Y.Z: "Licenses and
        Acknowledgements for Incorporated Software"`, the raw GitHub
        `vX.Y.Z/Doc/license.rst` URL with the same version, `Source sha256:`
        and 64 hex, the Extract line), a blank line, then the extract,
        starting with the heading line and its `=` underline, the heading
        once, naming expat and libmpdec, LF only.
        Round 3 (security L-9; N10, N10a): NOTICE.md also names
        licenses/CPython-X.Y-HACL.txt, whose header is `CPython X.Y.Z: HACL*
        licence header (MIT), Modules/_hacl/`, `Source:
        Python-X.Y.Z/Modules/_hacl/Hacl_Hash_SHA2.c`, `Tarball:` the
        python.org X.Y.Z tarball URL, `Tarball sha256:` and 64 lower-case hex,
        then a blank line and the extract (`/* MIT License` first, ` */` last
        and once, `HACL* Contributors` in it); line 1's version equals the
        incorporated file's and the Source/Tarball versions, X.Y the base
        tag's minor; a NOTICE.md block names the file with
        Modules/_hacl/Hacl_Hash_SHA2.c and the tarball URL. The CPython bullet
        says what each file holds (CPython's list; HACL*, MIT, _md5, _sha1,
        _sha2, _sha3) and claims no complete set. RED (round 3): the HACL file
        does not exist, and NOTICE.md's bullet says the incorporated file has
        the texts ("whose texts are in") and does not name the HACL file.
        Round 4 (security L-9b, I-8; PSC-14 amended round 4): the bullet says
        "the licence of the HACL* hash code ... is in" the HACL file, and names
        KaRaMeL, INRIA and Microsoft, Apache-2.0,
        licenses/CPython-X.Y-KaRaMeL.txt and licenses/Apache-2.0.txt; the
        KaRaMeL file has the header `CPython X.Y.Z: KaRaMeL licence header
        (Apache-2.0), Modules/_hacl/include/krml/`, `Source:
        Python-X.Y.Z/Modules/_hacl/include/krml/internal/target.h`, the
        Tarball: and Tarball sha256: lines (the HACL file's sha256 line), a
        blank line and the 2-line extract (`/* Copyright (c) INRIA and
        Microsoft Corporation. All rights reserved.`, then `Licensed under the
        Apache 2.0 License. */`), LF only, line 1's version that of the
        incorporated and HACL files; licenses/Apache-2.0.txt has sha256
        APACHE_2_SHA256; NOTICE.md's Licence texts names the KaRaMeL file with
        target.h and the tarball URL, and Apache-2.0.txt with base-files,
        /usr/share/common-licenses/Apache-2.0 and the sha256. RED (round 4):
        NOTICE.md's bullet has round 3's wording, and neither file exists."""
        s = _Scratch(self)

        def files(notice: str, text: str | None, dockerfile: str,
                  hacl: str | None = None) -> tuple[Path, Path, Path]:
            n = s.write(notice, "NOTICE.md")
            d = n.parent / "licenses"
            d.mkdir()
            for minor in ("3.12", "3.13"):
                if text is not None:
                    (d / f"CPython-{minor}-incorporated.txt").write_bytes(text.encode("utf-8"))
                if hacl is not None:
                    (d / f"CPython-{minor}-HACL.txt").write_bytes(hacl.encode("utf-8"))
            return n, d, s.write(dockerfile, "app.Dockerfile")

        def hacl_files(notice: str, text: str | None, hacl: str | None, dockerfile: str) -> tuple[Path, Path, Path]:
            return files(notice, text, dockerfile, hacl)

        def karamel_files(notice: str, text: str | None, hacl: str | None, karamel: str | None, apache: str | None,
                          dockerfile: str) -> tuple[Path, Path, Path, str]:
            n, d, df = files(notice, text, dockerfile, hacl)
            for minor in ("3.12", "3.13"):
                if karamel is not None:
                    (d / f"CPython-{minor}-KaRaMeL.txt").write_bytes(karamel.encode("utf-8"))
            if apache is not None:
                (d / "Apache-2.0.txt").write_bytes(apache.encode("utf-8"))
            return n, d, df, FIX_APACHE_SHA

        self._controls(incorporated_licence_problems, files(TARGET_NOTICE, TARGET_INCORPORATED,
                                                            TARGET_DOCKERFILE_FLAT),
                       {k: files(*v) for k, v in INCORPORATED_CONTROLS.items()},
                       {k: files(*v) for k, v in INCORPORATED_PASSING.items()})
        self._controls(hacl_licence_problems, hacl_files(TARGET_NOTICE, TARGET_INCORPORATED, TARGET_HACL,
                                                         TARGET_DOCKERFILE_FLAT),
                       {f"HACL: {k}": hacl_files(*v) for k, v in HACL_CONTROLS.items()},
                       {f"HACL: {k}": hacl_files(*v) for k, v in HACL_PASSING.items()})
        target = (TARGET_NOTICE, TARGET_INCORPORATED, TARGET_HACL, TARGET_KARAMEL, FIX_APACHE_TEXT,
                  TARGET_DOCKERFILE_FLAT)
        self._controls(karamel_licence_problems, karamel_files(*target),
                       {**{f"KaRaMeL: {k}": karamel_files(*v) for k, v in KARAMEL_CONTROLS.items()},
                        "KaRaMeL: the stand-in Apache text against the pinned base-files sha256":
                            karamel_files(*target)[:3]},
                       {f"KaRaMeL: {k}": karamel_files(*v) for k, v in KARAMEL_PASSING.items()})
        for name, check in (("incorporated", incorporated_licence_problems), ("HACL", hacl_licence_problems),
                            ("KaRaMeL and Apache-2.0", karamel_licence_problems)):
            with self.subTest(repository=name):
                self.assertEqual(check(NOTICE, LICENSES, APP_DOCKERFILE), [])

    def test_notice_named_licence_files_are_tracked(self):
        """PSC-14 (U1 round 3; security I-4, review N12): every
        `licenses/...` path NOTICE.md names is listed by `git ls-files --
        licenses`, since scripts/bundle.sh ships only those. Controls run on
        a scratch git repository; a git that cannot run, or a directory that
        is not a work tree, is a named failure, never a skip. RED (round 3):
        licenses/CPython-3.12-incorporated.txt is untracked."""
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo, True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        init = subprocess.run(["git", "-C", str(repo), "init", "-q"], capture_output=True, env=env, check=False)
        self.assertEqual(init.returncode, 0, f"git init failed: {init.stderr!r}")
        for rel in TRACKED_FILES + UNTRACKED_FILES:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(f"{rel}\n", encoding="utf-8")
        add = subprocess.run(["git", "-C", str(repo), "add", "--", *TRACKED_FILES], capture_output=True, env=env,
                             check=False)
        self.assertEqual(add.returncode, 0, f"git add failed: {add.stderr!r}")
        s = _Scratch(self)
        self._controls(untracked_licence_problems, (s.write(TARGET_NOTICE, "NOTICE.md"), repo),
                       {**{k: (s.write(v, "NOTICE.md"), repo) for k, v in TRACKED_CONTROLS.items()},
                        "git cannot run": (s.write(TRACKED_PASSING["names only tracked files, with a full stop "
                                                                   "after one"], "NOTICE.md"), repo,
                                           "git-not-installed-ke-u1"),
                        "not a git work tree": (s.write(TRACKED_PASSING["names only tracked files, with a full "
                                                                        "stop after one"], "NOTICE.md"), s.dir)},
                       {k: (s.write(v, "NOTICE.md"), repo) for k, v in TRACKED_PASSING.items()})
        self.assertEqual(untracked_licence_problems(NOTICE, GIT_ROOT), [])

    def test_notice_cites_no_repo_evidence_path(self):
        """PSC-14 (review B4, security L-8): NOTICE.md cites no
        `docs/evidence/` path (in any case, with / or \\), since a bundle
        carries only app/docs/quickstart.md from docs/. RED: the "Licence
        texts" section points to
        docs/evidence/platform-sbom/u1/licence-texts-provenance.md."""
        s = _Scratch(self)
        self._controls(evidence_path_problems, (s.write(TARGET_NOTICE, "NOTICE.md"),),
                       {k: (s.write(v, "NOTICE.md"),) for k, v in EVIDENCE_CONTROLS.items()},
                       {k: (s.write(v, "NOTICE.md"),) for k, v in EVIDENCE_PASSING.items()})
        self.assertEqual(evidence_path_problems(NOTICE), [])


if __name__ == "__main__":
    unittest.main()
