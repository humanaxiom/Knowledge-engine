# Review: platform-stack-up (2a), 2026-10-19

Reviewer: `git diff d26bec6` plus untracked files on `agent/platform-stack-up`
(I ignored docs/knowledge-engine-claude-code-prompt.md and .venv). Mutation
and orchestration runs: `docs/evidence/platform-stack/review-mutants.txt`.
Each mutant ran in a scratch copy inside `ke-gates` with `--network none`.
The scratch copy is deleted. I rebuilt no image.

**Verdict: CHANGES REQUESTED** (7 blocking, 11 nits)

## Criterion coverage (2a)

| Criterion | Code | Test that can fail | Status |
|---|---|---|---|
| PS-2.17 M5 | `build_provider` + WeakSet, `verify_provider` checks identity | M5a/b/c KILLED; `test_provider_not_built_by_engine_is_refused` alone fails 8/8 on M5a | met |
| PS-2.1 services, digests | compose; smoke health loop | D1/D2/D3 KILLED | met (worker: B2) |
| PS-2.2 ports | gateway only, long syntax | P1-P4, E1 KILLED; P5 survives (N3) | **not met**: *Resolves without .env* smoke missing (B4) |
| PS-2.3 restart | anchors | R1/R2/R3 KILLED | met |
| PS-2.4 /healthz | `engine/api.py` | `test_healthz` (gates-it) | met |
| PS-2.7 Mechanism | gates-it on backend only | G1/G2/G3 KILLED (static) | met statically; runtime proof vacuous (B1) |
| PS-2.9 scripts, quickstart | sh + ps1, `docs/quickstart.md` | launch/teardown fake-docker tests | **not met**: no shellcheck/PSScriptAnalyzer gate (B5); Windows run outstanding (B7) |
| PS-2.10/2.11/2.12 | compose | G1-G3 KILLED | met |
| PS-2.14 engine | refusal 6 | B1/B1b/V6a KILLED | api wiring untested, worker not wired (B2) |
| PS-2.14 gateway | `10-ke-bind-check.sh` | B2/B2b/V6b KILLED | met |
| PS-2.14 launch | launch.sh/.ps1 | B3/B3b/V6c KILLED | fails open when KE_ENV is missing (B3) |
| PS-2.15/2.16/2.19/2.20, PS-1.9 | yes | S1 KILLED; tests present | met |

## Blocking

- **B1. `test_gates_it_has_no_route_out` cannot fail when gates-it has a route out.**
  - On a network with a route out, a connect to 192.0.2.1 times out after 5 s. `TimeoutError` is an `OSError`, so `assertRaises(OSError)` and the `< 30` s bound both pass. On an internal network the connect fails at once with `ENETUNREACH`. Both measured; see the evidence file.
  - The static test does kill G1. But ruling R2 names this test as the runtime proof, and as written it only proves that nothing answered.
  - **Fix:** assert the failure is not a timeout, e.g. `errno in {ENETUNREACH, EHOSTUNREACH}` (or `assertNotIsInstance(exc, TimeoutError)`) and a tight elapsed bound.
- **B2. Refusal 6 is not enforced in `worker`, and the `api` wiring is untested** (PS-2.14 (1) says "engine startup in api and worker").
  - The worker runs `python -c "import signal; signal.pause()"` and never calls `startup()`. Its `import engine` healthcheck checks nothing.
  - In `api`, `main()` is `pragma: no cover`. Mutant W1 (api builds `Settings()` without `startup()`) SURVIVED.
  - **Fix:**
    - Have the placeholder worker call `startup()` and then idle, e.g. a minimal `engine/worker.py`. This is still a placeholder until 2b.
    - Add a unit test that patches `uvicorn.run` and asserts `startup()` runs first and that a refused setting stops `main()` before `run`. Do the same for the worker entrypoint.
- **B3. launch.sh/launch.ps1 fail open when the env file has no `KE_ENV`.**
  - `setting()` falls back to `.env.example`, which has `KE_ENV=dev`. Compose interpolates an empty `KE_ENV`.
  - Measured with `KE_ENV_FILE` lacking `KE_ENV` and `KE_BIND_ADDRESS=0.0.0.0`: launch warns "dev only", exits 0 and runs `compose up`. The gateway check refuses the same inputs (rc=1).
  - PS-2.14 requires the same rule in all three places: unset is not dev, so launch must exit non-zero without starting any container.
  - **Fix:** read the refusal inputs from the process env and the env file compose actually uses, with no `.env.example` fallback. Treat empty or unset `KE_ENV` as not dev. Add the launch test case.
- **B4. PS-2.2 *Resolves without .env* is missing.**
  - `[smoke: test_compose_resolves_without_env_file]` checks that `docker compose config` succeeds with no `.env` and that every published port binds 127.0.0.1.
  - PS-2.2 is in 2a by the split, but the developer put it in 2b without a ruling. Every verify run passes `--env-file .env.example`, so nothing exercises the no-`.env` path.
  - **Fix:** add it to the host half of smoke.sh (it can run `docker compose config` from a temp copy with no `.env`), or get an orchestrator ruling that moves it to 2b.
- **B5. The PS-2.9 lint gates do not exist.**
  - There is no `scripts/lint.sh` and no shellcheck or PSScriptAnalyzer in the gates image.
  - The `# shellcheck disable` comments in smoke.sh are inert.
  - The tester handoff names PSScriptAnalyzer as the mitigation for the static-only `test_launch_ps1_checks_bind_address`.
  - §2.2 specifies `lint.sh` in both modes.
- **B6. The host orchestration in verify.sh has no test, and dropping the gates-it stage still gives PASS.**
  - Mutant V7 removes the `compose run gates-it scripts/verify.sh full` line. `verify.sh fast` stays green, and `verify.sh full` prints `PASS` without running a single unit or integration test.
  - V1 (trap removed), V2 (host smoke removed), V3 (fixed project name) and V4/V5 (verify publishes ports) also SURVIVE.
  - Current behaviour is correct (see the evidence file): every stage failing gives non-zero, teardown runs on failure and on SIGINT/SIGTERM, and the host half lists no gate commands.
  - **Fix:** add a fast test that drives the host half with the existing `FAKE_DOCKER` pattern. It should assert:
    - the order build, launch, `run gates-it scripts/verify.sh full`, smoke;
    - non-zero exit when each stage fails;
    - `teardown.sh --volumes` on success, failure and INT;
    - `COMPOSE_FILE` includes the verify overlay;
    - a per-run project name.
- **B7. Commit preconditions** (blocking for the commit step, not for the code):
  - (a) New scripts are untracked, and `core.fileMode=false`, so a plain `git add` records 100644. CI runs `scripts/build.sh`, `launch.sh` and `teardown.sh` directly, so it would fail with "Permission denied". The teardown in the trap would also fail silently behind the `or true`. Use `git add --chmod=+x` on `scripts/build.sh`, `scripts/launch.sh`, `scripts/teardown.sh` and `docker/gateway/10-ke-bind-check.sh`, and confirm 100755 with `git ls-files -s`. A test asserting 100755 on tracked `scripts/*.sh` would stop this recurring (nit).
  - (b) The PS-2.9 recorded Windows run (Q31/Q34) has not been done.

## Nits

- **N1. Long port syntax:** fine. It is equivalent, and `host_ip` and `published` are tested. But PS-2.2 and §2.4 still prescribe the short string form. Ask the analyst/architect to amend the wording. The second loop of `test_compose_defaults_match_env_example` only matches the short form, so it never runs. The first loop already covers what it checks.
- **N2. `test_compose_passes_bind_address_to_app` accepts a `KE_ENV:-dev` default.** Mutant B5 SURVIVED. The current bare `KE_ENV` with no default is correct and fails closed. Pin it to exactly that.
- **N3. `KE_API_LISTEN` / `KE_GATEWAY_*_LISTEN`:** the naming is accepted. It matches the gateway listen names, and the port-range test stays meaningful. But `_declared()` only treats keys containing `PORT` as ports, so 8100-8102 are invisible to the hardcoded scan. Mutant P5 (literal `target: 8100`) SURVIVED. Declare `*_LISTEN` values as ports and assert that `target` is a variable. Also list `KE_API_LISTEN` in the §2.4 `.env.example` list.
- **N4. Literal postgres user/db `engine`:** acceptable for 2a. It duplicates `stores.postgres.{user,database}` in defaults.yaml, so add a drift test, or pass the user through a compose variable with an `.env.example` entry, before readyz connects in 2b.
- **N5. Compose warnings with no `.env`:** accepted. Unset `KE_ENV` fails closed (engine `ConfigError`, gateway not dev), and the secrets have no default by F3. The B4 smoke should assert that `config` succeeds despite them.
- **N6. Images use shared tags (`ke-app`, `ke-gateway`, `ke-gates`).**
  - A verify run from another worktree retags images that a parallel verify run or the live stack will use on its next `up --no-build`.
  - The §2.2 "never collides" claim holds for containers, networks and volumes, but not for images.
  - Architect: consider per-project tags.
- **N7. Teardown failure after a green run is masked** (rc=0, and the project leaks). Print a warning at least.
- **N8. `docker/app.Dockerfile` layer order (review N11):** code is copied before `uv sync`, so every code change reinstalls all dependencies. Use `uv sync --locked --no-dev --no-install-project` after copying the lock files, then copy the code, then sync.
- **N9. Dead code:**
  - The `setup_tracing` fallback in `tests/support.py`. It is guarded by `test_support_provider_is_engine_built`; remove it now that GREEN.
  - `verify_provider(service_names)` with `del service_names`.
- **N10. ci.yml comment is stale:** "runs every gate inside it with networking disabled" is no longer true for full. Also record the first cold CI duration against `timeout-minutes: 20`. Warm local is 61 s, cold is unmeasured, and PS-3.4 is in 2b.
- **N11. smoke.sh host half and the 2a split table:**
  - The host half neither launches nor tears down; verify.sh does both around it. The 2a split table says "smoke launches, checks /healthz, tears down". This is acceptable as split, but record it.
  - The gates-only OTLP contract still holds: the inner half runs `smoke_otlp.py` (green-full.txt:613). Without `KE_IN_GATES=1` it fails loudly rather than passing.
  - Build not checking the bind address is accepted: build never publishes. Record it against the Q33a "build/launch" wording.

## Developer decisions: verdicts

- `KE_API_LISTEN` replacing `KE_API__LISTEN_PORT`: **accepted**, with N3.
- Long port syntax: **accepted**; the docs need amending (N1).
- Worker placeholder: **accepted only if it runs `startup()`** (B2).
- Literal postgres `engine`: **accepted for 2a**, with a drift test (N4).
- Compose warnings with no `.env`: **accepted**; they fail closed (N5). The missing smoke is B4.

## Test integrity

- Removed tests are exactly the documented four:
  - `PhoenixDriftTest` x2 (ADR-KE-011 ports amendment). Their assertions moved to `test_published_ports_use_bind_address`, `test_compose_defaults_match_env_example` and `test_compose_phoenix_listen_port_matches_config`. Mutant P2 confirms phoenix publishing is still caught.
  - The R3 renames, `test_accepted_shapes` to `test_formerly_accepted_foreign_shapes_are_refused` and `..._ignores_proxy_env_is_accepted` to `..._is_refused_unless_engine_built`, each with engine-built controls.
- 55 tests were added. The scanner collector is stricter: a non-UTF-8 file in scope now raises instead of being skipped.
- No threshold was lowered.
