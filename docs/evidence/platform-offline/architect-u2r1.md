# architect: unit-2 rework round 1 (docs only), 2026-10-19

Scope: review B2, security M-1 (staging), M-2/I-1 (exact case, Windows-safe
names), M-3 (trust anchor). Files: `docs/architecture.md` (§2.5 Bundle step 6
and precondition 1, §2.5 Install rewritten as steps 1-9 plus path-comparison
rule and trust-anchor procedure, §2.6 item 5a, ADR-KE-012 status, decision,
alternatives, consequences), `docs/requirements.md` (PS-3.1 *Compose
override* B2 amendment; new block "Unit-2 rework round 1" with six criteria).

Decisions:
- Install order: args → staging copy (0700, `<parent>/.ke-install.<rand>`,
  no link follow, no-clobber, disk check) → manifest on staging (expected
  hash first, then lines/file set/hashes, print accepted hash) → `docker
  info` → bundle.json → `compose config --services` on staged app (coverage
  only; non-zero exit refuses) → load/tag from staging → override 0644 into
  staged app → rename staged app to target. Staging removed on every exit.
- `<out>.manifest.sha256`: one line `<hex>  <basename>/MANIFEST.sha256`,
  beside the bundle, refused if pre-existing.
- `--expect-manifest` / `-ExpectManifest` optional; 64 hex, lowercased;
  mismatch refuses before any docker call.
- Paths: ordinal, case-sensitive everywhere; manifest paths equal after
  lowercasing refused; reserved stems CON/PRN/AUX/NUL/COM1-9/LPT1-9, a
  trailing dot, and `:` refused (space and `:` already excluded by charset).
- Alternatives rejected: hash-the-load-stream (load finishes before the
  verdict), hardlink refusal only (window stays open), staging in system temp
  (no rename).

Proposed test names (tester had not added rework tests when checked; the
orchestrator reconciles): test_install_verifies_and_loads_from_private_staging,
test_install_removes_staging_on_exit, test_install_prints_accepted_manifest_hash,
test_install_refuses_expect_manifest_mismatch,
test_install_refuses_paths_differing_only_by_case,
test_install_refuses_windows_unsafe_names,
test_bundle_writes_manifest_hash_beside_bundle; B2 as a new case of
test_install_fails_when_service_has_no_bundle_entry; quickstart procedure via
test_quickstart_describes_offline_install.

Verify: `COMPOSE_PROJECT_NAME=ke-arch-u2r1 scripts/verify.sh fast` → PASS,
Ran 462 tests, OK (no failures anywhere; the tester's RED had not landed).
Full output: `docs/evidence/platform-offline/architect-u2r1-verify-fast.txt`.
