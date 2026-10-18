# Re-review: harness-followups, rework 2 (B1, B2, N6, N7, N8)

Reviewer, 2026-10-18. Scope: `scripts/test.sh`, `scripts/verify.sh`,
`tests/test_harness_followups.py` after rework 2. ci.yml and the hook were approved earlier
and were not re-reviewed. Bar (round 2 of 5): block only on spec violations, broken gates or
silent test loss.

Verdict: CHANGES REQUESTED (1 blocking, 4 nits)

## Method
- The repo was copied to a scratchpad (`.venv` excluded). Every mutant was applied to the copy
  only, and `scripts/verify.sh <mode>` ran inside `knowledge-engine-gates` with
  `--network none`, mounted on the copy. The repo's scripts were never edited. Their sha256
  values match the reviewed values (test.sh `057e4682...`, verify.sh `97692389...`). The copy
  was deleted afterwards.
- Raw output: `review-rework2-mutants.txt` and `review-rework2-probes.txt` (this directory).

## Mutants
| Mutant | Layout | Result |
|---|---|---|
| m0 baseline | repo as is | fast PASS, 82 tests |
| m1 delete top-level `unittest` line | repo as is | **RED** in fast and in full ("no Ran N tests line") |
| m2 delete the sub-package loop | repo as is | RED, 8 failures |
| m3 glob reverted to `tests/test_*.py` | repo as is | RED, 2 failures (`testfoo`) |
| **m4 = m1** | **+ `tests/unit/` package, 1 test** | **fast PASS, `Ran 1 test`: 82 tests silently lost** |
| **m7 = m1** | **+ `tests/integration/` package, 1 test** | **full PASS, `Ran 1 test`: 82 tests silently lost**; fast RED |
| m5 verify.sh: Ran check deleted | repo as is | caught: `VerifyRequiresTestsRunTest` RED (4 failures) |
| m6 verify.sh: pipefail/`||` handling removed | repo as is | caught: `test_failing_test_sh_still_fails` RED |
| m8 smoke.sh exits 3 (full) | repo as is | verify rc 3, no PASS line |
| m9 a real failing top-level test | repo as is | fast rc 1, full rc 1, smoke not run |

m5 and m6 change the gate itself, so the gate run shows PASS. That is expected. The point is
that the suite's own tests go red.

## Questions asked
1. **Resolved?** B2 yes (probe i: `deep` runs once in fast and in full). N6 yes (probes j and p
   fail and name the directory). N7 yes (header lines 8-9; probe k gives rc 5). N8 yes (probe d
   gives `error: no top-level unit tests in tests/`, with no ImportError). **B1 is only partly
   resolved; see B3.**
2. **Mutants:** see the table. m1, m2 and m3 are RED on today's tree. m1 goes green again as
   soon as `tests/` contains any other test package (m4, m7).
3. **Probes a-o, plus p-u:** all as intended. Integration runs once in full and never in fast,
   including the nested `tests/integration/deep` (probe m: 1, the base gave 2). Missing
   `__init__.py` fails at any depth, including inside integration (p) and hidden dirs (s). New
   gap: probe t, a symlinked test package, is skipped silently (N10).
4. **verify.sh:** it still lists no test commands (only `scripts/test.sh` and
   `scripts/smoke.sh`, and `test_verify_sh_has_no_inlined_commands` is green). It still fails
   when test.sh fails (m9 and m2 give rc 1 with "test.sh exited non-zero").
5. **tee/pipefail and smoke:** smoke's exit handling is unchanged. `scripts/smoke.sh` is not
   piped, so `set -e` passes smoke's own exit code through (m8: rc 3). For test.sh, pipefail
   makes the pipeline report test.sh's failure, and `||` converts it to rc 1. The original code
   is lost (for example 5 becomes 1); see N11.
6. **Full-mode output reaches the caller:** yes. tee streams to stdout, and m8 and the green
   run show the unittest output, the `Ran` line and the smoke lines. test.sh's stderr is now
   merged into stdout (N11).

## Findings

### B3 (blocking, the rest of B1): the "any Ran N > 0" check does not survive a second test package
- `grep -Eq '^Ran [1-9]'` passes if any unittest invocation ran a test. Deleting the
  top-level run line (m1) is caught only because the repo has no other test package today.
- With one `tests/unit/` package (m4, fast) or one `tests/integration/` package (m7, full,
  which is the commit gate), m1 prints `== verify: PASS ==` after 1 test instead of 83. Those
  82 tests include the guard tests themselves, so the loss is silent.
- `tests/integration/` is exactly the layout that PS-0.3 targets and that platform-skeleton
  will create. Rework 1 asked for "m1 must go RED". That only holds on the current tree.
- Fix (developer or architect picks one). The check must not be deleted along with the line it
  guards:
  - test.sh or verify.sh compares the sum of the unit-run `Ran N` lines with a loader count of
    `tests/` minus `tests/integration`; or
  - verify.sh requires a `Ran` line from the top-level run specifically (for example, test.sh
    prints a marker that verify checks before and after the top-level run); or
  - verify.sh checks that a known guard module ran (verbose ids such as
    `tests.test_harness_followups.`).
- Test: a `VerifyRequiresTestsRunTest` case and/or a fixture case that reproduces m4 and m7.
  For example, the fake test.sh reports only a sub-package or integration `Ran 1 test`, or the
  fixture project has a sub-package and the top-level run is missing. It must go RED under
  `scripts/verify.sh fast` and `full`. Re-run m1 with a sub-package present as evidence.

### N9 (nit): verify failure-path tests are thin
`test_failing_test_sh_still_fails` covers fast mode only. No test asserts that a failing
`smoke.sh` fails `verify full`. Behaviour is correct today (m8, m9).

### N10 (nit): a symlinked test package is skipped silently
Probe t: `find` does not follow symlinks, so `tests/ext -> /elsewhere` with tests gives rc 0
and runs 0 tests. The base `discover` would have run it. This layout is unlikely. Add `-L`,
or reject symlinked dirs under `tests/`.

### N11 (nit): stream merge and exit code
`2>&1 | tee` merges test.sh's stderr into stdout and maps every test.sh failure to rc 1.
Neither is a gate problem. Mention it in the verify.sh comment if callers ever rely on
either.

### N12 (nit): dead `tests/__pycache__` case
In test.sh line 42, the `tests/__pycache__` case in the loop is redundant because `find` with
`-prune` already returns nothing for it. This is harmless.

## Test adequacy
- No tests were weakened, skipped or removed. RED reasons in `red-rework2.txt` match the
  intended defects.
- New fixture cases (nested package, nested missing `__init__`, no top-level modules) and
  `VerifyRequiresTestsRunTest` exercise real behaviour. m5 and m6 prove the verify tests bite.
- Gap: none of them models a tree with more than one test package (B3).
