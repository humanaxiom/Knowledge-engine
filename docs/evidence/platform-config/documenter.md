# documenter: platform-config docs gate
- Files: README.md (Phoenix 47101 on loopback via KE_PHOENIX_PORT, new "Engine configuration" section, env table default), AGENTS.md line 149 (port value only; N13).
- CLAUDE.md untouched (no stale port).
- R7 NOT fixed: it is the `.env.example` comment ("Local Phoenix is reachable from the host" while defaults.yaml collector is http://phoenix:6006, reachable only inside compose). Out of my allowed files; needs a reword by the owner of .env.example.
- N13 remainder: pyproject name `monitored-harness` not changed (not a doc file).
- Verify: `scripts/verify.sh fast` PASS; docs/evidence/platform-config/documenter-verify.txt.
