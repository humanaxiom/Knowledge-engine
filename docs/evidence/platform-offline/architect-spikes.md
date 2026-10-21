## 2026-10-19 — architect: design amended from spikes S1–S4 (R2, R3, R6, L-5, S3)

- **Asked:** fold the spike findings and the orchestrator's rulings
  ("rulings on architect R1–R7", "rulings from spikes (R2, R6)") into §2.5,
  ADR-KE-012 and ADR-KE-009/013; drop the scan from this branch's stage
  order; reorder the first tests. Touch only `docs/architecture.md`.
- **Did (`docs/architecture.md`):**
  - §2 intro and §2.1: the scanner pair and the `scan` profile are marked
    platform-supply-chain; new invariant "isolated ⇒ internal" (S3); `dind`
    row: default (containerd) store, network alias `docker`;
    `offline-client` uid 10001; Image tags: install never touches `:local`.
  - §2.2: sequence diagram and stage text without `scan.sh` (later inserted
    by platform-supply-chain); L-5 block rewritten from S2 (image-owned
    `/opt/venv` and `UV_CACHE_DIR=/opt/uv-cache` chowned to 10001;
    `safe.directory /work` in the system gitconfig; tmpfs
    `/tmp:exec,mode=1777`; `MYPY_CACHE_DIR=/tmp/mypy`,
    `PYTHONDONTWRITEBYTECODE=1`, `GIT_OPTIONAL_LOCKS=0`; pyproject
    `[tool.coverage.run] data_file = "/tmp/.coverage"` instead of
    `COVERAGE_FILE`; `test.sh` drops `rm -f .coverage.*`; `UV_NO_SYNC`
    forbidden). PSScriptAnalyzer-by-hash marked platform-supply-chain
    (PS-3.7, per the split ruling); the pinned Docker CLI stays here.
  - §2.5: bundle and install made store-independent (R2); 10 GB disk floor
    in `bundle.sh` and `offline_check.sh` plus `df` log per stage (R6);
    `offline-client` reaches `tcp://docker:2376`, mounts only the certs
    `client` subpath read-only, never `ca/` (S3); "no pull" check compares
    tag sets, not IDs; scan section marked platform-supply-chain; time
    table re-based on S4 (about 2.5–4.5 min added); spikes section replaced
    by results; rulings list replaced by the decided rulings.
  - §2.6 platform-offline: reordered (below); scan and L-8 tests moved to an
    out-of-scope list.
  - ADR-KE-009: step 4 and the script list without `scan.sh`; clean-daemon
    TLS/alias/subpath text; L-5 consequence corrected; R6 disk line.
  - ADR-KE-012: decision, alternatives and consequences rewritten for R2
    (containerd-prerequisite design now a rejected alternative); bundle
    about 1 GB; first tests updated.
  - ADR-KE-013: retitled and marked platform-supply-chain; design kept.
- **Decisions made within the rulings (for orchestrator review):**
  - `as` scheme: first-party `ke-<x>:bundle-<sha12>`, vendor
    `ke-vendor/<name>:<digest12>`. `bundle.sh` tags `ref` → `as` on the
    build host and saves by `as` (S1: `docker tag` + `docker save <tag>`
    work on both stores).
  - `bundle.json` gains a `services` field (space-separated) next to
    file/ref/as: install needs it to write the override without running
    `compose config`. **Analyst: PS-3.1 wording on bundle.json fields.**
  - The override is `<target>/docker-compose.override.yml` with `image:
    <as>` and `pull_policy: never`. Compose auto-loads it because launch,
    teardown and smoke pass no `-f`; verify sets `COMPOSE_FILE`, so it is
    unaffected. No script change.
  - Install no longer untags or retags to `:local`; `:local` stays the
    operator's own `build.sh` tag. Two dirty bundles of one commit share a
    tag (accepted, recorded in ADR-KE-012).
  - The disk check also looks at `DockerRootDir` when it exists on the host;
    on Docker Desktop it is reported "not measurable", not failed.
  - The certs subpath needs a compose that supports `volume.subpath`;
    `offline_check.sh` refuses older, minimum measured at implementation.
- **First tests (§2.6, new order):** 1. L-5 static
  `test_gate_services_unprivileged_read_only_checkout` (first, so every
  later step runs under the final gates runtime); 2.
  `test_bundle_manifest_rejects_tamper`; 3.
  `test_install_refuses_unfit_target_or_daemon` (no store case); 4.
  `test_install_tags_loaded_images_and_writes_override`; 5.
  `test_bundle_lists_every_compose_image` (no `--platform`, 10 GB refusal);
  6. `test_bundle_contents`; 7. `test_compose_offline_services` (alias,
  subpath, isolated ⇒ internal); 8. Docker CLI hash pin; 9. image tags (N6);
  10. verify B6 order without scan; 11. netprobe + `ci/offline`; 12.
  `OfflineCheckScriptTest` (disk, df log, tag-set check); 13. notices; 14.
  CI timeout. Recorded red runs gain the L-5 lock-drift case.
- **Open for the analyst (not touched, they are editing requirements):**
  PS-3.1 (bundle.json `services`, no containerd prerequisite, no
  `--platform`), PS-3.2 (no-pull check by tag set), PS-3.5 (writable set
  per S2), and any PS text still naming the scan or L-8 in this branch.
- **Evidence:** `docs/evidence/platform-offline/architect-spikes-verify-fast.txt`.
- **Next:** orchestrator confirms the decisions above; analyst aligns
  PS-3.x; tester starts RED with test 1.
