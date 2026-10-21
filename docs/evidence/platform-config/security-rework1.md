# Security re-audit: platform-config, rework 1 of 5 (2026-10-19)

- Scope: `git diff 40c0c75` (uncommitted, `agent/platform-config`) plus the untracked `engine/`, `config/`, `.env.example` and `tests/` files. Prior findings: `security.md` (H1, M1, M2, L1-L7).
- Method: code read, plus probes in the `gates` image (`network_mode: none`, only `lo`).
  - Regression probe: `security-probe.py`, sections 1-7.
  - New probe: `security-probe-rework1.py`, sections 8a-11.
  - Raw output of both: `security-probes-rework1.txt`. Section references below (P8a etc.) point there.
- **Verdict: FAIL.** 1 high (H2, new), 2 medium (M3, M4, new), 3 low/info. H1, M1, M2, L4 and L6 are fixed. L1 is fixed as scoped, with a residual low.

## Prior findings: status
- **H1 FIXED** (P7, P8a, P8b).
  - Console mode always gets `ConsoleSpanExporter` only. This holds with `HARNESS_TRACING` unset or set to `otlp`, and with an external `PHOENIX_COLLECTOR_ENDPOINT`.
  - With `otlp` and a non-local endpoint, startup refuses and nothing is installed. Endpoints tried: an external `PHOENIX_COLLECTOR_ENDPOINT`, an external `KE_` endpoint, `localhost.evil.com`, `localhost@evil.com`, and dev mode.
  - With a local `KE_` endpoint and an external `PHOENIX_` one, `KE_` wins and the exporter goes to localhost.
  - `harness_telemetry.setup_tracing` is no longer called by the engine.
- **B2 (installed provider), passing path: FIXED** (P8c).
  - Refused: `Simple` or `Batch` with a non-local OTLP exporter, OTLP to `localhost@evil`, an unknown exporter, and `ConcurrentMultiSpanProcessor`.
  - Accepted: local OTLP and InMemory.
  - The refused path is still open; see M3.
- **M1 FIXED.** `git check-ignore -v` shows `.env` and `.env.local` ignored and `.env.example` not ignored.
- **M2 FIXED.** The publish is `127.0.0.1:${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}`, and gRPC is still unpublished.
- **L1 FIXED as scoped** (P6, P9).
  - Refused: a leading space, tab, U+200B, U+200D, NBSP, U+FEFF, U+2060, U+3000, the combination NBSP+FEFF+2060, and a trailing FEFF.
  - The residual is L1b below.
- **L4 FIXED** (P6, P10).
  - A non-JSON `KE_STACK__SERVICE_NAMES`, broken `KE_STACK`/`KE_STORES` JSON, and `KE_MODEL_UPSTREAM` values `[::1...` or `http://[...` all raise `ConfigError`.
  - N7 holds: in 13 malformed cases, no message contains the value, and `__cause__` is None. The parse-failure message lists variable names only.
- **L6 FIXED** (P8d).
  - In five refusal cases with nothing installed, the provider stays a `ProxyTracerProvider`.
  - The operator's `OPENINFERENCE_HIDE_INPUTS=1` is left as it was, and `OPENINFERENCE_HIDE_OUTPUTS` stays unset.
- **Egress guard: no regression.** Probe sections 1-5 are byte-identical to the original run.
  - Section 6 differs only where expected: L1/L4 are now refused or wrapped, and N6 names the variable the user actually set.
  - With the real transport, a denied host makes 0 DNS lookups (P11).
- **Deferred, unchanged: L2, L3, L5, L7.** L7's `from exc` is still at `loader.py`, in the `yaml.YAMLError` branch.

## High (merge-blocking)

### H2. Proxy environment variables reroute the "local" OTLP trace exporter off-host (`engine/telemetry.py:45`)
- `choose_exporter` builds `OTLPSpanExporter(endpoint, timeout=5)` with its default `requests.Session`, which has `trust_env=True`.
- `requests` therefore sends the export through `HTTP_PROXY`, `http_proxy` or `ALL_PROXY` after `is_local_endpoint` has already approved the collector.
- Repro (P8e; KE_ENV=ci, tracing otlp; socket spy records which host is dialled):

  | Collector | Proxy env | Host dialled |
  |---|---|---|
  | `http://localhost:6006` | none | `localhost` |
  | `http://localhost:6006` | `HTTP_PROXY=http://evil.example:3128` | `evil.example` |
  | `http://phoenix:6006` (the default) | `HTTP_PROXY` | `evil.example` |
  | `http://phoenix:6006` | `http_proxy` + `NO_PROXY=localhost,127.0.0.1` | `evil.example` |
  | `http://127.0.0.1:6006` | `ALL_PROXY` | `evil.example` |

- Impact:
  - This is the same outcome as H1: PS-1.5, DR39 and Q3 are defeated, and spans leave the host while startup reports the collector as local.
  - Only env is needed. Docker injects the client's `proxies` config (`~/.docker/config.json`) as `HTTP_PROXY`/`NO_PROXY` into every container. That is common on campus and corporate networks, and a typical `NO_PROXY` does not list compose service names such as `phoenix`.
  - The export is plain HTTP, so the proxy sees span names, `ke.*` attributes (env names, hosts checked, refused setting) and exception messages. In dev, with the hide flags off, it also sees prompts.
  - ADR-KE-010 already treats proxy env as a reroute vector: `ModelClient` uses `trust_env=False`. The trace exporter is the one outbound HTTP path in `engine/` without that protection.
- This is not a rework regression. The otlp branch had it from the start, and the first audit tested proxies only on `ModelClient`. It is in this diff (`engine/telemetry.py` is new), so it blocks.
- Fix (developer):
  - Build the exporter with `session=` set to a `requests.Session()` whose `trust_env = False`.
  - In `_verify_installed`, accept an installed local OTLP exporter only if its `_session.trust_env` is False. Otherwise refuse it, because it was not built by the engine.
  - Tests:
    - A fast test that `choose_exporter(...)._session.trust_env is False`.
    - A socket-spy test like P8e: with `HTTP_PROXY` set, the only host dialled is the collector host.
    - A DR38 mutant that drops `session=`.

## Medium (non-blocking)

### M3. Spans reach an unverified, already-installed provider before (or instead of) the provider check
- `startup()` (`startup.py:110-116`) runs the pre-flight `check()` before `configure_tracing` verifies the installed provider. `check_egress` opens `chain_span("engine.egress.startup_check")` (`startup.py:60`), and that span is emitted to whatever provider is installed.
- On a refusal, `configure_tracing` (and so `_verify_installed`) is skipped, but the traced block still runs.
- Repro (P8c), with a pre-installed provider that has a non-local OTLP or unknown exporter:
  - Passing env: `engine.egress.startup_check` reaches it before the refusal.
  - Refusing env (auth off): `engine.config.load`, `engine.startup.refusals` and `engine.startup` all reach it, and the provider is never checked.
- So "is any span able to reach a non-local collector?" Yes, in this case.
- This contradicts §2.3 / ADR-KE-010 rework 1: "an already-installed provider is verified, not trusted"; "in production no exporter exists and the spans go nowhere".
- Why medium, not high:
  - It needs in-process code to install a provider before `startup()`. No engine code does that, and no auto-instrumentation distro is in `uv.lock`.
  - The leaked content is metadata only: env names, hosts checked, refused setting, `ke.env` and the exception message. No secret or input/output value leaks.
- Fix: verify any installed SDK provider first in `startup()`, before any span opens and whether or not `check()` passes. Refuse if it fails. Add a test that a refusing env with a foreign provider installed gets zero spans.

### M4. Credentials in a model `base_url` reach exported spans through the exception message
- `ModelClient.complete` (`client.py:40-44`): when `base_url` carries userinfo (`http://u:pw@allowed.example/v1`), `raise_for_status()` raises `HTTPStatusError`. Its message contains the full URL with the password. The span records the exception event, and `OPENINFERENCE_HIDE_*` do not redact exception messages (P11, `pw-in-span=True`).
- `check_egress` reads only the host, so it accepts the URL. `AnyHttpUrl` keeps the userinfo.
- AGENTS.md says "never put secrets in span attributes". This is a misconfiguration path, but the operator gets no warning.
- Fix: reject userinfo in `models.*.base_url` (and in `model_upstream`) at load, with a `ConfigError` that names the key. Credentials belong in a `SecretStr` header field when a later item needs them. Add a fast test.

## Low / info (non-blocking)
- **L1b. The placeholder check is still bypassed by other invisible or look-alike characters** (P9).
  - Starts in `ci` with a leading U+180E, U+00AD, U+034F, U+2061 or U+2062, a Hangul filler (U+115F, U+3164, U+FFA0), a bidi control (U+202E, U+2066), or a tag character (U+E0020).
  - Also starts with an inner U+200B, a fullwidth `changeme`, a single space, or `x`.
  - The threat is a forgotten placeholder, not a hostile operator, so this stays low.
  - Suggest: NFKC-normalise, drop every category Cf/Zs/Cc character plus the Hangul fillers anywhere in the value, then test the prefix. Consider a minimum length outside dev.
- **I1. `complete()` relies on the env hide flags being set by `startup()`** (P11).
  - If a provider exists and `startup()` was not called, the flags are unset and the prompt is recorded unredacted.
  - The production path always calls `configure_tracing` first, so nothing leaks today.
  - Optional: read the flags from `Settings`, which `ModelClient` already has.
- **I2. `engine/errors.py`: no issue.** `StartupRefused(setting, reason)` messages carry setting names and hosts, never secret values. The import-cycle split is sound.

## New code: other checks
- **`complete()`:**
  - Every request goes through `self.http_client`, which is `GuardedTransport` + `trust_env=False`.
  - Denied hosts and redirect-to-evil raise `EgressDenied`, the `model.<pass>` LLM span is marked ERROR, and the exception message names only the host. The real transport makes 0 DNS lookups for a denied host.
  - The input is redacted when `hide=true`, and the response is never recorded as output.
  - With hide on, the 401 body (`BODY-<value>`) does not reach the span.
- **`_EnvSource`:** `KE_MODELS__MODEL_UPSTREAM`, `KE_MODELS='{"model_upstream":...}'` (JSON) and the lowercase `ke_models__model_upstream` are all dropped. `KE_MODEL_UPSTREAM` is the only name (P10).
- **Secrets and profile paths:**
  - Scanned the full `git diff 40c0c75` plus every untracked file, including all `docs/evidence/platform-config/*` (900 KB). Patterns: cloud/GitHub/OpenAI/Slack keys, PEM private keys, JWTs, credentialed connection strings, `password=`/`api_key=` literals, and Windows/Unix profile paths in plain and JSON-escaped form, plus the user name and e-mail.
  - The only hits were test fixtures (`changeme-x`, `evil.com` probe URLs) and one evidence line that says "session scratchpad" without a path. Clean.
- **Dependencies:** no new packages since the first audit. `requests` 2.34.2 is transitive, through the OTLP exporter.
