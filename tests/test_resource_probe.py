"""Plan item ci-speed, CS-11 (docs/requirements.md; architecture §2.2.1-r3
decision 4): scripts/resource_probe.sh <phase> [root] prints one
`resources:` line of fixed keys, each a number, `max` (two keys only) or
`n/a`. It always exits 0, writes nothing to stderr, reads no environment
variable and never prints file text other than digits or `max`.

`root` is the test seam: each case builds a fake /proc and /sys/fs/cgroup
under a temp dir and passes it. `nproc` is the one command the probe runs; a
fake one goes first on PATH, or PATH holds no nproc at all."""

import ctypes
import os
import random
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "resource_probe.sh"
BASH = shutil.which("bash")

# The fixed key order of §2.2.1-r3 decision 4 ("Exact line").
KEYS = ("phase", "nproc", "cpu_max_quota", "cpu_max_period", "cg_cpu_usage_us",
        "cg_cpu_throttled_us", "mem_total_kib", "mem_available_kib", "swap_total_kib",
        "swap_free_kib", "cg_mem_max", "cg_mem_peak", "psi_cpu_some_us", "psi_memory_some_us",
        "psi_memory_full_us", "psi_io_some_us", "psi_io_full_us", "cpu_steal_ticks",
        "cpu_total_ticks")
MAX_ALLOWED = ("cpu_max_quota", "cg_mem_max")
VALUE = re.compile(r"^([0-9]+|max|n/a)$")

# Every source the probe reads, relative to root.
SOURCES = ("sys/fs/cgroup/cpu.max", "sys/fs/cgroup/cpu.stat", "proc/meminfo",
           "sys/fs/cgroup/memory.max", "sys/fs/cgroup/memory.peak", "proc/pressure/cpu",
           "proc/pressure/memory", "proc/pressure/io", "proc/stat")

GOOD = {
    "sys/fs/cgroup/cpu.max": "200000 100000\n",
    "sys/fs/cgroup/cpu.stat": ("usage_usec 123456\nuser_usec 100000\nsystem_usec 23456\n"
                               "nr_periods 10\nnr_throttled 2\nthrottled_usec 789\n"),
    "proc/meminfo": ("MemTotal:        7000000 kB\nMemFree:         1000000 kB\n"
                     "MemAvailable:    5000000 kB\nBuffers:           10000 kB\n"
                     "SwapCached:            0 kB\nSwapTotal:       4194300 kB\n"
                     "SwapFree:        4194000 kB\n"),
    "sys/fs/cgroup/memory.max": "max\n",
    "sys/fs/cgroup/memory.peak": "1536000000\n",
    "proc/pressure/cpu": ("some avg10=0.00 avg60=0.00 avg300=0.00 total=111\n"
                          "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"),
    "proc/pressure/memory": ("some avg10=0.00 avg60=0.00 avg300=0.00 total=222\n"
                             "full avg10=0.00 avg60=0.00 avg300=0.00 total=333\n"),
    "proc/pressure/io": ("some avg10=0.00 avg60=0.00 avg300=0.00 total=444\n"
                         "full avg10=0.00 avg60=0.00 avg300=0.00 total=555\n"),
    # Fields 1-8 are user nice system idle iowait irq softirq steal: steal is
    # 80, and the total of fields 1-8 is 360 (guest fields 9-10 excluded).
    "proc/stat": ("cpu  10 20 30 40 50 60 70 80 90 100\n"
                  "cpu0 5 10 15 20 25 30 35 40 45 50\nintr 1 2 3\n"),
}
GOOD_LINE = ("resources: phase={phase} nproc=2 cpu_max_quota=200000 cpu_max_period=100000 "
             "cg_cpu_usage_us=123456 cg_cpu_throttled_us=789 mem_total_kib=7000000 "
             "mem_available_kib=5000000 swap_total_kib=4194300 swap_free_kib=4194000 "
             "cg_mem_max=max cg_mem_peak=1536000000 psi_cpu_some_us=111 "
             "psi_memory_some_us=222 psi_memory_full_us=333 psi_io_some_us=444 "
             "psi_io_full_us=555 cpu_steal_ticks=80 cpu_total_ticks=360")
ALL_NA = "resources: phase={phase} " + " ".join(f"{k}=n/a" for k in KEYS[1:])

# Rework 4 (architecture §2.2.1-r3 decision 4 "Hardening"; security S5): the
# hang guard for the bounded-read cases. It is well under the 60 s used
# elsewhere, so a probe that blocks on a FIFO or spins on an endless source
# fails the test instead of blocking the run.
PROBE_HANG_S = 10
# Rework 4 (security S6, review nit 6): the two tick keys never take `max`.
TICKS = re.compile(r"^([0-9]+|n/a)$")
INT64_MAX = 2**63 - 1
# Rework 4 (security S7): GNU nproc honours these two variables.
OMP_VARS = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT")
# Variables a canary must not replace: bash or the run itself needs them.
ENV_KEEP = {"PATH", "IFS", "ENV", "BASH_ENV", "SHELLOPTS", "BASHOPTS", "POSIXLY_CORRECT",
            "PS4", "LC_ALL", "LANG", "HOME", "TMPDIR"}


def script_names(text: str) -> set:
    """Every identifier-like word on the non-comment lines of a script: a
    superset of the variable names it uses (decision 4, test 5)."""
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return {w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code)
            if w not in ENV_KEEP and not w.startswith("BASH")}


@unittest.skipUnless(BASH, "needs bash")
class ResourceProbeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin_dir = self.tmp / "bin"
        self.bin_dir.mkdir()
        # cwd for every run: empty, so a relative read finds nothing.
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()

    def fake_root(self, files: dict, name: str = "root") -> Path:
        root = self.tmp / name
        root.mkdir()
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        return root

    def fake_nproc(self, body: str) -> None:
        path = self.bin_dir / "nproc"
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def require_probe(self) -> None:
        self.assertTrue(PROBE.is_file(), f"{PROBE.relative_to(ROOT).as_posix()} does not exist")

    def probe(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        # PATH holds only bin_dir: no nproc unless a test planted one there.
        # bash is called by its absolute path.
        run_env = {"PATH": str(self.bin_dir), "LC_ALL": "C"}
        run_env.update(env or {})
        return subprocess.run([BASH, str(PROBE), *args], cwd=self.cwd, env=run_env,
                              capture_output=True, text=True, timeout=30)

    def probe_bounded(self, *args: str, env: dict | None = None, full_env: dict | None = None,
                      argv: list | None = None, cwd: Path | None = None
                      ) -> subprocess.CompletedProcess:
        """As probe(), but in its own process group with a PROBE_HANG_S
        timeout: on expiry the whole group is killed (a blocked command
        substitution included) and the test fails."""
        if full_env is not None:
            run_env = dict(full_env)
        else:
            run_env = {"PATH": str(self.bin_dir), "LC_ALL": "C"}
            run_env.update(env or {})
        cmd = argv or [BASH, str(PROBE), *args]
        proc = subprocess.Popen(cmd, cwd=cwd or self.cwd, env=run_env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
        try:
            out, err = proc.communicate(timeout=PROBE_HANG_S)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = proc.communicate()
            self.fail(f"the probe did not return within {PROBE_HANG_S} s and was killed "
                      f"(stdout so far: {out[:200]!r})")
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)

    def values(self, result: subprocess.CompletedProcess) -> dict:
        """rc 0, empty stderr, one line of the fixed shape: its key=value map."""
        self.assertEqual(result.returncode, 0, result.stdout[:300] + result.stderr[:300])
        self.assertEqual(result.stderr, "", "the probe wrote to stderr")
        self.assertTrue(result.stdout.endswith("\n") and result.stdout.count("\n") == 1,
                        repr(result.stdout[:300]))
        line = result.stdout.rstrip("\n")
        self.assert_shape(line)
        return dict(p.split("=", 1) for p in line[len("resources: "):].split(" "))

    def assert_one_line(self, result: subprocess.CompletedProcess, expected: str) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "", "the probe wrote to stderr")
        self.assertEqual(result.stdout, expected + "\n")

    def assert_shape(self, line: str) -> None:
        """The fixed key list, in order, one space apart, each value allowed."""
        self.assertTrue(line.startswith("resources: "), line)
        pairs = [p.split("=", 1) for p in line[len("resources: "):].split(" ")]
        self.assertEqual([p[0] for p in pairs], list(KEYS), line)
        for key, value in pairs[1:]:
            with self.subTest(key=key):
                self.assertRegex(value, VALUE)
                if value == "max":
                    self.assertIn(key, MAX_ALLOWED, f"{key}=max is not allowed")

    def test_prints_one_line_from_a_fake_root(self):
        # CS-11, first failing test 1: known sources and a fake nproc give
        # the exact line, for both phases.
        self.require_probe()
        root = self.fake_root(GOOD)
        self.fake_nproc("echo 2\n")
        for phase in ("start", "end"):
            with self.subTest(phase=phase):
                result = self.probe(phase, str(root))
                self.assert_one_line(result, GOOD_LINE.format(phase=phase))
                self.assert_shape(result.stdout.rstrip("\n"))
        # `max` in cpu.max is the quota, and a numeric memory.max is printed
        # as it is.
        other = dict(GOOD)
        other["sys/fs/cgroup/cpu.max"] = "max 100000\n"
        other["sys/fs/cgroup/memory.max"] = "8589934592\n"
        root2 = self.fake_root(other, "root2")
        with self.subTest(case="cpu.max max, numeric memory.max"):
            expected = (GOOD_LINE.format(phase="start")
                        .replace("cpu_max_quota=200000", "cpu_max_quota=max")
                        .replace("cg_mem_max=max", "cg_mem_max=8589934592"))
            self.assert_one_line(self.probe("start", str(root2)), expected)

    def test_missing_sources_print_na_and_exit_0(self):
        # CS-11, first failing test 2: an empty root and no nproc on PATH give
        # n/a for every key, exit 0 and an empty stderr.
        self.require_probe()
        empty = self.fake_root({}, "empty")
        with self.subTest(case="empty root, no nproc"):
            self.assert_one_line(self.probe("start", str(empty)), ALL_NA.format(phase="start"))
        # Unreadable sources: each one is a directory, so a read fails (as
        # root a chmod 000 file is still readable). Under a non-root uid (the
        # gates run as 10001) a chmod 000 file is checked too. nproc fails.
        dirs = self.tmp / "dirs"
        for rel in SOURCES:
            (dirs / rel).mkdir(parents=True)
        self.fake_nproc("echo 'nproc: failed' >&2\nexit 1\n")
        with self.subTest(case="every source a directory, nproc fails"):
            self.assert_one_line(self.probe("end", str(dirs)), ALL_NA.format(phase="end"))
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            locked = self.fake_root(GOOD, "locked")
            for rel in SOURCES:
                (locked / rel).chmod(0)
            self.addCleanup(lambda: [(locked / rel).chmod(0o644) for rel in SOURCES])
            with self.subTest(case="every source chmod 000"):
                self.assert_one_line(self.probe("end", str(locked)), ALL_NA.format(phase="end"))

    def test_prints_only_numbers_never_file_text_or_env(self):
        # CS-11, first failing test 3; §2.2.1-r3 decision 4 rules: no file
        # content other than digits or `max`, no environment variable.
        self.require_probe()
        canary = "ke-canary-" + uuid.uuid4().hex
        numeric = "987654321987"  # passes the value pattern, so a leak would print
        env = {"KE_PROBE_CANARY": canary, "SECRET": canary, "root": numeric, "ROOT": numeric,
               "phase": numeric, "PHASE": numeric, "HOME": "/" + canary}
        for key in KEYS[1:]:
            env[key] = numeric
            env[key.upper()] = numeric
        planted = {
            "sys/fs/cgroup/cpu.max": "SECRET=x /etc/passwd\n",
            "sys/fs/cgroup/cpu.stat": f"usage_usec /root/.ssh/id_rsa\nthrottled_usec SECRET={canary}\n",
            "proc/meminfo": ("MemTotal:       SECRET=x kB\nMemAvailable:    /etc/shadow kB\n"
                             "SwapTotal:       12abc kB\nSwapFree:        -5 kB\n"),
            "sys/fs/cgroup/memory.max": "maximum\n",
            "sys/fs/cgroup/memory.peak": "max\n",  # `max` is allowed for cg_mem_max only
            "proc/pressure/cpu": "some avg10=0.00 avg60=0.00 avg300=0.00 total=SECRET=x\n",
            "proc/pressure/memory": "some total=/etc/passwd\nfull total=1e5\n",
            "proc/pressure/io": f"some avg10=1.00\nfull {canary}\n",
            "proc/stat": "cpu  1 2 3 4 5 6 7 SECRET=x\n",
        }
        root = self.fake_root(planted)
        self.fake_nproc("echo SECRET=x\n")
        result = self.probe("start", str(root), env=env)
        for text in ("SECRET", "/etc", "/root", canary, numeric, "12abc", "1e5", "maximum"):
            with self.subTest(leak=text):
                self.assertNotIn(text, result.stdout + result.stderr)
        with self.subTest(case="file text in every source"):
            self.assert_one_line(result, ALL_NA.format(phase="start"))
        # Env alone, with no source to read: still nothing from the env.
        empty = self.fake_root({}, "empty")
        with self.subTest(case="env set, sources missing, no nproc"):
            (self.bin_dir / "nproc").unlink()
            result = self.probe("end", str(empty), env=env)
            self.assert_one_line(result, ALL_NA.format(phase="end"))
            self.assertNotIn(canary, result.stdout)
            self.assertNotIn(numeric, result.stdout)
        # A phase other than start or end prints phase=n/a, never the argument.
        good = self.fake_root(GOOD, "good")
        self.fake_nproc("echo 2\n")
        for phase in ("SECRET=x", "", "start end", canary):
            with self.subTest(phase=phase):
                result = self.probe(phase, str(good), env=env)
                self.assert_one_line(result, GOOD_LINE.format(phase="n/a"))
        # The good line's key list is the fixed order exactly.
        self.assert_shape(GOOD_LINE.format(phase="start"))
        self.assert_shape(ALL_NA.format(phase="start"))

    # ---- rework 4: architecture §2.2.1-r3 "First failing tests, rework 4" ----

    def good_values(self) -> dict:
        line = GOOD_LINE.format(phase="start")
        return dict(p.split("=", 1) for p in line[len("resources: "):].split(" "))

    def assert_keys(self, values: dict, na: tuple) -> None:
        """`na` keys print n/a; every other key is as in GOOD_LINE. Messages
        are cut short, so a 1 MB leak does not flood the log."""
        good = self.good_values()
        for key in KEYS:
            want = "n/a" if key in na else good[key]
            got = values.get(key, "<missing>")
            with self.subTest(key=key):
                self.assertTrue(got == want, f"{key}={got[:60]!r}, want {want!r}")

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "killpg"),
                         "needs POSIX FIFOs and process groups")
    def test_fifo_or_device_source_gives_na_quickly(self):
        # Rework 4 test 1 (security S5): a FIFO with no writer or a symlink to
        # /dev/zero is never opened. The probe returns well inside
        # PROBE_HANG_S, prints n/a for those keys only, and exits 0.
        self.require_probe()
        zero = Path("/dev/zero")
        if not zero.exists():
            self.skipTest("needs /dev/zero")
        # The design's case: stat and cpu.max FIFOs, meminfo /dev/zero.
        bad = ("proc/stat", "sys/fs/cgroup/cpu.max", "proc/meminfo")
        mixed = self.fake_root({k: v for k, v in GOOD.items() if k not in bad}, "mixed")
        os.mkfifo(mixed / "proc/stat")
        os.mkfifo(mixed / "sys/fs/cgroup/cpu.max")
        (mixed / "proc/meminfo").symlink_to(zero)
        self.fake_nproc("echo 2\n")
        with self.subTest(case="stat and cpu.max FIFOs, meminfo -> /dev/zero, rest good"):
            values = self.values(self.probe_bounded("start", str(mixed)))
            self.assert_keys(values, ("cpu_max_quota", "cpu_max_period", "mem_total_kib",
                                      "mem_available_kib", "swap_total_kib", "swap_free_kib",
                                      "cpu_steal_ticks", "cpu_total_ticks"))
        (self.bin_dir / "nproc").unlink()
        fifos = self.tmp / "fifos"
        zeros = self.tmp / "zeros"
        for rel in SOURCES:
            (fifos / rel).parent.mkdir(parents=True, exist_ok=True)
            os.mkfifo(fifos / rel)
            (zeros / rel).parent.mkdir(parents=True, exist_ok=True)
            (zeros / rel).symlink_to(zero)
        with self.subTest(case="every source a FIFO with no writer, no nproc"):
            self.assert_one_line(self.probe_bounded("start", str(fifos)),
                                 ALL_NA.format(phase="start"))
        with self.subTest(case="every source a symlink to /dev/zero, no nproc"):
            self.assert_one_line(self.probe_bounded("end", str(zeros)),
                                 ALL_NA.format(phase="end"))

    @unittest.skipUnless(hasattr(os, "killpg"), "needs POSIX process groups")
    def test_oversized_source_is_cut_off(self):
        # Rework 4 test 2: reads are capped (-n 4096, at most 64 lines). A
        # 1 MB single line of digits in memory.peak, and a meminfo with more
        # than 64 filler lines before MemTotal:, both give n/a quickly.
        self.require_probe()
        files = dict(GOOD)
        files["sys/fs/cgroup/memory.peak"] = "7" * (1024 * 1024) + "\n"
        filler = "".join(f"Filler{i}:        {i} kB\n" for i in range(100))
        files["proc/meminfo"] = filler + GOOD["proc/meminfo"]
        root = self.fake_root(files)
        self.fake_nproc("echo 2\n")
        result = self.probe_bounded("start", str(root))
        self.assertLess(len(result.stdout), 4096, "an oversized value was printed")
        values = self.values(result)
        self.assert_keys(values, ("cg_mem_peak", "mem_total_kib", "mem_available_kib",
                                  "swap_total_kib", "swap_free_kib"))

    @unittest.skipUnless(hasattr(os, "killpg"), "needs POSIX process groups")
    def test_each_reader_caps_bytes_and_lines(self):
        # Rework 5 (review nit 2; reviewer mutants R6, R7 and R9 survived
        # rework 4, docs/evidence/ci-speed/rework4/review/probe-mutants.txt).
        # Each reader reads at most 4096 bytes per read and field and psi at
        # most 64 reads, so text past those caps is never seen.
        self.require_probe()
        self.fake_nproc("echo 2\n")
        cap = 64 * 4096
        cases = (
            # R7 (field: -n 4096): a first line longer than 64 x 4096 bytes is
            # 64 or more capped reads, so MemTotal: on the next line is past
            # the 64-read cap.
            ("meminfo first line over 64 x 4096 bytes", "proc/meminfo",
             "x" * (cap + 4096 * 2) + "\n" + GOOD["proc/meminfo"],
             ("mem_total_kib", "mem_available_kib", "swap_total_kib", "swap_free_kib")),
            # R9 (psi: 64-line cap): more than 64 filler lines before some/full.
            ("pressure/io: 100 filler lines first", "proc/pressure/io",
             "".join(f"filler{i} avg10=0.00 total={i}\n" for i in range(100))
             + GOOD["proc/pressure/io"],
             ("psi_io_some_us", "psi_io_full_us")),
            # R6 (one: -n 4096): the period starts past byte 4096 of the line,
            # so only the quota is read.
            ("cpu.max: period past byte 4096", "sys/fs/cgroup/cpu.max",
             "200000" + " " * 8192 + "100000\n", ("cpu_max_period",)),
        )
        for n, (case, rel, text, na) in enumerate(cases):
            with self.subTest(case=case):
                files = dict(GOOD)
                files[rel] = text
                root = self.fake_root(files, f"cap{n}")
                # Preconditions: past the byte cap, or past the line cap.
                first, lines = text.split("\n", 1)[0], text.count("\n")
                self.assertTrue(len(first) > 4096 or lines > 64, case)
                result = self.probe_bounded("start", str(root))
                self.assertLess(len(result.stdout), 4096, "an oversized value was printed")
                self.assert_keys(self.values(result), na)

    def test_stat_fields_are_base_10_and_capped(self):
        # Rework 4 test 3 (security S6, review nit 6): each of the 8 fields
        # must be 1-18 digits and is added as base 10. A leading zero is
        # decimal (`08` is no error); eight 18-digit fields give their exact
        # sum; a field over 18 digits gives n/a for BOTH steal and total.
        # Both keys always match ^([0-9]+|n/a)$.
        self.require_probe()
        self.fake_nproc("echo 2\n")
        eighteen = [str(10**17 + 123456789012345 * i) for i in range(1, 9)]
        cases = (
            # (fields 1-10, expected total, expected steal as an int or None for n/a)
            ("010 020 030 040 050 060 070 001 0 0", 281, 1),   # octal would give 225
            ("08 09 0 0 0 0 0 07 0 0", 24, 7),                 # 08/09: invalid octal
            ("0 0 0 0 0 0 0 0010 0 0", 10, 10),
            (" ".join(eighteen) + " 0 0", sum(int(f) for f in eighteen), int(eighteen[7])),
            ("999999999999999999 " * 8 + "0 0", 8 * (10**18 - 1), 10**18 - 1),
            ("1000000000000000000 0 0 0 0 0 0 5 0 0", None, None),        # 19 digits, field 1
            ("1 1 1 1 1 1 1 9223372036854775807 0 0", None, None),       # 19 digits, steal
            ("9223372036854775807 1 0 0 0 0 0 0 0 0", None, None),       # 2^63-1, sum over
            ("4611686018427387904 4611686018427387904 0 0 0 0 0 0 0 0", None, None),  # 2^63
            ("18446744073709551616 0 0 0 0 0 0 0 0 0", None, None),      # 2^64, wraps to 0
            ("99999999999999999999999 0 0 0 0 0 0 0 0", None, None),     # 23 digits
            ("0000000000000000001 0 0 0 0 0 0 0 0 0", None, None),       # 19 chars
        )
        for n, (fields, total, steal) in enumerate(cases):
            with self.subTest(fields=fields):
                parts = fields.split()
                if total is not None:  # the case table itself
                    self.assertEqual(sum(int(f, 10) for f in parts[:8]), total)
                    self.assertLessEqual(total, INT64_MAX)
                files = dict(GOOD)
                files["proc/stat"] = f"cpu  {fields}\ncpu0 1 2 3 4 5 6 7 8 9 10\n"
                root = self.fake_root(files, f"stat{n}")
                values = self.values(self.probe("start", str(root)))
                got_total, got_steal = values["cpu_total_ticks"], values["cpu_steal_ticks"]
                self.assertRegex(got_total, TICKS)
                self.assertRegex(got_steal, TICKS)
                if total is None:
                    self.assertEqual((got_steal, got_total), ("n/a", "n/a"))
                else:
                    self.assertEqual(got_total, str(total), "fields are summed as decimal")
                    self.assertNotEqual(got_steal, "n/a")
                    self.assertEqual(int(got_steal, 10), steal, "steal is field 8, decimal")
                good = self.good_values()
                for key in KEYS[:-2]:
                    self.assertEqual(values[key], good[key], key)

    def test_nproc_ignores_openmp_env(self):
        # Rework 4 test 4 (security S7): the probe runs nproc with
        # OMP_NUM_THREADS and OMP_THREAD_LIMIT emptied. A fake nproc that
        # honours them as GNU nproc does prints 7 only when both are empty
        # or unset.
        self.require_probe()
        self.fake_nproc('if [ -n "${OMP_NUM_THREADS:-}" ]; then echo "$OMP_NUM_THREADS"; exit 0; fi\n'
                        'if [ -n "${OMP_THREAD_LIMIT:-}" ]; then echo "$OMP_THREAD_LIMIT"; exit 0; fi\n'
                        'echo 7\n')
        root = self.fake_root(GOOD)
        expected = GOOD_LINE.format(phase="start").replace(" nproc=2 ", " nproc=7 ")
        for case, extra in (("both 424242", {"OMP_NUM_THREADS": "424242",
                                             "OMP_THREAD_LIMIT": "424242"}),
                            ("OMP_NUM_THREADS only", {"OMP_NUM_THREADS": "424242"}),
                            ("OMP_THREAD_LIMIT=1 only", {"OMP_THREAD_LIMIT": "1"}),
                            ("neither", {})):
            with self.subTest(case=case):
                result = self.probe("start", str(root), env=extra)
                self.assertNotIn("nproc=424242", result.stdout)
                self.assert_one_line(result, expected)
        # The real nproc (GNU, gates image): the probe prints what nproc
        # prints with both variables removed.
        real = shutil.which("nproc")
        if real is None:
            self.skipTest("needs a real nproc")
        clean = {k: v for k, v in os.environ.items() if k not in OMP_VARS}
        planted = {"OMP_NUM_THREADS": "424242", "OMP_THREAD_LIMIT": "424242"}
        baseline = subprocess.run([real], env=clean, capture_output=True, text=True,
                                  timeout=30).stdout.strip()
        self.assertRegex(baseline, r"^[0-9]+$")
        self.assertNotEqual(baseline, "424242")
        with self.subTest(case="real nproc, both 424242"):
            result = self.probe("start", str(root),
                                env={"PATH": str(Path(real).parent), **planted})
            self.assertNotIn("nproc=424242", result.stdout)
            self.assert_one_line(result, GOOD_LINE.format(phase="start")
                                 .replace(" nproc=2 ", f" nproc={baseline} "))

    @unittest.skipUnless(hasattr(os, "killpg"), "needs POSIX process groups")
    def test_no_root_path_reads_no_env(self):
        # Rework 4 test 5 (review nit 5; mutant P7 `pr_root="${2:-${ROOT:-/}}"`
        # survived round 3). Run exactly as scripts/test.sh does: `bash
        # scripts/resource_probe.sh start` from the repo root, no root
        # argument, the caller's environment. A canary is set for ROOT, root,
        # cg and every name the script uses (parsed from it), plus secrets.
        # No canary number, path or secret is printed, and nothing is read
        # from the planted trees.
        self.require_probe()
        rng = random.SystemRandom()
        markers = [str(rng.randrange(7 * 10**17, 8 * 10**17)) for _ in range(23)]
        it = iter(markers)
        stat_fields = [next(it) for _ in range(8)]
        files = {
            "sys/fs/cgroup/cpu.max": f"{next(it)} {next(it)}\n",
            "sys/fs/cgroup/cpu.stat": f"usage_usec {next(it)}\nthrottled_usec {next(it)}\n",
            "proc/meminfo": (f"MemTotal: {next(it)} kB\nMemAvailable: {next(it)} kB\n"
                             f"SwapTotal: {next(it)} kB\nSwapFree: {next(it)} kB\n"),
            "sys/fs/cgroup/memory.max": f"{next(it)}\n",
            "sys/fs/cgroup/memory.peak": f"{next(it)}\n",
            "proc/pressure/cpu": f"some avg10=0.00 total={next(it)}\n",
            "proc/pressure/memory": f"some total={next(it)}\nfull total={next(it)}\n",
            "proc/pressure/io": f"some total={next(it)}\nfull total={next(it)}\n",
            "proc/stat": "cpu  " + " ".join(stat_fields) + " 0 0\n",
        }
        self.assertIsNone(next(it, None), "every canary is used once")
        planted = self.fake_root(files, "planted")
        # Precondition: given as the root argument, this tree's values print,
        # so a run that reads it would show a canary.
        self.fake_nproc("echo 2\n")
        shown = self.probe("start", str(planted)).stdout
        self.assertTrue(all(m in shown for m in markers[8:]), shown)
        # From here on, inotify reports any open or read under the planted
        # tree, printed or not.
        watch, why = self.watch_tree(planted)
        secret = "ke-secret-" + uuid.uuid4().hex
        number = str(rng.randrange(6 * 10**17, 7 * 10**17))
        names = script_names(PROBE.read_text(encoding="utf-8")) | {
            "ROOT", "root", "cg", "pr_root", "PR_ROOT", "PROBE_ROOT", "KE_PROBE_ROOT"}
        base = {k: v for k, v in os.environ.items() if k not in OMP_VARS}
        base.update({"SECRET": secret, "KE_API_TOKEN": secret, "AWS_SECRET_ACCESS_KEY": secret,
                     "GITHUB_TOKEN": secret})
        # Rework 5 (review nit 2, mutant R18 `cg="${CG:-…}"`): every name is
        # also pointed at the planted cgroup and proc directories, so a name
        # used as one of those directories reads planted files.
        runs = (
            ("names -> planted tree", {**{n: str(planted) for n in names},
                                       "cg": str(planted / "sys/fs/cgroup")}),
            ("names -> planted/sys/fs/cgroup", {n: str(planted / "sys/fs/cgroup") for n in names}),
            ("names -> planted/proc", {n: str(planted / "proc") for n in names}),
            ("names -> canary number", {n: number for n in names}),
        )
        forbidden = markers + [str(sum(int(f) for f in stat_fields)), number, secret,
                               str(planted)]
        for case, canaries in runs:
            with self.subTest(case=case):
                result = self.probe_bounded(full_env={**base, **canaries}, cwd=ROOT,
                                            argv=[BASH, "scripts/resource_probe.sh", "start"])
                values = self.values(result)
                self.assertEqual(values["phase"], "start")
                for token in forbidden:
                    self.assertNotIn(token, result.stdout + result.stderr)
        # Rework 5 (review nit 5): without inotify the read check is a
        # visible skipped subtest with its reason, never a silent pass.
        with self.subTest(check="no open or read under the planted tree (inotify)"):
            if watch is None:
                self.skipTest(f"inotify unavailable ({why}); only the output check ran")
            try:
                events = os.read(watch, 65536)
            except BlockingIOError:
                events = b""
            self.assertTrue(events == b"", f"the probe opened or read a file in the planted tree "
                            f"({len(events)} bytes of inotify events)")

    def watch_tree(self, tree: Path):
        """(fd, None): a non-blocking inotify fd watching every directory
        under `tree` for open and access events (Linux), closed at cleanup.
        (None, reason) where inotify is not available."""
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            init = libc.inotify_init1
            add = libc.inotify_add_watch
        except (OSError, AttributeError, TypeError) as exc:
            return None, f"no inotify_init1 in libc: {type(exc).__name__}"
        fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
        if fd < 0:
            return None, f"inotify_init1 failed: {os.strerror(ctypes.get_errno())}"
        self.addCleanup(os.close, fd)
        in_access, in_open = 0x1, 0x20
        for d in [tree, *(p for p in tree.rglob("*") if p.is_dir())]:
            self.assertGreaterEqual(add(fd, os.fsencode(d), in_access | in_open), 0, str(d))
        return fd, None


if __name__ == "__main__":
    unittest.main()
