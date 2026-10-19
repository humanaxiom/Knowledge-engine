# Reviewer: platform-stack-up CI fix (5 MB hook timing test), 2026-10-19

Scope: uncommitted diff on top of 1e89584, `tests/test_block_main_commit_hook.py` only
(`git diff -- tests/test_block_main_commit_hook.py`: +68/-4, two hunks). Inputs read:
handoff `docs/handoffs/platform-stack.md` section "2026-10-19 tester: CI fix",
`ci-run.txt` (lines 712-720), `ci-fix-mutation.txt`, `ci-fix-verify.txt`,
`scripts/hooks/block-main-commit.sh` lines 40-70.

Verdict: APPROVED. No blocking findings.

## (a) Contradiction resolution, or gaming a gate?
Legitimate. Security L21 says text (b) is built and judged only when the command holds a
backslash-newline. That is a structural property, and the 3 s bound at 5 MB only stood in for
it, varying with runner load (CI no-jq: 3.92 / 4.42 / 6.43 s, ci-run.txt:712-717).
- The new test `test_second_text_built_and_judged_only_with_backslash_newline` asserts the
  property directly: (built, judged) == (1, 1) on 5 shapes with no backslash-newline,
  including the near-misses "windows paths" and "backslash, space, newline". It asserts
  (2, 2) on 3 shapes with one, in both jq and no-jq modes. Each fixture also asserts
  whether `\\n` is present, so fixture drift cannot hide a result.
- Mutation proof (ci-fix-mutation.txt): removing the `case` guard while keeping its body
  gives 10/10 failures `(2, 2) != (1, 1)`. The old 3 s test would only have caught this
  mutation through timing (Table C: two passes reached 2.3 s in the image, so even the old
  bound was marginal for this mutation). L21 is now guarded more strongly than before:
  the check is deterministic and fails on any regression to two passes, whatever the
  machine speed.
- The 5 MB test is kept, with its bound loosened to < 9 s, which is under the 10 s Claude
  Code hook timeout. It still catches a regression that would hit the real timeout, which
  is the user-facing harm. No assertion was removed; the silent-output check stays.
- The hook (`scripts/hooks/block-main-commit.sh`) is unchanged; the tester confirms
  `git diff --stat scripts/` is empty.
- verify full PASS: 320 unit tests OK, smoke 3 OK (ci-fix-verify.txt:833-843).

## (b) Brittleness of the `bash -x` trace count (nit)
- N1 (nit): `TRACE_BUILT` matches the literal `tr '[:upper:]' '[:lower:]'` inside `norm`,
  and `TRACE_JUDGED` matches the loop variable name in `for text in`. A harmless refactor
  breaks the test, for example lower-casing with `${x,,}`, renaming the loop variable,
  building texts in a helper loop, or adding a second `tr '[:upper:]'` elsewhere in the
  hook (there is exactly 1 today). This is not severe: every such breakage fails loudly,
  because counts go to 0 or 2+ against exact-equality assertions. None of them can pass
  silently. Suggest a short comment in the hook next to `norm` and the loop saying the
  test counts them. Optionally, count `texts+=`/array length via a trace marker instead.
- N2 (nit): `trace_passes` inherits `PS4` from `os.environ` through `self.env(mode)`. A
  caller with a custom PS4 (not root) would change the `+` prefix, and the anchored
  regexes would count 0. Pin `PS4='+ '` in the env for that run. This is low risk inside
  the gates image.

## (c) Requirement 4f 1 MB tests
Untouched. The diff has only two hunks, at lines 529+ (new test) and 615 (5 MB bound).
`test_one_megabyte_token_shapes_finish_quickly` (lines ~236-255, < 3.0) and
`test_one_megabyte_command_finishes_quickly` (lines ~375-385, < 3.0) are byte-identical
to 1e89584. Both passed in the red CI run; only the 5 MB test failed (ci-run.txt:712-719).

## (d) Other timing assertions that may flake on a 2-core runner
1. `test_one_megabyte_token_shapes_finish_quickly`: 1 MB < 3.0 s, both modes. "heredoc
   lines" no-jq is the closest analogue of the 5 MB shape that took 6.43 s. Linear
   scaling gives about 1.3 s, so headroom is about 2.3x. This is the most likely
   next flake, and it is a binding spec (4f), so if it flakes it needs an orchestrator or
   analyst ruling, not a quiet loosening. It passed in the failing CI run, but its
   timing was not printed.
2. `test_one_megabyte_command_finishes_quickly`: 1 MB of `echo x &&` < 3.0 s. Same class
   and same note.
3. `test_long_command_finishes_quickly`: 400 segments < 5.0 s. Tiny input, so low risk.
4. `test_block_main_commit_hook` 5 MB sanity: < 9.0 s against a 6.43 s CI worst case,
   about 1.4x headroom. Acceptable as a sanity bound tied to the 10 s hook timeout, but
   watch it. A slower runner day could reach 9 s; if that happens, the hook really is
   close to the real timeout, and that is a product finding, not a test flake.
5. `tests/integration/test_stack_up.py:106`: `elapsed < CONNECT_TIMEOUT_S` (2.0 s) on
   an immediate ENETUNREACH. Low risk: the error is synchronous, and a timeout is already
   asserted separately via `assertNotIsInstance(TimeoutError)`.
6. `tests/test_stack_scripts.py:528-537`: 20 s polling deadline plus a fixed 0.3 s sleep
   before the signal. Low risk; the deadline is generous.
Recommendation (nit): have the 1 MB tests print elapsed on success, or record it in the
evidence, so headroom on CI is visible before it turns red.
