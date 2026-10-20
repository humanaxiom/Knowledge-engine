# Changelog

Maintained by the `marketer` agent. Follows a Keep a Changelog style.

## [Unreleased]

### 2026-10-19 (platform-offline)

**Added:**
- An offline install bundle for machines with no internet access.
  `scripts/bundle.sh` writes one bundle per architecture (amd64 or arm64). It
  builds against whatever Docker daemon it talks to, including a remote ARM
  host. Each bundle holds the stack images, the app files, both installers,
  a manifest and the licence notices.
- `scripts/install.sh` (Linux and macOS) and `scripts/install.ps1` (Windows)
  install a bundle without the network. Before any `docker` command runs, the
  installer checks the bundle's manifest. Compare its hash with the value
  `bundle.sh` writes alongside the bundle, or pass `--expect-manifest <sha256>`.
- Licence notices in every bundle: `THIRD_PARTY_NOTICES.md`, `NOTICE.md`, and
  the licence texts they cite.
- An offline check in CI. It runs a clean Docker-in-Docker with networking
  disabled, installs the bundle, launches the stack and smoke-tests it. It
  fails if any image is pulled or if outbound traffic gets through.

**Changed:**
- The project is MIT-licensed. See `LICENSE`.
- The install target's parent directory must be owned by the operator (or
  root). The installer refuses one owned by another user.
- Build host requirements: `bundle.sh` needs `jq` and at least 7 GiB free on
  its output disk. Docker Engine 28 or later is required, as before.
- The code-first install is still the primary path. See `docs/quickstart.md`
  for both paths.

**Security:**
- Test containers run with least privilege.
- The Docker CLI and compose plugin in the gates image are pinned by version.
- `.env` is created private (0600), whatever the caller's umask.
- The bundle installer does not run `docker` until the manifest passes, and
  it installs only the staged copy it has verified.
- Production mode is refused. Authentication is not built yet, so this
  release is not for production use.

### 2026-10-19 (platform-stack-ready)

**Added:**
- `/readyz` on the api, with a status for each dependency and a fixed set of
  reasons. The model host is reported but is not required for readiness.
- A worker on Valkey (RQ) that runs allowlisted jobs.
- A smoke test that stops and restarts postgres and checks that the stack
  recovers.
- Model-calling checks in `scripts/verify.sh full`. They run when
  `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` are set.
- Dependencies: psycopg (LGPL-3.0), neo4j, redis and rq.

**Changed:**
- Teardown reports any leftover containers and fails instead of exiting clean.
- Lint refuses symlinks under `scripts/` and `docker/`, and checks scripts
  whatever the case of their extension.

**Security:**
- Readiness never reports credentials or error text.
- The worker decodes jobs as JSON only and refuses any job outside the
  allowlist.
- `scripts/verify.sh` passes no `KE_*` variable from the caller except the two
  model keys.
- Postgres connections disable GSS encryption.

### 2026-10-19 (platform-stack-up)

**Added:**
- A launchable stack: gateway, api, worker, postgres, neo4j, valkey and
  phoenix.
- Build, launch and teardown scripts for Linux (bash) and Windows (PowerShell).
- `/healthz` on the api.
- Lint gates: shellcheck and PSScriptAnalyzer, run from `scripts/lint.sh`.
- `scripts/verify.sh full` runs a throwaway stack and the integration tests in
  an isolated container.

**Changed:**
- Only the gateway publishes ports, on loopback: 47100 for the API and 47101
  for Phoenix.
- Docker Engine 28 or later is required. The launch scripts refuse older
  engines.
- All images are pinned by digest.

**Security:**
- The internal network is isolated from the host and the internet. Tests
  reach only the model host, through the gateway.
- The gateway refuses a model upstream that is not on the egress allowlist,
  and refuses malformed port values.
- LAN exposure is refused outside dev until the auth audit.
- Tracing accepts only a provider the engine built.

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
