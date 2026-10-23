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
- Settled, not re-opened: Q57 (SPDX 2.3 JSON per bundled image, offline at
  bundle time), Q58 (source offers built now), R4/A43, R7 (stack images
  only), Q48 (hash provenance for new pins and fetched source).
- Known drift to reconcile: PSC-14 names "the `uv` binary" in ke-app's base,
  but platform-supply-chain unit 3 (D10/PSC-17) removed uv from ke-app.
  The ke-app image is now multi-stage; check what the runtime stage holds.
- Open for the human (analyst drafts each with a recommendation):
  1. a failed source fetch: fail closed (as Q56(b) for the scan DB) or not;
  2. whether Q60's 3-min CI cost trigger applies to this item;
  3. whether `verify.sh full` builds the whole source set, given the 7 GiB
     disk floor (R6) and the 9.1 GiB free measured on CI.
- Constraints: CI cost and disk claims are measured on CI only; the floor
  is never lowered to pass; a new pinned tool needs digest + provenance
  (PSC-1 form); A34 Windows proof if Dockerfiles or compose files change;
  every product item ships its own e2e test (human, 2026-10-22), so the
  analyst says whether the SBOM/source bundle needs one here.
- Next role (analyst): confirm or correct the criteria, number any new
  ones PSC-19+, write the three questions into `docs/open-questions.md`
  (next free Q number) with recommendations, append here, log.

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
- 2026-10-22 orchestrator, ADR rulings (human new Q64: psycopg on Debian libpq, no `srpm` kind, adds U0): config digest names the image (analyst amends PSC-13/19); SBOMs, sources, notice copies under `app/`; classifier wider than PSC-15 (AGPL, GPL-1.0, LGPL-2.0) confirmed; neo4j jars decided at U3, back to architect if any; CLAUDE.md wording goes to the human at U8.
- 2026-10-22 analyst (Q64): PSC-25 added, PSC-13/19 use config digest, vendored libs dropped from PSC-14/15/22; Q65 (Windows host lock) and Q66 (libpq 15 vs 16+) opened.
- 2026-10-22 orchestrator, rulings: Q65 (orchestrator) shipped ke-app has no psycopg-binary, lock/dev-host resolution is the architect's, `--locked` kept; Q66 (orchestrator) accept Debian 12 libpq 15, security re-rates `require_auth` at U0 review.
- 2026-10-22 architect (Q64): ADR point 0 (U0) added; Q65/Q66 folded in.
- Final U0 tests (requirements names win):
  - `test_ke_app_resolves_psycopg_c_not_binary` (architect's #1)
  - `test_runtime_stage_has_no_compiler` (architect's #4, was `test_app_runtime_stage_installs_only_libpq5`)
  - `test_pyproject_puts_psycopg_c_in_image_groups_only`
  - `test_app_dockerfile_builds_psycopg_c_on_pinned_libpq`
  - `test_libpq_pin_matches_bookworm_base`
  - `test_gates_psycopg_is_c_impl_on_debian_libpq`
  - `test_smoke_checks_psycopg_c_impl_in_api`
  - `test_notice_psycopg_section_matches_lock`
- Next: tester RED on U0.

## U0 (committed 31bfed4; detail: docs/handoffs/archive/platform-sbom-part2.md)
- Outcome: psycopg-c on Debian libpq5 15.19-0+deb12u1; ke-app 265 -> 259 MB, bundle tar -2.6%.
- L-13 CLOSED (security).
- A66 re-rated low, re-scoped to auth-audit.
- Rework rounds used: 1 of 5 (B1-B3, M-1).
- Orchestrator verify full PASS 694 s.
- A34 proof at `docs/evidence/platform-sbom/u0/windows-run.txt`.
- Open nits carried: none.

## U1 (PSC-14; detail: archive/platform-sbom-part3.md and part4.md)
- Rounds used: 4 of 5.
- Human rulings: pip first kept, then dropped (2026-10-23).
- Outcome: ke-app is flattened (`FROM scratch` + `COPY --from=runtime / /`, amending ADR-KE-013 D10); pip and the ensurepip wheel are gone; image 259 -> 238 MB; tar 58.8 -> 54.9 MB (-6.7%).
- NOTICE: the Base of ke-app section (CPython is Python-2.0, points to LICENSE.txt), the incorporated, HACL* and KaRaMeL licence files, Apache-2.0.txt from the base's base-files, and the L-6 Source code sentence.
- Security confirmed the CPython, HACL* and KaRaMeL files by a second fetch of Python-3.12.15.tar.xz; its sha256 equals the base's PYTHON_SHA256.
- Tests added: `test_ke_app_no_pip.py`, `test_notice_ke_app.py`, the tracked-licence test; four tests re-targeted for the flattened shape; L-12 fixed in `unpinned_bases`.
- A34 proof `u1/windows-run.txt` stands because the Dockerfile is unchanged since it.
- Standing rule N1: no merge to main and no operator bundle before U3 (SBOM) and U9 (Source code section) land.
- Follow-ups: I-5 (.pyc from the pip uninstall), I-7 (optional bundle.sh twin of the tracked-licence check), N14/N16 (nits).
- Carried to later units: I-1 (U5/U6 libldap/libsasl2 GPL lines), I-3 (U9 `app/sources/`).
- Next: U2 (PSC-20 SBOM generator pin, compose, refusal).

## U2 (committed 98b6d27; detail: archive/platform-sbom-part5.md)
- syft v1.54.1 (grype v0.120.1's syft) pinned by index digest sha256:3eb5379b...49b1aa; provenance PASS (unsigned image; signed release checksums verify, amd64/arm64 binaries byte-identical).
- Hardened `sbom` service (`docker-compose.sbom.yml`): no network, read-only root, tmpfs /tmp, cap_drop ALL, no-new-privileges, /in ro, /out the only rw mount, 8 `SYFT_*=false` keys.
- `bundle.sh` refuses before any write if the generator image is absent; it never pulls.
- Interim pull in `offline_check.sh` before `bundle.sh` (fails closed) until U8.
- Rework rounds used: 0 of 5; review APPROVED, security PASS, A34 PASS, verify full PASS 699 s.
- Standing rule (security G5): record provenance BEFORE the first run of a newly pinned image.

## U3 (PSC-13; detail: archive/platform-sbom-part5.md)
- Outcome: one SPDX SBOM per bundled image in `app/sboms/`. Fresh evidence: ke-app 154 packages / 84 GPL-family / 2 unlicensed; neo4j 342. The earlier 700/505 came from a stale pre-U0 image (security M-1, fixed by regeneration).
- `documentNamespace` is `urn:uuid:<uuid4>`, fresh per document (orchestrator ruling b).
- `scripts/sbom_check.py` (validate/finish) checks and finishes each document.
- syft runs as the caller (`KE_SBOM_USER`, `user:` in the compose file).
- Windows-host fixes in `bundle.sh`: `hostpath`/`cygpath -m`, `MSYS_NO_PATHCONV=1`, mkdir then chmod.
- Ruling 5: jna and javassist are Apache-2.0 OR (exempt at U6); jaxb-api takes the CDDL branch (maven sources jar at U7); classifier token rule at U5; NOASSERTION goes to the U4 report; `XDG_CACHE_HOME=/tmp/cache` at U4.
- Review APPROVED (nits N1-N9); security PASS (M-1 fixed; L-1 revision-label check deferred to U10).
- A34 PASS (`u3/windows-run.txt`); verify full PASS 855 s.
- Carry to U4: review N1 (sbom_check.py docstring), N2 (L-13 cite in a bundle.sh comment), N3 (design notes lack hostpath/MSYS), N4 (tests for cygpath/MSYS/chmod), N5/ruling (XDG_CACHE_HOME), N6 (disk floor on TMPDIR, or work dir next to --out), N7 (uv.lock map keyed by name), N9 (stale u3_controls anchors).
- Tester finding (documenter): Windows build hosts need jq on PATH, and jq.exe needs `-b` (CRLF).
- U3 committed 464fa11 (review APPROVED, security PASS, A34 PASS, orchestrator verify full PASS 856 s).

## U4 so far (PSC-22; detail: archive/platform-sbom-part6.md)
- RED: 18 tests failing (all U4), reach PASS. GREEN: targets applied unchanged, verify fast PASS (832), full PASS (923 s); the real drift check passes on the ke-app SBOM.
- Orchestrator rulings, points 1-8: (1) `always` key of docker/source-policy.json arrives at U4; (2) libldap/libsasl2 in ke-app only; (3) the unlicensed report is bundle.sh output (index at U9); (4) the architect confirms the third field (licenseInfoFromFiles); (5) the work dir is beside `--out` (`.ke-sbom.*` in dirname(--out)); (6) offline_check.sh pulls the base by pinned digest before the drift step, fail closed; (7) the base SBOM run inherits the offline project; (8) ADDED_PACKAGES read by AST from tests/test_notice_ke_app.py. No postgres `always` entries.
- Q68 option 3 (orchestrator): ke-neo4j is not scanned in U4b; the scan-all-images follow-up goes to the human, with measured cost.
- Human ruling Q67: build our own neo4j image without the commercial fleet plugin (U4b, PSC-26, design N16).
- Review CHANGES REQUESTED: B1 (XDG_CACHE_HOME inert; add tmpfs `/tmp:mode=1777`), B2 (stale docstring at sbom_check.py l.30), N1-N8.
- Security FAIL: H-1 (59 hash-only `LicenseRef-<64 hex>` rows escape the unlicensed report and N8); M-1 (gcc in `always`), M-2 (jrt-fs), M-3 (neo4j fleet jar, human), L-1 (busybox/apk-tools), L-3 (escape report lines).
- Rework round 1 of 5 in progress. Architect decisions: H-1 rule in N8 (hash-only id = unlicensed in the report, unknown at U5); tmpfs `/tmp:mode=1777`; N5 floor on `--out` and `dirname(--out)`; the GCC runtime ships Debian source via the deb kind at U7 (no exemption).
- Tester round-1 RED: 16 tests failing (all `ReworkR1*`), controls 61 rows / 0 unexpected, reach PASS (851). Expected real counts: ke-app 19, ke-gateway 0, neo4j 28, phoenix 35, postgres 25, valkey 1.
- The U4 A34 proof (`u4/windows-run.txt`) is stale after the tmpfs change: re-run 2b and 3b.
- Next: developer round-1 GREEN.

## U4 (committed 40e2181; detail: archive/platform-sbom-part6.md and part7.md)
- Rework rounds used: 1 of 5.
- H-1 closed; all six unlicensed lists accepted by security.
- The cache warning is fixed with tmpfs `/tmp:mode=1777`.
- Carried to U5: security L-4, L-5, I-4, review R2 and R3, and a named LicenseRef fixture row.

## U4b (PSC-26, Q67; detail: archive/platform-sbom-part7.md)
- Orchestrator rulings: the EXPOSE exemption (the scanner gains a Dockerfile exact-line rule, which security must review); checks in offline_check after drift; the file tree as evidence only; the NOTICE section; labels excluded; installers unchanged; Q68, ke-neo4j not scanned.
- RED: 29 failing, 61 controls, reach PASS.
- GREEN: verify full PASS 990 s; config identical; file tree equal minus products (two jars: the fleet-management and genai plugins); plugin absent from the tar; ke-neo4j unlicensed 27; tar -1.15%.
- Next: A34 Windows proof (new Dockerfile plus compose), reviewer and security in parallel, orchestrator verify full, commit.

Session checkpoint: next-session brief is docs/handoffs/NEXT-SESSION.md (untracked)
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
