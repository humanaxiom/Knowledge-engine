# 2026-10-18 - reviewer: harness-claude-code, re-review after rework 4 (of 5)

Verdict: **APPROVED** (review gate). There are no blocking findings. The
remaining items below are nits. Item 13 (B4) and CI green still need the
commit and push.

Scope:
- Reviewed `git diff 886de45` plus the untracked files. Excluded
  docs/knowledge-engine-claude-code-prompt.md and .venv/.
- Since round 3 only these changed: `scripts/hooks/block-main-commit.sh`,
  `tests/test_block_main_commit_hook.py`, requirements item 4, the ADR-KE-001
  decision record, and the handoff/log/evidence files (by mtime).
- Judged against criterion 4a-4f as rewritten this round and against ADR-KE-001
  "Decision: commit hook is a simple fail-safe text rule (2026-10-18)".
- Severity rule for this round: a finding is blocking only if it violates the
  spec, AGENTS.md or CLAUDE.md, or makes a gate untrustworthy.
- Payloads were only piped into the hook. No commit or push was executed.

Evidence (all in docs/evidence/harness-claude-code/):
- `hook-probe-review-r4.txt` holds 102 probes x 4 runs: host natural no-jq,
  host fake jq, image jq and image fake jq. It also has the generator and
  driver.
- `hook-timing-review-r4.txt` holds 12 shapes of about 1 MB (several adversarial),
  on both branches and in both modes, in the image and on the host.
- `mutation-review-r4.txt` holds 14 mutants with their diffs. Each ran in the
  gates image on an isolated copy, so the live hook was never touched.

## Prior findings

| ID | Status | Notes |
|---|---|---|
| B4 | open, correctly not claimed | The item 13 clean-checkout verify runs and CI green come after the commit and push |
| B10 | **resolved** | The hook has no awk. Image worst case 0.46 s (1 MB of backslashes, no-jq); the three spec shapes 0.13-0.30 s; host worst 1.28 s. Tests cover all three 4f shapes plus a many-line heredoc, in both modes |
| B11 | **resolved** | `>/dev/null`, backtick, `!`, `command` and `exec` off main, and `sh -c` / bash heredoc on main, are each tested in both modes (`test_prefixed_push_to_main_denied_off_main`, `test_shell_wrapped_commit_denied_on_main`). Under the text rule these are no longer separate code paths, so no mutant can single them out; that is expected |
| N9 | open (nit) | Unchanged |
| N10 | open (nit) | `\u0067it commit` on main: jq decodes and denies; no-jq stays silent. It is the only mode disagreement in 408 decisions. Falls under "encodings" |
| N11, N12 | **moot** | No quote or heredoc state remains |
| N13 | partly moot | `main&>/dev/null` is now a word match. Still open, both spec-conformant: `--branches` (git 2.46 alias of `--all`) off main, and `pull` is not in the 4c verb list |
| N14 | **resolved** | `mutation-hook-r4.txt` now records the diff of each mutant |
| N15 | **resolved** | ADR "As built" points to the new decision record |

## 1. B10 and B11

Both are resolved (see the table). Timing in `knowledge-engine-gates:latest`
(mawk, jq 1.6), both modes, branch agent/x and main:

| Shape (about 1 MB) | Worst of 4 runs |
|---|---|
| unquoted token | 0.13 s |
| `-m "<1 MB>"` | 0.16 s |
| one heredoc line | 0.14 s |
| 100k `echo x &&` segments | 0.17 s |
| backslash-quote x 500k, backslash x 1M, backslash-newline x 250k | 0.36-0.46 s |
| `git push ` + `a/` x 500k, `-` x 1M, repeated pushes, 40k push lines | <= 0.31 s |

Full table: `hook-timing-review-r4.txt`. This is linear in practice, a long
way under the 3 s budget and the 10 s hook timeout.

## 2. The hook against 4a-4f

The four runs (host x2, image x2) agree on every probe except N10.

- **4a, extraction.** Checked:
  - jq path, sed fallback and raw input.
  - A JSON payload with no `command` field is silent (e00).
  - A forged escaped command key inside the description is silent (e02), and
    so is a description placed before command (e03).
  - Spaced JSON (a space after the colon) is extracted (e04).
- **4b, normalisation.** The tested cases work: a continuation between words,
  quotes, `ma\in`, `gi\t`, `g''it` and `GIT`. See N16 for a continuation
  inside a word.
- **4c, on main and master.** All 7 verbs are denied, and so are nested,
  wrapped, `G=git; $G commit`, `eval` and `xargs` forms. These stay silent:
  `status`, `log`, `diff`, `checkout -b`, `switch -c`, `fetch` and `ls`. One
  accepted false positive is denied: `log --grep revert`, plus a plan-branch
  push typed while on main.
- **4d, off main.** Every listed target and flag is denied in every prefix
  form: `-C`, `-c`, `/usr/bin/git`, `git.exe`, tab, `cd x &&`, `>/dev/null`,
  backtick, `!`, `command`, `exec`, subshell, brace group, `bash -c`, and a
  quoted command substitution.
  - These stay silent: everyday pushes (`-u`, `HEAD:agent/x`,
    `--follow-tags`, `-o ci.skip`, `agent/main-fix`), `fetch`/`rebase`/`merge`
    naming main, `log`/`diff` main, a Claude Code heredoc commit whose body
    has no git line, and a `log_event` action mentioning push to main.
  - The accepted false positives are denied: a one-line message, `echo`, and
    a heredoc body line naming git, push and main.
  - The accepted bypasses are silent: a variable target, and a push split
    across lines.
- **4e.** No probe printed `allow` and none exited non-zero.
- **4f.** Met, see section 1.

## 3. Was the test rewrite legitimate (requirement 10)?

Yes. I diffed it against my round-3 base copy of the test file
(`mut/base` in the reviewer scratchpad).

The only removed or changed assertions are these:
- Four B6 "silent" cases now expect a deny:
  - two one-line `-m` messages
  - the `echo` string
  - the `-F -` heredoc whose body line says git, push and main
- They moved, unchanged, into
  `test_one_line_mentions_are_accepted_false_positives_off_main`, which cites
  the ADR. They are exactly the class that the ADR Consequences and 4e name.
- The B6 silent test keeps a heredoc whose body has no git, plus the
  `agent/x` push and `log main`.
- The Claude Code heredoc test body changed from a line with git, push and
  main to one without git. The ADR requires this, because the old body is now
  an accepted false positive. It still checks the shape that matters, the
  backticks and the cat-heredoc command-substitution form.
- The round-3 comment block is reworded to match the ADR.

Nothing else was deleted:
- Every round-1 to round-3 test is still present.
- The suite went from 54 to 62 tests.
- `green-rework4.txt` shows `scripts/verify.sh full` PASS, 62 tests OK,
  0 skipped. My base mutant run in the image also gave OK.

No threshold was loosened. The 3 s and 5 s budgets are unchanged, and the 1 MB
shapes were added.

## 4. Are the mutation diffs in `mutation-hook-r4.txt` real?

Yes.
- The live hook sha256 is `746f090b...088f`, which matches the file.
- I rebuilt a-d from the recorded diffs on isolated copies. The failure counts
  match exactly: 4, 5, 56 and 66.

I also ran ten extra mutants:

| Mutant | Result |
|---|---|
| e: no continuation join | killed (4) |
| f: no `-f` cluster | killed (8) |
| g: no `+` refspec | killed (2) |
| h: no `--force` | killed (6) |
| i: jq filter broken | killed (74) |
| k: no JSON `\n` to newline | killed (6) |
| m: `am` dropped | killed (2) |
| n: `--mirror`/`--all` dropped | killed (4) |
| j: `head -n 1` changed to `tail -n 1` | **survives** (N17) |
| l: the empty-text early exit replaced by `:` | **survives**, but it is an equivalent mutant |

## 5. Are the docs consistent?

- requirements 4a-4f, the ADR decision record, the "As built" bullet, the hook
  header comment, the test module docstring and the tester and developer
  handoff sections all describe the same rule.
- AGENTS.md and CLAUDE.md do not contradict it.
- The handoff is 136 lines, under the 200 cap.
- Two wording nits: N18 and N19.

## 6. Requirements 1-14

- **1-3, 5-12 and 14 are met.**
  - Only the hook, its tests and the docs changed since round 3.
  - `test_harness_port.py`, `.claude/agents/`, CLAUDE.md, `scripts/` and
    `docker/` all have round-3-or-earlier mtimes.
  - `.github/agents/` is unchanged against 886de45.
  - All eight `dispatch-<role>.md` files are present.
  - `green-rework4.txt` shows 62 tests OK with 0 skipped, and smoke passes.
- **4 is met.** 4a-4f hold, and the unit line's named cases are all present in
  both modes. N17 is a minor test gap.
- **13:** the dispatch proof is met. The clean-checkout runs of every verify
  mode (B4) and CI green are due after the commit and push.

## Blocking

None.

## Nits (record; not merge-blocking)

- **N16. A continuation is joined with a space, not removed.**
  - Hook line 34 replaces backslash-newline with a space. Bash deletes it, so
    these are silent while bash would run the real words:
    - `git push origin ma\<newline>in` off main
    - `gi\<newline>t commit -m x` on main
  - Every run reproduces it (probes 039 and 076).
  - "Joined" in 4b does not say which. Between words, as in the tested case,
    both readings deny. Inside a word it is a deliberate obfuscation, which the
    "words hidden" bypass covers, so it is not blocking.
  - Fix: replace with an empty string. The space before the backslash in
    normal use keeps the words apart.
  - If round 5 happens, fold this in with a test.
- **N17. Two 4a clauses have no test.**
  - "A JSON payload with no `command` field prints nothing." No test sends
    such a payload. The probe shows it is silent in every mode, and every
    plausible regression would deny rather than allow.
  - "The first `command` value." Mutant j survives.
  - Neither can fail open, so the gate stays trustworthy. Add a test for each
    if round 5 happens.
- **N18. The ADR Decision says "a single sed".** The code uses
  `grep -o | head -n 1 | sed`. Requirements 4a, which only says "the first
  value", is accurate.
- **N19. AGENTS.md says the hook is "wired in `developer.agent.md`".** In
  Claude Code it is wired in `.claude/settings.json` for every session. This
  line is unchanged from the template, so it is not a contradiction, just
  incomplete.
- **N20. The `-f` cluster clause matches any later `-...f` token on the same
  line.**
  - Example: `git push origin agent/x && rm -rf build` is denied.
  - It conforms to 4d and fails safe. Worth a line among the accepted false
    positives in the ADR.
- N9, N10 and N13 remain open, as described in the table.

## Observability

No product agent loop, model call, retrieval or tool call was added, so no span
requirements apply.

## Next role needs to know

- **orchestrator:** the review gate passes.
  - N16 and N17 are cheap. Fold them in only if the round-4 security verdict
    forces a round 5 anyway.
  - Before the commit, run `scripts/verify.sh full` yourself.
  - After the commit, the clean-checkout runs for item 13 are still due.
- **Live hook:** while on this branch it denies any command text with a line
  that says git, push and main. Write probes and log actions with that in mind.
