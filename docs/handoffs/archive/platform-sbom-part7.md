U4 rework close-out, U4 commit gate, session checkpoint, and U4b to GREEN

## 2026-10-23 — developer (U4 rework GREEN)
- Applied the 5 r1 targets unchanged (modes 755 kept); B2 already absent in the target; added the N8 comment above `sbom_cleanup`. No test changed.
- verify fast PASS, verify full PASS (937 s); no "unable to get filesystem cache"; drift summary line present; unlicensed ke-app 19, gateway 0, neo4j 28, phoenix 35, postgres 25, valkey 1.
- Evidence: u4/r1-green-verify-fast.txt, r1-green-verify-full.txt, r1-real-run-report.txt (security re-review). Next: reviewer + security; redo A34 2b/3b.

## 2026-10-23 — security (U4 re-check)
- PASS. Closed: H-1 (independent recount: 59 hash rows, none hidden; 19/0/28/35/25/1), M-1, M-2, L-1, L-2 (probe: /tmp is noexec,nosuid,nodev, mode 1777) and L-3. M-3 is with the human (Q67, U4b). Per-image unlicensed review: all six accepted, no new `always` needed (hash rows go to source via N8/U7 deb; krb5, libxslt1.1 and pandas may be exempted at U6).
- Non-blocking for U5: L-4, so that declared `<hash>` + concluded `MIT` does not classify as MIT (pin it in N8 and add a test row). Carry: L-5, escape `validate`'s `sid` and drift's names with `_clean` and use `fullmatch`. Evidence: u4/security.md "Re-check", u4/r1-security-probes.txt.

## 2026-10-23 — reviewer (U4 re-check)
- APPROVED: B1, B2 and N1-N8 closed; H-1, M-1, M-2, L-1 and L-3 verified (25 `always` entries match the fixtures; fixtures equal the U3 blobs). Controls `r1 --base repo`: 61 rows, 0 unexpected. Full run: 0 cache warnings, summary line, counts 19/0/28/35/25/1.
- Nits: R1 PSC-22 test names; R2 escaping (= security L-5); R3 stale `u4_controls.py` anchor. Detail in `u4/review.md` "Re-check"; A34 2b/3b still pending.

## 2026-10-23 — tester (U4 rework Windows proof)
- A34 PASS (`u4/r1-windows-run.txt`; project ke-tester-u4r1win, 28 files hashed, identical start/end). 2b: tmpfs `/tmp:mode=1777` resolves from Windows PowerShell. 3b: bundle.sh wrote 6 valid SBOMs; "unable to get filesystem cache" count 0 (the drift base run also 0); unlicensed ke-app 19, ke-gateway 0, neo4j 28, phoenix 35, postgres 25, valkey 1; drift `ok` summary line printed; controls exit 1. verify fast PASS (851). Teardown left nothing; the bundle tags were restored.
- A tester sed bug in the first 3b count compare (it missed the by-type suffix) is recorded; the addendum re-ran the compare on the same raw output and the counts are equal. Next: reviewer + security verdicts, then orchestrator verify full.

## 2026-10-23 — orchestrator (U4 commit gate)
- Review APPROVED (re-check; R1 fixed in PSC-22, R2/R3 carried to U5), security PASS
  (re-check: H-1 closed, all six unlicensed lists accepted; L-4, L-5, I-4 carried to
  U5 in PSC-22), A34 re-proof PASS (0 cache warnings on Windows). Rework rounds 1 of 5.
- Orchestrator verify full PASS 896 s (851 unit + 15 integration; drift ok; counts
  19/0/28/35/25/1; 0 cache warnings; `u4/orchestrator-verify-full.txt`). Diff read.
- Accepted: the 16-hex `LicenseRef-` row meets PSC-22's "non-hash LicenseRef" control;
  a named-ref fixture row is a U5 nicety.
- Commit APPROVED: U4 (PSC-22). Next: U4b (PSC-26 own neo4j image, design N16).

## 2026-10-23 — orchestrator (session checkpoint)
- U0-U4 committed locally (31bfed4, 23e3c9b, 98b6d27, 464fa11, 40e2181), not pushed.
  U4b RED was running at checkpoint. Next-session brief: `docs/handoffs/NEXT-SESSION.md`
  (untracked) with order of work, human decisions pending (push; GCC source vs
  exemption before U7; scan every bundled image; CLAUDE.md at U8; Q62 at U11) and the
  standing rules learned this session.

## 2026-10-23 — tester (U4b RED)
- RED `verify.sh fast` FAIL as expected (`u4b/red-verify-fast.txt`): 29 tests, all U4b: 18 new in `tests/test_neo4j_image.py` (PSC-26 tags; install guard green) + 11 re-targeted (notices, first-party lists, `always` names, bundle image name `ke-neo4j`, offline pull order). Fake docker: neo4j `find` model, `FAKE_IMAGE_CONFIGS`; `tests/neo4j_support.py`.
- Targets `u4b/target-*` (N16 Dockerfile, compose, build headers, NOTICE "Base image of `ke-neo4j`", policy rename, smoke step, offline_check ke-neo4j step, `sbom_check.py neo4j`/`tree`). bundle.sh, install.sh/.ps1 unchanged (N16). Reach (`u4b/target-reach-verify-fast.txt`): only `test_no_hardcoded_ports` red. Controls `u4b/red-mutants.txt`: 55 rows, 0 unexpected.
- GREEN blocker (architect): `EXPOSE 7687` (N16, config parity) trips PS-1.2 `test_no_hardcoded_ports` (7687 is defaults.yaml's neo4j port); needs a recorded exemption or ADR ruling, not a test edit.
- Flags (architect): N16 places no `full` run for config/tar/SBOM checks; tester put them in offline_check after drift (official image pulled by digest before bundle.sh). File tree is "evidence, not a gate step" in N16 vs PSC-26 `[full]` (logic tested, not wired). PSC-26 says NOTICE "row", N16 a section (tests follow N16). Labels excluded from config compare (compose adds them).
- After ruling 1: PS-1.2 EXEMPTIONS entry (docker/neo4j.Dockerfile, exact line `EXPOSE 7473 7474 7687`; the scanner's Dockerfile form is exact-line only) + control test; reach `verify fast` PASS (871), RED re-run: same 29 U4b failures (`u4b/red-verify-fast.txt`); controls 61 rows, 0 unexpected.

## 2026-10-23 — orchestrator (U4b rulings on the tester's 6 points)
- (1) EXPOSE 7473/7474/7687 in docker/neo4j.Dockerfile: a recorded PS-1.2 exemption
  (the line mirrors the pinned official image's metadata, not a configurable port);
  tester adds the EXEMPTIONS entry, security reviews; the hardcoded test is not weakened.
- (2) config/tar/SBOM `full` checks run in offline_check.sh after drift as pinned
  (`sbom_check.py neo4j`); official neo4j pulled by digest before bundle.sh. Accepted.
- (3) file-tree equality: evidence at GREEN + A34, not a per-run gate (CI cost, Q62);
  analyst amends PSC-26's [full] tag to evidence.
- (4) NOTICE: N16's "Base image of ke-neo4j" section; analyst finalises wording.
- (5) Labels excluded from the config comparison (compose adds its own). (6) Installers
  and bundle.sh unchanged: accepted.

## 2026-10-23 — developer (U4b GREEN)
- Targets applied unchanged (9 files, scripts at 755). verify fast PASS, full PASS (990 s, 871 + 15 tests): `u4b/green-verify-fast.txt`, `u4b/green-verify-full.txt`. No test changed.
- ke-neo4j config identical to the official image's; tar has no products/fleet path; tree = official minus products/ (+2 jars), 0 attribute diffs; `sbom_check.py tree` ok: `u4b/file-tree-evidence.txt`.
- ke-neo4j unlicensed 27 (neo4j was 28). tar 351.9 MB vs official 356.0 MB (-1.15%).
