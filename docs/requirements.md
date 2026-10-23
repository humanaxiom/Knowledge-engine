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
      with `jq` present and with it absent, then it uses under 3 s of CPU time
      (user + sys of the hook and the children it waits for, measured as the
      `RUSAGE_CHILDREN` delta around the one hook call), whatever the
      command's shape: many short tokens, one long token, or one long heredoc
      line. The same call also finishes within a 60 s hang guard
      (`subprocess.run` `timeout`), which catches a hook that blocks or
      sleeps. *Reworded 2026-10-21 (human ruling, `ci-speed` rework 3;
      architecture §2.2.1-r3 decision 6). The bound stays 3 s; only what is
      measured changed, because wall time on a shared runner moves with
      load (`docs/evidence/ci-speed/rework3/hook-cpu-vs-wall.txt`).
      Original wording: "then it completes in under 3 s".*
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
    round 1, 2026-10-19).* The engine never negotiates GSS encryption, as
    defence in depth that keeps krb5 off that path. The first reason
    (psycopg-binary's vendored el7 Kerberos/SASL libraries) is gone under
    PSC-25, but Debian 12's libpq 15 is still built with GSSAPI, so
    `gssencmode="disable"` still applies. *(Amended 2026-10-23, analyst, U0 review.)* Given the postgres readiness probe, it connects with
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
  recorded measurement. From `ci-triggers` on, the two green runs are a PR's `pull_request` run and its manual re-run (attempt 2) on the same head commit (CT-5).

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
  PSScriptAnalyzer is installed from a package whose hash is pinned and
  checked before install (SHA-512 by the 2026-10-21 ruling; see PSC-10) (no install from a trusted PSGallery by version
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

Outcome metric moved: neither directly. **The CI speed-up is withdrawn**
(human ruling 2026-10-21). On the hosted runner the pool made the unit stage
slower (806–848 s against 542–793 s for one process;
`docs/evidence/ci-speed/rework3/diagnosis.md`), and this item makes no speed
claim. What it delivers instead:
- coverage that fails closed: every coverage run's data is accounted for, or
  the run fails naming it;
- CI diagnostics, through the resource probe and `--durations 10`, so the
  next slow run can be classified from its log;
- hook budget tests that no longer flake on a loaded runner;
- the CS-5 nested-coverage fix and the CS-8 hook header.

These keep the single CI gate trustworthy, so every later item can ship. The
speed goal moves to plan item `test-diet`.

- Source: `docs/handoffs/ci-speed.md` (orchestrator, accepted scope,
  2026-10-20; human rulings, 2026-10-21).
- Design: `docs/architecture.md` §2.2.1 (pool, withdrawn) and §2.2.1-r3 (in
  force).
- Profile: `docs/evidence/ci-speed/profile.md`.

The integration suite is unchanged. Criteria are `CS-<n>`. Named tests live
in `IntegrationRunsOnceTest` (`tests/test_harness_followups.py`) unless
another class is named.

- **CS-1 WITHDRAWN (human ruling 2026-10-21):** on CI the pool gave 0.78–1.18×
  one process's throughput, so it was slower; replaced by CS-10. Original
  text kept for the record: *One process per top-level module, bounded pool.* Given the
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
- **CS-2 WITHDRAWN (human ruling 2026-10-21):** one process streams its output,
  so there are no per-module blocks to order. Original text kept for the
  record: *Output printed whole, in module order.* Each module's output is
  printed as one contiguous block, after the pool, in module (glob) order,
  never interleaved with another module's. The sentinel line
  `test_top_level_unit_suite_ran (…) ... ok` therefore still matches the
  `verify.sh` check. `[unit: guard, contiguous output blocks]` (green today,
  stays green).
- **CS-3 WITHDRAWN (human ruling 2026-10-21):** per-module rc and `Ran` checks
  exist only for the pool. With one process, `set -e` and `verify.sh`'s
  existing `Ran N > 0` and sentinel checks fail closed (CS-10). Original text
  kept for the record: *The run fails closed.* Given any module exits non-zero, or exits 0
  but prints no `Ran N` line with N > 0, when the pool finishes, then
  `test.sh` exits non-zero. When one module fails, the other modules still
  run and their output is still printed.
  `[unit: test_unit_pool_fails_when_a_module_prints_no_ran_line]` (fake `uv`
  exits 0 silently for one named module) and the failing-module guard (green
  today, stays green). The existing `test_no_ran_line_fails` stays green.
- **CS-4 Coverage fails closed; threshold unchanged** (amended 2026-10-21:
  per coverage run instead of per pooled module; §2.2.1-r3 decision 3).
  - Every coverage run in `test.sh` (the top-level run, each sub-package run
    and the integration run) runs under `coverage run -p` with
    `uv run --locked`.
  - `coverage erase` still runs before the first run. The report enforces
    `fail_under = 80` from `pyproject.toml`, unchanged, and mypy is
    unchanged.
  - The coverage data path comes from coverage's Python API
    (`coverage.Coverage().config.data_file`, through
    `uv run --locked python -c`). A lookup that fails or prints nothing fails
    the run before any test runs. There is no `.coverage` fallback.
  - Each run writes `--data-file=<cov_dir>/<cov_name>.<label>`. The labels
    are `toplevel` for the top-level run, `tests.<pkg>` for each sub-package
    run and `tests.integration` for the integration run. No label is a
    dot-prefix of another.
  - Given a run that leaves no `<cov_name>.<label>.*` file, then `test.sh`
    exits non-zero and names the label.
  - `coverage combine` is given the explicit list of this run's data files,
    never a directory and never no argument.
  - Given any of those files is still on disk after `combine` (not
    consumed), then `test.sh` exits non-zero and names its label.
  - No percentage band against another figure is used (Q-CS1, resolved).

  `[unit: test_data_file_lookup_empty_or_failed_fails_before_any_test]`,
  `[unit: test_coverage_combine_gets_an_explicit_file_list]`, a run that leaves no
  data, and a fixture test with a real `combine` that leaves one run's file
  unconsumed. These are adapted to the labels; exact names are in the
  tester's handoff section. `[unit: test_engine_quality static pins]` stays
  green.
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
  `verify.sh full` that include this item's final `test.sh` (one top-level
  process; amended 2026-10-21, was "the pool"), `timeout-minutes` is set to the
  slower run's measured duration plus 50 %, rounded up to a whole minute
  (same rule as the platform-offline re-measure), in a follow-up commit on
  the branch. Both run ids, their durations and the arithmetic are saved in
  `docs/evidence/ci-speed/`, and the ci.yml comment names them.
  `test_ci_job_has_timeout` (fast) pins the exact value, so its constant and
  message change with this ruling (as at platform-offline); the reviewer
  checks the value against the evidence.
  **CS-7 MET (2026-10-21).** Green runs 39559700392 (21.1 min) and
  39559708963 (20.3 min) on `24b6839`; slower 21.1 min + 50 % = 31.65, rounded
  up: `timeout-minutes` 29 -> 32. Evidence:
  `docs/evidence/ci-speed/cs7/ci-timeout.md`.
- **CS-8 Hook header reflects Q18.** `scripts/hooks/block-main-commit.sh` no
  longer calls branch protection "the real control (Q18)". Its header says
  Q18 was skipped (human, 2026-10-20), merges to `main` are a manual human
  action, and this hook is the only automated guard. Comment-only: the hook's
  behaviour is unchanged, and the existing hook tests stay green (their
  budget measurement changes only under CS-12).
  `[unit: static test, "the hook header no longer calls branch protection
  the real control"]` (tester adding; exact method name in the tester's
  handoff section).
- **CS-9 WITHDRAWN (human ruling 2026-10-21):** there is no speed claim. The
  method was also wrong for its purpose: dedicated local cores with no stack
  do not model the hosted runner's CPU (0.57× locally, 1.02–1.56× on CI;
  diagnosis §6). Its corrected form, a CI A/B on the same commit, is TD-5 in
  `test-diet`. Original text kept for the record: *Outcome target, measured.* On the gates image pinned to 2 CPUs
  (`--cpuset-cpus`, as in profile.md §3), the pooled unit suite's wall time is
  at most about 60 % of a one-process run of the same unit suite measured on
  the SAME commit (the commit under test, not the branch base or an earlier
  experiment), on the same host in the same conditions (modelled: 426 s →
  about 260 s or less; review L1). Both figures, the commit and both
  commands are saved in `docs/evidence/ci-speed/`.
  The CI unit-suite time from the two CS-7 runs is recorded too (projected
  310–450 s; informational, the runner is noisy). A miss goes to the
  orchestrator with the evidence; the target is not adjusted to pass.
- **CS-10 One top-level process** (added 2026-10-21; §2.2.1-r3 decisions 2
  and 5).
  - Given the top-level unit modules (`tests/test*.py`), when `test.sh` runs,
    then they all run, each exactly once, in **one**
    `uv run --locked python -m coverage run -p --data-file=<cov_dir>/<cov_name>.toplevel -m unittest -v --durations 10 <modules…>`
    process, in glob order.
  - Output streams as it did before the pool. The sub-package runs and then
    the integration run (`full` only) follow in sequence.
  - Given any run exits non-zero, then `test.sh` exits non-zero and no later
    run starts. The one exception is the CS-11 end line.
  - `verify.sh`'s existing `Ran N > 0` and sentinel checks are unchanged.
  - Under CS-10 the pool's code is gone: no k, ordering, log directory,
    per-module summary lines or INT/TERM trap.

  `[unit: test_top_level_modules_run_in_one_process]` (counted modules
  record one shared pid, each module once, label `toplevel`; replaces
  `test_top_level_modules_run_in_separate_processes`), the `--durations 10`
  test adapted to the single run, and guards that stay green:
  - a failing top-level module fails the run;
  - `test_failing_subpackage_module_fails_run`;
  - `test_failing_integration_module_fails_full_run`.
- **CS-11 Resource probe** (added 2026-10-21; human ruling e3; §2.2.1-r3
  decision 4).
  - `test.sh` prints one `resources: phase=start …` line immediately before
    the top-level run.
  - It prints one `resources: phase=end …` line after the last unit run
    (before the integration run in `full`, before `combine` in `fast`), even
    when a unit run failed. `test.sh` still exits non-zero in that case.
  - The line has the exact keys, order and value pattern given in §2.2.1-r3:
    nproc, the cgroup CPU quota and throttling, memory and swap, the cgroup
    memory limit and peak, PSI totals for cpu, memory and io, and CPU steal
    and total ticks. The sources are `/proc` and `/sys/fs/cgroup`.
  - Given a missing or unreadable source, or a value that is not a number
    (or `max` where allowed), that key prints `n/a`. The probe still exits
    0, prints nothing to stderr and never fails the run.
  - The line never contains an environment variable's value or any file
    text other than digits or `max`.
  - *Hardening (added 2026-10-21, rework 4; §2.2.1-r3 decision 4; security
    S5–S7, review nits 5–6):*
    - Given a source that is a FIFO, a device (for example `/dev/zero`) or
      any other non-regular file, then that key prints `n/a`, and the probe
      exits 0 quickly without hanging. Reads are bounded: each read of a
      source has a timeout and a byte cap, and each source is read for at
      most a fixed number of lines. An oversized or endless printable
      regular file is cut off, and a key not found within the cap prints
      `n/a`. (The here-string read of the in-memory `cpu.max` value is
      uncapped by design.)
    - Known limit (security S8, accepted low): a NUL-filled file, or a FIFO
      swapped in after the regular-file check, is bounded only by the CI job
      timeout (on a local run, until someone stops it). These are the
      complete set of hang cases; `read -t` also fires on character devices
      such as /dev/zero. A NUL-filled file costs several seconds per GB
      (measured 2.5–11 s). It is reachable only through the test-only `root`
      argument or control of `/proc` and `/sys`, and it fails red, never
      green. The
      `timeout 10` wrapper is a follow-up (below).
    - A printed number has at most 20 digits; a longer one prints `n/a`.
    - `/proc/stat` arithmetic is base-10 (a leading zero is decimal), with
      each field capped at 18 digits so the sum cannot overflow. A field
      over the cap, or any invalid field, gives `n/a` for both
      `cpu_steal_ticks` and `cpu_total_ticks`. Both values are printed
      through the same number check as every other key.
    - `nproc` runs with `OMP_NUM_THREADS` and `OMP_THREAD_LIMIT` cleared, so
      an OpenMP override never changes the reported count.
    - The probe reads no environment variable: every variable is assigned
      before use, and `root` defaults to `/`. This is tested on the path
      `test.sh` uses (no `root` argument).

  `[unit: ResourceProbeTest.test_prints_one_line_from_a_fake_root]`,
  `[unit: ResourceProbeTest.test_missing_sources_print_na_and_exit_0]`,
  `[unit: ResourceProbeTest.test_prints_only_numbers_never_file_text_or_env]`,
  `[unit: test_resource_lines_bracket_the_unit_stage]`, and for the
  hardening (rework 4; exact names in the tester's handoff line):
  `[unit: ResourceProbeTest.test_fifo_or_device_source_gives_na_quickly]`,
  `[unit: ResourceProbeTest.test_oversized_source_is_cut_off]`,
  `[unit: ResourceProbeTest.test_stat_fields_are_base_10_and_capped]`,
  `[unit: ResourceProbeTest.test_nproc_ignores_openmp_env]`,
  `[unit: ResourceProbeTest.test_no_root_path_reads_no_env]`,
  `[unit: ResourceProbeTest.test_each_reader_caps_bytes_and_lines]`.
- **CS-12 Hook budget tests measure CPU time** (added 2026-10-21; human
  ruling; harness-claude-code requirement 4f as reworded; §2.2.1-r3
  decision 6).
  - Each wall-clock budget test in `tests/test_block_main_commit_hook.py`
    measures the hook's CPU time instead. That is user + sys from the
    `RUSAGE_CHILDREN` delta around the one `subprocess.run` of the hook.
  - The budgets are unchanged: 3 s for the 1 MB tests, 9 s for the 5 MB test,
    and 5 s for the 400-segment test (A-CS2, accepted 2026-10-21).
  - The same call keeps a 60 s `timeout` as a hang guard.
  - No budget is raised and no shape is dropped.
  - *No background work (added 2026-10-21, rework 4; security S4;
    §2.2.1-r3 decision 6).* The CPU budget does not count work the hook
    does not wait for, and no wall-clock bound is added, because it would
    bring back the load flake. Instead, a static test fails if the hook
    source has any character other than printable ASCII, tab and newline
    (security S9), or if any line, split on newline only and comment lines
    included (amended rework 5), has the plain spelling of any of these
    (forms that still pass are under Known limits below):
    - an `&` that is not part of `&&`, `|&`, `>&`, `<&` or `&>` (`|&`, the
      stderr pipe, is allowed);
    - process substitution `<(` or `>(`;
    - the words `setsid`, `nohup`, `disown`, `coproc`, `bg` or `eval`;
    - a nested shell (widened rework 5, review nit 1): `bash`, `sh`, `dash`,
      `zsh` or `ksh`, bare or quoted, or `$BASH`, `${BASH}` or `$SHELL`,
      with any options before `-c`; `bash -s`; piping into a shell; or
      `source` or `.` of `/dev/stdin`.

    Residual risk (accepted, low; security S10): a deny-list cannot be
    complete for bash, so a construct off the list (for example `se''tsid`
    or a `trap` string) is not seen; work detached by a program the hook
    calls is not seen; and a hook call over Claude Code's 10 s timeout
    fails open for that call. The fix, an allow-list of the commands the
    hook may call, is a follow-up (below).

    Known limits (rework 5; `rework5/review.md` F1, `rework5/security.md`
    S11): these nested-shell forms still pass the detector: `bash \<newline>
    -c`; a line ending in `|` with `bash` on the next line; `bash <<<…`; a
    heredoc fed to `bash`; `bash /dev/stdin`; `bash -`; `bash -i`;
    `source -- /dev/stdin`; `| nice -n 5 bash`; `ba""sh -c`; `$(echo bash)
    -c`. Each needs a deliberately hostile hook edit. The allow-list
    follow-up closes them.

  `[unit: a helper test: a sleeping child counts under 0.5 s of CPU and a
  busy child counts about its wall time]`, plus the four converted tests
  (names unchanged), and `[unit: test_hook_launches_no_background_work]`
  (static; one mutant per listed construct, per nested-shell spelling, per
  non-printable separator such as FF or `\x1f`, and per `#`-led line inside
  a string must fail it; exact names in the tester's handoff line).

Gates: the code and test changes touch `scripts/` and tests, so
`scripts/verify.sh full` is required, and it runs before the commit
regardless. TDD order (rework 3): CS-11 probe tests → CS-10 → CS-4 guards
adapted to the labels → CS-12 → the pool-only tests removed (tester) → CS-5
and CS-8 guards stay green → CS-7 (after the commit's CI runs).

### Follow-ups (not in ci-speed)

Recorded 2026-10-21 (orchestrator ruling, rework 5). None blocks this item.
- **Probe `timeout 10` wrapper (security S8).** Wrap both probe calls in
  `test.sh` so a NUL-filled source or a FIFO swapped in after `[ -f ]` fails
  at 10 s instead of at the CI job timeout. Trade-off: that case then fails
  the run instead of printing `n/a` (§2.2.1-r3, Alternatives considered).
- **Hook command allow-list (security S10).** Replace the CS-12 deny-list
  with an allow-list of the commands and builtins the hook may call. It also
  closes the S11 nested-shell forms listed under CS-12 Known limits.
- **Test nits from rework 5 review (F2, F3).** In
  `tests/test_block_main_commit_hook.py`: F2, write the literal U+2028 and
  U+2029 characters as `\u` escapes; F3, rewrite the "#-line in a quoted
  heredoc fed to a shell" mutant (~:963), which is caught by the plain
  `sleep 9 &` line and tests neither comment scanning nor a heredoc fed to
  a shell.
- **Speed goal: `test-diet`** (already a plan item, § Item: test-diet below;
  TD-5 is the corrected CS-9 A/B).
- **CS-7 PS-3.4 re-measure.** After the first two green CI runs that
  include this item's final `test.sh`, set `timeout-minutes` from them
  (CS-7 above; TD-6 re-measures again after `test-diet`).

### Open questions for this item

- **Q-CS1** was resolved by the orchestrator (A-CS1, 2026-10-20) and amended
  2026-10-21 (see `docs/open-questions.md`). There is no percentage
  tolerance. CS-4 requires each coverage run label to leave its own data
  file, and a missing one fails the run naming the label. The 80 % threshold
  is unchanged.
- **Q-CS2** was resolved by the orchestrator (A-CS2 accepted, 2026-10-21,
  as covered by the human's CPU-time ruling; see `docs/open-questions.md`).
  The 400-segment L8 test (5 s) moves to CPU time with the 3 s and 9 s
  tests, and its value is unchanged.

---

## Item: ci-triggers

Outcome metric moved: neither. This is CI infrastructure. It moves neither
*drafts a human reviewer has acted on* nor *ratified rules*; it halves the
billed CI minutes per PR push, so the private repo's monthly minutes last
about twice as many pushes. Source: `docs/handoffs/ci-triggers.md`
(orchestrator, 2026-10-22); the platform-supply-chain close-out security note
(`docs/handoffs/archive/platform-supply-chain.md`). Default branch:
`ccr-19465ed4-j1u0m5` (written `<default>` below).

- **CT-1 Trigger shape.** In `.github/workflows/ci.yml` the `on:` mapping has
  exactly two keys, `push` and `pull_request`. `push` has exactly one key,
  `branches`, whose value is the list `[<default>]` (no `tags`, `paths`,
  `paths-ignore` or `branches-ignore`). `pull_request` has no filter (null or
  empty) unless Q-CT1 rules otherwise. No `pull_request_target`,
  `workflow_dispatch` or `schedule`. `[unit]` (fast) loads ci.yml with
  `yaml.safe_load` and asserts these; PyYAML reads the bare key `on` as the
  boolean `True`, so the test reads `workflow.get("on", workflow.get(True))`
  and fails if neither is present.
- **CT-2 One run per event.** After the change lands: a push to a branch
  with an open PR targeting `<default>` gives exactly one run, event
  `pull_request`; a merge to `<default>` gives exactly one run, event
  `push`. Evidence: `gh run list --commit <sha>` output for the ci-triggers
  PR head and for its merge commit, with the run ids, saved under
  `docs/evidence/ci-triggers/` and named in the handoff.
- **CT-3 Concurrency.** The group stays `ci-${{ github.ref }}` with
  `cancel-in-progress: true` (unless Q-CT2 rules otherwise). `github.ref` is
  `refs/pull/<n>/merge` for a `pull_request` run and `refs/heads/<default>`
  for a `push` run, so a newer push to a PR cancels that PR's older run, and
  a PR run and a default-branch run never share a group. `[unit]` (fast)
  asserts the group string and `cancel-in-progress`.
- **CT-4 Existing pins unchanged.** One `run:` step, `./scripts/verify.sh
  full` (`test_ci_calls_verify_only`); `runs-on: ubuntu-24.04`; checkout at
  the same 40-hex SHA with `persist-credentials: false`; `timeout-minutes: 37`
  (`test_ci_job_has_timeout`); `permissions: contents: read`. CLAUDE.md
  "What CI runs that verify.sh does not: Nothing" stays true and unedited.
  The ci.yml diff touches only the `on:` block (and a comment, if any).
- **CT-5 PS-3.4 two green runs, restated.** Push and pull_request no longer
  both fire on one commit. From this item on, the two green runs for a
  PS-3.4 re-measure are the PR's `pull_request` run and a manual re-run of
  that same run (`gh run rerun <id>`, attempt 2) on the same head commit.
  Reason: same commit and tree, both before merge, so the timeout commit
  stays on the PR branch as CS-7 and PSC-9 did; no new trigger. Evidence
  names run id plus attempt number and each attempt's duration. Once ruled,
  PS-3.4 gets a one-line pointer here; the 37 min pin is not changed.
- **CT-6 Documented behaviour.** AGENTS.md "Branch Policy" (which CLAUDE.md
  imports, so one copy serves both) says: CI runs only on pushes to `<default>`
  and on pull requests; a branch pushed with no open PR gets no CI, so the
  developer (with the human's approval) or the human opens a PR, draft is
  fine; a PR with a merge conflict gets no `pull_request` run until the
  conflict is resolved. The README "CI runs on `ubuntu-24.04`" bullet gets
  one sentence saying the same. `[unit]` (fast) asserts a phrase in each.
- **CT-7 Cost measured on CI.** After landing, the evidence records, for one
  PR push before (PR #11: runs 39723927881 push, 39724208839 pull_request)
  and one after: the run count per head commit and each run's job minutes
  from `gh`. Pass: one run per PR push after, against two before. The
  billed-minutes claim is taken from these numbers, not estimated.


Status (documenter, 2026-10-22, close-out):

| Criterion | Status | Evidence |
|---|---|---|
| CT-1 | MET | `docs/evidence/ci-triggers/green-verify-fast.txt`, `green-verify-full.txt` |
| CT-2 | MET | PR #12 head `3c3382a`: one run, 39832485123, event `pull_request`, success (`docs/evidence/ci-triggers/ct2-pr-head.txt`); merge `d6b7035`: one run, 39837794999, event `push`, success (`docs/evidence/ci-triggers/ct2-merge-commit.txt`) |
| CT-3 | MET (pin, passed on arrival) | `test_ci_concurrency_per_ref` |
| CT-4 | MET | ci.yml diff is the `on:` block and its comment only (handoff, developer GREEN section) |
| CT-5 | MET | pointer added to the PS-3.4 bullet |
| CT-6 | MET | `test_docs_say_ci_needs_a_pull_request` |
| CT-7 | MET | `docs/evidence/ci-triggers/ct7-cost.md`: runs per PR push 2 -> 1, job minutes 43.4 -> 16.7 (billed 44 -> 17) |

Follow-ups (not in ci-triggers):
- `test-diet` TD-5 runs Arm B "on a scratch branch that is never merged".
  Under CT-1 that branch gets no CI; TD-5 needs amending to a draft PR that
  is never merged (Q-CT4).
- N1 (review): a workflow with both a quoted `"on"` key and a bare `on` key
  is an unhandled edge case in the CT-1 test.
- L-3 (security): `cancel-in-progress` applies only to `pull_request`; this
  needs a ruling and a CT-3 pin change.
- I-4 (security): pin `permissions: contents: read` in a test.

### Open questions for this item

- **Q-CT1 Filter `pull_request` to `<default>`?** Recommend no filter:
  stacked PRs (this branch was cut from a close-out branch) still get CI,
  and the cost per push is one run either way.
  **Ruled 2026-10-22 (orchestrator):** no `pull_request` filter.
- **Q-CT2 Cancel superseded default-branch runs?** Recommend keep
  `cancel-in-progress: true` for both: merges are human and rare, the PR
  head was already green, and the newest default-branch commit always gets
  a run. The alternative is not cancelling `push` runs.
  **Ruled 2026-10-22 (orchestrator):** keep `cancel-in-progress: true` for both events, group unchanged.
- **Q-CT3 Who triggers the CT-5 re-run?** It spends billed minutes like a
  push. Recommend the human approves it, as for a push.
  **Ruled 2026-10-22 (orchestrator):** the human approves the CT-5 re-run, as for a push.
- **Q-CT4 TD-5 amendment.** Recommend a draft PR for Arm B, opened and
  closed unmerged with the human's approval, over adding
  `workflow_dispatch` (keeps CT-1's two triggers).
  **Ruled 2026-10-22 (orchestrator):** TD-5 Arm B becomes a draft PR, never merged; recorded as a test-diet follow-up, not done here.
- **Q-CT5 Default branch rename.** The literal `<default>` in CT-1 stops all
  default-branch CI silently if the branch is renamed (`$default-branch`
  works only in workflow templates). Recommend pinning the literal in the
  test with a comment that a rename must update both.
  **Ruled 2026-10-22 (orchestrator):** pin the literal default-branch name in the test with a rename note.

---

## Item: test-diet

Outcome metric moved: neither directly. It keeps the single CI gate
(`scripts/verify.sh full`) inside its timeout with margin. It is the only
lever that helps a runner with about one core of parallel capacity, because
it removes CPU work instead of spreading it out.

- **Status: not started.** It was opened by the human ruling of 2026-10-21
  (`docs/handoffs/ci-speed.md`; ci-speed diagnosis option e1).
- It starts after `ci-speed` merges, because it needs the one-process unit
  stage and the CS-11 resource lines.
- **Scope:** tests and their fixtures only, in `InstallPs1Test`
  (`tests/test_offline_bundle.py`) and `LintScriptTest`
  (`tests/test_stack_scripts.py`). Together they take about 51 % of the unit
  suite's time (`docs/evidence/ci-speed/profile.md`).
  The `test_harness_followups` fixture cost (TD note below) is added to this scope.
- Production scripts, `verify.sh`, `ci.yml`, the sentinel and
  `[tool.coverage]` are unchanged. Any production change needs an
  orchestrator ruling first.
- Criteria are `TD-<n>`. Candidate cuts, for the architect to confirm:
  - one fixture bundle built once per class instead of per test;
  - a lint fixture tree with fewer files;
  - merging cases that run the same script invocation.
  - **TD note (from ci-speed CS-7):** the `test_harness_followups` fixture
    cost, about +90 s per CI run (24 -> 41 tests, 16 s -> 106 s; evidence
    `docs/evidence/ci-speed/cs7/ci-timeout.md`). It is the main part of this
    item's own ~110 s and is in scope for the cuts above.

Criteria:

- **TD-1 Behaviour kept.** Every requirement and finding that a changed test
  maps to keeps at least one named test that asserts it, in the same commit.
  The traceability for each cut is listed in the handoff.
- **TD-2 Each cut has a mutant.** For each cut, a scratch mutant of the
  production script that the removed or merged test used to catch is still
  caught (RED) by the remaining tests. Mutants and their results are saved
  under `docs/evidence/test-diet/`.
- **TD-3 Gates unchanged.** The coverage report still meets
  `fail_under = 80`. No test is skipped, weakened or moved out of
  `verify.sh`. The sentinel is untouched.
- **TD-4 Tests stay deterministic and independent.** A shared per-class
  fixture is created in `setUpClass` and is read-only to the tests that use
  it. The changed classes pass in any test order, run alone or with the rest
  of the suite.
- **TD-5 Measured on CI, A/B on the same commit** (the corrected CS-9; ci-speed
  diagnosis §6).
  - Arm A is the candidate commit.
  - Arm B is the same commit with only the two changed test modules (and
    their fixtures) restored to the branch base. Arm B is on a scratch branch
    that is never merged and is pushed only with the human's approval. No env
    key is added (PS-2.21).
  - Each arm runs twice on CI, interleaved in time, and both arms carry the
    CS-11 resource lines.
  - The metric is the unit stage measured from the runner's per-line
    timestamps, from `lint: PASS` to the first line after the unit stage, as
    parsed by `docs/evidence/ci-speed/experiments/parse_ci.py`.
  - **Pass:** A's slower run is faster than B's faster run, **and** the
    median A/B ratio is ≤ 0.85.
  - Run ids, timestamps, the resource lines and the arithmetic are saved
    under `docs/evidence/test-diet/`.
  - A local measurement is informational only. A miss goes to the
    orchestrator with the evidence, and the target is not adjusted to pass.
- **TD-6 PS-3.4 re-measure.** After two green CI runs of the merged change,
  `timeout-minutes` is re-measured under the same rule as CS-7.

---

## Item: platform-supply-chain

Outcome metric moved: **neither.** No draft is reviewed and no rule is
ratified because of this item, and none becomes possible because of it. What
it changes:
- a `ke-app` image with a known, fixed High or Critical vulnerability stops
  passing `verify.sh full`;
- the gates image stops trusting the PowerShell Gallery by version alone.

*(Split accepted 2026-10-21, orchestrator: "the bundle says what it contains
(SBOM) and which licence obligations come with it" moved with PSC-13–PSC-15
to § "Item: platform-sbom".)*

It closes security carry-ins on a bundle that already ships (L-13, L-8,
N-7). It does not unblock `ingest-ledger`; whether it goes first is a
sequencing call for the orchestrator.

- Source: `docs/handoffs/platform-supply-chain.md` (orchestrator, opened
  2026-10-21). Carried from `platform-offline` by the split ruling and R3
  (2026-10-19; `docs/handoffs/archive/platform-offline-part1.md`) and the
  close-out (`docs/handoffs/archive/platform-offline.md`).
- Supersedes the text of PS-3.6 and PS-3.7 (§ PS-3) for building. Those
  entries stay as the record. Their test names are kept below.
- Design: ADR-KE-013 and its amendment 1 (D1–D9, 2026-10-21), which also
  makes §2.2 "PSScriptAnalyzer by hash" concrete (D7, PS-3.7). First tests:
  `docs/architecture.md` §2.6 "platform-supply-chain".
- Settled, not re-opened here:
  - Q41: the scanner and its database are build and verify tools, fetched in
    the `verify.sh full` host half in CI and locally, never in the bundle, and
    a newly published CVE turning `full` red is the gate working;
  - Q43/R3: only `ke-app` is scanned;
  - R4/A43: the Neo4j GPL-3.0 listing and the Phoenix exception;
  - Q48: the hash-provenance rule;
  - A34: the Windows-proof scope.
- Criteria are `PSC-<n>`: PSC-1–PSC-12 and PSC-17 here. Q42 and Q56–Q60 were ruled
  2026-10-21 (`docs/open-questions.md` § platform-supply-chain, and Q42 in
  § platform-skeleton), and the criteria below apply the rulings (edited
  by the architect, 2026-10-21): Q42 in PSC-4 and PSC-5, Q56 in PSC-3,
  Q59 in PSC-2, Q60 in PSC-9.

**PS-3.6 Image scan (ADR-KE-013; security L-13).**

- **PSC-1 Pinned, reviewed scanner.** Given `docker-compose.scan.yml` (a
  standalone file, ADR-KE-013 amendment 1, D1), the `scan-db` and `scan`
  services use one scanner image referenced by digest (`@sha256:` + 64
  hex), with no `latest` tag and no tag-only reference. The digest is the
  multi-arch index digest, so the same pin runs on amd64 and arm64.
  Before the pin is committed, security records the release's provenance
  check (signature or attestation; the steps and the fallback are D2) in
  the handoff.
  - `[unit: test_image_scanner_is_pinned]` (fast, compose config)
  - Evidence: security's provenance note,
    `docs/evidence/platform-supply-chain/scanner-provenance.md`.
- **PSC-2 `ke-app` only, native architecture, from an image tar, no
  socket.** When `scripts/scan.sh` runs, then the steps run in this order:
  1. `ke-app:${KE_IMAGE_TAG}` is saved to a tar under `dist/<scan
     project>/`;
  2. `scan-db` runs;
  3. `scan` reads that tar, mounted read-only.

  No other image is scanned. No service in `docker-compose.scan.yml` mounts
  a Docker socket or sets `DOCKER_HOST` (ADR-KE-009).
  - *Native architecture (Q59 ruling).* `verify.sh full` scans the image of
    the host it runs on, with no `--platform` and no emulation: amd64 on CI
    and the dev host. The arm64 `ke-app` is scanned in recorded arm64 runs
    (the Q51 form), and each such run's scan output is saved as evidence
    under `docs/evidence/platform-supply-chain/arm64/`.
  - `[unit: test_scan_order_is_save_then_db_then_scan]` (fast, fake docker)
  - `[unit: test_scan_input_is_read_only_ke_app_tar]` (fast, fake docker)
  - `[unit: test_scan_services_have_no_docker_socket]` (fast, compose config)
  - `[unit: test_scan_refuses_malformed_image_tag]` (fast, fake docker: an
    unset or malformed `KE_IMAGE_TAG` fails before any docker call)
- **PSC-3 Fresh database, one network step, fail closed.**
  - Given the compose config, then `scan-db` mounts only the `scan-db` named
    volume. It has no checkout mount and a read-only root filesystem, and
    it is the only service in `docker-compose.scan.yml` with a route out
    (its project's default bridge).
  - `scan` has `network_mode: none` and mounts the `scan-db` volume
    read-only, with the database auto-update and update check turned off.
  - `gates` and `gates-it` are unchanged: no new network, mount or key.
    They, and `scan`, stay offline (Q56(a) ruling).
  - When `scan.sh` runs, the database update runs on every invocation, in
    CI and locally. No database from an earlier run is reused: each run
    has its own `ke-scan-<random>` project, so its volume starts empty, and
    `scan.sh`'s own `teardown.sh --volumes` removes it on every exit path.
    *(Amended 2026-10-21: the verify teardown runs before the scan, so it
    cannot remove the scan's volume.)*
  - *Fail closed (Q56(b) ruling).* When the scanner image pull or the
    database fetch fails, `scan.sh` exits non-zero with a message naming
    the stage (`scan-db`) and the host (the registry reference for the
    pull; the database host for the fetch). The call is made once, with no
    retry, and there is no skip path: `scan` does not run, and
    `verify.sh full` fails.
  - `[unit: test_compose_scan_db_has_only_db_volume]`,
    `[unit: test_compose_scan_has_no_network]` (fast, compose config);
    `[unit: test_scan_updates_db_every_run]`,
    `[unit: test_scan_db_failure_fails_closed_naming_host_and_stage]`
    (fast, fake docker); existing `test_gate_services_have_no_docker_host`
    stays green.
  - Evidence: a recorded red run with the database URL pointed at an
    unresolvable host fails naming it.
- **PSC-4 Threshold.** Q42 ruling (2026-10-21): keep A42. Fail on any High
  or Critical match that has a fixed version, after the ignore entries.
  Every other match is printed and does not fail.
  - Given a stubbed scanner result with one fixed High, then `scan.sh` exits
    non-zero and `verify.sh full` stops before `offline_check.sh` and exits
    non-zero.
  - Given only unfixed or lower-severity matches, then `scan.sh` exits 0 and
    prints them.
  - `[unit: test_verify_full_fails_when_image_scan_fails]`,
    `[unit: test_scan_fails_on_fixed_high]`,
    `[unit: test_scan_reports_but_passes_unfixed_and_lower]` (fast, stubbed
    scanner exit and output).
  - Evidence: a recorded red run of the real scan with a mutant policy
    (no `--only-fixed`, `--fail-on negligible`) fails on the real image.
- **PSC-5 Justified exceptions.** Accepted findings are listed in one
  committed ignore file (ADR-KE-013: `docker/scan-ignore.yaml`; schema in
  amendment 1, D5).
  - Each entry has the vulnerability id (key `vulnerability`, a CVE or GHSA
    id), an optional `package` (`name` only; omitted means every package),
    a non-blank `reason` and an `until` date.
  - *90-day cap (Q42 ruling).* `until` is a date with `today ≤ until ≤
    today + 90 days` (UTC). An entry is valid through its `until` day. An
    `until` that has passed, or one more than 90 days out, fails the test.
  - The file holds nothing but the `ignore` list, and no entry has a key
    outside the four above.
  - *psycopg-binary (Q42 ruling).* If a newer psycopg-binary wheel fixes a
    flagged vendored library, the lock is upgraded. If none does, the
    finding becomes a time-limited entry whose `reason` states why the
    code path is not reached (for krb5, `gssencmode=disable`, L-13),
    confirmed by security, and the orchestrator opens a follow-up item to
    evaluate psycopg on Debian's libpq.
    - *MOOT for the scan (2026-10-21, PSC-7 result).* grype v0.120.1
      catalogues none of the 15 files in `psycopg_binary.libs`, so the scan
      can never flag a vendored library and this branch never triggers
      from it. A krb5 or OpenSSL CVE in the wheel does not turn `full` red.
      The libraries are an accepted residual (L-13, PSC-7); the switch to
      Debian's libpq stays Q42's structural fix.
  - Security reviews every entry added in a diff.
  - `[unit: test_scan_ignores_are_justified]` (fast; controls: a valid
    entry passes; an entry missing `reason`, with a blank `reason`, missing
    `until`, with a past `until`, with an `until` 91 days out, with an
    `until` given as a string, with an unknown key, a malformed id, a
    duplicate, or a second top-level key each fail)
  - Evidence: a recorded run in which a planted entry for one real match
    suppresses it (the control that grype applies the file).
- **PSC-6 Place in `verify.sh`.**
  - `scan.sh` is a stage of the host half of `verify.sh full`, after the
    stack teardown and before `offline_check.sh`. `verify.sh fast` never
    scans.
  - A failing scan stops the later stages.
  - The tar, and the scan project with its database volume, are removed on
    every exit path: pass, fail, and interrupt.
  - The scan takes no key from the caller's environment or `.env`; the two
    model keys stay the only ones.
  - CI's only step stays `./scripts/verify.sh full`.
  - `[unit: test_verify_full_runs_scan_between_teardown_and_offline_check]`,
    `[unit: test_scan_removes_tar_on_every_exit]` (fast, fake docker); the
    existing `test_verify_full_takes_no_caller_ke_key_but_the_model_keys` and
    the CI single-step test stay green; `[gate: image-scan]` (full).
- **PSC-7 Report and the L-13 record.**
  - The scan prints its matches by severity, and the ignore entries it
    applied, to the verify output, so a CI log holds the full result.
  - The implementation commit saves one real `full` run's scan output under
    `docs/evidence/platform-supply-chain/` (saved in
    `u4-green-verify-full.txt`, lines 1601–1914).
  - That evidence states whether the scanner reported any package from
    `psycopg_binary.libs` (krb5, cyrus-sasl, pcre and others; L-13), and
    no doc claims the scan covers libraries it did not report. The method
    (the libraries in the image against the scanner's own package catalog)
    is ADR-KE-013 amendment 1, D6, recorded in
    `docs/evidence/platform-supply-chain/u4-psc7-psycopg-libs.txt`.
  - *Result (2026-10-21).* grype v0.120.1 catalogues none of the 15 files
    in `psycopg_binary.libs` (among them OpenSSL 3.5.8, libpq 18.0.6, pcre
    8.32, cyrus-sasl 2.1.26 and the el7 krb5), so the scan does not cover
    them. L-13 is an **accepted residual**, rated low by security
    (`security-u4.md`, "PSC-7 / L-13 residual").
    - Compensating control: track psycopg-binary releases, since the
      vendored libraries move with the wheel.
    - Mitigation today: `gssencmode=disable` (PS-2.5).
    - Structural fix: Q42's switch to psycopg on Debian's libpq.
    - L-13 closes under Q64 (platform-sbom U0). *(Added 2026-10-22,
      analyst, Q64; PSC-25.)*
    - **L-13 CLOSED 2026-10-23 by security (U0,
      `docs/evidence/platform-sbom/u0/security.md`).** *(Amended 2026-10-23, analyst, U0 review.)*
  - Evidence, checked by the reviewer and security; no unit test.
- **PSC-8 Not in the bundle.** The deployed product never scans: no bundle
  manifest entry names the scanner image or its database.
  `[unit: test_bundle_has_no_scanner_or_db]` (fast); `ci/deployable-offline`
  (full) stays green.
- **PSC-9 CI cost is measured on CI.**
  - Local timings do not predict CI. On the 2-vCPU runner, ci-speed's local
    benchmark (CS-9) missed the CI result (`docs/handoffs/archive/ci-speed.md`,
    2026-10-21 entries). Any local timing of the scan is informational only.
  - After the scan stage is wired in, two green CI runs of the branch record
    these from the runner's per-line timestamps:
    - the `ke-app` save, the `scan-db` fetch and the `scan` stage, each
      separately;
    - the whole job.

    They are saved under `docs/evidence/platform-supply-chain/ci/`, with the
    run ids.
  - If the slower run's job time plus 50%, rounded up, exceeds the
    `timeout-minutes` in force (32 once PR #9 lands), the timeout is
    re-measured under PS-3.4, as CS-7 was. It is not raised before two green
    runs exist.
  - *Trigger (Q60 ruling).* If the `save`, `scan-db` and `scan` stages
    together add more than 3 min (180 s) to the slower CI run, the
    orchestrator decides before the timeout is raised. Each stage is timed
    from its marker line to the next (ADR-KE-013 amendment 1, D8).
  - A run that times out is reported as red. It is never retried until it
    passes. `test_ci_job_has_timeout` pins the value.
  - **PSC-9 MET (2026-10-22).** Green runs on `34fc0c1`: push 39713504156
    (24.5 min; verify 1461 s; unit 1002 s; scan save 2 s, scan-db 90 s, scan
    6 s) and pull_request 39713519072 (23.0 min; verify 1372 s; unit 935 s;
    scan 2 s, 81 s, 5 s). The scan adds 88-98 s, under the Q60 trigger of
    180 s, so no decision is needed. Slower run 24.5 min x 1.5 = 36.75, rounded
    up: `timeout-minutes` 32 -> 37 (`CI_TIMEOUT_MINUTES` pinned by
    `test_ci_job_has_timeout`, red then green). The unit stage also grew
    (1002 s vs 893.6 s at ci-speed; 767 tests vs 724), so part of the job
    growth is new tests and runner variance, not the scan. Evidence:
    `docs/evidence/platform-supply-chain/psc9/ci-timeout.md`, logs in
    `docs/evidence/platform-supply-chain/ci/`.

**PS-3.7 Gates image supply chain (security L-8, review rework-1 N-7).**

- **PSC-10 PSScriptAnalyzer by hash.** Given `docker/gates.Dockerfile`:
  - the PSScriptAnalyzer package (`.nupkg`) for the pinned version is
    downloaded with `curl --proto '=https' --proto-redir '=https' --tlsv1.2`
    from the gallery's package endpoint to `/tmp`, and checked with
    `sha512sum -c` against `ARG PSSCRIPTANALYZER_SHA512` (one committed
    SHA-512, 128 lowercase hex; orchestrator ruling 2026-10-21, Q48). The
    check is the first step that reads the download, in the same fail-fast
    (`set -eu`) step, with no SHA-256 pin or cross-step;
  - after the check, it is unpacked with `python3 -I -m zipfile -e` into
    `/usr/local/share/powershell/Modules/PSScriptAnalyzer/<version>`, and
    the `.nupkg` and the NuGet packaging files (`_rels`, `package`,
    `[Content_Types].xml`, `*.nuspec`, `.signature.p7s`; security
    L-U1-1) are removed;
  - the check cannot be masked (u1 review B1; dash has no `pipefail`): it
    is a pipeline whose last command is `sha512sum`;
    it is not negated (`!`), not a condition (`if`, `elif`, `while`,
    `until`) and not backgrounded (`&`); the `RUN` has no `set +e` and no
    `set +o errexit`; and nothing writes the download path (`curl`/`wget`
    `-o`/`-O`, `cp`, `mv`, `>`, `tee`) between the check and the unpack;
    the check's pipeline is exactly two stages (an `echo` or `printf`
    feed, then `sha512sum -c -`), and the module `RUN` contains exactly one
    `sha512sum` (a second `sha512sum -c` stage would hide a failing first
    one; security M-U1R1-1, recorded as a killed mutant);
  - no gallery install command remains anywhere (`Install-Module`,
    `Install-PSResource`, `Save-Module`, `Save-PSResource`,
    `Set-`/`Register-PSRepository`, `Set-`/`Register-PSResourceRepository`);
  - the version is a fixed value. The package does not depend on the
    architecture, so one hash serves amd64 and arm64.
  - Hash provenance (Q48 form): the pinned SHA-512 equals the gallery's
    published `PackageHash` (base64 SHA512, converted to hex); the
    developer records both the API value and a local sha512 of the
    downloaded file; security re-checks them (ADR-KE-013 amendment 1, D7).
  - A build-time `pwsh … Import-Module PSScriptAnalyzer -ErrorAction Stop`,
    in the same `RUN` after the unpack, proves it; it is the first `RUN` in
    the final stage that starts pwsh.
  - With a wrong committed hash, the gates image build exits non-zero. The
    reviewer checks this by mutation, and the output is saved under
    `docs/evidence/platform-supply-chain/`.
  - `[unit: test_gates_image_verifies_psscriptanalyzer_hash]` (fast,
    Dockerfile; the one name, orchestrator ruling 2026-10-21; the earlier
    `test_gates_image_pins_psscriptanalyzer_by_hash` in architecture §2.6
    is retired; its mutant run records the reviewer's six masking mutants
    as killed, and M-U1R1-1, the second `sha512sum -c` stage);
    `[unit: test_gates_image_psscriptanalyzer_version_agrees]`
    (fast, Dockerfile: every PSScriptAnalyzer version a comment gives, and
    the module directory's version, equal `ARG PSSCRIPTANALYZER_VERSION`);
    `scripts/lint.sh` still runs PSScriptAnalyzer under `verify.sh full`
    (the real hash is proven by the build).
  - Evidence: `docs/evidence/platform-supply-chain/psscriptanalyzer-sha512.txt`
    (the gallery `PackageHash`, the local sha512 and the pin).
- **PSC-11 Telemetry off before pwsh (N-7).** `POWERSHELL_TELEMETRY_OPTOUT`
  and `POWERSHELL_UPDATECHECK` are set (each once in the file) by an `ENV`
  between the final `FROM` and the first `RUN` that starts `pwsh`.
  `[unit: test_gates_image_sets_telemetry_optout_before_pwsh]`
  (fast)
- **PSC-12 Windows proof.** Under A34 this item changes Dockerfiles and
  compose files, so the recorded Windows run is needed. It must match the
  branch head, or the diff since must touch none of those files (PS-2.9).
  **PSC-12 MET (2026-10-22).** The Windows run is at HEAD `34fc0c1`
  (PowerShell 7.6.7, Docker 29.5.2, Compose v5.1.4, project `ke-psc12-win`):
  `build.ps1`, `launch.ps1` (7/7 healthy, `/healthz` and `/readyz` 200,
  127.0.0.1 only), the refused `0.0.0.0` + prod case, and `teardown.ps1` (with
  and without `-Volumes`) all pass, the Windows-only tests pass, and
  `scripts/verify.sh fast` passes (767 tests). Evidence:
  `docs/evidence/platform-supply-chain/psc12-windows-run.txt` and
  `psc12-verify-fast.txt`. The close-out diff since `34fc0c1` (`ci.yml`
  timeout, `tests/test_stack_ready_docs.py`, docs) touches no PowerShell script,
  compose file or Dockerfile, so the proof stays current under A34.
- **PSC-17 `ke-app` ships without uv, and its scan is clean (ADR-KE-013
  amendment 1, D10; added by the architect, 2026-10-21, unit 3).** This
  is a new number, not an extension of PSC-2. PSC-2 says what is scanned
  and how; PSC-17 says what the scanned image contains. PSC-13–PSC-16
  belong to platform-sbom.
  - Given `docker/app.Dockerfile`, a `builder` stage on the pinned python
    base runs `uv sync --locked --no-dev` into `/opt/venv`. The last
    (shipped) stage uses the same base reference, byte for byte, and
    copies only `/opt/venv` and `/app` from `builder`. It has no uv
    binary, no `COPY --from=uv` and no `uv` command.
  - `PATH` starts with `/opt/venv/bin`, and the user `ke` (uid 10001),
    `USER ke` and the `CMD` are unchanged.
  - `uv.lock` pins certifi 2026.10.19 or later (GHSA-6q48-6c7w-9gw2,
    Critical). The lock diff changes only certifi. A fixed Critical
    overrides the usual settle period, and that is recorded in D10.
  - The gates image keeps uv, and its uv `FROM` reference is identical to
    the one in `app.Dockerfile`.
  - When the rebuilt `ke-app` is scanned, `scripts/scan.sh` exits 0. The
    certifi, quinn-proto (GHSA-4w2j-m93h-cj5j, High) and rustls rows are
    gone, with no new ignore entry. In the image, `command -v uv` finds
    nothing, and `python -m engine.notices` still prints its package
    table.
  - `[unit: test_app_image_final_stage_has_no_uv]` (fast, static; RED
    today)
  - `[unit: test_uv_pin_matches_in_app_and_gates_images]` (fast, static;
    a guard, proven by a recorded mutant)
  - Manual evidence: `u3-no-uv-in-ke-app.txt` (no uv, notices runs,
    certifi version) and `u3-real-scan.txt` (scan exits 0), both under
    `docs/evidence/platform-supply-chain/`. Passing this gates PSC-6.
- **PSC-18 Only a finished `full` says PASS (added by the architect,
  2026-10-22, unit 5; security u4-r1 L-3, L-4, review r1-n3).** A new
  number, not a PSC-6 sub-bullet: PSC-6 places the scan, PSC-18 is about
  what every `full` run prints at its end, whatever the stage. Design:
  ADR-KE-013 amendment 1, D4.
  - `verify.sh full` prints `== verify full: PASS (Ns) ==` exactly once,
    as its last stdout line, and only when every stage finished with rc
    0. A failing stage prints no such line.
  - The `gates-it` half of `full` prints `== gates-it: PASS ==`, never
    a `verify full: PASS` line. `fast` keeps `== verify fast: PASS ==`.
  - INT, TERM and HUP to a `full` run give exit 130, 143 and 129, with a
    `== verify full: FAIL (exit N) ==` line last and no PASS line.
  - An untrapped fatal signal (USR1 in the tests) gives
    `FAIL (stopped before the last stage; no PASS)`.
  - `offline_check.sh` never prints its PASS line on a signal: INT, TERM
    and HUP give 130, 143 and 129 with no `offline_check: PASS`.
  - `[unit: test_verify_full_only_the_outer_line_says_pass]`,
    `[unit: test_gates_it_half_prints_its_own_success_line]`,
    `[unit: test_verify_full_untrapped_signal_says_stopped_before_the_last_stage]`
    (`tests/test_stack_scripts.py`),
    `[unit: test_offline_check_signal_exits_with_its_status_and_no_pass]`
    (`tests/test_offline_check.py`), all fast with fake docker; the unit 4
    signal tests (for example
    `test_verify_full_signal_during_smoke_exits_with_its_status_and_no_pass`)
    stay green.

**SBOM and the M-NT1 remainder: moved.** PSC-13–PSC-15 moved to § "Item:
platform-sbom" (split accepted by the orchestrator, 2026-10-21), rewritten
there for the Q57 and Q58 rulings.

**Split (accepted 2026-10-21, orchestrator).** The analyst's proposal stood:
1. `platform-supply-chain` (this branch): PSC-1–PSC-12, plus PSC-17
   (added 2026-10-21, unit 3) and PSC-18 (added 2026-10-22, unit 5,
   after PSC-6). TDD order: PSC-11 → PSC-10 → PSC-1, 2, 3,
   5, 8 → PSC-4 → PSC-17 → PSC-6 → PSC-7 → PSC-9 → PSC-12
   (first tests: `docs/architecture.md` §2.6 "platform-supply-chain").
2. `platform-sbom`: PSC-13–PSC-16, opened right after this item.

Tags summary: fast covers every `unit:` test above; full covers
`[gate: image-scan]`, the PSScriptAnalyzer image build and
`ci/deployable-offline`; manual covers security's scanner provenance note,
the reviewer's wrong-hash mutation, the recorded red runs (mutant policy,
unreachable database host, planted ignore), the PSC-7 L-13 record, the PSC-9
CI measurement, the arm64 scan evidence when an arm64 run is recorded, the
PSC-17 no-uv and real-scan evidence, and the Windows run. Gate:
`scripts/verify.sh full`.

**Status at close-out (2026-10-22, documenter).** PSC-9 and PSC-12 are MET
above. The other criteria shipped in units 1-5 (commits `8900766`, `8b20fa5`,
`769b507`, `e6e1d28`, `34fc0c1`). Criteria with unit or integration tests have
them in `scripts/verify.sh full` (last unit-5 run PASS, 767 unit + 15
integration tests,
`docs/evidence/platform-supply-chain/orchestrator-u5-verify-full.txt`).
PSC-7 is evidence-only by design (checked by the reviewer and security; no
unit test). The arm64 scan evidence (PSC-2, Q59) is deferred to the next
recorded arm64 bundle run and is not in this table:

| Criteria | Unit | Evidence (under `docs/evidence/platform-supply-chain/`) |
|---|---|---|
| PSC-10, PSC-11 | 1 | `green-psc10-11-verify-full.txt`, `psscriptanalyzer-sha512.txt`, `review-u1*.md`, `review-u1-mutation-builds.txt` (PSC-10 wrong-hash mutation), `security-u1*.md` |
| PSC-1, PSC-2, PSC-3, PSC-5, PSC-8 | 2 | `u2-green-verify-full.txt`, `u2-green-real-scan.txt`, `scanner-provenance.md`, `review-u2*.md`, `review-u2-red-unresolvable-host.txt` (PSC-3), `u2-green-confirm-d3-d5.txt` (PSC-5 planted ignore), `security-u2*.md` |
| PSC-4 (units 3 and 4), PSC-17 | 3 (PSC-4 also 4) | `u3-green-verify-full.txt`, `u3-real-scan.txt`, `psc4-mutant-policy-red.txt` (PSC-4 mutant-policy red run), `u3-no-uv-in-ke-app.txt`, `review-u3.md`, `security-u3.md`; `test_verify_full_fails_when_image_scan_fails` landed in `e6e1d28` (unit 4) |
| PSC-6, PSC-7 (L-13 accepted residual) | 4 | `u4-green-verify-full.txt` (PSC-7 output at lines 1601-1914), `u4-psc7-psycopg-libs.txt`, `review-u4*.md`, `security-u4*.md` |
| PSC-18 | 5 | `u5-green-verify-full.txt`, `review-u5.md`, `security-u5.md` |

### Follow-ups (not in platform-supply-chain)

Recorded 2026-10-22 (architect, unit 5; security-u4-r1.md, review-u4-r1.md,
orchestrator ruling). None blocks this item; none can print a false PASS.
- **USR1 pin for `offline_check.sh`.** PSC-18 tests INT, TERM and HUP
  there. A USR1 subtest (an untrapped fatal signal) would pin its finished
  flag, as this test does for `verify.sh`:
  `test_verify_full_untrapped_signal_says_stopped_before_the_last_stage`.
- **r1-n4: a second signal during cleanup's teardown.** Inside verify's
  cleanup, INT, TERM and HUP still exit at once, so a second signal during
  the trap's teardown skips the FAIL line. It never prints PASS. Candidate
  fix: `trap '' INT TERM HUP` inside cleanup, as `scan.sh` does.
- **I-8: SIGKILL to `verify.sh` leaves the project behind.** The verify
  project and the orphaned stage keep running; an untrapped USR1 to verify
  alone tears down while the orphaned smoke stage runs on. Both fail closed
  (no PASS), and nothing more is possible for KILL; the project is removed
  by hand (`docker compose -p <project> down --volumes`).
- **I-9: no false PASS rests on every stage reporting a signal as
  non-zero.** All four real stages do today (security I-9). Any new stage
  script must turn a signal into a non-zero exit, and should get a signal
  test like PSC-18's.

Recorded 2026-10-21 (architect, unit 4 rework 1; security-u4.md). Neither
blocks this item.
- **`require_auth="scram-sha-256"` on every libpq connection (L-13
  hardening; goes with `auth-audit`).** Today the one site is
  `engine/readiness.py:89`; any later connection site gets it too. libpq
  18 then refuses GSS, SSPI, md5 and cleartext before any krb5 call, which
  shuts the last server-reachable path into the vendored krb5 (a
  compromised postgres answering `AuthenticationGSS`). It is engine code
  and needs its own TDD: extend the PS-2.5 pair
  (`test_postgres_probe_disables_gss_encryption`,
  `test_every_postgres_connect_in_engine_disables_gss_encryption`) to
  require it, and confirm the stack postgres uses SCRAM (a live readyz in
  `full`).
  - L-13 closes under Q64 (platform-sbom U0). Under PSC-25 the image's
    libpq is Debian 12's (the PostgreSQL 15 series), which has no
    `require_auth`, and the vendored krb5 this guarded is gone; whether
    this follow-up is kept, re-scoped or retired is Q66. *(Added
    2026-10-22, analyst, Q64.)*
  - Re-rated by security at U0 review (A66).
  - **L-13 CLOSED 2026-10-23 by security (U0,
    `docs/evidence/platform-sbom/u0/security.md`).** Security's A66
    re-rating: **low, re-scoped (not retired), goes with `auth-audit`,
    non-blocking.** `require_auth` cannot be added on libpq 15, and libpq
    15 still calls krb5 when a server asks for GSS auth (`gssencmode`
    stops GSS encryption only). The bullet is replaced by: *(Amended 2026-10-23, analyst, U0 review.)*
    1. Server side, now: `password_encryption=scram-sha-256` and a TCP
       `pg_hba` that is `scram-sha-256` only, proved by a live `full` check
       (`SHOW password_encryption`, `pg_hba_file_rules`).
    2. `channel_binding=require` on the client, only if `auth-audit` adds
       TLS to postgres.
    3. `require_auth=scram-sha-256` at every connect site, with the PS-2.5
       pair extended, once the base's libpq is 16 or later.
- **Security I-2: `scan.sh` saves by tag, not image ID**
  (`scripts/scan.sh:92`). A second `full` from the same checkout (same
  `wt-` tag) that rebuilds between build and scan could swap the image
  scanned. Candidate fix: pass the image ID recorded after build.

Recorded 2026-10-21 (architect, unit 3, ADR-KE-013 amendment 1, D10).
Neither blocks this item.
- **uv upgrade for the gates image and the `ke-app` builder.** Both still carry the uv
  binary with quinn-proto 0.11.14 and rustls 0.23.40. Neither image ships
  or is scanned.
  - When a uv release carries quinn-proto 0.11.15 or later and rustls
    0.23.45 or later, bump the one pin in both Dockerfiles in a single
    commit, with a provenance check.
  - Nobody has yet checked whether such a release exists.
- **pip in `ke-app`.** The base image's pip 25.0.1 has fixed findings, all
  Medium or Low and below the threshold. Dropping pip from the final stage
  is a candidate.

Recorded 2026-10-21 (orchestrator ruling, u1 rework 1). None blocks this
item.
- **N3: compare the reported version with the ARG.** In
  `tests/test_stack_scripts.py`, compare `(Get-Module PSScriptAnalyzer).Version`
  (which the test already reads) with `ARG PSSCRIPTANALYZER_VERSION`,
  instead of matching the `# PSScriptAnalyzer x.y.z (ARG below)` comment.
  The comment, and the comment half of
  `test_gates_image_psscriptanalyzer_version_agrees`, can then go.
- **N7: the same masking gap in the other pins.** Harden `_is_sha_check`
  and `_assert_pinned` (`tests/test_gates_docker_cli.py`) for the pwsh,
  Docker CLI and compose pins with the PSC-10 rules: the pipeline ends in
  the sha checker; not negated, conditional or backgrounded; no `set +e`
  or `set +o errexit` in the `RUN`; nothing writes the download path
  between the check and its use. Also cover these (PSC-10 survivors, u1
  re-review and re-check, 2026-10-21):
  - R1-N1: match the download path as a whole word, so a prefix twin such
    as `/tmp/psa.nupkg.ok` cannot satisfy the check's path match;
  - R1-N3 and L-U1R1-2 (this list is not exhaustive). PSC-10 now kills
    these variants: a function or alias for `sha512sum` inside the
    `RUN`, the `$(sha512sum ...)` self-hash, the `sed` stage, and any
    extra pipeline stage. These survive and need N7 rules:
    - a `PATH` shadow of `sha512sum` from an earlier layer (S10);
    - a self-hash or pin overwrite with a hasher other than `sha512sum`
      (S3d; assignment or `export` of the pin, S4c/S4d);
    - feed tampering: `/dev/null` as the checked file via `printf %.0s`
      (S2/S2b) or a parameter-expansion feed (S8);
    - a redirect attached to a flag (review R2-N1);
    - a later-layer overwrite of the module directory (S6/S7, already
      its own item below).
  - Also port two PSC-10 rules: exactly two stages (an `echo`/`printf`
    feed, then the checker) with exactly one checker word in the `RUN`
    ("exactly two stages, exactly one checker"; security M-U1R1-1).
  - Optional hardening, which would kill S2/S2b/S8/S3d: the feed's only
    argument is `"$PSSCRIPTANALYZER_SHA512  <path>"`, with no `$(` or
    backtick inside the quotes. Add "no assignment, read or export of
    the pin in the `RUN`" (S4c/S4d) and "no `PATH` change in an earlier
    layer" (S10).
- **RECOMMENDED: a behavioural check of the pin.** A `full`-mode test
  builds the gates image's module stage with a deliberately wrong
  `PSSCRIPTANALYZER_SHA512` and requires the build to fail at the check.
  Unlike the static detectors it catches every masking class at once,
  and it generalises to the pwsh, Docker CLI and compose pins (N7). Its
  CI cost and network use are not yet known and must be measured on CI.
- **R1-N2 / I-U1R1-3: the module path is owned by one `RUN`.** Only the
  module `RUN` may name `/Modules/PSScriptAnalyzer`, and no later `COPY`
  or `RUN` may overwrite it (an unpinned second download unpacked into
  the module directory passes today). This is an image-wide check, outside
  PSC-10; an image-wide "every fetch is hash-checked" invariant could
  join it.

---

## Item: platform-sbom

Status: **not started.** Opens right after `platform-supply-chain` (split
accepted by the orchestrator, 2026-10-21), on `agent/platform-sbom`.
PSC-13–PSC-15 moved here from `platform-supply-chain` and were rewritten on
2026-10-21 (architect) for the Q57 and Q58 rulings; PSC-16 is new. The
analyst confirms the criteria when the item opens. No mechanism is designed
yet: the item's architect writes an ADR for the SBOM generator (a new pinned
dependency) and the source archive.

*Confirmed/amended by the analyst, 2026-10-22* (item opened; checked against
`docker/app.Dockerfile`, `scripts/bundle.sh`, `scripts/install.sh`,
`scripts/install.ps1`, `scripts/offline_check.sh`, `docker-compose.scan.yml`
and `NOTICE.md` at `737750d`). The Q57 and Q58 rulings are untouched. What
changed:
- PSC-13: the image is named by its `ref` and by one value, the image ID of
  the tar; "runtime package" defined.
- PSC-14: `uv` removed (PSC-17 took it out of `ke-app`; it runs only in the
  unshipped `builder` stage). The shipped stage's real contents are named
  instead: CPython 3.12, the Debian 12 packages and the base's pip. The 15
  vendored files are named from the PSC-7 evidence; arm64 is covered.
- PSC-15: obligations and recommendation unchanged; its check also covers
  the components PSC-22 names; each bundle's `sources/` is self-sufficient.
- PSC-16: also measures the manifest size and the install's tmpfs (memory)
  use.
- The three open points are now Q61-Q63 in `docs/open-questions.md`.
- New: PSC-19 (e2e) to PSC-24. TDD order extended.

Outcome metric moved: **neither.** No draft is reviewed and no rule is
ratified because of this item. It closes the M-NT1 remainder
(`docs/evidence/platform-offline/audit-nt.md`, `audit-nt2.md`): the bundle
redistributes GPL-family binaries with no source offer, and does not say in
full what it contains.

- Source: `docs/handoffs/platform-supply-chain.md` (human rulings Q57 and
  Q58; orchestrator split ruling).
- Settled, not re-opened here:
  - Q57: SPDX 2.3 JSON, one per bundled image, generated offline at bundle
    time and shipped in the bundle;
  - Q58: source offers are built now, not deferred to SFU legal/IP advice;
  - R4/A43: the Neo4j GPL-3.0 listing and the Phoenix exception;
  - R7: the bundle holds the stack images only, so `ke-gates` and `dind`
    need no SBOM and no source;
  - Q48: the hash-provenance rule, for any new pinned tool or fetched
    source.
- Not ruled and not blocking (Q58): who asks SFU legal/IP, and whether
  distribution outside SFU is planned.
- Ruled by the human (`docs/open-questions.md` § platform-sbom, raised by
  the analyst 2026-10-22):
  - Q61 ruled 2026-10-22: fail closed on a failed or checksum-mismatched
    source fetch (one call, no retry, as Q56(b));
  - Q62 ruled 2026-10-22: Q60's 3-min trigger applies to this item's added
    CI time (above 180 s on the slower of two green runs, the measurement
    goes to the human before the timeout is raised);
  - Q63 ruled 2026-10-22: a reduced verify set, the full set for every
    operator bundle.
  - Q64 ruled 2026-10-22: psycopg built against Debian's libpq
    (`psycopg[c]`, the Q42 structural fix); `psycopg_binary.libs` is
    removed, its libraries become Debian packages, and no `srpm` source
    kind is built. Built as PSC-25, unit U0; L-13 closes. PSC-13, PSC-14,
    PSC-15, PSC-19 and PSC-22 are amended to match. *(Amended 2026-10-22, analyst, Q64.)*
- Orchestrator rulings on ADR-KE-016's open points (2026-10-22, handoff
  "rulings on ADR-KE-016 open points"). *(Amended 2026-10-22, analyst, Q64.)*
  - (1) The SBOM names its image by the tar's config digest, not by an
    image ID (PSC-13, PSC-19).
  - (2) SBOMs, sources and the notice copies sit under `app/`, the only
    directory install publishes. PSC-19's "installed copy" is that `app/`.
  - (4) The classifier is wider than PSC-15's licence list: it also treats
    AGPL, GPL-1.0 and LGPL-2.0, in any form, as GPL-family. Accepted as
    the more conservative reading; PSC-15's list is the minimum.
- Q65 and Q66 (`docs/open-questions.md` § platform-sbom, raised by the
  analyst 2026-10-22) ruled by the orchestrator 2026-10-22: A65, the
  shipped `ke-app` has no psycopg-binary and uses `psycopg-c` on Debian's
  libpq, and how the lock, dev hosts and `ke-gates` resolve psycopg is the
  architect's (no CLAUDE.md or AGENTS.md change, no dev-host toolchain,
  `--locked` everywhere, the `uv run` log step keeps working on Windows);
  A66, accept Debian 12's libpq 15, no apt.postgresql.org, and security
  re-rates the `require_auth` follow-up at U0 review. *(Amended 2026-10-22, analyst, A65/A66.)*

- **PSC-13 SBOM per bundled image (Q57).**
  - When `bundle.sh` builds a bundle, it writes one SPDX 2.3 JSON document
    for each image in `bundle.json`: `ke-app`, `ke-gateway` and every
    third-party stack image (postgres, neo4j, valkey, phoenix).
  - Each is generated offline, at bundle time, from the image tar the bundle
    ships: no network, no pull and no Docker socket in the generator
    container. The generator image is pinned by digest, with its provenance
    recorded as in PSC-1, and is not in the bundle.
  - Each document is listed in the bundle manifest with its hash, and names
    the image it describes by the `ref` in `bundle.json` and by the config
    digest of the tar it was generated from (`sha256:<hex>`, the `Config`
    entry of the tar's `manifest.json`), which is the same whichever image
    store loads the tar (R2); for a vendor image the pinned index digest is
    in the `ref`. *(Amended 2026-10-22, analyst: "digest or ID" made one
    value a test can compare.)* *(Amended 2026-10-22, analyst, Q64.)* Orchestrator ruling 1: the
    image ID `install` sees differs by store (R2), and a named load prints
    `Loaded image: <ref>`, so the config digest replaces it.
  - Each has the SPDX 2.3 required fields: `spdxVersion: "SPDX-2.3"`,
    `dataLicense: "CC0-1.0"`, a `documentNamespace` unique to the bundle,
    and `creationInfo` naming the generator and its version.
  - `ke-app`'s document lists every runtime package in `uv.lock` with its
    locked version. A runtime package is one the `ke-app` builder's final
    sync, `uv sync --locked --no-dev --group pq-c --no-binary-package
    psycopg-c`, installs into `/opt/venv`; that set includes `psycopg-c`
    (PSC-25). `test_sbom_lists_every_locked_runtime_package` takes the
    expected set from this definition. *(Amended 2026-10-23, analyst, U0 review.)* Every document lists the image's OS packages (dpkg or
    apk) with their versions and declared licences, as the generator
    reports them.
  - `[unit: test_bundle_has_sbom_per_image]`,
    `[unit: test_sbom_is_spdx_2_3]`,
    `[unit: test_sbom_lists_every_locked_runtime_package]` (fast, stubbed);
    `ci/deployable-offline` (full) generates the documents from the real
    images, and install checks them through the manifest.
- **PSC-14 Notices complete for `ke-app` (M-NT1).** *(Amended 2026-10-22,
  analyst: uv left `ke-app` with PSC-17.)* *(Amended 2026-10-22, analyst, Q64.)*
  - `NOTICE.md` has a paragraph for what `ke-app`'s shipped (last) stage
    holds besides `/opt/venv` and `/app`, pinned to the base digest in
    `docker/app.Dockerfile`, each with its licence: CPython 3.12 under
    `/usr/local`; the Debian 12 (bookworm) packages of
    `python:3.12-slim-bookworm` (licences under `/usr/share/doc/*/copyright`,
    and in the SBOM, PSC-13); and the base's own pip in its system
    site-packages, which is outside `uv.lock` and so outside the generated
    package table (the developer confirms this in the image).
  - It does not name uv as shipped: uv runs only in the `builder` stage,
    which does not ship (PSC-17). If pip is dropped from the last stage
    (platform-supply-chain follow-up), its line goes in the same change.
  - `ke-app` ships no `psycopg_binary.libs` (PSC-25); libpq and its
    dependencies are Debian packages covered by the SBOM and the `deb`
    source kind. The base paragraph above therefore also names the Debian
    packages the last stage adds to the base (`libpq5` and what it pulls
    in, PSC-25), and `NOTICE.md` names `libpq5` as a Debian package under
    the PostgreSQL licence. *(Amended 2026-10-22, analyst, Q64.)* The 15-library vendored table and
    its drift check against the image's `psycopg_binary.libs` are removed:
    nothing is vendored to list, and PSC-25's full check proves the
    directory is absent from the real image.
  - `[unit: test_notice_has_ke_app_base_paragraph]`,
    `[unit: test_notice_names_libpq_as_a_debian_package]` (fast, stubbed:
    `NOTICE.md` names `libpq5` as a Debian package under the PostgreSQL
    licence and has no table of libraries vendored in psycopg-binary).
    `test_notice_lists_psycopg_binary_vendored_libs` is renamed to this
    test, with its assertion replaced; the real-image drift check is
    retired in favour of `[full: ke-app psycopg impl is c and links system
    libpq]` (PSC-25). *(Amended 2026-10-22, analyst, Q64.)*
- **PSC-15 GPL source offers, built now (Q58).**
  - *Obligations to meet.*
    - **GPL-2.0 §3.** Whoever distributes the object code must do one of:
      (a) accompany it with the complete corresponding machine-readable
      source; (b) accompany it with a written offer, valid for at least
      three years, to give any third party that source for no more than
      the cost of physically distributing it; (c) pass on such an offer,
      only for non-commercial distribution of object code received with
      one. In this bundle: busybox, apk-tools and ssl_client (Alpine, in
      valkey and ke-gateway's base), the GPL-2.0 Debian packages in the
      postgres, neo4j, phoenix and ke-app bases, and the Temurin OpenJDK
      in the neo4j image (GPL-2.0 with the Classpath Exception; L-NT1).
    - **GPL-3.0 §6.** Whoever conveys the object code must provide the
      Corresponding Source by one of: (a) in a physical product,
      accompanied by the source on a durable physical medium; (b) in a
      physical product, a written offer valid for at least three years;
      (c) passing on such an offer, occasionally and non-commercially;
      (d) when the object code is offered from a designated place,
      equivalent access to the source from the same place, for as long as
      the object code is offered, with the distributor still obligated
      when a third party hosts the source; (e) peer-to-peer, by saying
      where the source is. In this bundle: Neo4j Community (GPL-3.0) and
      the GPL-3.0 Debian packages.
    - The LGPL components carry equivalent source terms: psycopg's
      compiled extension (LGPL-3.0, which applies GPL-3.0 §6 to conveying
      the library's object code), the LGPL-2.1 libraries among the image's
      Debian packages (LGPL-2.1 §4, which allows only the accompanying
      source or equal access from the same place, with no written-offer
      option) and glibc. The mechanism covers
      them too. *(Amended 2026-10-22, analyst, Q64.)* They are no longer vendored in
      `psycopg_binary.libs` (PSC-25), so their source is the `deb` kind;
      psycopg's compiled extension is now `psycopg-c`, built from its
      locked sdist.
  - *Options.*
    1. **A source archive in the bundle** (GPL-2.0 §3(a); for GPL-3.0 the
       source travels with the object code by the same means). The bundle
       carries `sources/`: the exact-version source of every GPL-family
       component the SBOMs list, each file hashed in the manifest, and an
       index mapping each SBOM package to its source file.
    2. **A written offer** (GPL-2.0 §3(b); GPL-3.0 §6(b)). An offer text in
       the bundle, valid for at least three years, naming who supplies the
       source. It needs a named contact and an SFU commitment, and the exact
       sources must still be archived for three years so that the offer can
       be met. GPL-3.0 §6(b) covers physical products only, so for a bundle
       handed over as files it does not cover Neo4j or the other GPL-3.0
       components.
  - **Recommended: option 1, the source archive in the bundle.** The
    written offer still needs the same archive, kept for three years, plus
    a contact and an organisational commitment, and it does not cover
    GPL-3.0 for a bundle of files. The archive also keeps each bundle
    self-sufficient offline, which is how the product is deployed.
    - Sources are fetched at bundle time on the build host, which already
      has the network for builds, by exact version: the Debian source
      packages matching each image's dpkg versions; the Alpine aports and
      upstream tarballs for each image's release; Neo4j's source at its
      tag; the source of the exact Temurin build; psycopg's sdist from
      `uv.lock`. Each is checked against the upstream checksum where one
      is published (Debian `.dsc`, Alpine `APKBUILD` sha512sums, the
      `uv.lock` hash), in the Q48 form. The SBOMs stay offline (Q57).
    - Source does not depend on the architecture. Whether amd64 and arm64
      bundles share one source set, where the package versions match, is a
      design choice. Each bundle's `sources/` still holds every source its
      own SBOMs need (PSC-21).
    - A failed or mismatched fetch: Q61. Which source set the verify bundle
      carries: Q63.
    - *Cost (estimate, not a measurement):* about 1–2.5 GB of disk per
      bundle (today's bundle is 941 MiB amd64, 2.4 GiB arm64), dominated by
      OpenJDK, the Debian runtime and toolchain sources across four
      Debian-based images (glibc, the gcc runtime, coreutils, util-linux,
      perl, systemd's libraries and others) and Neo4j. Bundle time is
      dominated by the fetch, likely minutes on CI. Both are measured on
      CI (PSC-16).
  - Criteria:
    - Given a bundle, every package that an SBOM lists under a GPL-family
      licence (GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, in any `-only`,
      `-or-later` or `WITH`-exception form) has an entry in the `sources/`
      index, or a recorded exemption whose reason security has reviewed. A
      drift check fails otherwise. That list is the minimum: the check also
      treats AGPL, GPL-1.0 and LGPL-2.0 as GPL-family (orchestrator ruling
      4). *(Amended 2026-10-22, analyst, Q64.)*
    - Every source file is in the bundle manifest with its SHA-256, and
      matches the upstream checksum recorded when it was fetched.
    - The notices point to `sources/`. They claim that a source obligation
      is met only for components whose source is in the bundle, and keep
      the L-NT1 wording ("Upstream source: <url>") for anything else.
      Security reviews the wording.
    - `[unit: test_every_gpl_package_has_source]`,
      `[unit: test_source_archive_hashes_in_manifest]` (fast, stubbed SBOM
      and index); the same checks run on the real bundle in
      `ci/deployable-offline` (full).
    - The first check also covers the components PSC-22 names, whatever
      licence the generator reports for them. *(Added 2026-10-22,
      analyst.)*
- **PSC-16 CI cost and disk measured on CI.**
  - Two green CI runs record, from the runner's per-line timestamps: the
    SBOM generation per image, the source fetch, and the whole job; plus
    the bundle size with and without `sources/` and the free disk at the
    offline stage. Saved under `docs/evidence/platform-sbom/ci/` with the
    run ids. Local timings are informational only.
  - The CI runner had 9.1 GiB free at the offline stage against the 7 GiB
    floor (R6). A source set of 1–2.5 GB in the verify bundle can break the
    floor, so the floor is re-derived from the measurement (as R6 was) in
    the same item. The floor is never lowered to pass.
  - The item re-measures PS-3.4 if it adds a minute or more on CI. Whether
    Q60's 3-min trigger also applies: Q62.
  - *(Added 2026-10-22, analyst.)* The same two runs also record the
    `MANIFEST.sha256` size against install's 1 MiB cap, and the `/install`
    tmpfs use in the offline client with the runner's free memory at that
    point. Install's staging copy is held in memory, about the bundle's size
    (R6), so `sources/` adds to memory as well as disk. What the verify
    bundle carries is Q63.

- **PSC-19 End to end: the shipped SBOMs and sources survive an offline
  install (added 2026-10-22, analyst; human rule of 2026-10-22, every
  product item ships its own e2e test).** This item changes what the bundle
  hands an operator, so it needs one. It extends `ci/deployable-offline`
  and adds no new stack.
  - Given the bundle that `offline_check.sh` builds in `verify.sh full` from
    the real images, when the offline client installs it with `install.sh`
    (no route out), then, reading only the installed copy:
    - every SBOM is listed in `MANIFEST.sha256`, parses as SPDX 2.3, and
      names one `bundle.json` `ref` and the config digest of that image's
      tar (`manifest.json` `Config`), the same value whichever store
      install loaded it into (R2); each `bundle.json` image has exactly one
      SBOM; *(Amended 2026-10-22, analyst, Q64.)*
    - the PSC-15 checks pass on the installed files: every GPL-family
      package has an index entry or a reviewed exemption, and every source
      file's SHA-256 matches the manifest and the recorded upstream
      checksum;
    - the notices point to `sources/`.
  - The source set the verify bundle carries follows Q63. If it is reduced,
    the same checks run on a full operator bundle in a recorded run, saved
    under `docs/evidence/platform-sbom/`.
  - The installed copy is the `app/` install publishes; SBOMs, sources and
    the notice copies sit under it (orchestrator ruling 2). *(Amended 2026-10-22, analyst, Q64.)*
  - `[e2e: test_installed_bundle_has_sboms_and_sources]` (full, in
    `ci/deployable-offline`); the existing deployable-offline checks stay
    green.
- **PSC-20 The SBOM generator runs like the scanner (PSC-1-PSC-3, PSC-8;
  added 2026-10-22, analyst).**
  - It is pinned by its multi-arch index digest (`@sha256:` + 64 hex, no
    tag-only reference). Security records its provenance in the PSC-1 form
    before the pin is committed:
    `docs/evidence/platform-sbom/generator-provenance.md`.
  - Its container has no network (`network_mode: none` or `--network
    none`), a read-only root filesystem with `/tmp` as tmpfs, `cap_drop:
    ALL` and `no-new-privileges`. It has no Docker socket and no
    `DOCKER_HOST`. The image tar is mounted read-only, its only writable
    mount is the SBOM output, and its update check is off.
  - Its run carries a label of its own, as the notices run does
    (`<project>-notices`), so it never looks like part of a stack project.
  - `bundle.sh` never pulls it. When it is absent, `bundle.sh` refuses
    before anything is written to `--out`, naming the reference. The ADR
    names the step that pulls it.
  - No bundle manifest entry names the generator image (as PSC-8).
  - `[unit: test_sbom_generator_is_pinned]`,
    `[unit: test_sbom_generator_runs_without_network_or_privileges]` (fast,
    static); `[unit: test_bundle_refuses_when_sbom_generator_absent]` (fast,
    fake docker); `[unit: test_bundle_has_no_sbom_generator]` (fast).
- **PSC-21 Per-arch bundles (Q49, Q51, Q59 form; added 2026-10-22,
  analyst).**
  - Each bundle's SBOMs are generated from its own tars on its build
    daemon's architecture, with no `--platform` and no emulation, and each
    SBOM records that architecture.
  - Each bundle's `sources/` holds every source its own SBOMs need. Any
    sharing between amd64 and arm64 happens at build time only; no bundle
    refers to another.
  - `verify.sh full` proves the native bundle (amd64 on CI and the dev
    host). The arm64 bundle's SBOMs, the PSC-14 drift check, the PSC-15
    checks and PSC-19 run in the next recorded arm64 run (Q51 form), saved
    under `docs/evidence/platform-sbom/arm64/`. Whether the item may close
    before that run is the orchestrator's call; platform-supply-chain
    deferred its arm64 scan evidence the same way (PSC-2).
- **PSC-22 An obligation is not hidden by what the generator reports
  (added 2026-10-22, analyst).** *(Amended 2026-10-22, analyst, Q64.)* Generators miss things: the
  scanner catalogued none of the 15 files in `psycopg_binary.libs` (PSC-7),
  which PSC-25 removes from `ke-app`. The clause that injected those files
  into `ke-app`'s SBOM is dropped with them.
  - The PSC-15 source check covers these whatever licence the generator
    reports: busybox, apk-tools and ssl_client; the Temurin OpenJDK in
    neo4j; Neo4j Community; psycopg, with `psycopg-c`, its compiled
    extension (LGPL-3.0-only, PSC-25); and glibc. Each has a `sources/`
    entry or an exemption whose reason security has reviewed.
  - Packages the generator reports with no licence (none or
    `NOASSERTION`) are listed per image, with a count, in the bundle output
    and the evidence. Security reviews the list whenever a digest or the
    lock changes; any it finds GPL-family needs a source entry or a
    reviewed exemption.
  - `[unit: test_named_gpl_components_need_source_whatever_the_generator_says]`,
    `[unit: test_unlicensed_packages_are_reported]` (fast, stubbed).
    `test_sbom_lists_psycopg_binary_vendored_libs` is retired: nothing is
    vendored to inject, and PSC-25's full check proves it. *(Amended 2026-10-22, analyst, Q64.)*
- **PSC-23 The source fetch is a named, bounded network step (added
  2026-10-22, analyst).**
  - SBOM generation stays offline (Q57); the fetch is the item's only new
    step with a route out. `scripts/bundle.sh`'s header says today that it
    "makes no network call". Where the fetch runs is the ADR's choice, and
    that header, CLAUDE.md's verification paragraph and the README then say
    where the route out is. CLAUDE.md is the human's: its change needs the
    human's approval and lands in the same commit, as for Q56(a).
  - Every fetch is HTTPS only (`--proto '=https' --proto-redir '=https'
    --tlsv1.2`, as PSC-10), to hosts listed in one committed place. The ADR
    records that list for SFU egress, as Q56's note did for the scan
    database host.
  - A fetched file is checked (PSC-15) before anything else reads it, and
    ships as fetched: it is never unpacked, built or run on the build host
    or in a gate service.
  - The fetch takes no key from the caller's environment or `.env`; the two
    model keys stay the only ones (PSC-6). `gates` and `gates-it` stay
    offline (Q56(a)).
  - A failed fetch or a checksum mismatch: Q61.
  - `[unit: test_source_fetch_is_https_only_to_listed_hosts]`,
    `[unit: test_source_fetch_checks_before_use]` (fast, fake fetch);
    `test_verify_full_takes_no_caller_ke_key_but_the_model_keys` stays
    green.
- **PSC-24 No partial bundle, and the manifest rules hold (added
  2026-10-22, analyst).**
  - Any SBOM, index or source failure makes the bundle step exit non-zero,
    naming the stage and the image or file. It leaves no `MANIFEST.sha256`
    and no release record, so install cannot accept what is left. Checks
    that can run before any write still run before it, as today.
  - Every file under the SBOM and source directories passes the manifest
    path rule that `bundle.sh`, `install.sh` and `install.ps1` enforce today
    (`[A-Za-z0-9._-]` per path segment). Debian source file names often
    hold `+` or `~` (today's `ke-app` has krb5 `1.20.1-2+deb12u5` and
    OpenSSL `3.0.22-1~deb12u1`, PSC-7 evidence). Either such files are
    stored under names that pass and the index records each upstream file
    name and URL, or the rule changes in all three scripts with security's
    review and tests. It is never loosened silently.
  - `MANIFEST.sha256` stays under install's 1 MiB cap, which is not raised
    to pass (measured, PSC-16).
  - Install refuses a bundle with a source or SBOM file missing, changed or
    unlisted. The manifest checks already do this; the tests pin it for the
    new paths in `install.sh` and `install.ps1`.
  - `[unit: test_bundle_writes_no_manifest_when_sbom_or_source_fails]`
    (fast, fake docker), `[unit: test_source_file_names_pass_the_manifest_rule]`
    (fast, stubbed index), `[unit: test_install_refuses_tampered_or_missing_source_file]`
    (fast; `install.sh` and `install.ps1`).

- **PSC-25 psycopg on Debian libpq (Q64, unit U0).** *(Added 2026-10-22,
  analyst, Q64.)* The Q42 structural fix, ruled by the human. `ke-app`
  stops shipping psycopg-binary and the 15 native libraries it vendors in
  `psycopg_binary.libs` (PSC-7). psycopg uses its C implementation, built
  against Debian 12's libpq, so libpq and its dependencies become Debian
  packages: the SBOM catalogues them (PSC-13), Debian's security updates
  patch them, the scan sees them (PSC-4) and the `deb` source kind covers
  them (PSC-15). L-13 closes. It is unit U0, before PSC-14, because PSC-14
  and PSC-22 assume `ke-app` vendors nothing.
  - *Lock.* *(Amended 2026-10-22, analyst, A65/A66.)* *(Amended 2026-10-23, analyst, U0 review.)* The `ke-app`
    builder's resolved set (what its final sync, `uv sync --locked
    --no-dev --group pq-c --no-binary-package psycopg-c`, installs into
    `/opt/venv` in the builder stage, on its platform) holds `psycopg-c` at psycopg's version, from
    its locked sdist with its sha256, and no `psycopg-binary`. Whether
    `uv.lock` still holds psycopg-binary under a non-Linux marker or a uv
    extra, for dev hosts and `ke-gates`, follows ADR-KE-016 within A65's
    limits: no CLAUDE.md or AGENTS.md change, no C toolchain on dev hosts,
    `--locked` everywhere, and the `uv run` log step keeps working on
    Windows. `uv.lock` is regenerated inside the gates image (CLAUDE.md,
    Generated artifacts) and the gate scripts' `--locked` runs stay green.
  - *Builder stage.* `psycopg-c` is compiled from source in `ke-app`'s
    `builder` stage against that stage's Debian `libpq-dev`. The compiler,
    `libpq-dev` and every other `-dev` or build-only package are installed
    in the builder stage only.
  - *Runtime stage.* The shipped (last) stage installs Debian's `libpq5`
    and only the packages it needs that the base lacks, each pinned to an
    exact version (`<package>=<version>`, as `gates.Dockerfile` pins
    shellcheck), with no recommended packages, and removes
    `/var/lib/apt/lists/*` in the same layer. It holds no compiler (`gcc`,
    `cc`, `make`) and no `-dev` package.
  - *No vendored copy.* `/opt/venv` in the shipped image has no
    `psycopg_binary` directory, no `psycopg_binary.libs` directory and no
    `psycopg_binary-*.dist-info`.
  - *C implementation, system libpq.* In the real image,
    `psycopg.pq.__impl__ == "c"`. The `libpq.so.5` the extension loads is
    a file the dpkg package `libpq5` owns, not a copy under `/opt/venv`,
    and `psycopg.pq.version()` matches the installed `libpq5` upstream
    version. A smoke check in `full` asserts all three against the image
    `verify.sh full` builds.
  - *Still connects.* The stack smoke in `full` stays green, and the api's
    postgres readiness probe connects to postgres through the new build
    (live `readyz` reports postgres ready).
  - *gssencmode unchanged.* Every postgres connection keeps
    `gssencmode="disable"`. Today the one site is `_probe_postgres` in
    `engine/readiness.py` (line 91), pinned by
    `test_postgres_probe_disables_gss_encryption` and
    `test_every_postgres_connect_in_engine_disables_gss_encryption` (PS-2.5,
    `tests/test_stack_readiness.py`). Debian's libpq5 is also built with
    GSSAPI, so the mitigation still applies. Both tests stay green and
    unchanged.
  - *Scan.* The image scan (PSC-4) still passes under the pinned policy
    (the Q42 threshold, `docker/scan-ignore.yaml`, the 90-day cap). If it
    newly reports a fixed High or Critical in `libpq5` or a package it
    pulls in, that is handled under PSC-4 and PSC-5 (upgrade the pin, or a
    time-limited ignore entry whose reason security confirms), never by
    loosening the policy or the threshold.
  - *Size.* `ke-app`'s image size and its bundle tar size, before and
    after, are recorded under `docs/evidence/platform-sbom/`. No ceiling
    exists today; the numbers feed PSC-16's floor derivation.
  - *Notices.* `NOTICE.md`'s psycopg section names `psycopg` and
    `psycopg-c` (both LGPL-3.0-only, each with its locked sdist URL and
    sha256) instead of psycopg-binary. The notices run (PS-3.8) stays
    green; stubbed fixtures that model psycopg-binary as a runtime package
    (`tests/test_offline_bundle.py`) move to `psycopg-c`.
  - *Windows (A34).* The Dockerfile changes, so, as for PSC-12, the
    Windows proof is recorded under `docs/evidence/platform-sbom/` before
    the unit commits: the PS-2.9 PowerShell `build.ps1`, `launch.ps1` and
    `teardown.ps1` proof, plus `scripts/verify.sh fast` run on Windows.
    It must match the branch head, or the diff since must touch none of the
    A34 files (PS-2.9). Recorded in
    `docs/evidence/platform-sbom/u0/windows-run.txt`. *(Amended 2026-10-23, analyst, U0 review.)*
  - *arm64.* The same image checks (C implementation, system libpq, no
    `psycopg_binary*`) run on the arm64 image in the next recorded arm64
    run (PSC-21).
  - Tests:
    - `[unit: test_ke_app_resolves_psycopg_c_not_binary]` (fast, offline):
      the set `uv.lock` resolves for the `ke-app` builder, with the
      builder's flags and platform (for example `uv export` or `uv tree`
      with `--locked --no-dev --group pq-c` for Linux on the image's
      architectures; *(Amended 2026-10-23, analyst, U0 review.)*),
      holds `psycopg-c` at psycopg's version and no `psycopg-binary`.
      Control: a lock or dependency fixture under which the builder's
      platform resolves `psycopg-binary` fails. Renamed from
      `test_lock_has_no_psycopg_binary`, because the lock itself may still
      name psycopg-binary for other platforms (A65). *(Amended 2026-10-22, analyst, A65/A66.)*
    - `[unit: test_runtime_stage_has_no_compiler]` (fast, static check of
      `docker/app.Dockerfile`): the last stage installs `libpq5=<version>`
      with the apt lists removed in the same `RUN`, and installs no
      compiler and no `-dev` package; the builder stage installs
      `libpq-dev`. Controls: a fixture with `gcc` or `libpq-dev` in the
      last stage fails, and so does an unpinned `libpq5`.
    - `[full: ke-app psycopg impl is c and links system libpq]` (smoke
      check in the real image).
    - The stack smoke, `[gate: image-scan]` and the two PS-2.5
      gssencmode tests stay green.

TDD order: PSC-14 → PSC-13 → PSC-15 → PSC-16. *Proposed by the analyst
(2026-10-22), for the architect to confirm:* PSC-14 → PSC-20 → PSC-13 →
PSC-22 → PSC-15 → PSC-23 → PSC-24 → PSC-19 → PSC-16, with PSC-21 at the
next recorded arm64 run. *(Amended 2026-10-22, analyst, Q64.)* PSC-25 (U0) comes first:
PSC-25 → PSC-14 → PSC-20 → PSC-13 → PSC-22 → PSC-15 → PSC-23 → PSC-24 →
PSC-19 → PSC-16, with PSC-21 at the next recorded arm64 run. Gate: `scripts/verify.sh full`; a recorded Windows
run under A34 if the item changes Dockerfiles, compose files or a
PowerShell script (`install.ps1` included, Q45).

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
