# Analyst: requirement 9 amendment (review finding B3), 2026-10-18

- Asked: amend `docs/requirements.md` per orchestrator ruling on B3
  (`docs/evidence/harness-claude-code/review.md` B3).
- Did: edited harness-claude-code criterion 9 and policy-book criterion 2.
  §R-DR DR16 row unchanged: it already maps DR16 to `test_registry_enforced`,
  `ci/generated-artifacts-drift`, owned by policy-book, which matches the move.

## harness-claude-code, criterion 9

Before:
> 9. `CLAUDE.md` lists everything CI runs that `verify.sh` does not, and every
>    committed generated artifact with its regenerate command.
>    `[gate: ci/generated-artifacts-drift]` regenerates each one and fails on diff.

After:
> 9. `CLAUDE.md` lists everything CI runs that `verify.sh` does not, and every
>    committed generated artifact with its regenerate command. Today CI runs
>    nothing beyond `scripts/verify.sh full`, and the only generated artifact is
>    `uv.lock`; its drift check is that every gate script and the gates image run
>    uv with `--locked`, so a stale lock turns verify red.
>    `[unit: test_gate_scripts_use_locked]` The generic regenerate-and-diff gate
>    (`ci/generated-artifacts-drift`) belongs to policy-book criterion 2.

## policy-book, criterion 2

Before:
> 2. A generated human-readable register (`docs/register.md`) has a CI drift check.
>    `[gate: ci/generated-artifacts-drift]` (DR16)

After:
> 2. A generated human-readable register (`docs/register.md`) has a CI drift check.
>    This item introduces the generic drift gate, called by `scripts/verify.sh`: it
>    regenerates every non-lockfile generated artifact listed in `CLAUDE.md` and
>    fails on `git diff --exit-code`. `[gate: ci/generated-artifacts-drift]` (DR16)

## For next role

- `test_gate_scripts_use_locked` does not exist yet in `tests/` (grep, 2026-10-18).
  Tester owns it: assert every gate script (test.sh, smoke.sh, others that call uv)
  and the gates Dockerfile invoke uv with `--locked`.
- Open question: none. The scope of "gates image" (which Dockerfile(s) under
  `docker/`) is left to the tester to enumerate from the repo.
