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
- Outcome: psycopg-c on Debian libpq5 15.19-0+deb12u1; ke-app 265 -> 259 MB, bundle tar -2.6%.
- L-13 CLOSED (security).
- A66 re-rated low, re-scoped to auth-audit.
- Rework rounds used: 1 of 5 (B1-B3, M-1).
- Orchestrator verify full PASS 694 s.
- A34 proof at `docs/evidence/platform-sbom/u0/windows-run.txt`.
- Open nits carried: none.

## U1 (PSC-14; detail: archive/platform-sbom-part3.md and part4.md)
- Commit 23e3c9b: ke-app flattened and pip dropped; NOTICE gains the Base of ke-app section (PSC-14).
- Rework rounds used 4 of 5; review APPROVED, security PASS, verify full PASS 721 s.
- Carried: I-1 to U5/U6 (libldap/libsasl2 GPL lines), I-3 to U9 (`app/sources/`); standing rule N1: no merge to main and no operator bundle before U3 and U9 land.

## U2 (committed 98b6d27; detail: archive/platform-sbom-part5.md)
- Commit 98b6d27: syft v1.54.1 pinned by index digest and hardened; `bundle.sh` refuses without it (PSC-20).
- Rework rounds used 0 of 5; review APPROVED, security PASS, verify full PASS 699 s.
- Carried: standing rule (security G5): record provenance BEFORE the first run of a newly pinned image.

## U3 (PSC-13; detail: archive/platform-sbom-part5.md)
- Commit 464fa11: one SPDX SBOM per bundled image in `app/sboms/` (PSC-13).
- Rework rounds used: not recorded in the summary (see archive part5); review APPROVED, security PASS, verify full PASS 856 s.
- Carried: ruling 5 to U5-U7 (jna, javassist Apache-2.0 OR exempt at U6; jaxb-api CDDL branch, maven sources jar at U7; classifier token rule at U5; NOASSERTION to the U4 report). Windows build hosts need jq on PATH, and `jq.exe` needs `-b`.

## U4 (committed 40e2181; detail: archive/platform-sbom-part6.md and part7.md)
- Commit 40e2181: obligations the generator could hide are surfaced (PSC-22).
- Rework rounds used 1 of 5; review APPROVED, security PASS, verify full PASS 896 s.
- Carried: to U5, security L-4, L-5, I-4, review R2 and R3, and a named LicenseRef fixture row.

## U4b (PSC-26, Q67; detail: archive/platform-sbom-part7.md and part8.md)
- Orchestrator rulings: the EXPOSE exemption (the scanner gains a Dockerfile exact-line rule, which security must review); checks in offline_check after drift; the file tree as evidence only; the NOTICE section; labels excluded; installers unchanged; Q68, ke-neo4j not scanned.
- RED: 29 failing, 61 controls, reach PASS.
- GREEN: verify full PASS 990 s; config identical; file tree equal minus products (two jars: the fleet-management and genai plugins); plugin absent from the tar; ke-neo4j unlicensed 27; tar -1.15%.
- Review APPROVED, 0 rework rounds (doc nits N1-N3 fixed; N6/N7 and cosmetic carried to U5).
- Security PASS, M-3 closed (L-1, I-2 carried to U5).
- A34 Windows proof PASS, including install.ps1 from the bundle (`u4b/windows-run.txt`).
- Orchestrator verify full PASS 995 s; committed c300d88.

## 2026-10-23 — orchestrator (pushed; human rulings Q69, Q70)
- U4b committed c300d88. Human approved push: `agent/platform-sbom` pushed, DRAFT PR #14
  (do not merge before U9, rule N1); its pull_request CI run is the first Linux
  classic-store run of the base `docker save name:tag@digest` and the sbom tmpfs mode.
- Human: Q69 GCC runtime SOURCE ships (U7, deb kind, no exemption); Q70 no scanning of
  the other bundled images for now. Analyst records both (uncommitted; ride with U5).
- Next: watch PR #14 CI; then U5 (classifier). Brief: docs/handoffs/NEXT-SESSION.md.

## U5 (PSC-15 classifier; in progress)
- CI for PR #14 run 40046377958: PASS, verify job 32m32s (feeds U11/Q62). Rulings: see design-notes N8 amendment U5.

## 2026-10-24 — architect (U5)
- Recorded orchestrator rulings 1-7 as "N8 amendment, U5" in `docs/evidence/platform-sbom/design-notes.md` l.940-1066 (append only; N8/N8a untouched). It fixes the API (`licence_input`, `is_gpl_id`, `needs_source`, `classify_package`, `classify_document(image, doc, always)`) and lists the first failing tests.
- Precision added: a separate classifier "missing" predicate (`_missing`/report unchanged); `needs` = any() over joined parts; WITH/AND/OR precedence; leaf = run of non-space non-paren chars; tar hard-link size 0, so normalise both listings; anchored `$` regexes only get `fullmatch`.
- Open for the orchestrator: unparseable text holding a hash id (`Public Domain OR <hash>`) still needs no source under the "iff gpl" ruling (it is only listed); not ruled: review R3 (stale controls anchor), the heredoc half of I-2, and the offline_check `drift_work` comment.
- Next: tester RED (classifier table in `fast`; smoke item 6 needs `full`).

## 2026-10-24 — tester (U5 RED)
- RED: `scripts/verify.sh fast`: 900 ran; 30 methods fail, all U5 (138 incl. subtests); 0 errors; sentinel ok (`u5/red-verify-fast.txt`).
- Reach: targets overlaid, verify fast PASS, 900 ran OK, sentinel ok; repo files restored (`u5/target-reach-verify-fast.txt`). Targets for the developer to copy: `u5/target-sbom_check.py`, `target-hardcoded_scan.py`, `target-smoke.sh`, `target-offline_check.sh`.
- Controls: `u5/u5_controls.py`, 66 rows (58 must fail, 8 must pass), 0 unexpected (`u5/red-mutants.txt`; run in the gates image).
  (Other bullets: archive/platform-sbom-part9.md.)

## 2026-10-24 — developer (U5 GREEN)
- Targets copied unchanged (`scripts/sbom_check.py`, `tests/hardcoded_scan.py`, `scripts/smoke.sh`, `scripts/offline_check.sh`); not committed. Rest: archive/platform-sbom-part9.md.
- Verify: `scripts/verify.sh fast` PASS (900 ran, OK skipped=8); `scripts/verify.sh full` PASS (1008 s; 900 + 15 integration). Evidence: `u5/green-verify-fast.txt`, `u5/green-verify-full.txt` (redacted).
- Controls `--base repo`: 66 rows, 58 must-fail, 8 must-pass, 0 unexpected (`u5/green-controls.txt`).

## 2026-10-24 — reviewer (U5)
- CHANGES REQUESTED: B1-B3, nits N1-N8.
- Detail: archive/platform-sbom-part9.md; evidence u5/review.md

## 2026-10-24 — security (U5)
- PASS: L-4/L-5/I-2/L-1 closed; new lows L-1..L-4, L-5a.
- Detail: archive/platform-sbom-part9.md; evidence u5/security.md

## 2026-10-24 — tester (U5 rework r1 RED)
- r1 RED: 11 failing, reach PASS, controls 103 (0 unexpected).
- Ruling 6 correction: my U5 RED note "one mutant is equivalent" was wrong, as review B1 showed; B1's rows killed the joined-text mutant. Under ruling 1 the B1 rows alone no longer kill it (the joined text does not parse and its NOASSERTION run now counts), so `test_each_part_is_classified_alone` pins per-part elections beside a junk part (`MIT OR GPL-2.0-only` + `Public Domain`: no source, unparsed).
- Detail: archive/platform-sbom-part9.md; evidence u5/r1-red-verify-fast.txt, u5/r1-target-reach-verify-fast.txt, u5/r1-red-mutants.txt

## 2026-10-24 — developer (U5 rework r1 GREEN)
- r1 GREEN: verify fast + full PASS 1033 s; controls 0 unexpected.
- Detail: archive/platform-sbom-part9.md; evidence u5/r1-green-verify-fast.txt, u5/r1-green-verify-full.txt, u5/r1-green-controls.txt

## 2026-10-24 — security (U5 rework r1)
- PASS: L-1..L-5a closed, no new finding.
- Detail: archive/platform-sbom-part9.md; evidence u5/security-r1.md

## 2026-10-24 — reviewer (U5 rework r1)
- CHANGES REQUESTED: B1-B3 closed; new R1-B1 leaf charset fail-open; nits R1-N1/N2.
- Detail: archive/platform-sbom-part9.md; evidence u5/review-r1.md

## 2026-10-24 — tester (U5 rework r2 RED)
- r2 RED: 5 failing, reach PASS, controls 123 (0 unexpected).
- Detail: archive/platform-sbom-part9.md; evidence u5/r2-red-verify-fast.txt, u5/r2-target-reach-verify-fast.txt, u5/r2-red-mutants.txt

## 2026-10-24 — developer (U5 rework r2 GREEN)
- r2 GREEN: verify fast + full PASS 969 s.
- Detail: archive/platform-sbom-part9.md; evidence u5/r2-green-verify-fast.txt, u5/r2-green-verify-full.txt, u5/r2-green-controls.txt

## 2026-10-24 — security (U5 rework r2)
- PASS: R1-B1 closed; new low R2-L1.
- Detail: archive/platform-sbom-part9.md; evidence u5/security-r2.md, u5/security-r2-probes.txt

## 2026-10-24 — reviewer (U5 rework r2)
- CHANGES REQUESTED: R1-B1/N1/N2 closed; new R2-B1/R2-B2 `+` suffix and `:`/`+` joiners hide an unknown id.
- Detail: archive/platform-sbom-part9.md; evidence u5/review-r2.md, u5/reviewer-r2-controls.txt, u5/reviewer-r2-probes.txt

## 2026-10-25 — tester (U5 rework r3 RED)
- Asked: round-3 RED for review R2-B1/B2 and security R2-L1 (orchestrator rulings 1-5).
- Tests: `tests/test_sbom_classifier.py` gains `ReworkR3DecoratedIdsTest` (4 methods) and `ReworkR3RunSplitTest` (1), with all the ruled rows. The file stays ASCII.
- RED: `scripts/verify.sh fast`, 926 ran. 3 methods fail (20 incl. subtests): trimmed unknown leaves, a hash anywhere in a leaf, joiners split runs. 0 errors, sentinel ok (`u5/r3-red-verify-fast.txt`). Guards, green on r2: the near-misses and 65-hex rows, and the junk 65-hex row.
- Reach: r3 target overlaid, verify fast PASS, 926 OK; repo restored (`u5/r3-target-reach-verify-fast.txt`). Target: `u5/r3-target-sbom_check.py` (only `scripts/sbom_check.py`). The real-row snapshot is unchanged, checked row by row against r2.
- Controls: `u5/r3_controls.py`, which supersedes r2_controls.py. 135 rows (118 must fail, 17 must pass), 0 unexpected, gates image. Full output: `u5/r3-red-mutants.txt`.
  - Mutants asked for: the round-2 `RUN_SPLIT_RE`, no `+` trim, no trim, and fullmatch instead of search.
  - Also: trailing-only trim, 65 hex counted as a hash, and NONE as a substring of the bare id.
- Flag (rulings 3 vs 4): `HASH_ID_RE.search` alone finds a 64-hex hash inside a 65-hex string. The target uses a separate `HASH_IN_RE` with a `(?![0-9a-f])` lookahead for leaves and runs, so a 65-hex leaf stays ordinary (ruling 4); `HASH_ID_RE` itself is unchanged (the U4 report).
  - Read as "unchanged", the round-0 whole-text `HASH_ID_RE.search` over unparseable text still counts a 65-hex id there. That is pinned as `test_hash_search_in_unparseable_text_unchanged` (`Public Domain <65 hex>` needs source); without it, the "junk hash ignored" mutant survived.
  - Orchestrator: confirm, or rule that junk uses the lookahead too.
- Unparsed is pinned only where the text cannot parse. Decorated idstring leaves (`NOASSERTION+`, `<hash>.x`) are left open.
- Next: developer GREEN (copy the r3 target or equivalent), loop `fast`; then re-review and security re-check.

## 2026-10-24 — developer (U5 rework r3 GREEN)
- Asked: round-3 GREEN for review R2-B1/B2, security R2-L1 (design-notes "Rework round 3"). Only `scripts/sbom_check.py` changed: copied `u5/r3-target-sbom_check.py`; diff against the r2 target read, no refactor (`RUN_SPLIT_RE` = `[^A-Za-z0-9.-]+`, `HASH_IN_RE`, `_unknown_id` trims `.-+` after the DocumentRef strip). `unlicensed_report`/`_missing`/`HASH_ID_RE` untouched.
- `scripts/verify.sh fast`: PASS (`u5/r3-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u5/r3-green-verify-full.txt`). Controls: `u5/r3-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

## 2026-10-25 — security (U5 rework r3)
- Asked: re-check round 3 (`RUN_SPLIT_RE` `[^A-Za-z0-9.-]+`, `HASH_IN_RE`, trimmed bare id; design-notes "Rework round 3"). Verdict: **PASS** (no critical/high/medium; no new finding). Detail: `u5/security-r3.md`; probes `u5/security-r3-probes.txt` (script `u5/security_r3_probes.py`).
- Closed: R2-L1 (`<hash>+`, `MIT WITH <hash>+`, `<hash>.x`, `x<hash>`, `NOASSERTION.`, `NOASSERTION+`, `-NONE`: need source, unidentified; 65 hex stays ordinary) and I-7 (lower-case/double/empty DocumentRef prefix with NONE, `NONE:`). Review R2-B1/B2 inputs (`MIT:NOASSERTION`, `MIT+NOASSERTION`, `DocumentRef-x:NONE+`) need source.
- Not weaker than r2: 150000 random expressions, 0 regressions, 0 lost listings; 1015 real rows unchanged; `unlicensed_report` and `HASH_ID_RE` identical to HEAD, six fixtures equal; no ReDoS (worst 0.14 s); r3 evidence clean.
- Info only: I-9 `NONE.NONE`, pinned `MIT-NOASSERTION`/`LicenseRef-NONE`, uppercase-hex hash (U4 I-4) stay ordinary. Next: nothing from security for U5.

## 2026-10-25 — reviewer (U5 rework r3)
- Asked: re-check rework round 3 (rulings design-notes l.1149-1171). Verdict: **APPROVED**. Detail: `u5/review-r3.md`.
- Closed: R2-B1 (`+` and `.`/`-` trim, hash anywhere in a leaf), R2-B2 (`:`/`+` split runs), security R2-L1. Every round-2 input now needs source and is unidentified. The pinned near-misses are unchanged.
- Real rows: `classify_document` is identical row by row to r1 and to r2 on all six fixtures. The U4 report block, `MISSING` and `HASH_ID_RE` are byte-identical to HEAD. r3 controls re-run: 135/118/17, 0 unexpected (`u5/reviewer-r3-controls.txt`). Host classifier tests: 52 OK.
- Not blocking: I-r3-1. Opaque idstrings with a joined keyword stay ordinary: `NOASSERTION.NONE`, `NOASSERTION-2.0`, `LicenseRef-NOASSERTION`. This is the same shape as ruled-ordinary `MIT-NOASSERTION`. There is no caller until U9 and no real row has the shape. If wanted, it becomes U6's first test row.
- I-r3-2: upper-hex hash ids stay ordinary (U4 I-4 carried).
- Next: orchestrator commit gate (`verify.sh full`, diff read).

## 2026-10-25 — orchestrator (U5 commit gate)
- Rework rounds used: 3 of 5 (r1 B1-B3 + security L-1..L-5a; r2 R1-B1 leaf charset; r3 R2-B1/B2 `+`/`:` joiners and hash anywhere). Rulings: design-notes N8 amendment U5 l.940-1171.
- Review APPROVED (r3; I-r3-1 keyword joined by `.`/`-` inside a valid id is U6's first test row, ruled boundary), security PASS (r3; no new finding; U4 I-4 upper-hex hash carried, generator digest bump = re-review trigger).
- Orchestrator verify full PASS 999 s (926 unit + 15 integration, sentinel ok; `u5/orchestrator-verify-full.txt`). Diff read: sbom_check.py (4 rounds), smoke.sh, offline_check.sh, hardcoded_scan.py, tests. Sentinel untouched.
- Also rides: Q69/Q70 records (analyst), requirements status line (N7), handoff splits (archive part1/3/5/6/8/9), u4/u4b controls marked superseded.
- No CHANGELOG line for U5 (no user-visible behaviour until U9); the smoke step now walks volumes (L-1). Commit APPROVED. Next: U6 (`hosts` + `exempt`, jna/javassist, security-reviewed; first test row I-r3-1).
