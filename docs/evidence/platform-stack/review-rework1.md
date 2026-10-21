# Re-review: platform-stack-up (2a), rework round 1 of 5, 2026-10-19

Reviewer: `git diff d26bec6` plus untracked files on `agent/platform-stack-up`
(uncommitted). Inputs: `review.md`, handoff sections "orchestrator: rework
round 1", tester and developer rework-1, rulings R1/R2, `green-rework1.txt`.
Mutants and measurements: `docs/evidence/platform-stack/review-rework1-mutants.txt`
(scratch copy, `ke-gates`, `--network none`; scratch deleted afterwards).

**Verdict: CHANGES REQUESTED** (2 blocking, 8 nits)

## B1-B6 and N7: status

| Finding | Status | Proof |
|---|---|---|
| B1 no-route-out vacuous | resolved | errno in {ENETUNREACH, EHOSTUNREACH}, not TimeoutError, elapsed < 2 s; green in gates-it (`green-rework1.txt:731`). Premise re-measured: TEST-NET-1 gives errno 101 in 0.00 s on an internal network. |
| B2 worker/api refusal 6 | resolved | `engine/worker.py`, api pragma removed. W1, W2, W3 KILLED. |
| B3 launch fail-open | resolved | launch.sh/.ps1 read `compose config --format json`, empty KE_ENV not dev. L1, L2 (sh), L5, L7 (ps1) KILLED. launch.ps1 is now tested behaviourally under pwsh. |
| B4 resolves without .env | resolved | smoke host half, empty env file, loopback count. SM1-SM4 KILLED. |
| B5 lint gates | resolved (nits N-1, N-2) | `scripts/lint.sh` covers all 10 `*.sh` (scripts/, scripts/hooks/, docker/gateway/) and all 3 `scripts/*.ps1`; called before test.sh in both modes. LN1, LN3, LN5, LN6, LN7 KILLED. |
| B6 verify host half | resolved | V1, V2, V3, V4, V5, V7, V8, V9, V10 KILLED (V7 by sed). |
| N7 teardown failure masked | resolved | V8 KILLED. |
| B7a exec bits | open, commit step | still untracked; `git add --chmod=+x` and `git ls-files -s` 100755 at commit. |
| B7b Windows run | open, commit step | Q34: scripts, compose and both Dockerfiles changed, so the recorded run is stale. |

Security fixes checked in passing: T1 (M-1 subclass), T2 (L-2 equality), T3
(post-install check), G1 (M-3 allowlist), C1 (isolated), C2 (N2) KILLED.

## Blocking

- **R1-B1. The fixed backend subnet 198.18.80.0/24 is a regression and a design deviation (decision a).**
  - Docker refuses a second network with an overlapping pool. Measured: a second `docker network create` with the same subnet fails with "Pool overlaps with other one on this address space". During this review the security agent had project `ke-sec-r1-24255` up holding 198.18.80.0/24, and a create on that subnet failed the same way.
  - So `verify.sh full` cannot run while the live stack, another worktree verify, or any other project of this compose file is up. That breaks the §2.2 isolation claim ("never collides with the live stack or with a parallel verify run"). It also makes the stack fail on any host whose LAN, VPN or another bridge already uses that /24.
  - The architect rejected exactly this in the rework-1 design (`docs/architecture.md` near line 2119: "An explicit ipam subnet so tests know the gateway address: this adds a network literal to config, and the test can derive the address"). The developer adopted it without a ruling.
  - PS-1.2 (as ruled 2026-10-18) flags every non-loopback address literal outside config and compose variable defaults. The scanner only catches declared values, so the gate stays green, but the subnet is an undeclared address literal in a compose file.
  - **Fix (architect picks; either needs a test):**
    - (i) make it configuration: `${KE_BACKEND_SUBNET:-...}` and `${KE_BACKEND_IP_RANGE:-...}`, with entries in `.env.example`. The verify host half then exports a per-run subnet that differs from the `.env.example` value. Add a VerifyHostHalfTest case that asserts this. Or
    - (ii) drop `ipam` and change the M-2 probe. With `isolated`, Docker gives `.1` to a container; without it, the bridge (host) owns `.1`. The probe can resolve the stack service names, treat a `.1` owned by a service as isolated, and otherwise require no RST. This keeps zero network literals.
- **R1-B2. The Docker Engine >= 28 refusal (the M-2 control on older engines) is untested and fails open on empty output (decision c).**
  - The fixture gap shaped production code. In `launch.sh` the check is `if [ -n "$engine" ] && ! at_least ...` and in `launch.ps1` it is `if ($engine) { ... }`, so both accept an empty version. That passes only because `tests/fake_docker.py` exits 0 with no output for any non-compose call.
  - L3 (delete the sh check) SURVIVED. L6 (delete the ps1 check) was killed only incidentally, by PSScriptAnalyzer flagging the mutant text, not by any launch test.
  - Engines older than 28 silently ignore `gateway_mode_ipv4: isolated` (the scripts say so), so this check is the only thing that enforces M-2 there.
  - **Fix:**
    - The fake answers `docker version --format ...` with `FAKE_DOCKER_ENGINE` (default a passing version, e.g. 28.0.0).
    - Both scripts refuse an empty version.
    - `_LaunchResolvedBase` gains these cases, for sh and ps1, each asserting no `compose up`: 27.5.1 refused, 28.0.0 accepted, `docker version` non-zero refused, empty refused.

## Developer decisions: verdicts

- **(a) Fixed ipam subnet: rejected.** It should not be a literal. A `.env` value with a default alone is not enough: verify must also override it per run, or the subnet goes away (option ii). See R1-B1.
- **(b) M-2 on Docker Desktop: accepted, with a gap noted.**
  - Measured here (Desktop, server 29.5.2): the probe of `.1` gives identical results with and without `isolated` (ports 22 and 6006 time out, 80 gives EHOSTUNREACH). The runtime test cannot discriminate locally.
  - Dropping `isolated` is caught on every platform by the static `test_backend_bridge_gateway_is_isolated` (C1 KILLED).
  - Whether the runtime probe discriminates on a Linux CI runner is plausible but unmeasured. The host would answer on the bridge IP through INPUT with an RST, which the test rejects. The architecture asked for the errno to be recorded on both settings; it was not. See N-6.
  - `ip_range` dropped (C3) is not caught statically. The developer reports it is caught at runtime (RST from a stack container). This is moot if R1-B1 picks option (ii).
- **(c) Empty `docker version` in the fake: not acceptable as a recorded gap.** The script code was written to pass it. See R1-B2.

## Lint (question 3)

- **Coverage:** complete today. Every tracked or untracked `*.sh` (10) and `*.ps1` (3) in the repo is linted, and no extension-less shell scripts exist. The `find scripts -maxdepth 1` for ps1 would miss future ps1 files in subdirectories, and the test helper has the same blind spot (N-5).
- **`PSAvoidUsingWriteHost` exclusion:** justified. These are interactive console scripts, and `Write-Output` would put messages on the success pipeline. Per-file `SuppressMessageAttribute` would be narrower but is not required.
- **Pins:**
  - Sound: pwsh 7.4.21 by sha256 (x64 and arm64), shellcheck `0.9.0-1` exact apt pin (fails loudly if bookworm drops it), and PSScriptAnalyzer 1.25.0 by version.
  - Nits (N-7):
    - `POWERSHELL_TELEMETRY_OPTOUT` is set in an `ENV` after the `RUN` that invokes pwsh, so Install-Module runs with telemetry on.
    - PSScriptAnalyzer is version-pinned only. `Save-Module` plus a nupkg sha256 would match the pwsh control.

## Test integrity (question 4)

- **`globals_patched` / `isolated`:** after a set, get returns the installed provider. This matches real OTel for a first install. Real OTel ignores a second set, and the fixture lets the last one win. That case is covered explicitly by `test_configure_tracing_refuses_if_its_provider_is_not_the_global` ("set ignored"), and T3 is killed by it. Not weakened.
- **`LaunchScriptTest`:** only the fake changed. Every case and assertion is as before (refusals, controls, `--wait --no-build`).
- **`VerifyRequiresTestsRunTest`:** a passing `lint.sh` stub only, and the Ran/sentinel assertions are unchanged. Lint failure is covered separately (`VerifyCallsLintTest`, LN6 KILLED).
- **Overall:** no test was removed or skipped and no threshold was lowered. pwsh absence is `fail`, never `skip`.

## Nits

- **N-1 (LN2 SURVIVED):** `test_lint_covers_every_shell_and_powershell_script` accepts any pwsh call that mentions `scripts`. Require each ps1 path.
- **N-2 (LN4 SURVIVED):** no planted Warning-severity PSScriptAnalyzer finding. Add one, e.g. an unused variable or `PSUseApprovedVerbs`.
- **N-3 (L4 SURVIVED):** the launch "port without host_ip counts as 0.0.0.0" path is untested in sh and ps1. Add a `FAKE_COMPOSE_RESOLVED` case.
- **N-4 (G2 SURVIVED):** the gateway upstream charset check is redundant given the exact allowlist match and port digits. Add a case where it is the only guard (an allowlist entry containing a metacharacter), or record it as defence in depth. Security has the final say.
- **N-5:** ps1 discovery is `-maxdepth 1` in lint.sh and in its test.
- **N-6:** record the M-2 probe errno per address and port on the first Linux CI run, e.g. the test prints them. This closes the architecture requirement and decision (b).
- **N-7:** gates image telemetry ENV order and PSScriptAnalyzer hash (above).
- **N-8:** with `core.autocrlf true` set system-wide in the gates image, `git add` in the lint test temp repos floods the log with LF/CRLF warnings (`green-rework1.txt:564-601`). Use `-c core.autocrlf=false` there.

Deferred by the orchestrator, not re-raised: review N3-N6, N8-N11 and security L-5.
