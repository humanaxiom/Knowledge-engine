# Security audit: platform-stack-up (2a), 2026-10-19

- Scope: uncommitted diff against d26bec6 plus untracked files on agent/platform-stack-up.
- Runtime checks ran in a scratch compose project, ke-sec-15807, with published ports 47190 and 47191. It was torn down with down --remove-orphans --volumes, and no containers, networks or volumes were left. No other project was touched.
- The scratch build re-tagged the shared ke-app, ke-gateway and ke-gates images from the same tree (cache hits).
- Raw output: docs/evidence/platform-stack/security-scan.txt, sections §1 to §10 below.

**Verdict: PASS.** There are no critical or high findings. There are 3 medium findings and 5 low ones (none of them block), plus info notes.

## Checked and holding
- **Exposure:**
  - Only gateway publishes, on 127.0.0.1:47190 and 127.0.0.1:47191. From the host, both ports are closed on every LAN, Tailscale and vEthernet IP and open on loopback. A control port published on 0.0.0.0 was open on all of them (§7).
  - The model forward (8102) and the stores publish nothing.
  - backend is internal=true, and only the gateway sits on edge.
- **gates-it:**
  - 1.1.1.1, 8.8.8.8, 169.254.169.254 and the edge gateway IP are unreachable.
  - No external names resolve.
  - It reaches only backend services (§7, but see M-2).
- **Bind address, three places.** Envs: dev, ci, prod, unset, DEV and " dev". 34 values: 0.0.0.0, 127/8, 10.x, 128.0.0.1, IPv6 forms, garbage, empty, whitespace, tab, newline, leading zeros, short forms, hex, CIDR, port suffix, hostnames, a command substitution.
  - **Gateway script:** accepts only 127/8, empty or unset outside dev. IPv6 and garbage are rejected in every env, and so are DEV and " dev". The value is never echoed (§1).
  - **Gateway entrypoint:** on refusal the entrypoint exits 1 and nginx never starts. The good case starts (§2).
  - **Engine:** a malformed value is a ConfigError that names the variable and does not leak the value. A non-loopback value is StartupRefused(KE_BIND_ADDRESS) outside dev. Empty means 127.0.0.1 (§3).
  - **Compose:** rejects whitespace, garbage and 127.1 itself (invalid ip address).
  - **launch.sh, process env:** correct in every env (§4). See L-1 for the env-file case.
  - **launch.ps1 (static review):** same logic. The .NET end anchor also matches before a trailing newline, but that fails safe: compose then rejects the IP.
- **M5:**
  - All six requested shapes are refused with StartupRefused(telemetry.tracing) and 0 spans or dials during startup, under both HARNESS_TRACING=off and otlp. The shapes: explicit session.proxies, a rerouting adapter, a rewritten _endpoint, a processor subclass, a Session subclass, and an SDK-subclass decoy.
  - The control (build_provider) is accepted, with 0 foreign spans (§6).
  - Forgery is possible, though: see M-1 and L-2.
- **Images:**
  - All 7 external images are digest-pinned, and each pin equals the current index digest at the publisher (§8).
  - Sources: Docker Official Images (postgres, neo4j, python) and vendor images (nginxinc, valkey, arizephoenix, astral-sh).
  - The gateway runs as nginx (101). /docker-entrypoint.d is root-owned 0755, so the runtime user cannot replace the check.
  - api and worker run as ke (10001). /app is root-owned.
  - There is no .env* in ke-app or ke-gateway, and no secret in image ENV or layers.
- **Compose secrets:**
  - POSTGRES_PASSWORD and NEO4J_AUTH come from env with no default. No changeme value appears in the compose files or Dockerfiles.
  - An empty value makes postgres and neo4j refuse to start (verified).
- **verify.sh:**
  - mode is allow-listed, and the project name is ke-verify- plus two RANDOM values.
  - COMPOSE_PROJECT_NAME, COMPOSE_FILE and KE_ENV_FILE are exported before the EXIT trap, so teardown can only hit the verify project.
  - The overlay resets the ports, and no env or argument value reaches an eval.
- **Dependencies:** fastapi 0.146.0, starlette 1.9.0, uvicorn 0.54.0, click 8.5.0 and annotated-doc 0.0.5, all hashed from PyPI. pip-audit over the locked no-dev set finds no known vulnerabilities (§9).
- **api:** docs, redoc and openapi are disabled, and /healthz has no I/O.
- **Traces:** the new code adds no span attributes beyond hostnames and env names.

## Medium (non-blocking)
- **M-1: a ProxyTracerProvider subclass bypasses M5.** The check is engine/telemetry.py verify_provider, which returns early on isinstance(provider, ProxyTracerProvider).
  - A foreign subclass of ProxyTracerProvider whose get_tracer returns tracers from its own SDK provider is accepted as "nothing installed".
  - configure_tracing then calls trace.set_tracer_provider(build_provider(...)). OTel ignores that, because the global can only be set once. configure_tracing still returns True, and every engine span goes to the foreign sink: 5 startup spans in both modes (§6, proxy_subclass).
  - No engine internals are touched, which contradicts the ADR-KE-010 M5 consequence that any foreign provider is refused.
  - Fix:
    - accept only the unset proxy (type(provider) is ProxyTracerProvider);
    - after set_tracer_provider, check that the global provider is the one just built, and refuse otherwise;
    - add the shape to test_provider_not_built_by_engine_is_refused.
- **M-2: backend is internal but not isolated from the host.**
  - Any backend container (api, worker, phoenix, the stores, gates-it) reaches services bound to 0.0.0.0 on the Docker host through the bridge gateway, 192.168.80.1.
  - Proof: a listener on the host network at 0.0.0.0:47199 was reached from the api container (§7).
  - On a Linux deployment host, that includes a local model server (for example Ollama on 11434), a proxy, sshd and similar services. All of them bypass the gateway and the egress allowlist.
  - Fix:
    - set the backend driver option com.docker.network.bridge.gateway_mode_ipv4=isolated (Docker 28 or later; this host has 29.5.2);
    - add a check that the bridge gateway is unreachable to test_gates_it_has_no_route_out;
    - require Docker Engine 28 or later in launch and in the quickstart.
- **M-3: the gateway model forward does not enforce the egress allowlist.**
  - With KE_MODEL_UPSTREAM=one.one.one.one:80 and KE_EGRESS_ALLOWLIST=gateway, gates-it got a Cloudflare response through gateway:8102 (§7).
  - The engine check_egress refuses that config, but only in api and worker. The gateway still forwards for every backend container, including third-party images.
  - The target is fixed per config and not chosen by the client.
  - Fix: in the gateway entrypoint, require KE_MODEL_UPSTREAM to be empty or a strict host:port, with its host in KE_EGRESS_ALLOWLIST (exact, case-folded). Otherwise exit non-zero. This also closes L-3.

## Low (non-blocking)
- **L-1: launch.sh and launch.ps1 read the env file differently from compose.**
  - With KE_ENV=prod in .env, compose resolves the dotenv forms "export KE_BIND_ADDRESS=0.0.0.0", "KE_BIND_ADDRESS = 0.0.0.0" and "KE_BIND_ADDRESS: 0.0.0.0" to host_ip 0.0.0.0. launch misses all three and launches anyway (§4, §5).
  - Also, when KE_ENV is absent from .env or written "export KE_ENV=prod", launch falls back to .env.example, sees dev, and only warns.
  - The gateway check stops the publish in every case, so there is no exposure. Still, the Q33a layer fails open.
  - Fix: read the resolved values from docker compose config --format json (the gateway host_ip and environment KE_ENV).
- **L-2: the registry checks equality, not identity.**
  - Membership in the WeakSet compares with == and the hash. A decoy that overrides __eq__ and __hash__ to match a live engine-built provider is accepted (§6, decoy_eq_hash_forgery).
  - It needs a live engine provider and deliberate code.
  - Fix: check identity with an any(p is provider ...) loop.
- **L-3: nginx config injection through envsubst-substituted KE_* values.**
  - A KE_MODEL_UPSTREAM value that closes the quoted map default and opens a new server block adds a second forward (listening on 9999 in the test), and nginx starts (§7).
  - Only the operator .env can do this. Fixed by the M-3 grammar check, and the listen ports should be checked as integers too.
- **L-4: a profile path in the evidence.** docs/evidence/platform-stack/windows-proof.txt line 565 contains the Windows user-profile temp path (the L8 class). Redact it before commit.
- **L-5: gates-it runs as root with the repo bind-mounted read-write, and is now networked.**
  - It can read a real local .env, write to .git/hooks, and reach the stores and the model forward.
  - This is pre-existing for gates (which has no network) and is acceptable for a dev gate. Consider a read-only mount plus a writable evidence path, or a non-root user.

## Info (accepted or residual)
- **Accepted by the ADR (I3, in-process trust):**
  - build_provider with a foreign exporter;
  - an extra processor added to an engine-built provider;
  - a direct add to _ENGINE_PROVIDERS.
- **Allowed by ruling:**
  - dev with a non-loopback bind starts with a warning, and .env.example ships KE_ENV=dev;
  - Phoenix and api are unauthenticated on loopback until auth-audit.
- **Container details:**
  - The neo4j healthcheck passes the password in argv inside the container.
  - The local ke-* images have no pull_policy. The docker.io/library namespace is not squattable, so a missing image just fails to pull.
- **Docker version:** use Docker 28 or later on Linux, where loopback-published ports can no longer be reached from the LAN. Verified here on 29.5.2.
- **Not scanned:** image CVEs (docker scout unavailable).
