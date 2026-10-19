# Requirements & Acceptance Criteria

Maintained by the `analyst` agent. One section per plan item.

Status: **draft plan, awaiting human approval** (plan item `engine-plan`,
2026-10-18). Nothing below is implemented yet. Open questions and the
assumptions taken in their absence are in
[docs/open-questions.md](open-questions.md); where an assumption is load-bearing
the criterion cites it as `(A<n>)`.

Conventions:

- **Given/When/Then** for behaviour; every criterion maps to at least one test
  or gate named in brackets, e.g. `[unit: test_ledger_one_row_per_file]`,
  `[integration]`, `[gate: ci/deployable-offline]`.
- Test names are the intended names. The tester may rename them, but the
  traceability table in §R-DR must be kept in sync in the same commit.
- "Integration" means tests run by a one-shot compose service (`gates-it`)
  against real PostgreSQL / Neo4j / Valkey running as compose services, with
  no Docker socket mounted anywhere. `gates-it` is attached only to the
  stack's internal network and has no internet access. The only host outside
  the stack that tests reach is the LLM on `aria-gb10-2`, and only through the
  stack gateway (the app's own path: model client → `gateway` →
  `KE_MODEL_UPSTREAM`). Integration tests that call a model run when that host
  is reachable through the gateway, and skip with a visible reason naming the
  host when it is not, as on GitHub runners. Unit tests (`gates`,
  `verify.sh fast`) keep `network_mode: none`. The app's egress allowlist
  (DR30) still applies inside every test, and the offline-bundle checks
  (`ci/offline`, `ci/deployable-offline`) still prove the deployed product
  runs offline. This is the human's ruling on Q30 (2026-10-18), as narrowed by
  the human's ruling F-A (2026-10-18); it amends DR31; see §R-DR.
  - *Q30 as first ruled, narrowed by F-A:* "The `gates-it` network has
    external access (it is not `internal`)."
  - *Original wording, superseded by Q30:* "'Integration' means real
    PostgreSQL / Neo4j / Valkey via testcontainers inside the `gates` compose
    service, with mocked model calls (design rule 31)."
- "Smoke" means a check run by `scripts/smoke.sh` on the host against the
  launched stack, inside `verify.sh full` (so also in CI).
- **Outcome metrics** for the whole project (shipping rule): *drafts a human
  reviewer has acted on* and *ratified rules*. Every plan item states which of
  the two it moves, or that it moves neither and why it is still next.

---

## Item: engine-plan (this document)

- Given the build prompt (v2, 2026-10-18), when the plan is delivered, then
  `docs/requirements.md`, `docs/architecture.md` and `docs/open-questions.md`
  exist, the architecture contains the port verdict table and the Mermaid
  diagrams named in §5.2 of the prompt, and no production code has been written.
- Outcome metric moved: neither. It is the precondition for every item that does.

---

## Item: harness-claude-code

Outcome metric moved: neither directly; it is the gate machinery every later item
relies on. Done when the proof below exists, not when the files exist.

1. Given `CLAUDE.md`, when a Claude Code session starts, then it imports
   `@AGENTS.md` and states the session is the **orchestrator**, which delegates
   and never skips a gate. `[unit: test_claude_md_imports_agents]`
2. Given `.github/agents/<role>.agent.md` for each of analyst, architect,
   developer, tester, reviewer, security, documenter, marketer, when the port runs,
   then `.claude/agents/<role>.md` exists for each, and the *Constraints*, file
   ownership and handoff/log duties are byte-identical to the Copilot source
   (modulo frontmatter and the removed verification commands of #5).
   `[unit: test_agent_port_preserves_constraints]`
3. Model tiers: analyst, architect, tester, reviewer, security → `opus`;
   developer, documenter, marketer → `sonnet` or `haiku`. Reviewer and security
   are never below `opus`. `[unit: test_agent_model_tiers]`
4. `.claude/settings.json` wires `scripts/hooks/block-main-commit.sh` as a
   `PreToolUse` hook on `Bash`. The hook is a **guard rail against agent
   mistakes, not a security boundary**: it is a simple, fail-safe text rule,
   not a shell parser, and any string-matching hook on a shell command can be
   bypassed. The real control is branch protection on the remote (Q18).
   Decision record: ADR-KE-001 "Decision: commit hook is a simple fail-safe
   text rule (2026-10-18)" in `docs/architecture.md`; round-4 ruling on
   security H2/L13/M3 (`docs/evidence/harness-claude-code/security-rework3.md`)
   and review B10/B11 (`docs/evidence/harness-claude-code/review-rework3.md`).
   The round-4 ruling replaces the round-3 segment/command-position parsing
   (earlier history: security M1/L9/L10, review B5-B9, in `security.md`,
   `security-rework2.md`, `review-rework1.md`, `review-rework2.md`).
   a. **Extraction.** The hook takes the command text from the payload with
      `jq` if `jq` is present and succeeds; otherwise the first
      `"command":"…"` value in the payload; otherwise the raw input. A JSON
      payload with no `command` field prints nothing.
   b. **Normalisation.** Before any rule is applied the extracted text is
      normalised: line continuations (backslash-newline) are joined, JSON `\n`
      escapes become newlines, all quote characters and backslashes are
      deleted, and the text is lower-cased.
   c. **On `main`/`master`** the hook denies when the normalised text contains
      the word `git` and any of the words `commit`, `push`, `merge`,
      `cherry-pick`, `am`, `rebase` or `revert`, anywhere in the text.
   d. **Off `main`/`master`** the hook denies any normalised line that contains
      `git`, later `push`, and later on that same line any of:
      - `main` or `master` as a word;
      - `--force` or `--force-with-lease`;
      - `--mirror` or `--all`;
      - a single-dash short-flag cluster containing `f` (e.g. `-f`, `-fu`);
      - a `+` refspec.
   e. **Otherwise** it prints nothing, so the normal permission flow decides. It
      never emits `allow` (which would auto-approve every Bash call).
      - **Accepted false positives (fail safe):** one-line commands that mention
        git, push and main (e.g. `git commit -m "fix push to main docs"` on a
        plan-item branch, or `echo "git push origin main"`).
      - **Accepted bypasses off `main`/`master`** (silent by design; Q18 branch
        protection is the real control): words hidden from the text (variables,
        `eval`, aliases, encodings), `gh`, `git update-ref`, and a push split
        across lines without a line continuation.
   f. **Performance.** The hook's cost is linear in the command's length and it
      uses no `awk`. Given a 1 MB command, when the hook runs in the gates image
      with `jq` present and with it absent, then it completes in under 3 s,
      whatever the command's shape: many short tokens, one long token, or one
      long heredoc line.
   `[unit: tests/test_block_main_commit_hook.py]` feeds Claude Code's real
   compact payload (`{"tool_input":{"command":"…"}}`, no spaces after `:`) and
   tests every rule in a-f both with `jq` on `PATH` and with it absent,
   including: a line continuation; an escaped quote; `ma\in`; `g''it` and
   uppercase `GIT` on `main`; `sh -c` and a bash heredoc on `main`;
   `>/dev/null git push origin main` and the backtick form off `main`; and the
   three 1 MB timing shapes of f.
5. `scripts/verify.sh` is the single verification entry point. It runs inside the
   `gates` compose service and only *calls* `scripts/test.sh`, `scripts/smoke.sh`
   and the CI step scripts; it never re-lists their commands.
   `[unit: test_verify_sh_has_no_inlined_commands]` greps it for `pytest`,
   `mypy`, `ruff`, `unittest`. Modes: `fast` (pure functions, docs) and `full`
   (integration + smoke).
6. No agent file and no `CLAUDE.md` contains a verification command other than
   `scripts/verify.sh [fast|full]`. `[unit: test_no_stray_verification_commands]`
7. `CLAUDE.md` and every producer agent (developer, tester, documenter) contain
   the same **path → required depth** table (schema, SQL, graph/vector stores,
   embeddings, workers, API routes → `full`; pure functions and docs → `fast`).
   `[unit: test_depth_table_identical_everywhere]`
8. Every producer agent's *Output Format* requires: the exact command, the last
   ~15 lines of real output, and what is now green that was red. The tester shows
   RED the same way. The orchestrator re-runs `scripts/verify.sh` and reads the
   diff before approving a commit. `[unit: test_evidence_contract_present]`
9. `CLAUDE.md` lists everything CI runs that `verify.sh` does not, and every
   committed generated artifact with its regenerate command. Today CI runs
   nothing beyond `scripts/verify.sh full`, and the only generated artifact is
   `uv.lock`; its drift check is that every gate script and the gates image run
   uv with `--locked`, so a stale lock turns verify red.
   `[unit: test_gate_scripts_use_locked]` The generic regenerate-and-diff gate
   (`ci/generated-artifacts-drift`) belongs to policy-book criterion 2.
10. The tester agent owns contradiction resolution: a change that contradicts an
    existing test resolves it in the same commit, citing the decision record.
11. Every role logs with `harness_telemetry.log_event` and appends to
    `docs/handoffs/<slug>.md`; evidence in `docs/evidence/<slug>/`.
12. `.github/agents/` is unchanged. An ADR records the port.
13. **Proof:** each of the eight subagents is dispatched once on a trivial task and
    the transcript is saved to `docs/evidence/harness-claude-code/dispatch-<role>.md`;
    every mode of `scripts/verify.sh` is run on a clean checkout and saved.
    The item is not done without these files.
14. `CLAUDE.md` carries the delivery and shipping rules of the prompt (outcome
    metric per item, ship only after live end-to-end smoke, deployable without
    the assistant, docs never restate live counts, handoffs ≤ ~200 lines).
    `docs/handoffs/README.md` gains the milestone "Done" check (metric now vs
    last milestone, why it did not move, external blocker with person and date).
    `[unit: test_handoff_line_cap]` fails if an active handoff exceeds 200 lines.

---

## Item: platform-skeleton

Outcome metric moved: neither; makes the product deployable, which is a
precondition for any human using it. It is still next because every later item
(ingest-ledger onward) needs the stores, configuration, egress guard and
integration gate it creates.

Analyst review 2026-10-18 (first review by the ported analyst). Criteria are
numbered `PS-<sub-item>.<n>` so they survive the split below. Open
questions specific to this item are `PS-Q<n>` at the end of the section. The
orchestrator ruled on PS-Q1–PS-Q6, PS-Q8, PS-Q9 and PS-Q11 on 2026-10-18
(`docs/handoffs/platform-skeleton.md`, "orchestrator: split accepted, rulings");
each criterion a ruling settles cites it. The architect answered PS-Q7 (Q19)
with ADR-KE-009, and the orchestrator ruled on the architect's findings F1–F6
the same day ("orchestrator: rulings on architect F1–F6"); F2–F6 are folded in
below. The human ruled on F1 (Q30), Q20 and Q7 on 2026-10-18
(`docs/handoffs/platform-skeleton.md`, "orchestrator: human rulings Q30, Q20,
Q7"), and the orchestrator replaced the placeholder-secret definition the same
day ("orchestrator: placeholder-secret ruling"). The human narrowed Q30 the
same day (ruling F-A: tests reach only the LLM on `aria-gb10-2`, through the
stack gateway, and get no internet access), and the orchestrator ruled on the
platform-config tester risks and on Q31/Q32 (`docs/handoffs/platform-config.md`,
"orchestrator: rulings on analyst Q31, Q32 and casing"); all are folded in below and
nothing in this item is blocked on them any more. Criteria that depend on an
open question cite it and must not be closed on a guessed value.

**Variable names (F2).** Environment variables are `KE_`-prefixed with `__`
for nesting (ADR-KE-010): `KE_ENV`, `KE_EGRESS_ALLOWLIST`,
`KE_MODEL_UPSTREAM`, `KE_MODELS__<PASS>__BASE_URL`. The unprefixed spellings
used earlier (`ENV`, `EGRESS_ALLOWLIST`, `MODEL_BASE_URL`) are not aliases.
Names that other tools already read keep their own names:
`PHOENIX_COLLECTOR_ENDPOINT`, `HARNESS_TRACING`, `OPENINFERENCE_HIDE_INPUTS`,
`OPENINFERENCE_HIDE_OUTPUTS`.

**Already delivered by harness-claude-code (do not rebuild; covered by
`tests/test_harness_port.py` and the hook tests):** the one-shot `gates` compose
service with `network_mode: none`; `scripts/verify.sh [fast|full]` as the only
entry point; CI's single step `./scripts/verify.sh full`
(`test_ci_calls_verify_only`); uv `--locked` everywhere and `UV_OFFLINE=1` in the
gates image (`test_gate_scripts_use_locked`); LF line endings for `*.sh`; the
`phoenix` compose service (this item changes only how its ports are set, PS-2.2).
A criterion below that restates one of these only extends it.

**Gate depth.** Every sub-item touches compose, Dockerfiles, `scripts/` or CI,
so every sub-item's gate is `scripts/verify.sh full`. The tag on each criterion
says where its named test runs: `fast` = in the unit suite (also part of
`full`); `full` = only in the integration, smoke or offline stage of `full`.

**Split into four plan items (accepted by the orchestrator 2026-10-18).**
platform-skeleton is no longer built as one item. It is split into four plan
items, each on its own `agent/<slug>` branch and with its own handoff doc,
built in the order below: `harness-followups` → `platform-config` →
`platform-stack` → `platform-offline`. `docs/handoffs/platform-skeleton.md`
stays the umbrella plan record. Each row ends with `verify.sh full` green and
the stack launchable by its own scripts. Each plan item's outcome-metric line:

- `harness-followups` — Outcome metric moved: neither; keeps CI green after the
  runner image change and closes carried security M4.
- `platform-config` — Outcome metric moved: neither; config, egress and startup
  safety that every service reads.
- `platform-stack` — Outcome metric moved: neither; the running stack and the
  real-store integration gate, a precondition for any reviewer to act.
- `platform-offline` — Outcome metric moved: neither; proves "deployable
  without the assistant", which must hold before any reviewer-facing feature
  ships.

| Order | Sub-item slug | Criteria | Outcome metric | Deployable as |
|---|---|---|---|---|
| 0 | `harness-followups` | PS-0.* | neither; keeps CI green after the runner image change and closes carried security M4 | harness only; no product runtime |
| 1 | `platform-config` | PS-1.* | neither; config, egress and startup safety every service reads | Python package exercised by the gates; no service yet |
| 2 | `platform-stack` | PS-2.* | neither; the running stack and the real-store integration gate | `scripts/launch` + live smoke on the developer's machine |
| 3 | `platform-offline` | PS-3.* | neither; proves "deployable without the assistant" | offline bundle installed with no network |

*Row 2 split (orchestrator ruling, 2026-10-19):* `platform-stack` is built as
two plan items, `platform-stack-up` (2a) then `platform-stack-ready` (2b),
each on its own `agent/<slug>` branch with its own handoff doc. The criteria
of each are listed under PS-2, "Split into 2a and 2b".

`platform-stack` may merge before `platform-offline` exists. The shipping rule
"deployable without the assistant" is met at the end of `platform-offline`, and
no reviewer-facing feature ships before then (PS-Q9, ruled 2026-10-18).

### PS-0 harness-followups (carry-in from `docs/handoffs/archive/harness-claude-code.md`)

- **PS-0.1 CI runner pinned.** Given `.github/workflows/ci.yml`, every job's
  `runs-on` names a versioned runner image, never `*-latest`.
  `[unit: test_ci_runner_pinned]` (fast). The image is `ubuntu-24.04` (PS-Q1).
- **PS-0.2 Checkout v5.** Every `uses:` in CI is pinned to a full 40-hex commit
  SHA with a version comment, and `actions/checkout` is a v5 release (the v4.4.0
  pin targets the deprecated Node 20 runtime). The SHA is read from the action's
  repository at implementation time and the source recorded in the handoff; it
  is not taken from this document. `[unit: test_ci_actions_pinned_to_sha]` (fast)
- **PS-0.3 Integration tests run once (review N3).** Given a `tests/integration/`
  package, when `scripts/test.sh full` runs, then each integration test executes
  exactly once; when `scripts/test.sh fast` runs, then no integration test
  executes. `[unit: test_integration_tests_run_once]` (fast; uses a fixture
  package, so it does not wait for PS-2).
- **PS-0.4 Hook CR fails safe (security M4).** Given the compact payload whose
  command contains a carriage return (`\r` JSON escape or a literal CR), when
  the hook runs on `main` with `jq` absent, then it denies exactly as it does
  for the same command without the CR; the same holds with `jq` present and off
  `main` for the push rules of harness-claude-code criterion 4d.
  `[unit: tests/test_block_main_commit_hook.py]` new cases (fast). Criterion 4
  of harness-claude-code is otherwise unchanged.
- **PS-0.5 Hook nits N16, N17.** A backslash-newline joins to nothing (N16:
  `pu\<newline>sh` is read as `push`); tests exist for "JSON payload without a
  `command` field prints nothing" and "only the first `command` value is used"
  (N17). `[unit: tests/test_block_main_commit_hook.py]` (fast)

Not carried into this item (stay deferred, no criterion here): review N5, N6,
N18, N19; security L2, L5, L7, L16, L17, L18.

### PS-1 platform-config

- **PS-1.1 Typed configuration.** Configuration is one typed settings object.
  Every key has a default in `config/defaults.yaml` and an environment override;
  given an env value of the wrong type, startup fails naming the key.
  `[unit: test_config_defaults_and_env_override]`,
  `[unit: test_config_rejects_bad_type]` (fast). The register entry for each
  key (DR16) is not required here: the register and `test_registry_enforced`
  arrive with policy-book, which then covers these keys (PS-Q8, confirmed
  2026-10-18).
  - *Variable names (F2).* Overrides are read only from the `KE_` names (and
    the standard tool names listed above). Given an unprefixed `ENV`,
    `EGRESS_ALLOWLIST` or `MODEL_BASE_URL` in the environment, it has no
    effect on the settings. `[unit: test_config_ignores_unprefixed_names]` (fast)
  - *Secrets exception (F3).* Secrets (passwords and other credentials) are
    the one accepted exception to "every key has a default": they have no
    default in `config/defaults.yaml` and come from the environment only.
    Given a required secret that is not set, startup fails with an error
    naming the key, never a value.
    `[unit: test_config_missing_secret_names_key]` (fast)
- **PS-1.2 No hardcoded hosts, ports or model names.** Given product source,
  compose files and scripts, no literal host port, host name or model name
  appears outside `config/defaults.yaml`, `.env.example`, `config/verify.env`
  (the verify-run overrides; accepted exemption, F4) and compose variable
  defaults. `[unit: test_no_hardcoded_ports]`, `[unit: test_no_hardcoded_hosts_or_models]`
  (fast). The model defaults are the prompt's (`qwen2.5:14b-instruct`, fallback
  `llama3.1:8b`, `nomic-embed-text` 768-dim, A7) and live only in config.
  The model host is `aria-gb10-2`, an OpenAI-compatible endpoint (human
  ruling Q7). It is reached only through `KE_MODEL_UPSTREAM` and the per-pass
  `KE_MODELS__<PASS>__BASE_URL` settings, and the name `aria-gb10-2` is a
  host name under this criterion: given product source, compose files or
  scripts, it appears only in the locations listed above.
  `[unit: test_no_hardcoded_hosts_or_models]` (fast) includes it.
  `harness_telemetry`'s default collector endpoint is in scope (PS-Q2): its
  drift test lands in platform-stack (PS-2.2).
  - *What is not a hardcoded host (orchestrator ruling, 2026-10-18).* A
    loopback address (`localhost`, `127.0.0.1`, `::1`) and the name of a
    compose service are not hardcoded hosts under this criterion;
    `test_no_hardcoded_hosts_or_models` does not flag them. Every other host
    name or address, including `aria-gb10-2`, is flagged outside the listed
    locations. The port rule above is unchanged by this.
  - *Phoenix ports land here (orchestrator ruling, 2026-10-18).* The compose
    part of PS-2.2 moves into this item: phoenix's published host port is the
    compose variable `KE_PHOENIX_PORT`, and `.env.example` sets
    `KE_PHOENIX_PORT=47101`. Given the compose files, no phoenix host port is
    a literal (today `6006`/`4317`). `[unit: test_no_hardcoded_ports]` (fast)
    covers it. `test_harness_default_collector_matches_env_example` and
    `test_docs_name_current_phoenix_port` stay in platform-stack.
  - *Model host per deployment (orchestrator ruling Q32, 2026-10-18).* The
    model host's scheme, port and URL are set per deployment in `.env`.
    Given `config/defaults.yaml`, it sets no model-host default (no
    `KE_MODEL_UPSTREAM` value and no model-host allowlist entry). Given
    `.env.example`, `KE_MODEL_UPSTREAM` is empty and a comment names
    `aria-gb10-2` as this deployment's host. No scheme or port is assumed.
- **PS-1.3 Egress guard at startup (DR30).** Given a configured inference host
  (any per-pass `KE_MODELS__<PASS>__BASE_URL`, or `KE_MODEL_UPSTREAM`) not on
  `KE_EGRESS_ALLOWLIST`, when the app starts, then startup fails with an error
  naming the host. An empty allowlist with a
  configured host also fails. `[unit: test_egress_guard_startup]` (fast)
- **PS-1.4 Egress guard at runtime (DR30).** Given a call whose target host is
  not on the allowlist, when the model client is invoked, then it raises before
  any socket is opened (asserted by a socket-level spy that records zero
  connection attempts). `[unit: test_egress_guard_runtime]` (fast). The guard is
  proven able to fail (DR38): `[unit: test_egress_guard_mutant_goes_red]` or a
  recorded mutation run in the evidence folder.
- **PS-1.5 Startup refuses unsafe settings (DR39, startup part).** Given each of
  the following, startup fails with a message naming the setting: auth disabled
  while `KE_ENV` is not `dev`; trace export to a collector that is not local;
  `OPENINFERENCE_HIDE_INPUTS` or `OPENINFERENCE_HIDE_OUTPUTS` not `true`
  outside `KE_ENV=dev`. Given `KE_ENV=dev` with auth off, startup succeeds and logs a
  warning. `[unit: test_startup_refuses_unsafe]` (fast), one case per setting.
  Auth itself is built in auth-audit; here only the setting and the refusal
  exist.
  - *Local collector (PS-Q3).* A collector endpoint is local when its host is a
    loopback address or the name of a compose service on the stack's internal
    network. Given any other host (including a public name or an external IP),
    startup fails naming the endpoint. Test cases cover an accepted loopback
    host, an accepted compose service name, and a refused external host.
  - *Hidden trace content (PS-Q4).* `OPENINFERENCE_HIDE_INPUTS` and
    `OPENINFERENCE_HIDE_OUTPUTS` default to `true` in every `KE_ENV`, including
    `dev`. Only `KE_ENV=dev` may set either to `false`; given that, startup
    succeeds and logs a warning naming the flag. Given `false` in any other
    `KE_ENV`, startup fails naming the flag. Test cases cover the default with no
    override, dev with `false` (warning), and non-dev with `false` (refused).
- **PS-1.6 Quality gates.** `scripts/test.sh` fails when combined line and
  branch coverage is below 80% or `mypy --strict` reports any error, and
  `verify.sh` only calls it (`test_verify_sh_has_no_inlined_commands` stays
  green). Scope (PS-Q5): every first-party package, today `harness_telemetry`
  and the new engine package; tests are excluded from both measurements. A
  first-party package added later is in scope without a new ruling.
  `[unit: test_test_sh_enforces_coverage_and_mypy]` (fast) asserts branch
  coverage is on, the threshold is 80, and both packages are measured and
  type-checked; plus a recorded RED run showing each threshold failing.
- **PS-1.7 Tracing.** The settings load and the startup check run inside a span
  per `AGENTS.md` (`chain_span`), asserted with the in-memory exporter.
  `[unit: test_startup_is_traced]` (fast)
- **PS-1.8 Python 3.12 pinned (PS-Q11).** `pyproject.toml` declares
  `requires-python = ">=3.12,<3.13"`, and `uv.lock` is regenerated from it
  (the existing `--locked` runs catch drift).
  `[unit: test_python_pinned_to_312]` (fast)
- **PS-1.9 Placeholder secrets refused outside dev (F3; orchestrator
  placeholder-secret ruling, 2026-10-18).**
  - *Placeholder form.* Given `.env.example`, every secret key's placeholder
    value is `changeme-<key in lowercase>`: the part after `changeme-` is
    lowercase and names that key (orchestrator casing ruling, 2026-10-18).
    `[unit: test_env_example_secret_placeholders_are_changeme]` (fast)
  - *Refusal.* Given `KE_ENV` other than `dev` and any secret whose value
    starts with `changeme`, matched case-insensitively (so `CHANGEME…` and
    `ChangeMe…` are refused too; orchestrator ruling, 2026-10-18), startup
    fails with an error naming the key, never the value. Given `KE_ENV=dev` and such values, startup succeeds. The check
    is by prefix and does not read `.env.example` at runtime. Test cases cover
    one refused non-dev case per secret key, a refused non-dev value that
    starts with `changeme` but differs from the `.env.example` placeholder,
    and the accepted dev case.
    `[unit: test_startup_refuses_placeholder_secrets]` (fast)
  - *Not shipped.* `.env.example` is not copied into any product image.
    `[unit: test_env_example_not_in_app_image]` (fast). The app image arrives
    in `platform-stack`, so this test is written and goes green there.
  - *Superseded definition, kept for the record:* "A placeholder secret is one
    whose value equals the value `.env.example` gives that key", with
    `.env.example` copied into the app image for the check.

### PS-2 platform-stack

- **PS-2.1 Services.** Given a fresh `.env` copied from `.env.example`, when
  the launch script runs, then api, worker, postgres, neo4j, valkey and phoenix
  are running and healthy, and `gates` stays a profile-only one-shot service.
  Engine versions follow `docs/architecture.md` §2 (PostgreSQL 16, Neo4j 5
  community, Valkey 8); every image is pinned by digest (architect picks the
  digest; not specified here). `[smoke: test_stack_services_healthy]` (full;
  re-tagged from integration, because only the host side can see container
  health: the launch script's wait on every healthcheck plus the probe),
  `[unit: test_compose_images_pinned_by_digest]` (fast)
- **PS-2.2 Ports from `.env` (A6; port ruling, umbrella 2026-10-19).** Every
  published host port, including phoenix's (today literal `6006`/`4317`), is a
  compose variable that `.env` overrides, and every default in `.env.example`
  lies in 47100–47199. No two defaults collide. `[unit: test_no_hardcoded_ports]`
  (fast, extends PS-1.2), `[unit: test_env_example_ports_in_range_and_unique]`
  (fast). Specific port numbers: architect (§2.4).
  - *Published-port form (port ruling).* Given every compose file, every
    published port is written `${KE_BIND_ADDRESS:-127.0.0.1}:${KE_<X>_PORT:-<default>}:<container port>`:
    the host address is never a literal and never omitted, and no host port
    uses the `:?` form (which breaks `verify.sh` and CI when no `.env`
    exists). Only `gateway` has a `ports:` entry (`docs/architecture.md`
    §2.4). `[unit: test_published_ports_use_bind_address]` (fast; name
    adopted from the architect by ruling R1, 2026-10-19; replaces the
    analyst's earlier `test_published_ports_use_bind_address_form`)
  - *No second default drifts.* Given every compose file, every
    `${VAR:-default}` default (ports included) equals the value
    `.env.example` sets for that variable, and every `KE_<X>_PORT` a compose
    file publishes is set in `.env.example`.
    `[unit: test_compose_defaults_match_env_example]` (fast; name adopted
    by R1, replaces `test_compose_port_defaults_match_env_example`;
    generalises platform-config's `test_compose_phoenix_defaults_match_config`).
  - *Resolves without `.env`.* Given a checkout with no `.env`, `docker
    compose config` succeeds and every published port binds to `127.0.0.1`.
    `[smoke: test_compose_resolves_without_env_file]` (full; needs the
    compose CLI, which the `gates` container does not have).
  - *Loopback by default.* `.env.example` either does not set
    `KE_BIND_ADDRESS` or sets it to `127.0.0.1`; it never sets a non-loopback
    value. `[unit: test_env_example_bind_address_is_loopback]` (fast)
  - *Delivered early (orchestrator ruling, 2026-10-18).* Phoenix's compose
    port (`KE_PHOENIX_PORT=47101`) lands in platform-config (see PS-1.2);
    the rest of this criterion stays here.
  - *One Phoenix (PS-Q2).* The harness and the product share the one phoenix
    service. `log_event` keeps reading `PHOENIX_COLLECTOR_ENDPOINT`; only its
    default changes, to the phoenix host port that `.env.example` sets.
    `[unit: test_harness_default_collector_matches_env_example]` (fast). Every
    doc that states the default endpoint or phoenix's ports (today `AGENTS.md`,
    `README.md`, the `harness_telemetry` docstring and the compose comment)
    states the new value, and none still names `6006` or `4317` as a host
    port. `[unit: test_docs_name_current_phoenix_port]` (fast)
- **PS-2.3 Restart policies (DR41).** Every long-running service declares a
  restart policy; `gates` does not. `[unit: test_compose_services_have_restart_policy]` (fast)
- **PS-2.4 `/healthz`.** Given the api process is up, `GET /healthz` returns 200
  without touching any dependency. `[integration: test_healthz]` (full; runs
  in `gates-it` under the Q30 integration convention).
- **PS-2.5 `/readyz`.** `GET /readyz` returns one entry per dependency
  (postgres, neo4j, valkey, model host), each with a status and, on failure, a
  reason; given one store unreachable, then that entry fails and the response
  is not ready. `[integration: test_readyz_reports_each_dependency]`,
  `[integration: test_readyz_fails_when_store_down]` (full; the store is made
  unreachable in process, by pointing that store's settings at a closed port,
  because the integration container cannot stop a container: it has no Docker
  socket, Q30).
  - *Real store stop (smoke).* Given the launched stack, when the smoke stops
    one real store container, then `/readyz` is not ready and names that
    store; when the store is started again, then `/readyz` is ready again.
    `[smoke: scripts/smoke.sh store stop/start]` (full; re-tagged from
    integration).
  - *Model-host probe guarded.* The model-host probe goes through the egress
    guard (PS-1.4); it is covered by
    `test_egress_allowlist_holds_with_network_access` (PS-2.7, full). The
    embedding-dimension check (DR13) joins `/readyz` in knowledge-plane, where
    the vector index exists; it is removed from this item.
  - *Model host (PS-Q6).* The model host is reported as its own field, but
    overall readiness excludes it, because ingest and review work without a
    model. Given all stores up and the model host unreachable, the
    model-host field reports failure with a reason and the response is still
    ready. Because `gates-it` can reach the model host through the gateway
    (Q30 as narrowed by F-A), the test makes the model host unreachable in process (its configured base URL
    points at a closed port), so the result does not depend on whether
    `aria-gb10-2` is up. Routes that compose drafts check the model host
    themselves rather than relying on `/readyz`.
    `[integration: test_readyz_ready_without_model_host]` (full)
  - *Model host reachable.* Given the configured model host reachable, the
    model-host field reports success. This is a model-calling integration
    test: it skips with a named reason when the host is unreachable (PS-2.7).
    `[integration: test_readyz_reports_reachable_model_host]` (full)
- **PS-2.6 Worker.** Given a no-op job enqueued on Valkey, the worker consumes
  it exactly once and records completion. `[integration: test_worker_consumes_noop_job]` (full;
  runs in `gates-it` under the Q30 integration convention).
- **PS-2.7 Real-store integration gate (DR31 as amended by Q30, narrowed by
  F-A).** Human rulings Q30 and F-A, 2026-10-18.
  - *Mechanism.* `verify.sh full` runs `tests/integration/` in the one-shot
    `gates-it` compose service against real PostgreSQL, Neo4j and Valkey
    compose services. `gates-it` mounts no Docker socket (PS-2.11) and is
    attached only to `internal: true` networks, so it has no internet access
    (human ruling F-A); `gates` keeps `network_mode: none` (`verify.sh fast`
    is unchanged).
    `[unit: test_gates_it_internal_only_and_no_socket]` (fast) asserts that
    every network `gates-it` joins is `internal: true`, that `gates-it` mounts
    no Docker socket, and that `gates` still has `network_mode: none`.
  - *No route out, at runtime (ruling R2, 2026-10-19).* The internal
    `backend` network is the boundary; there is no in-process socket-guard
    fixture. Given `gates-it` running, when a test opens a raw TCP connection
    to a TEST-NET-1 address (192.0.2.0/24), then the connection fails; and
    when it connects to `gateway`'s model listen port, then the connection is
    accepted (the control). `[integration: test_gates_it_has_no_route_out]`
    (full; name adopted by R1; the first integration test, since every later
    one assumes this topology).
  - *Model host only through the gateway (human ruling F-A).* The only host
    outside the stack that a test reaches is the model host (`aria-gb10-2`),
    and only through the stack gateway's model forward (model client →
    `gateway` → `KE_MODEL_UPSTREAM`). No test reaches any other outside host.
    Given the gateway's configuration, the only upstream outside the stack is
    the value of `KE_MODEL_UPSTREAM`; every other upstream is a compose
    service name. `[unit: test_gateway_only_external_upstream_is_model_upstream]`
    (fast). Given the compose files, `gates-it` and the `api`/`worker`
    services share an internal network with `gateway`, so the forward is
    reachable without a non-internal network (checked by
    `test_gates_it_internal_only_and_no_socket`, extended).
  - *Egress allowlist still holds (DR30).* Given model calls going through the
    gateway forward, when the app's model client is asked to reach a host not
    on `KE_EGRESS_ALLOWLIST`, then it raises before any connection is made.
    `[integration: test_egress_allowlist_holds_with_network_access]` (full;
    name kept: the gateway forward is the network access it holds against),
    proven able to fail (DR38).
  - *Model-calling tests run or skip by name.* Every integration test that
    calls a model is marked as such. Given the configured model host
    (`KE_MODEL_UPSTREAM`) reachable from `gates-it` through the gateway,
    those tests run. Given it
    unreachable, each is reported as skipped with a reason that names the
    host and says it is unreachable, and that reason appears in the
    `verify.sh full` output; it is never reported as passed. Integration tests
    that do not call a model never skip for this reason.
    `[unit: test_model_tests_skip_with_named_reason]` (fast; uses a fixture
    test and an unreachable host).
  - *Unit suite calls no model.* No test in the unit suite (`verify.sh fast`)
    opens a connection to a model host. `[unit: test_no_model_calls_in_unit_suite]`
    (fast; network guard).
  - *Deployed product still offline.* The offline-bundle checks are not
    changed by this ruling: PS-3.2 (`ci/deployable-offline`) and PS-3.3
    (`ci/offline`) still prove the deployed product runs without egress.
  - *Q30 wording narrowed by F-A, kept for the record:* "`gates-it` ... is
    attached to a network that is not `internal`, so it has external access",
    tested by `test_gates_it_has_network_access_and_no_socket`, which asserted
    at least one non-internal network.
  - *Superseded wording, kept for the record:* "PS-2.7 Real-store integration
    gate, no egress (DR31). `verify.sh full` runs `tests/integration/` against
    real PostgreSQL, Neo4j and Valkey, while any connection to a host outside
    the stack fails", proven then by an in-process socket-guard test. That
    test and its fixture are dropped (F-A, ruling R2); the runtime proof is
    `test_gates_it_has_no_route_out` above.
- **PS-2.8 Live-stack smoke.** `scripts/smoke.sh` launches the stack through
  the launch script, checks `/healthz` and `/readyz`, stops and starts one
  real store (PS-2.5), checks every service healthy (PS-2.1), then tears it
  down, in addition to the existing OTLP check. It runs in `verify.sh full`,
  so in CI. `[smoke: scripts/smoke.sh]` (full)
- **PS-2.9 Build, launch, teardown, quickstart.** Scripts exist for Windows
  PowerShell and for bash on Linux, with a fresh-machine quickstart in
  `README.md` or `docs/quickstart.md` that names only those scripts and the
  host prerequisites Git and Docker. Teardown leaves no running container of the
  project and keeps named volumes unless asked to remove them.
  `[unit: test_quickstart_names_existing_scripts]` (fast); lints run inside
  `verify.sh full`: `[gate: shellcheck]`, `[gate: PSScriptAnalyzer]` (full).
  - *Supported host OS (human ruling Q20, 2026-10-18).* Windows (PowerShell)
    and Linux only. macOS, including Apple silicon, is out of scope: no
    criterion requires a macOS script, run or proof, and the quickstart does
    not name macOS as supported.
  - *Proof per OS (orchestrator ruling Q31, 2026-10-18).* Linux is proven by
    CI (`verify.sh full`). Windows is proven by a recorded run of the
    PowerShell build, launch and teardown scripts on the human's Windows
    host, with its output saved under `docs/evidence/platform-stack/`
    `[gate: recorded Windows run]` (manual: neither fast nor full; it runs
    outside `verify.sh` and is checked by the reviewer). The evidence file
    shows, unedited: the Windows version, the commit the run used (equal to
    the branch head at review, or the diff since names no script, compose or
    Dockerfile change; orchestrator ruling Q34, 2026-10-19: otherwise the run
    is repeated before commit), the build script's output, the launch script
    reporting every PS-2.1 service healthy, the PowerShell launch script's
    refusal case (PS-2.14), and the teardown script followed by
    `docker compose ps` listing no running container of the project.
- **PS-2.10 Only the gateway has a route out.** Given the compose files, only
  `gateway` is attached to a network that is not `internal: true`; every other
  stack service is attached only to internal networks.
  `[unit: test_only_gateway_on_edge_network]` (fast). "Stack service" is as
  defined in PS-2.12 (no compose profile), so the profile-only `gates-it` is
  outside this criterion; it is internal-only anyway (PS-2.7, F-A).
- **PS-2.11 No Docker socket.** Given every compose file, no service mounts the
  Docker socket (`/var/run/docker.sock`, or the Windows named pipe
  `//./pipe/docker_engine`), whatever its profile.
  `[unit: test_no_docker_socket_mounted]` (fast)
- **PS-2.12 Stack services use named volumes only.** Given the compose files,
  no stack service (one without a compose profile) has a bind mount; only
  named volumes. One-shot gate services may bind-mount the checkout.
  `[unit: test_stack_services_have_no_bind_mounts]` (fast)
- **PS-2.13 CLAUDE.md lists what verify.sh runs that CI cannot (Q30).** Given
  `CLAUDE.md`, it has a section titled "What verify.sh runs that CI cannot"
  next to "What CI runs that verify.sh does not", and that section names the
  model-calling integration tests (PS-2.7) as running only where the model
  host is reachable, and skipping by name on GitHub runners.
  `[unit: test_claude_md_lists_verify_only_checks]` (fast)
- **PS-2.14 LAN exposure refused outside dev (port ruling, umbrella
  2026-10-19).** Exposing published ports beyond the host is a deliberate
  operator choice (`KE_BIND_ADDRESS` set to a non-loopback address in `.env`)
  and is refused until auth-audit lands. Q33 ruled by the orchestrator
  2026-10-19; design in `docs/architecture.md` §2.4 and the ADR-KE-011
  amendment.
  - *Definitions.* "Loopback" means any address in `127.0.0.0/8`, plus
    `::1` (Q33b). `KE_BIND_ADDRESS` takes an IPv4 literal only; IPv6 binding
    is out of scope for this item (architect, §2.4), so an IPv6 value such as
    `::` or `::1` is rejected in every `KE_ENV` as not IPv4, with an error
    naming `KE_BIND_ADDRESS`. Unset or empty means `127.0.0.1`, as in the
    compose `:-` default.
  - *Same rule in three places (Q33a, ruling R4).* Each of these applies the
    rule below: (1) engine startup in `api` and `worker` (refusal 6);
    (2) the gateway image's entrypoint check, which stops nginx before it
    publishes anything; (3) the build/launch scripts, bash and PowerShell,
    before `docker compose up`. The rule: given `KE_ENV` other than `dev` and
    a `KE_BIND_ADDRESS` that is not loopback, it refuses (startup fails, the
    entrypoint exits non-zero, the launch script exits non-zero without
    starting any container) with a message naming `KE_BIND_ADDRESS`; given
    `KE_ENV=dev` and a non-loopback IPv4 value, it logs or prints a warning
    naming `KE_BIND_ADDRESS` and continues (Q33c); given a loopback value,
    unset or empty, it continues in every `KE_ENV` with no warning. No
    message contains a secret setting value.
  - *Test cases (each check).* Unset, `127.0.0.1`, `127.0.0.2`, `0.0.0.0`
    and a private LAN address (e.g. `192.168.1.10`), each in `dev` and one
    non-dev `KE_ENV`; plus `::` and `::1`, rejected as not IPv4 in both.
    Expected: the loopback cases pass silently; `0.0.0.0` and the LAN
    address are refused outside `dev` and warn in `dev`.
  - `[unit: test_startup_refuses_non_loopback_bind_address]` (fast; engine,
    refusal 6; a non-IPv4 value is a `ConfigError` naming the variable).
  - `[unit: test_gateway_bind_check_refuses_non_loopback]` (fast; runs
    `docker/gateway/10-ke-bind-check.sh` under `sh` with the cases above and
    checks exit codes and that the message names `KE_BIND_ADDRESS`).
  - `[unit: test_launch_script_refuses_non_loopback_bind_address]` (fast;
    runs the bash launch script with the refused and the dev cases and
    asserts it exits non-zero, names `KE_BIND_ADDRESS`, and invokes no
    `docker compose up`; the dev case warns). The PowerShell launch script's
    refusal is shown by one refused non-dev case in the recorded Windows run
    (PS-2.9; manual).
  - *The checks see the value compose binds with.* Given the compose files,
    `api`, `worker` and `gateway` each receive `KE_BIND_ADDRESS` (same
    variable, same `127.0.0.1` default as the published ports) and `KE_ENV`.
    `[unit: test_compose_passes_bind_address_to_app]` (fast; covers
    `gateway` as well as the app services)
  - *Lifted only by auth-audit.* This criterion stays until auth-audit
    narrows it to "auth disabled" in every place above; no other item
    relaxes it.
  - *Out of scope.* IPv6 bind addresses; a hand-edited compose file that
    bypasses the variable (accepted residual, §2.4).
- **PS-2.15 test.sh header is current (carry-in, harness-followups).** Given
  `scripts/test.sh`, its header comment does not mention testcontainers and
  describes the `full` integration stage as `tests/integration/` run once in
  the `gates-it` compose service against the real stores (PS-2.7).
  `[unit: test_test_sh_header_matches_integration_mechanism]` (fast)
- **PS-2.16 AGENTS.md hook wording (carry-in, security L24).** Given
  `AGENTS.md`, the Branch Policy paragraph no longer says the hook "denies
  any commit/push attempted while on `main`"; it describes the hook as a guard
  rail that denies most such attempts, and names the on-`main` bypasses that
  ADR-KE-001 records (words hidden from the text: variables, `eval`, git
  aliases, encodings; and `gh`). No hook code changes.
  `[unit: test_agents_md_hook_wording_not_absolute]` (fast; asserts the
  absolute phrase is gone and each named bypass class appears).
- **PS-2.17 Installed-provider identity (carry-in, security M5; in 2a as the
  first unit, ruling R3, 2026-10-19; design: ADR-KE-010 M5 amendment, option
  c).** Only a tracer provider built by the engine's own constructor is
  accepted. Given a tracer provider installed before `startup()` that the
  engine did not build, when startup runs with otherwise passing settings,
  then it refuses naming `telemetry.tracing` and zero spans reach that
  provider's exporter, whatever its exporter. Cases, one subtest each, every
  provider built outside the engine: (a) local OTLP with `trust_env=False`
  and `session.proxies` set; (b) the same with a mounted rerouting transport
  adapter; (c) an `_endpoint` rewritten to localhost; (d) a plain in-memory
  exporter. `[unit: test_provider_not_built_by_engine_is_refused]` (fast;
  the first failing test of 2a). Control: given a provider built by the
  engine with an in-memory exporter, startup accepts it and that exporter
  receives the startup spans.
  `[unit: test_engine_built_provider_is_accepted]` (fast). With no provider
  installed (the proxy provider), startup is unchanged.
  - *Tests flip by ruling.* Tests that today pin a foreign provider as
    accepted (the console, in-memory and local-OTLP cases of
    `InstalledProviderTest`, and
    `test_local_otlp_that_ignores_proxy_env_is_accepted`) now expect
    "refused", and the controls (including
    `test_control_spans_do_reach_an_accepted_provider`) build their provider
    through the engine. This tightens those tests; it is authorised by
    ruling R3 and is not a weakened gate.
  - *Superseded, kept for the record:* the earlier shape-by-shape criterion
    named `test_installed_exporter_rerouting_is_refused` and waited on the
    architect's test-suite plan; that plan is now recorded (ADR-KE-010 M5
    amendment).
- **PS-2.18 Startup loads settings once; refusals logged (carry-in, review R3,
  R4).** Given one `startup()` call, the settings object is built exactly once
  (R3). Given an installed provider that startup refuses, a log record names
  `telemetry.tracing` and the reason, and contains no setting value (R4).
  `[unit: test_startup_loads_settings_once]`,
  `[unit: test_installed_provider_refusal_is_logged]` (fast)
- **PS-2.19 Hardcoded-value scanner covers the new surface (carry-in, review
  N1–N5).** This item adds compose files, gateway templates, PowerShell and
  bash scripts and store clients, so the PS-1.2 scanner is widened here:
  - *N1.* Host names match case-insensitively (`ARIA-GB10-2` is flagged like
    `aria-gb10-2`).
  - *N2.* Every tracked text file in the PS-1.2 scope is scanned whatever its
    suffix (including `*.conf`, `*.template`, `*.ps1`, `*.sql`, `*.cypher`,
    and compose files of any name); given a file whose type the scanner
    cannot classify, the test fails naming it rather than skipping it.
  - *N3.* A port number in a host/port tuple or under a `port` key in
    product source is flagged like any other literal port.
  - *N4.* The `DEFAULT_COLLECTOR` exemption covers only its assignment line;
    another line starting with the same name that holds a literal port is
    flagged.
  - *N5.* No test or product definition of loopback includes `0.0.0.0`
    (it is the LAN-exposure value PS-2.14 refuses).
  `[unit: test_no_hardcoded_hosts_or_models]`, `[unit: test_no_hardcoded_ports]`
  extended with one case per nit, `[unit: test_hardcoded_scan_covers_every_text_file]`
  (fast). Each new case is shown RED against the platform-config scanner.
- **PS-2.20 Project name (carry-in, review N13 remainder).** Given
  `pyproject.toml`, `[project].name` equals the OpenInference project name
  that `docs/architecture.md` §2.3 gives the product, and `uv.lock` is
  regenerated (the `--locked` runs catch drift).
  `[unit: test_pyproject_name_matches_project_name]` (fast)

**Also delivered in platform-stack (criteria live elsewhere):** PS-1.9
*Not shipped* (`test_env_example_not_in_app_image`, fast; the app image
arrives here) and the first PS-3.4 measurement (`test_ci_job_has_timeout`,
fast, plus the recorded CI duration).

**Carry-ins from platform-config (`docs/handoffs/archive/platform-config.md`,
close-out) — placement:**

| Finding | Here? | Where |
|---|---|---|
| security M5 | yes | PS-2.17, first unit of 2a (ruling R3; plan recorded in the ADR-KE-010 M5 amendment) |
| review R3, R4 | yes | PS-2.18 |
| review R5 (`ModelClient.complete` attributes, non-dict body, `base_url` error outside the span) | no | the first item that calls `complete()` in product code; this item only probes `/models` |
| review R6 (vacuous tests in `test_engine_startup.py`) | yes, no criterion | tester deletes them or points them at `test_engine_telemetry` while writing PS-2.18; reviewer checks |
| review R7 (`.env.example` Phoenix comment) | done | reworded at the platform-config docs gate (`docs/evidence/platform-config/r7-verify.txt`); nothing left |
| review N1–N5 | yes | PS-2.19 |
| review N11 (Dockerfile layer order) | yes, no criterion | applies to the new `docker/app.Dockerfile`; architect's call, reviewer judges |
| review N13 (pyproject name) | yes | PS-2.20; the other N13 docs drift was fixed at the platform-config docs gate |
| security L1c, L2, L3, L5, L7, I1 | no | stay deferred; not named for this item |

**Split into 2a and 2b (proposed by the analyst; accepted by the orchestrator
2026-10-19, with PS-2.17 moved into 2a by ruling R3).** PS-2.1–PS-2.20 is too
large for one fix-and-review loop under the 5-round cap, so it is built as two
plan items, in order, each on its own branch and handoff doc, each ending
`scripts/verify.sh full` green:

| Order | Slug | Criteria | Deployable as |
|---|---|---|---|
| 2a | `platform-stack-up` | PS-2.17 (M5, first unit), PS-2.1–PS-2.4, PS-2.7 *Mechanism* and *No route out, at runtime*, PS-2.9 (with the Windows run, including the PowerShell refusal case), PS-2.10–PS-2.12, PS-2.14–PS-2.16, PS-2.19, PS-2.20, PS-1.9 *Not shipped* | `scripts/launch` brings every service up healthy; smoke launches, checks `/healthz`, tears down |
| 2b | `platform-stack-ready` | PS-2.5, PS-2.6, the rest of PS-2.7, PS-2.8, PS-2.13, PS-2.18, the PS-3.4 measurement | the same stack with readiness, worker, model-gated integration tests and the full smoke |

Outcome-metric lines:

- `platform-stack-up` — Outcome metric moved: neither directly; the stack
  launches on loopback with every service healthy, behind the real-store
  `gates-it` gate, a precondition for any reviewer to act.
- `platform-stack-ready` — Outcome metric moved: neither directly; readiness,
  the worker, model-gated integration tests and the full live-stack smoke,
  a precondition for any reviewer to act.

PS-2.4 is in 2a because PS-2.1's health check needs `/healthz`, and it runs in
`gates-it`, so the `gates-it` mechanism (and its runtime no-route-out proof)
moves into 2a too. PS-2.17 is in 2a because the engine-built provider changes
`tests/support.py`, which every later test uses. PS-2.18 stays in 2b, and with
it the review R6 clean-up named in the placement table.

### PS-3 platform-offline

- **PS-3.1 Offline bundle.** `scripts/bundle.sh` (and its PowerShell twin)
  writes one bundle holding every image the stack runs, any vendored assets,
  and a checksum manifest; given a modified file, the install step rejects the
  bundle. `[unit: test_bundle_manifest_rejects_tamper]` (fast)
  - *No wheels (orchestrator ruling, 2026-10-18).* The bundle carries no
    Python wheels: the images carry their own dependencies. Rebuilding an
    image offline is out of scope.
  - *Every image listed.* Given the compose files, every image the stack
    services use is in the bundle. `[unit: test_bundle_lists_every_compose_image]` (fast)
  - *Platform.* The bundle is linux/amd64 only. macOS, including Apple
    silicon, is out of scope (human ruling Q20, 2026-10-18).
- **PS-3.2 Deployable offline.** Given the bundle and a Docker daemon that has
  none of the stack's images and no network egress, when the install and launch
  scripts run, then the stack starts and the PS-2.8 smoke passes without a pull
  or a package-index call. `[gate: ci/deployable-offline]` (full), called from
  `verify.sh full`. The clean daemon is the one ADR-KE-009 proposes (answers
  PS-Q7, Q19). When this criterion passes, the shipping rule "deployable
  without the assistant" is met (PS-Q9).
  - *Runs in every local `full` (F5).* The offline check runs in every
    `scripts/verify.sh full`, locally and in CI, so CI runs nothing that
    `verify.sh` does not. Given a local daemon that cannot run the check, the
    run fails and reports a blocker; it never skips the check and reports
    green. The orchestrator revisits this if a local `full` run takes more
    than about 15 minutes.
- **PS-3.3 Offline at runtime.** App containers have no route outside the
  stack's internal network except the allowlisted model host.
  `[gate: ci/offline]` (full) asserts an outbound call from api and worker to a
  non-allowlisted address fails.
- **PS-3.4 CI timeout from a measurement (F6).** The CI job's
  `timeout-minutes` equals the measured duration of a `verify.sh full` run in
  CI plus 50%, rounded up to a whole minute. The measured run (its CI log or
  the evidence file, and the duration read from it) is recorded in the
  sub-item's evidence folder. It is set in `platform-stack` and measured again
  in `platform-offline`, which makes `full` slower.
  `[unit: test_ci_job_has_timeout]` (fast) asserts the job declares
  `timeout-minutes`; the value is checked by the reviewer against the
  recorded measurement.

### Open questions for this item

Questions raised in the analyst review of 2026-10-18; rulings by the
orchestrator the same day. Full text and numbering in `docs/open-questions.md`
§ "platform-skeleton" (Q19–Q30).

Resolved (raised 2026-10-19 for platform-stack, ruled by the orchestrator the
same day, `docs/handoffs/platform-stack.md`): **Q33** LAN-exposure refusal
details, settled in PS-2.14; **Q34** Windows proof staleness, settled in
PS-2.9. Full text in `docs/open-questions.md`.

Ruled by the orchestrator 2026-10-18 (`docs/handoffs/platform-config.md`,
"orchestrator: rulings on analyst Q31, Q32 and casing"):

- **Q31 Windows proof.** A recorded run on the human's Windows host proves
  the PowerShell scripts. Settles the PS-2.9 proof note.
- **Q32 Model-host defaults.** Scheme, port and URL are set per deployment
  in `.env`; `config/defaults.yaml` has no model-host default. Settles the
  PS-1.2 note.
- Also ruled: loopback and compose service names are not hardcoded hosts
  (PS-1.2); phoenix compose ports move into platform-config (PS-1.2, PS-2.2);
  `changeme` matching is case-insensitive and placeholders are
  `changeme-<key in lowercase>` (PS-1.9).

Ruled by the human 2026-10-18 (`docs/handoffs/platform-skeleton.md`,
"orchestrator: human rulings Q30, Q20, Q7"; F-A narrowing the same day):

- **Q30 Integration mechanism vs DR31 (narrowed by F-A).** Compose services,
  no Docker socket, `gates-it` on internal networks only with no internet
  access; tests reach only the LLM on `aria-gb10-2`, through the stack
  gateway; model-calling integration tests run when it is reachable and skip
  by name otherwise; unit tests keep no network; DR30 still applies;
  offline-bundle checks unchanged. Amends DR31 and the "Integration"
  convention. Settles PS-2.4–PS-2.7, PS-2.13. As first ruled, `gates-it`'s
  network had external access; F-A withdrew that.
- **PS-Q10 / Q20 Supported OS.** Windows (PowerShell) and Linux only; no
  macOS. Settles PS-2.9 and the PS-3.1 platform note; the Windows proof is
  carried as Q31.
- **Q7 Model host.** `aria-gb10-2`, OpenAI-compatible, configured via
  `KE_MODEL_UPSTREAM` and the per-pass base URLs, never hardcoded. Settles
  the PS-1.2 note.

Ruled by the orchestrator 2026-10-18 ("orchestrator: placeholder-secret
ruling"): placeholders are `changeme-<key>`, refused by prefix outside `dev`,
`.env.example` not shipped in the image. Settles PS-1.9.

Answered by the architect:

- **PS-Q7 Gates network vs real stores (Q19).** ADR-KE-009: stores as compose
  services on an internal network; a one-shot `gates-it` joins it; `gates`
  keeps `network_mode: none`; no Docker socket; the offline check uses a
  privileged DinD daemon on an internal network. Settles PS-3.2. Amended by
  Q30, then narrowed by F-A: `gates-it` stays internal-only and reaches the
  model host only through the gateway.

Ruled (each cited by the criteria it settles):

- **PS-Q1 Runner image.** `ubuntu-24.04`, the image `ubuntu-latest` resolved to
  before the 2026-10-19 move; confirm from the CI log of 615adf8 when
  implementing. Settles PS-0.1.
- **PS-Q2 Harness Phoenix and A6.** One Phoenix for harness and product, ports
  from `.env` in 47100–47199; `log_event` keeps reading
  `PHOENIX_COLLECTOR_ENDPOINT`, only its default and the docs change. Settles
  PS-1.2, PS-2.2.
- **PS-Q3 "Local" collector.** A loopback address or a compose service name on
  the internal network; anything else is refused at startup. Settles PS-1.5.
- **PS-Q4 Hidden inputs in dev.** `OPENINFERENCE_HIDE_*` default `true` in every
  env; only `KE_ENV=dev` may set `false`, with a warning. Settles PS-1.5.
- **PS-Q5 Coverage and mypy scope.** Line + branch coverage >= 80% and
  `mypy --strict` over every first-party package (`harness_telemetry` and the
  engine package), tests excluded. Settles PS-1.6.
- **PS-Q6 Readiness without a model host.** Reported as its own field, excluded
  from overall readiness; model-dependent routes check it themselves. Settles
  PS-2.5.
- **PS-Q8 DR16 register.** Confirmed: register entries for config keys arrive
  with policy-book. Settles PS-1.1.
- **PS-Q9 Shipping rule timing.** `platform-stack` may merge before
  `platform-offline`; "deployable offline" is met at the end of
  `platform-offline`, before any reviewer-facing feature ships. Settles the
  split note and PS-3.2.
- **PS-Q11 Python version.** Pin 3.12 (`requires-python = ">=3.12,<3.13"`) in
  `platform-config`. Settles PS-1.8.
- **F2–F6 (architect findings, ruled 2026-10-18).** F2 `KE_` names canonical,
  no aliases (variable-names note, PS-1.1, PS-1.3, PS-1.5). F3 secrets have no
  default; placeholders refused outside dev (PS-1.1, PS-1.9). F4
  `config/verify.env` exempt (PS-1.2). F5 offline check in every local
  `full` (PS-3.2). F6 CI timeout = measured + 50% (PS-3.4). Bundle: no wheels,
  linux/amd64 only (PS-3.1). Re-tags and new criteria accepted (PS-2.1,
  PS-2.5, PS-2.8, PS-2.10–PS-2.12).

---

## Item: ingest-ledger

Outcome metric moved: neither directly; without a complete ledger every later
count is wrong (DR1, DR2).

1. Given N input files, when ingest runs, then the ledger has exactly N rows, one
   per source file, even if several files are byte-identical; duplicates become
   `duplicate_of` edges, never dropped rows. `[integration: test_ledger_one_row_per_file]` (DR1)
2. Parsed + skipped = input, always. Each skip has a named reason from a closed
   enum (`unsupported_type`, `corrupt`, `encrypted`, `empty`, `too_large`, …).
   `[integration: test_ingest_accounting_adds_up]` (DR2)
3. File type is detected from content (magic bytes), not the extension; a `.doc`
   that is RTF is parsed as RTF. `[unit: test_type_detection_by_content]` (DR2)
4. Ingest is idempotent (same file twice → no new rows, no new revision),
   incremental (only new or changed checksums are processed) and resumable (a
   killed run resumes from its manifest). `[integration: test_ingest_idempotent]`,
   `[integration: test_ingest_resume_after_kill]` (DR41)
5. Workers scale horizontally: two workers on one queue never process the same
   file twice. `[integration: test_two_workers_no_double_process]`
6. **Source revisions (corpus history).** See §R-REV-C.

---

## Item: data-plane

Outcome metric moved: neither directly; feeds drafts.

1. Every normalized record carries lineage: source file, page/region, extraction
   method, parser version, model + version, checksum, timestamp.
   `[unit: test_record_lineage_complete]`
2. Extraction profiles are per template and read headers, footers, tables and
   content controls as well as the body. `[unit: test_profile_reads_docx_header_table]`
   using a fixture whose identifying table sits in the header (DR3).
3. "Unknown" is a typed state (`FieldValue.unknown(reason)`), never a string.
   `[unit: test_no_sentinel_strings]` fails if any writer emits a value from the
   sentinel list (`Untitled`, `N/A`, `TBD`, `Unknown`, …); coverage checks count
   typed unknowns as not covered. (DR4)
4. Truncated values are refused and become unknown(`fragment`).
   `[unit: test_refuse_fragments]` (DR5)
5. Every field records `how`: `parsed | routed | entered | imported`.
   `[unit: test_field_provenance_required]` (DR6)
6. Every facet/filter returns matched / not matched / could-not-evaluate, and a
   signal's coverage is published before it may define membership.
   `[unit: test_facet_three_numbers]`, `[unit: test_low_coverage_signal_cannot_define_membership]` (DR7)
7. Version stamps propagate to every derived object; the freshness check lists
   stale objects after any parser, schema or rule version change.
   `[integration: test_freshness_flags_stale_after_parser_bump]` (DR8)
8. Supported inputs: PDF (text + OCR), DOCX/DOC/RTF, XLSX/CSV, HTML, Markdown,
   images, tables, each with a golden fixture. Model per stage is configured
   separately (DR29).

---

## Item: knowledge-plane

Outcome metric moved: neither directly; feeds drafts.

1. Exact-hash tier runs first and its groups are kept as a signal.
   `[integration: test_exact_tier_first_and_kept]` (DR9)
2. Edges are idempotent and canonically oriented; re-running the build produces
   no new edges; invariants (no self edge, star vs clique as pinned) are tested.
   `[integration: test_edges_idempotent_canonical]` (DR10)
3. Singletons reach the graph. `[integration: test_singletons_in_graph]` (DR11)
4. Vectors only rank. No code path compares a similarity to a threshold for a
   decision, and no template renders a similarity number.
   `[unit: test_no_similarity_threshold_in_decisions]` (AST scan),
   `[unit: test_templates_render_no_similarity]` (DR12)
5. Embedding windows are sized in tokens, per section, with `truncated` stamped
   on every vector node and back-off on rejection; dimension matches across model,
   index and config or `/readyz` fails. `[unit: test_token_windows]`,
   `[integration: test_embedding_dimension_mismatch_fails]` (DR13)
6. Title/keyword passes run in PostgreSQL and rank above semantic passes; vectors
   exclude the title. `[integration: test_title_pass_ranks_first]` (DR14)
7. Config knobs that select an algorithm are closed enums the code dispatches on.
   `[unit: test_algorithm_knobs_are_dispatched_enums]` (DR15)
8. Graph schema comes from the domain pack YAML; adding a corpus is adding a pack.
   `[integration: test_second_pack_without_code_change]` with a toy pack.

---

## Item: policy-book

Outcome metric moved: **ratified rules** (directly).

1. Every non-trivial default lives in versioned YAML with a register entry; the
   policy book fails to load if a knob has no entry; a `ratified` entry must carry
   `decided_by`, `decided_on`, `decision_note`. `[unit: test_registry_enforced]` (DR16)
2. A generated human-readable register (`docs/register.md`) has a CI drift check.
   This item introduces the generic drift gate, called by `scripts/verify.sh`: it
   regenerates every non-lockfile generated artifact listed in `CLAUDE.md` and
   fails on `git diff --exit-code`. `[gate: ci/generated-artifacts-drift]` (DR16)
3. Every rule has an owner tier: `institutional_policy | policy_informed | technical`;
   the review queue routes by tier. `[unit: test_rule_requires_owner_tier]` (DR17)
4. Every policy-book version is baselined over the full corpus snapshot before it
   can be offered for ratification; a rule that fires on 100% or 0% is flagged as
   a probable defect. `[integration: test_baseline_required_before_ratification]`,
   `[unit: test_always_fires_rule_flagged]` (DR18)
5. The review packet shows each rule's measured effect (what it blocks, how
   often, on which snapshot). `[integration: test_review_packet_has_effect]` (DR19)
6. A proposed rule's precision is measured over the corpus before it can be added.
   `[integration: test_precision_measured_before_add]` (DR20)
7. One knob answers one question: the register schema has a single `question`
   field and lint rejects a knob referenced by two unrelated rules.
   `[unit: test_one_knob_one_question]` (DR21)
8. Ratification sessions are planned objects with named owner and date; the
   funnel shows ratified / proposed per tier. (DR22)
9. The LLM may only propose; only ratified rules execute; evaluation is
   deterministic with no model client importable from the evaluator package.
   `[unit: test_evaluator_imports_no_llm]` (import-graph check)
10. **Policy history and revision UX.** See §R-REV-P.

---

## Item: verifier-validator

Outcome metric moved: drafts reviewed (raises trust so reviewers act).

1. The LLM edits field by field; it never receives replace-rights over a whole
   section or list. `[unit: test_llm_patch_is_field_scoped]` (DR23)
2. A carry-through verifier runs per section before and after every pass; >100%
   = fabrication, <100% = loss; deletions and new requirements are shown to the
   reviewer. `[unit: test_carry_through_flags_fabrication]`,
   `[unit: test_carry_through_flags_loss]` (DR24)
3. Advisory findings must quote verbatim evidence or are dropped.
   `[unit: test_advisory_without_quote_dropped]` (DR25)
4. Temperature 0; schema-constrained decoding where supported, else JSON mode
   with a repair loop that feeds back the real validation error; error class and
   message logged per item. `[unit: test_repair_loop_feeds_error]` (DR26)
5. Every required prompt instruction maps to a schema field.
   `[unit: test_prompt_schema_alignment]` (DR27)
6. Provenance alignment is one-to-one (Hungarian / linear assignment), never argmax.
   `[unit: test_alignment_one_to_one]` (DR28)
7. Model configuration is per pass (embed, rewrite, audit, compose).
   `[unit: test_per_pass_model_config]` (DR29)
8. The deterministic validator re-judges every AI output and fails closed.
9. Each guard is proven able to fail: a mutation test breaks it once and the
   suite goes red. `[gate: ci/guard-mutation]` (DR38)

---

## Item: agent-workflow

Outcome metric moved: drafts produced → drafts reviewed.

1. Steps Plan → Locate → Evaluate → Compose → Verify → Validate → Review queue →
   Publish run in order; each is a `harness_telemetry` span of the right kind and
   a test asserts the tree. `[unit: test_workflow_span_tree]`
2. Authorization filters are inside the Cypher/SQL query, never post-filtering.
   `[integration: test_authz_in_query_not_post]` seeds a forbidden record and
   asserts it is never fetched (span document count).
3. No user input is interpolated into Cypher/SQL; templates and parameters are
   recorded separately. `[unit: test_no_query_interpolation]` (AST + runtime).
4. `OPENINFERENCE_HIDE_INPUTS=true` / `_OUTPUTS=true` are defaults; Phoenix local.
5. Nothing publishes without a human approval action in the audit log.
   `[integration: test_publish_requires_human]`
6. Every output records the policy-book version and rule revision ids and the
   corpus revisions it cited (§R-REV-P.6, §R-REV-C.7).
7. Unit tests never call a model; model-calling integration and live golden
   tests run when the configured model host is reachable and skip with a
   visible, named reason when it is not (DR31 as amended by Q30).
   `[unit: test_no_model_calls_in_unit_suite]` (network guard),
   `[unit: test_model_tests_skip_with_named_reason]` (both delivered in
   platform-stack, PS-2.7; this item extends them to the workflow's tests).
   Original wording, superseded by Q30: "CI never calls a model; live golden
   tests are opt-in and skip without an endpoint.
   `[unit: test_no_model_calls_in_ci]`".

---

## Item: auth-audit

Outcome metric moved: neither; it is a ship blocker (an unauthenticated approve
once published, DR39).

1. Authorization matrix test walks the live routing table; a route without an
   access decision fails the build. `[unit: test_authz_matrix_covers_all_routes]`
2. The actor always comes from the session, never the request body.
   `[unit: test_actor_from_session_only]`
3. CSRF protection on every cookie-authenticated state change.
   `[integration: test_csrf_required]`
4. Audit log is append-only and hash-chained; `ke audit verify` detects a
   modified, deleted or reordered row. `[integration: test_audit_chain_detects_tamper]` (DR40)
5. SSO is pluggable (CAS, SAML, OIDC behind one interface) with a dev provider that
   never contacts a live IdP in CI. (DR42, A5)
6. Runbooks: "healthy silence vs hung" with its one query; a tested restore
   runbook whose test fails if a restore empties the store and exits 0. (DR41)

---

## Item: frontend

Outcome metric moved: **drafts reviewed** and **ratified rules** (the review
queue and policy editor are where humans act). Funnel ships first.

1. Funnel page: ingested → parsed → in graph → drafted → reviewed → published,
   computed from the database at request time; no count is cached or written to
   docs. `[integration: test_funnel_counts_match_store]`
2. Corpus manager: upload, ingest status, skip ledger, per-record lineage,
   **file and record history** (§R-REV-C.8).
3. Graph explorer: entities, relationships, the evidence behind each edge.
4. Policy-book editor: proposed vs ratified, clause citations, version diff,
   measured effect, owner tier, **rule and book history** (§R-REV-P.7).
5. Review queue: approve / edit / reject with audit; reviewer throughput view.
6. Ask/compose workspace: answer, rules applied (with revision), cited records
   (with revision) side by side.
7. No view renders a similarity percentage (DR12).
8. All JS/CSS assets vendored for offline use.

---

## §R-REV-C — Corpus revision history and UX

Added at the user's request (2026-10-18): "revision UX and history for both
corpus and policy". Owning plan items: `ingest-ledger` (source revisions),
`data-plane` (record revisions), `knowledge-plane` (stamps), `frontend` (UX).
Outcome metric: drafts reviewed — reviewers can only trust a draft whose source
history they can see.

Terms: a **source** is a logical document identified by `(corpus, source_key)`
(A10). A **source revision** is one byte-level version of it (checksum). A
**record revision** is one normalized extraction of a source revision under one
parser/profile/schema version, or one human correction.

1. **Append-only.** Given a source whose content changes, when it is re-ingested,
   then a new source revision is added with `revision_no = previous + 1` and
   `parent_revision_id`; no prior revision row is updated or deleted.
   `[integration: test_source_revision_append_only]` (DB role has no UPDATE/DELETE
   on revision tables).
2. **No-op on unchanged.** Same checksum → no new revision, ledger row gets a
   `seen_at` touch only. `[integration: test_unchanged_reingest_no_revision]`
3. **Cause is typed.** Every record revision has `cause ∈ {source_changed,
   parser_changed, profile_changed, schema_changed, human_correction, restore,
   tombstone}` and `caused_by` (actor or version id).
   `[unit: test_revision_cause_closed_enum]`
4. **Removal is a tombstone.** A source deleted upstream gets a `tombstone`
   revision; history, lineage and every draft that cited it remain readable.
   `[integration: test_tombstone_keeps_history]`
5. **Human corrections survive re-parse.** Given a field whose current value is
   `entered`, when a re-parse yields a different parsed value, then the entered
   value stays current and a `conflict` is raised to the review queue showing
   both; nothing is silently overwritten. `[integration: test_entered_value_survives_reparse]`
6. **Field-level history (blame).** For any field of any record, the system
   returns every value it has had, with revision, `how` (DR6), actor/version and
   timestamp. `[integration: test_field_blame]`
7. **Downstream stamps.** Every entity, vector, edge, draft and answer stores the
   record revision ids it was built from. After a new revision, the freshness
   check lists exactly the derived objects built from the superseded revision.
   `[integration: test_freshness_after_new_source_revision]` (DR8, DR32 — query
   the store, not the run counter).
8. **Corpus snapshots.** A snapshot is an immutable, named set of
   `(record_id, record_revision_id)` taken at a timestamp. Baselines (DR18),
   metrics and findings files name the snapshot they ran on. Comparing two
   snapshots reports buckets: added, changed, removed (tombstoned), unchanged,
   **unaccounted for** (DR33). Buckets sum to the union.
   `[integration: test_snapshot_compare_buckets_sum]`
9. **As-of reads.** Any record, the funnel and search can be read *as of* a
   snapshot or timestamp, with authorization applied in the query (DR39).
   `[integration: test_as_of_read_respects_authz]`
10. **Restore is a new revision.** Restoring an old revision creates a
    `restore` revision that goes through the review queue; it never rewinds a
    pointer silently. `[integration: test_restore_creates_revision_and_review_item]`
11. **Audit.** Every revision write (ingest, correction, restore, tombstone) emits
    an audit-log entry in the hash chain (DR40).
12. **UX — corpus manager** (`frontend`):
    - Source page **History** tab: a timeline of source and record revisions with
      cause badges, actor, parser/profile version, and the skip-ledger outcome per
      revision.
    - **Compare** any two revisions: field-level diff for structured fields,
      section-level text diff (word-level within a section), table cell diff;
      unknown↔value transitions shown explicitly, never as blank.
    - **Blame** toggle on the record view: hover/expand a field to see who or what
      set it, when, and how (parsed/routed/entered/imported).
    - **Impact panel**: for a selected revision, counts of derived objects built
      from it and how many are stale — computed live from the store.
    - **Snapshot** list and snapshot-vs-snapshot comparison with the five buckets.
    - Restore and correction actions require a reason, show a preview diff, and
      land in the review queue.
    - Every view works without JavaScript for reading (server-rendered); diffs are
      keyboard navigable and do not rely on colour alone (WCAG 2.1 AA).
    `[integration: test_history_views_render]`, `[e2e smoke: history page]`

## §R-REV-P — Policy-book revision history and UX

Owning plan items: `policy-book` (model and lifecycle), `agent-workflow`
(provenance on outputs), `frontend` (UX). Outcome metric: **ratified rules** —
ratifiers must see exactly what changed and its effect before signing.

Terms: a **rule** has a stable `rule_key`. A **rule revision** is one immutable
typed definition of it (decision table, threshold, routing), with clause
citation, owner tier and status. A **policy-book version** is an immutable set of
rule revisions plus knob values, identified by a monotonically increasing
version number and a content hash. A **changeset** is a mutable working draft
of the next version.

1. **Immutability.** Ratified rule revisions and published book versions are
   never updated or deleted. `[integration: test_policy_versions_immutable]`
2. **Lifecycle.** Rule revision status: `proposed → in_review → ratified |
   rejected`; later `superseded` or `retired` only by a newer version.
   Proposer is `llm` or a user; only a human with the rule's owner tier can
   ratify. `[unit: test_rule_lifecycle_transitions]`,
   `[integration: test_ratify_requires_owner_tier]`
3. **Two clocks.** Each version records `ratified_at` (when decided) and
   `effective_from` (when it applies); evaluation uses the version effective at
   the request's evaluation time, which is recorded. (A12)
   `[unit: test_effective_version_selection]`
4. **Diff between any two versions.** Output lists rules added / removed /
   changed / unchanged; for changed rules, a typed field diff (decision-table cell
   changes, threshold old→new, routing target), the citation change, the owner
   tier change, and the knob changes. `[unit: test_policy_diff_typed]`
5. **Effect diff.** For two versions baselined on the same corpus snapshot, the
   diff includes, per rule, how many records it blocks/routes under each version
   and the records that changed outcome (listed, not only counted).
   `[integration: test_effect_diff_same_snapshot]` (DR18, DR19, DR33)
6. **Answer provenance.** Every draft, answer and published artifact stores the
   book version, rule revision ids that fired, the corpus snapshot or record
   revisions cited, and the evaluation time. `[integration: test_output_records_rule_revision]`
7. **UX — policy-book editor** (`frontend`):
    - **Version timeline**: each version with status, ratified_at /
      effective_from, ratifiers, and the session it came from.
    - **Compare** picker (any two versions, default: current vs proposed
      changeset) showing the typed diff of P.4 and the effect diff of P.5 side by
      side.
    - **Rule history drawer**: every revision of a rule with who proposed it (LLM
      flagged as such), who ratified or rejected it and the `decision_note`.
    - **Clause view**: the cited clause text from the policy *document revision*
      it came from; when that document gets a new revision whose clause text
      changed, the rule is marked **citation stale** and queued for re-review.
      `[integration: test_citation_stale_on_policy_doc_revision]`
    - **Outputs by rule revision**: count and list of drafts/answers produced by a
      given rule revision, live from the store.
    - **Revert** = start a changeset that re-proposes an earlier revision; it goes
      through baseline and ratification like any change. No one-click rollback.
      `[integration: test_revert_is_a_new_changeset]`
    - Ratify/reject requires a `decision_note`; the packet cannot be submitted
      until the effect diff has loaded.
8. **Audit.** Every proposal, edit, ratification, rejection, publish and revert is
   an audit-chain entry with the actor from the session (DR39, DR40).

---

## §R-DR — Design-rule traceability (one test or gate per rule)

| DR | Rule (short) | Test / gate | Plan item |
|---|---|---|---|
| 1 | One ledger row per source file | `test_ledger_one_row_per_file` | ingest-ledger |
| 2 | Parsed + skipped = input; type by content | `test_ingest_accounting_adds_up`, `test_type_detection_by_content` | ingest-ledger |
| 3 | Per-template profiles read header/footer/tables | `test_profile_reads_docx_header_table` | data-plane |
| 4 | Unknown is typed; sentinel scan | `test_no_sentinel_strings` | data-plane |
| 5 | Refuse fragments | `test_refuse_fragments` | data-plane |
| 6 | Field provenance | `test_field_provenance_required` | data-plane |
| 7 | Facets report three numbers; coverage first | `test_facet_three_numbers`, `test_low_coverage_signal_cannot_define_membership` | data-plane |
| 8 | Version stamps + freshness | `test_freshness_flags_stale_after_parser_bump`, `test_freshness_after_new_source_revision` | data-plane |
| 9 | Exact-hash tier first, kept as signal | `test_exact_tier_first_and_kept` | knowledge-plane |
| 10 | Idempotent canonical edges | `test_edges_idempotent_canonical` | knowledge-plane |
| 11 | Singletons first-class | `test_singletons_in_graph` | knowledge-plane |
| 12 | Vectors rank, never threshold; no % in UI | `test_no_similarity_threshold_in_decisions`, `test_templates_render_no_similarity` | knowledge-plane, frontend |
| 13 | Token windows, truncated stamp, dim check | `test_token_windows`, `test_embedding_dimension_mismatch_fails` | knowledge-plane |
| 14 | Title/keyword in PG, ranked first | `test_title_pass_ranks_first` | knowledge-plane |
| 15 | Closed-enum knobs | `test_algorithm_knobs_are_dispatched_enums` | knowledge-plane |
| 16 | Registry enforced; ratified fields; drift | `test_registry_enforced`, `ci/generated-artifacts-drift` | policy-book |
| 17 | Owner tiers | `test_rule_requires_owner_tier` | policy-book |
| 18 | Baseline before ratification | `test_baseline_required_before_ratification`, `test_always_fires_rule_flagged` | policy-book |
| 19 | Review packet shows effect | `test_review_packet_has_effect` | policy-book |
| 20 | Precision before adding | `test_precision_measured_before_add` | policy-book |
| 21 | One knob, one question | `test_one_knob_one_question` | policy-book |
| 22 | Ratification is critical path | milestone Done check + funnel tier view | policy-book |
| 23 | Field-by-field LLM edits | `test_llm_patch_is_field_scoped` | verifier-validator |
| 24 | Carry-through verifier | `test_carry_through_flags_fabrication`, `test_carry_through_flags_loss` | verifier-validator |
| 25 | Advisory needs verbatim quote | `test_advisory_without_quote_dropped` | verifier-validator |
| 26 | Temp 0, constrained decoding, repair loop | `test_repair_loop_feeds_error` | verifier-validator |
| 27 | Prompts fit the schema | `test_prompt_schema_alignment` | verifier-validator |
| 28 | One-to-one alignment | `test_alignment_one_to_one` | verifier-validator |
| 29 | Per-pass model config | `test_per_pass_model_config` | verifier-validator |
| 30 | Egress allowlist fails closed | `test_egress_guard_startup`, `test_egress_guard_runtime`, `test_egress_allowlist_holds_with_network_access`, `ci/offline` | platform-skeleton |
| 31 | Unit tests never call a model; model-calling integration tests reach the model host only through the gateway, run when it is reachable, else skip by name; no internet access (amended by Q30 and F-A, see note) | `test_no_model_calls_in_unit_suite`, `test_model_tests_skip_with_named_reason`, `test_gates_it_internal_only_and_no_socket` | platform-skeleton (platform-stack), agent-workflow |
| 32 | Check the store, not the counter | `test_funnel_counts_match_store`, `test_freshness_after_new_source_revision` | frontend, data-plane |
| 33 | Buckets + unaccounted | `test_snapshot_compare_buckets_sum` | data-plane |
| 34 | Population defined per metric | `test_metric_declares_population` (metric registry) | jd-metrics-and-demo |
| 35 | Probe reproduces a known number, then control | `test_probe_reproduces_known_count` | jd-metrics-and-demo |
| 36 | Full corpus before thresholds | `test_threshold_requires_full_corpus_run` | policy-book |
| 37 | Rising score suspicion | `test_score_increase_requires_carry_through_check` | verifier-validator |
| 38 | Each guard can fail | `ci/guard-mutation` | verifier-validator |
| 39 | Authz matrix, session actor, startup check, CSRF | `test_authz_matrix_covers_all_routes`, `test_actor_from_session_only`, `test_startup_refuses_unsafe`, `test_csrf_required` | auth-audit; platform-skeleton (`test_startup_refuses_unsafe`) |
| 40 | Hash-chained audit + verify | `test_audit_chain_detects_tamper` | auth-audit |
| 41 | Manifests, resume, runbooks, tested restore, restart policies | `test_ingest_resume_after_kill`, `test_restore_not_empty`, `test_compose_services_have_restart_policy` | ingest-ledger, auth-audit, platform-skeleton |
| 42 | Pluggable SSO, dev hatch | `test_sso_dev_provider_offline` | auth-audit |

**DR31 amendment (human rulings Q30 and F-A, 2026-10-18).** DR31 now reads:
integration tests run as compose services with no Docker socket, on internal
networks only, with no internet access; the only outside host they reach is
the LLM on `aria-gb10-2`, and only through the stack gateway; model-calling
integration tests run when that host is reachable and skip with a visible,
named reason when it is not (for example on GitHub runners); unit tests
(`verify.sh fast`) keep no network; the app's egress allowlist (DR30) still
applies; the offline-bundle checks still prove the deployed product runs
offline. Criteria: PS-2.7, PS-2.13 and agent-workflow 7. *Q30 as first ruled,
narrowed by F-A:* integration tests ran "on a network with external access",
and DR31's test was `test_gates_it_has_network_access_and_no_socket` (now
`test_gates_it_internal_only_and_no_socket`). *Original wording, kept for the record:* the table row read
"CI never calls a model | `test_no_model_calls_in_ci` | agent-workflow", and
the build prompt's rule said integration tests use real Postgres/Neo4j/Valkey
"via testcontainers" with mocked model calls. DR30's earlier
in-process socket-guard test is replaced by
`test_egress_allowlist_holds_with_network_access` for the same reason; it is
kept under F-A because model calls still go through the gateway forward and
the allowlist must still hold.

---

## Item: jd-pack-port

Outcome metric moved: drafts produced (the first real ones).

1. Port verdict table (architecture.md §Port) is followed module by module; the
   source commit `2e3e6dc` is recorded in every ported file's header comment and in
   `docs/port-log.md`.
2. Tests are ported with the code; a module is not "ported" until its tests pass
   under `mypy --strict` and coverage.
3. The `jd` pack deduplicates (exact, near, semantic), harmonizes to ratified
   rules, composes new JDs and routes everything to human review.
4. SFU values live in `profiles/sfu/` as pure data; `[unit: test_engine_has_no_sfu_literals]`
   greps engine and pack code for profile literals.
5. `fixtures/` holds the public JD corpus with provenance in `fixtures/README.md`.

## Item: jd-metrics-and-demo

Outcome metric moved: both are *reported*; this item makes them visible.

1. A dated findings file `docs/findings/<date>-jd-metrics.md` names the query and
   the corpus snapshot for each figure: corpus size, duplicate buckets, drafts
   produced, drafts reviewed, fabrication rate before/after the verifier, time per
   JD vs a recorded manual baseline (A9).
2. No figure is copied from the JD repo's docs. `[unit: test_findings_cite_query]`.
