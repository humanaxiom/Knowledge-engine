# platform-config: reviewer findings (2026-10-18)

Verdict: **CHANGES REQUESTED** (7 blocking, 13 nits).
Scope reviewed: `git diff 40c0c75` plus untracked `engine/`, `config/`, `.env.example`,
`tests/test_engine_*.py`, `tests/engine_support.py`, `tests/hardcoded_scan.py`.
Mutants, plants, threshold RED runs and the probe: `docs/evidence/platform-config/review-mutants.txt`.

## Criteria status
| Criterion | Status |
|---|---|
| PS-1.1 typed config, KE_ only, secrets with no default | met; the tests can fail (M6, M16b killed). Precedence of KE_ names over standard names is untested (N6) |
| PS-1.2 no hardcoded hosts/ports/models | partly met: scanner false negative B4; nits N1-N4 |
| PS-1.3 egress check at startup | met for prod and ci; dev untested (B3, M15 survives) |
| PS-1.4 egress guard at runtime, DR38 | met (M10, M13, M14 killed; developer mutation.txt) |
| PS-1.5 startup refusals | refusals met (M4, M7, M9 killed); the local-collector rule is bypassed in console mode (B1) |
| PS-1.6 quality gates | the gates fire (my Q1: 52% gives rc 2; Q2: a mypy error gives rc 1), but see B5 and B6 |
| PS-1.7 traced startup | spans asserted (names, CHAIN kind, ke.env, trace id, ERROR, refused_setting, names not values; M12 killed). Exporter wiring untested (B2) |
| PS-1.8 Python pin | met (pyproject literal plus lock equivalence) |
| PS-1.9 placeholders | met (case-insensitive, per key, non-dev; `.dockerignore` excludes `.env*`; the image test is deferred to platform-stack as planned) |

## Blocking
- **B1 Console-mode tracing exports to a non-local collector.** `engine/telemetry.py:50-52` hands
  `console` to `harness_telemetry.setup_tracing`, which re-reads `HARNESS_TRACING` from the raw env
  (default `otlp`) and `PHOENIX_COLLECTOR_ENDPOINT`. `startup.check` refusal 2 applies only to
  `tracing == "otlp"`. Probe: `KE_ENV=prod KE_TELEMETRY__TRACING=console
  PHOENIX_COLLECTOR_ENDPOINT=http://collector.example.com:6006` gives a successful startup and
  `OTLPSpanExporter("http://collector.example.com:6006/v1/traces")`. The same happens if the YAML says `console`.
  This breaks ADR-KE-010 ("OTLP export is attached only after the collector is shown to be local").
  Fix: decide the exporter from `settings` only. For console, pass an explicit `ConsoleSpanExporter`,
  and never let the harness decide again from the env. Add a test.
- **B2 The export gate in `engine/telemetry.py` has no test that can fail.** M1 (local check
  removed), M2 (hide-flag export removed) and M11 (`startup()` no longer calls `configure_tracing`)
  all survive. The cause: `tests/support.py` installs a global SDK `TracerProvider`, so `configure_tracing`
  returns at line 40 before it reaches the exporter path. `test_non_local_collector_gets_no_exporter` and
  `test_configure_tracing_attaches_nothing_for_non_local` therefore pass vacuously. The missing 35% of
  coverage is exactly lines 40-52, the only code that sends data out of the process, so this gap matters.
  M2 matters too: the YAML default `hide_*: true` (PS-Q4) reaches span redaction only through that
  env export. Fix: patch `trace.get_tracer_provider` and `set_tracer_provider` (a proxy provider) and
  `OTLPSpanExporter`. Then assert that:
  - a local collector gets an exporter built with `<endpoint>/v1/traces`;
  - a non-local collector and console mode get no OTLP exporter;
  - the YAML hide defaults land in `OPENINFERENCE_HIDE_*` when the env does not set them;
  - `startup()` calls `configure_tracing`.
- **B3 The egress startup check is not tested outside prod.** Every `test_egress_guard_startup` case
  runs with `KE_ENV` unset, which is YAML `prod`. M15 (skip `check_egress` when `env == dev`) survives, and
  `.env.example` ships `KE_ENV=dev`. A DR30 bypass in the shipped template would go unnoticed.
  Run the refused cases for dev, ci and prod.
- **B4 Scanner false negative: `${VAR:-default}` is blanked in every file.** `tests/hardcoded_scan.py:52`
  applies `_COMPOSE_DEFAULT` to all paths. Plant S1, `PORT=${PG_PORT:-5432}` in `scripts/plant.sh`, is
  missed; the control S7, `psql -p 5432`, is caught. PS-1.2 and the contract docstring allow only
  *compose* variable defaults. Restrict the blanking to `docker-compose*.yml` and add a fixture test for a `.sh` file.
- **B5 `coverage erase` does not remove parallel data files.** Proved in the gates image: after
  `coverage run -p`, the `.coverage.<host>.<pid>.<rand>` file survives `coverage erase`, because
  `parallel` is not set in the config. Any run that stops between `coverage run -p` and `combine` leaves
  these files in the bind-mounted tree, and the next run combines them. Every RED step does this,
  because `set -e` exits at the failing unittest. Stale data can inflate coverage, or give a false
  red after a rename (seen: "No source for code"). The comment at `scripts/test.sh:16` claims the
  opposite. Fix: set `parallel = true` in `[tool.coverage.run]`, or `rm -f .coverage.*` before the run. Pin it with a test.
- **B6 The quality gates can be skipped silently.** `scripts/test.sh` wraps combine, report and mypy in
  `if [ -f pyproject.toml ]` and prints nothing when it skips them. Mutant T1 (`pyproject.tom`) survives `test_engine_quality`
  and `test_harness_followups`. Q3: with that mutant and a tree at 52% coverage, `test.sh fast` exits 0.
  This contradicts the loud-failure rule from harness-followups. The guard exists only for
  the fake project in `IntegrationRunsOnceTest`. Preferred fix (tester and developer): give that
  fixture a `pyproject.toml`, or make the fake `uv` treat `coverage combine`, `coverage report` and `mypy`
  as no-ops, then make the three steps unconditional. Minimum fix: print a loud message when the gates
  are skipped, and pin the exact guard in `test_engine_quality`.
- **B7 Unrecorded deviations from section 2.3. Each needs an architect amendment, an orchestrator ruling, or a revert:**
  - (a) Compose publishes `${KE_PHOENIX_PORT:-47101}`; ruling 1 says `${KE_PHOENIX_PORT:?set in .env}`.
    The blanking hides the literal 47101 from the scanner. A `:-` default may suit a template better
    (`docker compose up phoenix` works with no `.env`), but it must be ruled.
  - (b) `config/defaults.yaml` sets `telemetry.tracing: "off"`, while section 2.3 says `otlp`. The reason was
    a test helper (`base_env` sets `HARNESS_TRACING=off`). `.env.example` does not set
    `HARNESS_TRACING=otlp`, so the yaml comment "the stack .env turns otlp on" is not true of the template.
  - (c) Ruling 1 requires a drift test of compose `${PHOENIX_PORT:-6006}` against the port of
    `telemetry.collector_endpoint`. It does not exist.

## Nits
- N1 Host matching is case-sensitive. S2 (`ssh ARIA-GB10-2`) is missed by rule 1 and by
  `test_model_host_name_only_in_allowed_locations`. DNS names are case-insensitive.
- N2 Scanner file selection is a suffix allowlist. It misses `.conf`, `.j2`, `.html`, `.sql` and `.cypher` files
  (S6), and `docker-compose*.yaml` or `compose.yaml` (S5). platform-stack adds gateway config. Scan all
  text files, or fail on an unknown suffix.
- N3 Rule 2 misses undeclared ports in tuples and dicts (S3 `("0.0.0.0", 9999)`, S4 `{"port": 5433}`).
  This is within the wording of the spec; consider widening the spec.
- N4 The exemption regex `^\s*DEFAULT_COLLECTOR\b` skips any line in that file that starts with
  the symbol. Anchor it to the assignment (`^DEFAULT_COLLECTOR\s*=`).
- N5 `LOOPBACK` in `test_engine_hardcoded.py` includes `0.0.0.0`, which is not a loopback address. The engine
  function `is_local_endpoint` correctly disagrees.
- N6 Two KE_ names reach `models.model_upstream`: `KE_MODEL_UPSTREAM` and `KE_MODELS__MODEL_UPSTREAM`,
  and the second wins. The `KE_TELEMETRY__*` names also coexist with the standard names. Their precedence is
  untested (M5 survives). A bad `HARNESS_TRACING` gives an error naming `KE_TELEMETRY__TRACING`.
  Map the names back through `STANDARD_VARS` and document the order.
- N7 `raise ConfigError(...) from None` (`settings.py:132`) is load-bearing, because the text of a
  `ValidationError` carries input values, but it is untested (M17 survives). Assert `__cause__ is None` and `__suppress_context__`.
- N8 `configure_tracing` duplicates the harness provider construction and sets `service.name` instead
  of the OpenInference project-name attribute, so product traces land in the default Phoenix project.
  Reuse `setup_tracing(PROJECT_NAME, exporter=...)`; this also fixes B1.
- N9 `startup()` builds `Settings` twice: once inside `configure_tracing()` and once in the load span.
- N10 `configure_tracing` returns early whenever any SDK provider is installed, without checking where
  that provider exports. Document this.
- N11 `docker/gates.Dockerfile`: `COPY config` is not needed for `uv sync`. Copying `engine/` before the sync
  invalidates the dependency layer on every engine edit (the existing harness_telemetry copy does the same).
  Consider `uv sync --locked --no-install-project` before copying the sources.
- N12 The section 2.3 table lists a `model.<pass>` LLM span. `ModelClient` has no call method yet, so no
  model call is untraced today. The first call method must come with an `llm_span` and a test.
- N13 Docs drift:
  - `AGENTS.md:149` still gives the default as `http://localhost:6006` (README:23 and :96 are already known).
  - Architecture section 2.3 line 314 shows `tracing: otlp` (see B7b).
  - Section 2.3 names the project `knowledge-engine`; `pyproject.toml` is still `monitored-harness`.
  - Scanner rule 2 is stricter than ruling 2 about loopback URL literals, which is why `smoke_otlp.py`
    moves its host into a variable. Either record that or align the scanner.

## Scope
Everything in the diff is in scope:
- The move of `DEFAULT_COLLECTOR` to 47101 and the compose ports follow ruling 1.
- The `_span` NonRecordingSpan guard fixes a real crash that engine startup triggers when tracing
  is off. It has a regression test whose mutant was proven RED.
- The harness type annotations are required, because PS-1.6 puts `harness_telemetry` under `mypy --strict`.
- The `smoke_otlp.py` edit follows from the scanner.
- The requirements and architecture diffs are plan-step work.

## Verified good
- Settings sources run in the order init > KE_ env > standard names > YAML.
- `extra="forbid"`, so a misspelt nested `KE_` key fails loudly.
- Secrets are `SecretStr`, have no YAML default, and are found at any depth.
- Error messages drop the `input` value.
- The guard checks the host before the inner transport (M14 killed). `trust_env=False` (M10 killed).
  Every redirect hop is checked. The allowlist is exact and case-folded (M13 killed).
- Refusal 2 also applies in dev (M7 killed).
- `verify.sh` is unchanged. The sentinel, run-once and `Ran N` checks still hold, and the coverage output
  does not disturb the sentinel. A clean scratch run of `test.sh fast` passed: 149 OK, 92%, mypy clean.
