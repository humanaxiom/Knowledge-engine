## Direct subprocess spawns from the test process (head-spawns-nocov), by argv[0]

| argv[0] | spawns |
|---|---:|
| `bash` | 1358 |
| `git` | 618 |
| `sh` | 467 |
| `pwsh` | 175 |
| `python3` | 69 |
| `docker` | 15 |
| `snap.py` | 2 |
| `git-not-installed-ke-u1` | 1 |
| `nproc` | 1 |
| **total** | 2706 |

## Top 15 modules by wall, with direct spawns

| module | tests | wall s | CPU s | direct spawns | wall s per spawn | main argv[0]s |
|---|---:|---:|---:|---:|---:|---|
| test_offline_bundle | 165 | 294.2 | 282.3 | 606 | 0.49 | bash 289, git 182, pwsh 128 |
| test_stack_scripts | 119 | 118.5 | 114.2 | 416 | 0.28 | bash 229, git 140, pwsh 47 |
| test_harness_followups | 41 | 46.9 | 43.8 | 89 | 0.53 | bash 89 |
| test_sbom_bundle | 14 | 35.0 | 32.4 | 60 | 0.58 | git 28, bash 28, python3 4 |
| test_sbom_obligations | 44 | 33.0 | 28.3 | 89 | 0.37 | git 60, bash 24, docker 5 |
| test_offline_netprobe | 19 | 29.9 | 28.4 | 41 | 0.73 | bash 29, python3 12 |
| test_sources_resolve | 113 | 25.8 | 18.9 | 125 | 0.21 | git 94, bash 26, python3 5 |
| test_psycopg_c | 13 | 24.7 | 23.6 | 33 | 0.75 | bash 33 |
| test_offline_check | 26 | 24.5 | 19.9 | 56 | 0.44 | bash 52, docker 2, snap.py 2 |
| test_neo4j_image | 21 | 23.9 | 21.6 | 36 | 0.66 | bash 27, python3 5, git 4 |
| test_block_main_commit_hook | 56 | 21.1 | 20.9 | 450 | 0.05 | bash 372, git 74, python3 3 |
| test_stack_readiness | 19 | 15.3 | 5.7 | 10 | 1.53 | python3 10 |
| test_image_scan | 33 | 15.2 | 6.6 | 63 | 0.24 | bash 55, git 7, docker 1 |
| test_ke_app_no_pip | 4 | 13.9 | 13.3 | 19 | 0.73 | bash 19 |
| test_sbom_generator | 4 | 13.1 | 7.1 | 16 | 0.82 | git 10, bash 6 |

## Top 20 classs by wall, with direct spawns

| class | tests | wall s | CPU s | direct spawns | wall s per spawn | main argv[0]s |
|---|---:|---:|---:|---:|---:|---|
| test_offline_bundle.InstallPs1Test | 44 | 133.5 | 139.9 | 137 | 0.97 | pwsh 128, bash 9 |
| test_offline_bundle.BundleScriptTest | 29 | 86.9 | 79.5 | 193 | 0.45 | git 119, bash 67, docker 7 |
| test_stack_scripts.LintScriptTest | 15 | 56.8 | 62.9 | 189 | 0.30 | git 140, bash 48, pwsh 1 |
| test_harness_followups.IntegrationRunsOnceTest | 23 | 46.5 | 43.4 | 60 | 0.78 | bash 60 |
| test_offline_bundle.BundleNoticesTest | 14 | 43.0 | 39.7 | 108 | 0.40 | git 62, bash 46 |
| test_sbom_bundle.SbomBundleRunTest | 7 | 34.4 | 32.1 | 56 | 0.61 | git 28, bash 28 |
| test_offline_netprobe.SmokeCiOfflineTest | 8 | 29.3 | 28.0 | 29 | 1.01 | bash 29 |
| test_offline_bundle.InstallShTest | 47 | 28.1 | 20.8 | 151 | 0.19 | bash 151 |
| test_psycopg_c.SmokePsycopgTest | 5 | 24.5 | 23.4 | 33 | 0.74 | bash 33 |
| test_offline_check.OfflineCheckScriptTest | 16 | 23.9 | 19.4 | 47 | 0.51 | bash 45, snap.py 2 |
| test_stack_scripts.LaunchPs1ResolvedTest | 12 | 19.3 | 17.1 | 32 | 0.60 | pwsh 30, bash 2 |
| test_block_main_commit_hook.BlockMainCommitHookTest | 46 | 18.0 | 18.9 | 446 | 0.04 | bash 372, git 74 |
| test_neo4j_image.SmokeNoFleetPluginTest | 3 | 15.6 | 14.9 | 19 | 0.82 | bash 19 |
| test_stack_readiness.ReadinessCliTest | 4 | 14.8 | 5.3 | 10 | 1.48 | python3 10 |
| test_stack_scripts.SmokeStoreStopStartTest | 9 | 14.3 | 13.6 | 14 | 1.02 | bash 14 |
| test_ke_app_no_pip.SmokeNoPipTest | 3 | 13.9 | 13.3 | 19 | 0.73 | bash 19 |
| test_image_scan.ScanScriptTest | 22 | 12.7 | 4.4 | 55 | 0.23 | bash 54, docker 1 |
| test_sbom_obligations.SbomCarryU4Test | 6 | 10.2 | 9.0 | 28 | 0.36 | git 24, bash 4 |
| test_sources_resolve.ReworkR1LockScriptRunTest | 7 | 7.9 | 6.8 | 52 | 0.15 | git 42, bash 10 |
| test_sources_resolve.ReworkR1U7dScriptTest | 5 | 7.9 | 7.0 | 39 | 0.20 | git 30, bash 9 |

## Slowest 15 tests with their direct spawns

| test | wall s | spawns |
|---|---:|---|
| `test_stack_scripts.LintScriptTest.test_lint_runs_no_code_from_a_powershell_filename` | 24.61 | git 30, bash 10 |
| `test_offline_bundle.InstallPs1Test.test_install_loads_nothing_when_manifest_fails` | 16.79 | pwsh 21 |
| `test_offline_bundle.InstallPs1Test.test_bundle_manifest_rejects_tamper` | 15.84 | pwsh 21 |
| `test_offline_bundle.BundleScriptTest.test_bundle_maps_each_service_to_own_image_despite_dependencies` | 14.33 | docker 7, bash 6, git 4 |
| `test_psycopg_c.SmokePsycopgTest.test_smoke_checks_psycopg_c_impl_in_api` | 11.02 | bash 14 |
| `test_offline_bundle.InstallPs1Test.test_install_refuses_unfit_target_or_daemon` | 10.33 | pwsh 14 |
| `test_offline_bundle.BundleNoticesTest.test_notices_vendor_row_parse_is_strict` | 9.84 | bash 16, git 4 |
| `test_stack_scripts.LintScriptTest.test_lint_covers_upper_case_ps1_and_psm1` | 9.81 | git 12, bash 4 |
| `test_stack_scripts.LintScriptTest.test_lint_with_real_tools_fails_on_a_planted_finding` | 9.73 | git 11, bash 4 |
| `test_offline_netprobe.SmokeCiOfflineTest.test_ci_offline_fails_naming_the_service_that_gets_out` | 9.60 | bash 10 |
| `test_offline_bundle.BundleScriptTest.test_arch_normalisation` | 8.90 | bash 6, git 4 |
| `test_neo4j_image.SmokeNoFleetPluginTest.test_smoke_fails_when_the_fleet_plugin_is_in_neo4j` | 8.64 | bash 12 |
| `test_sbom_bundle.SbomBundleRunTest.test_bundle_refuses_on_sbom_failure` | 8.41 | bash 6, git 4 |
| `test_sbom_bundle.SbomBundleRunTest.test_bundle_has_sbom_per_image` | 8.22 | bash 5, git 4 |
| `test_offline_bundle.InstallPs1Test.test_install_stops_on_signal_to_its_own_pid` | 7.97 | pwsh 2 |
