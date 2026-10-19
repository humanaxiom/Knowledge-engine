# platform-config rework 2: reviewer re-review (2026-10-19)

Verdict: **CHANGES REQUESTED** (1 blocking, tests only; no production change needed).
Scope: this round's changes to `engine/telemetry.py`, `engine/startup.py`, `engine/config/settings.py`, `pyproject.toml`/`uv.lock`
(`requests`), `tests/test_engine_tracing_guard.py` (new), `test_engine_config.py`, `test_engine_startup.py` and `test_engine_telemetry.py`.
The bar is the orchestrator's: block only on spec violations, broken gates, untested egress/trace paths, or regressions.
Mutants and lock check: `docs/evidence/platform-config/review-rework2-mutants.txt`. The developer run is `green-rework2.txt`:
verify full PASS, 197 OK, 95%, mypy clean, smoke pass. The `engine/telemetry.py` sha256 equals the post-mutation restore
recorded in `mutation-rework2.txt`, so the tree I reviewed is the tree that went green.

## 1. Rework-2 items
| Item | Status | Teeth (reviewer mutants) |
|---|---|---|
| H2 trust_env False session; installed OTLP accepted only if every session ignores proxy env | resolved | W6 (trust_env line removed) KILLED 12. W7 (session check dropped) KILLED 12. W2/W5 (walk too shallow or inverted) KILLED by the accepted-shape controls. The developer's drop-session mutant also KILLED. The export path runs for real under SocketSpy for 4 proxy-env shapes. |
| M3 + R1 verify_provider runs before check() and before any span; non-SDK refused | resolved | V1 (non-SDK accepted) KILLED 9. V2 (old fall-through) KILLED 3. V3 (call deleted) KILLED 24. V4 (verify only when settings load) KILLED 4. A green control proves spans really reach an accepted provider. |
| M4 userinfo refused in every base_url and in model_upstream | resolved | U1 KILLED 18, U2 KILLED 5. The password is absent from the full exception text, and from startup() with the host allowlisted. U3 is equivalent. |
| L1b NFKC plus category strip anywhere | resolved | C1 Cf, C2 Cc, C3 Zs, C6 hangul, C7 CGJ, C8 NFKC and C9 KILLED. C4 Zl and C5 Zp survive (nit R2-N2). The over-refusal control is present. |
| R2 OpenInference project name on the resource | resolved | P1 KILLED 2 |

## 2. Blocking
**B-R2-1 Untested fail-closed branches in the installed-provider check (trace egress path).** `_verify_installed` claims
anything unreadable is refused. Its docstring says the tests pin every shape, so an upgrade that moves the private attributes fails
there instead of silently accepting. Two branches that carry that claim have no test.
- E1: a processor that is neither Simple nor Batch makes `_exporters_of` yield None, which today falls through to the raise.
  The mutant `[e for e in _exporters_of(provider) if e is not None]` SURVIVES. A custom SpanProcessor that ships spans anywhere
  (common in vendor distros) would then be accepted with no failing test.
- W3: an OTLP exporter with no reachable requests.Session is refused because of `bool(sessions) and ...`. The mutant
  `not sessions or all(...)` SURVIVES. If an SDK upgrade moved the session beyond the walk, a proxy-trusting exporter could be accepted.
- Fix (tests only): two cases in `InstalledProviderGuardTest`, and ideally a matching shape in `StartupVerifiesProviderFirstTest.FOREIGN`.
  (a) An SDK provider with a custom SpanProcessor subclass gives StartupRefused("telemetry.tracing").
  (b) A real local OTLP exporter whose session is made unreachable (for example, its transport session attribute deleted or set to
  None, so the walk finds nothing) is refused. Both pass on today's code. Prove each by re-running E1 and W3 as mutants (both must be KILLED).

## 3. Test integrity
- `InstalledProviderTest._real_otlp` (test_engine_telemetry.py:281): the change is **sound**. H2 makes a default-session OTLP exporter
  refusable, so the old accepted shapes would contradict the ruling. The helper now builds them the way the engine does. The refusal test
  `test_non_local_or_unknown_exporter_is_refused` is now stricter: its REMOTE and external-IP shapes also use trust_env False, so they
  are refused for the endpoint alone, and the session check cannot mask a broken endpoint check. The default-session refusal is covered
  separately by `test_local_otlp_that_trusts_proxy_env_is_refused`. The edit cites the ruling inline.
- No other weakening found. All 180 test ids from green-rework1.txt are present in green-rework2.txt, and 17 were added. No new skips.
  Every test file mtime is before red-rework2.txt, so the developer touched no test this round.
- Nit R2-N1: `test_engine_tracing_guard.sessions_of` copies the production `_sessions_of` algorithm. A shared bug would be invisible, but the
  accepted-shape controls (W2/W5 killed) cover that.

## 4. uv.lock and requests
- `uv lock --check --offline` in the gates image: rc 0. A fresh offline relock is impossible (no registry cache), so I do not claim it.
- This round's lock delta for requests is two lines: the project dependency entry and the metadata specifier `>=2.34.2`. That is exactly
  what `uv add requests` writes. The requests 2.34.2 package block and its hashes are unchanged from base, because it was already
  transitive via opentelemetry-exporter-otlp-proto-http. The image build's `uv sync --locked` verified the artifact hashes. No hand edit is indicated.
- Constraint: the lower bound is the version that is already locked, and there is no upper bound, the same style as every other dependency. Sensible,
  because the code now imports requests directly. mypy strict passes without stubs.

## 5. Nits (non-blocking, new this round)
- R2-N2: add U+2028 and U+2029 to L1B_HIDERS. Mutants C4 and C5 survive.
- R2-N3: W1 and W4 (walk stops at the first session; any instead of all) are equivalent today. An exporter with two sessions, one trusting env, would pin all.
- R2-N4: configure_tracing calls verify_provider again after startup() already did. That is harmless and keeps configure_tracing safe on its own. A one-line comment would help.
- R2-N5: with settings unloadable, verify_provider([]) treats only loopback as local (E2 survives). This is intended (pinned as either error
  type). Record it as a sentence in section 2.3 alongside the startup order.
- R2-N6: section 2.3 should now state the startup order (verify provider, then pre-flight check, then configure, then the traced block) and the trust_env rule.

## 6. Deferred, for the close-out record
- Review: R3 (Settings() built twice in startup()), R4 (installed-provider refusal not logged), R5 (ModelClient.complete output attributes,
  non-dict body, base_url ValueError outside the span), R6 (vacuous tests in test_engine_startup.py), R7 (.env.example Phoenix comment).
- Review carried: N1 (host matching is case-sensitive), N2 (scanner suffix allowlist), N3 (tuple/dict ports), N4 (unanchored exemption regex),
  N5 (0.0.0.0 as LOOPBACK in tests), N11 (Dockerfile layer order), N13 (docs drift: AGENTS.md/README localhost:6006, pyproject name monitored-harness).
- Security: L2, L3, L5, L7, I1.
- Architecture: section 2.4 (platform-stack) still uses :? ports, and needs a ruling before platform-stack starts.
- This round: R2-N1 to R2-N6 above. R7 and N13 go to the documenter at the docs gate.
