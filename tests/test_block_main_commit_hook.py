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
from unittest import mock

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

    # --- harness-followups: PS-0.4 (security M4) and PS-0.5 (review N16,
    # N17), docs/requirements.md § platform-skeleton. ---

    def cr_payloads(self, command: str) -> dict:
        """The compact payload with each CR as the JSON `\\r` escape, and the
        same payload with a literal CR byte in the string."""
        escaped = claude_code_payload(command, self.repo)
        self.assertIn("\\r", escaped)
        return {"escaped": escaped, "literal": escaped.replace("\\r", "\r")}

    def assert_cr_same_as_without(self, commands, expected) -> None:
        for mode in MODES:
            for command in commands:
                for form, payload in self.cr_payloads(command).items():
                    with self.subTest(mode=mode, command=command, cr=form):
                        self.require_mode(mode)
                        plain = self.decision(command.replace("\r", ""), mode)
                        self.assertEqual(plain, expected, "baseline without CR")
                        out = self.run_raw(payload, mode)
                        got = (json.loads(out)["hookSpecificOutput"]["permissionDecision"]
                               if out else None)
                        self.assertEqual(got, plain)

    def test_carriage_return_denies_as_without_it_on_main(self):
        # PS-0.4 / security M4: a CR must not hide `git` or the verb on main
        # (it failed open on the no-jq host path: `\r` became a letter r).
        self.assert_cr_same_as_without(("git commit -m x\r\n",
                                        "git\r commit -m x"), "deny")

    def test_carriage_return_denies_as_without_it_off_main(self):
        # PS-0.4 / security M4, criterion 4d push rules off main.
        self.switch("agent/x")
        self.assert_cr_same_as_without(("git push origin main\r",
                                        "git status\r\ngit push origin main"), "deny")

    def test_carriage_return_stays_silent_as_without_it(self):
        # PS-0.4: "exactly as without the CR" also means no new denials.
        self.assert_cr_same_as_without(("ls -la\r\n",), None)
        self.switch("agent/x")
        self.assert_cr_same_as_without(("git push origin agent/x\r\n",), None)

    def test_backslash_newline_joins_to_nothing_off_main(self):
        # PS-0.5 / review N16: `ma\<newline>in` is read as `main` and
        # `pu\<newline>sh` as `push`, as bash reads them.
        self.switch("agent/x")
        self.assert_all(("git push origin ma\\\nin",
                         "git pu\\\nsh origin main"), "deny")

    def test_backslash_newline_joins_to_nothing_on_main(self):
        # PS-0.5 / review N16: `gi\<newline>t` is read as `git`.
        self.assert_all(("gi\\\nt commit -m x",), "deny")

    # --- harness-followups rework 3: security M5 (docs/evidence/
    # harness-followups/security.md § M5). Orchestrator ruling: the hook
    # judges the command under two normalisations and denies if either
    # matches: (a) backslash-newline joined to nothing (PS-0.5, kept by the
    # two tests above) and (b) backslash-newline kept as a newline. Bash does
    # not join lines when the backslash ends a comment or is the second of an
    # even run, so the next line is a separate command there. ---

    def test_backslash_newline_after_comment_or_even_run_denies_on_main(self):
        # Security M5 rows 1-6 (main) and live shapes c1-c3.
        self.assert_all((
            "#x\\\ngit commit -m x",                    # c1: comment ends in a backslash
            "# copy to C:\\out\\\ngit commit -m x",     # c3: comment ends in a Windows path
            "ls #a\\\ngit commit -m x",                 # comment after a command
            "#x\\\ngit push",                           # comment, then a push on main
            "echo a\\\\\ngit commit -m x",              # c2: even run (two) then newline
            "echo a\\\\\\\\\ngit commit -m x",          # even run (four) then newline
        ), "deny")

    def test_backslash_newline_after_comment_or_even_run_denies_off_main(self):
        # Security M5 rows 7-9 (off main) and live shape p1.
        self.switch("agent/x")
        self.assert_all((
            "#x\\\ngit push origin main",               # comment, then push to main
            "#x\\\ngit push -f",                        # comment, then force push
            "echo a\\\\\ngit push origin main",         # even run, then push to main
            "#x\\\ngit push origin HEAD:main",          # p1
        ), "deny")

    # --- harness-followups rework 4: security M6 (docs/evidence/
    # harness-followups/security-rework3.md § M6, Table M), review N14,
    # security L21. Orchestrator ruling: in text (b) backslash-newline
    # becomes a space, not a newline, and text (b) is built only when the
    # command contains a backslash-newline. A non-continuation
    # backslash-newline (end of a comment, or an even backslash run) followed
    # by a real continuation inside the push line must still deny off main,
    # as the base hook a11842d did. ---

    def test_comment_or_even_run_then_continued_push_denies_off_main(self):
        # Security M6, Table M rows 1-11 (agent/x) and live shapes q1, q2:
        # rework 3 was silent on rows 1-10, q1 and q2; the base denied all.
        self.switch("agent/x")
        self.assert_all((
            "#x\\\ngit push \\\norigin main",                # M row 1
            "#x\\\ngit push origin \\\nmain",                # M row 2
            "#x\\\ngit push \\\n  origin main",              # M row 3
            "#x\\\ngit push \\\n-f origin x",                # M row 4
            "#x\\\ngit push \\\n--force",                    # M row 5
            "#x\\\ngit push \\\n--all",                      # M row 6
            "#x\\\ngit push origin \\\nHEAD:main",           # M row 7
            "# push from C:\\repo\\\ngit push \\\n  origin main",  # M row 8
            "echo a\\\\\ngit push \\\norigin main",          # M row 9: even run
            "#x\\\ngit \\\npush origin main",                # M row 10
            "git push \\\norigin main #x\\\nls",             # M row 11 (already DENY)
            "#x\\\ngit push \\\norigin HEAD:main",           # q1 (live: moved remote main)
            "# push from C:\\repo\\\ngit push \\\n  origin HEAD:main",  # q2 (live)
        ), "deny")

    def test_comment_then_continued_commit_denies_on_main(self):
        # Security M6, Table M rows 13 and 16 (main): DENY on base and rework
        # 3, pinned so the space reading keeps them. Rows 14 and 15 (a
        # continuation splitting the word git or commit after such a comment)
        # are silent on base, rework 3 and the space variant: an accepted
        # bypass (info), deliberately not asserted either way.
        self.assert_all((
            "#x\\\ngit \\\ncommit -m x",                     # M row 13
            "# C:\\a\\\ngit \\\n  commit -m x",              # M row 16
        ), "deny")

    def test_real_continuation_of_plan_item_push_stays_silent(self):
        # Security M6, Table M row 12, and review N14: a real continuation in
        # a push of the plan-item branch is silent, with or without a comment
        # line before it.
        self.switch("agent/x")
        self.assert_all((
            "git push \\\norigin agent/x",                   # M row 12
            "git push -u \\\n  origin agent/x",
            "#x\\\ngit push \\\norigin agent/x",
            "#x\\\nls",
        ), None)

    def test_multiline_without_backslash_newline_unchanged(self):
        # Review N14: with no backslash-newline the second text must add no
        # decision. Ordinary multi-line commands stay silent on both branches.
        benign = ("git status\nls",
                  "git log --oneline -3\ngit diff --stat",
                  "ls -la\necho done",
                  "#c\ngit status")
        self.assert_all(benign + ("echo a\\\nb", "#x\\\nls", "git status \\\n--short"), None)
        self.switch("agent/x")
        self.assert_all(benign + ("ls\ngit push origin agent/x",
                                  "git status\ngit push -u origin agent/x"), None)

    # --- platform-stack-up CI fix (2026-10-19), orchestrator ruling,
    # criterion 10 contradiction owned by tester. The 5 MB test below failed
    # on GitHub's 2-core runner in no-jq mode (3.9-6.4 s against 3 s;
    # docs/evidence/platform-stack/ci-run.txt) while it passed locally and in
    # earlier CI runs: timing variance on shared runners made a wall-clock
    # bound a flaky proxy for security L21, which is structural. L21 (text (b)
    # is built and judged ONLY when the command contains a backslash-newline)
    # is now checked directly from the hook's xtrace on small inputs; the
    # 5 MB run keeps only a loose sanity bound well under the 10 s hook
    # timeout. The binding timing spec, requirement 4f (1 MB under 3 s in
    # both modes), is unchanged in test_one_megabyte_token_shapes_finish_quickly
    # and test_one_megabyte_command_finishes_quickly. ---

    # Under `bash -x` each built text is one call of norm's
    # `tr '[:upper:]' '[:lower:]'`, and each judged text is one iteration of
    # the `for text in` loop. Anchored so command text in the trace can't match.
    TRACE_BUILT = re.compile(r"^\++ tr '\[:upper:\]' '\[:lower:\]'$", re.M)
    TRACE_JUDGED = re.compile(r"^\++ for text in ", re.M)

    def trace_passes(self, command: str, mode: str) -> tuple[int, int, str]:
        """Run the hook under bash -x; return (texts built, texts judged, stdout)."""
        # review-ci-fix N2 (platform-stack-ready, PS-2.24): the trace prefix is
        # pinned, so a caller's PS4 (or a BASH_ENV/ENV file that sets one)
        # cannot change the `+` the anchored regexes count.
        env = self.env(mode)
        env["PS4"] = "+ "
        for name in ("BASH_ENV", "ENV"):
            env.pop(name, None)
        result = subprocess.run(["bash", "-x", str(HOOK)],
                                input=claude_code_payload(command, self.repo),
                                cwd=self.repo, env=env,
                                capture_output=True, text=True, check=True)
        return (len(self.TRACE_BUILT.findall(result.stderr)),
                len(self.TRACE_JUDGED.findall(result.stderr)),
                result.stdout.strip())

    def test_second_text_built_and_judged_only_with_backslash_newline(self):
        # Security L21, checked structurally, no timing: without a
        # backslash-newline exactly one text is built and judged; with one,
        # text (b) is built and judged as well (M6 needs it). Fixtures are
        # silent off main, so the judge loop is never cut short by a match.
        self.switch("agent/x")
        without = {
            "one line": "echo hello",
            "multi line": "git status\nls -la\necho done",
            "heredoc": "cat <<'EOF'\nabcdefghi\nabcdefghi\nEOF",
            "windows paths": "echo C:\\a\\b C:\\c\\d",
            "backslash, space, newline": "echo a\\ \nb",
        }
        with_backslash_newline = {
            "continuation": "echo a\\\nb",
            "comment continuation": "#x\\\nls",
            "plan-item push": "git push \\\norigin agent/x",
        }
        for mode in MODES:
            for name, command in without.items():
                with self.subTest(mode=mode, shape=name):
                    self.require_mode(mode)
                    self.assertNotIn("\\\n", command)
                    built, judged, out = self.trace_passes(command, mode)
                    self.assertEqual(out, "")
                    self.assertEqual((built, judged), (1, 1))
            for name, command in with_backslash_newline.items():
                with self.subTest(mode=mode, shape=name):
                    self.require_mode(mode)
                    self.assertIn("\\\n", command)
                    built, judged, out = self.trace_passes(command, mode)
                    self.assertEqual(out, "")
                    self.assertEqual((built, judged), (2, 2))

    def test_trace_count_independent_of_caller_ps4(self):  # PS-2.24, review-ci-fix N2
        # A caller's PS4 changes the xtrace prefix. Bash ignores PS4 from the
        # environment when it runs as root (as in the gates image), so the
        # BASH_ENV case sets it from a startup file, which bash reads as root
        # too. Either way the structural counts must not change.
        self.switch("agent/x")
        rc = Path(self.repo) / "ps4.rc"
        rc.write_text("PS4='>>> '\n", encoding="utf-8")
        callers = {"PS4 in the environment": {"PS4": ">>> "},
                   "PS4 from BASH_ENV": {"BASH_ENV": str(rc)}}
        for mode in MODES:
            for caller, extra in callers.items():
                for command, expected in (("echo hello", (1, 1)), ("echo a\\\nb", (2, 2))):
                    with self.subTest(mode=mode, caller=caller, command=command):
                        self.require_mode(mode)
                        with mock.patch.dict(os.environ, extra):
                            built, judged, out = self.trace_passes(command, mode)
                        self.assertEqual(out, "")
                        self.assertEqual((built, judged), expected)

    def test_five_megabyte_command_without_backslash_newline_is_one_pass(self):
        # Security L21 sanity bound only (see the ruling note above): a 5 MB
        # command without a backslash-newline stays silent and finishes well
        # inside the 10 s hook timeout (< 9 s, loose on purpose: shared-runner
        # timing variance). The one-pass property itself is asserted by
        # test_second_text_built_and_judged_only_with_backslash_newline.
        mb5 = 5_000_000
        cases = {
            "heredoc lines": "cat <<'EOF'\n" + "abcdefghi\n" * (mb5 // 10) + "EOF",
            "one token": "echo " + "a" * mb5,
            "windows paths": "echo " + "C:\\a\\b " * (mb5 // 7 + 1),
        }
        self.switch("agent/x")
        for mode in MODES:
            for name, command in cases.items():
                with self.subTest(mode=mode, shape=name):
                    self.require_mode(mode)
                    self.assertGreaterEqual(len(command), mb5)
                    self.assertNotIn("\\\n", command)
                    start = time.monotonic()
                    out = self.run_hook(command, mode)
                    elapsed = time.monotonic() - start
                    self.assertEqual(out, "")
                    self.assertLess(elapsed, 9.0)

    def test_json_without_command_field_is_silent(self):
        # PS-0.5 / review N17: no command field means nothing to judge, even
        # on main with git commit text elsewhere in the payload.
        payload = json.dumps({
            "session_id": "00000000-0000-0000-0000-000000000000",
            "cwd": self.repo,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"description": "git commit -m x"},
        }, separators=(",", ":"))
        for mode in MODES:
            with self.subTest(mode=mode):
                self.require_mode(mode)
                self.assertEqual(self.run_raw(payload, mode), "")

    def test_only_first_command_value_is_judged(self):
        # PS-0.5 / review N17: tool_input.command comes first; a later
        # "command" key elsewhere in the payload is not judged.
        def payload(first: str, later: str) -> str:
            return json.dumps({
                "session_id": "00000000-0000-0000-0000-000000000000",
                "cwd": self.repo,
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": first, "description": "Run command"},
                "extra": {"command": later},
            }, separators=(",", ":"))
        for mode in MODES:
            with self.subTest(mode=mode):
                self.require_mode(mode)
                self.assertIn('"deny"', self.run_raw(payload("git commit -m x", "ls"), mode))
                self.assertEqual(self.run_raw(payload("ls", "git commit -m x"), mode), "")

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


class HookHeaderTest(unittest.TestCase):
    """Human ruling Q18, 2026-10-20 (docs/open-questions.md A18, handoff
    ci-speed): branch protection was SKIPPED. The hook's header must not call
    branch protection the real control; it says Q18 was skipped and that this
    hook is the only automated guard."""

    def header(self) -> str:
        lines = HOOK.read_text(encoding="utf-8").splitlines()[1:]  # after the shebang
        comment = []
        for line in lines:
            if not line.startswith("#"):
                break
            comment.append(line.lstrip("#").strip())
        return " ".join(comment)

    def test_header_says_q18_skipped_and_hook_is_only_automated_guard(self):
        header = self.header()
        self.assertNotRegex(header, r"(?i)real control", header)
        self.assertRegex(header, r"\bQ18\b", header)
        self.assertRegex(header, r"(?i)\bskipped\b", header)
        self.assertRegex(header, r"(?i)\bonly automated guard\b", header)


if __name__ == "__main__":
    unittest.main()
