"""platform-stack-ready (2b), PS-2.21: the model upstream in local verify.

Umbrella ruling "model upstream in local verify" (2026-10-19), orchestrator
ruling Q35 (the caller env wins; only the repo-root `.env` counts), design
docs/architecture.md §2.2 "Model keys in local verify":

- `scripts/env_value.sh <NAME>` prints KE_MODEL_UPSTREAM or
  KE_EGRESS_ALLOWLIST, and nothing else: any other name exits 2 before
  anything runs. The caller's env wins, even when set empty. Otherwise it
  reads `.env` only through `docker compose -f docker-compose.yml --env-file
  .env config --format json gateway`, so `.env` is never sourced. A failing
  `config`, or a value with a JSON escape, exits non-zero without echoing
  file content (EnvValueScriptTest; cases count under PS-2.21, ruling of
  2026-10-19).
- `verify.sh full` passes exactly those two keys to its verify project
  (both or neither, with a note), before build.sh, and nothing else from
  `.env` (VerifyModelKeysTest: test_verify_full_passes_model_upstream_keys,
  test_verify_full_takes_no_other_env_key).

Both drive the real scripts in a throwaway tree with tests/fake_docker.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import fake_docker
from tests.engine_support import ROOT

ENV_VALUE = ROOT / "scripts" / "env_value.sh"
KEYS = ("KE_MODEL_UPSTREAM", "KE_EGRESS_ALLOWLIST")
SECRET = "s3cret-marker-never-printed"


def _clean_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir()}
    env.update(extra)
    return env


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | 0o111)


def _pairs(argv: list[str]) -> list[tuple[str, str]]:
    return list(zip(argv, argv[1:]))


class EnvValueScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(ENV_VALUE.is_file(),
                        "scripts/env_value.sh is missing (PS-2.21, architecture §2.2)")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "scripts").mkdir()
        shutil.copy(ENV_VALUE, self.tmp / "scripts" / "env_value.sh")
        for rel in (".env.example", "docker-compose.yml"):
            shutil.copy(ROOT / rel, self.tmp / rel)
        fake_docker.install(self.tmp / "fakebin")
        self.json = self.tmp / "docker.jsonl"

    def _dotenv(self, *lines: str) -> None:
        (self.tmp / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def _run(self, *args: str, **extra: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        self.json.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), **extra)
        result = subprocess.run(["bash", "scripts/env_value.sh", *args], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=60)
        return result, fake_docker.records(self.json)

    def test_env_value_refuses_any_other_name(self):
        self._dotenv(f"KE_STORES__POSTGRES__PASSWORD={SECRET}", "KE_ENV=prod",
                     "KE_MODEL_UPSTREAM=modelhost:8000")
        cases = {"KE_ENV": ("KE_ENV",), "a secret": ("KE_STORES__POSTGRES__PASSWORD",),
                 "a longer name": ("KE_MODEL_UPSTREAMX",), "lower case": ("ke_model_upstream",),
                 "empty name": ("",), "no name": (), "two names": KEYS}
        for case, args in cases.items():
            with self.subTest(case=case):
                result, records = self._run(*args, KE_STORES__POSTGRES__PASSWORD=SECRET)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(records, [], "a refused name must not reach docker")
                self.assertNotIn(SECRET, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")

    def test_env_value_caller_env_wins_even_when_empty(self):
        self._dotenv("KE_MODEL_UPSTREAM=fromfile:1", "KE_EGRESS_ALLOWLIST=fromfile")
        for key, value in ((KEYS[0], "caller-host:8000"), (KEYS[1], "caller-host"),
                           (KEYS[0], ""), (KEYS[1], "")):
            with self.subTest(key=key, value=value):
                result, records = self._run(key, **{key: value})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.rstrip("\n"), value)
                self.assertEqual(records, [], "the caller's value needs no docker call")

    def test_env_value_without_dotenv_is_empty(self):
        for key in KEYS:
            with self.subTest(key=key):
                result, records = self._run(key)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "")
                self.assertEqual(records, [], "no .env, so nothing to resolve")

    def test_env_value_reads_dotenv_only_through_compose_config(self):
        marker, marker2 = self.tmp / "sourced-marker", self.tmp / "sourced-marker-2"
        self._dotenv("export KE_MODEL_UPSTREAM=modelhost:8000",
                     "KE_EGRESS_ALLOWLIST = modelhost",
                     f"touch {marker}",
                     f"KE_X=$(touch {marker2})",
                     f"KE_STORES__POSTGRES__PASSWORD={SECRET}")
        for key, expected in zip(KEYS, ("modelhost:8000", "modelhost")):
            with self.subTest(key=key):
                result, records = self._run(key)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.rstrip("\n"), expected)
                self.assertFalse(marker.exists() or marker2.exists(), ".env was sourced or evaluated")
                self.assertNotIn(SECRET, result.stdout + result.stderr)
                configs = [r["argv"] for r in records if "config" in r["argv"]]
                self.assertEqual(len(configs), 1, f"expected one compose config call: {records}")
                argv = configs[0]
                self.assertEqual(argv[0], "compose")
                self.assertIn(("-f", "docker-compose.yml"), _pairs(argv))
                self.assertTrue({("--env-file", ".env"), ("--env-file", "./.env")} & set(_pairs(argv)),
                                f"config must read the repo-root .env: {argv}")
                self.assertIn(("--format", "json"), _pairs(argv))
                self.assertEqual(argv[-1], "gateway", "only the gateway service is rendered")

    def test_env_value_trusts_compose_resolution(self):
        self._dotenv("KE_MODEL_UPSTREAM=fromfile:1")
        result, _ = self._run(KEYS[0], FAKE_COMPOSE_RESOLVED=json.dumps({KEYS[0]: "resolved:9"}))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.rstrip("\n"), "resolved:9")

    def test_env_value_config_failure_is_reported_without_content(self):
        self._dotenv(f"KE_STORES__POSTGRES__PASSWORD={SECRET}", "KE_MODEL_UPSTREAM=modelhost:8000")
        for key in KEYS:
            with self.subTest(key=key):
                result, _ = self._run(key, FAKE_DOCKER_FAIL="config")
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, "a failed compose config was swallowed")
                self.assertIn(".env", output)
                self.assertIn(key, output)
                self.assertNotIn(SECRET, output)
                self.assertNotIn("fake docker", output, "compose's own stderr is discarded")
                self.assertNotIn("modelhost", result.stdout)

    def test_env_value_refuses_a_json_escaped_value(self):
        self._dotenv("KE_MODEL_UPSTREAM=x")
        result, _ = self._run(KEYS[0], FAKE_COMPOSE_RESOLVED=json.dumps({KEYS[0]: 'a"b:1'}))
        self.assertNotEqual(result.returncode, 0,
                            f"a value with a JSON escape was accepted: {result.stdout!r}")


STAGE = """#!/usr/bin/env bash
echo "{name}|${{KE_MODEL_UPSTREAM-<unset>}}|${{KE_EGRESS_ALLOWLIST-<unset>}}" >> "$STAGE_LOG"
env > "$STAGE_ENV_DIR/{name}.env"
exit 0
"""


class VerifyModelKeysTest(unittest.TestCase):
    """The real verify.sh host half and env_value.sh, stub stages that record
    their environment, and the fake docker (which records the gates-it run's
    COMPOSE_*/KE_* environment)."""

    def setUp(self) -> None:
        self.assertTrue(ENV_VALUE.is_file(),
                        "scripts/env_value.sh is missing (PS-2.21, architecture §2.2)")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "scripts").mkdir()
        for rel in ("scripts/verify.sh", "scripts/env_value.sh", "scripts/image_tag.sh", ".env.example",
                    "docker-compose.yml", "docker-compose.verify.yml"):
            shutil.copy(ROOT / rel, self.tmp / rel)
        # PSC-6 (ADR-KE-013 amendment 1, D4): verify full also runs scan.sh;
        # its stub records its environment like the others, so the caller-key
        # checks below cover it too once it runs.
        for name in ("build", "launch", "smoke", "teardown", "scan", "offline_check"):
            stub = self.tmp / "scripts" / f"{name}.sh"
            stub.write_text(STAGE.format(name=name), encoding="utf-8", newline="\n")
            _make_executable(stub)
        fake_docker.install(self.tmp / "fakebin")
        self.json = self.tmp / "docker.jsonl"
        self.log = self.tmp / "stages.log"
        self.env_dir = self.tmp / "stage-env"
        self.env_dir.mkdir()

    def _dotenv(self, *lines: str) -> None:
        (self.tmp / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def _verify(self, **extra: str) -> tuple[subprocess.CompletedProcess, list[str], list[dict]]:
        for f in (self.json, self.log):
            f.write_text("", encoding="utf-8")
        env = _clean_env(PATH=f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '')}",
                         FAKE_DOCKER_JSON=str(self.json), STAGE_LOG=str(self.log),
                         STAGE_ENV_DIR=str(self.env_dir), **extra)
        result = subprocess.run(["bash", "scripts/verify.sh", "full"], cwd=self.tmp, env=env,
                                capture_output=True, text=True, timeout=60)
        return (result, self.log.read_text(encoding="utf-8").splitlines(),
                fake_docker.records(self.json))

    @staticmethod
    def _gates_it(records: list[dict]) -> dict:
        runs = [r for r in records if "run" in r["argv"] and "gates-it" in r["argv"]]
        assert len(runs) == 1, f"expected one gates-it run: {[r['argv'] for r in records]}"
        return runs[0]

    @staticmethod
    def _stage(lines: list[str], name: str) -> tuple[str, str]:
        found = [l.split("|") for l in lines if l.startswith(name + "|")]
        assert found, f"stage {name} never ran: {lines}"
        return found[0][1], found[0][2]

    def _assert_keys(self, lines: list[str], records: list[dict],
                     upstream: str, allowlist: str) -> None:
        env = self._gates_it(records)["env"]
        self.assertEqual((env.get(KEYS[0], ""), env.get(KEYS[1], "")), (upstream, allowlist),
                         "the gates-it run did not get the model keys")
        for stage in ("build", "launch"):
            with self.subTest(stage=stage):
                got = tuple("" if v == "<unset>" else v for v in self._stage(lines, stage))
                self.assertEqual(got, (upstream, allowlist),
                                 f"{stage}.sh (so gateway, api and worker) did not get the keys")

    def test_verify_full_passes_model_upstream_keys(self):
        cases = {
            "caller env only": ({KEYS[0]: "modelhost:8000", KEYS[1]: "modelhost"}, None,
                                ("modelhost:8000", "modelhost")),
            ".env only": ({}, ["KE_MODEL_UPSTREAM=modelhost:8000", "KE_EGRESS_ALLOWLIST=modelhost"],
                          ("modelhost:8000", "modelhost")),
            "caller env wins over .env (Q35)": (
                {KEYS[0]: "caller:1", KEYS[1]: "caller"},
                ["KE_MODEL_UPSTREAM=fromfile:2", "KE_EGRESS_ALLOWLIST=fromfile"], ("caller:1", "caller")),
            "neither": ({}, None, ("", "")),
        }
        for case, (env, dotenv, expected) in cases.items():
            with self.subTest(case=case):
                (self.tmp / ".env").unlink(missing_ok=True)
                if dotenv is not None:
                    self._dotenv(*dotenv)
                result, lines, records = self._verify(**env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self._assert_keys(lines, records, *expected)

    def test_verify_full_model_keys_both_or_neither(self):
        cases = {"allowlist unset": {KEYS[0]: "modelhost:8000"},
                 "upstream empty": {KEYS[0]: "", KEYS[1]: "modelhost"}}
        for case, env in cases.items():
            with self.subTest(case=case):
                (self.tmp / ".env").unlink(missing_ok=True)
                result, lines, records = self._verify(**env)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self._assert_keys(lines, records, "", "")
                notes = [l for l in output.splitlines() if KEYS[0] in l and KEYS[1] in l]
                self.assertTrue(notes, f"verify must print one note naming both keys:\n{output}")

    def test_verify_full_stops_before_build_when_the_helper_fails(self):
        self._dotenv("KE_MODEL_UPSTREAM=modelhost:8000", "KE_EGRESS_ALLOWLIST=modelhost")
        result, lines, records = self._verify(FAKE_DOCKER_FAIL="config")
        self.assertNotEqual(result.returncode, 0, "verify went on after env_value.sh failed")
        self.assertFalse([l for l in lines if l.startswith("build|")], "build.sh ran after the failure")
        self.assertFalse([r for r in records if "gates-it" in r["argv"]])

    def test_verify_full_takes_no_other_env_key(self):
        port_marker = "47188"
        markers = {"KE_STORES__POSTGRES__PASSWORD": "MARK-secret-pg",
                   "KE_STORES__NEO4J__PASSWORD": "MARK-secret-neo",
                   "KE_ENV": "MARK-env", "KE_BIND_ADDRESS": "MARK-bind",
                   "KE_AUTH__ENABLED": "MARK-auth"}
        self._dotenv(*(f"{k}={v}" for k, v in markers.items()), f"KE_API_PORT={port_marker}",
                     "KE_MODEL_UPSTREAM=modelhost:8000", "KE_EGRESS_ALLOWLIST=modelhost")
        result, lines, records = self._verify()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self._assert_keys(lines, records, "modelhost:8000", "modelhost")
        for value in markers.values():
            with self.subTest(marker=value):
                self.assertNotIn(value, output)
                for record in records:
                    self.assertNotIn(value, json.dumps(record["argv"]) + json.dumps(record["env"]),
                                     f"a .env value reached docker: {record['argv']}")
                for stage_env in self.env_dir.glob("*.env"):
                    self.assertNotIn(value, stage_env.read_text(encoding="utf-8"),
                                     f"a .env value reached {stage_env.stem}.sh")
        for record in records:
            self.assertNotEqual(record["env"].get("KE_API_PORT"), port_marker)
            self.assertNotIn(port_marker, record["argv"])
        for stage_env in self.env_dir.glob("*.env"):
            self.assertNotIn(f"KE_API_PORT={port_marker}", stage_env.read_text(encoding="utf-8"))

    def test_verify_full_takes_no_caller_ke_key_but_the_model_keys(self):
        # Rework 1, security L-11 (ADR-KE-011 2b: verify uses placeholder
        # store secrets, "never real ones"): compose lets the process env
        # outrank --env-file, so the host half must drop every caller KE_*
        # except the two model keys before any stage or compose call. Keys
        # verify sets itself (KE_ENV_FILE, KE_SMOKE_OWNS_PROJECT) are not
        # caller values and are not checked here.
        markers = {"KE_STORES__POSTGRES__PASSWORD": "MARK-caller-pg",
                   "KE_STORES__NEO4J__PASSWORD": "MARK-caller-neo",
                   "KE_STORES__POSTGRES__HOST": "MARK-caller-pghost",
                   "KE_ENV": "MARK-caller-env", "KE_BIND_ADDRESS": "MARK-caller-bind",
                   "KE_AUTH__ENABLED": "MARK-caller-auth", "KE_API_PORT": "47177",
                   "KE_MODELS__COMPOSE__BASE_URL": "http://MARK-caller-url:1/v1",
                   "KE_SOMETHING_NEW": "MARK-caller-new"}
        result, lines, records = self._verify(KE_MODEL_UPSTREAM="modelhost:8000",
                                              KE_EGRESS_ALLOWLIST="modelhost", **markers)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self._assert_keys(lines, records, "modelhost:8000", "modelhost")
        stage_envs = {p.stem: p.read_text(encoding="utf-8") for p in self.env_dir.glob("*.env")}
        # Review U4 N4: scan and offline_check are named, so PSC-6 "the scan
        # takes no key from the caller's environment" is pinned, not incidental.
        self.assertTrue({"build", "launch", "smoke", "teardown", "scan", "offline_check"} <= set(stage_envs),
                        sorted(stage_envs))
        for key, value in markers.items():
            with self.subTest(key=key):
                for record in records:
                    self.assertNotIn(value, json.dumps(record["argv"]) + json.dumps(record["env"]),
                                     f"caller {key} reached docker: {record['argv']}")
                for stage, text in stage_envs.items():
                    self.assertNotIn(value, text, f"caller {key} reached {stage}.sh")


if __name__ == "__main__":
    unittest.main()
