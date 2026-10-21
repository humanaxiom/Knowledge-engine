# ci-speed rework 4/5: reviewer verdict

**Verdict: PASS** (no blocking findings; 5 nits)

Reviewed: the round-4 working tree on agent/ci-speed (HEAD a375a4e + the reverted round 3 + round 4), as
`git diff HEAD` plus the untracked `scripts/resource_probe.sh` and `tests/test_resource_probe.py`. Read
rework3/review.md (nits 1-7), the round-4 handoff lines, architecture §2.2.1-r3 (decision 4 Hardening, decision 6
S4 paragraph, rework-4 first tests), requirements CS-11/CS-12, open-questions Q-CS2, and rework4/
red-verify-fast.txt (FAIL, 21 failures, all in the 4 new probe tests, for the expected reasons),
s4-mutants.txt, nit5-p7-mutant.txt, green-verify-fast.txt (PASS, 721 tests) and green-verify-full.txt
(PASS 557 s; the new tests are `ok`, not skipped; both real `resources:` lines carry live numbers, so `[ -f ]`
holds for /proc and cgroupfs).

Reviewer mutants and probes ran on scratch copies only, in containers labelled
`com.docker.compose.project=ke-reviewer-cs4` (image ke-gates:wt-33a132fbfdd7, the current tag; --network none;
uid 10001; ro mounts). Output: `review/probe-mutants.txt` and `review/s4-detector-probe.txt`.

## Round-3 nits

| Nit | Status | Where |
|---|---|---|
| 1 Q-CS2 still "open" | closed | docs/open-questions.md:267-271 (moved under "Resolved 2026-10-21"); docs/requirements.md:2505, 2540-2543 |
| 2 §2.2.1-r3 "proposed" | closed | docs/architecture.md:768 ("accepted, confirmed by the orchestrator 2026-10-21") |
| 3 CS-4 test name | closed | docs/requirements.md:2378 = tests/test_harness_followups.py:679 |
| 5 no-root env test (P7) | closed | tests/test_resource_probe.py:436-500; P7 killed by the output check and the inotify check (tester evidence and reviewer R17) |
| 6 cpu_total_ticks via num | closed | scripts/resource_probe.sh:81 (^[0-9]{1,18}$, 10#), :83-86, :106-107 (both through num) |
| 4 chmod +x, 7 prompt file | open until commit | resource_probe.sh still untracked: stage with `git add --chmod=+x`; leave docs/knowledge-engine-claude-code-prompt.md out |

## Decision 4 hardening: conformance

- `[ -f ]` before every source open: field :30, psi :43, one :62, /proc/stat :74. Matches.
- `read -r -t 1 -n 4096` on every source read: :31, :44, :63, :75. The here-string read at :71 has neither, but it
  reads the in-memory `pr_cpu_max`, already capped at 4096 by `one`. Fine in substance (see nit 4 for wording).
- 64-line cap: field :31, psi :44; one and stat read one line. Matches.
- num 1-20 digits :21; stat fields 1-18 digits, 10#, either failure gives n/a for both keys :77-87. Matches.
- nproc :69 `OMP_NUM_THREADS='' OMP_THREAD_LIMIT='' nproc`. This is the same as the bare `VAR= ` form in the docs:
  both pass an empty value. Checked in the image (GNU coreutils 9.1). With `OMP_NUM_THREADS=5` exported, both
  spellings print 24 and plain `nproc` prints 5. shellcheck 0.9.0 (the lint gate) rejects the bare form with SC1007
  (reproduced). The docs should say so (nit 3).
- No env input: every `pr_*`, `cg` and function local is assigned before its first read, and root defaults to the
  literal `/` :16. Matches.

Probe mutants (review/probe-mutants.txt): 15 of 20 are killed. That covers the -f removal or weakening in each
reader (R1-R4: killed by the 10 s guard), the line cap in field (R8, R19), the num cap (R10), the stat cap and base
(R11, R12, R20), OMP (R15, R16) and P7 (R17). Survivors: R5 (no -t 1), R13 (steal raw) and R14 (total not through
num) are defence in depth that a regular file cannot show, so they are accepted. R6, R7, R9 and R18 are test gaps
(nit 2).

## Flakiness

- **FIFO hang guard.** PROBE_HANG_S = 10 s (tests/test_resource_probe.py:75) bounds a probe that takes about 0.1 s.
  The control run of all 8 probe tests took 0.84 s, so the headroom is about 100x. That makes it a hang guard, not a
  budget, and the load flake the human ruled out does not apply. On expiry killpg(SIGKILL) reaps the whole session.
  The R1-R4 runs show a blocked open(2) is killed cleanly in about 10 s per case.
- **inotify** (test_no_root_path_reads_no_env). It works in the gates image (Debian 12; P7 evidence shows 960 bytes of
  events, and R17 trips it). It also works on ubuntu-24.04 runners: a Linux kernel, uid 10001 has no other
  instances, and max_user_instances is 128 or more. It is not racy:
  - the watch covers only a private temp tree;
  - the rglob list is fully built before the first watch is added, so the test's own directory opens are not seen;
  - the precondition run happens before the watch;
  - events are queued synchronously at open time, before the probe exits.

  Marker values are random 18-digit numbers. Real counters cannot contain one by chance in practice. If inotify
  cannot start, the read check is skipped without a message. The output canary check still kills P7 (nit 5).

## S4 static detector

- On today's hook it finds nothing, so there is no false positive. The hook's only non-comment `&` is the `&&` at
  scripts/hooks/block-main-commit.sh:60.
- `&` forms: no false negatives found. The probe tried `true&`, `>&2&`, `2>&1&`, `&>/dev/null&`, `|& cat &`,
  `x=1 & y=2`, `>& file &`, `1>&- &`, `[[ … ]] & true`, `trap '… &' EXIT`, `$(… &)` and `{ :; }&`. All of them are
  flagged.
- The six words and `<(` / `>(`: flagged, including `builtin eval`, `command nohup`, `(setsid …)` and
  `exec 3> >(cat)`.
- **Nested shell: false negatives** (nit 1). Common spellings of `bash -c` are missed: `bash -ce`,
  `bash -o pipefail -c`, `bash --norc -c`, `"bash" -c`, `"$BASH" -c`, `$SHELL -c`, `dash -c` and `zsh -c`. Shells
  that read commands from stdin (`bash -s`, `| bash`) are not on the list either.

## Findings

| # | Severity | Where | Finding |
|---|---|---|---|
| 1 | nit (fix in this round recommended) | tests/test_block_main_commit_hook.py:803 (NESTED_SHELL), :839-855 | The listed construct "`bash -c` or `sh -c`" has false negatives (above; review/s4-detector-probe.txt). The option prefix `(?:-[A-Za-z]+\s+)*` takes neither an option argument (`-o pipefail`) nor a long option (`--norc`). `-[A-Za-z]*c(?![\w-])` needs `c` last in the cluster, so `-ce` is missed. The shell word must be bare `bash` or `sh` followed by whitespace, so `"bash"`, `"$BASH"`, `$SHELL`, `dash` and `zsh` are missed. Impact is low: a literal `&` or listed word inside the string of the nested shell is still flagged, and only text built at run time (for example an ANSI-C escape for the ampersand) hides it. Fix: match the shell word quoted or unquoted, including `$BASH`, `${BASH}`, `$SHELL` and `dash`, `zsh`, `ksh`; allow any non-operator words before a `-…c…` cluster on the same simple command; add these spellings to the detector test. Name `bash -s` and piping into a shell in the residual-risk text, or flag them. |
| 2 | nit (test gap) | tests/test_resource_probe.py:333-349, 437-500 | Four probe mutants survive (review/probe-mutants.txt). **R7**: field has no `-n 4096`. Kill it with a meminfo whose first line is longer than 64x4096 bytes, followed by `MemTotal:`. With the cap that gives n/a; without it the value prints. **R9**: psi has no 64-line cap. Kill it with more than 64 filler lines before `some` in pressure/io. **R6**: one has no `-n 4096`. The 20-digit cap in num hides it, so it is acceptable as is. **R18**: `cg="${CG:-…}"`. The no-env test points every name at the planted root only, so a name used as a sub-directory reads a missing path. Also run the names pointed at `planted/sys/fs/cgroup` and `planted/proc`. |
| 3 | nit (docs) | docs/architecture.md:920-922 | Show the spelling the code uses, `OMP_NUM_THREADS='' OMP_THREAD_LIMIT='' nproc`, with "(quoted empty values; shellcheck SC1007 rejects the bare `VAR= cmd` form; same effect)". As written, a grep of the doc text does not find the script line. No behaviour difference. requirements.md:2482 says "cleared" and is fine. |
| 4 | nit (docs) | docs/architecture.md:976; docs/requirements.md:2513; docs/architecture.md:903 | The code also treats the stderr pipe (&#124;&amp;) as non-background (test :808 and the allowed list of the detector test), but both docs list only `&&`, `>&`, `<&`, `&>`. Add it. Also, architecture line 903 says "Every `read` has a timeout and a byte cap", while the here-string read at resource_probe.sh:71 has neither (it reads an in-memory value). Say "every read of a source". |
| 5 | nit | tests/test_resource_probe.py:506-514, 494 | If inotify_init1 is unavailable, the read check is skipped silently. It is available in the gates image and on CI today. Consider a visible note (for example a skipped subTest) so a lost check is not invisible. |

Commit hygiene carried from round 3: nit 4 (`git add --chmod=+x scripts/resource_probe.sh`) and nit 7 (exclude
docs/knowledge-engine-claude-code-prompt.md; include docs/evidence/ci-speed/ci/, rework3/, rework4/).
