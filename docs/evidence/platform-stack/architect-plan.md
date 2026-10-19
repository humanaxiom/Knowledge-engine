# platform-stack: architect plan step (2026-10-19)

- **Asked** (orchestrator):
  1. Apply the 2026-10-19 port ruling to §2.4 and ADR-KE-011.
  2. Check §2.1, §2.2 and §2.4 against F-A.
  3. Plan security M5 as an ADR-KE-010 amendment.
  4. Order the first tests.
  - Touch only `docs/architecture.md`; the analyst is editing the requirements concurrently.
- **Read:**
  - the handoff `docs/handoffs/platform-stack.md`;
  - the umbrella `docs/handoffs/platform-skeleton.md` (F-A/Q30 and the port ruling);
  - `docs/handoffs/archive/platform-config.md`;
  - `docs/evidence/platform-config/security-rework2.md` (M5, I3);
  - `engine/telemetry.py`, `tests/support.py`, `docker-compose.yml`, and PS-2.x in `docs/requirements.md` (read only).

## 1. Port ruling (§2.4, ADR-KE-011 amendment)
- **Published ports.** Every published port is `${KE_BIND_ADDRESS:-127.0.0.1}:${KE_<X>_PORT:-<47100–47199>}:<container port>`. Only `gateway` publishes:
  - API: 47100 → `KE_GATEWAY_API_LISTEN`
  - Phoenix: 47101 → `KE_GATEWAY_PHOENIX_LISTEN`
- **Container ports.** These are gateway listen-port variables that compose and the nginx envsubst templates share. The developer picks their defaults (unprivileged, outside 47100–47199). `phoenix` itself stops publishing.
- **Drift.** Every compose `${VAR:-default}` must equal `.env.example` (`test_compose_defaults_match_env_example`, which generalizes the phoenix drift test).
- **Bind address.** `KE_BIND_ADDRESS` is an IPv4 literal. IPv6 is out of scope (the short syntax makes it ambiguous).
- **Refusal outside `dev` until auth-audit, in two places:**
  - engine startup refusal 6, `Settings.bind_address`, which names `KE_BIND_ADDRESS`;
  - the gateway entrypoint script `docker/gateway/10-ke-bind-check.sh`, which exits non-zero.
  - The gateway check is needed because the gateway starts without `api` (§2.4 Images). The engine refusal alone would leave Phoenix on the LAN.
  - In `dev`: a warning. Accepted residual: someone editing the compose file by hand.

## 2. F-A drift check (§2.1, §2.2, §2.4)
- §2.1 and §2.4 already matched F-A: `gates-it` on `backend` only, no socket, model reached through the gateway. The only change was adding the bind address to the gateway row.
- **Drift fixed in §2.2, ADR-KE-009 and ADR-KE-003.** The `tests/integration` socket-guard fixture and `test_socket_guard_blocks_outbound` were still the design, although PS-2.7 superseded them.
  - The fixture is dropped: it could not see libpq, and the internal `backend` network is the boundary.
  - The runtime proof is the *proposed* `test_gates_it_has_no_route_out`.
- **Test names aligned to PS-2.7:**
  - `test_gates_it_network_topology` → `test_gates_it_internal_only_and_no_socket`
  - `test_model_skip_reason_names_upstream` → `test_model_tests_skip_with_named_reason`
  - `test_healthz` is integration, as PS-2.4 says; it was fast in §2.6.

## 3. M5 (ADR-KE-010 amendment, status proposed)
- **Chosen: (c), an engine-owned provider used by the tests.**
  - `engine.telemetry.build_provider(exporter, *, project_name)` is the only constructor and records the provider in a module-private WeakSet.
  - `verify_provider` accepts only a Proxy provider or a provider in that set, by identity.
  - The private-attribute inspection is deleted (`_verify_installed`, `_exporters_of`, `_sessions_of`, `_ignores_proxy_env`).
  - `tests/support.py` builds its provider with `build_provider(EXPORTER, project_name="harness-tests")` and `trace.set_tracer_provider`.
- **Rejected:**
  - (a) a registration API ships a production bypass;
  - (b) a resource-attribute marker is forgeable data, and it leaks into traces.
- **First failing test:** `test_provider_not_built_by_engine_is_refused`, with subtests for:
  - explicit proxies;
  - a rerouting adapter;
  - a rewritten `_endpoint`;
  - a plain in-memory provider built outside the engine.
  - Control: `test_engine_built_provider_is_accepted`.
- **Recommendation:** land it in platform-stack as unit 0. platform-stack is the first item where `startup()` runs in shipped processes (`api`, `worker`). The change is small, and it removes code.

## 4. First tests, platform-stack, in implementation order
- **Fast:**
  0. `test_provider_not_built_by_engine_is_refused` (if M5 is in scope)
  1. `test_compose_services_have_restart_policy`
  2. `test_compose_images_pinned_by_digest`
  3. `test_published_ports_use_bind_address` (*proposed*)
  4. `test_env_example_ports_in_range_and_unique`, `test_compose_defaults_match_env_example`
  5. `test_startup_refuses_non_loopback_bind_address` and `test_gateway_bind_check_refuses_non_loopback` (both *proposed*)
  6. `test_only_gateway_on_edge_network`
  7. `test_gates_it_internal_only_and_no_socket`
  8. `test_no_docker_socket_mounted`, `test_stack_services_have_no_bind_mounts`
  9. `test_harness_default_collector_matches_env_example`, `test_docs_name_current_phoenix_port`
  10. `test_model_tests_skip_with_named_reason`, `test_no_model_calls_in_unit_suite`
  11. `test_env_example_not_in_app_image`
  12. `test_quickstart_names_existing_scripts`, `test_claude_md_lists_verify_only_checks`
- **Integration (`gates-it`):**
  1. `test_gates_it_has_no_route_out` (*proposed*)
  2. `test_egress_allowlist_holds_with_network_access`
  3. `test_healthz`
  4. the three `test_readyz_*` tests
  5. `test_worker_consumes_noop_job`
  6. `test_readyz_reports_reachable_model_host` (skips by name when the host is unreachable)
- **Then:** smoke (`test_stack_services_healthy`, store stop/start), the lint gates, and the recorded Windows run (Q31).

## Needs a ruling (orchestrator / analyst)
- **R1, analyst:** adopt or rename the proposed criterion tests:
  - `test_published_ports_use_bind_address`
  - `test_startup_refuses_non_loopback_bind_address`
  - `test_gateway_bind_check_refuses_non_loopback`
  - `test_compose_defaults_match_env_example`
  - `test_gates_it_has_no_route_out`

  The port ruling and the PS-2.7 sentence "no test reaches any other outside host" have no named test yet.
- **R2, orchestrator:** the handoff says integration starts with `test_socket_guard_blocks_outbound`, but PS-2.7 superseded it. The design now drops the guard fixture. Confirm.
- **R3, orchestrator:** is M5 in platform-stack scope? If yes, the analyst needs a criterion (for example a PS-1.5 amendment). The tester needs a ruling to flip the green tests that pin foreign shapes as accepted: the `InstalledProviderTest` accepted shapes and `test_local_otlp_that_ignores_proxy_env_is_accepted`. This tightens them.
- **R4, orchestrator:** the gateway entrypoint check is a second enforcement point beyond the ruling's "refused at startup". Confirm, or accept the engine-only refusal and the LAN-exposed Phoenix residual.

## Verification
- `scripts/verify.sh fast`: see `architect-plan-verify-fast.txt` in this directory.
