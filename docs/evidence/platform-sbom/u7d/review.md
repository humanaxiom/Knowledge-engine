# platform-sbom U7d review (reviewer, 2026-10-26)

Scope: `git diff HEAD` (86f7831 = U7c) of scripts/, docker/source-policy.json and tests/.
Checked against design-notes "U7d precision", "P2 amended" and "security design review
adopted" (l.2107-2490). docker/sources.lock.json and the u7d lock-run files were not
touched; lock-run-0 was read only.

Verdict: **CHANGES REQUESTED** (B1, B2).

Evidence:
- `u7d/reviewer-controls.txt`: `u7d_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7d): 70 rows, 64 must-fail, 6 must-pass, 0 unexpected.
- `u7d/reviewer-probes.txt`, from `u7d/reviewer-probes/probe_u7d.py` and
  `probe_u7d_timeout.py` (loopback only).
- sources_resolve.py, sbom_check.py and source-policy.json are byte-identical to the
  `u7d/target-*` files. sources_lock.sh is not (B2).

## Blocking

**B1. Real-opener connect, TLS and send timeouts are neither retried nor reported as
timeouts** (sources_resolve.py `_default_opener` l.184-212 and `_transport` l.245-248).
- urllib.request wraps an OSError raised while connecting or sending, a timeout
  included, in `urllib.error.URLError` with `.reason` set to the TimeoutError.
- `_transport` classifies only a bare TimeoutError or socket.timeout as `_Retryable`, so
  these become a plain ResolveError: `<host>: URLError: <url>`.
- Only a timeout in getresponse() or in the body read arrives bare and is retried.
- Input (loopback, `probe_u7d_timeout.py`): a local listener that accepts and never
  answers the TLS handshake, with `_default_opener(url, 2)`. It raises URLError (reason
  TimeoutError), and `_transport` returns a non-retryable ResolveError.
- This is the transient failure Q72 and A72 exist for. R2 says "TimeoutError or
  socket.timeout, raised by OPENER". It fails closed, but the ruled retry never happens
  for it, and the line is not the item 4 text `timeout after <n> s`.
- The unit rows cannot see it: the fake opener raises a bare TimeoutError, and the real
  opener is `pragma: no cover`.
- Fix: in `_default_opener`, after the HTTPError branch (HTTPError is a URLError),
  catch a URLError whose reason is a TimeoutError and raise the reason. Or let
  `_transport` treat that shape as a timeout. Add a row with a fake OPENER that raises
  `URLError(TimeoutError())`, which must be retried with waits [10, 30, 60] and give the
  timeout line. A URLError whose reason is an SSL error or ConnectionRefusedError must
  stay non-retried.

**B2. An unrecorded, untested production change to sources_lock.sh** (l.105: the
`docker save -o` path now goes through `hostpath`).
- The working tree differs from `u7d/target-sources_lock.sh`, which the developer
  reported as copied. The change follows `u7d/lock-run-0-failed-docker-save.txt`:
  docker save failed on Git Bash, where MSYS_NO_PATHCONV=1 passes a POSIX path to the
  Windows docker CLI.
- The fix looks right; every other host path in the script already goes through
  `hostpath`. But it is production code with no failing test first (the CLAUDE.md TDD
  gate), it is absent from the developer handoff section, and no fake-docker row pins
  it. On Linux `hostpath` is the identity, so every test passes either way.
- Fix: record it in the handoff. Have the tester add a row that shims `cygpath` on
  PATH, so `hostpath` maps, and asserts that the fake docker `save -o` argument is the
  `cygpath -m` form. Show the row RED against the target and GREEN against the working
  tree, then re-run controls.

## Nits (non-blocking)
- **N1. The pgdg `suite` is checked for shape only, not bound to the image.** P5 says
  the suite is a full match of `[a-z]+-pgdg-archive`, and that is what the code checks.
  Input: the fixture lock with the `pgdg:postgresql-common@293.pgdg12+1` entry given
  suite `trixie-pgdg-archive` (or `evil-pgdg-archive`), and its `.dsc` `from` changed to
  match, passes `lock_problems`, although the postgres packages are `distro=debian-12`
  (bookworm).
  - The pool URLs and sha256 are what U8 uses, so nothing wrong is shipped.
  - But `suite` names the InRelease that security checks with gpgv at S8, and it is the
    provenance in `from`. Binding it in `lock_problems` to the suite that
    `lock_needs_doc` derives (the table on the distro major) is a few lines. An architect
    call (P5 amendment).
- **N2. sources_lock.sh hard-codes the U7d evidence folder** as the InRelease
  destination (l.170-177).
  - Every later run (U12 arm64, re-locks) will write into the U7d evidence folder,
    which ties an operator script to a plan-item path.
  - The copy runs after the lock is moved into place. If it fails, `set -e` exits 1
    with no FAIL line and the lock already written. That breaks the contract "1: a
    failure, the lock unchanged".
  - Suggest: copy the InRelease next to the lock (or to an evidence-dir argument) before
    the move, or print its path for the developer to copy. Either way, fail before the
    write, never after.
- **N3.** Sources stanzas go through `parse_deb822` one blank-line chunk at a time, so a
  "line N is not a field or continuation" message counts lines from the stanza, not the
  file. Cosmetic.
- **N4.** A parse failure in any stanza of the full 5 MB PGDG index fails the route (the
  whole index is parsed, not only the wanted stanzas). That fails closed and matches
  P2. Noted for the real run: one malformed foreign stanza blocks pgdg.

## Conformant
- **The retry state machine (R1-R6, security R-2 to R-5).**
  - `_attempts` wraps each logical request: the first URL, its redirects and its body
    read, through `stream`, `text`, `capped`, `_json` and `pgdg_index`. Each attempt
    calls `_fetch_once` afresh, with fresh hashers, size, buffers and per-file deadline.
    No production caller reads a body outside `_attempts`; the bare `fetch()` is unused.
  - `fetch` defaults to retries=0. `resolve()` sets the active retries to 3 and resets
    them in `finally`.
  - Only `_Retryable` is retried: a final 5xx at any hop, or a timeout from OPENER or the
    body. Everything else is a plain ResolveError raised at once: 4xx including 418 and
    429, refusals, more than 5 redirects, other OSError, HTTPException, the cap, the
    deadline, and hash, size or parse failures.
  - Waits are 10, 30 and 60 s through `SLEEP`, and the retry line omits the query. After
    the last attempt, the final item 4 line follows.
  - The run budget of 20 is checked before the increment, so the 21st retry fails. The
    run deadline of 10800 s is checked before every attempt, every OPENER call, every
    retry wait (with the wait ahead) and every snapshot pause.
  - `SNAPSHOT_PAUSE` applies before every snapshot attempt, retries included.
- **The shared deb822 parser.** `_paragraphs` is used by:
  - `parse_dsc` (armour stripped, one paragraph, duplicates refused across paragraphs);
  - the Sources stanzas (duplicates refused per stanza only);
  - the InRelease `SHA256` field, read through `parse_dsc`.

  All three apply CRLF folding, an LF-only split, the control-character set, a
  case-blind duplicate check, a non-field line failing with its line number (R1-N2), and
  a first entry on the field line.
- **pgdg route (P1-P6, P2 amended).**
  - lock-needs takes the suite from the distro major (12 bookworm, 13 trixie); unknown or
    mixed majors fail.
  - InRelease is fetched (1 MiB) and its armour stripped. Exactly one `SHA256` entry for
    `main/source/Sources` is required. The raw bytes go to `/out/pgdg-<suite>.InRelease`
    through a temp file.
  - Sources is uncompressed, under a 64 MiB cap, aborted past the Release size, and
    checked for exact size and sha256 before any stanza is used. One fetch per suite.
  - Stanza matching: exactly one Package/Version match; Directory by the pool rule (lib
    plus one letter, else the first letter); the `.dsc` must be listed.
  - The `.dsc` is fetched (1 MiB), its sha256 checked against the stanza, then parsed.
    Source/Version, Checksums-Sha256 against Files, and the Sources-versus-`.dsc`
    cross-check are applied. Other files are recorded, not fetched.
- **Lock rules P5, exact as ruled.**
  - The fifth key `suite`.
  - One `.dsc` named for the key, plus at least one other file.
  - Every file sha256, with the two `from` texts.
  - The url exactly `/pub/repos/apt/pool/main/<p>/<src>/<name>`, with no `%`.
  - `KIND_HOSTS` pgdg is the one host, and the policy has ten hosts.
- **Carried rows.** R1-N1 holds decoded `<P>` middle segments to the lock name rule;
  R1-N2 refuses a non-field line; I-5 uses a synthetic nonce.
- **PS-1.2.** No host URL literal is added.
- **Tests.**
  - Retry: constants and the default 0, retried statuses, lines and waits, the budget,
    head and mid-body timeouts, a 5xx at a hop restarting from the first URL, query
    omission, the never-retried list, the run budget and deadline, the pause on retries.
  - pgdg: entries, pool rule, InRelease write, failures, caps, a malformed route.
  - lock-needs suites, 182-key coverage, the lock P5 good and bad entries, and the
    static row for the InRelease copy.
  - Controls reproduce (70 rows, 0 unexpected).
- **Observability.** A maintainer tool; no spans needed.
