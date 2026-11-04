# platform-sbom U7d: security code audit (pgdg route, Sources binding, bounded retry)

Date: 2026-10-26 (UTC). Auditor: security. Tree: HEAD 86f7831 (U7c) plus the U7d working tree
(`git diff HEAD -- scripts/ docker/source-policy.json`). `sources_resolve.py`, `sbom_check.py`
and `source-policy.json` equal `u7d/target-*`. `sources_lock.sh` differs from its target in one
line, the Windows fix `docker save -o "$(hostpath ...)"` (quoted, benign). Design l.2107-2490.
Probes: `u7d/security-probes.txt` (script `u7d/security_probes.py`; gates image, `python -I`;
fake network, pure parsers, the fixture lock; no external request). The lock and
`u7d/lock-run-*` were not touched or read. verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. One low and four informational notes. My design-review
items A-1 (uncompressed Sources, per-stanza duplicates), R-2 (a run budget of 20 retries and
3 h), R-3 (the pause before every snapshot attempt), R-4 (`?<query omitted>` in retry lines)
and R-5 (the never-retried classes) are implemented and hold.

| ID | Severity | Finding (input) |
|---|---|---|
| L-1 | low | The copy step follows symlinks. `[ -f "$f" ]` and `cp` both dereference, so a `pgdg-x.InRelease` symlink placed in `$work/out` by a compromised resolver (it writes `/out` as the caller uid) would copy the host file it points to into `docs/evidence/`. The suite name itself cannot traverse: it is checked against `[a-z]+-pgdg-archive` before use, and a glob match cannot contain `/`. Fix: skip `-L` entries (`[ -f "$f" ] && [ ! -L "$f" ]`) or use `cp -P` and refuse a link |
| I-1 | info | The final error line after the last retry still prints the full URL, query included (`github.com: HTTP 503: https://github.com/a?sig=...`); only the retry lines omit it (R-4) |
| I-2 | info | `lock-check` does not bind an entry `suite` to the distro of its packages: `trixie-pgdg-archive` (with a matching `from`) on the bookworm postgresql-common entry passes. The URLs are the shared pool, so no file changes; only the provenance text would be wrong. `lock-needs` computes the right suite, and `lock-check` could compare against it |
| I-3 | info | The Sources stream rescans a growing buffer for a blank line; 60 MiB with no blank line takes 19 s. It is bounded by the Release size (5 MB today) and the 64 MiB cap |
| I-4 | info | The U7c I-5 nonce is gone from the test (now `__goaway_id=0000synthetic0nonce...`). It remains in the committed `u7c/r1-red-verify-fast.txt`; it is not a credential |

## 1. InRelease stripping (probe U7d-1)
The parser only ever reads text that gpgv would verify:
- A second signed block, or text after `END PGP SIGNATURE` (even with a SHA256 field), is ignored.
- A prefix before `BEGIN PGP SIGNED MESSAGE` makes the armour lines "not a field or continuation",
  which fails closed.
- Dash-escaped field and continuation lines are undone, as in OpenPGP. CRLF works.
- A Sources line injected as a continuation of another field is not read: only `SHA256` is read.
- Refused: a second `SHA256` field (also lower-case `sha256`), a Sources line listed twice in it,
  upper-hex, `./main/source/Sources`, U+2028 in an armour header, NUL in the body.
- The raw bytes used are the ones saved for gpgv (`_PGDG_INRELEASE[suite] = raw`). The signature
  is not verified in the tool (P-R1); S8 verifies it.

## 2. Sources binding (probe U7d-2)
- The read stops as soon as the size passes the Release size: 371 of 284365 bytes pulled.
- A shorter body, or a hash that differs from the Release, fails.
- Stanzas are parsed while streaming, but `kept` is returned only after the size and sha256
  checks pass. A tampered index holding the needed stanza returns nothing.
- Duplicate fields are refused per stanza; a non-UTF-8 byte or a separator in any stanza fails.
  CRLF and whitespace-only separator lines follow deb822.
- Two stanzas with the same Package and Version are caught later ("more than once").
- The `Directory` pool rule, the `.dsc` sha256 against the stanza, and the stanza and `.dsc`
  file-set cross-check are all in `resolve_pgdg`.

## 3. Retry loop (probe U7d-3, patched `SLEEP`)
- 503 three times then 200: 4 requests, waits 10/30/60. A fourth 503 fails.
- **Never retried, never slept:** 404, 418, 429 (with `Retry-After`), `ConnectionResetError`,
  `ssl.SSLError`.
- A connect or mid-body timeout is retried, and the restart hashes the full new body (fresh
  hashers). A 5xx on hop 2 restarts from hop 1.
- The run budget (patched to 2) refuses the third retry without sleeping. A wait that would end
  past the run deadline fails before sleeping, and a passed deadline makes no request.
- `fetch()` defaults to `retries=0`, so U8 gets one call.
- Snapshot: 4 attempts, 4 pauses. The run budget caps snapshot amplification at 20 extra
  requests per run.
- There is no nested retry: each `once()` uses `_fetch_once`.

## 4. pgdg lock rules (probe U7d-4, the 182-key fixture lock, baseline clean)
- Refused:
  - **Path:** pool letter `q` or `post`, a `dists/` path instead of `pool/`, `+` as `%2B`,
    another source directory.
  - **Host:** `apt.postgresql.org`, `snapshot.debian.org`.
  - **URL form:** a query.
  - **Suite:** `bookworm-pgdg` (non-archive), a suite with a slash, upper case, missing.
  - **Other:** a sixth key, a `from` naming another suite than the entry, sha1 upstream on the
    `.dsc`, a `.dsc` alone.
- `+` and `~` stay literal. The `lib` rule gives `libp` for `libpq`.
- Open: I-2.

## 5. The copy step (`sources_lock.sh`)
- It runs only after `lock-check` passed and the lock was moved into place.
- The file name comes from a validated suite. Open: L-1.

## 6. Evidence hygiene (`u7d/*`, excluding `lock-run-*`)
- `build.txt`, `green-*`, `red-*`, `s7-*`, `reviewer-*`, `suite-probe.txt`, the controls and
  targets were checked.
- No keys, tokens, signed queries, private keys, password values, profile paths, SIDs, or
  model-host name or port.
- IPs: 127.0.0.1, the stack gateway address in the smoke no-route lines, and a Temurin version.
