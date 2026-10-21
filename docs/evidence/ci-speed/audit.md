# ci-speed: combined review + security audit (2026-10-20)

**Verdict: FAIL / CHANGES REQUESTED.** Security sub-verdict: PASS (no critical/high).
Review blockers: R1, R2, R3 (all medium). Lows are non-blocking.

Scope: `git diff 0b874c2` (working tree, branch agent/ci-speed) plus untracked handoff/evidence.
Files: scripts/test.sh, scripts/hooks/block-main-commit.sh, tests/test_harness_followups.py,
tests/test_block_main_commit_hook.py, README, CHANGELOG, requirements CS-1..9, architecture
§2.2.1 + ADR-KE-001 wording, open-questions Q18/Q14/Q-CS1.
Method: mutants of scratch copies only, run in `ke-gates:latest` (`--network none`, `--user 10001`,
`--cap-drop ALL`, ro `/work`, fresh tmpfs `/tmp`), container names `ke-sec-cs-*`. Repo files, HEAD
and index were not touched. Raw output: `docs/evidence/ci-speed/audit/` (scratch paths redacted).

## What holds (checked)
- Pool fail-closed. rc is passed through `<logs>/<m>.rc`, written after `|| rc=$?`. A missing or
  empty rc file (worker died) reads as `missing` or `""` and fails. A killed child gives rc 137
  and fails. `wait -n || true` and the final bare `wait` cannot swallow a failure because the
  status never travels through `wait`. `set -e` in the background subshell is neutralised by
  `|| rc=$?`. Mutants M1a/M1b/M1c (rc ignored, rc always 0, rc check off) are killed by
  `test_failing_module_fails_run_and_other_modules_still_run`.
- Coverage-file check: M2 (check off) is killed by
  `test_unit_pool_fails_when_a_module_leaves_no_coverage_data`.
- Concurrency: M4a (k=1), M4b (no cap), M4c (k=4 fixed) and M8 (no throttle) are killed by
  `test_unit_pool_concurrency_follows_nproc_capped_at_4`.
- No interleaving: M7 (stream with tee) is killed by `test_each_module_output_block_is_contiguous`
  and `test_verify_sees_sentinel_and_ran_lines_from_real_test_sh`. M6 (no final wait) is killed
  by 22 failures.
- Grouping is deterministic: size desc, then name. Logs print in glob order.
- Control run (`bash scripts/test.sh fast`, unmutated): rc=0, TOTAL 90 %, 32 modules,
  32 `Ran N>0` lines, sentinel line exactly once, 0 `error:` lines (`audit/g-CTRL-original.txt`).
  This agrees with `green-verify-full.txt` (353 s, 90 %) and `cs9-measure.txt` (239 s on 2 CPUs).
- Fixture fix: `test_coverage_erase_precedes_first_run_and_spares_checkout` keeps every original
  assertion (data_file under /tmp, erase before the first run, checkout file spared). It adds
  assertions that the rewrite took effect, so the nested run now writes inside `self.root`.
  No other test runs a real `coverage erase` on the gate's data (test_gate_least_privilege
  redirects data_file to a temp dir).
- Hook: `git diff -w` shows only `#` lines changed, so the change is comment-only. Covered by
  `HookHeaderTest`.
- mktemp dir: created before the `trap ... EXIT`, removed on exit with a quoted `rm -rf --`.
  It lives in a per-container tmpfs.
- Security: no shell-injection path. The parsed `data_file` (sed captures no space or quote)
  and the module names appear only in quoted expansions or as single argv words. No eval, no
  network, no new dependency, no tracing/span change, no prompt-injection surface.
  Secret scan: 0 hits (`audit/secret-scan.txt`).

## Findings
- **R1 (medium, blocking for review; test adequacy). M3 (the `Ran N>0` check removed) survives.**
  `audit/u-M3-ran-check-off.txt` is all OK. `test_unit_pool_fails_when_a_module_prints_no_ran_line`
  is also satisfied by the coverage-data check, because the silent fake uv writes no data file
  either. The case only the Ran check stops is a module that raises `SystemExit(0)` at import:
  it exits with rc 0, coverage saves its data, and it prints no `Ran` line. verify.sh's global
  `Ran` grep does not help, because the other modules print one. The scratch probe
  (`audit/probe_test_exit0.py.txt`) passes on the real test.sh (`audit/p-exit0-orig.txt`) and
  fails on M3 (`audit/p-exit0-M3.txt`). Fix (tester): add that test, or make the silent fake
  leave a coverage data file so the Ran check is isolated.
- **R2 (medium, blocking for review; gate integrity, fail-open-capable).** The per-module check
  proves that *a* file exists at the parsed path. It does not prove `combine` consumes it, which
  CS-4 and A-CS1 claim ("combine consumes one per module").
  - Empty parse falls back to `./.coverage`. In the gate this fails closed only because the
    checkout is read-only (EROFS on every module, `audit/g-M5a-parse-empty.txt`). In a writable
    checkout it would write data where combine never looks.
  - A divergent but writable parse (M5b: name `/tmp/garbage`; M5c: dir `/tmp/ke-garbage`):
    - Stale files at that path satisfy the check for a module that wrote nothing.
      `audit/u-M5b-*.txt` and `audit/u-M5c-*.txt` say "tests.testfoo left no coverage data,
      test.sh passed". Those mutants were killed only because earlier tests had left files in
      the shared /tmp.
    - On a fresh tmpfs with the fixtures unmutated (`audit/h-m5b.txt`, `audit/h-m5c.txt`), only
      `coverage combine`'s "No data to combine" stops fast mode.
    - In full mode, integration data would let combine succeed, and the gate would rest on
      `fail_under = 80` alone (not measured).
  - The parse depends on the text format of `coverage debug config`, which is not a stable
    interface.
  - Fix (developer):
    1. Fail when the parse is empty (no `.coverage` fallback).
    2. After `coverage combine`, fail naming the module if any `$cov_dir/$cov_name.$m.*`
       remains (combine deletes what it consumes), or pass the files to combine explicitly.
    3. Add a fixture test with a real combine.
- **R3 (medium, blocking for review; docs accuracy).** The accepted architecture §2.2.1 does
  not match the code:
  - (a) decision 1 runs `unittest -v --durations 10`, and Consequences relies on it for
    per-test CI timings. The code has no `--durations`.
  - (b) decision 2 puts logs in `/tmp/ke-unit/<module>.log`. The code uses `mktemp -d`.
  - (c) decision 2 prints one summary line per module, `unit: <s>s rc=<rc> <module>`. The code
    prints none.
  - (d) decision 4 says "On INT/TERM, test.sh kills the pool's children (trap)". Only an EXIT
    cleanup trap exists.

  Implement these or amend §2.2.1 (architect). Low: CS-1 says `tests/test_*.py`, while the code
  (unchanged behaviour) globs `tests/test*.py`.
- **L1 (low).** CS-9 compares the pooled 239 s with 426 s from experiment A, which ran on the
  base commit. CS-9 asks for a one-process run on the same commit and host, and the new tests
  add time to both. Re-measure, or record the deviation.
- **L2 (low).** The printf format at scripts/test.sh lines 61–62 holds a literal newline
  instead of `\n`. It works but reads like a bug.
- **L3 (low).** If a module's `.log` is missing, `cat` fails under `set -e`. The script exits
  (fail-closed) before printing later modules, and only cat's path names the module.
- **L4 (low, security info).** `compgen -G` treats the parsed `data_file` as a glob, so glob
  characters in pyproject's `data_file` would widen the check. pyproject is in the same trust
  domain as test.sh, and there is no injection.
- **L5 (low).** CHANGELOG has no entry for the pool itself (output now arrives per module,
  after the pool). Owner: marketer.
- **Info.** Untracked `docs/knowledge-engine-claude-code-prompt.md` (2026-10-18) is not part of
  this item, so keep it out of the commit (0 secret hits). An ignored stray
  `.coverage.c3f6723effb0.pid109.*` in the checkout root dates from 2026-10-19, before this change.

## Mutant table (`audit/mutants.diff.txt`, `audit/mutant-summary.txt`)
| Mutant | Result | Killed by |
|---|---|---|
| M1a rc ignored / M1b rc always 0 / M1c rc check off | killed | failing_module_fails_run... |
| M2 coverage-file check off | killed | ...leaves_no_coverage_data |
| M3 Ran check off | **survives** | none (probe kills it) |
| M4a k=1 / M4b no cap / M4c k=4 fixed / M8 no throttle | killed | ...concurrency_follows_nproc_capped_at_4 |
| M5a parse empty, fallback | killed in real gate only (EROFS) | g-M5a |
| M5b/M5c parse garbage, writable | killed by order-dependent stale /tmp (unit), by "No data to combine" (fast) | R2 |
| M6 no final wait | killed | 22 tests |
| M7 streamed logs | killed | contiguity + verify sentinel |
