# platform-skeleton: analyst, F1–F6 rulings folded in (2026-10-18)

Written here, not in the handoff, at the orchestrator's request (the tester is
editing `tests/` concurrently). Orchestrator: copy or link into the handoff.

- **Asked:** apply the orchestrator's rulings on architect F1–F6, the bundle
  ruling, and the architect's analyst items to the PS criteria. PS-0.x unchanged.
  Touch only `docs/requirements.md` and `docs/open-questions.md`.
- **`docs/requirements.md`:**
  - Conventions: note under "Integration" that ADR-KE-009 proposes another
    mechanism, open as Q30; text of the convention and DR31 left as is. New
    "Smoke" convention (host-side `smoke.sh` check inside `verify.sh full`).
  - Item intro: PS-Q7 answered (ADR-KE-009); F2–F6 folded; F1 = Q30; new
    "Variable names (F2)" paragraph (`KE_ENV`, `KE_EGRESS_ALLOWLIST`,
    `KE_MODEL_UPSTREAM`, `KE_MODELS__<PASS>__BASE_URL`; no aliases; standard
    tool names kept).
  - PS-1.1: F2 sub-bullet `test_config_ignores_unprefixed_names`; F3 secrets
    exception sub-bullet `test_config_missing_secret_names_key`.
  - PS-1.2: `config/verify.env` added to allowed locations (F4).
  - PS-1.3, PS-1.5, PS-Q4 text: `ENV`/`EGRESS_ALLOWLIST` → `KE_` names.
  - New PS-1.9 placeholder secrets refused outside dev
    (`test_startup_refuses_placeholder_secrets`). Placeholder defined as "value
    equals the `.env.example` value for that key".
  - PS-2.1: `test_stack_services_healthy` re-tagged integration → smoke.
  - PS-2.5: store-down integration test made in process (closed port); new
    "Real store stop (smoke)" sub-bullet. PS-2.8 now lists both smoke checks.
  - PS-2.4, PS-2.5, PS-2.6, PS-2.7 marked **Blocked on Q30**. PS-2.7 records
    ADR-KE-009 as the proposed answer.
  - New PS-2.10 `test_only_gateway_on_edge_network`, PS-2.11
    `test_no_docker_socket_mounted`, PS-2.12
    `test_stack_services_have_no_bind_mounts` (all fast).
  - PS-3.1: wheels removed; `test_bundle_lists_every_compose_image` added;
    linux/amd64 only, Apple silicon under Q20.
  - PS-3.2: clean daemon per ADR-KE-009; F5 sub-bullet (every local `full`,
    blocker not skip, revisit at ~15 min).
  - New PS-3.4 CI timeout = measured + 50% (`test_ci_job_has_timeout` plus
    recorded measurement).
  - Open-questions block: Q30 added; PS-Q10 extended; PS-Q7 moved to
    "Answered by the architect"; F2–F6 summary under "Ruled".
- **`docs/open-questions.md`:** A7 uses `KE_MODEL_UPSTREAM`,
  `KE_MODELS__<PASS>__BASE_URL`, `KE_EGRESS_ALLOWLIST`; Q24 `KE_ENV`; new Q30
  (open, human); Q20 extended with Apple silicon; Q19 moved to "Answered by
  the architect"; F2–F6 ruling paragraph.
- **For the architect (not edited, outside my scope):**
  - §2.5 and ADR-KE-012 still list `wheels/` in the bundle; the ruling removes
    them.
  - §2.6 names `test_python_pinned_312`; the criterion is
    `test_python_pinned_to_312`.
  - §2.3 says standard names are "kept as aliases"; fine, but F2 means no
    aliases for `ENV`/`EGRESS_ALLOWLIST`/`MODEL_BASE_URL`; ADR-KE-010's
    "could be added as aliases if ruled so" is now ruled no.
- **For the tester:** new fast tests to write: PS-1.1 two, PS-1.9, PS-2.10–2.12,
  PS-3.1 `test_bundle_lists_every_compose_image`, PS-3.4. PS-2.4–2.7 tests wait
  on Q30.
- **Open:** Q30 (human), Q20 (human).
