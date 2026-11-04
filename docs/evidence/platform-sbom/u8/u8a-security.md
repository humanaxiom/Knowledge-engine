# U8a security audit: the source fetch client (2026-10-28, security)

Scope: `git diff 0630586 -- scripts/ tests/` plus the new `scripts/sources_fetch.py` and
`tests/test_sources_fetch.py` (U8a, uncommitted tree). Read: handoff U8 sections, design-notes
"N4 amendment, U8" items 1-6, 11, 12; requirements PSC-23 U8-2..U8-6; Q61.
Method: code read; fail-open probes through `F.R.OPENER`, `CLOCK`, `DISK_FREE` with `python -I`
and a patched `socket.create_connection` (no real network): `u8a-security-probes.txt` (output and
scripts, redacted). `python -m unittest tests.test_sources_fetch`: 30 OK (information only, not a gate).
Secret-pattern grep over the diff and both new files: one hit, the test's synthetic placeholder
`SECRET = "SECRETSIGNATURE"`. No environment read in the client (`environ`/`getenv` absent).

## Verdict: PASS (no critical or high). 2 medium, 5 low, 2 info.

By the role's rule, medium and low findings do not block a merge. The orchestrator's brief says any
unresolved finding blocks. M-1 and M-2 are cheap (a few lines plus one test row each) and are
recommended for a U8a rework before the commit.

## Findings

**M-1 (medium) An empty plan exits 0 with a "complete" `fetch.json`.** `sources_fetch.py:214-245`
has no non-empty check. The committed lock is amd64-only (183/183 entries `["amd64"]`), so
`--arch arm64` (an ARM model host, where the arch comes from the daemon, A75) prints `fetched 0 files`,
writes `fetch.json` with `components: {}`, and exits 0 for both `sample` and `full`. A lock with
`components: {}` does the same on amd64 (probes P1, P1b, P1c). This is the brief's fail-open class "exit 0
without fetch.json complete". It gives a vacuous green for the U8b `offline_check` sample stage on an ARM
host, and a completion record that U9 matches by set, arch and lock sha256. U9's coverage `index` is the
downstream backstop, which is why this is medium. Fix: a `stage lock` failure "the lock lists no entry
for ARCH" when the plan is empty, before the disk stage. Test row: arm64 on an amd64-only lock gives
exit 1, zero requests and no `fetch.json`.

**M-2 (medium) A held file skips the per-file size and upstream-digest checks.** `sources_fetch.py:230-234`
(and `sizes`, l.217, where the last value wins). When entry B's file shares a sha256 with entry A's, B's
lock `size` and `upstream` are never compared with the bytes. Probe Q2: B's lock and APKBUILD say sha512
`eee...`, the bytes' sha512 is different, and the run exits 0. Probe Q2b: B's lock size is 9999, the bytes
are 300, and the run exits 0. The `held` line prints `size=9999` and `fetch.json` records 9999 for B.
`lock_entry_problems` catches neither, because cross-entry consistency is unchecked. No unverified byte is
kept (sha256 binds the bytes). But U8-5 ("checked against the lock's size and sha256") and design item 4's
per-file upstream digest do not hold on the held path, and the record U9 reads can carry a false size.
The `.dsc` name check catches the deb case (probe P2b). It does not catch apk, which is checked by name
and sha512 only. The committed lock has 0 such conflicts today, so this is latent. Fix (either):
(a) keep, per sha256, the verified size and the sha1/sha256/sha512 digests (hash all three on every
download), and on a held hit check size and `digests[alg] == upstream.value` with the same FAIL texts; or
(b) a pure `lock_entry_problems` rule: one sha256 must carry one size and, per alg, one upstream value
across the lock. Test row: the Q2/Q2b fixtures give exit 1 and no `fetch.json`.

**L-1 (low) Query redaction stops at whitespace.** `_safe` (`sources_fetch.py:78`, the regex
backslash-? then non-space run) is applied to resolver text that can quote a raw refused `Location`
(`sources_resolve.py:325`, "not printable ASCII", where a space or NBSP is the reason it was refused).
Probes P3/P3b print `?<query omitted> BBBBLEAK&x=1`. A listed host has to send a malformed Location,
and GitHub's signed URLs hold no spaces. Fix: redact at the source (the resolver's refused-hop and
transport texts quote URLs through `_retry_url`, which drops everything after `?`), or have `_safe`
drop everything up to the message's own delimiter.

**L-2 (low) A pre-existing `.part` fails in a non-U8-4 form with an absolute path.** `os.open` at
`sources_fetch.py:117` is outside the `try`, so `FileExistsError` reaches the generic handler:
`stage fetch: FileExistsError: [Errno 17] File exists: (abs out path)/.(sha).part` (probe P4). It fails
closed and leaves the foreign file alone, which is correct. In `_write_record` (l.187-199) the `os.open` is
inside the `try`, so the `finally` deletes a pre-existing `.fetch.json.part` it did not create (P4e).
That is harmless, but it breaks "removes its own `.part`". Fix: a `created` flag in both functions; report
`write failed: FileExistsError` in the `host: name:` form, and unlink only what this run created. On
POSIX, O_EXCL also refuses a dangling symlink. A `.part` symlink could not be tested on this Windows host
(P4f).

**L-3 (low) The client neither refuses nor clears an earlier `fetch.json`.** A failed run into a
directory that already holds `fetch.json` leaves it in place (P4d). U8-1 puts the non-empty `--out`
refusal in U8b's `bundle_fetch.sh`, so the client is safe only behind that check. Carry to U8b: a test
row that the service is only reached with an empty or new `--out`. Optional defence in depth: the client
refuses (or unlinks) an existing `fetch.json` before the first request.

**L-4 (low) Item 11 properties with no test row.** (a) TLS >= 1.2, `ProxyHandler({})`, `NoRedirect`
and the User-Agent live in `_default_opener` (`sources_resolve.py:189-218`, `pragma: no cover`). No
test in U8a or `test_sources_resolve.py` pins them, and from U8 on that opener runs in verify and CI.
(b) "nothing unpacked, built or run" has no static row (today the client imports no `tarfile`,
`zipfile` or `subprocess`). (c) O_EXCL on the `.part` (P4) has no row. Fix: static rows. For example,
`inspect.getsource` of `_default_opener` holds `ProxyHandler({})`, `TLSv1_2` and `NoRedirect`; an AST
import allowlist for `sources_fetch.py`; and a pre-existing `.part` row.

**L-5 (low) The new `dsc_listing` Checksums-Sha1 rule passes an empty field and ignores sizes.**
`sources_resolve.py:701` uses `if sha1s and ...`, so an empty `Checksums-Sha1:` field and a Sha1 row
with another size both pass (checked in the audit run). Sha1 is not a trust input on the fetch path: the
lock pins the `.dsc` by sha256 and sha1, and the listing uses Sha256. That is why this is low. Fix:
`"Checksums-Sha1" in fields`, and compare (name, size).

**I-1 (info, reviewer)** `sources_resolve.py:699`: the removed backslash continuation left
`... md5s) or (13 spaces) len(...)` on one line (an edit artefact; same behaviour).
**I-2 (info)** A hop may go to any of the policy's hosts, whatever the kind (probe P5: a maven hop to
files.pythonhosted.org was accepted). This is U8-4 as written ("its host is in hosts"), and sha256 binds
the bytes. A per-kind hop allowlist would narrow egress further (O-2 territory).

## Design item 11 properties
| Property | Verdict | Where / test |
|---|---|---|
| No URL outside the lock | PASS | `fetch_plan` files only; `test_source_fetch_set_is_the_plan` (calls == chains) |
| Hosts only from the policy | PASS | `allow` from the policy `hosts`, l.212; `test_source_fetch_has_no_url_host_or_environment_literal` |
| Only first query is the apk API raw `ref=` | PASS | `sbom_check.py:1257-1259` before any request; lock row "non-apk lock url with a query" |
| Redirects by hand, hop rules, limit 5 | PASS | `_fetch_once`; hops test rows; P5b-P5f |
| TLS >= 1.2, no proxy, `-I` | PASS in code | `sources_resolve.py:197-200`; no test row (L-4a); `-I` is U8b's entrypoint |
| No retry (Q61) | PASS | `download` never calls `_attempts`; `test_download_*`, `test_source_fetch_never_retries` |
| Byte cap = lock size, before hash and write | PASS | `sources_resolve.py:369-371`; both cap rows |
| Nothing unpacked, built or run | PASS in code | only `_text` reads, after verification; no static row (L-4b) |
| No secret, no caller key | PASS (U8a) | no environment read; the service env is U8b |
| No `docs/evidence` read by a test | PASS | the only mention is the lock `from` string literal |
| No URL literal in `sources_fetch.py` | PASS | test row |

## The brief's items
1. Network: PASS. The first URL is the lock URL as written. Every hop passes `_hop_refusal` and `allow`,
   with at most 5 redirects. The opener reads no proxy or environment (`ProxyHandler({})`, `-I`), and its
   TLS floor is 1.2 with default verification. `lock_entry_problems`, the plan and the disk check are pure
   and run before the first `OPENER` call (zero calls on a lock or disk failure, tested). Q61 holds by
   construction: `download` has no `retries`, no `_attempts` and no `SLEEP`.
2. Files: PASS with L-2/L-3. Names on disk come only from the lock's sha256, which the rules require to be
   64 lower-case hex (`sbom_check.py:1283`). Upstream names never reach the filesystem. The `.part` is
   opened O_EXCL with mode 0644, then fsync and `os.replace`. A pre-existing sha-named file is replaced,
   not written through (P4b), and a directory there fails closed (P4c). The `.part` is removed in
   `finally`. The checks run before the rename, and `fetch.json` is written last and never after a failure
   in this run. The client follows `--out` if it is a symlink; U8-1's refusal is U8b's.
3. Parsing: PASS with L-5. The `.dsc` and APKBUILD are read only from the renamed, verified file. The
   lock size caps them at `TEXT_LIMIT`, they are decoded strictly, and the resolver's own parsers read
   them. Nothing is unpacked or run (`test_source_fetch_never_parses_a_dsc_that_failed_its_check`).
4. Output: PASS with L-1. Every FAIL and lock-problem line goes through `_safe`. `ok`/`held` lines print
   grammar-checked keys, `_safe` names and hosts only. The generic handler gives one line and no
   traceback (P7, P7b). Stdout carries the record; stderr carries the FAIL line.
5. Fail-open hunting: found M-1 (vacuous success) and M-2 (held-path checks). No probe kept an
   unverified byte, requested an unlisted host, retried or printed a traceback.
6. Tests: every item 11 property has a test row except L-4 (a) and (b). No test reads `docs/evidence/**`.

## Re-audit, rework round 1 (2026-10-28, security)

Scope: the round 1 delta (`sources_fetch.py`, `sbom_check.py` `_shared_sha256_problems` and `fetch_plan`,
`sources_resolve.py` refused-Location text, `download` cap text, `dsc_listing`). Probes P1-P7, Q2/Q2b were
re-run against the current module, and R1-R5 are new (`u8a-security-probes.txt`, section "Re-audit, rework
round 1"). `python -m unittest tests.test_sources_fetch`: 45 OK (information only). The developer's
`verify.sh full` is still due (blocked on daemon address pools).

**Verdict: PASS.** Every original finding is closed. One new low finding (L-6, a residual of M-2) does not
block.

| Finding | Status | Evidence |
|---|---|---|
| M-1 empty plan | CLOSED | P1/P1b/P1c and R5b (committed lock, arm64): `stage lock: the lock lists no entry for <arch>`, 0 calls, `--out` empty |
| M-2 held checks | CLOSED for size and same-alg digests; L-6 residual | Q2/Q2b, P2/P2b: named `lock problem`, `stage lock`, 0 calls; the held line now prints the verified size; committed lock passes the rule (R5) |
| L-1 redaction | CLOSED; no fail-open remains | P3/P3b: `?<query omitted>` and nothing of the query |
| L-2/N-3 foreign `.part` | CLOSED | P4: `<host>: <name>: write failed: FileExistsError`, the foreign `.part` kept; P4e: the foreign `.fetch.json.part` kept, no record |
| L-3 earlier `fetch.json` | CLOSED in the client | P4d, R3: refused at `stage lock` before the lock is read, 0 calls (`lexists`, so a dangling link is refused too; a link could not be made on this host, R3b) |
| L-4 test rows | CLOSED | the opener row runs `_default_opener` with `OpenerDirector.open` and `getproxies` patched (no socket) and pins TLS >= 1.2, CERT_REQUIRED, no proxy read, `NoRedirect` and the UA; an AST row bans unpack/exec/process modules and names; the foreign-`.part` row covers O_EXCL |
| L-5 Sha1 rule | CLOSED | `"Checksums-Sha1" in fields`, (name, size) compared; rows in `test_dsc_listing_checksums_sha1_rule` |
| I-1 | CLOSED | the continuation is restored at `sources_resolve.py:699-700` |

Why no fail-open remains for L-1: every URL that reaches a FAIL text is in one of two forms. Either it passed
`PRINTABLE` (`\x21-\x7e`, so it has no whitespace and `_safe`'s non-space run covers the whole query): this
holds for hop, transport, status, deadline and non-https texts. Or it goes through `_retry_url`, which
drops everything after `?`: the refused-Location text and `download`'s cap text. The lookahead added to
`_safe` cannot be abused: a query that starts with the marker `<query omitted>` has a space, so `PRINTABLE`
refuses it and the source redacts it (R2, R2c). A look-alike with no space is redacted normally (R2b). A
timeout at the signed hop prints `?<query omitted>` (R2d).

**L-6 (low, new) A held copy under another upstream alg is still unchecked.** `_shared_sha256_problems`
binds one value per (sha256, alg), and its control row allows one sha256 under two algs. The client checks
only the alg of the first fetched copy (`sources_fetch.py:124`, `algs=(alg,)`; the held branch is l.240-244).
Probe R1 (probe4): `apk:aaa` holds bytes X as a plain GitLab file (alg sha256). `apk:bbb` lists X in its
sha512sums with a wrong sha512 that its APKBUILD agrees with. `lock_entry_problems` returns `[]` and the run
exits 0 with `fetch.json`. Size is consistent and sha256 binds the bytes, so no unverified byte is kept. The
case needs a corrupt lock (the lock tool checks each sha512 against the bytes) and a sha256 shared across
algs; the committed lock has 0 of these. Fix (either): hash sha1 and sha512 on every download, keep the
digests per sha256 in `held`, and check `upstream.value` on a held hit; or a lock rule that one sha256
carries one upstream alg (the committed lock passes it). Test row: the R1 fixture exits 1 with no
`fetch.json`.

New attempts that failed closed: R2-R2d (redaction marker look-alikes, a signed-hop timeout), R3 (`fetch.json`
as a directory), R4 (malformed rows in the shared-sha256 rule: problems, never an exception), R5 (the committed
lock still passes `lock_entry_problems`).

## Re-audit addendum, rework round 2 (2026-10-28, security)

Delta: `_shared_sha256_problems` now requires one upstream alg per sha256 across the lock. Files of size 0
are exempt, and the orchestrator accepted the exemption. Probes R1 and E1-E5 are in
`u8a-security-probes.txt` (probe5). `python -m unittest tests.test_sources_fetch`: OK (information only).

**Verdict: PASS. L-6 is closed, and the size-0 exemption opens nothing.**
- R1 (sha256 first, wrong sha512 held): a named `stage lock` problem with 0 calls. The same pair with the
  true sha512 is also refused (R1c), so cross-alg sharing of a non-empty file is now refused outright.
- E4: a non-empty sha256 under two algs where one entry is arm64-only is refused in both lock orders, and
  an amd64 run makes 0 calls. The rule spans every entry and arch.
- E1: an empty file under sha256 in one entry and under sha512 in another passes the rule and fetches. This
  is safe for three reasons:
  - The exemption skips only the alg and value comparison; the one-size check runs first.
  - The per-file size-0 rules force sha256 to the empty hash and a sha512 upstream to the empty hash (E2,
    E2b refused). apk files may carry only sha256 or sha512, so every exempted digest is a fixed constant.
  - Size 0 is legal only for an apk GitLab API raw URL (E3b refused on distfiles).
- E1b, E3: a lock claiming size 0 for bytes that are not empty fails at `_place`'s cap (`more than 0
  bytes`, with the query omitted) before anything is hashed or written. So the fetched copy of an empty
  file is bound to 0 bytes and the empty sha256, and any held copy stands for those same bytes.
- E5: the committed lock still passes `lock_entry_problems` and holds 0 size-0 files today.
