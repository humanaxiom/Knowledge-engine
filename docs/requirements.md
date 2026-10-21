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
   bypassed. Branch protection on the remote (Q18) was skipped by decision.
   *Q18 resolved 2026-10-20 (human, SKIPPED; `docs/open-questions.md`): branch
   protection is not enabled, merges stay a manual human action, and this
   hook is the only automated guard (accepted risk).*
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
      - **Accepted bypasses off `main`/`master`** (silent by design; accepted
        risk per Q18, resolved 2026-10-20: branch protection SKIPPED, merges
        stay a manual human action): words hidden from the text (variables,
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
  (fast). The model defaults live only in config. *Amended 2026-10-20 (Q38
  resolved; item model-roles MR-1):* compose and rewrite use `qwen3.5:latest`,
  audit uses `gpt-oss:120b`, and embed uses `nomic-embed-text` (768-dim); the
  fallback is `gpt-oss:20b` (Q54, A54). *Superseded, kept for the record:* "the prompt's
  (`qwen2.5:14b-instruct`, fallback `llama3.1:8b`, `nomic-embed-text` 768-dim,
  A7)".
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
  - *Prod refused until auth-audit (orchestrator ruling 2026-10-19,
    platform-offline; architecture §2.3 refusal 7, ADR-KE-010).* Given
    `KE_ENV=prod` with `auth.enabled=true` (the `defaults.yaml` default, or
    `KE_AUTH__ENABLED=true`), startup fails with a message naming
    `auth.enabled` and saying authentication is not implemented until
    auth-audit. With the auth-disabled refusal above, prod cannot start in
    this release. This check runs after every other startup check, so any
    other unsafe prod setting is still refused naming its own setting.
    `[unit: test_startup_refuses_prod_until_auth_audit]` (fast)
  - *Auth enabled outside prod warns (security M-L2a).* Given
    `auth.enabled=true` with `KE_ENV` `dev` or `ci`, startup succeeds and logs
    a WARNING naming `auth.enabled` that says it has no effect until
    auth-audit; with `KE_ENV=dev` and a non-loopback `KE_BIND_ADDRESS`, both
    warnings are logged and startup succeeds.
    `[unit: test_auth_enabled_outside_prod_warns_no_effect_until_auth_audit]`
    (fast)
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
    - *Unit form (adopted from architect §2.6, 2026-10-19).* Given stubbed
      probes with every store ok and the model probe failing, `/readyz`
      answers 200, ready, with the model-host entry marked not required;
      given one store failing, it answers 503. Given the compose model
      `base_url` unset (null), the model-host reason is `not_configured`
      and no model probe is called.
      `[unit: test_readyz_ready_excludes_model_host]` (fast). This unit test
      and the integration test above are kept as two names: the unit test
      fixes the rule with stubs, the integration test proves it against
      the real stores.
    - *No upstream means not configured (Windows proof F1; orchestrator
      rework round 1, 2026-10-19).* Compose always sets every
      `KE_MODELS__*__BASE_URL` to the gateway forward (PS-2.7 *Model
      wiring*), so a set base URL does not mean a model host is configured.
      Given `KE_MODEL_UPSTREAM` unset or empty (`settings.models.model_upstream`
      falsy), with the compose base URL set to the gateway, the model-host
      entry is `{"ok": false, "reason": "not_configured", "required": false}`,
      no model probe is made, and the response is still ready (200). Given
      `KE_MODEL_UPSTREAM` set, the probe is made (control case).
      `[unit: test_readyz_model_host_not_configured_without_upstream]` (fast;
      cases: unset, empty), control `test_readyz_model_host_probed_when_upstream_set`
      (fast). In the integration suite, `test_readyz_reports_each_dependency`
      asserts `not_configured` when `KE_MODEL_UPSTREAM` is empty in the
      verify project, and `test_readyz_ready_without_model_host` sets
      `KE_MODEL_UPSTREAM` so its closed-port case still exercises a probe
      failure (full).
  - *Model host reachable.* Given the configured model host reachable, the
    model-host field reports success. This is a model-calling integration
    test: it skips with a named reason when the host is unreachable (PS-2.7).
    `[integration: test_readyz_reports_reachable_model_host]` (full)
  - *Status and reasons (analyst, 2b plan, 2026-10-19; shape from
    `docs/architecture.md` §2.4 "/readyz").* Ready answers 200, not ready
    503. Given any failing check, its reason is one of the fixed vocabulary
    the architecture names and contains no DSN, password, host credential or
    exception message text. `test_readyz_fails_when_store_down` asserts both,
    with a store password set to a known marker that must not appear in the
    body.
    - *Vocabulary (adopted 2026-10-19, architect §2.4 "/readyz" Reasons).*
      Every reason is exactly one of `timeout`, `refused`, `unreachable`,
      `auth_failed`, `egress_denied`, `not_configured`, or `error:` followed
      by the exception class name only. `unreachable` is a dial failure
      other than refused or timed out (for example a name that does not
      resolve); `not_configured` is the model host with no base URL or no
      `KE_MODEL_UPSTREAM` (F1, below *Unit form*). Given
      each exception family the architecture maps, the classifier returns
      its word; given an exception whose message (or a psycopg error) carries
      a marker password, the marker never appears in the result.
      `[unit: test_readyz_reason_vocabulary]` (fast)
  - *Bounded.* Given a store whose address accepts no connection, `/readyz`
    answers within that store's configured `readiness.timeout_s` plus a
    margin the test states, never hanging. Asserted in
    `test_readyz_fails_when_store_down` (full).
    - *Probe unit (adopted 2026-10-19, architect §2.6).* Given a store probe
      pointed at a closed loopback port inside `gates`, it returns `refused`
      well within `readiness.timeout_s`.
      `[unit: test_store_probe_classifies_closed_port]` (fast)
  - *Traced (AGENTS.md "Untraced agent steps").* One `/readyz` call produces
    an `api.readyz` CHAIN span with one `readyz.<dep>` TOOL child per
    dependency. `[unit: test_readyz_is_traced]` (fast; probes stubbed,
    in-memory exporter)
  - *Store identity has one source (carry-in, review round-0 N4).* Given the
    compose files and `config/defaults.yaml`, the postgres user and database
    the `postgres` service creates equal `stores.postgres.user` and
    `stores.postgres.database`. `[unit: test_compose_postgres_identity_matches_defaults]`
    (fast)
  - *No GSS encryption on postgres connections (security L-13; rework
    round 1, 2026-10-19).* psycopg-binary vendors old Kerberos/SASL
    libraries that pip-audit cannot see, so the engine never negotiates GSS
    encryption. Given the postgres readiness probe, it connects with
    `gssencmode="disable"`. `[unit: test_postgres_probe_disables_gss_encryption]`
    (fast). Given the engine source, every psycopg connect call passes
    `gssencmode="disable"`.
    `[unit: test_every_postgres_connect_in_engine_disables_gss_encryption]`
    (fast; static scan). The image scanner security also suggested
    (trivy/grype over `ke-app`) is not placed by this criterion (see the
    analyst rework-1 note).
- **PS-2.6 Worker.** Given a no-op job enqueued on Valkey, the worker consumes
  it exactly once and records completion. `[integration: test_worker_consumes_noop_job]` (full;
  runs in `gates-it` under the Q30 integration convention).
  - *Observable result (analyst, 2b plan).* "Exactly once" and "records
    completion" are asserted as: the job's queue status is `finished` and
    the job's side effect (the counter named in `docs/architecture.md` §2.4
    "Worker") equals 1 after the test's wait, enqueued from `gates-it` to the
    real `worker` container, never an in-process worker.
  - *Job path (2026-10-19, architect §2.4 "Worker").* The no-op job is
    `engine.jobs.noop`, enqueued by that dotted path on the `default` queue.
    This replaces `engine.worker.jobs.noop`; no criterion or test names the
    old path.
  - *Still refuses unsafe settings.* The 2a refusal behaviour of
    `python -m engine.worker` (startup refusals, including refusal 6) holds
    after the idle loop is replaced: the existing entrypoint unit test stays
    green unweakened. Its fixture patches `engine.worker.run` instead of
    `signal.pause`/`time.sleep`; its assertions are unchanged (orchestrator
    ruling W1, 2026-10-19).
  - *Traced.* Each job runs in a `job.<name>` CHAIN span carrying the job id.
    `[unit: test_worker_job_is_traced]` (fast; in-memory exporter)
  - *Runs only engine jobs, never unpickles (security M-1, engine side;
    orchestrator rework round 1, 2026-10-19).* Valkey is reachable from
    every `backend` service, so the worker trusts nothing it reads there.
    - *JSON only.* Given the worker built by `engine.worker.run`, the worker
      and each of its queues use `rq.serializers.JSONSerializer`; job data is
      never decoded with pickle. `[unit: test_worker_uses_json_serializer]`
      (fast)
    - *Allowlist.* Given a job whose function is not named in
      `engine.jobs.__all__` (cases: `platform.node`, `os.getcwd`, and
      `engine.jobs.traced_job`, which is in the module but not in `__all__`),
      when the worker executes it, then the function is never called and the
      job does not reach status `finished`. Given `engine.jobs.noop` (in
      `__all__`), it runs and finishes (control).
      `[unit: test_worker_refuses_a_job_outside_engine_jobs]`, control
      `test_worker_runs_a_job_in_engine_jobs` (fast)
    - *SimpleWorker pinned (review nit, mutant WK3).* The worker is an
      `rq.SimpleWorker` (no fork, so job spans are flushed, architecture §2.4
      "Worker"). `[unit: test_worker_is_a_simple_worker]` (fast)
    - *Network side deferred.* Valkey on its own network and a Valkey
      password/ACL are not in this item; they are auth-audit carry-in 7 and
      must land before any ingest exposure.
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
    - *Model wiring (adopted 2026-10-19, architect §2.4 "Model wiring").*
      Given the compose files, `api`, `worker` and `gates-it` each set every
      `KE_MODELS__*__BASE_URL` to the gateway's model forward
      (`http://gateway:${KE_GATEWAY_MODEL_LISTEN:-8102}/v1`) and their egress
      allowlist to `gateway` followed by `${KE_EGRESS_ALLOWLIST:-}`, while
      `gateway` keeps `${KE_EGRESS_ALLOWLIST:-}` unprefixed.
      `[unit: test_compose_model_wiring]` (fast). It checks environment
      wiring only; network membership stays with
      `test_gates_it_internal_only_and_no_socket`.
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
    - *Not configured (umbrella ruling, model upstream in local verify).*
      Given `KE_MODEL_UPSTREAM` or `KE_EGRESS_ALLOWLIST` unset or empty in
      the verify project, each model-calling test is reported skipped with a
      reason that names the unset key and says it is not configured (not
      "unreachable"), and no reachability probe is attempted. Covered by a
      second case of `test_model_tests_skip_with_named_reason` (fast).
    - *Only model-calling tests skip on network grounds.* Given the fixture
      run, a test not marked model-calling that hits the probe's failure
      fails rather than skips. Same test (fast).
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
  - *Who launches (carry-in, review round-0 N11; aligns with ADR-KE-009 and
    `docs/architecture.md` §2.2).* Inside `verify.sh full`, the stack the
    smoke checks is brought up by the launch script and removed by the
    teardown script, which `verify.sh` runs around the smoke host half (trap
    teardown); "smoke launches ... tears down" above is met by that
    sequence. The 2a split-table wording "smoke launches, checks /healthz,
    tears down" is read the same way.
  - *Tears down only what it launched (orchestrator ruling S1, 2026-10-19).*
    "Then tears it down" applies only to a project the smoke itself
    launched. Given no running container of the project before the smoke
    starts, the smoke launches it and tears it down on every exit path,
    pass or fail. Given the project already running (an operator's live
    stack, smoke run by hand), the smoke runs its checks against it and
    leaves it running on every exit path: it never runs the teardown
    script against it. Static cases are added to
    `test_smoke_stops_and_restarts_a_store` (fast, fake docker): no
    pre-existing project → teardown runs, including after a failed check;
    pre-existing project → teardown never runs. Whether the store
    stop/start runs against a pre-existing project is Q37.
  - *Store stop/start (PS-2.5 smoke).* Given the launched stack, the smoke
    host half stops one real store container, then asserts `/readyz` answers
    503 with that store's check failing and naming it, then starts it and
    asserts `/readyz` returns to 200 within a configured wait. Given the
    store fails to come back, the smoke fails naming the store; it never
    passes with a store left stopped. Static cases: `[unit: test_smoke_stops_and_restarts_a_store]`
    (fast, fake docker: asserts the stop, the start, both readiness checks,
    and a non-zero exit when readiness never recovers).
  - *Every service healthy.* `test_stack_services_healthy` (PS-2.1) runs in
    the same smoke after the store is back.
    - *Order (review R-B3, rework round 1, 2026-10-19; the criterion stands
      as written).* The every-service health check runs after the final
      `/readyz` ready, that is after the stopped store is started and
      readiness has recovered, never only before the stop. Given a service
      left unhealthy after the restart, the smoke fails naming it.
      `[unit: test_smoke_checks_every_service_healthy_after_the_store_is_back]`,
      `[unit: test_smoke_fails_when_a_service_is_unhealthy_after_the_restart]`
      (fast, fake docker)
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
    not name macOS as supported. *Narrowed 2026-10-19 (Q50 in scope):* the
    offline install with `install.sh` on an Apple-silicon Mac is in scope
    (PS-3.1 per-arch bundles), and the quickstart names it there. Q53 asks
    whether the launch scripts follow.
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
  - *What makes the Windows run stale (Q34 scope ruling, orchestrator
    rework round 1, 2026-10-19).* "Script" in the Q34 rule above means the
    PowerShell launch, build and teardown path. Only a diff since the
    recorded run that touches the PowerShell launch/build/teardown scripts,
    any compose file or any Dockerfile makes it stale, and then the run is
    repeated before commit. Gate-only bash scripts (for example
    `scripts/verify.sh`, `scripts/lint.sh`, `scripts/smoke.sh`,
    `scripts/env_value.sh`) and engine code do not make it stale.
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
  - *Names how to turn them on (umbrella ruling, model upstream in local
    verify).* The same section names `KE_MODEL_UPSTREAM` and
    `KE_EGRESS_ALLOWLIST` as the only two keys a local `verify.sh full`
    takes from the caller's environment or the operator's `.env`, and says
    the tests skip by name when either is unset. Same test (fast). The
    section's text was added at the 2a docs gate; only the test is new.
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
- **PS-2.21 Model upstream in local verify (umbrella ruling, 2026-10-19,
  "model upstream in local verify"; 2b).** Delivers Q30's "model-calling
  tests run when `aria-gb10-2` is reachable" for local runs.
  - *Exactly two keys.* Given `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST`
    set in the caller's environment, or in the operator's gitignored `.env`,
    when `verify.sh full` launches its verify project, then those two values
    reach the verify project's `gateway`, `api`, `worker` and `gates-it`.
    `[unit: test_verify_full_passes_model_upstream_keys]` (fast; fake
    docker as in the B6 tests; cases: caller env only, `.env` only, neither).
  - *Nothing else from `.env`.* Given a `.env` that also sets other keys
    (a secret, `KE_ENV`, `KE_BIND_ADDRESS`, a port), each with a marker
    value, none of those markers reaches the verify project's environment
    or compose arguments. `[unit: test_verify_full_takes_no_other_env_key]`
    (fast)
  - *No other caller `KE_*` key (security L-11; rework round 1,
    2026-10-19).* Compose gives the caller's shell precedence over
    `--env-file`, so the caller environment is filtered too. Given the
    caller's environment sets other `KE_*` keys (for example
    `KE_STORES__POSTGRES__PASSWORD`, `KE_ENV`, `KE_BIND_ADDRESS`), each with
    a marker value, when `verify.sh full` launches its verify project, then
    none of those markers reaches the verify project's environment or
    compose arguments (so no real store password reaches the verify stores
    or `gates-it`); only `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` pass.
    `[unit: test_verify_full_takes_no_caller_ke_key_but_the_model_keys]`
    (fast; fake docker as in the B6 tests)
  - *Unset means skip, never fail.* Given either key unset (as in CI, which
    has no `.env`), `verify.sh full` still passes, and the model-calling
    tests skip with the "not configured" reason of PS-2.7.
  - *No bypass.* The passed values go through the same checks as a launched
    stack: the gateway's upstream check (2a, security M-3) and the engine's
    egress guard (PS-1.3, PS-1.4). The existing tests for those stay green
    unweakened.
  - *Shown once with the host reachable.* The 2b evidence folder holds one
    local `verify.sh full` run with both keys set and `aria-gb10-2`
    reachable (human ruling 2026-10-19: `KE_MODEL_UPSTREAM` is
    `aria-gb10-2:11434`, allowlist host `aria-gb10-2`; Q38), in which the model-calling tests ran and passed (not
    skipped). If the host is unreachable when 2b closes, the tester reports
    that to the orchestrator; it is never shown with a skip in its place.
    `[gate: recorded local full run]` (manual)
  - *Precedence (Q35, resolved 2026-10-19).* Given a key set in both the
    caller's environment (even empty) and the repo-root `.env`, the caller's
    value wins. Only the repo-root `.env` counts as the operator's `.env`; a
    file named by `KE_ENV_FILE` is not read. Until platform-offline (L-5),
    "nothing else from `.env`" is asserted for the verify project's
    environment and compose arguments only, not the filesystem.
  - *Fixture (orchestrator ruling W1, 2026-10-19).* The `verify.sh` B6 temp
    tree used by these tests gains an `env_value.sh` stub; assertions are
    unchanged.
- **PS-2.22 Teardown leaves nothing of its project (carry-in, security L-9;
  2b).** Given a project with its own profile service containers (`gates`,
  `gates-it`), a `gates-it-run-*` one-off still running and its `backend`
  network still attached, when the teardown script (bash and PowerShell)
  runs, then afterwards no container or network labelled with that
  project's compose project name remains; if one cannot be removed, teardown
  exits non-zero naming it. Given another project's containers and
  networks, teardown leaves them untouched (it acts only on the resolved
  project name, never a default). With this, `verify.sh full`'s
  leaked-project check (2a review N7) fires on such a leak.
  `[unit: test_teardown_removes_or_reports_project_leftovers]`,
  `[unit: test_teardown_leaves_other_projects_alone]` (fast; fake docker,
  bash under `sh`, PowerShell under `pwsh` in the gates image). The
  Windows run (PS-2.9) shows the PowerShell teardown leaving none. This
  must stay consistent with ruling F3 (teardown never uses `--profile '*'`);
  the architect states how.
- **PS-2.23 PowerShell lint cannot be escaped by a file name (carry-in,
  security L-10, review rework-1 N-1, N-2, N-5, rework-2 R2-N6; 2b).**
  - *Wildcard names (L-10).* Given a `.ps1` whose name contains `[`, `]`,
    `*` or `?` and whose content has a finding (e.g. `b[1].ps1` with
    `Invoke-Expression`), `scripts/lint.sh` fails, either reporting that
    finding for that exact file or refusing the name and naming the file;
    it never passes. `[unit: test_lint_ps1_wildcard_name_cannot_escape]`
    (fast)
  - *Each file covered (N-1, N-5).* Every `.ps1` that lint.sh's scope
    covers is passed to PSScriptAnalyzer by its own path, including one in a
    subdirectory. `test_lint_covers_every_shell_and_powershell_script`
    (fast) is extended to require each path and to include a nested file.
  - *Warnings fail (N-2).* Given a planted Warning-severity finding, lint
    fails. `[unit: test_lint_fails_on_warning_severity_finding]` (fast)
  - *Any-context payload (R2-N6).* `test_lint_runs_no_code_from_a_powershell_filename`
    gains a payload that parses in any context (or a static assertion that
    the `-Command` text is fixed), so a per-file shape cannot pass it.
  - *Any case, modules, no links (security L-12; rework round 1,
    2026-10-19).* PowerShell files are selected case-insensitively and
    include modules: given a finding planted in `scripts/x.PS1`,
    `scripts/m.psm1`, `scripts/sub/Mixed.Ps1` or `scripts/M.PSM1`, lint fails
    naming the file. `[unit: test_lint_covers_upper_case_ps1_and_psm1]`
    (fast). Given a symlink under `scripts/` named like a script (`.ps1` or
    `.sh`), whether its target is inside or outside `scripts/`, lint fails
    (exits non-zero); it never passes.
    `[unit: test_lint_fails_on_a_symlinked_script]` (fast)
  - *Lone `[` (review nit, rework round 1).* Given a `.ps1` whose name
    contains a lone `[`, lint fails without running PowerShell, and its
    output names the rule it refused under. `[unit: test_lint_ps1_lone_open_bracket_is_refused_before_pwsh]`
    (fast)
- **PS-2.24 Tests that guard 2a security controls (carry-in, review
  rework-2 R2-N1–N5, review-ci-fix N2; 2b).** Each new case is shown RED
  against the mutant the reviewer recorded as surviving.
  - *R2-N1 (T3/T4).* Teardown (bash and PowerShell) never passes
    `--remove-orphans`. `[unit: test_teardown_does_not_remove_orphans]` (fast)
  - *R2-N2 (T5/T8).* Given `KE_ENV_FILE` set, teardown passes it as
    `--env-file` and carries the project name.
    `[unit: test_teardown_carries_project_and_env_file]` (fast)
  - *R2-N3 (version anchors).* The launch scripts refuse Engine
    `28.0.1-rc.1` and accept `100.0.0`; cases added to
    `test_launch_refuses_docker_engine_below_28_or_unreadable` (fast).
  - *R2-N4 (SM-I3).* Given the backend network inspected as not internal,
    the smoke host half fails naming the network; case added to
    `SmokeBackendIsolatedTest` (fast).
  - *R2-N5 (GP-order).* Every `docker/gateway/1x-ke-*.sh` check sorts
    before the image's `20-envsubst` step.
    `[unit: test_gateway_checks_run_before_envsubst]` (fast)
  - *ci-fix N2.* The hook's structural L21 trace count does not depend on the
    caller's `PS4`. `[unit: test_trace_count_independent_of_caller_ps4]`
    (fast). ci-fix N1 (a comment in the hook next to the counted lines)
    has no test; the reviewer checks it.
  - *Round-0 N3 (P5).* `*_LISTEN` keys count as ports for the PS-1.2 scan,
    and a literal `target:` port in a compose file is flagged; cases added
    to `test_no_hardcoded_ports` (fast).

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
| 2b | `platform-stack-ready` | PS-2.5, PS-2.6, the rest of PS-2.7, PS-2.8, PS-2.13, PS-2.18, PS-2.21–PS-2.24, the PS-3.4 measurement, a fresh PS-2.9 Windows run (Q34: 2b changes compose and scripts) | the same stack with readiness, worker, model-gated integration tests and the full smoke |

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

**2b gate depth (analyst, 2026-10-19; names adopted from architect §2.6
the same day).** Fast: `test_readyz_reason_vocabulary`, `test_readyz_is_traced`,
`test_readyz_ready_excludes_model_host`, `test_store_probe_classifies_closed_port`,
`test_compose_model_wiring`,
`test_compose_postgres_identity_matches_defaults`, `test_worker_job_is_traced`,
`test_gateway_only_external_upstream_is_model_upstream`,
`test_model_tests_skip_with_named_reason`, `test_no_model_calls_in_unit_suite`,
`test_smoke_stops_and_restarts_a_store`, `test_claude_md_lists_verify_only_checks`,
both PS-2.18 tests, every PS-2.21–PS-2.24 unit test, `test_ci_job_has_timeout`.
Full: the four `test_readyz_*` integration tests, `test_worker_consumes_noop_job`,
and the smoke (store stop/start, every service healthy). Manual: the
PS-2.21 reachable-host run and the PS-2.9 Windows run. The item's gate is
`scripts/verify.sh full`.

**PS-3.4 in 2b.** The baseline is 274 s (CI on 0f2821c, ubuntu-24.04,
`docs/evidence/platform-stack/ci-run-0f2821c.txt`), which gives 7 minutes.
2b adds the store stop/start and the worker, so the value is set from a CI
run that includes them (Q36, resolved). *Orchestrator ruling C1,
2026-10-19:* `timeout-minutes` stays at 20 until 2b's first green CI run;
the 7 minutes derived from the 274 s baseline is not applied. That run's
duration plus 50%, rounded up to a whole minute, is then set in a
follow-up commit on the 2b branch before the item closes, with the run's
log saved in `docs/evidence/platform-stack-ready/` and the reviewer
checking the value against it. The stale `ci.yml` comment that every gate runs
"with networking disabled" is corrected in the same edit (round-0 N10;
reviewer checks). The 2b CI evidence also records the elapsed time of the two
requirement-4f 1 MB hook tests (ci-fix watch); if one flakes, that goes to an
orchestrator ruling, and the 3 s bound is never loosened quietly.

**Carry-ins from platform-stack-up (`docs/handoffs/archive/platform-stack-up.md`)
— placement (analyst, 2026-10-19):**

| Finding | Here? | Where |
|---|---|---|
| model upstream in local verify (umbrella ruling) | yes | PS-2.21; PS-2.7 *Not configured*; PS-2.13 |
| security L-9 | yes | PS-2.22 |
| security L-10; review rework-1 N-1, N-2, N-5; R2-N6 | yes | PS-2.23 |
| review R2-N1–N5; review-ci-fix N2; round-0 N3 | yes | PS-2.24 |
| review-ci-fix N1 (hook comment) | yes, no criterion | reviewer checks (PS-2.24) |
| 1 MB timing-margin watch | yes, no test | elapsed recorded in the 2b CI evidence (PS-3.4 note above) |
| round-0 N4 (postgres identity) | yes | PS-2.5 *Store identity* |
| round-0 N10 (ci.yml comment) | yes, no criterion | with PS-3.4 |
| round-0 N11 (who launches the smoke) | yes | PS-2.8 *Who launches* |
| round-0 N9 (dead code: `support.py` fallback, `verify_provider` arg) | yes, no criterion | with PS-2.18 and the R6 clean-up; reviewer checks |
| R2-N7 (fake vs §2.4 names) | yes, no criterion | architect aligns §2.4 or the tester the fake |
| R2-N8 (single network inspect) | yes, no criterion | only if PS-2.8 rewrites that smoke code |
| R2-N9 = rework-1 N-8 (autocrlf in lint tests) | yes, no criterion | the class is edited for PS-2.23 anyway |
| rework-1 N-4 (gateway charset check) | yes, no criterion | security rules at the 2b audit: test it or record it as defence in depth |
| rework-1 N-3 | done | resolved in 2a rework 2 (L4 killed, `review-rework2.md`) |
| round-0 N5 | done | closed by 2a B4 (smoke resolves without `.env`) |
| rework-1 N-6 (M-2 errno record) | close | superseded by the inspect proof (ruling R1-B1 (ii)); orchestrator confirms |
| security L-5 (gates-it root, rw repo) | no | `platform-offline`, which reworks the verify host half for DinD; see Q35 |
| security L-8; rework-1 N-7 (PSScriptAnalyzer hash, telemetry ENV order) | no | `platform-offline` (gates image and supply chain); since moved to `platform-supply-chain` (PS-3.7, split ruling 2026-10-19) |
| round-0 N6 (shared image tags), N8 (Dockerfile layer order) | no | `platform-offline`, where the bundle names and rebuilds images |

**2b size (analyst, 2026-10-19).** One branch. The product part (PS-2.5,
2.6, 2.7 rest, 2.8, 2.13, 2.18, 2.21, PS-3.4) is about 20 named tests; the
carry-ins (PS-2.22–2.24) mostly add cases to existing 2a test classes. Both
halves change compose or scripts, so each would need its own Windows run
(Q34); one branch needs one. If the TDD RED for 2b exceeds what one review
loop can judge, the fallback split is: `platform-stack-ready` (product
part) then `platform-stack-hardening` (PS-2.22–PS-2.24), in that order.
Suggested TDD order: PS-2.18 → PS-2.24 → PS-2.22/2.23 → PS-2.5 →
PS-2.6 → PS-2.7 rest and PS-2.21 → PS-2.8 → PS-2.13 → PS-3.4.

**2b dependency licence note (orchestrator ruling, 2026-10-19).** 2b adds
`psycopg[binary]`, `neo4j`, `redis` and `rq`. psycopg is LGPL-licensed;
this is accepted because it is open source and used unmodified. Security
confirms the licence of the version pinned in `uv.lock` at the 2b audit;
if the pinned version's licence differs from that, it goes back to the
orchestrator.

### PS-3 platform-offline

- **PS-3.1 Offline bundle.** `scripts/bundle.sh` writes one bundle holding
  every image the stack runs, any vendored assets, and a checksum manifest;
  given a modified file, the install step rejects the bundle.
  `[unit: test_bundle_manifest_rejects_tamper]` (fast)
  - *Bash only for bundling (orchestrator R1, 2026-10-19).* Bundling runs on
    a Linux build host; there is no `bundle.ps1`. Install has a bash and a
    PowerShell script.
  - *No wheels (orchestrator ruling, 2026-10-18).* The bundle carries no
    Python wheels: the images carry their own dependencies. Rebuilding an
    image offline is out of scope.
  - *Every image listed.* Given the compose files, every image the stack
    services use is in the bundle. `[unit: test_bundle_lists_every_compose_image]` (fast)
  - *Platform: one bundle per arch (amended 2026-10-19; human rulings Q49,
    "build it for both", "Build the images"; Q50 in scope).* This replaces
    the earlier "linux/amd64 only, never `--platform`" text. The
    per-arch criteria are under "PS-3.1 per-arch bundles" below.
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

**Analyst review for `platform-offline` (2026-10-19).** PS-3.1–PS-3.4 above
stand as written; the sub-bullets below make each one testable case by case,
and PS-3.5–PS-3.9 place the carry-ins (`docs/handoffs/archive/platform-stack-ready.md`,
"item closed"). Design: `docs/architecture.md` §2.5, ADR-KE-012. Open
questions Q40–Q46 (`docs/open-questions.md`) each carry an assumption, and
none blocks the RED step. Where a criterion depends on one, it cites it.

*Reconciled with the rulings (analyst, 2026-10-19).* The criteria below now
follow the orchestrator's rulings in `docs/handoffs/platform-offline.md`
("rulings on analyst plan", "rulings on architect R1–R7", "rulings from
spikes (R2, R6)") and spike evidence `docs/evidence/platform-offline/spikes.md`.
Q40, Q41, Q43–Q46 are resolved; Q42 moves to `platform-supply-chain`; Q47
is new and does not block RED. Where the earlier text and a ruling differed,
the text was changed in place. Change list:
`docs/evidence/platform-offline/analyst-reconcile.md`.

PS-3.1 additions (bundle and install):
- *Manifest covers every file.* `MANIFEST.sha256` lists every file in the
  bundle except itself, and `bundle.json` has one entry per image.
  `[unit: test_bundle_manifest_covers_every_file]`, `[unit: test_bundle_json_names_every_image]` (fast)
- *One tar per image (R2).* The bundle holds one image tar per stack image,
  each written from the image's tag with no `--platform` flag (that flag
  changes the manifest digest; spike S1). Per-arch bundles keep this: the
  arch comes from the daemon, never from a flag.
  `[unit: test_bundle_saves_one_tar_per_image_without_platform]` (fast,
  stubbed docker)
- *`bundle.json` entries (R2; orchestrator ruling on the architect's spikes
  amendment, 2026-10-19).* Each entry records exactly four fields: `file`
  (the tar's path in the bundle, which `MANIFEST.sha256` lists), `ref` (the
  pinned source reference, digest included for vendor images), `as` (the
  local tag the installer gives the loaded image) and `services` (the
  space-separated compose service names that run this image, each matching
  `[a-z0-9_-]+`). Every stack service appears in exactly one entry's
  `services`. `as` carries no `@sha256:` digest and no registry host, and no
  two entries share an `as`. Given an entry missing any of the four fields,
  or a `services` value that is empty or has a name outside `[a-z0-9_-]+`,
  the installer rejects the bundle before any `docker load`.
  `[unit: test_bundle_json_records_file_ref_as]` (asserts all four fields),
  `[unit: test_install_rejects_bundle_json_missing_field]` (parametrised
  over the four fields) (fast).
- *`as` tag scheme (architect §2.5, accepted 2026-10-19).* A first-party
  image's `as` is `ke-<x>:bundle-<sha12>`, where `<sha12>` is the first 12
  hex characters of the bundle's `git_sha`. A vendor image's `as` is
  `ke-vendor/<name>:<digest12>`, where `<digest12>` is the first 12 hex
  characters of the pinned digest and `<name>` is the last path segment of
  the repository. Given two images with the same `<name>`, `bundle.sh` exits
  non-zero and writes no bundle. The installer never creates or moves a
  `:local` tag. Covered by `test_bundle_json_records_file_ref_as` (fast).
- *Digest pin checked on the build host (R2).* Before saving a vendor image,
  `bundle.sh` checks that its pinned `ref@digest` resolves on the build host;
  given one that does not, it exits non-zero naming the image and writes no
  bundle. After that, the tar hashes in `MANIFEST.sha256` carry the pin. The
  target daemon's image IDs are never compared with the pin.
  `[unit: test_bundle_fails_when_pinned_digest_unresolved]` (fast, stubbed docker)
- *Store-independent install (R2).* After the manifest check passes, the
  installer (bash and PowerShell) loads each tar, reads the one
  `Loaded image ID: ...` or `Loaded image: ...` line, and tags that image
  as the entry's `as`. Given a load that prints no such line, or more than
  one, the installer exits non-zero naming the tar. It never relies on
  `ref@digest` resolving on the target. Works on the classic and the
  containerd image store. There is no image-store prerequisite for
  operators: the installer neither checks nor refuses a target because of
  its image store, and `docs/quickstart.md` asks for no store setting.
  `[unit: test_install_tags_loaded_image_as_bundle_name]` (parametrised:
  ID line / name line / no line / two lines x sh/ps1; stubbed docker) (fast)
- *Compose override (R2).* The installer writes a compose override mapping
  every stack service to its `as` tag, taking the service names from the
  entries' `services` fields. With it applied, the resolved
  compose config names no image by digest and every service image is an
  `as` tag from `bundle.json`. Given a stack service with no `bundle.json`
  entry, the installer exits non-zero naming the service. With the override,
  a missing image fails the launch instead of pulling (spike S1).
  *Amended 2026-10-19 (review B2).* To find the stack's services, the
  installer runs `docker compose config --services` on the copied app
  (with no profile). It uses that output **only to check service coverage**,
  never to write the override. A non-zero exit, empty output, or a line that
  is not a service name is a refusal.
  `[unit: test_install_override_maps_every_service_to_as_tag]`,
  `[unit: test_install_fails_when_service_has_no_bundle_entry]` (fast; one
  case has `compose config --services` exit non-zero);
  launch from the bundle with no pull is proved by `ci/deployable-offline`.
- *Free disk (R6).* `bundle.sh` checks for at least 7 GiB free before it
  writes anything. Below that, it exits non-zero with a message giving the
  required and available space in GiB ("need 7 GiB free ... found <n> GiB",
  the figure found rounded down) and the path, and runs no `docker save`.
  7 GiB is the measured floor (amended 2026-10-20 from a 10 GiB default;
  PS-3.2 *Disk logging*).
  Control: with enough space it proceeds (same test).
  `[unit: test_bundle_fails_below_free_disk]` (fast, stubbed `df`)
- *Tamper cases.* Given a bundle with (a) a changed file, (b) a listed file
  missing, or (c) a file not in the manifest, the installer exits non-zero,
  names the file, and runs no `docker load`. Each case is tested for the bash
  and the PowerShell installer (pwsh is in the gates image).
  `[unit: test_bundle_manifest_rejects_tamper]` (parametrised a/b/c x sh/ps1),
  `[unit: test_install_loads_nothing_when_manifest_fails]` (fast). Control:
  the untouched bundle passes the same check (same test).
- *Manifest hash printed.* `bundle.sh` prints the manifest's own sha256
  for out-of-band comparison (integrity, not authenticity; ADR-KE-012).
  `[unit: test_bundle_prints_manifest_hash]` (fast)

*Unit-2 rework round 1 (2026-10-19; security M-1, M-2, M-3, I-1).* The test
names below are the tester's, from `tests/test_offline_bundle.py`
(reconciled by the architect, 2026-10-19). Install cases run for the bash
and the PowerShell installer. A behaviour marked *no test yet* has no
assertion in that file; it is flagged to the orchestrator.
- *Private staging (M-1).* The installer copies the bundle into a private
  staging directory before it checks anything. The directory has mode 0700
  (on Windows, an ACL for the current user only) and sits in the target's
  parent directory, so it is on the same filesystem. The copy follows no
  link. The manifest check, every `docker load`, the app copy and the
  override all use the staged copy only. Given a bundle file changed after
  the installer started (the fake docker swaps a tar and
  `app/scripts/launch.sh` when it gets `info`), the installer loads and
  installs the bytes it verified. Staging is removed on every exit, whether
  success or refusal. After a refusal, no target exists other than an empty
  one that was already there.
  `[unit: test_install_loads_and_copies_verified_bytes_only]` (cases: bundle
  changed after `info`; hardlink partner changed after `info`),
  `[unit: test_install_does_not_follow_target_planted_during_load]`,
  `[unit: test_install_leaves_no_partial_target]` (fast, stubbed docker).
  *No test yet:* staging mode 0700 and location in the target's parent;
  staging removed on every exit.
- *Manifest hash beside the bundle (M-3).* `bundle.sh` writes
  `<out>.manifest.sha256` beside the bundle directory, not inside it. It
  holds the same hash that `bundle.sh` prints, and it is not listed in
  `MANIFEST.sha256`. Given an existing `<out>.manifest.sha256`, `bundle.sh`
  exits non-zero before any `docker save`.
  `[unit: test_bundle_writes_manifest_hash_beside_bundle]` (fast).
  *No test yet:* the refusal of an existing `<out>.manifest.sha256`.
- *Installer prints and checks the manifest hash (M-3).* After the manifest
  check passes, the installer prints the SHA-256 of the `MANIFEST.sha256`
  it accepted. It also takes `--expect-manifest <sha256>` (bash) or
  `-ExpectManifest <sha256>` (PowerShell). Given a value that differs from
  the staged manifest's hash, it exits non-zero, prints both values, and
  runs no `docker` command. A value that is not 64 hex characters is a
  usage error. Control: the matching value proceeds.
  `[unit: test_install_prints_and_checks_manifest_hash]` (fast; cases:
  prints accepted hash, matching value, mismatch, not hex). *No test yet:*
  the mismatch refusal printing the expected value (the actual one is
  asserted).
- *Trust anchor procedure (M-3; must close before the item closes).*
  `docs/quickstart.md` tells the operator to do the following before running
  anything from the bundle:
  1. Compare the SHA-256 of `MANIFEST.sha256` with the value obtained out of
     band (from `<out>.manifest.sha256`, sent through a channel separate
     from the bundle).
  2. Check `install.sh` or `install.ps1` against its manifest line with
     their own `sha256sum` or `Get-FileHash`.
  3. Run the installer with `--expect-manifest` / `-ExpectManifest`.
  Covered by `test_quickstart_describes_offline_install` (PS-3.2 *Docs*),
  which asserts all three steps.
- *Exact-case paths (M-2).* Both installers compare paths ordinally and
  case-sensitively. Given an unlisted file that differs from a listed file
  only by case (`app/scripts/LAUNCH.sh` beside a listed `launch.sh`), or
  a manifest listing two paths that differ only by case, the installer
  exits non-zero, names the rule, and runs no `docker` command.
  `[unit: test_install_refuses_case_variant_paths]` (fast; the
  listed-collision case is PowerShell only)
- *Windows-safe names (I-1).* Given a manifest path with a segment whose
  stem is a Windows reserved name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
  `LPT1`–`LPT9`, in any case, with or without an extension), or a segment
  that ends in a dot or a space, or one that contains `:`, the installer
  exits non-zero, names the rule, and runs no `docker` command.
  Covered by `[unit: test_bundle_manifest_rejects_tamper]` (fast; cases
  `reserved_name_*`, `trailing_dot`, `colon`). *No test yet:* a segment
  ending in a space.
- *Manifest size cap (L-4; architecture §2.5 step 3, §2.6 item 5a).* The
  installer (bash and PowerShell) checks that the staged `MANIFEST.sha256`
  is a regular file (not a symlink or FIFO) of at most 1 MiB (1,048,576
  bytes) before it reads it. Given a manifest larger than 1 MiB, the
  installer exits non-zero, names `MANIFEST.sha256` and the size rule, and
  runs no `docker` command. Control: a manifest of exactly 1 MiB is not
  refused by the cap.
  `[unit: test_install_refuses_manifest_link_or_fifo]` (fast; sh and ps1;
  cases `manifest_over_1_mib`, `manifest_exactly_1_mib_not_refused_by_cap`,
  beside `manifest_is_symlink` and `manifest_is_fifo`).
- *Stack images only (R7).* The bundle holds the images of the stack
  services and nothing else: not the gates image and not `dind`, which are
  verification tools. `test_bundle_lists_every_compose_image` (fast) checks
  every stack service's image is present, and
  `[unit: test_bundle_holds_stack_images_only]` (fast) checks no other image
  is.
- *No wheels.* No `*.whl` file is in the bundle. `[unit: test_bundle_has_no_wheels]` (fast)
- *Where written (A40).* Under a gitignored `dist/`; a verify run removes its
  own bundle after the check; bundle sizes are recorded in the evidence; a
  bundle from a dirty tree is allowed and `bundle.json` marks it dirty.
  `[unit: test_dist_is_gitignored]`, `[unit: test_bundle_json_marks_dirty_tree]` (fast)
- *Windows (A45).* The PowerShell installer is proven by a recorded run on
  the human's Windows host (Q31/Q34) with a bundle built on a Linux build
  host: tamper rejection, then install and `launch.ps1` from the bundle.
  (manual)

PS-3.1 per-arch bundles (2026-10-19; human rulings Q49, "build it for
both", native arm64 builds on `aria-gb10`; architecture §2.5 *Arch*,
ADR-KE-012). Install cases run for the bash and the PowerShell installer.
- *Two arches.* linux/amd64 and linux/arm64 are both supported, one bundle
  per arch. The arm64 bundle serves Linux arm64 hosts (the GB10s) and
  Apple-silicon Macs, whose Docker Desktop daemon is linux/arm64.
- *Arch normalisation.* `bundle.sh` and both installers read the target
  daemon's `docker info` `Architecture` and normalise it the same way:
  `x86_64` and `amd64` become `amd64`; `aarch64` and `arm64` become
  `arm64`. Given any other value, the script exits non-zero naming the
  value.
  `[unit: test_arch_normalisation]` (fast; sh and ps1; cases `x86_64`,
  `amd64`, `aarch64`, `arm64`, unknown value refused)
- *Arch from the target daemon, natively.* `bundle.sh` bundles for the
  arch of the daemon it talks to (the active `DOCKER_CONTEXT` or
  `DOCKER_HOST`), from the images `build.sh` built and pulled on that same
  daemon. Run against the local daemon, it gives an amd64 bundle; run with
  `DOCKER_CONTEXT=aria-gb10`, an arm64 one. No docker command it runs
  carries `--platform` (spike S1), and it never builds or pulls.
  `--arch amd64|arm64` is optional and only an assertion: given a value
  that differs from the daemon's arch, `bundle.sh` exits non-zero naming
  both and runs no `save`. Any other `--arch` value is a usage error.
  `[unit: test_bundle_arch_comes_from_daemon]` (fast, stubbed docker;
  cases: x86_64 daemon, aarch64 daemon, matching `--arch`, mismatched
  `--arch` refused, bad value),
  `test_bundle_saves_one_tar_per_image_without_platform` (unchanged)
- *Every image has the arch.* Given any image whose `docker image inspect`
  `Os/Architecture` is not `linux/<daemon arch>`, whether one foreign image
  among native ones or all of them, `bundle.sh` exits non-zero naming the
  image and the os/arch it found, and runs no `save`.
  `[unit: test_bundle_refuses_image_of_other_arch]` (fast, stubbed docker;
  cases `mixed`, `all_foreign`, on both an amd64 and an arm64 daemon;
  replaces the `non_amd64` case)
- *Arch recorded.* The `bundle.json` header records `"arch": "amd64"` or
  `"arch": "arm64"` in place of the old `"platform": "linux/amd64"`. The
  `--out` basename must end in `-<arch>`, so the bundle directory, the
  `--tar` archive and the `<out>.manifest.sha256` release record all carry
  the arch. Otherwise it is a usage error before any `save`. The `as` tag
  scheme is unchanged: each arch's images live on their own daemon.
  `[unit: test_bundle_json_records_arch]`,
  `[unit: test_bundle_out_name_carries_arch]` (fast)
- *Install refuses an arch mismatch.* After the manifest check and the
  `docker info` check, and before `compose config` or any `docker load`,
  the installer compares the bundle's `arch` with the normalised daemon
  arch. If they differ, it exits non-zero naming both and loads nothing.
  Control: the same arch proceeds, including `aarch64` against an `arm64`
  bundle.
  `[unit: test_install_refuses_arch_mismatch]` (fast; sh and ps1; cases
  amd64 bundle on aarch64, arm64 bundle on x86_64, control)
- *install.sh on macOS (Q50, in scope 2026-10-19).* `install.sh` runs on
  Linux and on macOS, where `/bin/bash` is bash 3.2 and the userland is
  BSD. It uses no bash 4+ feature and no GNU-only tool form. SHA-256 comes
  from one helper that uses `sha256sum` if present and otherwise `shasum
  -a 256`.
  - `[unit: test_install_sh_uses_no_gnu_or_bash4_constructs]` (fast,
    static). Forbidden in `scripts/install.sh`: `declare -A`, `local -A`,
    `typeset -A`, `declare -n`, `local -n`, `mapfile`, `readarray`,
    `${x,,}`, `${x^^}`, `${x,}`, `${x^}`, `|&`, `&>>`, `;;&`, `coproc`,
    `wait -n`, `globstar`, `mv -T`, `cp -T`, `stat -c`, `stat --`,
    `readlink -f`, `realpath`, `find ... -printf`, `sed -i`, `sed -r`,
    `grep -P`, `sort -z`, `sort -V`, `xargs -r`, `du -b`, `timeout`, `tac`,
    `base64 -w`, `date -d`, a `mktemp` with no `XXXXXX` template, and any
    `sha256sum` or `shasum` call outside the helper.
  - `[unit: test_install_sh_runs_with_bsd_tool_shims]` (fast). This is an
    approximation of macOS, not proof of it. It runs `install.sh` under
    `bash --posix` with a PATH of shims, where `mv`, `cp`, `stat`,
    `readlink`, `find`, `sed`, `sort`, `xargs` and `date` exit 97 on a
    GNU-only option and `sha256sum` is absent, so the `shasum` fallback
    runs. Cases: clean install, one tamper case, arch mismatch.
  - *macOS proof (manual, open item).* A recorded install, launch and
    teardown from an arm64 bundle on the Apple-silicon Mac when it
    arrives. It is not a CI gate.
  - *Q53 extended (orchestrator, round 2, 2026-10-19).* `launch.sh` and
    `teardown.sh` meet the same bash 3.2 and BSD rule, so the Mac operator
    can launch and tear down. The static forbid list applies to
    `install.sh`, `launch.sh` and `teardown.sh`, and also forbids `[[ -v`,
    `${x@...}`, negative array subscripts, `$EPOCHSECONDS`,
    `$EPOCHREALTIME`, `printf '%(...)T'` and a bare `local -` (review P5).
    `smoke.sh`, `net_isolated.sh` and `verify.sh` stay Linux and dev only;
    the Mac proof does not claim smoke.
    `[unit: test_operator_scripts_use_no_gnu_or_bash4_constructs]` (fast,
    static), `[unit: test_launch_and_teardown_run_with_bsd_tool_shims]`
    (fast; `launch.sh` through `compose up`, `teardown.sh --volumes`, and
    a bad argument, under `bash --posix` with the shims)
- *arm64 proof (Q51, resolved 2026-10-19).* The amd64 bundle is proven by
  `ci/deployable-offline` (PS-3.2). The arm64 bundle is proven by a
  recorded run on `aria-gb10` (aarch64, Ubuntu 24.04, Docker 29.6.2),
  reached through a docker context over SSH: `build.sh` and `bundle.sh`
  with `DOCKER_CONTEXT=aria-gb10`, then on `aria-gb10` itself the
  trust-anchor check, `install.sh`, `launch.sh`, `smoke.sh` and teardown.
  The run's output is saved under `docs/evidence/platform-offline/`.
  (manual; an `ubuntu-24.04-arm` CI runner is a later option, not
  required)

PS-3.1 unit-2 rework round 2 (2026-10-19; security H-1, M-4, L-8, L-9,
L-10, I-3, I-5; review RB1, RB2, P1–P7; architecture §2.5 *Entry
hardening*, Install steps 1, 2 and 9; §2.6 item 5c). Install cases run for
the bash and the PowerShell installer unless noted. Test names are the
tester's, from `tests/test_offline_bundle.py`. A behaviour marked *no test
yet* has no assertion in that file; it is flagged to the orchestrator.
- *Staging cannot be swapped after verification (H-1).* After staging is
  created, the installer reaches it only through its working directory and
  relative paths. Given the staging directory renamed away and a
  self-consistent lookalike planted under its name after the manifest
  check (the fake docker does this at `info`), the installer either refuses
  or loads and publishes only the bytes it verified; it never loads the
  lookalike's tars or publishes its files.
  `[unit: test_install_survives_staging_swap_after_verification]` (fast).
  *No test yet:* a static check that no absolute staging path follows the
  `cd` in `install.sh`.
- *Windows staging ACL at creation (H-1).* On Windows, `install.ps1`
  creates staging and the claimed target with a protected ACL (current
  user only, no inherited entry) in the same call that creates them, then
  verifies the owner is the current user and the ACL is exactly that. Any
  other result refuses. It never protects a directory after creating it.
  `[unit: test_install_ps1_creates_windows_staging_with_its_acl]` (fast,
  static: `FileSystemAclExtensions]::Create`, no `Set-Acl`),
  `[unit: test_staging_never_inherits_an_ace]` (Windows host only, under a
  parent granting Authenticated Users Modify; skipped in the gates image),
  and the recorded Windows run (Q31/Q34).
- *Target's parent owned or writable by others: refused (H-1 fix 3;
  amended in round 4, 2026-10-19, by the orchestrator's ruling on security
  H-2, M-5, M-6, L-15 and review RB6; this supersedes the round-2 "warn,
  not refuse").* Both installers, on every platform, refuse a target
  parent that is owned by, or writable by, any principal other than the
  operator, root, or (Windows) SYSTEM or Administrators. Writable means
  group or other write in the mode, with or without the sticky bit (bash
  and pwsh off Windows), an `allow` ACL entry on macOS, or (Windows) an
  Allow ACE that is not inherit-only and grants any create, delete,
  rename, permission or ownership right, including GenericWrite or
  GenericAll. The installer **fails closed**: any error reading the
  owner, mode or ACL is a refusal. A refusal exits non-zero, names the
  parent, the rule and what was found, runs no `docker` command, and
  leaves no claimed target and no staging. Control: a 0755 parent owned
  by the operator installs with no such message; a root-owned 0755
  parent is not flagged.
  `[unit: test_install_flags_target_parent_others_can_write]` (fast; sh
  and ps1 off Windows; modes 0777, 0775, 0770 refused, control 0755),
  `[unit: test_install_sh_flags_parent_owned_by_another_user]` (fast; `id
  -u` shim; refused; root-owned control),
  `[unit: test_install_ps1_refuses_parent_owned_by_another_user]` (fast;
  L-15, off Windows),
  `[unit: test_install_sh_refuses_parent_it_cannot_check]` (fast; fail
  closed when the owner, mode or uid cannot be read),
  `[unit: test_install_ps1_acl_read_failure_is_not_silent]` (fast, static),
  and on a Windows host only
  `[unit: test_parent_granting_authenticated_users_modify_is_refused]`,
  `[unit: test_parent_others_can_create_in_is_refused]`
  (`InstallPs1WindowsAclTest`; skipped in the gates image). *No test
  yet:* a 1777 (sticky) parent refused; the macOS ACL branch (recorded Mac
  run only).
  *Rejected alternative:* warning and continuing (rounds 2–3). Three
  rounds of race fixes each opened a new race (round 3's cleanup emptied
  an operator directory, H-2/RB6; the chmod re-check left a window, M-5);
  refusing the parent removes the attacker's precondition instead.
- *Defence in depth kept (round 4).* Even under an operator-only parent:
  - *Staging pinned only when proven (H-2, RB6, N7).* Nothing chmods
    staging by name. The installer treats staging as pinned, and may
    empty it from inside, only after its working directory's real path
    (`pwd -P`) is the expected staging path, the directory is empty, is
    owned by the operator (`-O .`) and has mode 0700. `install.ps1` sets
    its Pinned flag only after the same assert, and never empties or
    enumerates a reparse point. Given the staging name swapped for a
    link to a non-empty operator-owned 0700 directory before the `cd`,
    that directory keeps every file, the install exits non-zero and runs
    no `docker` command. Given a file appearing in staging right after
    creation, `install.ps1` refuses naming staging before it pins.
    `[unit: test_install_sh_never_empties_dir_swapped_in_for_staging]`
    (fast; victims 0700 and 0755),
    `[unit: test_install_ps1_refuses_non_empty_staging]` (fast), and on a
    Windows host `[unit: test_staging_junction_to_operator_dir_is_never_emptied]`.
  - *Publish from inside the target (M-5).* The target is made 0755 by
    `cd` into it, a check of the claim marker and owner, removing the
    marker, `chmod 0755 .`, and a check that the target name still leads
    to that directory. Given the target swapped for a link to a 0700
    victim after the marker is removed, the victim stays 0700 and the
    install exits non-zero. The same holds when the swap happens at the
    `chmod` itself.
    `[unit: test_install_sh_never_chmods_a_target_swapped_at_publish]`,
    `[unit: test_install_sh_refuses_target_swapped_for_link_before_chmod]`,
    `[unit: test_install_ps1_rechecks_target_is_dir_right_before_chmod]`
    (fast)
  - *Windows rights mask from integers (M-6).* The write mask is built
    from integer constants, never by casting an undefined
    `FileSystemRights` value, and an exception while reading the ACL
    refuses. `[unit: test_install_ps1_never_casts_undefined_rights]`,
    `[unit: test_install_ps1_counts_generic_write_rights]` (fast, static)
    plus the Windows-host refusals above.
  - *Next step printed (N6).* `install.sh` prints `next: cd <target> &&
    bash scripts/launch.sh`.
    `[unit: test_install_sh_next_line_runs_launch_with_bash]` (fast)
- *Target claimed first (L-8).* Before any `docker` command, the installer
  claims the target as an empty 0700 directory with an exclusive create
  that does not follow a final symlink (an existing empty target is
  removed first), and marks it with a random claim file. It publishes by
  renaming each staged `app/` entry into the claimed target, removes the
  claim file and makes the target 0755 as the last step (on Windows, the
  target keeps its current-user ACL). Given the target removed and
  replaced by a directory or a symlink during load, the installer refuses,
  writes nothing into the planted directory or through the link, and
  leaves no staging. After a failed install, the claim is gone and no
  target exists other than an empty one that was already there.
  `[unit: test_install_claims_target_before_docker]`,
  `[unit: test_install_refuses_target_replaced_during_load]` (fast).
  *No test yet:* the final 0755 mode and the claim file's removal.
- *Interrupt sent to the installer alone (L-10, RB1).* Given SIGTERM or
  SIGHUP sent only to the installer's process (not its group) while
  `docker load` runs, the installer stops at the next step, exits
  non-zero with a status of its own, and leaves no target and no staging.
  `install.ps1` run in-process in an open session returns a non-zero
  status after the interrupt, a second run in that session succeeds (its
  interrupt flag is reset), and once it has returned the session no longer
  ignores SIGTERM (its signal handlers are disposed).
  `[unit: test_install_stops_on_signal_to_its_own_pid]`,
  `[unit: test_install_ps1_session_recovers_after_signal]` (fast)
- *Installer edited while it runs (M-4).* Given a command appended to the
  bundle's installer while it runs (the fake docker appends it at `info`),
  the command does not run. `install.sh` ends with the single line
  `main "$@"; exit`, so bash has parsed all of it before running any of it.
  `[unit: test_install_ignores_script_changed_during_run]` (fast)
- *Absolute PATH only (L-9).* Given a `PATH` with an empty entry (a
  leading, trailing or doubled `:`), `.` or a relative entry, `install.sh`
  exits non-zero naming PATH and the rule before running any external
  command, so a program of that name in the bundle root never runs, and
  runs no `docker` command. `install.ps1` refuses a relative entry; on
  Windows it ignores empty entries.
  `[unit: test_install_sh_refuses_relative_or_empty_path_entries]` (fast).
  *No test yet:* the `install.ps1` PATH rule.
- *PowerShell 7.3 (RB2b).* `install.ps1` declares `#Requires -Version 7.3`.
  ConstrainedLanguage mode is not supported and the quickstart says so.
  `[unit: test_install_ps1_requires_pwsh_7_3]` (fast, static)
- *Exec bits recorded (RB2c).* `scripts/bundle.sh`, `scripts/install.sh`,
  `scripts/launch.sh` and `scripts/teardown.sh` have mode 100755 in the git
  index.
  `[unit: test_operator_scripts_are_executable_in_git]` (fast)
- *Case collisions named (review P2, security I-3).* Given a bundle file
  that differs from another only by case, `install.sh` refuses it by the
  case rule, naming the path, before copying, on any filesystem; it copies
  without `cp -n`.
  `[unit: test_install_sh_names_case_rule_for_present_case_variant]` (fast)
- *Piped checks exit explicitly (security I-5).* Every `... | { ...; }`
  group in `install.sh` ends `} || exit 1` (or `|| die`).
  `[unit: test_install_sh_piped_checks_exit_explicitly]` (fast, static)

PS-3.2 additions (`ci/deployable-offline`):
- *Which arch it proves (2026-10-19).* `ci/deployable-offline` bundles and
  installs for the local daemon's arch, so on the `ubuntu-24.04` CI runner
  it proves the amd64 bundle. The arm64 bundle's proof is the PS-3.1
  *arm64 proof* criterion (Q51).
- *Wired into full.* `verify.sh full` runs the offline check, and its
  non-zero exit fails the run. `[unit: test_verify_full_runs_offline_check]` (fast)
- *Clean daemon precondition.* Before install, the check asserts the inner
  daemon lists no images, and that a registry pull from it fails. If
  either assertion fails, the gate fails as *inconclusive*, never as passed.
  (full, part of `ci/deployable-offline`; `[unit: test_offline_check_asserts_clean_daemon]` (fast, stubbed docker))
- *No privileged daemon is a blocker.* Given a daemon that refuses the
  privileged `dind` container, the check exits non-zero with a message
  naming the blocker. It never prints a pass or a skip.
  `[unit: test_offline_check_fails_without_privileged_daemon]` (fast, stubbed)
- *Nothing left behind.* After the check (pass or fail), no `ke-offline-*`
  container, network or volume remains on the host daemon. (full, asserted by
  the check's trap; `[unit: test_offline_check_tears_down_on_failure]` (fast, stubbed))
- *Inner daemon (spike S1, S3; ruling "rulings from spikes").* The `dind`
  daemon the check uses runs the containerd image store, is reachable on its
  network under the alias `docker` (the name its TLS server certificate
  covers), and the client container mounts only the `client` subpath of the
  certs volume, read-only; the `ca/` directory is never mounted. Any
  isolated inner network the check creates is `--internal`. Before install,
  the check asserts the inner daemon reports the containerd store; otherwise
  the gate fails as *inconclusive*. The containerd store is a property of
  this check's daemon only, not an operator prerequisite (R2).
  `[unit: test_offline_dind_uses_containerd_store]`,
  `[unit: test_offline_dind_has_network_alias_docker]`,
  `[unit: test_offline_client_mounts_only_client_certs_read_only]`,
  `[unit: test_offline_inner_networks_are_internal]` (fast, compose or script
  config)
- *No pull happened (orchestrator ruling on the architect's spikes
  amendment, 2026-10-19).* After teardown, the check compares the set of
  `repository:tag` names in the inner daemon (only fully dangling
  `<none>:<none>` entries excluded) with the set of `as` values in
  `bundle.json`. Image IDs are never compared (they differ by image
  store). A `repository:<none>` entry counts as an extra name, because a
  digest-pinned pull lists that way on the containerd store (architecture
  §2.5 client step 6; review B1, security M-OCa). Given the two sets differ
  (a name missing, or an extra name), the gate fails and names the
  differing tags; given they are equal, this step passes.
  `[unit: test_offline_check_fails_when_tag_set_differs_from_as_set]`
  (fast, stubbed docker; parametrised extra / extra `repository:<none>` /
  missing; control: equal sets pass, with or without a `<none>:<none>`
  entry), and `ci/deployable-offline` (full).
- *Free disk (R6).* `offline_check.sh` checks for at least 7 GiB free before
  its first stage (amended 2026-10-20 from 10 GiB). Below that it exits
  non-zero with a message giving the required and available space; it is reported as a failure, never a skip
  or a pass. Control: with enough space it proceeds.
  `[unit: test_offline_check_fails_below_free_disk]` (fast, stubbed `df`)
- *Disk logging (R6).* The check prints `df` output for the disk it uses
  before and after each offline stage, so the first CI run measures the
  real footprint. That measurement and the 10 GiB default are recorded in
  `docs/evidence/platform-offline/`. *Measured 2026-10-20 (CI run
  39359710258, `ci-39359710258.log`):* the GitHub ubuntu-24.04 runner had
  9.1 GiB free on `/` at the offline stage and failed the 10 GiB default.
  The offline stages add the bundle (941 MiB amd64; 2.4 GiB arm64 on its
  native build host) plus the `dind` store (about 3.3 GiB), about 4.3 GiB;
  with about 60% headroom the floor is 7 GiB in both `bundle.sh` and
  `offline_check.sh` (orchestrator ruling, architecture §2.5 R6).
  `[unit: test_offline_check_logs_disk_around_each_stage]` (fast, stubbed)
- *Docs (amended 2026-10-19, "build it for both").* `docs/quickstart.md`
  gives two install paths, in this order:
  1. **Code-first (primary):** clone, `scripts/build.sh`, then
     `scripts/launch.sh` (or the `.ps1` twins). It builds for the host's
     own arch and needs internet at build time.
  2. **Offline bundle (air-gap):** choosing the arch (`amd64`, or `arm64`
     for the GB10s and an Apple-silicon Mac); building and bundling on a
     daemon of that arch (`scripts/build.sh` then `scripts/bundle.sh --out
     dist/<name>-<arch>`, with `DOCKER_CONTEXT` naming an arm64 daemon such
     as `aria-gb10` for arm64); the three trust-anchor steps (security
     M-3, PS-3.1); the umask note (review N9); and installing with no
     network using bash (Linux and macOS) or PowerShell.
  *Round 2 (2026-10-19; security quickstart gaps a–e, review RB2, P6).*
  The offline path also tells the operator to:
  - copy the bundle off removable media, a share, or any place another
    account can write, into a directory only they can write, before the
    trust-anchor steps (M-4);
  - on a Mac, check the installer with `shasum -a 256 -c MANIFEST.sha256`;
  - run `bash ./install.sh ...` (and `bash scripts/bundle.sh ...`), not
    `./install.sh`, with a `PATH` of absolute directories only (L-9);
  - choose a target whose parent only they can write and that has room for
    the whole bundle, for example under their home directory; the examples
    never use `C:\` or `/opt` as a non-root user, or `/tmp` on macOS;
  - *(round 4, 2026-10-19)* the target's parent must be owned and writable
    only by them (or root / Administrators); the installer refuses
    otherwise, including a sticky `/tmp`-style parent and `C:\`;
  - on Windows, run `pwsh -NoProfile -File .\install.ps1 ...` with
    PowerShell 7.3 or later; Windows PowerShell 5.1 and ConstrainedLanguage
    mode are not supported;
  - and it notes that Finder `.DS_Store` / `._*` files and OneDrive
    placeholders make the bundle fail its check, that `bundle.sh` needs a
    Linux build host (bash 4, GNU tools), and that the Mac can install,
    launch and tear down but not run `smoke.sh` (Q53).
  `[unit: test_quickstart_describes_offline_install]` (fast; asserts the
  three M-3 steps, `DOCKER_CONTEXT`, `-<arch>`, the umask note and a macOS
  install with bash),
  `[unit: test_quickstart_offline_commands_run_as_written]` (fast; `pwsh
  ... -File ...install.ps1`, `bash ./install.sh`, `bash scripts/bundle.sh`,
  `shasum -a 256 -c`, and no code-block command that runs `./install.sh`,
  `.\install.ps1` or `scripts/bundle.sh` directly),
  `[unit: test_quickstart_offline_safety_notes]` (fast; the copy-first
  step, the operator-only parent, the Linux build host),
  `[unit: test_quickstart_target_not_directly_under_c_or_opt]` (fast; an
  example target directly under `C:\` or `/opt` only with the
  operator-only-parent note above it).
  *No test yet:* the absolute-`PATH` advice, PowerShell 7.3 / no
  ConstrainedLanguage, the `.DS_Store`/OneDrive note, "no smoke on the
  Mac", and the round-4 wording that the installer refuses (not warns
  about) a parent others own or can write.
  `[unit: test_quickstart_code_first_comes_first]` (fast; the clone,
  `build.sh`, `launch.sh` path appears before the first `bundle.sh`)

PS-3.3 additions (`ci/offline`):
- *Both app containers probed.* The probe runs from `api` and from `worker`,
  each against the same non-allowlisted target, and each must fail.
- *Control probe.* The same probe from a throwaway `ke-app` container on
  `edge` must succeed; if it fails, the gate fails as *inconclusive*.
  `[unit: test_offline_probe_fails_when_control_fails]` (fast, stubbed),
  `[gate: ci/offline]` (full). Target: A46.
- The other services are covered at network level by
  `test_only_gateway_on_edge_network` (PS-2.10) and `test_gates_it_has_no_route_out`.

PS-3.4 addition (re-measure): the current value is 10 minutes (389 s on
42547d0; `docs/evidence/platform-stack-ready/ci-timeout.md`). The offline check
adds a bundle, a load into DinD, a second launch and a second smoke, so 10
minutes may not be enough. Ruling R5 (A44): the commit that adds the offline
stages to `verify.sh full` sets `timeout-minutes` to 20. The first green CI
run that includes `ci/deployable-offline` then sets it to that run's
measured duration plus 50%, rounded up to a whole minute, in a follow-up
commit on the branch, with the run's log and arithmetic saved in
`docs/evidence/platform-offline/`. The local `full` elapsed time is also recorded. If it is over about 15
minutes, that goes to the orchestrator (F5). `test_ci_job_has_timeout` (fast)
is unchanged.

*R5 amended 2026-10-20 (orchestrator, CI run 39359710258):* the first CI run
with the offline stages reached them about 16 minutes in (unit tests 770 s on
the 2-core runner, against about 280 s locally), so 20 minutes would not fit
the run. `timeout-minutes` is 30 for the measurement run; the first green run
then sets it to measured plus 50% as above. The slow CI unit tests are a
follow-up outside this criterion (candidate: run test modules in parallel).

- **PS-3.5 Gate services least privilege (security L-5).** Both gate
  services, `gates` and `gates-it`, run as a non-root user, see the
  repository read-only with `/tmp` as the only writable path, and cannot
  read the repo-root `.env`. This closes the filesystem half of A35(c).
  Ruling R7: L-5 applies to both services through their shared definition;
  this replaces the earlier exclusion of `gates`. Each test below is
  parametrised over both services.
  `[unit: test_gates_it_is_non_root_with_read_only_repo]` (fast, compose
  config), `[integration: test_gates_it_cannot_write_repo]` (a write to the
  repo root and to `.git/hooks` fails), `[integration: test_gates_it_cannot_read_repo_env]` (full).
  Control: a write to `/tmp` succeeds (same test).
  The spike S2 specifics (`docs/evidence/platform-offline/spikes.md` § S2):
  - *Non-root uid.* Both services run as uid 10001.
    `[unit: test_gate_services_run_as_uid_10001]` (fast, compose config)
  - *Read-only checkout.* The repository mount is read-only in both
    services, and no other bind mount is writable.
    `[unit: test_gate_services_mount_repo_read_only]` (fast, compose config)
  - *Executable tmpfs.* `/tmp` is a tmpfs mounted with `exec` and mode 1777
    (tests run copied scripts from it; a `noexec` tmpfs failed 197 tests in
    S2). `[unit: test_gate_services_tmp_is_exec_tmpfs]` (fast, compose config)
  - *Image-owned venv and uv cache.* In the gates image, the uv cache is at
    a fixed path inside the image (not under a home directory) and it and
    `/opt/venv` are owned by uid 10001.
    `[unit: test_gates_image_venv_and_uv_cache_owned_by_gate_user]` (fast,
    Dockerfile). As uid 10001 with no network, `uv run --locked` passes on
    the committed lock, and fails when `pyproject.toml` drifts from
    `uv.lock` (control and drift case).
    `[integration: test_gates_uv_locked_catches_drift_as_non_root]` (full)
  - *Caches off the checkout.* Both services set
    `MYPY_CACHE_DIR=/tmp/mypy`, `PYTHONDONTWRITEBYTECODE=1` and
    `GIT_OPTIONAL_LOCKS=0`. `[unit: test_gate_services_env_for_read_only_repo]` (fast)
  - *Coverage data file.* `pyproject.toml` sets `data_file = "/tmp/.coverage"`
    under `[tool.coverage.run]`, and `COVERAGE_FILE` is set nowhere in the
    compose files, Dockerfiles, `scripts/` or the CI workflow (the env var
    leaks into nested coverage runs; S2 item 4).
    `[unit: test_coverage_data_file_is_under_tmp]`,
    `[unit: test_coverage_file_env_is_never_set]` (fast)
  - *No `UV_NO_SYNC`.* `UV_NO_SYNC` is set nowhere in the compose files,
    Dockerfiles, `scripts/`, `.env.example` or the CI workflow; it hides lock
    drift (S2 item 5). `[unit: test_uv_no_sync_is_never_set]` (fast)
  - *Git on CI.* If the CI checkout's owner differs from uid 10001 and git
    refuses it, the fix is a `safe.directory` setting inside the gate
    services, never a writable checkout. Unmeasured; settled by the first
    CI run (no separate test; `verify.sh full` on CI proves it).
  - *Proof.* `scripts/verify.sh fast` and `full` pass with these settings
    (the gates themselves run under them).
- **PS-3.6 Image scan (security L-13; orchestrator ruling 2026-10-19).**
  *Moved to `platform-supply-chain` (split ruling and R3, 2026-10-19);
  `platform-offline` has no scan stage. Q41 resolved, Q42 open there.*
  `verify.sh full` scans the `ke-app` image with trivy or grype. The scanner
  is pinned by version and digest. A finding at or above the threshold fails
  the run, and the full report is saved under `docs/evidence/<slug>/`.
  - `[unit: test_image_scanner_is_pinned]` (fast)
  - `[unit: test_verify_full_fails_when_image_scan_fails]` (fast, stubbed
    scanner exit)
  - `[gate: image-scan]` (full)
  - Accepted findings are listed in a committed exceptions file, each with
    a reason; security reviews that file.
  - Threshold, the vendored psycopg-binary libraries, and scope: Q42, Q43.
    Vulnerability DB: Q41.
  - The scanner and its DB are not part of the bundle; the deployed product
    never scans.
- **PS-3.7 Gates image supply chain (security L-8, review rework-1 N-7).**
  *Moved to `platform-supply-chain` (split ruling, 2026-10-19).*
  PSScriptAnalyzer is installed from a package whose sha256 is pinned and
  checked before install (no install from a trusted PSGallery by version
  alone). `POWERSHELL_TELEMETRY_OPTOUT` is set before the first instruction
  that runs pwsh. `[unit: test_gates_image_verifies_psscriptanalyzer_hash]`,
  `[unit: test_gates_image_sets_telemetry_optout_before_pwsh]` (fast). The
  build in `verify.sh full` proves the pinned hash matches. The reviewer
  checks that a wrong hash fails the build (mutation).
- **PS-3.8 Licence notices (orchestrator ruling on psycopg LGPL, 2026-10-19).**
  The `ke-app` image keeps the licence files of its installed Python
  distributions, including psycopg's LGPL-3.0 text. The bundle carries a
  third-party notices file listing each runtime package from `uv.lock` with
  its licence, generated at bundle time and not committed.
  `[unit: test_bundle_has_third_party_notices]` (fast; every runtime package
  in `uv.lock` appears).
  - *Licence check in the generator (R7).* The bundle-time notices generator
    takes each runtime package's licence from the `ke-app` image being
    bundled. Given a runtime package whose licence file is not in that
    image, `bundle.sh` exits non-zero naming the package and writes no
    bundle. This replaces the separate
    `test_app_image_keeps_psycopg_licence`.
    `[unit: test_notices_fail_when_package_licence_missing]` (fast,
    parametrised with psycopg's licence removed; control: the full set
    passes). The real image is checked each time `ci/deployable-offline`
    builds a bundle (full).
  - *Third-party images (A43, R4).* The notices list every third-party stack
    image in `bundle.json` by name, pinned reference and licence. Neo4j
    Community is listed as GPL-3.0 with an `https` source URL.
    `[unit: test_notices_list_every_stack_image_with_licence]`,
    `[unit: test_notices_neo4j_has_source_url]` (fast)
  - *Phoenix exception (human Q43, 2026-10-19).* Arize Phoenix is a documented
    exception to "open-source components only". The notices list it with its
    licence and mark it as that exception, citing the human ruling.
    `[unit: test_notices_mark_phoenix_as_exception]` (fast). Security confirms
    the licence text at the pinned digest (manual, security audit).
- **PS-3.9 Image tags and rebuilds (review round-0 N6, N8).**
  - *N6.* A `verify.sh full` run does not move any image tag that the live
    stack's compose resolves to. Verify-built images carry a per-project or
    per-run tag. `[unit: test_verify_does_not_retag_live_images]` (fast,
    compose config with and without the verify overlay)
  - *N8.* `docker/app.Dockerfile` installs locked dependencies before it
    copies the engine code, so a code-only change reuses the dependency
    layer. `[unit: test_app_dockerfile_syncs_deps_before_code]` (fast)
- **PS-3.10 Pinned Docker CLI in the gates image (architecture §2.2 Lint,
  §2.6 item 8; orchestrator ruling 2026-10-19).** `offline-client` runs on
  the gates image and needs the Docker CLI and the compose plugin (spike S3
  found neither). The gates image installs both from static release
  binaries at a pinned version, fetched by URL and checked against a
  SHA-256 committed in the repo, the same control as the pwsh tarball.
  - *Pinned and hash-checked.* Given `docker/gates.Dockerfile`, then for the
    Docker CLI and for the compose plugin: the version is a fixed value (no
    `latest`, no range); the download URL contains that version; a 64-hex
    SHA-256 is committed for each architecture the image builds for (amd64
    and arm64, as for pwsh); and the downloaded file goes through
    `sha256sum -c` before it is unpacked or installed, in the same
    fail-fast step. `[unit: test_gates_image_pins_docker_cli_by_hash]`,
    `[unit: test_gates_image_pins_compose_plugin_by_hash]` (fast, Dockerfile)
  - *Compose version.* The pinned compose plugin version is 2.24 or later
    (the `offline-client` compose features, §2.5).
    `[unit: test_gates_image_compose_plugin_at_least_2_24]` (fast)
  - *No other install route.* The Dockerfile installs no Docker package from
    apt or a Docker package repository, and pipes no download into a shell
    (no `get.docker.com`, no `curl … | sh`).
    `[unit: test_gates_image_installs_docker_only_from_pinned_binaries]` (fast)
  - *Client only in the gate services.* `gates` and `gates-it` set no
    `DOCKER_HOST` and mount no Docker socket; only `offline-client` points at
    `dind` (that half is in `test_compose_offline_services`).
    `[unit: test_gate_services_have_no_docker_host]` (fast, compose config)
  - *Mismatch fails the build.* With a wrong committed hash the image build
    exits non-zero and no image is produced. The reviewer checks this by
    mutation (as PS-3.7). The real hashes are proven by the image build in
    `verify.sh full`, and the binaries by `ci/deployable-offline`, where
    `offline-client` uses them.
  - *Hash provenance.* Each committed hash is computed from the downloaded
    file and cross-checked against a checksum the upstream publishes for
    that release where one exists; the developer records both, or the lack
    of an upstream checksum, in the handoff. Ruled by Q48 (orchestrator,
    2026-10-19; recorded in `docs/handoffs/archive/platform-offline-part1.md`):
    where upstream publishes a checksum (the compose plugin `.sha256`), the
    pin must equal it. Where upstream publishes none (the Docker static CLI
    tarball), a hash from an HTTPS fetch from `download.docker.com` is
    accepted on trust-on-first-use, and on every version bump security
    confirms it with an independent second fetch. The first such
    confirmation is `docs/evidence/platform-offline/audit-cli.md` §1
    (Docker CLI 29.9.1).

**Carry-in placement (analyst, 2026-10-19):**

| Carry-in | Here? | Where |
|---|---|---|
| security L-5 | yes | PS-3.5 |
| security L-8; review rework-1 N-7 | moved (split ruling) | PS-3.7, `platform-supply-chain` |
| ke-app image scan (L-13 follow-up, ruling 2026-10-19) | moved (split ruling) | PS-3.6, `platform-supply-chain` |
| psycopg licence notices | yes | PS-3.8 |
| review round-0 N6, N8 | yes | PS-3.9 |
| ADR-KE-012 manifest signing | no | flagged to security; no target item (authenticity out of scope) |

**Size and proposed split (analyst; the orchestrator decides).** About 30
named tests, plus a new Windows run (Q34: new PowerShell scripts and
Dockerfile changes). That is larger than 2b. The image scan is the one part
that can go red for reasons outside this repository, through the
vendored libraries (Q42). Proposed split, in this order:
1. `platform-offline`: PS-3.1–PS-3.5, PS-3.8, PS-3.9 and the PS-3.4
   re-measure. This meets the shipping rule.
2. `platform-supply-chain`: PS-3.6 and PS-3.7, which re-measure PS-3.4 if
   the scan adds a minute or more.

Both change a Dockerfile, so each needs its own Windows run under Q34. If
the orchestrator keeps one branch, the suggested TDD order is PS-3.9 →
PS-3.1 → PS-3.5 → PS-3.2 → PS-3.3 → PS-3.8 → PS-3.7 → PS-3.6 → PS-3.4.

*Split accepted (orchestrator, 2026-10-19).* This branch builds PS-3.1–PS-3.5,
PS-3.8, PS-3.9 and the PS-3.4 re-measure, in the TDD order PS-3.9 → PS-3.1 →
PS-3.5 → PS-3.2 → PS-3.3 → PS-3.8 → PS-3.4. It has no scan stage. PS-3.6 and
PS-3.7 are built in `platform-supply-chain`, which re-measures PS-3.4 if
they add a minute or more.

Tags summary for `platform-offline`. Fast: every `unit:` test in PS-3.1–PS-3.5,
PS-3.8, PS-3.9 and PS-3.10. Full: `ci/deployable-offline` (which also runs the notices
licence check against the real `ke-app` image), `ci/offline`,
`test_gates_it_cannot_write_repo`, `test_gates_it_cannot_read_repo_env`,
`test_gates_uv_locked_catches_drift_as_non_root`. Manual: the Windows
install run, security's Phoenix licence confirmation and the reviewer's
PS-3.4 check. `image-scan` and the PS-3.7 checks belong to
`platform-supply-chain`. Gate: `scripts/verify.sh full`.

*Q47 (new, does not block RED).* No gate installs the bundle on a
classic-store daemon: the CI `dind` uses the containerd store, and the
Windows host does too (spike S1). The classic-store path rests on the
stubbed installer tests and spike S1. See `docs/open-questions.md`.

### Open questions for this item

Questions raised in the analyst review of 2026-10-18; rulings by the
orchestrator the same day. Full text and numbering in `docs/open-questions.md`
§ "platform-skeleton" (Q19–Q30).

Raised 2026-10-19 for `platform-offline`. Resolved the same day
(orchestrator rulings; Q43 by the human): **Q40** bundle location, size and
dirty trees; **Q41** scanner vulnerability DB (applies to
`platform-supply-chain`); **Q43** scan and licence scope beyond `ke-app`
(Phoenix a documented exception); **Q44** CI timeout before the first
measured run; **Q45** Windows proof of the PowerShell installer; **Q46** the
`ci/offline` probe target. Still open, for `platform-supply-chain`:
**Q42** scan threshold and the vendored psycopg-binary libraries. Open, does
not block RED: **Q47** no gate covers a classic-store install.

Open (raised 2026-10-19 for `platform-stack-ready`; does not block the RED
step, has a stated assumption): **Q37** whether the PS-2.8 store stop/start
runs against a pre-existing project.

Open (raised 2026-10-19, rework round 1 of `platform-stack-ready`):
**Q39** where the auth-audit carry-in 7 (Valkey network + auth) is
scheduled, given ingest-ledger precedes auth-audit in this document. Q38,
raised in the same round (the default models were missing on
`aria-gb10-2`), was resolved by the human's ruling of 2026-10-20; see item
model-roles.

Rework round 1 (orchestrator, 2026-10-19,
`docs/handoffs/platform-stack-ready.md` "rework round 1 of 5"): F1 and L-13
in PS-2.5, M-1 engine side in PS-2.6, R-B3 in PS-2.8, the Q34 scope ruling
in PS-2.9, L-11 in PS-2.21, L-12 in PS-2.23; M-1 network side is auth-audit
carry-in 7.

Resolved (raised and ruled 2026-10-19 for `platform-stack-ready`,
`docs/handoffs/platform-stack-ready.md` "orchestrator: rulings on analyst
plan" and "rulings on architect plan"): **Q35** caller env wins, repo-root
`.env` only, "no other key" covers env and compose args until
platform-offline (PS-2.21); **Q36** CI stays at 20 min until 2b's first
green CI run, then measured + 50% (PS-3.4 in 2b, ruling C1).

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
  carried as Q31. *Narrowed 2026-10-19:* per-arch bundles (Q49) and
  `install.sh` on an Apple-silicon Mac (Q50) are in scope (PS-3.1).
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

## Item: model-roles

Outcome metric moved: neither directly. It points every model role at a
model that is installed on the model host, which any draft a reviewer can act
on depends on. It comes next because Q38 had to be settled "before the first
item that composes a draft".

Source: human ruling, 2026-10-20 (`docs/handoffs/model-roles.md`,
"orchestrator: item opened"; `docs/handoffs/archive/platform-offline.md`).
It resolves Q38 and amends the model-default sentence of PS-1.2 and A7. Scope
is config, the tests and docs that name models, and one recorded run. Nothing
else changes: the per-pass settings shape (DR29, one block per pass with no
inheritance), the egress guard (PS-1.3, PS-1.4), the gateway's model forward,
the skip rule (PS-2.7, PS-2.21) and the endpoint ruling (`aria-gb10-2:11434`,
allowlist host `aria-gb10-2`) all stay as they are. Criteria are `MR-<n>`.

| Role (pass) | `model` | Other keys in the block |
|---|---|---|
| compose | `qwen3.5:latest` | `fallback_model: gpt-oss:20b` (Q54 ruling); `timeout_s: 120` unchanged (Q55) |
| rewrite | `qwen3.5:latest` | `fallback_model: gpt-oss:20b` (Q54 ruling); `timeout_s: 120` unchanged (Q55) |
| audit | `gpt-oss:120b` | `fallback_model: gpt-oss:20b` (Q54 ruling); `timeout_s: 120` unchanged (Q55) |
| embed | `nomic-embed-text` | `dim: 768`, `timeout_s: 60` unchanged |

- **MR-1 Role defaults in config.** Given `config/defaults.yaml` and no
  `KE_MODELS__*` override, when the settings load, then `models.compose.model`
  and `models.rewrite.model` are `qwen3.5:latest`, `models.audit.model` is
  `gpt-oss:120b`, `models.embed.model` is `nomic-embed-text` and
  `models.embed.dim` is 768. Each block's `base_url` is still null. The test
  checks all four roles, not only compose and embed as it does today. Given
  `KE_MODELS__AUDIT__MODEL` set to a marker value, then `audit.model` is the
  marker and compose, rewrite and embed keep their defaults (no inheritance
  between roles, DR29). `[unit: test_model_role_defaults]` (fast; the tester
  can do this by extending `test_config_defaults_and_env_override` instead)
- **MR-2 Fallback model (Q54 ruled 2026-10-20 by the orchestrator; the
  human may change it).** Given `config/defaults.yaml` and no
  `KE_MODELS__*` override, when the settings load, then
  `models.compose.fallback_model`, `models.rewrite.fallback_model` and
  `models.audit.fallback_model` are each `gpt-oss:20b` (installed on
  `aria-gb10-2`, distinct from every primary). The key stays a required
  string, so there is no schema change, and the embed block still has no
  `fallback_model`. `gpt-oss:20b` is a declared model value, so MR-3's
  scan requires it in config and flags it outside the PS-1.2 locations.
  No code reads the key (a fallback mechanism stays out of scope).
  `[unit: test_model_role_defaults]` (fast)
- **MR-3 The scanner knows the new names.** `test_no_hardcoded_hosts_or_models`
  requires `qwen3.5:latest`, `gpt-oss:120b` and `nomic-embed-text` to be
  declared in config. It flags each of them in product source, compose files
  and scripts outside the PS-1.2 locations, and it no longer requires the
  retired names. `test_planted_model_name_is_flagged` plants a current role
  name (for example `gpt-oss:120b` in a script) and sees it flagged.
  `[unit: test_no_hardcoded_hosts_or_models]`,
  `[unit: test_planted_model_name_is_flagged]` (fast)
- **MR-4 Retired names gone from living files.** Given the repository,
  excluding history (`docs/handoffs/**` including the archive,
  `docs/evidence/**`, `docs/log.md`, published `CHANGELOG.md` entries, and the
  build prompt `docs/knowledge-engine-claude-code-prompt.md`), when it is
  searched for `qwen2.5:14b-instruct` and `llama3.1:8b`, then the only hits are
  in text that is explicitly marked as superseded or kept for the record, or
  that records the retirement itself. That is exactly: the PS-1.2 superseded
  note; the original wording of A7 and Q38 in `docs/open-questions.md`; the
  text of Q54/A54 (in `docs/open-questions.md` and this item's open-questions
  summary); MR-4's own text; and the ADR-KE-014 context in
  `docs/architecture.md`. Any hit outside that list fails MR-4. The recorded
  grep of 2026-10-20 gives 12 matching lines, all inside the list (an
  occurrence count with `grep -o` gives 16, because some lines name both
  retired names). The files to update
  are `config/defaults.yaml`, `tests/test_engine_config.py`,
  `tests/test_engine_hardcoded.py` (including the planted-name fixture),
  `docs/architecture.md` §2.4 (the `defaults.yaml` layout block),
  `docs/requirements.md` PS-1.2, and `docs/open-questions.md` A7 and Q38. The
  last two are done in this item's analyst step. `llama3.1:8b` does not stay:
  Q54 ruled the fallback `gpt-oss:20b` (A54), so `llama3.1:8b` is a retired
  name like `qwen2.5:14b-instruct`. `README.md` and the quickstart name no model
  today (grep, 2026-10-20), so neither changes.
  `[gate: recorded grep]` (`docs/evidence/model-roles/retired-names-grep.txt`
  holds the command and its output)
- **MR-5 Recorded run: each role answers through the gateway.** Given
  `KE_MODEL_UPSTREAM=aria-gb10-2:11434` and `KE_EGRESS_ALLOWLIST=aria-gb10-2`
  (the Q38 endpoint ruling), and `aria-gb10-2` reachable, when
  `scripts/verify.sh full` runs, then:
  - *Readiness.* `test_readyz_reports_reachable_model_host` runs and passes.
  - *Chat roles.* For each of compose, rewrite and audit, one model-calling
    integration test sends a short chat completion through
    `ModelClient(settings, <role>)`. That means the role's configured `model`
    and `base_url` are used and the egress guard is in the path. The test gets
    HTTP 200, the response's `model` names the role's configured model, and
    `choices[0].message.content` is non-empty.
  - *Embed role.* One model-calling integration test asks for an embedding
    with the embed role's configured model, through the embed role's
    `base_url` on the same guarded client path. It gets HTTP 200 and one
    vector whose length equals `models.embed.dim` (768).
  - *Through the gateway forward.* Each of these tests asserts that the
    role's `base_url` host is the stack's `gateway` service (set by compose
    as `KE_MODELS__<PASS>__BASE_URL`). No test addresses `aria-gb10-2`
    directly.
  - *Ran, not skipped.* In this run none of the model-calling tests skips.
    The evidence lists each one by name as `ok`. If the host is unreachable
    when the item closes, the tester reports that to the orchestrator; a
    skip never stands in for the run (as in PS-2.21).
  - *Unset still skips.* Each new test is marked `@model_calling` and calls
    `require_model_host` first. Without the two keys (CI, `verify.sh fast`),
    it skips with PS-2.7's "not configured" reason and the run passes.
    `test_stack_model_skip` stays green unweakened.
  - *Traced.* The chat calls are already LLM spans (`model.<role>`). If the
    embedding request goes through product code, that path emits the same
    kind of span with the model name, and a fast unit test using the
    in-memory exporter asserts it (AGENTS.md: untraced model calls are a
    review finding). The architect decides where the embedding call lives;
    see the notes below.
  - *Evidence.* `docs/evidence/model-roles/model-run-aria-gb10-2.txt` has the
    same header as the PS-2.21 run: date, HEAD, the two keys, the exact
    command, and the preflight `GET /v1/models` → 200 from the dev host. It
    adds the `GET /api/tags` name and digest of each of the three models
    (`:latest` is a moving tag, so the digest records what answered) and each
    role's measured call time. The whole run passes, teardown included.
  `[integration: test_compose_role_answers]`,
  `[integration: test_rewrite_role_answers]`,
  `[integration: test_audit_role_answers]`,
  `[integration: test_embed_role_answers]` (model-calling, full),
  `[gate: recorded local full run]` (manual)
- **MR-6 Role timeouts (Q55).** This item leaves `timeout_s` unchanged
  (compose, rewrite and audit 120, embed 60, `readiness.timeout_s` 2)
  unless the MR-5 run shows a role's call does not finish within its
  `timeout_s`. In that case the new value comes from the measured time in
  that run, using a rule the architect states and the orchestrator rules on,
  never a guessed number. Any change is pinned by MR-1's test.
  `[unit: test_model_role_defaults]` (fast)
- **MR-7 Q38 closed.** `docs/open-questions.md` shows Q38 as resolved by the
  2026-10-20 ruling, and A7's model-default sentence is marked superseded.
  This document's open-question lists no longer show Q38 as open. Done in the
  analyst step.

*Notes for the architect (not criteria):*
- **The embedding call.** `ModelClient` has `complete()` and `probe()` but
  no embedding call (`engine/llm/client.py`). Either add one (a small piece
  of product code, which then needs the MR-5 span and its unit test) or let
  the integration test post to `{base_url}/embeddings` through
  `client.http_client`. The item says "no new features", so state which
  approach you choose and why.
- **Latency on audit.** `gpt-oss:120b` is roughly a 65 GB model. A cold load
  on `aria-gb10-2`, plus memory pressure if Ollama has to evict `qwen3.5` or
  `nomic-embed-text` to load it, can take a large share of the 120 s
  `timeout_s`. That is the httpx client timeout for each operation, and on a
  non-streamed completion the read wait covers load plus generation. Test
  order also matters: role switches can force reloads.
- **Reasoning models.** `qwen3.5` and `gpt-oss` both reason before they
  answer. A low `max_tokens` cap can end on reasoning and leave `content`
  empty, and reasoning adds latency. The MR-5 prompts should be short and
  not cap tokens below what an answer needs.
- **Gateway forward timeouts.** The model forward is an nginx `stream`
  proxy (`docker/gateway/templates/model.conf.stream-template`) with
  `proxy_connect_timeout 5s` and nginx's default `proxy_timeout` (10 min
  idle). Neither should bind at 120 s, but say so.
- **The readiness probe** checks only `GET {compose.base_url}/models`. It
  does not check that each role's model is installed. That is not in scope
  here; MR-5 is the per-role proof.

Out of scope: pulling models; any fallback mechanism (no product code reads
`fallback_model` today, grep 2026-10-20); prompt tuning; streaming; gateway
changes beyond what MR-6 might need.

Gates: MR-1 to MR-4, MR-6 and MR-7 under `scripts/verify.sh fast`. MR-5 needs
`scripts/verify.sh full` with the two keys set on a host that can reach
`aria-gb10-2`. `scripts/verify.sh full` runs before the commit regardless.

### Open questions for this item

None open. Both questions raised for this item were ruled by the
orchestrator on 2026-10-20 (see `docs/open-questions.md`):
- **Q54 resolved (A54).** `fallback_model` for compose, rewrite and audit is
  `gpt-oss:20b`; the human may change it. MR-2 is unblocked, and MR-4
  removes `llama3.1:8b` from living files.
- **Q55 resolved (A55 accepted).** Timeouts stay as they are unless the MR-5
  run measures a slower call (MR-6).

---

## Item: ci-speed

Outcome metric moved: neither directly. It keeps the single CI gate
(`scripts/verify.sh full`) inside its timeout with margin, so every later
item can ship. Source: `docs/handoffs/ci-speed.md` (orchestrator, accepted
scope, 2026-10-20). Design: `docs/architecture.md` §2.2.1 (accepted). Profile:
`docs/evidence/ci-speed/profile.md`. Scope is architect step 1 (the unit
pool in `scripts/test.sh`), the nested-coverage test fix, and the hook
comment. Step 2 (splitting `test_offline_bundle.py`) and option (b) speed-ups
are out of scope. The integration suite is unchanged. Criteria are `CS-<n>`;
named tests live in `IntegrationRunsOnceTest` (`tests/test_harness_followups.py`).

- **CS-1 One process per top-level module, bounded pool.** Given the
  top-level unit modules (`tests/test*.py`, the same glob as unittest
  discovery's default pattern `test*.py`, so the pool runs exactly the
  modules discovery ran), when `test.sh` runs the unit
  suite, then each module runs in its own process, exactly once, and which
  modules share a process never depends on `nproc` or timing (none do). At
  most `min(nproc, 4)` module processes run at once, with `nproc` read inside
  the container (no new environment key; PS-2.21 stands).
  `[unit: test_top_level_modules_run_in_separate_processes]` (distinct pids,
  each module once) and
  `[unit: test_unit_pool_concurrency_follows_nproc_capped_at_4]` (fake
  `nproc`: 1 gives no overlap, 2 gives overlap of at least 2, 64 gives a
  maximum overlap of at most 4).
- **CS-2 Output printed whole, in module order.** Each module's output is
  printed as one contiguous block, after the pool, in module (glob) order,
  never interleaved with another module's. The sentinel line
  `test_top_level_unit_suite_ran (…) ... ok` therefore still matches the
  `verify.sh` check. `[unit: guard, contiguous output blocks]` (green today,
  stays green).
- **CS-3 The run fails closed.** Given any module exits non-zero, or exits 0
  but prints no `Ran N` line with N > 0, when the pool finishes, then
  `test.sh` exits non-zero. When one module fails, the other modules still
  run and their output is still printed.
  `[unit: test_unit_pool_fails_when_a_module_prints_no_ran_line]` (fake `uv`
  exits 0 silently for one named module) and the failing-module guard (green
  today, stays green). The existing `test_no_ran_line_fails` stays green.
- **CS-4 Coverage combines; threshold unchanged.** Every module process runs
  under `coverage run -p` with `uv run --locked`; `coverage erase` still runs
  before the first module; the report enforces `fail_under = 80` from
  `pyproject.toml`, unchanged; mypy is unchanged. The coverage data path
  comes from coverage's Python API (`coverage.Coverage().config.data_file`,
  via `uv run --locked python -c`); a lookup that fails or prints nothing
  fails the run before any test runs (no `.coverage` fallback). Every
  top-level module's process leaves its own coverage data file; given a
  module whose process leaves none, when the pool finishes, then `test.sh`
  exits non-zero and names that module. `coverage combine` is given the
  explicit list of this run's data files (each module's, plus the
  sub-package and integration runs'), never a directory or no argument.
  Given any of those files is still on disk after `combine` (not consumed),
  then `test.sh` exits non-zero and names its module. No percentage band
  against the one-process figure is used (Q-CS1, resolved).
  `[unit: test_unit_pool_fails_when_a_module_leaves_no_coverage_data]`,
  a fixture test with a real `combine` that leaves one module's file
  unconsumed (exact name in the tester's handoff section), and
  `[unit: test_engine_quality static pins]` (stay green).
- **CS-5 A nested `test.sh` never touches the gate's coverage data.** Given a
  test that runs `test.sh` in a throwaway project (today
  `test_coverage_erase_precedes_first_run_and_spares_checkout`), when it runs
  inside the gate, then no file under the gate's coverage `data_file` path
  (`/tmp/.coverage*`) is deleted or added by it. That test keeps its own
  assertions (erase precedes the first run; the checkout is spared).
  `[unit: test_nested_test_sh_leaves_gate_coverage_data_alone]` (a uniquely
  named planted `/tmp/.coverage.<unique>` survives; removed in cleanup). RED
  before the fix.
- **CS-6 Gates unchanged.** `git diff` against the branch base shows no change
  to `scripts/verify.sh`, `tests/test_sentinel.py` (module, class and method
  names), or the `[tool.coverage]` settings in `pyproject.toml`. In
  `.github/workflows/ci.yml` the only step stays `./scripts/verify.sh full`
  (`test_harness_port` stays green); only the `timeout-minutes` value and its
  comment may change, and only under CS-7. No gate is skipped, weakened or
  moved out of `verify.sh`.
- **CS-7 PS-3.4 re-measure.** After the first two green CI runs of
  `verify.sh full` that include the pool, `timeout-minutes` is set to the
  slower run's measured duration plus 50 %, rounded up to a whole minute
  (same rule as the platform-offline re-measure), in a follow-up commit on
  the branch. Both run ids, their durations and the arithmetic are saved in
  `docs/evidence/ci-speed/`, and the ci.yml comment names them.
  `test_ci_job_has_timeout` (fast) is unchanged; the reviewer checks the
  value against the evidence.
- **CS-8 Hook header reflects Q18.** `scripts/hooks/block-main-commit.sh` no
  longer calls branch protection "the real control (Q18)". Its header says
  Q18 was skipped (human, 2026-10-20), merges to `main` are a manual human
  action, and this hook is the only automated guard. Comment-only: the hook's
  behaviour and the existing hook tests are unchanged and green.
  `[unit: static test, "the hook header no longer calls branch protection
  the real control"]` (tester adding; exact method name in the tester's
  handoff section).
- **CS-9 Outcome target, measured.** On the gates image pinned to 2 CPUs
  (`--cpuset-cpus`, as in profile.md §3), the pooled unit suite's wall time is
  at most about 60 % of a one-process run of the same unit suite measured on
  the SAME commit (the commit under test, not the branch base or an earlier
  experiment), on the same host in the same conditions (modelled: 426 s →
  about 260 s or less; review L1). Both figures, the commit and both
  commands are saved in `docs/evidence/ci-speed/`.
  The CI unit-suite time from the two CS-7 runs is recorded too (projected
  310–450 s; informational, the runner is noisy). A miss goes to the
  orchestrator with the evidence; the target is not adjusted to pass.

Gates: the code and test changes touch `scripts/` and tests, so
`scripts/verify.sh full`; it runs before the commit regardless. TDD order:
CS-5 (prerequisite) → CS-1 → CS-3 → CS-2/CS-4 guards → CS-8 → CS-9 → CS-7
(after the commit's CI runs).

### Open questions for this item

None open. **Q-CS1 resolved (A-CS1, orchestrator, 2026-10-20; see
`docs/open-questions.md`):** no percentage tolerance; CS-4 instead requires
one coverage data file per module, and a missing one fails the run naming the
module. The 80 % threshold is unchanged.

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
   funnel shows ratified / proposed per tier. (DR22) Until real owners are
   named, the owner is the human (Adam Salah) as proxy ratifier (Q14, resolved
   2026-10-20), so ratification owners are not an external blocker.
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
7. **Valkey isolated and authenticated (carry-in, security M-1 network side,
   from `platform-stack-ready`; orchestrator rework round 1, 2026-10-19).**
   Must be done before any ingest exposure, that is before any item lets
   untrusted input reach the job queue, even if that item comes before
   auth-audit. Given the compose files, `valkey` sits on its own internal
   network that only `api`, `worker` (and `gates-it`) join, so no other
   service (`gateway`, `phoenix`, the stores) can reach it; and Valkey
   requires a password or ACL, passed only to `api` and `worker`, so an
   unauthenticated client is refused. The engine side of M-1 (JSON
   serializer, `engine.jobs.__all__` allowlist) is already PS-2.6. Test
   names are left to the tester (Q39 asks where it is scheduled).

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
