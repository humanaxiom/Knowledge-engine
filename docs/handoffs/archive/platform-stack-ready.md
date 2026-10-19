# Handoff: platform-stack-ready

Outcome metric moved: neither directly. Readiness, worker jobs and store
failure smoke make the stack operable, a precondition for reviewers.
Spec: `docs/requirements.md` § platform-skeleton, 2b scope: PS-2.5, 2.6, rest of 2.7, 2.8, 2.13, 2.18, PS-3.4 measurement.
Design: `docs/architecture.md` §2.2, §2.4, ADR-KE-009/010/011.
Base: `agent/platform-stack-up` @ fe2f101. Previous handoff: `docs/handoffs/archive/platform-stack-up.md`.

## 2026-10-19 — orchestrator: item opened
- Carry-ins (see the archived 2a handoff):
  - security L-9 (teardown leaves its own profile/one-off containers, exits 0) and L-10 (`[ ]` in .ps1 names escapes PSScriptAnalyzer);
  - review nits R2-N1–N9, rework-1 N-1/2/4/5/7/8, round-0 N3–N6, N8–N11, review-ci-fix N1/N2;
  - the 1 MB timing-margin watch;
  - security L-5, L-8;
  - model upstream in local verify (umbrella ruling: pass only KE_MODEL_UPSTREAM and KE_EGRESS_ALLOWLIST from caller env or the operator `.env`).
- PS-3.4 baseline: CI full = 274 s on ubuntu-24.04 (`docs/evidence/platform-stack/ci-run-0f2821c.txt`).
- Next: the analyst confirms 2b criteria and triages carry-ins (which are in scope vs deferred); the architect checks the design for readyz, worker jobs (RQ on Valkey) and store-down smoke. Then TDD.

## 2026-10-19 — analyst: 2b criteria confirmed, carry-ins triaged
- Touched only `docs/requirements.md` § PS-2 and `docs/open-questions.md`. Gate-depth list (fast/full/manual) is under PS-2 "2b gate depth".
- Tightened: PS-2.5 (200/503, no credential in reasons, bounded, `test_readyz_is_traced`, postgres identity drift test = round-0 N4); PS-2.6 (status `finished` + counter 1, `test_worker_job_is_traced`); PS-2.7 "not configured" skip reason; PS-2.8 store stop/start + `test_smoke_stops_and_restarts_a_store`, "who launches" per ADR-KE-009 (round-0 N11); PS-2.13 names the two keys.
- New: PS-2.21 model upstream in local verify (`test_verify_full_passes_model_upstream_keys`, `test_verify_full_takes_no_other_env_key`, one recorded run with aria-gb10-2 reachable); PS-2.22 L-9; PS-2.23 L-10 + rework-1 N-1/N-2/N-5 + R2-N6; PS-2.24 R2-N1–N5, ci-fix N2, round-0 N3.
- Placement table under PS-2 "Carry-ins from platform-stack-up". Deferred to platform-offline: L-5, L-8, rework-1 N-7, round-0 N6/N8. rework-1 N-3 and round-0 N5 already done in 2a; N-6 proposed closed.
- Architect: PS-2.22 must stay consistent with F3 (no `--profile '*'`); R2-N7 (fake vs §2.4 names) is yours or the tester's.
- Size: one branch; fallback split ready-then-hardening and TDD order under PS-2 "2b size". A fresh Windows run is needed (Q34).
- Open: Q35 (model-key precedence/which `.env`/L-5 interplay), Q36 (which CI run sets the timeout). Both assumed, neither blocks RED.
- Evidence: `docs/evidence/platform-stack-ready/analyst-plan-verify-fast.txt` (verify fast PASS).

## 2026-10-19 — orchestrator: rulings on analyst plan
- One branch, with the fallback split as written. rework-1 N-3 is already done in 2a. N-4 goes to security at the 2b audit.
- Q35: the caller env wins. Only the repo-root `.env` counts. Until platform-offline (L-5), "no other key" covers env and compose args only.
- Q36: CI stays at 20 min until the first green 2b CI run; then a follow-up commit sets the measured duration + 50%.
- L-5 and L-8 are deferred to platform-offline. rework-1 N-6 is closed (superseded by the network-inspect proof).

## 2026-10-19 — orchestrator: rulings on architect plan (S1, C1, W1)
- S1: smoke tears down only a project that smoke itself launched; it never stops an operator's live stack.
- C1: per Q36, CI stays at 20 min until 2b's first green CI run is measured; then measured + 50% in a follow-up commit.
- W1: approved. The worker entrypoint tests patch `engine.worker.run`; the verify B6 temp tree gains an `env_value.sh` stub (cite W1).
- psycopg LGPL is acceptable (open source, dependency not modified); security confirms the licence at the pin.
- The analyst adopts the architect's *-marked test names, the `unreachable`/`not_configured` vocabulary and the `engine.jobs.noop` path.

## 2026-10-19 — tester: RED written (fast + integration)
- `verify.sh fast` RED as expected: 389 run, 78 failures, 34 errors, all in new, W1-retargeted or PS-2.23-extended tests; no 2a test regressed (`docs/evidence/platform-stack-ready/red.txt`). Integration (`tests/integration/test_stack_ready.py`) runs only in full.
- New: `tests/test_stack_{readiness,worker,ready_compose,model_keys,model_skip,ready_docs}.py`, `tests/integration/{model.py,test_stack_ready.py}`. The skip helper (`require_model_host`, `@model_calling`) is written. Extended: test_stack_scripts (L-9 sh/ps1, L-10, smoke S1/Q37 order, R2-N1–N4, N-1/N-2/N-5, R2-N6/N9, W1 `env_value.sh` stub), test_stack_entrypoints (W1 `engine.worker.run`, R2-N5), hook (ci-fix N2), hardcoded (round-0 N3), startup (PS-2.18). `tests/fake_docker.py`: model keys in config, leftovers, `ps -q`, Internal flag, FAIL_NTH.
- Seams the developer must keep: probes reached via `socket.create_connection`, `psycopg.connect`, `neo4j.GraphDatabase.driver`, `redis.Redis`, `ModelClient.probe`; `engine.api.get_settings`; smoke checks "already running" with `compose ps -q` (or `docker ps -q`) before `launch.sh`; teardown lists with `--filter label=com.docker.compose.project=<p>`.
- PS-2.24: every case is RED against its surviving mutant and green on the tree (10/10 killed): `docs/evidence/platform-stack-ready/red-ps-2-24-mutants.txt`. The ci-fix N2 pin and the round-0 N3 `_LISTEN` port rule are test-side and already applied. `test_ci_job_has_timeout` and the identity test are green now (only drift guards, C1).
- Fixture-only changes, with assertions unchanged: B6 `env_value.sh` stub (W1), smoke launch/teardown stubs, `TeardownScriptTest` on `fake_docker`.
- For the orchestrator: under Q37, `verify.sh full` launches before smoke, so smoke sees a running project and skips the postgres stop/start. CI would then never exercise it. This needs a ruling, for example verify signalling that it owns the project.
- Ruled (`KE_SMOKE_OWNS_PROJECT=1`): RED added. Smoke with the flag runs the stop/restart and no teardown; the flag with no running project fails naming the flag; the verify host half passes the flag to smoke for its `ke-verify-*` project (B6 stub logs `owns=`). Re-run: 393 run, 81 failures, 34 errors, same `red.txt`.

## 2026-10-19 — developer: GREEN (fast + full), nothing staged
- Done: units 1-10. New: `engine/readiness.py`, `engine/jobs.py`, `scripts/env_value.sh`; changed: api, worker, llm/client (`probe`), startup (PS-2.18), compose (`x-model-env`, worker depends_on), app.Dockerfile (N11), smoke/teardown(.sh/.ps1)/lint/verify.
- Deps added (pyproject + uv.lock): psycopg[binary] 3.3.6 (LGPL-3.0), neo4j 6.4.1 (Apache-2.0), redis 8.1.0 (MIT), rq 2.12.0 (BSD-2); transitive croniter 6.2.4, pytz, python-dateutil, six, tzdata.
- `verify.sh fast`: 393 tests OK after one mypy fix (lambda in `check_all`). `verify.sh full`: PASS 147 s, `docs/evidence/platform-stack-ready/green-full.txt`.
- Real in full: 8 integration tests (readyz x3, worker noop finished=1) and the smoke postgres stop/restart. The only skip is `test_readyz_reports_reachable_model_host` (no `KE_MODEL_UPSTREAM` here). The PS-2.21 recorded run with aria-gb10-2 is not done.
- `verify.sh` calls `bash scripts/env_value.sh`, so it does not depend on the +x bit. New files that still want `git update-index --chmod=+x`: `scripts/env_value.sh`.
- Not done: Windows proof (pwsh teardown run on a real daemon), CI timeout (Q36/C1), CLAUDE.md (documenter).

## 2026-10-19 — orchestrator: rework round 1 of 5 (review CHANGES REQUESTED 4 blocking; security PASS 1 medium; Windows proof PASS w/ F1)
- In scope:
  - review R-B1 (write `test_gateway_only_external_upstream_is_model_upstream`), R-B2 (probe tests: guard, 401→auth_failed, 500→error, timeout), R-B3 (smoke health loop AFTER the final ready; PS-2.8 stands), R-B4 (R6 vacuous tests, round-0 N9 dead code + support.py fallback, ci-fix N1 hook comment);
  - Windows F1 (`not_configured` when KE_MODEL_UPSTREAM is empty, even though the base URL points at the gateway);
  - security M-1 engine side (RQ JSONSerializer; the worker refuses any job not in `engine.jobs.__all__`), L-11 (verify drops caller `KE_*` except the two model keys before compose), L-12 (lint: case-insensitive .ps1 and .psm1; fail on symlinked scripts), L-13 (psycopg `gssencmode=disable`);
  - review nits: SimpleWorker pinned by test; a lone-`[` lint case.
- Deferred: M-1 network side (valkey on its own network plus password/ACL; compose change) → auth-audit carry-in, before any ingest exposure. Other review nits are in review.md.
- Windows proof stays valid: this round touches only gate-only bash scripts and engine code, not the PS launch path, compose or Dockerfiles (Q34 scope ruling).
- Then: C1 CI timeout follow-up, round-0 N10 ci.yml comment, the PS-2.21 recorded run against aria-gb10-2:11434.

## 2026-10-19 — tester: rework 1 RED written
- `verify.sh fast` RED as expected: 413 run, 27 failures (all new tests), no error, no prior test regressed (`docs/evidence/platform-stack-ready/red-rework1.txt`).
- RED: F1 `test_readyz_model_host_not_configured_without_upstream`; M-1 `test_worker_uses_json_serializer`, `test_worker_refuses_a_job_outside_engine_jobs` (platform.node, os.getcwd, engine.jobs.traced_job); L-11 `test_verify_full_takes_no_caller_ke_key_but_the_model_keys`; L-12 `test_lint_covers_upper_case_ps1_and_psm1`, `test_lint_fails_on_a_symlinked_script`; L-13 `test_postgres_probe_disables_gss_encryption` + static scan; R-B3 `test_smoke_checks_every_service_healthy_after_the_store_is_back`, `test_smoke_fails_when_a_service_is_unhealthy_after_the_restart`.
- Green guards (the code is already right): R-B1 `test_gateway_only_external_upstream_is_model_upstream` (+ scanner self-check); R-B2 `ModelProbeTest` x4 (MP1/RZ9/MP2 killed by an in-process mutant check); `test_worker_is_a_simple_worker` (WK3); lone-`[` lint case; R6 tests rewritten under `isolated()` with local-collector controls (now fail when the exporter path is skipped).
- Seams: worker built by `engine.worker.run` (captured via `BaseWorker.work`); a job reaches its function through `execute_job(job, queue)`, so refuse there or below. F1 keys on `settings.models.model_upstream`. The probe is reached via `httpx.HTTPTransport` (MockTransport) and `EgressPolicy.require`.
- Contradiction (F1, orchestrator ruling in this handoff): `_settings()` in test_stack_readiness and integration `test_readyz_ready_without_model_host` now set KE_MODEL_UPSTREAM; integration `test_readyz_reports_each_dependency` asserts `not_configured` when it is empty (full only). The analyst should record F1 in PS-2.5.
- Not done here (developer): R-B4 round-0 N9 dead code/support.py fallback, ci-fix N1 hook comment (no test asked).

## 2026-10-19 — developer: rework 1 GREEN (one test blocked by a test defect)
- Done: F1 (readiness: not_configured when model_upstream empty), M-1 (`AllowListWorker(SimpleWorker)` + JSONSerializer, refusal in `execute_job` via `handle_job_failure`), L-11 (verify unsets caller KE_* after reading the two model keys), L-12 (lint -iname ps1/psm1, symlink fail), L-13 (gssencmode=disable), R-B3 (smoke `check_healthy` before proxies and after final ready; the RED #2 query needs both), R-B4 (hook comment; startup/telemetry no longer compute/pass service_names).
- `verify_provider` keeps an optional ignored `service_names` because tests still call `verify_provider([])`; tester can drop those args, then dev removes the parameter. `tests/support.py` fallback not touched.
- `scripts/verify.sh full` (193s, exit 1; `docs/evidence/platform-stack-ready/green-rework1.txt`): 413 run, 1 failure, so the smoke half has not run live yet.
- BLOCKER (test defect): integration `test_worker_consumes_noop_job` enqueues with a default (pickle) `rq.Queue`; M-1 workers read JSON, so the job stays queued. Fix is in the test: `rq.Queue("default", connection=..., serializer=JSONSerializer)`.

## 2026-10-19 — tester: contradiction resolution (criterion 10, ruling M-1)
- Tests only: integration noop enqueue uses `JSONSerializer` (M-1); `verify_provider()` called with no args (N9, dev may now drop the param); dead `tests/support.py` setup_tracing fallback and the `BUILD_PROVIDER_ERROR` assertion removed (build_provider exists since platform-stack-up).
- `scripts/verify.sh fast` PASS, 413 tests OK (`docs/evidence/platform-stack-ready/tester-contradiction.txt`); integration fix proves only under `verify.sh full`, next.

## 2026-10-19 — developer: rework 1 FINAL GREEN
- Removed the ignored `service_names` param from `engine.telemetry.verify_provider` (N9); no caller passes it.
- `scripts/verify.sh full` PASS, 152s, exit 0: 413 unit OK; integration 8 run OK (1 skipped: reachable model host, no upstream); `docs/evidence/platform-stack-ready/green-rework1-final.txt` (worker JSON noop line 852, smoke health after final ready lines 921-929, postgres stop/restart 914-921, `test_readyz_reports_each_dependency` line 850).

## 2026-10-19 — tester: PS-2.21 recorded model run (aria-gb10-2:11434, allowlist aria-gb10-2; keys in command env only)
- Preflight `/v1/models` 200. Two runs of `verify.sh full` with the keys: 413 unit OK; integration 8 run OK, 0 skipped; `test_readyz_reports_reachable_model_host` RAN and passed (asserts readyz `model_host` = ok/required False); smoke PASS (`docs/evidence/platform-stack-ready/model-run-aria-gb10-2.txt`, attempt 1 `...-attempt1.txt`).
- Both runs exit 1 at teardown only: a foreign one-shot `gates-it` container (cranky_nash, elastic_shaw; another agent's mutation check, mounting a scratchpad `mut` dir) was started inside the live `ke-verify-*` project during teardown. Not a code defect; rerun when no other agent borrows the verify project, or make verify's project name unguessable to peers (orchestrator call).

## 2026-10-19 — orchestrator: rework round 2 of 5 (review 1 blocking; security PASS; PS-2.21 model run done)
- PS-2.21 evidence: `model-run-aria-gb10-2.txt`. Integration 8/8 ran (no skips); `test_readyz_reports_reachable_model_host` passed against aria-gb10-2:11434. verify exited 1 only at teardown, where L-9 correctly reported a foreign `gates-it` container another agent ran inside the live `ke-verify-*` project. Accepted as the PS-2.21 record.
- In scope: review R1-B1 (symlink tests with clean targets), security L-15 (refuse ANY symlink under scripts/ and docker/, dirs included; `.sh` case-insensitive), review N-R1 (pin "refused job's function is never resolved"), N-R4 (missing base_url → not_configured).
- Deferred to the M-1 network unit (first unit of ingest-ledger, Q39): security M-2 (RQ callbacks/webhooks bypass the allowlist), L-14 / review N-R2 (bad job stops the worker), review N-R3. Review nits N-R5 (subsumed by L-15), SM6, RZ10 and round-0 N1/N3/N5/N6/N8/N9/N11–N14 are recorded.
- Agents must run scratch work only under their own project names, never inside a live `ke-verify-*`.

## 2026-10-19 — tester: rework 2 RED (R1-B1, L-15, N-R1, N-R4)
- New tests: LintScriptTest `test_lint_refuses_a_symlink_to_a_clean_script` (R1-B1), `test_lint_fails_on_a_directory_symlink_holding_a_finding`, `test_lint_refuses_any_symlink_under_scripts_and_docker`, `test_lint_shellchecks_upper_case_sh` (L-15); `test_worker_never_resolves_a_refused_jobs_function` (N-R1); `test_readyz_model_host_not_configured_without_base_url` (N-R4).
- `verify.sh fast`: RED, 14 failures, all L-15 subtests (dir symlinks not refused, non-script symlinks not refused, `*.SH` not shellchecked); 419 tests. Evidence `docs/evidence/platform-stack-ready/red-rework2.txt`.
- R1-B1/N-R1/N-R4 tests are green now (they pin existing behaviour) and kill L12b (4 fails), WK5 (3), F1b (1) in scratch copies: `red-rework2-mutants.txt`. Developer: refuse any `find scripts docker -type l`, naming "symlink" and the path; select shell scripts with `-iname '*.sh'`.

## 2026-10-19 — developer: rework 2 GREEN (L-15)
- `scripts/lint.sh` only: refuses ANY symlink under scripts/ and docker/ (`find scripts docker -type l`, message names "symlink" and path, exits before the tools); shell scripts selected with `-iname '*.sh'` (regular files); ps1/psm1 selection, wildcard/newline refusals and env-var passing kept.
- `scripts/verify.sh full` PASS, 146s, exit 0 (`docs/evidence/platform-stack-ready/green-rework2.txt`); the 14 red L-15 subtests are green. Nothing staged or committed.

## 2026-10-19 — documenter: docs updated
- README.md and docs/quickstart.md now describe /readyz (reason vocabulary, model_host not required), the allowlisted JSON worker, teardown leftover reporting, model keys in verify full (skip otherwise), smoke by hand, lint symlink refusal. Details: `docs/evidence/platform-stack-ready/documenter.md`.
- `verify.sh fast` PASS: `docs/evidence/platform-stack-ready/documenter-verify.txt`.
- Gaps: CLAUDE.md "What CI runs that verify.sh does not" model section is still unwritten here (out of my scope; test_stack_ready_docs expects it).

## 2026-10-19 — orchestrator: item closed + milestone Done check (platform-stack-ready)
- Pushed (human approved). CI green on 42547d0 (389 s job) and on 8c7d3d8 (timeout set to 10 min, 366 s job). Evidence: `ci-run-42547d0.txt`, `ci-run-8c7d3d8.txt`, `ci-timeout.md`. Doc-gate sections from the documenter/marketer are in `documenter.md` and `marketer.md`.
- PS-2.21 model run against aria-gb10-2:11434 is recorded (`model-run-aria-gb10-2.txt`).
- Outcome metrics: drafts reviewed n/a, ratified rules n/a (no data store yet). Not moved, by design: platform precondition.
- External blockers: Q18 branch protection (Adam Salah, no date); Q14 ratification owners (OWNER-TBD); Q38 compose models to pull on aria-gb10-2 (Adam Salah, agreed to pull).
- Carried forward:
  - to the FIRST unit of ingest-ledger (Q39): security M-1 network side (valkey network + password/ACL), M-2 (RQ callbacks/webhooks), L-14/N-R2 (bad job stops the worker), N-R3;
  - to the next lint touch: L-16;
  - to platform-offline: L-5, L-8, the ke-app image scan, psycopg licence notices.
  - Review nits are recorded in review-rework1.md and review-rework2.md.
- The profile path remains in pushed history of agent/platform-stack-up (0f2821c, fe2f101). The human declined a history rewrite.
