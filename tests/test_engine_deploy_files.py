"""platform-config rework 1: .env and .gitignore (security M1).

- M1: a real `.env` (secrets) is git-ignored; `.env.example` is not.

Removed in platform-stack-up (contradiction, resolved in the same item):
`PhoenixDriftTest` (`test_compose_phoenix_defaults_match_config`, review B7c,
and `test_phoenix_published_on_loopback_only`, security M2) asserted that the
`phoenix` service publishes one port on `127.0.0.1`. By the ADR-KE-011 ports
amendment (2026-10-19) and docs/architecture.md §2.4, phoenix publishes
nothing and only `gateway` publishes, on `${KE_BIND_ADDRESS:-127.0.0.1}`.
Their assertions move, generalised, to tests/test_stack_compose.py:
- M2 (loopback publish): `test_published_ports_use_bind_address`, plus the
  bind-address refusals in tests/test_stack_bind_address.py;
- B7c host side (`KE_PHOENIX_PORT` default = .env.example):
  `test_compose_defaults_match_env_example` (PS-2.2 generalises it);
- B7c container side (phoenix's listen port = defaults.yaml collector port):
  `test_compose_phoenix_listen_port_matches_config`.
"""

from __future__ import annotations

import subprocess
import unittest

from tests.engine_support import ROOT


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
