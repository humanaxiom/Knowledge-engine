# analyst: Q30 narrowed by F-A; orchestrator rulings folded in (2026-10-18)

Asked: record the human's ruling F-A (Q30 narrowed) and the orchestrator's
platform-config rulings in `docs/requirements.md` and `docs/open-questions.md`
only. Every change below records someone else's decision, not the analyst's.

## Human ruling F-A (narrows Q30)
Automated tests reach only the LLM on `aria-gb10-2`, through the stack
gateway, and get no internet access.
- "Integration" convention: `gates-it` on the stack's internal network only,
  no internet; only outside host is the model host via model client ->
  `gateway` -> `KE_MODEL_UPSTREAM`. Q30's first wording kept as a note.
- PS-2.7: mechanism now internal-only; new bullet "Model host only through
  the gateway"; `test_gates_it_has_network_access_and_no_socket` renamed
  `test_gates_it_internal_only_and_no_socket` (asserts every `gates-it`
  network is `internal: true`, no Docker socket, `gates` still
  `network_mode: none`). `test_egress_allowlist_holds_with_network_access`
  kept (name explained: the gateway forward is the access it holds against).
  Q30 wording kept as a note.
- PS-2.5 model-host bullet and PS-2.10 reworded (no "external access").
- DR31 amendment text and table row 31: rewritten for F-A; test renamed;
  first Q30 wording kept in the note; DR30 test kept with reason.
- Item open-questions list and PS-Q7 note updated. open-questions.md: Q30,
  Q7 (A7) and Q19 entries updated, old wording kept.

## Orchestrator rulings
- Phoenix compose port to `.env` (`KE_PHOENIX_PORT=47101`) within
  platform-config: new PS-1.2 sub-bullet; PS-2.2 "Delivered early" note.
  `test_harness_default_collector_matches_env_example` and
  `test_docs_name_current_phoenix_port` stay in platform-stack.
- Loopback and compose service names are not hardcoded hosts: PS-1.2
  sub-bullet.
- PS-1.9: placeholder `changeme-<key in lowercase>`; prefix match
  case-insensitive.
- Q31 resolved: recorded Windows run is the PowerShell proof (PS-2.9 note).
- Q32 resolved: scheme/port/URL per deployment in `.env`; no model-host
  default in `config/defaults.yaml`; `.env.example` leaves
  `KE_MODEL_UPSTREAM` empty with a comment naming `aria-gb10-2` (PS-1.2).

## Open questions for the orchestrator
- Interim harness default: once compose publishes phoenix on 47101 in this
  item, `harness_telemetry`'s default collector (today 6006) points at a
  port nothing serves until platform-stack changes it, unless the developer
  changes it here (the working tree already touches `tracing.py`). Not
  ruled; no criterion assumes either.
- Architecture §2.4 drops Phoenix's gRPC port 4317 and §2.1/ADR-KE-009 still
  describe a dedicated non-internal `gates-it` network: the architect needs
  to fold in F-A (not analyst files).

## Evidence
`scripts/verify.sh fast` -> FAIL, Ran 147, failures=13, errors=1. None are
docs tests: 12 in `test_harness_followups.IntegrationRunsOnceTest` ("fake
uv: no python argument", from the developer's in-progress `scripts/test.sh`),
`test_python_pinned_to_312` and `test_config_init_args_take_precedence`
(developer in-progress). Full output:
`docs/evidence/platform-config/analyst-q30-narrow-verify-fast.txt`.
