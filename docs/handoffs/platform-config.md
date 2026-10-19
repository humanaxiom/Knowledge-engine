# Handoff: platform-config

Outcome metric moved: neither directly. It is the typed configuration, egress
guard and startup refusals that every later item builds on.
Spec: `docs/requirements.md` § platform-skeleton, PS-1.x. Design: `docs/architecture.md` §2.3, ADR-KE-010.
Umbrella: `docs/handoffs/platform-skeleton.md`. Base: `agent/harness-followups` @ 40c0c75.

## 2026-10-18 — orchestrator: item opened
- First, a plan step: the analyst and architect fold in the human rulings Q30 (gates-it gets external access, amending DR31), Q20 (no macOS) and Q7 (model host `aria-gb10-2`), plus the placeholder-secret ruling (`changeme-` prefix). Rulings: `docs/handoffs/platform-skeleton.md`.
- Then TDD for PS-1.x, starting with `test_config_defaults_and_env_override`.

## 2026-10-18 — orchestrator: rulings on analyst Q31, Q32 and casing
- Q31: a recorded run on the human's Windows host (this machine) is the proof for the PowerShell scripts, captured as evidence in platform-stack.
- Q32: the model host's scheme, port and URL are per deployment, set in `.env`. `config/defaults.yaml` ships no host default, and `.env.example` leaves `KE_MODEL_UPSTREAM` empty with a comment naming `aria-gb10-2` as this deployment's host. Nothing is invented.
- The placeholder form is `changeme-<key in lowercase>`.

## 2026-10-18 — analyst: human rulings Q30, Q20, Q7 and placeholder ruling folded in
- Asked: apply the rulings (each is the human's / orchestrator's decision, not the analyst's) to `docs/requirements.md` and `docs/open-questions.md` only.
- **Q30 (human):** "Integration" convention and DR31 rewritten (compose services, no Docker socket, `gates-it` network with external access; model-calling integration tests run if the model host is reachable, else skip with a named reason; unit tests no network; DR30 still applies; offline-bundle checks unchanged). Original wording kept as notes (conventions bullet, note under §R-DR, agent-workflow 7). PS-2.4–2.7 unblocked; PS-2.7 rewritten.
  - New/renamed tests: `test_gates_it_has_network_access_and_no_socket`, `test_egress_allowlist_holds_with_network_access` (replaces `test_socket_guard_blocks_outbound`, also in DR30 row), `test_model_tests_skip_with_named_reason`, `test_no_model_calls_in_unit_suite` (replaces `test_no_model_calls_in_ci`), `test_readyz_reports_reachable_model_host`. `test_readyz_ready_without_model_host` now forces the host unreachable in process.
  - PS-2.10 clarified: profile-only `gates-it` is not a "stack service".
  - New **PS-2.13**: CLAUDE.md section "What verify.sh runs that CI cannot", `test_claude_md_lists_verify_only_checks` (fast; lands in platform-stack).
- **Q20 (human):** PS-2.9 Windows PowerShell + Linux bash only; macOS out of scope; PS-3.1 platform note updated. Windows *proof* not ruled, carried as **Q31**.
- **Q7 (human):** A7 resolved: `aria-gb10-2`, OpenAI-compatible, via `KE_MODEL_UPSTREAM` / per-pass base URLs. PS-1.2 note: the name counts as a host name for `test_no_hardcoded_hosts_or_models`. Port, scheme and whether it is a shipped default not ruled: **Q32**.
- **Placeholder ruling (orchestrator):** PS-1.9 rewritten: `.env.example` placeholders are `changeme-<key>` (`test_env_example_secret_placeholders_are_changeme`); prefix refusal outside dev (`test_startup_refuses_placeholder_secrets`, incl. a non-`.env.example` `changeme…` value); `.env.example` not in any image (`test_env_example_not_in_app_image`, written in platform-stack). Old definition kept as a note.
- **Open questions for the orchestrator:** Q31 (Windows proof), Q32 (model-host port/scheme/default). Neither blocks platform-config. `<key>` casing in `changeme-<key>` is not ruled; the criterion only requires that it names the key.
- **Next:** tester starts PS-1.x RED as planned. PS-1.9's tests now follow the prefix rule, not `.env.example` lookup.

## 2026-10-18 — tester: PS-1.x RED
- Asked: failing tests for PS-1.1–1.9 (the changeme check is case-insensitive per the orchestrator's ruling). Run `scripts/verify.sh fast`.
- New files: `tests/test_engine_{config,egress,startup,hardcoded,quality}.py`, plus helper `tests/engine_support.py` (not `test*`; it imports nothing from engine at import time, so each test fails on its own).
- RED: `scripts/verify.sh fast` gives `Ran 147`, failures=10, errors=66. All 76 are in `test_engine_*`; the sentinel is ok. Evidence: `docs/evidence/platform-config/red.txt`. Reasons: `engine` missing (40), `tests.hardcoded_scan` missing (17), `httpx`/`yaml`/`pydantic` missing (8), `config/defaults.yaml` and `.env.example` missing, and pyproject has no pin, deps, coverage or mypy config. Two guard tests are already green: `test_model_host_name_only_in_allowed_locations`, `test_tests_excluded_from_measurement`.
- **Developer must `uv add`:** `pydantic-settings`, `pyyaml` and `httpx` (runtime); `--group dev coverage mypy types-pyyaml`. Also: `requires-python = ">=3.12,<3.13"` then `uv lock`, and `engine` in the wheel packages. The gates Dockerfile copies only `harness_telemetry` before `uv sync`, so it needs `engine/` too.
- **Contracts the tests pin beyond the ADR names (developer: follow these; reviewer: judge them):**
  - `engine.config.Settings()` itself raises `engine.config.ConfigError` (wrap pydantic's ValidationError). Messages name the env var or the dotted key, never the value.
  - Lists in env are comma-separated.
  - `KE_MODEL_UPSTREAM` is the env name. The attribute may be `settings.model_upstream` or `settings.models.model_upstream`. §2.3's YAML nests it under `models`, which would give `KE_MODELS__MODEL_UPSTREAM`, so the env name needs explicit handling.
  - `engine.startup.check(settings)` raises `StartupRefused`, and `str()` names the setting or host. Dev warnings go to the logger `engine` (or a child). Refusal 2 applies only when `tracing=otlp`, and also in dev.
  - `engine.startup.startup()` takes no args and reads the env.
  - `engine.egress.EgressPolicy(allowlist)` and `GuardedTransport(policy, inner)`. `is_local_endpoint(url, service_names)`.
  - `engine.llm.client.ModelClient(settings, pass_name).http_client` is an httpx.Client with `trust_env False` and `_transport` a GuardedTransport.
  - `engine.telemetry.configure_tracing(settings)`. Span names and attributes follow the §2.3 table. The config-load span lists overridden env names, never values.
  - Secrets are discovered as SecretStr fields at any depth. `KE_STORES__POSTGRES__PASSWORD` and `KE_STORES__NEO4J__PASSWORD` must exist.
  - `tests/hardcoded_scan.find_hardcoded(files, declared_values, exemptions)`: the developer writes it. Its contract is in the docstring of `tests/test_engine_hardcoded.py`, and 10 fixture tests pin it (including DR38 planted literals).
- **Risks for the orchestrator:**
  - (a) `test_no_hardcoded_ports` declares the port of `telemetry.collector_endpoint` (6006). Compose `"6006:6006"` and the `harness_telemetry/tracing.py` docstring would then be flagged now, which pulls part of PS-2.2 (phoenix ports) into this item, or needs a ruling.
  - (b) Rule 2 flags `scripts/smoke_otlp.py`'s `f"http://127.0.0.1:{port}"`.
  - (c) The repo scan treats compose service names and loopback as non-hardcoded hosts. That is the tester's interpretation; otherwise every compose service name is a hit.
  - (d) `test_harness_default_collector_matches_env_example` was not written. It belongs to PS-2.2 in platform-stack, as the requirements tag it.
- Next: developer GREEN, starting with `test_config_defaults_and_env_override`.

## 2026-10-18 — analyst: Q30 narrowed by F-A (human); Q31, Q32, ports, hosts, casing (orchestrator)
- Recorded as others' decisions in `docs/requirements.md` and `docs/open-questions.md`. Details: `docs/evidence/platform-config/analyst-q30-narrow.md`.
- F-A (human): `gates-it` internal-only, no internet; tests reach only `aria-gb10-2` via the gateway. Integration convention, PS-2.5/2.7/2.10, DR31 text, row and note updated. Test renamed `test_gates_it_internal_only_and_no_socket`; `test_egress_allowlist_holds_with_network_access` kept.
- Orchestrator: phoenix compose port `KE_PHOENIX_PORT=47101` lands here (PS-1.2, PS-2.2 note); loopback/compose names not hardcoded hosts (PS-1.2); `changeme` case-insensitive, `changeme-<key in lowercase>` (PS-1.9); Q31, Q32 resolved.
- Open: interim harness default collector (6006 vs 47101) between this item and platform-stack; architect to fold F-A into architecture.md.
- verify fast: FAIL only on developer in-progress tests (harness_followups fake-uv, python pin, config init args); evidence `docs/evidence/platform-config/analyst-q30-narrow-verify-fast.txt`.

## 2026-10-18 — developer: PS-1.x GREEN (uncommitted)
- Done: deps, `engine/` (config, egress, startup, telemetry, llm/client), `config/defaults.yaml`, `.env.example`, `tests/hardcoded_scan.py`, coverage+mypy in test.sh, compose ports via `${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}` (4317 unpublished), `DEFAULT_COLLECTOR=http://localhost:47101` (docstring names no port), smoke_otlp builds its URL from a `host` variable.
- Lock: `uv add --no-sync pydantic-settings pyyaml httpx` and `uv add --no-sync --group dev coverage mypy types-pyyaml` on the host (uv 0.11.21, network). uv writes `requires-python = "==3.12.*"` into uv.lock, but the test pins the literal `>=3.12,<3.13`, so line 3 was edited by hand; `uv lock --check` and `uv sync --locked` accept it. A later `uv lock` will rewrite it: re-apply, or the tester relaxes the test.
- Result: `scripts/verify.sh full` = 146/147. ONE BLOCKER, a tester-file bug: `tests/engine_support.load_settings(env=None, **init)` is called as `load_settings(base_env(...), env="ci")` in `test_config_init_args_take_precedence`, a TypeError (multiple values for `env`) before engine code runs. Needs the helper's first param renamed (e.g. `environment`). I did not edit tests. Because test.sh stops at the failure, coverage and mypy were run separately in the gates container: coverage 92% (branch), `mypy` clean, smoke_otlp pass.
- Deviations to rule on: (1) defaults.yaml `telemetry.tracing: "off"` (not `otlp`): the leaf test loads defaults with HARNESS_TRACING=off and requires equality with every yaml leaf; the stack's .env should set `HARNESS_TRACING=otlp`. (2) test.sh runs tools as `uv run --locked python -m coverage|mypy` (fake-uv tests need a `python` arg) and guards the final trio with `[ -f pyproject.toml ]` since the fake-project tests have none. (3) Found/fixed a latent harness_telemetry bug: `_span` crashed on a NonRecordingSpan (tracing off, no provider); now guarded. Return types and a getattr added for mypy --strict. (4) `configure_tracing` exports the settings' hide flags to OPENINFERENCE_HIDE_* because harness_telemetry reads them from env.
- README still says Phoenix on 6006 (documenter).
- DR38 mutations (all RED, sha256 restored): `docs/evidence/platform-config/mutation.txt`. Full run: `docs/evidence/platform-config/green-full.txt`.

## 2026-10-18 — tester: fixups (helper bug, pin ruling, NonRecordingSpan regression)
- Touched tests/ only: `engine_support.py`, `test_engine_quality.py`, `test_tracing.py`.
- (1) My bug: `load_settings(environment=None, **init)`, renamed from `env`. All callers pass it positionally, so none changed. `test_config_init_args_take_precedence` now runs: ok.
- (2) Contradiction I own (criterion 10 / PS-1.8), resolved under the orchestrator ruling that uv.lock is generated and never hand-edited (cited in a test comment). `test_python_pinned_to_312` keeps the literal `>=3.12,<3.13` for pyproject. For uv.lock it checks equivalence: probes say every 3.12.x is allowed and 3.11.x, 3.13+ and 4.x are refused. Unknown specifier syntax fails. New `test_pin_equivalence_check_accepts_uv_forms_and_rejects_others` guards the checker.
- (3) New `test_spans_tolerate_non_recording_span` swaps only `harness_telemetry.tracing._tracer` for `trace.NoOpTracer()`, so the shared provider is untouched. It asserts the span is a NonRecordingSpan and nothing is exported.
- Mutation proofs, run in a scratch copy that was then deleted: with the guard reverted the new test fails with `AttributeError: 'NonRecordingSpan' object has no attribute 'status'`. The pin test passes for a `==3.12.*` lock and fails for `>=3.12`. Evidence: `docs/evidence/platform-config/tester-fixups-mutation.txt`.
- `scripts/verify.sh full`: PASS. Ran 149, OK, coverage 92%, mypy clean, smoke pass. Evidence: `docs/evidence/platform-config/tester-fixups.txt`.
- Next (developer): uv.lock line 3 is still hand-edited (`>=3.12,<3.13`). Regenerate it with `uv lock` (expect `==3.12.*`); the test now accepts that form. Then re-run verify full.

## developer: uv.lock regenerated (relock)
- Ran `uv lock` (host uv 0.11.21); no hand edits. Line 3 is `requires-python = ">=3.12,<3.13"` (uv's own form, matches pyproject.toml; not `==3.12.*`). `uv lock --check` passes.
- `scripts/verify.sh full`: PASS. Evidence: docs/evidence/platform-config/green-full-relock.txt. Nothing staged or committed.

## 2026-10-19 — orchestrator: rework round 1 of 5 (review CHANGES REQUESTED, security FAIL H1)
- In scope:
  - review B1–B6 (B1 = security H1: exporter chosen from settings only, explicit ConsoleSpanExporter, provider-already-installed case checked);
  - B7c (compose/defaults drift test);
  - security M1 (`.env` in .gitignore, keep `!.env.example`), M2 (Phoenix bound to 127.0.0.1), L1 (strip whitespace/zero-width before the changeme check), L4 (wrap SettingsError/ValueError into ConfigError), L6 (configure tracing only after `check()` passes);
  - review N6 (precedence test + error names the variable the user set), N7 (no input value in ConfigError, tested), N12 (ModelClient call wrapped in `llm_span` with a test).
- Rulings:
  - B7a: compose keeps `${KE_PHOENIX_PORT:-47101}`. `:?` breaks verify/CI when `.env` is absent. The architect amends §2.3. The scanner treats compose `${VAR:-default}` defaults as declared values (compose files only, B4).
  - B7b: `telemetry.tracing` defaults to `off` (safer). `.env.example` sets otlp for the local Phoenix. The architect amends §2.3.
- Deferred nits: N1–N5, N8–N11, N13 (docs drift goes to the documenter at the docs gate), security L2, L3, L5, L7.

## 2026-10-19 — tester: rework 1 RED
- Touched tests/ only. New: `test_engine_telemetry.py`, `test_engine_llm.py`, `test_engine_deploy_files.py`. Extended: `test_engine_config.py`, `test_engine_startup.py`, `test_engine_egress.py`, `test_engine_hardcoded.py`, `test_harness_followups.py` (fake uv now logs calls and no-ops `coverage combine|report` and `mypy`).
- `scripts/verify.sh fast`: Ran 179 (was 149), FAILED (failures=51, errors=15). Every failure is a new test. Evidence: `docs/evidence/platform-config/red-rework1.txt`.
- Contract pinned (from architecture §2.3 rework 1): `engine.telemetry.choose_exporter(settings)`; `configure_tracing(settings)` refuses an installed provider with `StartupRefused` naming `telemetry.tracing`; `startup()` runs `check()` before `configure_tracing`.
- RED by finding (expected reason):
  - B1/H1: `ChooseExporterTest` ImportError (no `choose_exporter`). `test_console_mode_installs_console_exporter_only`: OTLP built to the external host.
  - B2 installed provider: `test_non_local_or_unknown_exporter_is_refused` (9 subtests; trusted today).
  - L6: `test_refused_startup_installs_nothing` and `test_refused_startup_leaves_hide_env_untouched`. configure_tracing runs before check().
  - B4: `test_shell_parameter_default_is_flagged_outside_compose`. B5: `test_stale_parallel_coverage_data_is_not_combined`. B6: `test_quality_gates_always_run` (guard skips with no pyproject).
  - M1: `test_env_file_is_ignored`. M2: `test_phoenix_published_on_loopback_only`. L1: `test_placeholder_hidden_behind_invisible_prefix_is_refused`.
  - L4: `test_malformed_values_raise_config_error` (SettingsError / ValueError escape). N6: `test_error_names_the_variable_the_user_set` (names KE_TELEMETRY__*).
  - N12: `test_engine_llm` AttributeError. No call method existed, so the test pins `ModelClient.complete(messages)`: `POST {base_url}/chat/completions`, body `{model, messages}`, returns JSON, wrapped in `llm_span("model.compose")`.
- Green today, mutation-proven (scratch copy, gates image, `--network none`; baseline 8 OK; every mutant KILLED): M1, M2, M11, M15, M5, M17, T1, and the drift mutants D1/D2 for `test_compose_phoenix_defaults_match_config` (B7c). Evidence: `docs/evidence/platform-config/red-rework1-mutation.txt`.
- N6 model upstream, flipped under the orchestrator ruling (F2, no aliases): `KE_MODEL_UPSTREAM` is the only accepted name. New `PrecedenceTest.test_model_upstream_has_one_name`: the nested form alone has no effect, and with both set the flat value is used. It is RED today ('nested.internal:9001' is not None). The KE_TELEMETRY__* order is unchanged. M5 is still killed by the four telemetry cases. Re-run: Ran 180, FAILED (failures=52, errors=15); `red-rework1.txt` was overwritten.
- Developer notes:
  - The B5 test copies the real pyproject.toml, so either fix works (`rm -f .coverage.*` in test.sh, or `parallel = true`).
  - The guard must go: the fake project has no pyproject.toml and still expects the three steps.
  - This RED run left two `.coverage.*` files in the repo root (the B5 bug itself). They are gitignored.
  - The old `test_non_local_collector_gets_no_exporter`/`test_configure_tracing_attaches_nothing_for_non_local` in test_engine_startup stay unchanged. They are vacuous under the global provider; the new isolated tests cover the real path.

## developer: rework 1 GREEN
- `scripts/verify.sh full`: PASS first attempt. Ran 180, OK, coverage 95%, mypy clean, smoke pass. Evidence: `docs/evidence/platform-config/green-rework1.txt`. Nothing staged or committed. Stale `.coverage.*` deleted from the repo root.
- Production changes (tests untouched):
  - `engine/errors.py` (new): `StartupRefused` moved here (breaks the startup/telemetry import cycle); `engine.startup` re-exports it.
  - `engine/telemetry.py`: pure `choose_exporter(settings)` (otlp local only, console, off); `configure_tracing(settings)` writes hide flags, verifies an installed SDK provider (Console, InMemory, local OTLP accepted; anything else raises `StartupRefused("telemetry.tracing")`), else installs its own provider. No `setup_tracing`. B1/H1, B2.
  - `engine/startup.py`: `startup()` pre-flights `Settings()` + `check()`, calls `configure_tracing` only if both pass, then the traced block (repeats both so refusals are span-recorded). L6. L1: invisible edge chars stripped before the `changeme` check.
  - `engine/config`: `KE_MODEL_UPSTREAM` is the only name (nested form dropped by `_EnvSource`, N6); `var_name()` makes errors name the variable the user set; SettingsError/ValueError wrapped into ConfigError naming the KE_ variables, no values (L4, N7); model_upstream validated at load.
  - `engine/llm/client.py`: `complete(messages)` inside `llm_span("model.<pass>")` (N12).
  - `tests/hardcoded_scan.py` (helper): `${VAR:-default}` blanked only in docker-compose*.yml; elsewhere the default is exposed and flagged (B4).
  - `scripts/test.sh`: `rm -f .coverage.*` after erase (B5); guard removed (B6). `docker-compose.yml`: `127.0.0.1:` publish (M2). `.env.example`: `HARNESS_TRACING=otlp` (B7b). `.gitignore`: `.env`, `.env.*`, `!.env.example` (M1).
- Note for reviewer: startup runs `check()` twice (pre-flight and traced), so `engine.egress.startup_check` span appears twice on a passing start.

## 2026-10-19 — orchestrator: rework round 2 of 5 (review APPROVED r1; security FAIL H2)
- In scope:
  - security H2 (OTLP exporter session `trust_env=False`; installed OTLP exporters accepted only with `trust_env` False);
  - M3 + review R1 (check any installed provider in `startup()` before any span opens; refuse anything not a ProxyTracerProvider or an SDK provider that passes);
  - M4 (reject userinfo in `base_url`/`model_upstream` at settings load);
  - L1b (NFKC-normalise and strip format/space/control characters anywhere before the case-insensitive `changeme` check);
  - review R2 (resource carries the OpenInference project name).
- Deferred: review R3–R7, N1–N5, N11, N13; security L2, L3, L5, L7, I1. R7/N13 docs go to the documenter at the docs gate.

## 2026-10-19 — tester: rework 2 RED
- `scripts/verify.sh fast`: Ran 197 (was 180), FAILED (failures=133). Every failure is a new test. Evidence: `docs/evidence/platform-config/red-rework2.txt`.
- New `tests/test_engine_tracing_guard.py` (H2, M3, R1, R2). Extended `test_engine_config.py` (M4 `ModelUrlUserinfoTest`) and `test_engine_startup.py` (L1b).
- RED by finding (expected reason):
  - H2: `test_chosen_exporter_session_does_not_trust_env` (trust_env True; also kills the "session not passed" mutant, which is today's code). `test_chosen_exporter_dials_only_the_collector` and `test_configured_exporter_dials_only_the_collector`: the real export path, under a SocketSpy, dials `evil.example` for HTTP_PROXY, http_proxy+NO_PROXY, and ALL_PROXY. `test_local_otlp_that_trusts_proxy_env_is_refused`: a default-session local OTLP exporter is trusted.
  - M3: `test_foreign_provider_refused_before_any_span_passing_settings` and `..._gets_no_span_with_refusing_settings`. Spans reach the foreign provider's in-memory exporter. Shapes: unknown exporter, external OTLP, local OTLP trusting proxy env, non-SDK provider. Settings: passing, auth off, placeholder, non-local collector, ConfigError.
  - R1: `test_non_sdk_provider_is_refused` (falls through today).
  - R2: `test_provider_resource_carries_openinference_project_name`.
  - M4: `test_base_url_with_userinfo_is_refused` (4 passes x 3 forms), `test_model_upstream_with_userinfo_is_refused`, `test_startup_refuses_userinfo_without_the_password` (host allowlisted, so only the userinfo can refuse).
  - L1b: `test_placeholder_hidden_by_invisible_characters_is_refused`. The 7 listed characters plus U+200B, each before and inside, and fullwidth. 4 subtests (U+200B before) were already green.
- Green controls (pass today, keep them green): `test_control_spans_do_reach_an_accepted_provider` (proves the span routing is real), `test_local_otlp_that_ignores_proxy_env_is_accepted`, `test_proxy_provider_is_accepted`, `test_real_secrets_with_ordinary_characters_are_accepted`, `test_urls_without_userinfo_still_load`.
- Contradiction resolved (orchestrator rework-2 ruling, security H2): `InstalledProviderTest._real_otlp` in `test_engine_telemetry.py` now builds accepted OTLP shapes with a `trust_env=False` session. A default session must now be refused.
- Pinned for the developer:
  - With an unverifiable provider installed and settings that do not load (ConfigError), startup must still emit zero spans, so the provider check comes before the traced block. Either error type is accepted there.
  - With passing settings, the refusal names `telemetry.tracing`.
  - The tests locate the session by walking OTel attributes (today `_client._transport._session`). Pass `session=` to the exporter.
  - The `ExporterIgnoresProxyEnvTest` export patches `opentelemetry.exporter.otlp.common.http._MAX_RETRIES` to 1, so there is no backoff wait.

## 2026-10-19 — developer: rework 2 GREEN
- `scripts/verify.sh full`: PASS, 197 tests OK, first attempt. Evidence: `docs/evidence/platform-config/green-rework2.txt`.
- H2: `engine/telemetry.py` builds the exporter with a `trust_env=False` session; installed OTLP exporters accepted only if every reachable session (attribute walk) has `trust_env` False. `requests` declared via `uv add`, `uv lock`.
- M3/R1: new `verify_provider()` (Proxy ok, SDK checked, else refuse); `startup()` calls it before `check()` and any span, with `[]` service names if settings fail to load.
- M4: `_no_userinfo` validators on every `base_url` and `model_upstream`. L1b: `_visible` NFKC plus category strip. R2: resource has `openinference.project.name`.
- DR38 H2 mutation (drop `session=`): RED, 12 failures; restored, sha256 match. `mutation-rework2.txt`. Not staged or committed.
- 2026-10-19 orchestrator: security r2 PASS (0 crit/high). Deferred: M5 (installed OTLP exporter with explicit proxies/adapters passes the check; identity-marker fix conflicts with the test suite's global in-memory provider, so plan it), L1c (variation selectors etc.). L8 profile path redacted in mutation-rework2.txt.

## 2026-10-18 — tester: rework 3 (B-R2-1, R2-N2), tests only
- Added `InstalledProviderGuardTest.test_custom_span_processor_is_refused` (E1), `test_local_otlp_with_unreachable_session_is_refused` (W3), FOREIGN shape `sdk, custom span processor` (zero spans asserted), U+2028/U+2029 in `L1B_HIDERS`. No production change.
- Mutants E1, W3, C4, C5 all KILLED in a scratch copy (deleted): `docs/evidence/platform-config/tester-rework3-mutation.txt`.
- `scripts/verify.sh full`: PASS, 199 OK, 95%, mypy clean, smoke pass: `docs/evidence/platform-config/tester-rework3.txt`.

## 2026-10-19 — marketer: changelog gate
- Asked: CHANGELOG.md entry for shipped, tested behaviour (rework 3 state). Touched CHANGELOG.md only.
- Did: added `### 2026-10-19` under [Unreleased] (Added, Changed, Security). Terse, no figures.
- Checked: fail_under=80, mypy strict, compose `127.0.0.1:${KE_PHOENIX_PORT:-47101}`, requires-python 3.12 pin.
- Gate: TDD and smoke pass (rework 3). Reviewer has not re-approved rework 3, so the commit waits on that.
- For documenter: README.md line 23 still says Phoenix is on 6006. Evidence: `docs/evidence/platform-config/marketer.md`.

## documenter: docs gate
- README.md and AGENTS.md updated (Phoenix 47101, config section). R7 open (.env.example comment). Details: docs/evidence/platform-config/documenter.md
