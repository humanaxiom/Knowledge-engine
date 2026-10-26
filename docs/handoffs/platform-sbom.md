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

## U5 (PSC-15 classifier; committed d8ffa2d; detail: archive/platform-sbom-part9.md)
- Outcome: pure classifier functions in `scripts/sbom_check.py`, fail-closed rules (N8 amendment U5, design-notes l.940-1171); also escaping, tree size, scanner continuation lines and the smoke prune.
- Rework rounds 3 of 5: r1 B1-B3 + security lows, r2 leaf charset, r3 joiners/hash anywhere.
- Review APPROVED r3, security PASS r3, orchestrator verify full PASS 999 s. CI run 40046377958 PASS 32m32s (feeds U11/Q62).
- Carried to U6: I-r3-1 segment rule (first test row); security I-4 upper-hex hash (generator digest bump = re-review).
- Watch at U11: review N8 smoke flake risk.
- No CHANGELOG line until U9.

## U6 (hosts + exempt; committed 66781a9; detail: archive/platform-sbom-part9.md)
- Outcome: `hosts` holds the nine N4 hosts; `exempt` holds jna and javassist (reviewed `security 2026-10-25`); `exempt_matches`, `classify_document` exempt and the segment rule landed. PSC-22 amended: `always` overrides only the classifier, and an exact-version exempt entry still clears.
- Rework 0 of 5; review APPROVED, security PASS + exempt review PASS, orchestrator verify full PASS 962 s.
- Rulings: libffi notice goes to the ke-neo4j NOTICE section at U9; a base-image digest bump re-triggers the exempt review.
- First test rows carried to U7: a future `reviewed` date is rejected; a `#subpath` purl row.
- First test rows carried to U9: an exempt entry matching more than one package is a problem; `index` runs `validate` first.
- Also U9: drop the "no row both always and exempt" assertion when the first such entry lands; list "always, cleared by exemption".

## U7 (source lock; U7a 9b1754f, U7b 6d8fa4d committed; U7c in progress; detail: archive/platform-sbom-part10.md)
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
- U7c rework round 1 in progress: rulings design-notes l.1894-1946+.

## 2026-10-25 — architect (U7c)
- U7c precision D1-D7/A1-A5, R-1 stream distfiles, R-2 compose as source, gap rulings 1-5, two U7a apk rule changes.
- Detail: archive/platform-sbom-part10.md; evidence design-notes U7c precision l.1565-1789, gap rulings l.1806-1892

## 2026-10-25 — tester (U7c RED)
- U7c RED: 19 failing, reach PASS, controls 79 (0 unexpected).
- Detail: archive/platform-sbom-part10.md; evidence u7c/red-verify-fast.txt, u7c/target-reach-verify-fast.txt, u7c/red-mutants.txt

## 2026-10-25 — developer (U7c GREEN)
- U7c GREEN: verify fast + full PASS 1003 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7c/green-verify-fast.txt, u7c/green-verify-full.txt, u7c/green-controls.txt

## 2026-10-25 — reviewer (U7c)
- CHANGES REQUESTED: B1 APKBUILD from a subdirectory, N1 duplicate deb822 fields, N2 first-assignment APKBUILD, N3 U8 name checks.
- Detail: archive/platform-sbom-part10.md; evidence u7c/review.md, u7c/reviewer-controls.txt, u7c/reviewer-probes.txt

## 2026-10-25 — security (U7c)
- PASS: L-1 = B1, L-2 parse_dsc separators/duplicates, L-3 listing truncation, I-1 tree path encoding.
- Detail: archive/platform-sbom-part10.md; evidence u7c/security.md, u7c/security-probes.txt

## 2026-10-25 — tester (U7c Windows proof)
- A34 FAIL on the real Alpine component: GitLab raw endpoint behind a bot challenge; steps 3-4 and the real deb PASS.
- Detail: archive/platform-sbom-part10.md; evidence u7c/windows-run.txt

## 2026-10-25 — tester (U7c rework r1 RED)
- r1 RED: 39 failing, reach PASS, controls 34 (0 unexpected), item 9 apk API raw URL form.
- Detail: archive/platform-sbom-part10.md; evidence u7c/r1-red-verify-fast.txt, u7c/r1-target-reach-verify-fast.txt, u7c/r1-red-mutants.txt

## 2026-10-25 — developer (U7c rework r1 GREEN)
- U7c r1 GREEN: verify fast + full PASS 1004 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7c/r1-green-verify-fast.txt, u7c/r1-green-verify-full.txt, u7c/r1-green-controls.txt

## 2026-10-25 — tester (U7c r1 Windows re-run)
- r1 Windows re-run PASS: pax-utils resolves on the API form in 5.2 s, bash byte-identical, snapshot 503/31 s observed.
- Detail: archive/platform-sbom-part10.md; evidence u7c/windows-run.txt (addendum)

## 2026-10-25 — reviewer (U7c rework r1)
- Asked: re-check U7c rework round 1 (rulings l.1894-1984) and item 9 (l.1986-2105). Verdict: **APPROVED**. Detail: `u7c/review-r1.md`.
- Closed:
  - B1: the APKBUILD path is pinned on both the lock and resolver side.
  - N1: duplicate fields fail, case-insensitively.
  - N2: repeated top-level pkgver, pkgrel or sha512sums assignments fail.
  - L-2: CRLF is folded and every other control or separator character fails.
  - L-3: a full page needs an empty `x-next-page`.
  - I-1: the tree path is encoded.
- Item 9 is a rule change, not a loosening: the exact API raw form, ref = commit, canonical `<P>`, the decoded path rules, the query and `%` exempt only for apk on that shape, and `/-/raw/` refused.
- Challenge rows: a 307 to a plain path then 418 gives the HTTP 418 line; a 307 that keeps the `%2F` path is refused by the hop rules. Both give one FAIL line and write nothing.
- r1 controls re-run: 34/29/5, 0 unexpected (`u7c/reviewer-r1-controls.txt`). Probes: `u7c/reviewer-r1-probes.txt`.
- Nits:
  - R1-N1: the decoded middle segments of `<P>` accept any printable character (`..;`, `a?b`, `x&ref=0`); harmless on the wire, but looser than the resolver's safe_name. Suggest the lock name rule per segment.
  - R1-N2: `parse_dsc` drops the continuation lines after a junk line; U8 N3 reuses the parser. Suggest refusing a non-field line.
- Next: security re-check; orchestrator commit gate.

## 2026-10-25 — security (U7c rework r1)
- PASS: L-1/L-2/L-3/I-1 closed, item 9 holds, I-5 real nonce in a test -> U7d hygiene row.
- Detail: archive/platform-sbom-part10.md; evidence u7c/security-r1.md, u7c/security-r1-probes.txt

## 2026-10-25 — orchestrator (U7c commit gate)
- Rework rounds used: 1 of 5 (B1 APKBUILD path, N1/N2 parser strictness, security L-2/L-3/I-1, item 9: GitLab raw endpoint behind a bot challenge -> apk URLs move to the API raw form `.../repository/files/<P>/raw?ref=<commit>`, old form refused). Rulings: design-notes N5 amendment U7 "U7c precision" l.1565-1804, "gap rulings" l.1806-1892, "rework round 1" l.1894-2105.
- Review APPROVED (r1), security PASS (r1), A34 PASS (r1 Windows re-run: real `apk:pax-utils@1.3.8-r2` resolves on the API form in 5.2 s and passes lock-check; real `deb:bash@5.2.15-2` byte-identical across runs), controls 34 rows 0 unexpected.
- Orchestrator verify full PASS 1004 s (1047 unit + 15 integration, sentinel ok; `u7c/orchestrator-verify-full.txt`). Diff read: deb/apk routes, parse_dsc, `_apk_api_shape`/`_apk_api_problem`, lock-needs apk route, sources_lock.sh `--tar` for every image. Sentinel untouched. No lock file committed (U7d).
- Carried to U7d first rows: reviewer R1-N1 (decoded `<P>` middle segments held to the file-name rule), R1-N2 (a non-field `.dsc` line fails), security I-5 (replace the real challenge nonce in tests/test_sources_resolve.py with a synthetic value), security I-6/I-7 noted.
- Observed for U7d (for the human): snapshot.debian.org returned a 503 once and took 31 s once; a full run makes ~304 snapshot requests with no retry (Q61), so one transient error aborts the run fail-closed. The analyst drafts Q72 (resume-from-partial vs a bounded retry exception). Also for the human: Q71 (PGDG host) gates the committed lock; the CLAUDE.md "Generated artifacts" row (draft in N5 amendment U7 item 7).
- Commit APPROVED. Next: U7d needs Q71 and Q72 ruled, a fresh `scripts/build.sh`, the real full run, the committed lock + security review + third fetch, `.gitattributes` eol=lf, the CLAUDE.md row.
