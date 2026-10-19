"""platform-stack-up (2a), rework round 1: the host scripts, driven against a
fake `docker` (tests/fake_docker.py) in a throwaway copy of the repo files.

Findings (docs/evidence/platform-stack/review.md, security.md; orchestrator
"rework round 1 of 5" in docs/handoffs/platform-stack.md):

- B3 + L-1 (PS-2.14, Q33a): launch.sh and launch.ps1 take KE_ENV and
  KE_BIND_ADDRESS from `docker compose config`, the values compose actually
  resolves, so every dotenv form compose honours is honoured
  (`export KEY=`, `KEY = `, `KEY: `). They never fall back to `.env.example`.
  An empty or unset KE_ENV is not dev (fail closed).
- B4 (PS-2.2 *Resolves without .env*): the host half of smoke.sh runs
  `docker compose config` with no `.env` and no env file. It fails if that
  fails, or if a published port does not bind 127.0.0.1.
- B5 (PS-2.9, architecture §2.2 *Lint*): `scripts/lint.sh` runs shellcheck on
  every `*.sh` under scripts/ and docker/, and PSScriptAnalyzer on every
  `scripts/*.ps1`. A finding fails it. The container half of verify.sh calls
  it before test.sh, in both modes. The gates image carries both tools.
- B6 (§2.2 *full*): the verify.sh host half runs these stages in order:
  build.sh, launch.sh, `compose run gates-it scripts/verify.sh full`, then
  smoke.sh. Any failing stage gives a non-zero exit. `teardown.sh --volumes`
  runs exactly once on success, on failure, and on SIGINT/SIGTERM. The
  project is `ke-verify-<random>`, different on every run. Every stage sees
  the verify overlay, and nothing publishes.
- N7: a teardown failure after a green run makes verify exit non-zero and
  name the teardown. It is never swallowed.

Rework round 2 (orchestrator "rework round 2 of 5"):

- R1-B2 + security L-6: launch.sh/.ps1 refuse any Engine version that is not
  numeric and >= 28 (empty, garbage, a leading space, a daemon error), before
  `compose up`. The fake answers `docker version` from FAKE_DOCKER_ENGINE.
- R1-B1 + security M-4: smoke.sh's host half asserts, with `docker network
  inspect` on the run's own `<project>_backend`, that the bridge carries
  gateway_mode_ipv4=isolated.
- Review N-3: a published port without host_ip counts as 0.0.0.0.
- Windows proof F3: teardown.sh/.ps1 activate no profile.
- Security L-7: lint.sh runs no code from a PowerShell filename.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from tests import fake_docker
from tests.engine_support import ROOT

VAR = "KE_BIND_ADDRESS"
PWSH_MISSING = ("pwsh is not on PATH: the gates image must carry pwsh with a pinned "
                "PSScriptAnalyzer (architecture §2.2 Lint, review B5)")
SHELLCHECK_MISSING = ("shellcheck is not on PATH: the gates image must carry it "
                      "(architecture §2.2 Lint, review B5)")
ENGINE_OK = "29.5.2"  # the Engine on the recorded Windows proof; >= 28


def _clean_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir()}
    env.update(extra)
    return env


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_repo_files(dest: Path, rels: list[str]) -> None:
    for rel in rels:
        src = ROOT / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, target)


def _env_text(lines: list[str]) -> str:
    """The .env.example contents without KE_ENV/KE_BIND_ADDRESS, plus `lines`."""
    base = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    kept = [l for l in base
            if not re.match(r"^\s*(?:export\s+)?(?:KE_ENV|KE_BIND_ADDRESS)\s*[=:]", l)]
    return "\n".join(kept + lines) + "\n"


# --------------------------------------------------------------------------
# B3 + L-1: launch reads resolved values from `docker compose config`
# --------------------------------------------------------------------------

class _LaunchResolvedBase:
    """Shared cases for launch.sh and launch.ps1. Subclasses set `script`
    and `command`."""

    script: str
    command: list[str]

    def setUp(self) -> None:  # noqa: D401 - unittest hook
        test: Any = self
        path = ROOT / self.script
        test.assertTrue(path.is_file(), f"{self.script} is missing (PS-2.9)")
        self.tmp = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.tmp, True)
        rels = [".env.example", "docker-compose.yml",
                *(str(p.relative_to(ROOT)).replace(os.sep, "/")
                  for p in (ROOT / "scripts").glob("*") if p.suffix in {".sh", ".ps1"})]
        _copy_repo_files(self.tmp, rels)
        fake_docker.install(self.tmp / "fakebin")
        self.log = self.tmp / "docker.log"
        self.json = self.tmp / "docker.jsonl"
        self.path = f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"

    def _launch(self, **env: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        for f in (self.log, self.json):
            f.write_text("", encoding="utf-8")
        # Rework 2 (ruling R1-B2 + security L-6, docs/handoffs/platform-stack.md
        # "orchestrator: rework round 2 of 5"): the fake now answers `docker
        # version` with FAKE_DOCKER_ENGINE, and an empty version is refused.
        # Every case that is not about the engine runs on a valid engine.
        env = {"FAKE_DOCKER_ENGINE": ENGINE_OK, **env}
        run_env = _clean_env(PATH=self.path, FAKE_DOCKER_LOG=str(self.log),
                             FAKE_DOCKER_JSON=str(self.json), **env)
        result = subprocess.run(self.command, env=run_env, cwd=self.tmp,
                                capture_output=True, text=True, timeout=120)
        return result, fake_docker.records(self.json)

    def _write(self, name: str, lines: list[str]) -> Path:
        path = self.tmp / name
        path.write_text(_env_text(lines), encoding="utf-8", newline="\n")
        return path

    @staticmethod
    def _ups(records: list[dict]) -> list[list[str]]:
        return [r["argv"] for r in records if r["argv"][:1] == ["compose"] and "up" in r["argv"]]

    @staticmethod
    def _configs(records: list[dict]) -> list[list[str]]:
        return [r["argv"] for r in records if r["argv"][:1] == ["compose"] and "config" in r["argv"]]

    def _assert_refused(self, result: subprocess.CompletedProcess, records: list[dict]) -> None:
        test: Any = self
        test.assertNotEqual(result.returncode, 0,
                            f"launch did not refuse:\n{result.stdout}{result.stderr}")
        test.assertIn(VAR, result.stdout + result.stderr)
        test.assertEqual(self._ups(records), [], "compose up ran despite the refusal")

    def test_launch_refuses_when_env_file_lacks_ke_env(self):  # B3
        test: Any = self
        cases = {
            ".env without KE_ENV": (".env", {}),
            "KE_ENV_FILE without KE_ENV": ("custom.env", "KE_ENV_FILE"),
        }
        for case, (name, how) in cases.items():
            with test.subTest(case=case):
                (self.tmp / ".env").unlink(missing_ok=True)
                path = self._write(name, [f"{VAR}=0.0.0.0"])
                env = {"KE_ENV_FILE": str(path)} if how == "KE_ENV_FILE" else {}
                result, records = self._launch(**env)
                self._assert_refused(result, records)

    def test_launch_never_falls_back_to_env_example(self):  # B3
        # .env.example says KE_ENV=dev; an env file that says nothing about
        # KE_ENV must not inherit it.
        test: Any = self
        example = (self.tmp / ".env.example").read_text(encoding="utf-8")
        test.assertRegex(example, r"(?m)^KE_ENV=dev\s*$", "precondition: .env.example ships dev")
        self._write(".env", [f"{VAR}=10.0.0.5", "KE_ENV="])
        result, records = self._launch()
        self._assert_refused(result, records)

    def test_launch_honours_every_dotenv_form_compose_honours(self):  # L-1
        test: Any = self
        forms = {
            "export KEY=": [f"export KE_ENV=prod", f"export {VAR}=0.0.0.0"],
            "KEY = value": [f"KE_ENV = prod", f"{VAR} = 0.0.0.0"],
            "KEY: value": [f"KE_ENV: prod", f"{VAR}: 0.0.0.0"],
            "quoted": ['KE_ENV="prod"', f"{VAR}='0.0.0.0'"],
            "only bind in export form, KE_ENV plain": ["KE_ENV=prod", f"export {VAR}=0.0.0.0"],
        }
        for form, lines in forms.items():
            with test.subTest(form=form):
                self._write(".env", lines)
                result, records = self._launch()
                self._assert_refused(result, records)

    def test_launch_trusts_compose_config_not_its_own_parser(self):  # L-1
        # The env file reads as loopback/prod, but compose resolves 0.0.0.0
        # (whatever the reason). Launch must act on what compose resolved.
        test: Any = self
        self._write(".env", ["KE_ENV=prod", f"{VAR}=127.0.0.1"])
        result, records = self._launch(
            FAKE_COMPOSE_RESOLVED=json.dumps({"KE_ENV": "prod", VAR: "0.0.0.0"}))
        test.assertTrue(self._configs(records), "launch never ran `docker compose config`")
        self._assert_refused(result, records)

    def test_launch_resolves_with_the_env_file_compose_will_use(self):  # B3
        test: Any = self
        custom = self._write("custom.env", ["KE_ENV=prod", f"{VAR}=127.0.0.1"])
        self._write(".env", ["KE_ENV=dev", f"{VAR}=127.0.0.1"])
        result, records = self._launch(KE_ENV_FILE=str(custom))
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        configs = self._configs(records)
        test.assertTrue(configs, "launch never ran `docker compose config`")
        for argv in configs:
            test.assertIn("--env-file", argv, "config must resolve with KE_ENV_FILE")
            test.assertNotIn("--no-interpolate", argv)
        ups = self._ups(records)
        test.assertTrue(ups, "compose up was not called")
        test.assertIn("--env-file", ups[-1])

    def test_launch_accepts_loopback_and_warns_for_dev(self):  # control
        test: Any = self
        cases = {"prod, loopback": (["KE_ENV=prod", f"{VAR}=127.0.0.1"], False),
                 "export forms, prod, loopback": (["export KE_ENV=prod", f"export {VAR}=127.0.0.1"],
                                                  False),
                 "dev, 0.0.0.0": (["KE_ENV=dev", f"{VAR}=0.0.0.0"], True)}
        for case, (lines, warns) in cases.items():
            with test.subTest(case=case):
                self._write(".env", lines)
                result, records = self._launch()
                test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                ups = self._ups(records)
                test.assertTrue(ups, "compose up was not called")
                test.assertIn("--wait", ups[-1])
                test.assertIn("--no-build", ups[-1])
                if warns:
                    test.assertIn(VAR, result.stdout + result.stderr)

    # -- Rework 2: R1-B2 + security L-6, the Docker Engine >= 28 check --------

    # platform-stack-ready (PS-2.24, review R2-N3, mutants L3-anchor and
    # L6-anchor): a suffixed build is refused (the version regex is anchored
    # at the end) and the major is compared as an integer (100 >= 28).
    ENGINE_ACCEPTED = {"28.0.0": "28.0.0", "29.5.2": "29.5.2", "100.0.0": "100.0.0"}
    ENGINE_REFUSED = {
        "28.0.1-rc.1 (suffixed build, R2-N3)": ("28.0.1-rc.1", None),
        "27.1.1": ("27.1.1", None),
        "27.99.99": ("27.99.99", None),
        "empty": ("", None),
        "garbage": ("garbage", None),
        "leading space 27.1.1": (" 27.1.1", None),
        # The daemon errors (non-zero exit) even though stdout looks valid:
        # the exit status, not the text, decides.
        "daemon error": (ENGINE_OK, "1"),
    }

    def test_launch_accepts_docker_engine_28_or_later(self):  # R1-B2
        test: Any = self
        for case, engine in self.ENGINE_ACCEPTED.items():
            with test.subTest(engine=case):
                self._write(".env", ["KE_ENV=prod", f"{VAR}=127.0.0.1"])
                result, records = self._launch(FAKE_DOCKER_ENGINE=engine)
                test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                test.assertTrue(self._ups(records), "compose up was not called")

    def test_launch_refuses_docker_engine_below_28_or_unreadable(self):  # R1-B2, L-6
        # Engines older than 28 silently ignore gateway_mode_ipv4=isolated
        # (security M-2), so anything that is not a numeric version >= 28 is
        # refused before `compose up`: fail closed.
        test: Any = self
        for case, (engine, exit_code) in self.ENGINE_REFUSED.items():
            with test.subTest(engine=case):
                self._write(".env", ["KE_ENV=prod", f"{VAR}=127.0.0.1"])
                env = {"FAKE_DOCKER_ENGINE": engine}
                if exit_code:
                    env["FAKE_DOCKER_ENGINE_EXIT"] = exit_code
                result, records = self._launch(**env)
                output = result.stdout + result.stderr
                test.assertNotEqual(result.returncode, 0,
                                    f"launch accepted Docker Engine {engine!r}:\n{output}")
                test.assertEqual(self._ups(records), [], "compose up ran despite the refusal")
                test.assertRegex(output, r"(?i)engine|daemon",
                                 "the refusal must say it is about the Docker Engine")

    # -- Rework 2: review N-3, a published port without host_ip -------------

    @staticmethod
    def _ports(*host_ips: str | None) -> str:
        ports = []
        for i, host_ip in enumerate(host_ips):
            port: dict[str, Any] = {"mode": "ingress", "target": 8100 + i,
                                    "published": str(47100 + i), "protocol": "tcp"}
            if host_ip is not None:
                port["host_ip"] = host_ip
            ports.append(port)
        return json.dumps(ports)

    def test_launch_treats_a_port_without_host_ip_as_all_interfaces(self):  # N-3
        # Compose omits host_ip when a port is published on every interface.
        # That is 0.0.0.0, so outside dev launch must refuse it.
        test: Any = self
        cases = {
            "no host_ip on any port, prod": (["KE_ENV=prod"], self._ports(None, None)),
            "loopback then no host_ip, prod": (["KE_ENV=prod"], self._ports("127.0.0.1", None)),
            "no host_ip then loopback, prod": (["KE_ENV=prod"], self._ports(None, "127.0.0.1")),
            "no host_ip, KE_ENV missing": ([], self._ports(None, None)),
            "empty host_ip, prod": (["KE_ENV=prod"], self._ports("", "")),
        }
        for case, (lines, ports) in cases.items():
            with test.subTest(case=case):
                self._write(".env", [*lines, f"{VAR}=127.0.0.1"])
                result, records = self._launch(FAKE_COMPOSE_PORTS=ports)
                self._assert_refused(result, records)

    def test_launch_port_without_host_ip_warns_in_dev(self):  # N-3 control
        test: Any = self
        self._write(".env", ["KE_ENV=dev", f"{VAR}=127.0.0.1"])
        result, records = self._launch(FAKE_COMPOSE_PORTS=self._ports(None, None))
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        test.assertTrue(self._ups(records), "compose up was not called")
        test.assertIn(VAR, result.stdout + result.stderr, "dev must warn about all interfaces")


class LaunchShResolvedTest(_LaunchResolvedBase, unittest.TestCase):
    script = "scripts/launch.sh"
    command = ["bash", "scripts/launch.sh"]


class LaunchPs1ResolvedTest(_LaunchResolvedBase, unittest.TestCase):
    """The same cases under real pwsh. The gates image gains pwsh for
    PSScriptAnalyzer (§2.2 Lint); this replaces the static-only weak spot
    recorded in the 2a RED handoff."""

    script = "scripts/launch.ps1"
    command = ["pwsh", "-NoProfile", "-NonInteractive", "-File", "scripts/launch.ps1"]

    def setUp(self) -> None:
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        super().setUp()


# --------------------------------------------------------------------------
# Rework 2, Windows proof F3: teardown touches only its own default services
# --------------------------------------------------------------------------

class _TeardownScopeBase:
    """F3 (docs/evidence/platform-stack/windows-proof-rework1.txt): teardown
    must not activate profiles (`--profile '*'` or any other), so it never
    removes the profile-only one-shots (gates, gates-it) another run started
    under the same project. Subclasses set `command` and `volumes_flag`."""

    command: list[str]
    volumes_flag: str

    def setUp(self) -> None:  # noqa: D401 - unittest hook
        self.tmp = Path(tempfile.mkdtemp())
        getattr(self, "addCleanup")(shutil.rmtree, self.tmp, True)
        rels = [".env.example", "docker-compose.yml",
                *(str(p.relative_to(ROOT)).replace(os.sep, "/")
                  for p in (ROOT / "scripts").glob("*") if p.suffix in {".sh", ".ps1"})]
        _copy_repo_files(self.tmp, rels)
        fake_docker.install(self.tmp / "fakebin")
        self.json = self.tmp / "docker.jsonl"

    def _teardown(self, *args: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json))
        result = subprocess.run([*self.command, *args], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=120)
        return result, fake_docker.records(self.json)

    def test_teardown_activates_no_profile(self):
        test: Any = self
        for args in ((), (self.volumes_flag,)):
            with test.subTest(args=" ".join(args) or "(none)"):
                result, records = self._teardown(*args)
                test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                downs = [r for r in records if r["argv"][:1] == ["compose"] and "down" in r["argv"]]
                test.assertTrue(downs, "teardown did not call compose down")
                for record in records:
                    argv = record["argv"]
                    test.assertFalse(
                        any(a == "--profile" or a.startswith("--profile=") for a in argv),
                        f"teardown activates a profile, so it removes other runs' gates/gates-it "
                        f"containers (F3): {argv}")
                    test.assertNotIn("COMPOSE_PROFILES", record["env"],
                                     f"teardown sets COMPOSE_PROFILES (F3): {argv}")
                    test.assertFalse({"gates", "gates-it"} & set(argv),
                                     f"teardown names a profile-only service (F3): {argv}")

    def test_teardown_script_has_no_profile_wildcard(self):
        test: Any = self
        script = ROOT / self.command[-1]
        body = "\n".join(l for l in script.read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith("#"))
        test.assertNotRegex(body, r"--profile|COMPOSE_PROFILES",
                            f"{script.name} activates profiles (F3)")

    # -- platform-stack-ready, PS-2.24 ---------------------------------------

    def test_teardown_does_not_remove_orphans(self):  # R2-N1, mutants T3/T4
        # §2.4 Teardown scope: no --remove-orphans (F3: only the project's
        # default-profile services).
        test: Any = self
        for args in ((), (self.volumes_flag,)):
            with test.subTest(args=" ".join(args) or "(none)"):
                result, records = self._teardown(*args)
                test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                downs = [r for r in records if r["argv"][:1] == ["compose"] and "down" in r["argv"]]
                test.assertTrue(downs, "teardown did not call compose down")
                for record in records:
                    test.assertNotIn("--remove-orphans", record["argv"],
                                     f"teardown passes --remove-orphans (F3): {record['argv']}")

    def test_teardown_carries_project_and_env_file(self):  # R2-N2, mutants T5/T8
        test: Any = self
        shutil.copy(self.tmp / ".env.example", self.tmp / "custom.env")
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), KE_ENV_FILE="custom.env",
                         COMPOSE_PROJECT_NAME="ke-verify-123")
        result = subprocess.run(self.command, cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=120)
        records = fake_docker.records(self.json)
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        downs = [r for r in records if r["argv"][:1] == ["compose"] and "down" in r["argv"]]
        test.assertTrue(downs, "teardown did not call compose down")
        for record in downs:
            argv = record["argv"]
            pairs = list(zip(argv, argv[1:]))
            test.assertTrue(("--env-file", "custom.env") in pairs
                            or "--env-file=custom.env" in argv,
                            f"down does not carry KE_ENV_FILE as --env-file: {argv}")
            project = record["env"].get("COMPOSE_PROJECT_NAME")
            test.assertTrue(project == "ke-verify-123"
                            or ("-p", "ke-verify-123") in pairs
                            or ("--project-name", "ke-verify-123") in pairs,
                            f"down does not carry the project ke-verify-123: {argv}, env={project!r}")


class TeardownShScopeTest(_TeardownScopeBase, unittest.TestCase):
    command = ["bash", "scripts/teardown.sh"]
    volumes_flag = "--volumes"


class TeardownPs1ScopeTest(_TeardownScopeBase, unittest.TestCase):
    command = ["pwsh", "-NoProfile", "-NonInteractive", "-File", "scripts/teardown.ps1"]
    volumes_flag = "-Volumes"

    def setUp(self) -> None:
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        super().setUp()


# --------------------------------------------------------------------------
# platform-stack-ready, PS-2.22 (security L-9, within ruling F3): teardown
# detects what is left of its project after `down`, reports it, exits
# non-zero, and never removes it (architecture §2.4 "Teardown leftovers").
# --------------------------------------------------------------------------

PROJECT_LABEL = "com.docker.compose.project"

# Calls that would remove or stop something. `compose down` is teardown's
# own job and is allowed; anything else on this list is not (F3).
def _destructive(argv: list[str]) -> bool:
    if argv[:1] == ["STUB"]:
        return False
    if argv[:1] == ["compose"]:
        return any(a in {"rm", "stop", "kill"} for a in argv)
    verbs = {"rm", "rmi", "kill", "stop", "prune", "remove"}
    if argv[:1] and argv[0] in verbs:
        return True
    return len(argv) >= 2 and argv[0] in {"container", "network", "volume", "system"} \
        and argv[1] in verbs


class _TeardownLeftoversBase:
    """Subclasses set `command` and `volumes_flag` (sh and ps1)."""

    command: list[str]
    volumes_flag: str
    PROJECT = "ke-verify-123"

    setUp = _TeardownScopeBase.setUp

    def _teardown(self, *args: str, project: str | None = PROJECT,
                  **extra: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), **extra)
        if project is not None:
            env["COMPOSE_PROJECT_NAME"] = project
        result = subprocess.run([*self.command, *args], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=120)
        return result, fake_docker.records(self.json)

    @staticmethod
    def _leftovers(project: str, **kinds: list[str]) -> str:
        return json.dumps({project: kinds})

    @staticmethod
    def _listings(records: list[dict]) -> list[list[str]]:
        return [r["argv"] for r in records
                if any(a.startswith(f"label={PROJECT_LABEL}=") for a in r["argv"])]

    def _assert_nothing_removed(self, records: list[dict]) -> None:
        test: Any = self
        for record in records:
            argv = record["argv"]
            test.assertFalse(_destructive(argv),
                             f"teardown removed or stopped something itself (F3): {argv}")
            test.assertFalse(any(a == "--profile" or a.startswith("--profile=") for a in argv),
                             f"teardown activates a profile (F3): {argv}")

    def test_teardown_removes_or_reports_project_leftovers(self):
        test: Any = self
        cases = {
            "leftover container": ((), {"containers": [f"{self.PROJECT}-gates-it-run-1a2b3c"]},
                                   f"{self.PROJECT}-gates-it-run-1a2b3c"),
            "leftover network": ((), {"networks": [f"{self.PROJECT}_backend"]},
                                 f"{self.PROJECT}_backend"),
            "leftover volume, volumes asked": ((self.volumes_flag,),
                                               {"volumes": [f"{self.PROJECT}_postgres-data"]},
                                               f"{self.PROJECT}_postgres-data"),
        }
        for case, (args, kinds, name) in cases.items():
            with test.subTest(case=case):
                result, records = self._teardown(
                    *args, FAKE_DOCKER_LEFTOVERS=self._leftovers(self.PROJECT, **kinds))
                output = result.stdout + result.stderr
                test.assertNotEqual(result.returncode, 0,
                                    f"teardown exited 0 with a leftover ({case}):\n{output}")
                test.assertIn(self.PROJECT, output, "the report must name the project")
                test.assertIn(name, output, "the report must name the leftover")
                downs = [r for r in records if r["argv"][:1] == ["compose"] and "down" in r["argv"]]
                test.assertTrue(downs, "teardown did not call compose down")
                self._assert_nothing_removed(records)

    def test_teardown_kept_volume_is_not_a_leftover_without_volumes(self):
        test: Any = self
        result, records = self._teardown(
            FAKE_DOCKER_LEFTOVERS=self._leftovers(self.PROJECT,
                                                  volumes=[f"{self.PROJECT}_postgres-data"]))
        test.assertEqual(result.returncode, 0,
                         "kept volumes are the point of a teardown without "
                         f"{self.volumes_flag}:\n{result.stdout}{result.stderr}")
        self._assert_nothing_removed(records)

    def test_teardown_with_nothing_left_passes(self):
        test: Any = self
        for args in ((), (self.volumes_flag,)):
            with test.subTest(args=" ".join(args) or "(none)"):
                result, records = self._teardown(*args)
                test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                listings = self._listings(records)
                test.assertTrue(listings, "teardown never listed what is left of its project")
                self._assert_nothing_removed(records)

    def test_teardown_lists_with_the_project_compose_resolves(self):
        test: Any = self
        cases = {"ke-verify-123": "ke-verify-123", "default project": None}
        for case, project in cases.items():
            with test.subTest(project=case):
                result, records = self._teardown(project=project)
                test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                expected = f"label={PROJECT_LABEL}={project or 'knowledge-engine'}"
                listings = self._listings(records)
                kinds = {"containers": False, "networks": False}
                for argv in listings:
                    test.assertIn(expected, argv, f"a listing filters on another project: {argv}")
                    if argv[:1] == ["ps"] or argv[:1] == ["container"]:
                        kinds["containers"] = True
                    if argv[:1] == ["network"]:
                        kinds["networks"] = True
                test.assertEqual(kinds, {"containers": True, "networks": True},
                                 f"teardown must list containers and networks: {listings}")
                configs = [r for r in records if r["argv"][:1] == ["compose"] and "config" in r["argv"]]
                test.assertTrue(configs, "teardown must resolve the project with compose config")

    def test_teardown_fails_when_a_listing_fails(self):
        test: Any = self
        result, records = self._teardown(FAKE_DOCKER_FAIL=f"label={PROJECT_LABEL}=")
        test.assertNotEqual(result.returncode, 0,
                            "teardown passed although it could not list leftovers")
        self._assert_nothing_removed(records)

    def test_teardown_fails_without_a_resolved_project(self):
        test: Any = self
        result, records = self._teardown(FAKE_DOCKER_FAIL="config")
        test.assertNotEqual(result.returncode, 0,
                            "teardown passed although compose config (the project name) failed")
        downs = [r for r in records if r["argv"][:1] == ["compose"] and "down" in r["argv"]]
        test.assertEqual(downs, [], "down ran without a resolved project name")

    def test_teardown_leaves_other_projects_alone(self):
        test: Any = self
        other = "ke-verify-999"
        result, records = self._teardown(
            self.volumes_flag,
            FAKE_DOCKER_LEFTOVERS=self._leftovers(
                other, containers=[f"{other}-gates-1"], networks=[f"{other}_backend"],
                volumes=[f"{other}_postgres-data"]))
        output = result.stdout + result.stderr
        test.assertEqual(result.returncode, 0,
                         f"another project's resources failed this teardown:\n{output}")
        test.assertNotIn(other, output)
        for record in records:
            test.assertNotIn(other, " ".join(record["argv"]),
                             f"teardown touched another project: {record['argv']}")
        self._assert_nothing_removed(records)


class TeardownShLeftoversTest(_TeardownLeftoversBase, unittest.TestCase):
    command = ["bash", "scripts/teardown.sh"]
    volumes_flag = "--volumes"


class TeardownPs1LeftoversTest(_TeardownLeftoversBase, unittest.TestCase):
    command = ["pwsh", "-NoProfile", "-NonInteractive", "-File", "scripts/teardown.ps1"]
    volumes_flag = "-Volumes"

    def setUp(self) -> None:
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        _TeardownScopeBase.setUp(self)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# B6 + N7: the verify.sh host half
# --------------------------------------------------------------------------

STAGE_STUB = """#!/usr/bin/env bash
name="{name}"
echo "$name $* | project=${{COMPOSE_PROJECT_NAME:-}} | file=${{COMPOSE_FILE:-}} | owns=${{KE_SMOKE_OWNS_PROJECT-<unset>}}" >> "$STAGE_LOG"
case "|${{HANG_STAGE:-}}|" in *"|$name|"*) exec sleep 60 ;; esac
case "|${{FAIL_STAGE:-}}|" in *"|$name|"*) echo "stub $name: failing" >&2; exit 7 ;; esac
exit 0
"""

DOCKER_STUB = """#!/usr/bin/env bash
echo "docker $* | project=${COMPOSE_PROJECT_NAME:-} | file=${COMPOSE_FILE:-} | sep=${COMPOSE_PATH_SEPARATOR:-}" >> "$STAGE_LOG"
case "$*" in *gates-it*)
  case "|${FAIL_STAGE:-}|" in *"|gates-it|"*) echo "stub gates-it: failing" >&2; exit 7 ;; esac ;;
esac
case "$*" in *"compose version"*"--short"*) echo "2.29.7" ;; esac
exit 0
"""


class VerifyHostHalfTest(unittest.TestCase):
    """B6, N7: the real scripts/verify.sh in a throwaway project, with
    recording stubs for build/launch/smoke/teardown and a recording docker."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "verify.sh", self.tmp / "scripts" / "verify.sh")
        for rel in (".env.example", "docker-compose.yml", "docker-compose.verify.yml"):
            if (ROOT / rel).exists():
                shutil.copy(ROOT / rel, self.tmp / rel)
        for name in ("build", "launch", "smoke", "teardown", "lint", "test"):
            stub = self.tmp / "scripts" / f"{name}.sh"
            stub.write_text(STAGE_STUB.format(name=name), encoding="utf-8", newline="\n")
            _make_executable(stub)
        # platform-stack-ready, ruling W1 (docs/handoffs/platform-stack-ready.md
        # "orchestrator: rulings on architect plan"): verify.sh full calls
        # scripts/env_value.sh for the two model keys (PS-2.21, §2.2). This
        # fixture-only stub prints the caller's value, logs nothing to
        # STAGE_LOG, and leaves every assertion below unchanged. The real
        # helper is tested in tests/test_stack_model_keys.py.
        env_value = self.tmp / "scripts" / "env_value.sh"
        env_value.write_text('#!/usr/bin/env bash\nprintf \'%s\' "${!1-}"\n',
                             encoding="utf-8", newline="\n")
        _make_executable(env_value)
        (self.tmp / "bin").mkdir()
        docker = self.tmp / "bin" / "docker"
        docker.write_text(DOCKER_STUB, encoding="utf-8", newline="\n")
        _make_executable(docker)
        self.log = self.tmp / "stages.log"

    def _env(self, **extra: str) -> dict[str, str]:
        env = _clean_env(PATH=f"{self.tmp / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         STAGE_LOG=str(self.log), **extra)
        return env  # KE_IN_GATES deliberately absent: this is the host half

    def _verify(self, mode: str = "full", **extra: str) -> tuple[subprocess.CompletedProcess, list[str]]:
        self.log.write_text("", encoding="utf-8")
        result = subprocess.run(["bash", "scripts/verify.sh", mode], cwd=self.tmp,
                                env=self._env(**extra), capture_output=True, text=True, timeout=60)
        return result, self.log.read_text(encoding="utf-8").splitlines()

    @staticmethod
    def _stage(line: str) -> str:
        head = line.split(" | ", 1)[0]
        if head.startswith("docker ") and "gates-it" in head:
            return "gates-it"
        if head.startswith("docker "):
            return "docker"
        return head.split(" ", 1)[0]

    def _stages(self, lines: list[str]) -> list[str]:
        return [self._stage(l) for l in lines if self._stage(l) != "docker"]

    def test_full_runs_stages_in_order_then_tears_down(self):
        result, lines = self._verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._stages(lines), ["build", "launch", "gates-it", "smoke", "teardown"])
        gates_it = [l for l in lines if self._stage(l) == "gates-it"]
        self.assertEqual(len(gates_it), 1)
        head = gates_it[0].split(" | ", 1)[0]
        self.assertRegex(head, r"\bcompose\b.*\brun\b.*\bgates-it\s+scripts/verify\.sh\s+full\b",
                         "the gates-it stage must run `scripts/verify.sh full` in gates-it")
        teardown = [l for l in lines if self._stage(l) == "teardown"]
        self.assertRegex(teardown[0].split(" | ", 1)[0], r"(?:^|\s)--volumes(?:\s|$)")

    def test_removing_the_gates_it_stage_is_caught(self):  # V7 mutant
        # A copy of verify.sh with the gates-it run line deleted must not pass
        # this suite's order check; proves the check above is not vacuous.
        text = (self.tmp / "scripts" / "verify.sh").read_text(encoding="utf-8")
        kept: list[str] = []
        skipping = False
        for line in text.splitlines():
            if skipping or ("gates-it" in line and not line.lstrip().startswith("#")):
                # Drop the command and its backslash continuations, so the
                # mutant cannot leave a bare `scripts/verify.sh full` behind.
                skipping = line.rstrip().endswith("\\")
                continue
            kept.append(line)
        mutant = "\n".join(kept)
        self.assertNotEqual(mutant.strip(), text.strip(), "verify.sh has no gates-it line to remove")
        self.assertNotRegex(mutant, r"(?m)^\s*scripts/verify\.sh\s+full", "mutant would recurse")
        (self.tmp / "scripts" / "verify.sh").write_text(mutant + "\n", encoding="utf-8", newline="\n")
        result, lines = self._verify()
        self.assertNotEqual(self._stages(lines), ["build", "launch", "gates-it", "smoke", "teardown"])

    def test_each_failing_stage_fails_verify_and_still_tears_down(self):
        expected = ["build", "launch", "gates-it", "smoke"]
        for i, stage in enumerate(expected):
            with self.subTest(failing=stage):
                result, lines = self._verify(FAIL_STAGE=stage)
                self.assertNotEqual(result.returncode, 0, f"{stage} failed but verify exited 0")
                self.assertNotIn("verify full: PASS", result.stdout + result.stderr)
                stages = self._stages(lines)
                self.assertEqual(stages, expected[: i + 1] + ["teardown"],
                                 "later stages ran after a failure, or teardown did not run once")

    def test_teardown_runs_on_interrupt(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig.name):
                self.log.write_text("", encoding="utf-8")
                proc = subprocess.Popen(["bash", "scripts/verify.sh", "full"], cwd=self.tmp,
                                        env=self._env(HANG_STAGE="launch"),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=True)
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        if any(l.startswith("launch") for l in self.log.read_text().splitlines()):
                            break
                        time.sleep(0.1)
                    else:
                        self.fail("verify never reached the launch stage")
                    time.sleep(0.3)
                    os.killpg(proc.pid, sig)  # the whole group, as a terminal Ctrl-C does
                    proc.communicate(timeout=30)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                stages = self._stages(self.log.read_text(encoding="utf-8").splitlines())
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(stages.count("teardown"), 1, f"teardown on {sig.name}: {stages}")
                self.assertNotIn("gates-it", stages)
                self.assertNotIn("smoke", stages)

    def test_project_name_is_random_and_shared_by_every_stage(self):
        names = []
        for _ in range(2):
            result, lines = self._verify()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            projects = {l.split("project=", 1)[1].split(" | ", 1)[0]
                        for l in lines if self._stage(l) != "docker" or "gates-it" in l}
            self.assertEqual(len(projects), 1, f"stages used different projects: {projects}")
            name = projects.pop()
            self.assertRegex(name, r"^ke-verify-[a-z0-9]+$")
            names.append(name)
        self.assertNotEqual(names[0], names[1], "the project name is not random per run")

    def test_every_stage_sees_the_verify_overlay_and_nothing_publishes(self):
        result, lines = self._verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for line in lines:
            head, _, rest = line.partition(" | ")
            with self.subTest(call=head):
                overlay = "docker-compose.verify.yml" in rest or "docker-compose.verify.yml" in head
                self.assertTrue(overlay, "a stage ran without the verify overlay (it would publish)")
                self.assertNotRegex(head, r"(?:^|\s)(?:-p|--publish|--service-ports)(?:\s|=|$)")

    def test_verify_overlay_resets_every_published_port(self):
        import yaml

        from tests import compose_support as cs

        class Reset:
            def __init__(self, value: Any) -> None:
                self.value = value

        class Loader(yaml.SafeLoader):
            pass

        def reset(loader: Any, node: Any) -> Any:
            if isinstance(node, yaml.SequenceNode):
                return Reset(loader.construct_sequence(node))
            return Reset(loader.construct_scalar(node))

        Loader.add_constructor("!reset", reset)
        overlay_path = ROOT / "docker-compose.verify.yml"
        self.assertTrue(overlay_path.is_file(), "docker-compose.verify.yml is missing (§2.2)")
        overlay = (yaml.load(overlay_path.read_text(encoding="utf-8"), Loader=Loader) or {})  # noqa: S506
        reset_services = overlay.get("services") or {}
        publishers = [n for n, svc in cs.services().items() if cs.port_entries(svc)]
        self.assertTrue(publishers, "precondition: the stack publishes something")
        for name in publishers:
            with self.subTest(service=name):
                ports = (reset_services.get(name) or {}).get("ports")
                self.assertIsInstance(ports, Reset, f"{name}: ports are not `!reset` in the overlay")
                self.assertEqual(ports.value, [])

    def test_verify_full_marks_its_own_project_for_smoke(self):
        # Orchestrator ruling "Q37 vs CI": the host half exports
        # KE_SMOKE_OWNS_PROJECT=1 for its own random project before smoke, so
        # smoke runs the postgres stop/restart and leaves teardown to verify.
        result, lines = self._verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        smoke = [l for l in lines if self._stage(l) == "smoke"]
        self.assertEqual(len(smoke), 1)
        self.assertRegex(smoke[0], r"\| project=ke-verify-[a-z0-9]+ \|")
        self.assertTrue(smoke[0].endswith("| owns=1"),
                        f"smoke did not get KE_SMOKE_OWNS_PROJECT=1: {smoke[0]}")

    def test_verify_fast_does_not_set_the_smoke_flag(self):
        result, lines = self._verify("fast")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse([l for l in lines if "owns=1" in l], lines)

    def test_teardown_failure_after_green_run_is_reported(self):  # N7
        result, lines = self._verify(FAIL_STAGE="teardown")
        output = result.stdout + result.stderr
        self.assertEqual(self._stages(lines), ["build", "launch", "gates-it", "smoke", "teardown"])
        self.assertNotEqual(result.returncode, 0, "a failed teardown was swallowed (rc=0)")
        self.assertRegex(output, r"(?i)teardown", "verify must name the failed teardown")

    def test_gates_mask_overlay_only_when_env_exists(self):  # PS-3.5
        # With a repo-root .env, both modes add the overlay that masks it for
        # the gate services; without one, no overlay (a mount point cannot be
        # created in the read-only checkout).
        for mode in ("fast", "full"):
            for has_env in (False, True):
                with self.subTest(mode=mode, env=has_env):
                    env_file = self.tmp / ".env"
                    env_file.unlink(missing_ok=True)
                    if has_env:
                        env_file.write_text("KE_STORES__POSTGRES__PASSWORD=secret\n", encoding="utf-8")
                    result, lines = self._verify(mode)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    gates = [l for l in lines if re.search(r"\b(gates|gates-it)\s+scripts/verify\.sh", l)]
                    self.assertEqual(len(gates), 1, lines)
                    masked = "docker-compose.gates-mask.yml" in gates[0]
                    self.assertEqual(masked, has_env, gates[0])
        env_file.unlink(missing_ok=True)

    def test_gates_compose_files_are_pinned_whatever_the_caller_sets(self):  # security M-1
        # A caller COMPOSE_FILE, or an auto-loaded docker-compose.override.yml,
        # could replace `.:/work:ro`. Both modes pin COMPOSE_FILE to the repo's
        # own files, with a ":" separator, with and without a repo-root .env.
        (self.tmp / "docker-compose.override.yml").write_text(
            "services:\n  gates:\n    volumes:\n      - .:/work\n", encoding="utf-8")
        env_file = self.tmp / ".env"
        for mode in ("fast", "full"):
            for has_env in (False, True):
                with self.subTest(mode=mode, env=has_env):
                    env_file.unlink(missing_ok=True)
                    if has_env:
                        env_file.write_text("KE_X=1\n", encoding="utf-8")
                    result, lines = self._verify(mode, COMPOSE_FILE="evil.yml;rw-overlay.yml",
                                                 COMPOSE_PATH_SEPARATOR=";")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    gates = [l for l in lines if re.search(r"\b(gates|gates-it)\s+scripts/verify\.sh", l)]
                    self.assertEqual(len(gates), 1, lines)
                    files = re.search(r"\| file=(\S*)", gates[0])
                    self.assertIsNotNone(files, gates[0])
                    assert files is not None
                    base = ("docker-compose.yml:docker-compose.verify.yml" if mode == "full"
                            else "docker-compose.yml")
                    expected = base + (":docker-compose.gates-mask.yml" if has_env else "")
                    self.assertEqual(files.group(1), expected, gates[0])
                    self.assertTrue(gates[0].endswith("| sep=:"), gates[0])
        env_file.unlink(missing_ok=True)

    def test_fast_runs_gates_without_publishing(self):
        result, lines = self._verify("fast")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [l.split(" | ", 1)[0] for l in lines]
        self.assertEqual(len(calls), 1, calls)
        self.assertRegex(calls[0], r"\bcompose\b.*\brun\b.*\bgates\s+scripts/verify\.sh\s+fast\b")
        self.assertNotRegex(calls[0], r"(?:^|\s)(?:-p|--publish|--service-ports)(?:\s|=|$)")


# --------------------------------------------------------------------------
# B5: scripts/lint.sh
# --------------------------------------------------------------------------

LINT = ROOT / "scripts" / "lint.sh"

RECORDER = """#!/usr/bin/env bash
printf '%s\\n' "{name} $*" >> "$LINT_LOG"
# PS-2.23 (N-1, N-5): the .ps1 paths reach the analyzer only through
# KE_LINT_PS1_FILES (security L-7), so the recorder keeps that list too.
if [ "{name}" = pwsh ]; then printf '%s' "${{KE_LINT_PS1_FILES-}}" >> "$LINT_LOG.ps1files"; fi
case "|${{LINT_FAIL:-}}|" in *"|{name}|"*) exit 1 ;; esac
exit 0
"""


def _repo_shell_files() -> list[str]:
    found = [*(ROOT / "scripts").rglob("*.sh"), *(ROOT / "docker").rglob("*.sh")]
    return sorted(str(p.relative_to(ROOT)).replace(os.sep, "/") for p in found)


def _repo_ps1_files() -> list[str]:
    return sorted(str(p.relative_to(ROOT)).replace(os.sep, "/")
                  for p in (ROOT / "scripts").glob("*.ps1"))


class LintScriptTest(unittest.TestCase):
    """B5: scripts/lint.sh, first with recording stand-ins for the two tools
    (coverage of every file, failure propagation), then with the real tools
    (the gates image has them; a planted finding fails the gate)."""

    def _project(self) -> Path:
        self.assertTrue(LINT.is_file(), "scripts/lint.sh is missing (PS-2.9, §2.2 Lint)")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        _copy_repo_files(tmp, ["scripts/lint.sh", *_repo_shell_files(), *_repo_ps1_files()])
        # Some implementations list files with git; give them a repository.
        # autocrlf off (review R2-N9 = rework-1 N-8): no LF/CRLF warning flood.
        if shutil.which("git"):
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"], cwd=tmp, check=True)
        return tmp

    def _run(self, project: Path, path: str, **extra: str) -> subprocess.CompletedProcess:
        env = _clean_env(PATH=path, **extra)
        return subprocess.run(["bash", "scripts/lint.sh"], cwd=project, env=env,
                              capture_output=True, text=True, timeout=600)

    def _with_recorders(self) -> tuple[Path, str, Path]:
        project = self._project()
        bin_dir = project / "fakebin"
        bin_dir.mkdir()
        for name in ("shellcheck", "pwsh"):
            tool = bin_dir / name
            tool.write_text(RECORDER.format(name=name), encoding="utf-8", newline="\n")
            _make_executable(tool)
        log = project / "lint.log"
        return project, f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", log

    def test_lint_covers_every_shell_and_powershell_script(self):
        project, path, log = self._with_recorders()
        # PS-2.23 (rework-1 N-1, N-5): a .ps1 in a subdirectory is covered too,
        # and every .ps1 reaches the analyzer by its own path.
        nested = "scripts/sub/nested.ps1"
        (project / nested).parent.mkdir(parents=True, exist_ok=True)
        (project / nested).write_text("Write-Output 'ok'\n", encoding="utf-8", newline="\n")
        result = self._run(project, path, LINT_LOG=str(log))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        checked = " ".join(c for c in calls if c.startswith("shellcheck "))
        for rel in _repo_shell_files():
            with self.subTest(sh=rel):
                self.assertRegex(checked, rf"(?:^|[\s/]){re.escape(rel)}(?:\s|$)",
                                 f"shellcheck never saw {rel}")
        analyzer = [c for c in calls if c.startswith("pwsh ")]
        self.assertTrue(analyzer, "PSScriptAnalyzer (pwsh) was never run")
        joined = " ".join(analyzer)
        self.assertIn("Invoke-ScriptAnalyzer", joined)
        for rel in _repo_ps1_files():
            with self.subTest(ps1=rel):
                name = rel.rsplit("/", 1)[-1]
                self.assertTrue(name in joined or re.search(r"\bscripts\b", joined),
                                f"PSScriptAnalyzer never saw {rel}")
        listed_file = Path(f"{log}.ps1files")
        listed = {l.removeprefix("./") for l in
                  (listed_file.read_text(encoding="utf-8").splitlines() if listed_file.exists() else [])
                  if l}
        for rel in [*_repo_ps1_files(), nested]:
            with self.subTest(ps1_path=rel):
                self.assertIn(rel, listed,
                              f"{rel} is not passed to PSScriptAnalyzer by its own path "
                              f"(KE_LINT_PS1_FILES held {sorted(listed)})")

    def test_lint_fails_when_either_tool_fails(self):
        for tool in ("shellcheck", "pwsh"):
            with self.subTest(failing=tool):
                project, path, log = self._with_recorders()
                result = self._run(project, path, LINT_LOG=str(log), LINT_FAIL=tool)
                self.assertNotEqual(result.returncode, 0, f"lint.sh passed although {tool} failed")

    def test_gates_image_has_shellcheck_and_psscriptanalyzer(self):
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command",
             "Import-Module PSScriptAnalyzer -ErrorAction Stop; "
             "(Get-Module PSScriptAnalyzer).Version.ToString()"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, f"PSScriptAnalyzer is not installed: {result.stderr}")
        dockerfile = (ROOT / "docker" / "gates.Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"(?s)PSScriptAnalyzer.{0,200}?\d+\.\d+\.\d+",
                         "PSScriptAnalyzer must be version-pinned in the gates image (§2.2)")

    def test_lint_with_real_tools_fails_on_a_planted_finding(self):
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        path = os.environ.get("PATH", "")
        clean = self._project()
        result = self._run(clean, path)
        self.assertEqual(result.returncode, 0,
                         f"lint.sh fails on the committed scripts:\n{result.stdout}{result.stderr}")
        plants = {
            "scripts/planted.sh": "#!/usr/bin/env bash\nrm -rf $1/tmp\n",  # SC2086
            "docker/gateway/planted.sh": "#!/bin/sh\nrm -rf $1/tmp\n",
            "scripts/planted.ps1": (  # PSAvoidUsingConvertToSecureStringWithPlainText (Error)
                "$s = ConvertTo-SecureString -String 'x' -AsPlainText -Force\n$s\n"),
        }
        for rel, body in plants.items():
            with self.subTest(planted=rel):
                project = self._project()
                (project / rel).write_text(body, encoding="utf-8", newline="\n")
                if (project / ".git").exists():
                    subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"],
                                   cwd=project, check=True)
                result = self._run(project, path)
                self.assertNotEqual(result.returncode, 0, f"lint.sh passed with a finding in {rel}")

    # Rework 2, security L-7: PowerShell treats U+2018, U+2019, U+201A and
    # U+201B as single quotes too, so escaping only U+0027 in generated
    # source lets a committed filename run code. Paths must reach the
    # analyzer as arguments (or refused), never inside generated source.
    QUOTES = {"U+0027": "'", "U+2018": "‘", "U+2019": "’",
              "U+201A": "‚", "U+201B": "‛"}

    def test_lint_runs_no_code_from_a_powershell_filename(self):  # L-7
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        real_pwsh = shutil.which("pwsh")
        # PS-2.23 (review R2-N6, mutant LN-L7): the "closing" payload only
        # parses when the path is embedded in a list; the "comment" payload
        # ends in a `#` comment, so it parses in any context, including a
        # per-file `-Path '<name>'` shape.
        shapes = {
            "closing": lambda q, m: f"x{q}; Set-Content -Path {m} -Value pwned; {q}.ps1",
            "comment": lambda q, m: f"x{q}; Set-Content -Path {m} -Value pwned #.ps1",
        }
        for (label, quote), (shape, build) in [(q, s) for q in self.QUOTES.items()
                                               for s in shapes.items()]:
            with self.subTest(quote=label, shape=shape):
                project = self._project()
                marker = f"l7-marker-{label[2:]}-{shape}"
                name = build(quote, marker)
                (project / "scripts" / name).write_text("Write-Output 'ok'\n",
                                                        encoding="utf-8", newline="\n")
                if (project / ".git").exists():
                    subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"],
                                   cwd=project, check=True)
                # pwsh is wrapped so the test can see the analyzer really ran.
                bin_dir = project / "wrapbin"
                bin_dir.mkdir()
                wrapper = bin_dir / "pwsh"
                wrapper.write_text(f'#!/usr/bin/env bash\necho pwsh >> "$LINT_LOG"\n'
                                   f'exec "{real_pwsh}" "$@"\n', encoding="utf-8", newline="\n")
                _make_executable(wrapper)
                log = project / "lint.log"
                result = self._run(project, f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                                   LINT_LOG=str(log))
                planted = [p for p in project.rglob(f"{marker}*")]
                self.assertEqual(planted, [],
                                 f"lint.sh ran code from the filename (quote {label}):\n"
                                 f"{result.stdout}{result.stderr}")
                ran = log.exists() and "pwsh" in log.read_text(encoding="utf-8")
                self.assertTrue(ran or result.returncode != 0,
                                "lint.sh neither analysed the file nor refused it")

    def test_lint_powershell_command_text_is_fixed(self):  # R2-N6, static half
        # The -Command text is one quoted-heredoc constant: no shell expansion
        # can put a path (or anything else) into PowerShell source.
        text = LINT.read_text(encoding="utf-8")
        calls = [l for l in text.splitlines()
                 if re.match(r"^\s*pwsh\b", l) and not l.lstrip().startswith("#")]
        self.assertEqual(len(calls), 1, f"expected one pwsh call in lint.sh: {calls}")
        match = re.search(r"-Command\s+\"\$(\w+)\"", calls[0])
        self.assertIsNotNone(match, f"pwsh -Command must take one variable: {calls[0]}")
        var = match.group(1)  # type: ignore[union-attr]
        assignments = re.findall(rf"(?m)^\s*{var}=(.*)$", text)
        self.assertEqual(len(assignments), 1, f"{var} must be assigned exactly once")
        self.assertRegex(assignments[0], r"^\"\$\(cat <<'(\w+)'$",
                         f"{var} must come from a quoted heredoc (no expansion)")

    # -- PS-2.23, security L-10: wildcard characters in a .ps1 name ----------

    def test_lint_ps1_wildcard_name_cannot_escape(self):
        # Invoke-ScriptAnalyzer -Path treats its value as a wildcard pattern
        # and has no -LiteralPath, so `x[1].ps1` would be silently skipped and
        # `*`/`?` could match other files. lint.sh refuses such a path before
        # pwsh runs (architecture §2.2 Lint, L-10); the stub pwsh proves it
        # was never called.
        for name in ("b[1].ps1", "x]y.ps1", "x*.ps1", "x?.ps1"):
            with self.subTest(name=name):
                project, path, log = self._with_recorders()
                (project / "scripts" / name).write_text(
                    "Invoke-Expression $args[0]\n", encoding="utf-8", newline="\n")
                if (project / ".git").exists():
                    subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"],
                                   cwd=project, check=True)
                result = self._run(project, path, LINT_LOG=str(log))
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0,
                                    f"lint.sh passed with a wildcard .ps1 name {name!r}:\n{output}")
                calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
                self.assertFalse([c for c in calls if c.startswith("pwsh")],
                                 "pwsh ran although a .ps1 path holds a wildcard character")
                self.assertRegex(output, r"(?i)wildcard|\[|refus",
                                 "the refusal must name the rule")

    def test_lint_ps1_lone_open_bracket_is_refused_before_pwsh(self):  # review N4 (LN1)
        # Every name above also holds `]`; this pins the `[` alternative alone.
        project, path, log = self._with_recorders()
        (project / "scripts" / "a[1.ps1").write_text("Invoke-Expression $args[0]\n",
                                                      encoding="utf-8", newline="\n")
        if (project / ".git").exists():
            subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"], cwd=project, check=True)
        result = self._run(project, path, LINT_LOG=str(log))
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, f"lint.sh passed with a lone '[' in a .ps1 name:\n{output}")
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        self.assertFalse([c for c in calls if c.startswith("pwsh")],
                         "pwsh ran although a .ps1 path holds '['")
        self.assertRegex(output, r"(?i)wildcard|\[|refus", "the refusal must name the rule")

    # Rework 1, security L-12: PowerShell files the lint used to skip. Windows
    # runs `x.PS1`, modules (`.psm1`) are PowerShell too, and `find -type f`
    # skipped a symlinked script. Each plant holds a Warning-severity finding
    # (PSAvoidUsingInvokeExpression, or SC2086 for the shell case); lint must
    # fail, by analysing the file or by refusing it.
    def _real_lint_with(self, plants: dict[str, str], links: dict[str, str]) -> subprocess.CompletedProcess:
        project = self._project()
        for rel, body in plants.items():
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text(body, encoding="utf-8", newline="\n")
        for link, target in links.items():
            (project / link).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, project / link)
        if (project / ".git").exists():
            subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"], cwd=project, check=True)
        return self._run(project, os.environ.get("PATH", ""))

    def test_lint_covers_upper_case_ps1_and_psm1(self):  # L-12
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        for rel in ("scripts/x.PS1", "scripts/m.psm1", "scripts/sub/Mixed.Ps1", "scripts/M.PSM1"):
            with self.subTest(planted=rel):
                result = self._real_lint_with({rel: "Invoke-Expression $args[0]\n"}, {})
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, f"lint.sh passed with a finding in {rel}:\n{output}")
                self.assertIn(rel.rsplit("/", 1)[-1], output, "the failure must name the file")

    def test_lint_fails_on_a_symlinked_script(self):  # L-12
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        cases = {
            "ps1 link to a file outside scripts/": (
                {"outside/evil.txt": "Invoke-Expression $args[0]\n"},
                {"scripts/l.ps1": "../outside/evil.txt"}),
            "ps1 link inside scripts/": (
                {"scripts/real/target.ps1.txt": "Invoke-Expression $args[0]\n"},
                {"scripts/l.ps1": "real/target.ps1.txt"}),
            "sh link to a file outside scripts/": (
                {"outside/evil.txt": "#!/usr/bin/env bash\nrm -rf $1/tmp\n"},
                {"scripts/l.sh": "../outside/evil.txt"}),
        }
        for case, (plants, links) in cases.items():
            with self.subTest(case=case):
                result = self._real_lint_with(plants, links)
                self.assertNotEqual(result.returncode, 0,
                                    f"lint.sh passed with a symlinked script ({case}):\n"
                                    f"{result.stdout}{result.stderr}")

    # Rework round 2 (handoff "orchestrator: rework round 2 of 5").
    # Review R1-B1: every target above has a finding of its own, so the tools
    # fail the run even without the symlink rule (mutant L12b survives). These
    # targets are clean: only the refusal can fail lint. The recorder tools
    # always pass, so the refusal is the only possible cause of a failure.
    def _recorded_lint_with(self, plants: dict[str, str],
                            links: dict[str, str]) -> subprocess.CompletedProcess:
        project, path, log = self._with_recorders()
        for rel, body in plants.items():
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text(body, encoding="utf-8", newline="\n")
        for link, target in links.items():
            (project / link).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, project / link)
        if (project / ".git").exists():
            subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"], cwd=project, check=True)
        return self._run(project, path, LINT_LOG=str(log))

    CLEAN_SH = "#!/usr/bin/env bash\necho ok\n"
    CLEAN_PS1 = "Write-Output 'ok'\n"

    def test_lint_refuses_a_symlink_to_a_clean_script(self):  # review R1-B1, mutant L12b
        cases = {
            "sh link to a clean file outside scripts/": (
                {"outside/clean.txt": self.CLEAN_SH}, {"scripts/l.sh": "../outside/clean.txt"}),
            "sh link to a clean file inside scripts/": (
                {"scripts/real/clean.sh.txt": self.CLEAN_SH}, {"scripts/l.sh": "real/clean.sh.txt"}),
            "ps1 link to a clean file outside scripts/": (
                {"outside/clean.txt": self.CLEAN_PS1}, {"scripts/l.ps1": "../outside/clean.txt"}),
            "ps1 link to a clean file inside scripts/": (
                {"scripts/real/clean.ps1.txt": self.CLEAN_PS1}, {"scripts/l.ps1": "real/clean.ps1.txt"}),
        }
        for case, (plants, links) in cases.items():
            with self.subTest(case=case):
                result = self._recorded_lint_with(plants, links)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0,
                                    f"lint.sh passed with a symlink to a clean target ({case}):\n{output}")
                self.assertRegex(output, r"(?i)symlink", "the failure must name the symlink refusal")
                link = next(iter(links))
                self.assertIn(link, output, "the refusal must name the symlink")

    # Security L-15: `find` without -L does not descend into a symlinked
    # directory, so a script reached through one was neither linted nor
    # refused; and `*.SH` was not shellchecked. Fix per L-15: refuse any
    # symlink under scripts/ and docker/, and select shell scripts by
    # `-iname '*.sh'`.
    def test_lint_fails_on_a_directory_symlink_holding_a_finding(self):  # L-15
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        evil_ps1 = {"outside/dir/evil.ps1": "Invoke-Expression $args[0]\n"}
        evil_sh = {"outside/dir/evil.sh": "#!/usr/bin/env bash\nrm -rf $1/tmp\n"}
        cases = {
            "scripts/linkdir -> outside, holding an IEX .ps1": (evil_ps1, {"scripts/linkdir": "../outside/dir"}),
            "scripts/linkdir -> outside, holding an SC2086 .sh": (evil_sh, {"scripts/linkdir": "../outside/dir"}),
            "docker/linkdir -> outside, holding an SC2086 .sh": (evil_sh, {"docker/linkdir": "../outside/dir"}),
            "docker/linkdir -> outside, holding an IEX .ps1": (evil_ps1, {"docker/linkdir": "../outside/dir"}),
            "scripts/sub/deep -> outside, holding an IEX .ps1": (
                evil_ps1, {"scripts/sub/deep": "../../outside/dir"}),
        }
        for case, (plants, links) in cases.items():
            with self.subTest(case=case):
                result = self._real_lint_with(plants, links)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0,
                                    f"lint.sh passed with a script reachable through a "
                                    f"directory symlink ({case}):\n{output}")

    def test_lint_refuses_any_symlink_under_scripts_and_docker(self):  # L-15
        cases = {
            "scripts/ file link, non-script name": (
                {"outside/clean.txt": "hello\n"}, {"scripts/notes.txt": "../outside/clean.txt"}),
            "docker/ file link, non-script name": (
                {"outside/clean.txt": "hello\n"}, {"docker/notes.txt": "../outside/clean.txt"}),
            "scripts/ directory link to a clean dir": (
                {"outside/dir/clean.sh": self.CLEAN_SH}, {"scripts/linkdir": "../outside/dir"}),
            "docker/ directory link to a clean dir": (
                {"outside/dir/clean.sh": self.CLEAN_SH}, {"docker/linkdir": "../outside/dir"}),
            "nested scripts/ link to a clean script inside scripts/": (
                {"scripts/real/clean.sh.txt": self.CLEAN_SH}, {"scripts/sub/x": "../real/clean.sh.txt"}),
            "dangling link under docker/": ({}, {"docker/gone": "../nowhere/missing"}),
        }
        for case, (plants, links) in cases.items():
            with self.subTest(case=case):
                result = self._recorded_lint_with(plants, links)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0,
                                    f"lint.sh passed with a symlink under scripts/ or docker/ ({case}):\n{output}")
                self.assertRegex(output, r"(?i)symlink", "the failure must name the symlink refusal")
                self.assertIn(next(iter(links)), output, "the refusal must name the symlink")

    def test_lint_shellchecks_upper_case_sh(self):  # L-15
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        for rel in ("scripts/u.SH", "scripts/sub/m.Sh", "docker/gateway/u.SH"):
            with self.subTest(planted=rel):
                result = self._real_lint_with({rel: "#!/usr/bin/env bash\nrm -rf $1/tmp\n"}, {})
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, f"lint.sh passed with SC2086 in {rel}:\n{output}")
                self.assertIn(rel.rsplit("/", 1)[-1], output, "the failure must name the file")

    def test_lint_fails_on_warning_severity_finding(self):  # PS-2.23, review N-2
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        if shutil.which("shellcheck") is None:
            self.fail(SHELLCHECK_MISSING)
        project = self._project()
        # PSAvoidUsingCmdletAliases is Warning severity.
        (project / "scripts" / "planted-warning.ps1").write_text(
            "gci | % { $_.Name }\n", encoding="utf-8", newline="\n")
        if (project / ".git").exists():
            subprocess.run(["git", "-c", "core.autocrlf=false", "add", "-A"],
                           cwd=project, check=True)
        result = self._run(project, os.environ.get("PATH", ""))
        self.assertNotEqual(result.returncode, 0,
                            f"lint.sh passed a Warning-severity finding:\n{result.stdout}{result.stderr}")
        self.assertIn("planted-warning.ps1", result.stdout + result.stderr)


class VerifyCallsLintTest(unittest.TestCase):
    """B5, §2.2: the container half of verify.sh calls lint.sh, then test.sh,
    in both modes; a lint failure fails verify."""

    SENTINEL = ("test_top_level_unit_suite_ran "
                "(tests.test_sentinel.TopLevelSuiteSentinelTest.test_top_level_unit_suite_ran)"
                " ... ok")

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "verify.sh", self.tmp / "scripts" / "verify.sh")
        self.log = self.tmp / "calls.log"
        bodies = {
            "lint.sh": 'echo lint >> "$CALLS"\n[ -z "${LINT_FAIL:-}" ]\n',
            "test.sh": (f'echo "test $*" >> "$CALLS"\necho "Ran 3 tests" >&2\n'
                        f"echo '{self.SENTINEL}' >&2\n"),
            "smoke.sh": 'echo smoke >> "$CALLS"\n',
        }
        for name, body in bodies.items():
            path = self.tmp / "scripts" / name
            path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
            _make_executable(path)

    def _verify(self, mode: str, **extra: str) -> tuple[subprocess.CompletedProcess, list[str]]:
        self.log.write_text("", encoding="utf-8")
        env = _clean_env(KE_IN_GATES="1", CALLS=str(self.log), **extra)
        result = subprocess.run(["bash", "scripts/verify.sh", mode], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=60)
        return result, self.log.read_text(encoding="utf-8").splitlines()

    def test_container_half_runs_lint_before_tests(self):
        for mode in ("fast", "full"):
            with self.subTest(mode=mode):
                result, calls = self._verify(mode)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("lint", calls, "verify.sh never called scripts/lint.sh")
                self.assertLess(calls.index("lint"), calls.index(f"test {mode}"))

    def test_lint_failure_fails_verify(self):
        for mode in ("fast", "full"):
            with self.subTest(mode=mode):
                result, calls = self._verify(mode, LINT_FAIL="1")
                self.assertNotEqual(result.returncode, 0, "verify passed although lint failed")
                self.assertNotIn(f"== verify {mode}: PASS ==", result.stdout + result.stderr)


# --------------------------------------------------------------------------
# B4: smoke resolves the compose file with no .env
# --------------------------------------------------------------------------

SCRIPT_STUB = """#!/usr/bin/env bash
# Stand-in for scripts/{name}: one JSON record in the fake docker's call log,
# so stub and docker calls form one ordered sequence.
if [ -n "${{FAKE_DOCKER_JSON:-}}" ]; then
  extra=""
  for a in "$@"; do extra="$extra, \\"$a\\""; done
  printf '{{"argv": ["STUB", "{name}"%s], "env": {{}}, "cwd": "", "project_dir": "", "dotenv_present": false}}\\n' "$extra" >> "$FAKE_DOCKER_JSON"
fi
case "|${{FAKE_STUB_FAIL:-}}|" in *"|{name}|"*) echo "stub {name}: failing" >&2; exit 7 ;; esac
exit 0
"""


def _install_script_stubs(root: Path, names: tuple[str, ...]) -> None:
    for name in names:
        stub = root / "scripts" / name
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(SCRIPT_STUB.format(name=name), encoding="utf-8", newline="\n")
        _make_executable(stub)


class SmokeResolvesWithoutEnvTest(unittest.TestCase):
    """B4, PS-2.2 *Resolves without .env* [smoke:
    test_compose_resolves_without_env_file]: the smoke.sh host half runs
    `docker compose config` with no .env and no env file, and checks every
    published port binds 127.0.0.1. Driven with the fake docker; the real
    check runs in `verify.sh full`'s host smoke."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        rels = ["scripts/smoke.sh", ".env.example", "docker-compose.yml"]
        if (ROOT / "docker-compose.verify.yml").exists():
            rels.append("docker-compose.verify.yml")
        _copy_repo_files(self.tmp, rels)
        # A real .env with a non-loopback bind sits in the checkout: the
        # check must not read it.
        (self.tmp / ".env").write_text(_env_text(["KE_ENV=dev", f"{VAR}=0.0.0.0"]),
                                       encoding="utf-8", newline="\n")
        fake_docker.install(self.tmp / "fakebin")
        self.json = self.tmp / "docker.jsonl"
        # platform-stack-ready (PS-2.8, §2.4 Smoke): the smoke host half now
        # calls scripts/launch.sh and scripts/teardown.sh. Fixture-only stubs
        # that log into the fake docker's call log; the 2a assertions in this
        # class and SmokeBackendIsolatedTest are unchanged.
        _install_script_stubs(self.tmp, ("launch.sh", "teardown.sh"))

    def _smoke(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), KE_ENV_FILE=".env.example",
                         COMPOSE_PROJECT_NAME="ke-verify-test", **extra)
        result = subprocess.run(["bash", "scripts/smoke.sh"], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=60)
        return result, fake_docker.records(self.json)

    @staticmethod
    def _env_files_empty(argv: list[str], cwd: str) -> bool:
        files = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--env-file"]
        files += [a.split("=", 1)[1] for a in argv if a.startswith("--env-file=")]
        for f in files:
            path = Path(f) if os.path.isabs(f) else Path(cwd) / f
            if f != "/dev/null" and path.is_file() and path.stat().st_size > 0:
                return False
        return True

    def _no_env_configs(self, records: list[dict]) -> list[dict]:
        out = []
        for r in records:
            argv = r["argv"]
            if argv[:1] != ["compose"] or "config" not in argv:
                continue
            has_env_file = any(a == "--env-file" or a.startswith("--env-file=") for a in argv)
            if has_env_file and not self._env_files_empty(argv, r["cwd"]):
                continue
            if not has_env_file and r["dotenv_present"]:
                continue
            out.append(r)
        return out

    def test_smoke_resolves_compose_without_env_file(self):
        result, records = self._smoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self._no_env_configs(records),
                        "smoke.sh never ran `docker compose config` without a .env/env file: "
                        f"{[r['argv'] for r in records if 'config' in r['argv']]}")

    def test_smoke_fails_when_resolution_fails(self):
        result, _ = self._smoke(FAKE_DOCKER_FAIL="config")
        self.assertNotEqual(result.returncode, 0, "smoke passed although compose config failed")

    def test_smoke_fails_when_a_port_is_not_loopback(self):
        result, _ = self._smoke(FAKE_COMPOSE_RESOLVED=json.dumps({VAR: "0.0.0.0"}))
        self.assertNotEqual(result.returncode, 0,
                            "smoke passed although a published port binds 0.0.0.0")

    def test_smoke_sh_contains_the_check(self):
        text = (ROOT / "scripts" / "smoke.sh").read_text(encoding="utf-8")
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        self.assertRegex(body, r"\bconfig\b", "smoke.sh has no `docker compose config` call")
        self.assertIn("127.0.0.1", body)


# --------------------------------------------------------------------------
# Rework 2, R1-B1 + security M-4: smoke proves the backend bridge is isolated
# --------------------------------------------------------------------------

ISOLATED_KEY = "com.docker.network.bridge.gateway_mode_ipv4"


class SmokeBackendIsolatedTest(unittest.TestCase):
    """Ruling R1-B1 option (ii): the M-2 runtime proof is the smoke.sh host
    half asserting `docker network inspect <project>_backend` carries
    gateway_mode_ipv4=isolated, on the run's own project. Driven with the fake
    docker, whose backend options are FAKE_DOCKER_BACKEND_OPTIONS; the fake
    knows no other network, so inspecting a fixed name fails."""

    setUp = SmokeResolvesWithoutEnvTest.setUp

    def _smoke(self, project: str | None = "ke-verify-test",
               **extra: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), KE_ENV_FILE=".env.example", **extra)
        if project is not None:
            env["COMPOSE_PROJECT_NAME"] = project
        result = subprocess.run(["bash", "scripts/smoke.sh"], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=60)
        return result, fake_docker.records(self.json)

    @staticmethod
    def _inspects(records: list[dict]) -> list[list[str]]:
        return [r["argv"] for r in records if r["argv"][:2] == ["network", "inspect"]]

    def test_smoke_inspects_its_own_backend_network(self):
        cases = {"ke-verify-test": "ke-verify-test", "ke-verify-x7q2": "ke-verify-x7q2",
                 "default project": None}
        for case, project in cases.items():
            with self.subTest(project=case):
                result, records = self._smoke(project)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                inspects = self._inspects(records)
                self.assertTrue(inspects, "smoke.sh never ran `docker network inspect`")
                network = f"{project or 'knowledge-engine'}_backend"
                self.assertTrue(any(network in argv for argv in inspects),
                                f"smoke.sh did not inspect {network}: {inspects}")

    def test_smoke_fails_when_backend_is_not_isolated(self):
        cases = {
            "option absent": {},
            "nat": {ISOLATED_KEY: "nat"},
            "routed": {ISOLATED_KEY: "routed"},
            "empty": {ISOLATED_KEY: ""},
            "isolated on another key": {"com.docker.network.bridge.gateway_mode_ipv6": "isolated"},
        }
        for case, options in cases.items():
            with self.subTest(case=case):
                result, _ = self._smoke(FAKE_DOCKER_BACKEND_OPTIONS=json.dumps(options))
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0,
                                    f"smoke passed although backend is not isolated:\n{output}")
                self.assertNotIn("smoke: PASS", output)
                self.assertRegex(output, r"(?i)isolated|gateway_mode",
                                 "the failure must say the backend is not isolated")

    def test_smoke_fails_when_backend_network_is_missing(self):
        result, _ = self._smoke(FAKE_DOCKER_FAIL="network inspect")
        self.assertNotEqual(result.returncode, 0,
                            "smoke passed although `docker network inspect` failed")
        self.assertNotIn("smoke: PASS", result.stdout + result.stderr)

    def test_smoke_fails_when_backend_is_not_internal(self):  # PS-2.24, R2-N4, mutant SM-I3
        result, _ = self._smoke(FAKE_DOCKER_BACKEND_INTERNAL="false")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0,
                            f"smoke passed although the backend network is not internal:\n{output}")
        self.assertNotIn("smoke: PASS", output)
        self.assertRegex(output, r"(?i)ke-verify-test_backend[^\n]*internal|internal[^\n]*ke-verify-test_backend",
                         "the failure must name the network and say it is not internal")


# --------------------------------------------------------------------------
# platform-stack-ready, PS-2.8 (§2.4 "Smoke, host half"; rulings S1, Q37):
# smoke launches through launch.sh, waits for /readyz, stops and restarts
# postgres with readiness waits, and tears down only a project it launched.
# --------------------------------------------------------------------------

READY_RX = re.compile(r"--wait-for[ =]ready\b")
NOT_READY_PG_RX = re.compile(r"--wait-for[ =]not-ready:postgres\b")


def _smoke_steps(records: list[dict]) -> list[str]:
    """The PS-2.8 steps in call order; other calls are left out."""
    steps: list[str] = []
    for r in records:
        argv = r["argv"]
        joined = " ".join(argv)
        if argv[:2] == ["STUB", "launch.sh"]:
            steps.append("launch")
        elif argv[:2] == ["STUB", "teardown.sh"]:
            steps.append("teardown" + ("".join(" " + a for a in argv[2:])))
        elif argv[:1] == ["compose"] and "exec" in argv and "engine.readiness" in joined:
            if NOT_READY_PG_RX.search(joined):
                steps.append("not-ready:postgres")
            elif READY_RX.search(joined):
                steps.append("ready")
            else:
                steps.append("readiness:other")
        elif argv[:1] == ["compose"] and "stop" in argv:
            steps.append("stop " + " ".join(a for a in argv[argv.index("stop") + 1:]
                                            if not a.startswith("-")))
        elif argv[:1] == ["compose"] and "up" in argv and "postgres" in argv:
            steps.append("up postgres")
    return steps


class SmokeStoreStopStartTest(unittest.TestCase):
    setUp = SmokeResolvesWithoutEnvTest.setUp
    _smoke = SmokeBackendIsolatedTest._smoke

    LAUNCHED_ORDER = ["launch", "ready", "stop postgres", "not-ready:postgres",
                      "up postgres", "ready", "teardown"]

    def _readiness_calls(self, records: list[dict]) -> list[list[str]]:
        return [r["argv"] for r in records if r["argv"][:1] == ["compose"]
                and "exec" in r["argv"] and "engine.readiness" in " ".join(r["argv"])]

    def test_smoke_stops_and_restarts_a_store(self):
        result, records = self._smoke()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("smoke: PASS", output)
        self.assertEqual(_smoke_steps(records), self.LAUNCHED_ORDER,
                         "smoke must launch, wait ready, stop postgres, wait not-ready:postgres, "
                         "start postgres with --wait, wait ready, then tear down")
        inspects = [i for i, r in enumerate(records) if r["argv"][:2] == ["network", "inspect"]]
        launch = next(i for i, r in enumerate(records) if r["argv"][:2] == ["STUB", "launch.sh"])
        self.assertTrue(inspects and min(inspects) > launch,
                        "the 2a checks run against the launched stack, after launch.sh")
        for argv in self._readiness_calls(records):
            with self.subTest(readiness=" ".join(argv)):
                self.assertIn("api", argv[argv.index("exec") + 1:],
                              "the readiness CLI runs in the api container (§2.4 Smoke)")
                self.assertRegex(" ".join(argv), r"--within[ =]\d+", "every readiness wait is bounded")
        ups = [r["argv"] for r in records if r["argv"][:1] == ["compose"]
               and "up" in r["argv"] and "postgres" in r["argv"]]
        for flag in ("-d", "--no-build", "--wait"):
            self.assertIn(flag, ups[0], f"postgres restart must use `up {flag}` (§2.4 Smoke)")
        teardowns = [r["argv"] for r in records if r["argv"][:2] == ["STUB", "teardown.sh"]]
        self.assertEqual(len(teardowns), 1)
        self.assertNotIn("--volumes", teardowns[0], "smoke's own teardown keeps volumes")

    def test_smoke_fails_naming_the_store_when_readiness_never_recovers(self):
        result, records = self._smoke(FAKE_DOCKER_FAIL_NTH=r"engine\.readiness.*--wait-for[ =]ready\b#2")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0,
                            f"smoke passed with postgres never ready again:\n{output}")
        self.assertNotIn("smoke: PASS", output)
        self.assertRegex(output, r"postgres", "the failure must name the store")
        steps = _smoke_steps(records)
        self.assertEqual(steps[-1], "teardown", f"teardown must still run: {steps}")

    def test_smoke_fails_when_each_store_step_fails(self):
        cases = {
            "first ready never met": {"FAKE_DOCKER_FAIL_NTH": r"engine\.readiness.*--wait-for[ =]ready\b#1"},
            "stop postgres fails": {"FAKE_DOCKER_FAIL_NTH": r"\bstop\b.*\bpostgres\b#1"},
            "not-ready never seen": {"FAKE_DOCKER_FAIL": "not-ready:postgres"},
            "postgres restart fails": {"FAKE_DOCKER_FAIL_NTH": r"\bup\b.*\bpostgres\b#1"},
            "launch fails": {"FAKE_STUB_FAIL": "launch.sh"},
        }
        for case, extra in cases.items():
            with self.subTest(case=case):
                result, records = self._smoke(**extra)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, f"smoke passed although {case}:\n{output}")
                self.assertNotIn("smoke: PASS", output)
                steps = _smoke_steps(records)
                self.assertTrue(steps and steps[-1] == "teardown",
                                f"smoke launched the project, so teardown must run last: {steps}")
                self.assertEqual(steps.count("teardown"), 1)

    def test_smoke_leaves_a_project_it_did_not_launch(self):  # S1, Q37
        result, records = self._smoke(FAKE_DOCKER_RUNNING="0123456789ab")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        steps = _smoke_steps(records)
        self.assertNotIn("teardown", steps, "smoke tore down a project it did not launch (S1)")
        self.assertFalse([s for s in steps if s.startswith("stop")],
                         "smoke stopped a store of a project it did not launch (Q37)")
        self.assertNotIn("up postgres", steps)
        self.assertIn("ready", steps, "smoke still checks /readyz on a running project (PS-2.8)")
        lines = [l for l in output.splitlines() if re.search(r"(?i)skip", l)]
        self.assertTrue([l for l in lines if re.search(r"(?i)postgres|store", l)],
                        f"smoke must say the store stop/start was skipped:\n{output}")
        for line in output.splitlines():
            if re.search(r"(?i)stop|restart|store", line) and not re.search(r"(?i)skip", line):
                self.assertNotRegex(line, r"(?i)\bpass|\bok\b",
                                    f"a skipped store stop/start is reported as passed: {line!r}")

    def test_smoke_owned_by_verify_stops_and_restarts_without_teardown(self):
        # Ruling "Q37 vs CI": verify.sh sets KE_SMOKE_OWNS_PROJECT=1 for its own
        # running project; smoke then runs the store stop/restart and leaves
        # teardown to verify's trap.
        result, records = self._smoke(FAKE_DOCKER_RUNNING="0123456789ab", KE_SMOKE_OWNS_PROJECT="1")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("smoke: PASS", output)
        steps = [s for s in _smoke_steps(records) if s != "launch"]
        self.assertEqual(steps, ["ready", "stop postgres", "not-ready:postgres", "up postgres", "ready"],
                         "with the flag, smoke runs the stop/restart and no teardown")

    def test_smoke_flag_without_a_running_project_fails_loudly(self):
        # Ruling "Q37 vs CI": the flag promises a running verify project; with
        # nothing running the verify contract is broken, so smoke fails and
        # neither launches, stops nor tears anything down.
        result, records = self._smoke(KE_SMOKE_OWNS_PROJECT="1")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, f"smoke passed with the flag and no project:\n{output}")
        self.assertNotIn("smoke: PASS", output)
        self.assertIn("KE_SMOKE_OWNS_PROJECT", output, "the failure must name the broken contract")
        steps = _smoke_steps(records)
        self.assertNotIn("launch", steps)
        self.assertNotIn("teardown", steps)
        self.assertFalse([s for s in steps if s.startswith("stop") or s == "up postgres"], steps)

    # Rework 1, review R-B3 (PS-2.8 *Every service healthy*, which the
    # orchestrator kept as written): every stack service is checked healthy
    # AFTER the store is back, that is after the final `ready`.
    SERVICES = ("gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix")

    @staticmethod
    def _health_queries(records: list[dict]) -> list[tuple[int, str]]:
        out = []
        for i, r in enumerate(records):
            argv = r["argv"]
            if argv[:1] == ["compose"] and "ps" in argv and "Health" in " ".join(argv):
                out.append((i, argv[-1]))
        return out

    def _final_ready_index(self, records: list[dict]) -> int:
        readies = [i for i, r in enumerate(records) if r["argv"][:1] == ["compose"]
                   and "engine.readiness" in " ".join(r["argv"])
                   and READY_RX.search(" ".join(r["argv"]))]
        self.assertTrue(readies, "smoke never waited for ready")
        return readies[-1]

    def test_smoke_checks_every_service_healthy_after_the_store_is_back(self):
        cases = {"smoke launched the project": {},
                 "verify owns the project": {"FAKE_DOCKER_RUNNING": "0123456789ab",
                                             "KE_SMOKE_OWNS_PROJECT": "1"}}
        for case, extra in cases.items():
            with self.subTest(case=case):
                result, records = self._smoke(**extra)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                final_ready = self._final_ready_index(records)
                ups = [i for i, r in enumerate(records) if r["argv"][:1] == ["compose"]
                       and "up" in r["argv"] and "postgres" in r["argv"]]
                self.assertTrue(ups and ups[-1] < final_ready, "precondition: the restart came first")
                after = {svc for i, svc in self._health_queries(records) if i > final_ready}
                for service in self.SERVICES:
                    self.assertIn(service, after,
                                  f"{service} is not checked healthy after the final ready (PS-2.8)")
                teardowns = [i for i, r in enumerate(records) if r["argv"][:2] == ["STUB", "teardown.sh"]]
                if teardowns:
                    last_health = max(i for i, _ in self._health_queries(records))
                    self.assertLess(last_health, teardowns[0], "health is checked before teardown")

    def test_smoke_fails_when_a_service_is_unhealthy_after_the_restart(self):
        # The second health query for postgres is the one after the restart.
        result, records = self._smoke(FAKE_DOCKER_FAIL_NTH=r"\bps\b.*Health.*\bpostgres$#2")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0,
                            f"smoke passed with postgres failing its health check after the restart:\n{output}")
        self.assertNotIn("smoke: PASS", output)
        steps = _smoke_steps(records)
        self.assertEqual(steps[-1], "teardown", f"smoke launched the project, so teardown runs last: {steps}")

    def test_smoke_decides_it_launched_before_launching(self):  # S1
        result, records = self._smoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launches = [i for i, r in enumerate(records) if r["argv"][:2] == ["STUB", "launch.sh"]]
        self.assertTrue(launches, "smoke never ran scripts/launch.sh (PS-2.8)")
        launch = launches[0]
        probes = [i for i, r in enumerate(records)
                  if (r["argv"][:1] == ["compose"] and "ps" in r["argv"]
                      and ("-q" in r["argv"] or "--quiet" in r["argv"] or "--services" in r["argv"]))
                  or (r["argv"][:1] == ["ps"] and "-q" in r["argv"])]
        self.assertTrue(probes and min(probes) < launch,
                        "smoke must check whether the project already runs before launch.sh (S1)")


if __name__ == "__main__":
    unittest.main()
