# platform-sbom part 11

Plan item: platform-sbom. U7d: source lock real run, pgdg route, retry.
Live handoff: [../platform-sbom.md](../platform-sbom.md).

## 2026-10-25 — analyst (U7d)
- Q72 is drafted in `docs/open-questions.md`, for the human, before U7d's real run: should `snapshot.debian.org`'s transient errors still fail the lock tool under Q61? Recommended: resume-from-partial within a run, plus a bounded retry on 5xx and timeouts only. U8 keeps Q61 strictly. `docs/requirements.md` PSC-23 gains the pointer. Status line: "U0-U7c committed (U7c 86f7831, ...); U7d blocked on Q71 and Q72".


## 2026-10-25 — analyst (U7d rulings)
- Human rulings, verbatim "Ok to both 71 (pg) and 72 retry", recorded in `docs/open-questions.md` and in `docs/requirements.md` PSC-23:
  - A71: a `pgdg` kind and a tenth host, `apt-archive.postgresql.org`. This amends the host-set test to ten hosts and ADR-KE-016 point 4; security reviews both at U7d.
  - A72: option 3 only. The lock tool retries at most 3 times (10/30/60 s), on 5xx and timeouts only, and prints and records every retry. U8 keeps Q61 strictly. Option 2 is not adopted; it goes back to the human if the U7d run still fails.
- Status: U7d in progress.

## 2026-10-25 — architect (U7d)
- Asked: make U7d implementable. Wrote "U7d precision" at design-notes l.2107-2306 (before N6), and a pointer bullet at the end of ADR-KE-016.
- pgdg (P1-P6):
  - Route `{src, ver, suite}`, where suite is `bookworm-pgdg-archive` from the distro major.
  - One streamed `Sources.gz` per suite (1 GiB compressed, 4 GiB decompressed caps) gives the `.dsc` sha256. The `.dsc` is fetched from the pool and cross-checked against the index. The other files are not fetched.
  - No Release signature (no new trust root).
  - Lock: exact pool URL, a `suite` field, exact `from` texts. `hosts` grows to ten.
- Retry (R1-R6): in `fetch()`, per logical request.
  - Retried: 5xx and timeouts, including mid-body timeouts (restarted fresh). Waits 10/30/60 s, through a patchable `SLEEP`. Each retry prints `retry <n>/3 in <wait> s: <host>: HTTP <code>|timeout: <url>`.
  - Each attempt has its own 600 s deadline; waits are outside it.
  - Off by default (`retries=0`), so U8 keeps Q61.
- Steps S1-S10: build, RED (with the carried rows), GREEN, security host review, the real run (exit 3, then the manual neo4j entry, then exit 0), O3 key-set drift, commit content, security lock review plus the third Neo4j fetch, reviewer, A34, the CLAUDE.md row (updated text in S10).
- Rulings needed: P-R1 no Release signature; P-R2 mid-body timeouts retried. Fact to confirm by probe: the index path and suite name. Also: `suite` is a new exact key on pgdg entries.

## 2026-10-26 — tester (U7d RED: held on the suite probe)
- The probe was run first, as P1 asks. `dists/bookworm-pgdg-archive/Release` answers 200; plain `bookworm-pgdg/Release` answers 404.
- **No `main/source/Sources.gz` exists** (404). Release lists only `Sources` (5043212 B) and `Sources.bz2` (734866 B, sha256 matching Release).
- All three keys' stanzas are present: Directory `pool/main/p/<src>`, and the .dsc listed in Checksums-Sha256 (the first entry sits on the field line).
- Per P1 ("the architect amends the exact form"), no RED is written yet. Evidence: `u7d/suite-probe.txt`.

## 2026-10-26 — security (U7d design review)
- Asked: review the tenth host `apt-archive.postgresql.org`, the `pgdg` kind and its unsigned trust chain (P-R1), and the Q72 retry (P-R2), before GREEN. Verdict: **design review PASS** with one required amendment. Detail: `u7d/security-design.md`; probes `u7d/security-design-probes.txt` (only that host).
- Host: PGDG content on AWS S3/CloudFront, TLS 1.3, Amazon cert, SAN exact, no redirects; the `-archive` suite keeps all versions (pool `.dsc` 2026-07-17 under a 2026-10-21 Release) but nothing promises immutability; no `Valid-Until`. Pool paths follow the Debian rule.
- **A-1 (required):** there is no `Sources.gz` (404, also `.xz`); the signed Release lists `Sources` (5043212 B) and `Sources.bz2`. Recommend the uncompressed `Sources` with a 64 MiB cap (no decompressor), and duplicate-field checks **per stanza** (round 1 `parse_dsc` refuses duplicates across paragraphs).
- Trust chain verified out of band today: InRelease signed by `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8`, the key the bundled postgres image already pins; gpgv Good; signed Sources sha256 `9550c528...fe722`; postgresql-common `.dsc` `fc1b2290...91da` 1538 B = my fetch = the tester stanza. **R-1:** keep P-R1 in the tool, but at S8 security runs `gpgv` on the run InRelease and checks Sources and the 3 stanzas against the lock (no new trust root).
- Retry: **R-2** add a run-wide retry/wall-clock budget (45 min worst case per request); **R-3** keep `SNAPSHOT_PAUSE` per attempt, a 429 fails closed; **R-4** print signed queries as omitted; **R-5** never retry TLS errors, resets, caps, deadline or hash mismatches (pin in tests).

## 2026-10-26 — tester (U7d RED)
- 31 failing as expected: 26 U7d methods (3 guards pass), plus 5 changed U7a/U7b/U7c/U6 tests.
  - Rows: retry R1-R6 and security 3-6 (patched `SLEEP`, exact lines, `?<query omitted>`, run budget and deadline, never-retried list, 5xx/timeout contrast); the pgdg route (InRelease-bound Sources, caps, texts, pool rule, `/out/pgdg-<suite>.InRelease`); lock P5; lock-needs suite P1; ten hosts; R1-N1; R1-N2; per-stanza duplicates; first entry on the field line; I-5 synthetic nonce; 182-key coverage.
  - Changed, citing A71/A72: U6 host set, good_entry pgdg, full-lock test, pgdg host row, merge/skip rows, the truncation row (stale manual entry), the mid-body timeout line set.
- Targets `u7d/target-{sources_resolve.py,sbom_check.py,sources_lock.sh,source-policy.json}`; reach PASS, 1076 OK.
- Controls: 70 rows, 0 unexpected.
- Evidence: `u7d/red-verify-fast.txt`, `u7d/target-reach-verify-fast.txt`, `u7d/red-mutants.txt`.

## 2026-10-25 — developer (U7d GREEN)
- Asked: U7d GREEN (pgdg route, bounded retry, carried rows, ten hosts). Copied `u7d/target-sources_resolve.py`, `target-sbom_check.py`, `target-sources_lock.sh`, `target-source-policy.json` over `scripts/` and `docker/source-policy.json`; diffs against HEAD read, no refactor. The InRelease copy in `sources_lock.sh` uses `-f` and runs after the lock write. The real lock was NOT run.
- `scripts/verify.sh fast`: PASS (`u7d/green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7d/green-verify-full.txt`). Controls: `u7d/green-controls.txt`.
- Next: reviewer and security, then the real lock run (separately briefed). Nothing committed.

## 2026-10-26 — reviewer (U7d)
- Asked: review U7d GREEN (pgdg route, bounded retry, shared deb822 parser, P5 lock rules, ten hosts, carried rows). Verdict: **CHANGES REQUESTED**. Detail: `u7d/review.md`.
- B1: real-opener timeouts during connect, TLS or send arrive as `URLError(reason=TimeoutError)`, so they are not retried and not reported with the timeout text.
  - Input: loopback, a listener that never answers TLS: `_transport` gives a non-retryable `URLError` (`u7d/reviewer-probes.txt`).
  - Fakes hide it.
  - Fix: unwrap the timeout reason, plus a row.
- B2: `sources_lock.sh` l.105 (`docker save -o` through `hostpath`, after lock-run-0) differs from the copied target. It is not in the handoff and no test covers it. Fix: record it, plus a `cygpath`-shim fake-docker row.
- Nits:
  - N1: the pgdg `suite` is shape-only. `trixie-` or `evil-pgdg-archive` passes for a debian-12 package; bind it to the derived suite.
  - N2: the InRelease copy hard-codes the U7d evidence folder and runs after the lock write (exits 1 with the lock written).
  - N3: Sources line numbers are per stanza.
  - N4: one malformed foreign stanza fails the pgdg route (fails closed).
- Conformant:
  - Retry machine: per logical request, fresh hashers per attempt, run budget 20 and deadline 3 h, query omitted, never-retried list.
  - The shared parser in all three uses.
  - pgdg P1-P6 and P2 amended (InRelease-bound Sources size+sha256), the P5 rules, R1-N1/R1-N2/I-5, PS-1.2.
- Controls re-run: 70/64/6, 0 unexpected (`u7d/reviewer-controls.txt`). The lock file and the lock-run evidence were untouched.
- Next: tester rows for B1/B2; developer GREEN; re-check. The real lock run's resolver code changes with B1.

## 2026-10-26 — security (U7d)
- Asked: code audit of the pgdg route, the Sources binding, the bounded retry, the pgdg lock rules, the InRelease copy step and the tenth host (lock and lock-run files not touched). Verdict: **PASS** (no critical/high/medium). Detail: `u7d/security.md`; probes `u7d/security-probes.txt`.
- Holds: InRelease parsing sees only signed text (a trailer, a second block or a prefix are ignored or fail; duplicate SHA256 refused); Sources read stops past the Release size and is used only after size+sha256; retries only on 5xx/timeouts with 10/30/60, a run budget and a deadline checked before waits, never on 4xx/429/418/reset/TLS; the snapshot pause applies per attempt; pgdg URLs pinned to the pool path, suite grammar, `from` texts.
- L-1 (low): the copy step follows symlinks in `$work/out` (`[ -f ]` and `cp` dereference): skip links. Info: I-1 the final post-retry error keeps the query; I-2 the entry suite is not bound to the package distro in `lock-check`; I-3 the Sources buffer rescan (19 s for 60 MiB without a blank line, bounded); I-4 the old nonce remains in committed U7c evidence only.

## 2026-10-26 — security (U7d S8, third Neo4j fetch: blocked)
- Asked: the network-independent third fetch of the Neo4j 5.26.32 tarball before the lock commit. **Not done.** `aria-gb10`: host key unknown, strict checking refused (not accepted on the user's behalf); `aria-gb10-2`: publickey/password refused. No command ran on either host. Recorded in `sources-provenance.md` with the read-only one-liner.
- Needs the human: run the one-liner on a model host and paste sha256/size/host, or enable key login / confirm the `aria-gb10` host key, or approve a one-off CI step (repo change). Compare with `182ae2e5...91e3`, 20907800 B; a mismatch blocks the commit.

## 2026-10-25 — developer (U7d real run, BLOCKED)
- Asked: S5 real run `scripts/sources_lock.sh --arch amd64` (then neo4j manual entry, run 2, sizes, drift, lock-check). Result: STOPPED at run 1; no lock written, no neo4j entry written.
- Defect 1 (fixed, uncommitted): on Git Bash `docker save -o "$work/tars/..."` got a `\tmp\...` path (MSYS_NO_PATHCONV=1) and failed (`lock-run-0-failed-docker-save.txt`). One-line fix in `scripts/sources_lock.sh` l.105: `docker save -o "$(hostpath "$work/tars/$name.tar")"` (same as the other mounts; identity on Linux). Run 1 then got through save, SBOMs and lock-needs.
- Defect 2 (open, design): the resolver stops on the first apk key: `apk:alpine-baselayout@3.7.1-r8: alpine-baselayout: main/alpine-baselayout/alpine-baselayout.post-upgrade at dd4f6c3f... is not a regular file` (wall 100 s, exit 1; `lock-run-1.raw`). In aports that file is a symlink (mode 120000); design-notes l.1820-1823 (U7c ruling) makes a symlink or other non-blob entry a failure. Real data contradicts the ruling; needs an architect/orchestrator ruling (skip symlinks, or lock their target path). I did not change `_tree_blobs`.
- Fast verify after the script fix (`u7d/lock-fix-verify-fast.txt`): 1082 ran, 6 failures, all in the untracked `tests/test_sources_lock_committed.py` (they need the committed lock, which does not exist yet); no other test failed.
- Evidence redacted check: no profile paths or SIDs in the run logs. Not done: run 2, lock-sizes, drift, lock-check (nothing to check).

## 2026-10-26 — tester (U7d S7 RED)
- New `tests/test_sources_lock_committed.py`: 6 methods fail, each as a named "not committed" failure (no errors).
  - The methods: `lock_problems == []`; the 182-key set; canonical, LF-only, format 1; the manual neo4j entry (security's sha256/size, `from` names sources-provenance.md); sample = 7 kinds; the `.gitattributes` eol line.
- `LOCK`/`GITATTRIBUTES` are module paths. Reach: a stand-in lock from the fake-network coverage run, in a temp dir, plus `u7d/s7-target-gitattributes`.
- Controls: `u7d/s7_controls.py` + `s7-red-mutants.txt`, 23 rows, 0 unexpected. RED: `u7d/s7-red-verify-fast.txt`.

## 2026-10-26 — tester (U7d A34)
- Step 3 refusals PASS on Windows (`u7d/windows-run.txt`): nothing left behind, hashes unchanged, no InRelease copied.
- The happy path is the developer's Git Bash run. `u7d/lock-run-1.raw` failed (the aports symlink, round-1 item 8), so it is pending.

## 2026-10-26 — tester (U7d rework r1 RED)
- 20 failing as expected, plus S7's 6 (no lock yet).
  - New: ReworkR1U7d* — UrlError 2, Symlink 2, Script 4, SuiteBinding 2. The B2 hostpath row passes on GREEN and fails on the RED targets.
  - Changed, citing round 1 items 3/4/8: U7dLockNeeds text, U7dScriptStatic, the `--evidence-dir` option in the script-test harness (8 tests), and U7c's symlink row (now via metadata).
- Targets `u7d/r1-target-{sources_resolve.py,sbom_check.py,sources_lock.sh}`; reach: 1093 run, only S7's 6 fail.
- Controls `u7d/r1_controls.py` + `r1-red-mutants.txt`, 33 rows, 0 unexpected.
- No dedicated "chain" mutant: the chain row is caught by "target not checked".

## 2026-10-25 — developer (U7d r1 + S7 GREEN, real run, BLOCKED at run 2)
- Done: copied `u7d/r1-target-sources_resolve.py`, `r1-target-sbom_check.py`, `r1-target-sources_lock.sh` (it has the hostpath on `docker save -o`; diffs against the U7d targets read); `.gitattributes` now equals `u7d/s7-target-gitattributes`.
- Run 2 (`scripts/sources_lock.sh --arch amd64 --evidence-dir docs/evidence/platform-sbom/u7d`, wall 139 s, exit 1; `u7d/lock-run-2.txt`): the symlink rule worked (`alpine-baselayout.post-upgrade -> alpine-baselayout.post-install (symlink to a locked file, skipped)`, printed twice), then `sources_lock: FAIL (resolve: apk:apk-tools@3.0.3-r1: _apk: not a safe file name; the lock is unchanged)`. apk-tools' package directory holds a regular file named `_apk` (leading underscore); the safe-name rule rejects it. Not covered by the rulings. STOPPED: no production code patched, no lock written, no neo4j entry, no run 3, no lock-sizes/drift, no final verify or controls.
- Needs a ruling (allow a leading `_` in aports file names, or skip) and then a RED before any fix.

## 2026-10-26 — tester (U7d r1 item 10: aports probe + RED)
- Probe (read-only, 59 GitLab API requests, no raw/distfiles): the 19 apk keys at their real commits (o:/V:/c: from ke-gateway:local and valkey installed dbs). Only new shape: leading `_` names (apk-tools 3.0.3-r1 `_apk`; musl 1.2.5-r21 `__stack_chk_fail_local.c`, `__NR_riscv_hwprobe.patch`; musl 1.2.6-r2 `__stack_chk_fail_local.c`), all in sha512sums; item 10 clears them. No subdirs, submodules, collisions, other modes; links only alpine-baselayout x2 (skip rule holds); max 80 entries (busybox). Not probed: zero-size files (tree has no size; lock needs size > 0).
- RED: 13 failing in 8 methods (ReworkR1U7dUnderscoreTest 6, ReworkR1U7dUnderscoreLockTest 2 less 1 guard, SymlinkTest.test_the_real_shape changed to the key-prefixed line, citing item 10) + S7's 5. Targets: r1-target-sources_resolve.py / r1-target-sbom_check.py (pattern, key-prefixed skip line); baseline r1-pre10-*.
- Reach: only S7's 5 fail. Controls 27 rows, 0 unexpected.
- Evidence: u7d/aports-probe.txt, u7d/aports_probe.py, u7d/r1i10-red-verify-fast.txt, u7d/r1i10-target-reach-verify-fast.txt, u7d/r1i10_controls.py, u7d/r1i10-red-mutants.txt

## 2026-10-26 — tester (U7d r1 item 12 RED: empty GitLab apk files)
- RED: 4 failing (ReworkR1U7dEmptyFileLockTest: empty GitLab file passes; still_refused rows "size 0 with another sha256" and "...another sha512 upstream"; ReworkR1U7dEmptyFileTest: a 0-byte raw body gives a size-0 entry that passes lock_problems). Guarded rows: size 0 on distfiles/deb/pypi/maven, -1/true/false/4 GiB+1 on a GitLab file. Total RED 22 = item 10's 13 + 4 + S7's 5.
- Target: r1-target-sbom_check.py (low bound 0 only for apk at the API raw form; size 0 needs the empty sha256, and a sha512 upstream the empty sha512 - message `<name>: size 0 but sha512 is not the empty hash` is the tester's wording).
- Reach: only S7's 5 fail. Controls (r1i10_controls.py, items 10+12): 35 rows, 0 unexpected.
- Evidence: u7d/r1i12-red-verify-fast.txt, u7d/r1i12-target-reach-verify-fast.txt, u7d/r1i10-red-mutants.txt

## 2026-10-26 — developer (U7d GREEN + real run; verify RED on one scanner hit)
- Applied `u7d/r1-target-sources_resolve.py` and `r1-target-sbom_check.py` (items 10, 12; diffs vs `r1-pre10-*` read); `sources_lock.sh` equals `r1-target-sources_lock.sh` (cmp); `.gitattributes` has the S7 line.
- Run 3 (`u7d/lock-run-3.txt`): exit 3, wall 759 s, 2 symlink skips (alpine-baselayout 3.7.1-r8 and 3.7.2-r1), no retries. Candidate sha256 `182ae2e5...91e3`, size 20907800, host codeload.github.com == sources-provenance.md. Manual neo4j entry written (origin manual, arches ["amd64"], file `5.26.32.tar.gz`, upstream sha256 + "second fetch: security 2026-10-25, ..."), canonical via `lock_text`. Run 4 (`u7d/lock-run-4.txt`): exit 0, wall 98 s, no diff output (lock unchanged), no retries, no skips printed; `u7d/pgdg-bookworm-pgdg-archive.InRelease` present (5621 B).
- Lock: 182 keys == the 182 fixture keys, none added/missing (`u7d/drift.txt`); sizes in `u7d/lock-sizes.txt`; `lock-check` ok (182 components, amd64) against the six U3 fixture SBOMs (the run's own SBOMs are deleted by the tool).
- BLOCKER, verify fast and full RED (`u7d/r1-green-verify-fast.txt`, `-full.txt`; 1105 ran, 1 failure): `tests.test_engine_hardcoded.RepositoryScanTest.test_no_hardcoded_ports` flags `docker/sources.lock.json:8760: 8080` = `"size": 8080` of `lz4_1.10.0-4.debian.tar.xz`. A real data value, not a port. Outside the rulings; no scanner or lock change made. Needs a ruling (exempt `docker/sources.lock.json` in the port scan) and a RED.
- Controls: r1 33 rows 0 unexpected; r1i10 35 rows 0 unexpected; s7 23 rows, 2 unexpected = the two baseline rows "the repository today (no lock, no eol line)" and ".gitattributes line missing" which now hold (the line and lock exist); expected artifacts, same class as the U7b note.
- Nothing committed.

## 2026-10-26 — reviewer (U7d rework r1 + lock)
- Asked: re-check U7d rework round 1 (l.2492-2721) and review the real `docker/sources.lock.json`. Verdict: **APPROVED**. Detail: `u7d/review-r1.md`.
- Closed:
  - B1: URLError timeout reasons are unwrapped and retried; other reasons are not (tested against the real opener).
  - B2: the hostpath fix is pinned by a cygpath-shim row.
  - N1: suite bound via `pgdg_suite`.
  - N2: `--evidence-dir`, with the copy before the move and links refused.
- Rule changes: item 8 symlinks (resolver-only; same-dir regular target), item 10 leading `_`, item 12 size 0 at the API raw form with the empty hashes. No pass-but-should-not except R1-N1.
- The lock:
  - 182 keys = fixtures; canonical, LF; `lock_problems == []` with the fixture docs.
  - 872 files, 1.33 GB.
  - URL forms, `from` texts and algs per kind as designed.
  - neo4j manual = second fetch; temurin = sidecar; psycopg = uv.lock; pgdg suite bookworm; the baselayout link skipped.
  - The sample is one per kind.
  - The committed-lock test (7 OK on host) pins all of this.
- Controls re-run: r1 33/29/4, r1i10 35/31/4, s7 31/24/7, all 0 unexpected.
- Nits:
  - R1-N1: an empty APKBUILD passes the lock rule (suggest size > 0 for the APKBUILD).
  - R1-N2: drift.txt lacks the in-key package counts S6 asked for (information only).
  - R1-N4: optionally pin temurin and pypi in the committed test.
- Gates outside this verdict: item 13 (scanner hit at lock l.8760, verify red) and the third Neo4j fetch (human).

## 2026-10-26 — tester (U7d item 13 RED + s7 controls fix)
- RED 3 failing: RepositoryScanTest.test_no_hardcoded_ports (lock:8760 `8080`), ScannerContractTest.test_the_generated_lock_is_skipped, ReworkR1U7dEmptyFileLockTest.test_an_empty_apkbuild_fails (R1-N1); guard CommittedLockTest.test_nothing_the_hardcoded_scan_would_miss passes on the real lock. Targets u7d/i13-target-hardcoded_scan.py, i13-target-sbom_check.py; reach verify fast PASS.
- Controls: i13_controls.py 14 rows 0 unexpected; s7_controls.py baseline now built in a temp copy, `--base repo` 31 rows 0 unexpected (old run kept as s7-green-controls-attempt1.txt).
- Evidence: u7d/i13-red-verify-fast.txt (run1 = before the R1-N1 row), i13-target-reach-verify-fast.txt, i13-red-mutants.txt, s7-green-controls.txt

## 2026-10-26 — developer (U7d item 13 GREEN)
- Copied `u7d/i13-target-hardcoded_scan.py` -> `tests/hardcoded_scan.py` (path-exact `docker/sources.lock.json` in ALLOWED_FILES) and `i13-target-sbom_check.py` -> `scripts/sbom_check.py` (diff: only the APKBUILD `size 0` clause); nothing else changed.
- `scripts/verify.sh fast` PASS and `full` PASS (1015 s) with the lock in the tree (`u7d/i13-green-verify-fast.txt`, `-full.txt`).
- Controls: `u7d/i13-green-controls.txt`, `u7d/s7-green-controls-final.txt` (summaries in the report). Nothing committed.
- Controls note: i13 shows 3 unexpected, all `[baseline]` rows (scanner x2, sbom_check x1) that expect the pre-item-13 files to fail; `--base repo` now reads the GREEN files, so they pass. S7 final: 31 rows, 0 unexpected.

## 2026-10-26 — security (U7d r1 + lock review)
- Asked: re-check U7d rework round 1, review the item-13 design, and do S8 part 2 (the lock review). Verdicts: **code PASS**, item 13 **acceptable**, **lock review PASS**; the commit still **waits on the third Neo4j fetch** (human). Detail: `u7d/security-r1.md`; probes `u7d/security-r1-probes.txt`; provenance appended.
- Code: L-1 closed (links and non-regular files fail, `cp -P`, copy before the move, `--evidence-dir`); B1 holds (TLS-handshake timeout unwrapped and retried; SSL, refused and DNS errors never); N1 suite bound (trixie on bookworm refused); item 8 symlinks only to a sibling regular blob (13 refusal rows); items 10 and 12 hold. Item 13: path-exact skip plus the integer/key test is sound; optionally also scan the lock string values for declared tokens.
- Lock: `lock_problems == []` (182 entries, 872 files); hosts, URL templates, 11 `from` templates, arches amd64, no size 0, no signed queries; 11 shared deb orig URLs and 147 cross-commit apk sha256s are legitimate. pgdg: gpgv Good (B97B...4CF8), signed Sources sha256 = re-fetch, 3 stanzas and 3 `.dsc` = lock. One spot re-fetch per kind = lock. Neo4j manual entry = provenance. Lock and lock-run evidence clean.


## 2026-10-26 — tester (U7d item 13 controls baseline fix)
- i13_controls.py baseline now SAVED copies (u7d/i13-pre-hardcoded_scan.py = HEAD 86f7831; r1-target-sbom_check.py); `--base repo` 14 rows 0 unexpected (u7d/i13-green-controls.txt; developer's run kept as -attempt1); targets mode also 0 unexpected (i13-red-mutants-rerun.txt).
- STANDING RULE for every controls script: baselines come from SAVED copies, never from the repository's current files (`--base repo` swaps only the target).

## 2026-10-26 — reviewer (U7d item 13)
- Re-check: the scanner skips only `docker/sources.lock.json`, matched by exact path, with a reason comment (i13 mutants catch a line exemption, `docker/*.json`, suffix or prefix matching, a dropped skip and a dropped reason). The APKBUILD `size > 0` clause closes R1-N1 (mutant row). The new contract test catches a `port` key, an `http_*` key and a stray number (`u7d/reviewer-i13-probes.txt`). Targets are byte-identical; i13 verify full OK.
- **U7d final verdict: APPROVED.** The only remaining gate is the third Neo4j fetch (item 7, human).


## U7d region as it stood at the gate (verbatim from the live doc)

### 2026-10-25 — analyst (U7d)
- Q72 drafted, Q71 deadline moved to U7d.
- Detail: archive/platform-sbom-part11.md; evidence docs/open-questions.md, docs/requirements.md PSC-23

### 2026-10-25 — orchestrator (pushed U5-U7c)
- Pushed c300d88..86f7831 to draft PR #14 (human approved); no merge before U9. Detail: archive/platform-sbom-part8.md

### 2026-10-25 — analyst (U7d rulings)
- A71 pgdg kind + apt-archive.postgresql.org (human); A72 bounded retry for the lock tool only (human); option 2 not adopted.
- Detail: archive/platform-sbom-part11.md; evidence docs/open-questions.md, docs/requirements.md PSC-23

### 2026-10-25 — architect (U7d)
- U7d precision P1-P6/R1-R6/S1-S10 (design-notes l.2107-2321); P2 amended after the probe (uncompressed Sources bound to Release sha256+size, l.2323-2404); P-R1 no signature verification, P-R2 mid-body timeout retried.
- Detail: archive/platform-sbom-part11.md; evidence design-notes N5 amendment U7 "U7d precision"

### 2026-10-26 — tester (U7d RED: held on the suite probe)
- Suite probe found no `Sources.gz`; `bookworm-pgdg-archive` exists; RED held, then resumed.
- Detail: archive/platform-sbom-part11.md; evidence u7d/suite-probe.txt

### 2026-10-26 — security (U7d design review)
- Design review PASS: host on AWS S3/CloudFront, TLS ok, InRelease signed by the key the postgres image pins (gpgv at S8 adopted), per-stanza duplicates, retry budget 20 / 3 h, query omitted in retry lines.
- Detail: archive/platform-sbom-part11.md; evidence u7d/security-design.md, u7d/security-design-probes.txt

### 2026-10-26 — tester (U7d RED)
- RED: 31 failing (26 new U7d* + 5 re-targeted), reach PASS, controls 70 (0 unexpected); fake-network pgdg route on an InRelease-bound Sources, retry R1-R6 + budget/deadline, carried rows, ten hosts, 182 keys resolve.
- Detail: archive/platform-sbom-part11.md; evidence u7d/red-verify-fast.txt, u7d/target-reach-verify-fast.txt, u7d/red-mutants.txt

### 2026-10-25 — developer (U7d GREEN)
- GREEN: four targets copied, verify fast + full PASS 1009 s, controls 0 unexpected, real lock not yet run.
- Detail: archive/platform-sbom-part11.md; evidence u7d/green-verify-fast.txt, u7d/green-verify-full.txt, u7d/green-controls.txt

### 2026-10-26 — security (U7d)
- PASS: InRelease stripping, Sources binding, retry loop, pgdg rules, copy step hold; L-1 copy step follows symlinks (-> r1 item 6); I-1..I-4.
- Detail: archive/platform-sbom-part11.md; evidence u7d/security.md, u7d/security-probes.txt

### 2026-10-26 — reviewer (U7d)
- CHANGES REQUESTED: B1 URLError-wrapped connect/TLS timeouts not retried; B2 untested hostpath change to sources_lock.sh during the real run (accepted fix, pinned in r1, process breach recorded); N1 suite shape-only, N2 InRelease copy after the move into a hard-coded path, N3/N4 cosmetic; controls 70, 0 unexpected.
- Detail: archive/platform-sbom-part11.md; evidence u7d/review.md, reviewer-probes/

### 2026-10-26 — security (U7d S8, third Neo4j fetch: blocked)
- BLOCKED on the human: ssh to aria-gb10 (unknown host key, not accepted) and aria-gb10-2 (publickey denied); one-liner and options in sources-provenance.md; expected 182ae2e5...91e3 / 20907800 B; the lock commit waits.
- Detail: archive/platform-sbom-part11.md; evidence docs/evidence/platform-sbom/sources-provenance.md

### 2026-10-25 — developer (U7d real run, BLOCKED)
- Run 0 failed at docker save (POSIX path on Git Bash; hostpath fix, pinned in r1 item 2); run 1 exit 1, wall 100 s, at the first apk key: aports `alpine-baselayout.post-upgrade` is a symlink (-> r1 item 8 ruling); no lock written; no Neo4j comparison yet; logs u7d/lock-run-0-failed-docker-save.txt, lock-run-1.raw.
- Detail: archive/platform-sbom-part11.md; evidence u7d/lock-run-0-failed-docker-save.txt, u7d/lock-run-1.raw, u7d/lock-fix-verify-fast.txt

### 2026-10-26 — tester (U7d S7 RED)
- 6 failing (CommittedLockTest: lock not committed yet, named message); reach via a stand-in lock; controls 23, 0 unexpected; target .gitattributes line.
- Detail: archive/platform-sbom-part11.md; evidence u7d/s7-red-verify-fast.txt, u7d/s7_controls.py, u7d/s7-red-mutants.txt, u7d/s7-target-gitattributes

### 2026-10-26 — tester (U7d A34)
- Step 3 refusals PASS on Windows (3a-3e), nothing left behind, 13/13 hashes identical; happy path = the developer's real run, pending.
- Detail: archive/platform-sbom-part11.md; evidence u7d/windows-run.txt, u7d/lock-run-1.raw

### 2026-10-26 — tester (U7d rework r1 RED)
- 20 failing (10 new ReworkR1U7d* + 10 changed; URLError unwrap, symlink rule item 8, --evidence-dir/copy-before-move/links refused, suite binding) + the 6 S7 rows; reach PASS except S7's 6 (no lock); controls 33, 0 unexpected; B2 hostpath row already green on the tree.
- Detail: archive/platform-sbom-part11.md; evidence u7d/r1_controls.py, u7d/r1-red-mutants.txt, u7d/r1-target-sources_resolve.py

### 2026-10-25 — developer (U7d r1 + S7 GREEN, real run, BLOCKED at run 2)
- r1 targets + .gitattributes applied; run 2 exit 1 wall 139 s: symlink rule works (baselayout skipped), stopped on apk-tools `_apk` (leading `_` refused by the file-name rule -> r1 item 10 ruling); no lock written; run 3, sizes, drift, verify and controls pending.
- Detail: archive/platform-sbom-part11.md; evidence u7d/lock-run-2.txt

### 2026-10-26 — tester (U7d r1 item 10: aports probe + RED)
- Probe of the 19 aports dirs: only leading-`_` names (item 10) and the baselayout symlink (item 8); 59 read-only API requests; item-10 RED 13 failing, reach PASS except S7, controls 27, 0 unexpected.
- Detail: archive/platform-sbom-part11.md; evidence u7d/aports-probe.txt, u7d/r1i10-red-verify-fast.txt, u7d/r1i10-target-reach-verify-fast.txt, u7d/r1i10-red-mutants.txt

### 2026-10-26 — tester (U7d r1 item 12 RED: empty GitLab apk files)
- Item-12 RED 4 failing (size 0 only for GitLab apk files with the empty hashes); reach PASS except S7's 5; controls 35, 0 unexpected.
- Detail: archive/platform-sbom-part11.md; evidence u7d/r1i12-red-verify-fast.txt, u7d/r1i12-target-reach-verify-fast.txt, u7d/r1i10-red-mutants.txt

### 2026-10-26 — developer (U7d GREEN + real run; verify RED on one scanner hit)
- r1 + items 10/12 applied; run 3 exit 3 (759 s, Neo4j candidate == second fetch), manual entry written, run 4 exit 0 (98 s); 182 keys = fixtures, 872 files, 1.327 GB, sample 137 MB, 2 symlink skips, 0 retries; verify fast/full FAIL on one port-scanner hit in the lock (`size: 8080`) -> item 13; s7 controls baseline stale (2 rows).
- Detail: archive/platform-sbom-part11.md; evidence u7d/lock-run-3.txt, u7d/lock-run-4.txt, u7d/drift.txt, u7d/lock-sizes.txt, u7d/r1-green-verify-fast.txt

### 2026-10-26 — reviewer (U7d rework r1 + lock)
- APPROVED: B1/B2/N1/N2 closed; items 8/10/12 hold; the lock is canonical, 182 keys, lock_problems == [], manual neo4j == second fetch, temurin/pypi values cross-checked; nits R1-N1 empty APKBUILD passes size-0 rule (-> item 13 RED), R1-N2 package counts not compared, R1-N4 optional pins; controls r1/r1i10/s7 0 unexpected.
- Detail: archive/platform-sbom-part11.md; evidence u7d/review-r1.md, u7d/reviewer-r1-controls.txt

### 2026-10-26 — security (U7d r1 + lock review)
- Code r1 PASS (L-1, B1, B2, N1, items 8/10/12 hold); item 13 acceptable (PS-1.2); S8 lock review PASS: gpgv good signature on the saved InRelease, Sources + 3 .dsc re-fetched equal, one spot re-fetch per kind equal, 182 entries clean; third Neo4j fetch still with the human.
- Detail: archive/platform-sbom-part11.md; evidence u7d/security-r1.md, u7d/security-r1-probes.txt, sources-provenance.md

### 2026-10-26 — tester (U7d item 13 RED + s7 controls fix)
- Item-13 RED 3 failing (scanner skip for the lock, path-exact; APKBUILD size > 0), reach PASS with the lock in the tree; i13 controls 14, 0 unexpected; s7 baseline fixed, 31 rows, 0 unexpected.
- Detail: archive/platform-sbom-part11.md; evidence u7d/i13-red-verify-fast.txt, u7d/i13-target-reach-verify-fast.txt, u7d/i13-red-mutants.txt, u7d/s7-green-controls.txt

### 2026-10-26 — developer (U7d item 13 GREEN)
- Two targets applied; verify fast + full PASS 1015 s with the lock in the tree; s7 controls 0 unexpected; i13 controls 3 stale-baseline rows (tester re-baselining).
- Detail: archive/platform-sbom-part11.md; evidence u7d/i13-green-verify-fast.txt, u7d/i13-green-verify-full.txt, u7d/i13-green-controls.txt

### 2026-10-26 — tester (U7d item 13 controls baseline fix)
- i13 controls re-based on saved pre-13 files: 14 rows, 0 unexpected; rule: baselines from SAVED copies, `--base repo` swaps only the target.
- Detail: archive/platform-sbom-part11.md; evidence u7d/i13-green-controls.txt, u7d/i13-red-mutants-rerun.txt, sources-provenance.md

### 2026-10-26 — reviewer (U7d item 13)
- APPROVED (final for U7d): item 13 skip path-exact, R1-N1 closed, committed-lock guard probed; only the third Neo4j fetch remains.
- Detail: archive/platform-sbom-part11.md; evidence u7d/reviewer-i13-probes.txt, sources-provenance.md

### 2026-10-26 — orchestrator (U7d gate; commit HELD for the human's third fetch)
- Rework rounds used: 1 of 5 (items 1-13 incl. real-data rules 8/10/12 and the item-13 scanner skip). Rulings: design-notes N5 amendment U7 "U7d precision" l.2107-2404, "security design review adopted" l.2406-2490, "rework round 1" l.2492-2821.
- Review APPROVED (r1 + lock + item 13), security PASS (code r1; item 13 acceptable) and S8 lock review PASS (gpgv good signature on the saved PGDG InRelease; Sources + 3 .dsc re-fetched equal; one spot re-fetch per kind equal), A34 PASS (refusals; the happy path is the real run on this Windows host: lock-run-3/4), controls r1/r1i10/s7/i13 all 0 unexpected.
- Orchestrator verify full PASS 1018 s (1108 unit + 15 integration, sentinel ok, lock in the tree; `u7d/orchestrator-verify-full.txt`). Diff read across the unit. The lock: 182 keys, 1 manual (neo4j == second fetch), 472,945 B, LF, canonical; full set 1.327 GB, sample 137 MB.
- HELD: the commit waits for the third Neo4j fetch from another network path (U7b ruling; the human: one-liner in sources-provenance.md) and the CLAUDE.md "Generated artifacts" row (human's file; text in N5 amendment U7 item 7 + S10 with apt-archive.postgresql.org). Commit set when released: docker/sources.lock.json, .gitattributes, docker/source-policy.json, scripts/{sbom_check.py,sources_resolve.py,sources_lock.sh}, tests/{hardcoded_scan.py,test_engine_hardcoded.py,test_sbom_obligations.py,test_sources_lock.py,test_sources_resolve.py,test_sources_lock_committed.py}, docs/evidence/platform-sbom/{u7d,sources-provenance.md,design-notes.md}, docs/architecture.md, docs/open-questions.md, docs/requirements.md, handoff + archives part8/9/10/11, docs/log.md.
- Forward: full operator bundle ~8 GiB staged > 7 GiB floor (U11 states it for the human); keep the run's SBOMs in --evidence-dir (U8); U8 name checks (.dsc Files / APKBUILD sha512sums vs the entry); the stale-baseline lesson: controls baselines come from SAVED copies.

### 2026-10-26 — developer (CLAUDE.md row)
- Added the human-approved `docker/sources.lock.json` row after `uv.lock` in CLAUDE.md "Generated artifacts"; nothing else changed. `scripts/verify.sh fast` PASS (`u7d/claude-row-verify-fast.txt`). Not committed.
