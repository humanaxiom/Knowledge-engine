# analyst: rework round 1 recorded (2026-10-19)

Asked: record the rework-1 rulings and findings in `docs/requirements.md` and
`docs/open-questions.md` only (developer editing code concurrently; handoff
section kept here at the orchestrator's instruction).

Changed in `docs/requirements.md`:
- PS-2.5: F1 sub-bullet under *Unit form* — `KE_MODEL_UPSTREAM` unset/empty
  -> model host `not_configured`, no probe, still ready, although compose sets
  the base URL. `test_readyz_model_host_not_configured_without_upstream`
  (control `test_readyz_model_host_probed_when_upstream_set`); integration
  expectations of the tester's rework-1 note recorded. Vocabulary line for
  `not_configured` widened to match.
- PS-2.5: L-13 — postgres connects with `gssencmode="disable"`.
  `test_postgres_probe_disables_gss_encryption`,
  `test_every_postgres_connect_in_engine_disables_gss_encryption`.
- PS-2.6: M-1 engine side — `test_worker_uses_json_serializer`,
  `test_worker_refuses_a_job_outside_engine_jobs` (control
  `test_worker_runs_a_job_in_engine_jobs`), `test_worker_is_a_simple_worker`.
- PS-2.8: R-B3 — criterion stands; health check after the final ready.
  `test_smoke_checks_every_service_healthy_after_the_store_is_back`,
  `test_smoke_fails_when_a_service_is_unhealthy_after_the_restart`.
- PS-2.9: Q34 scope ruling (only PS launch/build/teardown, compose,
  Dockerfiles make the Windows run stale).
- PS-2.21: L-11 — `test_verify_full_takes_no_caller_ke_key_but_the_model_keys`;
  recorded run names `aria-gb10-2:11434`.
- PS-2.23: L-12 — `test_lint_covers_upper_case_ps1_and_psm1`,
  `test_lint_fails_on_a_symlinked_script`; lone-`[` nit
  `test_lint_ps1_lone_open_bracket_is_refused_before_pwsh`.
- auth-audit: carry-in 7, M-1 network side (Valkey own network +
  password/ACL), before any ingest exposure.
- PS-2 "Open questions for this item": Q38, Q39 and a rework-1 index.

Changed in `docs/open-questions.md`: Q38 (open, human) with the endpoint
ruling `aria-gb10-2:11434`; Q39 (open, assumed A39); Q34 scope ruling appended.

For the orchestrator:
- Q39: ingest-ledger precedes auth-audit in requirements and enqueues files;
  "before any ingest exposure" means carry-in 7 cannot wait for auth-audit
  in that order. A39 assumes it is the first unit of the first item feeding
  the queue.
- Unplaced: security L-13 also proposed an image scanner (trivy/grype over
  ke-app) in platform-offline; no ruling yet, not added.

Gate: `scripts/verify.sh fast` FAIL, 413 run, 1 failure:
`test_smoke_fails_when_a_service_is_unhealthy_after_the_restart` (R-B3 RED,
developer's in-progress `scripts/smoke.sh`, not docs). Output:
`docs/evidence/platform-stack-ready/analyst-rework1-verify-fast.txt`.
