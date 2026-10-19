# platform-config rework 3: reviewer confirmation (2026-10-18)

Verdict: **APPROVED**. B-R2-1 (E1, W3) is resolved and R2-N2 (C4, C5) is closed. There are no blocking findings.
Scope: this round is tests only. The changes are in `tests/test_engine_tracing_guard.py` and `tests/test_engine_startup.py`.
Inputs: the tester section in the handoff (rework 3), `tester-rework3.txt` (verify full PASS, 199 OK, 95%, mypy clean,
smoke pass) and `tester-rework3-mutation.txt`.

## 1. No production change since round 2
- `engine/telemetry.py` sha256 is f9bd5b33ce8eb574b35875fa4a59d7bcd742433d6f343e7a3cc124665679a9bd. That equals the
  f9bd5b33...79a9bd recorded in review-rework2-mutants.txt, the only hash my round-2 notes pinned.
- I checked every other production and config path by mtime: engine/, harness_telemetry/, config/, pyproject.toml, uv.lock,
  .env.example, scripts/, docker/ and docker-compose.yml. None is newer than review-rework2.md (18:22:42). Only two test
  files are newer.
- Current sha256 values, as the baseline for later rounds:
  - engine/startup.py b4e1076c48e49981c0526b7586ae91f9be4c42c0cdddd02b5be1441ecaa60657
  - engine/config/settings.py 335d8aac05a4613c09e660425dca4b51cb919dc5500d8a314e2a5b741b2a0d9b
  - engine/config/loader.py a3f091e45588a48a46e2089944f873a46e85ab8ae92d964a5d605635b15f556c
  - engine/egress.py 4e21f0d5d65dfdf82f9b96fcbfd8b28c415aaf01f448266abdac113aa54325cc
  - engine/llm/client.py dce053c90243e759eece0fe22537c14560ab20eaad039d3d9b5eea13f5fa3312
  - harness_telemetry/tracing.py be427e0446658fc98b88513a47d59024e820167f03ef7c6fe8a3b15988e9778b
  - pyproject.toml ae0b9f0045754032b201b38cce2d57c613627536569d0a281766e1055ac88624
  - uv.lock 048611a760be0a6440156c1feb8f9ce6af63b6bb9b77bbe8531e48b8ccd6328f

## 2. Mutation re-run (reviewer, gates image, no network)
How I ran it: I made a scratch copy of engine/, tests/, harness_telemetry/, config/, pyproject.toml and .env.example, and
mounted it read-only into `knowledge-engine-gates:latest` with `--network none` and HARNESS_TRACING=off.
- Targets: the test_engine_tracing_guard, telemetry, startup, config and llm tests (65 tests).
- Each mutant was applied alone to a fresh copy, by a single-occurrence replace (the run checks the target occurs exactly once).
- The scratch copy was deleted after the run.
- E1: `for exporter in [e for e in _exporters_of(provider) if e is not None]:`
- W3: `return not sessions or all(`
- C4: Zl removed from _STRIPPED_CATEGORIES. C5: Zp removed.

```
BASELINE: Ran 65 tests in 1.315s  OK 
== E1 rc=1 KILLED :: FAILED (failures=15)
      1 FAIL: test_custom_span_processor_is_refused (mode='console')
      1 FAIL: test_custom_span_processor_is_refused (mode='off')
      1 FAIL: test_custom_span_processor_is_refused (mode='otlp local')
      4 FAIL: test_foreign_provider_gets_no_span_with_refusing_settings
      1 FAIL: test_foreign_provider_gets_no_span_with_refusing_settings (provider='sdk, custom span processor', env='ci, auth off')
      1 FAIL: test_foreign_provider_gets_no_span_with_refusing_settings (provider='sdk, custom span processor', env='ci, otlp to a non-local collector')
      1 FAIL: test_foreign_provider_gets_no_span_with_refusing_settings (provider='sdk, custom span processor', env='ci, placeholder secret')
      1 FAIL: test_foreign_provider_gets_no_span_with_refusing_settings (provider='sdk, custom span processor', env='ci, settings do not load')
      2 FAIL: test_foreign_provider_refused_before_any_span_passing_settings
      1 FAIL: test_foreign_provider_refused_before_any_span_passing_settings (provider='sdk, custom span processor', env='ci, passing')
      1 FAIL: test_foreign_provider_refused_before_any_span_passing_settings (provider='sdk, custom span processor', env='dev, auth off (warns only)')
== W3 rc=1 KILLED :: FAILED (failures=6)
      1 FAIL: test_local_otlp_with_unreachable_session_is_refused (shape='batch otlp service name', mode='console')
      1 FAIL: test_local_otlp_with_unreachable_session_is_refused (shape='batch otlp service name', mode='off')
      1 FAIL: test_local_otlp_with_unreachable_session_is_refused (shape='batch otlp service name', mode='otlp local')
      1 FAIL: test_local_otlp_with_unreachable_session_is_refused (shape='simple otlp localhost', mode='console')
      1 FAIL: test_local_otlp_with_unreachable_session_is_refused (shape='simple otlp localhost', mode='off')
      1 FAIL: test_local_otlp_with_unreachable_session_is_refused (shape='simple otlp localhost', mode='otlp local')
== C4 rc=1 KILLED :: FAILED (failures=8)
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2028 line separator before', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2028 line separator before', env='prod')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2028 line separator inside', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2028 line separator inside', env='prod')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2028 line separator before', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2028 line separator before', env='prod')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2028 line separator inside', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2028 line separator inside', env='prod')
== C5 rc=1 KILLED :: FAILED (failures=8)
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2029 paragraph separator before', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2029 paragraph separator before', env='prod')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2029 paragraph separator inside', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__NEO4J__PASSWORD', value='U+2029 paragraph separator inside', env='prod')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2029 paragraph separator before', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2029 paragraph separator before', env='prod')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2029 paragraph separator inside', env='ci')
      1 FAIL: test_placeholder_hidden_by_invisible_characters_is_refused (secret='KE_STORES__POSTGRES__PASSWORD', value='U+2029 paragraph separator inside', env='prod')
POST: OK
```
All four are KILLED, and each one by the intended new test or shape. These results match the tester's host-venv run
(15/6/8/8 failures).

## 3. Test soundness and integrity
- E1 `test_custom_span_processor_is_refused` is sound. It uses a real `SpanProcessor` subclass that records spans. The test
  asserts the StartupRefused setting, that nothing was installed, and that zero spans were shipped, in all 3 modes.
  The matching FOREIGN shape in StartupVerifiesProviderFirstTest asserts, through addCleanup, that the custom processor got no
  spans, both before verification and with refusing settings. That covers the egress path end to end.
- W3 `test_local_otlp_with_unreachable_session_is_refused` is sound. It uses a real local OTLP exporter with
  trust_env=False, so only "no reachable session" can refuse it. The endpoint is local in both shapes, Simple and Batch.
  The helper swaps the session for a non-Session object and asserts `sessions_of(exporter) == []`, so the precondition is
  checked rather than assumed.
- R2-N2: the literal U+2028 and U+2029 characters were added to L1B_HIDERS (I confirmed the bytes are e2 80 a8 and
  e2 80 a9). They are written the same way as the existing entries.
- No weakening:
  - The test id set in tester-rework3.txt is a strict superset of green-rework2.txt (197 to 199; only the 2 new
    InstalledProviderGuardTest ids were added, none removed).
  - There are no skips in either test file.
  - The FOREIGN change only adds subtests.
  - Limit: the test files are untracked, so I could not byte-diff them against round 2. These three checks are the evidence.

## 4. Nits (non-blocking)
- R3-N1: `_make_session_unreachable` checks its precondition with a bare `assert`, which `python -O` strips. The gates do
  not run with -O, so this is harmless. `self.assertEqual` or a raise would be stricter.
- Carried open: R2-N1 and R2-N3 to R2-N6, plus the deferred list in review-rework2.md section 6.
