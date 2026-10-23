# Handoff archive: platform-sbom part 5 (U1 commit gate, U2 and U3 sections)

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

## 2026-10-23 — tester (U3 RED)
- RED: new `tests/test_sbom_bundle.py` (3 PSC-13 tags plus run argv/teardown, daemon arch, ref `-`, SBOM failure, L-1/L-2/N3 static, stdlib/never-shipped); edited `test_bundle_contents` (app/sboms, ADR-KE-016 pt 6), the offline_check pull test (KE_SBOM_USER, L-2), U2 `hardening_problems` (HOME/XDG only under /tmp, I-2). 46 failures in 14 tests, all U3; sentinel ok, lint PASS (`u3/red-verify-fast.txt`).
- Harness (tests/fake_docker.py): `save` writes real tars (FAKE_DOCKER_SAVE_TAR oci/legacy/two); `compose run sbom` models syft (FAKE_SYFT_DROP/_PYPI_VERSIONS/_RAW/_LOG, needs <work>/tmp); `docker run ... sbom_check.py` runs the real checker, argv paths remapped by -v and FAKE_IMAGE_PATHS; `_BundleBase.site` now at venv/lib/python3.12/site-packages.
- Targets `u3/target-*` (bundle.sh SBOM section, trap, generator arch check, ref_re; sbom_check.py; compose `user: ${KE_SBOM_USER:?}`; offline_check header + pull). Controls 107 (90 must-fail, 17 must-pass), 0 unexpected (`u3/red-mutants.txt`, driver `u3/u3_controls.py`).
- Reach BLOCKED by a design contradiction: with the targets, verify fast fails only test_no_hardcoded_ports and test_no_hardcoded_hosts_or_models on N6's `NAMESPACE_BASE = "https://spdx.knowledge-engine.invalid"` (PS-1.2 scan); orchestrator/architect: recorded exemption (ADR + EXEMPTIONS) or a non-URL namespace (`u3/red-reach-verify-fast.txt`).
- Open: N1 still says HOME/XDG under /out/tmp and its run form lacks --env-file (architect); pinned for GREEN: KE_SBOM_USER, KE_SBOM_IN=<out>/images, label <project>-sbomcheck, checker paths on its argv; neo4j jars (ruling 5) are not decided by these stubbed tests, first seen in GREEN verify full.
- Re-target (ruling (b) + N6 amendment): NAMESPACE_RE `urn:uuid:<v4>` (https, upper-case, non-v4, variant, '#', newline, bare refused), namespaces distinct per document and per run, new `test_finish_namespace_is_fresh_per_run` and `test_finish_refuses_uuid_option`; RED 48 failures in 16 tests, all U3 (`u3/red-verify-fast.txt`); controls 121, 0 unexpected; reach verify fast PASS, test_engine_hardcoded ok (`u3/red-reach-verify-fast.txt`); stale U2 row noted in `u2/red-mutants.txt`.

## 2026-10-23 — orchestrator (U3 ruling: SPDX namespace)
- Tester RED blocked reach: N6's `NAMESPACE_BASE = "https://spdx.knowledge-engine.invalid"`
  trips PS-1.2's hardcoded-host scan. RULING option (b): documentNamespace is
  `urn:uuid:<uuid4>`, a fresh uuid4 per document (an absolute RFC 3986 URI as SPDX 2.3
  requires; no exemption, no invented domain; unique per document and per run).
  Architect amends N6 (+ N1 nits: HOME/XDG only under /tmp, --env-file on run/down;
  review N4 wording); tester re-targets NAMESPACE_RE and validate's URI rule.

## 2026-10-23 — architect (U3 namespace)
- N6: `documentNamespace` = `urn:uuid:<uuid4>`, fresh `uuid.uuid4()` per document in `finish` (SPDX 2.3 absolute URI via RFC 3986/4122; no host, PS-1.2); `finish --uuid` and bundle.sh's od uuid dropped; validate regex `^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`, distinctness bundle-level (PSC-13 tests, N11). N1: HOME/XDG only under /tmp (I-2); run/down argv as `u3/target-bundle.sh` with --env-file + 3 KE_SBOM_* keys; N4 "must include these eight". N3 pins: KE_SBOM_USER, KE_SBOM_IN=<out>/images, label <project>-sbomcheck, argv-path rule, `validate(doc) -> list[str]`. Ruling 5 decided at GREEN verify full; GPL-family jar back to architect. ADR-KE-016 pts 1, 6 + consequences (195 lines, unchanged).

## 2026-10-23 — developer (U3 GREEN)
- Targets applied (bundle.sh, sbom_check.py 755, compose `user:`, offline_check); verify fast PASS, full PASS 855 s (`u3/green-verify-{fast,full}.txt`). Bundle of 6 SBOMs, all in the manifest (`u3/bundle-run.txt`, `u3/sboms/`); SBOM stage 75 s of a 97 s bundle.
- Production fixes beyond targets (Git Bash/NTFS): `mkdir -m 0700` fails, so mkdir then chmod; `MSYS_NO_PATHCONV=1` on syft run and checker run with host paths via `cygpath -m` (`hostpath`), else syft got `C:` mangled paths.
- Ruling 5: `u3/gpl-family-packages.md`. neo4j GPL-family beyond Neo4j's own org.neo4j jars: jna 5.15.0 (Apache-2.0 AND LGPL-2.1-only, dual), jaxb-api 2.2.12 (CDDL+GPL); 15 other maven jars NOASSERTION. To architect before commit.

## 2026-10-23 — security (U3)
- PASS (no crit/high). syft run inspected live: caller uid:gid, net none, RO, CapDrop ALL, /in ro, /out only rw, nothing left behind; checker inject-safe, depth bombs fail closed; Windows fixes safe, no mkdir/chmod TOCTOU (mktemp -d 0700). U2 L-1, L-2, I-1, I-2 closed. `u3/security.md`, raw `u3/security-u3-probes.txt`.
- M-1 medium (evidence): the u3 ke-app SBOM and the gpl-family ke-app counts come from a stale pre-U0 `ke-app:local` (pip, psycopg-binary, no libpq5). Regenerate them with a fresh HEAD build before ruling 5. L-1 low (architect): bundle.sh does not tie ke-* images to HEAD.

## 2026-10-23 — architect (ruling 5)
- N8a (+N8, N1, N4, N5, N9, N10, N15; ADR-KE-016 pts 4, 8, consequences, 200 lines): jna and javassist are OR (jar LICENSE / pom), Apache-2.0 elected, reviewed `exempt` (U6); jaxb-api is CDDL-1.1 OR GPL-2.0+CPE, CDDL elected but 3.1 still needs source, so U7 adds a `maven` kind (sources jar, repo1.maven.org, `.sha1`). N8 fixes: declared NOASSERTION falls through to concluded; a gpl/lgpl/agpl token in a folded `LicenseRef-` needs source (else jaxb-api passes, fail open); URL-folded ids listed (U5).
- NOASSERTION (neo4j 20; ke-app conditional on the regenerated SBOM) all to the U4 report, minus the DESCRIBES root, no cargo default; U4 sets `XDG_CACHE_HOME: /tmp/cache`; security L-1 (revision label, bundle.sh refuses mismatch) recorded at U10. javassist was missed by the evidence's case-sensitive selection.

## 2026-10-23 — reviewer (U3)
- APPROVED, no blocking. Diff read (bundle.sh = target + Windows fixes, which are correct and inert on Linux; the rest = targets). Carry list (review N1-N5, L-1, L-2, I-1, I-2, argv/project/teardown) all closed. Controls run on the real files with adapted anchors: 124 rows, 123 ok, 1 driver artifact (`u3/review-controls-base-repo.txt`, `u3/review_u3_controls.py`).
- Nits N1-N9 in `u3/review.md`. For the architect: N3 (design forms lack hostpath/MSYS_NO_PATHCONV), N5 (syft /.cache warning; N1 confirm-at-GREEN not recorded) and N6 (unpack in host TMPDIR, outside the R6 floor). N4: Windows branch and chmod have no test, so A34 must show the real SBOM stage. Ruling 5 must be decided before commit.

## 2026-10-23 — tester (U3 Windows proof)
- A34 PASS (`u3/windows-run.txt`): U2 driver/shim/phases, ke-tester-u3win, tag u3win-98b6d27; 2b shows `user: 1000:1000`, KE_SBOM_USER unset/empty fail closed (PowerShell, Git Bash); bundle.sh from Git Bash exit 0 in 96 s, 6 SBOMs validate() [], 6/6 namespaces, manifest verifies; launch 7/7, 4b/4c, refusal, teardown, 7 Windows tests, verify fast PASS (812, 556 s); nothing left; 7 sha256 equal start/end. Finding: bundle.sh on Windows needs jq on PATH in LF mode (winget jq.exe writes CRLF; run used `jq.exe -b`); host docs should say so.
- Security M-1: images proven fresh (ke-app 2becf293: no psycopg_binary/pip, libpq5 15.19-0+deb12u1); `u3/sboms/*.pkgs.tsv`, ke-gateway/valkey JSON and `u3/gpl-family-packages.md` regenerated from that bundle. ke-app 700/83/505 -> 154/84/2 (pkgs/GPL/no-licence; stale had 493 cargo, pip, psycopg-binary); ke-gateway 72/19/1 unchanged (only the pkg:oci row differs); neo4j jna + jaxb-api unchanged; other four TSVs byte-identical.
