"""platform-sbom U7c RED: controls for the U7c tests in
tests/test_sources_resolve.py (U7c* classes, and the two LockNeedsTest
methods U7c's A1 changes).

Never writes the repository. It builds a temporary root holding the files the
harnesses read, with the U7c targets (docs/evidence/platform-sbom/u7c/target-*)
in place, and runs real test methods on the targets, on the U7b baseline (the
SAVED u7b/r1-target-* files, byte-equal to the U7b commit 6d8fa4d) and on
mutants of each target. Each "must fail" row names the one test method that
must fail. Exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7c/u7c_controls.py [--base repo]
`--base repo` uses the repository's own files instead of the targets (GREEN).
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests import test_offline_bundle as tob  # noqa: E402
from tests import test_sources_lock as tsl  # noqa: E402
from tests import test_sources_resolve as tsr  # noqa: E402

HERE = Path(__file__).resolve().parent
U7B = HERE.parent / "u7b"
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"scripts/sources_resolve.py": "target-sources_resolve.py",
           "scripts/sources_lock.sh": "target-sources_lock.sh",
           "scripts/sbom_check.py": "target-sbom_check.py"}
BASELINE = {"scripts/sources_resolve.py": "r1-target-sources_resolve.py",
            "scripts/sources_lock.sh": "r1-target-sources_lock.sh",
            "scripts/sbom_check.py": "r1-target-sbom_check.py"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.sources.yml", ".env.example", ".gitignore", ".dockerignore", "pyproject.toml", "uv.lock",
        "LICENSE", "NOTICE.md", "config", "licenses", "docs/quickstart.md", ".github", "tests/fixtures"]
WORK = Path(tempfile.mkdtemp(prefix="u7c-controls-"))
rows: list[tuple[str, str, str, bool]] = []

SRC = {rel: (REPO / rel if BASE_REPO else HERE / name).read_text(encoding="utf-8") for rel, name in TARGETS.items()}
SAVED_U7B = {rel: (U7B / name).read_text(encoding="utf-8") for rel, name in BASELINE.items()}


def make_root(files: dict[str, str | None]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="root-", dir=WORK))
    for rel in COPY:
        src = REPO / rel
        if src.is_dir():
            shutil.copytree(src, root / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
    for rel, content in files.items():
        path = root / rel
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    return root


def module_at(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"u7c_check_{path.parent.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_test(cls: type, method: str, root: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    check = module_at(root / "scripts" / "sbom_check.py")
    patches = [mock.patch.object(tsr, "RESOLVER", root / "scripts" / "sources_resolve.py"),
               mock.patch.object(tsr, "LOCK_SH", root / "scripts" / "sources_lock.sh"),
               mock.patch.object(tsr, "SOURCES_COMPOSE", root / "docker-compose.sources.yml"),
               mock.patch.object(tsr, "ROOT", root), mock.patch.object(tob, "ROOT", root),
               mock.patch.object(tsl, "ROOT", root),
               mock.patch.object(tsr, "load_sbom_check", lambda m=check: m),
               mock.patch.object(tsl, "load_sbom_check", lambda m=check: m)]
    for p in patches:
        p.start()
    try:
        suite.run(result)
    finally:
        for p in patches:
            p.stop()
    return [f"{method}: " + str(b[1]).strip().splitlines()[-1] for b in result.failures + result.errors]


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    ok = bool(problems) == must_fail
    rows.append((group, name, "must fail" if must_fail else "must pass", ok))
    detail = problems[0][:110] if problems else "no problem"
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<70} {'must fail' if must_fail else 'must pass'} | {detail}",
          flush=True)


def swap(*pairs: str) -> Callable[[str], str]:
    def change(t: str) -> str:
        for old, new in zip(pairs[::2], pairs[1::2]):
            if t.count(old) != 1:
                raise AssertionError(f"mutant anchor found {t.count(old)} times: {old[:70]!r}")
            t = t.replace(old, new, 1)
        return t
    return change


def own(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls) if n in vars(cls)]


def every(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls)]


U7C_CLASSES = [tsr.U7cDebRouteTest, tsr.U7cApkRouteTest, tsr.U7cCoverageTest, tsr.U7cCarriedTest,
               tsr.U7cLockNeedsTest, tsr.U7cLockScriptRunTest, tsl.U7cApkLockRulesTest]
CHANGED = [(tsr.LockNeedsTest, "test_lock_needs_doc_on_the_fixtures"),
           (tsr.LockNeedsTest, "test_release_from_the_saved_tar")]
NEW = [t for cls in U7C_CLASSES for t in own(cls)] + CHANGED
OLD_CLASSES = (tsr.ResolverHopsTest, tsr.ResolverParsersTest, tsr.ResolverRoutesTest, tsr.ResolverMergeTest,
               tsr.ResolverMainTest, tsr.LockNeedsTest, tsr.SourcesComposeTest, tsr.SourcesLockScriptStaticTest,
               tsr.SourcesLockScriptRunTest, tsr.ReworkR1TransportTest, tsr.ReworkR1MainTest,
               tsr.ReworkR1RealOpenerTest, tsr.ReworkR1HopRulesTest, tsr.ReworkR1PypiScopeTest, tsr.ReworkR1KeysTest,
               tsr.ReworkR1LockScriptRunTest)
OLD = [t for cls in OLD_CLASSES for t in every(cls) if t not in CHANGED]
U7A = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.LockCheckCliTest,
                     tsl.ReworkR1PendingNeo4jCliTest) for t in own(cls)]
# Guards: U7c tests the U7b baseline already passes (R-2 (c) pins today's text).
GUARDS = {(tsr.U7cLockScriptRunTest, "test_the_six_equal_the_bundled_names")}

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(NEW)} U7c tests", False, [p for c, m in NEW for p in run_test(c, m, TROOT)])
row("target", f"TARGET: the {len(OLD)} U7b and rework-1 tests", False, [p for c, m in OLD for p in run_test(c, m, TROOT)])
row("target", f"TARGET: {len(U7A)} U7a lock tests", False, [p for c, m in U7A for p in run_test(c, m, TROOT)])

BROOT = make_root(dict(SAVED_U7B))
for cls, method in NEW:
    guard = (cls, method) in GUARDS
    row("u7b", f"U7b (saved r1 targets): {cls.__name__}.{method}" + (" (guard)" if guard else ""), not guard,
        run_test(cls, method, BROOT))

RES, SH, CHK = "scripts/sources_resolve.py", "scripts/sources_lock.sh", "scripts/sbom_check.py"
D, A, C, N = tsr.U7cDebRouteTest, tsr.U7cApkRouteTest, tsr.U7cCarriedTest, tsr.U7cLockNeedsTest
L = tsl.U7cApkLockRulesTest
MUTANTS: dict[str, tuple[str, Callable[[str], str], type, str]] = {
    # deb (D1-D7)
    "deb: the listed files streamed": (RES, swap(
        "    others = dsc_files(parse_dsc(body), dsc, src, ver, names)\n",
        "    others = dsc_files(parse_dsc(body), dsc, src, ver, names)\n"
        "    for f in others:\n        stream(f[\"url\"], allow)\n"), D, "test_the_entry"),
    "deb: the .dsc sha1 not compared": (RES, swap('    if digests["sha1"] != names[dsc]:', "    if False:"),
                                        D, "test_failures"),
    "deb: Source/Version not checked": (RES, swap(
        '    if (fields.get("Source"), fields.get("Version")) != (src, ver):', "    if False:"), D, "test_failures"),
    "deb: sizes not compared": (RES, swap(
        "    if sorted((n, z) for _, z, n in sha256s) != sorted((n, z) for _, z, n in md5s) or",
        "    if sorted(n for _, z, n in sha256s) != sorted(n for _, z, n in md5s) or"), D, "test_failures"),
    "deb: Checksums-Sha1 not compared": (RES, swap("        if names.get(name) != h:", "        if False:"),
                                         D, "test_failures"),
    "deb: the name rule dropped": (RES, swap(
        "    for _, _, name in sha256s + md5s + sha1s:\n        if not safe_name(name):",
        "    for _, _, name in sha256s + md5s + sha1s:\n        if False:"), D, "test_failures"),
    "deb: a listed file absent from srcfiles accepted": (RES, swap(
        "        if name not in names:\n            raise ResolveError(f\"{_clean(name)} is in the .dsc",
        "        if False:\n            raise ResolveError(f\"{_clean(name)} is in the .dsc"), D, "test_failures"),
    "deb: two sha1s for a name accepted": (RES, swap('            if out.get(e["name"], sha1) != sha1:',
                                                     "            if False:"), D, "test_failures"),
    "deb: fileinfo keys not checked as 40 hex": (RES, swap(
        'not re.fullmatch(r"[0-9a-f]{40}", sha1) or ', ""), D, "test_failures"),
    "deb: the .dsc cap dropped": (RES, swap('    got = capped(durl, allow, dsc, TEXT_LIMIT, ("sha1", "sha256"))',
                                            '    got = capped(durl, allow, dsc, 1 << 30, ("sha1", "sha256"))'),
                                  D, "test_failures"),
    "deb: dash-escapes kept": (RES, swap('        lines = [ln[2:] if ln.startswith("- ") else ln for ln in rest]',
                                         "        lines = rest"), D, "test_parse_dsc"),
    "deb: the signature kept": (RES, swap('            if ln.startswith("-----BEGIN PGP SIGNATURE"):',
                                          "            if False:"), D, "test_parse_dsc"),
    "deb: the epoch kept in the .dsc name": (RES, swap(
        "    dsc = f\"{src}_{ver.split(':', 1)[1] if ':' in ver else ver}.dsc\"", "    dsc = f\"{src}_{ver}.dsc\""),
        D, "test_dsc_forms"),
    "deb: the .dsc upstream from is item 4's old text": (RES, swap(
        'f"{SNAPSHOT} mr/package fileinfo")] + others)', 'f"{SNAPSHOT} mr/package/{src}/{ver}/srcfiles")] + others)'),
        D, "test_the_entry"),
    "deb: no pause": (RES, swap("        if wait > 0:\n", "        if False:\n"), C, "test_snapshot_pause"),
    "deb: the pause 0.5 s": (RES, swap("SNAPSHOT_PAUSE = 1.0  #", "SNAPSHOT_PAUSE = 0.5  #"), C, "test_snapshot_pause"),
    "deb: the route dropped (skipped)": (RES, swap('ROUTES = ("temurin", "maven", "pypi", "neo4j", "deb", "apk")',
                                                   'ROUTES = ("temurin", "maven", "pypi", "neo4j", "apk")'),
                                         tsr.U7cCoverageTest, "test_the_fixture_keys"),
    # apk (A2-A5, R-1, and the U7c gap rulings 1-4)
    "apk: both repos not detected": (RES, swap("    if len(found) == 2:", "    if False:"), A, "test_failures"),
    "apk: x-next-page ignored": (RES, swap('        if headers.get("x-next-page"):', "        if False:"),
                                 A, "test_failures"),
    "apk: the listing not recursive": (RES, swap("&ref={commit}&recursive=true&per_page=100", "&ref={commit}&per_page=100"),
                                       A, "test_the_entry"),
    "apk: an empty listing counted as here": (RES, swap("        if blobs:  # ruling 2", "        if True:  # ruling 2"),
                                              A, "test_the_entry"),
    "apk: a symlink or submodule accepted": (RES, swap(
        '        if e.get("type") != "blob" or e.get("mode") not in ("100644", "100755"):', "        if False:"),
        A, "test_failures"),
    "apk: two blobs with one basename accepted": (RES, swap("        if name in out:", "        if False:"),
                                                  A, "test_failures"),
    "apk: an unsafe listing path accepted": (RES, swap(
        "        if segs[-1] != name or not all(safe_name(x) for x in segs):", "        if segs[-1] != name:"),
        A, "test_failures"),
    "apk: a subdirectory file fetched at its basename": (RES, swap('        url = f"{raw}/{rel}"', '        url = f"{raw}/{name}"'),
                                                         A, "test_the_entry"),
    "apk: files outside sha512sums not locked": (RES, swap(
        "        if name in sums:\n            hashed, size = stream(url, allow, (\"sha512\", \"sha256\"))",
        "        if name not in sums:\n            continue\n        if name in sums:\n"
        "            hashed, size = stream(url, allow, (\"sha512\", \"sha256\"))"), A, "test_the_entry"),
    "apk: an install script's content_sha256 not compared": (RES, swap("            if hashed[\"sha256\"] != cs:",
                                                                       "            if False:"), A, "test_failures"),
    "apk: the APKBUILD content_sha256 not compared": (RES, swap('    if digests["sha256"] != want:', "    if False:"),
                                                      A, "test_failures"),
    "apk: the old APKBUILD from text": (RES, swap('    gl_from = f"gitlab files API content_sha256 at {commit}"',
                                                  '    gl_from = f"gitlab.alpinelinux.org files API at {commit}"'),
                                        A, "test_the_entry"),
    "apk: pkgver/pkgrel not compared": (RES, swap('f"{pv}-r{pr}" != ver:', "False:"), A, "test_failures"),
    "apk: a local file's sha512 not compared": (RES, swap('            if hashed["sha512"] != sums[name]:',
                                                          "            if False:"), A, "test_failures"),
    "apk: a distfile's sha512 not compared": (RES, swap('        if hashed["sha512"] != sha512:', "        if False:"),
                                              A, "test_failures"),
    "apk: a sha512sums `$` accepted": (RES, swap('    if "$" in block or "`" in block:', "    if False:"),
                                       A, "test_failures"),
    "apk: an unsafe sha512sums name accepted": (RES, swap("        if not safe_name(lm.group(2)):", "        if False:"),
                                                A, "test_failures"),
    "apk: a malformed route accepted": (RES, swap("        if not isinstance(value, str) or not re.fullmatch(rx, value):",
                                                  "        if False:"), A, "test_failures"),
    "apk: the route checked commit first": (RES, swap(
        '    for field, value, rx in (("origin", route.get("origin"), re.escape(origin)), ("ver", route.get("ver"), re.escape(ver)),\n'
        '                             ("commit", commit, r"[0-9a-f]{40}"), ("branch", branch, r"v\\d+\\.\\d+")):',
        '    for field, value, rx in (("commit", commit, r"[0-9a-f]{40}"), ("branch", branch, r"v\\d+\\.\\d+")):'),
        A, "test_failures"),
    "apk: distfiles never used": (RES, swap('        url = f"https://{DISTFILES}/distfiles/{branch}/{name}"',
                                            '        url = f"{raw}/{name}"'), A, "test_the_entry"),
    "deb: the old Files text": (RES, swap('        raise ResolveError(".dsc has no Files")',
                                          '        raise ResolveError(f"{_clean(dsc)}: no Files")'), D, "test_failures"),
    # the U7a apk lock rules, as the gap rulings change them (i), (ii)
    "lock: the subdirectory path refused (U7a's old rule)": (CHK, swap("                want = path\n", "                pass\n"),
                                                             L, "test_the_new_shapes_pass"),
    "lock: a subdirectory segment not checked": (CHK, swap(
        '            if subs and all(LOCK_FILE_NAME_RE.fullmatch(x) and ".." not in x for x in subs) and \\',
        "            if subs and \\"), L, "test_bad_shapes"),
    "lock: sha256 refused outside the APKBUILD (U7a's old rule)": (CHK, swap(
        '                    alg(f) == "sha256" and fup.get("from") == gl_from and on_gitlab):',
        '                    False):'), L, "test_the_new_shapes_pass"),
    "lock: a sha256 file's from not checked": (CHK, swap(
        '                    alg(f) == "sha256" and fup.get("from") == gl_from and on_gitlab):',
        '                    alg(f) == "sha256" and on_gitlab):'), L, "test_bad_shapes"),
    "lock: a sha256 file's host not checked": (CHK, swap(
        '                    alg(f) == "sha256" and fup.get("from") == gl_from and on_gitlab):',
        '                    alg(f) == "sha256" and fup.get("from") == gl_from):'), L, "test_bad_shapes"),
    "lock: the APKBUILD from not checked": (CHK, swap("            if fup.get(\"from\") != gl_from:  # U7c gap rulings",
                                                      "            if False:  # U7c gap rulings"), L, "test_bad_shapes"),
    # carried (C1, C2) and pgdg
    "C1: a server-supplied url keeps the first-request exemption": (RES, swap(
        "        refusal = _hop_refusal(current, first=hop == 0 and not supplied)",
        "        refusal = _hop_refusal(current, first=hop == 0)"), C, "test_a_server_supplied_url_gets_the_hop_rules"),
    "C2: read(CHUNK) in the real opener": (RES, swap("            data = r.read1(CHUNK)", "            data = r.read(CHUNK)"),
                                           C, "test_the_real_opener_reads_with_read1"),
    "pgdg: the old skip text": (RES, swap("route until Q71)", "route until U7c)"), C, "test_pgdg_is_skipped_until_q71"),
    # lock-needs (A1)
    "lock-needs: the origin not compared": (CHK, swap('                and st.get("o") == origin and', "                and"),
                                            N, "test_problems"),
    "lock-needs: the commit not checked as 40 hex": (CHK, swap(
        ' and re.fullmatch(r"[0-9a-f]{40}", st.get("c", ""))]', "]"), N, "test_problems"),
    "lock-needs: two commits accepted": (CHK, swap("    if len(commits) > 1:", "    if False:"), N, "test_problems"),
    "lock-needs: alpine-release not compared with the purl": (CHK, swap(
        '        if not rm or distro != f"alpine-{release}":', "        if not rm:"), N, "test_problems"),
    "lock-needs: the bottom layer's db wins": (CHK, swap(
        "                        found = data.read(limit + 1) if data is not None else None",
        "                        found = found or (data.read(limit + 1) if data is not None else None)"),
        N, "test_the_cli_reads_the_tar"),
    "lock-needs: the db read with no 16 MiB limit": (CHK, swap(
        "tar_file_text(path, APK_DB, 16 << 20)", "tar_file_text(path, APK_DB, 1 << 40)"),
        N, "test_the_cli_reads_the_tar"),
    "lock-needs: the release file not fail-closed": (CHK, swap(
        "                    body = tar_file_text(path, TEMURIN_RELEASE)",
        "                    body = tar_file_text(path, TEMURIN_RELEASE, 1 << 40)"), N, "test_the_cli_reads_the_tar"),
    # the script (A1, R-2)
    "script: --tar for ke-neo4j only": (SH, swap(
        '  tar_args+=(--tar "$name=/tars/$name.tar")  # U7c A1',
        '  if [ "$name" = ke-neo4j ]; then tar_args+=(--tar "$name=/tars/$name.tar"); fi  # U7c A1'),
        tsr.U7cLockScriptRunTest, "test_lock_needs_gets_every_tar"),
    "script: a seventh name in six": (SH, swap("six=(ke-app ke-gateway ke-neo4j phoenix postgres valkey)",
                                               "six=(ke-app ke-gateway ke-neo4j phoenix postgres valkey redis)"),
                                      tsr.U7cLockScriptRunTest, "test_the_six_equal_the_bundled_names"),
}
for name, (rel, m, cls, method) in MUTANTS.items():
    try:
        files = dict(SRC)
        files[rel] = m(SRC[rel])
    except AssertionError as exc:
        row("mutant", name, True, [])
        print(f"    anchor: {exc}")
        continue
    row("mutant", f"{name} -> {method}", True, run_test(cls, method, make_root(files)))

bad = [r for r in rows if not r[3]]
print(f"\nU7c controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
