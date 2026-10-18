# Handoff: harness-followups

Outcome metric moved: neither. These are carry-in fixes that keep the gates
trustworthy; the CI runner change on 2026-10-19 makes this urgent.
Spec: `docs/requirements.md` § platform-skeleton, criteria PS-0.1–PS-0.5.
Umbrella plan: `docs/handoffs/platform-skeleton.md`. Base: a11842d.

## 2026-10-18 — orchestrator: item opened
- Branch `agent/harness-followups`. It also carries the uncommitted platform-skeleton plan docs (requirements and handoffs).
- Next: the tester writes RED for PS-0.1–PS-0.5. Meanwhile the architect designs platform-config, platform-stack and platform-offline (PS-Q7 first) in `docs/architecture.md`.

## 2026-10-18 — tester: RED for PS-0.1–PS-0.5
- Asked: failing tests for PS-0.1..0.5; touched only `tests/` plus this section and evidence.
- New `tests/test_harness_followups.py`:
  - `test_ci_runner_pinned` (PS-0.1): every `runs-on` == `ubuntu-24.04` (PS-Q1), no `-latest` anywhere in ci.yml.
  - `test_ci_actions_pinned_to_sha` (PS-0.2): every `uses:` is `owner/repo@<40 hex> # vX[.Y.Z]`; checkout comment is `v5[.x]`. SHA not asserted; developer fetches it and records the source here.
  - `test_integration_tests_run_once` (PS-0.3): copies the real `scripts/test.sh` and `tests/__init__.py` into a temp project whose `tests/integration` package has one counting test; a fake `uv` on PATH runs the args after `python` with the test interpreter. Expects full=1, fast=0. No real integration suite is created.
- `tests/test_block_main_commit_hook.py`, new cases (both jq modes; CR as JSON `\r` escape and as a literal CR, each compared to the same command without CR):
  - PS-0.4: `test_carriage_return_denies_as_without_it_on_main`, `..._off_main`, `test_carriage_return_stays_silent_as_without_it`.
  - PS-0.5 N16: `test_backslash_newline_joins_to_nothing_off_main` (`ma\`+NL+`in`, `pu\`+NL+`sh`), `..._on_main` (`gi\`+NL+`t commit`).
  - PS-0.5 N17: `test_json_without_command_field_is_silent`, `test_only_first_command_value_is_judged` (pass already; coverage pins).
- Run: `scripts/verify.sh fast` -> FAILED (failures=13), 72 tests, 0 skipped. Evidence: `docs/evidence/harness-followups/red.txt`.
- RED reasons (all expected): runner `ubuntu-latest`; checkout `v4.4.0`; integration counts full 2 != 1, fast 1 != 0; no-jq `\r` escape becomes the letter r (`gitr`, `mainr`), so 2 CR subcases are silent; backslash-newline joins to a space, so 6 N16 subcases are silent.
- Next (developer): pin runner and checkout v5 SHA in ci.yml; fix test.sh discovery; hook: strip CR (`tr -d '\r'`, drop the `\r` escape), join backslash-newline to nothing. The existing continuation case in `test_backslash_forms_deny_push_off_main` still holds (a space precedes the backslash).

## 2026-10-18 — developer: GREEN for PS-0.1–PS-0.5
- Touched only `.github/workflows/ci.yml`, `scripts/test.sh`, `scripts/hooks/block-main-commit.sh`. No tests edited. Not staged or committed.
- PS-0.1: `runs-on: ubuntu-24.04`.
- PS-0.2: `actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0`.
  - Command: `gh api repos/actions/checkout/git/ref/tags/v5`. Result: object type `commit`, sha `fbc6f399...` (lightweight tag, no dereference needed).
  - Cross-check: `.../tags/v5.1.0` -> `commit fbc6f3992d24...` (identical); v5.0.0 = 08c6903c, v5.0.1 = 93cb6efe. v5 is a moving tag, so the comment names the exact release v5.1.0.
- PS-0.3: `scripts/test.sh` runs top-level `tests/test_*.py` as named modules, plus any other non-integration `tests/*/` package via discover. `tests/integration` runs only in `full`, once.
- PS-0.4/0.5: hook drops JSON `\r` escape in no-jq extraction, `tr -d '\r'` in normalisation, backslash-newline joined to nothing; header comment updated.
- `scripts/verify.sh full` -> `== verify full: PASS ==`, 72 tests OK. Evidence: `docs/evidence/harness-followups/green-full.txt`. Was red (13): `test_ci_runner_pinned`, `test_ci_actions_pinned_to_sha`, `test_integration_tests_run_once`, the CR cases and the backslash-newline cases.
- Windows host check (Git Bash 5.3.9, no jq, scratch repo, payloads piped only): all PS-0.4/0.5 cases deny, controls silent. Evidence: `docs/evidence/harness-followups/hook-live-host.txt` (driver: scratchpad `hostcheck.sh`).
- Next: reviewer and security, then commit approval.

## 2026-10-18 — tester: rework 1 RED (review B1, N1, N2)
- Touched only `tests/test_harness_followups.py`. The PS-0.3 fixture now has counted modules, each writing a label to `KE_TEST_COUNTER`: `tests/test_x.py` (top), `tests/testfoo.py` (testfoo), `tests/unit/` package (sub), `tests/integration/` (integration).
- `test_integration_tests_run_once` is unchanged in intent (full=1, fast=0) and passes.
- New tests, each run in fast and in full:
  - `test_unit_tests_run_once` (B1): top, testfoo and sub each ==1.
  - `test_helper_package_without_tests_passes` (N1): adds `tests/fixtures/__init__.py`; expects rc 0 with top and sub still ==1. testfoo is left out so this fails only on N1.
  - `test_test_dir_without_init_fails_loudly` (N2): adds `tests/loose/test_loose.py` with no `__init__.py`; expects rc != 0 and `tests/loose` in the output.
- Run: `scripts/verify.sh fast` -> FAILED (failures=6), 75 tests. Evidence: `docs/evidence/harness-followups/red-rework1.txt`.
- RED reasons (all expected):
  - testfoo ran 0 times in both modes (glob `test_*.py`).
  - fixtures: discover exits 5 "NO TESTS RAN" in both modes.
  - loose: rc 0, skipped silently in both modes.
- Next (developer): in `scripts/test.sh`:
  - glob `tests/test*.py`;
  - skip packages that have no `test*.py`;
  - for a dir with `test*.py` but no `__init__.py`, print a message naming the dir to stderr and exit 1.

## 2026-10-18 — developer: rework 1 GREEN (review B1, N1, N2)
- Changed only `scripts/test.sh`:
  - B1: top-level glob is now `tests/test*.py`.
  - N1: sub-packages with no `test*.py` are skipped.
  - N2: a `tests/<dir>/` with `test*.py` but no `__init__.py` prints an error naming the dir to stderr and exits 1 before any run.
- Integration still runs once, in full only. Gate commands are only in test.sh, and uv keeps `--locked`.
- `scripts/verify.sh full` -> PASS, 75 tests OK. Evidence: `docs/evidence/harness-followups/green-rework1.txt`.
- Nothing staged or committed.

## 2026-10-18 — tester: rework 2 RED (review B1, B2, N6, N8)
- Touched only `tests/test_harness_followups.py`.
- PS-0.3 fixture: added a nested package `tests/unit/deep/{__init__,test_d}.py` (label `deep`) to `UNIT_LABELS`. It already runs once, because `tests/unit` has its own test file and `discover` recurses.
- New tests in `IntegrationRunsOnceTest`, each run in fast and in full:
  - `test_package_with_only_nested_tests_runs_once` (B2, probe i): `tests/stores/graph/test_graph.py`, with `__init__` at each level and no test file in `tests/stores`. Expects `nesteddeep` == 1.
  - `test_nested_dir_without_init_fails_loudly` (N6): `tests/unit/loose2/test_l.py` with no `__init__`. Expects rc != 0 and `tests/unit/loose2` in the output.
  - `test_no_top_level_unit_tests_fails_clearly` (N8): removes the top-level modules. Expects rc != 0, `no top-level unit tests` in the output, and no `ImportError`.
- New class `VerifyRequiresTestsRunTest` (B1) copies the real `verify.sh` into a temp project with a fake `test.sh` and a fake `smoke.sh`, and sets `KE_IN_GATES=1`. The fake prints its `Ran` line to stderr, as unittest does.
  - `test_no_ran_line_fails` (fast and full): RED.
  - `test_ran_zero_tests_fails` (fast and full): RED.
  - `test_ran_some_tests_passes` (control, fast and full; checks that the `Ran` line and the smoke output are still shown): green.
  - `test_failing_test_sh_still_fails` (control): green.
- Run: `scripts/verify.sh fast` -> FAILED (failures=10), 82 tests. Evidence: `docs/evidence/harness-followups/red-rework2.txt`.
- RED reasons (all expected):
  - loose2 is skipped silently (rc 0).
  - With no top-level tests, the literal `tests.test*` ImportError appears and the message is missing.
  - `nesteddeep` runs 0 times.
  - verify prints PASS with no `Ran` line, and again with `Ran 0 tests`.
- `test_verify_sh_has_no_inlined_commands` is still green.
- Next (developer):
  - `verify.sh` (gates branch): capture test.sh's stdout and stderr, pass them through to the caller, and fail unless a `Ran N` line with N > 0 appears. Do not list any test commands in verify.sh.
  - `test.sh`: recursive `test*.py` detection, the `__init__.py` check at every depth, and `nullglob` plus a `no top-level unit tests` error.

## 2026-10-18 — developer: rework 2 GREEN (review B1, B2, N6, N7, N8)
- Changed only `scripts/test.sh` and `scripts/verify.sh`; no tests edited, nothing staged.
- `verify.sh` (gates branch): `test.sh 2>&1 | tee tmpfile` under pipefail. FAIL if test.sh exits non-zero, or if the output has no `^Ran N tests` line with N > 0. No test commands listed; the full-mode smoke call is kept.
- `test.sh`:
  - B2: a package is skipped only if it has no `test*.py` at any depth (`find ... -print -quit`).
  - N6: the `__init__.py` check covers every directory under tests/ with `test*.py` at any depth (`__pycache__` pruned).
  - N8: `nullglob`; with no top-level modules it prints `error: no top-level unit tests in tests/` and exits 1.
  - N7: header comment on the fail-closed (exit 5) behaviour.
  - integration runs once in full only; `--locked` kept.
- `scripts/verify.sh full` -> 82 tests OK, smoke pass, PASS. Evidence: `docs/evidence/harness-followups/green-rework2.txt`.
- Mutation m1 (top-level run line deleted, `verify.sh fast`) -> RED: "FAIL (no Ran N tests line with N > 0)", rc 1. `test.sh` restored, sha256 matches. Evidence: `docs/evidence/harness-followups/mutation-m1-rework2.txt`.
- Next: reviewer re-review.

## 2026-10-18 — tester: rework 3 RED (security M5, L20)
- Tests added (only the two test files touched):
  - `test_backslash_newline_after_comment_or_even_run_denies_on_main`: security M5 rows 1-6, live shapes c1-c3. Covers a comment ending in a backslash, a Windows-path comment, `ls #a\`, a comment then a push on main, and even runs of 2 and 4 backslashes.
  - `test_backslash_newline_after_comment_or_even_run_denies_off_main` (agent/x): rows 7-9 plus live shape p1 (`HEAD:main`).
  - Both run in jq and no-jq modes with the compact payload. The existing PS-0.5 join-to-nothing tests are unchanged.
  - `CiWorkflowTest.test_ci_checkout_does_not_persist_credentials`: L20. Every checkout step has a `with:` block containing `persist-credentials: false`. The parser was checked on host to pass with the line and fail with `true`.
- Added mid-round, for review B3 and N9 (orchestrator ruling):
  - New `tests/test_sentinel.py` with `TopLevelSuiteSentinelTest.test_top_level_unit_suite_ran`. It passes trivially. Its `-v` line appears in the real run.
  - `VerifyRequiresTestsRunTest.SENTINEL` holds that exact `... ok` line. The existing fakes (no Ran line, Ran 0, the passing control, failing test.sh) now print it, so each check is guarded on its own.
  - New `test_ran_without_sentinel_fails` (fast and full) covers the m4/m7 shape.
  - New `test_sentinel_with_ran_passes` is the control.
  - `test_failing_test_sh_still_fails` now covers full mode too.
  - New `test_failing_smoke_fails_full` (N9).
- `scripts/verify.sh fast` -> RED, 89 tests, failures=23, no errors or skips. Evidence: `docs/evidence/harness-followups/red-rework3.txt`.
  - 20 M5 subtests fail (10 rows x 2 modes). Each is `None != 'deny'`: the hook is silent, which is the fail-open security reported.
  - 1 L20 failure: "checkout step has no with: block".
  - 2 B3 subtests fail: `test_ran_without_sentinel_fails` fast and full. verify prints PASS without the sentinel.
  - The N9 tests are green already, as the review said (m8, m9).
  - All other tests, including PS-0.5, are green.
- Next (developer):
  - Hook: judge normalisation (a), join to nothing, and (b), backslash-newline kept as a newline. Deny if either matches.
  - ci.yml checkout step: add `with: persist-credentials: false`.
  - verify.sh (gates branch): also require a line matching `test_top_level_unit_suite_ran .* ok` in test.sh's output. Keep the Ran > 0 check.

## 2026-10-18 — developer: rework 3 GREEN (security M5, L20; review B3)
- Hook: `block-main-commit.sh` judges two texts, (a) backslash-newline joined to nothing, (b) backslash-newline as a newline; deny if either matches (loop, first match wins, two linear passes, no awk, never allow, same reasons). Header names both and cites M5.
- ci.yml: checkout step has `with: persist-credentials: false` (SHA pin and comment kept).
- verify.sh (gates branch): also requires `test_top_level_unit_suite_ran .* ok` in test.sh output; failure message names the sentinel. No test commands listed.
- `scripts/verify.sh full` -> PASS, Ran 89 tests, OK, smoke pass. Evidence: `docs/evidence/harness-followups/green-rework3.txt`. All 23 RED failures now green.
- Mutation (scratch copy, deleted): m4 (top-level line removed + tests/unit, fast) and m7 (+ tests/integration, full) both exit 1 with the sentinel message though `Ran 1 test OK`. Evidence: `mutation-rework3.txt`.
- Host check (Git Bash, no jq, payload files only): c1-c3, p1, plus even-run and continuation rows DENY; benign rows silent. Evidence: `hook-live-host-r3.txt`.
- Not staged or committed. Next: reviewer/security re-check.

## 2026-10-18 — tester: rework 4 RED (security M6, L21, I1; review N14, N17)
- Touched only `tests/test_block_main_commit_hook.py` and `tests/test_harness_followups.py`.
- Hook tests (both jq modes, compact payload):
  - `test_comment_or_even_run_then_continued_push_denies_off_main`: Table M rows 1-11 plus q1 and q2 on agent/x.
  - `test_comment_then_continued_commit_denies_on_main`: rows 13 and 16 (pin). Rows 14 and 15 are an accepted bypass (silent on base too), not asserted.
  - `test_real_continuation_of_plan_item_push_stays_silent`: row 12 plus N14 continuation controls.
  - `test_multiline_without_backslash_newline_unchanged` (N14): multi-line commands without a backslash-newline are silent on main and on agent/x.
  - `test_five_megabyte_command_without_backslash_newline_is_one_pass` (L21): three 5 MB shapes, each silent in < 3 s.
- Sentinel tests (`VerifyRequiresTestsRunTest`):
  - `test_sentinel_name_in_other_module_fails` (N17/I1).
  - `test_sentinel_text_in_skip_reason_fails`: another test's skip reason quotes the sentinel, or the sentinel is skipped with 'not ok'.
  - `test_sentinel_line_is_the_exact_full_line`: pins the SENTINEL that the passing controls print.
- `scripts/verify.sh fast` -> FAILED (failures=30), 97 tests, no errors or skips. Evidence: `docs/evidence/harness-followups/red-rework4.txt`.
- RED reasons (all expected):
  - 24 = 12 M6 rows (1-10, q1, q2) x 2 modes, each `None != 'deny'`: text (b) splits the push line.
  - 6 sentinel subtests: verify prints PASS because the unanchored grep matches.
- Already green, as pins: row 11, rows 13/16, the N14 controls and L21 (no-jq was at most 2.3 s with two passes).
- Iteration 2 of this RED: in iteration 1 the windows-paths fixture was 4.4 MB. That was a test bug, now fixed.
- Next (developer):
  - Hook: in `text_b`, backslash-newline becomes a space. Build `text_b` only if `base` contains a backslash-newline.
  - Update the header and the ADR wording.
  - verify.sh: anchor the sentinel grep to the full line `^...SENTINEL...$`.
  - Host check: run q1 and q2.

## 2026-10-18 — developer: rework 4 GREEN (security M6, L21, I1; review N17)
- Changed only `scripts/hooks/block-main-commit.sh` and `scripts/verify.sh`; no tests edited.
- Hook: text (b) now turns backslash-newline into a space (M6); the loop runs over a `texts` array, and (b) is built only when `base` contains a backslash-newline (L21). Header and step 2 comments cite M5/M6/L21.
- verify.sh: sentinel grep anchored to the full line (`^...\) \.\.\. ok$`), CR stripped from the log first (N17/I1).
- `scripts/verify.sh full` -> PASS, Ran 97 tests OK, smoke pass. Evidence: `docs/evidence/harness-followups/green-rework4.txt`. All 30 RED failures green.
- Host check (Git Bash, no jq, payload files): Table M rows 1-11, q1, q2 DENY on agent/x; rows 12 and benign silent; main rows 13, 16, c1 DENY. Evidence: `hook-live-host-r4.txt`.
- Host timing (no jq, ~6 MB payload JSON): no backslash-newline 4.9 s, with one 6.8 s. Under the 10 s goal but not "well under": the host is slow on sed -z over 5 MB. Evidence: `hook-timing-host-r4.txt`.
- Not staged or committed.

## 2026-10-18 — tester: rework 5 RED (review N19, N21)
- Edited only `tests/test_harness_followups.py` (VerifyRequiresTestsRunTest).
- N19: new `test_sentinel_followed_by_large_output_passes`. The fake test.sh prints the sentinel, `Ran 1 test`, OK, then about 320 KB of further output. It expects exit 0 and PASS in fast and full, run 5 times.
- N21: `test_sentinel_line_is_the_exact_full_line` now builds the line from `tests.test_sentinel.TopLevelSuiteSentinelTest('test_top_level_unit_suite_ran').id()`, reads the single-quoted sentinel ERE from scripts/verify.sh, checks that it is anchored with `^`/`$`, and runs it through `re`: it must match the line, and must not match the line with a prefix or a suffix added.
- `scripts/verify.sh fast` -> FAIL, Ran 98 tests, failures=10: all 10 are N19 subtests (5 attempts x fast/full), and each reports "sentinel ... did not report ok". That is the SIGPIPE false-FAIL (`tr | grep -q` under pipefail). N21 is green (a pin). Evidence: `docs/evidence/harness-followups/red-rework5.txt`.
- Next (developer): verify.sh line 38. Grep the log file directly with no pipe, allowing an optional trailing CR (`...ok\r?$`), or drop -q. Keep exactly one single-quoted pattern starting with `^` that names the sentinel, because the N21 test parses it.

## 2026-10-18 — developer: rework 5 GREEN (N19, N21)
- Edited only scripts/verify.sh. The sentinel check now reads the log directly: `grep -Pq '^…\) \.\.\. ok\r?$' "$log"`. There is no pipe, so no SIGPIPE under pipefail.
- Why -P and not -E: in GNU grep -E, `\r` matches a literal "r", not CR. -P and Python `re` both read `\r` as CR, and the pattern is still the one anchored single-quoted `^…$` that N21 parses.
- Note for reviewer: this needs grep with PCRE support. The gates image passed, so it has it.
- `scripts/verify.sh full` -> PASS, Ran 98 tests, OK, smoke pass. Evidence: `docs/evidence/harness-followups/green-rework5.txt`.
- Not staged or committed.

## 2026-10-18 — orchestrator: gates passed after rework 5 of 5
- Review APPROVED (`review-rework5.md`), security PASS 0 crit/high/med (`security-rework5.md`), orchestrator `verify.sh full` 98 OK + smoke (`orchestrator-verify-full.txt`); read verify.sh, test.sh, ci.yml.
- Open, non-blocking (next harness touch): review N4, N10–N13, N15c (verify.sh header, optional CR), N20, N22–N24; security L21 (host 5 MB w/ backslash-newline ~9.5 s of 10 s), L24 (on-main bypass list incomplete; AGENTS.md "denies any commit/push" too strong), I2 (`grep -P` not in ADR); test.sh header still says testcontainers (Q30 pending).
