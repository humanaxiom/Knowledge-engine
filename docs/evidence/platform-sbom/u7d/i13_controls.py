"""platform-sbom U7d rework round 1, item 13 RED: controls for the generated
lock's skip in the no-hardcoded scan (tests/test_engine_hardcoded.py
ScannerContractTest.test_the_generated_lock_is_skipped and the repository
scan with docker/sources.lock.json in the tree).

Never writes the repository. Each row loads a scanner text (the target
u7d/i13-target-hardcoded_scan.py, or with `--base repo` the repository's
tests/hardcoded_scan.py; the SAVED pre-13 scanner u7d/i13-pre-hardcoded_scan.py
as the baseline, never the repository's current file; or a mutant of the
target) from a temp file as
`tests.hardcoded_scan` and runs real test methods against it. Exit 1 if any
row is unexpected.

Usage (in the gates image, from the repo root, with the lock in the tree):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7d/i13_controls.py [--base repo]
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

import tests  # noqa: E402
from tests import test_engine_hardcoded as teh  # noqa: E402

HERE = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="u7d-i13-controls-"))
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGET = (REPO / "tests" / "hardcoded_scan.py" if BASE_REPO else HERE / "i13-target-hardcoded_scan.py").read_text(
    encoding="utf-8")
# Baselines come from SAVED copies, never from the repository's current files
# (attempt 1 read the repo after GREEN: u7d/i13-green-controls-attempt1.txt).
BASELINE = (HERE / "i13-pre-hardcoded_scan.py").read_text(encoding="utf-8")  # tests/hardcoded_scan.py at 86f7831
rows: list[tuple[str, str, str, bool]] = []
assert (REPO / "docker" / "sources.lock.json").is_file(), "run with the lock in the tree"


def run_test(cls: type, method: str, text: str) -> list[str]:
    path = WORK / f"scan-{abs(hash(text))}" / "hardcoded_scan.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(f"i13_scan_{path.parent.name.replace('-', '_')}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses reads the module's namespace
    spec.loader.exec_module(mod)
    result = unittest.TestResult()
    with mock.patch.dict(sys.modules, {"tests.hardcoded_scan": mod}), mock.patch.object(tests, "hardcoded_scan", mod,
                                                                                        create=True):
        unittest.TestSuite([cls(method)]).run(result)
    return [f"{method}: " + str(b[1]).strip().splitlines()[-1] for b in result.failures + result.errors]


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    ok = bool(problems) == must_fail
    rows.append((group, name, "must fail" if must_fail else "must pass", ok))
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<72} {'must fail' if must_fail else 'must pass'} | "
          f"{problems[0][:120] if problems else 'no problem'}", flush=True)


def swap(*pairs: str) -> Callable[[str], str]:
    def change(t: str) -> str:
        for old, new in zip(pairs[::2], pairs[1::2]):
            if t.count(old) != 1:
                raise AssertionError(f"mutant anchor found {t.count(old)} times: {old[:70]!r}")
            t = t.replace(old, new, 1)
        return t
    return change


SKIP = (teh.ScannerContractTest, "test_the_generated_lock_is_skipped")
REPO_SCAN = (teh.RepositoryScanTest, "test_no_hardcoded_ports")
ALL = [(c, m) for c in (teh.ScannerContractTest, teh.RepositoryScanTest, teh.ScannerWideningTest)
       for m in unittest.defaultTestLoader.getTestCaseNames(c)]

row("target", f"TARGET: all {len(ALL)} hardcoded-scan tests", False, [p for c, m in ALL for p in run_test(c, m, TARGET)])
row("baseline", "repository scanner: test_the_generated_lock_is_skipped", True, run_test(*SKIP, BASELINE))
row("baseline", "repository scanner: test_no_hardcoded_ports (lock in the tree)", True, run_test(*REPO_SCAN, BASELINE))

ENTRY = '"config/verify.env", "docker/sources.lock.json"}'
LOOP = "        for number, line in enumerate(text.splitlines(), start=1):\n"
MUTANTS = {
    "a line exemption instead (size lines only)": (swap(
        ENTRY, '"config/verify.env"}',
        LOOP, LOOP + '            if path == "docker/sources.lock.json" and re.fullmatch(r\'\\s*"size": \\d+,?\', line):\n'
                     "                continue\n"), SKIP),
    "the skip widened to docker/*.json": (swap(
        "    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)",
        '    return (path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)\n'
        '            or bool(re.fullmatch(r"docker/[^/]*\\.json", path)))'), SKIP),
    "the skip by suffix (sources.lock.json anywhere)": (swap(
        "    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)",
        '    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES) or path.endswith("sources.lock.json")'),
        SKIP),
    "the skip by prefix (docker/sources.lock.json*)": (swap(
        "    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)",
        '    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES + ("docker/sources.lock.json",))'), SKIP),
    "the skip dropped (contract row)": (swap(ENTRY, '"config/verify.env"}'), SKIP),
    "the skip dropped (repository scan)": (swap(ENTRY, '"config/verify.env"}'), REPO_SCAN),
    "the reason dropped": (swap("Reason: generated lock: sizes and hashes, PSC-15; checked by test_sources_lock_committed.py",
                                "Reason: generated."), SKIP),
    "Python rule 2 lost for the skip (all .py skipped)": (swap(
        "    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)",
        '    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES) or path.startswith("engine/")'), SKIP),
}
for name, (m, (cls, method)) in MUTANTS.items():
    try:
        text = m(TARGET)
    except AssertionError as exc:
        row("mutant", name, True, [])
        print(f"    anchor: {exc}")
        continue
    row("mutant", f"{name} -> {method}", True, run_test(cls, method, text))

# Review R1-N1 (orchestrator, item-13 RED): the APKBUILD keeps size > 0 under item 12.
from tests import test_sources_lock as tsl  # noqa: E402

CHK_TARGET = (REPO / "scripts" / "sbom_check.py" if BASE_REPO else HERE / "i13-target-sbom_check.py").read_text(
    encoding="utf-8")
CHK_BASE = (HERE / "r1-target-sbom_check.py").read_text(encoding="utf-8")  # SAVED: rounds 1, 10 and 12, pre-13


def run_lock_test(method: str, text: str) -> list[str]:
    path = WORK / f"chk-{abs(hash(text))}" / "sbom_check.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(f"i13_chk_{path.parent.name.replace('-', '_')}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    result = unittest.TestResult()
    with mock.patch.object(tsl, "load_sbom_check", lambda m=mod: m), \
            mock.patch.object(tsl, "fn", lambda name, m=mod: getattr(m, name)):
        unittest.TestSuite([tsl.ReworkR1U7dEmptyFileLockTest(method)]).run(result)
    return [f"{method}: " + str(b[1]).strip().splitlines()[-1] for b in result.failures + result.errors]


EMPTY_METHODS = unittest.defaultTestLoader.getTestCaseNames(tsl.ReworkR1U7dEmptyFileLockTest)
row("target", f"sbom_check target: all {len(EMPTY_METHODS)} ReworkR1U7dEmptyFileLockTest methods", False,
    [p for m in EMPTY_METHODS for p in run_lock_test(m, CHK_TARGET)])
row("baseline", "repository sbom_check: test_an_empty_apkbuild_fails", True,
    run_lock_test("test_an_empty_apkbuild_fails", CHK_BASE))
try:
    dropped = swap('        if name == "APKBUILD":  # review R1-N1: an empty APKBUILD has no pkgver\n'
                   '            p.append(f"{where}: APKBUILD: size 0")\n', "")(CHK_TARGET)
    row("mutant", "the APKBUILD clause dropped -> test_an_empty_apkbuild_fails", True,
        run_lock_test("test_an_empty_apkbuild_fails", dropped))
except AssertionError as exc:
    row("mutant", "the APKBUILD clause dropped", True, [])
    print(f"    anchor: {exc}")

bad = [r for r in rows if not r[3]]
print(f"\nU7d item 13 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, {sum(r[2] == 'must fail' for r in rows)} must-fail, "
      f"{sum(r[2] == 'must pass' for r in rows)} must-pass, {len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
