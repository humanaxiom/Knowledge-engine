# Security re-audit: platform-config, rework 2 of 5 (2026-10-19)

- Scope: `git diff 40c0c75` (uncommitted, `agent/platform-config`) plus untracked `engine/`, `config/`, `.env.example`, `tests/`, and the new evidence files. Prior: `security-rework1.md` (H2, M3, M4, L1b).
- Method: code read, plus probes in the `gates` image (`network_mode: none`, only `lo`).
  - Regression probe: `security-probe.py` (sections 1-7).
  - New: `security-probe-rework2.py` (sections 0-5) and `security-probe-rework2b.py` (3b, 5b).
  - Raw output: `security-probes-rework2.txt`. Section references below (S1 etc.) point there.
- **Verdict: PASS.** No open critical or high finding. H2 is fixed, M3/R1 is fixed, M4 is fixed, and L1b is fixed for its listed characters. New, non-blocking: one medium (M5), two lows (L1c, L8), and info items.

## Prior findings: status
- **H2 FIXED** (S0, S1, S2).
  - The engine's exporter session is `_client._transport._session` with `trust_env=False` and empty `proxies`.
  - S1 ran 4 endpoints x 11 proxy-env sets, 44 runs in total. Endpoints: `phoenix:6006` (the default), `localhost`, `127.0.0.1` and `[::1]`. Proxy env: none, `HTTP_PROXY`, `http_proxy`, `ALL_PROXY`, `all_proxy`, `HTTPS_PROXY`, all of them at once, `+NO_PROXY=localhost,127.0.0.1`, `+no_proxy` empty, `+NO_PROXY=*`, and `+REQUESTS_CA_BUNDLE/CURL_CA_BUNDLE`.
  - In all 44 runs the only host dialled was the collector. 0 runs dialled `evil.example`.
  - Installed-exporter check (S2, with `HTTP_PROXY` set):
    - Refused: a default session (`trust_env=True`); a session swapped for one with `trust_env=True`; `trust_env` flipped to True after the build; a session replaced by a custom non-Session object; an `OTLPSpanExporter` subclass; a raw-socket (non-requests) exporter. The gRPC exporter is not installed.
    - **Accepted while dialling evil:** `trust_env=False` with explicit `session.proxies`. See M5.
- **M3 / R1 FIXED** (S3, S3 order).
  - `verify_provider` runs before the first span in passing, refusing and ConfigError runs.
  - Six settings cases were tried: passing ci, passing dev, auth off, placeholder, non-local collector, ConfigError. Against them, these providers all got 0 spans and startup refused `telemetry.tracing`: SDK + unknown exporter, SDK + external OTLP, SDK + local OTLP that trusts env, and a non-SDK API provider.
  - `service_names=["evil.example"]` with an installed OTLP to evil is refused.
  - `OTEL_PYTHON_TRACER_PROVIDER=sdk_tracer_provider` loads an SDK provider with no processors, which is harmless.
  - `chain_span` is the only span helper in the startup, config and egress modules.
  - Residual: see M5 and I3.
- **M4 FIXED** (S4). Tested on every pass `base_url` and on `model_upstream`.
  - Refused with `ConfigError`, and the password is never in the message: `u:pw@`, `u@` (empty password), `:pw@`, bare `@`, `%40` in the user plus a real `@`, IPv6 with userinfo, a backslash before `@`, a tab or newline inside the userinfo, an uppercase scheme, no scheme, and a leading space.
  - Allowed, as intended: `@` in the path, query or fragment, and IPv6 without userinfo.
  - Edge: `KE_MODEL_UPSTREAM=http://u%3Apw%40allowed.example/v1` loads. There is no userinfo by URL semantics: the whole string is the host, so it fails the allowlist. That host string is then recorded in `ke.hosts_checked` and in the refusal message. Info only (I4). `base_url` rejects the same value.
- **L1b FIXED as listed** (S5, 5b).
  - Every character on the rework-1 list is refused before, inside and after the first letter. So are the new ones tried: U+200C, 2063, 2064, 1160, 202A, 2069, LRM, ALM, E0001, LS, PS, VT, U+001F, NEL and U+1D173.
  - NFKC forms are refused: fullwidth, math bold, double-struck, circled and superscript.
  - Ligatures: no NFKC ligature decomposes to a substring of `changeme`, so there is no case to test (controls behave).
  - Combining marks (U+0301 on `a`, `c` or `m`, U+0300 after the final `e`, U+0336) start. They render as visibly different text, so this is info.
  - Homoglyphs (Cyrillic `с`, `а`, `е`; Latin alpha) start. **Info only, out of scope.**
  - Residual: see L1c.
- **Egress table: no regression.** Probe sections 1-7 match the rework-1 run line for line. The only differences are 3 expected lines, where userinfo upstream and `base_url` cases now fail at load with `ConfigError` (M4) instead of at the allowlist.

## Medium (non-blocking)

### M5. An installed OTLP exporter can still route off-host while passing `_verify_installed` (`engine/telemetry.py:94-118`)
- `_ignores_proxy_env` checks only `trust_env is False`, and `_verify_installed` checks only `exporter._endpoint`.
- In S2 and 3b, full `startup()` reported "startup OK" and spans were exported to `evil.example` for three shapes:
  - `trust_env=False` plus explicit `session.proxies` (`http` or `all` set to a proxy). This is a plausible non-hostile configuration.
  - `trust_env=False` plus a mounted rerouting `HTTPAdapter`.
  - An exporter built for evil with `_endpoint` rewritten to localhost. The real URL is `_client._endpoint`.
- Why medium: same precondition as M3. In-process code must install a provider before `startup()`, no engine code does that, and the payload is metadata.
- Fix (developer):
  - Simplest and robust: accept only a provider and exporter the engine built itself (a module-level identity marker set in `configure_tracing`), and refuse every other SDK provider.
  - Or, at minimum: require empty `session.proxies`, only stock `HTTPAdapter` instances in `session.adapters`, and every reachable `*endpoint` string attribute local.
  - Add a test per shape.

## Low (non-blocking)
- **L1c. Placeholder still hidden by a few invisible non-Cf characters** (S5).
  - These start in ci, before or inside `changeme`: variation selectors U+FE00-FE0F and U+E0100-E01EF (Mn), Khmer U+17B4/17B5 (Mn), braille blank U+2800 (So), U+1D159 and U+FFFC (So).
  - Same threat model as L1, a forgotten placeholder. Suggest also stripping default-ignorable code points (variation selectors, U+17B4/5) and U+2800, or comparing on a letters-only projection.
- **L8. Profile path with the OS user name in committed evidence.** `docs/evidence/platform-config/mutation-rework2.txt` lines 2 and 4 contain a Windows profile temp path (C:/Users/USERNAME/AppData/Local/Temp/...). Replace it with a neutral label before commit.

## Info
- **I3.** Hostile in-process code can still pass verification: an SDK processor subclass with its own `on_end` sink, a `requests.Session` subclass that rewrites the URL, or a custom transport plus a decoy `trust_env=False` Session attribute. These are out of scope, since in-process code is inside the trust boundary. The M5 identity-marker fix closes them too.
- **I4.** `ke.hosts_checked` and the egress refusal record whatever host string is configured, including percent-encoded junk. These come from operator config only.
- **I1 (deferred, unchanged):** `complete()` relies on `startup()` having set the hide env flags.
- Deferred and unchanged: L2, L3, L5, L7.

## Dependency: `requests`
- It is now a direct dependency (`requests>=2.34.2`). `uv.lock` pins 2.34.2 with sdist and wheel sha256 hashes that match PyPI (`f288924c...b9ed` and `2a0d60c1...78e0`). `verify.sh` installs with `--locked`.
- 2.34.2 is the latest PyPI release (2026-05-14), and PyPI lists no vulnerabilities for it.
- It is past the fixes for CVE-2024-35195 (2.32.0) and CVE-2024-47081, the netrc leak fixed in 2.32.4. With `trust_env=False`, netrc and env CA settings are ignored anyway.
- Transitive `urllib3` is 2.8.0.

## Secrets and paths
- Scanned the full `git diff 40c0c75`, every untracked file (including all `docs/evidence/platform-config/*`) and this run's probe output, about 1.3 MB.
- Patterns: AWS, GitHub, OpenAI and Anthropic, Slack and Google keys, PEM private keys, JWTs, credentialed URLs, and `password`/`api_key`/`secret`/`token` literals.
- The only hits were test fixtures (`changeme*`, `hunter2`, `s3cr3t-VALUE`, `evil.example`) and test-name strings.
- Path scan: one hit, L8. No e-mail addresses.
