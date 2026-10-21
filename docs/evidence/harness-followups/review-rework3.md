# Re-review: harness-followups, rework 3 (review B3; security M5, L20)

Reviewer, 2026-10-18. Round 3 of 5. Bar: block only on a spec violation, a broken gate or
silent test loss; everything else is a nit. Diff against base a11842d (uncommitted):
`scripts/test.sh`, `scripts/verify.sh`, `scripts/hooks/block-main-commit.sh`,
`.github/workflows/ci.yml`, `tests/test_sentinel.py`, `tests/test_harness_followups.py`,
`tests/test_block_main_commit_hook.py`. Platform-skeleton docs are out of scope.

Verdict: APPROVED (0 blocking, 5 new nits, 3 carried nits)

## Method
- The repo was copied to the scratchpad with `.venv` excluded. Each mutant was applied to the
  copy only. `scripts/verify.sh <mode>` ran in `knowledge-engine-gates:latest` with
  `--network none` and `KE_IN_GATES=1`. The repo's scripts were never edited (sha256:
  test.sh `057e4682...`, which is unchanged since rework 2; verify.sh `fd067da3...`; hook
  `c7ec9af3...`). The copy was deleted afterwards.
- Raw output for every mutant and probe: `docs/evidence/harness-followups/review-rework3-raw.txt`.
  The probe rows are named by label there, and the exact strings are in the label list below.

## 1. B3: RESOLVED
| Mutant | Result |
|---|---|
| m0 baseline | fast PASS, 89 tests |
| m1 top-level run line deleted | RED fast and full (no Ran line) |
| m2 sub-package loop deleted | RED, 8 failures |
| m3 glob `test_*.py` | RED, 2 failures (`testfoo`) |
| **m4 = m1 + `tests/unit`** | **RED fast: `Ran 1 test OK`, then the sentinel FAIL message, rc 1** (was PASS in rework 2) |
| **m7 = m1 + `tests/integration`** | **RED full: sentinel FAIL, rc 1** (was PASS); fast RED (no Ran line) |
| m5 Ran check deleted | caught: 4 `VerifyRequiresTestsRunTest` failures |
| m6 pipefail/`\|\|` removed | caught: `test_failing_test_sh_still_fails` fast and full |
| m8 smoke exits 3 | verify full rc 3 |
| m9 failing top-level test | rc 1 |
| s1 sentinel check deleted from verify.sh | caught: `test_ran_without_sentinel_fails` fast and full |
| s3 sentinel `@skip` | RED (sentinel not `ok`) |
| s5 `tests/test_sentinel.py` deleted | RED, so it fails closed |
| s9 `"${mods[@]}"` changed to `"$mods"` (only the first module runs) | RED (sentinel absent, 40 tests) |
| s2 = m1 + `tests/unit` + sentinel moved into `tests/unit` | PASS, 2 tests: silent loss (N13) |
| s8 top-level glob narrowed to `tests/test_sent*.py` | PASS, 1 test: silent loss (N13) |

m1, m4 and m7 are the shapes B3 asked for, and all are now RED. s2 and s8 need a deliberate
edit that targets the sentinel; s2 also goes against the module's docstring. That is a nit,
not a block.

## 2. Hook dual normalisation
- **ADR-KE-001 and criterion 4:** consistent. text_a (joined to nothing) is the PS-0.5
  reading, and h2 (judge text_b only) turns the 10 PS-0.5/backslash-form subtests RED. text_b
  only adds denials. The decision stays a fail-safe text rule: linear, no awk, never `allow`,
  same reasons.
- **No new false negative.** I probed the base hook (a11842d) against the new one over 26
  shapes x 2 branches x jq/no-jq. Off the default branch, exactly two rows go from deny to
  silent:
  - `cont-originmain`: the remote word is glued to the branch word by a backslash-newline
    with no space. Bash reads one token, `originmain`.
  - `cont-gitpush-glued`: the git word is glued to the push verb. Bash reads `gitpush`.

  Neither is a push to the protected branch. PS-0.5 (join to nothing) requires this result,
  and it is the reading bash gives.
- **Rows that newly deny:** comment and even-run shapes (M5), `pu<BS-NL>sh`, `g<BS-NL>it`, the
  CRLF continuation, and a literal CR with no jq.
- **The new false positives fail safe.** Example: `sq-literal` (a backslash-newline inside
  single quotes, so a literal argument) now denies off the default branch. Benign
  continuations stay silent: `benign-ls` and `benign-cont`.
- The h3 mutant (`break` removed) is equivalent, because `reason` is never cleared.

## 3. Test adequacy
- **M5:** 10 rows x jq/no-jq. h1 (judge text_a only) turns all 20 subtests RED, so the tests
  bite. The PS-0.5 tests are unchanged.
- **L20:** l1 (`persist-credentials: true`) turns the test RED. The parser scopes to each
  checkout step's `with:` block.
- **B3/N9:** `test_ran_without_sentinel_fails` and `test_failing_smoke_fails_full` are new.
  `test_failing_test_sh_still_fails` now runs in both modes. The existing fakes print the
  sentinel, so each check is guarded on its own (s1, m5).
- No test was weakened, skipped or removed. The diff to the existing hook tests is
  additive only (+114/-0).

## 4. PS-0.x against the code
- PS-0.1: `runs-on: ubuntu-24.04`. Met.
- PS-0.2: checkout `@fbc6f39...` `# v5.1.0`, a full SHA. Met. The SHA source is in the
  earlier handoff and was not re-fetched, because the gates have no network.
- PS-0.3: m2, m3 and m7 fast/full. Met.
- PS-0.4: CR probes deny as without the CR, with and without jq, on and off the default
  branch. Met.
- PS-0.5: join to nothing, plus the N17 tests. Met.

## Findings

### N13 (nit): the sentinel can be defeated by edits that target it
s2 (sentinel moved into a sub-package) and s8 (top-level glob narrowed to the sentinel)
both print PASS with 1-2 tests. Optional hardening: verify.sh also requires one guard
module's line (for example `tests.test_harness_followups.VerifyRequiresTestsRunTest`), or
test.sh prints the top-level module count and verify compares it.

### N14 (nit): no silent-control test for text_b
No test asserts that the newline reading adds no denials for benign multi-line commands, for
example the `benign-ls` and `benign-cont` probe rows. Both are silent today.

### N15 (nit, architect/documenter): docs do not record the dual normalisation or the sentinel
- The ADR-KE-001 decision still says "Normalise: join line continuations". It should record
  (a) and (b), "deny if either", M5, and the new accepted false positive (`sq-literal`).
- CLAUDE.md, AGENTS.md and the verify.sh header do not say that verify needs
  `test_top_level_unit_suite_ran ... ok`, or that `tests/test_sentinel.py` must stay
  top-level.

### N16 (nit, record only): intended behaviour change from the base
The `cont-originmain` row is no longer denied off the default branch (bash reads
`originmain`). Record it with N15 so that a later reviewer does not read it as a regression.

### N17 (nit): sentinel regex is unanchored
`test_top_level_unit_suite_ran .* ok` would also match a sub-package test with the same
name, or a line that prints it. Anchoring on the module id
(`\(tests\.test_sentinel\.TopLevelSuiteSentinelTest\.`) is cheap.

### Carried, still open (nits): N10, N11, N12
test.sh is byte-identical to rework 2, so N10 (symlinked package) and N12 (dead
`__pycache__` case) are unchanged. N11 (stderr merge, rc mapped to 1) is unchanged. N9 is
resolved.
