# platform-sbom U7a rework round 2: security re-check

Date: 2026-10-25. Auditor: security. Scope: U7a rework round 2 GREEN. Only `scripts/sbom_check.py`
changed since r1, and it equals `u7a/r2-target-sbom_check.py`. Diff read:
`git diff --no-index docs/evidence/platform-sbom/u7a/r1-target-sbom_check.py scripts/sbom_check.py`.
Rulings: design-notes l.1300-1382 (items 1-5). Probes: `u7a/security-r2-probes.txt` (script
`u7a/security_r2_probes.py`: the r1 set re-run, then R2-1 to R2-5; gates image, `python -I`).
verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. R1-L1 and R1-L2 are closed. Review R1-B1 (plain paths) and
the pypi layout hold under every trick I tried. No new finding; two informational notes.

| ID | Status | Evidence / input |
|---|---|---|
| R1-L1 | **Closed** | A pypi name of `a-` x 50000 now gives only the name-rule problem in 0.002 s (was 7.2 s). 255-character adversarial names (`a-` runs or `aaaa` before `-3.3.6.tar.gz`) take 0.001 s. `_pypi_parts` on 1 MB takes under 1 ms, and `PYPI_DIST_RE` on 1 MB of `a-` ending in `-` takes 0.006 s. `psycopg_c-3.3.6.tar.gz` stays good for `pypi:psycopg-c@3.3.6` |
| R1-L2 | **Closed** | The temurin path is exact. Rejected: a feature-17 asset in temurin21, another tag, another version asset, extra segments, `Evil-jdk-sources_x.tar.gz`, `+` unencoded, `%2b` lower case, `%2B%2B`, `%252B`, `%2B` in the asset, a JRE or JDK binary asset, the temurin17 repo, a `from` naming another asset. The baseline URL equals the form derived from the design for `temurin:jdk-21.0.12.1+1`: `/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`, with `from` `<asset>.sha256.txt`. This matches the Adoptium naming convention (`jdk-<ver>+<build>` tag, `OpenJDK<N>U-jdk-sources_<ver>_<build>.tar.gz`); U7b confirms it against the release page |
| R1-B1 (review) | Holds | On real-shaped pypi and maven URLs, all are rejected with "not a plain path": `%2e%2e`, `%2E%2E`, `.%2e`, `%2E.`, `..%5c`, a backslash dot-dot, `%2f`, `//`, `/./`, `/../`, a trailing `/`, `%2B` outside the tag, `%25`, double-encoded `%252e%252e`, overlong UTF-8 `%c0%ae`, `%00`. A fullwidth percent and U+2024 dot leaders fail the printable-ASCII rule first, so Unicode normalisation cannot reach the path rule. A `;x` parameter fails the pypi layout |
| pypi layout | Holds | Rejected: upper-case hex, 59 or 61 hex, an extra or missing segment, a path not under `/packages/`, the legacy `/packages/source/p/psycopg/`, non-hex. The baseline Warehouse path passes |
| CLI | Holds | A missing file, invalid JSON, 100000-deep nesting and bad UTF-8 each give exactly one line `lock-check: FAIL (<Class>: <msg>)`, rc 1, no traceback. A hostile name gives no raw control byte |
| I-7 | info, new | The FAIL line for a missing file names the `--lock` path the operator gave (`FileNotFoundError: ... '/tmp/.../absent.json'`). On a host run this can carry a profile path into a log; redact it in evidence as usual |
| I-6 | info, carried | A pypi name in another case (`Psycopg-3.3.6.tar.gz`, `PSYCOPG-...`) passes by PEP 503 normalisation, which is acceptable. A tarball served raw from GitLab at the entry's own commit passes, as the design allows |

## Other checks
- **The r1 set re-run:**
  - Every smuggling, binding, escaping and robustness row that rejected at r1 still rejects.
  - Eight r1 path rows (space, non-ASCII, `../`, `%2e%2e`, backslash, quote, `<>`, `//`) edited a
    `/ab/` segment that the new pypi layout no longer has, so they did not change the URL. They
    are superseded by R2-1 on real-shaped URLs.
  - The old `TEMURIN_ASSET_RE` timing rows raise `AttributeError`, as expected: the pattern is
    gone.
- **`lock_needs` unchanged:** 182 keys and 0 problems, equal to r1. `component_key`, `lock_needs`,
  `classify_document`, `unlicensed_report` and `_clean` are source-identical to r1.
- **ReDoS:** `_plain_path` takes 0.035 s on 1 MB of `/a`, 0.001 s on 1 MB of `%2B` in the tag
  segment, and 0.002 s on `%%2B2B`. `_url_problems` on a 1 MB URL takes 0.033 s, and
  `PYPI_PATH_RE` on 1 MB under 1 ms. `lock_problems` on 20000 entries takes 1.4 s.
- **Evidence hygiene (`u7a/r2-*`, `u7a/r2_controls.py`, `review-r2.md`, `reviewer-r2-*`,
  `tests/test_sources_lock.py`):** no keys, tokens, private keys, JWTs, password values, profile
  paths, SIDs, model-host name or port, or `KE_*` values. The one credential-URL hit is the
  synthetic `https://u:p@` userinfo case of the test. IPs: 127.0.0.1, the stack gateway's internal
  address in the smoke no-route lines, and a Temurin version. `r2_controls.py` works in a
  `mkdtemp` dir it removes.
