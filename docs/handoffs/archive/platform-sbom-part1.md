# Archive: platform-sbom part 1 (plan-phase sections, 2026-10-22, moved verbatim from platform-sbom.md)

## 2026-10-22 — analyst
- Asked to: confirm or correct PSC-13..16 against today's code, add PSC-19+
  where a gap is real, write Q61-Q63 with recommendations. Docs only; no
  code, no tests, verify not run.
- Did: `docs/requirements.md` § platform-sbom (dated "Confirmed/amended"
  block under Status lists every change); `docs/open-questions.md` new
  § platform-sbom with Q61-Q63; pointers under the item's open points.
- Drift fixed:
  - PSC-14: "the `uv` binary" removed (PSC-17). The shipped stage is
    `python:3.12-slim-bookworm` + `/opt/venv` + `/app`, so the paragraph
    now names CPython 3.12, the Debian 12 packages and the base's pip (in
    system site-packages, outside `uv.lock` and the generated table; the
    developer confirms in the image). The 15 vendored files are named from
    `u4-psc7-psycopg-libs.txt`; NOTICE lists the amd64+arm64 union.
  - PSC-13: "digest or ID" -> the image ID of the tar (what install reports
    as `Loaded image ID`); "runtime package" defined as `--no-dev`.
  - PSC-15/16: unchanged in substance; PSC-16 also measures the manifest
    size (1 MiB install cap) and `/install` tmpfs (memory) use.
- New criteria: PSC-19 e2e (extends `ci/deployable-offline`: installed copy
  has one SPDX 2.3 SBOM per image naming the loaded ID, PSC-15 checks pass
  on it); PSC-20 generator pinned + PSC-1 provenance + no network,
  read-only, cap_drop ALL, no socket, not in bundle, refuse if absent;
  PSC-21 per-arch (native generation, self-sufficient `sources/`, arm64 in
  the recorded Q51 run); PSC-22 obligations not hidden by the generator
  (vendored libs in the SBOM, named GPL components always checked,
  no-licence packages reported); PSC-23 fetch is HTTPS-only to listed hosts,
  checked before use, ships unpacked, no keys, CLAUDE.md wording with human
  approval; PSC-24 no partial bundle, manifest path rule and 1 MiB cap hold.
- Open for the human: Q61 (rec. fail closed; mismatch never open), Q62
  (rec. the same 180 s trigger), Q63 (rec. reduced verify set, full set for
  operator bundles; cost figures are estimates, PSC-16 measures on CI).
- Next role (architect) needs to know, code that contradicts the criteria:
  - `scripts/bundle.sh` header: "makes no network call" vs PSC-15's fetch at
    bundle time; the ADR places the fetch (PSC-23).
  - Manifest path rule `[A-Za-z0-9._-]` in bundle.sh, install.sh,
    install.ps1 rejects Debian source names with `+`/`~` (PSC-24).
  - install.sh/install.ps1 parse `bundle.json` image entries with an exact
    regex; any new field there breaks install unless both change.
  - `/install` is an unsized tmpfs: sources add to memory, not only disk.
  - The scanner does not catalogue `psycopg_binary.libs`; a generator built
    on the same catalogers likely will not either (PSC-22).
  - Hosted CI keeps nothing between runs: a source cache needs a CI-only
    step, which the single-step rule forbids (Q63 option 2).
  - Proposed TDD order is in the item (after PSC-24).
- Evidence: `docs/evidence/platform-sbom/analyst-verify-fast.txt` (verify fast PASS, 770 tests OK, skipped=8).

## 2026-10-22 — orchestrator (human rulings Q61-Q63)
- Q61: fail closed on a failed or mismatched source fetch (as Q56(b)).
- Q62: Q60's 3-min CI-cost trigger applies; over 180 s goes to the human.
- Q63: reduced verify set (all SBOMs + full index + coverage every run; one
  source per kind fetched and shipped); full set for operator bundles.
- All three match the analyst's recommendation and the architect's working
  assumptions. Documenter records them in `docs/open-questions.md`.

## 2026-10-22 — architect
- Asked to: write the platform-sbom ADR (generator, fetch placement, lock
  and routes, naming, recording, `/install`, classifier, NOTICE, e2e,
  units). Docs only; no code, no tests, no network, verify not run.
- Did: `docs/architecture.md` ADR-KE-016 (lines 6535-6723; §9 index line
  updated); long detail in `docs/evidence/platform-sbom/design-notes.md`
  (N1-N15). The human's Q61/Q62/Q63 rulings (2026-10-22) are written as
  rulings; `docs/open-questions.md` untouched (documenter records them).
- Decided (one line each; ADR points 1-11):
  - syft, index-digest pin, D2 provenance; standalone
    `docker-compose.sbom.yml` service `sbom` (no network, read-only,
    cap_drop ALL, `--scope all-layers`, unpack on a disk work dir).
  - One stdlib checker `scripts/sbom_check.py`, run in `ke-app` at bundle
    time (as the notices run), in the offline client for the e2e.
  - Fetch is a pre-bundle step `scripts/bundle_fetch.sh` + one-shot
    `sources-fetch` (ke-gates image); `bundle.sh` stays offline; curl
    HTTPS-only, redirects followed by hand with a per-hop host check
    against `docker/source-policy.json` `hosts`; Q61 fail closed.
  - Committed generated lock `docker/sources.lock.json` (Debian via
    snapshot.debian.org, Alpine via aports commit + sha512sums, Neo4j TOFU
    + security second fetch, Temurin `.sha256.txt`, psycopg from `uv.lock`,
    psycopg-c from PyPI); sample = smallest entry per kind (Q63).
  - Content-addressed stored names `app/sources/files/<sha256>` + index;
    path rule and 1 MiB cap unchanged; `bundle.json` and installers
    unchanged (SBOMs `app/sboms/<name>.spdx.json`, all under `app/`).
  - `/install` tmpfs sized to bundle + 512 MiB with a MemAvailable
    pre-check; stays tmpfs because Q63 keeps verify small.
  - Classifier: OR/AND/WITH rule, GPL-family regex (wider: AGPL, GPL-1.0,
    LGPL-2.0), `always` + `exempt` (versioned purl, security-reviewed).
- Units (order; loop mode; every commit runs full): U1 PSC-14 (fast), U2
  PSC-20 (full, A34), U3 PSC-13 (full), U4 PSC-22/drift (full), U5
  classifier (fast), U6 policy (fast), U7 lock (full), U8 PSC-23 + CLAUDE.md
  (full, A34), U9 PSC-15/24 (full; A34 if install.ps1 changes), U10 PSC-19 +
  `/install` (full, A34), U11 PSC-16 on CI + full recorded run, U12 PSC-21.
- Flagged for the orchestrator/human (ADR "Flagged"):
  - (a) PSC-13/19 "image ID install reports as Loaded image ID" conflicts
    with R2 (named load prints `Loaded image: <as>`; IDs differ by store);
    design uses the tar's config digest. Analyst amendment needed.
  - (b) Install publishes only `app/`; PSC-19's "installed copy" is met by
    putting SBOMs, sources and notice copies under `app/`.
  - (c) LGPL libcrypt/libkeyutils in `psycopg_binary.libs` come from the
    wheel's el7 build image at an unrecorded release: `srpm` kind
    (vault.centos.org) with a reviewed best guess, or the Q42 fix (psycopg
    on Debian's libpq) removes them. Human call.
  - (d) classifier wider than PSC-15; (e) neo4j third-party GPL jars
    unknown until U3; (f) CLAUDE.md wording + a Generated-artifacts row for
    the lock (N13) need the human's approval at U8.
- Next role: orchestrator (Plan gate), then tester for U1:
  `test_notice_has_ke_app_base_paragraph`,
  `test_notice_lists_psycopg_binary_vendored_libs` (RED: no section/table).

## 2026-10-22 — orchestrator (rulings on ADR-KE-016 open points)
- Human (new Q64): build psycopg against Debian libpq (`psycopg[c]` in the
  builder stage, the Q42 structural fix). `psycopg_binary.libs` goes away,
  its 15 libs become `deb`-kind sources, L-13 closes. No `srpm` kind.
  Adds a first unit (U0) before PSC-14; A34 Windows proof (Dockerfile).
- Orchestrator: (1) SBOM names the image by the tar's config digest;
  analyst amends PSC-13/PSC-19 wording. (2) SBOMs, sources and notice
  copies under `app/`: confirmed. (4) classifier wider than PSC-15 (adds
  AGPL, GPL-1.0, LGPL-2.0): confirmed, more conservative. (5) neo4j jars:
  decided at U3, back to the architect if any. (6) CLAUDE.md wording (N13)
  goes to the human at U8 with the proposed text.
- Next: analyst amends criteria (U0 criterion, PSC-14/PSC-22, PSC-13/19
  wording, Q64 record); architect amends ADR-KE-016 (U0 design, unit list),
  in parallel on separate files. Then tester RED on U0.

## 2026-10-22 — analyst (Q64 amendments)
- Did: Q64 recorded resolved (open-questions); L-13 closure lines under Q42 and PSC-7/require_auth; PSC-25 (U0) added; PSC-13/19 use the tar config digest; PSC-14/15/22 drop the vendored libs; rulings 2 and 4 noted; TDD order starts PSC-25.
- Tests: `test_notice_lists_psycopg_binary_vendored_libs` renamed `test_notice_names_libpq_as_a_debian_package`; `test_sbom_lists_psycopg_binary_vendored_libs` retired; PSC-14 image drift check retired.
- New for U0: `test_lock_has_no_psycopg_binary`, `test_runtime_stage_has_no_compiler`, `[full: ke-app psycopg impl is c and links system libpq]`. gssencmode="disable" today at `engine/readiness.py:91`, stays.
- Open Q65 (blocks U0's lock): `uv run` log step on the Windows host needs psycopg-binary's wheel (psycopg-c is sdist-only); recommend Linux-only markers. ke-gates also syncs and builds psycopg-c.
- Open Q66 (non-blocking): Debian 12 libpq5 is PG 15, drops from vendored 18; the `require_auth` follow-up needs libpq 16+; recommend accept 15, security re-rates.
- Next: orchestrator rules Q65 (and Q66), then tester RED on U0.

## 2026-10-22 — orchestrator (rulings Q65, Q66)
- Q65 (orchestrator): constraint is the SHIPPED ke-app has no psycopg-binary
  and uses psycopg-c on Debian libpq. Lock/dev-host/ke-gates resolution is
  the architect's (markers or extras); no CLAUDE.md/AGENTS.md change, no dev
  toolchain, `--locked` kept, `uv run` log step works on Windows. The lock
  test checks what the ke-app builder resolves. Human's Q64 intent intact.
- Q66 (orchestrator): accept Debian 12 libpq 15; security re-rates the
  `require_auth` follow-up at U0 review. No apt.postgresql.org.

## 2026-10-22 — architect (Q64 amendment)
- Did: ADR-KE-016 point 0 (U0, PSC-25), Q65/Q66 folded in; srpm kind, vault.centos.org, pypi.org, vendored post-step/table/drift removed; rulings 1, 2, 4-6 written as decided; ADR still 189 lines. Detail: design-notes N0, N7, N10, N12, N15.
- U0: `psycopg` (no extra) in deps; groups `pq-c` (`psycopg[c]`) and `pq-build` (hash-locked build deps, `no-build-isolation-package`); builder and ke-gates compile with `--locked --no-binary-package psycopg-c`; runtime `libpq5=${LIBPQ_VERSION}` (one global ARG, also `libpq-dev`); hosts' `uv run` gets pure psycopg and compiles nothing; psycopg-binary leaves the lock.
- Proof in the smoke stage (live `api`: impl `c`, versions equal pin, ldd Debian libpq); gates test checks ke-gates. Confirm at GREEN: uv flags and psycopg-c build requires (not checked online, no network).
- Next: tester RED on U0, `test_app_builder_resolves_psycopg_c_from_locked_sdist` first (N0 lists 8 tests); U0 loop full, A34 Windows proof.

## Plan-phase detail (moved from the live doc 2026-10-24)
Opener (2026-10-22 orchestrator), bullets 3 onward:
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

Plan phase, further rulings:
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
