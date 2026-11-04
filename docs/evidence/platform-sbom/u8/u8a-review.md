# U8a review (reviewer, 2026-10-28, R4)

Scope: `git diff 0630586 -- scripts/ tests/` plus the untracked `scripts/sources_fetch.py` (268 lines) and
`tests/test_sources_fetch.py` (1150 lines). Read against design-notes "N4 amendment, U8" (items 1, 2, 4, 5, 6,
11, 12, orchestrator rulings) and PSC-23 "U8 precision" U8-2..U8-6.

**Verdict: CHANGES REQUESTED** (one blocking finding, B-1; the nits are optional but cheap to fold in).

## How it was checked
- Read the full diff of `sbom_check.py` and `sources_resolve.py`, the whole of `sources_fetch.py` and the test file.
- Controls: the five control files sha256 match `u8/u8a-controls.txt`; `git diff 0630586 -- tests/` is empty
  (no existing test edited).
- Sanity run on the host (NOT a gate): `uv run --locked python -m unittest tests.test_sources_fetch` -> Ran 30, OK.
- Mutation probes on a scratch copy of `scripts/` and `tests/` (the repo was not touched); one mutation at a time,
  the module re-run:

| Probe | Mutation | Result |
|---|---|---|
| M1 | drop the Checksums-Sha1 name rule in `dsc_listing` | caught (1 fail) |
| M2 | `_safe` stops redacting queries | caught (3) |
| M3 | `download` cap `>` -> `>=` | caught (35) |
| M4 | `_name_check` returns at once | caught (12) |
| M7 | run deadline +1 s | caught (2) |
| M9 | upstream digest check removed | caught (2) |
| M11 | `.part` never unlinked | caught (16) |
| M13 | dedup (`held`) removed | caught (1) |
| M14 | `_entry_stage` returns `{}` instead of None for non-object components | caught by `test_sources_lock` (1) |
| M5 | `write failed: <class>` text changed | **not caught** (B-1) |
| M6 | the 1 MiB refusal in `_text` removed | not caught (N-2) |
| M10 | `_text` decodes latin-1 (UTF-8 refusal gone) | not caught (N-2) |
| M12 | `O_EXCL` -> `O_TRUNC` on the `.part` | not caught (B-1 row (a) bites it) |
| M8 | `fsync` removed | not caught (accepted: no hook; not testable without patching os) |
| M15 | `fetch_plan` treats any non-"full" set as sample | not caught (N-4) |

## 1. Design conformance (item by item)
- Item 1 pins: `F.main`, `F.R`/`F.S` loaded by path (`_sibling`, spec_from_file_location), `R.OPENER` the one hook,
  `CLOCK = time.monotonic`, `RUN_DEADLINE = {"sample": 300, "full": 10800}`, `DISK_FREE(out)`: all present.
  `download(url, allow, fh, limit, algs, hops)`: exact signature, one `_fetch_once`, no `_attempts`, no retries
  parameter; the cap is checked before a chunk is hashed or written (sources_resolve.py:358-376). `dsc_listing`
  matches the design text, including "Checksums-Sha1 if present agrees in names". `lock_entry_problems`,
  `fetch_plan` (no `plan` CLI): as designed. OK.
- Item 4 order: lock rules (zero requests) -> plan -> disk (distinct sha256 bytes) -> per file: deadline, O_EXCL
  `.part`, one download, size, sha256, upstream digest, fsync, `os.replace` -> per entry name checks -> record
  last via `.fetch.json.part` + replace. OK (fsync before the checks instead of after is harmless).
- Item 2 lines: `ok`/`held`/`fetched` on stdout, FAIL on stderr, `<host>: <name>: <why>` for stage fetch, first
  20 lock problems on stderr. OK except the write-error form (B-1).
- Item 6: flat `<sha256>`, `fetch.json` canonical (`S.lock_text`), `lock_sha256` of the text as read
  (`newline=""`), written last. OK.
- Item 11 / PS-1.2: no `https://`, host, `environ`/`getenv` literal (test-enforced); stdlib only; `-I`-safe
  sibling loading. Q61: no retry by construction (`download` has no path to `_attempts`; the test also patches
  `_ACTIVE_RETRIES=[3]`, so a `stream()`-based client would fail it). OK.
- No spans: a build-time tool, not an agent step (design head, N3/ADR). Not an observability finding.

## 2. The resolved ambiguities (tester R2 and developer GREEN)
| # | Resolution | Ruling |
|---|---|---|
| a | Strip one leading `<host>: ` or `<name>: ` from the resolver text | Fine. The literal composition would print the host twice; a differing hop host is kept, which is the useful case. No amendment; a one-line precision in the design at U8b is optional. |
| b | Redact every `?...`, also the apk first-request `ref=<commit>` | Fine. Stricter than U8-2 (redirect queries only); the commit is in the lock and the path still names the origin. No amendment. |
| c | Cap text `<last hop host>: more than <limit> bytes: <lock url>` | Fine; never prints a signed hop URL. |
| d | `dsc_listing` also refuses a Checksums-Sha1 name set that differs | Not a deviation: design item 1 states it verbatim. It tightens `dsc_files` for that corner case only (U7c rows unchanged); the pgdg resolver route keeps its own copy without it (N-10). Message unpinned (N-8). |
| e | `fetched <n> files, <bytes>` counts requested files (held excluded) | Fine; equals the bytes on disk. |
| f | Name checks after the last file of an entry; earlier verified files stay on a failure | Fine: design items 2 and 6 make the U8b trap the "nothing remains" guarantee (U8-6). **Forward to the U8b tester:** the trap row must cover a client exit 1 that leaves verified `<sha256>` files (n-th file fault and a name-check failure), not only a first-file fault. |
| g | ok/held/fetched on stdout, FAIL on either stream | Fine. |
None needs the architect.

## 3. lock_problems refactor (behaviour-preserving: yes)
Before/after read side by side (0630586 sbom_check.py:1568-1615 vs now 1568-1630). Early returns keep their order
and text: arch -> not text -> not JSON -> canonical (accumulated) -> top-level keys -> format (accumulated) ->
components not an object -> every `_entry_problems`; `_entry_stage` returns `(p, None)` exactly where the old
function returned, and `lock_problems` returns `p` unchanged on None. `today` is resolved only in `_entry_stage`
and passed through; the one reorder (`today or now()` after the arch check) is pure. `hosts` and `comps` are the
same objects. Controls: `test_sources_lock.py` (49) and `test_sources_lock_committed.py` (7) unchanged by sha256
and green; M14 shows they bite on the None/`{}` boundary of the split.
`test_lock_entry_problems_is_lock_problems_without_coverage` compares both functions on six texts.

## 4. Findings

### Blocking
- **B-1 The U8-4 write-error line is untested, and one path misses it.** scripts/sources_fetch.py:117 opens the
  `.part` with `O_CREAT|O_EXCL` *outside* the `try` (:118-138), so an open failure (a pre-existing `.part`,
  EACCES, ENOSPC/inode exhaustion on create) reaches the catch-all in `main` (:261) and prints
  `bundle_fetch: FAIL (stage fetch: FileExistsError: [Errno 17] File exists: <out>/.<sha>.part; no retry)`:
  no host, no file name, not the U8-4 / design item 2 form `<host>: <file name>: write failed: <OSError class>`.
  The in-`try` path (:134-135) has the right form but no test: M5 (changing its text) and M12 (dropping O_EXCL)
  leave all 30 tests green. U8-4 lists "a write error (disk full included)" as an acceptance case.
  Fix: catch the `os.open` OSError on its own and raise `_fetch_fail(url, name, f"write failed: {type(exc).__name__}")`
  **without** unlinking (that `.part` was not created by this run; keep that property). Tests, with no new patch:
  (a) a pre-existing `<out>/.<sha256>.part` -> the exact U8-4 line, the foreign `.part` byte-identical afterwards,
  no request for that file; (b) `<out>/<sha256>` pre-created as a non-empty directory, so `os.replace` fails ->
  the exact line with `write failed: [A-Za-z]+Error` (the class differs by OS), no `.part` left, no `fetch.json`.

### Nits
- **N-1** scripts/sources_resolve.py:699: a backslash continuation in U7c-reviewed code was collapsed into one
  146-char line with 13 embedded spaces (`... md5s) or             len(...)`). Same behaviour; restore the
  two-line form (as at :1095).
- **N-2** scripts/sources_fetch.py:141-150: the `over 1 MiB, not checked` (design item 5) and `not UTF-8 text`
  refusals in `_text` have no row (M6, M10). One row each: a `.dsc` of `R.TEXT_LIMIT + 1` bytes with true hashes;
  a `.dsc` with one non-UTF-8 byte.
- **N-3** scripts/sources_fetch.py:187-199: `_write_record` opens `.fetch.json.part` with O_EXCL *inside* the
  `try`, so a pre-existing one is unlinked by the `finally`: the opposite of the `_place` handling. Align with B-1.
- **N-4** scripts/sbom_check.py:1677-1684: `fetch_plan` treats any `which` other than `"sample"` as full; raise
  ValueError on an unknown set (argparse guards the client today; the function is the documented interface).
- **N-5** scripts/sources_fetch.py has CRLF line endings in the working tree (siblings are LF). autocrlf
  normalises the commit to LF; still write it LF, since the U8b container mounts the worktree.
- **N-6** scripts/sources_fetch.py:15: "no read of the process settings" is phrasing bent around the `environ`
  substring ban in the test (which also forbids the word "environment"). Cosmetic; either is acceptable.
- **N-7** tests/test_sources_fetch.py:70 `NEO_FROM` duplicates tests/test_sources_lock.py:58 `FROM_NEO4J`; import
  it (the module already imports `canon`, `policy` from there) so a re-fetch record cannot drift between them.
- **N-8** tests/test_sources_fetch.py:1049-1051: the Sha1 case expects `want=None` (any ResolveError); pin
  `<dsc>: Checksums-Sha1 and Checksums-Sha256 list different files`.
- **N-9** the `bundle_fetch: lock problem: ...` stderr lines (first 20) are not asserted; one assertion in the
  stage-lock row would cover them.
- **N-10** (follow-up, not U8a) scripts/sources_resolve.py:1083-1097: the pgdg route re-implements the
  `dsc_listing` checks (without the Sha1 rule). Calling `dsc_listing` there is a resolver change outside the U8a
  scope (design: resolve routes unchanged); note it for a later unit.

## 5. Test adequacy (item 12)
Rows 1-10 are all present: checks before use (size, sha256, sha1, sha512, a junk `.dsc` never parsed), byte cap
(client and `download`, with an exact-limit control), hosts (4 hop refusals with zero follow-up requests, 5
stage-lock cases with zero requests), no retry (503, timeout, mid-body timeout; with `_ACTIVE_RETRIES=[3]`), dsc
(deb + pgdg, 4 differences + parser text) and APKBUILD name checks (3 differences + a control with a GitLab file
outside sha512sums), n-th file fault (middle, last), plan (sample/full x amd64/arm64, other arch never, 2 shared
sha256 held), record (canonical, last via `record_seen`, mode 0644 on POSIX), redirect query never printed (5
cases), run deadline via `CLOCK`, disk via `DISK_FREE` (one short, exact), CLI exit 2 (7 cases), one-line
exceptions (3), helpers. Patches beyond the module hooks are safety nets or probes (`time.sleep`,
`socket.create_connection`, `_attempts` to prove it is never called, `S.fetch_plan` to inject an error):
acceptable. No test reads `docs/evidence/**` (NEO_FROM is a string value). No counts in test names. Nothing
weaker: no existing test edited. Gaps: B-1, N-2, N-8, N-9.

## 6. Gate note
Design item 14 R3 schedules `u8/u8a-developer-verify-full.txt` (scripts/ touched); only the fast run exists so
far. It is required before the gate, after the B-1 rework.

---

# U8a re-review, rework round 1 (reviewer, 2026-10-28)

**Verdict: APPROVED** (code and tests). The gate still needs a green `scripts/verify.sh full` on this tree: the
developer run is blocked by Docker address-pool exhaustion (`u8/u8a-developer-verify-full.txt`, no test ran), so
the orchestrator run is the one that counts.

Read: `git diff 0630586 -- scripts/ tests/` again, the whole of `scripts/sources_fetch.py` (now 279 lines, LF)
and every new or changed row in `tests/test_sources_fetch.py` (1556 lines). Evidence:
`u8/u8a-r1-green-verify-fast.txt` (Ran 1155, OK, skipped=8). Controls: the five control files still match
`u8/u8a-controls.txt` by sha256; `git diff 0630586 -- tests/` is empty. Host sanity run of the module: OK.

## Findings from the first review
| Item | Status |
|---|---|
| B-1 | Closed. `_place` (sources_fetch.py:117-120) and `_write_record` (:191-194) catch the `os.open` OSError on its own, raise the U8-4 form (`<host>: <name>: write failed: <Class>` / `fetch.json: write failed: <Class>`) and never reach the `finally` that unlinks, so a foreign `.part` is untouched. Rows: foreign `.part`, `<sha256>` taken by a non-empty dir (rename), foreign `.fetch.json.part`. |
| N-1 | Closed: two-line form restored (sources_resolve.py:699-700). |
| N-2 | Closed: `test_source_fetch_reads_only_small_utf8_text` (limit+1, a 0xff byte, exact-limit control). |
| N-3 | Closed with B-1. |
| N-4 | Closed: `fetch_plan` raises ValueError (sbom_check.py:1711-1712); row with 5 bad sets. |
| N-5 | Closed: LF. |
| N-6 | Reworded ("reads nothing from the process settings"); still shaped by the `environ` ban; accepted, cosmetic. |
| N-7 | Closed: `FROM_NEO4J` imported from test_sources_lock. |
| N-8 | Closed: the Sha1 message is pinned (refusals row and the new Sha1 row). |
| N-9 | Closed: first-20 row, each line through `_safe`, a query in a problem never printed. |
| N-10 | Still a follow-up (pgdg route copy of the dsc checks); not U8a. |

## Security items
- **M-1** (empty plan): `stage lock: the lock lists no entry for <arch>` before the disk stage (sources_fetch.py:223-224);
  4 cases, zero requests, no record. Fine.
- **M-2** (`_shared_sha256_problems`, sbom_check.py:1599-1625): one sha256 = one size (reference: first entry in
  key order) and one upstream value per alg (reference: first entry holding it under that alg). Pure, skips
  malformed rows (left to `_entry_problems`), cleaned text, runs after the per-entry rules so it also guards
  `lock_problems` (lock-check, the committed-lock test, U9 index). The developer key0 choice for digests is the
  only one that makes sense (an entry under another alg has no value to compare); the pinned text reads
  consistently. The committed lock passes. The held line now prints the verified size (P7 below is an equivalent
  mutation under the rule).
- **L-1** (redaction at the source only for the refused-Location text): **acceptable; no U7c test change needed.**
  Every other resolver text that quotes a URL quotes one that already passed `PRINTABLE` (`[\x21-\x7e]+`: no
  space, tab, NBSP or any non-ASCII) or the lock URL, which the lock rules bind; `_clean` escapes control bytes to
  `\xNN`. So `_safe`'s `\?\S*` always reaches the end of such a query, and the only URL that can carry whitespace
  (a Location refused as not printable) is now redacted by `_retry_url` before it is quoted. The `_safe` negative
  lookahead for `?<query omitted>` cannot be abused: that marker contains a space, so no URL holding it gets past
  `PRINTABLE`. The cap text now uses `_retry_url` for the lock URL as well (stricter; `_safe` already covered it).
  The lock tool output gains the same redaction for that one text, which is harmless.
- **L-3**: `--out` holding `fetch.json` (lexists, so a link too) is `stage lock` before the lock is read; row pins
  the old record untouched. Fine; the non-empty `--out` refusal stays a U8b script row (carried).
- **L-4**: `test_default_opener_is_tls12_without_proxy_or_redirects` (no proxy read or installed, own redirect
  handler returning None, TLS floor >= 1.2 with CERT_REQUIRED and hostname check, User-Agent, timeout) and
  `test_source_fetch_unpacks_builds_and_runs_nothing` (AST: no archive/process/exec modules or calls, shutil only
  `disk_usage`, only the two siblings loaded). Fine.
- **L-5**: the Sha1 rule now applies whenever the field is present (an empty one included) and compares
  (name, size). It tightens `dsc_files` for the resolver too; the U7c rows stay green.

## Mutation probes (scratch copy, one at a time; repo untouched)
Caught: open-failure text (1), rename-failure text (1), `.part` O_EXCL->O_TRUNC (1), record O_EXCL->O_TRUNC (1),
unlinking a foreign `.part` (1) and a foreign `.fetch.json.part` (1), no empty-plan check (4), no fetch.json
check (1), old `_safe` regex (3), record write text (1), no 1 MiB limit (1), latin-1 decode (1), M-2 rule off (11),
M-2 not per alg (1), M-2 size check off (7), L-1 source redaction reverted (4), L-5 only when non-empty (3),
L-5 names only (1), N-4 ValueError off (5), name check off (15), dedup off (1), `ProxyHandler({})` dropped (1).
Not caught, both equivalent mutants: P7 the held line printing the lock size (equal under M-2) and P19 the cap
text quoting the lock URL with `_clean` (the client `_safe` drops the apk query anyway).

## New nits (none blocking)
- **R1-N1** The M-2 lock rule changes `lock_problems` (and so `lock-check`, `sources_lock.sh` and U9 `index`), but
  it is recorded only in the orchestrator log line and the test module doc. The architect/analyst should add one
  line to the N4 amendment U8 (or the N5 lock rules) and PSC-23 U8-3 at R5. The `LockEntryProblemsTest`
  docstring "(a pure refactor ...)" is now slightly stale: the split is still pure, the rule is new in both.
- **R1-N2** A file held for an entry whose upstream alg differs from the first holder (deb sha256 vs apk sha512 on
  the same bytes) never has that second digest computed on the bytes. The sha256 match makes the bytes identical,
  so this is defence in depth only; security may want the held path to hash the stored file for an alg not yet
  verified. Not a review blocker.
