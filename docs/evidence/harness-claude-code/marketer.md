# marketer: changelog entry (harness-claude-code)

Date: 2026-10-18. Branch: `agent/harness-claude-code`. Scope: `CHANGELOG.md` only.
README.md is being edited by the documenter and was not touched.

## Entry added
`CHANGELOG.md`, new `### 2026-10-18` block at the top of `## [Unreleased]`,
above the existing unreleased `### Added` and `### Changed` sections (left as is).

- **Added:** Claude Code support (`CLAUDE.md`, `.claude/agents/` with eight role
  subagents, `scripts/verify.sh [fast|full]` running in a no-network `gates`
  container; CI calls only `verify.sh full`).
- **Changed:** `AGENTS.md` names `scripts/verify.sh` as the only verification command.
- **Fixed:** shell scripts forced to LF via `.gitattributes`; gates run with
  `UV_OFFLINE=1`.
- **Security:** hook no longer prints `allow`; hook denies main/master pushes,
  force pushes and `--all`/`--mirror` from any branch, works without jq; base
  images pinned by digest; `actions/checkout` pinned by SHA; hook stated as a
  guard rail with branch protection recommended.

## Claims checked against the repo
- Eight files in `.claude/agents/`: yes.
- `network_mode: none` on the `gates` service in `docker-compose.yml`: yes.
- CI's only verify step is `./scripts/verify.sh full` (`.github/workflows/ci.yml`): yes.
- `.gitattributes` forces `*.sh` to `eol=lf`: yes.
- `UV_OFFLINE=1` set after `uv sync --locked` in `docker/gates.Dockerfile`: yes.
- `jq` installed in the gates image: yes.
- Digest-pinned `FROM` lines in `docker/gates.Dockerfile`: yes.
- `actions/checkout@11d5960a...` (SHA) in `ci.yml`: yes.
- Hook never prints `allow`; denies main/master push, force, `--all`/`--mirror`
  from any branch; jq optional: yes (`scripts/hooks/block-main-commit.sh`).
- Known bypasses and branch-protection note: ADR-KE-001 and the hook header.

## Judgment calls
- Dated block is a `###` heading rather than a new version, because the
  file has only `[Unreleased]`.
- Hook wording says "text-matching guard rail" and points to ADR-KE-001 for
  the bypasses, so the entry does not overstate the control.
- No figures added beyond the date and the eight-agent count, both in the repo.

## Log
Logged with `harness_telemetry.log_event --role marketer` (see the log for the
timestamped line; `HARNESS_TRACING=off`).
