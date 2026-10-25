# platform-sbom U7a rework round 1: security re-check

Date: 2026-10-25. Auditor: security. Scope: U7a rework round 1 GREEN; only `scripts/sbom_check.py`
changed since the U7a GREEN, and it equals `u7a/r1-target-sbom_check.py`. Diff read:
`git diff --no-index docs/evidence/platform-sbom/u7a/target-sbom_check.py scripts/sbom_check.py`.
Rulings: design-notes l.1163-1298. Probes: `u7a/security-r1-probes.txt` (script
`u7a/security_r1_probes.py`; gates image, `python -I`; baseline `good_lock(SMALL_KEYS)`, which
passes clean with the committed policy). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. U7a L-1, L-2 (except temurin, below), L-3, L-4, I-2 and I-4
are closed. Two new low findings and one informational note, all non-blocking.

| ID | Status | Evidence / input |
|---|---|---|
| L-1 | **Closed** | Rejected: tab or LF in the host, CR, leading or trailing space, leading NUL, space or non-ASCII in the path (`not printable ASCII`), `HTTP://` and `HTTPS://` (no round-trip), and `../` (a `..` segment) |
| L-2 | **Closed except temurin** | maven: github.com, another version path, another artifact or a binary jar are all rejected. apk: an APKBUILD at another commit, repo or origin, or from distfiles, and a tarball at another branch or a gitlab raw at another commit, are rejected, as is an entry commit that changed. pypi: github.com, `psycopg_c`/`psycopg-c` for `psycopg`, another version, `-1`, `binary`, `.zip`, `.whl`, a basename not equal to the name. deb: `.dsc` sha1 not equal to its URL either way, orig on gitlab, an upper-case sha1, `.dsc` alone. neo4j: a second file, another tag, another name, sha1 upstream, a value not equal to the file sha256, codeload. pgdg: every file is a problem until Q71 (fail closed). `KIND_HOSTS` is a subset of the committed hosts |
| L-3 | **Closed** | A hostile lock (ESC/CSI in keys, file name, url and a file key) plus SBOM purls with `%1b` give 11 problems with 0 raw control lines |
| L-4 | **Closed** | `u7a/reviewer-probes.txt` l.2 now reads `<scratch>\probe_u7a.py` |
| I-2 | **Closed** | size above 4 GiB is rejected (`4294967297`, `10**30`); an `a..b` name is rejected; `CON` fails the pypi binding |
| I-4 | **Closed** | Wrong types (lock not text, list components, entry, files, file, upstream, arches, name or commit of the wrong type, NaN, a 5000-digit int, JSON 100000 deep) are problems, never exceptions. `lock-check` returns rc 1 with one line and no traceback for a deep or huge-int lock and a deep policy |
| R1-L1 | low, new | `PYPI_DIST_RE` is quadratic and runs on names of any length: a pypi file named `a-` x 50000 takes 7.2 s in `lock_problems`, and 10x the length is about 100x the time (1 MB is about 12 min). The name check rejects names over 255 characters, but `_binding_problems` still runs on them. Fix: skip the binding when the name fails `LOCK_FILE_NAME_RE` (255 chars at most, under 1 ms), or make the pattern unambiguous |
| R1-L2 | low, new | temurin binding: only the repo prefix and an asset-name shape are checked. These pass: an asset of another feature in the temurin21 repo (`OpenJDK17U-jdk-sources_17.0.1_12.tar.gz`), another release tag, another version asset, extra path segments, and any prefix (`Evil-jdk-sources_x.tar.gz`). Fix at U7b (where the asset and tag forms are confirmed): path exactly `/adoptium/temurin<f>-binaries/releases/download/<quote(tag)>/OpenJDK<f>U-jdk-sources_<ver, + as _>.tar.gz` |
| I-6 | info | Printable but non-RFC-3986 path characters pass: `%2e%2e`, backslash, `"`, `<>`, an empty `//` segment. Host and kind binding still hold, so nothing changes host. A pypi name in other case (`Psycopg-`, `PSYCOPG-`) passes by PEP 503 normalisation, which is acceptable |

## Other checks
- **`lock_needs` unchanged:** on the six fixtures with the committed policy it gives 182 keys
  and 0 problems, equal to the U7a GREEN. `component_key`, `lock_needs`, `classify_document`,
  `unlicensed_report` and `_clean` are source-identical to the GREEN.
- **ReDoS:** at 10000 characters `PYPI_DIST_RE` takes 0.29 s, and at 50000 it takes 7.1 s (R1-L1).
  `TEMURIN_ASSET_RE` on a 50000-character run takes under 1 ms. `PRINTABLE_RE` on 1 MB takes
  0.004 s. `lock_problems` on 20000 entries takes 1.2 s.
- **Evidence hygiene (`u7a/r1-*`, `u7a/r1_controls.py`, the redacted `reviewer-probes.txt`,
  `tests/test_sources_lock.py`):** no keys, tokens, private keys, JWTs, password values, profile
  paths, SIDs, model-host name or port, or `KE_*` values. The two credential-URL hits are the
  synthetic `https://u:p@` userinfo case of the test, and its RED failure line in
  `r1-red-verify-fast.txt`. IPs: 127.0.0.1, the stack gateway's internal address in the smoke
  no-route lines, and a Temurin version.
