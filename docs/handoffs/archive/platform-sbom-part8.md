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
