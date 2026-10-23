# platform-sbom part 3: the U1 sections up to rework round 2's design (tester RED to the orchestrator's flatten-ke-app ruling)

## 2026-10-22 — tester (U1 RED)
- New `tests/test_notice_ke_app.py`: `test_notice_has_ke_app_base_paragraph`, `test_notice_names_libpq_as_a_debian_package` (PSC-14 tags) and `test_notice_points_to_generated_source_code_section` (pointer is U1 per ADR point 9 + N10/N15; name is the tester's, not a PSC-14 tag). Base ref + libpq pin from app.Dockerfile; added packages from the last stage's apt line plus the committed apt record `u0/green-verify-full.txt` (yields I-5's four); pip version shape only (no committed source).
- Criteria over brief: the three added deps need a licence pointer in their block (`/usr/share/doc/*/copyright`), not SPDX ids (PSC-14/N10 name none); section must give the base ref byte for byte, CPython 3.12 /usr/local PSF-2.0, Debian 12 + copyright + SBOM, libpq5 at the pin, pip <ver> site-packages MIT outside uv.lock, uv only negated.
- RED: `verify.sh fast` 785 run, failures=3 (the three new, each on the real NOTICE.md only), lint PASS, sentinel ok: `docs/evidence/platform-sbom/u1/red-verify-fast.txt`. Controls 35/35 fail as named, targets pass, reach check (today's NOTICE + target section with repo values) passes: `u1/red-mutants.txt`, driver `u1/u1_controls.py`.
- Rework (orchestrator ruling): no `docs/evidence/**` input; added packages are the `ADDED_PACKAGES` constant (security u0 I-5; U4's SBOM test checks the image), Dockerfile last-stage apt names must be in it; record controls replaced by "constant names libzz9" and "Dockerfile adds libzz9"; controls 35/35, re-run fast 785, failures=3 (same three).
- PSC-14 now tags `test_notice_points_to_generated_source_code_section` (analyst, 2026-10-23). This corrects the U1 RED note that said the name was not a PSC-14 tag.
- Next: developer GREEN edits NOTICE.md only (confirm pip version in the image); `verify.sh full` before commit.

## 2026-10-22 — developer (U1 GREEN)
- NOTICE.md: added "Base of `ke-app`" (base ref+digest, CPython 3.12/PSF-2.0, Debian 12 pkgs, libpq5 pin + 3 added pkgs, pip 25.0.1 MIT outside uv.lock, uv not shipped) and "Source code" pointer. Only NOTICE.md edited.
- pip 25.0.1 from `docker run --network none` on the pinned base@digest (local). `scripts/verify.sh fast` PASS: docs/evidence/platform-sbom/u1/green-verify-fast.txt. Not committed; orchestrator runs full.

## 2026-10-22 — security (U1)
- PASS (no critical/high). M-1: NOTICE "Source code" pointer names a section absent until U9; add the sentence in `u1/security.md` M-1 (passes all 3 checks); becomes high if a pre-U9 bundle is handed over or merged. L-1 SBOM forward ref until U3; L-2 pip's vendored Apache-2.0/MPL-2.0 parts ship no licence texts (drop pip from last stage, or name them); L-3 point CPython to `/usr/local/lib/python3.12/LICENSE.txt`.
- Image check (--network none): base digest, 4 added debs, libpq5 15.19-0+deb12u1, pip 25.0.1 MIT all match. I-1 for U5/U6: libldap/libsasl2 copyright files carry GPL lines. Evidence: `docs/evidence/platform-sbom/u1/security.md`.
## 2026-10-22 — reviewer (U1)
- CHANGES REQUESTED. B1: a stale NOTICE passes the test after a base bump, and an honest update fails. The CPython minor silently defaults to 3.12 when the ref does not parse, and `Debian 12` is hard-coded (probes P1/P2 pass stale, P3 honest trixie fails); derive both from the ref, fail when it does not parse, add 2 controls. B2: the PSC-14 amendment says the base section points to Source code, but the pointer has its own section (the right design); the analyst rewords PSC-14. B3: the `ADDED_PACKAGES` comment promises a U4 image check that PSC-22/N15 do not plan; plan it or reword the comment.
- Nits N1-N5: forward refs (SBOM U3, Source code U9) mean no merge/bundle before U9, and U9 pins the heading cross-file; pip 25.0.1 probe output not saved; PSF-2.0 vs Python-2.0 for CPython (needs a ruling); broad DATED_RE; private helper imports. Split faithful, RED/GREEN sound. Detail: `docs/evidence/platform-sbom/u1/review.md`.

## 2026-10-23 — orchestrator (U1 rework round 1 of 5)
- Review CHANGES REQUESTED (B1 base-bump gap in test, B2 PSC-14 pointer wording,
  B3 ADDED_PACKAGES promised an unplanned check); security PASS with M-1 (false
  "Source code" pointer before U9), L-1, L-2 (pip vendors Apache-2.0/MPL-2.0
  code), L-3, I-1 (libldap/libsasl2 copyright has GPL lines: U5/U6).
- Rulings: B1 strict ref parse + codename map, no default; B2 keep the separate
  section, reword PSC-14; B3 option (a): U4/PSC-22 checks the image's added dpkg
  set and pip version against ADDED_PACKAGES; N3 CPython is SPDX `Python-2.0`,
  pointing to /usr/local/lib/python3.12/LICENSE.txt; security M-1/L-1 wording
  verbatim; N2 save the pip probe; N4 tighten DATED_RE.
- N1 (standing): nothing from this branch merges to main and no operator bundle
  is cut before U3 (SBOM) and U9 (Source code section) land.

## 2026-10-23 — analyst (U1 rework)
- docs/requirements.md amended per rulings (marker "Amended 2026-10-23, analyst, U1 review"): PSC-14 pointer in own "Source code" section + pre-U9 no-`sources/` sentence (B2, M-1), CPython `Python-2.0` + LICENSE.txt (N3), SBOM conditional until U3 (L-1), pip vendored licences + drop-pip follow-up (L-2); PSC-15 `[unit: test_notice_source_code_heading_matches_generated]` (U9) + item standing no-merge/no-bundle rule (N1); PSC-22 `[full: ke-app SBOM's added dpkg set equals ADDED_PACKAGES and pip version matches NOTICE]` (U4, B3) + libldap/libsasl2 GPL lines need deb source or reviewed exemption (U5/U6, I-1).
- Tester: B3 is now planned, so the `ADDED_PACKAGES` comment may stay; NOTICE must carry the M-1/L-1/L-2/N3 wording. Open: whether Apache-2.0/MPL-2.0 texts go into `licenses/` before pip is dropped (not ruled).
- Human ruling 2026-10-23: keep pip in ke-app and document it, so
  `licenses/Apache-2.0.txt` and `licenses/MPL-2.0.txt` ship and NOTICE's pip
  bullet names them (test_licenses_carry_texts_for_pip_vendored_licences).
  The "drop pip" follow-up stays open, but is no longer a compliance gap.
- PSC-14 L-2 re-amended for "pip kept (human, 2026-10-23)": `licenses/Apache-2.0.txt` + `licenses/MPL-2.0.txt` ship, NOTICE's pip bullet names them, `[unit: test_licenses_carry_texts_for_pip_vendored_licences]` (fast); drop-pip follow-up stays open, not needed for compliance.

## 2026-10-23 — architect (U1 rework)
- ADR-KE-016 (189 lines, unchanged): point 9 CPython `Python-2.0` + `/usr/local/lib/python3.12/LICENSE.txt`, pre-U9 "no `sources/`, does not itself provide the source" (M-1), SBOM conditional until U3 (L-1), pip vendored licences (L-2); TDD list: U4 adds the image-side drift check (B3); U0 first tests now point to N0.
- design-notes: N7/N10/N15-U4 drift check = `ke-app` SBOM dpkg names minus base-image SBOM equal `ADDED_PACKAGES`, `pkg:pypi/pip` version equals NOTICE's ("no image-side drift check" removed); N10 pip bullet names vendored licences and `licenses/` Apache-2.0/MPL-2.0 texts (human: pip kept), drop-pip stays a follow-up; N15 U5/U6 note (I-1): libldap/libsasl2 GPL-family, U7 locks openldap/cyrus-sasl2 sources unless security exempts at U6. Next: `ADDED_PACKAGES` comment is now true (U4 planned); developer applies NOTICE wording.

## 2026-10-23 — orchestrator (attribution)
- The four "Human ruling 2026-10-23: keep pip" lines inside the analyst (U1 rework)
  section above are the orchestrator's, appended without a heading.

## 2026-10-23 — tester (U1 rework RED)
- `tests/test_notice_ke_app.py`: strict base-ref parse + DEBIAN_RELEASES (B1), Python-2.0 + LICENSE.txt (N3/L-3), conditional SBOM (L-1), pip vendored licences (L-2), M-1 sentence, start-of-block DATED_RE (N4), B3 comment; new `test_licenses_carry_texts_for_pip_vendored_licences` (human ruling; bundle.sh ships licenses/ wholesale via `git ls-files`, so the files must be git-added). 71 controls (68 fail, 3 pass), 0 unexpected; reach passes: `u1/red-mutants.txt`.
- RED `verify.sh fast`: 786 run, failures=3 (base paragraph, pointer, licence texts; each on the repo files only), lint PASS, sentinel ok: `docs/evidence/platform-sbom/u1/r1-red-verify-fast.txt`.
- Next: developer pastes `u1/r1-target-notice-sections.md` into NOTICE.md and adds canonical `licenses/Apache-2.0.txt` + `licenses/MPL-2.0.txt` (header comment there).

## 2026-10-22 — developer (U1 rework GREEN)
- NOTICE.md: "Base of ke-app" and "Source code" set to the target text; added a licence-texts line for Apache-2.0/MPL-2.0. Added `licenses/Apache-2.0.txt` (opentelemetry-api 1.45.1) and `licenses/MPL-2.0.txt` (pathspec 1.1.1), untracked: git add at commit. Provenance: `u1/licence-texts-provenance.md`; pip probe: `u1/pip-probe.txt`.
- GREEN `verify.sh fast` PASS: `docs/evidence/platform-sbom/u1/r1-green-verify-fast.txt`. Orchestrator runs full before commit.
## 2026-10-23 — reviewer (U1 re-check)
- CHANGES REQUESTED. B1-B3, N1-N4 resolved (N5 optional, not taken); security M-1/L-1/L-2/L-3 are in NOTICE.md and tested; 71 controls re-run, all as named; RED/GREEN sound; licence files cmp-identical to the locked wheels.
- B4: the NOTICE licence-texts paragraph cites docs/evidence/.../licence-texts-provenance.md, which no bundle carries, and says the two texts cover all pip-vendored packages; make it self-contained (wheel names + uv.lock sha256) and narrow it to Apache-2.0/MPL-2.0. Nits N6-N10 (driver labels, provenance note wrong on Apache newline and MPL bytes, git add + new full, other vendored notices for security, PSC-14 SBOM bullet): docs/evidence/platform-sbom/u1/review.md.
## 2026-10-22 — security (U1 re-check)
- PASS (no critical/high). M-1, L-1 closed; L-3 closed for Python-2.0 and the pointer. NEW M-2 (medium, fix before commit): the CPython bullet says LICENSE.txt holds "the licences of the third-party code CPython bundles", which is false (0 hits; expat 2.8.5 and libmpdec 2.5.1 are compiled in). The clause came from N10. L-5: ship the CPython incorporated-software notices. L-2b: the Apache/MPL texts leave the PSF/BSD/ISC/MIT notices of 9 vendored pip packages unshipped, so "no longer a compliance gap" is wrong; this goes back to the human (ship licenses/pip-25.0.1-vendored.txt, or drop pip). L-6: drop "carries no third-party source code". L-7: Apache-2.0.txt lacks the leading LF of the canonical text; the Debian base-files copy is sha256 cfc7749b...; the provenance note says "trailing", which is wrong. L-8: the Licence-texts paragraph cites a docs/ path that bundles do not carry.
- Exact replacement texts (all pass the 4 checks): docs/evidence/platform-sbom/u1/security.md "Re-check"; scan: u1/security-recheck-scan.txt. I-3 (U9: sources/ is app/sources/), I-4 (git add both texts). orchestrator-verify-full.txt predates the rework; run full again.

## 2026-10-23 — orchestrator (U1 rework round 2 of 5)
- Re-check: review CHANGES REQUESTED (B4 NOTICE cites a repo evidence path; N6-N10);
  security PASS with M-2 (false CPython "bundled code licences" clause), L-2b (pip's
  BSD/ISC/PSF/MIT vendored notices missing: my earlier "no longer a compliance gap"
  was wrong), L-5, L-6, L-7, L-8, I-3 (U9: sources at app/sources/), I-4.
- HUMAN RULING (2026-10-23, supersedes the earlier keep-pip ruling): DROP pip from
  ke-app's shipped stage. Revert the untracked licenses/Apache-2.0.txt and MPL-2.0.txt.
- Orchestrator: also remove ensurepip's bundled pip wheel if present (same vendored
  code); CPython incorporated-software licences ship as
  licenses/CPython-3.12-incorporated.txt from v3.12.15 Doc/license.rst (fetch, sha256,
  security second fetch, Q48); L-6 wording verbatim; U4 check becomes "no pip".
- U1 now changes app.Dockerfile: verify full + A34 Windows proof required.
## 2026-10-23 — analyst (U1 round 2)
- requirements.md (marker "U1 round 2; pip dropped, human"): PSC-14 pip not shipped (last stage removes pip + ensurepip wheel; NOTICE says so; no pip licence texts; `test_ke_app_last_stage_removes_pip`, `[full: smoke: no pip in api]`; `test_licenses_carry_texts_for_pip_vendored_licences` retired; follow-up DONE); CPython LICENSE.txt = PSF stack only + `licenses/CPython-3.12-incorporated.txt` from v3.12.15 Doc/license.rst, Q48 fetch (`test_notice_names_cpython_incorporated_licences`); L-6 sentence verbatim; B4 `test_notice_cites_no_repo_evidence_path`; N10 SBOM wording permanent.
- PSC-22 U4: SBOM lists no pip + CPython version matches the file; PSC-15 I-3 `app/sources/` (U9); PSC-25 static test allows the libpq5 RUN plus the pip removal only. Open: exact removal paths and smoke probe are design (architect/tester).
## 2026-10-22 — architect (U1 round 2)
- ADR-KE-016 point 9 (189 lines) and design-notes N10/N10a/N15: a delete in any stage FROM the base still ships pip (docker save keeps the base layer: 536 pip entries; syft all-layers sees them), so stage `runtime` runs `python -m pip uninstall -y pip && rm .../ensurepip/_bundled/pip-*.whl` (wheel exists, 1,841,526 B) and the last stage is `FROM scratch` + `COPY --from=runtime / /`; this amends D10 and needs the U0/D10/digest/notice static tests re-targeted (N10a). Smoke `no pip` in api; CPython-3.12-incorporated.txt from raw v3.12.15 Doc/license.rst (heading to EOF, header, Q48 + python.org tarball vs PYTHON_SHA256); U4 no pip + CPython version; I-3 paths relative to app/. U1 now full, A34.
- Next: orchestrator confirms the D10 amendment and files the probe (scratchpad r2-pip-probe.txt, path in report) as u1/r2-pip-probe.txt; tester re-targets the four tests; security: HACL* is absent from v3.12.15's list.

## 2026-10-23 — orchestrator (ruling: flatten ke-app)
- Architect found a layer-delete leaves pip in the base layer of the saved tar
  (536 entries; syft all-layers would list it). Ruling: CONFIRM the flattened last
  stage (`runtime` stage FROM the pinned base runs libpq5 + pip removal; last stage
  FROM scratch + COPY --from=runtime / /, ENV re-set). It amends ADR-KE-013 am.1
  D10; the architect records that amendment. Probe filed as u1/r2-pip-probe.txt.
