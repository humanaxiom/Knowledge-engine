## documenter (2026-10-18)
- Asked: update README.md only for the Claude Code port (CHANGELOG and handoff untouched).
- Changed README.md: Getting Started (Claude Code primary, Copilot still works; step 5 says gate scripts run only via verify.sh), new Verification section (verify.sh fast|full, Docker, Git Bash, gates image, no network, CI same command), Structure (CLAUDE.md, .claude/agents, .claude/settings.json, docker/gates.Dockerfile, .gitattributes, verify.sh, compose gates service), one-sentence hook guard-rail note citing ADR-KE-001 and branch protection.
- Verification: `scripts/verify.sh fast` -> PASS, 62 tests OK. Output: docs/evidence/harness-claude-code/documenter-verify.txt
- Nothing red to green (docs only).
