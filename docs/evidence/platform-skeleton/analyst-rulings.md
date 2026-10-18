# platform-skeleton: analyst, rulings folded in (2026-10-18)

Written here, not in the handoff, because the architect is appending to
`docs/handoffs/platform-skeleton.md` concurrently. Orchestrator: copy or link
this section into the handoff when convenient.

- Asked: fold the orchestrator's rulings PS-Q1–PS-Q6, PS-Q8, PS-Q9, PS-Q11
  into the PS criteria; record PS-Q1–PS-Q11 in `docs/open-questions.md`; note
  the four-way split with outcome-metric lines. Do not change PS-0.1–PS-0.5
  wording except the runner name in PS-0.1.
- `docs/requirements.md` § "Item: platform-skeleton":
  - Intro: rulings and their source cited; PS-Q7/PS-Q10 open (Q19, Q20).
  - "Proposed split" replaced by "Split into four plan items (accepted)": order
    `harness-followups` → `platform-config` → `platform-stack` →
    `platform-offline`, own branch and handoff each, one outcome-metric line
    each; table kept. PS-Q9 ruling replaces the one-branch fallback sentence.
  - PS-0.1: only change is "Which image: PS-Q1." -> "The image is
    `ubuntu-24.04` (PS-Q1)." PS-0.2–PS-0.5 untouched.
  - PS-1.1 cites PS-Q8 confirmed. PS-1.2: harness default endpoint in scope,
    changed in PS-2.2 (PS-Q2).
  - PS-1.5: sub-bullets for PS-Q3 (local = loopback or compose service name;
    cases: loopback ok, service name ok, external refused) and PS-Q4 (HIDE
    default true everywhere; dev `false` warns; non-dev `false` refused).
  - PS-1.6 (PS-Q5): line + branch >= 80%, mypy --strict, every first-party
    package (`harness_telemetry` + engine), tests excluded; test asserts scope.
  - New PS-1.8 (PS-Q11): `requires-python = ">=3.12,<3.13"`, uv.lock
    regenerated; `test_python_pinned_to_312`.
  - PS-2.2 (PS-Q2): one Phoenix; `log_event` default equals the `.env.example`
    phoenix port (`test_harness_default_collector_matches_env_example`); docs
    stop naming 6006/4317 (`test_docs_name_current_phoenix_port`).
  - PS-2.5 (PS-Q6): model host own field, excluded from overall readiness;
    `test_readyz_ready_without_model_host`.
  - PS-2.7, PS-3.2 cite PS-Q7 open (Q19); PS-2.9 cites PS-Q10 open (Q20);
    PS-3.2 marks the "deployable offline" rule met (PS-Q9).
  - "Open questions for this item" now lists open (Q7, Q10) then ruled.
- `docs/open-questions.md`: new "platform-skeleton" section. Q19 = PS-Q7
  (architect, open), Q20 = PS-Q10 (human, open), Q21–Q29 = PS-Q1, Q2, Q3, Q4,
  Q5, Q6, Q8, Q9, Q11 with rulings.
- Flags for the orchestrator/architect (not decided here):
  - PS-1.2's `test_no_hardcoded_ports` vs the literal default in
    `harness_telemetry/tracing.py` (`DEFAULT_COLLECTOR`): the ruling keeps a
    default, so either that file is exempt or the default is derived; the
    criterion only requires it to equal `.env.example`'s phoenix port. Architect.
  - PS-Q5 lists packages; `scripts/*.py` (not a package) is read as out of
    scope. Confirm if wrong.
- Next: architect resolves PS-Q7 before `platform-stack`; human answers Q20.
