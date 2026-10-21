# analyst: PS-3.10 pinned Docker CLI (2026-10-19)

- Asked: a PS-3 criterion for the gates image's Docker CLI (architecture §2.2 Lint, §2.6 item 8; orchestrator ruling 2026-10-19).
- Added `docs/requirements.md` PS-3.10; tags summary now lists PS-3.10 under fast.
- Fast static tests (new, all `unit:`):
  - `test_gates_image_pins_docker_cli_by_hash`
  - `test_gates_image_pins_compose_plugin_by_hash`
  - `test_gates_image_compose_plugin_at_least_2_24`
  - `test_gates_image_installs_docker_only_from_pinned_binaries`
  - `test_gate_services_have_no_docker_host`
- Mismatch-fails-build: reviewer mutation check (as PS-3.7); real hashes proven by the image build in `verify.sh full`, binaries by `ci/deployable-offline`.
- Per-arch hashes (amd64, arm64), mirroring the pwsh tarball.
- Open (orchestrator): Docker's static CLI tarball may have no upstream-published checksum; is a hash computed from the download alone acceptable? Not numbered in open-questions.md (analyst limited to requirements.md this turn).
- Verify: `COMPOSE_PROJECT_NAME=ke-analyst-cli scripts/verify.sh fast`, output in `analyst-docker-cli-verify-fast.txt`.
- Result: verify fast FAIL, 428 tests, 3 failures, all in the developer's in-flight GREEN unit 1 (working tree has uncommitted edits to pyproject.toml, scripts/test.sh and others): `test_coverage_data_file_is_under_tmp`, `test_stale_parallel_coverage_data_is_not_combined` (fast, full). None touches requirements.md; this change is docs-only.
