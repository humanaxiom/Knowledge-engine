# Security re-audit: platform-stack-ready, rework round 1, 2026-10-19

- Scope: uncommitted tree on agent/platform-stack-ready against fe2f101, after "developer: rework 1 FINAL GREEN" (`green-rework1-final.txt`, verify full PASS 152 s). Prior findings: `security.md`.
- Runtime: ke-app image hash-matched to the tree (engine/worker.py, readiness.py, jobs.py sha256 identical). Scratch project `ke-sec-rw1` only (verify overlay, publishes nothing, marker store passwords), torn down with volumes (0 containers/volumes/networks left). `ke-verify-*` untouched. Lint cases ran in ke-gates with `--network none` on a scratch copy; L-11 ran verify's host half in a scratch tree with stubbed docker and scripts.
- Raw output: `docs/evidence/platform-stack-ready/security-rework1-scan.txt` (R1 M-1, R2 F1, R3 L-13, R4 L-11, R5 L-12, R6 secrets).

**Verdict: PASS.** No critical or high findings. M-1 engine core, L-11, L-12 (as reported), L-13 and F1 are closed. New: 1 medium (residual of M-1), 2 low, info.

## Closed
- **M-1 engine core (R1).** Worker is `AllowListWorker(SimpleWorker)` with `JSONSerializer`. From api, JSON enqueues of `platform.node`, `os.getcwd`, `builtins.print`, `this.s`, `engine.jobsx.noop`, `engine.jobs.__init__`, `.noop`, `noop`, `engine.jobs.traced_job`, `engine.jobs.get_current_job`, `engine.jobs.noop.__wrapped__`, trailing space, trailing NUL, upper case, `engine.jobs.chain_span`, `engine.jobs.functools.partial`: all FAILED with the fixed reason, none ran. `this.s` as the job function did not import `this` (the Zen text appears once, from the R1 callback case below, not here). A JSON instance (`["upper","abc",...]`) is refused; with the allowed name it fails on `getattr(str, ...)`. A `{"py/object": ...}` arg is only a string (it became part of a `ke:noop:` key). Pickle raw in `data`, in the pickled 4-tuple, in `meta` and in `exc_info`: never unpickled (`/tmp/PWNED_PICKLE` absent).
- **L-11 (R4).** Caller exports of both store passwords (markers), KE_AUTH__ENABLED, KE_BIND_ADDRESS, KE_ENV, KE_ENV_FILE, KE_API_PORT, KE_IN_GATES=0 and KE_ZZ_OTHER reach none of build/launch/compose run/smoke/teardown; only KE_MODEL_UPSTREAM, KE_EGRESS_ALLOWLIST plus verify's own KE_ENV_FILE/KE_SMOKE_OWNS_PROJECT do. The resolved gates-it and gateway config has 0 markers (control without the unset: 2).
- **L-12 (R5).** `x.PS1`, `m.psm1`, `m.PSM1`, nested `a/b/y.Ps1` are linted (IEX flagged, FAIL). Symlinked `l.ps1` (in repo), `p.sh -> /etc/passwd`, `o.ps1` outside the repo, a dangling `z.ps1`, and a directory link named `d.ps1` are refused.
- **L-13 (R3).** Code: the only `psycopg.connect` passes `gssencmode="disable"`. Wire: the probe's first packet is `SSLRequest`, never `GSSENCRequest` (libpq 18.0.6).
- **F1 (R2).** With KE_MODEL_UPSTREAM empty: `not_configured`, no Python socket to the gateway (8102) and 0 `/v1`/8102 lines in the gateway log over 3 live /readyz calls.
- **Secrets and profile paths (R6).** Diff plus untracked (23,235 lines, incl. new evidence): only test markers; no user-profile paths. No marker in api/worker/gateway logs or Valkey.

## Medium (non-blocking)
- **M-2: RQ callbacks and webhooks still import or call code, and send requests, outside `engine.jobs.__all__` (R1 W5-W7).** Same precondition as M-1 (write to unauthenticated Valkey from `backend`).
  - An allowlisted `engine.jobs.noop` with `on_success`/`on_failure` names any importable callable: `builtins.print` was called with `(job, connection, result)`, and `this.s` imported `this` (side effect in the worker log). `execute_job` checks only `func_name`.
  - `StartedJobRegistry.cleanup` (worker maintenance, at start and every 10 min) calls the failure callback of any job id written to `rq:wip:default`; a job whose function is `platform.node` had `builtins.print` called. This path never passes `execute_job`.
  - Webhooks: a refused job (`os.getcwd`) still sent a POST with attacker headers to `http://api:9999/` and an allowed job a GET. urllib, so outside the DR30 egress guard; reach is the backend hosts and the gateway's fixed model forward.
  - Not shown to reach code execution (callbacks get fixed RQ arguments), but the allowlist invariant does not hold.
  - Fix (with Q39 carry-in 7 at the latest): give the worker a `job_class` whose success/failure/stopped callbacks resolve to None and whose webhooks are empty, and refuse in `execute_job` any job carrying a callback name, webhooks or an instance; tests for each, including the abandoned-registry path.

## Low (non-blocking)
- **L-14: one malformed job stops the worker process (R1b).** A list `func_name` raises `TypeError: unhashable type` in the allowlist check, and non-JSON `data` raises `DeserializationError`; both are outside the refusal, so RQ logs "found an unhandled exception, quitting". `restart: unless-stopped` brings it back (5 restarts for 5 such jobs, no loop). Fix: treat any exception reading `func_name` as a refusal and fail the job with the fixed reason.
- **L-15: lint does not follow directory symlinks, and skips `*.SH` (R5 F, F3, I, G).** `scripts/linkdir -> <outside dir>` holding an IEX `.ps1`, the same under `docker/`, and `scripts/sub` linked outside: lint PASS, while the scripts are runnable through the link. `scripts/u.SH` is not shellchecked. Fix: fail on any symlink under `scripts/` and `docker/` (`find scripts docker -type l`), and `-iname '*.sh'`.

## Info
- **M-1 network side (Q39).** Unchanged: the gateway (`nc -z valkey 6379` OPEN) and phoenix (PING to PONG) still reach the unauthenticated Valkey. The deferral is acceptable for this item: no route enqueues and `backend` is internal. Note: the trigger is not only untrusted ingest input. Any compromise of phoenix (unauthenticated OTLP on the loopback gateway port) or nginx is enough. So carry-in 7 should be the first unit of ingest-ledger, as A39 says, and M-2 and L-14 should go with it.
- `*.psd1` is not linted (a data file; PSScriptAnalyzer does not execute it).
- verify's host half still passes non-`KE_*` variables (HARNESS_TRACING, PHOENIX_PORT, COMPOSE_PROFILES). None of them is a secret.
- Carried forward, unchanged: L-5, L-8, and the info items in `security.md`.
