"""platform-stack-up (2a): LAN exposure refused outside dev (PS-2.14).

Rulings (docs/handoffs/platform-stack.md, authoritative over the drafts):
- Q33(a): the build/launch scripts also refuse a non-loopback
  `KE_BIND_ADDRESS` outside dev, before `compose up`;
- IPv4-only ruling (orchestrator, 2026-10-19, before GREEN; supersedes the
  handoff's Q33(b) "plus ::1" wording and matches PS-2.14 and architecture
  §2.4): `KE_BIND_ADDRESS` is an IPv4 literal. Loopback is 127.0.0.0/8 only.
  `::`, `::1` and any other IPv6 value are a ConfigError naming the variable
  in EVERY `KE_ENV`, dev included (no warn-and-continue); the gateway check
  and launch.sh likewise exit non-zero for them in every env;
- Q33(c): dev logs a warning naming the variable (IPv4 non-loopback only);
- R4: the gateway image has its own check, `docker/gateway/10-ke-bind-check.sh`,
  as well as engine refusal 6.
Design: docs/architecture.md §2.4 *Bind address* and ADR-KE-011's ports
amendment. Engine refusal 6: `Settings.bind_address` (env `KE_BIND_ADDRESS`,
default `127.0.0.1` in defaults.yaml) and `StartupRefused("KE_BIND_ADDRESS", ...)`
from `check()` when it is not loopback and `KE_ENV` is not dev.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.engine_support import ROOT, base_env, config_error, environ, load_settings

GATEWAY_CHECK = ROOT / "docker" / "gateway" / "10-ke-bind-check.sh"
VAR = "KE_BIND_ADDRESS"

# None = unset. PS-2.14 cases plus the 127.0.0.0/8 loopback range.
LOOPBACK = (None, "", "127.0.0.1", "127.0.0.2", "127.255.255.254")
EXPOSED = ("0.0.0.0", "192.168.1.10", "10.0.0.5")
# IPv4-only ruling: rejected in every env, dev included.
IPV6 = ("::", "::1", "fe80::1", "[::1]")
NON_DEV = ("ci", "prod")


def _refused() -> type[Exception]:
    from engine.startup import StartupRefused

    return StartupRefused


def _env(ke_env: str, bind: str | None) -> dict[str, str]:
    env = base_env(KE_ENV=ke_env)
    if bind is not None:
        env[VAR] = bind
    return env


def _check(env: dict[str, str]) -> None:
    from engine.startup import check

    check(load_settings(env))


class EngineRefusalTest(unittest.TestCase):
    """Refusal 6 (§2.3 list, §2.4)."""

    def test_startup_refuses_non_loopback_bind_address(self):
        for ke_env in NON_DEV:
            for bind in EXPOSED:
                with self.subTest(env=ke_env, bind=bind):
                    with self.assertRaises(_refused()) as ctx:
                        _check(_env(ke_env, bind))
                    self.assertIn(VAR, str(ctx.exception))
                    self.assertEqual(ctx.exception.setting, VAR)

    def test_dev_non_loopback_bind_address_warns(self):  # Q33(c)
        for bind in EXPOSED:
            with self.subTest(bind=bind):
                with self.assertLogs("engine", logging.WARNING) as logs:
                    _check(_env("dev", bind))
                self.assertTrue(any(VAR in line for line in logs.output), logs.output)

    def test_loopback_or_unset_bind_address_passes_everywhere(self):
        # Orchestrator ruling 2026-10-19 (platform-offline smoke loop 2;
        # docs/architecture.md line 3900, ADR-KE-010): prod is refused until
        # auth-audit whatever the bind address. In prod the only refusal
        # allowed here is that one; the bind address is never the reason.
        for ke_env in ("dev", *NON_DEV):
            for bind in LOOPBACK:
                with self.subTest(env=ke_env, bind=bind):
                    logger = logging.getLogger("engine")
                    with self.assertLogs(logger, logging.DEBUG) as logs:
                        logger.debug("probe")  # assertLogs needs one record
                        if ke_env == "prod":
                            with self.assertRaises(_refused()) as ctx:
                                _check(_env(ke_env, bind))
                            self.assertNotIn(VAR, str(ctx.exception))
                            self.assertRegex(str(ctx.exception), r"(?i)\bauth\b[\s\S]*\bauth-audit\b")
                        else:
                            _check(_env(ke_env, bind))
                    self.assertFalse([l for l in logs.output if VAR in l], logs.output)

    def test_bind_address_setting_defaults_to_loopback(self):
        settings = load_settings(_env("prod", None))
        self.assertEqual(str(settings.bind_address), "127.0.0.1")
        settings = load_settings(_env("prod", "127.0.0.2"))
        self.assertEqual(str(settings.bind_address), "127.0.0.2")

    def test_bind_address_that_is_not_an_address_is_a_config_error(self):
        for ke_env in ("dev", *NON_DEV):
            for bind in ("not-an-address", "999.1.1.1", "127.0.0.1.example.com"):
                with self.subTest(env=ke_env, bind=bind):
                    with self.assertRaises(config_error()) as ctx:
                        load_settings(_env(ke_env, bind))
                    self.assertIn(VAR, str(ctx.exception))
                    self.assertNotIn(bind, str(ctx.exception), "the message echoes the value")

    def test_ipv6_bind_address_is_a_config_error_in_every_env(self):
        # IPv4-only ruling (orchestrator, 2026-10-19; supersedes Q33(b)'s ::1).
        for ke_env in ("dev", *NON_DEV):
            for bind in IPV6:
                with self.subTest(env=ke_env, bind=bind):
                    with self.assertRaises(config_error()) as ctx:
                        _check(_env(ke_env, bind))
                    self.assertIn(VAR, str(ctx.exception))

    def test_startup_refusal_is_recorded_on_the_span(self):
        from engine.startup import startup
        from tests import support

        support.EXPORTER.clear()
        with environ(_env("prod", "0.0.0.0")):
            with self.assertRaises(_refused()):
                startup()
        refusals = support.finished_spans().get("engine.startup.refusals")
        self.assertIsNotNone(refusals)
        self.assertEqual(refusals.attributes.get("ke.refused_setting"), VAR)


def _run(cmd: list[str], env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=60)


def _clean_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir()}
    env.update(extra)
    return env


class GatewayBindCheckTest(unittest.TestCase):
    """R4: the gateway entrypoint check, run under POSIX sh."""

    def _check(self, ke_env: str | None, bind: str | None) -> subprocess.CompletedProcess:
        self.assertTrue(GATEWAY_CHECK.is_file(), f"{GATEWAY_CHECK.relative_to(ROOT)} is missing")
        env = _clean_env()
        if ke_env is not None:
            env["KE_ENV"] = ke_env
        if bind is not None:
            env[VAR] = bind
        return _run(["sh", str(GATEWAY_CHECK)], env)

    def test_gateway_bind_check_refuses_non_loopback(self):
        for ke_env in (*NON_DEV, None):  # unset KE_ENV fails closed (engine default: prod)
            for bind in (*EXPOSED, "128.0.0.1", "127.0.0.1.example.com", "1127.0.0.1"):
                with self.subTest(env=ke_env, bind=bind):
                    result = self._check(ke_env, bind)
                    self.assertNotEqual(result.returncode, 0, "non-loopback bind not refused")
                    self.assertIn(VAR, result.stdout + result.stderr)

    def test_gateway_bind_check_rejects_non_ipv4_in_every_env(self):
        # IPv4-only ruling (orchestrator, 2026-10-19): same as the engine's
        # ConfigError, so dev gets no warn-and-continue for these.
        for ke_env in ("dev", *NON_DEV, None):
            for bind in (*IPV6, "not-an-address", "999.1.1.1", "127.0.0.1.example.com"):
                with self.subTest(env=ke_env, bind=bind):
                    result = self._check(ke_env, bind)
                    self.assertNotEqual(result.returncode, 0, "a non-IPv4 value was accepted")
                    self.assertIn(VAR, result.stdout + result.stderr)

    def test_gateway_bind_check_allows_loopback_and_warns_in_dev(self):
        for ke_env in ("dev", *NON_DEV):
            for bind in LOOPBACK:
                with self.subTest(env=ke_env, bind=bind):
                    result = self._check(ke_env, bind)
                    self.assertEqual(result.returncode, 0, result.stderr)
        for bind in EXPOSED:
            with self.subTest(env="dev", bind=bind):
                result = self._check("dev", bind)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(VAR, result.stdout + result.stderr, "dev must warn naming the variable")

    def test_gateway_image_runs_bind_check(self):
        dockerfile = ROOT / "docker" / "gateway.Dockerfile"
        self.assertTrue(dockerfile.is_file(), "docker/gateway.Dockerfile is missing")
        text = dockerfile.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^COPY\s.*10-ke-bind-check\.sh\s+/docker-entrypoint\.d/",
                         "the check is not installed into /docker-entrypoint.d/")


FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *"compose version"*"--short"*) echo "2.29.7" ;;
  *"compose version"*) echo "Docker Compose version v2.29.7" ;;
esac
exit 0
"""


class LaunchScriptTest(unittest.TestCase):
    """Q33(a) and PS-2.9: scripts/launch.sh, driven against a fake `docker`
    in a copy of the repository files it needs (never the real checkout)."""

    def setUp(self) -> None:
        self.launch = ROOT / "scripts" / "launch.sh"
        self.assertTrue(self.launch.is_file(), "scripts/launch.sh is missing (PS-2.9)")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "scripts").mkdir()
        for rel in ("scripts/launch.sh", ".env.example", "docker-compose.yml"):
            shutil.copy(ROOT / rel, self.tmp / rel)
        for extra in (ROOT / "scripts").glob("*.sh"):  # shared helpers, if any
            if not (self.tmp / "scripts" / extra.name).exists():
                shutil.copy(extra, self.tmp / "scripts" / extra.name)
        bin_dir = self.tmp / "fakebin"
        bin_dir.mkdir()
        # Rework 1 (review B3, security L-1): launch resolves its inputs with
        # `docker compose config`, so the fake must answer it like compose
        # (tests/fake_docker.py); the assertions below are unchanged.
        from tests import fake_docker

        fake_docker.install(bin_dir)
        self.log = self.tmp / "docker.log"
        self.log.write_text("", encoding="utf-8")
        self.path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"

    def _launch(self, **env: str) -> tuple[subprocess.CompletedProcess, str]:
        # Rework 2 (ruling R1-B2 + security L-6): the fake answers `docker
        # version` with FAKE_DOCKER_ENGINE and launch refuses an empty one, so
        # these cases run on a valid engine. The assertions are unchanged.
        env = {"FAKE_DOCKER_ENGINE": "29.5.2", **env}
        run_env = _clean_env(PATH=self.path, FAKE_DOCKER_LOG=str(self.log), **env)
        result = _run(["bash", "scripts/launch.sh"], run_env, cwd=self.tmp)
        return result, self.log.read_text(encoding="utf-8")

    def _write_env(self, name: str, ke_env: str, bind: str) -> Path:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        lines = [l for l in text.splitlines()
                 if not l.startswith(("KE_ENV=", f"{VAR}="))]
        lines += [f"KE_ENV={ke_env}", f"{VAR}={bind}"]
        path = self.tmp / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return path

    @staticmethod
    def _ups(log: str) -> list[str]:
        return [l for l in log.splitlines() if " up" in f" {l}" and "compose" in l]

    def test_launch_sh_refuses_non_loopback_bind_address(self):
        cases = {
            ".env, prod, 0.0.0.0": lambda: (self._write_env(".env", "prod", "0.0.0.0"), {}),
            ".env, ci, LAN address": lambda: (self._write_env(".env", "ci", "192.168.1.10"), {}),
            "KE_ENV_FILE, prod, 0.0.0.0": lambda: (
                None, {"KE_ENV_FILE": str(self._write_env("custom.env", "prod", "0.0.0.0"))}),
            "process env overrides .env": lambda: (
                self._write_env(".env", "dev", "127.0.0.1"),
                {"KE_ENV": "prod", VAR: "10.0.0.5"}),
            # IPv4-only ruling (orchestrator, 2026-10-19): IPv6 refused even in dev.
            ".env, dev, ::1": lambda: (self._write_env(".env", "dev", "::1"), {}),
            ".env, dev, ::": lambda: (self._write_env(".env", "dev", "::"), {}),
        }
        for case, prepare in cases.items():
            with self.subTest(case=case):
                (self.tmp / ".env").unlink(missing_ok=True)
                self.log.write_text("", encoding="utf-8")
                _, env = prepare()
                result, log = self._launch(**env)
                self.assertNotEqual(result.returncode, 0, "launch did not refuse")
                self.assertIn(VAR, result.stdout + result.stderr)
                self.assertEqual(self._ups(log), [], "compose up ran despite the refusal")

    def test_launch_sh_allows_loopback_and_warns_in_dev(self):
        cases = {"prod, loopback": ("prod", "127.0.0.1", False),
                 "dev, 0.0.0.0 (warning)": ("dev", "0.0.0.0", True)}
        for case, (ke_env, bind, warns) in cases.items():
            with self.subTest(case=case):
                self._write_env(".env", ke_env, bind)
                self.log.write_text("", encoding="utf-8")
                result, log = self._launch()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                ups = self._ups(log)
                self.assertTrue(ups, f"compose up was not called: {log!r}")
                self.assertIn("--wait", ups[-1])
                self.assertIn("--no-build", ups[-1])
                if warns:
                    self.assertIn(VAR, result.stdout + result.stderr)

    def test_launch_sh_creates_env_from_example(self):  # §2.4 Scripts
        (self.tmp / ".env").unlink(missing_ok=True)
        result, _ = self._launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.tmp / ".env").read_text(encoding="utf-8"),
                         (self.tmp / ".env.example").read_text(encoding="utf-8"))
        self.assertIn(".env", result.stdout + result.stderr, "launch must say it created .env")

    def test_launch_ps1_checks_bind_address(self):
        # Static only: the gates image has no pwsh yet. The behaviour is proven
        # by the recorded Windows run (PS-2.9, Q31) and PSScriptAnalyzer (full).
        ps1 = ROOT / "scripts" / "launch.ps1"
        self.assertTrue(ps1.is_file(), "scripts/launch.ps1 is missing (PS-2.9)")
        text = ps1.read_text(encoding="utf-8")
        self.assertIn(VAR, text)
        self.assertIn("127.", text)


class TeardownScriptTest(unittest.TestCase):
    """PS-2.9: teardown removes the project's containers and keeps named
    volumes unless asked (§2.4 Scripts)."""

    def _teardown(self, *args: str) -> str:
        script = ROOT / "scripts" / "teardown.sh"
        self.assertTrue(script.is_file(), "scripts/teardown.sh is missing (PS-2.9)")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "scripts").mkdir()
        for extra in (ROOT / "scripts").glob("*.sh"):
            shutil.copy(extra, tmp / "scripts" / extra.name)
        for rel in (".env.example", "docker-compose.yml"):
            shutil.copy(ROOT / rel, tmp / rel)
        # platform-stack-ready (PS-2.22, security L-9; §2.4 Teardown leftovers):
        # teardown now resolves the project with `docker compose config` and
        # lists leftovers, so it needs the fake that answers like compose
        # (tests/fake_docker.py, same one-line FAKE_DOCKER_LOG format). Fixture
        # change only; the assertions below are unchanged.
        from tests import fake_docker

        fake_docker.install(tmp / "fakebin")
        log = tmp / "docker.log"
        env = _clean_env(PATH=f"{tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_LOG=str(log))
        result = _run(["bash", "scripts/teardown.sh", *args], env, cwd=tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return log.read_text(encoding="utf-8") if log.exists() else ""

    def test_teardown_keeps_volumes_unless_asked(self):
        downs = [l for l in self._teardown().splitlines() if " down" in f" {l}"]
        self.assertTrue(downs, "teardown did not call compose down")
        # No --remove-orphans assertion: ruling F3 (handoff "orchestrator: rework
        # round 2"; docs/architecture.md §2.4) removed it so teardown only
        # touches its own project's default services. Scope is checked in
        # Teardown{Sh,Ps1}ScopeTest.
        self.assertNotRegex(downs[-1], r"(?:^|\s)(?:-v|--volumes)(?:\s|$)")
        downs = [l for l in self._teardown("--volumes").splitlines() if " down" in f" {l}"]
        self.assertTrue(downs)
        self.assertRegex(downs[-1], r"(?:^|\s)(?:-v|--volumes)(?:\s|$)")


if __name__ == "__main__":
    unittest.main()
