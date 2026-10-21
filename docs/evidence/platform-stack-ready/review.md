# Review: platform-stack-ready (2b), round 0

- Reviewer, 2026-10-19. Base fe2f101, branch agent/platform-stack-ready, uncommitted tree plus untracked files.
- Read: handoff (S1, C1, W1, Q35-Q37, KE_SMOKE_OWNS_PROJECT ruling), requirements PS-2.5-2.8, 2.13, 2.18, 2.21-2.24 with the carry-in table and gate depth, the architecture 2b amendment (§2.2, §2.4, §2.6, ADR-KE-011), and green-full.txt.
- Diff read in full: engine/{api,readiness,jobs,worker,startup,llm/client}.py, docker-compose.yml, app.Dockerfile, scripts/{env_value,smoke,teardown(.sh/.ps1),lint,verify}.sh, and every changed or new test.
- Mutants: run in a scratch copy (no .env) inside the `gates` image (`network_mode: none`, project `ke-review-mut`). Each mutant was applied with perl, tested on its target modules, then restored. The scratch copy has been deleted, and no `ke-review-mut` container or network is left.

## Verdict: CHANGES REQUESTED

## Blocking

**R-B1. `test_gateway_only_external_upstream_is_model_upstream` was never written (PS-2.7 *Model host only through the gateway*).**
- The test is on the 2b fast gate-depth list (requirements "2b gate depth").
- The 2a handoff moved it into 2b explicitly ("Out of 2a, not written").
- No file under tests/ defines it, and no other test checks that every gateway upstream is a compose service name apart from `$KE_MODEL_UPSTREAM`. Today the templates hold `api`, `phoenix` and `$ke_model_upstream`, so the behaviour is right, but nothing protects it from regressing.

**R-B2. `ModelClient.probe` (a new outbound call) is untested, so DR30 and readiness paths can regress without any test failing.**
- MP1: `self.http_client.get(` changed to `httpx.get(` (the probe bypasses `GuardedTransport`). It SURVIVED readiness, model_skip, engine_llm and engine_egress. It also survives full, because `test_egress_allowlist_holds_with_network_access` calls `complete()`, not `probe()`. PS-2.5 *Model-host probe guarded* says that test covers the probe. It does not.
- RZ9: `raise_for_status()` removed. It SURVIVED. A model host (or forward) that answers 401, 404 or 5xx would then show `model_host.ok: true`. Coverage misses client.py 57 and 59.
- MP2: the per-call `timeout=` removed. It SURVIVED. The probe would then fall back to the pass's 120 s, which breaks *Bounded* for `/readyz`.
- Fix (fast, no network): a loopback or MockTransport test of the real `probe`:
  1. An off-list host raises `EgressDenied` with no socket opened, and `/readyz` reports `model_host.reason == "egress_denied"` through the real probe. Add the DR38 control: the guard disabled means a connection is attempted.
  2. 401 → `auth_failed`; 500 → `error:HTTPStatusError`.
  3. The probe passes the readiness timeout.

**R-B3. PS-2.8 *Every service healthy* runs before the store stop/start, not "after the store is back".**
- smoke.sh runs its health loop only before `/readyz` and never after `up --wait postgres`. green-full.txt lines 959-977 show the order.
- The criterion text and the PS-2.8 summary order ("stops and starts one real store, checks every service healthy") both put the check after the restart. Architecture §2.4 Smoke step 4 puts it before. The developer followed the architecture, so the requirement is not met.
- Fix: re-run the health loop after the final `ready`, and add it to `LAUNCHED_ORDER`. Otherwise the analyst amends PS-2.8. The orchestrator picks one.

**R-B4. Three in-scope carry-ins were not done. Each table row says "reviewer checks".**
- review R6 (platform-config): `test_non_local_collector_gets_no_exporter` and `test_configure_tracing_attaches_nothing_for_non_local` (tests/test_engine_startup.py:309, :321) are unchanged. They were neither deleted nor given a docstring pointing to test_engine_telemetry.
- round-0 N9:
  - `tests/support.py` still has the ImportError fallback.
  - `verify_provider(service_names)` still does `del service_names`.
  - startup.py:127, the line this diff rewrote, still computes `settings.stack.service_names if settings else []` only to pass it to that dead argument.
- review-ci-fix N1: there is no comment in scripts/hooks/block-main-commit.sh next to `norm` (the tr upper/lower call, line 44) or the `for text in` loop (line 56) saying the L21 test counts those lines.
- Each one is small. Do them, or the orchestrator records a deferral. They must not be dropped silently.

## Nits
- N1 (SM6 SURVIVED): when smoke's own teardown fails it must fail smoke (§2.4 Smoke step 2). Removing the `rc=1` promotion in `cleanup()` passes all smoke tests. Add a case with `FAKE_STUB_FAIL=teardown.sh`.
- N2 (WK3 SURVIVED fast and full): `rq.SimpleWorker` → `rq.Worker` passes every test. The design chose SimpleWorker so that `job.*` spans export, because a forked child never flushes. With a forking worker, job spans would be silently lost in production. Add a static or unit assertion.
- N3 (RZ10 SURVIVED): the `httpx.ConnectError` cause branches for TimeoutError and other OSError (readiness.py 78-81) have no case. A DNS failure of the model host would read `error:ConnectError` instead of `unreachable`. Add two vocabulary cases.
- N4 (LN1 SURVIVED, equivalent): with the open-bracket alternative removed from the lint.sh case, a lone open bracket still fails closed. I checked this in the gates image: a file named a, open bracket, 1.ps1 gives "The specified wildcard character pattern is not valid" and lint exits 1. Every test name also contains a close bracket. Add a name with only an open bracket so the stated rule is pinned.
- N5: the lint.sh wildcard refusal echoes `$file`, while §2.2 says "the path itself is not echoed, for the same reason as L-7". PS-2.23 allows "naming the file", and bash writing to stderr is not the L-7 pwsh vector. Align the architecture text or drop the echo.
- N6: teardown.sh exits silently (set -e/pipefail) when `compose config` or a listing command fails. §2.4 says "naming the check". teardown.ps1 does name it.
- N7: the coverage drop (94% → 88%) is mostly readiness.py 176-231, the `--wait-for` CLI. Four subprocess tests cover it, but coverage does not follow subprocesses. Consider in-process calls to `main` or `COVERAGE_PROCESS_START`. Not a testing gap.
- N8: the W1 test names `test_worker_main_idles_after_a_passing_startup` and `..._exits_before_idling` are now inaccurate. Rename later (the assertions are fine and stronger).
- N9: verify.sh exports `KE_SMOKE_OWNS_PROJECT=1` for the whole host half, and smoke honours the variable from any caller. An operator who has it exported gets postgres stopped on their live stack. Scope it to the smoke call only.
- N10 (for security): process env outranks `--env-file`, so a shell that exports `KE_STORES__*__PASSWORD` sends real secrets into the verify project. That now includes gates-it, which runs as root with the repo read-write (L-5). This predates 2b for api/worker. Consider having verify's host half pin or unset the two store secrets.
- N11: §2.4 Model wiring says the `.env.example` comment above `KE_EGRESS_ALLOWLIST` tells the operator to list the model host only. `.env.example` is unchanged. This is a documenter item.
- N12: tests/integration/test_stack_ready.py hardcodes postgres port 5432 in `require_reachable`. Use `settings.stores.postgres`.
- N13: `docs/knowledge-engine-claude-code-prompt.md` (untracked, dated 2026-10-18 11:07) is not part of this item. Do not stage it with `git add -A`.
- N14: store probes bound connect and handshake only. A neo4j or postgres server that accepts and then stalls on the query has no read timeout. Low, because the worst case in §2.4 assumes well-behaved servers. Record it or set a statement or transaction timeout.

## Mutant record (fast, gates image)
KILLED (37):
- RZ1 reason=str(exc); RZ2 error:{exc} fallback; RZ3 record_exception on the readyz span; RZ4 model host counted as required; RZ5 probe when base_url is null; RZ6 no 503; RZ7 no api.readyz span; RZ8 CLI honours proxy.
- WK1 worker skips startup() (calls run(Settings())); WK2 startup after run.
- JB1 traced_job removed from noop; JB2 decorator returns fn; JB3 no ke.job.id.
- ST1 Settings built twice in the load span; ST2 refusal log removed; ST3 extra Settings() in the preflight.
- EV1 third key KE_ENV accepted; EV1b secret key accepted; EV1c any key accepted; EV2 .env sourced; EV2b .env sourced in a subshell; EV3 the file wins over an empty caller value; EV4 compose stderr not discarded.
- VF1 either-not-both; VF2 no owns flag.
- SM1 teardown of a pre-existing project; SM1b launched always set; SM2 stop/restart skipped when the flag is set; SM3 stop on a pre-existing project; SM4 no not-ready wait; SM5 flag with nothing running launches.
- TD1 sh removes instead of reporting; TD1b sh removes and reports; TD1c sh network rm; TD2 ps1 removes instead of reporting; TD3 sh exits 0 with leftovers; TD4 volumes always listed; TD5 default project in the filter; TD6 ps1 skips networks.
- LN2 star allowed; LN3 maxdepth 1.
- CP1 no gateway prefix; CP2 gateway prefixed; CP3 gates-it on edge; CP4 worker has no depends_on.

SURVIVED: MP1, RZ9, MP2 (R-B2); SM6 (N1); WK3 (N2); RZ10 (N3); LN1 (N4, equivalent).

WK4 (queue name) survives fast. It is killed in full by test_worker_consumes_noop_job, because the job is enqueued on default.

## Test integrity (focus 4)
- W1: the worker entrypoint tests now patch engine.worker.run and wrap startup. Every assertion is kept and three were added: run is not called on refusal, startup runs exactly once, and run gets the Settings that startup returned. This is stronger, not weaker.
- B6 env_value.sh stub prints the caller's value only. The STAGE_STUB line gains an owns field at its end. The project and file parsers split on the project marker and the field separator, so no assertion became vacuous.
- Smoke launch.sh/teardown.sh stubs log into the fake's JSON call log. The 2a smoke assertions are unchanged.
- TeardownScriptTest moved from the inline sh fake to tests/fake_docker.py (same FAKE_DOCKER_LOG line format). Its assertions are unchanged.
- autocrlf: git add with core.autocrlf=false only.
- R2-N6 is extended: a comment-shaped payload plus a static heredoc check.
- The diff of tests against fe2f101 shows no removed test method and no deleted assertion. Only messages were reworded.

## Design conformance (focus 3)
- readiness.py matches §2.4: two-step probes through module seams, one classify, TOOL spans with no exception events, reasons drawn only from the vocabulary, the model host not required, and not_configured with no I/O. ConfigError text in the CLI names keys only (loader.py:34).
- The x-model-env anchor is a single source, enforced by a test that counts occurrences. No F-A risk: the anchor only sets in-stack URLs.
- The app allowlist (gateway prefixed to the operator list) is no F-A risk. gateway is in-stack, every gateway listener except the model forward proxies to api/phoenix, and the operator host stays unreachable directly because backend is internal and isolated. It is no DR30 weakening in itself, but see R-B2: the one new guarded call is not proven guarded.
- gates-it store passwords: under verify these are the .env.example placeholders. The residual risk is caller env (N10) together with L-5. Security has it.
- Teardown detect-and-report fits F3: no profile flag, no remove-orphans, no removal (TD mutants).
- The Dockerfile layer order (N11) is as designed.

## Carry-in triage (focus 5)
Done:
- L-9 → PS-2.22 (TD mutants).
- L-10, N-1, N-2, N-5, R2-N6 → PS-2.23 (LN2/LN3, and the warning test exists).
- R2-N1–N5 → PS-2.24 (tests present; RED evidence in red-ps-2-24-mutants.txt).
- ci-fix N2 → PS4 pinned plus a test.
- round-0 N3 → LISTEN keys and the compose target case.
- round-0 N4 → the identity test.
- round-0 N11 → the smoke header and the KE_SMOKE_OWNS_PROJECT ruling.
- review N11 (Dockerfile) → done.
- R2-N9 → autocrlf done.
- R2-N7 → the fake answers the §2.4 names and the JSON form.
- R2-N8 → n/a (the inspect code was not rewritten).

NOT done: R6, round-0 N9, ci-fix N1 (R-B4).

Pending by ruling, so they block commit but not this review:
- PS-3.4/C1 timeout follow-up together with the round-0 N10 ci.yml comment (ci.yml line 24 still says "with networking disabled").
- The 1 MB watch in the 2b CI evidence.
- The PS-2.9 Windows run (Q34; windows-proof.txt is present, and the tester is judging it).
- The PS-2.21 run with the host reachable (green-full skipped test_readyz_reports_reachable_model_host as not configured).
- rework-1 N-4 (security).
