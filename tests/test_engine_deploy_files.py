"""platform-config rework 1: compose, .env and .gitignore (review B7c; security M1, M2).

- B7c (ruling 1, amended by B7a): compose publishes Phoenix as
  `${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}`. The container-side
  default must equal the port of `telemetry.collector_endpoint` in
  config/defaults.yaml, and the host-side default must equal
  `KE_PHOENIX_PORT` in .env.example (architecture §2.3, ADR-KE-010 Compose).
- M1: a real `.env` (secrets) is git-ignored; `.env.example` is not.
- M2: Phoenix (no auth) is published on 127.0.0.1 only.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from typing import Any
from urllib.parse import urlsplit

from tests.engine_support import DEFAULTS, ROOT, read_env_example

COMPOSE = ROOT / "docker-compose.yml"


def _compose() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _phoenix() -> dict[str, Any]:
    return _compose()["services"]["phoenix"]


def _default_of(text: str, var: str) -> str | None:
    match = re.search(rf"\$\{{{var}:-([^}}]*)\}}", text)
    return match.group(1) if match else None


def _port_entries() -> list[Any]:
    ports = _phoenix().get("ports", [])
    return [p for p in ports if p is not None]


class PhoenixDriftTest(unittest.TestCase):
    def test_compose_phoenix_defaults_match_config(self):
        import yaml

        entries = [p if isinstance(p, str) else
                   f"{p.get('host_ip', '')}:{p.get('published', '')}:{p.get('target', '')}"
                   for p in _port_entries()]
        self.assertEqual(len(entries), 1, f"phoenix should publish one port: {entries}")
        entry = entries[0]

        container = _default_of(entry, "PHOENIX_PORT")
        host = _default_of(entry, "KE_PHOENIX_PORT")
        self.assertIsNotNone(container, f"container side is not ${{PHOENIX_PORT:-...}}: {entry}")
        self.assertIsNotNone(host, f"host side is not ${{KE_PHOENIX_PORT:-...}}: {entry}")

        defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
        endpoint = urlsplit(defaults["telemetry"]["collector_endpoint"])
        self.assertEqual(container, str(endpoint.port),
                         "compose PHOENIX_PORT default != defaults.yaml collector port")
        self.assertEqual(host, read_env_example().get("KE_PHOENIX_PORT"),
                         "compose KE_PHOENIX_PORT default != .env.example KE_PHOENIX_PORT")

        # Phoenix's own listen port uses the same default.
        env = _phoenix().get("environment", {})
        listen = env.get("PHOENIX_PORT") if isinstance(env, dict) else next(
            (e.split("=", 1)[1] for e in env if e.startswith("PHOENIX_PORT=")), None)
        self.assertEqual(_default_of(str(listen), "PHOENIX_PORT"), container)

    def test_phoenix_published_on_loopback_only(self):  # security M2
        entries = _port_entries()
        self.assertTrue(entries, "phoenix publishes no port")
        for entry in entries:
            with self.subTest(entry=entry):
                if isinstance(entry, dict):
                    self.assertEqual(entry.get("host_ip"), "127.0.0.1")
                else:
                    self.assertTrue(str(entry).startswith("127.0.0.1:"),
                                    f"published on every interface: {entry}")


class GitIgnoreTest(unittest.TestCase):  # security M1
    def _ignored(self, path: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", path],
            capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_env_file_is_ignored(self):
        self.assertTrue(self._ignored(".env"), ".env (real secrets) is not git-ignored")

    def test_env_example_is_not_ignored(self):
        self.assertFalse(self._ignored(".env.example"), ".env.example must stay tracked")


if __name__ == "__main__":
    unittest.main()
