## 2026-10-19 — architect: rework round 1 (amend §2.3 and ADR-KE-010)
- **Asked:** amend `docs/architecture.md` §2.3 and ADR-KE-010 to the orchestrator's rulings B7a, B7b, B1, L6, N13 (line 314) and N12. Docs only.
- **Changed (docs/architecture.md only):**
  - §2.3 "Standard tool names": `Settings` is the engine's only reader of `HARNESS_TRACING`, `PHOENIX_COLLECTOR_ENDPOINT` and `OPENINFERENCE_HIDE_*`.
  - §2.3 defaults.yaml layout: `tracing: "off"` (N13 drift fixed, B7b).
  - §2.3 scanner allowed locations: `${VAR:-default}` defaults count as declared values in `docker-compose*.yml` only (B4/B7a). Drift tests cover host ports (against `.env.example`) and container ports (against `defaults.yaml`).
  - §2.3 scan ruling 1 amended (B7a, M2): the publish is `"127.0.0.1:${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}"`, with `:-` because verify and CI have no `.env`. The drift test is `test_compose_phoenix_defaults_match_config`.
  - §2.3 "Tracing does not leak" rewritten (B1, B7b, L6, N8, N9, N10):
    - a pure `choose_exporter(settings)` maps otlp to local OTLP or none, console to `ConsoleSpanExporter`, and off to none;
    - `configure_tracing(settings)` builds the engine's own provider and never calls `harness_telemetry.setup_tracing`;
    - an already-installed provider is refused (`StartupRefused("telemetry.tracing", …)`) unless every exporter on it is positively local. The check fails closed;
    - startup order: `Settings()`, then a pre-flight `check()`, then `configure_tracing` (hide flags first), then the traced block.
  - §2.3 spans: an N12 note says every `ModelClient` call method opens `llm_span("model.<pass>")` and comes with a test.
  - ADR-KE-010: two new Decision bullets (Tracing, Compose), and new rejected alternatives, consequences and first tests, each marked "rework 1".
- **Decisions beyond the rulings (for the orchestrator to confirm):**
  - "Refused or replaced": the design picks **refuse**. The OTel global provider cannot be replaced once it is set.
  - The hide flags are still written to `os.environ`, but the value written is the one `Settings` resolved from the same names, so an operator's value is never overridden. A new harness API was rejected as extra surface. This partly answers L6's "prefer passing explicitly". Security may want to re-check it.
- **Flag (out of scope, not edited):** §2.4 "Compose" (platform-stack) still says host ports are `${KE_…_PORT:?set in .env}`. Under the B7a reasoning, platform-stack hits the same verify/CI problem and should also bind loopback. The orchestrator should rule on it before platform-stack starts.
- **First tests for the tester:**
  1. `choose_exporter`: console, with an external `PHOENIX_COLLECTOR_ENDPOINT` and `HARNESS_TRACING` unset or `otlp`, returns a `ConsoleSpanExporter` and never OTLP (the H1 repro).
  2. `choose_exporter`: otlp with a non-local collector returns none, and off returns none.
  3. An installed provider with a non-local OTLP exporter, or an unknown exporter, gives `StartupRefused`.
  4. `configure_tracing` is not called when `check()` refuses (L6).
  5. `test_compose_phoenix_defaults_match_config`, and a test that the publish is bound to `127.0.0.1`.
  6. The `ModelClient` call emits an LLM span (N12).
- **Evidence:** `scripts/verify.sh fast` gave PASS (149 tests). Output: `docs/evidence/platform-config/architect-rework1-verify-fast.txt`. The tester's RED tests had not landed in the tree, or did not fail, when this ran.
- **Next:** the tester writes the RED tests above, then the developer implements.
