# 2026-10-18 - reviewer: harness-claude-code, re-review after rework 1 (of 5)

Verdict: **CHANGES REQUESTED**

Scope: `git diff 886de45` plus untracked files (.claude/, docker/, .dockerignore,
CLAUDE.md, tests/test_harness_port.py, tests/test_block_main_commit_hook.py).
Excluded: docs/knowledge-engine-claude-code-prompt.md, .venv/. Prior findings:
`review.md`. Hook probe output: `hook-probe-rework1.txt` (scratch repo, host Git Bash).

## Prior findings

| ID | Status | Notes |
|---|---|---|
| B1 | resolved | AGENTS.md:15, :40, :53 name only `scripts/verify.sh`; `test_no_stray_verification_commands` scans AGENTS.md. Rules keep their meaning (see below) |
| B2 | resolved | `test_non_producer_body_identical_to_copilot` (whole body, CRLF-normalised) + `test_producer_sections_identical_except_verification_steps`; mutation-approach.txt shows it bites |
| B3 | resolved | Req 9 amended (uv.lock via `--locked`, generic drift gate moved to policy-book req 2); `test_gate_scripts_use_locked` covers scripts/*.sh and gates.Dockerfile. `uv run --locked` fails on a stale lock, so verify goes red |
| B4 | open, correctly not claimed | handoff line 4 "Done only with the proof in requirements item 13"; neither rework section claims it; green runs still print `886de45+dirty`. Post-commit clean-clone run still required |
| N1 | resolved | jq in gates image, jq test runs (0 skipped). But see B5: the no-jq path on JSON is now untested |
| N2 | addressed | `core.autocrlf true` in the image. Repo has 0 CRLF blobs (`git ls-files --eol`), so this is harmless on Linux CI |
| N4 | partly | `.dockerignore` added; `--build` registry lookup offline still untested (deployable-offline item) |

## Blocking

**B5. Regression: on this host the hook fails open for the most common
command shape.** Claude Code sends compact JSON (`"command":"git commit ..."`)
and there is no jq on the Windows host, so the raw fallback runs. It deletes
quotes, leaving `command:git commit -m x`. The segment test
`(^|[[:space:]])git[[:space:]]` then misses `git`, which is preceded by `:`. So any
Bash call whose *first* token is `git` passes silently, even on main: commit,
push, `push --force origin main`, merge. Probe evidence:
- `hook-probe-rework1.txt` "on main, compact JSON, no jq": all silent.
- The base hook (886de45) denies the same payload.
- Confirmed live in this session: `git -C <scratch> push -f --dry-run nosuchremote HEAD`
  ran unhindered (the remote did not exist). The same command prefixed with
  `echo probe &&` was denied ("Force pushes are not allowed.").
Why the tests stayed green:
- `run_hook` builds the payload with `json.dumps` default separators (`": "`),
  so there is always a space before `git`.
- The gates image now has jq, so no JSON test goes through the fallback anyway.
Fix:
- In the fallback, extract the `command` string from the JSON (sed on the
  command key, honouring escaped quotes) instead of scanning the whole payload.
  At minimum, turn quotes/braces/colons into spaces rather than deleting them.
- Tests (RED first): run the hook with a PATH that has no jq, feed compact
  JSON (json.dumps with separators `,` and `:`), and assert deny on main for
  `git commit -m x`, `git push origin main` and `git merge x`. Also send every
  existing case in compact form, since that is the shape Claude Code uses.

**B6. False positives on plan-item branches: the orchestrator concern is
real.** A segment counts as a push if the word `push` appears anywhere in it, and
quotes are stripped first. Denied on `agent/x` (see `hook-probe-rework1.txt`):
- `git commit -m "fix push to main docs"`: "Pushing to main/master is not allowed."
- `git commit -m "docs: note push -f is denied"`: "Force pushes are not allowed."
- `echo "git push origin main is blocked"`: denied, though it is not a git call.
- A heredoc commit message (the standard Claude Code commit form) with a body
  line such as "The hook now denies git push to main from any branch".
- Three commands from this review were denied by the live hook: the scratch
  probe script, and two attempts at the shell command that wrote this file. On
  the live path the JSON escapes the newlines, so a whole heredoc is one segment.
Why it blocks, although it fails safe:
- Gate 6 commits on the correct branch get denied whenever the message
  describes this very feature. The likely commit message for this plan item
  is one such message.
- A guard rail that routinely blocks legitimate work gets bypassed.
- It shares a root cause and a fix with B5.
Fix: judge the git *subcommand*, not any word in the segment.
- Find `git` at command position.
- Skip global options (`-C <path>`, `-c <k=v>`, `--git-dir=..`, `--work-tree=..`,
  `--no-pager`).
- Only when the next token is `push`, inspect its arguments for main/master
  refspecs and force flags.
- Do not treat text inside quoted strings or heredocs as arguments. Or accept
  that such text can only false-deny on main.
- The on-main check can keep its broad match, because fail-safe on main is fine.
Pin it in the suite (compact JSON):
- On an agent branch, the three commit-message cases and the `echo` case
  above stay silent.
- `git -C . push origin main` and `git push origin HEAD:main` still deny.

**B7. Requirement 4 now contradicts the hook.** docs/requirements.md item 4
says "on `main`/`master` ... denies it; otherwise it prints nothing". The hook and
the new tests deny push-to-main and force-push from any branch (security M1).
Criterion 10 makes the tester own contradiction resolution in the same commit,
citing the decision. The analyst should amend item 4:
- add the any-branch denials and the on-main merge/cherry-pick/am/rebase/revert list;
- record that the hook is a guard rail, not a boundary;
- name the security finding as the decision record.

## Nits

- **N7.** Bypasses still open: `git push --mirror origin` and `--all` (both can
  update main), and combined short flags (`-fu`). It is a guard rail, but the B6
  rewrite should handle `--mirror`/`--all`, and `-f` inside a short-flag cluster.
  Defer to security on severity.
- **N8.** The on-main match is still word-anywhere, so read-only commands on main
  such as `git log --grep revert` are denied. Fail-safe; acceptable.
- **N9.** `VERIFICATION_STEP = (?i)test|smoke|verif|gate` is broad: almost any
  producer Approach step mentions "test", so the step-level guard only really
  checks "the new text contains scripts/verify.sh". Acceptable with the
  section-level and non-producer equality tests; consider listing the
  permitted step numbers per role.
- N3, N5, N6 from review.md remain open as recorded; nothing new.

## Q3: Dockerfile, .dockerignore, ci.yml, AGENTS.md

- **gates.Dockerfile**:
  - Both FROM lines are digest-pinned; jq is installed.
  - `safe.directory /work` fixes git ownership on the bind mount.
  - `ENV UV_OFFLINE=1` comes after `uv sync --locked`. That is the right place:
    the build step can still fetch, and runtime cannot.
  - `green-rework1-later.txt` (11 min after the build) passes, and
    `offline-after.txt` reproduces the failure mode.
- **.dockerignore**: excludes .git, .venv, __pycache__, docs/evidence, .env*,
  .claude. The build only COPYs pyproject.toml, uv.lock and harness_telemetry,
  and .git arrives at run time through the bind mount, so nothing is lost.
  Excluding `.env*` from the build context is also a security plus.
- **ci.yml**: one `run:` step (`./scripts/verify.sh full`), checkout pinned to a
  full SHA with a version comment, timeout 20 min. OK.
- **AGENTS.md**: meaning is kept.
  - The tester still owns unit and smoke tests.
  - Gate 4 still makes the smoke test merge-blocking: `verify.sh full` runs
    smoke.sh.
  - File Conventions now list `verify.sh` as the single entry point.
  - The line `ci.yml ... calls the scripts above` is still true.
  - No rule was dropped. The Copilot agents still name test.sh (N6), which
    `.github/agents/` being frozen accepts.

## Q4: were tests weakened?

No.
- Every change matches the rework-1 section from the tester: an AGENTS.md scan
  was added, along with two port-equality tests, `test_gate_scripts_use_locked`,
  three hook tests (M1), the jq test and `GatesImageJqTest`.
- The pre-existing hook tests (commit/push/chained/`-C`/master/plan-item/
  non-git/raw) are all still present and unchanged in intent.
- No skip was added apart from the jq one, which now runs (41 tests, 0 skipped
  in `green-rework1.txt`).
- The developer section says no tests were edited, and the file content agrees.
- The gap is coverage, not weakening: the compact-JSON fallback (B5) and the
  false positives (B6) are not pinned.

## Observability
No product agent loop, model call, retrieval or tool call was added; no span
requirements.

## Next role needs to know
- tester: RED for B5 (no-jq PATH + compact JSON on main) and B6 (the
  commit-message, heredoc and echo cases stay silent on agent branches).
- developer: rewrite the fallback extraction and subcommand detection, then run
  `scripts/verify.sh full`.
- analyst: B7, amend requirement 4.
- orchestrator: B4 is still post-commit; this is rework round 2 of 5.
