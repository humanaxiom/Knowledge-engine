# Marketer: platform-stack-ready changelog gate

Scope: `CHANGELOG.md` only (new `### 2026-10-19 (platform-stack-ready)` block under [Unreleased], above platform-stack-up). No README or code changes.

## Claim-to-evidence map

| Changelog claim | Basis |
|---|---|
| `/readyz`, per-dependency status, fixed reasons, model host not required | Handoff: readiness module, F1 (not_configured without upstream), green-rework1-final.txt line 850 |
| Worker on Valkey (RQ), allowlisted jobs | Handoff: worker JSON noop finished, green-rework1-final.txt line 852; M-1 engine side |
| Smoke stops and restarts postgres | green-rework1-final.txt lines 914-921 |
| Model-calling checks in verify full, gated on the two keys | model-run-aria-gb10-2.txt (reachable model host test ran and passed); skip without keys |
| Deps psycopg (LGPL-3.0), neo4j, redis, rq | Handoff developer GREEN, licences in security 2b audit |
| Teardown reports leftovers, fails | L-9; Windows proof pass |
| Lint refuses symlinks, any extension case | L-12, L-15; red-rework2 then green-rework2.txt; reviewer re-review approved |
| Readiness no credentials or error text | Security 2b audit: no leak (markers, broken stores, spans, logs) |
| Worker JSON only, refuses non-allowlisted jobs | Security rework1 re-audit: M-1 engine core closed |
| verify passes no caller KE_* but the two model keys | L-11, security rework1 re-audit |
| Postgres GSS encryption disabled | L-13, wire SSLRequest check |

## Deliberately not claimed

- M-2 (RQ callbacks and webhooks bypass the allowlist) is open. The Security bullet is limited to "jobs", not callbacks.
- L-14 (a malformed job stops the worker) is open.
- M-1 network side (valkey on its own network, password/ACL) is open, deferred to the auth audit.
- L-5 and L-8 are deferred to platform-offline.
- No figures, counts or durations are stated.

## Gate

changelog: pass (entry added; claims traced to the handoff and evidence above).

## Open for the orchestrator

- The user's instruction was to touch only CHANGELOG.md. The handoff doc append required by AGENTS.md was therefore not made by this role. A one-line pointer to this file is needed there, or the orchestrator can accept this file as the marketer section.
- Before merge, M-2 and L-14 should be on the carry-in list so the Security copy stays accurate.
