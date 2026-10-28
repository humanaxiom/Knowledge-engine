# Q74: per-test profile of the top-level unit suite (tester, 2026-10-28)

Measurement only: no test, production or config file changed. Raw outputs, tools and generated
tables are in `docs/evidence/platform-sbom/u8/q74-profile/` (`analysis.md`, `spawns.md`,
`ci-per-module.md`, one `.json` per run with every test's timings, `tool-*.txt` = the scripts used,
scratch paths redacted to `<scratch>`).

## Verdict

**The unit-stage growth on CI (912 s at 86f7831 to 1567 s at 0630586) is not caused by the
U7d/U7e tests.** Run the same way in the same gates image on this host, the pre-U7 suite (1047
tests, 86f7831) and the current suite (1110 tests, 0630586) take the same time: 731.4 s vs
736.3 s wall, 645.5 vs 646.4 CPU-s (+4.9 s wall, +0.9 CPU-s). The 65 new tests cost 12.1 s wall
and 9.6 CPU-s in total. On CI, every unchanged module got 1.6-1.9x slower between the two runs,
by the same factor (`q74-profile/ci-per-module.md`), and the gates-it container's own cgroup CPU
use for the unit stage went from 844 CPU-s to 1442 CPU-s for the same work (resource-probe
`cg_cpu_usage_us` deltas; `cpu_steal_ticks` 0 both times; `psi_cpu_some` 189 s -> 458 s). The
runner ran the same instructions slower: a runner/host effect, not suite growth.
This contradicts the attribution in `ci-timing-q74.md` ("+654 s ... the U7d/U7e lock tests").

Neither coverage nor the 3.12.16 base explains it either: under coverage vs without, the wall is
equal (736.3 vs 735.8 s; coverage adds ~20 CPU-s to the parent process only), and the current
suite on the 86f7831 gates image (Python 3.12.15) was not faster (796.5 s, under host load).

What the suite *is*: ~97 % of its CPU is in child processes (`bash`, `pwsh`, `git`, the
fake-docker Python, shellcheck, PSScriptAnalyzer); the test process itself uses 25-53 CPU-s.
It runs ~1 core at a time (CPU-s / wall ~0.88 here, 0.92 on CI), so a 2-vCPU runner's unit stage
is roughly *local wall x runner speed factor*: 1.24x on run 40244299450, 2.13x on 40628987168.
`--cpus 2` locally adds 7-11 %.

## Runs (all in the gates image, gates-service settings, `--network none`)

Runs 1 and 2 (the comparison) ran on clean trees (head: 0630586 plus docs-only WIP). U8a work
landed in the shared checkout while runs 3-7 ran: `tests/test_sources_fetch.py` (untracked, from
local 22:24) and the `scripts/sbom_check.py`/`sources_resolve.py` refactor plus
`scripts/sources_fetch.py` (22:39-22:41, during runs 5-7). The new module's tests are excluded
from every count; the refactor is behaviour-preserving per the reviewer and its tests ran in
under 1 s here. The 2 pre-U7 failures are worktree artefacts
(CRLF checkout of `NOTICE.md`/`install.ps1` on Windows), not timing.

| # | Run | Tree | Image | Coverage | Tests | Wall s | own CPU s | child CPU s | Note |
|---|---|---|---|---|---:|---:|---:|---:|---|
| 1 | head-cov | 0630586 (+docs WIP) | ke-gates wt-33a1 (3.12.16) | yes (as test.sh) | 1110 | 736.3 | 45.7 | 600.6 | paired with 2 |
| 2 | pre-cov | worktree 86f7831 | same | yes | 1047 | 731.4 | 53.1 | 592.4 | 2 FAIL (CRLF) |
| 3 | head-nocov | 0630586 | same | no | 1110 | 735.8 | 25.2 | 626.6 | paired with 4 |
| 4 | pre-nocov | 86f7831 | same | no | 1047 | 737.3 | 33.1 | 616.5 | 2 FAIL (CRLF) |
| 5 | head-oldbase-cov | 0630586 | 86f7831's gates image (3.12.15) | yes | 1110 | 796.5 | 52.1 | 667.1 | 3 runs + other host load |
| 6 | head-cpus2-cov | 0630586 | wt-33a1, `--cpus 2` | yes | 1110 | 818.2 | 48.8 | 655.8 | concurrent with 5, 7 |
| 7 | head-spawns-nocov | 0630586 | wt-33a1 | no, + spawn count | 1110 | 764.3 | 26.4 | 655.7 | control for 5/6 |

Host: 24 CPUs (Docker Desktop, Windows bind mount); the CI runner: nproc 2.

## Slowest 30 tests (run 1, the gate's invocation under coverage)

| # | test | wall s | own CPU s | children CPU s | fixture gap before s |
|---|---|---:|---:|---:|---:|
| 1 | `test_stack_scripts.LintScriptTest.test_lint_runs_no_code_from_a_powershell_filename` | 22.19 | 0.20 | 24.66 | 0.00 |
| 2 | `test_offline_bundle.InstallPs1Test.test_bundle_manifest_rejects_tamper` | 13.88 | 0.08 | 16.27 | 0.00 |
| 3 | `test_offline_bundle.InstallPs1Test.test_install_loads_nothing_when_manifest_fails` | 13.78 | 0.07 | 16.23 | 0.00 |
| 4 | `test_offline_bundle.BundleScriptTest.test_bundle_maps_each_service_to_own_image_despite_dependencies` | 12.65 | 0.51 | 11.62 | 0.00 |
| 5 | `test_psycopg_c.SmokePsycopgTest.test_smoke_checks_psycopg_c_impl_in_api` | 10.12 | 0.04 | 9.65 | 0.00 |
| 6 | `test_offline_bundle.BundleNoticesTest.test_notices_vendor_row_parse_is_strict` | 9.69 | 0.88 | 8.37 | 0.00 |
| 7 | `test_offline_bundle.InstallPs1Test.test_install_refuses_unfit_target_or_daemon` | 9.47 | 0.05 | 10.93 | 0.00 |
| 8 | `test_stack_scripts.LintScriptTest.test_lint_covers_upper_case_ps1_and_psm1` | 9.41 | 0.06 | 10.86 | 0.00 |
| 9 | `test_stack_scripts.LintScriptTest.test_lint_with_real_tools_fails_on_a_planted_finding` | 9.05 | 0.09 | 10.00 | 0.00 |
| 10 | `test_offline_netprobe.SmokeCiOfflineTest.test_ci_offline_fails_naming_the_service_that_gets_out` | 8.92 | 0.03 | 8.59 | 0.00 |
| 11 | `test_offline_bundle.BundleScriptTest.test_arch_normalisation` | 8.53 | 0.36 | 7.77 | 0.00 |
| 12 | `test_sbom_bundle.SbomBundleRunTest.test_bundle_refuses_on_sbom_failure` | 8.33 | 0.35 | 7.48 | 0.00 |
| 13 | `test_neo4j_image.SmokeNoFleetPluginTest.test_smoke_fails_when_the_fleet_plugin_is_in_neo4j` | 8.20 | 0.03 | 7.83 | 0.00 |
| 14 | `test_sbom_bundle.SbomBundleRunTest.test_bundle_has_sbom_per_image` | 7.75 | 0.42 | 6.91 | 0.00 |
| 15 | `test_offline_bundle.InstallPs1Test.test_install_stops_on_signal_to_its_own_pid` | 7.66 | 0.01 | 1.68 | 0.00 |
| 16 | `test_block_main_commit_hook.BlockMainCommitHookTest.test_five_megabyte_command_without_backslash_newline_is_one_pass` | 7.11 | 0.14 | 7.29 | 0.00 |
| 17 | `test_psycopg_c.SmokePsycopgTest.test_smoke_checks_dpkg_libpq5_owns_the_loaded_libpq` | 6.99 | 0.03 | 6.65 | 0.00 |
| 18 | `test_harness_followups.IntegrationRunsOnceTest.test_combine_leaving_a_run_data_file_fails_naming_its_label` | 6.98 | 0.01 | 6.88 | 0.00 |
| 19 | `test_ke_app_no_pip.SmokeNoPipTest.test_smoke_fails_when_pip_is_in_api` | 6.88 | 0.02 | 6.60 | 0.00 |
| 20 | `test_stack_scripts.LintScriptTest.test_lint_shellchecks_upper_case_sh` | 6.65 | 0.05 | 7.49 | 0.00 |
| 21 | `test_offline_bundle.BundleScriptTest.test_bundle_arch_comes_from_daemon` | 6.49 | 0.37 | 5.77 | 0.00 |
| 22 | `test_image_scan.ScanScriptTest.test_scan_second_signal_does_not_abort_cleanup` | 6.48 | 0.03 | 0.29 | 0.00 |
| 23 | `test_sbom_bundle.SbomBundleRunTest.test_sbom_is_spdx_2_3` | 6.45 | 0.23 | 5.85 | 0.00 |
| 24 | `test_offline_bundle.InstallPs1Test.test_install_target_modes_ignore_build_host_umask` | 6.44 | 0.04 | 7.33 | 0.00 |
| 25 | `test_offline_bundle.InstallShTest.test_install_stops_on_signal_to_its_own_pid` | 6.26 | 0.01 | 0.24 | 0.00 |
| 26 | `test_stack_readiness.ReadinessCliTest.test_readiness_cli_condition_never_met` | 6.10 | 0.01 | 1.48 | 0.00 |
| 27 | `test_sbom_bundle.SbomBundleRunTest.test_sbom_lists_every_locked_runtime_package` | 5.92 | 0.28 | 5.26 | 0.00 |
| 28 | `test_offline_bundle.InstallPs1Test.test_install_rejects_bundle_json_missing_field` | 5.77 | 0.03 | 6.62 | 0.00 |
| 29 | `test_sbom_generator.SbomComposeTest.test_sbom_generator_is_pinned` | 5.55 | 0.57 | 0.01 | 0.00 |
| 30 | `test_offline_bundle.InstallPs1Test.test_arch_normalisation` | 5.35 | 0.02 | 5.93 | 0.00 |

No class or module fixture costs anything: the largest setUpClass/setUpModule gap is under 0.01 s. All time is inside test methods.

## Per-module totals, 0630586 vs 86f7831 (runs 1 and 2), sorted by wall delta

| module | head tests | head wall s | head own CPU s | head child CPU s | pre tests | pre wall s | pre own+child CPU s | delta wall s | delta CPU s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test_sources_resolve | 113 | 27.0 | 4.8 | 14.9 | 71 | 16.3 | 11.3 | +10.7 | +8.4 |
| test_engine_hardcoded | 24 | 7.8 | 1.0 | 0.0 | 23 | 7.3 | 1.0 | +0.5 | +0.1 |
| test_stack_entrypoints | 16 | 6.4 | 3.7 | 1.3 | 16 | 5.9 | 4.8 | +0.4 | +0.3 |
| test_sbom_generator | 4 | 12.5 | 1.0 | 6.0 | 4 | 12.1 | 6.8 | +0.4 | +0.2 |
| test_stack_bind_address | 16 | 2.3 | 0.4 | 1.3 | 16 | 2.0 | 1.5 | +0.3 | +0.2 |
| test_sources_lock_committed | 7 | 0.3 | 0.2 | 0.0 | 0 | 0.0 | 0.0 | +0.3 | +0.2 |
| test_harness_followups | 41 | 47.3 | 0.2 | 43.9 | 41 | 47.1 | 44.0 | +0.2 | +0.1 |
| test_sbom_bundle | 14 | 33.3 | 1.8 | 29.2 | 14 | 33.2 | 31.0 | +0.1 | +0.0 |
| test_offline_netprobe | 19 | 27.4 | 0.1 | 26.0 | 19 | 27.3 | 26.1 | +0.1 | +0.1 |
| test_gate_least_privilege | 14 | 0.9 | 0.5 | 0.1 | 14 | 0.8 | 0.6 | +0.1 | +0.0 |
| test_stack_model_skip | 8 | 0.6 | 0.4 | 0.0 | 8 | 0.5 | 0.4 | +0.1 | +0.0 |
| test_harness_port | 20 | 0.2 | 0.1 | 0.0 | 20 | 0.2 | 0.0 | +0.1 | +0.0 |
| test_ke_app_no_pip | 4 | 13.2 | 0.1 | 12.6 | 4 | 13.2 | 12.6 | +0.1 | +0.1 |
| test_offline_check | 26 | 23.0 | 1.8 | 17.1 | 26 | 22.9 | 18.9 | +0.1 | -0.0 |
| test_block_main_commit_hook | 56 | 20.7 | 0.5 | 19.8 | 56 | 20.7 | 20.2 | +0.0 | +0.1 |
| test_psycopg_c | 13 | 22.9 | 0.3 | 21.6 | 12 | 22.9 | 22.0 | +0.0 | -0.1 |
| test_engine_telemetry | 14 | 0.5 | 0.4 | 0.0 | 14 | 0.5 | 0.4 | +0.0 | +0.0 |
| test_tracing | 8 | 0.0 | 0.0 | 0.0 | 8 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_engine_egress | 8 | 0.3 | 0.2 | 0.0 | 8 | 0.3 | 0.2 | +0.0 | +0.0 |
| test_engine_quality | 5 | 0.0 | 0.0 | 0.0 | 5 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_log_event | 4 | 0.0 | 0.0 | 0.0 | 4 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_sentinel | 1 | 0.0 | 0.0 | 0.0 | 1 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_engine_notices | 7 | 0.0 | 0.0 | 0.0 | 7 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_stack_ready_compose | 7 | 0.1 | 0.1 | 0.0 | 7 | 0.1 | 0.1 | -0.0 | +0.0 |
| test_engine_llm | 2 | 0.0 | 0.0 | 0.0 | 2 | 0.0 | 0.0 | -0.0 | +0.0 |
| test_stack_ready_docs | 5 | 0.0 | 0.0 | 0.0 | 5 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_stack_scripts | 119 | 114.3 | 1.9 | 104.1 | 119 | 114.3 | 106.3 | -0.0 | -0.2 |
| test_engine_deploy_files | 2 | 0.0 | 0.0 | 0.0 | 2 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_stack_carry_ins | 4 | 0.0 | 0.0 | 0.0 | 4 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_image_scan | 33 | 15.8 | 0.8 | 6.1 | 33 | 15.8 | 7.0 | -0.0 | -0.1 |
| test_stack_model_keys | 12 | 1.0 | 0.1 | 0.8 | 12 | 1.0 | 0.8 | -0.0 | -0.0 |
| test_engine_config | 20 | 0.4 | 0.3 | 0.0 | 20 | 0.4 | 0.3 | -0.0 | -0.0 |
| test_engine_startup | 22 | 1.9 | 1.5 | 0.0 | 22 | 1.9 | 1.5 | -0.0 | -0.0 |
| test_resource_probe | 9 | 0.9 | 0.1 | 0.6 | 9 | 0.9 | 0.7 | -0.0 | -0.0 |
| test_engine_tracing_guard | 22 | 0.8 | 0.7 | 0.0 | 22 | 0.8 | 0.7 | -0.0 | -0.0 |
| test_neo4j_image | 21 | 23.3 | 0.9 | 20.5 | 21 | 23.4 | 21.6 | -0.0 | -0.1 |
| test_notice_ke_app | 6 | 0.2 | 0.1 | 0.0 | 6 | 0.2 | 0.1 | -0.0 | -0.0 |
| test_stack_worker | 10 | 0.2 | 0.2 | 0.0 | 10 | 0.2 | 0.2 | -0.0 | -0.0 |
| test_gates_docker_cli | 13 | 0.2 | 0.1 | 0.0 | 13 | 0.2 | 0.1 | -0.0 | -0.0 |
| test_stack_compose | 24 | 1.7 | 1.3 | 0.0 | 24 | 1.8 | 1.4 | -0.2 | -0.1 |
| test_sbom_obligations | 44 | 33.2 | 5.5 | 23.5 | 43 | 33.6 | 29.2 | -0.3 | -0.2 |
| test_offline_bundle | 165 | 271.5 | 10.3 | 244.4 | 165 | 271.9 | 255.1 | -0.4 | -0.4 |
| test_stack_readiness | 19 | 14.8 | 0.5 | 4.8 | 19 | 15.2 | 5.4 | -0.4 | -0.2 |
| test_sources_lock | 50 | 7.1 | 2.8 | 2.0 | 39 | 10.2 | 8.1 | -3.1 | -3.3 |
| test_sbom_classifier | 59 | 2.3 | 1.1 | 0.0 | 59 | 6.2 | 5.0 | -3.9 | -3.9 |
| **total** | 1110 | 736.3 | 45.7 | 600.6 | 1047 | 731.4 | 645.5 | +4.9 | +0.9 |

New tests in 0630586: 65, 12.1 s wall, 9.6 CPU-s; 2 pre-U7 tests renamed. `test_sources_lock` and `test_sbom_classifier` read faster at head (-3 to -4 s); same-sized noise is `test_offline_bundle` +/-10 s between paired runs.

## CI per module, both runs, against local run 1

| module | CI 86f7831 s | CI 0630586 s | CI ratio | local 0630586 s | CI 0630586 / local |
|---|---:|---:|---:|---:|---:|
| test_offline_bundle | 338.3 | 574.0 | 1.70 | 271.5 | 2.11 |
| test_stack_scripts | 192.0 | 315.1 | 1.64 | 114.3 | 2.76 |
| test_harness_followups | 55.4 | 96.7 | 1.75 | 47.3 | 2.05 |
| test_sbom_obligations | 39.8 | 69.2 | 1.74 | 33.2 | 2.08 |
| test_sbom_bundle | 41.1 | 69.0 | 1.68 | 33.3 | 2.07 |
| test_offline_netprobe | 35.2 | 57.0 | 1.62 | 27.4 | 2.08 |
| test_psycopg_c | 28.3 | 48.2 | 1.70 | 22.9 | 2.10 |
| test_neo4j_image | 26.7 | 47.2 | 1.77 | 23.3 | 2.02 |
| test_sources_resolve | 16.1 | 47.1 | 2.93 | 27.0 | 1.75 |
| test_offline_check | 26.3 | 45.4 | 1.72 | 23.0 | 1.97 |
| test_block_main_commit_hook | 23.9 | 44.4 | 1.86 | 20.7 | 2.14 |
| test_ke_app_no_pip | 17.1 | 28.2 | 1.65 | 13.2 | 2.13 |
| test_sources_lock | 11.2 | 21.6 | 1.93 | 7.1 | 3.05 |
| test_image_scan | 14.9 | 20.9 | 1.41 | 15.8 | 1.33 |
| test_stack_readiness | 15.0 | 20.0 | 1.34 | 14.8 | 1.36 |
| test_sbom_generator | 8.6 | 14.4 | 1.67 | 12.5 | 1.15 |
| test_sbom_classifier | 5.0 | 12.8 | 2.57 | 2.3 | 5.66 |
| test_stack_entrypoints | 7.6 | 12.2 | 1.62 | 6.4 | 1.92 |
| test_stack_compose | 1.7 | 6.6 | 3.85 | 1.7 | 4.02 |
| test_engine_startup | 1.9 | 3.8 | 1.99 | 1.9 | 2.06 |
| ... (rest in `q74-profile/ci-per-module.md`) | | | | | |

CI ratio between the runs is 1.6-1.9 on every module with more than a few seconds, including the untouched `test_offline_bundle` (338 -> 574 s) and `test_stack_scripts` (192 -> 315 s). `test_sources_resolve` grew 16 -> 47 s on CI (most of the 12.1 s the new tests cost locally; the module itself is 27 s locally).

## Where the time goes, and cheap fixes (estimates, nothing changed)

Direct spawns from the test process (run 7): 2706 (`bash` 1358, `git` 618, `sh` 467, `pwsh` 175,
`python3` 69). Grandchildren (fake docker, shellcheck) are not counted but are in child CPU.
Per-class table with spawns: `q74-profile/spawns.md`. Savings are local seconds; on CI multiply
by the runner factor (1.24-2.13x). None of them is a U7d/U7e cost.

1. **`test_offline_bundle.InstallPs1Test`, 133 s for 44 tests, 128 `pwsh` runs at ~1 s each.**
   Every case runs the real `install.ps1` under `pwsh` against fake docker on a fresh fixture
   bundle. `test_bundle_manifest_rejects_tamper` and `test_install_loads_nothing_when_manifest_fails`
   (13.9 + 13.8 s, 21 `pwsh` runs each) loop over the same `_tamper_cases()` with identical
   installs and only assert different things on the result. One loop asserting both: **~14 s
   local (~30 s on the slow runner)**, same coverage of behaviour. Applies to the
   `InstallShTest` twin too (cheap, bash). Any further cut means fewer `pwsh` runs (pwsh start
   alone is 0.17 s; the rest is install.ps1 itself and its docker calls).
2. **`test_stack_scripts.LintScriptTest`, 57 s for 15 tests.** Each `_project()` copies every
   `scripts/*.sh`, `docker/**/*.sh` and `scripts/*.ps1` into a git repo and runs the real
   `lint.sh` (shellcheck + PSScriptAnalyzer over all of them, ~2.4 s a run).
   `test_lint_runs_no_code_from_a_powershell_filename` alone does 10 such runs (22-25 s here,
   56 s and 91 s in the two CI runs: the slowest test on CI). The filename-injection and
   upper-case tests need only `lint.sh` plus the planted file; a minimal project for those three
   tests: **~30 s local (~65 s on the slow runner)**. The real-tools planted-finding test keeps
   the full set.
3. **Full `bundle.sh` runs, one per assertion.** `BundleScriptTest` (87 s), `BundleNoticesTest`
   (43 s), `SbomBundleRunTest` (34 s) and `sbom_obligations` bundle classes each run a complete
   `bundle.sh` (~2.4 s) per test; 23 tests do exactly one bash run each (66 s), many asserting on
   an unmodified default bundle. One shared default run per class (`setUpClass`, read-only
   assertions on its output): **up to ~45 s local**, less where a test needs its own inputs
   (per-test check needed).

Smaller: `test_harness_followups.IntegrationRunsOnceTest` 47 s (60 runs of `test.sh` variants,
0.8 s each); `SmokeCiOfflineTest` 29 s, `SmokePsycopgTest` 25 s (real `smoke.sh` per case).

Ruled out as causes, by measurement: `lock_problems` over the committed lock
(`test_sources_lock_committed`, 7 tests, 0.3 s in total; `test_no_lock_problems` 0.17 s); the
fake-network resolver (`U7dPgdgRouteTest` 1.2 s, `U7dRetryTest` 1.0 s, `U7dCoverageTest` 0.4 s);
sha256 over fixtures (in-process CPU in the whole suite is 25-53 s); coverage tracing (+0 s wall,
the children it does not trace hold the time); setUpClass fixtures (none costs > 0.01 s).
The largest new-test cost is `ReworkR1U7dScriptTest` (8.0 s, 5 tests, fake-docker
`sources_lock.sh` runs).

## What this means for Q74

The suite's local cost is ~736 s and did not grow with U7d/U7e. CI's unit stage is that times a
runner factor that varied 1.24x -> 2.13x between two runs three days apart on the same runner
label. Fixes 1-3 together save ~90 s local (~190 s at 2.13x). A timeout sized from one CI run
will flap with that factor; sizing needs the factor's spread (more CI samples) or a CPU-time
budget (`cg_cpu_usage_us`, already printed by the resource probe) rather than wall clock.

## Commands

```
# image (cached build of the current gates image)
KE_IMAGE_TAG=wt-33a132fbfdd7 COMPOSE_PROJECT_NAME=ke-tprof-q74 COMPOSE_FILE=docker-compose.yml \
  docker compose --env-file .env.example --profile gates build gates
# pre-U7 tree and image
git worktree add --detach <scratch>/pre-u7 86f7831
docker build -f docker/gates.Dockerfile -t ke-gates:q74-pre86f7831 <scratch>/pre-u7
# each run: tool-dockrun.sh.txt -> tool-inner.sh.txt -> tool-profrun.py.txt
#   docker run --rm --network none --user 10001:10001 --cap-drop ALL
#     --security-opt no-new-privileges:true -v <repo>:/work:ro --tmpfs /tmp:exec,mode=1777
#     -e MYPY_CACHE_DIR=/tmp/mypy -e PYTHONDONTWRITEBYTECODE=1 -e GIT_OPTIONAL_LOCKS=0
#     -v <scratch>/prof:/prof:ro -v <scratch>/out:/out -w /work <image> bash /prof/inner.sh <label> cov|nocov
#   inside: uv run --locked python -m coverage run -p --data-file=/tmp/.coverage.toplevel \
#             /prof/profrun.py /out/<label>.json -v tests.test_* (the test.sh module list)
#   pre-U7 adds: -v <scratch>/prof/pre-u7.gitfile:/work/.git:ro -v <repo>/.git:/gitmain:ro
bash tool-dockrun.sh head cov <repo>;  bash tool-dockrun.sh pre cov <scratch>/pre-u7 ...
bash tool-dockrun.sh head nocov <repo>; bash tool-dockrun.sh pre nocov <scratch>/pre-u7 ...
IMAGE=ke-gates:q74-pre86f7831 bash tool-dockrun.sh head-oldbase cov <repo>
bash tool-dockrun.sh head-cpus2 cov <repo> --cpus 2
bash tool-dockrun.sh head-spawns nocov <repo> -e PROF_COUNT_SPAWNS=1
python tool-analyze.py <out>; python tool-ci_modules.py <out>
gh run view 40244299450 --log; gh run view 40628987168 --log   # CI logs (not saved; excerpts in q74-profile/ci-*.txt)
git worktree remove <scratch>/pre-u7
```

`scripts/verify.sh fast` was run once afterwards with these evidence files in the tree (and the
U8a WIP of other roles): PASS, `Ran 1140 tests in 726.762s` (`q74-profile/verify-fast.txt`), a
further data point for the ~730 s local unit stage. No gate is claimed for U8a by this run.
