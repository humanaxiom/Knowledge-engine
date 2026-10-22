"""platform-stack-ready (2b): PS-2.13 and the PS-3.4 key (fast).

- `test_claude_md_lists_verify_only_checks` (PS-2.13, Q30, umbrella ruling
  "model upstream in local verify"): CLAUDE.md has a section titled "What
  verify.sh runs that CI cannot" next to "What CI runs that verify.sh does
  not". It names the model-calling integration tests as running only where
  the model host is reachable and skipping by name on GitHub runners, and it
  names KE_MODEL_UPSTREAM and KE_EGRESS_ALLOWLIST as the only two keys a
  local `verify.sh full` takes from the caller's environment or the
  operator's `.env`, with the tests skipping by name when either is unset.
- `test_ci_job_has_timeout` (PS-3.4): every CI job sets `timeout-minutes`
  to CI_TIMEOUT_MINUTES, which is the slower of the latest two green CI runs
  + 50%, rounded up. PSC-9 (platform-supply-chain) re-measured on 34fc0c1:
  push run 39713504156 took 24.5 min (1469 s, 02:49:44 to 03:14:13) and
  pull_request run 39713519072 took 23.0 min (1380 s, 02:49:55 to 03:12:55);
  docs/evidence/platform-supply-chain/ci/. The slower run + 50% =
  24.5 x 1.5 = 36.75, rounded up to 37. Earlier pin: ci-speed CS-7, 32.
- `CiTriggersTest` (ci-triggers, ADR-KE-015): ci.yml's `on:` has exactly
  `push` (only `branches: [DEFAULT_BRANCH]`) and an unfiltered
  `pull_request` (CT-1, Q-CT1); concurrency stays `ci-${{ github.ref }}` with
  `cancel-in-progress: true` (CT-3, Q-CT2, a pin); AGENTS.md Branch Policy and
  README say CI runs only on default-branch pushes and pull requests, that a
  branch pushed with no open PR gets no CI, and (AGENTS.md) that a PR with a
  merge conflict gets no run (CT-6).
"""

from __future__ import annotations

import re
import unittest

from tests.engine_support import ROOT

CLAUDE_MD = ROOT / "CLAUDE.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
VERIFY_ONLY = "What verify.sh runs that CI cannot"
CI_ONLY = "What CI runs that verify.sh does not"
# PS-3.4, PSC-9 platform-supply-chain (measured + 50%, using the slower green
# run): runs 39713504156 at 24.5 min and 39713519072 at 23.0 min
# (docs/evidence/platform-supply-chain/ci/ci-39713504156.log,
# ci-39713519072.log). The slower run sets the bound: 24.5 x 1.5 = 36.75,
# rounded up to 37. Before it, ci-speed CS-7 set 32.
CI_TIMEOUT_MINUTES = 37
# ci-triggers CT-1, Q-CT5: the repo's default branch, pinned literally because
# `$default-branch` works only in workflow templates. Renaming the default
# branch must update this constant and the `push: branches:` list in ci.yml
# together, or push CI on the default branch stops silently.
DEFAULT_BRANCH = "ccr-19465ed4-j1u0m5"
AGENTS_MD = ROOT / "AGENTS.md"
README_MD = ROOT / "README.md"
# CT-6 phrases, matched lowercased and whitespace-normalised.
CI_TRIGGER_PHRASE = "ci runs only on pushes to the default branch and on pull requests"
NO_PR_NO_CI_PHRASE = "a branch pushed with no open pr gets no ci"
MERGE_CONFLICT_PHRASE = "merge conflict"


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
                self.assertEqual(value, CI_TIMEOUT_MINUTES,
                                 f"job {name}: timeout-minutes is {value}, the ruling is "
                                 f"{CI_TIMEOUT_MINUTES} (PS-3.4, PSC-9 platform-supply-chain: "
                                 f"green CI runs 39713504156 24.5 min and "
                                 f"39713519072 23.0 min; slower run + 50% = "
                                 f"36.75 -> 37)")


def _flat(text: str) -> str:
    """Lowercased, whitespace-normalised text (CT-6 phrase matching)."""
    return " ".join(text.lower().split())


class CiTriggersTest(unittest.TestCase):
    """ci-triggers CT-1, CT-3, CT-6 (ADR-KE-015)."""

    def _load(self, path=CI):
        import yaml

        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIsInstance(workflow, dict, f"{path} is not a YAML mapping")
        return workflow

    def assert_triggers(self, path=CI):
        """CT-1 on the workflow at `path` (a path so mutants can be checked)."""
        workflow = self._load(path)
        # PyYAML reads the bare key `on` as the boolean True.
        on = workflow.get("on", workflow.get(True))
        self.assertIsNotNone(on, "ci.yml has no `on:` block (CT-1)")
        self.assertIsInstance(on, dict, "`on:` must be a mapping of events (CT-1)")
        self.assertEqual(set(on), {"push", "pull_request"},
                         "`on:` must have exactly push and pull_request; no "
                         "workflow_dispatch, schedule or pull_request_target (CT-1)")
        self.assertEqual(on["push"], {"branches": [DEFAULT_BRANCH]},
                         f"push must have only `branches: [{DEFAULT_BRANCH}]`; no tags, "
                         f"paths, paths-ignore or branches-ignore (CT-1, Q-CT5)")
        self.assertIn(on["pull_request"], (None, {}),
                      "pull_request must have no filter (CT-1, Q-CT1)")

    def test_ci_triggers_push_default_branch_and_pull_request(self):  # CT-1
        self.assert_triggers(CI)

    def test_ci_concurrency_per_ref(self):  # CT-3, Q-CT2 (a pin)
        concurrency = self._load().get("concurrency")
        self.assertIsInstance(concurrency, dict, "ci.yml has no concurrency mapping (CT-3)")
        self.assertEqual(concurrency.get("group"), "ci-${{ github.ref }}",
                         "concurrency group must stay per ref (CT-3)")
        self.assertIs(concurrency.get("cancel-in-progress"), True,
                      "cancel-in-progress must stay true for both events (CT-3, Q-CT2)")

    def test_docs_say_ci_needs_a_pull_request(self):  # CT-6
        text = AGENTS_MD.read_text(encoding="utf-8")
        match = re.search(r"^## Branch Policy\r?\n(.*?)(?=^## )", text, re.M | re.S)
        self.assertIsNotNone(match, "AGENTS.md has no Branch Policy section")
        section = _flat(match.group(1))
        for phrase in (CI_TRIGGER_PHRASE, NO_PR_NO_CI_PHRASE, MERGE_CONFLICT_PHRASE):
            with self.subTest(doc="AGENTS.md Branch Policy", phrase=phrase):
                self.assertIn(phrase, section,
                              f"AGENTS.md Branch Policy does not say {phrase!r} (CT-6)")
        readme = _flat(README_MD.read_text(encoding="utf-8"))
        for phrase in (CI_TRIGGER_PHRASE, NO_PR_NO_CI_PHRASE):
            with self.subTest(doc="README.md", phrase=phrase):
                # assertTrue, not assertIn: a failure must not dump all of README.md.
                self.assertTrue(phrase in readme, f"README.md does not say {phrase!r} (CT-6)")


if __name__ == "__main__":
    unittest.main()
