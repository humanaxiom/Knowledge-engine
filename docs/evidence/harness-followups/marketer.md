# Marketer: harness-followups changelog

Date: 2026-10-18. Role: marketer. Plan item: harness-followups.

## Input
- Handoff: `docs/handoffs/harness-followups.md` (rework 5 GREEN, reviewer and security approved).
- ADR: `docs/architecture.md` § ADR-KE-001 (as built, sentinel contract).
- Log tail: `docs/log.md` (final reviewer and security entries pass).

## Output
- `CHANGELOG.md` `[Unreleased]` / `2026-10-18` block:
  - Changed: CI runner and checkout pin, verify.sh sentinel and Ran checks, test.sh discovery and integration scope.
  - Fixed: integration suite ran twice; unit tests could silently stop running.
  - Security: hook CR and backslash-newline handling; guard rail caveat with branch protection as the real control.
- No README positioning change proposed (no value-proposition change).
- No edits to code, tests, or the handoff doc.

## Gate
- Changelog gate: marketer section written, entries limited to shipped and tested items.
