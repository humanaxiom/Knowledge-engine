# Security re-audit: platform-stack-up, rework 1 of 5, 2026-10-19

- Scope: the uncommitted diff against d26bec6 plus untracked files on agent/platform-stack-up, after the "rework 1 GREEN" section by the developer.
- Runtime: scratch compose project ke-sec-r1-24255 (ports 47192/47193), scratch networks ke-sec-r1-ctl*, ke-sec-r1-net and ke-sec-r1-clash, and containers ke-sec-r1-gw* and ke-sec-r1-listener. All were removed with `down --remove-orphans --volumes`, and nothing ke-sec-* is left. No other project was touched. Images were used as built (`--no-build`), and none were re-tagged.
- Raw output: `docs/evidence/platform-stack/security-rework1-scan.txt`, sections R1 to R6.
- Disclosure: a first launch.sh pass used a docker shim that PATH never picked up (the `C:` colon). Those runs did a real `up` of the scratch project only. That included the dev 0.0.0.0 cases, which published 47192/47193 on all interfaces for a few minutes, in dev, as the ruling allows. The refusal results are unaffected because refusals exit before `up`. The rerun with a working shim is what R4 records.

**Verdict: PASS.** There are no critical or high findings. Of the earlier findings, M-1, M-2, M-3 (allowlist), L-1, L-2 and L-4 are closed, and L-3 is only partly closed. New: 1 medium and 4 low, none of them blocking.

## Closed
- **M-1 and L-2 (R1).** 8 shapes were run under both HARNESS_TRACING=off and otlp. Every forgery is refused with StartupRefused(telemetry.tracing) and 0 foreign spans:
  - a ProxyTracerProvider subclass swapped in as the global default proxy;
  - a ProxyTracerProvider subclass that is installed;
  - an `__eq__`/`__hash__` decoy matching a live engine provider;
  - an ignored `set_tracer_provider` whose `get` then returns a foreign provider;
  - a forged `__class__` property.

  When `set_tracer_provider` is ignored outright, otlp mode is refused by the post-install identity check, and off mode installs nothing (no-op, correct). The control starts.
- **M-2 (R2).** api and worker on the isolated backend:
  - 198.18.80.0, .1 and .127 time out, and every other host address returns ENETUNREACH: docker0, the VM eth0 and services1 addresses, and the edge gateway.
  - There is no default route, and host.docker.internal does not resolve.
  - In the host netns, no interface holds an address in 198.18.80.0/24. That is the decisive check: there is nothing host-side to reach.
  - Control: the gateway, which is on edge by design, reaches the same host listener. A plain internal network reproduces the original M-2 (an OPEN connection at its gateway).
  - The daemon rejects `isolated` on a non-internal network, so the option cannot be paired with a routable network by mistake.
- **M-3 (R3).** The gateway now refuses to start (exit 1, nginx never runs, the value is not echoed) in each of these cases:
  - the host is off the allowlist;
  - a trailing dot on either side;
  - IP-versus-name mismatches;
  - a `*` entry;
  - a suffix such as evil.ALLOWED;
  - IPv6;
  - quote or semicolon injection in KE_MODEL_UPSTREAM;
  - port 0, port 65536, a leading-zero port, no port, or two ports.

  Case folding and allowlist whitespace are normalised, and that is safe. Decimal, hex and short IP forms pass only when the identical literal is on the allowlist. nginx sends those to DNS (it does not parse them as an address), so they are not a bypass.
- **L-1 (R4).** launch.sh and launch.ps1 were run against real `docker compose config`. Both refuse all of these:
  - the `export`, spaced and colon forms of KE_BIND_ADDRESS;
  - a missing, empty or `export KE_ENV`;
  - KE_ENV=DEV;
  - duplicate keys (the last one wins);
  - CRLF;
  - IPv6;
  - a LAN IP;
  - a process-env override of a loopback file.

  The quoted, spaced and comment forms of dev warn and launch, matching what compose hands the gateway. An empty bind address in prod resolves to loopback and launches. Engine 27.5.1 and 27.99.99 are refused, and 28 or later is accepted. See L-6.
- **L-4.** There are no profile paths in the diff or the evidence (R6).
- **Secrets (R6).** The secret-pattern scan over the 18,752-line diff plus the untracked files found only the `<redacted>` placeholders in windows-proof.txt. There are no keys, tokens, private keys or credentialed URLs.
- **Gates image (R5).**
  - The pwsh 7.4.21 x64 and arm64 sha256 pins equal the GitHub release asset digests, uploaded by the PowerShell team, and `sha256sum -c` gates the install.
  - shellcheck 0.9.0-1 comes from signed Debian apt, and the version is pinned.
- **engine/worker.py.** It calls `startup()` before idling. In prod with auth off, the worker crash-loops (refusal), as intended. It adds no input surface.
- **lint.sh.** shellcheck `-x` only parses the files. Its escaping of the ASCII apostrophe (U+0027) is correct. See L-7.

## Medium (non-blocking)
- **M-4: the M-2 runtime regression test cannot fail.**
  - `tests/integration/test_stack_up.py` `_bridge_gateways()` probes subnet+1.
  - With `ip_range: .128/25` and no `isolated` mode, Docker gives the bridge (host side) the first ip_range address, .128, not .1. In R2 control 3, .1 timed out while .128 returned HOSTNET-HIT.
  - So if isolation is lost (option dropped, an engine below 28 ignoring it, or L-6), the test still passes. The note in the GREEN section that Docker Desktop "cannot tell isolated from not" has the same cause.
  - The control itself holds at runtime, and the static compose test still pins the driver option.
  - Fix:
    - in `test_gates_it_has_no_route_out`, also probe the first address of the ip_range (or every non-container address in the subnet);
    - better, have the verify host half assert `docker network inspect PROJECT_backend` shows `gateway_mode_ipv4=isolated`;
    - kill the test with a mutant compose file that drops the option.

## Low (non-blocking)
- **L-3 (partly closed): other templated KE_* values still inject nginx config and bypass the M-3 allowlist (R3, R3b).**
  - KE_GATEWAY_MODEL_LISTEN, KE_API__LISTEN_PORT (from KE_API_LISTEN) and PHOENIX_PORT are substituted unchecked, and the gateway starts.
  - Demo: with KE_MODEL_UPSTREAM empty, an injected `location /x { proxy_pass http://1.1.1.1:80; }` returned a 301 from 1.1.1.1. A stream payload added listeners on 9999 and 9998.
  - KE_GATEWAY_API_LISTEN and KE_GATEWAY_PHOENIX_LISTEN payloads made nginx fail (emerg).
  - Only the operator .env can do this.
  - Fix: an entrypoint check that every substituted port (`KE_GATEWAY_*_LISTEN`, `KE_API__LISTEN_PORT`, `PHOENIX_PORT`) is a decimal 1 to 65535, exit 1 otherwise; add these to the entrypoint tests.
- **L-6: the Engine version check fails open.**
  - Both scripts accept empty `docker version` output, which the developer flagged.
  - launch.sh also accepts "garbage" and " 27.1.1" (a leading space), because sort -V ranks them at or above 28.
  - Real Docker always prints a version, so this needs an odd engine or shim. But that is exactly the case where `isolated` would be silently missing, and M-4 would not notice.
  - Fix: require a numeric dotted version and refuse anything else, including empty; fix `tests/fake_docker.py` to answer `version`.
- **L-7: lint.sh can execute code from a PowerShell filename (R5b).**
  - lint.sh escapes only U+0027, but PowerShell also treats U+2018, U+2019, U+201A and U+201B as single-quote delimiters.
  - A file named scripts/x(U+2019); CODE; (U+2019).ps1 ran CODE in the gates container (root, read-write repo) and created a marker file. The U+0027 form is escaped correctly.
  - It needs a committed filename, which is less visible in review than a code change.
  - Fix: pass the paths as arguments (pwsh -File with a fixed analyzer script and the paths as args) or through an env var, never inside generated source. Or refuse non-ASCII paths.
- **L-8: PSScriptAnalyzer is pinned by version only.**
  - Install-Module from PSGallery, which is set Trusted at build time, has no hash or signature check.
  - Gallery versions are immutable, and the module is Microsoft-signed, but nothing verifies that.
  - Fix: Save-Module plus a sha256 check of the nupkg, or Get-AuthenticodeSignature to require the Microsoft signer.

## Info
- **Fixed backend subnet (R2).** A second project on one host gets "Pool overlaps". A verify.sh full run alongside a live stack, or two verify runs in parallel, fails at network creation. This contradicts the section 2.2 / docker-compose.verify.yml claim that verify never collides with the live stack. It is availability, not security; it fails closed. Reviewer, please weigh it. A per-project subnet (for example, from an env var with a default) would fix it.
- **In-process trust (I3).** Writing the private trace._TRACER_PROVIDER after startup redirects later spans (late_swap, R1). This is accepted by the ADR, and set-once is the OTel boundary.
- **A stray .env in the repo root.** It is gitignored, was created at 03:43Z during this audit by another process (not this audit: every run here set KE_ENV_FILE), and has the same keys as .env.example with different values. Its values were not read. Leave it, or let its owner remove it. It cannot be committed.
- **Carried forward:**
  - L-5 (gates-it runs as root with a read-write repo) stays deferred.
  - The neo4j healthcheck passes the password in argv inside the container.
  - Image CVEs were not scanned (docker scout is unavailable).
