# platform-sbom U7b: security gate audit (the resolver, its host script and its compose service)

Date: 2026-10-25. Auditor: security. Tree: HEAD 9b1754f (U7a) plus the U7b working tree.
`scripts/sources_resolve.py`, `scripts/sources_lock.sh`, `docker-compose.sources.yml` and
`scripts/sbom_check.py` equal their `u7b/target-*` copies. Probes: `u7b/security-probes.txt`
(script `u7b/security_probes.py`; gates image, `python -I`; fake network only, by replacing
`OPENER`; no real request). verify.sh not run.

## Verdict: PASS

No critical or high finding. One medium and five low findings, all non-blocking by the rubric.
Fix M-1 before the tool first writes a real lock (U7c): it lets the tool write an incomplete
lock while reporting only "neo4j pending".

| ID | Severity | Finding (input) |
|---|---|---|
| M-1 | medium | `sources_lock.sh` step 5 decides "pending" from the truncated `lock-check` output (the first 20 lines). With the real fixtures, a lock holding every key but neo4j and pgdg gives 78 problems: 73 neo4j misses, then 5 pgdg misses. Only 20 neo4j lines are printed, so the rule at l.141-143 sets `pending=1`. The tool then writes `docker/sources.lock.json` with the pgdg gaps hidden and exits 3, "neo4j entries pending". Any miss for a key that sorts after `neo4j:` (pgdg, pypi, temurin) and any stale entry can hide the same way. Fix: decide pending in Python over the full problem list (for example `lock-check --allow-missing neo4j`, or a machine-readable list), never by grepping 20 printed lines |
| L-1 | low | `fetch()` checks scheme and hostname only, so an allowed host with a port or userinfo is requested, on the first URL and on any redirect: `https://github.com:8443/a`, `https://evil@github.com/a`, `https://evil.example<backslash>@github.com/a` (urlsplit takes the host after the `@`). None reaches a non-listed host. Fix: apply the U7a `_url_problems` rules (printable ASCII, round-trip, no userinfo or port, plain path) to every hop |
| L-2 | low | `pypi.org` is in the allow set for every request, so any route redirect may go to `https://pypi.org/...`. Restrict it to the JSON request of the pypi route |
| L-3 | low | `stream()` has no size cap and no total deadline: a 3 GiB body was hashed to the end. The timeout is per socket operation, so a slow server can hold the run. Fix: stop at the lock size cap (4 GiB, `MAX_FILE_SIZE`) and add a total deadline per file |
| L-4 | low | An error while reading a body escapes as a raw exception (`IncompleteRead`, `OSError`, `TimeoutError`): `main()` gives a traceback, not the Q61 `sources_lock: FAIL (resolve: ...)` line. It still fails closed: nothing is written (`out/` stays empty) and the shell script fails on the exit code. Wrap body iteration in `ResolveError` |
| L-5 | low | The lock is written via `mktemp docker/.sources.lock.json.XXXXXXXX`, mode 0600, so `docker/sources.lock.json` ends up 0600. On a Linux host the gates container (uid 10001, read-only bind of the checkout) cannot read it, and verify fails closed. `chmod 0644` before the `mv` |
| I-1 | info | The real opener reads a whole 3xx/4xx body into memory (`exc.read()`), with no limit |
| I-2 | info | Egress is the default bridge of the `ke-sources-<random>` project, unrestricted at network level. The in-process allowlist is the only host control. The stack networks (`backend`, `edge`) and the gate services belong to other projects and are not attached. Host-published ports are reachable only by IP literal or a non-listed name, which the allowlist refuses |
| I-3 | info | Keys from `needs.json` are not validated against `LOCK_KEY_RES` before requests, so an odd SBOM version can put `../` or `?` into a path on a fixed host (maven, neo4j, temurin URLs are built from the key). The final `lock-check` rejects such a lock, and the host never changes |
| I-4 | info | `tar_file_text` skips hard links and ignores whiteouts, so a lower layer copy of the release file could win. The release text must agree with the SBOM version, which fails closed |

## 1. SSRF and redirects (probe U7b-1)
- **First URL:** `http`, a non-listed host, `github.com@evil`, a trailing dot and an IDN
  look-alike are refused before any request. Port and userinfo forms are requested (L-1).
  Upper case is lower-cased and allowed.
- **Redirects:**
  - A relative (`/b`, `b`) or 308 redirect stays on the same host.
  - Refused: scheme-relative `//evil`, `http`, `github.com@evil`, IDN, trailing dot, `data:`,
    `file:`, `javascript:`, a tab that builds another host, an empty Location, a 3xx without
    Location, 304 and 100.
  - `https:<backslash>evil` resolves to a path on the same host.
  - CR/LF cannot reach a real header: http.client splits lines, and urljoin strips them.
  - A loop or more than 5 redirects gives "more than 5 redirects" after 6 requests.
  - A 2xx on an intermediate hop is final, and its Location is ignored.
- **Other handlers:** `ProxyHandler({})` drops proxy variables. The default file, ftp and data
  handlers of `build_opener` stay, but the scheme check runs before any request.
- **`pypi.org`:** reachable on any route by redirect (L-2). The JSON sdist URL must be on
  `files.pythonhosted.org`.

## 2. Streaming (probe U7b-2)
- The hash covers exactly the bytes received: a lying `Content-Length` (10) does not change it.
- No decompression: a gzip `Content-Encoding` body is hashed raw, because urllib sends no
  `Accept-Encoding` and does not decode.
- Nothing is stored. Only `<out>/.lock.new.json.tmp` and `<out>/lock.new.json` are written.
- `text()` stops at 1 MiB.
- There is no size cap or total deadline on `stream()` (L-3), and errors in the body escape as
  raw exceptions (L-4).

## 3. Trust on first use (probe U7b-3)
- A neo4j key with no entry streams once and prints `neo4j candidate: {...}` (JSON, so control
  characters are escaped). Exit 3. The new lock does not contain the key.
- A manual entry is never requested and never rewritten, with or without `--refresh` (the check
  at l.333 runs first). A generated route cannot overwrite a manual entry under any key.
- A manual entry that no image needs is kept; `lock-check` then reports it.
- The candidate cannot be accepted automatically. The entry is only ever written by hand and must
  equal `sources-provenance.md` (sha256 `182ae2e5...91e3`, size 20907800).

## 4. `sources_lock.sh`
- `set -euo pipefail`. `--arch` is whitelisted. Image references come from `compose config` and
  must pass `ref_re`. Names are `[a-z0-9._-]`. Every expansion is quoted.
- The work dir comes from `mktemp -d` under `TMPDIR` (0700 subdirectories), and the EXIT trap
  removes it and takes the compose project down. There is a 7 GiB floor.
- The SBOM step runs with no network; `lock-needs` and `lock-check` run with `--network none
  --read-only --cap-drop ALL`.
- Only `--env-file .env.example` is used, so the root `.env` is not loaded. `KE_SOURCES_*` are
  compose interpolation only. The container environment is the one literal
  `PYTHONDONTWRITEBYTECODE`, so no secret or `KE_*` key reaches it. `COMPOSE_FILE` and
  `COMPOSE_PROFILES` are unset.
- The output is `git diff --stat` only.
- M-1: the pending rule on truncated output. L-5: the 0600 mode.

## 5. Compose hardening
`sources-resolve` matches the `sbom` service: read-only, tmpfs `/tmp`, `cap_drop: ALL`,
`no-new-privileges`, the caller uid:gid, `pull_policy: never`, read-only mounts plus one rw
`/out`, no socket, no published port, no `extra_hosts`. The one intended difference is the
network: the project default bridge instead of `network_mode: none` (I-2).

## 6. `lock-needs` tar reading
- It reads the manifest and its layer blobs by member name and never extracts, so path
  traversal and symlinks have no file-system effect.
- Only regular files whose `_rel` name equals `opt/java/openjdk/release` are read, and each read
  stops at 1 MiB. The top layer wins (I-4).
- Errors give one `lock-needs: FAIL (...)` line.

## 7. Evidence hygiene (`u7b/*`, `sources-provenance.md`, `tests/test_sources_resolve.py`)
- No keys, tokens, signed query strings, private keys, password values, profile paths, SIDs or
  model-host name or port.
- The credential-URL hits are synthetic (`https://user:pw@repo1.maven.org/x.jar` in the reviewer
  probes). The one `KE_MODEL_UPSTREAM=` is a test refusing such a key.
- IPs: GitHub public addresses (provenance hops), 127.0.0.1, the internal address of the stack
  gateway in the smoke no-route lines, and a Temurin version.
