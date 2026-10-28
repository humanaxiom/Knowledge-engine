"""platform-sbom U7a: the source lock's pure half (PSC-15; design-notes N5 and
"N5 amendment, U7", items 2, 4, 5 and 6 (a)-(f)). Orchestrator U7a rulings
1-4 (2026-10-25): O1 goes to the human as Q71, the `.pgdg` mapping is pinned
(182 keys) and the tenth host is NOT added in U7a; O2 needs nothing here.

Interface pinned by these tests (tester, U7a RED, 2026-10-25). All in
`scripts/sbom_check.py`, standard library, pure:
- `lock_needs(policy, docs) -> (needs, problems)`: `docs` maps a bundled
  image name to its SPDX document; `needs[key] = {"kind": <kind>,
  "packages": [{"image", "purl", "spdxid"}, ...]}` for every row
  `classify_document(image, doc, policy["always"], policy["exempt"])` marks
  `needs` (item 2's mapping); `problems` names each row that maps to no kind.
  (The signature is the tester's reading; the amendment names the function.)
- `lock_text(lock) -> str`: `json.dumps(lock, indent=1, sort_keys=True,
  ensure_ascii=True) + "\\n"`.
- `lock_problems(lock_text, policy, docs, arch) -> list[str]`: the lock is
  passed as its file text (the canonical-form rule needs the text).
- `sample_keys(lock, arch) -> list[str]`: on the parsed lock.
- `sbom_check.py lock-check --lock L --policy P --arch A --sbom IMG=PATH...`.

pgdg: Q71 is ruled (A71, U7d precision P5): `apt-archive.postgresql.org` is
the tenth host and pgdg entries carry `suite`; the paragraph below is U7a
round 1's, kept for its history.
(ruling 1). Rework round 1 (N5 amendment U7, "Rework round 1", item 3):
until Q71 the kind has no allowed host, so every pgdg file is a problem and
the tests no longer add that host to a policy copy (the U7a RED did:
superseded, CLAUDE.md Contradictions). The small synthetic set therefore has
no pgdg key, and the full fixture lock's only problems are its pgdg files.

Fixtures: tests/fixtures/sbom-u3 (neo4j read as ke-neo4j, U6) and the
committed docker/source-policy.json; never docs/evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import shutil
import unittest
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from tests import sbom_support as ss
from tests.engine_support import ROOT
from tests.test_sbom_bundle import load_sbom_check

POLICY = ROOT / "docker" / "source-policy.json"
PGDG_HOST = "apt-archive.postgresql.org"  # O1 (a), Q71: the tenth host (A71, U7d P5)
PGDG_SUITE = "bookworm-pgdg-archive"
ARCH = "amd64"
FROM_NEO4J = "second fetch: security 2026-10-25, docs/evidence/platform-sbom/sources-provenance.md"


def fn(name: str) -> Callable[..., Any]:
    got = getattr(load_sbom_check(), name, None)
    if not callable(got):
        raise AssertionError(f"scripts/sbom_check.py has no {name}() (U7a interface, N5 amendment U7; "
                             "tests/test_sources_lock.py)")
    return got


def policy() -> dict[str, Any]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def pgdg_free(problems: list[str]) -> list[str]:
    """The problems that do not name a pgdg entry (rework round 1, item 3:
    every pgdg file is a problem until Q71)."""
    return [x for x in problems if not x.startswith("lock: pgdg:")]


def fixture_docs() -> dict[str, Any]:
    return {("ke-neo4j" if f == "neo4j" else f): ss.spdx_doc("ke-neo4j" if f == "neo4j" else f, ss.u3_rows(f))
            for f in ss.U3_IMAGES}


def canon(lock: Any) -> str:
    return json.dumps(lock, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def _h(alg: str, seed: str) -> str:
    return hashlib.new(alg, seed.encode()).hexdigest()


def _f(name: str, url: str, seed: str, alg: str, value: str | None, frm: str, size: int = 1000) -> dict[str, Any]:
    sha = _h("sha256", seed)
    return {"name": name, "url": url, "sha256": sha, "size": size,
            "upstream": {"alg": alg, "value": sha if alg == "sha256" else value, "from": frm}}


def good_entry(key: str, size: int = 1000) -> dict[str, Any]:
    """One valid lock entry for `key` (N5 amendment, U7, items 4 and 6 (c))."""
    kind, body = key.split(":", 1)
    name, _, ver = body.rpartition("@")
    entry: dict[str, Any] = {"kind": kind, "arches": [ARCH], "origin": "manual" if kind == "neo4j" else "generated"}
    if kind in ("deb", "pgdg"):
        nover = ver.split(":", 1)[1] if ":" in ver else ver
        dsc, orig = f"{name}_{nover}.dsc", f"{name}_{nover.rsplit('-', 1)[0]}.orig.tar.xz"
        if kind == "deb":
            d1, o1 = _h("sha1", key + dsc), _h("sha1", key + orig)
            entry["files"] = [
                _f(dsc, f"https://snapshot.debian.org/file/{d1}", key + dsc, "sha1", d1,
                   f"snapshot.debian.org mr/package/{name}/{ver}/srcfiles", size),
                _f(orig, f"https://snapshot.debian.org/file/{o1}", key + orig, "sha256", None, f"{dsc} Checksums-Sha256",
                   size)]
        else:
            # U7d P5: the pool rule, `suite`, and the exact from texts (was a placeholder until Q71).
            pool = f"https://{PGDG_HOST}/pub/repos/apt/pool/main/{name[:4] if name.startswith('lib') else name[0]}/{name}"
            entry["suite"] = PGDG_SUITE
            entry["files"] = [
                _f(dsc, f"{pool}/{dsc}", key + dsc, "sha256", None, f"{PGDG_HOST} {PGDG_SUITE} Sources", size),
                _f(orig, f"{pool}/{orig}", key + orig, "sha256", None, f"{dsc} Checksums-Sha256", size)]
    elif kind == "apk":
        commit = _h("sha1", key)
        tar = f"{name}-{ver.rsplit('-r', 1)[0]}.tar.gz"
        entry.update(commit=commit, branch="v3.23", repo="main")
        entry["files"] = [
            # U7c rework round 1, item 9: the API raw url (was /alpine/aports/-/raw/<commit>/main/<name>/APKBUILD).
            _f("APKBUILD", "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/"
               + quote(f"main/{name}/APKBUILD", safe="") + f"/raw?ref={commit}",
               # U7c gap rulings item 3: this from text replaces A3's (was "gitlab.alpinelinux.org files API at").
               key + "APKBUILD", "sha256", None, f"gitlab files API content_sha256 at {commit}", size),
            _f(tar, f"https://distfiles.alpinelinux.org/distfiles/v3.23/{tar}", key + tar, "sha512",
               _h("sha512", key + tar), f"APKBUILD sha512sums at {commit}", size)]
    elif kind == "neo4j":
        entry["files"] = [_f(f"{ver}.tar.gz", f"https://github.com/neo4j/neo4j/archive/refs/tags/{ver}.tar.gz",
                             key, "sha256", None, FROM_NEO4J, size)]
    elif kind == "temurin":
        tag = body
        v = tag[len("jdk-"):]
        feature = v.split(".", 1)[0]
        asset = f"OpenJDK{feature}U-jdk-sources_{v.replace('+', '_')}.tar.gz"
        entry["files"] = [_f(asset, f"https://github.com/adoptium/temurin{feature}-binaries/releases/download/"
                                    f"{quote(tag, safe='')}/{asset}", key, "sha256", None, f"{asset}.sha256.txt", size)]
    elif kind == "pypi":
        sdist = f"{name}-{ver}.tar.gz"
        h = _h("sha256", key + "path")  # rework round 2, item 5: /packages/<2 hex>/<2 hex>/<60 hex>/<name>
        entry["files"] = [_f(sdist, f"https://files.pythonhosted.org/packages/{h[:2]}/{h[2:4]}/{h[4:]}/{sdist}", key,
                             "sha256", None,
                             "uv.lock", size)]
    elif kind == "maven":
        g, a = name.split(":", 1)
        jar = f"{a}-{ver}-sources.jar"
        entry["files"] = [_f(jar, f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{ver}/{jar}", key, "sha1",
                             _h("sha1", key), f"{jar}.sha1", size)]
    else:
        raise AssertionError(f"no good entry for {key}")
    return entry


def good_lock(keys: Any) -> dict[str, Any]:
    return {"format": 1, "components": {k: good_entry(k) for k in sorted(keys)}}


# A small set of synthetic docs needing one key per kind (plus an epoch deb),
# for the schema rows; licences make each row `needs` by the classifier or
# by the committed `always`.
def small_docs() -> dict[str, Any]:
    alp = "?arch=x86_64&distro=alpine-3.23.3"
    return {
        "postgres": ss.spdx_doc("postgres", [
            {"purl": ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"), "declared": "GPL-3.0-or-later"},
            {"purl": ss.deb("libattr1", "1:2.5.1-4", upstream="attr"), "declared": "LGPL-2.1-or-later"}]),
        "valkey": ss.spdx_doc("valkey", [
            {"purl": f"pkg:apk/alpine/readline@8.2.13-r1{alp}", "declared": "GPL-3.0-or-later"}]),
        "ke-neo4j": ss.spdx_doc("ke-neo4j", [
            {"purl": "pkg:maven/org.neo4j/neo4j@5.26.32", "declared": "GPL-3.0-only"},
            {"purl": "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS", "declared": "NOASSERTION"},
            {"purl": "pkg:maven/javax.xml.bind/jaxb-api@2.2.12", "declared": JAXB_ID}]),
        "ke-app": ss.spdx_doc("ke-app", [{"purl": "pkg:pypi/psycopg@3.3.6", "declared": "LGPL-3.0-only"},
                                         {"purl": "pkg:pypi/psycopg-c@3.3.6", "declared": "LGPL-3.0-only"}]),
    }


JAXB_ID = "LicenseRef-https---glassfish.java.net-public-CDDL-GPL-1-1.html--https---glassfish.java.net-public-CDDL-GPL-1-1.html"
SMALL_KEYS = frozenset({"deb:bash@5.2.15-2", "deb:attr@1:2.5.1-4", "pypi:psycopg-c@3.3.6",
                        "apk:readline@8.2.13-r1", "neo4j:neo4j@5.26.32", "temurin:jdk-21.0.12.1+1",
                        "maven:javax.xml.bind:jaxb-api@2.2.12", "pypi:psycopg@3.3.6"})

# The 183 lock keys the six U3 fixtures need with the committed policy (N5
# amendment, U7, item 2; the architect's run and the tester's agree; 182 until U7e).
# U7e R4 re-pin (base 6dd8b6da): +deb:openssl@3.0.22-1~deb12u2 and
# +deb:ca-certificates@20250419~deb12u2, -deb:ca-certificates@20250419~deb12u1
# (only ke-app needed it); openssl ~deb12u1 stays for postgres; tzdata has no
# key (public domain). Explained by docs/evidence/platform-sbom/u7e/key-diff.txt
# l.6-8 <- base-dpkg-diff.txt (libssl3/openssl and ca-certificates moved).
FIXTURE_KEYS = frozenset({
    "apk:alpine-baselayout@3.7.1-r8", "apk:alpine-baselayout@3.7.2-r1", "apk:apk-tools@3.0.3-r1",
    "apk:apk-tools@3.0.8-r0", "apk:busybox@1.37.0-r30", "apk:busybox@1.37.0-r31", "apk:gcc@15.2.0-r2",
    "apk:gcc@15.2.0-r5", "apk:geoip@1.6.12-r6", "apk:gettext@0.24.1-r1", "apk:libcap-ng@0.8.5-r2",
    "apk:libidn2@2.3.8-r0", "apk:libunistring@1.4.1-r0", "apk:musl@1.2.5-r21", "apk:musl@1.2.6-r2",
    "apk:pax-utils@1.3.8-r2", "apk:pax-utils@1.3.9-r1", "apk:util-linux@2.42.3-r1", "apk:xz@5.8.2-r0",
    "deb:acl@2.3.1-3", "deb:acl@2.3.2-2", "deb:adduser@3.134", "deb:apt@2.6.1", "deb:apt@3.0.3",
    "deb:attr@1:2.5.1-4", "deb:attr@1:2.5.2-3", "deb:audit@1:3.0.9-1", "deb:audit@1:4.0.2-2+deb13u1",
    "deb:base-files@12.4+deb12u15", "deb:base-files@13.8+deb13u7", "deb:base-passwd@3.6.1", "deb:base-passwd@3.6.7",
    "deb:bash@5.2.15-2", "deb:bash@5.2.37-2", "deb:bzip2@1.0.8-5", "deb:bzip2@1.0.8-6",
    "deb:ca-certificates@20250419", "deb:ca-certificates@20250419~deb12u2", "deb:cdebconf@0.270",
    "deb:cdebconf@0.280", "deb:coreutils@9.1-1", "deb:coreutils@9.7-3", "deb:cyrus-sasl2@2.1.28+dfsg-10",
    "deb:dash@0.5.12-12", "deb:dash@0.5.12-2", "deb:db5.3@5.3.28+dfsg2-1", "deb:db5.3@5.3.28+dfsg2-9",
    "deb:debian-archive-keyring@2023.3+deb12u2", "deb:debian-archive-keyring@2025.1", "deb:debianutils@5.23.2",
    "deb:debianutils@5.7-0.5~deb12u1", "deb:diffutils@1:3.10-4", "deb:diffutils@1:3.8-4", "deb:dpkg@1.21.23",
    "deb:dpkg@1.22.22", "deb:e2fsprogs@1.47.0-2", "deb:e2fsprogs@1.47.2-3", "deb:findutils@4.10.0-3",
    "deb:findutils@4.9.0-4", "deb:gcc-12@12.2.0-14+deb12u1", "deb:gcc-14@14.2.0-19", "deb:gdbm@1.23-3",
    "deb:glibc@2.36-9+deb12u14", "deb:glibc@2.41-12+deb13u4", "deb:gmp@2:6.2.1+dfsg1-1.1", "deb:gmp@2:6.3.0+dfsg-3",
    "deb:gnupg2@2.2.40-1.1+deb12u2", "deb:gnutls28@3.7.9-2+deb12u7", "deb:gnutls28@3.8.9-3+deb13u4",
    "deb:grep@3.11-4", "deb:grep@3.8-5", "deb:gzip@1.12-1", "deb:gzip@1.13-1+deb13u1", "deb:hostname@3.23+nmu1",
    "deb:hostname@3.25", "deb:icu@72.1-3+deb12u1", "deb:init-system-helpers@1.65.2+deb12u1",
    "deb:init-system-helpers@1.69~deb13u1", "deb:jq@1.7.1-6+deb13u4", "deb:keyutils@1.6.3-2",
    "deb:keyutils@1.6.3-6", "deb:krb5@1.20.1-2+deb12u5", "deb:krb5@1.21.3-5+deb13u1", "deb:less@590-2.1~deb12u2",
    "deb:libassuan@2.5.5-5", "deb:libcap-ng@0.8.3-1", "deb:libcap-ng@0.8.5-4", "deb:libcap2@1:2.66-4+deb12u3",
    "deb:libcap2@1:2.75-10+deb13u1", "deb:libffi@3.4.4-1", "deb:libffi@3.4.8-2", "deb:libgcrypt20@1.10.1-3+deb12u1",
    "deb:libgpg-error@1.46-1", "deb:libidn2@2.3.3-1", "deb:libidn2@2.3.8-2", "deb:libjson-perl@4.10000-1",
    "deb:libksba@1.6.3-2", "deb:libnsl@1.3.0-2", "deb:libnsl@1.3.0-3", "deb:libonig@6.9.9-1",
    "deb:libseccomp@2.5.4-1+deb12u1", "deb:libseccomp@2.6.0-2", "deb:libselinux@3.4-1", "deb:libselinux@3.8.1-1",
    "deb:libsemanage@3.4-1", "deb:libsemanage@3.8.1-1", "deb:libsepol@3.4-2.1", "deb:libsepol@3.8.1-1",
    "deb:libtasn1-6@4.19.0-2+deb12u1", "deb:libtasn1-6@4.20.0-2+deb13u1", "deb:libtirpc@1.3.3+ds-1",
    "deb:libtirpc@1.3.6+ds-1", "deb:libunistring@1.0-2", "deb:libunistring@1.3-2", "deb:libxcrypt@1:4.4.33-2",
    "deb:libxcrypt@1:4.4.38-1", "deb:libxslt@1.1.35-1+deb12u4", "deb:libzstd@1.5.4+dfsg2-5",
    "deb:libzstd@1.5.7+dfsg-1", "deb:linux@6.12.113-1", "deb:lz4@1.10.0-4", "deb:lz4@1.9.4-1",
    "deb:mawk@1.3.4.20200120-3.1", "deb:mawk@1.3.4.20250131-1", "deb:netbase@6.4", "deb:netbase@6.5",
    "deb:nettle@3.10.1-1", "deb:nettle@3.8.1-2", "deb:npth@1.6-3", "deb:openldap@2.5.13+dfsg-5",
    "deb:openssl@3.0.22-1~deb12u1", "deb:openssl@3.0.22-1~deb12u2", "deb:openssl@3.5.7-1~deb13u3",
    "deb:p11-kit@0.24.1-2", "deb:p11-kit@0.25.5-3",
    "deb:pam@1.5.2-6+deb12u2", "deb:pam@1.7.0-5", "deb:perl@5.36.0-7+deb12u3", "deb:perl@5.36.0-7+deb12u4",
    "deb:perl@5.40.1-6+deb13u1", "deb:pinentry@1.2.1-1", "deb:postgresql-15@15.19-0+deb12u1",
    "deb:procps@2:4.0.4-9", "deb:python3.13@3.13.5-2+deb13u5", "deb:readline@8.2-1.3", "deb:readline@8.2-6",
    "deb:rpcsvc-proto@1.4.3-1", "deb:rust-sequoia-sqv@1.3.0-3", "deb:sed@4.9-1+deb12u1", "deb:sed@4.9-2+deb13u1",
    "deb:sensible-utils@0.0.17+nmu1", "deb:shadow@1:4.13+dfsg1-1+deb12u2", "deb:shadow@1:4.17.4-2",
    "deb:sqlite3@3.40.1-2+deb12u2", "deb:sqlite3@3.46.1-7+deb13u2", "deb:systemd@252.39-1~deb12u2",
    "deb:systemd@257.13-1~deb13u1", "deb:sysvinit@3.06-4", "deb:sysvinit@3.14-4", "deb:tar@1.34+dfsg-1.2+deb12u1",
    "deb:tar@1.35+dfsg-3.1", "deb:ucf@3.0043+nmu1+deb12u1", "deb:usrmerge@37~deb12u1",
    "deb:util-linux@2.38.1-5+deb12u3", "deb:util-linux@2.41.5-0+deb13u1", "deb:wget@1.25.0-2", "deb:xxhash@0.8.1-1",
    "deb:xxhash@0.8.3-2", "deb:xz-utils@5.4.1-1+deb12u2", "deb:xz-utils@5.8.1-1+deb13u1",
    "deb:xz-utils@5.8.1-1+deb13u2", "deb:z3@4.8.12-3.1", "maven:javax.xml.bind:jaxb-api@2.2.12",
    "neo4j:neo4j@5.26.32", "pgdg:postgresql-16@16.15-1.pgdg12+2", "pgdg:postgresql-18@18.6-1.pgdg12+2",
    "pgdg:postgresql-common@293.pgdg12+1", "pypi:autocommand@2.2.2", "pypi:ldap3@2.9.1", "pypi:pandas@2.3.3",
    "pypi:psycopg-c@3.3.6", "pypi:psycopg@3.3.6", "temurin:jdk-21.0.12.1+1",
})


def lock_problems_of(lock: Any, *, pol: dict[str, Any] | None = None, docs: dict[str, Any] | None = None,
                     arch: str = ARCH) -> list[str]:
    text = lock if isinstance(lock, str) else canon(lock)
    return fn("lock_problems")(text, pol if pol is not None else policy(),
                               docs if docs is not None else small_docs(), arch)


def miss(image: str, purl: str, key: str, arch: str = ARCH) -> str:
    return (f"{image}: {purl} needs source; the lock has no {key} for {arch}: "
            f"run scripts/sources_lock.sh --arch {arch}")


def stale(key: str, arch: str = ARCH) -> str:
    return f"lock: {key} is listed for {arch} but no image needs it: run scripts/sources_lock.sh --arch {arch}"


class LockNeedsTest(unittest.TestCase):
    """Item 6 (a), (b): which keys the images need (item 2's mapping)."""

    def test_needs_from_the_fixtures(self):
        needs, problems = fn("lock_needs")(policy(), fixture_docs())
        self.assertEqual(problems, [], "a fixture row that needs source maps to no lock kind")
        self.assertEqual(set(needs), FIXTURE_KEYS, f"missing {sorted(FIXTURE_KEYS - set(needs))[:5]}, "
                                                   f"extra {sorted(set(needs) - FIXTURE_KEYS)[:5]}")
        self.assertEqual(Counter(k.split(":", 1)[0] for k in needs),
                         # deb 152 -> 153 in U7e: u7e/key-diff.txt l.6-8 (+2 -1 deb keys).
                         Counter(deb=153, pgdg=3, apk=19, neo4j=1, temurin=1, maven=1, pypi=5))
        for key, entry in needs.items():
            with self.subTest(key=key):
                self.assertEqual(entry.get("kind"), key.split(":", 1)[0])
                self.assertTrue(entry.get("packages") and all({"image", "purl", "spdxid"} <= set(p)
                                                              for p in entry["packages"]), entry)
        purls = {key: {p["purl"].split("?", 1)[0] for p in e["packages"]} for key, e in needs.items()}
        images = {key: {p["image"] for p in e["packages"]} for key, e in needs.items()}
        with self.subTest(case="named rows (item 6 (a))"):
            self.assertLessEqual({"pkg:deb/debian/gcc-12-base@12.2.0-14%2Bdeb12u1",
                                  "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1",
                                  "pkg:deb/debian/libstdc%2B%2B6@12.2.0-14%2Bdeb12u1"}, purls["deb:gcc-12@12.2.0-14+deb12u1"])
            self.assertEqual(images["deb:gcc-12@12.2.0-14+deb12u1"], {"ke-app", "postgres"})
            self.assertEqual(images["deb:gcc-14@14.2.0-19"], {"ke-neo4j", "phoenix"})
            self.assertEqual(len(needs["neo4j:neo4j@5.26.32"]["packages"]), 73)
            self.assertIn("pkg:maven/org.neo4j.app/neo4j-server@5.26.32", purls["neo4j:neo4j@5.26.32"])
            self.assertEqual({p.split("@", 1)[0] for p in purls["temurin:jdk-21.0.12.1+1"]},
                             {"pkg:generic/oracle/openjdk", "pkg:maven/jrt-fs/jrt-fs"})
            self.assertEqual(purls["maven:javax.xml.bind:jaxb-api@2.2.12"], {"pkg:maven/javax.xml.bind/jaxb-api@2.2.12"})
            self.assertEqual({k for k in needs if k.startswith("pypi:")},
                             {"pypi:psycopg@3.3.6", "pypi:psycopg-c@3.3.6", "pypi:autocommand@2.2.2",
                              "pypi:ldap3@2.9.1", "pypi:pandas@2.3.3"})
            self.assertEqual({k for k in needs if k.startswith("pgdg:")},
                             {"pgdg:postgresql-16@16.15-1.pgdg12+2", "pgdg:postgresql-18@18.6-1.pgdg12+2",
                              "pgdg:postgresql-common@293.pgdg12+1"})
        with self.subTest(case="exempt and listed-only rows give no key (jna, javassist and 41 more)"):
            listed = {p.split("@", 1)[0] for s in purls.values() for p in s}
            for purl in ("pkg:maven/com.sun.jna/jna", "pkg:maven/org.javassist/javassist",
                         "pkg:maven/org.glassfish.hk2/hk2-api"):
                self.assertNotIn(purl, listed)
        with self.subTest(case="distinct Debian sources per image (item 2)"):
            per = Counter()
            for key, imgs in images.items():
                for img in imgs:
                    per[(img, key.split(":", 1)[0])] += 1
            self.assertEqual({k: v for k, v in per.items() if k[1] in ("deb", "pgdg")},
                             {("ke-app", "deb"): 70, ("ke-neo4j", "deb"): 61, ("phoenix", "deb"): 21,
                              ("postgres", "deb"): 78, ("postgres", "pgdg"): 3})

    def test_mapping_table(self):
        lock_needs = fn("lock_needs")
        empty = {"always": [], "exempt": [], "hosts": []}
        alp = "?arch=x86_64&distro=alpine-3.23.3"
        rows = {  # purl -> expected key (or None: no key and no problem)
            ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"): "deb:bash@5.2.15-2",
            ss.deb("sqv", "1.3.0-3+b2", upstream="rust-sequoia-sqv@1.3.0-3"): "deb:rust-sequoia-sqv@1.3.0-3",
            ss.deb("libattr1", "1:2.5.1-4", upstream="attr"): "deb:attr@1:2.5.1-4",
            ss.deb("libgcc-s1", "12.2.0-14+deb12u1", upstream="gcc-12"): "deb:gcc-12@12.2.0-14+deb12u1",
            ss.deb("tar", "1.34+dfsg-1.2+deb12u1"): "deb:tar@1.34+dfsg-1.2+deb12u1",
            ss.deb("libpq5", "18.6-1.pgdg12+2", upstream="postgresql-18"): "pgdg:postgresql-18@18.6-1.pgdg12+2",
            ss.deb("postgresql-common", "293.pgdg12+1"): "pgdg:postgresql-common@293.pgdg12+1",
            f"pkg:apk/alpine/libstdc%2B%2B@15.2.0-r2{alp}&upstream=gcc": "apk:gcc@15.2.0-r2",
            f"pkg:apk/alpine/readline@8.2.13-r1{alp}": "apk:readline@8.2.13-r1",
            "pkg:maven/org.neo4j/neo4j@5.26.32": "neo4j:neo4j@5.26.32",
            "pkg:maven/org.neo4j.app/neo4j-server@5.26.32": "neo4j:neo4j@5.26.32",
            "pkg:maven/com.neo4j/fleet@5.26.32": "neo4j:neo4j@5.26.32",
            "pkg:maven/org.neo4j.bolt/bolt-codec@12.0.0": "maven:org.neo4j.bolt:bolt-codec@12.0.0",
            "pkg:maven/org.neo4jx/other@5.26.32": "maven:org.neo4jx:other@5.26.32",
            "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS?repository_url=x": "temurin:jdk-21.0.12.1+1",
            "pkg:maven/jrt-fs/jrt-fs@21.0.12.1": "temurin:jdk-21.0.12.1+1",
            "pkg:maven/javax.xml.bind/jaxb-api@2.2.12": "maven:javax.xml.bind:jaxb-api@2.2.12",
            "pkg:pypi/Psycopg_C@3.3.6": "pypi:psycopg-c@3.3.6",
        }
        doc = ss.spdx_doc("ke-neo4j", [{"purl": p, "declared": "GPL-2.0-only"} for p in rows]
                          + [{"purl": "pkg:maven/org.example/permissive@1.0", "declared": "MIT"}])
        needs, problems = lock_needs(empty, {"ke-neo4j": doc})
        self.assertEqual(problems, [])
        got = {p["purl"]: key for key, e in needs.items() for p in e["packages"]}
        for purl, key in rows.items():
            with self.subTest(purl=purl):
                self.assertEqual(got.get(purl), key)
        self.assertNotIn("pkg:maven/org.example/permissive@1.0", got, "a row with needs False gets a key")
        bad = {"pkg:npm/left-pad@1.3.0": "left-pad", "pkg:deb/ubuntu/bash@5.2.21-2ubuntu4": "ubuntu"}
        for purl, word in bad.items():
            with self.subTest(problem=purl):
                needs, problems = lock_needs(empty, {"phoenix": ss.spdx_doc("phoenix", [
                    {"purl": purl, "declared": "GPL-2.0-only"}])})
                self.assertEqual(needs, {})
                self.assertTrue(problems and "phoenix" in problems[0] and purl in problems[0], problems)
        with self.subTest(problem="a row with no purl is named by SPDXID"):
            needs, problems = lock_needs(empty, {"phoenix": ss.spdx_doc("phoenix", [
                {"purl": None, "name": "mystery", "spdxid": "SPDXRef-Package-mystery-1", "declared": "GPL-2.0-only"}])})
            self.assertTrue(problems and "SPDXRef-Package-mystery-1" in problems[0], problems)
        with self.subTest(problem="a jrt-fs that is not the image's Temurin build"):
            needs, problems = lock_needs(empty, {"ke-neo4j": ss.spdx_doc("ke-neo4j", [
                {"purl": "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS", "declared": "GPL-2.0-only"},
                {"purl": "pkg:maven/jrt-fs/jrt-fs@21.0.11", "declared": "GPL-2.0-only"}])})
            self.assertTrue(problems and "jrt-fs" in problems[0] and "21.0.11" in problems[0]
                            and "ke-neo4j" in problems[0], problems)
            self.assertEqual(set(needs), {"temurin:jdk-21.0.12.1+1"})
        with self.subTest(problem="neo4j-group rows with no org.neo4j/neo4j row"):
            needs, problems = lock_needs(empty, {"ke-neo4j": ss.spdx_doc("ke-neo4j", [
                {"purl": "pkg:maven/org.neo4j/neo4j-kernel@5.26.32", "declared": "GPL-3.0-only"},
                {"purl": "pkg:maven/org.neo4j.app/neo4j-server@5.26.32", "declared": "GPL-3.0-only"}])})
            self.assertEqual(len(problems), 2, problems)
            self.assertEqual(needs, {})


# Rework round 1, item 8 (review N7): the problem each bad-shape row must
# produce, as a substring (the field and the rule), so an unrelated problem
# from the same mutation cannot mask the row. Wording: the tester's target
# (u7a/r1-target-sbom_check.py), which the developer keeps.
_KEY = "not a valid {} key"
BAD_SHAPE_SUBSTRINGS = {
    "not canonical (indent 2)": "lock: not in canonical form: regenerate",
    "not canonical (no final newline)": "lock: not in canonical form: regenerate",
    "not canonical (keys unsorted)": "lock: not in canonical form: regenerate",
    "a third top key": "top-level keys are not exactly format and components",
    "format 2": "format 2 is not 1",
    "components a list": "components is not an object",
    "deb src upper case": _KEY.format("deb"), "deb src one char": _KEY.format("deb"),
    "deb version not starting with a digit": _KEY.format("deb"), "deb key with .pgdg": _KEY.format("deb"),
    "pgdg key without .pgdg": _KEY.format("pgdg"), "apk without -r<n>": _KEY.format("apk"),
    "neo4j with a v": _KEY.format("neo4j"), "neo4j another name": _KEY.format("neo4j"),
    "temurin without jdk-": _KEY.format("temurin"), "temurin without +build": _KEY.format("temurin"),
    "pypi not PEP 503": _KEY.format("pypi"), "pypi underscore": _KEY.format("pypi"),
    "maven without a group": _KEY.format("maven"),
    "an unknown kind": "not a lock key of a known kind",
    "kind is not the key prefix": "kind 'apk' is not deb",
    "arches empty": "is not a sorted, unique, non-empty subset", "arches unsorted": "is not a sorted, unique, non-empty subset",
    "arches duplicated": "is not a sorted, unique, non-empty subset", "arches unknown": "is not a sorted, unique, non-empty subset",
    "origin unknown": "neo4j is manual, every other kind generated", "deb manual": "neo4j is manual, every other kind generated",
    "neo4j generated": "neo4j is manual, every other kind generated",
    "neo4j from not the second fetch": "upstream from is not `second fetch: security",
    "neo4j from with a reviewer other than security": "upstream from is not `second fetch: security",
    "neo4j from dated after today (UTC)": "the second-fetch date 2999-01-01 is after today (UTC)",
    "neo4j from with an impossible date": "the second-fetch date 2026-13-01 is not a date",
    "files empty": "no files",
    "a file with an extra key": "a file has an unexpected key note",
    "a file without size": "a file has no size",
    "a name with /": "not a safe file name", "a name ..": "not a safe file name",
    "a name with a leading dot": "not a safe file name", "a name of 256 characters": "not a safe file name",
    "a name duplicated in the entry": "is listed twice",
    "http": "url scheme is not https", "userinfo": "url carries userinfo", "a port": "url carries a port",
    "a query": "url carries a query", "a fragment": "url carries a fragment",
    "host deb.debian.org": "url host deb.debian.org is not in docker/source-policy.json hosts",
    "host evil.github.com": "url host evil.github.com is not in docker/source-policy.json hosts",
    "a pypi file on pypi.org (metadata only, O2)": "url host pypi.org is not in docker/source-policy.json hosts",
    "host Snapshot.debian.org": "url host Snapshot.debian.org is not in docker/source-policy.json hosts",
    "sha256 63 hex": "sha256 is not 64 lower-case hex", "sha256 65 hex": "sha256 is not 64 lower-case hex",
    "sha256 upper case": "sha256 is not 64 lower-case hex",
    "size 0": "is not an int in 1..4294967296", "size -1": "is not an int in 1..4294967296",
    "size true": "is not an int in 1..4294967296", 'size "1"': "is not an int in 1..4294967296",
    "upstream with an extra key": "upstream has an unexpected key note",
    "upstream alg md5": "upstream alg 'md5' is not sha1, sha256 or sha512",
    "upstream sha1 value 64 hex": "upstream value is not 40 lower-case hex",
    "upstream value upper case": "upstream value is not 40 lower-case hex",
    "upstream sha256 value differs from the file's": "upstream sha256 differs from the file's sha256",
    "upstream from blank": "upstream from is blank",
    "deb with two .dsc": "2 .dsc files, want exactly 1", "deb with no .dsc": "0 .dsc files, want exactly 1",
    "deb .dsc named for another version": "the .dsc is bash_5.2.15-3.dsc, want bash_5.2.15-2.dsc",
    "deb .dsc keeping the epoch": "want attr_2.5.1-4.dsc",
    "deb .dsc upstream sha256": "the .dsc is not sha1 with a snapshot.debian.org /file/<that sha1> url",
    "deb .dsc url not /file/<its sha1>": "the .dsc is not sha1 with a snapshot.debian.org /file/<that sha1> url",
    "deb other file sha1": "is not sha256 from bash_5.2.15-2.dsc Checksums-Sha256",
    "deb other file from another .dsc": "is not sha256 from bash_5.2.15-2.dsc Checksums-Sha256",
    "deb other file url under /archive": "not a deb file url",
    "apk without commit": "missing key commit", "apk without branch": "missing key branch",
    "apk without repo": "missing key repo",
    "apk commit not 40 hex": "commit 'abc123' is missing or malformed",
    "apk branch without v": "branch '3.23' is missing or malformed",
    "apk without APKBUILD": "not exactly one APKBUILD with sha256",
    "apk APKBUILD sha512": "not exactly one APKBUILD with sha256",
    "apk other file sha256": "is not sha512 (APKBUILD sha512sums)",
    "maven two files": "not one -sources.jar with sha1", "maven not a -sources.jar": "not one -sources.jar with sha1",
    "maven upstream sha256": "not one -sources.jar with sha1",
    "temurin two files": "not one file with sha256", "temurin upstream sha1": "not one file with sha256",
    "pypi upstream sha512": "not one file with sha256",
}


class LockSchemaTest(unittest.TestCase):
    """Item 6 (c): the schema on a synthetic lock, one entry per kind."""

    def test_lock_text_is_canonical(self):
        d = good_lock(SMALL_KEYS)
        self.assertEqual(fn("lock_text")(d), canon(d))
        self.assertEqual(fn("lock_text")({"b": 1, "a": chr(0xe9)}), '{\n "a": "' + chr(92) + 'u00e9",\n "b": 1\n}\n')

    def test_good_small_lock_passes(self):
        self.assertEqual(lock_problems_of(good_lock(SMALL_KEYS)), [])

    def test_good_full_lock_passes(self):
        # U7d (A71, P5): pgdg is legal now, so the full fixture lock has no problem
        # (until U7d its 3 pgdg entries' files were the only problems).
        self.assertEqual(lock_problems_of(good_lock(FIXTURE_KEYS), docs=fixture_docs()), [])

    def test_bad_shapes(self):
        def mut(key: str, change: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
            d = good_lock(SMALL_KEYS)
            change(d["components"][key])
            return d

        def top(change: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
            d = good_lock(SMALL_KEYS)
            change(d)
            return d

        def f0(key: str, change: Callable[[dict[str, Any]], Any], i: int = 0) -> dict[str, Any]:
            return mut(key, lambda e: change(e["files"][i]))

        def rekey(old: str, new: str) -> dict[str, Any]:
            d = good_lock(SMALL_KEYS)
            d["components"][new] = d["components"].pop(old)
            return d
        deb, apk, neo, tem, pyp, mav = ("deb:bash@5.2.15-2", "apk:readline@8.2.13-r1", "neo4j:neo4j@5.26.32",
                                        "temurin:jdk-21.0.12.1+1", "pypi:psycopg@3.3.6",
                                        "maven:javax.xml.bind:jaxb-api@2.2.12")
        good = good_lock(SMALL_KEYS)
        bad: dict[str, Any] = {
            # top level and text
            "not canonical (indent 2)": json.dumps(good, indent=2, sort_keys=True) + "\n",
            "not canonical (no final newline)": canon(good).rstrip("\n"),
            "not canonical (keys unsorted)": json.dumps({"format": 1, "components": good["components"]}, indent=1) + "\n",
            "a third top key": top(lambda d: d.update(generated="x")),
            "format 2": top(lambda d: d.update(format=2)),
            "components a list": top(lambda d: d.update(components=[])),
            # key grammar
            "deb src upper case": rekey(deb, "deb:Bash@5.2.15-2"),
            "deb src one char": rekey(deb, "deb:b@5.2.15-2"),
            "deb version not starting with a digit": rekey(deb, "deb:bash@v5.2.15-2"),
            "deb key with .pgdg": rekey(deb, "deb:bash@5.2.15-2.pgdg12+1"),
            "pgdg key without .pgdg": rekey(deb, "pgdg:bash@5.2.15-2"),
            "apk without -r<n>": rekey(apk, "apk:readline@8.2.13"),
            "neo4j with a v": rekey(neo, "neo4j:neo4j@v5.26.32"),
            "neo4j another name": rekey(neo, "neo4j:neo@5.26.32"),
            "temurin without jdk-": rekey(tem, "temurin:21.0.12.1+1"),
            "temurin without +build": rekey(tem, "temurin:jdk-21.0.12.1"),
            "pypi not PEP 503": rekey(pyp, "pypi:Psycopg@3.3.6"),
            "pypi underscore": rekey(pyp, "pypi:psycopg_c@3.3.6"),
            "maven without a group": rekey(mav, "maven:jaxb-api@2.2.12"),
            "an unknown kind": rekey(pyp, "npm:psycopg@3.3.6"),
            # entry fields
            "kind is not the key prefix": mut(deb, lambda e: e.update(kind="apk")),
            "arches empty": mut(deb, lambda e: e.update(arches=[])),
            "arches unsorted": mut(deb, lambda e: e.update(arches=["arm64", "amd64"])),
            "arches duplicated": mut(deb, lambda e: e.update(arches=["amd64", "amd64"])),
            "arches unknown": mut(deb, lambda e: e.update(arches=["amd64", "x86"])),
            "origin unknown": mut(deb, lambda e: e.update(origin="handmade")),
            "deb manual": mut(deb, lambda e: e.update(origin="manual")),
            "neo4j generated": mut(neo, lambda e: e.update(origin="generated")),
            "neo4j from not the second fetch": f0(neo, lambda f: f["upstream"].update({"from": "trust on first use"})),
            "neo4j from with a reviewer other than security": f0(neo, lambda f: f["upstream"].update(
                {"from": FROM_NEO4J.replace("security", "developer")})),
            "neo4j from dated after today (UTC)": f0(neo, lambda f: f["upstream"].update(
                {"from": FROM_NEO4J.replace("2026-10-25", "2999-01-01")})),
            "neo4j from with an impossible date": f0(neo, lambda f: f["upstream"].update(
                {"from": FROM_NEO4J.replace("2026-10-25", "2026-13-01")})),
            "files empty": mut(pyp, lambda e: e.update(files=[])),
            "a file with an extra key": f0(pyp, lambda f: f.update(note="x")),
            "a file without size": f0(pyp, lambda f: f.pop("size")),
            # names
            "a name with /": f0(pyp, lambda f: f.update(name="a/psycopg-3.3.6.tar.gz")),
            "a name ..": f0(pyp, lambda f: f.update(name="..")),
            "a name with a leading dot": f0(pyp, lambda f: f.update(name=".psycopg.tar.gz")),
            "a name of 256 characters": f0(pyp, lambda f: f.update(name="p" * 256)),
            "a name duplicated in the entry": mut(deb, lambda e: e["files"][1].update(name=e["files"][0]["name"])),
            # urls
            "http": f0(pyp, lambda f: f.update(url=f["url"].replace("https://", "http://"))),
            "userinfo": f0(pyp, lambda f: f.update(url=f["url"].replace("https://", "https://u:p@"))),
            "a port": f0(pyp, lambda f: f.update(url=f["url"].replace(".org/", ".org:443/", 1))),
            "a query": f0(pyp, lambda f: f.update(url=f["url"] + "?x=1")),
            "a fragment": f0(pyp, lambda f: f.update(url=f["url"] + "#sha256=x")),
            "host deb.debian.org": f0(deb, lambda f: f.update(url=f["url"].replace("snapshot.debian.org", "deb.debian.org"))),
            "host evil.github.com": f0(neo, lambda f: f.update(url=f["url"].replace("github.com", "evil.github.com"))),
            "a pypi file on pypi.org (metadata only, O2)": f0(pyp, lambda f: f.update(
                url=f["url"].replace("files.pythonhosted.org", "pypi.org"))),
            "host Snapshot.debian.org": f0(deb, lambda f: f.update(
                url=f["url"].replace("snapshot.debian.org", "Snapshot.debian.org"))),
            # hashes and sizes
            "sha256 63 hex": f0(pyp, lambda f: f.update(sha256=f["sha256"][:63])),
            "sha256 65 hex": f0(pyp, lambda f: f.update(sha256=f["sha256"] + "0")),
            "sha256 upper case": f0(pyp, lambda f: f.update(sha256=f["sha256"].upper())),
            "size 0": f0(pyp, lambda f: f.update(size=0)),
            "size -1": f0(pyp, lambda f: f.update(size=-1)),
            "size true": f0(pyp, lambda f: f.update(size=True)),
            'size "1"': f0(pyp, lambda f: f.update(size="1")),
            "upstream with an extra key": f0(pyp, lambda f: f["upstream"].update(note="x")),
            "upstream alg md5": f0(mav, lambda f: f["upstream"].update(alg="md5", value=_h("md5", "x"))),
            "upstream sha1 value 64 hex": f0(mav, lambda f: f["upstream"].update(value=_h("sha256", "x"))),
            "upstream value upper case": f0(mav, lambda f: f["upstream"].update(value=f["upstream"]["value"].upper())),
            "upstream sha256 value differs from the file's": f0(pyp, lambda f: f["upstream"].update(
                value=_h("sha256", "other"))),
            "upstream from blank": f0(pyp, lambda f: f["upstream"].update({"from": "  "})),
            # per kind: deb
            "deb with two .dsc": mut(deb, lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0]),
                                                                       name="bash_5.2.15-2+x.dsc"))),
            "deb with no .dsc": mut(deb, lambda e: e["files"].pop(0)),
            "deb .dsc named for another version": f0(deb, lambda f: f.update(name="bash_5.2.15-3.dsc")),
            "deb .dsc keeping the epoch": f0("deb:attr@1:2.5.1-4", lambda f: f.update(name="attr_1-2.5.1-4.dsc")),
            "deb .dsc upstream sha256": f0(deb, lambda f: f.update(upstream={"alg": "sha256", "value": f["sha256"],
                                                                             "from": "x"})),
            "deb .dsc url not /file/<its sha1>": f0(deb, lambda f: f.update(
                url=f"https://snapshot.debian.org/file/{_h('sha1', 'other')}")),
            "deb other file sha1": f0(deb, lambda f: f.update(upstream={"alg": "sha1", "value": _h("sha1", "o"),
                                                                        "from": f["upstream"]["from"]}), 1),
            "deb other file from another .dsc": f0(deb, lambda f: f["upstream"].update(
                {"from": "other_1.dsc Checksums-Sha256"}), 1),
            "deb other file url under /archive": f0(deb, lambda f: f.update(
                url="https://snapshot.debian.org/archive/debian/20250101T000000Z/pool/main/b/bash/bash_5.2.15.orig.tar.xz"), 1),
            # per kind: apk
            "apk without commit": mut(apk, lambda e: e.pop("commit")),
            "apk commit not 40 hex": mut(apk, lambda e: e.update(commit="abc123")),
            "apk without branch": mut(apk, lambda e: e.pop("branch")),
            "apk branch without v": mut(apk, lambda e: e.update(branch="3.23")),
            "apk without repo": mut(apk, lambda e: e.pop("repo")),
            "apk without APKBUILD": mut(apk, lambda e: e["files"].pop(0)),
            "apk APKBUILD sha512": f0(apk, lambda f: f.update(upstream={"alg": "sha512", "value": _h("sha512", "a"),
                                                                        "from": f["upstream"]["from"]})),
            "apk other file sha256": f0(apk, lambda f: f.update(upstream={"alg": "sha256", "value": f["sha256"],
                                                                          "from": f["upstream"]["from"]}), 1),
            # per kind: maven, temurin, pypi
            "maven two files": mut(mav, lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0]),
                                                                       name="jaxb-api-2.2.12.pom"))),
            "maven not a -sources.jar": f0(mav, lambda f: f.update(name="jaxb-api-2.2.12.jar")),
            "maven upstream sha256": f0(mav, lambda f: f.update(upstream={"alg": "sha256", "value": f["sha256"],
                                                                          "from": "x.sha1"})),
            "temurin two files": mut(tem, lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0]),
                                                                         name="second.tar.gz"))),
            "temurin upstream sha1": f0(tem, lambda f: f.update(upstream={"alg": "sha1", "value": _h("sha1", "t"),
                                                                          "from": "x.sha256.txt"})),
            "pypi upstream sha512": f0(pyp, lambda f: f.update(upstream={"alg": "sha512", "value": _h("sha512", "p"),
                                                                         "from": "uv.lock"})),
        }
        self.assertEqual(set(bad), set(BAD_SHAPE_SUBSTRINGS), "every bad-shape row has its targeted substring")
        for case, lock in bad.items():
            with self.subTest(case=case):
                problems = lock_problems_of(lock)
                want = BAD_SHAPE_SUBSTRINGS[case]  # rework round 1, item 8 (review N7)
                self.assertTrue([p for p in problems if want in p],
                                f"the lock check accepts {case} (no problem contains {want!r}): {problems}")
        with self.subTest(case="the canonical-form message"):
            self.assertIn("lock: not in canonical form: regenerate",
                          lock_problems_of(json.dumps(good, indent=2, sort_keys=True) + "\n"))


class LockCoverageTest(unittest.TestCase):
    """Item 6 (d): coverage both ways for the arch, with the exact messages."""

    def test_a_missing_key_names_every_package(self):
        key = "deb:gcc-12@12.2.0-14+deb12u1"
        needs, _ = fn("lock_needs")(policy(), fixture_docs())
        want = {miss(p["image"], p["purl"], key) for p in needs[key]["packages"]}
        self.assertEqual(len(want), 6, "gcc-12 has 6 packages (ke-app, postgres)")
        problems = pgdg_free(lock_problems_of(good_lock(FIXTURE_KEYS - {key}), docs=fixture_docs()))
        self.assertEqual(set(problems), want)
        self.assertEqual(len(problems), len(want))

    def test_small_lock_missing_key_exact_message(self):
        problems = lock_problems_of(good_lock(SMALL_KEYS - {"deb:bash@5.2.15-2"}))
        self.assertEqual(problems, [miss("postgres", ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"),
                                         "deb:bash@5.2.15-2")])

    def test_a_stale_key_is_reported(self):
        d = good_lock(SMALL_KEYS)
        d["components"]["deb:zlib@1:1.2.13.dfsg-1"] = good_entry("deb:zlib@1:1.2.13.dfsg-1")
        self.assertEqual(lock_problems_of(d), [stale("deb:zlib@1:1.2.13.dfsg-1")])
        with self.subTest(case="a manual neo4j entry no image needs is stale too"):
            d = good_lock(SMALL_KEYS)
            d["components"]["neo4j:neo4j@5.26.31"] = good_entry("neo4j:neo4j@5.26.31")
            self.assertEqual(lock_problems_of(d), [stale("neo4j:neo4j@5.26.31")])

    def test_arches(self):
        d = good_lock(SMALL_KEYS)
        d["components"]["deb:bash@5.2.15-2"]["arches"] = ["arm64"]
        self.assertEqual(lock_problems_of(d), [miss("postgres", ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"),
                                                    "deb:bash@5.2.15-2")],
                         "an arm64-only entry does not cover amd64, and is not stale for amd64")
        with self.subTest(case="both arches cover amd64"):
            d["components"]["deb:bash@5.2.15-2"]["arches"] = ["amd64", "arm64"]
            self.assertEqual(lock_problems_of(d), [])
        with self.subTest(case="an extra arm64-only entry is not stale for amd64"):
            d = good_lock(SMALL_KEYS)
            d["components"]["deb:zlib@1:1.2.13.dfsg-1"] = dict(good_entry("deb:zlib@1:1.2.13.dfsg-1"), arches=["arm64"])
            self.assertEqual(lock_problems_of(d), [])
        with self.subTest(case="checked for arm64, the amd64 lock covers nothing"):
            problems = lock_problems_of(good_lock(SMALL_KEYS), arch="arm64")
            self.assertEqual(len(problems), 8, problems)  # 8 packages, 8 keys (pgdg out, psycopg-c in)
            self.assertTrue(all("for arm64: run scripts/sources_lock.sh --arch arm64" in p for p in problems))


class SampleKeysTest(unittest.TestCase):
    """Item 6 (e): per kind, the smallest total size, ties by key, this arch."""

    def test_sample_keys(self):
        lock = {"format": 1, "components": {
            "deb:aaa@1.0-1": good_entry("deb:aaa@1.0-1", size=500),          # 1000 total
            "deb:bbb@1.0-1": good_entry("deb:bbb@1.0-1", size=500),          # 1000 total, ties: aaa wins
            "deb:ccc@1.0-1": good_entry("deb:ccc@1.0-1", size=100),          # smallest, arm64 only
            "deb:ddd@1.0-1": good_entry("deb:ddd@1.0-1", size=9000),
            "apk:big@1.0-r0": good_entry("apk:big@1.0-r0", size=900),
            "apk:small@1.0-r0": good_entry("apk:small@1.0-r0", size=10),
            "neo4j:neo4j@5.26.32": good_entry("neo4j:neo4j@5.26.32", size=10 ** 8),
            "temurin:jdk-21.0.12.1+1": good_entry("temurin:jdk-21.0.12.1+1", size=10 ** 8),
            "pypi:zz@1.0": good_entry("pypi:zz@1.0", size=5),
            "pypi:aa@1.0": good_entry("pypi:aa@1.0", size=50),
        }}
        lock["components"]["deb:ccc@1.0-1"]["arches"] = ["arm64"]
        got = fn("sample_keys")(lock, "amd64")
        self.assertEqual(sorted(got), ["apk:small@1.0-r0", "deb:aaa@1.0-1", "neo4j:neo4j@5.26.32", "pypi:zz@1.0",
                                       "temurin:jdk-21.0.12.1+1"])
        self.assertEqual(len(got), len(set(got)), "one key per kind")
        self.assertEqual(sorted(fn("sample_keys")(lock, "arm64")), ["deb:ccc@1.0-1"])
        self.assertEqual(sorted(fn("sample_keys")(good_lock(SMALL_KEYS), "amd64")),
                         sorted({"deb:attr@1:2.5.1-4", "apk:readline@8.2.13-r1",
                                 "neo4j:neo4j@5.26.32", "temurin:jdk-21.0.12.1+1",
                                 "maven:javax.xml.bind:jaxb-api@2.2.12", "pypi:psycopg-c@3.3.6"}),
                         "ties broken by key: deb:attr before deb:bash")


class LockCheckCliTest(unittest.TestCase):
    """Item 6 (f): `sbom_check.py lock-check` as the lock tool runs it (python -I)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _run(self, lock: Any, *, docs: dict[str, Any] | None = None, arch: str = ARCH,
             sbom_args: list[str] | None = None, overwrite: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        (self.tmp / "lock.json").write_text(lock if isinstance(lock, str) else canon(lock), encoding="utf-8",
                                            newline="")
        ss.write_json(self.tmp / "policy.json", policy())
        args = []
        for image, doc in (docs if docs is not None else small_docs()).items():
            ss.write_json(self.tmp / f"{image}.spdx.json", doc)
            args += ["--sbom", f"{image}={self.tmp / f'{image}.spdx.json'}"]
        for rel, text in (overwrite or {}).items():  # rework round 1: hostile inputs beside a good lock
            (self.tmp / rel).write_text(text, encoding="utf-8", newline="")
        return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-check",
                               "--lock", str(self.tmp / "lock.json"), "--policy", str(self.tmp / "policy.json"),
                               "--arch", arch] + (sbom_args if sbom_args is not None else args),
                              capture_output=True, text=True, timeout=120)

    def test_lock_check_cli(self):
        ok = self._run(good_lock(SMALL_KEYS))
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(ok.stdout.strip(), f"lock-check: ok ({len(SMALL_KEYS)} components, amd64)")
        with self.subTest(case="problems: the first 20 on stderr, exit 1"):
            bad = self._run({"format": 1, "components": {}}, docs=fixture_docs())
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            lines = [ln for ln in bad.stderr.splitlines() if "needs source; the lock has no" in ln]
            self.assertEqual(len(lines), 20, bad.stderr)
            self.assertNotIn("lock-check: ok", bad.stdout)
        with self.subTest(case="a bad arch exits 2"):
            self.assertEqual(self._run(good_lock(SMALL_KEYS), arch="x86_64").returncode, 2)
        with self.subTest(case="an --sbom without IMAGE= exits 2"):
            self.assertEqual(self._run(good_lock(SMALL_KEYS), sbom_args=["--sbom", str(self.tmp / "x.json")]).returncode,
                             2)



# --------------------------------------------------------------------------
# U7a rework round 1 (review B1, B2, N1-N7; security L-1..L-4, I-1, I-2,
# I-4; orchestrator rulings 1-9; design-notes N5 amendment U7, "Rework round
# 1", l.1163 on). Every rule fails closed: a named problem, never a pass,
# never an exception. Tester, U7a rework r1 RED, 2026-10-25.
# --------------------------------------------------------------------------

R1_DEB, R1_APK, R1_NEO, R1_TEM = "deb:bash@5.2.15-2", "apk:readline@8.2.13-r1", "neo4j:neo4j@5.26.32", "temurin:jdk-21.0.12.1+1"
R1_PYP, R1_PYC, R1_MAV = "pypi:psycopg@3.3.6", "pypi:psycopg-c@3.3.6", "maven:javax.xml.bind:jaxb-api@2.2.12"
R1_PGDG = "pgdg:postgresql-common@293.pgdg12+1"
OTHER_SHA1 = "0" * 40


def r1_lock(change: Callable[[dict[str, Any]], Any] | None = None, keys: Any = SMALL_KEYS) -> dict[str, Any]:
    d = good_lock(keys)
    if change:
        change(d)
    return d


def r1_entry(key: str, change: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    return r1_lock(lambda d: change(d["components"][key]))


def r1_file(key: str, change: Callable[[dict[str, Any]], Any], i: int = 0) -> dict[str, Any]:
    return r1_entry(key, lambda e: change(e["files"][i]))


def r1_rename(key: str, name: str, i: int = 0) -> dict[str, Any]:
    """The file renamed, with its url's last segment renamed too."""
    def change(f: dict[str, Any]) -> None:
        f["url"] = f["url"].rsplit("/", 1)[0] + "/" + name
        f["name"] = name
    return r1_file(key, change, i)


def r1_rekey(old: str, new: str) -> dict[str, Any]:
    return r1_lock(lambda d: d["components"].__setitem__(new, d["components"].pop(old)))


class _R1Rows(unittest.TestCase):
    def rows(self, rows: dict[str, tuple[Any, str]], *, docs: dict[str, Any] | None = None,
             pol: dict[str, Any] | None = None) -> None:
        for case, (lock, want) in rows.items():
            with self.subTest(case=case):
                try:
                    problems = lock_problems_of(lock, docs=docs, pol=pol)
                except Exception as exc:  # noqa: BLE001 - ruling 6: a problem, never an exception
                    self.fail(f"{case}: lock_problems raised {type(exc).__name__}: {exc}")
                self.assertTrue([p for p in problems if want in p],
                                f"{case}: no problem contains {want!r}: {problems}")


class ReworkR1Neo4jBindingTest(_R1Rows):
    """Ruling 1 (review B1): one file, alg sha256, value the file's sha256."""

    def test_neo4j_entry_binds_one_sha256_file(self):
        self.rows({
            "two files": (r1_entry(R1_NEO, lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0])))),
                          "neo4j: not exactly one file"),
            "alg sha1 with a 40-hex value": (r1_file(R1_NEO, lambda f: f["upstream"].update(alg="sha1",
                                                                                          value=_h("sha1", "n"))),
                                             "neo4j: upstream alg is not sha256"),
            "alg sha512 with a 128-hex value": (r1_file(R1_NEO, lambda f: f["upstream"].update(
                alg="sha512", value=_h("sha512", "n"))), "neo4j: upstream alg is not sha256"),
            "sha256 with a different value": (r1_file(R1_NEO, lambda f: f["upstream"].update(value=_h("sha256", "x"))),
                                              "neo4j: upstream value is not the file's sha256"),
        })


class ReworkR1CharsetTest(_R1Rows):
    """Ruling 2 (review B2, security L-1, I-1): printable ASCII 0x21-0x7e in
    every string field (`upstream.from` 0x20-0x7e), checked before urlsplit;
    the url round-trips; the scheme is exactly lower-case https."""

    def test_printable_ascii_before_parsing(self):
        tab_host = lambda f: f.update(url=f["url"].replace("files.pythonhosted.org", "files.py\thonhosted.org"))  # noqa: E731
        self.rows({
            "a tab in the url host": (r1_file(R1_PYP, tab_host), "url is not printable ASCII (0x21-0x7e)"),
            "a space in the url path": (r1_file(R1_PYP, lambda f: f.update(url=f["url"].replace("/packages/", "/pack ages/"))),
                                        "url is not printable ASCII (0x21-0x7e)"),
            "an LF in the url path": (r1_file(R1_PYP, lambda f: f.update(url=f["url"].replace("/packages/", "/pack\nages/"))),
                                      "url is not printable ASCII (0x21-0x7e)"),
            "a CR at the url's end": (r1_file(R1_PYP, lambda f: f.update(url=f["url"] + "\r")),
                                      "url is not printable ASCII (0x21-0x7e)"),
            "a NUL in name": (r1_file(R1_PYP, lambda f: f.update(name="psycopg\x00-3.3.6.tar.gz")),
                              "name is not printable ASCII (0x21-0x7e)"),
            "a non-ASCII name": (r1_file(R1_PYP, lambda f: f.update(name="psycop" + chr(0xe9) + "-3.3.6.tar.gz")),
                                 "name is not printable ASCII (0x21-0x7e)"),
            "a tab in from": (r1_file(R1_PYP, lambda f: f["upstream"].update({"from": "uv\t.lock"})),
                              "upstream.from is not printable ASCII (0x20-0x7e)"),
            "a space in the component key": (r1_rekey(R1_DEB, "deb:bash @5.2.15-2"), "key is not printable ASCII"),
            "a tab in kind": (r1_entry(R1_DEB, lambda e: e.update(kind="deb\t")), "kind is not printable ASCII"),
            "a CR in origin": (r1_entry(R1_DEB, lambda e: e.update(origin="generated\r")),
                               "origin is not printable ASCII"),
            "an LF in an arches item": (r1_entry(R1_DEB, lambda e: e.update(arches=["amd64\n"])),
                                        "arches item is not printable ASCII"),
            "a space in sha256": (r1_file(R1_PYP, lambda f: f.update(sha256=f["sha256"][:63] + " ")),
                                  "sha256 is not printable ASCII"),
            "a space in commit": (r1_entry(R1_APK, lambda e: e.update(commit=e["commit"][:39] + " ")),
                                  "commit is not printable ASCII"),
            "a tab in upstream.value": (r1_file(R1_MAV, lambda f: f["upstream"].update(
                value=f["upstream"]["value"][:39] + "\t")), "upstream.value is not printable ASCII"),
            "a non-ASCII upstream.alg": (r1_file(R1_MAV, lambda f: f["upstream"].update(alg="sha" + chr(0x2081))),
                                         "upstream.alg is not printable ASCII"),
        })

    def test_url_round_trips_and_scheme_is_lower_case_https(self):
        self.rows({
            "an empty query (`?`)": (r1_file(R1_PYP, lambda f: f.update(url=f["url"] + "?")),
                                     "url does not round-trip"),
            "an empty fragment (`#`)": (r1_file(R1_PYP, lambda f: f.update(url=f["url"] + "#")),
                                        "url does not round-trip"),
            "HTTPS upper case": (r1_file(R1_PYP, lambda f: f.update(url=f["url"].replace("https://", "HTTPS://"))),
                                 "url scheme is not https"),
            "Https mixed case": (r1_file(R1_PYP, lambda f: f.update(url=f["url"].replace("https://", "Https://"))),
                                 "url scheme is not https"),
        })
        with self.subTest(case="a space in from is allowed (`<dsc> Checksums-Sha256`)"):
            self.assertEqual(lock_problems_of(r1_lock()), [])


class ReworkR1BindingTest(_R1Rows):
    """Ruling 3 (review N1, security L-2): each kind's url host and path and
    the file name; pgdg has no allowed host until Q71."""

    def test_per_kind_hosts_paths_and_names(self):
        # U7c rework round 1, item 9: the commit is the url's ref= (was its /-/raw/<commit>/ segment).
        other_commit = lambda f: f.update(url=f["url"].replace(  # noqa: E731
            f["url"].rsplit("ref=", 1)[1], OTHER_SHA1))
        self.rows({
            "a maven jar named evil-1.0-sources.jar": (r1_rename(R1_MAV, "evil-1.0-sources.jar"), "not a maven file url"),
            "a maven jar on files.pythonhosted.org": (r1_file(R1_MAV, lambda f: f.update(
                url=f["url"].replace("repo1.maven.org", "files.pythonhosted.org"))), "is not a maven file host"),
            "a pypi sdist of another package": (r1_rename(R1_PYP, "requests-2.0.tar.gz"),
                                                "not a pypi file of psycopg 3.3.6"),
            "a pypi sdist of another version": (r1_rename(R1_PYP, "psycopg-3.3.5.tar.gz"),
                                                "not a pypi file of psycopg 3.3.6"),
            "a temurin asset on repo1.maven.org": (r1_file(R1_TEM, lambda f: f.update(
                url=f["url"].replace("github.com", "repo1.maven.org"))), "is not a temurin file host"),
            "a temurin asset of another feature": (r1_file(R1_TEM, lambda f: f.update(
                url=f["url"].replace("temurin21-binaries", "temurin17-binaries"))), "not a temurin file url"),
            "a temurin asset that is not jdk-sources": (r1_rename(R1_TEM, "OpenJDK21U-jdk_x64_linux_21.0.12.1_1.tar.gz"),
                                                        "not a temurin file url"),
            "a temurin from not <name>.sha256.txt": (r1_file(R1_TEM, lambda f: f["upstream"].update(
                {"from": "release.sha256.txt"})), "temurin upstream from is not"),
            "a neo4j tarball at github.com/attacker": (r1_file(R1_NEO, lambda f: f.update(
                url=f["url"].replace("/neo4j/neo4j/", "/attacker/neo4j/"))), "not a neo4j file url"),
            "a neo4j tarball of another tag": (r1_file(R1_NEO, lambda f: f.update(
                url=f["url"].replace("5.26.32.tar.gz", "5.26.31.tar.gz"), name="5.26.31.tar.gz")),
                "not a neo4j file url"),
            "a neo4j name that is not <ver>.tar.gz": (r1_rename(R1_NEO, "neo4j-5.26.32.tar.gz"), "not a neo4j file url"),
            # rework round 2, item 1: one "plain path" problem now (was "url path has a .. segment")
            "../.. in a path": (r1_file(R1_PYP, lambda f: f.update(url=f["url"].replace("/packages/", "/packages/../../"))),
                                "url path is not a plain path"),
            "an apk file on GitLab at another commit": (r1_file(R1_APK, other_commit), "not a apk file url"),
            "an apk file on distfiles for another branch": (r1_file(R1_APK, lambda f: f.update(
                url=f["url"].replace("/v3.23/", "/v3.22/")), 1), "not a apk file url"),
            "the APKBUILD from distfiles": (r1_file(R1_APK, lambda f: f.update(
                url="https://distfiles.alpinelinux.org/distfiles/v3.23/APKBUILD")), "the APKBUILD comes from gitlab"),
            "a url whose last segment is not name": (r1_file(R1_PYP, lambda f: f.update(
                url=f["url"].rsplit("/", 1)[0] + "/other-3.3.6.tar.gz")), "url path does not end in /psycopg-3.3.6.tar.gz"),
            "a neo4j tarball on files.pythonhosted.org": (r1_file(R1_NEO, lambda f: f.update(
                url=f["url"].replace("github.com", "files.pythonhosted.org"))), "is not a neo4j file host"),
            "an apk file on repo1.maven.org": (r1_file(R1_APK, lambda f: f.update(
                url=f["url"].replace("distfiles.alpinelinux.org", "repo1.maven.org")), 1), "is not a apk file host"),
            "a pypi sdist on github.com": (r1_file(R1_PYP, lambda f: f.update(
                url=f["url"].replace("files.pythonhosted.org", "github.com"))), "is not a pypi file host"),
            "a deb file on deb.debian.org": (r1_file(R1_DEB, lambda f: f.update(
                url=f["url"].replace("snapshot.debian.org", "deb.debian.org")), 1), "is not a deb file host"),
            "a name with a leading -": (r1_rename(R1_PYP, "-psycopg-3.3.6.tar.gz"), "not a safe file name"),
            "a name with .. inside": (r1_rename(R1_PYP, "psycopg..3.3.6.tar.gz"), "not a safe file name"),
            "a name with a backslash": (r1_file(R1_PYP, lambda f: f.update(name="psycopg\\3.3.6.tar.gz")),
                                        "not a safe file name"),
        })

    def test_pgdg_files_need_the_tenth_host(self):
        """U7d (A71, P5) supersedes "any pgdg file is a problem until Q71":
        pgdg files are legal with the committed (ten-host) policy and refused
        when a policy copy drops apt-archive.postgresql.org."""
        docs = small_docs()
        docs["postgres"] = ss.spdx_doc("postgres", [
            {"purl": ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"), "declared": "GPL-3.0-or-later"},
            {"purl": ss.deb("libattr1", "1:2.5.1-4", upstream="attr"), "declared": "LGPL-2.1-or-later"},
            {"purl": ss.deb("postgresql-common", "293.pgdg12+1"), "declared": "GPL-2.0-only"}])
        lock = r1_lock(keys=SMALL_KEYS | {R1_PGDG})
        self.assertEqual(lock_problems_of(lock, docs=docs), [], "pgdg files with the committed hosts")
        without = policy()
        without["hosts"] = [h for h in without["hosts"] if h != PGDG_HOST]
        problems = lock_problems_of(lock, docs=docs, pol=without)
        hits = [p for p in problems if "is not in docker/source-policy.json hosts" in p]
        self.assertEqual(len(hits), 2, f"each of the 2 pgdg files is refused without the host: {problems}")

    def test_good_names(self):
        for name in ("psycopg_c-3.3.6.tar.gz", "psycopg-c-3.3.6.tar.gz", "Psycopg_C-3.3.6.tar.gz"):
            with self.subTest(name=name):
                self.assertEqual(lock_problems_of(r1_rename(R1_PYC, name)), [])
        with self.subTest(case="an apk entry with only its APKBUILD (no sources) is legal"):
            self.assertEqual(lock_problems_of(r1_entry(R1_APK, lambda e: e["files"].pop(1))), [])


class ReworkR1CompletenessAndKeysTest(_R1Rows):
    """Rulings 4 (review N2) and 5 (N4): a deb entry needs a file beside its
    `.dsc`; entry, file and upstream key sets are exact."""

    def test_deb_needs_more_than_the_dsc(self):
        self.rows({"a .dsc-only deb": (r1_entry(R1_DEB, lambda e: e["files"].pop(1)), "deb: no file besides the .dsc")})

    def test_exact_key_sets(self):
        self.rows({
            '"skip": true on a deb entry': (r1_entry(R1_DEB, lambda e: e.update(skip=True)), "unexpected key skip"),
            "apk's commit on a deb entry": (r1_entry(R1_DEB, lambda e: e.update(commit=OTHER_SHA1)), "unexpected key commit"),
            "no origin": (r1_entry(R1_DEB, lambda e: e.pop("origin")), "missing key origin"),
            "no files": (r1_entry(R1_DEB, lambda e: e.pop("files")), "missing key files"),
            "no arches": (r1_entry(R1_PYP, lambda e: e.pop("arches")), "missing key arches"),
            "a file without url": (r1_file(R1_PYP, lambda f: f.pop("url")), "a file has no url"),
            "upstream without from": (r1_file(R1_PYP, lambda f: f["upstream"].pop("from")), "upstream has no from"),
        })


class ReworkR1TypesTest(_R1Rows):
    """Ruling 6 (review N5): a field of the wrong JSON type is a problem,
    never an exception."""

    def test_wrong_types_are_problems(self):
        self.rows({
            'arches ["amd64", 1]': (r1_entry(R1_DEB, lambda e: e.update(arches=["amd64", 1])),
                                    "arches is not a list of strings"),
            'arches [["amd64"]]': (r1_entry(R1_DEB, lambda e: e.update(arches=[["amd64"]])),
                                   "arches is not a list of strings"),
            'arches "amd64"': (r1_entry(R1_DEB, lambda e: e.update(arches="amd64")), "arches is not a list of strings"),
            "files {}": (r1_entry(R1_DEB, lambda e: e.update(files={})), "files is not a list"),
            "upstream null": (r1_file(R1_PYP, lambda f: f.update(upstream=None)), "upstream is not an object"),
            "an entry that is a list": (r1_lock(lambda d: d["components"].__setitem__(R1_PYP, [])),
                                        "the entry is not an object"),
            "kind 1": (r1_entry(R1_DEB, lambda e: e.update(kind=1)), "kind is not a string"),
            "origin null": (r1_entry(R1_DEB, lambda e: e.update(origin=None)), "origin is not a string"),
            "name 7": (r1_file(R1_PYP, lambda f: f.update(name=7)), "name is not a string"),
            "url []": (r1_file(R1_PYP, lambda f: f.update(url=[])), "url is not a string"),
            "sha256 null": (r1_file(R1_PYP, lambda f: f.update(sha256=None)), "sha256 is not a string"),
            'a file "x"': (r1_entry(R1_PYP, lambda e: e.update(files=["x"])), "a file is not an object"),
            "commit 1": (r1_entry(R1_APK, lambda e: e.update(commit=1)), "commit is not a string"),
            "upstream.alg null": (r1_file(R1_PYP, lambda f: f["upstream"].update(alg=None)),
                                  "upstream.alg is not a string"),
            "upstream.from 3": (r1_file(R1_PYP, lambda f: f["upstream"].update({"from": 3})),
                                "upstream.from is not a string"),
        })


class ReworkR1CleanAndSizeTest(_R1Rows):
    """Ruling 8 (security L-3): SBOM and lock text through _clean in every
    message; ruling 9 (security I-2): size at most 4 GiB."""

    def test_keys_printed_clean(self):
        evil = "pkg:deb/debian/evil@1?upstream=ev%1b%5b2Jil%401"
        docs = {"postgres": ss.spdx_doc("postgres", [{"purl": evil, "declared": "GPL-2.0-only"}])}
        problems = lock_problems_of({"format": 1, "components": {}}, docs=docs)
        self.assertTrue(problems and all(not re.search(r"[\x00-\x1f\x7f-\x9f]", p) for p in problems),
                        f"a key from the SBOM is printed raw (L-3): {problems!r}")
        self.assertTrue(any("ev\\x1b[2Jil" in p for p in problems), problems)
        lock = r1_lock(lambda d: d["components"].__setitem__("deb:ev\x1b[2Jil@1", good_entry(R1_DEB)))
        problems = lock_problems_of(lock)
        self.assertTrue(problems and all(not re.search(r"[\x00-\x1f\x7f-\x9f]", p) for p in problems),
                        f"a lock key is printed raw (L-3): {problems!r}")

    def test_size_cap(self):
        self.rows({"size 4 GiB + 1": (r1_file(R1_PYP, lambda f: f.update(size=4294967297)),
                                      "is not an int in 1..4294967296")})
        with self.subTest(case="size exactly 4 GiB is allowed"):
            self.assertEqual(lock_problems_of(r1_file(R1_PYP, lambda f: f.update(size=4294967296))), [])


class ReworkR1CliTest(LockCheckCliTest):
    """Ruling 6 (review N5): `lock-check` catches any exception, with one
    message and exit 1, never a traceback."""

    def test_lock_check_never_shows_a_traceback(self):
        for case, text in {"a deeply nested lock (RecursionError)":
                           '{"components": ' + "[" * 200000 + "]" * 200000 + ', "format": 1}\n',
                           "wrong types everywhere": canon({"format": 1, "components": {
                               R1_DEB: {"kind": 1, "arches": "amd64", "origin": None, "files": {}}}})}.items():
            with self.subTest(case=case):
                r = self._run(text)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-500:])
                self.assertNotIn("Traceback", r.stderr)
                if "nested" in case:
                    self.assertEqual(len([ln for ln in r.stderr.splitlines() if ln.strip()]), 1, r.stderr[-500:])
        nested = "[" * 200000 + "]" * 200000
        for case, (target, text) in {"a policy whose hosts is not a list (raises inside the check)":
                                     ("policy.json", '{"hosts": 5, "always": [], "exempt": []}'),
                                     "a deeply nested SBOM (RecursionError while reading)":
                                     ("postgres.spdx.json", nested)}.items():
            with self.subTest(case=case):
                r = self._run(good_lock(SMALL_KEYS), overwrite={target: text})
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-500:])
                self.assertNotIn("Traceback", r.stderr)
                self.assertEqual(len([ln for ln in r.stderr.splitlines() if ln.strip()]), 1, r.stderr[-500:])

    test_lock_check_cli = None  # type: ignore[assignment]  # inherited only for _run; run in LockCheckCliTest



# --------------------------------------------------------------------------
# U7a rework round 2 (review R1-B1, R1-N1, R1-N2; security R1-L1;
# orchestrator round-2 rulings 1-5; design-notes N5 amendment U7, "Rework
# round 2", l.1300 on). Tester, U7a rework r2 RED, 2026-10-25.
# --------------------------------------------------------------------------

R2_TEM_DL = "https://github.com/adoptium/temurin21-binaries/releases/download/"
R2_TEM_ASSET = "OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz"
PLAIN = "url path is not a plain path"
PYPI_URL = "not a pypi file url"


def r2_url(key: str, url: str, name: str | None = None) -> dict[str, Any]:
    def change(f: dict[str, Any]) -> None:
        f["url"] = url
        if name is not None:
            f["name"] = name
    return r1_file(key, change)


def r2_pyc(old: str, new: str) -> dict[str, Any]:
    """psycopg-c's good url with `old` replaced by `new`."""
    url = good_entry(R1_PYC)["files"][0]["url"]
    assert old in url, (old, url)
    return r2_url(R1_PYC, url.replace(old, new, 1))


class ReworkR2PlainPathTest(_R1Rows):
    """Ruling 1 (review R1-B1): every url path is plain: no backslash in the
    url, no empty segment, no `.` or `..` segment, no `%` in the path but the
    literal `%2B` inside temurin's tag segment; the one text "url path is not
    a plain path"."""

    def test_url_paths_are_plain(self):
        self.rows({
            # the reviewer's five inputs
            "temurin %2e%2e segments": (r2_url(R1_TEM, R2_TEM_DL + "%2e%2e/%2e%2e/%2e%2e/%2e%2e/attacker/repo/releases/download/x/"
                                        + R2_TEM_ASSET), PLAIN),
            "temurin %2E%2E segments": (r2_url(R1_TEM, R2_TEM_DL + "%2E%2E/%2E%2E/%2E%2E/%2E%2E/attacker/repo/releases/download/x/"
                                        + R2_TEM_ASSET), PLAIN),
            "temurin ..%2F..": (r2_url(R1_TEM, R2_TEM_DL + "..%2F..%2F..%2F..%2Fattacker/" + R2_TEM_ASSET), PLAIN),
            "temurin backslash segments": (r2_url(R1_TEM, R2_TEM_DL + "x\\..\\..\\..\\..\\attacker\\repo/" + R2_TEM_ASSET),
                                           PLAIN),
            "pypi /%2e%2e/": (r2_url(R1_PYC, "https://files.pythonhosted.org/%2e%2e/psycopg_c-3.3.6.tar.gz",
                                     "psycopg_c-3.3.6.tar.gz"), PLAIN),
            # more spellings (ruling 1; architect item 1)
            "a .%2e segment": (r2_pyc("/packages/", "/packages/.%2e/"), PLAIN),
            "..%5c inside a segment": (r2_pyc("/packages/", "/packages/..%5cb/"), PLAIN),
            "a literal \\..\\": (r2_pyc("/packages/", "/packages\\..\\b/"), PLAIN),
            "a /./ segment": (r2_pyc("/packages/", "/packages/./"), PLAIN),
            "an empty segment (//)": (r2_pyc("/packages/", "/packages//"), PLAIN),
            "a trailing /": (r1_file(R1_PYC, lambda f: f.update(url=f["url"] + "/")), PLAIN),
            "%5c in the path": (r2_pyc("/packages/", "/pack%5cages/"), PLAIN),
            "%2f in the path": (r2_pyc("/packages/", "/pack%2fages/"), PLAIN),
            "%2B outside temurin's tag segment": (r2_pyc("/packages/", "/pack%2Bages/"), PLAIN),
            "%2b lower case in temurin's tag": (r2_url(R1_TEM, R2_TEM_DL + "jdk-21.0.12.1%2b1/" + R2_TEM_ASSET), PLAIN),
            "%2B in temurin's asset segment": (r2_url(R1_TEM, R2_TEM_DL + "jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1%2B1.tar.gz",
                                                      "OpenJDK21U-jdk-sources_21.0.12.1%2B1.tar.gz"), PLAIN),
            "a %65 in a deb path": (r1_file(R1_DEB, lambda f: f.update(url=f["url"].replace("/file/", "/fil%65/")), 1), PLAIN),
            "a backslash in an apk url": (r1_file(R1_APK, lambda f: f.update(url=f["url"].replace("/v3.23/", "/v3.23\\x/")), 1),
                                          PLAIN),
        })
        with self.subTest(case="the temurin tag's literal %2B is allowed (good lock)"):
            self.assertEqual(lock_problems_of(r1_lock()), [])


class ReworkR2TemurinBindingTest(_R1Rows):
    """Ruling 2 (review R1-N1, security R1-L2): the temurin path is exactly
    /adoptium/temurin<N>-binaries/releases/download/jdk-<ver, + as %2B>/<asset>,
    and the asset exactly OpenJDK<N>U-jdk-sources_<ver, + as _>.tar.gz, from the
    key `temurin:jdk-<ver>`; `from` is `<asset>.sha256.txt`."""

    def test_temurin_bound_to_the_key(self):
        def asset(name: str) -> Callable[[dict[str, Any]], None]:
            def change(f: dict[str, Any]) -> None:
                f["url"] = R2_TEM_DL + "jdk-21.0.12.1%2B1/" + name
                f["name"] = name
                f["upstream"]["from"] = f"{name}.sha256.txt"
            return change
        self.rows({
            "another feature's tag segment": (r2_url(R1_TEM, R2_TEM_DL + "jdk-17.0.1%2B1/" + R2_TEM_ASSET),
                                              "not a temurin file url"),
            "an OpenJDK17U asset under temurin21": (r1_file(R1_TEM, asset("OpenJDK17U-jdk-sources_17.0.1_1.tar.gz")),
                                                    "not a temurin file url"),
            "an asset of another build": (r1_file(R1_TEM, asset("OpenJDK21U-jdk-sources_21.0.12.2_1.tar.gz")),
                                          "not a temurin file url"),
            "a JRE asset": (r1_file(R1_TEM, asset("OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz")),
                            "not a temurin file url"),
            "a JDK binary asset": (r1_file(R1_TEM, asset("OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz")),
                                   "not a temurin file url"),
            "an extra subdirectory": (r2_url(R1_TEM, R2_TEM_DL + "jdk-21.0.12.1%2B1/extra/" + R2_TEM_ASSET),
                                      "not a temurin file url"),
            "a tag with a raw +": (r2_url(R1_TEM, R2_TEM_DL + "jdk-21.0.12.1+1/" + R2_TEM_ASSET), "not a temurin file url"),
            "a tag without jdk-": (r2_url(R1_TEM, R2_TEM_DL + "21.0.12.1%2B1/" + R2_TEM_ASSET), "not a temurin file url"),
            "another temurin<N>-binaries repo": (r2_url(R1_TEM, R2_TEM_DL.replace("temurin21-", "temurin17-")
                                                        + "jdk-21.0.12.1%2B1/" + R2_TEM_ASSET), "not a temurin file url"),
            "from naming another asset": (r1_file(R1_TEM, lambda f: f["upstream"].update(
                {"from": "OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz.sha256.txt"})),
                "temurin upstream from is not"),
        })


class ReworkR2PypiPathTest(_R1Rows):
    """Ruling 5: a pypi file's url path is exactly
    /packages/<2 hex>/<2 hex>/<60 hex>/<name>, lower-case hex."""

    def test_pypi_path_layout(self):
        url = good_entry(R1_PYC)["files"][0]["url"]
        head, h1, h2, h3, name = url.rsplit("/", 4)
        self.rows({
            "under /simple/": (r2_url(R1_PYC, f"https://files.pythonhosted.org/simple/{h1}/{h2}/{h3}/{name}"), PYPI_URL),
            "a 59-hex third segment": (r2_url(R1_PYC, f"{head}/{h1}/{h2}/{h3[:59]}/{name}"), PYPI_URL),
            "a 61-hex third segment": (r2_url(R1_PYC, f"{head}/{h1}/{h2}/{h3}0/{name}"), PYPI_URL),
            "upper-case hex": (r2_url(R1_PYC, f"{head}/{h1.upper()}/{h2}/{h3}/{name}"), PYPI_URL),
            "an extra segment": (r2_url(R1_PYC, f"{head}/{h1}/{h2}/{h3}/extra/{name}"), PYPI_URL),
            "a missing segment": (r2_url(R1_PYC, f"{head}/{h1}/{h3}/{name}"), PYPI_URL),
            "a 3-hex first segment": (r2_url(R1_PYC, f"{head}/{h1}0/{h2}/{h3}/{name}"), PYPI_URL),
        })
        with self.subTest(case="the uv.lock layout is good (psycopg_c-3.3.6.tar.gz)"):
            self.assertEqual(lock_problems_of(r2_url(R1_PYC, f"{head}/{h1}/{h2}/{h3}/psycopg_c-3.3.6.tar.gz",
                                                     "psycopg_c-3.3.6.tar.gz")), [])


class ReworkR2RedosTest(_R1Rows):
    """Ruling 4 (security R1-L1): an over-long or adversarial name is one name
    problem, and no regex runs on it; a 255-character adversarial name is
    checked in well under 0.1 s."""

    def _timed(self, name: str) -> tuple[list[str], float]:
        import time
        lock = r1_file(R1_PYP, lambda f: f.update(name=name))
        start = time.perf_counter()
        problems = lock_problems_of(lock)
        return problems, time.perf_counter() - start

    def test_adversarial_pypi_names(self):
        base = self._timed("psycopg-3.3.6.tar.gz")[1]  # the same lock, a good name: the cost of the rest
        problems, took = self._timed("a-" * 50000)
        self.assertEqual(len(problems), 1, problems[:3])
        self.assertIn("not a safe file name", problems[0])
        self.assertLess(took - base, 0.1, f"a 100000-character name cost {took - base:.3f} s")
        self.assertLess(took, 1.0)
        name = ("a-" * 123) + "-1.tar.gz"
        self.assertEqual(len(name), 255)
        problems, took = self._timed(name)
        self.assertLess(took - base, 0.1, f"a 255-character adversarial name cost {took - base:.3f} s")


class ReworkR2CliLineTest(LockCheckCliTest):
    """Ruling 3 (review R1-N2; architect item 3): every exception lock-check
    catches is one stderr line, exactly `lock-check: FAIL (<ExceptionClass>:
    <message through _clean>)`, exit 1."""

    test_lock_check_cli = None  # type: ignore[assignment]  # run in LockCheckCliTest

    def _one_line(self, r: subprocess.CompletedProcess, cls: str) -> None:
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-500:])
        lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, r.stderr[-500:])
        self.assertRegex(lines[0], rf"^lock-check: FAIL \({cls}: .+\)$")
        self.assertNotRegex(r.stderr, r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "the message is printed raw")

    def test_exception_line(self):
        nested = "[" * 100000 + "]" * 100000
        cases = {
            "a lock that is not JSON": ("JSONDecodeError", "{not json\n", {}),
            "a 100000-deep nested lock": ("RecursionError", '{"components": ' + nested + ', "format": 1}\n', {}),
            "a policy that is not JSON": ("JSONDecodeError", None, {"policy.json": "{not json"}),
            "a policy whose hosts is not a list": ("TypeError", None,
                                                   {"policy.json": '{"hosts": 5, "always": [], "exempt": []}'}),
            "a deeply nested SBOM": ("RecursionError", None, {"postgres.spdx.json": nested}),
        }
        for case, (cls, lock, overwrite) in cases.items():
            with self.subTest(case=case):
                self._one_line(self._run(lock if lock is not None else good_lock(SMALL_KEYS), overwrite=overwrite), cls)
        self._run(good_lock(SMALL_KEYS))  # writes the policy and SBOMs
        for case, (lock_name, cls) in {"a missing lock file": ("nope.json", "FileNotFoundError"),
                                       # an OS error of some class (Linux: FileNotFoundError; Windows: OSError)
                                       "a missing lock file, its name holding an ESC": ("nope\x1b[2J.json", "[A-Za-z]*Error")
                                       }.items():
            with self.subTest(case=case):
                r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-check",
                                    "--lock", str(self.tmp / lock_name), "--policy", str(self.tmp / "policy.json"),
                                    "--arch", ARCH, "--sbom", f"valkey={self.tmp / 'valkey.spdx.json'}"],
                                   capture_output=True, text=True, timeout=120)
                self._one_line(r, cls)


# --------------------------------------------------------------------------
# U7b rework round 1, item 2 (review B2, security M-1; design-notes "U7b
# rework round 1"): `lock-check --pending-neo4j` decides "only neo4j keys
# missing" in Python, on the full problem list. Exit 3 exactly when the list
# is non-empty and every problem is a coverage miss for a `neo4j:` key; else
# 1 on problems, 0 on none. Without the flag, U7a's exits are unchanged.
# --------------------------------------------------------------------------

U7B_NEO = "neo4j:neo4j@5.26.32"


class ReworkR1PendingNeo4jCliTest(LockCheckCliTest):

    def _pending(self, lock: Any, *, docs: dict[str, Any] | None = None, flag: bool = True
                 ) -> subprocess.CompletedProcess:
        ss.write_json(self.tmp / "policy.json", policy())
        (self.tmp / "lock.json").write_text(lock if isinstance(lock, str) else canon(lock), encoding="utf-8",
                                            newline="")
        args = []
        for image, doc in (docs if docs is not None else small_docs()).items():
            ss.write_json(self.tmp / f"{image}.spdx.json", doc)
            args += ["--sbom", f"{image}={self.tmp / f'{image}.spdx.json'}"]
        return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "sbom_check.py"), "lock-check",
                               "--lock", str(self.tmp / "lock.json"), "--policy", str(self.tmp / "policy.json"),
                               "--arch", ARCH, *args] + (["--pending-neo4j"] if flag else []),
                              capture_output=True, text=True, timeout=120)

    def test_only_neo4j_misses_exit_3(self):
        lock = good_lock(SMALL_KEYS - {U7B_NEO})
        self.assertEqual(lock_problems_of(lock), [miss("ke-neo4j", "pkg:maven/org.neo4j/neo4j@5.26.32", U7B_NEO)],
                         "fixture: the only problem is the neo4j miss")
        r = self._pending(lock)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(self._pending(lock, flag=False).returncode, 1, "without the flag U7a's exit 1 is unchanged")

    def test_a_clean_lock_exits_0_with_the_flag(self):
        r = self._pending(good_lock(SMALL_KEYS))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), f"lock-check: ok ({len(SMALL_KEYS)} components, amd64)")

    def test_the_reviewers_79_problem_lock_exits_1(self):
        """u7b/review.md B2: the fixture lock without neo4j, pandas and the
        three pgdg keys has 79 problems; the first 20 printed are all neo4j
        misses and 6 later ones are not. The decision must see all 79."""
        drop = {U7B_NEO, "pypi:pandas@2.3.3"} | {k for k in FIXTURE_KEYS if k.startswith("pgdg:")}
        lock = good_lock(FIXTURE_KEYS - drop)
        problems = lock_problems_of(lock, docs=fixture_docs())
        neo = [x for x in problems if f"the lock has no {U7B_NEO} for" in x]
        self.assertEqual((len(problems), len(problems) - len(neo)), (79, 6), "fixture: the reviewer's B2 row")
        self.assertTrue(all(x in neo for x in problems[:20]), "fixture: the first 20 problems are neo4j misses")
        r = self._pending(lock, docs=fixture_docs())
        self.assertEqual(r.returncode, 1, "6 of 79 problems are not neo4j misses: not pending (B2, M-1)")
        printed = [ln for ln in r.stderr.splitlines() if ln.startswith("sbom_check: lock-check: ")]
        self.assertEqual(len(printed), 20, "the print cut is unchanged (output only)")

    def test_other_problems_with_a_neo4j_miss_exit_1(self):
        rows = {
            "a neo4j miss and a stale entry": (good_lock((SMALL_KEYS - {U7B_NEO}) | {"deb:zzz@1.0-1"}), None),
            "a neo4j miss and a non-canonical lock": (json.dumps(good_lock(SMALL_KEYS - {U7B_NEO}), indent=2), None),
            "a stale neo4j entry only (not a miss)": (
                good_lock(SMALL_KEYS),
                {k: v for k, v in small_docs().items() if k != "ke-neo4j"} | {"ke-neo4j": ss.spdx_doc("ke-neo4j", [
                    {"purl": "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS", "declared": "NOASSERTION"},
                    {"purl": "pkg:maven/javax.xml.bind/jaxb-api@2.2.12", "declared": JAXB_ID}])}),
            "a bad neo4j entry (a shape problem, not a miss)": (
                {"format": 1, "components": dict(good_lock(SMALL_KEYS)["components"],
                                                 **{U7B_NEO: dict(good_entry(U7B_NEO), files=[])})}, None),
        }
        for case, (lock, docs) in rows.items():
            with self.subTest(case=case):
                self.assertTrue(lock_problems_of(lock, docs=docs), "fixture: the lock has problems")
                r = self._pending(lock, docs=docs)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)


# --------------------------------------------------------------------------
# U7c gap rulings, consequence for U7a's apk lock rules (design-notes "U7c
# gap rulings", architect's flag (i) and (ii); orchestrator, 2026-10-25).
# Rule changes, not loosening: (i) a GitLab raw path may carry plain
# subdirectory segments below <origin>, the last segment still the name;
# (ii) an apk file outside sha512sums may be sha256 iff its url is GitLab raw
# at the entry's commit and its from is exactly `gitlab files API
# content_sha256 at <commit>`; distfiles files stay sha512; the APKBUILD is
# required once, sha256, with that same from.
# --------------------------------------------------------------------------

APK_API = "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/"


def apk_api_url(commit: str, path: str, *, seg: str | None = None, query: str | None = None) -> str:
    """U7c rework round 1, item 9: the GitLab API raw url of an aports file."""
    return APK_API + (quote(path, safe="") if seg is None else seg) + "/raw" + (f"?ref={commit}" if query is None else query)


def u7c_apk_lock(change: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
    """The small good lock whose apk entry also holds an install script
    (sha256 by the files API) and a patch in a subdirectory (sha512)."""
    def add(d: dict[str, Any]) -> None:
        e = d["components"][R1_APK]
        c = e["commit"]
        e["files"].append(_f("readline.post-install", apk_api_url(c, "main/readline/readline.post-install"), "post",
                             "sha256", None, f"gitlab files API content_sha256 at {c}"))
        e["files"].append(_f("sub-fix.patch", apk_api_url(c, "main/readline/patches/sub-fix.patch"), "sub", "sha512",
                             _h("sha512", "sub"), f"APKBUILD sha512sums at {c}"))
        if change:
            change(e)
    return r1_lock(add)


def _apk_file(name: str) -> Callable[[Callable[[dict[str, Any]], Any]], Callable[[dict[str, Any]], Any]]:
    def wrap(change: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
        return lambda e: change(next(f for f in e["files"] if f["name"] == name))
    return wrap


def _reurl(name: str, make: Callable[[str], str]) -> dict[str, Any]:
    """u7c_apk_lock with file `name`'s url replaced by make(<entry commit>)."""
    return u7c_apk_lock(lambda e: next(f for f in e["files"] if f["name"] == name).update(url=make(e["commit"])))


class U7cApkLockRulesTest(_R1Rows):
    """U7c gap rulings (i), (ii), with item 9's url form (round 1): the
    subdirectory rows are now about the decoded path <P>."""

    def test_the_new_shapes_pass(self):
        self.assertEqual([p for p in lock_problems_of(u7c_apk_lock()) if R1_APK in p], [],
                         "an install script (sha256, files API) and a subdirectory patch are legal apk files")

    def test_bad_shapes(self):
        post = _apk_file("readline.post-install")
        self.rows({
            # Item 9 (b) supersedes the plain-segment rule: "-patches" is a legal
            # segment now; "." is not (was "/-patches/" until round 1).
            "a . subdirectory segment": (_reurl("sub-fix.patch", lambda c: apk_api_url(
                c, "main/readline/./sub-fix.patch")), "not a apk file url"),
            "an empty subdirectory segment": (_reurl("sub-fix.patch", lambda c: apk_api_url(
                c, "main/readline/patches//sub-fix.patch")), "not a apk file url"),
            "a subdirectory under another origin": (_reurl("sub-fix.patch", lambda c: apk_api_url(
                c, "main/ncurses/patches/sub-fix.patch")), "not a apk file url"),
            "a path whose last segment is not the name": (_reurl("sub-fix.patch", lambda c: apk_api_url(
                c, "main/readline/patches/other.patch")), "not a apk file url"),
            "a sha256 file with another from": (u7c_apk_lock(post(lambda f: f["upstream"].update(
                **{"from": f"APKBUILD sha512sums at {'0' * 40}"}))), "is not sha512 (APKBUILD sha512sums)"),
            "a sha256 file with the files API from at another commit": (u7c_apk_lock(post(lambda f: f["upstream"].update(
                **{"from": f"gitlab files API content_sha256 at {'0' * 40}"}))), "is not sha512 (APKBUILD sha512sums)"),
            "a sha256 file on distfiles": (u7c_apk_lock(post(lambda f: f.update(
                url="https://distfiles.alpinelinux.org/distfiles/v3.23/readline.post-install"))),
                "is not sha512 (APKBUILD sha512sums)"),
            "the APKBUILD with A3's old from": (u7c_apk_lock(_apk_file("APKBUILD")(lambda f: f["upstream"].update(
                **{"from": "gitlab.alpinelinux.org files API at " + f["url"].rsplit("ref=", 1)[1]}))),
                "APKBUILD upstream from"),
            "two APKBUILDs": (u7c_apk_lock(lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0])))),
                              "not exactly one APKBUILD with sha256"),
        })


class ReworkR1U7cApkbuildPathTest(_R1Rows):
    """U7c rework round 1, item 1 (review B1), in item 9's form: the
    APKBUILD's decoded path is exactly <repo>/<origin>/APKBUILD; subdirectory
    segments hold for every other file only."""

    def test_the_apkbuild_path_is_exact(self):
        self.rows({
            "the reviewer's tests/APKBUILD": (_reurl("APKBUILD", lambda c: apk_api_url(
                c, "main/readline/tests/APKBUILD")), "not a apk file url"),
            "a/b/APKBUILD": (_reurl("APKBUILD", lambda c: apk_api_url(c, "main/readline/a/b/APKBUILD")),
                             "not a apk file url"),
        })
        self.assertEqual([p for p in lock_problems_of(u7c_apk_lock()) if R1_APK in p], [],
                         "a patch in a subdirectory stays good")


class ReworkR1U7cApiUrlTest(_R1Rows):
    """U7c rework round 1, item 9 (the A34 finding): every apk GitLab file is
    at .../repository/files/<P>/raw?ref=<commit>, narrowly; the old /-/raw/
    form is gone; no other kind or form carries a query or %2F."""

    def test_good_forms(self):
        self.assertEqual([p for p in lock_problems_of(u7c_apk_lock()) if R1_APK in p], [])

        def community(e: dict[str, Any]) -> None:
            e["repo"] = "community"
            for f in e["files"]:
                if f["url"].startswith(APK_API):
                    f["url"] = f["url"].replace(quote("main/", safe=""), quote("community/", safe=""), 1)
        self.assertEqual([p for p in lock_problems_of(u7c_apk_lock(community)) if R1_APK in p], [],
                         "a community entry's files")

    def test_bad_forms(self):
        key = f"lock: {R1_APK}"
        apkb = "main/readline/APKBUILD"
        rows: dict[str, tuple[Any, str]] = {
            "the old /-/raw/ form": (_reurl("APKBUILD", lambda c: (
                f"https://gitlab.alpinelinux.org/alpine/aports/-/raw/{c}/main/readline/APKBUILD")), "not a apk file url"),
            "ref another commit": (_reurl("APKBUILD", lambda c: apk_api_url("0" * 40, apkb)), key),
            "ref upper-case": (_reurl("APKBUILD", lambda c: apk_api_url(c.upper(), apkb)), key),
            "ref 39 hex": (_reurl("APKBUILD", lambda c: apk_api_url(c[:39], apkb)), key),
            "ref then another param": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb, query=f"?ref={c}&x=1")),
                                       "url carries a query"),
            "another param then ref": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb, query=f"?x=1&ref={c}")),
                                       "url carries a query"),
            "ref twice": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb, query=f"?ref={c}&ref={c}")),
                          "url carries a query"),
            "an empty ref": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb, query="?ref=")), key),
            "a fragment": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb) + "#f"), "url carries a fragment"),
            "lower-case escapes": (_reurl("APKBUILD", lambda c: apk_api_url(c, "", seg="main%2freadline%2fAPKBUILD")),
                                   key),
            "a needless escape": (_reurl("APKBUILD", lambda c: apk_api_url(c, "", seg="main%2Freadline%2F%41PKBUILD")),
                                  key),
            "double encoding": (_reurl("APKBUILD", lambda c: apk_api_url(c, "", seg="main%252Freadline%252FAPKBUILD")),
                                key),
            "an encoded dot-dot": (_reurl("APKBUILD", lambda c: apk_api_url(c, "", seg="main%2F%2e%2e%2FAPKBUILD")),
                                   key),
            "the path split into real segments": (_reurl("APKBUILD", lambda c: apk_api_url(c, "", seg=apkb)), key),
            "another origin": (_reurl("APKBUILD", lambda c: apk_api_url(c, "main/other/APKBUILD")), key),
            "community for a main entry": (_reurl("APKBUILD", lambda c: apk_api_url(c, "community/readline/APKBUILD")),
                                           key),
            "an empty segment": (_reurl("sub-fix.patch", lambda c: apk_api_url(c, "main/readline//sub-fix.patch")), key),
            "a . segment": (_reurl("sub-fix.patch", lambda c: apk_api_url(c, "main/readline/./sub-fix.patch")), key),
            "an APKBUILD in a subdirectory": (_reurl("APKBUILD", lambda c: apk_api_url(c, "main/readline/sub/APKBUILD")),
                                              key),
            "another name": (_reurl("APKBUILD", lambda c: apk_api_url(c, "main/readline/APKBUILD.orig")), key),
            "no /raw": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb).replace("/raw?", "?")), key),
            "another project": (_reurl("APKBUILD", lambda c: apk_api_url(c, apkb).replace("alpine%2Faports",
                                                                                         "alpine%2Fother")), key),
            "this form on a deb file": (r1_file(R1_DEB, lambda f: f.update(url=apk_api_url("a" * 40, "main/x/x.dsc"))),
                                        "url carries a query"),
            "this form on a temurin file": (r1_file(R1_TEM, lambda f: f.update(url=apk_api_url("a" * 40, "main/x/x"))),
                                            "url carries a query"),
            "this form on a maven file": (r1_file("maven:javax.xml.bind:jaxb-api@2.2.12", lambda f: f.update(
                url=apk_api_url("a" * 40, "main/x/x.jar"))), "url carries a query"),
            "a query on a distfiles url": (_reurl("readline-8.2.13.tar.gz", lambda c: (
                "https://distfiles.alpinelinux.org/distfiles/v3.23/readline-8.2.13.tar.gz?x=1")), "url carries a query"),
            "%2F on a distfiles url": (_reurl("readline-8.2.13.tar.gz", lambda c: (
                "https://distfiles.alpinelinux.org/distfiles/v3.23%2Freadline-8.2.13.tar.gz")), "plain path"),
        }
        self.rows(rows)


# --------------------------------------------------------------------------
# U7d P5 (A71): the pgdg lock rules; U7c review R1-N1 (subdirectory segments
# of an apk GitLab path pass the file-name rule).
# --------------------------------------------------------------------------

def pgdg_docs() -> dict[str, Any]:
    docs = small_docs()
    docs["postgres"] = ss.spdx_doc("postgres", [
        {"purl": ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"), "declared": "GPL-3.0-or-later"},
        {"purl": ss.deb("libattr1", "1:2.5.1-4", upstream="attr"), "declared": "LGPL-2.1-or-later"},
        {"purl": ss.deb("postgresql-common", "293.pgdg12+1"), "declared": "GPL-2.0-only"}])
    return docs


def pgdg_lock(change: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
    return r1_lock((lambda d: change(d["components"][R1_PGDG])) if change else None, keys=SMALL_KEYS | {R1_PGDG})


class U7dPgdgLockRulesTest(_R1Rows):

    def test_the_good_entry(self):
        self.assertEqual(lock_problems_of(pgdg_lock(), docs=pgdg_docs()), [])
        e = good_entry(R1_PGDG)
        self.assertEqual(set(e), {"kind", "arches", "origin", "files", "suite"})

    def test_bad_entries(self):
        key = f"lock: {R1_PGDG}"
        pool = f"https://{PGDG_HOST}/pub/repos/apt/pool/main/p/postgresql-common/"

        def f0(change: Callable[[dict[str, Any]], Any], i: int = 0) -> dict[str, Any]:
            return pgdg_lock(lambda e: change(e["files"][i]))

        def resuite(e: dict[str, Any], suite: str) -> None:
            """Only the suite rule can fail: the .dsc's from follows the suite."""
            e["suite"] = suite
            e["files"][0]["upstream"]["from"] = f"{PGDG_HOST} {suite} Sources"
        rows = {
            "no suite": (pgdg_lock(lambda e: e.pop("suite")), "missing key suite"),
            "a plain bookworm-pgdg suite": (pgdg_lock(lambda e: resuite(e, "bookworm-pgdg")), key),
            "an upper-case suite": (pgdg_lock(lambda e: resuite(e, "Bookworm-pgdg-archive")), key),
            "another entry key": (pgdg_lock(lambda e: e.update(commit="a" * 40)), "unexpected key commit"),
            "two .dsc files": (pgdg_lock(lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0])))), key),
            "the .dsc named for another version": (f0(lambda f: f.update(
                name="postgresql-common_292.pgdg12+1.dsc", url=pool + "postgresql-common_292.pgdg12+1.dsc")), key),
            "no file besides the .dsc": (pgdg_lock(lambda e: e["files"].pop(1)), key),
            "a sha512 file": (f0(lambda f: f["upstream"].update(alg="sha512", value=_h("sha512", "x")), 1), key),
            "the .dsc from another text": (f0(lambda f: f["upstream"].update(**{"from": "apt-archive Sources"})), key),
            "another file from another text": (f0(lambda f: f["upstream"].update(**{"from": "Sources"}), 1), key),
            "a snapshot url": (f0(lambda f: f.update(url="https://snapshot.debian.org/file/" + "a" * 40)),
                               "is not a pgdg file host"),
            "a wrong pool letter": (f0(lambda f: f.update(url=f["url"].replace("/main/p/", "/main/q/"))),
                                    "not a pgdg file url"),
            "another source dir": (f0(lambda f: f.update(url=f["url"].replace("/postgresql-common/", "/postgresql-16/"))),
                                   "not a pgdg file url"),
            "a last segment that is not the name": (f0(lambda f: f.update(url=pool + "other.dsc")), key),
            "a query": (f0(lambda f: f.update(url=f["url"] + "?x=1")), "url carries a query"),
            "a fragment": (f0(lambda f: f.update(url=f["url"] + "#f")), "url carries a fragment"),
            "an escaped +": (f0(lambda f: f.update(url=f["url"].replace("+", "%2B"))), "plain path"),
            "the dists path": (f0(lambda f: f.update(url=f["url"].replace("/pool/main/p/postgresql-common/",
                                                                          "/dists/bookworm-pgdg-archive/"))),
                               "not a pgdg file url"),
        }
        self.rows(rows, docs=pgdg_docs())


class U7dApkSegmentNameTest(_R1Rows):
    """U7c review R1-N1: each decoded <P> middle segment passes the lock
    file-name rule."""

    def test_middle_segments(self):
        self.rows({
            "a segment starting with -": (_reurl("sub-fix.patch", lambda c: apk_api_url(
                c, "main/readline/-patches/sub-fix.patch")), "not a apk file url"),
            "a segment with :": (_reurl("sub-fix.patch", lambda c: apk_api_url(
                c, "main/readline/pa:tches/sub-fix.patch")), "not a apk file url"),
        })
        self.assertEqual([p for p in lock_problems_of(u7c_apk_lock()) if R1_APK in p], [], "patches/ stays good")


class ReworkR1U7dSuiteBindingTest(_R1Rows):
    """U7d rework round 1, item 3 (review N1, security I-2): a pgdg entry's
    `suite` is the one its packages' distro derives."""

    @staticmethod
    def _suited(suite: str) -> dict[str, Any]:
        def change(e: dict[str, Any]) -> None:
            e["suite"] = suite
            e["files"][0]["upstream"]["from"] = f"{PGDG_HOST} {suite} Sources"
        return pgdg_lock(change)

    def test_the_suite_is_bound(self):
        self.assertEqual(lock_problems_of(self._suited("bookworm-pgdg-archive"), docs=pgdg_docs()), [])
        for suite in ("trixie-pgdg-archive", "evil-pgdg-archive"):
            with self.subTest(suite=suite):
                problems = lock_problems_of(self._suited(suite), docs=pgdg_docs())
                self.assertIn(f"lock: {R1_PGDG}: suite {suite} is not bookworm-pgdg-archive "
                              "(from postgres distro debian-12.15)", problems)

    def test_packages_that_derive_two_suites(self):
        docs = pgdg_docs()
        docs["ke-app"] = ss.spdx_doc("ke-app", [
            {"purl": ss.deb("postgresql-client-common", "293.pgdg12+1", upstream="postgresql-common",
                            distro="debian-13.1"), "declared": "GPL-2.0-only"}])
        problems = lock_problems_of(pgdg_lock(), docs=docs)
        self.assertIn(f"{R1_PGDG}: packages derive suites bookworm-pgdg-archive, trixie-pgdg-archive", problems)


class ReworkR1U7dUnderscoreLockTest(_R1Rows):
    """U7d rework round 1, item 10 (u7d/lock-run-2.txt; u7d/aports-probe.txt):
    the lock file-name rule takes a leading `_`, in file names and in the
    decoded <P> middle segments; a leading `-` or `.` and `..` still fail."""

    PATTERN = "[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}"

    @staticmethod
    def _with(*files: tuple[str, str]) -> dict[str, Any]:
        def add(e: dict[str, Any]) -> None:
            c = e["commit"]
            for name, path in files:
                e["files"].append(_f(name, apk_api_url(c, path), "item10 " + path, "sha512",
                                     _h("sha512", "item10 " + path), f"APKBUILD sha512sums at {c}"))
        return u7c_apk_lock(add)

    def test_the_pattern(self):
        self.assertEqual(load_sbom_check().LOCK_FILE_NAME_RE.pattern, self.PATTERN)

    def test_a_leading_underscore_passes(self):
        lock = self._with(("_apk", "main/readline/_apk"), ("_x.patch", "main/readline/_x.patch"),
                          ("__stack_chk_fail_local.c", "main/readline/__stack_chk_fail_local.c"),
                          ("__NR_riscv_hwprobe.patch", "main/readline/__NR_riscv_hwprobe.patch"),
                          ("y.patch", "main/readline/_patches/y.patch"))
        self.assertEqual([p for p in lock_problems_of(lock) if R1_APK in p], [])

    def test_still_refused(self):
        self.rows({
            "a name with a leading -": (self._with(("-x", "main/readline/-x")), "not a safe file name"),
            "a name with a leading .": (self._with((".x", "main/readline/.x")), "not a safe file name"),
            "a name with ..": (self._with(("a..b", "main/readline/a..b")), "not a safe file name"),
            "_ then a /": (self._with(("_/x", "main/readline/_/x")), "not a safe file name"),
            "a middle segment with a leading .": (self._with(("y.patch", "main/readline/.patches/y.patch")),
                                                  "not a apk file url"),
            "a middle segment with a leading -": (self._with(("y.patch", "main/readline/-patches/y.patch")),
                                                  "not a apk file url"),
        })


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
EMPTY_SHA512 = hashlib.sha512(b"").hexdigest()


class ReworkR1U7dEmptyFileLockTest(_R1Rows):
    """U7d rework round 1, item 12: an apk file at the GitLab API raw form may
    have size 0; every other file (distfiles, deb, pgdg, neo4j, temurin,
    pypi, maven) keeps 0 < size."""

    def test_an_empty_gitlab_file_passes(self):
        def empty(e: dict[str, Any]) -> None:
            for f in e["files"]:
                if f["name"] in ("readline.post-install", "sub-fix.patch"):
                    f.update(size=0, sha256=EMPTY_SHA256)
                    f["upstream"]["value"] = EMPTY_SHA256 if f["upstream"]["alg"] == "sha256" else EMPTY_SHA512
        self.assertEqual([p for p in lock_problems_of(u7c_apk_lock(empty)) if R1_APK in p], [],
                         "an empty install script (files API) and an empty patch (sha512sums) are legal")

    def test_an_empty_apkbuild_fails(self):
        """Review R1-N1 (item 13 RED): the APKBUILD keeps size > 0 under item 12;
        an empty APKBUILD has no pkgver, so the resolver can never produce it."""
        def empty(f: dict[str, Any]) -> None:
            f.update(size=0, sha256=EMPTY_SHA256)
            f["upstream"]["value"] = EMPTY_SHA256
        problems = lock_problems_of(u7c_apk_lock(_apk_file("APKBUILD")(empty)))
        self.assertIn(f"lock: {R1_APK}: APKBUILD: size 0", problems)

    def test_still_refused(self):
        def dist(change: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
            return u7c_apk_lock(lambda e: change(next(f for f in e["files"] if "distfiles" in f["url"])))
        post = _apk_file("readline.post-install")
        self.rows({
            "size 0 with another sha256": (u7c_apk_lock(post(lambda f: f.update(size=0))),
                                           "readline.post-install: size 0 but sha256 is not the empty hash"),
            "size 0, the empty sha256, another sha512 upstream": (u7c_apk_lock(_apk_file("sub-fix.patch")(
                lambda f: f.update(size=0, sha256=EMPTY_SHA256))), "sub-fix.patch: size 0 but"),
            "an empty distfiles apk file": (dist(lambda f: f.update(size=0, sha256=EMPTY_SHA256)),
                                            "size 0 is not an int in 1..4294967296"),
            "an empty maven file": (r1_file("maven:javax.xml.bind:jaxb-api@2.2.12", lambda f: f.update(size=0)),
                                    "size 0 is not an int in 1..4294967296"),
            "a GitLab apk file of size false": (u7c_apk_lock(post(lambda f: f.update(size=False))),
                                                "size False is not an int"),
            "an empty deb file": (r1_file(R1_DEB, lambda f: f.update(size=0)), "size 0 is not an int in 1..4294967296"),
            "an empty pypi file": (r1_file(R1_PYP, lambda f: f.update(size=0)), "size 0 is not an int in 1..4294967296"),
            "a GitLab apk file of size -1": (u7c_apk_lock(post(lambda f: f.update(size=-1))), "size -1 is not an int"),
            "a GitLab apk file of size true": (u7c_apk_lock(post(lambda f: f.update(size=True))), "size True is not an int"),
            "a GitLab apk file of 4 GiB + 1": (u7c_apk_lock(post(lambda f: f.update(size=4294967297))),
                                               "size 4294967297 is not an int"),
        })


if __name__ == "__main__":
    unittest.main()
