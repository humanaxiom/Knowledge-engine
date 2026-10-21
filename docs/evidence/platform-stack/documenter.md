## 2026-10-18 documenter: platform-stack-up docs gate
- Files: README.md (Running the stack, verify full description, Structure, Getting Started no longer says `docker compose up -d phoenix`), CLAUDE.md (new section "What verify.sh runs that CI cannot", after "What CI runs that verify.sh does not"; depth table and evidence contract untouched), docs/quickstart.md (URLs, model host).
- PS-2.13: section was absent, so added. Its test (`test_claude_md_lists_verify_only_checks`) and the model-calling integration tests are 2b and do not exist yet; the section states the rule only.
- Not claimed: readyz, worker behaviour, store stop/start (2b).
- Verify: `scripts/verify.sh fast` PASS; output in docs/evidence/platform-stack/documenter-verify.txt.
