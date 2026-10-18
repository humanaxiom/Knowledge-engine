"""The PreToolUse hook denies commit/push on main/master and stays silent
otherwise, so it never auto-approves a Bash call the user would be asked about.

Every JSON case is sent the way Claude Code sends it (compact JSON with the
full PreToolUse envelope) and runs twice: once with jq usable and once with a
fake jq that exits 127 first on PATH, so the no-jq fallback that the Windows
host uses is exercised in the gates image too (review B5, security H1).

Rule under test: ADR-KE-001 "Decision: commit hook is a simple fail-safe text
rule (2026-10-18)" in docs/architecture.md. The command text is normalised
(continuations joined, quotes and backslashes deleted, lower-cased). On
main/master: deny when it contains the word `git` and any of commit, push,
merge, cherry-pick, am, rebase, revert. Off main: deny a line with
`git ... push` followed on that line by main/master, --force(-with-lease),
--mirror, --all, a short-flag cluster containing f, or a + refspec."""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "block-main-commit.sh"

MODES = ("jq", "no-jq")


def claude_code_payload(command: str, cwd: str, description: str = "Run command") -> str:
    """The PreToolUse payload as Claude Code sends it: compact separators."""
    return json.dumps({
        "session_id": "00000000-0000-0000-0000-000000000000",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": description},
    }, separators=(",", ":"))


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "needs bash and git")
class BlockMainCommitHookTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        # A fake jq that exits 127 ("command not found"), first on PATH, makes
        # the hook take its no-jq path without any test-only switch in the hook.
        self.fake_jq_dir = tempfile.mkdtemp()
        fake = Path(self.fake_jq_dir) / "jq"
        fake.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8", newline="\n")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.fake_jq_dir, ignore_errors=True)

    def switch(self, branch: str) -> None:
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", branch], check=True)

    def env(self, mode: str) -> dict:
        env = dict(os.environ)
        if mode == "no-jq":
            env["PATH"] = self.fake_jq_dir + os.pathsep + env.get("PATH", "")
        return env

    def require_mode(self, mode: str) -> None:
        if mode == "jq" and not shutil.which("jq"):
            self.skipTest("needs jq (installed in the gates image)")

    def run_raw(self, stdin: str, mode: str) -> str:
        result = subprocess.run(["bash", str(HOOK)], input=stdin, cwd=self.repo,
                                env=self.env(mode), capture_output=True, text=True,
                                check=True)
        return result.stdout.strip()

    def run_hook(self, command: str, mode: str, description: str = "Run command") -> str:
        return self.run_raw(claude_code_payload(command, self.repo, description), mode)

    def decision(self, command: str, mode: str) -> str | None:
        out = self.run_hook(command, mode)
        if not out:
            return None
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"]

    def assert_all(self, commands, expected) -> None:
        for mode in MODES:
            for command in commands:
                with self.subTest(mode=mode, command=command):
                    self.require_mode(mode)
                    self.assertEqual(self.decision(command, mode), expected)

    def test_payload_helper_is_compact_claude_code_shape(self):
        payload = claude_code_payload("git commit -m x", "/r", "Commit")
        self.assertIn('"command":"git commit -m x"', payload)
        self.assertNotIn('": ', payload)
        self.assertEqual(json.loads(payload)["hook_event_name"], "PreToolUse")

    def test_denies_commit_and_push_on_main(self):
        self.assert_all(('git commit -m "x"', "git push origin main",
                         "git add . && git commit -m x", "git -C . commit --amend"), "deny")

    def test_denies_git_first_word_on_main(self):
        # Review B5 / security H1: git as the first word, target as the last
        # word, in the compact payload Claude Code sends.
        self.assert_all(("git commit -m x", "git push", "git merge x",
                         'git commit -m "quoted msg"'), "deny")

    def test_denies_on_master(self):
        self.switch("master")
        self.assert_all(("git commit -m x",), "deny")

    def test_silent_on_plan_item_branch(self):
        self.switch("agent/some-item")
        self.assert_all(("git commit -m x",), None)

    def test_silent_for_non_git_command(self):
        self.assert_all(("ls -la", "git status"), None)

    def test_denies_push_to_main_or_force_push_from_any_branch(self):
        # Security M1 and H1, review N7: from a plan-item branch, a push that
        # targets main or rewrites history is still denied.
        self.switch("agent/x")
        self.assert_all(("git push origin HEAD:main", "git push origin main",
                         "git push --force origin agent/x", "git push origin +agent/x",
                         'git push origin "main"', "git -C . push origin main",
                         "git push --all origin", "git push --mirror origin",
                         "git push -fu origin agent/x"), "deny")

    def test_silent_for_plain_push_of_plan_item_branch(self):
        self.switch("agent/x")
        self.assert_all(("git push origin agent/x", "git push -u origin agent/some-item"), None)

    def test_silent_for_text_that_only_mentions_push_on_plan_item_branch(self):
        # Review B6, narrowed by ADR-KE-001 "Decision: commit hook is a simple
        # fail-safe text rule (2026-10-18)": text that mentions push and main
        # is silent only while no single line says git, push and main. The
        # one-line B6 cases moved to
        # test_one_line_mentions_are_accepted_false_positives_off_main.
        self.switch("agent/x")
        heredoc = ("git commit -F - <<'EOF'\n"
                   "harness: hook\n"
                   "\n"
                   "note: a push to main is denied\n"
                   "EOF")
        self.assert_all((heredoc,
                         "git push origin agent/x",
                         "git log --oneline main"), None)

    # --- Rework 4: ADR-KE-001 simple fail-safe text rule; review B10/B11,
    # security H2/L13/M3. ---

    def test_one_line_mentions_are_accepted_false_positives_off_main(self):
        # ADR-KE-001 "Decision: commit hook is a simple fail-safe text rule
        # (2026-10-18)", Consequences: a one-line command that mentions git,
        # push and main is denied (fail safe). This reverses the B6 ruling, so
        # these cases moved here from the silent test above. The `-f` message
        # matches because `-f` follows `git ... push` on the same line.
        self.switch("agent/x")
        heredoc = ("git commit -F - <<'EOF'\n"
                   "harness: hook\n"
                   "\n"
                   "note: git push to main is denied\n"
                   "EOF")
        self.assert_all(('git commit -m "fix push to main docs"',
                         'git commit -m "docs: note push -f is denied"',
                         'echo "git push origin main is blocked"',
                         heredoc,
                         'bash -c "git push origin main"',
                         'echo "$(git push origin main)"'), "deny")

    def test_grep_for_a_verb_on_main_is_accepted_false_positive(self):
        # ADR-KE-001 (2026-10-18): on main any text with the word git and a
        # listed verb is denied, so a read-only log search is denied too.
        self.assert_all(("git log --grep revert",), "deny")

    def test_silent_for_everyday_commands_on_plan_item_branch(self):
        # ADR-KE-001 (2026-10-18): the rule must stay silent for the commands
        # an agent runs every day off main.
        self.switch("agent/x")
        heredoc = ("git commit -m \"$(cat <<'EOF'\n"
                   "harness: hook rework\n"
                   "\n"
                   "A push to main and a force push are denied.\n"
                   "EOF\n"
                   ")\"")
        self.assert_all(("git push origin agent/x",
                         "git push -u origin agent/harness-claude-code",
                         "git log --oneline -5",
                         "git diff 886de45 --stat",
                         heredoc,
                         "ls -la"), None)
        for mode in MODES:
            with self.subTest(mode=mode, command="ls + forged description"):
                self.require_mode(mode)
                self.assertEqual(
                    self.run_hook("ls", mode, 'note "command":"git push origin main"'), "")

    def test_backslash_forms_deny_push_off_main(self):
        # Security H2: line continuation, escaped quote and a backslash inside
        # a word must not hide a push to main or a force push.
        self.switch("agent/x")
        self.assert_all(("git push \\\norigin main",
                         "git push \\\n-f origin agent/x",
                         'git commit -m "a\\"b"; git push origin main',
                         "git push origin ma\\in"), "deny")

    def test_split_or_cased_git_word_denied_on_main(self):
        # Security L13: quotes, backslashes and case must not split the word
        # git on main (GIT runs git on the case-insensitive Windows host).
        self.assert_all(("g''it commit -m x",
                         '"g"it commit -m x',
                         "GIT commit -m x",
                         "Git commit -m x",
                         "gi\\t commit -m x"), "deny")

    def test_prefixed_push_to_main_denied_off_main(self):
        # Review B11: the redirection, backtick and leading-word forms.
        self.switch("agent/x")
        self.assert_all((">/dev/null git push origin main",
                         "echo `git push origin main`",
                         "! git push origin main",
                         "command git push origin main",
                         "exec git push origin main"), "deny")

    def test_shell_wrapped_commit_denied_on_main(self):
        # Review B11: sh -c and a bash heredoc whose body commits.
        self.assert_all(('sh -c "git commit -m x"',
                         "bash <<'EOF'\ngit commit -m x\nEOF"), "deny")

    def test_one_megabyte_token_shapes_finish_quickly(self):
        # Review B10 / security M3 (criterion 4f): 1 MB as one token, one
        # quoted -m message, one heredoc line, and many heredoc lines, each
        # under 3 s in both modes, off main where the whole rule runs.
        mb = 1_000_000
        cases = {
            "unquoted token": "echo " + "a" * mb,
            "-m message": 'git commit -m "' + "a" * mb + '"',
            "heredoc line": "cat <<'EOF'\n" + "a" * mb + "\nEOF",
            "heredoc lines": "cat <<'EOF'\n" + "abcdefghi\n" * (mb // 10) + "EOF",
        }
        self.switch("agent/x")
        for mode in MODES:
            for name, command in cases.items():
                with self.subTest(mode=mode, shape=name):
                    self.require_mode(mode)
                    self.assertGreaterEqual(len(command), mb)
                    start = time.monotonic()
                    out = self.run_hook(command, mode)
                    elapsed = time.monotonic() - start
                    self.assertEqual(out, "")
                    self.assertLess(elapsed, 3.0)

    def test_denies_commit_creating_commands_on_main(self):
        # Security M1: these create or rewrite commits on the current branch.
        self.assert_all(("git merge x", "git cherry-pick abc", "git am p.patch",
                         "git rebase x", "git revert abc"), "deny")

    def test_judges_only_the_command_field(self):
        # Security N1/H1: only tool_input.command is judged, so a payload whose
        # description mentions a commit is not denied, with or without jq.
        for mode in MODES:
            with self.subTest(mode=mode):
                self.require_mode(mode)
                self.assertEqual(self.run_hook("ls", mode, "prepare git commit"), "")
                self.assertEqual(self.decision('git commit -m "x"', mode), "deny")

    def test_long_command_finishes_quickly(self):
        # Security L8: the hook timeout is 10 s; 400 segments must take < 5 s.
        self.switch("agent/x")
        command = " && ".join(f"echo {i}" for i in range(400))
        for mode in MODES:
            with self.subTest(mode=mode):
                self.require_mode(mode)
                start = time.monotonic()
                out = self.run_hook(command, mode)
                elapsed = time.monotonic() - start
                self.assertEqual(out, "")
                self.assertLess(elapsed, 5.0)

    # --- Rework 3: review B8/B9, security M1/L9/L10, orchestrator ruling. ---
    # On main/master the rule is broad and fail-safe: any command text that
    # contains `git` and commit/push/merge/cherry-pick/am/rebase/revert is
    # denied, nested, quoted, `bash -c` and heredoc forms included. Off main,
    # per ADR-KE-001 "Decision: commit hook is a simple fail-safe text rule
    # (2026-10-18)", the precise lexer is gone: `"$(...)"`, `bash -c` and
    # `sh -c` are denied when one line says git, push and main (see
    # test_one_line_mentions_are_accepted_false_positives_off_main). Hidden
    # words (variables, eval, aliases, encodings), gh, update-ref and a push
    # split across lines without a continuation stay accepted bypasses and
    # are deliberately not tested as denied.

    def test_denies_nested_git_on_main(self):
        # Review B8 / security M1: every shape below was silent on main after
        # rework 2; the base hook (886de45) denied them.
        self.assert_all(("(git push origin main)",
                         "echo $(git push origin main)",
                         "out=$(git commit -m x 2>&1)",
                         'echo "$(git commit -m x)"',
                         "echo `git commit -m x`",
                         "{ git commit -m x; }",
                         "if git push origin main; then echo ok; fi",
                         "! git commit -m x",
                         "sleep 1 & git commit -m x",
                         "time git commit -m x",
                         'bash -c "git commit -m x"',
                         "echo $((1<<2)) && git commit -m x"), "deny")

    def test_denies_nested_push_to_main_or_force_from_plan_item_branch(self):
        # Review B8, security M1/L10: unquoted & ( ) { } $( and backtick are
        # segment breaks; leading ! / keywords / time / command / env / exec
        # are skipped; $(( is arithmetic, not a heredoc.
        self.switch("agent/x")
        self.assert_all(("(git push origin main)",
                         "{ git push origin main; }",
                         "if git push origin main; then :; fi",
                         "true & git push origin main",
                         "env git push origin main",
                         "echo $(git push --force origin agent/x)",
                         "echo $((1<<2))\ngit push origin main"), "deny")

    def test_denies_push_with_c_global_option_from_plan_item_branch(self):
        # Review B9: the `-c` skip is otherwise untested.
        self.switch("agent/x")
        self.assert_all(("git -c x=y push origin main",), "deny")

    def test_denies_push_refspec_forms_from_plan_item_branch(self):
        # Review B9: refs/heads/ strip, delete refspec, lease, plain -f, master.
        self.switch("agent/x")
        self.assert_all(("git push origin refs/heads/main",
                         "git push origin :main",
                         "git push --force-with-lease origin agent/x",
                         "git push -f origin agent/x",
                         "git push origin master"), "deny")

    def test_denies_push_on_master(self):
        # Review B9: the only master case was commit.
        self.switch("master")
        self.assert_all(("git push",), "deny")

    def test_escaped_quote_does_not_hide_following_push(self):
        # Review B9 (pins the B6 lexer): an escaped quote inside the message
        # must not swallow the next segment.
        self.switch("agent/x")
        self.assert_all(('git commit -m "x \\"y\\"" && git push origin main',), "deny")

    def test_silent_for_claude_code_heredoc_commit_on_plan_item_branch(self):
        # Review B9: the exact form Claude Code writes commits in. Under
        # ADR-KE-001 "Decision: commit hook is a simple fail-safe text rule
        # (2026-10-18)" a body line saying git, push and main is an accepted
        # false positive, so the body mentions push and main without git.
        self.switch("agent/x")
        command = ("git commit -m \"$(cat <<'EOF'\n"
                   "harness: hook\n"
                   "\n"
                   "note: push to main and push --force are denied\n"
                   "EOF\n"
                   ")\"")
        self.assert_all((command,), None)

    def test_description_with_forged_command_key_is_not_judged(self):
        # Review B9 (pins H1): a description that carries a forged command key.
        for mode in MODES:
            with self.subTest(mode=mode):
                self.require_mode(mode)
                self.assertEqual(
                    self.run_hook("ls", mode, 'note "command":"git push origin main"'), "")

    def test_one_megabyte_command_finishes_quickly(self):
        # Security L9: the hook was quadratic (1 MB took 3-12 s; the Claude
        # Code timeout is 10 s). ~1 MB of `echo x &&` segments must take < 3 s.
        body = "echo x && " * 100_000 + "echo x"
        self.assertGreaterEqual(len(body), 1_000_000)
        self.switch("agent/x")
        for mode in MODES:
            with self.subTest(mode=mode):
                self.require_mode(mode)
                start = time.monotonic()
                out = self.run_hook(body, mode)
                elapsed = time.monotonic() - start
                self.assertEqual(out, "")
                self.assertLess(elapsed, 3.0)

    def test_works_without_jq_on_raw_input(self):
        # Git Bash on Windows has no jq; the hook falls back to scanning stdin.
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertIn('"deny"', self.run_raw("git commit -m x", mode))


class GatesImageJqTest(unittest.TestCase):
    def test_gates_image_installs_jq(self):
        # Security N1: without jq in the gates image the jq-mode cases above
        # are always skipped there and the jq path is never exercised.
        dockerfile = (HOOK.parent.parent.parent / "docker" / "gates.Dockerfile").read_text(
            encoding="utf-8")
        install = re.search(r"apt-get install[^\n]*(?:\\\n[^\n]*)*", dockerfile)
        self.assertIsNotNone(install, "no apt-get install in gates.Dockerfile")
        self.assertRegex(install.group(0), r"\bjq\b")


if __name__ == "__main__":
    unittest.main()
