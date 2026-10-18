# Handoff: platform-skeleton

Outcome metric moved: neither directly. It makes the product deployable,
which is a precondition for any reviewer or ratifier to act.
Spec: `docs/requirements.md` § "Item: platform-skeleton". Design: `docs/architecture.md` §2 and ADR-KE-002/003.
Base: `agent/harness-claude-code` @ a11842d (the remote has no `main`).

## 2026-10-18 — orchestrator: item opened
- Plan approved by the human on 2026-10-18. The answers to Q1–Q17 stand as assumed, except Q3, which is resolved (local Docker).
- Carry-in follow-ups from `docs/handoffs/archive/harness-claude-code.md`:
  - CI: the checkout action targets Node 20 (move to a v5 SHA), and `ubuntu-latest` moves to Ubuntu 26, so pin it.
  - Hook M4 (CR) and the N16/N17 nits.
  - Review N3: once `tests/integration/` exists, `scripts/test.sh` runs it twice.
- Next: the analyst refines the acceptance criteria (first review by the ported analyst); the architect then designs.

## 2026-10-18 — analyst: acceptance criteria reviewed
- Asked: make the platform-skeleton criteria complete, testable and scoped; decide carry-ins; mark what harness-claude-code already delivered; flag gaps.
- Done: rewrote `docs/requirements.md` § "Item: platform-skeleton" (criteria now `PS-<sub>.<n>`, each with a named test/gate and a fast/full tag); §R-DR rows 30, 39, 41 updated.
- Already delivered (not to rebuild): gates service with `network_mode: none`, `verify.sh` single entry, CI = `verify.sh full` only, uv `--locked` + `UV_OFFLINE=1`, LF `*.sh`, phoenix service.
- Proposed split (orchestrator decides; no branches created):
  0. `harness-followups` — CI runner pin, checkout v5 SHA, N3 (integration runs once), M4 (CR fails safe), N16/N17.
  1. `platform-config` — typed config, no hardcoded hosts/ports/models, egress guard startup+runtime (DR30), startup refusals (DR39 part), coverage/mypy gate.
  2. `platform-stack` — compose services pinned by digest, ports from `.env` incl. phoenix, restart policies (DR41), `/healthz`, `/readyz`, worker no-op job, real-store integration gate with socket guard, live-stack smoke, tri-OS scripts + lints + quickstart.
  3. `platform-offline` — bundle with checksum manifest, `ci/deployable-offline`, `ci/offline`.
- Carry-in decisions: CI pin, checkout v5, N3, M4, N16, N17 → PS-0. N5, N6, N18, N19, L2, L5, L7, L16-L18 stay deferred.
- Changes to the draft: DR13 embedding-dim check moved out of `/readyz` to knowledge-plane; DR16 register entry deferred to policy-book (PS-Q8); added restart policies, socket guard, live-stack smoke, worker job, image digests, tracing of startup.
- Open questions (full text in requirements § platform-skeleton): PS-Q1 runner image; PS-Q2 does A6 move the harness Phoenix port; PS-Q3 what counts as a local collector; PS-Q4 hide flags in dev; PS-Q5 coverage/mypy scope; PS-Q6 is model host required for readiness; PS-Q7 (architect, blocking) how network-less `gates` reaches real stores / clean daemon; PS-Q8 DR16 timing; PS-Q9 shipping rule before bundle; PS-Q10 macOS/Windows proof; PS-Q11 Python 3.12 pin.
- Next: architect designs, starting with PS-Q7 (it may amend the as-built gates in ADR-KE-001); orchestrator answers or escalates PS-Q1..Q11 and may copy them into `docs/open-questions.md`.

## 2026-10-18 — orchestrator: split accepted, rulings
- The split into four plan items, each on its own `agent/<slug>` branch in this order, is accepted: `harness-followups` → `platform-config` → `platform-stack` → `platform-offline`. This doc stays the umbrella plan record, and each sub-item gets its own handoff. The plan docs commit with `harness-followups`, which is the current branch, renamed.
- Rulings on the analyst's open questions (analyst: fold these into `docs/open-questions.md` and the criteria):
  - PS-Q1: pin `ubuntu-24.04`, the image `ubuntu-latest` resolves to before the 2026-10-19 move. Verify it from the CI log of 615adf8 when implementing.
  - PS-Q2: yes. One Phoenix for harness and product, with ports from `.env` in the 47100–47199 range. `log_event` keeps reading `PHOENIX_COLLECTOR_ENDPOINT`; only its default changes, plus docs.
  - PS-Q3: "local" means a loopback address or a compose service name on the internal network. Anything else is refused at startup.
  - PS-Q4: `OPENINFERENCE_HIDE_*` defaults to `true` in every env. Only `ENV=dev` may set false, and then it logs a warning.
  - PS-Q5: line + branch coverage ≥ 80% and `mypy --strict` over every first-party package (`harness_telemetry` and the new engine package), excluding tests.
  - PS-Q6: `/readyz` reports the model host as its own field. Overall readiness excludes it (ingest and review work without a model). Compose-dependent routes check it themselves.
  - PS-Q7: architect, blocking for `platform-stack` only.
  - PS-Q8: confirmed. DR16 register entries arrive with policy-book.
  - PS-Q9: yes, `platform-stack` may merge before `platform-offline`. The "deployable offline" rule is met at the end of `platform-offline`, before any reviewer-facing feature ships.
  - PS-Q10: asked of the human.
  - PS-Q11: pin Python 3.12 (`requires-python = ">=3.12,<3.13"`), in `platform-config`.

## 2026-10-18 — orchestrator: rulings on architect F1–F6
- F1 (ADR-KE-009 replaces testcontainers in DR31 with compose services on an internal network): **the human decides**, because DR31 is a binding rule. Asked; `platform-stack` waits on it. `platform-config` does not.
- F2: the `KE_`-prefixed names are canonical, with no aliases. The analyst renames `ENV`, `EGRESS_ALLOWLIST` and `MODEL_BASE_URL` in the requirements and A7.
- F3: secrets have no default (an accepted exception to PS-1.1). Placeholder secrets are refused outside `dev`.
- F4: `config/verify.env` is an accepted literal exemption under PS-1.2.
- F5: the offline check runs in every local `full`, keeping CI identical to local. Revisit if `full` exceeds about 15 minutes locally.
- F6: CI `timeout-minutes` is set from the measured duration plus 50%.
- Bundle: no wheels (the images carry their dependencies). linux/amd64 only for now; Apple silicon is recorded under Q20.
- The analyst's re-tags and the three new criteria proposed by the architect are accepted. The analyst applies them.

## 2026-10-18 — architect: platform design, Q19 (formerly PS-Q7) answered
- **Asked:**
  - Answer Q19 as an ADR.
  - Design platform-config, platform-stack and platform-offline, and name the first tests.
  - Orchestrator inputs: decide the `DEFAULT_COLLECTOR` scan conflict; `scripts/*.py` is out of coverage and mypy scope.
- **Did:**
  - Rewrote `docs/architecture.md` §2 as subsections 2.1–2.6.
  - Added ADR-KE-009 to ADR-KE-012.
  - Added amendment notes to ADR-KE-001 and ADR-KE-003.
- **Q19 decision (ADR-KE-009):**
  - **Stores and network:** the stores are compose services on `backend` (`internal: true`), and a new one-shot `gates-it` (the same gates image) joins `backend`. There is no socket and no testcontainers.
  - **`gates` and fast:** `gates` stays `network_mode: none`, and `fast` is unchanged.
  - **`verify.sh full`, host half:**
    1. `build.sh`.
    2. `launch.sh`, using an isolated project `ke-verify-<suffix>` with ports reset, so nothing is published.
    3. `compose run gates-it scripts/verify.sh full`, which runs `lint.sh` and `test.sh`.
    4. `smoke.sh` (two-sided).
    5. `offline_check.sh`.
    6. Teardown, run by a trap.
  - **Clean daemon:** the offline check uses privileged DinD on an internal network, in every `verify.sh full`, locally and in CI.
  - **Socket (b) rejected:** the Docker socket is root-equivalent on the host and lets test code escape `network_mode: none`.
  - **Option (c) rejected:** its bridge network gives tests a route to the internet and the model host.
- **Other decisions:**
  - **Package:** `engine/`.
  - **Settings:** pydantic-settings (init → environment → `config/defaults.yaml`). Variables are `KE_`-prefixed with `__` nesting. Secrets come from the environment only.
  - **Egress:** an httpx `GuardedTransport` plus startup checks.
  - **Network:** `gateway` (nginx) is the only service on `edge`. It reverse-proxies api and phoenix and forwards one TCP port to the model upstream.
  - **Queue:** RQ on Valkey.
  - **Ports:** 47100 (api) and 47101 (phoenix, harness included). 4317 is no longer published.
- **`DEFAULT_COLLECTOR`:**
  - It stays a literal and is the scanner's single exemption.
  - `test_harness_default_collector_matches_env_example` pins it to `KE_PHOENIX_PORT`.
- **Needs an orchestrator or human ruling:**
  - F1. ADR-KE-009 changes the *mechanism* named in DR31 and the requirements conventions ("via testcontainers"). DR31 is "binding" in the prompt.
  - F2. The env-var names differ from the spelling in the requirements (`ENV`, `EGRESS_ALLOWLIST`, A7 `MODEL_BASE_URL`), which would become `KE_ENV` and similar.
  - F3. Secrets have no `defaults.yaml` default, an exception to PS-1.1.
  - F4. `config/verify.env` becomes an allowed literal location (PS-1.2).
  - F5. Offline check: it runs in every local `full` (time, disk, privileged). The alternative, CI-only, would need a CLAUDE.md row.
  - F6. The CI `timeout-minutes` must rise.
- **For the analyst:**
  - Re-tag `test_stack_services_healthy` and the real store stop as smoke. Integration makes store-down in process.
  - Proposed new criteria:
    - `test_only_gateway_on_edge_network`
    - `test_no_docker_socket_mounted`
    - `test_stack_services_have_no_bind_mounts`
  - Placeholder secrets refused outside dev?
  - PS-3.1: what are the wheels for? The bundle is linux/amd64 only, so macOS on arm64 is not covered (relates to Q20).
- **Next:**
  - The orchestrator rules on F1–F6.
  - The tester starts platform-config RED with `test_config_defaults_and_env_override` (`docs/architecture.md` §2.6).

## 2026-10-18 — architect: architecture.md aligned with F1–F6 rulings
- **Asked:** fold the orchestrator's F1–F6 and bundle rulings into `docs/architecture.md` only.
- **Did (`docs/architecture.md`):**
  - §2.2 and ADR-KE-009: status "proposed, pending human ruling Q30" (F1); DR31 edit waits on Q30. F5 (offline check in every local `full`, blocker not skip, revisit ~15 min) and F6 (timeout = measured + 50%) recorded.
  - §2.3 and ADR-KE-010: `KE_` names only, no aliases; standard tool names kept (F2). Secrets no default (F3) plus startup refusal 5, placeholder secrets outside `dev` (PS-1.9); app image copies `.env.example` for it. `config/verify.env` as F4 exemption. "Could be added as aliases" removed.
  - §2.5 and ADR-KE-012: `wheels/` removed; linux/amd64 only, Apple silicon under Q20; F5/F6 noted.
  - §2.6: `test_python_pinned_to_312`; added `test_config_ignores_unprefixed_names`, `test_config_missing_secret_names_key`, `test_startup_refuses_placeholder_secrets`, `test_ci_job_has_timeout`; PS-2.10–2.12 no longer "proposed"; `gates-it` integration marked blocked on Q30.
- **Design choice for the tester/developer:** the placeholder-secret check reads `.env.example` (copied into the app image) and names the key, never the value.
- **Next:** tester starts platform-config RED with `test_config_defaults_and_env_override`.

## 2026-10-18 — orchestrator: placeholder-secret ruling
- This overrides the architect's §2.4 choice to copy `.env.example` into the app image. Instead, every secret placeholder in `.env.example` is `changeme-<key>`, and startup refuses any secret whose value starts with `changeme` outside `dev`. `.env.example` is not shipped in the image.
- The analyst updates the PS-1.9 definition, and the architect updates §2.3/§2.4. Both are done at the start of `platform-config`, as its first plan step.

## 2026-10-18 — orchestrator: human rulings Q30, Q20, Q7
- Q30 (human): automated integration tests get external network access. The mechanism is ADR-KE-009 minus the isolation: compose services, no Docker socket, but the `gates-it` network is NOT `internal`. This amends DR31 ("CI never calls a model") and the offline-gates constraint, for integration tests only. Consequences:
  - model-calling integration tests run when aria-gb10-2 is reachable, and skip with a visible reason when it isn't, as on GitHub runners;
  - CLAUDE.md gains a "What verify.sh runs that CI cannot" row;
  - the app's egress allowlist (DR30) still limits model calls to the configured host;
  - unit tests (`gates`, `verify fast`) keep `network_mode: none`;
  - the offline-bundle check (`ci/offline`, `ci/deployable-offline`) still proves the *deployed* product runs offline.
  The architect amends ADR-KE-009, and the analyst amends DR31, the Q30 entry and PS-2.4–2.7.
- Q20 (human): no macOS for now; Windows (PowerShell) and Linux only. Apple silicon is out of scope.
- Q7 (human): the model host is `aria-gb10-2` (OpenAI-compatible). It is configured via `KE_MODEL_UPSTREAM` and the per-pass base URLs, never hardcoded.
