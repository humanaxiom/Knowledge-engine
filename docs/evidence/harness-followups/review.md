# Review: harness-followups (PS-0.1 to PS-0.5)

Reviewer, 2026-10-18. Diff: `git diff a11842d` for .github/workflows/ci.yml,
scripts/test.sh, scripts/hooks/block-main-commit.sh,
tests/test_block_main_commit_hook.py, plus untracked tests/test_harness_followups.py.
Out of scope: the platform-skeleton plan docs.

Verdict: CHANGES REQUESTED (1 blocking, 5 nits)

## Test count, 62 -> 72 (exact)
I listed test IDs with a TestLoader in a detached worktree at a11842d (`discover -s tests -t .`)
and in the working tree (the same module list test.sh builds). `diff` result: all 62 base IDs are present.
The 10 additions are:
- the 7 new BlockMainCommitHookTest cases: backslash_newline x2, carriage_return x3,
  json_without_command_field_is_silent, only_first_command_value_is_judged
- the 3 cases in test_harness_followups: test_ci_runner_pinned,
  test_ci_actions_pinned_to_sha, test_integration_tests_run_once
No existing test stopped running.

## test.sh edge probes
Method: copy the new scripts/test.sh into a scratch project and put a fake uv on PATH that
execs the args after `python`.
| Case | New test.sh | Base test.sh |
|---|---|---|
| a. `tests/testfoo.py` (matches `test*.py`, not `test_*.py`) | silently NOT run, rc=0 | run |
| b. `tests/unit/` without `__init__.py` | silently skipped, rc=0 | also skipped (3.12 discover does not recurse into non-packages) |
| c. `tests/fixtures/__init__.py` with no tests | rc=5 "NO TESTS RAN", gate fails | pass |
| d. no top-level `tests/test_*.py` | literal glob `tests.test_*` gives ImportError, rc=1 (fails loudly) | Ran 0, pass |
| e. failing integration test, full | rc=1 (gate fails); fast rc=0 | same |
| f. failing test in a sub-package with `__init__` | rc=1 | same |
| g. `tests/test_a-b.py` | runs (importlib accepts it) | silently skipped |
| h. `tests/integration` without `__init__`, full | ImportError "not importable", rc=1 | same |
`set -euo pipefail` propagates every `uv run` failure, so `full` still fails if the
integration suite fails (e).

## Findings

### B1 (blocking): test.sh can silently run fewer unit tests and nothing guards it
- The top-level glob is `tests/test_*.py`. The base ran unittest's default pattern
  `test*.py`, so probe (a) shows a file that ran before now silently does not run. No such
  file exists today, but stopping silent drops is the reason for this rewrite.
- `test_integration_tests_run_once` only counts integration runs. Two mutations still pass
  every test and keep the gate green:
  - deleting the top-level `uv run ... "${mods[@]}"` line;
  - deleting the sub-package discover loop.
  In the first case the real gate would report OK with no unit tests run at all. The
  sub-package branch is never exercised (no sub-package exists, and the fixture has none).
- Fix:
  - glob `tests/test*.py`, matching unittest's default pattern;
  - extend the PS-0.3 fixture so it also asserts, in both fast and full, that one top-level
    unit test and one test in a non-integration sub-package (e.g. `tests/unit/`) each run
    exactly once. Use the same counter technique.

### N1 (nit): a package with no tests fails the gate
Probe (c): a helper package such as `tests/fixtures/` with only `__init__.py` makes discover
exit 5 under Python 3.12 and fails the gate. This fails closed, but it will surprise the
platform-skeleton work. Either skip packages with no `test*.py` or document the behaviour in
the test.sh header.

### N2 (nit): a sub-directory without `__init__.py` is skipped silently
Probe (b). This matches the base behaviour, so it is not a regression. Failing loudly
(`echo "tests/x has tests but no __init__.py" >&2; exit 1`) would close the last silent drop.

### N3 (nit): ADR-KE-001 normalise bullet does not mention CR deletion
The hook change is consistent with the decision. A text rule with fail-safe intent: CR is not
a word separator in bash, so deleting it reads `git\r commit` and `git\rcommit` as bash does.
Backslash-newline joined to nothing also matches bash (`gi\<NL>t` = `git`). Within the
judged words, neither change creates a new false negative compared with how bash runs the
command:
- `origin\<NL>main` was denied before and is now silent, but bash runs it as `originmain`,
  not `main`.
- `\<CR><LF>` is now joined, but bash does not treat it as a continuation. This can only
  over-deny.
The ADR's "Normalise" bullet still says only "join line continuations". The architect (who is
editing architecture.md) should add "delete CR; a continuation joins to nothing" so the ADR
and the hook header agree.

### N4 (nit, pre-existing, not a regression): no-jq path leaves `\uXXXX` escapes as letters
`git\u000d commit` reads as `gitu000d commit`. JSON.stringify and json.dumps emit `\r`, not
`\u000d`, for CR, so the PS-0.4 payloads are covered. Record this next to the accepted bypasses.

### N5 (nit): PS-0.2 test does not pin the SHA, by design
This follows the requirement. I checked the pin independently:
- `gh api repos/actions/checkout/git/ref/tags/v5.1.0` returns `commit fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`.
- The release v5.1.0 has target `releases/v5` and was published 2026-07-20.
- The commit message is "backport fixes to releases-v5 (#2523)".
The comment `# v5.1.0` is correct.

## Test adequacy (other items)
- PS-0.1/0.2 tests parse every `runs-on`/`uses:`. Adequate.
- PS-0.3: the fake uv is sound (no network, uses the real test.sh and tests/__init__.py). RED
  showed full=2 and fast=1 against the base script, so it catches the N3 regression. Gap: B1.
- PS-0.4: `assert_cr_same_as_without` checks:
  - the baseline without CR equals the expected decision;
  - the CR payload equals the baseline;
  - both the JSON `\r` and the literal-CR forms, in both jq modes.
  The literal-CR payload is invalid JSON, so jq mode also exercises the fallback sed path.
  RED failed on the no-jq `\r` -> `r` cases as expected. Adequate.
- PS-0.5: N16 cases cover `ma\`, `pu\` and `gi\` splits. RED showed them silent under the old
  join-to-space. The N17 cases are coverage pins and passed before by design. Adequate.
- No tests were weakened or removed. The hook test diff is additions only.
