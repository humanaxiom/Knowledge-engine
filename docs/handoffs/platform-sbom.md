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

## U7 (source lock; U7a committed 9b1754f; U7b in progress; detail: archive/platform-sbom-part10.md)
- Plan: the architect's split U7a-d; 182 keys = deb 152 / pgdg 3 / apk 19 / neo4j 1 / temurin 1 / maven 1 / pypi 5. The CLAUDE.md row draft is in N5 amendment U7 item 7, for the human at U7d.
- U7a outcome: `lock_needs`, `lock_problems`, `sample_keys`, `lock_text` and `lock-check`; fail-closed URL, path and per-kind binding rules; no lock committed.
- Rework 2 of 5; review APPROVED, security PASS, orchestrator verify full PASS 968 s.
- Rulings: O2 lock-time resolution endpoints are listed in N5 and `hosts` is file URLs only; O3 fresh-image drift stops U7d.
- Open for the human: Q71 PGDG host/kind before U7c.
- Carried: security I-7 operator path in the FAIL line (evidence redaction); U7b confirms the real temurin asset form (exact amendment, never looser); U7d adds `.gitattributes` eol=lf for the lock.
- U7b rework round 1 in progress: rulings design-notes l.1444-1532.

## 2026-10-25 — security (U7b second fetch)
- Neo4j 5.26.32 sha256 `182ae2e5...91e3`, 20907800 B, commit `27f24499...`; Temurin sidecar `573057d0...8234`; hops github.com -> codeload / release-assets.
- Detail: archive/platform-sbom-part10.md; evidence docs/evidence/platform-sbom/sources-provenance.md

## 2026-10-25 — tester (U7b RED)
- U7b RED: 20 failing, reach PASS, controls 62 (0 unexpected), OPENER hook.
- Detail: archive/platform-sbom-part10.md; evidence u7b/red-verify-fast.txt, u7b/target-reach-verify-fast.txt, u7b/red-mutants.txt

## 2026-10-25 — developer (U7b GREEN)
- U7b GREEN: verify fast + full PASS 983 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7b/green-verify-fast.txt, u7b/green-verify-full.txt, u7b/green-controls.txt

## 2026-10-25 — reviewer (U7b)
- CHANGES REQUESTED: B1 body errors/deadline/cap, B2 pending-neo4j from truncated output, N1-N6.
- Detail: archive/platform-sbom-part10.md; evidence u7b/review.md, u7b/reviewer-controls.txt, u7b/reviewer-probes.txt

## 2026-10-25 — security (U7b)
- PASS: M-1 = B2, L-1..L-5, I-1..I-4.
- Detail: archive/platform-sbom-part10.md; evidence u7b/security.md, u7b/security-probes.txt

## 2026-10-25 — tester (U7b Windows proof)
- A34 FAIL on one defect: `sources_lock.sh` lacks `$work/sboms/tmp`; all other checks PASS. O3: fresh ke-neo4j 72 vs 73 Neo4j packages (genai plugin), keys unchanged.
- Detail: archive/platform-sbom-part10.md; evidence u7b/windows-run.txt

## 2026-10-25 — tester (U7b rework r1 RED)
- U7b r1 RED: 25 failing as expected (new classes only), reach PASS (1016 OK), controls 71 rows 0 unexpected; fake docker runs the real resolver for the script happy path.
- KE_IN_GATES accepted (item 13). After GREEN: re-run A34 steps 3 and 4 on Windows.
- Detail: archive/platform-sbom-part10.md; evidence u7b/r1-red-verify-fast.txt, u7b/r1-target-reach-verify-fast.txt, u7b/r1-red-mutants.txt

## 2026-10-25 — developer (U7b rework r1 GREEN)
- Asked: U7b rework r1 GREEN (review B1/B2/N1-N6, security M-1/L-1..L-5, A34 `$work/sboms/tmp`; design-notes "U7b rework round 1"). Copied `u7b/r1-target-sources_resolve.py`, `r1-target-sources_lock.sh`, `r1-target-sbom_check.py` (adds `lock-check --pending-neo4j`, exit 3, `_coverage_misses`, `only_neo4j_misses`) over the scripts; diffs against the U7b GREEN read, no refactor. `mv -f -- "$tmp" docker/sources.lock.json` stays alone on its line. Compose unchanged. `sources_lock.sh` NOT run against the network.
- `scripts/verify.sh fast`: PASS (`u7b/r1-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7b/r1-green-verify-full.txt`). Controls: `u7b/r1-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.
- Controls note (U7b rework r1): `r1-green-controls.txt` reports 71 rows, 25 "unexpected". All 25 are the "U7b GREEN: ... must fail" baseline rows, which read the repo's own scripts as the old U7b GREEN tree (`GREEN_U7B` in `r1_controls.py`); with the repo now at r1 they pass, so they cannot fail. Every target and mutant row is ok. Not a code defect; the tester should confirm or fix the control's baseline (use the saved U7b target files).

## 2026-10-25 — reviewer (U7b rework r1)
- Asked: re-check U7b rework round 1 (rulings l.1444-1563). Verdict: **APPROVED**. Detail: `u7b/review-r1.md`.
- Closed:
  - B1: mid-body timeout, IncompleteRead and ConnectionResetError, plus OPENER InvalidURL and BadStatusLine, now give one FAIL line with the item 4 text and no lock.new.json. The 600 s deadline, the 4 GiB cap before hashing and the catch-all in main are in.
  - B2: `--pending-neo4j` decides on the full list; my 79-problem input gives exit 1, and the end-to-end test keeps the lock byte-identical.
  - N1: port, userinfo, tab, `%` and non-literal https hops are refused.
  - N2-N4, L-2, L-5, I-1, I-3 and the sbom tmp dir.
- The happy-path fake-docker test runs the real resolver and pins step order, chmod 0644, no temp left, `git diff --stat`, and exits 0 and 3.
- r1 controls re-run after the harness fix: 71/66/5, 0 unexpected (`u7b/reviewer-r1-controls.txt`). Probes: `u7b/reviewer-r1-probes.txt`.
- Nits, as U7c first rows:
  - R1-N1: the pypi JSON sdist url (server-supplied) is fetched as a first request, so it is exempt from the path-% rule. `.../packages/33/01/%2e%2e/%2e%2e/<60>/pandas-2.3.3.tar.gz` is requested; the U7a lock check then refuses the entry, so it fails closed.
  - R1-N2: the `six=(...)` literal beside the compose list.
- Next: security re-check; orchestrator commit gate.

## 2026-10-25 — security (U7b rework r1)
- Asked: re-check U7b rework round 1 (pending decided by `lock-check --pending-neo4j`, per-hop URL rules, pypi.org JSON-only, deadline and cap, ResolveError everywhere, 0644, key grammar first). Verdict: **PASS** (no critical/high/medium). Detail: `u7b/security-r1.md`; probes `u7b/security-r1-probes.txt` (fake network plus one loopback server).
- Closed: M-1 (the real-fixture lock without neo4j and pgdg now rc 1, not 3; no grep in step 5), L-1 (port/userinfo/fragment/non-plain path/raw-Location tricks refused on the first URL and every hop; query only on hops to allowed hosts), L-2, L-4, L-5, I-1, I-3. L-3: the cap and the slow-chunk deadline hold.
- New R1-L1 (low): the deadline is checked only between chunks, and the real opener `read(65536)` blocks until 64 KiB: a 1-byte/50 ms drip held one read past 12 s against a 2 s deadline. Use `read1` or a per-read socket timeout = remaining deadline. Listed hosts only; a stalled maintainer run at worst.
- Script: tools first (`tools: docker not on PATH`), six images exactly, trap removes the temp file. r1 evidence clean.

## 2026-10-25 — tester (U7b r1 controls + A34 re-run)
- Controls baseline fixed (saved u7b/target-*): `--base repo` 71 rows, 0 unexpected. A34 steps 3 and 4 PASS on Windows (refusals incl. tools and six images; the script's own SBOM + lock-needs path with sboms/tmp).
- O3: the fresh key set differs (psycopg-binary in, psycopg-c and postgresql-15 out) because ke-app:local here is stale (pre-23e3c9b); rebuild before a real lock run.
- Detail: archive/platform-sbom-part10.md; evidence u7b/r1-green-controls.txt, u7b/windows-run.txt (addendum), u7b/windows-run-r1-attempts.txt

## 2026-10-25 — orchestrator (U7b commit gate)
- Rework rounds used: 1 of 5 (B1 body errors/deadline/byte cap, B2/M-1 pending-neo4j on the full list, hop rules, tools check, trap, six images, pypi.org JSON-only, chmod 0644, error-body limit, key validation, A34 defect `$work/sboms/tmp`). Rulings: design-notes N5 amendment U7 "U7b interface pins" l.1384-1442 and "U7b rework round 1" l.1444-1563.
- Review APPROVED (r1), security PASS (r1), A34 PASS (steps 1-5; 3-4 re-run after r1), controls 71 rows 0 unexpected after the harness baseline fix (saved targets, not the repo).
- Orchestrator verify full PASS 1042 s (1016 unit + 15 integration, sentinel ok; `u7b/orchestrator-verify-full.txt`). Diff read: sources_resolve.py (fetch/stream/hop rules), sources_lock.sh (round-1 diff), compose service, lock-needs. Sentinel untouched. No lock file committed.
- Rulings: KE_IN_GATES accepted (image ENV marker); the second fetch stands for U7b, U7d adds a third fetch from another network path; U7d compares KEY SETS (fresh ke-neo4j 72 vs 73 Neo4j packages is information).
- Carried to U7c first test rows: review R1-N1 (a server-supplied pypi sdist URL is checked by the hop/path rules before streaming), security R1-L1 (deadline enforced within one read: `read1` or per-read socket timeout = remaining deadline), review R1-N2 (the six-image list is a literal beside bundle.sh's).
- Notes: the host's `ke-app:local` is stale (built 2026-10-20, carries psycopg-binary): U7d runs build.sh first. The tester's A34 driver bug caused 3 unintended real-network resolver runs (maven jar + Neo4j tarball fetched, then failed closed at pypi psycopg-binary; nothing written; `u7b/windows-run-r1-attempts.txt`).
- Commit APPROVED (`git add --chmod=+x` for the two new scripts). Next: U7c (deb/apk routes against a fake network; pgdg waits for Q71).
