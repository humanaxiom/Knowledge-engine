# ci-speed rework 2: security re-audit (2026-10-21)

**Verdict: PASS.** Nothing critical, high or medium. One new low (S3) and three info notes; none blocks the merge. Round-1 S1 and S2 are closed.

- Scope: `git diff 0b874c2 -- scripts tests` (working tree), the untracked `docs/handoffs/ci-speed.md` and `docs/evidence/ci-speed/rework2/`.
- Changes since round 1: `kill_jobs` TERM, ~2 s poll, KILL (scripts/test.sh:74-94); the N6 header (test.sh:12-13); the tests' `kill_leftovers` and `module_procs` (tests/test_harness_followups.py:817-870); and the new S1, N1, N2 and N3 tests.
- Method:
  - Scratch copies only, with no tests/ or docs/ and the scratch `fail_under` set to 0. `fx/full` is a working-tree copy that includes tests/.
  - Image `ke-gates:wt-33a132fbfdd7` (bash 5.2.15, pid_max 4194304), run with `--network none`, `--user 10001`, `--cap-drop ALL`, a read-only `/work` and a tmpfs `/tmp`.
  - Containers named `ke-sec-r2-*` and labelled `ke.project=ke-sec-r2`.
  - Repo files, HEAD and index were not touched.
- Raw output, harness and fixtures: `docs/evidence/ci-speed/rework2/security-scan/`.

## Checked and holding
- **S1 closed: KILL escalation works and stays inside the pool's job groups.**
  - Fixture: a module that ignores TERM and INT, plus a grandchild in its own group that also ignores TERM.
  - Controls that must survive:
    - OUT1: `setsid sleep`.
    - OUT2: a `sleep` in the wrapper's group.
    - OUT3: a TERM-ignoring process in another session.
    - OUT4: a TERM-ignoring process in the wrapper's group.
  - Results:

    | Run | Case | test.sh exit | Time to exit |
    |---|---|---|---|
    | t1 | TERM, pool | 143 | 2.03 s |
    | t2 | INT, pool | 130 | 2.03 s |
    | t3 | TERM, sub-package `step` | 143 | 2.02 s |
    | t3b | INT, same | 130 | 2.03 s |
    | t4 | TERM to test.sh's process group | 143 | 2.02 s |
    | t7 | TERM after a failing module, with the ignorer still running | 143 | 2.03 s |

  - In every run the ignorer, its uv and the grandchild were gone, OUT1-OUT4 were all alive, and the log dir was removed.
- **PID or PGID reuse between TERM and KILL.**
  - `pids` is captured once, from `jobs -p`. With `set -m`, every entry leads its own process group.
  - A PGID cannot be reallocated while any member of the group, a zombie included, still exists.
  - Once the group is empty, the number can come back only if the PID allocator wraps pid_max (4194304 in the gate) inside the ~2 s window.
  - The runner is uid 10001 with `--cap-drop ALL`, so no kill can reach another uid or anything outside the gate's PID namespace.
  - Not exploitable. Hardening is noted in I1.
- **A red run cannot read as green; exit codes are preserved.**
  - On a signal, `on_signal` always reaches `exit 130|143`, and the EXIT trap keeps that status.
  - Every command in `kill_jobs` is `|| true`, `|| return 0` or `sleep`.
  - A second TERM or INT during the poll is ignored (t6).
  - TERM with no jobs and an empty `pids` under `set -u` gives 143 (t12, `kill_jobs` copied verbatim).
  - Controls:
    - Red with no signal: rc=1 (`run-red.txt`).
    - Green: rc=0 (`run-green.txt`).
  - No path ends in 0 after a failure or a signal.
- **S2 closed: the tests' cleanup.** `kill_leftovers` (tests/test_harness_followups.py:817-837):
  - SIGKILLs a PID only while `proc_alive` holds.
  - Sends `killpg` only while `proc.poll() is None`. test.sh is unreaped, so its PID and PGID cannot be reused.
- **The /proc scan (`module_procs`, :855-870) is narrow.**
  - It matches a process only when all of these hold:
    - its argv contains the module name;
    - its cwd equals that test's own `mkdtemp` project;
    - it is not a zombie.
  - It skips other uids, whose `readlink` fails.
  - Decoy D1 (argv names `tests.test_ign_term`, but cwd is `/tmp/decoy`, and it ignores TERM) survived. So did D2 (`setsid sleep`) and D3 (TERM-ignoring, in the runner's group).
  - The results were the same with the real tests passing (t8) and with a TERM-only `kill_jobs` mutant that turns the S1 test red (t9). In t9 the cleanup removed the real leftovers and nothing else.
- **Hook:** the diff is still comment-only (header lines 3-4, Q18 wording). The new `HookHeaderTest` only reads the file.
- **Secrets and redaction:**
  - 0 profile paths, 0 SIDs and 0 secret-pattern hits in `rework2/`, the handoff and the diff's added lines.
  - The `KE_STORES__*_PASSWORD` hits in `green-verify-full.txt` are compose "variable is not set" warnings and carry no value.
  - The scan output is in `security-scan/secret-and-redaction-scan.txt`.
- **Out of scope for this change:** no new dependency, no network, no tracing or span change, and no prompt-injection surface.

## Findings
- **S3 (low, non-blocking): SIGHUP is not handled.** scripts/test.sh:96 and :100-101.
  - `on_signal` ignores only INT and TERM while it polls.
  - A HUP inside the ~2 s window ends test.sh with 129 before KILL is sent, and the TERM-ignoring module and its grandchild outlive it (t6).
  - A HUP alone does the same (t10: rc=129, pool children left). That is pre-existing in kind, since the base had no traps.
  - The exit stays non-zero, and inside the gate the container teardown reaps the orphans. The effect is limited to host runs.
  - Fix: add `trap 'on_signal 129' HUP` and set `trap '' INT TERM HUP` in `on_signal`.

## Info (no action required)
- **I1. KILL goes to every recorded group, not just live ones.** test.sh:91-93 KILLs every recorded pid without re-checking it.
  - Separately, `jobs -p` can still list the last pool job after the bare `wait` (line 140), even though bash has already reaped it, until its next job-table cleanup (t11).
  - Either path reaches a foreign process only after a full pid_max wrap (see "PID or PGID reuse" above).
  - Optional: KILL only the pids that were still alive at the last `kill -0`.
- **I2. `kill_leftovers` checks liveness, then kills, by bare PID.** tests/test_harness_followups.py:823-828.
  - It does not check identity, for example by start time from `/proc/<pid>/stat`.
  - This is theoretical, under the same wrap condition. It is test-only and fails red, not green.
- **I3. bash version floor.** The header allows bash >= 4.3 (test.sh:12).
  - On bash 4.3, `"${pids[@]}"` on an empty array under `set -u` would exit 1 instead of 130/143. That is still non-zero.
  - The gate runs bash 5.2.15, which behaves correctly (t12).
