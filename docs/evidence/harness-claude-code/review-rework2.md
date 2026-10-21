# 2026-10-18 - reviewer: harness-claude-code, re-review after rework 2 (of 5)

Verdict: **CHANGES REQUESTED**

Scope:
- Reviewed `git diff 886de45` plus the untracked files. Excluded
  docs/knowledge-engine-claude-code-prompt.md and .venv/.
- The focus was `scripts/hooks/block-main-commit.sh`,
  `tests/test_block_main_commit_hook.py` and requirements item 4 (a-e).
- Probe output is in `hook-probe-rework2.txt`:
  - Section A: host Git Bash with no jq, compact payloads.
  - Section D: the same payloads in `knowledge-engine-gates:latest` with jq.
  - Section E: the base hook compared with the new hook on main.
- No real git commit or push was run. Payloads were only piped into the hook.

## Prior findings

| ID | Status | Notes |
|---|---|---|
| B4 | open, correctly not claimed | Proof run on a clean checkout is still due after the commit |
| B5 | **resolved** | With no jq on the host, compact JSON on main: `git commit -m x`, `git push origin main` and `git merge x` are denied (probe A). Tests run every case in `jq` and `no-jq` modes (fake jq exits 127) with `claude_code_payload` (compact, full envelope) |
| B6 | **resolved** for the cases named | Silent on agent/x: the two `-m` messages, the `echo` string, the `-F - <<'EOF'` heredoc, the real Claude Code form `-m "$(cat <<'EOF' ...)"` (probe cc_heredoc), and escaped quotes inside the message (probe C). The live hook in this session also let through several of my probe commands that had `git push origin main` inside heredocs |
| B7 | **resolved** | Item 4 a-e now matches the hook: any-branch push rules, the on-main list, guard rail rather than boundary, Q18, and the decision record |
| N7 | resolved | `--all`, `--mirror`, `-fu` and `--force-with-lease` are denied |
| N8 | superseded | Orchestrator ruling: 4a applies on main too. `git log --grep revert` on main is silent |
| N9 | open (nit) | Unchanged |

## Correctness of the new hook against item 4

- **JSON extraction (no-jq awk).** It matches the first `"command"\s*:\s*"`.
  - An injected key inside another string value cannot match: JSON escapes
    every quote inside a string, so `command\"` never equals `command"`.
  - Verified with the description `note "command":"git push origin main"`,
    placed both before and after `command`: silent (probe C, desc_first and
    desc_cmd_inject).
  - `\uXXXX` is not decoded (N10).
- **Quote handling.** Single quotes, double quotes with backslash escapes, and
  backslashes outside quotes all work. probe esc_q_then_push
  (`git commit -m "x \"y\"" && git push origin main`) is denied on agent/x, so
  an escaped quote does not swallow the next segment.
- **Heredocs.** Unquoted `<<`, `<<-` and quoted delimiters are skipped to the
  terminator line. A `<<` inside double quotes is not seen, which is harmless
  for the standard form (but see N11).
- **Global options.** `-C`, `-c`, `--git-dir`, `--work-tree` and `--namespace`
  take one argument. `--x=y` and other dash options are skipped.
  - `git -c x=y push origin main` is denied on agent/x and on main.
  - `git -c x=y push -f origin agent/x` is denied (force).
  - `--no-pager` and `--git-dir .git` were also verified.
- **Push rules (4b).** Probes A and D confirm `origin main`, `HEAD:main`,
  `refs/heads/main`, `HEAD:refs/heads/master`, `:main`, `--delete main`,
  `--force`, `--force-with-lease[=..]`, `-fu`, `+refspec`, `--all` and
  `--mirror`. A plain `-u origin agent/x` is silent.
- **Fixed reasons.** The reasons are three constant strings with no quotes or
  percent signs, so the JSON output is always valid. The hook never prints
  allow (4d).
- **cd elsewhere && git commit**: silent on agent/x and denied on main, judged
  by the cwd branch. Accepted per N5.
- **jq and no-jq agree** on every Claude Code-shaped probe. They differ only on
  hand-crafted `\uXXXX` escapes (N10).

## Blocking

**B8. Git at a nested command position is not judged. Regression on main
compared with the base hook.**
- The judge only treats token 1 of a segment (after `VAR=` prefixes) as the
  command position, and only `&& || ; |` and newlines split segments.
- Silent on **main** (probe E) for all of the following, though the base hook
  (886de45) denied every one:
  - `(git push origin main)`
  - `echo $(git push origin main)`
  - `out=$(git push origin main 2>&1)`
  - `echo "$(git push origin main)"`
  - echo with backticks around `git push origin main`
  - `{ git push origin main; }`
  - `if git push origin main; then ...; fi`
  - `! git push origin main`
  - `sleep 1 & git push origin main`
- The same holds for `git commit` in these shapes, which is the hook's main job.
- Why this blocks:
  - Item 4a requires judging "git at command position". In bash every one of
    these is a command position.
  - None of them is on the accepted-bypass list (aliases, eval, indirection,
    gh, update-ref, checkout main && commit).
  - Agents do write `out=$(git push ... 2>&1)`, `if ! git ...; then` and
    `(cd x && git ...)`.
- Fix:
  - Outside quotes, treat `(`, `)`, `$(`, backtick and a lone `&` as segment
    boundaries.
  - Skip the leading words `! { } if then elif else do while until time`
    before looking for `git`.
  - For a command substitution inside double quotes, lex its body as a nested
    command. This also fixes N11, because the Claude Code heredoc commit form
    would then be parsed properly.
  - If that is too much, the orchestrator may rule quoted substitution an
    accepted bypass. The unquoted shapes should still be fixed.
- RED first: on main and on agent/x, deny each shape above in both modes.

**B9. The tests do not cover the cases item 4 names for them.** Item 4's unit
line says the file "covers each denial in b and c ... `git -C` and `git -c`
global options ... master". Missing:
- `git -c k=v push origin main`. No test touches the `-c` skip. Removing `-c`
  from hook line 76 makes `x=y` the subcommand, so the hook goes silent and
  the suite stays green.
- `refs/heads/main`, `:main`, `--force-with-lease`, plain `-f`, and a push
  that targets `master` from a plan-item branch. Removing the `refs/heads/`
  strip (line 66) or the `--force-with-lease` branch (line 87) also leaves
  the suite green.
- `git push` on master. The only master case is `commit`.
Also pin, because these were the B6 and H1 motivations:
- The real Claude Code heredoc commit form (`git commit -m "$(cat <<'EOF'`
  ... body mentioning git push to main ... `EOF` then `)"`), silent on
  agent/x. The test uses `-F - <<'EOF'`, which is a different lexer path.
- A description that contains `"command":"git push origin main"` with `ls`
  as the command, silent. Today's description is only `prepare git commit`.
- An escaped quote inside the message followed by a real push, denied on
  agent/x.

## Nits

- **N10.** The no-jq extractor does not decode `\uXXXX`.
  - `git push origin main` and `git push -f ...` fail open without
    jq and are denied with jq.
  - `-m "a; git push -f"` is falsely denied without jq (probes B
    and D).
  - Claude Code's JSON.stringify never escapes printable ASCII this way, so
    this is not reachable from real payloads.
  - Fix: decode the ASCII range, or document the gap.
- **N11.** If the body of a Claude Code-form heredoc commit message has an odd
  number of double quotes (e.g. `a 12" ruler`), the quote state flips. Later
  body lines are then lexed as commands, so a line starting with
  `git push --force` is falsely denied on agent/x (cc_heredoc_oddquote). This
  fails safe and goes away with the B8 nested-substitution fix.
- **N12.** Arithmetic `$((1<<2))` is taken as a heredoc with delimiter `2))`.
  Every later line is then skipped, so a `git push origin main` on the next
  line is silent (arith_heredoc). This is contrived.
- **N13.** Other small gaps, all fail-open on agent/x unless noted:
  - `git push origin main&>/dev/null`: the redirect is glued to the token.
  - `git push --branches origin`: git 2.46+ alias for `--all`.
  - `git pull` on main: not on the 4c list. Consider adding it.
  - `env git` / `command git` / `sudo git`: arguably indirection.
  - A git path written with Windows backslashes.
  - A pretty-printed payload with a newline after `"command":` is silent in
    no-jq mode. This is not Claude Code's shape.

## Were the tests weakened?

No.
- All the earlier cases are still there: commit and push on main, chained,
  `-C`, master, plan-item, non-git, raw stdin, and push-to-main/force from a
  branch.
- `test_jq_reads_only_the_command_field` was renamed to
  `test_judges_only_the_command_field` and now runs in both modes, so it is
  stronger.
- `git status` was added to the silent set, which agrees with 4a.
- The only skip is jq mode when jq is absent. In the gates image it runs
  (`green-rework2.txt`: 45 tests, OK).
- L8 (400 segments in under 5 s) was added.
- The gap is coverage (B9), not weakening.

## Observability
No product agent loop, model call, retrieval or tool call was added. No span
requirements apply.

## Next role needs to know
- tester: RED for B8 (nested shapes, on main and on agent/x, both modes) and
  for every missing B9 case.
- developer: lexer and judge changes for B8, optional N10/N11/N13, then
  `scripts/verify.sh full`.
- orchestrator:
  - Rule on whether a quoted command substitution is in scope for B8.
  - This is rework round 2 of 5. B4 is still due after the commit.
