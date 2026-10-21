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
PROBE_SH = ROOT / "scripts" / "resource_probe.sh"

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
      integration: tests/integration/test_counted.py

    ci-speed (architecture §2.2.1-r3; the §2.2.1 pool is withdrawn): with
    $KE_TEST_PIDS set, a counted module also writes `<label> <pid>` there.
    The real scripts/resource_probe.sh is copied in too, once it exists.

    Coverage knobs of the fake uv. A coverage run's *label* is the suffix of
    its `--data-file=<dir>/<name>.<label>`: `toplevel`, `tests.<pkg>` or
    `tests.integration` (§2.2.1-r3 decision 3).
    - `coverage combine` is real (the fake logs `combine-dir <arg>` for any
      directory argument, then runs it), so a file combine does not consume
      stays on disk, as in the gate. `coverage report` and mypy stay no-ops.
    - $KE_TEST_MARK_COMBINE=1: the fake prints `fake-uv: coverage combine` to
      stderr just before combine, so its place shows in the merged output.
    - $KE_TEST_NODATA_LABEL: the coverage run with that label drops
      `-m coverage run ...` and runs `-m unittest ...` directly: its tests
      run and print `Ran`, but it leaves no coverage data.
    - $KE_TEST_DATA_LOG=1: each `coverage run --data-file=X` runs to the end
      and the fake logs `data-written <file>` for every X.* it left.
    - $KE_TEST_BADDATA_LABEL: after the coverage run with that label, its
      data file(s) X.* are overwritten with bytes that are not a coverage
      database (logged `data-corrupted <file>`). Real combine cannot read
      them and leaves them on disk, exit 0 (coverage 7.16).
    - $KE_TEST_LOOKUP=empty|fail: any python call that is not coverage
      erase/run/combine/report, mypy or unittest (that is, the data_file
      lookup) prints nothing and exits 0, or exits 1 (logged
      `lookup-intercepted`)."""

    COUNTED = (
        "import os\n"
        "import unittest\n"
        "class Counted(unittest.TestCase):\n"
        "    def test_counted(self):\n"
        "        with open(os.environ['KE_TEST_COUNTER'], 'a', encoding='utf-8') as f:\n"
        "            f.write({label!r} + '\\n')\n"
        "        pids = os.environ.get('KE_TEST_PIDS')\n"
        "        if pids:\n"
        "            with open(pids, 'a', encoding='utf-8') as f:\n"
        "                f.write({label!r} + ' ' + str(os.getpid()) + '\\n')\n"
    )
    UNIT_LABELS = ("top", "testfoo", "sub", "deep")
    # Rework 1 (review B6): the fake uv logs every python invocation to
    # $KE_TEST_UV_LOG and treats `coverage report` and `mypy` as no-ops, so
    # test.sh needs no pyproject.toml guard to run in this throwaway project.
    # On `coverage combine` it also logs any planted stale parallel data file
    # still present (review B5). ci-speed rework round 1 (CS-4, §2.2.1
    # decision 5): `coverage combine` was a no-op too; it now runs for real,
    # because test.sh must fail on any data file combine leaves behind, and a
    # no-op combine would leave all of them.
    FAKE_UV = (
        "#!/bin/sh\n"
        "# Fake uv: skip to the first python argument and run it with the\n"
        "# test interpreter.\n"
        "uvlog=\"${KE_TEST_UV_LOG:-/dev/null}\"\n"
        "data_file_arg() {\n"
        "  next=\n"
        "  for b in \"$@\"; do\n"
        "    if [ -n \"$next\" ]; then echo \"$b\"; return; fi\n"
        "    case \"$b\" in --data-file=*) echo \"${b#--data-file=}\"; return ;; --data-file) next=1 ;; esac\n"
        "  done\n"
        "}\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in python|python3)\n"
        "    shift\n"
        "    [ -n \"${KE_TEST_UV_LOG:-}\" ] && echo \"python $*\" >> \"$KE_TEST_UV_LOG\"\n"
        "    if [ -n \"${KE_TEST_LOOKUP:-}\" ]; then\n"
        "      case \"$1 $2 $3\" in\n"
        "        '-m coverage erase'*|'-m coverage run'*|'-m coverage combine'*|'-m coverage report'*|'-m mypy'*|'-m unittest'*) ;;\n"
        "        *) echo \"lookup-intercepted $KE_TEST_LOOKUP\" >> \"$uvlog\"\n"
        "           [ \"$KE_TEST_LOOKUP\" = fail ] && exit 1\n"
        "           exit 0 ;;\n"
        "      esac\n"
        "    fi\n"
        "    if [ -n \"${KE_TEST_NODATA_LABEL:-}\" ] && [ \"$1 $2 $3\" = '-m coverage run' ]; then\n"
        "      case \"$(data_file_arg \"$@\")\" in *.\"$KE_TEST_NODATA_LABEL\")\n"
        "        while [ $# -gt 1 ] && ! { [ \"$1\" = -m ] && [ \"$2\" = unittest ]; }; do shift; done\n"
        "        echo \"nodata-run $KE_TEST_NODATA_LABEL\" >> \"$uvlog\"\n"
        "        [ \"$1 $2\" = '-m unittest' ] && exec \"$KE_TEST_PYTHON\" \"$@\" ;;\n"
        "      esac\n"
        "    fi\n"
        "    if [ \"$1 $2 $3\" = '-m coverage run' ] && { [ -n \"${KE_TEST_DATA_LOG:-}\" ] || [ -n \"${KE_TEST_BADDATA_LABEL:-}\" ]; }; then\n"
        "      df=\"$(data_file_arg \"$@\")\"\n"
        "      bad=\n"
        "      case \"$df\" in *.\"${KE_TEST_BADDATA_LABEL:-//none//}\") bad=1 ;; esac\n"
        "      if [ -n \"$df\" ]; then\n"
        "        \"$KE_TEST_PYTHON\" \"$@\"\n"
        "        rc=$?\n"
        "        for f in \"$df\".*; do\n"
        "          [ -f \"$f\" ] || continue\n"
        "          echo \"data-written $f\" >> \"$uvlog\"\n"
        "          if [ -n \"$bad\" ]; then\n"
        "            printf 'not a coverage database\\n' > \"$f\"\n"
        "            echo \"data-corrupted $f\" >> \"$uvlog\"\n"
        "          fi\n"
        "        done\n"
        "        exit \"$rc\"\n"
        "      fi\n"
        "    fi\n"
        "    case \"$1 $2 $3\" in\n"
        "      '-m coverage combine'*)\n"
        "        [ -n \"${KE_TEST_MARK_COMBINE:-}\" ] && echo 'fake-uv: coverage combine' >&2\n"
        "        for f in .coverage.stale*; do\n"
        "          [ -e \"$f\" ] && echo \"stale-present $f\" >> \"$KE_TEST_UV_LOG\"\n"
        "        done\n"
        "        n=0\n"
        "        for a in \"$@\"; do\n"
        "          n=$((n + 1))\n"
        "          [ \"$n\" -le 3 ] && continue\n"
        "          case \"$a\" in -*) ;; *) [ -d \"$a\" ] && echo \"combine-dir $a\" >> \"$uvlog\" ;; esac\n"
        "        done\n"
        "        exec \"$KE_TEST_PYTHON\" \"$@\" ;;\n"
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
        # ci-speed §2.2.1-r3 decision 4: test.sh runs the real probe by its
        # repo path, so the copy carries it once it exists.
        if PROBE_SH.is_file():
            shutil.copyfile(PROBE_SH, self.project / "scripts" / "resource_probe.sh")

    def base_env(self, counter: Path, extra_env: dict | None = None) -> dict:
        env = dict(os.environ)
        env["PATH"] = str(self.bin_dir) + os.pathsep + env.get("PATH", "")
        env["KE_TEST_PYTHON"] = sys.executable
        env["KE_TEST_COUNTER"] = str(counter)
        env["KE_TEST_UV_LOG"] = str(self.uv_log)
        env.update(extra_env or {})
        return env

    def run_mode(self, mode: str, extra_env: dict | None = None, merged: bool = False,
                 script: str = "test.sh"):
        """Run scripts/<script> <mode>; return (returncode, output, {label: runs}).

        merged=True sends stderr into the stdout pipe, so the output keeps the
        order in which lines were written (ci-speed ordering checks)."""
        counter = self.root / f"counter-{mode}"
        if counter.exists():
            counter.unlink()
        self.uv_log = self.root / f"uv-{mode}.log"
        if self.uv_log.exists():
            self.uv_log.unlink()
        env = self.base_env(counter, extra_env)
        result = subprocess.run(["bash", str(self.project / "scripts" / script), mode],
                                cwd=self.project, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if merged else subprocess.PIPE)
        counts = {}
        if counter.exists():
            for line in counter.read_text(encoding="utf-8").splitlines():
                counts[line] = counts.get(line, 0) + 1
        return result.returncode, result.stdout + (result.stderr or ""), counts

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

    def test_coverage_erase_precedes_first_run_and_spares_checkout(self):
        # Formerly test_stale_parallel_coverage_data_is_not_combined (renamed,
        # review-l5-r1 n4: that stale data is not combined is proven by
        # test_coverage_erase_removes_stale_parallel_data in
        # tests/test_gate_least_privilege.py). Review B5, reworked for PS-3.5 (the checkout is read-only in the
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
        # ci-speed (§2.2.1 decision 6, CS-5): the copy points data_file (and so
        # every parallel `.coverage.*` file beside it) inside this test's own
        # temp root, so its nested `coverage erase` and `coverage run -p` never
        # touch the gate's data beside the real data_file.
        own_data_file = (self.root / ".coverage").as_posix()
        self.assertNotIn("'", own_data_file)
        real_line = f'data_file = "{data_file}"'
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(pyproject.count(real_line), 1, real_line)
        self.write("pyproject.toml", pyproject.replace(real_line, f"data_file = '{own_data_file}'"))
        copied = tomllib.loads((self.project / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(copied["tool"]["coverage"]["run"]["data_file"], own_data_file)
        self.assertTrue(copied["tool"]["coverage"]["run"]["parallel"])
        for mode in ("fast", "full"):
            in_checkout = self.project / ".coverage.stale-host.pid1.x1y2z3"
            in_checkout.write_bytes(b"left alone: the checkout is read-only in the gates")
            with self.subTest(mode=mode):
                calls = self.assert_quality_gates_ran(mode)
                erase = calls.index("python -m coverage erase")
                first_run = min(i for i, c in enumerate(calls) if c.startswith("python -m coverage run"))
                self.assertLess(erase, first_run, "coverage erase must run before the first coverage run")
                self.assertTrue(in_checkout.exists(), "test.sh removed a file in the checkout")

    # ---- ci-speed (architecture §2.2.1, docs/handoffs/ci-speed.md) ----------

    def test_nested_test_sh_leaves_gate_coverage_data_alone(self):
        # §2.2.1 decision 6 (precondition): the nested test.sh in
        # test_coverage_erase_precedes_first_run_and_spares_checkout runs with
        # a copy of the real pyproject.toml. Its `coverage erase` must not
        # delete the gate's own parallel data beside the real data_file
        # (experiments/coverage-erase-probe.txt: the gate's pid44 file went).
        # That erase would drop the gate's data of runs that already finished
        # (kept under §2.2.1-r3 decision 7). A uniquely named file stands in
        # for that data; the
        # test that runs the nested test.sh is run here as it is, so the guard
        # holds whatever shape its fix takes.
        import tomllib
        import uuid

        data_file = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")
                                  )["tool"]["coverage"]["run"]["data_file"]
        planted = Path(f"{data_file}.ke-ci-speed-planted.{uuid.uuid4().hex}")
        planted.write_bytes(b"stands in for the gate's own coverage data")
        self.addCleanup(planted.unlink, missing_ok=True)
        nested = unittest.TestResult()
        type(self)("test_coverage_erase_precedes_first_run_and_spares_checkout").run(nested)
        self.assertEqual(nested.testsRun, 1)
        self.assertTrue(nested.wasSuccessful(), nested.failures + nested.errors)
        self.assertTrue(planted.exists(),
                        f"a nested test.sh deleted {planted}, a file beside the gate's "
                        f"data_file {data_file}")

    # ---- ci-speed rework 3 (architecture §2.2.1-r3; the §2.2.1 pool is
    # withdrawn, human ruling 2026-10-21). One top-level coverage process
    # (CS-10), fail-closed coverage per run label (CS-4), the resource probe
    # lines (CS-11). ----------------------------------------------------------

    def clear_coverage_data(self) -> None:
        """Without a pyproject `parallel = true`, test.sh's `coverage erase`
        keeps parallel files, so a failed earlier mode's data would carry
        over into the next mode's run."""
        for path in self.project.glob(".coverage*"):
            path.unlink()

    @staticmethod
    def error_lines(output: str, *words: str) -> list[str]:
        """test.sh's own failure lines (`error: ...`) that hold every word."""
        return [line for line in output.splitlines()
                if line.startswith("error:") and all(w in line for w in words)]

    def coverage_runs(self) -> list[str]:
        """The `python -m coverage run ...` calls of the last run, in order."""
        return [c for c in self.uv_calls() if c.startswith("python -m coverage run")]

    @staticmethod
    def label_of(call: str) -> str | None:
        """A coverage run's label: what follows `<name>.` in its
        `--data-file=<dir>/<name>.<label>` (<name> is `.coverage` in every
        throwaway project here)."""
        match = re.search(r"--data-file[= ](\S+)", call)
        if not match:
            return None
        name = match.group(1).replace("\\", "/").rsplit("/", 1)[-1]
        return name[len(".coverage."):] if name.startswith(".coverage.") else None

    def glob_order(self) -> list[str]:
        """The top-level modules in the order test.sh's glob lists them: the
        same bash glob, in the same environment."""
        listing = subprocess.run(
            ["bash", "-c", "shopt -s nullglob; for f in tests/test*.py; do m=\"${f%.py}\"; "
                           "echo \"${m//\\//.}\"; done"],
            cwd=self.project, env=self.base_env(self.root / "unused"), text=True,
            stdout=subprocess.PIPE, check=True)
        return listing.stdout.split()

    # The labels of every coverage run in each mode, in run order.
    LABELS = {"fast": ["toplevel", "tests.unit"],
              "full": ["toplevel", "tests.unit", "tests.integration"]}

    def test_top_level_modules_run_in_one_process(self):
        # CS-10 / §2.2.1-r3 decision 2. Replaces
        # test_top_level_modules_run_in_separate_processes (§2.2.1 decision 1,
        # withdrawn): every top-level module runs, each exactly once, in ONE
        # coverage process whose data file label is `toplevel`, with the
        # modules in glob order. The sub-package and integration runs follow
        # with their own labels.
        self.counted("tests/test_y.py", "top2")
        top_labels = ("top", "testfoo", "top2")
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            pids_file = self.root / f"pids-{mode}"
            code, output, counts = self.run_mode(mode, {"KE_TEST_PIDS": str(pids_file)})
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output)
                pids: dict[str, list[str]] = {}
                for line in pids_file.read_text(encoding="utf-8").splitlines():
                    label, pid = line.split()
                    pids.setdefault(label, []).append(pid)
                for label in top_labels:
                    self.assertEqual(counts.get(label, 0), 1, counts)
                    self.assertEqual(len(pids.get(label, [])), 1, pids)
                top = {label: pids[label][0] for label in top_labels}
                self.assertEqual(len(set(top.values())), 1,
                                 f"top-level modules ran in more than one process: {top}")
                runs = self.coverage_runs()
                self.assertEqual([self.label_of(c) for c in runs], self.LABELS[mode], runs)
                modules = [a for a in runs[0].split("-m unittest", 1)[-1].split()
                           if a.startswith("tests.")]
                self.assertEqual(modules, self.glob_order(), runs[0])

    def test_top_level_run_has_durations_10_and_no_other_run_does(self):
        # CS-10 / §2.2.1-r3 decision 5 (adapted from
        # test_unit_pool_runs_each_module_with_durations_10): the one
        # top-level run is `unittest -v --durations 10`; the sub-package and
        # integration runs do not get it.
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, _ = self.run_mode(mode)
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output)
                runs = self.coverage_runs()
                top = [c for c in runs if self.label_of(c) == "toplevel"]
                self.assertEqual(len(top), 1, runs)
                self.assertRegex(top[0], r"-m unittest -v --durations[ =]10 ")
                for call in runs:
                    if call is not top[0]:
                        self.assertNotIn("--durations", call)

    RESOURCES = re.compile(r"^resources: phase=(\S+) ")

    def resource_lines(self, lines: list[str]) -> list[tuple[int, str]]:
        found = []
        for i, line in enumerate(lines):
            match = self.RESOURCES.match(line)
            if match:
                found.append((i, match.group(1)))
        return found

    def assert_probe_line(self, line: str) -> None:
        from tests.test_resource_probe import KEYS, VALUE

        pairs = [p.split("=", 1) for p in line[len("resources: "):].split(" ")]
        self.assertEqual([p[0] for p in pairs], list(KEYS), line)
        for _, value in pairs[1:]:
            self.assertRegex(value, VALUE, line)

    def test_resource_lines_bracket_the_unit_stage(self):
        # CS-11 / §2.2.1-r3 decision 4, first failing test 4. One
        # `resources: phase=start` line comes before the first top-level
        # output; one `phase=end` line comes after the last sub-package run,
        # before the integration run in full and before combine in fast. When
        # a unit run fails the end line still prints, test.sh exits non-zero
        # and no later run starts (CS-10).
        self.assertTrue(PROBE_SH.is_file(), "scripts/resource_probe.sh does not exist")
        env = {"KE_TEST_MARK_COMBINE": "1"}
        combine_mark = "fake-uv: coverage combine"
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, _ = self.run_mode(mode, env, merged=True)
            with self.subTest(mode=mode, run="all pass"):
                self.assertEqual(code, 0, output)
                lines = output.splitlines()
                found = self.resource_lines(lines)
                self.assertEqual([phase for _, phase in found], ["start", "end"], output)
                (start, _), (end, _) = found
                for i, _ in found:
                    self.assert_probe_line(lines[i])
                first_top = min(i for i, line in enumerate(lines)
                                if "(tests.test_x." in line or "(tests.testfoo." in line)
                self.assertLess(start, first_top, "phase=start is not before the top-level run")
                last_sub = max(i for i, line in enumerate(lines) if "(tests.unit." in line)
                self.assertGreater(end, last_sub, "phase=end is not after the last sub-package run")
                combine = [i for i, line in enumerate(lines) if line == combine_mark]
                self.assertEqual(len(combine), 1, output)
                self.assertLess(end, combine[0], "phase=end is not before combine")
                if mode == "full":
                    first_it = min(i for i, line in enumerate(lines)
                                   if "(tests.integration." in line)
                    self.assertLess(end, first_it, "phase=end is not before the integration run")
        failing = {"top-level run fails": ("tests/test_bad.py", "tests.test_bad",
                                           ("sub", "deep", "integration")),
                   "sub-package run fails": ("tests/unit/test_bad.py", "tests.unit.test_bad",
                                             ("integration",))}
        for case, (rel, module, not_started) in failing.items():
            self.write(rel, self.FAILING)
            for mode in ("fast", "full"):
                self.clear_coverage_data()
                code, output, counts = self.run_mode(mode, env, merged=True)
                with self.subTest(mode=mode, run=case):
                    lines = output.splitlines()
                    fail = f"FAIL: test_bad ({module}.Bad.test_bad)"
                    self.assertIn(fail, lines, "precondition: the planted failure did not run")
                    self.assertNotEqual(code, 0, output)
                    found = self.resource_lines(lines)
                    self.assertEqual([phase for _, phase in found], ["start", "end"], output)
                    self.assertGreater(found[1][0], lines.index(fail),
                                       "phase=end is not after the failed run")
                    for label in not_started:
                        self.assertEqual(counts.get(label, 0), 0,
                                         f"{label} ran after a failed run: {counts}")
                    self.assertNotIn(combine_mark, lines, "combine ran after a failed run")
            (self.project / rel).unlink()

    def test_combine_leaving_a_run_data_file_fails_naming_its_label(self):
        # CS-4 / §2.2.1-r3 decision 3 (adapted from
        # test_unit_pool_fails_when_combine_leaves_a_module_data_file, review
        # R2): the data file of a run is at the expected path but real combine
        # cannot read it, skips it, leaves it on disk and exits 0. test.sh must
        # fail and name the run's label. The control run (nothing corrupted)
        # passes and combine leaves no parallel data file behind.
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, _ = self.run_mode(mode, {"KE_TEST_DATA_LOG": "1"}, merged=True)
            with self.subTest(mode=mode, run="control"):
                self.assertEqual(code, 0, output)
                self.assertEqual(sorted(p.name for p in self.project.glob(".coverage.*")), [],
                                 "real combine left parallel data files in the control run")
                for label in self.LABELS[mode]:
                    self.assertTrue([c for c in self.uv_calls() if c.startswith("data-written ")
                                     and f".coverage.{label}." in c],
                                    f"the {label} run left no data: {self.uv_calls()}")
            for label in self.LABELS[mode]:
                self.clear_coverage_data()
                code, output, _ = self.run_mode(mode, {"KE_TEST_BADDATA_LABEL": label},
                                                merged=True)
                with self.subTest(mode=mode, run="unconsumed", label=label):
                    corrupted = [c for c in self.uv_calls()
                                 if c.startswith("data-corrupted ") and f".coverage.{label}." in c]
                    self.assertTrue(corrupted, f"precondition: no data file labelled {label} was "
                                               f"corrupted: {self.uv_calls()}")
                    self.assertNotEqual(code, 0, f"combine left the {label} data file unconsumed, "
                                        "test.sh passed:\n" + output)
                    self.assertTrue(self.error_lines(output, label),
                                    f"no error line names the label {label}:\n" + output)

    def test_coverage_combine_gets_an_explicit_file_list(self):
        # CS-4 / §2.2.1-r3 decision 3: `coverage combine` is given exactly
        # this run's data files, one per run label, never a directory and
        # never no argument (with none it searches the data directory and
        # takes whatever is there).
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, _ = self.run_mode(mode)
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output)
                calls = self.uv_calls()
                combine = [c for c in calls if c.startswith("python -m coverage combine")]
                self.assertEqual(len(combine), 1, calls)
                files = [a for a in combine[0].split()[4:] if not a.startswith("-")]
                self.assertTrue(files, f"coverage combine got no file list: {combine[0]}")
                self.assertEqual([c for c in calls if c.startswith("combine-dir ")], [],
                                 "coverage combine was given a directory")
                self.assertEqual(len(files), len(self.LABELS[mode]), files)
                for label in self.LABELS[mode]:
                    self.assertEqual(len([f for f in files if f".coverage.{label}." in f]), 1,
                                     f"the {label} data file is not in the combine list once: "
                                     f"{files}")

    def test_data_file_lookup_empty_or_failed_fails_before_any_test(self):
        # Review R2 / CS-4 / §2.2.1-r3 decision 3: if the data_file lookup
        # prints nothing or exits non-zero, test.sh fails before any test
        # runs: no fallback to ./.coverage.
        for lookup in ("empty", "fail"):
            for mode in ("fast", "full"):
                self.clear_coverage_data()
                code, output, counts = self.run_mode(mode, {"KE_TEST_LOOKUP": lookup}, merged=True)
                with self.subTest(lookup=lookup, mode=mode):
                    calls = self.uv_calls()
                    self.assertTrue([c for c in calls if c.startswith("lookup-intercepted ")],
                                    f"precondition: test.sh made no data_file lookup: {calls}")
                    self.assertNotEqual(code, 0, f"data_file lookup {lookup}, test.sh passed:\n"
                                        + output)
                    ran = [c for c in calls if c.startswith("python ")
                           and ("-m unittest" in c or "-m coverage run" in c)]
                    self.assertEqual(ran, [], "tests ran after the data_file lookup failed")
                    self.assertEqual(counts, {}, output)

    def test_each_coverage_run_leaves_data_or_fails_naming_its_label(self):
        # Ruling Q-CS1 / CS-4 / §2.2.1-r3 decision 3 (adapted from
        # test_unit_pool_fails_when_a_module_leaves_no_coverage_data): no
        # percentage tolerance; every coverage run must leave a data file for
        # `combine`. A run whose tests ran and printed `Ran`/OK but wrote no
        # data fails test.sh with an error line naming its label and coverage.
        ran_label = {"toplevel": "testfoo", "tests.unit": "sub", "tests.integration": "integration"}
        for mode in ("fast", "full"):
            for label in self.LABELS[mode]:
                self.clear_coverage_data()
                code, output, counts = self.run_mode(mode, {"KE_TEST_NODATA_LABEL": label},
                                                     merged=True)
                with self.subTest(mode=mode, label=label):
                    self.assertIn(f"nodata-run {label}", self.uv_calls(),
                                  f"precondition: no coverage run is labelled {label}: "
                                  f"{self.coverage_runs()}")
                    self.assertEqual(counts.get(ran_label[label], 0), 1,
                                     f"the no-data run's tests did not run: {counts}\n{output}")
                    self.assertNotEqual(code, 0,
                                        f"the {label} run left no coverage data, test.sh "
                                        "passed:\n" + output)
                    named = [line for line in self.error_lines(output, label)
                             if "coverage" in line.lower()]
                    self.assertTrue(named, f"no error line names {label} and coverage:\n" + output)

    # Guards, green before rework 3 and kept green by it.

    def chatty(self, name: str, tests: int = 4) -> None:
        body = "import time\nimport unittest\nclass Chatty(unittest.TestCase):\n"
        for i in range(tests):
            body += f"    def test_c{i}(self):\n        time.sleep(0.1)\n"
        self.write(f"tests/{name}.py", body)

    FAILING = ("import unittest\nclass Bad(unittest.TestCase):\n"
               "    def test_bad(self):\n        self.fail('planted')\n")

    def test_failing_module_fails_run_and_other_modules_still_run(self):
        # CS-10 guard: one failing top-level module fails test.sh; the other
        # top-level modules (same process) still ran and their output is
        # printed; no later run starts.
        self.write("tests/test_fails.py",
                   "import unittest\nclass Fails(unittest.TestCase):\n"
                   "    def test_fails(self):\n        self.fail('planted failure')\n")
        code, output, counts = self.run_mode("fast")
        self.assertNotEqual(code, 0, output)
        self.assertIn("FAIL: test_fails (tests.test_fails.Fails.test_fails)", output)
        for label, module in (("top", "tests.test_x"), ("testfoo", "tests.testfoo")):
            with self.subTest(module=module):
                self.assertEqual(counts.get(label, 0), 1, counts)
                self.assertIn(f"test_counted ({module}.Counted.test_counted) ... ok", output)
        self.assertEqual(counts.get("sub", 0), 0, f"a later run started: {counts}")

    # Review N1 (ci-speed rework 2): a failing sub-package or integration run
    # must still fail test.sh; in full, a failing sub-package run stops the
    # integration run from starting (CS-10).

    def test_failing_subpackage_module_fails_run(self):
        self.write("tests/unit/test_bad.py", self.FAILING)
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, counts = self.run_mode(mode, merged=True)
            with self.subTest(mode=mode):
                self.assertIn("FAIL: test_bad (tests.unit.test_bad.Bad.test_bad)", output,
                              "precondition: the planted sub-package test did not run")
                self.assertNotEqual(code, 0, "a failing sub-package test, test.sh passed:\n"
                                    + output)
                self.assertEqual(counts.get("integration", 0), 0,
                                 f"the integration run started after a failed run: {counts}")

    def test_failing_integration_module_fails_full_run(self):
        self.write("tests/integration/test_bad.py", self.FAILING)
        self.clear_coverage_data()
        code, output, _ = self.run_mode("full", merged=True)
        self.assertIn("FAIL: test_bad (tests.integration.test_bad.Bad.test_bad)", output,
                      "precondition: the planted integration test did not run")
        self.assertNotEqual(code, 0, "a failing integration test, test.sh full passed:\n"
                            + output)

    def install_real_verify(self) -> None:
        """The real verify.sh and sentinel module in the throwaway project,
        with passing lint and smoke stand-ins (KE_IN_GATES=1 keeps verify.sh
        out of docker)."""
        shutil.copyfile(VERIFY_SH, self.project / "scripts" / "verify.sh")
        shutil.copyfile(ROOT / "tests" / "test_sentinel.py",
                        self.project / "tests" / "test_sentinel.py")
        # verify.sh runs scripts/test.sh as a program; copyfile drops the mode.
        test_sh = self.project / "scripts" / "test.sh"
        test_sh.chmod(test_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        for name, body in (("lint.sh", "echo 'fake lint: ok'\n"), ("smoke.sh", "echo 'fake smoke: ok'\n")):
            path = self.project / "scripts" / name
            path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def test_verify_sees_sentinel_and_ran_lines_from_real_test_sh(self):
        # profile.md §5 / CS-10: the real verify.sh, fed by the real test.sh
        # (and the real sentinel module), finds the whole sentinel line and a
        # `Ran N > 0` line.
        self.install_real_verify()
        for name in ("test_ca", "test_cb", "test_cc"):
            self.chatty(name)
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, _ = self.run_mode(mode, {"KE_IN_GATES": "1"}, merged=True,
                                            script="verify.sh")
            with self.subTest(mode=mode):
                self.assertEqual(code, 0, output[-3000:])
                self.assertIn(f"== verify {mode}: PASS ==", output)
                self.assertEqual(output.splitlines().count(VerifyRequiresTestsRunTest.SENTINEL), 1,
                                 output[-3000:])

    def test_verify_fails_when_a_top_level_module_exits_zero_at_import(self):
        # Review R1 (audit probe audit/probe_test_exit0.py.txt), adapted for
        # §2.2.1-r3 decision 2: the per-module Ran check is withdrawn, and
        # verify.sh's sentinel check catches this instead. A module raising
        # SystemExit(0) at import stops loading before any top-level test
        # runs, so the sentinel never reports ok and the real verify.sh fails
        # whatever test.sh's exit status is.
        self.install_real_verify()
        self.write("tests/test_exit0.py", "import sys\nsys.exit(0)\n")
        for mode in ("fast", "full"):
            self.clear_coverage_data()
            code, output, _ = self.run_mode(mode, {"KE_IN_GATES": "1"}, merged=True,
                                            script="verify.sh")
            with self.subTest(mode=mode):
                # No precondition on the sentinel line: before rework 3 the
                # pool ran test_sentinel in its own process, and test.sh's
                # per-module Ran check failed the run instead.
                self.assertNotEqual(code, 0, output[-3000:])
                self.assertNotIn(": PASS ==", output)


class UnitStageStaticTest(unittest.TestCase):
    """ci-speed: static pins on scripts/test.sh (rework 1; rework 3,
    §2.2.1-r3)."""

    @staticmethod
    def code() -> str:
        return "\n".join(line for line in read(TEST_SH).splitlines()
                         if not line.lstrip().startswith("#"))

    def test_data_file_comes_from_coverage_api_not_debug_config(self):
        # Review R2 / CS-4 / §2.2.1-r3 decision 3: the data path comes from
        # coverage's Python API, not from parsing the text of
        # `coverage debug config` (not a stable interface).
        code = self.code()
        self.assertNotIn("debug config", code)
        self.assertRegex(code, r"Coverage\(\)\.config\.data_file")

    def test_printf_formats_hold_no_literal_newline(self):
        # Review L2: a printf format spelled across two lines works but reads
        # like a bug; the newline is written `\n`.
        formats = re.findall(r"\bprintf\s+(?:--\s+)?('[^']*'|\"[^\"]*\")", read(TEST_SH))
        for fmt in formats:
            with self.subTest(format=fmt):
                self.assertNotIn("\n", fmt)

    def test_pool_machinery_is_gone(self):
        # CS-10 last bullet / §2.2.1-r3 decision 1: no k from nproc, no job
        # control or `wait -n` scheduling, no log directory, no size ordering
        # and no INT/TERM trap are left in test.sh.
        code = self.code()
        for name, pattern in (("nproc", r"\bnproc\b"), ("wait -n", r"\bwait\s+-n\b"),
                              ("set -m", r"\bset\s+-m\b"), ("mktemp", r"\bmktemp\b"),
                              ("stat -c", r"\bstat\s+-c\b"),
                              ("INT/TERM trap", r"\btrap\b[^\n]*\b(INT|TERM)\b")):
            with self.subTest(left=name):
                match = re.search(pattern, code)
                self.assertIsNone(match, f"{name} is still in test.sh: "
                                         f"{match.group(0) if match else ''!r}")

    def test_probe_runs_with_a_phase_only(self):
        # CS-11 / §2.2.1-r3 decision 4: test.sh runs
        # `bash scripts/resource_probe.sh start` and `... end`; the root
        # argument is a test seam that test.sh never passes.
        calls = re.findall(r"\bbash\s+scripts/resource_probe\.sh([^\n;|&)]*)", self.code())
        self.assertTrue(calls, "test.sh never runs scripts/resource_probe.sh")
        for args in calls:
            with self.subTest(args=args):
                self.assertIn(args.split(), (["start"], ["end"]))
        self.assertEqual({args.split()[0] for args in calls if args.split()}, {"start", "end"})


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
