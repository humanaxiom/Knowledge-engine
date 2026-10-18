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
2. Install dependencies and start Phoenix:

   ```bash
   uv sync
   docker compose up -d phoenix   # UI at http://localhost:6006
   ```

3. Open the agent picker in VS Code and select **Orchestrator**.
4. Describe the task. The orchestrator plans it, delegates to the right
   role agents on a plan-item branch, enforces the gates in
   [AGENTS.md](AGENTS.md) (including reviewer/security approval), and only
   commits locally once every gate passes. Follow progress per plan item in
   Phoenix's **Sessions** view.
5. Extend [scripts/test.sh](scripts/test.sh) and
   [scripts/smoke.sh](scripts/smoke.sh) with the real commands for this
   project's stack (they currently cover `harness_telemetry`).
6. When you're ready to merge a plan-item branch, open a PR and paste in
   [.github/pull_request_template.md](.github/pull_request_template.md)'s
   checklist.

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
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006` | Phoenix base URL (`/v1/traces` is appended) |
| `HARNESS_TRACING` | `otlp` | `otlp`, `console`, or `off` |
| `OPENINFERENCE_HIDE_INPUTS` / `_OUTPUTS` | unset | `true` redacts prompts, queries, documents, answers |

## Structure

- `.github/agents/` — orchestrator + the eight role agents
- `.github/workflows/ci.yml` — CI entrypoint
- `.github/pull_request_template.md` — gate checklist for PR descriptions
- `harness_telemetry/` — OpenInference span helpers and the `log_event` CLI
- `examples/custom_agent.py` — traced pure-Python agent loop (stubbed services)
- `docker-compose.yml` — local Phoenix
- `scripts/hooks/block-main-commit.sh` — `PreToolUse` hook enforcing the
  branch policy (wired into `developer.agent.md`)
- `scripts/test.sh`, `scripts/smoke.sh` — test/smoke entrypoints; the smoke
  test exports real OTLP traces to a stub collector
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
