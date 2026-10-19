# Handoff: platform-stack

Outcome metric moved: neither directly. It makes the stack launchable
(compose services, health, gateway, launch scripts), which is a precondition
for any reviewer to act.
Spec: `docs/requirements.md` § platform-skeleton, PS-2.x. Design: `docs/architecture.md` §2.1–2.2, §2.4, ADR-KE-009 (F-A) and ADR-KE-011.
Umbrella: `docs/handoffs/platform-skeleton.md`. Base: `agent/platform-config` @ d26bec6.

## 2026-10-19 — orchestrator: item opened
- First, a plan step: the architect applies the port ruling (umbrella, 2026-10-19: `${KE_BIND_ADDRESS:-127.0.0.1}:${KE_…_PORT:-default}`; LAN exposure refused outside dev until auth-audit) and checks §2.4 against F-A (gates-it internal-only; model via the gateway). The analyst checks that the PS-2.x criteria match the design.
- Carry-ins: security M5 (identity-marker provider check) needs a test-suite plan, so the architect proposes one. The harness-followups test.sh header still mentions testcontainers. AGENTS.md L24 wording. PS-2.13 CLAUDE.md row.
- Then TDD, starting with `test_compose_services_have_restart_policy` (fast), then `test_gates_it_internal_only_and_no_socket` (fast) and `test_egress_allowlist_holds_with_network_access` (full); `test_socket_guard_blocks_outbound` was replaced under F-A.

## 2026-10-19 — analyst: PS-2.x checked against the rulings; carry-ins placed
- **Asked:** make PS-2.1–PS-2.13 complete, testable and consistent with the port ruling, F-A, Q31; add carry-in criteria; place M5 and the deferred nits; tag fast/full; scope check. Touched only `docs/requirements.md` § PS-2 and `docs/open-questions.md`.
- **Port ruling:** PS-2.2 now requires `${KE_BIND_ADDRESS:-127.0.0.1}:${KE_<X>_PORT:-default}:<container>` for every published port, no `:?` (`test_published_ports_use_bind_address_form`), compose defaults equal `.env.example` (`test_compose_port_defaults_match_env_example`), resolves with no `.env` (smoke, full), `.env.example` bind address loopback or unset. New **PS-2.14**: non-loopback `KE_BIND_ADDRESS` refused outside dev, `test_startup_refuses_non_loopback_bind_address` (fast) + `test_compose_passes_bind_address_to_app` (fast).
- **Architect, note:** §2.4 still says `${KE_…_PORT:?set in .env}`; PS-2.2 now contradicts it by ruling. §2.4 also says only `gateway` publishes, while `docker-compose.yml` publishes phoenix directly today. PS-2.2 does not decide that; keep §2.4 and the compose file consistent.
- **F-A:** PS-2.7 was already consistent; added `test_gateway_only_external_upstream_is_model_upstream` (fast) and a shared-internal-network check on `test_gates_it_internal_only_and_no_socket`.
- **Q31:** PS-2.9 Windows proof tagged manual (outside verify.sh) and given the evidence contents to check. The staleness rule I wrote is raised as Q34.
- **Carry-ins:** PS-2.15 test.sh header; PS-2.16 AGENTS.md L24 wording; PS-2.13 unchanged (already complete). **M5 here** as PS-2.17, but TDD on it waits for the architect's test-suite plan. R3/R4 → PS-2.18; N1–N5 → PS-2.19; N13 pyproject name → PS-2.20. R6 and N11 are here with no criterion (tester and reviewer). R5 is deferred to the first item that calls `complete()`. R7 is already done. L1c/L2/L3/L5/L7/I1 stay deferred. The placement table is in requirements under PS-2.
- **Gate depth:** every PS-2 criterion tagged; the Windows run is the only manual one.
- **Scope:** split proposed (not created): `platform-stack-up` (2a) / `platform-stack-ready` (2b); the table is in requirements under PS-2.
- **Orchestrator, fix:** line 12 above names `test_socket_guard_blocks_outbound`, which F-A superseded (PS-2.7 "Superseded wording"). Use `test_gates_it_internal_only_and_no_socket` (fast) and `test_egress_allowlist_holds_with_network_access` (full).
- **Open:** Q33 (where the bind refusal runs, given the gateway publishes even if api refuses; loopback set; dev warning), Q34 (Windows run staleness).
- **Evidence:** `docs/evidence/platform-stack/analyst-plan-verify-fast.txt`.

## 2026-10-19 — orchestrator: split + rulings Q33, Q34
- Split accepted:
  - 2a `platform-stack-up` (this branch, renamed `agent/platform-stack-up`): PS-2.1–2.4, the PS-2.7 mechanism, 2.9, 2.10–2.12, 2.14–2.16, 2.19, 2.20.
  - 2b `platform-stack-ready` (next branch): PS-2.5, 2.6, the rest of 2.7, 2.8, 2.13, 2.17 (M5), 2.18, and the PS-3.4 measurement.
  - This handoff serves 2a; 2b gets its own.
- Q33:
  - (a) build/launch scripts (bash and PowerShell) also refuse a non-loopback `KE_BIND_ADDRESS` outside dev before `compose up`, in addition to the api refusal;
  - (b) loopback means any address in 127.0.0.0/8, plus ::1;
  - (c) dev logs a warning naming the variable.
- Q34: accepted as the analyst proposed. The recorded Windows run must match the branch head, or no script, compose file or Dockerfile may have changed since it.

## 2026-10-19 — orchestrator: rulings on architect R1–R4
- R1: the architect's proposed test names are adopted.
- R2: confirmed. The socket-guard fixture is dropped (the internal `backend` network is the boundary); runtime proof is `test_gates_it_has_no_route_out`.
- R3: M5 (PS-2.17) moves into 2a as the FIRST unit. It uses option (c), the engine-owned `build_provider` plus a weak registry, and deletes the private-attribute inspection. The tester may flip `InstalledProviderTest` accepted shapes and `test_local_otlp_that_ignores_proxy_env_is_accepted` to "refused" and switch the controls to `build_provider` (stricter, cite this ruling).
- R4: confirmed. The gateway image has its own bind check (`10-ke-bind-check.sh`) as well as engine refusal 6, consistent with Q33a.

## 2026-10-19 — tester: 2a TDD RED
- **Asked:** failing tests for 2a in implementation order (M5 first), touching only `tests/`. **Evidence:** `docs/evidence/platform-stack/red.txt` (verify fast, verify full, and a supplementary integration-only run in `gates`).
- **Result:** `verify.sh fast` RED, 245 tests, 133 failures + 19 errors. Every failure or error is a new or R3-flipped test, and fails for a missing-behaviour reason. `verify.sh full` stops at the same unit run, so `tests/integration` runs only once fast is green.
- **Files:** `tests/support.py`, `test_engine_tracing_guard.py`, `test_engine_telemetry.py`, `test_engine_hardcoded.py`, `test_engine_deploy_files.py`; new: `compose_support.py`, `test_stack_compose.py`, `test_stack_bind_address.py`, `test_stack_carry_ins.py`, `integration/{__init__,stack,test_stack_up}.py`.
- **Unit 0, M5 (R3):**
  - `ProviderIdentityTest.test_provider_not_built_by_engine_is_refused` covers 4 shapes × 2 passing envs, with zero spans, zero exports and zero dials. `test_engine_built_provider_is_accepted` is the control.
  - Also added: `build_provider` resource/processors and not installing globally; private helpers deleted; `test_support_provider_is_engine_built`.
  - Flipped per R3: `test_accepted_shapes` → `test_formerly_accepted_foreign_shapes_are_refused`, plus `test_engine_built_shapes_are_accepted`. `..._ignores_proxy_env_is_accepted` → `..._is_refused_unless_engine_built`. The in-memory shape joins `FOREIGN`. The control `test_control_spans_do_reach_an_accepted_provider` now uses `build_provider`.
  - `support.py` calls `build_provider`. The import is guarded: until GREEN it falls back to `setup_tracing` and only `test_support_provider_is_engine_built` fails. Developer: the fallback becomes dead code; leave it, or remove it once green.
- **Contradiction resolved here (cite ADR-KE-011 ports amendment, §2.4):** removed `PhoenixDriftTest` (`test_compose_phoenix_defaults_match_config`, `test_phoenix_published_on_loopback_only`). Phoenix no longer publishes. Their assertions move to `test_published_ports_use_bind_address`, `test_compose_defaults_match_env_example` and the new `test_compose_phoenix_listen_port_matches_config`. The record is in the `test_engine_deploy_files.py` docstring.
- **Contracts the developer must meet (decided in tests):**
  - `Settings.bind_address`. Refusal 6 is `StartupRefused(setting="KE_BIND_ADDRESS")` for IPv4 values.
  - Per Q33b, `::1` is loopback, so IPv6 must parse. Non-dev `::` may be `ConfigError` or refusal, as long as it names the variable; dev `::` starts with a warning. This differs from §2.4's "IPv4 literal only" (the handoff ruling wins). **Architect, please reconcile.**
  - The gateway check also fails closed when `KE_ENV` is unset, and refuses `128.0.0.1`, `1127.0.0.1` and `127.0.0.1.example.com`.
  - `launch.sh` refuses based on `.env`, `KE_ENV_FILE` or process env, before any `compose up`. It is tested with a fake `docker` in a temp copy. Its `up` must carry `--wait --no-build`.
  - `teardown.sh` runs `down --remove-orphans`, and adds `-v` only with `--volumes`.
  - `test_compose_defaults_match_env_example` is strict: every `${VAR:-d}` must be in `.env.example` with the same value. Today it fails on `PHOENIX_PORT`.
  - The scanner gains `collect_files(root, paths)`; the contract is in the `ScannerWideningTest` docstring. The repo scan now uses git-tracked plus untracked-not-ignored paths.
  - N5 is RED on the test helper `LOOPBACK` in `test_engine_hardcoded.py:51`. Removing `0.0.0.0` there is part of GREEN, sanctioned by PS-2.19 N5.
- **Green at RED (guards, not proof):** `test_no_docker_socket_mounted`, `test_stack_services_have_no_bind_mounts`, `test_harness_default_collector_matches_env_example`, `test_docs_name_current_phoenix_port`, `test_configure_tracing_installs_an_engine_built_provider`, `test_loopback_or_unset_bind_address_passes_everywhere`, `test_n2` on `docker-compose.verify.yaml`.
- **Weak spot:** `test_launch_ps1_checks_bind_address` is static only (no pwsh in the gates image). PowerShell behaviour rests on the Windows run (Q31) and PSScriptAnalyzer.
- **Integration (full, gates-it):** `test_gates_it_has_no_route_out`, `test_egress_allowlist_holds_with_network_access` (includes a DR38 mutant) and `test_healthz`. Outside gates-it each fails with a named reason, never a skip (see `red.txt` §3). It reads `KE_GATEWAY_MODEL_LISTEN` from env, else `.env.example`, and the api port from `KE_API__LISTEN_PORT`, else `defaults.yaml`.
- **Out of 2a, not written:** PS-2.5, 2.6, 2.13, 2.18, `test_gateway_only_external_upstream_is_model_upstream`, `test_model_tests_skip_with_named_reason`, `test_no_model_calls_in_unit_suite`.
- **Re-RED after orchestrator follow-up (IPv4-only ruling; it supersedes the Q33b `::1` wording and the IPv6 contract bullet above):**
  - Bind-address tests now say `KE_BIND_ADDRESS` is IPv4 only, and loopback means 127.0.0.0/8.
  - `::`, `::1`, `fe80::1` and `[::1]` are a `ConfigError` naming the variable in every `KE_ENV`, dev included. Tested by the new `test_ipv6_bind_address_is_a_config_error_in_every_env`.
  - The gateway check and `launch.sh` exit non-zero for these in every env, dev included. Tested by the new `test_gateway_bind_check_rejects_non_ipv4_in_every_env` and the new launch cases.
  - N5 is fixed in the test helper: `0.0.0.0` is removed from `LOOPBACK`, and `test_n5_no_loopback_definition_includes_unspecified_address` is now green.
  - `verify.sh fast`: 247 tests, 168 failures + 19 errors, all expected. See section 0 of `red.txt`.
- **Next:** developer GREEN in unit order (M5 → compose/deploy → bind refusals → scanner → carry-ins), then `verify.sh full`, where integration first runs in gates-it.

## 2026-10-18 — developer: 2a TDD GREEN (no stage, no commit)
- `verify.sh fast` PASS (247 tests), `verify.sh full` PASS against a real stack: 247 unit + 3 integration in gates-it, host smoke. Warm-cache `full` took 56-61 s wall (`green-full.txt`; a cold pull and build is longer). Evidence: `docs/evidence/platform-stack/green-full.txt`, `green-fast.txt`.
- M5: `build_provider` + weak registry, private-attribute helpers deleted. `Settings.bind_address` (IPv4Address), refusal 6, `docker/gateway/10-ke-bind-check.sh`, `scripts/{build,launch,teardown}.{sh,ps1}`; `engine/api.py` (`/healthz`, fastapi+uvicorn via `uv add`); `pyproject` name `knowledge-engine`.
- Compose: gateway (edge+backend, the only publisher, long-syntax ports), api, worker, postgres, neo4j, valkey, phoenix, `gates`, `gates-it`; every image digest-pinned (`docker buildx imagetools inspect`). Overlay `docker-compose.verify.yml` resets ports. Listen ports 8100/8101/8102 (gateway), api 8080 via `KE_API_LISTEN`.
- Decisions: `worker` is an idle placeholder (same ke-app image, healthy) until 2b PS-2.6. `KE_API_LISTEN` replaces `KE_API__LISTEN_PORT` in `.env.example` (the port-range test matches `KE_*_PORT`). Build script does not check the bind address; only launch does. Host `smoke.sh` checks health and gateway to api/phoenix `/healthz`; launch-and-teardown standalone, readyz, store stop/start are PS-2.8 (2b).
- For the commit step: new scripts need `git update-index --chmod=+x` (Windows checkout; the 100755 mode matters in CI). `docker compose config` with no `.env` resolves but warns on unset `KE_ENV` and the two secrets (PS-2.2 smoke, 2b). Windows manual run (Q31) not done; pwsh refusal cases were hand-checked locally.

## 2026-10-19 — orchestrator: rework round 1 of 5 (review CHANGES REQUESTED 7 blocking; security PASS w/ 3 medium)
- Windows proof (Q31) PASS: `windows-proof.txt` (path redacted). B7b is satisfied; it must be re-run if scripts/compose/Dockerfiles change (Q34), so after this round.
- In scope:
  - review B1 (no-route-out must fail on timeout), B2 (worker runs `startup()`; api wiring tested), B3 + security L-1 (launch scripts read resolved values via `docker compose config`; a missing KE_ENV counts as non-dev, fail closed; N2 too), B4 (PS-2.2 "resolves without .env" smoke is back in 2a), B5 (`scripts/lint.sh` runs shellcheck + PSScriptAnalyzer inside the gates image, called by test.sh or verify full), B6 (fake-docker test of the verify.sh host half), B7a (`git add --chmod=+x` at commit);
  - security M-1 (accept only `type(p) is ProxyTracerProvider`; verify the global provider is the one built after install), M-2 (`backend` bridge `gateway_mode_ipv4=isolated`, Docker ≥ 28 stated in the quickstart; no-route-out test also checks the bridge gateway), M-3 (gateway entrypoint requires KE_MODEL_UPSTREAM empty or strict host:port on KE_EGRESS_ALLOWLIST; closes L-3), L-2 (registry checks identity with `is`);
  - review N7 (teardown failure reported).
- Deferred: review N3–N6, N8–N11; security L-5 (gates-it root + rw repo).

## 2026-10-19 — tester: rework 1 RED
- `verify.sh fast` RED: 295 tests, 64 failures + 2 errors, all new tests failing for missing behaviour (`docs/evidence/platform-stack/red-rework1.txt` §1). Full stops at units, so integration (B1 errno + M-2 bridge gateway) is unproven until fast is green.
- New: `tests/fake_docker.py` (answers `compose config` like compose: env files, dotenv forms, process env; `FAKE_COMPOSE_RESOLVED` override), `test_stack_scripts.py` (B3/L-1 sh + pwsh, B4, B5, B6, N7), `test_stack_entrypoints.py` (B2, M-3/L-3). Added to: `test_stack_compose.py` (N2, M-2, worker command, gateway allowlist env), `test_engine_tracing_guard.py` (M-1, L-2), `integration/test_stack_up.py`.
- Contracts: lint.sh is called by the verify container half before test.sh in both modes (§2.2). pwsh, shellcheck and a version-pinned PSScriptAnalyzer are in the gates image, and launch.ps1 is now tested behaviourally under pwsh. N7 means a non-zero exit plus a message naming teardown. The worker is `python -m engine.worker`: `main()` refuses before idling and idles via `signal.pause`/`time.sleep`. Every `docker/gateway/1x-*.sh` runs as an entrypoint check.
- Test-only fixture changes (no assertion weakened): `globals_patched` and `test_engine_telemetry.isolated` now return the installed provider after a set, as real OTel does (needed for M-1). `LaunchScriptTest` uses the new fake (B3). `VerifyRequiresTestsRunTest` gains a passing `lint.sh` stub (B5).
- Green at RED (guards): the B6 order/failure/signal/random-name/overlay tests. They kill reviewer mutants V1, V2, V3, V4 and V7 (§2). Also green: N2 `${KE_ENV}`, api `main` refusal with uvicorn mocked (kills W1), and the launch.sh loopback controls.

## 2026-10-18 — developer: rework 1 GREEN (no stage, no commit)
- `verify.sh fast` PASS (295 tests, lint PASS); `verify.sh full` PASS against a real stack, 80 s wall (`green-rework1.txt`, `green-rework1-fast.txt`).
- Done: M-1/L-2 (`type is`, identity, post-install check); `engine/worker.py` + compose command, api pragma gone; `11-ke-upstream-check.sh`; launch.sh/.ps1 on `compose config --format json`, Engine >= 28 check; smoke no-.env + loopback; `scripts/lint.sh`, gates image (pwsh 7.4.21 sha256-verified, PSScriptAnalyzer 1.25.0, apt shellcheck 0.9.0); verify calls lint; N7 exit non-zero.
- Decision: isolated bridge hands the first container `.1`, so the M-2 probe saw an RST from a stack container. Fix: `backend` ipam subnet 198.18.80.0/24 (benchmarking range) with ip_range upper half, so `.1` stays unassigned.
- Gaps: `tests/fake_docker.py` answers `docker version` with empty output, so scripts accept an empty engine version (non-zero exit or < 28 refuses). On Docker Desktop an internal network also times out at `.1` without `isolated`, so the M-2 probe cannot tell isolated from not here; kept `isolated` per design.
- Windows proof must re-run: launch/build/teardown/smoke/lint/verify scripts, compose, gates + gateway Dockerfiles changed.

## 2026-10-19 — orchestrator: rework round 2 of 5 (review CHANGES REQUESTED 2 blocking; security PASS; Windows proof r1 PASS)
- Windows proof after rework 1: PASS (`windows-proof-rework1.txt`); its F1 confirms R1-B1. It goes stale again after this round (Q34).
- Rulings:
  - R1-B1: option (ii). Drop the backend `ipam` subnet/ip_range. The M-2 runtime proof becomes a host-side check that `docker network inspect <project>_backend` carries `com.docker.network.bridge.gateway_mode_ipv4=isolated` (closes security M-4). The no-route-out probe keeps the ENETUNREACH requirement for outside hosts.
  - R1-B2 + security L-6: the version check requires a numeric Engine version ≥ 28; empty, garbage or a daemon error are refused. The fake docker gets `FAKE_DOCKER_ENGINE`.
- Also in scope: security L-3 (gateway entrypoint validates every substituted port as an integer 1–65535), L-7 (lint.sh passes paths as arguments, never in generated source), Windows F3 (teardown removes only its own project's default services), review N-3 (a port with no host_ip test).
- Deferred: review LN2/LN4/N-4/N-8, PS telemetry ordering; security L-5, L-8.

## 2026-10-19 — tester: rework 2 RED
- `verify.sh fast` RED: 319 tests, 123 failures (subtests), all new tests, expected reasons (`docs/evidence/platform-stack/red-rework2.txt`). Lint PASS.
- New: compose `Rework2ComposeTest` (R1-B1 no pool, static); `SmokeBackendIsolatedTest` (smoke must `docker network inspect <project>_backend`, isolated); launch Engine cases sh+ps1 (R1-B2/L-6); `GatewayPortCheckTest` (L-3, template-driven drift); L-7 lint filename (U+2018/2019/201A/201B red, U+0027 green); `Teardown{Sh,Ps1}ScopeTest` (F3). Fake docker: `FAKE_DOCKER_ENGINE`(+`_EXIT`), `FAKE_DOCKER_BACKEND_OPTIONS`, `FAKE_COMPOSE_PORTS`; supported inspect formats are in its docstring.
- Fixture changes, cited (no assertion weakened): launch `_launch` defaults `FAKE_DOCKER_ENGINE=29.5.2` (ruling R1-B2); gateway `_run_entrypoint` sets compose port defaults (L-3); integration M-2 probe skips a first address owned by a stack container (ruling R1-B1 (ii), ipam gone).
- Green at RED (guards): N-3 no-host_ip cases sh+ps1 (L4 mutant now killable), Engine 27.x and daemon-error refusals, valid-port acceptance, KE_MODEL_UPSTREAM injection. Integration not run (full stops at units).

## 2026-10-19 — developer: rework 2 GREEN
- `verify.sh full` (`green-rework2.txt`, 85 s): 318 of 319 pass; BLOCKER: stale `tests.test_stack_bind_address.TeardownScriptTest.test_teardown_keeps_volumes_unless_asked` line 333 asserts `--remove-orphans`, which ruling F3 forbids. Tester must drop that assert (I did not edit tests).
- Changed: docker-compose.yml (ipam removed), scripts/{smoke,launch,lint,teardown}.sh, launch.ps1, teardown.ps1, docker/gateway.Dockerfile, NEW docker/gateway/12-ke-port-check.sh (needs `git add --chmod=+x`).
- smoke: project from `config` `name:`; inspect `<project>_backend` isolated + Internal. launch: server version `^N.N.N$` and major >= 28.
- Live (units skipped): `green-rework2-live.txt` (29 s) build, launch, integration 3 OK, smoke PASS incl. real network inspect, teardown rc 0.
- Windows proof must re-run. No stage/commit done.

## tester: contradiction fix + final verify (2026-10-18)
- Criterion 10: removed the `--remove-orphans` assert in `TeardownScriptTest.test_teardown_keeps_volumes_unless_asked` (comment cites F3, architecture §2.4); `--volumes`-only-when-asked checks kept.
- `scripts/verify.sh full` -> PASS, 89 s, 319/319 unit + 3/3 integration OK, smoke pass incl. live `network inspect` (`<project>_backend` internal + isolated): `docs/evidence/platform-stack/green-rework2-final.txt`.

## 2026-10-19 — orchestrator: 2a gates passed after rework 2
- Review APPROVED (`review-rework2.md`); security PASS, 0 crit/high (`security-rework2.md`); Windows proof r2 PASS (`windows-proof-rework2.txt`).
- Carry-ins to platform-stack-ready (2b):
  - security L-9 (teardown leaves its own profile/one-off containers, exits 0; verify N7 misses it) and L-10 (`[ ]` in .ps1 names escapes PSScriptAnalyzer). Both touch scripts that 2b changes anyway, where the Windows proof re-runs.
  - review nits R2-N1–N9, rework-1 N-1/2/4/5/7/8, round-0 N3–N6, N8–N11.
  - security L-5, L-8.
  - model upstream in local verify (umbrella ruling).
- Commit: `git add --chmod=+x` on every new .sh (B7a).

## 2026-10-19 — marketer: changelog gate (platform-stack-up)
- **Asked:** CHANGELOG.md entry for 2a shipped, tested behaviour only; no figures; touch only CHANGELOG.md.
- **Did:** added `### 2026-10-19 (platform-stack-up)` under [Unreleased] with Added, Changed, Security. Claims checked against compose, launch.sh, quickstart and the rework-2 gate evidence.
- **Not announced:** commit/CI for 2a (pending), deferred nits and L-5/L-8/L-9/L-10, and any worker job processing (2b).
- **Evidence:** `docs/evidence/platform-stack/marketer.md`.
- **Next:** orchestrator confirms CI green at the 2a commit before the entry is released; README positioning is the documenter's call (not changed here).
## 2026-10-18 documenter: platform-stack-up docs gate
- Files: README.md (Running the stack, verify full description, Structure, Getting Started no longer says `docker compose up -d phoenix`), CLAUDE.md (new section "What verify.sh runs that CI cannot", after "What CI runs that verify.sh does not"; depth table and evidence contract untouched), docs/quickstart.md (URLs, model host).
- PS-2.13: section was absent, so added. Its test (`test_claude_md_lists_verify_only_checks`) and the model-calling integration tests are 2b and do not exist yet; the section states the rule only.
- Not claimed: readyz, worker behaviour, store stop/start (2b).
- Verify: `scripts/verify.sh fast` PASS; output in docs/evidence/platform-stack/documenter-verify.txt.

## 2026-10-19 tester: CI fix, 5 MB hook test (criterion 10 contradiction, orchestrator ruling)
- Cause: CI 1e89584 red, `test_five_megabyte_command_without_backslash_newline_is_one_pass` no-jq 3.9-6.4 s vs 3 s on the 2-core runner (`ci-run.txt`); wall-clock proxy for security L21.
- Change (tests/test_block_main_commit_hook.py only): NEW `test_second_text_built_and_judged_only_with_backslash_newline` counts, from `bash -x`, norm calls (texts built) and `for text in` iterations (texts judged): (1, 1) without a backslash-newline, (2, 2) with one, both modes, small inputs. 5 MB test kept as sanity bound < 9 s (hook timeout 10 s). Requirement 4f 1 MB < 3 s tests unchanged. Comment cites the ruling.
- Mutation (guard case/esac removed, body verbatim): new test RED 10 failures `(2, 2) != (1, 1)`; scratch copy deleted: `ci-fix-mutation.txt`.
- `scripts/verify.sh full` PASS, 320 unit OK, smoke pass: `ci-fix-verify.txt`. Next: developer commits, push on human approval, confirm CI green.
