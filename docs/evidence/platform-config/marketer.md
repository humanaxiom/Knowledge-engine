# platform-config: marketer (changelog gate)

Date: 2026-10-19. Role: marketer. Scope: `CHANGELOG.md` only.

## Gate check before drafting
- TDD: tester rework 3, 199 tests, all green (`tester-rework3.txt`).
- Smoke: `scripts/verify.sh full` pass in the same run (`tester-rework3.txt`).
- Review: reviewer last verdict was "changes requested" on E1/W3 after rework 2.
  Tester closed E1/W3 in rework 3 (`tester-rework3-mutation.txt`). No reviewer
  re-approval is recorded yet. The entry is drafted, but it should not be
  committed until reviewer re-approves rework 3.

## Facts checked against the tree
- Coverage gate: `pyproject.toml` `fail_under = 80`, branch coverage on.
- mypy: `strict = true` in `pyproject.toml`; `scripts/test.sh` runs `mypy`.
- Phoenix: `docker-compose.yml` publishes `127.0.0.1:${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}`.
- Python: `requires-python = ">=3.12,<3.13"`.
- Egress, startup refusals, traced startup and `.env` ignore are covered by ADR-KE-010 and the handoff rework sections.

## CHANGELOG entry added
- New sub-block `### 2026-10-19` under `## [Unreleased]`, above `### 2026-10-18`.
- Added, Changed and Security sections as requested. No test counts or measured
  coverage figures are included.

## Notes for the documenter (not edited here)
- `README.md` line 23 still says `UI at http://localhost:6006`. Under the
  shipped compose default the UI is at `http://127.0.0.1:47101`. The Phoenix port
  is a changed, user-visible fact, so the README needs updating.
- No README positioning change proposed. The engine is not yet a user-facing
  value-proposition change, and the documenter is editing README concurrently.

## Gate result
- changelog: pass (drafted). Commit blocked on reviewer re-approval of rework 3.
