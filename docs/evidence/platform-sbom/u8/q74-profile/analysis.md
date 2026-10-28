### head-cov: 1110 tests; process wall 737.8 s, own CPU 46.8 s, reaped-children CPU 600.6 s; import/load 1.5 s wall / 1.1 s CPU; results {'ok': 1102, 'skip': 8}

### pre-cov: 1047 tests; process wall 733.1 s, own CPU 54.3 s, reaped-children CPU 592.4 s; import/load 1.6 s wall / 1.2 s CPU; results {'ok': 1037, 'FAIL': 2, 'skip': 8}

### head-nocov: 1110 tests; process wall 736.9 s, own CPU 25.9 s, reaped-children CPU 626.6 s; import/load 1.0 s wall / 0.6 s CPU; results {'ok': 1102, 'skip': 8}

### pre-nocov: 1047 tests; process wall 738.4 s, own CPU 33.9 s, reaped-children CPU 616.5 s; import/load 1.1 s wall / 0.8 s CPU; results {'ok': 1037, 'FAIL': 2, 'skip': 8}

## Slowest 30 tests, head-cov (the gate's own invocation, under coverage)

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

## Largest fixture gaps (setUpModule/setUpClass of the next class + tearDownClass of the previous), head-cov

| next test | gap wall s | gap own CPU s | gap children CPU s |
|---|---:|---:|---:|
| `test_sources_resolve.U7cCarriedTest.test_a_server_supplied_url_gets_the_hop_rules` | 0.00 | 0.00 | 0.00 |
| `test_neo4j_image.Neo4jCheckerCliTest.test_neo4j_checker_cli` | 0.00 | 0.00 | 0.00 |
| `test_block_main_commit_hook.BlockMainCommitHookTest.test_backslash_forms_deny_push_off_main` | 0.00 | 0.00 | 0.00 |
| `test_ke_app_no_pip.KeAppNoPipStaticTest.test_ke_app_last_stage_removes_pip` | 0.00 | 0.00 | 0.00 |
| `test_engine_deploy_files.GitIgnoreTest.test_env_example_is_not_ignored` | 0.00 | 0.00 | 0.00 |
| `test_sources_lock.LockCoverageTest.test_a_missing_key_names_every_package` | 0.00 | 0.00 | 0.00 |
| `test_stack_bind_address.LaunchScriptTest.test_launch_ps1_checks_bind_address` | 0.00 | 0.00 | 0.00 |
| `test_resource_probe.ResourceProbeTest.test_oversized_source_is_cut_off` | 0.00 | 0.00 | 0.00 |
| `test_image_scan.ScanScriptTest.test_scan_tar_is_world_readable_before_any_compose_call` | 0.00 | 0.00 | 0.00 |
| `test_sbom_generator.SbomComposeTest.test_sbom_generator_is_pinned` | 0.00 | 0.00 | 0.00 |

## Per-module totals, head-cov vs pre-cov (86f7831), sorted by wall delta

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

## Coverage multiplier per module: head-cov vs head-nocov

| module | cov tests | cov wall s | cov own CPU s | cov child CPU s | nocov tests | nocov wall s | nocov own+child CPU s | delta wall s | delta CPU s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test_sbom_obligations | 44 | 33.2 | 5.5 | 23.5 | 44 | 31.0 | 27.1 | +2.2 | +1.9 |
| test_stack_entrypoints | 16 | 6.4 | 3.7 | 1.3 | 16 | 4.3 | 3.1 | +2.0 | +1.9 |
| test_sources_lock | 50 | 7.1 | 2.8 | 2.0 | 50 | 5.3 | 3.3 | +1.8 | +1.5 |
| test_sources_resolve | 113 | 27.0 | 4.8 | 14.9 | 113 | 25.3 | 18.3 | +1.7 | +1.4 |
| test_block_main_commit_hook | 56 | 20.7 | 0.5 | 19.8 | 56 | 19.3 | 19.0 | +1.4 | +1.2 |
| test_engine_startup | 22 | 1.9 | 1.5 | 0.0 | 22 | 1.0 | 0.6 | +0.9 | +0.8 |
| test_stack_compose | 24 | 1.7 | 1.3 | 0.0 | 24 | 1.1 | 0.6 | +0.6 | +0.7 |
| test_engine_hardcoded | 24 | 7.8 | 1.0 | 0.0 | 24 | 7.2 | 0.8 | +0.6 | +0.2 |
| test_sbom_classifier | 59 | 2.3 | 1.1 | 0.0 | 59 | 1.7 | 0.7 | +0.5 | +0.4 |
| test_stack_bind_address | 16 | 2.3 | 0.4 | 1.3 | 16 | 1.9 | 1.5 | +0.4 | +0.2 |
| test_gate_least_privilege | 14 | 0.9 | 0.5 | 0.1 | 14 | 0.5 | 0.3 | +0.4 | +0.3 |
| test_engine_tracing_guard | 22 | 0.8 | 0.7 | 0.0 | 22 | 0.4 | 0.3 | +0.4 | +0.4 |
| test_engine_telemetry | 14 | 0.5 | 0.4 | 0.0 | 14 | 0.2 | 0.2 | +0.2 | +0.2 |
| test_stack_scripts | 119 | 114.3 | 1.9 | 104.1 | 119 | 114.0 | 109.3 | +0.2 | -3.2 |
| test_stack_model_skip | 8 | 0.6 | 0.4 | 0.0 | 8 | 0.4 | 0.2 | +0.2 | +0.2 |
| test_sources_lock_committed | 7 | 0.3 | 0.2 | 0.0 | 7 | 0.2 | 0.1 | +0.1 | +0.2 |
| test_harness_followups | 41 | 47.3 | 0.2 | 43.9 | 41 | 47.2 | 44.0 | +0.1 | +0.1 |
| test_gates_docker_cli | 13 | 0.2 | 0.1 | 0.0 | 13 | 0.1 | 0.0 | +0.1 | +0.1 |
| test_stack_worker | 10 | 0.2 | 0.2 | 0.0 | 10 | 0.1 | 0.1 | +0.1 | +0.1 |
| test_engine_config | 20 | 0.4 | 0.3 | 0.0 | 20 | 0.3 | 0.2 | +0.1 | +0.1 |
| test_stack_ready_compose | 7 | 0.1 | 0.1 | 0.0 | 7 | 0.1 | 0.0 | +0.0 | +0.1 |
| test_notice_ke_app | 6 | 0.2 | 0.1 | 0.0 | 6 | 0.1 | 0.1 | +0.0 | +0.0 |
| test_stack_model_keys | 12 | 1.0 | 0.1 | 0.8 | 12 | 1.0 | 0.8 | +0.0 | +0.0 |
| test_engine_egress | 8 | 0.3 | 0.2 | 0.0 | 8 | 0.3 | 0.2 | +0.0 | +0.0 |
| test_harness_port | 20 | 0.2 | 0.1 | 0.0 | 20 | 0.2 | 0.0 | +0.0 | +0.0 |
| test_stack_carry_ins | 4 | 0.0 | 0.0 | 0.0 | 4 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_engine_notices | 7 | 0.0 | 0.0 | 0.0 | 7 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_engine_llm | 2 | 0.0 | 0.0 | 0.0 | 2 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_stack_ready_docs | 5 | 0.0 | 0.0 | 0.0 | 5 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_engine_quality | 5 | 0.0 | 0.0 | 0.0 | 5 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_log_event | 4 | 0.0 | 0.0 | 0.0 | 4 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_engine_deploy_files | 2 | 0.0 | 0.0 | 0.0 | 2 | 0.0 | 0.0 | +0.0 | -0.0 |
| test_tracing | 8 | 0.0 | 0.0 | 0.0 | 8 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_sentinel | 1 | 0.0 | 0.0 | 0.0 | 1 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_sbom_bundle | 14 | 33.3 | 1.8 | 29.2 | 14 | 33.4 | 31.1 | -0.0 | -0.1 |
| test_stack_readiness | 19 | 14.8 | 0.5 | 4.8 | 19 | 14.8 | 5.2 | -0.0 | +0.0 |
| test_neo4j_image | 21 | 23.3 | 0.9 | 20.5 | 21 | 23.5 | 21.5 | -0.2 | -0.1 |
| test_resource_probe | 9 | 0.9 | 0.1 | 0.6 | 9 | 1.1 | 0.9 | -0.2 | -0.2 |
| test_offline_netprobe | 19 | 27.4 | 0.1 | 26.0 | 19 | 27.7 | 26.3 | -0.3 | -0.1 |
| test_psycopg_c | 13 | 22.9 | 0.3 | 21.6 | 13 | 23.3 | 22.2 | -0.4 | -0.3 |
| test_offline_check | 26 | 23.0 | 1.8 | 17.1 | 26 | 23.4 | 19.1 | -0.4 | -0.3 |
| test_image_scan | 33 | 15.8 | 0.8 | 6.1 | 33 | 16.4 | 7.6 | -0.6 | -0.7 |
| test_ke_app_no_pip | 4 | 13.2 | 0.1 | 12.6 | 4 | 14.3 | 13.6 | -1.0 | -1.0 |
| test_sbom_generator | 4 | 12.5 | 1.0 | 6.0 | 4 | 13.5 | 6.9 | -1.0 | +0.1 |
| test_offline_bundle | 165 | 271.5 | 10.3 | 244.4 | 165 | 281.0 | 266.5 | -9.6 | -11.8 |
| **total** | 1110 | 736.3 | 45.7 | 600.6 | 1110 | 735.8 | 651.8 | +0.5 | -5.4 |

## Coverage multiplier per module: pre-cov vs pre-nocov

| module | cov tests | cov wall s | cov own CPU s | cov child CPU s | nocov tests | nocov wall s | nocov own+child CPU s | delta wall s | delta CPU s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test_sources_lock | 39 | 10.2 | 6.0 | 2.2 | 39 | 8.7 | 6.6 | +1.5 | +1.5 |
| test_block_main_commit_hook | 56 | 20.7 | 0.5 | 19.7 | 56 | 19.2 | 18.9 | +1.5 | +1.3 |
| test_stack_entrypoints | 16 | 5.9 | 3.6 | 1.2 | 16 | 4.5 | 3.2 | +1.4 | +1.6 |
| test_sbom_obligations | 43 | 33.6 | 6.0 | 23.2 | 43 | 32.2 | 27.6 | +1.3 | +1.6 |
| test_engine_startup | 22 | 1.9 | 1.5 | 0.0 | 22 | 1.0 | 0.7 | +0.8 | +0.8 |
| test_stack_compose | 24 | 1.8 | 1.4 | 0.0 | 24 | 1.1 | 0.7 | +0.7 | +0.8 |
| test_engine_hardcoded | 23 | 7.3 | 0.9 | 0.0 | 23 | 6.6 | 0.7 | +0.6 | +0.2 |
| test_sources_resolve | 71 | 16.3 | 2.8 | 8.5 | 71 | 15.8 | 10.3 | +0.5 | +1.0 |
| test_engine_tracing_guard | 22 | 0.8 | 0.7 | 0.0 | 22 | 0.4 | 0.3 | +0.4 | +0.4 |
| test_stack_readiness | 19 | 15.2 | 0.5 | 5.0 | 19 | 14.8 | 5.0 | +0.3 | +0.4 |
| test_gate_least_privilege | 14 | 0.8 | 0.4 | 0.2 | 14 | 0.5 | 0.3 | +0.3 | +0.2 |
| test_engine_telemetry | 14 | 0.5 | 0.4 | 0.0 | 14 | 0.2 | 0.2 | +0.2 | +0.2 |
| test_gates_docker_cli | 13 | 0.2 | 0.1 | 0.0 | 13 | 0.1 | 0.0 | +0.1 | +0.1 |
| test_harness_followups | 41 | 47.1 | 0.2 | 43.8 | 41 | 47.0 | 43.8 | +0.1 | +0.2 |
| test_stack_worker | 10 | 0.2 | 0.2 | 0.0 | 10 | 0.1 | 0.1 | +0.1 | +0.1 |
| test_stack_model_skip | 8 | 0.5 | 0.4 | 0.0 | 8 | 0.5 | 0.3 | +0.1 | +0.1 |
| test_notice_ke_app | 6 | 0.2 | 0.1 | 0.0 | 6 | 0.1 | 0.1 | +0.1 | +0.0 |
| test_stack_ready_compose | 7 | 0.1 | 0.1 | 0.0 | 7 | 0.1 | 0.1 | +0.1 | +0.1 |
| test_engine_config | 20 | 0.4 | 0.3 | 0.0 | 20 | 0.4 | 0.2 | +0.0 | +0.1 |
| test_engine_egress | 8 | 0.3 | 0.2 | 0.0 | 8 | 0.2 | 0.2 | +0.0 | +0.0 |
| test_stack_bind_address | 16 | 2.0 | 0.3 | 1.1 | 16 | 2.0 | 1.5 | +0.0 | +0.0 |
| test_stack_carry_ins | 4 | 0.0 | 0.0 | 0.0 | 4 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_stack_ready_docs | 5 | 0.0 | 0.0 | 0.0 | 5 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_tracing | 8 | 0.0 | 0.0 | 0.0 | 8 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_engine_llm | 2 | 0.0 | 0.0 | 0.0 | 2 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_log_event | 4 | 0.0 | 0.0 | 0.0 | 4 | 0.0 | 0.0 | +0.0 | +0.0 |
| test_sentinel | 1 | 0.0 | 0.0 | 0.0 | 1 | 0.0 | 0.0 | -0.0 | -0.0 |
| test_engine_notices | 7 | 0.0 | 0.0 | 0.0 | 7 | 0.0 | 0.0 | -0.0 | +0.0 |
| test_engine_quality | 5 | 0.0 | 0.0 | 0.0 | 5 | 0.0 | 0.0 | -0.0 | +0.0 |
| test_engine_deploy_files | 2 | 0.0 | 0.0 | 0.0 | 2 | 0.1 | 0.0 | -0.0 | +0.0 |
| test_stack_model_keys | 12 | 1.0 | 0.1 | 0.8 | 12 | 1.1 | 0.9 | -0.0 | -0.0 |
| test_resource_probe | 9 | 0.9 | 0.1 | 0.6 | 9 | 0.9 | 0.7 | -0.0 | -0.0 |
| test_sbom_classifier | 59 | 6.2 | 5.0 | 0.0 | 59 | 6.3 | 5.0 | -0.1 | +0.0 |
| test_harness_port | 20 | 0.2 | 0.0 | 0.0 | 20 | 0.3 | 0.0 | -0.1 | -0.0 |
| test_sbom_generator | 4 | 12.1 | 1.1 | 5.7 | 4 | 12.4 | 6.7 | -0.2 | +0.1 |
| test_psycopg_c | 12 | 22.9 | 0.3 | 21.7 | 12 | 23.2 | 22.1 | -0.3 | -0.1 |
| test_neo4j_image | 21 | 23.4 | 1.0 | 20.5 | 21 | 23.7 | 21.6 | -0.3 | -0.1 |
| test_sbom_bundle | 14 | 33.2 | 1.9 | 29.2 | 14 | 33.6 | 31.2 | -0.4 | -0.2 |
| test_offline_netprobe | 19 | 27.3 | 0.1 | 25.9 | 19 | 27.7 | 26.4 | -0.4 | -0.3 |
| test_offline_check | 26 | 22.9 | 1.7 | 17.1 | 26 | 23.5 | 19.0 | -0.6 | -0.2 |
| test_ke_app_no_pip | 4 | 13.2 | 0.1 | 12.5 | 4 | 14.4 | 13.7 | -1.2 | -1.1 |
| test_image_scan | 33 | 15.8 | 0.8 | 6.2 | 33 | 17.2 | 7.6 | -1.4 | -0.7 |
| test_stack_scripts | 119 | 114.3 | 1.9 | 104.3 | 119 | 115.9 | 108.5 | -1.6 | -2.3 |
| test_offline_bundle | 165 | 271.9 | 12.3 | 242.9 | 165 | 281.3 | 265.3 | -9.4 | -10.1 |
| **total** | 1047 | 731.4 | 53.1 | 592.4 | 1047 | 737.3 | 649.6 | -5.9 | -4.1 |

## Per-test delta for tests present in both (head-cov minus pre-cov), top 20 by wall increase

| test | head wall s | pre wall s | delta s |
|---|---:|---:|---:|
| `test_offline_bundle.BundleNoticesTest.test_notices_accept_crlf_notice_md` | 2.33 | 0.21 | +2.12 |
| `test_offline_bundle.InstallPs1Test.test_install_claims_target_before_docker` | 2.25 | 1.82 | +0.43 |
| `test_offline_bundle.BundleScriptTest.test_bundle_json_names_every_image` | 2.42 | 2.09 | +0.33 |
| `test_sources_resolve.ReworkR1LockScriptRunTest.test_a_truncated_neo4j_list_is_not_pending` | 1.61 | 1.30 | +0.31 |
| `test_offline_bundle.BundleScriptTest.test_bundle_manifest_covers_every_file` | 2.37 | 2.08 | +0.29 |
| `test_offline_bundle.BundleScriptTest.test_bundle_writes_manifest_hash_beside_bundle` | 2.37 | 2.09 | +0.28 |
| `test_offline_bundle.BundleNoticesTest.test_notices_neo4j_has_source_url` | 2.44 | 2.17 | +0.27 |
| `test_stack_scripts.LaunchPs1ResolvedTest.test_launch_accepts_loopback_and_warns_for_dev` | 1.72 | 1.46 | +0.26 |
| `test_stack_scripts.TeardownPs1LeftoversTest.test_teardown_lists_with_the_project_compose_resolves` | 1.20 | 0.97 | +0.24 |
| `test_offline_bundle.InstallPs1Test.test_install_override_maps_every_service_to_as_tag` | 1.39 | 1.16 | +0.23 |
| `test_sbom_obligations.DriftOfflineCheckTest.test_offline_check_runs_image_side_drift_check` | 1.19 | 0.98 | +0.21 |
| `test_sbom_obligations.ReworkR1BundleTest.test_bundle_output_marks_unidentified_and_escapes_generator_text` | 2.38 | 2.18 | +0.20 |
| `test_stack_scripts.SmokeStoreStopStartTest.test_smoke_fails_naming_the_store_when_readiness_never_recovers` | 1.16 | 0.95 | +0.20 |
| `test_sbom_generator.SbomBundleTest.test_bundle_has_no_sbom_generator` | 2.40 | 2.20 | +0.19 |
| `test_sbom_obligations.SbomCarryU4Test.test_bundle_hands_host_paths_through_cygpath` | 2.42 | 2.24 | +0.18 |
| `test_engine_hardcoded.RepositoryScanTest.test_no_hardcoded_ports` | 2.71 | 2.53 | +0.18 |
| `test_stack_entrypoints.GatewayUpstreamCheckTest.test_gateway_refuses_upstream_not_on_allowlist_or_malformed` | 0.71 | 0.53 | +0.18 |
| `test_sbom_obligations.DriftOfflineCheckTest.test_offline_check_refuses_an_unpinned_base_reference` | 1.27 | 1.10 | +0.17 |
| `test_sbom_obligations.SbomCarryU4Test.test_bundle_sbom_work_dir_on_out_filesystem` | 2.27 | 2.11 | +0.17 |
| `test_offline_bundle.BundleScriptTest.test_bundle_reads_available_column_when_filesystem_has_spaces` | 2.51 | 2.34 | +0.16 |

New tests in head (not in pre): 65, wall 12.1 s, own+child CPU 9.6 s
Tests in pre gone/renamed in head: 2

## Per-class totals, head-cov, top 25 by wall

| class | tests | wall s | own CPU s | child CPU s | pre wall s |
|---|---:|---:|---:|---:|---:|
| test_offline_bundle.InstallPs1Test | 44 | 118.4 | 0.6 | 118.6 | 121.4 |
| test_offline_bundle.BundleScriptTest | 29 | 80.6 | 5.5 | 68.6 | 80.0 |
| test_stack_scripts.LintScriptTest | 15 | 53.3 | 0.9 | 56.0 | 53.6 |
| test_harness_followups.IntegrationRunsOnceTest | 23 | 46.9 | 0.2 | 43.6 | 46.8 |
| test_offline_bundle.BundleNoticesTest | 14 | 43.0 | 3.4 | 36.3 | 40.8 |
| test_sbom_bundle.SbomBundleRunTest | 7 | 32.8 | 1.7 | 28.9 | 32.7 |
| test_offline_netprobe.SmokeCiOfflineTest | 8 | 26.9 | 0.1 | 25.7 | 26.8 |
| test_offline_bundle.InstallShTest | 47 | 26.5 | 0.6 | 18.4 | 26.6 |
| test_psycopg_c.SmokePsycopgTest | 5 | 22.7 | 0.1 | 21.6 | 22.6 |
| test_offline_check.OfflineCheckScriptTest | 16 | 22.3 | 1.5 | 16.7 | 22.2 |
| test_stack_scripts.LaunchPs1ResolvedTest | 12 | 19.6 | 0.2 | 16.8 | 18.9 |
| test_block_main_commit_hook.BlockMainCommitHookTest | 46 | 17.6 | 0.5 | 17.7 | 17.6 |
| test_neo4j_image.SmokeNoFleetPluginTest | 3 | 15.3 | 0.1 | 14.6 | 15.3 |
| test_stack_readiness.ReadinessCliTest | 4 | 14.2 | 0.0 | 4.8 | 14.7 |
| test_ke_app_no_pip.SmokeNoPipTest | 3 | 13.2 | 0.1 | 12.6 | 13.2 |
| test_image_scan.ScanScriptTest | 22 | 13.2 | 0.5 | 4.0 | 13.2 |
| test_stack_scripts.SmokeStoreStopStartTest | 9 | 12.9 | 0.1 | 12.2 | 13.1 |
| test_sbom_obligations.SbomCarryU4Test | 6 | 9.4 | 0.6 | 7.8 | 9.3 |
| test_sources_resolve.ReworkR1LockScriptRunTest | 7 | 8.1 | 0.7 | 6.2 | 8.2 |
| test_sources_resolve.ReworkR1U7dScriptTest | 5 | 8.0 | 0.5 | 6.6 | 0.0 |
| test_engine_hardcoded.RepositoryScanTest | 4 | 7.6 | 0.9 | 0.0 | 7.1 |
| test_sbom_generator.SbomBundleTest | 2 | 6.9 | 0.4 | 6.0 | 6.7 |
| test_sbom_obligations.DriftOfflineCheckTest | 5 | 6.8 | 1.0 | 4.8 | 6.9 |
| test_stack_scripts.VerifyHostHalfTest | 26 | 6.5 | 0.2 | 1.9 | 6.2 |
| test_stack_scripts.TeardownPs1LeftoversTest | 7 | 5.7 | 0.1 | 4.3 | 5.6 |
