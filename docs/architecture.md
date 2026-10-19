# Architecture

Maintained by the `architect` agent. This page describes the **current state**
and is rewritten whole whenever the design changes. ADRs follow the overview.

**Current state (2026-10-18):** the repository holds the `monitored-harness`
template (tracing helpers, the Copilot role agents, and test and smoke scripts).
The branch `agent/harness-claude-code` adds the Claude Code port (ADR-KE-001):
`CLAUDE.md`, eight `.claude/agents/`, the commit hook in
`.claude/settings.json`, and `scripts/verify.sh`, which runs every gate in the
one-shot `gates` compose service with no network. The engine itself still does
not exist: none of the engine described below has been built. This document is the **proposed
design** for plan approval. Each section is marked *proposed* until the plan
item that builds it is committed. Assumptions `(A<n>)` refer to
[open-questions.md](open-questions.md).

**Next to build (2026-10-18):** `platform-skeleton`, split into
`platform-config` → `platform-stack` → `platform-offline` (§2, ADR-KE-009 to
ADR-KE-012). ADR-KE-009 answers Q19 (formerly PS-Q7): how the gates reach real
stores and a clean Docker daemon. It amends the as-built gates of ADR-KE-001,
and is accepted with the human's Q30 amendment, narrowed by ruling F-A
(model-calling integration tests reach the model host through the gateway
only; no route to the internet). Human rulings folded in: Q30 (as narrowed by
F-A), Q20 (Windows and Linux only),
Q7 (model host `aria-gb10-2`), and the `changeme-` placeholder-secret ruling.

## 1. What the system is

The system is a knowledge engine in a box: an on-premises, offline stack. It
turns an institution's documents into three queryable planes, plus a versioned
**policy book**. It answers through a fixed agentic workflow in which a local LLM
only composes wording. **AI is the interface, not the source of truth.** Every
answer traces to ratified rule revisions and to source record revisions. A
deterministic validator re-judges every AI output, and nothing publishes
without a human.

```mermaid
flowchart LR
  subgraph Inputs
    F[Files: PDF/DOCX/DOC/RTF/XLSX/CSV/HTML/MD/images]
    P[Policy documents]
  end
  subgraph Engine
    I[Ingest ledger<br/>+ source revisions]
    DP[(Data plane<br/>PostgreSQL + blob store)]
    KP[(Knowledge plane<br/>Neo4j graph + vector indexes)]
    PB[(Policy book<br/>PostgreSQL, versioned)]
    WF[Agent workflow]
    V[Verifier + validator]
    RQ[Review queue]
    AU[(Audit chain)]
  end
  subgraph Humans
    UI[Frontend]
  end
  F --> I --> DP --> KP
  P --> I
  DP -->|clause extraction, LLM proposes| PB
  UI -->|ratify| PB
  UI -->|ask| WF
  WF -->|authz-filtered queries| DP & KP
  WF -->|deterministic evaluation| PB
  WF --> V --> RQ --> UI
  RQ -->|human approve| PUB[Published artifact]
  I & PB & RQ & PUB -.-> AU
```

## 2. Platform (proposed, `platform-skeleton`)

Criteria: `docs/requirements.md` § platform-skeleton (PS-1.x, PS-2.x, PS-3.x).
Decisions: ADR-KE-009 (gates topology), ADR-KE-010 (configuration and egress),
ADR-KE-011 (stack topology and job queue), ADR-KE-012 (offline bundle).
Every image is pinned by digest. **No tag or digest is chosen in this
document.** The developer resolves and records each one at implementation
time, in the sub-item's handoff.

### 2.1 Containers and networks

Everything runs under docker compose. The compose file sets the top-level
`name: knowledge-engine`, so volumes keep their names whatever the checkout
directory is called. **Of the stack services, only `gateway` touches a network
with a route out.** The one-shot `gates-it` verify service sits on `backend`
only, like the app containers (Q30 as narrowed by F-A, ADR-KE-009). There is no
`gates-it` network. Its only way off the machine is the gateway's single
upstream forward to the configured model host.

| Network | `internal` | Members |
|---|---|---|
| `edge` | no | `gateway` |
| `backend` | yes (no route out), and `gateway_mode_ipv4: isolated` (no route to the Docker host; rework 1, M-2) | every stack service, `gates-it`, `probe` |
| `offline` | yes | `dind`, `offline-client` |

**`backend` is isolated from the Docker host too (amended, platform-stack
rework 1, security M-2).** `internal: true` removes the route out, but the
bridge still gives the host an address on `backend` (the bridge gateway), so
any backend container could reach a host service bound to `0.0.0.0`, such as
a local model server, a proxy or sshd, and bypass the gateway and the
allowlist. `backend` therefore also sets
```yaml
driver_opts:
  com.docker.network.bridge.gateway_mode_ipv4: isolated
```
and Docker then gives the bridge no host address. This needs **Docker Engine
28 or later**. Older engines ignore the option without an error, so
`launch.sh`/`.ps1` refuse anything but a numeric Engine version ≥ 28 (§2.4
Scripts; rework 2) and `docs/quickstart.md` lists Engine ≥ 28 as a
prerequisite.

**No fixed address on `backend` (rework 2, review R1-B1 option (ii),
security M-4).** `backend` has **no `ipam` block**: no subnet, no
`ip_range`, and no address literal anywhere in compose, config or tests.
Docker picks the subnet from its default pools per project. So parallel
stacks from this compose file are supported again: the live stack, any
number of `ke-verify-*` runs, and stacks in other worktrees each get their
own `<project>_backend` and never hit "Pool overlaps". (Two *live* stacks
still need different published ports; verify publishes none.) The runtime
proof of isolation is the network's own configuration, checked from the
host (§2.2 No route out). `edge` is unchanged:
the gateway needs its route out. `offline` (platform-offline) should take the
same option when it is created; that is recorded here for that item, not done
in this one.

| Service | Image (digest pinned at implementation) | Networks | Restart | Role |
|---|---|---|---|---|
| `gateway` | `ke-gateway`, built `FROM` the official nginx image (unprivileged variant) with the config baked in | `edge`, `backend` | `unless-stopped` | Publishes the only host ports, on `KE_BIND_ADDRESS` (loopback by default; §2.4). Reverse-proxies `api` and `phoenix`, and forwards one TCP port to the model host. Its entrypoint refuses an upstream that is not on the allowlist (§2.4) |
| `api` | `ke-app` (`docker/app.Dockerfile`): Python 3.12, FastAPI, uvicorn | `backend` | `unless-stopped` | HTTP API, server-rendered UI, `/healthz`, `/readyz` |
| `worker` | `ke-app` | `backend` | `unless-stopped` | RQ worker (ADR-KE-011). Only the no-op job for now. In 2a it is a placeholder, `python -m engine.worker`, that runs `startup()` and then idles (§2.4 Worker) |
| `postgres` | official `postgres`, major 16 | `backend` | `unless-stopped` | records, revisions, ledger, policy book, review queue, audit chain |
| `neo4j` | official `neo4j`, 5.x community | `backend` | `unless-stopped` | graph and vector indexes (ADR-KE-002) |
| `valkey` | `valkey/valkey`, major 8, AOF on | `backend` | `unless-stopped` | job queue only |
| `phoenix` | `arizephoenix/phoenix` (today `version-20.22.0`; digest added) | `backend` | `unless-stopped` | traces for the product and the harness (Q2 ruling) |
| `gates` | `ke-gates` (`docker/gates.Dockerfile`) | `network_mode: none` | none | one-shot: lint and unit gates (unchanged from ADR-KE-001) |
| `gates-it` | `ke-gates` (same YAML anchor) | `backend` only; no Docker socket | none | one-shot: unit, integration, coverage and mypy against the real stores; model-calling tests reach the model host only through `gateway`, and run only when it is reachable (ADR-KE-009, Q30/F-A) |
| `probe` | `ke-app` | `backend` only | none | one-shot: the live-smoke checks (`python -m engine.ops.smoke`) |
| `dind` | official `docker` image, `dind` variant, privileged | `offline` (internal) | none | clean daemon for the offline check (ADR-KE-009, ADR-KE-012) |
| `offline-client` | `ke-gates` | `offline` (internal) | none | runs install, launch and smoke against `dind` |
| model host | external, OpenAI-compatible | — | — | The deployment's model host is `aria-gb10-2` (Q7 ruling). Ollama now, vLLM later. The app reaches it only through `gateway`. Config carries it in `KE_MODEL_UPSTREAM`; no code names it |

`gates`, `gates-it`, `probe`, `dind` and `offline-client` are behind compose
profiles (`gates`, `probe`, `offline`), so `up` never starts them.

```mermaid
flowchart LR
  subgraph host["Host (Git + Docker only)"]
    user[Browser / log_event]
  end
  subgraph edge["edge network (bridge)"]
    gw[gateway]
  end
  subgraph backend["backend network (internal: true, no route out)"]
    api[api]
    wk[worker]
    pg[(postgres)]
    n4[(neo4j)]
    vk[(valkey)]
    ph[phoenix]
    pr[probe<br/>one-shot]
    git[gates-it<br/>one-shot, verify only]
  end
  mh[(model host aria-gb10-2<br/>via KE_MODEL_UPSTREAM)]
  user -- "KE_API_PORT 47100" --> gw
  user -- "KE_PHOENIX_PORT 47101" --> gw
  gw --> api & ph
  api & wk -- "model port on gateway" --> gw -- "TCP, one upstream (edge)" --> mh
  api & wk --> pg & n4 & vk
  api & wk -- OTLP --> ph
  pr --> api & gw
  git --> pg & n4 & vk & api
  git -- "model port on gateway" --> gw
```

`gates-it` is on `backend` only. Its model-calling tests go through
`ModelClient` → `gateway` → `KE_MODEL_UPSTREAM`, the same path as the app, so
the DR30 allowlist and the gateway forward are what the tests exercise. No
other path leaves `backend`.

Stack services (everything without a profile) use **named volumes only, with
no bind mounts**, so the same compose file runs unchanged inside `dind`. Only
the one-shot gate services bind-mount the checkout.

Blob storage holds original files and revision content. It is a volume mounted
into `api` and `worker`, content-addressed by SHA-256 and encrypted per source
(A11). It arrives with `ingest-ledger`.

### 2.2 How `verify.sh` runs the gates (ADR-KE-009, answers Q19)

**Status: accepted with a human amendment (Q30, 2026-10-18), narrowed by
ruling F-A (2026-10-18).** The mechanism is compose services with no Docker
socket, as proposed. `gates-it` sits on the `internal: true` `backend` network
only; there is no separate external network for it. Tests need to reach only
the LLM on `aria-gb10-2`, not the internet, so model-calling integration tests
reach it through the gateway's upstream forward (edge network) and nothing
else. Unit `gates` keeps `network_mode: none`. `platform-stack` is not blocked.

`scripts/verify.sh` keeps its two halves.
- **Host half:** only Docker orchestration, which calls other scripts.
- **Container half:** only calls `scripts/lint.sh` and `scripts/test.sh`.

No gate command is ever written in `verify.sh`
(`test_verify_sh_has_no_inlined_commands` stays as it is).

- **Isolation.** Each run uses its own compose project,
  `ke-verify-<random suffix>`. It reads `--env-file .env.example`, then
  `--env-file config/verify.env`, which holds only the verify overrides.
  `docker-compose.verify.yml` resets every `ports:` to an empty list (`!reset`,
  Compose ≥ 2.24), so a verify run publishes nothing. `backend` has no fixed
  subnet (§2.1, rework 2), so each project's networks come from Docker's
  default pools. A verify run therefore never collides with the live stack
  or with a parallel verify run.
- **The real model host, through the gateway, skipped when unreachable (Q30,
  F-A, Q7).** `config/verify.env` does **not** override `KE_MODEL_UPSTREAM`,
  so the verify stack's gateway (on `edge`) forwards to the configured host
  from `.env.example`. (Rework 2, R2: `.env.example` now leaves
  `KE_MODEL_UPSTREAM` empty, so as written a verify run has no upstream and
  the model-calling tests skip with a named reason. How an operator points a
  local verify run at `aria-gb10-2` is open, flagged to the orchestrator.)
  `gates-it` itself
  has no route out; the gateway forward is its only path to the model host.
  Model-calling integration tests:
  - first run one reachability probe per test run: `GET {compose.base_url}/models`
    through `ModelClient`, so it passes the egress guard, with
    `readiness.timeout_s`;
  - run when the probe succeeds;
  - otherwise raise `unittest.SkipTest` with a named reason built from the
    configured value and the fixed reason vocabulary of `/readyz`, e.g.
    `model host unreachable: <KE_MODEL_UPSTREAM> (timeout)`. unittest prints
    it in the verbose output, so the skip is visible in the evidence file.
  On GitHub runners the host is never reachable, so those tests always skip
  in CI. The probe outcome is never a failure, and no other test may skip on
  network grounds.
- **`fast`:** unchanged. `docker compose … --profile gates run --rm --build
  gates scripts/verify.sh fast` → `lint.sh`, `test.sh fast`, with
  `network_mode: none`.
- **`full`:**

```mermaid
sequenceDiagram
  participant H as verify.sh (host)
  participant D as host Docker daemon
  participant G as gates-it (backend only)
  participant W as gateway (backend + edge)
  participant M as model host (KE_MODEL_UPSTREAM)
  participant S as smoke.sh (host)
  participant O as offline_check.sh (host)
  H->>H: trap → teardown.sh --volumes (this project)
  H->>D: build.sh (ke-app, ke-gateway, ke-gates; store images by digest)
  H->>D: launch.sh (up -d --no-build --wait)
  H->>G: compose run gates-it scripts/verify.sh full
  G->>G: lint.sh; test.sh full (unit + store integration, coverage, mypy)
  G->>W: probe GET /models via ModelClient (DR30 allowlist)
  W->>M: TCP forward, one upstream
  alt reachable
    G->>W: model-calling integration tests
    W->>M: TCP forward
  else unreachable (always on GitHub runners)
    G->>G: skip them: "model host unreachable: <upstream> (<reason>)"
  end
  H->>S: smoke.sh
  S->>D: launch.sh (idempotent), run probe, stop/start valkey, run probe
  S->>D: run gates scripts/smoke.sh (inner half: OTLP export check, no network)
  S->>D: teardown.sh --volumes
  H->>O: offline_check.sh (platform-offline; §2.5)
```

- **Two-sided scripts.** `smoke.sh` has the same two-sided shape as
  `verify.sh`, keyed on `KE_IN_GATES`.
  - On the host it runs the live-stack smoke (PS-2.8).
  - In `gates` it runs today's OTLP check (`smoke_otlp.py`).
  - `smoke.sh --live` runs the host half only. The offline check uses it,
    because the bundle carries no gates image.
- **Store-down cases.** Because `gates-it` has no Docker socket, it cannot stop
  a container. Integration tests make a store "down" in process, by pointing
  one store's settings at a closed port on a stack host. The real stop and
  start of a container happens in `smoke.sh` on the host.
- **No route out, proven at runtime (amended 2026-10-19, F-A drift fix).**
  `backend` being `internal: true` is the boundary for `gates-it`. The earlier
  `tests/integration` socket-guard fixture is dropped: it could not see libpq
  (psycopg connects in C), and since F-A the network layer already refuses
  every raw connection out. The in-process socket-guard test that went with
  it was superseded in the requirements (PS-2.7). Two tests prove the boundary:
  - **Statically:** `test_gates_it_internal_only_and_no_socket` (fast), and
    `test_backend_network_isolated_from_host` (fast, rework 1): `backend` has
    `internal: true` and the driver option
    `com.docker.network.bridge.gateway_mode_ipv4: isolated`.
  - **At runtime:** `test_gates_it_has_no_route_out` (PS-2.7). Amended in
    rework 1 (review B1, security M-2), because "the connect failed" alone
    also passes when a route exists and nothing answers:
    1. A raw TCP connect from `gates-it` to a TEST-NET-1 address must fail
       **fast and with a no-route errno**: `errno in {ENETUNREACH,
       EHOSTUNREACH}`, not `TimeoutError`, within a tight bound (about 2 s,
       well under the socket timeout). A timeout means packets left, so it
       fails the test.
    2. *(Removed in rework 2, R1-B1 option (ii).)* The in-container probe of
       the `backend` bridge-gateway address is gone, with its derived `.1`
       address. Host isolation is proven by the host-side check below.
    3. The control: `gateway`'s model listen port accepts.
  - **Host isolation, at runtime (rework 2, R1-B1 option (ii); closes
    security M-4).** The host half of `smoke.sh` (so every `verify.sh full`,
    for its own `ke-verify-*` project, and every live smoke) asserts that the
    project's `backend` network carries the option:
    - The project name is the `name:` line of `docker compose <args> config`
      (the same argument list launch uses), so `COMPOSE_PROJECT_NAME` and
      the compose file's top-level `name` both resolve as compose resolves
      them, and the script names no project literal.
    - `docker network inspect <project>_backend --format '{{index .Options
      "com.docker.network.bridge.gateway_mode_ipv4"}}'` must print exactly
      `isolated`. A missing network, an inspect error, an empty value or any
      other value fails the smoke, naming the network and the option.
    - It also checks `.Internal` is `true` on the same inspect.
    - **Why not probe an address from inside:** a connect from a container
      can only show that one address did not answer, never that the host
      has no address on the bridge. Measured in this item:
      - With `isolated`, Docker hands the subnet's `.1` to a container, so a
        `.1` probe can hit a stack service (rework 1 saw an RST from one).
      - Without `isolated` and with an `ip_range`, the host's bridge address
        is the first `ip_range` address, not `.1`, so the probe missed it
        and passed with isolation lost (security M-4, control 3).
      - On Docker Desktop the host side is a VM, and probes of `.1` give the
        same timeouts and errnos with and without `isolated` (review
        rework 1, server 29.5.2), so no errno discriminates.
      The daemon's network configuration is the authoritative source, and
      the host half can read it without a Docker socket in any container.
    - The static `test_backend_network_isolated_from_host` stays. Together
      they cover both "the compose file lost the option" and "the engine
      ignored it".
    - First tests (fast, fake docker): the smoke host half fails when
      inspect prints an empty value, `nat`, or exits non-zero, and passes on
      `isolated`; it inspects `<project>_backend` for the project that
      `config` names (`ke-verify-123` in the fixture). The real run in
      `verify.sh full` is the integration proof; a mutant compose file
      without the option must make it fail (reviewer measures).

  The allowlist layer is proven separately, by
  `test_egress_allowlist_holds_with_network_access`.
- **No runtime installs.** The gates anchor sets `UV_OFFLINE=1` alongside
  `--locked`, so a verify run can never pass locally only because it fetched
  a dependency that CI could not.
- **Container health.** Health of the running containers is proven by
  `launch.sh --wait`, which fails unless every healthcheck passes, and by the
  probe.
- **Lint (made concrete in rework 1, review B5).** `scripts/lint.sh` runs
  shellcheck over `scripts/**/*.sh` and `docker/**/*.sh`, and PSScriptAnalyzer
  (`Invoke-ScriptAnalyzer`, severity Warning and Error, any finding is
  non-zero) over `scripts/*.ps1`. It runs **inside the gates image only**,
  never on the host. The container half of `verify.sh` calls `scripts/lint.sh`
  and then `scripts/test.sh`, in both modes, so `gates` (fast) and `gates-it`
  (full) both lint. The command lines stay in `lint.sh`
  (`test_verify_sh_has_no_inlined_commands`).
  - Gates image: `shellcheck` from the pinned Debian base's apt; `pwsh` from a
    version-pinned release archive checked by SHA-256; PSScriptAnalyzer saved
    at a pinned `-RequiredVersion` at **build** time. With `UV_OFFLINE=1` and
    `network_mode: none`, nothing is fetched at gate time.
  - **Paths never become code (rework 2, security L-7).** `lint.sh` never
    builds PowerShell source from file names. The `-Command` text is one
    fixed single-quoted shell constant with no expansion in it. The `.ps1`
    paths reach it only through the environment: `lint.sh` exports
    `KE_LINT_PS1_FILES`, the paths joined by newlines, and the fixed command
    splits `$env:KE_LINT_PS1_FILES` and calls `Invoke-ScriptAnalyzer -Path`
    on each as a value. A path containing a newline is refused (exit
    non-zero) before pwsh runs. (`pwsh -Command` joins trailing arguments
    into the command text, so arguments are not used; a separate `-File`
    analyzer script was not chosen, because it would be one more `.ps1` to
    keep lint-covered.) First tests (fast): a static test that the
    `-Command` argument in `lint.sh` is a literal with no `$`-expansion by
    the shell; a behavioural test that a `.ps1` named with the U+2019 payload
    from L-7 (and the U+0027 form) is linted and leaves no marker file.
  - Inline `# shellcheck disable=` comments name the rule and give a reason;
    a blanket disable is a review finding.
  - The Docker CLI and compose plugin, which `offline-client` needs, arrive
    with platform-offline, not here.
  - First test: `test_lint_sh_runs_shellcheck_and_psscriptanalyzer` (fast,
    static: `lint.sh` names both tools over those globs, and `verify.sh`'s
    container half calls `lint.sh` before `test.sh`). The proof that lint can
    go red is a recorded run with a planted shellcheck finding and a planted
    PSScriptAnalyzer finding (DR38), saved under `docs/evidence/`.
- **The host half is tested with a fake docker (rework 1, review B6).** A
  fast test copies `scripts/verify.sh` into a temp tree whose
  `scripts/{build,launch,teardown,smoke}.sh` are stubs that log their name
  and arguments and exit with a code the test sets, and puts a fake `docker`
  first on `PATH` that logs its arguments and `COMPOSE_FILE` and
  `COMPOSE_PROJECT_NAME`. `verify.sh` needs no new seam, because it already
  `cd`s to its own parent. The test asserts:
  - the order build, launch, `docker compose … run … gates-it scripts/verify.sh full`,
    smoke;
  - a non-zero exit when each stage fails, and no later stage runs;
  - `teardown.sh --volumes` runs on success, on each failure, and on SIGINT
    and SIGTERM;
  - `COMPOSE_FILE` includes `docker-compose.verify.yml`;
  - the project name matches `ke-verify-<digits>` and differs between two
    runs;
  - no `ports`/`-p`/`--publish` argument reaches docker.
- **A failed teardown is reported (rework 1, review N7).** The `EXIT` trap
  prints a warning naming the project when `teardown.sh` fails, instead of
  hiding it behind `|| true`. The exit code of the run is unchanged, because
  the gates have already passed or failed. The B6 test covers the warning.

### 2.3 platform-config (ADR-KE-010)

**Package.** First-party code lives in one new package, `engine/`, next to
`harness_telemetry/`. `pyproject.toml` is changed as follows:
- project `knowledge-engine`
- `requires-python = ">=3.12,<3.13"` (Q11 ruling)
- wheel packages `engine` and `harness_telemetry`
- a `dev` dependency group with coverage, mypy and type stubs

```
engine/
  __init__.py
  config/      settings.py (Settings + sub-models), loader.py (sources, ConfigError)
  egress.py    EgressPolicy, EgressDenied, GuardedTransport (httpx), is_local_endpoint()
  startup.py   startup() → Settings; StartupRefused(setting, reason); warnings
  telemetry.py configure_tracing(settings) – export only to a local collector
  llm/client.py ModelClient: per-pass, guarded httpx client (OpenAI-compatible)
config/defaults.yaml   every non-secret key's default (repo root, copied into images)
```

**Settings.** One `pydantic-settings` `Settings` object. The sources are, in
order of precedence:
1. init arguments (tests);
2. environment variables;
3. `config/defaults.yaml`, located through `KE_CONFIG_FILE`, defaulting to
   `config/defaults.yaml` relative to the working directory. A missing file is
   a `ConfigError` that names the path.

Environment variables:
- **Naming:** `KE_` prefix, with `__` for nesting, e.g.
  `KE_STORES__POSTGRES__PORT`.
- **`KE_` names only (F2 ruling):** the requirement names map to `KE_ENV`,
  `KE_EGRESS_ALLOWLIST`, `KE_MODEL_UPSTREAM` and `KE_MODELS__<PASS>__BASE_URL`.
  Unprefixed names (`ENV`, `EGRESS_ALLOWLIST`, `MODEL_BASE_URL`) are ignored,
  with no aliases (`test_config_ignores_unprefixed_names`).
- **Standard tool names stay:** variables other tools already read keep their
  own names: `PHOENIX_COLLECTOR_ENDPOINT`, `HARNESS_TRACING`,
  `OPENINFERENCE_HIDE_INPUTS`, `OPENINFERENCE_HIDE_OUTPUTS`. For the engine,
  `Settings` is their **only** reader (they fill `telemetry.*`); no engine
  code path lets `harness_telemetry` read them again (B1, rework 1).
- **Lists:** comma-separated in the environment.

`defaults.yaml` layout. The values shown are the A7 defaults:

```yaml
env: prod                    # dev | ci | prod; fail-closed default
auth: {enabled: true}
egress_allowlist: []         # hosts; exact, case-folded, no wildcards
stack:
  service_names: [gateway, api, worker, postgres, neo4j, valkey, phoenix]  # drift-tested against compose
api: {listen_port: 8080}
stores:
  postgres: {host: postgres, port: 5432, database: engine, user: engine}
  neo4j:    {host: neo4j, port: 7687, user: neo4j}
  valkey:   {host: valkey, port: 6379}
models:                      # one block per pass (DR29); no inheritance between passes
  model_upstream: null       # gateway's upstream host:port, checked against the allowlist
  compose: {base_url: null, model: qwen2.5:14b-instruct, fallback_model: llama3.1:8b, timeout_s: 120}
  rewrite: {base_url: null, model: qwen2.5:14b-instruct, fallback_model: llama3.1:8b, timeout_s: 120}
  audit:   {base_url: null, model: qwen2.5:14b-instruct, fallback_model: llama3.1:8b, timeout_s: 120}
  embed:   {base_url: null, model: nomic-embed-text, dim: 768, timeout_s: 60}
telemetry: {tracing: "off", collector_endpoint: "http://phoenix:6006", hide_inputs: true, hide_outputs: true}  # B7b: off by default; .env.example sets HARNESS_TRACING=otlp
readiness: {timeout_s: 2}
```

The numbers above are the images' own defaults and A7's values, and are listed
here for the layout only. They live **only** in this file.

**Secrets (F3 ruling).** Passwords are `SecretStr` with **no** YAML default, an
accepted exception to PS-1.1. They come from the environment only. A missing
secret is a `ConfigError` that names the key
(`test_config_missing_secret_names_key`). Every secret placeholder in
`.env.example` is `changeme-<key>` (for example
`KE_STORES__POSTGRES__PASSWORD=changeme-postgres-password`), and any secret
whose value starts with `changeme` is refused outside `dev` (placeholder-secret
ruling, PS-1.9, startup refusal 5 below). `.env.example` is **not** copied into
any image; the check needs only the prefix.

**Errors.** A bad type (PS-1.1) raises `ConfigError`. Its message names the
environment variable or YAML key, never the value.

**Egress guard (DR30, PS-1.3/1.4).**
- **Startup.** For every pass whose `base_url` is set, the host must be in
  `egress_allowlist`; the same applies to the host of `models.model_upstream`.
  Any configured host with an empty allowlist also fails. The error names the
  host.
- **Runtime.** `ModelClient` builds its `httpx.Client` with
  `transport=GuardedTransport(policy, httpx.HTTPTransport())` and
  `trust_env=False`, so proxy environment variables cannot reroute it.
  - `GuardedTransport.handle_request` checks `request.url.host` **before**
    calling the inner transport. A denied host therefore opens no socket.
  - Every redirect hop also passes through the transport.
  - If a later item adopts the `openai` SDK, it is given the same client
    (`http_client=`).
- **Network layer.** The network topology in §2.1 is the second layer. A
  Python audit hook is not used, because libpq does not go through Python
  sockets.

**No-hardcoded scan (PS-1.2, PS-2.2).** `engine/…` holds no scanner. The scan
is a pure function, `find_hardcoded(files, declared_values, exemptions)`, in
`tests/hardcoded_scan.py`.
- **Two rules:**
  1. Every host, port and model value declared in `config/defaults.yaml` and
     `.env.example` must not appear as a literal in the scanned files.
  2. Any `scheme://host[:port]` string literal, or any integer port assigned to
     a `*port*` name, in Python source is flagged.
- **Scanned:** `engine/`, `harness_telemetry/`, `scripts/`, `docker/`,
  `docker-compose*.yml`, `.github/`.
- **Allowed locations:** `config/defaults.yaml`, `.env.example`,
  `config/verify.env` (F4 ruling: an accepted literal exemption under PS-1.2),
  `tests/`, `docs/`, and compose `${VAR:-default}` defaults. **In compose
  files only** (`docker-compose*.yml`), the scanner treats the `default` of a
  `${VAR:-default}` as a declared value, not a literal (B4, B7a ruling). The
  same text in any other file is scanned as usual. Drift tests tie every such
  compose default to its source: host ports to `.env.example`,
  container-internal listen ports to `defaults.yaml`.
- **Mutation test:** a planted literal must be flagged (DR38).

**`harness_telemetry` default collector (orchestrator input, 2026-10-18).**
`DEFAULT_COLLECTOR` stays a literal (`http://localhost:47101`), because the
harness is a standalone template package with no config system, and
`log_event` runs on the host. It is the scanner's **single** exemption: path,
symbol and reason are recorded in the exemption list in the test file. A drift
test, `test_harness_default_collector_matches_env_example`, asserts that its
port equals `KE_PHOENIX_PORT` in `.env.example`, so PS-2.2 holds.
- **Rejected alternative:** reading `.env.example` at import time depends on
  the working directory and ties a template package to this repo's layout.

**Orchestrator rulings for the scan (2026-10-18, answering tester risks (a)
and (c)).**
1. **Phoenix's literal ports move to `.env` in platform-config**, not
   platform-stack. `.env.example` gains `KE_PHOENIX_PORT=47101` (the A6
   value). Until `gateway` exists (platform-stack), the harness `phoenix`
   service publishes it directly. **Amended by ruling B7a (rework 1,
   2026-10-19):** the publish is
   `"127.0.0.1:${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}"`.
   - Bound to loopback, because Phoenix has no auth and must not be reachable
     from the LAN (security M2).
   - `:-`, not `:?`: `verify.sh` and CI run compose with no `.env`, and `:?`
     fails there.
   - The defaults cannot drift: one drift test,
     `test_compose_phoenix_defaults_match_config`, asserts that the host
     default (47101) equals `KE_PHOENIX_PORT` in `.env.example`, and that the
     container default (6006, in both `ports` and the `PHOENIX_PORT`
     environment entry) equals the port of `telemetry.collector_endpoint` in
     `defaults.yaml`.

   Phoenix's gRPC port 4317
   is **not published**. Consequences in this item: `DEFAULT_COLLECTOR` and the
   `harness_telemetry/tracing.py` docstring move to `http://localhost:47101`;
   the compose header comment stops naming 6006/4317; README's Phoenix URL
   changes (documenter). platform-stack later moves the publish onto `gateway`
   with the same variable.
2. **Loopback addresses and compose service names are not hardcoded hosts.**
   `localhost`, 127.0.0.0/8 and `::1`, and any name in `stack.service_names`
   (the compose services; drift-tested), are never flagged as hosts by either
   rule. This matches the Q3 meaning of "local". Ports are still checked on
   their own: `f"http://127.0.0.1:{port}"` is clean (loopback host, port from a
   variable), while `http://127.0.0.1:6006` is flagged for the port.

**Startup refusals (PS-1.5).** `startup.check(settings)` raises
`StartupRefused(setting, reason)` on the first of the following:
1. `auth.enabled=false` while `env≠dev`;
2. tracing `otlp` to a non-local collector. "Local" (Q3 ruling) means
   `localhost`, 127.0.0.0/8, `::1`, or a name in `stack.service_names`;
3. `hide_inputs` or `hide_outputs` not true while `env≠dev`;
4. the egress startup check;
5. a secret whose value starts with `changeme` while `env≠dev`
   (placeholder-secret ruling, PS-1.9). The check iterates over every
   `SecretStr` field of `Settings`, so a new secret is covered without a list
   to maintain. It reads no file. The refusal names the key, never the value.

6. (platform-stack, §2.4, port ruling 2026-10-19) `bind_address`
   (`KE_BIND_ADDRESS`) not loopback while `env≠dev`, until auth-audit.

In `dev`, cases 1, 3 and 6 log a warning instead (Q4 ruling); case 5 is allowed.

**Tracing does not leak before the checks pass (amended, rework 1: B1, B7b,
L6).**
- **Defaults.** `telemetry.tracing` is `off` in `defaults.yaml` (B7b).
  `.env.example` sets `HARNESS_TRACING=otlp`, so a stack started from the
  template traces to its local Phoenix; the collector endpoint stays the
  `defaults.yaml` value.
- **The exporter comes from `Settings` alone (B1).** One pure function,
  `telemetry.choose_exporter(settings) -> SpanExporter | None`, decides:

  | `telemetry.tracing` | Exporter |
  |---|---|
  | `otlp` | `OTLPSpanExporter(<collector_endpoint>/v1/traces, timeout=5)`, only if `is_local_endpoint(collector_endpoint, stack.service_names)`; otherwise none |
  | `console` | `ConsoleSpanExporter()` |
  | `off` | none |

  `configure_tracing(settings)` builds the engine's own `TracerProvider`
  (resource: OpenInference project name `knowledge-engine`, which also fixes
  N8), adds the exporter (batched for OTLP, simple for console) and installs
  it. It never calls `harness_telemetry.setup_tracing`, whose env reading
  (`HARNESS_TRACING`, `PHOENIX_COLLECTOR_ENDPOINT`) is how B1 leaked.
  `configure_tracing` takes `settings` as a required argument; it no longer
  builds its own (N9).
- **An already-installed provider is verified, not trusted (B1, N10).** The
  OTel global provider can be set only once, so it cannot be replaced; it is
  refused instead. If an SDK `TracerProvider` is already installed in any
  mode, every exporter attached to it must be positively identified as local:
  `ConsoleSpanExporter`, `InMemorySpanExporter`, or `OTLPSpanExporter` whose
  endpoint passes `is_local_endpoint`. Anything else, including an exporter
  that cannot be identified, raises `StartupRefused("telemetry.tracing", …)`.
  The check fails closed. It needs the SDK's private processor attributes,
  so a fast test builds each accepted shape and one unknown shape. An OTel
  upgrade that moves those attributes then fails that test, rather than
  silently accepting.
  **Superseded by the M5 amendment to ADR-KE-010 (2026-10-19) when that
  lands:** only a provider built by `engine.telemetry.build_provider` is
  accepted, and the exporter-shape inspection is deleted.
- **Order in `startup()` (L6).**
  1. `settings = Settings()` (a `ConfigError` propagates).
  2. `check(settings)` runs as a pre-flight with no exporter installed.
  3. Only if it passes: `configure_tracing(settings)`. It first writes the
     resolved hide flags to `OPENINFERENCE_HIDE_INPUTS`/`_OUTPUTS` (the
     values `Settings` read from those same names, so an operator's setting
     is kept, not overridden), then verifies or installs the provider. The
     hide flags are therefore in force before any span can be exported.
  4. The traced block (`engine.startup` → `engine.config.load` →
     `engine.startup.refusals`) runs with the same `settings` object and
     records the spans.

  On a refusal, step 3 is skipped. Step 4 still runs, so the refusal is
  recorded and re-raised, but in production no exporter exists and the spans
  go nowhere. Tests see them through the in-memory provider from
  `tests/support.py`, which passes the installed-provider check.
- **Rejected alternatives:** reusing `setup_tracing(PROJECT_NAME,
  exporter=…)` (it returns any existing provider unchecked and uses a
  synchronous processor for every exporter); a new harness API for the hide
  flags (more surface than the env write, which carries the value `Settings`
  already resolved).

**Spans (PS-1.7).** All are `harness_telemetry` spans:

| Span | Kind | Notes |
|---|---|---|
| `engine.startup` | CHAIN | root; attribute `ke.env`; ERROR on refusal |
| `engine.config.load` | CHAIN | key names overridden from the environment, never values |
| `engine.startup.refusals` | CHAIN | `ke.refused_setting` on refusal |
| `engine.egress.startup_check` | CHAIN | host names checked |
| `model.<pass>` | LLM | wraps every `ModelClient` call; model name; `EgressDenied` marks it ERROR |

N12 (rework 1): every `ModelClient` call method, including any added in
platform-config, opens `llm_span(f"model.{pass}")` around the HTTP request,
and comes with a test that asserts the span (kind LLM, model name, ERROR on
`EgressDenied`) through the in-memory exporter. A call method without its
span is a review finding.

**Quality gates (PS-1.6, Q5 ruling).**
- **Coverage:** `[tool.coverage]` in `pyproject.toml` sets `branch = true`,
  `source = ["engine", "harness_telemetry"]` and `fail_under = 80`.
- **mypy:** `[tool.mypy]` sets `strict = true` with the pydantic plugin, and
  `files = ["engine", "harness_telemetry"]`.
- **Out of scope:** `scripts/*.py` and tests (orchestrator ruling,
  2026-10-18).
- **`test.sh`:**
  - Unit tests run under `coverage run -p`.
  - In `full`, integration tests also run under `coverage run -p` (inside
    `gates-it`).
  - Then `coverage combine`, `coverage report` and `mypy`. Both modes enforce
    the threshold on what that mode ran.
- The tests stay on `unittest`, and every `uv run` keeps `--locked`.

### 2.4 platform-stack (ADR-KE-011)

**Ports (A6, Q2 ruling).**
- **Published:** only `gateway` publishes host ports.
  - `KE_API_PORT=47100`: API and UI.
  - `KE_PHOENIX_PORT=47101`: Phoenix UI and OTLP/HTTP, for both the product and
    the harness's `log_event`.
- **Reserved:** 47102–47199 is reserved, and every new published port takes the
  next free number.
- **Not published:** Phoenix's gRPC port 4317 is dropped, because nothing uses
  it. Stores publish nothing; use `docker compose exec` for psql, cypher-shell
  or valkey-cli.
- **Compose (amended 2026-10-19, port ruling from platform-config B7a;
  amended again in platform-stack rework 1, review N1: long syntax).** Every
  published port uses compose's **long syntax**, with these three keys
  (plus `protocol: tcp`):
  ```yaml
  ports:
    - target: ${KE_GATEWAY_API_LISTEN:-<n>}
      host_ip: ${KE_BIND_ADDRESS:-127.0.0.1}
      published: ${KE_API_PORT:-47100}
    - target: ${KE_GATEWAY_PHOENIX_LISTEN:-<n>}
      host_ip: ${KE_BIND_ADDRESS:-127.0.0.1}
      published: ${KE_PHOENIX_PORT:-47101}
  ```
  It means the same as the short string
  `"${KE_BIND_ADDRESS:-127.0.0.1}:${KE_<X>_PORT:-<default>}:<container port>"`
  that this section first prescribed. The long form is preferred because each
  part is a separate key that a test can check, and an address is never
  split on `:`. Rules: `host_ip` is exactly `${KE_BIND_ADDRESS:-127.0.0.1}`;
  `published` is `${KE_<X>_PORT:-<default>}` with `<default>` in
  47100–47199; `target` is a `${KE_GATEWAY_<X>_LISTEN:-<n>}` variable, never
  a literal (review N3: the hardcoded scan treats `*_LISTEN` values as ports).
  Only `gateway` has `ports:`.

  `:-` rather than `:?`, because `verify.sh` and CI run compose without a
  `.env`. The container ports are the gateway's unprivileged listen ports,
  `KE_GATEWAY_API_LISTEN`, `KE_GATEWAY_PHOENIX_LISTEN` and
  `KE_GATEWAY_MODEL_LISTEN` (the last is never published). The API's own
  listen port is `KE_API_LISTEN`, which compose passes to `api`, `gateway`
  and `gates-it` as `KE_API__LISTEN_PORT` (the `Settings` name); its compose
  default equals `api.listen_port` in `defaults.yaml`. These are compose
  variables, and the gateway's nginx templates read the same variables (the
  official image's envsubst templates), so there is one source per port. The
  developer picked them outside 47100–47199 and recorded them in the
  handoff. Every `${VAR:-default}` default in compose equals that
  variable's value in `.env.example` (`test_compose_defaults_match_env_example`,
  which generalizes platform-config's phoenix drift test). The `phoenix`
  service itself publishes nothing once the gateway exists; its
  platform-config line `127.0.0.1:${KE_PHOENIX_PORT:-47101}:…` moves to the
  gateway.
- **Bind address.** `KE_BIND_ADDRESS` is an IPv4 literal, `127.0.0.1` by
  default. IPv6 binding is out of scope (the long syntax would carry it, but
  nothing validates it yet). Binding anything other than loopback
  (127.0.0.0/8) exposes unauthenticated services to the LAN. That is a
  deliberate operator choice in `.env`, and **outside `dev` it is refused
  until auth-audit lands**. An empty or unset `KE_ENV` is **not** `dev` in
  all three places (fail closed). Three places enforce it (PS-2.14, Q33a),
  because the engine does not own the socket the gateway binds:
  - **Engine:** startup refusal 6 (§2.3 list). `Settings.bind_address`
    (env `KE_BIND_ADDRESS`, default `127.0.0.1` in `defaults.yaml`) is
    validated as an IPv4 address at load, so a bad value is a `ConfigError`
    naming the variable. `check()` raises
    `StartupRefused("KE_BIND_ADDRESS", …)` when it is not loopback while
    `env≠dev`. Compose passes `KE_BIND_ADDRESS` and `KE_ENV` into `api` and
    `worker`.
  - **Gateway:** the gateway image adds one POSIX `sh` script to
    `/docker-entrypoint.d/` (`docker/gateway/10-ke-bind-check.sh`). Under the
    same rule it exits non-zero, so nginx never starts and nothing is
    published. Compose passes the same two variables into `gateway`. This is
    the check that actually stops the publish: the gateway must start without
    `api` (see Images), so the engine's refusal alone would leave Phoenix on
    the LAN. `lint.sh`'s shellcheck glob gains `docker/**/*.sh`.
  - **Launch (amended, rework 1: review B3, security L-1).** `launch.sh` and
    `launch.ps1` check **the values compose will actually use**, not their
    own reading of the env file. They build one compose argument list
    (`--env-file "$KE_ENV_FILE"` when set, plus whatever `COMPOSE_FILE` and
    `COMPOSE_PROJECT_NAME` say) and use it for both
    `docker compose … config --format json gateway` and `up`, so the check
    and the launch cannot read different inputs. From the JSON they read
    `services.gateway.environment.KE_ENV` and every
    `services.gateway.ports[].host_ip` (and `published`, for the printed
    URLs). There is **no `.env.example` fallback** any more (it said
    `KE_ENV=dev` and made launch fail open). Rules, all fail closed:
    - `KE_ENV` missing, empty, or anything but exactly `dev` → not dev.
    - A port entry with no `host_ip` binds every interface → treated as
      `0.0.0.0`.
    - A `host_ip` that is not an IPv4 literal → refused in every env (as
      today).
    - No port entries at all (the verify overlay resets `ports:`) →
      nothing is published, so there is nothing to check.
    - `docker compose config` failing → launch fails.

    PowerShell parses with `ConvertFrom-Json`. Bash has no JSON parser among
    the prerequisites (Git and Docker only), so it extracts the keys line by
    line from compose's indented JSON. It joins lines but **never strips
    whitespace inside values** (`" dev"` must stay not-dev). A value with
    a JSON escape does not match the pattern, which counts as missing, so the
    result is still refused. This resolves all the L-1 dotenv forms
    (`export KEY=…`, `KEY = …`, `KEY: …`), because compose has already
    parsed them.
  - In `dev` all three log or print a warning naming `KE_BIND_ADDRESS` and start.
  - When auth-audit lands, it narrows the condition to "auth disabled", in
    all three places.
  - Residual: someone who edits the compose file by hand can bypass all of
    them. That is accepted, the same trust level as editing the code.
- **Gateway upstream check (rework 1, security M-3 and L-3; extends DR30 to
  the gateway).** The engine's egress startup check refuses an upstream that
  is not on the allowlist, but only in `api` and `worker`. The gateway itself
  forwarded to any `KE_MODEL_UPSTREAM` for every `backend` container, and the
  value went through envsubst into nginx config unchecked, so a crafted value
  could add a server block. A second POSIX `sh` script,
  `docker/gateway/11-ke-upstream-check.sh`, runs from `/docker-entrypoint.d/`
  after the bind check and **before** the image's `20-envsubst-on-templates.sh`.
  On any failure it exits non-zero, so no template is rendered and nginx never
  starts. Like the bind check, it names the variable and never echoes the
  value.
  - `KE_MODEL_UPSTREAM` empty or unset: allowed. The forward has no upstream,
    and its connections fail, as in CI.
  - Otherwise the whole value must be a strict `host:port`, matched as one
    line (a value containing a newline is refused first, because `grep`
    matches per line):
    - host: an IPv4 dotted quad, or DNS labels `[A-Za-z0-9]` or
      `[A-Za-z0-9][A-Za-z0-9-]*[A-Za-z0-9]`, each at most 63 characters,
      joined by single dots, with no trailing dot;
    - port: decimal `1`–`65535`, no leading zero, no sign;
    - nothing else (no whitespace, quote, `;`, `{`, `}`, `$`, `/`, scheme or
      brackets).
  - The host, case-folded, must equal an entry of `KE_EGRESS_ALLOWLIST`.
    Entries are comma-separated, trimmed, case-folded, with a trailing dot
    removed, exactly as the engine's `normalise_host` does. No wildcards. An
    empty allowlist with a non-empty upstream is refused.
  - **Every other value the templates substitute is checked too (L-3;
    rework 1 left it partly open, security re-audit R3/R3b; required in
    rework 2):** `KE_GATEWAY_API_LISTEN`, `KE_GATEWAY_PHOENIX_LISTEN`,
    `KE_GATEWAY_MODEL_LISTEN`, `KE_API__LISTEN_PORT` and `PHOENIX_PORT` must
    each be a decimal integer `1`–`65535`, with the same port grammar as the
    upstream (no leading zero, no sign, no whitespace, one line). Unset or
    empty is refused too, because the template would render an empty
    `listen`. The upstream keeps its rules above. Each failure exits
    non-zero before `20-envsubst-on-templates.sh`, names the variable and
    never echoes the value.
  - **Drift test (fast):** the set of `${…}` names in
    `docker/gateway/templates/*` must equal the set the entrypoint checks
    validate (the five ports plus `KE_MODEL_UPSTREAM`), read from one list in
    the script, so a new template variable cannot skip the check. If the
    image's envsubst filter (`NGINX_ENVSUBST_FILTER`) is set, the test reads
    it too.
  - **First tests (fast), per port variable:** a payload such as
    `80; } location /x { proxy_pass http://1.1.1.1:80; } server { listen 81`,
    `0`, `65536`, `080`, `-1`, `80 `, a newline, empty and unset → exit
    non-zero, output without the value; `1` and `65535` → pass.
  - Compose passes `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` into
    `gateway` from the same variables the engine reads, so the two checks
    cannot disagree.
  - The proposed first test is `test_gateway_upstream_check_refuses_off_allowlist`
    (fast). It runs the script under `sh` with: empty (passes); allowlisted
    `host:port` (passes); the same host in a different case (passes); a host
    not on the allowlist, as in the M-3 repro (`one.one.one.one:80` with
    allowlist `gateway`); an empty allowlist; the L-3 injection payload; a
    newline; a missing port, port `0`, `65536`, a leading zero; a scheme; a
    trailing dot; and a non-integer listen port. Each failure exits non-zero
    and its output does not contain the value. A Dockerfile test asserts the
    script is copied mode 0755 with a name that sorts before `20-`.

**`.env.example`** holds:
- the published ports, and `KE_BIND_ADDRESS=127.0.0.1` with a comment that
  any other value is refused outside `dev` until auth-audit;
- the gateway listen ports (`KE_GATEWAY_API_LISTEN`,
  `KE_GATEWAY_PHOENIX_LISTEN`, `KE_GATEWAY_MODEL_LISTEN`), which are not
  published, and the API listen port `KE_API_LISTEN` (rework 1, review N3;
  it replaced `KE_API__LISTEN_PORT` in `.env.example`, because the port-range
  test matches `KE_*_PORT`);
- `KE_MODEL_UPSTREAM=` **empty** (amended, rework 2, review R2). A comment
  above it says the value is the model host as `host:port`, set per
  deployment in `.env`, and that this deployment's host is `aria-gb10-2`
  (Q7 ruling). An empty upstream is valid: the gateway starts and the model
  forward has no upstream (as in CI). The comment is the only committed
  config text that names the host; the hardcoded scan (§2.3, rule 1) fails
  if any scanned code repeats it;
- `KE_EGRESS_ALLOWLIST=` **empty**, set by the operator in `.env` together
  with the upstream (for example `gateway,<upstream host>`). With an empty
  upstream nothing needs allowing; a non-empty upstream with an empty
  allowlist is refused by the gateway and the engine;
- `KE_ENV=dev`;
- `KE_AUTH__ENABLED=false`, because auth arrives in auth-audit;
- the secret placeholders, each `changeme-<key>` (placeholder-secret ruling).

`api` and `worker` dial `http://gateway:<KE_GATEWAY_MODEL_LISTEN>/v1`. That
port is reachable on `backend` only and never published. The per-pass
`base_url` defaults in `defaults.yaml` carry it, and a drift test ties them to
`.env.example`.

**`/healthz` (PS-2.4).** Returns `200 {"status":"ok"}` from process state only,
with no I/O. It is untraced, because it is liveness and is called every few
seconds. The compose healthchecks of `api` and `gateway` use it.

**`/readyz` (PS-2.5, Q6 ruling).** The response looks like this:
```json
{"ready": true,
 "checks": {"postgres": {"ok": true, "reason": null},
            "neo4j": {...}, "valkey": {...},
            "model_host": {"ok": false, "reason": "refused", "required": false}}}
```
- `ready` = postgres ∧ neo4j ∧ valkey. The status code is 200 if ready,
  otherwise 503.
- **Probes:**
  - postgres: `SELECT 1`.
  - neo4j: `RETURN 1`.
  - valkey: `PING`.
  - model host: `GET {compose.base_url}/models` through `ModelClient`, so it
    passes the egress guard.
- **Timeouts:** each probe has `readiness.timeout_s`.
- **Reasons:** a fixed vocabulary (`timeout | refused | auth_failed |
  egress_denied | error:<ExceptionClass>`). It never includes a DSN, host
  credential or message text.
- **Spans:** `api.readyz` (CHAIN), with one `readyz.<dep>` (TOOL) per
  dependency.

**Worker (PS-2.6).**
- The worker is RQ on Valkey, started as `python -m engine.worker`, and listens
  on one queue, `default`.
- `engine.worker.jobs.noop(token)` runs `INCR ke:noop:<token>` and returns.
- RQ records the job as `finished`.
- Each job runs in a `job.<name>` CHAIN span carrying the job id.
- The integration test enqueues to the real `worker` container from
  `gates-it`. It then asserts that the status is `finished` and the counter
  is 1.
- **2a placeholder (developer decision, accepted by review only with B2).**
  Until 2b brings RQ, `worker` runs `python -m engine.worker`, whose `main()`
  calls `engine.startup.startup()` and then idles (`signal.pause()`). So
  refusal 6 and every other refusal hold in `worker` as PS-2.14 (1) requires.
  A refusal exits non-zero; the container then restarts and never becomes
  healthy, so `launch.sh --wait` fails. 2b replaces the idle with the RQ
  loop in the same module, so the compose `command` does not change.
- **Entrypoints are unit-tested (review B2).** `engine.api.main()` and
  `engine.worker.main()` lose `pragma: no cover`. A fast test patches
  `uvicorn.run` (api) and `signal.pause` (worker), and asserts that
  `startup()` runs first and its `Settings` give the listen port, and that a
  `StartupRefused` (for example a non-loopback `KE_BIND_ADDRESS` with
  `KE_ENV=prod`) propagates before `run`/`pause` is called.

**Images.**
- `docker/app.Dockerfile` reuses the pinned `python:3.12-slim-bookworm` and
  `uv` bases, runs `uv sync --locked --no-dev`, runs as a non-root user, and
  copies `engine/` and `config/`. It does **not** copy `.env.example`
  (placeholder-secret ruling; the refusal checks the `changeme` prefix).
- `docker/gateway.Dockerfile` is the pinned nginx image plus templates. Its
  upstreams resolve per connection, so the gateway **starts and serves the
  other routes when any upstream is absent**: CI has no model host, and the
  harness may run `phoenix` without `api`.

**Scripts (PS-2.9).** Each script is a bash file for Linux plus a PowerShell
twin for Windows. macOS is not supported (Q20 ruling). They contain only
`docker compose` calls, plus the read-only `docker version` (launch) and
`docker network inspect` (smoke host half) checks.

| Script | Does |
|---|---|
| `build.sh` / `.ps1` | `compose build` (ke-app, ke-gateway, ke-gates), then `compose pull` of the digest-pinned images |
| `launch.sh` / `.ps1` | Copies `.env.example` to `.env` if it is missing (and says so). Checks Compose ≥ 2.24 and Docker Engine ≥ 28 (`docker version --format '{{.Server.Version}}'`; rework 1, M-2; Engine rule below), refusing below either. Reads the resolved `KE_ENV` and gateway `host_ip`s from `compose config --format json gateway` and applies the bind-address rule (Bind address above). Runs `compose up -d --no-build --wait` with the same arguments. Prints the URLs from the resolved `host_ip` and `published` values |
| `teardown.sh` / `.ps1` | `compose <args> down`, and `--volumes` only when asked. No `--profile` and no `--remove-orphans` (rework 2, Windows proof F3; rule below) |
| `smoke.sh` | the two-sided live smoke (§2.2), including the host-side `docker network inspect` isolation check (rework 2) |

**Engine version rule (rework 2, review R1-B2, security L-6).** The
`isolated` option is silently ignored below Engine 28, so this check is the
only M-2 control on such hosts, and it fails closed:
- `docker version --format '{{.Server.Version}}'` must exit 0, and its
  output, with only the trailing newline removed, must match the whole of
  `^[0-9]+\.[0-9]+\.[0-9]+$`. Empty output, a daemon error, a leading or
  trailing space, `garbage`, or a suffixed build such as `28.0.1-rc.1` are
  refused. Suffixed builds are refused on purpose (fail closed); an operator
  on one sees a message naming the Engine check.
- The major part is compared as an integer, `≥ 28`. No `sort -V` and no
  string comparison (`100.0.0` passes, `27.99.99` is refused).
- Refusal exits non-zero before `compose config` or `up`, and the message
  names the requirement and the version read (it is not secret).
- Both scripts implement the same rule; PowerShell anchors with `\A…\z`.
- `tests/fake_docker.py` answers `version --format …` with
  `FAKE_DOCKER_ENGINE` (default `28.0.0`), and exits non-zero when
  `FAKE_DOCKER_ENGINE_FAIL` is set. Cases for sh and ps1, each asserting no
  `compose up`: `27.5.1`, `27.99.99`, empty, `garbage`, ` 27.1.1`,
  `28.0.1-rc.1` and a non-zero exit refused; `28.0.0`, `29.5.2` and
  `100.0.0` accepted.

**Teardown scope (rework 2, Windows proof F3).** `teardown.sh`/`.ps1` stop
and remove only **their own project's default-profile services**: the same
compose argument list as launch (`KE_ENV_FILE`, `COMPOSE_FILE`,
`COMPOSE_PROJECT_NAME`), then `down`, plus `--volumes` when asked.
- `--profile '*'` is dropped: it pulled in `gates-it`, `probe` and the
  offline services, so a teardown of the default project removed one-shot
  containers that another run had started under the same project label.
- `--remove-orphans` is dropped too: which containers compose counts as
  orphans for profile-disabled services has varied between Compose
  releases, and the ruling is "only default-profile services". A container
  of a renamed or deleted service is removed by hand.
- One-shot services already run with `compose run --rm`. If one is left
  behind (for example a verify run killed mid-`run`), `down` cannot remove
  the network it holds and exits non-zero; `verify.sh`'s N7 warning names the
  project. That is accepted: it fails loudly, never silently removes
  another run's container.
- First tests (fast, fake docker, sh and ps1): the `down` call carries no
  `--profile` and no `--remove-orphans`, carries the project and env-file
  arguments, and carries `--volumes` only with `--volumes`/`-Volumes`.

All scripts honor `KE_ENV_FILE` and `COMPOSE_PROJECT_NAME`. `docs/quickstart.md`
names only these scripts and the prerequisites: Git, and **Docker Engine ≥ 28**
(for the isolated `backend` bridge, §2.1; amended in rework 1, M-2) with
Compose ≥ 2.24. It has two paths only, Windows (PowerShell) and Linux (bash),
and no macOS path (Q20 ruling).

**Script lint and tests (rework 1).** `scripts/lint.sh` (§2.2) lints every
script here. Fast tests drive `launch.sh`, and `launch.ps1` under the gates
image's `pwsh`, with a fake `docker` on `PATH` that answers `version` and
`compose version` and returns fixture `config --format json` output. The
cases: `KE_ENV` missing, empty, `" dev"`, `DEV` or `prod` with `host_ip`
`0.0.0.0` → exit non-zero and no `up`; `dev` with `0.0.0.0` → a warning, then
`up`; a port with no `host_ip` → treated as `0.0.0.0`; no ports → `up`;
`config` failing → exit non-zero; the Engine version cases (Engine version
rule above; rework 2, R1-B2). One case in the
host half of `smoke.sh` (full) runs the **real** `docker compose config`
with an env file holding `KE_ENV=prod` and `export KE_BIND_ADDRESS=0.0.0.0`,
and asserts that `launch.sh` refuses, which proves that the fixture shape
matches real compose.

**Developer decisions accepted in review (2a, 2026-10-19).**
- **Worker placeholder:** accepted only because it calls `startup()` (B2;
  Worker above).
- **Postgres user and database are the literal `engine`** in compose: accepted
  for 2a. They duplicate `stores.postgres.{user,database}` in
  `defaults.yaml`. Before readyz connects in 2b, either a drift test ties the
  two, or compose takes the user from a variable with an `.env.example` entry
  (review N4, deferred).
- **Compose warns when there is no `.env`** about unset `KE_ENV` and the two
  store secrets: accepted, because each fails closed. Unset `KE_ENV` is not
  dev in the engine, the gateway and launch. The secrets have no default
  (F3), and postgres and neo4j refuse to start on an empty one. The PS-2.2
  smoke `test_compose_resolves_without_env_file` (host half of `smoke.sh`,
  restored to 2a by review B4) asserts that `docker compose config` succeeds
  despite the warnings from a temp copy with no `.env`, and that every
  `host_ip` is `127.0.0.1`.
- **`KE_API_LISTEN`** in place of `KE_API__LISTEN_PORT`, and **the long port
  syntax**: accepted (N1, N3; Ports above).

### 2.5 platform-offline (ADR-KE-012)

**Bundle (PS-3.1).** `scripts/bundle.sh` / `.ps1` writes
`dist/knowledge-engine-<git sha>/` (and a `.tar` of it) containing:
- `images/*.tar`: `docker save` of every image `docker compose config --images`
  lists for the stack services, plus `ke-app`, `ke-gateway`, `ke-gates` and the
  `dind` image. The gates image is included so that verification can run on the
  box;
- no wheels: the images carry their dependencies (bundle ruling);
- `assets/`: vendored assets (none until `frontend`);
- `compose/`: `docker-compose.yml`, `.env.example`, `config/`, `scripts/`,
  `docs/quickstart.md`;
- `bundle.json`: git sha, creation time, and each image's name and digest;
- `MANIFEST.sha256`: `sha256sum` format, covering every file except itself.

**Platform.** The bundle is linux/amd64 only, installed from Linux (bash) or
Windows (PowerShell). macOS and Apple silicon are out of scope (Q20 ruling).

**Install.** `scripts/install.sh` / `.ps1` verifies the manifest before
anything else. It rejects a mismatch, a missing file, or **any file not listed
in the manifest**. Only then does it run `docker load` for each image.
- **Tools:** bash uses `sha256sum -c --strict` plus a listing comparison;
  PowerShell uses `Get-FileHash`.
- **Integrity, not authenticity:** `bundle.sh` prints the manifest's own hash
  for an out-of-band comparison. Signing is out of scope (flagged to security).

**Gates (both are stages inside `verify.sh full`, not separate CI jobs).**
- `ci/offline` (PS-3.3) runs in `smoke.sh` against the verify stack.
  - Assertion: `docker compose exec api` and `exec worker` each attempt a TCP
    connection to `KE_OFFLINE_PROBE_TARGET`, and the attempt must fail.
  - Control: the same probe from a throwaway `ke-app` container on `edge` must
    succeed. If the control fails, the gate fails as *inconclusive*; it never
    passes silently.
  - The target is chosen at implementation and recorded in the handoff.
- `ci/deployable-offline` (PS-3.2) is `scripts/offline_check.sh` (host):
  1. `bundle.sh`.
  2. Start `dind` (a fresh anonymous `/var/lib/docker`, on the internal network
     `offline`, TLS certificates on a shared volume).
  3. In `offline-client`:
     - assert `docker image ls -q` is empty;
     - `install.sh`;
     - `launch.sh`;
     - `smoke.sh --live`;
     - `teardown.sh`.
  4. `down -v` of the `ke-offline-<suffix>` project.

  Any pull or package-index call fails, because the inner daemon has no route
  out.

  **F5 ruling:** it runs in every local `full`, so the offline proof is the
  same locally and in CI. (Since Q30, local `full` covers more than CI
  overall: see ADR-KE-009.) A daemon that cannot run privileged containers is a blocker, never a
  skip. Revisit if `full` exceeds about 15 minutes locally.

`.github/workflows/ci.yml` keeps its single step. **F6 ruling:**
`timeout-minutes` is set to the measured duration of `verify.sh full` plus 50%
(PS-3.4, `test_ci_job_has_timeout`); the measurement is recorded in the
sub-item's handoff.

### 2.6 First failing tests

Suggested first test per sub-item, followed by the order of the rest.

- **platform-config.** First: `test_config_defaults_and_env_override`.
  Then:
  1. `test_config_rejects_bad_type`, where the message names the key, not the
     value.
  2. `test_config_ignores_unprefixed_names` (F2) and
     `test_config_missing_secret_names_key` (F3).
  3. `test_egress_guard_startup`.
  4. `test_egress_guard_runtime`, with a socket spy recording zero connects,
     plus `test_egress_guard_mutant_goes_red`.
  5. `test_startup_refuses_unsafe`, one subTest per case, plus the dev
     warnings; then `test_startup_refuses_placeholder_secrets` (PS-1.9: any
     `SecretStr` starting with `changeme`, outside `dev`; allowed in `dev`)
     and `test_env_example_secrets_use_changeme_prefix` (every secret key in
     `.env.example` has a `changeme-` value, so the two cannot drift).
  6. `test_startup_is_traced`, using the in-memory exporter, which also proves
     nothing is exported to a non-local collector.
  7. `test_no_hardcoded_ports` and `test_no_hardcoded_hosts_or_models`:
     scanner on fixtures first, then the repository.
  8. `test_harness_default_collector_matches_env_example`.
  9. `test_test_sh_enforces_coverage_and_mypy`, plus recorded RED runs.
  10. `test_python_pinned_to_312`.
- **platform-stack** (rewritten 2026-10-19 in implementation order, with the
  names aligned to PS-2.x; the names marked *proposed* need the analyst to
  adopt them). The compose tests parse the YAML of every compose file.
  - **Rework 1 (2026-10-19), first:** the new M-1/L-2 subtests of
    `test_provider_not_built_by_engine_is_refused` and
    `test_configure_tracing_refuses_when_install_is_ignored` (ADR-KE-010);
    `test_backend_network_isolated_from_host`;
    `test_gateway_upstream_check_refuses_off_allowlist` and the template
    variable drift test (§2.4); the launch fake-docker cases on resolved
    config (§2.4 Scripts); the api/worker entrypoint tests (§2.4 Worker);
    `test_lint_sh_runs_shellcheck_and_psscriptanalyzer` and the `verify.sh`
    host-half fake-docker test (§2.2); then the amended
    `test_gates_it_has_no_route_out` (integration).
  - **Fast first** (`verify.sh fast`, `gates`):
    0. *If M5 lands here (recommended; ADR-KE-010 M5 amendment):*
       `test_provider_not_built_by_engine_is_refused`.
    1. `test_compose_services_have_restart_policy` (PS-2.3): every service
       without a profile has `unless-stopped`; `gates`, `gates-it`, `probe`,
       `dind` and `offline-client` have none.
    2. `test_compose_images_pinned_by_digest` (PS-2.1).
    3. `test_published_ports_use_bind_address` (port ruling; long syntax
       since rework 1, N1). Every `ports:` entry of every service is a
       long-syntax mapping with `host_ip: ${KE_BIND_ADDRESS:-127.0.0.1}`,
       `published: ${KE_<X>_PORT:-<n>}` and `target` a `${…_LISTEN:-<n>}`
       variable, and only `gateway` has any.
    4. `test_env_example_ports_in_range_and_unique` (PS-2.2), plus
       `test_compose_defaults_match_env_example`, which generalizes
       platform-config's phoenix drift test.
    5. `test_startup_refuses_non_loopback_bind_address`
       (refusal 6). Subtests: `0.0.0.0` and a LAN address are refused in
       `prod`/`ci` and the refusal names `KE_BIND_ADDRESS`; in `dev` there is
       a warning; `127.0.0.1` and `127.0.0.2` pass; a non-IPv4 value is a
       `ConfigError`. Then `test_gateway_bind_check_refuses_non_loopback`,
       which runs `docker/gateway/10-ke-bind-check.sh` under `sh` with the same
       cases and checks the exit codes.
    6. `test_only_gateway_on_edge_network` (PS-2.10).
    7. `test_gates_it_internal_only_and_no_socket` (PS-2.7): every network
       `gates-it` joins is `internal: true`, it mounts no socket, and `gates`
       keeps `network_mode: none`.
    8. `test_no_docker_socket_mounted` (PS-2.11), then
       `test_stack_services_have_no_bind_mounts` (PS-2.12).
    9. `test_harness_default_collector_matches_env_example` and
       `test_docs_name_current_phoenix_port` (PS-2.2).
    10. `test_model_tests_skip_with_named_reason` (PS-2.7): the skip helper,
        given a failed probe, raises `SkipTest` naming `KE_MODEL_UPSTREAM` and
        a vocabulary reason; given success, it does not skip. Then
        `test_no_model_calls_in_unit_suite`.
    11. `test_env_example_not_in_app_image` (PS-1.9): parse
        `docker/app.Dockerfile` and its `.dockerignore`.
    12. `test_quickstart_names_existing_scripts` (PS-2.9) and
        `test_claude_md_lists_verify_only_checks` (PS-2.13).
  - **Then integration** (`verify.sh full`, in `gates-it`):
    1. `test_gates_it_has_no_route_out` (F-A, PS-2.7, §2.2). A raw TCP
       connect to a TEST-NET-1 address fails fast with `ENETUNREACH` or
       `EHOSTUNREACH`, never a timeout (rework 1, B1); a connect to the
       `backend` bridge gateway does not reach the host (rework 1, M-2); and
       `gateway`'s model listen port accepts. It goes first because every
       later test assumes this topology. The earlier in-process socket-guard
       test is superseded (PS-2.7), and its guard fixture is dropped.
    2. `test_egress_allowlist_holds_with_network_access` (PS-2.7, DR38
       mutant recorded).
    3. `test_healthz` (PS-2.4; integration per the criterion).
    4. `test_readyz_reports_each_dependency`, `test_readyz_fails_when_store_down`,
       `test_readyz_ready_without_model_host` (PS-2.5).
    5. `test_worker_consumes_noop_job` (PS-2.6).
    6. Model-calling, skipping by name when the host is unreachable:
       `test_readyz_reports_reachable_model_host`.
  - **Then smoke and gates:** `test_stack_services_healthy` and the store
    stop/start in `scripts/smoke.sh` (PS-2.1, PS-2.5, PS-2.8); shellcheck and
    PSScriptAnalyzer (PS-2.9); the recorded Windows run (Q31).
  - That the *app* containers have no route out stays proven by `ci/offline`
    (platform-offline).
- **platform-offline.** First: `test_bundle_manifest_rejects_tamper` (fast).
  It covers both `install.sh` and `install.ps1` on a tiny fixture bundle, in
  three cases: a byte changed, a file missing, and an extra file. Then:
  1. `test_bundle_lists_every_compose_image`.
  2. `test_ci_job_has_timeout` (PS-3.4, F6), plus the recorded measurement.
  3. The gates `ci/offline` and `ci/deployable-offline`, each with a recorded
     run that shows it can go red (DR38).

## 3. The three planes (proposed)

```mermaid
flowchart TB
  subgraph DataPlane["Data plane (PostgreSQL + blobs)"]
    SRC[source<br/>corpus, source_key]
    SREV[source_revision<br/>checksum, revision_no, parent]
    LED[ingest_ledger<br/>one row per file, skip reason]
    REC[record]
    RREV[record_revision<br/>cause, parser/profile/schema versions]
    FV[field_value<br/>value or typed Unknown, how, revision]
    SNAP[corpus_snapshot<br/>immutable record_revision set]
    SRC --> SREV --> LED
    SREV --> RREV
    REC --> RREV --> FV
    SNAP -.members.-> RREV
  end
  subgraph KnowledgePlane["Knowledge plane (Neo4j)"]
    ENT((Entity<br/>built_from: record_revision_id))
    VEC[[Section vector<br/>truncated, model, dim, built_from]]
    ENT -- REL, evidence --> ENT
    ENT -- DUPLICATE_OF canonical --> ENT
    VEC -- OF --> ENT
  end
  subgraph PolicyPlane["Policy book (PostgreSQL)"]
    RK[rule<br/>rule_key]
    RR[rule_revision<br/>typed definition, citation, tier, status]
    BV[book_version<br/>ratified_at, effective_from, hash]
    CS[changeset<br/>mutable draft]
    RK --> RR
    BV -.members.-> RR
    CS -.proposes.-> RR
  end
  RREV ==> ENT
  RREV ==> VEC
  RR -- cites clause in --> SREV
```

- **Data plane:** original files plus normalized records. Lineage is stored per
  record revision: source revision, page or region, extraction method, parser
  version, model and version, checksum and timestamp. Field values are a typed
  union, `Known(value) | Unknown(reason)`, and each carries `how ∈ {parsed,
  routed, entered, imported}` (DR4–DR6).
- **Knowledge plane:** Neo4j holds both the graph and the vector indexes. The
  graph schema comes from the domain pack. Every node and vector stores
  `built_from` (record revision id) and the versions it was built with (DR8).
  Edges are canonically oriented and MERGEd idempotently (DR10).
- **Policy book:** typed rule revisions grouped into immutable book versions.
  It is evaluated by a pure-Python deterministic evaluator that cannot import an
  LLM client (import-graph test).

## 4. Revision history: corpus and policy (proposed; ADR-KE-007)

Both histories use one pattern: **append-only revision rows, a computed
"current" view, immutable snapshots or versions for anything a decision or
metric depends on, and an audit-chain entry per write.** Mutating a revision is
impossible at the database-role level. The application role has `INSERT` and
`SELECT` only on revision tables. "Current" is a view (the latest non-superseded
revision), never an updated pointer column, so no write can be lost.

### 4.1 Corpus revisions

```mermaid
stateDiagram-v2
  [*] --> r1: first ingest (source_changed)
  r1 --> r2: new checksum (source_changed)
  r2 --> r3: parser/profile/schema bump (parser_changed…)
  r3 --> r4: reviewer correction (human_correction, entered)
  r4 --> r5: re-parse disagrees with entered value → stays r4 value, conflict to review
  r4 --> r6: restore of r2 (restore, via review queue)
  r6 --> t: deleted upstream (tombstone)
  t --> [*]
```

- **Identity:** `source(corpus, source_key)`, where `source_key` comes from the
  institution profile's external ID, else the path, else the uploader's explicit
  choice (A10). Similarity never decides identity (DR12).
- **Re-ingest:** the same checksum produces no revision (only `seen_at` is
  updated). A new checksum produces `source_revision n+1`, then extraction, then
  `record_revision` with `cause=source_changed`. A parser, profile or schema
  version change re-extracts and writes `cause=parser_changed|profile_changed|
  schema_changed` revisions.
- **Entered values win:** extraction never supersedes a field whose current value
  is `entered`. It records a `field_conflict` row and a review item (§R-REV-C.5).
- **Freshness:** a single SQL plus Cypher predicate,
  `derived.built_from ≠ current_revision(record)`, defines *stale*. The funnel,
  the impact panel and the freshness CLI all call that one predicate (DR32).
- **Snapshots:** `corpus_snapshot` is an immutable membership table. Baselines,
  findings files and metrics reference a snapshot id. Snapshot comparison
  returns the buckets `added | changed | removed | unchanged | unaccounted`,
  and a test asserts they sum to the union of both snapshots (DR33).
- **As-of reads:** queries take `as_of` (snapshot id or timestamp), which
  resolves to a revision set *inside* the query, together with the authorization
  predicate (DR39).

### 4.2 Policy-book revisions

```mermaid
stateDiagram-v2
  [*] --> proposed: LLM or human proposes (cites clause @ source revision)
  proposed --> in_review: changeset baselined on snapshot S (DR18–20)
  in_review --> ratified: owner-tier human + decision_note
  in_review --> rejected: owner-tier human + decision_note
  ratified --> superseded: newer version ratifies a new revision of the rule
  ratified --> retired: newer version drops the rule
  ratified --> citation_stale: cited clause text changed in a new policy-doc revision
  citation_stale --> in_review: re-review packet
```

- **Changeset → version:** edits collect in a mutable `changeset`. Submitting
  freezes it, runs the baseline on a named snapshot, and builds the review packet
  (typed diff, effect diff and per-rule precision). Ratifying all its rules
  publishes `book_version n+1` with a content hash, `ratified_at` and
  `effective_from` (A12).
- **Typed diff:** rule definitions are pydantic models (decision table,
  threshold, routing). The diff is structural: cells, operands, targets, tier
  and citation. It is never a text diff of YAML.
- **Effect diff:** for two versions on the same snapshot, the baseline results
  are joined per record, and the diff lists records whose outcome changed.
- **Revert:** a new changeset that re-proposes an older rule revision's
  definition. It goes through the same baseline and ratification. There is no
  pointer rewind.
- **Provenance on outputs:** `draft`, `answer` and `published_artifact` store
  `book_version_id`, `fired_rule_revision_ids[]`, `snapshot_id` or
  `record_revision_ids[]` and `evaluated_at`.

### 4.3 Revision UX

The UX is server-rendered, readable without JavaScript, and shows no similarity
percentages.

| View | Corpus | Policy |
|---|---|---|
| Timeline | Source page → History: revisions with cause badge, actor/version, skip outcome | Book → Versions: status, ratified_at / effective_from, ratifiers, session |
| Compare | Any two revisions: field diff, section word diff, table cell diff, explicit Unknown↔value | Any two versions: rules added/removed/changed with typed diff + effect diff |
| Blame | Per field: value history, `how`, actor, revision | Per rule: revision history, proposer (LLM flagged), decision notes |
| Impact | Derived objects built from this revision, stale count (live query) | Outputs produced by this rule revision (live query) |
| Snapshot | Snapshot list, snapshot-vs-snapshot buckets | Baseline runs per version, keyed by snapshot |
| Change action | Correction or restore → reason + preview diff → review queue | Edit or revert → changeset → baseline → ratification packet |

Diffs are computed server-side by one `revision_diff` module per plane, which
returns a typed diff model. Templates render that model, and tests assert on
the model, not on HTML.

## 5. Policy-book lifecycle (proposed, `policy-book`)

```mermaid
sequenceDiagram
  participant D as Policy doc (source revision)
  participant L as LLM (propose only)
  participant C as Changeset
  participant B as Baseline runner
  participant H as Owner-tier human
  participant V as Book version
  D->>L: clauses
  L->>C: proposed rule revisions + clause citations
  H->>C: edit (field by field)
  C->>B: freeze, run on snapshot S (full corpus)
  B-->>C: per-rule effect, precision, always/never-fires flags
  C->>H: review packet (typed diff + effect diff)
  H->>V: ratify / reject with decision_note
  V-->>V: immutable version n+1, effective_from
```

The registry is versioned YAML. The loader refuses to start if a knob lacks a
register entry, or if a `ratified` entry lacks `decided_by`, `decided_on` or
`decision_note` (DR16). `docs/register.md` is generated, and CI fails on drift.

## 6. Agent workflow (proposed, `agent-workflow`)

```mermaid
flowchart LR
  Q[Request + session actor] --> PL[1 Plan<br/>CHAIN]
  PL --> LO[2 Locate<br/>RETRIEVER x3: title/keyword PG, graph, vector]
  LO --> EV[3 Evaluate ratified rules<br/>TOOL, deterministic]
  EV --> CO[4 Compose<br/>LLM, temp 0, field patches]
  CO --> VE[5 Verify carry-through<br/>CHAIN, fail closed]
  VE --> VA[6 Validate<br/>TOOL, deterministic]
  VA --> RQ[7 Review queue]
  RQ -->|human approve| PU[8 Publish]
  VE -.fail.-> RQ
  VA -.fail.-> RQ
```

The whole run is an `agent_span` with one child span per step. The authorization
predicate is part of every retriever query template, and the parameters are
recorded separately from the template. `OPENINFERENCE_HIDE_INPUTS` and
`OPENINFERENCE_HIDE_OUTPUTS` default to `true`.

## 7. Engine / pack / profile split (proposed)

```mermaid
flowchart TB
  subgraph Engine["engine/ (generic code)"]
    E1[ingest ledger, revisions, snapshots]
    E2[extract framework, lineage, typed Unknown]
    E3[dedup tiers, clustering, graph builder]
    E4[policy-book loader, registry, evaluator, baseline]
    E5[verifier, validator, review queue, audit, auth]
    E6[workflow, retrieval, UI shell]
  end
  subgraph Pack["packs/jd/ (declarative YAML + pack code hooks)"]
    P1[schema: sections, entity types, relations]
    P2[extraction profiles per template]
    P3[harmonize/merge, composer prompts]
    P4[JD quality rules]
  end
  subgraph Profile["profiles/sfu/ (pure data)"]
    S1[classification schemes: Hay, WJQ routing]
    S2[employee groups, templates, footer wording]
    S3[rulebook values]
  end
  Pack -->|loaded by| Engine
  Profile -->|values for| Pack
  Profile -->|values for| Engine
```

A pack is YAML plus an optional Python module that implements engine-defined
protocols (for example `SectionMerger`). The engine never imports a pack by
name, and a test asserts that engine code contains no profile literals.

## 8. Port verdict table (from `humanaxiom/jd-assistant` @ `2e3e6dc`)

This follows the pattern of the JD repo's ADR-005: one row per module, a verdict,
and a rationale that **bolds** any obligation the port carries. Pure,
deterministic code is ported with its tests. Code coupled to the JD schema or
its stores is rewritten from spec, with the old code and tests kept as the
behavioural reference. Paths are relative to `core/src/` unless noted. Line
counts come from `wc -l` at `2e3e6dc`.

Verdicts: **engine** = generic code; **jd pack** = JD-specific; **SFU profile**
= institution data (pure YAML); **split** = parts go to more than one layer;
**discard** = not carried over.

| # | JD-repo module | LOC | Verdict | Rationale / obligation |
|---|---|---|---|---|
| 1 | `settings.py` | 691 | split | Typed config loader → engine. CAS URL and origins → **SFU profile** |
| 2 | `agents/`, `gates/`, `models/`, `worker/` | ~1,180 | discard | Dev-harness tooling (task runner, gate runner). Replaced by `.claude/agents/` and `scripts/verify.sh` |
| 3 | `memory/` | 137 | discard (pattern → engine) | Harness memory. Its Neo4j vector-index plumbing is reused in the engine's vector store |
| 4 | `api/` shell (main, csrf, deps, errors, readiness, security_headers, service_origin) | 1,230 | engine | Generic hardening. **Drop the harness routes** and add the authz-matrix test (DR39) |
| 5 | `api/db` | 141 | engine | users, roles, sessions. Role names become pack config |
| 6 | `api/services` | 373 | split | audit verify, sessions, users → engine. `cas_service` → **pluggable SSO adapter** (DR42) with SFU config in the profile |
| 7 | `api/routes` | 3,843 | split | auth, admin, front door and forms → engine. review, library and dashboards → **generic engine views over pack data**. compose and compose_ui → jd pack |
| 8 | `api/templates` | 25 files | split | base, login, error, admin and `review_diff` → engine (seed of the revision UX, §4.3). compose, library and role pages → jd pack. Branding and footer → profile |
| 9 | `jd_export/` | 166 | jd pack + profile | The .docx renderer → pack. Template file and mandated wording → profile |
| 10 | `jd_core/models` | 1,137 | jd pack | JD schema contracts. **Rename off the SFU name.** Fields adopt the typed `Unknown` (DR4) |
| 11 | `jd_core/parser` | 1,730 | jd pack + profile | Segmenter → pack. Heading sets, WJQ/CUPE templates and grade patterns → profile. `PARSER_VERSION` becomes a **pack-declared version stamp** (DR8) |
| 12 | `jd_core/quality` | 1,356 | split | Gates and scoring → engine rule evaluator. Validators → pack. Thresholds and boilerplate → profile |
| 13 | `jd_core/rules` (loader 4,365 L + 25 YAML) | 4,977 | split (critical) | Content-hash version stamps, the register 3-way check and trivial exemptions → **engine policy-book loader** (DR16). Rule schemas → pack. Values → profile. Technical YAML (dedup, embeddings, textnorm) → engine defaults. **Rulebook history moves from git into the versioned `book_version` tables (§4.2)** |
| 14 | `jd_core/bank` | 3,762 | split | minhash, shingles, clustering, word_diff, change_log and provenance → engine (`word_diff` backs the revision diffs). merge, similarity, render, embed_text and version_diff → pack. hay_signals and title_family → profile |
| 15 | `jd_core/textnorm.py` | 261 | engine | Generic text normalization |
| 16 | `jd_bank/` helpers | 143 | split | `stable_reason` → engine. `jd_text` → pack. `grade_import` → profile |
| 17 | `jd_bank/db` + alembic 0001–0006 | 404 | engine (rewrite) | Domain-neutral once renamed. **Rewrite to the source / revision / snapshot schema of §4.1.** The old `UNIQUE(storage_ref, sha256)` row-per-change design had no current flag, so changed files double-counted |
| 18 | `jd_bank/ingest` | 1,527 | split | Walk, hash, extract and idempotency → engine ledger. Name scrub → pack. Filename facets → profile |
| 19 | `jd_bank/dedup` (tier 1) | 1,107 | engine | Exact-hash tier (DR9) |
| 20 | `jd_bank/dedup/near` | 1,528 | engine | MinHash/Jaccard with a text-source injection point |
| 21 | `jd_bank/dedup/role` | 1,308 | jd pack | Depends on JD signals |
| 22 | `jd_bank/cluster` | 1,162 | engine + pack hooks | Connected components → engine. Employee-group and level constraints → pack/profile hooks |
| 23 | `jd_bank/embeddings` | 1,590 | engine | Runner, store and reconcile → engine. **Stamp `built_from` record revision** (DR8). `roles.py` → pack |
| 24 | `jd_bank/harmonize` | 921 | jd pack | JD-specific measurement |
| 25 | `jd_bank/canonical` | 1,752 | split | Producer skeleton → engine. Merge policy → pack |
| 26 | `jd_bank/review` | 1,150 | engine | The approval and versioning spine; the core asset. Extend with rule revision provenance (§R-REV-P.6) |
| 27 | `jd_bank/llm` | 413 + 8 j2 | engine (prompts → pack) | OpenAI-compatible client and versioned prompt loader. **Per-pass config** (DR29) |
| 28 | `jd_bank/rewrite`, `jd_bank/quality` | 630 | jd pack | JD prompts. **Rewrite as field patches** (DR23) behind the carry-through verifier (DR24) |
| 29 | `jd_bank/security` | 95 | engine | Egress guard (DR30) |
| 30 | `jd_bank/composer` | 3,000 + 2 YAML | jd pack + profile | Composer → pack. Question sets and form routing → profile. `duplicates.py` and `persist.py` → candidate engine primitives |
| 31 | `jd_bank/library` | 2,112 | split | Library and funnel → engine. **The funnel must query the store live** (`_base.html:76` once served stale numbers). Families and units → profile |
| 32 | `jd_bank/baseline` | 1,487 | jd pack + profile | Runs over a **named corpus snapshot**. Era and group facets → profile |
| 33 | `jd_bank/bank_audit`, `field_audit` | 1,466 | jd pack (+ profile) | Per-form audits |
| 34 | `jd_bank/singletons` | 510 | discard (pattern → pack) | One-off investigation. DR11 is covered by a graph test |
| 35 | `core/scripts` | 546 | discard / profile | One-off backfills. `import_grades` → profile |

The tests come across with the code. At `2e3e6dc` the JD repo has 119 unit, 30
integration and 4 live test files, split by directory, with a `live` marker that
is excluded by default. The port keeps the same layout.

**Gaps the port must close.** The JD repo has no stale detection against a stored
rules or parser version. Its rulebook history exists only in git. It has no
history or diff UI for sources, parses or rules (only drafts get a diff against
the last published version). These gaps are what §4 and ADR-KE-007 address.

## 9. ADRs

The template's existing ADR (OpenInference tracing to Arize Phoenix) stays in
force, and its text is kept below unchanged. ADR-KE-001 is built (amended by
ADR-KE-009). ADR-KE-002 to ADR-KE-012 are **proposed**.

### ADR: OpenInference tracing to Arize Phoenix
- Context: `docs/log.md` records what each role did, but not how agent code
  behaved at runtime; custom Python agents exported as plain OpenTelemetry
  spans show up in Phoenix as a flat list.
- Decision: add `harness_telemetry`, a thin layer over the OpenTelemetry SDK
  that sets `openinference.span.kind` and the OpenInference input/output,
  retrieval-document, and token-count attributes, exported over OTLP/HTTP to
  Phoenix. Agents log through `log_event`, which writes the log line and an
  AGENT span with `session.id` = plan-item slug.
- Alternatives considered: `openinference-instrumentation` auto-instrumentors
  (only cover supported frameworks, not hand-written loops); one trace per
  plan item with cross-process context propagation (needs state files to
  carry span context between stateless agent runs — sessions give the same
  grouping for free).
- Consequences: three runtime dependencies; the log line stays the source of
  truth and tracing is best-effort (bounded delay when Phoenix is down).
  Prompts and documents leave the process unless the `OPENINFERENCE_HIDE_*`
  flags are set.
- First tests to write: span kinds and parent/child nesting; error status on
  exceptions; redaction; `log_event` line format and session id.

### ADR-KE-001: Port the harness to Claude Code natively
- **Context:** the role agents are written for Copilot. In the JD repo, Claude
  Code agents were vendored into a subfolder and never installed, while the docs
  said they ran.
- **Decision:** add `.claude/agents/<role>.md`, a `CLAUDE.md` that imports
  `AGENTS.md`, the `block-main-commit` hook in `.claude/settings.json`, and a
  single `scripts/verify.sh [fast|full]`. `.github/agents/` is kept unchanged.
- **Alternatives:** symlinking the Copilot files was rejected because the
  frontmatter is incompatible. A Claude-only harness was rejected because
  Copilot users still rely on it.
- **Consequences:** two sets of agent files must stay in sync, so a unit test
  (`tests/test_harness_port.py`) compares their Constraints sections and their
  handoff/log duty step.
- **Done only with proof:** a dispatch transcript for each role and every
  verify mode run on a clean checkout.
- **As built (`agent/harness-claude-code`):**
  - `scripts/verify.sh` re-runs itself in the one-shot `gates` compose service
    (`docker/gates.Dockerfile`, `network_mode: none` in `docker-compose.yml`).
  - CI's only step is `./scripts/verify.sh full` (`.github/workflows/ci.yml`),
    so nothing runs in CI that verify does not.
  - `verify.sh` fails unless `scripts/test.sh` output contains both a
    `Ran N tests` line with N > 0 and, as a whole line, the exact sentinel
    line from `tests/test_sentinel.py`:

    ```
    test_top_level_unit_suite_ran (tests.test_sentinel.TopLevelSuiteSentinelTest.test_top_level_unit_suite_ran) ... ok
    ```

    That module must stay
    top-level in `tests/`, and its module, class and method names must stay
    unchanged; renaming or moving any of them turns every verify run red.
  - `.gitattributes` forces LF on `*.sh`. The Windows checkout
    (`core.autocrlf=true`) had CRLF scripts, which fail in containers.
  - `scripts/hooks/block-main-commit.sh` used to print `permissionDecision:
    "allow"` for every non-blocked call. In Claude Code that auto-approves
    every Bash command and bypasses permission prompts. It now never prints
    `allow`. It prints a fixed deny, or it prints nothing so the call goes
    through the normal permission flow. The same script serves the Copilot developer
    agent, so it no longer auto-approves there either.
  - The hook is a simple fail-safe text rule, not a shell lexer: broad on
    main/master (deny `git` plus any history-writing verb), narrow off main
    (deny a single line that pushes to main/master or forces). It uses no awk.
    See the decision record below, which supersedes the round-3 precise
    off-main lexer.
  - Claude Code loads `.claude/agents/` only at session start, so the dispatch
    proof needed a fresh session (evidence:
    `docs/evidence/harness-claude-code/dispatch-*.md`).
- **Amended by ADR-KE-009 (accepted with the Q30 amendment, narrowed by F-A):**
  - `gates` keeps `network_mode: none` and still runs the fast path.
  - `verify.sh full` adds a host-side orchestration and a second one-shot
    service, `gates-it`, that sits on the internal `backend` network only. It
    reaches the model host only through the gateway's upstream forward.
- **Further consequences (harness-followups review, recorded 2026-10-18):**
  - **verify.sh needs a grep with PCRE (I2).** The sentinel check is
    `grep -Pq '^…\) \.\.\. ok\r?$' "$log"`. The gates image's GNU grep has
    `-P`, and so does Git Bash's. A grep without PCRE (BSD grep, or GNU built
    with `--disable-perl-regexp`) exits 2, `if !` treats that as no match, and
    verify **fails closed**. The FAIL message then blames the sentinel, not
    grep; grep's own stderr line just above it is the tell. It only matters
    outside the image (`KE_IN_GATES=1` exported on a host, or a verify test
    run directly on a host), neither of which is a documented workflow.
  - **On-main accepted bypasses are wider than Table M rows 14 and 15
    (security L24).** On main/master the hook is also silent for anything
    that hides the words from the text: a git alias verb (`git ci -m x`),
    variables, `eval`, and base64 or other encodings. It is also silent for
    `gh` (`gh pr merge`), as off main. The hook is a guard rail that denies
    most commits and pushes on main, not all; branch protection (Q18) is the
    control. AGENTS.md's "denies any commit/push" wording overclaims; that
    edit is the documenter's (L24 ask).

#### Decision: commit hook is a simple fail-safe text rule (2026-10-18)
The orchestrator ruled this in round 4. It also answers review N15, which
asked for the hook design to be recorded in this ADR.
- **Context:**
  - Three review rounds of a precise awk shell lexer each produced a
    fail-open regression:
    - B5: compact JSON with no jq.
    - B8: nested syntax.
    - H2: gawk doubles backslashes, which the mawk-only gates cannot see.
  - Each round also produced timing failures (L9, B10): the lexer was
    quadratic under mawk and went past the 10 s hook timeout.
  - Off-main push protection was a medium, non-blocking finding (security
    M1). Branch protection is the real control (Q18).
- **Decision:**
  - Extract the `command` field: jq if it works, else a single sed on the
    first `"command":"…"` value, else the raw input.
  - Normalise: turn JSON `\n` into newlines, delete CR (PS-0.4), then build
    up to two texts, each with quotes and backslashes deleted and
    lower-cased:
    - text (a): backslash-newline joined to nothing, as bash does for a real
      continuation (PS-0.5, security M5);
    - text (b): built only when the command contains a backslash-newline
      (security L21, so there is no second pass otherwise); each
      backslash-newline becomes a space, so a push split after a comment or
      an even run of backslashes is still one line (security M6).
  - The hook denies if either text matches the rules below.
  - On main/master: deny if the text contains the word `git` and any of
    commit, push, merge, cherry-pick, am, rebase or revert.
  - Off main: deny any line containing `git … push` followed on that same
    line by any of:
    - `main`/`master` as a word
    - `--force`/`--force-with-lease`
    - `--mirror`
    - `--all`
    - a single-dash short-flag cluster containing `f`
    - a `+` refspec
  - Use no awk, so there are no dialect differences. Cost is linear.
  - It never prints `allow`.
- **Consequences:**
  - Accepted false positives, which fail safe: a one-line command that
    mentions git, push and main, e.g. `git commit -m "fix git push to main
    docs"` or `echo "git push origin main"`. Heredoc commit bodies stay
    silent unless a single line says it. This reverses the earlier B6
    ruling.
  - Accepted false positives from the two texts, which also fail safe:
    - a backslash-newline inside single quotes (bash keeps it literal; the
      hook joins it);
    - a continuation glued with no space, e.g. `origin\` then newline then
      `main` (bash reads one word; text (b) splits it);
    - comment and even-backslash-run shapes, where bash does not continue
      the line but text (b) joins it.
  - Accepted bypasses off main:
    - anything that hides the words (variables, eval, aliases, encodings)
    - `gh` and `update-ref`
    - a push spread across lines without a continuation
    - after a comment or even backslash run ending in a backslash-newline, a
      continuation that splits a word of the push line (e.g. `pu\`+newline+
      `sh`, `ma\`+newline+`in`, `--for\`+newline+`ce`); the off-main form
      of Table M rows 14 and 15 (security L23)
    - `git`, CR, `push`: CR deletion (PS-0.4) glues the pair into one word,
      as bash reads it
  - Accepted bypasses on main: Table M rows 14 and 15, where after a comment
    or even backslash run a continuation splits the `git` or `commit` word.
    These shapes are contrived; branch protection (Q18) is the control. Also
    anything that hides the words, and `gh` (security L24; see "Further
    consequences" above).
  - Cost: host timing for 5 MB-plus commands (Git Bash, no jq) is 4.9 s with
    one text and 6.8 s with two, under the 10 s hook timeout but with low
    headroom when a backslash-newline is present
    (`docs/evidence/harness-followups/hook-timing-host-r4.txt`).
- **Alternatives rejected:**
  - Keep extending the lexer: each round added fail-open gaps.
  - A Python or shlex hook: it needs a runtime on the host, and the host has
    only Git Bash.
  - Drop the off-main rule: it would lose cheap coverage of the most likely
    accident.

### ADR-KE-002: Storage split
- **Decision:**
  - Neo4j holds the graph and the vector indexes (no pgvector, no Chroma).
  - PostgreSQL holds records, revisions, snapshots, the policy book, the review
    queue and the audit chain.
  - Valkey is the job queue only.
  - Blobs live on a content-addressed volume.
- **Context:** this follows the JD repo's ADR-002.
- **Consequences:**
  - There are two migration systems: Alembic and versioned Cypher files.
  - A consistency check compares Neo4j `built_from` ids with PostgreSQL
    revision ids.
  - Writes are ordered PostgreSQL first, then Neo4j, using an outbox table, so
    the knowledge plane never references a revision that does not exist.

### ADR-KE-003: Offline inference behind an egress allowlist
- **Decision:**
  - Use one OpenAI-compatible client with a separate config for each pass.
  - The allowlist is checked at startup and on every call.
  - CI installs a socket guard that fails any outbound connection outside the
    compose network.
- **Consequences:** moving the model host off the trusted segment is a
  compliance decision recorded as an ADR amendment, not a config edit.
- **Made concrete by:**
  - ADR-KE-010: the guarded httpx transport and the startup checks.
  - ADR-KE-011: the network layer, where `gateway` is the only way out.
  - ADR-KE-009: the internal `backend` network that `gates-it` sits on. The
    CI socket guard named above was dropped on 2026-10-19 (F-A drift fix):
    the internal network is the guard, and a runtime test proves it.
- **Amended by Q30 (human, 2026-10-18), narrowed by F-A, for integration
  tests only:** model-calling tests may call the configured model host, through
  the gateway's upstream forward and the DR30 allowlist, the app's own path.
  `gates-it` has no other route out, because `backend` is internal. The app's allowlist and the network layer of ADR-KE-011 are
  unchanged.

### ADR-KE-004: Domain packs and institution profiles
- **Decision:**
  - A pack is versioned YAML (entity types, relations, sections, extraction
    profiles, prompts, validation rules) plus optional Python implementing
    engine protocols.
  - A profile is pure data.
  - Every derived object stores the pack version and the profile version.
- **Alternatives:** a plugin entry-point system was rejected as more machinery
  than two packs need.
- **First tests:** a toy pack loads without any engine change, and the engine
  contains no SFU literals.

### ADR-KE-005: Deterministic policy evaluation
- **Decision:** rules are typed pydantic definitions (decision table, threshold,
  routing) evaluated by pure functions.
- **Enforcement:** the `engine.policy.evaluate` package is import-checked so it
  cannot reach any LLM client.
- **Rule lifecycle:** the LLM's only route into the policy book is creating a
  `proposed` rule revision.

### ADR-KE-006: Frontend stack
- **Decision:** server-rendered FastAPI + Jinja + htmx for every view, with one
  Cytoscape.js island for the graph explorer. All assets are vendored and
  checksummed in the offline bundle.
- **Trade-off:**
  - Server rendering reuses the JD repo's working templates and keeps one
    language, one test stack and one authorization path. Every view is
    readable without JavaScript, which suits revision diffs and audit views.
  - What it gives up is a rich client-side graph and diff interactivity.
- **Alternative:** React + TypeScript + Cytoscape.js would give a better graph
  explorer, but adds a Node build chain, a second test stack, an API-only
  authorization surface and a larger offline bundle.
- **Revisit when:** the graph explorer needs more than about 2,000 nodes on
  screen, or a collaborative diff editor is requested.

### ADR-KE-007: Revision history for corpus and policy
- **Context:** the user asked for revision UX and history for both corpus and
  policy. The JD repo gave a changed file a new row with no current flag (it
  double-counted), had no stale detection, and kept rulebook history only in git.
- **Decision:**
  - Append-only revision tables for sources, records, rules and book versions.
  - "Current" is a view, never an updated pointer.
  - Immutable corpus snapshots and book versions are the only things that
    baselines, metrics and outputs reference.
  - The database role is limited to INSERT and SELECT on revision tables.
  - Every revision write is an audit-chain entry.
  - Diffs are typed models computed server-side.
  - Restore and revert create new revisions through review; nothing rewinds.
  - Erasure is done by crypto-shredding per source (A11).
- **Alternatives considered:**
  - PostgreSQL temporal or system-versioned tables: there is no native support
    in PG 16, and extensions complicate the offline bundle.
  - Event sourcing with projections: stronger replay, but it is more machinery
    and the audit chain already gives the ordered event record.
  - Git-backed policy YAML: this is the JD repo's approach. Rejected because
    history is invisible to the UI and cannot carry ratification metadata or
    effect diffs.
- **Consequences:**
  - Storage grows with every revision. Revision content is stored in
    content-addressed blobs, so identical content is stored once.
  - "Current" views need indexes on `(record_id, revision_no DESC)`.
  - Freshness is one predicate shared by the funnel, the CLI and the UI.
- **First tests to write:**
  - `test_source_revision_append_only`
  - `test_unchanged_reingest_no_revision`
  - `test_entered_value_survives_reparse`
  - `test_snapshot_compare_buckets_sum`
  - `test_policy_versions_immutable`
  - `test_policy_diff_typed`
  - `test_revert_is_a_new_changeset`
  - `test_citation_stale_on_policy_doc_revision`
- **Plan placement:** no new plan item is needed.
  - The source and record revision model lands in `ingest-ledger` and
    `data-plane`.
  - `built_from` stamps land in `knowledge-plane`.
  - Policy versions and the changeset lifecycle land in `policy-book`.
  - Output provenance lands in `agent-workflow`.
  - The six history views of §4.3 land in `frontend`, directly after the funnel.

### ADR-KE-008: Authentication, authorization and audit
- **Decision:**
  - SSO goes behind a `IdentityProvider` protocol (CAS first, then SAML and
    OIDC), with a dev provider for CI.
  - Sessions are server-side and revocable.
  - The actor comes only from the session.
  - CSRF protection applies to cookie-authenticated writes.
  - An authorization-matrix test walks the routing table.
  - The audit log is a hash chain maintained by an insert trigger, checked with
    `ke audit verify`.
- **Context:** this follows the JD repo's ADR-008, generalized.

### ADR-KE-009: Gates reach real stores over compose networks, with no Docker socket (answers Q19, amends ADR-KE-001)
- **Status:** accepted with a human amendment (Q30, 2026-10-18), narrowed by
  ruling F-A (2026-10-18): automated tests need to reach only the LLM on
  `aria-gb10-2`, not the internet. The mechanism is option (a) below,
  unchanged: `gates-it` on the `internal: true` `backend` network only, no
  separate external network, no Docker socket, no testcontainers.
  Model-calling integration tests reach the model host only through the
  gateway's upstream forward. This amends DR31 ("CI never calls a model") for
  integration tests only; the analyst edits DR31 and PS-2.4 to PS-2.7.
- **Context:**
  - `gates` runs with `network_mode: none` and has no Docker socket.
  - Yet integration needs real PostgreSQL, Neo4j and Valkey (DR31).
  - The live smoke (PS-2.8) needs to launch the stack, and the offline check
    (PS-3.2) needs a daemon that has no images and no egress.
  - The rule: everything runs in Docker, and CI's only step is
    `verify.sh full`.
  - Q30 (human): model-calling integration tests should run against the real
    model host (`aria-gb10-2`, Q7) when it is reachable. F-A (human) narrows
    this: the model host only, not the internet.
- **Options:**
  - **(a) Compose services, one-shot `gates-it` on the stack network.**
    - The stores are ordinary compose services on `backend` (`internal: true`).
    - A second one-shot service, `gates-it` (same image, same YAML anchor),
      joins `backend`.
    - The host half of `verify.sh` starts the stack before running `gates-it`
      and tears it down afterwards.
    - No socket and no testcontainers.
  - **(b) Mount `/var/run/docker.sock` into gates** for testcontainers.
  - **(c) A separate integration profile whose gates container sits on an
    ordinary bridge network**, with the stores started by compose or
    testcontainers.
- **Security trade-off of the socket (b):**
  - The Docker API socket is root-equivalent on the host. Any code running in
    gates could start a privileged container with the host's `/` mounted.
    That includes every test, every imported dependency, and a test file
    added by a hostile PR.
  - It also lets that code read other projects' volumes and secrets. On Docker
    Desktop it reaches the VM, which mounts the host drives.
  - Testcontainers also pulls its Ryuk image at test time.
  - **Rejected.** Q30 and F-A did not change this.
- **(c) rejected (F-A).** An ordinary bridge network would give tests a route
  to the internet, which F-A rules unnecessary: only the model host is
  needed, and the gateway already forwards to it.
- **Decision: (a).**
  - **Networks:** `gates-it` joins `backend` only (to reach the stores, `api`
    and `gateway`). There is no `gates-it` network. `backend` stays
    `internal: true`, so neither the app containers nor `gates-it` have a
    route out except the gateway's single upstream forward (DR30,
    ADR-KE-011).
  - **Unit `gates`** keeps `network_mode: none`; `verify.sh fast` is
    unchanged.
  - **Model-calling integration tests** go through `ModelClient` → `gateway`
    (model port on `backend`) → upstream forward over `edge` →
    `KE_MODEL_UPSTREAM`, the app's own path, so the DR30 egress allowlist
    applies to them. `config/verify.env` no longer overrides
    `KE_MODEL_UPSTREAM` (the earlier `.invalid` upstream is dropped), so the
    configured host is used. One reachability probe per run
    (`GET {compose.base_url}/models`, `readiness.timeout_s`) decides: run
    them, or skip them with `model host unreachable: <KE_MODEL_UPSTREAM>
    (<reason>)`, using the `/readyz` reason vocabulary. No other test may
    skip on network grounds.
  - **`verify.sh full`, host half:**
    1. It sets a trap that runs `teardown.sh --volumes`.
    2. It runs `build.sh`, then `launch.sh` for an isolated project,
       `ke-verify-<suffix>`. That project:
       - uses `--env-file .env.example`, overlaid by `config/verify.env`;
       - uses `docker-compose.verify.yml`, which resets every `ports:`, so
         nothing is published.
    3. It runs `compose run gates-it scripts/verify.sh full`. Inside, that does
       `lint.sh` and `test.sh full` (store integration always; model-calling
       tests when the probe succeeds).
    4. It runs `smoke.sh`, then `offline_check.sh`.
  - The gate commands stay only in `lint.sh`, `test.sh`, `smoke.sh` and
    `offline_check.sh`. `verify.sh` calls scripts and `compose run`, nothing
    else.
  - The gates anchor sets `UV_OFFLINE=1`, so a run never depends on fetching
    a dependency (and `gates-it` has no route to an index anyway).
- **Clean daemon:**
  - `offline_check.sh` starts the official Docker `dind` image (privileged,
    with a fresh anonymous `/var/lib/docker`) on an internal network,
    `offline`.
  - It drives that daemon from `offline-client`, which uses the gates image.
  - It runs **in every `verify.sh full`, locally and in CI** (F5 ruling;
    revisit if `full` exceeds about 15 minutes locally). The offline proof of
    the *deployed* product (`ci/offline`, `ci/deployable-offline`) is
    unchanged by Q30 and F-A.
  - Locally this needs a daemon that permits privileged containers. Docker
    Desktop and Linux Docker Engine both do. Rootless or Podman setups report
    a blocker rather than skipping.
- **Consequences:**
  - **Local `verify.sh full` covers more than CI.** Where `aria-gb10-2` is
    reachable, the model-calling tests run; on GitHub runners they always
    skip. CLAUDE.md records this in a new "What verify.sh runs that CI
    cannot" row (orchestrator or documenter edit). "What CI runs that
    verify.sh does not: Nothing" stays true. A green CI therefore does not
    prove the model-calling tests passed; the evidence file shows whether
    they ran or skipped.
  - **The checkout cannot leave the machine through tests (F-A).** `gates-it`
    has no route to the internet: `backend` is internal, and the gateway's
    forward goes to one configured upstream, the model host, never to an
    arbitrary address. The only off-machine peer a test can reach is the
    trusted model host the app already uses, and only through the gateway.
    Unit `gates` stays without a network.
  - (Amended 2026-10-19, F-A drift fix.) There is no test socket guard. The
    earlier `tests/integration` fixture, which patched `socket.socket.connect`,
    could not see libpq (psycopg connects in C). Since F-A, the internal
    `backend` network is the boundary, and it refuses every raw connection
    out. A runtime integration test proves it (§2.2,
    `test_gates_it_has_no_route_out`).
  - (Amended, platform-stack rework 1, review B1 and security M-2.)
    `internal: true` alone left the Docker host reachable through the
    `backend` bridge gateway, and the runtime test could not tell "no route"
    from "nothing answered". `backend` now also sets
    `com.docker.network.bridge.gateway_mode_ipv4: isolated` (Docker Engine
    ≥ 28, ADR-KE-011), and the runtime test requires a fast no-route errno,
    rather than a timeout, both for TEST-NET-1 and for the bridge gateway.
  - (Amended, platform-stack rework 2, review R1-B1 option (ii), security
    M-4.) The rework-1 fixed `backend` subnet is removed, so no address
    literal exists and parallel stacks and verify runs from this compose
    file work again (Docker refused a second project with "Pool overlaps").
    The in-container bridge-gateway probe is dropped: a probe can show only
    that one address did not answer, it missed the host's real bridge
    address when isolation was off (M-4), and on Docker Desktop it gives
    the same result either way. The runtime proof of host isolation is now
    the host half of `smoke.sh` asserting that `docker network inspect
    <project>_backend` shows `gateway_mode_ipv4=isolated` and `Internal`
    true (§2.2). The TEST-NET-1 probe keeps the fast no-route errno
    requirement for outside hosts.
    - *Alternative rejected:* a per-run subnet variable (R1-B1 option (i))
      adds config and verify plumbing and still proves isolation only by
      probing addresses.
  - (Amended, rework 2, security L-7.) `lint.sh` passes `.ps1` paths to
    PSScriptAnalyzer through an environment variable read by a fixed
    command, never inside generated PowerShell source (§2.2 Lint).
  - (Amended, rework 1, review B5 and B6.) `scripts/lint.sh` (shellcheck and
    PSScriptAnalyzer, pinned in the gates image) runs in the container half
    of both modes. The host half of `verify.sh` is covered by a fast
    fake-docker test of its stage order, failure exits, teardown on every
    exit path, the overlay and the per-run project name. A failed teardown
    prints a warning (N7).
  - Integration tests cannot stop containers, so store-down cases are made in
    process, and real stop and start happens in the host-side smoke.
  - DNS on internal networks (`backend`, `offline`) may still forward queries
    outward through Docker's embedded resolver. This is residual (it applies
    to `gates-it` too), and flagged to security.
  - DinD is privileged too. Control of its API is effectively root on the
    host. Accepted because:
    - the only code with that control is our shell scripts, at the same trust
      level as the host half of `verify.sh`, which already drives the host
      daemon;
    - no test or third-party Python runs there;
    - its daemon has no route out.
  - `verify.sh full` becomes slower and needs more disk. The CI
    `timeout-minutes` is the measured duration plus 50% (F6 ruling, PS-3.4).
    An unreachable model host costs at most one probe timeout.
- **First tests** (names aligned to PS-2.7 on 2026-10-19):
  - `test_gates_it_internal_only_and_no_socket` (fast);
  - `test_model_tests_skip_with_named_reason` (fast);
  - `test_gates_it_has_no_route_out` (integration) and
    `test_egress_allowlist_holds_with_network_access` (integration). These
    replace the in-process socket-guard test (PS-2.7);
  - rework 1: `test_backend_network_isolated_from_host`,
    `test_lint_sh_runs_shellcheck_and_psscriptanalyzer` and the fake-docker
    test of the `verify.sh` host half (all fast);
  - rework 2: the smoke host-half isolation check against a fake `docker
    network inspect` (empty, `nat`, error refused; `isolated` passes), and
    the `lint.sh` fixed-command and U+2019 filename tests (all fast);
  - `test_no_docker_socket_mounted` (fast);
  - `test_verify_sh_has_no_inlined_commands` (existing, stays green).

### ADR-KE-010: Typed configuration and the egress guard (platform-config)
- **Context:**
  - PS-1.x: one typed config, no hardcoded hosts, ports or models, and
    egress that fails closed (DR30).
  - Startup refusals (DR39) and traced startup.
  - Coverage ≥ 80 % and `mypy --strict`.
- **Decision:**
  - **Settings:** `engine.config.Settings` on `pydantic-settings`, with
    sources in the order init → environment → `config/defaults.yaml`.
    - Environment variables use the `KE_` prefix with `__` nesting. `KE_`
      names only, with no unprefixed aliases (F2 ruling).
    - Standard tool variables (`PHOENIX_COLLECTOR_ENDPOINT`,
      `HARNESS_TRACING`, `OPENINFERENCE_HIDE_*`) keep their own names.
    - Secrets come from the environment only, with no default (F3 ruling).
      `.env.example` placeholders are `changeme-<key>`, and any secret
      starting with `changeme` is refused outside `dev` (PS-1.9,
      placeholder-secret ruling). `.env.example` is not shipped in an image.
    - The model host (`aria-gb10-2` for this deployment, Q7) is configuration
      only: `KE_MODEL_UPSTREAM` and the per-pass base URLs. No code names it,
      and the hardcoded scan enforces that.
    - Errors name the key, never the value.
  - **Egress:** an httpx `GuardedTransport` runs before any socket is opened,
    with `trust_env=False`. The startup check covers every pass `base_url`
    and `model_upstream`.
  - **Startup refusals:** run in `engine.startup`. OTLP export is attached
    only after the collector is shown to be local.
  - **Tracing (amended, rework 1, 2026-10-19: B1, B7b, L6):**
    - `telemetry.tracing` defaults to `off`; `.env.example` turns `otlp` on
      for the local Phoenix.
    - The exporter is chosen from `Settings` only, by the pure
      `choose_exporter`: `otlp` → OTLP to the checked local collector,
      `console` → `ConsoleSpanExporter`, `off` → none. The engine never uses
      `harness_telemetry.setup_tracing` or its env reading.
    - A tracer provider that is already installed is refused
      (`StartupRefused("telemetry.tracing", …)`) unless every exporter on it
      is positively identified as local.
    - `configure_tracing` runs only after `check()` passes, and applies the
      hide flags before it installs the exporter.
    - Every `ModelClient` call method is wrapped in an `llm_span` (N12).
  - **Compose (amended, rework 1: B7a, M2):** Phoenix is published as
    `127.0.0.1:${KE_PHOENIX_PORT:-47101}:${PHOENIX_PORT:-6006}`, on loopback
    only. It uses `:-` because verify and CI run compose without a `.env`. A
    drift test ties both defaults to `.env.example` and `defaults.yaml`. The
    scanner reads `${VAR:-default}` defaults as declared values in compose
    files only.
  - **Hardcoded scan:** a pure scanner in `tests/`. Its single exemption is
    `harness_telemetry.tracing.DEFAULT_COLLECTOR`, which is pinned to
    `.env.example` by a drift test.
  - **Quality gates:** coverage (branch) and mypy (strict) are configured in
    `pyproject.toml` over `engine` and `harness_telemetry`, and run by
    `test.sh`. `scripts/*.py` and tests are out of scope.
- **New dependencies:**
  - runtime: `pydantic-settings` (brings `pydantic`), `PyYAML`, `httpx`;
  - dev: `coverage`, `mypy`, `types-PyYAML`.
- **Alternatives considered:**
  - Hand-rolled dataclasses plus environment parsing: this re-implements
    pydantic's validation.
  - Dynaconf: more machinery and weaker typing.
  - Unprefixed variable names (`ENV`, `EGRESS_ALLOWLIST`, `MODEL_BASE_URL`, as
    the requirements spelled them): rejected because of collision risk. F2
    ruled no aliases either; the requirements now use the `KE_` names.
  - A process-wide socket audit hook: it misses libpq and cannot be removed in
    tests.
  - Making the harness read its default from `.env.example`: this couples the
    template to the working directory.
  - (Rework 1) `${KE_PHOENIX_PORT:?set in .env}`: this breaks `verify.sh` and
    CI, which have no `.env`. Defaulting tracing to `otlp`: a fresh checkout
    would try to export before anyone has chosen to. Replacing an installed
    provider: OTel allows the global provider to be set only once.
    `setup_tracing(…, exporter=…)`: it returns an existing provider
    unchecked.
- **Consequences:**
  - Defaults live in exactly two committed files: `defaults.yaml` (app keys)
    and `.env.example` (compose and deployment keys).
  - `config/verify.env` is a third, and small, allowed location (F4 ruling:
    an accepted literal exemption under PS-1.2). It does not override
    `KE_MODEL_UPSTREAM` (Q30).
  - The placeholder check needs no file at runtime; a fast test keeps
    `.env.example`'s secret values on the `changeme-` prefix.
  - Alternative rejected by the orchestrator's ruling: copying `.env.example`
    into the app image and comparing values, which ships a dev file in a
    production image.
  - Default `env=prod` with `auth.enabled=true` refuses to start until
    auth-audit exists. `.env.example` therefore ships `KE_ENV=dev` with auth
    off, which logs a warning.
  - The exceptions are ruled and recorded in PS-1.1/PS-1.2: secrets have no
    YAML default (F3), and the requirement names are `KE_` variables (F2).
  - (Rework 1) The installed-provider check reads private OTel SDK
    attributes. It fails closed, and a fast test pins every accepted shape.
  - (Rework 1) Startup runs `check()` twice: once untraced as the pre-flight,
    and once inside the traced block. It is pure and cheap.
  - (Rework 1) The spans of a refused startup are recorded but not exported
    (no exporter exists yet). Tests see them through the in-memory provider.
- **First tests:**
  - `test_config_defaults_and_env_override`;
  - `test_config_ignores_unprefixed_names`;
  - `test_egress_guard_runtime`;
  - `test_startup_refuses_unsafe`.
  - Rework 1:
    - `choose_exporter` is pure and needs no global provider (this avoids
      B2's vacuous pass). With `console` and an external
      `PHOENIX_COLLECTOR_ENDPOINT` while `HARNESS_TRACING` is unset or
      `otlp`, the result is a `ConsoleSpanExporter` and never OTLP (the H1
      repro).
    - With `off`, it returns none.
    - With `otlp` and a non-local collector, it returns none.
    - An installed provider with a non-local OTLP exporter, or an unknown
      exporter, is refused.
    - `configure_tracing` is not called when `check()` refuses (L6).
    - `test_compose_phoenix_defaults_match_config`, and a test that the
      compose publish is bound to `127.0.0.1`.
    - The `ModelClient` call emits an LLM span (N12).
- **Amendment, 2026-10-19: security M5 (installed-provider identity).**
  Status: proposed. Recommended to land in platform-stack, as its first unit.
  - **Context:**
    - `_verify_installed` admits any SDK provider whose exporters *look*
      local. Security M5 found three shapes that pass and still export
      off-host: explicit `session.proxies`, a mounted rerouting adapter, and a
      rewritten `_endpoint`. Hostile variants (I3) also pass.
    - The obvious fix, accepting only a provider the engine built, collides
      with `tests/support.py`. At import, it installs a global SDK provider
      with an `InMemorySpanExporter` through `harness_telemetry.setup_tracing`,
      and OTel allows the global provider to be set only once.
  - **Options:**
    - **(a) A test-only registration API**, `engine.telemetry.trust(provider)`.
      Rejected. It ships a bypass in production code: any in-process code can
      mark any provider as trusted, including custom processors (E1) and every
      M5 shape. Gating it on an env var makes it worse.
    - **(b) A marker on the tests' provider through a supported hook**, for
      example a resource attribute `ke.provider.owner=engine`. Rejected. A
      marker is data, so any library can copy or forge it. It also puts a
      trust flag into exported trace data.
    - **(c) An engine-owned provider used by the tests. Chosen.**
  - **Decision (c):**
    - A new
      `engine.telemetry.build_provider(exporter: SpanExporter, *, project_name: str = PROJECT_NAME) -> TracerProvider`
      is the only constructor:
      - it sets the resource (`service.name` and the OpenInference project
        name);
      - it adds `SimpleSpanProcessor` for console and in-memory exporters and
        `BatchSpanProcessor` otherwise;
      - it records the provider in a module-private `weakref.WeakSet`.
    - `configure_tracing` uses it for `choose_exporter(settings)`.
    - `verify_provider` accepts a `ProxyTracerProvider`, or a provider that
      *is* (identity) in that set. (Tightened by the rework-1 amendment
      below: exactly `type(p) is ProxyTracerProvider`, identity by `is`, and
      a post-install check.) It refuses everything else with
      `StartupRefused("telemetry.tracing", …)`.
    - `_verify_installed`, `_exporters_of`, `_sessions_of` and
      `_ignores_proxy_env` are deleted. The check no longer reads private SDK
      attributes, which removes the rework-1 consequence about them.
    - `tests/support.py` builds its provider with
      `engine.telemetry.build_provider(EXPORTER, project_name="harness-tests")`
      and installs it with `trace.set_tracer_provider`, instead of calling
      `setup_tracing`. `harness_telemetry.setup_tracing` is unchanged:
      `log_event` and the template still use it, and it returns the
      already-installed provider, so `test_tracing`'s project-name assertion
      holds.
  - **Consequences:**
    - Any foreign SDK provider is refused, whatever its exporters, including
      every M5 and I3 shape.
    - Code that deliberately calls `build_provider` with its own exporter is
      accepted. That is in-process code inside the trust boundary (I3); a
      library cannot reach this state by accident.
    - `tests/support.py`, a harness template file, now imports `engine`.
      That is acceptable in this product repo. The template upstream is not
      changed.
    - Tests that pin today's accepted foreign shapes flip from accepted to
      refused. These are the console, in-memory and local-OTLP cases of
      `InstalledProviderTest`, and
      `test_local_otlp_that_ignores_proxy_env_is_accepted`. The
      tracing-guard control `test_control_spans_do_reach_an_accepted_provider`
      must then build its provider with `build_provider`. This tightens the
      tests, it does not weaken them, but the tester needs an orchestrator
      ruling to edit tests that are green, citing this amendment.
  - **First failing test:** `test_provider_not_built_by_engine_is_refused`
    in `tests/test_engine_tracing_guard.py`. It uses one subtest per shape,
    each a provider built *outside* the engine:
    - local OTLP with `trust_env=False` and `session.proxies` set;
    - the same with a mounted rerouting `HTTPAdapter`;
    - an `_endpoint` rewritten to localhost;
    - a plain in-memory exporter.

    `startup()` must refuse naming `telemetry.tracing`, and the provider's
    exporter must get zero spans. It is RED today because all four are
    accepted. Its control, `test_engine_built_provider_is_accepted`, uses
    `build_provider(InMemorySpanExporter())`, is accepted, and receives the
    startup spans.
- **Amendment, 2026-10-19: M5 forgery gaps (platform-stack rework 1,
  security M-1 and L-2).** Status: accepted for 2a.
  - **Context:** the M5 check had two gaps.
    - M-1: `verify_provider` returned early on
      `isinstance(provider, ProxyTracerProvider)`. A foreign *subclass* of
      the proxy, whose `get_tracer` hands out its own SDK tracers, passed as
      "nothing installed". The later `set_tracer_provider(build_provider(…))`
      was then ignored by OTel (the global can be set once), yet
      `configure_tracing` returned `True`, and every engine span went to the
      foreign sink.
    - L-2: `provider in _ENGINE_PROVIDERS` compares with `__eq__`/`__hash__`,
      so a decoy that overrides both to match a live engine provider passed.
  - **Decision:**
    - "Nothing installed" is exactly `type(provider) is ProxyTracerProvider`.
      A subclass is a foreign provider and is refused.
    - Registry membership is identity:
      `any(p is provider for p in _ENGINE_PROVIDERS)`. `in` is not used.
    - **Post-install check.** After `trace.set_tracer_provider(built)`,
      `configure_tracing` asserts `trace.get_tracer_provider() is built`, and
      otherwise raises `StartupRefused("telemetry.tracing", …)`. This catches
      any path where the install was silently ignored, including ones not yet
      known.
    - Everything else in the M5 amendment stands.
  - **Alternatives:** keeping `isinstance` and also inspecting `get_tracer`
    on subclasses re-creates the shape inspection that M5 deleted. The
    post-install check alone would catch M-1 but not a decoy accepted
    *before* any install (L-2); both changes are kept.
  - **Consequences:** a provider is accepted only if it is the stock unset
    proxy, or an object the engine itself built. Forging either one now
    needs in-process code that writes to `_ENGINE_PROVIDERS` or replaces OTel
    internals. That stays inside the accepted I3 trust boundary.
  - **First tests:** add two subtests to
    `test_provider_not_built_by_engine_is_refused`: a `ProxyTracerProvider`
    subclass that routes to a foreign SDK provider, and a decoy whose
    `__eq__`/`__hash__` match a live engine-built provider. Each is refused
    naming `telemetry.tracing`, and its sink gets zero spans. Add
    `test_configure_tracing_refuses_when_install_is_ignored`: patch
    `trace.set_tracer_provider` to a no-op (the M-1 effect), so
    `configure_tracing` raises `StartupRefused` instead of returning `True`.
    The control, `test_engine_built_provider_is_accepted`, stays green.

### ADR-KE-011: Stack topology, gateway and job queue (platform-stack)
- **Context:**
  - PS-2.x and PS-3.3: app containers may reach nothing outside the stack
    except the allowlisted model host.
  - Containers attached only to an `internal` network cannot publish host
    ports.
- **Decision:**
  - **Networks:**
    - Every stack service sits only on `backend` (`internal: true`), except
      `gateway`, which sits on both `backend` and `edge`. The verify-only
      `gates-it` service also sits on `backend` only (ADR-KE-009, Q30/F-A), so
      this layer is the same for tests as for the app.
    - The gateway is an nginx image with baked-in templates. It:
      - publishes `KE_API_PORT` and `KE_PHOENIX_PORT`, on `KE_BIND_ADDRESS`
        (amended below);
      - reverse-proxies `api` and `phoenix`;
      - forwards one TCP listen port to `KE_MODEL_UPSTREAM`.
    - The app's allowlist covers the host it dials (`gateway`) and the
      upstream host, and both are checked at startup.
  - **Job queue:** RQ on Valkey (the `rq` and `redis` client libraries).
  - **Store drivers:** `psycopg` (v3), `neo4j`, and `redis` (compatible with
    Valkey).
  - **API:** `fastapi` and `uvicorn`.
  - **Restart policy:** `unless-stopped` on every long-running service.
- **Alternatives considered:**
  - **Gateway:**
    - Publishing `api` and `phoenix` directly from an `edge` network gives both
      a route out, which fails PS-3.3.
    - A forward HTTP proxy (squid or tinyproxy) for egress, plus a separate
      ingress proxy, means two services.
    - iptables rules are host-specific and not portable to Docker Desktop.
  - **Queue:**
    - A hand-rolled queue on Valkey Streams: its retries, failed-job registry
      and heartbeats would all be ours to build.
    - Celery: heavy.
    - arq: async-only and in maintenance mode.
    - Dramatiq: less job introspection.
    - RQ's heartbeats and failed registry also feed the DR41 "healthy silence
      versus hung" runbook.
- **Consequences:**
  - The gateway is a single choke point and must start with any upstream
    absent.
  - Phoenix becomes reachable only through the gateway, so the harness runs
    `docker compose up -d phoenix gateway` or `launch.sh`.
    `harness_telemetry`'s default becomes `http://localhost:47101`
    (Q2 ruling), and the README changes with it.
  - The 4317 gRPC port is no longer published.
  - Compose ≥ 2.24 is a host prerequisite.
  - `/readyz` is public; auth-audit's authorization matrix must classify it.
    Its reasons use a fixed vocabulary, so it leaks no credentials.
- **Amendment, 2026-10-19: ports and the bind address** (orchestrator port
  ruling, from platform-config B7a; details in §2.4).
  - **Context:** `${KE_…_PORT:?set in .env}` breaks `verify.sh` and CI,
    which have no `.env`. None of the published services has auth until
    auth-audit.
  - **Decision:**
    - Every published port is
      `${KE_BIND_ADDRESS:-127.0.0.1}:${KE_<X>_PORT:-<default in 47100–47199>}:<container port>`,
      and compose defaults are drift-tested against `.env.example`.
      (Rework 1, N1: written in compose's long syntax, `host_ip` /
      `published` / `target`, with the same three variables; §2.4.)
    - A `KE_BIND_ADDRESS` that is not loopback is refused outside `dev`,
      until auth-audit, in three places (PS-2.14):
      - engine startup refusal 6;
      - the gateway's entrypoint check, which is the check that actually
        prevents the publish, because the gateway runs without `api`;
      - `launch.sh`/`.ps1`, before any container starts (rework 1: on the
        values `docker compose config` resolves).
  - **Alternatives:**
    - `:?`: rejected, as above.
    - Literal `127.0.0.1` with no variable: LAN exposure would mean editing
      the compose file, which no check sees.
    - The engine check alone: Phoenix behind a gateway that started without
      `api` would still be published to the LAN.
    - `depends_on: api` on the gateway: this contradicts "the gateway starts
      with any upstream absent".
  - **Consequences:**
    - A fresh checkout publishes on loopback only.
    - LAN exposure needs both an `.env` edit and `KE_ENV=dev` until
      auth-audit, which then narrows the rule to "auth disabled".
    - Hand-edited compose files bypass the rule (accepted residual).
- **Amendment, 2026-10-19: platform-stack rework 1** (review B2, B3, N1,
  N3; security M-2, M-3, L-1, L-3; details in §2.1 and §2.4).
  - **Context:** review and security found that the Docker host was
    reachable from `backend`, that the gateway forwarded to any upstream and
    rendered it into nginx config unchecked, that launch read the env file
    differently from compose and fell back to `.env.example`'s `KE_ENV=dev`,
    and that `worker` never ran `startup()`.
  - **Decision:**
    - **Ports:** compose long syntax (`host_ip`, `published`, `target`). The
      gateway listen ports come from `KE_GATEWAY_{API,PHOENIX,MODEL}_LISTEN`,
      and the API's from `KE_API_LISTEN`, passed in as
      `KE_API__LISTEN_PORT`. `target` is always a variable.
    - **Host isolation:** `backend` sets
      `com.docker.network.bridge.gateway_mode_ipv4: isolated`. Docker Engine
      ≥ 28 becomes a host prerequisite (quickstart), and launch checks it,
      because older engines ignore the option silently.
    - **Gateway enforces the allowlist (DR30 extended to the gateway):**
      `docker/gateway/11-ke-upstream-check.sh` runs before the envsubst step
      and requires `KE_MODEL_UPSTREAM` to be empty, or a strict `host:port`
      whose host is on `KE_EGRESS_ALLOWLIST` (exact, case-folded). It also
      requires every listen port the templates substitute to be an integer
      from 1 to 65535. Otherwise it exits non-zero and nginx never starts.
      DR30 now holds in three layers: the engine (startup check and
      `GuardedTransport`), the gateway entrypoint, and the network topology.
    - **Launch reads compose's resolved values** (`config --format json
      gateway`), with no `.env.example` fallback. A missing or empty
      `KE_ENV` is not dev.
    - **Worker placeholder** runs `startup()`, then idles, as
      `python -m engine.worker`, until 2b.
  - **Alternatives:**
    - A host firewall rule instead of `isolated`: host-specific, and not
      portable to Docker Desktop (the same reason iptables was rejected
      above).
    - An explicit `ipam` subnet so tests know the gateway address: this adds
      a network literal to config, and the test can derive the address.
      (Rework 1 adopted it anyway; rework 2 removed it, see below.)
    - Validating the upstream only in the engine: third-party images on
      `backend` never run the engine check.
    - Escaping the value for nginx instead of validating it: the grammar is
      tiny, and refusing is simpler and fails closed.
    - Parsing the env file in the launch scripts (the 2a approach): it can
      never match compose's dotenv grammar exactly (L-1).
  - **Consequences:**
    - Hosts on Docker Engine < 28 cannot launch the stack. The CI runner and
      the Windows proof host must meet this, so the Windows run (Q31/Q34) is
      repeated after this round.
    - A host service such as a local Ollama is no longer reachable from
      `backend`. The model host is reached only through
      `KE_MODEL_UPSTREAM` on the gateway, as the design always intended.
    - Changing the allowlist or the upstream needs a gateway restart, the
      same as any other config change.
    - The bash launch script parses compose's JSON line by line. That is
      deliberately narrow and fails closed, and a smoke case against real
      compose checks that the fixture shape is right.
- **First tests:**
  - `test_compose_services_have_restart_policy`;
  - `test_published_ports_use_bind_address` (long syntax, rework 1);
  - `test_startup_refuses_non_loopback_bind_address`;
  - `test_only_gateway_on_edge_network`;
  - `test_worker_consumes_noop_job`.
  - Rework 1: `test_backend_network_isolated_from_host`,
    `test_gateway_upstream_check_refuses_off_allowlist`, the gateway
    template-variable drift test, the launch fake-docker cases on resolved
    config (§2.4 Scripts), and the api/worker entrypoint tests (§2.4 Worker).
- **Amendment, 2026-10-19: platform-stack rework 2** (review R1-B1 option
  (ii), R1-B2; security M-4, L-3, L-6, L-7; Windows proof F3; review R2 on
  `.env.example`; details in §2.1, §2.2 and §2.4).
  - **Context:** rework 1 added a fixed `backend` subnet, which broke
    parallel projects ("Pool overlaps") and still let the runtime probe pass
    with isolation lost (M-4). The Engine check accepted empty or garbage
    versions (L-6). The gateway substituted listen ports unchecked (L-3).
    `lint.sh` built PowerShell source from file names (L-7). Teardown with
    `--profile '*'` removed other runs' one-shot containers (F3).
  - **Decision:**
    - **No fixed address:** `backend` has no `ipam`; Docker's default pools
      give each project its own subnet, so parallel stacks from this compose
      file are supported. Host isolation is proven at runtime by the smoke
      host half reading `docker network inspect <project>_backend` for
      `gateway_mode_ipv4=isolated` (and `Internal`), not by probing an
      address from inside, which cannot prove absence (§2.2).
    - **Engine version:** launch requires `docker version` to succeed with a
      strictly numeric `MAJOR.MINOR.PATCH`, major ≥ 28 compared as an
      integer; anything else is refused before compose runs.
    - **Gateway templates:** the entrypoint validates every
      template-substituted variable: the five ports as integers 1–65535, the
      upstream as before. A drift test ties the template variables to the
      checked set.
    - **Lint:** `.ps1` paths reach PSScriptAnalyzer only through
      `KE_LINT_PS1_FILES`, read by a fixed command.
    - **Teardown:** `down` on the project's default-profile services only,
      without `--profile '*'` or `--remove-orphans`.
    - **`.env.example`:** `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` are
      empty; a comment names `aria-gb10-2`; the operator sets both in `.env`.
  - **Alternatives:**
    - A per-run subnet variable overridden by verify (R1-B1 option (i)):
      more config, and still a probe of guessed addresses.
    - Identifying the owner of `.1` by resolving service names (the
      review's suggested form of option (ii)): depends on Docker's
      allocation order and still cannot see a host address elsewhere in the
      subnet; the daemon's own setting is direct.
    - `sort -V` version comparison: ranks garbage and leading-space values
      at or above 28 (L-6).
    - A `-File` analyzer script taking paths as arguments (also allowed by
      L-7): one more `.ps1` to keep lint-covered.
  - **Consequences:**
    - Docker's default address pools must not overlap the host's LAN or
      VPN; that is a host Docker setting (`default-address-pools`), not
      ours.
    - Engine builds with suffixed versions (release candidates, some
      distro packages) cannot launch the stack.
    - A leftover one-shot container in a project makes teardown fail loudly
      instead of being removed silently.
    - Local verify runs have no model upstream unless the open R2 question
      (§2.2) is ruled.
    - The Windows proof goes stale again (Q34) and is repeated.
  - **First tests:** the Engine version cases and the teardown argument
    cases (§2.4 Scripts), the per-port gateway cases and the template drift
    test (§2.4 Gateway upstream check), the smoke host-half isolation check
    (§2.2), and the lint fixed-command tests (§2.2 Lint), all fast.

### ADR-KE-012: Offline bundle with a checksum manifest (platform-offline)
- **Context:** PS-3.1/3.2 require a bundle that installs and runs on a daemon
  with no images and no egress, and that rejects tampering.
- **Decision:**
  - **Bundle:** a directory, plus a tar of it, holding:
    - `docker save` image tars;
    - no wheels: the images carry their dependencies (bundle ruling);
    - vendored assets;
    - the compose files, config and scripts;
    - `bundle.json`;
    - `MANIFEST.sha256`.
  - **Install:** checks the manifest first, rejecting changed, missing and
    unlisted files, and then loads the images.
  - **Proof:** `ci/deployable-offline` runs in DinD within `verify.sh full`
    (ADR-KE-009). `ci/offline` runs in the host-side smoke, with a control
    probe that must succeed.
- **Alternatives considered:**
  - A private registry inside the bundle: an extra service just to serve
    images.
  - OCI layout plus skopeo: an extra host tool, against the "Git and Docker
    only" rule.
  - A signed manifest (minisign or cosign): a stronger guarantee, but it needs
    key management. Deferred and flagged to security.
- **Consequences:**
  - The bundle is large and linux/amd64 only. Hosts are Linux (bash
    installer) and Windows (PowerShell installer); macOS and Apple silicon
    are out of scope (Q20 ruling).
  - With no wheels, an offline image rebuild is not supported; the bundle
    ships built images only.
  - `ci/deployable-offline` runs in every local `full` (F5 ruling); the CI
    timeout is measured plus 50% (F6 ruling).
  - Integrity is proven, authenticity is not.
- **First tests:**
  - `test_bundle_manifest_rejects_tamper` (bash and PowerShell installers);
  - `test_bundle_lists_every_compose_image`.
