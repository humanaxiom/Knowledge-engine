## 2026-10-19 — analyst: 2b names, vocabulary, S1/C1/W1 folded into criteria

- **Asked:** adopt the architect's *proposed* test names, the
  `unreachable`/`not_configured` vocabulary and `engine.jobs.noop`; fold in
  S1, C1/Q36, W1; resolve Q35/Q36; record the psycopg LGPL note. Touch only
  `docs/requirements.md` and `docs/open-questions.md`.
- **Names adopted (one name each; no existing name collided):**
  - `test_readyz_reason_vocabulary` — PS-2.5 *Status and reasons* > *Vocabulary* (fast).
  - `test_readyz_ready_excludes_model_host` — PS-2.5 *Model host* > *Unit form* (fast).
    Kept alongside the integration `test_readyz_ready_without_model_host`:
    stubbed rule vs real stores, not duplicates.
  - `test_store_probe_classifies_closed_port` — PS-2.5 *Bounded* > *Probe unit* (fast).
    The full-gate bound stays asserted in `test_readyz_fails_when_store_down`.
  - `test_compose_model_wiring` — PS-2.7 *Model host only through the gateway* >
    *Model wiring* (fast). Env wiring only; network membership stays with
    `test_gates_it_internal_only_and_no_socket`.
  - All four added to "2b gate depth" Fast.
  - Not adopted (not in the brief): `test_compose_worker_waits_for_valkey`,
    `EnvValueScriptTest`. The env_value.sh cases overlap PS-2.21's
    `test_verify_full_passes_model_upstream_keys` / `..._takes_no_other_env_key`;
    orchestrator decides whether they become their own criterion.
- **Vocabulary:** `timeout | refused | unreachable | auth_failed |
  egress_denied | not_configured | error:<Class>`; `not_configured` when the
  compose model `base_url` is null, with no probe called.
- **Job path:** PS-2.6 *Job path* = `engine.jobs.noop`, replacing
  `engine.worker.jobs.noop`. W1 fixture note in PS-2.6 and PS-2.21.
- **S1:** PS-2.8 *Tears down only what it launched*: no pre-existing project
  → launch, teardown on every exit path; pre-existing → checks run, never
  torn down. Static cases go into `test_smoke_stops_and_restarts_a_store`.
- **C1/Q36:** PS-3.4 in 2b: 20 min until 2b's first green CI run, then
  measured + 50% in a follow-up commit; the "7 now" is not applied.
- **Q35/Q36:** marked resolved in both files; PS-2.21 *Precedence* states A35.
- **psycopg LGPL:** "2b dependency licence note" after "2b size": accepted
  (open source, unmodified); security confirms at the `uv.lock` pin.
- **New open question Q37** (does not block RED): does the store stop/start
  run against a pre-existing project? Assumed: skipped with a printed notice,
  never reported passed. Tester: write the pre-existing case to that
  assumption, or wait for a ruling.
- **Note for tester/architect:** architect plan §6 puts the trap in smoke.sh
  unconditionally; S1 needs it conditional on "smoke launched it"
  (architect's alternative: `compose ps -q` empty before launch).
- **Evidence:** `docs/evidence/platform-stack-ready/analyst-names-verify-fast.txt`.
