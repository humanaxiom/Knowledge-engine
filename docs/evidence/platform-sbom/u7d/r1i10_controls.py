"""platform-sbom U7d rework round 1, item 10 RED: controls for the leading
`_` file-name rule and the key-prefixed symlink skip line
(ReworkR1U7dUnderscoreTest, ReworkR1U7dUnderscoreLockTest, and the changed
ReworkR1U7dSymlinkTest.test_the_real_shape). Targets u7d/r1-target-* (with
item 10); the baseline is u7d/r1-pre10-* (the round-1 targets before item 10,
equal to the working tree the developer's run 2 used).

Never writes the repository: a temporary root per row, real test methods.
Exit 1 if any row is unexpected.

Usage (in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7d/r1i10_controls.py
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
WORK = Path(tempfile.mkdtemp(prefix="u7d-r1i10-controls-"))
rows: list[tuple[str, str, str, bool]] = []


def head(rel: str) -> str:
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


SRC = {rel: (REPO / rel if BASE_REPO else HERE / name).read_text(encoding="utf-8") for rel, name in TARGETS.items()}
BASELINE = {rel: (HERE / name.replace("r1-target-", "r1-pre10-") if name.startswith("r1-target-") and "lock.sh" not in name else HERE / name).read_text(encoding="utf-8")
            for rel, name in TARGETS.items()}
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
              tsr.ReworkR1U7dUnderscoreTest, tsl.ReworkR1U7dUnderscoreLockTest,
              tsr.ReworkR1U7dEmptyFileTest, tsl.ReworkR1U7dEmptyFileLockTest,
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


UT, ULT, SYT = tsr.ReworkR1U7dUnderscoreTest, tsl.ReworkR1U7dUnderscoreLockTest, tsr.ReworkR1U7dSymlinkTest
EFT, EFLT = tsr.ReworkR1U7dEmptyFileTest, tsl.ReworkR1U7dEmptyFileLockTest  # item 12
I10 = [t for cls in (UT, ULT, EFT, EFLT) for t in own(cls)] + [(SYT, "test_the_real_shape")]
GUARDS = {(UT, "test_still_refused"), (ULT, "test_still_refused")}
ALL = [t for t in NEW + OLD + U7A]

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(I10)} item-10 and item-12 tests", False, [p for c, m in I10 for p in run_test(c, m, TROOT)])
row("target", f"TARGET: the {len(ALL)} round-1, U7b-U7d and lock tests", False,
    [p for c, m in ALL for p in run_test(c, m, TROOT)])

BROOT = make_root(dict(BASELINE))
for cls, method in I10:
    guard = (cls, method) in GUARDS
    row("pre10", f"{'guard ' if guard else ''}{cls.__name__}.{method}", not guard, run_test(cls, method, BROOT))

RES, CHK = "scripts/sources_resolve.py", "scripts/sbom_check.py"
OLD_RX, NEW_RX = "[A-Za-z0-9][A-Za-z0-9._+~-]{0,254}", "[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}"
WIDE_RX = "[A-Za-z0-9_.-][A-Za-z0-9._+~-]{0,254}"
RES_RX = 'NAME_RE = re.compile(r"' + NEW_RX + '")'
CHK_RX = 'LOCK_FILE_NAME_RE = re.compile(r"' + NEW_RX + '")'
PRINT = '    print(f"{_clean(key)}: {_clean(path)} -> {_clean(target)} (symlink to a locked file, skipped)", file=sys.stderr)'
LOW = '    low = 0 if kind == "apk" and isinstance(f["url"], str) and _apk_api_shape(f["url"]) is not None else 1'
MUTANTS = {
    "resolver keeps the old pattern (one pattern)": (RES, swap(RES_RX, RES_RX.replace(NEW_RX, OLD_RX)), UT, "test_one_pattern"),
    "resolver keeps the old pattern (real shapes)": (RES, swap(RES_RX, RES_RX.replace(NEW_RX, OLD_RX)), UT,
                                                     "test_the_real_shapes"),
    "lock side keeps the old pattern (one pattern)": (CHK, swap(CHK_RX, CHK_RX.replace(NEW_RX, OLD_RX)), UT,
                                                      "test_one_pattern"),
    "lock side keeps the old pattern (lock rows)": (CHK, swap(CHK_RX, CHK_RX.replace(NEW_RX, OLD_RX)), ULT,
                                                    "test_a_leading_underscore_passes"),
    "lock side keeps the old pattern (resolved entry fails lock_ok)": (CHK, swap(CHK_RX, CHK_RX.replace(NEW_RX, OLD_RX)),
                                                                       UT, "test_the_real_shapes"),
    "resolver lead too wide (- and . allowed)": (RES, swap(RES_RX, RES_RX.replace(NEW_RX, WIDE_RX)), UT, "test_still_refused"),
    "lock lead too wide (- and . allowed)": (CHK, swap(CHK_RX, CHK_RX.replace(NEW_RX, WIDE_RX)), ULT, "test_still_refused"),
    "resolver drops the .. rule": (RES, swap('bool(NAME_RE.fullmatch(name)) and ".." not in name',
                                             'bool(NAME_RE.fullmatch(name))'), UT, "test_still_refused"),
    "lock middle segments keep the old pattern": (CHK, swap(
        "if not all(LOCK_FILE_NAME_RE.fullmatch(x) for x in parts[2:-1]):",
        'if not all(re.fullmatch(r"' + OLD_RX + '", x) for x in parts[2:-1]):'), ULT, "test_a_leading_underscore_passes"),
    "resolver directory segments keep the old rule": (RES, swap(
        "if segs[-1] != name or not all(safe_name(x) for x in segs):",
        'if segs[-1] != name or not all(safe_name(x) for x in segs) or any(x.startswith("_") for x in segs[:-1]):'),
        UT, "test_the_real_shapes"),
    "symlink targets keep the old rule": (RES, swap(
        'target in ("", ".", "..") or not safe_name(target):',
        'target in ("", ".", "..") or not safe_name(target) or target.startswith("_"):'),
        UT, "test_a_link_to_an_underscore_name"),
    "skip line names the origin": (RES, swap(PRINT, PRINT.replace("{_clean(key)}", "{_clean(origin)}")), UT,
                                   "test_the_skip_line_names_the_key"),
    "skip line names the origin (one key)": (RES, swap(PRINT, PRINT.replace("{_clean(key)}", "{_clean(origin)}")), SYT,
                                             "test_the_real_shape"),
    "skip line deduplicated across keys": (RES, swap(PRINT, (
        '    seen = _check_link.__dict__.setdefault("seen", set())\n'
        '    if (rel, target) not in seen:\n'
        '        seen.add((rel, target))\n    ' + PRINT)), UT, "test_the_skip_line_names_the_key"),
    "skip line printed twice": (RES, swap(PRINT, PRINT + "\n" + PRINT), UT, "test_a_link_to_an_underscore_name"),
    # Item 12: empty GitLab apk files.
    "size 0 accepted everywhere": (CHK, swap(LOW, "    low = 0"), EFLT, "test_still_refused"),
    "size 0 refused for GitLab apk (lock rows)": (CHK, swap(LOW, "    low = 1"), EFLT, "test_an_empty_gitlab_file_passes"),
    "size 0 refused for GitLab apk (resolved entry)": (CHK, swap(LOW, "    low = 1"), EFT, "test_an_empty_aports_file"),
    "size 0 with any sha256": (CHK, swap('        if f["sha256"] != EMPTY_SHA256:', "        if False:"), EFLT,
                               "test_still_refused"),
    "size 0 with any sha512 upstream": (CHK, swap('        if up0.get("alg") == "sha512" and up0.get("value") != EMPTY_SHA512:',
                                                  "        if False:"), EFLT, "test_still_refused"),
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
print(f"\nU7d rework round 1 items 10 and 12 controls: {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
