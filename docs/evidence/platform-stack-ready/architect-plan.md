## 2026-10-19 — architect: 2b plan (readyz, worker, smoke, model keys, L-9, L-10, PS-3.4)

- **Asked:** design the 2b parts concretely; check §2.4 against what 2a built; touch only `docs/architecture.md`.
- **Did (`docs/architecture.md`):** §2.1 (worker row, `probe` not built), §2.2 (isolation drift, model keys in local verify, skip-helper location, sequence diagram, Lint L-10), §2.4 (12-ke-port-check, Model wiring, /healthz drift, /readyz, Worker, Images N11, Scripts table, Smoke host half, Teardown leftovers L-9), §2.5 (PS-3.4 measurement), §2.6 (2b first tests), ADR-KE-011 amendment "platform-stack-ready (2b plan)".

### §2.4 vs as-built (checked)
- Long port syntax (`target`/`host_ip`/`published`/`protocol`): matches compose. No change.
- Worker `python -m engine.worker` running `startup()` then idling: matches. 2b keeps the command; `engine/worker.py` stays a module (a 2a test asserts the file).
- Gateway checks: 10 (bind) and 11 (upstream) were described; the L-3 port check is a separate `12-ke-port-check.sh` as built. Now named in §2.4.
- Drift fixed in text: no `config/verify.env` exists (verify uses `.env.example` only); `defaults.yaml` has `base_url: null` (the "defaults.yaml carries the gateway URL" text was never built); the gateway healthcheck uses `/_gateway/healthz`, not api's `/healthz`; `probe` service never built (dropped, smoke uses `compose exec`).

### Decisions
1. **/readyz:** `engine/readiness.py` (`classify`, `check_all`, CLI). Route `GET /readyz` takes settings through the FastAPI dependency `get_settings` (from `app.state.settings`, set in `main()`), so tests override it.
   - Store probes take two steps. First a raw TCP dial, which gives refused, timeout or unreachable. Then the driver: psycopg `SELECT 1`, neo4j `RETURN 1`, redis `PING`, each with timeout `t = readiness.timeout_s`.
   - Model: `not_configured` if `compose.base_url` is null. Otherwise a new `ModelClient.probe(t)` sends `GET {base_url}/models` through `GuardedTransport`, so the result is `egress_denied` before any socket opens. No llm_span.
   - Vocabulary: `timeout | refused | unreachable | auth_failed | egress_denied | not_configured | error:<Class>`. It never carries message text, DSNs or hosts.
   - Spans: `api.readyz` CHAIN, and `readyz.{postgres,neo4j,valkey,model_host}` TOOL. Failed spans are ERROR with the reason.
2. **Model wiring:** the compose `x-model-env` anchor sets `KE_MODELS__*__BASE_URL=http://gateway:${KE_GATEWAY_MODEL_LISTEN:-8102}/v1` in api, worker and gates-it.
   - The app allowlist is `gateway,${KE_EGRESS_ALLOWLIST:-}`. Without the prefix, the base URLs would make every app start refuse.
   - The gateway's own allowlist is unchanged, and `.env.example` is unchanged.
   - gates-it also gets `KE_MODEL_UPSTREAM` and the two store passwords. These are the verify project's placeholders only.
3. **Worker:** RQ `SimpleWorker(["default"])`. The forking Worker would lose job spans because of `os._exit`.
   - `main()` is `startup()` then `run(settings)`.
   - Jobs live in `engine/jobs.py`. `@traced_job` gives a `job.<name>` CHAIN span with `ke.job.id`.
   - `noop` INCRs `ke:noop:<token>` on the job's connection.
   - The worker gets `depends_on` valkey healthy.
4. **Dependencies:** `psycopg[binary]`, `neo4j`, `redis`, `rq`, added through `uv add` and pinned in uv.lock at implementation. No versions are chosen here. mypy overrides are per-module with a reason. The psycopg LGPL licence is flagged for security and the human.
5. **Model keys in local verify:** new `scripts/env_value.sh <NAME>`.
   - It accepts only the two names; any other exits 2.
   - The caller env wins, even when set empty.
   - Otherwise it reads `.env` through `docker compose -f docker-compose.yml --env-file .env config --format json gateway` and extracts the gateway env key line by line, as launch does. It never sources the file, and compose's stderr is discarded. The gateway service carries no secrets.
   - If the call fails, or the value has a JSON escape, it exits non-zero.
   - `verify.sh` assigns both values (both or neither, with a printed note) and exports them before `build.sh`.
   - Skip reason: `model host not configured: KE_MODEL_UPSTREAM is empty (...)`, or `model host unreachable: <upstream> (<reason>)`.
6. **Smoke host half:** after the 2a no-.env check, it sets a trap to `teardown.sh`, runs `launch.sh` (idempotent), then the 2a checks. Then:
   - `exec api python -m engine.readiness --wait-for ready --within 60`;
   - `stop postgres`;
   - `--wait-for not-ready:postgres --within 30`;
   - `up -d --no-build --wait postgres`;
   - `--wait-for ready`.
   Postgres is the store stopped, not valkey, which would crash-loop the worker. All commands stay in smoke.sh, and verify.sh is unchanged apart from the model keys.
7. **L-9 within F3:** teardown resolves the project name before `down`. After `down` it lists, read-only, containers, networks and (with `--volumes` only) volumes labelled with the project. Any leftover or listing failure means exit non-zero, naming the leftovers and printing hand-removal commands. It never removes anything itself. The N7 hand command points to that output.
8. **L-10:** `lint.sh` refuses `.ps1` paths containing `[ ] * ?` before pwsh runs, in the same loop as the newline refusal. `Invoke-ScriptAnalyzer` has no `-LiteralPath`.
9. **PS-3.4:** 274 s × 1.5 = 411 s, so `timeout-minutes: 7` (from 20).
   - It is recorded in a comment on the ci.yml line, with the arithmetic and the evidence path `docs/evidence/platform-stack/ci-run-0f2821c.txt`, plus `docs/evidence/platform-stack-ready/ci-timeout.md`.
   - It is re-measured from 2b's own green CI run at close-out.
   - The test also asserts that the comment's evidence path exists.
10. **N11:** app.Dockerfile installs dependencies before copying code (`uv sync --no-install-project`, then copy, then sync).

### First tests (order, fast first)
Full list: §2.6 "platform-stack-ready". Start with these fast tests:
1. `test_readyz_reason_vocabulary` (proposed)
2. `test_readyz_is_traced`
3. `test_readyz_ready_excludes_model_host` (proposed)
4. `test_store_probe_classifies_closed_port` (proposed)
5. `test_worker_job_is_traced`
6. The worker entrypoint tests, retargeted to the new seam
7. `test_compose_model_wiring` (proposed)
8. `test_compose_postgres_identity_matches_defaults`
9. `env_value.sh` / verify B6 cases
10. The skip-helper tests
11. The L-9 teardown cases
12. The L-10 lint case
13. The readiness CLI and smoke-order tests
14. `test_ci_job_has_timeout`, PS-2.13, PS-2.18

Then the integration tests, in order: `test_readyz_reports_each_dependency`, `test_readyz_fails_when_store_down` (with only the postgres password set to the marker; a wrong neo4j password counts toward its failed-auth lock), `test_readyz_ready_without_model_host` (`http://gateway:1/v1`), `test_worker_consumes_noop_job`, and `test_readyz_reports_reachable_model_host`.

### Needs a ruling
- **S1:** PS-2.8 says smoke tears down. Run by hand against the operator's live project, it therefore takes that project down. The design follows PS-2.8 literally. The alternative is to tear down only if smoke itself started the project (`compose ps -q` empty before launch).
- **C1:** set `timeout-minutes: 7` now from the only measurement, 274 s, as PS-3.4 says literally? 2b's first CI run then risks cancellation. The alternative is to keep 20 until 2b's CI run is measured and set it at close-out. The architect recommends 7 now, then re-measuring.
- **W1 (tester fixture changes, assertions unchanged):** the worker entrypoint tests patch `engine.worker.run` instead of `signal.pause`/`time.sleep`, and the verify B6 temp tree gains an `env_value.sh` stub.
- **For the analyst:** the vocabulary gains `unreachable` and `not_configured`; the names marked proposed in §2.6 need adopting. The worker job path is `engine.jobs.noop`, replacing `engine.worker.jobs.noop`.
- **Not designed here (not in this brief):** security L-5 and L-8, and review nits R2-N*, N-*, N3–N11 other than N4 and N11. PS-2.18 is fully specified by requirements.
- The Windows proof (Q34) goes stale: scripts and compose change.

### Evidence
- `docs/evidence/platform-stack-ready/architect-plan-verify-fast.txt`
