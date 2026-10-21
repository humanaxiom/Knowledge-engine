# Security re-audit: platform-stack-up, rework 2 of 5, 2026-10-19

- Scope: the uncommitted diff against d26bec6 plus untracked files on agent/platform-stack-up, after "developer: rework 2 GREEN" and the tester's final verify (`green-rework2-final.txt`).
- Runtime: Docker Engine 29.5.2 (Docker Desktop), compose 5.1.4. Scratch projects were ke-sec-r2-m2, ke-sec-r2-other and ke-sec-r2-m2c-{noiso,nointernal}. Scratch containers were ke-sec-r2-l3-* and ke-sec-r2-listener. The verify overlay meant nothing was published. Images were used as built (`--no-build`); the gateway image's port check and templates hash-match the working tree. Everything was removed with volumes, nothing ke-sec-* is left, and no other project was touched.
- The launch.sh probes used a shim that was confirmed with `command -v docker` before any run. It never forwards `up`, and the env file was prod plus loopback.
- Raw output: `docs/evidence/platform-stack/security-rework2-scan.txt`, sections S1 to S6.

**Verdict: PASS.** No critical or high findings. M-2, M-4, L-3, L-6 and L-7 are closed, and so is F3 as stated. New: 2 low findings, plus info items.

## Closed
- **M-2 (S1), no ipam.**
  - The backend gets an auto pool (192.168.112.0/20, no Gateway key), and worker holds .1.
  - From api and worker, every address in the host netns returns ENETUNREACH: docker0, eth0, services1, all 20 bridge gateways and the edge gateway.
  - Unassigned subnet addresses time out, and host/gateway.docker.internal do not resolve.
  - The only route is the connected /20, with no default route.
  - The host netns holds no address in the backend subnet.
  - Control: the gateway (edge) reaches the same listener.
- **M-4 (S1).** The smoke inspect check works and the proof is sensitive.
  - Against the scratch stack, smoke passes ("internal with gateway_mode_ipv4=isolated").
  - With a scratch override `driver_opts: !reset {}`, smoke fails (rc 1, empty gateway_mode_ipv4). The bridge gateway then answers OPEN HOSTNET-HIT, which reproduces M-2.
  - Also making the network non-internal fails smoke too.
  - Holds on Engine 29.5.2. A 28.x engine was not available, so 28.0 itself is untested. On an engine below 28, the stored option may show in inspect without being honoured. The launch Engine >= 28 gate (L-6) covers that, and verify full runs launch before smoke.
- **L-3 (S2).** Every substituted template variable is checked. The templates use KE_GATEWAY_{API,PHOENIX,MODEL}_LISTEN, KE_API__LISTEN_PORT, PHOENIX_PORT, KE_MODEL_UPSTREAM (11-ke-upstream-check) and NGINX_LOCAL_RESOLVERS.
  - The 5 port variables were each tried with 15 bad values, and every one exits 1 before nginx starts, without echoing the value. The bad values were: server/location/semicolon injection, a newline, leading and trailing space, plus, minus, a leading zero, 0, 65536, 20 digits, empty, hex and full-width digits.
  - Unset fails closed too, and 1 and 65535 start.
  - An injected NGINX_LOCAL_RESOLVERS is overwritten by the image's 15-local-resolvers.envsh, and compose does not pass it anyway.
  - The gateway environment is an explicit list, with no env_file.
  - The drift test derives the list from the templates.
  - No template variable is left unchecked.
- **L-6 (S3).**
  - launch.sh refuses all of these with rc 1, before compose config/up:
    - empty, garbage, and a leading or trailing space;
    - -rc builds (28 and 29), 27.5.1 and 27.99.99;
    - 28, 28.0 and v29.5.2;
    - multi-line output, CR, and non-ASCII digits;
    - a daemon error, with or without stdout.
  - It accepts 28.0.0, 29.5.2 and 100.0.0.
  - launch.ps1, by static review:
    - an anchored ASCII MAJOR.MINOR.PATCH regex (`\z`, no multiline) plus LASTEXITCODE refuses empty, garbage, a leading space, -rc, multi-line, a daemon error and 27.x;
    - an out-of-range major throws under ErrorActionPreference=Stop, which fails closed;
    - a missing docker throws as well.
- **L-7 (S4).** No probe filename ran code:
  - U+2018, U+2019, U+201A and U+201B;
  - U+0027, ASCII double quote and U+201C to U+201E with subexpressions;
  - pwsh subexpressions, bash command substitution and bash backticks;
  - pwsh backtick escapes, and env references.

  The fixed -Command text plus the env-var path list removes the source-injection class. A newline in a path is refused, and lint exits 1.
- **F3 (S5).** teardown no longer touches another project's containers. ke-sec-r2-other's one-off survived.
- **Secrets and profile paths (S6).** Scanned 26,582 lines of diff plus untracked files, including all rework-2 evidence. There are no keys, tokens, PEM keys or credentialed URLs. `.env.example` holds only changeme-* placeholders. There are no user-profile paths.

## Low (non-blocking)
- **L-9: teardown leaves its own profile containers and backend network, and still exits 0 (S5).** After `scripts/teardown.sh --volumes` on a project with its own gates/gates-it service containers and a gates-it-run-* one-off:
  - all three keep running, and the project's backend network stays ("Resource is still in use");
  - compose 5.1.4 exits 0, so teardown exits 0;
  - so verify's N7 check ("a leaked project is not a pass") does not fire.

  In normal runs `run --rm` removes the one-off. But after an interrupted verify (killed client), a root gates-it container with the repo mounted read-write can stay attached to the backend unnoticed. teardown.ps1 has the same command, so it has the same behaviour (static).

  Neither the gates profile flags nor --remove-orphans removes the run container.

  Fix:
  - after down, list the containers and networks labelled com.docker.compose.project=PROJECT;
  - remove what is left, or exit non-zero naming it;
  - always scope this by the resolved project name, never the default.

  Reviewer: this touches N7.
- **L-10: a .ps1 with square brackets in its name escapes PSScriptAnalyzer (S4).**
  - `Invoke-ScriptAnalyzer -Path` treats the path as a wildcard.
  - scripts/b[1].ps1 containing Invoke-Expression gives lint PASS. The same content in plain.ps1 gives lint FAIL (PSAvoidUsingInvokeExpression).
  - This is a gate bypass, not code execution. It needs a committed, oddly named file.
  - Fix: refuse wildcard characters (`[ ] * ?`) in ps1 paths, as newline is, or escape them with WildcardPattern.Escape; add the case to the L-7 tests.
- **Carried forward, still deferred:**
  - L-5: gates-it runs as root with a read-write repo.
  - L-8: PSScriptAnalyzer is pinned by version only.

## Info
- The launch.sh version check accepts 029.0.0 (it parses as 29) and a 20-digit major (a positive bash 64-bit wrap). No real engine reports either, and producing them needs a hostile docker on PATH, which already owns the launch. launch.ps1 refuses the huge case.
- -rc and distro suffixes (for example 28.2.2+dfsg1) are refused. That fails closed, an availability cost only.
- The earlier "Pool overlaps" info is resolved: the auto pool allowed four scratch backends side by side with the other stacks on this host.
- smoke.sh briefly creates ./.env.smoke.XXXXXX in the repo root (trap-removed; none left after these runs).
