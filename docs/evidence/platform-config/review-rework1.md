# platform-config rework 1: reviewer re-review (2026-10-19)

Verdict: **APPROVED** (0 blocking; 1 new should-fix nit, 6 new nits, deferred nits carried).
Scope: `git diff 40c0c75` plus untracked `engine/`, `config/`, `.env.example`, `tests/test_engine_*.py`,
`tests/engine_support.py`, `tests/hardcoded_scan.py`. Base design: architecture section 2.3 and ADR-KE-010 as amended
(`architect-rework1.md`). Mutants and probe: `docs/evidence/platform-config/review-rework1-mutants.txt`.
The developer run is `green-rework1.txt` (verify full PASS, Ran 180, 95%, mypy clean, smoke pass). No source,
test or script file changed after that run; only the security probe, handoff and log are newer.

## 1. Prior findings
| Finding | Status | Proof |
|---|---|---|
| B1 console mode exported to a non-local collector | resolved. `choose_exporter` reads `Settings` only; console gives `ConsoleSpanExporter`; `setup_tracing` is no longer called | mutant N8 (console builds OTLP from env) KILLED by 4 + 3 subtests |
| B2 export gate had no test that could fail | resolved. Isolated provider/exporter patches | M1, M2, M11 KILLED; N1, N2 (installed provider trusted) KILLED |
| B3 egress startup check untested outside prod | resolved | M15 KILLED (3 dev subtests) |
| B4 `${VAR:-default}` blanked in every file | resolved. Blanking only in `docker-compose*.yml`; elsewhere the default is exposed as a token | planted `PORT=${PG_PORT:-5432}` in `scripts/plant.sh` KILLED (`test_no_hardcoded_ports`) |
| B5 stale parallel coverage data | resolved (`rm -f .coverage.*` after erase) | N5 (rm removed) KILLED |
| B6 quality gates skipped silently | resolved. Guard removed; the fake uv makes the three steps no-ops | T1 (`pyproject.tom` guard re-added) KILLED, 6 subtests |
| B7a compose `:-` | resolved by ruling. `127.0.0.1:${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}`; section 2.3 amended | N10 (loopback dropped) KILLED |
| B7b tracing default | resolved by ruling. `defaults.yaml` `off`; `.env.example` `HARNESS_TRACING=otlp`; section 2.3 amended | n/a (config) |
| B7c drift test | resolved. `test_compose_phoenix_defaults_match_config` | D1/D2 from the tester KILLED (`red-rework1-mutation.txt`) |
| N6 precedence and alias | resolved. `KE_MODEL_UPSTREAM` is the only name; errors name the variable that was set | M5 KILLED; N4 (`_EnvSource` pop removed) KILLED; N9 (`var_name` ignores standard names) KILLED |
| N7 ConfigError chaining | resolved | M17 / M17b KILLED. M17c (parse branch `from exc`) survives but is equivalent: `test_malformed_values_raise_config_error` checks the full traceback text for the value, and the pydantic-settings parse chain does not carry it |
| N12 untraced model call | resolved. `complete()` runs inside `llm_span("model.<pass>")`; ERROR on egress denial | N7 (span removed) KILLED |

Also mutation-checked: L6 order (N3, configure before check) KILLED; L1 invisible strip (N6) KILLED.
Baseline and post-restore runs of all 115 target tests: OK.

## 2. Design conformance
- `choose_exporter`: matches the section 2.3 table. It is pure, reads `Settings` only, and gives OTLP `<endpoint>/v1/traces`, timeout 5, only when local.
- `configure_tracing`: takes `settings` as an argument; writes the resolved hide flags first; verifies an installed SDK
  provider (Console, InMemory, local OTLP; anything unreadable is refused); otherwise installs its own provider (Batch for OTLP, Simple for console). It refuses rather than replaces, per the ruling.
- Startup order: pre-flight `Settings()` + `check()`, then `configure_tracing` only on success, then the traced block. This matches section 2.3 steps 1-4.
  Deviation (nit R3): step 4 says the traced block uses "the same settings object"; the code loads `Settings()` again
  inside `engine.config.load`. It is safe, because the returned object is re-checked and tracing was configured from a checked object.
- `engine/errors.py`: minimal; it breaks the cycle; `engine.startup` re-exports `StartupRefused` in `__all__`.
- `_EnvSource`: drops `models.model_upstream` from every KE_ env form (nested and JSON `KE_MODELS`). `var_name` special-cases it.
  This matches the F2 "no aliases" ruling.
- Deviation (nit R2): section 2.3 says the provider resource is the OpenInference project name `knowledge-engine` ("also fixes
  N8"). The code sets `service.name`, so product traces still land in the Phoenix default project. One line: `ResourceAttributes.PROJECT_NAME`.

## 3. Test weakening
None found.
- All 149 test ids from `green-full-relock.txt` are present in `green-rework1.txt` (180). None were removed or renamed.
- Every `tests/test_*.py` mtime is before `red-rework1.txt`; the developer GREEN step touched no test file.
  The one developer edit under `tests/` is the scanner helper `tests/hardcoded_scan.py`, which the B4 fix requires. It is stricter, not looser (the B4 plant is killed).
- The only flipped expectation is `PrecedenceTest.test_model_upstream_has_one_name` (N6 ruling).
- `test_engine_quality.py` is unchanged since before rework.

## 4. New findings (non-blocking)
- **R1 (should fix, next touch of telemetry) A non-SDK provider fails open.** `configure_tracing` checks only
  `isinstance(current, TracerProvider)` (SDK). If a non-SDK API provider is already installed (for example a vendor distro), the code falls
  through to `set_tracer_provider`. OTel refuses the override with a warning, `configure_tracing` returns `True`,
  and the foreign provider stays unverified. Probe output is in the mutants file. Section 2.3 scopes the check to SDK providers, so
  this is not a spec violation. It does contradict "fails closed". Fix: refuse unless `current` is a `ProxyTracerProvider` or a
  verified SDK `TracerProvider`; add one `InstalledProviderTest` case.
- R2 Resource uses `service.name`, not the OpenInference project name (see section 2; N8 is still open).
- R3 `Settings()` is built twice in `startup()` (see section 2). Either amend section 2.3 step 4 or pass the pre-flight object into the load span.
- R4 An installed-provider refusal raises out of `startup()` before the traced block, so it is not recorded on spans and not logged.
  Not tracing is arguably correct, because that exporter is the untrusted one. Add a `log.error` and a sentence to section 2.3. The hide flags are already written to env when this refusal fires (harmless, because the process exits).
- R5 `ModelClient.complete` records no output value or `llm.output_messages`. A non-dict JSON body gives `AttributeError` on
  `.get`. The `ValueError` for a missing `base_url` is raised outside the span. These are fine for a first call method; revisit when compose uses it.
- R6 The old `test_non_local_collector_gets_no_exporter` and `test_configure_tracing_attaches_nothing_for_non_local` in `test_engine_startup.py`
  still pass vacuously under the global provider (as the tester noted). Delete them, or add a docstring that points to `test_engine_telemetry`, so they do not read as coverage.
- R7 The `.env.example` comment says "Local Phoenix is reachable from the host", but the collector endpoint stays `http://phoenix:6006`,
  which resolves only inside the compose network. Reword it for the documenter.
- Note: `choose_exporter` imports `OTLPSpanExporter` lazily and keeps a module-level `_OtlpType` for `isinstance`. That works, but
  the pair exists only so the test patch applies. A comment would help.

## 5. Deferred nits carried (orchestrator ruling)
- N1: host matching is case-sensitive.
- N2: the scanner selects files by a suffix allowlist.
- N3: tuple and dict ports are not caught.
- N4: the exemption regex is unanchored.
- N5: `0.0.0.0` counts as LOOPBACK in the tests.
- N8: now R2.
- N9: now R3.
- N10: now covered by `_verify_installed`; R1 is the remaining gap.
- N11: the Dockerfile layer order.
- N13: docs drift, for the documenter at the docs gate. Also `AGENTS.md:149` and the README still say `localhost:6006`, and `pyproject` is still named `monitored-harness`.
- Security L2, L3, L5 and L7 are deferred.
- The architect flagged that section 2.4 (platform-stack) still uses `:?` ports. That needs a ruling before platform-stack starts.

## Scope
Everything in the diff traces to a rework-1 item or to the original plan step. `ModelClient.complete` is new product surface,
but it is the minimum that N12 needs (the tester pinned it), and it is guarded and traced.
