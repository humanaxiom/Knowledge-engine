# platform-sbom U7b rework round 1: security re-check

Date: 2026-10-25. Auditor: security. Scope: U7b rework round 1 GREEN. `sources_resolve.py`,
`sources_lock.sh` and `sbom_check.py` equal `u7b/r1-target-*`; `docker-compose.sources.yml` is
unchanged. Diffs read against `u7b/target-*`. Rulings: design-notes l.1444-1563. Probes:
`u7b/security-r1-probes.txt` (script `u7b/security_r1_probes.py`; gates image, `python -I`; fake
network, plus one loopback HTTP server for the drip-feed row; no external request).
verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. M-1, L-1, L-2, L-4, L-5, I-1 and I-3 are closed. L-3 is
closed for the byte cap and for slow chunks, but not inside one read of the real opener (R1-L1,
low). No other new finding.

| ID | Status | Evidence / input |
|---|---|---|
| M-1 | **Closed** | `lock-check --pending-neo4j` decides over the full list. The real-fixture lock without neo4j and pgdg (73 + 5 misses) now gives rc 1, as does "all but neo4j and temurin"; only a list of nothing but neo4j misses gives 3 (`test_neo4j_pending_exit_3`, `test_a_truncated_neo4j_list_is_not_pending`). Step 5 branches on the exit code alone; there is no grep |
| L-1 | **Closed** | Refused before any request, on the first URL and on hops: port, userinfo (also the backslash form), fragment, `//`, `/./`, upper-case scheme, tab. On hops also: `%2e%2e` and `%2B` in the path, raw `HTTPS://`/`Https://`, `https:evil`, `https:/evil`, a backslash form, raw tab, LF, space and non-ASCII in the Location (checked before the join), `javascript:`, `a:b`. A query on a hop to an allowed host passes (signed release assets); a query on a hop to a non-listed host does not. A query on a first URL passes the resolver, but the U7a lock rules refuse a query in any lock URL. A relative `/./b` joins to `/b`, which is plain |
| L-2 | **Closed** | `pypi.org` is refused without `first_allow`, allowed only for the first JSON request, and refused on every hop (also a pypi.org to pypi.org redirect) |
| L-3 | **Partly closed** | The cap aborts at the first chunk past it (cap patched to 10 chunks: 11 pulled, then "more than 655360 bytes"). The deadline aborts slow small chunks (patched to 1 s: aborted at 1.0 s). Open: R1-L1 |
| L-4 | **Closed** | `IncompleteRead`, `OSError`, `TimeoutError` and `ValueError` mid-body all become `ResolveError` (`github.com: IncompleteRead: <url>`). `main` prints one FAIL line for any exception, and nothing is written |
| L-5 | **Closed** | `chmod 0644 -- "$tmp"` before `mv`. A `cp` or `chmod` failure fails, and the EXIT trap removes the temp file (`tmp=""` after the move) |
| I-1 | **Closed** | Error and 3xx bodies are read up to 1 MiB, then dropped |
| I-3 | **Closed** | Every needs key is checked against the U7a grammar (`valid_key`) before any URL is built |
| R1-L1 | low, new | The deadline is checked only between chunks. In the real opener one `r.read(65536)` on an `http.client` response loops over `recv` until 64 KiB or EOF, and each `recv` is under the 60 s socket timeout. A server sending 1 byte every 50 ms held one read for more than 12 s against a deadline patched to 2 s (loopback, Content-Length 100000). With a drip just under 60 s per byte, one chunk can take weeks. Only listed hosts are contacted, so the impact is a stalled maintainer run. Fix: read with `r.read1(CHUNK)` (one `recv`), or set the socket timeout to the remaining deadline before each read |

## Script paths
- Tools come first: with `docker` missing, the run fails with
  `sources_lock: FAIL (tools: docker not on PATH; the lock is unchanged)`, rc 1, before any
  write.
- Exactly the six images are required: an extra or a missing name fails
  (`test_exactly_the_six_images`).
- `$work/sboms/tmp` is created with 0700. `--tar` is given only for ke-neo4j.
- The trap removes the work dir, the compose project and the temp file.

## Evidence hygiene (`u7b/r1-*`, `r1_controls.py`, `reviewer-r1-*`, `tests/test_sources_resolve.py`)
No keys, tokens, signed query strings, private keys, password values, profile paths, SIDs, or
model-host name or port. The credential-URL hits are the synthetic
`https://user:pw@repo1.maven.org/x.jar` test and reviewer cases. IPs: 127.0.0.1, the internal
address of the stack gateway in the smoke no-route lines, and a Temurin version.
