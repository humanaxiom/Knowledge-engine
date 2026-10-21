# Documenter section (harness-followups, docs gate, N15c)
- Updated README.md (Verification guards), CLAUDE.md (Delivery rule: verify sentinel, init check, CI pins), AGENTS.md (Rules for All Agents: sentinel). Depth table and evidence contract untouched; no forbidden words in CLAUDE.md/AGENTS.md.
- Command: scripts/verify.sh fast -> PASS (Ran 97 tests, OK). Output: docs/evidence/harness-followups/documenter-verify.txt
- Sentinel test test_top_level_unit_suite_ran reports ok in that run.
