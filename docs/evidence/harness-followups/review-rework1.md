# Re-review: harness-followups, rework 1 (B1, N1, N2)

Reviewer, 2026-10-18. Scope: `scripts/test.sh` and `tests/test_harness_followups.py`
after rework 1. ci.yml and the hook were approved in the first review (`review.md`) and
were not re-reviewed.

Verdict: CHANGES REQUESTED (2 blocking, 3 nits)

## Mutation check (requested by orchestrator)
Method: the repo's `scripts/test.sh` was swapped for each mutant, `scripts/verify.sh fast`
was run, and the file was restored at once. It was then byte-compared with the reviewed copy
and was identical.
| Mutant | verify fast | Raw output |
|---|---|---|
| m1: delete `uv run ... -m unittest -v "${mods[@]}"` | **PASS, 0 tests run** | `review-rework1-mutant-m1.txt` |
| m2: delete the sub-package loop | RED, 4 fails (`sub` = 0, fast and full) | `review-rework1-mutant-m2.txt` |
| m3: revert glob to `tests/test_*.py` | RED, 2 fails (`testfoo` = 0, fast and full) | `review-rework1-mutant-m3.txt` |

The fixture would catch m1, but it never runs under m1. The guard lives in
`tests/test_harness_followups.py`, a top-level module, so deleting the top-level run line
also deletes the guard. The repo has no sub-packages, so under m1 the real gate runs nothing
and prints `== verify fast: PASS ==`.

## Edge-case probes, new vs base test.sh
Method: a scratch project with a fake `uv` on PATH (execs the args after `python`). Each
module appends a label to a counter file. Raw output: `review-rework1-probes.txt`.
| Case | New | Base |
|---|---|---|
| a. `tests/testfoo.py` | runs, rc 0 (B1 glob fixed) | runs |
| b. `tests/unit/test_u.py`, no `__init__` | rc 1, names dir (N2 fixed) | silent skip, rc 0 |
| c. `tests/fixtures/__init__.py` only | rc 0 (N1 fixed) | rc 0 |
| d. no top-level `tests/test*.py` | rc 1 (literal glob, ImportError): fails closed | rc 0 |
| e. failing integration test, full / fast | rc 1 / rc 0 (by design) | rc 1 / rc 1 |
| f. failing test in sub-package | rc 1 | rc 1 |
| g. `tests/test_a-b.py` | runs | silently skipped |
| h. `tests/integration` without `__init__`, full | rc 1, names dir | rc 1, ImportError |
| **i. `tests/unit/__init__.py` + `tests/unit/deep/{__init__,test_d}.py`** | **deep NOT run, rc 0** | deep runs |
| j. `tests/unit/loose/test_l.py` (no `__init__`) under a package | loose skipped silently, rc 0 | same |
| k. `tests/fixtures/test_data.py` with no TestCase | rc 5 NO TESTS RAN | rc 0 |
| l. unit + integration pkgs, fast / full | integ 0 / 1 | integ 1 / 2 |
| m. `tests/integration/deep/` package, full | integdeep 1 | 2 |
| n. package dir with a space | runs | runs |
| o. `tests/integration` without `__init__`, fast | rc 1, names dir | rc 0 |

## Findings

### B1 (blocking, still open): deleting the top-level run line still leaves the gate green
- The glob half of B1 is fixed: m3 goes RED and probe a runs.
- The sub-package half is fixed: m2 goes RED.
- The m1 half is not fixed. The m1 mutation was named explicitly in B1, and verify reports
  PASS with zero tests run. A guard that runs inside the run it guards cannot catch that run
  being removed.
- Fix: put the check outside the top-level run. Any one of these would do (the architect or
  developer picks):
  - `scripts/verify.sh` or test.sh fails when the unit run executed fewer tests than a
    `TestLoader` count of `tests/` minus `tests/integration`;
  - test.sh asserts that each unit `unittest` invocation reports `Ran N` with N > 0;
  - a check in `verify.sh` (outside test.sh) that the fixture module ran.
- Whatever is chosen needs a test, and m1 must go RED under `scripts/verify.sh fast`.
  Re-run all three mutants as evidence.

### B2 (blocking, new regression from the N1 fix): nested test packages are dropped silently
- Probe i: `compgen -G "$d/test*.py"` looks only one level deep. A package such as
  `tests/unit/` that holds tests only in a nested package (`tests/unit/stores/test_x.py`) is
  now skipped with rc 0. The base `discover` ran those tests.
- This is the same kind of silent drop that B1 was about, and platform-skeleton is likely to
  create this layout.
- Fix: test for `test*.py` recursively, e.g. `find "$d" -name 'test*.py' -print -quit | grep -q .`.
- Test: a fixture case with a nested package whose tests must run exactly once, in fast and in
  full.

### N6 (nit): the N2 check is top-level only
Probe j: `tests/unit/loose/test_l.py` with no `__init__.py`, inside a package, is still skipped
silently. This matches the base behaviour, so it is not a regression. If B2's fix walks the
tree recursively, the same walk can apply the `__init__.py` check at every depth.

### N7 (nit): a helper package with a `test*.py` file that holds no tests fails the gate
Probe k: rc 5 "NO TESTS RAN". This fails closed. Document it in the test.sh header next to the
skip rule.

### N8 (nit): an empty top-level glob fails with an ImportError, not a clear message
Probe d: with no `tests/test*.py`, the literal pattern is passed to unittest. This fails
closed, but `shopt -s nullglob` plus an explicit message would be clearer. It interacts with
B1: zero top-level modules should be an error.

## Test adequacy
- The fixture design is sound. Labelled counters cover top, testfoo, sub and integration in
  both modes. N1 and N2 have their own cases, and RED showed the expected reasons.
- Gaps: m1 (B1) and nested packages (B2), as above.
- Environment note: the fixture passes a Windows path to bash, so it fails when run with the
  Windows host Python (exit 127). It is only valid inside the gates container, which is the
  only supported entry point. This is not a finding.
- No tests were weakened or removed.
