"""Plan item harness-claude-code: the Copilot workflow runs natively in Claude Code.

Each test maps to a criterion in docs/requirements.md § harness-claude-code.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPILOT = ROOT / ".github" / "agents"
CLAUDE_AGENTS = ROOT / ".claude" / "agents"
ROLES = ("analyst", "architect", "developer", "tester",
         "reviewer", "security", "documenter", "marketer")
PRODUCERS = ("developer", "tester", "documenter")
REASONING = ("analyst", "architect", "tester", "reviewer", "security")
TRIVIAL = ("developer", "documenter", "marketer")

# Commands that run a gate. Only `scripts/verify.sh` may appear in agent
# files and CLAUDE.md, so no agent can improvise a narrower check.
STRAY_VERIFICATION = re.compile(
    r"scripts/(?:test|smoke)\.sh|\bpytest\b|\bunittest\b|\bmypy\b|\bruff\b"
    r"|make gates|smoke_otlp")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise AssertionError("missing frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def section(text: str, heading: str) -> str:
    """Body of a `## heading` section, up to the next `## ` heading."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not match:
        raise AssertionError(f"missing section: {heading}")
    return match.group(1).strip()


def marked_block(text: str, name: str) -> str:
    match = re.search(rf"<!-- {name}:start -->\n(.*?)<!-- {name}:end -->", text, re.S)
    if not match:
        raise AssertionError(f"missing marked block: {name}")
    return match.group(1)


def duty_step(text: str) -> str:
    """The numbered 'Append your section …' step, normalised for numbering."""
    match = re.search(r"^\d+\.\s+(Append your section.*?never edit the log by hand\)\.)",
                      text, re.S | re.M)
    if not match:
        raise AssertionError("missing handoff/log duty step")
    return re.sub(r"\s+", " ", match.group(1))


def claude_agent(role: str) -> str:
    return read(CLAUDE_AGENTS / f"{role}.md")


# Roles whose Claude Code body must be the Copilot body, byte for byte.
NON_PRODUCERS = tuple(r for r in ROLES if r not in PRODUCERS)
# Sections a producer port may add on top of the Copilot source.
ALLOWED_EXTRA_SECTIONS = {"Verification depth", "Evidence contract", "Contradictions"}
# A Copilot Approach step that is about verification (so the port may reword it).
VERIFICATION_STEP = re.compile(r"(?i)test|smoke|verif|gate")


def body(text: str) -> str:
    """Everything after the frontmatter, with CRLF normalised to LF."""
    text = text.replace("\r\n", "\n")
    match = re.match(r"---\n.*?\n---\n", text, re.S)
    if not match:
        raise AssertionError("missing frontmatter")
    return text[match.end():]


def sections(text: str) -> dict[str, str]:
    """`## heading` -> section text; the text before the first heading is ''."""
    parts = re.split(r"^## (.+)\n", text, flags=re.M)
    found = {"": parts[0].strip()}
    for heading, content in zip(parts[1::2], parts[2::2]):
        found[heading.strip()] = content.strip()
    return found


def numbered_steps(approach: str) -> list[str]:
    """Split an Approach section into its numbered steps, numbers removed."""
    return [step.strip() for step in re.split(r"^\d+\.\s+", approach, flags=re.M)[1:]]


class ClaudeMdTest(unittest.TestCase):
    def test_claude_md_imports_agents(self):
        text = read(ROOT / "CLAUDE.md")
        self.assertIn("@AGENTS.md", text)
        self.assertRegex(text, r"(?i)you are the \*\*orchestrator\*\*")
        self.assertRegex(text, r"(?i)never skip a gate")

    def test_delivery_rules_present(self):
        text = read(ROOT / "CLAUDE.md")
        for phrase in ("outcome metric", "end-to-end smoke", "deployable offline",
                       "never restate live counts", "200 lines"):
            self.assertIn(phrase, text, phrase)

    def test_ci_only_and_generated_artifacts_listed(self):
        text = read(ROOT / "CLAUDE.md")
        section(text, "What CI runs that verify.sh does not")
        generated = section(text, "Generated artifacts")
        self.assertIn("uv.lock", generated)


class AgentPortTest(unittest.TestCase):
    def test_every_role_ported(self):
        for role in ROLES:
            self.assertTrue((CLAUDE_AGENTS / f"{role}.md").is_file(), role)

    def test_copilot_agents_kept(self):
        for role in (*ROLES, "orchestrator"):
            self.assertTrue((COPILOT / f"{role}.agent.md").is_file(), role)

    def test_agent_port_preserves_constraints(self):
        for role in ROLES:
            source = read(COPILOT / f"{role}.agent.md")
            ported = claude_agent(role)
            with self.subTest(role=role):
                self.assertEqual(section(ported, "Constraints"), section(source, "Constraints"))
                self.assertEqual(duty_step(ported), duty_step(source))
                self.assertEqual(frontmatter(ported)["name"], role)
                self.assertTrue(frontmatter(ported)["description"])

    def test_non_producer_body_identical_to_copilot(self):
        # Requirement 2: file ownership, Approach and Output Format carry over
        # unchanged for roles that run no verification.
        for role in NON_PRODUCERS:
            with self.subTest(role=role):
                self.assertEqual(body(claude_agent(role)),
                                 body(read(COPILOT / f"{role}.agent.md")))

    def test_producer_sections_identical_except_verification_steps(self):
        for role in PRODUCERS:
            source = sections(body(read(COPILOT / f"{role}.agent.md")))
            ported = sections(body(claude_agent(role)))
            with self.subTest(role=role):
                for heading, content in source.items():
                    if heading == "Approach":
                        continue
                    self.assertEqual(ported.get(heading), content, heading or "preamble")
                self.assertLessEqual(set(ported) - set(source), ALLOWED_EXTRA_SECTIONS)

                source_steps = numbered_steps(source["Approach"])
                ported_steps = numbered_steps(ported["Approach"])
                self.assertEqual(len(ported_steps), len(source_steps))
                for number, (old, new) in enumerate(zip(source_steps, ported_steps), 1):
                    if old == new:
                        continue
                    with self.subTest(step=number):
                        # Only a verification step may change, and only to
                        # point at scripts/verify.sh.
                        self.assertRegex(old, VERIFICATION_STEP)
                        self.assertIn("scripts/verify.sh", new)

    def test_agent_model_tiers(self):
        for role in REASONING:
            self.assertEqual(frontmatter(claude_agent(role))["model"], "opus", role)
        for role in TRIVIAL:
            self.assertIn(frontmatter(claude_agent(role))["model"], {"sonnet", "haiku"}, role)

    def test_judges_cannot_edit(self):
        for role in ("reviewer", "security"):
            tools = frontmatter(claude_agent(role))["tools"]
            self.assertNotIn("Edit", tools, role)
            self.assertNotIn("Write", tools, role)


class VerificationEntryPointTest(unittest.TestCase):
    def test_verify_sh_has_no_inlined_commands(self):
        text = read(ROOT / "scripts" / "verify.sh")
        body = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith("#"))
        # platform-offline (architecture §2.6 item 10): the bundle and the
        # offline check keep their commands in bundle.sh / offline_check.sh.
        # platform-supply-chain PSC-6 (ADR-KE-013 amendment 1, D4): the image
        # scan keeps its scanner in scan.sh and docker-compose.scan.yml.
        for forbidden in ("pytest", "unittest", "mypy", "ruff", "uv run", "smoke_otlp",
                          "docker save", "sha256sum", "grype"):
            self.assertNotIn(forbidden, body, forbidden)
        self.assertIn("scripts/test.sh", body)
        self.assertIn("scripts/smoke.sh", body)

    def test_ci_calls_verify_only(self):
        ci = read(ROOT / ".github" / "workflows" / "ci.yml")
        runs = re.findall(r"^\s*run:\s*(.+)$", ci, re.M)
        self.assertEqual(runs, ["./scripts/verify.sh full"])

    def test_no_stray_verification_commands(self):
        # AGENTS.md is imported by CLAUDE.md (`@AGENTS.md`), so it loads into
        # every session and counts as part of it.
        files = [ROOT / "CLAUDE.md", ROOT / "AGENTS.md",
                 *(CLAUDE_AGENTS / f"{r}.md" for r in ROLES)]
        for path in files:
            with self.subTest(file=path.name):
                self.assertIsNone(STRAY_VERIFICATION.search(read(path)))

    def test_gate_scripts_use_locked(self):
        # Requirement 9 (amended): uv.lock drift is caught because every uv
        # call in the gates runs with --locked.
        paths = [*sorted((ROOT / "scripts").glob("*.sh")),
                 ROOT / "docker" / "gates.Dockerfile"]
        calls = []
        for path in paths:
            for line in read(path).splitlines():
                if line.lstrip().startswith("#"):
                    continue
                for match in re.finditer(r"\buv\s+(?:run|sync)\b[^;&|]*", line):
                    calls.append((path.name, match.group(0)))
        self.assertTrue(calls, "no uv run/sync found in the gate scripts")
        for name, call in calls:
            with self.subTest(file=name, call=call):
                self.assertIn("--locked", call)

    def test_depth_table_identical_everywhere(self):
        reference = marked_block(read(ROOT / "CLAUDE.md"), "depth-table")
        self.assertIn("scripts/verify.sh full", reference)
        self.assertIn("scripts/verify.sh fast", reference)
        for role in PRODUCERS:
            self.assertEqual(marked_block(claude_agent(role), "depth-table"), reference, role)

    def test_evidence_contract_present(self):
        reference = marked_block(read(ROOT / "CLAUDE.md"), "evidence-contract")
        for phrase in ("exact command", "last ~15 lines", "now green that was red"):
            self.assertIn(phrase, reference)
        for role in PRODUCERS:
            self.assertEqual(marked_block(claude_agent(role), "evidence-contract"),
                             reference, role)
        self.assertIn("RED", claude_agent("tester"))
        claude_md = re.sub(r"\s+", " ", read(ROOT / "CLAUDE.md"))
        self.assertIn("re-run `scripts/verify.sh full` yourself and read the diff", claude_md)

    def test_tester_owns_contradictions(self):
        self.assertRegex(claude_agent("tester"),
                         r"(?is)contradict.*same commit.*decision record")


class SettingsTest(unittest.TestCase):
    def test_hook_wired_on_bash(self):
        settings = json.loads(read(ROOT / ".claude" / "settings.json"))
        entries = settings["hooks"]["PreToolUse"]
        bash = [e for e in entries if e.get("matcher") == "Bash"]
        self.assertEqual(len(bash), 1)
        commands = [h["command"] for h in bash[0]["hooks"]]
        self.assertTrue(any("scripts/hooks/block-main-commit.sh" in c for c in commands))


class HandoffCapTest(unittest.TestCase):
    def test_handoff_line_cap(self):
        handoffs = ROOT / "docs" / "handoffs"
        for path in handoffs.glob("*.md"):
            if path.name == "README.md":
                continue
            with self.subTest(handoff=path.name):
                self.assertLessEqual(len(read(path).splitlines()), 200)

    def test_done_check_in_handoff_readme(self):
        text = read(ROOT / "docs" / "handoffs" / "README.md")
        self.assertIn("Milestone Done check", text)


if __name__ == "__main__":
    unittest.main()
