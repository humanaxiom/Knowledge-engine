"""platform-sbom U7d rework round 1 RED: controls for the ReworkR1U7d* tests
(tests/test_sources_resolve.py, tests/test_sources_lock.py) and the tests
round 1 changes. Targets u7d/r1-target-*; the baseline is the SAVED
u7d/target-* files (the U7d RED targets); the B2 row also runs against the
working tree's script (the U7d GREEN, with the hostpath fix).

Never writes the repository. It builds a temporary root with the U7d targets
(docs/evidence/platform-sbom/u7d/target-*: the resolver, sbom_check.py,
sources_lock.sh and source-policy.json) in place and runs real test methods
on the targets, on the U7c baseline (the SAVED u7c/r1-target-* files, equal to
86f7831, with the committed policy and script) and on mutants of each target.
Each "must fail" row names the one test method that must fail. Exit 1 if any
row is unexpected.

Usage (in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7d/u7d_controls.py [--base repo]
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
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
from tests import test_sbom_obligations as tso  # noqa: E402
from tests import test_sources_lock as tsl  # noqa: E402
from tests import test_sources_resolve as tsr  # noqa: E402

HERE = Path(__file__).resolve().parent
U7C = HERE.parent / "u7c"
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"scripts/sources_resolve.py": "r1-target-sources_resolve.py",
           "scripts/sources_lock.sh": "r1-target-sources_lock.sh",
           "scripts/sbom_check.py": "r1-target-sbom_check.py",
           "docker/source-policy.json": "target-source-policy.json"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.sources.yml", ".env.example", ".gitignore", ".dockerignore", "pyproject.toml", "uv.lock",
        "LICENSE", "NOTICE.md", "config", "licenses", "docs/quickstart.md", ".github", "tests/fixtures"]
WORK = Path(tempfile.mkdtemp(prefix="u7d-r1-controls-"))
rows: list[tuple[str, str, str, bool]] = []


def head(rel: str) -> str:
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


SRC = {rel: (REPO / rel if BASE_REPO else HERE / name).read_text(encoding="utf-8") for rel, name in TARGETS.items()}
BASELINE = {rel: (HERE / name.replace("r1-", "")).read_text(encoding="utf-8") for rel, name in TARGETS.items()}
WORKTREE_SH = (REPO / "scripts" / "sources_lock.sh").read_text(encoding="utf-8")


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
    spec = importlib.util.spec_from_file_location(f"u7d_r1_check_{path.parent.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_test(cls: type, method: str, root: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    check = module_at(root / "scripts" / "sbom_check.py")
    pol = root / "docker" / "source-policy.json"
    patches = [mock.patch.object(tsr, "RESOLVER", root / "scripts" / "sources_resolve.py"),
               mock.patch.object(tsr, "LOCK_SH", root / "scripts" / "sources_lock.sh"),
               mock.patch.object(tsr, "SOURCES_COMPOSE", root / "docker-compose.sources.yml"),
               mock.patch.object(tsr, "ROOT", root), mock.patch.object(tob, "ROOT", root),
               mock.patch.object(tsl, "ROOT", root), mock.patch.object(tsl, "POLICY", pol),
               mock.patch.object(tso, "POLICY", pol),
               mock.patch.object(tsr, "load_sbom_check", lambda m=check: m),
               mock.patch.object(tsl, "load_sbom_check", lambda m=check: m),
               mock.patch.object(tsl, "fn", lambda name, m=check: getattr(m, name))]
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


R1_CLASSES = [tsr.ReworkR1U7dUrlErrorTest, tsr.ReworkR1U7dSymlinkTest, tsr.ReworkR1U7dScriptTest,
              tsl.ReworkR1U7dSuiteBindingTest]
CHANGED = [(tsr.U7dLockNeedsTest, "test_trixie_and_unknown"), (tsr.U7dScriptStaticTest, "test_the_inrelease_is_copied")]
NEW = [t for cls in R1_CLASSES for t in own(cls)] + CHANGED
OLD_CLASSES = (tsr.ResolverHopsTest, tsr.ResolverParsersTest, tsr.ResolverRoutesTest, tsr.ResolverMergeTest,
               tsr.ResolverMainTest, tsr.LockNeedsTest, tsr.SourcesComposeTest, tsr.SourcesLockScriptStaticTest,
               tsr.SourcesLockScriptRunTest, tsr.ReworkR1TransportTest, tsr.ReworkR1MainTest,
               tsr.ReworkR1RealOpenerTest, tsr.ReworkR1HopRulesTest, tsr.ReworkR1PypiScopeTest, tsr.ReworkR1KeysTest,
               tsr.ReworkR1LockScriptRunTest, tsr.U7cDebRouteTest, tsr.U7cApkRouteTest, tsr.U7cCoverageTest,
               tsr.U7cCarriedTest, tsr.U7cLockNeedsTest, tsr.U7cLockScriptRunTest, tsr.ReworkR1U7cApkbuildTest,
               tsr.ReworkR1U7cDscTest, tsr.ReworkR1U7cApkbuildAssignTest, tsr.ReworkR1U7cListingTest,
               tsr.ReworkR1U7cApiUrlResolverTest, tsr.U7dRetryConstantsTest, tsr.U7dRetryTest, tsr.U7dCarriedTest,
               tsr.U7dPgdgRouteTest, tsr.U7dLockNeedsTest, tsr.U7dCoverageTest, tsr.U7dScriptStaticTest)
OLD = [t for cls in OLD_CLASSES for t in every(cls) if t not in CHANGED]
U7A = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.LockCheckCliTest,
                     tsl.ReworkR1BindingTest, tsl.ReworkR1PendingNeo4jCliTest, tsl.U7cApkLockRulesTest,
                     tsl.ReworkR1U7cApkbuildPathTest, tsl.ReworkR1U7cApiUrlTest, tsl.U7dPgdgLockRulesTest,
                     tsl.U7dApkSegmentNameTest, tso.PolicyU6SchemaTest) for t in own(cls)]

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(NEW)} round-1 tests", False, [p for c, m in NEW for p in run_test(c, m, TROOT)])
row("target", f"TARGET: the {len(OLD)} U7b, U7c and U7d tests", False, [p for c, m in OLD for p in run_test(c, m, TROOT)])
row("target", f"TARGET: {len(U7A)} lock and policy tests", False, [p for c, m in U7A for p in run_test(c, m, TROOT)])

BROOT = make_root(dict(BASELINE))
for cls, method in NEW:
    row("u7d", f"U7d RED targets: {cls.__name__}.{method}", True, run_test(cls, method, BROOT))
WROOT = make_root(dict(BASELINE, **{"scripts/sources_lock.sh": WORKTREE_SH}))
row("worktree", "B2 on the working tree's script (the GREEN hostpath fix): test_docker_save_gets_the_host_path", False,
    run_test(tsr.ReworkR1U7dScriptTest, "test_docker_save_gets_the_host_path", WROOT))

RES, SH, CHK = "scripts/sources_resolve.py", "scripts/sources_lock.sh", "scripts/sbom_check.py"
UE, SY, SC, SB = tsr.ReworkR1U7dUrlErrorTest, tsr.ReworkR1U7dSymlinkTest, tsr.ReworkR1U7dScriptTest, \
    tsl.ReworkR1U7dSuiteBindingTest
MUTANTS: dict[str, tuple[str, Callable[[str], str], type, str]] = {
    "URLError not unwrapped": (RES, swap(
        "        if isinstance(exc.reason, BaseException):\n            raise exc.reason from None",
        "        if False:\n            raise exc.reason from None"), UE, "test_the_mapping"),
    "URLError not unwrapped (resolve)": (RES, swap(
        "        if isinstance(exc.reason, BaseException):\n            raise exc.reason from None",
        "        if False:\n            raise exc.reason from None"), UE, "test_through_resolve"),
    "an SSL URLError retried": (RES, swap(
        "            raise exc.reason from None  # a TimeoutError",
        "            raise TimeoutError() from None  # a TimeoutError"), UE, "test_through_resolve"),
    "the suite unbound": (CHK, swap(
        "        if suite is not None and isinstance(e, dict) and e.get(\"suite\") != suite:",
        "        if False:"), SB, "test_the_suite_is_bound"),
    "two derived suites accepted": (CHK, swap(
        "    if len(suites) != 1:\n        return None, [f\"{_clean(key)}: packages derive suites",
        "    if len(suites) > 1 and False:\n        return None, [f\"{_clean(key)}: packages derive suites"),
        SB, "test_packages_that_derive_two_suites"),
    "links locked as files": (RES, swap(
        '        link = e.get("type") == "blob" and e.get("mode") == "120000" and links is not None\n'
        '        if not link and (e.get("type") != "blob" or e.get("mode") not in ("100644", "100755")):',
        '        link = False\n'
        '        if e.get("type") != "blob" or e.get("mode") not in ("100644", "100755", "120000"):'),
        SY, "test_the_real_shape"),
    "the link target not checked": (RES, swap(
        "    if there is None or os.path.dirname(there) != os.path.dirname(rel):\n        raise refused",
        "    if False:\n        raise refused"), SY, "test_refused_links"),
    "a link named in sha512sums accepted": (RES, swap(
        "    if name in sums:\n        raise ResolveError(f\"{origin}: {_clean(name)} is a symlink named in sha512sums\")",
        "    if False:\n        raise ResolveError(f\"{origin}: {_clean(name)} is a symlink named in sha512sums\")"),
        SY, "test_refused_links"),
    "the content_sha256 not bound": (RES, swap(
        "    if len(target_bytes) > 1024 or hashlib.sha256(target_bytes).hexdigest() != want:",
        "    if len(target_bytes) > 1024:"), SY, "test_refused_links"),
    "hostpath dropped": (SH, swap('  docker save -o "$(hostpath "$work/tars/$name.tar")" "$ref"',
                                  '  docker save -o "$work/tars/$name.tar" "$ref"'), SC, "test_docker_save_gets_the_host_path"),
    "--evidence-dir optional": (SH, swap('[ -n "$evdir" ] || usage\n', ""), SC, "test_the_option_is_required"),
    "the directory not checked": (SH, swap(
        'if [ ! -d "$evdir" ] || [ ! -w "$evdir" ]; then fail "evidence: $evdir is not a writable directory"; fi\n'
        'evdir="$(cd -- "$evdir" && pwd)"\n', ""), SC, "test_the_directory_must_be_writable"),
    "the copy after the move": (SH, swap(
        'mv -f -- "$tmp" docker/sources.lock.json\n',
        'mv -f -- "$tmp" docker/sources.lock.json\nfor f in "${inreleases[@]}"; do cp -P -- "$f" "$evdir/"; done\n',
        '  cp -P -- "$f" "$evdir/" || fail "evidence: copy of $f failed"\n', '  :\n'),
        SC, "test_the_inrelease_is_copied_before_the_move"),
    "a hard-coded evidence path": (SH, swap('  cp -P -- "$f" "$evdir/" || fail',
                                            '  mkdir -p -- docs/evidence/platform-sbom/u7d && cp -P -- "$f" docs/evidence/platform-sbom/u7d/ || fail'),
                                   tsr.U7dScriptStaticTest, "test_the_inrelease_is_copied"),
    "a failed copy ignored": (SH, swap('  cp -P -- "$f" "$evdir/" || fail "evidence: copy of $f failed"',
                                       '  cp -P -- "$f" "$evdir/" || true'), SC, "test_failures_leave_the_lock"),
    "-f only (links followed)": (SH, swap('  if [ -L "$f" ]; then fail "evidence: $f is a link"; fi\n', ""),
                                 SC, "test_failures_leave_the_lock"),
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
print(f"\nU7d rework round 1 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
