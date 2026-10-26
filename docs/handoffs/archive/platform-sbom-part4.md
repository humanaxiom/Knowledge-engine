# Handoff archive: platform-sbom part 4 (U1 rework rounds 2-4 and re-checks)

## 2026-10-23 — tester (U1 round 2 RED)
- RED `scripts/verify.sh fast` (`u1/r2-red-verify-fast.txt`): 791 tests, 8 methods / 22 subtests fail, all U1 round 2. New: `test_ke_app_last_stage_removes_pip` and 3 smoke tests in `tests/test_ke_app_no_pip.py`, plus `test_notice_names_cpython_incorporated_licences` and `test_notice_cites_no_repo_evidence_path`. Updated: the base test (M-2, no pip) and the pointer test (L-6). Sentinel ok; lint PASS.
- Retired `test_licenses_carry_texts_for_pip_vendored_licences` (PSC-14). Re-targeted, green today and on the N10a target: `test_runtime_stage_has_no_compiler`, D10 test 1 (`final_stage_problems`), `test_dockerfiles_pin_base_images_by_digest` (exactly `scratch` allowed), and the notice base read via `test_psycopg_c.shipped_stage`.
- Controls driver `u1/u1_controls.py`: 233 controls (212 must-fail, 21 must-pass), 0 unexpected; 9/9 smoke mutants killed. Reach: the targets pass every check, the static classes and all smoke suites (`u1/r2-red-mutants.txt`).
- For the developer: `u1/r2-target-app.Dockerfile`, `r2-target-notice-sections.md` (NOTICE from `## Base of` to the end, plus the licence-file header), `r2-target-smoke-block.sh` (insert after the psycopg step). fake_docker gains FAKE_API_FILES and FAKE_API_PIP_IMPORTABLE.
- Ruling (orchestrator, 2026-10-23): empty no-pip output FAILS. This supersedes N10a's `${pip_hits:--}` (design-note owner: please amend N10a). New subtest `test_smoke_fails_when_pip_is_in_api` (case='the check exits 0 and prints nothing'). The target compares `"$pip_hits"` to `-` exactly. Mutant S10 (default restored) is killed. RED re-run: 8 methods / 23 subtests.
- Open: `licenses/Apache-2.0.txt` and `MPL-2.0.txt` are still untracked in the tree, and the base test fails while NOTICE names them. The real licence extract is the maintainer's fetch.

## 2026-10-22 — developer (U1 round 2 GREEN)
- Applied the tester targets: `app.Dockerfile` (`runtime` stage, pip removed, `FROM scratch` flatten; ENV: kept PATH/LANG, dropped GPG_KEY, PYTHON_VERSION, PYTHON_SHA256 as build-only), smoke `no pip` step, NOTICE sections. No test changed.
- `licenses/CPython-3.12-incorporated.txt` fetched; sha256s equal the probe (`u1/cpython-incorporated-provenance.md`). Apache/MPL files deleted; `licence-texts-provenance.md` marked superseded.
- GREEN: `verify.sh fast` PASS (`u1/r2-green-verify-fast.txt`); `verify.sh full` PASS 718 s (`u1/r2-green-verify-full.txt`), no pip smoke on host and offline client, scan under unchanged policy. Tar 58,818,048 -> 54,872,576 B (`u1/size.md`). Not committed.
## 2026-10-23 — reviewer (U1 re-check 2)
- CHANGES REQUESTED (doc-only). B4 resolved; N7, N9 superseded; N10 resolved. Dockerfile flatten, the ENV drop (safe; nothing reads GPG_KEY/PYTHON_*; the base's only other config is Cmd), the no-pip smoke (empty output fails), NOTICE, and the licence extract (independent fetch: sha256 equal, cmp-identical) all sound. 233 controls as named. RED 23 / GREEN fast and full sound. B5: PSC-14/PSC-25 still say "last stage" for the pip removal and libpq5; the tests require `runtime` (analyst rewords). B6: N10a l.747 still shows the overruled `${pip_hits:--}` (architect amends).
- Nits: N6 driver labels; N11 stale "next"; N12 git add the licence file and the 2 test modules, then run verify full; N13 record the base `.Config`. Detail: docs/evidence/platform-sbom/u1/review.md "Re-check 2".

## 2026-10-22 — security (U1 re-check 2)
- PASS, no critical or high. Q48 second fetch CONFIRMED: the python.org tarball sha256 equals the base's PYTHON_SHA256, license.rst equals the header sha256, and the extract `cmp`-equals the file body (`u1/security-cpython-second-fetch.txt`). The saved tar has 5 layers and 0 pip paths or whiteouts. setuid, writable paths, dpkg and uid 10001 are unchanged. pip's 6 GHSAs are gone (`u1/security-recheck2-probes.txt`). M-2, L-5, L-6, L-8 and L-2b are closed.
- New, non-blocking: L-9 (HACL* MIT notice missing upstream; add `licenses/CPython-3.12-HACL.txt` or reword NOTICE), L-12 (pin check accepts `FROM x AS x`; predates this change), I-5 (.pyc) and I-6 (first-line read). I-4 at commit: `git add` the CPython licence file and re-run `verify.sh full` after the add (details: `u1/security.md` Re-check 2).

## 2026-10-23 — tester (U1 Windows proof)
- A34 PASS (`u1/windows-run.txt`): U0 driver on this tree, own project `ke-tester-u1win`, tag `u1win-31bfed4`. build/launch/teardown(-Volumes) exit 0, 7/7 healthy, refusal exit 1, Windows tests 7 OK, `verify.sh fast` PASS (791). 4b psycopg `c 150019` on dpkg libpq5 15.19-0+deb12u1. 4c `find_spec('pip')` None (api python and `/usr/local/bin/python3 -I`, worker); `_bundled/` empty; history 8 last-stage entries, `COPY / /` 134 MB, 5 RootFS layers.
- Run tied to sha256s, identical at start and end (app.Dockerfile 128c5dbe…, uv.lock feff8833…, pyproject 80d17709…, smoke.sh c3a328e6…). If any of these changes, the proof is stale. Build was a BuildKit cache hit. Teardown left 0 containers, networks, volumes or images for the project, and no `.env`.

## 2026-10-23 — orchestrator (U1 rework round 3 of 5)
- Re-check 2: review CHANGES REQUESTED (B5 PSC-14/25 still say "last stage"; B6 N10a
  snippet keeps ${pip_hits:--}; N6, N11-N13); security PASS (L-9 HACL* MIT notice
  missing from CPython's list; L-12; I-4 untracked licence file; I-5; I-6).
- Round 3 (Dockerfile unchanged, so the running A34 proof stays valid): analyst B5;
  architect B6 + L-9 design; tester RED: test_notice_named_licence_files_are_tracked,
  HACL file check, I-6 whole-output subtest, L-12 controls, N6 relabel; developer:
  licenses/CPython-3.12-HACL.txt from the verified tarball, smoke I-6, git add of the
  new licence/test files, N13 base-config probe. I-5 (.pyc from pip uninstall) is a
  follow-up. Correction (N11): "U1 so far" next-step is superseded by this section.

## 2026-10-23 — analyst (U1 round 3)
- requirements.md: B5 PSC-14/25 say "shipped stage (`runtime`...; N10a)", test names kept; L-9 `licenses/CPython-3.12-HACL.txt` + notice test extended; I-4 `test_notice_named_licence_files_are_tracked`; I-5 under new "Follow-ups (not in platform-sbom)".

## 2026-10-22 — architect (U1 round 3)
- design-notes N10a: B6/I-6 smoke is `[ "$pip_out" = - ] || FAIL` (empty or a 2nd line fails), I-5 `.pyc` follow-up line, HACL file design (extract `sed -n '1,/^ \*\/$/p'` of `Modules/_hacl/Hacl_Hash_SHA2.c`, 23 lines, sha256 `998ce04f...d78c`; 4-line header); N10 NOTICE wording claims no complete set; ADR-KE-016 pt 9 same length. Open for security: 5 Apache-2.0 KaRaMeL headers in `_hacl/include/krml/`.

## 2026-10-23 — tester (U1 round 3 RED)
- RED `verify.sh fast` (`u1/r3-red-verify-fast.txt`): 792 ran, 4 methods / 5 failures, all round 3, sentinel ok, lint PASS. HACL check + CPython-bullet wording (`test_notice_names_cpython_incorporated_licences`); `test_notice_named_licence_files_are_tracked` (new; incorporated file untracked); I-6 subtest `-` + second line (smoke reads line 1); L-12 x2 in `test_dockerfiles_pin_base_images_by_digest`.
- L-12 is a real gap: `unpinned_bases` (test code, `tests/test_stack_compose.py`) counts any `AS` name as a stage. Developer fixes it there (earlier-line rule; the driver's reach probe passes all 14 controls and 3 Dockerfiles).
- Targets: `u1/r3-target-notice.md` (CPython bullet, HACL Licence-texts paragraph, HACL header), `r3-target-smoke-block.sh` (replaces the no-pip step; `[ "$pip_out" = - ]`), `r3-target-CPython-3.12-HACL.txt` (scratch, from the architect's extract). Then `git add` both licence files and the two test modules.
- Driver `u1/u1_controls.py`: REPO rows expect GREEN (N6); `--red` labels round 3's RED. 291 controls, 0 unexpected; 12/12 smoke mutants killed; reach green (`u1/r3-red-mutants.txt`).
- L-12 fixed by the tester (coordinator ruling: test code): `unpinned_bases` counts a stage only if an earlier FROM defines it; driver `--only=digest` GREEN mode 10+4, 0 unexpected, 3 repo Dockerfiles pass (`u1/r3-red-mutants.txt` addendum). RED is now 3 methods / 3 failures.

## 2026-10-22 — developer (U1 round 3 GREEN)
- HACL file built from the verified tarball (sha256 c2c43219...94fd5a; extract 23 lines, 998ce04f...d78c; final d83382d7...c483, cmp-equal to the tester's target); NOTICE CPython bullet + HACL sentence; smoke no-pip whole-output `-` compare; 4 files git-added (not committed); base-config.json saved (N13).
- `verify.sh fast` PASS (rc 0, incl. L-12 controls): `u1/r3-green-verify-fast.txt`; provenance `u1/cpython-hacl-provenance.md`. Orchestrator runs full at the gate.

## 2026-10-22 — reviewer (U1 re-check 3)
- APPROVED for commit, provided the orchestrator's `verify.sh full` on this index passes. B5, B6, N6, N11, N12 and N13 are resolved. L-9 (HACL file independently re-fetched, `cmp`-equal), L-12, I-4 and I-6 are handled. The driver exits 0 (291 controls, 0 unexpected). app.Dockerfile, uv.lock and pyproject sha256 equal the A34 proof, so A34 stands.
- Nits: N14 (base-config.json has no command recorded); N15 (5 KaRaMeL Apache-2.0 krml headers, for security to rule on); commit must stage `u1/` and archive part2/part3, not NEXT-SESSION.md. Detail: docs/evidence/platform-sbom/u1/review.md "Re-check 3".

## 2026-10-23 — security (U1 re-check 3)
- PASS, no critical or high. HACL second fetch CONFIRMED: my tarball c2c43219...94fd5a, `sed` extract 998ce04f...d78c `cmp`-equal to `tail -n +6` of the file. Closed: L-9, L-12 (forward and self-named stages flagged), I-4 (the tracked-licence test is enough; no bundle.sh l.195 change), I-6 (the whole-output `= -` fails on empty and second-line output, and is injection-safe). NOTICE is true and claims no complete set. Evidence sweep clean.
- KaRaMeL ruling: YES. The Apache-2.0 macros and the inline `FStar_UInt128_add` from `_hacl/include/krml/` are compiled into `_md5`, `_sha1`, `_sha2` and `_sha3`. That is new L-9b (low): add `licenses/Apache-2.0.txt` (base-files, cfc7749b...d30), add `licenses/CPython-3.12-KaRaMeL.txt`, and reword NOTICE; exact text in `u1/security.md` Re-check 3, probes in `u1/security-recheck3-probes.txt`. Info: I-7 (optional bundle.sh twin), I-8 (wording, folded into L-9b).

## 2026-10-23 — orchestrator (U1 rework round 4 of 5)
- Re-check 3: review APPROVED; security PASS with L-9b (KaRaMeL headers are compiled
  into _md5/_sha1/_sha2/_sha3, Apache-2.0, not attributed in NOTICE). Fix before
  commit per security's exact text: licenses/CPython-3.12-KaRaMeL.txt (sibling,
  extract of krml/internal/target.h), licenses/Apache-2.0.txt (offline byte copy of
  the base's /usr/share/common-licenses/Apache-2.0, sha256 cfc7749b...), NOTICE
  CPython bullet + two Licence-texts paragraphs. Tester RED first, then developer.

## 2026-10-23 — analyst (U1 round 4)
- PSC-14 amended per security L-9b: new KaRaMeL sub-bullet (ships `licenses/CPython-3.12-KaRaMeL.txt`, 4-line header + `krml/internal/target.h` extract; `licenses/Apache-2.0.txt`, offline byte copy of base-files 12.4+deb12u15 `/usr/share/common-licenses/Apache-2.0`, sha256 cfc7749b...); NOTICE names all four licence files; `test_notice_names_cpython_incorporated_licences` extended to both; pip bullet keeps "no Apache-2.0 for pip" and adds that Apache-2.0.txt ships for KaRaMeL. Next: tester RED, then developer.

## 2026-10-23 — tester (U1 round 4 RED)
- RED `verify.sh fast` (`u1/r4-red-verify-fast.txt`): 792 ran, 1 method / 2 subtest failures, lint PASS: `test_notice_names_cpython_incorporated_licences` repository='HACL' (I-8 wording) and repository='KaRaMeL and Apache-2.0' (new `karamel_licence_problems`: bullet lacks KaRaMeL/INRIA and Microsoft/Apache-2.0/both paths; both files missing; no Apache paragraph). Contradiction resolved in the base check (cite PSC-14 round 4, L-9b fix 5): Apache-2.0.txt allowed only beside KaRaMeL/base-files, never pip; MPL-2.0.txt never.
- Developer targets: `u1/r4-target-notice.md` (bullet, 2 Licence-texts paragraphs, KaRaMeL header), `r4-target-CPython-3.12-KaRaMeL.txt` (scratch build, 3230026...796d), Apache via security's offline docker command (cfc7749b...d30); `git add` both. Driver `--red --reach` in the gates image: 350 controls, 0 unexpected, reach 15/15 checks + 17/17 static, 12/12 smoke mutants (`u1/r4-red-mutants.txt`).

## 2026-10-23 — developer (U1 round 4 GREEN)
- Built `licenses/Apache-2.0.txt` (11358 B, cfc7749b...d30, offline docker cat) and `licenses/CPython-3.12-KaRaMeL.txt` (3230026...796d, `cmp`-equal to target; extract 2 lines 6b7cb4bd...8a26 from re-fetched tarball c2c43219...94fd5a); NOTICE bullet + 2 Licence-texts paragraphs; 3 files git-added, not committed.
- `verify.sh fast` PASS: `u1/r4-green-verify-fast.txt`; provenance `u1/cpython-karamel-provenance.md`. Orchestrator runs full.

## 2026-10-23 — reviewer (U1 re-check 4)
- APPROVED, provided the orchestrator's verify full passes. L-9b and I-8 are done: the KaRaMeL and Apache files are hash-verified and staged, the NOTICE is true, and the Apache rule matches PSC-14 round 4. Driver default mode: exit 0, 350 controls, 0 unexpected. RED 2 subtests, GREEN 792 OK. A34 hashes are unchanged. Nit N16 (the indent is not pinned). Detail: u1/review.md "Re-check 4".

## 2026-10-23 — security (U1 re-check 4)
- PASS, L-9b closed: Apache-2.0.txt cmp-equal to pinned base (cfc7749b...d30); KaRaMeL extract+header cmp-equal; NOTICE fix 3/4 text exact; 4 licence files staged, 0 CR; r4 evidence clean. `u1/security.md` Re-check 4, probes `u1/security-recheck4-probes.txt`.
