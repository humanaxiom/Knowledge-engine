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
