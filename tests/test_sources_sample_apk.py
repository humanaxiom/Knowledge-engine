"""platform-sbom U9c: the verify/CI sample fetches, for the `apk` kind, only
the sample key's distfiles.alpinelinux.org files (the human's ruling A81,
Q81 option 3; requirements "U9c precision" U9c-1..U9c-4 and U9c-7, with the
orchestrator's O-21 amendments; design-notes "N9 amendment, U9c" items 2-7,
11, 13 and 14). Tester, U9c RED, 2026-10-30.

Interface pinned (design items 2, 3, 5, 6, 7):
- `sbom_check.APK_DISTFILES_HOST == "distfiles.alpinelinux.org"` and
  `KIND_HOSTS["apk"] == (APK_API_HOST, APK_DISTFILES_HOST)` (item 2: the
  host the plan selects is one the lock rules already bind apk files to);
- `fetch_plan(lock, arch, "sample")`: an apk sample key's files whose lock
  URL host is that host, in file order; none left is `ValueError("<key>: the
  apk sample key has no file on distfiles.alpinelinux.org; the sample needs
  one (A81)")`, which the fetch client prints as `bundle_fetch: FAIL (stage
  lock: <that text>; no retry)` with zero requests. `full` is unchanged;
- `sources_fetch._name_check` prints `bundle_fetch: apk <key>: APKBUILD name
  check skipped (sample set, A81)` (stdout, once per apk sample key, after
  that key's files) and runs no APKBUILD check, keyed on set `sample` and
  kind `apk` only; in `full` the APKBUILD is fetched and checked as before;
- `source_index`: status `partial` for a key some but not all of whose
  files are planned, `path` per planned (key, name); `index: <key> is
  partial in a full bundle`; `index: <key> is partial, and only the apk
  sample key may be (A81)`;
- `source_section`: the partial row (item 7, exact text, PARTIAL_CELL) with
  the URL of the component's first file that has no path; `notices: <key> is
  partial in a full index`; `notices: <key> is partial but lists no fetched
  file or no unfetched file`.

Fixtures: tests.test_sources_fetch's synthetic locks (real bytes; the apk
sample key APK_KEY has an APKBUILD, a sha512 patch and a plain file on
gitlab.alpinelinux.org and one tarball on distfiles.alpinelinux.org) and the
committed lock, read only for the plan rows (no fetch). The fake transport
is tests.test_sources_fetch.Net; a refused connection is a route that raises
ConnectionRefusedError. The bundle row adds one apk entry to
tests/test_bundle_sources.py's synthetic lock through `_relock_for` (that
module's own fixture has no apk key and is not edited). No network; no test
reads docs/evidence.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.test_bundle_sources import NOTICES, _section, _SourcesBase
from tests.test_sbom_bundle import load_sbom_check, pinned_syft_version, raw_doc
from tests.test_source_index import (BANNER, GIT_SHA, I3, LOCK_COMPONENT_KEYS, NOT_SAMPLE, PARTIAL_CELL,
                                     SHIPPED_CELL, _CliAsserts, _IndexCase, distinct, record_text, run_check,
                                     syn_policy, write_fetched)
from tests.test_sources_fetch import (APK_DISTFILES, APK_KEY, ARCH, COMMITTED_LOCK, DEB_KEY, PGDG_KEY, LockBuilder,
                                      _FetchCase, blob, dsc_cases, fetch_fail, h, host_of, key_parts, load_fetch,
                                      one_per_kind, plan_of, sample_files, wide)

GITLAB = "gitlab.alpinelinux.org"
COMMITTED_APK_KEY = "apk:alpine-baselayout@3.7.1-r8"
NO_DISTFILES = "the apk sample key has no file on distfiles.alpinelinux.org; the sample needs one (A81)"


def skip_line(key: str) -> str:
    """Design item 5: the one line a sample run prints for its apk key."""
    return f"bundle_fetch: apk {key}: APKBUILD name check skipped (sample set, A81)"


def committed_lock() -> dict[str, Any]:
    return json.loads(COMMITTED_LOCK.read_text(encoding="utf-8"))


def full_mirror(lock: dict[str, Any], arch: str) -> list[tuple[str, dict[str, Any]]]:
    """Every file of every key listed for `arch`, keys sorted, file order (U8)."""
    comps = lock["components"]
    return [(k, f) for k in sorted(comps) if arch in comps[k]["arches"] for f in comps[k]["files"]]


def refused(*a: Any, **k: Any) -> Any:
    """A route that fails as a refused TCP connection (U9c-7's closure)."""
    raise ConnectionRefusedError(111, "Connection refused")


def no_query(url: str) -> str:
    return url.split("?", 1)[0] + "?<query omitted>"


def apk_without_distfiles() -> LockBuilder:
    """An apk sample key whose files are all on GitLab, beside a deb key."""
    b = LockBuilder()
    b.apk(APK_KEY, patches=[("fix-build.patch", blob("readline patch", 90))],
          plain=[("readline.trigger", blob("readline trigger", 40))])
    b.deb(DEB_KEY, [("bash_5.2.15.orig.tar.gz", blob("bash orig", 400)),
                    ("bash_5.2.15-2.debian.tar.xz", blob("bash debian 2", 120))])
    return b


# --------------------------------------------------------------------------
# U9c-1: the plan (design items 2 and 3)
# --------------------------------------------------------------------------

class SamplePlanTest(_FetchCase):

    def setUp(self) -> None:
        super().setUp()
        self.S = load_sbom_check()

    def plan(self, lock: dict[str, Any], which: str, arch: str = ARCH) -> list[tuple[str, dict[str, Any]]]:
        return [tuple(x) for x in self.S.fetch_plan(lock, arch, which)]  # type: ignore[misc]

    def test_sample_plan_apk_is_distfiles_only(self):
        for name, b in (("one_per_kind", one_per_kind()), ("wide", wide())):
            with self.subTest(lock=name):
                lock = b.lock()
                plan = self.plan(lock, "sample")
                apk = [(k, f) for k, f in plan if k.startswith("apk:")]
                files = lock["components"][APK_KEY]["files"]
                self.assertTrue([f for f in files if host_of(f["url"]) == GITLAB], "fixture: GitLab files")
                self.assertEqual(apk, [(APK_KEY, f) for f in files if host_of(f["url"]) == APK_DISTFILES],
                                 "the apk sample row is the key's distfiles files, in file order (U9c-1)")
                self.assertEqual([f["name"] for _, f in apk], ["readline-8.2.13.tar.gz"])
                self.assertEqual([f["url"] for _, f in plan if host_of(f["url"]) == GITLAB], [],
                                 "the sample plan holds no gitlab.alpinelinux.org file (A81)")
        with self.subTest(lock="committed (U9c-5: u8/ and u9/expected.md \"U9c\")"):
            lock = committed_lock()
            plan = self.plan(lock, "sample")
            apk = [(k, f) for k, f in plan if k.startswith("apk:")]
            self.assertEqual({k for k, _ in apk}, {COMMITTED_APK_KEY}, "the apk sample key is unchanged (QA-1)")
            self.assertEqual([f["name"] for _, f in apk], ["protocols-6.4", "services-6.4"])
            self.assertEqual({host_of(f["url"]) for _, f in apk}, {APK_DISTFILES})
            self.assertEqual([f["url"] for _, f in plan if host_of(f["url"]) == GITLAB], [])
            shas = {f["sha256"]: f["size"] for _, f in plan}
            self.assertEqual((len({k for k, _ in plan}), len(plan), len(shas), sum(shas.values())),
                             (7, 10, 10, 136553898), "sample amd64: keys, rows, distinct sha256, distinct bytes")
            self.assertEqual(self.plan(lock, "sample", "arm64"), [])
        with self.subTest(case="the host is the checker's constant, shared with KIND_HOSTS (design item 2)"):
            self.assertEqual(getattr(self.S, "APK_DISTFILES_HOST", None), APK_DISTFILES)
            self.assertEqual(self.S.KIND_HOSTS["apk"], (self.S.APK_API_HOST, APK_DISTFILES))

    def test_sample_plan_other_kinds_unchanged(self):
        for name, lock in (("one_per_kind", one_per_kind().lock()), ("wide", wide().lock()),
                           ("committed", committed_lock())):
            for arch in ("amd64", "arm64"):
                with self.subTest(lock=name, arch=arch):
                    plan = self.plan(lock, "sample", arch)
                    keys = self.S.sample_keys(lock, arch)
                    self.assertEqual(list(dict.fromkeys(k for k, _ in plan)), keys,
                                     "the sample's key list is sample_keys, in order (unchanged, QA-1)")
                    for k in keys:
                        if k.startswith("apk:"):
                            continue
                        self.assertEqual([f for kk, f in plan if kk == k], lock["components"][k]["files"],
                                         f"{k}: every file, in the entry's order, as before U9c")

    def test_full_plan_unchanged(self):
        for name, lock in (("one_per_kind", one_per_kind().lock()), ("wide", wide().lock()),
                           ("committed", committed_lock())):
            for arch in ("amd64", "arm64"):
                with self.subTest(lock=name, arch=arch):
                    self.assertEqual(self.plan(lock, "full", arch), full_mirror(lock, arch))
        with self.subTest(case="committed, amd64 (u8/expected.md \"full, amd64\")"):
            lock = committed_lock()
            plan = self.plan(lock, "full")
            shas = {f["sha256"]: f["size"] for _, f in plan}
            self.assertEqual((len({k for k, _ in plan}), len(plan), len(shas), sum(shas.values())),
                             (183, 876, 716, 1180936586))
            apk_keys = sorted({k for k, _ in plan if k.startswith("apk:")})
            self.assertTrue(apk_keys)
            for k in apk_keys:
                self.assertIn("APKBUILD", [f["name"] for kk, f in plan if kk == k],
                              f"{k}: the full set still fetches the APKBUILD over the GitLab route (A81)")
            self.assertEqual(self.plan(lock, "full", "arm64"), [])

    def test_sample_plan_refuses_an_apk_key_without_distfiles(self):
        b = apk_without_distfiles()
        lock = b.lock()
        self.assertEqual(self.S.lock_entry_problems(b.text(), syn_policy()), [],
                         "fixture: the lock passes its entry rules")
        with self.subTest(case="fetch_plan fails closed, naming the key"):
            with self.assertRaises(ValueError) as cm:
                self.S.fetch_plan(lock, ARCH, "sample")
            self.assertEqual(str(cm.exception), f"{APK_KEY}: {NO_DISTFILES}")
        with self.subTest(case="the fetch client: one stage-lock line, zero requests"):
            run = self.run_fetch(b.text(), b.routes())
            self.assert_failed(run, re.escape(f"bundle_fetch: FAIL (stage lock: {APK_KEY}: {NO_DISTFILES}; no retry)"))
            self.assertEqual(run.net.calls, [], "zero requests")
            self.assertEqual(run.listing(), [])
        with self.subTest(case="control: the full plan of that lock is every file"):
            self.assertEqual(self.plan(lock, "full"), full_mirror(lock, ARCH))
        with self.subTest(case="control: a lock with no apk key has a sample plan"):
            c = one_per_kind()
            del c.components[APK_KEY]
            self.assertEqual(self.plan(c.lock(), "sample"), plan_of(c, ARCH, "sample"))


# --------------------------------------------------------------------------
# U9c-3: the APKBUILD name check (design item 5)
# --------------------------------------------------------------------------

class SampleFetchNameCheckTest(_FetchCase):

    def spies(self) -> tuple[mock.Mock, mock.Mock, list[Any]]:
        apk_spy = mock.Mock(wraps=self.F.R.parse_apkbuild)
        dsc_spy = mock.Mock(wraps=self.F.R.parse_dsc)
        patches = [lambda F: mock.patch.object(F.R, "parse_apkbuild", apk_spy),
                   lambda F: mock.patch.object(F.R, "parse_dsc", dsc_spy)]
        return apk_spy, dsc_spy, patches

    def test_sample_fetch_skips_the_apkbuild_check_only_for_apk(self):
        b = one_per_kind()
        apkbuild = next(f for f in b.components[APK_KEY]["files"] if f["name"] == "APKBUILD")
        with self.subTest(set="sample"):
            apk_spy, dsc_spy, patches = self.spies()
            run = self.run_fetch(b.text(), b.routes(), patches=patches)
            self.assertEqual(run.rc, 0, run.text)
            lines = run.out.splitlines()
            self.assertEqual([ln for ln in lines if "name check" in ln], [skip_line(APK_KEY)],
                             "one line, naming the apk sample key; the skip is never silent (U9c-3)")
            at = lines.index(skip_line(APK_KEY))
            apk_ok = [i for i, ln in enumerate(lines) if ln.startswith(f"bundle_fetch: ok {APK_KEY} ")]
            later = [i for i, ln in enumerate(lines) if ln.startswith("bundle_fetch: ok ") and i not in apk_ok]
            self.assertTrue(apk_ok and max(apk_ok) < at < min(later), "after the key's files, before the next key's")
            self.assertEqual(apk_spy.call_count, 0, "no APKBUILD is read in the sample")
            self.assertEqual(dsc_spy.call_count, 2, "the deb and pgdg .dsc checks still run in the sample")
            self.assertEqual([u for u in run.net.calls if host_of(u) == GITLAB], [], "no GitLab request")
            self.assertNotIn(apkbuild["sha256"], run.listing())
        with self.subTest(set="full"):
            apk_spy, dsc_spy, patches = self.spies()
            run = self.run_fetch(b.text(), b.routes(), which="full", patches=patches)
            self.assertEqual(run.rc, 0, run.text)
            self.assertNotIn("skipped", run.text, "no skip line in a full run")
            self.assertEqual(apk_spy.call_count, 1, "the full run reads and checks the APKBUILD")
            self.assertEqual(dsc_spy.call_count, 2)
            self.assertIn(apkbuild["url"], run.net.calls)

    def test_full_fetch_apkbuild_mismatch_still_fails(self):
        patch_ = ("fix-build.patch", blob("readline patch", 90))
        dist = ("readline-8.2.13.tar.gz", blob("readline tarball", 300))
        with self.subTest(case="the sample key's APKBUILD names differ: the U8-5 line in full"):
            b = one_per_kind()
            a = LockBuilder()
            commit = a.apk(APK_KEY, patches=[patch_], plain=[("readline.trigger", blob("readline trigger", 40))],
                           distfiles=[dist], sums=[(dist[0], h("sha512", dist[1]))])
            b.components[APK_KEY] = a.components[APK_KEY]
            b.bodies.update(a.bodies)
            run = self.run_fetch(b.text(), b.routes(), which="full")
            self.assert_failed(run, fetch_fail(GITLAB, "APKBUILD",
                                               f"APKBUILD at {commit}: sha512sums names differ from the lock entry"))
            self.assertNotIn("skipped", run.text)
            self.assert_no_partial(run)
        with self.subTest(case="no fail-open: a full run whose plan lacks the APKBUILD fails closed, no skip"):
            b = one_per_kind()

            def no_apkbuild(real: Any) -> Any:
                def plan(lock: Any, arch: str, which: str) -> Any:
                    return [(k, f) for k, f in real(lock, arch, which) if f["name"] != "APKBUILD"]
                return plan
            run = self.run_fetch(b.text(), b.routes(), which="full",
                                 patches=[lambda F: mock.patch.object(F.S, "fetch_plan", no_apkbuild(F.S.fetch_plan))])
            self.assertEqual(run.rc, 1, run.text)
            self.assertEqual(len(run.fail_lines), 1, run.text)
            self.assertNotIn("skipped", run.text, "the skip never depends on the APKBUILD being absent (U9c-3)")
            self.assertNotIn("Traceback", run.text)
            self.assert_no_partial(run)

    def test_sample_fetch_dsc_check_still_runs(self):
        for kind, host in (("deb", "snapshot.debian.org"), ("pgdg", "apt-archive.postgresql.org")):
            key = DEB_KEY if kind == "deb" else PGDG_KEY
            src, ver = key_parts(key)
            for case in ("control: equal", "an extra file in the lock entry"):
                with self.subTest(kind=kind, case=case):
                    b = dsc_cases(kind)[case]
                    b.apk(APK_KEY, patches=[("fix-build.patch", blob("readline patch", 90))],
                          distfiles=[("readline-8.2.13.tar.gz", blob("readline tarball", 300))])
                    self.assertIn(APK_KEY, load_sbom_check().sample_keys(b.lock(), ARCH), "fixture: an apk sample key")
                    run = self.run_fetch(b.text(), b.routes())
                    if case.startswith("control"):
                        self.assertEqual(run.rc, 0, run.text)
                        continue
                    self.assert_failed(run, fetch_fail(host, f"{src}_{ver}.dsc",
                                                       "Files/Checksums-Sha256 differ from the lock entry"))
                    self.assert_no_partial(run)


# --------------------------------------------------------------------------
# U9c-7: the outcome, with gitlab.alpinelinux.org refusing connections
# --------------------------------------------------------------------------

class GitLabUnreachableTest(_FetchCase):

    @staticmethod
    def closed(b: LockBuilder) -> dict[str, Any]:
        routes = b.routes()
        for url in routes:
            if host_of(url) == GITLAB:
                routes[url] = refused
        return routes

    def test_sample_fetch_passes_with_gitlab_unreachable(self):
        b = wide()
        self.assertTrue([u for u in b.routes() if host_of(u) == GITLAB], "fixture: GitLab files in the lock")
        run = self.run_fetch(b.text(), self.closed(b))
        self.assertEqual(run.rc, 0, run.text)
        self.assertEqual([u for u in run.net.calls if host_of(u) == GITLAB], [],
                         "no request to gitlab.alpinelinux.org in a sample run (U9c-7)")
        self.assertIn("fetch.json", run.listing())
        record = json.loads((run.outdir / "fetch.json").read_text(encoding="utf-8"))
        self.assertEqual(record["set"], "sample")
        self.assertEqual(record["components"][APK_KEY],
                         [{"name": f["name"], "sha256": f["sha256"], "size": f["size"]}
                          for f in sample_files(APK_KEY, b.components[APK_KEY]["files"])])
        self.assertNotIn("hops=" + GITLAB, run.out)
        self.assertRegex(run.out.splitlines()[-1], r"^bundle_fetch: fetched \d+ files, \d+ bytes, \d+ components "
                                                   rf"\(sample, {ARCH}\) in [0-9.]+ s$")

    def test_full_fetch_fails_with_gitlab_unreachable(self):
        b = one_per_kind()
        first = full_mirror(b.lock(), ARCH)[0][1]
        self.assertEqual((host_of(first["url"]), first["name"]), (GITLAB, "APKBUILD"), "fixture: GitLab first")
        run = self.run_fetch(b.text(), self.closed(b), which="full",
                             patches=[lambda F: mock.patch.object(F.R, "_ACTIVE_RETRIES", [3])])
        self.assert_failed(run, fetch_fail(GITLAB, "APKBUILD", f"ConnectionRefusedError: {no_query(first['url'])}"))
        self.assertEqual(run.net.calls, [first["url"]], "one attempt, no retry, nothing after it (Q61)")
        self.assertEqual(run.sleeps.calls, [])
        self.assert_no_partial(run)


# --------------------------------------------------------------------------
# U9c-2: the record and `sources-check` accept the partial apk entry
# --------------------------------------------------------------------------

class SampleRecordTest(_CliAsserts):

    command = "sources-check"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.b = wide()
        self.lock = self.tmp / "sources.lock.json"
        self.lock.write_bytes(self.b.text().encode("utf-8"))
        self.pol = self.tmp / "source-policy.json"
        self.pol.write_text(json.dumps(syn_policy()), encoding="utf-8")

    def run_cli(self, which: str, directory: Path) -> Any:
        return run_check("sources-check", "--lock", str(self.lock), "--policy", str(self.pol), "--dir",
                         str(directory), "--arch", ARCH, "--set", which)

    def test_sample_record_accepts_the_partial_apk_entry(self):
        S = load_sbom_check()
        dist = sample_files(APK_KEY, self.b.components[APK_KEY]["files"])
        with self.subTest(case="the record's apk entry is the distfiles files"):
            rec = json.loads(record_text(self.b, "sample"))
            self.assertEqual(rec["components"][APK_KEY],
                             [{"name": f["name"], "sha256": f["sha256"], "size": f["size"]} for f in dist])
            self.assertEqual(S.fetch_record_problems(record_text(self.b, "sample"), self.b.text(), syn_policy(), ARCH,
                                                     "sample"), [])
        with self.subTest(case="the fetch client's own _write_record over the sample plan"):
            d = self.tmp / "written"
            d.mkdir()
            load_fetch()._write_record(str(d), "sample", ARCH, self.b.text(), plan_of(self.b, ARCH, "sample"))
            self.assertEqual(S.fetch_record_problems((d / "fetch.json").read_bytes().decode("utf-8"), self.b.text(),
                                                     syn_policy(), ARCH, "sample"), [])
        with self.subTest(case="sources-check --set sample accepts the directory"):
            d = self.tmp / "sample"
            write_fetched(d, self.b, "sample")
            r = self.run_cli("sample", d)
            self.assertKnown(r)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            want = distinct(self.b, "sample")
            self.assertEqual(r.stdout.splitlines(), sorted(want))
            keys = {k for k, _ in plan_of(self.b, ARCH, "sample")}
            self.assertIn(f"sources-check: ok {len(want)} files, {sum(want.values())} bytes, {len(keys)} components "
                          f"(sample, {ARCH})", r.stderr.splitlines())
        with self.subTest(case="control: that directory for a full bundle is refused (set mismatch)"):
            self.assertRefused(self.run_cli("full", self.tmp / "sample"),
                               "fetch.json: set is sample, this bundle needs full")
        with self.subTest(case="control: an unchanged full directory passes a full bundle"):
            d = self.tmp / "full"
            write_fetched(d, self.b, "full")
            r = self.run_cli("full", d)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            self.assertEqual(r.stdout.splitlines(), sorted(distinct(self.b, "full")))


# --------------------------------------------------------------------------
# U9c-4: the partial component in the index (design item 6)
# --------------------------------------------------------------------------

class PartialIndexTest(_IndexCase):

    def short_plan(self, which: str, drop: Any) -> Any:
        real = self.S.fetch_plan

        def plan(lock: Any, arch: str, w: str) -> Any:
            rows = real(lock, arch, w)
            return [(k, f) for k, f in rows if not drop(k, f)] if w == which else rows
        return plan

    def test_sample_index_marks_the_partial_apk_key(self):
        index = self.ok("sample")
        lock = self.b.lock()
        comps = self.lock_components(index)
        byk = {c["key"]: c for c in comps}
        c = byk[APK_KEY]
        self.assertEqual(c["status"], "partial", "the apk sample key is neither shipped nor not-shipped (U9c-4)")
        self.assertEqual(set(c), LOCK_COMPONENT_KEYS, "no new field: the status says it (design item 6)")
        self.assertEqual([{k: v for k, v in f.items() if k != "path"} for f in c["files"]],
                         lock["components"][APK_KEY]["files"], "every file of the key is listed, lock fields verbatim")
        for f in c["files"]:
            with self.subTest(file=f["name"]):
                if host_of(f["url"]) == APK_DISTFILES:
                    self.assertEqual(f["path"], f"sources/files/{f['sha256']}")
                else:
                    self.assertIsNone(f["path"], "a file not fetched carries no path")
        self.assertEqual({x["status"] for x in index["components"]}, {"shipped", "partial", "not-shipped", "exempt"})
        sample = set(self.S.sample_keys(lock, ARCH))
        self.assertEqual({x["key"] for x in comps if x["status"] == "shipped"}, sample - {APK_KEY})
        self.assertEqual([x["key"] for x in comps if x["status"] == "partial"], [APK_KEY])
        with self.subTest(case="a not-shipped key sharing the fetched tarball's sha256 gets no path (per key, name)"):
            other = byk["apk:readline@8.2.13-r0"]
            self.assertEqual(other["status"], "not-shipped")
            self.assertEqual([f["path"] for f in other["files"]], [None] * len(other["files"]))

    def test_full_index_refuses_a_partial_key(self):
        drop = self.short_plan("full", lambda k, f: k == APK_KEY and host_of(f["url"]) == GITLAB)
        listing = {f["sha256"]: ("file", f["size"]) for _, f in drop(self.b.lock(), ARCH, "full")}
        with mock.patch.object(self.S, "fetch_plan", side_effect=drop):
            problems = self.refused(f"index: {APK_KEY} is partial in a full bundle", listing=listing)
        self.assertFalse([p for p in problems if f"{APK_KEY} is not shipped" in p], problems)
        with self.subTest(case="a partial key of another kind in a full bundle"):
            drop = self.short_plan("full", lambda k, f: k == DEB_KEY and f["name"].endswith(".debian.tar.xz"))
            listing = {f["sha256"]: ("file", f["size"]) for _, f in drop(self.b.lock(), ARCH, "full")}
            with mock.patch.object(self.S, "fetch_plan", side_effect=drop):
                self.refused(f"index: {DEB_KEY} is partial in a full bundle", listing=listing)

    def test_index_refuses_a_partial_key_of_another_kind(self):
        drop = self.short_plan("sample", lambda k, f: k == DEB_KEY and f["name"].endswith(".debian.tar.xz"))
        listing = {f["sha256"]: ("file", f["size"]) for _, f in drop(self.b.lock(), ARCH, "sample")}
        with mock.patch.object(self.S, "fetch_plan", side_effect=drop):
            problems = self.refused(f"index: {DEB_KEY} is partial, and only the apk sample key may be (A81)",
                                    which="sample", listing=listing)
        self.assertFalse([p for p in problems if APK_KEY in p], f"the apk sample key may be partial: {problems}")


# --------------------------------------------------------------------------
# U9c-4: the partial row of the "Source code" section (design item 7)
# --------------------------------------------------------------------------

class PartialNoticesTest(_IndexCase):

    def setUp(self) -> None:
        super().setUp()
        self.section = self.S.source_section

    def index(self, which: str = "sample") -> dict[str, Any]:
        """A hand-made index: one shipped, one partial, one not-shipped key."""
        lock = self.b.lock()

        def comp(key: str, status: str, image: str, pathed: Any) -> dict[str, Any]:
            files = [dict(f, path=f"sources/files/{f['sha256']}" if pathed(f) else None)
                     for f in lock["components"][key]["files"]]
            return {"key": key, "kind": key.split(":", 1)[0], "status": status, "files": files,
                    "packages": [{"image": image, "spdxid": "SPDXRef-x", "purl": None, "name": "x", "always": False,
                                  "expression": None, "licence": {"declared": None, "concluded": None}}]}
        return {"format": 1, "set": which, "arch": ARCH, "git_sha": GIT_SHA, "lock_sha256": "0" * 64,
                "components": [comp(APK_KEY, "partial", "valkey", lambda f: host_of(f["url"]) == APK_DISTFILES),
                               comp(DEB_KEY, "shipped", "postgres", lambda f: True),
                               comp(NOT_SAMPLE, "not-shipped", "ke-app", lambda f: False)],
                "unparsed": [], "unidentified": [], "unlicensed": {}}

    def rows(self, text: str) -> list[str]:
        lines = text.splitlines()
        head = lines.index("| Component | Images | Source |")
        return [ln for ln in lines[head + 2:] if ln.startswith("| ")]

    def assertRefusedWith(self, ix: dict[str, Any], line: str | None = None) -> None:
        text, problems = self.section(ix)
        self.assertIsNone(text, "a section was produced")
        self.assertTrue(problems)
        if line is not None:
            self.assertIn(line, problems)

    def test_notices_partial_row(self):
        ix = self.index()
        apkbuild = next(f for f in ix["components"][0]["files"] if f["name"] == "APKBUILD")
        self.assertEqual(ix["components"][0]["files"][0]["name"], "APKBUILD", "fixture: the APKBUILD comes first")
        text, problems = self.section(ix)
        self.assertEqual(problems, [])
        assert text is not None
        partial_row = f"| `{APK_KEY}` | valkey | {PARTIAL_CELL}{apkbuild['url']} |"
        self.assertEqual(self.rows(text), [
            partial_row,
            f"| `{DEB_KEY}` | postgres | {SHIPPED_CELL} |",
            f"| `{NOT_SAMPLE}` | ke-app | Upstream source: {ix['components'][2]['files'][0]['url']} |"])
        self.assertNotIn("source in `sources/`", partial_row, "the shipped claim is for complete source only")
        self.assertEqual([ln for ln in text.splitlines() if ln.strip()][:3], ["## Source code", BANNER, I3],
                         "the do-not-distribute banner stays first (O-13 (4))")
        with self.subTest(case="the URL is the first file with no path, not the first file"):
            ix2 = copy.deepcopy(ix)
            files = ix2["components"][0]["files"]
            files.insert(0, files.pop(next(i for i, f in enumerate(files) if f["path"] is not None)))
            text2, problems2 = self.section(ix2)
            self.assertEqual(problems2, [])
            assert text2 is not None
            self.assertEqual(self.rows(text2)[0], partial_row)
        with self.subTest(case="a partial component in a full index is refused"):
            self.assertRefusedWith(self.index("full"), f"notices: {APK_KEY} is partial in a full index")
        for case, every in (("no fetched file", False), ("no unfetched file", True)):
            with self.subTest(case=f"a partial component with {case} is refused"):
                ix3 = copy.deepcopy(ix)
                for f in ix3["components"][0]["files"]:
                    f["path"] = f"sources/files/{f['sha256']}" if every else None
                self.assertRefusedWith(ix3, f"notices: {APK_KEY} is partial but lists no fetched file or no "
                                            "unfetched file")
        for case, change in (("a pipe in the URL", lambda c: c["files"][0].update(url=c["files"][0]["url"] + "|x")),
                             ("a backtick in the key", lambda c: c.update(key=APK_KEY + "`x")),
                             ("a markdown character in an image", lambda c: c["packages"][0].update(image="valkey*")),
                             ("a newline in the URL", lambda c: c["files"][0].update(url=c["files"][0]["url"] + "\nx"))):
            with self.subTest(case=f"{case} is refused, never escaped"):
                ix4 = copy.deepcopy(ix)
                change(ix4["components"][0])
                self.assertRefusedWith(ix4)
        with self.subTest(case="control: the not-shipped and shipped rows are unchanged"):
            self.assertIn(f"| `{DEB_KEY}` | postgres | {SHIPPED_CELL} |", text)


# --------------------------------------------------------------------------
# U9c-4 / U9-6 at bundle level: no GitLab file of the partial key on disk
# --------------------------------------------------------------------------

class PartialBundleTest(_SourcesBase):

    def test_partial_files_without_path_are_not_on_disk(self):
        raw = raw_doc("valkey", pinned_syft_version())
        self._relock_for({"valkey": raw})
        apk = sorted(k for k in self.src_lock.components if k.startswith("apk:"))
        self.assertEqual(len(apk), 1, f"fixture: one apk key added to the synthetic lock: {apk}")
        key = apk[0]
        _, _, out = self._ok_bundle(sources_set="sample", FAKE_SYFT_RAW=json.dumps({"valkey": json.dumps(raw)}))
        app = out / "app"
        index = json.loads((app / "sources" / "index.json").read_text(encoding="utf-8"))
        comp = next(c for c in index["components"] if c.get("key") == key)
        self.assertEqual(comp["status"], "partial", "the apk sample key of a sample bundle is partial (U9c-4)")
        on_disk = set(os.listdir(app / "sources" / "files"))
        paths = {f["path"] for c in index["components"] for f in c["files"] if f.get("path")}
        for p in sorted(paths):
            self.assertTrue((app / p).is_file(), f"{p}: a path that is not on disk")
        self.assertEqual({f"sources/files/{n}" for n in on_disk}, paths, "every file under files/ is some path")
        self.assertEqual(on_disk, set(self._distinct("sample")), "files/ is exactly the sample plan's sha256 set")
        unpathed = [f for f in comp["files"] if f["path"] is None]
        self.assertEqual([f["name"] for f in unpathed], ["APKBUILD"])
        for f in unpathed:
            self.assertNotIn(f["sha256"], on_disk, f"{f['name']}: a GitLab file of the partial key is on disk")
        self.assertEqual([host_of(f["url"]) for f in comp["files"] if f["path"]], [APK_DISTFILES])
        section = _section((out / NOTICES).read_text(encoding="utf-8"), "Source code")
        self.assertIn(f"| `{key}` | valkey | {PARTIAL_CELL}{unpathed[0]['url']} |", section.splitlines())


if __name__ == "__main__":
    unittest.main()
