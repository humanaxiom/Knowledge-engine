# platform-sbom part 14

Plan item: platform-sbom. U8b service, script, wiring and real runs (sections dated 2026-10-28). Live handoff: [../platform-sbom.md](../platform-sbom.md).

## 2026-10-28 — tester (U8b RED)
- Tests: new `tests/test_bundle_fetch.py` (service row by row, `bundle_fetch.sh` static/run on fake docker, CLAUDE.md A73 sentence verbatim, README route out + order, `bundle.sh` header); `U8bLockSbomsTest` (U8-12) in test_sources_resolve.py; offline_check rows renamed to `test_offline_check_fetches_the_sample` / `..._stops_when_the_fetch_fails`; `fake_docker.py` models `run sources-fetch` (real client, `R.OPENER` = FAKE_RESOLVE_NET); sources-fetch bind exemption (exact six binds) in test_stack_compose.py.
- Re-pins (cited U8-7/8/9/12, items 3/8/9): services list, REFUSAL text, obligations order (fetch < pull base), InRelease-failure evdir may hold `sboms/`, a fresh evdir per lock run. Controls `u8/u8b-controls.txt` (only the 2 renames differ).
- RED `u8/u8b-red-verify-fast.txt`: 1186 run, failures=38 (by subtest), all new/re-pinned rows, lint PASS, sentinel ok. Reach proof on scratch targets `u8/u8b-red-reach.txt` (all pass but the index-mode row, which needs .git).
- For the developer: `git add --chmod=+x scripts/bundle_fetch.sh` (shape test reads the index); `[ -e ]` is fine, `docker ... -e` is not; the `fetch.json` check runs after the client.
- Ambiguities for the orchestrator: (1) `--arch` mismatch exit 1 (U8-1, pinned) vs exit 2 (item 3); (2) U8-4 "one FAIL line" vs item 3 step 5's second `sources_fetch.py exited <rc>` line (both pinned per design); (3) N13's README `bundle.sh --sources` and header "the source set it ships" vs U8-9's no-sources-before-U9 rule (tests pin neither); (4) design R6 names `u8b-tester-red-verify-full.txt`, brief asked `fast`.

## 2026-10-28 — developer (U8b GREEN; BLOCKED at the first real sample fetch)
- Built: `sources-fetch` in `docker-compose.sources.yml` (header names both starters), `scripts/bundle_fetch.sh` (staged `git add --chmod=+x`; O-4/O-5), `offline_check.sh` (fetch replaces only the generator pull; trap removes `dist/<project>-sources`; header stage list), `bundle.sh` refusal/header (O-6), `sources_lock.sh` SBOM copies (U8-12), README § Verification + operator order, CLAUDE.md A73 sentence verbatim. No test edited, no URL/host literal in a script.
- Fast run on the tree: 1186 tests, 2 old pins failed (header-stage regex in test_sbom_bundle; `-e` scan in sources_lock.sh), fixed in code, not tests (`u8/u8b-green-first-fast-2-failures.txt`).
- `verify.sh full` (`u8/u8b-green-verify-full.txt`): 1186 unit OK, 15 integration OK, smoke, scan OK; FAILED only at the first real fetch: `gitlab.alpinelinux.org` APKBUILD `OSError` (container: errno 101; host `curl -4`: TCP connect timeout to 172.105.69.85:443; `distfiles.alpinelinux.org` and snapshot answer). Host/network fault, not a lock defect; no lock edit. `u8/sample-run.txt`; `size.md` not started (no bytes fetched).
- Next: rerun `full` where gitlab.alpinelinux.org is reachable (human/network); if it stays unreachable, the architect decides IPv6/alternate-route handling (U7c item 9 candidate). Open: client prints only the exception type (no errno) in its FAIL line.

## 2026-10-28 — security (U8b audit)
- Verdict **PASS** (no critical/high/medium); `u8/u8b-security.md`, probes `u8/u8b-security-probes.txt` (fake docker, compose config with no daemon; nothing real or networked).
- Holds: sources-fetch hardening (default bridge only, literal env, six binds/one writable), no injection via --out/--set/--arch/daemon arch/KE_IMAGE_TAG, trap scope its own ke-fetch project, no URL literal, no retry, offline_check swaps only the generator pull, lock-tool SBOM copies refuse links/existing entries, CLAUDE.md sentence verbatim Q73 opt. 2.
- Low (non-blocking): L-1 `--out link//` or `link/.` passes the symlink refusal (strip all trailing `/`, refuse `.`/`..`, add rows); L-2 the service guard is a denylist (pin exact service and bind keys). Info I-1..I-7: client errno omission is not a security finding (print only the integer errno if wanted, never `str(exc)`); I-6 NEXT-SESSION.md l.109 profile path to redact before staging.
- Not covered by this PASS: verify full is still red at the real sample fetch (upstream unreachable); the real sample, O-1 full set and R9/O-2 remain.

## 2026-10-28 — reviewer (U8b review: CHANGES REQUESTED)
- Read the diff, the new script and tests, and items 3/8/9/12 with O-1..O-7 and U8-1..U8-14. Conformant: O-4, O-5, O-6, A73 verbatim, the service hardening, the offline_check wiring, the U8-12 copies. Controls are clean: test file hashes equal the RED AFTER list.
- Blocking: B-1 `bundle_fetch.sh` l.80 accepts an unlistable non-empty `--out` (fails open on an `ls` error; probe: exit 0, or exit 1 with verified files left beside the operator's file). B-2 cleanup l.95 clears INT/TERM/HUP instead of ignoring them (not "as scan.sh" I-4); a second signal can leak the network or `--out`. Each needs a tester RED row first.
- Non-blocking: N-1 errno in the FAIL line (not blocking; follow-up in `_transport`), N-2 unset DOCKER_DEFAULT_PLATFORM/COMPOSE_ENV_FILES, N-3 empty only an `--out` verified at stage 2, N-4..N-6 nits, N-7 `u8/expected.md` (R8) missing before the rerun, N-8 untracked docs out of scope, N-9 same `ls -A` in bundle.sh (carry to U9).
- Evidence: `docs/evidence/platform-sbom/u8/u8b-review.md`, probes `u8/u8b-review-probes.txt` (read-only, fake docker, uid 10001).

## 2026-10-28 — tester (U8b rework 1 RED: B-1 B-2 N-2 N-3 N-5 L-1 L-2)
- Rows (additions only, `tests/test_bundle_fetch.py`; controls `u8/u8b-r1-controls.txt`, nothing removed): `test_hardening_check_rejects_extra_service_and_bind_keys` (L-2), `..._cleanup_ignores_signals_before_clearing_exit_trap` (B-2 static), `..._cleanup_survives_a_second_signal` (B-2), `..._refuses_an_unlistable_out` (B-1), `..._refuses_a_linked_out_behind_slashes_or_dot` (L-1), `..._leaves_an_out_that_appears_after_the_check` (N-3), `..._keeps_the_callers_platform_and_env_files_out` (N-2), `..._names_compose_when_compose_itself_fails` and `..._passes_the_clients_bad_argument_exit_through` (N-5; the latter green now, a gap pin).
- RED `u8/u8b-r1-red-verify-fast.txt`: 1195 run, failures=34 (by subtest), skipped=8 (as before), all in the new rows; lint PASS, sentinel ok.
- For the developer: L-2 is fixed in the oracle `fetch_service_problems` (allowlist of service keys and bind keys), as the orchestrator's brief allows; N-3: an `--out` absent at stage 2 must be `mkdir`ed (no second `[ -e ]`), so one that appears is refused, not used; N-5: compose failure is pinned only for rc 125 (a code the client never uses).
- Open for the orchestrator: a compose failure with rc 1 (e.g. network create) cannot be told from the client's by rc; not pinned.

## 2026-10-28 — developer (U8b rework 1 GREEN: B-1 B-2 N-2 N-3 N-5 L-1 L-2)
- `scripts/bundle_fetch.sh`: B-1 `ls -A` fails closed; B-2 `trap '' INT TERM HUP` then `trap - EXIT`; N-2 unset DOCKER_DEFAULT_PLATFORM/COMPOSE_ENV_FILES; N-3 `given=1` at stage 2, only a given dir emptied, absent one by plain mkdir; N-5 per O-8 (compose named for 125-127); L-1 all trailing `/` stripped, `.`/`..` refused. Re-staged 100755. Test file: L-2 allowlist in `fetch_service_problems` only.
- `verify.sh fast` PASS: `u8/u8b-r1-green-verify-fast.txt`. Full NOT run: `curl -4 https://gitlab.alpinelinux.org/` timed out at 20 s (BLOCKED upstream); no sample, size.md or hop-hosts.md yet.

## 2026-10-28 — security (U8b re-audit, rework 1)
- **PASS**: L-1, L-2 closed; review B-1, B-2, N-2, N-3, N-5/O-8 hold; nothing weaker than the U8b PASS (`u8/u8b-security.md` § Rework round 1; probes `u8/u8b-r1-security-probes.txt`, links in ke-gates with network none and fake docker).
- Residual info only: a link as a middle `--out` component is followed; `--out /` message blank (I-2); verify full still red at the real fetch (not covered by this PASS).

## 2026-10-28 — reviewer (U8b rework 1: APPROVED)
- B-1, B-2, N-2, N-3, N-5/O-8, L-1 and L-2 closed in `bundle_fetch.sh` and the `fetch_service_problems` allowlist. Test diff is additions only (the tester's rows plus the 8-line allowlist), and nothing is weaker: random-argument and edge probes re-run read-only as uid 10001.
- New nits R1-N1 (the compose row asserts non-zero, not 125) and R1-N2 (mkdir text). Carried: N-1 errno follow-up, N-7 real runs, N-8 untracked docs, N-9 to U9. Evidence: `u8/u8b-review.md` § Rework round 1; probes `u8/u8b-review-probes.txt` R1-1..5.

## 2026-10-28 — tester (U8b A34 Windows proof: PASS)
- Git Bash on Docker Desktop 29.5.2, real network, COMPOSE_PROJECT_NAME unset: `bundle_fetch.sh --set sample --out <new dir>` exit 0 (pull 2 s, fetch 30 s) and again `--arch amd64` into a given empty dir exit 0 (pull 1 s, fetch 25 s); 25 ok lines equal `u8/expected.md` sample amd64 row for row, 25 sha256-named files + fetch.json, every sha256sum equals its name, the two runs byte-identical.
- Refusals: non-empty `--out` exit 1 "stage out ... is not empty", operator file untouched; `--arch arm64` exit 1 naming amd64/x86_64 and arm64, no dir created. 0 ke-fetch networks/projects/containers/volumes after every step; scratch deleted.
- Info: `chmod 0700` on the created `--out` has no visible effect on NTFS (drwxr-xr-x); not a U8b defect. Evidence `u8/a34-windows-run.txt`.

## 2026-10-28 developer: U8b real runs (R8-R10; no code change, nothing staged)
- `COMPOSE_PROJECT_NAME=ke-dev-u8b-real scripts/verify.sh full`: PASS 1113 s (offline_check 233 s); first real sample fetch ok: 25 files, 136571547 bytes, 7 components, 25 s. All 25 rows (key, name, sha256, size) equal u8/expected.md (sorted diff empty). Evidence: u8/u8b-r1-green-verify-full.txt, u8/sample-run.txt (outage record kept below its heading).
- O-1 `bundle_fetch.sh --set full`: exit 0, 716 files, 716 distinct sha256, 1180936586 bytes, 183 components, 614.2 s; fetch.json lock_sha256 = 12eebc8c...761b = expected.md. Scratch dir deleted. Evidence: u8/full-run.txt.
- R10 u8/size.md (local only); R9 u8/hop-hosts.md: deb snapshot.debian.org; pgdg apt-archive.postgresql.org; apk gitlab + distfiles.alpinelinux.org; neo4j github.com -> codeload.github.com; temurin github.com -> release-assets.githubusercontent.com; maven repo1.maven.org; pypi files.pythonhosted.org.
- O-2: objects.githubusercontent.com unused anywhere (0 hits); still in source-policy.json hosts: drop it as a reviewed U8-10 change (policy + design note + test + security).
- Throwaway .env removed. Next: orchestrator decides O-2 and the U8b commit.
