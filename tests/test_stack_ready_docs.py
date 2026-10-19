"""platform-stack-ready (2b): PS-2.13 and the PS-3.4 key (fast).

- `test_claude_md_lists_verify_only_checks` (PS-2.13, Q30, umbrella ruling
  "model upstream in local verify"): CLAUDE.md has a section titled "What
  verify.sh runs that CI cannot" next to "What CI runs that verify.sh does
  not". It names the model-calling integration tests as running only where
  the model host is reachable and skipping by name on GitHub runners, and it
  names KE_MODEL_UPSTREAM and KE_EGRESS_ALLOWLIST as the only two keys a
  local `verify.sh full` takes from the caller's environment or the
  operator's `.env`, with the tests skipping by name when either is unset.
- `test_ci_job_has_timeout` (PS-3.4): every CI job sets `timeout-minutes`.
  Orchestrator ruling C1 (= Q36): the value stays 20 until 2b's first green
  CI run is measured; a follow-up commit then sets measured + 50%. So this
  test asserts the key, not the value.
"""

from __future__ import annotations

import re
import unittest

from tests.engine_support import ROOT

CLAUDE_MD = ROOT / "CLAUDE.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
VERIFY_ONLY = "What verify.sh runs that CI cannot"
CI_ONLY = "What CI runs that verify.sh does not"


def _sections(text: str) -> list[tuple[str, str]]:
    """(title, body) of every `## ` section, in order."""
    parts = re.split(r"(?m)^## +(.+?)\s*$", text)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


class ClaudeMdVerifyOnlyTest(unittest.TestCase):
    def test_claude_md_lists_verify_only_checks(self):
        sections = _sections(CLAUDE_MD.read_text(encoding="utf-8"))
        titles = [t for t, _ in sections]
        self.assertIn(VERIFY_ONLY, titles)
        self.assertIn(CI_ONLY, titles)
        self.assertEqual(abs(titles.index(VERIFY_ONLY) - titles.index(CI_ONLY)), 1,
                         "the two sections must sit next to each other")
        body = dict(sections)[VERIFY_ONLY]
        flat = " ".join(body.split())
        self.assertRegex(flat, r"(?i)model", "the section names the model-calling tests")
        self.assertRegex(flat, r"(?i)reachable")
        self.assertRegex(flat, r"(?i)skip")
        self.assertRegex(flat, r"(?i)GitHub|CI")
        for key in ("KE_MODEL_UPSTREAM", "KE_EGRESS_ALLOWLIST"):
            with self.subTest(key=key):
                self.assertIn(key, body)
        self.assertRegex(flat, r"\.env", "the section names the operator's .env")
        self.assertRegex(flat, r"(?i)environment", "the section names the caller's environment")
        self.assertRegex(flat, r"(?i)only|exactly|no other",
                         "the section says these are the only two keys taken")
        self.assertRegex(flat, r"(?i)unset|empty|not configured",
                         "the section says the tests skip when either key is unset")


class CiTimeoutTest(unittest.TestCase):
    def test_ci_job_has_timeout(self):
        import yaml

        workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
        jobs = workflow.get("jobs") or {}
        self.assertTrue(jobs, "ci.yml defines no jobs")
        for name, job in jobs.items():
            with self.subTest(job=name):
                self.assertIn("timeout-minutes", job,
                              f"job {name} has no timeout-minutes (PS-3.4, F6)")
                value = job["timeout-minutes"]
                self.assertIsInstance(value, int)
                self.assertGreater(value, 0)


if __name__ == "__main__":
    unittest.main()
