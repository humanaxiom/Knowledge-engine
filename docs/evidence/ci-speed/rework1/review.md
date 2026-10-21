# ci-speed rework 1: re-review (reviewer, 2026-10-20)

**Verdict: CHANGES REQUESTED.** Two blocking findings (N1, N2), both test-only. The production
changes to `scripts/test.sh` are correct as written; every prior blocker is closed.

Scope: `git diff 0b874c2` (working tree, agent/ci-speed) plus untracked `docs/handoffs/ci-speed.md`
and `docs/evidence/ci-speed/`. `docs/knowledge-engine-claude-code-prompt.md` was ignored. CS-6 holds:
there is no change to verify.sh, ci.yml, pyproject.toml or test_sentinel.py.
Method: 8 mutants of scratch copies plus 5 reviewer probe tests, run in `ke-gates:wt-33a132fbfdd7`
(bash 5.2.15, coverage 7.16.2) with `--network none`, uid 10001, `--cap-drop ALL`, a read-only
/work and a tmpfs /tmp. Raw output is in `review/` (mutants.txt, out-*.txt, probe_review.py.txt,
stress-order-guard.txt). The unmutated baseline passes all 34 tests, probes included (`review/out-base.txt`).

## Prior findings
| ID | Status | Where |
|---|---|---|
| R1 | closed | tests/test_harness_followups.py:593 (SystemExit(0) at import, error line names module + Ran); :555 now has the silent module leave data (`assert_left_data`). M3 killed: rework1/r1-tests-M3-ran-check-off.txt |
| R2 | closed | scripts/test.sh:57-65 (API lookup, empty/failed fails, no fallback); :86-99, :149-152, :164, :169 (per-label collect); :176-183 (explicit list + leftover check). Tests :612, :641, :663, :1022. Reviewer mutants mB/mC (sub-package/integration not collected), mG (fallback restored) and mH (combine only the module files) are all killed |
| R3 | closed | (a) test.sh:115 `--durations 10`, test :683; (b) mktemp kept, architecture.md:659 amended; (c) test.sh:141, test :696; (d) test.sh:69-84, test :763. mE (no `set -m`) and mF (no kill_jobs) are killed. CS-1 glob: requirements.md:2298 |
| L1 | closed (nit N7) | rework1/cs9-same-commit.txt: 271 s pool vs 475 s one process = 0.57 <= 0.60; requirements.md:2374 |
| L2 | closed | test.sh:108 uses `\n`; test :1030 |
| L3 | closed | test.sh:126-133 (and :135-138 for rc); test :725 |
| L5 | closed | CHANGELOG.md:7-19 |
| L4 | moot | the compgen check is gone; the glob at test.sh:92 quotes the parsed path |

## Checked and holding
- Trap and process groups. Under `set -m`, every `&` job leads its own process group, so
  `kill -TERM -- -$p` (:75) takes down the subshell, uv and python. `trap '' INT TERM` stops the
  handler running twice, and `exit` still runs the EXIT `rm -rf`.
  - Probes measured exit codes 130 (INT) and 143 (TERM).
  - A TERM sent while the sequential sub-package `step` runs kills its python and exits 143
    (`test_probe_signal_during_subpackage_step`, passes on the baseline).
- Wait semantics. `wait -n || true` (:120) and the bare `wait` (:123) never carry a module
  status; the status travels through the `.rc` file. `step` (:101-104) returns the job's status,
  and `set -e` then fails the run, so a failing sub-package or integration suite does fail
  test.sh (probes pass on the baseline). Pool failure exits at :154, before sub-packages,
  as before the change.
- Combine list and leftover check. The label globs (`<name>.<label>.*`) cannot collide: a
  `.` follows the label, and the labels are `tests.test*` and `tests.<dir>`. data_files cannot be
  empty at :176. Duplicate files are deleted by combine ("Combined 21 files, skipped 12" in
  tester-verify-full.txt:1948 = 33 runs).
- Data_file lookup fails closed. Empty output, a failed lookup or a relative path all end in a
  failure; a relative path gets EROFS in the read-only checkout. `COVERAGE_FILE` is honoured
  by the API, as it is by `coverage run`.
- Tests not weakened. Contiguity (:903) is now stricter for result lines: whole-line `^...$`,
  exactly 4, contiguous. Its part (b) checks only the chatty modules against each other, but the
  new order guard (:934) spans every module in glob order, so mutants m1-m5 are all killed
  (tester-contiguity-mutants.txt, tester-order-mutants.txt). The fixture fix keeps its asserts.
- The signal test (:763) is robust. It waits up to 60 s for the sleepers to start, 30 s for exit
  and 10 s for death, runs in its own session, skips with a named reason off Linux, and kills
  everything in `finally`.

## Findings
1. **N1 (medium, blocking; gate integrity).** The `step` exit status is untested.
   - Mutant mA, `wait "$!" || true` at scripts/test.sh:103, passes every shipped test
     (`review/out-mA.txt`). Only the reviewer probes kill it.
   - Under mA, a failing sub-package or integration test leaves test.sh exiting 0, and verify.sh's
     Ran/sentinel greps still pass. The gate would go green on a red integration suite.
   - The change introduced this indirection: before, it was a direct command under `set -e`.
   - Fix (tester): in IntegrationRunsOnceTest, add a failing `tests/unit/test_bad.py` (fast and
     full) and a failing `tests/integration/test_bad.py` (full); test.sh must exit non-zero.
     Scratch version: `review/probe_review.py.txt`, the two `test_probe_failing_*` methods.
2. **N2 (medium, blocking; flaky gate test).** The order guard
   `test_module_logs_and_summary_lines_print_in_glob_order` (tests/test_harness_followups.py:934-985)
   gets its reverse finish order from 1.2/0.6/0.0 s sleeps. Its precondition is an
   `assertEqual` (:959-960), so start-up jitter fails it instead of skipping it.
   - Measured on `--cpuset-cpus 0,1` (`review/stress-order-guard.txt`): 12/12 pass with 0 or 2
     busy loops, but 10/12 with 6 busy loops. The two failures were finish orders
     `[ob, oc, oa]` and `[oc, oa, ob]`.
   - In CI (2 vCPU, k=2) this test runs beside another pool module while its fixture starts four
     python processes, which is close to the failing load.
   - Fix (tester): make the order deterministic with a file handshake instead of sleeps.
     test_oc writes `done-oc` in tearDownClass; test_ob waits (bounded) for `done-oc` before it
     finishes, and test_oa waits for `done-ob`. All three start together (k=4 >= 3, size
     padding unchanged). Keep the precondition and the m1/m5 mutant kills.
3. **N3 (low).** Exit codes 130/143 (architecture.md:672) are not pinned. The signal test asserts
   only `!= 0` (:802), so mutant mD (`on_signal 1`) survives (`review/out-mD.txt`).
   Fix (tester): `assertEqual(code, 128 + sig)`, as in `test_probe_signal_exit_codes`. Cheap; do it with N1/N2.
4. **N4 (nit).** kill_jobs (:72-77) sends TERM and exits without waiting or escalating. Children
   can outlive test.sh by a moment, and one that ignores TERM survives. That is fine for
   python/uv today; the test allows 10 s.
5. **N5 (nit).** After `set -m` (:71), the foreground commands (combine, report, mypy) run in
   their own process groups. A terminal Ctrl-C or hangup no longer reaches them; the trap fires
   once they finish. SIGHUP is not trapped, so pool children would survive a hangup outside a
   container. This does not matter in the gate (PID namespace, no tty on stderr).
6. **N6 (nit, portability).** `stat -c %s` (:108), `nproc`, `wait -n` and `mapfile` need GNU
   tools and bash >= 4.3. That is fine because test.sh only runs inside the gates image
   (bash 5.2.15), but a header comment saying so would help.
7. **N7 (nit).** CS-9 evidence. Both runs in cs9-same-commit.txt exited 1, because the
   contiguity conflict was still open, and the file names an image tag, not a commit (the change
   is uncommitted). 0.57 holds. Record the commit SHA when CS-7 measures CI.

Observability: no agent loop, model, retrieval or tool call was added, so no span is needed.
Security: there is no new input surface; the labels and paths appear only in quoted expansions.
