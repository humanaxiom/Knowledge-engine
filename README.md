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

## Getting Started

1. Use this repo as a GitHub template for a new project.
2. Install dependencies, create your `.env` and start Phoenix:

   ```bash
   uv sync
   cp .env.example .env           # .env is gitignored
   docker compose up -d phoenix   # UI at http://localhost:47101
   ```

   Phoenix is published on loopback only (`127.0.0.1`); the host port is
   `KE_PHOENIX_PORT` in `.env` (47101 if unset). The OTLP/gRPC port is not
   published.

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

## Verification

`scripts/verify.sh` is the one verification command, locally, for agents, and
in CI (CI runs `./scripts/verify.sh full`):

```bash
scripts/verify.sh fast   # docs-only and pure-function changes
scripts/verify.sh full   # everything else, and always before a commit
```

It needs Docker (on Windows, run it from Git Bash). It builds the `gates`
image from `docker/gates.Dockerfile` and runs the gate scripts inside it with
networking disabled. See [CLAUDE.md](CLAUDE.md) for which run a change needs.

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
  (this deployment: `aria-gb10-2`, OpenAI-compatible; scheme and port are
  chosen in `.env`). It must be on `KE_EGRESS_ALLOWLIST`.

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
- `docker-compose.yml` — local Phoenix and the one-shot `gates` service
- `docker/gates.Dockerfile` — the image `verify.sh` runs the gates in
- `.gitattributes` — forces LF line endings for shell scripts
- `scripts/verify.sh` — the single verification entrypoint (`fast|full`)
- `scripts/hooks/block-main-commit.sh` — `PreToolUse` hook for the branch
  policy (wired in `.claude/settings.json` and `developer.agent.md`). It is a
  guard rail, not a security boundary (see ADR-KE-001 in
  [docs/architecture.md](docs/architecture.md)); branch protection on `main`
  is the real control.
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
