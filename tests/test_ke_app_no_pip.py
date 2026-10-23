"""platform-sbom U1 round 2 (PSC-14): ke-app ships no pip.

Criteria: docs/requirements.md PSC-14 (amended 2026-10-23, U1 round 2; pip
dropped, human): "The last stage of `ke-app` removes the base's pip, and
removes `ensurepip`'s bundled pip wheel ... In the real image, pip is not
importable by the system Python, no pip distribution is installed in its
site-packages, no `pip` command is on `PATH`, and `ensurepip` has no bundled
pip wheel." Tags `[unit: test_ke_app_last_stage_removes_pip]` and `[full:
smoke: no pip in api]`. Design: docs/architecture.md ADR-KE-016 point 9 and
docs/evidence/platform-sbom/design-notes.md N10a (orchestrator ruling
2026-10-23: flatten the last stage, since a delete in a layer on the base
leaves pip in the saved tar).

Interface pinned here (tester, U1 round 2 RED, 2026-10-23):
- docker/app.Dockerfile has one stage `AS runtime` (FROM the base) whose
  RUNs include, after the libpq5 apt RUN, exactly
    RUN python -m pip uninstall -y pip \\
     && rm /usr/local/lib/python3.X/ensurepip/_bundled/pip-*.whl
  (`&&` only; `rm` with no flags, so no -f; X the base tag's minor;
  tests.test_psycopg_c.pip_removal_minor). The last stage is `FROM scratch`
  and its first instruction is `COPY --from=runtime / /`; its ENV PATH
  starts `/opt/venv/bin:`, has `/usr/local/bin` as an entry and no `$`
  (scratch has no PATH to extend), and LANG is `C.UTF-8`. No RUN of the last
  stage names pip, ensurepip or get-pip.
- Smoke (host half of scripts/smoke.sh, after the psycopg step): prints the
  line `== smoke: no pip ==`, runs `compose exec -T api
  /usr/local/bin/python3 -I -c CODE` where CODE walks `/usr` and `/opt` with
  os.walk for names matching `pip(3(\\.[0-9]+)?)?|pip-.+\\.(dist-info|whl)`
  and falls back to `importlib.util.find_spec("pip")`, and prints one token,
  the hits or `-`. The host compares the whole captured output only as a
  string with `-` (security M-1 pattern; U1 round 3, security I-6, N10a
  `[ "$pip_out" = - ]`): any other value, empty output, a second word or a
  second line fails with a `smoke: FAIL` line naming pip; a failed exec
  fails.
  The fake docker models the api's files (tests/fake_docker.py, "U1 round
  2": FAKE_API_FILES, FAKE_API_PIP_IMPORTABLE). The real check runs in the
  `full` smoke against the image verify builds.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from pathlib import Path

from tests import test_stack_scripts as tss
from tests.engine_support import ROOT
from tests.test_image_scan import _env_pairs, _stages
from tests.test_notice_ke_app import parse_base_ref
from tests.test_psycopg_c import (TARGET_APP_FLAT, _apt_installs, _exec_service, _packages, _Scratch,
                                  pip_removal_minor)

APP_DOCKERFILE = ROOT / "docker" / "app.Dockerfile"
PIP_WORD_RE = re.compile(r"(?<![\w.-])(?:pip3?(?:\.\d+)?|ensurepip|get-pip(?:\.py)?)(?![\w-])")


def last_stage_pip_problems(path: Path) -> list[str]:
    """test_ke_app_last_stage_removes_pip on `path` (N10a)."""
    stages = _stages(path)
    if not stages:
        return [f"{path.name}: no FROM"]
    problems: list[str] = []
    last = stages[-1]
    body = last["body"]
    if last["ref"] != "scratch":
        problems.append(f"the last stage is FROM {last['ref']!r}, not scratch: a delete in a stage FROM the base "
                        f"leaves pip in the base layer of the saved tar (N10a probe)")
    if not body or body[0][0] != "COPY" or body[0][1].split() != ["--from=runtime", "/", "/"]:
        problems.append("the last stage does not start with `COPY --from=runtime / /` (N10a)")
    env = dict(pair for keyword, rest in body if keyword == "ENV" for pair in _env_pairs(rest))
    path_env = env.get("PATH", "")
    if not path_env.startswith("/opt/venv/bin:") or "/usr/local/bin" not in path_env.split(":") or "$" in path_env:
        problems.append(f"the last stage's PATH must start /opt/venv/bin:, have /usr/local/bin and be spelled out "
                        f"(scratch has no $PATH; N10a): {path_env!r}")
    if env.get("LANG") != "C.UTF-8":
        problems.append(f"the last stage's LANG is {env.get('LANG')!r}, want 'C.UTF-8' (the base's, N10a)")
    for keyword, rest in body:
        if keyword == "RUN" and PIP_WORD_RE.search(rest):
            problems.append(f"the last stage runs pip, ensurepip or get-pip: {rest} (pip must not come back)")
    runtimes = [s for s in stages[:-1] if (s["name"] or "").lower() == "runtime"]
    if len(runtimes) != 1:
        return problems + [f"{path.name} has {len(runtimes)} stages `AS runtime`, want 1 (N10a)"]
    runtime = runtimes[0]
    py, _, _, ref_problems = parse_base_ref(runtime["ref"])
    problems += ref_problems
    rb = runtime["body"]
    apt = [n for n, (k, rest) in enumerate(rb) if k == "RUN"
           and any(p.split("=", 1)[0] == "libpq5" for words in _apt_installs(rest) for p in _packages(words))]
    pip = [(n, pip_removal_minor(rest)) for n, (k, rest) in enumerate(rb) if k == "RUN"
           and pip_removal_minor(rest) is not None]
    if len(pip) != 1:
        problems.append(f"runtime has {len(pip)} pip-removal RUNs, want exactly one `RUN python -m pip uninstall "
                        f"-y pip && rm /usr/local/lib/python{py or 'X.Y'}/ensurepip/_bundled/pip-*.whl` "
                        f"(`&&` only, rm with no -f; N10a)")
    else:
        n, minor = pip[0]
        if not apt or n < apt[0]:
            problems.append("runtime's pip-removal RUN does not come after its libpq5 apt RUN (N10a)")
        if py is not None and minor != py:
            problems.append(f"runtime removes the wheel under python{minor}, but the base tag's CPython is {py}")
    return problems


def _pip_controls() -> tuple[dict[str, str], dict[str, str]]:
    """(must pass, must fail) for test_ke_app_last_stage_removes_pip."""
    t = TARGET_APP_FLAT
    uninstall = "RUN python -m pip uninstall -y pip \\\n"
    wheel = " && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl\n"
    pip_run = uninstall + wheel
    apt_start = t.index("RUN apt-get update \\\n && apt-get install -y --no-install-recommends libpq5")
    apt_run = t[apt_start:t.index(pip_run)]
    env = ("ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \\\n"
           "    LANG=C.UTF-8 \\\n    PYTHONUNBUFFERED=1\n")
    assert apt_run and env in t
    passing = {
        "python3 -m pip uninstall --yes pip": t.replace("python -m pip uninstall -y pip",
                                                        "python3 -m pip uninstall --yes pip"),
        "ENV split over two instructions": t.replace(env, "ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin\n"
                                                          "ENV LANG=C.UTF-8 PYTHONUNBUFFERED=1\n"),
        "one line, extra spaces": t.replace(pip_run, "RUN  python -m pip uninstall -y pip  &&  rm "
                                                     "/usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl\n"),
    }
    failing = {
        "today's shape: no runtime stage, last stage FROM the base": (
            t[:t.index("FROM python:3.12-slim-bookworm@sha256:" + "3" * 64 + " AS runtime")]
            + "FROM python:3.12-slim-bookworm@sha256:" + "3" * 64 + "\nARG LIBPQ_VERSION\n" + apt_run
            + "ENV PATH=/opt/venv/bin:$PATH\nCOPY --from=builder /opt/venv /opt/venv\nUSER ke\n"),
        "U0 shape with the pip removal (pip still ships in the base layer)": (
            t.replace(" AS runtime", "").replace("FROM scratch\nCOPY --from=runtime / /\n", "")),
        "runtime without the pip removal": t.replace(pip_run, ""),
        "pip removal before the libpq5 RUN": t.replace(apt_run + pip_run, pip_run + apt_run),
        "pip removal in the scratch stage, not runtime": t.replace(pip_run, "").replace(
            "WORKDIR /app\nRUN useradd", "WORKDIR /app\n" + pip_run + "RUN useradd"),
        "uninstall without -y": t.replace("uninstall -y pip", "uninstall pip"),
        "pip3 uninstall, not python -m pip": t.replace("python -m pip uninstall", "pip3 uninstall"),
        "uninstall also removes setuptools": t.replace("uninstall -y pip \\", "uninstall -y pip setuptools \\"),
        "rm -f on the wheel": t.replace(" && rm /usr", " && rm -f /usr"),
        "rm -rf of the _bundled directory": t.replace("rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl",
                                                      "rm -rf /usr/local/lib/python3.12/ensurepip/_bundled"),
        "; instead of && (a missing pip passes)": t.replace(" && rm /usr/local", " ; rm /usr/local"),
        "|| true after the removal": t.replace("pip-*.whl\n", "pip-*.whl || true\n", 1),
        "uninstall and rm in two RUNs": t.replace(pip_run, uninstall.rstrip(" \\\n") + "\nRUN" + wheel[3:]),
        "the wheel glob widened to pip*.whl": t.replace("_bundled/pip-*.whl", "_bundled/pip*.whl"),
        "the wheel under python3.13, base 3.12": t.replace("python3.12/ensurepip", "python3.13/ensurepip"),
        "no wheel removal": t.replace(pip_run, "RUN python -m pip uninstall -y pip\n"),
        "last stage FROM runtime (its layers ship)": t.replace("FROM scratch\nCOPY --from=runtime / /\n",
                                                               "FROM runtime\n"),
        "last stage FROM the base": t.replace("FROM scratch\nCOPY --from=runtime / /\n",
                                              "FROM python:3.12-slim-bookworm@sha256:" + "3" * 64 + "\n"),
        "COPY --from=runtime / / not first": t.replace("COPY --from=runtime / /\n" + env, env + "COPY --from=runtime / /\n"),
        "COPY --from=builder / /": t.replace("COPY --from=runtime / /", "COPY --from=builder / /"),
        "PATH extends $PATH (empty under scratch)": t.replace(
            "PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin", "PATH=/opt/venv/bin:$PATH"),
        "PATH without /usr/local/bin": t.replace("/opt/venv/bin:/usr/local/bin:", "/opt/venv/bin:"),
        "PATH with /usr/local/bin/ only as a prefix of another entry": t.replace(
            "/opt/venv/bin:/usr/local/bin:", "/opt/venv/bin:/usr/local/bin2:"),
        "PATH not starting /opt/venv/bin:": t.replace("PATH=/opt/venv/bin:/usr/local/bin:", "PATH=/usr/local/bin:/opt/venv/bin:"),
        "no LANG": t.replace("    LANG=C.UTF-8 \\\n", ""),
        "LANG=C": t.replace("LANG=C.UTF-8", "LANG=C"),
        "the scratch stage restores pip with ensurepip": t.replace("RUN useradd", "RUN python -m ensurepip && useradd"),
        "two runtime stages": t.replace(" AS runtime\n", " AS runtime\nFROM python:3.12-slim-bookworm@sha256:"
                                        + "3" * 64 + " AS runtime\n"),
    }
    for name, text in failing.items():
        assert text != t, name
    return passing, failing


PIP_PASSING, PIP_CONTROLS = _pip_controls()


class KeAppNoPipStaticTest(unittest.TestCase):
    """PSC-14 (fast, static): docker/app.Dockerfile removes pip and flattens."""

    def test_ke_app_last_stage_removes_pip(self):
        """PSC-14, ADR-KE-016 point 9, N10a: stage `runtime` runs `python -m
        pip uninstall -y pip && rm /usr/local/lib/python3.12/ensurepip/
        _bundled/pip-*.whl` (no -f) after its libpq5 RUN; the last stage is
        `FROM scratch` starting `COPY --from=runtime / /`, with PATH starting
        /opt/venv/bin: and holding /usr/local/bin, and LANG=C.UTF-8. RED:
        today's last stage is FROM the base, there is no runtime stage and
        nothing removes pip."""
        s = _Scratch(self)
        with self.subTest(control="target shape (N10a) passes"):
            self.assertEqual(last_stage_pip_problems(s.write(TARGET_APP_FLAT, "app.Dockerfile")), [])
        for name, text in PIP_PASSING.items():
            with self.subTest(control=name):
                self.assertEqual(last_stage_pip_problems(s.write(text, "app.Dockerfile")), [],
                                 f"the check failed a control that must pass: {name}")
        for name, text in PIP_CONTROLS.items():
            with self.subTest(control=name):
                self.assertNotEqual(last_stage_pip_problems(s.write(text, "app.Dockerfile")), [],
                                    f"the check passed a control that must fail: {name}")
        self.assertEqual(last_stage_pip_problems(APP_DOCKERFILE), [])


# --------------------------------------------------------------------------
# Smoke: no pip in the live api (fake docker)
# --------------------------------------------------------------------------

_SITE = "/usr/local/lib/python3.12/site-packages"
_WHEEL = "/usr/local/lib/python3.12/ensurepip/_bundled/pip-25.0.1-py3-none-any.whl"
# The unmodified base's six hits (N10a probe).
BASE_PIP_FILES = ["/usr/local/bin/pip", "/usr/local/bin/pip3", "/usr/local/bin/pip3.12", f"{_SITE}/pip/",
                  f"{_SITE}/pip-25.0.1.dist-info/", _WHEEL]
# (?s): the joined argv holds the check's multi-line CODE.
NO_PIP_CHECK_RX = r"(?s)\bexec\b.*find_spec\(.pip.\)"


class SmokeNoPipTest(unittest.TestCase):
    """PSC-14 `[full: smoke: no pip in api]`, driven with the fake docker:
    the smoke host half checks the live api for pip after the psycopg step."""

    _smoke = tss.SmokeBackendIsolatedTest._smoke
    BASH_ERROR = re.compile(r"(?m)smoke\.sh: line \d+: ")

    def setUp(self) -> None:
        tss.SmokeResolvesWithoutEnvTest.setUp(self)  # type: ignore[arg-type]
        for rel in ("docker/app.Dockerfile", "docker/gates.Dockerfile"):
            dest = self.tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)

    @staticmethod
    def _execs(records: list[dict]) -> list[tuple[int, str | None, list[str]]]:
        return [(n, *_exec_service(r["argv"])) for n, r in enumerate(records)
                if r["argv"][:1] == ["compose"] and "exec" in r["argv"]]

    def _assert_fails(self, case: str, extra: dict[str, str], named: str | None = None) -> str:
        result, records = self._smoke(**extra)
        out = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, f"smoke passed with {case}:\n{out}")
        self.assertNotIn("smoke: PASS", out)
        self.assertIsNone(self.BASH_ERROR.search(out), f"smoke stopped on a bash error, not a named FAIL ({case}):\n{out}")
        fails = [l for l in out.splitlines() if "smoke: FAIL" in l and "pip" in l]
        self.assertTrue(fails, f"the failure must be a `smoke: FAIL` line naming pip ({case}):\n{out}")
        if named is not None:
            self.assertTrue([l for l in fails if named in l], f"the failure must name {named!r} ({case}):\n{out}")
        steps = tss._smoke_steps(records)
        self.assertEqual(steps[-1:], ["teardown"], f"smoke launched it, so it tears down: {steps}")
        return out

    def test_smoke_checks_no_pip_in_api(self):
        """The clean image passes; the check runs in api with `-T` as
        `/usr/local/bin/python3 -I -c CODE`, CODE walks /usr and /opt with
        os.walk and asks find_spec("pip"), after /readyz is ready and after
        the psycopg check, under a `== smoke: no pip ==` line. RED: smoke has
        no such step."""
        passing = {
            "clean image (the fake's default model)": {},
            "near misses: libpipeline, pipes.py, pipx, an empty _bundled": {
                "FAKE_API_FILES": "/usr/bin/pipx,/usr/local/lib/python3.12/pipes.py,"
                                  "/usr/share/doc/libpipeline1/changelog.gz,/opt/venv/lib/python3.12/"
                                  "site-packages/pipdeptree/"},
        }
        for case, extra in passing.items():
            with self.subTest(case=case):
                result, records = self._smoke(**extra)
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, out)
                self.assertIn("smoke: PASS", out)
                self.assertIn("== smoke: no pip ==", result.stdout, "smoke prints the step header")
                execs = self._execs(records)
                checks = [(n, svc, cmd) for n, svc, cmd in execs if cmd and "-c" in cmd
                          and 'find_spec("pip")' in " ".join(cmd)]
                self.assertEqual(len(checks), 1, f"smoke runs the no-pip check once in api: {[c for *_, c in execs]}")
                if not checks:
                    continue
                n, svc, cmd = checks[0]
                self.assertEqual(svc, "api", "the no-pip check runs in api")
                self.assertIn("-T", records[n]["argv"], "exec -T (no tty)")
                self.assertEqual(cmd[:2], ["/usr/local/bin/python3", "-I"],
                                 "the base interpreter, isolated: the venv's sys.path omits the system site-packages")
                code = cmd[cmd.index("-c") + 1]
                for needle in ("os.walk", '"/usr"', '"/opt"', 'find_spec("pip")'):
                    self.assertIn(needle, code, f"the no-pip CODE does not use {needle}")
                psycopg = [m for m, _, c in execs if "psycopg" in " ".join(c)]
                readies = [m for m, r in enumerate(records) if "engine.readiness" in r["argv"]
                           and tss.READY_RX.search(" ".join(r["argv"]))]
                self.assertTrue(readies and readies[0] < n, "the no-pip check runs once /readyz is ready")
                self.assertTrue(psycopg and max(psycopg) < n, "the no-pip check runs after the psycopg check")

    def test_smoke_fails_when_pip_is_in_api(self):
        """Each thing the base ships for pip fails smoke by name: the
        package, its dist-info, a pip command on PATH, ensurepip's bundled
        wheel, pip importable with nothing on disk to find, the whole
        unmodified base, a failed check, empty output, and `-` followed by
        a second line naming a pip path (round 3, security I-6). RED (round
        3): smoke reads only line 1 with `read -r`, so the second-line case
        passes."""
        failing = {
            "the pip package in site-packages": ({"FAKE_API_FILES": f"{_SITE}/pip/"}, f"{_SITE}/pip"),
            "pip's dist-info": ({"FAKE_API_FILES": f"{_SITE}/pip-25.0.1.dist-info/"}, "pip-25.0.1.dist-info"),
            "/usr/local/bin/pip3": ({"FAKE_API_FILES": "/usr/local/bin/pip3"}, "/usr/local/bin/pip3"),
            "/usr/local/bin/pip3.12": ({"FAKE_API_FILES": "/usr/local/bin/pip3.12"}, "/usr/local/bin/pip3.12"),
            "ensurepip's bundled wheel": ({"FAKE_API_FILES": _WHEEL}, _WHEEL),
            "pip in the venv": ({"FAKE_PQ_VENV_EXTRA": "pip"}, "/opt/venv/lib/python3.12/site-packages/pip"),
            "importable only (nothing on disk)": ({"FAKE_API_PIP_IMPORTABLE": "1"}, "importable"),
            "the unmodified base (six hits, N10a probe)": ({"FAKE_API_FILES": ",".join(BASE_PIP_FILES)}, _WHEEL),
            "the check fails in api": ({"FAKE_DOCKER_HOOKS": json.dumps([{"on": NO_PIP_CHECK_RX, "exit": 1}])}, None),
            # Orchestrator ruling, 2026-10-23: empty output is not clean (fail
            # closed, as M-1); supersedes N10a's `${pip_hits:--}`.
            "the check exits 0 and prints nothing": ({"FAKE_DOCKER_HOOKS": json.dumps(
                [{"on": NO_PIP_CHECK_RX, "stdout": "", "exit": 0}])}, None),
            # U1 round 3 (security I-6, review B6; N10a): the whole output is
            # compared, so `-` then a second line holding a pip path fails
            # (`read -r` kept only line 1).
            "the check prints `-`, then a second line with a pip path": ({"FAKE_DOCKER_HOOKS": json.dumps(
                [{"on": NO_PIP_CHECK_RX, "stdout": "-\n/usr/local/bin/pip\n", "exit": 0}])}, None),
        }
        for case, (extra, named) in failing.items():
            with self.subTest(case=case):
                self._assert_fails(case, extra, named)

    def test_smoke_never_evaluates_the_pip_token(self):
        """Security M-1 pattern: the check's output is container output. smoke
        compares the whole output only as a string with `-`, so
        no payload runs on the host (the marker file is never created) and
        each fails closed, naming pip. RED: smoke has no such step, so it
        passes."""
        for name, template in {
            "command substitution": "$(touch {m})",
            "backticks": "`touch {m}`",
            "array subscript": "0+PPID[$(touch {m})]",
            "dash, then a second word": "- $(touch {m})",
            "dash-prefixed token": "-$(touch {m})",
            "a pip path, then a command": "/usr/local/bin/pip;touch {m}",
        }.items():
            with self.subTest(case=name):
                marker = self.tmp / f"pip-marker-{abs(hash(name))}"
                payload = template.format(m=marker.as_posix())
                self.assertFalse(marker.exists(), "precondition")
                hooks = [{"on": NO_PIP_CHECK_RX, "stdout": payload + "\n", "exit": 0}]
                self._assert_fails(name, {"FAKE_DOCKER_HOOKS": json.dumps(hooks)})
                self.assertFalse(marker.exists(), f"smoke ran a command from the no-pip output on the host: {marker}")


if __name__ == "__main__":
    unittest.main()
