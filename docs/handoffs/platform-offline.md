# Handoff: platform-offline

Outcome metric moved: neither directly. It makes the product installable with
no internet (the "deployable without the assistant" rule), a precondition for
any on-prem reviewer to use it.
Spec: `docs/requirements.md` § platform-skeleton, PS-3.x. Design: `docs/architecture.md` §2.5, ADR-KE-012 (+ ADR-KE-009 on the DinD offline check).
Base: `agent/platform-stack-ready` @ 4b19971. Previous handoffs: `docs/handoffs/archive/platform-stack-{up,ready}.md`.

## Rulings in force (summary; history in archive/platform-offline-part1.md)
- Scope: PS-3.1–3.5, 3.8, 3.9, 3.10 here; PS-3.6 (scan) and 3.7 (L-8) in platform-supply-chain. No scan stage on this branch.
- R1 no bundle.ps1 (bundle on a Linux host; install.sh + install.ps1). R4 Neo4j GPL with source URL. R5 CI 20 min, then measured + 50%. R7 stack images only; the notices generator fails on a missing runtime licence.
- R2 store-independent: per-image tars, `bundle.json` file/ref/as/services, install = verify → load → tag to `as` → override (`pull_policy: never`). `as` = `ke-<x>:bundle-<sha12>` / `ke-vendor/<name>:<digest12>`. Never compare image ids; no containerd prerequisite for operators.
- R6 10 GB free-disk floor in bundle.sh and offline_check.sh; `df` around offline stages.
- S3 dind: alias `docker`, only the certs `client` subpath read-only, inner isolated networks `--internal`; `offline-client` runs as 10001:10001.
- Q47 no classic-store gate. Q48 docker CLI hash: TOFU over HTTPS if no upstream checksum (security re-fetches); otherwise it must equal upstream.
- Test names: requirements PS-3.x are canonical; architecture §2.6 sets order.
- Unit 1 (L-5) DONE in 1fe81dd. Open carry: N9 quickstart umask → documenter. Security L-3 (`.env.*`, `.git/config` readable) → auth-audit.

## 2026-10-19 — tester: RED unit 2 (PS-3.1 bundle and install, fast, stubbed docker/df)
- New `tests/test_offline_bundle.py`. `InstallShTest`/`InstallPs1Test` (same cases, bash and pwsh, tiny fixture bundle): `test_bundle_manifest_rejects_tamper` (a/b/c + symlink, `..`, leading `/`, backslash, malformed, duplicate; docker log empty; control logs info then load/tag/inspect per image), `test_install_loads_nothing_when_manifest_fails`, `test_install_rejects_bundle_json_missing_field` (4 fields + bad `services`), `test_install_refuses_unfit_target_or_daemon` (§2.6 #3), `test_install_tags_loaded_image_as_bundle_name` (name/ID line; none/two lines name the tar), `test_install_override_maps_every_service_to_as_tag`, `test_install_fails_when_service_has_no_bundle_entry`.
- `BundleScriptTest` (temp git repo copy, fake docker + df): lists_every_compose_image, holds_stack_images_only, json_names_every_image, saves_one_tar_per_image_without_platform, json_records_file_ref_as (+ `as` scheme, name collision), manifest_covers_every_file, prints_manifest_hash, has_no_wheels, json_marks_dirty_tree, fails_below_free_disk (3 GiB refused, 11 GiB control), fails_when_pinned_digest_unresolved, refuses_unfit_image_or_out (§2.6 #5). `DistIgnoredTest.test_dist_is_gitignored`.
- Harness: `tests/fake_docker.py` gains env-gated `load`/`save`/`tag`/`image inspect`, `compose config --images`/FAKE_COMPOSE_IMAGES, and `install_df`. Probe in the gates image: `red-u2-harness-probe.txt`.
- Nits n1–n4 folded in (test-only, green): n1 skipped subTest for worktree `.git`; n2 comment; n3 USER guard; n4 rename to `test_coverage_erase_precedes_first_run_and_spares_checkout`.
- RED: `COMPOSE_PROJECT_NAME=ke-tester-u2red scripts/verify.sh fast` → 462 tests, failures=28, all in the new module: 12 "scripts/bundle.sh is missing", 7+7 "scripts/install.sh|install.ps1 is missing", 2 subtests `.gitignore`/`.dockerignore` lack `dist/`. Lint PASS. Evidence: `red-u2-verify-fast.txt`.
- Interface pinned for the developer: `bash scripts/bundle.sh --out <dir>` run from the repo root; `bash <bundle>/install.sh <target>`; `pwsh -File <bundle>/install.ps1 -Target <dir>`; load output via the `Loaded image[ ID]:` line; `docker image inspect <as>`; df message "need 10 GB free" + available GB + path.
- Not covered here (later units): notices (PS-3.8), `--tar`, `app/` exact file set (§2.6 #6 proposed `test_bundle_contents`).
## Unit 2 state (summary; history in archive/platform-offline-part2.md)
- Unit 2 = bundle.sh / install.sh / install.ps1 (+ quickstart). R2 store-independent; staging + claim-marker publish; trust anchor (`<out>.manifest.sha256`, --expect-manifest); ordinal/reserved-name path rules; 1 MiB manifest cap.
- Arch (Q49, human): per-arch bundles, linux/amd64 + linux/arm64; arch = target daemon's (DOCKER_CONTEXT); `--arch` is an assertion only; `-<arch>` out suffix; install refuses a mismatch. arm64 builds natively on aria-gb10 (context `aria-gb10`; buildx-arm64-gb10.txt). Proof: CI amd64 + a recorded aria-gb10 arm64 run.
- macOS: install.sh, launch.sh, teardown.sh are bash 3.2/BSD-portable (Q50/Q53). MLX model serving → later item `model-hosts` (Q52).
- Code-first (clone → build → launch) is the primary documented path; the bundle is the air-gap path.
- Writable target parent → WARNING (architect ruling, security accepted).
- Rounds: unit-2 rework rounds 1–5 done (round 5 human-approved after escalation). History: archive/platform-offline-part3.md.

## State (2026-10-20; history in archive/platform-offline-part{1..4}.md)
- Committed + pushed (agent/platform-offline): 1fe81dd (L-5), 84ee95c (bundle/installers), 62fa043 (audit-l2 follow-ups), f7e9074 (PS-3.10 docker CLI), e3d3fed (offline check). CI run 39359710258: all green until offline_check, which failed the 10 GiB floor (9.1 GiB free); unit tests took 770 s on CI.
- Uncommitted, gates passed: PS-3.8 notices (audit-nt.md PASS/APPROVED) + I-OC1b-2 + Q1/Q2; disk floor 7 GiB + CI timeout 30 min (green-floor-verify-full.txt).
- Human rulings 2026-10-20: push approved; project licence MIT (holder "Humanaxiom" by default, pending the human); usernames/host names stay in evidence (redact profile paths + SIDs only); jq installed (Windows winget 1.8.2, WSL 1.8.1); D-1 in order (CRF draft yes; pre-fill anticipated grade yes; Part II suggestions barred yes; KE adopts no-grade rule NO; reorg unanswered → out of scope).
- Both arches proven end to end with no workarounds: arm64 (recorded2), amd64 (recorded3). DR38 red runs accepted.
- Next: commit notices+floor → push → CI measurement → set timeout to measured+50%. Then the notices round: MIT LICENSE + NOTICE.md statement, valkey BSD-3 text (M-NT1 part), L-NT1..5, quickstart 7 GiB sentence. Deferred to platform-supply-chain: M-NT1 full SBOM/source offers, Q42, image scan, CI unit-test speed (parallel modules). Known limits: L-OCa, N4.
