# Changelog

Maintained by the `marketer` agent. Follows a Keep a Changelog style.

## [Unreleased]

### 2026-10-19

**Added:**
- The `engine` package with typed configuration. Settings come from `KE_`
  environment variables over `config/defaults.yaml`. Secrets are read from the
  environment only.
- An egress allowlist guard on model calls. It fails closed before any socket
  opens.
- Startup refuses unsafe settings and names the setting, never its value.
- Startup and model calls are traced.
- Coverage of at least 80% and strict type-checking are gates in
  `scripts/verify.sh`.

**Changed:**
- Phoenix is published on port 47101, on loopback only (`127.0.0.1`). The port
  is set in `.env`.
- Python is pinned to 3.12.

**Security:**
- Traces are exported only to a verified local collector, and never via proxy
  settings.
- Placeholder secrets are refused outside dev.
- Credentials in model URLs are refused.
- `.env` is gitignored.

### 2026-10-18

**Added:**
- Claude Code support. `CLAUDE.md` makes the orchestrator, `.claude/agents/`
  holds the eight role subagents, and `scripts/verify.sh [fast|full]` is the
  single verification entry point. It re-runs inside a `gates` container with
  networking disabled. CI calls only `./scripts/verify.sh full`.

**Changed:**
- `AGENTS.md` names `scripts/verify.sh` as the only verification command.
- CI runs on `ubuntu-24.04`. `actions/checkout` is pinned by SHA
  (v5.1.0) and does not persist credentials.
- `scripts/verify.sh` fails unless at least one test ran and the top-level
  sentinel test reported ok.
- `scripts/test.sh` runs integration tests only in `full`, finds tests at any
  depth, and fails loudly on a test directory without `__init__.py`.

**Fixed:**
- Shell scripts are forced to LF (`.gitattributes`). CRLF checkouts on
  Windows broke them inside the gates container.
- Gates run offline (`UV_OFFLINE=1`). A stale uv cache previously sent
  `uv run` to PyPI, which fails without network.
- The integration suite ran twice.
- Unit tests could silently stop running.

**Security:**
- The commit hook (`scripts/hooks/block-main-commit.sh`) no longer prints
  `allow`. That output auto-approved every Bash call in Claude Code.
- The hook also denies pushes that name main/master, force pushes, and
  `--all`/`--mirror`, from any branch. It works without jq.
- The hook now handles carriage returns and backslash-newline continuations
  the way bash does. Command shapes that previously slipped through are denied.
- It is still a guard rail, not a boundary, and it has known bypasses
  (see ADR-KE-001). Branch protection is the real control. Enable it on the
  remote.
- Gate base images are pinned by digest. `actions/checkout` is pinned by SHA.

### Added
- Arize Phoenix observability: every agent action logged through
  `harness_telemetry.log_event` is also traced, grouped per plan item in
  Phoenix's Sessions view, with failed gates shown as errors.
- `harness_telemetry` helpers that tag spans with OpenInference kinds
  (AGENT, CHAIN, RETRIEVER, LLM, TOOL) so custom Python agents render as a
  nested trace tree, including retrieved documents and token usage.
- Input/output redaction via `OPENINFERENCE_HIDE_INPUTS`/`_OUTPUTS`.
- Local Phoenix via `docker compose up -d phoenix`.
- Real tests and an OTLP smoke test wired into `scripts/` and CI.

### Changed
- Reviewer and security gates now check tracing coverage and what traces export.
- CI runs with read-only permissions, cancels superseded runs, and uses `uv`.
