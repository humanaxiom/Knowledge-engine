"""platform-offline, PS-3.3 `ci/offline`: engine.netprobe and the smoke.sh
host-half check, against socket stubs, real loopback sockets and the fake
docker.

Criteria: docs/requirements.md PS-3.3 (*Offline at runtime*, *Both app
containers probed*, *Control probe*: `test_offline_probe_fails_when_control_fails`).
Design: docs/architecture.md §2.5 "`ci/offline` (PS-3.3): in the host half of
`smoke.sh`" (target, control first, assertion, `engine/netprobe.py`), §2.6
item 11 (`NetprobeTest` and the smoke fake-docker cases).

Interface pinned by these tests (tester, RED offline check, 2026-10-19):
- `python -m engine.netprobe <ip> <port> --within <s>` and, in process,
  `engine.netprobe.main(argv: list[str]) -> int` (or SystemExit with that
  code): prints one word; exit 0 only for `connected`, 1 for `no_route`.
- In smoke.sh the control is `docker run --rm --network <project>_edge
  --entrypoint python <api image> -m engine.netprobe <ip> <port> --within 5`;
  the assertion is `compose exec -T <api|worker> python -m engine.netprobe
  <ip> <port> --within 2`. Failures say `ci/offline` and, for the assertion,
  name the service; a failed control says `inconclusive`.

Full tier: that api and worker really have no route out is `ci/offline` in
the live smoke of the developer's `scripts/verify.sh full` (and inside
`dind`); these fast tests do not stand in for it.
"""

from __future__ import annotations

import contextlib
import errno
import importlib
import io
import os
import re
import socket
import subprocess
import sys
import unittest
from typing import Any
from unittest import mock

from tests import test_stack_scripts as tss
from tests.engine_support import ROOT

NETPROBE = ROOT / "engine" / "netprobe.py"
TARGET = ["192.0.2.10", "8100"]
_REAL_SOCKET = socket.socket  # bound before any mock.patch("socket.socket")


class _FakeSocket:
    """socket.socket stand-in: `raise_` is what connect raises (None = connect)."""

    raise_: BaseException | None = None
    instances: list["_FakeSocket"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.timeout: float | None = None
        self.closed = False
        self.connected_to: Any = None
        _FakeSocket.instances.append(self)

    def settimeout(self, value: float | None) -> None:
        # Review NB1: the real settimeout raises OverflowError for a finite
        # value past the platform's time_t (1e300); the stand-in checks the
        # value on a real, never-connected socket so in-process tests see the
        # same failure the CLI does.
        if value is not None:
            with _REAL_SOCKET(socket.AF_INET, socket.SOCK_STREAM) as real:
                real.settimeout(value)
        self.timeout = value

    def gettimeout(self) -> float | None:
        return self.timeout

    def setsockopt(self, *args: Any) -> None:
        pass

    def setblocking(self, flag: bool) -> None:
        pass

    def bind(self, *args: Any) -> None:
        pass

    def connect(self, address: Any) -> None:
        self.connected_to = address
        if _FakeSocket.raise_ is not None:
            raise _FakeSocket.raise_

    def connect_ex(self, address: Any) -> int:
        self.connected_to = address
        exc = _FakeSocket.raise_
        if exc is None:
            return 0
        if isinstance(exc, OSError) and exc.errno:
            return exc.errno
        raise exc

    def close(self) -> None:
        self.closed = True

    def shutdown(self, *args: Any) -> None:
        pass

    def fileno(self) -> int:
        return -1

    def detach(self) -> int:
        return -1

    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class NetprobeTest(unittest.TestCase):
    """§2.6 item 11: engine.netprobe with socket stubs, then real loopback."""

    def _module(self) -> Any:
        if not NETPROBE.is_file():
            self.fail("engine/netprobe.py is missing (architecture §2.5 ci/offline)")
        return importlib.import_module("engine.netprobe")

    def _probe(self, raise_: BaseException | None, within: str = "2") -> tuple[int, str]:
        module = self._module()
        _FakeSocket.raise_ = raise_
        _FakeSocket.instances = []
        out = io.StringIO()
        with mock.patch("socket.socket", _FakeSocket), contextlib.redirect_stdout(out):
            try:
                code = module.main([*TARGET, "--within", within])
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
        return int(code or 0), out.getvalue()

    def _one_word(self, out: str) -> str:
        words = out.split()
        self.assertEqual(len(words), 1, f"netprobe prints exactly one word, got {out!r}")
        return words[0]

    def test_no_route_errnos_print_no_route_and_exit_1(self):
        for name in ("ENETUNREACH", "EHOSTUNREACH"):
            with self.subTest(errno=name):
                code, out = self._probe(OSError(getattr(errno, name), os.strerror(getattr(errno, name))))
                self.assertEqual(self._one_word(out), "no_route")
                self.assertEqual(code, 1)

    def test_refused_timeout_and_other_errors(self):
        cases = {
            "refused": (ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused"), r"refused"),
            "timeout": (TimeoutError("timed out"), r"timeout"),
            "socket.timeout": (socket.timeout("timed out"), r"timeout"),
            "EACCES": (PermissionError(errno.EACCES, "Permission denied"),
                       r"error:(?:EACCES|PermissionError)"),
            "EADDRNOTAVAIL": (OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address"),
                              r"error:(?:EADDRNOTAVAIL|OSError)"),
        }
        for case, (exc, word) in cases.items():
            with self.subTest(case=case):
                code, out = self._probe(exc)
                self.assertRegex(self._one_word(out), rf"^{word}$")
                self.assertNotEqual(code, 0, f"{case} must not exit 0 (only connected does)")

    def test_connected_exits_0_and_closes(self):
        code, out = self._probe(None)
        self.assertEqual(self._one_word(out), "connected")
        self.assertEqual(code, 0)
        self.assertTrue(_FakeSocket.instances, "netprobe opened no socket")
        sock = _FakeSocket.instances[-1]
        self.assertEqual(sock.connected_to[:2], ("192.0.2.10", 8100), "one TCP connect to <ip> <port>")
        self.assertTrue(sock.closed, "the probe socket is closed")

    def test_within_bounds_the_connect(self):
        for within in ("2", "5"):
            with self.subTest(within=within):
                self._probe(TimeoutError("timed out"), within=within)
                timeouts = [s.timeout for s in _FakeSocket.instances]
                self.assertIn(float(within), timeouts, f"--within {within} is the connect timeout")

    def test_real_loopback_connected_and_refused(self):
        self.assertTrue(NETPROBE.is_file(), "engine/netprobe.py is missing (architecture §2.5 ci/offline)")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            result = subprocess.run([sys.executable, "-m", "engine.netprobe", "127.0.0.1", str(port),
                                     "--within", "2"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        finally:
            listener.close()
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "connected"), result.stderr)
        result = subprocess.run([sys.executable, "-m", "engine.netprobe", "127.0.0.1", str(port),
                                 "--within", "2"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.stdout.strip(), "refused", result.stderr)
        self.assertNotEqual(result.returncode, 0)

    # -- rework round 1: review N6, security L-OCc ------------------------------

    BAD_ARGS = {
        "hostname localhost": ["localhost", "8100", "--within", "2"],
        "hostname example.invalid": ["example.invalid", "8100", "--within", "2"],
        "short dotted 172.30.0": ["172.30.0", "8100", "--within", "2"],
        "octet 300.1.2.3": ["300.1.2.3", "8100", "--within", "2"],
        "ipv6 fe80::1": ["fe80::1", "8100", "--within", "2"],
        "port 0": ["192.0.2.10", "0", "--within", "2"],
        "port 65536": ["192.0.2.10", "65536", "--within", "2"],
        "port -1": ["192.0.2.10", "-1", "--within", "2"],
        "port not a number": ["192.0.2.10", "http", "--within", "2"],
        "within 0": ["192.0.2.10", "8100", "--within", "0"],
        "within -1": ["192.0.2.10", "8100", "--within", "-1"],
        "within nan": ["192.0.2.10", "8100", "--within", "nan"],
        # Review NB1 (rework round 1): finite but past what settimeout takes
        # (OverflowError traceback), and infinity.
        "within 1e300": ["192.0.2.10", "8100", "--within", "1e300"],
        "within inf": ["192.0.2.10", "8100", "--within", "inf"],
        # Review NB2 (mutants MP5, MP6): argparse errors and non-ASCII digits.
        "missing port": ["192.0.2.10", "--within", "2"],
        "extra positional": ["192.0.2.10", "8100", "extra", "--within", "2"],
        "port arabic-indic digits": ["192.0.2.10", "\u0668\u0661\u0660\u0660", "--within", "2"],
        "port arabic-indic one": ["192.0.2.10", "\u0661", "--within", "2"],
    }

    def test_netprobe_rejects_bad_arguments_with_one_word(self):
        # A hostname is never resolved, the port is 1..65535 and --within > 0.
        # A bad argument prints one word, exits 1 and raises no traceback;
        # no socket is opened and no name is looked up.
        module = self._module()
        lookups: list[Any] = []

        def no_lookup(*args: Any, **kwargs: Any) -> Any:
            lookups.append(args)
            raise OSError("name lookup attempted")

        for case, argv in self.BAD_ARGS.items():
            with self.subTest(case=case):
                _FakeSocket.raise_ = None
                _FakeSocket.instances = []
                lookups.clear()
                out, err = io.StringIO(), io.StringIO()
                with mock.patch("socket.socket", _FakeSocket), \
                        mock.patch("socket.getaddrinfo", no_lookup), \
                        mock.patch("socket.gethostbyname", no_lookup), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        code: Any = module.main(list(argv))
                    except SystemExit as exc:
                        code = exc.code
                    except Exception as exc:  # noqa: BLE001 - the finding is the traceback
                        self.fail(f"{case}: main raised {exc!r} (a traceback, not a word)")
                self.assertEqual(code, 1, f"{case}: exit {code!r}, want 1 (stderr: {err.getvalue()!r})")
                word = self._one_word(out.getvalue())
                self.assertRegex(word, r"^[A-Za-z][\w:.-]*$")
                self.assertNotEqual(word, "connected")
                self.assertNotIn("Traceback", err.getvalue())
                self.assertEqual(lookups, [], f"{case}: a name lookup was attempted")
                self.assertEqual([s.connected_to for s in _FakeSocket.instances if s.connected_to], [],
                                 f"{case}: a connect was attempted")

    def test_netprobe_accepts_the_bounds(self):  # control for the rejections above
        module = self._module()
        for argv in (["192.0.2.10", "1", "--within", "0.5"], ["192.0.2.10", "65535", "--within", "2"]):
            with self.subTest(argv=argv):
                _FakeSocket.raise_ = None
                _FakeSocket.instances = []
                out = io.StringIO()
                with mock.patch("socket.socket", _FakeSocket), contextlib.redirect_stdout(out):
                    code = module.main(list(argv))
                self.assertEqual((code, out.getvalue().strip()), (0, "connected"))

    def test_netprobe_cli_bad_arguments_have_no_traceback(self):
        self.assertTrue(NETPROBE.is_file(), "engine/netprobe.py is missing")
        for case in ("port 65536", "within 0", "port 0", "within nan"):
            with self.subTest(case=case):
                result = subprocess.run([sys.executable, "-m", "engine.netprobe", *self.BAD_ARGS[case]],
                                        cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(len(result.stdout.split()), 1, f"one word on stdout: {result.stdout!r}")
                self.assertNotIn("Traceback", result.stderr)

    def test_netprobe_bad_arguments_print_exactly_bad_arguments_with_empty_stderr(self):
        # Review NB1/NB2: every BAD_ARGS case, in process, prints exactly
        # `bad_arguments`, returns 1 and writes nothing to stderr (no argparse
        # usage, no traceback). Kills MP5 (no _Parser.error override: usage on
        # stderr, exit 2) and MP6 (no isascii(): Arabic-Indic digits accepted).
        module = self._module()
        for case, argv in self.BAD_ARGS.items():
            with self.subTest(case=case):
                _FakeSocket.raise_ = None
                _FakeSocket.instances = []
                out, err = io.StringIO(), io.StringIO()
                with mock.patch("socket.socket", _FakeSocket), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        code: Any = module.main(list(argv))
                    except SystemExit as exc:
                        code = exc.code
                    except Exception as exc:  # noqa: BLE001 - the finding is the traceback
                        self.fail(f"{case}: main raised {exc!r} (a traceback, not bad_arguments)")
                self.assertEqual((code, out.getvalue()), (1, "bad_arguments\n"),
                                 f"{case}: want exit 1 and exactly `bad_arguments` (stderr: {err.getvalue()!r})")
                self.assertEqual(err.getvalue(), "", f"{case}: stderr must stay empty (no argparse usage)")
                self.assertEqual([s.connected_to for s in _FakeSocket.instances if s.connected_to], [],
                                 f"{case}: a connect was attempted")

    def test_netprobe_cli_bad_arguments_print_bad_arguments_and_nothing_on_stderr(self):
        # Review NB1/NB2, through the real CLI (`python -m engine.netprobe`)
        # with a real socket module: `--within 1e300` used to end in an
        # OverflowError traceback from settimeout.
        self.assertTrue(NETPROBE.is_file(), "engine/netprobe.py is missing")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        for case in ("within 1e300", "within inf", "missing port", "extra positional",
                     "port arabic-indic digits", "port arabic-indic one"):
            with self.subTest(case=case):
                result = subprocess.run([sys.executable, "-m", "engine.netprobe", *self.BAD_ARGS[case]],
                                        cwd=ROOT, env=env, capture_output=True, text=True,
                                        encoding="utf-8", timeout=30)
                self.assertEqual((result.returncode, result.stdout), (1, "bad_arguments\n"),
                                 f"{case}: stdout {result.stdout!r}, stderr {result.stderr!r}")
                self.assertEqual(result.stderr, "", f"{case}: stderr must be empty")

    def test_netprobe_runs_no_startup_and_reads_only_its_arguments(self):
        import ast

        self.assertTrue(NETPROBE.is_file(), "engine/netprobe.py is missing")
        tree = ast.parse(NETPROBE.read_text(encoding="utf-8"))
        imported: list[str] = []
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported += [f"{node.module or ''}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        for module in imported:
            with self.subTest(imports=module):
                self.assertNotRegex(module, r"startup|telemetry|opentelemetry|engine\.config",
                                    "netprobe is not an agent step: no startup(), no span (§2.5)")
        for name in ("startup", "environ", "getenv", "input", "stdin"):
            with self.subTest(uses=name):
                self.assertNotIn(name, names, "netprobe takes no input except its arguments (§2.5)")


# --------------------------------------------------------------------------
# smoke.sh host half: ci/offline against the fake docker
# --------------------------------------------------------------------------

def _is_control(record: dict) -> bool:
    argv = record["argv"]
    return (argv[:1] == ["run"] or argv[:2] == ["container", "run"]) and "engine.netprobe" in argv


def _probe_service(record: dict) -> str | None:
    argv = record["argv"]
    if argv[:1] != ["compose"] or "exec" not in argv or "engine.netprobe" not in argv:
        return None
    i = argv.index("exec") + 1
    while i < len(argv):
        if argv[i] in ("-e", "--env", "-u", "--user", "-w", "--workdir", "--index"):
            i += 2
            continue
        if argv[i].startswith("-"):
            i += 1
            continue
        return argv[i]
    return None


def _tail(argv: list[str]) -> list[str]:
    return argv[argv.index("engine.netprobe") + 1:]


def _pairs(argv: list[str]) -> set[tuple[str, str]]:
    out = set(zip(argv, argv[1:]))
    out |= {tuple(a.split("=", 1)) for a in argv if a.startswith("--") and "=" in a}  # type: ignore[misc]
    return out


class SmokeCiOfflineTest(unittest.TestCase):
    """§2.5 ci/offline, §2.6 item 11 smoke cases; PS-3.3."""

    setUp = tss.SmokeResolvesWithoutEnvTest.setUp
    _smoke = tss.SmokeBackendIsolatedTest._smoke

    @staticmethod
    def _probes(records: list[dict]) -> tuple[list[tuple[int, dict]], dict[str, list[tuple[int, dict]]]]:
        controls = [(i, r) for i, r in enumerate(records) if _is_control(r)]
        services: dict[str, list[tuple[int, dict]]] = {}
        for i, r in enumerate(records):
            svc = _probe_service(r)
            if svc:
                services.setdefault(svc, []).append((i, r))
        return controls, services

    def test_ci_offline_probes_api_and_worker_after_a_connected_control(self):
        cases = {
            "smoke launched the project": ({}, "ke-verify-test", "8100"),
            "verify owns the project": ({"FAKE_DOCKER_RUNNING": "0123456789ab",
                                         "KE_SMOKE_OWNS_PROJECT": "1"}, "ke-verify-test", "8100"),
            "an operator's running stack": ({"FAKE_DOCKER_RUNNING": "0123456789ab"}, "ke-verify-test", "8100"),
            "another project and API port": ({"FAKE_COMPOSE_RESOLVED": '{"KE_GATEWAY_API_LISTEN": "8123"}'},
                                             "ke-verify-x7q2", "8123"),
        }
        for case, (extra, project, port) in cases.items():
            with self.subTest(case=case):
                result, records = self._smoke(project, **extra)
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, out)
                self.assertIn("smoke: PASS", out)
                controls, services = self._probes(records)
                self.assertEqual(len(controls), 1, f"one control probe: {[r['argv'] for _, r in controls]}")
                c_index, control = controls[0]
                argv = control["argv"]
                self.assertIn("--rm", argv, "the control container is removed (--rm)")
                self.assertIn(("--network", f"{project}_edge"), _pairs(argv),
                              "the control runs on <project>_edge")
                self.assertIn(("--entrypoint", "python"), _pairs(argv))
                self.assertIn("ke-app:local", argv, "the control uses the api image from compose config")
                self.assertEqual(_tail(argv), ["172.30.0.2", port, "--within", "5"])
                inspects = [r["argv"] for r in records if r["argv"][:1] == ["inspect"]
                            or r["argv"][:2] == ["container", "inspect"]]
                self.assertTrue([a for a in inspects if "fakegateway000000" in a],
                                f"the target comes from inspecting `compose ps -q gateway`: {inspects}")
                for svc in ("api", "worker"):
                    self.assertIn(svc, services, f"{svc} was never probed (PS-3.3 both app containers)")
                    for index, record in services[svc]:
                        self.assertIn("-T", record["argv"])
                        self.assertEqual(_tail(record["argv"]), ["172.30.0.2", port, "--within", "2"])
                        self.assertLess(c_index, index, "the control runs first")
                readies = [i for i, r in enumerate(records) if "engine.readiness" in r["argv"]]
                self.assertTrue(readies and readies[0] < c_index, "ci/offline runs after the readiness check")

    def test_offline_probe_fails_when_control_fails(self):  # PS-3.3 *Control probe*
        for word in ("no_route", "timeout", "refused", "error:EACCES", ""):
            with self.subTest(control=word or "(nothing)"):
                result, records = self._smoke(FAKE_NETPROBE_CONTROL=word)
                out = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, f"control {word!r} but smoke passed:\n{out}")
                self.assertNotIn("smoke: PASS", out)
                self.assertRegex(out, r"(?i)ci/offline[^\n]*inconclusive|inconclusive[^\n]*ci/offline",
                                 "a failed control is `ci/offline inconclusive`, never a pass")
                _, services = self._probes(records)
                self.assertEqual(services, {}, "api/worker were probed after a failed control")
                steps = tss._smoke_steps(records)
                self.assertEqual(steps[-1], "teardown", f"smoke launched it, so it tears down: {steps}")

    def test_ci_offline_fails_naming_the_service_that_gets_out(self):
        for svc in ("api", "worker"):
            for word in ("connected", "timeout", "refused", "error:EACCES", ""):
                with self.subTest(service=svc, result=word or "(nothing)"):
                    result, _ = self._smoke(FAKE_NETPROBE=f'{{"{svc}": "{word}"}}')
                    out = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, f"{svc} printed {word!r} but smoke passed:\n{out}")
                    self.assertNotIn("smoke: PASS", out)
                    named = [l for l in out.splitlines()
                             if re.search(r"(?i)ci/offline", l) and re.search(rf"\b{svc}\b", l)]
                    self.assertTrue(named, f"the ci/offline failure must name {svc}:\n{out}")

    def test_ci_offline_control_never_pulls(self):
        # Review N2 (rework round 1): on an operator host without the api
        # image, the control `docker run` must fail, not reach for docker.io.
        text = (ROOT / "scripts" / "smoke.sh").read_text(encoding="utf-8")
        body = "\n".join(l for l in text.replace("\\\n", " ").splitlines()
                         if not l.lstrip().startswith("#"))
        runs = re.findall(r"\bdocker\s+(?:container\s+)?run\b[^\n]*", body)
        self.assertTrue([r for r in runs if "engine.netprobe" in r], f"no control `docker run`: {runs}")
        for run in runs:
            with self.subTest(run=run):
                self.assertRegex(run, r"(?:^|\s)--pull(?:\s+|=)never(?:\s|$)",
                                 "smoke.sh's `docker run` must pass --pull never (N2)")

    def test_ci_offline_inconclusive_names_the_target_the_control_probed(self):
        # DR38 run 2 (docs/evidence/platform-offline/dr38-runs.md): a copy of
        # smoke.sh whose control probes port 1 failed as inconclusive, but the
        # message said `<ip>:8100` because it interpolates $probe_port, not
        # the control's own target. Mutant: the control's port becomes 1. If
        # the control's port argument is its own variable (not probe_port),
        # the mutant sets that variable's single assignment to 1; otherwise it
        # replaces the argument itself. The inconclusive message must name the
        # address:port the fake docker recorded for the control.
        smoke = self.tmp / "scripts" / "smoke.sh"
        text = smoke.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        control_lines = [i for i, l in enumerate(lines) if not l.lstrip().startswith("#")
                         and "engine.netprobe" in l and re.search(r"\bdocker\s+(?:container\s+)?run\b", l)]
        self.assertEqual(len(control_lines), 1, "smoke.sh has one control `docker run ... engine.netprobe` line")
        line = lines[control_lines[0]]
        target = re.search(r"engine\.netprobe\s+(\S+)\s+(\S+)", line)
        self.assertIsNotNone(target, f"no `engine.netprobe <ip> <port>` on the control line: {line!r}")
        assert target is not None
        port_var = re.fullmatch(r'"?\$\{?(\w+)\}?"?', target.group(2))
        if port_var and port_var.group(1) != "probe_port":
            name = port_var.group(1)
            mutant, count = re.subn(rf"(?m)^(\s*(?:local\s+)?{name}=).*$", r"\g<1>1", text)
            self.assertEqual(count, 1, f"the control port variable {name} has one assignment")
        else:
            lines[control_lines[0]] = line[:target.start(2)] + "1" + line[target.end(2):]
            mutant = "".join(lines)
        self.assertNotEqual(mutant, text)
        smoke.write_text(mutant, encoding="utf-8", newline="\n")
        result, records = self._smoke(FAKE_NETPROBE_CONTROL="refused")
        out = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, out)
        self.assertNotIn("smoke: PASS", out)
        controls, services = self._probes(records)
        self.assertEqual(len(controls), 1, out)
        self.assertEqual(services, {}, "api/worker were probed after a failed control")
        probed_ip, probed_port = _tail(controls[0][1]["argv"])[:2]
        self.assertEqual(probed_port, "1", "precondition: the mutant control probes port 1")
        inconclusive = [l for l in out.splitlines() if re.search(r"(?i)inconclusive", l)]
        self.assertEqual(len(inconclusive), 1, out)
        self.assertIn(f"{probed_ip}:{probed_port}", inconclusive[0],
                      "the inconclusive message must name the address:port the control actually probed")
        self.assertNotIn(":8100", inconclusive[0], "the message names the app port, not the control's target")

    def test_ci_offline_refuses_a_non_ipv4_target(self):
        for value in ("", "fe80::1", "gateway", "300.1.2.3", "172.30.0", "172.30.0.2 172.30.0.3"):
            with self.subTest(target=value or "(empty)"):
                result, records = self._smoke(FAKE_GATEWAY_EDGE_IP=value)
                out = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, f"target {value!r} accepted:\n{out}")
                self.assertNotIn("smoke: PASS", out)
                controls, services = self._probes(records)
                self.assertEqual((controls, services), ([], {}), "probed a target that is not IPv4")


if __name__ == "__main__":
    unittest.main()
