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

## platform-supply-chain

Raised 2026-10-21 by the analyst (`docs/requirements.md` § "Item:
platform-supply-chain"; handoff `docs/handoffs/platform-supply-chain.md`).
**All ruled 2026-10-21** (handoff, "HUMAN RULINGS" and "ORCHESTRATOR
RULINGS"; recorded here by the architect). Q42 (§ platform-skeleton below)
also belongs to this item and is ruled too. Each answer below is the ruling
as written in the handoff; the original question follows it, kept for the
record.

- **Q56. Resolved 2026-10-21 (human ruling).** **A56:**
  - (a) YES: the scan DB is fetched by a host-half one-shot `scan-db` (the
    only service with a route out); gates, gates-it and scan stay offline.
    CLAUDE.md and README "networking disabled" wording is updated to say the
    rule covers the gate services; the human approved the CLAUDE.md change,
    and it lands in the same commit as scan-db.
  - (b) FAIL CLOSED, naming the host and the stage.
  - Not ruled, carried as a design note: the database host the dev host
    and CI must reach is the one named in `scripts/scan.sh`
    (`docs/architecture.md` ADR-KE-013, amendment 1); the developer records
    it in the handoff. If SFU's network restricts egress, that host is the
    one to allow.

  Original question, kept for the record:
  *Q56. The scan database fetch, the only network step.*
  - Settled by Q41: the database is fetched fresh in the `verify.sh full`
    host half, in CI and locally.
  - ADR-KE-013 puts the fetch in a host-half one-shot (`scan-db`, on the
    default bridge). It is not in `gates` or `gates-it`, which keep no route
    out.
  - Not settled:
    - (a) Does this fit "networking disabled in gates" as you mean it?
      CLAUDE.md says verify runs "inside the one-shot `gates` compose
      service … with networking disabled". With `scan-db`, a second
      container in a verify run has a route out. `build.sh`'s pulls already
      use the network, but they run on the host, not in a container.
    - (b) When the database host cannot be reached or the fetch fails, does
      the run fail, or skip the scan with a named reason?
  - **Recommended default:**
    - (a) Yes. The rule applies to the gate services, and they stay
      offline. `scan-db` is a host-half fetch like `build.sh`'s pulls and
      mounts only its own volume. The CLAUDE.md and README wording is
      updated to say so, with your approval, since CLAUDE.md is yours.
    - (b) Fail closed, naming the host and the stage.
  - Trade-off for (b):
    - Failing closed means an outage or rate limit at the database host
      turns every `full` red, in CI and locally, even for changes that do
      not touch `ke-app`.
    - Skipping with a reason, as the model tests do, keeps unrelated work
      moving. But a green CI run could then carry no scan, which is what
      the scan exists to prevent.
    - A middle option is a bounded retry before failing. It adds CI time,
      which PSC-9 would have to measure.
  - Also needed: the dev host and CI must be able to reach the scanner's
    database host. If SFU's network restricts egress, you name the
    allowed host.

- **Q57. Resolved 2026-10-21 (human ruling).** **A57:** SPDX 2.3 JSON, one
  per bundled image, generated offline at bundle time and shipped in the
  bundle. Built in the new item `platform-sbom` (split accepted by the
  orchestrator, 2026-10-21).

  Original question, kept for the record: *Q57. SBOM format and scope.*
  - **Recommended default:**
    - SPDX 2.3 JSON;
    - one SBOM for each image in `bundle.json`: `ke-app`, `ke-gateway` and
      the third-party stack images;
    - generated offline at bundle time, and shipped in the bundle next to
      `THIRD_PARTY_NOTICES.md`.
  - Trade-offs:
    - *Format.* SPDX is an ISO standard (ISO/IEC 5962) aimed at licence
      compliance, which is what M-NT1 asks for. It also matches the SPDX
      identifiers `NOTICE.md` already requires. CycloneDX is aimed at
      security tooling and vulnerability exchange (VEX), and many scanners
      consume it. Producing both adds little generator time, but doubles
      the files to test and ship.
    - *Scope.* SBOMs for every bundled image cover M-NT1's Alpine and
      Debian layers in valkey, ke-gateway, postgres and neo4j. They add one
      generator run per image to `bundle.sh` on CI, about six; the cost is
      measured on CI, as in PSC-9. `ke-app` alone is cheaper, but leaves the
      third-party layers unlisted.
    - *Placement.* Shipping the SBOM in the bundle gives the operator the
      inventory. Keeping it as evidence only keeps the bundle smaller, but
      the operator does not get it.

- **Q58. Resolved 2026-10-21 (human ruling).** **A58:** BUILD SOURCE OFFERS
  NOW (not deferred to SFU advice). Built in `platform-sbom`
  (`docs/requirements.md` § "Item: platform-sbom"). Not ruled, and not
  blocking that item: who asks SFU legal/IP, and whether distribution
  outside SFU is planned.

  Original question, kept for the record: *Q58. GPL source offers: now, or
  after SFU legal/IP advice?*
  - What ships today (M-NT1), with no written source offer:
    - GPL-2.0 Alpine packages (busybox, apk-tools, ssl_client) in valkey
      and in ke-gateway's base;
    - Debian GPL packages in the postgres, neo4j and ke-app bases.

    Neo4j's GPL-3.0 has an upstream URL only (R4, L-NT1).
  - **Recommended default:** defer source offers until SFU legal/IP advice
    says whether and how they apply, for example whether installing the
    bundle within SFU counts as distribution. Until then, this item:
    - lists the components with their upstream source (PSC-15), in wording
      that claims no compliance;
    - records a known limit: the bundle goes to no one outside SFU until
      the ruling.
  - Trade-offs:
    - Deferring builds no mechanism that the advice could make unnecessary
      or shape differently. Until the advice comes, the bundle cannot go to
      a third party. If it does, the GPL-2.0 §3 and GPL-3.0 §6 obligations
      are unmet.
    - Building offers now (a source archive, or a written offer valid for
      three years) costs disk, bundle time and an archive to maintain. It
      may also not match the advice.
  - Also needed:
    - who asks SFU legal/IP;
    - whether any distribution outside SFU is planned, which would set a
      date.

- **Q59. Resolved 2026-10-21 (orchestrator ruling).** **A59:** scan the
  native arch in verify full; the arm64 scan comes with recorded arm64 runs
  (output saved as evidence).

  Original question, kept for the record: *Q59. Which architecture's
  `ke-app` is scanned.*
  - `verify.sh full` builds and scans the native architecture: amd64 on CI
    and on the dev host.
  - The arm64 `ke-app` in the aria-gb10 bundle is scanned only when `full`
    runs on an arm64 host. psycopg-binary's aarch64 wheel vendors its own
    copies of the native libraries, which may differ.
  - **Recommended default:** scan the native architecture in
    `verify.sh full`. When an arm64 bundle is produced, its recorded arm64
    run (the Q51 form) includes the scan, and the scan output is saved as
    evidence.
  - Trade-off: this adds no CI time and needs no emulation. But between
    recorded arm64 runs, the arm64 image can carry a fixed High that nobody
    sees. Scanning both architectures on every CI run needs either a
    cross-architecture build, emulated and slow on the 2-vCPU runner, or an
    arm64 runner.

- **Q60. Resolved 2026-10-21 (orchestrator ruling).** **A60:** trigger at
  > 3 min added to the slower CI run; the orchestrator decides before the
  timeout is raised.

  Original question, kept for the record: *Q60. When the scan's CI cost
  needs a decision (orchestrator or human).*
  - Context:
    - the CI job takes 20.3–21.1 min against a 32-min timeout (once PR #9
      lands);
    - ADR-KE-013 estimates 40–80 s for the scan, which is not a CI
      measurement (PSC-9);
    - PS-3.4 lets the timeout follow the measured time with no cap.
  - **Recommended default:** no hard cap, but a trigger. If the save,
    `scan-db` and `scan` stages together add more than 3 min to the slower
    CI run, the orchestrator decides before the timeout is raised: accept
    and re-measure, or ask the architect to cut the cost (for example by
    reusing the bundle's `ke-app` tar).
  - Trade-off: a trigger keeps the margin for later items in view. No
    trigger keeps the rule simple, but the job grows by the scan's cost
    with no one deciding it.

## platform-sbom

Raised 2026-10-22 by the analyst (`docs/requirements.md` § "Item:
platform-sbom", PSC-13-PSC-24; handoff `docs/handoffs/platform-sbom.md`).
**Q61-Q63 were resolved by the human on 2026-10-22**, each matching the
recommended option. Q57 and Q58 (§ platform-supply-chain above) are settled
and not re-opened. **Q64 was resolved by the human on 2026-10-22**; Q65 and
Q66 (raised by the analyst 2026-10-22, from the Q64 amendments) were
resolved by the orchestrator on 2026-10-22. **Q67 was resolved by the
human on 2026-10-23** (security U4 M-3); Q68 (raised by the analyst
2026-10-23, from Q67) was resolved by the orchestrator on 2026-10-23.
**Q69 and Q70 were resolved by the human on 2026-10-23.** *(Amended 2026-10-23, analyst, Q69/Q70)*
**Q71 is open for the human** (raised 2026-10-25 by the analyst from
architect U7 point O1; decide before U7c). *(Amended 2026-10-25, analyst, U7)*

- **Q61. Resolved 2026-10-22 (human ruling).** **A61:** FAIL CLOSED on a
  failed or checksum-mismatched source fetch: one call, no retry, naming the
  host, the stage and the file, as Q56(b).

  Original question, kept for the record: *Q61. A failed or
  checksum-mismatched source fetch.*
  - Context:
    - PSC-15 fetches the exact-version source of every GPL-family
      component at bundle time, on the build host, and checks each file
      against the upstream checksum in the Q48 form. PSC-23 makes the fetch
      the item's only new network step.
    - The hosts include Debian's archive, Alpine's aports and distfiles,
      GitHub (the Neo4j tag, the Temurin build) and PyPI. The images are
      pinned by digest, so their package versions age. Older Debian
      versions may by then be served only by `snapshot.debian.org`, which is
      slow and rate-limited (to be confirmed by the architect).
    - Two kinds of failure: (i) the host cannot be reached, times out or
      returns an error; (ii) the file arrives, but its checksum differs from
      the upstream one (or from the trust-on-first-use value recorded
      earlier, Q48).
  - Options:
    1. Fail closed for both. The bundle step exits non-zero, naming the
       host, the stage and the file, and leaves no manifest and no release
       record (PSC-24). One call, no retry, no skip path, as Q56(b) for the
       scan database.
    2. Fail closed for both, with one bounded retry on an unreachable host
       first.
    3. Fail open on an unreachable host. The bundle is written; the
       component falls back to the L-NT1 wording ("Upstream source:
       <url>"), and the gap is recorded in the source index and
       `bundle.json` and printed. A mismatch still fails closed.
  - **Recommended: option 1, and a mismatch is never fail-open under any
    option.**
    - A bundle that ships GPL binaries without their source is the M-NT1
      defect this item closes. A fail-open bundle can reach a third party
      with nobody noticing, which the Q58 ruling (build the offers now) is
      meant to prevent.
    - A checksum mismatch is an integrity failure (tampering, or an
      upstream re-release), not an availability one.
    - It keeps one rule for verify's network steps (Q56(b)).
  - Trade-offs:
    - An outage at any source host turns `full` red, in CI and locally,
      even for changes that touch no image. The exposure depends on Q63:
      with the full set fetched every run, every PR push depends on every
      source host; with a reduced verify set, only on a few small files.
    - A bounded retry (option 2) softens transient failures, at a CI cost
      PSC-16 would measure; the scan precedent chose no retry.
    - Option 3 keeps unrelated work moving, but a green run could then
      carry a bundle with missing source, which is what the item exists to
      stop.

- **Q62. Resolved 2026-10-22 (human ruling).** **A62:** Q60's 3-minute CI-cost
  trigger applies to this item. Above 180 s on the slower of two green runs,
  the measurement goes to the human before the timeout is raised.

  Original question, kept for the record: *Q62. Does Q60's 3-minute trigger
  apply to this item's CI time, and what happens past it?*
  - Context:
    - A60 set the trigger for the scan stages only ("the save, `scan-db`
      and `scan` stages together add more than 3 min"). PSC-16 says this
      item re-measures PS-3.4 if it adds a minute or more on CI.
    - This item adds SBOM generation for six images, the source fetch, a
      larger bundle to hash and copy, a larger install to check, and the
      PSC-19 e2e checks.
    - Today a PR push costs one run of about 17 billed minutes (CT-7) on a
      private repo with 2,000 minutes a month. PSC-9's slower green run was
      24.5 min against a 37-min timeout. The scan used 88-98 s of its 180 s.
  - Options:
    1. The same trigger: if this item's added stages together add more
       than 180 s to the slower of two green CI runs (timed from marker
       line to marker line, as ADR-KE-013 amendment 1, D8), the
       orchestrator decides before the timeout is raised.
    2. A separate, larger budget for this item (for example 5 min), since
       the fetch is network-bound.
    3. A cumulative trigger: 3 min over the platform-supply-chain
       close-out job time, so every later item shares one margin.
    4. No trigger: PS-3.4 alone sets the timeout from the measured time.
  - Past the trigger (options 1-3): the timeout is not raised before the
    decision. The orchestrator either accepts and re-measures under PS-3.4,
    or asks the architect to cut the cost (for example Q63's reduced verify
    set). It brings the measurement and its decision to the human, since CI
    minutes are billed.
  - **Recommended: option 1.**
    - One rule for every stage added to `full` keeps the margin in view,
      and it is the rule already applied and met once (PSC-9).
    - 180 s is about 18% of today's 17-min run, enough for this item under
      Q63's recommended answer but not under a full fetch every run, which
      is the case that should get a decision.
    - Option 3 is the better long-run rule, but it changes how A60 is read
      for every later item, which is a wider call than this item.
  - Trade-off: a fixed trigger can force a decision on a cost that is
    worth paying. Option 4 keeps the rule simple, but the job grows by this
    item's cost with nobody deciding it.
  - Whichever is chosen, the added time is measured on CI (PSC-16); a local
    timing never counts.

- **Q63. Resolved 2026-10-22 (human ruling).** **A63:** REDUCED VERIFY SET.
  Every run builds all SBOMs, the full source index and the full coverage
  check, and fetches and ships one source of each kind. Operator bundles get
  the full set.

  Original question, kept for the record: *Q63. Does `verify.sh full`, and so
  CI, build the whole source set on every run?*
  - Context:
    - `offline_check.sh` builds and installs a real bundle in every `full`
      run, and CI's only step is `./scripts/verify.sh full` (a test
      enforces it).
    - PSC-15 estimates `sources/` at 1-2.5 GB per bundle. That is not a
      measurement.
    - The 7 GiB floor (R6) is the bundle (0.94 GiB amd64) plus the `dind`
      store after load (about 3.3 GiB), about 4.3 GiB, with about 60%
      headroom. CI had 9.1 GiB free at the offline stage (run
      39359710258).
    - The same derivation with 1-2.5 GB of sources gives a need of about
      5.3-6.8 GiB, and about 8.5-10.9 GiB with the same headroom: at or
      above what CI has today (estimate).
    - Install's staging copy sits on the offline client's `/install` tmpfs,
      so sources also add about their size to memory during install.
    - Each run would also fetch 1-2.5 GB from third-party hosts (the Q61
      exposure).
  - Options:
    1. **The full set every run.** The strongest proof, since what CI
       checks is what ships. It likely breaks the floor on today's runner
       (estimate), adds minutes of fetch time and gigabytes of memory, and
       makes every PR push depend on every source host.
    2. **A cached, content-addressed source set**, keyed by the SBOMs'
       package names and versions and fetched once per image or lock
       change. Locally it saves the fetch after the first run. GitHub's
       hosted runners keep nothing between runs, so on CI it helps only
       with a cache step outside `verify.sh`. That breaks "CI's only step
       is `./scripts/verify.sh full`" unless you rule otherwise, and it
       must then be listed in CLAUDE.md. The bundle's disk use is
       unchanged.
    3. **A reduced verify set, and the full set for every operator
       bundle.** `verify.sh full` builds every SBOM and the full source
       index: every GPL-family package mapped to its source URL and
       upstream checksum, so PSC-15's coverage rule is still checked in
       full. It fetches and ships only a fixed sample, one source of each
       kind (a Debian source package, an Alpine package, the Neo4j tag, the
       Temurin build and the psycopg sdist), and runs the PSC-19 e2e on
       it. `bundle.sh` run for an operator builds the full set, and each
       such bundle's full checks are recorded as evidence before it is
       handed over. Precedent: the verify run already leaves out `--tar`
       for disk (R6).
    4. **A separate CI job** (a second job or workflow, on a schedule or a
       tag) builds the full set. It breaks the single-step CI rule and its
       test, needs your ruling and a CLAUDE.md change, and spends runner
       minutes whenever it runs.
  - **Recommended: option 3.**
    - It keeps disk and memory near today's measured values, and keeps
      each PR run's network exposure to a few small files.
    - The coverage rule is checked in full every run; only the bytes are
      sampled, one per kind of source, so each fetch path is exercised.
    - The full set is proven where it matters, on the bundle that is
      handed to someone, with no CI-only step.
  - Trade-offs:
    - A component-specific fetch failure outside the sample, or a
      full-set disk or memory problem, is found only when an operator
      bundle is built. The recorded run is the control; option 1 would
      catch it on every push, at a cost CI likely cannot carry today.
    - Option 2 helps locally but not on hosted CI without a CI-only step.
  - Cost claims here are estimates. PSC-16 measures the chosen option on CI
    (two green runs) and re-derives the floor from the measurement; the
    floor is never lowered to pass. If option 1 is chosen and the runner
    cannot meet the re-derived floor, that is a blocker for you, not a
    reason to lower the floor.

- **Q64. Resolved 2026-10-22 (human ruling).** **A64:** build psycopg
  against Debian's libpq (`psycopg[c]` in `ke-app`'s builder stage, the Q42
  structural fix). `psycopg_binary.libs` is removed, its libraries become
  ordinary Debian packages, and the `srpm` source kind is not built. Built
  as PSC-25, unit U0 (`docs/requirements.md` § "Item: platform-sbom").
  L-13 closes under Q64 (platform-sbom U0).

  Original question, kept for the record: *Q64. Where does the source of
  the LGPL libraries vendored in psycopg-binary come from?* libcrypt and
  libkeyutils (LGPL-2.1) in `psycopg_binary.libs` come from the wheel's
  CentOS 7 (el7, manylinux2014) build image, at a release the wheel does
  not record (ADR-KE-016 flag (c); design notes N12). Options: (1) a `srpm`
  source kind from vault.centos.org with a reviewed best guess at the
  release, which may not be provably exact; (2) the libpq switch, which
  removes the vendored libraries.

- **Q65. Resolved 2026-10-22 (orchestrator ruling).** **A65:** the shipped
  `ke-app` image contains no psycopg-binary and uses `psycopg-c` built on
  Debian's libpq. How the lock, the dev hosts and `ke-gates` resolve
  psycopg is the architect's (ADR-KE-016), by platform markers or uv
  extras, within these limits: no CLAUDE.md or AGENTS.md change, no C
  toolchain on dev hosts, `--locked` everywhere, and the `uv run` log step
  keeps working on Windows. The lock test checks what the `ke-app` builder
  resolves (PSC-25, `test_ke_app_resolves_psycopg_c_not_binary`). The
  human's Q64 intent is unchanged.

  Original question, kept for the record: *Q65. psycopg-binary on hosts
  outside a Linux image.* It blocked U0's lock change (PSC-25, "Lock").
  - Context:
    - `uv.lock` is universal, and `uv run` syncs the project's runtime
      dependencies on whatever host runs it. Every role's log step
      (`uv run python -m harness_telemetry.log_event`, AGENTS.md) runs on
      the Windows dev host. Its `.venv` holds psycopg-binary today, from
      the `win_amd64` wheel.
    - `psycopg-c` is published as an sdist only. Without psycopg-binary in
      the lock, `uv run` on a host without `pg_config` and a C compiler has
      to build it, and is expected to fail (not tried). That would break
      the log step on the Windows dev host, and on any other host that
      runs it outside an image.
    - `ke-gates` also runs `uv sync --locked`, so it builds `psycopg-c`
      too. It does not ship, so a compiler there is a design choice, not a
      PSC-25 breach.
  - Options:
    1. **Platform markers:** `psycopg[c]` on Linux, `psycopg[binary]`
       elsewhere. psycopg-binary then stays in `uv.lock` under a marker
       that excludes Linux. PSC-25's lock bullet would become: "no
       `psycopg-binary` resolves for Linux, and no image installs it",
       with `test_lock_has_no_psycopg_binary` checking the marker.
    2. **Keep the lock free of psycopg-binary** and change how hosts run
       the log step, so that it does not install the project's runtime
       dependencies. That changes the AGENTS.md and CLAUDE.md command (the
       human's) and both agent sets.
    3. **A C toolchain and libpq on every dev host.** Heavy on Windows, and
       it breaks the log step for anyone without them.
  - Recommended: option 1. Q64's effect on what ships is unchanged (no
    image holds psycopg-binary), and the log step keeps working. Trade-off:
    `uv.lock` still names psycopg-binary, so the test pins the marker and
    the image check, not the lock's absence of the name.
  - Who rules: the orchestrator; the human if option 2 is chosen, since it
    changes CLAUDE.md.

- **Q66. Resolved 2026-10-22 (orchestrator ruling).** **A66:** accept
  Debian 12's libpq (the PostgreSQL 15 series); no apt.postgresql.org.
  Security re-rates the `require_auth` hardening follow-up at U0 review.
  Outcome 2026-10-23: security re-rated the follow-up low, re-scoped to
  auth-audit (see `docs/requirements.md`, the `require_auth` follow-up, and
  `docs/evidence/platform-sbom/u0/security.md`). Compensating control:
  Debian security updates arrive through the pin and base-image bumps, and
  the scan sees libpq5 through dpkg.

  Original question, kept for the record: *Q66. libpq drops from 18 to
  15.* It did not block U0.
  - Context:
    - psycopg-binary 3.3.6 vendors libpq 18.0.6 (PSC-7 evidence). Debian
      12's `libpq5` is the PostgreSQL 15 series. The stack's server is
      `postgres:16-bookworm`; a libpq 15 client connects to it.
    - The recorded L-13 hardening follow-up (`docs/requirements.md`,
      "`require_auth="scram-sha-256"` on every libpq connection", goes
      with `auth-audit`) relies on `require_auth`, which libpq has only
      from 16. It guarded the vendored el7 krb5. Under PSC-25 that krb5 is
      gone, and the GSSAPI code is Debian's krb5, which Debian's security
      updates patch. `gssencmode="disable"` stays.
  - Options:
    1. **Accept Debian's libpq 15.** Security re-rates the follow-up: keep
       it for when libpq 16+ is available, re-scope it, or retire it.
    2. **libpq 16+ from the PostgreSQL apt repository**
       (apt.postgresql.org). This adds a new apt source with its own
       signing-key provenance (Q48), a new fetch host, and source that
       snapshot.debian.org does not hold, so the `deb` source kind would
       need another route.
  - Recommended: option 1. It keeps Q64's "ordinary Debian packages", and
    the risk the follow-up addressed is removed by the switch itself.
  - Who rules: the orchestrator, with security's rating.

- **Q67. Resolved 2026-10-23 (human ruling).** **A67:** the bundle ships
  our own neo4j image, built from the pinned
  `neo4j:5-community@sha256:0a6e7aedf54a531f76286032d4365ead65b11cca05e4a15cdf23b8e53d6db02b`
  with `/var/lib/neo4j/products` (the commercially licensed
  fleet-management plugin) removed, and flattened (`FROM scratch` +
  `COPY --from`, as `ke-app`, N10a) so the jar is not in the saved tar.
  Built as PSC-26, unit U4b, after U4 (`docs/requirements.md` § "Item:
  platform-sbom"). Raised by security as U4 M-3
  (`docs/evidence/platform-sbom/u4/security.md`).

  Original question, kept for the record: *Q67. May the bundle
  redistribute the commercial jar in the official neo4j image?*
  - Context: the official `neo4j:5-community` image ships
    `com.neo4j/neo4j-fleet-management-plugin` 1.2.0 in
    `/var/lib/neo4j/products`. It is inactive by default. Its notice
    reads: "Use of this Software without a proper commercial license with
    Neo4j, Inc. ... is prohibited". It is not GPL-family.
  - Options:
    1. Ship the official image unmodified and defer to SFU legal (citing
       Neo4j's terms for redistributing the image).
    2. Build our own image without `products/`.
  - Who rules: the human.

- **Q68. Resolved 2026-10-23 (orchestrator ruling).** **A68:** option 3.
  U4b does not add `ke-neo4j` to the image scan, so the scan scope stays as
  it is today: `scripts/scan.sh` scans `ke-app` only, and `ke-gateway` and
  the vendored images are not scanned either. Reason: option 1 would likely
  turn every `full` run red on upstream jar CVEs that only a Neo4j digest
  bump can fix, and option 2 changes the Q42 policy, which is the human's
  call. Scanning every bundled image (report-only or fail mode, with the CI
  cost measured) is recorded as a follow-up for the human
  (`docs/requirements.md` § "Item: platform-sbom", "Follow-ups (not in
  platform-sbom)", "Scan every bundled image").

  Original question, kept for the record: *Q68. How does the image scan
  treat `ke-neo4j`?* It blocked only PSC-26's *Scanned* bullet.
  - Context:
    - `scripts/scan.sh` scans only the `ke-app` tar today, under PSC-4
      (fail on any High or Critical with a fixed version) and PSC-5
      (ignore entries, 90-day cap). The third-party stack images, the
      official neo4j among them, are not scanned.
    - `ke-neo4j` holds the official image's files minus `products/`. A
      fixed High in a jar Neo4j ships, or in the Temurin JDK, can be
      fixed only by a newer upstream digest, not by us.
    - The orchestrator's brief for PSC-26 says `ke-neo4j` is scanned as a
      first-party image.
  - Options:
    1. Scan it under PSC-4 and PSC-5, as `ke-app`: a fixed High or
       Critical fails `verify.sh full` until a digest bump or a
       time-limited ignore entry whose reason security confirms.
    2. Scan it and report the matches without failing (a new mode, which
       changes the Q42 policy for this image).
    3. Do not scan it, as today for the official image.
  - Recommended: option 1. It is what a first-party image gets today and
    needs no new policy. Trade-off: `full` can turn red on an upstream
    finding we cannot fix ourselves, and the 90-day cap then forces a
    digest bump. The scan time it adds is measured on CI (PSC-16).
  - Who rules: the orchestrator; the human for option 2, since it changes
    the Q42 policy.

- **Q69. Resolved 2026-10-23 (human ruling).** **A69:** source ships.
  U7's generated source lock carries the Debian `gcc-12` and `gcc-14`
  source packages via the `deb` kind, with no exemption under the GCC
  Runtime Library Exception. This is the design default (architecture
  N10). *(Amended 2026-10-23, analyst, Q69/Q70)*

  Original question, kept for the record: *Q69. For the GCC runtime
  libraries (`upstream=gcc-12` in `ke-app` and postgres, `upstream=gcc-14`
  in neo4j and phoenix; PSC-22 `always` list), does the bundle ship
  their Debian source or record a reviewed exemption?* Raised as a
  platform-sbom follow-up (`docs/requirements.md` § "Item:
  platform-sbom", "Follow-ups (not in platform-sbom)"), to be decided
  before U7. Who rules: the human.

- **Q70. Resolved 2026-10-23 (human ruling).** **A70:** not now. The
  bundled images other than `ke-app` (`ke-gateway`, `ke-neo4j`, and the
  vendored postgres, valkey and phoenix) are not scanned for now. The
  Q68 follow-up "Scan every bundled image" is closed as deferred by the
  human, with no work in platform-sbom. *(Amended 2026-10-23, analyst, Q69/Q70)*

  Original question, kept for the record: *Q70. Does the image scan
  cover every bundled image, in report-only mode (a Q42 policy change)
  or fail mode (PSC-4, PSC-5), with the CI cost measured first?* Raised
  by A68. Who rules: the human.

- **Q71. Open (raised 2026-10-25, analyst, U7).** *Where does the bundle
  get the source of the three postgres-image packages that come from the
  PostgreSQL project's Debian archive (PGDG), not from Debian?*
  *(Added 2026-10-25, analyst, U7)*
  - Context: the `postgres` image ships `postgresql-16 16.15-1.pgdg12+2`,
    `postgresql-18 18.6-1.pgdg12+2` (which also builds the image's
    `libpq5`) and `postgresql-common 293.pgdg12+1`.
    - PGDG builds them, so `snapshot.debian.org` does not have their
      source, and the U7 lock (PSC-15 option 1) cannot get it through the
      `deb` kind.
    - Every fetch host is in `docker/source-policy.json` `hosts` (PSC-22,
      U6; nine hosts today). U8's fetch refuses any other host (PSC-23).
    - Source: design notes "N5 amendment, U7", point O1
      (`docs/evidence/platform-sbom/design-notes.md`).
  - Options:
    1. A `pgdg` lock kind and a tenth fetch host,
       `apt-archive.postgresql.org` (PGDG's archive of every published
       version). The kind takes the same `.dsc` chain as `deb`, from
       `https://apt-archive.postgresql.org/pub/repos/apt/pool/main/<p>/<src>/`.
       This amends:
       - the U6 host-set test (ten hosts);
       - ADR-KE-016 point 4;
       - the SFU egress list that ADR-KE-016 records (PSC-23).
       Security reviews the host and the kind.
    2. Upstream PostgreSQL release tarballs. They lack PGDG's `debian/`
       packaging and patches, so they are not the corresponding source of
       the shipped binaries.
    3. A reviewed `exempt` entry per package. `postgresql-common` is plain
       GPL-2.0 with no OR branch to elect, so no exemption reason can be
       justified (PSC-22's `exempt` rules).
  - Recommended (architect, adopted by the analyst): option 1. It ships
    the exact corresponding source, as the `deb` kind does for Debian's
    packages. Its only new cost is one host on the egress list.
    Trade-off: the bundle-time fetch gains a route to a host that SFU's
    egress rules may need to allow.
  - Who rules: the human, because the SFU egress list is the human's.
  - Deadline: before U7c (the `deb`, `apk` and `pgdg` routes). Until it is
    ruled, U7c's `pgdg` route is not built, and the three keys stay
    without an entry, so the source check fails closed (Q61).

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

- **Q42. Resolved 2026-10-21 (orchestrator ruling,
  `docs/handoffs/platform-supply-chain.md`).** **A42 (ruled):** keep A42
  (fail on fixed High/Critical); each ignore entry needs a reason plus
  `until` ≤ 90 days; psycopg-binary per the analyst default (upgrade if a
  fix exists, else a time-limited ignore stating why the path is
  unreachable, confirmed by security, plus a follow-up on Debian libpq).
  Built as PSC-4 and PSC-5 (`docs/requirements.md` § "Item:
  platform-supply-chain"). The psycopg-binary half is moot for the scan
  (2026-10-21, PSC-7 outcome below). Original question and the analyst's
  default, kept for the record:

  *Q42. Scan threshold and the vendored libraries.* **A42 (assumed):**
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

  **Recommended default (analyst, 2026-10-21, `platform-supply-chain`
  PSC-4, PSC-5; not a ruling).**
  - *Threshold.* Keep A42 and cap each ignore entry's `until` at 90 days.
    - Trade-off: an unfixed Critical never fails the run and is visible
      only in the log.
    - Failing on unfixed Criticals as well would catch them, but could hold
      `full` red for weeks with nothing to upgrade to. Those findings would
      then end up in the ignore file anyway.
  - *psycopg-binary libraries.* If a newer psycopg-binary wheel fixes a
    flagged library, upgrade the lock. If none does, accept the finding as a
    time-limited ignore entry and open a follow-up item to evaluate psycopg
    on Debian's libpq. The entry's reason states why the code path is not
    reached (for krb5, `gssencmode=disable`, L-13), and security confirms
    it.
    - Trade-off: exceptions leave `ke-app` and the notices unchanged, but
      `ke-app` keeps shipping old native code.
    - The switch removes the vendored libraries (and part of M-NT1's list)
      and hands their CVEs to Debian's security updates. But it changes
      `ke-app` and needs apt pinning. It changes `NOTICE.md`: psycopg stays
      LGPL-3.0, and libpq comes under the PostgreSQL licence. It also needs
      a new Windows run and a CI re-measure.
  - If the scanner does not see `psycopg_binary.libs` at all (PSC-7), the
    second half of Q42 is moot for the scan, and L-13 stays a documented
    residual.
    - *Outcome 2026-10-21 (PSC-7, ADR-KE-013 amendment 1, D6;
      `docs/evidence/platform-supply-chain/u4-psc7-psycopg-libs.txt`):*
      grype v0.120.1 catalogues none of the 15 files in
      `psycopg_binary.libs` (OpenSSL 3.5.8, libpq 18.0.6, pcre 8.32,
      cyrus-sasl 2.1.26, the el7 krb5, ...). The psycopg-binary half of
      Q42 is therefore **MOOT for the scan**: it can never flag a vendored
      library. L-13 is an accepted residual, rated low by security. The
      compensating control is tracking psycopg-binary releases (the
      libraries move with the wheel); `gssencmode=disable` is today's
      mitigation; the structural fix stays the switch to psycopg on
      Debian's libpq.
    - L-13 closes under Q64 (platform-sbom U0). *(Added 2026-10-22,
      analyst, Q64; § platform-sbom, PSC-25.)*
  - Who rules: the orchestrator or security, as before. The 90-day cap is
    the orchestrator's or the human's call.

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
  - **Amended 2026-10-21 (rework 3, human ruling: pool withdrawn).** The rule
    stands, applied per coverage run label instead of per pooled module.
    The labels are `toplevel` (the one top-level run), `tests.<pkg>` and
    `tests.integration`. Each run label must leave its own data file, and a
    missing file or a file left after `combine` fails the run, naming the
    label (CS-4, architecture §2.2.1-r3 decision 3). There is still no
    percentage tolerance, and 80 % is unchanged.

Resolved 2026-10-21 by the orchestrator for `ci-speed` (raised by the
architect in rework 3):

- **Q-CS2. Resolved 2026-10-21 (orchestrator ruling: A-CS2 accepted, as
  covered by the human's CPU-time ruling).** **A-CS2:** the 400-segment L8
  test moves to CPU time with the 3 s and 9 s tests, and its 5 s value is
  unchanged (CS-12, architecture §2.2.1-r3 decision 6). Original question,
  kept for the record: *Does the 5 s L8 hook test move to CPU time too?* The
  human ruling moves the hook budget tests to CPU time, naming the 3 s and
  9 s budgets. `test_long_command_finishes_quickly` (security L8: 400
  segments under 5 s) is the same kind of wall-clock budget test. If it
  stays on wall time, it can still flake on a loaded runner.

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
