# platform-offline — part 1 history (plan, spikes, unit 1 L-5)

Moved from docs/handoffs/platform-offline.md on 2026-10-19 to keep the active doc under 200 lines. Unit 1 committed as 1fe81dd.

## 2026-10-19 — orchestrator: item opened
- Carry-ins: security L-5 (gates-it runs as root with the repo mounted rw), L-8 (PSScriptAnalyzer pinned by version only), the ke-app image scan (trivy or grype, pinned; Q39 ruling), psycopg LGPL licence files kept in the image plus bundle notices; review round-0 N6/N8 (shared image tags, rebuilds) and rework-1 N-7.
- Standing rulings: F5 (offline check runs in every local `full`, so CI stays equal to local; revisit if local full > ~15 min); bundle has no wheels and is linux/amd64 only; Q20/Q31 (no macOS; Windows proof by recorded run); Q34 scope.
- Next: the analyst confirms PS-3.x criteria and triages carry-ins; the architect checks §2.5/ADR-KE-012 and the DinD design against what 2a/2b built. Then TDD.

## 2026-10-19 — analyst: PS-3 confirmed, carry-ins triaged
- Asked: confirm PS-3.1–3.4 testable; triage L-5, L-8, image scan, psycopg notices, N6/N8, N-7; open questions; size.
- Done: `docs/requirements.md` § PS-3, "Analyst review for platform-offline". PS-3.1–3.4 stand; added per-case tests (tamper a/b/c x sh/ps1, no load on reject, clean-daemon and pull-fails precondition, privileged-blocker, ci/offline control, quickstart). PS-3.4: re-measure from first green CI run with the offline check.
- Carry-ins all in scope: PS-3.5 L-5 (non-root, ro repo, no `.env` read; closes A35(c)), PS-3.6 image scan, PS-3.7 L-8 + N-7, PS-3.8 licence notices, PS-3.9 N6 + N8. Manifest signing stays out (security flag).
- Open (all assumed, none blocks RED; `docs/open-questions.md`): Q40 bundle location/size/dirty tree; Q41 scanner DB build-time only; Q42 threshold + psycopg-binary vendored libs; Q43 scope beyond ke-app (neo4j GPLv3, Phoenix licence to human); Q44 timeout 20 until measured; Q45 Windows installer proof; Q46 probe target.
- Size: ~30 tests + a Windows run. Proposed split: `platform-offline` (3.1–3.5, 3.8, 3.9, 3.4) then `platform-supply-chain` (3.6, 3.7). Single-branch TDD order is in requirements.
- Next: orchestrator rules on split and Q42/Q43; architect aligns §2.5 (dist/ gitignore, L-5 writable path, tag scheme, scan stage).

## 2026-10-19 — orchestrator: rulings on analyst plan (split, Q40–Q46)
- Split accepted: `platform-offline` (this branch: PS-3.1–3.5, 3.8, 3.9, PS-3.4 re-measure) then `platform-supply-chain` (PS-3.6 image scan, PS-3.7 L-8/N-7). Each needs its own Windows run (Q34).
- Q40, Q41, Q44, Q45, Q46: accepted as the analyst assumed. Q42 (scan threshold, psycopg-binary native libs) is decided when platform-supply-chain opens.
- Q43 (HUMAN, 2026-10-19): keep Arize Phoenix as a documented exception to "open-source components only". It is likely Elastic License 2.0; internal on-prem use is allowed. Listed in the bundle third-party notices; security confirms the licence text at the pinned digest. Neo4j Community is GPLv3 (OSI) and is listed too.

## 2026-10-19 — orchestrator: rulings on architect R1–R7
- R1: no bundle.ps1 (bundling happens on the build host only; install has bash and PS).
- R3: accepted for platform-supply-chain (ke-app only, fresh DB; a new CVE fix turning red is the gate working). This branch has NO scan stage.
- R4: Neo4j GPL-3.0 listed with a source URL in the notices; Phoenix per human Q43.
- R5: CI timeout goes to 20 min when the offline stages land, then measured + 50%.
- R7: the bundle holds stack images only (no gates/dind); L-5 applies to both gate services (shared anchor); the psycopg licence test is covered by the bundle-time notices generator. The analyst reconciles PS-3.1/3.5/3.8 to this.
- R2/R6: decided after spikes. PREFERENCE: a store-independent design (e.g. install writes a compose override mapping services to loaded `ke-*/vendor` tags) over adding a containerd-store prerequisite for operators.

## 2026-10-19 - developer: spikes S1-S4 (evidence only)
- Evidence: `docs/evidence/platform-offline/spikes.md` (+ `spike-s2-run7-tail.txt`). No repo code changed.
- S1: `save --platform` changes the digest; classic store never resolves `ref@digest`; containerd resolves only if the image is named. Store-independent fallback (per-image tar, load, tag by ID, compose override) works on both. Recommend R2 = store-independent.
- S2: uid 10001 + `:ro` needs image-owned `/opt/venv` + uv cache (NOT `UV_NO_SYNC`, it hides lock drift), tmpfs `/tmp:exec`, `MYPY_CACHE_DIR`, and pyproject `data_file` (not env `COVERAGE_FILE`).
- S3: client key is 0644, readable by 10001; server SAN lacks `dind` (alias `docker` or `DOCKER_TLS_SAN`); `isolated` needs `--internal` and is honoured in dind.
- S4: 10.8 s, 0.96 GB tar, 3.3 GB inner store; recommend 10 GB free check (R6).
- Next: architect/orchestrator amend L-5 and R2 text from the spikes; tester starts RED.

## 2026-10-19 — orchestrator: rulings from spikes (R2, R6)
- R2: STORE-INDEPENDENT. Per-image tars (`docker save <tag>`, no --platform); `bundle.json` records file/ref/as; install verifies, loads, tags the loaded id to `as`, writes a compose override mapping services to `as` tags. The digest pin is enforced on the build host plus tar hashes. Only the CI dind uses the containerd store. No operator prerequisite.
- R6: `bundle.sh` and `offline_check.sh` fail early below 10 GB free with a clear message; the first CI run logs `df` before/after each offline stage. 10 GB is a default until measured.
- L-5 per spike S2: image-owned /opt/venv and uv cache for uid 10001; tmpfs /tmp with exec; coverage data_file in pyproject (not an env var); MYPY_CACHE_DIR=/tmp/mypy; never UV_NO_SYNC (hides lock drift); git safe.directory on CI if needed.
- S3: dind gets network alias `docker` (TLS SAN); mount only certs `client` subpath read-only; never `ca/`. Isolated inner networks must be `--internal`.

## 2026-10-19 — analyst: PS-3 reconciled with rulings
- Done: `docs/requirements.md` § PS-3 rewritten in place per R1, R2, R5, R6, R7, S2, S3 and Q43; PS-3.6/3.7 marked moved; `docs/open-questions.md` Q40, Q41, Q43–Q46 resolved, Q42 open for platform-supply-chain, Q47 new. Change list and new test names: `docs/evidence/platform-offline/analyst-reconcile.md`.
- Open: Q47 (no classic-store install gate; assumed stubbed tests + spike S1 suffice; does not block RED). Three interpretations for the orchestrator to check are listed at the end of the evidence file.
- Next: orchestrator confirms; tester starts RED in order PS-3.9 → 3.1 → 3.5 → 3.2 → 3.3 → 3.8 → 3.4.

## 2026-10-19 — orchestrator: rulings on analyst reconcile + architect spikes amendment
- Analyst interpretations 1–3 accepted (generator fails bundle on a missing runtime licence; /tmp tmpfs is the only writable path; `as` scheme is the architect's).
- Q47: accepted the analyst assumption (stubbed installer tests + S1 manual classic-store run). No classic-store gate.
- Architect decisions accepted: `as` = `ke-<x>:bundle-<sha12>` / `ke-vendor/<name>:<digest12>`; `bundle.json` gains `services`; override auto-loaded (no `-f`), verify's COMPOSE_FILE keeps it out, offline-client never sets it; dirty-bundle tag collision accepted; disk check reports "not measurable" for an in-VM DockerRootDir; compose minimum for volume subpath measured at implementation; L-8 PSScriptAnalyzer hash text moves to platform-supply-chain.
- TDD order: architect §2.6 (L-5 first, then the bundle tamper test). Test NAMES: the analyst's PS-3.x names in requirements.md are canonical; §2.6 sets order only. Where §2.6 names one combined test, the tester writes the PS-3.x-named tests.
- Analyst follow-up (in flight): PS-3.1 `services` field + no --platform; PS-3.2 no-pull check compares tag sets.

## 2026-10-19 — tester: RED unit 1 (L-5 static, both gate services)
- Done: `tests/test_gate_least_privilege.py` (unittest + subTest over `gates`, `gates-it`). Names per PS-3.5: `test_gates_it_is_non_root_with_read_only_repo`, `test_gate_services_run_as_uid_10001` (+ last `USER` in gates.Dockerfile), `test_gate_services_mount_repo_read_only` (checkout `/work` ro; every bind mount of a gate service in every compose file ro, so a future `.env` mask overlay is covered), `test_gate_services_tmp_is_exec_tmpfs` (short `tmpfs:` `/tmp` with `exec`, `mode=1777`, no `noexec`), `test_gates_image_venv_and_uv_cache_owned_by_gate_user` (UV_CACHE_DIR absolute, not under /root|/home, set before first `uv sync`; recursive `chown 10001` of /opt/venv + cache after last sync; safe.directory `/work`, never `*`), `test_gate_services_env_for_read_only_repo` (effective env per service; note gates-it's own `environment:` replaces the anchor's), `test_coverage_data_file_is_under_tmp` (+ subtest: test.sh has no `rm ... .coverage`), `test_coverage_file_env_is_never_set`, `test_uv_no_sync_is_never_set` (non-comment lines of compose, Dockerfiles, scripts/**, workflows; + .env.example for UV_NO_SYNC).
- RED: `COMPOSE_PROJECT_NAME=ke-tester-l5red scripts/verify.sh fast` → 428 tests, failures=20, all in the new module, each "property missing". Lint PASS. Evidence: `docs/evidence/platform-offline/red-l5-verify-fast.txt`.
- Already green (guards, property holds today): `test_coverage_file_env_is_never_set`, `test_uv_no_sync_is_never_set`.
- Deferred to GREEN (integration, full): `test_gates_it_cannot_write_repo`, `test_gates_it_cannot_read_repo_env` (incl. mask overlay present iff `.env` exists), `test_gates_uv_locked_catches_drift_as_non_root`.
- Next (developer): x-gates anchor `user`, ro `/work`, tmpfs, env (also in gates-it's own env block); Dockerfile UV_CACHE_DIR/chown/USER 10001; pyproject data_file; drop `rm -f .coverage.*` from test.sh. Expect checkout-writing tests to surface as EROFS.

## 2026-10-19 — orchestrator: analyst reconcile-2 accepted; RED unit 1 accepted
- Analyst delta: docs/evidence/platform-offline/analyst-reconcile-2.md (bundle.json file/ref/as/services; no --platform; tag-set no-pull test `test_offline_check_fails_when_tag_set_differs_from_as_set`).
- Ruling: the pinned Docker CLI (architect §2.6 #8) gets a PS-3 criterion (analyst, in flight). The CI dind containerd assertion stays (check-only, not operators).
- RED unit 1 checked by orchestrator: 20 failures, all in tests/test_gate_least_privilege.py, each a missing property. Next: developer GREEN unit 1, including the full tests test_gates_it_cannot_write_repo, test_gates_it_cannot_read_repo_env, test_gates_uv_locked_catches_drift_as_non_root.

## 2026-10-19 — developer: GREEN unit 1 (L-5), not committed
- Done: gates image (UV_CACHE_DIR=/opt/uv-cache before sync, chown -R 10001:0 /opt/venv /opt/uv-cache, USER 10001; safe.directory /work already present); compose x-gates (user 10001, `.:/work:ro`, tmpfs /tmp:exec,mode=1777, env MYPY_CACHE_DIR/PYTHONDONTWRITEBYTECODE/GIT_OPTIONAL_LOCKS, also merged into gates-it's own env); pyproject `data_file=/tmp/.coverage`; test.sh `rm -f .coverage.*` dropped. No UV_NO_SYNC.
- `.env` mask built: `docker-compose.gates-mask.yml` (+ committed empty `docker/empty`); verify.sh host half adds it to COMPOSE_FILE (fast and full) only if `./.env` exists. Overlay repeats profiles/network_mode/networks so each definition of a gate service stays complete (existing all-files compose tests iterate overlays).
- New tests: `tests/integration/test_gate_least_privilege.py` (3 PS-3.5 full tests); unit `VerifyHostHalfTest.test_gates_mask_overlay_only_when_env_exists` (fake docker).
- Changed an existing test (flag for review): `test_harness_followups...test_stale_parallel_coverage_data_is_not_combined` asserted test.sh `rm`s stale `.coverage.*` in the checkout, which L-5 forbids. Now asserts: data_file under /tmp, `coverage erase` before first run, test.sh removes nothing in the checkout.
- Container paths writing to /work: none found (verify's log is mktemp -> /tmp; smoke.sh container half writes nothing; the `.env.smoke.*` mktemp is host side only).
- Limits: drift test fails offline on uv's re-resolution ("No solution found ... network disabled") before the "needs to be updated" message, so it accepts either; it cannot tell --locked from plain `uv run` offline. The mask runtime path (.env present) is not exercised in this run: no `.env` on this machine; it is covered by the fake-docker unit test and the empty-file assertion.
- Evidence: `docs/evidence/platform-offline/green-l5-verify-full.txt` (COMPOSE_PROJECT_NAME=ke-dev-l5green; verify full PASS 160s, 429 unit + 11 integration).
- Next: reviewer/security on the diff; orchestrator re-runs full before approving commit.

## 2026-10-19 — orchestrator: PS-3.10 + Q48; GREEN unit 1 to review
- PS-3.10 (pinned docker CLI + compose plugin by SHA-256) added: docs/evidence/platform-offline/analyst-docker-cli.md. Its fast run failed only on the developer's in-flight edits (shared tree), so the developer's full run supersedes it.
- Q48 ruling: if upstream publishes no checksum (docker static CLI), a hash recorded from an HTTPS download.docker.com fetch is acceptable. The handoff records "no upstream checksum", and security confirms it by an independent second fetch. Where upstream publishes one (compose plugin .sha256), the pin must equal it.
- GREEN unit 1 accepted for review (green-l5-verify-full.txt). Notes for review: the rewritten test_stale_parallel_coverage_data_is_not_combined (combine-stale assertion replaced by tmpfs + erase-order); the offline drift test cannot tell --locked from plain run; the .env mask path is not run for real. The orchestrator will run the pre-commit verify with a throwaway .env from .env.example.

## 2026-10-19 — security: audit unit 1 (L-5, PS-3.5)
- Verdict: **PASS** (no critical or high findings). Findings, repro steps and the focus answers are in docs/evidence/platform-offline/security-l5.md. Probe output is in docs/evidence/platform-offline/security-l5-probes.txt.
- Runtime-confirmed: uid 10001 with no effective caps. /work, .git/hooks, .git/config and .git/objects return EROFS. The .env mask reads 0 bytes, read-only, in fast and full. A .env that is a directory fails closed. /opt/venv changes do not survive into the next container. safe.directory is /work only and global git config cannot be written. tmpfs is nosuid,nodev and exec reopens nothing.
- M-1 (medium, fix recommended): verify.sh:32-37. Fast mode with no .env leaves COMPOSE_FILE unpinned, so a COMPOSE_FILE inherited from the caller, or an auto-loaded docker-compose.override.yml (the planned bundle override), can replace `.:/work:ro`. Fix: always export COMPOSE_FILE and the separator in fast mode, plus a fake-docker unit test.
- Low: L-1 gid 0 can write the group-writable PowerShell tree in the image (in-run only; use 10001:10001 or g-w). L-2 add no-new-privileges and cap_drop ALL. L-3 .env.* siblings and .git/config are not masked. L-4 the mask is a time-of-check snapshot taken before build/launch. L-5 the integration mask test passes vacuously without a .env, so keep the orchestrator throwaway-.env run as evidence.
- Not tested: .env as a symlink (no symlink privilege on this host, and the Linux-volume probe was blocked by a tool safety check). The analysis is in the evidence file.
- Note: ke-gates was retagged during the audit by a concurrent ke-review-l5 run, not by security.

## 2026-10-19 — reviewer: GREEN unit 1 (L-5) review, CHANGES REQUESTED
- Verdict: CHANGES REQUESTED, with 2 blocking and 9 non-blocking findings. Detail: `docs/evidence/platform-offline/review-l5.md`. My fast run passed: `review-l5-verify-fast.txt`, ke-review-l5, 429 tests.
- The L-5 config (compose, Dockerfile, pyproject, test.sh) conforms to §2.2 and PS-3.5. The mask works on Docker Desktop: an empty file bound read-only reads 0 bytes, and a write gives EROFS.
- B1: the mask overlay sorts first, so `_find_service` in test_stack_compose reads the overlay. Mutant gates-it on `edge` survives `test_gates_it_internal_only_and_no_socket` with the overlay present and is killed without it. Fix: the overlay keeps only volumes, the helpers read the base file, and a test pins the overlay content.
- B2: the stale-coverage rework is a weakening. `coverage erase` does NOT remove `/tmp/.coverage.*` because `parallel` is not configured (shown by a probe). The test asserts nothing about the hazard. Fix: add `parallel = true` plus a real-erase behavioural test, or name and assert the per-container tmpfs guarantee. Correct the pyproject comment; the claim in architecture §2.2 goes to the architect.
- Drift test: it proves more than the control (`--frozen` passes on drift), but offline it cannot tell `--locked` from a plain run; static tests cover that. Tighten its regex (N3).
- Next: developer fixes B1 and B2 (N1-N4 recommended); then re-review.

## 2026-10-19 — orchestrator: unit-1 rework round 1/5 (review CHANGES REQUESTED, security PASS)
- Fix now (developer): review B1, B2 (take the preferred route: `parallel = true` + a fast test running the real `coverage erase` against a planted stale file), N1–N6. Security M-1 (fast always sets COMPOSE_FILE + COMPOSE_PATH_SEPARATOR; test that caller COMPOSE_FILE and an override file are ignored; this also closes N7), L-1 (`user: "10001:10001"`; the image chowns to 10001:10001), L-2 (`cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]` on both gate services).
- N3 / DR38: add the extra-dependency drift case to the drift test; its run is the evidence.
- Accepted: security L-3 (`.env.*` and `.git/config` readable; noted for auth-audit), L-4 (fails safe), L-5 (my pre-commit run with a throwaway .env, saved per N8).
- N9 (quickstart umask note) → documenter at the docs step. Architect: correct the §2.2 `coverage erase` text.

## 2026-10-19 - developer: unit-1 rework round 1/5 (L-5), not committed
- B1: `docker-compose.gates-mask.yml` now holds only the two mask volumes; test helpers read the base (`_find_service` -> `cs.services()`; the no-bind-mount loop classifies by base service). New `test_gates_mask_overlay_holds_only_the_env_mask` pins the exact content. Mutant M1 (gates-it networks [backend, edge], gates `network_mode` removed in the base) is caught: `test_gates_it_internal_only_and_no_socket` fails (`rework1-l5-mutant-m1.txt`); reverted.
- B2: `parallel = true` in `[tool.coverage.run]`, comment corrected; `test_coverage_erase_removes_stale_parallel_data` runs the real `coverage erase` with the repo's run table (data_file redirected) and checks a planted `.coverage.*` is removed. The B5 test comment is corrected.
- N1 skipTest with reason; N2 append mode + EROFS; N3 tight regex, UV_FROZEN unset, temp venv, extra-dependency case; N4 `.git` file handled; N5 long-syntax `read_only: true` (+ test); N6 chown in the same RUN as `uv sync` (the static test now requires exactly one chown, after the sync).
- Security M-1/N7: fast always exports COMPOSE_FILE (+mask if .env) and `:`; fake-docker test `test_gates_compose_files_are_pinned_whatever_the_caller_sets` (caller COMPOSE_FILE, override file, both modes, with/without .env). L-1: `10001:10001` (compose, USER, chown) + test. L-2: `cap_drop: [ALL]`, `no-new-privileges:true` + test.
- Not run: the masked-.env runtime path (no .env here; the integration test skips with a reason). The offline drift test still cannot tell `--locked` from plain `uv run`. Docs/architecture.md untouched. The `ke-gates` image was rebuilt by the run.
- Evidence: `rework1-l5-verify-full.txt` (PASS 161s, 435 unit + 11 integration, ke-dev-l5r1), `rework1-l5-mutant-m1.txt`.

## 2026-10-19 — reviewer: unit-1 re-review after rework 1/5, APPROVED
- Verdict: APPROVED (0 blocking, 4 nits). Detail: `docs/evidence/platform-offline/review-l5-r1.md`.
- B1, B2 and N1–N7 are verified fixed in the diff, and security M-1, L-1 and L-2 are implemented with tests. A `compose config` probe of base+mask shows the expected merged gate config. No test was weakened.
- M1 collateral (`test_no_model_calls_in_unit_suite`) is expected: it reads the base `gates.network_mode`, which M1 deleted. The gates-it `edge` half is now killed in test_stack_compose.
- Still open: N8 (the orchestrator's throwaway-.env full run must show `test_gates_it_cannot_read_repo_env` ran, not skipped) and N9 (documenter). Verify was not run by the reviewer because the orchestrator's full run was using the shared ke-gates tag.

## 2026-10-19 — orchestrator: unit 1 (L-5) approved for local commit
- Gates: review APPROVED (review-l5-r1.md), security PASS (security-l5.md), orchestrator `scripts/verify.sh full` PASS 158 s with a throwaway .env, and test_gates_it_cannot_read_repo_env ran ok (orchestrator-l5-env-verify-full.txt). Diff read by orchestrator.
- Carry to unit 2: reviewer nits n1–n4; `offline-client` runs as 10001:10001 (L-1 applies there too; architect §2.6 text updates with it); N9 quickstart umask → documenter.

