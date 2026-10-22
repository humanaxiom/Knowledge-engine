# Monitored Harness

A GitHub template for running future projects through a role-based agent
team — analyst, architect, developer, tester, reviewer, security, documenter,
and marketer — coordinated by an orchestrator agent, under a strict
Plan → TDD → Review & Security → Smoke Test → CI → Commit workflow.

This is [`harness`](https://github.com/adamsalah13/harness) with observability
built in: every agent action is both logged to `docs/log.md` and traced to
[Arize Phoenix](https://github.com/Arize-ai/phoenix), and the pure-Python
agents you build with it emit OpenInference spans, so Phoenix renders each run
as a nested AGENT → RETRIEVER / LLM / TOOL tree.

See [AGENTS.md](AGENTS.md) for the full workflow and role/file conventions.

## Licence

The project is licensed under the MIT licence: see [LICENSE](LICENSE). Notices
for the third-party software the stack images carry are in
[NOTICE.md](NOTICE.md) (vendor images, with licence texts under `licenses/`).
An offline bundle ships `LICENSE`, `NOTICE.md`, `licenses/` and a generated
`THIRD_PARTY_NOTICES.md` (the packages inside the images, from that build) at
its root, all listed in the bundle's `MANIFEST.sha256`.

## Install paths

Two ways to get the stack running; both are written out step by step in
[docs/quickstart.md](docs/quickstart.md).

- **Code-first (primary).** Clone the repository, then `scripts/build.sh` and
  `scripts/launch.sh` (PowerShell: `scripts\build.ps1`, `scripts\launch.ps1`).
  Builds the images natively on the target, x86 or ARM, and needs the network
  at build time. Hosts: Linux (bash) and Windows (PowerShell).
- **Offline bundle (air-gap).** Build and bundle on a connected Linux host with
  `scripts/bundle.sh`, carry the bundle across, verify its manifest hash and
  run `install.sh` (Linux, macOS) or `install.ps1` (Windows) on the target. A
  bundle holds one architecture, `amd64` or `arm64`, so build one per target
  architecture.

Current limit: this release runs in dev mode only (`KE_ENV=dev`, loopback
binding). `KE_ENV=prod` is refused until the stack has authentication, which
arrives with `auth-audit`. Set real secrets in `.env` regardless.

## Getting Started

1. Use this repo as a GitHub template for a new project.
2. Install dependencies, create your `.env` and start Phoenix:

   ```bash
   uv sync
   cp .env.example .env           # .env is gitignored
   scripts/build.sh && scripts/launch.sh   # Phoenix UI at http://localhost:47101
   ```

   See [Running the stack](#running-the-stack). Phoenix is reached through the
   gateway, on loopback only (`127.0.0.1`); the host port is `KE_PHOENIX_PORT`
   in `.env` (47101 if unset). The OTLP/gRPC port is not published.

3. Open the repo in [Claude Code](https://claude.com/claude-code) (the
   primary runner). The session is the orchestrator
   ([CLAUDE.md](CLAUDE.md)) and delegates to the role subagents in
   `.claude/agents/`. GitHub Copilot in VS Code still works: pick
   **Orchestrator** from the agent picker (`.github/agents/`).
4. Describe the task. The orchestrator plans it, delegates to the right
   role agents on a plan-item branch, enforces the gates in
   [AGENTS.md](AGENTS.md) (including reviewer/security approval), and only
   commits locally once every gate passes. Follow progress per plan item in
   Phoenix's **Sessions** view.
5. Extend [scripts/test.sh](scripts/test.sh) and
   [scripts/smoke.sh](scripts/smoke.sh) with the real commands for this
   project's stack (they currently cover `harness_telemetry`). Do not run
   them directly; they run through `scripts/verify.sh` (below).
6. When you're ready to merge a plan-item branch, open a PR and paste in
   [.github/pull_request_template.md](.github/pull_request_template.md)'s
   checklist.

## Running the stack

Prerequisites: Git, and Docker Engine 28 or later with Compose 2.24 or later.
Linux (bash) and Windows (PowerShell) are supported for the code-first install;
macOS only through the offline bundle. A host that builds an offline bundle also
needs `jq` and at least 7 GiB free on the disk that holds the output directory
(`bundle.sh` refuses otherwise). See [docs/quickstart.md](docs/quickstart.md).

1. Copy `.env.example` to `.env` and set the secrets
   (`KE_STORES__POSTGRES__PASSWORD`, `KE_STORES__NEO4J__PASSWORD`). The
   placeholders are accepted only with `KE_ENV=dev`.
2. Build, launch, tear down:

   ```bash
   scripts/build.sh       # PowerShell: scripts\build.ps1
   scripts/launch.sh      # PowerShell: scripts\launch.ps1
   scripts/teardown.sh    # PowerShell: scripts\teardown.ps1
   scripts/teardown.sh --volumes   # also removes the data (PowerShell: -Volumes)
   ```

   `launch` creates `.env` from `.env.example` if it is missing and waits until
   every service is healthy.
3. The API is at http://localhost:47100 (`/healthz`, `/readyz`) and Phoenix at
   http://localhost:47101. Both go through the gateway, the only service that
   publishes ports, and are bound to loopback.

`teardown` removes the project's containers and networks (and volumes with
`--volumes`), then lists anything of the same project that is still there. If
something is left it prints each resource, exits non-zero and tells you to
remove it by hand; it never removes a leftover itself.

### Readiness

`GET http://localhost:47100/readyz` returns 200 when postgres, neo4j and valkey
all answer, and 503 otherwise. The body lists each check as
`{"ok": bool, "reason": ...}`; `reason` is null when ok, else one word:

| Reason | Meaning |
|---|---|
| `refused` | the connection was refused |
| `timeout` | no answer in time |
| `unreachable` | the host could not be reached |
| `auth_failed` | credentials were rejected |
| `egress_denied` | the egress allowlist refused the host (model host) |
| `not_configured` | not set up (model host only) |
| `error:<ExceptionClass>` | anything else, by exception class only |

Reasons never carry credentials, hosts or exception text. The model host is
reported as `model_host` with `"required": false`: it never makes `/readyz`
return 503, and it shows `not_configured` until `KE_MODEL_UPSTREAM` is set.

### Worker

The `worker` service consumes one RQ queue (`default`) on Valkey. Job data is
JSON, not pickle, and the worker runs only the functions listed in
`engine.jobs.__all__`; any other job is failed without being resolved or run.

Exposing the ports on the LAN by setting `KE_BIND_ADDRESS` to a non-loopback
IPv4 address is refused outside `KE_ENV=dev` (by the launch scripts, the
gateway and the engine) until the stack has authentication.

Model host: set `KE_MODEL_UPSTREAM` to `host:port` and add the host to
`KE_EGRESS_ALLOWLIST`. The gateway refuses an upstream that is not on the
allowlist. For this deployment, put these in `.env`:

```
KE_MODEL_UPSTREAM=aria-gb10-2:11434
KE_EGRESS_ALLOWLIST=aria-gb10-2
```

## Verification

`scripts/verify.sh` is the one verification command, locally, for agents, and
in CI (CI runs `./scripts/verify.sh full`):

```bash
scripts/verify.sh fast   # docs-only and pure-function changes
scripts/verify.sh full   # everything else, and always before a commit
```

It needs Docker (on Windows, run it from Git Bash). It builds the `gates`
image from `docker/gates.Dockerfile` and runs the gate scripts inside it.
The gate services have networking disabled: `gates` has no network, and
`gates-it` reaches only the throwaway stack, and the model host through
its gateway. `full` also builds and launches a throwaway stack under a
random project name with nothing published, runs lint, the unit tests, the
integration tests (in the isolated `gates-it` container) and the smoke test,
then tears the stack down, scans the `ke-app` image, and finally runs the
offline check. Several runs can go in parallel. See
[CLAUDE.md](CLAUDE.md) for which run a change needs.

The offline check (`scripts/offline_check.sh`) builds a
throwaway bundle for the local architecture and installs it from a client
container with no network, against a Docker-in-Docker daemon that holds only
the bundle's images. That daemon runs privileged, so a host or CI runner that
refuses privileged containers cannot run `full`; there is no way around it. It
also needs the 7 GiB of free disk that `bundle.sh` requires.

The scan (`scripts/scan.sh`) looks for known vulnerabilities in the
`ke-app` image. A one-shot `scan-db` container fetches the scanner's
database fresh on every run, and the scan itself runs with no network.
`scan-db` is not the only container with a route out: the smoke check's
network-control probe runs on the stack's `edge` network. The scan does not
see the native libraries vendored inside the psycopg-binary wheel
(`psycopg_binary.libs`); this is a documented residual (L-13), see
`docs/requirements.md` PSC-7. A fixed High or Critical finding fails the
run, and so does a database host that cannot be reached; there is no retry
and no skip. `full` therefore needs
outbound HTTPS to `grype.anchore.io` for the vulnerability database.

The model-calling checks in `full` run only when `KE_MODEL_UPSTREAM` and
`KE_EGRESS_ALLOWLIST` are both set and the host is reachable. Each is taken
from the caller's environment first, else from the repo-root `.env`; these are
the only two `KE_*` values `verify.sh` passes on (the rest of the run uses the
`.env.example` placeholders). Otherwise those checks skip with a named reason
(`not configured` or `model host unreachable`), as on GitHub runners.

`scripts/smoke.sh` is meant to be run through `verify.sh`. Run by hand against
a stack that is already up, it checks that stack, skips the postgres
stop/restart and never tears it down; it tears down only a stack it launched
itself.

`scripts/lint.sh` (part of `full`) refuses any symlink under `scripts/` and
`docker/`.

Guards that make a green run mean something:

- `verify.sh` fails unless the test run reports at least one test and includes
  the sentinel test in `tests/test_sentinel.py`. Keep that file top-level and
  leave its module, class and method names unchanged; renaming any of them
  turns every run red. A test enforces this.
- `scripts/test.sh` fails loudly if a test directory has test files but no
  `__init__.py` (its tests would otherwise be skipped silently).
  `tests/integration/` runs only in `full`.
- CI runs on `ubuntu-24.04`, with the checkout action pinned to a commit SHA
  and credentials not persisted.

## Tracing your own agents

```python
from harness_telemetry import (
    agent_span, llm_span, record_documents, record_token_usage,
    retriever_span, set_output, setup_tracing,
)

setup_tracing(project_name="my-agent")

with agent_span("Agent Reasoning Loop", input=question, session_id=conversation_id) as agent:
    with retriever_span("Graph Search", input={"query": CYPHER, "parameters": params}) as r:
        docs = search(params)
        record_documents(r, docs)            # [{"id", "content", "score"?, "metadata"?}]
    with llm_span("Synthesize Answer", input=prompt, model=model_name) as llm:
        answer, prompt_tokens, completion_tokens = generate(prompt)
        record_token_usage(llm, prompt_tokens, completion_tokens)
        set_output(llm, answer)
    set_output(agent, answer)
```

Run the stub example: `HARNESS_TRACING=console uv run python examples/custom_agent.py`
(prints spans) or without the variable to send them to Phoenix.

| Variable | Default | Purpose |
|---|---|---|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:47101` | Phoenix base URL (`/v1/traces` is appended) |
| `HARNESS_TRACING` | `otlp` | `otlp`, `console`, or `off` |
| `OPENINFERENCE_HIDE_INPUTS` / `_OUTPUTS` | unset | `true` redacts prompts, queries, documents, answers |

## Engine configuration

Copy `.env.example` to `.env` (gitignored) and edit it. Never ship `.env.example`
in an image.

- Settings are `KE_`-prefixed environment variables layered over
  `config/defaults.yaml`; `__` nests (`KE_STORES__POSTGRES__PORT`). Lists are
  comma-separated.
- Secrets (`KE_STORES__POSTGRES__PASSWORD`, `KE_STORES__NEO4J__PASSWORD`) have
  no defaults. The `changeme-...` placeholders in `.env.example` are refused
  outside `KE_ENV=dev`.
- Tracing is off by default in `config/defaults.yaml`. `.env.example` sets
  `HARNESS_TRACING=otlp` to send traces to the local Phoenix.
- The model host is set per deployment as `host:port` in `KE_MODEL_UPSTREAM`
  (this deployment: `aria-gb10-2:11434`, OpenAI-compatible). It must be on
  `KE_EGRESS_ALLOWLIST` (this deployment: `aria-gb10-2`).

The engine refuses to start when: auth is off outside dev; the trace collector
is not local; the hide-inputs/outputs flags are off outside dev; a secret is a
placeholder; a model host is not on the allowlist; or a model URL carries
credentials (`user:pass@`). The error names the setting, never its value.

## Structure

- `CLAUDE.md` — Claude Code entry point: the session is the orchestrator
- `.claude/agents/` — the eight role subagents for Claude Code
- `.claude/settings.json` — wires the commit hook (`PreToolUse` on Bash)
- `.github/agents/` — orchestrator + the eight role agents (Copilot)
- `.github/workflows/ci.yml` — CI entrypoint
- `.github/pull_request_template.md` — gate checklist for PR descriptions
- `harness_telemetry/` — OpenInference span helpers and the `log_event` CLI
- `examples/custom_agent.py` — traced pure-Python agent loop (stubbed services)
- `docker-compose.yml` — the stack (gateway, api, worker, postgres, neo4j,
  valkey, Phoenix) and the one-shot `gates` and `gates-it` services;
  `docker-compose.verify.yml` is the overlay `verify.sh` uses (nothing published)
- `docker/` — the gates, app and gateway images
- `scripts/{build,launch,teardown}.{sh,ps1}` — run the stack
- `.gitattributes` — forces LF line endings for shell scripts
- `scripts/verify.sh` — the single verification entrypoint (`fast|full`)
- `scripts/hooks/block-main-commit.sh` — `PreToolUse` hook for the branch
  policy (wired in `.claude/settings.json` and `developer.agent.md`). It is a
  guard rail, not a security boundary (see ADR-KE-001 in
  [docs/architecture.md](docs/architecture.md)). Branch protection (Q18) was
  skipped by decision: merges to `main` are a manual human action, and this
  hook is the only automated guard.
- `scripts/test.sh`, `scripts/smoke.sh` — gate scripts called by
  `verify.sh`; the smoke test exports real OTLP traces to a stub collector
- `docs/requirements.md`, `docs/architecture.md` — living plan artifacts
- `docs/log.md` — append-only observability log, written via `log_event`
- `docs/handoffs/<plan-item-slug>.md` — running handoff doc per plan item,
  used to pass context between stateless subagent invocations
- `docs/handoffs/archive/` — handoff docs for committed plan items
- `docs/evidence/<plan-item-slug>/` — raw command/test/CI output, referenced
  by path instead of pasted into handoff docs or logs
- `CHANGELOG.md` — user-facing change log

No one commits directly to `main` — every plan item lives on
`agent/<slug>` (or `feat|fix|chore/<slug>` for human-driven work); see
[AGENTS.md](AGENTS.md#branch-policy).

Handoff docs and logs stay terse and structured on purpose — see
[AGENTS.md](AGENTS.md#context-window-discipline) for the rules that keep
oral history detailed on disk without bloating any agent's context window.

Each role agent runs on a model tier suited to its job: `orchestrator`,
`analyst`, `architect`, `tester`, `reviewer`, and `security` use a larger
reasoning model for planning/design/judging; `developer`, `documenter`, and
`marketer` use a smaller, faster model for mechanical implementation and
copy work. Tune the `model:` frontmatter in each `.github/agents/*.agent.md`
file as the available model catalog changes.
