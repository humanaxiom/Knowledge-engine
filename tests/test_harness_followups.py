"""Plan item harness-followups: carry-in fixes that keep the gates trustworthy.

Each test maps to a criterion in docs/requirements.md § platform-skeleton,
"PS-0 harness-followups". The hook cases (PS-0.4, PS-0.5) live in
tests/test_block_main_commit_hook.py next to the rest of the hook rule.
"""

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
TEST_SH = ROOT / "scripts" / "test.sh"
VERIFY_SH = ROOT / "scripts" / "verify.sh"

# Orchestrator ruling PS-Q1 (docs/handoffs/platform-skeleton.md): pin the
# image `ubuntu-latest` resolved to before the 2026-10-19 runner move.
PINNED_RUNNER = "ubuntu-24.04"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class CiWorkflowTest(unittest.TestCase):
    def test_ci_runner_pinned(self):
        # PS-0.1: every job's runs-on names a versioned image, never *-latest.
        ci = read(CI)
        runners = re.findall(r"^\s*runs-on:\s*(\S+)\s*$", ci, re.M)
        self.assertTrue(runners, "no runs-on in ci.yml")
        for runner in runners:
            with self.subTest(runner=runner):
                self.assertEqual(runner.strip("'\""), PINNED_RUNNER)
        self.assertNotRegex(ci, r"-latest\b", "a *-latest label is left in ci.yml")

    def test_ci_actions_pinned_to_sha(self):
        # PS-0.2: every `uses:` is a full 40-hex commit SHA with a version
        # comment, and actions/checkout is a v5 release. The SHA itself is
        # not asserted here: the developer reads it from the action's repo.
        ci = read(CI)
        uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(.*)$", ci, re.M)
        self.assertTrue(uses, "no uses: in ci.yml")
        checkout = []
        for line in uses:
            with self.subTest(uses=line):
                match = re.fullmatch(
                    r"([\w.-]+/[\w./-]+)@([0-9a-f]{40})\s+#\s*(v\d+(?:\.\d+)*)\s*", line)
                self.assertIsNotNone(match, "not pinned to a 40-hex SHA with a version comment")
                if match and match.group(1) == "actions/checkout":
                    checkout.append(match.group(3))
        self.assertTrue(checkout, "actions/checkout is not pinned in ci.yml")
        for version in checkout:
            with self.subTest(checkout=version):
                self.assertRegex(version, r"^v5(\.|$)")

    def test_ci_checkout_does_not_persist_credentials(self):
        # Security L20 (docs/evidence/harness-followups/security.md § 3),
        # orchestrator ruling rework 3: the checkout step sets
        # `with: persist-credentials: false`, so the GITHUB_TOKEN is not left
        # in the work tree's git config that the gates container bind-mounts.
        lines = read(CI).splitlines()
        starts = [i for i, line in enumerate(lines)
                  if re.match(r"^\s*-\s*uses:\s*actions/checkout@", line)]
        self.assertTrue(starts, "no actions/checkout step in ci.yml")
        for start in starts:
            dash = len(lines[start]) - len(lines[start].lstrip())
            step = []
            for line in lines[start + 1:]:
                if line.strip() and (len(line) - len(line.lstrip())) <= dash:
                    break
                step.append(line)
            body = "\n".join(step)
            with self.subTest(step=lines[start].strip()):
                with_block = re.search(r"^(\s*)with:\s*$((?:\n\1\s+.*)*)", body, re.M)
                self.assertIsNotNone(with_block, "checkout step has no with: block")
                self.assertRegex(with_block.group(2),
                                 r"(?m)^\s+persist-credentials:\s*false\s*(#.*)?$")


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class IntegrationRunsOnceTest(unittest.TestCase):
    """PS-0.3 (review N3; rework 1 B1, N1, N2; rework 2 B2, N6, N8):
    scripts/test.sh runs every unit test exactly once in both modes, at every
    depth under tests/, runs tests/integration once in full mode and not at
    all in fast mode, tolerates a helper package with no tests, fails loudly on
    a test directory at any depth that is not a package, and fails with a clear
    message when there are no top-level unit tests.

    The real scripts/test.sh is copied into a throwaway project whose test
    modules each append a label line to one counter file, so no real suite is
    needed. A fake `uv` first on PATH drops everything before the `python`
    argument and runs the rest with this interpreter (no network, no lock
    resolution). The repo's tests/__init__.py is copied too, so a fix placed
    there is also exercised.

    Counted modules (label: path):
      top:         tests/test_x.py         (top-level, test_* name)
      testfoo:     tests/testfoo.py        (unittest's default test*.py, not test_*)
      sub:         tests/unit/test_sub.py  (non-integration sub-package)
      deep:        tests/unit/deep/test_d.py (nested package, __init__ at each level)
      integration: tests/integration/test_counted.py"""

    COUNTED = (
        "import os\n"
        "import unittest\n"
        "class Counted(unittest.TestCase):\n"
        "    def test_counted(self):\n"
        "        with open(os.environ['KE_TEST_COUNTER'], 'a', encoding='utf-8') as f:\n"
        "            f.write({label!r} + '\\n')\n"
    )
    UNIT_LABELS = ("top", "testfoo", "sub", "deep")
    # Rework 1 (review B6): the fake uv logs every python invocation to
    # $KE_TEST_UV_LOG and treats `coverage combine`, `coverage report` and
    # `mypy` as no-ops, so test.sh needs no pyproject.toml guard to run in
    # this throwaway project. On `coverage combine` it also logs any planted
    # stale parallel data file still present (review B5).
    FAKE_UV = (
        "#!/bin/sh\n"
        "# Fake uv: skip to the first python argument and run it with the\n"
        "# test interpreter.\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in python|python3)\n"
        "    shift\n"
        "    [ -n \"${KE_TEST_UV_LOG:-}\" ] && echo \"python $*\" >> \"$KE_TEST_UV_LOG\"\n"
        "    case \"$1 $2 $3\" in\n"
        "      '-m coverage combine'*)\n"
        "        for f in .coverage.stale*; do\n"
        "          [ -e \"$f\" ] && echo \"stale-present $f\" >> \"$KE_TEST_UV_LOG\"\n"
        "        done\n"
        "        exit 0 ;;\n"
        "      '-m coverage report'*) exit 0 ;;\n"
        "    esac\n"
        "    case \"$1 $2\" in '-m mypy'*) exit 0 ;; esac\n"
        "    exec \"$KE_TEST_PYTHON\" \"$@\" ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        "echo 'fake uv: no python argument' >&2\n"
        "exit 2\n"
    )

    def write(self, rel: str, text: str = "") -> None:
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def counted(self, rel: str, label: str) -> None:
        self.write(rel, self.COUNTED.format(label=label))

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.project = self.root / "project"
        (self.project / "scripts").mkdir(parents=True)
        shutil.copyfile(TEST_SH, self.project / "scripts" / "test.sh")
        (self.project / "tests").mkdir()
        shutil.copyfile(ROOT / "tests" / "__init__.py", self.project / "tests" / "__init__.py")
        self.counted("tests/test_x.py", "top")
        self.counted("tests/testfoo.py", "testfoo")
        self.write("tests/unit/__init__.py")
        self.counted("tests/unit/test_sub.py", "sub")
        self.write("tests/unit/deep/__init__.py")
        self.counted("tests/unit/deep/test_d.py", "deep")
        self.write("tests/integration/__init__.py")
        self.counted("tests/integration/test_counted.py", "integration")
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        fake = self.bin_dir / "uv"
        fake.write_text(self.FAKE_UV, encoding="utf-8", newline="\n")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run_mode(self, mode: str):
        """Run test.sh <mode>; return (returncode, output, {label: runs})."""
        counter = self.root / f"counter-{mode}"
        if counter.exists():
            counter.unlink()
        env = dict(os.environ)
        env["PATH"] = str(self.bin_dir) + os.pathsep + env.get("PATH", "")
        env["KE_TEST_PYTHON"] = sys.executable
        env["KE_TEST_COUNTER"] = str(counter)
        self.uv_log = self.root / f"uv-{mode}.log"
        if self.uv_log.exists():
            self.uv_log.unlink()
        env["KE_TEST_UV_LOG"] = str(self.uv_log)
        result = subprocess.run(["bash", str(self.project / "scripts" / "test.sh"), mode],
                                cwd=self.project, env=env, capture_output=True, text=True)
        counts = {}
        if counter.exists():
            for line in counter.read_text(encoding="utf-8").splitlines():
                counts[line] = counts.get(line, 0) + 1
        return result.returncode, result.stdout + result.stderr, counts

    def runs(self, mode: str) -> dict:
        code, output, counts = self.run_mode(mode)
        self.assertEqual(code, 0, output)
        return counts

    def test_integration_tests_run_once(self):
        with self.subTest(mode="full"):
            self.assertEqual(self.runs("full").get("integration", 0), 1)
        with self.subTest(mode="fast"):
            self.assertEqual(self.runs("fast").get("integration", 0), 0)

    def test_unit_tests_run_once(self):
        # B1: a top-level test_*.py, a top-level test*.py (unittest's default
        # pattern) and a non-integration sub-package each run exactly once.
        for mode in ("fast", "full"):
            counts = self.runs(mode)
            for label in self.UNIT_LABELS:
                with self.subTest(mode=mode, label=label):
                    self.assertEqual(counts.get(label, 0), 1, counts)

    def test_helper_package_without_tests_passes(self):
        # N1: a helper package holding only __init__.py does not fail the
        # gate, and the unit tests still run once.
        self.write("tests/fixtures/__init__.py")
        for mode in ("fast", "full"):
            code, output, counts = self.run_mode(mode)
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output)
                for label in ("top", "sub"):
                    self.assertEqual(counts.get(label, 0), 1, counts)

    def test_test_dir_without_init_fails_loudly(self):
        # N2: a tests/<dir>/ with test_*.py but no __init__.py is not skipped
        # silently: the gate exits non-zero and names the directory.
        self.counted("tests/loose/test_loose.py", "loose")
        for mode in ("fast", "full"):
            code, output, _ = self.run_mode(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, "tests/loose skipped silently:\n" + output)
                self.assertIn("tests/loose", output)

    def test_package_with_only_nested_tests_runs_once(self):
        # B2 (review probe i): a package whose only test*.py sits in a nested
        # package is not skipped; the nested tests run exactly once.
        self.write("tests/stores/__init__.py")
        self.write("tests/stores/graph/__init__.py")
        self.counted("tests/stores/graph/test_graph.py", "nesteddeep")
        for mode in ("fast", "full"):
            counts = self.runs(mode)
            with self.subTest(mode=mode):
                self.assertEqual(counts.get("nesteddeep", 0), 1, counts)
                self.assertEqual(counts.get("deep", 0), 1, counts)

    def test_nested_dir_without_init_fails_loudly(self):
        # N6 (review probe j): the __init__.py check applies at every depth.
        # tests/unit is a package; tests/unit/loose2 is not.
        self.counted("tests/unit/loose2/test_l.py", "loose2")
        for mode in ("fast", "full"):
            code, output, _ = self.run_mode(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, "tests/unit/loose2 skipped silently:\n" + output)
                self.assertIn("tests/unit/loose2", output)

    def test_no_top_level_unit_tests_fails_clearly(self):
        # N8 (review probe d): with no tests/test*.py but a valid sub-package,
        # the gate fails with a clear message, not an ImportError from a
        # literal glob passed to unittest.
        (self.project / "tests" / "test_x.py").unlink()
        (self.project / "tests" / "testfoo.py").unlink()
        for mode in ("fast", "full"):
            code, output, _ = self.run_mode(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, output)
                self.assertIn("no top-level unit tests", output)
                self.assertNotIn("ImportError", output)

    def uv_calls(self) -> list[str]:
        if not self.uv_log.exists():
            return []
        return self.uv_log.read_text(encoding="utf-8").splitlines()

    def assert_quality_gates_ran(self, mode: str) -> list[str]:
        code, output, _ = self.run_mode(mode)
        self.assertEqual(code, 0, output)
        calls = self.uv_calls()
        last_unittest = max(i for i, c in enumerate(calls) if "-m unittest" in c)
        for step in ("-m coverage combine", "-m coverage report", "-m mypy"):
            matching = [i for i, c in enumerate(calls) if c.startswith(f"python {step}")]
            self.assertEqual(len(matching), 1, f"{step} ran {len(matching)} times: {calls}")
            self.assertGreater(matching[0], last_unittest, f"{step} ran before the tests")
        return calls

    def test_quality_gates_always_run(self):
        # Review B6: no silent skip. This project has no pyproject.toml; the
        # coverage and mypy steps must run anyway (here as fake-uv no-ops).
        self.assertFalse((self.project / "pyproject.toml").exists())
        for mode in ("fast", "full"):
            with self.subTest(mode=mode):
                self.assert_quality_gates_ran(mode)

    def test_quality_gates_run_with_pyproject(self):
        # Review B6, mutant T1 (`pyproject.tom`): with a pyproject.toml the
        # steps run too, whatever the guard spelling.
        self.write("pyproject.toml", '[project]\nname = "fixture"\nversion = "0"\n')
        for mode in ("fast", "full"):
            with self.subTest(mode=mode):
                self.assert_quality_gates_ran(mode)

    def test_stale_parallel_coverage_data_is_not_combined(self):
        # Review B5, reworked for PS-3.5 (the checkout is read-only in the
        # gates, so test.sh may not `rm` anything in it): a run that stopped
        # between `coverage run -p` and `combine` leaves parallel data files,
        # and the next run must not combine them. They now live beside
        # `[tool.coverage.run] data_file` (/tmp, a fresh tmpfs per container),
        # and test.sh clears them with `coverage erase`, which removes them only
        # because `parallel = true` is set (the real erase runs in
        # tests/test_gate_least_privilege.py, review B2). So: erase runs before the
        # first coverage run, data_file is under /tmp, and test.sh touches no file
        # in the checkout.
        import tomllib

        data_file = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")
                                  )["tool"]["coverage"]["run"]["data_file"]
        self.assertTrue(str(data_file).startswith("/tmp/"), data_file)
        shutil.copyfile(ROOT / "pyproject.toml", self.project / "pyproject.toml")
        for mode in ("fast", "full"):
            in_checkout = self.project / ".coverage.stale-host.pid1.x1y2z3"
            in_checkout.write_bytes(b"left alone: the checkout is read-only in the gates")
            with self.subTest(mode=mode):
                calls = self.assert_quality_gates_ran(mode)
                erase = calls.index("python -m coverage erase")
                first_run = min(i for i, c in enumerate(calls) if c.startswith("python -m coverage run"))
                self.assertLess(erase, first_run, "coverage erase must run before the first coverage run")
                self.assertTrue(in_checkout.exists(), "test.sh removed a file in the checkout")


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class VerifyRequiresTestsRunTest(unittest.TestCase):
    """PS-0.3 rework 2, B1 (review m1 mutant): inside the gates container,
    scripts/verify.sh fails unless scripts/test.sh's output has a
    `Ran N tests` line with N > 0. Deleting the top-level unittest run from
    test.sh then turns the gate red even though test.sh exits 0.

    The real scripts/verify.sh is copied into a throwaway project with a fake
    scripts/test.sh (and, for full, a fake scripts/smoke.sh). KE_IN_GATES=1
    stops verify.sh re-executing itself through docker. Like real unittest,
    the fake prints its `Ran` summary to stderr."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.project = self.root / "project"
        (self.project / "scripts").mkdir(parents=True)
        shutil.copyfile(VERIFY_SH, self.project / "scripts" / "verify.sh")
        self.script("smoke.sh", "echo 'fake smoke: ok'\nexit 0\n")
        # platform-stack-up B5 (architecture §2.2 Lint): the container half
        # also calls scripts/lint.sh; a passing stand-in keeps these cases
        # about the Ran/sentinel checks only.
        self.script("lint.sh", "echo 'fake lint: ok'\nexit 0\n")

    def script(self, name: str, body: str) -> None:
        path = self.project / "scripts" / name
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def fake_test_sh(self, summary: str, code: int = 0) -> None:
        body = "echo 'fake test.sh running'\n"
        for line in summary.splitlines():
            body += f"echo {shlex.quote(line)} >&2\n"
        body += f"exit {code}\n"
        self.script("test.sh", body)

    def verify(self, mode: str):
        env = dict(os.environ)
        env["KE_IN_GATES"] = "1"
        result = subprocess.run(["bash", str(self.project / "scripts" / "verify.sh"), mode],
                                cwd=self.project, env=env, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    # Review B3 / orchestrator ruling rework 3: verify.sh also requires the
    # sentinel line from tests/test_sentinel.py, as unittest -v prints it.
    SENTINEL = ("test_top_level_unit_suite_ran "
                "(tests.test_sentinel.TopLevelSuiteSentinelTest.test_top_level_unit_suite_ran)"
                " ... ok")

    def test_no_ran_line_fails(self):
        # m1 shape: test.sh exits 0 having run no unittest at all. The
        # sentinel is present so the Ran > 0 check is what must catch it.
        self.fake_test_sh(self.SENTINEL)
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, output)
                self.assertNotIn(": PASS ==", output)

    def test_ran_zero_tests_fails(self):
        self.fake_test_sh(self.SENTINEL + "\nRan 0 tests in 0.000s\n\nOK")
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, output)
                self.assertNotIn(": PASS ==", output)

    def test_ran_without_sentinel_fails(self):
        # Review B3, mutants m4/m7: the top-level run line is deleted but
        # another test package still runs, so `Ran 1 test` / OK appears
        # without the sentinel. verify must fail in both modes.
        self.fake_test_sh("test_other (tests.unit.test_x.T.test_other) ... ok\n"
                          "Ran 1 test in 0.001s\n\nOK")
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, output)
                self.assertNotIn(": PASS ==", output)

    # Review N17 / security I1, orchestrator ruling rework 4: the sentinel
    # check is anchored to the full line SENTINEL, so a same-named test in
    # another module or a skip reason that quotes it cannot stand in for it.

    @staticmethod
    def verify_sentinel_pattern() -> str:
        # The single-quoted ERE in scripts/verify.sh that names the sentinel.
        patterns = re.findall(r"'(\^[^']*test_top_level_unit_suite_ran[^']*)'",
                              read(VERIFY_SH))
        if len(patterns) != 1:
            raise AssertionError(f"expected one sentinel pattern in verify.sh, got {patterns!r}")
        return patterns[0]

    def test_sentinel_line_is_the_exact_full_line(self):
        # Review N21, rework 5: build the line unittest -v actually prints for
        # the real sentinel test from its live id, and check that verify.sh's
        # anchored pattern matches it. Renaming the sentinel module, class or
        # method without updating verify.sh fails here.
        from tests import test_sentinel
        method = "test_top_level_unit_suite_ran"
        test_id = test_sentinel.TopLevelSuiteSentinelTest(method).id()
        expected = f"{method} ({test_id}) ... ok"
        self.assertEqual(self.SENTINEL, expected,
                         "the SENTINEL the fakes print drifted from the real test id")
        pattern = self.verify_sentinel_pattern()
        self.assertTrue(pattern.startswith("^"), pattern)
        self.assertTrue(re.search(r"\$$", pattern), f"pattern not end-anchored: {pattern}")
        self.assertIsNotNone(re.search(pattern, expected),
                             f"verify.sh pattern {pattern!r} does not match {expected!r}")
        # Whole-line: a longer line that merely contains it must not match.
        self.assertIsNone(re.search(pattern, "x" + expected))
        self.assertIsNone(re.search(pattern, expected + " extra"))

    def test_sentinel_followed_by_large_output_passes(self):
        # Review N19, rework 5: in the real test.sh, sub-package and
        # integration suites print after the top-level run. More than 200 KB
        # after the sentinel must not false-FAIL the sentinel check (a
        # `tr | grep -q` pipeline under pipefail dies with SIGPIPE). Repeated
        # to catch the race.
        body = ("echo 'fake test.sh running'\n"
                f"echo {shlex.quote(self.SENTINEL)} >&2\n"
                "echo 'Ran 1 test in 0.001s' >&2\n"
                "echo '' >&2\n"
                "echo 'OK' >&2\n"
                # 4000 lines x ~80 bytes = ~320 KB of later sub-package output.
                "yes 'sub-package output line padding padding padding padding padding padding' "
                "| head -n 4000 >&2\n"
                "exit 0\n")
        self.script("test.sh", body)
        for attempt in range(5):
            for mode in ("fast", "full"):
                code, output = self.verify(mode)
                with self.subTest(attempt=attempt, mode=mode):
                    self.assertGreater(len(output), 200 * 1024)
                    self.assertEqual(code, 0, output[-2000:])
                    self.assertIn(f"== verify {mode}: PASS ==", output)

    def test_sentinel_name_in_other_module_fails(self):
        # Security I1 case 1 / review N17: a sub-package test with the same
        # name reports ok, the top-level suite did not run.
        self.fake_test_sh("test_top_level_unit_suite_ran "
                          "(tests.unit.test_x.T.test_top_level_unit_suite_ran) ... ok\n"
                          "Ran 1 test in 0.001s\n\nOK")
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, output)
                self.assertNotIn(": PASS ==", output)

    def test_sentinel_text_in_skip_reason_fails(self):
        # Security I1 case 2: a skip reason carries the sentinel text, or the
        # sentinel itself is skipped with a reason ending in " ok".
        shapes = {
            "other test, reason quotes sentinel":
                "test_other (tests.unit.test_x.T.test_other) ... skipped '"
                + self.SENTINEL + "'",
            "sentinel skipped, reason has ok":
                self.SENTINEL[:-len(" ... ok")] + " ... skipped 'not ok'",
        }
        for shape, line in shapes.items():
            self.fake_test_sh(line + "\nRan 1 test in 0.001s\n\nOK (skipped=1)")
            for mode in ("fast", "full"):
                code, output = self.verify(mode)
                with self.subTest(shape=shape, mode=mode):
                    self.assertNotEqual(code, 0, output)
                    self.assertNotIn(": PASS ==", output)

    def test_sentinel_with_ran_passes(self):
        # Review B3 control: the sentinel line plus `Ran 1 test` / OK passes.
        self.fake_test_sh(self.SENTINEL + "\nRan 1 test in 0.001s\n\nOK")
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output)
                self.assertIn(f"== verify {mode}: PASS ==", output)

    def test_ran_some_tests_passes(self):
        # Control: a real-looking run passes, and test.sh's output is still
        # shown to the caller.
        self.fake_test_sh(self.SENTINEL + "\nRan 3 tests in 0.001s\n\nOK")
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output)
                self.assertIn("Ran 3 tests", output)
                self.assertIn(f"== verify {mode}: PASS ==", output)
                if mode == "full":
                    self.assertIn("fake smoke: ok", output)

    def test_failing_test_sh_still_fails(self):
        # Control, fast and full (review N9): a failing run fails even though
        # it reports tests ran and prints the sentinel.
        self.fake_test_sh(self.SENTINEL + "\nRan 3 tests in 0.001s\n\nFAILED (failures=1)",
                          code=1)
        for mode in ("fast", "full"):
            code, output = self.verify(mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(code, 0, output)
                self.assertNotIn(": PASS ==", output)

    def test_failing_smoke_fails_full(self):
        # Review N9: a passing test.sh followed by a failing smoke.sh fails
        # verify full.
        self.fake_test_sh(self.SENTINEL + "\nRan 3 tests in 0.001s\n\nOK")
        self.script("smoke.sh", "echo 'fake smoke: FAIL'\nexit 3\n")
        code, output = self.verify("full")
        self.assertNotEqual(code, 0, output)
        self.assertIn("fake smoke: FAIL", output)
        self.assertNotIn(": PASS ==", output)


if __name__ == "__main__":
    unittest.main()
