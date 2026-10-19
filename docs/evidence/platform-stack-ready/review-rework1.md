# Review: platform-stack-ready (2b), rework round 1 of 5

- Reviewer, 2026-10-19. Base fe2f101, uncommitted tree. Read: review.md (round 0), handoff sections from "orchestrator: rework round 1" to "developer: rework 1 FINAL GREEN", green-rework1-final.txt, requirements F1 / M-1 / L-11 / L-12 criteria.
- Diff read: engine/{worker,readiness,telemetry,startup,llm/client}.py, scripts/{verify,smoke,lint}.sh, the hook comment, tests/support.py, tests/test_engine_{startup,tracing_guard}.py, tests/test_stack_{worker,readiness,ready_compose,model_keys}.py, tests/integration/test_stack_ready.py.
- Freshness: no file under engine/, scripts/, tests/, docker/, compose, pyproject or uv.lock is newer than green-rework1-final.txt (00:10:01 local).
- Mutants: run in a scratch copy (no .env, no .git) with `docker run --network none` on the ke-gates image. Each mutant was applied with perl and run on its target modules, then restored. Baselines were green (42 Python tests, 115 script tests). The scratch copy is deleted and no ke-gates container is left.

## Verdict: CHANGES REQUESTED (1 blocking)

## Blocking

**R1-B1. The L-12 symlink refusal is untested: mutant L12b survives (PS-2.23 *Any case, modules, no links*).**
- Mutant L12b replaces `if [ -L "$file" ]; then` with `if false; then` in scripts/lint.sh. It SURVIVED tests.test_stack_scripts, tests.test_stack_model_keys and tests.test_harness_port (115 tests).
- Why it survives: every case in `test_lint_fails_on_a_symlinked_script` links to a target that has a finding of its own (`Invoke-Expression $args[0]`, `rm -rf $1/tmp`). Without the rule, shellcheck or PSScriptAnalyzer still fails on the target, so the test passes.
- Concrete check in the gates image: with the rule removed, a symlink `scripts/l.sh -> ../outside/clean.txt` (a clean target) gives `lint: PASS`, rc 0. With the rule in place it gives rc 1, `lint: FAIL (a script is a symlink: refused: scripts/l.sh)`.
- The criterion says the symlink fails "whether its target is inside or outside scripts/ ... it never passes". The test does not prove that.
- Fix (tests only): add symlink cases with clean targets, one inside and one outside scripts/, for both .sh and .ps1. Assert rc != 0 and that the output names the symlink refusal.

## Re-run of round-0 survivors and the rework blockers

| Mutant | Round 0 | Now | Note |
|---|---|---|---|
| MP1 probe via `httpx.get` (bypasses the guard) | SURVIVED | KILLED (1 failure, 7 errors) | R-B2 |
| RZ9 probe `raise_for_status()` removed | SURVIVED | KILLED (4 failures) | R-B2 |
| MP2 probe `timeout=` removed | SURVIVED | KILLED (1 failure) | R-B2 |
| WK3 `rq.SimpleWorker` -> `rq.Worker` | SURVIVED | KILLED (2 failures) | N2 |
| LN1 lint open-bracket alternative removed | SURVIVED (equivalent) | KILLED | lone-bracket case |
| SM6 smoke cleanup `rc=1` promotion removed | SURVIVED | SURVIVED | N1, not in rework scope; still open |
| RZ10a/b ConnectError TimeoutError/OSError cause branches removed | SURVIVED | SURVIVED | N3, not in rework scope; still open |

- R-B1: RB1a (a `set` to an external host in phoenix.conf.template) and RB1b (`proxy_pass http://${KE_MODEL_UPSTREAM}` in api.conf.template) are both KILLED by test_stack_ready_compose. Resolved.
- R-B2: resolved (above).
- R-B3: removing the second `check_healthy` (SH2) is KILLED (3 failures), and removing the first (SH1) is KILLED. green-rework1-final.txt lines 921-929 show all 7 services healthy after "ready again after postgres restart". Resolved.
- R-B4: resolved.
  - R6: both tests are rewritten under `isolated()` with a local-collector control. Mutant R6-remote (choose_exporter returns an exporter for a non-local endpoint) is KILLED by test_configure_tracing_attaches_nothing_for_non_local. The prod twin is refused upstream by check(), as designed.
  - N9: the `verify_provider` parameter is gone, and startup no longer computes service_names. No caller passes an argument; the only remaining `verify_provider([])` is in an archived platform-config evidence script, which is not executed.
  - ci-fix N1: the comment is present. The L21 test counts `bash -x` trace lines (TRACE_BUILT/TRACE_JUDGED, anchored to `+`), so a comment cannot change the count.

## New code (focus 2)

- **Worker JSON plus allowlist.**
  - A refused job's function is neither resolved nor called. `Job.func_name` only JSON-decodes `job.data` (`_deserialize_data`, rq 2.12.0) and imports nothing. `handle_job_failure` touches no `job.func`.
  - Mutants WK6 (no allowlist), WK7 (prefix `engine.jobs.` allowed), WK8 (no `return` after the refusal) and WK9 (pickle serializer) are all KILLED.
  - Nit N-R1: "unresolved" is not pinned by a test. Mutant WK5 (`_ = job.func` before the check) SURVIVED, because the tests patch the target and assert only that it is not called. Resolving an arbitrary dotted path imports that module, and its import-time code runs. Add an assertion that `rq.utils.import_attribute` (or `importlib.import_module`) is not called for a refused job.
  - Nit N-R2 (for security): a job whose data is not JSON (for example pickle from a default `rq.Queue`) raises `DeserializationError` from `execute_job`. Checked in the gates image. The RQ work loop catches it with a bare except, logs "found an unhandled exception, quitting..." and the worker exits. Nothing is unpickled, so M-1 holds, but one bad job stops consumption until compose restarts the worker. Consider catching DeserializationError in `execute_job` and failing the job with the fixed reason.
  - Nit N-R3 (for security): the refusal goes through `handle_job_failure`. That path still honours data the job carries: `job.should_retry` requeues a refused job up to its `retries_left`, and `job.send_webhooks(FAILED)` makes urllib requests to job-supplied URLs, outside GuardedTransport. The worker is on `backend` only, and anyone who can write Valkey can already reach the same in-stack hosts, so this gives no new privilege. Record it with the M-1 network-side carry-in.
- **F1.**
  - Mutant F1a (the `model_upstream` condition removed) is KILLED (2 failures). The spec is met.
  - Nit N-R4: mutant F1b (the `base_url is None` condition removed) SURVIVED. With the upstream set and the base URL null, the reason becomes `error:ValueError` instead of `not_configured`. No I/O happens either way (probe raises first), so this changes only the reason word. Add that case.
- **L-11 scrub in verify.sh.**
  - `compgen -e | grep '^KE_'` runs after the two model keys are read and before any stage. It lists no test commands: test_verify_sh_has_no_inlined_commands is green, and the forbidden words are absent from the body.
  - Mutant L11a (scrub removed) is KILLED (9 failures). Mutant L11b (scrub only `KE_STORES*`) is KILLED (6 failures).
  - The B6 VerifyHostHalfTest and model-keys tests are green (115 OK, baseline).
  - The 14 "variable is not set" compose warnings in green-rework1-final.txt also appear in round-0 green-full.txt. They come from smoke's no-.env resolve check, not from the scrub.
- **L-12 lint.**
  - Mutant L12a (back to `-name '*.ps1'`) is KILLED (4 failures). Mutant L12c (symlinks dropped from both finds) is KILLED (3 failures).
  - The symlink rule itself is untested (R1-B1).
  - Nit N-R5: `find` without `-L` does not descend into a symlinked directory. A `.ps1` under `scripts/sub -> elsewhere` is neither linted nor refused. This is outside the criterion text. Consider `find scripts -type l` (any symlink) as the refusal.
- **smoke `check_healthy` twice.** The function runs at top level, so its `exit 1` ends smoke, and the EXIT trap still tears down a project smoke launched. Both calls are pinned (SH1, SH2 KILLED). It also runs on the "already running, SKIPPED" path, which is correct.

## Test integrity (focus 3)

- **`support.BUILD_PROVIDER_ERROR` assertion replaced by a comment: legitimate.** The variable and the setup_tracing fallback are both gone. An import failure of `build_provider` now errors every module that imports tests/support.py, which is louder than the old single assertion. The test keeps `assertIs(trace.get_tracer_provider(), support.PROVIDER)` and the unpatched `verify_provider()` call, which would refuse a provider that the engine did not build. Nothing is weakened.
- **Integration JSON enqueue: legitimate.** The producer must match the worker's JSONSerializer (M-1). The assertions (status `finished`, counter 1) are unchanged. A pickle producer now fails closed, which is the intended behaviour (see N-R2 for how it fails).
- **`verify_provider()` arity change: legitimate.** The argument was dead (`del service_names`). Every call site was updated, and the identity tests (decoy refused, engine-built accepted) are unchanged. mypy is clean in the final run.

## Coverage (focus 4)

readiness.py at 70% (missing lines 78-81 and 176-231). No untested security path is hidden there:
- 176-231 is the `--wait-for` CLI (`_met`, `_valid_condition`, `_fetch`, `main`). It is exercised by four subprocess tests (ReadinessCliTest), which coverage does not follow:
  - proxy ignored (RZ8 killed in round 0);
  - the polled route;
  - the `--within` bound;
  - unreachable, with no traceback;
  - usage errors (exit 2).
- The one branch with no test is `ConfigError` -> exit 2. I probed it in the gates image with marker values in KE_API__LISTEN_PORT and KE_ENV, and with an empty postgres password. The output names keys only and leaks no value, as loader.py guarantees.
- The URL is fixed to 127.0.0.1. The failure message echoes only the classified `/readyz` body or `unreachable (<ClassName>)`.
- Lines 78-81 are the RZ10 vocabulary gap (N3, still open, not security).
- Nit N7 from round 0 still stands: run `main()` in-process, or set COVERAGE_PROCESS_START, so the number reflects reality.

## Still open from round 0 (nits, not re-raised as blocking)
N1/SM6, N3/RZ10, N5, N6, N8, N9 (KE_SMOKE_OWNS_PROJECT exported for the whole host half), N11 (.env.example comment), N12 (port 5432 hard-coded at integration line 105), N13 (untracked docs/knowledge-engine-claude-code-prompt.md must not be staged), N14.
Pending by ruling, so they block commit but not this review: the C1 CI timeout together with the round-0 N10 ci.yml comment, the 1 MB watch, and the PS-2.21 recorded run with the model host reachable.
