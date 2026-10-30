# Handoff: platform-sbom

Plan item: `platform-sbom` (PSC-13..PSC-16; ADR to be written). Outcome
metric: neither *drafts a human reviewer has acted on* nor *ratified rules*;
it closes the M-NT1 remainder (no GPL source offer, incomplete SBOM). Branch:
`agent/platform-sbom`, cut from main at `737750d` (PR #13 merged).

## 2026-10-22 — orchestrator
- Asked to: open `platform-sbom` (the human said proceed, 2026-10-22).
- Criteria already drafted: `docs/requirements.md` `## Item: platform-sbom`
  (PSC-13 SBOM per image, PSC-14 ke-app notices, PSC-15 GPL source archive,
  PSC-16 CI cost and disk). TDD order PSC-14 -> PSC-13 -> PSC-15 -> PSC-16.
- Opener detail: archive/platform-sbom-part1.md

## Plan phase (detail: docs/handoffs/archive/platform-sbom-part1.md)
- 2026-10-22 analyst: criteria PSC-13..16 confirmed against code; drift fixed (uv gone from ke-app; tar config digest); PSC-19..24 added; Q61-Q63 drafted.
- 2026-10-22 orchestrator, human rulings: Q61 fail closed on a failed or mismatched source fetch (human); Q62 Q60's 3-min CI trigger applies, over 180 s goes to the human (human); Q63 reduced verify set, full set for operator bundles (human).
- 2026-10-22 architect: ADR-KE-016 is at `docs/architecture.md`; detail in `docs/evidence/platform-sbom/design-notes.md` (N0 is U0). Units:
  - U0 PSC-25 psycopg built against Debian libpq (full, A34)
  - U1 PSC-14 ke-app notices (fast)
  - U2 PSC-20 pinned SBOM generator (full, A34)
  - U3 PSC-13 SBOM per image (full)
  - U4 PSC-22 obligations not hidden / drift (full)
  - U5 licence classifier (fast)
  - U6 source policy (fast)
  - U7 generated source lock (full)
  - U8 PSC-23 fetch + CLAUDE.md wording (full, A34)
  - U9 PSC-15/24 source archive and manifest (full; A34 if install.ps1 changes)
  - U10 PSC-19 e2e + `/install` sizing (full, A34)
  - U11 PSC-16 CI cost on CI plus full recorded run
  - U12 PSC-21 per-arch
- Further plan-phase rulings and the final U0 test list: archive/platform-sbom-part1.md

## U0 (committed 31bfed4; detail: docs/handoffs/archive/platform-sbom-part2.md)
- Outcome: psycopg-c built against Debian libpq5; ke-app 265 -> 259 MB. Rework 1 of 5; verify full PASS 694 s.

## U1 (PSC-14; committed 23e3c9b; detail: archive/platform-sbom-part3.md and part4.md)
- Outcome: ke-app flattened and pip dropped; NOTICE gains the Base of ke-app section. Rework 4 of 5; verify full PASS 721 s.
- Still carried: I-3 to U9 (`app/sources/`); standing rule N1: no merge to main and no operator bundle before U9.

## U2 (PSC-20; committed 98b6d27; detail: archive/platform-sbom-part5.md)
- Outcome: syft v1.54.1 pinned by index digest and hardened; `bundle.sh` refuses without it. Rework 0 of 5; verify full PASS 699 s.

## U3 (PSC-13; committed 464fa11; detail: archive/platform-sbom-part5.md)
- Outcome: one SPDX SBOM per bundled image in `app/sboms/`. Rework not recorded in the summary; verify full PASS 856 s.

## U4 (PSC-22; committed 40e2181; detail: archive/platform-sbom-part6.md and part7.md)
- Outcome: obligations the generator could hide are surfaced. Rework 1 of 5; verify full PASS 896 s.

## U4b (PSC-26, Q67; committed c300d88; detail: archive/platform-sbom-part7.md and part8.md)
- Outcome: our own ke-neo4j image without the fleet-management and genai plugins; EXPOSE exemption added to the scanner. Rework 0 of 5; verify full PASS 995 s.

## 2026-10-23 — orchestrator (pushed; human rulings Q69, Q70; detail: archive/platform-sbom-part8.md)
- U4b pushed as DRAFT PR #14 (no merge before U9); Q69 GCC runtime source ships (U7); Q70 no scanning of the other bundled images.

## U5 (PSC-15 classifier; committed d8ffa2d; detail: archive/platform-sbom-part9.md)
- Outcome: pure fail-closed classifier functions in `scripts/sbom_check.py` (N8 amendment U5). Rework 3 of 5; verify full PASS 999 s; CI run 40046377958 PASS 32m32s (feeds U11/Q62). Still carried: security I-4 upper-hex hash (generator digest bump = re-review); watch review N8 smoke flake at U11; no CHANGELOG line until U9.

## U6 (hosts + exempt; committed 66781a9; detail: archive/platform-sbom-part9.md)
- Outcome: `hosts` (nine N4 hosts) and `exempt` (jna, javassist; reviewed `security 2026-10-25`) landed with `exempt_matches` and the segment rule. Rework 0 of 5; verify full PASS 962 s. Still carried to U9: libffi notice in the ke-neo4j NOTICE section; an exempt entry matching more than one package is a problem; `index` runs `validate` first; drop the "no row both always and exempt" assertion and list "always, cleared by exemption"; a base-image digest bump re-triggers the exempt review.

## U7 (source lock; U7a 9b1754f, U7b 6d8fa4d, U7c 86f7831 committed, U7d 45411ae WIP, U7e gate passed (commit in progress); detail: archive/platform-sbom-part10.md and part11.md)
- Plan: the architect's split U7a-d; 182 keys = deb 152 / pgdg 3 / apk 19 / neo4j 1 / temurin 1 / maven 1 / pypi 5. The CLAUDE.md row draft is in N5 amendment U7 item 7, for the human at U7d.
- U7a outcome: `lock_needs`, `lock_problems`, `sample_keys`, `lock_text` and `lock-check`; fail-closed URL, path and per-kind binding rules; no lock committed.
- Rework 2 of 5; review APPROVED, security PASS, orchestrator verify full PASS 968 s.
- Rulings: O2 lock-time resolution endpoints are listed in N5 and `hosts` is file URLs only; O3 fresh-image drift stops U7d.
- Open for the human: Q71 PGDG host/kind before U7c.
- Carried: security I-7 operator path in the FAIL line (evidence redaction); U7b confirms the real temurin asset form (exact amendment, never looser); U7d adds `.gitattributes` eol=lf for the lock.
- U7b outcome: `sources_resolve.py` for neo4j/temurin/pypi/maven (hop-by-hop https, deadline and cap, fail-closed lines); `sources_lock.sh` maintainer tool; `sources-resolve` service; `lock-needs`; `lock-check --pending-neo4j`. Provenance recorded: Neo4j sha256 `182ae2e5...91e3`, commit `27f24499...`.
- U7b rework 1 of 5; review APPROVED, security PASS, A34 PASS, verify full PASS 1042 s.
- U7b rulings: KE_IN_GATES accepted; second fetch stands, U7d adds a third fetch from another network; U7d compares key sets.
- Carried to U7c first test rows: server-supplied URLs pass the hop rules; deadline within one read; six-image list derived.
- Notes: host `ke-app:local` is stale, so U7d runs build.sh first; a tester driver bug caused 3 unintended real-network resolver runs, all failed closed, nothing written.
- U7c outcome: deb route via the snapshot `.dsc`; apk route via the GitLab API raw form after the raw endpoint's bot challenge; strict deb822 and APKBUILD parsers; every aports file locked, distfiles streamed. Real `bash` and `pax-utils` resolve on Windows.
- U7c rework 1 of 5; review APPROVED, security PASS, A34 PASS, verify full PASS 1004 s.
- U7c rulings: R-1 stream distfiles; R-2 compose as source; gap rulings; item 9 URL form; two U7a apk rule changes.
- Carried to U7d first rows: R1-N1 middle segments, R1-N2 non-field `.dsc` line, I-5 synthetic nonce.
- U7d: Q71/Q72 ruled by the human 2026-10-25; CI run 40244299450 on 86f7831 PASS (verify 23 min); see the U7d block below.

## U7d (source lock real run; gate passed 2026-10-26; committed 45411ae as WIP; detail: archive/platform-sbom-part11.md)
- Outcome: pgdg route via the apt-archive InRelease-bound Sources; bounded retry 3x (10/30/60 s) on 5xx and timeouts plus a run budget (20 / 3 h); real-data rules: aports symlink skip, leading `_`, size-0 GitLab apk files, scanner skips the lock. The lock: 182 keys, 872 files, 1.327 GB full, 137 MB sample, 1 manual neo4j entry == second fetch. CLAUDE.md row added with the human's approval.
- Gates: review APPROVED, security PASS + gpgv lock review PASS, A34 PASS, controls 0 unexpected, verify full PASS 1018 s (plus a final run after the CLAUDE.md row). Rework 1 of 5.
- Rulings: A71 (pgdg kind + tenth host), A72 (lock-tool retry only), P-R1 (no signature verification in the tool), P-R2 (mid-body timeouts retried), item 14 (third Neo4j fetch deferred to U8's CI sample fetch; the ARM one-liner is still preferred before the first operator bundle).
- Lessons: a change found during a real run goes back through RED; controls baselines come from SAVED copies.
- Forward U8: keep the run's SBOMs in `--evidence-dir`; name checks of `.dsc` Files and APKBUILD sha512sums; cite the CI fetch in sources-provenance.md.
- Forward U11: full operator bundle ~8 GiB staged > 7 GiB floor; CI verify 23 min. Forward U9: the U6 carried rows.


## 2026-10-27 — analyst (plan update U7d)
- requirements.md: new status line (U7d gate passed, next U8); table rows PSC-15/16/22/23 updated; PSC-23 says U8's first CI sample fetch is the third Neo4j fetch (sources-provenance.md). open-questions.md: Q61-Q72 all resolved, plus the third-fetch refinement with the architect's caveat (ARM one-liner still preferred).

## 2026-10-27 — marketer (CHANGELOG U5-U7d)
- CHANGELOG "platform-sbom (in progress)" rewritten to U0-U7d in six bullets (U0-U4b merged in, U5-U7d added); no README change (no operator-facing shift until U9); no evidence file.

## U7e (base bump to python 3.12.16; gate passed 2026-10-28; detail: archive/platform-sbom-part12.md)
- Outcome: all three FROM lines (app builder, app runtime, gates) move to `python:3.12-slim-bookworm@sha256:6dd8b6da...9753`: CPython 3.12.16, openssl/libssl3 3.0.22-1~deb12u2, no libssl pin. CPython licence file headers to 3.12.16, bodies byte-identical. NOTICE updated. Whole ke-app fixture replaced (6 rows changed, each explained by the base dpkg diff). Lock 183 keys: +openssl~u2, +ca-certificates~u2, -ca-certificates~u1; openssl~u1 kept for postgres. Image sizes flat (`u7e/size.md`). CHANGELOG bullet added. PSC-27's drift-check claim withdrawn; the proof is the scan plus the fixture rows.
- Gates: tester RED (`u7e/tester-red-verify-full.txt`), developer GREEN (`developer-verify-full.txt`), tester re-pins (`tester-repin-verify-full.txt`), security PASS with 3 records (`security-review.md`, `base-provenance.md`, `base-dpkg-diff.txt`), reviewer APPROVED after rework 1 of 5 (`review.md`), A34 PASS (`a34-windows-run.txt`, `a34-verify-full.txt`, 1132 s), orchestrator verify full PASS 1162 s on the final tree (`orchestrator-verify-full.txt`; scan green, CVE-2026-84782 absent).
- Rulings: human: base bump ("get the fixed python"); orchestrator: B-2 proof ruling (scan + fixture rows, not a drift check); tester kept ReworkR1 B2 at (79,6).
- Lessons: an inserted test must not split a neighbouring loop (RED's insertion silently dropped a control, caught at re-pin); a count in a test name goes stale.
- Decisions waiting for the human: (1) security M-1: ke-gates' compose 5.6.0 (Go stdlib / x-net Criticals) and uv 0.11.21 (quinn-proto High) are not bundled and have no network; bump the pins as a follow-up item? (2) postgres still ships openssl ~deb12u1, unscanned under Q70. (3) the Neo4j ARM third fetch (U8's CI sample fetch, or the ARM one-liner first).
- Forward: next U8; keep the orchestrator's "record provenance before running" rule. Commit of U7d+U7e on a new draft PR needs the human.

- 2026-10-28 documenter: U7e closed in this file; sections moved verbatim to archive/platform-sbom-part12.md. Status: U7e gate passed, commit in progress, next U8.

## U8a (committed as 3203054) + Q74 (gate passed 2026-10-28; detail: archive/platform-sbom-part13.md)
- Landed: `scripts/sources_fetch.py` (the fetch client: `main`, per-file size/sha256/upstream checks, `.dsc` and APKBUILD name checks, `fetch.json` written last); `download` and `dsc_listing` in `sources_resolve.py` (one attempt, no retries, Q61); `lock_entry_problems`, the shared-sha256 rules (one size, one upstream alg, one value per alg; size-0 exemption from the alg rule) and `fetch_plan` in `sbom_check.py`; `tests/test_sources_fetch.py`; `ci.yml` job timeout 37 -> 69 per A74. Q73 option 2 (CLAUDE.md sentence) lands at U8b.
- Gates: tester RED/GREEN `u8/u8a-red..r2-green-verify-fast.txt` (1140 -> 1157 tests), controls `u8/u8a-controls.txt`; review `u8/u8a-review.md` APPROVED after rework 1 of 5 (2 rounds); security `u8/u8a-security.md` PASS after rounds 1-2 (probes `u8a-security-probes.txt`); Q74 `u8/q74-red-verify-fast.txt`, `q74-green-verify-fast.txt`; orchestrator `u8/orchestrator-verify-full-u8a.txt` PASS 1095 s. Developer full runs were blocked by Docker address pools (`u8a-developer-verify-full.txt`).
- Rulings: A75 (arch from the daemon, no `--evidence-dir`); A76 (completion record last: set, arch, lock sha256; U9 refuses missing/mismatch); O-1 full-set real fetch at U8b; O-2 drop `objects.githubusercontent.com` if unused; O-3 flat `<out>/<sha256>` layout; M-2 and L-6 as lock rules (N4 am. U8 item 1, PSC-23 U8-3); A73 Q73 option 2; A74 Q74 timeout 69, the human's "69 seconds" read as minutes (the human may correct). Q74 profile: the suite did not grow (~735 s local); CI slowness is the hosted runner (1.24x-2.13x).
- Carried to U8b: script's non-empty `--out` refusal and the trap row for a client exit 1 leaving verified files; stale `fetch.json` (L-3). Open for the human: security M-1 (ke-gates compose/uv pins), postgres openssl under Q70, Neo4j ARM third fetch.
- Next: U8b: `sources-fetch` service in docker-compose.sources.yml, `bundle_fetch.sh`, `offline_check.sh` wiring (replaces only the generator pull), `bundle.sh` header, `sources_lock.sh` SBOM copies, README, the CLAUDE.md sentence per A73, real sample and full-set runs, A34 (full). Then U8c: CI extract and the third Neo4j fetch (provenance record). Not user-visible until U8b: README and CHANGELOG untouched.

## 2026-10-28 — documenter (U8a + Q74 closed)
- Moved the U8a/Q73/Q74 sections (lines 105-187) verbatim to archive/platform-sbom-part13.md; replaced them with the summary block above.
- No README/CHANGELOG change (U8a not user-visible until U8b).

## U8b (committed as 98e465a; gate passed 2026-10-28; detail: archive/platform-sbom-part14.md)
- Landed: `sources-fetch` service in `docker-compose.sources.yml`; `scripts/bundle_fetch.sh` (`--set sample|full --out DIR [--arch]`, fail closed, no retry, trap cleanup); `offline_check.sh` runs it with `--set sample` in place of only the generator pull; `bundle.sh` refusal text and header; `sources_lock.sh` keeps the run's SBOM copies (U8-12); README route-out and operator order; CLAUDE.md sentence per A73; `tests/test_bundle_fetch.py` plus re-pins.
- Gates (all in `docs/evidence/platform-sbom/u8/`): RED `u8b-red-verify-fast.txt`; GREEN `u8b-green-verify-full.txt` (failed only at the gitlab.alpinelinux.org outage); review `u8b-review.md` APPROVED after rework 1 of 5; security `u8b-security.md` PASS (twice); rework `u8b-r1-red-verify-fast.txt`, `u8b-r1-green-verify-fast.txt`; `u8b-r1-green-verify-full.txt` PASS 1113 s with the real sample fetch (`sample-run.txt`); O-1 full set `full-run.txt` PASS (716 files, 1180936586 B, equal to `expected.md`); `size.md`, `hop-hosts.md`; A34 `a34-windows-run.txt` PASS; `orchestrator-verify-full-u8b.txt` PASS 1137 s (2026-10-29, after the outage; attempt 1 `orchestrator-verify-full-u8b-attempt1-outage.txt`).
- Rulings: O-4..O-8; O-2 answered: `objects.githubusercontent.com` is unused, the drop is deferred to U8c as U8-10, a reviewed change.
- Closed: the gitlab.alpinelinux.org outage (~13:50-18:03 UTC) that failed the first full run; Q61 fail-closed by design, no lock edit.
- Carried: reviewer N-1 errno follow-up, N-4, N-6, N-9 (`bundle.sh` `ls -A`, to U9), R1-N1, R1-N2; security I-2..I-7.
- Next: U8c: CI extract of the sample fetch as the third Neo4j fetch evidence in sources-provenance.md; O-2 host drop; then U9.

## 2026-10-28 — documenter (U8b closed)
- Moved the U8b sections (tester RED through the A34 proof and the developer's real runs) verbatim to archive/platform-sbom-part14.md; replaced them with the block above.
- CHANGELOG gains one U8 bullet (assigned once by the orchestrator); README checked against the bundle_fetch.sh header, no drift.
- Follow-up: CHANGELOG intro line now says the source fetch landed at U8 and shipping it with notices and index arrives at U9.

## U8c (part 1 committed as 23bf33e; part 2 committed as ecdd33f; detail: archive/platform-sbom-part15.md)
- Part 1: `objects.githubusercontent.com` dropped from `docker/source-policy.json` `hosts` (nine left; O-2, U8-10). Tester RED, developer GREEN (`verify full` PASS 1107 s, 1201 tests), review APPROVED, security PASS (`u8/u8c-o2-*`).
- Part 2: the third Neo4j fetch, from PR #15 CI run 40907497118 on 5cf025c (GitHub-hosted Azure westus runner, ubuntu-24.04 20261025.353.1): sha256 182ae2e5...91e3, 20907800 B, hops github.com -> codeload.github.com. It equals the lock and the second fetch: three fetches, two networks, agree. Security PASS. Recorded last in `sources-provenance.md`; extract `u8/ci-40907497118-fetch.txt`, log `u8/ci-40907497118.log`.
- Q74 data point (`u8/ci-timing-q74.md`): verify job 32m06s, unit stage 1261 s, offline_check 292 s, under the 69-min timeout.
- Still optional, for the human: the ARM one-liner before the first operator bundle. It does not block U9.

## U9a (committed as fc8bbf8; gate passed 2026-10-29; detail: archive/platform-sbom-part15.md)
- Landed, `scripts/sbom_check.py` only: `fetch_record_problems`, `listing_problems`, `source_index`, `source_section`; the multi-match rule in `exempt_matches`; subcommands `sources-check`, `index`, `notices` (refuse, never escape); the shared `_open_regular` (no FIFO hang, no link or device swap). Install pins (12 tamper rows, sh and ps1) in `tests/test_offline_bundle.py`; new `tests/test_source_index.py` (67 tests). Not wired into `bundle.sh` yet.
- Gates (evidence in `docs/evidence/platform-sbom/u9/`): RED/GREEN `u9a-red-verify-fast.txt`, `u9a-green-verify-fast.txt` (1201 -> 1251 tests, the 88 RED rows green); review `u9a-review.md` CHANGES REQUESTED (B-1, B-2) then APPROVED after rework 1 of 5; security `u9a-security.md` PASS twice (`u9a-security-probes.txt`); controls `u9a-controls.txt`; rework `u9a-r1-red-verify-fast.txt`, `u9a-r1-green-verify-fast.txt` (1270 OK, 8 skips), `u9a-r1-controls.txt`; orchestrator `orchestrator-verify-full-u9a.txt` PASS 1156 s (attempt 1 red at the GitLab outage: `orchestrator-verify-full-u9a-attempt1-outage.txt`).
- Rulings: Q78-Q80 (option 1 each: `--sources` mandatory, recorded full-set bundle at U9, no exempt checksum compare at U9); O-9 (split U9a/U9b), O-10 (removal on failure), O-11 (A34 for U9b), O-12 (7 GiB floor unchanged), O-13 (1)-(8), O-14 and its precision (lock-key `_`/`!` print, backtick and `|` refused).
- Carried to U9b: reviewer N-1, N-2 (architect: un-passed-image policy entries skipped silently; `always` field types unchecked), N-6, N-8, R1-N1..N3; security I-1, I-2, I-4 (closed by item 8: name == hash on shipped bytes), I-5 (`notices` reads past the cap if the file grows), I-6 (URL column relies on the lock host check); the O-10 removal test row.
- Plan pointers: requirements.md l.4391-4727 (U9 precision, U9-1..U9-15); design-notes.md l.4237-4890 ("N9 amendment, U9"); ADR-KE-016 "Amended U9".
- Next: U9b: `bundle.sh --sources` mandatory, `offline_check.sh` flags, NOTICE/libffi (security confirms the libffi text source first, R7), README and header, the real sample in `verify full`, the Q79 full-set bundle, A34. Write `u9/expected.md` before any real run.

## 2026-10-29 — documenter (U8c + U9a handoff closed)
- Moved the U8c part 1/2, analyst/architect U9 and U9a sections (tester through security rework 1) verbatim to archive/platform-sbom-part15.md; replaced them with the two blocks above.
- CHANGELOG gains one U9a bullet; "ten hosts" corrected to nine (U8c part 1).

## 2026-10-29 — analyst (Q81 raised)
- Q81 (open-questions.md l.1173-1305, status l.312), for the human: the sample fetch's dependence on gitlab.alpinelinux.org. Checked: no apk lock key avoids GitLab (every APKBUILD is there), so option 2 does not remove it. Alpine's 2026-10-28 post (CVE-2026-97229) says GitLab is closed to the public, with no reopening date.
- Recommended: option 3, distfiles-only apk files in the verify/CI sample (U9b-adjacent or U10). It also needs a partial-key rule in U9-5 and U9a's `source_index`. Counter-argument recorded: CI loses its early warning on the GitLab API raw route.
- Next: the human rules before U11's CI runs; until then U9b's and the orchestrator's `verify full` runs stay red whenever GitLab is down (Q61).

## U9b (committed as 0396699; gate passed 2026-10-30; detail: archive/platform-sbom-part16.md)
- R7 security PASS (`u9/libffi-provenance.md`). RED: `tests/test_bundle_sources.py` 31 rows + re-pins (201 red, `u9/u9b-red-verify-fast.txt`). GREEN (uncommitted; `git add -N licenses/libffi-jna-5.15.0.txt` only): bundle.sh `--sources`/`--sources-set`, shell refusals, sources-check before the first write, `cp -P` copy, index, notices, app/ copies, manifest name==hash + count + 1 MiB, O-10 trap, N-9, O-15 lines; offline_check flags; NOTICE I-3 + libffi; README. Fast 1302 OK/8 skips (`u9/u9b-green-verify-fast.txt`), full PASS 1273 s (`u9/u9b-green-verify-full.txt`), sample bundle = expected.md (`u9/sample-bundle-run.txt`, `size.md`).
- Q79 full FETCH done (`u9/full-fetch-run.txt`: 716 files, 1180936586 B, rows = u8/full-run.txt), kept in `dist/ke-q79-sources` for the bundle half, which runs after rework.
- Review CHANGES REQUESTED (`u9/u9b-review.md`): B-1 unnormalised paths pass the overlap/symlink guards; B-2 O-15 A2/A3/A4/A8 unpinned; B-3 no signal row/trap pin, no save or app/-copy fault rows, tag/save/app copies exit without a `bundle:` line; N-1..N-11. Security FAIL (`u9/u9b-security.md`, probes): L-4 = B-1 root cause (`mkdir -p` adopts a pre-existing dir that the O-10 cleanup then `rm -rf`s; record overwritten); I-7..I-12 info. libffi file and NOTICE paragraph = R7. Carried: U9a I-1, I-4, U8b N-9 closed; I-2 out of scope; I-5, I-6 open.
- Orchestrator rulings for rework 1: design-notes **O-16** (path rule, plain `mkdir`, noclobber record, A4 scope, accepted N-items, deferrals).
- Rework 1 (O-16): tester RED 12 rows + O-15 pins, 19 controls (`u9/u9b-r1-red-verify-fast.txt`, `u9b-r1-controls.txt`; O-16 precision (a) N-7 at `stage index`, (b) `--sources //` exit 2). Developer GREEN: path rule (`segment_bad`, all trailing slashes), `mkdir --` claim, noclobber record, named tag/save/app-copy failures, manifest `stage_die`, N-1/N-2/N-4/N-5/N-9; fast Ran 1322 OK/8 skips, full PASS 1422 s (`u9b-r1-green-verify-fast.txt`, `-full.txt`). Q79 full-set bundle PASS (`u9/full-bundle-run.txt`, `size.md`): 716 files, 183/0 shipped, MANIFEST 111025 B/764 lines, bundle 2147272340 B (965441167 B without sources), wall 2m38 s; `dist/ke-q79-sources` kept for A34.
- Rework-1 verdicts: security PASS (`u9/u9b-r1-security.md`; L-4 closed, I-8/I-9/M-3 closed; I-13 medium = reviewer B-1; I-14 low: link to a non-regular file at the record path is written through, cleanup removes the link). Reviewer CHANGES REQUESTED (`u9/u9b-r1-review.md`): new B-1 `created` re-tested at the first write (O-16 (2) not done; a late `--out` dir or dir-link is adopted), B-2 `docs/quickstart.md` l.69/l.78 command now exits 2 (documenter at close); no control for the trailing `..` segment, N-4/N-5; N-2 relative paths from `/` refused (docs), N-3 dead `-ge 1`, N-4 stale jq comment, N-5/N-6 info.
- Orchestrator rulings for rework 2: design-notes **O-17**.
- Rework 2 (O-17): tester RED 4 rows + 3 O-16 controls (`u9/u9b-r2-red-verify-fast.txt`, `u9b-r2-controls.txt`); developer GREEN (`created` decided once, given-`--out` re-check, record `chmod || die` before `record_made=1`, N-3/N-4): fast Ran 1328 OK/8, full PASS 1365 s (`u9b-r2-green-verify-fast.txt`, `-full.txt`). Reviewer APPROVED (`u9/u9b-r2-review.md`; N-7, N-8 optional), security PASS (`u9/u9b-r2-security.md`; I-13, I-14 closed; I-15 = N-8, I-16 = N-7 non-blocking). **O-18** defers I-15/N-8 and I-16/N-7 to U10 (design rows); code final at bundle.sh 9624710b.
- Documenter close (`u9/u9b-docs-verify-fast.txt`, fast Ran 1328 OK): quickstart.md U9 order (B-2), README path rule + ordinary-user sentence + status line (N-2, O-18 (2), N-11), CHANGELOG U9b bullet.
- Gate: A34 PASS (u9/a34-windows-run.txt), Q79 re-run equal (u9/full-bundle-run.txt), orchestrator verify full PASS 1390 s (u9/orchestrator-verify-full-u9b.txt), committed 0396699. Next: U10 (e2e verify, /install sizing, revision label; design rows for the O-18 deferrals I-15/N-8 and I-16/N-7).

## 2026-10-30 — tester (U9b A34 Windows proof R13 + Q79 re-run O-17 (5))
- Q79 re-run on bundle.sh 9624710b: PASS. Every row equals the first run's (716 files/1180936586 B/183 components; index 183 shipped + 2 exempt, 876 rows, lock 12eebc8c; MANIFEST 111025 B/764 lines; bundle 2147272340 B, 965441167 B without sources; --sources unchanged). Only the timings and the per-run manifest digest moved. Section "2026-10-30 rework 2 re-run" in `u9/full-bundle-run.txt`; `size.md` updated.
- A34 (`u9/a34-windows-run.txt`), Git Bash + PowerShell 7.6.9: steps 1-6 PASS. Sample fetch = u8/expected.md (25/136571547 B/7). Sample bundle = expected.md + sample-bundle-run.txt (index 7/176/2; 25 files named by sha256; Source code section + sample warning in both notices; libffi in licenses/ and app/licenses/). install.ps1 + launch: 7/7 healthy, /healthz 200, /readyz ready; teardown. Both refusals are `stage sources-check`, exit 1, nothing written. 0 leftovers at every step.
- Step 7 own `verify full`: FAIL (exit 1, 1053 s; `u9/a34-verify-full.txt`). Unit Ran 1328 OK. One integration failure, `test_gates_it_cannot_read_repo_env`: the orchestrator's concurrent R15 run created a repo-root `.env` at 01:39:56Z, after my run had chosen no mask at 01:36:52Z. This is interference, not U9b. Not re-run (R15 still in flight); R13 cites the developer's PASS (`u9b-r2-green-verify-full.txt`).
- For the orchestrator: (1) my run overlapped your R15 run 01:39:56Z-01:54:25Z (both built ke-*:wt-33a132fbfdd7). (2) A `.env` that appeared between 01:15Z and 01:19Z (owner unknown) was overwritten by my `cp .env.example .env` at 01:22:19Z without a check first. Its content is lost; it then held .env.example + a marker line. Its owner deleted it at about 01:36Z. (3) `ke-*:bundle-1a7a9e276d57` now point at the :local ids, moved by the Q79 run. I did not restore them during R15; the old ids keep their `wt-33a132fbfdd7` tags.
- Not run: build.sh (the dispatch listed (a)-(e)); the :local images have the same Created times as verify's own build of this tree.

## 2026-10-29 developer: U9b committed
- U9b committed locally as 0396699 on agent/platform-sbom, not pushed; this handoff note is after the commit and stays uncommitted.
