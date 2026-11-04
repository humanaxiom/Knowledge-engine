# platform-sbom part 15

Plan item: platform-sbom. U8c parts 1 and 2 and U9a (sections dated 2026-10-29), moved verbatim. Live handoff: [../platform-sbom.md](../platform-sbom.md).

## 2026-10-29 — tester (U8c O-2 RED: drop objects.githubusercontent.com)
- RED `verify.sh fast`: 1201 tests, failures=5, all O-2 rows, all for "host still in the policy" (`u8/u8c-o2-red-verify-fast.txt`); names before/after and a scratch-copy control (policy less the host: 32/32 OK) in `u8/u8c-o2-controls.txt`.
- Red: `PolicyU6SchemaTest.test_hosts_are_the_fetch_hosts` (U6_HOSTS re-pinned to nine), `...test_hosts_drop_the_unused_temurin_redirect_target`, `CommittedLockTest.test_policy_hosts_are_the_lock_url_hosts_and_their_redirect_targets`, `SourceFetchDroppedHostTest.test_source_fetch_refuses_a_temurin_redirect_to_the_dropped_host`, `U8cDroppedHostTest.test_a_temurin_redirect_to_the_dropped_host_is_refused`. Resolver fakes moved to release-assets (green).
- No per-kind rule named the host (KIND_HOSTS binds lock URLs only; hops use policy `hosts`), so the developer's change is the policy line plus the design note; security reviews (U8-10).
- Ambiguity for the orchestrator: the brief's list had `pypi.org`; the design (N0, O2 ruling) keeps it out of `hosts`, and the tests pin it out.

## 2026-10-29 — developer (U8c O-2 GREEN: policy hosts narrowed)
- `docker/source-policy.json`: `objects.githubusercontent.com` removed from `hosts` (one entry); design-notes.md amended in 3 places (U8-10); architecture.md names no hosts, unchanged.
- Evidence: `u8/u8c-o2-green-verify-full.txt`: `verify full` PASS 1107 s, 1201 tests OK, sample fetch Temurin hops=github.com,release-assets.githubusercontent.com; the 5 RED rows green. .env removed.

## 2026-10-29 — reviewer (U8c O-2 review: APPROVED)
- Diff read: policy is exactly one host removed; tests add 5 rows, remove none, fakes retargeted equivalently; design notes additions only; full PASS 1201 OK with Temurin hop github.com -> release-assets.
- No blocking findings; nits N-1 (redundant narrowed-lock test), N-2 ("nine hosts" message), N-3 (stage only U8c files) in `u8/u8c-o2-review.md`. Security review (U8-10) still required before commit.

## 2026-10-29 — security (U8c O-2: `hosts` change, U8-10)
- PASS, no critical/high/medium. Narrowing only (10 -> 9, nothing added). `hosts` = the lock's 7 file-URL hosts plus the two observed redirect targets (codeload, release-assets). The dropped host appears 0 times in the sample, full and U8c runs. KIND_HOSTS unchanged. A refused hop names only the host, so no signed query is printed (probed with X-Amz-Signature, case and trailing-dot variants). The policy parses through sbom_check.
- Evidence: `u8/u8c-o2-security.md`, `u8/u8c-o2-security-probes.txt`. Info I-1 (one tautological test, for the reviewer), I-2 (a future Temurin redirect change fails closed and needs a reviewed re-add), I-3 (pre-existing: the policy has no eol=lf attribute).

## 2026-10-29 — analyst (U9 precision criteria)
- Asked: testable U9 criteria (PSC-15/PSC-24) in the "U8 precision" style. Written: requirements.md PSC-24 "U9 precision" U9-1..U9-15 plus the outcome metric (neither), and pointers in the status line, the table note and PSC-15.
- Covers: `--sources`/`--sources-set` CLI; the fetched dir's shape and `fetch.json` (set, arch, lock sha256, components == `fetch_plan`, every file re-hashed, nothing extra) before any write; `index` (`validate` first, `lock_problems` both ways on the bundle's SBOMs, always/exempt problems, multi-match exempt); index.json statuses; the copy (not linked; manifest sha == name); the "Source code" section and sample banner; `app/` notice copies (absent today, `bundle.sh` l.348-371); NOTICE I-3 sentence and libffi; no partial bundle and N-9; install tamper tests (sh, ps1); wiring; `u9/size.md`; the gate (full).
- Carried rows placed: U6 L-1/L-2/N1/N2, the listing, libffi (U9-4, U9-5, U9-9); U8b N-9 (U9-10). Q77 stays deferred (no re-lock at U9).
- Open, for the orchestrator: Q78 (`--sources` mandatory; rec. yes), Q79 (recorded full-set bundle at U9; rec. yes), Q80 (exempt checksum compare, security U6 L-1(b); rec. not at U9).
- Next: architect, the U9 design (N9/N3 amendment), then the orchestrator's rulings on Q78-Q80 before RED.

## 2026-10-29 — architect (U9 design: "N9 amendment, U9")
- Asked: the U9 design in the U8 pattern. Written: design-notes.md "N9 amendment, U9" (l.4237-4831, items 1-18; pointer in N9 at l.4204) and ADR-KE-016 "Amended U9" (end of architecture.md). Checked against the analyst's U9-1..U9-15: no conflict except O-11 below.
- Design: `sbom_check.py` gains `sources-check` (before any write: fetch.json canonical, set/arch/lock sha256, components == `fetch_plan`, exact listing, no links, re-hash), `index` (validate first, `lock_problems` on the bundle's SBOMs, always/exempt problems incl. multi-match, copied listing; schema item 5) and `notices` (refuse, never escape). `bundle.sh` copies the files (`cp -P`, never linked), adds `app/` notice copies and checks that each source file's manifest hash equals its name and that the manifest is under 1 MiB. Any failure after the first write removes the run's output. Installers unchanged; tamper pins for sh and ps1.
- Layout: flat `app/sources/files/<sha256>` plus `index.json` (O-3). Per-key directories would add 160 files and 161,505,072 B, and 148 names plus every key fail the path rule.
- Split: U9a (checker and install pins, fast) and U9b (wiring, NOTICE/libffi, real sample, Q79 full-set bundle, A34). No U9c: its pins cannot be RED.
- For the orchestrator: Q78 option 1, Q79 option 1 (bundle only), Q80 option 1. Also O-9 (split), O-10 (removal on failure, stronger than U9-10), O-11 (A34 for U9b despite U9-11/U9-15 "only if install.ps1 changes"), O-12 (7 GiB floor unchanged, U11). Nothing for the human. Before U9b's RED, security confirms the libffi text source (R7).
- 2026-10-29 analyst (rulings recorded): Q78-Q80 resolved (option 1 each) in open-questions.md; requirements.md U9 block amended for O-9 (U9a/U9b), O-10 (U9-10 removal), O-11 (A34 for U9b: U9-11, U9-15; N15 note in design-notes), O-12, Q78 (U9-1), Q79 (U9-13), Q80 (U9-4). Plan gate: PASS.

## 2026-10-29 — security (U8c part 2: third Neo4j fetch recorded, CI run 40907497118)
- PASS. The CI sample fetch on 5cf025c (GitHub-hosted, Azure westus, ubuntu-24.04 20261025.353.1) logged `neo4j:neo4j@5.26.32` sha256 182ae2e5...91e3, 20907800 B, hops github.com -> codeload.github.com. This equals the lock and the second fetch: three fetches from two networks agree. Recorded in `sources-provenance.md` (new last section).
- The 25 ok lines equal the `u8/expected.md` sample table. objects.githubusercontent.com: 0 hits. Secret scan of the saved log: 0 hits. Extract and comparison: `u8/ci-40907497118-fetch.txt`. Q74 data point (32m06s, unit stage 1261 s, offline_check 292 s) is in `u8/ci-timing-q74.md`.
- Open, optional, for the human: the ARM one-liner before the first operator bundle. It does not block U9. Next: U8c part 2 commit (verify fast at minimum; full before commit), then U9a.

## 2026-10-29 — tester (U9a RED: sources-check, index, notices; install pins)
- RED `verify.sh fast` (`u9/u9a-red-verify-fast.txt`): 1201 -> 1251 tests, failures=88, errors=0, all in new `tests/test_source_index.py`: missing `fetch_record_problems`/`listing_problems`/`source_index` (section tests fail at their `source_index` fixture), argparse "invalid choice" for `sources-check`/`index`/`notices`, and `exempt_matches` returning [] for a two-SPDXID jna match. Controls green in the same module (classifier unchanged; committed policy one match per entry).
- Install pins (item 10): fixture gains an SBOM, `index.json`, two `files/<sha>`; 12 rows in `_tamper_cases` plus `test_install_refuses_tampered_or_missing_source_file` (sh, ps1) green as designed; mutation controls (each rule disabled in a scratch copy, in the gates image) fail exactly their three rows each (`u9/u9a-controls.txt`, names before/after: +2, nothing removed; l.1134 kept).
- Tester's readings, not resolved (for the architect/orchestrator): ok-line counts distinct files and bytes; 4 MiB refusal text unpinned beyond `fetch.json` + a size word; multi-match SPDXIDs in document order; sample banner place vs the I-3 sentence (U9-7 "starts with" vs item 7 order); stage 6 reached by patching `fetch_plan`; `--git-sha` shape not pinned as exit 2; index stderr line form `<image>: <package>: <listing>` (prefix free).
- Next: developer U9a GREEN (`sbom_check.py` only; no test edits needed).

## 2026-10-29 — developer (U9a GREEN: sources-check, index, notices)
- `scripts/sbom_check.py` only: `fetch_record_problems`, `listing_problems`, `source_index`, `source_section`, multi-match in `exempt_matches`, the three subcommands. `verify fast` PASS, 1251 OK (8 skips): `u9/u9a-green-verify-fast.txt`; the 88 RED rows green, no test edited.
- For review: `listing_problems` catches an OSError only from a lazily read listing (O-13 (8)); the CLI builds the dict and turns a failed `scandir` into `<dir>: cannot list`. Policy shape (lists of objects, exempt strings) is checked in `source_index`. Not run: `full` (orchestrator).

## 2026-10-29 — reviewer (U9a review: CHANGES REQUESTED)
- The code conforms to items 1, 3, 5, 6 and 7 and to O-13 (1)-(8) (read and probed; `u9/u9a-review.md`). Both blocking findings are test-only: B-1 pin O-13 (2), (4)/U9-7 "starts with", (6) and (7), and refresh the stale docstring readings; B-2 pin U9-2's L-3 escape of record text in a refusal (pure and CLI).
- Nits N-1..N-9 (N-1 and N-2 for the architect: policy entries for un-passed images are skipped silently, and `always` field types are unchecked). Next: tester adds the pins (with mutation controls), then re-review.

## 2026-10-29 — security (U9a audit)
- PASS, no critical/high/medium. L-1 `fetch.json` lstat-then-`open` with no `O_NOFOLLOW`/`O_NONBLOCK`/`fstat` (a swap is followed; a FIFO hangs; `_sha256_of` hangs on a FIFO too); L-2 `reviewed` may carry Markdown link syntax into the section; L-3 `notices --index` uncapped. I-1..I-4 incl. U9b must land item 8 (name == hash on shipped bytes).
- Probes (gates image): every hostile fetch.json, link, listing, notices and argv case refused with one line and no traceback; tamper pins live (`u9a-controls.txt`). Evidence: `u9/u9a-security.md`, `u9/u9a-security-probes.txt`.

## 2026-10-29 — tester (U9a rework 1 RED, O-14)
- `scripts/verify.sh fast`: 72 fails, all in the new rows, for the expected reasons (N-3, I-3, L-1 FIFO/link swap, N-7, L-2, L-3). B-1 and B-2 pins, N-9 and the planned-file link pass from the start, and each has a mutation control (`u9/u9a-r1-red-verify-fast.txt`, `u9/u9a-r1-controls.txt`). Flag: L-2 also refuses `_`/`!` in lock keys (the regexes allow them; none committed today).
- O-14 precision: the L-2 row now treats the lock-key column as a control (`_`/`!` print, backtick/`|` refused); module re-run in gates: 67 tests, 56 fails, all expected (`u9/u9a-r1-red-module-o14p.txt`); test file sha256 ea4b63a4.

## 2026-10-29 developer: U9a rework 1 GREEN
scripts/sbom_check.py only (N-3, I-3, L-1/N-4 shared _open_regular, L-3, N-7, L-2, N-5); fast verify 1270 OK, 8 skips: docs/evidence/platform-sbom/u9/u9a-r1-green-verify-fast.txt
## 2026-10-29 — reviewer (U9a rework 1: APPROVED)
- B-1/B-2 pinned with live mutation controls; O-14 fixes as ruled; 67 names = 48 + 19, hashes match the controls; probes clean. Nits R1-N1..N3 optional (`u9/u9a-review.md` "Rework round 1").
- 2026-10-29 security (U9a rework 1 re-audit): PASS. L-1, L-2 (as ruled O-14), L-3 and I-3 closed: every FIFO, link, device, directory and sparse swap is refused with one line and no hang; Markdown in `reviewed` is refused; deep records return a problem.
- New info I-5 (`notices` reads past the cap if the file grows after fstat) and I-6 (the URL column relies on the lock host check). I-4 is carried to U9b. Evidence: `u9/u9a-security.md` "Rework round 1", `u9/u9a-security-probes.txt`.
