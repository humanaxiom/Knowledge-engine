# Review: platform-stack-ready (2b), rework round 2 of 5

- Reviewer, 2026-10-19. Base fe2f101, uncommitted tree. Read: handoff sections "orchestrator: rework round 2", "tester: rework 2 RED", "developer: rework 2 GREEN"; red-rework2.txt, red-rework2-mutants.txt, green-rework2.txt; review-rework1.md.
- Diff read: scripts/lint.sh (full diff against fe2f101); the new tests in tests/test_stack_scripts.py (LintScriptTest, lines 1159-1262), tests/test_stack_worker.py:170-195, tests/test_stack_readiness.py:552-571.
- Freshness: no file under engine/, scripts/, tests/, docker/, compose, pyproject or uv.lock is newer than green-rework2.txt (00:38:28 local; lint.sh 00:36:00). green-rework2.txt ends `== verify full: PASS (146s) ==`, exit 0, 419 unit tests OK.
- Mutants: run in a scratch copy of the tree (no .git, no .env) with `docker run --rm --network none` on ke-gates. Standalone containers named rw2-reviewer-mutants*, with no compose project and nothing in a ke-verify-* project. Each mutant ran in its own copy inside the container against tests.test_stack_scripts.LintScriptTest (15 tests, using the real shellcheck and pwsh). The scratch copy is deleted and no container is left.

## Verdict: APPROVED (0 blocking)

## R1-B1: resolved

`test_lint_refuses_a_symlink_to_a_clean_script` uses the recorder tools, which always pass, and clean targets inside and outside scripts/ for .sh and .ps1. It asserts rc != 0, "symlink" and the link path. Nothing but the refusal can fail lint here.

## Mutant results (baseline: 15 tests OK)

| Mutant | Change | Result |
|---|---|---|
| L12b | refusal `if` -> `if false` | KILLED (18) incl. all 4 clean-target cases |
| L15a | `docker` dropped from the link find | KILLED (5) |
| L15b | file links only (`-xtype f`) | KILLED (8): dir and dangling links |
| L15c | only script-named links refused | KILLED (11) |
| L15d | `exit 1` after the refusal removed | KILLED (18) |
| L15e | refusal message without the path | KILLED (11) |
| L15f | `-iname '*.sh'` -> `-name` | KILLED (3) |
| L15g | `docker` dropped from the shellcheck find | KILLED (5) |
| L12a | ps1 `-iname` -> `-name` | KILLED (2) |
| L12d | `.psm1` dropped | KILLED (2) |
| PSdepth | `-maxdepth 1` on the ps1 find | KILLED (2) |
| LN1 | `[` alternative dropped | KILLED (1) |
| WC | `*` alternative dropped | KILLED (1) |
| SEV | `-Severity Error` only | KILLED (5) |

The first L15c attempt broke the find syntax, so its kill did not count. The mutant was corrected (bash -n clean) and re-run, and the table shows the re-run. The PSdepth regex failed to apply on the first pass and was also re-run.

## New lint code (soundness, PS-2.23)

- `find scripts docker -type l -print0` (without -L) lists every symlink as an entry: file, directory or dangling, under any name and at any depth. Nothing is descended through a link, and lint exits 1 before either tool runs. This closes N-R5 / L-15.
- With links refused first, `-type f` on the two tool finds no longer hides anything. Shell scripts are selected case-insensitively (`-iname '*.sh'`). The PowerShell find (`*.ps1`/`*.psm1`, any case and depth), the newline and wildcard refusals, the env-only path passing (L-7) and the fixed `-Command` heredoc are all unchanged. Their mutants are killed above, so PS-2.23 has not regressed.

## Test integrity

- Six tests were added (413 -> 419) and none removed. Since green-rework1-final, no assertion, skip or threshold was changed. The removals shown by a diff against fe2f101 are the round-1 changes already judged legitimate in review-rework1.md.
- N-R1: patches `Job.func` as a raising PropertyMock, and both `import_attribute` bindings, for three refused names. The tester recorded that it kills WK5 (3 failures, red-rework2-mutants.txt). N-R4: the real probe path is in place, with no client, dial or request. The tester recorded that it kills F1b.

## Nits (non-blocking)

- N-R6: the three `find` calls run in process substitutions, so a find error (missing dir, unreadable subdir) is not fail-closed. An empty link list then reads as "no links". This is a pre-existing pattern, and the dirs are fixed, in-repo and readable in the gates image.
- N-R7: the N-R1 test swallows any exception from `execute_job` and has no in-test check that the refusal path was reached. WK5 being killed shows it is reached today. A `job.get_status() == FAILED` assertion would make that explicit.
- N-R8: lint.sh header line 4 is about 120 chars. Cosmetic.
- Still open by ruling: M-2, L-14/N-R2, N-R3 (deferred to ingest-ledger M-1 unit); SM6/N1, RZ10/N3 and the round-0 nits listed in review-rework1.md.
