# platform-offline: analyst reconcile of PS-3 with the rulings (2026-10-19)

Asked: reconcile PS-3.1/3.2/3.4/3.5/3.8 and the split with the orchestrator's
rulings (handoff "rulings on analyst plan", "rulings on architect R1–R7",
"rulings from spikes (R2, R6)") and `spikes.md`; resolve Q40, Q41, Q43–Q46;
keep Q42 open. Files touched: `docs/requirements.md` § PS-3,
`docs/open-questions.md`. Not touched: `docs/architecture.md` (architect).

## docs/requirements.md § PS-3

- Reconcile note added after "Analyst review for `platform-offline`".
- PS-3.1 (R1, R2, R6, R7):
  - "and its PowerShell twin" removed; new bullet: bash only for bundling, no
    `bundle.ps1`; install has sh and ps1 (tamper tests stay a/b/c x sh/ps1).
  - "Verification images included" replaced by "Stack images only":
    `test_bundle_holds_stack_images_only` (new).
  - Store-independent install, new tests:
    `test_bundle_saves_one_tar_per_image_without_platform`,
    `test_bundle_json_records_file_ref_as`,
    `test_install_rejects_bundle_json_missing_field`,
    `test_bundle_fails_when_pinned_digest_unresolved`,
    `test_install_tags_loaded_image_as_bundle_name` (ID line / name line /
    no line / two lines x sh/ps1),
    `test_install_override_maps_every_service_to_as_tag`,
    `test_install_fails_when_service_has_no_bundle_entry`.
  - Free disk 10 GB: `test_bundle_fails_below_free_disk`.
  - A40 folded in: `test_bundle_json_marks_dirty_tree` (new); Windows bullet
    per A45 (installer + `launch.ps1`, bundle from a Linux host).
- PS-3.2 (S1, S3, R6): inner dind containerd store (asserted, else
  inconclusive), alias `docker`, client-cert subpath read-only, never `ca/`,
  inner networks `--internal`; 10 GB check; `df` before/after each stage.
  New tests: `test_offline_dind_uses_containerd_store`,
  `test_offline_dind_has_network_alias_docker`,
  `test_offline_client_mounts_only_client_certs_read_only`,
  `test_offline_inner_networks_are_internal`,
  `test_offline_check_fails_below_free_disk`,
  `test_offline_check_logs_disk_around_each_stage`. Quickstart: Linux build host.
- PS-3.3: "Target: Q46" -> "Target: A46".
- PS-3.4 (R5): 20 min when the offline stages land, then measured + 50%.
- PS-3.5 (R7, S2): now both `gates` and `gates-it` (exclusion of `gates`
  removed); `/tmp` is the only writable path; existing tests parametrised
  over both. New tests: `test_gate_services_run_as_uid_10001`,
  `test_gate_services_mount_repo_read_only`,
  `test_gate_services_tmp_is_exec_tmpfs`,
  `test_gates_image_venv_and_uv_cache_owned_by_gate_user`,
  `test_gates_uv_locked_catches_drift_as_non_root` (full),
  `test_gate_services_env_for_read_only_repo`,
  `test_coverage_data_file_is_under_tmp`,
  `test_coverage_file_env_is_never_set`, `test_uv_no_sync_is_never_set`.
  Git `safe.directory` on CI: inside the services if needed, never a
  writable checkout (no separate test; unmeasured).
- PS-3.6, PS-3.7: marked moved to `platform-supply-chain`; carry-in table
  updated.
- PS-3.8 (R7, R4, Q43): licence check moves into the bundle-time notices
  generator; `test_app_image_keeps_psycopg_licence` dropped. New tests:
  `test_notices_fail_when_package_licence_missing`,
  `test_notices_list_every_stack_image_with_licence`,
  `test_notices_neo4j_has_source_url`, `test_notices_mark_phoenix_as_exception`;
  security confirms Phoenix licence at the pinned digest (manual).
- Split note: this branch's TDD order PS-3.9 -> 3.1 -> 3.5 -> 3.2 -> 3.3 ->
  3.8 -> 3.4; no scan stage. Tags summary rewritten for this branch.
- Item open-question summary updated.

## docs/open-questions.md

- Q42 kept open, header says it moves to `platform-supply-chain`.
- Q40, Q41, Q43, Q44, Q45, Q46 moved to a new "Resolved 2026-10-19 for
  `platform-offline`" block (ruling first, original kept for the record).
- Q47 added (open, assumed, does not block RED): no gate installs on a
  classic-store daemon; A47 = stubbed installer tests + spike S1 suffice.

## Interpretations the orchestrator should check

1. R7 "psycopg licence test covered by the generator": read as the generator
   failing the bundle when any runtime package's licence file is missing
   from the `ke-app` image; the real-image check runs in full via
   `ci/deployable-offline`.
2. PS-3.5 "only writable path is `/tmp`": the earlier "single named writable
   path for outputs" is now the `/tmp` tmpfs (spike S2 "nothing else
   writable").
3. `as` tag scheme left to the architect; criteria only require no digest,
   no registry host, unique per entry.
