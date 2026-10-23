U3 commit gate and U4 sections up to rework round 1 RED

## 2026-10-23 — orchestrator (U3 commit gate)
- Review APPROVED (0 rework rounds; nits carried to U4), security PASS (M-1 resolved by
  regenerating evidence from fresh images; redaction fixed), A34 PASS (bundle.sh wrote 6
  valid SBOMs on Windows), ruling 5 decided (architect, implemented U4-U7).
- Orchestrator verify full PASS 856 s (812 unit + 15 integration; offline_check 168 s,
  was 95 s at U2: the SBOM stage adds ~73 s locally, PSC-16/Q62 measure on CI at U11).
- Commit APPROVED: U3 (PSC-13). Next: U4 (PSC-22 + the carry list above).

## 2026-10-23 — tester (U4 RED)
- New `tests/test_sbom_obligations.py` (18 tests; interface in its docstring) + `tests/sbom_support.py`; harness: `test_offline_check.py` stub bundle now writes bundle.json and a valid ke-app SBOM, fake `save` refuses an absent image, fake syft logs work-dir modes.
- RED `u4/red-verify-fast.txt`: 15 tests fail, all U4 (30 subtest entries); 3 carry tests (cygpath, MSYS_NO_PATHCONV, chmod 0700) green on arrival. Reach `u4/target-reach-verify-fast.txt` PASS (830 tests); targets `u4/target-*` incl. `target-source-policy.json`.
- Controls `u4/red-mutants.txt`: 190 rows, 0 unexpected (66 U4 + 124 U3 folded from the reviewer's anchors, review N9).
- Ambiguities for the architect: `always` is U6 in N15 (pinned here at U4); libldap/libsasl2 in `always` vs N10's classifier; report printed by bundle.sh (index copy U9); N8 "third field" read as licenseInfoFromFiles; N6 work dir pinned beside --out; drift step in offline_check before dind; who puts the base image on a CI daemon (never pulled here).
- Developer also: review N1 (sbom_check.py l.21 docstring), N2 (bundle.sh L-13 comment). Documenter: Windows build hosts need jq on PATH, and `jq.exe -b`.
- Re-targeted to ruling 6 and the architect's U4 rulings: the base is pulled by digest after the generator pull and before bundle.sh (events: pull sbom, pull base, bundle, drift); unpinned-ref and pull-failure tests; the exact N8 type rule; N7 accepts forked names. RED: 18 failing (17 U4 + the re-targeted `test_offline_check_pulls_sbom_generator_before_bundle`); reach PASS (832); controls 203 rows, 0 unexpected; files overwritten in `u4/`.

## 2026-10-23 — orchestrator (U4 rulings on the tester's 8 points)
- Accepted as pinned: (1) `always` key of docker/source-policy.json arrives at U4 (U6
  adds hosts/exempt); (2) libldap-2.5-0 + libsasl2 pkgs in `always` (PSC-22 + I-1);
  (3) unlicensed report = bundle.sh output at U4, index at U9; (5) SBOM work dir under
  dirname(--out), outside --out (review N6); (7) the base SBOM run inherits the offline
  project; (8) ADDED_PACKAGES read by AST from tests/test_notice_ke_app.py.
- (4) architect confirms the third "unlicensed" field (licenseInfoFromFiles).
- (6) RULING: offline_check.sh PULLS the ke-app base by its pinned digest before the
  drift step (fail closed, no retry), like the syft interim pull; never relies on the
  BuildKit cache having it. Tester re-targets the exact-events test accordingly.

## 2026-10-23 — architect (U4 rulings)
- Point 4 CONFIRMED (N8 exact rule): unlicensed = declared and concluded each absent/null/""/"NONE"/"NOASSERTION" (exact, case-sensitive) AND licenseInfoFromFiles absent/null/[]/all entries missing; tightening: wrong-typed values count as missing (no crash). syft 1.54.1 emits no licenseInfoFromFiles. Review N7: lock = name -> set of versions, forked names accepted (N7).
- Point 6 (N1 am. U4): base pulled by digest right after the generator pull, before bundle.sh; stays in offline_check.sh after U8 (bundle_fetch.sh fetches bundle inputs only); Docker Hub, host half, no CLAUDE.md change. Work dir `.ke-sbom.*` in dirname(--out): the 7 GiB floor covers it. N10: openldap/cyrus-sasl2 in ke-app `always` supersede "classifier"; postgres has the same 3 (flag, orchestrator's call). ADR-KE-016 pts 8 + TDD units amended (200 lines).

## 2026-10-23 — developer (U4 GREEN)
- Targets applied unchanged (sbom_check.py, bundle.sh, offline_check.sh, compose XDG_CACHE_HOME, docker/source-policy.json); no test touched. verify fast PASS (832 tests, 598 s), full PASS (923 s; offline_check 192 s); `docker save` of `name:tag@digest` works on the containerd store, no --platform needed.
- Real drift check passes on the ke-app SBOM (one success line; the checker is silent on the sub-checks); unlicensed: ke-app 1, ke-gateway 0, neo4j 19, phoenix 25, postgres 3, valkey 1. Evidence: `u4/green-verify-full.txt`, `u4/real-run-report.txt`.
- Open: syft warns `unable to create directory at '/tmp/cache/syft': mkdir /tmp/cache: permission denied` (tmpfs /tmp not writable by uid:gid on Docker Desktop; fix would be `/tmp:mode=1777`, not in targets, not done). Base pull ~1 s cached, drift step ~4 s.

## 2026-10-23 — reviewer (U4)
- CHANGES REQUESTED (`u4/review.md`): B1 XDG_CACHE_HOME inert (the cache warning moved, it did not go): add `/tmp:mode=1777` to sbom's tmpfs, test first (PS-3.5 precedent; U2 test allows it). B2 U3 N1 not closed: drop the tester note at sbom_check.py l.30. Nits N1-N8 (forked psycopg-c lock, upstream `@` split, ast/TypeError wrap, externalRefs guard, floor probe when --out is an existing mount, drift success summary, checker --label, `down` raw-path comment). Controls `--base repo`: 203 rows, 0 unexpected. All 16 `always` entries match the real U3 SBOMs. Linux classic-store save and tmpfs mode go to the PR CI run.

## 2026-10-23 — security (U4)
- FAIL: H-1 (syft hash-only `LicenseRef-<64 hex>` rows, 59 of them incl. wget GPL-3 in neo4j and the GCC runtime, escape the unlicensed report and N8). Fix in `_missing` + test; N8 amendment. M-1 gcc `always`, M-2 jrt-fs, M-3 neo4j commercial fleet jar (human); L-1 upstream=busybox/apk-tools, L-2 add `/tmp:mode=1777`, L-3 escape report lines.
- Lists: ke-gateway, valkey accepted; ke-app, neo4j (20->19 = oci root, explained), phoenix, postgres reported rows reviewed, accepted after H-1. Base pull and drift step: no finding. `u4/security.md`, `u4/security-probes.txt`.

## 2026-10-23 — tester (U4 Windows proof)
- A34 PASS (`u4/windows-run.txt`; tree tied by 8 sha256): 2b shows XDG_CACHE_HOME=/tmp/cache on Windows; bundle.sh 109 s, 6 valid SBOMs; unlicensed ke-app 1, ke-gateway 0, neo4j 19, phoenix 25, postgres 3, valkey 1; drift per offline_check.sh (warm pull, save, base SBOM, `sbom_check.py drift`) exit 0, 2 negative controls exit 1; up/down/Windows tests, verify fast (832) PASS; teardown left nothing, tags restored.
- Cache warning still printed (`mkdir /tmp/cache: permission denied`, 7/7 runs): the syft image's /tmp is 0755 root and the tmpfs takes that mode; `--tmpfs /tmp:mode=1777` removes it (3c; supports review B1). Changing the compose file makes this proof stale: re-run 2b+3b. Cold base pull not exercised.

## 2026-10-23 — orchestrator (U4 rework round 1 of 5; human ruling M-3)
- Review CHANGES REQUESTED (B1 XDG_CACHE_HOME no-op, B2 stale docstring; N1-N8);
  security FAIL H-1 (59 hash-only `LicenseRef-<64hex>` rows hidden from the report and
  from N8's classifier; real GPL among them) + M-1 (GCC runtime gcc-12/gcc-14 not in
  `always`), M-2 (neo4j jrt-fs = Temurin, GPL-2.0+CE), M-3, L-1 (busybox-binsh,
  libapk), L-3 (escape report output). A34 PASS (and root cause of B1: syft image /tmp
  is 0755; `--tmpfs /tmp:mode=1777` fixes it).
- HUMAN RULING M-3 (2026-10-23): build our own neo4j image without the commercial
  fleet-management plugin (products/ removed, flattened FROM scratch). New unit U4b
  after U4; analyst adds the criterion, architect designs.
- Round 1 fixes: B1 tmpfs `/tmp:mode=1777` (both reviewers + A34 evidence); B2; H-1 a
  licence made only of `LicenseRef-[0-9a-f]{64}` ids counts as unlicensed (report +
  N8 for U5 sends them to security as unknowns); M-1/M-2/L-1 `always` entries; L-3;
  review N1-N4, N6 summary line, N7 label, N8 comment; N5 to the architect.

## 2026-10-23 — analyst (Q67, PSC-26, PSC-22 amends)
- Q67 recorded resolved (A67: own neo4j image, `products/` removed, flattened); PSC-26 (U4b, after U4, before U5): `ke-neo4j` tags, config/file-tree parity vs the official image, plugin absent from image + every tar layer + SBOM, first-party bundle with no official neo4j tar, compose `build:`, NOTICE row re-keyed, A34 `u4b/windows-run.txt`, arm64, 3 unit + 4 full tests. PSC-13/PSC-14 cross-refs.
- PSC-22 amended (U4 review): H-1 hash-only `LicenseRef-[0-9a-f]{64}` = unlicensed (+ controls), `always` gcc-12/gcc-14, jrt-fs, upstream=busybox/apk-tools, report escapes C0/C1 (L-3). OPEN Q68 (scan fail mode for ke-neo4j; rec. option 1, PSC-4/5 as ke-app), must be ruled before U4b RED.
- Q68 recorded resolved (A68, orchestrator: option 3, ke-neo4j not scanned in U4b; scan stays ke-app only); PSC-26 *Scanned* bullet replaced by *Not scanned in U4b (Q68)*; follow-up "Scan every bundled image" (human, CI cost measured first) added.

## 2026-10-23 — orchestrator (Q68)
- Q68 RULED option 3 (orchestrator, 2026-10-23): U4b does not add ke-neo4j to the
  image scan; scope stays as today (scan.sh scans ke-app only; ke-gateway and the
  vendored images are not scanned either). Reason: option 1 would likely turn every
  full run red on upstream jar CVEs only a Neo4j digest bump can fix; option 2 changes
  the Q42 policy (human's call). Follow-up for the human with measured cost: scan
  every bundled image (report-only or fail mode). Analyst records Q68 + the follow-up.

## 2026-10-23 — architect (U4 rework + U4b design)
- U4 rework (design-notes N1 am. U4 rework, N8, N10, N15): hash-only `LicenseRef-<64 hex>` = missing in the report, unknown (source or reviewed exempt) at U5; `sbom` tmpfs `/tmp:mode=1777` (image /tmp 0755); N5: floor measured on `--out` AND `dirname(--out)`, lands this round; `always` + gcc-12/gcc-14, jrt-fs, upstream=busybox/apk-tools; GCC runtime ships Debian source (deb, U7), no RLE exemption.
- U4b (N16, ADR-KE-016 pt 12): `ke-neo4j` = pinned neo4j minus `/var/lib/neo4j/products/` (fleet + GenAI jars, the only 2 files), FROM scratch + COPY, config re-set (7 ENV, ENTRYPOINT tini, CMD neo4j, WORKDIR, VOLUME /data /logs, EXPOSE 7473/7474/7687, no USER); first-party like ke-gateway, no install change; policy keys neo4j -> ke-neo4j; loop full, A34 yes. ADR 200 lines.

## 2026-10-23 — tester (U4 rework RED)
- New in `tests/test_sbom_obligations.py` (classes `ReworkR1*`, interface in the docstring's last section) + fixtures `tests/fixtures/sbom-u3/*.pkgs.tsv` (byte copies of u3 lists) + fake syft cache model in `tests/fake_docker.py`. H-1 per architect N8 (split on whitespace/parens, drop AND/OR/WITH any case + WITH's exception); marker `(unidentified licence text)` per row; L-3 no C0/C1 in report lines; B1 tmpfs exactly `/tmp:mode=1777` + no cache WARN (fake-modelled, bundle and offline drift runs); N5 floor on `--out` and `dirname(--out)`; N1-N4, N6 (one `drift` summary line), N7 (label `<project>[-x]`).
- RED `u4/r1-red-verify-fast.txt`: 851 tests, 16 distinct tests fail (29 entries), all `ReworkR1*`, none else. Reach `u4/r1-target-reach-verify-fast.txt` PASS (851, targets `u4/r1-target-*` incl. bundle.sh, restored after). Real counts with the target (`u4/r1-real-counts.txt`): ke-app 19, ke-gateway 0, neo4j 28, phoenix 35, postgres 25, valkey 1 = security's.
- Controls `u4/r1-red-mutants.txt` (`u4/r1_controls.py`): 61 rows, 0 unexpected (first run caught a prefix-match gap; a 65-hex row was added). Developer: B2 (drop sbom_check.py l.30), N8 comment; swapped-floor and same-fs floor tests are green on arrival (guards).
