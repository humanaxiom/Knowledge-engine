# Review: platform-supply-chain unit 5 ("verify output hygiene")

Reviewer, 2026-10-22. Diff: `git diff e6e1d28` (uncommitted U5 on
agent/platform-supply-chain). Scope: security L-3, L-4; review r1-n1..r1-n3;
PSC-18.

**Verdict: APPROVED** (0 blocking, 4 nits).

## Files read
scripts/verify.sh, scripts/offline_check.sh, tests/test_stack_scripts.py
(DOCKER_STUB, VerifyHostHalfTest, VerifyCallsLintTest),
tests/test_offline_check.py, tests/test_harness_followups.py, README.md,
docs/requirements.md (PSC-18, follow-ups), docs/architecture.md (D4 note).
Evidence read: u5-red-verify-fast.txt (20 expected failures),
u5-red-mutants.txt (16/16), u5-green-verify-fast.txt (767 run, OK,
`== verify fast: PASS ==` last), u5-green-verify-full.txt (`== gates-it:
PASS ==` once at :1517, `== verify full: PASS (632s) ==` once and last at
:2148, `== offline_check: PASS (92s) ==` at :2147).

## Checks
- **Fake gates-it (DOCKER_STUB) is sound.** It copies the verify.sh under
  test from the fixture cwd, runs its inner half (KE_IN_GATES=1) in a
  mktemp sandbox with lint/test/smoke stand-ins that write nothing to
  STAGE_LOG (stage-order tests unaffected), and ends `exit $?`; the EXIT
  trap only removes the sandbox and does not change the status. A failed
  mktemp makes every later step fail, so it fails closed. FAIL_STAGE=gates-it
  still exits 7 before the inner run. Reviewer mutants (review-u5-mutants.txt):
  inner `full` exits 3 before its line -> KILLED (6+ host tests red);
  inner line dropped with rc 0 -> KILLED (SS + HF). It cannot mask a failure.
- **test_harness_followups pins.** `INNER_PASS["fast"]` is exactly the old
  `== verify fast: PASS ==`; only the `full` value changed, to the new inner
  line. The 4 positive pins are `assertIn` on the merged output (same
  substring strength as before); the exact-line check is in
  `test_gates_it_half_prints_its_own_success_line` (`in out.splitlines()`)
  for both modes. The HF negatives were already `": PASS =="`; the
  VerifyCallsLintTest negative was widened to `": PASS =="`, which is stricter.
- **offline_check.sh.** `finished=0` is set before `trap cleanup EXIT`;
  `finished=1` only directly before `exit 0`, with nothing in between.
  PASS needs rc 0 and finished 1. `die` exits 1; `set -euo pipefail` is on,
  so every failure path reaches cleanup with rc != 0. INT/TERM traps and
  the teardown/bundle removal are unchanged; HUP added to the trap and to
  the reset. No path prints PASS without a finished rc-0 run. The only PASS
  after a signal is an untrapped signal that lands after `finished=1`, when
  the work is already done (truthful).
- **verify.sh.** Host PASS line unchanged (rc 0 + finished). Inner `full`
  prints `== gates-it: PASS ==`, `fast` unchanged. The r1-n2 comment is
  accurate (bash defers a trap until the foreground child returns).
- **Consumers of `verify full: PASS`.** None outside tests/docs. CI runs
  only `./scripts/verify.sh full` (rc-based). verify.sh's sentinel and
  `Ran N` greps read the test log, not PASS lines. No script, hook, .ps1 or
  agent file greps a PASS line. lint.sh/smoke.sh lines unchanged.
- **Docs.** PSC-18, D4 and README agree with the code. README r1-n1 done
  (no stage-order parenthetical, no repeated "`full` also scans").
- **Scope.** All changes map to L-3, L-4, r1-n1..n3 or PSC-18. Handoff and
  log changes are append-only. Evidence has no profile paths or SIDs.

## Findings
Blocking: none.

Nits (none can produce a false PASS):
- **n1 Positive offline_check PASS line is unpinned.** Mutant
  `oc_drop_finished_set` (delete `finished=1`) SURVIVED all 143 tests in
  test_offline_check + test_stack_scripts: offline_check would never print
  its PASS line on success, and nothing fails. Fail-safe direction, and the
  real full run shows the line, but the new flag is only tested in the
  negative direction. Suggest one `assertIn("== offline_check: PASS (", out)`
  in an existing happy-path host test.
- **n2 PSC-18's "`FAIL (exit N)` line last" is not asserted.** The M-1/L-3
  tests check the status and that no PASS line appears, not the FAIL line.
  Add `assertIn(f"FAIL (exit {128+n})", out)` or soften the bullet.
- **n3 The HUP trap in offline_check is not distinguished by a test.**
  Mutants `oc_drop_hup_trap_keep_flag` and `oc_hup_not_in_reset` SURVIVED:
  bash still dies 129 after the EXIT trap and the flag suppresses PASS, so
  the test sees the same result. The orchestrator ruled "both", so this is
  not a defect, but D4's "the traps give the exit status" is better read as
  "the traps give cleanup the signal's status". `oc_finished_at_start`
  SURVIVED too; that is the recorded USR1-pin follow-up.
- **n4 verify.sh:155-162** has two consecutive `if [ "$mode" = "full" ]`
  blocks. They could be merged into one if/else (cosmetic).

## Evidence
- Mutant run: docs/evidence/platform-supply-chain/review-u5-mutants.txt
  (driver: review-u5-mutants.py.txt). Baseline 143 tests OK; 2 KILLED,
  4 SURVIVED as above.
