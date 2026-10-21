# Re-review: platform-stack-up (2a), rework round 2 of 5, 2026-10-19

Reviewer: `git diff d26bec6` plus untracked files on `agent/platform-stack-up`
(uncommitted). Inputs: `review-rework1.md`, handoff sections "orchestrator:
rework round 2", tester/developer rework 2, tester contradiction fix,
`green-rework2-final.txt` (verify full PASS, 319/319 unit + 3/3 integration,
live smoke with real `network inspect`).
Mutants, parallel-stack run: `docs/evidence/platform-stack/review-rework2-mutants.txt`
(scratch copy, `ke-gates`, `--network none`; scratch deleted afterwards).

**Verdict: APPROVED** (0 blocking, 9 new nits, deferred list below)

## 1. R1-B1 and R1-B2

| Finding | Status | Proof |
|---|---|---|
| R1-B1 fixed backend subnet | resolved | `ipam` gone from `docker-compose.yml`; no CIDR in any compose file. IPAM (subnet+ip_range), IPAM-var (`${KE_BACKEND_SUBNET:-...}`), IPAM-overlay KILLED by `Rework2ComposeTest`. Runtime isolation proof moved to smoke host half (`docker network inspect <project>_backend`): SM-I1 (block removed), SM-I2 (mode check removed), SM-I4 (fixed name), SM-I5 (mode assumed), SM-I6 (failure downgraded) KILLED by `SmokeBackendIsolatedTest`. |
| R1-B2 Engine >= 28 untested / fail-open on empty | resolved | Fake answers `docker version` with `FAKE_DOCKER_ENGINE`; both scripts refuse empty, garbage, leading space, < 28, daemon error. L3 and L6 (check deleted) KILLED by `test_launch_refuses_docker_engine_below_28_or_unreadable` itself (L6 is no longer an incidental lint kill). L3-empty, L6-empty (empty accepted), L3-exit, L6-exit (exit status ignored), L3-min27 KILLED. |

Other rework-2 scope:
- **Security L-3, gateway ports:** each of the five ports dropped from the check (GP-API, GP-PHX, GP-MODEL, GP-APIPORT, GP-PHXPORT) KILLED, and so are GP-zero, GP-range and GP-copy (Dockerfile no longer installs the script). The template-driven drift test works.
- **Security L-7, lint path injection:** the rework-1 shape (paths embedded as a PowerShell array literal, LN-L7b) is KILLED by `test_lint_runs_no_code_from_a_powershell_filename` (markers written for U+2018, U+2019, U+201A, U+201B). A per-file shape (LN-L7) survives that test, because its payload tail does not parse. See R2-N6. Current code is safe by construction: the `-Command` text is fixed and paths travel in `KE_LINT_PS1_FILES`.
- **F3, teardown profiles:** T1, T2 (`--profile '*'`) and T6 (`COMPOSE_PROFILES='*'`) KILLED by `Teardown{Sh,Ps1}ScopeTest`. T7 (`--volumes` ignored) KILLED.
- **N-3, no host_ip:** L4-sh and L4-ps1 KILLED. Old L4 is closed.

## 2. Test integrity

- **`--remove-orphans` assert removal: legitimate.**
  - The old assertion required `--remove-orphans`. Ruling F3 and architecture section 2.4 (lines 924, 955) forbid it, so the test could not pass against a compliant implementation.
  - The removal is cited in-line (F3, section 2.4) and the `--volumes` checks are kept.
  - Gap: the inverse assertion that section 2.4 lists as a first test ("carries no `--remove-orphans`") was not added. T3 and T4 (re-add `--remove-orphans`) SURVIVE. See R2-N1.
- **Other fixture changes cited by the tester: not weakening.**
  - Launch defaults `FAKE_DOCKER_ENGINE=29.5.2`. Every refusal case overrides it explicitly.
  - Gateway `_run_entrypoint` sets the compose port defaults. Every bad or injected case overrides one variable.
  - The integration M-2 probe skips a `.1` owned by a stack container. This is ruling R1-B1 (ii) as written. Without `isolated` the host owns `.1`, so the probe still runs there.
  - `_bridge_gateways()` was kept, not removed as the architect noted. It is now redundant with the smoke inspect but harmless.
- **Limitation:** the test files are untracked, so a mechanical rework-1 to rework-2 test diff was not possible. Checked by reading the classes and by the mutants above. No skip was added, and pwsh/shellcheck absence is still `fail`.

## 3. Parallel stacks: yes, shown

- **Live run:** `ke-rev2-a` and `ke-rev2-b` came up concurrently with the verify overlay, and `ke-rev2-live` came up alongside them without the overlay, publishing 127.0.0.1:47100/47101. All 21 containers were healthy.
- **Backend pools:** Docker gave each backend its own auto pool (192.168.96.0/20, 192.168.128.0/20, 192.168.144.0/20). Each is internal and `isolated`.
- **Smoke:** the real `scripts/smoke.sh` host half passed against `ke-rev2-a` while all three were up.
- **Teardown:** all three projects were torn down to zero containers, networks and volumes.
- **From the compose file:**
  - There is no `ipam`, no `container_name` and no fixed network name. Networks and volumes are project-scoped.
  - Only the gateway publishes, and the verify overlay resets its ports. So parallel verify runs, and verify next to the live stack, cannot collide.
  - Two non-overlay live stacks on one host still collide on 47100/47101. That is by design.

## Blocking

None.

## New nits (rework 2)

- **R2-N1 (T3/T4 SURVIVED):** no test asserts teardown omits `--remove-orphans` (sh and ps1). Section 2.4 lists it as a first test. Add `assertNotIn("--remove-orphans", argv)` to `_TeardownScopeBase`.
- **R2-N2 (T5/T8 SURVIVED):** no test asserts teardown passes `--env-file` from `KE_ENV_FILE` (section 2.4 first test: "carries the project and env-file arguments").
- **R2-N3 (L3-anchor/L6-anchor SURVIVED):** the section 2.4 cases `28.0.1-rc.1` (refused) and `100.0.0` (accepted) are missing from `ENGINE_REFUSED`/`ENGINE_ACCEPTED`, so dropping the end anchor of the version regex goes unnoticed. This is not a security weakening, because the major is still >= 28.
- **R2-N4 (SM-I3 SURVIVED):** the smoke `"Internal": true` check is untested. The fake hard-codes `Internal: True`. Add an `Internal: false` case. The runtime no-route-out integration test still covers the property.
- **R2-N5 (GP-order SURVIVED):** nothing asserts the port check sorts before `20-envsubst` (installing it as `30-` passes). Today it is defence in depth only, since a later failing script still aborts the nginx entrypoint. The script header states it runs before 20-envsubst.
- **R2-N6 (LN-L7):** the L-7 payload is shape-specific. Add a payload that parses in any context (for example a filename ending in a `#` comment before `.ps1`), or a static assertion that the `-Command` text is the fixed heredoc.
- **R2-N7:** fake/architecture drift. `FAKE_DOCKER_ENGINE` defaults to empty, not `28.0.0`, and the fake uses `FAKE_DOCKER_ENGINE_EXIT` where section 2.4 says `FAKE_DOCKER_ENGINE_FAIL`. Align the doc or the fake.
- **R2-N8 (SM-I7 SURVIVED, near-equivalent):** a failure of the first `network inspect` is caught only because the second inspect fails too. A single JSON inspect parsed once would remove the duplication.
- **R2-N9:** rework-1 N-8 is still live. `LintScriptTest._project` runs `git add -A` without `-c core.autocrlf=false`, and the LF/CRLF warning flood reappears (the L-7 test already uses the flag).

## Deferred nits to carry to close-out

- **Review rework 1 (deferred by orchestrator):**
  - N-1 / LN2: ps1 coverage accepts any `scripts` mention.
  - N-2 / LN4: no planted Warning-severity PSScriptAnalyzer finding.
  - N-4 / G2: gateway upstream charset check redundant.
  - N-5: ps1 discovery is `-maxdepth 1`.
  - N-6: M-2 probe errno per port on a Linux CI run. Largely superseded by the inspect proof; record it or close it.
  - N-7: pwsh telemetry ENV after Install-Module.
  - N-8: autocrlf (see R2-N9).
- **Review round 0:** N3-N6, N8-N11 (see `review.md`).
- **Security:** L-5; L-8 (PSScriptAnalyzer pinned by version, not hash).
- **Architect flag (needs a ruling, not a code nit):** `.env.example` has `KE_MODEL_UPSTREAM=` empty and verify does not override it, so model-calling tests always skip in `verify.sh full`. This conflicts with the Q30 intent.
- **Commit-step items:**
  - B7a: `git add --chmod=+x` for every new `*.sh`, including the new `docker/gateway/12-ke-port-check.sh`, then check `git ls-files -s` shows 100755.
  - B7b: the Windows proof (PS-2.9, Q34) is stale again. launch/teardown/lint/smoke scripts, compose and the gateway Dockerfile changed in rework 2.
