# architect: rework round 1 design (platform-stack-up 2a), 2026-10-19

Asked: design the fixes for orchestrator rework round 1 (review N1, B3, B5,
B6, the developer-decision verdicts, N7; security M-1, M-2, M-3, L-1, L-2,
L-3) in `docs/architecture.md` §2.1, §2.2, §2.4, §2.6, ADR-KE-009, -010 and
-011. Docs only. Only `docs/architecture.md` was touched (the tester is
writing tests at the same time).

## Decisions (where they are recorded)
- **N1 ports (§2.4 Ports, ADR-KE-011 port amendment):** compose long syntax
  `target` / `host_ip` / `published` (+ `protocol: tcp`). `host_ip` is exactly
  `${KE_BIND_ADDRESS:-127.0.0.1}`, `published` is `${KE_<X>_PORT:-<47100–47199>}`,
  and `target` is always a `${KE_GATEWAY_<X>_LISTEN:-<n>}` variable (N3). The
  API listen port is `KE_API_LISTEN`, passed in as `KE_API__LISTEN_PORT`, and
  listed in `.env.example`.
- **M-2 (§2.1 new paragraph, ADR-KE-009/-011):** `backend.driver_opts:
  com.docker.network.bridge.gateway_mode_ipv4: isolated`. Docker Engine ≥ 28
  is a quickstart prerequisite. Launch checks the server version too,
  because older engines ignore the option silently (see R1). `offline`
  should take the same option in platform-offline.
- **B1 + M-2 runtime proof (§2.2):** `test_gates_it_has_no_route_out` needs
  `errno in {ENETUNREACH, EHOSTUNREACH}`, never a timeout, in about 2 s for
  TEST-NET-1. A connect to the backend bridge gateway (subnet first host,
  derived in the container) must not be `ECONNREFUSED` or succeed. The
  tester records the measured errno for both settings.
  Static: `test_backend_network_isolated_from_host`.
- **M-3/L-3 (§2.4 Gateway upstream check, ADR-KE-011 rework amendment):**
  new `docker/gateway/11-ke-upstream-check.sh`, before
  `20-envsubst-on-templates.sh`. It allows `KE_MODEL_UPSTREAM` to be empty;
  otherwise the value must be a strict `host:port` (IPv4 or DNS labels, port
  1–65535 with no leading zero, newline refused first) whose case-folded host
  is on `KE_EGRESS_ALLOWLIST`, normalised like `engine.egress.normalise_host`.
  Every other template variable (`KE_GATEWAY_*_LISTEN`, `KE_API__LISTEN_PORT`,
  `PHOENIX_PORT`) must be an integer. A drift test ties the template `${…}`
  names to the validated set. It never echoes a value. DR30 now has three
  layers.
- **M-1/L-2 (ADR-KE-010 new amendment):** `type(p) is ProxyTracerProvider`;
  identity via `any(p is provider …)`; after `set_tracer_provider(built)`,
  refuse unless `trace.get_tracer_provider() is built`.
- **B3/L-1 (§2.4 Bind address, Launch; Scripts table):** one compose argument
  list used for `config --format json gateway` and for `up`. Launch reads
  `services.gateway.environment.KE_ENV` and the ports' `host_ip`/`published`.
  There is no `.env.example` fallback. Missing, empty or non-exact `dev`
  counts as not dev; a port with no `host_ip` counts as `0.0.0.0`; no ports
  means nothing to check; a failed `config` fails launch. Bash extracts keys
  line by line without stripping whitespace inside values, so it fails
  closed; ps1 uses `ConvertFrom-Json`. A real-compose smoke case
  (`export KE_BIND_ADDRESS=0.0.0.0`, `KE_ENV=prod`) proves the fixture shape.
- **B5 (§2.2 Lint):** `scripts/lint.sh` runs shellcheck over
  `scripts/**/*.sh` and `docker/**/*.sh`, and PSScriptAnalyzer (Warning+Error)
  over `scripts/*.ps1`, in the gates image only. The verify.sh container half
  calls `lint.sh` and then `test.sh` in both modes. Tools are pinned and
  installed at build time.
- **B6 + N7 (§2.2):** a fast test copies verify.sh into a temp tree with stub
  stage scripts and a fake `docker`. It asserts order, failure exits,
  teardown on success, failure, INT and TERM, the overlay in `COMPOSE_FILE`,
  and a per-run project name. A failed teardown prints a warning, and the
  rc is unchanged.
- **Developer decisions recorded (§2.4 end, §2.4 Worker):** the worker
  placeholder `python -m engine.worker` runs `startup()` and then idles
  (B2), with entrypoint unit tests patching `uvicorn.run` and `signal.pause`.
  The literal postgres `engine` user/db is accepted for 2a (N4 drift test
  before 2b readyz). Compose warnings with no `.env` are accepted; the B4
  smoke asserts `config` succeeds and every `host_ip` is 127.0.0.1.
- **Stale names:** `test_socket_guard_blocks_outbound` is replaced by "the
  in-process socket-guard test" in §2.2, §2.6 and ADR-KE-009. *Proposed*
  markers are dropped on names the requirements have now adopted.

## Suggested first tests (tester)
1. M-1/L-2 subtests in `test_provider_not_built_by_engine_is_refused`, plus
   `test_configure_tracing_refuses_when_install_is_ignored`.
2. `test_gateway_upstream_check_refuses_off_allowlist` and the template
   variable drift test.
3. `test_backend_network_isolated_from_host`.
4. Launch fake-docker cases on resolved config (sh, and ps1 under pwsh).
5. api/worker entrypoint tests; the lint static test; the verify.sh
   host-half test; then the amended `test_gates_it_has_no_route_out`.

## For the orchestrator
- **R1:** the launch Docker Engine ≥ 28 check goes slightly beyond the
  orchestrator's "state it in the quickstart" (security M-2 asked for both).
  I designed it in because the option is ignored silently on older engines.
  Confirm, or strike it.
- **R2 (drift, not changed):** §2.4 says `.env.example` sets
  `KE_MODEL_UPSTREAM` to the `aria-gb10-2` host and lists the allowlist as
  `gateway,<upstream host>`. The working-tree `.env.example` has both
  empty. Decide which one is intended. With the upstream check, an empty
  upstream is valid. A non-empty one needs its host on the allowlist, or
  the gateway will not start.
- The gates image gains pwsh and PSScriptAnalyzer, which makes the image
  bigger and the cold build slower (N10 timing).
- The Windows run (Q31/Q34) must be repeated: compose, scripts and
  Dockerfiles all change.
