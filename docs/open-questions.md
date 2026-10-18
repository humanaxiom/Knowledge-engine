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
- **Q18. Branch protection on `main`.** Is branch protection enabled on `main` in
  `humanaxiom/Knowledge-engine`? The local hook (`block-main-commit.sh`,
  harness-claude-code criterion 4) is only a guard rail against agent mistakes
  and can be bypassed; branch protection is the real control (security M1).
  **A18:** not verified from here. Recommend enabling it: require a PR to merge
  into `main` and block force pushes.

## Deployment

- **Q5. SSO.** Which identity provider goes first: CAS (as in the JD repo's
  ADR-008), SAML or OIDC? **A5:** CAS first, behind the pluggable interface,
  with a dev provider for CI.
- **Q6. Port range.** The box runs other stacks. **A6:** all host ports default to
  the `47100–47199` range, set in `.env`, never in code.
- **Q7. Model host.** What is the model host's address, and is it reachable from
  where the gates run? **A7:** it is an OpenAI-compatible endpoint whose
  host:port is set by `KE_MODEL_UPSTREAM`; each pass's base URL is
  `KE_MODELS__<PASS>__BASE_URL`, and both hosts must be on
  `KE_EGRESS_ALLOWLIST` (names per ADR-KE-010; the unprefixed
  `MODEL_BASE_URL` is retired, ruling F2 of 2026-10-18). CI never calls it,
  and live golden tests skip when it is absent. Defaults are `qwen2.5:14b-instruct` (fallback `llama3.1:8b`) and
  `nomic-embed-text` (768-dim).
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
- **Q14. Ratification owners.** DR22 needs named people and dates per owner tier
  (institutional policy, policy-informed, technical). **A14:** they appear as
  marked placeholders (`OWNER-TBD`) in the plan. The milestone "Done" check
  reports them as an external blocker until you name them.

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

Open:

- **Q30 (architect finding F1). Integration mechanism vs DR31 (human; blocks
  `platform-stack`).** DR31, a binding rule of the build prompt, says
  integration tests use real Postgres/Neo4j/Valkey "via testcontainers".
  ADR-KE-009 (the answer to Q19) proposes instead that the stores run as
  compose services on an internal network (`internal: true`, no route out),
  reached by a one-shot `gates-it` container, with no Docker socket and no
  testcontainers. It keeps DR31's intent: real stores, mocked models, no
  egress. The architect rejected mounting the Docker socket for testcontainers
  because the socket is root-equivalent on the host and would let test code
  escape `network_mode: none`. Do you accept the compose mechanism in place of
  testcontainers? **A30:** none; asked of you. Until you rule, DR31's text and
  the requirements' "Integration" convention stay as written, `platform-config`
  proceeds, and PS-2.4–PS-2.7 are blocked.
- **Q20 (PS-Q10). macOS and Windows proof (human).** CI runs Linux only. Is a
  recorded run on your Windows machine enough proof for the PowerShell build,
  launch and teardown scripts, and who proves macOS (no macOS machine is
  recorded)? The offline bundle is linux/amd64 only for now (orchestrator
  ruling, 2026-10-18), so a Mac on Apple silicon (arm64) can run it only under
  emulation, if at all: is Apple silicon a target, and if so, does it need
  arm64 images in the bundle? **A20:** none yet; asked of you.

Answered by the architect 2026-10-18:

- **Q19 (PS-Q7). Gates network vs real stores.** `gates` has `network_mode:
  none` and no Docker socket, yet integration needs real stores, and the
  live-stack smoke and deployable-offline gate need a running stack and a
  clean daemon. **A19:** ADR-KE-009. The stores are compose services on an
  internal network, a one-shot `gates-it` joins that network, `gates` stays
  network-less, and the offline check drives a privileged DinD daemon on an
  internal network in every `verify.sh full`. The change of mechanism from
  DR31 is Q30.

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
under Q20).
