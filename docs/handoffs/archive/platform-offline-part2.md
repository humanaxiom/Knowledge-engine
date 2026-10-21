# platform-offline — part 2 history (unit 2 bundle/install through round 2, arch, MLX path)

Moved from docs/handoffs/platform-offline.md on 2026-10-19 to keep it under 200 lines.


## 2026-10-19 — developer: GREEN unit 2 (PS-3.1 bundle and install)
- Added `scripts/bundle.sh` (`--out <dir>`; no `--tar` yet), `scripts/install.sh`, `scripts/install.ps1`; `dist/` added to `.gitignore` and `.dockerignore`. Tests untouched.
- bundle.sh: per-service `compose config --images <svc>` (no jq), refusals before any write (pattern, non-amd64, digest pin via `image inspect`, name/`as` collision, non-empty out, 10 GB floor), then tag + `save -o` per image, app/, bundle.json (printf), sorted manifest, prints manifest hash. `app/` ships launch/teardown/smoke (+ `net_isolated.sh` if present), `.env.example`, `config/`, `docs/quickstart.md`. NOTICE.md and licenses/ copied only if they exist (PS-3.8 later).
- install.sh/ps1: manifest (line pattern, segments, dupes, links, file set, hashes) before any docker; then info, target, bundle.json fixed patterns, service coverage via `compose config --services`, load/tag/inspect, copy, override. No eval / Invoke-Expression.
- Green: all 27 tests in `tests/test_offline_bundle.py` (InstallShTest 7, InstallPs1Test 7, BundleScriptTest 12, DistIgnoredTest 1). Lint PASS (shellcheck 14 files, PSScriptAnalyzer 4 files).
- `COMPOSE_PROJECT_NAME=ke-dev-u2 scripts/verify.sh full` -> PASS (193s). Evidence: `docs/evidence/platform-offline/green-u2-verify-full.txt`.
- Not done / next: `--tar`, notices (PS-3.8); install against a real daemon and real compose `config --services` on the shipped app/ (only covered by the later ci/deployable-offline gate); not committed.

## 2026-10-19 — security: audit unit 2 (PS-3.1 bundle + installers)
- Verdict PASS: 0 crit/high, 3 medium, 7 low, 2 info. Full report with repros: `docs/evidence/platform-offline/security-u2.md`.
- M-1 TOCTOU: install.sh/ps1 hash files, then re-read them for `docker load` and the app copy (repro: tar and launch.sh swapped after the check, exit 0). Fix: stage into a private dir, or hash the same stream.
- M-2 install.ps1 compares paths with case-insensitive `@{}`, so an unhashed case variant (`app/scripts/LAUNCH.ps1`) in a case-sensitive dir passes and is copied (bash refuses it). Fix: Ordinal comparers plus a test.
- M-3 trust anchor: the installer checks itself. **Must close before the item closes**: the quickstart (pending *Docs* criterion) gives the out-of-band manifest-hash comparison and has the operator verify install.sh/ps1 before running them. Also suggested: the installer prints, or takes `--expect-manifest`.
- Low: L-1 ps1 follows a junction target; L-2 target check-then-use race; L-3 hardlinks accepted; L-4 ps1 reads the manifest before its link check; L-5 the loaded name is not compared with `as`; L-6 no staging/disk check in install, and the `df $4` column shift in bundle.sh; L-7 `cp -R config` can ship ignored files.
- Clean: no docker before the manifest passes, no YAML/arg injection, no secrets in the diff.

## 2026-10-19 — reviewer: unit 2 (PS-3.1) CHANGES REQUESTED
- Read diff vs 1fe81dd + untracked scripts/tests. `COMPOSE_PROJECT_NAME=ke-review-u2 scripts/verify.sh fast` PASS (462 OK). Detail: `docs/evidence/platform-offline/review-u2.md`.
- Mutants (scratch copy, gates image): hash/dup/unlisted drop and `docker info`-first caught in sh and ps1; amd64 and name-collision drop caught.
- B1 (tester): link and dot-dot rules not pinned. m3/m4 (sh) and p3 (ps1) survive; m4 lets an unlisted dir symlink (`app/evil -> /etc`) into the target. Add an unlisted dir-symlink case; assert each refusal names its rule.
- B2 (analyst/architect, docs only): PS-3.1 says the installer "does not run `compose config`"; it runs `config --services` for the no-entry refusal. Amend requirements and §2.5 Install; keep the code.
- Nits N1-N8 (ps1 fifo/target/link-message parity, ordinal hashtables, dead `seen_as`, ignored compose exit status, untested paths, GB/GiB).
- Rulings: NOTICE/licenses/net_isolated copy-if-exists OK for now, carry to PS-3.8/PS-3.3 (copy unconditionally + `test_bundle_contents`). amd64 refusal conforms. `as` scheme and `<name>` collision conform to §2.5.

## 2026-10-19 — orchestrator: unit-2 rework round 1/5 (review CHANGES REQUESTED, security PASS w/ M-1..M-3)
- Tester RED first, then developer GREEN. Scope:
  - review B1: unlisted dir- and file-symlink cases; each refusal must name its rule (sh + ps1); m3/m4/p3 must be caught.
  - review N1–N8, all fixed (N4: delete the dead check or make it reachable; N8: say "10 GiB", round down explicitly).
  - security M-1 private staging copy: verify, load and copy from it only, with a fake docker that mutates the bundle after `info` as the test.
  - security M-2 ordinal path tables in ps1, refuse paths differing only by case.
  - security M-3 code half: installers print the accepted manifest sha256 and take `--expect-manifest <sha>` / `-ExpectManifest`; bundle.sh writes `<out>.manifest.sha256` beside (not inside) the bundle.
  - security L-1..L-7, I-1 (refuse reserved names, trailing dot/space, `:`), I-2 (override written 0644 explicitly).
- B2 docs (analyst + architect): PS-3.1/§2.5 say install runs `compose config --services` only to check service coverage.
- Must-close carries: M-3 quickstart procedure (documenter); NOTICE/licenses/net_isolated copy-unconditionally + test_bundle_contents at the PS-3.8/PS-3.3 units.
- Q49 (asked of the human): arm64 bundle? amd64-only stands meanwhile.

## 2026-10-19 — tester: RED unit-2 rework 1 (B1, N1–N3, N5–N8, M-1..M-3, L-1..L-7, I-1, I-2)
- `tests/test_offline_bundle.py`: tamper cases now carry (path, rule regex); refusals must name both (`RULE_*` constants). New cases: unlisted dir/file symlink, dot segment, fifo, reserved names, trailing dot, colon. New install tests (sh+ps1): `test_install_fails_when_compose_config_fails` (N6), `_refuses_manifest_link_or_fifo` (L-4), `_refuses_case_variant_paths` (M-2/N5; ps1 also refuses listed case collisions), `_loads_and_copies_verified_bytes_only` (M-1, L-3 hardlink), `_does_not_follow_target_planted_during_load` (L-2), `_leaves_no_partial_target` (L-6), `_prints_and_checks_manifest_hash` (M-3), `_writes_override_0644` (I-2); subtests for link/dangling target (N3/L-1), `as` sha12 vs git_sha and unknown service (N7), loaded name must be `as` (L-5). Bundle: GiB wording + round-down (N8), df column with spaces (L-6), `<out>.manifest.sha256` (M-3), tracked config only (L-7), unpinned third-party (N7), compose failure (N6).
- Interface pinned: `bash install.sh [--expect-manifest <sha256>] <target>`; `install.ps1 -Target <dir> [-ExpectManifest <sha256>]`; installers print the accepted manifest sha256; bundle.sh writes `<out>.manifest.sha256` (first token = hash); df message `need 10 GiB free ... found <floor> GiB`.
- Contradictions resolved here: `LOADED_APP_NAME` is now `as` (L-5, orchestrator round-1 scope); "need 10 GB free" -> "need 10 GiB free" (N8 ruling). Architecture §2.5/§2.6 still say "10 GB" — architect to align.
- Harness: `fake_docker.py` gains FAKE_DOCKER_HOOKS, FAKE_DOCKER_LOADED_LOG, FAKE_DOCKER_EXIT_AFTER; fake df FAKE_DF_TOTAL_KB, FAKE_DF_FILESYSTEM.
- RED: `COMPOSE_PROJECT_NAME=ke-tester-u2r1 scripts/verify.sh fast` -> 483 tests, failures=58, all in `tests.test_offline_bundle`; lint PASS. Evidence `red-u2r1-verify-fast.txt`.
- Mutants (`red-u2r1-mutants.txt`): m3 caught by dotdot_path/dot_path; m4 by symlink/unlisted_dir_symlink/unlisted_file_symlink/unlisted_fifo; p3 by dotdot_path/dot_path. Those subtests pass on current code (mutant-only kills).
- Green now, pins only: colon, ps1 manifest symlink, ps1 compose failure, unknown service, unpinned third-party, no-entry zero loads, dangling target. Not pinned: manifest size cap (no figure specified), N4 (excluded).
- Addendum: manifest size cap (§2.5, 1 MiB): `manifest_over_1_mib` (refused before docker, names MANIFEST.sha256 + size rule `RULE_SIZE`) RED sh+ps1 (current refuses only via "listed file is missing", having read it all); `manifest_exactly_1_mib_not_refused_by_cap` green pin. Re-run verify fast: failures=60, all in the module; evidence overwritten.

## 2026-10-19 — developer: GREEN unit-2 rework 1/5 (B1, N1–N8, M-1..M-3, L-1..L-7, I-1, I-2)
- `scripts/install.sh`/`install.ps1`: args (`--expect-manifest`/`-ExpectManifest`), target parent/link checks, private 0700 staging in the target's parent, link/fifo refusal by rule before any open, disk check (GiB), manifest on staging (regular, <=1 MiB, expect hash first, rule-named refusals, reserved names/trailing dot/case collisions, ordinal tables in ps1), loaded name must equal `as`, first-party sha12 vs git_sha, `compose config` exit status checked, override 0644, publish by rename, cleanup on every exit (trap / try-finally).
- `scripts/bundle.sh`: robust `df` read, GiB messages, `<out>.manifest.sha256` (refuses if present), `git ls-files config` only, compose exit statuses checked, dead `seen_as` removed. Output line is now `manifest sha256: <hex>`.
- Tests untouched. All 60 failures in `tests/test_offline_bundle.py` pass (InstallShTest, InstallPs1Test, BundleScriptTest). Lint PASS.
- `COMPOSE_PROJECT_NAME=ke-dev-u2r1 scripts/verify.sh full` -> PASS (232s). Evidence `docs/evidence/platform-offline/green-u2r1-verify-full.txt`.
- Not proven: Windows paths in ps1 (ACL staging, DriveInfo, junctions) have no test here; Windows host run (Q31/Q34) still needed. Needs GNU `find -printf`, `mv -T`, `cp`, `mktemp` on the install host. Not committed.

## 2026-10-19 — tester: pins for the architect's five untested behaviours (post-GREEN u2r1)
- New: `test_install_stages_privately_in_target_parent` (one `.ke-install.*` dir in the target's parent, 0700 under umask 022, observed at `docker info`); `test_install_removes_staging_on_every_exit` (success, manifest refusal, failed load, failed info, SIGINT/SIGTERM to the process group during load); `test_bundle_refuses_existing_manifest_record`; mismatch subtest now also asserts the expected value is printed; tamper case `trailing_space`. Harness: hook actions `list`/`touch`/`sleep`.
- Mutants (11, scratch copies): s1/s2/p1/p2 (staging location, mode), s3/p3 (cleanup), b1 (record), s4/p4 (expected value), s5/p5 (character rule) — all caught. `pins-u2r1-mutants.txt`.
- RED found: install.ps1 on interrupt. SIGTERM leaves `.ke-install.*` behind (no finally runs); SIGINT removes staging but exits 0. sh holds every case. `COMPOSE_PROJECT_NAME=ke-tester-u2r1 scripts/verify.sh fast` -> 488 tests, failures=2 (those two subtests), lint PASS. Evidence `pins-u2r1-verify-fast.txt`. Next: developer (ps1 signal handling), or orchestrator ruling if SIGTERM cleanup in pwsh is deemed infeasible.

## 2026-10-19 — orchestrator: Q49 resolved by human (per-arch bundles); Q50 opened
- Human: "build an arm64 bundle on an ARM host, or cross-build with docker buildx" is correct; an MLX (Apple Silicon) box comes later.
- Ruling: bundle.sh accepts linux/amd64 OR linux/arm64, which must equal the build host's arch, and all images must share it; bundle.json records `arch`; the installer refuses a bundle whose arch differs from `docker info` Architecture, before any load. buildx cross-build is deferred (no --platform on save; it changes digests, spike S1).
- Q50 (open, not blocking): install.sh needs GNU find/mv/cp; macOS hosts (MLX box) need portable tools or a documented coreutils prerequisite.
- Sequence: after the ps1 interrupt fix lands, analyst+architect amend PS-3.1/§2.5 → tester RED → developer GREEN, then review+security of the whole unit 2.

## 2026-10-19 — orchestrator: human "build it for both" — bundles for amd64 AND arm64; code-first primary
- The pause/park plan is withdrawn; work continues on agent/platform-offline. The interrupted developer step left install.ps1 unchanged; green-u2r1b-verify-full.txt ran the OLD script and is not evidence of the fix.
- Code-first (clone → scripts/build.sh → scripts/launch.sh, native arch, needs internet at build) is the primary documented install path. The offline bundle is the air-gap path.
- Bundles are per arch: linux/amd64 and linux/arm64 are both first-class. bundle.sh builds for the host arch; `arch` is in bundle.json; install refuses an arch ≠ daemon arch before any load. The CI deployable-offline gate proves amd64. arm64 proof: an ARM CI runner if available (ubuntu-24.04-arm), else a recorded run on aria-gb10 (human to confirm docker access there). buildx cross-build stays deferred.

## 2026-10-19 — orchestrator: buildx cross-build in scope; MLX path
- Human: "Build the images" / "Yes" → `bundle.sh --arch amd64|arm64` cross-builds first-party images with buildx and pulls vendor images by index digest per platform. Orchestrator buildx probe running → docs/evidence/platform-offline/buildx-probe.txt.
- Human: "A path for mlx as well". (1) Stack on an Apple Silicon Mac: the arm64 bundle + code-first; Q50 is IN scope here: install.sh portable to macOS (BSD tools, bash 3.2), static forbid-list test, recorded Mac install later. (2) MLX model serving (native mlx_lm.server, OpenAI-compatible) needs per-role model upstreams in the gateway, since embeddings likely stay on Ollama → new plan item `model-hosts` after platform-offline (Q52).

## 2026-10-19 — orchestrator: arm64 images build natively on aria-gb10
- The dev host's Docker Desktop has no arm64 binfmt (exec format error; buildx-probe.txt). The human chose native arm64 builds. aria-gb10 = aarch64, Ubuntu 24.04, Docker 29.6.2, buildx 0.35; docker context `aria-gb10` over SSH (host key ED25519 SHA256:dqiWPQUGKqHZxfqnHAQ6g7BvKUO3+xLekaMmKwtRg6c accepted on first use, with the human's OK).
- ke-app 12 s, ke-gateway 7 s, ke-gates 22 s, all linux/arm64, unchanged Dockerfiles (incl. the per-arch pwsh/shellcheck pins); `python -c import engine` on aarch64 OK. Evidence: buildx-arm64-gb10.txt. Probe tags `*:probe-arm64` remain on aria-gb10.
- Design (sent to the architect): the bundle arch = the target daemon's arch (DOCKER_CONTEXT); `--arch` is an assertion only; no --platform; binfmt optional. arm64 proof = a recorded bundle + install on aria-gb10 (Q51).

## 2026-10-19 — developer: GREEN unit-2 rework 1b (install.ps1 interrupts)
- `scripts/install.ps1` only. Compiled C# `KeInterrupt` (PosixSignalRegistration SIGINT/SIGTERM/SIGHUP, Cancel=true, sets Fired) so finally runs and staging is removed; `$finished` flag set at end of try and in catch; finally calls `[Environment]::Exit(1)` when pwsh stopped the pipeline itself (SIGINT path, which otherwise exits 0); final `exit` is 1 if Fired.
- Green: `InstallPs1Test.test_install_removes_staging_on_every_exit` (SIGINT and SIGTERM cases). Tests untouched.
- `COMPOSE_PROJECT_NAME=ke-dev-u2r1b scripts/verify.sh full` PASS (258s), lint PASS. Evidence `docs/evidence/platform-offline/green-u2r1b-verify-full.txt`. Windows Ctrl+C/Ctrl+Break path not tested here. Not committed.

