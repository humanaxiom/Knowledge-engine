# Monitored Harness: Multi-Agent Development Workflow

This repository is a GitHub template that bootstraps every future project with a
role-based agent team, coordinated by an **orchestrator**, following a strict
**Plan → TDD → Review & Security → Smoke Test → CI → Commit** workflow.

## Roles

| Agent | Responsibility | Invocation | Model tier |
|---|---|---|---|
| `orchestrator` | Plans work, delegates to role agents, evaluates their output against gates, approves commits | Human-invocable | Reasoning |
| `analyst` | Clarifies requirements, writes acceptance criteria to `docs/requirements.md` | Subagent only | Reasoning |
| `architect` | Designs technical approach, records decisions in `docs/architecture.md` (ADR style) | Subagent only | Reasoning |
| `developer` | Implements code via TDD (red→green→refactor), stages and commits once gates pass | Subagent only | Trivial |
| `tester` | Writes/runs unit tests and the smoke test via `scripts/verify.sh`, judges pass/fail with evidence | Subagent only | Reasoning |
| `reviewer` | Reviews the diff for design conformance, code quality, and test adequacy; merge-blocking | Subagent only | Reasoning |
| `security` | Audits the diff for injection, secrets, unsafe dependencies, and other OWASP Top 10 risks; merge-blocking | Subagent only | Reasoning |
| `documenter` | Keeps `README.md` and in-repo docs in sync with shipped behavior | Subagent only | Trivial |
| `marketer` | Writes `CHANGELOG.md` entries and release/positioning copy | Subagent only | Trivial |

**Model tiers**: `Reasoning` roles plan, design, or judge gate outcomes and
run on a larger model. `Trivial` roles perform mechanical implementation/copy
work (coding, docs, changelog text) once the reasoning roles have decided
what to do, and run on a smaller/faster model. Tier-to-model mapping lives in
each agent's `model:` frontmatter — update it there, not here, when the
available model catalog changes.

## Workflow Gates

Work moves forward only when the current gate passes. No gate may be skipped.

1. **Plan** — `analyst` produces requirements/acceptance criteria; `architect` proposes
   a design. Orchestrator confirms both are unambiguous before implementation starts.
2. **TDD** — `tester` writes a failing test first; `developer` implements the minimal
   code to pass it, then refactors. Repeat per unit of work. No production code is
   written before a failing test exists for it.
3. **Review & Security** — `reviewer` and `security` audit the integrated diff in
   parallel. Both are merge-blocking: any unresolved finding sends the change back
   to `developer`, capped at the iteration limit below.
4. **Smoke Test** — `tester` runs `scripts/verify.sh full`, which includes the smoke test, against the integrated change.
   Must pass before merge/commit is approved.
5. **CI** — `.github/workflows/ci.yml` must be green (or updated to cover the new
   surface) before the orchestrator approves a commit.
6. **Commit** — `developer` stages and commits locally only after gates 1–5 pass,
   on a plan-item branch (never `main`), using a message that references the plan
   item. Pushing/PRs require explicit human approval.

## File Conventions

- `docs/requirements.md` — living acceptance criteria (analyst)
- `docs/architecture.md` — design decisions / ADRs (architect)
- `CHANGELOG.md` — user-facing change log (marketer)
- `scripts/verify.sh` — the single verification entry point; it runs the unit/integration and smoke gate scripts in `scripts/` inside the `gates` container
- `.github/workflows/ci.yml` — CI entrypoint, calls the scripts above
- `docs/log.md` — append-only observability log, written only through
  `harness_telemetry.log_event`, which also traces each entry to Phoenix
- `harness_telemetry/` — OpenInference tracing helpers and the `log_event` CLI
- `docker-compose.yml` — local Arize Phoenix (trace UI + OTLP collector)
- `docs/handoffs/<plan-item-slug>.md` — the running handoff/plan document for
  a single plan item, written and read by every role that touches that item
- `docs/handoffs/archive/<plan-item-slug>.md` — closed-out handoff docs,
  moved here once a plan item is committed so active docs stay small
- `docs/evidence/<plan-item-slug>/` — raw command output, full test/CI logs;
  referenced by path from handoff docs and `docs/log.md` instead of pasted inline
- `.github/pull_request_template.md` — gate checklist pasted into every PR description

## Branch Policy

- No one — human or agent — commits directly to `main`. Every plan item gets a
  branch: `agent/<plan-item-slug>` for agent-driven work, or `feat|fix|chore/<slug>`
  for human-driven work.
- `developer` creates/checks out the branch before writing any code, and a
  `PreToolUse` hook (`scripts/hooks/block-main-commit.sh`, wired in
  `developer.agent.md`) denies any commit/push attempted while on `main`.
- Merging `agent/*` branches to `main` is a human action (PR + review), same as
  pushing — never automated.

## Escalation & Anti-Gaming Rules

- **Iteration cap**: any fix-and-retest loop (TDD, review/security rework) is
  capped at 5 attempts. On the 6th failure, stop delegating and report the full
  failure history to the human instead of continuing to iterate.
- **Never game a gate.** Do not weaken, delete, or skip a failing test to force
  green; do not lower a coverage/quality threshold to pass; do not comment out
  or remove a gate from CI/scripts to unblock a commit. A red gate means the
  work isn't done, not that the gate is wrong.
- **Escalate with evidence, not a guess.** When capped out, point to the
  relevant `docs/evidence/<plan-item-slug>/` files and the handoff doc section
  where the disagreement/failure is recorded.

## Oral History: Logs & Handoffs

Each subagent invocation is stateless — it has no memory of prior turns — so
context must be passed through files, not assumed:

1. **Before acting**, read `docs/handoffs/<plan-item-slug>.md` for the plan
   item in scope. If it doesn't exist yet, the orchestrator/analyst creates it.
2. **After acting**, append a new dated section to that handoff doc: what you
   were asked to do, what you did, what you decided/found, evidence (command
   output, file paths, test results), and what the next role needs to know.
   Never delete or rewrite another role's prior section — only append.
3. **Always** log a one-line entry with
   `uv run python -m harness_telemetry.log_event --role <role> --plan-item <slug>
   --action "<what you did>" --gate "<gate: result>" [--evidence <path>]`.
   It appends `timestamp | role | plan item | action | gate result` to
   `docs/log.md` — the durable audit trail — and emits the same event to
   Phoenix (see [Observability](#observability-traces-in-arize-phoenix)).
4. The orchestrator reads both the handoff doc and `docs/log.md` before
   deciding the next delegation — never rely on chat history alone to know
   what already happened.
5. **Check prior art first.** Before writing new requirements or a new design,
   `analyst` and `architect` grep `docs/handoffs/archive/` and the existing
   `docs/requirements.md`/`docs/architecture.md` for related past decisions —
   don't re-litigate or contradict a decision that's already recorded.

## Observability: Traces in Arize Phoenix

`docs/log.md` tells you *what* happened; traces show *how*. Two layers, one
convention (OpenInference span kinds, which Phoenix renders as a trace tree):

1. **Workflow traces.** Every `log_event` call emits an `AGENT` span named
   `<role>: <action>`, with `session.id` = plan-item slug, the role as a tag,
   and gate/evidence as metadata. Phoenix's **Sessions** view therefore shows
   each plan item's full role-by-role history; failed gates (`fail`,
   `blocked`, `changes requested`) show as errors.
2. **Product traces.** Agent code built with this harness wraps each step in
   a `harness_telemetry` span so a run renders as a nested tree:
   `agent_span` (the loop; set `session_id`) → `retriever_span`
   (+ `record_documents`), `llm_span` (+ `record_token_usage`), `tool_span`,
   `chain_span`. Exceptions mark the span `ERROR` and are re-raised. See
   `examples/custom_agent.py`.

Rules:

- **Untraced agent steps are a review finding.** Any new agent loop, model
  call, retrieval, or tool call gets the matching span and a test asserting
  it (`tests/support.py` provides an in-memory exporter).
- **Record what was actually sent.** Retriever spans record the query
  template and its parameters separately; never interpolate user input into
  a query string.
- **Don't export what you shouldn't.** Never put secrets in span attributes.
  Set `OPENINFERENCE_HIDE_INPUTS=true` / `OPENINFERENCE_HIDE_OUTPUTS=true`
  wherever traces could carry personal data, or when exporting to a
  collector you don't control.
- **Tracing never blocks the work.** The log line is always written; if
  Phoenix is down the trace is dropped after a few seconds. Set
  `HARNESS_TRACING=off` to skip export, or `console` to print spans.

Configuration: `PHOENIX_COLLECTOR_ENDPOINT` (default `http://localhost:6006`),
`HARNESS_TRACING` (`otlp` | `console` | `off`), and the two `OPENINFERENCE_HIDE_*`
flags above.

## Context Window Discipline

Handoff docs and logs exist so agents don't need chat history — but if they
grow unbounded, reading them back in costs as much context as they saved.
Apply these rules so detail is preserved on disk without bloating any single
agent's context window:

- **Summarize, don't transcribe.** Handoff sections are terse and structured
  (bullets, fixed fields) — never a full prose transcript of what happened.
- **Evidence lives in files, not in the handoff doc.** Full test output, CI
  logs, or long command output goes in `docs/evidence/<plan-item-slug>/`;
  the handoff doc and `docs/log.md` reference it by path (and line range if
  relevant), never paste it inline.
- **Read narrow, not wide.** Read only the handoff sections/log lines
  relevant to the current plan item and the immediately preceding role's
  entry — not the entire project history — unless specifically diagnosing
  a regression.
- **`docs/log.md` stays one line per entry**, always. It's an index, not a
  report; details belong in the handoff doc or an evidence file it points to.
- **Archive on completion.** Once a plan item is committed, the orchestrator
  moves its handoff doc to `docs/handoffs/archive/` so the active
  `docs/handoffs/` directory only holds in-flight work.
- **Prefer diffs and paths over pasted file contents** in any report between
  agents — link to the file/line instead of quoting it in full.

## Rules for All Agents

- Do not skip a gate to save time; report a blocker to the orchestrator instead.
- Do not commit or push without the orchestrator's explicit go-ahead.
- Keep changes scoped to the current plan item.
- Do not act without first reading the plan item's handoff doc; do not finish
  without appending to it and to `docs/log.md`.
