"""platform-stack-up (2a): quickstart (PS-2.9) and carry-ins PS-2.15, PS-2.16,
PS-2.20 (docs/requirements.md § PS-2; placement table under PS-2)."""

from __future__ import annotations

import re
import tomllib
import unittest

from tests.engine_support import ROOT

QUICKSTART = ROOT / "docs" / "quickstart.md"
SCRIPT_PAIRS = ("build", "launch", "teardown")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class QuickstartTest(unittest.TestCase):
    """PS-2.9 and architecture §2.4 *Scripts*: Windows (PowerShell) and Linux
    (bash) only (Q20); prerequisites Git and Docker with Compose >= 2.24."""

    def test_quickstart_names_existing_scripts(self):
        self.assertTrue(QUICKSTART.is_file(), "docs/quickstart.md is missing (§2.4)")
        text = QUICKSTART.read_text(encoding="utf-8")
        named = set(re.findall(r"scripts[/\\]([\w.-]+\.(?:sh|ps1))", text))
        for name in sorted(named):
            with self.subTest(script=name):
                self.assertTrue((ROOT / "scripts" / name).is_file(), f"scripts/{name} does not exist")
        for stem in SCRIPT_PAIRS:
            for ext in ("sh", "ps1"):
                with self.subTest(required=f"{stem}.{ext}"):
                    self.assertTrue((ROOT / "scripts" / f"{stem}.{ext}").is_file())
                    self.assertIn(f"{stem}.{ext}", named, f"quickstart does not name {stem}.{ext}")
        for prerequisite in ("Git", "Docker", "2.24"):
            with self.subTest(prerequisite=prerequisite):
                self.assertIn(prerequisite, text)
        for line in text.splitlines():
            if re.search(r"(?i)mac\s?os|os x|apple silicon", line):
                with self.subTest(macos_line=line):
                    self.assertRegex(line, r"(?i)not supported|unsupported|out of scope",
                                     "the quickstart must not offer a macOS path (Q20)")


class TestShHeaderTest(unittest.TestCase):
    def test_test_sh_header_matches_integration_mechanism(self):  # PS-2.15
        lines = _read("scripts/test.sh").splitlines()
        header = []
        for line in lines[1:]:
            if not line.startswith("#"):
                break
            header.append(line)
        text = "\n".join(header)
        self.assertNotIn("testcontainers", text.lower())
        self.assertIn("tests/integration", text)
        self.assertIn("gates-it", text)


class AgentsHookWordingTest(unittest.TestCase):
    def test_agents_md_hook_wording_not_absolute(self):  # PS-2.16, security L24
        text = _read("AGENTS.md")
        match = re.search(r"^## Branch Policy\r?\n(.*?)(?=^## )", text, re.M | re.S)
        self.assertIsNotNone(match, "AGENTS.md has no Branch Policy section")
        section = " ".join(match.group(1).split())
        self.assertNotRegex(section, r"denies any commit", "the absolute wording is still there")
        self.assertRegex(section, r"(?i)guard ?rail")
        bypasses = {"variables": r"(?i)variable", "eval": r"`eval`|\beval\b",
                    "git aliases": r"(?i)alias", "encodings": r"(?i)encod",
                    "gh": r"`gh`|\bgh\b"}
        for name, pattern in bypasses.items():
            with self.subTest(bypass=name):
                self.assertRegex(section, pattern, f"Branch Policy does not name {name}")


class ProjectNameTest(unittest.TestCase):
    def test_pyproject_name_matches_project_name(self):  # PS-2.20, review N13
        from engine.telemetry import PROJECT_NAME

        with (ROOT / "pyproject.toml").open("rb") as handle:
            name = tomllib.load(handle)["project"]["name"]
        self.assertEqual(PROJECT_NAME, "knowledge-engine", "architecture §2.3 project name")
        self.assertEqual(name, PROJECT_NAME)
        lock = _read("uv.lock")
        self.assertRegex(lock, rf'(?m)^name = "{re.escape(name)}"\r?\n.*\r?\nsource = {{ editable = "\." }}',
                         "uv.lock is not regenerated for the new project name")


if __name__ == "__main__":
    unittest.main()
