# 2026-10-18 — architect: Q30 narrowed by F-A; scan rulings in §2.3

- **Asked:** fold human ruling F-A (tests reach only the LLM on `aria-gb10-2`,
  not the internet) into ADR-KE-009, §2.1 and §2.2; record two orchestrator
  rulings in §2.3. Docs only; touched only `docs/architecture.md`.
- **Changed in `docs/architecture.md`:**
  - Header "Next to build": Q30 described as narrowed by F-A.
  - §2.1: `gates-it` network removed from the network table; `gates-it` row
    is `backend` only, no Docker socket; diagram puts `gates-it` inside
    `backend`, drops the "route out (accepted risk)" edge and the outside
    node, and labels the gateway forward "(edge)".
  - §2.2: status narrowed by F-A; the model-host bullet says the gateway
    forward is `gates-it`'s only path out; sequence diagram adds the gateway
    participant (G → gateway → model host); socket guard now has the internal
    network behind it again.
  - §2.3: new "Orchestrator rulings for the scan": (1) Phoenix ports move to
    `.env` in platform-config, `KE_PHOENIX_PORT=47101`, published by the
    harness `phoenix` service until `gateway` exists; container port as a
    compose `${VAR:-default}`; gRPC 4317 not published; `DEFAULT_COLLECTOR`,
    tracing.py docstring and compose comment move off 6006/4317. (2) Loopback
    and `stack.service_names` are never flagged as hosts; ports still are.
  - §2.6: `test_gates_it_network_topology` asserts `backend` only, no
    non-internal network except `edge`, no socket; the raw-connection clause
    of `test_socket_guard_blocks_outbound` is restored.
  - ADR-KE-001 amendment, ADR-KE-003 amendment, ADR-KE-011 network bullet:
    aligned to `backend` only.
  - ADR-KE-009: status/context narrowed; option (c) explicitly rejected (F-A);
    decision is plain (a); "Tests can reach the internet" risk and its
    mitigations removed, replaced by "the checkout cannot leave the machine
    through tests"; "Local verify covers more than CI" consequence and the
    CLAUDE.md row (PS-2.13) kept; DNS residual notes it applies to `gates-it`.
- **For the orchestrator:**
  - Precision note: "cannot leave the machine" holds except as model input
    to the configured model host via the gateway (the app's own trusted
    path), plus the existing Docker DNS residual. Both are written into the
    ADR rather than hidden.
  - Ruling (1) pulls `DEFAULT_COLLECTOR` → 47101 into platform-config. Its
    drift test (`test_harness_default_collector_matches_env_example`) is
    tagged PS-2.2/platform-stack in requirements; the analyst decides whether
    it moves. README Phoenix URL is a documenter edit.
- **Verify:** `scripts/verify.sh fast` → FAIL, exit 1, `Ran 147`,
  failures=9, errors=1. All 10 failures are in `tests.test_engine_*`
  (developer's in-progress GREEN work: `test_config_init_args_take_precedence`,
  `test_python_pinned_to_312`, `test_test_sh_enforces_coverage_and_mypy`);
  zero failures outside `test_engine_*`. Evidence:
  `docs/evidence/platform-config/architect-q30-narrow-verify-fast.txt`.
- **Next:** developer continues; platform-stack tests follow the updated §2.6.
