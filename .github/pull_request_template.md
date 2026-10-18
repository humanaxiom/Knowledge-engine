## Plan Item

<!-- link to the plan item / handoff doc, e.g. docs/handoffs/archive/<slug>.md -->

## Gate Checklist

- [ ] Plan: `docs/requirements.md` and `docs/architecture.md` updated for this item
- [ ] TDD: failing test written first, then minimal implementation, then refactor
- [ ] Reviewer subagent: `APPROVED`
- [ ] Security subagent: `PASS` (or explicit low/medium-only findings, justified below)
- [ ] Smoke test (`scripts/smoke.sh`): passing
- [ ] CI (`.github/workflows/ci.yml`): green
- [ ] Observability: new agent/model/retrieval/tool steps traced with `harness_telemetry` spans and asserted in tests
- [ ] Docs (`README.md`/`docs/`) and `CHANGELOG.md` updated
- [ ] Branch name matches `agent/<slug>` or `feat|fix|chore/<slug>` (never `main`)

## Notes / Justifications

<!-- any non-blocking security/review findings accepted as-is, and why -->
