# Security audit: platform-stack-ready, 2026-10-19

- Scope: uncommitted tree on agent/platform-stack-ready against fe2f101 (diff + untracked files), after "developer: GREEN units 1-10" and `green-full.txt` (verify full PASS 147 s).
- Runtime: Docker Engine 29.5.2; `docker` is the real Docker Desktop binary (checked with `command -v`/`type -a`; no shim). ke-app image files hash-match the tree; images used with `--no-build`.
- Scratch only: projects ke-sec-ready-a (live, ports 47190/47191 on 127.0.0.1, marker passwords) and ke-sec-ready-b (teardown.ps1), decoy containers ke-sec-decoy-*. All removed with volumes; no other project touched.
- Raw output: `docs/evidence/platform-stack-ready/security-scan.txt` (S1 live, S2 env_value, S3 lint, S4 deps, S5 secrets).

**Verdict: PASS.** No critical or high findings. L-9 and L-10 are closed. New: 1 medium, 3 low, info items.

## Checked and holding
- **/readyz body, spans, logs (S1 R1-R9).** Stores stopped one by one, two at once, and api given wrong postgres/neo4j passwords: bodies carry only `unreachable`, `auth_failed`, `error:<Class>`. Spans (HARNESS_TRACING=console) carry `ke.readyz.ok/reason` and no events or exception text. Marker passwords, wrong-password markers, DSN schemes, `postgres:5432` and "password": 0 hits in api, worker and gateway logs. The model host name appears only in the 2a `ke.hosts_checked` startup span and the gateway nginx error log (operator config, pre-existing).
- **Reachability (S1 R2/R3).** Only the gateway publishes (127.0.0.1:47190/47191). /readyz from every other host address (LAN 192.168.1.80, 100.75.x, two vEthernet) and api:8080 on the host: connection refused.
- **Not a scanner.** The route takes no parameters; targets come only from Settings. `--wait-for` accepts only the fixed vocabulary and always asks 127.0.0.1.
- **ModelClient.probe vs DR30 (S1 P1/P2).** A base_url host off the allowlist gives `egress_denied` with no socket opened; an allowlisted host that 302-redirects to `phoenix` is denied at the redirect hop. `trust_env=False`.
- **Model wiring.** The app allowlist `gateway,<operator list>` cannot widen egress: app, worker and gates-it sit only on the internal backend, and the gateway forward is still the fixed `map` to KE_MODEL_UPSTREAM, checked by 11-ke-upstream-check against the operator raw list (no `gateway` prefix there). Compose interpolation carries a newline/YAML payload in KE_EGRESS_ALLOWLIST literally (KE_AUTH__ENABLED stays "false").
- **env_value.sh (S2).** Other names, two args and `NAME[0]` exit 2. `.env` is never sourced: `$()`, backticks, escaped quotes, `\n`, `"` and a JSON key-injection value run nothing (0 PWNED files), and escapes fail closed. A JSON-injected `"KE_EGRESS_ALLOWLIST"` inside another value is not matched. An unparseable `.env` fails without echoing it.
- **Teardown L-9 (S1 T1/T2), closed.** The filter is an exact label match: decoys labelled ke-sec-ready-a-x, ke-sec-ready and KE-SEC-READY-A were neither reported nor touched; the own leftover was reported, not removed, rc 1, for teardown.sh and teardown.ps1.
- **Lint L-10 (S3), closed.** `[ ] * ?` in the name or a directory are refused; backtick names, `$()`, quotes and pwsh subexpressions are linted (IEX flagged) and run nothing.
- **Worker.** No route enqueues; job function and args are set only by whoever writes Valkey (see M-1). Worker runs as `ke`.
- **Dependencies (S4).** All new packages come from PyPI with sha256 for the sdist and every wheel. pip-audit 2.10.1 on the frozen export: no known vulnerabilities. Licences: psycopg/psycopg-binary 3.3.6 LGPL-3.0-only; neo4j Apache-2.0 AND Python-2.0; redis MIT; rq BSD-2-Clause; croniter MIT; pytz MIT; python-dateutil Apache-2.0/BSD; six MIT; tzdata Apache-2.0 (win32 only, not in the image). psycopg used unmodified and imported dynamically is acceptable under LGPL-3.0; for platform-offline, keep the dist-info `licenses/` in the image and list psycopg (LGPL, with the pinned sdist URL as the source) in the bundle notices.
- **Secrets and profile paths (S5).** 15,926 lines: only test markers; no user-profile paths, including in the new evidence.

## Medium (non-blocking)
- **M-1: anyone on `backend` can run code in the worker through unauthenticated Valkey (S1 W1/W2).**
  - From api, `Queue('default').enqueue('platform.node')`, a callable outside `engine.jobs`, finished in the worker and returned its hostname. RQ imports any dotted path and unpickles job data with its default (pickle) serializer.
  - Valkey has no password; the gateway (`nc -z valkey 6379` OPEN) and phoenix (PING -> PONG) reach it, as do gates-it and the stores.
  - So a compromise of phoenix (third-party, takes unauthenticated OTLP on the gateway port) or nginx becomes code execution as `ke` in the worker, which holds both store passwords and the model route. No outside path exists today: no enqueue route, backend internal, gateway forwards fixed.
  - Fix before any untrusted input reaches the queue (ingest) or auth-audit, whichever comes first:
    - put valkey on its own internal network with only api, worker (and gates-it);
    - set a Valkey password or ACL, passed only to api and worker;
    - use `rq.serializers.JSONSerializer` and refuse any job whose `func_name` is not in `engine.jobs.__all__`.

## Low (non-blocking)
- **L-11: caller-shell store passwords override the verify placeholders and now reach gates-it (S2).** Compose gives the shell precedence over `--env-file .env.example`. An operator with `KE_STORES__POSTGRES__PASSWORD` exported (for example after `set -a; . .env`) puts the real value into the verify stores and, new in 2b, into gates-it (root, repo read-write, L-5). That contradicts the ADR-KE-011 2b consequence "never real ones". `test_verify_full_takes_no_other_env_key` covers `.env` only. Fix: in the verify.sh host half, unset `KE_STORES__*` (or every `KE_*` but the two model keys) before compose, and add the caller-env case to the test.
- **L-12: lint still skips some PowerShell files (S3 C7, C8, C12).** `scripts/x.PS1` (Windows runs it), a symlinked `scripts/l.ps1`, and `scripts/m.psm1` all give lint PASS with Invoke-Expression inside. `find -name '*.ps1' -type f` is case-sensitive and skips links. Pre-existing selection, same class as L-10. Fix: `-iname '*.ps1' -o -iname '*.psm1'`, and fail on any symlink under scripts/ named like a script (also for `*.sh`).
- **L-13: psycopg-binary vendors old native libraries that pip-audit cannot see (S4).** The SBOM lists krb5-libs 1.15.1 (el7), cyrus-sasl 2.1.26, pcre 8.32. Exposure is small: password auth on an internal network, and no Kerberos credentials in the container. Fix: pass `gssencmode="disable"` on connect, and add an image scanner (trivy/grype) over ke-app in platform-offline.

## Info
- env_value E13: a `.env` value written as `${KE_STORES__POSTGRES__PASSWORD}` resolves through compose and is printed. Only the operator can author that; the gateway check then refuses the value without echoing it.
- env_value E8: a `$` in a `.env` value comes back doubled (`$$`), from the compose config escaping. Fidelity only; `$` is refused downstream.
- A wrong postgres password is reported as `error:OperationalError`, not `auth_failed`: psycopg sets no sqlstate on connect failures. Vocabulary accuracy for the reviewer; nothing leaks.
- KE_SMOKE_OWNS_PROJECT: only someone who already controls the operator shell can set it, and they could run `compose stop` anyway, so no boundary is crossed. Effect: a postgres outage of about 30-90 s, and `up -d --no-build --wait postgres` may recreate the container if its config drifted. Optional: also require `COMPOSE_PROJECT_NAME` to match `ke-verify-*` when the flag is set.
- /readyz is unauthenticated and costs four probes per request. Loopback-only by default. Revisit at auth-audit, or if KE_BIND_ADDRESS leaves loopback.
- KE_MODEL_UPSTREAM in gates-it is a host:port, not a secret. Carried forward, still deferred: L-5, L-8.
