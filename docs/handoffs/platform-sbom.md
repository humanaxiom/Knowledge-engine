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

## 2026-10-22 — tester (U0 RED)
- Did: 8 U0 tests in new `tests/test_psycopg_c.py` (static `*_problems(path)` checks + in-test controls; gates real import; smoke via fake docker). `tests/fake_docker.py` models the api's psycopg/ldd/dpkg (defaults = a correct image at the app.Dockerfile pin). `tests/test_offline_bundle.py`: `_runtime_packages` walks `pq-c`; the psycopg native case follows the lock (binary now, psycopg-c after U0).
- RED: `verify.sh fast` 778 run, 21 failures, all new (7 methods + 14 smoke subtests), none existing; sentinel ok. `docs/evidence/platform-sbom/u0/red-verify-fast.txt`.
- Mutants: static 0 unexpected (TARGET passes 1-5, 8 and existing AppImageTest; M1-M15 fail as named); smoke 0 unexpected (TARGET passes; S1-S6 fail; S7 equivalent). `u0/red-mutants.txt`, drivers `u0/u0_mutants.py`, `u0/u0_smoke_mutants.py`, `u0/target_smoke_block.sh`.
- For GREEN: smoke must accept libpq at `/lib/<triplet>/` as well as `/usr/lib/<triplet>/` (bookworm ldd prints the /lib alias; N0 says /usr/lib only); dpkg owns only the /usr path. The pin compare may use dpkg-query in api or the Dockerfile (then add it to the shared smoke setUp copy list).
- For GREEN: confirm `uv lock` puts `pq-c`/`pq-build` under the project's `[package.dev-dependencies]` (test 1 and the bundle fixture read them there); recheck gates-side tests (`test_gate_least_privilege` chown after last sync, `test_block_main_commit_hook` apt line) on the new gates.Dockerfile.
- Next: developer GREEN on U0 (`verify.sh full`, A34 Windows run).

## 2026-10-22 — developer (U0 GREEN)
- Did: `pyproject.toml` psycopg plain + groups `pq-c`, `pq-build` (setuptools==83.0.0, wheel==0.48.0 from psycopg-c 3.3.6's sdist) + `[tool.uv] no-build-isolation-package`; no dependency-metadata needed (sdist PKG-INFO is static). `uv.lock` regenerated by `uv lock` in a throwaway ke-gates container with network (UV_OFFLINE unset); psycopg-binary gone, psycopg-c sdist only.
- `app.Dockerfile`/`gates.Dockerfile`: `LIBPQ_VERSION=15.19-0+deb12u1` (apt-cache policy at the base digest), builder gcc+libc6-dev+libpq-dev, three `--locked` syncs, runtime libpq5 pin. `smoke.sh` psycopg step (ldd prints `/lib/x86_64-linux-gnu/libpq.so.5`). `NOTICE.md` names psycopg-c.
- GREEN: `verify.sh fast` PASS (778 tests, the 8 U0 tests ok); `verify.sh full` PASS 711 s; scan: only Medium/Low, no fixed High/Critical; scan policy and ignore file untouched. ke-app 265 -> 259 MB. Windows `uv run --locked ... log_event --help` works (no compile).
- Evidence: `docs/evidence/platform-sbom/u0/green-verify-fast.txt`, `green-verify-full.txt`, `size.md`. Not committed. The `docs/evidence/platform-sbom/u0-psycopg-c.md` doc (N0 "confirm at GREEN") was not written.

## 2026-10-22 — documenter (U0)
- Wrote `docs/evidence/platform-sbom/u0-psycopg-c.md` (N0 confirmations, with a "Not confirmed" list: bundle tar size, offline-client run of the step, L-13 closure, aarch64 ldd path).
- README.md scan paragraph: dropped the false "psycopg-binary vendored libs, residual L-13" statement. Other psycopg-binary mentions are dated rulings, ADR history and requirements text, left alone. No verify run (docs).

## 2026-10-23 — tester (U0 Windows proof)
- A34 PASS at HEAD 737750d + U0 tree (sha256 of both Dockerfiles, uv.lock, pyproject, smoke.sh in the file), aria-alien1, pwsh 7.6.7, Docker 29.5.2, project ke-tester-u0win, tag u0win-737750d: build.ps1/launch.ps1 exit 0, 7/7 healthy, 127.0.0.1 only; refusal 0.0.0.0+prod exit 1, no compose up; teardown.ps1 and -Volumes exit 0, nothing of the project left; .env and tags removed; Windows-only tests 7 OK.
- api and worker: `c 150019`; psycopg_c.pq links /lib/x86_64-linux-gnu/libpq.so.5 (mapped /usr/lib/.../libpq.so.5.15), no psycopg_binary, libpq5 15.19-0+deb12u1. `COMPOSE_PROJECT_NAME=ke-tester-u0win scripts/verify.sh fast` PASS (778, skipped=8). Evidence: `docs/evidence/platform-sbom/u0/windows-run.txt`; stale if an A34 file changes before commit.

## 2026-10-23 — reviewer (U0)
- CHANGES REQUESTED. B1 smoke does not check that dpkg owns the loaded libpq, or that no psycopg_binary* is in /opt/venv (PSC-25, and PSC-14's retired drift check relies on it); B2 PSC-25 *Size*: bundle tar size before/after not recorded; B3 ADR-KE-016/N0 test names and the /usr/lib-only proof are stale, PSC-13/PSC-25 *Lock* "--no-dev" leaves out pq-c.
- Confirmed: lock (psycopg-c sdist-only + sha256, no psycopg-binary), groups, both Dockerfiles (one pin, no compiler ships), NOTICE, RED 21 all U0, GREEN fast+full PASS, mutants real, Windows proof hashes = tree, agent Constraints untouched. Nits N1-N6. Detail: `docs/evidence/platform-sbom/u0/review.md`.
- Next: developer+tester fix B1/B2; architect (B3.1-2) and analyst (B3.3, N1) amend docs; reviewer re-reviews.

## 2026-10-22 — security (U0)
- PASS (no critical/high). M-1 medium: smoke.sh `$((10#$deb_major...))` evaluates container-supplied dpkg-query output (array-subscript command execution on the host; proof `u0/security-smoke-arith-poc.txt`); developer validates `$deb` with a regex + BASH_REMATCH before arithmetic, tester adds the fake-docker case. L-1 apt deps unpinned (N0-accepted); L-2 unpinned base pull: record it in one line and `docker image rm python:3.12-slim-bookworm`.
- L-13 CLOSED: no psycopg_binary/*.libs in the shipped image, libpq.so.5 owned by dpkg libpq5 15.19-0+deb12u1, deps scanned as deb; policy unchanged, `ignore: []`. A66: require_auth follow-up re-rated low, re-scoped for auth-audit (server scram-only pg_hba + password_encryption now; channel_binding=require if backend TLS; require_auth when libpq>=16).
- Info for documenter: stale PS-2.5 rationale; krb5/keyutils were already in base (size.md, u0-psycopg-c.md). Detail: `docs/evidence/platform-sbom/u0/security.md`.

## 2026-10-23 — orchestrator (U0 rework round 1 of 5)
- Review CHANGES REQUESTED (B1 smoke lacks dpkg-ownership and no-psycopg_binary
  checks; B2 bundle tar size missing; B3 ADR/N0/PSC-13/PSC-25 drift); security
  PASS with M-1 (host arithmetic injection via dpkg version in smoke), fix now.
  L-13 CLOSED (security). A66 re-rated low, re-scoped to auth-audit.
- Round 1: tester RED (B1 x2, M-1, N3 dpkg-query failure + non-numeric version,
  N4 cleanup, gssencmode test comment); developer GREEN (smoke, B2 sizes, N5
  uv-run output, L-2 record + remove the unpinned base tag); architect B3.1/B3.2;
  analyst B3.3 + N1 + gssencmode reason (requirements ~578); documenter N2 README
  operator line + package-list correction in u0/size.md and u0-psycopg-c.md.
- Correction to my opening section: the ADR is written (ADR-KE-016); the U4
  "drift" mention in the unit list is stale (no vendored drift check).

## 2026-10-22 — documenter (U0 rework)
- README: operator note on the libpq5 pin (N2) and L-13 closure sentence citing u0/security.md (N6); size.md and u0-psycopg-c.md package list corrected to the four packages apt added (security I-5).
- Docs only; fast verify not re-run this round (no code touched).

## 2026-10-23 — analyst (U0 rework)
- requirements.md, each marked "(Amended 2026-10-23, analyst, U0 review)": B3.3 runtime packages = builder's final sync `--no-dev --group pq-c --no-binary-package psycopg-c` (PSC-13, PSC-25 *Lock*, resolver test flags); N1 PSC-25 *Windows (A34)* = PS-2.9 proof + `verify.sh fast` (`u0/windows-run.txt`), as PSC-12; PS-2.5 gssencmode reason updated (criterion unchanged).
- L-13 marked CLOSED 2026-10-23 by security (PSC-7, `require_auth` follow-up); A66 re-rating recorded there (low, re-scoped to auth-audit, 3-step replacement). Next: architect/tester build U3's SBOM test from the new PSC-13 definition.

## 2026-10-23 — architect (U0 rework)
- B3.1/B3.2/N2 done, ADR-KE-016 still 189 lines (architecture.md 6569-6588, 6703-6723): all 8 U0 test names, requirements names win; *Proof* now covers /usr/lib or merged-usr /lib, realpath plus `dpkg-query -S` owned by libpq5, no psycopg_binary* in /opt/venv, and versions checked against the installed dpkg libpq5 with a strict, fail-closed regex (M-1); *Consequences* gains the operator pin-drift line.
- N0 (design-notes.md 107-111, 149-162, 201, 219, 231-234): the same proof and test names; apt added only libpq5, libldap-2.5-0, libsasl2-2, libsasl2-modules-db (krb5, keyutils were already in the base). Next: developer/tester make smoke.sh match the *Proof*.

## 2026-10-23 — tester (U0 rework RED)
- Added 4 tests to `SmokePsycopgTest` (tests/test_psycopg_c.py): B1a psycopg_binary dir, `.libs` and dist-info beside c; B1b realpath + dpkg owner exactly libpq5 (also ldd path end anchor, N3); M-1 `0+PPID[$(touch m)]`, `0+BASH_VERSINFO[...]`, `x.y`; N3 dpkg-query failure (green on arrival, mutant T6 kills it) and empty version. Fake knobs: FAKE_PQ_VENV_EXTRA, FAKE_LIBPQ_REALPATH, FAKE_LIBPQ_OWNER, FAKE_LIBPQ5_ABSENT, empty FAKE_LIBPQ5_VERSION, `find`; the stub site sets sys.prefix to `<tmp>/opt/venv`, so smoke's venv scan must use sys.prefix (or `find /opt/venv` in api), not a literal /opt/venv in the python CODE.
- N4: dead `NOTICE_LICENCE["psycopg-binary"]` removed, case asserts psycopg-c (and no psycopg-binary) directly; ok. gssencmode comment at tests/test_stack_readiness.py:480 updated (comment only).
- RED: `COMPOSE_PROJECT_NAME=ke-tester-u0r1 scripts/verify.sh fast` FAIL, 782 tests, failures=15, all new subtests; lint PASS, sentinel ok. Evidence `u0/r1-red-verify-fast.txt`.
- Scratch check `u0/r1-red-mutants.txt` (driver `u0/r1_smoke_check.py`): CURRENT fails 15 new and 0 old; TARGET `u0/r1-target-smoke-block.sh` passes all (shellcheck clean); mutants T1-T6 each killed.
- Next: developer GREEN, putting the target block (or equivalent) into scripts/smoke.sh, then `verify.sh full`.

## 2026-10-23 — developer (U0 rework GREEN)
- `scripts/smoke.sh` psycopg step = tester's target block (B1 realpath + dpkg-query -S owner exactly libpq5[:arch], os.walk(sys.prefix) psycopg_binary* scan; M-1 `$deb` regex + BASH_REMATCH before arithmetic; N3 end-anchored libpq regex, named FAIL on empty/failed dpkg). shellcheck is not on the host; the fast gate's lint passed.
- B2 `u0/size.md`: `docker save` tar (as bundle.sh) 60,414,464 B at 737750d -> 58,818,048 B after (-1.6 MB); sizecheck tag and scratch worktree removed. N5 `u0/q65-windows-uv-run.txt` (exit 0). L-2 `u0/u0-lock-regen.md`: unpinned python:3.12-slim-bookworm removed, pinned 34386ef0 kept.
- GREEN: `verify.sh fast` PASS (782, skipped=8), `verify.sh full` PASS 707 s; psycopg smoke line printed for the build host and the offline client. Evidence `u0/r1-green-verify-{fast,full}.txt`. Throwaway .env deleted. Not committed.

## 2026-10-23 — security (U0 re-check)
- PASS (no critical/high/medium). M-1 FIXED: every api value in the smoke psycopg step is validated, quoted, fail-closed; PoC re-run, 18 hostile cases no marker, round-0 control creates one (`u0/security-recheck-m1-poc.txt`). L-2 DONE (tag gone, pinned 34386ef0 kept). Docs (README, PSC-7/A66, ADR-KE-016) accurate; new tests/fake safe, no network; evidence sweep clean.
- Info only: I-6 optional anchor on `$libpq_real`; I-7 raw container text in messages; I-8 smoke.sh:133 stale "not production" comment (reviewer); I-9 Q66 in open-questions lacks the A66 outcome pointer (analyst). Detail: `docs/evidence/platform-sbom/u0/security.md` "Re-check".

## 2026-10-23 — reviewer (U0 re-check)
- APPROVED. B1 (realpath + dpkg-query -S owner exactly libpq5, sys.prefix psycopg_binary* scan), B2 (tar 60,414,464 -> 58,818,048 B; reviewer re-measured the after tag exactly), B3, N1-N5 and security M-1 resolved; PoC re-run, no host execution; both r1 verify runs PASS, psycopg line for build host and offline client; A34 hashes equal except smoke.sh (gate script).
- Open nits, none blocking: N6 README line width; N7 end-anchor/realpath-failure branches not pinned by their own subtest (R2/R6 survive, still fail closed); N8 smoke.sh line 133 "tester scratch target, not production" comment; N9 N0 wording. Detail: `docs/evidence/platform-sbom/u0/review.md` Re-check, `u0/r1-review-mutants.txt`.
## 2026-10-23 — documenter (U0 nits)
- N6 README re-wrapped (no word changes); N9 N0 now names the string compare and the four new SmokePsycopgTest methods; I-9 Q66 outcome line added; q65 file notes the truncated usage line. Docs only; no verify run.
## 2026-10-22 — tester (U0 N7)
- N7: two new subtests in `test_smoke_checks_dpkg_libpq5_owns_the_loaded_libpq` kill R2 ("end anchor: ldd libpq.so.5.evil, realpath to the libpq5-owned file") and R6 ("realpath -e fails in api (its output is the libpq5-owned file)"); the old "N3 end anchor" subtest renamed "ldd path libpq.so.5-evil, realpath unowned (ldd regex or dpkg -S)". fake_docker.py unchanged (hook stdout/exit).
- Mutants R1-R7 + R2b all killed, shipped 0 failing: `u0/r1-n7-mutants.txt`. `verify.sh fast` PASS (782 tests, OK skipped=8): `u0/r1-n7-verify-fast.txt`.

## 2026-10-23 — orchestrator (U0 commit gate)
- Review APPROVED on re-check (N6-N9 fixed after it); security PASS on re-check
  (M-1 fixed, L-2 done, L-13 CLOSED, A66 re-rated). Rework rounds used: 1 of 5.
- Orchestrator verify full PASS 694 s on the final tree (782 unit + 15 integration;
  psycopg c on libpq5 15.19-0+deb12u1 on build host and offline client; scan done;
  `docs/evidence/platform-sbom/u0/orchestrator-verify-full.txt`). Diff read.
- A34 proof `u0/windows-run.txt` covers both Dockerfiles, uv.lock, pyproject.toml.
- Commit APPROVED: U0 (PSC-25) plus the item's plan docs. Next: U1 (PSC-14).
