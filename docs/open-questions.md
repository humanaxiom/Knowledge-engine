# Open questions and working assumptions

The consolidated pre-code message asked for in §5.1 of the build prompt
(2026-10-18). Each question names the assumption the plan uses until you
answer it. Answer by number; anything left unanswered stands as assumed.

## Repository and process

- **Q1. The repo was empty.** `humanaxiom/Knowledge-engine` had no commits; it was
  not created from the template. **A1:** the `monitored-harness` template (commit
  `9abb753`) was imported verbatim as the first commit (`119aca7`).
- **Q2. Branches and pushing.** The prompt says pushing and PRs need your
  approval, and plan items go on `agent/<slug>`. The cloud session that started
  this work was assigned the branch `ccr-19465ed4-j1u0m5`, which is still the
  only branch on the remote. Since 2026-10-18 the work runs in your local clone,
  so idle reclamation no longer applies. **A2:** the planning documents are on
  `ccr-19465ed4-j1u0m5`. Each plan item is built on a local `agent/<slug>`
  branch, and nothing is pushed (to `agent/*` or any other branch), and no PR
  is opened, without your explicit go-ahead.
- **Q3. Resolved 2026-10-18.** The work moved to your local clone on Windows,
  where Docker 29.5.2 runs, and every gate now runs locally through
  `scripts/verify.sh` (evidence:
  `docs/evidence/harness-claude-code/green-full.txt`). Original question, kept
  for the record: *No Docker daemon in this cloud session.* The Docker CLI is installed
  but `/var/run/docker.sock` is absent. Every gate must run inside Docker, and
  item 0 is not done until `scripts/verify.sh` has run in every mode on a clean
  checkout. **A3:** gates are proven in GitHub Actions (which has Docker) and on
  your machine, and the evidence files say which. Nothing is reported green here
  that ran outside Docker. If you can enable Docker for this environment, say so.
- **Q4. Iteration cap.** **A4:** 5 per fix-and-retest loop, as in `AGENTS.md`.
- **Q18. Resolved 2026-10-20 (human ruling: SKIPPED, `docs/handoffs/ci-speed.md`).**
  **A18:** branch protection is not enabled. Merges to `main` stay a manual
  human action (PR + review); the local commit hook (`block-main-commit.sh`)
  remains the only automated guard. This is an accepted risk: the hook's
  known bypasses (harness-claude-code criterion 4e) are not backed by a
  remote control. Original question, kept for the record: *Branch protection
  on `main`.* Is branch protection enabled on `main` in
  `humanaxiom/Knowledge-engine`? The local hook (`block-main-commit.sh`,
  harness-claude-code criterion 4) is only a guard rail against agent mistakes
  and can be bypassed; branch protection is the real control (security M1).
  The earlier assumption said: not verified from here. Recommend enabling it:
  require a PR to merge into `main` and block force pushes.

## Deployment

- **Q5. SSO.** Which identity provider goes first: CAS (as in the JD repo's
  ADR-008), SAML or OIDC? **A5:** CAS first, behind the pluggable interface,
  with a dev provider for CI.
- **Q6. Port range.** The box runs other stacks. **A6:** all host ports default to
  the `47100–47199` range, set in `.env`, never in code.
- **Q7. Resolved 2026-10-18 (human ruling).** The model host is
  `aria-gb10-2`, an OpenAI-compatible endpoint. **A7:** it is configured via
  `KE_MODEL_UPSTREAM` and each pass's `KE_MODELS__<PASS>__BASE_URL`, never
  hardcoded (PS-1.2), and both hosts must be on `KE_EGRESS_ALLOWLIST` (names
  per ADR-KE-010; the unprefixed `MODEL_BASE_URL` is retired, ruling F2 of
  2026-10-18). GitHub runners cannot reach it, so model-calling integration
  and live golden tests skip there with a named reason and run where it is
  reachable through the stack gateway (Q30, narrowed by F-A). Model defaults
  are set by the Q38 ruling of 2026-10-20: compose and rewrite use
  `qwen3.5:latest`, audit uses `gpt-oss:120b`, and embed uses
  `nomic-embed-text` (768-dim); the fallback is `gpt-oss:20b` (A54). These
  config names are tags, not pins: the `/api/tags` digests recorded by the
  MR-5 run are the record of what was tested (see ADR-KE-014). *Superseded, kept
  for the record:* "Model defaults are `qwen2.5:14b-instruct` (fallback
  `llama3.1:8b`) and `nomic-embed-text` (768-dim)." Its port, URL scheme and URL are set per deployment in `.env`,
  with no default in `config/defaults.yaml` (Q32, resolved). Original question, kept for the
  record: *What is the model host's address, and is it reachable from where
  the gates run?* The earlier assumption said "CI never calls it".
- **Q8. Target hardware.** CPU and GPU, RAM, and disk on the on-premises box,
  which decide the OCR and layout models. **A8:** a CPU-only path (Tesseract,
  Docling or unstructured layout) is the default, and GPU models are opt-in per
  stage.

## Data and metrics

- **Q9. Manual baseline for "time per JD".** Who measured it, how, and when?
  **A9:** none exists yet. The metric is shown as *not yet measured*, with a
  placeholder that names the owner to be decided. It is never estimated.
- **Q10. Source identity for corpus revisions.** When a file is uploaded again,
  how do we know it is a new version of an existing document rather than a new
  document? **A10:** `source_key` is, in order of preference: an external ID from
  the institution profile (for example a position number), else a
  corpus-relative path, else the original filename plus the uploader's choice in
  the upload dialog ("new document" or "new version of …"). This choice is never
  inferred from similarity (DR12).
- **Q11. Retention and erasure.** Revisions are append-only. Does any corpus
  carry personal data that may need erasing, which conflicts with append-only
  storage? **A11:** revision content is stored in an encrypted blob keyed per
  source, so erasure deletes the key ("crypto-shredding"). Metadata, hashes and
  the audit chain remain, and the audit chain records the erasure itself. All
  revisions are retained indefinitely by default.
- **Q12. Policy effective dates.** Do rules need `effective_from` (applying from a
  future date, or back-dated) as well as the ratification date? **A12:** yes, both
  clocks are stored. Evaluation uses the version in effect at the evaluation
  time, and every output records that time.
- **Q13. Human corrections to records.** May reviewers correct extracted fields,
  as opposed to drafts? **A13:** yes, as `entered` revisions through the review
  queue. They survive re-parse, and any conflict goes to review (§R-REV-C.5).
- **Q14. Resolved 2026-10-20 (human ruling, `docs/handoffs/ci-speed.md`).**
  **A14:** the human (Adam Salah) acts as proxy ratifier for policy rules
  until real owners are named. Ratification is therefore no
  longer an external blocker in the milestone "Done" check; naming the real
  owners later replaces the proxy. Original question, kept for the record:
  *Ratification owners.* DR22 needs named people and dates per owner tier
  (institutional policy, policy-informed, technical). The earlier assumption
  said: they appear as marked placeholders (`OWNER-TBD`) in the plan. The
  milestone "Done" check reports them as an external blocker until you name
  them.

## Corpus

- **Q15. JD fixtures.** The prompt permits the JD repo's `fixtures/golden/` as the
  `jd` test corpus because it is published on public job boards. **A15:** it is
  copied as-is into `fixtures/jd/`, with the source commit and that provenance
  statement in `fixtures/README.md`. No other JD-repo data is copied.
- **Q16. The second corpus.** Which corpus follows JD? It shapes how generic the
  pack schema must be. **A16:** none is named yet. A toy pack under
  `tests/packs/toy/` proves "a new corpus is a new pack, not code".

## Frontend

- **Q17. Stack.** **A17 (proposed in ADR-KE-006):** server-rendered FastAPI +
  Jinja + htmx for every view, with one Cytoscape.js island for the graph
  explorer, all assets vendored. React + TypeScript stays the fallback if the
  graph explorer outgrows the island.

## platform-skeleton

Raised in the analyst review of the platform-skeleton criteria (2026-10-18) as
PS-Q1–PS-Q11 (`docs/requirements.md` § "Item: platform-skeleton"); the
orchestrator ruled the same day (`docs/handoffs/platform-skeleton.md`,
"orchestrator: split accepted, rulings"). The ones still open come first.

Open, raised 2026-10-19 by the analyst for `platform-offline`
(`docs/requirements.md` § PS-3). Moved with PS-3.6 to `platform-supply-chain`
by the split ruling (`docs/handoffs/platform-offline.md`, "rulings on
analyst plan") and decided when that item opens. It does not block
`platform-offline`, which has no scan stage.

- **Q42. Scan threshold and the vendored libraries.** **A42 (assumed):**
  - the run fails on any CRITICAL or HIGH finding that has a fixed version
    available;
  - other findings are reported in the evidence only;
  - exceptions go in a committed file, each with a reason, and security
    reviews them.

  Not settled: psycopg-binary vendors old native libraries (krb5 1.15.1,
  cyrus-sasl 2.1.26, pcre 8.32; L-13). If the scanner flags them, should they
  be accepted as exceptions (gssencmode is already disabled), or should the
  image switch to psycopg built against the base image's libpq? That
  switch changes the app image and the licence picture. Orchestrator or
  security.

Open, raised 2026-10-19 by the analyst for `platform-offline` (reconciling
R2 with spike S1). Does not block RED.

- **Q47. No gate covers a classic-store install.** R2 makes the install
  store-independent so operators need no containerd store. But the CI
  `dind` uses the containerd store (by ruling) and the human's Windows host
  does too (spike S1), so no recorded run installs the bundle on a
  classic-store (`overlay2`) daemon, where spike S1 showed `ref@digest`
  never resolves. **A47 (assumed):** the stubbed installer tests
  (`test_install_tags_loaded_image_as_bundle_name`,
  `test_install_override_maps_every_service_to_as_tag`) plus spike S1's
  manual classic-store run are enough for this item; no classic-store gate
  is added. Orchestrator: accept, or ask for a one-off recorded
  classic-store install in the evidence.

Raised and mostly settled 2026-10-19 for `platform-offline` (handoff
orchestrator sections "Q49 resolved", "build it for both", and later
rulings). Design: `docs/architecture.md` §2.5 *Arch*; criteria: PS-3.1
"per-arch bundles".

- **Q49. Resolved (human).** Per-arch bundles: linux/amd64 and
  linux/arm64, one bundle each. Built natively on a daemon of that arch
  (arm64 on `aria-gb10` through a docker context); no `--platform`; the
  installer refuses an arch mismatch before any load.
- **Q50. Resolved: in scope (human, "a path for mlx").** `install.sh` must
  run on macOS (bash 3.2, BSD tools) as well as Linux. Proven by a static
  forbid-list test, a shimmed-PATH test, and a recorded install on the
  Apple-silicon Mac when it arrives (not CI).
- **Q51. Resolved (orchestrator, 2026-10-19).** arm64 proof is a recorded
  build, bundle, install, launch and smoke on `aria-gb10` (aarch64,
  Ubuntu 24.04, Docker 29.6.2), reached through a docker context over SSH.
  An `ubuntu-24.04-arm` CI runner stays a later option; whether the repo
  can use one is unconfirmed.
- **Q52. Open, not this item.** Model serving with MLX on the Mac belongs
  to a later `model-hosts` plan item.
- **Q53. Resolved: extended (orchestrator, unit-2 rework round 2,
  2026-10-19; review RB2a).** The bash 3.2 and BSD rule now covers
  `install.sh`, `launch.sh` and `teardown.sh`, and the static forbid list
  runs over all three. `smoke.sh`, `net_isolated.sh` and `verify.sh` stay
  Linux and dev only. The Mac's recorded proof is install, launch and
  teardown, not smoke. A53 (install only) is withdrawn. Design:
  `docs/architecture.md` §2.5 *`install.sh` portability*.

Open, raised 2026-10-19 (orchestrator note in `docs/handoffs/platform-skeleton.md`,
"human rulings: model endpoint; orchestrator note Q38"; recorded by the analyst
in `platform-stack-ready` rework round 1):

- **Q38. Resolved 2026-10-20 (human ruling, `docs/handoffs/model-roles.md`).**
  **A38:** compose and rewrite use `qwen3.5:latest`, audit uses
  `gpt-oss:120b`, and embed uses `nomic-embed-text`. All three are installed
  on `aria-gb10-2` (`GET /api/tags`), so nothing needs pulling. This is a
  config change only, delivered by item model-roles (MR-1 to MR-7). The
  ruling does not name a fallback model; Q54 (A54) sets it to `gpt-oss:20b`. Original question, kept for
  the record: *Default models missing on the model host (human).* The prompt's
  default models `qwen2.5:14b-instruct` and `llama3.1:8b` are not installed
  on `aria-gb10-2`; `nomic-embed-text` is. Either pull the two models on
  `aria-gb10-2`, or name installed models as the defaults (a config change
  only). Must be settled before the first item that composes a draft; does
  not block the platform items. **Ruled alongside (human, 2026-10-19):**
  this deployment's `KE_MODEL_UPSTREAM` is `aria-gb10-2:11434` (Ollama,
  OpenAI-compatible `/v1`), with allowlist host `aria-gb10-2`; checked with
  `GET /v1/models` answering 200 from the dev host. This is the endpoint the
  PS-2.21 recorded run uses. No assumption is taken for the model names.

Resolved 2026-10-20 by the orchestrator for `model-roles`
(`docs/handoffs/model-roles.md`, rulings Q54, Q55; raised by the analyst,
`docs/requirements.md` § Item: model-roles):

- **Q54. Resolved 2026-10-20 (orchestrator ruling; the human may change
  it).** **A54:** `fallback_model` for compose, rewrite and audit is
  `gpt-oss:20b`. It is installed on `aria-gb10-2`, faster than the
  primaries and distinct from each of them. The key stays a required
  string (no schema change); no product code reads it. This unblocks MR-2,
  and `llama3.1:8b` leaves the living files (MR-4). Original question,
  kept for the record: *Fallback model for the chat roles (orchestrator or
  human; blocks MR-2).* The Q38 ruling names each role's `model` but not the
  `fallback_model` that compose, rewrite and audit each carry. That key is a
  required string in the settings, it is `llama3.1:8b` today, and that model
  is not installed on `aria-gb10-2`. No product code reads it yet (grep,
  2026-10-20). The options are: (a) each role's own model; (b) another model
  that is installed on `aria-gb10-2`, named by the human; (c) make the key
  optional and set it to null, which changes the settings schema. No
  assumption is taken.
- **Q55. Resolved 2026-10-20 (orchestrator ruling: A55 accepted).**
  **A55:** the timeouts stay as they are (120 s for the chat roles, 60 s for
  embed) unless the MR-5 recorded run measures a call that exceeds its
  role's `timeout_s`. In that case the architect proposes a value derived
  from that measurement and the orchestrator rules on it. Original
  question, kept for the record: *Chat-role timeouts for the new models
  (orchestrator; does not block RED).* `gpt-oss:120b` on audit may need more
  than `timeout_s: 120`, counting the cold load and the reasoning time.

Resolved 2026-10-20 by the orchestrator for `ci-speed`
(`docs/handoffs/ci-speed.md`; raised by the analyst,
`docs/requirements.md` § Item: ci-speed):

- **Q-CS1. Resolved 2026-10-20 (orchestrator ruling: no percentage
  tolerance).** **A-CS1:** pooled coverage is not judged against a band
  around the one-process figure. Instead every top-level module's process
  leaves its own coverage data file (`coverage run -p`), `coverage combine`
  consumes one per module, and a missing data file fails the run, naming the
  module (CS-4). The 80 % threshold is unchanged. Original question, kept
  for the record: *Coverage tolerance for the pool.* CS-4 proposed that the
  pooled coverage total may fall at most 1 point below the one-process
  figure for the same tests; confirm or set another value.

Open, raised 2026-10-19 by the analyst (`platform-stack-ready` rework round 1):

- **Q39. When the Valkey network/auth carry-in lands.** The orchestrator
  placed security M-1's network side (Valkey on its own network, password or
  ACL) in auth-audit as carry-in 7, "to be done before any ingest exposure".
  `docs/requirements.md` lists ingest-ledger before auth-audit, and
  ingest-ledger criterion 5 puts files on the job queue. Is carry-in 7 built
  at the start of ingest-ledger (or a small item before it), or does
  auth-audit move ahead of ingest-ledger? **A39 (assumed):** carry-in 7 is
  done as the first unit of whichever item first feeds untrusted input to
  the queue (today ingest-ledger), and is tracked in auth-audit until then.
  Does not block `platform-stack-ready`.

Open, raised 2026-10-19 for `platform-stack-ready` (analyst, after ruling S1):

- **Q37. Store stop/start against a pre-existing project.** Ruling S1 says
  the PS-2.8 smoke tears down only a project it launched and "never stops an
  operator's live stack". Not settled: given smoke run by hand against an
  already-running project, does it still stop and restart one store (a
  brief outage of the operator's postgres), or does it skip the store
  stop/start and say so? Inside `verify.sh full` and CI the project is
  always smoke-launched, so the gate is unaffected. **A37 (assumed):** the
  smoke skips the store stop/start against a pre-existing project and
  prints that it skipped it (never reports it as passed), reading "never
  stops an operator's live stack" as covering a single store. Does not
  block RED; the tester writes the pre-existing case to that assumption.

Resolved 2026-10-19 for `platform-offline` (`docs/handoffs/platform-offline.md`,
"rulings on analyst plan", "rulings on architect R1–R7", "rulings from
spikes (R2, R6)"; Q43 by the human). Criteria: `docs/requirements.md` § PS-3,
"Reconciled with the rulings".

- **Q40. Resolved (orchestrator ruling).** **A40:** as assumed: `dist/` is gitignored, a verify run removes its own
  bundle, there is no size cap (sizes are recorded in the evidence), and a
  dirty-tree bundle is allowed and marked in `bundle.json`. Amended by R2
  (per-image tars, no single `.tar` of the directory) and R6 (a 10 GB
  free-disk check; PS-3.1, PS-3.2).
  Original question, kept for the record: Bundle location, size and dirty trees. §2.5 writes
  `dist/knowledge-engine-<git sha>/` plus a `.tar` of it, but `dist/` is
  not gitignored. Bundle and tar on disk, plus the images loaded into DinD,
  roughly triple the image footprint, and CI runner disk is finite. A sha
  does not identify an uncommitted tree. **A40 (assumed):**
  - `dist/` is gitignored;
  - a verify run removes its own bundle when the check ends;
  - there is no size cap, but the size of the bundle and the tar is
    recorded in the evidence;
  - a bundle built from a dirty tree is allowed (verify tests the working
    tree), and `bundle.json` marks it as dirty.
- **Q41. Resolved (orchestrator ruling).** **A41:** as assumed. It applies to `platform-supply-chain`, which now holds
  the scan (R3); this branch has no scan stage.
  Original question, kept for the record: Scanner vulnerability DB: offline or build-time. The deployed
  product has no runtime internet, but builds may fetch. **A41 (assumed):**
  - the scanner and its DB are build and verify tools, fetched in the
    `verify.sh full` host half alongside the image builds, in CI and
    locally;
  - they are not in the bundle, and a deployed box never scans;
  - a newly published CVE can turn `full` red with no code change, and
    that is the gate working, not a flake.
- **Q43. Resolved (human ruling on Phoenix; orchestrator R4, R7).** **A43:** the bundle holds the stack images only (R7), so `ke-gates` and
  `dind` are not redistributed. Only `ke-app` is scanned, in
  `platform-supply-chain`. The notices list `ke-app`'s Python packages and
  every third-party stack image by name and licence. Neo4j Community is
  listed as GPL-3.0 with a source URL (R4). Arize Phoenix is kept as a
  documented exception to "open-source components only" (human, 2026-10-19):
  likely Elastic License 2.0, internal on-prem use allowed, listed in the
  notices; security confirms the licence text at the pinned digest
  (PS-3.8).
  Original question, kept for the record: Scan and licence scope beyond `ke-app`. The ruling names the
  `ke-app` scan and psycopg notices only. The bundle also redistributes
  `ke-gateway`, `ke-gates`, `dind` and the third-party images (postgres,
  neo4j, valkey, phoenix). Neo4j Community is GPLv3. Phoenix's licence
  (Elastic License 2.0 as I understand it) should be confirmed by security at
  the pinned version against the prompt's "open-source components only".
  **A43 (assumed):**
  - only `ke-app` is scanned;
  - notices cover `ke-app`'s Python packages;
  - the third-party images are listed in the notices by name and licence,
    with no further obligation work in this item;
  - Phoenix's licence goes to the human.
- **Q44. Resolved (orchestrator ruling).** **A44:** as assumed (R5): 20 minutes when the offline stages land, then
  measured + 50% from the first green CI run (PS-3.4).
  Original question, kept for the record: CI timeout before the first measured run. The offline check may
  push `full` past today's 10 minutes, and a cancelled run costs a round.
  **A44 (assumed):** as C1 did for 2b, the commit that wires in the offline
  check raises `timeout-minutes` to 20. The first green CI run then sets
  measured + 50% in a follow-up commit on the branch.
- **Q45. Resolved (orchestrator ruling).** **A45:** as assumed. With no `bundle.ps1` (R1), the Windows run proves the
  PowerShell installer and `launch.ps1`; the bundle is built on a Linux
  build host.
  Original question, kept for the record: Windows proof of the PowerShell installer. **A45 (assumed):** a
  recorded run on the human's Windows host (Q31) does three things: it
  rejects a tampered bundle, installs the untouched bundle, and launches
  with `launch.ps1`. The host's network is not disabled, because the
  offline property is proven by DinD on Linux and the Windows run proves
  the scripts.
- **Q46. Resolved (orchestrator ruling).** **A46:** as assumed.
  Original question, kept for the record: `ci/offline` probe target. §2.5 leaves it to implementation.
  **A46 (assumed):** the target is neither the model host nor any
  allowlisted host. The gate's verdict does not depend on a public
  third-party host being up, so the control has to succeed in CI and on a
  dev box alike. The target is recorded in the handoff.

Resolved by the orchestrator 2026-10-19 (`docs/handoffs/platform-stack-ready.md`,
"orchestrator: rulings on analyst plan"; C1 in "rulings on architect plan"):

- **Q35. Resolved (orchestrator ruling).** **A35:** as assumed: (a) the
  caller's environment wins, even when set empty; (b) only the repo-root
  `.env` counts; (c) until platform-offline (L-5), "no other key" covers the
  verify project's environment and compose arguments only. Settled in
  PS-2.21 *Precedence*. Original question, kept for the record:
  Model upstream keys in local verify: source and precedence. The
  umbrella ruling passes `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` "from
  the caller's environment or the operator's `.env`". Not settled: (a) when
  both set a key, which wins; (b) whether "the operator's `.env`" is only the
  repo-root `.env` or also a file named by `KE_ENV_FILE` (the launch scripts
  read both); (c) security L-5 (deferred) leaves `gates-it` able to read the
  whole `.env` through its read-write repo mount, so "no other `.env` value
  is read" holds for the verify project's environment and compose arguments,
  not for the filesystem. Is that acceptable until `platform-offline`?
  **A35 (assumed):** (a) the caller's environment wins, as compose does;
  (b) the repo-root `.env` only; (c) acceptable, with PS-2.21 testing the
  environment and arguments only.
- **Q36. Resolved (orchestrator ruling; reaffirmed as C1 against the
  architect's "7 min now").** **A36:** as assumed: CI stays at 20 minutes
  until 2b's first green CI run, then that run's duration plus 50%, rounded
  up, in a follow-up commit before close. Settled in PS-3.4 in 2b. Original
  question, kept for the record: Which CI run sets the PS-3.4 timeout. The 274 s baseline
  (0f2821c) predates 2b's store stop/start and worker, so 2b's `full` will be
  slower. **A36 (assumed):** the timeout stays 20 minutes until the first
  green CI run of the 2b branch; the value is then set to that run's
  duration plus 50%, rounded up, in a follow-up commit on the same branch
  before the item closes, and the reviewer checks it against that run's log.

Resolved by the orchestrator 2026-10-19 (`docs/handoffs/platform-stack.md`,
"orchestrator: split + rulings Q33, Q34" and "rulings on architect R1–R4"):

- **Q33. Resolved (orchestrator ruling).** **A33:** (a) the build/launch
  scripts (bash and PowerShell) also refuse a non-loopback `KE_BIND_ADDRESS`
  outside `dev` before `docker compose up`, in addition to the engine's
  startup refusal; the gateway image's entrypoint bind check refuses under
  the same rule (ruling R4), and is the check that stops the publish;
  (b) loopback means any address in `127.0.0.0/8`, plus `::1`;
  `KE_BIND_ADDRESS` itself is IPv4 only (architect, §2.4), so IPv6 binding is
  out of scope and an IPv6 value is rejected as not IPv4; (c) in `dev` each
  check warns naming `KE_BIND_ADDRESS` and continues. Settled in PS-2.14.
  Original question, kept for the record: The port
  ruling (umbrella, 2026-10-19) says a non-loopback `KE_BIND_ADDRESS` is
  refused at startup outside `dev`. Not settled:
  (a) *Where.* The engine's startup check runs in `api` and `worker`, but
  `gateway` publishes the ports whether or not `api` starts, so a refused
  `api` still leaves the gateway (and Phoenix behind it) on the LAN. Should
  the launch scripts (bash and PowerShell) also refuse before
  `docker compose up`, or is the `api` refusal enough until auth-audit?
  (b) *Loopback set.* Is it exactly `127.0.0.1` and `::1` (the addresses
  Docker accepts as a bind host), or the whole `127.0.0.0/8`? PS-Q3's list
  also has `localhost`, which Docker does not accept as a bind address.
  (c) *Dev warning.* Should `KE_ENV=dev` with a non-loopback value log a
  warning naming `KE_BIND_ADDRESS`, as PS-1.5 does for auth off and hidden
  trace content?
- **Q34. Resolved (orchestrator ruling).** **A34:** accepted as the analyst
  proposed: the recorded Windows run must use the branch head, or the diff
  since must change no script, compose file or Dockerfile; otherwise it is
  repeated before commit. Settled in PS-2.9. **Scope ruling (orchestrator,
  2026-10-19, `platform-stack-ready` rework round 1):** "script" means the
  PowerShell launch, build and teardown path; gate-only bash scripts and
  engine code do not make the Windows proof stale, while the PowerShell
  launch/build/teardown scripts, compose files and Dockerfiles do. Original question, kept for the
  record: Q31 accepts a
  recorded run on the human's Windows host. If scripts, compose files or
  Dockerfiles change after the run, must it be repeated before commit? PS-2.9
  currently requires it to match the branch head, or the diff since to touch
  none of those files.

Resolved by the orchestrator 2026-10-18 (`docs/handoffs/platform-config.md`,
"orchestrator: rulings on analyst Q31, Q32 and casing"):

- **Q31. Resolved (orchestrator ruling).** **A31:** a recorded run on the
  human's Windows host proves the PowerShell build, launch and teardown
  scripts, with its output saved as evidence in platform-stack (PS-2.9).
  Original question, kept for the record: *Q20 settled the scope (Windows and
  Linux only) but not the proof. CI runs Linux only. Is a recorded run on
  your Windows machine, with its output in the evidence folder, enough proof
  for the PowerShell scripts?*
- **Q32. Resolved (orchestrator ruling).** **A32:** the model host's scheme,
  port and URL are set per deployment in `.env`. `config/defaults.yaml` ships
  no model-host default; `.env.example` leaves `KE_MODEL_UPSTREAM` empty with
  a comment naming `aria-gb10-2` as this deployment's host (PS-1.2). Original
  question, kept for the record: *Q7 names the host but not its port or URL
  scheme, and does not say whether `config/defaults.yaml` ships it as the
  default `KE_MODEL_UPSTREAM` (and `KE_EGRESS_ALLOWLIST` entry) or leaves
  both unset so each deployment supplies them.*
- Also ruled the same day (tester risks, platform-config): loopback addresses
  and compose service names are not hardcoded hosts (PS-1.2); phoenix's
  compose port moves to `.env` (`KE_PHOENIX_PORT=47101`) within
  platform-config, while `test_harness_default_collector_matches_env_example`
  stays in platform-stack (PS-2.2); `changeme` matching is case-insensitive
  and placeholders are `changeme-<key in lowercase>` (PS-1.9).

Resolved by the human 2026-10-18 (`docs/handoffs/platform-skeleton.md`,
"orchestrator: human rulings Q30, Q20, Q7"):

- **Q30. Resolved (human ruling, narrowed by the human's ruling F-A the same
  day).** Integration tests run as compose services with no Docker socket.
  `gates-it` is on internal networks only and has no internet access; the
  only outside host tests reach is the LLM on `aria-gb10-2`, through the
  stack gateway (F-A). Model-calling integration tests run when that host is
  reachable and skip with a visible, named reason when it is not
  (for example on GitHub runners). Unit tests (`verify.sh fast`) keep no
  network. The app's egress allowlist (DR30) still applies. The offline-bundle
  checks still prove the deployed product runs offline. This amends DR31 and
  the "Integration" convention in `docs/requirements.md` (both keep their
  original wording as a note) and settles PS-2.4–PS-2.7; `CLAUDE.md` gains a
  "What verify.sh runs that CI cannot" section (PS-2.13).
  `test_gates_it_internal_only_and_no_socket` replaces
  `test_gates_it_has_network_access_and_no_socket`;
  `test_egress_allowlist_holds_with_network_access` is kept (model calls go
  through the gateway forward). As first ruled, Q30 put `gates-it` on a
  network WITH external access (not `internal`); F-A withdrew that, on the
  architect's flag that the gateway already gives the model route. Original
  question, kept for the record:
- *(original)* **Q30 (architect finding F1). Integration mechanism vs DR31 (human; blocks
  `platform-stack`).** DR31, a binding rule of the build prompt, says
  integration tests use real Postgres/Neo4j/Valkey "via testcontainers".
  ADR-KE-009 (the answer to Q19) proposes instead that the stores run as
  compose services on an internal network (`internal: true`, no route out),
  reached by a one-shot `gates-it` container, with no Docker socket and no
  testcontainers. It keeps DR31's intent: real stores, mocked models, no
  egress. The architect rejected mounting the Docker socket for testcontainers
  because the socket is root-equivalent on the host and would let test code
  escape `network_mode: none`. Do you accept the compose mechanism in place of
  testcontainers? **A30 (before the ruling):** none; asked of you.
- **Q20. Resolved (human ruling).** No macOS for now: Windows (PowerShell) and
  Linux only; Apple silicon is out of scope. Settles PS-2.9 and the PS-3.1
  platform note. The proof sub-question is carried as Q31. *Narrowed
  2026-10-19 by Q49 and Q50:* arm64 bundles and `install.sh` on an
  Apple-silicon Mac are now in scope. Original question, kept for the
  record:
- *(original)* **Q20 (PS-Q10). macOS and Windows proof (human).** CI runs Linux only. Is a
  recorded run on your Windows machine enough proof for the PowerShell build,
  launch and teardown scripts, and who proves macOS (no macOS machine is
  recorded)? The offline bundle is linux/amd64 only for now (orchestrator
  ruling, 2026-10-18), so a Mac on Apple silicon (arm64) can run it only under
  emulation, if at all: is Apple silicon a target, and if so, does it need
  arm64 images in the bundle? **A20 (before the ruling):** none; asked of you.
- **Placeholder secrets (orchestrator ruling, replaces part of F3).** Every
  secret placeholder in `.env.example` is `changeme-<key>`; startup refuses
  any secret starting with `changeme` outside `dev`; `.env.example` is not
  shipped in the image (PS-1.9).

Answered by the architect 2026-10-18:

- **Q19 (PS-Q7). Gates network vs real stores.** `gates` has `network_mode:
  none` and no Docker socket, yet integration needs real stores, and the
  live-stack smoke and deployable-offline gate need a running stack and a
  clean daemon. **A19:** ADR-KE-009. The stores are compose services on an
  internal network, a one-shot `gates-it` joins that network, `gates` stays
  network-less, and the offline check drives a privileged DinD daemon on an
  internal network in every `verify.sh full`. The change of mechanism from
  DR31 was Q30, now ruled and narrowed by F-A: `gates-it` is internal-only
  and reaches the model host only through the gateway.

Ruled 2026-10-18:

- **Q21 (PS-Q1). CI runner image.** **A21:** pin `ubuntu-24.04`, the image
  `ubuntu-latest` resolved to before the 2026-10-19 move; confirm it from the CI
  log of 615adf8 when implementing.
- **Q22 (PS-Q2). Harness Phoenix and A6.** **A22:** one Phoenix for harness and
  product, with ports from `.env` in 47100–47199. `log_event` keeps reading
  `PHOENIX_COLLECTOR_ENDPOINT`; only its default and the docs change.
- **Q23 (PS-Q3). "Local" trace collector.** **A23:** a loopback address or a
  compose service name on the internal network; anything else is refused at
  startup.
- **Q24 (PS-Q4). Hidden trace content in dev.** **A24:** `OPENINFERENCE_HIDE_*`
  defaults to `true` in every env; only `KE_ENV=dev` may set `false`, and then it
  logs a warning.
- **Q25 (PS-Q5). Coverage and mypy scope.** **A25:** line + branch coverage
  >= 80% and `mypy --strict` over every first-party package (`harness_telemetry`
  and the new engine package), excluding tests.
- **Q26 (PS-Q6). Readiness without a model host.** **A26:** `/readyz` reports
  the model host as its own field; overall readiness excludes it (ingest and
  review work without a model). Routes that compose drafts check it themselves.
- **Q27 (PS-Q8). DR16 register timing.** **A27:** confirmed; register entries
  for config keys arrive with policy-book.
- **Q28 (PS-Q9). Shipping rule timing.** **A28:** `platform-stack` may merge
  before `platform-offline`. "Deployable offline" is met at the end of
  `platform-offline`, before any reviewer-facing feature ships.
- **Q29 (PS-Q11). Python version.** **A29:** pin Python 3.12
  (`requires-python = ">=3.12,<3.13"`), in `platform-config`.

Architect findings F2–F6, ruled by the orchestrator 2026-10-18
(`docs/handoffs/platform-skeleton.md`, "orchestrator: rulings on architect
F1–F6"; F1 is Q30): `KE_`-prefixed variable names are canonical with no
aliases; secrets have no default and placeholders are refused outside `dev`;
`config/verify.env` is an allowed literal location; the offline check runs in
every local `verify.sh full`; CI `timeout-minutes` is the measured duration
plus 50%; the bundle carries no wheels and is linux/amd64 only (Apple silicon
out of scope, Q20). The placeholder definition in F3 was later replaced by the
`changeme-` prefix ruling above.
