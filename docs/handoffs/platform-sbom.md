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

## 2026-10-23 — orchestrator (U1 commit gate)
- Review APPROVED (re-check 4) and security PASS (re-check 4, L-9b closed); rework
  rounds used 4 of 5. Orchestrator verify full PASS 721 s on the final tree (792 unit +
  15 integration; psycopg c on libpq5 and "no pip in api" on build host and offline
  client; scan done; `u1/orchestrator-verify-full.txt`). Diff read. A34 proof stands.
- Commit APPROVED: U1 (PSC-14, pip dropped, ke-app flattened). Next: U2 (PSC-20).

## 2026-10-23 — tester (U2 RED)
- RED: `tests/test_sbom_generator.py` has 4 PSC-20 tests (8 subtest failures). They fail because docker-compose.sbom.yml is missing and bundle.sh has no generator check. Everything else passes, including the sentinel (`u2/red-verify-fast.txt`).
- Harness: the fake reads compose `config` for each file (FAKE_COMPOSE_FILE_IMAGES/_REQUIRED); `_BundleBase` holds the syft ref; `docker-compose.sbom.yml` is in `_REPO_COPY`. Contradiction resolved: `test_stack_services_have_no_bind_mounts` exempts `sbom` (ADR-KE-016 pt 1, N1).
- Targets for the developer: `u2/target-*` (the compose file, the refusal snippet before "licence notices", the pin location). Reach: verify fast PASS with these targets (`u2/red-reach-verify-fast.txt`). Controls: 110, 0 unexpected (`u2/red-mutants.txt`, driver `u2/u2_controls.py`).
- Open for the orchestrator: (1) U2 verify full: nothing pulls syft before U8's bundle_fetch.sh, so offline_check's bundle.sh refuses. Pick the step that pulls it at U2. (2) The refusal text names bundle_fetch.sh, which does not exist yet. (3) The label (`-p <project>-sbom`) is tested statically only; the run itself is U3's.

## 2026-10-23 — architect (U2 decisions)
- syft v1.54.1 (the one grype v0.120.1 embeds), index sha256:3eb5379b…49b1aa; 8 `SYFT_*=false` keys (4 new: JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES, GOLANG_USE_PACKAGES_LIB, PYTHON_SEARCH_REMOTE_LICENSES, CPP_VCPKG_ALLOW_GIT_CLONE); full digests and reasons in design-notes "N1 amendment, U2"; ADR-KE-016 pt 1 amended.
- Interim pull in `offline_check.sh` just before `bundle.sh`: `KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom`; read uses same dummy form (not --no-interpolate; pull has none); refusal says `pull it first with: docker pull <ref>` until U8. Tester: re-target RED (env set, message, new offline_check "pull sbom" before "bundle" + pull-fail stops before bundle). CLAUDE.md unchanged.

## 2026-10-23 — security (U2 provenance)
- PASS: `anchore/syft:v1.54.1@sha256:3eb5379b…49b1aa` (amd64 507b76f0…, arm64 9c493ce4…) confirmed on docker.io and ghcr.io; image unsigned, so N2 step 3: `syft_1.54.1_checksums.txt` verify-blob OK against anchore/syft `release.yaml@refs/heads/main` (commit b254e6d9 = tag), 3 negative controls fail; both archives match it; `/syft` docker-cp'd (never run) from each platform image is byte-identical to the archive binary.
- Gaps: G2 low (built on a self-hosted runs-on.com runner, unlike grype; re-check at each bump), G1/G3/G4/G5 info. Record: `docs/evidence/platform-sbom/generator-provenance.md`, raw `u2/security-*.txt`; host keeps only the amd64 pin.
- Tester (U2 RED re-target, 2026-10-23): RED now 11 failures, all U2 (`u2/red-verify-fast.txt`): the 4 sbom tests plus new `test_offline_check_pulls_sbom_generator_before_bundle` and `test_offline_check_stops_when_sbom_pull_fails`; eight `SYFT_*=false` + TMPDIR, exact refusal (`pull it first with: docker pull <ref>`), `--env-file .env.example` on every sbom compose call; targets `u2/target-*` (real pin, `target-offline_check.sh` + pull snippet); controls 138, 0 unexpected (`u2/red-mutants.txt`); reach PASS (`u2/red-reach-verify-fast.txt`); `u2/syft-v1.54.1-config.txt` copied (checked: no secrets, no profile paths).

## 2026-10-23 — orchestrator (U2 plan gate)
- Architect: syft v1.54.1 (grype v0.120.1's syft), index sha256:3eb5379b...49b1aa;
  interim pull in offline_check.sh before bundle.sh; 8 SYFT_*=false keys + TMPDIR.
  Security: provenance PASS (unsigned image; signed checksums + byte-identical binary
  for amd64/arm64; G2 low self-hosted runner, re-check at each bump).
- Standing rule (security G5, adopted): record provenance BEFORE running any newly
  pinned image, even offline.
- Tester RED re-target accepted (11 failing, 138 controls, reach PASS). Next: GREEN.

## 2026-10-23 — developer (U2 GREEN)
- Added docker-compose.sbom.yml (syft v1.54.1 index pin, hardened, 8 SYFT_* keys, TMPDIR), bundle.sh refusal, offline_check.sh interim pull; copied from the tester's targets (diff vs targets empty). No .ps1 counterpart changes (install.ps1 only consumes bundles). Tests unchanged.
- verify fast PASS; verify full PASS 703 s (offline_check stage 95 s; pull line then "bundle written"). Pull cost not separable: output has no timestamps and the image may have been cached (u2/green-verify-fast.txt, u2/green-verify-full.txt).

## 2026-10-23 — reviewer (U2)
- APPROVED, no blocking. Diff read; files equal targets; controls re-run on the real files: 138, 0 unexpected (`u2/review-controls-base-repo.txt`); evidence red/reach/green fast+full consistent.
- Nits N1-N5 in `u2/review.md`; N1 (run/down lines lack `--env-file .env.example`) and N2 (no linux/$arch check of the generator) carry to U3 with tester items 5 and 8 (deferral accepted on that condition).

## 2026-10-23 — security (U2)
- PASS (no crit/high/med): hardening, 8 SYFT keys + TMPDIR complete vs v1.54.1 config, refusal read injection-safe/no pull/no `.env` (probes), pull adds no egress (docker.io already; CLAUDE.md holds), pin agrees. `u2/security.md`, raw `u2/security-u2-probes.txt`.
- L-1 low: tests read raw YAML; compose `config` fetches remote `include` and `extends` merges host net/binds unseen; forbid both. L-2 low (U3): no `user:`, syft runs uid 0 writing /out; set caller uid:gid. I-1..I-3 info.

## 2026-10-23 — tester (U2 Windows proof)
- A34 PASS (`u2/windows-run.txt`): U1 driver/phases/shim, project ke-tester-u2win, tag u2win-23e3c9b; build/launch (7/7 healthy)/4b/4c/refusal/teardown/7 Windows tests PASS; NEW 2b: `docker compose --env-file .env.example -f docker-compose.sbom.yml config` resolves on Windows (network_mode none, read_only, cap_drop ALL, no-new-privileges, tmpfs /tmp, /in ro + /out binds), `config --images sbom` == pin, unset KE_SBOM_IN fails closed; syft not run or pulled; verify fast PASS (798, 480 s); teardown left nothing; six sha256 identical start/end (2b "ports/profiles: 1 entries" is a PowerShell @($null) artifact, real key set in the final check).

## 2026-10-23 — orchestrator (U2 commit gate)
- Review APPROVED (0 rework rounds), security PASS, A34 Windows proof PASS (hashes in
  u2/windows-run.txt), orchestrator verify full PASS 699 s (798 unit + 15 integration;
  syft pulled then bundle written; `u2/orchestrator-verify-full.txt`). Diff read.
- Carried to U3 (the first syft run, which edits these files anyway): review N1
  (--env-file + KE_SBOM_* on run/down), N2 (generator image is linux/$arch), N3
  (offline_check header stage list), N4 (design note wording), N5 (compose comment);
  security L-1 (tests forbid top-level include/extends), L-2 (run as caller uid:gid),
  I-1 (ref_re leading '-'), I-2 (no HOME/XDG under /out/tmp). Reviewer's conditions:
  U3 RED pins the full run argv and the `<project>-sbom` project + its teardown.
- Commit APPROVED: U2 (PSC-20). Next: U3 (PSC-13 SBOM generation).
