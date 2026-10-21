## 2026-10-19 — analyst: PS-3.1/PS-3.2 aligned with the spikes amendment

- **Asked:** apply the orchestrator's "rulings on analyst reconcile + architect
  spikes amendment" to PS-3: `bundle.json` `services` field, no `--platform`,
  no containerd operator prerequisite, architect's `as` scheme, no-pull
  check by tag set; remove any PS-3 text still placing the scan or L-8 on
  this branch. Edit only `docs/requirements.md`.
- **Changed (`docs/requirements.md`):**
  - PS-3.1 *Platform*: linux/amd64 means the build host's images; `bundle.sh`
    never passes `--platform` (S1).
  - PS-3.1 *`bundle.json` entries*: four fields `file`/`ref`/`as`/`services`;
    every stack service in exactly one entry's `services`; reject on a missing
    field or a bad/empty `services`. Test names unchanged:
    `test_bundle_json_records_file_ref_as` now asserts all four fields;
    `test_install_rejects_bundle_json_missing_field` parametrised over four.
  - PS-3.1 new *`as` tag scheme*: `ke-<x>:bundle-<sha12>` /
    `ke-vendor/<name>:<digest12>`; `<name>` collision fails `bundle.sh`;
    installer never touches `:local`. Covered by the existing
    `test_bundle_json_records_file_ref_as` (no new name).
  - PS-3.1 *Store-independent install*: explicit "no image-store prerequisite
    for operators" (installer never checks/refuses by store; quickstart asks
    for no store setting).
  - PS-3.1 *Compose override*: service names come from `services`, not
    `compose config`.
  - PS-3.2 new *No pull happened*: set of `repository:tag` names in the inner
    daemon (dangling excluded) equals the `as` set; IDs never compared. New
    test `test_offline_check_fails_when_tag_set_differs_from_as_set` (fast,
    stubbed; extra/missing; control equal).
  - PS-2 carry-in table (2b section) L-8 row: appended "since moved to
    `platform-supply-chain` (PS-3.7)". No other PS-3 text places the scan or
    L-8 here (PS-3.6/3.7 already marked moved; split note says no scan stage).
- **New test name for the tester:** `test_offline_check_fails_when_tag_set_differs_from_as_set`.
- **Open / for orchestrator:** (1) the pinned Docker CLI hash (architect §2.6
  test 8) has no PS-3 criterion; not added since not in the ask — confirm
  whether it needs one. (2) the containerd-store assertion on the CI `dind`
  (PS-3.2 *Inner daemon*) is kept; it is a property of the check's daemon,
  not an operator prerequisite.
- **Evidence:** `docs/evidence/platform-offline/analyst-reconcile-2-verify-fast.txt`.
