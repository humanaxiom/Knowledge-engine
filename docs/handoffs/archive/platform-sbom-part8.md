Plan item platform-sbom, part 8: U4b review, security, marketer, A34 Windows proof and commit gate (live doc: ../platform-sbom.md)

## 2026-10-23 — reviewer (U4b)
- APPROVED, 0 blocking. Dockerfile = N16 exactly; compose/NOTICE/policy/smoke/offline_check/sbom_check per PSC-26 and rulings 1-6; 11 re-targeted tests keep intent; controls re-run `--base repo`: 61 rows, 0 unexpected.
- Nits N1-N7 (README/CHANGELOG lack U4b, NOTICE GenAI wording, SBOM package diff + tree listings not saved, tree omits size, scanner continuation-line edge): `u4b/review.md`.

## 2026-10-23 — marketer (U4b CHANGELOG)
- CHANGELOG `platform-sbom (in progress)` entry: one Changed bullet for the own neo4j image (ke-neo4j, Q67/PSC-26), NOTICE.md described.
- The bullet names the removed `products/` folder: it holds the fleet-management plugin and the GenAI plugin (the Dockerfile removes the whole folder).
- To keep the subsection at 11 lines, the two ke-app Changed bullets (psycopg, pip) were merged into one. No content lost.
- README positioning not touched (documenter owns the README status).
- Next: reviewer or orchestrator judges the CHANGELOG; the U4b commit is already on the branch.

## 2026-10-23 — security (U4b)
- PASS; M-3 closed: no products/, fleet jar or whiteout in any layer of ke-neo4j's saved tar; bundle has 3 first-party + phoenix/postgres/valkey, no neo4j or ke-vendor/neo4j. Tree vs official: 8019 paths equal incl. content sha256; setid, world-writable, owners, USER unset and entrypoint drop to 7474 all as official. Scanner rule exact-line, one file; smoke step injection-safe and fails closed; offline pull by digest, CLAUDE.md holds; NOTICE true.
- Non-blocking: L-1 smoke `find -xdev` skips volumes; I-1 `tree` checks no size/content; I-2 continuation/heredoc line; I-3 "one layer" (2nd is empty); I-4 ArgsEscaped; I-5 NEO4J_PLUGINS fallback. Evidence: u4b/security.md, u4b/security-probes.txt.

## 2026-10-23 — orchestrator (correction)
- The marketer's "U4b CHANGELOG" section says the U4b commit is on the branch: it is
  not. HEAD is 40e2181 (U4); U4b is uncommitted until its commit gate.

## 2026-10-23 — tester (U4b Windows proof)
- A34 PASS (`u4b/windows-run.txt`): build.ps1 builds ke-neo4j; config 13/13 N16 fields equal; launch 7/7 healthy, live neo4j on ke-neo4j with no products/ or fleet file; bundle.sh writes images/ke-neo4j.tar + its SBOM (no neo4j.tar, no ke-vendor/neo4j); NEW install.ps1 section: loads ke-neo4j:bundle-<sha12>, installed stack 7/7 healthy; tree = official minus products/, 0 attribute/owner diffs; teardown leaves nothing; Windows tests 7 OK; verify fast PASS (871). N4 TSV diff and N5 listings: `u4b/windows-*.{tsv,txt}`.
- Findings for review/security: ke-neo4j .Config has `ArgsEscaped=true` (official: absent), outside N16's list and sbom_check's NEO4J_CONFIG_FIELDS; ke-neo4j has 2 rootfs layers (the 2nd is WORKDIR's empty layer, 0 entries), not 1.

## 2026-10-23 — orchestrator (U4b commit gate)
- Review APPROVED (0 rework rounds; doc nits N1-N3 fixed: README, CHANGELOG, NOTICE
  wording; N4/N5 evidence recorded in the A34 run; N6/N7 + cosmetic carried to U5),
  security PASS (M-3 closed; flattened image as safe as official by content hash),
  A34 PASS (incl. install.ps1 from the bundle; SBOM diff = 2 plugin jars + root row).
- Orchestrator verify full PASS 995 s (871 unit + 15 integration; ke-neo4j ok; no
  fleet plugin on build host and offline client; `u4b/orchestrator-verify-full.txt`).
  Diff read. Commit APPROVED: U4b (PSC-26) + this session's README/CHANGELOG/
  requirements-status updates. Next: U5 (classifier; carry list in U4/U4b bullets).

## Closed-unit summaries as they stood 2026-10-26 (moved from the live doc)

### U0 (committed 31bfed4; detail: docs/handoffs/archive/platform-sbom-part2.md)
- Outcome: psycopg-c on Debian libpq5 15.19-0+deb12u1; ke-app 265 -> 259 MB, bundle tar -2.6%.
- L-13 CLOSED (security).
- A66 re-rated low, re-scoped to auth-audit.
- Rework rounds used: 1 of 5 (B1-B3, M-1).
- Orchestrator verify full PASS 694 s.
- A34 proof at `docs/evidence/platform-sbom/u0/windows-run.txt`.
- Open nits carried: none.

### U1 (PSC-14; detail: archive/platform-sbom-part3.md and part4.md)
- Commit 23e3c9b: ke-app flattened and pip dropped; NOTICE gains the Base of ke-app section (PSC-14).
- Rework rounds used 4 of 5; review APPROVED, security PASS, verify full PASS 721 s.
- Carried: I-1 to U5/U6 (libldap/libsasl2 GPL lines), I-3 to U9 (`app/sources/`); standing rule N1: no merge to main and no operator bundle before U3 and U9 land.

### U2 (committed 98b6d27; detail: archive/platform-sbom-part5.md)
- Commit 98b6d27: syft v1.54.1 pinned by index digest and hardened; `bundle.sh` refuses without it (PSC-20).
- Rework rounds used 0 of 5; review APPROVED, security PASS, verify full PASS 699 s.
- Carried: standing rule (security G5): record provenance BEFORE the first run of a newly pinned image.

### U3 (PSC-13; detail: archive/platform-sbom-part5.md)
- Commit 464fa11: one SPDX SBOM per bundled image in `app/sboms/` (PSC-13).
- Rework rounds used: not recorded in the summary (see archive part5); review APPROVED, security PASS, verify full PASS 856 s.
- Carried: ruling 5 to U5-U7 (jna, javassist Apache-2.0 OR exempt at U6; jaxb-api CDDL branch, maven sources jar at U7; classifier token rule at U5; NOASSERTION to the U4 report). Windows build hosts need jq on PATH, and `jq.exe` needs `-b`.

### U4 (committed 40e2181; detail: archive/platform-sbom-part6.md and part7.md)
- Commit 40e2181: obligations the generator could hide are surfaced (PSC-22).
- Rework rounds used 1 of 5; review APPROVED, security PASS, verify full PASS 896 s.
- Carried: to U5, security L-4, L-5, I-4, review R2 and R3, and a named LicenseRef fixture row.

### U4b (PSC-26, Q67; detail: archive/platform-sbom-part7.md and part8.md)
- Orchestrator rulings: the EXPOSE exemption (the scanner gains a Dockerfile exact-line rule, which security must review); checks in offline_check after drift; the file tree as evidence only; the NOTICE section; labels excluded; installers unchanged; Q68, ke-neo4j not scanned.
- RED: 29 failing, 61 controls, reach PASS.
- GREEN: verify full PASS 990 s; config identical; file tree equal minus products (two jars: the fleet-management and genai plugins); plugin absent from the tar; ke-neo4j unlicensed 27; tar -1.15%.
- Review APPROVED, 0 rework rounds (doc nits N1-N3 fixed; N6/N7 and cosmetic carried to U5).
- Security PASS, M-3 closed (L-1, I-2 carried to U5).
- A34 Windows proof PASS, including install.ps1 from the bundle (`u4b/windows-run.txt`).
- Orchestrator verify full PASS 995 s; committed c300d88.

### 2026-10-23 — orchestrator (pushed; human rulings Q69, Q70)
- U4b committed c300d88. Human approved push: `agent/platform-sbom` pushed, DRAFT PR #14
  (do not merge before U9, rule N1); its pull_request CI run is the first Linux
  classic-store run of the base `docker save name:tag@digest` and the sbom tmpfs mode.
- Human: Q69 GCC runtime SOURCE ships (U7, deb kind, no exemption); Q70 no scanning of
  the other bundled images for now. Analyst records both (uncommitted; ride with U5).
- Next: watch PR #14 CI; then U5 (classifier). Brief: docs/handoffs/NEXT-SESSION.md.

### 2026-10-25 — orchestrator (pushed U5-U7c)
- Human approved the push ("Push"). `agent/platform-sbom` pushed c300d88..86f7831 to the draft PR #14 (U5 d8ffa2d, U6 66781a9, U7a 9b1754f, U7b 6d8fa4d, U7c 86f7831). Rule N1 holds: no merge before U9. Its pull_request CI run is the second Linux data point for U11/Q62; check it first next session. U7d still blocked on Q71, Q72 and the CLAUDE.md row.

