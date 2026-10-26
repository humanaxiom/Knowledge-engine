# platform-sbom U7b review (reviewer, 2026-10-25)

Scope: `git diff HEAD` (9b1754f = U7a) of scripts/sbom_check.py (`lock-needs`,
`tar_file_text`, `lock_needs_doc`) and tests/test_stack_compose.py, plus the new
scripts/sources_resolve.py, scripts/sources_lock.sh, docker-compose.sources.yml and
tests/test_sources_resolve.py. Checked against design-notes "N5 amendment, U7" items 1,
3, 4 and 5, "Resolution endpoints", and "U7b interface pins" (l.1384-1442).

Verdict: **CHANGES REQUESTED** (B1, B2).

Evidence:
- `u7b/reviewer-controls.txt`: `u7b_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7b): 62 rows, 58 must-fail, 4 must-pass, 0 unexpected (reproduced).
- `u7b/reviewer-probes.txt`, from `u7b/reviewer-probes/probe_u7b.py`. It uses a fake
  OPENER patched as the tests do; temp paths are redacted.
- On the Windows host, `python -I -m unittest tests.test_sources_resolve` fails 6
  SourcesLockScriptRunTest subtests, because `bash` resolves to WSL there
  ("Catastrophic failure"). This is a host artifact: verify (Linux gates) passes, 988 OK
  (`u7b/green-verify-fast.txt`).

## Blocking

**B1. Network errors during the body, and non-OSError opener errors, escape as
tracebacks; there is no overall byte deadline** (scripts/sources_resolve.py `fetch`
l.110-142, `stream` l.145-155, `text` l.158-168).
- `fetch` catches `TimeoutError`/`socket.timeout`/`OSError` only around the OPENER
  call. The body is iterated in `stream` and `text` with no handler. `main` catches only
  `ResolveError`.
- Probes (maven route, fake OPENER; each run writes nothing, but none prints the item 4
  why-text or the pin 4 line `sources_lock: FAIL (resolve: <key>: ...; the lock is
  unchanged)`):
  - a body that raises `TimeoutError` after the first chunk escapes as an uncaught
    TimeoutError, where item 4 wants `<host>: timeout after <n> s: <url>`;
  - `http.client.IncompleteRead` and `ConnectionResetError` mid-body are uncaught;
  - OPENER raising `http.client.InvalidURL` (a ValueError) or `BadStatusLine` (an
    HTTPException, not an OSError) is uncaught.
- Item 3.5 also says "a per-request timeout and an overall byte deadline apply". Only
  the per-read socket timeout exists. A server that drips one byte per minute keeps the
  run alive indefinitely. A body of any size is streamed: the probe streamed 1.22 GiB
  with no cap. The U7a lock refuses more than 4 GiB, but only after the full download.
- Fix:
  - wrap the body iteration in `stream`/`text` and map each error to the item 4 texts
    as a ResolveError;
  - catch OSError, ValueError and http.client.HTTPException around OPENER;
  - add a wall-clock deadline per file and a byte cap equal to the U7a cap (4 GiB),
    each a named ResolveError;
  - add rows: a mid-body timeout, a mid-body IncompleteRead, InvalidURL, a deadline
    exceeded, and a cap exceeded, each giving the exact FAIL line and no lock.new.json.

**B2. The "only neo4j misses, so write and exit 3" test in sources_lock.sh reads only
the first 20 lines of lock-check output** (scripts/sources_lock.sh l.139-148; lock-check
prints `problems[:20]`).
- Item 3.6: "If the only problems are missing neo4j keys, it writes the file, prints
  the TOFU candidate and exits 3. Any other problem means exit 1, and the committed
  file is untouched."
- With no neo4j entry, 73 neo4j-miss lines sort before every `pgdg:`, `pypi:` and
  `temurin:` miss and every stale-entry line. So the 20 lines the script greps can all be
  neo4j while other problems exist.
- Input: lock-check on the fixture lock without `neo4j:neo4j@5.26.32`, `pypi:pandas@2.3.3`
  and the three `pgdg:` keys gives 79 problems, 6 of them not neo4j. The first 20 are all
  neo4j misses (`reviewer-probes.txt`, last block).
- So the script writes `docker/sources.lock.json` and exits 3. This is exactly the first
  real U7c run: deb and apk resolved, pgdg skipped until Q71, neo4j TOFU pending. In U7b
  it is masked only because `apk:`/`deb:` misses sort first.
- The U7d committed-lock test would catch it later. But the write gate of the script is
  defeated, and an unreviewed partial lock lands in the working tree.
- Fix: decide in Python, not by grepping truncated text. For example `lock-check
  --pending-neo4j` (or `--all`, which prints every problem) returns 3 exactly when every
  problem is a neo4j miss, and the script keys on that exit code. Add a row with the
  input above, where the script must exit 1 with the lock untouched.

## Nits (non-blocking)
- **N1. Hop rules accept a port or userinfo on an allowed host.** A redirect to
  `https://repo1.maven.org:8443/x.jar` or `https://user:pw@repo1.maven.org/x.jar` is
  followed: `urlsplit(...).hostname` drops both. The U7a lock refuses both. Apply the
  same per-hop rules (printable 0x21-0x7e, no userinfo, no port, lower-case `https://`)
  before calling OPENER. (A tab in a Location is already refused, because the host
  string then differs.)
- **N2. jq is required with no check.** sources_lock.sh l.53 runs `jq -er`, and this Git
  Bash host has no jq. The failure reads "images: service X has no image", which
  misleads. Check `command -v jq` up front with a clear message, or document it as a
  maintainer prerequisite. bundle.sh treats jq as optional.
- **N3.** The temp file `docker/.sources.lock.json.XXXXXXXX` is not in the EXIT trap. If
  `cp` or `mv` fails it is left in `docker/`. Add it to `cleanup`.
- **N4.** The script does not check that it found six images (it accepts any count above
  0), and `--tar ke-neo4j=/tars/ke-neo4j.tar` is hard-coded. A renamed or missing
  ke-neo4j surfaces only as a lock-needs failure. A count check with the expected names
  would fail earlier with a clearer message.
- **N5.** `tar_file_text` ignores whiteouts: a top-layer `.wh.release` leaves the lower
  copy winning. The SBOM cross-check in the resolver catches a mismatch, so it fails
  closed; noted.
- **N6.** `main` lets an OSError writing `/out` and a non-dict needs entry
  (AttributeError in `resolve`) escape as tracebacks. Fold these into the B1 handler.

## Conformant
- **Hops.**
  - At most 5 redirects; each hop must be `https` with its host in `hosts` plus
    `pypi.org` (exact, lower-cased).
  - Relative Locations are joined, and `//evil` is refused.
  - The messages for non-https, an unlisted host, more than 5 redirects, non-2xx and an
    OPENER timeout match item 4.
  - There is no GitHub API call, and the endpoints are exactly the "Resolution
    endpoints" list for the four kinds.
- **Routes.**
  - temurin: the tag comes from the release file in the saved tar, cross-checked against
    the SBOM and the key; the URL is the exact U7a round-2 form (`quote` gives `%2B`);
    the sidecar parser takes one line.
  - maven: a 40-hex `.sha1`, and sha1 and sha256 are both streamed.
  - pypi: uv.lock gives the url, hash and size with no call; phoenix uses one sdist from
    pypi.org JSON on files.pythonhosted.org and streams it to compare.
  - neo4j: streamed once, the candidate printed with its hop host, never written, exit 3.
  - Every produced entry passes the U7a `lock_problems` (`lock_ok` in the tests).
- **Merge.**
  - `manual` is never rewritten or removed.
  - An existing generated entry for the arch is skipped unless `--refresh`.
  - Arches are unioned on rewrite.
  - Unneeded generated entries lose the arch, and are deleted when none is left.
  - deb/apk/pgdg are skipped and named on stderr (pin 3).
- **Writes.** The resolver writes only `out/lock.new.json`, through a temp file and
  `os.replace` inside `/out`. A failure writes nothing.
- **lock-needs.**
  - It reads `/opt/java/openjdk/release` from the docker save tar (top layer wins,
    nothing extracted, 1 MiB cap).
  - `route` holds the item 3.3 inputs.
  - It prints one FAIL line on an exception and the first 20 problems otherwise.
- **Compose.**
  - sources-resolve has: `pull_policy: never`, the caller uid:gid, a read-only root,
    tmpfs `/tmp`, `cap_drop: ALL` and `no-new-privileges`.
  - Its mounts: the script, the policy, uv.lock and `/in` read-only; `/out` the only
    writable one.
  - Its environment is the literal PYTHONDONTWRITEBYTECODE. No ports, no socket, and the
    default bridge of the project is its only network.
  - It matches the hardening of the sbom service except for the network, which this
    service needs. The test_stack_compose exemption names only this service.
- **Script.**
  - Strict mode, quoted arrays, `cd` to the repo, `hostpath`/MSYS_NO_PATHCONV for Git
    Bash.
  - mktemp work dir with the 7 GiB floor, and an EXIT trap that runs `down --volumes` on
    the random project.
  - A pinned sbom with no network, and gates runs with `--network none --read-only
    --cap-drop ALL --pull never`.
  - No `-e`, no `--env-file` value and no KE_* reach a container (KE_SOURCES_* is
    compose interpolation only).
  - lock-check runs before a temp file is moved in `docker/`, then `git diff --stat`;
    exit codes 1, 2 and 3.
  - Never called by verify or CI (tested).
- **PS-1.2.** No scheme-and-host URL literal (constants plus f-strings); the verify
  scanner passes.
- **Tests and controls.** 22 methods cover:
  - hop rules, the parsers, the four routes, the neo4j exit 3, merge and the CLI;
  - lock-needs on the fixtures and a saved tar;
  - compose hardening, with a 14-bad-shape oracle;
  - the script statically and with fake docker (a missing image, bad arguments, the
    floor).

  The 37 mutants reproduce. Not covered: mid-body errors and the deadline (B1), the
  truncation case (B2), and the happy path of the script (the tester flagged it; the U7d
  real run).
- **Observability.** A maintainer build tool, not an agent step (N3); no spans needed.
