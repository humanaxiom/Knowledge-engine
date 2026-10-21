# model-roles: architect evidence (2026-10-20)

- Command: `COMPOSE_PROJECT_NAME=ke-arch-mr scripts/verify.sh fast`
- Full output: `docs/evidence/model-roles/architect-verify-fast.txt`
- Result: `Ran 685 tests`, `OK (skipped=8)`, `== verify fast: PASS ==` (exit 0).
- Change under test: docs only (`docs/architecture.md` §2.3 layout block,
  §2.4 *Model roles*, §2.6 *model-roles*, §9 intro and ADR-KE-014;
  `docs/requirements.md` MR table fallback cells and MR-2).
