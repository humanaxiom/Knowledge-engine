# 2026-10-18 - reviewer: harness-claude-code, re-review after rework 3 (of 5)

Verdict: **CHANGES REQUESTED**. There are two blocking findings, both small.
B10 is a hook performance fix in two functions. B11 adds about five strings to
existing test tuples.

Scope:
- Reviewed `git diff 886de45` plus the untracked files. Excluded
  docs/knowledge-engine-claude-code-prompt.md and .venv/.
- Judged against criterion 4 as amended in round 3 (4a-4f). Accepted bypasses
  in 4d are not findings.
- No git commit or push was executed. Payloads were piped into the hook only.

Evidence (all in docs/evidence/harness-claude-code/):
- `hook-probe-review-r3.txt`: 138 probe decisions.
  - Section A: host Git Bash, no jq.
  - Section B: gates image with jq.
  - The decisions are identical in both sections.
- `mutation-review-r3.txt`: 10 mutants. The test suite was run against each
  one in the gates image.
- `hook-timing-review-r3.txt`: 1 MB timings. The gates image uses mawk.

## Prior findings

| ID | Status | Notes |
|---|---|---|
| B4 | open, correctly not claimed | The clean-checkout verify runs (item 13) are due after the commit |
| B8 | **resolved** | On main and master, every nested shape is denied. That includes a quoted command substitution, `sh -c`, a `bash` heredoc, `eval`, `xargs` and `$G commit`. On agent/x, every deny example in 4a is denied: subshell, brace group, `if`, `true &`, `>/dev/null git`, `2>&1 git`, `$( )`, backtick, `$((1<<2))` followed by a newline, `!`, `time`, `command`, `exec`, `while` and `out=$(..)`. Only the 4d bypasses stay silent off main |
| B9 | **resolved** | Every case named in round 2 is tested in both modes. Mutants a, b and c each fail exactly the intended test |
| N9 | open (nit) | Unchanged |
| N10 | open (nit) | Unchanged (`\uXXXX`) |
| N11 | open (nit), extended below | |
| N12 | resolved for `$((`; variant below | |
| N13 | open (nit) | `&>` glued to `main`, `--branches`, `git pull` on main |

## Probes (question 2)

- **The B6 silent set is still silent on agent/x.** The cases are:
  - both `-m` messages
  - the `echo` string
  - the `-F -` heredoc
  - `push origin agent/x`
  - `log --oneline main`
  - `status`
- **Realistic agent commands are silent on agent/x.** These were checked:
  - the Claude Code heredoc commit form (`git add -A && git commit -m` with a
    quoted cat-heredoc substitution), with a body that contains backticks,
    apostrophes, `"k":"v"`, `( ) { } & | ;` and `git push origin main`
  - `git log --oneline -5`
  - `git diff 886de45 --stat`
  - `git push -u origin agent/harness-claude-code`
  - `git push -u origin HEAD:agent/x`
  - `--follow-tags`
  - `-o ci.skip`
  - `git fetch origin main`, `git rebase origin/main`,
    `git merge --ff-only main`
  - a `log_event` call with `--action "push to main blocked; -f"`
  - a `# push to main` comment
- **On main** these are silent: `status`, `log`, `diff`, `checkout -b` and
  `ls`. Every command that contains `git` and one of the 4c verbs is denied,
  as 4c requires. The accepted false positives include
  `git push -u origin agent/x` run while on main.
- **jq and no-jq agree** on all 138 decisions.

## Mutations (question 3)

`mutation-hook-r3.txt` is real. I rebuilt all four mutants independently
(`mutation-review-r3.txt`).
- Each mutant is a one-line semantic change.
- a (`-c` skip), b (`refs/heads/` strip) and c (`--force-with-lease`) each
  fail 2 subtests, in the intended test.
- d (broad rule off) fails 50.
- The base copy passes with 0 skipped.
- The developer's b was first a no-op. Their re-run and my rebuild both show
  that the redone b is real.

## Blocking

**B10. 4f is not met. The lexer is quadratic in token length under mawk, and
the gates image uses mawk.**
- Measured in `knowledge-engine-gates:latest` (awk is `/usr/bin/mawk`), with
  and without jq:

  | 1 MB command | Time |
  |---|---|
  | `git commit -m "<1 MB>"` | 8.06 s |
  | the same with realistic message text | 8.03 s |
  | `echo '<1 MB>'` | 7.85 s |
  | `echo <1 MB>` | 8.29 s |
  | a 1 MB heredoc line | 7.81 s |

  The budget is 3 s, and the Claude Code timeout is 10 s.
- Scaling for `-m "<N x a>"`:

  | N | Time |
  |---|---|
  | 125k | 0.24 s |
  | 250k | 0.81 s |
  | 500k | 2.17 s |
  | 1M | 8.06 s |

  The time grows about 4x per doubling, so it is quadratic.
- Cause:
  - `add()` does `cur = cur ch` for every character (hook line 61).
  - `skip_heredocs` does `line = line ch` (line 124).
  - mawk copies the string on every append. gawk on the host appends in
    place, which is why the host shows 0.6-0.9 s.
- The L9 test only feeds 100,000 short tokens, so it is green while 4f fails.
- This matters because security L9 is about timeouts:
  - A timed-out hook is a non-blocking error, so the hook fails open.
  - Debian and Ubuntu hosts also ship mawk.
- Fix (developer):
  - Never build a token or line one character at a time.
  - For quoted strings and runs of plain characters, find the end by scanning
    indices, then take one `substr()`.
  - For heredoc lines, scan to the newline and take one `substr()`.
- RED first (tester), in both modes, under 3 s in the gates image:
  - a 1 MB single `-m "..."` token
  - a 1 MB unquoted token
  - a 1 MB heredoc body line
- Do not loosen 4f to fit the current code.

**B11. Some cases named in 4a and 4c are still untested, and their mutants
survive** (`mutation-review-r3.txt`).
- On agent/x (4a's deny list):
  - `>/dev/null git push origin main`: dropping the redirection skip (lines
    84-85) leaves the suite green.
  - The backtick form of `echo $(git push origin main)`: dropping the
    backtick break leaves the suite green. Backticks are tested only on main,
    where the broad rule hides them.
- On main (4c says "every case listed in b and c has a test"):
  - `sh -c "git commit -m x"` is missing.
  - A `bash` heredoc whose body is `git commit -m x` is missing.
- Also surviving, and recommended: the skip words `!`, `command` and `exec`
  off main. Dropping them stays green.
- The fix is tests only: add these strings to
  `test_denies_nested_push_to_main_or_force_from_plan_item_branch` and
  `test_denies_nested_git_on_main`. The hook already passes them, as the
  probes show.

## Nits (record; not merge-blocking)

- **N11 (extended).** If a Claude Code heredoc message body has an odd number
  of double quotes (e.g. `a 12" ruler`), the double-quote state flips. Two
  effects:
  - A later body line `git push --force origin main` is falsely denied. This
    fails safe.
  - A trailing `&& git push origin main` after such a message is silent off
    main. This fails open, but it falls in the 4d quoted-substitution bypass
    family.
  - Messages with an even number of quotes, including backticks and
    apostrophes, are fine.
- **N12 (variant).** A bare `(( x = 1 << 2 ))` (no `$`) is still taken as a
  heredoc, so the next line `git push origin main` is silent off main. This
  is contrived.
- **N14.** The `mutation-hook-r3.txt` file records the results but not the
  diff of each mutant. Recording the `diff` would make the evidence check
  itself. This would have caught the first no-op b.
- **N15.** ADR-KE-001 "As built" does not mention the round-3 hook split
  (broad on main, precise off main). The decision record is in requirements
  item 4, which is enough, but a one-line pointer in the ADR would help.

## Requirements 1-14 (question 4)

- **1-3, 5-12 and 14 are met.**
  - Each has its named test in `tests/test_harness_port.py`.
  - The developer's `green-rework3.txt` shows `scripts/verify.sh full`
    passing with 54 tests and 0 skipped.
  - My mutant base run also showed 0 skipped.
  - `.github/agents/` is unchanged against 886de45.
  - All eight `dispatch-<role>.md` files exist.
- **Item 4:** 4a-4e are met. **4f fails (B10)**, and the unit line is short of
  the 4a/4c cases (B11).
- **Item 13:** the dispatch part is met. The clean-checkout verify runs are
  due after the commit (B4), and CI green needs a push, which needs human
  approval.

## Were the tests weakened?

No.
- The B6 silent set, the L8 test, the master and `-C` cases, and the
  forged-description test are all present.
- jq mode runs in the image with 0 skipped.

## Observability

No product agent loop, model call, retrieval or tool call was added. No span
requirements apply.

## Next role needs to know

- **tester:** write the RED tests for B10 (three 1 MB single-token or line
  shapes, both modes, under 3 s) and the B11 strings.
- **developer:** fix B10 in the lexer only, then run `scripts/verify.sh full`.
- **orchestrator:** this is round 3 of 5. If rounds 4 and 5 do not clear B10,
  escalate. Do not amend 4f.
