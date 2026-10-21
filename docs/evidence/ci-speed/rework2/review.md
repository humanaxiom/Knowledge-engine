# ci-speed rework 2: re-review (reviewer, 2026-10-20)

**Verdict: PASS.** No blocking findings. N1-N4, N6 and N7 are closed; N5 was accepted. There are two new nits (N8, N9), neither blocking.

Scope: `git diff 0b874c2 -- scripts tests` (working tree, agent/ci-speed). sha256 of that diff is
0d3e44c5...3b22, the same tree that CS-9 measured. Method: 9 variants of scratch copies, a latency and
bystander probe (3 runs), and a load stress (2 CPUs, 6 busy loops, 12 runs for each of 3 tests). All ran in
`ke-gates:wt-33a132fbfdd7` with `--network none`, uid 10001, `--cap-drop ALL`, a read-only /work and the label
`ke.reviewer.project=ke-reviewer-cs2`. Raw output is in `review/` (mutants.txt, out-*.txt, probe_r2.py.txt,
out-probe.txt, stress.sh.txt, out-stress.txt). The baseline IntegrationRunsOnceTest + UnitPoolStaticTest
passes 32/32 with no skips (`review/out-base.txt`).

## Prior findings
| ID | Status | Where / proof |
|---|---|---|
| N1 | closed | tests/test_harness_followups.py:1014 (sub-package, fast+full) and :1026 (integration, full). Each one asserts its precondition (the FAIL line ran) and then `!= 0`, and calls clear_coverage_data so no carried-over data can cause the failure. mA (`wait "$!" \|\| true`, scripts/test.sh:120) is killed in all 3 subtests (`review/out-mA.txt`) |
| N2 | closed | :1067-1104 HANDSHAKE, :1106-1157. The finish order is fixed by the done-marker (atomic `os.replace`) and the wait for the predecessor pid, not by timing. The precondition assertEqual is kept at :1131. k=4 starts all three modules at once, so the handshake cannot deadlock, and each wait is capped at 60 s. PID reuse on the /proc wait can only make a module wait longer, never change the order. Stress: 12/12 (`review/out-stress.txt`), and the tester's 12/12. m1 and m5 are killed on the final test.sh (`review/out-m1.txt`, `out-m5.txt`) |
| N3 | closed | :804 `assertEqual(code, 128 + int(sig))`, :912 `== 143`. mD (INT->1) and mDt (TERM->1) are killed |
| N4 | closed | scripts/test.sh:74-94 (TERM, then a poll of at most 20 x 0.1 s, then KILL to the live groups). S1 test :874. K1 (no KILL) and K2 (KILL to the leader pid only, not the group) are killed (`[167] != []`) |
| N6 | closed | scripts/test.sh:12-13 (see nit N9 on the version floor) |
| N7 | closed | rework2/cs9-same-commit.txt records HEAD 0b874c2 and the diff sha256, which matches the reviewed tree. Both runs exit 0; 271/464 = 0.58 <= 0.60 |
| N5 | accepted | orchestrator ruling |

## Round-2 changes checked
- **kill_jobs (test.sh:76-94).**
  - Correct: the trap ignores INT/TERM during cleanup (:96). With an empty `pids` the function returns at once (:88). Every kill is guarded (`|| true` or `if`), so `set -e` cannot abort the handler, and `exit "$1"` runs the EXIT `rm -rf`.
  - Bounded: the probe measured 0.11 s from TERM to exit with normal modules and 2.07 s with a TERM-ignoring module, 3/3 runs (`review/out-probe.txt`).
  - Exit codes: 143 in every run.
  - Scope: an unrelated process with the same cwd survives every run (`bystander_alive=True`).
  - K3 (no TERM, poll, then KILL) survives, as expected: TERM-first is a courtesy that no test can observe, and it does not affect correctness.
- **S2 cleanup (:817-837).** Only live pids get SIGKILL. `killpg` is called only while `proc.poll() is None`, and test.sh is unreaped at that point, so its pgid cannot have been reused. Note that set -m puts pool jobs in their own groups, so `killpg` is only a backstop for test.sh's own group; the recorded pids cover the module processes.
- **S1 test (:839-927).**
  - The module writes its pid only after `SIG_IGN` is set, so the RED was genuine.
  - The /proc scan (:855-870) needs both the module name in argv and cwd == the throwaway project. That excludes test.sh itself (its argv has no module name) and every outside process. It skips entries that vanish (OSError) and counts zombies as dead.
  - Stress result: 12/12, and 12/12 for the signal test (`review/out-stress.txt`).
- **Tests not weakened.** The only skips added are the `skipUnless(linux and /proc)` guards on the two signal tests, and their reason names the platform. Both ran (not skipped) in rework2/green-verify-full.txt:962-963, which ends in `verify full: PASS (357s)`.

## New findings
8. **N8 (nit; kill scope).** scripts/test.sh:81, :86, :92: the single-pid fallbacks `|| kill -TERM "$p"`, `|| kill -0 "$p"` and `|| kill -KILL "$p"`.
   - Under `set -m` (:73), every job's leader p is the pgid of its group and never leaves it. The group form fails (ESRCH) only when no member is left, the leader included.
   - So the fallback can reach only a process that reused pid p, which is outside the job groups. The `kill -0` fallback would then keep the poll busy and lead to a KILL of that process.
   - It is unreachable in practice: it needs a PID wrap during one run inside the gate's PID namespace. Dropping the fallbacks would make "kill only job groups" hold by construction. This is optional.
9. **N9 (nit; comment accuracy).** scripts/test.sh:12 says bash >= 4.3. `"${pids[@]}"` on an empty array under `set -u` (:85, :91, reached when a signal arrives after all jobs are reaped, for example during combine) is "unbound variable" before bash 4.4. The real floor is 4.4. The gates image has bash 5.2.15, so this has no effect.

Observation, not a finding: under `set -m`, bash prints `[n] Terminated run_module "$m"` job notices on a signal exit (`review/out-probe.txt`). They are cosmetic.

Observability: no agent loop, model call, retrieval or tool call was added, so no span is needed.
Next: N8 and N9 are optional. They can go to the developer with the commit or be left as they are; neither blocks the gates.
