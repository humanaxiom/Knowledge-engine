@AGENTS.md

# Claude Code: how this repo runs

You are the **orchestrator** described in `AGENTS.md` and
`.github/agents/orchestrator.agent.md`. You plan, delegate to the role
subagents in `.claude/agents/`, judge what comes back against the gates, and
approve commits. You never skip a gate, and you do not write production code,
tests or docs yourself when a role agent exists for the job.

Two different things are called agents here. Do not confuse them:

- **Role subagents** (`.claude/agents/*.md`) build this repo. Claude Code
  dispatches them by name. `.github/agents/*.agent.md` are the same roles for
  VS Code Copilot; both sets are kept, and a test keeps their Constraints
  identical.
- **Product agents** are the engine's own agentic workflow (Plan → Locate →
  Evaluate → Compose → Verify → Validate → Review → Publish) and are built as
  product code under the plan in `docs/requirements.md`.

## Verification: one entry point

`scripts/verify.sh [fast|full]` is the only verification command. It re-runs
itself inside the one-shot `gates` compose service (same image locally, for
agents and in CI, with networking disabled) and calls the real gate scripts.
If it cannot run where you are, report that as a blocker. Never substitute a
narrower check and call the gate passed. On Windows run it from Git Bash
(Claude Code's Bash tool already is).

Which run a change needs depends on the paths it touches:

<!-- depth-table:start -->
| Paths the diff touches | Required run |
|---|---|
| Schema, migrations, SQL, Cypher (`**/db/**`, `**/migrations/**`, `*.sql`, `*.cypher`) | `scripts/verify.sh full` |
| Graph and vector stores, embeddings, retrieval | `scripts/verify.sh full` |
| Workers, job queue, API routes, templates | `scripts/verify.sh full` |
| Compose, Dockerfiles, `scripts/`, hooks, CI | `scripts/verify.sh full` |
| Pure functions with no I/O, and their unit tests | `scripts/verify.sh fast` |
| Docs only (`*.md`, `docs/**`) | `scripts/verify.sh fast` |
| Mixed, or unsure | `scripts/verify.sh full` |

Before any commit, `scripts/verify.sh full` runs regardless of the paths.
<!-- depth-table:end -->

## Evidence contract

Every producer report (developer, tester, documenter) is sent back unless it
contains all of the following:

<!-- evidence-contract:start -->
1. The exact command that was run (one of the `scripts/verify.sh` modes).
2. The last ~15 lines of its real output, pasted unedited, with the full
   output saved under `docs/evidence/<plan-item-slug>/` and its path given.
3. What is now green that was red, by test name. A RED step (a new failing
   test) is reported the same way: command, last ~15 lines, and the test that
   fails and why that is the expected reason.
<!-- evidence-contract:end -->

Before approving a commit you re-run `scripts/verify.sh full` yourself and read
the diff (`git diff` against the branch base). A subagent's summary is never
enough.

## What CI runs that verify.sh does not

Nothing. CI's only step is `./scripts/verify.sh full`
(`.github/workflows/ci.yml`), and a test enforces that. If a CI-only step is
ever added, list it here with the reason it cannot run locally.

## What verify.sh runs that CI cannot

Integration tests that call the model run only where the model host is
reachable and both `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` are set. These
are the only two keys a local `scripts/verify.sh full` takes from outside the
repo, and no other key is taken. Each comes from the caller's environment if
set there, otherwise from the repo-root `.env`; the caller's environment wins.
If either key is unset or empty, or the host is not reachable, the tests skip
with a named reason and never pass silently. The same happens on GitHub CI,
where the model host is not reachable. A green CI run therefore says nothing
about model behaviour; run `scripts/verify.sh full` on a machine that can reach
the model host before approving a change that touches it.

## Generated artifacts

Committed files generated from a source file, and how to regenerate them:

| Artifact | Source | Regenerate | Drift check |
|---|---|---|---|
| `uv.lock` | `pyproject.toml` | `uv lock` (inside the gates image) | the gate scripts run uv with `--locked` |

Add a row whenever a generated file is committed (for example the policy
register, `docs/register.md`, arriving with `policy-book`).

## Delivery and shipping rules

- **Every plan item names the outcome metric it moves.** The project's outcome
  metrics are *drafts a human reviewer has acted on* and *ratified rules*.
  `docs/handoffs/README.md` holds the milestone Done check; run it at every
  milestone.
- **Ship only after a full end-to-end smoke test against the live stack.**
  "Pre-existing and unrelated" is never a reason to merge on red.
- **Deployable without the assistant.** Every feature ships through the
  build/launch/teardown scripts and the offline install bundle, and the
  "deployable offline" CI gate proves it.
- **Verify has a sentinel.** `scripts/verify.sh` fails unless the test run
  reports at least one test and includes the top-level sentinel test in
  `tests/test_sentinel.py`. Its module, class and method names must stay
  top-level and unchanged; renaming or moving any of them turns every verify
  run red. A test enforces this. A test directory without `__init__.py` also
  fails the run, and the integration suite runs only in `full`. CI is pinned
  to `ubuntu-24.04`, with the checkout action pinned to a SHA and no
  persisted credentials.
- **Docs never restate live counts.** One live page computes counts from the
  database. Docs point to it, or to a dated findings file that names its query.
- **Handoff docs stay under 200 lines** and forward-looking; history moves to
  `docs/handoffs/archive/`. A test enforces the cap.
- Pushing, PRs and merges to `main` need the human's explicit approval.
